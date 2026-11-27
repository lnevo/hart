"""The jython the Windows apply step installs (tools/hosts/windows/jython_list.ps1, Get-JythonSources), for tests.

With pwsh on PATH the reader itself runs, on a list and a package folder given here. Without it, windows_jython
takes the rows of jython_scripts.txt (read by jython_list.sh, as pi_drop does) whose role is in the reader's
$JythonWindowsRoles, so the Windows set still follows the one list and the roles the reader declares.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from pi_drop import JYTHON_LIST, ROOT, jython_rows

READER = ROOT / "tools/hosts/windows/jython_list.ps1"
PWSH = shutil.which("pwsh")


class PwshError(Exception):
    """Get-JythonSources threw; the message is what it said."""


def declared_roles(name: str) -> tuple[str, ...]:
    """The roles the reader assigns to `name` (JythonRoles or JythonWindowsRoles): its one `$name = @('a', ...)`."""
    found = re.findall(rf"^\${name} = @\(([^)]*)\)$", READER.read_text(encoding="utf-8"), re.M)
    if len(found) != 1:
        raise AssertionError(f"{READER.name}: expected one ${name} = @(...) line, found {len(found)}")
    return tuple(re.findall(r"'([a-z]+)'", found[0]))


def run_reader(listing: Path, package: Path) -> list[str]:
    """Get-JythonSources on `listing` and `package` in pwsh: each source path, relative to `package`, as posix."""
    if PWSH is None:
        raise RuntimeError("pwsh is not installed")
    script = ("$ErrorActionPreference = 'Stop'; . $args[0]; "
              "try { Get-JythonSources -List $args[1] -Package $args[2] } catch { [Console]::Error.WriteLine($_); exit 3 }")
    done = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", script, str(READER), str(listing),
                           str(package)], capture_output=True, text=True, timeout=120, check=False)
    if done.returncode == 3:
        raise PwshError(done.stderr.strip())
    if done.returncode != 0:
        raise AssertionError(f"pwsh failed ({done.returncode}): {done.stderr.strip()}")
    return [Path(line).relative_to(package).as_posix() for line in done.stdout.splitlines() if line.strip()]


def windows_jython(listing: Path = JYTHON_LIST, package: Path = ROOT) -> list[str]:
    """The repo paths Windows installs from `listing`, in list order (`package`: where the reader looks for them)."""
    if PWSH is not None:
        return run_reader(listing, package)
    roles = declared_roles("JythonWindowsRoles")
    return [row.path for row in jython_rows(listing) if row.role in roles]
