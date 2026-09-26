// Audit round 3 (2026-09-26): invariants the corpus cases cannot state.
// Port of python/tests/test_audit3.py.
//
// - Greek words (`2πr`, `fλ`, `Δx`) become one span; units, Greek prose,
//   long Latin words and identifiers keep their earlier shape.
// - `canonicalize` closes the last group of a span that was never closed
//   (`$\frac{1}{2$`), never guessing an empty argument, and `audit` is clean
//   afterwards.
// - Both rules are idempotent and never move or drop a digit.
@TestOn('vm')
library;

import 'dart:convert';
import 'dart:io';

import 'package:pupiltree_latex/pupiltree_latex.dart';
import 'package:pupiltree_latex/src/unicode_math.dart' show greekWordAt;
import 'package:test/test.dart';

const greekWordInputs = [
  'Area = 2πr and πr²',
  'Circumference 2πr',
  'v = fλ',
  'E = hν',
  'Δx·Δp ≥ ħ/2',
  'ωt + φ',
  'ρL',
  '2πrh',
  'sin θ',
  'nλ = d sinθ',
  'ΔG = ΔH − TΔS',
  '2.5λ and ₹2π',
  'x≤2πr and 3×πr',
  'πr^2 and 2πr_1',
  'ΔH₂O',
  'e^{iπ}',
  r'Cost \$5π',
  'q_π and २π and πक',
];

// Units keep exactly the shape they had before audit round 3.
const units = {
  '5 µs': r'5 $\mu$s',
  '10 kΩ': r'10 k$\Omega$',
  '3 MΩ': r'3 M$\Omega$',
  '2 µm': r'2 $\mu$m',
  '5 µg': r'5 $\mu$g',
  '4 mΩ': r'4 m$\Omega$',
  'Ω·m': r'$\Omega\cdot$m',
  'J·s': r'J$\cdot$s',
  '10Ω': r'10$\Omega$',
  '5μs': r'5$\mu$s',
  '10kΩ': r'10k$\Omega$',
  '2 GΩ': r'2 G$\Omega$',
  '3 µF': r'3 $\mu$F',
  '1 μΩ': r'1 $\mu\Omega$',
  'kΩm': r'k$\Omega$m',
  '5 μm²': r'5 $\mu m^{2}$', // merged by mergeAdjacentMath, as before
};

const braceFixed = {
  r'$\frac{1}{2$': r'$\frac{1}{2}$',
  r'$x^{2$': r'$x^{2}$',
  r'$\sqrt{x+1$': r'$\sqrt{x+1}$',
  r'$x_{i$ and $\vec{F$': r'$x_{i}$ and $\vec{F}$',
  r'$\frac{a}{b$ and $y$': r'$\frac{a}{b}$ and $y$',
  // `$y$` is a span, so the text segment before it holds exactly one pair.
  r'$x^{2$ and $y$ and $z': r'$x^{2}$ and $y$ and $z',
};

const braceKept = [
  r'$\frac{1}{$',
  r'$\frac{$',
  r'$x^{$',
  r'$x^{2^$',
  r'$\frac{1}{\sqrt$',
  r'$\frac{\frac{1}{2$',
  r'$\left( x^{2$',
  r'$\begin{matrix} x^{2$',
  r'$a}{b$',
  r'$\{x$',
  r'$\frac{1}{2 $',
  r'$\frac{1}{2$5',
  r'$$\frac{1}{2$$',
  r'$x^{2$ and $z', // odd count of dollars on the line
];

const scriptGroupInputs = [
  'e^{iπ}',
  'e^{iπt}',
  'x_{α}',
  '10^{-3}μ',
  r'\frac{π}{2}',
  r'\sqrt{2π}',
  'sin^{2}θ',
  'a_{αβ} and e^{i×π}',
  r'\text{π} and \vec{α}',
  r'\frac{π} and x^{π',
  'the set {α, β}',
  'q_{π}_x',
];

const _scriptDigits = '⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉';
final _digit = RegExp(r'\p{Nd}', unicode: true);

/// Python `re.findall(r"\d", s.translate(_SUP))`.
List<String> digits(String s) {
  final b = StringBuffer();
  for (final r in s.runes) {
    final c = String.fromCharCode(r);
    final k = _scriptDigits.indexOf(c);
    b.write(k >= 0 ? '${k % 10}' : c);
  }
  return [for (final m in _digit.allMatches(b.toString())) m[0]!];
}

bool dollarInOpenGroup(String value) {
  var depth = 0;
  var i = 0;
  while (i < value.length) {
    final c = value[i];
    if (c == r'\') {
      i += 2;
      continue;
    }
    if (c == '{') {
      depth++;
    } else if (c == '}') {
      depth = depth - 1 < 0 ? 0 : depth - 1;
    } else if (c == r'$' && depth > 0) {
      return true;
    }
    i++;
  }
  return false;
}

List<String> allCorpusInputs() {
  final files = Directory('../../corpus')
      .listSync()
      .whereType<File>()
      .where((f) => f.path.endsWith('.json'))
      .toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  final out = <String>[];
  for (final f in files) {
    final data = jsonDecode(f.readAsStringSync()) as Map<String, Object?>;
    if (data['function'] == 'json_transport') continue;
    for (final c in (data['cases']! as List).cast<Map<String, Object?>>()) {
      final input = c['input'];
      if (input is String) out.add(input);
    }
  }
  return {...out, ...scriptGroupInputs}.toList();
}

void main() {
  group('idempotent and digits kept', () {
    for (final text in [
      ...greekWordInputs,
      ...units.keys,
      ...braceFixed.keys,
      ...scriptGroupInputs,
    ]) {
      test(text, () {
        final out = fix(text);
        expect(fix(out), out);
        expect(digits(out), digits(text));
      });
    }
  });

  group('units keep their shape', () {
    units.forEach((text, expected) {
      test(text, () => expect(fix(text), expected));
    });
  });

  test('Greek word spans', () {
    expect(fix('Circumference 2πr'), r'Circumference $2\pi r$');
    expect(fix('v = fλ'), r'v = $f\lambda$');
    expect(fix('E = hν'), r'E = $h\nu$');
    expect(fix('ωt + φ'), r'$\omega t$ + $\phi$');
    expect(fix('ρL'), r'$\rho L$');
    expect(fix('2πrh'), r'$2\pi rh$');
    expect(fix('sin θ'), r'sin $\theta$');
    expect(fix('Δx·Δp ≥ ħ/2'), r'$\Delta x\cdot\Delta p \geq \hbar$/2');
  });

  test('Greek word refusals', () {
    final spaced = RegExp(r'\\[A-Za-z]+ [A-Za-z]');
    for (final text in [
      'αβγtest',
      'Thetaα',
      'λmax',
      'sinθ',
      'λόγος',
      'Ελλάδα',
      'q_π'
    ]) {
      final out = fix(text);
      expect(spaced.hasMatch(out), isFalse, reason: '$text -> $out');
    }
    expect(greekWordAt('αβγtest', 0), isNull);
    expect(greekWordAt('λόγος', 0), isNull);
    expect(greekWordAt('x^iπ', 3), isNull);
    expect(greekWordAt('२π', 1), isNull);
    expect(greekWordAt('πक', 0), isNull);
    expect(greekWordAt('10 kΩ', 4), isNull);
    expect(greekWordAt('5μs', 1), isNull);
    expect(greekWordAt('ΔH₂O', 0), isNull);
    expect(greekWordAt('a 2πr b', 3), (2, 5));
    expect(greekWordAt('2.5λ', 3), (0, 4));
  });

  test('radical coefficient untouched', () {
    expect(fix('2√3'), r'2$\sqrt{3}$');
    expect(fix(r'2$\sqrt{3}$'), r'2$\sqrt{3}$');
  });

  group('unclosed group is closed', () {
    braceFixed.forEach((text, expected) {
      test(text, () {
        expect(canonicalize(text), expected);
        expect(fix(text), expected);
        // The trailing `$z` of one case is a real unbalanced dollar.
        expect(
          [
            for (final f in audit(expected))
              if (f.kind != 'unbalanced_dollar') f
          ],
          isEmpty,
        );
      });
    });
  });

  group('unclosed group kept when closing would guess', () {
    for (final text in braceKept) {
      test(text, () => expect(canonicalize(text), text));
    }
  });

  test('brace close is not a normalize or repair rule', () {
    expect(normalize(r'$\frac{1}{2$'), r'$\frac{1}{2$');
    expect(repair(r'$\frac{1}{2$'), r'$\frac{1}{2$');
  });

  test('fix never puts a dollar inside an open group of a math span', () {
    final bad = <String>[];
    for (final text in allCorpusInputs()) {
      final out = fix(text);
      // A span that was already in the input as written (Backend's
      // `$\text{VS} = $\frac{\text{CS}$}{R}$` is left alone on purpose) is
      // not something fix introduced.
      final before = {
        for (final s in segment(repair(text)))
          if (s.isMath) s.value,
      };
      for (final seg in segment(out)) {
        if (seg.isMath &&
            dollarInOpenGroup(seg.value) &&
            !before.contains(seg.value)) {
          bad.add('${jsonEncode(text)} -> ${jsonEncode(out)}');
        }
      }
    }
    expect(bad, isEmpty, reason: bad.join('\n'));
  });
}
