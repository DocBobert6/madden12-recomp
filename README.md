# madden12-recomp

Madden NFL 12 (Xbox 360), statically recompiled to portable C++ with the
[ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) (v0.10.0) — no JIT, no
emulation at runtime. This package is the *game* half of a future Android port:
the recompiled code plus everything a developer needs to finish the Android
side (ARM64 `.so` + JNI + launcher APK + Vulkan renderer), modeled on
[wwe-svr2011-pc](https://github.com/KaikoClanworth1/wwe-svr2011-pc)'s
`port/android` tree. This is the first known Madden/EA Sports title attempted
through ReXGlue.

Full technical report: [`PROJECT_REPORT.md`](PROJECT_REPORT.md).

## Contents

| Path | What it is |
|---|---|
| `generated/` | The recompilation output: ~782 C++ files (~411 MB), from the final successful codegen run. |
| `madden12_manifest.toml` | ReXGlue codegen manifest — includes 34 manually registered function entries the scanner missed (see report §5). |
| `CMakeLists.txt`, `CMakePresets.json` | Build glue: compiles the recompiled code against the ReXGlue runtime (`REXSDK_DIR` must point at SDK v0.10.0 source). |
| `extract_xex.py` | Pure-Python XDVDFS/GDFX extractor — pulls `default.xex` from your own disc ISO (file managers can't parse the XGD game partition). |
| `verify_xex.py` | Sanity-checks the extracted XEX (XEX2 magic + title ID `0x45410937`) before you spend ~25 minutes on codegen. |
| `evidence/` | `codegen_unresolved_functions.txt` (the 34 missed branch targets) and `codegen_final_run.log` (the final successful run). |
| `VERSION.txt` | Package version and toolchain pins. |
| `PROJECT_REPORT.md` | The full project report: target, toolchain, pipeline, codegen findings, reproduction checklist. |

## What you need (not in this repo)

1. **Your own legally owned copy of Madden NFL 12 (Xbox 360).** Extract
   `default.xex` with `extract_xex.py`, then run
   `python3 verify_xex.py default.xex` to confirm the XEX2 magic and title ID
   `0x45410937`. No separate decryption step is needed: ReXGlue codegen
   decrypts retail XEXs internally with the public retail key, the same way
   Xenia does at load.
2. **ReXGlue SDK v0.10.0** — referenced, not vendored. Set `REXSDK_DIR` to
   its source tree. (Android is not an official SDK target; the Android half
   is custom work.)
3. **Build tools:** Android NDK 27.2.12479018, Java 21, CMake 3.28, Clang.

## Reproduce

1. Run ReXGlue codegen against your `default.xex` with `madden12_manifest.toml`
   — or start from the shipped `generated/` output (regenerate if your dump
   differs; see the manifest gotcha in report §5).
2. Configure with `CMakePresets.json` and build the ARM64 native library.
3. Write the Android side around it: JNI bridge, launcher with
   install-from-own-copy flow, touch controls, and the native Vulkan renderer
   (`xenos` GPU plugin). The reference project's `port/android` tree is the
   model; note its Mali GPU support is alpha — budget driver work accordingly.

## Ground rules

- No game data, keys, or the original XEX in this repo or its issues — ever
  (`.gitignore` enforces it).
- EA's online services for this title are long dead; offline play is the target.
