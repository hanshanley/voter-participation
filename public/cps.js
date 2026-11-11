(() => {
  const root = document.getElementById("participation-cps");
  if (!root) return;
  const select = document.getElementById("cps-dimension");
  const body = document.getElementById("cps-rows");
  const summary = document.getElementById("cps-summary");
  const error = document.getElementById("cps-error");
  const format = value => value.toLocaleString("en-US");
  const dataRoot = root.dataset.dataRoot || "data/";
  select.disabled = true;
  fetch(dataRoot + "cps/inputs.json")
    .then(response => {
      if (!response.ok) throw new Error("Survey input audit unavailable");
      return response.json();
    })
    .then(data => {
      const render = () => {
        body.replaceChildren();
        for (const row of data.marginals.filter(row => row.dimension === select.value)) {
          const tr = document.createElement("tr");
          const values = [row.year, row.group, format(row.sample_n),
            row.reported_voting_pct.toFixed(2) + "%", row.unknown_pct.toFixed(2) + "%"];
          values.forEach((value, index) => {
            const cell = document.createElement(index === 0 ? "th" : "td");
            if (index === 0) cell.scope = "row";
            if (index >= 2) cell.className = "numeric";
            cell.textContent = value;
            tr.append(cell);
          });
          body.append(tr);
        }
      };
      summary.textContent = `${format(data.summaries.reduce((n, row) => n + row.sample_n, 0))} `
        + `adult-citizen survey observations across ${data.years.join(" and ")}; `
        + `${data.comparisons.filter(row => row.passed).length} of ${data.comparisons.length} `
        + "published-rate checks passed. Historical inputs only, not a 2026 estimate.";
      select.disabled = false;
      select.addEventListener("change", render);
      render();
    })
    .catch(() => {
      error.hidden = false;
      error.textContent = body.children.length
        ? "Interactive input audit unavailable; the saved table and complete downloads remain available."
        : "Input audit unavailable here; use the complete downloadable observations.";
    });
})();
