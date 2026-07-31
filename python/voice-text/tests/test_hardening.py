from __future__ import annotations

import time

from hypothesis import given, settings, strategies as st

from mendelio_voice_text import SpeechPreprocessor


_UNICODE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=240,
)


@given(_UNICODE_TEXT)
@settings(max_examples=80, deadline=None, derandomize=True, database=None)
def test_arbitrary_unicode_is_deterministic_and_chunk_bounded(source: str) -> None:
    preprocessor = SpeechPreprocessor.czech_omnivoice(max_chars=120)

    first = preprocessor.prepare(source)
    second = preprocessor.prepare(source)

    assert first == second
    assert first.display_text == source
    assert all(len(chunk.model_text) <= 120 for chunk in first.chunks)


def test_combining_marks_emoji_bidi_and_controls_do_not_corrupt_display_text() -> None:
    source = "Příliš žluťoučký 🦊 e\u0301 \u202eabc\u202c\x00 konec."

    prepared = SpeechPreprocessor.czech_omnivoice().prepare(source)

    assert prepared.display_text == source
    assert "\U0001f98a" in prepared.spoken_text
    assert "\x00" in prepared.model_text


def test_huge_integer_and_percent_tokens_are_linear_and_do_not_raise() -> None:
    digits = "9" * 5_000
    prepared = SpeechPreprocessor.czech_generic(max_chars=300).prepare(
        f"{digits} a {digits} %"
    )

    assert not any(char.isascii() and char.isdigit() for char in prepared.spoken_text)
    assert all(len(chunk.model_text) <= 300 for chunk in prepared.chunks)


def test_ten_thousand_sentence_semantic_budget() -> None:
    preprocessor = SpeechPreprocessor.czech_generic(max_chars=300)
    sentence = "V roce 1993 bylo 45 % lidí a cesta měřila 12 km."

    started = time.perf_counter()
    for _ in range(10_000):
        preprocessor.prepare(sentence)
    elapsed = time.perf_counter() - started

    assert elapsed < 10.0, f"10k sentence budget exceeded: {elapsed:.3f}s"
