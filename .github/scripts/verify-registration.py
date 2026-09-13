#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import argparse
import ctypes
import json
from pathlib import Path

PLUGIN_ID = "deepseek-harness-session"
REPOSITORY = "https://github.com/ahoo/cpa-plugin-deepseek-harness-session"
SOURCE_HEADER = "X-DeepSeek-Harness-Session-Id"
TARGET_HEADER = "X-Session-ID"
MAX_CGO_BYTES_LENGTH = (1 << 31) - 1


class Buffer(ctypes.Structure):
    _fields_ = [("ptr", ctypes.c_void_p), ("len", ctypes.c_size_t)]


def load_functions(path: Path):
    library = ctypes.CDLL(str(path.resolve()))
    call = library.cliproxyPluginCall
    call.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.POINTER(Buffer),
    ]
    call.restype = ctypes.c_int
    free = library.cliproxyPluginFree
    free.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    free.restype = None
    return library, call, free


def invoke(call, free, method: str | None, payload: bytes | None = None, declared_length: int | None = None):
    raw = payload or b""
    request = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw) if payload else None
    response = Buffer()
    length = len(raw) if declared_length is None else declared_length
    encoded_method = method.encode() if method is not None else None
    status = call(encoded_method, request, length, ctypes.byref(response))
    try:
        data = ctypes.string_at(response.ptr, response.len) if response.ptr else b""
    finally:
        if response.ptr:
            free(response.ptr, response.len)
    if not data:
        raise SystemExit(f"{method or 'nil method'} returned an empty response (status={status})")
    try:
        return status, json.loads(data)
    except json.JSONDecodeError as error:
        raise SystemExit(f"{method or 'nil method'} returned invalid JSON (status={status}): {error}") from error


def intercept(call, free, method: str, headers: dict[str, list[str]]):
    payload = json.dumps({"RequestID": "probe", "Headers": headers}, separators=(",", ":")).encode()
    status, envelope = invoke(call, free, method, payload)
    if status != 0 or not envelope.get("ok"):
        raise SystemExit(f"{method} failed: status={status} envelope={envelope}")
    return envelope["result"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    _library, call, free = load_functions(args.library)
    status, envelope = invoke(call, free, "plugin.register")
    if status != 0 or not envelope.get("ok"):
        raise SystemExit(f"registration failed: status={status} envelope={envelope}")

    registration = envelope["result"]
    expected_metadata = {
        "Name": PLUGIN_ID,
        "Version": args.version,
        "Author": "ahoo",
        "GitHubRepository": REPOSITORY,
        "Logo": "",
        "ConfigFields": [],
    }
    if registration.get("metadata") != expected_metadata:
        raise SystemExit(f"registration metadata mismatch: {registration!r}")
    if registration.get("schema_version") != 1:
        raise SystemExit(f"unexpected schema version: {registration!r}")
    if registration.get("capabilities") != {"request_interceptor": True}:
        raise SystemExit(f"unexpected capabilities: {registration!r}")

    guards = (
        ("nil-method", None, 0, "invalid_method"),
        ("nil-buffer", "request.intercept_after", 1, "invalid_request"),
        ("oversized", "request.intercept_after", MAX_CGO_BYTES_LENGTH + 1, "request_too_large"),
    )
    for label, method, length, error_code in guards:
        status, envelope = invoke(call, free, method, declared_length=length)
        if status != 1 or envelope.get("ok") or envelope.get("error", {}).get("code") != error_code:
            raise SystemExit(f"{label} guard failed: status={status} envelope={envelope}")

    for method in ("request.intercept_before", "request.intercept_after"):
        result = intercept(call, free, method, {SOURCE_HEADER.lower(): ["  session-123  "]})
        if result.get("Headers") != {TARGET_HEADER: ["session-123"]}:
            raise SystemExit(f"{method} mapping failed: {result!r}")

    preserved = intercept(
        call,
        free,
        "request.intercept_after",
        {SOURCE_HEADER: ["source-session"], TARGET_HEADER.lower(): ["existing-session"]},
    )
    if preserved.get("Headers") != {}:
        raise SystemExit(f"existing target was not preserved: {preserved!r}")

    status, envelope = invoke(call, free, "request.intercept_after", b'{"Headers":')
    if status != 1 or envelope.get("ok") or envelope.get("error", {}).get("code") != "plugin_error":
        raise SystemExit(f"malformed-payload guard failed: status={status} envelope={envelope}")

    print(f"verified {PLUGIN_ID} registration {args.version}, ABI guards, mapping, and target preservation")


if __name__ == "__main__":
    main()
