"""``url4-cloud`` console entrypoint — runs the ASGI app."""


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("url4_cloud.app:create_app", factory=True, host="0.0.0.0", port=9108)
