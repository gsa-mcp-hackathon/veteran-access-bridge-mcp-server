(async function () {
  const explorer = document.querySelector(".ec-explorer");
  if (!explorer) return;
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
