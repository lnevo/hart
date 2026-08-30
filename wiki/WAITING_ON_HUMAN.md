# Waiting on you

**Cleared 2026-08-07** — decisions locked in ADR-004:

| Question | Answer |
|----------|--------|
| JMRI version | Current host build (**5.15.4plus** in hart panel; CATS 3.2 OK) |
| Who throws switches in CTC | **CATS** |
| First plant | **Brick** |

## Your next hands-on step

1. JMRI up → load `jmri/layouts/hart/output/hart_prod.xml`
2. `./cats/scripts/launch_cats.sh` (or Designer to polish topology)
3. File → Open `cats/panels/HART_Brick.xml`
4. Test OS 100 / Switch 100 per `cats/docs/BRICK_BINDINGS.md`

If Designer rejects MQTT manager class names, re-bind devices in the Designer tables UI using the CSVs — keep the same user names.
