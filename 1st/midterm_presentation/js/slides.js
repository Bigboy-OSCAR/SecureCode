(function () {
  const state = {
    index: 0,
    slides: []
  };

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function renderSlides() {
    const deck = document.getElementById("deck");
    deck.innerHTML = window.DeckData.slides
      .map((slide, index) => {
        const activeClass = index === 0 ? " is-active" : "";
        const customClass = slide.className ? ` ${slide.className}` : "";
        return `<section class="slide${customClass}${activeClass}" data-title="${slide.title}">${slide.html}</section>`;
      })
      .join("");
  }

  function updateSlide(nextIndex, pushHash = true) {
    state.index = clamp(nextIndex, 0, state.slides.length - 1);
    state.slides.forEach((slide, index) => {
      slide.classList.toggle("is-active", index === state.index);
    });

    const current = state.slides[state.index];
    const title = current.getAttribute("data-title") || "";
    document.getElementById("current-title").textContent = title;
    document.getElementById("slide-counter").textContent = `${state.index + 1} / ${state.slides.length}`;
    document.getElementById("progress-bar").style.width = `${((state.index + 1) / state.slides.length) * 100}%`;
    document.getElementById("prev-slide").disabled = state.index === 0;
    document.getElementById("next-slide").disabled = state.index === state.slides.length - 1;

    if (pushHash) {
      history.replaceState(null, "", `#${state.index + 1}`);
    }
  }

  function bindControls() {
    document.getElementById("prev-slide").addEventListener("click", () => updateSlide(state.index - 1));
    document.getElementById("next-slide").addEventListener("click", () => updateSlide(state.index + 1));

    window.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") {
        event.preventDefault();
        updateSlide(state.index + 1);
      }
      if (event.key === "ArrowLeft" || event.key === "PageUp") {
        event.preventDefault();
        updateSlide(state.index - 1);
      }
      if (event.key === "Home") updateSlide(0);
      if (event.key === "End") updateSlide(state.slides.length - 1);
    });
  }

  function init() {
    renderSlides();
    window.renderDeckCharts();
    window.renderMiniVisualizers();
    state.slides = Array.from(document.querySelectorAll(".slide"));
    const start = Number(window.location.hash.replace("#", "")) - 1;
    updateSlide(Number.isFinite(start) ? start : 0, false);
    bindControls();
  }

  window.addEventListener("DOMContentLoaded", init);
})();
