"""``url4-cloud`` console entrypoint — one image, two modes.

    url4-cloud serve   # the control plane: mint tokens, bridge WS, schedule Runner Jobs
    url4-cloud run     # one url4 evaluation, streamed to NATS, then exit

WHY one artifact with a mode argument rather than two images: the two halves already shared
their whole wire vocabulary (`job_env`, `subjects`, the JetStream binding), and keeping them in
separate distributions meant maintaining hand-synced duplicates of all three plus contract tests
whose only job was to catch the copies drifting. The run mode's dependencies are a strict subset
of the serving mode's, so merging cost no new dependency — only the serving-side packages now
sitting unused on a Job's disk.

INVARIANT: the mode is chosen by ARGV, never sniffed from the environment. `K8sJobRunner`
schedules `["url4-cloud", "run"]` explicitly, so a Job that is missing its env fails loudly at
boot instead of silently booting a web server that nothing will ever dial.

``serve`` is the default when no subcommand is given, which is what keeps the image's
``CMD ["url4-cloud"]`` and the chart's ``command: [url4-cloud]`` working unchanged.
"""

import argparse

from url4_cloud.logs import configure as configure_logging

_PORT = 9108


def _serve() -> None:
    """Serve the env-wired control plane with uvicorn."""
    import uvicorn  # WHY: lazy — cold-start discipline, and unit tests never reach a real server

    # INVARIANT: the deployed entrypoint serves the ENV-WIRED factory. The bare `create_app` is
    # the dependency-injected one tests use — calling it here would build
    # stream=None/job_runner=None and skip `_require_prod_secret`, i.e. an App that cannot stream,
    # cannot schedule, and would boot on the insecure default secret.
    #
    # INVARIANT: _PORT here IS the chart's `containerPort` (deploy/helm/templates/deployment.yaml),
    # and it is hardcoded on BOTH sides on purpose. This path reads no port from the environment,
    # so a chart value for it could only ever point the probes and the Service's `targetPort` at a
    # port nothing listens on — which is exactly what `config.port` did before it was removed.
    # Changing this means changing the containerPort in the same commit.
    uvicorn.run("url4_cloud.app:create_app_from_env", factory=True, host="0.0.0.0", port=_PORT)


def _serve_local() -> None:
    """Serve the fused local-mode App — in-process runner, in-memory stream, loopback only.

    A sibling of :func:`_serve` rather than a flag on it: the two share only the word "serve".
    They resolve different factories, bind different addresses, and differ on whether the
    insecure default JWT secret is tolerated — a boolean parameter switching all of that would
    be a second function wearing the first one's name.
    """
    import uvicorn  # WHY: lazy — same cold-start discipline as `_serve`

    # INVARIANT: loopback only — see `local.LOCAL_HOST`. Local mode accepts the insecure default
    # JWT secret, so the bind address is the only thing keeping it unreachable.
    from url4_cloud.local import LOCAL_HOST

    uvicorn.run("url4_cloud.local:create_local_app", factory=True, host=LOCAL_HOST, port=_PORT)


def _run() -> None:
    """Execute one url4 run from the Job's environment, then exit."""
    # WHY: lazy, and the reason the layering rule earns its keep — importing the run path must
    # not drag in FastAPI/uvicorn/kubernetes, and importing `serve` must not drag in the engine.
    from url4_cloud.runner.main import main as run_main

    run_main()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="url4-cloud", description="url4-cloud — the control plane, or one url4 run."
    )
    # WHY not `required=True`: bare `url4-cloud` must keep meaning `serve`, since that is the
    # image CMD and the chart's Deployment command.
    # WHY a top-level default: bare `url4-cloud` parses no subparser, so `args.local` would not
    # exist at all without one.
    parser.set_defaults(local=False)
    sub = parser.add_subparsers(dest="mode")
    serve_parser = sub.add_parser(
        "serve", help="serve the REST + WebSocket control plane (default)"
    )
    serve_parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "run the whole protocol in one process — runs execute as asyncio tasks and frames "
            "travel an in-memory stream, so neither Kubernetes nor NATS is needed. Binds "
            "loopback only."
        ),
    )
    sub.add_parser("run", help="execute one url4 expression from the environment, then exit")
    args = parser.parse_args(argv)

    # BEFORE dispatch, and for every mode: a Job's logs are as load-bearing as the control
    # plane's, and neither `uvicorn.run` nor `run_main` configures anything for this package.
    configure_logging()

    if args.mode == "run":
        _run()
    elif args.local:
        _serve_local()
    else:
        _serve()
