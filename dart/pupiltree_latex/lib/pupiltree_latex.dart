/// pupiltree-latex: one contract, one corpus, one API for math text.
///
/// ```dart
/// import 'package:pupiltree_latex/pupiltree_latex.dart';
///
/// final fixed = fix(modelText);           // the one call
/// final shown = normalize(stored);        // any client, before rendering
/// final parts = segment(shown);           // the one tokenizer
/// final spoken = toPlain(shown, style: 'tts');
/// ```
///
/// See `spec/API.md` for the semantics each function guarantees and
/// `spec/CONTRACT.md` for where each one may run. The Python package is the
/// reference implementation; `corpus/` is the executable contract.
///
/// Known differences from the Python reference (none observable in the
/// corpus):
///
/// - Positions (`Finding.position`) are UTF-16 indices, not code points.
/// - `canonicalize` uses the mojibake table where Python may use ftfy;
///   corpus cases that need ftfy carry `"impl": ["python"]`.
/// - `toPlain` ends with a minimal NFC step (`src/nfc.dart`): it composes
///   the accent marks the converter itself emits on Latin letters and the
///   Angstrom/Ohm/Kelvin singletons; other decomposed sequences already in
///   the input are left as written.
/// - `isdigit()` is approximated as `\p{Nd}` plus the superscript and
///   subscript digits (as in the JS port); Python's rarer Numeric_Type=Digit
///   characters (circled digits and the like) are not digits here.
library;

export 'src/audit.dart'
    show
        Finding,
        allKinds,
        audit,
        auditDeep,
        auditKinds,
        countByKind,
        errorKinds,
        isError,
        makeSnippet;
export 'src/canonicalize.dart' show canonicalize, canonicalizeDeep;
export 'src/commands.dart';
export 'src/fix.dart'
    show
        escapeTextSpecials,
        fix,
        fixDeep,
        kTypographicSpans,
        mergeAdjacentMath,
        unwrapTypographicSpans,
        wrapBareSymbolCommands,
        wrapUnicodeChemistry,
        wrapUnicodeScripts;
export 'src/json_transport.dart'
    show escapeLatexForJson, loadsLatexAware, loadsModelJson;
export 'src/mojibake.dart'
    show fixMojibakeCore, fixMojibakeTable, unescapeHtmlEntities;
export 'src/normalize.dart'
    show
        decodeEscapesOutsideMath,
        escapeCurrency,
        normalize,
        normalizeDelimiters,
        stripOrphanDelimiters;
export 'src/repair.dart' show repair, repairDeep;
export 'src/segment.dart' show Segment, containsMath, isPlainProse, segment;
export 'src/spans.dart' show mathMask, mathRanges;
export 'src/tables.g.dart';
export 'src/to_plain.dart'
    show bareChemistryToUnicode, latexToPlain, styles, toPlain;
export 'src/unicode_math.dart'
    show
        convertCombiningVec,
        normalizeHomoglyphs,
        unicodeMathToLatex,
        wrapBareUnicodeMath;
export 'src/walk.dart'
    show isNonContentKey, isNotRenderedKey, isUrlOrPathString;
