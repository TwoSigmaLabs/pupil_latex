/// Flutter adapter for `pupiltree_latex`: the [MathText] widget every
/// Pupiltree app renders math text with (CONTRACT §4).
///
/// Pipeline: `fix` ([MathTextMode.fix], the default) or `normalize`
/// ([MathTextMode.normalize]) → plain [Text] when `isPlainProse` → else
/// `$…$` / `$$…$$` → `\(…\)` / `\[…\]` with prose `\$` unescaped
/// ([toBracketDelimiters], built on `segment`) → [GptMarkdown] with
/// `useDollarSignsForLatex: false` and inline `\(…\)` claimed before
/// emphasis ([inlineMathPattern]), math drawn by flutter_math_fork with
/// `Strict.ignore` after `\ce{…}` / `\pu{…}` are translated ([ceToLatex];
/// there is no mhchem in Flutter). A formula
/// that fails to parse shows its source in grey italic, never a red box,
/// never nothing.
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import 'package:pupiltree_latex/pupiltree_latex.dart';

import 'src/chem_tex.dart';

export 'src/chem_tex.dart' show ceBodyToLatex, ceToLatex, puBodyToLatex;

/// Convert the math spans [segment] finds into `\(…\)` / `\[…\]` and turn
/// every prose `\$` into a plain `$`, for a renderer that must NOT be given
/// the `$` job.
///
/// Built on [segment], the tokenizer the web clients use, so Flutter and
/// web agree on what is math: `10$ and 20$ later`, `$ x $` and the `$…$`
/// of `$\frac{1}{2}$2 apples` stay prose here exactly as they do there.
///
/// gpt_markdown detects `$…$` spans first but then unescapes `\$` only
/// OUTSIDE any `[…]` or `(…)`, plain prose parentheses included, so
/// `(about \$5)` reached the teacher as `\$5`. Doing the split here — spans
/// first, then the unescape on prose only — is the same order without that
/// hole. Inside a span `\$` is left alone: LaTeX draws it as `$`.
String toBracketDelimiters(String text) {
  if (!text.contains(r'$')) return text;
  final out = StringBuffer();
  for (final seg in segment(text)) {
    if (!seg.isMath) {
      out.write(seg.value); // prose, `\$` already unescaped
    } else if (seg.display) {
      out.write('\\[${seg.value}\\]');
    } else {
      out.write('\\(${seg.value}\\)');
    }
  }
  return out.toString();
}

/// An inline `\(…\)` formula, claimed before gpt_markdown parses emphasis.
///
/// The parser pairs `*` delimiters by scanning for the next star run, so in
/// `\(a\) * \(b*c\)` the prose `*` closed on the `*` inside the second
/// formula and both came out as literal text. `inlinePatterns` matches are
/// lifted out of the source before parsing (gpt_markdown ≥ 1.3.0), so no
/// emphasis can open or close inside a formula. (Reordering the legacy
/// `inlineComponents` could not fix this: that combined regex takes the
/// leftmost match, and the `*` comes first. Passing them would also switch
/// the widget back to the legacy regex parser.)
final InlinePattern inlineMathPattern = InlinePattern(
  pattern: RegExp(r'\\\((.*?)\\\)', dotAll: true),
  builder:
      (context, match, style) => WidgetSpan(
        alignment: PlaceholderAlignment.baseline,
        baseline: TextBaseline.alphabetic,
        child: mathWidget(match[1]!.trim(), style, inline: true),
      ),
);

/// How MathText draws one formula: flutter_math_fork with `Strict.ignore`,
/// `\ce{…}` / `\pu{…}` translated first ([ceToLatex]; flutter_math_fork has
/// no mhchem), and a parse failure shown as its source ([MathSourceFallback]).
Widget mathWidget(String tex, TextStyle textStyle, {required bool inline}) =>
    Math.tex(
      ceToLatex(tex),
      textStyle: textStyle,
      mathStyle: inline ? MathStyle.text : MathStyle.display,
      settings: const TexParserSettings(strict: Strict.ignore),
      onErrorFallback: (_) => MathSourceFallback(tex, style: textStyle),
    );

/// How [MathText] prepares its text before rendering.
enum MathTextMode {
  /// `fix`: repair, normalize, canonicalize and wrap Unicode chemistry. The
  /// default; right for model output and stored content alike.
  fix,

  /// `normalize` only: content-preserving, no heuristic wrapping. For text
  /// that is already canonical and must be shown byte-for-byte.
  normalize,
}

/// Renders LLM-generated text with LaTeX + Markdown, identically to the web
/// clients (KaTeX) so a teacher sees exactly what a student sees.
class MathText extends StatelessWidget {
  const MathText(
    this.text, {
    super.key,
    this.style,
    this.textAlign,
    this.maxLines,
    this.overflow,
    this.mode = MathTextMode.fix,
    @Deprecated('Use mode: MathTextMode.fix (the default).')
    this.canonical = false,
  });

  /// The stored or generated text (canonical form, or anything `normalize`
  /// can make displayable).
  final String text;

  /// Style for prose and math alike.
  final TextStyle? style;

  final TextAlign? textAlign;

  /// Clamp the rendered text to this many lines, like [Text.maxLines].
  /// Applied on both the plain fast path and the markdown path.
  final int? maxLines;

  /// How clipped text is treated, like [Text.overflow].
  final TextOverflow? overflow;

  /// What to run on [text] before rendering; see [MathTextMode].
  final MathTextMode mode;

  /// Deprecated alias: `canonical: true` behaves like [MathTextMode.fix].
  final bool canonical;

  /// [text] after `fix` (or `normalize` in [MathTextMode.normalize]).
  String get _shown =>
      mode == MathTextMode.fix || canonical ? fix(text) : normalize(text);

  /// The string handed to the renderer: [_shown], trimmed, with `$`
  /// delimiters rewritten to `\(…\)` / `\[…\]`.
  String get processed => toBracketDelimiters(_shown).trim();

  @override
  Widget build(BuildContext context) {
    final baseStyle = style ?? DefaultTextStyle.of(context).style;
    final shown = _shown;

    // Fast path: prose with nothing for gpt_markdown to do. Parsing a string
    // costs ~20 regex alternations and builds a StatefulWidget + ClipRRect +
    // Text.rich per field; a question screen builds 30 cards × ~7 fields in
    // one frame (script_editor #428: a 7.58 s ANR). `isPlainProse` is
    // deliberately conservative so the two paths render the SAME text.
    if (isPlainProse(shown)) {
      return Text(
        shown.trim(),
        style: baseStyle,
        // gpt_markdown hard-codes both of these, so the fast path must too
        // or a field would flip alignment/direction the moment its text
        // stopped containing math.
        textAlign: textAlign ?? TextAlign.start,
        textDirection: TextDirection.ltr,
        maxLines: maxLines,
        overflow: overflow,
      );
    }

    return GptMarkdown(
      processed,
      style: baseStyle,
      textAlign: textAlign ?? TextAlign.start,
      maxLines: maxLines,
      overflow: overflow,
      useDollarSignsForLatex: false,
      inlinePatterns: [inlineMathPattern],
      latexBuilder:
          (context, tex, textStyle, inline) =>
              mathWidget(tex, textStyle, inline: inline),
    );
  }
}

/// What a formula that failed to parse shows: its source, in grey italic.
class MathSourceFallback extends StatelessWidget {
  const MathSourceFallback(this.source, {super.key, this.style});

  final String source;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) => Text(
    source,
    style: (style ?? DefaultTextStyle.of(context).style).copyWith(
      color: Colors.grey,
      fontStyle: FontStyle.italic,
    ),
  );
}
