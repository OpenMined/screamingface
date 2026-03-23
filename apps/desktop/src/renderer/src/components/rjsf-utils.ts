import type { RJSFSchema } from '@rjsf/utils';

/**
 * Inline all `$ref` / `$defs` so RJSF gets a plain schema with no refs.
 * Pydantic emits `$defs` + `$ref` for nested models — RJSF *should*
 * resolve these, but in practice the custom templates sometimes receive
 * the un-resolved `$ref` node, which causes the field to render as a
 * text input showing `[object Object]`.
 */
export function inlineRefs(schema: RJSFSchema): RJSFSchema {
  const defs: Record<string, RJSFSchema> = schema.$defs ?? schema.definitions ?? {};
  if (Object.keys(defs).length === 0) return schema;

  function resolve(node: unknown): unknown {
    if (node === null || typeof node !== 'object') return node;
    if (Array.isArray(node)) return node.map(resolve);

    const obj = node as Record<string, unknown>;

    // Replace {"$ref": "#/$defs/Foo"} or {"$ref": "#/definitions/Foo"} with the def itself
    if (typeof obj.$ref === 'string') {
      const match = obj.$ref.match(/^#\/(?:\$defs|definitions)\/(.+)$/);
      if (match && defs[match[1]]) {
        return resolve(defs[match[1]]);
      }
    }

    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) {
      if (k === '$defs' || k === 'definitions') continue; // strip defs from output
      out[k] = resolve(v);
    }
    return out;
  }

  return resolve(schema) as RJSFSchema;
}
