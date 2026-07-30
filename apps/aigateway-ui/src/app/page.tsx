/**
 * The console's home: every tenant the gateway will serve, and the form that adds one.
 *
 * A Server Component, which is the whole point. `listAccounts` runs here, on the server, carrying
 * the `X-User-Email` the mesh put on the incoming request — the browser never learns the admin
 * API's address and never holds an identity header. The single write on this page goes out through
 * `createAccountAction`, handed to a Client Component as a prop rather than imported by it.
 *
 * INVARIANT: this page makes no authorization decision. It asks the gateway for the list and
 * renders whatever comes back — including the refusal. A 403 becomes the "not an administrator"
 * panel and a 503 becomes the "admin API is not enabled" panel, both by way of `describeFailure`,
 * because the gateway owns the allowlist and this console must never hold a second copy of it.
 */
import { Button, EmptyState, Field, Input, Notice } from "@/components/ui";
import type { AdminAccount } from "@/lib/aigateway/client";
import { listAccounts } from "@/lib/aigateway/client";
import type { AdminGateFailure } from "@/lib/auth";
import { describeFailure } from "@/lib/auth";

import { AccountsTable, summarizeAccounts } from "./accounts-table";
import { createAccountAction } from "./actions";
import { CreateAccountForm } from "./create-account-form";

type SearchParams = { q?: string | string[] };

export default async function Page({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  // A repeated `?q=` arrives as an array. Take the first rather than joining: the gateway wants
  // one search term, and a joined pair would silently search for something nobody typed.
  const raw = Array.isArray(params.q) ? params.q[0] : params.q;
  const query = raw?.trim() ?? "";

  let accounts: AdminAccount[] = [];
  let total = 0;
  let failure: AdminGateFailure | null = null;

  try {
    const page = await listAccounts(query ? { q: query } : undefined);
    accounts = page.accounts;
    total = page.total;
  } catch (error) {
    // `describeFailure` RETHROWS anything that is not an AdminApiError, so a genuine bug still
    // reaches the error boundary instead of being flattened into a tidy sentence that hides it.
    failure = describeFailure(error);
  }

  return (
    <main className="page">
      <p className="eyebrow">OpenMined · ScreamingFace</p>
      <h1 className="page-title">Gateway accounts</h1>
      <p className="lede">
        Every tenant aigateway will serve, and the provider API key attached to each. Access is
        granted by your Cloudflare-verified address — the gateway holds the administrator list, and
        this console only renders its answer.
      </p>

      {failure ? (
        <Notice tone="error" title={failure.title} className="accounts-failure">
          {failure.message}
          {failure.retryable ? (
            // A GET form, not a link: submitting it re-requests the URL the operator is already
            // on, which is exactly what "try again" means and needs no JavaScript to do it.
            <form method="get" action="/" className="accounts-retry">
              {query ? <input type="hidden" name="q" value={query} /> : null}
              <Button type="submit" variant="ghost">
                Try again
              </Button>
            </form>
          ) : null}
        </Notice>
      ) : (
        <div className="accounts-body">
          <div className="accounts-list">
            {/* A search box over an empty estate is furniture. It appears once there is something
                to search, and stays put while a query is active so it can be cleared. */}
            {total > 0 || query ? (
              <form method="get" action="/" role="search" className="accounts-search">
                <Field
                  label="Search accounts"
                  hint="Matches the email address and the display name."
                  className="accounts-search-field"
                >
                  <Input
                    type="search"
                    name="q"
                    defaultValue={query}
                    autoComplete="off"
                    placeholder="acme.org"
                  />
                </Field>
                <Button type="submit" variant="ghost">
                  Search
                </Button>
              </form>
            ) : null}

            {accounts.length > 0 ? (
              <AccountsTable
                accounts={accounts}
                caption={summarizeAccounts(accounts.length, total, query)}
              />
            ) : query ? (
              <EmptyState
                title="No matching accounts"
                message={`Nothing here has “${query}” in its address or display name. Search only looks at tenants this gateway already knows about — a new one has to be provisioned below.`}
                action={
                  // No class: `.ui-empty-action` already owns the spacing under an empty state.
                  <form method="get" action="/">
                    <Button type="submit" variant="ghost">
                      Show every account
                    </Button>
                  </form>
                }
              />
            ) : (
              <EmptyState
                title="No accounts yet"
                message="This gateway has no tenants. Provision the first one below, then attach its provider API key from the account's own page."
              />
            )}
          </div>

          <section className="accounts-section" aria-labelledby="provision-heading">
            <h2 className="accounts-heading" id="provision-heading">
              Provision a tenant
            </h2>
            <p className="accounts-section-lede">
              The address must be the one Cloudflare Access will verify — the gateway keys the
              account on it, so a typo here is a tenant that can never sign in. The provider API key
              is attached afterwards, from the account&rsquo;s own page.
            </p>
            <CreateAccountForm action={createAccountAction} />
          </section>
        </div>
      )}
    </main>
  );
}
