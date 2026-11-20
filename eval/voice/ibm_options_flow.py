"""Isolated IBM native flow candidate; importing this file does not deploy it.

Uses only the evaluation toolkit. Both MCP calls must receive the current
host-issued scope. The backend independently rejects option searches until its
patient read has verified identity. No authority is created by this flow.
"""

from typing import Any

from ibm_watsonx_orchestrate.flow_builder.flows import Flow, flow
from ibm_watsonx_orchestrate.flow_builder.masking_utils import MaskingPolicy
from pydantic import BaseModel


class OptionsInput(BaseModel):
    case_id: str
    session_scope: str
    date_from: str = ""
    date_to: str = ""
    time_preference: str = "ANY"


class OptionsOutput(BaseModel):
    options_result: Any


@flow(
    name="vab_latency_eval_options_flow",
    description="Read verified patient, then scoped appointment options. Never book.",
    input_schema=OptionsInput,
    output_schema=OptionsOutput,
    suppress_agent_summarization=False,
)
def options_flow(aflow: Flow) -> Flow:
    patient = aflow.tool(
        "vab-latency-eval-mcp:get_va_patient_health_sandbox_summary",
        name="patient",
    )
    options = aflow.tool(
        "vab-latency-eval-mcp:search_call_appointments", name="options"
    )
    for node in (patient, options):
        node.map_input("case_id", "flow.input.case_id")
        node.map_input("session_scope", "flow.input.session_scope")
    for field in ("date_from", "date_to", "time_preference"):
        options.map_input(field, "flow.input." + field)
    aflow.sequence(aflow.start("start"), patient, options, aflow.end("end"))
    aflow.map_output("options_result", "flow.options.output")
    aflow.mask_property("flow.input.session_scope", MaskingPolicy.MASK_ALL)
    return aflow
