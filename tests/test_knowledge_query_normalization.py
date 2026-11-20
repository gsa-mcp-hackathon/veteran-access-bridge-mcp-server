import pytest

from veteran_access_bridge.services.call_knowledge import knowledge_search_term


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("How do I prepare for my primary care appointment?", "primary care"),
        ("How do I cancel my appointment?", "cancel"),
        ("Can I have a video appointment?", "video"),
        ("Can I cancel a video appointment?", "Can I cancel a video appointment?"),
        ("I have a billing question", "I have a billing question"),
        ("videographer", "videographer"),
        ("%' OR 1=1 --", "%' OR 1=1 --"),
    ],
)
def test_opt_in_bounded_topics(monkeypatch, query, expected):
    monkeypatch.setenv("VAB_KB_QUERY_NORMALIZATION", "true")
    assert knowledge_search_term(query) == expected


def test_default_preserves_existing_query(monkeypatch):
    monkeypatch.delenv("VAB_KB_QUERY_NORMALIZATION", raising=False)
    query = "How do I cancel my appointment?"
    assert knowledge_search_term(query) == query
