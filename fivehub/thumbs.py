"""Tiny dependency-free PNG writing, used for placeholder thumbnails when a
viewport capture is unavailable (headless publishes, tests, the demo)."""

import struct
import zlib


def _chunk(tag, data):
    payload = tag + data
    return struct.pack(">I", len(data)) + payload + struct.pack(
        ">I", zlib.crc32(payload) & 0xFFFFFFFF
    )


def write_placeholder_png(path, size=64, cell=8):
    """Write a black & white checkerboard PNG (fits the hub aesthetic)."""
    rows = []
    for y in range(size):
        row = bytearray(b"\x00")  # no filter
        for x in range(size):
            value = 255 if ((x // cell) + (y // cell)) % 2 == 0 else 0
            row.extend((value, value, value))
        rows.append(bytes(row))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + _chunk(b"IEND", b"")
    )
    with open(path, "wb") as handle:
        handle.write(data)
    return path
