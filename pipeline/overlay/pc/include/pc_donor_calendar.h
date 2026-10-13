#ifndef PC_DONOR_CALENDAR_H
#define PC_DONOR_CALENDAR_H
/* Original ordinary-town ground palette mapping, inclusive date ceilings.
 * Foreground date table 0x931cc6 -> ground column of 0x9dd660. */
static inline int pc_donor_ground_season(int month, int day) {
    int md=month*100+day;
    return md<=224 ? 9 : md<=405 ? 0 : md<=705 ? 1 : md<=907 ? 2 :
           md<=915 ? 3 : md<=1016 ? 4 : md<=1101 ? 5 : md<=1117 ? 6 :
           md<=1125 ? 7 : md<=1210 ? 8 : 9;
}
#endif
