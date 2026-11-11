(() => {
  "use strict";
  const root = document.getElementById("current-participation");
  if (!root) return;
  const $ = id => document.getElementById("nc-current-" + id);
  const number = value => new Intl.NumberFormat("en-US").format(value);
  const date = value => new Date(value).toLocaleString("en-US", {
    timeZone: "America/New_York", month: "long", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  });
  async function get(path) {
    const response = await fetch((root.dataset.dataRoot || "data/") + path);
    if (!response.ok) throw new Error(`Current snapshot: HTTP ${response.status}`);
    return response.json();
  }
  function options(element, values, label) {
    element.replaceChildren(...values.map(value => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label(value);
      return option;
    }));
  }
  async function main() {
    const latest = await get("current/latest.json");
    const directory = "current/" + latest.snapshot_id + "/";
    const snapshot = await get(directory + "snapshot.json");
    const counties = snapshot.reporting.map(row => row.county)
      .sort((a, b) => a === "STATEWIDE" ? -1 : b === "STATEWIDE" ? 1 : a.localeCompare(b));
    options($("county"), counties, value => value === "STATEWIDE" ? "North Carolina statewide" : value);
    const methods = ["All methods", ...new Set(snapshot.demographics.map(row => row.request_type)
      .filter(value => value !== "All methods"))];
    options($("method"), methods, value => value === "All methods" ? "All request types" : value);
    $("asof").textContent = "Saved snapshot retrieved " + date(snapshot.retrieved_at) + ". Not a live feed.";
    const source = name => snapshot.sources.find(row => row.file === name);
    $("reporting-time").textContent = "Election-night file updated "
      + date(source("reporting.json").last_modified) + ".";
    $("absentee-time").textContent = "Demographic file updated "
      + date(source("absentee-state.csv").last_modified)
      + "; it does not cover Election Day in-person voting.";
    for (const [id, file] of [["complete", "complete-snapshot.zip"],
      ["demographics", "demographics.csv"], ["reporting-download", "reporting.csv"]]) {
      $(id).href = (root.dataset.dataRoot || "data/") + directory + file;
    }
    function render() {
      const county = $("county").value;
      const report = snapshot.reporting.find(row => row.county === county);
      const unreported = report.quality.includes("no_ballots_reported_yet");
      $("ballots").textContent = unreported ? "Not reported" : number(report.ballots_cast);
      $("fraction").textContent = report.reported_ballot_fraction_pct == null
        ? "No validated fraction" : report.reported_ballot_fraction_pct.toFixed(2) + "%";
      $("precincts").textContent = number(report.precincts_reporting) + " / " + number(report.precincts_total);
      const rows = snapshot.demographics.filter(row => row.county === county
        && row.dimension === $("dimension").value && row.request_type === $("method").value)
        .sort((a, b) => b.ballots - a.ballots || a.group.localeCompare(b.group));
      const maximum = Math.max(1, ...rows.map(row => row.ballots));
      $("chart").replaceChildren(...rows.map(row => {
        const li = document.createElement("li"), label = document.createElement("span");
        const count = document.createElement("strong"), bar = document.createElement("i");
        label.textContent = row.group;
        count.textContent = number(row.ballots);
        bar.setAttribute("aria-hidden", "true");
        bar.style.width = 100 * row.ballots / maximum + "%";
        li.append(label, count, bar);
        return li;
      }));
      $("group-note").textContent = number(rows.reduce((total, row) => total + row.ballots, 0))
        + " reported absentee/early-voting ballots in this selection. Counts, not demographic turnout rates.";
      $("county-note").textContent = "Reporting geography: "
        + (county === "STATEWIDE" ? "North Carolina" : county)
        + ". Source update label: " + report.source_update_label
        + ". Registered-voter denominator: " + number(report.registered_voters) + ".";
    }
    for (const id of ["county", "dimension", "method"]) $(id).addEventListener("change", render);
    render();
    root.hidden = false;
  }
  main().catch(error => {
    $("error").textContent = "The saved current snapshot could not load. "
      + "Any static snapshot below and historical downloads remain available. " + error.message;
    $("error").hidden = false;
    root.hidden = false;
  });
})();
