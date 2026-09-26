"""Generate lib/src/nfc.dart (the minimal NFC table `toPlain` needs) with
Python's unicodedata:  python tool/gen_nfc.py
"""
import os
import unicodedata

marks = ["\u0302", "\u0304", "\u0307", "\u0308", "\u0303"]
BS = chr(92)
L = []
L.append("/// Minimal NFC composition for `toPlain` (Dart has no `unicodedata`).")
L.append("///")
L.append("/// Python's `latex_to_plain` ends with `unicodedata.normalize('NFC', …)`.")
L.append("/// This module composes exactly what that step can change in practice:")
L.append("/// a Latin letter followed by one of the combining marks the accent")
L.append(
    "/// commands emit (`"
    + BS
    + "hat` U+0302, `"
    + BS
    + "bar` U+0304, `"
    + BS
    + "tilde` U+0303, `"
    + BS
    + "dot`"
)
L.append(
    "/// U+0307, `" + BS + "ddot` U+0308) when a precomposed character exists, plus the"
)
L.append(
    "/// three compatibility singletons (ANGSTROM, OHM, KELVIN SIGN) that NFC maps"
)
L.append("/// to their Latin/Greek letters. It is NOT a full NFC implementation: other")
L.append("/// decomposed sequences already present in the input (`e` + U+0301, Hangul")
L.append("/// jamo, reordering of multiple marks) are left as written.")
L.append("///")
L.append("/// GENERATED with Python's `unicodedata` (base letters A–Z, a–z × the five")
L.append("/// marks); regenerate the table rather than editing it.")
L.append("library;")
L.append("")
L.append("/// (base + combining mark) → precomposed character.")
L.append("const Map<String, String> _compose = {")
for base in [chr(c) for c in range(0x41, 0x5B)] + [chr(c) for c in range(0x61, 0x7B)]:
    for m in marks:
        n = unicodedata.normalize("NFC", base + m)
        if len(n) == 1:
            L.append("  '%s%su%04X': '%su%04X'," % (base, BS, ord(m), BS, ord(n)))
L.append("};")
L.append("")
L.append("/// Singleton canonical decompositions NFC applies to symbol code points.")
L.append("const Map<String, String> _singletons = {")
for s in ["\u212b", "\u2126", "\u212a"]:
    n = unicodedata.normalize("NFC", s)
    L.append("  '%su%04X': '%su%04X'," % (BS, ord(s), BS, ord(n)))
L.append("};")
L.append("")
L.append(
    "final _marks = RegExp('[A-Za-z][%su0302%su0303%su0304%su0307%su0308]');"
    % ((BS * 2,) * 5)
)
L.append("final _singleton = RegExp('[%su212A%su212B%su2126]');" % ((BS * 2,) * 3))
L.append("")
L.append("/// Compose the accents `toPlain` can produce (see the library comment).")
L.append("String nfcCompose(String text) {")
L.append("  if (_marks.hasMatch(text)) {")
L.append("    text = text.replaceAllMapped(_marks, (m) => _compose[m[0]!] ?? m[0]!);")
L.append("  }")
L.append("  if (_singleton.hasMatch(text)) {")
L.append("    text = text.replaceAllMapped(_singleton, (m) => _singletons[m[0]!]!);")
L.append("  }")
L.append("  return text;")
L.append("}")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "src", "nfc.dart")
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print(len(L))
