# How the release was verified

The first-run setup was run on a clean folder with the developer's own ROMs (New Leaf USA `0004000000086300`,
GameCube `GAFE01`) and its output compared with the developer workspace the mod was made in.

## Generated source and texture packs

| What | Result |
|---|---|
| Generated C sources (630 files: terrain, trees, foliage, bridges, docks, houses, fences, signs, tools, fish, bugs, characters, hats, ~500 furniture items, NL UI, lighting) | 601 byte-identical |
| Characters (`pc_chr_smooth*`, `pc_player_clean`, heads, creator heads, hats) | identical (the NPC and player poses captured by the setup match the developer's dumps exactly) |
| Gyroids (127) and aquariums/bug cases/UFO (47) | mostly identical; 25 gyroids differ by 1-2 vertex units (one by 12) because their idle animation is captured a few frames apart |
| `pc_mailbox_hd`, `pc_gyroid_hd`, `gc_villager_houses`, `3ds_mailbox` | differ: the developer used 105 hand-picked AI redraws of GameCube textures (`upscale_override`), which are not shipped; the setup uses the Real-ESRGAN result instead |
| Texture packs `3ds_interiors` (444), `gc_shirts_hd` (255), `nl_faces` (301), `gc_station_hd` (74), `shop_signs` (15), `3ds_holes`, `3ds_apple_trial` | byte-identical |
| Shader `default.frag` (New Leaf character lighting curves filled in by the setup) | byte-identical |

Steps that were hand edits in the workspace are scripted in `pipeline/scripts_ours` and reproduce the developer's files
exactly: museum insect-room textures, SOLD OUT sign and shop floors, TV programmes, the ivory piano, the character
lighting curves, the field lighting tables, Rover's creator lines and the crisp shirt pass.

Every Ohana export folder the generators read (1,381) was re-exported from the ROM and compared file by file with the
workspace copy; every raw ROM copy (2,598) and GameCube extract (forest_1st/2nd.arc members, room wallpaper/carpet
slices, shirt textures, foresta.rel) was checked byte for byte.

## In game

The same scenes were captured with the developer's `AnimalCrossing.exe` and with `newleaf_cache/game/AnimalCrossing-NL.exe`
built by the setup (`--tree-test-town`, fixed date/time/position, `--capture-after 300`): town in summer, houses at dusk,
town in snow at night, Nook's Cranny and the museum insect room. The graphics match; the remaining pixel differences come
from things the test town randomises (falling snow, the player's random clothes/hair, the shop's stock).

## Not tested here

- Downloading and compiling Ohana3DS Rebirth on a player's machine (`pipeline/build_exporters.py`): the test used the
  exporters already built in the workspace (`ACPC_EXPORTERS_DIR`). The patch to `CGFX.cs` was checked by hash.
- Machines without a Vulkan GPU (Real-ESRGAN fails; setup stops with a message and the GameCube build runs).
- New Leaf regions other than USA, and Welcome amiibo.
