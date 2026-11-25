# MQTT startup race upstream: hand-off (2026-11-23)

Status: active

Watch JMRI/JMRI pull request [#16004](https://github.com/JMRI/JMRI/pull/16004) and issue [#16003](https://github.com/JMRI/JMRI/issues/16003) until the pull request is merged; the owner closes the topic only then (2026-11-23).

## Where it stands

- The startup MQTT drop is a stock JMRI bug in `MqttAdapter`, reproduced on bare profiles and fixed by the diff in [`docs/jmri/MQTT_STARTUP_RACE.md`](../../docs/jmri/MQTT_STARTUP_RACE.md).
- #16003 (issue) has the cause, the results and the diff, plus a comment that the fix targets the 5.19 series and `master`, not 5.18 or the 5.17.6 pre-release.
- #16004 (pull request, opened 2026-11-23 about 23:00) is commit `ed9e77ab` on `lnevo/JMRI` branch `fix-mqtt-listener-race`: the fix, `MqttAdapterTest` changes with two new tests, and a release note under MQTT. All 363 MQTT tests passed locally on JDK 11.
- At hand-off, JMRI's checks showed two expected failures: `check-pr` (JMRI blocks merging for 24 hours after a pull request opens; label "New PR") and "Approved after last commit" (waits for a maintainer review). The release-note check passed. JMRI's build and test workflows had not started; most likely they wait for a maintainer to approve runs from a first-time contributor, not confirmed.
- The hosts run JMRI 5.16 with the fix as a one-class overlay meanwhile (2026-11-24, [ADR-034](../decisions/ADR-034-jmri-mqtt-race-overlay.md), `tools/jmri/mqtt_overlay/`). A change asked for in #16004 goes into `tools/jmri/mqtt_overlay/MqttAdapter.java` too, then `build.sh` and a deploy.

- Open on #16004, found by this repo's code review (2026-11-24): a `subscribe()` that gets a topic's list from `computeIfAbsent` just as `unsubscribe()` empties it and removes it from the map adds its listener to a list the map no longer holds, so that bean gets no messages and the broker subscription is gone. It needs the last listener of a topic to unsubscribe while another subscribes (a bean deleted at run time), which the layout does not do. Fix: do the add and the remove-if-empty in one `compute` per key. Proposing it on #16004 is public: owner's yes first; the overlay follows whatever JMRI takes.

## The watcher

In a fresh session, schedule a recurring check (for example every 3 hours, off the hour) with this prompt:

> Check JMRI/JMRI pull request #16004 and issue #16003 for anything new since the last check: comments, review comments or requested changes, CI workflow runs and their results, labels, approval, merge or close. Use gh read-only (`gh pr view 16004 -R JMRI/JMRI --comments`, `gh pr checks 16004 -R JMRI/JMRI`, `gh issue view 16003 -R JMRI/JMRI --comments`). If nothing changed, say so in one line. If a reviewer asked for changes or a check failed on the code, give the exact text and propose the fix, but do not push, comment or reply on JMRI without the owner's yes. If the PR is merged, tell the owner and close the topic (below), then delete the job. If it is closed without merging, tell the owner and stop.

## If changes are asked for

- The branch is `fix-mqtt-listener-race` on `lnevo/JMRI`. A sparse, blobless clone of the fork is enough to edit: `java/src/jmri/jmrix/mqtt/`, `java/test/jmri/jmrix/mqtt/` and `help/en/releasenotes/current-draft-note.shtml`.
- Run JMRI's tests on the Windows box's WSL (Ubuntu-24.04), which has JDK 11, Maven and Ant installed and a clone at `~/jmri-pr/JMRI`: `git pull`, then `JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64 mvn -q -B -Dtest='jmri.jmrix.mqtt.**.*Test' -Dsurefire.failIfNoSpecifiedTests=false test -Djmri.skipTestsRequiringSeparateRunning=true -Djava.awt.headless=true`. The first run took 213 s with dependencies cached.
- The bare-profile startup repro is `tools/jmri/mqtt_race_repro/run.sh`, if a reviewer wants the startup numbers again.
- Every push or reply to JMRI is public under the owner's account: owner's yes first.

## Closing the topic

When #16004 is merged: in a new worktree, replace the race item in `wiki/STATUS.md` Future goals with the merge date and the first JMRI release that carries it, log the old text in `wiki/STATUS_LOG.md`, set this page to `Status: done (YYYY-MM-DD)` and drop it from the active list in `wiki/home.md`. Then ask the owner whether to remove the test tools on the Windows box's WSL (JDK 11, JDK 21 runtime, Maven, Ant, Mosquitto with its service off, `~/jmri-pr`, `~/mqtt-race-repro`) and `C:\Users\lnevo\mqtt-race-win`. Moving the hosts to the fixed JMRI waits for a release that CATS supports (`wiki/STATUS.md`, JMRI line); once they run it, remove `tools/jmri/mqtt_overlay/` and the deploy lines that call it (ADR-034).
