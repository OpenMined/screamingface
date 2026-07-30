/**
 * Skeleton shell. OME-708 replaces this with the accounts table and the credential forms; what
 * lives here now exists so the CI lane has something real to lint, typecheck and render.
 */
export default function Page() {
  return (
    <main className="page">
      <p className="eyebrow">OpenMined · ScreamingFace</p>
      <h1 className="page-title">aigateway admin</h1>
      <p className="lede">
        Manage gateway accounts and the provider API keys attached to them. Access is granted by
        the caller&rsquo;s Cloudflare-verified email address; the gateway holds the allowlist.
      </p>
      <p className="notice">Not yet implemented — OME-708.</p>
    </main>
  );
}
