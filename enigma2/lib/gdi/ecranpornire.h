/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __ecranpornire_h
#define __ecranpornire_h

/*
 * Ecranul de pornire (/usr/share/backdrop.mvi) facut din poza utilizatorului.
 *
 * Doua functii, dupa forma lui savePNG din epng.h:
 *  - pregatesteEcranPornire: poza (JPG sau PNG) -> suprafata 1920x1080, umpluta si decupata simetric;
 *    cu un rand_de_jos dat, si fasia de jos intunecata cat trebuie cu randul scris peste ea (gol = poza
 *    fara niciun text, cum le face imaginea acum);
 *  - faEcranPornire: aceeasi suprafata, codata ca un cadru I MPEG-2 si scrisa in fisierul cerut. Fara rand_de_jos
 *    elibereaza GIL-ul cat tine conversia (chemata din Python pe un fir separat, nu tine firul enigma2).
 *
 * Fisierul care merge (backdrop.mvi) NU se atinge aici: se scrie fisierul cerut, iar mutarea peste cel
 * vechi o face Components/HdsEcranePornire.aplica(), care scrie alaturi, face fsync si muta cu os.replace.
 *
 * Semnatura de pornire (randul cu siturile si versiunea imaginii, peste poza pusa de showiframe):
 *  - deseneazaSemnaturaPornire: o capsula intunecata cu textul, jos, centrata, desenata pe OSD (gMainDC) la
 *    masurile unui ecran de 1920x1080, micsorata pe un OSD mai mic (720x576 inainte de skin). Intoarce 0, -1
 *    (text gol sau OSD lipsa) sau -6 (niciun font nu scrie textul);
 *  - ascundeSemnaturaPornire: cere desktopului redesenarea locului ei (la primul desen al interfetei).
 *
 * Caile si textul sunt std::string, nu const char *: un str Python cu octeti care nu sunt UTF-8 (o poza
 * de pe stick, cu nume Latin-1) ajunge intreg prin std::string, pe cand un const char * arunca TypeError
 * (masurat).
 *
 * Codurile intoarse (0 = gata). Textele pentru om se scriu in Python, ca sa fie traduse:
 *   -1 poza nu se poate deschide sau citi
 *   -2 poza nu e nici JPEG, nici PNG
 *   -3 poza are prea multi pixeli (vezi ECRAN_PORNIRE_MAXIM_PIXELI)
 *   -4 poza nu s-a putut decoda (fisier stricat)
 *   -5 pastrat, nefolosit (memoria nu se poate verifica: enigma2 nu are exceptii)
 *   -6 nu s-a putut scrie randul de jos (fontul nu e inregistrat)
 *   -7 codorul MPEG-2 (lib/gdi/mpeg2intra.h) nu a putut coda poza
 *   -8 fisierul cerut nu s-a putut scrie
 *   -9 poza are prea multe detalii: nici la cuantizarea 31 fisierul nu incape sub prag (sters)
 */

#include <string>

#include <lib/gdi/gpixmap.h>

/* Cat de mare poate fi poza aleasa. Peste atat nici nu se incearca decodarea: enigma2 se compileaza cu
   -fno-exceptions, deci o alocare cazuta nu se poate prinde, ci opreste receptorul. La 32 de biti pe
   pixel, 24 de milioane de pixeli inseamna 96 MB, iar poza unui telefon obisnuit are 12 milioane. */
#define ECRAN_PORNIRE_MAXIM_PIXELI 24000000

SWIG_VOID(int) pregatesteEcranPornire(ePtr<gPixmap> &SWIG_OUTPUT, const std::string &poza, const std::string &rand_de_jos);

int faEcranPornire(const std::string &poza, const std::string &fisier, const std::string &rand_de_jos, int cod_cuantizare = 4);

int deseneazaSemnaturaPornire(const std::string &text);
void ascundeSemnaturaPornire();

#endif
