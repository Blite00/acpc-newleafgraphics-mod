#include "libforest/gbi_extensions.h"
/* The ground-cover pass no longer draws sidewalls. Keep this texture identity
 * for inactive legacy material routing; no skirt geometry is linked. */
unsigned char pc_foliage_wall_tex_dummy[64*64/2] ATTRIBUTE_ALIGN(32) = {0};
