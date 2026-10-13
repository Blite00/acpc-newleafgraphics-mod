#ifndef PC_TREE_WORLD_H
#define PC_TREE_WORLD_H
#include "PR/gbi.h"
extern int g_pc_tree_world;
extern int g_pc_cedar_world;
extern int g_pc_tree_test_town;
#define PC_TREE_ROOT_INSET 4.0f
/* Idle leaf/trunk, shake, cut-left/right leaf, cut-left/right trunk, mature stump. */
Gfx* pc_tree_world_mesh(int part);
Gfx* pc_cedar_world_mesh(int part);
Gfx* pc_tree_world_mesh_style(int part, int hardwood);
/* Original saplings/young trees/pines/palms/stumps. family 0 hardwood, 1 cedar,
 * 2 palm; native stage 1..5; parts as above plus 7 stump, 8 withered sapling. */
extern int g_pc_young_plants;
Gfx* pc_young_plant_mesh(int family, int stage, int part, int hardwood);
void pc_tree_world_set_light(const unsigned char* ambient,const unsigned char* sun,
    const unsigned char* moon,float sx,float sy,float sz,float mx,float my,float mz);
void pc_tree_world_set_donor_light(int enabled,const unsigned char* diffuse,
    const unsigned char* specular,const unsigned char* sky,const unsigned char* ground);
#endif
