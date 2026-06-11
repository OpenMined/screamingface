import { useState } from 'react';

import screamShaking from '@/assets/scream-shaking.gif';

/**
 * The screamingface logo lockup: static 😱 mark + wordmark.
 *
 * Per the brand system, the static system emoji is the resting mark and the
 * animated mark "earns its place in moments that deserve it." Hovering the
 * logo is one such moment — we swap in the shaking GIF, remounting it so it
 * replays from the first frame each hover.
 */
export function BrandMark() {
  const [animate, setAnimate] = useState(false);

  return (
    <span
      className="flex items-center gap-2"
      onMouseEnter={() => setAnimate(true)}
      onMouseLeave={() => setAnimate(false)}
    >
      <span className="grid size-5 place-items-center" aria-hidden="true">
        {animate ? (
          <img
            src={screamShaking}
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
