/* Dedicated high-detail seasonal foliage; ordinary terrain keeps its atlas. */
#include <string.h>
#include "pc_foliage_data.c_inc"
extern int pc_foliage_calendar_season(void);

const unsigned char* pc_foliage_surface(int kind,int width,int height,const unsigned char* native_rgba) {
    static unsigned char pixels[1024*256*4];
    int season=pc_foliage_calendar_season();
    const unsigned char* foliage;
    int row,x;
    if (season<0 || season>=23) season=0;
    foliage=kind==7 ? pc_foliage_wall_seasons[season] : pc_foliage_seasons[season];
    memset(pixels,0,sizeof(pixels));
    for (row=0;row<256;row++) {
        /* A true256-square leaf cell at x384; no runtime enlargement. */
        memcpy(pixels+(row*1024+384)*4,foliage+row*256*4,256*4);
        for (x=0;x<128;x++) {
            int sx=x*width/128,sy=row*height/256;
            unsigned char* p=pixels+(row*1024+x)*4;
            p[0]=p[1]=p[2]=255;
            p[3]=kind==7 ? 255 : native_rgba[(sy*width+sx)*4+3];
        }
    }
    return pixels;
}
