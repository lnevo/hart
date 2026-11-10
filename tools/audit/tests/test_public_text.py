"""check_public_text finds personal email addresses and reads PDFs."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("check_public_text", ROOT / "tools/audit/check_public_text.py")
cpt = importlib.util.module_from_spec(spec)
sys.modules["check_public_text"] = cpt
spec.loader.exec_module(cpt)

try:
    import pypdf  # noqa: F401
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False


def tiny_pdf(text: str) -> bytes:
    """A one-page PDF with `text` on it, built by hand so the test needs no writer library."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


class PersonalEmail(unittest.TestCase):
    def test_consumer_addresses_fail(self) -> None:
        for text in ("send to someone@icloud.com now", "x.y+z@Gmail.com", "a@mac.com"):
            self.assertTrue(cpt.personal_email(text), text)

    def test_service_addresses_pass(self) -> None:
        for text in ("git@github.com:lnevo/hart.git", "jmriusers@groups.io", "noreply@anthropic.com",
                     "user@host.local", "a@mac.community"):
            self.assertFalse(cpt.personal_email(text), text)


class Files(unittest.TestCase):
    def check(self, name: str, data: bytes) -> list[str]:
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp) / name
            path.write_bytes(data)
            return cpt.problems([str(path.relative_to(ROOT))])

    def test_text_file_with_email_fails(self) -> None:
        self.assertEqual(len(self.check("a.sh", b"#!/bin/sh\nTO=someone@icloud.com\n")), 1)

    def test_clean_text_file_passes(self) -> None:
        self.assertEqual(self.check("a.md", b"# Notes\nNothing private.\n"), [])

    @unittest.skipUnless(HAVE_PYPDF, "pypdf not installed")
    def test_pdf_text_is_read(self) -> None:
        self.assertEqual(len(self.check("a.pdf", tiny_pdf("mail someone@icloud.com"))), 1)
        self.assertEqual(self.check("b.pdf", tiny_pdf("Neville Island")), [])


if __name__ == "__main__":
    unittest.main()
