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
# --keep leaves that worktree for a look afterwards. Python is ~/hart/.venv (3.13, requirements.txt).
#
# Not for: make panelpro-test, screenshots, deploys, or anything that reads the Mac's
# JMRI_UserFiles. Refuses while the operating flag is set: CATS runs on that box during a session.
# Exit 3 means the box could not be used (flag set, unreachable, setup failed): run the command on the Mac.
# WSL's CPU cap (8 of 16 threads) is processors=8 in %USERPROFILE%\.wslconfig on Windows.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"
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
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    -*) echo "win_run.sh: unknown option $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
[[ $# -gt 0 ]] || { echo "win_run.sh: no command given (try --help)" >&2; exit 2; }

if [[ $print_script -eq 0 ]]; then
# operating.sh status: 0 = set, 1 = clear. Anything else (broken, missing) counts as set: fail closed.
flag_rc=0
"$ROOT/tools/hosts/operating.sh" status >/dev/null 2>&1 || flag_rc=$?
if [[ $flag_rc -ne 1 ]]; then
  echo "win_run.sh: the operating flag is set (or unreadable, status $flag_rc), so the Windows box is left to CATS; run the command on the Mac." >&2
  exit 3
fi

# The commit to run: the branch's (or REF's), which origin must have.
if [[ -z "$ref" ]]; then
  ref="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
  [[ "$ref" != HEAD ]] || ref="$(git -C "$ROOT" rev-parse HEAD)"
fi
sha="$(git -C "$ROOT" rev-parse --verify "$ref^{commit}")" || { echo "win_run.sh: unknown ref $ref" >&2; exit 2; }
if ! git -C "$ROOT" fetch -q origin; then
  echo "win_run.sh: could not fetch origin from the Mac; run the command on the Mac." >&2
  exit 3
fi
if ! git -C "$ROOT" branch -r --contains "$sha" | grep -q .; then
  echo "win_run.sh: $ref ($sha) is not on origin; push it first (git push -u origin HEAD)." >&2
  exit 2
fi
if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]]; then
  echo "win_run.sh: note: uncommitted changes here are not sent; the run uses $sha." >&2
fi
else
  sha="$(git -C "$ROOT" rev-parse HEAD)"
fi

cmd="$(printf '%q ' "$@")"
run_id="$(date +%Y%m%d-%H%M%S)-$$"
# Concurrent runs allowed on the Windows box (WIN_RUN_SLOTS, default 2); each gets nproc/slots check.sh jobs.
slots="${WIN_RUN_SLOTS:-2}"
[[ "$slots" =~ ^[1-9][0-9]*$ ]] || { echo "win_run.sh: WIN_RUN_SLOTS must be a whole number above 0, got $slots" >&2; exit 2; }

# The remote script goes over stdin to bash inside WSL, so no quoting passes through Windows' shell; the command
# itself reads /dev/null, or it would eat the rest of the script. Exit codes: a setup failure there is 3 (use the
# Mac); the command's own 3 or 255 becomes 1, so 3 and 255 always mean the box, never the command.
remote_script() {
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
# --- slots (tests run this block alone)
# At most $slots runs at once, each with its share of the CPUs: more runs only slow each other down (2026-11-21:
# four checks at once each took three times as long). A run waits here for a free slot; the slot is held on fd 9
# until the command ends.
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

if [[ $print_script -eq 1 ]]; then remote_script; exit 0; fi
set +e
remote_script | ssh -o ConnectTimeout=8 -o LogLevel=ERROR -p "$PORT" "$WIN" "wsl.exe -d $DISTRO -- bash -s"
rc=$?
set -e
if [[ $rc -eq 255 ]]; then
  echo "win_run.sh: could not reach $WIN; run the command on the Mac." >&2
  exit 3
fi
exit $rc
