import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import 'package:pupiltree_latex_flutter/pupiltree_latex_flutter.dart';

Widget _app(Widget child) =>
    MaterialApp(home: Scaffold(body: SingleChildScrollView(child: child)));

void main() {
  group('toBracketDelimiters', () {
    test('rewrites spans and unescapes prose dollars only', () {
      expect(
        toBracketDelimiters(r'Cost \$5 (about \$6) and $x^2$ then $$a$$'),
        r'Cost $5 (about $6) and \(x^2\) then \[a\]',
      );
      expect(toBracketDelimiters(r'$\$5 + x$'), r'\(\$5 + x\)');
      expect(toBracketDelimiters('no dollars'), 'no dollars');
    });
  });

  group('MathText', () {
    testWidgets('plain prose takes the Text fast path', (tester) async {
      await tester.pumpWidget(
        _app(const MathText('Water boils at 100 degrees.')),
      );
      expect(find.byType(GptMarkdown), findsNothing);
      expect(find.text('Water boils at 100 degrees.'), findsOneWidget);
      expect(
        const MathText('  Water boils at 100 degrees. ').processed,
        'Water boils at 100 degrees.',
      );
    });

    testWidgets('a formula renders through a Math widget', (tester) async {
      await tester.pumpWidget(_app(const MathText(r'Area is $\frac{1}{2}bh$')));
      await tester.pumpAndSettle();
      expect(find.byType(GptMarkdown), findsOneWidget);
      expect(find.byType(Math), findsOneWidget);
      expect(find.byType(MathSourceFallback), findsNothing);
    });

    testWidgets('legacy \\(…\\) and control-char damage are normalized first', (
      tester,
    ) async {
      await tester.pumpWidget(
        _app(const MathText('\\(\theta\\) and \\(\x0crac{1}{2}\\)')),
      );
      await tester.pumpAndSettle();
      expect(find.byType(Math), findsNWidgets(2));
    });

    testWidgets('a broken formula shows its source in grey italic', (
      tester,
    ) async {
      // `$\frac{1}{$` is not a span at all (the closer search is
      // brace-aware, as in KaTeX auto-render); `\left(` without `\right` is
      // a span that fails to parse.
      await tester.pumpWidget(_app(const MathText(r'Bad: $\left( x$')));
      await tester.pumpAndSettle();
      final fallback = tester.widget<MathSourceFallback>(
        find.byType(MathSourceFallback),
      );
      expect(fallback.source, r'\left( x');
      final text = tester.widget<Text>(
        find.descendant(
          of: find.byType(MathSourceFallback),
          matching: find.byType(Text),
        ),
      );
      expect(text.style?.color, Colors.grey);
      expect(text.style?.fontStyle, FontStyle.italic);
    });

    testWidgets('currency stays text', (tester) async {
      // `normalize` escapes both dollars, so the string carries `\$` and
      // takes the markdown path; nothing in it is math and the dollars are
      // shown as written.
      const widget = MathText(r'It costs $5 and $10 today.');
      expect(widget.processed, r'It costs $5 and $10 today.');
      await tester.pumpWidget(_app(widget));
      await tester.pumpAndSettle();
      expect(find.byType(Math), findsNothing);
      expect(find.byType(MathSourceFallback), findsNothing);
      expect(
        find.textContaining(r'$5 and $10', findRichText: true),
        findsOneWidget,
      );
    });

    testWidgets('currency next to a real formula keeps the formula', (
      tester,
    ) async {
      await tester.pumpWidget(
        _app(const MathText(r'Pay $5000 for $\frac14$ share')),
      );
      await tester.pumpAndSettle();
      expect(find.byType(Math), findsOneWidget);
      expect(find.textContaining(r'$5000', findRichText: true), findsOneWidget);
    });

    testWidgets(
      'the default mode is fix: bare π is wrapped, normalize mode is not',
      (tester) async {
        const fixed = MathText('The ratio is π here');
        const plain = MathText(
          'The ratio is π here',
          mode: MathTextMode.normalize,
        );
        // ignore: deprecated_member_use_from_same_package
        const legacy = MathText('The ratio is π here', canonical: true);
        expect(fixed.processed, r'The ratio is \(\pi\) here');
        expect(legacy.processed, fixed.processed);
        expect(plain.processed, 'The ratio is π here');
        await tester.pumpWidget(_app(fixed));
        await tester.pumpAndSettle();
        expect(find.byType(Math), findsOneWidget);
        await tester.pumpWidget(_app(plain));
        await tester.pumpAndSettle();
        expect(find.byType(Math), findsNothing);
      },
    );

    testWidgets('Unicode chemistry renders as math', (tester) async {
      const water = MathText('Water is H₂O');
      expect(water.processed, r'Water is \(\text{H}_{2}\text{O}\)');
      await tester.pumpWidget(_app(water));
      await tester.pumpAndSettle();
      expect(find.byType(Math), findsOneWidget);
      expect(find.byType(MathSourceFallback), findsNothing);

      const iron = MathText('Fe³⁺ is an ion');
      expect(iron.processed, r'\(\text{Fe}^{3+}\) is an ion');
      await tester.pumpWidget(_app(iron));
      await tester.pumpAndSettle();
      expect(find.byType(Math), findsOneWidget);
      expect(find.byType(MathSourceFallback), findsNothing);
    });

    testWidgets('style, alignment and maxLines reach the fast path', (
      tester,
    ) async {
      await tester.pumpWidget(
        _app(
          const MathText(
            'plain',
            style: TextStyle(fontSize: 22),
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      );
      final text = tester.widget<Text>(find.text('plain'));
      expect(text.style?.fontSize, 22);
      expect(text.textAlign, TextAlign.center);
      expect(text.maxLines, 2);
      expect(text.overflow, TextOverflow.ellipsis);
    });
  });
}
