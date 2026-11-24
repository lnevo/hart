#!/usr/bin/env bash
# Deploy step 5: send Windows' package (one tarball, scp) and apply it there (apply_hart_package_local.ps1).
# Every check was made by gate.sh, including that Windows has a temp folder and tar.
#
# Usage: ship_win.sh [--dry-run] STAGED_WIN_DIR     (the win/ folder stage.sh built)
#   --dry-run  builds the tarball and says what it would send: no ssh
# Run alone it repeats the gate's checks for Windows (it answers over ssh, can make a temp folder and has tar); the
# entry point exports HART_GATED=1 once gate.sh has passed in the same run, and they are not asked twice.
# When the Pi already has this deploy (HART_PI_DONE=1, set by sync_hart_package.sh), a failure here says so and
# names the redeploy that brings Windows to the same commit.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
DO_WIN=1
STAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -*) echo "ship_win.sh: unknown option: $1" >&2; exit 1 ;;
    *) [[ -z "$STAGE" ]] || { echo "ship_win.sh: one folder only" >&2; exit 1; }; STAGE="$1" ;;
  esac
  shift
done
[[ -d "$STAGE" ]] || { echo "Usage: ship_win.sh [--dry-run] STAGED_WIN_DIR" >&2; exit 1; }
deploy_facts
refuse_before_changing
# run alone, the gate's origin/main check too (G0b, check_on_main)
if [[ "${HART_GATED:-0}" != 1 && "$DRY_RUN" -eq 0 ]]; then
  check_on_main || exit 1
fi

WIN_TGZ=""      # the Windows tarball
WIN_STEP=1      # 1 until Windows' apply succeeds
WIN_APPLY=0     # 1 once the Windows apply was started
on_exit() {
  [[ -z "$WIN_TGZ" ]] || rm -f "$WIN_TGZ"
  if [[ "$WIN_STEP" -eq 1 && "${HART_PI_DONE:-0}" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
    if [[ "$WIN_APPLY" -eq 1 ]]; then
      echo "The Pi has this deploy (commit ${DEPLOY_COMMIT:0:12}); the Windows apply failed, so Windows may be partly installed." >&2
    else
      echo "The Pi has this deploy (commit ${DEPLOY_COMMIT:0:12}) but Windows does not." >&2
    fi
    echo "Once Windows answers, give it the same commit: make redeploy COMMIT=$DEPLOY_COMMIT HOSTS=--win" >&2
    [[ "$DEPLOY_DIRTY" == no ]] || echo "  (this checkout was dirty: the Pi also got uncommitted files that a redeploy of the commit does not carry)" >&2
  fi
  ssh_mux_close
}
trap on_exit EXIT
ssh_mux_open
if [[ "${HART_GATED:-0}" != 1 && "$DRY_RUN" -eq 0 ]]; then
  preflight_hosts
  check_windows_can_take_package
fi

# The Windows tarball. The name ends in the X's: BSD mktemp (macOS) only fills trailing ones, so a
# template ending in .tgz made the literal name and failed on the next run. on_exit
# removes it on every way out.
push_tar_scp() {
  local stage="$1"
  local tgz
  tgz="$(mktemp "${TMPDIR:-/tmp}/hart-pkg.XXXXXX")"
  WIN_TGZ="$tgz"
  COPYFILE_DISABLE=1 tar -C "$stage" -czf "$tgz" .
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "dry-run: would scp $(du -h "$tgz" | awk '{print $1}') package → ${WIN_HOST}:%TEMP%"
    rm -f "$tgz"
    return 0
  fi
  # Windows OpenSSH is cmd.exe; extract with PowerShell so it is not shell-specific.
  WIN_DROP="$(ssh_win "powershell -NoProfile -Command \"\$d = Join-Path \$env:TEMP ('hart-deploy-' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory \$d | Out-Null; \$d\"" | tr -d '\r' | tail -1)"
  [[ -n "$WIN_DROP" ]] || { echo "Could not create a Windows temp folder" >&2; rm -f "$tgz"; exit 1; }
  scp_win "$tgz" "${WIN_HOST}:${WIN_DROP//\\//}/_pkg.tgz"
  ssh_win "powershell -NoProfile -Command \"Set-Location '${WIN_DROP}'; tar -xzf _pkg.tgz; Remove-Item _pkg.tgz -Force\""
  rm -f "$tgz"
}

echo "Deploy → Windows ($WIN_HOST:$WIN_PORT) via tar..."
push_tar_scp "$STAGE"
if [[ "$DRY_RUN" -eq 0 ]]; then
  rc=0
  WIN_APPLY=1
  ssh_win "powershell -NoProfile -ExecutionPolicy Bypass -File \"${WIN_DROP}\\cats\\scripts\\windows\\apply_hart_package_local.ps1\" -Hart \"${WIN_DROP}\" -OverwriteOps ${HART_OVERWRITE_OPS} -UserFiles \"${WIN_USERFILES}\"" || rc=$?
  # Windows has the deploy once the apply succeeded; a failed folder cleanup below does not change that.
  [[ "$rc" -ne 0 ]] || WIN_STEP=0
  # A leftover temp folder is not a failed deploy: warn, and let the apply's result decide the exit.
  ssh_win "powershell -NoProfile -Command \"Remove-Item -LiteralPath '${WIN_DROP}' -Recurse -Force\"" \
    || echo "WARNING: could not remove ${WIN_DROP} on Windows; delete it by hand." >&2
  [[ "$rc" -eq 0 ]] || exit "$rc"
fi
WIN_STEP=0
echo "Windows deploy done."
