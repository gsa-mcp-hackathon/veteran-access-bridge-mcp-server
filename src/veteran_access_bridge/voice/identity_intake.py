"""Collect caller-supplied identity; readback is never identity authorization."""

import re
from dataclasses import dataclass, field
from datetime import date

from .spoken_identity import spoken_birth_date, spoken_name

YES = frozenset(
    {
        "yes",
        "yes please",
        "yes that is correct",
        "yes that's correct",
        "that's correct",
        "that is correct",
        "correct",
        "right",
        "yes that's right",
        "that's right",
        "yes that is right",
        "yep",
        "yeah",
    }
)
DATE_START = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b"
    r"(?=\s+(?:\d|first\b|second\b|third\b|fourth\b|fifth\b|sixth\b|seventh\b|eighth\b|ninth\b|tenth\b|eleventh\b|twelfth\b|thirteenth\b|fourteenth\b|fifteenth\b|sixteenth\b|seventeenth\b|eighteenth\b|nineteenth\b|twentieth\b|twenty\b|thirtieth\b|thirty\b|one\b|two\b|three\b|four\b|five\b|six\b|seven\b|eight\b|nine\b|ten\b))"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b",
    re.I,
)


@dataclass
class IdentityIntake:
    name: str = field(default="", repr=False)
    birth_date: str = field(default="", repr=False)
    pending_birth: str = field(default="", repr=False)
    last_four: str = field(default="", repr=False)
    awaiting_confirmation: bool = False
    turns: int = 0
    attempts: int = 0
    halted: bool = False

    def clear(self):
        self.name = self.birth_date = ""
        self.pending_birth = ""
        self.last_four = ""
        self.awaiting_confirmation = False

    def stop(self):
        self.clear()
        self.halted = True
        return (
            "I'm unable to complete verification. Please contact your facility's "
            "scheduling team for help."
        )

    def mismatch(self):
        self.attempts += 1
        self.clear()
        if self.attempts >= 2:
            return self.stop()
        return (
            "Those details didn't match. Let's check what I heard. "
            "Please say or spell your full name, saying space between names."
        )

    def receive(self, text: str) -> tuple[str, bool]:
        """Return speech and whether complete, read-back answers were confirmed."""
        self.turns += 1
        if self.halted or self.turns > 10:
            return self.stop(), False
        clean = text.strip().replace("’", "'").strip(" .!?")
        confirmation = " ".join(re.sub(r"[,!?;:.]", " ", clean.lower()).split())
        if self.awaiting_confirmation and confirmation in YES:
            self.awaiting_confirmation = False
            return "", True
        if confirmation in YES:
            return (
                "Please tell me the details you'd like me to check or correct.",
                False,
            )
        if confirmation in {"no", "no that's wrong", "that's wrong", "not correct"}:
            self.awaiting_confirmation = False
            return "What should I correct—your name or your date of birth?", False
        # Explicit corrections replace supplied fields; never infer from a record.
        clean = re.sub(
            r"^(?:(?:no|actually|sorry|correction)[,.!?:;\s]+)+",
            "",
            clean,
            flags=re.I,
        )
        match = DATE_START.search(clean)
        supplied_birth = spoken_birth_date(clean[match.start() :]) if match else None
        prefix = clean[: match.start()].strip(" ,.") if match else clean
        if not match and self.pending_birth:
            supplied_birth = spoken_birth_date(self.pending_birth + " " + clean)
            if supplied_birth:
                prefix = ""
            elif all(
                token.isdigit()
                or token
                in {
                    "zero",
                    "one",
                    "two",
                    "three",
                    "four",
                    "five",
                    "six",
                    "seven",
                    "eight",
                    "nine",
                    "ten",
                    "eleven",
                    "twelve",
                    "thirteen",
                    "fourteen",
                    "fifteen",
                    "sixteen",
                    "seventeen",
                    "eighteen",
                    "nineteen",
                    "twenty",
                    "thirty",
                    "forty",
                    "fifty",
                    "sixty",
                    "seventy",
                    "eighty",
                    "ninety",
                    "hundred",
                    "thousand",
                    "and",
                }
                for token in re.findall(r"[a-z0-9]+", clean.lower())
            ):
                self.pending_birth = (self.pending_birth + " " + clean)[:128]
                self.awaiting_confirmation = False
                return (
                    "Sorry, I didn't catch the full date of birth. Could "
                    "you include the four-digit year?",
                    False,
                )
        prefix = re.sub(
            r"(?:[, .]+)?(?:and )?(?:my (?:date of birth|birth date|birthday)"
            r"(?: is|'s)?|i was born(?: on)?|born(?: on)?)$",
            "",
            prefix,
            flags=re.I,
        ).strip(" ,.")
        if match and not supplied_birth:
            candidate = spoken_name(prefix) if prefix else None
            if candidate and re.fullmatch(r"[\w'’-]+(?:\s+[\w'’-]+){0,5}", candidate):
                self.name = candidate
            self.birth_date = ""
            self.pending_birth = clean[match.start() :]
            self.awaiting_confirmation = False
            return (
                "Sorry, I didn't catch your full date of birth. "
                "Please say the month, day, and four-digit year.",
                False,
            )
        if supplied_birth:
            self.birth_date = supplied_birth
            self.pending_birth = ""
            if prefix.lower() in {"it's", "it is", "yes", "yes but"}:
                prefix = ""
        last = re.fullmatch(r"(?:my )?last name (?:is |should be )?(.+)", prefix, re.I)
        if last and self.name:
            given = (
                self.name.split()[:-1] if len(self.name.split()) > 1 else [self.name]
            )
            prefix = " ".join(given) + " " + last.group(1)
        candidate = spoken_name(prefix) if prefix else None
        if candidate and re.fullmatch(r"[\w'’-]+(?:\s+[\w'’-]+){0,5}", candidate):
            if (
                self.name
                and len(self.name.split()) == 1
                and len(candidate.split()) == 1
            ):
                candidate = self.name + " " + candidate
            self.name = candidate
        elif prefix and not supplied_birth:
            self.awaiting_confirmation = False
            if len(self.name.split()) >= 2 and not self.birth_date:
                return (
                    "Sorry, I didn't catch your date of birth. Could you "
                    "say the month, day, and year?",
                    False,
                )
            return (
                "Sorry, I didn't catch your full name. Could you say "
                "or spell it for me?",
                False,
            )
        self.awaiting_confirmation = False
        if not self.name:
            return (
                "Sorry, I didn't catch your full name. Could you say it again?",
                False,
            )
        if len(self.name.split()) < 2:
            return (
                "Sorry, I didn't catch your last name. Could you say it again?",
                False,
            )
        if not self.birth_date:
            return (
                "What is your date of birth, including the month, day, "
                "and four-digit year?",
                False,
            )
        birthday = date.fromisoformat(self.birth_date)
        self.awaiting_confirmation = True
        return (
            f"I heard {self.name}, born {birthday.strftime('%B')} {birthday.day}, "
            f"{birthday.year}. Is that correct?"
        ), False
