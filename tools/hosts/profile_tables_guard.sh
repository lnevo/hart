#!/usr/bin/env bash
# The profile guards, sourced by the deploy scripts, launch_cats.sh and the PanelPro wrappers: the
# unpulled-Store test (ADR-014 item 5), the HART_TABLES refusal and the unrestored-profile refusal.
#
# profile_tables_unpulled SRC DIR succeeds when DIR/tables.xml changed since the last deploy
# wrote DIR/.tables_deployed.sha256 (a PanelPro Store) and installing SRC would replace it.
# HART_OVERWRITE_PROFILE_TABLES=1 makes it fail, so the install goes ahead.
# With no stamp at all, a file that differs from SRC counts too (ADR-029: it may hold an owner's Store).
# A Store already split into the sources of the checkout this file is in (hart_split_shas) is taken, so it never
# counts.
_HART_GUARD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
profile_tables_unpulled() {
  local src="$1" dest="$2/tables.xml" stamp="$2/.tables_deployed.sha256" have
  [[ "${HART_OVERWRITE_PROFILE_TABLES:-0}" != "1" && -f "$dest" ]] || return 1
  have="$(shasum -a 256 "$dest" | cut -d' ' -f1)"
  if [[ -f "$stamp" ]]; then
    [[ "$have" != "$(cat "$stamp")" ]] || return 1
  fi
  ! grep -qxF "$have" <<<"$(hart_split_shas "$_HART_GUARD_ROOT")" || return 1
  ! cmp -s "$src" "$dest"
}

# hart_split_shas ROOT prints the hash of every Store split into ROOT's sources (jmri/layouts/hart/data/
# store_splits.csv, written by tools/schematic/split_store.py), one a line; nothing when there is none. A host
# whose tables.xml has one of them is not holding unpulled edits: they are in the generated tables.xml (R9d).
hart_split_shas() {
  local csv="$1/jmri/layouts/hart/data/store_splits.csv"
  [[ -f "$csv" ]] || return 0
  tail -n +2 "$csv" | cut -d, -f1 | grep -E '^[0-9a-f]{64}$' || true
}

# hart_main_checkout ROOT prints the main checkout of the repo ROOT belongs to: the parent of git's common dir, so a
# worktree answers with the checkout it was made from; ROOT itself where git cannot say (a copied tree, or an answer
# that is not one path). A relative common dir (git before 2.31 has no --path-format, so none is asked for) is read
# against ROOT, where git ran. Mirrors hartlib.paths.main_checkout().
hart_main_checkout() {
  local common
  common="$(git -C "$1" rev-parse --git-common-dir 2>/dev/null)" || { echo "$1"; return; }
  if [[ -z "$common" || "$common" == *$'\n'* ]]; then echo "$1"; return; fi
  [[ "$common" == /* ]] || common="$1/$common"
  common="$(cd "$common" 2>/dev/null && pwd -P)" || { echo "$1"; return; }
  dirname "$common"
}

# hart_cache_dir ROOT NAME prints the shared cache folder NAME: HART_CACHE_DIR/NAME (spaces trimmed, a leading ~
# expanded, as hartlib.paths.cache_dir does), else <main checkout>/.cache/hart/NAME (gitignored), so every worktree
# shares one warm cache.
hart_cache_dir() {
  local base="${HART_CACHE_DIR:-}"
  base="${base#"${base%%[![:space:]]*}"}"
  base="${base%"${base##*[![:space:]]}"}"
  case "$base" in
    "~") base="$HOME" ;;
    "~/"*) base="$HOME/${base#\~/}" ;;
  esac
  [[ -n "$base" ]] || base="$(hart_main_checkout "$1")/.cache/hart"
  echo "$base/$2"
}

# hart_pulled_dir prints the folder PanelPro Stores taken off a host are kept in (make tables-pull, tables-pull-pi,
# run_sml_discover.sh, run_panelpro_roundtrip.sh): HART_PULLED_DIR, else <main checkout>/media/pulled-stores, created
# on demand. Every worktree shares the main checkout's folder, so a worktree swept after its merge never takes the
# owner's only copy with it. Only two places are accepted (exit 1 otherwise): a folder outside every git checkout, or
# one in the MAIN checkout that git ignores (media/ is gitignored, so a Store cannot reach a commit). A folder in a
# linked worktree or any other repo is refused. Mirrors hartlib.paths.pulled_stores_dir().
hart_pulled_dir() {
  local dir="${HART_PULLED_DIR:-}" probe main top root
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  main="$(hart_main_checkout "$root")"
  case "$dir" in "~") dir="$HOME" ;; "~/"*) dir="$HOME/${dir#\~/}" ;; esac
  [[ -n "$dir" ]] || dir="$main/media/pulled-stores"
  probe="$dir"
  while [[ ! -d "$probe" ]]; do probe="$(dirname "$probe")"; done   # checked before anything is made
  if top="$(git -C "$probe" rev-parse --show-toplevel 2>/dev/null)" && [[ -n "$top" ]]; then
    if [[ "$(cd "$top" && pwd -P)" != "$(cd "$main" && pwd -P)" ]]; then
      echo "STOP: $dir is inside the git checkout $top; pulled Stores live in the main checkout's gitignored media/ (HART_PULLED_DIR), never in a worktree a sweep removes" >&2
      return 1
    fi
    if ! git -C "$probe" check-ignore -q "$dir" 2>/dev/null; then
      echo "STOP: $dir is inside the main checkout and not git-ignored; pulled Stores live in its gitignored media/ (HART_PULLED_DIR)" >&2
      return 1
    fi
  fi
  mkdir -p "$dir" || { echo "STOP: cannot make $dir for the pulled Stores" >&2; return 1; }
  (cd "$dir" && pwd)
}

# hart_keep_store FILE DIR HOST BASE keeps a pulled Store in DIR as HOST-<date>.xml with BASE (a tables_base.sh
# line) in HOST-<date>.xml.base, and prints the kept path. A Store whose hash a kept HOST-*.xml already has is kept
# once: that file is printed and its base left as it is (the same Store has the same base), unless the kept base is
# "none" and BASE is not: then BASE, which was not known at the first pull, replaces it.
hart_keep_store() {
  local file="$1" dir="$2" host="$3" base="$4" sha f saved
  sha="$(shasum -a 256 "$file" | cut -d' ' -f1)"
  for f in "$dir/$host"-*.xml; do
    [[ -f "$f" && "$(shasum -a 256 "$f" | cut -d' ' -f1)" == "$sha" ]] || continue
    if [[ ! -f "$f.base" ]] || { [[ "$(<"$f.base")" == none ]] && [[ "$base" != none ]]; }; then
      echo "$base" >"$f.base"
    fi
    echo "$f"
    return 0
  done
  saved="$dir/$host-$(date +%Y%m%d-%H%M%S).xml"
  cp "$file" "$saved"
  [[ "$(shasum -a 256 "$saved" | cut -d' ' -f1)" == "$sha" ]] \
    || { echo "The kept copy $saved does not match what was read; pull again." >&2; rm -f "$saved"; return 1; }
  echo "$base" >"$saved.base"
  echo "$saved"
}

# refuse_hart_tables WHAT exits 1 while HART_TABLES is set. HART_TABLES (hartlib.paths) points the
# table checks at another file; a deploy ships, and PanelPro loads and stores, the checkout's
# tables.xml, and the repairs after it write the file hartlib names, so none of them runs with it.
refuse_hart_tables() {
  if [[ -n "${HART_TABLES:-}" ]]; then
    echo "HART_TABLES is set ($HART_TABLES): it is for checks only; unset it to $1" >&2
    exit 1
  fi
}

# refuse_unrestored_profile WHAT exits 1 while a PanelPro wrapper run's profile backup is left over
# (the run was killed with SIGKILL, tools/hosts/panelpro_session.sh): the live profile.xml may still
# hold that run's Start Up changes, so nothing should start JMRI on it or patch it until it is back.
refuse_unrestored_profile() {
  local profile="${HOME}/Library/Preferences/JMRI/My_JMRI_Railroad.jmri/profile/profile.xml"
  if [[ -e "$profile.hart-run.bak" || -e "$profile.hart-run.sha256" ]]; then
    echo "STOP: $profile.hart-run.bak is left from a PanelPro wrapper run that did not finish; not going to $1." >&2
    echo "Quit the PanelPro it left, then run: python3 $_HART_GUARD_ROOT/tools/hosts/panelpro_profile.py restore --profile $profile" >&2
    exit 1
  fi
}

# hart_plugin_pin_problem ROOT prints why the schematic plugin (external/model-railroad-skills) is not usable as pinned,
# or nothing when it is at the commit ROOT's branch records. A checked-out submodule on another commit (git submodule
# status shows "+") gives builds and tests an older or newer plugin than the branch was written for, and their failures
# look like real bugs (2026-11-21). SCHEMATIC_PLUGIN set means a local plugin on purpose: nothing is printed then.
hart_plugin_pin_problem() {
  local status
  [[ -z "${SCHEMATIC_PLUGIN:-}" ]] || return 0
  status="$(git -C "$1" submodule status -- external/model-railroad-skills 2>/dev/null)" || return 0
  case "$status" in
    +*) echo "external/model-railroad-skills is checked out at ${status:1:8}, not the commit this branch pins; run: git submodule update external/model-railroad-skills (or set SCHEMATIC_PLUGIN to test a local plugin on purpose)" ;;
  esac
}
