import type { FormProps } from '@rjsf/core';
import Form from '@rjsf/core';
import type {
  ArrayFieldItemButtonsTemplateProps,
  ArrayFieldItemTemplateProps,
  ArrayFieldTemplateProps,
  BaseInputTemplateProps,
  FieldTemplateProps,
  ObjectFieldTemplateProps,
  RegistryWidgetsType,
  RJSFSchema,
  TemplatesType,
  WidgetProps,
} from '@rjsf/utils';
import { Component, type ComponentType, type ErrorInfo, type ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Error boundary — catches render crashes inside RJSF
// ---------------------------------------------------------------------------
interface ErrorBoundaryProps {
  name: string;
  children: ReactNode;
}
interface ErrorBoundaryState {
  error: Error | null;
}

class RJSFErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[rjsf] ErrorBoundary(${this.props.name}) caught:`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive">
          <p className="font-medium">RJSF crash in {this.props.name}</p>
          <pre className="mt-1 whitespace-pre-wrap text-[10px]">{this.state.error.message}</pre>
          <pre className="mt-1 whitespace-pre-wrap text-[10px] text-destructive/60">
            {this.state.error.stack}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Schema helpers
// ---------------------------------------------------------------------------

/** "RoutingRule" → "Routing Rule", "MitmproxyInterceptSettings" → "Mitmproxy Intercept Settings" */
function humanizeTitle(title: string): string {
  return title.replace(/([a-z])([A-Z])/g, '$1 $2');
}

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

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

function BaseInputTemplate(props: BaseInputTemplateProps) {
  const {
    id,
    type,
    value,
    onChange,
    onBlur,
    onFocus,
    disabled,
    readonly,
    autofocus,
    placeholder,
    rawErrors,
    schema,
  } = props;
  const hasError = rawErrors && rawErrors.length > 0;
  const examples = (schema as { examples?: string[] }).examples;
  const listId = examples ? `${id}-suggestions` : undefined;
  const inputClass = `w-full rounded-md border px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 ${
    hasError
      ? 'border-destructive bg-destructive/5 focus:ring-destructive'
      : 'border-input bg-background focus:ring-ring'
  }`;
  return (
    <>
      <input
        id={id}
        list={listId}
        type={type === 'number' || type === 'integer' ? 'number' : 'text'}
        value={value ?? ''}
        placeholder={placeholder}
        disabled={disabled || readonly}
        autoFocus={autofocus}
        onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
        onBlur={(e) => onBlur?.(id, e.target.value)}
        onFocus={(e) => onFocus?.(id, e.target.value)}
        className={inputClass}
      />
      {examples && (
        <datalist id={listId}>
          {examples.map((ex) => (
            <option key={ex} value={ex} />
          ))}
        </datalist>
      )}
    </>
  );
}

function FieldTemplate(props: FieldTemplateProps) {
  const { id, label, children, rawDescription, rawErrors, schema } = props;
  if (schema.type === 'object' || schema.type === 'array') {
    return <>{children}</>;
  }
  if (schema.type === 'boolean') {
    return <div>{children}</div>;
  }
  return (
    <div className="space-y-1.5">
      <div>
        {label && (
          <label htmlFor={id} className="text-xs text-muted-foreground">
            {humanizeTitle(label)}
          </label>
        )}
        {rawDescription && (
          <p className="mt-0.5 text-[10px] text-muted-foreground/60">{rawDescription}</p>
        )}
      </div>
      {children}
      {rawErrors && rawErrors.length > 0 && (
        <p className="text-[10px] text-destructive">{rawErrors.join(', ')}</p>
      )}
    </div>
  );
}

function ObjectFieldTemplate(props: ObjectFieldTemplateProps) {
  const { title, properties, idSchema } = props;
  const isRoot = !idSchema || idSchema.$id === 'root';
  return (
    <div className="space-y-3">
      {!isRoot && title && (
        <h4 className="text-xs font-medium text-foreground">{humanizeTitle(title)}</h4>
      )}
      {properties.map((p) => (
        <div key={p.name}>{p.content}</div>
      ))}
    </div>
  );
}

function ArrayFieldItemButtonsTemplate(props: ArrayFieldItemButtonsTemplateProps) {
  const { hasRemove, disabled, readonly, onRemoveItem } = props;
  if (!hasRemove) return null;
  return (
    <button
      type="button"
      disabled={disabled || readonly}
      onClick={(e) => {
        if (window.confirm('Remove this item?')) {
          onRemoveItem(e);
        }
      }}
      title="Remove item"
      className="flex h-5 w-5 items-center justify-center rounded-full border border-muted-foreground/30 text-muted-foreground transition-colors hover:border-destructive hover:text-destructive disabled:opacity-40"
    >
      <svg
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      >
        <path d="M2 2l6 6M8 2l-6 6" />
      </svg>
    </button>
  );
}

function ArrayFieldItemTemplate(props: ArrayFieldItemTemplateProps) {
  const { children, buttonsProps } = props;
  return (
    <div className="rounded-md border border-muted-foreground/30 p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex-1 space-y-3">{children}</div>
        <div className="ml-3 shrink-0 self-start">
          <ArrayFieldItemButtonsTemplate {...buttonsProps} />
        </div>
      </div>
    </div>
  );
}

function ArrayFieldTemplate(props: ArrayFieldTemplateProps) {
  const { title, items, canAdd, onAddClick } = props;
  return (
    <div className="space-y-3">
      {title && <h4 className="text-xs font-medium text-foreground">{humanizeTitle(title)}</h4>}
      {items}
      {canAdd && (
        <button
          type="button"
          onClick={onAddClick}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          + Add item
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Widgets
// ---------------------------------------------------------------------------

function CheckboxWidget(props: WidgetProps) {
  const { id, value, onChange, label, disabled, readonly } = props;
  return (
    <label htmlFor={id} className="flex items-center gap-2.5 text-xs text-foreground">
      <input
        id={id}
        type="checkbox"
        checked={Boolean(value)}
        disabled={disabled || readonly}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 rounded border-input"
      />
      {label}
    </label>
  );
}

function SelectWidget(props: WidgetProps) {
  const { id, value, onChange, disabled, readonly, options, rawErrors } = props;
  const enumOptions = (options?.enumOptions ?? []) as { value: string; label: string }[];
  const hasError = rawErrors && rawErrors.length > 0;
  return (
    <select
      id={id}
      value={value ?? ''}
      disabled={disabled || readonly}
      onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
      className={`w-full appearance-none rounded-md border px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 ${
        hasError
          ? 'border-destructive bg-destructive/5 focus:ring-destructive'
          : 'border-input bg-background focus:ring-ring'
      }`}
    >
      <option value="">Select...</option>
      {enumOptions.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------
// Theme assembly
// ---------------------------------------------------------------------------

const templates: Partial<TemplatesType> = {
  BaseInputTemplate: BaseInputTemplate as ComponentType<BaseInputTemplateProps>,
  FieldTemplate: FieldTemplate as ComponentType<FieldTemplateProps>,
  ObjectFieldTemplate: ObjectFieldTemplate as ComponentType<ObjectFieldTemplateProps>,
  ArrayFieldTemplate: ArrayFieldTemplate as ComponentType<ArrayFieldTemplateProps>,
  ArrayFieldItemTemplate: ArrayFieldItemTemplate as ComponentType<ArrayFieldItemTemplateProps>,
  ArrayFieldItemButtonsTemplate:
    ArrayFieldItemButtonsTemplate as ComponentType<ArrayFieldItemButtonsTemplateProps>,
};

const widgets: RegistryWidgetsType = {
  CheckboxWidget: CheckboxWidget as ComponentType<WidgetProps>,
  SelectWidget: SelectWidget as ComponentType<WidgetProps>,
};

// ---------------------------------------------------------------------------
// Export: pre-themed Form component
// ---------------------------------------------------------------------------

export function ThemedForm<T = unknown>(props: Omit<FormProps<T>, 'templates' | 'widgets'>) {
  return (
    <RJSFErrorBoundary name="ThemedForm">
      <Form {...props} templates={templates} widgets={widgets} />
    </RJSFErrorBoundary>
  );
}
