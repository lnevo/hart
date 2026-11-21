#!/usr/bin/env bash
# Deploy step 1: every check, before anything is sent to a host or installed on this Mac. Run by
# tools/hosts/sync_hart_package.sh; it can run alone to check a deploy that is not yet wanted.
#
# Usage: gate.sh [--pi] [--win] [--mac] [--dry-run] [--check-only] [--stage-only]
#   --pi --win   the hosts the deploy names (checks that need a host only run for those)
#   --mac        the Mac install will follow (its Store check runs)
#   --dry-run    no ssh, no Mac check: the local checks only
#   --check-only the host checks (ssh answers, the Pi's unpulled files) and stop there
#   --stage-only the local checks only, for a staging run (implies --dry-run)
#
# Order (the first failure stops it; nothing has changed on any host or on the Mac):
#   G0  the HART_TABLES and unrestored-profile refusals, the live paths list, the parked features
#   G1  one ssh no-op to each host named
#   G2  the Pi's unpulled files (Operations Pro files, a PanelPro Store)
#   G3  the panel audit          G4  tables.xml is what the generator writes     G5  the Digicon mast check
#   G6  the Mac's own Store check
#   G7  a trial staging into a folder that is thrown away (a real deploy to a host only)
#   G8  Windows can take the package: scp and tar here, a temp folder and tar there (ssh read-only)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
DO_MAC_WEB=0
CHECK_ONLY=0
STAGE_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pi) DO_PI=1 ;;
    --win) DO_WIN=1 ;;
    --mac) DO_MAC_WEB=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --check-only) CHECK_ONLY=1 ;;
    --stage-only) STAGE_ONLY=1; DRY_RUN=1; DO_MAC_WEB=0 ;;
    *) echo "gate.sh: unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

TRIAL=""        # the trial staging folder
RESTART=0       # 1 once a host answered: a PanelPro quit for this deploy comes back if a later check stops the run
on_exit() {
  local rc=$?
  [[ -z "$TRIAL" ]] || rm -rf "$TRIAL"
  if [[ "$RESTART" -eq 1 && "$rc" -ne 0 ]]; then
    RESTART=0
    pi_restart_if_due
  fi
  ssh_mux_close
}
trap on_exit EXIT

# ---- G0: before anything (no ssh) ----
refuse_hart_tables "deploy"
refuse_unrestored_profile "deploy"
load_parked
# The shipped paths are listed in tools/hosts/live_paths.txt (deploy_status.sh counts commits that touch them).
# A run that stages or deploys stops if the list names a path that is gone, so the list cannot drift from the
# checkout; --help, --check-only and --dry-run only read and are not blocked.
if [[ "$CHECK_ONLY" -eq 0 && "$DRY_RUN" -eq 0 || "$STAGE_ONLY" -eq 1 ]]; then
  python3 "$ROOT/tools/hosts/live_paths.py" check || exit 1
fi
deploy_facts
ssh_mux_open

# ---- G1: Windows is kept matching the Pi, and the Pi step runs first. A host that does not answer would
# stop the run after the other host, the Mac or the repo's tables.xml had already changed, so ask every host
# named for one ssh no-op before the checks below. It runs before the Pi's unpulled check, which needs ssh too and
# would name the wrong cause for a Pi that is down. A dry run and --stage-only change nothing on a host and skip it.
preflight_hosts() {
  local down=() pi_up=0 h
  if [[ "$DO_PI" -eq 1 ]]; then
    if ssh_pi true </dev/null >/dev/null; then pi_up=1; else down+=("the Pi ($PI_HOST)"); fi
  fi
  # "exit 0" also runs under cmd.exe, the Windows OpenSSH shell.
  if [[ "$DO_WIN" -eq 1 ]] && ! ssh_win "exit 0" </dev/null >/dev/null; then
    down+=("Windows ($WIN_HOST port $WIN_PORT)")
  fi
  [[ "${#down[@]}" -gt 0 ]] || return 0
  for h in "${down[@]}"; do
    echo "STOP: cannot reach $h over ssh." >&2
  done
  echo "No file was sent to or installed on any host, and the Mac install did not run. Deploy again once every host answers." >&2
  # A PanelPro quit for this deploy comes back, as after any stopped Pi deploy: the one thing done on a host.
  if [[ "$pi_up" -eq 1 ]]; then
    echo "The Pi answered: PanelPro there is started again if it was quit for this deploy (a line below says so)." >&2
    pi_restart_if_due
  fi
  exit 1
}
if [[ "$DRY_RUN" -eq 0 ]]; then
  preflight_hosts
  [[ "$DO_PI" -eq 0 ]] || RESTART=1
fi

# ---- G2: what the owner changed on the Pi since the last deploy or pull would be replaced: Operations
# Pro saves its files as the session runs, and a PanelPro Store rewrites tables.xml. Stop before
# a byte is sent, and bring back a PanelPro quit for this deploy.
# HART_DISCARD_PI_CHANGES=1 replaces them anyway (the owner's call).
pi_stop() {
  echo "$1" >&2
  RESTART=0
  pi_restart_if_due
  exit 1
}
if [[ "$DO_PI" -eq 1 && "$DRY_RUN" -eq 0 && "${HART_DISCARD_PI_CHANGES:-0}" != "1" ]]; then
  # the generated tables.xml is the reference when the Pi has none (no stamp, no pull): a file unlike it may be a Store
  generated_sha="$(shasum -a 256 "$ROOT/jmri/layouts/hart/output/tables.xml" 2>/dev/null | cut -d' ' -f1)"
  split_shas="$(hart_split_shas "$ROOT" | tr '\n' ' ' | sed 's/ *$//')"
  if ! unpulled="$(ssh_pi "bash -s -- '$PI_USERFILES' '$generated_sha'${split_shas:+ $split_shas}" < "$ROOT/tools/hosts/pi/unpulled_changes.sh")"; then
    pi_stop "STOP: could not check the Pi for unpulled changes. HART_DISCARD_PI_CHANGES=1 deploys without the check."
  fi
  if [[ -n "$unpulled" ]]; then
    msg=""
    grep -qx ops <<<"$unpulled" && msg+="STOP: the Pi's Operations Pro files changed since the last deploy or pull. Run make ops-pull and commit first."$'\n'
    grep -qx tables <<<"$unpulled" && msg+="STOP: the Pi's tables.xml changed since the last deploy (a PanelPro Store). Run make tables-pull-pi: it keeps the Store in ~/JMRI_UserFiles-pulled; split it in a task worktree (tools/schematic/split_store.py) and merge that, then deploy (this deploy would replace the Pi's file with the generated tables.xml)."$'\n'
    pi_stop "${msg}HART_DISCARD_PI_CHANGES=1 replaces them anyway."
  fi
fi
if [[ "$CHECK_ONLY" -eq 1 ]]; then
  [[ "$DO_PI" -eq 0 ]] || echo "Pi check: nothing unpulled."
  echo "Host check: every host named answered over ssh."
  RESTART=0
  exit 0
fi

# ---- G3: the panel audit ----
PANEL_AUDIT="$ROOT/jmri/layouts/hart/scripts/audit_panel_contracts.py"
if [[ -n "$TABLES" && -f "$PANEL_AUDIT" ]]; then
  # The audit places masts by the schematic-maps plugin's slot rule (the submodule, or SCHEMATIC_PLUGIN, which
  # redeploy_commit.sh sets). Stop here with the fix rather than fail inside the audit.
  if [[ -z "${SCHEMATIC_PLUGIN:-}" && ! -f "$ROOT/external/model-railroad-skills/plugins/schematic-maps/schematic/slots.py" ]]; then
    echo "the panel audit needs the schematic-maps plugin: run git submodule update --init external/model-railroad-skills, or set SCHEMATIC_PLUGIN" >&2
    exit 1
  fi
  python3 "$PANEL_AUDIT" --strict
fi

# ---- G4: tables.xml is generated (ADR-029, R9c): ship it only when it is what build_tables.py writes from its
# sources, and with the Digicon masts' Signal Mast Logic stored disabled. A redeploy of a commit before R9c has no
# generator.
TABLES_BUILD="$ROOT/tools/schematic/build_tables.py"
if [[ -n "$TABLES" && -f "$TABLES_BUILD" && -n "${HART_REDEPLOY_FROM:-}" ]]; then
  # A redeploy runs this script from an old commit's worktree with the checkout's plugin (redeploy_commit.sh), so
  # a regeneration would draw with another plugin than the commit's and read STALE falsely: the commit's tables.xml
  # was checked when it was committed. The Digicon check below still runs.
  echo "Redeploy of an older commit: not regenerating tables.xml to check it (it was checked when committed); the Digicon check still runs."
elif [[ -n "$TABLES" && -f "$TABLES_BUILD" ]]; then
  tables_rc=0
  SCHEMATIC_REQUIRED=1 python3 "$TABLES_BUILD" --check || tables_rc=$?
  if (( tables_rc == 3 )); then
    echo "STOP: the tables check needs the schematic-maps plugin at its pin: run git submodule update --init external/model-railroad-skills, or set SCHEMATIC_PLUGIN. Nothing was sent to any host." >&2
    exit 1
  elif (( tables_rc == 2 )); then
    echo "STOP: tools/schematic/build_tables.py cannot make tables.xml from its sources: fix the source error above, or rerun discovery (jmri/layouts/hart/scripts/run_sml_discover.sh) when it names the Signal Mast Logic. Nothing was sent to any host." >&2
    exit 1
  elif (( tables_rc != 0 )); then
    echo "STOP: tables.xml is not what tools/schematic/build_tables.py writes from its sources; run make panels (or the script) and commit, then deploy. Nothing was sent to any host." >&2
    exit 1
  fi
fi
# ---- G5 ----
if [[ -n "$TABLES" ]] && ! python3 "$ROOT/jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py" --check --panel "$TABLES"; then
  echo "STOP: a Digicon mast's Signal Mast Logic is stored enabled in tables.xml; run python3 tools/schematic/build_tables.py and commit, then deploy. Nothing was sent to any host." >&2
  exit 1
fi
# The stamp names the tables shipped and whether they differ from the committed file (an uncommitted change).
tables_facts 1

# ---- G6: this Mac's own Store check, before the Mac install changes anything ----
if [[ "$DO_MAC_WEB" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  check_mac_store || exit 1
fi

# ---- G7: the package builds. The trial is staged by stage.sh into a folder that is thrown away. ----
if [[ ( "$DO_PI" -eq 1 || "$DO_WIN" -eq 1 ) && "$DRY_RUN" -eq 0 ]]; then
  TRIAL="$(mktemp -d)"
  trial_flags=()
  [[ "$DO_PI" -eq 0 ]] || trial_flags+=(--pi)
  [[ "$DO_WIN" -eq 0 ]] || trial_flags+=(--win)
  if ! bash "$DEPLOY_STEPS_DIR/stage.sh" "${trial_flags[@]}" "$TRIAL/stage" >/dev/null; then
    echo "STOP: the host package cannot be built (see above). Nothing was sent to any host, and the Mac install did not run." >&2
    exit 1
  fi
  rm -rf "$TRIAL"
  TRIAL=""
fi

# ---- G8: Windows can take the package. The tarball is made here, so tar, scp and a temp file must work; the
# temp folder on Windows and its tar (which unpacks it) are asked for with a folder made and removed again. ----
if [[ "$DO_WIN" -eq 1 ]]; then
  for tool in tar scp; do
    command -v "$tool" >/dev/null 2>&1 || {
      echo "STOP: Windows needs $tool on this Mac to send the package, and it is not on PATH. Nothing was sent to any host." >&2
      exit 1
    }
  done
  tgz_probe="$(mktemp "${TMPDIR:-/tmp}/hart-pkg.XXXXXX")" || {
    echo "STOP: Windows needs a temporary file on this Mac for the package (mktemp failed in ${TMPDIR:-/tmp}). Nothing was sent to any host." >&2
    exit 1
  }
  rm -f "$tgz_probe"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    # Windows OpenSSH is cmd.exe; the probe runs in PowerShell like the real steps.
    if ! ssh_win "powershell -NoProfile -Command \"\$d = Join-Path \$env:TEMP ('hart-probe-' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory \$d | Out-Null; Remove-Item -LiteralPath \$d -Force; if (-not (Get-Command tar -ErrorAction SilentlyContinue)) { exit 1 }\"" </dev/null >/dev/null; then
      echo "STOP: Windows ($WIN_HOST port $WIN_PORT) cannot take the package: it did not give a temp folder, or it has no tar. Nothing was sent to any host, and the Mac install did not run." >&2
      exit 1
    fi
  fi
fi
RESTART=0
exit 0
