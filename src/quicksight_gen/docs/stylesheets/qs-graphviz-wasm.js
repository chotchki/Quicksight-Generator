// Phase T — graphviz WASM client-side renderer.
//
// The mkdocs-macros `diagram(...)` entry emits every diagram as:
//
//   <figure class="qs-diagram" data-zoomable="true" tabindex="0">
//     <script type="text/x-graphviz">…DOT source…</script>
//   </figure>
//
// At page load this shim:
//   1. Finds every <script type="text/x-graphviz"> block.
//   2. Loads @hpcc-js/wasm-graphviz from jsDelivr (cached after first
//      hit by the browser).
//   3. Runs `g.dot(source)` against each block's textContent.
//   4. Replaces the <script> with the rendered <svg> *inside the same
//      figure*, so qs-lightbox.js's click-to-zoom (which targets
//      `<figure class="qs-diagram">`) keeps working unchanged.
//
// Why <script type="text/..."> rather than <pre>: browsers don't
// HTML-process script content, so any `<` / `>` / `<br/>` inside the
// DOT source reaches the renderer verbatim instead of being mangled
// by the page's HTML parser.

(async () => {
  const blocks = document.querySelectorAll(
    'script[type="text/x-graphviz"]'
  );
  if (blocks.length === 0) return;

  let Graphviz;
  try {
    // @hpcc-js/wasm-graphviz exports `Graphviz` as a named export with
    // a `.load()` static that returns a promise resolving to a
    // renderer instance.
    Graphviz = (await import(
      "https://cdn.jsdelivr.net/npm/@hpcc-js/wasm-graphviz@1/+esm"
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
    const source = block.textContent.trim();
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
