(() => {
  const root = document.getElementById("nationwide-participation");
  if (!root) return;
  const element = name => root.querySelector("#national-current-" + name);
  const number = value => value == null ? "Not reported" : value.toLocaleString("en-US");
  const labels = { race: "Race", ethnicity: "Ethnicity", gender: "Gender (source labels)", age_range: "Age" };
  const modes = { in_person_early: "in-person early voting", mail_returned: "returned mail ballots" };
  const kinds = { in_person_early: "inperson", mail_returned: "returned" };
  const time = value => new Date(value).toLocaleString("en-US", {
    timeZone: "America/New_York", dateStyle: "medium", timeStyle: "short",
  }) + " Eastern";
  const options = (select, items, selected) => {
    select.replaceChildren(...items.map(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      return option;
    }));
    if (items.some(([value]) => value === selected)) select.value = selected;
  };
  async function load(path) {
    const response = await fetch(root.dataset.dataRoot + path);
    if (!response.ok) throw new Error("Saved nationwide data could not be loaded.");
    return response.json();
  }
  async function start() {
    const latest = await load("nationwide/latest.json");
    const directory = "nationwide/" + latest.snapshot_id + "/";
    const snapshot = await load(directory + "snapshot.json");
    root.hidden = false;
    element("asof").textContent = "Saved nationwide capture: " + time(snapshot.retrieved_at)
      + ". Source data dates differ and are shown separately; not a live feed.";
    element("summary").textContent = snapshot.audit.jurisdictions_with_data
      + " jurisdictions with data; " + snapshot.audit.jurisdictions_with_demographic_counts
      + " states with nonzero demographic counts; " + snapshot.audit.jurisdictions_with_official_ballots
      + " official administrative ballot feeds. All 50 states and DC assessed.";
    for (const [id, file] of Object.entries({
      complete: "complete-snapshot.zip", demographics: "demographics.csv",
      early: "early_voting.csv", reporting: "reporting.csv", coverage: "coverage.csv",
    })) element(id).href = root.dataset.dataRoot + directory + file;
    options(element("state"), snapshot.coverage.map(row => [row.state_code, row.state]), "GA");
    function render() {
      const state = element("state").value, mode = element("mode").value;
      const coverage = snapshot.coverage.find(row => row.state_code === state);
      const total = snapshot.early_voting.find(row =>
        row.state_code === state && row.mode === mode && row.geography_level === "state");
      const groups = snapshot.demographics.filter(row => row.state_code === state
        && row.mode === mode && row.demographic_source_total > 0);
      const dimensions = [...new Set(groups.map(row => row.dimension))];
      options(element("dimension"), dimensions.length
        ? dimensions.map(value => [value, labels[value]]) : [["", "Not reported for this selection"]],
      element("dimension").value || "race");
      element("dimension").disabled = dimensions.length === 0;
      const selected = groups.filter(row => row.dimension === element("dimension").value)
        .sort((a, b) => b.ballots - a.ballots);
      element("selection").textContent = coverage.state + " · " + modes[mode];
      element("total").textContent = "Reported " + modes[mode] + ": " + number(total?.ballots)
        + (total ? ". Source data date: " + total.source_date + "." : ".");
      const source = snapshot.datasets[state + "-" + kinds[mode]];
      element("mode-note").textContent = source?.status === "retained_after_failure"
        ? "Source refresh failed; retained data from " + time(source.source.retrieved_at) + ". " + source.error
        : "These counts do not cover the full election and are not turnout rates."
          + (total?.quality.length ? " Source caveats: " + total.quality.join("; ").replaceAll("_", " ") + "." : "");
      const official = snapshot.reporting.find(row => row.state_code === state);
      element("official").textContent = official
        ? "Official administrative ballots reported: " + number(official.ballots)
          + ". Source update: " + official.source_update_label + ". Denominator basis: "
          + official.denominator_basis.replaceAll("_", " ")
          + (official.denominator == null ? " (exact denominator not supplied)." : ": " + number(official.denominator) + ".")
          + (official.status === "retained_after_failure" ? " Retained from an earlier capture after source failure." : "")
        : "Official full-election ballots have not been ingested for this state. Missing is not zero turnout.";
      const maximum = Math.max(1, ...selected.map(row => row.ballots));
      element("chart").replaceChildren(...selected.map(row => {
        const item = document.createElement("li"), label = document.createElement("span");
        const value = document.createElement("strong"), bar = document.createElement("i");
        label.textContent = row.group;
        value.textContent = number(row.ballots);
        bar.style.width = 100 * row.ballots / maximum + "%";
        bar.setAttribute("aria-hidden", "true");
        item.append(label, value, bar);
        return item;
      }));
      element("group-note").textContent = selected.length
        ? "Demographic source date: " + selected[0].source_date + ". "
          + number(selected[0].demographic_source_total) + " voters represented in this breakdown. "
          + (selected[0].quality.length ? "Source caveats: " + selected[0].quality.join("; ").replaceAll("_", " ") + ". " : "")
          + (selected.some(row => row.status === "retained_after_failure") ? "Retained from an earlier capture after a source failure. " : "")
          + "Counts, not group turnout rates; group definitions differ by state."
        : "No nonzero, dated demographic breakdown is reported by the assessed source for this selection. "
          + "This is not evidence that no members of a group voted.";
    }
    for (const id of ["state", "mode", "dimension"]) element(id).addEventListener("change", render);
    render();
  }
  start().catch(error => {
    element("error").textContent = error.message + " Saved tables and downloads remain available.";
    element("error").hidden = false;
  });
})();
