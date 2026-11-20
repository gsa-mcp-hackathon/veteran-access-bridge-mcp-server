import pytest

from veteran_access_bridge.voice.response_policy import (
    STAFF_CONTACT,
    constrain_staff_transfer,
)


@pytest.mark.parametrize(
    "offer",
    [
        "Would you like me to connect you with the scheduling team?",
        "I will transfer you now.",
        "Let me put you through to a scheduler.",
        "I've connected you with staff.",
        "I can't book that, but I can transfer you to staff.",
        "I cannot transfer you, but I can connect you with staff.",
    ],
)
def test_unsupported_transfer_offer_is_not_spoken(offer):
    text, changed = constrain_staff_transfer("No booking was made. " + offer)
    assert changed
    assert text == "No booking was made.\n" + STAFF_CONTACT


@pytest.mark.parametrize(
    "text",
    [
        "I cannot transfer you. Please contact your facility's scheduling team.",
        "I’m unable to connect you to staff.",
        "Your microphone is connected. No booking was made.",
        "Please contact your VA facility's scheduling team for help.",
        "Your options are unchanged.",
    ],
)
def test_safe_wording_is_preserved(text):
    assert constrain_staff_transfer(text) == (text, False)
