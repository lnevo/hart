#!/usr/bin/env bash
# Watches JMRI/JMRI pull request 16004 and issue 16003 from GitHub Actions (.github/workflows/watch-jmri-pr.yml).
# Read-only on JMRI. Anything new since the last report becomes a comment on one tracking issue in this repo that
# mentions the owner, so GitHub's own notifications (mobile app, email) do the alerting.
# Each post carries a hidden marker with the time this run started fetching and the PR head commit; the next run
# reads the newest marker as its cutoff, so a late or skipped scheduled run neither loses nor repeats an event.
# Upstream text and links go inside code spans: no @mention or #ref in them pings anyone, and nothing posted here
# cross-references the JMRI pull request. When the pull request is merged or closed, the job posts once more and
# closes the tracking issue; a closed tracking issue stops the job.
# Needs GH_TOKEN with issues: write on this repo. DRY_RUN=1 prints instead of posting (and opens no issue).
set -euo pipefail

UP=repos/JMRI/JMRI
PR=16004
ISSUE=16003
HERE="${GITHUB_REPOSITORY:-lnevo/hart}"
OWNER_LOGIN=lnevo
TITLE="Watch: JMRI/JMRI PR $PR (MQTT startup race)"
BOT="github-actions[bot]"
now="$(date -u +%FT%TZ)"
marker() { printf '<!-- watch-jmri-pr cutoff=%s head=%s -->' "$1" "$2"; }

# The tracking issue: found by title and author, made on the first run so the cutoff always comes from a marker.
existing="$(gh api "repos/$HERE/issues?state=all&per_page=100" --paginate \
  --jq ".[] | select(.title == \"$TITLE\" and .user.login == \"$BOT\" and (.pull_request | not)) | \"\(.number) \(.state)\"" | head -n1)"
track="" state_here=""
[ -n "$existing" ] && read -r track state_here <<<"$existing"
if [ "$state_here" = closed ]; then
  echo "tracking issue #$track is closed: nothing to watch"
  exit 0
fi

if [ -n "$track" ]; then
  last="$( { gh api "repos/$HERE/issues/$track" --jq '.body // ""'
             gh api "repos/$HERE/issues/$track/comments?per_page=100" --paginate \
               --jq ".[] | select(.user.login == \"$BOT\") | .body"; } \
           | grep -o 'watch-jmri-pr cutoff=[^ ]* head=[^ ]*' | tail -n1 || true)"
  cutoff="$(sed -n 's/.*cutoff=\([^ ]*\).*/\1/p' <<<"$last")"
  last_head="$(sed -n 's/.*head=\([^ ]*\).*/\1/p' <<<"$last")"
fi
cutoff="${cutoff:-${SINCE:-$(date -u -d '-255 min' +%FT%TZ)}}"
last_head="${last_head:-}"
echo "cutoff $cutoff head $last_head"

pr_json="$(gh api "$UP/pulls/$PR")"
head="$(jq -r .head.sha <<<"$pr_json")"
pr_state="$(jq -r .state <<<"$pr_json")"
merged="$(jq -r .merged <<<"$pr_json")"
status="$(jq -r '"STATE \(.state) merged=\(.merged) by=\(.merged_by.login // "-") at=\(.merged_at // "-") labels=\([.labels[].name] | join(",")) head=\(.head.sha[0:8])"' <<<"$pr_json")"

# Code span: no backticks or newlines inside, so the text cannot leave it.
span='(gsub("[`\\s]+"; " ") | "`" + . + "`")'
lines=()
add() { while IFS= read -r l; do [ -n "$l" ] && lines+=("$l"); done; }
if [ -n "$last_head" ] && [ "$last_head" != "$head" ]; then
  lines+=("- NEW head commit \`${last_head:0:8}\` -> \`${head:0:8}\`")
fi
for e in "pulls/$PR/reviews" "pulls/$PR/comments" "issues/$PR/comments" "issues/$ISSUE/comments"; do
  add < <(gh api "$UP/$e?per_page=100" --paginate --jq \
    ".[] | (.submitted_at // .created_at) as \$t | select(\$t > \"$cutoff\" or ((.updated_at // \"\") > \"$cutoff\"))
      | (if \$t > \"$cutoff\" then \"NEW\" else \"EDITED\" end) as \$k
      | \"- \(\$k) \`$e\` \(.user.login | $span) \(\$t) \(.state // \"\"): \((.body // \"\") | .[0:400] | $span) \(.html_url | $span)\"")
done
add < <(gh api "$UP/issues/$PR/events?per_page=100" --paginate --jq \
  ".[] | select(.created_at > \"$cutoff\" and (.event | IN(\"subscribed\", \"unsubscribed\", \"mentioned\") | not))
    | \"- NEW event \(.event) \(.actor.login | $span) \(.created_at)\"")
add < <(gh api "$UP/commits/$head/check-runs?per_page=100" --paginate --jq \
  ".check_runs[] | select(.conclusion != null and .conclusion != \"success\" and .conclusion != \"skipped\"
      and .completed_at > \"$cutoff\" and .name != \"check-pr\" and (.name | test(\"Approved after\") | not))
    | \"- FAIL \(.name | $span) \(.conclusion) \(.completed_at) \(.html_url | $span)\"")

echo "$status"
printf '%s\n' "${lines[@]+"${lines[@]}"}"

if [ -z "$track" ] && [ "${DRY_RUN:-0}" != 1 ]; then
  track="$(gh api "repos/$HERE/issues" -f title="$TITLE" \
    -f body="Comments here come from \`.github/workflows/watch-jmri-pr.yml\` when JMRI/JMRI pull request $PR or issue $ISSUE (\`https://github.com/JMRI/JMRI/pull/$PR\`) changes. @$OWNER_LOGIN
$(marker "$cutoff" "${last_head:-$head}")" --jq .number)"
  echo "opened tracking issue #$track"
fi

if [ "${#lines[@]}" -eq 0 ] && [ "$pr_state" = open ]; then
  echo "nothing new"
  exit 0
fi

body="@$OWNER_LOGIN JMRI/JMRI PR $PR: \`$status\`"$'\n\n'
[ "${#lines[@]}" -gt 0 ] && body+="$(printf '%s\n' "${lines[@]}")"$'\n'
if [ "$pr_state" != open ]; then
  if [ "$merged" = true ]; then
    body+=$'\n'"Merged. Close the topic per [the hand-off](https://github.com/$HERE/blob/main/wiki/projects/mqtt-race-upstream-handoff.md#closing-the-topic) and delete \`.github/workflows/watch-jmri-pr.yml\`. This issue closes now, which stops the watch."
  else
    body+=$'\n'"Closed without merging. This issue closes now, which stops the watch."
  fi
fi
body+=$'\n'"$(marker "$now" "$head")"

if [ "${DRY_RUN:-0}" = 1 ]; then
  printf -- '--- would post to %s ---\n%s\n' "${track:-a new issue}" "$body"
  exit 0
fi
gh api "repos/$HERE/issues/$track/comments" -f body="$body" --jq .html_url
if [ "$pr_state" != open ]; then
  gh api -X PATCH "repos/$HERE/issues/$track" -f state=closed --jq .state
fi
