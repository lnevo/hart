#!/usr/bin/env bash
# The unpulled-Store test, sourced by sync_hart_package.sh and redeploy_commit.sh (ADR-014 item 5).
#
# profile_tables_unpulled SRC DIR succeeds when DIR/tables.xml changed since the last deploy
# wrote DIR/.tables_deployed.sha256 (a PanelPro Store) and installing SRC would replace it.
# HART_OVERWRITE_PROFILE_TABLES=1 makes it fail, so the install goes ahead.
profile_tables_unpulled() {
  local src="$1" dest="$2/tables.xml" stamp="$2/.tables_deployed.sha256"
  [[ "${HART_OVERWRITE_PROFILE_TABLES:-0}" != "1" && -f "$dest" && -f "$stamp" ]] || return 1
  [[ "$(shasum -a 256 "$dest" | cut -d' ' -f1)" != "$(cat "$stamp")" ]] || return 1
  ! cmp -s "$src" "$dest"
}
