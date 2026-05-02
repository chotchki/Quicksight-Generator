// Phase S spike — graphviz WASM bootstrap.
//
// Finds every <script type="text/x-graphviz"> block emitted by the
// diagram() macro (when QS_USE_WASM=1 was set at build time), loads
// @hpcc-js/wasm-graphviz from jsDelivr, runs `g.dot(source)` against
// each block's textContent, and inserts the rendered SVG after the
// script element.
//
// Why <script type="text/..."> rather than <pre>: browsers don't
// HTML-process script content, so any `<` / `>` / `<br>` inside the
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
    console.debug(`qs-graphviz-wasm: rendering block ${i}`, source);
    try {
      const svg = renderer.dot(source);
      const wrapper = document.createElement("div");
      wrapper.className = "qs-graphviz-wasm-rendered";
      wrapper.innerHTML = svg;
      // Insert after the <script> rather than replacing it so the
      // source stays in the DOM for "view source" debugging.
      block.parentNode.insertBefore(wrapper, block.nextSibling);
    } catch (err) {
      console.error(`qs-graphviz-wasm: render failed for block ${i}`, err);
      const errWrapper = document.createElement("pre");
      errWrapper.className = "qs-graphviz-wasm-error";
      errWrapper.textContent =
        "graphviz render error: " + (err.message || err) + "\n\n" + source;
      block.parentNode.insertBefore(errWrapper, block.nextSibling);
    }
  }
})();
