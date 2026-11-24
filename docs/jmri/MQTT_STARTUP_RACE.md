# JMRI MQTT startup race

The connection drop at PanelPro start is a bug in stock JMRI 5.16, reproduced on a bare profile with nothing from the layout in it (2026-11-23).

## What happens

`jmri.jmrix.mqtt.MqttAdapter` keeps its subscriptions in a plain `HashMap` (`mqttEventListeners`) with no lock. While `tables.xml` loads, each MQTT sensor and turnout calls `subscribe()`, which adds to that map. At the same time the broker sends the retained message for each topic already subscribed, and Paho's callback thread runs `messageArrived()`, which copies the map (`new HashMap<>(mqttEventListeners)`, source comment "Avoid ConcurrentModificationException"). If a `subscribe()` lands during the copy, the copy throws `ConcurrentModificationException`. The exception leaves `messageArrived()`, so Paho closes the connection. Every `subscribe()` after that logs `ERROR Can't subscribe`, JMRI retries every 500 ms, logs `Succeeded to reconnect` and subscribes to every topic again, which brings the retained states back.

JMRI's `connectionLost()` does not log the cause, so most drops show no `ConcurrentModificationException` in the log at all. It appears only when the first failed `subscribe()` happens to carry it as its cause. An exception recording (Java Flight Recorder, `jdk.JavaExceptionThrow`) shows the same throw at `MqttAdapter.messageArrived` (line 382 in the 5.16 build) for every drop checked.

## The bare setup

`tools/jmri/mqtt_race_repro/run.sh` builds it in a temp folder:

- a private Mosquitto on 127.0.0.1:18830, not the layout broker
- a new JMRI profile with one MQTT connection on stock options and one startup action, loading `tables.xml`; no panels, scripts, Logix, LogixNG, signal logic, CATS or Operations Pro
- a generated `tables.xml` holding only N MQTT sensors and N MQTT turnouts on the stock topics (`track/sensor/<n>`, `track/turnout/<n>`)
- optionally one retained message per bean, set by `retain.py` (Python, 127.0.0.1 only)
- JMRI started with `JmriFaceless` N times, stopped about 15 s after the table load, each `session.log` kept

`JFR=1` adds the exception recording; read it with `jfr print --events jdk.JavaExceptionThrow --stack-depth 20 recN.jfr`.

## Results (Mac, JMRI 5.16, Java 17.0.1, 2026-11-23)

Beans is the total: `run.sh N` makes N sensors and N turnouts, so 2N beans.

| `run.sh` N | Beans | Retained | Starts | Connection dropped | Starts with an exception recording |
|---|---|---|---|---|---|
| 500 | 1000 | yes | 5 | 5 | 2 |
| 500 | 1000 | no | 5 | 0 | 0 |
| 53 | 106 (the layout's MQTT count: 86 sensors, 20 turnouts) | yes | 12 | 11 | 2 |
| 10 | 20 | yes | 5 | 0 | 0 |

All 4 recorded starts dropped, and in each the recording shows the `ConcurrentModificationException` above; the other drops are inferred from the same log pattern. Every start that dropped also logged `Succeeded to reconnect`. Every start in the table loaded `tables.xml`, connected and shut down normally, so the zero rows are real starts, not failed ones.

## What it rules out

The race needs only stock JMRI, many MQTT beans subscribing at load and retained messages for them on the broker. Nothing the layout adds (custom topics, our `tables.xml`, scripts, panels) is needed. Without retained messages it did not happen. At 20 beans it did not happen in 5 starts; a shorter load window is the likely reason, not checked.

Why the new Pi card shows it more often than the old one is not measured; a faster CPU or Java 21 changing the timing is a guess.

## Next

A standalone test against `MqttAdapter`, then a JMRI issue and pull request. Possible fixes: a `ConcurrentHashMap` (or a synchronized copy) for `mqttEventListeners`, and catching exceptions inside `messageArrived()` so one bad delivery cannot close the connection.
