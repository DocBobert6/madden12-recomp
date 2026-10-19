#!/usr/bin/env python3
"""
extract_xex.py -- pull default.xex out of an Xbox 360 ISO (XGD2/XGD3), on-device.

Usage:
    python extract_xex.py "/sdcard/Download/Madden NFL 12 (World).iso"

Writes ./default.xex in the folder you run it from, plus ./extract_log.txt
with full diagnostics. Fully offline, stdlib only.

Method 1: scan for the GDFX volume, walk the directory-entry binary tree
(the way Xenia parses it), extract default.xex.
Method 2 (fallback): find the filename bytes directly, parse the 14-byte
directory entry in front of them, locate the enclosing volume, and carve the
file out. The XEX2 header check confirms the right bytes.

Key format fact (from Xenia's disc_image_device.cc): on Xbox 360 discs the
filesystem is GDFX and its volume descriptor ("MICROSOFT*XBOX*MEDIA") lives at
SECTOR 32 of the game partition -- i.e. 0x10000 bytes AFTER the partition
base. So: partition_base = magic_offset - 0x10000, and every sector number in
a directory entry is relative to partition_base, not to the magic.
"""

import os
import struct
import sys

SECTOR_SIZE = 2048
VOLUME_MAGIC = b"MICROSOFT*XBOX*MEDIA"  # 20 bytes
DESC_SECTOR = 32                    # GDFX volume descriptor lives here
DESC_OFF = DESC_SECTOR * SECTOR_SIZE  # = 0x10000; partition_base = magic - this
ATTR_DIRECTORY = 0x10
CHUNK = 8 * 1024 * 1024
NEEDLE = b"default.xex"


class Tee:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def log(self, msg):
        print(msg, flush=True)
        self.f.write(str(msg) + "\n")
        self.f.flush()


def find_volume_offsets(path, log):
    """Yield byte offsets where an XDVDFS volume header may start."""
    size = os.path.getsize(path)
    seen = set()
    with open(path, "rb") as f:
        carry = b""
        base = 0
        n = 0
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            buf = carry + chunk
            start = 0
            while True:
                i = buf.find(VOLUME_MAGIC, start)
                if i < 0:
                    break
                off = base - len(carry) + i
                if off not in seen:
                    seen.add(off)
                    yield off
                start = i + 1
            carry = buf[-(len(VOLUME_MAGIC) - 1):]
            base += len(chunk)
            n += 1
            if n % 16 == 0:
                log.log(f"  scanned {base / 1e9:.1f} / {size / 1e9:.1f} GB...")


def read_volume_header(f, base):
    f.seek(base)
    hdr = f.read(0x800)
    if len(hdr) < 0x800:
        return None
    if hdr[0:0x14] != VOLUME_MAGIC or hdr[0x7EC:0x800] != VOLUME_MAGIC:
        return None
    return struct.unpack_from("<II", hdr, 0x14)  # root sector, root size


def walk_table(f, fs_base, table_sector, table_size, depth=0):
    table_base = fs_base + table_sector * SECTOR_SIZE
    stack = [0]
    seen = set()
    while stack:
        rel = stack.pop()
        if rel in seen or rel + 14 > table_size:
            continue
        seen.add(rel)
        f.seek(table_base + rel)
        node = f.read(14)
        if len(node) < 14 or node in (b"\x00" * 14, b"\xff" * 14):
            continue
        left, right, sector, size, attr, name_len = struct.unpack("<HHIIBB",
                                                                  node)
        name = f.read(name_len).decode("cp1252", errors="replace")
        is_dir = bool(attr & ATTR_DIRECTORY)
        yield name, sector, size, is_dir
        for child in (left, right):
            if child not in (0, 0xFFFF):
                stack.append(child * 4)
        if is_dir and depth < 8:
            for sname, ssec, ssize, sdir in walk_table(f, fs_base, sector,
                                                      size, depth + 1):
                yield name + "/" + sname, ssec, ssize, sdir


def extract_at(f, data_off, fsize, out_path, log):
    f.seek(data_off)
    with open(out_path, "wb") as out:
        remaining = fsize
        while remaining:
            data = f.read(min(CHUNK, remaining))
            if not data:
                break
            out.write(data)
            remaining -= len(data)
    log.log(f"Wrote {out_path} ({fsize} bytes) from 0x{data_off:X}")


def carve_fallback(iso_path, out_path, log, bases):
    """Find the filename bytes, parse the dirent in front, carve the file."""
    log.log("Phase 3 (fallback): carving dirent from raw filename hits...")
    size = os.path.getsize(iso_path)
    hits = []
    with open(iso_path, "rb") as f:
        carry = b""
        base = 0
        n = 0
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            buf = (carry + chunk).lower()
            start = 0
            while True:
                i = buf.find(NEEDLE, start)
                if i < 0:
                    break
                hits.append(base - len(carry) + i)
                start = i + 1
                if len(hits) >= 10:
                    break
            if len(hits) >= 10:
                break
            carry = chunk[-32:]
            base += len(chunk)
            n += 1
            if n % 16 == 0:
                log.log(f"  searched {base / 1e9:.1f} / {size / 1e9:.1f} GB...")
    log.log(f"  filename hits: {[hex(h) for h in hits]}")
    if not hits:
        log.log("  filename bytes appear NOWHERE in the ISO.")
        return False

    with open(iso_path, "rb") as f:
        for h in hits:
            f.seek(h - 14)
            node = f.read(14)
            if len(node) < 14:
                continue
            left, right, sector, fsize, attr, nlen = struct.unpack("<HHIIBB",
                                                                   node)
            log.log(f"  hit 0x{h:X}: left={left} right={right} sector={sector} "
                    f"size={fsize} attr=0x{attr:02x} namelen={nlen}")
            if nlen != len(NEEDLE) or fsize == 0 or fsize > 2**31:
                log.log("    dirent failed validation, skipping")
                continue
            # nearest valid partition bases first, then absolute sector
            order = sorted([b for b in bases if b < h], reverse=True)
            for fb in order + [None]:
                data_off = (sector * SECTOR_SIZE if fb is None
                            else fb + sector * SECTOR_SIZE)
                where = "absolute" if fb is None else f"volume 0x{fb:X}"
                if data_off + 4 > size or data_off < 0:
                    continue
                f.seek(data_off)
                if f.read(4) == b"XEX2":
                    log.log(f"    XEX2 confirmed at 0x{data_off:X} ({where})")
                    extract_at(f, data_off, fsize, out_path, log)
                    log.log("RESULT: SUCCESS (via carve fallback)")
                    return True
                log.log(f"    no XEX2 at 0x{data_off:X} ({where})")
    return False


def main():
    if len(sys.argv) < 2:
        print('Usage: python extract_xex.py "/path/to/game.iso" [output.xex]')
        sys.exit(1)
    iso_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "default.xex"
    log = Tee("extract_log.txt")

    if not os.path.isfile(iso_path):
        log.log(f"Not found: {iso_path}")
        sys.exit(1)

    log.log(f"ISO: {iso_path} ({os.path.getsize(iso_path) / 1e9:.2f} GB)")

    log.log("Phase 1: scanning for GDFX volumes...")
    magics = list(find_volume_offsets(iso_path, log))
    log.log(f"Magic hits: {[hex(m) for m in magics]}")
    # GDFX descriptor sits at sector 32 of the partition: base = magic - 0x10000
    bases = sorted({m - DESC_OFF for m in magics if m >= DESC_OFF})
    log.log(f"Partition bases: {[hex(b) for b in bases]}")

    log.log("Phase 2: walking directory trees...")
    with open(iso_path, "rb") as f:
        for base in bases:
            vol = read_volume_header(f, base + DESC_OFF)
            if not vol:
                log.log(f"  [0x{base:X}] header invalid, skipping")
                continue
            root_sector, root_size = vol
            log.log(f"  [0x{base:X}] valid header: root sector={root_sector} "
                    f"size={root_size}")
            if root_size == 0 or root_size > 50 * 1024 * 1024:
                log.log("    suspicious root table size, skipping")
                continue
            f.seek(base + root_sector * SECTOR_SIZE)
            log.log(f"    root table first 64 bytes: "
                    f"{f.read(64).hex()}")
            names = []
            found = None
            for name, sector, size, is_dir in walk_table(f, base, root_sector,
                                                        root_size):
                if len(names) < 40:
                    names.append(("D " if is_dir else "F ") + name)
                if not is_dir and name.lower() == "default.xex":
                    found = (sector, size)
                    break
            log.log(f"    entries walked (first 40): {names}")
            if not found:
                log.log("    default.xex NOT in this volume")
                continue
            sector, size = found
            data_off = base + sector * SECTOR_SIZE
            f.seek(data_off)
            if f.read(4) != b"XEX2":
                log.log(f"    found entry but no XEX2 at 0x{data_off:X}, "
                        "skipping")
                continue
            log.log(f"    default.xex: sector={sector} size={size}, "
                    "extracting...")
            extract_at(f, data_off, size, out_path, log)
            log.log("RESULT: SUCCESS")
            return

    if carve_fallback(iso_path, out_path, log, bases):
        return
    log.log("RESULT: NOT FOUND -- send Pip this log.")


main()
