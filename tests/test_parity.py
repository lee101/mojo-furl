from __future__ import annotations

import random
import string

import furl as upstream
import pytest

import mojofurl as mojo
from mojofurl import _lib


URLS = [
    "",
    "http://example.com",
    "https://example.com:8443/a%20path/file?x=1&x=2&flag#section",
    "//user:p%40ss@example.com/path",
    "mailto:user@example.com",
    "h1://example.com/path",
    "x^y:/path",
    "git+ssh://git@example.com/repo.git",
    "http://[2001:db8::1]:8080/a?empty=&bare",
    "///absolute",
    ":relative",
    "custom:/one/two?unicode=%E2%98%83#frag?still-path",
]


@pytest.mark.parametrize("value", URLS)
def test_urlsplit_matches_upstream(value):
    got = mojo.urlsplit(value)
    expected = upstream.urlsplit(value)
    assert tuple(got) == tuple(expected)
    if got.netloc is not None:
        assert got.username == expected.username
        assert got.password == expected.password
        assert got.hostname == expected.hostname
        assert got.port == expected.port


def test_urlsplit_many_matches_upstream():
    values = URLS * 100
    got = mojo.urlsplit_many(values)
    expected = [upstream.urlsplit(value) for value in values]
    assert [tuple(item) for item in got] == [tuple(item) for item in expected]
    assert mojo.urlsplit_many([]) == []


@pytest.mark.parametrize("count", [4095, 4096])
def test_urlsplit_many_large_boundaries(count):
    values = [URLS[i % len(URLS)] + str(i) for i in range(count)]
    got = mojo.urlsplit_many(values)
    expected = [upstream.urlsplit(value) for value in values]
    assert [tuple(item) for item in got] == [tuple(item) for item in expected]


@pytest.mark.parametrize("tail", range(18))
def test_urlsplit_simd_tail(tail):
    value = "https://example.com/" + ("x" * tail) + "?q=1#fragment"
    assert tuple(mojo.urlsplit(value)) == tuple(upstream.urlsplit(value))


@pytest.mark.parametrize("value", URLS)
def test_furl_roundtrip_and_properties_match_upstream(value):
    got, expected = mojo.furl(value), upstream.furl(value)
    assert str(got) == str(expected)
    for name in ("scheme", "username", "password", "host", "port", "netloc", "origin"):
        assert getattr(got, name) == getattr(expected, name)
    assert got.path.asdict() == expected.path.asdict()
    assert got.query.params.allitems() == expected.query.params.allitems()
    assert str(got.fragment) == str(expected.fragment)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/",
        "/a/b/",
        "a//b",
        "/a%20b/caf%C3%A9",
        "//a/./b/../c//",
        "symbols:@!$&'()*+,;=",
    ],
)
def test_path_load_and_normalize_matches_upstream(value):
    got, expected = mojo.Path(value), upstream.Path(value)
    assert got.asdict() == expected.asdict()
    assert str(got.normalize()) == str(expected.normalize())


def test_path_mutations_match_upstream():
    got, expected = mojo.Path("/a/b/"), upstream.Path("/a/b/")
    operations = [
        ("add", "c d"),
        ("add", ["e", "f"]),
        ("remove", "e/f"),
        ("set", "/x/y/"),
        ("remove", "y/"),
    ]
    for method, value in operations:
        getattr(got, method)(value)
        getattr(expected, method)(value)
        assert got.asdict() == expected.asdict()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a=1&b=two",
        "a=1&a=2&flag",
        "space=a+b&encoded=%E2%98%83",
        "===equal=sign===",
        "empty=&=value&&last",
    ],
)
def test_query_parse_and_encode_matches_upstream(value):
    got, expected = mojo.Query(value), upstream.Query(value)
    assert got.params.allitems() == expected.params.allitems()
    assert str(got) == str(expected)
    for options in (
        {},
        {"delimiter": ";"},
        {"quote_plus": False},
        {"dont_quote": "/?@"},
        {"dont_quote": True},
    ):
        assert got.encode(**options) == expected.encode(**options)


@pytest.mark.parametrize("tail", range(18))
def test_query_decode_simd_tail(tail):
    value = ("k" * tail) + "=value+with%2Fescapes&bare"
    got, expected = mojo.Query(value), upstream.Query(value)
    assert got.params.allitems() == expected.params.allitems()


def test_query_ordered_multivalue_mutations_match_upstream():
    got, expected = mojo.Query("a=1&a=2&b=3"), upstream.Query("a=1&a=2&b=3")
    for method, value in [
        ("add", [("a", ["4", "5"]), ("c", None)]),
        ("set", [("a", ["x", "y"]), ("d", "z")]),
        ("remove", [("a", "x"), "b"]),
    ]:
        getattr(got, method)(value)
        getattr(expected, method)(value)
        assert got.params.allitems() == expected.params.allitems()
        assert str(got) == str(expected)


def test_query_iterable_values_load_matches_upstream():
    values = [("a", ["1", "2"]), ("empty", []), ("bare", None)]
    got, expected = mojo.Query(values), upstream.Query(values)
    assert got.params.allitems() == expected.params.allitems()


@pytest.mark.parametrize(
    "value",
    ["", "path", "a/b?x=1&x=2", "query=only", "dog?machine?yes", "/x?#=v"],
)
def test_fragment_matches_upstream(value):
    got, expected = mojo.Fragment(value), upstream.Fragment(value)
    assert str(got) == str(expected)
    assert got.asdict() == expected.asdict()


def test_furl_add_set_remove_matches_upstream():
    got = mojo.furl("https://user:pass@example.com/a?x=1#frag")
    expected = upstream.furl("https://user:pass@example.com/a?x=1#frag")
    actions = [
        ("add", {"path": "b c", "args": [("x", "2"), ("flag", None)]}),
        ("set", {"host": "EXAMPLE.ORG", "port": 9443, "fragment_path": "top"}),
        ("remove", {"username": True, "password": True, "query": ["flag"]}),
        ("set", {"fragment_args": [("page", "3")], "fragment_separator": True}),
    ]
    for method, kwargs in actions:
        getattr(got, method)(**kwargs)
        getattr(expected, method)(**kwargs)
        assert str(got) == str(expected)


def test_join_and_division_match_upstream():
    got, expected = mojo.furl("custom://example.com/a/b/"), upstream.furl(
        "custom://example.com/a/b/"
    )
    got.join("../c?x=1")
    expected.join("../c?x=1")
    assert str(got) == str(expected)
    assert str(got / "d e") == str(expected / "d e")


@pytest.mark.parametrize(
    "text,safe",
    [
        ("simple", ""),
        ("a b/c?d=e", "/"),
        ("café and lambda λ", ""),
        ("~._-:@!$&'()*+,;=", ":@!$&'()*+,;="),
        ("100% complete", ""),
        ("café", "é"),
    ],
)
def test_quote_unquote_matches_stdlib_surface(text, safe):
    encoded = mojo.quote(text, safe=safe)
    assert encoded == upstream.quote(text, safe=safe)
    assert mojo.unquote(encoded) == upstream.unquote(encoded)
    assert mojo.quote_plus(text, safe=safe) == upstream.urllib.parse.quote_plus(
        text, safe=safe
    )


def test_large_random_codec_parity():
    rng = random.Random(7)
    alphabet = string.ascii_letters + string.digits + " /?&=%+" + "éλ"
    value = "".join(rng.choice(alphabet) for _ in range(100_000))
    encoded = mojo.quote_plus(value, safe="/?")
    assert encoded == upstream.urllib.parse.quote_plus(value, safe="/?")
    assert mojo.unquote_plus(encoded) == value


@pytest.mark.parametrize("port", [0, -1, 1, 80, 65535, 65536, "443", "x"])
def test_port_validation_matches_upstream(port):
    assert mojo.is_valid_port(port) == upstream.is_valid_port(port)


@pytest.mark.parametrize(
    "groups",
    [
        (["a"], ["b"]),
        (["a", ""], ["", "b"]),
        (["", "a"], ["b", "c"]),
        ([], ["a"]),
    ],
)
def test_join_path_segments_matches_upstream(groups):
    assert mojo.join_path_segments(*groups) == upstream.join_path_segments(*groups)


def test_invalid_ports_and_ipv6_raise():
    for value in ("http://example.com:99999/", "http://[not-ipv6/"):
        with pytest.raises(ValueError):
            mojo.furl(value)


def test_public_helpers_match_upstream():
    assert mojo.get_scheme("git+ssh://example.com/x") == upstream.get_scheme(
        "git+ssh://example.com/x"
    )
    assert mojo.strip_scheme("git+ssh://example.com/x") == upstream.strip_scheme(
        "git+ssh://example.com/x"
    )
    assert mojo.set_scheme("//example.com/x", "https") == upstream.set_scheme(
        "//example.com/x", "https"
    )
    assert mojo.has_netloc("https://example.com") == upstream.has_netloc(
        "https://example.com"
    )
    assert mojo.remove_path_segments(
        ["", "a", "b"], ["b"]
    ) == upstream.remove_path_segments(["", "a", "b"], ["b"])
    for value in ("https", "git+ssh", "1bad"):
        assert mojo.is_valid_scheme(value) == upstream.is_valid_scheme(value)
    for value in ("example.com", "example..com", "bad@example.com"):
        assert mojo.is_valid_host(value) == upstream.is_valid_host(value)
    for value in ("a%20b", "bad%2"):
        assert (
            mojo.is_valid_encoded_path_segment(value)
            == upstream.is_valid_encoded_path_segment(value)
        )
        assert (
            mojo.is_valid_encoded_query_key(value)
            == upstream.is_valid_encoded_query_key(value)
        )
        assert (
            mojo.is_valid_encoded_query_value(value)
            == upstream.is_valid_encoded_query_value(value)
        )


def test_copy_tostr_asdict_and_idna_match_upstream():
    value = "https://münich.example/a?x=1#frag"
    got, expected = mojo.furl(value), upstream.furl(value)
    assert got.tostr() == expected.tostr()
    assert got.copy().asdict() == expected.copy().asdict()
    assert mojo.idna_encode("münich.example") == upstream.idna_encode(
        "münich.example"
    )
    encoded = mojo.idna_encode("münich.example")
    assert mojo.idna_decode(encoded) == upstream.idna_decode(encoded)


def test_strict_mode_warns_for_malformed_encoding():
    with pytest.warns(UserWarning):
        mojo.Path("/bad%2", strict=True)
    with pytest.warns(UserWarning):
        mojo.Query("bad%2=value", strict=True)


def test_native_error_status_is_not_swallowed():
    with pytest.raises(RuntimeError, match="native test failed with status -2"):
        _lib._check_result("test", -2)


def test_native_functions_reject_invalid_buffer_contracts():
    native = _lib.lib()
    assert native.mf_urlsplit(0, 1, 0, 0) < 0
    assert native.mf_urlsplit_many(0, 0, 0, 0, 1, 0, 0) < 0
    assert native.mf_quote(0, 1, 0, 0, 0, 0, 0) < 0
    assert native.mf_unquote(0, 1, 0, 0, 0) < 0
    assert native.mf_query_decode(0, 1, 0, 0, 0, 0) < 0
