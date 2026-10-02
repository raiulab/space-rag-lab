import math
import unittest

from rag_lab.embeddings import HashEmbeddingModel, cosine_similarity
from rag_lab.text import normalize_text, tokenize


class TextAndEmbeddingTests(unittest.TestCase):
    def test_normalization_and_japanese_tokens(self) -> None:
        self.assertEqual(normalize_text("  ３２％  "), "32%")
        tokens = tokenize("火星の砂嵐")
        self.assertIn("ja:火星", tokens)
        self.assertIn("ja:砂嵐", tokens)

    def test_embedding_is_deterministic_and_normalized(self) -> None:
        model = HashEmbeddingModel(64)
        first = model.embed("太陽電池の出力")
        second = model.embed("太陽電池の出力")
        self.assertEqual(first, second)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in first)), 1.0)
        self.assertAlmostEqual(cosine_similarity(first, second), 1.0)


if __name__ == "__main__":
    unittest.main()
