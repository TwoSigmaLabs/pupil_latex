/// Character predicates and regex fragments that reproduce the Python
/// reference semantics (`str.isalpha`, `str.isspace`, `\s`, `\w`) on
/// UTF-16 Dart strings.
library;

/// Code points of Python's `str.isspace()` set (also what `\s` matches on
/// `str` patterns). Dart's own `\s` differs at the edges (it takes U+FEFF and
/// rejects U+001C–U+001F and U+0085).
const _pyWsCodePoints = [
  0x09,
  0x0A,
  0x0B,
  0x0C,
  0x0D,
  0x1C,
  0x1D,
  0x1E,
  0x1F,
  0x20,
  0x85,
  0xA0,
  0x1680,
  0x2000,
  0x2001,
  0x2002,
  0x2003,
  0x2004,
  0x2005,
  0x2006,
  0x2007,
  0x2008,
  0x2009,
  0x200A,
  0x2028,
  0x2029,
  0x202F,
  0x205F,
  0x3000,
];

/// The Python whitespace set as a regex character-class body, written as
/// `\uXXXX` escapes (which `RegExp` reads in every mode).
final String pyWs = _pyWsCodePoints
    .map((c) => '\\u${c.toRadixString(16).padLeft(4, '0')}')
    .join();

/// `\s` / `\S` with Python semantics.
final String pyS = '[$pyWs]';
final String pyNotS = '[^$pyWs]';

/// The character with code point [codePoint]. Used for characters that must
/// not appear literally in the source (private-use sentinels, combining
/// marks, the replacement character).
String u(int codePoint) => String.fromCharCode(codePoint);

/// Python's `\w` (Unicode alphanumerics plus underscore); the containing
/// regex must be built with `unicode: true`.
const pyW = r'\p{L}\p{N}_';

final _alpha = RegExp(r'^\p{L}$', unicode: true);
final _alnum = RegExp(r'^[\p{L}\p{N}]$', unicode: true);
final _space = RegExp('^$pyS\$');
// Python `isdigit()` is Unicode decimal digits plus the characters with
// Numeric_Type=Digit that lesson text can carry (super/subscript digits);
// the same class as the JS port.
final _digit = RegExp(r'^[\p{Nd}²³¹⁰⁴-⁹₀-₉]$', unicode: true);

/// `str.isalpha()` for one code point (Unicode letter categories).
bool isAlpha(String ch) => _alpha.hasMatch(ch);

/// `str.isalnum()` for one code point.
bool isAlnum(String ch) => _alnum.hasMatch(ch);

/// `str.isspace()` for one code point.
bool isSpace(String ch) => _space.hasMatch(ch);

/// `str.isdigit()` for one code point: Unicode decimal digits plus the
/// superscript and subscript digits (`$x$²` does not close a span, as in
/// Python and JS).
bool isDigit(String ch) => _digit.hasMatch(ch);

/// The code point starting at UTF-16 index [i] of [s] as a string (one or
/// two code units), so a surrogate pair is never split where Python would
/// have seen one character.
String codePointAt(String s, int i) {
  final unit = s.codeUnitAt(i);
  if (unit >= 0xD800 && unit <= 0xDBFF && i + 1 < s.length) {
    final low = s.codeUnitAt(i + 1);
    if (low >= 0xDC00 && low <= 0xDFFF) return s.substring(i, i + 2);
  }
  return s[i];
}

final _leadingWs = RegExp('^$pyS+');
final _trailingWs = RegExp('$pyS+\$');

/// `str.strip()` with Python's whitespace set.
String pyStrip(String s) => pyRstrip(pyLstrip(s));

/// `str.lstrip()`.
String pyLstrip(String s) => s.replaceFirst(_leadingWs, '');

/// `str.rstrip()`.
String pyRstrip(String s) => s.replaceFirst(_trailingWs, '');

/// Number of code points in [s] (Python `len`).
int cpLength(String s) => s.runes.length;

/// A regex character class matching any one of [chars] (each a single BMP
/// character), with the class metacharacters escaped.
String charClass(Iterable<String> chars) {
  final b = StringBuffer('[');
  for (final c in chars) {
    if (c == r'\' || c == ']' || c == '^' || c == '-' || c == '[') {
      b.write('\\');
    }
    b.write(c);
  }
  b.write(']');
  return b.toString();
}

/// `re.escape`-like escaping for use inside a regex alternation.
String regexEscape(String s) =>
    s.replaceAllMapped(RegExp(r'[.*+?^${}()|\[\]\\/]'), (m) => '\\${m[0]}');
