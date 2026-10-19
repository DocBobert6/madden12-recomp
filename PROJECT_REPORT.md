# madden12-recomp — Project Report

Technical report for developers: the static recompilation of Madden NFL 12
(Xbox 360) to portable C++, and everything needed to finish the Android side
of the port. This package is the *game* half only — the recompiled code, the
codegen configuration, the build glue, and the tooling.

Status as of 2026-10-19.

---

## 1. Target

| Field | Value |
|---|---|
| Game | Madden NFL 12 |
| Platform (original) | Xbox 360 |
| XEX title ID | `0x45410937` |
| `default.xex` size | 29,708,288 bytes (matches disc dirent exactly) |
| XEX header | `XEX2`, `module_flags=TITLE` |
| Encryption / compression | `NORMAL` (retail) / `BASIC` — standard for retail 360 discs; codegen decrypts internally with the public retail key |

EA's online services for this title are long dead; **offline play is the target.**

## 2. Approach: static recompilation

Modeled on **wwe-svr2011-pc** (Xbox 360 → PC + Android via static
recompilation). The **ReXGlue SDK** (`rexglue/rexglue-sdk`) translates Xbox 360
PowerPC code into portable C++ at build time — no JIT, no emulation at runtime.
This is the first known Madden/EA Sports title attempted through ReXGlue, so
expect game-specific unknowns.

- **ReXGlue SDK:** v0.10.0 (referenced via `REXSDK_DIR`, not vendored).
- Codegen produced **782 files (~411 MB) of C++** (781 written by the final
  run, plus codegen metadata).
- ReXGlue officially builds for `linux-aarch64`; **Android is NOT an official
  SDK target.** The Android side (ARM64 `.so` + JNI + launcher APK + native
  Vulkan renderer) is the developer's work, modeled on the reference
  project's `port/android` tree.
- **Known risk: Mali GPUs.** The reference project's own Mali support is
  alpha and its Vulkan renderer is experimental — budget driver work
  accordingly.

## 3. Build environment

| Tool | Version |
|---|---|
| ReXGlue SDK | 0.10.0 |
| Android NDK | 27.2.12479018 |
| Java | 21 |
| CMake | 3.28 |

Codegen's analysis pass alone takes ~25 minutes on a modest VM; allow on the
order of an hour for a full codegen run.

## 4. Pipeline, step by step

1. **Extract `default.xex`** from your own disc ISO. `extract_xex.py` is a
   pure-Python XDVDFS/GDFX extractor — 360 discs use GDFX and the volume
   descriptor sits at sector 32 of the game partition, i.e. 0x10000 bytes
   *after* the partition base. Get that offset wrong and every sector
   calculation is off by 64 KB. Then run `python3 verify_xex.py default.xex`
   to confirm the XEX2 magic and title ID `0x45410937` before codegen. (No
   separate decryption step: codegen decrypts retail XEXs internally with
   the public retail key, the same way Xenia does at load.)
2. **ReXGlue codegen** on the XEX → C++ (see §5 for the manual fix-up this
   required).
3. **Compile the native code** to an ARM64 shared library with the NDK,
   using `CMakeLists.txt` / `CMakePresets.json` in this repo.

## 5. Codegen findings: the 34 missed branch targets

The ReXGlue analysis pass failed validation with **34 unresolved calls** —
branch targets the function scanner missed (pattern: `b <addr>` from inside a
function to an address the scanner did not attribute to any function; see
`evidence/codegen_unresolved_functions.txt`). The fix is manual entries in the manifest's
`[entrypoint.functions]` section:

```toml
[entrypoint.functions."0x8242D4F8"]
# ... (34 entries total — see madden12_manifest.toml)
```

**Gotcha (cost one full ~25 min codegen run):** these entries must be under
`[entrypoint.functions]`. Placed in the wrong manifest section, they are
silently ignored and codegen reports the same 34 errors again. If you hit
"target not in any function" errors, check the section name before rerunning.

The final codegen run completed cleanly (`evidence/codegen_final_run.log`).

## 6. Recompilation output

- `generated/` — ~782 C++ files (~411 MB): `madden12_funcs.*.h` and
  `madden12_recomp.*.cpp` (the translated game code),
  `codegen.partition.json`, `rexglue.cmake` (the SDK boilerplate the build
  includes).
- The build compiles this against the ReXGlue runtime with the `xenos` GPU
  plugin (`rexglue_setup_target(madden12 GPU_PLUGINS xenos)` in
  `CMakeLists.txt`).

## 7. What's in this repo — and what's deliberately not

Included — the complete game-side package:
`generated/` (the recompilation output), `madden12_manifest.toml` (with the
34 manual function entries), `CMakeLists.txt` + `CMakePresets.json` (build
glue against `REXSDK_DIR`), `extract_xex.py` (XEX extractor for your own
disc), `verify_xex.py` (pre-codegen sanity check: XEX2 magic + title ID;
no separate decrypt step — codegen handles retail decryption internally),
`evidence/` (the 34 missed targets + the final successful codegen
log), `VERSION.txt` (toolchain pins), this report, and the developer
`README.md`.

**Not included, by design:**
- Any game files, assets, or the original `default.xex` — extract from your
  own legally owned copy (the "bring your own disc" line; `.gitignore`
  enforces it).
- The Android side itself: JNI bridge, launcher app, touch controls, APK
  packaging — that is the work this package exists to enable.

## 8. Reproduction checklist

- [ ] Own a legal copy of Madden NFL 12 (Xbox 360); extract `default.xex`
      with `extract_xex.py` and confirm it with `python3 verify_xex.py
      default.xex` (XEX2 magic, title ID `0x45410937`).
- [ ] Install the toolchain (§3); set `REXSDK_DIR` to a ReXGlue SDK v0.10.0
      source tree.
- [ ] Run ReXGlue codegen with `madden12_manifest.toml` (34 manual function
      entries included, §5) — or start from the shipped `generated/` output.
- [ ] Configure with `CMakePresets.json`; build the ARM64 native library.
- [ ] Write the Android side: JNI entry point, launcher with
      install-from-own-copy flow, input/touch controls, native Vulkan
      renderer. The reference project's `port/android` tree is the model.

## 9. Notes for the Android-side developer

- The game renders through the `xenos` GPU plugin; the renderer is the
  largest piece of custom Android work.
- Mali GPUs: the reference project's Mali support is alpha — verify the
  Vulkan path on Mali hardware early.
- No game-specific patches were needed for the recompilation (the reference
  project carries SDK patches for its title; this one needed none).
- The shared tooling (extractor, manifest pattern, build glue) should
  transfer to other Xbox 360 titles.
