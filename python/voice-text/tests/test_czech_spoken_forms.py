"""Czech spoken-form normalization through the package's public contract.

Fixtures are lifted from real tutoring content strings
(kinematika.json, cr-fyz.json, erben-kytice.json, ustava.json),
not invented — see the content audit that seeded the table.
"""

from __future__ import annotations

import pytest

from mendelio_voice_text.czech_spoken_forms import normalize_czech_spoken_forms


class TestUnits:
    def test_kmh_genitive(self):
        # "z" is a genitive preposition, so the declension pass words the
        # number too — "z devadesáti", not "z devadesát".
        assert (
            normalize_czech_spoken_forms("Když auto brzdí z 90 km/h na 0 za 5 sekund.")
            == "Když auto brzdí z devadesáti kilometrů za hodinu na 0 za 5 sekund."
        )

    def test_ms_and_ms_squared(self):
        out = normalize_czech_spoken_forms("rychlostí 30 m/s (g = 10 m/s²)")
        assert out == "rychlostí 30 metrů za sekundu (g = 10 metrů za sekundu na druhou)"

    def test_one_uses_gender_correct_numeral(self):
        assert normalize_czech_spoken_forms("ujel 1 km") == "ujel jeden kilometr"
        assert normalize_czech_spoken_forms("stojí 1 Kč") == "stojí jedna koruna"
        assert normalize_czech_spoken_forms("obsah 1 ‰") == "obsah jedno promile"

    def test_two_to_four_use_plural(self):
        assert normalize_czech_spoken_forms("2 km") == "dva kilometry"
        assert normalize_czech_spoken_forms("2 Kč") == "dvě koruny"
        assert normalize_czech_spoken_forms("3 km") == "3 kilometry"

    def test_celsius_and_area(self):
        assert normalize_czech_spoken_forms("+33 °C oproti vakuu") == "+33 stupňů Celsia oproti vakuu"
        assert (
            normalize_czech_spoken_forms("Plocha ČR: 78 866 km²")
            == "Plocha ČR: 78 866 kilometrů čtverečních"
        )

    def test_unit_never_eats_word_prefix(self):
        assert normalize_czech_spoken_forms("5 kmenů") == "5 kmenů"
        assert normalize_czech_spoken_forms("za 30 minut") == "za 30 minut"

    def test_decimal_unit_is_spoken(self):
        assert normalize_czech_spoken_forms("3,1 mil. v pohraničí") == "tři celé jedna milionu v pohraničí"

    def test_elevation(self):
        assert normalize_czech_spoken_forms("1602 m n. m.") == "1602 metrů nad mořem."

    def test_dotted_unit_keeps_sentence_final_period(self):
        assert (
            normalize_czech_spoken_forms("Trvá to 30 min. Pak končíme.")
            == "Trvá to 30 minut. Pak končíme."
        )


class TestEra:
    def test_pred_nasim_letopoctem(self):
        assert (
            normalize_czech_spoken_forms("ze 3. tisíciletí př. n. l. pochází epos")
            == "ze třetího tisíciletí před naším letopočtem pochází epos"
        )

    def test_without_diacritics(self):
        assert normalize_czech_spoken_forms("roku 500 pr. n. l.") == (
            "roku 500 před naším letopočtem."
        )

    def test_naseho_letopoctu_standalone(self):
        assert normalize_czech_spoken_forms("v roce 100 n. l. vládl") == (
            "v roce 100 našeho letopočtu vládl"
        )

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            (
                "Ve III. století př. Kr.",
                "Ve třetím století před Kristem.",
            ),
            (
                "Umění III. století před Kristem",
                "Umění třetího století před Kristem",
            ),
            (
                "Od III. do II. století před naším letopočtem",
                "Od třetího do druhého století před naším letopočtem",
            ),
        ],
    )
    def test_century_era_forms(self, source: str, expected: str):
        assert normalize_czech_spoken_forms(source) == expected

    def test_century_abbreviation(self):
        assert normalize_czech_spoken_forms("klasický 19. st. výklad") == (
            "klasický devatenáctého století výklad"
        )
        assert normalize_czech_spoken_forms("7. stol. př. n. l.") == (
            "Sedmé století před naším letopočtem."
        )


class TestContextualOrdinals:
    @pytest.mark.parametrize(
        ("arabic", "roman", "expected"),
        [
            ("19. století bylo bouřlivé", "XIX. století bylo bouřlivé", "Devatenácté století bylo bouřlivé"),
            ("Umění 19. století", "Umění XIX. století", "Umění devatenáctého století"),
            ("V 19. století", "V XIX. století", "V devatenáctém století"),
            ("Mezi 19. stoletím", "Mezi XIX. stoletím", "Mezi devatenáctým stoletím"),
            ("Ve 3. tisíciletí", "Ve III. tisíciletí", "Ve třetím tisíciletí"),
            ("Obraz 19. st.", "Obraz XIX. st.", "Obraz devatenáctého století"),
            ("Obraz 19. stol.", "Obraz XIX. stol.", "Obraz devatenáctého století"),
        ],
    )
    def test_arabic_and_roman_single_forms_are_equivalent(
        self, arabic: str, roman: str, expected: str
    ):
        assert normalize_czech_spoken_forms(arabic) == expected
        assert normalize_czech_spoken_forms(roman) == expected

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("Ve 13. a 14. století", "Ve třináctém a čtrnáctém století"),
            ("Filosofie XIX. a XX. století", "Filosofie devatenáctého a dvacátého století"),
            ("Na přelomu XIX.–XX. století", "Na přelomu devatenáctého až dvacátého století"),
            ("od XIII. do XIV. století", "od třináctého do čtrnáctého století"),
            ("XIX., XX. a XXI. století", "Devatenácté, dvacáté a jednadvacáté století"),
            ("mezi XIX. a XX. stoletím", "mezi devatenáctým a dvacátým stoletím"),
        ],
    )
    def test_groups_are_normalized_atomically(self, source: str, expected: str):
        assert normalize_czech_spoken_forms(source) == expected

    @pytest.mark.parametrize(
        "source",
        [
            "Ve XIX. a IIII. století",
            "Ve XIX. a IC. století",
            "Ve XIX. a XXXII. století",
            "Ve XIX a XX. století",
            "Ve xix. století",
            "Ve 0. století",
            "Ve XXXII. století",
        ],
    )
    def test_invalid_group_is_left_whole(self, source: str):
        assert normalize_czech_spoken_forms(source) == source

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("I. století", "První století"),
            ("IV. století", "Čtvrté století"),
            ("IX. století", "Deváté století"),
            ("XX. století", "Dvacáté století"),
            ("XXI. století", "Jednadvacáté století"),
            ("XXXI. století", "Jednatřicáté století"),
        ],
    )
    def test_canonical_roman_boundaries(self, source: str, expected: str):
        assert normalize_czech_spoken_forms(source) == expected

    @pytest.mark.parametrize(
        "source",
        [
            "Karel IV. vládl",
            "oddíl IV. popisuje postup",
            "Vitamin C",
            "MIX je akronym",
            "Bylo jich 20. Pak odešli.",
            "8. V. 1945",
        ],
    )
    def test_unrelated_ordinals_and_roman_tokens_are_untouched(self, source: str):
        assert normalize_czech_spoken_forms(source) == source

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("1. ledna", "prvního ledna"),
            ("21. června", "jednadvacátého června"),
            ("31. prosince", "jednatřicátého prosince"),
            ("21. cervna", "jednadvacátého cervna"),
            ("0. ledna", "0. ledna"),
            ("32. ledna", "32. ledna"),
        ],
    )
    def test_dates(self, source: str, expected: str):
        assert normalize_czech_spoken_forms(source) == expected

    @pytest.mark.parametrize(
        "source",
        [
            "V XIX. století",
            "Na přelomu XIX.–XX. století",
            "21. cervna",
            "90 km/h a tzv. mloci atd.",
        ],
    )
    def test_positive_forms_are_idempotent(self, source: str):
        once = normalize_czech_spoken_forms(source)
        assert normalize_czech_spoken_forms(once) == once


class TestAgreementHeuristics:
    def test_tzv_agrees_with_next_word(self):
        assert normalize_czech_spoken_forms("tzv. studená válka") == "takzvaná studená válka"
        assert normalize_czech_spoken_forms("tzv. mloci") == "takzvaní mloci"
        assert normalize_czech_spoken_forms("tzv. skleníkový efekt") == "takzvaný skleníkový efekt"

    def test_sv_nominative_and_genitive(self):
        assert normalize_czech_spoken_forms("Libuše, Vyšehrad, sv. Václav") == (
            "Libuše, Vyšehrad, svatý Václav"
        )
        assert normalize_czech_spoken_forms("chrám sv. Víta") == "chrám svatého Víta"
        assert normalize_czech_spoken_forms("odkaz sv. Ludmily") == "odkaz svaté Ludmily"


class TestTextual:
    def test_naprsklad_mid_sentence_drops_dot(self):
        assert normalize_czech_spoken_forms("např. NaCl je sůl") == "například NaCl je sůl"

    def test_atd_keeps_sentence_final_dot(self):
        assert normalize_czech_spoken_forms("jablka, hrušky atd. Další věta.") == (
            "jablka, hrušky a tak dále. Další věta."
        )
        assert normalize_czech_spoken_forms("jablka atd. a jiné") == "jablka a tak dále a jiné"

    def test_min_before_number_is_minimalne(self):
        assert normalize_czech_spoken_forms("nech ho mluvit min. 30 sekund") == (
            "nech ho mluvit minimálně 30 sekund"
        )

    def test_legal_citation(self):
        assert normalize_czech_spoken_forms("ústavní zákon č. 1/1993 Sb., účinnost") == (
            "ústavní zákon číslo 1/1993 Sbírky, účinnost"
        )

    def test_common_connectors(self):
        assert normalize_czech_spoken_forms("tj. počet potomků, resp. uzlů") == (
            "to jest počet potomků, respektive uzlů"
        )
        assert normalize_czech_spoken_forms("od cca 1850") == "od cirka 1850"
        assert normalize_czech_spoken_forms("zlato vs. dítě") == "zlato versus dítě"

    def test_capital_preserved(self):
        assert normalize_czech_spoken_forms("Např. voda.") == "Například voda."


class TestCurrenciesAndSymbols:
    def test_currency_suffix_forms(self):
        assert normalize_czech_spoken_forms("stálo to 50 €") == "stálo to 50 eur"
        assert normalize_czech_spoken_forms("1 € je moc") == "jedno euro je moc"
        assert normalize_czech_spoken_forms("dluh 3 USD") == "dluh 3 dolary"

    def test_currency_prefix_swaps_order(self):
        assert normalize_czech_spoken_forms("stálo to $100") == "stálo to 100 dolarů"
        assert normalize_czech_spoken_forms("cena €2") == "cena dvě eura"
        assert normalize_czech_spoken_forms("za £5 týdně") == "za 5 liber týdně"

    def test_paragraf(self):
        assert normalize_czech_spoken_forms("dle § 89 zákona") == "dle paragraf 89 zákona"
        assert normalize_czech_spoken_forms("tento §") == "tento paragraf"

    def test_copyright_read_trademark_silent(self):
        # NVDA policy line: © carries meaning (read), ®/™ are legal furniture
        # humans skip in flowing speech (drop silently).
        assert normalize_czech_spoken_forms("© 2026 Mendelio") == "copyright 2026 Mendelio"
        assert normalize_czech_spoken_forms("značka™ funguje") == "značka funguje"
        assert normalize_czech_spoken_forms("Vitamin C® denně") == "Vitamin C denně"

    def test_division_minus_approx(self):
        assert normalize_czech_spoken_forms("12 ÷ 3") == "12 děleno 3"
        assert normalize_czech_spoken_forms("teplota −5 stupňů") == "teplota mínus 5 stupňů"
        assert normalize_czech_spoken_forms("~50 lidí") == "asi 50 lidí"

    def test_angular_coordinates(self):
        assert normalize_czech_spoken_forms("49° 12′ 30″") == "49 stupňů 12 minut 30 vteřin"

    def test_multiplication(self):
        assert normalize_czech_spoken_forms("plocha 3 x 4 metry") == "plocha 3 krát 4 metry"
        assert normalize_czech_spoken_forms("zrychlil 10x") == "zrychlil 10 krát"
        assert normalize_czech_spoken_forms("axiom x je") == "axiom x je"

    def test_ampersand_only_between_spaces(self):
        assert normalize_czech_spoken_forms("Dvořák & syn") == "Dvořák a syn"
        assert normalize_czech_spoken_forms("AT&T funguje") == "AT&T funguje"

    def test_fractions(self):
        assert normalize_czech_spoken_forms("přidej ½ lžičky") == "přidej jedna polovina lžičky"


class TestPrepositionDeclension:
    """ÚJČ-backed: unambiguous prepositions govern one case; 5–99 share one
    oblique form; ambiguous prepositions decide by the noun's plural ending."""

    def test_genitive_prepositions(self):
        assert normalize_czech_spoken_forms("od 3 km daleko") == "od tří kilometrů daleko"
        assert normalize_czech_spoken_forms("do 30 minut") == "do třiceti minut"
        assert normalize_czech_spoken_forms("Bez 3 lidí to nejde") == "Bez tří lidí to nejde"
        assert normalize_czech_spoken_forms("kolem 25 km") == "kolem dvaceti pěti kilometrů"

    def test_dative_and_instrumental(self):
        assert normalize_czech_spoken_forms("k 9 hodinám") == "k devíti hodinám"
        assert normalize_czech_spoken_forms("s 8 lidmi") == "s osmi lidmi"
        assert normalize_czech_spoken_forms("před 5 lety") == "před pěti lety"
        assert normalize_czech_spoken_forms("mezi 5 kandidáty") == "mezi pěti kandidáty"

    def test_ambiguous_preposition_decided_by_noun_ending(self):
        assert normalize_czech_spoken_forms("po 5 minutách") == "po pěti minutách"
        assert normalize_czech_spoken_forms("v 7 případech") == "v sedmi případech"
        # Accusative readings: no oblique ending on the noun → numeral untouched.
        assert normalize_czech_spoken_forms("o 5 minut déle") == "o 5 minut déle"
        assert normalize_czech_spoken_forms("v 5 hodin") == "v 5 hodin"

    def test_oblique_unit_paradigms(self):
        # dat/loc/ins plural unit forms are derived: hard masc, soft masc
        # (stupních!), feminine -a, multi-word with frozen tails and agreeing
        # adjectives.
        assert normalize_czech_spoken_forms("s 5 kg nákladu") == "s pěti kilogramy nákladu"
        assert normalize_czech_spoken_forms("při 30 °C") == "při třiceti stupních Celsia"
        assert normalize_czech_spoken_forms("k 5 km") == "k pěti kilometrům"
        assert normalize_czech_spoken_forms("s 10 m² plochy") == "s deseti metry čtverečními plochy"
        assert normalize_czech_spoken_forms("před 90 min. Pak šel.") == "před devadesáti minutami. Pak šel."

    def test_value_one_and_two_outside_genitive(self):
        assert normalize_czech_spoken_forms("s 1 kg mouky") == "s jedním kilogramem mouky"
        assert normalize_czech_spoken_forms("s 1 Kč") == "s jednou korunou"
        assert normalize_czech_spoken_forms("se 2 kg") == "se dvěma kilogramy"

    def test_coordination_shares_case(self):
        assert normalize_czech_spoken_forms("mezi 5 a 10 km") == "mezi pěti a deseti kilometry"
        assert normalize_czech_spoken_forms("od 3 do 5 km") == "od tří do pěti kilometrů"
        assert normalize_czech_spoken_forms("mezi 5–10 %")  # dash reads "až" — just must not crash
        assert normalize_czech_spoken_forms("po 5 až 10 minutách") == "po pěti až deseti minutách"

    def test_scope_guards(self):
        # Years and 3+ digit numbers never decline ("od 1620" stays literal).
        assert normalize_czech_spoken_forms("od 1620 do 1648") == "od 1620 do 1648"
        # Ordinals belong to the century/date passes and are consumed before
        # this generic preposition-driven numeral rule can see them.
        assert normalize_czech_spoken_forms("od 5. století") == "od pátého století"
        # Value 1 with a unit takes the derived genitive singular.
        assert normalize_czech_spoken_forms("do 1 km") == "do jednoho kilometru"
        assert normalize_czech_spoken_forms("od 1 Kč") == "od jedné koruny"
        assert normalize_czech_spoken_forms("od 12 °C") == "od dvanácti stupňů Celsia"
        # Decimals skip the declension pass; the plain unit pass speaks them.
        assert normalize_czech_spoken_forms("od 5,5 km") == "od pět celých pět kilometru"


class TestDecimalsAndDecades:
    """Real failure modes caught by the maturita-content eval (2026-07-21):
    "0,4" split into "nula.čtyři"; "70. let" read as a cardinal."""

    def test_decimal_comma(self):
        assert normalize_czech_spoken_forms("rozdíl 0,4 až 1,7") == (
            "rozdíl nula celá čtyři až jedna celá sedm"
        )
        assert normalize_czech_spoken_forms("π je 3,14") == "π je tři celé čtrnáct"

    def test_dotted_label_reads_tecka(self):
        # "10.1" is a chapter/version label, not a fraction — "deset tečka jedna".
        assert normalize_czech_spoken_forms("kapitola 10.1 Úvod") == (
            "kapitola deset tečka jedna Úvod"
        )
        assert normalize_czech_spoken_forms("verze 2.5") == "verze dva tečka pět"
        assert normalize_czech_spoken_forms("Kapitola 10.1: úvod") == "Kapitola deset tečka jedna: úvod"

    def test_decimal_leading_zero_in_fraction(self):
        assert normalize_czech_spoken_forms("0,05 gramu") == "nula celá nula pět gramu"

    def test_decades_agree_with_noun(self):
        assert normalize_czech_spoken_forms("v 70. letech") == "v sedmdesátých letech"
        assert normalize_czech_spoken_forms("90. léta byla divoká") == "devadesátá léta byla divoká"
        assert normalize_czech_spoken_forms("konec 60. let") == "konec šedesátých let"

    def test_plain_ordinal_not_a_decade(self):
        # No "let"/"léta" after it → ordinary ordinal, left for the number pass.
        assert normalize_czech_spoken_forms("70. výročí") == "70. výročí"

    def test_clock_time_is_not_a_decimal(self):
        # Colons guard clock times; only "." / "," between digits convert.
        assert normalize_czech_spoken_forms("sešli se v 14:30") == "sešli se v 14:30"


class TestSafety:
    def test_untouched_text_is_identical(self):
        text = "Ahoj, jak se máš? Povídej mi o fotosyntéze."
        assert normalize_czech_spoken_forms(text) == text

    def test_roman_numeral_ruler_untouched(self):
        assert normalize_czech_spoken_forms("Karel V. vládl") == "Karel V. vládl"

    def test_idempotent(self):
        once = normalize_czech_spoken_forms("90 km/h a tzv. mloci atd.")
        assert normalize_czech_spoken_forms(once) == once

    def test_empty(self):
        assert normalize_czech_spoken_forms("") == ""
