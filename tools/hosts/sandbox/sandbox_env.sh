#!/usr/bin/env bash
# Environment for a sandbox PanelPro run: a copy of the live profile with its own user files and MQTT on a local
# broker, so nothing reaches the layout. Source it with HART_SANDBOX set to the sandbox folder (see README.md).
: "${HART_SANDBOX:?set HART_SANDBOX to the sandbox folder}"
export JMRI_PROFILE="$HART_SANDBOX/HARTSandbox.jmri"
export JMRI_PROFILE_XML="$JMRI_PROFILE/profile/profile.xml"
export JMRI_USER_FILES="$HART_SANDBOX/uf/"
RUN="${HART_SANDBOX_RUN:-$HART_SANDBOX/run}"
mkdir -p "$RUN"
export HART_PANELPRO_SMOKE_MARKER="$RUN/smoke.done" HART_PANELPRO_SMOKE_LOG="$RUN/smoke_panelpro.log"
export HART_STAGE1_MARKER="$RUN/stage1.done" HART_STAGE1_LOG="$RUN/stage1_panelpro.log"
export HART_NX_DISCOVER_MARKER="$RUN/nx.done" HART_NX_DISCOVER_LOG="$RUN/nx_panelpro.log"
unset HART_TABLES
