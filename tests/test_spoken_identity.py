import pytest

from veteran_access_bridge.voice.spoken_identity import spoken_birth_date, spoken_name


@pytest.mark.parametrize(
    "spoken,expected",
    [
        (
            "My name is spelled Juliet Alpha November Echo space "
            "Delta Oscar Echo one two three.",
            "jane doe123",
        ),
        ("Spelled J A N E space D O E 123.", "jane doe123"),
        ("Spelt J A N E space D O E 123.", "jane doe123"),
        ("Spelt Juliet probably Echo space Delta.", None),
        ("Spelt J A N E space D O E 124.", "jane doe124"),
        ("Jane Doe123.", "Jane Doe123"),
        (
            "Spelled Juliet Alpha November Echo space Delta Oscar Echo one two four.",
            "jane doe124",
        ),
        ("Spelled Juliet probably Echo space Delta. ", None),
        ("Spelled Juliet Alpha November Echo", None),
    ],
)
def test_exact_name_formatting(spoken, expected):
    assert spoken_name(spoken) == expected


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("November twelfth nineteen sixty eight.", "1968-11-12"),
        ("January twenty first nineteen eighty five", "1985-01-21"),
        ("February twenty ninth two thousand", "2000-02-29"),
        ("March third two thousand and one", "2001-03-03"),
        ("November 12, 1968.", "1968-11-12"),
        ("1968-11-12", "1968-11-12"),
        ("November thirteenth nineteen sixty eight", "1968-11-13"),
        ("February thirtieth nineteen eighty", None),
        ("December thirtieth nineteen forty nine.", "1949-12-30"),
        ("December thirty first nineteen forty nine.", "1949-12-31"),
        ("November twelfth maybe nineteen sixty eight", None),
        ("November twelfth sixty eight", None),
    ],
)
def test_exact_birth_date_formatting(spoken, expected):
    assert spoken_birth_date(spoken) == expected
