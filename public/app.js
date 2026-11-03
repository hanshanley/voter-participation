"use strict";

const $ = id => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const colors = ["#256e70", "#9d704b", "#7278a0", "#798e45", "#b36976", "#597e9a", "#8d795f", "#547556"];
const state = { view: "national", national: [], states: [], coverage: [], ncSummary: [], geometry: null, nc: new Map(), shapes: new Map(), table: [], columns: [], generation: 0 };
const fmt = value => value == null ? "—" : new Intl.NumberFormat("en-US").format(value);
const pct = value => value == null ? "No validated rate" : value.toFixed(1) + "%";
const electionType = year => year % 4 === 0 ? "presidential" : "midterm";
const selectedType = year => $("type").value === "all" || electionType(year) === $("type").value;
const unique = items => [...new Set(items)];
function node(tag, attrs = {}, text = "") {
  const element = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  if (text) element.textContent = text;
  return element;
}
async function get(path) {
  const response = await fetch("data/" + path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}
function options(element, items, preferred) {
  const previous = preferred ?? element.value;
  element.replaceChildren(...items.map(([value, label]) => {
    const option = document.createElement("option");
    option.value = value; option.textContent = label;
    return option;
  }));
  element.value = items.some(item => item[0] === previous) ? previous : items[0]?.[0] ?? "";
}
function notice(text) {
  $("notice").textContent = text;
  $("notice").hidden = !text;
}
function tooltip(event, text) {
  const box = $("tooltip");
  box.textContent = text;
  box.hidden = false;
  box.style.left = Math.max(8, Math.min(event.clientX + 16, innerWidth - 340)) + "px";
  box.style.top = Math.max(8, Math.min(event.clientY + 12, innerHeight - 170)) + "px";
}
function bindTooltip(element, text) {
  element.addEventListener("pointermove", event => tooltip(event, text));
  element.addEventListener("pointerleave", () => { $("tooltip").hidden = true; });
  element.addEventListener("focus", () => {
    const rect = element.getBoundingClientRect();
    tooltip({ clientX: rect.left, clientY: rect.top }, text);
  });
  element.addEventListener("blur", () => { $("tooltip").hidden = true; });
}
function configure() {
  const precincts = state.view === "precincts";
  $("basis-label").hidden = precincts || state.view === "coverage";
  $("dimension-label").hidden = ["states", "coverage"].includes(state.view);
  $("group-label").hidden = ["states", "coverage"].includes(state.view);
  $("minimum-label").hidden = !precincts;
  let years = unique(state.national.map(row => row.year));
  if (precincts) years = state.ncSummary.filter(row => row.status === "aggregated").map(row => row.year);
  if (state.view === "coverage") years = unique(state.coverage.map(row => row.year));
  options($("year"), years.filter(selectedType).sort((a, b) => b - a).map(year => [String(year), `${year} · ${electionType(year)}`]));
  const dimensions = precincts
    ? [["overall", "All registered voters"], ["race", "Race"], ["ethnicity", "Ethnicity"], ["sex", "Sex"], ["age", "Age"]]
    : [["overall", "Overall"], ["race", "Race / ethnicity"], ["age", "Age"], ["sex", "Sex"], ["education", "Education"]];
  options($("dimension"), dimensions);
  configureGroups();
}
function configureGroups() {
  const dimension = $("dimension").value;
  const basis = $("basis").value;
  let groups = ["All groups"];
  if (state.view === "precincts") {
    const summary = state.ncSummary.find(row => row.year === Number($("year").value));
    groups.push(...unique((summary?.statewide ?? []).filter(row => row.dimension === dimension).map(row => row.group)));
  } else {
    const rows = state.national.filter(row => row.denominator === basis);
    groups.push(...unique(rows.filter(row => dimension === "age"
      ? row.dimension === "overall" && row.age_group !== "All ages"
      : row.dimension === dimension && row.age_group === "All ages")
      .map(row => dimension === "age" ? row.age_group : row.group)));
  }
  if (state.view === "precincts") groups = groups.filter(group => group !== "All groups");
  options($("group"), groups.map(group => [group, group]));
}
function setTable(rows, columns) {
  state.table = rows; state.columns = columns;
  renderTable();
}
function renderTable() {
  const search = $("search").value.toLowerCase();
  const rows = state.table.filter(row => JSON.stringify(row).toLowerCase().includes(search));
  const tr = document.createElement("tr");
  for (const [, label] of state.columns) {
    const th = document.createElement("th"); th.textContent = label; tr.append(th);
  }
  $("table-head").replaceChildren(tr);
  $("table-body").replaceChildren(...rows.slice(0, 150).map(row => {
    const element = document.createElement("tr");
    for (const [key] of state.columns) {
      const td = document.createElement("td");
      const value = row[key];
      td.textContent = key === "turnout_pct" ? pct(value) : Array.isArray(value) ? value.join("; ") || "OK" : value == null ? "—" : String(value);
      if (typeof value === "number") td.className = "numeric";
      element.append(td);
    }
    return element;
  }));
  $("table-note").textContent = `${fmt(rows.length)} observations match; showing ${Math.min(rows.length, 150)}. Downloads contain every observation, including flagged and unmatched records.`;
}
function svg(width = 1100, height = 540) {
  const chart = node("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": $("title").textContent });
  $("visualization").replaceChildren(chart);
  return chart;
}
function legend(items) {
  const wrapper = document.createElement("div"); wrapper.className = "legend";
  items.forEach(([label, color]) => {
    const span = document.createElement("span");
    const swatch = document.createElement("i"); swatch.className = "swatch"; swatch.style.setProperty("--color", color);
    span.append(swatch, document.createTextNode(label)); wrapper.append(span);
  });
  $("key").replaceChildren(wrapper);
}
function color(value) {
  if (value == null) return "#e5e7e2";
  const t = Math.max(0, Math.min(1, (value - 20) / 65));
  const start = [237, 243, 239], end = [26, 104, 110];
  return `rgb(${start.map((channel, i) => Math.round(channel + t * (end[i] - channel))).join(",")})`;
}
function ramp() {
  $("key").innerHTML = '<div class="legend"><span>20%</span><i class="ramp"></i><span>85%+</span><span><i class="swatch" style="--color:#e5e7e2"></i>No validated rate</span></div>';
}
function nationalView() {
  const dimension = $("dimension").value, basis = $("basis").value, group = $("group").value;
  let rows = state.national.filter(row => row.denominator === basis && selectedType(row.year)
    && (dimension === "age" ? row.dimension === "overall" && row.age_group !== "All ages"
      : row.dimension === dimension && row.age_group === "All ages"))
    .map(row => ({ ...row, series: dimension === "age" ? row.age_group : row.group }));
  if (group !== "All groups") rows = rows.filter(row => row.series === group);
  $("subtitle").textContent = "United States · Census Current Population Survey";
  $("title").textContent = "Participation across elections";
  $("measure").textContent = `Percent of ${basis === "cvap" ? "adult citizens" : "all adult residents, including noncitizens"} who reported voting. Presidential and midterm observations are explicitly labeled.`;
  $("caption").textContent = "Circles: presidential elections. Squares: midterms. Lines connect elections of the same type only; gaps are not interpolated. The vertical line marks the selected year.";
  if (!rows.length) {
    notice("This demographic series is not available for the selected population denominator.");
    $("visualization").innerHTML = '<p class="empty">No comparable series for this denominator.</p>';
    setTable([], [["year", "Election"], ["series", "Group"], ["turnout_pct", "Turnout"]]);
    return;
  }
  const issues = unique(rows.flatMap(row => row.warnings));
  if (!rows.some(row => row.year === Number($("year").value)))
    issues.unshift("This demographic series is not available for the selected year and population denominator; available years remain shown.");
  notice(issues.join(" "));
  const chart = svg(1100, 480), x = year => 60 + (year - 1964) / 60 * 1010, y = rate => 410 - rate * 3.6;
  for (let tick = 0; tick <= 100; tick += 20) {
    chart.append(node("line", { x1: 60, x2: 1070, y1: y(tick), y2: y(tick), class: "chart-grid" }));
    chart.append(node("text", { x: 45, y: y(tick) + 4, "text-anchor": "end", class: "axis-label" }, tick + "%"));
  }
  for (let year = 1964; year <= 2024; year += 8)
    chart.append(node("text", { x: x(year), y: 440, "text-anchor": "middle", class: "axis-label" }, String(year)));
  chart.append(node("line", { x1: x(Number($("year").value)), x2: x(Number($("year").value)), y1: 45, y2: 410, stroke: "#9da8a0", "stroke-dasharray": "3 4" }));
  const series = unique(rows.map(row => row.series));
  legend(series.map((label, index) => [label, colors[index % colors.length]]));
  series.forEach((name, index) => {
    const c = colors[index % colors.length];
    for (const type of ["presidential", "midterm"]) {
      const observations = rows.filter(row => row.series === name && row.election_type === type).sort((a, b) => a.year - b.year);
      let segment = [];
      const flush = () => {
        if (segment.length > 1) chart.append(node("path", { d: segment.map((r, i) => `${i ? "L" : "M"}${x(r.year)},${y(r.turnout_pct)}`).join(" "), class: "chart-line", stroke: c, "stroke-dasharray": type === "midterm" ? "4 3" : "" }));
        segment = [];
      };
      for (const row of observations) {
        if (segment.length && row.year - segment[segment.length - 1].year !== 4) flush();
        if (segment.length && ((dimension === "race" && segment[segment.length - 1].year < 2004 && row.year >= 2004)
          || (basis === "cvap" && segment[segment.length - 1].year < 1996 && row.year >= 1996)
          || (dimension === "education" && segment[segment.length - 1].year < 1992 && row.year >= 1992)
          || (segment[segment.length - 1].year < 1972 && row.year >= 1972))) flush();
        segment.push(row);
      }
      flush();
      for (const row of observations) {
        const point = type === "presidential"
          ? node("circle", { cx: x(row.year), cy: y(row.turnout_pct), r: 4, fill: c, class: "chart-point", tabindex: 0 })
          : node("rect", { x: x(row.year) - 3.5, y: y(row.turnout_pct) - 3.5, width: 7, height: 7, fill: c, class: "chart-point", tabindex: 0 });
        bindTooltip(point, `${row.year} ${type} · ${name}: ${pct(row.turnout_pct)}. ${row.warnings.join(" ")}`);
        chart.append(point);
      }
    }
  });
  setTable(rows.sort((a, b) => b.year - a.year), [["year", "Year"], ["election_type", "Election"], ["series", "Group"], ["turnout_pct", "Turnout"], ["denominator", "Denominator"], ["warnings", "Comparability notes"]]);
}
function coordinateRings(geometry) {
  return geometry.type === "MultiPolygon" ? geometry.coordinates.flat() : geometry.coordinates;
}
function mapPaths(features, projection, bounds, region) {
  const [left, top, width, height] = region;
  const points = bounds ?? features.flatMap(feature => coordinateRings(feature.geometry).flat().map(projection));
  const [xmin, xmax, ymin, ymax] = points.reduce(
    ([x0, x1, y0, y1], [x, y]) => [Math.min(x0, x), Math.max(x1, x), Math.min(y0, y), Math.max(y1, y)],
    [Infinity, -Infinity, Infinity, -Infinity]);
  const scale = Math.min(width / (xmax - xmin), height / (ymax - ymin));
  const ox = left + (width - (xmax - xmin) * scale) / 2, oy = top + (height - (ymax - ymin) * scale) / 2;
  return features.map(feature => ({
    feature,
    d: coordinateRings(feature.geometry).map(ring => ring.map((point, index) => {
      const [x, y] = projection(point);
      return `${index ? "L" : "M"}${(ox + (x - xmin) * scale).toFixed(2)},${(oy + (y - ymin) * scale).toFixed(2)}`;
    }).join("") + "Z").join(""),
  }));
}
function albers([longitude, latitude]) {
  const radians = Math.PI / 180, p1 = 29.5 * radians, p2 = 45.5 * radians;
  const n = (Math.sin(p1) + Math.sin(p2)) / 2, c = Math.cos(p1) ** 2 + 2 * n * Math.sin(p1);
  const rho = Math.sqrt(c - 2 * n * Math.sin(latitude * radians)) / n;
  const theta = n * (longitude + 96) * radians;
  return [rho * Math.sin(theta), -rho * Math.cos(theta)];
}
function nationalMap(features, rateFor, textFor) {
  const chart = svg();
  for (const [codes, projection, region] of [
    [null, albers, [20, 10, 1060, 465]],
    [["AK"], ([lon, lat]) => [lon > 0 ? lon - 360 : lon, -lat], [45, 390, 180, 125]],
    [["HI"], ([lon, lat]) => [lon, -lat], [250, 425, 135, 80]],
  ]) {
    const subset = features.filter(f => codes ? codes.includes(f.properties.STUSAB) : !["AK", "HI", "PR", "GU", "VI", "MP", "AS"].includes(f.properties.STUSAB));
    for (const { feature, d } of mapPaths(subset, projection, null, region)) {
      const path = node("path", { d, fill: color(rateFor(feature)), class: "map-feature", "fill-rule": "evenodd", tabindex: 0 });
      bindTooltip(path, textFor(feature));
      chart.append(path);
    }
  }
}
function statesView() {
  const year = Number($("year").value), basis = $("basis").value;
  const rows = state.states.filter(row => row.year === year && row.denominator === basis);
  const byName = new Map(rows.map(row => [row.state, row]));
  $("subtitle").textContent = "State-level estimates · not precinct-level data";
  $("title").textContent = `${year} ${electionType(year)} participation`;
  $("measure").textContent = `CPS survey-reported turnout among ${basis === "cvap" ? "adult citizens" : "all adult residents"}. All 50 states and D.C. are shown; gray means no estimate.`;
  $("caption").textContent = "State shapes are a display basemap, not historical precinct boundaries. Sampling uncertainty can be substantial; this map is not a ranking of statistically significant differences.";
  notice(unique(rows.flatMap(row => row.warnings)).join(" ") || (!rows.length ? "No state estimates for this year and denominator in the downloaded historical tables." : ""));
  ramp();
  nationalMap(state.geometry.features, f => byName.get(f.properties.NAME)?.turnout_pct,
    f => `${f.properties.NAME} · ${year}: ${pct(byName.get(f.properties.NAME)?.turnout_pct)}`);
  setTable(rows.sort((a, b) => a.state.localeCompare(b.state)), [["state", "State"], ["year", "Year"], ["turnout_pct", "Turnout"], ["denominator", "Denominator"], ["warnings", "Comparability notes"]]);
}
async function precinctsView(generation) {
  const year = Number($("year").value);
  $("visualization").innerHTML = '<p class="empty">Loading historical precinct observations…</p>';
  $("title").textContent = `${year} precinct participation`;
  $("subtitle").textContent = "North Carolina · administrative voter-history pilot";
  setTable([], []);
  if (!state.nc.has(year)) state.nc.set(year, await get(`nc/${year}.json`));
  if (generation !== state.generation) return;
  const data = state.nc.get(year), dimension = $("dimension").value, group = $("group").value;
  const audit = state.geometryAudit.find(row => row.year === year);
  const rows = data.records.filter(row => row.dimension === dimension && row.group === group);
  const keyed = new Map(rows.map(row => [`${row.county}|${row.precinct}`, row]));
  const minimum = Number($("minimum").value);
  $("subtitle").textContent = "North Carolina · administrative voter-history pilot";
  $("title").textContent = `${year} participation · ${group}`;
  $("measure").textContent = "Participants recorded in NC voter history ÷ election-time registered voters (active + inactive). This is not a share of all adult citizens and is not a national precinct dataset.";
  $("nc-download").href = `data/nc/${year}.csv`;
  $("nc-download").textContent = `NC ${year} complete observations (CSV)`;
  $("caption").textContent = "Gray: missing or flagged rate, unmatched geography, or registration count below the selected minimum. Unmatched counts remain in the downloads. Precinct IDs are not comparable over time without a boundary crosswalk.";
  ramp();
  if (!audit) {
    notice("Participation counts are available, but no election-year precinct boundary snapshot has been validated for this year. We do not substitute a different year's map.");
    $("visualization").innerHTML = '<p class="empty">Historical precinct counts available below; election-year geometry not validated.</p>';
  } else {
    if (!state.shapes.has(year)) state.shapes.set(year, await get(`nc/geometry-${year}.geojson`));
    if (generation !== state.generation) return;
    notice(`${audit.participant_match_pct.toFixed(1)}% of all recorded participants join to this boundary snapshot by county + precinct ID. ${audit.vintage}. ID matching is not independent certification of election-day boundaries. Rates with inconsistent counts are withheld, not clipped.`);
    const chart = svg(1100, 440);
    for (const { feature, d } of mapPaths(state.shapes.get(year).features, albers, null, [10, 10, 1080, 420])) {
      const p = feature.properties, row = keyed.get(`${p.county}|${p.precinct}`);
      const value = row && row.registered >= minimum ? row.turnout_pct : null;
      const path = node("path", { d, fill: color(value), class: "map-feature", "fill-rule": "evenodd" });
      bindTooltip(path, `${p.county} · ${p.precinct} · ${group}: ${pct(value)}. Participants: ${fmt(row?.participants)}; registered: ${fmt(row?.registered)}. ${row?.quality.join("; ") ?? "No matching observation"}`);
      chart.append(path);
    }
  }
  setTable(rows, [["county", "County"], ["precinct", "Precinct"], ["group", "Group"], ["participants", "Participants"], ["registered", "Registered"], ["turnout_pct", "Participation"], ["quality", "Quality flags"]]);
}
function coverageView() {
  const year = Number($("year").value);
  const rows = state.coverage.filter(row => row.year === year);
  const keyed = new Map(rows.map(row => [row.state, row]));
  $("subtitle").textContent = "Nationwide scope · explicit data gaps";
  $("title").textContent = `${year} precinct coverage audit`;
  $("measure").textContent = "A research coverage map, not turnout. 'Not assessed' means the precinct numerator, denominator, and historical geometry have not yet been verified.";
  notice("Only North Carolina currently has ingested administrative precinct data. Other states are not assessed, not declared unavailable. State-level CPS estimates do not fill precinct gaps.");
  $("caption").textContent = "Teal: NC aggregate precinct counts ingested. Gray: not assessed. See the table for boundary snapshots and match rates. Education is absent from NC's registration/history demographics.";
  legend([["Precinct counts ingested", "#256e70"], ["Not assessed", "#e5e7e2"]]);
  nationalMap(state.geometry.features, f => keyed.get(f.properties.NAME)?.precinct_counts === "downloaded_and_aggregated" ? 85 : null,
    f => `${f.properties.NAME}: ${keyed.get(f.properties.NAME)?.precinct_counts ?? "not_assessed"}`);
  setTable(rows, [["state", "State"], ["year", "Year"], ["precinct_counts", "Precinct counts"], ["demographic_participation", "Demographics"], ["geometry", "Boundary vintage"], ["participant_geometry_match_pct", "Participants joined (%)"]]);
}
async function render() {
  const generation = ++state.generation;
  $("tooltip").hidden = true;
  notice("");
  try {
    if (state.view === "national") nationalView();
    if (state.view === "states") statesView();
    if (state.view === "precincts") await precinctsView(generation);
    if (state.view === "coverage") coverageView();
  } catch (error) {
    if (generation !== state.generation) return;
    notice(`Data could not be loaded: ${error.message}. Run the data pipeline and serve this directory over local HTTP.`);
    $("visualization").innerHTML = '<p class="empty">Data unavailable; no values have been inferred.</p>';
  }
}
async function main() {
  const [national, states, geometry, coverage, ncSummary, geometryAudit, methods] = await Promise.all([
    get("national.json"), get("states.json"), get("states.geojson"), get("coverage.json"),
    get("nc/summary.json"), get("geometry-audit.json"), get("methodology.json"),
  ]);
  Object.assign(state, { national, states, geometry, coverage, ncSummary, geometryAudit });
  const list = document.createElement("ul");
  for (const text of methods.limitations) { const li = document.createElement("li"); li.textContent = text; list.append(li); }
  $("methods").append(list);
  document.querySelectorAll("nav button").forEach(button => button.addEventListener("click", () => {
    state.view = button.dataset.view;
    document.querySelectorAll("nav button").forEach(b => b.classList.toggle("active", b === button));
    $("search").value = "";
    configure(); render();
  }));
  $("type").addEventListener("change", () => { configure(); render(); });
  $("basis").addEventListener("change", () => { configureGroups(); render(); });
  $("dimension").addEventListener("change", () => { configureGroups(); render(); });
  $("year").addEventListener("change", () => { configureGroups(); render(); });
  $("group").addEventListener("change", render);
  $("minimum").addEventListener("change", render);
  $("search").addEventListener("input", renderTable);
  configure(); await render();
}
main().catch(error => notice(`Cannot initialize: ${error.message}. Build the data first and use a local HTTP server.`));
