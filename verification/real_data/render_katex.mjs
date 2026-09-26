// Render every math segment (before and after fix) with KaTeX + mhchem.
// Run from anywhere:  node render_katex.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const jsRoot = path.resolve(here, "..", "..", "js");
const katexPath = path.join(
  jsRoot,
  "node_modules",
  "katex",
  "dist",
  "katex.mjs",
);
const mhchemPath = path.join(
  jsRoot,
  "node_modules",
  "katex",
  "dist",
  "contrib",
  "mhchem.mjs",
);
const katex = (await import(pathToFileURL(katexPath).href)).default;
await import(pathToFileURL(mhchemPath).href);

const segs = JSON.parse(
  fs.readFileSync(path.join(here, "math_segments.json"), "utf8"),
);
const failures = [];
let nBefore = 0;
let nAfter = 0;
let failBefore = 0;
let failAfter = 0;
let uniqueFail = 0;
for (const s of segs) {
  nBefore += s.before_n;
  nAfter += s.after_n;
  try {
    katex.renderToString(s.tex, {
      displayMode: s.display,
      throwOnError: true,
      strict: "ignore",
    });
  } catch (e) {
    uniqueFail += 1;
    failBefore += s.before_n;
    failAfter += s.after_n;
    failures.push({
      tex: s.tex,
      display: s.display,
      message: String(e.message || e).slice(0, 300),
      before_n: s.before_n,
      after_n: s.after_n,
      before_ids: s.before,
      after_ids: s.after,
    });
  }
}
const out = {
  katex_version: katex.version,
  unique_segments: segs.length,
  segments_before: nBefore,
  segments_after: nAfter,
  failing_unique: uniqueFail,
  failing_before: failBefore,
  failing_after: failAfter,
  only_after: failures.filter((f) => f.before_n === 0).length,
  only_before: failures.filter((f) => f.after_n === 0).length,
  failures,
};
fs.writeFileSync(
  path.join(here, "katex_results.json"),
  JSON.stringify(out, null, 1),
);
const { failures: _f, ...brief } = out;
console.log(JSON.stringify(brief, null, 1));
