// JS parity pass: fix / segment / auditKinds / toPlain over strings.json.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(here, "..", "..", "js", "dist", "index.js");
const lib = await import(pathToFileURL(dist).href);
const { fix, segment, auditKinds, toPlain } = lib;
if (typeof fix !== "function")
  throw new Error("fix is not exported by js/dist/index.js");

const strings = JSON.parse(
  fs.readFileSync(path.join(here, "strings.json"), "utf8"),
);
const t0 = Date.now();
const results = strings.map((rec) => {
  const fixed = fix(rec.text);
  return {
    id: rec.id,
    fix: fixed,
    audit_before: auditKinds(rec.text),
    audit_after: auditKinds(fixed),
    segments: segment(fixed),
    to_plain_text: toPlain(fixed, "text"),
    to_plain_pdf: toPlain(fixed, "pdf"),
    idempotent: fix(fixed) === fixed,
  };
});
fs.writeFileSync(path.join(here, "js_results.json"), JSON.stringify(results));
console.log(
  "js: strings",
  results.length,
  "ms",
  Date.now() - t0,
  "non-idempotent",
  results.filter((r) => !r.idempotent).length,
);
