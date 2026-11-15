/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdscalitate.h: calitatea semnalului (raportul semnal/zgomot) pentru tunerele placilor HiSilicon cu libreader
 * (Octagon SF8008, SF8008 MINI, primul Amiko Viper 4K). Numai o functie pura, fara enigma2, ca sa se probeze singura,
 * pe PC.
 *
 * Driverul acestor placi (hi-dvb.ko) da in FE_READ_SNR raportul in zecimi sau sutimi de dB, nu pe scara 0..65535:
 * fara formula tunerului procentul iesea snr / 65536, adica 0-2 % cu imagine buna. Formula e cea folosita in general
 * pentru aceleasi nume de tuner (numele din /proc/bus/nim_sockets, scris de driver):
 *   "Si2166D..."          DVB-S/S2, sutimi de dB; 100 % = 16,2 dB;
 *   "ATBM7821 DVB-T2/C"   DVB-T/T2 si DVB-C, zecimi de dB; 100 % = 42 dB;
 *   "AVL62X1"             DVB-S/S2 (SF8008 Supreme), sutimi de dB; 100 % = maximul de satelit al apelantului (16 dB).
 * Alte nume nu se schimba (functia nu atinge nimic): tunerele Amiko Viper 4K V20, V30 si V40 se numesc "DVB-S2 NIM",
 * "DVB-C NIM", "DVB-C,T/T2 NIM", "HISI 3136 DVB-S" sau "Philips dvbc DVB-C".
 */

#ifndef __lib_dvb_hdscalitate_h
#define __lib_dvb_hdscalitate_h

#include <string.h>

namespace hdscal
{
	/* ret: sutimi de dB; sat_max, ter_max, cab_max: valoarea de 100 %, tot in sutimi de dB.
	 * Intoarce true cand numele e al unui tuner cunoscut aici (si a pus valorile), false altfel (nimic schimbat). */
	inline bool calitateTuner(const char *descriere, int snr, int &ret, int &sat_max, int &ter_max, int &cab_max)
	{
		if (!descriere)
			return false;
		if (!strncmp(descriere, "Si2166D", 7))
		{
			ret = snr;
			sat_max = 1620;
			return true;
		}
		if (!strcmp(descriere, "ATBM7821 DVB-T2/C"))
		{
			ret = snr * 10;
			ter_max = 4200;
			cab_max = 4200;
			return true;
		}
		if (!strcmp(descriere, "AVL62X1"))
		{
			ret = snr;
			return true;
		}
		/* HDSatelit (0.7.5, 15.11.2026, TNB): tunerele Broadcom FBC (GigaBlue UHD Quad 4K Pro si Vu+ 4K:
		 * "DVB-S2X NIM(45308X FBC)", "DVB-S2 NIM(45308 FBC)", "DVB-S2 NIM(45208 FBC)") dau FE_READ_SNR pe scara 0..65535.
		 * Fara formula, calitatea in dB ramanea 0x12345678 ("nu se stie"): bucla motorului compara doua valori egale
		 * (proba de stabilitate a celor 5 pasi era oarba) si ecranele nu aratau dB. Formula pe bucati e cea din
		 * OE-Alliance enigma2 (lib/dvb/frontend.cpp, aceleasi trei nume, GPL-2.0), in sutimi de dB; 65535 = ~16,4 dB. */
		if (strstr(descriere, "NIM(45308X FBC)") || strstr(descriere, "NIM(45308 FBC)") || strstr(descriere, "NIM(45208 FBC)"))
		{
			ret = (int)(snr < 57500 ? (snr < 52500 ? (snr < 32200 ? 0.02640 * snr + 0.0 : 0.02604 * snr + 11.55125)
				: 0.01310 * snr + 661.55172) : 0.02826 * snr - 210.);
			return true;
		}
		return false;
	}
}

#endif
