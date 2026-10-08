// 1.4.0 Group B behaviour that the corpus cannot express (deep walks,
// positions, options). Translation of python/tests/test_v140_b.py.

import 'package:pupiltree_latex/pupiltree_latex.dart';
import 'package:test/test.dart';

const narrative = ['story_script', 'transcript', 'script@transcript'];

void main() {
  test('fixDeep: narrative keys get repair only', () {
    final doc = {
      'question': 'Area = πr²',
      'story_script': 'Then π \x0Crac{1}{2} and H₂O',
      'podcast': {'transcript': 'x² is πr', 'script': 'x² here'},
      'lesson': {'script': 'x² here'},
      '_id': 'q_1',
    };
    final out = fixDeep(doc, narrativeKeys: narrative) as Map;
    expect(out['question'], r'Area = $\pi r^{2}$');
    expect(out['story_script'], r'Then π \frac{1}{2} and H₂O');
    expect((out['podcast'] as Map)['transcript'], 'x² is πr');
    expect((out['podcast'] as Map)['script'], 'x² here');
    expect((out['lesson'] as Map)['script'], r'$x^{2}$ here');
    expect(out['_id'], 'q_1');
  });

  test('fixDeep without narrative keys is unchanged behaviour', () {
    final doc = {
      'transcript': 'x²',
      'items': [
        'π',
        {'story_script': 'π'},
      ],
    };
    expect(fixDeep(doc), {
      'transcript': r'$x^{2}$',
      'items': [
        r'$\pi$',
        {'story_script': r'$\pi$'},
      ],
    });
  });

  test('fixDeep: narrative lists and nested values', () {
    final doc = {
      'story_sections': [
        {'text': 'π \x0Crac{1}{2}'},
        'x²',
      ],
    };
    expect(fixDeep(doc, narrativeKeys: ['story_sections']), {
      'story_sections': [
        {'text': r'π \frac{1}{2}'},
        'x²',
      ],
    });
  });

  test('canonicalizeDeep: narrative keys', () {
    final doc = {'q': 'π', 'transcript': 'π', 'script': 'π'};
    expect(canonicalizeDeep(doc, narrativeKeys: narrative), {
      'q': r'$\pi$',
      'transcript': 'π',
      'script': 'π',
    });
  });

  test('currencySpans: positions', () {
    const text = r'Rs $5 and \$10.50, ₹ 45,00,000 and $x^2$';
    final spans = currencySpans(text);
    expect([for (final s in spans) s.text], [r'$5', r'\$10.50', '₹ 45,00,000']);
    for (final s in spans) {
      expect(text.substring(s.start, s.end), s.text);
    }
    expect(currencySpans(''), isEmpty);
  });

  test('needsFix: the chemistry option', () {
    expect(needsFix(''), isFalse);
    expect(needsFix(r'\ce{H2O}'), isTrue);
    expect(needsFix(r'\ce{H2O}', chemistry: false), isFalse);
  });

  test('normalizeOptionText: idempotent', () {
    expect(normalizeOptionText(''), '');
    for (final text in [
      r'$\text{H_{2}O}$',
      r'$50 \text{ %}$',
      r'\text{rises} when $x > 0$',
    ]) {
      final once = normalizeOptionText(text);
      expect(normalizeOptionText(once), once);
    }
  });

  test('normalize: code spans are off by default', () {
    expect(normalize('`x^2`'), '`x^2`');
    expect(normalize('`x^2`', codeSpansAsMath: true), r'$x^2$');
  });

  test('loadsModelJson: lenient flag', () {
    expect(loadsModelJson(r'{"a": "\q"}'), {'a': r'\q'});
    expect(loadsModelJson(r'{"a": "\q"}', lenient: true), {'a': r'\q'});
    expect(() => loadsModelJson(r'{"a": "\q"}', lenient: false),
        throwsFormatException);
    expect(() => loadsModelJson('{"a": "x\ny"}', lenient: false),
        throwsFormatException);
  });

  test('repair: currency-aware span', () {
    const text = 'costs \$5.\nangle ABC costs \$10';
    expect(repair(text), text);
    expect(repair(text, guessWhitespace: false), text);
  });

  test('lost_escape is not an error kind', () {
    expect(allKinds, contains('lost_escape'));
    expect(isError(['lost_escape']), isFalse);
    expect(isError(auditKinds('a\x7Fb')), isTrue);
  });

  test('fix is idempotent on the new repairs', () {
    for (final text in [
      r'$x}$',
      r'${{x}}$ and $\fre{a}{b}$',
      r'What is $x + 1',
      r'\$1.56 \text{ m}$',
      r'$\AA$ and \text{\AA}',
      'costs \$5.\nangle ABC costs \$10',
    ]) {
      final once = fix(text);
      expect(fix(once), once, reason: text);
    }
  });
}
