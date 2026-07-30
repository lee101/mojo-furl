from __future__ import annotations

import ctypes
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_PACKAGED_LIB = Path(__file__).with_name("libmojo-furl.so")
_DEVELOPMENT_LIB = ROOT / "dist" / "libmojo-furl.so"
LIB_PATH = Path(os.environ["MOJOFURL_LIB"]) if "MOJOFURL_LIB" in os.environ else (
    _PACKAGED_LIB if _PACKAGED_LIB.exists() else _DEVELOPMENT_LIB
)

I = ctypes.c_int64
_SIGNATURES = {
    "mf_urlsplit": ([I, I, I, I], I),
    "mf_urlsplit_many": ([I, I, I, I, I, I, I], I),
    "mf_quote": ([I, I, I, I, I, I, I], I),
    "mf_unquote": ([I, I, I, I, I], I),
    "mf_query_decode": ([I, I, I, I, I, I], I),
}
_library: ctypes.CDLL | None = None
_bytes_address = ctypes.pythonapi.PyBytes_AsString
_bytes_address.argtypes = [ctypes.py_object]
_bytes_address.restype = ctypes.c_void_p


def lib() -> ctypes.CDLL:
    global _library
    if _library is None:
        if not LIB_PATH.exists():
            raise RuntimeError(
                f"Mojo library not found at {LIB_PATH}; run `pixi run build`"
            )
        _library = ctypes.CDLL(str(LIB_PATH))
        for name, (argtypes, restype) in _SIGNATURES.items():
            fn = getattr(_library, name)
            fn.argtypes = argtypes
            fn.restype = restype
    return _library


def _input_address(data: bytes) -> int:
    address = _bytes_address(data)
    if not address:
        raise RuntimeError("CPython returned a null bytes buffer")
    return address


def _check_result(operation: str, result: int, *, expected: int | None = None) -> int:
    if result < 0:
        raise RuntimeError(f"native {operation} failed with status {result}")
    if expected is not None and result != expected:
        raise RuntimeError(
            f"native {operation} returned {result}, expected {expected}"
        )
    return result


def split_offsets(data: bytes) -> tuple[int, ...]:
    spans = (I * 9)()
    result = lib().mf_urlsplit(
        _input_address(data), len(data), ctypes.addressof(spans), len(spans)
    )
    _check_result("urlsplit", result, expected=0)
    return tuple(spans)


def quote_bytes(data: bytes, safe: bytes, plus: bool = False) -> bytes:
    table = (ctypes.c_ubyte * 256)()
    for c in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-~" + safe:
        if c < 128:
            table[c] = 1
    dst = (ctypes.c_ubyte * max(1, len(data) * 3))()
    result = lib().mf_quote(
        _input_address(data),
        len(data),
        ctypes.addressof(table),
        len(table),
        plus,
        ctypes.addressof(dst),
        len(dst),
    )
    n = _check_result("quote", result)
    if n > len(dst):
        raise RuntimeError(f"native quote returned invalid output length {n}")
    return ctypes.string_at(dst, n)


def unquote_bytes(data: bytes, plus: bool = False) -> bytes:
    dst = (ctypes.c_ubyte * max(1, len(data)))()
    result = lib().mf_unquote(
        _input_address(data), len(data), plus, ctypes.addressof(dst), len(dst)
    )
    n = _check_result("unquote", result)
    if n > len(dst):
        raise RuntimeError(f"native unquote returned invalid output length {n}")
    return ctypes.string_at(dst, n)


def split_many_offsets(values: list[bytes]):
    packed = b"".join(values)
    offsets = np.empty(len(values) + 1, dtype=np.int64)
    offsets[0] = 0
    if values:
        lengths = np.fromiter(map(len, values), dtype=np.int64, count=len(values))
        np.cumsum(lengths, out=offsets[1:])
    spans = np.empty(max(1, len(values) * 9), dtype=np.int64)
    if values:
        result = lib().mf_urlsplit_many(
            _input_address(packed),
            len(packed),
            offsets.ctypes.data,
            offsets.size,
            len(values),
            spans.ctypes.data,
            spans.size,
        )
        _check_result("urlsplit_many", result, expected=len(values))
    return spans[: len(values) * 9].reshape(len(values), 9).tolist()


def query_items(data: bytes) -> list[tuple[str, str | None]]:
    dst = (ctypes.c_ubyte * max(1, len(data)))()
    pair_count = data.count(b"&") + 1
    spans = (I * (pair_count * 4))()
    result = lib().mf_query_decode(
        _input_address(data),
        len(data),
        ctypes.addressof(dst),
        len(dst),
        ctypes.addressof(spans),
        len(spans),
    )
    count = _check_result("query_decode", result)
    if count > pair_count:
        raise RuntimeError(f"native query_decode returned invalid pair count {count}")
    decoded = bytes(dst)
    items = []
    for i in range(count):
        ks, kn, vs, vn = spans[i * 4 : i * 4 + 4]
        if ks < 0 or kn < 0 or ks + kn > len(data):
            raise RuntimeError("native query_decode returned an invalid key span")
        if vn >= 0 and (vs < 0 or vs + vn > len(data)):
            raise RuntimeError("native query_decode returned an invalid value span")
        key = decoded[ks : ks + kn].decode("utf-8", "replace")
        value = (
            None
            if vn < 0
            else decoded[vs : vs + vn].decode("utf-8", "replace")
        )
        items.append((key, value))
    return items
