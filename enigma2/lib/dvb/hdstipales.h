/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdstipales.h: tipul ales in Python pentru un tuner cu mai multe sisteme fara /proc/stb/frontend/N/mode (Dreambox
 * DM900/DM920/DM7080 cu Si2169C/D: satelit, cablu si terestru pe acelasi frontend, ales de nucleu dupa canal). Nucleul
 * spune ca fiecare tuner poate primi orice sistem (DTV_ENUM_DELSYS), deci la un canal terestru isCompatibleWith dadea
 * acelasi scor tuturor, iar allocateFrontend lua primul: tunerul A, pus pe satelit, in locul lui B, pus pe terestru
 * (DMV6, DM900, asistenta 507366). Numai functii pure, fara enigma2, ca sa se probeze singure, pe PC.
 *
 * ales: bitii tipurilor alese de om (1 << feSatellite, 1 << feCable, 1 << feTerrestrial), ca m_delsys_types; negativ =
 * Python n-a spus nimic (toate celelalte receptoare): scorul ramane exact cel vechi.
 */

#ifndef __lib_dvb_hdstipales_h
#define __lib_dvb_hdstipales_h

namespace hdstip
{
	enum { SATELIT = 0, CABLU = 1, TERESTRU = 2, NESPUS = -1 };

	/* Scorul unui tuner pentru un canal de cablu sau terestru (tip), pornind de la scorul de pana acum (vechi):
	   - nespus: vechi, neschimbat;
	   - tipul canalului e cel ales: vechi + 1, tunerul ales pentru el trece inaintea celorlalte;
	   - tunerul e ales numai pentru satelit: 0, nu primeste canalul (intrarea lui e la antena de satelit; si tunerul
	     preferat din Setari, care castiga orice scor pozitiv, il ocoleste);
	   - alt tip de cablu/terestru ales (DVB-C cand canalul e DVB-T, sau invers): vechi, ca pana acum (pe Si2169C cablul
	     si terestrul intra pe aceeasi mufa). */
	inline int scor(int tip, int ales, int vechi)
	{
		if (ales < 0 || (tip != CABLU && tip != TERESTRU) || vechi <= 0)
			return vechi;
		if (ales & (1 << tip))
			return vechi + 1;
		if (!(ales & ((1 << CABLU) | (1 << TERESTRU))))
			return 0;
		return vechi;
	}
}

#endif
