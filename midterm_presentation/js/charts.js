(function () {
  const data = window.PresentationData;

  function formatNumber(value, suffix) {
    const rounded = Math.abs(value) >= 100 ? Math.round(value) : Number(value.toFixed(2));
    return `${rounded.toLocaleString("ko-KR")}${suffix || ""}`;
  }

  function scaledWidth(value, max, scale) {
    if (max <= 0) return 0;
    if (scale === "log") {
      return (Math.log10(value + 1) / Math.log10(max + 1)) * 100;
    }
    return (value / max) * 100;
  }

  function renderBarChart(el, config) {
    const rows = config.rows || [];
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
      fill.style.width = `${Math.max(scaledWidth(row.value, max, config.scale), row.value === 0 ? 0 : 3)}%`;
      fill.style.background = row.color || data.colors.select;
      track.appendChild(fill);

      const value = document.createElement("div");
      value.className = "bar-value";
      value.textContent = formatNumber(row.value, config.valueSuffix);

      item.append(label, track, value);
      chart.appendChild(item);
    });

    if (config.scale === "log") {
      const note = document.createElement("div");
      note.className = "chart-scale-note";
      note.textContent = "막대 길이는 log scale";
      chart.appendChild(note);
    }

    el.replaceChildren(chart);
  }

  function renderCharts() {
    document.querySelectorAll("[data-chart]").forEach((el) => {
      const key = el.getAttribute("data-chart");
      const config = data.charts[key];
      if (!config) {
        el.textContent = `Unknown chart: ${key}`;
        return;
      }
      renderBarChart(el, config);
    });
  }

  window.addEventListener("DOMContentLoaded", renderCharts);
})();
