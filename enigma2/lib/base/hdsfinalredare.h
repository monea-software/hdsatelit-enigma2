/* HD Satelit (hdsatelit.com, moneasoftware.com), 2026 */
/*
 * Sfarsitul redarii din fisier (timeshift, inregistrari, filme), in eFilePushThread.
 *
 * La capatul fisierului firul asteapta ca driverul sa fi luat tot („wait for driver eof ok”) si trimitea imediat
 * evtEOF. Dar decodorul mai are in tampon cateva secunde de imagine si sunet: evtEOF inchide redarea (MoviePlayer
 * iese, timeshift trece pe direct), asa ca ultimele secunde nu se mai vedeau. Acum, dupa „eof ok”, firul mai citeste
 * fisierul o data pe secunda, de cel mult PASI_MAX ori (in timeshift fisierul inca poate creste), si trimite evtEOF
 * numai daca n-a venit nimic nou. Orice citire cu date o ia de la capat.
 *
 * Numai numaratoarea sta aici (fara enigma2, ca proba unitara sa o compileze singura: teste/test_final_redare_vu1_074.py);
 * pauza de o secunda o face filepush.cpp (nanosleep, oprita de SIGUSR1 din stop()).
 *
 * Idee din imaginea oficiala VU+ (depozitul open-vuplus, peticul e2-fix-inits-and-timeshift-eof al enigma2, GPLv2;
 * VU+ / Satco Europe GmbH); codul de aici e scris de noi.
 */
#ifndef __lib_base_hdsfinalredare_h
#define __lib_base_hdsfinalredare_h

struct hdsFinalRedare
{
	enum { PAS_MS = 1000, PASI_MAX = 5 };
	int pasi;

	hdsFinalRedare(): pasi(0) {}

	/* s-au citit date: sfarsitul nu mai e aproape, numaratoarea o ia de la capat */
	void dateNoi() { pasi = 0; }

	/* dupa „wait for driver eof ok”: true = mai asteapta un pas (PAS_MS) si citeste din nou; false = trimite evtEOF */
	bool maiAsteapta()
	{
		if (pasi < PASI_MAX)
		{
			++pasi;
			return true;
		}
		return false;
	}
};

#endif
