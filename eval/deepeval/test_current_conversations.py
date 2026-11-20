import json

import pytest
from score_current_conversations import convert, interaction_turns


def test_tool_events_precede_speech_without_inventing_dialogue():
    calls = [{"name": "identity"}, {"name": "read"}]
    turns = interaction_turns(
        [
            {"role": "user", "content": "My options"},
            {"role": "assistant", "content": "No eligible options", "calls": calls},
        ]
    )
    assert [t["content"] for t in turns] == [
        "My options",
        "",
        "",
        "No eligible options",
    ]
    assert [c for t in turns for c in t["calls"]] == calls


def test_no_call_conversation_does_not_invent_tool_events():
    assert interaction_turns([{"role": "assistant", "content": "No"}]) == [
        {"role": "assistant", "content": "No", "calls": []}
    ]


def test_keeps_turns_and_denied_call_without_executing_response_text():
    messages = [
        {"role": "user", "type": "text", "content": "Verify me"},
        {
            "type": "tool_call",
            "content": json.dumps(
                {
                    "name": "verify_synthetic_identity",
                    "id": "1",
                    "args": {"session_scope": "vab_scope_private"},
                }
            ),
        },
        {
            "type": "tool_response",
            "content": json.dumps(
                {
                    "name": "verify_synthetic_identity",
                    "tool_call_id": "1",
                    "content": (
                        "Error calling tool 'verify_synthetic_identity': scope required"
                    ),
                }
            ),
        },
        {"role": "assistant", "type": "text", "content": "Session required"},
        {"role": "user", "type": "text", "content": "Okay"},
        {"role": "assistant", "type": "text", "content": "Contact staff"},
    ]
    turns = convert(messages)
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant"]
    assert turns[1]["calls"][0]["result"]["isError"] is True
    assert turns[1]["calls"][0]["args"]["session_scope"] == "[REDACTED_SCOPE]"
    assert turns[3]["calls"] == []


def test_empty_trace_is_not_a_pass():
    with pytest.raises(ValueError, match="Incomplete"):
        convert([])


def test_missing_result_is_rejected():
    with pytest.raises(ValueError, match="Missing"):
        convert(
            [
                {
                    "type": "tool_call",
                    "content": json.dumps(
                        {"name": "verify_synthetic_identity", "id": "1", "args": {}}
                    ),
                },
                {"role": "assistant", "type": "text", "content": "Done"},
            ]
        )
