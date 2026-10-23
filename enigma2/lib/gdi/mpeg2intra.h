/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_gdi_mpeg2intra_h
#define __lib_gdi_mpeg2intra_h

/* Codor MPEG-2 pentru UN SINGUR cadru intra: ecranul de pornire (.mvi) al receptorului.
   Scris de noi dupa ISO/IEC 13818-2 (acelasi text cu ITU-T H.262), ca sa nu fie nevoie
   de niciun pachet in plus pe receptor (ffmpeg ar fi insemnat peste 20 MB).
   Fisierul asta NU include nimic din enigma2, ca sa poata fi compilat si incercat singur pe PC. */

#include <vector>

namespace mpeg2intra
{
	/* Marimile sunt fixe: ecranul de pornire e mereu 1920x1080.
	   1080 nu se imparte la 16, deci se codeaza 1088 de randuri (68 de randuri de macroblocuri);
	   ultimele 8 randuri nu se vad niciodata, dar trebuie sa existe. */
	static const int LATIME = 1920;
	static const int INALTIME = 1080;
	static const int INALTIME_CODATA = 1088;
	static const int LATIME_CROMA = 960;
	static const int INALTIME_CROMA = 544;

	/* Din BGRA (asa sta un gPixmap de 32 de biti: B, G, R, A) in Y, Cb, Cr.
	   Matricea e BT.601 cu domeniu limitat (alb 235, negru 16), masurata pe fisierele
	   care merg azi pe receptor, nu presupusa. Croma se subesantioneaza 4:2:0 (media a 2x2).
	   Randurile de sub 1080 se umplu copiind randul 1079.
	   "pas" este numarul de octeti dintre doua randuri ale imaginii (stride).
	   Cele trei planuri trebuie sa aiba LATIME*INALTIME_CODATA, respectiv
	   LATIME_CROMA*INALTIME_CROMA octeti. */
	void dinBGRA(const unsigned char *bgra, int pas,
		unsigned char *planY, unsigned char *planCb, unsigned char *planCr);

	/* Codeaza cele trei planuri intr-un cadru intra MPEG-2, exact in forma pe care o accepta
	   showiframe pe receptor. "cod_cuantizare" este quantiser_scale_code (1..31): mai mic
	   inseamna poza mai buna si fisier mai mare. Intoarce 0 la bine, negativ la rau. */
	int codeaza(const unsigned char *planY, const unsigned char *planCb, const unsigned char *planCr,
		int cod_cuantizare, std::vector<unsigned char> &iesire);
}

#endif
