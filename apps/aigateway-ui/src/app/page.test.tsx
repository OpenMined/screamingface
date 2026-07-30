/**
 * The accounts page is an async Server Component, so Testing Library cannot render it directly.
 * It CAN be invoked as the async function it is — `await Page(props)` returns the element tree —
 * and that tree is then ordinary sync React. That is enough to hold the decisions this page owns:
 * which of the three empty/populated states appears, and that a refusal from the gateway replaces
 * the whole working surface instead of sitting above a form that would only be refused too.
 *
 * `server-only` is stubbed because vitest runs outside the react-server condition, where importing
 * it throws by design. That does not weaken anything: `next build` is what enforces the
 * client/server split, and it still sees the real module.
 */
import { render, screen } from "@testing-library/react";

vi.mock("server-only", () => ({}));

const listAccounts = vi.fn();

// Spread the real module so `AdminApiError` keeps ONE identity — `describeFailure` narrows with
// `instanceof`, and a second copy of the class would make every refusal look like a bug.
vi.mock("@/lib/aigateway/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/aigateway/client")>();
  return { ...actual, listAccounts: (...args: unknown[]) => listAccounts(...args) };
});

// The page imports the server action only to hand it to the form as a prop, so a stand-in
// function is all the page needs to render.
vi.mock("./actions", () => ({ createAccountAction: vi.fn(async () => ({ ok: true })) }));

const { AdminApiError } = await import("@/lib/aigateway/client");
const { default: Page } = await import("./page");
type AdminAccount = import("@/lib/aigateway/client").AdminAccount;

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

/** Invoke the Server Component and render what it returned. */
async function renderPage(q?: string) {
  const element = await Page({ searchParams: Promise.resolve(q === undefined ? {} : { q }) });
  render(element);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("the accounts page", () => {
  it("lists the tenants the gateway returned, with the count", async () => {
    listAccounts.mockResolvedValue({
      accounts: [account(), account({ id: "acc-2", username: "sre@beta.io" })],
      total: 2,
    });

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Gateway accounts");
    expect(screen.getByRole("link", { name: "ops@acme.org" })).toHaveAttribute(
      "href",
      "/accounts/acc-1",
    );
    expect(screen.getByText("2 accounts")).toBeInTheDocument();
  });

  it("passes the trimmed query through to the gateway", async () => {
    listAccounts.mockResolvedValue({ accounts: [account()], total: 1 });

    await renderPage("  acme  ");

    expect(listAccounts).toHaveBeenCalledWith({ q: "acme" });
    expect(screen.getByRole("searchbox", { name: /search accounts/i })).toHaveValue("acme");
  });

  it("asks for the whole estate when no query was given", async () => {
    listAccounts.mockResolvedValue({ accounts: [], total: 0 });

    await renderPage();

    expect(listAccounts).toHaveBeenCalledWith(undefined);
  });

  it("distinguishes an empty estate from a search that matched nothing", async () => {
    listAccounts.mockResolvedValue({ accounts: [], total: 0 });

    await renderPage();

    expect(screen.getByText("No accounts yet")).toBeInTheDocument();
    // Nothing to search over yet, so the search box would be furniture.
    expect(screen.queryByRole("search")).not.toBeInTheDocument();
  });

  it("keeps the search box available when a query matched nothing", async () => {
    listAccounts.mockResolvedValue({ accounts: [], total: 0 });

    await renderPage("acme");

    expect(screen.getByText("No matching accounts")).toBeInTheDocument();
    expect(screen.getByRole("search")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show every account" })).toBeInTheDocument();
  });

  it("replaces the working surface with the refusal when the caller is not an administrator", async () => {
    listAccounts.mockRejectedValue(new AdminApiError("forbidden", 403, "nope"));

    await renderPage();

    expect(screen.getByRole("alert")).toHaveTextContent("Not an administrator");
    // A provisioning form under a 403 would only ever produce another 403.
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Provision tenant" })).not.toBeInTheDocument();
  });

  it("names a deployment problem as one and offers no retry", async () => {
    listAccounts.mockRejectedValue(new AdminApiError("unavailable", 503, "off"));

    await renderPage();

    expect(screen.getByRole("alert")).toHaveTextContent("Admin API is not enabled");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("offers a retry, carrying the query, when the gateway was merely unreachable", async () => {
    listAccounts.mockRejectedValue(new AdminApiError("unreachable", 0, "no answer"));

    await renderPage("acme");

    expect(screen.getByRole("alert")).toHaveTextContent("Gateway unreachable");
    const retry = screen.getByRole("button", { name: "Try again" });
    expect(retry).toBeInTheDocument();
    expect(retry.closest("form")?.querySelector("input[name='q']")).toHaveValue("acme");
  });

  it("lets a non-AdminApiError reach the error boundary instead of flattening it", async () => {
    listAccounts.mockRejectedValue(new TypeError("fetch is not a function"));

    await expect(renderPage()).rejects.toThrow("fetch is not a function");
  });
});
