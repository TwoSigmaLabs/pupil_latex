// Audit round 3 (2026-09-26): invariants the corpus cases cannot state.
// Mirrors python/tests/test_audit3.py.
//
// - Greek words (`2πr`, `fλ`, `Δx`) become one span; units, Greek prose,
//   long Latin words and identifiers keep their earlier shape.
// - `canonicalize` closes the last group of a span that was never closed
//   (`$\frac{1}{2$`), never guessing an empty argument, and `audit` is clean
//   afterwards.
// - Symbols inside a bare script / command argument group (`e^{iπ}`) never
//   get a span of their own inside the group.
// - All of it is idempotent and never moves or drops a digit.

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import * as L from "../dist/index.js";
import { greekWordAt } from "../dist/unicodeMath.js";

const GREEK_WORD_INPUTS = [
  "Area = 2πr and πr²",
  "Circumference 2πr",
  "v = fλ",
  "E = hν",
  "Δx·Δp ≥ ħ/2",
  "ωt + φ",
  "ρL",
  "2πrh",
  "sin θ",
  "nλ = d sinθ",
  "ΔG = ΔH − TΔS",
  "2.5λ and ₹2π",
  "x≤2πr and 3×πr",
  "πr^2 and 2πr_1",
  "ΔH₂O",
  "e^{iπ}",
  "Cost \\$5π",
  "q_π and २π and πक",
];

// Units keep exactly the shape they had before audit round 3.
const UNITS = {
  "5 µs": "5 $\\mu$s",
  "10 kΩ": "10 k$\\Omega$",
  "3 MΩ": "3 M$\\Omega$",
  "2 µm": "2 $\\mu$m",
  "5 µg": "5 $\\mu$g",
  "4 mΩ": "4 m$\\Omega$",
  "Ω·m": "$\\Omega\\cdot$m",
  "J·s": "J$\\cdot$s",
  "10Ω": "10$\\Omega$",
  "5μs": "5$\\mu$s",
  "10kΩ": "10k$\\Omega$",
  "2 GΩ": "2 G$\\Omega$",
  "3 µF": "3 $\\mu$F",
  "1 μΩ": "1 $\\mu\\Omega$",
  kΩm: "k$\\Omega$m",
  "5 μm²": "5 $\\mu m^{2}$", // merged by mergeAdjacentMath, as before
};

const BRACE_FIXED = {
  "$\\frac{1}{2$": "$\\frac{1}{2}$",
  "$x^{2$": "$x^{2}$",
  "$\\sqrt{x+1$": "$\\sqrt{x+1}$",
  "$x_{i$ and $\\vec{F$": "$x_{i}$ and $\\vec{F}$",
  "$\\frac{a}{b$ and $y$": "$\\frac{a}{b}$ and $y$",
  // `$y$` is a span, so the text segment before it holds exactly one pair.
  "$x^{2$ and $y$ and $z": "$x^{2}$ and $y$ and $z",
};

const BRACE_KEPT = [
  "$\\frac{1}{$",
  "$\\frac{$",
  "$x^{$",
  "$x^{2^$",
  "$\\frac{1}{\\sqrt$",
  "$\\frac{\\frac{1}{2$",
  "$\\left( x^{2$",
  "$\\begin{matrix} x^{2$",
  "$a}{b$",
  "$\\{x$",
  "$\\frac{1}{2 $",
  "$\\frac{1}{2$5",
  "$$\\frac{1}{2$$",
  "$x^{2$ and $z", // odd count of dollars on the line
];

const SCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉";

function digits(s) {
  let t = "";
  for (const c of s) {
    const k = SCRIPT_DIGITS.indexOf(c);
    t += k === -1 ? c : String(k % 10);
  }
  return t.match(/\p{Nd}/gu) ?? [];
}

for (const text of [
  ...GREEK_WORD_INPUTS,
  ...Object.keys(UNITS),
  ...Object.keys(BRACE_FIXED),
]) {
  test(`idempotent and digits kept: ${JSON.stringify(text)}`, () => {
    const out = L.fix(text);
    assert.equal(L.fix(out), out);
    assert.deepEqual(digits(out), digits(text));
  });
}

for (const [text, expected] of Object.entries(UNITS).sort()) {
  test(`unit keeps its shape: ${JSON.stringify(text)}`, () => {
    assert.equal(L.fix(text), expected);
  });
}

test("Greek word spans", () => {
  assert.equal(L.fix("Circumference 2πr"), "Circumference $2\\pi r$");
  assert.equal(L.fix("v = fλ"), "v = $f\\lambda$");
  assert.equal(L.fix("E = hν"), "E = $h\\nu$");
  assert.equal(L.fix("ωt + φ"), "$\\omega t$ + $\\phi$");
  assert.equal(L.fix("ρL"), "$\\rho L$");
  assert.equal(L.fix("2πrh"), "$2\\pi rh$");
  assert.equal(L.fix("sin θ"), "sin $\\theta$");
  assert.equal(
    L.fix("Δx·Δp ≥ ħ/2"),
    "$\\Delta x\\cdot\\Delta p \\geq \\hbar$/2",
  );
});

test("Greek word refusals", () => {
  // 3+ Latin letters, Greek prose, identifiers, scripts, other scripts.
  for (const text of [
    "αβγtest",
    "Thetaα",
    "λmax",
    "sinθ",
    "λόγος",
    "Ελλάδα",
    "q_π",
  ]) {
    const out = L.fix(text);
    assert.ok(!/\\[A-Za-z]+ [A-Za-z]/.test(out), `${text} -> ${out}`);
  }
  assert.equal(greekWordAt("αβγtest", 0), null);
  assert.equal(greekWordAt("λόγος", 0), null);
  assert.equal(greekWordAt("x^iπ", 3), null);
  assert.equal(greekWordAt("२π", 1), null);
  assert.equal(greekWordAt("πक", 0), null);
  assert.equal(greekWordAt("10 kΩ", 4), null);
  assert.equal(greekWordAt("5μs", 1), null);
  assert.equal(greekWordAt("ΔH₂O", 0), null);
  assert.deepEqual(greekWordAt("a 2πr b", 3), [2, 5]);
  assert.deepEqual(greekWordAt("2.5λ", 3), [0, 4]);
});

test("radical coefficient untouched", () => {
  assert.equal(L.fix("2√3"), "2$\\sqrt{3}$");
  assert.equal(L.fix("2$\\sqrt{3}$"), "2$\\sqrt{3}$");
});

for (const [text, expected] of Object.entries(BRACE_FIXED).sort()) {
  test(`unclosed group is closed: ${JSON.stringify(text)}`, () => {
    assert.equal(L.canonicalize(text), expected);
    assert.equal(L.fix(text), expected);
    // The trailing `$z` of one case is a real unbalanced dollar.
    assert.deepEqual(
      L.audit(expected).filter((f) => f.kind !== "unbalanced_dollar"),
      [],
    );
  });
}

for (const text of BRACE_KEPT) {
  test(`unclosed group kept when closing would guess: ${JSON.stringify(text)}`, () => {
    assert.equal(L.canonicalize(text), text);
  });
}

test("brace close is not a normalize or repair rule", () => {
  assert.equal(L.normalize("$\\frac{1}{2$"), "$\\frac{1}{2$");
  assert.equal(L.repair("$\\frac{1}{2$"), "$\\frac{1}{2$");
});

// ---------------------------------------------------------------------------
// audit3-script-group: no `$` inside an open brace group of a math span
// ---------------------------------------------------------------------------

const SCRIPT_GROUP_INPUTS = [
  "e^{iπ}",
  "e^{iπt}",
  "x_{α}",
  "10^{-3}μ",
  "\\frac{π}{2}",
  "\\sqrt{2π}",
  "sin^{2}θ",
  "a_{αβ} and e^{i×π}",
  "\\text{π} and \\vec{α}",
  "\\frac{π} and x^{π",
  "the set {α, β}",
  "q_{π}_x",
];

function dollarInOpenGroup(value) {
  let depth = 0;
  let i = 0;
  while (i < value.length) {
    const c = value[i];
    if (c === "\\") {
      i += 2;
      continue;
    }
    if (c === "{") depth++;
    else if (c === "}") depth = Math.max(0, depth - 1);
    else if (c === "$" && depth > 0) return true;
    i++;
  }
  return false;
}

function allCorpusInputs() {
  const dir = join(
    dirname(fileURLToPath(import.meta.url)),
    "..",
    "..",
    "corpus",
  );
  const out = [];
  for (const f of readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .sort()) {
    const data = JSON.parse(readFileSync(join(dir, f), "utf8"));
    if (data.function === "json_transport") continue;
    for (const c of data.cases)
      if (typeof c.input === "string") out.push(c.input);
  }
  return [...new Set([...out, ...SCRIPT_GROUP_INPUTS])];
}

test("fix never puts a dollar inside an open group of a math span", () => {
  const bad = [];
  for (const text of allCorpusInputs()) {
    const out = L.fix(text);
    // A span that was already in the input as written (Backend's
    // `$\text{VS} = $\frac{\text{CS}$}{R}$` is left alone on purpose) is
    // not something fix introduced.
    const before = new Set(
      L.segment(L.repair(text))
        .filter((s) => s.kind === "math")
        .map((s) => s.value),
    );
    for (const seg of L.segment(out)) {
      if (
        seg.kind === "math" &&
        dollarInOpenGroup(seg.value) &&
        !before.has(seg.value)
      )
        bad.push([text, out]);
    }
  }
  assert.deepEqual(bad, []);
});

for (const text of SCRIPT_GROUP_INPUTS) {
  test(`script group idempotent and digits kept: ${JSON.stringify(text)}`, () => {
    const out = L.fix(text);
    assert.equal(L.fix(out), out);
    assert.deepEqual(digits(out), digits(text));
  });
}
