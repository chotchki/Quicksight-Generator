// Phase T — graphviz WASM client-side renderer.
//
// The mkdocs-macros `diagram(...)` entry emits every diagram as:
//
//   <figure class="qs-diagram" data-zoomable="true" tabindex="0">
//     <template class="qs-graphviz-source">…DOT source…</template>
//   </figure>
//
// At page load this shim:
//   1. Finds every <template class="qs-graphviz-source"> block.
//   2. Loads @hpcc-js/wasm-graphviz from the vendored bundle at
//      ./wasm-graphviz/index.js (no CDN fetch; works offline /
//      from a flat file directory).
//   3. Runs `g.dot(source)` against each block's content.textContent.
//   4. Replaces the <template> with the rendered <svg> *inside the same
//      figure*, so qs-lightbox.js's click-to-zoom (which targets
//      `<figure class="qs-diagram">`) keeps working unchanged.
//
// Why <template> rather than <script type="text/x-graphviz">: Material's
// `navigation.instant` re-evaluates every <script> tag on cross-page
// navigation regardless of the type attribute, treating `digraph { ... }`
// as JavaScript and throwing "Unexpected token '{'". <template> content
// is inert by the HTML5 spec — never parsed as live DOM, never executed.
// Same `<` / `>` parsing safety as the script tag (browser doesn't
// HTML-process template contents either).

(async () => {
  const blocks = document.querySelectorAll(
    'template.qs-graphviz-source'
  );
  if (blocks.length === 0) return;

  let Graphviz;
  try {
    // @hpcc-js/wasm-graphviz v1.21.5 vendored at
    // ./wasm-graphviz/index.js (the upstream `dist/index.js` from
    // the npm tarball, with the WASM binary inlined as base64 —
    // single file, no separate .wasm download). Exports `Graphviz`
    // as a named export with a `.load()` static returning a
    // promise that resolves to a renderer instance.
    Graphviz = (await import(
      "./wasm-graphviz/index.js"
    )).Graphviz;
  } catch (err) {
    console.error("qs-graphviz-wasm: module load failed", err);
    return;
  }

  let renderer;
  try {
    renderer = await Graphviz.load();
  } catch (err) {
    console.error("qs-graphviz-wasm: WASM init failed", err);
    return;
  }

  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    // <template> exposes its inert content via .content (a
    // DocumentFragment); plain text inside lands as a text node.
    const source = block.content.textContent.trim();
    try {
      const svg = renderer.dot(source);
      // Insert the rendered SVG into the figure (or into the parent
      // node if the script is somehow not inside a figure — defensive).
      // The script element itself is removed once render succeeds so
      // we don't leave dead text in the DOM.
      const wrapper = document.createElement("div");
      wrapper.className = "qs-graphviz-wasm-rendered";
      wrapper.innerHTML = svg;
      block.parentNode.insertBefore(wrapper, block);
      block.remove();
    } catch (err) {
      console.error(`qs-graphviz-wasm: render failed for block ${i}`, err);
      const errWrapper = document.createElement("pre");
      errWrapper.className = "qs-graphviz-wasm-error";
      errWrapper.textContent =
        "graphviz render error: " + (err.message || err) + "\n\n" + source;
      block.parentNode.insertBefore(errWrapper, block);
      block.remove();
    }
  }
})();
