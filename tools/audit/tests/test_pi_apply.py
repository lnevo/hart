"""The Pi keeps one tables.xml, in JMRI_UserFiles."""
from __future__ import annotations

import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "cats/scripts/pi/apply_hart_package_local.sh"

class PiTablesTest(unittest.TestCase):
    def test_deploy_moves_tables_out_of_hart(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('mv -f "$HART/tables.xml" "$UF/tables.xml"', source)
        self.assertNotIn('cp -f "$HART/tables.xml"', source)

    def test_hosts_have_no_hart_folder(self) -> None:
        for folder in (SCRIPT.parent, SCRIPT.parent.parent / "windows"):
            for path in folder.iterdir():
                if path.suffix in {".sh", ".bat", ".ps1", ".desktop", ".txt"} or path.name == "JMRI_CATS":
                    source = path.read_text(encoding="utf-8", errors="replace")
                    self.assertNotIn("/home/pi/hart", source, path.name)
                    self.assertNotIn("USERPROFILE%\\hart", source, path.name)
                    self.assertNotIn("USERPROFILE 'hart", source, path.name)

    def test_windows_deploy_writes_only_to_user_files(self) -> None:
        source = (SCRIPT.parent.parent / "windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
        self.assertNotIn("$dests.Add((Join-Path $_.FullName 'tables.xml'))", source)
        self.assertNotIn("$roots.Add($_.FullName)", source)

    def test_windows_apply_finds_user_python_and_checks_it(self) -> None:
        source = (SCRIPT.parent.parent / "windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
        path_merge = source.index("GetEnvironmentVariable('Path', 'User')")
        find = source.index("$python = Find-Python")
        call = source.index("& $python.Exe @pyArgs")
        self.assertLess(path_merge, find, "user PATH must be loaded before Python is looked up")
        self.assertLess(find, call)
        self.assertIn("$env:Path = (@($first) + @($rest)) -join ';'", source, "user PATH goes first")
        after = source[call:call + 300]
        self.assertLess(after.index("$LASTEXITCODE"), after.index("Start Up retargeted"),
                        "a failed retarget must not report success")

    def test_windows_apply_python_order_and_missing_python(self) -> None:
        """py -3, then python, then python3; Store stubs skipped; no Python warns and skips."""
        source = (SCRIPT.parent.parent / "windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
        self.assertIn("foreach ($c in @(@('py', '-3'), @('python'), @('python3')))", source)
        self.assertIn("-notmatch '\\\\WindowsApps\\\\'", source)
        self.assertNotIn("& python @pyArgs", source)
        finder = source[source.index("function Find-Python"):source.index("$python = Find-Python")]
        self.assertIn("sys.version_info[0] == 3", finder, "each candidate must start a Python 3")
        self.assertLess(finder.index("$LASTEXITCODE -eq 0"), finder.index("return [pscustomobject]"))
        block = source[source.index("if (Test-Path $patchPy)"):source.index("& $python.Exe @pyArgs")]
        self.assertIn("if (-not $python)", block)
        self.assertIn("Write-Warning", block)
        self.assertNotIn("throw", block, "a missing Python warns instead of failing the deploy")

    def test_pi_drop_stays_in_tmp_and_is_removed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("/tmp/hart-deploy.*)", source)
        self.assertIn("""trap 'rm -rf "$HART"' EXIT""", source)


if __name__ == "__main__":
    unittest.main()
