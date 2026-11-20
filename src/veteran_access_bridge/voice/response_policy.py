"""Bounded delivery guard for capabilities absent from the browser voice flow.

This changes spoken wording, never tool authority or tool results. Preserve the
original IBM event and record any replacement as an application-owned event.
"""

import re

STAFF_CONTACT = "Please contact your VA facility's scheduling team for help."
_TRANSFER = re.compile(
    r"\b(?:connect(?:ed|ing)?|transfer(?:red|ring)?|patch(?:ed|ing)?|put(?:ting)?)\b",
    re.I,
)
_OFFER = re.compile(r"\b(?:i|i'll|i've|let me|would you like me|shall i|can i)\b", re.I)
_DENIAL = re.compile(
    r"\b(?:cannot|can't|can not|unable to|not able to)"
    r"\s+(?:connect|transfer|patch|put)\b",
    re.I,
)


def constrain_staff_transfer(text: str) -> tuple[str, bool]:
    """Replace unsupported first-person transfer offers; keep honest refusals."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    changed = False
    result = []
    for part in parts:
        normalized = part.replace("’", "'")
        if (
            _TRANSFER.search(normalized)
            and _OFFER.search(normalized)
            and not (
                len(_TRANSFER.findall(normalized)) == 1 and _DENIAL.search(normalized)
            )
        ):
            changed = True
            if STAFF_CONTACT not in result:
                result.append(STAFF_CONTACT)
        else:
            result.append(part)
    return ("\n".join(result), True) if changed else (text, False)
