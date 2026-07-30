# mojo-furl

`mojo-furl` is a Mojo-accelerated port of the URL parsing and manipulation
core of Python's [`furl`](https://github.com/gruns/furl). It keeps furl's
mutable object model and ordered multi-value query behavior while moving the
linear byte-scanning work into one compiled Mojo shared library.

The Python package is named `mojofurl`, so it can be installed beside `furl`
for differential testing. The covered names and method signatures follow
furl 2.1.4.

## Coverage

Implemented:

- `furl`, `Path`, `Query`, and `Fragment`
- URL component properties, default ports, user information, IDNA hosts, and
  IPv6 literals
- `load()`, `add()`, `set()`, `remove()`, `join()`, `copy()`, `tostr()`,
  `asdict()`, path division, and path normalization
- ordered repeated query keys, bare keys, blank values, custom delimiters,
  `quote_plus`, and `dont_quote`
- `urlsplit()`, `urljoin()`, percent quote/unquote helpers, scheme and host
  validators, and path-segment helpers
- `urlsplit_many()`, an additional bulk interface that amortizes the FFI call
  across many URLs

Not implemented are furl's abstract composition-interface classes, deprecated
`pathstr`/`querystr`/`fragmentstr` properties, Python 2 compatibility helpers,
and byte-for-byte reproduction of every warning message. Strict mode still
warns for malformed encoded path and query input. This is not a replacement
for every undocumented subclassing hook in furl.

## Install and build

The repository pins the tested Mojo nightly and installs upstream furl for
parity tests:

```bash
pixi install
pixi run build
pixi run test
```

The build creates `dist/libmojo-furl.so` and stages the same library as package
data. Install the built package with:

```bash
pixi run build
pixi run python -m pip install .
```

The installed package loads its bundled library. Developers can instead set
`MOJOFURL_LIB` to a compatible library path.

## Usage

```python
from mojofurl import Query, furl, urlsplit_many

url = furl("https://user@example.com/a%20path?tag=one&tag=two")
url.path.add("report 2026")
url.args.add("format", "json")

assert url.path.segments == ["a path", "report 2026"]
assert url.args.getlist("tag") == ["one", "two"]
assert str(url) == (
    "https://user@example.com/a%20path/report%202026"
    "?tag=one&tag=two&format=json"
)

parts = urlsplit_many(["https://example.com/a?x=1", "mailto:user@example.com"])
assert parts[0].hostname == "example.com"
assert parts[1].scheme == "mailto"
```

## Benchmarks

Measured with `pixi run bench` on an Intel Xeon E5-2697 v4 at 2.30 GHz,
CPython 3.13.14. Times are the best of three warmed runs. A speedup above
`1.00x` favors mojo-furl.

| Case | mojo-furl | furl 2.1.4 | Speedup |
|---|---:|---:|---:|
| quote_plus, 3.7M chars | 19.42 ms | 180.25 ms | 9.28x |
| unquote_plus, 5.3M chars | 23.70 ms | 351.27 ms | 14.82x |
| urlsplit, 1.2M-char URL | 1.31 ms | 4.94 ms | 3.77x |
| Query parse, 100k pairs | 296.81 ms | 1949.59 ms | 6.57x |
| urlsplit_many, 100k URLs | 312.66 ms | 1470.03 ms | 4.70x |

These numbers include UTF-8 conversion, ctypes calls, result construction,
and ordered-multidict insertion. They are workload-specific; short individual
URLs may not recover the fixed FFI cost.

GPU acceleration is intentionally not included. These delimiter and percent
scans perform well below roughly two arithmetic operations per byte moved, so
device transfer and launch overhead would dominate. Bulk splitting also stays
serial: locked measurements showed that initializing CPU workers cost more
than parallelizing its short per-URL native scans.

## How it works

`src/furl.mojo` is one compilation unit exporting C-ABI functions for URL
delimiter scans, percent encoding, percent decoding, decoded query
tokenization, and bulk URL splitting. Python passes UTF-8 buffers as integer
addresses through ctypes without copying immutable byte inputs. The caller
owns every allocation: output byte arrays and NumPy `Int64` offset/span arrays
are passed zero-copy to Mojo, then converted to Python strings and
`SplitResult` objects. Every native entry point receives explicit buffer
lengths, rejects null or inconsistent ranges, and has its status and returned
length checked by Python before output is consumed.

Query decoding is a single pass. Mojo records key and value spans after
decoding `%HH` and `+`, while Python inserts the resulting objects into an
`omdict1D`. Bulk splitting packs URL bytes contiguously and supplies an offset
array, so one FFI call produces nine component offsets per URL.

The test suite compares behavior directly with installed furl 2.1.4, including
encoded Unicode, repeated and bare query keys, custom schemes, IPv6, fragments,
path mutation, URL joining, validation, and large randomized codec input.
