"use client";

/**
 * The provision-a-tenant form — the console's only Client Component, and it is one solely because
 * `useActionState` is a hook.
 *
 * INVARIANT: the action arrives as a PROP. `createAccountAction` is imported by the Server
 * Component page and handed down, so nothing in this file's module graph reaches
 * `src/lib/aigateway/client` or `src/lib/auth`. Those modules are `server-only`; pulling either
 * into a `'use client'` graph fails the build by design, and the fix is this shape, not a
 * workaround. The type-only import below is erased by the compiler and carries no such graph.
 */

import { useActionState, useState } from "react";

import { Button, Field, Input, Notice } from "@/components/ui";

import type { ActionState, FormState } from "./actions";

export type CreateAccountFormProps = {
  action: (state: FormState, formData: FormData) => Promise<ActionState>;
};

export function CreateAccountForm({ action }: CreateAccountFormProps) {
  /*
   * Both inputs are CONTROLLED, and that is not a style preference.
   *
   * React 19 resets an uncontrolled `<form action={…}>` the moment the action returns — on failure
   * as well as on success. That would clear the address an operator has just mistyped at exactly
   * the moment they need to see and correct it, and no amount of care in the action can put it
   * back: `ActionState` carries a message, not the submitted values. Holding the values here makes
   * the reset ours, and we make it only on success.
   */
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");

  /*
   * The clearing lives in the action wrapper rather than in an effect, because this is where
   * success is actually known: it runs exactly once per submission, inside the transition, with no
   * need to reason about which later re-render is a repeat. An effect keyed on the result would
   * fire again on the re-render `revalidatePath` causes and wipe whatever had been typed since.
   */
  const [state, submit, pending] = useActionState<FormState, FormData>(async (previous, data) => {
    const result = await action(previous, data);
    if (result.ok) {
      setEmail("");
      setDisplayName("");
    }
    return result;
  }, null);

  const failed = state !== null && !state.ok;
  // The action names the control at fault when it can. Anything it could not attach to a control
  // (or attached to one this form does not render) has to be said at form level instead, or it
  // would be silently dropped.
  const emailError = failed && state.field === "email" ? state.error : undefined;
  const formError = failed && state.field !== "email" ? state.error : undefined;

  return (
    <form action={submit} className="accounts-create">
      {state?.ok ? (
        <Notice tone="success" className="accounts-create-notice">
          Tenant provisioned. It is in the list above.
        </Notice>
      ) : null}
      {formError ? (
        <Notice
          tone="error"
          title="Could not provision that tenant"
          className="accounts-create-notice"
        >
          {formError}
        </Notice>
      ) : null}

      <div className="accounts-create-row">
        <Field
          label="Email address"
          hint="The address Cloudflare Access will verify. The gateway keys the account on it."
          error={emailError}
        >
          {/* `required` and `type="email"` stay even though the action re-checks both: the
              browser's own check is instant and costs no round trip, and the action's copy is the
              backstop for anything that reaches it without passing through this form. */}
          <Input
            name="email"
            type="email"
            required
            autoComplete="off"
            placeholder="operator@example.org"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>
        <Field label="Display name" hint="Optional. Shown in the list instead of the address.">
          <Input
            name="display_name"
            type="text"
            autoComplete="off"
            placeholder="Acme Corp"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </Field>
      </div>

      <Button type="submit" disabled={pending}>
        {pending ? "Provisioning…" : "Provision tenant"}
      </Button>
    </form>
  );
}
