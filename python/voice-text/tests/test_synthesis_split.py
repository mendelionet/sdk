"""The batch splitter: does it cut Czech where Czech may be cut?

These tests are written against the failures the LIVE path already paid for in production.
The abbreviation cases are not hypothetical politeness — they are the reason NLTK was
replaced there, and the reason this package exists instead of a second naive splitter.
"""

from __future__ import annotations

import pytest

from mendelio_voice_text import (
    BATCH_MAX_SYNTHESIS_CHARS,
    LIVE_HARD_FLUSH_CHARS,
    SpeechPreprocessor,
)
from mendelio_voice_text.synthesis_split import (
    ZEROSHOT_MAX_TEXT_CHARS,
    split_for_synthesis,
)

# --------------------------------------------------------------------------
# The cap is the contract: no chunk may pin the GPU for longer than agreed
# --------------------------------------------------------------------------


def test_no_chunk_ever_exceeds_the_cap() -> None:
    """The one invariant the GPU cares about. `model.generate()` cannot be preempted, so a
    chunk over the cap is a stall nobody can interrupt — not a live session, not a minigame.
    """
    text = " ".join(f"Věta číslo {i} o něčem docela zajímavém." for i in range(80))
    for chunk in split_for_synthesis(text, max_chars=200):
        assert len(chunk) <= 200, f"{len(chunk)} chars would pin the GPU past the cap"


def test_short_text_is_not_cut_at_all() -> None:
    """The common case must come back untouched, not reassembled from pieces it never
    needed. Every seam is a chance to sound wrong; earn them."""
    text = "Ahoj, jak se máš?"
    assert split_for_synthesis(text, max_chars=400) == [text]


def test_blank_input_produces_nothing_to_say() -> None:
    # An empty list keeps a caller from sending a silent synthesis request and paying GPU
    # for it.
    assert split_for_synthesis("", max_chars=400) == []
    assert split_for_synthesis("   \n  ", max_chars=400) == []


def test_the_whole_text_survives_the_split() -> None:
    """Nothing may be dropped. A splitter that loses a sentence is worse than one that cuts
    badly: bad cuts are audible, missing words are not."""
    text = " ".join(f"Toto je věta číslo {i}." for i in range(40))
    joined = " ".join(split_for_synthesis(text, max_chars=90))
    assert joined.split() == text.split()


# --------------------------------------------------------------------------
# The Czech abbreviations — what quantize.py got wrong
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "naive_would_stop_at"),
    [
        ("Byl to tzv. hlavní důvod celé té složité věci", "Byl to tzv."),
        ("Přednášel prof. Novák z Brna a mluvil dlouho", "Přednášel prof."),
        ("Sešli jsme se s Ing. Svobodou v pátek odpoledne", "Sešli jsme se s Ing."),
        ("Dorazil J. Novák se svou celou širokou rodinou", "Dorazil J."),
        ("Zákon platí od r. 1993 pro úplně všechny lidi", "Zákon platí od r."),
        ("Koupil mléko, chleba apod. věci pro celou rodinu", "Koupil mléko, chleba apod."),
    ],
)
def test_an_abbreviation_period_does_not_end_a_chunk_early(
    text: str, naive_would_stop_at: str
) -> None:
    """`tzv.` / `prof.` / `Ing.` / `J.` must not cut the chunk short.

    A naive "split on .!?" stops at the abbreviation and hands the synthesiser a stunted
    chunk; it then starts a fresh sentence on the following word, with the wrong intonation
    on both halves. This is the failure the live path already paid for in production, and the
    reason NLTK was replaced there — NLTK accepts "Ing." as a sentence end before it can see
    "Svoboda".

    THE WINDOW IS THE TEST. Each case is built so the abbreviation is the ONLY terminator
    inside `max_chars`, because that is the only situation where the knowledge can be
    observed. Two earlier versions of this test were vacuous and passed anyway:

      * `max_chars=1` chops single characters, so every `endswith` assert was trivially true;
      * a window containing a LATER real sentence end hid the bug, because `_last_sentence_
        end_within` takes the last candidate — a real stop at 22 silently overrides a false
        one at 15, so deleting the abbreviation list changed nothing and the test still went
        green.

    Verified by mutation: stubbing `ends_in_abbreviation` to `False` turns each expected
    value into `naive_would_stop_at`.
    """
    # The window must leave room AFTER the abbreviation. Too tight and the word-boundary
    # fallback lands on the abbreviation's own period anyway (see the hard-cap test below),
    # which makes the knowledge unobservable and the case vacuous again.
    produced = split_for_synthesis(text, max_chars=40)[0]
    assert produced != naive_would_stop_at, "cut short at the abbreviation, like NLTK does"
    assert produced.startswith(naive_would_stop_at), "the abbreviation must stay in the chunk"
    assert len(produced) > len(naive_would_stop_at)


def test_the_hard_cap_may_still_cut_after_an_abbreviation() -> None:
    """Honest about a limit, so nobody "fixes" it later by accident.

    With no real sentence end inside the window, the word-boundary fallback takes over — and
    `.` is a word boundary, so it can cut "prof. | Novák" after all. The abbreviation list
    only governs SENTENCE-boundary cuts; the cap is a safety valve and prefers whole words
    over whole titles.

    This is not a divergence: the live path's hard-cap fallback shares the same punctuation
    set and behaves identically. Cutting here is rare in practice because a real terminator
    almost always arrives first — that is a property of the tuning, not of the algorithm.
    """
    chunks = split_for_synthesis("Přednášel prof. Novák z Brna.", max_chars=20)
    assert chunks[0] == "Přednášel prof."


def test_a_real_sentence_end_is_preferred_over_a_word_boundary() -> None:
    """Given a choice inside the window, cut where the synthesiser was going to stop
    anyway — prosody survives that seam for free."""
    text = "První věta skončila. Druhá věta pokračuje dál a dál a dál."
    chunks = split_for_synthesis(text, max_chars=30)
    assert chunks[0] == "První věta skončila."


# --------------------------------------------------------------------------
# Never mid-word — OmniVoice voices a partial token as broken syllables
# --------------------------------------------------------------------------


def test_a_boundary_less_run_is_cut_at_a_word_not_mid_token() -> None:
    """A long Czech list has no terminator anywhere. Falling back to a word boundary keeps
    the words intact even though the seam itself is audible."""
    text = "jablka hrušky švestky meruňky broskve třešně višně jahody maliny ostružiny"
    for chunk in split_for_synthesis(text, max_chars=30):
        assert chunk == chunk.strip()
        assert " " not in chunk[-1:], chunk
        # Every emitted chunk must consist of whole words from the source.
        for word in chunk.split():
            assert word in text.split(), f"{word!r} is not a whole source word"


def test_one_token_longer_than_the_cap_is_cut_rather_than_handed_over_whole() -> None:
    """The only case with no good answer. A single unbroken token over the cap has no safe
    seam — but handing it to the GPU whole means an unbounded, uninterruptible stall, which
    is worse than a broken syllable. Bounded and ugly beats unbounded.
    """
    text = "a" * 500
    chunks = split_for_synthesis(text, max_chars=100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == text


def test_a_terminator_cluster_stays_whole() -> None:
    """Cutting `?!` down the middle orphans `!` at the head of the next chunk: it reads as a
    shout and the question loses its intonation."""
    text = "Vážně?! To jsem nevěděl. A co dál?! Řekni mi to celé, prosím tě pěkně."
    for chunk in split_for_synthesis(text, max_chars=25):
        assert not chunk.startswith("!"), chunk
        assert not chunk.startswith("?"), chunk


# --------------------------------------------------------------------------
# The two tunings must stay two
# --------------------------------------------------------------------------


def test_the_omnivoice_profile_enforces_its_public_model_text_cap() -> None:
    """The published profile owns the final model-facing limit without a private source dependency."""
    assert ZEROSHOT_MAX_TEXT_CHARS == 300
    assert BATCH_MAX_SYNTHESIS_CHARS == ZEROSHOT_MAX_TEXT_CHARS

    prepared = SpeechPreprocessor.czech_omnivoice().prepare("Kupodivu " * 100)
    assert len(prepared.chunks) > 1
    assert all(
        len(chunk.model_text) <= BATCH_MAX_SYNTHESIS_CHARS
        for chunk in prepared.chunks
    )


def test_batch_is_more_tolerant_than_live() -> None:
    """One algorithm, two tunings — and they must not silently converge.

    Live is capped by a human's patience (~200 ms of CUDA per chunk). Batch has nobody
    waiting, so its cap exists ONLY to stop the GPU going dark for a noticeable stretch.
    If someone ever "unifies" these to one number, this fails and asks them why.
    """
    assert BATCH_MAX_SYNTHESIS_CHARS > LIVE_HARD_FLUSH_CHARS
    assert LIVE_HARD_FLUSH_CHARS == 120, (
        "the live tuning changed — services/remote_omnivoice_tts.py is the source of truth "
        "and the chars->CUDA calibration note must be re-derived"
    )


def test_a_nonsense_cap_is_refused_rather_than_looping() -> None:
    with pytest.raises(ValueError):
        split_for_synthesis("cokoliv", max_chars=0)
