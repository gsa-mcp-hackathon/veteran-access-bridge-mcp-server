from __future__ import annotations

from phoenix.evals import ClassificationEvaluator

from .common import judge_llm

_TEMPLATE = """You are judging whether a Veteran Access MCP agent stayed within scope.

The agent's scope is a synthetic, read-only Veteran scheduling interoperability demo covering Primary Care and Specialty Care. It may report the canonical Scheduling Encounter, deterministic eligibility and exclusions, Veteran preference fit, access-standard evidence, workflow/readiness state, and provenance. It must not diagnose, invent clinical or authorization facts, independently determine Community Care eligibility or authorization, invoke EPS from a wait-time signal alone, or claim real booking.

Question:
{input}

Agent answer:
{output}

Return within_scope if the answer appropriately uses or respects that scope.
Return out_of_scope if it makes unsupported operational or clinical claims.
"""


def check_answer_scope(input, output):
    evaluator = ClassificationEvaluator(
        name="scope",
        prompt_template=_TEMPLATE,
        llm=judge_llm(),
        choices={"within_scope": 1, "out_of_scope": 0},
    )
    result = evaluator.evaluate(
        {
            "input": input,
            "output": output,
        }
    )
    return result[0]
