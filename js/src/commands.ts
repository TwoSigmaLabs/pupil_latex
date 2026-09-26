/**
 * Command vocabularies shared by every function in the package. All of them
 * come from the generated tables (python/pupiltree_latex/commands.py is the
 * source); this module only gives them their documented names and derives
 * the two computed sets.
 */

import {
  JSON_WHITESPACE_COLLISION_COMMANDS,
  KATEX_COMMANDS,
  LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
} from "./tables.g.js";

export {
  ARGUMENT_COMMANDS,
  AUDIT_EXTRA_ALLOWED_COMMANDS,
  COLLAPSE_COMMANDS,
  JSON_WHITESPACE_COLLISION_COMMANDS,
  KATEX_COMMANDS,
  LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
  NON_KATEX_MODEL_EMISSIONS,
  SCRIPT_LABELS,
  STRUCTURAL_COMMANDS,
  SYMBOL_COMMANDS,
  UNSUPPORTED_COMMANDS,
} from "./tables.g.js";

/** Commands `canonicalize` collapses a doubled backslash before: every KaTeX command plus mhchem. */
export const COLLAPSIBLE_COMMANDS: ReadonlySet<string> = new Set([
  ...KATEX_COMMANDS,
  "ce",
  "pu",
]);

/**
 * The escape decoders' vocabulary OUTSIDE math: the full KaTeX vocabulary
 * minus the four names production prose proved to be line breaks
 * ("\nu = -25 cm", "\ne) No enzyme", "\ni) Presence of", "\not").
 */
export const PROSE_ESCAPE_COMMANDS: ReadonlySet<string> = new Set(
  [
    ...JSON_WHITESPACE_COLLISION_COMMANDS,
    ...LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
  ].filter((c) => c !== "nu" && c !== "ne" && c !== "ni" && c !== "not"),
);
