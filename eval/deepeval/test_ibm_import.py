import pytest
from import_ibm_smoke import decode_result


def test_literal_result_retained():
    raw = (
        "{'content': [TextContent(type='text', text='{}', "
        "annotations=None, meta=None)], "
        "'structuredContent': {'verified': False}, 'isError': False}"
    )
    assert decode_result(raw) == {
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": {"verified": False},
        "isError": False,
    }


@pytest.mark.parametrize(
    "raw",
    [
        "{'content': [__import__('os').system('echo forbidden')], 'isError': False}",
        "{'content': [TextContent(type='text', text=str(42))], 'isError': False}",
        "{'content': [], 'structuredContent': dict(verified=True), 'isError': False}",
    ],
)
def test_nonliteral_content_rejected(raw):
    with pytest.raises(ValueError):
        decode_result(raw)
