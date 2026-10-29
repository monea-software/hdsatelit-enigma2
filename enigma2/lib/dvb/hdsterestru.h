/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsterestru.h: DVB-T si DVB-T2 pe tunerul terestru: sistemul si PLP-ul, randul `t` din lamedb, latimea de banda in
 * Hz pentru DTV_BANDWIDTH_HZ, descriptorul T2 din NIT. Numai functii pure, fara enigma2, ca sa se probeze singure, pe PC.
 *
 * Valorile, la fel in structura eDVBFrontendParametersTerrestrial, in lamedb, in terrestrial.xml si in Python (cele
 * noi sunt adaugate dupa Auto, deci numerele vechi isi pastreaza intelesul):
 *   system             0 DVB-T, 1 DVB-T2; orice alta valoare citita devine DVB-T (asa se acordau toate pana acum);
 *   plp_id             0..255 = PLP-ul ales (numai la DVB-T2); -1 = PLP-ul implicit al multiplexului, ales de driver;
 *   bandwidth          0 8 MHz, 1 7 MHz, 2 6 MHz, 3 Auto, 4 5 MHz, 5 1,712 MHz, 6 10 MHz;
 *   modulation         0 QPSK, 1 16QAM, 2 64QAM, 3 Auto, 4 256QAM;
 *   code_rate HP/LP    0 1/2, 1 2/3, 2 3/4, 3 5/6, 4 7/8, 5 Auto, 7 8/9, 8 3/5, 9 4/5 (6 e scris diferit de liste: Auto);
 *   transmission_mode  0 2k, 1 8k, 2 Auto, 3 4k, 4 1k, 5 16k, 6 32k;
 *   guard_interval     0 1/32, 1 1/16, 2 1/8, 3 1/4, 4 Auto, 5 1/128, 6 19/128, 7 19/256;
 *   hierarchy          0 fara, 1, 2, 3 (4), 4 Auto.
 * Randul `t` din lamedb: frecventa:latime:fec_hp:fec_lp:modulatie:mod:garda:ierarhie:inversare:steaguri (10 campuri, ce
 * scria imaginea pana acum) urmat de :system:plp_id (12, forma de acum, aceeasi ordine ca listele altor receptoare).
 * Se citesc 10, 11 sau 12 campuri; un rand DVB-T are PLP-ul implicit, orice ar scrie.
 */

#ifndef __lib_dvb_hdsterestru_h
#define __lib_dvb_hdsterestru_h

#include <stdio.h>
#include <stddef.h>
#include <stdlib.h>

namespace hdster
{
	enum
	{
		SISTEM_T = 0,
		SISTEM_T2 = 1,
		PLP_IMPLICIT = -1,
		/* in structura (enum-urile din frontendparms.h, aceleasi numere) */
		BW_8 = 0, BW_7 = 1, BW_6 = 2, BW_AUTO = 3, BW_5 = 4, BW_1_712 = 5, BW_10 = 6,
		MOD_AUTO = 3, MOD_256 = 4,
		FEC_AUTO = 5,
		TM_AUTO = 2,
		GI_AUTO = 4,
		IER_AUTO = 4,
		INV_AUTO = 2,
		/* descriptorul T2 din NIT (extensia 0x04 a descriptorului 0x7F): frecventele sunt in unitati de 10 Hz */
		T2_DESCRIPTOR = 0x04,
	};

	inline int sistemNormalizat(int sistem)
	{
		return sistem == SISTEM_T2 ? SISTEM_T2 : SISTEM_T;
	}

	inline int plpNormalizat(int sistem, int plp)
	{
		return (sistemNormalizat(sistem) == SISTEM_T2 && plp >= 0 && plp <= 255) ? plp : PLP_IMPLICIT;
	}

	/* DTV_BANDWIDTH_HZ: Auto (si orice valoare necunoscuta) e 0, adica: driverul o afla */
	inline unsigned int latimeHz(int bandwidth)
	{
		switch (bandwidth)
		{
		case BW_8: return 8000000;
		case BW_7: return 7000000;
		case BW_6: return 6000000;
		case BW_5: return 5000000;
		case BW_1_712: return 1712000;
		case BW_10: return 10000000;
		default: return 0;
		}
	}

	/* citirea inapoi: latimea in Hz de la driver -> valoarea din structura */
	inline int latimeDinHz(unsigned int hz)
	{
		switch (hz)
		{
		case 8000000: return BW_8;
		case 7000000: return BW_7;
		case 6000000: return BW_6;
		case 5000000: return BW_5;
		case 1712000: return BW_1_712;
		case 10000000: return BW_10;
		default: return BW_AUTO;
		}
	}

	/* valorile pe care structura le stie; orice altceva trece pe Auto (asa le si trimite prepare_terrestrial) */
	inline int latimeValida(int v) { return (v >= BW_8 && v <= BW_10) ? v : BW_AUTO; }
	inline int modulatieValida(int v) { return (v >= 0 && v <= MOD_256) ? v : MOD_AUTO; }
	inline int fecValid(int v) { return ((v >= 0 && v <= FEC_AUTO) || (v >= 7 && v <= 9)) ? v : FEC_AUTO; }
	inline int modTransmisieValid(int v) { return (v >= 0 && v <= 6) ? v : TM_AUTO; }
	inline int gardaValida(int v) { return (v >= 0 && v <= 7) ? v : GI_AUTO; }
	inline int ierarhieValida(int v) { return (v >= 0 && v <= IER_AUTO) ? v : IER_AUTO; }
	inline int inversareValida(int v) { return (v >= 0 && v <= INV_AUTO) ? v : INV_AUTO; }

	struct LinieTerestru
	{
		int frequency, bandwidth, code_rate_HP, code_rate_LP, modulation, transmission_mode, guard_interval, hierarchy,
			inversion, flags, system, plp_id;
	};

	/* randul `t` fara "t " in fata; intoarce cate campuri s-au citit (cel putin 1 pentru un rand bun). Campurile lipsa
	   raman pe implicit (Auto, steaguri 0, DVB-T, PLP implicit). */
	inline int citesteLinieTerestru(const char *text, LinieTerestru &l)
	{
		l.frequency = 0;
		l.bandwidth = BW_AUTO;
		l.code_rate_HP = l.code_rate_LP = FEC_AUTO;
		l.modulation = MOD_AUTO;
		l.transmission_mode = TM_AUTO;
		l.guard_interval = GI_AUTO;
		l.hierarchy = IER_AUTO;
		l.inversion = INV_AUTO;
		l.flags = 0;
		l.system = SISTEM_T;
		l.plp_id = PLP_IMPLICIT;
		if (!text)
			return 0;
		int n = sscanf(text, "%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d", &l.frequency, &l.bandwidth, &l.code_rate_HP,
			&l.code_rate_LP, &l.modulation, &l.transmission_mode, &l.guard_interval, &l.hierarchy, &l.inversion,
			&l.flags, &l.system, &l.plp_id);
		if (n < 0)
			n = 0;
		l.system = sistemNormalizat(l.system);
		l.plp_id = plpNormalizat(l.system, l.plp_id);
		return n;
	}

	/* forma de acum: 12 campuri */
	inline int scrieLinieTerestru(char *buf, size_t marime, const LinieTerestru &l)
	{
		int sistem = sistemNormalizat(l.system);
		return snprintf(buf, marime, "%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d", l.frequency, l.bandwidth, l.code_rate_HP,
			l.code_rate_LP, l.modulation, l.transmission_mode, l.guard_interval, l.hierarchy, l.inversion, l.flags,
			sistem, plpNormalizat(sistem, l.plp_id));
	}

	/* doua acordari pe aceeasi frecventa duc la acelasi multiplex, afara de doua PLP-uri alese si diferite */
	inline bool acelasiPlp(int a, int b)
	{
		return a < 0 || b < 0 || a == b;
	}

	/* aceeasi frecventa terestra (Hz): canalele sunt la 7 sau 8 MHz unul de altul, NIT-ul poate da un decalaj mic */
	inline bool aceeasiFrecventa(unsigned int a, unsigned int b)
	{
		return (a > b ? a - b : b - a) < 1000000;
	}

	/* descriptorul T2 (EN 300 468, 6.4.6.3) -> valorile din structura */
	inline int latimeDinDescriptorT2(int cod)
	{
		switch (cod)
		{
		case 0: return BW_8;
		case 1: return BW_7;
		case 2: return BW_6;
		case 3: return BW_5;
		case 4: return BW_10;
		case 5: return BW_1_712;
		default: return BW_AUTO;
		}
	}

	inline int gardaDinDescriptorT2(int cod)
	{
		static const int tabel[] = { 0, 1, 2, 3, 5, 6, 7 };   /* 1/32 1/16 1/8 1/4 1/128 19/128 19/256 */
		return (cod >= 0 && cod <= 6) ? tabel[cod] : GI_AUTO;
	}

	inline int modDinDescriptorT2(int cod)
	{
		static const int tabel[] = { 0, 1, 3, 4, 5, 6 };      /* 2k 8k 4k 1k 16k 32k */
		return (cod >= 0 && cod <= 5) ? tabel[cod] : TM_AUTO;
	}
}

#endif
