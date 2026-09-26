/**
 * Entry point of the browser bundle `dist/pupiltree-latex.iife.js`, which
 * exposes `window.PupiltreeLatex`: the core API plus the vanilla DOM adapter
 * (`PupiltreeLatex.typesetMath(root)`), for pages that vendor KaTeX and
 * auto-render as plain scripts (Fillers).
 *
 * Minimum engines: Safari/iOS 14, Chrome/Edge 80, Firefox 78. The library
 * uses no regex lookbehind (src/lookbehind.ts does those checks in code), so
 * iPads on iOS 14-16.3 run it. scripts/build-iife.mjs still wraps the bundle
 * in try/catch: on an engine older than the minimum the script loads without
 * an uncaught error, logs once and leaves `window.PupiltreeLatex` undefined.
 * See README.md.
 */

export * from "./index.js";
export * from "./dom.js";
