# JMRI jython -- part of signal_coordinator.py: the boot check, the Enable / Disable steps
# and the hand-off of each Digicon head between SML (SET) and the field (Unheld; the mast reports
# are painted in sml_events).
#
# signal_coordinator.py loads this from preference:jython after sml_beans and sml_claims and
# reloads it on every run (jython_siblings.py).

from java.lang import Runnable, Thread
from javax.swing import JOptionPane, SwingUtilities

from sml_beans import (
    BOOT_MODE_WAIT_MS,
    HOLD_WAIT_MS,
    PROBE_WAIT_MS,
    SML_ABORT_RESUME_MS,
    SML_MODE_TOPIC,
    TOPIC_PREFIX,
    _ascii,
    _bean_label,
    _head_manager,
    _head_names_on_mast,
    _topic_suffix,
)


class SmlHandoff(object):
    """DigiconMqttSml's Enable / Disable and per-mast hand-off between SML and the field."""

    def _boot_hold_sml_off(self):
        """Force Digicon SML pairs off until boot check finishes. No MQTT mute."""
        self._boot_pending = True
        if self._set_all_digicon_sml_destinations(False) is not True:
            self._retry_uncheck_loudly("boot hold")
        self._global_enabled = False
        self._sync_sml_mode_sensor()
        self._snapshot_mast_sml_state()
        self._set_button_label()

    def _schedule_boot_check(self):
        """After subscribe, read sml_mode (broker retain arrives as a message).

        No publish during this decision. missing/disabled/query -> enable Digicon;
        enabled -> stay Disabled with zero Unheld.
        """
        controller = self

        class _Boot(Runnable):
            def run(_self):
                Thread.sleep(BOOT_MODE_WAIT_MS)
                if controller._shutting_down:
                    print("mqtt_signalhead: boot check skipped (shutting down)")
                    return
                # Read and claim in one step: a rival claim lands before (seen here) or after
                # (compared with this claim).
                with controller._claim_lock:
                    mode = controller._retained_mode
                    mode_s = "" if mode is None else str(mode).strip().lower()
                    take = mode is None or mode_s in (
                        "",
                        "disabled",
                        "query",
                        "disabling",
                    )
                    # A claim with this host's own name was left by its earlier run.
                    own_stale = (
                        mode_s in ("enabled", "enabling")
                        and controller._retained_host == controller._host
                    )
                    if take or own_stale:
                        print(
                            "mqtt_signalhead: boot mode=%s%s -- take Digicon (enable)"
                            % (
                                mode_s if mode_s else "missing",
                                " (left by this host)" if own_stale else "",
                            )
                        )
                        controller._boot_pending = False
                        controller._enter_enabled(force=True, from_boot=True)
                        return
                print(
                    "mqtt_signalhead: boot mode=%s -- stay SML Disabled "
                    "(no Unheld, no mode publish)"
                    % (mode_s if mode_s else "missing")
                )
                controller._boot_pending = False
                controller._global_enabled = False
                controller._snapshot_mast_sml_state()
                controller._set_button_label()

        Thread(_Boot(), "digicon-sml-boot").start()

    def _on_toggle(self):
        if self._is_busy():
            return
        if self._global_enabled:
            self._enter_disabled(release=True)
        else:
            self._enter_enabled(force=False, from_boot=False)

    def _ask_force_override_edt(self):
        """Show override confirm on the EDT. Return True if Yes."""
        holder = [JOptionPane.NO_OPTION]
        msg = (
            "track/bridge/sml_mode is already enabled "
            "(another Digicon session or stale retain).\n"
            "Force override Digicon control?"
        )
        title = "SML Enabled"

        class _Ask(Runnable):
            def run(_self):
                try:
                    from jmri.util.swing import JmriJOptionPane

                    holder[0] = JmriJOptionPane.showConfirmDialog(
                        None,
                        msg,
                        title,
                        JmriJOptionPane.YES_NO_OPTION,
                        JmriJOptionPane.WARNING_MESSAGE,
                    )
                except Exception:
                    holder[0] = JOptionPane.showConfirmDialog(
                        None,
                        msg,
                        title,
                        JOptionPane.YES_NO_OPTION,
                        JOptionPane.WARNING_MESSAGE,
                    )

        try:
            if SwingUtilities.isEventDispatchThread():
                _Ask().run()
            else:
                SwingUtilities.invokeAndWait(_Ask())
        except Exception as exc:
            print("mqtt_signalhead: override dialog failed: " + _ascii(exc))
            return False
        return holder[0] == JOptionPane.YES_OPTION

    def _probe_and_confirm_override(self):
        """If sml_mode is already enabled elsewhere, ask before taking control.

        Return "ok" (take Digicon now), "force" (publish enabling so others
        abort), or "cancel".
        """
        mode = self._retained_mode
        if mode is not None and str(mode).strip().lower() == "enabled":
            print("mqtt_signalhead: retain already enabled -- asking override")
            if self._ask_force_override_edt():
                return "force"
            return "cancel"
        # Live probe: another Enabled Digicon answers query with enabled.
        self._probe_saw_enabled = False
        self._probe_active = True
        try:
            self._publish(SML_MODE_TOPIC, "query", retain=False)
            print("mqtt_signalhead: enable probe query (wait for enabled ACK)")
            Thread.sleep(PROBE_WAIT_MS)
        finally:
            self._probe_active = False
        if self._probe_saw_enabled:
            print("mqtt_signalhead: probe saw enabled -- asking override")
            if self._ask_force_override_edt():
                return "force"
            return "cancel"
        print("mqtt_signalhead: probe clear -- enabling without override")
        return "ok"

    def _enter_enabled(self, force, from_boot, resume=False):
        """Take Digicon on a worker. force/from_boot skip the operator probe.

        A boot or bridge-release take claims here, on the deciding thread, so the claim
        goes out at the moment of the decision. resume=True carries on the claim the
        stored-dests boot announced, and skips if that claim was lost.
        """
        with self._claim_lock:
            if self._is_busy() or self._shutting_down:
                return
            if resume:
                if self._claim is None or not self._enabling_originator:
                    print("mqtt_signalhead: enabling lost to another host -- no take")
                    return
            elif force or from_boot:
                self._announce_enabling("take")
            self._busy = True
            abort_gen = self._abort_gen
        self._set_button_busy()
        controller = self

        class _Run(Runnable):
            def run(_self):
                try:
                    if controller._shutting_down:
                        return
                    if not force and not from_boot:
                        result = controller._probe_and_confirm_override()
                        if result == "cancel":
                            print("mqtt_signalhead: enable aborted (no override)")
                            return
                        with controller._claim_lock:
                            if controller._abort_gen != abort_gen:
                                print(
                                    "mqtt_signalhead: enable skipped (aborted during "
                                    "probe; another agent is taking Digicon)"
                                )
                                return
                            if result == "force":
                                controller._announce_enabling("force override", force=True)
                            else:
                                controller._announce_enabling("operator enable")
                        if result == "force":
                            Thread.sleep(SML_ABORT_RESUME_MS)
                    if controller._shutting_down:
                        print("mqtt_signalhead: enable skipped (shutting down)")
                        return
                    controller._hand_off_enabled(abort_gen)
                finally:
                    controller._busy = False
                    controller._set_button_label()
                    controller._sync_sml_mode_sensor()

        Thread(_Run(), "digicon-sml-enable").start()

    def _enter_disabled(self, release):
        # Under the claim lock, as _enter_enabled: a message thread that checks _is_busy()
        # and starts a take cannot slip between this check and _busy.
        with self._claim_lock:
            if self._is_busy():
                return
            self._busy = True
            abort_gen = self._abort_gen
        self._set_button_busy()
        controller = self

        class _Run(Runnable):
            def run(_self):
                controller._releasing = True
                try:
                    controller._hand_off_disabled(release=release, abort_gen=abort_gen)
                finally:
                    controller._releasing = False
                    controller._busy = False
                    controller._set_button_label()
                    controller._sync_sml_mode_sensor()

        Thread(_Run(), "digicon-sml-disable").start()

    def _apply_global_disabled(self, release, publish_mode, abort_gen=None):
        """Disable Digicon SML in JMRI. RELEASE only when release=True.

        If an abort ran since `abort_gen` was read, another agent owns Digicon: no
        Unheld of its heads and no `disabled` over its enabling.
        """
        if abort_gen is None:
            abort_gen = self._abort_gen
        print(
            "mqtt_signalhead: Hold Digicon masts, wait %d ms before SML off / Unheld"
            % HOLD_WAIT_MS
        )
        self._set_masts_held(True)
        Thread.sleep(HOLD_WAIT_MS)
        print("mqtt_signalhead: Hold wait done -- disabling SML pairs")
        off = self._try_set_all_digicon_sml(False)
        aborted = self._abort_gen != abort_gen
        if aborted:
            print(
                "mqtt_signalhead: aborted during Disable -- no Unheld, no disabled "
                "(another agent owns Digicon)"
            )
        elif not off:
            self._stay_owner_after_failed_disable(abort_gen)
            return
        if release and not aborted:
            print(
                "mqtt_signalhead: publishing Unheld for %d MQTT head(s)"
                % len(self._heads)
            )
            for head in self._heads:
                if self._abort_gen != abort_gen:
                    break
                self._publish_unheld(head)
        self._set_masts_held(False)
        self._global_enabled = False
        self._enabling_originator = False
        self._claim = None
        if publish_mode and self._abort_gen == abort_gen:
            self._publish_mode("disabled")
        self._sync_sml_mode_sensor()

    def _try_set_all_digicon_sml(self, enabled):
        """Bulk set, then snapshot; False (printed) if any pair may be left as it was."""
        ok = False
        try:
            ok = self._set_all_digicon_sml_destinations(enabled) is True
            self._snapshot_mast_sml_state()
        except Exception as exc:
            print(
                "mqtt_signalhead: %s SML pairs failed: %s"
                % ("enabling" if enabled else "disabling", _ascii(exc))
            )
            ok = False
        return ok

    def _set_masts_held(self, held):
        """Hold (or release) every Digicon mast. A mast that refuses is printed by name and
        the rest still go: one stuck mast must not stop the hand-off of the others."""
        for mast in self._masts:
            try:
                mast.setHeld(held)
            except Exception as exc:
                print(
                    "mqtt_signalhead: %s failed on %s: %s"
                    % ("Hold" if held else "Hold release", _bean_label(mast), _ascii(exc))
                )

    def _stay_owner_after_failed_disable(self, abort_gen):
        """Pairs may still be on: handing off now would make two owners. Keep Digicon.

        After an abort another agent owns Digicon: no re-enable and no enabled.
        """
        print("mqtt_signalhead: Disable FAILED -- SML pairs may still be on")
        if self._abort_gen != abort_gen:
            print("mqtt_signalhead: taken over during the failed Disable -- no enabled")
            self._set_masts_held(False)
            self._sync_sml_mode_sensor()
            return
        # Best effort: all pairs on again, so this host owns consistently.
        on = self._try_set_all_digicon_sml(True)
        if self._abort_gen != abort_gen:
            print("mqtt_signalhead: taken over during the failed Disable -- pairs off, no enabled")
            if self._set_all_digicon_sml_destinations(False) is not True:
                self._retry_uncheck_loudly("taken over during the failed Disable")
            self._snapshot_mast_sml_state()
            self._set_masts_held(False)
            self._sync_sml_mode_sensor()
            return
        print(
            "mqtt_signalhead: keeping Digicon (enabled) after the failed Disable. "
            "Check the SML table, then try Disable again."
        )
        self._set_masts_held(False)
        if not on:
            self._unheld_heads_of_dark_masts(abort_gen)
        with self._claim_lock:
            if self._abort_gen == abort_gen:
                self._publish_mode("enabled")
        self._sync_sml_mode_sensor()

    def _unheld_heads_of_dark_masts(self, abort_gen):
        """Owning with some pairs off: their masts send no SET, so let the field drive
        their heads (Unheld) rather than freeze them."""
        names = []
        for mast in self._masts:
            if self._mast_logic_enabled(mast):
                continue
            names.append(_bean_label(mast))
            for head in self._mqtt_heads_on_mast(mast):
                if self._abort_gen != abort_gen:
                    return
                self._publish_unheld(head)
        if names:
            print(
                "mqtt_signalhead: owning with these masts' pairs off -- Unheld their "
                "heads: %s" % ", ".join(names)
            )

    def _pairs_still_on(self):
        """'source -> dest' for every Digicon pair still Enabled, for failure lines."""
        out = []
        for sml in self._smls:
            try:
                it = sml.getDestinationList().iterator()
                while it.hasNext():
                    dest = it.next()
                    if sml.isEnabled(dest):
                        out.append(
                            "%s -> %s" % (_bean_label(sml.getSourceMast()), _bean_label(dest))
                        )
            except Exception:
                continue
        return ", ".join(out) or "none listed"

    def _retry_uncheck_loudly(self, why):
        """After a bulk uncheck that failed: print the pairs still on and retry once.
        Always retry, as before: in JMRI runOnLayout blocks until the work is done, so
        a timeout cannot be told apart reliably, and a missed retry can leave pairs on
        while another host owns Digicon."""
        print(
            "mqtt_signalhead: %s FAILED to turn all SML pairs off (still on: %s) -- "
            "retrying once" % (why, self._pairs_still_on())
        )
        if self._set_all_digicon_sml_destinations(False) is True:
            return True
        print(
            "mqtt_signalhead: %s retry FAILED -- SML pairs still on: %s"
            % (why, self._pairs_still_on())
        )
        return False

    def _hand_off_disabled(self, release, abort_gen=None):
        print("mqtt_signalhead: global -> SML Disabled (release=%s)" % release)
        self._apply_global_disabled(
            release=release, publish_mode=True, abort_gen=abort_gen
        )

    def _hand_off_enabled(self, abort_gen=None):
        if self._shutting_down:
            print("mqtt_signalhead: enable skipped (shutting down)")
            return
        if abort_gen is None:
            abort_gen = self._abort_gen
        if self._abort_gen != abort_gen or self._claim is None:
            print("mqtt_signalhead: enable skipped (aborted; another agent is taking Digicon)")
            self._enabling_originator = False
            return
        # ACK query/disabling during Hold (not yet _global_enabled). The Hold is also the
        # window in which a rival claim is heard and compared.
        self._enabling_originator = True
        print("mqtt_signalhead: global -> SML Enabled")
        print(
            "mqtt_signalhead: Hold Digicon masts, wait %d ms before SML on"
            % HOLD_WAIT_MS
        )
        self._set_masts_held(True)
        Thread.sleep(HOLD_WAIT_MS)
        # Commit under the claim lock: a rival claim is handled either before (this claim
        # lost, or kept) or after (this host owns; the rival is compared with an owner).
        with self._claim_lock:
            lost = (
                self._shutting_down
                or self._abort_gen != abort_gen
                or self._claim is None
            )
            if not lost:
                self._global_enabled = True
        if lost:
            print(
                "mqtt_signalhead: enable Hold done but shutting down, aborted or lost "
                "to another host -- leave dests, no enabled"
            )
            if self._abort_gen != abort_gen:
                self._enabling_originator = False
            self._set_masts_held(False)
            return
        print("mqtt_signalhead: Hold wait done -- enabling SML pairs")
        on = self._try_set_all_digicon_sml(True)
        if self._abort_gen != abort_gen:
            # Taken over while the pairs went on: the abort's uncheck may have run first.
            print("mqtt_signalhead: taken over during enable -- pairs off, no enabled")
            if self._set_all_digicon_sml_destinations(False) is not True:
                self._retry_uncheck_loudly("taken over during enable")
            self._snapshot_mast_sml_state()
            self._set_masts_held(False)
            return
        if not on:
            if self._back_out_failed_enable(abort_gen):
                return
            self._unheld_heads_of_dark_masts(abort_gen)
        self._set_masts_held(False)
        # Ownership announce for the bridge and the other host (not a boot retain republish).
        # Under the lock, so an abort that lands now cannot be followed by our enabled.
        with self._claim_lock:
            if self._abort_gen == abort_gen and self._claim is not None:
                self._publish_mode("enabled")
            self._enabling_originator = False
        self._sync_sml_mode_sensor()
        # Push current appearances once Digicon owns SET again.
        for head in self._heads:
            if self._mast_logic_enabled(self._mast_for_head(head)):
                self._publish_head_set(head, force=True)

    def _back_out_failed_enable(self, abort_gen):
        """The pairs did not all go on: never announce enabled with pairs off.

        Turn them off again and hand off as Disable does (True). If that fails too,
        some pairs may be on: return False, and the caller stays the owner and
        announces enabled. One owner, possibly partial, beats two.
        """
        print("mqtt_signalhead: Enable FAILED -- not all SML pairs went on; no enabled")
        off = self._try_set_all_digicon_sml(False)
        if not off:
            print(
                "mqtt_signalhead: and turning them off FAILED -- keeping Digicon "
                "(enabled). Check the SML table."
            )
            return False
        print(
            "mqtt_signalhead: SML pairs off again -- publishing Unheld for %d MQTT head(s)"
            % len(self._heads)
        )
        for head in self._heads:
            if self._abort_gen != abort_gen:
                break
            self._publish_unheld(head)
        self._set_masts_held(False)
        with self._claim_lock:
            self._global_enabled = False
            self._enabling_originator = False
            self._claim = None
            if self._abort_gen == abort_gen:
                self._publish_mode("disabled")
        self._sync_sml_mode_sensor()
        return True

    def _mast_for_head(self, head):
        if head is None:
            return None
        return self._head_to_mast.get(head.getSystemName())

    def _sml_for_mast(self, mast):
        if mast is None:
            return None
        return self._sml_by_mast.get(mast)

    def _mast_logic_enabled(self, mast):
        """True if Digicon source mast has any destination Enabled in the SML table."""
        return self._enabled_dest_count(mast) > 0

    def _enabled_dest_count(self, mast):
        if mast is None:
            return 0
        sml = self._sml_for_mast(mast)
        if sml is None:
            return 0
        n = 0
        try:
            dests = sml.getDestinationList()
            if dests is None or dests.isEmpty():
                return 0
            it = dests.iterator()
            while it.hasNext():
                dest = it.next()
                try:
                    if sml.isEnabled(dest):
                        n += 1
                except Exception:
                    continue
        except Exception:
            return 0
        return n

    def _dest_enable_map(self, sml):
        """dest systemName -> isEnabled for one source logic."""
        out = {}
        if sml is None:
            return out
        try:
            dests = sml.getDestinationList()
            if dests is None or dests.isEmpty():
                return out
            it = dests.iterator()
            while it.hasNext():
                dest = it.next()
                try:
                    key = dest.getSystemName()
                    out[key] = bool(sml.isEnabled(dest))
                except Exception:
                    continue
        except Exception:
            return out
        return out

    def _field_owns_mast(self, mast):
        """Field owns heads when global SML is off or this source was unchecked."""
        if mast is None:
            return False
        if not self._global_enabled:
            return True
        if self._source_field_owned.get(mast):
            return True
        return not self._mast_logic_enabled(mast)

    def _publish_unheld(self, head):
        if head is None:
            return
        sys_name = head.getSystemName()
        if sys_name not in self.mqtt_wanted:
            return
        topic = TOPIC_PREFIX + _topic_suffix(sys_name)
        prev = self._last_mqtt_appearance.get(sys_name)
        if prev == "Unheld":
            return
        self._last_mqtt_appearance[sys_name] = "Unheld"
        self._publish(topic, "Unheld", retain=True)

    def _mqtt_heads_on_mast(self, mast):
        heads = []
        hm = _head_manager()
        if hm is None or mast is None:
            return heads
        for sys_name in _head_names_on_mast(mast):
            if sys_name not in self.mqtt_wanted:
                continue
            head = hm.getSignalHead(sys_name)
            if head is not None:
                heads.append(head)
        return heads

    def _hand_source_to_field(self, mast):
        """Uncheck Enable: Unheld this source's heads; field owns until re-enabled."""
        if self._source_field_owned.get(mast):
            return
        self._source_field_owned[mast] = True
        heads = self._mqtt_heads_on_mast(mast)
        if not heads:
            print(
                "mqtt_signalhead: SML dest off %s -- no MQTT heads "
                "(roster=%s)"
                % (
                    _ascii(mast.getDisplayName()),
                    ",".join(sorted(self.mqtt_wanted)),
                )
            )
            return
        for head in heads:
            self._publish_unheld(head)
        print(
            "mqtt_signalhead: SML dest off -> Unheld %s (field owns)"
            % _ascii(mast.getDisplayName())
        )

    def _hand_source_to_sml(self, mast):
        """Re-check Enable: Digicon SET again."""
        self._source_field_owned[mast] = False
        heads = self._mqtt_heads_on_mast(mast)
        for head in heads:
            self._publish_head_set(head, force=True)
        print(
            "mqtt_signalhead: SML dest on -> SET %s (Digicon owns)"
            % _ascii(mast.getDisplayName())
        )

    def _publish_head_set(self, head, force=False):
        if self.mqtt is None or head is None:
            return
        if not self._global_enabled:
            return
        mast = self._mast_for_head(head)
        if self._field_owns_mast(mast):
            return
        sys_name = head.getSystemName()
        if sys_name not in self.mqtt_wanted:
            return
        topic = TOPIC_PREFIX + _topic_suffix(sys_name)
        data = head.getAppearanceName()
        prev = self._last_mqtt_appearance.get(sys_name)
        # Skip unchanged chatter on property churn -- but Enable must always SET
        # so the field/bridge re-applies even if the aspect string is the same.
        if not force and prev is not None and prev == data:
            return
        self._last_mqtt_appearance[sys_name] = data
        # Retain so LCOS bridge can resume Flashing Red / ... after restart
        # (color/Dark toggles stay bridge-local and never appear on MQTT).
        self._publish(topic, data, retain=True)
