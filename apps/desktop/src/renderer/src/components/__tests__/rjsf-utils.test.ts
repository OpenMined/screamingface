import { describe, it, expect } from 'vitest';
import type { RJSFSchema } from '@rjsf/utils';
import { buildCodeEditorUiSchema } from '../rjsf-utils';

describe('buildCodeEditorUiSchema', () => {
  it('routes an x-code-editor property to CodeDictField with its language', () => {
    const schema: RJSFSchema = {
      type: 'object',
      properties: {
        scripts: {
          type: 'object',
          additionalProperties: { type: 'string' },
          'x-code-editor': { language: 'python' },
        } as RJSFSchema,
      },
    };
    expect(buildCodeEditorUiSchema(schema)).toEqual({
      scripts: { 'ui:field': 'CodeDictField', 'ui:options': { language: 'python' } },
    });
  });

  it('returns an empty object when no property carries the hint', () => {
    const schema: RJSFSchema = {
      type: 'object',
      properties: { name: { type: 'string' } },
    };
    expect(buildCodeEditorUiSchema(schema)).toEqual({});
  });

  it('defaults language to plaintext when unspecified', () => {
    const schema: RJSFSchema = {
      type: 'object',
      properties: { blob: { type: 'string', 'x-code-editor': {} } as RJSFSchema },
    };
    expect(buildCodeEditorUiSchema(schema)).toEqual({
      blob: { 'ui:field': 'CodeDictField', 'ui:options': { language: 'plaintext' } },
    });
  });
});
