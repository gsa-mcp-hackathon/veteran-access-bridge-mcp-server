/* Static catalog derived from src/veteran_access_bridge/mcp/tools registration.
   29-tool configuration requires CRM and agent-scheduling flags; 21 were attached
   to the reviewed November 18 Avery configuration. This is not live discovery. */
(() => {
  const root = document.getElementById("vab-tool-explorer");
  if (!root) return;
  const tools = [
  {
    "name": "verify_synthetic_identity",
    "category": "Identity",
    "description": "Verify an approved synthetic caller against governed fixture data.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/verify_synthetic_identity.py"
  },
  {
    "name": "determine_workflow_state",
    "category": "Scheduling",
    "description": "Determine the case's workflow state using deterministic rules.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/determine_workflow_state.py"
  },
  {
    "name": "search_availability",
    "category": "Scheduling",
    "description": "Return normalized appointment availability for a synthetic case.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/search_availability.py"
  },
  {
    "name": "assess_access_standard",
    "category": "Access",
    "description": "Compare available care timing with the configured access standard.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/assess_access_standard.py"
  },
  {
    "name": "check_community_care_eligibility",
    "category": "Access",
    "description": "Return a bounded verification status; does not grant Community Care eligibility.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/check_community_care_eligibility.py"
  },
  {
    "name": "get_case_lifecycle_state",
    "category": "Lifecycle",
    "description": "Read the synthetic case lifecycle state and event history.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/get_case_lifecycle_state.py"
  },
  {
    "name": "get_scheduling_encounter",
    "category": "Scheduling",
    "description": "Read canonical scheduling evidence; does not book an appointment.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/get_scheduling_encounter.py"
  },
  {
    "name": "prepare_scheduling_handoff",
    "category": "Lifecycle",
    "description": "Prepare a scheduling handoff review artifact; no booking.",
    "attachedToAvery": false,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/prepare_scheduling_handoff.py"
  },
  {
    "name": "get_scheduling_handoff",
    "category": "Lifecycle",
    "description": "Read a prepared scheduling handoff artifact.",
    "attachedToAvery": false,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/get_scheduling_handoff.py"
  },
  {
    "name": "validate_option_selection",
    "category": "Lifecycle",
    "description": "Check whether a proposed handoff option can be selected.",
    "attachedToAvery": false,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/validate_option_selection.py"
  },
  {
    "name": "record_option_selection",
    "category": "Lifecycle",
    "description": "Record a scheduler selection in the restricted handoff path.",
    "attachedToAvery": false,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/record_option_selection.py"
  },
  {
    "name": "prepare_veteran_confirmation_request",
    "category": "Lifecycle",
    "description": "Prepare a Veteran confirmation request artifact.",
    "attachedToAvery": false,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/prepare_veteran_confirmation_request.py"
  },
  {
    "name": "record_veteran_confirmation",
    "category": "Lifecycle",
    "description": "Record the Veteran's response within the restricted confirmation flow.",
    "attachedToAvery": false,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/record_veteran_confirmation.py"
  },
  {
    "name": "validate_booking_preconditions",
    "category": "Lifecycle",
    "description": "Check booking preconditions without committing a booking.",
    "attachedToAvery": false,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/validate_booking_preconditions.py"
  },
  {
    "name": "record_lifecycle_event",
    "category": "Lifecycle",
    "description": "Record a governed synthetic lifecycle transition.",
    "attachedToAvery": false,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/record_lifecycle_event.py"
  },
  {
    "name": "get_va_sandbox_health_facility",
    "category": "VA sandbox",
    "description": "Read a facility record from the enabled VA sandbox adapter.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/va_sandbox_readonly.py"
  },
  {
    "name": "search_va_sandbox_health_facilities",
    "category": "VA sandbox",
    "description": "Search facility metadata through the enabled sandbox adapter.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/va_sandbox_readonly.py"
  },
  {
    "name": "get_va_sandbox_health_facility_service",
    "category": "VA sandbox",
    "description": "Read VA sandbox facility service details.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/va_sandbox_readonly.py"
  },
  {
    "name": "get_va_community_care_case_summary",
    "category": "VA sandbox",
    "description": "Read configured Community Care sandbox case context.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/va_sandbox_readonly.py"
  },
  {
    "name": "get_va_patient_health_sandbox_summary",
    "category": "VA sandbox",
    "description": "Read configured patient health sandbox summary data.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/va_sandbox_readonly.py"
  },
  {
    "name": "get_va_clinical_health_case_summary",
    "category": "VA sandbox",
    "description": "Read configured clinical health sandbox context.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/va_sandbox_readonly.py"
  },
  {
    "name": "get_crm_case",
    "category": "CRM",
    "description": "Read scoped synthetic CRM case details.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/crm.py"
  },
  {
    "name": "record_crm_interaction",
    "category": "CRM",
    "description": "Write a governed CRM interaction record.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/crm.py"
  },
  {
    "name": "create_crm_follow_up",
    "category": "CRM",
    "description": "Create a governed CRM follow-up item.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/crm.py"
  },
  {
    "name": "update_crm_follow_up",
    "category": "CRM",
    "description": "Update a governed CRM follow-up item.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/crm.py"
  },
  {
    "name": "search_call_appointments",
    "category": "Avery voice",
    "description": "Search appointment options within a trusted voice call.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/voice_workflow.py"
  },
  {
    "name": "select_call_appointment",
    "category": "Avery voice",
    "description": "Select a call-scoped appointment option, not a booking.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/voice_workflow.py"
  },
  {
    "name": "book_call_appointment",
    "category": "Avery voice",
    "description": "Request a protected synthetic booking subject to trusted authority checks.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/voice_workflow.py"
  },
  {
    "name": "search_call_knowledge",
    "category": "Avery voice",
    "description": "Retrieve call-bound supporting knowledge without granting authority.",
    "attachedToAvery": true,
    "source": "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/voice_workflow.py"
  }
];
  const search = root.querySelector("#vab-tool-search");
  const category = root.querySelector("#vab-tool-category");
  const attachment = root.querySelector("#vab-tool-attachment");
  const list = root.querySelector("#vab-tool-list");
  const count = root.querySelector("#vab-tool-count");
  const make = (tag, cls, text) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  for (const value of [...new Set(tools.map(x => x.category))].sort()) {
    const opt = new Option(value, value);
    category.add(opt);
  }
  function render() {
    const q = search.value.trim().toLowerCase();
    const selected = tools.filter(t =>
      (!q || [t.name,t.description,t.category].some(s=>s.toLowerCase().includes(q))) &&
      (category.value === "all" || t.category === category.value) &&
      (attachment.value === "all" || t.attachedToAvery === (attachment.value === "attached"))
    );
    count.textContent = selected.length + " of " + tools.length + " registered tools shown";
    list.replaceChildren();
    for (const t of selected) {
      const card = make("details","vab-tool");
      const head = make("summary");
      head.append(make("code","vab-tool-name",t.name));
      head.append(make("span",t.attachedToAvery?"vab-tool-pill attached":"vab-tool-pill restricted",t.attachedToAvery?"Attached to Avery":"Not attached to Avery"));
      card.append(head);
      const body = make("div","vab-tool-body");
      body.append(make("p","",t.description));
      body.append(make("p","vab-tool-meta",t.category + " · November 18 reviewed configuration"));
      const a = make("a","","View tool source on GitHub");
      a.href=t.source; a.target="_blank"; a.rel="noopener noreferrer";
      body.append(a);
      card.append(body);
      list.append(card);
    }
    if(!selected.length) list.append(make("p","vab-tool-empty","No tools match these filters."));
  }
  search.addEventListener("input",render);
  category.addEventListener("change",render);
  attachment.addEventListener("change",render);
  render();
})();
