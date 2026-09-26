/// Command vocabularies derived from the generated tables (the Python
/// package computes the same sets in `commands.py`).
library;

import 'tables.g.dart';

/// Commands `canonicalize` collapses a doubled backslash before (`\\frac` →
/// `\frac`): every KaTeX command plus mhchem.
final Set<String> kCollapsibleCommands = {...kKatexCommands, 'ce', 'pu'};

/// The escape decoders' vocabulary OUTSIDE math: the full KaTeX vocabulary
/// minus the four names production prose proved to be line breaks
/// ("\nu = -25 cm", "\ne) No enzyme", "\ni) Presence of", "\not").
final Set<String> kProseEscapeCommands = {
  ...kJsonWhitespaceCollisionCommands,
  ...kLatexCommandsBehindJsonEscapes,
}..removeAll(const {'nu', 'ne', 'ni', 'not'});
