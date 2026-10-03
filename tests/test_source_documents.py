import unittest

from rag_lab.source_documents import (
    ContentBlock,
    SourceDocument,
    SourcePage,
    chunk_source_document,
    split_block_text,
)


class SourceDocumentTests(unittest.TestCase):
    def test_chunking_preserves_source_provenance(self) -> None:
        document = SourceDocument(
            document_id="demo_pdf",
            title="試験文書",
            source="demo.pdf",
            media_type="application/pdf",
            metadata={"classification": "synthetic"},
            pages=[
                SourcePage(
                    page=2,
                    blocks=[
                        ContentBlock(
                            block_id="demo_pdf:p2:b001",
                            kind="text",
                            text="最初の文です。次の文です。",
                            section="本文",
                            extraction_method="test",
                        )
                    ],
                )
            ],
        )

        chunks = chunk_source_document(document, chunk_size=8)

        self.assertEqual([chunk.page for chunk in chunks], [2, 2])
        self.assertEqual(chunks[0].chunk_id, "demo_pdf:p2:001")
        self.assertEqual(chunks[0].section, "本文")
        self.assertEqual(chunks[0].source, "demo.pdf")
        self.assertEqual(chunks[0].metadata["classification"], "synthetic")
        self.assertEqual(chunks[0].metadata["source_block_id"], "demo_pdf:p2:b001")

    def test_oversized_sentence_is_never_lost(self) -> None:
        text = "A" * 21
        parts = split_block_text(text, chunk_size=10)
        self.assertEqual(parts, ["A" * 10, "A" * 10, "A"])
        self.assertEqual("".join(parts), text)

    def test_invalid_chunk_size_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "1以上"):
            split_block_text("本文", chunk_size=0)


if __name__ == "__main__":
    unittest.main()
