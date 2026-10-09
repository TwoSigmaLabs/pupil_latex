// v1.4.0 Group A behaviour the corpus cannot express (translation of the
// matching tests in python/tests/test_api.py).

import 'package:pupiltree_latex/pupiltree_latex.dart';
import 'package:test/test.dart';

// [input, Python html.unescape(input)]
const _unescapeSamples = <(String, String)>[
  ('a &amp; b', 'a & b'),
  ('a &amp;lt; b', 'a &lt; b'),
  ('&thinsp;&ndash;&mdash;&micro;&hellip;', ' –—µ…'),
  ('x &lt y &gt z', 'x < y > z'),
  ('&ampx &notit; &notin; &not', '&x ¬it; ∉ ¬'),
  ('&AMP; &Afr; &afr;', '& \u{1D504} \u{1D51E}'),
  ('&#65;&#x41;&#X41;&#65 &#x41g', 'AAAA Ag'),
  ('&#0; &#13; &#128; &#129; &#150; &#159;', '� \r € \u0081 – Ÿ'),
  ('&#1; &#11; &#127; &#xFDD0; &#xFFFE; &#x1FFFF;', '     '),
  ('&#xD800; &#x110000; &#99999999999999999999;', '� � �'),
  ('&#128512; &#x1F600;', '\u{1F600} \u{1F600}'),
  ('AT&T Q&A &foo; & ; &; &#; &#x;', 'AT&T Q&A &foo; & ; &; &#; &#x;'),
  (
    '&abcdefghijklmnopqrstuvwxyzabcdefghij;',
    '&abcdefghijklmnopqrstuvwxyzabcdefghij;',
  ),
  ('&lt;&lt;&lt', '<<<'),
  ('no entity', 'no entity'),
];

void main() {
  test('unescapeHtmlEntities is Python html.unescape (v140-a2)', () {
    for (final (input, expected) in _unescapeSamples) {
      expect(unescapeHtmlEntities(input), expected, reason: input);
    }
  });

  test('compare decodes entities once; normalize keeps its set (v140-a2)',
      () {
    expect(toPlain('a &amp;lt; b', style: 'compare'), 'a &lt; b');
    expect(normalize('a &amp;lt; b'), 'a < b');
    expect(normalize('x &thinsp; y'), 'x &thinsp; y');
  });

  test('compare fold table (v140-a1)', () {
    expect(kCompareFold['½'], '1/2');
    expect(kCompareFold['㎤'], 'cm³');
    expect(kCompareFold['–'], '-');
    expect(kCompareFold.containsKey('²'), isFalse);
  });

  test('unwrapTypographicSpans (v140-a7)', () {
    expect(unwrapTypographicSpans(r'a$\ldots$'), 'a…');
    expect(unwrapTypographicSpans(r'$\textmu$m'), r'$\mu$m');
    expect(unwrapTypographicSpans(r'$x\ldots$'), r'$x\ldots$');
    expect(unwrapTypographicSpans(r'costs \$5'), r'costs \$5');
  });

  test('element symbols (v140-a9)', () {
    expect(kElementSymbols.length, 118);
    expect(bareChemistryToUnicode('H_2SO_4'), 'H₂SO₄');
    expect(bareChemistryToUnicode('lo_0'), 'lo_0');
  });
}
