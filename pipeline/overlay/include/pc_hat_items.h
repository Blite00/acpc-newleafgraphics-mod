#ifndef PC_HAT_ITEMS_H
#define PC_HAT_ITEMS_H
/* PC: New Leaf hats as items, in spare indices of the GC "dummy/diary" item category (see generate_nl_hat_items.py). */
#define ITM_HAT_START 0x2B10
#define PC_HAT_NUM 123
#define ITEM_IS_HAT(item) ((item) >= ITM_HAT_START && (item) < ITM_HAT_START + PC_HAT_NUM)
#define PC_HAT_INDEX(item) ((int)(item) - ITM_HAT_START)

extern const char pc_hat_item_name[][17];
extern const unsigned short pc_hat_item_price[];
extern unsigned short pc_hat_icon_pal[][16];
extern unsigned char pc_hat_icon_tex[][512];
/* the worn hat lives in two spare bytes of the player's save data */
#define PC_HAT_SLOT(priv) ((mActor_name_t*)&(priv)->unk_10A8[0])
/* a random hat (uses the game's fqrand, so call it where m_lib is in scope) */
#define PC_HAT_RANDOM() ((mActor_name_t)(ITM_HAT_START + (int)(fqrand() * (f32)PC_HAT_NUM) % PC_HAT_NUM))
#endif
