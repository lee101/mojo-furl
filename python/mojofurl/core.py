from __future__ import annotations

import re
import warnings
from copy import deepcopy
from posixpath import normpath
from urllib.parse import SplitResult, urljoin as _stdlib_urljoin
from urllib.parse import urlsplit as _stdlib_urlsplit
from urllib.parse import urlunsplit

from orderedmultidict import omdict

from ._lib import (
    query_items,
    quote_bytes,
    split_many_offsets,
    split_offsets,
    unquote_bytes,
)

DEFAULT_PORTS = {
    "acap": 674, "afp": 548, "dict": 2628, "dns": 53, "ftp": 21,
    "git": 9418, "gopher": 70, "hdl": 2641, "http": 80, "https": 443,
    "imap": 143, "ipp": 631, "ipps": 631, "irc": 194, "ircs": 6697,
    "ldap": 389, "ldaps": 636, "mms": 1755, "msrp": 2855, "mtqp": 1038,
    "nfs": 111, "nntp": 119, "nntps": 563, "pop": 110, "prospero": 1525,
    "redis": 6379, "rsync": 873, "rtsp": 554, "rtsps": 322, "rtspu": 5005,
    "sftp": 22, "sip": 5060, "sips": 5061, "smb": 445, "snews": 563,
    "snmp": 161, "ssh": 22, "svn": 3690, "telnet": 23, "tftp": 69,
    "ventrilo": 3784, "vnc": 5900, "wais": 210, "ws": 80, "wss": 443,
    "xmpp": 5222,
}
PERCENT_REGEX = r"\%[a-fA-F\d][a-fA-F\d]"
INVALID_HOST_CHARS = "!@#$%^&'\"*()+=:;/"
_ABSENT = object()
_SCHEME_RE = re.compile(r"[a-zA-Z][a-zA-Z\-.\+]*")
_ENCODED_PATH_RE = re.compile(
    r"^([\w%s]|(%s))*$" % (re.escape("-.~:@!$&'()*+,;="), PERCENT_REGEX)
)
_ENCODED_KEY_RE = re.compile(
    r"^([\w%s]|(%s))*$" % (re.escape("-.~:@!$&'()*+,;/?"), PERCENT_REGEX)
)
_ENCODED_VALUE_RE = re.compile(
    r"^([\w%s]|(%s))*$" % (re.escape("-.~:@!$&'()*+,;/?="), PERCENT_REGEX)
)


def attemptstr(value):
    try:
        return str(value)
    except Exception:
        return value


def non_string_iterable(value):
    return hasattr(value, "__iter__") and not isinstance(value, (str, bytes))


def _as_bytes(value) -> bytes:
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


def quote(value, safe="/", encoding="utf-8", errors="strict"):
    if isinstance(value, str):
        data = value.encode(encoding, errors)
    else:
        data = bytes(value)
    safe_bytes = (
        safe.encode("ascii", "ignore") if isinstance(safe, str) else bytes(safe)
    )
    return quote_bytes(data, safe_bytes).decode("ascii")


def quote_plus(value, safe="", encoding="utf-8", errors="strict"):
    if isinstance(value, str):
        data = value.encode(encoding, errors)
    else:
        data = bytes(value)
    safe_bytes = (
        safe.encode("ascii", "ignore") if isinstance(safe, str) else bytes(safe)
    )
    return quote_bytes(data, safe_bytes, plus=True).decode("ascii")


def unquote(value, encoding="utf-8", errors="replace"):
    if isinstance(value, bytes):
        return unquote_bytes(value).decode(encoding, errors)
    return unquote_bytes(value.encode("utf-8")).decode(encoding, errors)


def unquote_plus(value, encoding="utf-8", errors="replace"):
    if isinstance(value, bytes):
        return unquote_bytes(value, plus=True).decode(encoding, errors)
    return unquote_bytes(value.encode("utf-8"), plus=True).decode(encoding, errors)


def idna_encode(value):
    return value.encode("idna").decode("utf-8") if hasattr(value, "encode") else value


def idna_decode(value):
    return value.encode("utf-8").decode("idna") if isinstance(value, str) else value


def is_valid_port(port):
    text = str(port)
    return text.isdigit() and 0 < int(text) <= 65535


def is_valid_encoded_path_segment(segment):
    return _ENCODED_PATH_RE.match(segment) is not None


def is_valid_encoded_query_key(key):
    return _ENCODED_KEY_RE.match(key) is not None


def is_valid_encoded_query_value(value):
    return _ENCODED_VALUE_RE.match(value) is not None


def is_valid_scheme(scheme):
    return _SCHEME_RE.match(scheme) is not None


def is_valid_host(hostname):
    tokens = hostname.split(".")
    if tokens[-1] == "":
        tokens.pop()
    return "" not in tokens and all(
        not any(c in INVALID_HOST_CHARS for c in token) for token in tokens
    )


def get_scheme(url):
    if url.startswith(":"):
        return ""
    head = url.split("#", 1)[0].split("?", 1)[0].split("/", 1)[0]
    position = head.find(":")
    scheme = url[: max(0, position)] or None
    return scheme if scheme is None or is_valid_scheme(scheme) else None


def strip_scheme(url):
    scheme = get_scheme(url) or ""
    result = url[len(scheme) :]
    return result[1:] if result.startswith(":") else result


def set_scheme(url, scheme):
    rest = strip_scheme(url)
    return rest if scheme is None else f"{scheme}:{rest}"


def has_netloc(url):
    scheme = get_scheme(url)
    return url.startswith("//" if scheme is None else scheme + "://")


def urlsplit(url):
    if not isinstance(url, str):
        url = str(url)
    data = url.encode("utf-8")
    se, ns, ne, ps, pe, qs, qe, fs, fe = split_offsets(data)

    def text(start, end):
        return data[start:end].decode("utf-8")

    scheme = text(0, se) if se >= 0 else None
    netloc = text(ns, ne) if ns >= 0 else None
    path = text(ps, pe)
    query = text(qs, qe) if qs <= qe else ""
    fragment = text(fs, fe) if fs <= fe else ""
    if netloc is not None:
        _stdlib_urlsplit("http://" + netloc + "/")
    return SplitResult(scheme, netloc, path, query, fragment)


def urlsplit_many(urls):
    texts = [str(url) for url in urls]
    encoded = [url.encode("utf-8") for url in texts]
    all_spans = split_many_offsets(encoded)
    results = []
    if all(map(str.isascii, texts)):
        for data, spans in zip(texts, all_spans):
            se, ns, ne, ps, pe, qs, qe, fs, fe = spans
            results.append(
                SplitResult(
                    data[:se] if se >= 0 else None,
                    data[ns:ne] if ns >= 0 else None,
                    data[ps:pe],
                    data[qs:qe],
                    data[fs:fe],
                )
            )
        return results
    for data, spans in zip(encoded, all_spans):
        se, ns, ne, ps, pe, qs, qe, fs, fe = spans
        results.append(
            SplitResult(
                data[:se].decode("utf-8") if se >= 0 else None,
                data[ns:ne].decode("utf-8") if ns >= 0 else None,
                data[ps:pe].decode("utf-8"),
                data[qs:qe].decode("utf-8"),
                data[fs:fe].decode("utf-8"),
            )
        )
    return results


def urljoin(base, url):
    base_scheme = get_scheme(base) if has_netloc(base) else None
    url_scheme = get_scheme(url) if has_netloc(url) else None
    root = set_scheme(base, "http") if base_scheme is not None else base
    joined = _stdlib_urljoin(root, url)
    new_scheme = url_scheme if url_scheme is not None else base_scheme
    return set_scheme(joined, new_scheme) if new_scheme is not None and has_netloc(joined) else joined


def join_path_segments(*groups):
    result = []
    for source in groups:
        segments = list(source)
        if not segments or segments == [""]:
            continue
        if not result:
            result.extend(segments)
        else:
            if result[-1] == "" and (segments[0] != "" or len(segments) > 1):
                result.pop()
            elif result[-1] != "" and segments[0] == "" and len(segments) > 1:
                segments = segments[1:]
            result.extend(segments)
    return result


def remove_path_segments(segments, remove):
    if segments == [""]:
        segments.append("")
    if remove == [""]:
        remove.append("")
    if remove == segments:
        return []
    if len(remove) > len(segments):
        return segments
    target = list(remove)
    if len(target) > 1 and target[0] == "":
        target.pop(0)
    if target and target == segments[-len(target) :]:
        result = segments[: -len(target)]
        if remove[0] != "" and result:
            result.append("")
        return result
    return segments


class omdict1D(omdict):
    def load_items(self, items):
        self.clear()
        mapping = self._map
        itemlist = self._items
        for key, value in items:
            values = value if non_string_iterable(value) else (value,)
            if values:
                nodes = mapping.setdefault(key, [])
                for item in values:
                    nodes.append(itemlist.append(key, item))
        return self

    def add(self, key, value):
        values = value if non_string_iterable(value) else [value]
        if values:
            self._map.setdefault(key, [])
        for item in values:
            node = self._items.append(key, item)
            self._map[key].append(node)
        return self

    def set(self, key, value):
        return self._set(key, value)

    def __setitem__(self, key, value):
        return self._set(key, value)

    def _set(self, key, value):
        self.setlist(key, value if non_string_iterable(value) else [value])
        return self

    def _bin_update_items(self, items, replace_at_most_one, replacements, leftovers):
        for key, values in items:
            if not non_string_iterable(values) or not values:
                values = [values]
            for value in values:
                if value == []:
                    replacements[key] = []
                    leftovers[:] = [item for item in leftovers if key != item[0]]
                elif key in self and replacements.get(key, _ABSENT) in ([], _ABSENT):
                    replacements[key] = [value]
                elif key in self and not replace_at_most_one and len(
                    replacements[key]
                ) < len(self.values(key)):
                    replacements[key].append(value)
                elif replace_at_most_one:
                    replacements[key] = [value]
                else:
                    leftovers.append((key, value))


class Path:
    SAFE_SEGMENT_CHARS = ":@-._~!$&'()*+,;="

    def __init__(self, path="", force_absolute=lambda _: False, strict=False):
        self.segments = []
        self.strict = strict
        self._isabsolute = False
        self._force_absolute = force_absolute
        self.load(path)

    def _segments_from_path(self, path):
        result = []
        for segment in str(path).split("/"):
            if not is_valid_encoded_path_segment(segment):
                if self.strict:
                    warnings.warn(
                        f"Improperly encoded path string received: '{path}'.",
                        UserWarning,
                    )
                segment = quote(segment)
            result.append(unquote(segment))
        return result

    def _path_from_segments(self, segments):
        return "/".join(
            quote(attemptstr(segment), self.SAFE_SEGMENT_CHARS)
            for segment in segments
        )

    def load(self, path):
        if not path:
            segments = []
        elif hasattr(path, "segments") and non_string_iterable(path.segments):
            segments = list(path.segments)
        elif non_string_iterable(path):
            segments = list(path)
        else:
            segments = self._segments_from_path(path)
        self._isabsolute = segments and segments[0] == ""
        if self._force_absolute(self):
            self._isabsolute = bool(segments)
        if self.isabsolute and len(segments) > 1 and segments[0] == "":
            segments.pop(0)
        self.segments = segments
        return self

    def add(self, path):
        if hasattr(path, "segments"):
            new = list(path.segments)
        elif non_string_iterable(path):
            new = list(path)
        else:
            new = self._segments_from_path(path)
        if self.segments == [""] and new and new[0] != "":
            new.insert(0, "")
        base = self.segments
        if self.isabsolute and base and base[0] != "":
            base.insert(0, "")
        return self.load(join_path_segments(base, new))

    def set(self, path):
        return self.load(path)

    def remove(self, path):
        if path is True:
            return self.load("")
        segments = list(path) if non_string_iterable(path) else self._segments_from_path(path)
        base = ([""] if self.isabsolute else []) + self.segments
        return self.load(remove_path_segments(base, segments))

    def normalize(self):
        if str(self):
            normalized = normpath(str(self)) + ("/" * self.isdir)
            if normalized.startswith("//"):
                normalized = "/" + normalized.lstrip("/")
            self.load(normalized)
        return self

    @property
    def isabsolute(self):
        return True if self._force_absolute(self) else self._isabsolute

    @isabsolute.setter
    def isabsolute(self, value):
        if self._force_absolute(self):
            raise AttributeError("Path.isabsolute is True and read-only for URLs with a netloc")
        self._isabsolute = value

    @property
    def isdir(self):
        return not self.segments or self.segments[-1] == ""

    @property
    def isfile(self):
        return not self.isdir

    def asdict(self):
        return {
            "encoded": str(self), "isdir": self.isdir, "isfile": self.isfile,
            "segments": self.segments, "isabsolute": self.isabsolute,
        }

    def __truediv__(self, path):
        return deepcopy(self).add(path)

    def __bool__(self):
        return bool(self.segments)

    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        segments = list(self.segments)
        if self.isabsolute:
            segments = ["", ""] if not segments else [""] + segments
        return self._path_from_segments(segments)

    def __repr__(self):
        return f"{self.__class__.__name__}('{self}')"


class Query:
    SAFE_KEY_CHARS = "/?:@-._~!$'()*+,;"
    SAFE_VALUE_CHARS = SAFE_KEY_CHARS + "="

    def __init__(self, query="", strict=False):
        self.strict = strict
        self._params = omdict1D()
        self.load(query)

    def _extract_items_from_querystr(self, querystr):
        raw = querystr.encode("utf-8")
        decoded = query_items(raw)
        if not self.strict:
            return decoded
        raw_pairs = querystr.split("&")
        for pair in raw_pairs:
            raw_key, _, raw_value = pair.partition("=")
            if (
                not is_valid_encoded_query_key(raw_key)
                or not is_valid_encoded_query_value(raw_value)
            ):
                warnings.warn(
                    f"Incorrectly percent encoded query string received: '{querystr}'.",
                    UserWarning,
                )
        return decoded

    def _items(self, items):
        if not items:
            return []
        if hasattr(items, "allitems"):
            return list(items.allitems())
        if hasattr(items, "iterallitems"):
            return list(items.iterallitems())
        if hasattr(items, "items"):
            return list(items.items())
        if isinstance(items, str):
            return self._extract_items_from_querystr(items)
        return list(items)

    @property
    def params(self):
        return self._params

    @params.setter
    def params(self, params):
        self._params.load_items(self._items(params))

    def load(self, query):
        self._params.load_items(self._items(query))
        return self

    def add(self, args):
        for key, value in self._items(args):
            self.params.add(key, value)
        return self

    def set(self, mapping):
        self.params.updateall(mapping)
        return self

    def remove(self, query):
        if query is True:
            return self.load("")
        if hasattr(query, "items"):
            items = self._items(query)
        elif non_string_iterable(query):
            items = query
        else:
            items = [query]
        for item in items:
            if non_string_iterable(item) and len(item) == 2:
                self.params.popvalue(item[0], item[1], None)
            else:
                self.params.pop(item, None)
        return self

    def encode(self, delimiter="&", quote_plus=True, dont_quote="", delimeter=_ABSENT):
        if delimeter is not _ABSENT:
            delimiter = delimeter
        if dont_quote is True:
            key_safe, value_safe = self.SAFE_KEY_CHARS, self.SAFE_VALUE_CHARS
        elif dont_quote is False:
            key_safe = value_safe = ""
        else:
            key_safe = "".join(set(str(dont_quote)) & set(self.SAFE_KEY_CHARS))
            value_safe = "".join(set(str(dont_quote)) & set(self.SAFE_VALUE_CHARS))
        pairs = []
        for key, value in self.params.iterallitems():
            key_text = attemptstr(key)
            encoded_key = (
                globals()["quote_plus"](key_text, key_safe)
                if quote_plus
                else quote(key_text, key_safe)
            )
            if value is None:
                pairs.append(encoded_key)
                continue
            value_text = attemptstr(value)
            encoded_value = (
                globals()["quote_plus"](value_text, value_safe)
                if quote_plus
                else quote(value_text, value_safe)
            )
            if not encoded_key:
                encoded_value = encoded_value.replace("%3D", "=")
            pairs.append(encoded_key + "=" + encoded_value)
        return delimiter.join(pairs)

    def asdict(self):
        return {"encoded": str(self), "params": self.params.allitems()}

    def __bool__(self):
        return bool(len(self.params))

    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        return self.encode()

    def __repr__(self):
        return f"{self.__class__.__name__}('{self}')"


class Fragment:
    def __init__(self, fragment="", strict=False):
        self.strict = strict
        self.path = Path(strict=strict)
        self.query = Query(strict=strict)
        self.separator = True
        self.load(fragment)

    @property
    def args(self):
        return self.query.params

    @args.setter
    def args(self, value):
        self.query.load(value)

    def load(self, fragment):
        self.path.load("")
        self.query.load("")
        fragment = "" if fragment is None else str(fragment)
        tokens = fragment.split("?", 1)
        if len(tokens) == 1:
            self.query.load(fragment) if "=" in fragment else self.path.load(fragment)
        elif "=" in tokens[1]:
            self.path.load(tokens[0])
            self.query.load(tokens[1])
        else:
            self.path.load(fragment)
        return self

    def add(self, path=_ABSENT, args=_ABSENT):
        if path is not _ABSENT:
            self.path.add(path)
        if args is not _ABSENT:
            self.query.add(args)
        return self

    def set(self, path=_ABSENT, args=_ABSENT, separator=_ABSENT):
        if path is not _ABSENT:
            self.path.load(path)
        if args is not _ABSENT:
            self.query.load(args)
        if separator in (True, False):
            self.separator = separator
        return self

    def remove(self, fragment=_ABSENT, path=_ABSENT, args=_ABSENT):
        if fragment is True:
            self.load("")
        if path is not _ABSENT:
            self.path.remove(path)
        if args is not _ABSENT:
            self.query.remove(args)
        return self

    def asdict(self):
        return {
            "encoded": str(self), "separator": self.separator,
            "path": self.path.asdict(), "query": self.query.asdict(),
        }

    def __bool__(self):
        return bool(self.path) or bool(self.query)

    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        path, query = str(self.path), str(self.query)
        if path and (not query or not self.separator):
            path = path.replace("%3F", "?")
        separator = "?" if path and query and self.separator else ""
        return path + separator + query

    def __repr__(self):
        return f"{self.__class__.__name__}('{self}')"


class furl:
    def __init__(
        self, url="", args=_ABSENT, path=_ABSENT, fragment=_ABSENT,
        scheme=_ABSENT, netloc=_ABSENT, origin=_ABSENT,
        fragment_path=_ABSENT, fragment_args=_ABSENT,
        fragment_separator=_ABSENT, host=_ABSENT, port=_ABSENT,
        query=_ABSENT, query_params=_ABSENT, username=_ABSENT,
        password=_ABSENT, strict=False,
    ):
        self.strict = strict
        self._path = Path(
            force_absolute=lambda path: bool(path) and bool(self.netloc),
            strict=strict,
        )
        self._query = Query(strict=strict)
        self._fragment = Fragment(strict=strict)
        self.load(url)
        self.set(
            args=args, path=path, fragment=fragment, scheme=scheme,
            netloc=netloc, origin=origin, fragment_path=fragment_path,
            fragment_args=fragment_args, fragment_separator=fragment_separator,
            host=host, port=port, query=query, query_params=query_params,
            username=username, password=password,
        )

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        self._path.load(value)

    @property
    def query(self):
        return self._query

    @query.setter
    def query(self, value):
        self._query.load(value)

    @property
    def args(self):
        return self._query.params

    @args.setter
    def args(self, value):
        self._query.load(value)

    @property
    def fragment(self):
        return self._fragment

    @fragment.setter
    def fragment(self, value):
        self._fragment.load(value)

    def load(self, url):
        self.username = self.password = None
        self._host = self._port = self._scheme = None
        tokens = urlsplit("" if url is None else url)
        self.netloc = tokens.netloc
        self.scheme = tokens.scheme
        if not self.port:
            self._port = DEFAULT_PORTS.get(self.scheme)
        self.path.load(tokens.path)
        self.query.load(tokens.query)
        self.fragment.load(tokens.fragment)
        return self

    @property
    def scheme(self):
        return self._scheme

    @scheme.setter
    def scheme(self, value):
        self._scheme = value.lower() if hasattr(value, "lower") else value

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, value):
        _stdlib_urlsplit("http://%s/" % value)
        resembles_ipv6 = (
            value is not None and str(value).startswith("[")
            and ":" in value and str(value).endswith("]")
        )
        if value is not None and not resembles_ipv6 and not is_valid_host(value):
            raise ValueError(f"Invalid host '{value}'.")
        if hasattr(value, "lower"):
            value = value.lower()
        if hasattr(value, "startswith") and value.startswith("xn--"):
            value = idna_decode(value)
        self._host = value

    @property
    def port(self):
        return self._port or DEFAULT_PORTS.get(self.scheme)

    @port.setter
    def port(self, value):
        if value is None:
            self._port = DEFAULT_PORTS.get(self.scheme)
        elif is_valid_port(value):
            self._port = int(str(value))
        else:
            raise ValueError(f"Invalid port '{value}'.")

    @property
    def netloc(self):
        userpass = quote(self.username or "", safe="")
        if self.password is not None:
            userpass += ":" + quote(self.password, safe="")
        if userpass or self.username is not None:
            userpass += "@"
        netloc = idna_encode(self.host)
        if self.port and self.port != DEFAULT_PORTS.get(self.scheme):
            netloc = (netloc or "") + ":" + str(self.port)
        return (userpass or "") + (netloc or "") if userpass or netloc else netloc

    @netloc.setter
    def netloc(self, value):
        _stdlib_urlsplit("http://%s/" % value)
        username = password = host = port = None
        netloc = value
        if netloc and "@" in netloc:
            userpass, netloc = netloc.split("@", 1)
            if ":" in userpass:
                username, password = userpass.split(":", 1)
            else:
                username = userpass
        if netloc and ":" in netloc:
            if "]" in netloc:
                colon, bracket = netloc.rfind(":"), netloc.rfind("]")
                if colon > bracket + 1:
                    raise ValueError(f"Invalid netloc '{netloc}'.")
                if colon == bracket + 1:
                    host, port = netloc.rsplit(":", 1)
                else:
                    host = netloc
            else:
                host, port = netloc.rsplit(":", 1)
        else:
            host = netloc
        self.port = port
        self.host = host
        self.username = None if username is None else unquote(username)
        self.password = None if password is None else unquote(password)

    @property
    def origin(self):
        scheme = self.scheme or ""
        host = idna_encode(self.host) or ""
        port = (
            ":" + str(self.port)
            if self.port and self.port != DEFAULT_PORTS.get(self.scheme)
            else ""
        )
        return f"{scheme}://{host}{port}"

    @origin.setter
    def origin(self, value):
        if value is None:
            self.scheme = self.netloc = None
            return
        tokens = value.split("://", 1)
        if len(tokens) == 1:
            host_port = value
        else:
            self.scheme, host_port = tokens
        if ":" in host_port:
            self.host, self.port = host_port.split(":", 1)
        else:
            self.host = host_port

    @property
    def url(self):
        return self.tostr()

    @url.setter
    def url(self, value):
        self.load(value)

    def add(self, args=_ABSENT, path=_ABSENT, fragment_path=_ABSENT,
            fragment_args=_ABSENT, query_params=_ABSENT):
        if path is not _ABSENT:
            self.path.add(path)
        if args is not _ABSENT:
            self.query.add(args)
        if query_params is not _ABSENT:
            self.query.add(query_params)
        if fragment_path is not _ABSENT or fragment_args is not _ABSENT:
            self.fragment.add(path=fragment_path, args=fragment_args)
        return self

    def set(
        self, args=_ABSENT, path=_ABSENT, fragment=_ABSENT, query=_ABSENT,
        scheme=_ABSENT, username=_ABSENT, password=_ABSENT, host=_ABSENT,
        port=_ABSENT, netloc=_ABSENT, origin=_ABSENT, query_params=_ABSENT,
        fragment_path=_ABSENT, fragment_args=_ABSENT,
        fragment_separator=_ABSENT,
    ):
        original = self.url
        try:
            for name, value in (
                ("username", username), ("password", password),
                ("netloc", netloc), ("origin", origin), ("scheme", scheme),
                ("host", host), ("port", port),
            ):
                if value is not _ABSENT:
                    setattr(self, name, value)
            if path is not _ABSENT:
                self.path.load(path)
            for value in (query, args, query_params):
                if value is not _ABSENT:
                    self.query.load(value)
            if fragment is not _ABSENT:
                self.fragment.load(fragment)
            if fragment_path is not _ABSENT:
                self.fragment.path.load(fragment_path)
            if fragment_args is not _ABSENT:
                self.fragment.query.load(fragment_args)
            if fragment_separator is not _ABSENT:
                self.fragment.separator = fragment_separator
        except Exception:
            self.load(original)
            raise
        return self

    def remove(
        self, args=_ABSENT, path=_ABSENT, fragment=_ABSENT,
        query=_ABSENT, scheme=False, username=False, password=False,
        host=False, port=False, netloc=False, origin=False,
        query_params=_ABSENT, fragment_path=_ABSENT, fragment_args=_ABSENT,
    ):
        for name, enabled in (
            ("scheme", scheme), ("username", username), ("password", password),
            ("host", host), ("port", port), ("netloc", netloc), ("origin", origin),
        ):
            if enabled is True:
                setattr(self, name, None)
        if path is not _ABSENT:
            self.path.remove(path)
        for value in (args, query, query_params):
            if value is not _ABSENT:
                self.query.remove(value)
        if fragment is not _ABSENT:
            self.fragment.remove(fragment)
        if fragment_path is not _ABSENT:
            self.fragment.path.remove(fragment_path)
        if fragment_args is not _ABSENT:
            self.fragment.query.remove(fragment_args)
        return self

    def tostr(self, query_delimiter="&", query_quote_plus=True, query_dont_quote=""):
        encoded_query = self.query.encode(
            query_delimiter, query_quote_plus, query_dont_quote
        )
        result = urlunsplit(
            (self.scheme or "", self.netloc, str(self.path), encoded_query, str(self.fragment))
        )
        if self.scheme == "":
            result = ":" + result
        if self.netloc == "":
            if self.scheme is None:
                result = "//" + result
            elif strip_scheme(result) == "":
                result += "//"
        return result

    def join(self, *urls):
        for value in urls:
            self.load(urljoin(self.url, str(value)))
        return self

    def copy(self):
        return self.__class__(self)

    def asdict(self):
        return {
            "url": self.url, "scheme": self.scheme, "username": self.username,
            "password": self.password, "host": self.host,
            "host_encoded": idna_encode(self.host), "port": self.port,
            "netloc": self.netloc, "origin": self.origin,
            "path": self.path.asdict(), "query": self.query.asdict(),
            "fragment": self.fragment.asdict(),
        }

    def __truediv__(self, path):
        return self.copy().add(path=path)

    def __eq__(self, other):
        return self.url == getattr(other, "url", None)

    def __str__(self):
        return self.tostr()

    def __repr__(self):
        return f"{self.__class__.__name__}('{self}')"
