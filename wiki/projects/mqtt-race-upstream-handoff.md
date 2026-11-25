# MQTT startup race upstream: hand-off (2026-11-23)

Status: active

Watch JMRI/JMRI pull request [#16004](https://github.com/JMRI/JMRI/pull/16004) and issue [#16003](https://github.com/JMRI/JMRI/issues/16003) until the pull request is merged; the owner closes the topic only then (2026-11-23).

## Where it stands

- The startup MQTT drop is a stock JMRI bug in `MqttAdapter`, reproduced on bare profiles and fixed by the diff in [`docs/jmri/MQTT_STARTUP_RACE.md`](../../docs/jmri/MQTT_STARTUP_RACE.md).
- #16003 (issue) has the cause, the results and the diff, plus a comment that the fix targets the 5.19 series and `master`, not 5.18 or the 5.17.6 pre-release.
- #16004 (pull request, opened 2026-11-23 about 23:00) is commit `ed9e77ab` on `lnevo/JMRI` branch `fix-mqtt-listener-race`: the fix, `MqttAdapterTest` changes with two new tests, and a release note under MQTT. All 363 MQTT tests passed locally on JDK 11.
- At hand-off, JMRI's checks showed two expected failures: `check-pr` (JMRI blocks merging for 24 hours after a pull request opens; label "New PR") and "Approved after last commit" (waits for a maintainer review). The release-note check passed. JMRI's build and test workflows had not started; most likely they wait for a maintainer to approve runs from a first-time contributor, not confirmed.
- The hosts stay on stock JMRI 5.16 meanwhile (`wiki/STATUS.md`, Future goals).

## The watcher

GitHub Actions runs it, so it costs no Claude tokens (2026-11-24; it replaced a cloud scheduled task). [`.github/workflows/watch-jmri-pr.yml`](../../.github/workflows/watch-jmri-pr.yml) runs [`tools/ci/watch_jmri_pr.sh`](../../tools/ci/watch_jmri_pr.sh) every 4 hours at :17. It reads #16004 and #16003 (reviews, new or edited comments, events, new commits, failed check runs other than `check-pr` and "Approved after last commit") and, only when something is new, comments on the issue "Watch: JMRI/JMRI PR 16004 (MQTT startup race)" in this repo, mentioning the owner; GitHub's own notifications deliver it. Quoted JMRI text and links sit in code spans, so the posts ping no one else and leave no cross-reference on the JMRI pull request. When the pull request is merged or closed it posts once more and closes that issue, which stops the watch. Run it by hand from the Actions tab (`dry_run` prints without posting). It never writes to JMRI. A reply or fix on JMRI still needs a session and the owner's yes.

## If changes are asked for

- The branch is `fix-mqtt-listener-race` on `lnevo/JMRI`. A sparse, blobless clone of the fork is enough to edit: `java/src/jmri/jmrix/mqtt/`, `java/test/jmri/jmrix/mqtt/` and `help/en/releasenotes/current-draft-note.shtml`.
- Run JMRI's tests on the Windows box's WSL (Ubuntu-24.04), which has JDK 11, Maven and Ant installed and a clone at `~/jmri-pr/JMRI`: `git pull`, then `JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64 mvn -q -B -Dtest='jmri.jmrix.mqtt.**.*Test' -Dsurefire.failIfNoSpecifiedTests=false test -Djmri.skipTestsRequiringSeparateRunning=true -Djava.awt.headless=true`. The first run took 213 s with dependencies cached.
- The bare-profile startup repro is `tools/jmri/mqtt_race_repro/run.sh`, if a reviewer wants the startup numbers again.
- Every push or reply to JMRI is public under the owner's account: owner's yes first.

## Closing the topic

When #16004 is merged: in a new worktree, replace the race item in `wiki/STATUS.md` Future goals with the merge date and the first JMRI release that carries it, log the old text in `wiki/STATUS_LOG.md`, set this page to `Status: done (YYYY-MM-DD)` and drop it from the active list in `wiki/home.md`. Then ask the owner whether to remove the test tools on the Windows box's WSL (JDK 11, JDK 21 runtime, Maven, Ant, Mosquitto with its service off, `~/jmri-pr`, `~/mqtt-race-repro`) and `C:\Users\lnevo\mqtt-race-win`. Moving the hosts to the fixed JMRI waits for a release that CATS supports (`wiki/STATUS.md`, JMRI line).
