(function () {
  const visualSteps = {
    symbol: [
      ["Scan source", "AST parser reads functions and classes"],
      ["Create URI", "memory://symbol/path.py::qualname"],
      ["Filter", "question terms reduce candidates"],
      ["Select", "LLM chooses a compact URI"],
      ["Bundle", "primary symbol plus constants and helpers"],
      ["Answer", "small code evidence enters prompt"]
    ],
    self: [
      ["Base window", "4k context handles local tokens"],
      ["Overflow", "long input exceeds default slot"],
      ["Group", "G=2 or G=4 folds distant positions"],
      ["Accept", "reported context capacity grows"],
      ["Retrieve", "key facts still need verification"],
      ["Fallback", "use only after sanity checks"]
    ],
    runtime: [
      ["Producer", "tool creates large log, doc, or JSON"],
      ["Store", "RuntimeStore keeps raw value outside prompt"],
      ["Pointer", "runtime://kind/producer/id"],
      ["Resolve", "mirrored tool loads raw object"],
      ["Extract", "field, section, or log lines only"],
      ["Prompt", "small runtime evidence enters context"]
    ],
    source: [
      ["Source file", "large disk log, doc, or JSON"],
      ["Catalog", "source://kind/path with tools and hints"],
      ["Select tool", "LLM chooses extractor call"],
      ["Resolve", "manifest maps pointer to safe path"],
      ["Extract", "grep, section, or JSON path"],
      ["Prompt", "small source evidence enters context"]
    ]
  };

  function renderMiniVisual(root, type) {
    const steps = visualSteps[type] || visualSteps.symbol;
    root.innerHTML = `
      <div class="mini-visual-inner">
        ${steps
          .map(
            ([title, copy]) => `
              <article class="visual-step">
                <strong>${title}</strong>
                <span>${copy}</span>
              </article>`
          )
          .join("")}
      </div>
      <i class="moving-dot" aria-hidden="true"></i>`;
  }

  window.renderMiniVisualizers = function renderMiniVisualizers() {
    document.querySelectorAll("[data-mini-visual]").forEach((root) => {
      renderMiniVisual(root, root.getAttribute("data-mini-visual"));
    });
  };
})();
