import os

from atee_core.http_server import run


def bind_from_env() -> tuple[str, int]:
    host = os.environ.get("ATEE_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("ATEE_PORT", "8787"))
    except ValueError:
        port = 8787
    return host, port


if __name__ == "__main__":
    run(*bind_from_env())
