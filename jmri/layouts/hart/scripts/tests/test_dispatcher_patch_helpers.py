import ast
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "patch_dispatcher_facing.py"


def load_patch_namespace():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    payload = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "_PATCH"
            for target in node.targets
        ):
            payload = ast.literal_eval(node.value)
            break
    if payload is None:
        raise AssertionError("_PATCH payload not found")
    namespace = {}
    exec(payload, namespace)
    return namespace


class FakeBlock:
    def __init__(self, name):
        self.name = name

    def getUserName(self):
        return self.name


class DispatcherPatchHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = load_patch_namespace()

    def test_missing_speed_factor_uses_safe_default(self):
        normalize = self.namespace["_hart_normalize_speed_factor"]
        self.assertEqual("100", normalize(None))
        self.assertEqual("100", normalize(""))
        self.assertEqual("100", normalize("-1"))
        self.assertEqual("85", normalize("85"))

    def test_route_window_excludes_start_and_unrelated_transit_blocks(self):
        select = self.namespace["_hart_requested_route_blocks"]
        blocks = [
            FakeBlock("unrelated west"),
            FakeBlock("East Main Ext"),
            FakeBlock("OS 117b"),
            FakeBlock("Main East"),
            FakeBlock("McKeesport"),
            FakeBlock("unrelated east"),
        ]
        selected = select(blocks, "East Main Ext", "McKeesport")
        self.assertEqual(
            ["OS 117b", "Main East", "McKeesport"],
            [block.getUserName() for block in selected],
        )

    def test_route_window_fails_closed_when_endpoint_is_missing(self):
        select = self.namespace["_hart_requested_route_blocks"]
        blocks = [FakeBlock("East Main Ext"), FakeBlock("Main East")]
        self.assertIsNone(select(blocks, "East Main Ext", "McKeesport"))

    def test_first_move_keeps_registered_facing(self):
        skip = self.namespace["_hart_should_skip_uturn_flip"]
        self.assertTrue(skip({"hart_honor_facing": True, "direction": "forward"}))
        self.assertFalse(skip({"hart_honor_facing": False, "direction": "forward"}))
        self.assertFalse(skip({"direction": "forward"}))


JYTHON_RUNTIME_SCRIPTS = (
    Path(__file__).resolve().parents[1] / "hart_dispatcher_startup.py",
    Path(__file__).resolve().parents[1] / "hide_cats_desk_windows.py",
    Path(__file__).resolve().parents[1] / "patch_dispatcher_facing.py",
)


class DispatcherJythonRuntimeGuardTest(unittest.TestCase):
    def test_jmri_scripts_do_not_enable_print_function(self):
        for path in JYTHON_RUNTIME_SCRIPTS:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                self.assertNotEqual(
                    stripped,
                    "from __future__ import print_function",
                    msg=(
                        "%s would leak print_function into JMRI's shared Jython "
                        "engine and break stock DispatcherSystem/Startup.py"
                        % path.name
                    ),
                )

    def test_wrapper_compiles_stock_files_without_inherited_flags(self):
        text = JYTHON_RUNTIME_SCRIPTS[0].read_text(encoding="utf-8")
        self.assertIn('compile(source, path, "exec", 0, True)', text)


if __name__ == "__main__":
    unittest.main()
