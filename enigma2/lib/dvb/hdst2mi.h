/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdst2mi.h: alegerea tunerului pentru un transponder DVB-S2 cu T2-MI (campurile t2mi_plp_id / t2mi_pid scrise de
 * listele facute pe alte imagini) pe receptoarele cu tunere amestecate: unele decapsuleaza T2-MI in driver
 * (HiSilicon: /proc/stb/frontend/N/t2mi), altele nu (un tuner pe USB sau de alt fel langa ele). frontend.cpp trimite
 * PID-ul si PLP-ul driverului la acordare (DTV_ISDBT_SB_SEGMENT_IDX), dar numai driverul cu T2-MI le foloseste: pe
 * celalalt tuner canalul ar da numai PID-ul T2-MI redat ca sunet. De aceea, cand receptorul are macar un tuner cu
 * T2-MI, isCompatibleWith nu da transponderul T2-MI celui fara (ca OE-Alliance, isT2MI); daca tunerul cu T2-MI e
 * ocupat sau nu prinde satelitul, Python (Hds/DabT2/pornire.py, _t2mi_direct_acum) duce canalul prin releul nostru,
 * care acorda transponderul fara campuri T2-MI si merge pe orice tuner. Pe receptoarele fara niciun tuner cu T2-MI
 * (Vu+, Broadcom) si pe cele cu toate tunerele cu T2-MI (SF8008) nimic nu se schimba.
 *
 * Indicele N din /proc/stb/frontend/N este m_dvbid (frontend-ul DVB, Frontend_Device din /proc/bus/nim_sockets), la fel
 * in Python (Hds/DabT2/straine.py, tunere_t2mi). procfs nu se schimba cat merge enigma2: citit o data, tinut minte.
 */

#ifndef __lib_dvb_hdst2mi_h
#define __lib_dvb_hdst2mi_h

#include <stdio.h>
#include <unistd.h>

namespace hdst2mi
{
	enum { MAX_FE = 16 };

	/* Campurile T2-MI ale transponderului ajung la driver (aceeasi poarta ca in setFrontend: PLP 0..255, PID 1..0x1FFE,
	 * numai la DVB-S2). Functie pura. */
	inline bool areT2mi(bool dvbs2, int t2mi_plp_id, int t2mi_pid)
	{
		return dvbs2 && t2mi_plp_id >= 0 && t2mi_plp_id <= 255 && t2mi_pid > 0 && t2mi_pid <= 0x1FFE;
	}

	/* Tunerul poate primi transponderul? Fara T2-MI pe transponder: da. Cu T2-MI: tunerul cu T2-MI in driver da;
	 * cel fara, numai daca receptorul n-are niciun tuner cu T2-MI (acolo Python duce canalul prin releu inainte de
	 * acordare, iar o alocare ramasa nu se strica fata de cum era). Functie pura. */
	inline bool tunerPrimeste(bool transponder_t2mi, bool tuner_t2mi, bool receptor_t2mi)
	{
		return !transponder_t2mi || tuner_t2mi || !receptor_t2mi;
	}

	/* /proc/stb/frontend/<fe>/t2mi exista (driverul decapsuleaza T2-MI). Tinut minte pe frontend. */
	inline bool tunerCuT2mi(int fe)
	{
		static signed char tinut[MAX_FE];		// 0 necitit, 1 nu, 2 da
		if (fe < 0 || fe >= MAX_FE)
			return false;
		if (!tinut[fe])
		{
			char cale[48];
			snprintf(cale, sizeof(cale), "/proc/stb/frontend/%d/t2mi", fe);
			tinut[fe] = ::access(cale, F_OK) == 0 ? 2 : 1;
		}
		return tinut[fe] == 2;
	}

	/* Macar un frontend al receptorului decapsuleaza T2-MI. */
	inline bool receptorCuT2mi()
	{
		static signed char tinut;			// 0 necitit, 1 nu, 2 da
		if (!tinut)
		{
			tinut = 1;
			for (int fe = 0; fe < MAX_FE; ++fe)
				if (tunerCuT2mi(fe))
				{
					tinut = 2;
					break;
				}
		}
		return tinut == 2;
	}
}

#endif
