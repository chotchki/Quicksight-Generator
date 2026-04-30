/*
 * QuickSight diagram lightbox — click-to-zoom for inline SVG diagrams.
 *
 * Targets <figure class="qs-diagram" data-zoomable="true"> wrappers
 * emitted by main.py::_wrap_svg. Off-the-shelf mkdocs lightbox plugins
 * (e.g. mkdocs-glightbox) only handle <img> tags; our diagrams render
 * inline so we ship a small vanilla-JS overlay instead. No third-party
 * dependency, no build step — just transform-driven pan + zoom.
 *
 * Behaviour:
 *   - Click (or press Enter/Space while focused) on a diagram → opens
 *     a fullscreen overlay containing a clone of the SVG.
 *   - Mouse wheel zooms about the cursor; +/- buttons step by 1.25x.
 *   - Drag to pan; "reset" centers + fits to viewport.
 *   - Esc, ×, or backdrop click closes the overlay.
 *   - Works in both `default` and `slate` (dark) Material color schemes
 *     — backdrop tint + button text follow the css var below.
 *
 * Wired in via mkdocs.yml's extra_javascript.
 */

(function () {
  "use strict";

  // Singleton overlay — created on first open, then reused.
  let overlay = null;
  let viewport = null;
  let svgHost = null;
  let state = null;

  const ZOOM_MIN = 0.2;
  const ZOOM_MAX = 20;
  const ZOOM_STEP = 1.25;

  function buildOverlay() {
    overlay = document.createElement("div");
    overlay.className = "qs-lightbox";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Diagram zoom view");
    overlay.hidden = true;

    const backdrop = document.createElement("div");
    backdrop.className = "qs-lightbox__backdrop";

    viewport = document.createElement("div");
    viewport.className = "qs-lightbox__viewport";

    svgHost = document.createElement("div");
    svgHost.className = "qs-lightbox__svg-host";
    viewport.appendChild(svgHost);

    const controls = document.createElement("div");
    controls.className = "qs-lightbox__controls";
    controls.appendChild(makeButton("−", "Zoom out", () => zoomBy(1 / ZOOM_STEP)));
    controls.appendChild(makeButton("Reset", "Reset zoom", fitToViewport));
    controls.appendChild(makeButton("+", "Zoom in", () => zoomBy(ZOOM_STEP)));
    controls.appendChild(makeButton("×", "Close", closeLightbox));

    overlay.appendChild(backdrop);
    overlay.appendChild(viewport);
    overlay.appendChild(controls);

    backdrop.addEventListener("click", closeLightbox);
    // Clicking empty space inside the viewport (e.g. around an SVG that
    // doesn't fill the aspect-ratio-matched box) also closes — but only
    // if the mouse hasn't moved (i.e. it's a click, not the tail of a
    // pan drag). Drag-initiated mouseups don't fire `click` if the
    // pointer travelled far enough, but short jitter would still fire,
    // so guard with a movement threshold.
    viewport.addEventListener("click", onViewportClick);
    viewport.addEventListener("wheel", onWheel, { passive: false });
    viewport.addEventListener("mousedown", onPanStart);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", () => {
      if (!overlay.hidden) fitToViewport();
    });

    document.body.appendChild(overlay);
  }

  function makeButton(label, title, handler) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "qs-lightbox__btn";
    b.textContent = label;
    b.title = title;
    b.setAttribute("aria-label", title);
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      handler();
    });
    return b;
  }

  function openLightbox(figure) {
    if (overlay === null) buildOverlay();
    const sourceSvg = figure.querySelector("svg");
    if (sourceSvg === null) return;

    // Clone so the in-page diagram stays put. Set width/height to 100%
    // so CSS sizing wins; preserveAspectRatio defaults to "xMidYMid
    // meet" which keeps the diagram fully visible inside the viewport.
    const clone = sourceSvg.cloneNode(true);
    clone.setAttribute("width", "100%");
    clone.setAttribute("height", "100%");
    clone.style.display = "block";

    svgHost.replaceChildren(clone);

    state = { scale: 1, tx: 0, ty: 0, dragging: false, lastX: 0, lastY: 0 };
    overlay.hidden = false;
    document.body.classList.add("qs-lightbox-open");
    fitToViewport();
  }

  function closeLightbox() {
    if (overlay === null) return;
    overlay.hidden = true;
    svgHost.replaceChildren();
    document.body.classList.remove("qs-lightbox-open");
  }

  function fitToViewport() {
    if (state === null) return;
    state.scale = 1;
    state.tx = 0;
    state.ty = 0;
    applyTransform();
  }

  function applyTransform() {
    svgHost.style.transform =
      "translate(" + state.tx + "px, " + state.ty + "px) scale(" + state.scale + ")";
  }

  function clampScale(next) {
    return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, next));
  }

  function zoomBy(factor) {
    if (state === null) return;
    // Zoom about the viewport center.
    const rect = viewport.getBoundingClientRect();
    zoomAtPoint(factor, rect.width / 2, rect.height / 2);
  }

  function zoomAtPoint(factor, viewportX, viewportY) {
    const next = clampScale(state.scale * factor);
    const realFactor = next / state.scale;
    // Keep the point under (viewportX, viewportY) stationary.
    state.tx = viewportX - (viewportX - state.tx) * realFactor;
    state.ty = viewportY - (viewportY - state.ty) * realFactor;
    state.scale = next;
    applyTransform();
  }

  function onWheel(e) {
    if (state === null) return;
    e.preventDefault();
    const rect = viewport.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
    zoomAtPoint(factor, x, y);
  }

  function onPanStart(e) {
    if (state === null) return;
    if (e.button !== 0) return;
    // Don't start a pan if the click landed on a control button.
    if (e.target.closest(".qs-lightbox__controls")) return;
    state.dragging = true;
    state.moved = false;
    state.startX = e.clientX;
    state.startY = e.clientY;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    viewport.classList.add("qs-lightbox__viewport--grabbing");
    document.addEventListener("mousemove", onPanMove);
    document.addEventListener("mouseup", onPanEnd);
    e.preventDefault();
  }

  function onPanMove(e) {
    if (state === null || !state.dragging) return;
    state.tx += e.clientX - state.lastX;
    state.ty += e.clientY - state.lastY;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    if (
      Math.abs(e.clientX - state.startX) > 3 ||
      Math.abs(e.clientY - state.startY) > 3
    ) {
      state.moved = true;
    }
    applyTransform();
  }

  function onPanEnd() {
    if (state === null) return;
    state.dragging = false;
    viewport.classList.remove("qs-lightbox__viewport--grabbing");
    document.removeEventListener("mousemove", onPanMove);
    document.removeEventListener("mouseup", onPanEnd);
  }

  function onViewportClick(e) {
    // The viewport sits on top of the backdrop and covers the whole
    // overlay. Treat a click here as "close" — UNLESS the click was
    // part of a pan (state.moved) or hit the controls bar.
    if (state === null) return;
    if (state.moved) {
      state.moved = false;
      return;
    }
    if (e.target.closest(".qs-lightbox__controls")) return;
    closeLightbox();
  }

  function onKeyDown(e) {
    if (overlay === null || overlay.hidden) return;
    if (e.key === "Escape") {
      closeLightbox();
    } else if (e.key === "+" || e.key === "=") {
      zoomBy(ZOOM_STEP);
    } else if (e.key === "-" || e.key === "_") {
      zoomBy(1 / ZOOM_STEP);
    } else if (e.key === "0") {
      fitToViewport();
    }
  }

  function bindFigures(root) {
    const figures = root.querySelectorAll(
      'figure.qs-diagram[data-zoomable="true"]'
    );
    figures.forEach((figure) => {
      if (figure.dataset.qsLightboxBound === "1") return;
      figure.dataset.qsLightboxBound = "1";
      figure.addEventListener("click", (e) => {
        // Avoid hijacking text-selection drags inside SVG labels.
        if (window.getSelection && window.getSelection().toString()) return;
        e.preventDefault();
        openLightbox(figure);
      });
      figure.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openLightbox(figure);
        }
      });
    });
  }

  // mkdocs-material's `navigation.instant` swaps page content without a
  // full reload. Re-bind whenever the document body subtree changes.
  function init() {
    bindFigures(document);
    if (window.document$ && typeof window.document$.subscribe === "function") {
      window.document$.subscribe(() => bindFigures(document));
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
