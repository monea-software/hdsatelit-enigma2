/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_gdi_desennetezit_h
#define __lib_gdi_desennetezit_h

/*
 * Desen netezit (cu margini netede, fara trepte) pe suprafete de 32 de biti.
 *
 * Forme: linie groasa cu capete rotunde, arc cu grosime (capete drepte sau rotunde), inel, cerc plin,
 * poligon plin. Fiecare pixel primeste o acoperire intre 0 si 1 socotita din distanta semnata de la centrul
 * pixelului pana la marginea formei (acoperire = 0,5 - distanta, taiata la 0..1), apoi se amesteca o singura
 * data cu ce era dedesubt ("over", alfa drept, pe toate cele patru canale, fara gamma, ca in ecranpornire.cpp).
 *
 * Conventii (aceleasi ca la fillRect):
 *  - pixelul i acopera [i, i+1], deci centrul lui este i + 0,5; fillCircle(5, 5, 5) umple exact 10x10;
 *  - culoarea e un gRGB in care octetul a este TRANSPARENTA (0 = opac, 255 = invizibil), ca in skin
 *    (#80rrggbb = pe jumatate transparent); in suprafata octetul de sus este opacitatea (gpixmap.cpp:222);
 *  - unghiurile sunt in grade, 0 = spre dreapta, pozitiv = in sensul acelor de ceas PE ECRAN (y creste in
 *    jos), ca in SVG si in canvas-ul din browser: 90 = in jos, 180 = spre stanga, 270 = in sus.
 *
 * Nicio forma nu scrie in afara suprafetei si a zonei de taiere: marginile se taie intai in virgula mobila,
 * abia apoi se trec in intregi. Intrari fara sens (NaN, infinit, grosime sau raza <= 0, coordonate peste
 * +-1 000 000, poligon cu mai putin de 3 varfuri sau peste 4096) nu deseneaza nimic.
 *
 * Desenul se face pe firul gRC (gDC::exec, opcode gOpcode::desenNetezit), in aceeasi coada cu fill, blit si
 * textul, deci ordinea fata de fillRect se pastreaza si nimic nu scrie in panza cat timp o copiaza gRC pe ecran.
 */

#include <vector>
#include <lib/gdi/gpixmap.h>
#include <lib/gdi/region.h>

struct gDesenNetezit
{
	enum
	{
		linie = 1,		/* x0,y0 -> x1,y1, grosime, capete rotunde */
		arc = 2,		/* centru x0,y0, raza liniei de mijloc, grosime, start si unghi_arc in grade */
		disc = 3,		/* centru x0,y0, raza */
		poligon = 4		/* puncte = x,y,x,y,... */
	};
	int forma;
	float x0, y0, x1, y1;
	float raza, grosime;
	float start, unghi_arc;	/* unghi_arc cu semn; |unghi_arc| >= 360 = inel intreg */
	int capete_rotunde;	/* numai pentru arc: 1 = capete rotunde, 0 = capete drepte (taiate pe raza) */
	std::vector<float> puncte;
	gRGB culoare;

	gDesenNetezit(): forma(0), x0(0), y0(0), x1(0), y1(0), raza(0), grosime(0), start(0), unghi_arc(0),
		capete_rotunde(1)
	{
	}
};

/* Deseneaza forma pe suprafata, numai in interiorul zonei de taiere, cu forma mutata cu `offset`
   (m_current_offset al gDC-ului, ca la fill). Suprafetele care nu au 32 de biti pe pixel se lasa neatinse. */
void deseneazaNetezit(gSurface *suprafata, const gRegion &taiere, const ePoint &offset, const gDesenNetezit &d);

/* Dreptunghiul care cuprinde tot ce poate atinge forma (cu marginea netezita), taiat la `limite`.
   Gol daca forma nu deseneaza nimic. Folosit de eCanvas ca sa invalideze numai cat trebuie. */
eRect margineDesenNetezit(const gDesenNetezit &d, const eRect &limite);

#endif
