(() => {
  const root = document.getElementById("participation-model");
  if (!root) return;
  const select = root.querySelector("#model-dimension");
  const labels = { age: "Age", race: "Race / ethnicity", sex: "Sex", education: "Education" };
  const average = (rows, field) => rows.reduce((sum, row) => sum + row[field], 0) / rows.length;
  async function load() {
    try {
      const response = await fetch((root.dataset.dataRoot || "data/") + "model/validation.json");
      if (!response.ok) throw new Error("Independent-model validation unavailable");
      const result = await response.json();
      const format = value => value.toFixed(2);
      function render() {
        const rows = result.predictions.filter(row => select.value === "all" || row.dimension === select.value);
        root.querySelector("#model-summary").textContent =
          rows.length + " historical tests · " + (labels[select.value] || "All categories")
          + ". Candidate mean absolute error: " + format(average(rows, "absolute_error_pp"))
          + " pp; carry-forward: " + format(average(rows, "baseline_absolute_error_pp")) + " pp. Lower is better.";
        const body = root.querySelector("#model-rows");
        body.replaceChildren();
        for (const year of [...new Set(rows.map(row => row.year))].sort()) {
          const tests = rows.filter(row => row.year === year);
          const tr = document.createElement("tr");
          const values = [String(year), tests[0].election_type, String(tests.length),
            format(average(tests, "absolute_error_pp")), format(average(tests, "baseline_absolute_error_pp"))];
          values.forEach((value, index) => {
            const cell = document.createElement(index === 0 ? "th" : "td");
            if (index === 0) cell.scope = "row";
            if (index > 1) cell.className = "numeric";
            cell.textContent = value;
            tr.append(cell);
          });
          body.append(tr);
        }
      }
      select.addEventListener("change", render);
      select.disabled = false;
      render();
    } catch (error) {
      const status = root.querySelector("#model-error");
      status.textContent = error.message + (root.querySelector("#model-rows").children.length
        ? ". The saved validation table and complete downloads remain available."
        : ". Use the complete downloads below.");
      status.hidden = false;
    }
  }
  load();
})();
