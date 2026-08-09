# CATS load safety overlay

Stock `release3.2/cats.jar` NPEs in `PtsVitalLogic.setSelectedTrack` when
turnout `SELECTEDREPORT` arrives before lock processors exist. That uncaught
exception kills `RREventManager` and freezes occupancy.

`cats-pts-nullguard.jar` is the last known-good overlay that keeps the event
queue alive. `install_into_jmri.sh` copies stock, then overlays this jar.

Do not clear/publish MQTT from launch to paper over the race.
