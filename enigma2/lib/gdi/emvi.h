/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __emvi_h
#define __emvi_h

#include <lib/gdi/gpixmap.h>

/* Scrie un gPixmap de 1920x1080 pe 32 de biti ca ecran de pornire MPEG-2 (.mvi),
   acela pe care il arata showiframe inainte sa porneasca interfata.
   "quantiser_scale_code" merge de la 1 la 31: mai mic inseamna poza mai buna si fisier mai mare.
   Implicit e 4, ca in galeria retetei si ca in PLAN.md (P6): da fisiere mai mici, iar pe receptor
   inca nu stim daca showiframe are vreo limita de marime. Ecranele facute cu ffmpeg folosesc 2.
   Intoarce 0 la bine si un numar negativ la rau. */
int saveMVI(const char *filename, gPixmap *pixmap, int quantiser_scale_code = 4);

#endif
