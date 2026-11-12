/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_gdi_hdsanimatie_h
#define __lib_gdi_hdsanimatie_h

/*
 * Animatiile ferestrelor desenate de enigma2 (HDSatelit 0.7.4), pe receptoarele a caror placa video nu le face singura
 * (fara /proc/stb/fb/animation_*: SF8008, Viper 4K si celelalte HiSilicon; unde fisierele exista le face placa, ca in
 * OE-Alliance, main/enigma.cpp).
 *
 * Cum: desktopul (lib/gui/ewidgetdesktop.cpp) compune in RAM doua imagini de marimea ecranului: „inainte” (ce se vedea in
 * zona ferestrei chiar inainte sa se deschida sau sa se inchida) si „dupa” (aceeasi zona dupa schimbare). Operatia
 * gOpcode::hdsAnimatie, pe firul gRC (in ordine cu restul desenului), trece de la una la alta in durata aleasa: fiecare cadru
 * se scrie direct in pagina vazuta, iar la sfarsit zona primeste exact imaginea „dupa”. Din memoria video nu se citeste
 * nimic (pe SF8008 citirea ei e de ~10 ori mai lenta decat scrierea: 8 MB in ~90 ms).
 *
 * Felurile: 1 aparitie treptata (amestec), 2 alunecare scurta (fereastra noua urca de la o distanta mica, cea care se
 * inchide coboara), 3 marire usoara (fereastra noua creste de la 92%, cea care se inchide scade). Toate cu amestec si
 * curba lina (incetinire spre final, cubica).
 *
 * Timpul e masurat, nu numarat in cadre: un receptor lent face mai putine cadre in aceeasi durata; daca primul cadru
 * singur ia peste 60% din durata, animatia sare direct la imaginea finala (nimic mai lent decat fara animatie).
 * O tasta apasata (main/enigma.cpp, deliverKey) sau o animatie noua opresc animatia in curs: zona primeste imediat
 * imaginea finala.
 *
 * Pixelii: 32 de biti, octetul de sus = opacitatea (0 = transparent, peste imagine). Amestecul a doi pixeli din care
 * unul e transparent pastreaza culoarea celuilalt si schimba numai opacitatea (altfel marginea s-ar intuneca la mijlocul
 * trecerii).
 */

#include <stdint.h>

struct gSurface;

struct gHdsAnimatie
{
	enum { oprita = 0, treptata = 1, alunecare = 2, marire = 3 };
	int fel;
	int durata_ms;
	int inchidere;		/* 1 = fereastra pleaca (alunecarea coboara, marirea scade) */
	int x, y, w, h;		/* zona, in coordonatele ecranului (aceleasi in toate cele trei suprafete) */
	struct gPixmap *inainte, *dupa;	/* referinte tinute de gPainter::hdsAnimatie, eliberate in gDC::exec */
};

/* curba: t din [0, durata] -> 0..256, cubica cu incetinire spre final */
int hdsAnimatieCurba(long t_us, long durata_us);

/* amestecul a doi pixeli (f = 0: a, f = 256: b), cu paza transparentei de mai sus */
uint32_t hdsAnimatieAmesteca(uint32_t a, uint32_t b, unsigned f);

/*
 * Un cadru: scrie zona w x h in dst (pas_dst pixeli pe rand) din inainte/dupa (pas_src pixeli pe rand; pointerii arata
 * deja coltul zonei in fiecare suprafata), la progresul p (0..256, deja trecut prin curba). tabel: loc pentru 2 * w + h
 * intregi de 32 de biti (marirea si un rand de lucru). Functie pura, probata pe PC si sub qemu-arm cu NEON
 * (teste/test_animatii_ferestre_an_074.py).
 */
void hdsAnimatieCadru(uint32_t *dst, int pas_dst, const uint32_t *inainte, const uint32_t *dupa, int pas_src, int w, int h,
	int fel, int inchidere, int p, int *tabel);

/*
 * Animatia intreaga, pe firul gRC: cadre pana la durata (sau oprire), apoi imaginea finala. arata(ctx) dupa fiecare cadru
 * (gDC: flush, ca pagina sa ajunga pe ecran unde e nevoie, de pilda in emulatorul de pe PC). Intoarce numarul de cadre.
 */
int hdsAnimatieRuleaza(gSurface *ecran, const gSurface *inainte, const gSurface *dupa, const gHdsAnimatie &a,
	void (*arata)(void *), void *ctx);

/* oprirea animatiei in curs (orice fir): zona primeste imediat imaginea finala */
void hdsAnimatieOpreste();

#endif
