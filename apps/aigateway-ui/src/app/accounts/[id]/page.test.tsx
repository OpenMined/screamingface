/**
 * The detail page owns three decisions worth holding: that both reads go out together, that a
 * missing tenant reads as "no such tenant" rather than a generic refusal, and that any other
 * refusal replaces the working surface instead of sitting above controls that would also be
 * refused.
 *
 * Invoked as `await Page(props)` — an async Server Component is just an async function returning a
 * tree, and that tree is ordinary sync React. `server-only` is stubbed because vitest runs outside
 * the react-server condition where it throws by design; `next build` still sees the real module,
 * so the client/server split is enforced where it actually matters.
 */
import { render, screen } from "@testing-library/react";

vi.mock("server-only", () => ({}));

const getAccount = vi.fn();
const listProfiles = vi.fn();

// Spread the real module so `AdminApiError` keeps ONE identity — `describeFailure` narrows with
// `instanceof`, and a second copy of the class would make every refusal look like a bug.
vi.mock("@/lib/aigateway/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/aigateway/client")>();
  return {
    ...actual,
    getAccount: (...args: unknown[]) => getAccount(...args),
    listProfiles: (...args: unknown[]) => listProfiles(...args),
  };
});

vi.mock("@/app/actions", () => ({
  setAccountActiveAction: vi.fn(async () => ({ ok: true })),
  deleteProfileAction: vi.fn(async () => ({ ok: true })),
}));

const { AdminApiError } = await import("@/lib/aigateway/client");
const { default: Page } = await import("./page");
type AdminAccount = import("@/lib/aigateway/client").AdminAccount;
type AdminProfile = import("@/lib/aigateway/client").AdminProfile;

function account(overrides: Partial<AdminAccount> = {}): AdminAccount {
  return {
    id: "acc-1",
    username: "ops@acme.org",
    display_name: "Acme Ops",
    created_at: "2026-07-30T14:22:09Z",
    last_login_at: null,
    is_active: true,
    ...overrides,
  };
}

function profile(overrides: Partial<AdminProfile> = {}): AdminProfile {
  return {
    id: "acc-1:anthropic:default",
    account_id: "acc-1",
    provider: "anthropic",
    name: "default",
    account_label: "API key ····WXYZ",
    state: "authenticated",
    auth_type: "api_key",
    defaults: {},
    last_refreshed_at: null,
    ...overrides,
  } as AdminProfile;
}

const props = { params: Promise.resolve({ id: "acc-1" }) };

beforeEach(() => {
  getAccount.mockReset().mockResolvedValue(account());
  listProfiles.mockReset().mockResolvedValue({ profiles: [] });
});

it("names the tenant it is showing", async () => {
  render(await Page({ params: Promise.resolve({ id: "acc-1" }) }));

  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("ops@acme.org");
});

it("reads the account and its credentials in one round trip, not two", async () => {
  // Sequential awaits would put a second round trip on the critical path of a page that cannot
  // render without either result.
  await Page({ params: Promise.resolve({ id: "acc-1" }) });

  expect(getAccount).toHaveBeenCalledWith("acc-1");
  expect(listProfiles).toHaveBeenCalledWith("acc-1");
});

it("shows an attached credential by its masked label", async () => {
  listProfiles.mockResolvedValue({ profiles: [profile()] });

  render(await Page({ params: Promise.resolve({ id: "acc-1" }) }));

  expect(screen.getByText("API key ····WXYZ")).toBeInTheDocument();
});

it("explains the consequence when a tenant has no credentials", async () => {
  // This sentence is the entire reason the console exists — a tenant with no key authenticates and
  // then gets 404 profile_not_found.
  render(await Page(props));

  expect(screen.getByText(/profile_not_found/i)).toBeInTheDocument();
});

it("says no such tenant rather than a generic refusal", async () => {
  getAccount.mockRejectedValue(new AdminApiError("not_found", 404, "nope"));
  listProfiles.mockRejectedValue(new AdminApiError("not_found", 404, "nope"));

  render(await Page({ params: Promise.resolve({ id: "missing" }) }));

  expect(screen.getByText(/no such tenant/i)).toBeInTheDocument();
});

it("replaces the whole surface when the caller is not an administrator", async () => {
  getAccount.mockRejectedValue(new AdminApiError("forbidden", 403, "nope"));
  listProfiles.mockRejectedValue(new AdminApiError("forbidden", 403, "nope"));

  render(await Page(props));

  expect(screen.getByText(/not an administrator/i)).toBeInTheDocument();
  // No controls a refused caller could press.
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("lets a real bug reach the error boundary", async () => {
  // `describeFailure` rethrows anything that is not an AdminApiError. Flattening a TypeError into
  // tidy copy would hide the bug behind a page that looks like a permissions problem.
  getAccount.mockRejectedValue(new TypeError("boom"));
  listProfiles.mockRejectedValue(new TypeError("boom"));

  await expect(Page(props)).rejects.toThrow(TypeError);
});
