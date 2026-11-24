# JMRI MQTT startup race

The connection drop at PanelPro start is a bug in stock JMRI 5.16, reproduced on a bare profile with nothing from the layout in it, on macOS and Linux and with four brokers (2026-11-23). JMRI tried to fix it in 2021; 5.17.5 and 5.19.1 have the same code.

## What happens

`jmri.jmrix.mqtt.MqttAdapter` keeps its subscriptions in a plain `HashMap` (`mqttEventListeners`) with no lock. While `tables.xml` loads, each MQTT sensor and turnout calls `subscribe()`, which adds to that map. At the same time the broker sends the retained message for each topic already subscribed, and Paho's callback thread runs `messageArrived()`, which copies the map (`new HashMap<>(mqttEventListeners)`, source comment "Avoid ConcurrentModificationException"). If a `subscribe()` lands during the copy, the copy throws `ConcurrentModificationException`. The exception leaves `messageArrived()`, so Paho closes the connection. Every `subscribe()` after that logs `ERROR Can't subscribe`, JMRI retries every 500 ms, logs `Succeeded to reconnect` and subscribes to every topic again, which brings the retained states back.

JMRI's `connectionLost()` does not log the cause, so most drops show no `ConcurrentModificationException` in the log at all. It appears only when the first failed `subscribe()` happens to carry it as its cause. An exception recording (Java Flight Recorder, `jdk.JavaExceptionThrow`) shows the same throw at `MqttAdapter.messageArrived` (line 382 in the 5.16 build) for every drop checked on the Mac.

The same race has a second symptom. In 2 of the 9 Linux drops the recording shows no `ConcurrentModificationException`; instead `messageArrived()` threw `No subscriber for MQTT topic track/turnout/42` (line 401) for a topic that had been added to the map before it was subscribed. The likely reading is that the unlocked copy missed that entry without failing; that is inferred from the code, not traced. The exception closes the connection the same way.

## Upstream history

JMRI pull request [#10280](https://github.com/JMRI/JMRI/pull/10280), "Mqtt concurrency fix" (merged 2021-11-10), added the copy: "Cache an iteration list to avoid ConcurrentModificationException during startup." Copying a `HashMap` iterates it, so the copy can still fail while another thread adds to it. `MqttAdapter.java` in 5.17.5 is identical to 5.16; 5.19.1 changes only payload encoding (UTF-8). No JMRI issue for the remaining race was found on 2026-11-23.

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

## Other systems and brokers (2026-11-23)

Same bare setup, N=53 (106 beans), retained messages on, 10 starts each.

| OS | Java | Broker | Connection dropped |
|---|---|---|---|
| macOS (arm64) | 17.0.1 | EMQX 5.8.6 (Docker) | 10 |
| macOS (arm64) | 17.0.1 | HiveMQ CE (Docker) | 9 |
| macOS (arm64) | 17.0.1 | NanoMQ 0.23.10 (Docker) | 1 |
| Linux (Ubuntu 24.04 in WSL2, x86_64) | 21.0.13.1 | Mosquitto 2.0.18, same machine | 9 |
| Windows 11 (x86_64) | 21.0.11 | Mosquitto 2.0.18 in WSL2, through its network bridge | 0 |

The Linux starts all ran with the exception recording: 7 drops show the `ConcurrentModificationException`, 2 the missing-subscriber exception. The Docker rows and the Windows row had no recording; in the Docker rows 19 of the 20 drops logged the `ConcurrentModificationException` directly. The Windows row is not a clean test: its broker sat behind the WSL2 network bridge, not on the same machine, which changes the timing, and the run stopped there once the upstream history settled the question. How often each broker hits it depends on how fast it returns retained messages, which was not measured. EMQX holds retained messages but does not send them to a bare `#` subscription, so `retain.py` also subscribes to `track/#` when counting.

## What it rules out

The race needs only stock JMRI, many MQTT beans subscribing at load and retained messages for them on the broker. Nothing the layout adds (custom topics, our `tables.xml`, scripts, panels) is needed. Without retained messages it did not happen. At 20 beans it did not happen in 5 starts; a shorter load window is the likely reason, not checked.

Why the new Pi card shows it more often than the old one is not measured; a faster CPU or Java 21 changing the timing is a guess.

## Next

The reproduction stopped at the owner's word (2026-11-23): the bug is in JMRI and an earlier fix for it is on record. Next is a JMRI issue citing #10280 and these results, and a pull request. Possible fixes: a `ConcurrentHashMap` (or a synchronized copy) for `mqttEventListeners`, and catching exceptions inside `messageArrived()` so one bad delivery cannot close the connection.
