"""``url4-cloud`` console entrypoint.

No subcommand: preserves the existing prod behaviour (``uvicorn.run`` over the stateless
``create_app`` factory). ``local``: runs the complete service in-process — no k8s, no NATS
(local-mode PRD, docs/plans/url4-cloud-integration/prd/local-mode.md).
"""

import argparse
import logging
import os
import socket

# WHY: only 127.0.0.1/::1 (and its hostname alias) never expose the local world beyond this
# machine — anything else binds a routable interface, so it gets a loud warning (PRD §4 NFR).
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="url4-cloud")
    subparsers = parser.add_subparsers(dest="command")

    local = subparsers.add_parser(
        "local", help="Run the complete service in-process (no k8s, no NATS)."
    )
    local.add_argument(
        "--host",
        default=os.environ.get("URL4_CLOUD_HOST", "127.0.0.1"),
        help="Bind host (env URL4_CLOUD_HOST; default: %(default)s).",
    )
    local.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("URL4_CLOUD_PORT", "9108")),
        help="Bind port (env URL4_CLOUD_PORT; default: %(default)s).",
    )
    local.add_argument(
        "--max-runs",
        type=int,
        default=int(os.environ.get("URL4_CLOUD_MAX_RUNS", "4")),
        help="Max concurrent local runs before 503 (env URL4_CLOUD_MAX_RUNS; "
        "default: %(default)s).",
    )
    return parser


def _check_port_free(host: str, port: int) -> None:
    """Pre-bind check (fail fast, mirrors ``url4 serve``): an occupied port — or any other
    bind-time config error — exits 2 before the app is even built.

    WHY getaddrinfo: resolve the address family from the host so an IPv6 loopback (``::1``) binds
    on an ``AF_INET6`` socket rather than failing unconditionally on a hardcoded ``AF_INET`` one.
    """
    try:
        family, socktype, proto, _canon, sockaddr = socket.getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )[0]
        with socket.socket(family, socktype, proto) as sock:
            sock.bind(sockaddr)
    except OSError as exc:
        raise SystemExit(2) from exc


def _run_local(*, host: str, port: int, max_runs: int) -> None:
    if host not in _LOOPBACK_HOSTS:
        logging.warning(
            "url4-cloud local is binding to non-loopback host %r — the local world can reach "
            "configured routes, so exposure matters",
            host,
        )
    _check_port_free(host, port)  # fail fast, before building the app

    from url4_cloud.app import make_local_app
    from url4_cloud_runner.aigateway_connector import AigatewayConfig

    # WHY aigateway_config (not a pre-built world): the shared aigateway world is built lazily at
    # ASGI startup, in the app's own event loop, from AIGATEWAY_TOKEN/AIGATEWAY_PROFILE env — see
    # make_local_app's docstring (local-mode credential model, aigateway connector plan Batch 4).
    app = make_local_app(max_runs=max_runs, aigateway_config=AigatewayConfig())  # pragma: no cover
    print(f"url4-cloud local on http://{host}:{port}")

    import uvicorn  # WHY: lazy — cold-start discipline, and unit tests never reach a real server

    uvicorn.run(app, host=host, port=port)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "local":
        _run_local(host=args.host, port=args.port, max_runs=args.max_runs)
        return

    import uvicorn

    # INVARIANT: the deployed entrypoint serves the ENV-WIRED factory. The bare `create_app` is
    # the dependency-injected one tests use — calling it here would build bus=None/job_runner=None
    # and skip `_require_prod_secret`, i.e. an App that cannot stream, cannot schedule, and would
    # boot on the insecure default secret. This is the chart's `command: [url4-cloud]`.
    uvicorn.run("url4_cloud.app:create_app_from_env", factory=True, host="0.0.0.0", port=9108)
