# JMRI jython -- part of signal_coordinator.py: what the controller hears and says on MQTT (the
# subscriptions, the roster from track/signalmast and its reports painted on the heads and masts,
# sml_mode and sml_claim in and out) and its answer to an SML dest Enabled checkbox change.
#
# signal_coordinator.py loads this from preference:jython last, after sml_handoff, and reloads it on every
# run (jython_siblings.py). notifyMqttMessage and propertyChange stay in the script (the Java listener
# methods JMRI calls), and _should_ack_sml_alive beside them.

from sml_beans import (
    MAST_TOPIC_PREFIX,
    SML_CLAIM_TOPIC,
    SML_MODE_TOPIC,
    TOPIC_PREFIX,
    _ASPECT_TO_APPEARANCE,
    _appearance_constant,
    _ascii,
    _head_manager,
    _packed_is_lcos_signal,
)
from sml_claims import _parse_claim


class SmlEvents(object):
    """DigiconMqttSml's MQTT subscriptions, publishes and sml_mode / sml_claim answers."""

    def _subscribe_mqtt(self):
        try:
            self.mqtt.subscribe(SML_MODE_TOPIC, self)
            self.mqtt.subscribe(SML_CLAIM_TOPIC, self)
            # signalmast first (roster + paint). signalhead is SET/Unheld; do not enroll.
            self.mqtt.subscribe(MAST_TOPIC_PREFIX + "#", self)
            self.mqtt.subscribe(TOPIC_PREFIX + "#", self)
        except Exception as exc:
            print("mqtt_signalhead: MQTT subscribe failed: " + _ascii(exc))

    def _enroll_packed(self, packed):
        """Add packed disc to MQTT roster from track/signalmast (not signalhead)."""
        packed = str(packed).strip()
        if not _packed_is_lcos_signal(packed):
            return
        sys_name = "IH" + packed
        if sys_name in self.mqtt_wanted:
            return
        hm = _head_manager()
        if hm is None:
            return
        head = hm.getSignalHead(sys_name)
        if head is None:
            print(
                "mqtt_signalhead: skip enroll %s (no IH bean)"
                % _ascii(sys_name)
            )
            return
        self.mqtt_wanted.add(sys_name)
        if head not in self._heads:
            self._heads.append(head)
            try:
                head.addPropertyChangeListener(self)
            except Exception as exc:
                print(
                    "mqtt_signalhead: listener %s: %s"
                    % (_ascii(sys_name), _ascii(exc))
                )
        print("mqtt_signalhead: enrolled %s from signalmast" % _ascii(sys_name))
        if self._global_enabled:
            self._publish_head_set(head)

    def _publish(self, topic, payload, retain=False):
        if self.mqtt is None:
            return
        try:
            # Always name the retain flag: JMRI's two-argument MqttAdapter.publish(topic, data)
            # retains (its `retained` field defaults to true), so it cannot send a plain message.
            # The three-argument form needs JMRI 5.9.1 or later (hosts run 5.16); on an older
            # JMRI this raises and is printed below, with no two-argument fallback.
            self.mqtt.publish(topic, payload, bool(retain))
        except Exception as exc:
            print(
                "mqtt_signalhead: publish failed %s %s: %s"
                % (_ascii(topic), _ascii(payload), _ascii(exc))
            )

    def _publish_mode(self, mode):
        """Retained sml_mode word; enabling / enabled then this host's claim.

        The word goes first: a host that hears it while idle stands back before the
        claim reaches it, and one already claiming compares the claim.
        """
        claim = self._claim
        if mode in ("enabling", "enabled") and claim is None:
            # Lost or aborted on another thread just now: nothing to announce.
            print("mqtt_signalhead: no claim -- %s not sent" % mode)
            return
        self._retained_mode = mode
        self._publish(SML_MODE_TOPIC, mode, retain=True)
        if mode not in ("enabling", "enabled"):
            return
        stamp, force = claim
        payload = "%s %s %d" % (mode, self._host, stamp)
        if force:
            # On enabled too: both hosts must rank an owner with the same key.
            payload += " force"
        self._retained_host = self._host
        self._publish(SML_CLAIM_TOPIC, payload, retain=True)

    def _on_sml_claim(self, message):
        """A claim from track/bridge/sml_claim (this host's own echo included)."""
        mode, host, stamp, force = _parse_claim(message)
        if mode not in ("enabling", "enabled") or stamp is None:
            print("mqtt_signalhead: sml_claim %r not understood -- ignored" % message)
            return
        with self._claim_lock:
            # The last claim on the broker; read at boot with the retained mode.
            self._retained_host = host
            if self._is_own_claim(host, stamp):
                return
            if self._claim is not None:
                self._resolve_claim_race(mode, host, stamp, force)

    def _on_sml_mode(self, message):
        words = message.split()
        mode = words[0].lower() if words else ""
        with self._claim_lock:
            self._on_sml_mode_locked(mode)

    def _on_sml_mode_locked(self, mode):
        bridge_release = mode == "disabled" and self._bridge_release_pending
        if mode == "disabling":
            self._bridge_release_pending = True
        elif mode in ("enabled", "enabling", "aborting", "aborted", "disabled"):
            self._bridge_release_pending = False
        if mode == "enabled" and self._probe_active:
            self._probe_saw_enabled = True
        if mode in (
            "enabled",
            "disabled",
            "query",
            "disabling",
            "enabling",
            "aborting",
            "aborted",
        ):
            # Do not let our probe query wipe a known enabled retain for the fast path.
            if not (self._probe_active and mode == "query"):
                self._retained_mode = mode
        if mode in ("enabling", "enabled") and self._claim is not None:
            # Claiming or owning: this host's own echo, or a rival whose claim follows
            # on sml_claim and is compared there.
            if mode == "enabling" and self._enabling_originator:
                print(
                    "mqtt_signalhead: own enabling -- leave SML, wait to announce enabled"
                )
            return
        if mode == "enabling":
            print("mqtt_signalhead: saw enabling -- abort SML")
            self._abort_sml_immediate()
            return
        # Live Digicon: answer query and disabling so the LCOS bridge can abort RELEASE.
        # ACK while owning or taking (Hold included). Do not ACK our Enable probe
        # or during abort (unchecked, not yet re-enabled).
        if mode in ("query", "disabling") and self._should_ack_sml_alive():
            self._publish_mode("enabled")
            print("mqtt_signalhead: ACK %s -> enabled" % mode)
            return
        # The bridge found nobody owning a retained enabled (query, disabling, then
        # disabled): e.g. a stale retain after a power cut made this host stay Disabled
        # at boot. Take the boot decision again. An operator Disable on another host
        # publishes disabled alone, and stays as the operator set it.
        if bridge_release and self._idle_for_take():
            print("mqtt_signalhead: bridge released sml_mode -- take Digicon (enable)")
            self._enter_enabled(force=True, from_boot=True)

    def _idle_for_take(self):
        """Not owning, taking, aborting, booting or quitting Digicon."""
        return not (
            self._is_busy()
            or self._boot_pending
            or self._shutting_down
            or self._global_enabled
            or self._enabling_originator
            or self._owns_digicon_now()
        )

    def _on_sml_property(self, sml):
        # Global button / boot bulk setDisabled owns Unheld.
        if self._is_busy() or self._boot_pending:
            return
        if not self._global_enabled:
            return
        try:
            mast = sml.getSourceMast()
        except Exception:
            return
        if mast not in self._masts:
            return
        now_map = self._dest_enable_map(sml)
        was_map = self._dest_enable_maps.get(sml) or {}
        self._dest_enable_maps[sml] = now_map
        self._mast_sml_was_enabled[mast] = any(now_map.values())
        if not was_map:
            return
        disabled = []
        enabled = []
        keys = set(now_map.keys()) | set(was_map.keys())
        for dest in keys:
            now_on = now_map.get(dest)
            was_on = was_map.get(dest)
            if was_on is None or now_on is None:
                continue
            if was_on and not now_on:
                disabled.append(dest)
            elif (not was_on) and now_on:
                enabled.append(dest)
        if disabled:
            print(
                "mqtt_signalhead: dest Enabled off %s -> %s"
                % (_ascii(mast.getDisplayName()), _ascii(disabled[0]))
            )
            self._hand_source_to_field(mast)
            return
        if enabled:
            print(
                "mqtt_signalhead: dest Enabled on %s -> %s"
                % (_ascii(mast.getDisplayName()), _ascii(enabled[0]))
            )
            self._hand_source_to_sml(mast)

    def _apply_mast_payload_to_head(self, packed, payload):
        """track/signalmast/<packed> -> IH heads + source SignalMast when field owns."""
        sys_name = "IH" + str(packed)
        if sys_name not in self.mqtt_wanted:
            return
        mast = self._head_to_mast.get(sys_name)
        if self._global_enabled and not self._field_owns_mast(mast):
            return
        parts = [p.strip() for p in str(payload).split(";") if p.strip()]
        if not parts:
            return
        aspect = parts[0]
        head = _head_manager().getSignalHead(sys_name)
        if head is not None:
            mapped = _ASPECT_TO_APPEARANCE.get(aspect.lower())
            if mapped is None:
                mapped = aspect
            const = _appearance_constant(mapped)
            if const is not None:
                try:
                    if head.getAppearance() != const:
                        head.setAppearance(const)
                except Exception as exc:
                    print(
                        "mqtt_signalhead: setAppearance %s %s: %s"
                        % (_ascii(sys_name), _ascii(mapped), _ascii(exc))
                    )
        if mast is None:
            return
        mast_aspect = aspect
        if aspect.lower() in _ASPECT_TO_APPEARANCE:
            appearance = _ASPECT_TO_APPEARANCE[aspect.lower()]
            mast_aspect = {
                "Red": "Stop",
                "Yellow": "Approach",
                "Green": "Clear",
                "Dark": "Dark",
            }.get(appearance, aspect)
        try:
            current = None
            try:
                current = mast.getAspect()
            except Exception:
                pass
            if current != mast_aspect:
                mast.setAspect(mast_aspect)
        except Exception as exc:
            print(
                "mqtt_signalhead: setAspect %s %s: %s"
                % (_ascii(mast.getDisplayName()), _ascii(mast_aspect), _ascii(exc))
            )
        for token in parts[1:]:
            low = token.lower()
            try:
                if low == "lit":
                    mast.setLit(True)
                elif low == "unlit":
                    mast.setLit(False)
                elif low == "held":
                    mast.setHeld(True)
                elif low == "unheld":
                    mast.setHeld(False)
            except Exception:
                pass
