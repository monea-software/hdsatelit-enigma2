/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_dvb_hdsepgloc_h
#define __lib_dvb_hdsepgloc_h

/*
 * HDSatelit 0.8.0 (EPG1): locul ghidului importat de pluginurile de ghid (EPGImport si celelalte, eEPGCache::importExternEvents).
 *
 * Pana in 0.7.9 locul era fix: 100000 de emisiuni si 64 MiB socotiti (EXTERN_TOTAL, EXTERN_OCTETI). Pe 26.11.2026 doua
 * receptoare din Italia (DM920, SF8008) l-au umplut cu 550-750 MB de memorie disponibila: "366267 peste plafon; in ghid
 * 100000" (asistentele AS226 si AS230), iar emisiunile italiene, venite dupa altele, nu mai intrau.
 *
 * Acum locul se socoteste la inceputul fiecarui import, dupa receptor:
 *   ce tine deja ghidul importat + jumatate din memoria disponibila peste rezerva (MemAvailable - EXTERN_MEMORIE_MIN_KB),
 *   cel mult cat e liber pe discul fisierului ghidului (epg.dat ajunge la ~60% din octetii socotiti),
 *   niciodata sub cat era pana acum (podeaua) si nici peste tavan,
 *   si niciodata sub ce tine deja ghidul (altfel, cu discul mai plin dupa scrierea epg.dat, importul urmator ar refuza
 *   tot, si inlocuirile).
 * Numarul de emisiuni creste in aceeasi masura (aceeasi proportie ca podeaua). Fara /proc/meminfo ramane podeaua.
 * Paza de memorie de dinainte (hdsEpgMemorieBuna: sub EXTERN_MEMORIE_MIN_KB nu se mai primeste nimic, recitita la
 * 512 inserari) ramane neschimbata.
 *
 * Toate socotelile in long long: pe ARM32 long are 32 de biti, iar KiB x 1024 trece peste 2 GiB.
 * Functie curata (fara fisiere, fara ceas), probata pe PC: teste/epg1_loc_proba.cpp.
 */

struct hdsEpgLoc
{
	long long octeti;
	long long evenimente;
};

/*
 * tinuti / tinutiEvenimente: octetii socotiti si evenimentele ghidului importat de acum (eventData::ExternBytes,
 *   eventData::ExternCount);
 * memorieKb: MemAvailable in KiB, < 0 cand nu se poate citi;
 * rezervaKb: memoria lasata altora (EXTERN_MEMORIE_MIN_KB);
 * discKb: KiB liberi pe sistemul de fisiere al ghidului, < 0 cand nu se stie;
 * podeaOcteti / podeaEvenimente: locul de pana in 0.7.9; tavanOcteti: cel mai mult.
 */
static inline hdsEpgLoc hdsEpgLocSocotit(long long tinuti, long long tinutiEvenimente, long long memorieKb, long long rezervaKb,
	long long discKb, long long podeaOcteti, long long podeaEvenimente, long long tavanOcteti)
{
	hdsEpgLoc loc;
	long long octeti = podeaOcteti;
	if (memorieKb >= 0)
	{
		long long peste = memorieKb - rezervaKb;
		if (peste < 0)
			peste = 0;
		octeti = (tinuti > 0 ? tinuti : 0) + peste * 1024LL / 2;
		if (discKb >= 0 && octeti > discKb * 1024LL / 2)  /* coordonator: epg.dat (~60%) ia cel mult ~30% din discul liber */
			octeti = discKb * 1024LL / 2;
	}
	if (octeti > tavanOcteti)
		octeti = tavanOcteti;
	if (octeti < podeaOcteti)
		octeti = podeaOcteti;
	if (octeti < tinuti)
		octeti = tinuti;
	loc.octeti = octeti;
	loc.evenimente = podeaOcteti > 0 ? podeaEvenimente * octeti / podeaOcteti : podeaEvenimente;
	if (loc.evenimente < tinutiEvenimente)
		loc.evenimente = tinutiEvenimente;
	return loc;
}

#endif
