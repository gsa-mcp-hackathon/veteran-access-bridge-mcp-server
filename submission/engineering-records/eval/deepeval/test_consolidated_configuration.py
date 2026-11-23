import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from mcp.types import Tool
from verify_consolidated_configuration import (
    ALLOWED,
    CATALOG,
    FACILITY_READS,
    ExportLoader,
    verify,
)


def approved_fixture():
    return yaml.safe_load(
        (Path(__file__).parent / "fixtures/catalog-integrity.yaml").read_text(
            encoding="utf-8"
        )
    )


def scope_policy():
    return json.loads(Path(__file__).with_name("catalog-scope-policy.json").read_text())


def fixture():
    prefix = "consolidated:"
    binding = {
        "server_url": "https://example.test/mcp/",
        "connections": {"existing": "same"},
    }
    registry = []
    for name in sorted(CATALOG):
        scoped = name not in FACILITY_READS | {"get_scheduling_handoff"}
        props = (
            {"case_id": {"type": "string"}, "session_scope": {"type": "string"}}
            if scoped
            else {}
        )
        definition = {
            "name": name,
            "inputSchema": {"type": "object", "properties": props},
            "description": "Fixture metadata.",
        }
        if scoped:
            definition.update(
                description="Scheduling encounter metadata.",
                annotations={"readOnlyHint": True},
            )
        registry.append(definition)
    imported = [
        {
            "name": prefix + t["name"],
            "input_schema": copy.deepcopy(t["inputSchema"]),
            "description": t["description"],
            "annotations": copy.deepcopy(t.get("annotations")),
            "binding": {"mcp": copy.deepcopy(binding)},
        }
        for t in registry
    ]
    agent = {
        "name": "veteran_access_agent_m64",
        "llm": "existing-model",
        "tools": sorted(prefix + n for n in ALLOWED),
        "context_variables": ["vab_case_id", "vab_mcp_scope"],
        "instructions": "reviewed",
    }
    return [
        registry,
        imported,
        copy.deepcopy(agent),
        copy.deepcopy(agent),
        copy.deepcopy(agent),
    ], {
        "prefix": prefix,
        "binding": binding,
        "approved": approved_fixture(),
        "scope_policy": scope_policy(),
    }


def test_acceptance_is_configuration_only():
    args, kw = fixture()
    assert verify(*args, **kw) == {
        "catalog_tools": 21,
        "scoped_catalog_tools": 17,
        "avery_tools": 13,
        "scoped_avery_tools": 10,
        "live_acceptance": "NOT_RUN_BY_THIS_CHECK",
    }


@pytest.mark.parametrize(
    "attack",
    [
        "missing",
        "duplicate",
        "schema",
        "connection",
        "restricted",
        "alias",
        "model",
        "context",
        "instruction",
    ],
)
def test_configuration_drift_is_rejected(attack):
    args, kw = fixture()
    registry, imported, before, candidate, exported = args
    if attack == "missing":
        registry.pop()
    elif attack == "duplicate":
        imported.append(copy.deepcopy(imported[0]))
    elif attack == "schema":
        imported[0]["input_schema"]["properties"].pop("session_scope")
    elif attack == "connection":
        imported[0]["binding"]["mcp"]["connections"] = {}
    elif attack == "restricted":
        exported["tools"][0] = kw["prefix"] + "record_veteran_confirmation"
    elif attack == "alias":
        exported["tools"][0] = "old:" + exported["tools"][0].split(":")[1]
    elif attack == "model":
        exported["llm"] = "other"
    elif attack == "context":
        exported["context_variables"].remove("vab_mcp_scope")
    else:
        exported["instructions"] = "unreviewed"
    with pytest.raises(ValueError):
        verify(*args, **kw)


@pytest.mark.parametrize(
    "change",
    [
        "description_only",
        "both_descriptions",
        "both_schemas",
        "both_names",
        "both_annotations",
        "new_metadata",
        "binding_extra",
        "toolkit_prefix",
    ],
)
def test_independent_contract_rejects_drift_before_local_acceptance(change):
    from unittest.mock import Mock

    args, kw = fixture()
    original = next(t for t in args[0] if t["name"] == "get_scheduling_encounter")
    exported = next(t for t in args[1] if t["name"] == kw["prefix"] + original["name"])
    if change in {"description_only", "both_descriptions"}:
        exported["description"] += " (sample)"
        if change == "both_descriptions":
            original["description"] = exported["description"]
    elif change == "both_schemas":
        original["inputSchema"]["additionalProperties"] = False
        exported["input_schema"]["additionalProperties"] = False
    elif change == "both_names":
        original["name"] += "_alternate"
        exported["name"] += "_alternate"
    elif change == "both_annotations":
        original["annotations"]["readOnlyHint"] = False
        exported["annotations"]["readOnlyHint"] = False
    elif change == "new_metadata":
        exported["_meta"] = {"access": "different"}
    elif change == "binding_extra":
        exported["binding"]["mcp"]["transport"] = "alternate"
    else:
        kw["prefix"] = "other:"
    downstream = Mock()
    with pytest.raises(ValueError):
        downstream(verify(*args, **kw))
    downstream.assert_not_called()


def test_metadata_key_order_is_immaterial():
    args, kw = fixture()
    for entry in args[1]:
        entry["input_schema"] = dict(reversed(entry["input_schema"].items()))
    assert verify(*args, **kw)["catalog_tools"] == 21


@pytest.mark.parametrize(
    "change",
    [
        "unchanged",
        "equal_aliases",
        "addition",
        "removal",
        "nested_change",
        "discovery_conflict",
        "import_conflict",
        "approval_conflict",
        "empty_addition",
        "wrong_type",
    ],
)
def test_sdk_metadata_matches_independent_approval(change):
    args, kw = fixture()
    name = "get_va_sandbox_health_facility"
    index = next(i for i, row in enumerate(args[0]) if row["name"] == name)
    value = {"labels": {"reviewed": True}}
    sdk = Tool.model_validate({**args[0][index], "_meta": copy.deepcopy(value)})
    observed = args[0][index] = sdk.model_dump(mode="json")
    assert observed["meta"] == value
    imported = args[1][index]
    approved = kw["approved"]["tools"][name] = copy.deepcopy(
        kw["approved"]["tools"][name]
    )
    imported["_meta"] = copy.deepcopy(value)
    approved["_meta"] = copy.deepcopy(value)
    if change == "equal_aliases":
        observed["_meta"] = copy.deepcopy(value)
        imported["meta"] = copy.deepcopy(value)
    elif change == "addition":
        del approved["_meta"]
    elif change == "removal":
        imported.pop("_meta")
    elif change == "nested_change":
        observed["meta"]["labels"]["reviewed"] = 1
    elif change == "discovery_conflict":
        observed["_meta"] = None
    elif change == "import_conflict":
        imported["meta"] = {}
    elif change == "approval_conflict":
        approved["meta"] = {}
    elif change == "empty_addition":
        del approved["_meta"]
        observed["meta"] = {}
    elif change == "wrong_type":
        imported["_meta"] = []
    if change in {"unchanged", "equal_aliases"}:
        assert verify(*args, **kw)["live_acceptance"] == "NOT_RUN_BY_THIS_CHECK"
    else:
        with pytest.raises(ValueError, match="meta"):
            verify(*args, **kw)


def test_duplicate_metadata_keys_rejected_during_export_parsing():
    with pytest.raises(ValueError, match="Duplicate"):
        yaml.load("meta: {label: one, label: two}", Loader=ExportLoader)


def current_tools_fixture():
    args, kw = fixture()
    names = [
        "get_crm_case",
        "record_crm_interaction",
        "create_crm_follow_up",
        "update_crm_follow_up",
        "search_call_appointments",
        "select_call_appointment",
        "book_call_appointment",
        "search_call_knowledge",
    ]
    source = next(t for t in args[0] if t["name"] == "get_scheduling_encounter")
    imported = next(t for t in args[1] if t["name"] == kw["prefix"] + source["name"])
    reference = kw["approved"]["tools"][source["name"]]
    args[0] = [dict(copy.deepcopy(source), name=name) for name in names]
    args[1] = [
        dict(copy.deepcopy(imported), name=kw["prefix"] + name) for name in names
    ]
    kw["approved"]["tools"] = {name: copy.deepcopy(reference) for name in names}
    kw["approved"]["agent_tools"] = ["get_crm_case", "search_call_appointments"]
    for agent in args[2:]:
        agent["tools"] = [kw["prefix"] + name for name in kw["approved"]["agent_tools"]]
    return args, kw


def test_scoped_counts_follow_current_policy_and_attachments():
    args, kw = current_tools_fixture()
    result = verify(*args, **kw)
    assert result["scoped_catalog_tools"] == result["catalog_tools"] == 8
    assert result["scoped_avery_tools"] == result["avery_tools"] == 2


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "unknown",
        "wrong_class",
        "version",
        "missing_case_id",
        "missing_session_scope",
        "wrong_case_type",
        "wrong_scope_type",
        "wrong_root_type",
    ],
)
def test_scope_policy_enforced_even_when_exports_match_catalog(change):
    args, kw = current_tools_fixture()
    name = "get_crm_case"
    policy = kw["scope_policy"]
    if change == "missing":
        del policy["tools"][name]
    elif change == "unknown":
        policy["tools"][name] = "optional"
    elif change == "wrong_class":
        policy["tools"][name] = "no_case"
    elif change == "version":
        policy["version"] = "unsupported"
    else:
        schema = kw["approved"]["tools"][name]["inputSchema"]
        if change.startswith("missing_"):
            del schema["properties"][change.removeprefix("missing_")]
        elif change == "wrong_root_type":
            schema["type"] = "array"
        else:
            field = "case_id" if change == "wrong_case_type" else "session_scope"
            schema["properties"][field]["type"] = "integer"
        args[0][0]["inputSchema"] = copy.deepcopy(schema)
        args[1][0]["input_schema"] = copy.deepcopy(schema)
    with pytest.raises(ValueError, match="scope"):
        verify(*args, **kw)


def test_cli_uses_committed_approval_even_if_working_copy_changes(tmp_path):
    # Exercise the actual command from outside its repository.
    root = tmp_path / "checkout"
    directory = root / "eval/deepeval"
    directory.mkdir(parents=True)
    script = directory / "verify_consolidated_configuration.py"
    shutil.copy(Path(__file__).with_name(script.name), script)
    baseline = directory / "approved-catalog.json"
    policy_file = directory / "catalog-scope-policy.json"
    policy_file.write_text(json.dumps(scope_policy()), encoding="utf-8")
    approved = approved_fixture()
    baseline.write_text(json.dumps(approved), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "eval"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Reviewed fixture",
        ],
        cwd=root,
        check=True,
    )
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    args, kw = fixture()
    cmd = [
        sys.executable,
        str(script),
        "--approved-commit",
        commit,
        "--prefix",
        kw["prefix"],
    ]
    for flag, obj in zip(
        ("registry", "imported", "before-agent", "candidate", "exported", "binding"),
        [*args, kw["binding"]],
        strict=True,
    ):
        path = tmp_path / (flag + ".json")
        path.write_text(json.dumps(obj), encoding="utf-8")
        cmd.extend(["--" + flag, str(path)])
    policy_file.write_text("{}", encoding="utf-8")
    assert json.loads(subprocess.check_output(cmd, cwd=tmp_path))["avery_tools"] == 13
    name = "get_scheduling_encounter"
    for flag in ("registry", "imported"):
        path = tmp_path / (flag + ".json")
        rows = json.loads(path.read_text(encoding="utf-8"))
        next(t for t in rows if t["name"].split(":")[-1] == name)["description"] += (
            " (sample)"
        )
        path.write_text(json.dumps(rows), encoding="utf-8")
    approved["tools"][name]["description"] += " (sample)"
    baseline.write_text(json.dumps(approved), encoding="utf-8")
    rejected = subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True)
    assert rejected.returncode != 0 and not rejected.stdout
    assert "description differs" in rejected.stderr
