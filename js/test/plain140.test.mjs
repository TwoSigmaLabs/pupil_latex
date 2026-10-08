// v1.4.0 Group A behaviour the corpus cannot express (translation of the
// matching tests in python/tests/test_api.py).

import assert from "node:assert/strict";
import { test } from "node:test";

import * as L from "../dist/index.js";

// [input, Python html.unescape(input)]
const UNESCAPE_SAMPLES = [
  ["a &amp; b", "a & b"],
  ["a &amp;lt; b", "a &lt; b"],
  ["&thinsp;&ndash;&mdash;&micro;&hellip;", " –—µ…"],
  ["x &lt y &gt z", "x < y > z"],
  ["&ampx &notit; &notin; &not", "&x ¬it; ∉ ¬"],
  ["&AMP; &Afr; &afr;", "& 𝔄 𝔞"],
  ["&#65;&#x41;&#X41;&#65 &#x41g", "AAAA Ag"],
  ["&#0; &#13; &#128; &#129; &#150; &#159;", "� \r € \u0081 – Ÿ"],
  ["&#1; &#11; &#127; &#xFDD0; &#xFFFE; &#x1FFFF;", "     "],
  ["&#xD800; &#x110000; &#99999999999999999999;", "� � �"],
  ["&#128512; &#x1F600;", "😀 😀"],
  ["AT&T Q&A &foo; & ; &; &#; &#x;", "AT&T Q&A &foo; & ; &; &#; &#x;"],
  [
    "&abcdefghijklmnopqrstuvwxyzabcdefghij;",
    "&abcdefghijklmnopqrstuvwxyzabcdefghij;",
  ],
  ["&lt;&lt;&lt", "<<<"],
  ["no entity", "no entity"],
];

test("unescapeHtmlEntities is Python html.unescape (v140-a2)", () => {
  for (const [input, expected] of UNESCAPE_SAMPLES) {
    assert.strictEqual(L.unescapeHtmlEntities(input), expected, input);
  }
});

test("compare decodes entities once; normalize keeps its set (v140-a2)", () => {
  assert.strictEqual(L.toPlain("a &amp;lt; b", "compare"), "a &lt; b");
  assert.strictEqual(L.normalize("a &amp;lt; b"), "a < b");
  assert.strictEqual(L.normalize("x &thinsp; y"), "x &thinsp; y");
});

test("compare fold table (v140-a1)", () => {
  assert.strictEqual(L.COMPARE_FOLD["½"], "1/2");
  assert.strictEqual(L.COMPARE_FOLD["㎤"], "cm³");
  assert.strictEqual(L.COMPARE_FOLD["–"], "-");
  assert.ok(!("²" in L.COMPARE_FOLD));
});

test("unwrapTypographicSpans (v140-a7)", () => {
  assert.strictEqual(L.unwrapTypographicSpans("a$\\ldots$"), "a…");
  assert.strictEqual(L.unwrapTypographicSpans("$\\textmu$m"), "$\\mu$m");
  assert.strictEqual(L.unwrapTypographicSpans("$x\\ldots$"), "$x\\ldots$");
  assert.strictEqual(L.unwrapTypographicSpans("costs \\$5"), "costs \\$5");
  assert.strictEqual(L.unwrapTypographicSpans(null), null);
});

test("element symbols (v140-a9)", () => {
  assert.strictEqual(L.ELEMENT_SYMBOLS.size, 118);
  assert.strictEqual(L.bareChemistryToUnicode("H_2SO_4"), "H₂SO₄");
  assert.strictEqual(L.bareChemistryToUnicode("lo_0"), "lo_0");
});
