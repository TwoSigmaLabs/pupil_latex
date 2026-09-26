// `fix`, `fixDeep` and `wrapUnicodeChemistry`: the one-call entry point.

import assert from "node:assert/strict";
import { test } from "node:test";

import * as L from "../dist/index.js";

const CHEM = [
  ["H\u2082O", "$\\text{H}_{2}\\text{O}$"],
  ["NaHCO\u2083", "$\\text{NaHCO}_{3}$"],
  ["SO\u2084\u00b2\u207b", "$\\text{SO}_{4}^{2-}$"],
  ["Ca(OH)\u2082", "$\\text{Ca(OH)}_{2}$"],
  ["Fe\u00b3\u207a", "$\\text{Fe}^{3+}$"],
  ["Mg\u00b2\u207a", "$\\text{Mg}^{2+}$"],
  ["O\u2082\u00b2\u207b", "$\\text{O}_{2}^{2-}$"],
  ["C\u2086H\u2081\u2082O\u2086", "$\\text{C}_{6}\\text{H}_{12}\\text{O}_{6}$"],
  ["Na\u207a and Cl\u207b", "$\\text{Na}^{+}$ and $\\text{Cl}^{-}$"],
  ["Water (H\u2082O) boils.", "Water ($\\text{H}_{2}\\text{O}$) boils."],
  ["xH\u2082O hydrate", "$\\text{xH}_{2}\\text{O}$ hydrate"],
  [
    "2H\u2082 + O\u2082 \u2192 2H\u2082O",
    "$\\text{2H}_{2}$ + $\\text{O}_{2}$ \u2192 $\\text{2H}_{2}\\text{O}$",
  ],
  ["(NH\u2084)\u2082SO\u2084", "($\\text{NH}_{4}\\text{)}_{2}\\text{SO}_{4}$"],
  ["Fe\u207a\u00b2 odd order", "$\\text{Fe}^{+2}$ odd order"],
];

const UNCHANGED = [
  "10\u2078", // starts with a digit
  "mc\u00b2", // lowercase start
  "x\u2081",
  "H2O", // no script character
  "O\u00b2", // superscript without a charge
  "_H\u2082O and TRUE_FALSE\u207b", // an underscore before the run blocks it
  "{H\u2082O}", // preceded by a brace
  "\\H\u2082O", // preceded by a backslash
  "$H\u2082O$", // already math
  "$$Fe\u00b3\u207a$$",
  "\\(H\u2082O\\)",
  "plain prose",
  "",
];

test("wrapUnicodeChemistry converts chemistry runs in prose", () => {
  for (const [input, expected] of CHEM) {
    assert.strictEqual(L.wrapUnicodeChemistry(input), expected, input);
    assert.strictEqual(
      L.wrapUnicodeChemistry(expected),
      expected,
      `idempotent on ${expected}`,
    );
  }
});

test("wrapUnicodeChemistry leaves non-chemistry and math alone", () => {
  for (const input of UNCHANGED)
    assert.strictEqual(L.wrapUnicodeChemistry(input), input, input);
  for (const value of [null, undefined, 3, true, {}, []])
    assert.strictEqual(L.wrapUnicodeChemistry(value), value);
});

test("wrapUnicodeChemistry rewrites text segments on their raw slice", () => {
  assert.strictEqual(
    L.wrapUnicodeChemistry(
      "Cost \\$5 for H\u2082O and $x_1$ then Fe\u00b3\u207a",
    ),
    "Cost \\$5 for $\\text{H}_{2}\\text{O}$ and $x_1$ then $\\text{Fe}^{3+}$",
  );
  assert.strictEqual(
    L.wrapUnicodeChemistry(
      "H\u2082O\nCO\u2082 + H\u2082O \u2192 H\u2082CO\u2083",
    ),
    "$\\text{H}_{2}\\text{O}$\n$\\text{CO}_{2}$ + $\\text{H}_{2}\\text{O}$ \u2192 $\\text{H}_{2}\\text{CO}_{3}$",
  );
});

test("fix = merge(chemistry(symbols(canonicalize(normalize(text)))))", () => {
  const input =
    "Cost $5 and \\(\\theta\\) with \x0crac{1}{2} and \u03c0 and H\u2082O";
  const expected =
    "Cost \\$5 and $\\theta$ with $\\frac{1}{2}$ and $\\pi$ and $\\text{H}_{2}\\text{O}$";
  assert.strictEqual(L.fix(input), expected);
  const staged = (s) =>
    L.mergeAdjacentMath(
      L.wrapUnicodeChemistry(
        L.wrapBareSymbolCommands(L.canonicalize(L.normalize(s))),
      ),
    );
  for (const s of [
    input,
    "3 \times 10^8 and \x0crac{a}{b}",
    "\u03b1 + \u03b2 \u2264 \u03c0 \u00d7 2",
  ]) {
    assert.strictEqual(L.fix(s), staged(s), s);
  }
  // Reference results from the Python implementation.
  assert.strictEqual(
    L.fix("3 \times 10^8 and \x0crac{a}{b}"),
    "3 $\\times 10^8$ and $\\frac{a}{b}$",
  );
  assert.strictEqual(
    L.fix("\u03b1 + \u03b2 \u2264 \u03c0 \u00d7 2"),
    "$\\alpha$ + $\\beta \\leq \\pi \\times$ 2",
  );
  assert.strictEqual(L.fix("\u00cf\u20ac r^2"), "$\\pi r^2$");
  assert.strictEqual(
    L.fix("2H\u2082 + O\u2082 \u2192 2H\u2082O"),
    "$\\text{2H}_{2}$ + $\\text{O}_{2} \\rightarrow \\text{2H}_{2}\\text{O}$",
  );
  assert.strictEqual(L.fix("$H\u2082O$"), "$H_{2}O$");
  assert.strictEqual(
    L.fix("\u00cf\u20ac and Fe\u00b3\u207a"),
    "$\\pi$ and $\\text{Fe}^{3+}$",
  );
});

test("fix is idempotent and passes non-strings through", () => {
  const samples = [
    "Cost $5 and \\(\\theta\\) with \x0crac{1}{2} and \u03c0 and H\u2082O",
    "SO\u2084\u00b2\u207b in $\\ce{H2SO4}$ and \\$60 and $x^2$",
    "\u221a2 and \u0127\u03c9 and H_{2}O and MCQ_SINGLE",
    "https://a/b_c.png {{IMAGE:59_1}} NaHCO\u2083",
    "no math at all",
  ];
  for (const s of samples) {
    const once = L.fix(s);
    assert.strictEqual(L.fix(once), once, s);
  }
  for (const value of [null, undefined, 5, true, { a: 1 }, ["x"], ""])
    assert.strictEqual(L.fix(value), value);
});

test("fixDeep fixes content strings only, skipping non-content keys and URLs", () => {
  const doc = {
    _id: "H\u2082O_69e7",
    audioUrl: "https://s/H\u2082O.wav",
    status: "Fe\u00b3\u207a",
    question: "Water is H\u2082O and \\(\\theta\\) costs $5",
    options: [{ id: "opt_1", text: "Fe\u00b3\u207a" }, "\x0crac{1}{2}"],
    createdAt: new Date(Date.UTC(2026, 8, 25, 10, 0)),
    nested: { description: "see https://a/b_c.png and CO\u2082" },
    n: 7,
  };
  const out = L.fixDeep(doc);
  assert.strictEqual(out._id, doc._id);
  assert.strictEqual(out.audioUrl, doc.audioUrl);
  assert.strictEqual(out.status, doc.status);
  assert.strictEqual(
    out.question,
    "Water is $\\text{H}_{2}\\text{O}$ and $\\theta$ costs \\$5",
  );
  assert.strictEqual(out.options[0].id, "opt_1");
  assert.strictEqual(out.options[0].text, "$\\text{Fe}^{3+}$");
  assert.strictEqual(out.options[1], "$\\frac{1}{2}$");
  assert.strictEqual(
    out.createdAt,
    doc.createdAt,
    "a Date passes through, as in Python fix_deep",
  );
  assert.strictEqual(
    out.nested.description,
    "see https://a/b_c.png and $\\text{CO}_{2}$",
  );
  assert.strictEqual(out.n, 7);
  assert.strictEqual(
    doc.question,
    "Water is H\u2082O and \\(\\theta\\) costs $5",
    "input is not mutated",
  );
  assert.deepStrictEqual(L.fixDeep(L.fixDeep(doc)), out, "idempotent");
});

test("wrapBareSymbolCommands wraps argument-less symbols outside math", () => {
  assert.strictEqual(
    L.wrapBareSymbolCommands("3 \\times 10^8"),
    "3 $\\times$ 10^8",
  );
  assert.strictEqual(
    L.wrapBareSymbolCommands("\\alpha and \\to and \\cdots"),
    "$\\alpha$ and $\\to$ and $\\cdots$",
  );
  assert.strictEqual(
    L.wrapBareSymbolCommands("$\\times$ and $$\\alpha$$"),
    "$\\times$ and $$\\alpha$$",
  );
  assert.strictEqual(
    L.wrapBareSymbolCommands("a \\\\times b"),
    "a \\\\times b",
  );
  assert.strictEqual(
    L.wrapBareSymbolCommands("\\timesx and \\frac{1}{2}"),
    "\\timesx and \\frac{1}{2}",
  );
  assert.strictEqual(
    L.wrapBareSymbolCommands("\\leftrightarrow"),
    "$\\leftrightarrow$",
    "longest name wins",
  );
  assert.strictEqual(L.wrapBareSymbolCommands("no commands"), "no commands");
  for (const value of [null, 7, {}])
    assert.strictEqual(L.wrapBareSymbolCommands(value), value);
  assert.ok(
    L.SYMBOL_COMMANDS instanceof Set &&
      L.SYMBOL_COMMANDS.has("times") &&
      L.SYMBOL_COMMANDS.has("to"),
  );
  // Values with arguments (`\tfrac{1}{2}`, `\sqrt[3]`, `\mathbb{R}`) are not
  // plain commands; `\sqrt` (from `√`) is, as in Python.
  assert.ok(
    !L.SYMBOL_COMMANDS.has("tfrac") && !L.SYMBOL_COMMANDS.has("mathbb"),
  );
  // `\sqrt` (from `√`) is excluded: `$\sqrt$` is a parse error.
  assert.ok(!L.SYMBOL_COMMANDS.has("sqrt"));
  assert.strictEqual(
    L.wrapBareSymbolCommands("use \\sqrt here"),
    "use \\sqrt here",
  );
  assert.strictEqual(L.fix("use \\sqrt here"), "use \\sqrt here");
});

test("mergeAdjacentMath joins inline spans separated by blanks only", () => {
  assert.strictEqual(L.mergeAdjacentMath("$\\times$ $10^8$"), "$\\times 10^8$");
  assert.strictEqual(L.mergeAdjacentMath("$a$ $b$ $c$"), "$a b c$");
  assert.strictEqual(L.mergeAdjacentMath("$a$\t$b$"), "$a b$");
  assert.strictEqual(L.mergeAdjacentMath("$$a$$ $$b$$"), "$$a$$ $$b$$");
  assert.strictEqual(L.mergeAdjacentMath("$a$ + $b$"), "$a$ + $b$");
  assert.strictEqual(L.mergeAdjacentMath("$a$ $$b$$"), "$a$ $$b$$");
  assert.strictEqual(
    L.mergeAdjacentMath("\\(a\\) $b$"),
    "\\(a\\) $b$",
    "only `$` spans merge",
  );
  assert.strictEqual(
    L.mergeAdjacentMath("$a$ $b"),
    "$a$ $b",
    "fewer than four dollars",
  );
  assert.strictEqual(L.mergeAdjacentMath("$a$\n$b$"), "$a$\n$b$");
  for (const value of [null, 7, ""])
    assert.strictEqual(L.mergeAdjacentMath(value), value);
});

test("fixDeep on scalars and non-plain objects", () => {
  assert.strictEqual(L.fixDeep("H\u2082O"), "$\\text{H}_{2}\\text{O}$");
  assert.strictEqual(L.fixDeep(null), null);
  assert.strictEqual(L.fixDeep(4), 4);
  class Ref {}
  const ref = new Ref();
  assert.strictEqual(L.fixDeep({ ref }).ref, ref);
});
