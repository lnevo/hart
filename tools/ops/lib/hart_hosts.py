"""Shim: broker and JMRI addresses moved to ``hartlib.hosts`` (tools/hartlib).

Kept so scripts that put tools/ops/lib on sys.path keep working; new code imports
``from hartlib import hosts`` (tools/hartlib/README.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[2] / "hartlib" / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from hartlib.hosts import (  # noqa: E402,F401
    BROKER_VARS,
    DEFAULT_BROKER,
    DEFAULT_JMRI_JSON,
    DEFAULT_PORT,
    JMRI_JSON_VARS,
    PI_HOST,
    PORT_VARS,
    env_file_path,
    jmri_json_url,
    mqtt_broker,
    mqtt_port,
    read_env_file,
)
