/// `normalize`: display-safe, content-preserving preparation for a renderer.
///
/// Ported from script_editor `latex_preprocess.dart` (#420, #421) via
/// `python/pupiltree_latex/normalize.py`. The order is load-bearing:
/// delimiters are normalised BEFORE prose escapes are decoded, so a `\theta`
/// still sitting inside `\(…\)` is recognised as math and not turned into a
/// TAB plus "heta". Nothing here wraps text in `$`, converts Unicode or
/// touches URLs.
library;

import 'audit.dart';
import 'commands.dart';
import 'guarded_regexp.dart';
import 'mojibake.dart';
import 'repair.dart';
import 'text_util.dart';

// ---------------------------------------------------------------------------
// 3. delimiters
// ---------------------------------------------------------------------------

// Not after a backslash, so a LaTeX line break `\\[2pt]` inside a display
// block is not mistaken for an opening `\[`, and `\\)` is not a closer: the
// opener through the guard, the closer through the last character of the
// lazy body, `[\s\S]*?[^\\]` (at least one character, as `[\s\S]+?`).
final _displayBracket =
    GuardedRegExp.notAfter(r'\\', r'\\\[([\s\S]*?[^\\])\\\]');
final _inlineParen = GuardedRegExp.notAfter(r'\\', r'\\\(([\s\S]*?[^\\])\\\)');
final _innerNewline = RegExp('$pyS*\\n$pyS*');

/// `\(…\)` → `$…$` and `\[…\]` → `$$…$$`.
///
/// Newlines inside an inline span collapse to one space: no inline matcher
/// (gpt_markdown, remark-math, this package's `segment`) crosses lines.
String normalizeDelimiters(String text) {
  if (!text.contains(r'\(') && !text.contains(r'\[')) return text;
  text = _displayBracket.replaceAllMapped(text, (m) => '\$\$${m[1]}\$\$');
  text = _inlineParen.replaceAllMapped(
    text,
    (m) => '\$${pyStrip(m[1]!.replaceAll(_innerNewline, ' '))}\$',
  );
  return text;
}

// ---------------------------------------------------------------------------
// 4. orphan delimiters
// ---------------------------------------------------------------------------

final _orphanDelimiter = GuardedRegExp.notAfter(r'\\', r'\\[()\[\]]');

/// Remove any `\(` `\)` `\[` `\]` left after [normalizeDelimiters]; by
/// construction they have no partner. Leaving one would make gpt_markdown
/// skip every `$…$` in the field.
String stripOrphanDelimiters(String text) {
  if (!text.contains(r'\(') &&
      !text.contains(r'\)') &&
      !text.contains(r'\[') &&
      !text.contains(r'\]')) {
    return text;
  }
  return _orphanDelimiter.replaceAll(text, '');
}

// ---------------------------------------------------------------------------
// 5. currency
// ---------------------------------------------------------------------------

bool _isDigitAt(String s, int i) =>
    i >= 0 &&
    i < s.length &&
    s.codeUnitAt(i) >= 0x30 &&
    s.codeUnitAt(i) <= 0x39;

bool _isSpaceAt(String s, int i) =>
    i >= 0 && i < s.length && (s[i] == ' ' || s[i] == '\t');

bool _isEscaped(String s, int i) => i > 0 && s[i - 1] == r'\';

final _formulaChars = RegExp(r'^[0-9A-Za-z+\-*/=<>().,^_ \t]+$');
final _formulaOperator = RegExp(r'[+\-*/=<>^_]');
final _formulaCommand = RegExp(r'\\[A-Za-z]+');
final _twoLetters = RegExp(r'[A-Za-z]{2,}');
final _alphaChar = RegExp(r'\p{L}', unicode: true);

/// True when the content of `$<digit>… $` (space before the closer) is
/// clearly a formula, not prose between two amounts: after removing command
/// names it is only digits, letters, operators, brackets and spaces, has an
/// operator and a letter or command, and no two letters in a row (no word).
bool isFormula(String content) {
  var end = content.length;
  while (end > 0 && (content[end - 1] == ' ' || content[end - 1] == '\t')) {
    end--;
  }
  final core = content.substring(0, end);
  if (core.isEmpty) return false;
  final hasCommand = _formulaCommand.hasMatch(core);
  final bare = core.replaceAll(_formulaCommand, ' ');
  if (!_formulaChars.hasMatch(bare) || _twoLetters.hasMatch(bare)) {
    return false;
  }
  if (!_formulaOperator.hasMatch(bare) && !hasCommand) return false;
  if (!(hasCommand || _alphaChar.hasMatch(bare))) return false;
  // A command that needs an argument and has none (`$5 \text $`) cannot
  // render: as currency it at least stays readable.
  final probe = '\$$core\$';
  return detectCommandMissingArgument(probe).isEmpty &&
      detectFracMissingArgs(probe).isEmpty;
}

String _escapeCurrencyInLine(String line) {
  if (!line.contains(r'$')) return line;
  final out = StringBuffer();
  var i = 0;
  final n = line.length;
  while (i < n) {
    final ch = line[i];
    if (ch != r'$' || _isEscaped(line, i)) {
      out.write(ch);
      i++;
      continue;
    }
    // `$$` display block: copy through to its closing `$$` (or end of line).
    if (i + 1 < n && line[i + 1] == r'$') {
      final close = line.indexOf(r'$$', i + 2);
      final end = close == -1 ? n : close + 2;
      out.write(line.substring(i, end));
      i = end;
      continue;
    }
    if (!_isDigitAt(line, i + 1)) {
      // A math opener: copy the whole span through to its first closer (the
      // tokenizer's rule) so the closer is never re-examined as a currency
      // opener (`$\sqrt$2` must not become `$\sqrt\$2`).
      var j = i + 1;
      while (j < n && !(line[j] == r'$' && !_isEscaped(line, j))) {
        j++;
      }
      if (j < n) {
        out.write(line.substring(i, j + 1));
        i = j + 1;
        continue;
      }
      out.write(ch);
      i++;
      continue;
    }
    // `$<digit>`: currency unless the next single `$` is a valid closer.
    var j = i + 1;
    var closerValid = false;
    while (j < n) {
      if (line[j] == r'$' && !_isEscaped(line, j)) {
        // A `$` right after the closer is the NEXT span's opener
        // (`$1$$\gamma$`), not a display delimiter: only whitespace before
        // and a digit after invalidate a closer.
        closerValid = !_isDigitAt(line, j + 1) &&
            (!_isSpaceAt(line, j - 1) ||
                // `Compute $2x + 3 $.`: the renderers pair a closer after a
                // space, so a formula keeps its dollars.
                isFormula(line.substring(i + 1, j)));
        break;
      }
      j++;
    }
    if (closerValid) {
      out.write(line.substring(i, j + 1));
      i = j + 1;
    } else {
      out.write(r'\$');
      i++;
    }
  }
  return out.toString();
}

/// A `$` that is money becomes `\$` (pandoc's closer rule, per line).
///
/// `$5000 and $\frac14$` → `\$5000 and $\frac14$`; `$5-$10` → `\$5-\$10`;
/// `costs $5.` → `costs \$5.`; `$2x + 3$` unchanged.
String escapeCurrency(String text) {
  if (!text.contains(r'$')) return text;
  return text.split('\n').map(_escapeCurrencyInLine).join('\n');
}

// ---------------------------------------------------------------------------
// 6. prose escapes
// ---------------------------------------------------------------------------

// A whole math span. Inline content may contain `\$` but no bare `$` and no
// newline — the shape every inline matcher accepts. An inline `$` must not
// follow a backslash; a `$$` may. The scan pattern tries `$$…$$` at a `$$`
// (zero width) and the inline form one character after a non-backslash;
// the two can never both match at one position (`$$` vs `$` + non-`$`).
const _mathSpanBody = r'\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\n\\])+\$';
final _mathSpan = GuardedRegExp.custom(
  _mathSpanBody,
  '(?:(?=\\\$\\\$)|[^\\\\](?=\\\$(?!\\\$)))(?=($_mathSpanBody))',
  accept: (text, m) =>
      m[0]!.startsWith(r'$$') || m.start == 0 || text[m.start - 1] != r'\',
);
final _proseEscape = RegExp(r'\\r\\n|\\[nrt]');
final _commandName = RegExp(r'\\([A-Za-z]+)');
// A lesson-script label is a lowercase word: `\teacher:`, `\type:`. A
// capitalised word after `\n` (`Host: Priya\nGuest: Vikram`) is a line break
// followed by a name.
final _scriptLabel = RegExp(r'\\[a-z][a-z_]*:');

String _decodeProseEscapes(String prose) {
  return prose.replaceAllMapped(_proseEscape, (m) {
    final name = _commandName.matchAsPrefix(prose, m.start);
    // Same vocabulary as the JSON transport: outside math `\nu`, `\ne`,
    // `\ni`, `\not` are line breaks (production prose proved it).
    if (name != null && kProseEscapeCommands.contains(name[1])) return m[0]!;
    // A lesson-script label (`\teacher:`, `\type:`, `\read:`) is never an
    // escape, whatever the word.
    if (_scriptLabel.matchAsPrefix(prose, m.start) != null) return m[0]!;
    return m[0] == r'\t' ? '\t' : '\n';
  });
}

/// Literal two-character `\n` / `\r\n` / `\r` / `\t` in prose become real
/// whitespace. Math spans are left intact, and a known command (`\theta`,
/// `\neq`, `\text{…}`, `\right`) is never touched.
String decodeEscapesOutsideMath(String text) {
  if (!text.contains(r'\')) return text;
  return _mathSpan.splitMapJoin(
    text,
    onMatch: (m) => m[0]!,
    onNonMatch: _decodeProseEscapes,
  );
}

// ---------------------------------------------------------------------------
// pipeline
// ---------------------------------------------------------------------------

/// repair → mojibake table → delimiters → orphans → currency → escapes.
/// Idempotent, content-preserving.
String normalize(String text) {
  if (text.isEmpty) return text;
  text = repair(text);
  text = fixMojibakeTable(text);
  text = normalizeDelimiters(text);
  text = stripOrphanDelimiters(text);
  text = escapeCurrency(text);
  text = decodeEscapesOutsideMath(text);
  return text;
}
