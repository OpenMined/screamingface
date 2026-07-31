export type Tone = 'neutral' | 'accent' | 'danger' | 'info' | 'success'

/**
 * An inline form shown in place of a row's action button. Fully declarative:
 * the caller decides which state a row is in, so a sequence of states can be
 * rendered as a walkthrough without the row holding any of its own.
 */
export interface NbRowForm {
  /** `options` offers auth methods; `entry` collects one credential. */
  kind: 'options' | 'entry'
  /** Buttons for `options`, e.g. `['API key', 'OAuth']`. */
  choices?: string[]
  /** Placeholder for `entry`. */
  placeholder?: string
  /** Value shown in the field; rendered as dots when `secret`. */
  value?: string
  secret?: boolean
  /** Confirm button label. Omit to hide. */
  confirm?: string
  /** Cancel button label. Omit to hide. */
  cancel?: string
  /** Renders the field as focused, for a walkthrough step. */
  focused?: boolean
}

/** A row in a NbRowList — providers, models, datasets, anything addressable. */
export interface NbRow {
  id: string
  label: string
  /** Second line under the label, e.g. a version or route */
  sublabel?: string
  /** Right-aligned monospace status text */
  status?: string
  tone?: Tone
  /** Action button label. Omit for a read-only row. */
  action?: string
  /** Renders the action as a ghost (outlined) button */
  actionGhost?: boolean
  busy?: boolean
  disabled?: boolean
  /** Shown instead of the action button while a connection is being set up. */
  form?: NbRowForm
}

export interface NbStat {
  label: string
  value: string | number
}

export interface NbCheckItem {
  label: string
  done?: boolean
}

export interface NbScoreRow {
  id: string
  label: string
  sublabel?: string
  /** Numeric magnitude driving the bar */
  value: number
  /** Overrides the formatted value, e.g. "88.0%" */
  valueLabel?: string
  /** Secondary metric, right-aligned before the score */
  meta?: string
  metaSub?: string
  selectable?: boolean
}
