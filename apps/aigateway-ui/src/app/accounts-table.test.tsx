/**
 * The table is the console's primary read surface, so what is asserted here is what an operator
 * and a screen reader actually get out of it: a stable, zone-independent timestamp, a count that
 * tells the truth about truncation, status stated in words, and one navigable row per tenant.
 *
 * No module stubbing is needed. `accounts-table.tsx` imports `AdminAccount` as a type only, so the
 * server-only gateway client never enters this test's module graph — which is the point of keeping
 * these pieces free of data access.
 */
import { render, screen, within } from "@testing-library/react";

import type { AdminAccount } from "@/lib/aigateway/client";

import { AccountsTable, StatusBadge, formatTimestamp, summarizeAccounts } from "./accounts-table";

function account(overrides: Partial<AdminAccount> = {}): AdminAccount {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    username: "ops@acme.org",
    display_name: "Acme Ops",
    created_at: "2026-07-30T14:22:09.482913Z",
    last_login_at: null,
    is_active: true,
    ...overrides,
  };
}

describe("formatTimestamp", () => {
  it("renders an instant in UTC, to the minute", () => {
    expect(formatTimestamp("2026-07-30T14:22:09.482913Z")).toBe("2026-07-30 14:22 UTC");
  });

  it("normalises an offset instant to UTC rather than echoing the offset", () => {
    // Same moment as the case above, written +02:00. If this ever came back as "16:22" the table
    // would disagree with the gateway's own logs.
    expect(formatTimestamp("2026-07-30T16:22:09+02:00")).toBe("2026-07-30 14:22 UTC");
  });

  it("crosses a date boundary by UTC, not by the reader's day", () => {
    // 22:40 in Auckland on the 31st is still the 30th in UTC. The page renders on the server and
    // hydrates in the browser, so anything that resolved per-viewer would be a hydration mismatch
    // as well as a disagreement with the gateway's logs.
    expect(formatTimestamp("2026-07-31T02:40:00+13:00")).toBe("2026-07-30 13:40 UTC");
  });

  it("shows an em dash when the gateway has no timestamp", () => {
    expect(formatTimestamp(null)).toBe("—");
    expect(formatTimestamp(undefined)).toBe("—");
    expect(formatTimestamp("")).toBe("—");
  });

  it("echoes an unparseable value instead of printing 'Invalid Date'", () => {
    expect(formatTimestamp("last thursday")).toBe("last thursday");
  });
});

describe("summarizeAccounts", () => {
  it("states the count when nothing was truncated", () => {
    expect(summarizeAccounts(12, 12, "")).toBe("12 accounts");
  });

  it("says 'account' for exactly one", () => {
    expect(summarizeAccounts(1, 1, "")).toBe("1 account");
  });

  it("names the query it counted under", () => {
    expect(summarizeAccounts(3, 3, "acme")).toBe("3 accounts matching “acme”");
  });

  it("makes truncation impossible to miss", () => {
    expect(summarizeAccounts(25, 60, "")).toBe("Showing 25 of 60 accounts");
    expect(summarizeAccounts(2, 9, "acme")).toBe("Showing 2 of 9 accounts matching “acme”");
  });

  it("counts zero without pretending it is one", () => {
    expect(summarizeAccounts(0, 0, "")).toBe("0 accounts");
  });
});

describe("StatusBadge", () => {
  it("says Active in words, not only in colour", () => {
    render(<StatusBadge isActive />);

    const badge = screen.getByText("Active");
    expect(badge).toHaveClass("ui-badge", "ui-badge-good");
  });

  it("says Suspended when the gateway will not serve the tenant", () => {
    render(<StatusBadge isActive={false} />);

    const badge = screen.getByText("Suspended");
    expect(badge).toHaveClass("ui-badge", "ui-badge-bad");
  });
});

describe("AccountsTable", () => {
  it("gives the table its count as an accessible caption", () => {
    render(<AccountsTable accounts={[account()]} caption="12 accounts" />);

    expect(screen.getByText("12 accounts").tagName).toBe("CAPTION");
  });

  it("renders the four columns the console reads by", () => {
    render(<AccountsTable accounts={[account()]} caption="1 account" />);

    const headers = screen.getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(headers).toEqual(["Address", "Display name", "Status", "Created"]);
  });

  it("makes each address a row header linking to that account", () => {
    render(
      <AccountsTable
        accounts={[
          account({ id: "acc-1", username: "ops@acme.org" }),
          account({ id: "acc-2", username: "sre@beta.io" }),
        ]}
        caption="2 accounts"
      />,
    );

    const rowHeaders = screen.getAllByRole("rowheader");
    expect(rowHeaders).toHaveLength(2);
    expect(within(rowHeaders[0]).getByRole("link", { name: "ops@acme.org" })).toHaveAttribute(
      "href",
      "/accounts/acc-1",
    );
    expect(within(rowHeaders[1]).getByRole("link", { name: "sre@beta.io" })).toHaveAttribute(
      "href",
      "/accounts/acc-2",
    );
  });

  it("states a missing display name rather than leaving the cell blank", () => {
    render(<AccountsTable accounts={[account({ display_name: null })]} caption="1 account" />);

    expect(screen.getByText("Not set")).toHaveClass("accounts-blank");
  });

  it("treats an empty display name the same as a missing one", () => {
    render(<AccountsTable accounts={[account({ display_name: "" })]} caption="1 account" />);

    expect(screen.getByText("Not set")).toBeInTheDocument();
  });

  it("shows the creation instant and the tenant's status in the row", () => {
    render(
      <AccountsTable
        accounts={[account({ is_active: false, created_at: "2026-01-04T09:05:00Z" })]}
        caption="1 account"
      />,
    );

    const row = screen.getAllByRole("row")[1];
    expect(within(row).getByText("2026-01-04 09:05 UTC")).toBeInTheDocument();
    expect(within(row).getByText("Suspended")).toBeInTheDocument();
  });

  it("renders a header row and nothing else when handed no accounts", () => {
    render(<AccountsTable accounts={[]} caption="0 accounts" />);

    expect(screen.getAllByRole("row")).toHaveLength(1);
  });
});
