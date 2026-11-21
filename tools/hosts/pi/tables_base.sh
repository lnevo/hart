#!/usr/bin/env bash
# Runs on the host a Store is pulled from (the Pi over ssh, the Mac in place). Names what the host's tables.xml was
# before the owner's PanelPro session, so the split (tools/schematic/split_store.py) compares the Store with that
# base. It reads the same two references as unpulled_changes.sh, and the newer counts:
#   deploy SHA COMMIT    what the last deploy shipped (tables_sha256 and commit in cats/deploy_stamp.txt)
#   store SHA            a hash in .tables_deployed.sha256, newer than the stamp and not its hash: a Store an earlier
#                        pull recorded as taken (pulls before R9d did; on the Mac a deploy writes that file too, before
#                        its stamp, with the hash it shipped: that is the deploy)
#   deploy SHA           .tables_deployed.sha256 with no stamp at all: a deploy from before the stamp, commit unknown
#                        (split_store.py still finds a kept Store with that hash, if it was one)
#   none                 neither is there
# The pull writes the line to STORE.base beside the kept Store. Usage: tables_base.sh USERFILES
set -euo pipefail
uf="${1:?usage: tables_base.sh USERFILES}"
stamp="$uf/cats/deploy_stamp.txt" pulled="$uf/.tables_deployed.sha256"
sha="" commit=""
if [[ -f "$stamp" ]]; then
  sha="$(sed -n 's/^tables_sha256=//p' "$stamp")"
  commit="$(sed -n 's/^commit=//p' "$stamp")"
fi
if [[ -f "$pulled" && ! -f "$stamp" ]]; then
  echo "deploy $(cat "$pulled")"
elif [[ -f "$pulled" && "$pulled" -nt "$stamp" && "$(cat "$pulled")" != "$sha" ]]; then
  echo "store $(cat "$pulled")"
elif [[ -n "$sha" && "$sha" != none ]]; then
  echo "deploy $sha${commit:+ $commit}"
else
  echo none
fi
