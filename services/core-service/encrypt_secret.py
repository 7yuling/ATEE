import argparse
from pathlib import Path

from atee_core.secret_store import load_secret_file, write_encrypted_secret_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt an ATEE secret file with Windows DPAPI CurrentUser.")
    parser.add_argument("--input", required=True, help="Plaintext or already-supported secret file path")
    parser.add_argument("--output", required=True, help="Encrypted secret output path")
    args = parser.parse_args()

    secret = load_secret_file(args.input)
    if not secret:
        raise SystemExit("input secret is empty")
    write_encrypted_secret_file(secret, args.output)
    Path(args.input).write_text("migrated_to_encrypted_secret_file\n", encoding="utf-8")
    print(f"encrypted_secret_file={args.output}")


if __name__ == "__main__":
    main()
