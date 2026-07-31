"""Czech cardinal numbers as spoken words — the canonical home of digit→words.

WHY THIS MODULE EXISTS
----------------------
Until 2026-07-21 the digit→words tables lived twice, verbatim: in the live
orchestrator (``response_scrub``) and in the podcast renderer
(``omnivoice_rules``). Same units, same teens, same "dvacetjedna" glue, same
"čtrnáct set" year style — two copies of one decision, drifting apart one
hotfix at a time. This module is where that knowledge moved; the consumers
import it and keep only their DRIVERS (which regex fires, on which text).

CASES
-----
``cardinal(n)`` is the historical nominative behaviour, byte-for-byte.
``cardinal(n, case=...)`` adds the oblique cases (genitive, dative, locative,
instrumental) needed by the preposition-driven declension pass in
``czech_spoken_forms`` — "od 5 km" must become "od pěti kilometrů", and the
preposition already names the case. Forms follow the ÚJČ paradigm tables;
compound tens decline BOTH parts glued the same way the nominative glues them
("dvaceti pěti" is kept as "dvacetipěti"? no — spoken Czech separates them,
and the glue exists only in the nominative for TTS prosody; oblique forms use
a space, which is how they are actually said).

SPOKEN-STYLE INVARIANTS (listened-to, do not "fix"):
  * 21 nominative is "dvacetjedna" — glued, including inside 1921.
  * Years 1100–1999 read as hundreds: "čtrnáct set třicet čtyři".
  * These are TTS prosody decisions from the live path, not typos.
"""

from __future__ import annotations

CASES = ("nom", "gen", "dat", "loc", "ins")

_UNITS_NOM = {
    0: "nula", 1: "jedna", 2: "dva", 3: "tři", 4: "čtyři",
    5: "pět", 6: "šest", 7: "sedm", 8: "osm", 9: "devět",
}
_TEENS_NOM = {
    10: "deset", 11: "jedenáct", 12: "dvanáct", 13: "třináct", 14: "čtrnáct",
    15: "patnáct", 16: "šestnáct", 17: "sedmnáct", 18: "osmnáct", 19: "devatenáct",
}
_TENS_NOM = {
    20: "dvacet", 30: "třicet", 40: "čtyřicet", 50: "padesát",
    60: "šedesát", 70: "sedmdesát", 80: "osmdesát", 90: "devadesát",
}
_HUNDREDS_NOM = {
    1: "sto", 2: "dvě stě", 3: "tři sta", 4: "čtyři sta", 5: "pět set",
    6: "šest set", 7: "sedm set", 8: "osm set", 9: "devět set",
}

# Oblique forms. gen/dat/loc share one form for 5+ ("pěti"), and for 2–4 the
# gen differs (dvou, tří, čtyř) while dat/loc/ins have their own. 1 declines
# like an adjective; TTS content overwhelmingly hits 2+ after prepositions,
# and "jedna" after a preposition ("od 1 km") reads fine declined masculine.
_OBLIQUE_UNITS = {
    # n: (gen, dat, loc, ins)
    1: ("jednoho", "jednomu", "jednom", "jedním"),
    2: ("dvou", "dvěma", "dvou", "dvěma"),
    3: ("tří", "třem", "třech", "třemi"),
    4: ("čtyř", "čtyřem", "čtyřech", "čtyřmi"),
    5: ("pěti",) * 3 + ("pěti",),
    6: ("šesti",) * 4,
    7: ("sedmi",) * 4,
    8: ("osmi",) * 4,
    9: ("devíti",) * 4,
}
_OBLIQUE_TEENS = {n: (word + "i",) * 4 for n, word in _TEENS_NOM.items()}
_OBLIQUE_TENS = {
    20: ("dvaceti",) * 4, 30: ("třiceti",) * 4, 40: ("čtyřiceti",) * 4,
    50: ("padesáti",) * 4, 60: ("šedesáti",) * 4, 70: ("sedmdesáti",) * 4,
    80: ("osmdesáti",) * 4, 90: ("devadesáti",) * 4,
}
# Hundreds decline both words: "dvou set", "třem stům", "pěti stech", "dvěma sty".
_STO = {"gen": "sta", "dat": "stu", "loc": "stu", "ins": "stem"}
_SET_PLURAL = {"gen": "set", "dat": "stům", "loc": "stech", "ins": "sty"}

_CASE_INDEX = {"gen": 0, "dat": 1, "loc": 2, "ins": 3}


def _under_100(n: int, case: str) -> str:
    if case == "nom":
        if n < 10:
            return _UNITS_NOM[n]
        if n < 20:
            return _TEENS_NOM[n]
        tens, unit = (n // 10) * 10, n % 10
        if unit == 0:
            return _TENS_NOM[tens]
        # Glued on purpose — the live path's spoken-prosody invariant.
        return f"{_TENS_NOM[tens]}{_UNITS_NOM[unit]}"
    idx = _CASE_INDEX[case]
    if n == 0:
        return "nule" if case in ("dat", "loc") else ("nuly" if case == "gen" else "nulou")
    if n < 10:
        return _OBLIQUE_UNITS[n][idx]
    if n < 20:
        return _OBLIQUE_TEENS[n][idx]
    tens, unit = (n // 10) * 10, n % 10
    if unit == 0:
        return _OBLIQUE_TENS[tens][idx]
    # Both parts decline, spoken with a space: "dvaceti pěti".
    return f"{_OBLIQUE_TENS[tens][idx]} {_OBLIQUE_UNITS[unit][idx]}"


def _hundreds_word(hundreds: int, case: str) -> str:
    if case == "nom":
        return _HUNDREDS_NOM[hundreds]
    if hundreds == 1:
        return _STO[case]
    if hundreds == 2:
        two = {"gen": "dvou", "dat": "dvěma", "loc": "dvou", "ins": "dvěma"}[case]
        return f"{two} {_SET_PLURAL[case] if case != 'gen' else 'set'}"
    prefix = _under_100(hundreds, case)
    return f"{prefix} {_SET_PLURAL[case]}"


def _under_1000(n: int, case: str) -> str:
    if n < 100:
        return _under_100(n, case)
    hundreds, rest = n // 100, n % 100
    prefix = _hundreds_word(hundreds, case)
    if rest == 0:
        return prefix
    return f"{prefix} {_under_100(rest, case)}"


def cardinal(n: int, case: str = "nom") -> str:
    """Spoken Czech cardinal for 0..9999.

    ``case="nom"`` reproduces the historical live-path output exactly
    (glued 21, "čtrnáct set" years). Oblique cases serve the
    preposition-driven declension pass; years keep the hundreds style with
    the prefix declined ("od čtrnácti set třiceti" is unnatural — year-like
    numbers after a preposition are read as plain numbers, so oblique cases
    use the thousand style throughout).
    """
    if case not in CASES:
        raise ValueError(f"unknown case {case!r}")
    if n < 1000:
        return _under_1000(n, case)
    if case == "nom" and 1100 <= n <= 1999:
        rest = n % 100
        prefix = f"{_under_100(n // 100, 'nom')} set"
        if rest == 0:
            return prefix
        return f"{prefix} {_under_100(rest, 'nom')}"
    thousands, rest = n // 1000, n % 1000
    if case == "nom":
        if thousands == 1:
            prefix = "tisíc"
        elif 2 <= thousands <= 4:
            prefix = f"{_UNITS_NOM[thousands]} tisíce"
        else:
            prefix = f"{_UNITS_NOM[thousands]} tisíc"
    else:
        idx = _CASE_INDEX[case]
        thousand_form = {"gen": "tisíc", "dat": "tisícům", "loc": "tisících", "ins": "tisíci"}[case]
        if thousands == 1:
            prefix = {"gen": "tisíce", "dat": "tisíci", "loc": "tisíci", "ins": "tisícem"}[case]
        else:
            prefix = f"{_OBLIQUE_UNITS[thousands][idx] if thousands < 10 else _under_100(thousands, case)} {thousand_form}"
    if rest == 0:
        return prefix
    return f"{prefix} {_under_1000(rest, case)}"


_CELA_BY_WHOLE = {0: "celá", 1: "celá"}  # 2–4 → celé, 5+ → celých


def _cela_form(whole: int) -> str:
    if whole in _CELA_BY_WHOLE:
        return _CELA_BY_WHOLE[whole]
    if 2 <= whole <= 4:
        return "celé"
    return "celých"


def _speak_fraction(frac_digits: str) -> str:
    """Digits after the separator: leading zeros spoken one by one, the rest
    as one cardinal ("05" → "nula pět", "14" → "čtrnáct")."""
    lead = len(frac_digits) - len(frac_digits.lstrip("0"))
    zeros = " ".join(["nula"] * lead)
    rest = frac_digits[lead:]
    return " ".join(x for x in (zeros, cardinal(int(rest)) if rest else "") if x)


def decimal(whole: int, frac_digits: str) -> str:
    """Decimal COMMA — a real fraction: "3,14" → "tři celé čtrnáct",
    "0,05" → "nula celá nula pět". The connector agrees with the whole part.
    """
    return f"{cardinal(whole)} {_cela_form(whole)} {_speak_fraction(frac_digits)}".rstrip()


def dotted(whole: int, frac_digits: str) -> str:
    """Dotted number — a hierarchical label (chapter/version), NOT a fraction:
    "10.1" → "deset tečka jedna". Read the way people actually say it.
    """
    return f"{cardinal(whole)} tečka {_speak_fraction(frac_digits)}".rstrip()


def percent_words(value: int) -> str:
    """"5 %" with the right gender/number: jedno procento, dvě procenta, pět procent."""
    if value == 1:
        return "jedno procento"
    if value == 2:
        return "dvě procenta"
    if 3 <= value <= 4:
        return f"{cardinal(value)} procenta"
    return f"{cardinal(value)} procent"
