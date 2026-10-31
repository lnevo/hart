# Agent skills and MCPs

- **Owner:** lnevo
- **Status:** Done
- **Repo:** [lnevo/model-railroad-skills](https://github.com/lnevo/model-railroad-skills), at `external/model-railroad-skills`

A public Claude Code plugin for any JMRI user. It holds nothing specific to this railroad, and no bridge or custom MQTT methods.

| Type | Items |
|---|---|
| Skills | `jmri-panel-xml`, `jmri-sml-nx`, `jmri-dispatcher-system`, `jmri-mqtt-layout`, `cats-on-jmri`, `sts-docker` |
| Read-only MCPs | `jmri-json`, `mqtt-layout` |

Each rule was confirmed in JMRI, CATS or STS source. Rules that could only be supported from this railroad were left out.

## Rules for adding to it

1. Check every rule against source, and record the commit.
2. Keep every MCP read-only unless the owner decides otherwise.
3. Scan for railroad names before publishing. This repo stays the home for railroad-specific lessons.

## Dropped from the 2026-09-14 inventory

The other skills and MCPs are dropped unless a job needs one. Do not build MCPs for serial ports, CATS, Arduino flashing, WiThrottle or deploys.

## Open

- `jmri-json` has been tested against a stub, and needs a run against live PanelPro.
- `mqtt-layout` has been tested against a local broker, and needs a run against the layout broker.
