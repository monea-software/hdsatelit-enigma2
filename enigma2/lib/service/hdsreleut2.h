/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsreleut2.h: recunoaste calea unui canal pus prin releul T2-MI local al imaginii (Hds/DabT2, portul 8889,
 * „http://127.0.0.1:8889/t2/<flux>/<plp>”, vezi buchete.py). Jurnalul schimbarii de canal (hdsjurnalzap) e pornit
 * numai pentru canalele de pe tuner; fluxurile de internet raman afara (ar umple hds-zap.log), dar comutarile pe
 * releul T2 trebuie sa se vada, cu timpii si esecurile (proba pe Octagon SF8008 Supreme, 06.11.2026: niciun rand).
 * Numai <string>, ca sa se probeze singur pe PC (teste/test_supreme_defecte_071.py).
 */
#ifndef __lib_service_hdsreleut2_h
#define __lib_service_hdsreleut2_h

#include <string>

static inline bool hdsEsteReleuT2(const std::string &cale)
{
	/* calea vine decodata („http://127.0.0.1:8889/t2/...”); se primeste si forma cu „%3a”, cum sta in bucheturi */
	static const char *const forme[] = {
		"http://127.0.0.1:8889/t2/", "http://localhost:8889/t2/",
		"http%3a//127.0.0.1%3a8889/t2/", "http%3a//localhost%3a8889/t2/",
	};
	std::string mic(cale.substr(0, 40));
	for (std::string::size_type i = 0; i < mic.size(); ++i)
		if (mic[i] >= 'A' && mic[i] <= 'Z')
			mic[i] = mic[i] - 'A' + 'a';
	for (unsigned i = 0; i < sizeof(forme) / sizeof(forme[0]); ++i)
	{
		std::string f(forme[i]);
		if (mic.compare(0, f.size(), f) == 0)
			return true;
	}
	return false;
}

#endif
