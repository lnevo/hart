#!/usr/bin/env bash
# Run before any commit that changes tables or signals. Deploy gates run separately.
# HART_TABLES=<tables file> runs the table checks against that file instead of the checkout's
# own (the Layout Editor cut-over candidate, a sandbox copy; hartlib.paths). The unit tests
# always run against the checkout's own file.
set -uo pipefail
# A relative HART_TABLES is the caller's (read before the cd below), and ~ is expanded as hartlib does.
if [[ -n "${HART_TABLES:-}" ]]; then
  case "$HART_TABLES" in "~"/*) HART_TABLES="$HOME/${HART_TABLES#"~/"}" ;; esac
  [[ -f "$HART_TABLES" ]] || { echo "HART_TABLES=$HART_TABLES: no such file"; exit 1; }
  HART_TABLES="$(cd "$(dirname "$HART_TABLES")" && pwd)/$(basename "$HART_TABLES")"
  export HART_TABLES
  echo "Table checks read $HART_TABLES (HART_TABLES), not the checkout's tables file"
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export JMRI_LAYOUT=hart
# ops/hart-ops/.venv's Python when there is one: it carries pypdf, for the public text check's PDF part.
HOPS_PY=python3
[[ -x ops/hart-ops/.venv/bin/python ]] && HOPS_PY=ops/hart-ops/.venv/bin/python
# Docs-only and light paths, the rule CI uses (tools/ci/changed_kind.py --git: the branch against its merge base with
# origin/main, plus uncommitted and untracked files). Markdown docs only: the quick docs checks (tools/ci/docs_checks.sh).
# Light (docs, or data that only static checks read): tools/ci/light_checks.sh (make static's jobs, the static jobs
# that read the changed files, then the quick docs checks). Neither ends "ALL PASSED": not a pass of check.sh (the
# rule: docs/pipeline-map/checks-and-remote.md, "Docs-only changes" and "Light changes"). CI, FULL=1 and any run that asks for something particular (CHECK_ONLY, CHECK_AUDIT,
# HART_TABLES, PORTAL_CHECK=1, the CI stamp folders) take the normal path, as does one where git cannot say what changed.
DOCS_ONLY=0 LIGHT=0
if [[ -z "${CI:-}" && "${FULL:-}" != 1 && -z "${CHECK_ONLY:-}" && -z "${CHECK_AUDIT:-}" && -z "${HART_TABLES:-}" \
      && "${PORTAL_CHECK:-}" != 1 && -z "${CHECK_RECORD_TO:-}" && -z "${CHECK_SKIP_FROM:-}" \
      && -z "${CHECK_AUDIT_FAILS:-}" ]]; then
  if verdict="$(python3 tools/ci/changed_kind.py --git 2>&1)"; then
    case "$verdict" in
      docs:*) DOCS_ONLY=1
              echo "Docs-only change (${verdict#docs: }): quick docs checks only, no stamps recorded, not a full pass (FULL=1 runs everything)" ;;
      light:*) LIGHT=1
               echo "Light change (${verdict#light: }): the light checks only, not a full pass (FULL=1 runs everything)" ;;
      full:*) echo "Full checks: ${verdict#full: } (tools/ci/changed_kind.py; make pr-kind)" ;;
      unknown:*) echo "Full checks: cannot tell what changed, ${verdict#unknown: }" ;;
      *) echo "Full checks: tools/ci/changed_kind.py --git printed no verdict: $verdict" ;;
    esac
  else
    echo "Full checks: tools/ci/changed_kind.py --git failed: $verdict"
  fi
fi
# The caller's PYTHONPATH, before any job puts a hook on it: a bash check runs with it (run_check).
CALLER_PYTHONPATH=()
if [[ -n "${PYTHONPATH+set}" ]]; then CALLER_PYTHONPATH=(PYTHONPATH="$PYTHONPATH"); else CALLER_PYTHONPATH=(-u PYTHONPATH); fi
# The schematic plugin's cache, the folder the builds use (publish_draft.CACHE: <main checkout>/.cache/hart/schematic,
# private to this user), for every job: the Layout Editor job solves the whole sheet without it (about 3 minutes).
# An empty SCHEMATIC_CACHE (the caller's) keeps it off, as does a folder that cannot be made. CI keeps the folder.
if [[ -z "${SCHEMATIC_CACHE+set}" ]]; then
  source "$ROOT/tools/hosts/profile_tables_guard.sh"
  cache="$(hart_cache_dir "$ROOT" schematic)"
  if mkdir -p "$cache" 2>/dev/null && chmod 700 "$cache"; then
    export SCHEMATIC_CACHE="$cache"
  else
    echo "schematic cache off: cannot make $cache"
  fi
fi
# A worktree not made by make wt (a subagent's isolation worktree, an older one) may lack the submodules the checks
# import (CHECK_SUBMODULES in tools/agent/worktrees.py); check them out the way make wt does. Only in a worktree
# (.git is a file there): the main checkout is not changed, and CI checks them out itself (.github/workflows/check.yml).
if [[ -z "${CI:-}" && -f .git ]]; then
  python3 tools/agent/worktrees.py submodules "$ROOT" || echo "checks that need a missing submodule will fail (SCHEMATIC_REQUIRED=0 lets the schematic ones skip)"
fi
# A plugin on another commit than the branch pins makes checks fail as if the code were wrong: stop before any job.
source "$ROOT/tools/hosts/profile_tables_guard.sh"
pin_problem="$(hart_plugin_pin_problem "$ROOT")"
if [[ -n "$pin_problem" ]]; then
  echo "STOP: $pin_problem" >&2
  exit 2
fi
(( LIGHT )) && { HOPS_PY="$HOPS_PY" bash tools/ci/light_checks.sh --git; exit $?; }
if (( DOCS_ONLY )); then
  HOPS_PY="$HOPS_PY" bash tools/ci/docs_checks.sh && { echo "DOCS CHECKS PASSED (the docs-only path; FULL=1 runs check.sh in full)"; exit 0; }
  echo "FAILED"; exit 1
fi
# A schematic check that cannot load the plugin fails, as in CI: no ALL PASSED without the submodule. SCHEMATIC_REQUIRED=0 skips them.
export SCHEMATIC_REQUIRED="${SCHEMATIC_REQUIRED:-1}"
fail=0
# Local traced stamps (tools/audit/check_stamps.py, traced.py): a job whose recorded reads (files its Python opened,
# probed, listed) match its last pass is skipped ("<job>: current, skipped"); a job running a program the trace cannot
# see falls back to its declared folders. CI (unless CHECK_SKIP_FROM), FULL=1 and an audit run never skip. CHECK_ONLY=
# <regex> runs the jobs whose name matches. CHECK_AUDIT=<folder> logs the repo files each job's Python opens.
# STAMPS: a job may be skipped; RECORD: a passing job records its stamp, read from the trace hook's log of its Python's
# reads (FULL=1 and an audit run record, CI only with CHECK_RECORD_TO).
STAMPS=1
RECORD=1
if [[ -n "${CI:-}" || "${FULL:-}" == 1 || -n "${CHECK_AUDIT:-}" ]]; then STAMPS=0; fi
if [[ -n "${CI:-}" ]]; then RECORD=0; fi
# The checkout's .cache (gitignored) before any job starts: a job may make it (make panels made .cache/panel-stamps
# there), and a job that lists the root and passed before that recorded a listing without it, so the next run reran it.
# Without the folder the run goes on; a job that saw it appear then records nothing and reruns next time.
if ! mkdir -p "$ROOT/.cache" 2>/dev/null; then
  echo "cannot make $ROOT/.cache: a job that lists the root and finishes before a step makes it reruns next time"
fi
# CI only (.github/workflows/check.yml, tools/ci/stamp_gate.py): CHECK_RECORD_TO=<folder> is main's push run, which runs
# every job and records the stamps of the ones that passed there; CHECK_SKIP_FROM=<folder> is a pull request run with
# main's stamps for its merge base, which skips a job whose inputs are byte-identical to that pass and records
# nothing. CHECK_SKIP_NOTE says where the stamps came from in each skipped job's line. FULL=1 and CHECK_AUDIT still
# run everything. Off CI both are refused: the Mac and WSL keep their own stamps (paths differ).
# The folder goes to the stamp helper only (STAMP_ENV), and the three variables are unset here, so a job (a test that
# runs check.sh itself) never inherits them or writes into main's stamps.
SKIP_NOTE="current"
STAMP_ENV=()
STAMP_WHY=()     # a pull request run says why each job that runs did not match main's stamp
if [[ -n "${CHECK_RECORD_TO:-}" || -n "${CHECK_SKIP_FROM:-}" ]]; then
  if [[ -z "${CI:-}" ]]; then echo "CHECK_RECORD_TO and CHECK_SKIP_FROM are for CI runs only" >&2; exit 2; fi
  if [[ -n "${CHECK_RECORD_TO:-}" && -n "${CHECK_SKIP_FROM:-}" ]]; then
    echo "CHECK_RECORD_TO and CHECK_SKIP_FROM together: a run either records or skips" >&2; exit 2
  fi
  if [[ -n "${CHECK_RECORD_TO:-}" ]]; then
    mkdir -p "$CHECK_RECORD_TO" || exit 2
    STAMP_ENV=(CHECK_STAMPS_DIR="$(cd "$CHECK_RECORD_TO" && pwd)")
    RECORD=1
  elif [[ "${FULL:-}" != 1 && -z "${CHECK_AUDIT:-}" ]]; then
    [[ -d "$CHECK_SKIP_FROM" ]] || { echo "CHECK_SKIP_FROM=$CHECK_SKIP_FROM: no such folder" >&2; exit 2; }
    dir="$(cd "$CHECK_SKIP_FROM" && pwd)"
    rm -f "$dir/filehash.json"      # keyed on another checkout's mtimes: hash every file again
    STAMP_ENV=(CHECK_STAMPS_DIR="$dir")
    STAMP_WHY=(--why)
    STAMPS=1
    SKIP_NOTE="${CHECK_SKIP_NOTE:-current on main}"
    echo "A job whose inputs match the stamps in $dir is skipped ($SKIP_NOTE)"
  fi
fi
unset CHECK_RECORD_TO CHECK_SKIP_FROM CHECK_SKIP_NOTE
# CHECK_RESULTS_TO=<file>: once every job is done, "<name><TAB>passed|failed|skipped" per queued job, for
# tools/ci/stamp_gate.py (.github/workflows/check.yml). Emptied here, so a run that stops early leaves it empty (which
# the gate refuses); unset, so a job never inherits it.
RESULTS_TO="${CHECK_RESULTS_TO:-}"
unset CHECK_RESULTS_TO
if [[ -n "$RESULTS_TO" ]] && ! : >"$RESULTS_TO"; then
  echo "CHECK_RESULTS_TO=$RESULTS_TO: cannot write it" >&2
  exit 2
fi
if [[ -n "${CHECK_AUDIT:-}" ]]; then
  mkdir -p "$CHECK_AUDIT"
  CHECK_AUDIT="$(cd "$CHECK_AUDIT" && pwd)"
  # its logs, inside the checkout, would be new files while each job runs: every job would record nothing
  if [[ "$CHECK_AUDIT/" == "$ROOT/"* ]]; then
    echo "CHECK_AUDIT=$CHECK_AUDIT is inside the checkout; give a folder outside it" >&2
    exit 2
  fi
  rm -f "$CHECK_AUDIT"/*.log "$CHECK_AUDIT"/*.name
fi
# The declaration audit (check_stamps.py record, ADR-037 stage 4c): a step-manifest job that read a file its step
# does not declare in tools/pipeline/checks.toml FAILS in an audit run (CHECK_AUDIT) and with CHECK_AUDIT_FAILS=1 (the
# weekly full run, .github/workflows/check.yml); any other run (local, pull request, main's push) warns, so a new
# undeclared read is seen before it blocks anyone. Only a job that records is audited, so such a run must record.
AUDIT_FAILS=()
case "${CHECK_AUDIT_FAILS:-}" in
  "") ;;
  1) AUDIT_FAILS=(--audit-fails) ;;
  *) echo "CHECK_AUDIT_FAILS=$CHECK_AUDIT_FAILS: it is 1 or unset" >&2; exit 2 ;;
esac
[[ -z "${CHECK_AUDIT:-}" ]] || AUDIT_FAILS=(--audit-fails)
unset CHECK_AUDIT_FAILS
if (( ${#AUDIT_FAILS[@]} && ! RECORD )); then
  echo "the declaration audit fails jobs in this run, but it records no stamp (CI without CHECK_RECORD_TO), so no job would be audited" >&2
  exit 2
fi
MANIFEST_JOBS=" "      # the step-manifest jobs' names, each between spaces: an audit run says which it did not audit
# The read-only checks come from the step manifest, tools/pipeline/checks.toml (ADR-037): each step is a job of its
# own, named after it (stage 4b), the "static" group's queued ahead of the unit tests and the steps in no group after
# them. A manifest that does not load, or a list with no check in it, stops the run here, before any job: check.sh
# never passes having run nothing. The panels step is one job per step of tools/pipeline/panels.toml, panels-<step>,
# each running that step's check (stage 6; manifest.py prints their lines). Two conditions stay here, keyed on a
# step's name, so each must be in its list: the panels jobs are queued first, and the portal job runs only where its
# inputs are (below).
manifest_lines() {   # the lines of `manifest.py jobs check <args>` into MANIFEST_LINES; stops the run when there are none
  local out line
  MANIFEST_LINES=()
  if ! out="$(python3 tools/pipeline/manifest.py jobs check "$@")"; then
    echo "STOP: tools/pipeline/manifest.py jobs check $* failed (its error is above); no check ran" >&2
    exit 2
  fi
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    if [[ ! "$line" =~ ^[a-z0-9][a-z0-9-]*\  ]]; then
      echo "STOP: tools/pipeline/manifest.py jobs check $* printed \"$line\", not a step name and its command" >&2
      exit 2
    fi
    # each line is eval'd later; one that will not parse, eval'd in this shell, leaves bash 3.2 unable to read the
    # rest of this file, so it is parsed here in a subshell
    if ! ( eval "set -- $line" ); then
      echo "STOP: tools/pipeline/manifest.py jobs check $* printed a line the shell cannot parse: $line" >&2
      exit 2
    fi
    MANIFEST_LINES+=("$line")
  done <<<"$out"
  if (( ${#MANIFEST_LINES[@]} == 0 )); then
    echo "STOP: tools/pipeline/manifest.py jobs check $* listed no check; no check ran" >&2
    exit 2
  fi
}
has_step() {   # has_step NAME LINE...: whether one of the lines is step NAME's
  local name="$1" line
  shift
  for line in "$@"; do [[ "${line%% *}" == "$name" ]] && return 0; done
  return 1
}
manifest_lines --group static
STATIC_LINES=("${MANIFEST_LINES[@]}")
manifest_lines --ungrouped
OWN_LINES=("${MANIFEST_LINES[@]}")
for line in "${STATIC_LINES[@]}" "${OWN_LINES[@]}"; do MANIFEST_JOBS+="${line%% *} "; done
has_step panels-tables "${STATIC_LINES[@]}" || { echo "STOP: no panels-tables job in tools/pipeline/manifest.py jobs check --group static: the panels step of tools/pipeline/checks.toml lists the steps of tools/pipeline/panels.toml, and the deploy gate reads panels-tables" >&2; exit 2; }
has_step portal "${OWN_LINES[@]}" || { echo "STOP: no portal step in tools/pipeline/checks.toml; check.sh decides when it runs" >&2; exit 2; }
# The jobs run side by side, at most one per core, each in its own temp folders. `later` queues a job; `start_jobs`
# checks every stamp in one process (check_stamps.py current-batch) and starts the jobs that must run, output to files;
# `collect` prints each in queue order under its heading, and a failure sooner (early_failures). set -m gives each job
# its own process group with a terminal's signals, and Ctrl-C or TERM stops every group still running.
set -m
JOBS="$(mktemp -d)"
MAX_JOBS="${CHECK_MAX_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)}"   # win_run.sh sets CHECK_MAX_JOBS to its share of the box
(( MAX_JOBS >= 2 )) || MAX_JOBS=2
names=()
cmds=()          # each queued job's command line, quoted for eval
pids=()          # each job's process, "" for a job that was skipped and never started
verdicts=()      # each job's stamp verdict: 0 current (skip it), 1 run and record its stamp, 2 run and record nothing
stop_jobs() {
  local pid
  for pid in ${pids[@]+"${pids[@]}"}; do [[ -z "$pid" ]] || kill -TERM -- "-$pid" 2>/dev/null; done
}
trap 'rm -rf "$JOBS"' EXIT
trap 'stop_jobs; exit 130' INT
trap 'stop_jobs; exit 143' TERM
later() {
  local name="$1"
  shift
  if [[ -n "${CHECK_ONLY:-}" && ! "$name" =~ $CHECK_ONLY ]]; then return 0; fi
  names+=("$name")
  cmds+=("$(printf '%q ' "$@")")
}
# Every queued job's verdict from one check_stamps.py process (current-batch), which also saves each stampable job's
# snapshot ($JOBS/<n>.stamp, taken before any job starts) and, on a pull request run, why each runs (<n>.stamplog).
# A batch that fails, or answers for other jobs than were queued, makes every job run and record nothing, and says why.
# The batch's files are dropped when its answers are not used: a reason it wrote for one job is not why that job runs.
batch_failed() {
  echo "$1, so every job runs and none records a stamp"
  rm -f "$JOBS"/*.stamp "$JOBS"/*.stamplog
}
read_verdicts() {
  local i v n=0 total="${#names[@]}"
  for (( i = 0; i < total; i++ )); do verdicts[$i]=2; done
  (( STAMPS || RECORD )) || return 0
  (( total > 0 )) || return 0
  printf '%s\n' "${names[@]}" >"$JOBS/names"
  if ! env ${STAMP_ENV[@]+"${STAMP_ENV[@]}"} python3 tools/audit/check_stamps.py current-batch "$JOBS/names" "$JOBS" \
       ${STAMP_WHY[@]+"${STAMP_WHY[@]}"} >"$JOBS/batch.log" 2>&1; then
    batch_failed "stamp check failed ($(tail -n 5 "$JOBS/batch.log"))"
    return 0
  fi
  if [[ ! -f "$JOBS/verdicts" ]]; then
    batch_failed "stamp check wrote no verdicts ($(tail -n 5 "$JOBS/batch.log"))"
    return 0
  fi
  local got=()
  while IFS=$'\t' read -r i v; do
    if [[ ! "$i" =~ ^[0-9]+$ || ! "$v" =~ ^[012]$ ]] || (( i >= total )); then
      batch_failed "stamp check: \"$i	$v\" in its verdicts is no verdict of a queued job"
      for (( i = 0; i < total; i++ )); do verdicts[$i]=2; done
      return 0
    fi
    got[$i]=$v
    n=$((n + 1))
  done <"$JOBS/verdicts"
  if (( n != total || ${#got[@]} != total )); then
    batch_failed "stamp check: verdicts for ${#got[@]} of $total jobs in $n lines"
    return 0
  fi
  for (( i = 0; i < total; i++ )); do verdicts[$i]=${got[$i]}; done
}
# shellcheck disable=SC2120  # its "$@" is each job's own command, set from cmds by eval
start_jobs() {
  read_verdicts
  local n src name
  for n in "${!names[@]}"; do
    name="${names[$n]}"
    src="${verdicts[$n]}"
    # a current verdict without a saved snapshot is run, don't record
    if (( src == 0 )) && [[ ! -s "$JOBS/$n.stamp" ]]; then src=2; fi
    if (( src == 0 && ! STAMPS )); then src=1; fi       # FULL=1 or an audit run: run it, and record
    if (( src == 1 && ! RECORD )); then src=2; fi       # a pull request run on main's stamps: run it, untraced
    if (( src == 0 )); then
      echo "$name: $SKIP_NOTE, skipped" >"$JOBS/$n.log"
      : >"$JOBS/$n.skip"
      pids[$n]=""
      continue
    fi
    while (( $(jobs -rp | wc -l) >= MAX_JOBS )); do early_failures; sleep 0.2; done
    eval "set -- ${cmds[$n]}"
    (
      start=$SECONDS
      pp_set=${PYTHONPATH+1}
      pp=${PYTHONPATH-}
      if [[ -n "${CHECK_AUDIT:-}" ]]; then
        echo "$name" >"$CHECK_AUDIT/$n.name"
        export CHECK_AUDIT_LOG="$CHECK_AUDIT/$n.log" CHECK_AUDIT_ROOT="$ROOT" PYTHONPATH="$ROOT/tools/audit/stamp_audit${PYTHONPATH:+:$PYTHONPATH}"
      fi
      unset HART_TRACE_LOG HART_TRACE_SPAWN HART_TRACE_PATH
      if (( src == 1 )); then
        # the trace this job's stamp is recorded from; the job's own Python process (the check run_check starts) is
        # expected in it ("b" lines), so a process that dropped the hook leaves the trace short and records nothing
        export HART_TRACE_LOG="$JOBS/$n.trace" HART_TRACE_ROOT="$ROOT" PYTHONPATH="$ROOT/tools/audit/trace_hook${PYTHONPATH:+:$PYTHONPATH}"
        : >"$HART_TRACE_LOG"
        [[ "$(type -t "$1")" == function ]] || printf '0\tb\n' >>"$HART_TRACE_LOG"
      fi
      "$@" >"$JOBS/$n.log" 2>&1
      rc=$?
      # A passing job records its stamp, except a check that printed SKIPPED (it did not really run; a unit job's
      # output may quote the word). A unit job whose tests skipped records them: the trace hook logs each skipped
      # test's id and reason, the stamp's key holds them, and the stamp helper refuses when the trace holds fewer
      # skips than the output's skipped=N counts. Any other job whose output shows skipped= records nothing.
      stampable=0
      skip_count=()
      if (( rc == 0 && src == 1 )) && [[ -s "$JOBS/$n.stamp" ]]; then
        if [[ "$name" == unit-* ]]; then
          stampable=1
          skip_count=(--skipped "$(grep -o 'skipped=[0-9]*' "$JOBS/$n.log" | awk -F= '{ s += $2 } END { print s + 0 }')")
        elif ! grep -q "skipped=" "$JOBS/$n.log" && ! grep -q SKIPPED "$JOBS/$n.log"; then
          stampable=1
        fi
      fi
      if (( stampable )); then
        # with the environment the stamp check had (PYTHONPATH is in the key), untraced
        if [[ -n "$pp_set" ]]; then ppenv=(PYTHONPATH="$pp"); else ppenv=(-u PYTHONPATH); fi
        # its exit counts only when the audit fails jobs (AUDIT_FAILS): 0 audited, 3 nothing to audit (bash, a unit
        # job, not stampable now), anything else fails the job (an undeclared read, an audit that could not run);
        # elsewhere the audit only warns and the job's own result stands
        env -u HART_TRACE_LOG -u HART_TRACE_SPAWN -u HART_TRACE_PATH -u CHECK_AUDIT_LOG "${ppenv[@]}" ${STAMP_ENV[@]+"${STAMP_ENV[@]}"} python3 tools/audit/check_stamps.py record "$name" "$JOBS/$n.stamp" --trace "$HART_TRACE_LOG" ${skip_count[@]+"${skip_count[@]}"} ${AUDIT_FAILS[@]+"${AUDIT_FAILS[@]}"} >>"$JOBS/$n.stamplog" 2>&1
        audit_rc=$?
        if (( ${#AUDIT_FAILS[@]} )); then
          if (( audit_rc == 0 )); then
            : >"$JOBS/$n.audited"
          elif (( audit_rc != 3 )); then
            echo "$name: FAILED by the declaration audit above (ADR-037 stage 4c; check_stamps.py record exited $audit_rc)" >>"$JOBS/$n.stamplog"
            rc=1
          fi
        fi
      fi
      if [[ -s "$JOBS/$n.stamplog" ]]; then { echo "--- stamps ($name):"; cat "$JOBS/$n.stamplog"; } >>"$JOBS/$n.log"; fi
      echo "$((SECONDS - start))" >"$JOBS/$n.time"
      echo "$rc" >"$JOBS/$n.rc"   # collect reads this, not wait's status (job_status, below)
      exit "$rc"
    ) &
    pids[$n]=$!
  done
}
# job_status I: whether job I passed. The code the job wrote itself counts first; else wait's own status, unless wait
# answered 127 "pid N is not a child of this shell": bash 3.2 (macOS) can drop a background job from its table
# under load, finished or still running, and then wait returns at once. A job that is still alive then is waited
# for by polling until it writes its code or ends; one that ended without writing a code fails.
job_status() {
  local rc pid="${pids[$1]}" w=0
  wait "$pid" 2>/dev/null || w=$?
  if [[ ! -e "$JOBS/$1.rc" ]]; then
    (( w != 127 )) && return "$w"
    while [[ ! -e "$JOBS/$1.rc" ]] && kill -0 "$pid" 2>/dev/null; do sleep 0.2; done
  fi
  rc="$(cat "$JOBS/$1.rc" 2>/dev/null)" || return 1
  [[ "$rc" == 0 ]]
}
# A failed job queued after the one collect waits for (COLLECTED) is printed as soon as it ends, between EARLY FAILURE
# lines no parser takes for a heading (win_run.sh, deploy/ci_pass.py), and again in its place. bash 3.2 has no wait -n.
COLLECTED=-1 reported=()      # reported: each finished job's code, once early_failures has read it
early_failures() {
  local j rc
  for j in "${!pids[@]}"; do
    rc=; (( j > COLLECTED )) && [[ -n "${pids[$j]}" && -z "${reported[$j]:-}" ]] && { read -r rc <"$JOBS/$j.rc"; } 2>/dev/null; [[ -n "$rc" ]] || continue
    reported[$j]=$rc
    [[ "$rc" == 0 ]] || { echo "EARLY FAILURE: ${names[$j]} FAILED ($(cat "$JOBS/$j.time" 2>/dev/null)s), more jobs still running"
      cat "$JOBS/$j.log"; echo "EARLY FAILURE: end of ${names[$j]}; every job is reported in queue order once all have ended"; }
  done
}
await_job() {   # await_job I: until job I writes its code or is no longer running, printing early failures meanwhile
  while [[ ! -s "$JOBS/$1.rc" && $'\n'"$(jobs -rp)"$'\n' == *$'\n'"${pids[$1]}"$'\n'* ]]; do early_failures; sleep 0.2; done
}
collect() {
  local i took skipped=0 results=()
  for i in "${!names[@]}"; do
    COLLECTED=$i
    [[ -e "$JOBS/$i.skip" ]] || await_job "$i"
    if [[ -e "$JOBS/$i.skip" ]]; then
      skipped=$((skipped + 1))
      results+=("${names[$i]}"$'\tskipped')
    elif job_status "$i"; then
      echo "--- ${names[$i]} ($(cat "$JOBS/$i.time")s)"
      results+=("${names[$i]}"$'\tpassed')
    else
      fail=1
      took="$(cat "$JOBS/$i.time" 2>/dev/null)" || took="killed before it finished, no "
      echo "--- ${names[$i]} FAILED (${took}s)"
      results+=("${names[$i]}"$'\tfailed')
    fi
    cat "$JOBS/$i.log"
  done
  # no job queued: the file stays empty (printf with no line would still write a newline), which the gate refuses
  if [[ -n "$RESULTS_TO" ]] && (( ${#results[@]} > 0 )) && ! printf '%s\n' "${results[@]}" >"$RESULTS_TO"; then
    echo "CHECK_RESULTS_TO=$RESULTS_TO: cannot write the jobs' results"
    fail=1
  fi
  # A job that printed SKIPPED did not really check (a unit job's output may quote the word, as for the stamps above).
  local i2 said=()
  for i2 in "${!names[@]}"; do
    [[ "${names[$i2]}" == unit-* || -e "$JOBS/$i2.skip" ]] && continue
    grep -q SKIPPED "$JOBS/$i2.log" 2>/dev/null && said+=("${names[$i2]}")
  done
  if (( ${#said[@]} > 0 )); then
    echo "${#said[@]} job(s) printed SKIPPED and checked only part of their inputs: ${said[*]}"
  fi
  # A run whose audit fails jobs names the step-manifest jobs that passed unaudited (bash, or not traced: SKIPPED in
  # their output, not stampable now, a failed stamp batch), and fails when it audited none of them.
  if (( ${#AUDIT_FAILS[@]} )); then
    local i3 audited=0 passed=0 unaudited=()
    for i3 in "${!names[@]}"; do
      [[ "$MANIFEST_JOBS" == *" ${names[$i3]} "* && "${results[$i3]}" == *$'\tpassed' ]] || continue
      passed=$((passed + 1))
      if [[ -e "$JOBS/$i3.audited" ]]; then audited=$((audited + 1)); else unaudited+=("${names[$i3]}"); fi
    done
    if (( ${#unaudited[@]} > 0 )); then
      echo "declaration audit: ${#unaudited[@]} of $passed passing step-manifest job(s) not audited (bash, or not traced): ${unaudited[*]}"
    fi
    if (( passed > 0 && audited == 0 )); then
      echo "declaration audit: no step-manifest job was audited, so this run does not show the declarations hold"
      fail=1
    fi
  fi
  if (( skipped > 0 )); then
    if [[ "$SKIP_NOTE" == current ]]; then
      echo "$skipped of ${#names[@]} jobs current, skipped (FULL=1 runs them all)"
    else
      echo "$skipped of ${#names[@]} jobs $SKIP_NOTE, skipped; $((${#names[@]} - skipped)) ran (the full-ci label runs them all)"
    fi
  fi
}
# Unit tests compare fixtures with the checkout's tables file, so HART_TABLES never reaches them.
unit() {
  local name="$1"
  shift
  later "$name" env -u HART_TABLES "$@"
}
# One step of the manifest as a job: run_line LINE [WORD...] evals the step's line (its name, then its command) inside
# the job, so an env PYTHONPATH=dir word keeps the trace hook start_jobs put on PYTHONPATH, and adds the words. Its
# trace: a Python check (python3, env VAR=... python3) is one Python process it expects ("b"); bash, which the hook
# cannot see into, is a spawn nothing hooked ("x"), so the stamp falls back to its declaration, and runs with the
# caller's PYTHONPATH. Any other program is refused: its reads would be missing.
run_line() {
  local line=$1
  shift
  eval "run_check $line"' ${1+"$@"}'
}
run_check() {
  local name=$1
  shift
  local prog=$1 i
  if [[ "$prog" == env ]]; then
    for (( i = 2; i <= $#; i++ )); do [[ "${!i}" == *=* ]] || { prog="env ${!i}"; break; }; done
  fi
  case "$prog" in
    python3|"env python3")
      [[ -z "${HART_TRACE_LOG:-}" ]] || printf '0\tb\n' >>"$HART_TRACE_LOG"
      "$@" ;;
    bash)
      # and when it starts ("t", from a Python outside the hook): the job's stamp checks no file it hashes changed since
      if [[ -n "${HART_TRACE_LOG:-}" ]]; then
        printf '0\tt\t%s\n' "$(env -u HART_TRACE_LOG -u PYTHONPATH python3 -c 'import time; print(time.time_ns())')" >>"$HART_TRACE_LOG"
        printf '0\tx\tcheck.sh-run\t%s\t%s\n' "$ROOT" "$(IFS=$'\t'; echo "$*")" >>"$HART_TRACE_LOG"
      fi
      env -u HART_TRACE_LOG -u HART_TRACE_SPAWN -u HART_TRACE_ROOT -u CHECK_AUDIT_LOG ${CALLER_PYTHONPATH[@]+"${CALLER_PYTHONPATH[@]}"} "$@" ;;
    *) echo "$name: check.sh's run_check takes python3, env VAR=... python3 or bash, not $prog; not run"; return 1 ;;
  esac
}
# The read-only checks: the panels jobs first, panels-schematic and panels-cats (the slowest) ahead of the rest,
# then the others after the Layout Editor job below.
for pass in slow rest; do
  for line in "${STATIC_LINES[@]}"; do
    case "${line%% *}" in
      panels-schematic|panels-cats) [[ $pass == slow ]] || continue ;;
      panels-*) [[ $pass == rest ]] || continue ;;
      *) continue ;;
    esac
    later "${line%% *}" run_line "$line"
  done
done
# The longest jobs start first, so none of them waits behind the quick ones: the Layout Editor job, unit-jmri, then
# the per-file guard and host jobs, with the files in SLOW of each folder (each 10-20 s) ahead of the rest.
SLOW=" test_worktrees.py test_panelpro_wrappers.py test_deploy_stage.py test_deploy_gates.py test_deploy_preflight.py "
SLOW+="test_redeploy_commit.py "
SLOW+="test_main_panel_names_copies.py test_polish_hart_layout_editor.py "
# The Layout Editor test files run as one job in one process: each builds the three-level candidate through
# test_build_layout_le.built(), cached per process, so three jobs solved the sheet three times side by side with an
# empty schematic cache (about 5 minutes each).
LE_TESTS="test_build_layout_le test_le_cutover test_le_mast_parity"
SLOW+=" test_panel_stamps.py test_build_tables.py test_build_panels.py "
slow_first() {
  local f
  for f in "$@"; do [[ "$SLOW" == *" ${f##*/} "* ]] && echo "$f"; done
  for f in "$@"; do [[ "$SLOW" == *" ${f##*/} "* ]] || echo "$f"; done
  return 0
}
# PYTHONPATH is extended inside the job, where the trace hook is already on it (bash execs python: one process)
# shellcheck disable=SC2016  # expanded by the inner bash
unit "unit-guards layout-editor ($LE_TESTS)" bash -c 'PYTHONPATH="tools/audit/tests${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m unittest -b -q '"$LE_TESTS"
for line in "${STATIC_LINES[@]}"; do
  [[ "${line%% *}" == panels-* ]] && continue
  later "${line%% *}" run_line "$line"
done
# unit-jmri runs one job per file on a local run, the slow files first (25 s in one job, 16 s over six cores). CI keeps
# one job: its four cores are full for minutes, so a split would only add some 50 interpreter starts.
JMRI_TESTS=jmri/layouts/hart/scripts/tests
if [[ -n "${CI:-}" ]]; then
  unit unit-jmri python3 -m unittest discover -b -q -s jmri/layouts/hart/scripts/tests
else
  for t in $(slow_first "$JMRI_TESTS"/test*.py); do
    f="$(basename "$t")"
    unit "unit-jmri ${f%.py}" python3 -m unittest discover -b -q -s "$JMRI_TESTS" -p "$f"
  done
fi
# The host, guard and schematic tests run one job per file, found as discover finds them, the files in SLOW first. A
# file in BY_CLASS runs one job per test class instead (test_worktrees: about 40 tests of git calls; the deploy tests).
for d in "$JMRI_TESTS" tools/hosts/tests tools/audit/tests tools/schematic/tests; do
  if [[ -n "$(find "$d" -mindepth 2 -name 'test*.py' -print -quit)" ]]; then
    echo "--- $d: tests in a subfolder; give them their own job in check.sh"
    fail=1
  fi
done
BY_CLASS=" test_worktrees.py "
BY_CLASS+=" test_panel_stamps.py "      # in tools/schematic/tests
# in tools/hosts/tests: the deploy scripts in scratch repos took 456 s and 274 s per file, 94 s at most per class side
# by side. CI keeps one job per file, as for unit-jmri: its cores are full, and these tests wait on timeouts.
[[ -n "${CI:-}" ]] || BY_CLASS+=" test_deploy_gates.py test_deploy_preflight.py "
# A class in BY_METHOD runs one job per test (test_panel_stamps.ShellTest: eight runs of build_panels.sh in scratch repos).
BY_METHOD=" test_panel_stamps.ShellTest "
for t in $(slow_first tools/hosts/tests/test*.py tools/audit/tests/test*.py tools/schematic/tests/test*.py); do
  d="$(dirname "$t")"
  f="$(basename "$t")"
  [[ "$d" == tools/audit/tests && " $LE_TESTS " == *" ${f%.py} "* ]] && continue    # in the Layout Editor job above
  kind=unit-guards
  [[ "$d" == tools/hosts/tests ]] && kind=unit-hosts
  [[ "$d" == tools/schematic/tests ]] && kind=unit-schematic
  if [[ "$BY_CLASS" == *" $f "* ]]; then
    classes="$(python3 tools/audit/test_classes.py "$t")" || { echo "--- $kind ${f%.py}: cannot list its test classes"; fail=1; continue; }
    for c in $classes; do
      if [[ "$BY_METHOD" == *" $c "* ]]; then
        for m in $(python3 tools/audit/test_classes.py "$t" --methods "$c"); do
          unit "$kind $m" python3 -m unittest discover -b -q -s "$d" -p "$f" -k "$m"
        done
      else
        unit "$kind $c" python3 -m unittest discover -b -q -s "$d" -p "$f" -k "$c."
      fi
    done
  else
    unit "$kind ${f%.py}" python3 -m unittest discover -b -q -s "$d" -p "$f"
  fi
done
unit unit-jmri-scripts python3 -m unittest discover -b -q -s jmri/scripts/tests
unit unit-cats python3 -m unittest discover -b -q -s cats/scripts/tests
unit unit-mimic python3 -m unittest discover -b -q -s tools/mqtt-mimic/tests
unit unit-hartlib python3 -m unittest discover -b -q -s tools/hartlib/tests
unit unit-anyrail python3 -m unittest discover -b -q -s tools/anyrail/tests
unit unit-portal python3 -m unittest discover -b -q -s www/scripts/tests
# Car cards, intake and publications. Uses ops/hart-ops/.venv when it exists; a checkout
# without it (a worktree) skips, CI installs ops/hart-ops/requirements-test.txt.
if [[ -n "${CI:-}" ]] || "$HOPS_PY" -c "import numpy, scipy, docx, pytesseract" 2>/dev/null; then
  unit unit-hart-ops "$HOPS_PY" -m unittest discover -b -q -s ops/hart-ops/tests
else
  later "unit-hart-ops skipped (no ops/hart-ops/.venv)" true
fi
# The portal build needs the gitignored photo mirrors (media/), which CI does not have. It is skipped only when
# tools/audit/portal_inputs.py exits 3 (this checkout changes no site input); a crash there runs it, and
# PORTAL_CHECK=1 runs it anyway. The website deploy always runs it, with its count comparison.
portal_why=""
if [[ -z "${CI:-}" && "${PORTAL_CHECK:-}" != 1 ]]; then
  portal_why="$(python3 tools/audit/portal_inputs.py)"
  portal_rc=$?
fi
# The manifest's steps in no group (public-text, ruff, portal): each a job of its own. public-text runs on HOPS_PY
# (set at the top; it carries pypdf for the PDF part), which its line names as "$HOPS_PY".
for line in "${OWN_LINES[@]}"; do
  if [[ "${line%% *}" != portal ]]; then
    eval "later $line"
  elif [[ -n "${CI:-}" ]]; then
    later "portal skipped in CI" true
  elif [[ "${PORTAL_CHECK:-}" != 1 && "$portal_rc" -eq 3 ]]; then
    later "portal skipped: $portal_why (PORTAL_CHECK=1 runs it)" true
  else
    eval "later $line"
  fi
done
if (( ${#names[@]} == 0 )); then
  echo "--- no job to run${CHECK_ONLY:+: CHECK_ONLY=$CHECK_ONLY matches none}"
  fail=1
fi
start_jobs
collect
# Each step-manifest job's run goes to the local timings log (tools/pipeline/step_timings.sh; make timings), not from CI or an audit run;
# a helper that fails leaves one line in step-timings.err beside the log, and the run is unchanged.
[[ -n "${CI:-}${CHECK_AUDIT:-}" ]] || { if source tools/pipeline/step_timings.sh; then step_timings_jobs "$ROOT" "$JOBS" "$MANIFEST_JOBS" ${names[@]+"${names[@]}"}
  else printf '%s\tcheck\tsource tools/pipeline/step_timings.sh failed\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$(hart_cache_dir "$ROOT" step-timings.err)"; fi; } 2>/dev/null
if [[ "$fail" -eq 0 ]]; then echo "${CHECK_PASS_LINE:-ALL PASSED}"; else echo "FAILED"; fi
exit "$fail"
