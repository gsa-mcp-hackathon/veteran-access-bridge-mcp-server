import importlib.util
from pathlib import Path

import pytest

from veteran_access_bridge.mcp import session_scope as scope


def candidate():
    path = Path(__file__).parents[1] / "eval/voice/options_workflow_candidate.py"
    spec = importlib.util.spec_from_file_location("options_candidate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare_options


@pytest.mark.asyncio
async def test_unbound_real_scope_boundary_prevents_sequence():
    async def execute(name, args):
        async def forbidden():
            pytest.fail("Unbound tool executed")

        return await scope.scoped_call("invalid", name, args["case_id"], forbidden)

    with pytest.raises(PermissionError):
        await candidate()(execute, case_id="case")


@pytest.mark.asyncio
@pytest.mark.parametrize("verified", [True, False])
async def test_dependency_and_no_writes(verified):
    calls = []

    async def execute(name, args):
        calls.append(name)
        if len(calls) == 1:
            return {
                "case_id": "case",
                "identity_matches": verified,
                "source_verified": verified,
            }
        return {"options": []}

    if verified:
        assert await candidate()(execute, case_id="case") == {"options": []}
        assert calls == [
            "get_va_patient_health_sandbox_summary",
            "search_call_appointments",
        ]
    else:
        with pytest.raises(PermissionError):
            await candidate()(execute, case_id="case")
        assert calls == ["get_va_patient_health_sandbox_summary"]
