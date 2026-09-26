// Builds dist/pupiltree-latex.iife.js (window.PupiltreeLatex).
//
// The library uses no regex lookbehind (Safari/iOS only gained it in 16.4;
// src/lookbehind.ts applies those checks in code, and
// test/no-lookbehind.test.mjs keeps it that way). `target` lists the minimum
// engines, so esbuild lowers any newer syntax a future change might add.
//
// The bundle is still wrapped in try/catch as a safety net: if an engine
// fails while the bundle initialises, the script loads without an uncaught
// error, `window.PupiltreeLatex` stays undefined and one console.error says
// why, so the host page keeps working.
// Minimum browsers: Safari/iOS 14, Chrome/Edge 80, Firefox 78 (see README.md).

import { build } from "esbuild";

const message =
  "PupiltreeLatex: this browser cannot run the bundle (it needs Safari/iOS " +
  "14+, Chrome/Edge 80+ or Firefox 78+); math is left as source.";

await build({
  entryPoints: ["src/iife.ts"],
  bundle: true,
  format: "iife",
  globalName: "PupiltreeLatex",
  target: ["es2020", "safari14", "ios14", "chrome80", "edge80", "firefox78"],
  minify: true,
  outfile: "dist/pupiltree-latex.iife.js",
  banner: { js: "try{" },
  footer: {
    js:
      '}catch(e){typeof console!="undefined"&&console.error(' +
      JSON.stringify(message) +
      ",e)}",
  },
  logLevel: "warning",
});
