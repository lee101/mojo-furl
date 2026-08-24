from std.sys.info import simd_width_of


comptime BPtr = UnsafePointer[UInt8, AnyOrigin[mut=True]]
comptime IPtr = UnsafePointer[Int64, AnyOrigin[mut=True]]


def is_alpha(c: UInt8) -> Bool:
    return (c >= 65 and c <= 90) or (c >= 97 and c <= 122)


def hex_value(c: UInt8) -> Int:
    if c >= 48 and c <= 57:
        return Int(c - 48)
    if c >= 65 and c <= 70:
        return Int(c - 65) + 10
    if c >= 97 and c <= 102:
        return Int(c - 97) + 10
    return -1


def urlsplit_impl(src_addr: Int, n: Int, spans_addr: Int):
    var src = BPtr(unsafe_from_address=src_addr)
    var spans = IPtr(unsafe_from_address=spans_addr)

    var fragment_mark = n
    var query_mark = n
    var first_slash = n
    comptime W = simd_width_of[DType.float64]()
    var i = 0
    while i + W <= n:
        var chars = src.load[width=W](i)
        var hits = (
            chars.eq(UInt8(35)).cast[DType.uint8]()
            + chars.eq(UInt8(63)).cast[DType.uint8]()
        )
        if first_slash == n and query_mark == n:
            hits += chars.eq(UInt8(47)).cast[DType.uint8]()
        if hits.reduce_add() != 0:
            for lane in range(W):
                var c = chars[lane]
                if c == 35:
                    fragment_mark = i + lane
                    break
                if c == 63 and query_mark == n:
                    query_mark = i + lane
                elif c == 47 and first_slash == n and query_mark == n:
                    first_slash = i + lane
        i += W
        if fragment_mark < n:
            break
    while i < n and fragment_mark == n:
        var c = src[i]
        if c == 35:
            fragment_mark = i
            break
        if c == 63 and query_mark == n:
            query_mark = i
        elif c == 47 and first_slash == n and query_mark == n:
            first_slash = i
        i += 1

    if query_mark > fragment_mark:
        query_mark = fragment_mark
    var prefix_end = query_mark
    if first_slash > prefix_end:
        first_slash = prefix_end

    var scheme_end = -1
    if n > 0 and src[0] == 58:
        scheme_end = 0
    elif n > 0 and is_alpha(src[0]):
        for i in range(1, first_slash):
            if src[i] == 58:
                scheme_end = i
                break

    var after_scheme = 0
    if scheme_end >= 0:
        after_scheme = scheme_end + 1

    var netloc_start = -1
    var netloc_end = -1
    var path_start = after_scheme
    if after_scheme + 1 < prefix_end and src[after_scheme] == 47 and src[after_scheme + 1] == 47:
        netloc_start = after_scheme + 2
        netloc_end = prefix_end
        for i in range(netloc_start, prefix_end):
            if src[i] == 47:
                netloc_end = i
                break
        path_start = netloc_end

    spans[0] = Int64(scheme_end)
    spans[1] = Int64(netloc_start)
    spans[2] = Int64(netloc_end)
    spans[3] = Int64(path_start)
    spans[4] = Int64(query_mark)
    spans[5] = Int64(query_mark + 1 if query_mark < fragment_mark else query_mark)
    spans[6] = Int64(fragment_mark)
    spans[7] = Int64(fragment_mark + 1 if fragment_mark < n else fragment_mark)
    spans[8] = Int64(n)


@export("mf_urlsplit")
def mf_urlsplit(
    src_addr: Int, n: Int, spans_addr: Int, spans_len: Int
) abi("C") -> Int:
    if src_addr == 0 or n < 0 or spans_addr == 0 or spans_len < 9:
        return -1
    urlsplit_impl(src_addr, n, spans_addr)
    return 0


@export("mf_urlsplit_many")
def mf_urlsplit_many(
    src_addr: Int,
    src_len: Int,
    offsets_addr: Int,
    offsets_len: Int,
    count: Int,
    spans_addr: Int,
    spans_len: Int,
) abi("C") -> Int:
    if (
        src_addr == 0
        or src_len < 0
        or offsets_addr == 0
        or count < 0
        or offsets_len < count + 1
        or spans_addr == 0
        or spans_len // 9 < count
    ):
        return -1
    var offsets = IPtr(unsafe_from_address=offsets_addr)
    if offsets[0] != 0:
        return -2
    for i in range(count):
        var begin = Int(offsets[i])
        var end = Int(offsets[i + 1])
        if begin < 0 or end < begin or end > src_len:
            return -2
        urlsplit_impl(src_addr + begin, end - begin, spans_addr + i * 72)
    return count


@export("mf_quote")
def mf_quote(
    src_addr: Int,
    n: Int,
    safe_addr: Int,
    safe_len: Int,
    plus: Int,
    dst_addr: Int,
    dst_len: Int,
) abi("C") -> Int:
    if (
        src_addr == 0
        or n < 0
        or safe_addr == 0
        or safe_len < 256
        or dst_addr == 0
        or dst_len / 3 < n
    ):
        return -1
    var src = BPtr(unsafe_from_address=src_addr)
    var safe = BPtr(unsafe_from_address=safe_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var digits = String("0123456789ABCDEF").unsafe_ptr()
    var j = 0
    for i in range(n):
        var c = src[i]
        if safe[Int(c)] != 0:
            dst[j] = c
            j += 1
        elif plus != 0 and c == 32:
            dst[j] = 43
            j += 1
        else:
            dst[j] = 37
            dst[j + 1] = digits[Int(c) >> 4]
            dst[j + 2] = digits[Int(c) & 15]
            j += 3
    return j


@export("mf_unquote")
def mf_unquote(
    src_addr: Int, n: Int, plus: Int, dst_addr: Int, dst_len: Int
) abi("C") -> Int:
    if src_addr == 0 or n < 0 or dst_addr == 0 or dst_len < n:
        return -1
    var src = BPtr(unsafe_from_address=src_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var i = 0
    var j = 0
    while i < n:
        var c = src[i]
        if c == 37 and i + 2 < n:
            var hi = hex_value(src[i + 1])
            var lo = hex_value(src[i + 2])
            if hi >= 0 and lo >= 0:
                dst[j] = UInt8((hi << 4) | lo)
                i += 3
                j += 1
                continue
        if plus != 0 and c == 43:
            dst[j] = 32
        else:
            dst[j] = c
        i += 1
        j += 1
    return j


def decode_part(src: BPtr, begin: Int, end: Int, dst: BPtr, dst_begin: Int) -> Int:
    var i = begin
    var j = dst_begin
    comptime W = simd_width_of[DType.float64]()
    while i < end:
        if i + W <= end:
            var chars = src.load[width=W](i)
            var special = (
                chars.eq(UInt8(37)).cast[DType.uint8]()
                + chars.eq(UInt8(43)).cast[DType.uint8]()
            )
            if special.reduce_add() == 0:
                dst.store(j, chars)
                i += W
                j += W
                continue
        var c = src[i]
        if c == 37 and i + 2 < end:
            var hi = hex_value(src[i + 1])
            var lo = hex_value(src[i + 2])
            if hi >= 0 and lo >= 0:
                dst[j] = UInt8((hi << 4) | lo)
                i += 3
                j += 1
                continue
        dst[j] = 32 if c == 43 else c
        i += 1
        j += 1
    return j


def decode_query_pair(
    src: BPtr,
    pair_start: Int,
    boundary: Int,
    equal: Int,
    dst: BPtr,
    dst_pos: Int,
    spans: IPtr,
    pair_index: Int,
) -> Int:
    var key_end = boundary if equal < 0 else equal
    var key_start_out = dst_pos
    var next_dst_pos = decode_part(src, pair_start, key_end, dst, dst_pos)
    spans[pair_index * 4] = Int64(key_start_out)
    spans[pair_index * 4 + 1] = Int64(next_dst_pos - key_start_out)

    if equal < 0:
        spans[pair_index * 4 + 2] = Int64(next_dst_pos)
        spans[pair_index * 4 + 3] = -1
    else:
        var value_start_out = next_dst_pos
        next_dst_pos = decode_part(
            src, equal + 1, boundary, dst, next_dst_pos
        )
        spans[pair_index * 4 + 2] = Int64(value_start_out)
        spans[pair_index * 4 + 3] = Int64(next_dst_pos - value_start_out)
    return next_dst_pos


@export("mf_query_decode")
def mf_query_decode(
    src_addr: Int,
    n: Int,
    dst_addr: Int,
    dst_len: Int,
    spans_addr: Int,
    spans_len: Int,
) abi("C") -> Int:
    if (
        src_addr == 0
        or n < 0
        or dst_addr == 0
        or dst_len < n
        or spans_addr == 0
        or spans_len < 4
    ):
        return -1
    var src = BPtr(unsafe_from_address=src_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var spans = IPtr(unsafe_from_address=spans_addr)
    var pair_start = 0
    var pair_index = 0
    var dst_pos = 0
    var equal = -1
    var boundary = 0
    comptime W = simd_width_of[DType.float64]()

    while boundary < n:
        if boundary + W <= n:
            var chars = src.load[width=W](boundary)
            var delimiters = (
                chars.eq(UInt8(38)).cast[DType.uint8]()
                + chars.eq(UInt8(61)).cast[DType.uint8]()
            )
            if delimiters.reduce_add() == 0:
                boundary += W
                continue
        var c = src[boundary]
        if c == 61 and equal < 0:
            equal = boundary
        elif c == 38:
            if (pair_index + 1) > spans_len / 4:
                return -2
            dst_pos = decode_query_pair(
                src, pair_start, boundary, equal, dst, dst_pos, spans, pair_index
            )
            pair_index += 1
            pair_start = boundary + 1
            equal = -1
        boundary += 1

    if (pair_index + 1) > spans_len / 4:
        return -2
    _ = decode_query_pair(
        src, pair_start, n, equal, dst, dst_pos, spans, pair_index
    )
    pair_index += 1
    return pair_index
