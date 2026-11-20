"""Exercise the deployed guard predicate without importing the IBM SDK."""

import ast
import re
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "case,scope,allowed",
    [
        ("DEMO-PC-VOICE-INTAKE-001", "vab_scope_" + "a" * 43, True),
        ("VAB-DEMO-20261113-CASE-048", "vab_scope_" + "a" * 43, True),
        (
            "VAB-CALL-0db65627-0c07-59eb-87eb-89b72eb6d0b5",
            "vab_scope_" + "a" * 43,
            True,
        ),
        ("VAB-CALL-0db65627-0c07-59eb-87eb-89b72eb6d0b5", "", False),
        ("VAB-CALL-any-patient", "vab_scope_" + "a" * 43, False),
        (
            "VAB-CALL-0db65627-0c07-49eb-87eb-89b72eb6d0b5",
            "vab_scope_" + "a" * 43,
            False,
        ),
        ("real-patient", "vab_scope_" + "a" * 43, False),
    ],
)
def test_application_context_formats(case, scope, allowed):
    path = Path(__file__).parents[1] / "deploy/ibm/orchestrate/require_voice_context.py"
    tree = ast.parse(path.read_text())
    predicate = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "has_application_context"
    )
    namespace = {"re": re}
    exec(
        compile(ast.Module(body=[predicate], type_ignores=[]), str(path), "exec"),
        namespace,
    )
    assert (
        namespace["has_application_context"](
            {"context": {"vab_case_id": case, "vab_mcp_scope": scope}}
        )
        is allowed
    )
