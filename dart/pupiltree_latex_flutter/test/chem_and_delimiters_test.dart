import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import 'package:pupiltree_latex/pupiltree_latex.dart';
import 'package:pupiltree_latex_flutter/pupiltree_latex_flutter.dart';

Widget _app(Widget child) =>
    MaterialApp(home: Scaffold(body: SingleChildScrollView(child: child)));

/// Pump [input] and return the Math widgets drawn (every one parsed, none
/// replaced by the grey-source fallback).
Future<List<Math>> _render(WidgetTester tester, String input) async {
  await tester.pumpWidget(_app(MathText(input)));
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull, reason: input);
  expect(find.byType(MathSourceFallback), findsNothing, reason: input);
  final maths = tester.widgetList<Math>(find.byType(Math)).toList();
  for (final m in maths) {
    expect(m.parseError, isNull, reason: input);
  }
  return maths;
}

void main() {
  group('ceToLatex', () {
    test('formulas, coefficients, charges and arrows', () {
      expect(ceToLatex(r'\ce{H2O}'), r'{\mathrm{H}_{2}\mathrm{O}}');
      expect(
        ceToLatex(r'\ce{2H2 + O2 -> 2H2O}'),
        r'{2\mathrm{H}_{2} + \mathrm{O}_{2} \rightarrow 2\mathrm{H}_{2}\mathrm{O}}',
      );
      expect(ceToLatex(r'\ce{SO4^2-}'), r'{\mathrm{SO}_{4}^{2-}}');
      expect(ceToLatex(r'\ce{SO4^{2-}}'), r'{\mathrm{SO}_{4}^{2-}}');
      expect(ceToLatex(r'\ce{Fe^3+}'), r'{\mathrm{Fe}^{3+}}');
      expect(ceToLatex(r'\ce{NH4^+}'), r'{\mathrm{NH}_{4}^{+}}');
      expect(
        ceToLatex(r'\ce{Na+ + Cl- -> NaCl}'),
        r'{\mathrm{Na}^{+} + \mathrm{Cl}^{-} \rightarrow \mathrm{NaCl}}',
      );
      expect(
        ceToLatex(r'\ce{N2 + 3H2 <=> 2NH3}'),
        r'{\mathrm{N}_{2} + 3\mathrm{H}_{2} \rightleftharpoons 2\mathrm{NH}_{3}}',
      );
      expect(ceToLatex(r'\ce{A <- B}'), r'{\mathrm{A} \leftarrow \mathrm{B}}');
      expect(
        ceToLatex(r'\ce{A <-> B}'),
        r'{\mathrm{A} \leftrightarrow \mathrm{B}}',
      );
    });

    test('arrow labels, states, hydrates, parentheses', () {
      expect(
        ceToLatex(r'\ce{CaCO3 ->[\Delta] CaO + CO2}'),
        r'{\mathrm{CaCO}_{3} \xrightarrow{\Delta} \mathrm{CaO} + \mathrm{CO}_{2}}',
      );
      expect(
        ceToLatex(r'\ce{A ->[heat][-H2O] B}'),
        r'{\mathrm{A} \xrightarrow[- \mathrm{H}_{2}\mathrm{O}]{\mathrm{heat}} \mathrm{B}}',
      );
      expect(
        ceToLatex(r'\ce{NaCl(aq)}'),
        r'{\mathrm{NaCl}(\mathrm{aq})}',
      );
      expect(
        ceToLatex(r'\ce{H2O(l) -> H2O(g)}'),
        r'{\mathrm{H}_{2}\mathrm{O}(\mathrm{l}) \rightarrow \mathrm{H}_{2}\mathrm{O}(\mathrm{g})}',
      );
      expect(
        ceToLatex(r'\ce{CuSO4*5H2O}'),
        r'{\mathrm{CuSO}_{4} \cdot 5\mathrm{H}_{2}\mathrm{O}}',
      );
      expect(
        ceToLatex(r'\ce{CuSO4·5H2O}'),
        r'{\mathrm{CuSO}_{4} \cdot 5\mathrm{H}_{2}\mathrm{O}}',
      );
      expect(
        ceToLatex(r'\ce{Ca(OH)2}'),
        r'{\mathrm{Ca}(\mathrm{OH})_{2}}',
      );
      expect(
        ceToLatex(r'\ce{[Cu(NH3)4]^2+}'),
        r'{[\mathrm{Cu}(\mathrm{NH}_{3})_{4}]^{2+}}',
      );
    });

    test('pu quantities', () {
      expect(ceToLatex(r'\pu{3e8 m/s}'), r'{3\times10^{8}\ \mathrm{m/s}}');
      expect(
        ceToLatex(r'\pu{8.314 J K^-1 mol^-1}'),
        r'{8.314\ \mathrm{J}\ \mathrm{K}^{-1}\ \mathrm{mol}^{-1}}',
      );
      expect(ceToLatex(r'\pu{25 °C}'), r'{25\ {}^{\circ}\mathrm{C}}');
      expect(ceToLatex(r'\pu{1.6e-19 C}'), r'{1.6\times10^{-19}\ \mathrm{C}}');
    });

    test('the rest of the formula is untouched', () {
      expect(
        ceToLatex(r'x = \ce{H2O} + y'),
        r'x = {\mathrm{H}_{2}\mathrm{O}} + y',
      );
      expect(ceToLatex(r'\frac{1}{2}'), r'\frac{1}{2}');
      expect(ceToLatex(r'\cex{H2}'), r'\cex{H2}');
    });

    test('notation outside the grammar is left as written', () {
      for (final s in [
        r'\ce{H2O',
        r'\ce{}',
        r'\ce{A ~ B}',
        r'\ce{A ->[x B}',
        r'\pu{m/s 3}',
        r'\pu{3 m/s!}',
      ]) {
        expect(ceToLatex(s), s, reason: s);
      }
    });
  });

  group('mhchem renders in Flutter (no grey source)', () {
    for (final input in [
      r'$\ce{H2O}$',
      r'$\ce{2H2 + O2 -> 2H2O}$',
      r'$\ce{SO4^2-}$',
      r'$\ce{N2 + 3H2 <=> 2NH3}$',
      r'$\pu{3e8 m/s}$',
      r'$\ce{Fe^3+ + e- -> Fe^2+}$',
      r'$\ce{CaCO3 ->[\Delta] CaO + CO2}$',
      r'$\ce{CuSO4*5H2O}$',
      r'$\ce{[Cu(NH3)4]^2+}$',
      r'$\ce{A <- B <-> C}$',
      r'$\pu{8.314 J K^-1 mol^-1}$',
      r'Water is $\ce{H2O}$ and speed $\pu{3e8 m/s}$.',
    ]) {
      testWidgets(input, (tester) async {
        final maths = await _render(tester, input);
        expect(maths, isNotEmpty, reason: input);
      });
    }

    testWidgets('an untranslatable \\ce still falls back to its source', (
      tester,
    ) async {
      await tester.pumpWidget(_app(const MathText(r'$\ce{A ~ B}$')));
      await tester.pumpAndSettle();
      expect(find.byType(MathSourceFallback), findsOneWidget);
    });
  });

  group('toBracketDelimiters follows segment()', () {
    test('only the spans segment calls math become brackets', () {
      expect(toBracketDelimiters(r'10$ and 20$ later'), r'10$ and 20$ later');
      expect(toBracketDelimiters(r'$ x $'), r'$ x $');
      expect(
        toBracketDelimiters(r'$\frac{1}{2}$2 apples'),
        r'$\frac{1}{2}$2 apples',
      );
      expect(toBracketDelimiters(r'$x$²'), r'$x$²');
      expect(
        toBracketDelimiters(r'Cost \$5 and $x$ and $$y$$'),
        r'Cost $5 and \(x\) and \[y\]',
      );
    });

    test('bracket count equals segment math count', () {
      for (final input in [
        r'10$ and 20$ later',
        r'$ x $',
        r'$\frac{1}{2}$2 apples',
        r'a $x$ b $$y$$ c \$5 $z$',
        r'$a$ * $b*c$',
        r'$\mu$₀ and $x$²',
      ]) {
        final math = segment(input).where((s) => s.isMath).length;
        final out = toBracketDelimiters(input);
        final brackets = RegExp(r'\\\(|\\\[').allMatches(out).length;
        expect(brackets, math, reason: input);
      }
    });

    testWidgets('trailing dollars are not math', (tester) async {
      await tester.pumpWidget(_app(const MathText(r'10$ and 20$ later')));
      await tester.pumpAndSettle();
      expect(find.byType(Math), findsNothing);
      expect(
        find.textContaining(r'10$ and 20$ later', findRichText: true),
        findsWidgets,
      );
    });

    testWidgets(r'a spaced $ x $ is not math', (tester) async {
      await tester.pumpWidget(
        _app(const MathText(r'$ x $', mode: MathTextMode.normalize)),
      );
      await tester.pumpAndSettle();
      expect(find.byType(Math), findsNothing);
    });

    testWidgets('Flutter draws exactly the math segment() finds', (
      tester,
    ) async {
      for (final input in [
        r'10$ and 20$ later',
        r'$\frac{1}{2}$2 apples',
        r'Pay $5000 for $\frac14$ share',
        r'$a$ and $$b$$ and \$3',
      ]) {
        final shown = fix(input);
        final expected = segment(shown).where((s) => s.isMath).length;
        await tester.pumpWidget(_app(MathText(input)));
        await tester.pumpAndSettle();
        expect(find.byType(Math), findsNWidgets(expected), reason: input);
      }
    });
  });

  group('emphasis never splits a formula', () {
    testWidgets(r'$a$ * $b*c$ draws both formulas', (tester) async {
      final maths = await _render(tester, r'$a$ * $b*c$');
      expect(maths, hasLength(2));
      expect(find.textContaining('*', findRichText: true), findsWidgets);
    });

    testWidgets('italics and bold around prose still work', (tester) async {
      await tester.pumpWidget(
        _app(const MathText(r'*note* and **key** with $x^2$')),
      );
      await tester.pumpAndSettle();
      expect(find.byType(Math), findsOneWidget);
      final spans = <TextSpan>[];
      for (final rt in tester.widgetList<RichText>(find.byType(RichText))) {
        rt.text.visitChildren((s) {
          if (s is TextSpan) spans.add(s);
          return true;
        });
      }
      expect(
        spans.any(
          (s) => s.text == 'note' && s.style?.fontStyle == FontStyle.italic,
        ),
        isTrue,
      );
      expect(
        spans.any(
          (s) => s.text == 'key' && s.style?.fontWeight == FontWeight.bold,
        ),
        isTrue,
      );
    });

    testWidgets('a formula inside italics is still drawn', (tester) async {
      final maths = await _render(tester, r'*see $x^2$ here*');
      expect(maths, hasLength(1));
    });

    testWidgets('bold never closes inside a formula', (tester) async {
      final maths = await _render(tester, r'$a$ ** $b**c$');
      expect(maths, hasLength(2));
    });

    testWidgets('the widget stays on the plusparse pipeline', (tester) async {
      await tester.pumpWidget(_app(const MathText(r'$a$ * $b*c$')));
      await tester.pumpAndSettle();
      final md = tester.widget<GptMarkdown>(find.byType(GptMarkdown));
      // ignore: deprecated_member_use
      expect(md.inlineComponents, isNull);
      // ignore: deprecated_member_use
      expect(md.components, isNull);
      expect(md.inlinePatterns, [inlineMathPattern]);
    });
  });
}
