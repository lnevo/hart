import io
import os
import subprocess
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "pack_roster_stage.sh")


def pack(path):
    out = subprocess.run([SCRIPT, path], check=True, capture_output=True).stdout
    return tarfile.open(fileobj=io.BytesIO(out))


class PackRosterStageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "stage", "roster")
        os.makedirs(os.path.join(self.dir, "sub"))
        for name, text in (("2738.xml", "new"), ("1993.xml", "other"), ("._2738.xml", "junk")):
            with open(os.path.join(self.dir, name), "w") as f:
                f.write(text)
        with open(os.path.join(self.dir, "sub", "inner.xml"), "w") as f:
            f.write("nested")

    def tearDown(self):
        self.tmp.cleanup()

    def test_names_are_relative_to_the_stage_folder(self):
        names = pack(self.dir).getnames()
        for n in names:
            self.assertFalse(n.startswith("/"), n)
            self.assertNotIn(self.tmp.name.strip("/"), n)
        self.assertEqual(sorted(n.lstrip("./") for n in names), ["1993.xml", "2738.xml"])

    def test_skips_appledouble_and_subfolders(self):
        names = " ".join(pack(self.dir).getnames())
        self.assertNotIn("._", names)
        self.assertNotIn("inner.xml", names)

    def test_unpacks_flat_with_the_same_content(self):
        dest = os.path.join(self.tmp.name, "dest")
        os.makedirs(dest)
        tar = pack(self.dir)
        for m in tar.getmembers():
            with open(os.path.join(dest, os.path.basename(m.name)), "wb") as f:
                f.write(tar.extractfile(m).read())
        self.assertEqual(sorted(os.listdir(dest)), ["1993.xml", "2738.xml"])
        with open(os.path.join(dest, "2738.xml")) as f:
            self.assertEqual(f.read(), "new")

    def test_missing_folder_fails(self):
        r = subprocess.run([SCRIPT, os.path.join(self.tmp.name, "nope")], capture_output=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
