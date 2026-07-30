/**
 * Liveness/readiness endpoint for the container HEALTHCHECK and the Kubernetes probes.
 *
 * INVARIANT: this never calls aigateway. A liveness probe that fails when a dependency is down
 * turns one unhealthy backend into a restart loop across every UI pod — strictly worse than
 * serving an error page. "Is this process serving HTTP?" is the whole question it answers.
 */
export function GET(): Response {
  return Response.json({ status: "ok" });
}
