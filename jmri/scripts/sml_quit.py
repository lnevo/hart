# JMRI jython -- part of signal_coordinator.py: the quit release (main-window close and the
# ShutDownTask): Hold, Unheld, sml_mode disabled, then the SML pairs off, once.
#
# signal_coordinator.py loads this from preference:jython after sml_beans and reloads it on every run
# (jython_siblings.py). The task itself (DigiconSmlQuitTask) and its registration stay in the
# script: the task falls back to the script's global `controller`.

from java.lang import Runnable, Thread

from sml_beans import HOLD_WAIT_MS, _ascii


class SmlQuit(object):
    """DigiconMqttSml's release of Digicon when JMRI quits."""

    def _add_quit_window_hook(self):
        """WINDOW_CLOSING still has MQTT; File->Exit / window X both hit this."""
        try:
            from apps import Apps
            from java.awt.event import WindowAdapter

            space = Apps.buttonSpace()
            frame = space.getTopLevelAncestor() if space is not None else None
            if frame is None:
                print("mqtt_signalhead: no main frame for window close hook")
                return
            hook = self

            class _Quit(Runnable):
                def run(_self):
                    hook._on_jmri_shutdown()

            class _Close(WindowAdapter):
                def windowClosing(_self, event):
                    # The release Holds for HOLD_WAIT_MS; never sleep on the Swing thread.
                    print("mqtt_signalhead: main window closing")
                    Thread(_Quit(), "digicon-sml-quit").start()

            listener = _Close()
            frame.addWindowListener(listener)
            self._close_frame = frame
            self._close_listener = listener
            print(
                "mqtt_signalhead: window close hook on %s"
                % _ascii(frame.getTitle())
            )
        except Exception as exc:
            print("mqtt_signalhead: window close hook failed: " + _ascii(exc))

    def _owns_digicon_now(self):
        if self._global_enabled or self._enabling_originator:
            return True
        try:
            for mast in self._masts:
                if self._enabled_dest_count(mast) > 0:
                    return True
        except Exception:
            pass
        return False

    def _on_jmri_shutdown(self):
        """Quit: Hold/wait/Unheld then sml_mode disabled. Idempotent.

        The window-close worker and the ShutDownTask can both call this; the lock makes
        the later caller wait for the release instead of running it a second time.
        """
        with self._shutdown_lock:
            self._on_jmri_shutdown_locked()

    def _on_jmri_shutdown_locked(self):
        if self._shutdown_released:
            return
        self._shutting_down = True
        try:
            if self._abort_in_progress:
                print(
                    "mqtt_signalhead: shutdown skip (abort; other agent owns Digicon)"
                )
                self._shutdown_released = True
                return
            if not self._owns_digicon_now():
                print("mqtt_signalhead: shutdown skip (SML not enabled)")
                self._shutdown_released = True
                return
            print("mqtt_signalhead: shutdown Hold/wait/Unheld then disabled")
            self._busy = True
            try:
                self._release_on_quit()
            finally:
                self._busy = False
            self._shutdown_released = True
        except Exception as exc:
            print("mqtt_signalhead: shutdown task failed: " + _ascii(exc))

    def _release_on_quit(self):
        """MQTT Unheld + disabled before dest uncheck so a layout hang cannot skip RELEASE.

        JMRI is exiting, so its pairs stop driving Digicon anyway. An abort during the
        Hold means another agent is taking Digicon: no Unheld and no disabled over its
        enabling. While it runs, any other host's claim wins.
        """
        self._releasing = True
        try:
            self._release_on_quit_steps()
        finally:
            self._releasing = False

    def _release_on_quit_steps(self):
        abort_gen = self._abort_gen
        print(
            "mqtt_signalhead: Hold Digicon masts, wait %d ms before Unheld / disabled"
            % HOLD_WAIT_MS
        )
        self._set_masts_held(True)
        Thread.sleep(HOLD_WAIT_MS)
        if self._abort_gen != abort_gen:
            print("mqtt_signalhead: shutdown aborted during Hold -- no Unheld, no disabled")
        else:
            print(
                "mqtt_signalhead: shutdown publishing Unheld for %d MQTT head(s)"
                % len(self._heads)
            )
        for head in self._heads:
            if self._abort_gen != abort_gen:
                break
            self._publish_unheld(head)
        sent = False
        with self._claim_lock:
            if self._abort_gen == abort_gen:
                self._publish_mode("disabled")
                sent = True
                # Not the owner from here on: no head SET may follow disabled.
                self._global_enabled = False
                self._enabling_originator = False
                self._claim = None
        if sent:
            # The release is out: a later failure must not make a second caller
            # send disabled again.
            self._shutdown_released = True
            self._sync_sml_mode_sensor()
            print("mqtt_signalhead: shutdown sml_mode disabled -- unchecking SML pairs")
        else:
            print("mqtt_signalhead: shutdown -- unchecking SML pairs (no disabled sent)")
        suppress = self._suppress_sml
        self._suppress_sml = True  # the uncheck itself publishes nothing
        try:
            if self._set_all_digicon_sml_destinations(False) is not True:
                print(
                    "mqtt_signalhead: shutdown FAILED to turn all SML pairs off "
                    "(still on: %s)" % self._pairs_still_on()
                )
            try:
                self._snapshot_mast_sml_state()
            except Exception as exc:
                print("mqtt_signalhead: shutdown snapshot failed: " + _ascii(exc))
        finally:
            self._suppress_sml = suppress
            # A failed bulk set must not leave the masts Held or this host owning.
            self._set_masts_held(False)
            self._global_enabled = False
            self._enabling_originator = False
            self._claim = None
            self._sync_sml_mode_sensor()
