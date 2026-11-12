"""Broker and JMRI addresses for the Mac tools: one setting each, one default.

The Pi runs Mosquitto and JMRI (10.0.0.150). On the Pi itself the broker is 127.0.0.1;
set HART_MQTT_BROKER there. minipc-e5h6x.local is the Windows box, never the broker.

Lookup order, first set wins:
  broker     HART_MQTT_BROKER, MQTT_HOST or HART_MQTT_HOST (older names), tools/env/hart.env
  port       HART_MQTT_PORT, tools/env/hart.env, 1883
  JMRI JSON  HART_JMRI_JSON, JMRI_JSON (older name), tools/env/hart.env

Any name set in the environment beats hart.env, old names included, so a one-off
`MQTT_HOST=... python3 ...` still works; a stale exported MQTT_HOST also wins, so unset it.
hart.env is found as load_env.sh finds it: HART_ENV_FILE, else HART_REPO_ROOT/tools/env/hart.env.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

PI_HOST = "10.0.0.150"
DEFAULT_BROKER = PI_HOST
DEFAULT_PORT = 1883
DEFAULT_JMRI_JSON = f"http://{PI_HOST}:12080/json"

BROKER_VARS = ("HART_MQTT_BROKER", "MQTT_HOST", "HART_MQTT_HOST")
PORT_VARS = ("HART_MQTT_PORT",)
JMRI_JSON_VARS = ("HART_JMRI_JSON", "JMRI_JSON")

_VAR = re.compile(r"\$(?:\{(\w+)\}|(\w+))")


def env_file_path() -> Path:
    """HART_ENV_FILE, else <HART_REPO_ROOT or this repo>/tools/env/hart.env, as load_env.sh finds it."""
    override = os.environ.get("HART_ENV_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    root = os.environ.get("HART_REPO_ROOT", "").strip()
    base = Path(root).expanduser() if root else Path(__file__).resolve().parents[3]
    return base / "tools" / "env" / "hart.env"


def _value(raw: str, known: Mapping[str, str]) -> str:
    """One shell-style value: quotes kept whole, ' #' comments dropped, $VAR expanded."""
    raw = raw.strip()
    if raw[:1] in ("'", '"') and raw[0] in raw[1:]:
        quote = raw[0]
        value = raw[1:raw.index(quote, 1)]
        if quote == "'":
            return value
    else:
        value = re.split(r"\s#", raw, maxsplit=1)[0].strip()
    return _VAR.sub(lambda m: known.get(m.group(1) or m.group(2), ""), value)


def read_env_file(path: Path | None = None) -> dict[str, str]:
    """KEY=VALUE lines from hart.env, read like `source` would. Missing file: {}."""
    try:
        text = (path or env_file_path()).read_text(encoding="utf-8")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        if not key.isidentifier():
            continue
        value = _value(raw, {**os.environ, **values})
        if value:
            values[key] = value
    return values


def _lookup(names: tuple[str, ...], default: str, env: Mapping[str, str] | None,
            file_values: Mapping[str, str] | None) -> str:
    env = os.environ if env is None else env
    for name in names:
        value = (env.get(name) or "").strip()
        if value:
            return value
    file_values = read_env_file() if file_values is None else file_values
    for name in names:
        value = (file_values.get(name) or "").strip()
        if value:
            return value
    return default


def mqtt_broker(env: Mapping[str, str] | None = None,
                file_values: Mapping[str, str] | None = None) -> str:
    return _lookup(BROKER_VARS, DEFAULT_BROKER, env, file_values)


def mqtt_port(env: Mapping[str, str] | None = None,
              file_values: Mapping[str, str] | None = None) -> int:
    raw = _lookup(PORT_VARS, str(DEFAULT_PORT), env, file_values)
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"HART_MQTT_PORT must be a number, not {raw!r}") from None


def jmri_json_url(env: Mapping[str, str] | None = None,
                  file_values: Mapping[str, str] | None = None) -> str:
    """JMRI JSON base URL without a trailing slash, e.g. http://10.0.0.150:12080/json."""
    return _lookup(JMRI_JSON_VARS, DEFAULT_JMRI_JSON, env, file_values).rstrip("/")
