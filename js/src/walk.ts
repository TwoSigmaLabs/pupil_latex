/**
 * Document walking: which keys and values are content. Port of
 * python/pupiltree_latex/walk.py; the key tables come from tables.g.ts.
 */

import {
  FILE_EXTENSIONS,
  NON_CONTENT_KEYS,
  NON_CONTENT_KEY_SUFFIXES,
  NOT_RENDERED_KEYS,
  URL_PREFIXES,
} from "./tables.g.js";

export { NON_CONTENT_KEYS, NON_CONTENT_KEY_SUFFIXES };

/**
 * True for an object key whose value must pass through untouched.
 * Case-insensitive; `user_id`, `userId` and `userid` all match.
 */
export function isNonContentKey(key: unknown): boolean {
  if (typeof key !== "string") return false;
  const k = key.toLowerCase().split("-").join("_");
  if (NON_CONTENT_KEYS.has(k) || NON_CONTENT_KEYS.has(k.split("_").join("")))
    return true;
  return NON_CONTENT_KEY_SUFFIXES.some((suffix) => k.endsWith(suffix));
}

/** True for strings shaped like URLs, API paths or media files. */
export function isUrlOrPathString(value: unknown): boolean {
  if (typeof value !== "string" || !value) return false;
  if (URL_PREFIXES.some((p) => value.startsWith(p))) return true;
  const lower = value.toLowerCase();
  return FILE_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** Raw model output / prompt fields: kept for provenance, never rendered. */
export function isNotRenderedKey(key: unknown): boolean {
  if (typeof key !== "string") return false;
  const k = key.toLowerCase();
  return NOT_RENDERED_KEYS.has(k) || k.endsWith("_raw") || k.startsWith("raw_");
}
