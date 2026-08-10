# Share caller credentials only across matching Access audiences

ScreamingFace presents one caller identity and login experience. The Client may reuse one
Cloudflare Access credential for its configured Engine and Scoreboard origins only when both
advertise the same Access issuer and application audience; the default hosted deployment places
both hostnames in that shared application. A different audience authenticates independently and
only after an explicit deployment-provided challenge. `client.logout()` clears every caller
credential held by that Client. The Client never infers trust from hostname branding alone, guesses
an authentication flow from a plain application 401, or supplies the mesh-owned `X-User-Email`
identity header itself.
