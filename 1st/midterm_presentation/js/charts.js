(function () {
  function formatValue(value, unit) {
    const rounded = Math.abs(value) >= 100 ? Math.round(value) : Number(value.toFixed(2));
    return `${rounded.toLocaleString("en-US")}${unit || ""}`;
  }

  function getRows(config) {
    const rows = [...(config.rows || [])];
    if (config.sort === "desc") return rows.sort((a, b) => b.value - a.value);
    if (config.sort === "asc") return rows.sort((a, b) => a.value - b.value);
    return rows;
  }

  function scaledWidth(value, max, scale) {
    if (value <= 0 || max <= 0) return 0;
    if (scale === "log") {
      return (Math.log10(value + 1) / Math.log10(max + 1)) * 100;
    }
    return (value / max) * 100;
  }

  function renderBarChart(root, config) {
    const rows = getRows(config);
    const max = Math.max(...rows.map((row) => row.value), 1);
    const chart = document.createElement("div");
    chart.className = "bar-chart";

    rows.forEach((row) => {
      const item = document.createElement("div");
      item.className = "bar-row";

      const label = document.createElement("div");
      label.className = "bar-label";
      label.textContent = row.label;

      const track = document.createElement("div");
      track.className = "bar-track";

      const fill = document.createElement("div");
      fill.className = "bar-fill";
      const width = scaledWidth(row.value, max, config.scale);
      fill.style.width = `${Math.max(width, row.value > 0 ? 2.5 : 0)}%`;
      fill.style.background = row.color || "#1f6feb";
      track.appendChild(fill);

      const value = document.createElement("div");
      value.className = "bar-value";
      value.textContent = formatValue(row.value, config.unit);

      item.append(label, track, value);
      chart.appendChild(item);
    });

    if (config.note) {
      const note = document.createElement("div");
      note.className = "chart-note";
      note.textContent = config.note;
      chart.appendChild(note);
    }

    root.replaceChildren(chart);
  }

  window.renderDeckCharts = function renderDeckCharts() {
    const charts = window.DeckData.charts;
    document.querySelectorAll("[data-chart]").forEach((root) => {
      const key = root.getAttribute("data-chart");
      const config = charts[key];
      if (!config) {
        root.textContent = `Missing chart: ${key}`;
        return;
      }
      renderBarChart(root, config);
    });
  };
})();
