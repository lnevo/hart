# JMRI jython -- part of signal_coordinator.py: claim parsing and ordering, the claim race
# between hosts, and the abort that a lost race or a rival's enabling starts.
#
# signal_coordinator.py loads this from preference:jython after sml_beans and reloads it on
# every run (jython_siblings.py).

import re
from java.lang import Runnable, Thread

from sml_beans import SML_ABORT_RESUME_MS, _ascii


def _host_token(name):
    """One lower-case word for the payload: first DNS label, [a-z0-9_-] only."""
    s = _ascii(name).strip().lower().split(".")[0] if name else ""
    s = re.sub(r"[^a-z0-9_-]+", "-", s).strip("-")
    return s or "unknown"


def _local_host_name():
    name = None
    try:
        from java.net import InetAddress

        name = InetAddress.getLocalHost().getHostName()
    except Exception:
        name = None
    if not name:
        try:
            import platform

            name = platform.node()
        except Exception:
            name = None
    return _host_token(name)


def _parse_claim(message):
    """sml_claim payload -> (mode, host, stamp, force).

    "enabling <host> <ms> [force]" or "enabled <host> <ms>". Anything shorter or without
    a number gives host and stamp None.
    """
    words = _ascii(message).split()
    if not words:
        return "", None, None, False
    mode = words[0].lower()
    if len(words) < 3:
        return mode, None, None, False
    try:
        stamp = int(words[2])
    except Exception:
        return mode, None, None, False
    force = "force" in [w.lower() for w in words[3:]]
    return mode, words[1].lower(), stamp, force


def _claim_key(stamp, host, force):
    """Smaller wins: a force claim first, then the earlier stamp, then the host name."""
    return (0 if force else 1, stamp, host)


def _owned_claim(old):
    """The claim of an earlier run's controller if it owns Digicon and is not mid-change."""
    try:
        claim = getattr(old, "_claim", None)
        if claim is None or not getattr(old, "_global_enabled", False):
            return None
        for busy in ("_busy", "_abort_in_progress", "_releasing", "_shutting_down"):
            if getattr(old, busy, False):
                return None
        return claim
    except Exception:
        return None


class SmlClaims(object):
    """DigiconMqttSml's claims: stamp, announce, compare, lose, and the abort."""

    def _is_busy(self):
        """A Disable/Enable worker or an abort is running."""
        return self._busy or self._abort_in_progress

    def _abort_sml_immediate(self):
        """Uncheck Digicon SML now: aborting -> dests off (no Hold/Red/Unheld) -> aborted.

        Called on JMRI's one MQTT callback thread. The bulk uncheck waits on the layout
        thread, so it runs on a worker; SET stops and the ACK is refused here at once.
        Leaves `_busy` alone: a Disable/Enable worker still running owns that flag.
        """
        if self._abort_in_progress:
            return
        self._abort_in_progress = True
        self._abort_gen += 1
        self._boot_pending = False
        self._global_enabled = False
        self._enabling_originator = False
        self._claim = None
        self._sync_sml_mode_sensor()
        controller = self

        class _Abort(Runnable):
            def run(_self):
                controller._run_abort()

        Thread(_Abort(), "digicon-sml-abort").start()

    def _run_abort(self):
        self._suppress_sml = True
        try:
            print("mqtt_signalhead: sml_mode aborting (immediate uncheck, no RELEASE)")
            self._publish_mode("aborting")
            if self._set_all_digicon_sml_destinations(False) is not True:
                self._retry_uncheck_loudly("abort")
            self._snapshot_mast_sml_state()
            self._publish_mode("aborted")
            print("mqtt_signalhead: sml_mode aborted")
        finally:
            self._suppress_sml = False
            self._abort_in_progress = False
            # A Disable/Enable worker still running resets the button when it ends.
            if not self._busy:
                self._set_button_label()

    def _stamp_claim(self, force=False):
        """Start a claim: this host's stamp now. Published by _announce_enabling."""
        with self._claim_lock:
            self._claim = (self._now_ms(), bool(force))
            self._enabling_originator = True

    def _announce_enabling(self, reason, force=False):
        """Publish enabling with this host's claim; a stamped claim keeps its stamp."""
        with self._claim_lock:
            if self._claim is None or not self._enabling_originator:
                self._stamp_claim(force=force)
            stamp, forced = self._claim
            self._publish_mode("enabling")
        print(
            "mqtt_signalhead: sml_mode enabling (%s; claim %s %d%s)"
            % (reason, self._host, stamp, " force" if forced else "")
        )

    def _my_claim_key(self):
        stamp, force = self._claim
        return _claim_key(stamp, self._host, force)

    def _is_own_claim(self, host, stamp):
        return (
            self._claim is not None
            and host == self._host
            and stamp == self._claim[0]
        )

    def _lose_claim(self, why):
        """Another host's claim won. Pending: cancel the Hold; with dests on: abort."""
        print("mqtt_signalhead: %s -- stand down" % why)
        self._claim = None
        self._enabling_originator = False
        if self._global_enabled or self._digicon_dests_on():
            self._abort_sml_immediate()
        else:
            # A pending Hold reads the bump and leaves the pairs off, with no enabled.
            self._abort_gen += 1
            self._sync_sml_mode_sensor()

    def _resolve_claim_race(self, mode, host, stamp, force):
        """A claim (enabling) or ownership (enabled) from elsewhere while this host
        claims or owns. The smaller key wins on both hosts, as each compares the
        same two keys."""
        if host == self._host:
            print(
                "mqtt_signalhead: %s from this host's earlier run (%d) -- ignored"
                % (mode, stamp)
            )
            return
        theirs = _claim_key(stamp, host, force)
        if self._releasing or theirs < self._my_claim_key():
            self._lose_claim(
                "%s %s %d%s is first" % (mode, host, stamp, " force" if force else "")
            )
            return
        if self._global_enabled:
            # Still the owner: say so, so the later claimant stands down.
            print(
                "mqtt_signalhead: %s %s %d is later -- keep Digicon, re-announce enabled"
                % (mode, host, stamp)
            )
            self._publish_mode("enabled")
            return
        print(
            "mqtt_signalhead: %s %s %d is later -- keep taking" % (mode, host, stamp)
        )

    def _schedule_enabled_after_enabling(self):
        """Originator only: dests stay on; after a short wait announce enabled."""
        if self._enabling_wait_scheduled:
            return
        self._enabling_wait_scheduled = True
        controller = self

        class _Resume(Runnable):
            def run(_self):
                Thread.sleep(SML_ABORT_RESUME_MS)
                controller._enabling_wait_scheduled = False
                if controller._shutting_down:
                    print("mqtt_signalhead: enabling announce skipped (shutting down)")
                    return
                if controller._global_enabled and str(
                    controller._retained_mode or ""
                ).strip().lower() == "enabled":
                    print("mqtt_signalhead: enabling announce skipped (already enabled)")
                    return
                print("mqtt_signalhead: enabling -- take Digicon (enabled)")
                controller._enter_enabled(force=True, from_boot=True, resume=True)

        Thread(_Resume(), "digicon-sml-enabling").start()
