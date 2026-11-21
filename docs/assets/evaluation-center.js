(async function () {
  const explorer = document.querySelector(".ec-explorer");
  if (!explorer) return;
  const header = document.querySelector(".md-header__inner");
  if (header) {
    const navigation = document.createElement("nav");
    navigation.className = "ec-topnav";
    navigation.setAttribute("aria-label", "Main sections");
    for (const [name, path] of [
      ["Solution & Architecture", "../solution-architecture/"], ["MCP Implementation", "../mcp-implementation/"],
      ["Security & Governance", "../security-governance/"], ["Evaluation & Results", "./"],
      ["Demonstration", "../demonstration/"], ["Developer Guide", "../developer-guide/"],
      ["GitHub", "https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server"]
    ]) {
      const link = document.createElement("a");
      link.href = path;
      link.textContent = name;
      if (path === "./") link.setAttribute("aria-current", "page");
      navigation.append(link);
    }
    header.append(navigation);
  }
  const tabs = Array.from(explorer.querySelectorAll('[role="tab"]'));
  const dashboard = explorer.closest(".ec");
  function activateTab(tab) {
    for (const item of tabs) {
      const active = item === tab;
      item.setAttribute("aria-selected", String(active));
      item.tabIndex = active ? 0 : -1;
      document.getElementById(item.getAttribute("aria-controls")).hidden = !active;
    }
    dashboard.classList.toggle("ec-expanded", tab.id !== "tab-gold");
  }
  for (const [index, tab] of tabs.entries()) {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", event => {
      const positions = {ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: tabs.length - 1};
      if (!(event.key in positions)) return;
      event.preventDefault();
      const next = tabs[(positions[event.key] + tabs.length) % tabs.length];
      activateTab(next);
      next.focus();
    });
  }
  for (const link of dashboard.querySelectorAll('a[href="#gold-questions"], a[href="#overview"]')) {
    link.addEventListener("click", () => activateTab(tabs[0]));
  }

  const select = explorer.querySelector("select");
  const source = document.getElementById("ec-source");

  // The matrix stores JSON arrays inside CSV cells, including escaped quotes and commas.
  function parseCSV(text) {
    const rows = [];
    let row = [], field = "", quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (c === '"') {
        if (quoted && text[i + 1] === '"') { field += '"'; i++; }
        else quoted = !quoted;
      } else if (!quoted && c === ",") { row.push(field); field = ""; }
      else if (!quoted && c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
      else if (quoted || c !== "\r") field += c;
    }
    if (field || row.length) { row.push(field); rows.push(row); }
    const headers = rows.shift();
    return rows.map(values => Object.fromEntries(headers.map((key,i) => [key,values[i]])));
  }

  const fields = {
    1: ["Patient classification"], 2: ["Service", "Visit type"], 3: ["Format", "Minutes"],
    4: ["Patient-indicated date"], 5: ["Slots considered", "Eligible slots"],
    6: ["Eligible", "Reasons"], 7: ["Earliest option", "Wait in days"],
    8: ["Preference overrides eligibility"], 9: ["Read only", "Appointment created"],
    10: ["Wait in days", "Standard in days", "Standard exceeded"],
    11: ["Review recommended", "Authorization status", "Authorization granted", "External scheduler invoked"],
    12: ["Outcome"], 13: ["Verified"], 14: ["Verified"], 15: ["Route"], 16: ["Route"]
  };
  function describe(id, cell) {
    const value = JSON.parse(cell);
    const values = Array.isArray(value) ? value : [value];
    return values.map((v, i) => {
      const readable = Array.isArray(v) ? v.join(", ").toLowerCase().replaceAll("_", " ")
        : typeof v === "boolean" ? (v ? "Yes" : "No") : String(v);
      return fields[id]?.[i] ? fields[id][i] + ": " + readable : readable;
    }).join("\n");
  }

  try {
    const response = await fetch(explorer.dataset.source);
    if (!response.ok) throw new Error("Matrix unavailable");
    const records = parseCSV((await response.text()).replace(/^\uFEFF/, ""));
    select.replaceChildren(...records.map(r => new Option(r["Gold question"], r.ID)));
    select.value = records.some(r => r.ID === "6") ? "6" : records[0].ID;
    function show() {
      const r = records.find(row => row.ID === select.value);
      document.getElementById("ec-expected").textContent = describe(r.ID, r.Expected);
      document.getElementById("ec-observed").textContent = describe(r.ID, r.Observed);
      const verdict = document.getElementById("ec-verdict");
      verdict.textContent = r.Result === "PASS" ? "Matched" : r.Result;
      verdict.dataset.matched = String(r.Result === "PASS");
      document.getElementById("ec-values").textContent = "Expected: " + r.Expected + " · Observed: " + r.Observed;
      if (r.ID === "6") {
        for (const [id, cell] of [["ec-expected", r.Expected], ["ec-observed", r.Observed]]) {
          const [eligible, reasons] = JSON.parse(cell);
          document.getElementById(id).textContent = (eligible ? "Eligible" : "Ineligible") + " with " + reasons.length + " mismatch reasons.";
        }
      }
      source.textContent = (r.Result === "PASS" ? "Matched" : r.Result) + " · Row " + r.ID + " · " + r["Fixture case"] + " · " + r["MCP tool"];
    }
    show();
    select.disabled = false;
    select.addEventListener("change", show);
  } catch {
    select.replaceChildren(new Option("Question matrix unavailable"));
    source.textContent = "Open the CSV below to inspect the original records.";
  }
})();
