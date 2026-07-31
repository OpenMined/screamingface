/**
 * The form's job is to carry the action's verdict back to the operator without losing any of it:
 * a message the action attached to a control lands on that control, a message it could not attach
 * to one is still said out loud, and the values survive a failure so they can be corrected — the
 * last of which React 19 does NOT give for free, since it resets an uncontrolled form action on
 * every return, success or not.
 *
 * The action is a stand-in, which is exactly how the component sees it in production too: it
 * arrives as a prop from the Server Component page, never as an import.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { ActionState, FormState } from "./actions";
import { CreateAccountForm } from "./create-account-form";

function renderForm(result: ActionState) {
  const action = vi.fn<(state: FormState, formData: FormData) => Promise<ActionState>>(
    async () => result,
  );
  render(<CreateAccountForm action={action} />);
  return action;
}

function type(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
}

describe("CreateAccountForm", () => {
  it("labels both fields and marks only the address as required", () => {
    renderForm({ ok: true });

    const email = screen.getByLabelText(/email address/i);
    expect(email).toBeRequired();
    // The browser's own check runs before the action does — one fewer round trip on a typo.
    expect(email).toHaveAttribute("type", "email");
    expect(screen.getByLabelText(/display name/i)).not.toBeRequired();
  });

  it("sends what was typed to the action", async () => {
    const action = renderForm({ ok: true });

    type(/email address/i, "ops@acme.org");
    type(/display name/i, "Acme Ops");
    submit();

    await waitFor(() => expect(action).toHaveBeenCalledTimes(1));
    const formData = action.mock.calls[0][1];
    expect(formData.get("email")).toBe("ops@acme.org");
    expect(formData.get("display_name")).toBe("Acme Ops");
  });

  it("attaches a field-level failure to the control the action named", async () => {
    renderForm({ ok: false, error: "That address is already provisioned.", field: "email" });

    type(/email address/i, "ops@acme.org");
    submit();

    await waitFor(() =>
      expect(screen.getByText("That address is already provisioned.")).toBeInTheDocument(),
    );
    const email = screen.getByLabelText(/email address/i);
    expect(email).toHaveAttribute("aria-invalid", "true");
    // The message must be reachable FROM the control, not merely printed near it.
    expect(email).toHaveAccessibleDescription(/already provisioned/i);
  });

  it("says a failure out loud when the action could not attach it to a control", async () => {
    renderForm({ ok: false, error: "The gateway is not configured to serve the admin API." });

    type(/email address/i, "ops@acme.org");
    submit();

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "The gateway is not configured to serve the admin API.",
      ),
    );
    expect(screen.getByLabelText(/email address/i)).not.toHaveAttribute("aria-invalid", "true");
  });

  it("confirms a success and clears the form so the next tenant is not a duplicate", async () => {
    renderForm({ ok: true });

    type(/email address/i, "ops@acme.org");
    type(/display name/i, "Acme Ops");
    submit();

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/tenant provisioned/i),
    );
    expect(screen.getByLabelText(/email address/i)).toHaveValue("");
    expect(screen.getByLabelText(/display name/i)).toHaveValue("");
  });

  it("keeps the typed values after a failure, so they can be corrected", async () => {
    renderForm({ ok: false, error: "That address is already provisioned.", field: "email" });

    type(/email address/i, "ops@acme.org");
    type(/display name/i, "Acme Ops");
    submit();

    await waitFor(() =>
      expect(screen.getByText("That address is already provisioned.")).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/email address/i)).toHaveValue("ops@acme.org");
    expect(screen.getByLabelText(/display name/i)).toHaveValue("Acme Ops");
  });
});
