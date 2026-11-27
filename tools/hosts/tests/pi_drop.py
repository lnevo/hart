"""The Pi's apply step (tools/hosts/pi/apply_hart_package_local.sh) run on this machine against a made-up deploy drop.

The drop holds the files the apply step needs to finish plus the ones a test names; the Pi's JMRI_UserFiles, home
and JMRI profile are folders in a temporary directory. ssh, scp, sudo, systemctl and loginctl on PATH log their call
and fail, so nothing reaches a host. install_ops_files.sh and install_roster.sh in the drop only log their call:
their own tests cover them.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APPLY = ROOT / "tools/hosts/pi/apply_hart_package_local.sh"
PATCH = ROOT / "cats/scripts/patch_jmri_startup.py"
# The Pi's JMRI profile, as the apply step names it under $HOME.
PROFILE = Path(".jmri/TCS_MQTT.jmri/profile/profile.xml")
NETWORK = ("ssh", "scp", "sudo", "systemctl", "loginctl")
LOGGER = '#!/bin/bash\necho "$(basename "$0") $*" >>"$PI_DROP_LOG"\n'
# The drop's files the apply step reads on every run, whatever a test adds.
REQUIRED: dict[str, str] = {
    "cats/scripts/install_ops_files.sh": LOGGER,
    "cats/scripts/pi/install_roster.sh": LOGGER,
    "cats/scripts/pi/launch_cats.sh": "#!/bin/bash\n",
    "cats/scripts/pi/JMRI_CATS": "#!/bin/bash\n",
    "cats/scripts/pi/README_CATS.txt": "CATS\n",
    "cats/panels/HART_CTC.xml": "<panel/>\n",
    "cats/panels/HART_ABS.xml": "<panel/>\n",
}
START_UP = """<?xml version="1.0" encoding="UTF-8"?>
<auxiliary-configuration>
  <startup>
{entries}
  </startup>
</auxiliary-configuration>
"""
PERFORM = ('    <perform name="{name}" type="ScriptFile" enabled="yes" '
           'class="jmri.util.startup.configurexml.PerformScriptModelXml"/>')


def start_up(*names: str) -> str:
    """A profile.xml whose Start Up list runs the scripts `names`, in order."""
    return START_UP.format(entries="\n".join(PERFORM.format(name=n) for n in names))


@dataclass(frozen=True)
class PiHost:
    """The made-up Pi after one apply: where it installed, what it printed, and the calls it logged."""
    drop: Path
    home: Path
    user_files: Path
    code: int
    out: str
    calls: list[str]

    @property
    def profile(self) -> Path:
        return self.home / PROFILE


def _write(root: Path, files: Mapping[str, str | bytes]) -> None:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body, encoding="utf-8")
        if rel.endswith(".sh"):
            path.chmod(0o755)


def _env(drop: Path, home: Path, user_files: Path, bin_dir: Path, log: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HART", "JMRI_", "XDG_", "DBUS_"))}
    env.update(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", HART=str(drop), HOME=str(home),
               JMRI_USERFILES=str(user_files), JMRI_HOME=str(home / "JMRI"), PI_DROP_LOG=str(log),
               PYTHONDONTWRITEBYTECODE="1")
    return env


@contextmanager
def applied(package: Mapping[str, str | bytes], installed: Mapping[str, str | bytes] | None = None,
            profile: str | None = None) -> Iterator[PiHost]:
    """Run the apply step on a drop holding REQUIRED and `package` (paths inside the package). `installed` is what
    the Pi holds before, by path under its home; `profile`, when given, is its JMRI profile.xml."""
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        # the apply step refuses a drop outside /tmp/hart-deploy.*, and removes the drop when it ends
        drop = Path(tempfile.mkdtemp(prefix="hart-deploy.", dir="/tmp"))
        try:
            home, bin_dir, log = tmp / "home", tmp / "bin", tmp / "calls.log"
            user_files = home / "JMRI_UserFiles"
            _write(drop, {**REQUIRED, **package})
            _write(home, dict(installed or {}))
            if profile is not None:
                _write(home, {str(PROFILE): profile})
            bin_dir.mkdir()
            for tool in NETWORK:
                (bin_dir / tool).write_text(LOGGER + "exit 99\n", encoding="utf-8")
                (bin_dir / tool).chmod(0o755)
            log.touch()
            done = subprocess.run(["bash", str(APPLY)], env=_env(drop, home, user_files, bin_dir, log),
                                  capture_output=True, text=True, timeout=120)
            yield PiHost(drop, home, user_files, done.returncode, done.stdout + done.stderr,
                         log.read_text(encoding="utf-8").splitlines())
        finally:
            shutil.rmtree(drop, ignore_errors=True)


def files_under(root: Path) -> list[str]:
    """Every file under `root`, by path relative to it, sorted."""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
