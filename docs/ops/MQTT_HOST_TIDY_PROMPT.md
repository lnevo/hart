# Prompt: MQTT host tidy-ups

Hand-off for the code tidy-ups left over from the 2026-11-11 network change (PRs #320–#325). Paste the block below into a new session.

```text
Tidy the MQTT host settings in the HART repo. Read AGENTS.md and wiki/STATUS.md first,
and start with `make wt TOPIC=mqtt-host-tidy`.

Background: since 2026-11-11 Mosquitto runs on the Pi. The Pi itself uses 127.0.0.1;
everything else uses 10.0.0.150. minipc-e5h6x.local is the Windows box, never the broker.

1. One broker setting for the Mac tools. tools/env/hart.env.example documents
   HART_MQTT_BROKER, but the Python tools read MQTT_HOST or HART_MQTT_HOST, and each
   repeats 10.0.0.150 as a literal default:
     jmri/layouts/hart/scripts/seed_default_thrown_turnouts.py
     tools/mqtt/sync_mqtt_turnouts_from_fb.py
     tools/mqtt/clear_mqtt_cmd_sensor_retain.py
     tools/mqtt-mimic/lcos_mqtt_mimic.py (pick_mqtt_host)
     tools/mqtt-mimic/sim_hart_train_mqtt.py
     tools/mqtt-mimic/qa/run_native_sml_qa.py (HOST constant, no override at all)
   Pick one name (HART_MQTT_BROKER, with MQTT_HOST still honoured), read it in one small
   shared helper, keep 10.0.0.150 as the single default, and update the env example
   and docs. The JMRI JSON URLs (http://10.0.0.150:12080) in the same scripts get the
   same treatment.

2. Mimic page duplication. jmri/resources/jmri-web/mimic/index.html copies the CSS and
   render() from tools/mqtt-mimic/lcos_mqtt_mimic.html; only the transport differs
   (JMRI JSON WebSocket + mimic_relay.py versus the Mac server's /api). Share the markup,
   style and render code, keep the two transports separate, and keep
   tools/mqtt-mimic/tests/test_mimic_web.py passing (the page may only build
   track/sensor and track/turnout topics and may post only the IMHART_MIMIC memory).

Rules: no MQTT publishes from tests (example.invalid host, as the existing tests do).
Do not touch external/lcos-bridge/lcos/. Run ./tools/check.sh, and /code-review medium
before merging. This is Mac tooling and a web page: no PanelPro test. Deploy to the Pi
(sync_hart_package.sh --pi) only if the mimic page changed.
```
