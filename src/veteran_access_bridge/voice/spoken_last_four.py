"""Strict caller-supplied digit extraction; never infer from patient records."""

import re

from .identity_intake import DATE_START
from .spoken_identity import spoken_birth_date

VERIFICATION_PROMPT = (
    "For verification purposes, please provide your full name, date of birth, "
    "and last 4 of your social."
)
WORDS = dict(
    zip("zero one two three four five six seven eight nine".split(), "0123456789")
)
WORDS["oh"] = "0"
LABEL = re.compile(
    r"\b(?:(?:the |my )?last (?:four|4)(?: digits)?"
    r"(?: of (?:my |the |your )?(?:social(?: security)?(?: number)?|ssn))?"
    r"|(?:my )?(?:social(?: security)?(?: number)?|ssn))"
    r"\s*(?:is|are|:)?\s*",
    re.I,
)


def four_digits(text: str) -> str | None:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if not tokens or any(t not in WORDS and not t.isascii() for t in tokens):
        return None
    digits = "".join(WORDS.get(t, t) for t in tokens)
    return digits if re.fullmatch(r"[0-9]{4}", digits) else None


def split_last_four(text: str) -> tuple[str, str | None, bool]:
    """Strip an explicit factor clause, standalone digits, or unambiguous suffix.

    Return remaining name/DOB, the four digits, and whether a factor was attempted.
    An incomplete or conflicting explicit clause never falls into name parsing.
    """
    labels = list(LABEL.finditer(text))
    if labels:
        first = labels[0]
        clean = re.sub(r"\b(?:and|my)\s*$", "", text[: first.start()].strip(" ,.;"))
        value = four_digits(text[first.end() :]) if len(labels) == 1 else None
        return clean.strip(" ,.;"), value, True
    value = four_digits(text)
    if value is not None:
        return "", value, True
    # Do not confuse a spoken birth year with the extra verification factor.
    tokens = list(
        re.finditer(
            r"\b(?:[0-9]+|zero|oh|one|two|three|four|five|six|seven|eight|nine)\b",
            text,
            re.I,
        )
    )
    for token in tokens:
        suffix = text[token.start() :]
        value = four_digits(suffix)
        prefix = text[: token.start()].strip(" ,.;")
        prefix = re.sub(r"\band\s*$", "", prefix).strip(" ,.;")
        birth = DATE_START.search(prefix)
        if value and birth and spoken_birth_date(prefix[birth.start() :]):
            return prefix, value, True
    return text, None, False


def redact_spoken_identity(text: str, *, identity_phase: bool) -> str:
    # Suppress partial STT hypotheses too: waiting for four final digits leaks
    # the preceding one-, two-, and three-digit interim captions.
    if identity_phase:
        return "[Verification details withheld]"
    if LABEL.search(text):
        return "[Social Security details withheld]"
    return text
