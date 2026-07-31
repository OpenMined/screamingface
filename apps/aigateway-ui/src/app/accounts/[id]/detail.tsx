/**
 * The pure half of the tenant detail page: formatting decisions and presentational components
 * that take plain props.
 *
 * WHY this is a separate module. `page.tsx` is an async Server Component that awaits the gateway,
 * and Testing Library cannot render one — so everything here that makes a DECISION (how an
 * instant reads, what an unknown profile state looks like, what the empty credentials table says)
 * lives where a test can hold it, and `page.tsx` is left as fetching plus composition.
 *
 * INVARIANT: no `'use client'` and no runtime import from `src/lib/*`. The only reference to the
 * server-only client is `import type`, which the compiler erases — that is what lets this module
 * render inside the Server Component page AND inside a jsdom test.
 */
import type { ReactNode } from "react";

import type { BadgeTone } from "@/components/ui";
import { Badge, EmptyState, TBody, TD, TH, THead, TR, Table } from "@/components/ui";
import type { AdminProfile } from "@/lib/aigateway/client";

import styles from "./detail.module.css";

/** What an absent optional value looks like. An em dash, not an empty cell that reads as a bug. */
export const NO_VALUE = "—";

/**
 * Render an ISO-8601 instant as `YYYY-MM-DD HH:MM UTC`.
 *
 * UTC, not the viewer's locale, for two reasons. It is deterministic — a locale- or
 * timezone-formatted string differs between the server render and the browser's hydration of it,
 * which React reports as a hydration mismatch. And it matches what an operator reads everywhere
 * else in this stack: aigateway's logs and the gateway's own timestamps are UTC.
 *
 * An unparseable value is returned VERBATIM rather than replaced: showing what the gateway
 * actually sent is more useful than hiding it behind a dash.
 */
export function formatInstant(value: string | null | undefined): string {
  if (!value) return NO_VALUE;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return `${parsed.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

const PROFILE_STATES: Record<string, { label: string; tone: BadgeTone }> = {
  authenticated: { label: "Authenticated", tone: "good" },
  pending: { label: "Pending", tone: "neutral" },
  error: { label: "Error", tone: "bad" },
};

/**
 * How a profile's state reads, and which badge tone carries it.
 *
 * A state this console has not heard of is shown verbatim as a neutral badge. The gateway owns
 * that enum and may grow it; swallowing an unknown value into "unknown" would hide the one piece
 * of information the operator needs to go look it up.
 */
export function describeProfileState(state: string): { label: string; tone: BadgeTone } {
  return PROFILE_STATES[state] ?? { label: state, tone: "neutral" };
}

/** `api_key` / `oauth` as an operator reads them; anything else passes through untouched. */
export function authTypeLabel(authType: string): string {
  if (authType === "api_key") return "API key";
  if (authType === "oauth") return "OAuth";
  return authType;
}

export type AccountFactsProps = {
  displayName?: string | null;
  createdAt: string;
  lastLoginAt?: string | null;
  isActive: boolean;
};

/** The tenant's own facts, as a definition list — labelled data, not a table of one row. */
export function AccountFacts({ displayName, createdAt, lastLoginAt, isActive }: AccountFactsProps) {
  return (
    <dl className={styles.facts}>
      <div className={styles.fact}>
        <dt className={styles.factLabel}>Display name</dt>
        <dd className={styles.factValue}>{displayName?.trim() || NO_VALUE}</dd>
      </div>
      <div className={styles.fact}>
        <dt className={styles.factLabel}>Created</dt>
        <dd className={styles.factValue}>{formatInstant(createdAt)}</dd>
      </div>
      <div className={styles.fact}>
        <dt className={styles.factLabel}>Last login</dt>
        {/* "Never" rather than a dash: a tenant that has not yet called the gateway is a fact
            about the tenant, not a value the gateway failed to give us. */}
        <dd className={styles.factValue}>{lastLoginAt ? formatInstant(lastLoginAt) : "Never"}</dd>
      </div>
      <div className={styles.fact}>
        <dt className={styles.factLabel}>Status</dt>
        <dd className={styles.factValue}>
          <Badge tone={isActive ? "good" : "bad"}>{isActive ? "Active" : "Deactivated"}</Badge>
        </dd>
      </div>
    </dl>
  );
}

export type CredentialsTableProps = {
  profiles: AdminProfile[];
  /**
   * The per-row controls. A render prop rather than a baked-in button because the control is a
   * Client Component holding a server action bound to THIS row — knowledge that belongs to the
   * page, not to a presentational table.
   */
  renderActions: (profile: AdminProfile) => ReactNode;
};

export function CredentialsTable({ profiles, renderActions }: CredentialsTableProps) {
  return (
    <Table>
      <THead>
        <TR>
          <TH>Provider</TH>
          <TH>Name</TH>
          <TH>Label</TH>
          <TH>State</TH>
          <TH>Auth type</TH>
          <TH>Last refreshed</TH>
          <TH>Actions</TH>
        </TR>
      </THead>
      <TBody>
        {profiles.map((profile) => {
          const state = describeProfileState(profile.state);
          return (
            <TR key={profile.id}>
              <TD>{profile.provider}</TD>
              <TD>{profile.name}</TD>
              {/* `account_label` is the gateway's MASKED form ("API key ····WXYZ") and is printed
                  exactly as received. There is no unmasked value anywhere in this app to reveal,
                  and nothing here asks for one. */}
              <TD className={styles.labelCell}>{profile.account_label || NO_VALUE}</TD>
              <TD>
                <Badge tone={state.tone}>{state.label}</Badge>
              </TD>
              <TD>{authTypeLabel(profile.auth_type)}</TD>
              <TD>{formatInstant(profile.last_refreshed_at)}</TD>
              <TD>{renderActions(profile)}</TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}

/**
 * The empty credentials table.
 *
 * This copy is the reason the console exists, so it states the failure literally rather than
 * politely: a tenant with no profile clears Cloudflare Access, becomes a real account, and then
 * every chat request it sends comes back `404 profile_not_found`. Attaching a key is what closes
 * that gap.
 */
export function NoCredentials({ action }: { action?: ReactNode }) {
  return (
    <EmptyState
      title="No credentials attached"
      message="This tenant can authenticate but cannot be served. With no profile, every chat request it sends comes back 404 profile_not_found — attaching a provider API key here is what closes that gap."
      action={action}
    />
  );
}
