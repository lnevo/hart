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
# the model-railroad-skills submodule checked out, so runs from several agents do not collide.
# --keep leaves that worktree for a look afterwards. Python is ~/hart/.venv (3.13, requirements.txt).
#
# Not for: make panelpro-test, screenshots, deploys, or anything that reads the Mac's
# JMRI_UserFiles. Refuses while the operating flag is set: CATS runs on that box during a session.
# Exit 3 means the box could not be used (flag set, unreachable): run the command on the Mac.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"
WIN="${HART_WIN_SSH:?HART_WIN_SSH is not set}"
PORT="${HART_WIN_SSH_PORT:-2222}"
DISTRO="${HART_WIN_WSL_DISTRO:-Ubuntu-24.04}"

ref="" keep=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) ref="${2:?--ref needs a value}"; shift 2 ;;
    --keep) keep=1; shift ;;
    --) shift; break ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    -*) echo "win_run.sh: unknown option $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
[[ $# -gt 0 ]] || { echo "win_run.sh: no command given (try --help)" >&2; exit 2; }

if "$ROOT/tools/hosts/operating.sh" status >/dev/null 2>&1; then
  echo "win_run.sh: the operating flag is set, so the Windows box is left to CATS; run the command on the Mac." >&2
  exit 3
fi

# The commit to run: the branch's (or REF's), which origin must have.
if [[ -z "$ref" ]]; then
  ref="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
  [[ "$ref" != HEAD ]] || ref="$(git -C "$ROOT" rev-parse HEAD)"
fi
sha="$(git -C "$ROOT" rev-parse --verify "$ref^{commit}")" || { echo "win_run.sh: unknown ref $ref" >&2; exit 2; }
git -C "$ROOT" fetch -q origin
if ! git -C "$ROOT" branch -r --contains "$sha" | grep -q .; then
  echo "win_run.sh: $ref ($sha) is not on origin; push it first (git push -u origin HEAD)." >&2
  exit 2
fi
if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]]; then
  echo "win_run.sh: note: uncommitted changes here are not sent; the run uses $sha." >&2
fi

cmd="$(printf '%q ' "$@")"
run_id="$(date +%Y%m%d-%H%M%S)-$$"

# The remote script goes over stdin to bash inside WSL, so no quoting passes through Windows' shell.
remote_script() {
  cat <<EOF
set -euo pipefail
export PATH="\$HOME/hart/.venv/bin:\$HOME/.local/bin:\$PATH"
main="\$HOME/hart" wt="\$HOME/wt/$run_id"
mkdir -p "\$HOME/wt"
git -C "\$main" fetch -q origin
git -C "\$main" worktree add -q --detach "\$wt" $sha
cleanup() { [[ $keep -eq 1 ]] && echo "win_run.sh: kept \$wt" >&2 || git -C "\$main" worktree remove --force "\$wt"; }
trap cleanup EXIT
# The links must not show as untracked (a dirty tree changes what some tests stage), as in tools/agent/worktrees.py.
exclude="\$(git -C "\$main" rev-parse --git-common-dir)/info/exclude"
for rel in media ops/car-cards ops/hart-ops/.venv; do
  grep -qxF "/\$rel" "\$exclude" 2>/dev/null || echo "/\$rel" >> "\$exclude"
  [[ -e "\$main/\$rel" ]] && ln -sfn "\$main/\$rel" "\$wt/\$rel"
done
git -C "\$wt" submodule update --init -q --reference "\$main/external/model-railroad-skills" external/model-railroad-skills
cd "\$wt"
echo "win_run.sh: $sha on \$(hostname) (WSL, \$(nproc) CPUs): $cmd" >&2
set +e
$cmd
rc=\$?
set -e
exit \$rc
EOF
}

set +e
remote_script | ssh -o ConnectTimeout=8 -o LogLevel=ERROR -p "$PORT" "$WIN" "wsl.exe -d $DISTRO -- bash -s"
rc=$?
set -e
if [[ $rc -eq 255 ]]; then
  echo "win_run.sh: could not reach $WIN; run the command on the Mac." >&2
  exit 3
fi
exit $rc
