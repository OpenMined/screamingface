// apps/desktop/src/renderer/src/components/CopyButton.tsx
//
// Small icon button that copies a string to the clipboard and briefly shows a
// check. Shared across the url4 editing surfaces.
import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  value: string;
  className?: string;
  title?: string;
}

export function CopyButton({ value, className, title = 'Copy to clipboard' }: Props) {
  const [copied, setCopied] = useState(false);

  const copy = async (e: React.MouseEvent): Promise<void> => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — no-op */
    }
  };

  return (
    <button
      type="button"
      aria-label="Copy to clipboard"
      title={copied ? 'Copied' : title}
      onClick={(e) => void copy(e)}
      className={cn(
        'rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
        className,
      )}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-chart-3" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}
