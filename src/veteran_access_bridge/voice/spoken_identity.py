"Deterministic speech formatting, never identity inference or fuzzy matching."

import re
from datetime import date, datetime

_DIGITS = dict(
    zip(
        "zero one two three four five six seven eight nine".split(),
        "0123456789",
        strict=True,
    )
)
_NATO = dict(
    zip(
        (
            "alpha bravo charlie delta echo foxtrot golf hotel india"
            " juliet kilo lima mike november oscar papa quebec romeo"
            " sierra tango uniform victor whiskey xray yankee zulu"
        ).split(),
        "abcdefghijklmnopqrstuvwxyz",
        strict=True,
    )
)
_SMALL = dict(
    zip(
        (
            "zero one two three four five six seven eight nine ten e"
            "leven twelve thirteen fourteen fifteen sixteen seventee"
            "n eighteen nineteen"
        ).split(),
        range(20),
        strict=True,
    )
)
_TENS = dict(
    zip(
        "twenty thirty forty fifty sixty seventy eighty ninety".split(),
        range(20, 100, 10),
        strict=True,
    )
)
_ORDINALS = dict(
    zip(
        (
            "first second third fourth fifth sixth seventh eighth ni"
            "nth tenth eleventh twelfth thirteenth fourteenth fiftee"
            "nth sixteenth seventeenth eighteenth nineteenth twentie"
            "th"
        ).split(),
        range(1, 21),
        strict=True,
    )
)
_ORDINALS["thirtieth"] = 30
_MONTHS = {datetime(2000, i, 1).strftime("%B").lower(): i for i in range(1, 13)}


def spoken_name(text: str) -> str | None:
    answer = re.sub(
        r"^(my name is|my name['’]s|this is|i am|i['’]m|it is|it['’]s)\s+",
        "",
        text.strip(),
        flags=re.I,
    ).strip(" .")
    # STT may render the explicit spelling marker as either English variant.
    # Both use the same strict alphabet parser; neither permits fuzzy matching.
    if not answer.lower().startswith(("spelled ", "spelt ")):
        return answer
    tokens = re.findall(r"[a-z0-9]+", answer.lower())[1:]
    output = []
    for token in tokens:
        if token == "space":
            output.append(" ")
        elif token in _NATO:
            output.append(_NATO[token])
        elif token in _DIGITS:
            output.append(_DIGITS[token])
        elif re.fullmatch(r"[a-z]|[0-9]+", token):
            output.append(token)
        else:
            return None
    name = "".join(output).strip()
    return name if re.fullmatch(r"[a-z0-9]+(?: [a-z0-9]+)+", name) else None


def _under100(tokens):
    if len(tokens) == 1:
        word = tokens[0]
        return _SMALL.get(
            word,
            _TENS.get(
                word,
                _ORDINALS.get(
                    word, int(word) if word.isdigit() and len(word) <= 2 else None
                ),
            ),
        )
    if len(tokens) == 2 and tokens[0] in _TENS:
        unit = _SMALL.get(tokens[1], _ORDINALS.get(tokens[1]))
        if unit is not None and 1 <= unit <= 9:
            return _TENS[tokens[0]] + unit
    return None


def spoken_birth_date(text: str) -> str | None:
    answer = re.sub(
        r"^(my date of birth is|my birthday is|my birthday['’]s|my birth date is|"
        r"i was born on|i was born|born on)\s+",
        "",
        text.strip(),
        flags=re.I,
    ).strip(" .")
    answer = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", answer)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(answer, fmt).date().isoformat()
        except ValueError:
            pass
    words = re.sub(r"[,.-]", " ", answer.lower()).split()
    if not words or words[0] not in _MONTHS:
        return None
    candidates = set()
    for split in (2, 3):
        day = _under100(words[1:split])
        year_words = words[split:]
        year = None
        if len(year_words) == 1 and re.fullmatch(r"\d{4}", year_words[0]):
            year = int(year_words[0])
        elif year_words and year_words[0] in ("eighteen", "nineteen", "twenty"):
            tail = year_words[1:]
            rem = 0 if tail == ["hundred"] else _under100(tail)
            if rem is not None:
                year = _SMALL.get(year_words[0], 20) * 100 + rem
        elif year_words[:2] == ["two", "thousand"]:
            tail = year_words[2:]
            if tail[:1] == ["and"]:
                tail = tail[1:]
            rem = 0 if not tail else _under100(tail)
            if rem is not None:
                year = 2000 + rem
        if day is not None and year is not None:
            try:
                candidates.add(date(year, _MONTHS[words[0]], day).isoformat())
            except ValueError:
                pass
    return candidates.pop() if len(candidates) == 1 else None
