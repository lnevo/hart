"""Repo path resolver for tools; live data is read from the repo."""
from __future__ import annotations

import os
from pathlib import Path


def hart_repo_root() -> Path:
    env = os.environ.get("HART_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def hart_runtime_root() -> Path:
    env = os.environ.get("HART_RUNTIME_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return hart_repo_root()


def hart_ops_root() -> Path:
    env = os.environ.get("HART_OPS_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return hart_repo_root() / "external/hart-ops"


def sts_docker_root() -> Path:
    env = os.environ.get("STS_DOCKER_ROOT", os.environ.get("STS_DOCKER", "")).strip()
    if env:
        return Path(env).expanduser().resolve()
    return hart_repo_root() / "external/sts-docker"


def sts_helpers_root() -> Path:
    env = os.environ.get("STS_HELPERS_ROOT", os.environ.get("HART_STS_HELPERS", "")).strip()
    if env:
        return Path(env).expanduser().resolve()
    return hart_repo_root() / "external/sts-helpers"


def sts_data_root() -> Path:
    env = os.environ.get("STS_DATA_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return hart_repo_root() / "external/sts-docker-data"


def sts_backups_dir() -> Path:
    env = os.environ.get("STS_BACKUPS_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return sts_data_root() / "backups"


def sts_database_dir() -> Path:
    env = os.environ.get("STS_DATABASE_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return sts_data_root() / "database"


def sts_images_dir() -> Path:
    env = os.environ.get("STS_IMAGES_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return sts_data_root() / "images"


def mirror_hart_src() -> Path:
    env = os.environ.get("HART_MIRROR_SRC", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return hart_repo_root()


def mirror_desktop_hart() -> Path:
    env = os.environ.get("DESKTOP_HART", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / "Desktop/HART"


def car_images_final() -> Path:
    env = os.environ.get("HART_CAR_IMAGES_FINAL", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    local = hart_repo_root() / "ops/car-cards/car-images/CarImagesFinal"
    if local.is_dir():
        return local
    return mirror_desktop_hart() / "Car Cards/CarImagesFinal"


def car_cards_root() -> Path:
    env = os.environ.get("HART_CAR_CARDS_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return hart_repo_root() / "ops/car-cards"


def sts_compose_files() -> list[Path]:
    return [sts_docker_root() / "docker-compose.yml"]


def sts_docker_env_file() -> Path | None:
    """Legacy — compose uses literal paths; no .env required."""
    return None


def rel(repo: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return str(path)


def path_public_name_map() -> Path:
    return hart_runtime_root() / "jmri/layouts/hart/data/public_name_map.csv"


def path_block_display_names() -> Path:
    return hart_runtime_root() / "jmri/layouts/hart/data/block_display_names.csv"


def path_tables_xml() -> Path:
    return hart_runtime_root() / "jmri/layouts/hart/output/tables.xml"


def path_hart_prod_xml() -> Path:
    return hart_runtime_root() / "jmri/layouts/hart/output/tables.xml"


def path_signal_wiring() -> Path:
    return hart_runtime_root() / "docs/wiring/signals/signal_wiring.csv"


def path_lcos_bridge() -> Path:
    sub = hart_repo_root() / "external/lcos-bridge"
    if (sub / "serial_to_mqtt.py").is_file():
        return sub
    sibling = hart_repo_root().parent / "LCOS_ESP32_MQTT_Client"
    return sibling if sibling.is_dir() else sub


def all_runtime_paths() -> dict[str, Path]:
    """Named runtime paths for audits."""
    return {
        "HART_REPO_ROOT": hart_repo_root(),
        "HART_RUNTIME_ROOT": hart_runtime_root(),
        "HART_OPS_ROOT": hart_ops_root(),
        "STS_DOCKER_ROOT": sts_docker_root(),
        "STS_HELPERS_ROOT": sts_helpers_root(),
        "STS_DATA_ROOT": sts_data_root(),
        "STS_BACKUPS_DIR": sts_backups_dir(),
        "STS_DATABASE_DIR": sts_database_dir(),
        "STS_IMAGES_DIR": sts_images_dir(),
        "HART_CAR_CARDS_ROOT": car_cards_root(),
        "HART_CAR_IMAGES_FINAL": car_images_final(),
    }


def all_mirror_sources() -> dict[str, Path]:
    return {
        "HART_MIRROR_SRC": mirror_hart_src(),
        "DESKTOP_HART": mirror_desktop_hart(),
    }
