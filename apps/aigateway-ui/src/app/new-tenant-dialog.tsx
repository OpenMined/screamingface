"use client";

/**
 * "New tenant" as a button that opens a modal, rather than a form always sitting under the table.
 *
 * A native `<dialog>` rather than a hand-rolled overlay: it brings focus trapping, Escape-to-close,
 * inertness of the page behind it, and top-layer stacking for free. Every one of those is a thing
 * a custom modal gets subtly wrong, and the accessibility ones are the ones nobody notices.
 *
 * INVARIANT (unchanged from the inline form it replaces): the server action arrives as a PROP.
 * Nothing in this file's module graph reaches `src/lib/aigateway/client` or `src/lib/auth` — those
 * are `server-only` and would fail the build if pulled into a `'use client'` graph.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui";

import type { ActionState, FormState } from "./actions";
import { CreateAccountForm } from "./create-account-form";

export type NewTenantDialogProps = {
  action: (state: FormState, formData: FormData) => Promise<ActionState>;
};

export function NewTenantDialog({ action }: NewTenantDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);

  // `showModal()` is a method, not an attribute, so the element has to be driven imperatively —
  // rendering `<dialog open>` gives a NON-modal dialog with no backdrop, no focus trap and no
  // Escape handling, which looks right and behaves wrongly.
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  const close = useCallback(() => setOpen(false), []);

  return (
    <>
      <Button type="button" onClick={() => setOpen(true)}>
        New tenant
      </Button>

      <dialog
        ref={ref}
        className="tenant-dialog"
        aria-labelledby="new-tenant-title"
        // Fires on Escape and on backdrop dismissal as well as on `close()`, so React state cannot
        // drift out of step with the element's own idea of whether it is open.
        onClose={close}
      >
        <div className="tenant-dialog-head">
          <h2 className="tenant-dialog-title" id="new-tenant-title">
            New tenant
          </h2>
          <button
            type="button"
            className="tenant-dialog-close"
            onClick={close}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div className="tenant-dialog-body">
          <p className="lede">
            The address must be the one Cloudflare Access will verify — the gateway keys the account
            on it, so a typo here is a tenant that can never sign in. The provider API key is
            attached afterwards, from the account&rsquo;s own page.
          </p>
          {/* Deliberately left open after a successful provision: the success notice is inside the
              form, and closing on success would flash it away before it could be read. The
              refreshed list is already behind the dialog when it is dismissed. */}
          <CreateAccountForm action={action} />
        </div>
      </dialog>
    </>
  );
}
