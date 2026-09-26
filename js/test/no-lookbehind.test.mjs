// Safari / iOS below 16.4 cannot parse regex lookbehind, and one lookbehind
// literal is a SyntaxError that kills the whole script. The library must not
// contain any (src/lookbehind.ts does those checks in code).

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import vm from "node:vm";

const DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const IIFE = join(DIST, "pupiltree-latex.iife.js");
// Built from pieces so this file never contains the pattern it looks for.
const LOOKBEHIND = new RegExp("\\(\\?<[=!]");

test("no regex lookbehind anywhere in dist/*.js (ESM files and IIFE bundle)", () => {
  const files = readdirSync(DIST).filter((f) => f.endsWith(".js"));
  assert.ok(files.includes("pupiltree-latex.iife.js"));
  assert.ok(files.length > 10);
  const offenders = [];
  for (const f of files) {
    const lines = readFileSync(join(DIST, f), "utf8").split("\n");
    lines.forEach((line, i) => {
      if (LOOKBEHIND.test(line)) offenders.push(`${f}:${i + 1}`);
    });
  }
  assert.deepEqual(offenders, []);
});

test("IIFE runs on an engine without lookbehind (Safari < 16.4)", () => {
  const code = readFileSync(IIFE, "utf8");
  const errors = [];
  const window = {};
  const ctx = vm.createContext({
    window,
    console: {
      error: (...a) => errors.push(a.map(String).join(" ")),
      warn() {},
      log() {},
    },
  });
  // A RegExp constructor that rejects lookbehind the way old JavaScriptCore
  // does. Literals are covered by the scan above; this catches any pattern
  // built at run time.
  vm.runInContext(
    `
    const R = RegExp;
    const LB = new R("\\\\(\\\\?<[=!]");
    globalThis.RegExp = function RegExp(p, f) {
      const src = p instanceof R ? p.source : String(p);
      if (LB.test(src))
        throw new SyntaxError("Invalid regular expression: invalid group specifier name");
      return f === undefined ? new R(p) : new R(p, f);
    };
    globalThis.RegExp.prototype = R.prototype;
    `,
    ctx,
  );
  // The stub really rejects lookbehind.
  assert.throws(
    () => vm.runInContext('new RegExp("(?" + "<!a)b", "g")', ctx),
    /invalid group specifier name/,
  );
  vm.runInContext(code, ctx);
  assert.deepEqual(errors, []);
  assert.equal(vm.runInContext("typeof PupiltreeLatex", ctx), "object");
  assert.equal(
    vm.runInContext("PupiltreeLatex.fix('3×10⁸ m/s')", ctx),
    "$3\\times10^{8}$ m/s",
  );
  assert.equal(
    vm.runInContext(
      "PupiltreeLatex.normalize('Legacy \\\\(x^2\\\\) and \\\\[E = mc^2\\\\]')",
      ctx,
    ),
    "Legacy $x^2$ and $$E = mc^2$$",
  );
});
