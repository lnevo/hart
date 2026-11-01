# CATS overlay review

What the removed `cats-pts-nullguard.jar` changed, compared with the stock CATS 3.2 `cats.jar` on 2026-10-31. CATS has run stock since then. Use this list to decide what to report upstream and what to compensate for.

The `PatchCatsMqttLoad.java` source never covered the whole jar. The jar and sources are in git at `443b5f28`, under `tools/cats/patches/`.

| Change | In the source? | What it did | Effect on stock | Next step |
|---|---|---|---|---|
| `RREventManager.consume` catches everything | Yes | Keeps the event thread alive | One bad event ends the thread and freezes occupancy and control until restart | Report upstream; first priority |
| `PtsVitalLogic.setSelectedTrack` defers and guards nulls | Yes | Ignores a route until its frogs and lock processors exist | The NPE that kills the thread; reproduced 2026-10-31 | Report upstream with the stack trace |
| `SwitchPoints.syncLastRouteFromFeedback`, called from `acceptMakeEvent` | No | Updates `LastRoute` from field feedback | `LastRoute` follows CATS commands only, so **Refresh Layout** can command points back to a stale route, moving a turnout that was thrown in the field | Verify on the bench, then report upstream. Never use Refresh Layout |
| `DeviceMonitor.linkUp` calls `refreshListener` | No | Reads JMRI state as each device links | CATS does not read device state at link time, so a turnout may paint wrong until it reports | Compensate: Appearance → Refresh Screen after start. Possible upstream enhancement |
| `HartMqttRefresh` from `Screen` | Yes, source only | Repeats Refresh Screen nine times over 60 seconds | No automatic refresh | Compensate as above. HART-specific; do not send upstream |
| `RouteInfo.sendFeedback` null check | Yes | Ignores feedback before `VitalLogic` is set | NPE on the same thread | Report with the thread bug |
| `PtsEdge.isLocalControlAllowed` null check | Yes | Allows local control when `MyBlock` is unset | NPE on a turnout with no block | Find out whether any HART turnout has no block; a panel fix would be better |
| `PtsEdge.handleFieldAction` catches everything around `changeLinkages` | No | Hides an unknown failure | Original failure unknown | Do not promote. Investigate only if it appears on stock |
| `DeviceMonitor.refreshListener` null check, `refreshScreen` per-device catch | No | One unlinked device cannot stop a refresh | Refresh Screen can abort partway | Report if it appears on stock |
