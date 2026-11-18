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

/*
 * MI7 (15.11.2026): campul tp= din randul de esec al jurnalului de zap (hdsjurnalzap.cpp, textCanal) la canalul pus prin
 * releu. Lista de canale nu stie transponderul unui flux, deci randul scria "tp=?"; acum scrie feed-ul si PLP-ul din cale:
 * "http://127.0.0.1:8889/t2/<feed>/<plp>" -> "t2/<feed>/<plp>". Fara spatii (tp= ramane un singur cuvant): se opreste la
 * spatiu, ghilimele, ':', '?', '#' si dupa al doilea '/'. Gol cand calea nu e a releului; "t2/?" cand lipseste feed-ul.
 */
static inline std::string hdsReleuT2Tp(const std::string &cale)
{
	if (!hdsEsteReleuT2(cale))
		return std::string();
	std::string mic(cale);
	for (std::string::size_type i = 0; i < mic.size(); ++i)
		if (mic[i] >= 'A' && mic[i] <= 'Z')
			mic[i] = mic[i] - 'A' + 'a';
	static const char marcaj[] = "8889/t2/";
	std::string::size_type p = mic.find(marcaj);
	if (p == std::string::npos)
		return std::string();
	std::string rest(cale.substr(p + sizeof(marcaj) - 1));
	std::string tp("t2/");
	int bare = 0;
	for (std::string::size_type i = 0; i < rest.size(); ++i)
	{
		char c = rest[i];
		if (c == ' ' || c == '\t' || c == '"' || c == ':' || c == '?' || c == '#' || c == '\r' || c == '\n')
			break;
		if (c == '/' && ++bare == 2)
			break;
		tp += c;
	}
	if (tp.size() == 3 || tp[3] == '/')
		return "t2/?";
	if (tp[tp.size() - 1] == '/')
		tp.erase(tp.size() - 1);
	return tp;
}

#endif
