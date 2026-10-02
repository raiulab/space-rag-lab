import tempfile
import unittest
from pathlib import Path

from rag_lab.ingest import chunk_document, parse_front_matter, split_pages


class IngestTests(unittest.TestCase):
    def test_front_matter_and_pages(self) -> None:
        text = "---\ndocument_id: demo\ntitle: 試験文書\n---\n<!-- page: 2 -->\n本文"
        metadata, body = parse_front_matter(text)
        self.assertEqual(metadata["document_id"], "demo")
        self.assertEqual(split_pages(body), [(2, "\n本文")])

    def test_chunk_preserves_provenance(self) -> None:
        content = """---
document_id: demo
title: 試験文書
source: unit-test
classification: synthetic
---
<!-- page: 3 -->
# 結果
温度は78 ℃だった。
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.md"
            path.write_text(content, encoding="utf-8")
            chunks = chunk_document(path)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].document_id, "demo")
        self.assertEqual(chunks[0].page, 3)
        self.assertEqual(chunks[0].section, "結果")
        self.assertEqual(chunks[0].source, "unit-test")
        self.assertEqual(chunks[0].metadata["classification"], "synthetic")


if __name__ == "__main__":
    unittest.main()
