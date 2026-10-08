/// Mojibake repair: the deterministic table + context rules, identical in
/// Python, Dart and JS. Port of `fix_mojibake_table` in
/// `python/pupiltree_latex/mojibake.py` (Python's `fix_mojibake_ftfy` has no
/// Dart equivalent; corpus cases that need ftfy are tagged
/// `"impl": ["python"]`). The table itself, including the generated Latin-1
/// and Windows-1252 readings, is `kMojibakeTable`.
library;

import 'dart:convert';

import 'tables.g.dart';
import 'text_util.dart';

/// Table keys, longest first, ties in table order (Python's stable sort).
final List<String> _tableKeysLongestFirst = () {
  final keys = kMojibakeTable.keys.toList();
  final index = {for (var i = 0; i < keys.length; i++) keys[i]: i};
  keys.sort((a, b) {
    final byLength = b.length.compareTo(a.length);
    return byLength != 0 ? byLength : index[a]!.compareTo(index[b]!);
  });
  return keys;
}();

final _entity =
    RegExp(r'&(?:#([0-9]{1,7})|#[xX]([0-9A-Fa-f]{1,6})|([A-Za-z]{2,8}));');

String _entityReplace(Match m) {
  final int code;
  if (m[1] != null) {
    code = int.parse(m[1]!);
  } else if (m[2] != null) {
    code = int.parse(m[2]!, radix: 16);
  } else {
    return kHtmlEntities[m[0]!] ?? m[0]!;
  }
  if (code > 0 && code <= 0x10FFFF && !(code >= 0xD800 && code <= 0xDFFF)) {
    return String.fromCharCode(code);
  }
  return m[0]!;
}

// Python `html.unescape` (tag `v140-a2`): the same character-reference
// pattern, the full HTML5 table and the Windows-1252 numeric overrides.
final _charref =
    RegExp(r'&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[^\t\n\f <&#;]{1,32};?)');

bool _invalidCodepoint(int num) =>
    (num >= 0x1 && num <= 0x8) ||
    num == 0xB ||
    (num >= 0xE && num <= 0x1F) ||
    (num >= 0x7F && num <= 0x9F) ||
    (num >= 0xFDD0 && num <= 0xFDEF) ||
    (num & 0xFFFE) == 0xFFFE;

String _replaceCharref(Match m) {
  final s = m[1]!;
  if (s.startsWith('#')) {
    final hex = s.length > 1 && (s[1] == 'x' || s[1] == 'X');
    var digits = hex ? s.substring(2) : s.substring(1);
    if (digits.endsWith(';')) digits = digits.substring(0, digits.length - 1);
    var k = 0;
    while (k < digits.length && digits[k] == '0') {
      k++;
    }
    digits = digits.substring(k);
    // More than 8 significant digits is past U+10FFFF in either base.
    final num = digits.length > 8
        ? 0x7FFFFFFF
        : digits.isEmpty
            ? 0
            : int.parse(digits, radix: hex ? 16 : 10);
    final override = kHtmlNumericOverrides['$num'];
    if (override != null) return override;
    if ((num >= 0xD800 && num <= 0xDFFF) || num > 0x10FFFF) {
      return u(0xFFFD);
    }
    if (_invalidCodepoint(num)) return '';
    return String.fromCharCode(num);
  }
  final whole = kHtml5Entities[s];
  if (whole != null) return whole;
  // The longest legacy name (one without `;`) that starts the reference.
  for (var x = s.length - 1; x > 1; x--) {
    final head = kHtml5Entities[s.substring(0, x)];
    if (head != null) return head + s.substring(x);
  }
  return '&$s';
}

/// Python's `html.unescape`, in every language (tag `v140-a2`): the full
/// HTML5 table, numeric references with or without `;`, legacy names
/// without `;` (`&lt` → `<`, longest prefix: `&ampx` → `&x`), one round
/// (`&amp;lt;` → `&lt;`); unknown names stay (`AT&T`, `&foo;`).
String unescapeHtmlEntities(String text) {
  if (!text.contains('&')) return text;
  return text.replaceAllMapped(_charref, _replaceCharref);
}

/// The small `kHtmlEntities` set plus numeric references, up to three
/// rounds: what `normalize`'s mojibake step decodes (unchanged since 1.0).
String _unescapeTableEntities(String text) {
  if (!text.contains('&')) return text;
  for (var round = 0; round < 3; round++) {
    final decoded = text.replaceAllMapped(_entity, _entityReplace);
    if (decoded == text) return text;
    text = decoded;
  }
  return text;
}

final _nonAscii = RegExp(r'[^\x00-\x7F]');
final _bad = RegExp('[${u(0xFFFD)}\xC3\xC2]');
final _replacement = RegExp(u(0xFFFD));
final _c1 = RegExp(r'[\x80-\x9F]');
final _loneSurrogate = RegExp(r'[\uD800-\uDFFF]');
const _garbage = r'[\x80-\x9F\xA0-\xFF]';
final _rootDigits = RegExp('â$_garbage{0,3}([0-9]+)');
final _rootParen = RegExp('â$_garbage{0,3}\\(');
final _letterRoot = RegExp('([A-Za-z])â$_garbage{0,3}([0-9])');
final _slashRoot = RegExp('/â$_garbage{0,3}([0-9])');
final _digitPi = RegExp('([0-9])$_garbage{0,2}Ï');
final _leadPiSlash = RegExp('(^|[$pyWs(,\\[])Ï$_garbage{0,2}/');
final _slashOmega = RegExp('/Ï(?=[$pyWs,.)\\]}]|\$)');
final _opPi = RegExp(
  '([+\\-*×÷=/(])Ï(?=[+\\-*×÷=/)$pyWs,]|\$)',
);
final _leadPi = RegExp('(^|[$pyWs(,])Ï(?=[$pyWs),.]|\$)');

/// Re-encode as Latin-1 and decode as UTF-8; keep the result only when it
/// has fewer bad characters than the input.
String _tryFixDoubleEncoding(String text) {
  if (!text.contains('Ã') && !text.contains('Â')) return text;
  final List<int> raw;
  try {
    raw = latin1.encode(text);
  } on ArgumentError {
    return text; // a character above U+00FF: not Latin-1 mojibake
  }
  final decoded = utf8.decode(raw, allowMalformed: true);
  final originalBad = _bad.allMatches(text).length;
  final decodedBad = _replacement.allMatches(decoded).length;
  return decodedBad < originalBad ? decoded : text;
}

String _applyTable(String text) {
  for (final key in _tableKeysLongestFirst) {
    if (text.contains(key)) text = text.replaceAll(key, kMojibakeTable[key]!);
  }
  return text;
}

/// π, ω and √ present before the context rules run are hidden behind these
/// private-use placeholders so the doubled-symbol cleanup never touches them.
final _collapsePlaceholders = <String, String>{
  'π': u(0xE020),
  'ω': u(0xE021),
  '√': u(0xE022),
};

String _applyContextRules(String text) {
  for (final e in _collapsePlaceholders.entries) {
    text = text.replaceAll(e.key, e.value);
  }
  // NBSP is a space, not garbage; C1 controls that survived the table are
  // garbage; a lone surrogate can never be encoded.
  text = text.replaceAll(' ', ' ');
  text = text.replaceAll(_c1, '');
  text = _stripLoneSurrogates(text);
  text = text.replaceAllMapped(_rootDigits, (m) => '√${m[1]}');
  text = text.replaceAll(_rootParen, '√(');
  text = text.replaceAllMapped(_letterRoot, (m) => '${m[1]}√${m[2]}');
  text = text.replaceAllMapped(_slashRoot, (m) => '/√${m[1]}');
  text = text.replaceAllMapped(_digitPi, (m) => '${m[1]}π');
  text = text.replaceAllMapped(_leadPiSlash, (m) => '${m[1]}π/');
  text = text.replaceAll(_slashOmega, '/ω');
  text = text.replaceAll('Ï/Ï', 'π/ω');
  text = text.replaceAllMapped(_opPi, (m) => '${m[1]}π');
  text = text.replaceAllMapped(_leadPi, (m) => '${m[1]}π');
  // Collapse a doubled π / ω / √ only when a context rule above produced
  // one of the pair (`Ï€Ï` once became `ππ`). A genuine repeated letter
  // (`ππ`, `√√2`, or `Ï€Ï€` which the table maps to `ππ`) is protected by
  // the placeholders.
  for (final e in _collapsePlaceholders.entries) {
    final ch = e.key;
    final placeholder = e.value;
    text = text
        .replaceAll('$ch$ch', ch)
        .replaceAll('$placeholder$ch', placeholder)
        .replaceAll('$ch$placeholder', placeholder)
        .replaceAll(placeholder, ch);
  }
  return text;
}

/// Remove UTF-16 surrogates that do not form a pair (Python's
/// `[\ud800-\udfff]` on a str, where a lone surrogate is one code point).
String _stripLoneSurrogates(String text) {
  if (!_loneSurrogate.hasMatch(text)) return text;
  final out = StringBuffer();
  final units = text.codeUnits;
  for (var i = 0; i < units.length; i++) {
    final unit = units[i];
    if (unit >= 0xD800 && unit <= 0xDBFF) {
      if (i + 1 < units.length &&
          units[i + 1] >= 0xDC00 &&
          units[i + 1] <= 0xDFFF) {
        out.writeCharCode(unit);
        out.writeCharCode(units[i + 1]);
        i++;
      }
      continue;
    }
    if (unit >= 0xDC00 && unit <= 0xDFFF) continue;
    out.writeCharCode(unit);
  }
  return out.toString();
}

/// Deterministic mojibake repair (spec §2 step 2): HTML entities decoded,
/// then the double-encoding retry, [kMojibakeTable] longest key first, and
/// the context rules for `â…digits` → `√…` and a lone `Ï` → `π`/`ω`. The
/// byte-level steps are skipped when the text has no character ≥ U+0080.
String fixMojibakeTable(String text) {
  if (text.isEmpty) return text;
  return fixMojibakeCore(_unescapeTableEntities(text));
}

/// [fixMojibakeTable] without its entity step: double-encoding repair, the
/// table and the context rules. `toPlain(…, style: 'compare')` decodes
/// entities with [unescapeHtmlEntities] first, once.
String fixMojibakeCore(String text) {
  if (text.isEmpty) return text;
  if (!_nonAscii.hasMatch(text)) return text;
  text = _tryFixDoubleEncoding(text);
  text = _applyTable(text);
  text = _applyContextRules(text);
  return text;
}
