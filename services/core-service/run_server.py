import errno
import os
import sys

from atee_core.http_server import run


def bind_from_env() -> tuple[str, int]:
    host = os.environ.get("ATEE_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("ATEE_PORT", "8787"))
    except ValueError:
        port = 8787
    return host, port


if __name__ == "__main__":
    host, port = bind_from_env()
    try:
        run(host, port)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(f"ATEE Core Service could not bind {host}:{port}; the address is already in use.", file=sys.stderr)
            sys.exit(98)
        raise
