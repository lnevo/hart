"""Broker and JMRI addresses for the Mac tools: one setting each, one default.

The Pi runs Mosquitto and JMRI. On the Pi itself the broker is 127.0.0.1;
set HART_MQTT_BROKER there. The Windows box is never the broker.

Lookup order, first set wins:
  broker     HART_MQTT_BROKER, MQTT_HOST or HART_MQTT_HOST (older names), tools/env/hart.env
  port       HART_MQTT_PORT, tools/env/hart.env
  JMRI JSON  HART_JMRI_JSON, JMRI_JSON (older name), tools/env/hart.env
then the default in tools/env/defaults.env, which load_env.sh reads as well.

Any name set in the environment beats hart.env, old names included, so a one-off
`MQTT_HOST=... python3 ...` still works; a stale exported MQTT_HOST also wins, so unset it.
hart.env is found as load_env.sh finds it: HART_ENV_FILE, else HART_REPO_ROOT/tools/env/hart.env.
"""
from __future__ import annotations

import functools
import os
import re
from pathlib import Path
from typing import Mapping

DEFAULTS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "env" / "defaults.env"

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
    # Not hartlib.paths: hosts must import even where there is no full checkout around it.
    up = Path(__file__).resolve().parents  # src/hartlib/hosts.py -> repo is up[4]
    base = Path(root).expanduser() if root else up[min(4, len(up) - 1)]
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


@functools.lru_cache(maxsize=1)
def _defaults() -> dict[str, str]:
    """tools/env/defaults.env, the one copy of the defaults load_env.sh also reads."""
    values = read_env_file(DEFAULTS_FILE)
    if not values:
        raise SystemExit(f"hartlib.hosts: cannot read the host defaults in {DEFAULTS_FILE}")
    return dict(values)


def default(name: str) -> str:
    """The defaults.env value for NAME; stops with a clear message when it has none."""
    value = _defaults().get(name, "")
    if not value:
        raise SystemExit(f"hartlib.hosts: {name} has no default in {DEFAULTS_FILE}")
    return value


def _lookup(names: tuple[str, ...], default_name: str, env: Mapping[str, str] | None,
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
    return default(default_name)


def mqtt_broker(env: Mapping[str, str] | None = None,
                file_values: Mapping[str, str] | None = None) -> str:
    return _lookup(BROKER_VARS, "HART_MQTT_BROKER", env, file_values)


def mqtt_port(env: Mapping[str, str] | None = None,
              file_values: Mapping[str, str] | None = None) -> int:
    raw = _lookup(PORT_VARS, "HART_MQTT_PORT", env, file_values)
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(f"HART_MQTT_PORT must be a number, not {raw!r}") from exc


def jmri_json_url(env: Mapping[str, str] | None = None,
                  file_values: Mapping[str, str] | None = None) -> str:
    """JMRI JSON base URL without a trailing slash, e.g. http://<pi>:12080/json."""
    return _lookup(JMRI_JSON_VARS, "HART_JMRI_JSON", env, file_values).rstrip("/")
