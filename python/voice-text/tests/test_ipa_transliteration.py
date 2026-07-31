"""The pure transliteration core: IPA -> the spelling handed to the model.

No GPU, no map, no server — every case here is a function call, so these are the
cheapest place to pin the phonology down.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from ipa_transliteration import (  # noqa: E402
    UnknownSymbol,
    Verdict,
    decide_respelling,
    ipa_to_czech,
    model_g2p,
    reads_as,
)


def respell(written: str, *ipas: str) -> str | None:
    return decide_respelling(written, list(ipas))[1]


def verdict(written: str, *ipas: str) -> str:
    return decide_respelling(written, list(ipas))[0]


# --- The table (plan 4a) ----------------------------------------------------


@pytest.mark.parametrize(
    "written, ipa, expected",
    [
        # The foreign spelling this whole layer exists for (plan 1).
        ("meeting", "[miːtɪŋk]", "mítyng"),
        ("screeningový", "[skriːnɪŋgɔviː]", "skrínyngový"),
        ("snowboardista", "[snɔʊ̯bɔrdɪsta]", "snoubordysta"),
        ("streamování", "[striːmɔvaːɲiː]", "strímováňí"),
        ("notebook", "[ˈnɔʊ̯t.buk]", "noutbuk"),
        ("judo", "[d͡ʒʊdɔ]", "džudo"),
        ("software", "[sɔftvɛːr]", "softvér"),
        ("xylofon", "[ksɪlɔfɔn]", "ksylofon"),
        # Native di/ti/ni, i.e. what the legacy map already repairs.
        ("kupodivu", "[ˈkʊ.pɔ.ɟɪ.vʊ]", "kupoďivu"),
        ("nivu", "[ɲɪvʊ]", "ňivu"),
        ("hodina", "[ɦɔɟɪna]", "hoďina"),
        ("čeština", "[t͡ʃɛʃcɪna]", "češťina"),
        ("efektivní", "[ɛfɛktɪvɲiː]", "efektyvňí"),
        ("audit", "[aʊ̯dɪt]", "audyt"),
        # Voicing the spelling genuinely controls: [z] between vowels.
        ("anisotropní", "[anɪzɔtrɔpɲiː]", "anyzotropňí"),
    ],
)
def test_transliterates_documented_pronunciation(written, ipa, expected) -> None:
    assert respell(written, ipa) == expected


def test_anti_devoicing_keeps_the_written_voiced_ending() -> None:
    # IPA records final devoicing ([miːtɪŋk]); spelling it "mítynk" would break
    # the oblique cases, which voice it again (mítyngu [gʊ]).
    assert respell("meeting", "[miːtɪŋk]") == "mítyng"
    assert ipa_to_czech("[miːtɪŋk]") == "mítynk"


def test_map_values_are_lowercase_because_the_runtime_reapplies_case() -> None:
    # Capitalization is _match_case's job at call time, so the map stays
    # lowercase and one entry serves "Medína" and "medína" alike.
    assert respell("Medína", "[mɛɟiːna]") == "meďína"


def test_unknown_symbol_drops_the_word_rather_than_guessing() -> None:
    with pytest.raises(UnknownSymbol):
        ipa_to_czech("[wɪkɪpɛdɪjɛ]")  # w is not a Czech phoneme
    assert respell("wikipedie", "[wɪkɪpɛdɪjɛ]") is None


# --- The gate (plan 4b) -----------------------------------------------------


@pytest.mark.parametrize(
    "written, ipa",
    [
        ("víkend", "[viːkɛnt]"),  # final devoicing only
        ("chaos", "[xaɔs]"),  # transliterates to itself
        ("francouzský", "[frant͡sɔʊ̯skiː]"),  # assimilation the reader applies
        ("město", "[mɲɛstɔ]"),  # ě
        ("dům", "[duːm]"),  # ů
        ("být", "[biːt]"),  # y/i is not a sound distinction
        ("vpravo", "[fpravɔ]"),  # v -> [f] before a voiceless obstruent
    ],
)
def test_words_the_model_already_reads_right_stay_out_of_the_map(written, ipa) -> None:
    assert verdict(written, ipa) == Verdict.READS_CORRECTLY


def test_only_consonants_degeminate() -> None:
    # Czech degeminates consonants ("francouzský" is [frant͡sɔʊ̯skiː], not
    # [...sskiː]) but NOT vowels: collapsing those turns the prefixed "neetický"
    # into "netický", a different word.
    assert model_g2p("francouzský") == "frant͡sɔʊ̯skiː"
    assert model_g2p("neetycký") == "nɛɛtɪt͡skiː"


def test_ipa_never_invents_a_spelling_reform() -> None:
    # The IPA fixes the sound, never the spelling. Czech writes [iː] as í or ý
    # and [uː] as ú or ů with no phonetic difference, so a spelling rebuilt from
    # IPA alone "corrects" být to bít and my to mi — different words.
    for written, ipa in [
        ("být", "[biːt]"),
        ("my", "[mɪ]"),
        ("vy", "[ˈvɪ]"),
        ("starý", "[ˈstariː]"),
        ("dům", "[duːm]"),
        ("růže", "[ruːʒɛ]"),
        ("člověk", "[t͡ʃlɔvjɛk]"),
    ]:
        assert respell(written, ipa) is None, written


def test_a_respelling_must_earn_every_letter_it_changes() -> None:
    # "vsadit" reads [fsaɟɪt] whether it starts v or f, so only the di the model
    # cannot resolve is allowed to move.
    assert respell("vsadit", "[fsaɟɪt]") == "vsaďit"
    # Same for ě: only the ti becomes ť.
    assert respell("květina", "[kvjɛcɪna]") == "kvěťina"
    assert respell("zemětřesení", "[zɛmɲɛtr̝̊ɛsɛɲiː]") == "zemětřeseňí"


def test_length_alone_never_justifies_an_entry() -> None:
    # gilotina's variants differ only in length; the first documented one wins
    # (plan 4d) and matches the legacy map's "gilotyna".
    assert respell("gilotina", "[gɪlɔtɪna]", "[gɪlɔtiːna]") == "gilotyna"
    # A word whose ONLY difference is unwritten latinate length stays out.
    assert verdict("kultura", "[kʊltuːra]") == Verdict.READS_CORRECTLY


# --- Sanity filters (plan 4c) -----------------------------------------------


def test_another_words_ipa_is_rejected() -> None:
    # The entry "šestnáctipodlažní" really does carry dvoupodlažní's IPA. Which
    # filter catches it is not the contract — several apply (it strays far from
    # the written form AND loses the š) and they may reorder. Staying out of the
    # map, in front of a human, is.
    assert verdict("šestnáctipodlažní", "[dvɔʊ̯pɔdlaʒɲiː]").startswith("review_")
    # "Moravcovi" carries the IPA of "panu" — far too short to be this word.
    assert verdict("Moravcovi", "[panʊ]") == Verdict.DROP_ROUND_TRIP


def test_empty_or_truncated_ipa_never_yields_an_empty_respelling() -> None:
    for written, ipa in [("břidlicový", "[]"), ("heroický", "[ˈ]"), ("akutnost", "[ˈʔa")]:
        assert respell(written, ipa) is None, written


def test_colloquial_variant_does_not_override_a_readable_written_form() -> None:
    # "člověk" documents [t͡ʃlɔvjɛk] alongside colloquial [t͡ʃlɔʊ̯jɛk]. Reading
    # the written form delivers the first, so the word needs no help.
    assert verdict("člověk", "[t͡ʃlɔvjɛk]", "[t͡ʃɫɔvjɛk]", "[t͡ʃlɔʊ̯jɛk]") == Verdict.READS_CORRECTLY


def test_structurally_conflicting_variants_go_to_review(written=None) -> None:
    assert verdict("puzzle", "[pazl]", "[pʊt͡slɛ]") == Verdict.REVIEW_CONFLICTING
    assert verdict("workshop", "[ˈvɔrk.ʃɔp]", "[ˈvɛrk.ʃɔp]") == Verdict.REVIEW_CONFLICTING


# --- The model this is all aimed at -----------------------------------------


def test_written_di_ti_ni_is_treated_as_undecidable_not_as_hard() -> None:
    # The model is unreliable in BOTH directions: it hardens soft "nivu" and
    # palatalizes hard "tipnout". So a written di/ti/ni predicts nothing, and
    # every site must be spelled out — which is why "audit" earns "audyt" even
    # though the hard reading it needs is the one the model usually guesses.
    assert not reads_as("audit", "[aʊ̯dɪt]")
    assert reads_as("audyt", "[aʊ̯dɪt]")
    assert reads_as("ňivu", "[ɲɪvʊ]")


def test_model_g2p_reports_unreadable_rather_than_inventing_a_reading() -> None:
    assert model_g2p("software") is None  # w
    assert model_g2p("mítynk") == "miːtɪŋk"


# --- Regressions found by adversarial review (2026-07-17) --------------------


@pytest.mark.parametrize(
    "written, ipa",
    [
        ("obřad", "[ˈɔpr̝̊at]"),
        ("obřezal", "[ˈɔpr̝̊ɛzal]"),
        ("samozřejmou", "[ˈsamɔsr̝̊ɛjmɔʊ̯]"),
        ("březový", "[ˈpr̝̊ɛzɔviː]"),
        ("keř", "[kɛr̝̊]"),
        ("potřebovat", "[ˈpɔ.tr̝̊ɛ.bɔ.vat]"),
        ("hospodářství", "[ɦɔspɔdaːr̝̊stviː]"),
    ],
)
def test_r_hacek_is_an_obstruent_and_neutralizes_what_precedes_it(written, ipa) -> None:
    # ř devoices the consonant before it, and Czech spells voiced and voiceless ř
    # alike. Treating ř as a sonorant made [ˈɔpr̝̊at] unreachable for any spelling
    # with a b, so the layer "repaired" the letter instead: obřad -> "opřad",
    # samozřejmou -> "samosřejmou". 193 such entries shipped.
    assert verdict(written, ipa) == Verdict.READS_CORRECTLY


def test_a_respelling_may_never_lose_a_hacek_sibilant() -> None:
    # Writing ř takes two combining marks, so the dump often types a plain [r]
    # instead. Every other filter waves it through (similarity ~0.9, length
    # unchanged) and the phoneme just vanishes.
    for written, ipa in [
        ("přijmout", "[ˈprɪjmɔʊ̯t]"),
        ("kořist", "[ˈkɔrɪst]"),
        ("pohoří", "[pɔɦɔriː]"),
    ]:
        assert verdict(written, ipa) == Verdict.REVIEW_LOST_HACEK, written


def test_bare_ts_is_two_phonemes_not_an_affricate() -> None:
    # The tie bar is what marks an affricate. Czech genuinely has [t]+[s] across
    # a morpheme seam, and collapsing it shipped "octraňil" for "odstranil".
    assert respell("odstranil", "[ˈɔtstraɲɪl]") == "odstraňil"
    assert verdict("odstoupí", "[ˈɔtstɔʊ̯piː]") == Verdict.READS_CORRECTLY
    assert verdict("představitel", "[ˈpr̝ɛtstavɪtɛl]") == Verdict.READS_CORRECTLY
    # ...while the tie-barred affricate still maps to a single letter.
    assert respell("čeština", "[t͡ʃɛʃcɪna]") == "češťina"


def test_a_transposed_ipa_is_a_typo_not_a_pronunciation() -> None:
    # The dump types "odstoupí" as [ɔt͡stɔpʊiː] — the reading [ɔtstɔʊ̯piː] with
    # two phonemes swapped — which respelled it to "octopuí". Czech never
    # metathesizes against its own spelling, so a permutation is the typist's.
    assert verdict("odstoupí", "[ɔt͡stɔpʊiː]") == Verdict.DROP_TRANSPOSED_IPA
    assert respell("odstoupí", "[ɔt͡stɔpʊiː]") is None


def test_a_loanword_is_not_a_transposition() -> None:
    # judo's [d͡ʒʊdɔ] CHANGES a phoneme against the reading [jʊdɔ] rather than
    # reordering it, which is exactly what a real foreign pronunciation looks
    # like. The transposition guard must not touch this class.
    assert respell("judo", "[d͡ʒʊdɔ]") == "džudo"
    assert respell("notebook", "[ˈnɔʊ̯t.buk]") == "noutbuk"
    assert respell("software", "[sɔftvɛːr]") == "softvér"
    assert respell("xylofon", "[ksɪlɔfɔn]") == "ksylofon"


def test_a_hacek_sibilant_cannot_read_as_its_plain_counterpart() -> None:
    # Czech reads š/ž/č/ř with no exception but voicing — there is no reading of
    # "š" as [s]. The dump types "příští" as [pr̝̊iːsciː] and "rozčeše" as
    # [ˈrɔst͡sɛʃɛ]; both respell the háček away, and similarity (~0.9) and length
    # both wave them through.
    assert verdict("příští", "[pr̝̊iːsciː]") == Verdict.REVIEW_LOST_HACEK
    assert verdict("rozčeše", "[ˈrɔst͡sɛʃɛ]") == Verdict.REVIEW_LOST_HACEK


def test_gaining_a_hacek_is_the_whole_point() -> None:
    # Only a DROP is suspicious: a loanword gains one, and so does every di/ti/ni
    # repair the corpus exists to make.
    assert respell("judo", "[d͡ʒʊdɔ]") == "džudo"
    assert respell("čeština", "[t͡ʃɛʃcɪna]") == "češťina"
    assert respell("nivu", "[ɲɪvʊ]") == "ňivu"


def test_a_neighbouring_words_ipa_that_swaps_one_phoneme_is_rejected() -> None:
    # The dump carries the wrong word's pronunciation, changing exactly one letter
    # for an unrelated phoneme. Every other guard waves these through — similarity
    # is ~0.9, the length is unchanged, and no háček is lost. See
    # _SPURIOUS_SUBSTITUTIONS.
    assert verdict("pradlena", "[ˈpr̝adlɛna]") == Verdict.REVIEW_SPURIOUS_PHONEME
    assert verdict("dopamin", "[ˈdɔmamɪn]") == Verdict.REVIEW_SPURIOUS_PHONEME
    assert verdict("mocná", "[ˈmɔcnaː]") == Verdict.REVIEW_SPURIOUS_PHONEME


def test_a_single_letter_swap_that_preserves_the_sound_still_passes() -> None:
    # i/y and the di/ti/ni softenings are single-letter substitutions too, but
    # they are sound-equal and must never be mistaken for a spurious swap.
    assert respell("adjektiva", "[adjɛktɪva]") == "adjektyva"
    assert respell("nivu", "[ɲɪvʊ]") == "ňivu"


def test_a_softening_with_nothing_to_license_it_is_rejected() -> None:
    # The dump's IPA carries a neighbour's [ɲ]/[c], planting ď/ť/ň before a hard
    # vowel or at the word end where Czech has a plain d/t/n.
    assert verdict("moučná", "[ˈmɔʊ̯t͡ʃɲaː]") == Verdict.REVIEW_SPURIOUS_SOFTENING
    assert verdict("svícen", "[ˈsviːt͡sɛɲ]") == Verdict.REVIEW_SPURIOUS_SOFTENING
    assert verdict("kominář", "[ˈkɔmɪɲaːr̝]") == Verdict.REVIEW_SPURIOUS_SOFTENING


def test_a_softening_the_context_licenses_still_passes() -> None:
    # Before a soft vowel it is the di/ti/ni device; before a soft consonant it is
    # regressive palatal assimilation (n takes ň before ď/ť). Both are correct.
    assert respell("nivu", "[ɲɪvʊ]") == "ňivu"
    assert respell("rwanďan", "[ˈrvaɲɟan]") == "rvaňďan"
