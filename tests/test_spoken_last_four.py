import pytest

from veteran_access_bridge.voice.spoken_last_four import (
    four_digits,
    redact_spoken_identity,
    split_last_four,
)


@pytest.mark.parametrize("text", ["0067", "zero zero six seven", "oh oh six seven"])
def test_explicit_four_preserves_leading_zeroes(text):
    assert four_digits(text) == "0067"


@pytest.mark.parametrize(
    "text", ["067", "00067", "sixty seven", "００６７", "0067 yes"]
)
def test_ambiguous_or_incomplete_digits_are_not_guessed(text):
    assert four_digits(text) is None


@pytest.mark.parametrize(
    "suffix",
    [
        ", last four of my social are zero zero six seven",
        ", zero zero six seven",
        ", 0067",
        " and zero zero six seven",
    ],
)
def test_combined_fields(suffix):
    name_birth = "Judy Morrison, May fifth nineteen forty five"
    assert split_last_four(name_birth + suffix) == (name_birth, "0067", True)


def test_birth_year_is_not_a_factor():
    text = "Judy Morrison, May 5, 1945"
    assert split_last_four(text) == (text, None, False)


def test_bad_correction_does_not_preserve_old_factor():
    assert split_last_four("my last four are zero zero") == ("", None, True)
    assert split_last_four("last four 0067, last four 0068")[1] is None


@pytest.mark.parametrize("text", ["zero", "zero zero", "0067", "My name is Judy"])
def test_interim_and_final_identity_captions_are_withheld(text):
    assert redact_spoken_identity(text, identity_phase=True) == (
        "[Verification details withheld]"
    )


def test_non_identity_caption_and_unsolicited_social():
    assert redact_spoken_identity("Tuesday morning", identity_phase=False) == (
        "Tuesday morning"
    )
    assert "0067" not in redact_spoken_identity(
        "My social is 0067", identity_phase=False
    )
