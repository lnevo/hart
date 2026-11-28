#!/usr/bin/env bash
# Run a repo command (checks, tests, builds) on the Windows box's WSL Ubuntu instead of the Mac,
# to spare the Mac's CPU (8 cores, often busy). Output streams back; the exit code is the command's.
#
#   tools/hosts/win_run.sh [--ref REF] [--keep] [--] COMMAND...
#   make remote CMD="./tools/check.sh"
#
# REF defaults to the current branch; its commit must already be on origin (push first), since
# the Windows clone (~/hart in WSL) fetches from GitHub. Each run gets its own worktree under
# ~/wt there, with the gitignored mirrors (media, ops/car-cards, ops/hart-ops/.venv) linked and
# every submodule checked out, so runs from several agents do not collide.
# Every run's whole output is saved on the Mac in <cache>/remote-logs (the newest WIN_RUN_KEEP_LOGS, default 20),
# with the remote's stderr merged into stdout; the run ends with its failed jobs, then "log: <path>".
# --keep leaves that worktree for a look afterwards. Python is ~/hart/.venv (3.13, requirements.txt).
#
# Not for: make panelpro-test, screenshots, deploys, or anything that reads the Mac's
# JMRI_UserFiles. Refuses while the operating flag is set: CATS runs on that box during a session.
# Exit 3 means the box could not be used (flag set, unreachable, setup failed): run the command on the Mac.
# WSL's CPU cap (8 of 16 threads) is processors=8 in %USERPROFILE%\.wslconfig on Windows.
# At most WIN_RUN_SLOTS runs at once from this Mac: a run waits for a free slot /tmp/hart-remote.lock.N (the mac lock block).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"
source "$ROOT/tools/hosts/profile_tables_guard.sh"     # hart_cache_dir, sent to Windows below
WIN="${HART_WIN_SSH:?HART_WIN_SSH is not set}"
PORT="${HART_WIN_SSH_PORT:-2222}"
DISTRO="${HART_WIN_WSL_DISTRO:-Ubuntu-24.04}"

ref="" keep=0 print_script=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) ref="${2:?--ref needs a value}"; shift 2 ;;
    --keep) keep=1; shift ;;
    --print-script) print_script=1; shift ;;   # print what would run on Windows (sha = this HEAD) and stop: for tests
    --) shift; break ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) echo "win_run.sh: unknown option $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
[[ $# -gt 0 ]] || { echo "win_run.sh: no command given (try --help)" >&2; exit 2; }

# --- stamp name (tests run this block alone)
# stamp_name GITDIR REF SHA prints the name of REF's stamp folder on Windows: "main" for main (its runs keep the shared
# folder), else the branch name with every character but letters, digits, - and _ made _, cut to 60, and the first 10
# hex of git's hash of the full name (so a/b and a_b get two folders); REF that names no local or remote-tracking
# branch (a commit, a tag, HEAD~1) gives SHA.
stamp_name() {
  local branch="" safe LC_ALL=C     # bytes, not the locale's letters: é is two _, as on every machine
  if git -C "$1" show-ref --verify -q "refs/heads/$2"; then branch="$2"
  elif git -C "$1" show-ref --verify -q "refs/remotes/$2"; then branch="${2#*/}"
  fi
  if [[ -z "$branch" ]]; then
    [[ "$3" =~ ^[0-9a-f]{40}$ ]] || { echo "win_run.sh: $3 is not a commit sha (for $2's stamp folder)" >&2; return 2; }
    echo "$3"; return 0
  fi
  if [[ "$branch" == main ]]; then echo main; return 0; fi
  safe="${branch//[^A-Za-z0-9_-]/_}"
  echo "${safe:0:60}-$(printf '%s' "$branch" | git hash-object --stdin | cut -c1-10)"
}
# --- end stamp name

if [[ -z "$ref" ]]; then
  ref="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
  [[ "$ref" != HEAD ]] || ref="$(git -C "$ROOT" rev-parse HEAD)"
fi
if [[ $print_script -eq 0 ]]; then
# operating.sh status: 0 = set, 1 = clear. Anything else (broken, missing) counts as set: fail closed.
flag_rc=0
"$ROOT/tools/hosts/operating.sh" status >/dev/null 2>&1 || flag_rc=$?
if [[ $flag_rc -ne 1 ]]; then
  echo "win_run.sh: the operating flag is set (or unreadable, status $flag_rc), so the Windows box is left to CATS; run the command on the Mac." >&2
  exit 3
fi

# The commit to run: the branch's (or REF's), which origin must have.
sha="$(git -C "$ROOT" rev-parse --verify "$ref^{commit}")" || { echo "win_run.sh: unknown ref $ref" >&2; exit 2; }
if ! git -C "$ROOT" fetch -q origin; then
  echo "win_run.sh: could not fetch origin from the Mac; run the command on the Mac." >&2
  exit 3
fi
if ! git -C "$ROOT" branch -r --contains "$sha" | grep . >/dev/null; then
  echo "win_run.sh: $ref ($sha) is not on origin; push it first (git push -u origin HEAD)." >&2
  exit 2
fi
if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]]; then
  echo "win_run.sh: note: uncommitted changes here are not sent; the run uses $sha." >&2
fi
else
  sha="$(git -C "$ROOT" rev-parse HEAD)"
fi
stamps="$(stamp_name "$ROOT" "$ref" "$sha")" || exit 2

cmd="$(printf '%q ' "$@")"
run_id="$(date +%Y%m%d-%H%M%S)-$$"
# Concurrent runs allowed on the Windows box (WIN_RUN_SLOTS, default 2); each gets nproc/slots check.sh jobs.
slots="${WIN_RUN_SLOTS:-2}"
[[ "$slots" =~ ^[1-9][0-9]*$ ]] || { echo "win_run.sh: WIN_RUN_SLOTS must be a whole number above 0, got $slots" >&2; exit 2; }
# The newest remote-run logs kept on the Mac (the log block, below).
keep_logs="${WIN_RUN_KEEP_LOGS:-20}"
[[ "$keep_logs" =~ ^[1-9][0-9]*$ ]] || { echo "win_run.sh: WIN_RUN_KEEP_LOGS must be a whole number above 0, got $keep_logs" >&2; exit 2; }

# The remote script goes over stdin to bash inside WSL, so no quoting passes through Windows' shell; the command
# itself reads /dev/null, or it would eat the rest of the script. Exit codes: a setup failure there is 3 (use the
# Mac); the command's own 3 or 255 becomes 1, so 3 and 255 always mean the box, never the command.
# The script is printed in parts (remote_script runs them in order); each part fills in this run's values ($sha,
# $run_id, $keep, $stamps, $slots, $cmd) and escapes what the remote shell expands.
remote_setup() {   # the shell options, the worktree for $sha and its links and submodules; ends in the worktree
  cat <<EOF
set -euo pipefail
trap 'echo "win_run.sh: setup on Windows failed; run the command on the Mac." >&2; exit 3' ERR
export PATH="\$HOME/hart/.venv/bin:\$HOME/.local/bin:\$PATH"
main="\$HOME/hart" wt="\$HOME/wt/$run_id"
mkdir -p "\$HOME/wt"
# One fetch at a time into the shared clone: parallel runs would fight over its ref locks.
flock "\$main/.git/win_run.lock" git -C "\$main" fetch -q origin $sha
git -C "\$main" worktree add -q --detach "\$wt" $sha
cleanup() {
  if [[ $keep -eq 1 ]]; then echo "win_run.sh: kept \$wt" >&2
  else git -C "\$main" worktree remove --force "\$wt" || echo "win_run.sh: warning: could not remove \$wt" >&2; fi
}
trap cleanup EXIT
# The links must not show as untracked (a dirty tree changes what some tests stage), as in tools/agent/worktrees.py.
exclude="\$(git -C "\$main" rev-parse --path-format=absolute --git-common-dir)/info/exclude"
for rel in media ops/car-cards ops/hart-ops/.venv; do
  grep -qxF "/\$rel" "\$exclude" 2>/dev/null || echo "/\$rel" >> "\$exclude"
  if [[ -e "\$main/\$rel" ]]; then ln -sfn "\$main/\$rel" "\$wt/\$rel"; fi
done
# Every submodule, borrowing objects from the main clone's copy when it has one (a new submodule it lacks).
git -C "\$wt" config -f .gitmodules --get-regexp '\.path\$' | while read -r _ sub; do
  if git -C "\$main/\$sub" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "\$wt" submodule update --init -q --reference "\$main/\$sub" "\$sub"
  else
    git -C "\$wt" submodule update --init -q "\$sub"
  fi
done
cd "\$wt"
EOF
}
remote_stamps() {   # the run's CHECK_STAMPS_DIR
  cat <<EOF
# --- stamps (tests run this block alone)
# check.sh's stamps (tools/audit/check_stamps.py, CHECK_STAMPS_DIR). One folder for every branch would hold whichever
# branch ran last, with reads of files only that branch has, so main's runs keep the shared folder
# (<cache>/check-stamps) and each other ref gets <cache>/check-stamps-by-ref/<name>, copied from the shared one on
# its first run: a copy, never a link, so one ref's records never change another's. A copied stamp is
# safe: a job is skipped only when its key and every hash of its read set match this checkout (check_stamps.py
# why_not_current, traced.mismatch). filehash.json is not copied: its keys are other runs' worktree paths.
# Under one lock: folders untouched for 14 days are removed first, the copy goes to a temp folder that is renamed
# into place, and the folder is touched, so two runs of one ref never see half a copy.
$(declare -f hart_main_checkout hart_cache_dir)
ref_stamps() {   # <shared> <by-ref folder> <name>: make or reuse <by-ref folder>/<name>; return 3 with a message
  local shared="\$1" byref="\$2" dir="\$2/\$3" tmp="\$2/.\$3.tmp.\$\$" old removed=0 how f
  local -a files=()
  while IFS= read -r -d '' old; do
    # an old folder that will not go is litter, not a reason to refuse the run: warn and go on
    if rm -rf "\$old"; then removed=\$((removed + 1))
    else echo "win_run.sh: warning: could not remove the old stamp folder \$old; remove it by hand" >&2; fi
  done < <(find "\$byref" -mindepth 1 -maxdepth 1 -type d -mtime +13 -print0)
  if [[ -d "\$dir" ]]; then
    how="reused"
  else
    if [[ -d "\$shared" ]]; then
      for f in "\$shared"/*.json; do
        if [[ -f "\$f" && "\${f##*/}" != filehash.json ]]; then files+=("\$f"); fi
      done
    else
      echo "win_run.sh: no shared stamps at \$shared yet; \$3 starts with none" >&2
    fi
    if ! { rm -rf "\$tmp" && mkdir "\$tmp"; }; then echo "win_run.sh: could not make \$tmp" >&2; return 3; fi
    if (( \${#files[@]} )) && ! cp -- "\${files[@]}" "\$tmp/"; then
      rm -rf "\$tmp"
      echo "win_run.sh: could not copy the stamps of \$shared into \$dir; run the command again, or on the Mac." >&2
      return 3
    fi
    f=\$(( \$(find "\$tmp" -maxdepth 1 -name '*.json' -type f | wc -l) ))   # BSD wc pads the number
    if (( f != \${#files[@]} )); then
      rm -rf "\$tmp"
      echo "win_run.sh: copied \$f of \${#files[@]} stamps from \$shared; \$dir was not made" >&2
      return 3
    fi
    if ! mv "\$tmp" "\$dir"; then rm -rf "\$tmp"; echo "win_run.sh: could not move \$tmp to \$dir" >&2; return 3; fi
    how="new, \${#files[@]} stamps copied from \$shared"
  fi
  touch "\$dir" || { echo "win_run.sh: could not touch \$dir" >&2; return 3; }
  echo "win_run.sh: stamps in \$dir (\$how; \$removed stamp folders untouched for 14 days removed)" >&2
}
shared="\$(hart_cache_dir "\$main" check-stamps)"
if [[ "$stamps" == main ]]; then
  export CHECK_STAMPS_DIR="\$shared"
  echo "win_run.sh: stamps in \$shared (main's, shared)" >&2
else
  byref="\$(hart_cache_dir "\$main" check-stamps-by-ref)"
  mkdir -p "\$byref" || { echo "win_run.sh: could not make \$byref; run the command on the Mac." >&2; exit 3; }
  if ! ( flock 7 && ref_stamps "\$shared" "\$byref" "$stamps" ) 7>"\$byref/.lock"; then
    echo "win_run.sh: the stamp folder $stamps was not set up (above); run the command on the Mac." >&2
    exit 3
  fi
  export CHECK_STAMPS_DIR="\$byref/$stamps"
  [[ -d "\$CHECK_STAMPS_DIR" ]] || { echo "win_run.sh: \$CHECK_STAMPS_DIR is missing after setup" >&2; exit 3; }
fi
# --- end stamps
EOF
}
remote_ruff() {   # the ruff the commit pins, first on PATH
  cat <<EOF
# --- ruff (tests run this block alone)
# The ruff this commit pins (requirements.txt, read by tools/audit/check_ruff.py --pin), installed once per version in
# ~/.cache/hart/ruff/<version> with uv and put first on PATH: runs of commits that pin other versions never share an
# install. A commit from before the pin installs nothing. A failed install is a warning, not a setup failure: check.sh's
# ruff job then says which ruff it lacks, and any other command runs as before.
install_ruff() {   # <folder> <ruff==X>: into a temp folder, then moved into place, so a half install is never used
  [[ -x "\$1/bin/ruff" ]] && return 0
  rm -rf "\$1.tmp"
  uv pip install -q --target "\$1.tmp" "\$2" && mv "\$1.tmp" "\$1"
}
if [[ -f tools/audit/check_ruff.py ]]; then
  if want="\$(python3 tools/audit/check_ruff.py --pin 2>&1)"; then
    rdir="\$HOME/.cache/hart/ruff/\${want#ruff==}"
    mkdir -p "\$HOME/.cache/hart/ruff"
    if ( flock 8 && install_ruff "\$rdir" "\$want" ) 8>"\$HOME/.cache/hart/ruff/.lock" >&2; then
      export PATH="\$rdir/bin:\$PATH"
    else
      echo "win_run.sh: warning: could not install \$want into \$rdir; the ruff job will fail" >&2
    fi
  else
    echo "win_run.sh: warning: no ruff pin (\$want); the ruff job will fail" >&2
  fi
fi
# --- end ruff
EOF
}
remote_venv() {   # ~/hart/.venv brought up to the commit's requirements.txt
  cat <<EOF
# --- venv (tests run this block alone)
# ~/hart/.venv follows the requirements.txt of the commit being run: when that file's sha256 differs from the one the
# venv last took, uv installs it (under a lock, so two runs never install at once) and records the sha256. A failed
# install is a warning, not a setup failure: the job that needs a missing package then says which one.
if [[ -f requirements.txt ]]; then
  want_req="\$(sha256sum requirements.txt | cut -d' ' -f1)"
  req_stamp="\$HOME/hart/.venv/.requirements.sha256"
  if [[ "\$(cat "\$req_stamp" 2>/dev/null || true)" != "\$want_req" ]]; then
    mkdir -p "\$HOME/.cache/hart"
    if ( flock 8 && uv pip install -q --python "\$HOME/hart/.venv/bin/python" -r requirements.txt \
           && echo "\$want_req" > "\$req_stamp" ) 8>"\$HOME/.cache/hart/venv.lock" >&2; then
      echo "win_run.sh: ~/hart/.venv now has this commit's requirements.txt" >&2
    else
      echo "win_run.sh: warning: could not install requirements.txt into ~/hart/.venv; a job that needs a new package will fail" >&2
    fi
  fi
fi
# --- end venv
EOF
}
remote_slots() {   # a free run slot and the run's CHECK_MAX_JOBS
  cat <<EOF
# --- slots (tests run this block alone)
# At most $slots runs at once, each with its share of the CPUs: more runs only slow each other down. A run waits
# here for a free slot; the slot is held on fd 9 until the command ends.
got=""; waited=0
while [[ -z "\$got" ]]; do
  for i in \$(seq 0 $((slots - 1))); do
    exec 9>"\$main/.git/win_run.slot\$i"
    if flock -n 9; then got=\$i; break; fi
    exec 9>&-
  done
  if [[ -z "\$got" ]]; then
    if [[ \$waited -eq 0 ]]; then echo "win_run.sh: $slots runs already going on Windows; waiting for a free slot" >&2; fi
    waited=1; sleep 10
  fi
done
export CHECK_MAX_JOBS=\$(( \$(nproc) / $slots > 1 ? \$(nproc) / $slots : 2 ))
# --- end slots
EOF
}
remote_command() {   # the command itself, and its exit code
  cat <<EOF
trap - ERR
echo "win_run.sh: $sha on \$(hostname) (WSL, \$(nproc) CPUs, slot \$got of $slots, \$CHECK_MAX_JOBS jobs): $cmd" >&2
set +e
$cmd </dev/null
rc=\$?
set -e
if [[ \$rc -eq 3 || \$rc -eq 255 ]]; then echo "win_run.sh: the command exited \$rc (reported as 1)" >&2; rc=1; fi
exit \$rc
EOF
}
remote_script() {   # the whole script, its parts in order
  remote_setup && remote_stamps && remote_ruff && remote_venv && remote_slots && remote_command
}

if [[ $print_script -eq 1 ]]; then remote_script; exit 0; fi
# --- log (tests run this block alone)
# Every run's whole output (its stderr too) is saved, so a failed run never has to be repeated to see which job failed,
# even when the caller keeps only the last lines: <cache>/remote-logs/<stamp name>-<YYYYmmdd-HHMMSS>-<pid>.log, the
# newest WIN_RUN_KEEP_LOGS (default 20) kept. The run ends with every "--- <job> FAILED" line and, last, "log: <path>",
# so even a caller's tail shows where to look. A log that cannot be written is a warning; the run goes on.
start_log() {   # <folder> <name>: prints the log's path, or nothing when it cannot be made
  mkdir -p "$1" 2>/dev/null && : >"$1/$2.log" 2>/dev/null && echo "$1/$2.log"
}
prune_logs() {   # <folder> <keep>: remove all but the newest <keep> .log files (names sort by time per ref; mtime here)
  local -a old=()
  local f
  while IFS= read -r f; do old+=("$f"); done < <(ls -1t "$1"/*.log 2>/dev/null | tail -n +"$(( $2 + 1 ))")
  if (( ${#old[@]} )); then rm -f -- "${old[@]}" || echo "win_run.sh: warning: could not prune old logs in $1" >&2; fi
}
end_log() {   # <log>: the failed jobs it holds, then where it is
  grep -E '^--- .* FAILED' "$1" || true
  echo "log: $1"
}
finish_log() {   # <log> <folder> <keep>: on every exit of a logged run, a stopped one too
  end_log "$1"
  prune_logs "$2" "$3"
}
run_logged() {   # <log> <header> COMMAND...: remote_script into COMMAND, its stdout and stderr shown and appended to <log>;
  # returns COMMAND's exit code
  local rcs
  { set +e   # a subshell (the pipeline's left side): the failed command's code is reported, not acted on
    echo "$2"
    remote_script | "${@:3}" 2>&1
    r=${PIPESTATUS[1]}   # COMMAND's: read before any other command resets PIPESTATUS
    echo "win_run.sh: exit $r"
    exit "$r"
  } | tee -a "$1"
  rcs=("${PIPESTATUS[@]}")
  return "${rcs[0]}"
}
# --- end log
# --- mac lock (tests run this block alone)
# At most $slots remote runs at once from this Mac (WIN_RUN_SLOTS, the box's own limit), whoever starts them (the
# owner, a session, make ready). Each slot is the folder <WIN_RUN_LOCK>.<n> for n = 1 .. slots (default
# /tmp/hart-remote.lock.1 and .2), made with mkdir, holding an owner file "pid since-epoch ref". A run takes the first
# free slot and waits, with a line every minute, only when every slot is held. A slot whose holder process is gone
# (or that has no owner file) and which is older than WIN_RUN_LOCK_STALE seconds (default 2700, longer than any
# check.sh run) is stale: it is renamed away and cleared with a line. release_lock runs on every exit (the EXIT trap below) and removes only the slot this process
# holds.
lock_base="${WIN_RUN_LOCK:-/tmp/hart-remote.lock}"
lock_dir=""
claim_slot() {   # <folder> <ref>: 0 when mkdir made the slot for this process
  mkdir "$1" 2>/dev/null || return 1
  lock_dir="$1"
  echo "$$ $(date +%s) $2" >"$1/owner"
}
take_lock() {   # <ref>: returns once this process holds a slot, its folder in lock_dir
  local waited=0 i dir pid since age holders line
  while true; do
    holders=""
    for i in $(seq 1 "$slots"); do
      dir="$lock_base.$i"
      if claim_slot "$dir" "$1"; then return 0; fi
      line="$(cat "$dir/owner" 2>/dev/null || true)"
      read -r pid since _ <<<"$line" || true
      # no owner file (a holder killed between mkdir and the write): the folder's own time stands in
      [[ -n "$since" ]] || since="$(stat -f %m "$dir" 2>/dev/null || stat -c %Y "$dir" 2>/dev/null || date +%s)"
      age=$(( $(date +%s) - since ))
      if { [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; } && (( age > ${WIN_RUN_LOCK_STALE:-2700} )); then
        # clear it only if the owner is still the one judged stale, and by a rename, so a waiter that judged the
        # same slot stale cannot remove a claim another waiter has just made
        if [[ -d "$dir" && "$(cat "$dir/owner" 2>/dev/null || true)" == "$line" ]] && mv "$dir" "$dir.stale.$$" 2>/dev/null; then
          echo "win_run.sh: $dir is stale (holder ${pid:-none} gone, $(( age / 60 )) min old); cleared it" >&2
          rm -rf "$dir.stale.$$"
        fi
        if claim_slot "$dir" "$1"; then return 0; fi
      fi
      holders="$holders ${pid:-?} ($(( age / 60 )) min)"
    done
    if (( waited % ${WIN_RUN_LOCK_SAY:-60} == 0 )); then
      echo "win_run.sh: $(date +%H:%M) all $slots remote slots ($lock_base.N) are held:$holders; waiting" >&2
    fi
    sleep "${WIN_RUN_LOCK_POLL:-5}"
    waited=$(( waited + ${WIN_RUN_LOCK_POLL:-5} ))
  done
}
release_lock() {
  if [[ -n "$lock_dir" ]]; then rm -f "$lock_dir/owner"; rmdir "$lock_dir" 2>/dev/null || true; lock_dir=""; fi
}
# --- end mac lock
trap 'release_lock' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
take_lock "$ref"
logs="$(hart_cache_dir "$ROOT" remote-logs)"
log="$(start_log "$logs" "$stamps-$run_id")" || log=""
if [[ -n "$log" ]]; then
  # on every exit, a stopped or cut-off run too (Ctrl-C, a superseded run's TERM): the failed jobs, the path, the prune
  trap 'release_lock; finish_log "$log" "$logs" "$keep_logs"' EXIT
else
  echo "win_run.sh: warning: could not write a log in $logs; this run's output is not saved" >&2
fi
set +e
if [[ -n "$log" ]]; then
  run_logged "$log" "win_run.sh: $ref ($sha) on $WIN: $cmd" \
    ssh -o ConnectTimeout=8 -o LogLevel=ERROR -p "$PORT" "$WIN" "wsl.exe -d $DISTRO -- bash -s"
  rc=$?
else
  remote_script | ssh -o ConnectTimeout=8 -o LogLevel=ERROR -p "$PORT" "$WIN" "wsl.exe -d $DISTRO -- bash -s"
  rc=$?
fi
set -e
if [[ $rc -eq 255 ]]; then
  echo "win_run.sh: could not reach $WIN; run the command on the Mac." >&2
  exit 3
fi
exit $rc
