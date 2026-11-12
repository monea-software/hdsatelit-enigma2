/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdssoftcsapornire.h: hotararea pornirii devreme a buclei SoftCSA (0.7.4), fara nimic din enigma2, ca sa se poata
 * proba pe PC (teste/test_softcsa_pornire_074.py o compileaza si o ruleaza).
 *
 * DE CE: pe un canal CSA-ALT drumul obisnuit porneste intai decodorul pe placa (cu PID-urile tinute minte, la acordare),
 * asteapta PMT-ul si ECM-ul, apoi elibereaza decodorul si face altul pe demuxul buclei (servicedvb.cpp, softCsaSwitch).
 * Masurat pe Octagon SF8008 (11.11.2026): Sky Nature cu imagine la 1432 ms, fata de 794 ms pe un canal descifrat de placa.
 * Cand nucleul stie deja canalul CSA-ALT (ECM-ul lui analizat de la pornirea interfetei, cu modul ECM tinut minte:
 * eDVBCSASession::cachedCsaAlt = 1), bucla porneste odata cu primul program si decodorul se face direct pe ea.
 *
 * CAND DA (toate): canalul viu al ferestrei principale (nu fisier, nu flux, nu timeshift), inca fara decodor si fara
 * sesiune, stiut CSA-ALT din ECM (1; nu 2 = numai cuvinte venite fara ECM analizat, nici -1 sau 0), cu un CAID VideoGuard
 * in program, descifrarea in software gata (biblioteca, modulul cu protocolul 3 si cuvintele extinse) si niciun modul CI
 * pus pe serviciu. Altfel ramane drumul de azi.
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */
#ifndef __lib_service_hdssoftcsapornire_h
#define __lib_service_hdssoftcsapornire_h

#include <stdint.h>

namespace hdssoftcsa
{

/* CSA-ALT exista numai la VideoGuard (CAID 0x09xx) */
inline bool videoGuard(uint16_t caid)
{
	return (caid >> 8) == 0x09;
}

/* PID-ul ECM din PMT; in programul din PID-urile tinute minte nu se stie (-1) */
inline bool pidEcmBun(int pid)
{
	return pid > 0 && pid < 0x1fff;
}

struct Pornire
{
	bool principal;   /* fereastra principala */
	bool fisier;      /* inregistrare sau fisier */
	bool flux;        /* flux http */
	bool timeshift;   /* bufferul timeshift se reda */
	bool decodor;     /* decodorul exista deja */
	bool sesiune;     /* sesiunea SoftCSA exista deja */
	int csa_alt;      /* eDVBCSASession::cachedCsaAlt: -1 nestiut, 0 nu, 1 CSA-ALT */
	bool videoguard;  /* programul are un CAID VideoGuard (din PMT sau din lista de canale) */
	bool gata;        /* eDVBCAHandler::softCsaReady */
	bool ci;          /* un modul CI e pus pe serviciu (eDVBCIInterfaces::isHandlerAssigned) */
	Pornire(): principal(false), fisier(false), flux(false), timeshift(false), decodor(false), sesiune(false),
		csa_alt(-1), videoguard(false), gata(false), ci(false) {}
};

/* bucla porneste inaintea decodorului, fara PMT si fara ECM */
inline bool pornesteDevreme(const Pornire &p)
{
	return p.principal && !p.fisier && !p.flux && !p.timeshift && !p.decodor && !p.sesiune && p.csa_alt == 1
		&& p.videoguard && p.gata && !p.ci;
}

/* bucla pornita devreme (din memoria canalului, fara niciun ECM al acestui zap) se opreste cand PMT-ul venit nu are niciun
   ECM VideoGuard: canalul nu poate fi CSA-ALT acum, decodorul trece inapoi pe demuxul viu. O bucla pornita din ECM-ul
   acestui zap ramane ca pana acum. */
inline bool inapoiPePlaca(bool pmt_venit, bool bucla_devreme, bool are_ecm_videoguard)
{
	return pmt_venit && bucla_devreme && !are_ecm_videoguard;
}

}

#endif
