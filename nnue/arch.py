"""File format and integer evaluation for ChessSI networks.

Shared by the trainer, ``check_inference.py``, and the night-0 tests. No torch.

Formats (little-endian), also parsed by ``src/nnue.cpp``:

CSNN  net12 and earlier. Magic "CSNN", hidden int32, ft int16[768][H], bias int16[H],
      out int16[2H], out bias int32.
CSKB  net13 king buckets, folded at export. Magic "CSKB", hidden int32, buckets int32
      (8 or 16), ft int16[buckets][768][H], then the same bias and output as CSNN.
      A CSNN file does not parse as CSKB.

Quantization, the same constants as ``src/nnue.cpp``: QA = 255, QB = 64, SCALE = 400.
King-bucket rows are ``W0[feature] + U[bucket, feature]`` folded into the dense table.
U = 0 leaves every bucket equal to W0, so step 0 matches the CSNN file the weights
were copied from.
"""

import struct

import numpy as np

SCALE = 400
QA, QB = 255, 64
PIECES = {"P": 0, "N": 1, "B": 2, "R": 3, "Q": 4, "K": 5}
PAD = 768


def features(board_field):
    """Feature indices from White's and Black's perspective for one FEN board field."""
    white, black = [], []
    rank = 7
    file = 0
    for ch in board_field:
        if ch == "/":
            rank -= 1
            file = 0
        elif ch.isdigit():
            file += int(ch)
        else:
            sq = rank * 8 + file
            is_white = ch.isupper()
            pt = PIECES[ch.upper()]
            white.append((0 if is_white else 384) + pt * 64 + sq)
            black.append((0 if not is_white else 384) + pt * 64 + (sq ^ 56))
            file += 1
    return white, black


def king_squares(board_field):
    """Real-board squares (a1 = 0) of the white and black kings."""
    wk = bk = None
    rank, file = 7, 0
    for ch in board_field:
        if ch == "/":
            rank -= 1
            file = 0
        elif ch.isdigit():
            file += int(ch)
        else:
            sq = rank * 8 + file
            if ch == "K":
                wk = sq
            elif ch == "k":
                bk = sq
            file += 1
    if wk is None or bk is None:
        raise ValueError(f"missing king in {board_field}")
    return wk, bk


def king_bucket(sq, n_buckets):
    """Friendly-king bucket for net13. One layout, from the research note in PR #69.

    Square a1 = 0. If the king's file is a-d, mirror the square with ``^ 7`` so it
    stands on files e-h. The file id is then 0..3 for e..h. Rank is the real rank
    (not flipped vertically): Black's bucket uses Black's king on the real board.

        K8:  file_id + 4 * (1 if rank >= 5 else 0)     # ranks 1-4 vs 5-8
        K16: file_id + 4 * (rank_index // 2)           # pairs 1-2, 3-4, 5-6, 7-8

    ``src/nnue.h`` ``NNUE::king_bucket`` is this function. Keep them the same.
    """
    sq = int(sq)
    if n_buckets not in (8, 16):
        raise ValueError(n_buckets)
    if (sq & 7) < 4:
        sq ^= 7
    file_id = (sq & 7) - 4
    rank = sq >> 3
    if n_buckets == 8:
        return file_id + 4 * (1 if rank >= 4 else 0)
    return file_id + 4 * (rank >> 1)


def tdiv(a, b):
    """Integer division truncating toward zero, as in C++."""
    q = abs(int(a)) // abs(int(b))
    return q if (int(a) >= 0) == (int(b) > 0) else -q


def _i16_bytes(array):
    return np.ascontiguousarray(array, dtype="<i2").tobytes()


def pack_csnn(hidden, ft_w, ft_b, out_w, out_b):
    """ft_w int16[768, H], ft_b int16[H], out_w int16[2H], out_b int."""
    ft_w = np.ascontiguousarray(ft_w, dtype=np.int16)
    if ft_w.shape != (PAD, hidden):
        raise ValueError(ft_w.shape)
    return b"".join([
        b"CSNN",
        struct.pack("<i", int(hidden)),
        _i16_bytes(ft_w),
        _i16_bytes(ft_b),
        _i16_bytes(out_w),
        struct.pack("<i", int(out_b)),
    ])


def pack_cskb(hidden, buckets, ft_w, ft_b, out_w, out_b):
    """ft_w int16[buckets, 768, H], the dense table after folding W0 + U."""
    ft_w = np.ascontiguousarray(ft_w, dtype=np.int16)
    if buckets not in (8, 16) or ft_w.shape != (buckets, PAD, hidden):
        raise ValueError((buckets, ft_w.shape))
    return b"".join([
        b"CSKB",
        struct.pack("<i", int(hidden)),
        struct.pack("<i", int(buckets)),
        _i16_bytes(ft_w),
        _i16_bytes(ft_b),
        _i16_bytes(out_w),
        struct.pack("<i", int(out_b)),
    ])


def parse_net(data):
    """Bytes -> dict of numpy arrays. Raises ValueError on a short or unknown file."""
    if len(data) < 8:
        raise ValueError("network file is too short")
    magic, pos = data[:4], 4
    (hidden,) = struct.unpack_from("<i", data, pos)
    pos += 4
    if hidden <= 0 or hidden > 4096 or hidden % 32 != 0:
        raise ValueError(f"bad hidden size {hidden}")

    def take(count, dtype):
        nonlocal pos
        width = np.dtype(dtype).itemsize
        nbytes = count * width
        if len(data) - pos < nbytes:
            raise ValueError("network file ended early")
        arr = np.frombuffer(data, dtype=dtype, count=count, offset=pos).copy()
        pos += nbytes
        return arr

    buckets = 1
    if magic == b"CSNN":
        ft = take(PAD * hidden, "<i2").reshape(1, PAD, hidden)
    elif magic == b"CSKB":
        (buckets,) = struct.unpack_from("<i", data, pos)
        pos += 4
        if buckets not in (8, 16):
            raise ValueError(f"bad bucket count {buckets}")
        ft = take(buckets * PAD * hidden, "<i2").reshape(buckets, PAD, hidden)
    else:
        raise ValueError(f"unknown network magic {magic!r}")

    ft_b = take(hidden, "<i2")
    out_w = take(2 * hidden, "<i2")
    (out_b,) = struct.unpack_from("<i", data, pos)
    pos += 4
    if np.any((out_w < -128) | (out_w > 128)):
        raise ValueError("output weight does not fit the int16 v*w path")

    return {
        "magic": magic,
        "hidden": hidden,
        "buckets": buckets,
        "ft_w": ft,
        "ft_b": ft_b,
        "out_w": out_w,
        "out_b": int(out_b),
    }


def _accumulate(ft, bucket, feats, bias):
    """int16 accumulator half: bias plus the feature rows, wrapped as C++ int16 adds."""
    acc = bias.astype(np.int32).copy()
    if len(feats):
        acc += ft[bucket, feats].sum(axis=0, dtype=np.int32)
    return acc.astype(np.int16).astype(np.int64)


def _screlu_dot(acc, out_w):
    """Sum of v * int16(v * w) over chunks of 32, matching ``NNUE::evaluate``."""
    total = 0
    for c in range(0, len(acc), 32):
        chunk = 0
        for i in range(c, c + 32):
            v = int(acc[i])
            if v < 0:
                v = 0
            elif v > QA:
                v = QA
            vw = np.int16(v * int(out_w[i]))  # low 16 bits, in range by the loader check
            chunk += int(vw) * v
        total += chunk
    return total


def evaluate(data, fen):
    """Centipawns for the side to move, the same integer steps as ``src/nnue.cpp``."""
    if isinstance(data, (bytes, bytearray)):
        net = parse_net(data)
    else:
        net = data
    parts = fen.split()
    board, stm = parts[0], parts[1]
    white, black = features(board)
    if net["buckets"] > 1:
        wk, bk = king_squares(board)
        wb, bb = king_bucket(wk, net["buckets"]), king_bucket(bk, net["buckets"])
    else:
        wb = bb = 0
    if stm == "w":
        us, them, ub, tb = white, black, wb, bb
    elif stm == "b":
        us, them, ub, tb = black, white, bb, wb
    else:
        raise ValueError(f"bad side to move in {fen}")
    stm_acc = _accumulate(net["ft_w"], ub, us, net["ft_b"])
    nstm_acc = _accumulate(net["ft_w"], tb, them, net["ft_b"])
    acc = np.concatenate([stm_acc, nstm_acc])
    total = tdiv(_screlu_dot(acc, net["out_w"]), QA) + net["out_b"]
    return tdiv(total * SCALE, QA * QB)


def load_csnn(path):
    """A CSNN file as int arrays. The night-0 init source (net12)."""
    with open(path, "rb") as f:
        data = f.read()
    net = parse_net(data)
    if net["magic"] != b"CSNN":
        raise ValueError(f"{path} is {net['magic']!r}, not a CSNN network")
    return net


def requant_matches(q, scale):
    """True when float32(q / scale) rounds back to q. Step 0 depends on this for net12."""
    f32 = q.astype(np.float32) / np.float32(scale)
    back = np.rint(f32 * np.float32(scale)).astype(np.int32)
    return np.array_equal(back, q.astype(np.int32))
