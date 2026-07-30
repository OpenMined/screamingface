/**
 * The container HEALTHCHECK and the Kubernetes probes both hit this route, so its contract is
 * "200 with a tiny JSON body" and nothing more. It deliberately does NOT reach aigateway: a
 * liveness probe that fails when a dependency is down turns one unhealthy backend into a restart
 * loop of every UI pod, which is strictly worse than serving an error page.
 */
import { GET } from "./route";

describe("GET /healthz", () => {
  it("answers 200", async () => {
    const response = await GET();

    expect(response.status).toBe(200);
  });

  it("reports status ok", async () => {
    const response = await GET();

    await expect(response.json()).resolves.toEqual({ status: "ok" });
  });
});
