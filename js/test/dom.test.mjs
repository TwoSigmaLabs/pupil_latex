// The vanilla DOM adapter against real KaTeX auto-render inside jsdom.

import assert from "node:assert/strict";
import { test } from "node:test";

import { JSDOM } from "jsdom";
import renderMathInElement from "katex/contrib/auto-render";
import "katex/contrib/mhchem";

import {
  auditRawMath,
  ESC_DOLLAR_CLASS,
  ESC_DOLLAR_SENTINEL,
  maskEscapedDollars,
  MATH_DELIMITERS,
  typesetMath,
} from "../dist/dom.js";

function makeRoot(html) {
  const dom = new JSDOM(
    `<!doctype html><body><div id="root">${html}</div></body>`,
  );
  // auto-render creates nodes through the global `document`.
  globalThis.document = dom.window.document;
  return dom.window.document.getElementById("root");
}

const katexOption = { katex: { renderMathInElement } };

function silenced(fn) {
  const original = console.warn;
  const calls = [];
  console.warn = (...args) => calls.push(args);
  try {
    return [fn(), calls];
  } finally {
    console.warn = original;
  }
}

test("currency \\$60 stays text and $x^2$ typesets", () => {
  const root = makeRoot("Cost \\$60 and $x^2$ today");
  const [hits, warnings] = silenced(() => typesetMath(root, katexOption));
  assert.deepStrictEqual(hits, []);
  assert.deepStrictEqual(warnings, []);
  assert.strictEqual(root.querySelectorAll(".katex").length, 1);
  assert.strictEqual(root.querySelectorAll(".katex-error").length, 0);
  const dollar = root.querySelector(`.${ESC_DOLLAR_CLASS}`);
  assert.ok(dollar, "restored dollar span");
  assert.strictEqual(dollar.textContent, "$");
  assert.ok(root.textContent.includes("Cost $60 and"));
  assert.ok(!root.textContent.includes(ESC_DOLLAR_SENTINEL));
  assert.ok(!root.textContent.includes("$x^2$"));
});

test("unescaped currency before a formula is protected too", () => {
  const root = makeRoot("Cost $60 and $x^2$ today");
  silenced(() => typesetMath(root, katexOption));
  assert.strictEqual(root.querySelectorAll(".katex").length, 1);
  assert.ok(root.textContent.includes("Cost $60 and"));
});

test("a form-feed-corrupted \\frac is repaired and typesets", () => {
  const root = makeRoot("Area is $\x0crac{1}{2}bh$ here");
  const [hits] = silenced(() => typesetMath(root, katexOption));
  assert.deepStrictEqual(hits, []);
  assert.strictEqual(root.querySelectorAll(".katex").length, 1);
  assert.strictEqual(root.querySelectorAll(".katex-error").length, 0);
  assert.ok(root.querySelector(".mfrac"), "a fraction was rendered");
  assert.ok(!root.textContent.includes("\x0c"));
});

test("legacy delimiters and mhchem typeset", () => {
  const root = makeRoot("Water \\(\\ce{H2O}\\) and \\[E = mc^2\\]");
  const [hits] = silenced(() => typesetMath(root, katexOption));
  assert.deepStrictEqual(hits, []);
  assert.strictEqual(root.querySelectorAll(".katex").length, 2);
  assert.strictEqual(root.querySelectorAll(".katex-display").length, 1);
});

test("fix mode (default) typesets Unicode chemistry and bare symbols", () => {
  const root = makeRoot("Water is H₂O and Fe³⁺ and π.");
  const [hits] = silenced(() => typesetMath(root, katexOption));
  assert.deepStrictEqual(hits, []);
  assert.strictEqual(root.querySelectorAll(".katex").length, 3);
  assert.strictEqual(root.querySelectorAll(".katex-error").length, 0);
  assert.ok(root.textContent.startsWith("Water is "));
  assert.ok(!root.textContent.includes("H₂O"));
});

test("normalize mode keeps chemistry and bare symbols as text", () => {
  const root = makeRoot("Water is H₂O and Fe³⁺ and $x^2$");
  silenced(() => typesetMath(root, { ...katexOption, mode: "normalize" }));
  assert.strictEqual(root.querySelectorAll(".katex").length, 1);
  assert.ok(root.textContent.includes("H₂O and Fe³⁺ and "));
});

test("typesetting twice is idempotent", () => {
  const root = makeRoot("Cost \\$60 and $x^2$ then $$\\frac{a}{b}$$ and \\$5");
  silenced(() => typesetMath(root, katexOption));
  const once = root.innerHTML;
  const [hits] = silenced(() => typesetMath(root, katexOption));
  assert.deepStrictEqual(hits, []);
  assert.strictEqual(root.innerHTML, once);
  assert.strictEqual(root.querySelectorAll(".katex").length, 2);
  assert.strictEqual(root.querySelectorAll(`.${ESC_DOLLAR_CLASS}`).length, 2);
});

test("skipped tags and ignored classes are left alone", () => {
  const root = makeRoot(
    '<code>$x^2$</code><span class="keep">$y^2$</span> $z^2$',
  );
  const [hits] = silenced(() =>
    typesetMath(root, { ...katexOption, ignoredClasses: ["keep"] }),
  );
  assert.deepStrictEqual(hits, []);
  assert.strictEqual(root.querySelector("code").textContent, "$x^2$");
  assert.strictEqual(root.querySelector(".keep").textContent, "$y^2$");
  assert.strictEqual(root.querySelectorAll(".katex").length, 1);
});

test("auditRawMath reports leftover raw math and typesetMath warns once", () => {
  const root = makeRoot("Still raw $\\frac{1}{2}$ and \\(x\\) here");
  assert.deepStrictEqual(auditRawMath(root), [
    "Still raw $\\frac{1}{2}$ and \\(x\\) here",
  ]);
  assert.deepStrictEqual(auditRawMath(null), []);

  // Raw math that auto-render cannot see (a stub renderer that does nothing)
  // is reported by the return value and warned about exactly once.
  const stub = makeRoot("Still raw $\\frac{1}{2}$ here");
  const [hits, warnings] = silenced(() =>
    typesetMath(stub, { katex: { renderMathInElement: () => {} } }),
  );
  assert.deepStrictEqual(hits, ["Still raw $\\frac{1}{2}$ here"]);
  assert.strictEqual(warnings.length, 1);
  assert.ok(String(warnings[0][0]).includes("math left raw"));
  assert.deepStrictEqual(warnings[0][2], hits);

  // After a real typeset nothing is left, and later DOM changes are seen.
  const live = makeRoot("Fine $x^2$");
  const [none] = silenced(() => typesetMath(live, katexOption));
  assert.deepStrictEqual(none, []);
  live.appendChild(
    live.ownerDocument.createTextNode(" then $\\alpha$ arrives"),
  );
  assert.deepStrictEqual(auditRawMath(live), ["then $\\alpha$ arrives"]);
});

test("typesetMath needs an auto-render", () => {
  const root = makeRoot("$x$");
  delete globalThis.renderMathInElement;
  assert.throws(() => typesetMath(root), /auto-render/);
  assert.deepStrictEqual(typesetMath(null, katexOption), []);
});

test("maskEscapedDollars mirrors auto-render's split", () => {
  assert.strictEqual(
    maskEscapedDollars("Cost \\$60 and $x^2$"),
    `Cost ${ESC_DOLLAR_SENTINEL}60 and $x^2$`,
  );
  assert.strictEqual(maskEscapedDollars("$\\$5 + x$"), "$\\$5 + x$");
  assert.strictEqual(
    maskEscapedDollars("\\\\$x$ and \\$1"),
    `\\\\$x$ and ${ESC_DOLLAR_SENTINEL}1`,
  );
  assert.strictEqual(maskEscapedDollars("open $x \\$1"), "open $x \\$1");
  assert.strictEqual(maskEscapedDollars("no dollars"), "no dollars");
  assert.strictEqual(MATH_DELIMITERS[0].left, "$$");
  assert.strictEqual(MATH_DELIMITERS.length, 4);
});
