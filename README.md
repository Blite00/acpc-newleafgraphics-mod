# ACPC New Leaf Graphics Mod

A graphics mod for FlyingMeta's [ACGC-PC-Port](https://github.com/flyngmt/ACGC-PC-Port), the native PC port of Animal Crossing
(GameCube). It applies a small source overlay to the upstream project; the upstream source and game executable are not bundled.
It replaces the GameCube graphics with models and textures converted from **Animal Crossing: New Leaf**
(Nintendo 3DS): terrain, cliffs, water and sky, trees and flowers, houses, fences and town buildings, about 500
pieces of furniture, player heads and hats, tools, fish and bugs, interiors, and the dialogue, pocket, map, keyboard
and letter screens. It also brings the port's PC changes: keyboard and mouse controls, controller prompts and a
character creator.

The mod package contains the New Leaf changes, setup scripts, and tools. It does not contain the ACGC-PC-Port project,
its compiled game, or Nintendo game data. Get the base project from FlyingMeta's GitHub page and supply your own GameCube
and New Leaf game dumps. On first setup the mod applies its overlay to a local copy of the upstream source, converts assets
from your ROMs on your computer, and builds the New Leaf version locally.

## Requirements

- Windows 10 or 11, 64-bit
- ACGC-PC-Port 0.9.3 source from [FlyingMeta's pinned source page](https://github.com/flyngmt/ACGC-PC-Port/tree/4099d246c927e75b4fd342ca13f4ac4395c55af5). Choose **Code → Download ZIP**, extract it, and select the folder containing `pc`, `src` and `include` when setup asks.
- The original ACGC-PC-Port release executable and its `shaders` folder for GameCube-graphics fallback. Put `AnimalCrossing.exe` in this package's `gc` folder renamed `AnimalCrossing-GC.exe`, and copy `shaders` next to the mod launcher. Get them from [the upstream releases page](https://github.com/flyngmt/ACGC-PC-Port/releases).
- Your own **Animal Crossing (USA) GameCube disc image** (`GAFE01`, `.iso`, `.gcm` or `.ciso`), the same one
  ACGC-PC-Port needs
- Your own **decrypted Animal Crossing: New Leaf (USA) ROM** (see the formats below)
- A graphics card with **Vulkan** support (used once by the texture upscaler during setup) and OpenGL 3.3 for the game
- About 6 GB of free disk space during setup (about 1 GB afterwards)
- An internet connection during the first setup (to download the model reader source, see *How it works*)

- Gameplay preview
- https://www.youtube.com/watch?v=6_uEB3ACC3M

### Supported New Leaf ROM formats

The ROM must be **decrypted** (for example dumped with GodMode9 using a "decrypted" option, or decrypted afterwards).

| Format | Notes |
|---|---|
| `.3ds` / `.cci` | NCSD cartridge image |
| `.cxi` / `.app` | the game's main NCCH content |
| `.cia` | decrypted CIA (content 0 is used) |
| `.romfs` | a raw RomFS image (also needs `exefs/code.bin` next to it, see below) |
| a folder | an extracted RomFS (the folder with `Bg`, `Item`, `Strc` ...). Put the ExeFS `code.bin` (or `.code`) in an `exefs` folder next to it, or inside it |

The mod is made and tested with **Animal Crossing: New Leaf (USA)**, title ID `0004000000086300`. Setup checks the
files it reads against that release and warns if they differ. Other regions and Welcome amiibo are not tested.

## Install and first launch

1. Download the release zip and extract it to a folder of its own.
2. Put your GameCube disc image in the `rom` folder. Get the original port executable and shaders as described above if you want the GameCube-graphics fallback.
3. Run `AnimalCrossing.exe`.
4. A window asks how to set up the mod:
   - **Choose my New Leaf ROM file** or **Choose an extracted RomFS folder**: pick your decrypted New Leaf ROM.
   - **Play with the original GameCube graphics**: skips the mod (you can set it up later).
5. The browser opens FlyingMeta's pinned ACGC-PC-Port 0.9.3 page. Download and extract the source ZIP, then select its root folder (the one containing `pc`, `src` and `include`). The mod verifies the supported version and applies its overlay to a local working copy.
6. A console window shows the setup's progress. It takes roughly 15 to 30 minutes, depending on your PC:
   - it copies the needed files out of your two ROMs;
   - it exports the New Leaf models and textures and runs the converters;
   - it compiles the New Leaf build of the game with the bundled compiler;
   - it starts that build a few times for a second or two (a game window opens briefly) to record character and
     furniture poses, then finishes the conversion and rebuilds.
7. The game starts. Later launches start the New Leaf build straight away.

If the ROM is missing, encrypted or not New Leaf, or anything fails, setup shows the reason and the game starts with the
GameCube graphics instead. The full log is in `newleaf_cache\setup.log`.

- `Set up New Leaf graphics.cmd` (or `AnimalCrossing.exe --setup`) runs the setup again.
- `Play with GameCube graphics.cmd` (or `AnimalCrossing.exe --vanilla`) starts the GameCube-graphics build.
- To remove the converted data, delete the `newleaf_cache` folder.

Saves (`save/`), `settings.ini` and `keybindings.ini` are shared by both versions and use the normal ACGC-PC-Port
format. Your own Dolphin-style HD texture packs still go in `texture_pack/`.

## How it works

The release contains only the mod's source overlay (`pipeline/overlay`), not a copy of ACGC-PC-Port. Setup copies the source
folder you selected into a local working directory, verifies the pinned 0.9.3 version, and applies the overlay. The setup
(`pipeline/setup_mod.py`, run by the launcher on the bundled Python) then regenerates game assets:

1. **ROM reading** (`pipeline/acnl_rom.py`, `pipeline/gc_rom.py`): NCSD/NCCH/CIA/RomFS for New Leaf, ISO/GCM/CISO, Yaz0
   and RARC for the GameCube disc.
2. **Extraction**: the New Leaf files listed in `pipeline/tables/nl_raw_copies.json` and the GameCube files in
   `pipeline/tables/gc_files.json`.
3. **Model export**: `ExportModels`, `ExportTreeModels` and `DumpAnims` (`pipeline/scripts/*.cs`) export CGFX models
   and textures to JSON and PNG. They use the CGFX/PICA200 code of
   [Ohana3DS Rebirth](https://github.com/gdkchan/Ohana3DS-Rebirth). That project has no license file, so its code is
   not redistributed: setup downloads it at a fixed commit, checks every file's hash, and compiles the exporters with
   the C# compiler that ships with Windows.
4. **Generators** (`pipeline/scripts`, order in `pipeline/tables/steps.json`): about 85 Python scripts that fit the
   New Leaf models to the GameCube game and write C source and texture packs. A few textures are upscaled with
   Real-ESRGAN.
5. **Build**: the bundled w64devkit (i686 GCC + CMake) compiles the game, exactly like the developer build.
6. **Poses**: the first build records the GameCube skeleton poses some generators need; those parts are regenerated and
   the game is rebuilt.
7. **Install**: `newleaf_cache/game` gets `AnimalCrossing-NL.exe`, its shaders and texture packs. The launcher starts it
   with the game folder as working directory, so `rom/`, `save/` and the settings are shared.

Every table in `pipeline/tables` holds only paths, offsets and hashes. All generator outputs were checked against
the developer's own build: the generated sources and texture packs come out byte-identical, except a handful of
textures upscaled on the GPU and furniture poses captured a few frames apart (see `docs/VERIFICATION.md`).

## Building the release from source

Maintainers only; players use the release zip.

1. `tools/sync_from_dev.py` compares the patched development source with the pinned upstream checkout and writes only the mod overlay; generated game data is stripped.
2. `tools/make_tables.py` writes the tables from the verified provenance data.
3. Build the launcher: `launcher/build.cmd <w64devkit\bin>`.
4. `tools/build_release.py --out <folder> --zip` assembles the mod and runtimes
   (Python 3.12 with numpy, Pillow and SciPy; w64devkit; Real-ESRGAN ncnn Vulkan; SDL2 2.30.10).

To build the New Leaf game by hand instead of through the launcher:

```
runtime\python\python.exe -s mod\pipeline\setup_mod.py --root <game folder> --nl-rom <your New Leaf ROM> --base-source <extracted ACGC-PC-Port 0.9.3 folder> --keep-work
```

## Repository layout

| Path | What |
|---|---|
| `pipeline/overlay` | only the files added or changed by this mod, applied to the user's upstream ACGC-PC-Port 0.9.3 source |
| `pipeline/` | first-run setup: ROM readers, extraction, exporter build, build and install steps |
| `pipeline/scripts` | the generators and their own parameter tables |
| `pipeline/scripts_ours` | generators written for this release (scripted versions of earlier hand edits) |
| `pipeline/tables` | what to extract, export and run (paths, offsets and hashes only) |
| `launcher/` | `AnimalCrossing.exe`: the first-run prompt and launcher |
| `tools/` | maintainer tools: sync from the dev workspace, tables, release build, Nintendo-data scan |

## Legal

You must own the games and supply your own legally made dumps of them. This project contains no Nintendo graphics, models, text, sound, ROM or disc data, NES games, or data converted from
them, and it does not help you obtain any. The base ACGC-PC-Port source and compiled executable are obtained directly
from FlyingMeta by the player; the mod applies its overlay locally.
Animal Crossing is a trademark of Nintendo. This is a fan project, not affiliated with or endorsed by Nintendo.

## Credits

- [ACGC-PC-Port](https://github.com/flyngmt/ACGC-PC-Port) by FlyingMeta, the PC port this mod is built on
- [ac-decomp](https://github.com/ACreTeam/ac-decomp) by ACreTeam, the decompilation the port is built on
- [Ohana3DS Rebirth](https://github.com/gdkchan/Ohana3DS-Rebirth) by gdkchan, for CGFX and PICA200 texture reading
- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) by xinntao, for texture upscaling
- [w64devkit](https://github.com/skeeto/w64devkit), SDL2, Python, NumPy, SciPy and Pillow

See `LICENSE` and `THIRD_PARTY_NOTICES.md`.

## AI notice

AI tools (Claude) were used to write this mod's code, as with the upstream port.
