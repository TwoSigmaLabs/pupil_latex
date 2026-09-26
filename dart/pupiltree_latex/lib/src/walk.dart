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

/// True for fields that hold the model's raw output or our own prompts:
/// kept for provenance, never rendered, so `auditDeep` skips them.
bool isNotRenderedKey(Object? key) {
  if (key is! String) return false;
  final k = key.toLowerCase();
  return kNotRenderedKeys.contains(k) ||
      k.endsWith('_raw') ||
      k.startsWith('raw_');
}
