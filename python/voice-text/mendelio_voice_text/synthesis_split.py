"""Split a known-in-advance Czech text into chunks that are safe to synthesise.

WHAT THIS IS FOR
----------------
`model.generate()` is NOT preemptible. Whatever text you hand to one call, the GPU is gone
for its whole duration and nothing — not a live session, not a minigame — can get in front
of it. The TTS server's `SynthesisScheduler` ranks work by signed work class, but it can
only rank BETWEEN calls: hand it one enormous call and it has nothing to rank.

So the size of a chunk is not a text-formatting decision. It is the answer to "how long may
the GPU be unavailable?", and that is why the cap is expressed in characters but REASONED
about in milliseconds.

    services/voice-orchestrator/benchmarks/capacity/bench_scheduler_parallelism.py:127
        "OmniVoice at hard_flush_chars=120 = ~200 ms of CUDA work per chunk."

That note is the only chars→GPU-time conversion this repo has. Treat it as calibration, NOT
as measurement: it is a constant in a SIMULATION (`GPU_TIME = 0.2`), where thread sleeps
stand in for CUDA. It is far better grounded than a guess, and it is still not an odometer
reading. A real number has to come off a real card.

ONE ALGORITHM, TWO TUNINGS
--------------------------
The live path and the batch path cut Czech at the same places, for the same reasons, using
the same primitives (`czech_sentences`). They differ ONLY in how much they are willing to
hand the GPU at once:

    live   ~120 chars  (~200 ms)   a human is waiting; latency decides
    batch  ~400 chars  (~700 ms)   nobody is waiting; the cap exists ONLY so the GPU
                                   does not go dark for a noticeable stretch

The live path also carries `min_chars` / `first_chunk_min_chars`, which have NO meaning here.
Those are a FLOOR, not a cap: they exist so 2–3 sentences merge into one call and the reply
does not arrive as staccato with ~100–200 ms of startup overhead between sentences. Batch has
no such problem — it already packs each chunk as full as the cap allows — so the floor is
deliberately absent rather than defaulted to something.
"""

from __future__ import annotations

from mendelio_voice_text.czech_sentences import ends_in_abbreviation, split_at_word_boundary

#: What the live path runs today (`services/remote_omnivoice_tts.py`). Here for reference and
#: for tests that assert the two tunings have not silently converged — NOT a batch default.
LIVE_HARD_FLUSH_CHARS = 120

#: The TTS server's OWN hard limit on `/zeroshot` text (`tts_server/app.py:559`):
#:
#:     if len(text) > 300:
#:         return JSONResponse({"error": "text_too_long"}, status_code=400)
#:
#: A cloned voice renders through `/zeroshot` (reference audio + transcript), so for
#: Mendelio Voice this is not a tuning knob — it is a wall. Exceeding it is not a slow
#: render, it is an HTTP 400 and a failed paid job.
ZEROSHOT_MAX_TEXT_CHARS = 300

#: The batch cap. NOT freely chosen: it is the zeroshot wall above, and picking a "more
#: tolerant" number would simply mean every chunk over 300 comes back 400.
#:
#: An earlier value here was 400, reasoned purely from the chars→CUDA calibration, on the
#: assumption that batch could be as tolerant as it liked. It could not: the assumption never
#: checked what the server accepts. Note the two constraints happen to agree — 300 is also
#: ~0.5 s of GPU by that calibration, which is a fine bound for work nobody is waiting on —
#: but the wall is what decides, and if the server ever raises its limit this may only rise
#: with a measurement behind it.
BATCH_MAX_SYNTHESIS_CHARS = ZEROSHOT_MAX_TEXT_CHARS


def _last_sentence_end_within(text: str, limit: int) -> int:
    """Position after the LAST real sentence terminator at or before `limit`, else 0.

    Scans from the start rather than from `limit` backwards, because the abbreviation test
    needs the token that precedes the period: asking "is this a sentence end?" about a slice
    that begins mid-token would see a truncated word and answer about the wrong thing.

    A terminator cluster (`?!`, `?!?`) advances the boundary through the whole run, so the
    cut lands after the last mark. Splitting `?!` down the middle would leave `!` orphaned at
    the head of the next chunk, which reads as a shout and loses the question intonation.
    """
    best = 0
    i = 0
    n = min(len(text), limit)
    while i < n:
        ch = text[i]
        if ch in ".!?":
            if ch == "." and ends_in_abbreviation(text[: i + 1]):
                i += 1
                continue
            best = i + 1
        i += 1
    return best


def split_for_synthesis(
    text: str,
    *,
    max_chars: int = BATCH_MAX_SYNTHESIS_CHARS,
) -> list[str]:
    """Cut `text` into chunks of at most `max_chars`, preferring sentence boundaries.

    The preference order is the whole design:

    1. **Sentence end** — the last real one that fits. Prosody survives a cut here because
       the synthesiser was going to stop anyway.
    2. **Word boundary** — when a chunk holds no sentence end at all (a long Czech list, a
       URL). The seam is audible but the words are intact.
    3. **Raw cut at the cap** — only when a single token is itself longer than the cap. This
       is the one case that can sound wrong, and it is preferred to the alternative, which is
       to hand the GPU an unbounded token and hope.

    Text shorter than the cap comes back as a single chunk, untouched. That matters: the
    common case must not be re-joined from pieces it never needed to be cut into.

    Returns `[]` for blank input — an empty list is the honest answer to "what should I
    synthesise?" when there is nothing, and it keeps a caller from sending a silent request.
    """
    if max_chars < 1:
        raise ValueError(f"max_chars must be >= 1, got {max_chars}")

    buf = text.strip()
    chunks: list[str] = []

    while buf:
        if len(buf) <= max_chars:
            chunks.append(buf)
            break

        cut = _last_sentence_end_within(buf, max_chars)

        if cut == 0:
            emit, _ = split_at_word_boundary(buf[:max_chars])
            # `split_at_word_boundary` returns "" when the window is one boundary-less token.
            # There is no safe cut, so take the cap: better a broken syllable than a GPU
            # held for however long the token runs.
            cut = len(emit) if emit else max_chars

        chunk = buf[:cut].strip()
        if chunk:
            chunks.append(chunk)
        buf = buf[cut:].lstrip()

    return chunks
