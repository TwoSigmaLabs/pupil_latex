// Persistent KaTeX checker. One JSON object per stdin line: {"tex": "...", "display": bool}
// -> one JSON line: {"ok": true} | {"ok": false, "error": "..."}.
// KaTeX + mhchem are resolved from ../../js/node_modules; throwOnError, strict "ignore".
const path = require("path");
const readline = require("readline");
const jsDir = path.resolve(__dirname, "..", "..", "js");
const katex = require(require.resolve("katex", { paths: [jsDir] }));
require(require.resolve("katex/contrib/mhchem", { paths: [jsDir] }));
console.warn = () => {};
const rl = readline.createInterface({ input: process.stdin, terminal: false });
rl.on("line", (line) => {
  if (!line.trim()) return;
  let r;
  try {
    const it = JSON.parse(line);
    katex.renderToString(it.tex, { throwOnError: true, strict: "ignore", displayMode: !!it.display });
    r = { ok: true };
  } catch (e) {
    r = { ok: false, error: String(e && e.message || e).slice(0, 200) };
  }
  process.stdout.write(JSON.stringify(r) + "\n");
});
