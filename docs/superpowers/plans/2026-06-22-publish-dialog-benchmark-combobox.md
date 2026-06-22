# Publish Dialog: Manual Benchmark Combobox + Full-Height URL4 Field — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the auto-derived read-only benchmark field in the Publish-to-Leaderboard dialog with a manual, filterable combobox (registered list + free text, blank default), and make the read-only URL4 field grow to full content height so the dialog has a single scrollbar.

**Architecture:** Desktop-only (`apps/desktop`). A new reusable `Combobox` UI primitive (no new deps) feeds from the already-committed `useKnownBenchmarks()` registry layer. The dialog drops the SF-300 derived-id display + consistency gate but still computes the content signature (sent as payload metadata) and reuses `checkBenchmarkRegistration` for an advisory hint on the chosen value. A small pure `clampEditorHeight` helper plus a `maxContentHeight` prop lets `Url4MonacoEditor` opt out of its 360px cap.

**Tech Stack:** React 19 + TypeScript + Vite + Tailwind v4 + Vitest/jsdom + Monaco (`@monaco-editor/react`).

**Spec:** `docs/superpowers/specs/2026-06-22-publish-dialog-benchmark-combobox-and-url4-height-design.md`

**Branch:** `SF-309-publish-benchmark-combobox` (already created, off the SF-300 registry-validation baseline).

---

## File Structure

| File | Responsibility | Action |
| --- | --- | --- |
| `apps/desktop/src/renderer/src/components/ui/combobox.tsx` | Reusable filterable combobox primitive (input + listbox, keyboard, a11y) | Create |
| `apps/desktop/src/renderer/src/components/ui/__tests__/combobox.test.tsx` | Combobox unit tests | Create |
| `apps/desktop/src/renderer/src/lib/editor-height.ts` | Pure `clampEditorHeight(contentHeight, maxContentHeight)` | Create |
| `apps/desktop/src/renderer/src/lib/__tests__/editor-height.test.ts` | Height-clamp unit tests | Create |
| `apps/desktop/src/renderer/src/components/Url4MonacoEditor.tsx` | Use `clampEditorHeight` + new `maxContentHeight` prop + release wheel capture | Modify |
| `apps/desktop/src/renderer/src/components/Url4Field.tsx` | Thread `maxContentHeight` prop through | Modify |
| `apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx` | Combobox replaces derived display; gating/payload; URL4 full height | Modify |
| `apps/desktop/src/renderer/src/components/eval/__tests__/PublishToLeaderboardDialog.test.tsx` | Rewrite benchmark-related tests for manual pick | Modify |

**Reused as-is (no edits):** `hooks/use-known-benchmarks.ts`, `lib/benchmark-identity.ts` (`computeContentSignature`, `checkBenchmarkRegistration`), `main/services/list-benchmarks.ts`, `publish:listBenchmarks` IPC, `hooks/use-publish-score.ts` (`PublishInputs` already carries `benchmarkSignature`).

---

## Task 1: Reusable `Combobox` primitive

**Files:**
- Create: `apps/desktop/src/renderer/src/components/ui/combobox.tsx`
- Test: `apps/desktop/src/renderer/src/components/ui/__tests__/combobox.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/renderer/src/components/ui/__tests__/combobox.test.tsx`:

```tsx
// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { Combobox, type ComboboxOption } from '../combobox';

const OPTIONS: ComboboxOption[] = [
  { value: 'hle', label: 'News Hallucinations' },
  { value: 'livetruth', label: 'News Livetruth' },
];

afterEach(cleanup);

function setup(value = '') {
  const onChange = vi.fn();
  render(
    <Combobox value={value} onChange={onChange} options={OPTIONS} placeholder="Select a benchmark" aria-label="Benchmark" />,
  );
  const input = screen.getByRole('combobox', { name: 'Benchmark' }) as HTMLInputElement;
  return { onChange, input };
}

describe('Combobox', () => {
  it('shows all options on focus and filters by value or label', () => {
    const { input } = setup();
    fireEvent.focus(input);
    expect(screen.getByRole('option', { name: /hle/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /livetruth/i })).toBeInTheDocument();
    // Filter by label substring ("truth") — only livetruth remains.
    fireEvent.change(input, { target: { value: 'truth' } });
    expect(screen.queryByRole('option', { name: /hle/i })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: /livetruth/i })).toBeInTheDocument();
  });

  it('passes free text straight through onChange', () => {
    const { input, onChange } = setup();
    fireEvent.change(input, { target: { value: 'custom-id' } });
    expect(onChange).toHaveBeenLastCalledWith('custom-id');
  });

  it('selecting an option emits its value and closes the list', () => {
    const { input, onChange } = setup();
    fireEvent.focus(input);
    fireEvent.mouseDown(screen.getByRole('option', { name: /livetruth/i }));
    expect(onChange).toHaveBeenLastCalledWith('livetruth');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('keyboard: ArrowDown + Enter selects the highlighted option', () => {
    const { input, onChange } = setup();
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: 'ArrowDown' }); // highlight index 1 (livetruth)
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenLastCalledWith('livetruth');
  });

  it('Escape closes the list without changing the value', () => {
    const { input, onChange } = setup();
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/ui/__tests__/combobox.test.tsx`
Expected: FAIL — `Failed to resolve import "../combobox"`.

- [ ] **Step 3: Implement the component**

Create `apps/desktop/src/renderer/src/components/ui/combobox.tsx`:

```tsx
// apps/desktop/src/renderer/src/components/ui/combobox.tsx
//
// Minimal, dependency-free filterable combobox: a text input plus a filtered
// listbox. Free text is allowed (the input value IS the value), and the list
// offers known options. Brand-styled (square, hairline, mono ids). Keyboard:
// ArrowUp/Down move the highlight, Enter selects it, Escape closes.
import { useId, useMemo, useRef, useState } from 'react';

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
          // Delay close so a mouse selection on an option still registers.
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
                // mousedown fires before the input's blur, so the click isn't lost.
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/ui/__tests__/combobox.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/components/ui/combobox.tsx \
        apps/desktop/src/renderer/src/components/ui/__tests__/combobox.test.tsx
git commit -m "SF-309: add reusable filterable Combobox primitive

Brand-styled, dependency-free combobox (input + filtered listbox) with free-text
entry and keyboard nav, for the publish dialog's manual benchmark picker.

https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215924460243610"
```

---

## Task 2: Wire the combobox into the publish dialog

**Files:**
- Modify: `apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx`
- Modify (rewrite benchmark tests): `apps/desktop/src/renderer/src/components/eval/__tests__/PublishToLeaderboardDialog.test.tsx`

### Behavior being implemented
- Benchmark becomes a `Combobox` (blank default, registered options + free text).
- Advisory hint (✓ registered / ⚠ not-registered + suggestion) computed on the **current combobox value**, silent while loading/unreachable.
- The content **signature** is still computed (via `computeContentSignature`) and sent as `benchmarkSignature`.
- `canPublish = !blockReason && benchmarkId.trim() && specId.trim() && redactionResolved`. The SF-300 `verifyIdentityConsistency` gate is removed.

- [ ] **Step 1: Rewrite the benchmark-related dialog tests (failing)**

Replace the whole file `apps/desktop/src/renderer/src/components/eval/__tests__/PublishToLeaderboardDialog.test.tsx` with:

```tsx
// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { PublishToLeaderboardDialog } from '../PublishToLeaderboardDialog';
import type { EvalRunDetail } from '../types';

const publishMock = vi.fn();
const toastMock = vi.fn();
const listBenchmarksMock = vi.fn();
const hookState: {
  status: 'idle' | 'submitting' | 'success' | 'error';
  error: string | null;
  result: { id: string; benchmarkId: string; specId: string; portalLink: string } | null;
} = { status: 'idle', error: null, result: null };

vi.mock('@/hooks/use-publish-score', () => ({
  usePublishScore: () => ({
    publish: publishMock,
    status: hookState.status,
    error: hookState.error,
    result: hookState.result,
  }),
}));
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: toastMock }) }));
vi.mock('@/components/Url4Field', () => ({
  Url4Field: ({ value }: { value: string }) => <span data-testid="url4">{value}</span>,
}));

const QUESTIONS: EvalRunDetail['questions'] = [
  {
    id: 'q-0',
    idx: 0,
    question: '2+2?',
    expected: '4',
    predicted: '4',
    correct: true,
    raw_output: null,
    error: null,
  },
];

function makeRun(overrides: Partial<EvalRunDetail> = {}): EvalRunDetail {
  return {
    id: 'eval-run-1',
    spec_name: 'hle:hle-ensemble-three',
    url4_expression:
      'https://screamingface.ai/honest-agi-live-week-3.eval.jsonl*(/claude($item.question))',
    started_at: '2026-05-04T11:00:00Z',
    finished_at: '2026-05-04T11:55:00Z',
    status: 'done',
    accuracy: 0.81,
    total_questions: 1000,
    correct_questions: 810,
    error: null,
    favorite: false,
    questions: QUESTIONS,
    ...overrides,
  };
}

function benchmarkInput(): HTMLInputElement {
  return screen.getByRole('combobox', { name: 'Benchmark' }) as HTMLInputElement;
}

afterEach(cleanup);

beforeEach(() => {
  publishMock.mockReset();
  toastMock.mockReset();
  hookState.status = 'idle';
  hookState.error = null;
  hookState.result = null;
  window.sessionStorage.clear();
  listBenchmarksMock
    .mockReset()
    .mockResolvedValue([
      { id: 'hle', displayName: 'News Hallucinations' },
      { id: 'livetruth', displayName: 'News Livetruth' },
    ]);
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    publish: {
      openExternal: vi.fn(async () => {}),
      getContext: vi.fn(),
      listBenchmarks: listBenchmarksMock,
    },
  };
});

describe('PublishToLeaderboardDialog — benchmark combobox', () => {
  it('opens with a blank benchmark and Publish disabled until one is chosen', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(benchmarkInput().value).toBe('');
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
    // Choosing a registered benchmark enables publish.
    fireEvent.focus(benchmarkInput());
    fireEvent.mouseDown(await screen.findByRole('option', { name: /livetruth/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
  });

  it('filters registered benchmarks and allows free text', () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'live' } });
    expect(screen.getByRole('option', { name: /livetruth/i })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /^hle/i })).not.toBeInTheDocument();
    // Free text that matches nothing keeps the typed value.
    fireEvent.change(benchmarkInput(), { target: { value: 'brand-new-2026' } });
    expect(benchmarkInput().value).toBe('brand-new-2026');
  });

  it('shows ✓ registered for a registered value and ⚠ + suggestion for an unknown one', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'hle' } });
    expect(await screen.findByText(/registered benchmark/i)).toBeInTheDocument();
    // A near-miss of a registered id → not-registered warning with did-you-mean.
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruh' } });
    expect(await screen.findByText(/not a registered scoreboard benchmark/i)).toBeInTheDocument();
    expect(screen.getByText('livetruth')).toBeInTheDocument();
    // Advisory only — publish stays enabled.
    expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled();
  });

  it('stays silent about registration while the registry is unreachable', async () => {
    listBenchmarksMock.mockResolvedValue(null);
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'whatever' } });
    await Promise.resolve();
    expect(screen.queryByText(/registered benchmark/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not a registered scoreboard benchmark/i)).not.toBeInTheDocument();
  });

  it('publishes the chosen benchmark id plus the content signature', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruth' } });
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    await waitFor(() => expect(publishMock).toHaveBeenCalledTimes(1));
    const sent = publishMock.mock.calls[0][0];
    expect(sent.benchmarkId).toBe('livetruth');
    expect(sent.benchmarkSignature).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe('PublishToLeaderboardDialog — guards & misc', () => {
  it('prefills spec id from the colon-delimited spec_name', () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByDisplayValue('hle-ensemble-three')).toBeInTheDocument();
  });

  it('blocks a zero-question run with an explanation (preflight guard)', () => {
    render(
      <PublishToLeaderboardDialog
        run={makeRun({ total_questions: 0, correct_questions: 0 })}
        serverUrl=""
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/no graded questions/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
  });

  it('warns about /data refs and publishes the sanitized expression by default', async () => {
    const run = makeRun({ url4_expression: '(/data/abc123)!$prompt' });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByText(/references local/i)).toBeInTheDocument();
    expect(screen.getByTestId('url4')).toHaveTextContent('/data/<redacted>');
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruth' } });
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    expect(publishMock).toHaveBeenCalledTimes(1);
    expect(publishMock.mock.calls[0][0].url4Expression).toContain('/data/<redacted>');
  });

  it('blocks publish if /data refs are neither sanitized nor acknowledged', async () => {
    const run = makeRun({ url4_expression: '(/data/abc123)!$prompt' });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruth' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /sanitize/i })); // uncheck
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /exposes my local data/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
  });

  it('persists the submitter name to sessionStorage on publish', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruth' } });
    fireEvent.change(screen.getByPlaceholderText('leave blank for anonymous'), {
      target: { value: 'Ada Lovelace' },
    });
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    expect(window.sessionStorage.getItem('sf-leaderboard-submitter')).toBe('Ada Lovelace');
  });

  it('prefills the submitter name from sessionStorage on open', () => {
    window.sessionStorage.setItem('sf-leaderboard-submitter', 'Grace Hopper');
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByPlaceholderText('leave blank for anonymous')).toHaveValue('Grace Hopper');
  });

  it('shows the success state and opens the leaderboard deep link', () => {
    hookState.status = 'success';
    hookState.result = {
      id: 'score-1',
      benchmarkId: 'hle',
      specId: 'hle-ensemble-three',
      portalLink: 'http://localhost:8080/spec.html?benchmark=hle&spec=hle-ensemble-three',
    };
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /view on leaderboard/i }));
    expect(
      (
        window as unknown as {
          electronAPI: { publish: { openExternal: ReturnType<typeof vi.fn> } };
        }
      ).electronAPI.publish.openExternal,
    ).toHaveBeenCalledWith('http://localhost:8080/spec.html?benchmark=hle&spec=hle-ensemble-three');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/eval/__tests__/PublishToLeaderboardDialog.test.tsx`
Expected: FAIL — no `combobox` role (the dialog still renders the read-only `benchmark-identity` div).

- [ ] **Step 3: Edit the dialog — imports**

In `apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx`, replace the benchmark-identity import block:

```tsx
import {
  deriveBenchmarkIdentity,
  verifyIdentityConsistency,
  checkBenchmarkRegistration,
  type BenchmarkIdentity,
} from '@/lib/benchmark-identity';
```

with:

```tsx
import { computeContentSignature, checkBenchmarkRegistration } from '@/lib/benchmark-identity';
import { Combobox } from '@/components/ui/combobox';
```

- [ ] **Step 4: Edit the dialog — state, signature, gating**

Replace the identity state/effect block:

```tsx
  const [identity, setIdentity] = useState<BenchmarkIdentity | null>(null);
  useEffect(() => {
    let cancelled = false;
    void deriveBenchmarkIdentity(run).then((next) => {
      if (!cancelled) setIdentity(next);
    });
    return () => {
      cancelled = true;
    };
  }, [run]);

  const [specId, setSpecId] = useState(parsed.spec_id);
```

with:

```tsx
  // Manual benchmark selection (SF-309): blank default, registered list + free text.
  const [benchmarkId, setBenchmarkId] = useState('');
  // The content signature still travels with the publish as metadata so the
  // scoreboard can later verify what actually ran — computed, never displayed.
  const [signature, setSignature] = useState('');
  useEffect(() => {
    let cancelled = false;
    void computeContentSignature(run).then((sig) => {
      if (!cancelled) setSignature(sig);
    });
    return () => {
      cancelled = true;
    };
  }, [run]);

  const [specId, setSpecId] = useState(parsed.spec_id);
```

Replace the `identityCheck` + `registryCheck` block:

```tsx
  const identityCheck = useMemo(
    () => (identity ? verifyIdentityConsistency(identity) : { ok: false, reason: null }),
    [identity],
  );
  const { benchmarks: knownBenchmarks, loading: benchmarksLoading } = useKnownBenchmarks();
  const registryCheck = useMemo(
    () =>
      checkBenchmarkRegistration(
        identity?.id ?? '',
        benchmarksLoading ? null : (knownBenchmarks?.map((b) => b.id) ?? null),
      ),
    [identity, knownBenchmarks, benchmarksLoading],
  );
```

with:

```tsx
  const { benchmarks: knownBenchmarks, loading: benchmarksLoading } = useKnownBenchmarks();
  const benchmarkOptions = useMemo(
    () => (knownBenchmarks ?? []).map((b) => ({ value: b.id, label: b.displayName })),
    [knownBenchmarks],
  );
  // Advisory registry check on the CURRENT field value (not a derived id).
  const registryCheck = useMemo(
    () =>
      checkBenchmarkRegistration(
        benchmarkId.trim(),
        benchmarksLoading ? null : (knownBenchmarks?.map((b) => b.id) ?? null),
      ),
    [benchmarkId, knownBenchmarks, benchmarksLoading],
  );
```

Replace the `canPublish` definition:

```tsx
  const canPublish =
    !blockReason && !!identity && identityCheck.ok && specId.trim().length > 0 && redactionResolved;
```

with:

```tsx
  const canPublish =
    !blockReason &&
    benchmarkId.trim().length > 0 &&
    specId.trim().length > 0 &&
    redactionResolved;
```

- [ ] **Step 5: Edit the dialog — handlePublish payload**

Replace the body of `handlePublish`:

```tsx
  const handlePublish = async (): Promise<void> => {
    if (!identity) return;
    saveSubmitter(submittedBy.trim());
    const out = await publish({
      run,
      benchmarkId: identity.id,
      benchmarkSignature: identity.signature,
      specId: specId.trim(),
      url4Expression: expressionToPublish,
      providers,
      submittedBy: submittedBy.trim() || null,
    });
```

with:

```tsx
  const handlePublish = async (): Promise<void> => {
    saveSubmitter(submittedBy.trim());
    const out = await publish({
      run,
      benchmarkId: benchmarkId.trim(),
      benchmarkSignature: signature,
      specId: specId.trim(),
      url4Expression: expressionToPublish,
      providers,
      submittedBy: submittedBy.trim() || null,
    });
```

- [ ] **Step 6: Edit the dialog — replace the benchmark JSX**

Replace the entire benchmark-identity `<div className="block">…</div>` (the first column inside `{/* benchmark identity (auto-derived, read-only) + spec id */}`, from `<div className="block">` through its closing `</div>` just before the Spec ID `<label>`) with:

```tsx
                <div className="block">
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">
                    Benchmark <span className="text-destructive">*</span>
                  </span>
                  <Combobox
                    value={benchmarkId}
                    onChange={setBenchmarkId}
                    options={benchmarkOptions}
                    placeholder="Select a benchmark"
                    aria-label="Benchmark"
                  />
                  {registryCheck.status === 'registered' && (
                    <p className="mt-1 flex items-center gap-1 text-[11px] text-gain">
                      <CheckCircle2 className="h-3 w-3 shrink-0" />
                      Registered benchmark
                    </p>
                  )}
                  {registryCheck.status === 'unknown' && (
                    <p className="mt-1 flex items-start gap-1 text-[11px] leading-relaxed text-destructive">
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                      <span>
                        Not a registered scoreboard benchmark — publishing will fail until the
                        scoreboard owner registers{' '}
                        <code className="font-mono">{benchmarkId.trim()}</code>.
                        {registryCheck.suggestion && (
                          <>
                            {' '}
                            Did you mean{' '}
                            <code className="font-mono">{registryCheck.suggestion}</code>?
                          </>
                        )}
                      </span>
                    </p>
                  )}
                </div>
```

Then delete the now-orphaned identity-consistency block:

```tsx
              {/* Identity consistency: id<->signature must agree before publish. */}
              {identity && !identityCheck.ok && identityCheck.reason && (
                <div className="flex items-start gap-1.5 rounded-none border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>{identityCheck.reason}</span>
                </div>
              )}
```

- [ ] **Step 7: Run the dialog tests to verify they pass**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/eval/__tests__/PublishToLeaderboardDialog.test.tsx`
Expected: PASS (all describe blocks).

If a test referencing `useMemo`/`useEffect`/`useState` errors on an unused import, remove any now-unused import (e.g. `BenchmarkIdentity`, `verifyIdentityConsistency`, `deriveBenchmarkIdentity`) — they were replaced in Step 3.

- [ ] **Step 8: Commit**

```bash
git add apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx \
        apps/desktop/src/renderer/src/components/eval/__tests__/PublishToLeaderboardDialog.test.tsx
git commit -m "SF-309: manual benchmark combobox in publish dialog

Replace the SF-300 auto-derived read-only benchmark with a filterable combobox
(registered list + free text, blank default). Keep computing the content
signature as payload metadata; advisory registered/not-registered hint now runs
on the chosen value; drop the id<->signature consistency gate.

https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215924460243610"
```

---

## Task 3: Full-height URL4 field (single scrollbar)

**Files:**
- Create: `apps/desktop/src/renderer/src/lib/editor-height.ts`
- Test: `apps/desktop/src/renderer/src/lib/__tests__/editor-height.test.ts`
- Modify: `apps/desktop/src/renderer/src/components/Url4MonacoEditor.tsx`
- Modify: `apps/desktop/src/renderer/src/components/Url4Field.tsx`
- Modify: `apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx`

- [ ] **Step 1: Write the failing height-helper test**

Create `apps/desktop/src/renderer/src/lib/__tests__/editor-height.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { clampEditorHeight } from '../editor-height';

describe('clampEditorHeight', () => {
  it('floors at 28px', () => {
    expect(clampEditorHeight(10, 360)).toBe(28);
  });
  it('caps at the given maximum', () => {
    expect(clampEditorHeight(500, 360)).toBe(360);
  });
  it('returns content height between the floor and the cap', () => {
    expect(clampEditorHeight(120, 360)).toBe(120);
  });
  it('removes the cap when max is null (full content height)', () => {
    expect(clampEditorHeight(5000, null)).toBe(5000);
    expect(clampEditorHeight(10, null)).toBe(28);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/desktop && npx vitest run src/renderer/src/lib/__tests__/editor-height.test.ts`
Expected: FAIL — `Failed to resolve import "../editor-height"`.

- [ ] **Step 3: Implement the helper**

Create `apps/desktop/src/renderer/src/lib/editor-height.ts`:

```ts
// apps/desktop/src/renderer/src/lib/editor-height.ts
//
// Pure height-clamp for the url4 Monaco editor's auto-grow. Extracted so the cap
// logic is unit-testable without mounting Monaco. `maxContentHeight === null`
// means "no upper cap" — grow to the full content height (SF-309) so the editor
// never shows its own scrollbar inside a scrolling dialog.

const MIN_HEIGHT = 28;

export function clampEditorHeight(contentHeight: number, maxContentHeight: number | null): number {
  const lower = Math.max(contentHeight, MIN_HEIGHT);
  return maxContentHeight == null ? lower : Math.min(lower, maxContentHeight);
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd apps/desktop && npx vitest run src/renderer/src/lib/__tests__/editor-height.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Thread the prop through `Url4Field`**

In `apps/desktop/src/renderer/src/components/Url4Field.tsx`, add `maxContentHeight` to the props interface (props already spread to the editor via `{...props}`, so no other change needed):

```tsx
interface Url4FieldProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  serverUrl: string;
  className?: string;
  /** Upper bound for the editor's auto-grow height; null = grow to full content (no inner scrollbar). Defaults to 360. */
  maxContentHeight?: number | null;
}
```

- [ ] **Step 6: Use the helper + new prop in `Url4MonacoEditor`**

In `apps/desktop/src/renderer/src/components/Url4MonacoEditor.tsx`:

Add the import near the top:

```tsx
import { clampEditorHeight } from '@/lib/editor-height';
```

Add `maxContentHeight` to the `Props` interface and destructure it (default 360):

```tsx
interface Props {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  serverUrl: string;
  className?: string;
  maxContentHeight?: number | null;
}

export default function Url4MonacoEditor({
  value,
  onChange,
  readOnly,
  serverUrl,
  className,
  maxContentHeight = 360,
}: Props) {
```

Replace the `applyHeight` body:

```tsx
    const applyHeight = (): void => {
      const h = Math.min(Math.max(editor.getContentHeight(), 28), 360);
      if (wrapRef.current) wrapRef.current.style.height = `${h}px`;
      editor.layout();
    };
```

with:

```tsx
    const applyHeight = (): void => {
      const h = clampEditorHeight(editor.getContentHeight(), maxContentHeight);
      if (wrapRef.current) wrapRef.current.style.height = `${h}px`;
      editor.layout();
    };
```

In the editor `options`, change the `scrollbar` line so wheel events bubble to the surrounding scroll container when the editor is at full height:

```tsx
          scrollbar: { horizontalScrollbarSize: 0, verticalScrollbarSize: 8 },
```

to:

```tsx
          scrollbar: {
            horizontalScrollbarSize: 0,
            verticalScrollbarSize: 8,
            alwaysConsumeMouseWheel: false,
          },
```

- [ ] **Step 7: Pass `maxContentHeight={null}` from the dialog**

In `apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx`, update the read-only `Url4Field` usage:

```tsx
                  <Url4Field value={expressionToPublish} serverUrl={serverUrl} readOnly />
```

to:

```tsx
                  <Url4Field
                    value={expressionToPublish}
                    serverUrl={serverUrl}
                    readOnly
                    maxContentHeight={null}
                  />
```

- [ ] **Step 8: Run the editor-height + dialog tests**

Run: `cd apps/desktop && npx vitest run src/renderer/src/lib/__tests__/editor-height.test.ts src/renderer/src/components/eval/__tests__/PublishToLeaderboardDialog.test.tsx`
Expected: PASS (the dialog mocks `Url4Field`, so the new prop is inert in tests; the height logic is covered by the helper test).

- [ ] **Step 9: Commit**

```bash
git add apps/desktop/src/renderer/src/lib/editor-height.ts \
        apps/desktop/src/renderer/src/lib/__tests__/editor-height.test.ts \
        apps/desktop/src/renderer/src/components/Url4MonacoEditor.tsx \
        apps/desktop/src/renderer/src/components/Url4Field.tsx \
        apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx
git commit -m "SF-309: full-height URL4 field in publish dialog (single scrollbar)

Extract a pure clampEditorHeight helper and add a maxContentHeight prop to
Url4Field/Url4MonacoEditor; pass null from the publish dialog so the read-only
expression grows to full content height (and release Monaco's wheel capture), so
the dialog has a single scrollbar instead of a nested one.

https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215924460243610"
```

---

## Task 4: Full verification & PR

**Files:** none (verification only).

- [ ] **Step 1: Full desktop test suite**

Run: `cd apps/desktop && npx vitest run`
Expected: PASS — all files (the prior 278 baseline plus the new `combobox`, `editor-height`, and rewritten dialog tests).

- [ ] **Step 2: Build (typechecks main + preload + renderer)**

Run: `cd apps/desktop && npm run build`
Expected: `✓ built` with no TypeScript errors.

- [ ] **Step 3: Manual verification in the app**

Per the project rule, close any running dev app first, then run a single instance:

```bash
cd apps/desktop && npm run dev
```

Open Eval Studio → a completed run → **Publish to Leaderboard** and confirm:
1. Benchmark field is **blank** with a "Select a benchmark" placeholder; Publish is disabled.
2. Focus/typing shows a filterable list of registered benchmarks (`id — display name`); arrow keys + Enter select; typing a custom id is allowed.
3. A registered value shows ✓ "Registered benchmark"; an unknown value shows ⚠ + "Did you mean …"; Publish stays enabled either way.
4. The **URL4 expression** block shows the full expression with **no inner scrollbar**, and scrolling over it scrolls the whole dialog (single scrollbar).

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin SF-309-publish-benchmark-combobox
gh pr create --title "SF-309: manual benchmark combobox + full-height URL4 field in publish dialog" --body "$(cat <<'BODY'
Implements docs/superpowers/specs/2026-06-22-publish-dialog-benchmark-combobox-and-url4-height-design.md.

- Reusable `Combobox` primitive (no new deps).
- Publish dialog benchmark = manual combobox (registered list + free text, blank default); content signature still sent as metadata; advisory registered/not-registered hint on the chosen value; consistency gate dropped.
- Read-only URL4 field grows to full content height (single scrollbar) via a `maxContentHeight` prop + `clampEditorHeight` helper + released Monaco wheel capture.
- Builds on the SF-300 registry-validation commit on this branch.

Asana: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215924460243610
BODY
)"
```

Note: this branch also carries the SF-300 registry-validation commit (`6817e2e`) that the combobox builds on; it lands with this PR unless the team prefers to split it.

---

## Notes / decisions baked in (from the approved spec)

- **Free-text 404 is accepted** — a typed unregistered id still 404s on publish, surfaced verbatim by the existing error handling; the ⚠ hint warns first.
- **Trust trade-off acknowledged** — manual pick reverses SF-300's lock (a score can be published under a benchmark the run didn't execute against). The signature still records the true content; server-side verification remains a future follow-up.
- **`computeContentSignature` empty signature** (e.g. a run with no question rows) is sent as an empty string — best-effort metadata, not a publish gate; the zero-question case is still blocked by `publish-guard` on the totals.
