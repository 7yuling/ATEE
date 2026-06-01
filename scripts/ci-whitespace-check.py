from __future__ import annotations

import subprocess
import sys


def git_bytes(*args: str) -> bytes:
    result = subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE)
    return result.stdout


def committed_paths() -> list[str]:
    output = git_bytes("ls-tree", "-r", "--name-only", "-z", "HEAD")
    return [
        raw.decode("utf-8", errors="surrogateescape")
        for raw in output.split(b"\0")
        if raw
    ]


def committed_blob(path: str) -> bytes:
    return git_bytes("show", f"HEAD:{path}")


def is_binary(data: bytes) -> bool:
    return b"\0" in data


def main() -> int:
    problems: list[str] = []
    for path in committed_paths():
        data = committed_blob(path)
        if is_binary(data):
            continue
        for line_number, raw_line in enumerate(data.splitlines(keepends=True), start=1):
            line = raw_line.rstrip(b"\r\n")
            if line.endswith((b" ", b"\t")):
                problems.append(f"{path}:{line_number}: trailing whitespace")

    if problems:
        print("Committed whitespace check failed:")
        for problem in problems[:50]:
            print(problem)
        if len(problems) > 50:
            print(f"... and {len(problems) - 50} more")
        return 1

    print("Committed whitespace check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
