/**
 * The accounts table, plus the two pure functions that decide what its cells and caption say.
 *
 * This module is deliberately dumb: props in, JSX out, no data access, no directive. It carries no
 * `'use client'` because it renders inside the Server Component page, and it carries no runtime
 * import from `src/lib/*` because it has no business talking to the gateway — `AdminAccount` comes
 * in as a type-only import, which the compiler erases. That is also what lets the test file render
 * these pieces directly: there is no server-only module in their graph to stub out.
 */
import Link from "next/link";

import { Badge, TBody, TD, TH, THead, TR, Table } from "@/components/ui";
import type { AdminAccount } from "@/lib/aigateway/client";

/** What a cell shows when the gateway has nothing for it. */
const NOT_SET = "—";

/**
 * Render an ISO-8601 instant as `YYYY-MM-DD HH:MM UTC`.
 *
 * UTC, not the reader's locale, for two reasons. The page renders on the server and hydrates in
 * the browser, and a locale- or zone-dependent format differs between the two — that is a
 * hydration mismatch, not a cosmetic difference. And an operator reading this table is usually
 * comparing it against gateway logs, which are UTC; making them convert in their head is how
 * incidents get misread.
 *
 * An unparseable value comes back verbatim rather than as "Invalid Date": if the gateway ever
 * sends something unexpected, showing what it actually sent is what makes the bug findable.
 */
export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return NOT_SET;
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return value;
  return `${at.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

/**
 * The table's caption: how many tenants are on screen, out of how many the query matched.
 *
 * `total` is the gateway's count for THIS query, not the size of the estate, so the two numbers
 * only diverge when the gateway's page limit truncated the response. Saying "Showing 25 of 60"
 * only in that case keeps the common line short and makes the truncation impossible to miss.
 */
export function summarizeAccounts(shown: number, total: number, query: string): string {
  const noun = total === 1 ? "account" : "accounts";
  const scope = query ? ` matching “${query}”` : "";
  return shown < total
    ? `Showing ${shown} of ${total} ${noun}${scope}`
    : `${total} ${noun}${scope}`;
}

export type StatusBadgeProps = { isActive: boolean };

/**
 * Whether the gateway will serve this tenant.
 *
 * The words carry the meaning and the border carries the tone — a colour-blind operator and a
 * screen reader both get the same answer, which they would not from a coloured dot.
 */
export function StatusBadge({ isActive }: StatusBadgeProps) {
  return <Badge tone={isActive ? "good" : "bad"}>{isActive ? "Active" : "Suspended"}</Badge>;
}

export type AccountsTableProps = {
  accounts: AdminAccount[];
  /** Becomes the table's `<caption>`, which is also its accessible name. */
  caption: string;
};

export function AccountsTable({ accounts, caption }: AccountsTableProps) {
  return (
    <Table className="accounts-table">
      <caption className="accounts-caption">{caption}</caption>
      <THead>
        <TR>
          <TH>Address</TH>
          <TH>Display name</TH>
          <TH>Status</TH>
          <TH>Created</TH>
        </TR>
      </THead>
      <TBody>
        {accounts.map((account) => (
          <TR key={account.id}>
            {/* The address is the row's header, not a plain cell: it is what identifies the row,
                and `scope="row"` is what lets a screen reader announce "status: suspended" as
                belonging to a named tenant rather than as a loose word in a grid. */}
            <TH scope="row">
              <Link className="accounts-link" href={`/accounts/${account.id}`}>
                {account.username}
              </Link>
            </TH>
            <TD>
              {account.display_name ? (
                account.display_name
              ) : (
                <span className="accounts-blank">Not set</span>
              )}
            </TD>
            <TD>
              <StatusBadge isActive={account.is_active} />
            </TD>
            <TD className="accounts-when">{formatTimestamp(account.created_at)}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
