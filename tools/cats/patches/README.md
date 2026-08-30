# CATS load safety overlay

Stock `release3.2/cats.jar` NPEs in `PtsVitalLogic.setSelectedTrack` when
turnout `SELECTEDREPORT` arrives before lock processors exist. That uncaught
exception kills `RREventManager` and freezes occupancy.

`cats-pts-nullguard.jar` is a **javassist** overlay of a few classes (see
`PatchCatsMqttLoad.java`). It is not a decompiled CATS tree. Application
source is [Kb0oys/cats](https://bitbucket.org/Kb0oys/cats/src/master/) —
`./tools/cats/fetch_cats_src.sh`.

`install_into_jmri.sh` copies stock, then overlays this jar.

Do not clear/publish MQTT from launch to paper over the race.
