// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { Combobox, type ComboboxOption } from '../combobox';

const OPTIONS: ComboboxOption[] = [
  { value: 'hle', label: 'News Hallucinations' },
  { value: 'livetruth', label: 'News Livetruth' },
];

afterEach(cleanup);

// Drives the pure-controlled Combobox with real state (so filtering updates as
// the parent would in production) while still spying on every onChange call.
function setup(initial = '') {
  const onChange = vi.fn();
  function Controlled() {
    const [value, setValue] = useState(initial);
    return (
      <Combobox
        value={value}
        onChange={(v) => {
          onChange(v);
          setValue(v);
        }}
        options={OPTIONS}
        placeholder="Select a benchmark"
        aria-label="Benchmark"
      />
    );
  }
  render(<Controlled />);
  const input = screen.getByRole('combobox', { name: 'Benchmark' }) as HTMLInputElement;
  return { onChange, input };
}

describe('Combobox', () => {
  it('shows all options on focus and filters by value or label', () => {
    const { input } = setup();
    fireEvent.focus(input);
    expect(screen.getByRole('option', { name: /hle/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /livetruth/i })).toBeInTheDocument();
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
    fireEvent.keyDown(input, { key: 'ArrowDown' });
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

  it('keeps Enter selection valid after filtering narrows the list', () => {
    const { input, onChange } = setup();
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: 'ArrowDown' }); // highlight index 1 (livetruth)
    fireEvent.change(input, { target: { value: 'hle' } }); // list narrows to [hle]; active clamps to 0
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenLastCalledWith('hle');
  });
});
