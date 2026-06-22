// apps/desktop/src/renderer/src/components/ui/combobox.tsx
//
// Minimal, dependency-free filterable combobox: a text input plus a filtered
// listbox. Pure controlled — the `value` prop is the single source of truth and
// also drives the filter; typing/selecting calls `onChange`. Free text is
// allowed. Brand-styled (square, hairline, mono ids). Keyboard: ArrowUp/Down
// move the highlight, Enter selects it, Escape closes.
import { useEffect, useId, useMemo, useRef, useState } from 'react';

export interface ComboboxOption {
  value: string;
  label: string;
}

interface ComboboxProps {
  value: string;
  onChange: (value: string) => void;
  options: ComboboxOption[];
  placeholder?: string;
  disabled?: boolean;
  'aria-label'?: string;
}

export function Combobox({
  value,
  onChange,
  options,
  placeholder,
  disabled,
  'aria-label': ariaLabel,
}: ComboboxProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const filtered = useMemo(() => {
    const q = value.trim().toLowerCase();
    if (q.length === 0) return options;
    return options.filter(
      (o) => o.value.toLowerCase().includes(q) || o.label.toLowerCase().includes(q),
    );
  }, [options, value]);

  // Keep the highlight within the (possibly newly-filtered) list, so the visual
  // highlight, aria-activedescendant, and Enter selection never go out of bounds.
  useEffect(() => {
    setActive((i) => (filtered.length === 0 ? 0 : Math.min(i, filtered.length - 1)));
  }, [filtered]);

  // Cancel a pending blur-close if we unmount within the timeout window.
  useEffect(
    () => () => {
      if (blurTimer.current) clearTimeout(blurTimer.current);
    },
    [],
  );

  const commit = (v: string): void => {
    onChange(v);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      if (open && filtered[active]) {
        e.preventDefault();
        commit(filtered[active].value);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && filtered[active] ? `${listId}-${active}` : undefined}
        aria-label={ariaLabel}
        className="w-full rounded-none border border-border bg-background px-3 py-2 text-sm"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          blurTimer.current = setTimeout(() => setOpen(false), 120);
        }}
        onKeyDown={onKeyDown}
      />
      {open && filtered.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-48 w-full overflow-auto rounded-none border border-border bg-popover text-sm"
        >
          {filtered.map((o, i) => (
            <li
              key={o.value}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={`cursor-pointer px-3 py-1.5 ${
                i === active ? 'bg-accent text-accent-foreground' : ''
              }`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                commit(o.value);
              }}
            >
              <span className="font-mono">{o.value}</span>
              {o.label && o.label !== o.value && (
                <span className="ml-2 text-xs text-muted-foreground">{o.label}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
