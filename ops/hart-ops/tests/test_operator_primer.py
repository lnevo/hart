"""publications/rebuild_operator_primer.py: the primer text file and the document built from it."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "publications"))

from docx import Document  # noqa: E402

import rebuild_operator_primer as primer  # noqa: E402

RAW = json.loads(primer.TEXT.read_text(encoding="utf-8"))


def load(raw: object) -> primer.PrimerText:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "operator_primer.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return primer.load_text(path)


def changed(edit) -> dict:
    raw = copy.deepcopy(RAW)
    edit(raw)
    return raw


class LoadText(unittest.TestCase):
    def test_shipped_text_loads(self) -> None:
        text = primer.load_text()
        self.assertEqual(text.publication["pub_id"], "HB-01")
        self.assertEqual([j.code for j in text.jobs][:3], ["D749", "NVL", "CK1"])
        self.assertEqual(len(text.pages), 4)

    def test_unknown_block_kind_names_the_page_and_block(self) -> None:
        raw = changed(lambda r: r["pages"][1].insert(0, {"kind": "poem", "text": "x"}))
        with self.assertRaisesRegex(primer.PrimerDataError, r"page 2 block 1: unknown block kind 'poem'"):
            load(raw)

    def test_field_a_block_does_not_use_is_refused(self) -> None:
        raw = changed(lambda r: r["pages"][0][0].update(space_after=3))
        with self.assertRaisesRegex(primer.PrimerDataError, r"heading block has fields it does not use: \['space_after'\]"):
            load(raw)

    def test_body_without_text_is_refused(self) -> None:
        raw = changed(lambda r: r["pages"][0][1].pop("text"))
        with self.assertRaisesRegex(primer.PrimerDataError, r"page 1 block 2: 'text' must be a str"):
            load(raw)

    def test_link_without_url_is_refused(self) -> None:
        def edit(r: dict) -> None:
            links = next(b for b in r["pages"][3] if b["kind"] == "links")
            links["items"][0].pop("url")
        with self.assertRaisesRegex(primer.PrimerDataError, "a link needs a label and a url"):
            load(changed(edit))

    def test_jobs_block_must_appear_once(self) -> None:
        raw = changed(lambda r: r["pages"][2].append({"kind": "jobs"}))
        with self.assertRaisesRegex(primer.PrimerDataError, "need one jobs block, found 2"):
            load(raw)

    def test_job_missing_a_blurb_is_refused(self) -> None:
        raw = changed(lambda r: r["jobs"][0].pop("blurb"))
        with self.assertRaisesRegex(primer.PrimerDataError, "job 1: 'blurb' must be a str"):
            load(raw)

    def test_unreadable_file_keeps_the_cause(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operator_primer.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(primer.PrimerDataError) as caught:
                primer.load_text(path)
        self.assertIsInstance(caught.exception.__cause__, json.JSONDecodeError)
        self.assertIn("operator_primer.json", str(caught.exception))

    def test_every_master_colour_has_a_primer_train(self) -> None:
        self.assertEqual(len(primer.BLOCK_LEGEND), len(primer.PRIMER_BLOCK_TRAIN))


class Build(unittest.TestCase):
    def test_document_follows_the_text_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = primer.build(out=Path(tmp) / "sub" / "primer.docx")
            doc = Document(str(out))
        paras = [p.text for p in doc.paragraphs]
        text = primer.PRIMER
        headings = [b["text"] for page in text.pages for b in page if b["kind"] == "heading"]
        positions = [paras.index(h) for h in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(paras[0], "HART Railroad")
        self.assertIn(text.subtitle, paras)
        for job in text.jobs:
            self.assertIn(f"{job.code}  ·  {job.name}", paras)
        self.assertLess(paras.index(text.signature["closing"]), paras.index(text.signature["lines"][0]["text"]))
        self.assertEqual(len(doc.tables[0].rows), 1 + len(primer.BLOCK_LEGEND))


if __name__ == "__main__":
    unittest.main()
