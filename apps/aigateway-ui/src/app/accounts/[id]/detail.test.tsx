/**
 * The tenant detail page, minus the fetch.
 *
 * `page.tsx` is an async Server Component and cannot be rendered here — so it holds nothing but
 * the two gateway calls and the composition, and everything that decides something lives in
 * `detail.tsx` or in the two client components, which is what this file exercises.
 *
 * Two things are pinned deliberately rather than incidentally: the masked label is rendered
 * exactly as the gateway sent it (never re-derived, never unmasked), and the empty state names
 * `404 profile_not_found` — the failure this whole console exists to prevent.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { ActionState } from "@/app/actions";
import type { AdminProfile } from "@/lib/aigateway/client";

import { AccountStatusControl } from "./account-status-control";
import { DeleteProfileButton } from "./delete-profile-button";
import {
  AccountFacts,
  CredentialsTable,
  NO_VALUE,
  NoCredentials,
  authTypeLabel,
  describeProfileState,
  formatInstant,
} from "./detail";

function profile(overrides: Partial<AdminProfile> = {}): AdminProfile {
  return {
    id: "profile-1",
    account_id: "account-1",
    provider: "anthropic",
    name: "default",
    account_label: "API key ····WXYZ",
    state: "authenticated",
    auth_type: "api_key",
    defaults: {},
    last_refreshed_at: "2026-07-30T14:03:07.512Z",
    ...overrides,
  };
}

describe("formatInstant", () => {
  it("renders an ISO instant in UTC, to the minute", () => {
    expect(formatInstant("2026-07-30T14:03:07.512Z")).toBe("2026-07-30 14:03 UTC");
  });

  it("normalises an offset to UTC rather than showing it as-written", () => {
    // 09:03-05:00 IS 14:03Z. Formatting in a fixed zone is what keeps the server render and the
    // browser's hydration of it byte-identical.
    expect(formatInstant("2026-07-30T09:03:07-05:00")).toBe("2026-07-30 14:03 UTC");
  });

  it("shows a dash for an absent value", () => {
    expect(formatInstant(null)).toBe(NO_VALUE);
    expect(formatInstant(undefined)).toBe(NO_VALUE);
    expect(formatInstant("")).toBe(NO_VALUE);
  });

  it("passes an unparseable value through instead of hiding it", () => {
    expect(formatInstant("whenever")).toBe("whenever");
  });
});

describe("describeProfileState", () => {
  it("maps the gateway's states to a label and a tone", () => {
    expect(describeProfileState("authenticated")).toEqual({ label: "Authenticated", tone: "good" });
    expect(describeProfileState("pending")).toEqual({ label: "Pending", tone: "neutral" });
    expect(describeProfileState("error")).toEqual({ label: "Error", tone: "bad" });
  });

  it("shows a state it has never heard of verbatim", () => {
    // The gateway owns that enum and may grow it. Collapsing an unknown value into "unknown"
    // would hide the one string the operator needs in order to go look it up.
    expect(describeProfileState("revoked")).toEqual({ label: "revoked", tone: "neutral" });
  });
});

describe("authTypeLabel", () => {
  it("spells out the auth types", () => {
    expect(authTypeLabel("api_key")).toBe("API key");
    expect(authTypeLabel("oauth")).toBe("OAuth");
  });

  it("passes anything else through", () => {
    expect(authTypeLabel("mtls")).toBe("mtls");
  });
});

describe("AccountFacts", () => {
  it("pairs every fact with its label", () => {
    render(
      <AccountFacts
        displayName="Platform team"
        createdAt="2026-07-01T08:00:00Z"
        lastLoginAt="2026-07-30T14:03:07Z"
        isActive
      />,
    );

    expect(screen.getByText("Display name").tagName).toBe("DT");
    expect(screen.getByText("Platform team").tagName).toBe("DD");
    expect(screen.getByText("2026-07-01 08:00 UTC")).toBeInTheDocument();
    expect(screen.getByText("2026-07-30 14:03 UTC")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("says a tenant that has not called the gateway has never logged in", () => {
    render(<AccountFacts createdAt="2026-07-01T08:00:00Z" lastLoginAt={null} isActive />);

    expect(screen.getByText("Never")).toBeInTheDocument();
  });

  it("dashes an absent or blank display name", () => {
    render(
      <AccountFacts displayName="   " createdAt="2026-07-01T08:00:00Z" lastLoginAt={null} isActive />,
    );

    expect(screen.getByText(NO_VALUE)).toBeInTheDocument();
  });

  it("states a deactivated tenant as deactivated", () => {
    render(
      <AccountFacts createdAt="2026-07-01T08:00:00Z" lastLoginAt={null} isActive={false} />,
    );

    expect(screen.getByText("Deactivated")).toBeInTheDocument();
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
  });
});

describe("CredentialsTable", () => {
  it("heads every column the operator needs to tell two credentials apart", () => {
    render(<CredentialsTable profiles={[profile()]} renderActions={() => null} />);

    const headers = screen.getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(headers).toEqual([
      "Provider",
      "Name",
      "Label",
      "State",
      "Auth type",
      "Last refreshed",
      "Actions",
    ]);
  });

  it("renders the gateway's masked label exactly as received", () => {
    // The console has no unmasked value to reveal and must never look like it does.
    render(<CredentialsTable profiles={[profile()]} renderActions={() => null} />);

    expect(screen.getByText("API key ····WXYZ")).toBeInTheDocument();
  });

  it("dashes a profile the gateway gave no label for", () => {
    render(
      <CredentialsTable profiles={[profile({ account_label: null })]} renderActions={() => null} />,
    );

    expect(screen.getByText(NO_VALUE)).toBeInTheDocument();
  });

  it("renders a row per profile, with its own actions", () => {
    render(
      <CredentialsTable
        profiles={[
          profile(),
          profile({ id: "profile-2", provider: "openai", name: "batch", state: "pending" }),
        ]}
        renderActions={(row) => <button type="button">{`Detach ${row.provider}/${row.name}`}</button>}
      />,
    );

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByRole("button", { name: "Detach anthropic/default" })).toBeVisible();
    expect(within(rows[1]).getByRole("button", { name: "Detach openai/batch" })).toBeVisible();
    expect(within(rows[1]).getByText("Pending")).toBeInTheDocument();
  });

  it("never renders a defaults blob or anything else the row happens to carry", () => {
    render(
      <CredentialsTable
        profiles={[profile({ defaults: { model: "claude-sonnet-4-5", max_tokens: 4096 } })]}
        renderActions={() => null}
      />,
    );

    expect(screen.queryByText(/claude-sonnet-4-5/)).not.toBeInTheDocument();
  });
});

describe("NoCredentials", () => {
  it("names the exact failure an unprovisioned tenant hits", () => {
    render(<NoCredentials action={<a href="/x">Attach API key</a>} />);

    expect(screen.getByText(/404 profile_not_found/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Attach API key" })).toBeInTheDocument();
  });
});

describe("DeleteProfileButton", () => {
  it("names the credential it would detach, so identical buttons stay distinguishable", () => {
    render(<DeleteProfileButton provider="anthropic" name="default" action={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Detach anthropic / default" })).toBeInTheDocument();
  });

  it("does not fire on the first click — it arms", () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ ok: true }));
    render(<DeleteProfileButton provider="anthropic" name="default" action={action} />);

    fireEvent.click(screen.getByRole("button", { name: "Detach anthropic / default" }));

    expect(action).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Confirm detaching anthropic / default" }),
    ).toBeInTheDocument();
  });

  it("puts the button back when the operator cancels", () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ ok: true }));
    render(<DeleteProfileButton provider="anthropic" name="default" action={action} />);

    fireEvent.click(screen.getByRole("button", { name: "Detach anthropic / default" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel detaching anthropic / default" }));

    expect(action).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Detach anthropic / default" })).toBeInTheDocument();
  });

  it("calls the bound action once the operator confirms", async () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ ok: true }));
    render(<DeleteProfileButton provider="anthropic" name="default" action={action} />);

    fireEvent.click(screen.getByRole("button", { name: "Detach anthropic / default" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm detaching anthropic / default" }));

    await waitFor(() => expect(action).toHaveBeenCalledTimes(1));
  });

  it("shows the gateway's refusal and stays armed to retry", async () => {
    const action = vi.fn(
      async (): Promise<ActionState> => ({ ok: false, error: "Another change landed first." }),
    );
    render(<DeleteProfileButton provider="anthropic" name="default" action={action} />);

    fireEvent.click(screen.getByRole("button", { name: "Detach anthropic / default" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm detaching anthropic / default" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Another change landed first.");
    expect(
      screen.getByRole("button", { name: "Confirm detaching anthropic / default" }),
    ).toBeInTheDocument();
  });
});

describe("AccountStatusControl", () => {
  it("explains that deactivating locks the tenant out, and arms before it does", () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ ok: true }));
    render(<AccountStatusControl isActive action={action} />);

    expect(screen.getByText(/locks this tenant out of the gateway/i)).toBeInTheDocument();
    expect(screen.getByText(/refused with 401/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Deactivate tenant" }));

    expect(action).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Confirm deactivation" })).toBeInTheDocument();
  });

  it("backs out cleanly", () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ ok: true }));
    render(<AccountStatusControl isActive action={action} />);

    fireEvent.click(screen.getByRole("button", { name: "Deactivate tenant" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep active" }));

    expect(action).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Deactivate tenant" })).toBeInTheDocument();
  });

  it("deactivates on confirmation", async () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ ok: true }));
    render(<AccountStatusControl isActive action={action} />);

    fireEvent.click(screen.getByRole("button", { name: "Deactivate tenant" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivation" }));

    await waitFor(() => expect(action).toHaveBeenCalledTimes(1));
  });

  it("reactivates in one click — restoring service is not the destructive direction", async () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ ok: true }));
    render(<AccountStatusControl isActive={false} action={action} />);

    expect(screen.getByText(/locked out/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reactivate tenant" }));

    await waitFor(() => expect(action).toHaveBeenCalledTimes(1));
  });

  it("reports a change the gateway refused", async () => {
    const action = vi.fn(
      async (): Promise<ActionState> => ({ ok: false, error: "The gateway is unreachable." }),
    );
    render(<AccountStatusControl isActive={false} action={action} />);

    fireEvent.click(screen.getByRole("button", { name: "Reactivate tenant" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The gateway is unreachable.");
  });
});
