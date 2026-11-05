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

/**
 * True when `parent[key]` is Class B narration (tag `v140-b5`).
 * `narrativeKeys` lists key names (exact match) and `name@sibling` entries
 * that match `name` only in an object that also has a `sibling` key
 * (`script@transcript`: a podcast's `script` sits beside its `transcript`).
 */
export function isNarrativeKey(
  key: unknown,
  parent: unknown,
  narrativeKeys: readonly string[] | undefined,
): boolean {
  if (!narrativeKeys || narrativeKeys.length === 0 || typeof key !== "string")
    return false;
  for (const entry of narrativeKeys) {
    const at = entry.indexOf("@");
    const name = at === -1 ? entry : entry.slice(0, at);
    const sibling = at === -1 ? "" : entry.slice(at + 1);
    if (
      key === name &&
      (!sibling ||
        (parent !== null &&
          typeof parent === "object" &&
          Object.prototype.hasOwnProperty.call(parent, sibling)))
    )
      return true;
  }
  return false;
}

/** Raw model output / prompt fields: kept for provenance, never rendered. */
export function isNotRenderedKey(key: unknown): boolean {
  if (typeof key !== "string") return false;
  const k = key.toLowerCase();
  return NOT_RENDERED_KEYS.has(k) || k.endsWith("_raw") || k.startsWith("raw_");
}
