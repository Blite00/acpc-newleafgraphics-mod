# Third-party software

The repository and release contain the mod overlay and setup tools, but not the ACGC-PC-Port project or its game executable.
Players obtain the pinned upstream source and original executable from FlyingMeta's page. Any upstream source keeps its own
licenses when the mod applies its overlay. The release bundles its own build tools and libraries, which keep their licenses:

| Component | Where | License | Source |
|---|---|---|---|
| ACGC-PC-Port 0.9.3 (FlyingMeta) | not bundled; selected by the player during setup | MIT (port layer), CC0 (decompilation); upstream terms remain with the upstream project | https://github.com/flyngmt/ACGC-PC-Port |
| ac-decomp (ACreTeam) | not bundled; part of player-obtained upstream source | CC0 1.0 | https://github.com/ACreTeam/ac-decomp |
| FixNES (FIX94) | not bundled; part of player-obtained upstream source | MIT | https://github.com/FIX94/fixNES |
| SDL2 2.30.10 | `SDL2.dll`, `runtime/SDL2-2.30.10` | zlib | https://github.com/libsdl-org/SDL |
| glad | not bundled; part of player-obtained upstream source | MIT / public domain | https://github.com/Dav1dde/glad |
| Python 3.12 | `runtime/python` | PSF License (`runtime/python/LICENSE.txt`) | https://www.python.org/ |
| NumPy | `runtime/python/Lib/site-packages/numpy` | BSD-3-Clause (license files in the package's `.dist-info`) | https://github.com/numpy/numpy |
| SciPy | `runtime/python/Lib/site-packages/scipy` | BSD-3-Clause (`.dist-info`) | https://github.com/scipy/scipy |
| Pillow | `runtime/python/Lib/site-packages/PIL` | MIT-CMU (`.dist-info`) | https://github.com/python-pillow/Pillow |
| w64devkit 2.1.0 (i686) | `runtime/w64devkit` | Unlicense; it bundles GCC and GNU Binutils (GPLv3, GCC Runtime Library Exception), GNU Make (GPLv3), mingw-w64 (ZPL and others), CMake (BSD-3-Clause), BusyBox (GPLv2) and more, see `runtime/w64devkit/COPYING` and the licenses inside | https://github.com/skeeto/w64devkit (build scripts and the exact upstream source versions) |
| Real-ESRGAN ncnn Vulkan + models | `runtime/realesrgan` | MIT (program), BSD-3-Clause (Real-ESRGAN models) | https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan, https://github.com/xinntao/Real-ESRGAN |

The compiler is only used by the setup to build the New Leaf version of the game on the player's computer; the game
does not link any GPL code. The GPL components are unmodified upstream builds; their complete corresponding source is
available from the upstream projects listed in w64devkit's documentation.

## Downloaded during setup (not included)

| Component | Use | Notes |
|---|---|---|
| Ohana3DS Rebirth (gdkchan), commit `c50635e8` | CGFX model and PICA200 texture reading for the exporters in `pipeline/scripts/ExportModels.cs`, `ExportTreeModels.cs`, `DumpAnims.cs` | Fetched from https://github.com/gdkchan/Ohana3DS-Rebirth, checked against known file hashes and compiled on the player's machine with the .NET Framework C# compiler that ships with Windows. The repository has no license file, so none of its code is redistributed here. |

## Not included

No Nintendo data of any kind: no graphics, models, text, sound, ROM or disc data, NES games, or anything converted from
them. The setup reads the player's own New Leaf ROM and GameCube disc and writes the converted data only to
`newleaf_cache/` on that computer.
