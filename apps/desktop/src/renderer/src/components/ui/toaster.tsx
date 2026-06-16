import { useToast, type ToastVariant } from '@/hooks/use-toast';

const variantStyles: Record<ToastVariant, string> = {
  default: 'bg-card border-border text-foreground',
  success: 'bg-gain/15 border-gain/30 text-gain',
  error: 'bg-destructive/15 border-destructive/30 text-destructive',
  warning: 'bg-primary/15 border-primary/30 text-primary',
};

export function Toaster() {
  const { toasts, dismiss } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-12 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto animate-in slide-in-from-right-5 fade-in rounded-none border px-4 py-2 font-mono text-xs font-medium ${variantStyles[t.variant]}`}
          onClick={() => dismiss(t.id)}
          role="status"
        >
          {t.title && <div>{t.title}</div>}
          {t.description && (
            <div className="mt-1 text-[11px] font-normal opacity-80">{t.description}</div>
          )}
        </div>
      ))}
    </div>
  );
}
