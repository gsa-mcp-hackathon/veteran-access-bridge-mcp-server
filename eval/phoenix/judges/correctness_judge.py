from __future__ import annotations

from phoenix.evals import ClassificationEvaluator

from .common import judge_llm

_TEMPLATE = """You are judging a synthetic Veteran scheduling MCP agent.

Question:
{input}

Agent answer:
{output}

Reference answer:
{reference}

Decide whether the agent answer is factually equivalent to the reference.
Allow harmless differences in capitalization, punctuation, ordering of an
unordered list, and brief surrounding explanation. Do not allow invented
authorization, verification, booking, workflow state, or source facts.

Return correct or incorrect.
"""


def match_expected_response(input, output, expected):
    evaluator = ClassificationEvaluator(
        name="correctness",
        prompt_template=_TEMPLATE,
        llm=judge_llm(),
        choices={"correct": 1, "incorrect": 0},
    )
    result = evaluator.evaluate(
        {
            "input": input,
            "output": output,
            "reference": expected,
        }
    )
    return result[0]
