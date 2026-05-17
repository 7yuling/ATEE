import base64
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path


class SecretStoreError(RuntimeError):
    pass


def load_secret_file(path: str | Path) -> str | None:
    text = Path(path).read_text(encoding="utf-8").lstrip("\ufeff").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(payload, dict) or payload.get("type") != "windows_dpapi_current_user":
        return text
    ciphertext = base64.b64decode(str(payload.get("ciphertext") or ""))
    return _dpapi_unprotect(ciphertext).decode("utf-8").lstrip("\ufeff").strip() or None


def write_encrypted_secret_file(secret: str, path: str | Path) -> None:
    encrypted = _dpapi_protect(secret.lstrip("\ufeff").strip().encode("utf-8"))
    payload = {
        "version": 1,
        "type": "windows_dpapi_current_user",
        "ciphertext": base64.b64encode(encrypted).decode("ascii"),
    }
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _require_windows() -> None:
    if sys.platform != "win32":
        raise SecretStoreError("windows_dpapi_current_user is only available on Windows")


def _blob_from_bytes(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _bytes_from_blob(blob: _DataBlob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _dpapi_protect(data: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _buffer = _blob_from_bytes(data)
    out_blob = _DataBlob()
    if not crypt32.CryptProtectData(ctypes.byref(in_blob), "ATEE LLM API key", None, None, None, 0, ctypes.byref(out_blob)):
        raise SecretStoreError("CryptProtectData failed")
    try:
        return _bytes_from_blob(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _buffer = _blob_from_bytes(data)
    out_blob = _DataBlob()
    description = ctypes.c_wchar_p()
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), ctypes.byref(description), None, None, None, 0, ctypes.byref(out_blob)):
        raise SecretStoreError("CryptUnprotectData failed")
    try:
        return _bytes_from_blob(out_blob)
    finally:
        if description:
            kernel32.LocalFree(description)
        kernel32.LocalFree(out_blob.pbData)
