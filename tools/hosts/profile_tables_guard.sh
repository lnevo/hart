#!/usr/bin/env bash
# The profile guards, sourced by the deploy scripts, launch_cats.sh and the PanelPro wrappers: the
# unpulled-Store test (ADR-014 item 5), the HART_TABLES refusal and the unrestored-profile refusal.
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
    echo "Quit the PanelPro it left, then run: python3 $ROOT/tools/hosts/panelpro_profile.py restore --profile $profile" >&2
    exit 1
  fi
}
