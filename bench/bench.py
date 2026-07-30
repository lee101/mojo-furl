from __future__ import annotations

import math
import os
import platform
import sys
import time

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"
    ),
)

import furl as upstream  # noqa: E402
import mojofurl as mojo  # noqa: E402


def best_time(fn, repeat=5):
    best = math.inf
    result = None
    for _ in range(repeat):
        start = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - start)
    return best, result


def cpu_name():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown CPU"


def main():
    text = ("URL parsing: café / lambda λ?x=1&y=two words; " * 80_000)
    encoded = upstream.urllib.parse.quote_plus(text, safe="/?")
    long_url = "https://user:pass@example.com:8443/" + ("segment/" * 150_000)
    long_url += "?a=1&b=two#fragment"
    query = "&".join(
        f"k{i % 250}=value+{i}%2Ftail" if i % 11 else f"flag{i}"
        for i in range(100_000)
    )
    urls = [
        f"https://user:p%40ss@host{i % 100}.example:{8000 + i % 100}/"
        f"a/{i}?x={i}&tag=a%20b#row-{i}"
        for i in range(100_000)
    ]

    cases = [
        (
            "quote_plus, 3.7M chars",
            lambda: mojo.quote_plus(text, safe="/?"),
            lambda: upstream.urllib.parse.quote_plus(text, safe="/?"),
        ),
        (
            "unquote_plus, 5.3M chars",
            lambda: mojo.unquote_plus(encoded),
            lambda: upstream.urllib.parse.unquote_plus(encoded),
        ),
        (
            "urlsplit, 1.2M-char URL",
            lambda: mojo.urlsplit(long_url),
            lambda: upstream.urlsplit(long_url),
        ),
        (
            "Query parse, 100k pairs",
            lambda: mojo.Query(query),
            lambda: upstream.Query(query),
        ),
        (
            "urlsplit_many, 100k URLs",
            lambda: mojo.urlsplit_many(urls),
            lambda: [upstream.urlsplit(value) for value in urls],
        ),
    ]

    print(f"Machine: {cpu_name()}; {platform.python_implementation()} {platform.python_version()}")
    print()
    print("| Case | mojo-furl | furl 2.1.4 | Speedup |")
    print("|---|---:|---:|---:|")
    for name, ours, reference in cases:
        ours()
        reference()
        ours_s, ours_value = best_time(ours, repeat=3)
        ref_s, ref_value = best_time(reference, repeat=3)
        if name.startswith("Query"):
            assert ours_value.params.allitems() == ref_value.params.allitems()
        elif name.startswith("urlsplit_many"):
            assert [tuple(v) for v in ours_value] == [tuple(v) for v in ref_value]
        else:
            assert ours_value == ref_value
        print(
            f"| {name} | {ours_s * 1000:.2f} ms | {ref_s * 1000:.2f} ms | "
            f"{ref_s / ours_s:.2f}x |"
        )


if __name__ == "__main__":
    main()
