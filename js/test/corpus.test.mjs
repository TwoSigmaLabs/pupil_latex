// The shared conformance corpus (corpus/*.json) run against the JS package.
// Mirrors python/pupiltree_latex/corpus.py: one test per case, the same
// assertion shapes, plus KaTeX rendering for `must_render` cases with
// `engine: "katex"`. Cases whose `impl` excludes "js" are skipped.

import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { after, describe, test } from "node:test";

import katex from "katex";
import "katex/contrib/mhchem";

import {
  auditKinds,
  canonicalize,
  fix,
  loadsLatexAware,
  loadsModelJson,
  normalize,
  repair,
  segment,
  toPlain,
} from "../dist/index.js";

const CORPUS_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "corpus",
);
const FUNCTIONS = [
  "repair",
  "fix",
  "normalize",
  "canonicalize",
  "segment",
  "to_plain",
  "audit",
  "json_transport",
];
const STRING_FUNCTIONS = new Set([
  "repair",
  "fix",
  "normalize",
  "canonicalize",
  "to_plain",
]);
const PREDICATE_KEYS = [
  "contains",
  "not_contains",
  "kinds_include",
  "kinds_exclude",
  "json_contains",
];

class ParseError extends Error {}

function load(name, impl = "js") {
  const path = join(CORPUS_DIR, `${name}.json`);
  if (!existsSync(path)) return [];
  const data = JSON.parse(readFileSync(path, "utf8"));
  return data.cases.filter((c) =>
    (c.impl ?? ["python", "dart", "js"]).includes(impl),
  );
}

/** The implementation's output for `c` (ParseError on a JSON failure). */
function run(fn, c) {
  const inp = c.input;
  switch (fn) {
    case "repair":
      return repair(inp, c.variant !== "hard");
    case "normalize":
      return normalize(inp);
    case "fix":
      return fix(inp);
    case "canonicalize":
      return canonicalize(inp);
    case "segment":
      return segment(inp);
    case "to_plain":
      return toPlain(inp, c.style ?? "text");
    case "audit":
      return auditKinds(inp);
    case "json_transport":
      try {
        if (String(c.via ?? "").includes("loads_model_json"))
          return loadsModelJson(inp);
        return loadsLatexAware(inp);
      } catch (err) {
        if (err instanceof SyntaxError) throw new ParseError(err.message);
        throw err;
      }
    default:
      throw new Error(`unknown function ${fn}`);
  }
}

function deepEqual(a, b) {
  try {
    assert.deepStrictEqual(a, b);
    return true;
  } catch {
    return false;
  }
}

function rendersWithKatex(value, display) {
  const html = katex.renderToString(value, {
    displayMode: display,
    throwOnError: true,
    strict: "ignore",
  });
  return !html.includes("katex-error");
}

/** `[passed, got]` for one case. */
function check(fn, c) {
  if (c.expected_error) {
    let got;
    try {
      got = run(fn, c);
    } catch (err) {
      if (err instanceof ParseError) return [true, "<error>"];
      throw err;
    }
    return [false, got];
  }
  if (c.must_render) {
    const got = run("segment", c);
    const math = got.filter((s) => s.kind === "math");
    if (math.length === 0) return [false, got];
    if (c.engine === "katex") {
      for (const s of math) {
        try {
          if (!rendersWithKatex(s.value, s.display))
            return [false, ["katex-error", s]];
        } catch (err) {
          return [false, [`katex threw: ${err.message}`, s]];
        }
      }
    }
    return [true, got];
  }
  if (c.property === "idempotent") {
    const once = run(fn, c);
    const twice = run(fn, { ...c, input: once });
    return [deepEqual(once, twice), [once, twice]];
  }
  let got;
  try {
    got = run(fn, c);
  } catch (err) {
    if (err instanceof ParseError) return [false, `<error: ${err.message}>`];
    throw err;
  }
  if ("expected" in c && c.expected !== null) {
    if (!deepEqual(got, c.expected)) return [false, got];
    if (STRING_FUNCTIONS.has(fn) && typeof got === "string") {
      const again = run(fn, { ...c, input: got });
      if (again !== got) return [false, ["not idempotent", got, again]];
    }
    return [true, got];
  }
  let ok = true;
  if ("contains" in c) ok = ok && c.contains.every((s) => got.includes(s));
  if ("not_contains" in c)
    ok = ok && !c.not_contains.some((s) => got.includes(s));
  if ("kinds_include" in c)
    ok = ok && c.kinds_include.every((k) => got.includes(k));
  if ("kinds_exclude" in c)
    ok = ok && !c.kinds_exclude.some((k) => got.includes(k));
  if ("json_contains" in c) {
    for (const [key, needle] of Object.entries(c.json_contains)) {
      const value =
        got !== null && typeof got === "object" && !Array.isArray(got)
          ? got[key]
          : undefined;
      ok = ok && typeof value === "string" && value.includes(needle);
    }
  }
  if (!PREDICATE_KEYS.some((k) => k in c))
    return [false, "<no assertion in case>"];
  return [ok, got];
}

/** `must_not_change`: true when `fn` leaves `inp` alone. */
function unchanged(fn, inp) {
  if (fn === "segment") {
    const segs = segment(inp);
    return [
      segs.length === 1 && segs[0].kind === "text" && segs[0].value === inp,
      segs,
    ];
  }
  if (fn === "audit") {
    const kinds = auditKinds(inp);
    return [kinds.length === 0, kinds];
  }
  const got = run(fn, { input: inp });
  return [got === inp, got];
}

const totals = new Map();
function tally(fn, ok) {
  const t = totals.get(fn) ?? { passed: 0, total: 0 };
  t.total++;
  if (ok) t.passed++;
  totals.set(fn, t);
}

const describeCase = (c) =>
  `${c.id}${c.source ? ` (${c.source})` : ""} tags=${JSON.stringify(c.tags ?? [])}`;

for (const fn of FUNCTIONS) {
  const cases = load(fn);
  describe(fn, () => {
    for (const c of cases) {
      test(c.id, () => {
        const [ok, got] = check(fn, c);
        tally(fn, ok);
        const shape = Object.fromEntries(
          Object.entries(c).filter(([k]) =>
            [
              "contains",
              "not_contains",
              "kinds_include",
              "kinds_exclude",
              "json_contains",
              "must_render",
              "property",
              "expected_error",
            ].includes(k),
          ),
        );
        assert.ok(
          ok,
          `${describeCase(c)}\n  input:    ${JSON.stringify(c.input)}\n  expected: ${JSON.stringify(c.expected)} ${JSON.stringify(shape)}\n  got:      ${JSON.stringify(got)}`,
        );
      });
    }
  });
}

describe("must_not_change", () => {
  for (const c of load("must_not_change")) {
    test(c.id, () => {
      for (const fn of c.functions) {
        const [ok, got] = unchanged(fn, c.input);
        tally("must_not_change", ok);
        assert.ok(
          ok,
          `${c.id}: ${fn} changed the input\n  input: ${JSON.stringify(c.input)}\n  got:   ${JSON.stringify(got)}`,
        );
      }
    });
  }
});

test("corpus files exist", () => {
  const missing = [...FUNCTIONS, "must_not_change"].filter(
    (f) => !existsSync(join(CORPUS_DIR, `${f}.json`)),
  );
  assert.deepStrictEqual(missing, []);
});

after(() => {
  const lines = [];
  let passed = 0;
  let total = 0;
  for (const fn of [...FUNCTIONS, "must_not_change"]) {
    const t = totals.get(fn) ?? { passed: 0, total: 0 };
    passed += t.passed;
    total += t.total;
    lines.push(`  ${fn.padEnd(16)} ${t.passed}/${t.total}`);
  }
  console.log(
    `corpus checks (js):\n${lines.join("\n")}\n  ${"all".padEnd(16)} ${passed}/${total}`,
  );
});
