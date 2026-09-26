// Audit round 2 (2026-09-26): invariants the corpus cases cannot state.
// Mirror of python/tests/test_audit2.py (the ftfy variants do not apply:
// Dart has the table engine only).
import 'package:pupiltree_latex/pupiltree_latex.dart';
import 'package:test/test.dart';

const auditInputs = [
  'The product 3×4×5=60 is easy.',
  'If x≤5 then y≥2.',
  'Find 3.14×10⁻⁵ in standard form.',
  r'3×10⁸ m/s and $E=mc^2$',
  '6.022×10²³ particles',
  '6.022 × 10²³ mol⁻¹',
  'CuSO₄·5H₂O',
  'Take n→∞ and x→0.',
  'Given ε₀ and μ₀, find c.',
  'λ₁, λ₂ are eigenvalues.',
  'σ₁₂',
  'µ₀ = 4π × 10⁻⁷ T·m/A',
  r'x\leq5 holds',
  r'x$\leq$5 holds',
  r'Use \pi2 here',
  r'2×10 and 3 \times4',
  r'\alpha_1 and \beta^2',
  r'\\\frac{1}{2}',
  r'\\$\frac{1}{2}$',
  r'$ H₂',
  r'$H₂O',
  r'$×5',
  r'$\leq 5',
  r'Solve $ x^2 + 1 = 0 $ now',
  r'Let $ \theta = 30° $ here',
  r'I paid $ 5 and got $ 3 back',
  'm/s² and per mm³ and x²5',
  'यदि x≤५ है',
  r'\sqrt{2}3 and \frac{1}{2}4',
  'â‚¬5 and Â£3',
  'ππ and Ï€Ï€',
  '2.5583 and 1,00,000 and ₹2,50,000 and 9:3:3:1 and 45°',
];

final _cmd = RegExp(r'\\([A-Za-z]+)');
final _doubleDollar = RegExp(r'(?<!\\)\$\$');

void main() {
  group('fix on the audit inputs', () {
    for (final s in auditInputs) {
      test('is idempotent: $s', () {
        final once = fix(s);
        expect(fix(once), once);
      });

      test('never creates display math: $s', () {
        final out = fix(s);
        if (s.contains(r'$$') || s.contains(r'\[')) return;
        expect(segment(out).any((seg) => seg.display), isFalse, reason: out);
        expect(_doubleDollar.hasMatch(out), isFalse, reason: out);
      });

      test('leaves no KaTeX command beside a dollar in prose: $s', () {
        for (final seg in segment(fix(s))) {
          if (seg.isMath) continue;
          final raw = seg.raw;
          for (final m in _cmd.allMatches(raw)) {
            if (!kKatexCommands.contains(m[1])) continue;
            final before = m.start > 0 ? raw[m.start - 1] : '';
            final after = m.end < raw.length ? raw[m.end] : '';
            expect(before, isNot(r'$'), reason: '$s → $raw');
            expect(after, isNot(r'$'), reason: '$s → $raw');
          }
        }
      });
    }
  });

  test('prose digits are byte-identical', () {
    const s = '2.5583 and 1,00,000 and ₹2,50,000 and 9:3:3:1 and 45°';
    expect(fix(s), s);
    expect(canonicalize(s), s);
  });

  test('currency mojibake', () {
    expect(fix('â‚¬5'), '€5');
    expect(canonicalize('â‚¬5'), '€5');
    expect(fix('Price Â£5, â‚¹500, Â¥3'), 'Price £5, ₹500, ¥3');
    expect(fix('â‚¬5 and â‚¹2,50,000'), isNot(contains('neg')));
  });

  test('repeated Greek is kept', () {
    expect(fix('ππ'), r'$\pi\pi$');
    expect(fix('ωω'), r'$\omega\omega$');
    expect(fix('Ï€Ï€'), r'$\pi\pi$');
    expect(normalize('αα and λλ'), 'αα and λλ');
    expect(fixMojibakeTable('√√2'), '√√2');
  });

  test('the table still collapses a pair made by a context rule', () {
    // `Ï` next to a real π is mojibake of the same letter: one π, not two.
    expect(fixMojibakeTable('2Ïπ'), '2π');
  });

  test('fixDeep and canonicalizeDeep skip taxonomy lists', () {
    final doc = {
      'tags': ['x_1', 'E_n'],
      'labels': ['a^2'],
      'keywords': ['H₂O'],
      'text': 'x_1',
    };
    final out = fixDeep(doc) as Map;
    expect(out['tags'], ['x_1', 'E_n']);
    expect(out['labels'], ['a^2']);
    expect(out['keywords'], ['H₂O']);
    expect(out['text'], r'$x_1$');
    expect((canonicalizeDeep(doc) as Map)['tags'], ['x_1', 'E_n']);
    expect(isNonContentKey('Tags'), isTrue);
    expect(isNonContentKey('keywords'), isTrue);
  });
}
