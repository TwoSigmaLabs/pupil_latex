/**
 * @pupiltree/latex: one contract, one corpus, one API for math text.
 *
 *     import { repair, normalize, canonicalize, segment, toPlain, audit } from "@pupiltree/latex";
 *
 * See spec/API.md for the semantics each function guarantees and
 * spec/CONTRACT.md for where each one may run. The Python package
 * (python/pupiltree_latex) is the reference implementation; this is its port.
 */

export {
  fix,
  fixDeep,
  wrapBareSymbolCommands,
  wrapUnicodeScripts,
  escapeTextSpecials,
  mergeAdjacentMath,
  SYMBOL_COMMANDS,
} from "./fix.js";
export { mathMask, mathRanges } from "./spans.js";
export { COLLAPSIBLE_COMMANDS, PROSE_ESCAPE_COMMANDS } from "./commands.js";
export { wrapUnicodeChemistry } from "./chemistry.js";
export { repair, repairDeep } from "./repair.js";
export {
  normalize,
  normalizeDelimiters,
  stripOrphanDelimiters,
  escapeCurrency,
  decodeEscapesOutsideMath,
} from "./normalize.js";
export { canonicalize, canonicalizeDeep } from "./canonicalize.js";
export { segment, containsMath, isPlainProse } from "./segment.js";
export type { Segment } from "./segment.js";
export { toPlain, STYLES } from "./toPlain.js";
export type { PlainStyle } from "./toPlain.js";
export {
  audit,
  auditKinds,
  auditDeep,
  countByKind,
  isError,
  ALL_KINDS,
  ERROR_KINDS,
} from "./audit.js";
export type { Finding, FindingKind } from "./audit.js";
export {
  escapeLatexForJson,
  loadsLatexAware,
  loadsModelJson,
} from "./jsonTransport.js";
export { fixMojibakeTable, unescapeHtmlEntities } from "./mojibake.js";
export {
  normalizeHomoglyphs,
  convertCombiningVec,
  unicodeMathToLatex,
  wrapBareUnicodeMath,
  greekWordAt,
  attachedGroupMask,
} from "./unicodeMath.js";
export {
  isNonContentKey,
  isUrlOrPathString,
  isNotRenderedKey,
} from "./walk.js";
export {
  VERSION,
  LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
  JSON_WHITESPACE_COLLISION_COMMANDS,
  KATEX_COMMANDS,
  COLLAPSE_COMMANDS,
  STRUCTURAL_COMMANDS,
  UNICODE_MATH,
  HOMOGLYPHS,
  WRAPPABLE_BARE_CHARS,
  LATEX_CMD_MAP,
  MOJIBAKE_TABLE,
  NON_CONTENT_KEYS,
  NON_CONTENT_KEY_SUFFIXES,
  SCRIPT_LABELS,
  HTML_ENTITIES,
  GREEK_MATH_LETTERS,
  GREEK_UNIT_SYMBOLS,
} from "./tables.g.js";
