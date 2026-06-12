import { useEffect, useRef, useState } from 'react';

import screamShaking from '@/assets/scream-shaking.gif';

interface BrandMarkProps {
  /** When true, show the animated (shaking) mark instead of the resting emoji. */
  animate?: boolean;
}

/**
 * The screamingface logo lockup: static 😱 mark + wordmark.
 *
 * Per the brand system, the static system emoji is the resting mark and the
 * animated mark "earns its place in moments that deserve it." Hovering the
 * sidebar header is one such moment — the parent drives `animate`, and we swap
 * in the shaking GIF. Each time animation (re)starts we bump a nonce so the GIF
 * reloads from frame one instead of showing a cached final frame.
 */
export function BrandMark({ animate = false }: BrandMarkProps) {
  const [nonce, setNonce] = useState(0);
  const wasAnimating = useRef(false);

  useEffect(() => {
    if (animate && !wasAnimating.current) setNonce((n) => n + 1);
    wasAnimating.current = animate;
  }, [animate]);

  return (
    <span className="flex items-center gap-2">
      <span className="grid size-5 place-items-center" aria-hidden="true">
        {animate ? (
          <img
            key={nonce}
            src={`${screamShaking}?n=${nonce}`}
            alt=""
            draggable={false}
            className="size-5 select-none"
            style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
          />
        ) : (
          <span className="text-lg leading-none">&#x1F631;</span>
        )}
      </span>
      <span className="font-heading text-sm font-semibold text-sidebar-foreground">
        screamingface
      </span>
    </span>
  );
}
