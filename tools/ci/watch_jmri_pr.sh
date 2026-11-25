#!/usr/bin/env bash
# Watches JMRI/JMRI pull request #16004 and issue #16003 from GitHub Actions (.github/workflows/watch-jmri-pr.yml).
# Read-only on JMRI. Anything new since the last report becomes a comment on one tracking issue in this repo that
# mentions the owner, so GitHub's own notifications (mobile app, email) do the alerting. The cutoff is the time of
# that issue's last comment from this job, so a late or skipped scheduled run neither loses nor repeats an event.
# When the pull request is merged or closed, the job posts once more and closes the tracking issue; a closed
# tracking issue stops the job. Needs GH_TOKEN with issues: write on this repo. DRY_RUN=1 prints instead of posting.
set -euo pipefail

UP=repos/JMRI/JMRI
PR=16004
ISSUE=16003
HERE="${GITHUB_REPOSITORY:-lnevo/hart}"
OWNER_LOGIN=lnevo
TITLE="Watch: JMRI/JMRI PR #$PR (MQTT startup race)"
BOT="github-actions[bot]"

existing="$(gh api "repos/$HERE/issues?state=all&creator=$BOT&per_page=100" \
  --jq "[.[] | select(.title == \"$TITLE\" and (.pull_request | not))] | first // empty | \"\(.number) \(.state) \(.created_at)\"")"

if [ -n "$existing" ]; then
  read -r track state_here created <<<"$existing"
  if [ "$state_here" = closed ]; then
    echo "tracking issue #$track is closed: nothing to watch"
    exit 0
  fi
  cutoff="$(gh api "repos/$HERE/issues/$track/comments?per_page=100" --paginate \
    --jq "[.[] | select(.user.login == \"$BOT\") | .created_at] | last // empty" | tail -n1)"
  cutoff="${cutoff:-$created}"
else
  track=""
  cutoff="${SINCE:-$(date -u -d '-255 min' +%FT%TZ)}"
fi
echo "cutoff $cutoff"

pr_json="$(gh api "$UP/pulls/$PR")"
head="$(jq -r .head.sha <<<"$pr_json")"
pr_state="$(jq -r .state <<<"$pr_json")"
merged="$(jq -r .merged <<<"$pr_json")"
status="$(jq -r '"STATE \(.state) merged=\(.merged) by=\(.merged_by.login // "-") at=\(.merged_at // "-") labels=\([.labels[].name] | join(",")) head=\(.head.sha[0:8])"' <<<"$pr_json")"

lines=()
for e in "pulls/$PR/reviews" "pulls/$PR/comments" "issues/$PR/comments" "issues/$ISSUE/comments"; do
  while IFS= read -r l; do [ -n "$l" ] && lines+=("$l"); done < <(gh api "$UP/$e?per_page=100" --paginate --jq \
    ".[] | select((.submitted_at // .created_at) > \"$cutoff\") |
      \"- NEW \`$e\` \(.user.login) \(.submitted_at // .created_at) \(.state // \"\"): \((.body // \"\") | gsub(\"\\\\s+\"; \" \") | .[0:400]) \(.html_url)\"")
done
while IFS= read -r l; do [ -n "$l" ] && lines+=("$l"); done < <(gh api "$UP/issues/$PR/events?per_page=100" --paginate --jq \
  ".[] | select(.created_at > \"$cutoff\") | \"- NEW event \(.event) \(.actor.login) \(.created_at)\"")
while IFS= read -r l; do [ -n "$l" ] && lines+=("$l"); done < <(gh api "$UP/commits/$head/check-runs?per_page=100" --jq \
  ".check_runs[] | select(.conclusion != null and .conclusion != \"success\" and .conclusion != \"skipped\"
      and .completed_at > \"$cutoff\" and .name != \"check-pr\" and (.name | test(\"Approved after\") | not))
    | \"- FAIL \(.name) \(.conclusion) \(.completed_at) \(.html_url)\"")

echo "$status"
printf '%s\n' "${lines[@]+"${lines[@]}"}"

if [ "${#lines[@]}" -eq 0 ] && [ "$pr_state" = open ]; then
  echo "nothing new"
  exit 0
fi

body="@$OWNER_LOGIN JMRI/JMRI#$PR: \`$status\`"$'\n\n'
[ "${#lines[@]}" -gt 0 ] && body+="$(printf '%s\n' "${lines[@]}")"$'\n'
if [ "$pr_state" != open ]; then
  if [ "$merged" = true ]; then
    body+=$'\n'"Merged. Close the topic per [the hand-off](https://github.com/$HERE/blob/main/wiki/projects/mqtt-race-upstream-handoff.md#closing-the-topic) and delete \`.github/workflows/watch-jmri-pr.yml\`. This issue closes now, which stops the watch."
  else
    body+=$'\n'"Closed without merging. This issue closes now, which stops the watch."
  fi
fi

if [ "${DRY_RUN:-0}" = 1 ]; then
  printf -- '--- would post to %s ---\n%s\n' "${track:-a new issue}" "$body"
  exit 0
fi

if [ -z "$track" ]; then
  track="$(gh api "repos/$HERE/issues" -f title="$TITLE" \
    -f body="Comments here come from \`.github/workflows/watch-jmri-pr.yml\` when JMRI/JMRI#$PR or #$ISSUE changes. @$OWNER_LOGIN" \
    --jq .number)"
  echo "opened tracking issue #$track"
fi
gh api "repos/$HERE/issues/$track/comments" -f body="$body" --jq .html_url
if [ "$pr_state" != open ]; then
  gh api -X PATCH "repos/$HERE/issues/$track" -f state=closed --jq .state
fi
