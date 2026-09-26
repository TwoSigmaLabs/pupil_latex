// Audit round 2 (2026-09-26): invariants the corpus cases cannot state.
// Mirrors python/tests/test_audit2.py (the ftfy variants do not apply: JS
// has only the table fixer).
//
// - A span created by `fix` never ends right before a digit or opens against
//   a literal `$` (the renderers would drop it and a later pass nested `$$`).
// - `fix` is idempotent on every audit input.
// - The mojibake table repairs currency and keeps repeated Greek letters.
// - `fixDeep` leaves taxonomy lists (`tags`, `labels`, `keywords`) alone.

import assert from "node:assert/strict";
import { test } from "node:test";

import * as L from "../dist/index.js";

const AUDIT_INPUTS = [
  "The product 3×4×5=60 is easy.",
  "If x≤5 then y≥2.",
  "Find 3.14×10⁻⁵ in standard form.",
  "3×10⁸ m/s and $E=mc^2$",
  "6.022×10²³ particles",
  "6.022 × 10²³ mol⁻¹",
  "CuSO₄·5H₂O",
  "Take n→∞ and x→0.",
  "Given ε₀ and μ₀, find c.",
  "λ₁, λ₂ are eigenvalues.",
  "σ₁₂",
  "µ₀ = 4π × 10⁻⁷ T·m/A",
  "x\\leq5 holds",
  "x$\\leq$5 holds",
  "Use \\pi2 here",
  "2×10 and 3 \\times4",
  "\\alpha_1 and \\beta^2",
  "\\\\\\frac{1}{2}",
  "\\\\$\\frac{1}{2}$",
  "$ H₂",
  "$H₂O",
  "$×5",
  "$\\leq 5",
  "Solve $ x^2 + 1 = 0 $ now",
  "Let $ \\theta = 30° $ here",
  "I paid $ 5 and got $ 3 back",
  "m/s² and per mm³ and x²5",
  "यदि x≤५ है",
  "\\sqrt{2}3 and \\frac{1}{2}4",
  "â‚¬5 and Â£3",
  "ππ and Ï€Ï€",
  "2.5583 and 1,00,000 and ₹2,50,000 and 9:3:3:1 and 45°",
];

const CMD_RE = /\\([A-Za-z]+)/g;

for (const s of AUDIT_INPUTS) {
  test(`fix is idempotent: ${JSON.stringify(s)}`, () => {
    const once = L.fix(s);
    assert.equal(L.fix(once), once);
  });

  test(`fix never creates display math: ${JSON.stringify(s)}`, () => {
    if (s.includes("$$") || s.includes("\\[")) return;
    const out = L.fix(s);
    assert.ok(!L.segment(out).some((seg) => seg.display), out);
    assert.ok(!/(?<!\\)\$\$/.test(out), out);
  });

  test(`no KaTeX command left next to a dollar in prose: ${JSON.stringify(s)}`, () => {
    for (const seg of L.segment(L.fix(s))) {
      if (seg.kind !== "text") continue;
      const raw = seg.raw;
      for (const m of raw.matchAll(CMD_RE)) {
        if (!L.KATEX_COMMANDS.has(m[1])) continue;
        const before = m.index ? raw[m.index - 1] : "";
        const end = m.index + m[0].length;
        const after = end < raw.length ? raw[end] : "";
        assert.ok(before !== "$" && after !== "$", `${s} -> ${raw}`);
      }
    }
  });
}

test("prose digits are byte-identical", () => {
  const s = "2.5583 and 1,00,000 and ₹2,50,000 and 9:3:3:1 and 45°";
  assert.equal(L.fix(s), s);
  assert.equal(L.canonicalize(s), s);
});

test("currency mojibake", () => {
  assert.equal(L.fix("â‚¬5"), "€5");
  assert.equal(L.canonicalize("â‚¬5"), "€5");
  assert.equal(L.fix("Price Â£5, â‚¹500, Â¥3"), "Price £5, ₹500, ¥3");
  assert.ok(!L.fix("â‚¬5 and â‚¹2,50,000").includes("neg"));
});

test("repeated Greek is kept", () => {
  assert.equal(L.fix("ππ"), "$\\pi\\pi$");
  assert.equal(L.fix("ωω"), "$\\omega\\omega$");
  assert.equal(L.fix("Ï€Ï€"), "$\\pi\\pi$");
  assert.equal(L.normalize("αα and λλ"), "αα and λλ");
});

test("the table still collapses a pair made by a context rule", () => {
  // `Ï` next to a real π is mojibake of the same letter: one π, not two.
  assert.equal(L.fixMojibakeTable("2Ïπ"), "2π");
});

test("fixDeep skips taxonomy lists", () => {
  const doc = {
    tags: ["x_1", "E_n"],
    labels: ["a^2"],
    keywords: ["H₂O"],
    text: "x_1",
  };
  const out = L.fixDeep(doc);
  assert.deepEqual(out.tags, ["x_1", "E_n"]);
  assert.deepEqual(out.labels, ["a^2"]);
  assert.deepEqual(out.keywords, ["H₂O"]);
  assert.equal(out.text, "$x_1$");
  assert.deepEqual(L.canonicalizeDeep(doc).tags, ["x_1", "E_n"]);
});

// Spec §0.1: no `$$` mid-sentence for the audited shapes.
test("no display math mid-sentence for the audited shapes", () => {
  for (const s of [
    "Light moves at 3×10⁸ m/s today.",
    "Avogadro: 6.022×10²³ per mole.",
    "Eigenvalues λ₁ and λ₂ here.",
    "If x≤5 then stop.",
    "Blue vitriol is CuSO₄·5H₂O crystals.",
  ]) {
    const out = L.fix(s);
    assert.ok(!out.includes("$$"), `${s} -> ${out}`);
    assert.equal(L.fix(out), out);
  }
});
