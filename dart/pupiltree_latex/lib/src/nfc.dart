/// Minimal NFC composition for `toPlain` (Dart has no `unicodedata`).
///
/// Python's `latex_to_plain` ends with `unicodedata.normalize('NFC', …)`.
/// This module composes exactly what that step can change in practice:
/// a Latin letter followed by one of the combining marks the accent
/// commands emit (`\hat` U+0302, `\bar` U+0304, `\tilde` U+0303, `\dot`
/// U+0307, `\ddot` U+0308) when a precomposed character exists, plus the
/// three compatibility singletons (ANGSTROM, OHM, KELVIN SIGN) that NFC maps
/// to their Latin/Greek letters. It is NOT a full NFC implementation: other
/// decomposed sequences already present in the input (`e` + U+0301, Hangul
/// jamo, reordering of multiple marks) are left as written.
///
/// GENERATED with Python's `unicodedata` (base letters A–Z, a–z × the five
/// marks); regenerate the table rather than editing it.
library;

/// (base + combining mark) → precomposed character.
const Map<String, String> _compose = {
  'A\u0302': '\u00C2',
  'A\u0304': '\u0100',
  'A\u0307': '\u0226',
  'A\u0308': '\u00C4',
  'A\u0303': '\u00C3',
  'B\u0307': '\u1E02',
  'C\u0302': '\u0108',
  'C\u0307': '\u010A',
  'D\u0307': '\u1E0A',
  'E\u0302': '\u00CA',
  'E\u0304': '\u0112',
  'E\u0307': '\u0116',
  'E\u0308': '\u00CB',
  'E\u0303': '\u1EBC',
  'F\u0307': '\u1E1E',
  'G\u0302': '\u011C',
  'G\u0304': '\u1E20',
  'G\u0307': '\u0120',
  'H\u0302': '\u0124',
  'H\u0307': '\u1E22',
  'H\u0308': '\u1E26',
  'I\u0302': '\u00CE',
  'I\u0304': '\u012A',
  'I\u0307': '\u0130',
  'I\u0308': '\u00CF',
  'I\u0303': '\u0128',
  'J\u0302': '\u0134',
  'M\u0307': '\u1E40',
  'N\u0307': '\u1E44',
  'N\u0303': '\u00D1',
  'O\u0302': '\u00D4',
  'O\u0304': '\u014C',
  'O\u0307': '\u022E',
  'O\u0308': '\u00D6',
  'O\u0303': '\u00D5',
  'P\u0307': '\u1E56',
  'R\u0307': '\u1E58',
  'S\u0302': '\u015C',
  'S\u0307': '\u1E60',
  'T\u0307': '\u1E6A',
  'U\u0302': '\u00DB',
  'U\u0304': '\u016A',
  'U\u0308': '\u00DC',
  'U\u0303': '\u0168',
  'V\u0303': '\u1E7C',
  'W\u0302': '\u0174',
  'W\u0307': '\u1E86',
  'W\u0308': '\u1E84',
  'X\u0307': '\u1E8A',
  'X\u0308': '\u1E8C',
  'Y\u0302': '\u0176',
  'Y\u0304': '\u0232',
  'Y\u0307': '\u1E8E',
  'Y\u0308': '\u0178',
  'Y\u0303': '\u1EF8',
  'Z\u0302': '\u1E90',
  'Z\u0307': '\u017B',
  'a\u0302': '\u00E2',
  'a\u0304': '\u0101',
  'a\u0307': '\u0227',
  'a\u0308': '\u00E4',
  'a\u0303': '\u00E3',
  'b\u0307': '\u1E03',
  'c\u0302': '\u0109',
  'c\u0307': '\u010B',
  'd\u0307': '\u1E0B',
  'e\u0302': '\u00EA',
  'e\u0304': '\u0113',
  'e\u0307': '\u0117',
  'e\u0308': '\u00EB',
  'e\u0303': '\u1EBD',
  'f\u0307': '\u1E1F',
  'g\u0302': '\u011D',
  'g\u0304': '\u1E21',
  'g\u0307': '\u0121',
  'h\u0302': '\u0125',
  'h\u0307': '\u1E23',
  'h\u0308': '\u1E27',
  'i\u0302': '\u00EE',
  'i\u0304': '\u012B',
  'i\u0308': '\u00EF',
  'i\u0303': '\u0129',
  'j\u0302': '\u0135',
  'm\u0307': '\u1E41',
  'n\u0307': '\u1E45',
  'n\u0303': '\u00F1',
  'o\u0302': '\u00F4',
  'o\u0304': '\u014D',
  'o\u0307': '\u022F',
  'o\u0308': '\u00F6',
  'o\u0303': '\u00F5',
  'p\u0307': '\u1E57',
  'r\u0307': '\u1E59',
  's\u0302': '\u015D',
  's\u0307': '\u1E61',
  't\u0307': '\u1E6B',
  't\u0308': '\u1E97',
  'u\u0302': '\u00FB',
  'u\u0304': '\u016B',
  'u\u0308': '\u00FC',
  'u\u0303': '\u0169',
  'v\u0303': '\u1E7D',
  'w\u0302': '\u0175',
  'w\u0307': '\u1E87',
  'w\u0308': '\u1E85',
  'x\u0307': '\u1E8B',
  'x\u0308': '\u1E8D',
  'y\u0302': '\u0177',
  'y\u0304': '\u0233',
  'y\u0307': '\u1E8F',
  'y\u0308': '\u00FF',
  'y\u0303': '\u1EF9',
  'z\u0302': '\u1E91',
  'z\u0307': '\u017C',
};

/// Singleton canonical decompositions NFC applies to symbol code points.
const Map<String, String> _singletons = {
  '\u212B': '\u00C5',
  '\u2126': '\u03A9',
  '\u212A': '\u004B',
};

final _marks = RegExp('[A-Za-z][\\u0302\\u0303\\u0304\\u0307\\u0308]');
final _singleton = RegExp('[\\u212A\\u212B\\u2126]');

/// Compose the accents `toPlain` can produce (see the library comment).
String nfcCompose(String text) {
  if (_marks.hasMatch(text)) {
    text = text.replaceAllMapped(_marks, (m) => _compose[m[0]!] ?? m[0]!);
  }
  if (_singleton.hasMatch(text)) {
    text = text.replaceAllMapped(_singleton, (m) => _singletons[m[0]!]!);
  }
  return text;
}
