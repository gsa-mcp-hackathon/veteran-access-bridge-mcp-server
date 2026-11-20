from veteran_access_bridge.mcp.tools.verify_synthetic_identity import (
    run,
)

CASE_ID = "DEMO-CARD-5000335-001"


def test_explicit_spelling_requires_exact_letters_and_known_tokens() -> None:
    intake = "DEMO-PC-VOICE-INTAKE-001"
    name = (
        "My name is spelled Lima Uniform India Sierra nine two three space "
        "Mike Alpha Yankee Echo Romeo three seven zero."
    )
    assert run(intake, name, "1969-07-03")["verified"] is True
    assert run(intake, name.replace("India", "Oscar"), "1969-07-03")[
        "verified"
    ] is False
    assert run(intake, name.replace("India", "maybe"), "1969-07-03")[
        "verified"
    ] is False


def test_literal_spoken_date_preserves_exact_identity_match() -> None:
    intake = "DEMO-PC-VOICE-INTAKE-001"
    assert run(intake, "Luis923 Mayer370", "July third, nineteen sixty nine")[
        "verified"
    ] is True
    assert run(intake, "Luis923 Mayer370", "July fourth, nineteen sixty nine")[
        "verified"
    ] is False
    assert run(intake, "Luis923 Mayer370", "July maybe third nineteen sixty nine")[
        "verified"
    ] is False


def test_verify_synthetic_identity_matches_approved_fixture() -> None:
    result = run(CASE_ID, "Mr. Mariano761 Ruelas156", "1907-11-20")

    assert result == {
        "verified": True,
        "synthetic": True,
        "case_id": CASE_ID,
        "reason": "MATCH",
    }


def test_verify_synthetic_identity_normalizes_name_case_and_punctuation() -> None:
    result = run(CASE_ID, "MR Mariano761   Ruelas156", "1907-11-20")

    assert result["verified"] is True
    assert result["reason"] == "MATCH"


def test_verify_synthetic_identity_fails_closed_on_mismatch() -> None:
    result = run(CASE_ID, "Someone Else", "1907-11-20")

    assert result["verified"] is False
    assert result["reason"] == "NO_MATCH"
    assert "full_name" not in result
    assert "birth_date" not in result


def test_verify_synthetic_identity_accepts_spoken_birth_date() -> None:
    result = run(CASE_ID, "Mr. Mariano761 Ruelas156", "November 20, 1907")

    assert result["verified"] is True
    assert result["reason"] == "MATCH"


def test_verify_synthetic_identity_accepts_name_without_honorific() -> None:
    result = run(CASE_ID, "Mariano761 Ruelas156", "11/20/1907")

    assert result["verified"] is True
    assert result["reason"] == "MATCH"


def test_verify_synthetic_identity_fails_closed_on_invalid_date() -> None:
    result = run(CASE_ID, "Mr. Mariano761 Ruelas156", "not-a-date")

    assert result["verified"] is False
    assert result["reason"] == "INVALID_BIRTH_DATE_FORMAT"


def test_verify_synthetic_identity_fails_closed_on_unknown_case() -> None:
    result = run("DEMO-UNKNOWN-001", "Synthetic Veteran", "1900-01-01")

    assert result["verified"] is False
    assert result["reason"] == "UNKNOWN_SYNTHETIC_CASE"
