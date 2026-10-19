#!/usr/bin/env python3
"""verify_xex.py - sanity-check a decrypted-or-not default.xex before codegen.

Verifies the XEX2 magic and reads the title ID / media ID / version out of
the execution-info header entry (0x40006), so a developer knows they extracted
the right file *before* kicking off a ~25-minute codegen run.

Usage:
    python3 verify_xex.py default.xex [--expect-title-id 0x45410937]

Exit 0 on PASS, 1 on FAIL. No game data is modified.
"""

import os
import struct
import sys

EXECUTION_INFO_KEY = 0x40006


def fail(msg):
    print(f"FAIL: {msg}")
    return 1


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("Usage: python3 verify_xex.py default.xex [--expect-title-id 0x45410937]")
        return 2
    path = argv[1]
    expect = 0x45410937
    if "--expect-title-id" in argv:
        expect = int(argv[argv.index("--expect-title-id") + 1], 0)

    if not os.path.isfile(path):
        return fail(f"not a file: {path}")
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(0x10000)
    if len(head) < 0x20:
        return fail("file too small to hold an XEX2 header")
    if head[0:4] != b"XEX2":
        return fail(f"bad magic: {head[0:4]!r} (expected b'XEX2')")
    print(f"magic: XEX2 OK  ({size} bytes)")

    count = struct.unpack(">I", head[0x14:0x18])[0]
    if count == 0 or count > 64:
        return fail(f"implausible header entry count: {count}")
    exec_off = None
    for i in range(count):
        key, val = struct.unpack(">II", head[0x18 + i * 8:0x20 + i * 8])
        if key == EXECUTION_INFO_KEY:
            exec_off = val
            break
    if exec_off is None:
        return fail("no execution-info header entry (0x40006) found")
    if exec_off + 16 > len(head):
        return fail("execution-info entry points outside the header")

    media_id, version, _base, title_id = struct.unpack(">IIII", head[exec_off:exec_off + 16])
    ver_str = f"{version >> 28}.{(version >> 24) & 0xF}.{(version >> 16) & 0xFF}.{version & 0xFFFF}"
    print(f"title_id:  0x{title_id:08X} (expected 0x{expect:08X})")
    print(f"media_id:  0x{media_id:08X}")
    print(f"version:   {ver_str}")
    if title_id != expect:
        return fail("title ID mismatch — wrong game or wrong file")

    print("PASS: this is the expected XEX")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
