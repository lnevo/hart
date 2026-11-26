#!/usr/bin/env bash
# The deploy gate's own pulls (sourced by common.sh, never run): when check_pi_unpulled finds Pi changes a deploy would
# replace, autopull_pi_changes saves them with the scripts a person runs, then stops the deploy. Split from common.sh
# (2026-11-26, lane N8) when the roster pull joined the Operations pull, to keep common.sh under its size limit.
# It uses common.sh's ROOT and pi_stop.

# reusable_ops_pull_worktree REPO WTDIR: the newest ops-pull-* worktree that REPO lists (git worktree list), directly
# under WTDIR, whose branch is not yet merged into origin/main (an earlier auto-pull waiting for its merge). Prints its
# path, or nothing: a plain folder of that name, a merged one, or an unreadable origin/main is not reused.
reusable_ops_pull_worktree() {
  local repo="$1" dir path="" branch line best="" base want
  dir="$(cd "$2" 2>/dev/null && pwd -P)" || return 0
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) path="${line#worktree }"; branch="" ;;
      "branch "*)
        branch="${line#branch }"
        base="$(basename "$path")"
        want="$(cd "$(dirname "$path")" 2>/dev/null && pwd -P)" || continue
        [[ "$want" == "$dir" && "$base" == ops-pull-* && -d "$path" ]] || continue
        # rc 1 is "not an ancestor", i.e. not merged; any other failure (no origin/main) is not a reason to reuse
        git -C "$repo" merge-base --is-ancestor "$branch" refs/remotes/origin/main >/dev/null 2>&1 && continue
        [[ "$?" -eq 1 ]] || continue
        best="$path" ;;   # the list is in creation order; the last match is the newest
    esac
  done < <(git -C "$repo" worktree list --porcelain 2>/dev/null)
  [[ -z "$best" ]] || echo "$best"
}

# autopull_pi_changes UNPULLED: save what check_pi_unpulled found, then stop (T9a). The same scripts a person runs:
# tools/ops/pull_tables_pi.sh keeps a Store in the pulled folder with its base (PanelPro may stay up for it);
# tools/ops/pull_ops.sh --no-mark writes the Operations files into the checkout it runs from and leaves the Pi
# unmarked, so the session counts as pulled only once the repo holds it (check_pi_unpulled compares the Pi's files
# with this checkout's; a deploy before the merge stops again); tools/ops/pull_roster.sh does the same for the
# DecoderPro roster (it never writes on the Pi). From the main checkout (which stays clean for deploys) both run in
# one worktree: an existing ops-pull-* one is reused, else a new one (make wt TOPIC=ops-pull-<stamp>).
# The Operations pull needs JMRI closed: PanelPro is quit first with pi_quit_panelpro.sh --for-deploy, and pi_stop's
# restart brings it back; the roster pull reads with JMRI up. The operating flag's hook has already refused anything
# that reaches the Pi while it is set.
# A pull failure stops saying so and what was and was not kept. Test hooks (the scripts are stubbed in tests):
# HART_AUTOPULL_QUIT, HART_AUTOPULL_TABLES, HART_AUTOPULL_OPS, HART_AUTOPULL_ROSTER (script), HART_AUTOPULL_NEWWT
# (prints the new worktree's path), HART_AUTOPULL_RMWT (removes it: path, topic), HART_AUTOPULL_WT_DIR (where
# ops-pull-* live), HART_AUTOPULL_FROM_MAIN (1/0).
AUTOPULL_TARGET=""   # the checkout the Operations and roster pulls write into, once autopull_target chose it
AUTOPULL_TOPIC=""    # the new worktree's topic, when autopull_target made one

# autopull_target WHAT: sets AUTOPULL_TARGET (this checkout, a reused ops-pull-* worktree, or a new one), once per
# run. Returns 1, with the reason added to autopull_pi_changes' failed, when the worktree cannot be made.
autopull_target() {
  local what="$1" from_main wtdir existing topic target rc=0
  [[ -z "$AUTOPULL_TARGET" ]] || return 0
  from_main="${HART_AUTOPULL_FROM_MAIN:-}"
  if [[ -z "$from_main" ]]; then
    if [[ "$(git -C "$ROOT" rev-parse --git-dir 2>/dev/null)" == "$(git -C "$ROOT" rev-parse --git-common-dir 2>/dev/null)" ]]; then from_main=1; else from_main=0; fi
  fi
  if [[ "$from_main" != "1" ]]; then
    AUTOPULL_TARGET="$ROOT"
    return 0
  fi
  wtdir="${HART_AUTOPULL_WT_DIR:-$ROOT/.claude/worktrees}"
  existing="$(reusable_ops_pull_worktree "${HART_AUTOPULL_WT_REPO:-$ROOT}" "$wtdir")"
  if [[ -n "$existing" && -d "$existing" ]]; then
    AUTOPULL_TARGET="$existing"   # an earlier auto-pull not merged yet
    return 0
  fi
  topic="ops-pull-$(date +%Y%m%d-%H%M%S)"
  if [[ -n "${HART_AUTOPULL_NEWWT:-}" ]]; then
    target="$(bash "$HART_AUTOPULL_NEWWT" "$topic")" || rc=1
  else
    target="$(python3 "$ROOT/tools/agent/worktrees.py" new "$topic")" || rc=1
  fi
  if [[ "$rc" -ne 0 || ! -d "$target" ]]; then
    failed+="could not make the worktree $topic for the $what pull; nothing was kept for the $what files"$'\n'
    return 1
  fi
  AUTOPULL_TARGET="$target"
  AUTOPULL_TOPIC="$topic"
}

# autopull_drop_new_worktree FOLDER: after a failed pull into AUTOPULL_TARGET, the worktree this run made is removed,
# unless the other pull already wrote into it (kept names it). Appends what happened to failed.
autopull_drop_new_worktree() {
  local target="$AUTOPULL_TARGET" topic="$AUTOPULL_TOPIC"
  if [[ -z "$topic" ]]; then
    [[ "$target" != "$ROOT" ]] || failed+=" (check git status in $1)"
    return 0
  fi
  if [[ "$kept" == *" into $target/"* ]]; then
    failed+="; the new worktree $target keeps the other pull"
    return 0
  fi
  if [[ -n "${HART_AUTOPULL_RMWT:-}" ]]; then
    bash "$HART_AUTOPULL_RMWT" "$target" "$topic" && failed+="; the new worktree $target was removed" || failed+="; the new worktree $target was left (remove it)"
  elif git -C "$ROOT" worktree remove --force "$target" >/dev/null 2>&1; then
    git -C "$ROOT" branch -D "agent/claude/$topic" >/dev/null 2>&1 || true
    failed+="; the new worktree $target was removed"
  else
    failed+="; the new worktree $target was left (remove it)"
  fi
  AUTOPULL_TARGET=""
  AUTOPULL_TOPIC=""
}

autopull_pi_changes() {
  local unpulled="$1" out saved kept="" failed="" rc
  echo "The Pi has changes that a deploy would replace; saving them first (HART_NO_AUTOPULL=1 only stops)."
  if grep -qx tables <<<"$unpulled"; then
    if out="$(bash "${HART_AUTOPULL_TABLES:-$ROOT/tools/ops/pull_tables_pi.sh}" 2>&1)"; then
      echo "$out"
      saved="$(sed -n "s/^Pulled: the Pi.s Store is kept as \(.*\) (outside every checkout).*/\1/p" <<<"$out" | head -1)"
      if [[ -n "$saved" ]]; then
        kept+="kept the Pi's Store as $saved; split it (python3 tools/schematic/split_store.py $saved), merge, then deploy"$'\n'
      else
        failed+="the Store pull kept nothing (see above); nothing was kept for the Store"$'\n'
      fi
    else
      echo "$out" >&2
      failed+="the pull of the Pi's Store failed; nothing was kept for it"$'\n'
    fi
  fi
  if grep -qx ops <<<"$unpulled"; then
    if ! bash "${HART_AUTOPULL_QUIT:-$ROOT/tools/hosts/pi_quit_panelpro.sh}" --for-deploy; then
      failed+="could not quit PanelPro on the Pi (tools/hosts/pi_quit_panelpro.sh --for-deploy), so the Operations pull failed and nothing was kept for the Operations files"$'\n'
    elif autopull_target Operations; then
      if out="$(cd "$AUTOPULL_TARGET" && bash "${HART_AUTOPULL_OPS:-$AUTOPULL_TARGET/tools/ops/pull_ops.sh}" --no-mark 2>&1)"; then
        echo "$out"
        kept+="brought the Pi's Operations session into $AUTOPULL_TARGET/jmri/layouts/hart/operations; review, commit and merge it, then deploy from the updated main (the Pi counts as pulled only once the repo holds these files)"$'\n'
      else
        echo "$out" >&2
        failed+="the pull of the Pi's Operations files failed (see above); nothing was kept for them"
        autopull_drop_new_worktree jmri/layouts/hart/operations
        failed+=$'\n'
      fi
    fi
  fi
  if grep -qx roster <<<"$unpulled"; then
    # a reused ops-pull-* worktree from before the roster master has no pull_roster.sh: say so, not "exit 127"
    if ! autopull_target roster; then
      :   # autopull_target said why in failed
    elif [[ -z "${HART_AUTOPULL_ROSTER:-}" && ! -f "$AUTOPULL_TARGET/tools/ops/pull_roster.sh" ]]; then
      failed+="the worktree $AUTOPULL_TARGET is from before the roster pull (no tools/ops/pull_roster.sh); nothing was kept for the DecoderPro roster: merge main into it or remove it, then deploy"$'\n'
    else
      rc=0
      out="$(cd "$AUTOPULL_TARGET" && HART_AUTOPULL_FROM_MAIN=0 bash "${HART_AUTOPULL_ROSTER:-$AUTOPULL_TARGET/tools/ops/pull_roster.sh}" 2>&1)" || rc=$?
      if [[ "$rc" -eq 0 || "$rc" -eq 3 ]]; then
        echo "$out"
        kept+="brought the Pi's DecoderPro roster into $AUTOPULL_TARGET/jmri/layouts/hart/roster; review, commit and merge it, then deploy from the updated main (the Pi counts as pulled only once the repo holds it)"$'\n'
        # 3: pulled, but tools/ops/check_roster.py found a problem (a new loco locos.csv lacks): fix it before the commit
        [[ "$rc" -eq 0 ]] || kept+="the roster pull's check_roster.py found problems (see above): fix locos.csv in $AUTOPULL_TARGET before the commit"$'\n'
      else
        echo "$out" >&2
        failed+="the pull of the Pi's DecoderPro roster failed (see above); nothing was kept for it"
        autopull_drop_new_worktree jmri/layouts/hart/roster
        failed+=$'\n'
      fi
    fi
  fi
  if [[ -n "$failed" ]]; then
    pi_stop "${kept}STOP: the pull failed. ${failed}Nothing was shipped. HART_DISCARD_PI_CHANGES=1 replaces the Pi's files anyway."
  fi
  pi_stop "${kept}STOP: the Pi's changes are saved, not shipped. HART_DISCARD_PI_CHANGES=1 replaces them anyway."
}
