import pytest

from veteran_access_bridge.voice.identity_intake import IdentityIntake


@pytest.mark.parametrize(
    "name",
    [
        "Judy Morrison",
        "I'm Judy Morrison",
        "I’m Judy Morrison",
        "My name's Judy Morrison",
    ],
)
def test_natural_name_then_birthdate_requires_readback_confirmation(name):
    flow = IdentityIntake()
    assert not flow.receive(name)[1]
    reply, ready = flow.receive("My birthday's May fifth nineteen forty-five")
    assert not ready and "Judy Morrison" in reply and "1945" in reply
    assert flow.receive("Yes, that's correct.")[1]
    assert (flow.name, flow.birth_date) == ("Judy Morrison", "1945-05-05")


@pytest.mark.parametrize(
    "correction",
    [
        "No, my last name is Morrison.",
        "No. My last name is Morrison.",
        "Actually! My last name is Morrison.",
    ],
)
def test_combined_answer_and_correction_do_not_verify_automatically(correction):
    flow = IdentityIntake()
    assert not flow.receive(
        "I'm Judy Morris, my birthday is May fifth nineteen forty-five."
    )[1]
    reply, ready = flow.receive(correction)
    assert not ready and "I heard Judy Morrison" in reply
    assert flow.awaiting_confirmation
    assert flow.name == "Judy Morrison"
    assert not flow.receive("Actually, it's May sixth nineteen forty-five.")[1]
    assert flow.birth_date == "1945-05-06"
    assert flow.receive("Yes.")[1]


def test_first_name_only_asks_for_missing_last_name():
    flow = IdentityIntake()
    assert (
        flow.receive("I'm Judy.")[0]
        == "Sorry, I didn't catch your last name. Could you say it again?"
    )
    assert "date of birth" in flow.receive("Morrison.")[0]
    assert flow.name == "Judy Morrison"


def test_ambiguous_birthdate_never_guesses_year():
    flow = IdentityIntake()
    flow.receive("Judy Morrison")
    assert not flow.receive("May fifth forty-five")[1]
    assert not flow.birth_date
    assert not flow.awaiting_confirmation


def test_wrong_identity_has_bounded_retries_and_no_expected_answers():
    flow = IdentityIntake()
    for attempt in range(2):
        flow.receive("Other Person, January first nineteen eighty")
        assert flow.receive("Yes")[1]
        reply = flow.mismatch()
        assert "Judy" not in reply
        assert not flow.name and not flow.birth_date
        assert flow.halted == (attempt == 1)
    assert not flow.receive("Yes")[1]


def test_no_and_ambiguous_confirmation_do_not_release_answers():
    flow = IdentityIntake()
    flow.receive("Judy Morrison, May fifth nineteen forty-five")
    assert not flow.receive("No")[1]
    assert not flow.receive("Yes")[1]


def test_intake_turns_are_bounded():
    flow = IdentityIntake()
    for _ in range(11):
        assert not flow.receive("???")[1]
    assert flow.halted


def test_pause_split_name_and_birthdate_require_complete_readback():
    flow = IdentityIntake()
    assert not flow.receive("Judy")[1]
    assert not flow.receive("Morrison")[1]
    assert not flow.receive("May fifth")[1]
    assert not flow.awaiting_confirmation
    reply, ready = flow.receive("nineteen forty-five")
    assert not ready and "Judy Morrison" in reply and "1945" in reply
    assert flow.receive("Yes")[1]


def test_changed_birthdate_does_not_confirm_previous_readback():
    flow = IdentityIntake()
    flow.receive("Judy Morrison, May fifth nineteen forty-five")
    assert not flow.receive("No, May sixth nineteen forty-five")[1]
    assert flow.birth_date == "1945-05-06"
    assert flow.awaiting_confirmation


def test_month_word_in_name_is_not_mistaken_for_birthdate():
    flow = IdentityIntake()
    assert "date of birth" in flow.receive("I'm May Jones")[0]
    assert flow.name == "May Jones" and not flow.birth_date


def test_year_split_over_two_final_segments_keeps_the_name():
    flow = IdentityIntake()
    flow.receive("Judy Morrison")
    flow.receive("May fifth")
    assert not flow.receive("nineteen")[1]
    assert flow.name == "Judy Morrison" and not flow.birth_date
    reply, ready = flow.receive("forty-five")
    assert not ready and "1945" in reply
    assert flow.receive("yes")[1]


def test_incomplete_date_correction_invalidates_old_date():
    flow = IdentityIntake()
    flow.receive("Judy Morrison, May fifth nineteen forty-five")
    flow.receive("No, May sixth")
    assert not flow.birth_date and not flow.awaiting_confirmation
    assert not flow.receive("Yes")[1]


@pytest.mark.parametrize(
    "confirmation",
    ["Yes. That's correct.", "Yes, that's correct.", "Yes! That's correct."],
)
def test_recognizer_sentence_punctuation_in_full_correction_exchange(confirmation):
    flow = IdentityIntake()
    flow.receive("I'm Judy Morris.")
    flow.receive("May fifth nineteen forty five.")
    reply, ready = flow.receive("No. My last name is Morrison.")
    assert not ready and "I heard Judy Morrison" in reply
    assert flow.receive(confirmation)[1]
    assert (flow.name, flow.birth_date) == ("Judy Morrison", "1945-05-05")


def test_punctuated_rejection_invalidates_confirmation():
    flow = IdentityIntake()
    flow.receive("Judy Morrison, May fifth nineteen forty-five")
    assert not flow.receive("No. That's wrong.")[1]
    assert not flow.receive("Yes. That's correct.")[1]


def test_partial_combined_answer_preserves_name_while_repairing_date():
    intake = IdentityIntake()
    prompt, ready = intake.receive("Judy Morrison, May fifth")
    assert not ready and "didn't catch" in prompt
    assert intake.name == "Judy Morrison"
    assert "Judy Morrison" in intake.receive("nineteen forty five")[0]
