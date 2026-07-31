"""czech_numbers: the one home of digit→words, incl. oblique cases (ÚJČ ?id=792/671/791).

Nominative outputs are LOCKED to the historical live-path behaviour
(glued "dvacetjedna", "čtrnáct set" years) — changing them changes prod audio.
Oblique forms follow the ÚJČ paradigm tables; the named traps (sedmi, osmi,
devíti, tří/čtyř spisovné, dvou set) are exactly the forms generators get wrong.
"""

from __future__ import annotations

import pytest

from mendelio_voice_text.czech_numbers import cardinal, percent_words


class TestNominativeLockedBehaviour:
    @pytest.mark.parametrize("n,expected", [
        (0, "nula"),
        (5, "pět"),
        (21, "dvacetjedna"),          # glued — spoken-prosody invariant
        (99, "devadesátdevět"),
        (100, "sto"),
        (256, "dvě stě padesátšest"),
        (1000, "tisíc"),
        (1620, "šestnáct set dvacet"),     # year style
        (1921, "devatenáct set dvacetjedna"),
        (2026, "dva tisíce dvacetšest"),
        (9999, "devět tisíc devět set devadesátdevět"),
    ])
    def test_nominative(self, n, expected):
        assert cardinal(n) == expected


class TestObliqueForms:
    @pytest.mark.parametrize("n,case,expected", [
        (2, "gen", "dvou"), (2, "dat", "dvěma"), (2, "ins", "dvěma"),
        (3, "gen", "tří"), (3, "dat", "třem"), (3, "loc", "třech"), (3, "ins", "třemi"),
        (4, "gen", "čtyř"), (4, "ins", "čtyřmi"),
        (5, "gen", "pěti"), (5, "loc", "pěti"),
        (7, "gen", "sedmi"),          # not "sedmy"
        (8, "dat", "osmi"),
        (9, "gen", "devíti"),         # stem change — not "devěti"
        (10, "loc", "deseti"),
        (19, "ins", "devatenácti"),
        (20, "gen", "dvaceti"),
        (25, "ins", "dvaceti pěti"),  # both parts decline, spoken with a space
        (99, "gen", "devadesáti devíti"),
        (100, "gen", "sta"),
        (200, "gen", "dvou set"),
        (300, "dat", "třem stům"),
        (500, "loc", "pěti stech"),
        (200, "ins", "dvěma sty"),
        (1000, "gen", "tisíce"),
        (5000, "ins", "pěti tisíci"),
    ])
    def test_oblique(self, n, case, expected):
        assert cardinal(n, case) == expected

    def test_unknown_case_raises(self):
        with pytest.raises(ValueError):
            cardinal(5, "vocative")


class TestPercent:
    @pytest.mark.parametrize("n,expected", [
        (1, "jedno procento"),
        (2, "dvě procenta"),
        (3, "tři procenta"),
        (5, "pět procent"),
        (50, "padesát procent"),
    ])
    def test_forms(self, n, expected):
        assert percent_words(n) == expected
