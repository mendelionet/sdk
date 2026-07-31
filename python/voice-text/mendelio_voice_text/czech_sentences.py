"""Czech sentence-boundary primitives shared by every Mendelio speech path.

WHY THIS PACKAGE EXISTS
-----------------------
Two things in this repo have to answer the same question — "where may I cut this Czech text
so the TTS still sounds right?" — and until now only one of them knew the answer.

The live path learned it the hard way, in production, and the knowledge is not derivable:
NLTK's `match_endofsentence` accepts `Ing.` as a sentence end at the moment the `.` arrives
(it needs to see "Svoboda" to know better, and mid-stream that word does not exist yet). So
`CZECH_ABBREVIATIONS` is not a nicety — it is the list that stops the synthesiser from
stopping dead after "Dr." and starting a new sentence at "Novák".

The batch path (podcast, Mendelio Voice) needs exactly the same answer, for a different
reason: a single un-split `model.generate()` is NOT preemptible, so an over-long chunk pins
the GPU and every live session waits behind it.

Same question, same answer, one implementation. What differs between the callers is the
TUNING, not the algorithm — see `synthesis_split.py`.

WHAT IS HERE AND WHAT IS NOT
----------------------------
Only pure functions over `str`. No pipecat, no asyncio, no I/O — deliberately, because the
live path's `ChunkedTextAggregator` is a STREAMING state machine (char-by-char, deferred
flush, delta boundaries) and the batch path has the whole text up front. The streaming
machine is not shared and must not be: batch would have to fake a stream to use it.

The primitives are shared. The drivers are not.

PROVENANCE
----------
Lifted verbatim (behaviour-for-behaviour) from
`services/voice-orchestrator/services/chunked_text_aggregator.py` and `services/stream_emit.py`.
The orchestrator is the ORIGIN, not a copy of this — this is where its knowledge moved to.
Until the orchestrator's Docker build context is widened to see this package, it still runs
its own copy; that duplication is in-flight, not the design, and closes with that commit.
"""

from __future__ import annotations

# Common Czech abbreviations ending in `.`. When a buffer ends with one of these, the period
# belongs to the abbreviation and is NOT a sentence end.
#
# This list is the whole point of the module. Do not "tidy" it by deleting entries that look
# unlikely: every one of them is a place the synthesiser would otherwise take a full stop.
CZECH_ABBREVIATIONS = frozenset({
    # Academic / professional titles (most likely LLM-generated)
    "dr", "mgr", "ing", "bc", "phdr", "mudr", "judr", "rndr", "mvdr",
    "prof", "doc", "csc", "drsc", "ph", "phd", "mba",
    # Honorifics + references
    "p", "pí", "č", "čp", "str", "roč", "kap", "obr", "tab", "sv",
    "stran", "strany",
    # Standard Czech list abbreviations
    "tj", "tzn", "tzv", "atd", "apod", "např", "resp", "popř", "příp",
    "mj", "vč", "cca", "př", "ppř", "zkr", "aj", "atp", "vs", "kupř",
    "event", "zvl", "pozn", "čís",
    # Mid-token pieces of multi-word abbreviations — "n." inside
    # "př. n. l." / "n. m." must not read as a sentence end, or the
    # spoken-abbreviation expander downstream only ever sees fragments.
    "n", "sb",
    # Quantities the tutoring content actually contains
    "mil", "mld", "tis", "sek",
    # Business / quantities
    "max", "min", "tzv", "spol", "a.s", "s.r.o",
    # Units / time (short — an LLM may slip these in numeric contexts)
    "hod", "sec", "kg", "km", "cm", "mm", "m", "l", "ml", "kč",
    # Temporal
    "r", "st", "stol", "pol", "př.n.l", "n.l",
    # Geo / postal
    "okr", "kr", "ul", "nám", "tř",
})

# Characters a word may end on. `.!?` are IN the set on purpose: a cut placed after a
# terminator keeps the terminator with its sentence, which is what carries the intonation.
WORD_BOUNDARY_PUNCT = frozenset(".!?,;:—–-\"'“”„«»")


def ends_in_abbreviation(buf: str) -> bool:
    """True when `buf` ends with a Czech abbreviation + `.`.

    Covers known multi-letter abbreviations (`Dr.`, `tzv.`, `apod.` …) and single-capital
    initials (`J.` in `J. Novák`). The period is part of the token, not a sentence end.
    """
    if not buf.endswith("."):
        return False
    trimmed = buf[:-1].rstrip()
    # Last whitespace position — the token under inspection is whatever follows it.
    # `rfind` returns -1 when no whitespace exists, which makes `token = trimmed[0:]`
    # (the whole buffer), which is what we want.
    last_ws = max(trimmed.rfind(" "), trimmed.rfind("\t"), trimmed.rfind("\n"))
    token = trimmed[last_ws + 1:] if last_ws >= 0 else trimmed
    if not token:
        return False
    # Initial like "J." or "V." — a single capitalised letter.
    if len(token) == 1 and token.isalpha() and token.isupper():
        return True
    # Czech documents vary ("Dr." / "dr." / "DR."), so match case-insensitively.
    return token.lower() in CZECH_ABBREVIATIONS


def find_sentence_end(buf: str) -> int:
    """Position AFTER the first real sentence terminator in `buf`, or 0 if there is none.

    Scans forward for `.!?`, skipping any `.` that belongs to a Czech abbreviation or a
    single-letter initial. This substitutes for NLTK's `match_endofsentence`, which cannot
    do this reliably without the following word.
    """
    i = 0
    n = len(buf)
    while i < n:
        ch = buf[i]
        if ch in ".!?":
            if ch == "." and ends_in_abbreviation(buf[: i + 1]):
                i += 1
                continue
            return i + 1
        i += 1
    return 0


def split_at_word_boundary(text: str) -> tuple[str, str]:
    """Split at the last word boundary; return `(emit, holdback)`.

    A mid-word cut is the one failure this must never allow: OmniVoice voices a partial
    token as broken syllables with the wrong prosody. When `text` is a single boundary-less
    token there is no safe cut, and `("", text)` says so rather than inventing one — the
    caller decides whether to flush it raw or wait for more.
    """
    if not text:
        return "", ""
    last = text[-1]
    if last.isspace() or last in WORD_BOUNDARY_PUNCT:
        return text, ""
    for i in range(len(text) - 1, -1, -1):
        ch = text[i]
        if ch.isspace() or ch in WORD_BOUNDARY_PUNCT:
            return text[: i + 1], text[i + 1:]
    return "", text
