from __future__ import annotations

import re
import unicodedata
from collections import Counter


ASCII_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]*|\d+(?:\.\d+)?")
JAPANESE_SEQUENCE_RE = re.compile(r"[一-龯々〆ヵヶぁ-んァ-ヶー]+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])\s*|\n+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    """Tokenize English and Japanese without an external tokenizer.

    Japanese character bigrams make the offline baseline useful while keeping the
    project dependency-free. A production system should compare this baseline with
    a proper multilingual embedding model and a language-aware tokenizer.
    """

    normalized = normalize_text(text).lower()
    tokens = ASCII_TOKEN_RE.findall(normalized)
    for sequence in JAPANESE_SEQUENCE_RE.findall(normalized):
        if len(sequence) == 1:
            tokens.append(f"ja:{sequence}")
            continue
        tokens.extend(f"ja:{sequence[index:index + 2]}" for index in range(len(sequence) - 1))
        if len(sequence) >= 3:
            tokens.extend(
                f"ja3:{sequence[index:index + 3]}" for index in range(len(sequence) - 2)
            )
    return tokens


def token_counts(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
