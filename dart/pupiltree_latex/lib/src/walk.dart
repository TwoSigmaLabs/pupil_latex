/// Document walking: which keys and values are content.
///
/// The LaTeX functions are for renderable text (questions, scripts,
/// explanations), not for ids, URLs, paths, timestamps or status enums
/// (CONTRACT §5). Port of `python/pupiltree_latex/walk.py`.
library;

import 'tables.g.dart';

/// True for a map key whose value must pass through untouched.
/// Case-insensitive; `user_id`, `userId` and `userid` all match.
bool isNonContentKey(Object? key) {
  if (key is! String) return false;
  final k = key.toLowerCase().replaceAll('-', '_');
  if (kNonContentKeys.contains(k) ||
      kNonContentKeys.contains(k.replaceAll('_', ''))) {
    return true;
  }
  return kNonContentKeySuffixes.any(k.endsWith);
}

/// True for strings shaped like URLs, API paths or media files.
bool isUrlOrPathString(Object? value) {
  if (value is! String || value.isEmpty) return false;
  if (kUrlPrefixes.any(value.startsWith)) return true;
  final lower = value.toLowerCase();
  return kFileExtensions.any(lower.endsWith);
}

/// True when `parent[key]` is Class B narration (tag `v140-b5`).
/// [narrativeKeys] lists key names (exact match) and `name@sibling` entries
/// that match `name` only in a map that also has a `sibling` key
/// (`script@transcript`: a podcast's `script` sits beside its `transcript`).
bool isNarrativeKey(
  Object? key,
  Object? parent,
  Iterable<String>? narrativeKeys,
) {
  if (narrativeKeys == null || key is! String) return false;
  for (final entry in narrativeKeys) {
    final at = entry.indexOf('@');
    final name = at == -1 ? entry : entry.substring(0, at);
    final sibling = at == -1 ? '' : entry.substring(at + 1);
    if (key == name &&
        (sibling.isEmpty || (parent is Map && parent.containsKey(sibling)))) {
      return true;
    }
  }
  return false;
}

/// True for fields that hold the model's raw output or our own prompts:
/// kept for provenance, never rendered, so `auditDeep` skips them.
bool isNotRenderedKey(Object? key) {
  if (key is! String) return false;
  final k = key.toLowerCase();
  return kNotRenderedKeys.contains(k) ||
      k.endsWith('_raw') ||
      k.startsWith('raw_');
}
