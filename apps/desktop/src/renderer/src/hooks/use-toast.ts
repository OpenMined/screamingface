import { useSyncExternalStore, useCallback } from 'react';

export type ToastVariant = 'default' | 'success' | 'error' | 'warning';

export interface Toast {
  id: string;
  message: string;
  variant: ToastVariant;
  duration: number;
}

type Listener = () => void;

let nextId = 0;
let toasts: Toast[] = [];
const listeners = new Set<Listener>();

function emit() {
  for (const l of listeners) l();
}

function addToast(message: string, variant: ToastVariant = 'default', duration = 3000): string {
  const id = String(++nextId);
  toasts = [...toasts, { id, message, variant, duration }];
  emit();
  setTimeout(() => dismiss(id), duration);
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

  const toast = useCallback((message: string, variant?: ToastVariant, duration?: number) => {
    return addToast(message, variant, duration);
  }, []);

  return { toasts: items, toast, dismiss };
}

// Direct access for non-component code
export const toast = addToast;
export { dismiss as dismissToast };
