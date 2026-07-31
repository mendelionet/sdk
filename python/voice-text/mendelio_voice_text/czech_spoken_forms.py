"""Deterministic high-confidence Czech spoken forms for Mendelio speech.

WHY THIS MODULE EXISTS
----------------------
OmniVoice's Czech grapheme→phoneme rules read abbreviations literally —
"km/h" comes out as garbled letter salad, "př. n. l." as three broken
syllables. Both TTS paths (live orchestrator via ``response_scrub`` and the
batch podcast renderer via ``omnivoice_rules``) already rewrite DIGITS to
Czech words before synthesis; this module is the same principle applied to
ABBREVIATIONS and contextual ordinals, shared so the lexical and grammatical
knowledge exists exactly once.

No ready-made Czech abbreviation→expansion table exists in the open-source
TTS world (NeMo has no ``cs``, espeak-ng only respells units phonetically).
The entries here are curated from the ÚJČ Internetová jazyková příručka
(https://prirucka.ujc.cas.cz/?id=780, ?id=782, ?id=785) filtered to what the
tutoring content actually contains (maturita knowledge JSON, prepared
activities, minigames) plus the standard written-Czech connectors an LLM
will emit on its own.

DESIGN
------
* Units are DIGIT-ANCHORED ("90 km/h", "78 km²") and pick the grammatical
  form from the value: exact 1 → singular with a gender-correct numeral
  ("jeden kilometr", "jedna koruna"), exact 2 → "dva/dvě" + plural,
  3–4 → plural (digits left for the number pass), everything else →
  genitive plural. Decimals keep their digits and take the genitive.
* The trailing period of a dotted abbreviation is kept only when the next
  non-space character is uppercase or the text ends — i.e. when the period
  plausibly also closes the sentence ("… atd. Další věta.").
* ``tzv.`` and ``sv.`` agree with the FOLLOWING word via an ending
  heuristic; documented at the rules. Ambiguous single letters that would
  misfire ("s", "t", "A", bare "st.") are deliberately absent.
* CONFIDENCE POLICY: a rule belongs here only when it is right ~99 % of the
  time in real content. Ambiguous forms stay untranslated ("min" without a
  dot and without an adjacent digit, bare "st.", "s.", "fa") — an unread
  abbreviation is a smaller failure than a wrong word. The LLM pass exists
  for the semantic cases; this module is the always-on floor.
* Normalization must run BEFORE the digit→words pass of the caller, so the
  numbers it leaves in place ("3 metry") still get spoken.

Pure functions over ``str`` only, like the rest of this package.
"""

from __future__ import annotations

import re

from mendelio_voice_text.czech_numbers import cardinal, decimal, dotted

_ONE_BY_GENDER = {"M": "jeden", "F": "jedna", "N": "jedno"}
_TWO_BY_GENDER = {"M": "dva", "F": "dvě", "N": "dvě"}

# unit token → (singular, plural 2–4, genitive plural, gender)
# Foreign-looking stems (joule, coulomb) are respelled phonetically because
# the Czech G2P would read them letter-by-letter — same trick as the podcast
# renderer's PRONUNCIATION_OVERRIDES.
_UNIT_FORMS: dict[str, tuple[str, str, str, str]] = {
    "km/h": ("kilometr za hodinu", "kilometry za hodinu", "kilometrů za hodinu", "M"),
    "km/hod": ("kilometr za hodinu", "kilometry za hodinu", "kilometrů za hodinu", "M"),
    "km/s": ("kilometr za sekundu", "kilometry za sekundu", "kilometrů za sekundu", "M"),
    "m/s²": ("metr za sekundu na druhou", "metry za sekundu na druhou", "metrů za sekundu na druhou", "M"),
    "m/s2": ("metr za sekundu na druhou", "metry za sekundu na druhou", "metrů za sekundu na druhou", "M"),
    "m/s": ("metr za sekundu", "metry za sekundu", "metrů za sekundu", "M"),
    "km²": ("kilometr čtvereční", "kilometry čtvereční", "kilometrů čtverečních", "M"),
    "km2": ("kilometr čtvereční", "kilometry čtvereční", "kilometrů čtverečních", "M"),
    "m²": ("metr čtvereční", "metry čtvereční", "metrů čtverečních", "M"),
    "m2": ("metr čtvereční", "metry čtvereční", "metrů čtverečních", "M"),
    "cm²": ("centimetr čtvereční", "centimetry čtvereční", "centimetrů čtverečních", "M"),
    "m³": ("metr krychlový", "metry krychlové", "metrů krychlových", "M"),
    "m3": ("metr krychlový", "metry krychlové", "metrů krychlových", "M"),
    "cm³": ("centimetr krychlový", "centimetry krychlové", "centimetrů krychlových", "M"),
    "µm": ("mikrometr", "mikrometry", "mikrometrů", "M"),
    "μm": ("mikrometr", "mikrometry", "mikrometrů", "M"),
    "µC": ("mikrokulomb", "mikrokulomby", "mikrokulombů", "M"),
    "μC": ("mikrokulomb", "mikrokulomby", "mikrokulombů", "M"),
    "km": ("kilometr", "kilometry", "kilometrů", "M"),
    "cm": ("centimetr", "centimetry", "centimetrů", "M"),
    "mm": ("milimetr", "milimetry", "milimetrů", "M"),
    "m": ("metr", "metry", "metrů", "M"),
    "kg": ("kilogram", "kilogramy", "kilogramů", "M"),
    "mg": ("miligram", "miligramy", "miligramů", "M"),
    "g": ("gram", "gramy", "gramů", "M"),
    "ha": ("hektar", "hektary", "hektarů", "M"),
    "hl": ("hektolitr", "hektolitry", "hektolitrů", "M"),
    "ml": ("mililitr", "mililitry", "mililitrů", "M"),
    "l": ("litr", "litry", "litrů", "M"),
    "kWh": ("kilowatthodina", "kilowatthodiny", "kilowatthodin", "F"),
    "kW": ("kilowatt", "kilowatty", "kilowattů", "M"),
    "MW": ("megawatt", "megawatty", "megawattů", "M"),
    "W": ("watt", "watty", "wattů", "M"),
    "kJ": ("kilodžaul", "kilodžauly", "kilodžaulů", "M"),
    "kcal": ("kilokalorie", "kilokalorie", "kilokalorií", "F"),
    "kHz": ("kilohertz", "kilohertze", "kilohertzů", "M"),
    "MHz": ("megahertz", "megahertze", "megahertzů", "M"),
    "GHz": ("gigahertz", "gigahertze", "gigahertzů", "M"),
    "Hz": ("hertz", "hertze", "hertzů", "M"),
    "V": ("volt", "volty", "voltů", "M"),
    "N": ("newton", "newtony", "newtonů", "M"),
    "°C": ("stupeň Celsia", "stupně Celsia", "stupňů Celsia", "M"),
    "°F": ("stupeň Fahrenheita", "stupně Fahrenheita", "stupňů Fahrenheita", "M"),
    "°": ("stupeň", "stupně", "stupňů", "M"),
    "Kč": ("koruna", "koruny", "korun", "F"),
    "CZK": ("koruna", "koruny", "korun", "F"),
    "€": ("euro", "eura", "eur", "N"),
    "EUR": ("euro", "eura", "eur", "N"),
    "$": ("dolar", "dolary", "dolarů", "M"),
    "USD": ("dolar", "dolary", "dolarů", "M"),
    "£": ("libra", "libry", "liber", "F"),
    "GBP": ("libra", "libry", "liber", "F"),
    # "%" belongs to the table so the preposition pass can decline it
    # ("mezi pěti a deseti procenty"); consumers' own percent handling only
    # ever sees digit-adjacent "%", so there is no double conversion.
    "%": ("procento", "procenta", "procent", "N"),
    "‰": ("promile", "promile", "promile", "N"),
    # Angular/geographic coordinates: 12′ 30″ (U+2032/U+2033, not apostrophes).
    "′": ("minuta", "minuty", "minut", "F"),
    "″": ("vteřina", "vteřiny", "vteřin", "F"),
    "kB": ("kilobajt", "kilobajty", "kilobajtů", "M"),
    "KB": ("kilobajt", "kilobajty", "kilobajtů", "M"),
    "MB": ("megabajt", "megabajty", "megabajtů", "M"),
    "GB": ("gigabajt", "gigabajty", "gigabajtů", "M"),
    "TB": ("terabajt", "terabajty", "terabajtů", "M"),
    "mil.": ("milion", "miliony", "milionů", "M"),
    "mld.": ("miliarda", "miliardy", "miliard", "F"),
    "tis.": ("tisíc", "tisíce", "tisíc", "M"),
    "hod.": ("hodina", "hodiny", "hodin", "F"),
    "hod": ("hodina", "hodiny", "hodin", "F"),
    "min.": ("minuta", "minuty", "minut", "F"),
    "min": ("minuta", "minuty", "minut", "F"),
    "sek.": ("sekunda", "sekundy", "sekund", "F"),
    "sec.": ("sekunda", "sekundy", "sekund", "F"),
    "sek": ("sekunda", "sekundy", "sekund", "F"),
}

# Longest token first so "km/h" wins over "km", "mm" over "m", "min." over "m".
_UNIT_ALTERNATION = "|".join(
    re.escape(tok) for tok in sorted(_UNIT_FORMS, key=len, reverse=True)
)
# A unit not ending in "." must not be a prefix of a longer word ("km" in
# "kmen"); the lookahead forbids a following letter. Dotted units carry
# their own terminator. Lookbehind keeps clock times (14:30), decimals'
# tails and hyphenated IDs from anchoring a unit.
_UNIT_RE = re.compile(
    rf"(?<![\w,.:/-])(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>{_UNIT_ALTERNATION})"
    rf"(?![^\W\d_])"
)

# --- Era / epoch — must run before the unit pass so "l." is never a litre.
# `p[řr]` also accepts the diacritics-less "pr. n. l." seen in raw content.
_ERA_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bp[řr]\.\s*n\.\s*l\.", re.IGNORECASE), "před naším letopočtem"),
    (re.compile(r"\bp[řr]\.\s*Kr\.", re.IGNORECASE), "před Kristem"),
    (re.compile(r"\bpo\s+Kr\.", re.IGNORECASE), "po Kristu"),
    (re.compile(r"\bn\.\s*l\.", re.IGNORECASE), "našeho letopočtu"),
    (re.compile(r"(?<=\d)\s*m\s+n\.\s*m\.", re.IGNORECASE), " metrů nad mořem"),
    (re.compile(r"\bn\.\s*m\.", re.IGNORECASE), "nad mořem"),
]

# Decades: "70. léta / let / letech" → "sedmdesátá léta / sedmdesátých let /
# sedmdesátých letech". Scoped to a following "lét"/"let" word so plain
# ordinals ("70. výročí") are untouched. The decade ordinal agrees with the
# noun form: nominative "-á" before "léta", genitive/locative "-ých" else.
_DECADE_ORDINAL = {
    20: "dvacát", 30: "třicát", 40: "čtyřicát", 50: "padesát",
    60: "šedesát", 70: "sedmdesát", 80: "osmdesát", 90: "devadesát",
}
_DECADE_RE = re.compile(
    r"\b(?P<dec>[2-9]0)\.\s+(?P<noun>lét[a-z]*|let[a-z]*)",
    re.IGNORECASE,
)


def _decade_repl(match: re.Match[str]) -> str:
    stem = _DECADE_ORDINAL[int(match.group("dec"))]
    noun = match.group("noun")
    # "léta" (nominative plural neuter) → "-á léta"; every other form
    # ("let", "letech", "letům") is oblique → "-ých".
    ending = "á" if noun.lower() in ("léta", "leta") else "ých"
    return f"{stem}{ending} {noun}"


# Numbers with a separator, read by NATURAL Czech pronunciation:
#   * COMMA is the Czech decimal separator → a real fraction ("3,14" → "tři
#     celé čtrnáct").
#   * DOT between digits is a hierarchical label — chapter, section, version —
#     NOT a decimal: "10.1" is said "deset tečka jedna", not "deset celá
#     jedna". (Imported English decimals with a dot are rare in this content
#     and "tečka" is still an acceptable reading for them.)
# Both guard against clock times and multi-part versions ("2.5.1") by
# forbidding another separator+digit on either side.
# Frac lookahead allows trailing punctuation ("10.1," "10.1:" "3,5.") but
# blocks a further digit or separator+digit — the latter is another version
# level ("2.5.1"), a clock tail ("10.1:30") or a malformed decimal, left
# untouched.
_FRAC_END = r"(?![\w/-])(?![.,:]\d)"
_DECIMAL_COMMA_RE = re.compile(
    rf"(?<![\w.,:/-])(?P<whole>\d{{1,4}}),(?P<frac>\d{{1,4}}){_FRAC_END}"
)
_DOTTED_NUMBER_RE = re.compile(
    rf"(?<![\w.,:/-])(?P<whole>\d{{1,4}})\.(?P<frac>\d{{1,4}}){_FRAC_END}"
)


def _decimal_comma_repl(match: re.Match[str]) -> str:
    return decimal(int(match.group("whole")), match.group("frac"))


def _dotted_repl(match: re.Match[str]) -> str:
    return dotted(int(match.group("whole")), match.group("frac"))


# "min./max." BEFORE a number is "minimálně/maximálně", not a unit
# ("nech ho mluvit min. 30 sekund").
_MIN_BEFORE_DIGIT_RE = re.compile(r"\bmin\.\s*(?=\d)", re.IGNORECASE)
_MAX_BEFORE_DIGIT_RE = re.compile(r"\bmax\.\s*(?=\d)", re.IGNORECASE)

# One lexeme table owns every contextual ordinal from 1 through 31. The
# genitive neuter form is the lossless base: nominative, locative and
# instrumental endings are deterministic for both hard (-ého) and soft (-ího)
# adjective paradigms.
_ORDINAL_GENITIVE = {
    1: "prvního", 2: "druhého", 3: "třetího", 4: "čtvrtého", 5: "pátého",
    6: "šestého", 7: "sedmého", 8: "osmého", 9: "devátého", 10: "desátého",
    11: "jedenáctého", 12: "dvanáctého", 13: "třináctého", 14: "čtrnáctého",
    15: "patnáctého", 16: "šestnáctého", 17: "sedmnáctého", 18: "osmnáctého",
    19: "devatenáctého", 20: "dvacátého", 21: "jednadvacátého",
    22: "dvaadvacátého", 23: "třiadvacátého", 24: "čtyřiadvacátého",
    25: "pětadvacátého", 26: "šestadvacátého", 27: "sedmadvacátého",
    28: "osmadvacátého", 29: "devětadvacátého", 30: "třicátého",
    31: "jednatřicátého",
}

_CZECH_MONTHS_GENITIVE = (
    "ledna", "února", "unora", "března", "brezna", "dubna", "května",
    "kvetna", "června", "cervna", "července", "cervence", "srpna", "září",
    "zari", "října", "rijna", "listopadu", "prosince",
)
_DATE_RE = re.compile(
    r"(?<![\w/.,-])(?P<day>\d{1,2})\.(?P<space>\s+)(?P<month>"
    + "|".join(_CZECH_MONTHS_GENITIVE)
    + r")\b",
    re.IGNORECASE,
)

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}
_ROMAN_DIGITS = ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
_ORDINAL_TOKEN_RE = re.compile(r"(?<!\w)(?P<token>\d{1,3}|[A-Za-z]+)\.")
_CENTURY_NOUN_RE = r"(?:stoletím|tisíciletím|století|tisíciletí|stol\.|st\.)"
_CENTURY_SEPARATOR_RE = (
    r"(?:\s*,\s*(?:(?:a|nebo)\s+)?|\s+(?:a|nebo|až|do)\s+|\s*[–—-]\s*)"
)
_CENTURY_GROUP_RE = re.compile(
    rf"(?<![\w.])(?P<body>(?:\d{{1,3}}|[A-Za-z]+)\."
    rf"(?:{_CENTURY_SEPARATOR_RE}(?:(?:v|ve|o|po|od|do|z|ze|bez|u|"
    rf"kolem|okolo)\s+)?(?:\d{{1,3}}|[A-Za-z]+)\.)*)"
    rf"(?P<space>\s+)(?P<noun>{_CENTURY_NOUN_RE})",
    re.IGNORECASE,
)
_LOCATIVE_CENTURY_PREPOSITIONS = frozenset({"v", "ve", "o", "po"})
_GENITIVE_CENTURY_PREPOSITIONS = frozenset(
    {
        "od", "do", "z", "ze", "bez", "u", "kolem", "okolo", "během",
        "koncem", "počátkem",
    }
)
_CENTURY_PRECEDING_FRAGMENT_RE = re.compile(
    r"(?P<word>[A-Za-zÁČĎÉĚÍŇÓŘŠŤÚŮÝŽáčďéěíňóřšťúůýž]+)\s*$"
)
_INCOMPLETE_GROUP_PREFIX_RE = re.compile(
    r"(?:\d+|[A-Za-z]+)\s+(?:a|nebo|až|do)\s*$", re.IGNORECASE
)
_LOCAL_PREPOSITION_RE = re.compile(
    r"(?:^|\s)(v|ve|o|po|od|do|z|ze|bez|u|kolem|okolo)\s*$",
    re.IGNORECASE,
)


def _date_repl(match: re.Match[str]) -> str:
    ordinal = _ORDINAL_GENITIVE.get(int(match.group("day")))
    if ordinal is None:
        return match.group(0)
    return f"{ordinal}{match.group('space')}{match.group('month')}"


def _roman_encode(value: int) -> str:
    result: list[str] = []
    for amount, symbol in _ROMAN_DIGITS:
        while value >= amount:
            result.append(symbol)
            value -= amount
    return "".join(result)


def _ordinal_value(token: str) -> int | None:
    if token.isdigit():
        value = int(token)
        return value if value in _ORDINAL_GENITIVE else None
    if token != token.upper() or any(char not in _ROMAN_VALUES for char in token):
        return None
    value = 0
    for index, char in enumerate(token):
        current = _ROMAN_VALUES[char]
        following = _ROMAN_VALUES[token[index + 1]] if index + 1 < len(token) else 0
        value += -current if current < following else current
    if value not in _ORDINAL_GENITIVE or _roman_encode(value) != token:
        return None
    return value


def _ordinal_for_case(value: int, case: str) -> str:
    base = _ORDINAL_GENITIVE[value]
    if case == "gen":
        return base
    if base.endswith("ího"):
        stem = base[:-3]
        return stem + {"nom": "í", "loc": "ím", "ins": "ím"}[case]
    stem = base[:-3]
    return stem + {"nom": "é", "loc": "ém", "ins": "ým"}[case]


def _group_case(source: str, start: int, noun: str) -> tuple[str, bool]:
    if noun.lower() in {"stoletím", "tisíciletím"}:
        return "ins", False
    prefix = source[:start]
    if not prefix.strip() or re.search(r"[.!?]\s*$", prefix):
        return "nom", True
    phrase = re.search(r"\bna\s+přelomu\s*$", prefix, re.IGNORECASE)
    if phrase:
        return "gen", False
    preceding = _CENTURY_PRECEDING_FRAGMENT_RE.search(prefix)
    if preceding is None:
        return "nom", False
    word = preceding.group("word").lower()
    if word in _LOCATIVE_CENTURY_PREPOSITIONS:
        return "loc", False
    if word in _GENITIVE_CENTURY_PREPOSITIONS:
        return "gen", False
    return "gen", False


def _century_group_repl(match: re.Match[str]) -> str:
    body = match.group("body")
    prefix = match.string[:match.start()]
    # A missing ordinal dot before a coordination must not let the regex start
    # at a later valid member and produce a half-normalized group.
    if _INCOMPLETE_GROUP_PREFIX_RE.search(prefix):
        return match.group(0)

    tokens = list(_ORDINAL_TOKEN_RE.finditer(body))
    values = [_ordinal_value(token.group("token")) for token in tokens]
    if not tokens or any(value is None for value in values):
        return match.group(0)

    group_case, sentence_initial = _group_case(
        match.string, match.start(), match.group("noun")
    )
    pieces: list[str] = []
    cursor = 0
    for index, (token, value) in enumerate(zip(tokens, values)):
        between = body[cursor:token.start()]
        local_prep = _LOCAL_PREPOSITION_RE.search(between)
        ordinal_case = group_case
        if local_prep:
            prep = local_prep.group(1).lower()
            if prep in _LOCATIVE_CENTURY_PREPOSITIONS:
                ordinal_case = "loc"
            elif prep in _GENITIVE_CENTURY_PREPOSITIONS:
                ordinal_case = "gen"
        if re.fullmatch(r"\s*[–—-]\s*", between):
            between = " až "
        spoken = _ordinal_for_case(value, ordinal_case)
        if index == 0 and sentence_initial:
            spoken = spoken[:1].upper() + spoken[1:]
        pieces.extend((between, spoken))
        cursor = token.end()

    noun = match.group("noun")
    if noun.lower() in {"st.", "stol."}:
        noun = "století"
    return "".join(pieces) + match.group("space") + noun

# "sv." before a capitalised name. Czech needs the adjective to agree with
# the name's case; the name ENDING is a cheap, mostly-right proxy for the
# case the content actually uses ("sv. Václav" nom., "chrám sv. Víta" gen.,
# "sv. Ludmily" gen. fem.).
_SV_RE = re.compile(
    r"\b(?P<sv>[Ss]v)\.\s+(?=(?P<name>[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\wáčďéěíňóřšťúůýž]+))"
)

# "tzv." agrees with the following word; its ending picks the form
# ("tzv. studená válka" → takzvaná, "tzv. mloci" → takzvaní).
_TZV_RE = re.compile(r"\b(?P<tzv>[Tt])zv\.\s*(?=(?P<next>[\wáčďéěíňóřšťúůýž]+))?")

# ---------------------------------------------------------------------------
# Preposition-driven numeral declension (ÚJČ ?id=792, ?id=671, ?id=791).
# ---------------------------------------------------------------------------
# "od 5 km" must read "od pěti kilometrů", not "od pět". Deterministic thanks
# to two facts from the grammar: (1) these prepositions govern exactly one
# case, and (2) numerals 5–99 share a single oblique form (G=D=L=I "pěti"),
# so even the ambiguous prepositions only need to know oblique-vs-not for
# most values. Confidence scoping (the ~99 % policy):
#   * numbers 1–99 only — hundreds decline irregularly ("před sto lety" is
#     indeclinable by ÚJČ), years must never decline ("od 1620" stays), so
#     3+ digits are left for the plain number pass;
#   * no ordinals ("od 5. století" belongs to the century pass) and no
#     decimals;
#   * a following UNIT token is declined only under genitive prepositions,
#     where its genitive plural IS the unit table's "many" form; other cases
#     would need unit paradigms the table does not carry — skipped, and the
#     phrase falls through to today's behaviour.
_PREP_CASE = {
    **{p: "gen" for p in (
        "bez", "od", "do", "z", "ze", "u", "kolem", "okolo", "vedle",
        "kromě", "krom", "místo", "podle", "podél", "dle", "během",
        "pomocí", "prostřednictvím", "poblíž", "ohledně", "včetně",
        "namísto", "uprostřed", "vyjma",
    )},
    **{p: "dat" for p in (
        "k", "ke", "ku", "kvůli", "díky", "proti", "oproti", "naproti",
        "vůči", "navzdory",
    )},
    "při": "loc",
    # With a numeral these read instrumental in practice ("před pěti lety",
    # "mezi pěti kandidáty", "s pěti lidmi") — the accusative/directional
    # readings are rare enough with bare numbers to clear the 99 % bar.
    "s": "ins", "se": "ins", "před": "ins", "mezi": "ins",
}
# Ambiguous prepositions where the FOLLOWING noun's plural ending names the
# case: "-ách/-ích/-ech" locative, "-ám/-ům/-ím" dative, "-ami/-emi/-mi"
# instrumental ("po pěti minutách" vs "o pět minut"). No oblique ending → the
# accusative reading → numeral stays in its base form (today's behaviour).
_AMBIG_PREPS = ("o", "po", "v", "ve", "na")
_OBLIQUE_NOUN_ENDINGS = [
    (re.compile(r"(ách|ích|ech)$"), "loc"),
    (re.compile(r"(ám|ům|ím)$"), "dat"),
    (re.compile(r"(ami|emi|mi)$"), "ins"),
]
_ALL_PREPS = sorted({*_PREP_CASE, *_AMBIG_PREPS}, key=len, reverse=True)
_PREP_NUMBER_RE = re.compile(
    rf"(?P<prep>\b(?:{'|'.join(_ALL_PREPS)}))\s+(?P<num>\d{{1,2}})"
    rf"(?!\d|[.,]\d|\.)"
    # Coordination/range: "od 3 do 5", "mezi 5 a 10", "po 5 až 10", "5–10".
    # Both numerals share the governed case; an en-dash reads "až".
    rf"(?:\s*(?P<conj>[–—-]|(?:a|až|nebo|do)\b)\s*(?P<num2>\d{{1,2}})(?!\d|[.,]\d|\.))?"
    rf"(?:\s*(?P<unit>{_UNIT_ALTERNATION})(?![^\W\d_]))?"
    # Lowercase-only despite IGNORECASE (inline (?-i:…)): a capitalized word
    # after the numeral is the next sentence or a proper noun, not the
    # governed noun whose ending should decide a case.
    rf"(?:\s+(?P<noun>(?-i:[a-záčďéěíňóřšťúůýž]+)))?",
    re.IGNORECASE,
)


# Genitive singular of a unit, derived from its nominative singular: feminine
# and neuter units already carry it as their 2–4 form ("koruny", "eura");
# masculine hard stems take -u, with the two soft exceptions named.
_MASC_GEN_SG_EXCEPTIONS = {"stupeň": "stupně", "tisíc": "tisíce"}


def _unit_genitive_singular(forms: tuple[str, str, str, str]) -> str:
    singular, few, _many, gender = forms
    if gender in ("F", "N"):
        return few
    head, _, rest = singular.partition(" ")
    head = _MASC_GEN_SG_EXCEPTIONS.get(head, head + "u")
    return f"{head} {rest}" if rest else head


# --- Oblique PLURAL unit forms (dat/loc/ins), derived word-by-word ---------
# The head noun declines by gender class, the two adjectives our units carry
# agree explicitly, and genitive attributes ("za hodinu", "Celsia", "na
# druhou") are frozen. Derivation is regular for every unit in the table;
# the soft masculines are the only exceptions and are named.
_MASC_SOFT_PL = {
    "stupeň": {"dat": "stupňům", "loc": "stupních", "ins": "stupni"},
    "tisíc": {"dat": "tisícům", "loc": "tisících", "ins": "tisíci"},
}
_UNIT_ADJECTIVES_PL = {
    "čtvereční": {"dat": "čtverečním", "loc": "čtverečních", "ins": "čtverečními"},
    "krychlový": {"dat": "krychlovým", "loc": "krychlových", "ins": "krychlovými"},
}
_MASC_PL_SUFFIX = {"dat": "ům", "loc": "ech", "ins": "y"}
_FEM_A_PL_SUFFIX = {"dat": "ám", "loc": "ách", "ins": "ami"}
_FEM_E_PL_SUFFIX = {"dat": "ím", "loc": "ích", "ins": "emi"}


def _decline_unit_plural(forms: tuple[str, str, str, str], case: str) -> str:
    singular, _few, _many, gender = forms
    words = singular.split(" ")
    head = words[0]
    if head == "promile":
        declined_head = "promile"  # indeclinable neuter
    elif head in _MASC_SOFT_PL:
        declined_head = _MASC_SOFT_PL[head][case]
    elif gender == "M":
        declined_head = head + _MASC_PL_SUFFIX[case]
    elif gender == "F" and head.endswith("a"):
        declined_head = head[:-1] + _FEM_A_PL_SUFFIX[case]
    elif gender == "F" and head.endswith("e"):
        declined_head = head[:-1] + _FEM_E_PL_SUFFIX[case]
    elif gender == "N" and head.endswith("o"):
        declined_head = head[:-1] + _MASC_PL_SUFFIX[case]  # hard neuter = hard masc plural endings
    else:
        declined_head = head
    tail = [
        _UNIT_ADJECTIVES_PL[w][case] if w in _UNIT_ADJECTIVES_PL else w
        for w in words[1:]
    ]
    return " ".join([declined_head, *tail])


# Instrumental SINGULAR for value 1 ("s 1 kg" → "s jedním kilogramem").
_MASC_INS_SG_EXCEPTIONS = {"stupeň": "stupněm", "tisíc": "tisícem"}
_UNIT_ADJECTIVES_INS_SG = {"čtvereční": "čtverečním", "krychlový": "krychlovým"}


def _unit_instrumental_singular(forms: tuple[str, str, str, str]) -> str:
    singular, _few, _many, gender = forms
    words = singular.split(" ")
    head = words[0]
    if head == "promile":
        declined_head = "promile"
    elif head in _MASC_INS_SG_EXCEPTIONS:
        declined_head = _MASC_INS_SG_EXCEPTIONS[head]
    elif gender == "M":
        declined_head = head + "em"
    elif gender == "F" and head.endswith("a"):
        declined_head = head[:-1] + "ou"
    elif gender == "F" and head.endswith("e"):
        declined_head = head[:-1] + "í"
    elif gender == "N" and head.endswith("o"):
        declined_head = head[:-1] + "em"
    else:
        declined_head = head
    tail = [
        _UNIT_ADJECTIVES_INS_SG.get(w, w)
        for w in words[1:]
    ]
    return " ".join([declined_head, *tail])


_ONE_BY_CASE_M = {"gen": "jednoho", "dat": "jednomu", "loc": "jednom", "ins": "jedním"}
_ONE_BY_CASE_F = {"gen": "jedné", "dat": "jedné", "loc": "jedné", "ins": "jednou"}


def _spoken_unit_for_case(
    unit: str, value: int, case: str
) -> str | None:
    """Declined unit phrase for prep-governed cases; None = no safe paradigm."""
    forms = _UNIT_FORMS[unit]
    if value == 1:
        one = (_ONE_BY_CASE_F if forms[3] == "F" else _ONE_BY_CASE_M)[case]
        if case == "gen":
            return f"{one} {_unit_genitive_singular(forms)}"
        if case == "ins":
            return f"{one} {_unit_instrumental_singular(forms)}"
        # dat/loc singular needs stem softening for feminines ("koruně") —
        # under the 99% policy that stays out; the caller leaves the text.
        return None
    if case == "gen":
        return f"{cardinal(value, 'gen')} {forms[2]}"  # gen pl = the "many" form
    return f"{cardinal(value, case)} {_decline_unit_plural(forms, case)}"


def _prep_number_repl(match: re.Match[str]) -> str:
    prep = match.group("prep")
    value = int(match.group("num"))
    conj = match.group("conj")
    num2 = match.group("num2")
    unit = match.group("unit")
    noun = match.group("noun") or ""
    case = _PREP_CASE.get(prep.lower())
    if case is None:  # ambiguous preposition — the noun ending decides
        for ending_re, ending_case in _OBLIQUE_NOUN_ENDINGS:
            if noun and ending_re.search(noun.lower()):
                case = ending_case
                break
        if case is None:
            return match.group(0)  # accusative reading — leave for the number pass
    tail = f" {noun}" if noun else ""

    # Coordination: both numerals share the case; the closing numeral carries
    # the unit ("mezi pěti a deseti kilometry"). Dashes read "až".
    coordination = ""
    if conj and num2:
        spoken_conj = "až" if conj in ("–", "—", "-") else conj
        coordination = f" {spoken_conj} "
        value2 = int(num2)

    if unit:
        closing_value = value2 if coordination else value
        spoken_unit = _spoken_unit_for_case(unit, closing_value, case)
        if spoken_unit is None:
            return match.group(0)
        # A dotted unit ("min.") may have carried the sentence's final period;
        # when no noun follows, restore it by the same next-char rule the
        # plain unit pass uses.
        if unit.endswith(".") and not noun:
            spoken_unit += _sentence_dot(match.string, match.end())
        if coordination:
            # The unit phrase already contains the declined closing numeral.
            return f"{prep} {cardinal(value, case)}{coordination}{spoken_unit}{tail}"
        return f"{prep} {spoken_unit}{tail}"
    if coordination:
        return f"{prep} {cardinal(value, case)}{coordination}{cardinal(value2, case)}{tail}"
    return f"{prep} {cardinal(value, case)}{tail}"


# Currency symbol BEFORE the number ("$100", "€ 50") — spoken Czech puts the
# currency after: "sto dolarů". The number keeps its digits (unless 1/2, same
# rule as the suffix pass) and the order swaps.
_CURRENCY_PREFIX_RE = re.compile(r"(?P<cur>[€$£])\s*(?P<num>\d+(?:[.,]\d+)?)")

# High-confidence standalone symbols. "&" only between spaces (never inside
# "AT&T"); "×"/"x" only glued to digits ("2 x 3", "10x") where it can only
# mean multiplication.
_AMPERSAND_RE = re.compile(r"(?<=\s)&(?=\s)")
_TIMES_BETWEEN_RE = re.compile(r"(?<=\d)\s*[×x]\s*(?=\d)")
_TIMES_SUFFIX_RE = re.compile(r"(?<=\d)\s*[×x](?![^\W\d_])")
# Policy (NVDA cs symbols.dic, ÚJČ ?id=785): a symbol is VERBALIZED when it
# carries lexical meaning (NVDA level `some`) and SILENTLY DROPPED when it is
# visual punctuation (`most`/`all` — prosody's job, not vocabulary's). ® and ™
# get dropped despite NVDA reading them: screen readers verbalize for
# accessibility completeness, but flowing human speech skips them outside
# legal contexts — the user's call, backed by common practice.
_SIMPLE_SYMBOLS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\s*[®™]"), ""),
    (re.compile(r"©"), "copyright"),
    (re.compile(r"№\s*"), "číslo "),
    # Digit-adjacent "§ 5" keeps its own rule (adds the space); this covers prose "dle §".
    (re.compile(r"§(?!\s*\d)"), "paragraf"),
    (re.compile(r"±"), "plus minus"),
    (re.compile(r"(?<=\d)\s*÷\s*(?=\d)"), " děleno "),
    (re.compile(r"(?<=[\s(])−\s*(?=\d)"), "mínus "),  # U+2212, digit-anchored
    (re.compile(r"~\s*(?=\d)"), "asi "),
    (re.compile(r"½"), "jedna polovina"),
    (re.compile(r"⅓"), "jedna třetina"),
    (re.compile(r"⅔"), "dvě třetiny"),
    (re.compile(r"¼"), "jedna čtvrtina"),
    (re.compile(r"¾"), "tři čtvrtiny"),
]

_CISLO_RE = re.compile(r"\bč(?:ís)?\.\s*(?=\d)", re.IGNORECASE)
_ROKU_RE = re.compile(r"\br\.\s*(?=\d{3,4}\b)")
_PARAGRAF_RE = re.compile(r"§\s*(?=\d)")
_CCA_RE = re.compile(r"\bcca\b\.?", re.IGNORECASE)

# token (without the dot), expansion, may-end-sentence flag. All matched
# case-insensitively with the leading capital preserved, except "Sb."
# (Sbírky zákonů) which is meaningful only capitalised.
_TEXTUAL: list[tuple[str, str, bool]] = [
    ("např", "například", False),
    ("kupř", "kupříkladu", False),
    ("atd", "a tak dále", True),
    ("apod", "a podobně", True),
    ("atp", "a tak podobně", True),
    ("aj", "a jiné", True),
    ("mj", "mimo jiné", False),
    ("tj", "to jest", False),
    ("tzn", "to znamená", False),
    ("resp", "respektive", False),
    ("popř", "popřípadě", False),
    ("příp", "případně", False),
    ("vč", "včetně", False),
    ("event", "eventuálně", False),
    ("zvl", "zvláště", False),
    ("pozn", "poznámka", False),
    ("vs", "versus", False),
]
_TEXTUAL_PATTERNS: list[tuple[re.Pattern[str], str, bool]] = [
    (re.compile(rf"\b{re.escape(tok)}\.", re.IGNORECASE), expansion, may_end)
    for tok, expansion, may_end in _TEXTUAL
]
_SB_RE = re.compile(r"\bSb\.")


def _sentence_dot(source: str, end_pos: int) -> str:
    """Return "." when the abbreviation's period plausibly also ended the
    sentence — next non-space char is uppercase, or the text ends here."""
    rest = source[end_pos:].lstrip()
    if not rest or rest[0].isupper():
        return "."
    return ""


def _match_case(expansion: str, matched: str) -> str:
    if matched[:1].isupper():
        return expansion[:1].upper() + expansion[1:]
    return expansion


def _spoken_amount(num_raw: str, forms: tuple[str, str, str, str]) -> str:
    singular, few, many, gender = forms
    if "," in num_raw or "." in num_raw:
        # A decimal governs the genitive SINGULAR ("0,4 stupně", "3,1 milionu",
        # "5,5 kilometru") — same rule as "0,5 metru" (ÚJČ ?id=792).
        whole, _, frac = num_raw.replace(".", ",").partition(",")
        if len(whole.lstrip("0") or "0") > 4:
            return f"{num_raw} {_unit_genitive_singular(forms)}"
        return f"{decimal(int(whole), frac)} {_unit_genitive_singular(forms)}"
    if len(num_raw.lstrip("0") or "0") > 4:
        # Leave the token numeric for the outer fixed-order driver, which reads
        # arbitrary-length untrusted integers digit by digit without int().
        return f"{num_raw} {many}"
    value = int(num_raw)
    if value == 1:
        return f"{_ONE_BY_GENDER[gender]} {singular}"
    if value == 2:
        return f"{_TWO_BY_GENDER[gender]} {few}"
    if value in (3, 4):
        return f"{num_raw} {few}"
    return f"{num_raw} {many}"


def _unit_repl(match: re.Match[str]) -> str:
    spoken = _spoken_amount(match.group("num"), _UNIT_FORMS[match.group("unit")])
    if match.group("unit").endswith("."):
        spoken += _sentence_dot(match.string, match.end())
    return spoken


def _currency_prefix_repl(match: re.Match[str]) -> str:
    return _spoken_amount(match.group("num"), _UNIT_FORMS[match.group("cur")])


def _sv_repl(match: re.Match[str]) -> str:
    name = match.group("name")
    ending = name[-1:].lower()
    if ending == "a":
        form = "svatého"  # gen. masc.: "chrám sv. Víta", "socha sv. Václava"
    elif ending in ("y", "e", "ě"):
        form = "svaté"  # gen./dat. fem.: "sv. Ludmily", "sv. Anežce"
    elif ending in ("u",) or name.endswith("ovi"):
        form = "svatému"
    else:
        form = "svatý"  # nom. masc.: "sv. Václav"
    return _match_case(form, match.group("sv")) + " "


def _tzv_repl(match: re.Match[str]) -> str:
    next_word = match.group("next") or ""
    ending = next_word[-1:].lower()
    if ending in ("a", "á"):
        form = "takzvaná"
    elif ending in ("é", "í", "o"):
        form = "takzvané"
    elif ending == "i":
        form = "takzvaní"
    elif ending == "y":
        form = "takzvané"
    else:
        form = "takzvaný"
    return _match_case(form, match.group("tzv")) + " "


def normalize_czech_spoken_forms(text: str) -> str:
    """Expand deterministic high-confidence Czech written forms for TTS.

    Czech-only — callers gate on language. Run it BEFORE any digit→words
    pass so the numbers this leaves in place still get spoken. Dates and
    century/millennium ordinal groups are consumed atomically before generic
    cardinal handling. Idempotent.
    """
    if not text:
        return text

    for pattern, expansion in _ERA_PATTERNS:
        text = pattern.sub(
            lambda m, e=expansion: e + _sentence_dot(m.string, m.end()), text
        )

    text = _MIN_BEFORE_DIGIT_RE.sub("minimálně ", text)
    text = _MAX_BEFORE_DIGIT_RE.sub("maximálně ", text)

    text = _DATE_RE.sub(_date_repl, text)
    text = _CENTURY_GROUP_RE.sub(_century_group_repl, text)

    # Decades ("70. let" → "sedmdesátých let") before the preposition pass so
    # the ordinal digit is not read as a cardinal.
    text = _DECADE_RE.sub(_decade_repl, text)

    # Declension by preposition consumes prep+number(+unit) whole, so it must
    # run before the unit and currency passes ever see the digits.
    text = _PREP_NUMBER_RE.sub(_prep_number_repl, text)

    # Currency-before-number swaps the order, so it must run before the
    # suffix unit pass ever sees the digits.
    text = _CURRENCY_PREFIX_RE.sub(_currency_prefix_repl, text)
    text = _UNIT_RE.sub(_unit_repl, text)

    # Decimals ("0,4" → "nula celá čtyři") and dotted labels ("10.1" → "deset
    # tečka jedna") AFTER units so "5,5 km" stays with the unit pass; only
    # bare numbers reach here. Before symbols/textual so a number never splits
    # into two standalone cardinals.
    text = _DECIMAL_COMMA_RE.sub(_decimal_comma_repl, text)
    text = _DOTTED_NUMBER_RE.sub(_dotted_repl, text)
    text = _TIMES_BETWEEN_RE.sub(" krát ", text)
    text = _TIMES_SUFFIX_RE.sub(" krát", text)
    text = _AMPERSAND_RE.sub("a", text)
    for pattern, spoken in _SIMPLE_SYMBOLS:
        text = pattern.sub(spoken, text)

    text = _SV_RE.sub(_sv_repl, text)
    text = _TZV_RE.sub(_tzv_repl, text)

    text = _CISLO_RE.sub("číslo ", text)
    text = _ROKU_RE.sub("roku ", text)
    text = _PARAGRAF_RE.sub("paragraf ", text)
    text = _CCA_RE.sub(lambda m: _match_case("cirka", m.group(0)), text)

    for pattern, expansion, may_end in _TEXTUAL_PATTERNS:
        def _textual_repl(
            m: re.Match[str], e: str = expansion, keep: bool = may_end
        ) -> str:
            out = _match_case(e, m.group(0))
            if keep:
                out += _sentence_dot(m.string, m.end())
            return out

        text = pattern.sub(_textual_repl, text)
    text = _SB_RE.sub(
        lambda m: "Sbírky" + _sentence_dot(m.string, m.end()), text
    )

    return text
