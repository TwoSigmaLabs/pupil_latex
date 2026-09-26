/// Behavioural tests the JSON corpus cannot express: deep walkers, empty
/// strings, fast paths, the mojibake table, JSON transport. Port of the
/// applicable parts of `python/tests/test_api.py`.
library;

import 'dart:convert';

import 'package:pupiltree_latex/pupiltree_latex.dart';
import 'package:test/test.dart';

void main() {
  test('string functions return the empty string unchanged', () {
    expect(repair(''), '');
    expect(normalize(''), '');
    expect(canonicalize(''), '');
    expect(toPlain(''), '');
    expect(toPlain('', style: 'tts'), '');
    expect(fixMojibakeTable(''), '');
  });

  test('segment, audit and containsMath on the empty string', () {
    expect(segment(''), isEmpty);
    expect(audit(''), isEmpty);
    expect(auditKinds(''), isEmpty);
    expect(containsMath(''), isFalse);
  });

  test('repair fast path and the hard variant', () {
    expect(repair('no controls here'), 'no controls here');
    expect(repair('3 \times 10'), '3 \\times 10');
    expect(repair('3 \timesx'), '3 \timesx'); // "timesx" is no command
    expect(repair('3 \times 10', guessWhitespace: false), '3 \times 10');
    expect(repair('a\x0bb'), 'ab');
    expect(repair('\x00\x7f'), '');
  });

  test('repairDeep touches every string and nothing else', () {
    final doc = <String, Object?>{
      'question': 'Area \x0crac{1}{2}',
      'options': [
        '\x08eta decay',
        {'text': '\times'},
      ],
      'url': 'https://x/\x0crac.png',
      'n': 3,
      'flag': true,
    };
    final out = repairDeep(doc) as Map<String, dynamic>;
    expect(out['question'], 'Area \\frac{1}{2}');
    expect((out['options'] as List)[0], '\\beta decay');
    expect(((out['options'] as List)[1] as Map)['text'], '\\times');
    expect(out['url'], 'https://x/\\frac.png');
    expect(out['n'], 3);
    expect(out['flag'], true);
    expect(repairDeep(null), isNull);
    expect(repairDeep(2.5), 2.5);
  });

  test('canonicalizeDeep skips non-content keys and URLs', () {
    final doc = <String, Object?>{
      '_id': 'ahs_69e74f5e84fd',
      'audioUrl': 'https://s/ahs_69e74f5e84fd_vocab_20260425.wav',
      'className': '10_A',
      'status': 'in_progress',
      'question': 'Water is H_{2}O at 3 \u00d7 10^8',
      'options': [
        {'id': 'opt_a_1', 'text': '\u03c0'},
      ],
      'nested': {'description': 'see https://a/b_c.png here'},
      'count': 7,
    };
    final out = canonicalizeDeep(doc) as Map<String, dynamic>;
    expect(out['_id'], doc['_id']);
    expect(out['audioUrl'], doc['audioUrl']);
    expect(out['className'], '10_A');
    expect(out['status'], 'in_progress');
    expect(out['question'], r'Water is $H_{2}O$ at 3 $\times$ $10^8$');
    expect(((out['options'] as List)[0] as Map)['id'], 'opt_a_1');
    expect(((out['options'] as List)[0] as Map)['text'], r'$\pi$');
    expect((out['nested'] as Map)['description'], 'see https://a/b_c.png here');
    expect(out['count'], 7);
    expect(canonicalizeDeep(['x_1', 5]), ['\$x_1\$', 5]);
  });

  test('walk predicates', () {
    expect(isNonContentKey('userId'), isTrue);
    expect(isNonContentKey('user_id'), isTrue);
    expect(isNonContentKey('created-at'), isTrue);
    expect(isNonContentKey('question'), isFalse);
    expect(isNonContentKey(5), isFalse);
    expect(isUrlOrPathString('https://a/b'), isTrue);
    expect(isUrlOrPathString('/api/x'), isTrue);
    expect(isUrlOrPathString('clip.MP3'), isTrue);
    expect(isUrlOrPathString('plain'), isFalse);
    expect(isUrlOrPathString(''), isFalse);
    expect(isNotRenderedKey('raw_response'), isTrue);
    expect(isNotRenderedKey('body_raw'), isTrue);
    expect(isNotRenderedKey('prompt'), isTrue);
    expect(isNotRenderedKey('text'), isFalse);
  });

  test('canonicalize is idempotent on typical content', () {
    const samples = [
      r'The price is $50 and the ratio is 1/\sqrt{2}',
      r'Cost $60 and $x^2$',
      r'\left[ $\frac12$ \right] $\frac{q^2}{a^2}$',
      r'H_{2}O and MCQ_SINGLE and 3^{\circ}C',
      '\u221a2 and \u0127\u03c9 and \u03c0 and 3 \u00d7 10^8',
      r'{{IMAGE:59_1}} then \frac{a}{b}',
    ];
    for (final s in samples) {
      final once = canonicalize(s);
      expect(canonicalize(once), once, reason: s);
    }
  });

  test('canonicalize leaves an argument-less structural command as prose', () {
    expect(canonicalize(r'use \sqrt here'), r'use \sqrt here');
    expect(canonicalize(r'use \frac{1}{2} here'), r'use $\frac{1}{2}$ here');
    expect(canonicalize(r'the \sum symbol'), r'the $\sum$ symbol');
    expect(fix(r'use \sqrt here'), r'use \sqrt here');
  });

  test('canonicalize converts what its own wrapping just created', () {
    // `\text{…}` is a text-mode group: its content stays as written (R2).
    expect(canonicalize(r'\text{H₂O}'), r'$\text{H₂O}$');
    expect(
        canonicalize(r'$10⁻³ and C₆H₁₂O₆$'), r'$10^{-3} and C_{6}H_{12}O_{6}$');
    expect(canonicalize(r'x^10 in $x^10$ and H₂O'),
        r'$x^{10}$ in $x^{10}$ and H₂O');
  });

  test('canonicalize leaves whole-string URLs and image markers alone', () {
    expect(canonicalize('https://a/b_c.png'), 'https://a/b_c.png');
    expect(canonicalize('  gs://bucket/x_y  '), '  gs://bucket/x_y  ');
    expect(canonicalize('{{IMAGE:59_1}} x_1'), r'{{IMAGE:59_1}} $x_1$');
  });

  test('canonicalize helper steps are exported', () {
    expect(normalizeHomoglyphs('\u00b5m \u2212 \u2126'), '\u03bcm - \u03a9');
    expect(
        unicodeMathToLatex(r'$a\cdot b$ and \u03c0'), r'$a\cdot b$ and \u03c0');
    expect(unicodeMathToLatex('\$\u03c0 \u00d7 2\$'), r'$\pi \times 2$');
    expect(wrapBareUnicodeMath('\u210f\u03c9'), r'$\hbar\omega$');
    expect(wrapBareUnicodeMath('\u0127\u03c9'),
        '\u0127\$\\omega\$'); // \u0127 is a homoglyph
    expect(wrapBareUnicodeMath('\u221a and \u03c0'), '\u221a and \$\\pi\$');
    expect(convertCombiningVec('a\u20d7 and \$b\u20d7\$'),
        r'$\vec{a}$ and $\vec{b}$');
  });

  test('normalize is idempotent on typical content', () {
    const samples = [
      r'\(\theta\) costs $5000 and $\frac14$ then \nNext',
      r'Cost \$60 and $x^2$ end \( orphan',
      '\u00cf\u20ac is \u00c3\u2014 fun with \u00e2\u02c6\u0161' '2',
      r'$5-$10 and $2x + 3$',
    ];
    for (final s in samples) {
      final once = normalize(s);
      expect(normalize(once), once, reason: s);
    }
  });

  test('normalize never wraps or converts', () {
    expect(
      normalize('\u221a2 and \u03c0 and \\frac{1}{2} and H_{2}O'),
      '\u221a2 and \u03c0 and \\frac{1}{2} and H_{2}O',
    );
    expect(
      normalize('https://a/b_c.png {{IMAGE:59_1}}'),
      'https://a/b_c.png {{IMAGE:59_1}}',
    );
  });

  test('step order: theta inside paren delimiters', () {
    // B5: decoding prose escapes before normalising delimiters turned
    // `\(\theta\)` into TAB + "heta" (script_editor #420, tutor #383).
    expect(
        normalize(r'\(\theta\) and \(\times 2\)'), r'$\theta$ and $\times 2$');
  });

  test('normalize steps individually', () {
    expect(normalizeDelimiters('\\(a\n b\\) \\[c\\]'), r'$a b$ $$c$$');
    expect(normalizeDelimiters(r'\\[2pt] x'), r'\\[2pt] x');
    expect(stripOrphanDelimiters(r'a \( b \] c'), 'a  b  c');
    expect(escapeCurrency(r'$5000 and $\frac14$'), r'\$5000 and $\frac14$');
    expect(escapeCurrency(r'$5-$10'), r'\$5-\$10');
    expect(escapeCurrency(r'$2x + 3$'), r'$2x + 3$');
    expect(decodeEscapesOutsideMath(r'a\nb $\nu$ \neq \text{x}'),
        'a\nb \$\\nu\$ \\neq \\text{x}');
    expect(decodeEscapesOutsideMath(r'\nStatement \t x'), '\nStatement \t x');
  });

  test('auditDeep paths and skips', () {
    final doc = <String, Object?>{
      'question': 'Area \x0crac{1}{2}',
      'raw_response': r'\(ignored\)',
      'audio_url': r'https://x/\(y\).wav',
      'options': [
        {'text': r'$x^10$'},
        {'text': 'fine'},
      ],
      'meta': jsonEncode({'explanation': r'\(json leaf\)'}),
    };
    final found = auditDeep(doc);
    final paths = {for (final hit in found) hit.path: hit.finding.kind};
    expect(paths['question'], 'control_char');
    expect(paths['options[0].text'], 'script_missing_braces');
    expect(paths['meta(json).explanation'], 'legacy_delimiter');
    expect(
      paths.keys.any(
          (p) => p.startsWith('raw_response') || p.startsWith('audio_url')),
      isFalse,
    );
    final listHits = auditDeep(['fine', r'\(a\)']);
    expect(listHits.map((h) => h.path), ['[1]', '[1]']); // opener and closer
    expect(auditDeep(42), isEmpty);
  });

  test('audit snippet makes control chars visible', () {
    final f = audit('Area \x0crac{1}{2}')
        .singleWhere((x) => x.kind == 'control_char');
    expect(f.snippet, contains('<0x0C>'));
    expect(f.position, 5);
    expect(isError(['control_char']), isTrue);
    expect(isError(['mojibake']), isFalse);
    expect(countByKind(audit(r'\(a\) \[b\]')), {'legacy_delimiter': 4});
    expect(makeSnippet('a\nb', 1), 'a\u21b5b');
    expect(makeSnippet('x' * 200, 100), startsWith('\u2026'));
  });

  test('audit unsupported command inside math only', () {
    expect(auditKinds(r'$\frac{1}{2}$'), isEmpty);
    expect(auditKinds(r'$\ce{H2O}$'), isEmpty);
    expect(auditKinds(r'$\notacommand{x}$'), ['unsupported_command']);
    expect(auditKinds(r'prose \notacommand{x}'), isEmpty);
    expect(auditKinds(r'$\mathscr{L}$'), ['unsupported_command']);
    expect(auditKinds(r'\mathfrak{g}'), ['unsupported_command']);
  });

  test('audit findings are sorted by position then kind', () {
    final kinds = auditKinds('\u03c0 \\(x\\) \$');
    expect(kinds, [
      'bare_unicode_math',
      'legacy_delimiter',
      'legacy_delimiter',
      'unbalanced_dollar'
    ]);
    expect(allKinds.length, 12);
    expect(errorKinds, {'control_char'});
  });

  test('isPlainProse fast path', () {
    expect(isPlainProse('Water boils at 100 degrees.'), isTrue);
    expect(isPlainProse(r'Water is $H_2O$'), isFalse);
    expect(isPlainProse(r'Use \frac here'), isFalse);
    expect(isPlainProse('**bold**'), isFalse);
    expect(isPlainProse('- item'), isFalse);
    expect(isPlainProse('a\n\nb'), isFalse);
    expect(isPlainProse('  indented'), isFalse);
    expect(isPlainProse('1. list'), isFalse);
    expect(isPlainProse(''), isTrue);
  });

  test('containsMath', () {
    expect(containsMath(r'$x$'), isTrue);
    expect(containsMath(r'\frac{1}{2}'), isTrue);
    expect(containsMath(r'costs $5 and $10'), isFalse);
    expect(containsMath('plain'), isFalse);
  });

  test('segment value/raw/display and equality', () {
    final segs = segment(r'Cost \$60 and $x^2$ and $$a$$');
    expect(segs.map((s) => s.kind), ['text', 'math', 'text', 'math']);
    expect(segs[0].value, r'Cost $60 and ');
    expect(segs[0].raw, r'Cost \$60 and ');
    expect(
        segs[1],
        const Segment(
            kind: 'math', display: false, value: 'x^2', raw: r'$x^2$'));
    expect(segs[3].display, isTrue);
    expect(segs[1].toJson(),
        {'kind': 'math', 'display': false, 'value': 'x^2', 'raw': r'$x^2$'});
    expect(segs[1].hashCode, segs[1].hashCode);
    expect(segs[1].toString(), contains('x^2'));
  });

  test('toPlain styles and the unknown-style error', () {
    expect(toPlain(r'$\vec{F} = m\vec{a}$'), 'F = ma');
    expect(toPlain(r'$\vec{F}$', style: 'pdf'), 'F\u20d7');
    expect(toPlain(r'$\vec{AB}$', style: 'pdf'), 'vec(AB)');
    expect(toPlain(r'$\hat{i}$', style: 'pdf'), '\u00ee');
    expect(toPlain(r'$x^2$', style: 'tts'), 'x squared');
    expect(latexToPlain(r'$\alpha$', markAccents: true), '\u03b1');
    expect(styles, ['text', 'pdf', 'tts']);
    expect(() => toPlain(r'$x$', style: 'html'), throwsArgumentError);
  });

  test('mojibake table fixes common patterns and leaves accents alone', () {
    for (final (bad, good) in [
      ('\u00cf\u20ac', '\u03c0'),
      ('\u00c3\u2014', '\u00d7'),
      ('\u00e2\u02c6\u0161' '2', '\u221a2'),
      ('\u00e2\u2030\u00a4', '\u2264'),
    ]) {
      expect(fixMojibakeTable(bad), good);
    }
    expect(fixMojibakeTable('\u00c5ngstr\u00f6m and caf\u00e9'),
        '\u00c5ngstr\u00f6m and caf\u00e9');
    expect(fixMojibakeTable('plain ascii'), 'plain ascii');
  });

  test('escapeLatexForJson and the loaders', () {
    expect(
        escapeLatexForJson(r'{"a": "\frac{1}{2}"}'), r'{"a": "\\frac{1}{2}"}');
    expect(escapeLatexForJson(r'{"a": "x\ny"}'), r'{"a": "x\ny"}');
    expect(escapeLatexForJson(r'{"a": "$\nu$"}'), r'{"a": "$\\nu$"}');
    expect(escapeLatexForJson(r'{"a": "\u00e9 \" \\ \/ \0 \ "}'),
        r'{"a": "\u00e9 \" \\ \/ \\0 \\ "}'); // `\0` and `\ ` are LaTeX (R5)
    expect(escapeLatexForJson(r'{"a": "\% \b"}'), r'{"a": "\\% \\b"}');
    expect(loadsLatexAware(r'{"a": "\frac{1}{2}"}'), {'a': r'\frac{1}{2}'});
    expect(loadsModelJson(r'{"a": "\frac{1}{2}"}'), {'a': r'\frac{1}{2}'});
    expect(() => loadsModelJson('{"a": '), throwsFormatException);
    expect(() => loadsLatexAware('{"a": '), throwsFormatException);
    expect(loadsLatexAware('[1, 2]'), [1, 2]);
    // Raw control characters inside a string value are content
    // (Python `strict=False`), not a decode error.
    expect(loadsLatexAware('{"q": "a\tb\nc"}'), {'q': 'a\tb\nc'});
    expect(loadsModelJson('{"q": "a\tb"}'), {'q': 'a\tb'});
    expect(kProseEscapeCommands, isNot(contains('nu')));
    expect(kProseEscapeCommands, contains('neq'));
  });

  test('wrapUnicodeChemistry wraps formulas in prose only', () {
    const cases = {
      'H₂O': r'$\text{H}_{2}\text{O}$',
      'NaHCO₃': r'$\text{NaHCO}_{3}$',
      'SO₄²⁻': r'$\text{SO}_{4}^{2-}$',
      'Ca(OH)₂': r'$\text{Ca(OH)}_{2}$',
      'Fe³⁺': r'$\text{Fe}^{3+}$',
      'Na⁺ and Cl⁻': r'$\text{Na}^{+}$ and $\text{Cl}^{-}$',
      'C₆H₁₂O₆': r'$\text{C}_{6}\text{H}_{12}\text{O}_{6}$',
      '10⁸': '10⁸', // starts with a digit
      'mc²': 'mc²', // lowercase start
      'x₁': 'x₁', // lowercase start
      'H2O': 'H2O', // no script character
      'E²': 'E²', // superscript without a charge
      'ΔH₂O': 'ΔH₂O', // preceded by a letter
      r'$H₂O$': r'$H₂O$', // math segment untouched
      r'\H₂O and {H₂O}': r'\H₂O and {H₂O}', // defensive skips
      'Water (H₂O) boils.': r'Water ($\text{H}_{2}\text{O}$) boils.',
      'Water (H₂O) and CO₂.':
          r'Water ($\text{H}_{2}\text{O}$) and $\text{CO}_{2}$.',
      '2H₂ + O₂ → 2H₂O':
          r'$\text{2H}_{2}$ + $\text{O}_{2}$ → $\text{2H}_{2}\text{O}$',
      '5H₂O crystal': r'$\text{5H}_{2}\text{O}$ crystal',
      'xH₂O': r'$\text{xH}_{2}\text{O}$', // hydrate prefix (R10)
      'abH₂O': 'abH₂O', // two lowercase letters are a word
      'x_H₂O': 'x_H₂O', // an underscore joins the word (F5)
      'TRUE_FALSE⁻': 'TRUE_FALSE⁻',
      'Na⁺': r'$\text{Na}^{+}$',
      '': '',
    };
    for (final e in cases.entries) {
      expect(wrapUnicodeChemistry(e.key), e.value, reason: e.key);
      expect(wrapUnicodeChemistry(e.value), e.value,
          reason: 'idempotent ${e.key}');
    }
  });

  test('wrapBareSymbolCommands wraps argument-less commands in prose', () {
    expect(wrapBareSymbolCommands(r'3 \times 10^8'), r'3 $\times$ 10^8');
    expect(wrapBareSymbolCommands(r'\alpha and \to and \ldots'),
        r'$\alpha$ and $\to$ and $\ldots$');
    // One tight cluster (spec §0.1), never `$\times$$\pi$`.
    expect(wrapBareSymbolCommands(r'\times\pi'), r'$\times\pi$');
    expect(wrapBareSymbolCommands(r'x\leq5'), r'$x\leq5$');
    expect(wrapBareSymbolCommands(r'x$\leq$5'), r'$x\leq5$');
    expect(wrapBareSymbolCommands(r'3\times4\times5'), r'$3\times4\times5$');
    expect(wrapBareSymbolCommands(r'a \\times b'),
        r'a \\times b'); // escaped backslash
    expect(wrapBareSymbolCommands(r'\timesx and \frac{1}{2}'),
        r'\timesx and \frac{1}{2}');
    expect(wrapBareSymbolCommands(r'$\times$ stays'), r'$\times$ stays');
    expect(wrapBareSymbolCommands('no backslash'), 'no backslash');
    expect(kSymbolCommands, containsAll(['times', 'pi', 'leq', 'to', 'ldots']));
    expect(kSymbolCommands, isNot(contains('frac'))); // takes arguments
    expect(kSymbolCommands, isNot(contains('sqrt'))); // `$\sqrt$` cannot render
    expect(wrapBareSymbolCommands(r'use \sqrt here'), r'use \sqrt here');
    expect(kSymbolCommands,
        isNot(contains('mathbb'))); // `\mathbb{R}` is not plain
  });

  test('mergeAdjacentMath joins inline spans separated by blanks only', () {
    expect(mergeAdjacentMath(r'3 $\times$ $10^8$ and $x$'),
        r'3 $\times 10^8$ and $x$');
    expect(mergeAdjacentMath(r'$a$ $b$ $c$'), r'$a b c$');
    expect(mergeAdjacentMath(r'$a$ + $b$'), r'$a$ + $b$');
    expect(mergeAdjacentMath(r'$$a$$ $$b$$'), r'$$a$$ $$b$$');
    expect(mergeAdjacentMath(r'$a$ $$b$$'), r'$a$ $$b$$');
    expect(mergeAdjacentMath(r'\(a\) $b$'), r'\(a\) $b$'); // only `$` spans
    expect(mergeAdjacentMath(r'$a$ $b$'), r'$a b$');
    expect(mergeAdjacentMath(r'$a$ $'), r'$a$ $'); // fewer than four dollars
    expect(mergeAdjacentMath('\$a\$\t\$b\$ x \$c\$'), '\$a b\$ x \$c\$');
  });

  test(
      'fix is normalize + canonicalize + symbols + chemistry + merge, idempotent',
      () {
    expect(fix(''), '');
    expect(
      fix('Cost \$5 and \\(\\theta\\) with \x0crac{1}{2} and π and H₂O'),
      r'Cost \$5 and $\theta$ with $\frac{1}{2}$ and $\pi$ and $\text{H}_{2}\text{O}$',
    );
    // TAB + "imes" and FF + "rac": JSON-escape damage repaired, then wrapped.
    expect(fix('3 \times 10^8 and \x0crac{a}{b}'),
        r'3 $\times 10^8$ and $\frac{a}{b}$');
    // The trailing `2` is prose to every step, so it stays outside the span
    // (corpus `fix/curated-greek-and-symbols`).
    expect(fix('α + β ≤ π × 2'), r'$\alpha$ + $\beta \leq \pi \times$ 2');
    expect(fix('Ï€ r^2'), r'$\pi r^2$');
    expect(fix('2H₂ + O₂ → 2H₂O'),
        r'$\text{2H}_{2}$ + $\text{O}_{2} \rightarrow \text{2H}_{2}\text{O}$');
    expect(fix(r'$$a$$ $$b$$'), r'$$a$$ $$b$$');
    expect(fix(r'$a$ + $b$'), r'$a$ + $b$');
    // `\\times` is a double-escaped command: canonicalize collapses it, then
    // the bare symbol is wrapped (mergeAdjacentMath alone leaves it).
    expect(fix(r'a \\times b'), r'a $\times$ b');
    const samples = [
      r'The price is $50 and the ratio is 1/\sqrt{2}',
      'Ï€ is Ã— fun with âˆš2 and SO₄²⁻',
      'Water is H_{2}O at 3 × 10^8 and Fe³⁺',
      r'{{IMAGE:59_1}} then \frac{a}{b} and https://a/b_c.png',
      r'3 \times 10^8 and \frac{a}{b}',
      'α + β ≤ π × 2',
    ];
    for (final s in samples) {
      final once = fix(s);
      expect(fix(once), once, reason: s);
    }
  });

  test('fixDeep skips non-content keys and URLs, fixes the rest', () {
    final doc = <String, Object?>{
      '_id': 'ahs_69e7',
      'audioUrl': 'https://s/H₂O_clip.wav',
      'status': 'in_progress',
      'question': r'\(\theta\) and H₂O and π',
      'options': ['Fe³⁺', 'plain', 4],
      'nested': {'text': 'costs \$5.'},
    };
    final out = fixDeep(doc) as Map<String, dynamic>;
    expect(out['_id'], 'ahs_69e7');
    expect(out['audioUrl'], 'https://s/H₂O_clip.wav');
    expect(out['status'], 'in_progress');
    expect(out['question'], r'$\theta$ and $\text{H}_{2}\text{O}$ and $\pi$');
    expect(out['options'], [r'$\text{Fe}^{3+}$', 'plain', 4]);
    expect((out['nested'] as Map)['text'], r'costs \$5.');
    expect(fixDeep(null), isNull);
    expect(fixDeep(['H₂O']), [r'$\text{H}_{2}\text{O}$']);
  });

  test('lesson-script labels survive every escape decoder (D0)', () {
    // (a) normalize keeps `\type:` / `\read:` / `\teacher:`.
    expect(normalize(r'\teacher: hello \type: mcq \read: it \tool: x'),
        r'\teacher: hello \type: mcq \read: it \tool: x');
    expect(normalize(r'\nNext line'), '\nNext line'); // still decoded
    // (b) escapeLatexForJson doubles the backslash of a label.
    expect(escapeLatexForJson(r'{"s": "\teacher: hi\nb"}'),
        r'{"s": "\\teacher: hi\nb"}');
    expect(loadsLatexAware(r'{"s": "\read: it"}'), {'s': r'\read: it'});
    // (c) repair restores a label whose backslash became TAB/LF/CR.
    expect(repair('\teacher: hi and \read: it'), r'\teacher: hi and \read: it');
    expect(repair('\tool: x'), r'\tool: x');
    expect(repair('\teacher hi'), '\teacher hi'); // no colon: a real tab
    expect(repair('\nother: x'), '\nother: x'); // not a label
    expect(kScriptLabels, containsAll(['teacher', 'type', 'read', 'tool']));
    // (d) canonicalize never wraps a script line whole.
    expect(canonicalize(r'\type: \alpha'), r'\type: \alpha');
    expect(fix('\type: mcq'), r'\type: mcq'); // TAB + "ype:" repaired first
  });

  test('bare scripts after a backslash or dollar are not wrapped (D1)', () {
    // `\log` is structural now: wrapped with its scripts only (R3e).
    expect(canonicalize(r'\log_{10} x'), r'$\log_{10}$ x');
    // The whole short string is wrapped once; `log_{10}` is never wrapped on
    // its own as a bare script (`$\log_{10}$` inside `$…$` would be broken).
    expect(canonicalize(r'see \log_{10}'), r'see $\log_{10}$');
    expect(canonicalize(r'\$x^2$'), r'\$x^2$');
    expect(canonicalize('E_n and x^2'), r'$E_n$ and $x^2$');
  });

  test('escapeCurrency copies a math span through its closer (D2)', () {
    expect(escapeCurrency(r'$\sqrt$2'), r'$\sqrt$2');
    expect(normalize(r'$\sqrt$2'), r'$\sqrt$2');
    expect(escapeCurrency(r'$x$ and $5'), r'$x$ and \$5');
    expect(escapeCurrency(r'$x$5 and $y$'), r'$x$5 and $y$');
    expect(escapeCurrency(r'$x and $5'),
        r'$x and $5'); // one span, no closer re-read
  });

  test('ellipsis is no longer wrapped bare but converts inside math (D3)', () {
    expect(canonicalize('1, 2, …'), '1, 2, …');
    expect(canonicalize(r'$1, 2, …$'), r'$1, 2, \ldots$');
    expect(kWrappableBareChars, isNot(contains('…')));
  });

  test('lowercase-word suffixes are identifiers, short ones are math (D4)', () {
    expect(canonicalize('mode no_capture and ai_recreate'),
        'mode no_capture and ai_recreate');
    expect(canonicalize('E_n, x_0, H_2O'), r'$E_n$, $x_0$, $H_2O$');
    expect(canonicalize('v_avg'), 'v_avg'); // the documented casualty
  });

  test('grade-level keys are non-content (D5)', () {
    expect(isNonContentKey('gradeLevel'), isTrue);
    expect(isNonContentKey('grade_level'), isTrue);
    expect(isNonContentKey('classLevel'), isTrue);
    expect(isNonContentKey('difficulty_level'), isTrue);
    expect(canonicalizeDeep({'gradeLevel': '10_A', 'q': 'x_1'}),
        {'gradeLevel': '10_A', 'q': r'$x_1$'});
  });

  test('mojibake table knows Ïˆ and decodes HTML entities first (D6, D8)', () {
    expect(fixMojibakeTable('Ïˆ'), 'ψ');
    expect(fixMojibakeTable('a &amp; b &lt; c'), 'a & b < c');
    expect(fixMojibakeTable('&#960; and &#x3C0; and &pi;'), 'π and π and π');
    expect(fixMojibakeTable('&unknown; &#0; &#xD800; &#1114112;'),
        '&unknown; &#0; &#xD800; &#1114112;');
    expect(unescapeHtmlEntities('&#128512;'), '\u{1F600}');
    expect(unescapeHtmlEntities('no entity'), 'no entity');
    expect(normalize('x &gt; 5 and Ï€'), 'x > 5 and π');
  });

  test('mergeAdjacentMath skips unbalanced spans (D7)', () {
    expect(mergeAdjacentMath(r'$a$ $b$'), r'$a b$');
    expect(mergeAdjacentMath(r'$\frac{a$ $b}$'), r'$\frac{a$ $b}$');
    expect(mergeAdjacentMath(r'$a}$ $b$'), r'$a}$ $b$');
    expect(mergeAdjacentMath(r'$\begin{cases}a$ $\end{cases}$'),
        r'$\begin{cases}a$ $\end{cases}$');
    expect(mergeAdjacentMath(r'$\begin{cases}a\end{cases}$ $b$'),
        r'$\begin{cases}a\end{cases} b$');
  });

  test('toPlain runs on braces alone and keeps image markers (D10)', () {
    expect(toPlain('1{,}000'), '1,000');
    expect(toPlain('{{IMAGE:59_1}} then \$x^2\$'), '{{IMAGE:59_1}} then x²');
    expect(toPlain('{{IMAGE:a_b}}'), '{{IMAGE:a_b}}');
    expect(toPlain('plain'), 'plain');
  });

  test('control chars inside math are audited and repaired (D11)', () {
    expect(auditKinds('\$x \nightarrow y\$'), ['control_char']);
    expect(auditKinds('x \nightarrow y'), isEmpty); // prose: ambiguous, kept
    expect(repair('\$x \nightarrow y\$'), r'$x \rightarrow y$');
    expect(repair('x \nightarrow y'), 'x \nightarrow y');
    // LF + `u`: only `\nu` fits, so it is restored; the audit's 3-letter
    // minimum after a newline keeps it silent.
    // Fewer than three letters after the newline: not restored (R7).
    expect(repair('\$a \nu b\$'), '\$a \nu b\$');
    expect(repair('\$a \tau b\$'), r'$a \tau b$'); // `tau` is in the narrow set
    expect(repair('\$\no'), '\$\no'); // no closer after it
    expect(auditKinds('\$\nabc'),
        ['unbalanced_dollar']); // no closer: not "inside"
    expect(auditKinds('\$a \nu b\$'), isEmpty);
    expect(repair('\$a \tau b\$'), r'$a \tau b$'); // only `\tau` fits
    expect(auditKinds('\$a \tau b\$'), ['control_char']);
    expect(repair('\$a \x0b b\$'), r'$a  b$'); // VT is not one of the three
  });

  test('stash tokens are private-use only and restored in reverse (F1, F2)',
      () {
    expect(canonicalize('{{IMAGE:10}} and IMG_10 x_1'),
        r'{{IMAGE:10}} and IMG_10 $x_1$');
    expect(canonicalize('{{IMAGE:x}} gs://b/{{IMAGE:x}}/a_b.png'),
        '{{IMAGE:x}} gs://b/{{IMAGE:x}}/a_b.png');
    expect(canonicalize(r'see https://a/b_c.png$x_1$'),
        r'see https://a/b_c.png$x_1$');
    expect(canonicalize(r'see https://a/b_c.png $x_1$'),
        r'see https://a/b_c.png $x_1$');
  });

  test(
      'pure-math wrapping needs a real command and no foreign-script word (F3)',
      () {
    expect(canonicalize(r'\\cs 5'), r'\\cs 5');
    expect(canonicalize(r'\alpha 5'), r'$\alpha 5$');
    expect(canonicalize(r'यह \alpha कण है'), r'यह \alpha कण है');
    expect(fix(r'यह \alpha कण है'), r'यह $\alpha$ कण है');
  });

  test('class names are identifiers (F4)', () {
    expect(canonicalize('class 10_A and 6_B and 12_PCM'),
        'class 10_A and 6_B and 12_PCM');
    expect(canonicalize('10_ABCDE'), r'$10_ABCDE$');
    expect(canonicalize('x_A'), r'$x_A$');
  });

  test('math mask comes from the tokenizer (R1)', () {
    expect(mathMask(r'a $b$ c'),
        [false, false, true, true, true, false, false, false]);
    expect(mathRanges(r'a $b$ $$c$$'), [(2, 5, false), (6, 11, true)]);
    expect(convertCombiningVec('\$\$x⃗\$\$'), r'$$\vec{x}$$');
    expect(canonicalize('\$\$x⃗\$\$'), r'$$\vec{x}$$');
    expect(auditKinds(r'$$π$$ and \$5 π'), ['bare_unicode_math']);
    // Linear, not quadratic: a long Greek prose line stays fast.
    final long = List.filled(2000, 'α β γ π θ ').join();
    final sw = Stopwatch()..start();
    expect(canonicalize(long), isNotEmpty);
    expect(sw.elapsedMilliseconds, lessThan(2000));
  });

  test('collapse, identifier braces and short-string bails (R3)', () {
    expect(canonicalize(r'\\frac{1}{2}'), r'$\frac{1}{2}$');
    expect(canonicalize(r'a \\\frac{1}{2}'),
        r'a \\$\frac{1}{2}$'); // odd run: line break, then the command wrapped on its own
    // mhchem collapses too; the short pure-math string is then wrapped whole.
    expect(canonicalize(r'\\ce{H2O} x'), r'$\ce{H2O} x$');
    expect(kCollapsibleCommands, containsAll(['frac', 'ce', 'pu']));
    expect(canonicalize(r'$q_001_easy_2026$ and $x^10$'),
        r'$q_001_easy_2026$ and $x^{10}$');
    expect(
        canonicalize(r'\frac and \alpha $'), r'\frac and \alpha $'); // odd `$`
    // A missing argument (`\frac` alone) stops the whole-string wrap; the
    // bare `\alpha` is `fix`'s job (`wrapBareSymbolCommands`), not this one.
    expect(canonicalize(r'\alpha \frac'), r'\alpha \frac');
    expect(canonicalize(r'\alpha \beta'), r'$\alpha \beta$');
    // New stop words: `we`/`you` make the string prose, so it is not wrapped
    // whole (the bare `\alpha` is wrapped by `fix`).
    expect(canonicalize(r'we \alpha you'), r'we \alpha you');
    expect(fix(r'we \alpha you'), r'we $\alpha$ you');
  });

  test('currency closer and prose escapes (R4)', () {
    expect(escapeCurrency(r'$1$$\gamma$'), r'$1$$\gamma$');
    expect(normalize(r'Given\nu = 5 cm'), 'Given\nu = 5 cm');
    expect(normalize(r'a \neq b'), r'a \neq b');
    expect(kProseEscapeCommands, isNot(contains('nu')));
  });

  test('mojibake: NBSP, entity loop, C1 and surrogates (R6)', () {
    expect(fixMojibakeTable('a b'), 'a b');
    expect(fixMojibakeTable('&amp;amp; &amp;lt;'), '& <');
    expect(fixMojibakeTable('x\u0085yé'), 'xyé');
    expect(fixMojibakeTable('a\ud800bé'), 'abé');
    expect(
        fixMojibakeTable('\u{1F600}é'), '\u{1F600}é'); // a real pair survives
    expect(kMojibakeTable['Ï€'], 'π');
    expect(kMojibakeTable.length, greaterThan(150)); // generated readings
  });

  test('toPlain keeps KaTeX names, guards depth, speaks nested fractions (R8)',
      () {
    expect(toPlain(r'$\neg p$'), '¬ p'); // the space after a command is kept
    expect(toPlain(r'$\intercal$'), '⊺'); // now in kLatexCmdMap
    expect(toPlain(r'$\Bumpeq$'), 'Bumpeq'); // a KaTeX name outside the map
    expect(toPlain(r'$\colonN$'), ':N');
    expect(
        toPlain(r'$\frac{\frac{a}{b}}{c}$', style: 'tts'), '(a over b) over c');
    expect(toPlain(r'$\frac{a}{b}$', style: 'tts'), 'a over b');
    expect(toPlain(r'$x^{20}$', style: 'tts'), 'x to the power 20');
    expect(toPlain(r'$x^2 y^{3}$', style: 'tts'), 'x squared y cubed');
    expect(toPlain(r'$\pmatrix$', style: 'tts'), 'pmatrix');
    final deep = '${'{' * 600}x${'}' * 600}';
    expect(toPlain('\$$deep\$'), 'x');
    expect(toPlain(r'$\frac{a}{b}$'), '(a)/(b)'); // the guard resets
  });

  test('audit no longer whitelists the model emissions (R9)', () {
    expect(auditKinds(r'$\textmu$'), ['unsupported_command']);
    expect(auditKinds(r'$\ce{H2O}$'), isEmpty);
    expect(kAuditExtraAllowedCommands, {'ce', 'pu'});
  });

  test('wrapUnicodeScripts, escapeTextSpecials and no-separator merge (R10)',
      () {
    expect(wrapUnicodeScripts('10⁻³ and mc² and x₁ and 2.5⁴'),
        r'$10^{-3}$ and $mc^{2}$ and $x_{1}$ and $2.5^{4}$');
    expect(
        wrapUnicodeScripts(r'$x²$ and \x² and {y₁}'), r'$x²$ and \x² and {y₁}');
    expect(wrapUnicodeScripts('H₂O'),
        r'$H_{2}$O'); // chemistry runs first in `fix`
    expect(fix('H₂O and mc²'), r'$\text{H}_{2}\text{O}$ and $mc^{2}$');
    expect(escapeTextSpecials(r'$50%$ and 50% and $\text{cost $5}$'),
        r'$50\%$ and 50% and $\text{cost \$5}$');
    expect(escapeTextSpecials(r'$a \% b$'), r'$a \% b$');
    expect(mergeAdjacentMath(r'$1$$\gamma$'), r'$1 \gamma$');
    expect(mergeAdjacentMath(r'$a$$b$ $c$'), r'$a b c$');
    expect(fix(r'$1$$\gamma$ $2$'), r'$1 \gamma 2$');
  });

  test('exported tables are populated and versioned', () {
    expect(kVersion, '1.1.0');
    expect(kKatexCommands, contains('frac'));
    expect(kJsonWhitespaceCollisionCommands, contains('nu'));
    expect(kLatexCommandsBehindJsonEscapes, contains('theta'));
    expect(kLatexCommandsBehindJsonEscapes, isNot(contains('nu')));
    expect(kUnicodeMath['\u03c0'], r'\pi');
    expect(kWrappableBareChars, contains('\u03c0'));
    expect(kHomoglyphs['\u00b5'], '\u03bc');
    expect(kCollapseCommands, contains('frac'));
    expect(kStructuralCommands, contains('sqrt'));
    expect(kLatexCmdMap['alpha'], '\u03b1');
    expect(kMojibakeTable['\u00cf\u20ac'], '\u03c0');
    expect(kNonContentKeys, contains('url'));
    expect(kNonContentKeySuffixes, contains('_id'));
  });
}
