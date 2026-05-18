import { useSyncExternalStore, useCallback } from 'react';

export type ToastVariant = 'default' | 'success' | 'error' | 'warning';

export interface Toast {
  id: string;
  title?: string;
  description?: string;
  variant: ToastVariant;
  duration: number;
}

export interface ToastOptions {
  title?: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

type ToastInput = string | ToastOptions;

type Listener = () => void;

let nextId = 0;
let toasts: Toast[] = [];
const listeners = new Set<Listener>();

function emit() {
  for (const l of listeners) l();
}

function addToast(input: ToastInput, variant: ToastVariant = 'default', duration = 3000): string {
  const id = String(++nextId);
  const toast =
    typeof input === 'string'
      ? { id, title: input, variant, duration }
      : {
          id,
          title: input.title,
          description: input.description,
          variant: input.variant ?? variant,
          duration: input.duration ?? duration,
        };

  toasts = [...toasts, toast];
  emit();
  setTimeout(() => dismiss(id), toast.duration);
  return id;
}

function dismiss(id: string) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

function getSnapshot() {
  return toasts;
}

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useToast() {
  const items = useSyncExternalStore(subscribe, getSnapshot);

  const toast = useCallback((input: ToastInput, variant?: ToastVariant, duration?: number) => {
    return addToast(input, variant, duration);
  }, []);

  return { toasts: items, toast, dismiss };
}

// Direct access for non-component code
export const toast = addToast;
export { dismiss as dismissToast };
