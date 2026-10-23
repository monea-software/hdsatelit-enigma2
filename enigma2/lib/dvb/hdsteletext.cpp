/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsteletext.cpp: culegerea, randarea si compunerea paginilor de teletext (vezi hdsteletext.h).
 *
 * Trimiterile la standard sunt la ETSI EN 300 706 (Enhanced Teletext specification): 8.2 Hamming 8/4, 8.3 Hamming
 * 24/18, 9.3 antetul paginii, 9.4 pachetele X/26-X/28, 9.5 M/29, 9.8 8/30, 12.2 atributele de spatiere (tabelul 26),
 * 15 seturile de caractere (tabelele 32-36).
 */

#include <lib/dvb/hdsteletext.h>

#include <algorithm>
#include <math.h>
#include <string.h>

namespace hdsttx
{

/* ------------------------------------------------------------------ decodari */

namespace
{
	struct Tabele
	{
		uint8_t intors[256];
		int8_t h84[256];
		Tabele()
		{
			for (int i = 0; i < 256; i++)
			{
				int r = 0;
				for (int b = 0; b < 8; b++)
					if (i & (1 << b))
						r |= 0x80 >> b;
				intors[i] = (uint8_t)r;
			}
			/* cuvintele de cod Hamming 8/4 (8.2): P1 D1 P2 D2 P3 D3 P4 D4 in bitii 0..7, fiecare test cu paritate
			   impara; un octet la cel mult un bit de un cuvant de cod se citeste ca acel cuvant */
			uint8_t cod[16];
			for (int d = 0; d < 16; d++)
			{
				int d1 = d & 1, d2 = (d >> 1) & 1, d3 = (d >> 2) & 1, d4 = (d >> 3) & 1;
				int p1 = 1 ^ d1 ^ d3 ^ d4, p2 = 1 ^ d1 ^ d2 ^ d4, p3 = 1 ^ d1 ^ d2 ^ d3;
				int p4 = 1 ^ p1 ^ d1 ^ p2 ^ d2 ^ p3 ^ d3 ^ d4;
				cod[d] = (uint8_t)(p1 | d1 << 1 | p2 << 2 | d2 << 3 | p3 << 4 | d3 << 5 | p4 << 6 | d4 << 7);
			}
			for (int i = 0; i < 256; i++)
			{
				h84[i] = -1;
				for (int d = 0; d < 16; d++)
				{
					int x = i ^ cod[d];
					if ((x & (x - 1)) == 0)    /* zero sau un singur bit */
					{
						h84[i] = (int8_t)d;
						break;
					}
				}
			}
		}
	};
	const Tabele &tabele()
	{
		static const Tabele t;
		return t;
	}
}

uint8_t intoarce(uint8_t b)
{
	return tabele().intors[b];
}

int hamming84(uint8_t intors)
{
	return tabele().h84[intors];
}

int hamming2418(const uint8_t *b)
{
	uint32_t v = (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16);
	/* pozitiile 1..24 sunt bitii 0..23; P1-P5 la 1, 2, 4, 8, 16 dau, cu paritate impara, sindromul (pozitia
	   bitului gresit); P6 (pozitia 24) tine paritatea impara a tuturor */
	int sindrom = 0;
	for (int k = 0; k < 5; k++)
	{
		int test = 0;
		for (int p = 1; p <= 23; p++)
			if ((p >> k) & 1)
				test ^= (v >> (p - 1)) & 1;
		if (!test)
			sindrom |= 1 << k;
	}
	int toti = 0;
	for (int p = 0; p < 24; p++)
		toti ^= (v >> p) & 1;
	if (sindrom)
	{
		if (toti)              /* paritatea totala buna si totusi sindrom: doua erori */
			return -1;
		if (sindrom > 23)
			return -1;
		v ^= 1u << (sindrom - 1);
	}
	return (int)(((v >> 2) & 1) | (((v >> 4) & 7) << 1) | (((v >> 8) & 0x7F) << 4) | (((v >> 16) & 0x7F) << 11));
}

int paritate(uint8_t intors)
{
	uint8_t x = intors;
	x ^= x >> 4;
	x ^= x >> 2;
	x ^= x >> 1;
	return (x & 1) ? (intors & 0x7F) : -1;
}

int paginaDinZecimal(int numar)
{
	if (numar < 100 || numar > 899)
		return PAGINA_FARA;
	return ((numar / 100) << 8) | (((numar / 10) % 10) << 4) | (numar % 10);
}

int zecimalDinPagina(int pagina)
{
	int m = (pagina >> 8) & 0xF, z = (pagina >> 4) & 0xF, u = pagina & 0xF;
	if (m < 1 || m > 8 || z > 9 || u > 9 || (pagina & ~0xFFF))
		return 0;
	return m * 100 + z * 10 + u;
}

/* ------------------------------------------------------------------ seturile de caractere */

namespace
{
	/* pozitiile G0 pe care subsetul national le schimba (tabelul 36), in ordinea coloanelor de mai jos */
	const uint8_t POZITII_NATIONALE[13] = { 0x23, 0x24, 0x40, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x60, 0x7B, 0x7C, 0x7D, 0x7E };

	enum
	{
		N_CEHA, N_ENGLEZA, N_ESTONA, N_FRANCEZA, N_GERMANA, N_ITALIANA, N_LETONA, N_POLONA, N_PORTUGHEZA, N_ROMANA,
		N_SARBA, N_SUEDEZA, N_TURCA, N_SUBSETURI
	};

	const uint16_t NATIONALE[N_SUBSETURI][13] = {
		/* ceha, slovaca */ { 0x0023, 0x016F, 0x010D, 0x0165, 0x017E, 0x00FD, 0x00ED, 0x0159, 0x00E9, 0x00E1, 0x011B, 0x00FA, 0x0161 },
		/* engleza */ { 0x00A3, 0x0024, 0x0040, 0x2190, 0x00BD, 0x2192, 0x2191, 0x0023, 0x2015, 0x00BC, 0x2016, 0x00BE, 0x00F7 },
		/* estona */ { 0x0023, 0x00F5, 0x0160, 0x00C4, 0x00D6, 0x017D, 0x00DC, 0x00D5, 0x0161, 0x00E4, 0x00F6, 0x017E, 0x00FC },
		/* franceza */ { 0x00E9, 0x00EF, 0x00E0, 0x00EB, 0x00EA, 0x00F9, 0x00EE, 0x0023, 0x00E8, 0x00E2, 0x00F4, 0x00FB, 0x00E7 },
		/* germana */ { 0x0023, 0x0024, 0x00A7, 0x00C4, 0x00D6, 0x00DC, 0x005E, 0x005F, 0x00B0, 0x00E4, 0x00F6, 0x00FC, 0x00DF },
		/* italiana */ { 0x00A3, 0x0024, 0x00E9, 0x00B0, 0x00E7, 0x2192, 0x2191, 0x0023, 0x00F9, 0x00E0, 0x00F2, 0x00E8, 0x00EC },
		/* letona, lituaniana */ { 0x0023, 0x0024, 0x0160, 0x0117, 0x0119, 0x017D, 0x010D, 0x016B, 0x0161, 0x0105, 0x0173, 0x017E, 0x012F },
		/* polona */ { 0x0023, 0x0144, 0x0105, 0x01B5, 0x015A, 0x0141, 0x0107, 0x00F3, 0x0119, 0x017C, 0x015B, 0x0142, 0x017A },
		/* portugheza, spaniola */ { 0x00E7, 0x0024, 0x00A1, 0x00E1, 0x00E9, 0x00ED, 0x00F3, 0x00FA, 0x00BF, 0x00FC, 0x00F1, 0x00E8, 0x00E0 },
		/* romana */ { 0x0023, 0x00A4, 0x0162, 0x00C2, 0x015E, 0x0102, 0x00CE, 0x0131, 0x0163, 0x00E2, 0x015F, 0x0103, 0x00EE },
		/* sarba, croata, slovena */ { 0x0023, 0x00CB, 0x010C, 0x0106, 0x017D, 0x0110, 0x0160, 0x00EB, 0x010D, 0x0107, 0x017E, 0x0111, 0x0161 },
		/* suedeza, finlandeza, maghiara */ { 0x0023, 0x00A4, 0x00C9, 0x00C4, 0x00D6, 0x00C5, 0x00DC, 0x005F, 0x00E9, 0x00E4, 0x00F6, 0x00E5, 0x00FC },
		/* turca */ { 0x20BA, 0x011F, 0x0130, 0x015E, 0x00D6, 0x00C7, 0x00DC, 0x011E, 0x0131, 0x015F, 0x00F6, 0x00E7, 0x00FC },
	};

	/* grupa (4 biti) si optiunea (3 biti, C12-C14 sau din X/28/0, M/29/0) -> subsetul (tabelul 32). Seturile
	   nelatine (chirilic, grec, arab, ebraic) si pozitiile rezervate cad pe engleza; grupa 0 optiunea 7 (rezervata)
	   e romana, ca la canalele romanesti care o trimit fara M/29. */
	const uint8_t SUBSET[16][8] = {
		{ N_ENGLEZA, N_GERMANA, N_SUEDEZA, N_ITALIANA, N_FRANCEZA, N_PORTUGHEZA, N_CEHA, N_ROMANA },
		{ N_POLONA, N_GERMANA, N_SUEDEZA, N_ITALIANA, N_FRANCEZA, N_ENGLEZA, N_CEHA, N_ENGLEZA },
		{ N_ENGLEZA, N_GERMANA, N_SUEDEZA, N_ITALIANA, N_FRANCEZA, N_PORTUGHEZA, N_TURCA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_SARBA, N_ENGLEZA, N_ROMANA },
		{ N_ENGLEZA, N_GERMANA, N_ESTONA, N_LETONA, N_ENGLEZA, N_ENGLEZA, N_CEHA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_TURCA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_FRANCEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
		{ N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA, N_ENGLEZA },
	};

	/* G2 latin (tabelul 33), 0x20..0x7F; 0x41-0x4F sunt semnele diacritice singure */
	const uint16_t G2_LATIN[96] = {
		0x0020, 0x00A1, 0x00A2, 0x00A3, 0x0024, 0x00A5, 0x0023, 0x00A7, 0x00A4, 0x2018, 0x201C, 0x00AB, 0x2190, 0x2191, 0x2192, 0x2193,
		0x00B0, 0x00B1, 0x00B2, 0x00B3, 0x00D7, 0x00B5, 0x00B6, 0x00B7, 0x00F7, 0x2019, 0x201D, 0x00BB, 0x00BC, 0x00BD, 0x00BE, 0x00BF,
		0x0020, 0x0060, 0x00B4, 0x02C6, 0x02DC, 0x00AF, 0x02D8, 0x02D9, 0x00A8, 0x0020, 0x02DA, 0x00B8, 0x0020, 0x02DD, 0x02DB, 0x02C7,
		0x2015, 0x00B9, 0x00AE, 0x00A9, 0x2122, 0x266A, 0x20AC, 0x2030, 0x03B1, 0x0020, 0x0020, 0x0020, 0x215B, 0x215C, 0x215D, 0x215E,
		0x2126, 0x00C6, 0x0110, 0x00AA, 0x0126, 0x0020, 0x0132, 0x013F, 0x0141, 0x00D8, 0x0152, 0x00BA, 0x00DE, 0x0166, 0x014A, 0x0149,
		0x0138, 0x00E6, 0x0111, 0x00F0, 0x0127, 0x0131, 0x0133, 0x0140, 0x0142, 0x00F8, 0x0153, 0x00DF, 0x00FE, 0x0167, 0x014B, 0x0020,
	};

	/* litera compusa (NFC) pentru semnul 1..15 (randul) si litera A-Z, a-z (coloana); 0 = nu exista. Facut din
	   tabelele Unicode. */
	const uint16_t DIACRITICE[15][52] = {
		{ 0x00C0, 0x0000, 0x0000, 0x0000, 0x00C8, 0x0000, 0x0000, 0x0000, 0x00CC, 0x0000, 0x0000, 0x0000, 0x0000, 0x01F8, 0x00D2, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x00D9, 0x0000, 0x1E80, 0x0000, 0x1EF2, 0x0000, 0x00E0, 0x0000, 0x0000, 0x0000, 0x00E8, 0x0000, 0x0000, 0x0000, 0x00EC, 0x0000, 0x0000, 0x0000, 0x0000, 0x01F9, 0x00F2, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x00F9, 0x0000, 0x1E81, 0x0000, 0x1EF3, 0x0000 },
		{ 0x00C1, 0x0000, 0x0106, 0x0000, 0x00C9, 0x0000, 0x01F4, 0x0000, 0x00CD, 0x0000, 0x1E30, 0x0139, 0x1E3E, 0x0143, 0x00D3, 0x1E54, 0x0000, 0x0154, 0x015A, 0x0000, 0x00DA, 0x0000, 0x1E82, 0x0000, 0x00DD, 0x0179, 0x00E1, 0x0000, 0x0107, 0x0000, 0x00E9, 0x0000, 0x01F5, 0x0000, 0x00ED, 0x0000, 0x1E31, 0x013A, 0x1E3F, 0x0144, 0x00F3, 0x1E55, 0x0000, 0x0155, 0x015B, 0x0000, 0x00FA, 0x0000, 0x1E83, 0x0000, 0x00FD, 0x017A },
		{ 0x00C2, 0x0000, 0x0108, 0x0000, 0x00CA, 0x0000, 0x011C, 0x0124, 0x00CE, 0x0134, 0x0000, 0x0000, 0x0000, 0x0000, 0x00D4, 0x0000, 0x0000, 0x0000, 0x015C, 0x0000, 0x00DB, 0x0000, 0x0174, 0x0000, 0x0176, 0x1E90, 0x00E2, 0x0000, 0x0109, 0x0000, 0x00EA, 0x0000, 0x011D, 0x0125, 0x00EE, 0x0135, 0x0000, 0x0000, 0x0000, 0x0000, 0x00F4, 0x0000, 0x0000, 0x0000, 0x015D, 0x0000, 0x00FB, 0x0000, 0x0175, 0x0000, 0x0177, 0x1E91 },
		{ 0x00C3, 0x0000, 0x0000, 0x0000, 0x1EBC, 0x0000, 0x0000, 0x0000, 0x0128, 0x0000, 0x0000, 0x0000, 0x0000, 0x00D1, 0x00D5, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0168, 0x1E7C, 0x0000, 0x0000, 0x1EF8, 0x0000, 0x00E3, 0x0000, 0x0000, 0x0000, 0x1EBD, 0x0000, 0x0000, 0x0000, 0x0129, 0x0000, 0x0000, 0x0000, 0x0000, 0x00F1, 0x00F5, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0169, 0x1E7D, 0x0000, 0x0000, 0x1EF9, 0x0000 },
		{ 0x0100, 0x0000, 0x0000, 0x0000, 0x0112, 0x0000, 0x1E20, 0x0000, 0x012A, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x014C, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x016A, 0x0000, 0x0000, 0x0000, 0x0232, 0x0000, 0x0101, 0x0000, 0x0000, 0x0000, 0x0113, 0x0000, 0x1E21, 0x0000, 0x012B, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x014D, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x016B, 0x0000, 0x0000, 0x0000, 0x0233, 0x0000 },
		{ 0x0102, 0x0000, 0x0000, 0x0000, 0x0114, 0x0000, 0x011E, 0x0000, 0x012C, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x014E, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x016C, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0103, 0x0000, 0x0000, 0x0000, 0x0115, 0x0000, 0x011F, 0x0000, 0x012D, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x014F, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x016D, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000 },
		{ 0x0226, 0x1E02, 0x010A, 0x1E0A, 0x0116, 0x1E1E, 0x0120, 0x1E22, 0x0130, 0x0000, 0x0000, 0x0000, 0x1E40, 0x1E44, 0x022E, 0x1E56, 0x0000, 0x1E58, 0x1E60, 0x1E6A, 0x0000, 0x0000, 0x1E86, 0x1E8A, 0x1E8E, 0x017B, 0x0227, 0x1E03, 0x010B, 0x1E0B, 0x0117, 0x1E1F, 0x0121, 0x1E23, 0x0000, 0x0000, 0x0000, 0x0000, 0x1E41, 0x1E45, 0x022F, 0x1E57, 0x0000, 0x1E59, 0x1E61, 0x1E6B, 0x0000, 0x0000, 0x1E87, 0x1E8B, 0x1E8F, 0x017C },
		{ 0x00C4, 0x0000, 0x0000, 0x0000, 0x00CB, 0x0000, 0x0000, 0x1E26, 0x00CF, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x00D6, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x00DC, 0x0000, 0x1E84, 0x1E8C, 0x0178, 0x0000, 0x00E4, 0x0000, 0x0000, 0x0000, 0x00EB, 0x0000, 0x0000, 0x1E27, 0x00EF, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x00F6, 0x0000, 0x0000, 0x0000, 0x0000, 0x1E97, 0x00FC, 0x0000, 0x1E85, 0x1E8D, 0x00FF, 0x0000 },
		{ 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000 },
		{ 0x00C5, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x016E, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x00E5, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x016F, 0x0000, 0x1E98, 0x0000, 0x1E99, 0x0000 },
		{ 0x0000, 0x0000, 0x00C7, 0x1E10, 0x0228, 0x0000, 0x0122, 0x1E28, 0x0000, 0x0000, 0x0136, 0x013B, 0x0000, 0x0145, 0x0000, 0x0000, 0x0000, 0x0156, 0x015E, 0x0162, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x00E7, 0x1E11, 0x0229, 0x0000, 0x0123, 0x1E29, 0x0000, 0x0000, 0x0137, 0x013C, 0x0000, 0x0146, 0x0000, 0x0000, 0x0000, 0x0157, 0x015F, 0x0163, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000 },
		{ 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000 },
		{ 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0150, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0170, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0151, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0171, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000 },
		{ 0x0104, 0x0000, 0x0000, 0x0000, 0x0118, 0x0000, 0x0000, 0x0000, 0x012E, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x01EA, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0172, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0105, 0x0000, 0x0000, 0x0000, 0x0119, 0x0000, 0x0000, 0x0000, 0x012F, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x01EB, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0173, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000 },
		{ 0x01CD, 0x0000, 0x010C, 0x010E, 0x011A, 0x0000, 0x01E6, 0x021E, 0x01CF, 0x0000, 0x01E8, 0x013D, 0x0000, 0x0147, 0x01D1, 0x0000, 0x0000, 0x0158, 0x0160, 0x0164, 0x01D3, 0x0000, 0x0000, 0x0000, 0x0000, 0x017D, 0x01CE, 0x0000, 0x010D, 0x010F, 0x011B, 0x0000, 0x01E7, 0x021F, 0x01D0, 0x01F0, 0x01E9, 0x013E, 0x0000, 0x0148, 0x01D2, 0x0000, 0x0000, 0x0159, 0x0161, 0x0165, 0x01D4, 0x0000, 0x0000, 0x0000, 0x0000, 0x017E },
	};

	/* litera G0 latina cu subsetul dat; 0x7F (dreptunghiul plin) se trateaza separat */
	uint32_t literaG0(int cod, int subset)
	{
		for (int k = 0; k < 13; k++)
			if (POZITII_NATIONALE[k] == cod)
				return NATIONALE[subset][k];
		return (uint32_t)cod;
	}

	/* litera de baza (ASCII) cu semnul 1..15; fara forma compusa ramane litera */
	uint32_t cuSemn(uint32_t baza, int semn)
	{
		int c = -1;
		if (baza >= 'A' && baza <= 'Z')
			c = (int)(baza - 'A');
		else if (baza >= 'a' && baza <= 'z')
			c = 26 + (int)(baza - 'a');
		if (c < 0 || semn < 1 || semn > 15)
			return baza;
		uint32_t r = DIACRITICE[semn - 1][c];
		return r ? r : baza;
	}

	/* desemnarea pe 7 biti (grupa << 3 | optiunea) -> subset */
	int subsetDin(int desemnare)
	{
		return SUBSET[(desemnare >> 3) & 0xF][desemnare & 7];
	}

	/* pagina interna dintr-o legatura de 6 octeti (X/27/0, 8/30): unitati, zeci, S1, S2+M1, S3, S4+M2+M3; magazia
	   e relativa la cea a pachetului. PAGINA_FARA = fara legatura (0xFF) sau octeti stricati. */
	int citesteLegatura(const uint8_t *b, int magazie)
	{
		int u = hamming84(b[0]), z = hamming84(b[1]), s2m1 = hamming84(b[3]), s4m23 = hamming84(b[5]);
		if (u < 0 || z < 0 || s2m1 < 0 || s4m23 < 0)
			return PAGINA_FARA;
		int x = (z << 4) | u;
		if (x == 0xFF)
			return PAGINA_FARA;
		int rel = ((s2m1 >> 3) & 1) | (((s4m23 >> 2) & 3) << 1);
		int m = (magazie & 7) ^ rel;
		if (!m)
			m = 8;
		return (m << 8) | x;
	}
}

/* ------------------------------------------------------------------ culegerea */

Subpagina::Subpagina()
	: subcod(0), control(0), randuri(0), are_x28(false), are_legaturi(false), ordine(0), versiune(0)
{
	memset(text, 0, sizeof(text));
	x28[0] = x28[1] = 0;
	for (int k = 0; k < LEGATURI; k++)
		legaturi[k] = PAGINA_FARA;
}

void Subpagina::stergeCorpul()
{
	memset(text[1], 0, sizeof(text) - sizeof(text[0]));
	randuri &= 1;
	x26.clear();
	are_x28 = false;
	are_legaturi = false;
	for (int k = 0; k < LEGATURI; k++)
		legaturi[k] = PAGINA_FARA;
}

Colector::Colector(size_t max_subpagini)
	: m_max(max_subpagini < 16 ? 16 : max_subpagini)
{
	reseteaza();
}

void Colector::setMaxSubpagini(size_t n)
{
	m_max = n < 16 ? 16 : n;
	while (m_numar > m_max)
		faLoc();
}

void Colector::reseteaza()
{
	m_pagini.clear();
	m_numar = 0;
	m_ceas = 0;
	m_versiune++;
	m_bune = m_rele = 0;
	for (int m = 0; m < 9; m++)
	{
		m_curenta[m] = PAGINA_FARA;
		m_subcod_curent[m] = 0;
		m_are_antet[m] = false;
		m_antet_control[m] = 0;
		m_antet_versiune[m] = 0;
		m_are_m29[m] = false;
		m_m29[m][0] = m_m29[m][1] = 0;
	}
	memset(m_antet, 0, sizeof(m_antet));
	m_initiala = PAGINA_FARA;
	memset(m_nume, 0, sizeof(m_nume));
	m_are_nume = false;
}

Subpagina *Colector::curenta(int magazie)
{
	if (m_curenta[magazie] == PAGINA_FARA)
		return 0;
	std::map<int, Subpagini>::iterator p = m_pagini.find(m_curenta[magazie]);
	if (p == m_pagini.end())
		return 0;
	Subpagini::iterator s = p->second.find(m_subcod_curent[magazie]);
	return s == p->second.end() ? 0 : &s->second;
}

void Colector::inchide(int magazie)
{
	m_curenta[magazie] = PAGINA_FARA;
}

void Colector::faLoc()
{
	/* pleaca subpagina primita cel mai demult, dar nu una care se primeste acum */
	std::map<int, Subpagini>::iterator pagina_veche = m_pagini.end();
	Subpagini::iterator sub_veche;
	uint32_t cea_mai_veche = 0;
	bool gasit = false;
	for (std::map<int, Subpagini>::iterator p = m_pagini.begin(); p != m_pagini.end(); ++p)
		for (Subpagini::iterator s = p->second.begin(); s != p->second.end(); ++s)
		{
			bool acum = false;
			for (int m = 1; m <= 8; m++)
				if (m_curenta[m] == p->first && m_subcod_curent[m] == s->first)
					acum = true;
			if (acum)
				continue;
			if (!gasit || s->second.ordine < cea_mai_veche)
			{
				gasit = true;
				cea_mai_veche = s->second.ordine;
				pagina_veche = p;
				sub_veche = s;
			}
		}
	if (!gasit)
		return;
	pagina_veche->second.erase(sub_veche);
	if (pagina_veche->second.empty())
		m_pagini.erase(pagina_veche);
	m_numar--;
}

bool Colector::adaugaPachet(const uint8_t *ad)
{
	uint8_t d[42];
	for (int k = 0; k < 42; k++)
		d[k] = intoarce(ad[k]);
	int a0 = hamming84(d[0]), a1 = hamming84(d[1]);
	if (a0 < 0 || a1 < 0)
	{
		m_rele++;
		return false;
	}
	int magazie = a0 & 7;
	if (!magazie)
		magazie = 8;
	int rand = (a0 >> 3) | (a1 << 1);
	const uint8_t *date = d + 2;
	m_ceas++;

	if (rand == 0)
	{
		int h[8];
		for (int k = 0; k < 8; k++)
		{
			h[k] = hamming84(date[k]);
			if (h[k] < 0)
			{
				m_rele++;
				return false;
			}
		}
		int x = (h[1] << 4) | h[0];
		int subcod = h[2] | ((h[3] & 7) << 4) | (h[4] << 8) | ((h[5] & 3) << 12);
		int control = ((h[3] & 8) ? C4_STERGE : 0) | ((h[5] & 0xC) << 3) | (h[6] << 7) | (h[7] << 11);
		if (control & C11_SERIAL)
			for (int m = 1; m <= 8; m++)
				inchide(m);
		else
			inchide(magazie);
		/* antetul magaziei (si la paginile de umplere 0xFF): ceasul din coltul din dreapta merge cu el */
		if (memcmp(m_antet[magazie], date + 8, 32) || !m_are_antet[magazie] || m_antet_control[magazie] != control)
		{
			memcpy(m_antet[magazie], date + 8, 32);
			m_antet_control[magazie] = (uint16_t)control;
			m_antet_versiune[magazie]++;
		}
		m_are_antet[magazie] = true;
		m_bune++;
		if (x == 0xFF)
			return true;
		int pagina = (magazie << 8) | x;
		Subpagini &subs = m_pagini[pagina];
		Subpagini::iterator s = subs.find(subcod);
		if (s == subs.end())
		{
			while (m_numar >= m_max)
			{
				size_t inainte = m_numar;
				faLoc();
				if (m_numar == inainte)
					break;
			}
			s = m_pagini[pagina].insert(std::make_pair(subcod, Subpagina())).first;
			s->second.subcod = (uint16_t)subcod;
			m_numar++;
		}
		Subpagina &sp = s->second;
		if (control & C4_STERGE)
			sp.stergeCorpul();
		sp.control = (uint16_t)control;
		memset(sp.text[0], 0x20 | 0x80, 8);      /* coloanele 0-7 nu se afiseaza; spatiu cu paritatea buna */
		memcpy(sp.text[0] + 8, date + 8, 32);
		sp.randuri |= 1;
		sp.ordine = m_ceas;
		sp.versiune++;
		m_versiune++;
		m_curenta[magazie] = pagina;
		m_subcod_curent[magazie] = subcod;
		return true;
	}

	if (rand == 29)
	{
		int dc = hamming84(date[0]);
		if (dc == 0)
		{
			int t1 = hamming2418(date + 1), t2 = hamming2418(date + 4);
			if (t1 >= 0 && t2 >= 0)
			{
				m_m29[magazie][0] = (uint32_t)t1;
				m_m29[magazie][1] = (uint32_t)t2;
				m_are_m29[magazie] = true;
				m_versiune++;
			}
		}
		m_bune++;
		return true;
	}

	if (rand == 30)
	{
		if (magazie == 8)
		{
			int dc = hamming84(date[0]);
			if (dc >= 0 && dc <= 3)
			{
				int p = citesteLegatura(date + 1, 8);
				if (p != PAGINA_FARA && zecimalDinPagina(p))
					m_initiala = p;
				for (int k = 0; k < 20; k++)
				{
					int c = paritate(date[20 + k]);
					m_nume[k] = (uint8_t)(c >= 0x20 ? c : 0x20);
				}
				m_are_nume = true;
			}
		}
		m_bune++;
		return true;
	}

	if (rand == 31)
	{
		m_bune++;
		return true;
	}

	Subpagina *sp = curenta(magazie);
	if (!sp)
	{
		m_bune++;
		return true;     /* pachet al unei pagini al carei antet nu l-am vazut */
	}
	sp->ordine = m_ceas;

	if (rand <= 25)
	{
		bool avea = (sp->randuri >> rand) & 1;
		for (int k = 0; k < COLOANE; k++)
		{
			/* octetul cu paritatea stricata nu inlocuieste unul bun primit inainte */
			if (paritate(date[k]) < 0 && avea && paritate(sp->text[rand][k]) >= 0)
				continue;
			sp->text[rand][k] = date[k];
		}
		sp->randuri |= 1u << rand;
	}
	else if (rand == 26)
	{
		int dc = hamming84(date[0]);
		if (dc >= 0)
		{
			size_t baza = (size_t)dc * TRIPLETI_X26;
			if (sp->x26.size() < baza + TRIPLETI_X26)
				sp->x26.resize(baza + TRIPLETI_X26, 0xFFFFFFFFu);
			for (int k = 0; k < TRIPLETI_X26; k++)
			{
				int t = hamming2418(date + 1 + 3 * k);
				sp->x26[baza + k] = t < 0 ? 0xFFFFFFFFu : (uint32_t)t;
			}
		}
	}
	else if (rand == 27)
	{
		int dc = hamming84(date[0]);
		if (dc == 0)
		{
			for (int k = 0; k < LEGATURI; k++)
				sp->legaturi[k] = citesteLegatura(date + 1 + 6 * k, magazie);
			sp->are_legaturi = true;
		}
	}
	else if (rand == 28)
	{
		int dc = hamming84(date[0]);
		if (dc == 0)
		{
			int t1 = hamming2418(date + 1), t2 = hamming2418(date + 4);
			if (t1 >= 0 && t2 >= 0)
			{
				sp->x28[0] = (uint32_t)t1;
				sp->x28[1] = (uint32_t)t2;
				sp->are_x28 = true;
			}
		}
	}
	sp->versiune++;
	m_versiune++;
	m_bune++;
	return true;
}

const Subpagina *Colector::gaseste(int pagina, int subcod) const
{
	std::map<int, Subpagini>::const_iterator p = m_pagini.find(pagina);
	if (p == m_pagini.end() || p->second.empty())
		return 0;
	if (subcod >= 0)
	{
		Subpagini::const_iterator s = p->second.find(subcod);
		return s == p->second.end() ? 0 : &s->second;
	}
	const Subpagina *cea_noua = 0;
	for (Subpagini::const_iterator s = p->second.begin(); s != p->second.end(); ++s)
		if (!cea_noua || s->second.ordine > cea_noua->ordine)
			cea_noua = &s->second;
	return cea_noua;
}

std::vector<int> Colector::subcoduri(int pagina) const
{
	std::vector<int> r;
	std::map<int, Subpagini>::const_iterator p = m_pagini.find(pagina);
	if (p != m_pagini.end())
		for (Subpagini::const_iterator s = p->second.begin(); s != p->second.end(); ++s)
			r.push_back(s->first);
	return r;
}

std::vector<int> Colector::pagini() const
{
	std::vector<int> r;
	for (std::map<int, Subpagini>::const_iterator p = m_pagini.begin(); p != m_pagini.end(); ++p)
		r.push_back(p->first);
	return r;
}

uint32_t Colector::versiunePagina(int pagina) const
{
	std::map<int, Subpagini>::const_iterator p = m_pagini.find(pagina);
	if (p == m_pagini.end())
		return 0;
	uint32_t v = 0;
	for (Subpagini::const_iterator s = p->second.begin(); s != p->second.end(); ++s)
		v += s->second.versiune;
	return v ? v : 1;
}

const uint8_t *Colector::antetRulant(int magazie, uint16_t *control) const
{
	if (magazie < 1 || magazie > 8 || !m_are_antet[magazie])
		return 0;
	if (control)
		*control = m_antet_control[magazie];
	return m_antet[magazie];
}

uint32_t Colector::versiuneAntet(int magazie) const
{
	return (magazie >= 1 && magazie <= 8) ? m_antet_versiune[magazie] : 0;
}

bool Colector::m29(int magazie, uint32_t t[2]) const
{
	if (magazie < 1 || magazie > 8 || !m_are_m29[magazie])
		return false;
	t[0] = m_m29[magazie][0];
	t[1] = m_m29[magazie][1];
	return true;
}

int Colector::paginaInitiala() const
{
	return m_initiala;
}

std::string Colector::numeServiciu() const
{
	if (!m_are_nume)
		return std::string();
	int a = 0, b = 20;
	while (a < b && m_nume[a] == 0x20)
		a++;
	while (b > a && m_nume[b - 1] == 0x20)
		b--;
	return std::string((const char *)m_nume + a, (size_t)(b - a));
}

size_t Colector::octeti() const
{
	size_t n = 0;
	for (std::map<int, Subpagini>::const_iterator p = m_pagini.begin(); p != m_pagini.end(); ++p)
		for (Subpagini::const_iterator s = p->second.begin(); s != p->second.end(); ++s)
			n += sizeof(Subpagina) + s->second.x26.capacity() * sizeof(uint32_t) + 48;
	return n;
}

int Colector::topTip(int pagina) const
{
	int z = zecimalDinPagina(pagina);
	if (!z)
		return -1;
	const Subpagina *btt = gaseste(0x1F0, -1);
	if (!btt)
		return -1;
	int index = z - 100;
	int rand = 1 + index / COLOANE, col = index % COLOANE;
	if (!((btt->randuri >> rand) & 1))
		return -1;
	int v = hamming84(btt->text[rand][col]);
	return v < 0 ? 0 : v;
}

/* ------------------------------------------------------------------ copia (exporta / incarca) */

namespace
{
	const char MAGIC[8] = { 'H', 'D', 'S', 'T', 'T', 'X', '0', '1' };

	void pune16(std::string &o, unsigned v)
	{
		o += (char)(v & 0xFF);
		o += (char)((v >> 8) & 0xFF);
	}

	void pune32(std::string &o, uint32_t v)
	{
		pune16(o, v & 0xFFFF);
		pune16(o, v >> 16);
	}

	struct Cititor
	{
		const uint8_t *p, *capat;
		bool bun;
		Cititor(const uint8_t *d, size_t n) : p(d), capat(d + n), bun(true) {}
		bool are(size_t n) { if ((size_t)(capat - p) < n) bun = false; return bun; }
		unsigned u8() { if (!are(1)) return 0; return *p++; }
		unsigned u16() { if (!are(2)) return 0; unsigned v = p[0] | (p[1] << 8); p += 2; return v; }
		uint32_t u32() { uint32_t a = u16(); uint32_t b = u16(); return a | (b << 16); }
		void bloc(void *d, size_t n) { if (!are(n)) return; memcpy(d, p, n); p += n; }
	};
}

std::string Colector::exporta(int pid) const
{
	std::string o(MAGIC, sizeof(MAGIC));
	pune16(o, pid > 0 ? (unsigned)pid : 0);
	pune32(o, (uint32_t)m_numar);
	for (std::map<int, Subpagini>::const_iterator p = m_pagini.begin(); p != m_pagini.end(); ++p)
		for (Subpagini::const_iterator s = p->second.begin(); s != p->second.end(); ++s)
		{
			const Subpagina &sp = s->second;
			pune16(o, (unsigned)p->first);
			pune16(o, sp.subcod);
			pune16(o, sp.control);
			pune32(o, sp.randuri);
			pune32(o, sp.ordine);
			o.append((const char *)sp.text, sizeof(sp.text));
			pune16(o, (unsigned)sp.x26.size());
			for (size_t k = 0; k < sp.x26.size(); k++)
				pune32(o, sp.x26[k]);
			o += (char)(sp.are_x28 ? 1 : 0);
			pune32(o, sp.x28[0]);
			pune32(o, sp.x28[1]);
			o += (char)(sp.are_legaturi ? 1 : 0);
			for (int k = 0; k < LEGATURI; k++)
				pune16(o, (unsigned)sp.legaturi[k]);
		}
	for (int m = 1; m <= 8; m++)
	{
		o += (char)(m_are_antet[m] ? 1 : 0);
		pune16(o, m_antet_control[m]);
		o.append((const char *)m_antet[m], 32);
		o += (char)(m_are_m29[m] ? 1 : 0);
		pune32(o, m_m29[m][0]);
		pune32(o, m_m29[m][1]);
	}
	pune16(o, (unsigned)m_initiala);
	o += (char)(m_are_nume ? 1 : 0);
	o.append((const char *)m_nume, 20);
	return o;
}

int Colector::incarca(const uint8_t *date, size_t n)
{
	reseteaza();
	Cititor c(date, n);
	char magic[8];
	c.bloc(magic, sizeof(magic));
	if (!c.bun || memcmp(magic, MAGIC, sizeof(MAGIC)))
		return -1;
	int pid = (int)c.u16();
	uint32_t numar = c.u32();
	if (!c.bun || numar > 100000)
		return -1;
	for (uint32_t k = 0; k < numar && c.bun; k++)
	{
		int pagina = (int)c.u16();
		Subpagina sp;
		sp.subcod = (uint16_t)c.u16();
		sp.control = (uint16_t)c.u16();
		sp.randuri = c.u32();
		sp.ordine = c.u32();
		c.bloc(sp.text, sizeof(sp.text));
		unsigned n26 = c.u16();
		if (n26 > 16 * TRIPLETI_X26)
		{
			c.bun = false;
			break;
		}
		sp.x26.resize(n26);
		for (unsigned t = 0; t < n26; t++)
			sp.x26[t] = c.u32();
		sp.are_x28 = c.u8() != 0;
		sp.x28[0] = c.u32();
		sp.x28[1] = c.u32();
		sp.are_legaturi = c.u8() != 0;
		for (int l = 0; l < LEGATURI; l++)
			sp.legaturi[l] = (int)c.u16();
		sp.versiune = 1;
		if (!c.bun || pagina < 0x100 || pagina > 0x8FF)
		{
			c.bun = false;
			break;
		}
		if (m_pagini[pagina].insert(std::make_pair((int)sp.subcod, sp)).second)
			m_numar++;
		if (sp.ordine > m_ceas)
			m_ceas = sp.ordine;
	}
	for (int m = 1; m <= 8 && c.bun; m++)
	{
		m_are_antet[m] = c.u8() != 0;
		m_antet_control[m] = (uint16_t)c.u16();
		c.bloc(m_antet[m], 32);
		m_antet_versiune[m] = 1;
		m_are_m29[m] = c.u8() != 0;
		m_m29[m][0] = c.u32();
		m_m29[m][1] = c.u32();
	}
	m_initiala = (int)c.u16();
	m_are_nume = c.u8() != 0;
	c.bloc(m_nume, 20);
	if (!c.bun)
	{
		reseteaza();
		return -1;
	}
	m_versiune++;
	return pid;
}

/* ------------------------------------------------------------------ randarea */

namespace
{
	struct StareRand
	{
		int fata, fundal;
		bool mozaic, separat, tinut, intermitent, ascuns, cutie, dubla_i, dubla_l, esc;
		int tinut_cod;
		bool tinut_separat;
		StareRand()
			: fata(7), fundal(0), mozaic(false), separat(false), tinut(false), intermitent(false), ascuns(false),
			  cutie(false), dubla_i(false), dubla_l(false), esc(false), tinut_cod(0x20), tinut_separat(false)
		{
		}
	};

	uint8_t sextante(int cod)
	{
		return (uint8_t)(0x40 | (cod & 0x1F) | ((cod & 0x40) ? 0x20 : 0));
	}

	/* un rand de 40 de octeti intorsi -> celule; intoarce true daca are celule cu dubla inaltime */
	bool randeazaRand(const uint8_t *octeti, int subset, int subset2, int col0, Celula *iesire, bool permite_dubla_i)
	{
		StareRand s;
		bool are_dubla = false;
		for (int c = col0; c < COLOANE; c++)
		{
			Celula &ce = iesire[c];
			int b = paritate(octeti[c]);
			if (b < 0)
				b = 0x20;
			/* atributele "set-at" lucreaza chiar pe celula lor */
			if (b < 0x20)
			{
				switch (b)
				{
				case 0x09: s.intermitent = false; break;
				case 0x0C:
					if (s.dubla_i || s.dubla_l)
						s.tinut_cod = 0x20;
					s.dubla_i = s.dubla_l = false;
					break;
				case 0x18: s.ascuns = true; break;
				case 0x19: s.separat = false; break;
				case 0x1A: s.separat = true; break;
				case 0x1C: s.fundal = 0; break;
				case 0x1D: s.fundal = s.fata; break;
				case 0x1E: s.tinut = true; break;
				default: break;
				}
			}
			ce.fundal = (uint8_t)s.fundal;
			ce.fata = (uint8_t)s.fata;
			ce.atribute = 0;
			ce.mozaic = 0;
			ce.cod = 0x20;
			if (b < 0x20)
			{
				/* celula unui atribut: spatiu, sau mozaicul tinut */
				if (s.tinut && s.mozaic && s.tinut_cod != 0x20)
				{
					ce.mozaic = sextante(s.tinut_cod);
					if (s.tinut_separat)
						ce.atribute |= A_SEPARAT;
				}
			}
			else if (b == 0x7F)
			{
				ce.mozaic = 0x40 | 0x3F;
				if (s.mozaic)
				{
					s.tinut_cod = b;
					s.tinut_separat = s.separat;
					if (s.separat)
						ce.atribute |= A_SEPARAT;
				}
			}
			else if (s.mozaic && (b & 0x20))
			{
				ce.mozaic = sextante(b);
				if (s.separat)
					ce.atribute |= A_SEPARAT;
				s.tinut_cod = b;
				s.tinut_separat = s.separat;
			}
			else
				ce.cod = literaG0(b, s.esc ? subset2 : subset);
			if (s.intermitent)
				ce.atribute |= A_INTERMITENT;
			if (s.ascuns)
				ce.atribute |= A_ASCUNS;
			if (s.cutie)
				ce.atribute |= A_CUTIE;
			if (s.dubla_i && permite_dubla_i)
			{
				ce.atribute |= A_DUBLA_INALTIME;
				are_dubla = true;
			}
			if (s.dubla_l && c < COLOANE - 1)
				ce.atribute |= A_DUBLA_LATIME;
			/* atributele "set-after" lucreaza de la celula urmatoare */
			if (b < 0x20)
			{
				switch (b)
				{
				case 0x00: case 0x01: case 0x02: case 0x03: case 0x04: case 0x05: case 0x06: case 0x07:
					if (s.mozaic)
						s.tinut_cod = 0x20;
					s.fata = b;
					s.mozaic = false;
					s.ascuns = false;
					break;
				case 0x08: s.intermitent = true; break;
				case 0x0A: s.cutie = false; break;
				case 0x0B: s.cutie = true; break;
				case 0x0D:
					if (!s.dubla_i || s.dubla_l)
						s.tinut_cod = 0x20;
					s.dubla_i = true;
					s.dubla_l = false;
					break;
				case 0x0E:
					if (s.dubla_i || !s.dubla_l)
						s.tinut_cod = 0x20;
					s.dubla_i = false;
					s.dubla_l = true;
					break;
				case 0x0F:
					if (!s.dubla_i || !s.dubla_l)
						s.tinut_cod = 0x20;
					s.dubla_i = s.dubla_l = true;
					break;
				case 0x10: case 0x11: case 0x12: case 0x13: case 0x14: case 0x15: case 0x16: case 0x17:
					if (!s.mozaic)
						s.tinut_cod = 0x20;
					s.fata = b - 0x10;
					s.mozaic = true;
					s.ascuns = false;
					break;
				case 0x1B: s.esc = !s.esc; break;
				case 0x1F: s.tinut = false; break;
				default: break;
				}
			}
			/* dubla latime: celula din dreapta e acoperita de litera din stanga */
			if ((ce.atribute & A_DUBLA_LATIME) && c + 1 < COLOANE)
			{
				Celula &dr = iesire[c + 1];
				dr = ce;
				dr.atribute = (uint8_t)((ce.atribute & ~A_DUBLA_LATIME) | A_JUMATATE_DREAPTA);
				dr.cod = 0x20;
				dr.mozaic = 0;
				c++;
			}
		}
		return are_dubla;
	}

	void randGol(Celula *iesire)
	{
		for (int c = 0; c < COLOANE; c++)
		{
			iesire[c].cod = 0x20;
			iesire[c].mozaic = 0;
			iesire[c].fata = 7;
			iesire[c].fundal = 0;
			iesire[c].atribute = 0;
		}
	}

	/* X/26 la nivelul 1.5: pozitia activa, literele G0 cu semn si literele G2 */
	void aplicaX26(const Subpagina &sp, Celula iesire[RANDURI][COLOANE], int subset)
	{
		int rand = -1, col = -1;
		for (size_t k = 0; k < sp.x26.size(); k++)
		{
			uint32_t t = sp.x26[k];
			if (t == 0xFFFFFFFFu)
				continue;
			int adresa = t & 0x3F, mod = (t >> 6) & 0x1F, date = (t >> 11) & 0x7F;
			if (adresa >= 40)
			{
				if (mod == 0x1F)
					return;          /* sfarsitul tripletilor */
				if (mod == 0x04)
				{
					rand = adresa == 40 ? 24 : adresa - 40;
					col = date < 40 ? date : -1;
				}
				else if (mod == 0x07 && adresa == 63)
				{
					rand = 0;
					col = date < 40 ? date : -1;
				}
				continue;
			}
			col = adresa;
			if (rand < 0 || rand >= RANDURI)
				continue;
			Celula &ce = iesire[rand][col];
			if (ce.atribute & (A_JUMATATE_JOS | A_JUMATATE_DREAPTA))
				continue;
			uint32_t nou = 0;
			if (mod == 0x0F)
			{
				if (date >= 0x20)
					nou = G2_LATIN[date - 0x20];
			}
			else if (mod == 0x09)
			{
				if (date >= 0x20)
					nou = date == 0x7F ? 0x25A0 : literaG0(date, subset);
			}
			else if (mod >= 0x10)
			{
				int semn = mod & 0xF;
				if (date >= 0x20)
				{
					if (semn == 0 && date == 0x2A)
						nou = '@';
					else if (semn == 0)
						nou = literaG0(date, subset);
					else
						nou = cuSemn((uint32_t)date, semn);
				}
				else if (semn && ce.cod < 0x80)
					nou = cuSemn(ce.cod, semn);   /* fara litera: semnul pus pe litera deja de acolo */
			}
			if (nou)
			{
				ce.cod = nou;
				ce.mozaic = 0;
			}
		}
	}
}

void randeaza(const Colector &col, const Subpagina *sp, int pagina, const char *stare, const uint8_t *antet,
	uint16_t antet_control, Celula iesire[RANDURI][COLOANE])
{
	for (int r = 0; r < RANDURI; r++)
		randGol(iesire[r]);
	int magazie = (pagina >> 8) & 0xF;
	if (magazie < 1 || magazie > 8)
		magazie = 8;
	uint16_t control = sp ? sp->control : antet_control;

	/* setul national: X/28/0 al paginii, altfel M/29/0 al magaziei, altfel antetul (grupa 0) */
	/* C12 e bitul cel mai semnificativ al optiunii, C14 cel mai putin (tabelul 32: germana = C14) */
	int optiune = (((control >> 12) & 1) << 2) | (((control >> 13) & 1) << 1) | ((control >> 14) & 1);
	int desemnare = optiune, desemnare2 = -1;
	uint32_t t[2];
	if (sp && sp->are_x28 && (sp->x28[0] & 0x7F) == 0)
	{
		desemnare = (sp->x28[0] >> 7) & 0x7F;
		desemnare2 = (int)(((sp->x28[1] & 7) << 4) | ((sp->x28[0] >> 14) & 0xF));
	}
	else if (col.m29(magazie, t) && (t[0] & 0xF) == 0)
	{
		desemnare = (t[0] >> 7) & 0x7F;
		desemnare2 = (int)(((t[1] & 7) << 4) | ((t[0] >> 14) & 0xF));
	}
	int subset = subsetDin(desemnare);
	int subset2 = desemnare2 >= 0 ? subsetDin(desemnare2) : subset;

	/* antetul: coloanele 0-7 sunt starea data de ecran; 8-39 ale paginii, cu ceasul (32-39) din ultimul antet */
	uint8_t rand0[COLOANE];
	for (int c = 0; c < COLOANE; c++)
		rand0[c] = 0x20 | 0x80;
	bool fara_antet = sp && (sp->control & C7_FARA_ANTET);
	if (!fara_antet)
	{
		if (sp && (sp->randuri & 1))
		{
			memcpy(rand0 + 8, sp->text[0] + 8, 32);
			if (antet)
				memcpy(rand0 + 32, antet + 24, 8);
		}
		else if (antet)
			memcpy(rand0 + 8, antet, 32);
	}
	randeazaRand(rand0, subset, subset2, 8, iesire[0], false);
	for (int c = 0; c < 8; c++)
	{
		Celula &ce = iesire[0][c];
		ce.cod = (stare && c < (int)strlen(stare)) ? (uint32_t)(uint8_t)stare[c] : 0x20;
		if (ce.cod < 0x20 || ce.cod > 0x7E)
			ce.cod = 0x20;
		ce.mozaic = 0;
		ce.fata = 7;
		ce.fundal = 0;
		ce.atribute = 0;
	}
	if (!sp || (sp->control & C10_FARA_AFISARE))
		return;

	/* corpul */
	for (int r = 1; r < RANDURI; r++)
	{
		if (!((sp->randuri >> r) & 1))
			continue;
		bool dubla = randeazaRand(sp->text[r], subset, subset2, 0, iesire[r], r <= 22);
		if (dubla && r + 1 < RANDURI)
		{
			/* randul de dedesubt nu se arata: fundalul de sus coboara, iar sub literele duble e jumatatea lor */
			for (int c = 0; c < COLOANE; c++)
			{
				Celula &jos = iesire[r + 1][c];
				const Celula &sus = iesire[r][c];
				jos.cod = 0x20;
				jos.mozaic = 0;
				jos.fata = sus.fata;
				jos.fundal = sus.fundal;
				jos.atribute = (sus.atribute & A_DUBLA_INALTIME) ? (uint8_t)A_JUMATATE_JOS : 0;
				if (sus.atribute & A_JUMATATE_DREAPTA)
					jos.atribute = A_JUMATATE_JOS;
			}
			r++;
		}
	}
	aplicaX26(*sp, iesire, subset);
}

void legaturiZecimale(const Subpagina &sp, int iesire[LEGATURI])
{
	for (int k = 0; k < LEGATURI; k++)
		iesire[k] = sp.are_legaturi ? zecimalDinPagina(sp.legaturi[k]) : 0;
}

/* ------------------------------------------------------------------ compunerea */

Aspect::Aspect()
	: l(36), i(42), peste(false), hd(false), cu_contur(false), cu_umbra(false), relief(false), contur(2), alfa_fundal(208),
	  stinge_intermitente(false), arata_ascuns(false)
{
}

uint32_t culoare(int index)
{
	static const uint32_t PALETA[8] = { 0x000000, 0xFF0000, 0x00FF00, 0xFFFF00, 0x0000FF, 0xFF00FF, 0x00FFFF, 0xFFFFFF };
	return PALETA[index & 7];
}

namespace
{
	/* x / 255 fara impartire, exact pentru 0 <= x <= 66047 (verificat pe toate valorile) */
	inline int div255(int x)
	{
		return (int)(((uint32_t)x * 0x8081u) >> 23);
	}

	inline uint32_t peste(uint32_t jos, uint32_t rgb, int alfa)
	{
		if (alfa <= 0)
			return jos;
		if (alfa >= 255)
			return 0xFF000000u | rgb;
		int ja = (int)(jos >> 24);
		int sr = (int)((rgb >> 16) & 0xFF), sg = (int)((rgb >> 8) & 0xFF), sb = (int)(rgb & 0xFF);
		int jr = (int)((jos >> 16) & 0xFF), jg = (int)((jos >> 8) & 0xFF), jb = (int)(jos & 0xFF);
		if (ja == 255)
		{
			int r = div255(sr * alfa + jr * (255 - alfa) + 127);
			int g = div255(sg * alfa + jg * (255 - alfa) + 127);
			int b = div255(sb * alfa + jb * (255 - alfa) + 127);
			return 0xFF000000u | (uint32_t)(r << 16) | (uint32_t)(g << 8) | (uint32_t)b;
		}
		int jos_ramas = div255(ja * (255 - alfa));
		int oa = alfa + jos_ramas;
		if (oa <= 0)
			return 0;
		int r = (sr * alfa + jr * jos_ramas + oa / 2) / oa;
		int g = (sg * alfa + jg * jos_ramas + oa / 2) / oa;
		int b = (sb * alfa + jb * jos_ramas + oa / 2) / oa;
		return ((uint32_t)oa << 24) | (uint32_t)(r << 16) | (uint32_t)(g << 8) | (uint32_t)b;
	}

	void umple(std::vector<uint8_t> &acop, std::vector<uint8_t> &fata, int W, int H, int x0, int y0, int x1, int y1,
		uint8_t culoarea, uint8_t acoperirea)
	{
		if (x0 < 0) x0 = 0;
		if (y0 < 0) y0 = 0;
		if (x1 > W) x1 = W;
		if (y1 > H) y1 = H;
		for (int y = y0; y < y1; y++)
		{
			memset(&acop[(size_t)y * W + x0], acoperirea, x1 > x0 ? (size_t)(x1 - x0) : 0);
			memset(&fata[(size_t)y * W + x0], culoarea, x1 > x0 ? (size_t)(x1 - x0) : 0);
		}
	}

	/* randul are numai zerouri */
	inline bool gol(const uint8_t *s, int n)
	{
		int k = 0;
		for (; k + 8 <= n; k += 8)
		{
			uint64_t v;
			memcpy(&v, s + k, 8);
			if (v)
				return false;
		}
		for (; k < n; k++)
			if (s[k])
				return false;
		return true;
	}

	/* maximul pe o fereastra de 2r+1, pe orizontala si apoi pe verticala (conturul). Randurile fara nimic se sar (iesirea
	   ramane 0 acolo unde nicio intrare din fereastra nu are nimic); pe vertical se lucreaza rand cu rand. */
	void lateste(const std::vector<uint8_t> &in, std::vector<uint8_t> &out, int W, int H, int r)
	{
		std::vector<uint8_t> tmp((size_t)W * H, 0);
		std::vector<char> are(H, 0);
		for (int y = 0; y < H; y++)
		{
			const uint8_t *s = &in[(size_t)y * W];
			if (gol(s, W))
				continue;
			are[y] = 1;
			uint8_t *d = &tmp[(size_t)y * W];
			int x0 = r < W ? r : W, x1 = W - r > x0 ? W - r : x0;    /* [x0, x1): fereastra intreaga in rand */
			for (int x = 0; x < W; x++)
			{
				if (x == x0)
				{
					/* mijlocul randului, fara margini de verificat (r = 1 si 2, conturul obisnuit, pe scurt) */
					if (r == 1)
						for (; x < x1; x++)
						{
							if (!(x & 7) && x + 8 + r <= W && gol(s + x - r, 8 + 2 * r))
							{
								x += 7;     /* 8 pixeli fara nimic in fereastra: raman 0 */
								continue;
							}
							uint8_t m = s[x - 1] > s[x] ? s[x - 1] : s[x];
							d[x] = s[x + 1] > m ? s[x + 1] : m;
						}
					else if (r == 2)
						for (; x < x1; x++)
						{
							if (!(x & 7) && x + 8 + r <= W && gol(s + x - r, 8 + 2 * r))
							{
								x += 7;
								continue;
							}
							uint8_t m = s[x - 2] > s[x - 1] ? s[x - 2] : s[x - 1], n = s[x] > s[x + 1] ? s[x] : s[x + 1];
							m = m > n ? m : n;
							d[x] = s[x + 2] > m ? s[x + 2] : m;
						}
					else
						for (; x < x1; x++)
						{
							uint8_t m = 0;
							for (int k = x - r; k <= x + r; k++)
								m = s[k] > m ? s[k] : m;
							d[x] = m;
						}
					if (x >= W)
						break;
				}
				uint8_t m = 0;
				int a = x - r < 0 ? 0 : x - r, b = x + r >= W ? W - 1 : x + r;
				for (int k = a; k <= b; k++)
					m = s[k] > m ? s[k] : m;
				d[x] = m;
			}
		}
		out.assign((size_t)W * H, 0);
		for (int y = 0; y < H; y++)
		{
			int a = y - r < 0 ? 0 : y - r, b = y + r >= H ? H - 1 : y + r;
			uint8_t *d = &out[(size_t)y * W];
			for (int k = a; k <= b; k++)
			{
				if (!are[k])
					continue;
				const uint8_t *s = &tmp[(size_t)k * W];
				int x = 0;
				for (; x + 8 <= W; x += 8)
				{
					uint64_t v;
					memcpy(&v, s + x, 8);
					if (!v)
						continue;
					for (int q = x; q < x + 8; q++)
						d[q] = s[q] > d[q] ? s[q] : d[q];
				}
				for (; x < W; x++)
					d[x] = s[x] > d[x] ? s[x] : d[x];
			}
		}
	}
}

namespace
{
	/* bloc separat HD: dreptunghi cu colturi rotunde, cu margine neteda */
	void blocRotund(std::vector<uint8_t> &acop, std::vector<uint8_t> &fata, int W, int H, float bx0, float by0,
		float bx1, float by1, uint8_t culoarea, int acoperirea)
	{
		float cx = (bx0 + bx1) * 0.5f, cy = (by0 + by1) * 0.5f, hw = (bx1 - bx0) * 0.5f, hh = (by1 - by0) * 0.5f;
		float raza = (hw < hh ? hw : hh) * 0.6f;
		int x0 = (int)bx0 - 1, x1 = (int)bx1 + 1, y0 = (int)by0 - 1, y1 = (int)by1 + 1;
		if (x0 < 0) x0 = 0;
		if (y0 < 0) y0 = 0;
		if (x1 > W) x1 = W;
		if (y1 > H) y1 = H;
		for (int y = y0; y < y1; y++)
			for (int x = x0; x < x1; x++)
			{
				float dx = fabsf(x + 0.5f - cx) - (hw - raza), dy = fabsf(y + 0.5f - cy) - (hh - raza);
				float ex = dx > 0 ? dx : 0, ey = dy > 0 ? dy : 0;
				float d = sqrtf(ex * ex + ey * ey) - raza;
				float acc = 0.5f - d;
				if (acc <= 0)
					continue;
				int v = (int)((acc > 1 ? 1 : acc) * acoperirea + 0.5f);
				size_t p = (size_t)y * W + x;
				if (v > acop[p])
				{
					acop[p] = (uint8_t)v;
					fata[p] = culoarea;
				}
			}
	}

	/* suma[x] += semn * s[x], sarind bucatile de 8 fara nimic */
	inline void adunaRand(int *suma, const uint8_t *s, int W, int semn)
	{
		int x = 0;
		for (; x + 8 <= W; x += 8)
		{
			uint64_t v;
			memcpy(&v, s + x, 8);
			if (!v)
				continue;
			for (int q = x; q < x + 8; q++)
				suma[q] += semn * s[q];
		}
		for (; x < W; x++)
			suma[x] += semn * s[x];
	}

	/* estompare cu o fereastra de 2r+1 (medie, rotunjita in jos), pe orizontala si pe verticala. Impartirea la 2r+1 e
	   o inmultire (exacta pentru sume de cel mult 255 x 63, verificat pe toate valorile); verticala merge rand cu rand,
	   cu o suma pe fiecare coloana; randurile fara nimic se sar. */
	void estompeaza(std::vector<uint8_t> &v, int W, int H, int r)
	{
		std::vector<uint8_t> tmp((size_t)W * H, 0);
		std::vector<char> are(H, 0);
		const int n = 2 * r + 1;
		const uint32_t inv = (1u << 20) / (uint32_t)n + 1;
		const bool repede = n <= 63;
		for (int y = 0; y < H; y++)
		{
			const uint8_t *s = &v[(size_t)y * W];
			if (gol(s, W))
				continue;
			are[y] = 1;
			uint8_t *d = &tmp[(size_t)y * W];
			int suma = 0;
			for (int k = -r; k <= r; k++)
				suma += s[k < 0 ? 0 : (k >= W ? W - 1 : k)];
			for (int x = 0; x < W; x++)
			{
				if (!suma && x >= r && x + r + 8 < W && gol(s + x + r + 1, 8))
				{
					x += 7;         /* fereastra si urmatorii 8 fara nimic: iesirea ramane 0, suma ramane 0 */
					continue;
				}
				d[x] = (uint8_t)(repede ? (((uint32_t)suma * inv) >> 20) : (uint32_t)(suma / n));
				int iese = x - r, intra = x + r + 1;
				suma += s[intra >= W ? W - 1 : intra] - s[iese < 0 ? 0 : iese];
			}
		}
		std::vector<int> suma(W, 0);
		int active = 0;     /* cate randuri cu ceva sunt in fereastra */
		for (int k = -r; k <= r; k++)
		{
			int kk = k < 0 ? 0 : (k >= H ? H - 1 : k);
			if (!are[kk])
				continue;
			active++;
			adunaRand(&suma[0], &tmp[(size_t)kk * W], W, 1);
		}
		for (int y = 0; y < H; y++)
		{
			uint8_t *d = &v[(size_t)y * W];
			if (active)
			{
				for (int x = 0; x < W; x++)
					d[x] = (uint8_t)(repede ? (((uint32_t)suma[x] * inv) >> 20) : (uint32_t)(suma[x] / n));
			}
			else
				memset(d, 0, (size_t)W);
			int iese = y - r, intra = y + r + 1;
			iese = iese < 0 ? 0 : iese;
			intra = intra >= H ? H - 1 : intra;
			if (are[intra])
			{
				adunaRand(&suma[0], &tmp[(size_t)intra * W], W, 1);
				active++;
			}
			if (are[iese])
			{
				adunaRand(&suma[0], &tmp[(size_t)iese * W], W, -1);
				active--;
			}
		}
	}
}

/* ------------------------------------------------------------------ HD: stratul netezit al paginii */

/*
 * Teletextul neted (intern: hd). Fundalurile celulelor si mozaicul legat fac o imagine de 80 x 75 de
 * sextante (2 x 3 pe celula), cu o culoare pe sextant. O netezire facuta pe celule, sau numai pe mozaic, lasa valuri la
 * fiecare treapta si rotunjeste formele acolo unde ele continua in fundalul randului vecin. Aici:
 *  1. granitele dintre culori se urmaresc pe toata grila, ca lanturi de laturi de sextant intre doua culori (in afara
 *     paginii e culoarea 0, ca pe ecran); un lant se opreste unde se intalnesc trei culori (acolo ramane fix). Fiecare
 *     lant se netezeste o singura data, iar curba lui e granita pentru ambele culori: nimic nu ramane neacoperit, nimic
 *     nu se acopera de doua ori;
 *  2. pe un lant, fugile (laturile drepte facute din sextante) sunt trepte (capetele cotesc in sensuri opuse: scara
 *     merge mai departe) sau laturi (capetele cotesc in acelasi sens: un colt, capatul unei linii). Intr-o scara (cel
 *     putin trei trepte la rand, sau doua scurte), o treapta de cel mult TREAPTA_LUNGA sextante devine un singur punct,
 *     mijlocul ei: o scara cu trepte egale devine o dreapta oblica, una cu trepte care variaza o curba lina. O treapta
 *     singura, sau doua lungi (piciorul unui T sub bara), sunt pasi adevarati ai formei si raman colturi. Laturile
 *     raman drepte, continue peste granitele dintre randuri si coloane; capatul lor spre o scara se taie cat jumatate
 *     din treapta scarii (dreapta scarii prelungita), iar doua laturi care se intalnesc fac un colt real, rotunjit cu
 *     un arc mic (acelasi arc e racordul concav al culorii vecine). Celelalte varfuri ale poligonului se racordeaza cu
 *     arcul cel mai mare care incape (cel mult jumatate din laturile vecine);
 *  3. se netezesc numai cotiturile care ating un sextant aprins de mozaic legat: cutiile de text (numai fundal) raman cu
 *     colturile drepte, ca la emisie, iar o forma facuta din fundal pe un rand si din mozaic pe urmatorul continua drept;
 *  4. desenul: fiecare sextant cu culoarea lui, la aceleasi margini de pixel ca la clasic, apoi, pentru fiecare bucata in
 *     care curba se departeaza de trepte, numai diferenta: aria cu semn a conturului inchis (curba inainte, treptele
 *     inapoi), acumulata pe randuri de pixeli cu acoperirea exacta a fiecarui pixel, inmultita cu saltul de culoare
 *     (stanga - dreapta). Laturile drepte nu costa nimic;
 *  5. formele se tin minte dupa amprenta grilei: antetul (la fiecare secunda, pentru ceas), corpul si faza stinsa a
 *     intermitentelor folosesc acelasi calcul. Memoria e una singura: compunerea HD merge numai pe firul principal.
 * Aceeasi logica e scrisa si in desenatorul paginii web (teletext_web.py, ttxStratHd), comparata pixel cu pixel.
 */
namespace
{
	enum
	{
		GW = 2 * COLOANE,           /* sextante pe orizontala */
		GH = 3 * RANDURI,           /* sextante pe verticala */
		NEGRU_OPAC = 8,             /* peste imagine: mozaicul negru (fundalul negru e transparent) */
		S_APRINS = 1,               /* sextant aprins al unui mozaic legat sau al unui bloc plin */
		TREAPTA_LUNGA = 6,          /* o treapta mai lunga (in sextante) ramane latura dreapta */
		TREAPTA_SCURTA = 2          /* doua trepte la rand fac o scara numai daca au cel mult atat */
	};

	/* varfurile poligonului: fix (capat de lant, cotitura care nu se netezeste), colt (doua laturi: arcul de raza data),
	   neted (arcul cel mai mare care incape) */
	enum { V_FIX, V_COLT, V_NETED };

	/* cat se poate departa (pixeli) un punct al unei scari de dreapta care il inlocuieste */
	const double SIMPLIFICARE_PX = 0.4;

	const int DX[4] = { 1, 0, -1, 0 }, DY[4] = { 0, 1, 0, -1 };     /* E, S, V, N */

	struct GrilaHd
	{
		uint8_t c[GH][GW];          /* culoarea vazuta: 0..7, NEGRU_OPAC */
		uint8_t m[GH][GW];          /* S_APRINS */
	};

	struct PunctHd
	{
		double x, y;
		PunctHd() : x(0), y(0) {}
		PunctHd(double x_, double y_) : x(x_), y(y_) {}
	};

	/* o bucata de diferenta: conturul inchis (curba, apoi treptele inapoi), in pixelii paginii intregi */
	struct BucataHd
	{
		std::vector<PunctHd> p;
		double j[4];                /* saltul de culoare stanga - dreapta, RGBA premultiplicat (0..255) */
		int n1, n2;                 /* relieful: saltul de nivel stanga - dreapta (-1, 0, 1) pe mastile "nivel >= 1" si
		                               "nivel 2" */
		double x0, y0, x1, y1;
	};

	struct FormeHd
	{
		uint64_t cheie;
		bool gata;
		std::vector<BucataHd> bucati;
		uint8_t niv[GH][GW];        /* nivelul regiunii fiecarui sextant (relieful, vezi niveluriHd) */
		FormeHd() : cheie(0), gata(false) {}
	};

	/* marginile de pixel ale sextantelor, aceleasi ca la clasic (xs si ys din compune, si pentru celulele duble) */
	struct HartaHd
	{
		int x[GW + 1], y[GH + 1];
		explicit HartaHd(const Aspect &a)
		{
			for (int g = 0; g <= GW; g++)
				x[g] = (g / 2) * a.l + ((g % 2) ? (a.l + 1) / 2 : 0);
			for (int g = 0; g <= GH; g++)
			{
				int k = g % 3;
				y[g] = (g / 3) * a.i + (k == 0 ? 0 : (k == 1 ? (a.i + 1) / 3 : (2 * a.i + 1) / 3));
			}
		}
		double px(double g) const
		{
			int k = (int)floor(g);
			if (k < 0)
				k = 0;
			if (k > GW - 1)
				k = GW - 1;
			return x[k] + (g - k) * (x[k + 1] - x[k]);
		}
		double py(double g) const
		{
			int k = (int)floor(g);
			if (k < 0)
				k = 0;
			if (k > GH - 1)
				k = GH - 1;
			return y[k] + (g - k) * (y[k + 1] - y[k]);
		}
	};

	/* culoarea unui sextant ca RGBA premultiplicat (0..255) si ca pixel ARGB */
	void rgbaHd(int v, const Aspect &a, double o[4])
	{
		uint32_t rgb = v == NEGRU_OPAC ? 0 : culoare(v);
		double al = !a.peste ? 255.0 : (v == 0 ? 0.0 : (double)a.alfa_fundal);
		o[0] = ((rgb >> 16) & 0xFF) * al / 255.0;
		o[1] = ((rgb >> 8) & 0xFF) * al / 255.0;
		o[2] = (rgb & 0xFF) * al / 255.0;
		o[3] = al;
	}

	uint32_t argbHd(int v, const Aspect &a)
	{
		if (!a.peste)
			return 0xFF000000u | culoare(v);
		if (v == 0)
			return 0;
		return ((uint32_t)a.alfa_fundal << 24) | (v == NEGRU_OPAC ? 0 : culoare(v));
	}

	/* grila: fundalul fiecarei celule, apoi sextantele mozaicului legat vazut (si blocul plin din X/26); intoarce true
	   daca are sextante aprinse (altfel nu e nimic de netezit) */
	bool faGrilaHd(const Celula pagina[RANDURI][COLOANE], const Aspect &a, GrilaHd &g)
	{
		for (int r = 0; r < RANDURI; r++)
			for (int c = 0; c < COLOANE; c++)
			{
				uint8_t f = (uint8_t)(pagina[r][c].fundal & 7);
				for (int k = 0; k < 3; k++)
				{
					g.c[3 * r + k][2 * c] = g.c[3 * r + k][2 * c + 1] = f;
					g.m[3 * r + k][2 * c] = g.m[3 * r + k][2 * c + 1] = 0;
				}
			}
		bool aprinse = false;
		for (int r = 0; r < RANDURI; r++)
			for (int c = 0; c < COLOANE; c++)
			{
				const Celula &ce = pagina[r][c];
				if (ce.atribute & (A_JUMATATE_JOS | A_JUMATATE_DREAPTA))
					continue;
				if ((ce.atribute & A_INTERMITENT) && a.stinge_intermitente)
					continue;
				if ((ce.atribute & A_ASCUNS) && !a.arata_ascuns)
					continue;
				int s;
				if (ce.mozaic)
				{
					if (ce.atribute & A_SEPARAT)
						continue;
					s = ce.mozaic & 0x3F;
				}
				else if (ce.cod == 0x25A0)
					s = 0x3F;               /* blocul plin din X/26 (G0 0x7F) se lipeste de mozaic */
				else
					continue;
				if (!s)
					continue;
				aprinse = true;
				bool dl = (ce.atribute & A_DUBLA_LATIME) != 0, di = (ce.atribute & A_DUBLA_INALTIME) != 0;
				uint8_t fata = (uint8_t)((a.peste && (ce.fata & 7) == 0) ? NEGRU_OPAC : (ce.fata & 7));
				uint8_t fundal = (uint8_t)(ce.fundal & 7);
				for (int k = 0; k < 6; k++)
				{
					bool aprins = ((s >> k) & 1) != 0;
					int cx = k & 1, cy = k >> 1;
					int gx0 = 2 * c + (dl ? 2 * cx : cx), gx1 = gx0 + (dl ? 2 : 1);
					int gy0 = 3 * r + (di ? 2 * cy : cy), gy1 = gy0 + (di ? 2 : 1);
					for (int gy = gy0; gy < gy1 && gy < GH; gy++)
						for (int gx = gx0; gx < gx1 && gx < GW; gx++)
						{
							g.c[gy][gx] = aprins ? fata : fundal;
							g.m[gy][gx] = aprins ? (uint8_t)S_APRINS : (uint8_t)0;
						}
				}
			}
		return aprinse;
	}

	uint64_t amprentaHd(const GrilaHd &g, const Aspect &a)
	{
		uint64_t h = 1469598103934665603ull;
		const uint8_t *p = &g.c[0][0];
		for (size_t k = 0; k < sizeof(g.c); k++)
			h = (h ^ p[k]) * 1099511628211ull;
		p = &g.m[0][0];
		for (size_t k = 0; k < sizeof(g.m); k++)
			h = (h ^ p[k]) * 1099511628211ull;
		const uint32_t extra[4] = { (uint32_t)a.l, (uint32_t)a.i, a.peste ? 1u : 0u, (uint32_t)a.alfa_fundal };
		for (int k = 0; k < 4; k++)
			h = (h ^ extra[k]) * 1099511628211ull;
		return h;
	}

	/* relieful: nivelul fiecarui sextant, 2 = mozaic aprins (sau bloc plin) colorat, 1 = alta
	   culoare decat negrul sau transparentul, 0 = negru sau transparent (si mozaicul negru: o forma neagra nu are fata
	   laterala, s-ar ingrosa numai). Apoi nivelul regiunii: cel mai mare din regiunea de aceeasi culoare (vecinii pe cele
	   8 directii, ca un lant care trece printr-o tabla de sah), pus pe toate sextantele ei. Asa o granita de nivel e
	   intotdeauna o granita de culoare: mastile reliefului ies din aceleasi lanturi si aceleasi curbe ca stratul, iar o
	   forma lipita de una de aceeasi culoare nu are fata laterala intre ele (nu se vede granita) */
	void niveluriHd(const GrilaHd &g, uint8_t niv[GH][GW])
	{
		static const int VX[8] = { 1, -1, 0, 0, 1, 1, -1, -1 }, VY[8] = { 0, 0, 1, -1, 1, -1, 1, -1 };
		std::vector<int> regiune, stiva;
		std::vector<uint8_t> vazut((size_t)GH * GW, 0);
		for (int y0 = 0; y0 < GH; y0++)
			for (int x0 = 0; x0 < GW; x0++)
			{
				if (vazut[(size_t)y0 * GW + x0])
					continue;
				const uint8_t c = g.c[y0][x0];
				regiune.clear();
				stiva.assign(1, y0 * GW + x0);
				vazut[(size_t)y0 * GW + x0] = 1;
				int maxim = 0;
				while (!stiva.empty())
				{
					int p = stiva.back();
					stiva.pop_back();
					regiune.push_back(p);
					int x = p % GW, y = p / GW;
					int n = (c == 0 || c == NEGRU_OPAC) ? 0 : ((g.m[y][x] & S_APRINS) ? 2 : 1);
					if (n > maxim)
						maxim = n;
					for (int d = 0; d < 8; d++)
					{
						int xx = x + VX[d], yy = y + VY[d];
						if (xx < 0 || xx >= GW || yy < 0 || yy >= GH || vazut[(size_t)yy * GW + xx] || g.c[yy][xx] != c)
							continue;
						vazut[(size_t)yy * GW + xx] = 1;
						stiva.push_back(yy * GW + xx);
					}
				}
				for (size_t k = 0; k < regiune.size(); k++)
					niv[regiune[k] / GW][regiune[k] % GW] = (uint8_t)maxim;
			}
	}

	/* un lant: varfurile grilei (x + y * (GW + 1)), deschis (capetele fixe) sau inchis */
	struct LantHd
	{
		std::vector<int> v;
		bool inchis;
		uint8_t st, dr;             /* culorile din stanga si din dreapta sensului de mers (y creste in jos) */
		int cst, cdr;               /* sextantele (y * GW + x) din stanga si din dreapta primei laturi; -1 = in afara
		                               paginii (pentru nivelul reliefului) */
		LantHd() : inchis(false), st(0), dr(0), cst(-1), cdr(-1) {}
	};

	/* urmarirea granitelor: varfurile grilei sunt colturile sextantelor, (0..GW) x (0..GH); latura de la varful (x, y)
	   pe directia d exista cand cele doua sextante de o parte si de alta au culori diferite. In afara paginii e negru
	   (pe tot ecranul) sau transparent (peste imagine), adica culoarea 0, ca pe ecran: o forma care ajunge la marginea
	   paginii are acolo o granita ca oricare alta (coltul unei casete lipite de margine se rotunjeste ca cel din
	   cealalta parte) */
	class UrmaritorHd
	{
	public:
		explicit UrmaritorHd(const GrilaHd &g) : m_g(g)
		{
			memset(m_h, 0, sizeof(m_h));
			memset(m_v, 0, sizeof(m_v));
		}

		/* toate lanturile: intai cele cu capete (de la varfurile unde se opresc), apoi buclele */
		void lanturi(std::vector<LantHd> &iesire)
		{
			LantHd l;
			for (int y = 0; y <= GH; y++)
				for (int x = 0; x <= GW; x++)
				{
					bool a_legat;
					if (tip(x, y, a_legat) != 0)
						continue;
					for (int d = 0; d < 4; d++)
						if (latura(x, y, d) && !parcursa(x, y, d))
						{
							urmareste(x, y, d, l);
							iesire.push_back(l);
						}
				}
			for (int y = 0; y <= GH; y++)
				for (int x = 0; x < GW; x++)
					if (latura(x, y, 0) && !parcursa(x, y, 0))
					{
						urmareste(x, y, 0, l);
						iesire.push_back(l);
					}
			for (int y = 0; y < GH; y++)
				for (int x = 0; x <= GW; x++)
					if (latura(x, y, 1) && !parcursa(x, y, 1))
					{
						urmareste(x, y, 1, l);
						iesire.push_back(l);
					}
		}

		/* un sextant aprins de mozaic in jurul varfului: cotitura de aici se netezeste */
		bool netezit(int x, int y) const
		{
			for (int yy = y - 1; yy <= y; yy++)
				for (int xx = x - 1; xx <= x; xx++)
					if (yy >= 0 && yy < GH && xx >= 0 && xx < GW && (m_g.m[yy][xx] & S_APRINS))
						return true;
			return false;
		}

	private:
		const GrilaHd &m_g;
		uint8_t m_h[GH + 1][GW];    /* laturile orizontale parcurse: de la (x, y) la (x + 1, y) */
		uint8_t m_v[GH][GW + 1];    /* cele verticale: de la (x, y) la (x, y + 1) */

		/* culoarea sextantului (x, y); in afara paginii 0 */
		uint8_t cul(int x, int y) const
		{
			return (x >= 0 && x < GW && y >= 0 && y < GH) ? m_g.c[y][x] : 0;
		}

		bool aprins(int x, int y) const
		{
			return x >= 0 && x < GW && y >= 0 && y < GH && (m_g.m[y][x] & S_APRINS);
		}

		bool latura(int x, int y, int d) const
		{
			switch (d)
			{
			case 0: return x < GW && cul(x, y - 1) != cul(x, y);
			case 1: return y < GH && cul(x - 1, y) != cul(x, y);
			case 2: return x >= 1 && cul(x - 1, y - 1) != cul(x - 1, y);
			default: return y >= 1 && cul(x - 1, y - 1) != cul(x, y - 1);
			}
		}

		/* numai pentru o latura care exista */
		uint8_t &parcursa(int x, int y, int d)
		{
			switch (d)
			{
			case 0: return m_h[y][x];
			case 1: return m_v[y][x];
			case 2: return m_h[y][x - 1];
			default: return m_v[y - 1][x];
			}
		}

		void culori(int x, int y, int d, uint8_t &st, uint8_t &dr) const
		{
			switch (d)
			{
			case 0: st = cul(x, y - 1); dr = cul(x, y); break;
			case 1: st = cul(x, y); dr = cul(x - 1, y); break;
			case 2: st = cul(x - 1, y); dr = cul(x - 1, y - 1); break;
			default: st = cul(x - 1, y - 1); dr = cul(x, y - 1); break;
			}
		}

		/* sextantul (x, y) ca indice, -1 in afara paginii */
		static int celula(int x, int y)
		{
			return (x >= 0 && x < GW && y >= 0 && y < GH) ? y * GW + x : -1;
		}

		/* sextantele de o parte si de alta a laturii, in aceeasi ordine ca culori() */
		void celule(int x, int y, int d, int &st, int &dr) const
		{
			switch (d)
			{
			case 0: st = celula(x, y - 1); dr = celula(x, y); break;
			case 1: st = celula(x, y); dr = celula(x - 1, y); break;
			case 2: st = celula(x - 1, y); dr = celula(x - 1, y - 1); break;
			default: st = celula(x - 1, y - 1); dr = celula(x, y - 1); break;
			}
		}

		/* 0 = lantul se opreste aici (marginea, trei culori), 1 = trece (doua laturi), 2 = tabla de sah (doua culori pe
		   diagonale); a_legat: la tabla de sah ramane legata diagonala NV-SE */
		int tip(int x, int y, bool &a_legat) const
		{
			int n = 0;
			for (int d = 0; d < 4; d++)
				n += latura(x, y, d) ? 1 : 0;
			a_legat = true;
			if (n == 2)
				return 1;
			if (n != 4)
				return 0;
			uint8_t nv = cul(x - 1, y - 1), ne = cul(x, y - 1), sv = cul(x - 1, y), se = cul(x, y);
			if (nv != se || ne != sv)
				return 0;
			bool fa = aprins(x - 1, y - 1) && aprins(x, y);
			bool fb = aprins(x, y - 1) && aprins(x - 1, y);
			if (fa != fb)
				a_legat = fa;   /* mozaicul aprins ramane legat */
			else
			{
				/* altfel culoarea mai rara in jur: o linie subtire ramane legata */
				int na = 0, nb = 0;
				for (int yy = y - 2; yy <= y + 1; yy++)
					for (int xx = x - 2; xx <= x + 1; xx++)
					{
						if (cul(xx, yy) == nv)
							na++;
						else if (cul(xx, yy) == ne)
							nb++;
					}
				a_legat = na <= nb;
			}
			return 2;
		}

		/* directia de plecare din varful (x, y), unde s-a ajuns mergand pe d; -1 = lantul se opreste */
		int urmatoarea(int x, int y, int d) const
		{
			int venit = (d + 2) & 3;
			bool a_legat;
			int t = tip(x, y, a_legat);
			if (t == 1)
			{
				for (int s = 0; s < 4; s++)
					if (s != venit && latura(x, y, s))
						return s;
				return -1;
			}
			if (t == 2)
			{
				/* NV-SE legat: perechile N-E si S-V (in jurul colturilor celeilalte culori); altfel N-V si E-S */
				static const int PERECHE_A[4] = { 3, 2, 1, 0 }, PERECHE_B[4] = { 1, 0, 3, 2 };
				return a_legat ? PERECHE_A[venit] : PERECHE_B[venit];
			}
			return -1;
		}

		void urmareste(int x0, int y0, int d0, LantHd &l)
		{
			l.v.clear();
			l.inchis = false;
			culori(x0, y0, d0, l.st, l.dr);
			celule(x0, y0, d0, l.cst, l.cdr);
			int x = x0, y = y0, d = d0;
			l.v.push_back(x + y * (GW + 1));
			for (;;)
			{
				parcursa(x, y, d) = 1;
				x += DX[d];
				y += DY[d];
				int nd = urmatoarea(x, y, d);
				if (nd < 0)
				{
					l.v.push_back(x + y * (GW + 1));
					return;
				}
				if (parcursa(x, y, nd))
				{
					l.inchis = true;    /* inapoi la primul varf */
					return;
				}
				l.v.push_back(x + y * (GW + 1));
				d = nd;
			}
		}
	};

	/* netezirea unui lant: poligonul, racordurile si bucatile de diferenta (vezi descrierea de mai sus) */
	class NetezitorHd
	{
	public:
		NetezitorHd(const HartaHd &h, const Aspect &a, std::vector<BucataHd> &iesire, const uint8_t (*niv)[GW])
			: m_h(h), m_a(a), m_iesire(iesire), m_niv(niv), m_n1(0), m_n2(0)
		{
			double sw = a.l * 0.5, sh = a.i / 3.0;
			m_raza = 0.5 * (sw < sh ? sw : sh);
		}

		void lant(const LantHd &l, const UrmaritorHd &u)
		{
			const int N = (int)l.v.size(), L1 = GW + 1;
			if (N < 2)
				return;
			m_inchis = l.inchis;
			std::vector<int> &v = m_varfuri;
			v.assign(l.v.begin(), l.v.end());
			if (m_inchis)
			{
				/* bucla incepe la o cotitura */
				int start = -1;
				for (int k = 0; k < N && start < 0; k++)
				{
					int a = v[(k + N - 1) % N], b = v[k], c = v[(k + 1) % N];
					if (b - a != c - b)
						start = k;
				}
				if (start < 0)
					return;
				std::rotate(v.begin(), v.begin() + start, v.end());
			}
			/* fugile */
			m_f.clear();
			int laturi = m_inchis ? N : N - 1;
			for (int k = 0; k < laturi; k++)
			{
				int a = v[k], b = v[(k + 1) % N];
				int dx = b % L1 - a % L1, dy = b / L1 - a / L1;
				if (!m_f.empty() && m_f.back().dx == dx && m_f.back().dy == dy)
					m_f.back().L++;
				else
				{
					Fuga f;
					f.x = a % L1;
					f.y = a / L1;
					f.dx = dx;
					f.dy = dy;
					f.L = 1;
					m_f.push_back(f);
				}
			}
			const int NF = (int)m_f.size();
			m_nf = NF;
			/* cotiturile: cotitura k e la capatul fugii k */
			m_sens.assign(NF, 0);
			m_net.assign(NF, 0);
			bool vreuna = false;
			for (int k = 0; k < NF; k++)
			{
				if (urm(k) < 0)
					continue;
				const Fuga &a = m_f[k], &b = m_f[urm(k)];
				m_sens[k] = a.dx * b.dy - a.dy * b.dx;
				m_net[k] = u.netezit(a.x + a.dx * a.L, a.y + a.dy * a.L) ? 1 : 0;
				if (m_net[k])
					vreuna = true;
			}
			if (!vreuna)
				return;
			/* treptele: capetele cotesc in sensuri opuse, cel mult TREAPTA_LUNGA sextante, si o scara: cel putin trei la
			   rand, sau doua scurte (de cel mult TREAPTA_SCURTA: coltul unei litere taiat cu un sextant). O treapta singura,
			   sau doua lungi (piciorul unui T sub bara), sunt pasi adevarati ai formei: colturi */
			std::vector<char> &zc = m_zc, &z = m_z;
			zc.assign(NF, 0);
			z.assign(NF, 0);
			int s0 = -1;            /* bucla se parcurge de la o fuga care nu e treapta (o scara nu trece peste ea) */
			for (int k = 0; k < NF; k++)
			{
				zc[k] = !inceputFix(k) && !sfarsitFix(k) && m_sens[prec(k)] != m_sens[k] && m_f[k].L <= TREAPTA_LUNGA;
				if (m_inchis && !zc[k] && s0 < 0)
					s0 = k;
			}
			if (s0 < 0)
				s0 = 0;
			for (int q = 0; q < NF;)
			{
				if (!zc[(s0 + q) % NF])
				{
					q++;
					continue;
				}
				int e = q, lung = 0;
				while (e < NF && zc[(s0 + e) % NF])
				{
					if (m_f[(s0 + e) % NF].L > lung)
						lung = m_f[(s0 + e) % NF].L;
					e++;
				}
				if (e - q >= 3 || (e - q == 2 && lung <= TREAPTA_SCURTA))
					for (int t = q; t < e; t++)
						z[(s0 + t) % NF] = 1;
				q = e;
			}
			/* laturile: cat se taie din capete spre o scara (jumatate din treapta scarii de aceeasi directie) */
			m_ci.assign(NF, 0.0);
			m_cs.assign(NF, 0.0);
			for (int k = 0; k < NF; k++)
			{
				if (z[k])
					continue;
				double a = 0, b = 0;
				if (!inceputFix(k) && z[prec(k)])
				{
					int pp = prec(prec(k));
					a = ((pp >= 0 && z[pp]) ? m_f[pp].L : 2) * 0.5;
				}
				if (!sfarsitFix(k) && z[urm(k)])
				{
					int nn = urm(urm(k));
					b = ((nn >= 0 && z[nn]) ? m_f[nn].L : 2) * 0.5;
				}
				if (a + b > m_f[k].L)
				{
					double s = m_f[k].L / (a + b);
					a *= s;
					b = m_f[k].L - a;
				}
				m_ci[k] = a;
				m_cs[k] = b;
			}
			/* poligonul, in ordinea lantului */
			m_p.clear();
			if (!m_inchis)
				pune(0, 0.0, V_FIX);
			for (int k = 0; k < NF; k++)
			{
				if (z[k])
					pune(k, m_f[k].L * 0.5, V_NETED);
				else
				{
					double a = m_ci[k], b = m_f[k].L - m_cs[k];
					if (a > 0)
						pune(k, a, V_NETED);
					if (m_cs[k] > 0 && b > a + 1e-9)
						pune(k, b, V_NETED);
				}
				if (urm(k) >= 0)
				{
					if (!m_net[k])
						pune(k, m_f[k].L, V_FIX);
					else if (!z[k] && !z[urm(k)])
						pune(k, m_f[k].L, V_COLT);
				}
			}
			if (!m_inchis)
				pune(NF - 1, m_f[NF - 1].L, V_FIX);
			simplifica();
			racordeaza();
			double s[4], d[4];
			rgbaHd(l.st, m_a, s);
			rgbaHd(l.dr, m_a, d);
			for (int k = 0; k < 4; k++)
				m_j[k] = s[k] - d[k];
			/* relieful: nivelurile regiunilor de o parte si de alta (aceleasi pe tot lantul, vezi niveluriHd) */
			int ns = l.cst < 0 ? 0 : m_niv[l.cst / GW][l.cst % GW], nd = l.cdr < 0 ? 0 : m_niv[l.cdr / GW][l.cdr % GW];
			m_n1 = (ns >= 1 ? 1 : 0) - (nd >= 1 ? 1 : 0);
			m_n2 = (ns >= 2 ? 1 : 0) - (nd >= 2 ? 1 : 0);
			bucati();
		}

	private:
		struct Fuga
		{
			int x, y, dx, dy, L;    /* inceputul (varf al grilei), directia, lungimea in sextante */
		};
		struct VarfHd
		{
			double gx, gy;          /* in grila */
			int fel;
			int fuga;               /* fuga pe care sta */
			bool la_capat;          /* la capatul fugii, deci si la inceputul celei urmatoare */
		};

		const HartaHd &m_h;
		const Aspect &m_a;
		std::vector<BucataHd> &m_iesire;
		const uint8_t (*m_niv)[GW];
		double m_raza;
		bool m_inchis;
		int m_nf;
		double m_j[4];
		int m_n1, m_n2;
		std::vector<int> m_varfuri;
		std::vector<Fuga> m_f;
		std::vector<int> m_sens;
		std::vector<char> m_net, m_zc, m_z, m_scos;
		std::vector<double> m_ci, m_cs;
		std::vector<VarfHd> m_p;
		std::vector<PunctHd> m_pp, m_in, m_out, m_arc, m_curba, m_trepte;
		std::vector<int> m_arc0, m_arc1;

		int prec(int k) const { return m_inchis ? (k + m_nf - 1) % m_nf : k - 1; }
		int urm(int k) const { return m_inchis ? (k + 1) % m_nf : (k + 1 < m_nf ? k + 1 : -1); }
		/* inceputul fugii: capatul lantului sau o cotitura care nu se netezeste */
		bool inceputFix(int k) const { int p = prec(k); return p < 0 || !m_net[p]; }
		bool sfarsitFix(int k) const { return urm(k) < 0 || !m_net[k]; }

		void pune(int k, double d, int fel)
		{
			VarfHd q;
			q.gx = m_f[k].x + m_f[k].dx * d;
			q.gy = m_f[k].y + m_f[k].dy * d;
			q.fel = fel;
			q.fuga = k;
			q.la_capat = d >= m_f[k].L;
			m_p.push_back(q);
		}

		PunctHd capat(int k) const
		{
			const Fuga &f = m_f[k];
			return PunctHd(m_h.x[f.x + f.dx * f.L], m_h.y[f.y + f.dy * f.L]);
		}

		/* punctele din mijlocul unei scari care stau pe aceeasi dreapta (cel mult SIMPLIFICARE_PX de ea) se scot: raman
		   numai cotiturile adevarate ale poligonului, iar racordurile lor au loc pe toata lungimea laturilor drepte.
		   Se scot numai varfuri netede care nu ating o latura asezata pe trepte. */
		void simplifica()
		{
			const int M = (int)m_p.size();
			if (M < 4)
				return;
			m_pp.resize(M);
			for (int j = 0; j < M; j++)
				m_pp[j] = PunctHd(m_h.px(m_p[j].gx), m_h.py(m_p[j].gy));
			std::vector<char> &scos = m_scos;
			scos.assign(M, 0);
			int capete = 0;
			for (int j = 0; j < M; j++)
			{
				int jp = m_inchis ? (j + M - 1) % M : j - 1, jn = m_inchis ? (j + 1) % M : j + 1;
				bool poate = jp >= 0 && jn < M && m_p[j].fel == V_NETED && !peTrepte(jp, j) && !peTrepte(j, jn);
				scos[j] = poate ? 1 : 0;      /* deocamdata: se poate scoate */
				if (!poate)
					capete++;
			}
			if (!capete)
				return;
			int start = 0;
			while (scos[start])
				start++;
			/* de la un varf pastrat, cat mai departe cat timp cele sarite raman langa dreapta */
			std::vector<char> pastrat(M, 0);
			int k = start, facuti = 0;
			pastrat[start] = 1;
			while (facuti < M)
			{
				int bun = (k + 1) % M, pas = 1;
				if (!m_inchis && k == M - 1)
					break;
				for (int m = 2; m < M; m++)
				{
					int t = (k + m) % M;
					if (!m_inchis && k + m >= M)
						break;
					if (!scos[(k + m - 1) % M])
						break;          /* varful dinainte de t trebuie pastrat */
					bool aproape = true;
					double ax = m_pp[k].x, ay = m_pp[k].y, bx = m_pp[t].x - ax, by = m_pp[t].y - ay;
					double lung = sqrt(bx * bx + by * by);
					if (lung < 1e-9)
						break;
					for (int q = 1; q < m && aproape; q++)
					{
						const PunctHd &p = m_pp[(k + q) % M];
						double d = ((p.x - ax) * by - (p.y - ay) * bx) / lung;
						aproape = d < SIMPLIFICARE_PX && d > -SIMPLIFICARE_PX;
					}
					if (!aproape)
						break;
					bun = t;
					pas = m;
					if (m_inchis && t == start)
						break;
				}
				facuti += pas;
				k = bun;
				if (m_inchis && k == start)
					break;
				pastrat[k] = 1;
			}
			std::vector<VarfHd> p;
			for (int j = 0; j < M; j++)
				if (pastrat[j])
					p.push_back(m_p[j]);
			m_p.swap(p);
		}

		/* racordurile: varful j se inlocuieste cu arcul (Bezier patratic) de la in[j] la out[j] */
		void racordeaza()
		{
			const int M = (int)m_p.size();
			m_pp.resize(M);
			m_in.resize(M);
			m_out.resize(M);
			m_arc0.assign(M, 0);
			m_arc1.assign(M, 0);
			m_arc.clear();
			for (int j = 0; j < M; j++)
				m_pp[j] = PunctHd(m_h.px(m_p[j].gx), m_h.py(m_p[j].gy));
			for (int j = 0; j < M; j++)
			{
				m_in[j] = m_out[j] = m_pp[j];
				m_arc0[j] = m_arc1[j] = (int)m_arc.size();
				if (m_p[j].fel == V_FIX)
					continue;
				int jp = m_inchis ? (j + M - 1) % M : j - 1, jn = m_inchis ? (j + 1) % M : j + 1;
				if (jp < 0 || jn >= M)
					continue;
				double ax = m_pp[j].x - m_pp[jp].x, ay = m_pp[j].y - m_pp[jp].y;
				double bx = m_pp[jn].x - m_pp[j].x, by = m_pp[jn].y - m_pp[j].y;
				double l1 = sqrt(ax * ax + ay * ay), l2 = sqrt(bx * bx + by * by);
				if (l1 < 1e-9 || l2 < 1e-9)
					continue;
				ax /= l1;
				ay /= l1;
				bx /= l2;
				by /= l2;
				double cosu = ax * bx + ay * by;
				if (cosu > 1.0 - 1e-12)
					continue;
				if (cosu < -1.0)
					cosu = -1.0;
				/* cat din fiecare latura vecina ia arcul: intre doua laturi oblice (varfuri ale unei scari care se curbeaza)
				   jumatate din fiecare latura, deci doua varfuri la rand se ating la mijlocul laturii dintre ele: curba lina
				   prin mijloacele laturilor. Unde o latura dreapta a formei (asezata pe trepte) intalneste alta latura, un
				   arc de raza mica, la fel pe ambele laturi: m_raza la un colt intre doua laturi drepte, dublu la trecerea
				   dintr-o latura dreapta intr-o scara (unghi mai deschis) */
				double t1 = l1 * 0.5, t2 = l2 * 0.5;
				bool p1 = peTrepte(jp, j), p2 = peTrepte(j, jn);
				if (m_p[j].fel == V_COLT || p1 || p2)
				{
					double t = t1 < t2 ? t1 : t2;
					if (cosu > -1.0 + 1e-12)
					{
						double raza = m_p[j].fel == V_COLT ? m_raza : 2 * m_raza;
						double tc = raza * sqrt((1.0 - cosu) / (1.0 + cosu));
						if (tc < t)
							t = tc;
					}
					t1 = t2 = t;
				}
				m_in[j] = PunctHd(m_pp[j].x - ax * t1, m_pp[j].y - ay * t1);
				m_out[j] = PunctHd(m_pp[j].x + bx * t2, m_pp[j].y + by * t2);
				double mx = (m_in[j].x + m_out[j].x) * 0.5 - m_pp[j].x, my = (m_in[j].y + m_out[j].y) * 0.5 - m_pp[j].y;
				int n = (int)ceil(sqrt(5.0 * sqrt(mx * mx + my * my)));
				if (n < 2)
					n = 2;
				if (n > 12)
					n = 12;
				for (int s = 1; s < n; s++)
				{
					double q = (double)s / n, w0 = (1 - q) * (1 - q), w1 = 2 * q * (1 - q), w2 = q * q;
					m_arc.push_back(PunctHd(w0 * m_in[j].x + w1 * m_pp[j].x + w2 * m_out[j].x,
						w0 * m_in[j].y + w1 * m_pp[j].y + w2 * m_out[j].y));
				}
				m_arc1[j] = (int)m_arc.size();
			}
		}

		/* segmentul j -> k sta pe trepte (pe o fuga): acolo curba si treptele coincid */
		bool peTrepte(int j, int k) const
		{
			if (m_p[j].fuga == m_p[k].fuga)
				return true;
			return m_p[j].la_capat && m_p[k].fuga == urm(m_p[j].fuga);
		}

		int fugaComuna(int j, int k) const
		{
			return m_p[j].fuga == m_p[k].fuga ? m_p[j].fuga : m_p[k].fuga;
		}

		void adaugaVarf(int j)
		{
			for (int k = m_arc0[j]; k < m_arc1[j]; k++)
				m_curba.push_back(m_arc[k]);
			m_curba.push_back(m_out[j]);
		}

		/* bucata dintre doua locuri unde curba sta pe trepte: S pe fuga rs, E pe fuga re */
		void inchide(const PunctHd &S, int rs, const PunctHd &E, int re, bool ocol)
		{
			if (m_curba.size() <= 2 && rs == re && !ocol)
				return;
			m_trepte.clear();
			m_trepte.push_back(S);
			if (rs != re || ocol)
			{
				int k = rs;
				do
				{
					m_trepte.push_back(capat(k));
					k = urm(k);
				} while (k != re && k >= 0);
			}
			m_trepte.push_back(E);
			BucataHd b;
			b.p = m_curba;
			for (size_t k = m_trepte.size(); k-- > 0;)
				b.p.push_back(m_trepte[k]);
			emite(b);
		}

		void emite(BucataHd &b)
		{
			b.x0 = b.x1 = b.p[0].x;
			b.y0 = b.y1 = b.p[0].y;
			for (size_t k = 1; k < b.p.size(); k++)
			{
				if (b.p[k].x < b.x0) b.x0 = b.p[k].x;
				if (b.p[k].x > b.x1) b.x1 = b.p[k].x;
				if (b.p[k].y < b.y0) b.y0 = b.p[k].y;
				if (b.p[k].y > b.y1) b.y1 = b.p[k].y;
			}
			if (b.x1 - b.x0 < 1e-9 || b.y1 - b.y0 < 1e-9)
				return;
			for (int k = 0; k < 4; k++)
				b.j[k] = m_j[k];
			b.n1 = m_n1;
			b.n2 = m_n2;
			m_iesire.push_back(b);
		}

		void bucati()
		{
			const int M = (int)m_p.size();
			if (M < 2)
				return;
			const int NS = m_inchis ? M : M - 1;
			int prima = -1, despartiri = 0;
			for (int j = 0; j < NS; j++)
				if (peTrepte(j, (j + 1) % M))
				{
					if (prima < 0)
						prima = j;
					despartiri++;
				}
			if (prima < 0)
			{
				if (!m_inchis)
					return;
				/* bucla fara niciun loc comun: toata curba si toata bucla de trepte, inapoi */
				BucataHd b;
				for (int j = 0; j < M; j++)
				{
					b.p.push_back(m_in[j]);
					for (int k = m_arc0[j]; k < m_arc1[j]; k++)
						b.p.push_back(m_arc[k]);
					b.p.push_back(m_out[j]);
				}
				b.p.push_back(m_in[0]);
				const int N = (int)m_varfuri.size(), L1 = GW + 1;
				PunctHd v0(m_h.x[m_varfuri[0] % L1], m_h.y[m_varfuri[0] / L1]);
				b.p.push_back(v0);
				for (int k = N - 1; k >= 0; k--)
					b.p.push_back(PunctHd(m_h.x[m_varfuri[k] % L1], m_h.y[m_varfuri[k] / L1]));
				emite(b);
				return;
			}
			const bool ocol = m_inchis && despartiri == 1;
			int j = (prima + 1) % M;
			int rs = fugaComuna(prima, j);
			PunctHd S = m_in[j];
			m_curba.clear();
			m_curba.push_back(S);
			const int pasi = m_inchis ? M : M - 1 - prima;
			for (int q = 0; q < pasi; q++, j = (j + 1) % M)
			{
				adaugaVarf(j);
				bool ultim = !m_inchis && j == M - 1;
				int k = (j + 1) % M;
				if (ultim || peTrepte(j, k))
				{
					int re = ultim ? m_p[j].fuga : fugaComuna(j, k);
					inchide(S, rs, m_out[j], re, ocol);
					if (ultim)
						break;
					S = m_in[k];
					rs = re;
					m_curba.clear();
					m_curba.push_back(S);
				}
				else
					m_curba.push_back(m_in[k]);
			}
		}
	};

	/* desenul unei bucati: aria cu semn a conturului, pe randuri de pixeli, apoi culoarea schimbata cu j x acoperirea */
	class AcumulatorHd
	{
	public:
		void bucata(const BucataHd &b, uint32_t *pixeli, int pas, int W, int Y0, int Y1)
		{
			parcurge(b, W, Y0, Y1, PeCuloare(b, pixeli, pas, Y0));
		}

		/* relieful: aceeasi bucata pe cele doua masti de nivel (m1 = nivel >= 1, m2 = nivel 2; W octeti pe rand, randurile
		   [Y0, Y1) ale paginii), cu saltul de nivel x 255 in loc de saltul de culoare */
		void masca(const BucataHd &b, uint8_t *m1, uint8_t *m2, int W, int Y0, int Y1)
		{
			parcurge(b, W, Y0, Y1, PeMasca(b, m1, m2, W, Y0));
		}

	private:
		struct PeCuloare
		{
			const BucataHd &b;
			uint32_t *pixeli;
			int pas, Y0;
			PeCuloare(const BucataHd &b_, uint32_t *p_, int pas_, int y0_) : b(b_), pixeli(p_), pas(pas_), Y0(y0_) {}
			void operator()(int x, int y, double s) const
			{
				aplica(pixeli[(size_t)(y - Y0) * pas + x], b.j, s);
			}
		};

		struct PeMasca
		{
			uint8_t *m1, *m2;
			int W, Y0;
			double j1, j2;
			PeMasca(const BucataHd &b, uint8_t *m1_, uint8_t *m2_, int w_, int y0_)
				: m1(m1_), m2(m2_), W(w_), Y0(y0_), j1(b.n1 * 255.0), j2(b.n2 * 255.0) {}
			void operator()(int x, int y, double s) const
			{
				size_t p = (size_t)(y - Y0) * W + x;
				if (j1 != 0)
					m1[p] = (uint8_t)octet(m1[p] + j1 * s);
				if (j2 != 0)
					m2[p] = (uint8_t)octet(m2[p] + j2 * s);
			}
		};

		/* aria cu semn a conturului bucatii, pe randurile de pixeli [Y0, Y1); f(x, y, acoperirea) pentru fiecare pixel
		   atins (y al paginii) */
		template <class F> void parcurge(const BucataHd &b, int W, int Y0, int Y1, const F &f)
		{
			int bx0 = (int)floor(b.x0) - 1, bx1 = (int)ceil(b.x1) + 2;
			int by0 = (int)floor(b.y0), by1 = (int)ceil(b.y1);
			if (by0 < Y0)
				by0 = Y0;
			if (by1 > Y1)
				by1 = Y1;
			if (by1 <= by0)
				return;
			m_bw = bx1 - bx0 + 1;
			m_bh = by1 - by0;
			size_t n = (size_t)m_bw * m_bh;
			if (m_buf.size() < n)
				m_buf.resize(n, 0.0);       /* celulele folosite se pun la loc pe 0 dupa fiecare bucata */
			m_min.assign(m_bh, m_bw);
			m_max.assign(m_bh, -1);
			const size_t np = b.p.size();
			for (size_t k = 0; k < np; k++)
			{
				const PunctHd &p = b.p[k], &q = b.p[(k + 1) % np];
				latura(p.x - bx0, p.y - by0, q.x - bx0, q.y - by0);
			}
			for (int y = 0; y < m_bh; y++)
			{
				if (m_max[y] < m_min[y])
					continue;
				double *r = &m_buf[(size_t)y * m_bw];
				double s = 0;
				for (int c = m_min[y]; c <= m_max[y]; c++)
				{
					s += r[c];
					r[c] = 0;
					if (s > -1.0 / 1024 && s < 1.0 / 1024)
						continue;
					int x = bx0 + c;
					if (x >= 0 && x < W)
						f(x, by0 + y, s);
				}
			}
		}

		std::vector<double> m_buf;
		std::vector<int> m_min, m_max;
		int m_bw, m_bh;

		/* integrala pe [lo, hi] din max(0, s - u) du */
		static double primitiva(double s, double lo, double hi)
		{
			if (s <= lo)
				return 0;
			if (s >= hi)
				return (hi - lo) * (s - (lo + hi) * 0.5);
			return (s - lo) * (s - lo) * 0.5;
		}

		/* o latura a conturului: pe fiecare rand de pixeli pe care il traverseaza, in coloana c se adauga diferenta
		   F(c) - F(c - 1), unde F(c) = sens x aria din pixelul c aflata la dreapta laturii (dupa insumarea pe rand,
		   pixelul primeste acoperirea lui) */
		void latura(double x0, double y0, double x1, double y1)
		{
			if (y0 == y1)
				return;
			double sens = 1.0;
			if (y0 > y1)
			{
				double t = x0; x0 = x1; x1 = t;
				t = y0; y0 = y1; y1 = t;
				sens = -1.0;
			}
			double dxdy = (x1 - x0) / (y1 - y0);
			int ya = (int)floor(y0), yb = (int)ceil(y1);
			if (ya < 0)
				ya = 0;
			if (yb > m_bh)
				yb = m_bh;
			for (int y = ya; y < yb; y++)
			{
				double sy0 = y0 > y ? y0 : (double)y, sy1 = y1 < y + 1 ? y1 : (double)(y + 1);
				double dy = sy1 - sy0;
				if (dy <= 0)
					continue;
				double xa = x0 + (sy0 - y0) * dxdy, xb = x0 + (sy1 - y0) * dxdy;
				double lo = xa < xb ? xa : xb, hi = xa < xb ? xb : xa;
				int c0 = (int)floor(lo), c1 = (int)floor(hi) + 1;
				if (c0 < 0)
					c0 = 0;
				if (c1 > m_bw - 1)
					c1 = m_bw - 1;
				double *r = &m_buf[(size_t)y * m_bw];
				double f = sens * dy, inainte = 0;
				if (hi - lo < 1e-12)
				{
					for (int c = c0; c <= c1; c++)
					{
						double u = c + 1 - lo;
						double v = f * (u <= 0 ? 0 : (u >= 1 ? 1 : u));
						r[c] += v - inainte;
						inainte = v;
					}
				}
				else
				{
					double k = f / (hi - lo);
					for (int c = c0; c <= c1; c++)
					{
						double v = k * (primitiva(c + 1, lo, hi) - primitiva(c, lo, hi));
						r[c] += v - inainte;
						inainte = v;
					}
				}
				if (c0 < m_min[y])
					m_min[y] = c0;
				if (c1 > m_max[y])
					m_max[y] = c1;
			}
		}

		static int octet(double v)
		{
			return v <= 0 ? 0 : (v >= 255 ? 255 : (int)(v + 0.5));
		}

		static void aplica(uint32_t &px, const double j[4], double s)
		{
			int A = (int)(px >> 24);
			if (A == 255 && j[3] == 0)
			{
				px = 0xFF000000u | ((uint32_t)octet(((px >> 16) & 0xFF) + j[0] * s) << 16) |
					((uint32_t)octet(((px >> 8) & 0xFF) + j[1] * s) << 8) | (uint32_t)octet((px & 0xFF) + j[2] * s);
				return;
			}
			double a = A + j[3] * s;
			double r = ((px >> 16) & 0xFF) * A / 255.0 + j[0] * s;
			double g = ((px >> 8) & 0xFF) * A / 255.0 + j[1] * s;
			double bl = (px & 0xFF) * A / 255.0 + j[2] * s;
			if (a > 255)
				a = 255;
			if (a < 0.5)
			{
				px = 0;
				return;
			}
			px = ((uint32_t)octet(a) << 24) | ((uint32_t)octet(r * 255.0 / a) << 16) | ((uint32_t)octet(g * 255.0 / a) << 8) |
				(uint32_t)octet(bl * 255.0 / a);
		}
	};

	FormeHd g_forme[2];
	int g_forme_urmatoarea = 0;
	AcumulatorHd g_acumulator;

	const FormeHd &formeHd(const GrilaHd &g, const HartaHd &h, const Aspect &a)
	{
		uint64_t cheie = amprentaHd(g, a);
		for (int k = 0; k < 2; k++)
			if (g_forme[k].gata && g_forme[k].cheie == cheie)
				return g_forme[k];
		FormeHd &f = g_forme[g_forme_urmatoarea];
		g_forme_urmatoarea ^= 1;
		f.gata = false;
		f.bucati.clear();
		niveluriHd(g, f.niv);
		std::vector<LantHd> lanturi;
		UrmaritorHd u(g);
		u.lanturi(lanturi);
		NetezitorHd n(h, a, f.bucati, f.niv);
		for (size_t k = 0; k < lanturi.size(); k++)
			n.lant(lanturi[k], u);
		f.cheie = cheie;
		f.gata = true;
		return f;
	}

	/* relieful: cat se deplaseaza forma spre dreapta-jos (pixeli) */
	inline int adancimeRelief(const Aspect &a)
	{
		int d = (a.i + 4) / 9;
		return d < 2 ? 2 : d;
	}

	/* nuanta fetei laterale la k pixeli (1..D) de forma, x 256: 0,70 langa forma, 0,50 la capat (trecerea de lumina) */
	inline int nuantaRelief(int k, int D)
	{
		return 179 - (k - 1) * 51 / (D - 1);
	}

	/*
	 * Formele in relief (numai la neted, optiune): fiecare forma colorata (mozaicul legat, casetele
	 * colorate; mozaicul separat in reliefSeparatHd; nu literele) primeste spre dreapta-jos o fata laterala: aceeasi forma deplasata
	 * 1..D pixeli pe diagonala (deplasari SAU pe masca), in nuanta mai inchisa a culorii ei, mai deschisa langa forma si
	 * mai inchisa spre capat. Nivelurile (niveluriHd): mozaicul (2) sta peste casete (1), casetele peste negru sau
	 * transparent (0); fata unei forme se vede numai pe ce e mai jos decat ea si numai in partea pixelului neacoperita de
	 * forma (marginea neteda a formei ramane neteda). Mastile celor doua niveluri (acoperirea "nivel >= 1" si "nivel 2")
	 * ies din aceleasi sextante si aceleasi bucati netezite ca stratul (salturile de nivel in loc de culoare), pe
	 * randurile [Y0 - D, Y1): fata unei forme din randul de deasupra benzii (antetul, sau randul de margine al fazei
	 * stinse) se vede la fel ca in pagina intreaga. Culoarea fetei e a regiunii din grila, la pixelul sursa (sau mai sus-
	 * stanga pe diagonala, unde curba a mutat granita). Pe un pixel p, cu c1, c2 = acoperirea mastilor in p, f1, f2 = cea
	 * mai mare acoperire pe diagonala sus-stanga (1..D), a2 = f2 daca f2 > c2, a1 = max(0, f1 - a2) daca f1 > c1, totul
	 * premultiplicat:
	 *   nou = L2 + (1 - a2) (P - L2) + a2 (1 - c2) F2 + a1 ((1 - c1) F1 - (P - L1)),  L2 = c2 S2,  L1 = L2 + (c1 - c2) S1
	 * (P pixelul stratului, S culoarea formei, F culoarea fetei): fata 2 in fata fetei 1, ambele in spatele formelor.
	 * Aceeasi socoteala, cu numere intregi, in desenatorul web (ttxReliefHd), comparata pixel cu pixel.
	 */
	struct ReliefHd
	{
		const GrilaHd &g;
		const uint8_t (*niv)[GW];
		int D;
		std::vector<int16_t> sx, sy;    /* sextantul fiecarei coloane si al fiecarui rand de pixeli al paginii */

		ReliefHd(const GrilaHd &g_, const uint8_t niv_[GH][GW], const HartaHd &h, const Aspect &a)
			: g(g_), niv(niv_), D(adancimeRelief(a)), sx(COLOANE * a.l), sy(RANDURI * a.i)
		{
			for (int gx = 0; gx < GW; gx++)
				for (int x = h.x[gx]; x < h.x[gx + 1]; x++)
					sx[x] = (int16_t)gx;
			for (int gy = 0; gy < GH; gy++)
				for (int y = h.y[gy]; y < h.y[gy + 1]; y++)
					sy[y] = (int16_t)gy;
		}

		/* culoarea (indicele) regiunii de nivel >= L la pixelul (x, y) al paginii, sau mai sus-stanga pe diagonala; -1 */
		int sursa(int L, int x, int y) const
		{
			for (int s = 0; s < D + 3 && x - s >= 0 && y - s >= 0; s++)
			{
				int gx = sx[x - s], gy = sy[y - s];
				if (niv[gy][gx] >= L)
					return g.c[gy][gx];
			}
			return -1;
		}
	};

	/* mastile reliefului, tinute intre compuneri (compunerea merge numai pe firul principal, ca formele) */
	std::vector<uint8_t> g_relief_m1, g_relief_m2;

	/* relieful randurilor [rand0, rand1), peste stratul deja desenat; f = formele netezite (0 = pagina fara mozaic) */
	void reliefHd(const GrilaHd &g, const uint8_t niv[GH][GW], const FormeHd *f, const HartaHd &h, const Aspect &a,
		int rand0, int rand1, uint32_t *pixeli, int pas)
	{
		ReliefHd r(g, niv, h, a);
		const int W = COLOANE * a.l, D = r.D;
		const int Y0 = rand0 * a.i, Y1 = rand1 * a.i, Ym = Y0 - D > 0 ? Y0 - D : 0, HM = Y1 - Ym;
		if (g_relief_m1.size() < (size_t)W * HM)
		{
			g_relief_m1.resize((size_t)W * HM);
			g_relief_m2.resize((size_t)W * HM);
		}
		uint8_t *m1 = &g_relief_m1[0], *m2 = &g_relief_m2[0];   /* fiecare octet folosit se scrie mai jos */
		/* mastile: sextantele, apoi bucatile netezite cu salturile de nivel */
		for (int gy = 0; gy < GH; gy++)
		{
			int y0 = h.y[gy] > Ym ? h.y[gy] : Ym, y1 = h.y[gy + 1] < Y1 ? h.y[gy + 1] : Y1;
			if (y1 <= y0)
				continue;
			uint8_t *r1 = &m1[(size_t)(y0 - Ym) * W], *r2 = &m2[(size_t)(y0 - Ym) * W];
			for (int gx = 0; gx < GW; gx++)
			{
				int n = niv[gy][gx], x0 = h.x[gx], w = h.x[gx + 1] - x0;
				memset(r1 + x0, n >= 1 ? 255 : 0, (size_t)w);
				memset(r2 + x0, n >= 2 ? 255 : 0, (size_t)w);
			}
			for (int y = y0 + 1; y < y1; y++)
			{
				memcpy(&m1[(size_t)(y - Ym) * W], r1, (size_t)W);
				memcpy(&m2[(size_t)(y - Ym) * W], r2, (size_t)W);
			}
		}
		if (f)
			for (size_t k = 0; k < f->bucati.size(); k++)
			{
				const BucataHd &b = f->bucati[k];
				if ((b.n1 || b.n2) && b.y1 > Ym && b.y0 < Y1)
					g_acumulator.masca(b, m1, m2, W, Ym, Y1);
			}
		uint32_t culori[9];
		for (int v = 0; v < 9; v++)
			culori[v] = argbHd(v, a);
		for (int y = Y0; y < Y1; y++)
		{
			const int kmax = y - Ym < D ? y - Ym : D;
			if (kmax <= 0)
				continue;
			const uint8_t *c1r = &m1[(size_t)(y - Ym) * W], *c2r = &m2[(size_t)(y - Ym) * W];
			uint32_t *d = pixeli + (size_t)(y - Y0) * pas;
			for (int x0 = 0; x0 < W; x0 += 8)
			{
				const int x1 = x0 + 8 < W ? x0 + 8 : W;
				if (x1 - x0 == 8 && x0 >= D && kmax == D)
				{
					/* 8 pixeli la rand: daca fereastra diagonala a fiecaruia are pe ambele masti aceleasi valori ca el,
					   nicio fata (rezultatul e acelasi ca pixel cu pixel); asa se sare tot ce e in interiorul formelor si
					   pe fundal, iar socoteala ramane langa granite */
					uint64_t a1, a2;
					memcpy(&a1, c1r + x0, 8);
					memcpy(&a2, c2r + x0, 8);
					if (a2 == ~(uint64_t)0)
						continue;
					bool la_fel = true;
					for (int k = 1; k <= D && la_fel; k++)
					{
						uint64_t b1, b2;
						const size_t q = (size_t)(y - k - Ym) * W + (size_t)(x0 - k);
						memcpy(&b1, m1 + q, 8);
						memcpy(&b2, m2 + q, 8);
						la_fel = b1 == a1 && b2 == a2;
					}
					if (la_fel)
						continue;
				}
				for (int x = x0; x < x1; x++)
				{
					const int c1 = c1r[x], c2 = c2r[x];
					if (c2 == 255)
						continue;
					int f1 = 0, k1 = 0, f2 = 0, k2 = 0;
					const int km = x < kmax ? x : kmax;
					for (int k = 1; k <= km; k++)
					{
						size_t q = (size_t)(y - k - Ym) * W + (size_t)(x - k);
						if (m2[q] > f2)
						{
							f2 = m2[q];
							k2 = k;
						}
						if (m1[q] > f1)
						{
							f1 = m1[q];
							k1 = k;
						}
					}
					int a2 = f2 > c2 ? f2 : 0, a1 = f1 > c1 ? f1 : 0;
					int v2 = a2 ? r.sursa(2, x - k2, y - k2) : -1, v1 = -1;
					if (v2 < 0)
						a2 = 0;
					a1 = a1 > a2 ? a1 - a2 : 0;
					if (a1)
					{
						v1 = r.sursa(1, x - k1, y - k1);
						if (v1 < 0)
							a1 = 0;
					}
					if (!a2 && !a1)
						continue;
					if (v1 < 0)
						v1 = v2;
					if (v2 < 0)
						v2 = v1;
					/* premultiplicat: P, S2, S1, F2, F1 (r, g, b, a) */
					const uint32_t px = d[x], s2 = culori[v2], s1 = culori[v1];
					const int pa = (int)(px >> 24), a_2 = (int)(s2 >> 24), a_1 = (int)(s1 >> 24);
					const int n2 = a2 ? nuantaRelief(k2, D) : 0, n1 = a1 ? nuantaRelief(k1, D) : 0;
					int o[4];
					for (int ch = 0; ch < 4; ch++)
					{
						int P, S2, S1, F2, F1;
						if (ch < 3)
						{
							const int sh = 16 - 8 * ch;
							const int p = (int)((px >> sh) & 0xFF);
						const int c_2 = (int)((s2 >> sh) & 0xFF), c_1 = (int)((s1 >> sh) & 0xFF);
							P = (p * pa + 127) / 255;
							S2 = (c_2 * a_2 + 127) / 255;
							S1 = (c_1 * a_1 + 127) / 255;
							F2 = (((c_2 * n2 + 128) >> 8) * a_2 + 127) / 255;
							F1 = (((c_1 * n1 + 128) >> 8) * a_1 + 127) / 255;
						}
						else
						{
							P = pa;
							S2 = F2 = a_2;
							S1 = F1 = a_1;
						}
						const int L2 = c2 * S2, L1 = L2 + (c1 > c2 ? c1 - c2 : 0) * S1;
						const int v = L2 * 255 + (255 - a2) * (P * 255 - L2) + a2 * (255 - c2) * F2 +
							a1 * ((255 - c1) * F1 - (P * 255 - L1));
						o[ch] = v <= 0 ? 0 : ((v + 32512) / 65025 > 255 ? 255 : (v + 32512) / 65025);
					}
					if (!o[3])
					{
						d[x] = 0;
						continue;
					}
					for (int ch = 0; ch < 3; ch++)
					{
						int c = (o[ch] * 255 + o[3] / 2) / o[3];
						o[ch] = c > 255 ? 255 : c;
					}
					d[x] = ((uint32_t)o[3] << 24) | ((uint32_t)o[0] << 16) | ((uint32_t)o[1] << 8) | (uint32_t)o[2];
				}
			}
		}
	}

	/* stratul HD al randurilor [rand0, rand1): sextantele ca la clasic, apoi bucatile netezite */
	void stratHd(const Celula pagina[RANDURI][COLOANE], int rand0, int rand1, const Aspect &a, uint32_t *pixeli, int pas)
	{
		GrilaHd g;
		bool aprinse = faGrilaHd(pagina, a, g);
		HartaHd h(a);
		const int W = COLOANE * a.l, Y0 = rand0 * a.i, Y1 = rand1 * a.i;
		uint32_t culori[9];
		for (int v = 0; v < 9; v++)
			culori[v] = argbHd(v, a);
		for (int gy = 3 * rand0; gy < 3 * rand1; gy++)
		{
			int y0 = h.y[gy], y1 = h.y[gy + 1];
			if (y1 <= y0)
				continue;
			uint32_t *d = pixeli + (size_t)(y0 - Y0) * pas;
			for (int gx = 0; gx < GW; gx++)
			{
				uint32_t c = culori[g.c[gy][gx]];
				for (int x = h.x[gx]; x < h.x[gx + 1]; x++)
					d[x] = c;
			}
			for (int y = y0 + 1; y < y1; y++)
				memcpy(pixeli + (size_t)(y - Y0) * pas, d, (size_t)W * sizeof(uint32_t));
		}
		if (!aprinse)
		{
			/* fara mozaic nimic de netezit; relieful casetelor colorate din sextante */
			if (a.relief)
			{
				uint8_t niv[GH][GW];
				niveluriHd(g, niv);
				reliefHd(g, niv, 0, h, a, rand0, rand1, pixeli, pas);
			}
			return;
		}
		const FormeHd &f = formeHd(g, h, a);
		for (size_t k = 0; k < f.bucati.size(); k++)
		{
			const BucataHd &b = f.bucati[k];
			if (b.y1 <= Y0 || b.y0 >= Y1)
				continue;
			g_acumulator.bucata(b, pixeli, pas, W, Y0, Y1);
		}
		if (a.relief)
			reliefHd(g, f.niv, &f, h, a, rand0, rand1, pixeli, pas);
	}

	/* fata laterala a unui bloc separat de bw x bh pixeli (colturile ca la blocRotund): pe (bw + D) x (bh + D) pixeli, de
	   la coltul blocului, cea mai mare acoperire a blocului deplasat cu (k, k), k = 1..D, si k-ul ei. Toate blocurile de
	   aceeasi marime au aceeasi fata: se socoteste o data (o pagina cu harta are sute de blocuri, de cateva marimi) */
	struct FataBlocHd
	{
		int tw, th;
		std::vector<uint8_t> acop, k;
	};

	const FataBlocHd &fataBlocHd(int bw, int bh, int D)
	{
		static std::map<uint32_t, FataBlocHd> tinute;
		uint32_t cheie = ((uint32_t)bw << 20) | ((uint32_t)bh << 8) | (uint32_t)D;
		std::map<uint32_t, FataBlocHd>::iterator g = tinute.find(cheie);
		if (g != tinute.end())
			return g->second;
		if (tinute.size() > 64)
			tinute.clear();
		FataBlocHd &f = tinute[cheie];
		f.tw = bw + D;
		f.th = bh + D;
		f.acop.assign((size_t)f.tw * f.th, 0);
		f.k.assign((size_t)f.tw * f.th, 0);
		/* acoperirea blocului, ca in blocRotund */
		std::vector<uint8_t> bloc((size_t)bw * bh, 0);
		float cx = bw * 0.5f, cy = bh * 0.5f, hw = bw * 0.5f, hh = bh * 0.5f, raza = (hw < hh ? hw : hh) * 0.6f;
		for (int y = 0; y < bh; y++)
			for (int x = 0; x < bw; x++)
			{
				float dx = fabsf(x + 0.5f - cx) - (hw - raza), dy = fabsf(y + 0.5f - cy) - (hh - raza);
				float ex = dx > 0 ? dx : 0, ey = dy > 0 ? dy : 0;
				float acc = 0.5f - (sqrtf(ex * ex + ey * ey) - raza);
				if (acc > 0)
					bloc[(size_t)y * bw + x] = (uint8_t)((acc > 1 ? 1 : acc) * 255 + 0.5f);
			}
		for (int y = 0; y < f.th; y++)
			for (int x = 0; x < f.tw; x++)
				for (int q = 1; q <= D; q++)
				{
					int u = x - q, v = y - q;
					if (u < 0 || v < 0 || u >= bw || v >= bh)
						continue;
					uint8_t c = bloc[(size_t)v * bw + u];
					size_t p = (size_t)y * f.tw + x;
					if (c > f.acop[p])
					{
						f.acop[p] = c;
						f.k[p] = (uint8_t)q;
					}
				}
		return f;
	}

	/* relieful mozaicului separat (blocurile rotunjite, care nu sunt in strat): fata laterala a fiecarui bloc colorat,
	   direct in pixeli, sub litere si sub blocuri (acelea se pun peste, la sfarsitul compunerii, deci un bloc acopera fata
	   vecinului sau). Pe fiecare pixel, cea mai mare acoperire a blocului deplasat cu (k, k), k = 1..D, ca la strat, in
	   nuanta culorii lui la k. Randurile [rand0 - 1, rand1): fata unui bloc din randul de deasupra cade si in banda */
	void reliefSeparatHd(const Celula pagina[RANDURI][COLOANE], int rand0, int rand1, const Aspect &a, uint32_t *pixeli,
		int pas)
	{
		const int W = COLOANE * a.l, H = (rand1 - rand0) * a.i, D = adancimeRelief(a);
		const int acop = a.peste ? a.alfa_fundal : 255;
		int nuante[64];
		for (int q = 1; q <= D && q < 64; q++)
			nuante[q] = nuantaRelief(q, D);
		for (int r = rand0 > 0 ? rand0 - 1 : 0; r < rand1; r++)
			for (int c = 0; c < COLOANE; c++)
			{
				const Celula &ce = pagina[r][c];
				int s = ce.mozaic & 0x3F;
				if (!ce.mozaic || !s || !(ce.atribute & A_SEPARAT) || !(ce.fata & 7))
					continue;
				if (ce.atribute & (A_JUMATATE_JOS | A_JUMATATE_DREAPTA))
					continue;
				if ((ce.atribute & A_INTERMITENT) && a.stinge_intermitente)
					continue;
				if ((ce.atribute & A_ASCUNS) && !a.arata_ascuns)
					continue;
				bool dl = (ce.atribute & A_DUBLA_LATIME) != 0, di = (ce.atribute & A_DUBLA_INALTIME) != 0;
				int w = a.l * (dl ? 2 : 1), h = a.i * (di ? 2 : 1), x0 = c * a.l, y0 = (r - rand0) * a.i;
				int xs[3] = { 0, (w + 1) / 2, w }, ys[4] = { 0, (h + 1) / 3, (2 * h + 1) / 3, h };
				const uint32_t rgb = culoare(ce.fata);
				for (int k = 0; k < 6; k++)
				{
					if (!((s >> k) & 1))
						continue;
					int cx = k & 1, cy = k >> 1;
					int bx0 = xs[cx], bx1 = xs[cx + 1], by0 = ys[cy], by1 = ys[cy + 1];
					int gx = (bx1 - bx0) / 3, gy = (by1 - by0) / 3;
					bx0 += gx > 0 ? gx : 1;
					by1 -= gy > 0 ? gy : 1;
					if (bx1 <= bx0 || by1 <= by0 || D >= 64)
						continue;
					const FataBlocHd &f = fataBlocHd(bx1 - bx0, by1 - by0, D);
					const int ox = x0 + bx0, oy = y0 + by0;
					for (int ty = 0; ty < f.th; ty++)
					{
						const int y = oy + ty;
						if (y < 0 || y >= H)
							continue;
						const uint8_t *fa = &f.acop[(size_t)ty * f.tw], *fk = &f.k[(size_t)ty * f.tw];
						uint32_t *d = pixeli + (size_t)y * pas;
						for (int tx = 0; tx < f.tw; tx++)
						{
							const int x = ox + tx;
							if (!fa[tx] || x < 0 || x >= W)
								continue;
							const int n = nuante[fk[tx]];
							const uint32_t c = ((((rgb >> 16) & 0xFF) * n + 128) >> 8 << 16) |
								((((rgb >> 8) & 0xFF) * n + 128) >> 8 << 8) | (((rgb & 0xFF) * n + 128) >> 8);
							d[x] = peste(d[x], c, (fa[tx] * acop + 127) / 255);
						}
					}
				}
			}
	}
}

int compune(const Celula pagina[RANDURI][COLOANE], int rand0, int rand1, const Aspect &a, Glife &glife,
	uint32_t *pixeli, int pas)
{
	if (rand0 < 0)
		rand0 = 0;
	if (rand1 > RANDURI)
		rand1 = RANDURI;
	if (rand1 <= rand0 || a.l < 2 || a.i < 3)
		return 0;
	const int W = COLOANE * a.l, H = (rand1 - rand0) * a.i;
	std::vector<uint8_t> acop((size_t)W * H, 0), fata((size_t)W * H, 7);
	/* conturul (optiune): peste imagine grosimea din aspect, in jurul literelor si formelor deschise; pe tot ecranul 1 px,
	   numai in jurul literelor deschise */
	const int grosime = a.cu_contur ? (a.peste ? a.contur : 1) : 0;
	std::vector<uint8_t> litere;                    /* toate literele, pentru umbra */
	std::vector<uint8_t> deschise;                  /* literele deschise la culoare, pentru conturul pe tot ecranul */
	if (a.cu_umbra)
		litere.assign((size_t)W * H, 0);
	if (grosime > 0 && !a.peste)
		deschise.assign((size_t)W * H, 0);
	bool deschisa[8];
	for (int k = 0; k < 8; k++)
		deschisa[k] = luminanta(culoare(k)) >= PRAG_DESCHIS;
	const int acop_mozaic = a.peste ? a.alfa_fundal : 255;
	int intermitente = 0;

	/* HD: fundalurile si mozaicul legat, netezite pe toata pagina, direct in pixeli; aici raman literele si mozaicul
	   separat */
	if (a.hd)
	{
		stratHd(pagina, rand0, rand1, a, pixeli, pas);
		if (a.relief)
			reliefSeparatHd(pagina, rand0, rand1, a, pixeli, pas);
	}

	for (int r = rand0; r < rand1; r++)
		for (int c = 0; c < COLOANE; c++)
		{
			const Celula &ce = pagina[r][c];
			int x0 = c * a.l, y0 = (r - rand0) * a.i;
			/* fundalul */
			if (!a.hd)
			{
				uint32_t f;
				if (!a.peste)
					f = 0xFF000000u | culoare(ce.fundal);
				else
					f = ce.fundal ? ((uint32_t)a.alfa_fundal << 24) | culoare(ce.fundal) : 0;
				for (int y = y0; y < y0 + a.i; y++)
				{
					uint32_t *d = pixeli + (size_t)y * pas + x0;
					for (int x = 0; x < a.l; x++)
						d[x] = f;
				}
			}
			if (ce.atribute & (A_JUMATATE_JOS | A_JUMATATE_DREAPTA))
				continue;
			if (ce.atribute & A_INTERMITENT)
				intermitente = 1;
			if ((ce.atribute & A_INTERMITENT) && a.stinge_intermitente)
				continue;
			if ((ce.atribute & A_ASCUNS) && !a.arata_ascuns)
				continue;
			bool dl = (ce.atribute & A_DUBLA_LATIME) != 0, di = (ce.atribute & A_DUBLA_INALTIME) != 0;
			int w = a.l * (dl ? 2 : 1), h = a.i * (di ? 2 : 1);
			if (ce.mozaic)
			{
				int s = ce.mozaic & 0x3F;
				if (!s)
					continue;
				bool separat = (ce.atribute & A_SEPARAT) != 0;
				if (a.hd && !separat)
					continue;               /* HD: mozaicul legat e in strat */
				int xs[3] = { 0, (w + 1) / 2, w }, ys[4] = { 0, (h + 1) / 3, (2 * h + 1) / 3, h };
				for (int k = 0; k < 6; k++)
				{
					if (!((s >> k) & 1))
						continue;
					int cx = k & 1, cy = k >> 1;
					int bx0 = xs[cx], bx1 = xs[cx + 1], by0 = ys[cy], by1 = ys[cy + 1];
					if (separat)
					{
						int gx = (bx1 - bx0) / 3, gy = (by1 - by0) / 3;
						bx0 += gx > 0 ? gx : 1;
						by1 -= gy > 0 ? gy : 1;
					}
					if (a.hd)
						blocRotund(acop, fata, W, H, (float)(x0 + bx0), (float)(y0 + by0), (float)(x0 + bx1),
							(float)(y0 + by1), ce.fata, acop_mozaic);
					else
						/* peste imagine mozaicul e cat un fundal colorat (cutiile facute din blocuri si din fundal ies la fel) */
						umple(acop, fata, W, H, x0 + bx0, y0 + by0, x0 + bx1, y0 + by1, ce.fata, (uint8_t)acop_mozaic);
				}
				continue;
			}
			if (ce.cod <= 0x20 || (a.hd && ce.cod == 0x25A0))
				continue;               /* HD: blocul plin e in strat, ca mozaicul */
			const uint8_t *m = glife.acoperire(ce.cod, w, h);
			if (!m)
				continue;
			const bool lit_deschisa = !deschise.empty() && deschisa[ce.fata & 7];
			for (int y = 0; y < h && y0 + y < H; y++)
			{
				const uint8_t *s = m + (size_t)y * w;
				uint8_t *da = &acop[(size_t)(y0 + y) * W + x0];
				uint8_t *df = &fata[(size_t)(y0 + y) * W + x0];
				uint8_t *dlit = litere.empty() ? 0 : &litere[(size_t)(y0 + y) * W + x0];
				uint8_t *dd = lit_deschisa ? &deschise[(size_t)(y0 + y) * W + x0] : 0;
				int n = x0 + w > W ? W - x0 : w;
				for (int x = 0; x < n; x++)
				{
					if (s[x] > da[x])
					{
						da[x] = s[x];
						df[x] = ce.fata;
					}
					if (dlit && s[x] > dlit[x])
						dlit[x] = s[x];
					if (dd && s[x] > dd[x])
						dd[x] = s[x];
				}
			}
		}

	/* umbra moale a literelor (optiune; jos-dreapta), sub contur si sub litere */
	std::vector<uint8_t> umbra;
	if (a.cu_umbra)
	{
		int ud = a.i / 20 > 1 ? a.i / 20 : 1;
		umbra.assign((size_t)W * H, 0);
		for (int y = ud; y < H; y++)
			memcpy(&umbra[(size_t)y * W + ud], &litere[(size_t)(y - ud) * W], (size_t)(W - ud));
		int raza = a.i / 12 > 1 ? a.i / 12 : 1;
		estompeaza(umbra, W, H, raza);
	}

	/* conturul (optiune), numai in jurul a ce e deschis la culoare (literele negre sau inchise nu se ingroasa): pe tot
	   ecranul in jurul literelor deschise; peste imagine in jurul literelor si formelor deschise. Neted peste imagine:
	   fundalurile si mozaicul legat sunt in strat (in pixeli), deci se iau pixelii deschisi ai stratului, cu opacitatea
	   lor, iar conturul se pune numai unde stratul e mai transparent decat el (in jurul formelor, peste imagine) */
	std::vector<uint8_t> contur, strat;
	if (grosime > 0)
	{
		if (a.peste)
		{
			std::vector<uint8_t> sursa((size_t)W * H, 0);
			for (size_t p = 0; p < sursa.size(); p++)
				if (acop[p] && deschisa[fata[p] & 7])
					sursa[p] = acop[p];
			if (a.hd)
			{
				strat.resize((size_t)W * H);
				for (int y = 0; y < H; y++)
				{
					const uint32_t *d = pixeli + (size_t)y * pas;
					uint8_t *st = &strat[(size_t)y * W], *su = &sursa[(size_t)y * W];
					for (int x = 0; x < W; x++)
					{
						st[x] = (uint8_t)(d[x] >> 24);
						if (st[x] > su[x] && luminanta(d[x]) >= PRAG_DESCHIS)
							su[x] = st[x];
					}
				}
			}
			lateste(sursa, contur, W, H, grosime);
		}
		else
			lateste(deschise, contur, W, H, grosime);
	}

	for (int y = 0; y < H; y++)
	{
		uint32_t *d = pixeli + (size_t)y * pas;
		const uint8_t *ac = &acop[(size_t)y * W];
		const uint8_t *fa = &fata[(size_t)y * W];
		const uint8_t *co = contur.empty() ? 0 : &contur[(size_t)y * W];
		const uint8_t *um = umbra.empty() ? 0 : &umbra[(size_t)y * W];
		const uint8_t *st = strat.empty() ? 0 : &strat[(size_t)y * W];
		if (gol(ac, W) && (!co || gol(co, W)) && (!um || gol(um, W)))
			continue;
		for (int x = 0; x < W; x++)
		{
			if (!(x & 7) && x + 8 <= W)
			{
				uint64_t a8, c8 = 0, u8 = 0;
				memcpy(&a8, ac + x, 8);
				if (co)
					memcpy(&c8, co + x, 8);
				if (um)
					memcpy(&u8, um + x, 8);
				if (!(a8 | c8 | u8))
				{
					x += 7;     /* 8 pixeli fara litera, contur si umbra */
					continue;
				}
			}
			if (!ac[x] && !(co && co[x]) && !(um && um[x]))
				continue;
			uint32_t v = d[x];
			if (um && um[x] > ac[x])
				v = peste(v, 0x000000, um[x] * 3 / 4);    /* umbra, numai in afara literei */
			if (co && co[x] > ac[x] && !(st && st[x] >= co[x]))
				v = peste(v, 0x000000, co[x]);       /* conturul, numai in afara literei (sub marginea ei neteda) */
			if (ac[x])
				v = peste(v, culoare(fa[x]), ac[x]);
			d[x] = v;
		}
	}
	return intermitente;
}

bool compuneStinsa(const Celula pagina[RANDURI][COLOANE], const Aspect &a, Glife &glife, const uint32_t *aprinsa,
	uint32_t *stinsa, int pas)
{
	if (a.l < 2 || a.i < 3)
		return false;
	const int W = COLOANE * a.l;
	/* randurile cu celule intermitente (o celula dubla atinge si randul de dedesubt) */
	bool rand[RANDURI];
	memset(rand, 0, sizeof(rand));
	for (int r = 1; r < RANDURI; r++)
		for (int c = 0; c < COLOANE; c++)
		{
			const Celula &ce = pagina[r][c];
			if (!(ce.atribute & A_INTERMITENT) || (ce.atribute & (A_JUMATATE_JOS | A_JUMATATE_DREAPTA)))
				continue;
			bool in_strat = ((ce.mozaic & 0x3F) && !(ce.atribute & A_SEPARAT)) || (!ce.mozaic && ce.cod == 0x25A0);
			if (a.hd && in_strat)
				return false;
			rand[r] = true;
			if ((ce.atribute & A_DUBLA_INALTIME) && r + 1 < RANDURI)
				rand[r + 1] = true;
		}
	for (int y = 0; y < (RANDURI - 1) * a.i; y++)
		memcpy(stinsa + (size_t)y * pas, aprinsa + (size_t)y * pas, (size_t)W * sizeof(uint32_t));
	std::vector<uint32_t> tmp;
	for (int r = 1; r < RANDURI;)
	{
		if (!rand[r])
		{
			r++;
			continue;
		}
		int b0 = r, b1 = r;
		while (b1 < RANDURI && rand[b1])
			b1++;
		r = b1;
		/* umbra si conturul trec cativa pixeli in randul vecin, in ambele sensuri: se copiaza si randul de dinainte si
		   cel de dupa banda (au urme de la literele ei), compuse cu inca un rand de margine (au urme de la vecinii
		   lor); randul de sus se ia si el cand e jumatatea de jos a unor celule duble (le deseneaza randul de deasupra) */
		b0 = b0 - 1 < 1 ? 1 : b0 - 1;
		b1 = b1 + 1 > RANDURI ? RANDURI : b1 + 1;
		int c0 = b0 - 1 < 1 ? 1 : b0 - 1, c1 = b1 + 1 > RANDURI ? RANDURI : b1 + 1;
		for (bool jumatate = true; jumatate && c0 > 1;)
		{
			jumatate = false;
			for (int c = 0; c < COLOANE; c++)
				if (pagina[c0][c].atribute & A_JUMATATE_JOS)
					jumatate = true;
			if (jumatate)
				c0--;
		}
		tmp.assign((size_t)W * (c1 - c0) * a.i, 0);
		compune(pagina, c0, c1, a, glife, &tmp[0], W);
		for (int y = (b0 - c0) * a.i; y < (b1 - c0) * a.i; y++)
			memcpy(stinsa + (size_t)((c0 - 1) * a.i + y) * pas, &tmp[(size_t)y * W], (size_t)W * sizeof(uint32_t));
	}
	return true;
}

}

#ifndef HDS_TELETEXT_FARA_PYTHON
/* ------------------------------------------------------------------ pentru Python si pentru parser */

eHdsTeletext *eHdsTeletext::getInstance()
{
	static eHdsTeletext unic;
	return &unic;
}

eHdsTeletext *eHdsTeletext::copie(int loc)
{
	static eHdsTeletext copii[2];
	return &copii[loc == 1 ? 1 : 0];
}

PyObject *eHdsTeletext::exporta()
{
	std::string o = m_colector.exporta(m_pid);
	return PyBytes_FromStringAndSize(o.data(), (Py_ssize_t)o.size());
}

int eHdsTeletext::incarca(PyObject *date)
{
	if (!date || !PyBytes_Check(date))
		return -1;
	if (this == getInstance())
		return -1;          /* paginile serviciului care merge nu se inlocuiesc dintr-o copie */
	int pid = m_colector.incarca((const uint8_t *)PyBytes_AS_STRING(date), (size_t)PyBytes_GET_SIZE(date));
	m_pid = pid > 0 ? pid : -1;
	return pid;
}

eHdsTeletext::eHdsTeletext()
	: m_proprietar(0), m_pid(-1)
{
}

void eHdsTeletext::porneste(const void *proprietar, int pid)
{
	/* acelasi parser si acelasi PID (PMT-ul reinnoit, updateDecoder din nou): memoria ramane */
	if (proprietar == m_proprietar && pid == m_pid)
		return;
	m_colector.reseteaza();
	m_proprietar = proprietar;
	m_pid = pid > 0 && pid < 0x1FFF ? pid : -1;
}

void eHdsTeletext::opreste(const void *proprietar)
{
	if (proprietar != m_proprietar)
		return;
	m_colector.reseteaza();
	m_proprietar = 0;
	m_pid = -1;
}

void eHdsTeletext::adauga(const void *proprietar, const uint8_t *adresa_si_date)
{
	if (proprietar == m_proprietar && m_pid > 0)
		m_colector.adaugaPachet(adresa_si_date);
}

PyObject *eHdsTeletext::stare()
{
	return Py_BuildValue("(iiiiIII)", m_pid, (int)m_colector.numarPagini(), (int)m_colector.numarSubpagini(),
		(int)m_colector.octeti(), (unsigned int)m_colector.versiune(), (unsigned int)m_colector.pacheteBune(),
		(unsigned int)m_colector.pacheteRele());
}

PyObject *eHdsTeletext::pagini()
{
	std::vector<int> p = m_colector.pagini();
	PyObject *l = PyList_New(0);
	for (size_t k = 0; k < p.size(); k++)
	{
		int z = hdsttx::zecimalDinPagina(p[k]);
		if (!z)
			continue;
		PyObject *n = PyLong_FromLong(z);
		PyList_Append(l, n);
		Py_DECREF(n);
	}
	return l;
}

PyObject *eHdsTeletext::subpagini(int pagina)
{
	std::vector<int> s = m_colector.subcoduri(hdsttx::paginaDinZecimal(pagina));
	PyObject *l = PyList_New((Py_ssize_t)s.size());
	for (size_t k = 0; k < s.size(); k++)
		PyList_SET_ITEM(l, (Py_ssize_t)k, PyLong_FromLong(s[k]));
	return l;
}

int eHdsTeletext::versiune(int pagina)
{
	return (int)(m_colector.versiunePagina(hdsttx::paginaDinZecimal(pagina)) & 0x7FFFFFFF);
}

PyObject *eHdsTeletext::pagina(int pagina, int subcod, const char *stare, int aratAntet)
{
	int p = hdsttx::paginaDinZecimal(pagina);
	if (p == hdsttx::PAGINA_FARA)
		Py_RETURN_NONE;
	const hdsttx::Subpagina *sp = m_colector.gaseste(p, subcod);
	if (!sp && !aratAntet)
		Py_RETURN_NONE;
	uint16_t control = 0;
	const uint8_t *antet = m_colector.antetRulant((p >> 8) & 0xF, &control);
	static hdsttx::Celula celule[hdsttx::RANDURI][hdsttx::COLOANE];
	hdsttx::randeaza(m_colector, sp, p, stare, antet, control, celule);
	char octeti[hdsttx::RANDURI * hdsttx::COLOANE * 8];
	char *o = octeti;
	for (int r = 0; r < hdsttx::RANDURI; r++)
		for (int c = 0; c < hdsttx::COLOANE; c++)
		{
			const hdsttx::Celula &ce = celule[r][c];
			o[0] = (char)(ce.cod & 0xFF);
			o[1] = (char)((ce.cod >> 8) & 0xFF);
			o[2] = (char)((ce.cod >> 16) & 0xFF);
			o[3] = (char)((ce.cod >> 24) & 0xFF);
			o[4] = (char)ce.mozaic;
			o[5] = (char)ce.fata;
			o[6] = (char)ce.fundal;
			o[7] = (char)ce.atribute;
			o += 8;
		}
	return Py_BuildValue("(iiiy#)", pagina, sp ? (int)sp->subcod : -1, sp ? (int)(sp->versiune & 0x7FFFFFFF) : 0,
		octeti, (Py_ssize_t)sizeof(octeti));
}

PyObject *eHdsTeletext::legaturi(int pagina, int subcod)
{
	const hdsttx::Subpagina *sp = m_colector.gaseste(hdsttx::paginaDinZecimal(pagina), subcod);
	if (!sp || !sp->are_legaturi)
		Py_RETURN_NONE;
	int l[hdsttx::LEGATURI];
	hdsttx::legaturiZecimale(*sp, l);
	PyObject *r = PyList_New(hdsttx::LEGATURI);
	for (int k = 0; k < hdsttx::LEGATURI; k++)
		PyList_SET_ITEM(r, k, PyLong_FromLong(l[k]));
	return r;
}

PyObject *eHdsTeletext::top()
{
	if (m_colector.topTip(0x100) < 0)
		Py_RETURN_NONE;
	char t[800];
	for (int k = 0; k < 800; k++)
	{
		int v = m_colector.topTip(hdsttx::paginaDinZecimal(100 + k));
		t[k] = (char)(v < 0 ? 0 : v);
	}
	return PyBytes_FromStringAndSize(t, sizeof(t));
}

int eHdsTeletext::paginaInitiala()
{
	return hdsttx::zecimalDinPagina(m_colector.paginaInitiala());
}

std::string eHdsTeletext::numeServiciu()
{
	return m_colector.numeServiciu();
}
#endif
