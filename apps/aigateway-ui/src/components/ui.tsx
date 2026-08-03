/**
 * The console's presentational vocabulary — buttons, fields, tables, notices.
 *
 * INVARIANT: no `'use client'` here, and no imports from `src/lib/*`. These components are pure
 * props-in / JSX-out, which is what lets the SAME component render inside a Server Component (the
 * accounts table) and inside a Client Component (a form driven by `useActionState`). A directive
 * either way would break one of those two callers; data access would break the BFF rule.
 *
 * INVARIANT: no hooks. A Server Component cannot call `useId`, so `Field` derives the id it needs
 * from the control it is given (explicit `htmlFor` → the control's `id` → its `name` → the label
 * text) rather than generating one. That keeps the id stable across server render and hydration,
 * which a random id would not.
 *
 * Styling is class-only, against the SFDS v2 tokens in `src/brand/tokens/tokens.css`; every class
 * used here is defined in `src/app/globals.css` under the "UI primitives" banner.
 */
import * as React from "react";

/** Join class names, dropping the empty ones. Returns "" so callers can `|| undefined` it. */
function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/* ── Button ─────────────────────────────────────────────────────────────────────────────────── */

export type ButtonVariant = "primary" | "ghost" | "danger";

export type ButtonProps = React.ComponentPropsWithRef<"button"> & {
  variant?: ButtonVariant;
};

/**
 * NOTE: `type` is deliberately NOT defaulted. The native default inside a form is `submit`, and
 * the forms in this console are `<form action={serverAction}>` — defaulting to `"button"` would
 * turn every submit button into a no-op that looks fine. Pass `type="button"` explicitly for the
 * ones that must not submit.
 */
export function Button({ variant = "primary", className, ...props }: ButtonProps) {
  return <button className={cx("ui-btn", `ui-btn-${variant}`, className)} {...props} />;
}

/* ── Field ──────────────────────────────────────────────────────────────────────────────────── */

/** The subset of a control's props `Field` reads and writes when it wires up accessibility. */
type ControlProps = {
  id?: string;
  name?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean | "true" | "false" | "grammar" | "spelling";
};

export type FieldProps = {
  label: React.ReactNode;
  /** Overrides the derived control id. Needed only when the control is not the first element. */
  htmlFor?: string;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
};

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * A labelled control with its hint and error text.
 *
 * The first element child is treated as the control: it receives the derived `id`, and when
 * `error` is set, `aria-invalid` plus an `aria-describedby` pointing at the hint and error nodes.
 * Anything else in `children` passes through untouched.
 */
export function Field({ label, htmlFor, hint, error, className, children }: FieldProps) {
  // `toArray` keys the children for us, so the mapped output below stays a valid list.
  const items = React.Children.toArray(children);
  const controlIndex = items.findIndex((child) => React.isValidElement<ControlProps>(child));
  const control =
    controlIndex < 0 ? null : (items[controlIndex] as React.ReactElement<ControlProps>);

  const controlId =
    htmlFor ??
    control?.props.id ??
    (control?.props.name ? `field-${control.props.name}` : undefined) ??
    (typeof label === "string" ? `field-${slugify(label)}` : undefined);

  const hintId = hint && controlId ? `${controlId}-hint` : undefined;
  const errorId = error && controlId ? `${controlId}-error` : undefined;

  const body = items.map((child, index) =>
    index === controlIndex && React.isValidElement<ControlProps>(child)
      ? React.cloneElement(child, {
          id: child.props.id ?? controlId,
          "aria-invalid": error ? true : child.props["aria-invalid"],
          "aria-describedby": cx(child.props["aria-describedby"], hintId, errorId) || undefined,
        })
      : child,
  );

  return (
    <div className={cx("ui-field", className)}>
      <label className="ui-field-label" htmlFor={controlId}>
        {label}
      </label>
      {body}
      {hint ? (
        <p className="ui-field-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="ui-field-error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/* ── Form controls ──────────────────────────────────────────────────────────────────────────── */

export type InputProps = React.ComponentPropsWithRef<"input">;
export type SelectProps = React.ComponentPropsWithRef<"select">;
export type TextareaProps = React.ComponentPropsWithRef<"textarea">;

export function Input({ className, ...props }: InputProps) {
  return <input className={cx("ui-control", "ui-input", className)} {...props} />;
}

export function Select({ className, ...props }: SelectProps) {
  return <select className={cx("ui-control", "ui-select", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaProps) {
  return <textarea className={cx("ui-control", "ui-textarea", className)} {...props} />;
}

/* ── Table ──────────────────────────────────────────────────────────────────────────────────── */

/**
 * Wraps the table in its own scroll container so a wide column set scrolls inside the table
 * instead of pushing the page sideways.
 */
export function Table({ className, children, ...props }: React.ComponentPropsWithRef<"table">) {
  return (
    <div className="ui-table-scroll">
      <table className={cx("ui-table", className)} {...props}>
        {children}
      </table>
    </div>
  );
}

export function THead({ className, ...props }: React.ComponentPropsWithRef<"thead">) {
  return <thead className={cx("ui-thead", className)} {...props} />;
}

export function TBody({ className, ...props }: React.ComponentPropsWithRef<"tbody">) {
  return <tbody className={cx("ui-tbody", className)} {...props} />;
}

export function TR({ className, ...props }: React.ComponentPropsWithRef<"tr">) {
  return <tr className={cx("ui-tr", className)} {...props} />;
}

/** `scope="col"` by default — override with `scope="row"` for a row header cell. */
export function TH({ scope = "col", className, ...props }: React.ComponentPropsWithRef<"th">) {
  return <th scope={scope} className={cx("ui-th", className)} {...props} />;
}

export function TD({ className, ...props }: React.ComponentPropsWithRef<"td">) {
  return <td className={cx("ui-td", className)} {...props} />;
}

/* ── Notice ─────────────────────────────────────────────────────────────────────────────────── */

export type NoticeTone = "info" | "success" | "error";

export type NoticeProps = {
  tone: NoticeTone;
  title?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
};

/**
 * Tone is carried by the left border, not by the text colour: the tinted palette steps do not
 * theme-switch, so tone-coloured body text would fall below contrast in dark mode. The title and
 * body stay on the themed text tokens, and an error additionally announces itself via `role`.
 */
export function Notice({ tone, title, className, children }: NoticeProps) {
  return (
    <div
      className={cx("ui-notice", `ui-notice-${tone}`, className)}
      data-tone={tone}
      role={tone === "error" ? "alert" : "status"}
    >
      {title ? <p className="ui-notice-title">{title}</p> : null}
      <div className="ui-notice-body">{children}</div>
    </div>
  );
}

/* ── EmptyState ─────────────────────────────────────────────────────────────────────────────── */

export type EmptyStateProps = {
  title: React.ReactNode;
  message: React.ReactNode;
  /** Usually a `<Button>` or a link — the one thing to do about the emptiness. */
  action?: React.ReactNode;
  className?: string;
};

/**
 * The title is a `<p>`, not a heading: an empty state appears inside sections at different depths
 * and a fixed heading level would break the document outline in at least one of them.
 */
export function EmptyState({ title, message, action, className }: EmptyStateProps) {
  return (
    <div className={cx("ui-empty", className)}>
      <p className="ui-empty-title">{title}</p>
      <p className="ui-empty-message">{message}</p>
      {action ? <div className="ui-empty-action">{action}</div> : null}
    </div>
  );
}

/* ── Badge ──────────────────────────────────────────────────────────────────────────────────── */

export type BadgeTone = "neutral" | "good" | "bad";

export type BadgeProps = {
  tone?: BadgeTone;
  className?: string;
  children: React.ReactNode;
};

/** Colour is redundant here on purpose — the badge's own text is what states the fact. */
export function Badge({ tone = "neutral", className, children }: BadgeProps) {
  return (
    <span className={cx("ui-badge", `ui-badge-${tone}`, className)} data-tone={tone}>
      {children}
    </span>
  );
}
