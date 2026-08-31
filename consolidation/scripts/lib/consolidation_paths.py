"""Path resolver for consolidation workspace — prefer local mirrors over live repo."""
from __future__ import annotations

import os
from pathlib import Path


def consolidation_root() -> Path:
    return Path(__file__).resolve().parents[2]


def hart_repo_root() -> Path:
    return consolidation_root().parent


def hart_runtime_root() -> Path:
    """Standalone layout ops tree under external/hart-runtime/."""
    runtime = consolidation_root() / "external/hart-runtime"
    if (runtime / "jmri/layout_paths.py").is_file():
        return runtime
    return hart_repo_root()


def desktop_data_root() -> Path:
    return consolidation_root() / "external/desktop-data"


def car_images_final() -> Path:
    env = os.environ.get("HART_CAR_IMAGES_FINAL", "").strip()
    if env:
        return Path(env).expanduser()
    local = desktop_data_root() / "car-images/CarImagesFinal"
    if local.is_dir():
        return local
    return Path.home() / "Desktop/HART/Car Cards/CarImagesFinal"


def rel(repo: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return str(path)


def path_public_name_map() -> Path:
    snap = consolidation_root() / "sor/names/public_name_map.csv"
    if snap.is_file():
        return snap
    return hart_runtime_root() / "jmri/layouts/hart/data/public_name_map.csv"


def path_block_display_names() -> Path:
    snap = consolidation_root() / "sor/names/block_display_names.csv"
    if snap.is_file():
        return snap
    return hart_runtime_root() / "jmri/layouts/hart/data/block_display_names.csv"


def path_tables_xml() -> Path:
    return hart_runtime_root() / "jmri/layouts/hart/output/tables.xml"


def path_hart_prod_xml() -> Path:
    return hart_runtime_root() / "jmri/layouts/hart/output/hart_prod.xml"


def path_signal_wiring() -> Path:
    snap = consolidation_root() / "sor/signals/signal_wiring.csv"
    if snap.is_file():
        return snap
    return hart_runtime_root() / "cats/data/signal_wiring.csv"


def path_lcos_bridge() -> Path:
    sub = consolidation_root() / "external/lcos-bridge"
    if (sub / "serial_to_mqtt.py").is_file():
        return sub
    sibling = hart_repo_root().parent / "LCOS_ESP32_MQTT_Client"
    return sibling if sibling.is_dir() else sub
