import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path


DEFAULT_ENV_NAME = "ATEE_ADMIN_TOKEN"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate the ATEE Admin Token in an environment file.")
    parser.add_argument("--env-file", required=True, help="Environment file to update, for example ~/.config/atee/atee-core.env")
    parser.add_argument("--env-name", default=DEFAULT_ENV_NAME, help="Environment variable name to update")
    parser.add_argument("--bytes", type=int, default=32, help="Random byte length before URL-safe encoding")
    parser.add_argument("--show-token", action="store_true", help="Print the new token once. Avoid this in shared terminals.")
    parser.add_argument("--json", action="store_true", help="Print a JSON summary")
    args = parser.parse_args()

    if args.bytes < 24:
        raise SystemExit("--bytes must be at least 24")

    token = secrets.token_urlsafe(args.bytes)
    env_path = Path(args.env_file).expanduser()
    previous = _read_lines(env_path)
    updated = _replace_env_line(previous, args.env_name, token)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    _chmod_owner_only(env_path)

    summary = {
        "ok": True,
        "env_file": str(env_path),
        "env_name": args.env_name,
        "token_fingerprint": _fingerprint(token),
        "token_written": True,
        "token_shown": bool(args.show_token),
    }
    if args.show_token:
        summary["token"] = token

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"admin_token_rotated=true")
        print(f"env_file={summary['env_file']}")
        print(f"env_name={summary['env_name']}")
        print(f"token_fingerprint={summary['token_fingerprint']}")
        if args.show_token:
            print(f"token={token}")
        else:
            print("token=hidden")
    return 0


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _replace_env_line(lines: list[str], name: str, value: str) -> list[str]:
    prefix = f"{name}="
    replacement = f"{name}={value}"
    changed = False
    result: list[str] = []
    for line in lines:
        if line.startswith(prefix) or line.startswith(f"#{prefix}"):
            if not changed:
                result.append(replacement)
                changed = True
            continue
        result.append(line)
    if not changed:
        if result and result[-1].strip():
            result.append("")
        result.append(replacement)
    return result


def _chmod_owner_only(path: Path) -> None:
    if os.name == "posix":
        path.chmod(0o600)


def _fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


if __name__ == "__main__":
    raise SystemExit(main())
