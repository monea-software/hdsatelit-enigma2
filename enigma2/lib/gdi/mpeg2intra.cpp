/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
/* Codorul MPEG-2 de cadru intra, scris de noi dupa ISO/IEC 13818-2 (ITU-T H.262), Anexa B.
   Tabelele de coduri sunt date din standard, scrise de mana si dovedite inainte pe pixeli:
   un cititor propriu a desfacut sase cadre I facute cu ffmpeg pana la pixeli si a folosit
   toate cele 111 intrari ale Tabelului B-14.
   Nu se compileaza nimic din enigma2 aici: fisierul merge si singur, pe PC. */

#include <lib/gdi/mpeg2intra.h>

#include <math.h>
#include <string.h>

namespace
{
	/* Tabelul 7-3: matricea de cuantizare intra implicita. Pentru ca in antet scriem
	   load_intra_quantiser_matrix = 0, matricea asta NU se scrie in fisier: decodorul o stie. */
	const int MATRICE_INTRA[64] = {
		 8, 16, 19, 22, 26, 27, 29, 34,
		16, 16, 22, 24, 27, 29, 34, 37,
		19, 22, 26, 27, 29, 34, 34, 38,
		22, 22, 26, 27, 29, 34, 37, 40,
		22, 26, 27, 29, 32, 35, 40, 48,
		26, 27, 29, 32, 35, 40, 48, 58,
		26, 27, 29, 34, 38, 46, 56, 69,
		27, 29, 35, 38, 46, 56, 69, 83
	};

	/* Figura 7-2: parcurgerea zigzag obisnuita (alternate_scan = 0).
	   ZIGZAG[i] = locul in bloc (rand*8 + coloana) al pasului i. */
	const int ZIGZAG[64] = {
		 0,  1,  8, 16,  9,  2,  3, 10, 17, 24, 32, 25, 18, 11,  4,  5,
		12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13,  6,  7, 14, 21, 28,
		35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
		58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63
	};

	struct CodFix
	{
		unsigned short cod;
		unsigned char lungime;
	};

	/* Tabelul B-12: dct_dc_size_luminance. Indexat dupa marimea diferentei de DC (0..11). */
	const CodFix DC_LUMA[12] = {
		{ 0x004, 3 }, { 0x000, 2 }, { 0x001, 2 }, { 0x005, 3 },
		{ 0x006, 3 }, { 0x00e, 4 }, { 0x01e, 5 }, { 0x03e, 6 },
		{ 0x07e, 7 }, { 0x0fe, 8 }, { 0x1fe, 9 }, { 0x3fe, 10 }
	};

	/* Tabelul B-13: dct_dc_size_chrominance. */
	const CodFix DC_CROMA[12] = {
		{ 0x000, 2 }, { 0x001, 2 }, { 0x002, 2 }, { 0x006, 3 },
		{ 0x00e, 4 }, { 0x01e, 5 }, { 0x03e, 6 }, { 0x07e, 7 },
		{ 0x0fe, 8 }, { 0x1fe, 9 }, { 0x3fe, 10 }, { 0x7fe, 11 }
	};

	/* Tabelul B-14: dct_coefficients_table_zero (intra_vlc_format = 0).
	   Perechea (cate zerouri sari, ce valoare); bitul de semn se scrie dupa cod.
	   Codul "10" e End of Block, iar "000001" e escape; ele nu stau in tablou. */
	struct CodAC
	{
		unsigned char sarit;
		unsigned char nivel;
		unsigned short cod;
		unsigned char lungime;
	};

	// 111 intrari, scoase din tabele.py de genereaza-tabel-b14.py
	static const CodAC TABEL_B14[] = {
		{  0,  1, 0x0003,  2 },  // "11"
		{  0,  2, 0x0004,  4 },  // "0100"
		{  0,  3, 0x0005,  5 },  // "00101"
		{  0,  4, 0x0006,  7 },  // "0000110"
		{  0,  5, 0x0026,  8 },  // "00100110"
		{  0,  6, 0x0021,  8 },  // "00100001"
		{  0,  7, 0x000a, 10 },  // "0000001010"
		{  0,  8, 0x001d, 12 },  // "000000011101"
		{  0,  9, 0x0018, 12 },  // "000000011000"
		{  0, 10, 0x0013, 12 },  // "000000010011"
		{  0, 11, 0x0010, 12 },  // "000000010000"
		{  0, 12, 0x001a, 13 },  // "0000000011010"
		{  0, 13, 0x0019, 13 },  // "0000000011001"
		{  0, 14, 0x0018, 13 },  // "0000000011000"
		{  0, 15, 0x0017, 13 },  // "0000000010111"
		{  0, 16, 0x001f, 14 },  // "00000000011111"
		{  0, 17, 0x001e, 14 },  // "00000000011110"
		{  0, 18, 0x001d, 14 },  // "00000000011101"
		{  0, 19, 0x001c, 14 },  // "00000000011100"
		{  0, 20, 0x001b, 14 },  // "00000000011011"
		{  0, 21, 0x001a, 14 },  // "00000000011010"
		{  0, 22, 0x0019, 14 },  // "00000000011001"
		{  0, 23, 0x0018, 14 },  // "00000000011000"
		{  0, 24, 0x0017, 14 },  // "00000000010111"
		{  0, 25, 0x0016, 14 },  // "00000000010110"
		{  0, 26, 0x0015, 14 },  // "00000000010101"
		{  0, 27, 0x0014, 14 },  // "00000000010100"
		{  0, 28, 0x0013, 14 },  // "00000000010011"
		{  0, 29, 0x0012, 14 },  // "00000000010010"
		{  0, 30, 0x0011, 14 },  // "00000000010001"
		{  0, 31, 0x0010, 14 },  // "00000000010000"
		{  0, 32, 0x0018, 15 },  // "000000000011000"
		{  0, 33, 0x0017, 15 },  // "000000000010111"
		{  0, 34, 0x0016, 15 },  // "000000000010110"
		{  0, 35, 0x0015, 15 },  // "000000000010101"
		{  0, 36, 0x0014, 15 },  // "000000000010100"
		{  0, 37, 0x0013, 15 },  // "000000000010011"
		{  0, 38, 0x0012, 15 },  // "000000000010010"
		{  0, 39, 0x0011, 15 },  // "000000000010001"
		{  0, 40, 0x0010, 15 },  // "000000000010000"
		{  1,  1, 0x0003,  3 },  // "011"
		{  1,  2, 0x0006,  6 },  // "000110"
		{  1,  3, 0x0025,  8 },  // "00100101"
		{  1,  4, 0x000c, 10 },  // "0000001100"
		{  1,  5, 0x001b, 12 },  // "000000011011"
		{  1,  6, 0x0016, 13 },  // "0000000010110"
		{  1,  7, 0x0015, 13 },  // "0000000010101"
		{  1,  8, 0x001f, 15 },  // "000000000011111"
		{  1,  9, 0x001e, 15 },  // "000000000011110"
		{  1, 10, 0x001d, 15 },  // "000000000011101"
		{  1, 11, 0x001c, 15 },  // "000000000011100"
		{  1, 12, 0x001b, 15 },  // "000000000011011"
		{  1, 13, 0x001a, 15 },  // "000000000011010"
		{  1, 14, 0x0019, 15 },  // "000000000011001"
		{  1, 15, 0x0013, 16 },  // "0000000000010011"
		{  1, 16, 0x0012, 16 },  // "0000000000010010"
		{  1, 17, 0x0011, 16 },  // "0000000000010001"
		{  1, 18, 0x0010, 16 },  // "0000000000010000"
		{  2,  1, 0x0005,  4 },  // "0101"
		{  2,  2, 0x0004,  7 },  // "0000100"
		{  2,  3, 0x000b, 10 },  // "0000001011"
		{  2,  4, 0x0014, 12 },  // "000000010100"
		{  2,  5, 0x0014, 13 },  // "0000000010100"
		{  3,  1, 0x0007,  5 },  // "00111"
		{  3,  2, 0x0024,  8 },  // "00100100"
		{  3,  3, 0x001c, 12 },  // "000000011100"
		{  3,  4, 0x0013, 13 },  // "0000000010011"
		{  4,  1, 0x0006,  5 },  // "00110"
		{  4,  2, 0x000f, 10 },  // "0000001111"
		{  4,  3, 0x0012, 12 },  // "000000010010"
		{  5,  1, 0x0007,  6 },  // "000111"
		{  5,  2, 0x0009, 10 },  // "0000001001"
		{  5,  3, 0x0012, 13 },  // "0000000010010"
		{  6,  1, 0x0005,  6 },  // "000101"
		{  6,  2, 0x001e, 12 },  // "000000011110"
		{  6,  3, 0x0014, 16 },  // "0000000000010100"
		{  7,  1, 0x0004,  6 },  // "000100"
		{  7,  2, 0x0015, 12 },  // "000000010101"
		{  8,  1, 0x0007,  7 },  // "0000111"
		{  8,  2, 0x0011, 12 },  // "000000010001"
		{  9,  1, 0x0005,  7 },  // "0000101"
		{  9,  2, 0x0011, 13 },  // "0000000010001"
		{ 10,  1, 0x0027,  8 },  // "00100111"
		{ 10,  2, 0x0010, 13 },  // "0000000010000"
		{ 11,  1, 0x0023,  8 },  // "00100011"
		{ 11,  2, 0x001a, 16 },  // "0000000000011010"
		{ 12,  1, 0x0022,  8 },  // "00100010"
		{ 12,  2, 0x0019, 16 },  // "0000000000011001"
		{ 13,  1, 0x0020,  8 },  // "00100000"
		{ 13,  2, 0x0018, 16 },  // "0000000000011000"
		{ 14,  1, 0x000e, 10 },  // "0000001110"
		{ 14,  2, 0x0017, 16 },  // "0000000000010111"
		{ 15,  1, 0x000d, 10 },  // "0000001101"
		{ 15,  2, 0x0016, 16 },  // "0000000000010110"
		{ 16,  1, 0x0008, 10 },  // "0000001000"
		{ 16,  2, 0x0015, 16 },  // "0000000000010101"
		{ 17,  1, 0x001f, 12 },  // "000000011111"
		{ 18,  1, 0x001a, 12 },  // "000000011010"
		{ 19,  1, 0x0019, 12 },  // "000000011001"
		{ 20,  1, 0x0017, 12 },  // "000000010111"
		{ 21,  1, 0x0016, 12 },  // "000000010110"
		{ 22,  1, 0x001f, 13 },  // "0000000011111"
		{ 23,  1, 0x001e, 13 },  // "0000000011110"
		{ 24,  1, 0x001d, 13 },  // "0000000011101"
		{ 25,  1, 0x001c, 13 },  // "0000000011100"
		{ 26,  1, 0x001b, 13 },  // "0000000011011"
		{ 27,  1, 0x001f, 16 },  // "0000000000011111"
		{ 28,  1, 0x001e, 16 },  // "0000000000011110"
		{ 29,  1, 0x001d, 16 },  // "0000000000011101"
		{ 30,  1, 0x001c, 16 },  // "0000000000011100"
		{ 31,  1, 0x001b, 16 },  // "0000000000011011"
	};
	// sarit maxim = 31, nivel maxim = 40

	const int CATE_B14 = (int)(sizeof(TABEL_B14) / sizeof(TABEL_B14[0]));

	/* Cautare rapida in B-14: din (sarit, nivel) drept in intrarea din tablou.
	   -1 inseamna ca perechea nu are cod propriu si se scrie cu escape. */
	struct CautareAC
	{
		short unde[32][41];

		CautareAC()
		{
			memset(unde, -1, sizeof(unde));
			for (int i = 0; i < CATE_B14; ++i)
				unde[TABEL_B14[i].sarit][TABEL_B14[i].nivel] = (short)i;
		}
	};

	/* Scrie biti unul dupa altul, cel mai greu primul, si ii scoate pe octeti intregi. */
	class ScriitorBiti
	{
	public:
		ScriitorBiti(std::vector<unsigned char> &iesire) : out(iesire), rezerva(0), biti(0) {}

		void pune(unsigned int valoare, int lungime)
		{
			rezerva = (rezerva << lungime) | (valoare & ((1u << lungime) - 1u));
			biti += lungime;
			while (biti >= 8)
			{
				biti -= 8;
				out.push_back((unsigned char)((rezerva >> biti) & 0xffu));
			}
		}

		/* Umplutura de zerouri pana la marginea de octet: fiecare startcod incepe pe octet. */
		void aliniaza()
		{
			if (biti)
				pune(0, 8 - biti);
		}

		void startcod(unsigned char cod)
		{
			aliniaza();
			out.push_back(0);
			out.push_back(0);
			out.push_back(1);
			out.push_back(cod);
		}

	private:
		std::vector<unsigned char> &out;
		unsigned int rezerva;
		int biti;
	};

	class Codor
	{
	public:
		Codor(std::vector<unsigned char> &iesire) : b(iesire)
		{
			/* baza DCT: cos8[u][x] = 1/2 x C(u) x cos((2x+1) u pi / 16), cu C(0) = 1/radical(2) */
			for (int u = 0; u < 8; ++u)
				for (int x = 0; x < 8; ++x)
					cos8[u][x] = 0.5 * (u ? 1.0 : M_SQRT1_2)
						* cos((2.0 * x + 1.0) * u * M_PI / 16.0);
		}

		/* Cei 47 de octeti de antet. Sunt scrisi camp cu camp, dar ies octet cu octet
		   aceiasi ca in ecranele care merg azi pe receptor (dovedit cu cmp -n 47). */
		void antet()
		{
			b.startcod(0xb3);                   /* antet de secventa */
			b.pune(mpeg2intra::LATIME, 12);     /* horizontal_size_value */
			b.pune(mpeg2intra::INALTIME, 12);   /* vertical_size_value */
			b.pune(3, 4);                       /* aspect_ratio_information = 16:9 */
			b.pune(3, 4);                       /* frame_rate_code = 25 cadre pe secunda */
			b.pune(0x3ffff, 18);                /* bit_rate_value: toti 1, adica nelimitat */
			b.pune(1, 1);                       /* marker_bit */
			b.pune(3, 10);                      /* vbv_buffer_size_value: 3 x 16384 octeti */
			b.pune(0, 1);                       /* constrained_parameters_flag */
			b.pune(0, 1);                       /* load_intra_quantiser_matrix: nu, cea implicita */
			b.pune(0, 1);                       /* load_non_intra_quantiser_matrix */

			b.startcod(0xb5);                   /* extensie de secventa */
			b.pune(1, 4);                       /* extension_start_code_identifier */
			b.pune(0x44, 8);                    /* profil Main, nivel High */
			b.pune(1, 1);                       /* progressive_sequence */
			b.pune(1, 2);                       /* chroma_format = 4:2:0 */
			b.pune(0, 2);                       /* horizontal_size_extension */
			b.pune(0, 2);                       /* vertical_size_extension */
			b.pune(0, 12);                      /* bit_rate_extension */
			b.pune(1, 1);                       /* marker_bit */
			b.pune(0, 8);                       /* vbv_buffer_size_extension */
			b.pune(0, 1);                       /* low_delay */
			b.pune(0, 2);                       /* frame_rate_extension_n */
			b.pune(0, 5);                       /* frame_rate_extension_d */

			b.startcod(0xb8);                   /* antet de grup de imagini */
			b.pune(0, 1);                       /* drop_frame_flag */
			b.pune(0, 5);                       /* ore */
			b.pune(0, 6);                       /* minute */
			b.pune(1, 1);                       /* marker_bit */
			b.pune(0, 6);                       /* secunde */
			b.pune(0, 6);                       /* imagini */
			b.pune(1, 1);                       /* closed_gop */
			b.pune(0, 1);                       /* broken_link */
			b.aliniaza();

			b.startcod(0x00);                   /* antet de imagine */
			b.pune(0, 10);                      /* temporal_reference */
			b.pune(1, 3);                       /* picture_coding_type = I */
			b.pune(0xffff, 16);                 /* vbv_delay nedefinit */
			b.pune(0, 1);                       /* extra_bit_picture = 0 (6.2.3): scris, nu lasat umpluturii */
			b.aliniaza();

			b.startcod(0xb5);                   /* extensie de codare a imaginii */
			b.pune(8, 4);                       /* extension_start_code_identifier */
			b.pune(15, 4);                      /* f_code[0][0], nefolosit la imagini I */
			b.pune(15, 4);                      /* f_code[0][1] */
			b.pune(15, 4);                      /* f_code[1][0] */
			b.pune(15, 4);                      /* f_code[1][1] */
			b.pune(0, 2);                       /* intra_dc_precision = 8 biti */
			b.pune(3, 2);                       /* picture_structure = cadru intreg */
			b.pune(0, 1);                       /* top_field_first */
			b.pune(1, 1);                       /* frame_pred_frame_dct: nu se scrie dct_type */
			b.pune(0, 1);                       /* concealment_motion_vectors */
			b.pune(0, 1);                       /* q_scale_type = scara liniara */
			b.pune(0, 1);                       /* intra_vlc_format = 0, adica Tabelul B-14 */
			b.pune(0, 1);                       /* alternate_scan = 0, zigzagul obisnuit */
			b.pune(0, 1);                       /* repeat_first_field */
			b.pune(1, 1);                       /* chroma_420_type */
			b.pune(1, 1);                       /* progressive_frame */
			b.pune(0, 1);                       /* composite_display_flag */
			b.aliniaza();
		}

		/* Cele 68 de felii, cate una pe fiecare rand de macroblocuri. */
		void felii(const unsigned char *planY, const unsigned char *planCb,
			const unsigned char *planCr, int cod_cuantizare)
		{
			const int randuri = mpeg2intra::INALTIME_CODATA / 16;
			const int coloane = mpeg2intra::LATIME / 16;
			/* q_scale_type = 0, deci quantiser_scale = 2 x cod */
			const int cuantizare = 2 * cod_cuantizare;

			for (int rand = 0; rand < randuri; ++rand)
			{
				b.startcod((unsigned char)(rand + 1));
				b.pune((unsigned int)cod_cuantizare, 5);    /* quantiser_scale_code */
				b.pune(0, 1);                               /* extra_bit_slice */

				/* predictorii de DC se reseteaza la 128 la fiecare felie, separat Y, Cb, Cr */
				int pred[3] = { 128, 128, 128 };

				for (int col = 0; col < coloane; ++col)
				{
					b.pune(1, 1);   /* macroblock_address_increment = 1 (Tabelul B-1) */
					b.pune(1, 1);   /* macroblock_type: intra, fara schimbare de cuantizare (B-2) */

					/* cele sase blocuri, in ordinea Y0, Y1, Y2, Y3, Cb, Cr */
					for (int nr = 0; nr < 4; ++nr)
					{
						const unsigned char *p = planY
							+ (rand * 16 + (nr >> 1) * 8) * mpeg2intra::LATIME
							+ col * 16 + (nr & 1) * 8;
						bloc(p, mpeg2intra::LATIME, true, pred[0], cuantizare);
					}
					const int sar = rand * 8 * mpeg2intra::LATIME_CROMA + col * 8;
					bloc(planCb + sar, mpeg2intra::LATIME_CROMA, false, pred[1], cuantizare);
					bloc(planCr + sar, mpeg2intra::LATIME_CROMA, false, pred[2], cuantizare);
				}
				b.aliniaza();
			}
		}

	private:
		/* DCT 8x8 directa, separabila: intai randurile, apoi coloanele.
		   Esantioanele intra asa cum sunt (0..255), FARA scaderea lui 128: la MPEG-2
		   predictorul de DC porneste de la 128 si face acelasi lucru.
		   Pentru un bloc plat de valoare v iese F[0] = 8v. */
		void dct(const unsigned char *sursa, int pas, double *F) const
		{
			double mijloc[64];
			for (int y = 0; y < 8; ++y)
				for (int u = 0; u < 8; ++u)
				{
					double s = 0.0;
					for (int x = 0; x < 8; ++x)
						s += sursa[y * pas + x] * cos8[u][x];
					mijloc[y * 8 + u] = s;
				}
			for (int v = 0; v < 8; ++v)
				for (int u = 0; u < 8; ++u)
				{
					double s = 0.0;
					for (int y = 0; y < 8; ++y)
						s += mijloc[y * 8 + u] * cos8[v][y];
					F[v * 8 + u] = s;
				}
		}

		/* O pereche (cate zerouri sari, ce valoare) din Tabelul B-14. */
		void coeficient(int sarit, int nivel)
		{
			const int marime = nivel < 0 ? -nivel : nivel;
			const short unde = (sarit < 32 && marime <= 40)
				? cautare.unde[sarit][marime] : (short)-1;
			if (unde >= 0)
			{
				b.pune(TABEL_B14[unde].cod, TABEL_B14[unde].lungime);
				b.pune(nivel < 0 ? 1 : 0, 1);   /* ultimul bit al codului e semnul */
			}
			else
			{
				/* escape: 000001, apoi 6 biti de sarit si 12 biti de valoare cu semn */
				b.pune(1, 6);
				b.pune((unsigned int)sarit, 6);
				b.pune((unsigned int)(nivel & 0xfff), 12);
			}
		}

		/* Un bloc 8x8 intra: DC cu diferenta fata de blocul dinainte de acelasi fel,
		   apoi coeficientii AC in ordinea zigzag, la urma End of Block. */
		void bloc(const unsigned char *sursa, int pas, bool e_luma, int &predictor, int cuantizare)
		{
			double F[64];
			dct(sursa, pas, F);

			/* DC: se imparte fix la 8 (intra_dc_mult, cu intra_dc_precision = 0), nu cu matricea */
			int dc = (int)(F[0] / 8.0 + 0.5);
			if (dc < 0)
				dc = 0;
			else if (dc > 255)
				dc = 255;
			const int diferenta = dc - predictor;
			predictor = dc;

			int marime = 0;
			for (int m = diferenta < 0 ? -diferenta : diferenta; m; m >>= 1)
				++marime;
			const CodFix *tabel = e_luma ? DC_LUMA : DC_CROMA;
			b.pune(tabel[marime].cod, tabel[marime].lungime);
			if (marime)
			{
				/* diferenta negativa se scrie ca valoare + (1 << marime) - 1 */
				const int valoare = diferenta > 0 ? diferenta : diferenta + (1 << marime) - 1;
				b.pune((unsigned int)valoare, marime);
			}

			int zerouri = 0;
			for (int i = 1; i < 64; ++i)
			{
				const int poz = ZIGZAG[i];
				/* cuantizare intra: QF = 16 F / (W x quantiser_scale), rotunjit la cel mai apropiat.
				   Decodorul face inapoi F'' = (2 QF W quantiser_scale) / 32. */
				const double q = F[poz] * 16.0 / (MATRICE_INTRA[poz] * (double)cuantizare);
				int nivel = (int)(q >= 0.0 ? q + 0.5 : q - 0.5);
				if (nivel > 2047)
					nivel = 2047;
				else if (nivel < -2047)
					nivel = -2047;
				if (!nivel)
				{
					++zerouri;
					continue;
				}
				coeficient(zerouri, nivel);
				zerouri = 0;
			}
			b.pune(2, 2);   /* End of Block */
		}

		ScriitorBiti b;
		CautareAC cautare;
		double cos8[8][8];
	};

	/* Esantioanele raman in 1..254. Regula e din ITU-R BT.601 (interfata digitala tine 0 si 255 pentru
	   semnalele de sincronizare), nu din MPEG-2: decodorul MPEG-2 primeste si 0, si 255. Pe drumul din
	   enigma2 limitarea nu se atinge niciodata, fiindca BT.601 cu domeniu limitat da oricum 16..235. */
	inline int limiteaza(int v)
	{
		if (v < 1)
			return 1;
		if (v > 254)
			return 254;
		return v;
	}
}

namespace mpeg2intra
{

void dinBGRA(const unsigned char *bgra, int pas,
	unsigned char *planY, unsigned char *planCb, unsigned char *planCr)
{
	/* BT.601 cu domeniu limitat (alb 235, negru 16). Coeficientii sunt 65,481 / 128,553 / 24,966
	   si perechile lor, inmultiti cu 65536/255 si rotunjiti, ca sa se lucreze pe numere intregi. */
	for (int y = 0; y < INALTIME_CODATA; ++y)
	{
		/* randurile 1080..1087 copiaza randul 1079: nu se vad, dar trebuie sa existe */
		const int sy = y < INALTIME ? y : INALTIME - 1;
		const unsigned char *s = bgra + (long)sy * pas;
		unsigned char *d = planY + (long)y * LATIME;
		for (int x = 0; x < LATIME; ++x, s += 4)
			d[x] = (unsigned char)limiteaza(
				(16829 * s[2] + 33039 * s[1] + 6416 * s[0] + (16 << 16) + 32768) >> 16);
	}

	/* croma 4:2:0: media a patru pixeli vecini (2x2) */
	for (int y = 0; y < INALTIME_CROMA; ++y)
	{
		const int sy0 = (2 * y) < INALTIME ? (2 * y) : INALTIME - 1;
		const int sy1 = (2 * y + 1) < INALTIME ? (2 * y + 1) : INALTIME - 1;
		const unsigned char *r0 = bgra + (long)sy0 * pas;
		const unsigned char *r1 = bgra + (long)sy1 * pas;
		unsigned char *db = planCb + (long)y * LATIME_CROMA;
		unsigned char *dr = planCr + (long)y * LATIME_CROMA;
		for (int x = 0; x < LATIME_CROMA; ++x)
		{
			int sumb = 0;
			int sumr = 0;
			for (int k = 0; k < 4; ++k)
			{
				const unsigned char *p = ((k & 2) ? r1 : r0) + (2 * x + (k & 1)) * 4;
				sumb += (-9714 * p[2] - 19071 * p[1] + 28784 * p[0] + (128 << 16) + 32768) >> 16;
				sumr += (28784 * p[2] - 24103 * p[1] - 4681 * p[0] + (128 << 16) + 32768) >> 16;
			}
			db[x] = (unsigned char)limiteaza((sumb + 2) >> 2);
			dr[x] = (unsigned char)limiteaza((sumr + 2) >> 2);
		}
	}
}

int codeaza(const unsigned char *planY, const unsigned char *planCb, const unsigned char *planCr,
	int cod_cuantizare, std::vector<unsigned char> &iesire)
{
	if (!planY || !planCb || !planCr)
		return -1;
	if (cod_cuantizare < 1 || cod_cuantizare > 31)
		return -2;

	iesire.clear();
	/* 4 MB cerute o singura data: cel mai mare fisier masurat are 3,6 MB (zgomot la cuantizarea 1), iar la
	   cuantizarea de pornire din enigma2 (4) o poza foarte incarcata ajunge la 1,7 MB. Cu 1 MB vectorul s-ar
	   fi marit de doua-trei ori, iar enigma2 e compilat cu -fno-exceptions: o marire cazuta nu se poate
	   prinde, opreste receptorul. */
	iesire.reserve(4 << 20);

	Codor c(iesire);
	c.antet();
	c.felii(planY, planCb, planCr, cod_cuantizare);

	/* fara cod de sfarsit de secventa (B7): asa arata si fisierele care merg azi pe receptor */
	return 0;
}

}
