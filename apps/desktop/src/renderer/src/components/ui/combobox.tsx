// apps/desktop/src/renderer/src/components/ui/combobox.tsx
//
// Minimal, dependency-free filterable combobox: a text input plus a filtered
// listbox, with a clear (✕) button and a chevron toggle. Pure controlled — the
// `value` prop is the single source of truth; typing/selecting/clearing calls
// `onChange`. Free text is allowed. While typing, the list filters by the value;
// when reopened by focus/click/chevron it shows ALL options so alternatives stay
// visible even with a value set. Brand-styled (square, hairline, mono ids).
// Keyboard: ArrowUp/Down move the highlight, Enter selects it, Escape closes.
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';

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
  // Distinguishes "typing" (filter by value) from "browsing" (show all options).
  const [typing, setTyping] = useState(false);
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const filtered = useMemo(() => {
    const q = value.trim().toLowerCase();
    // Only filter while actively typing — browsing shows the full list.
    if (!typing || q.length === 0) return options;
    return options.filter(
      (o) => o.value.toLowerCase().includes(q) || o.label.toLowerCase().includes(q),
    );
  }, [options, value, typing]);

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
    setTyping(false);
    setOpen(false);
  };

  // Open the list in "browse" mode (all options), as opposed to typing/filtering.
  const openBrowsing = (): void => {
    setTyping(false);
    setActive(0);
    setOpen(true);
  };

  const clearValue = (): void => {
    onChange('');
    openBrowsing();
    inputRef.current?.focus();
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
        ref={inputRef}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && filtered[active] ? `${listId}-${active}` : undefined}
        aria-label={ariaLabel}
        className="w-full rounded-none border border-border bg-background py-2 pl-3 pr-14 text-sm"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => {
          onChange(e.target.value);
          setTyping(true);
          setOpen(true);
          setActive(0);
        }}
        onFocus={openBrowsing}
        onBlur={() => {
          blurTimer.current = setTimeout(() => setOpen(false), 120);
        }}
        onKeyDown={onKeyDown}
      />
      {/* Trailing controls: clear (when a value is set) + chevron toggle. Both use
          onMouseDown+preventDefault so the input doesn't blur-close before the click,
          and tabIndex=-1 since the input is the single focusable control. */}
      <div className="absolute inset-y-0 right-0 flex items-center gap-0.5 pr-1.5">
        {value.length > 0 && !disabled && (
          <button
            type="button"
            aria-label="Clear"
            tabIndex={-1}
            className="text-muted-foreground transition-colors hover:text-foreground"
            onMouseDown={(e) => {
              e.preventDefault();
              clearValue();
            }}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          type="button"
          aria-label="Toggle options"
          aria-expanded={open}
          tabIndex={-1}
          disabled={disabled}
          className="text-muted-foreground transition-colors hover:text-foreground"
          onMouseDown={(e) => {
            e.preventDefault();
            if (open) setOpen(false);
            else openBrowsing();
            inputRef.current?.focus();
          }}
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </div>
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
