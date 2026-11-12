/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsconsolacitire.h: cand se lasa consola (eRCConsoleDriver pe /dev/tty0, lib/driver/rcconsole.cpp): dupa citiri
 * fara date, la rand.
 *
 * DE CE: pe Vu+ Duo 4K firul principal al enigma2 tinea un nucleu la 85-99% de la pornire (0.7.1-0.7.3). Contoarele
 * buclei principale (lib/base/ebase.cpp, 0.7.3) au aratat in toate rapoartele automate "procesor" de pe acest model
 * acelasi descriptor: /dev/tty0, 87-107 mii de activari pe secunda, revents IN, cerut IN. poll() spune ca e ceva de
 * citit, read() din eRCConsoleDriver::keyPressed nu scoate nimic din coada (intoarce 0 sau -1), deci poll() se
 * intoarce iar imediat, la nesfarsit. Pe celelalte modele consola nu apare in contoare. Nucleul Duo 4K e singurul
 * dintre modelele noastre fara terminale virtuale (CONFIG_VT nesetat; Solo4K, Uno4K SE, SF8008 au CONFIG_VT=y), deci
 * acolo /dev/tty0 nu e o consola (de pilda un fisier obisnuit lasat de o scriere: poll() spune mereu "gata", read()
 * da 0). De aceea eRCConsoleDriver nu mai urmareste deloc un /dev/tty0 care nu e terminal (tcgetattr cade), iar
 * regula de mai jos ramane plasa pentru un terminal adevarat care se strica.
 *
 * REGULA: o citire cu date (rezultat > 0) aduce numaratoarea la 0; o citire fara date (0 sau -1, oricare ar fi
 * errno) o creste. La LIMITA_GOALE citiri fara date la rand consola se lasa: notificatorul se elibereaza (nu doar se
 * opreste, fiindca eRCConsoleDriver::unlock() l-ar porni din nou), descriptorul se inchide, cu cate un singur rand in
 * jurnalul interfetei si in /home/root/logs/hds-consola.log (de ce: errno, dispozitivul, grupurile de procese).
 * O citire goala rara (o cursa intre poll si read) nu ajunge la limita: dupa ea fie vin date, fie poll() asteapta.
 * Consola aduce numai literele unei tastaturi USB in campurile de text; pe un receptor unde citirea nu scoate nimic,
 * ele oricum nu ajung.
 *
 * Fara enigma2: antetul se compileaza si singur, pentru proba de pe PC (teste/test_consola_tty0_074.py).
 */
#ifndef __lib_driver_hdsconsolacitire_h
#define __lib_driver_hdsconsolacitire_h

namespace hdsconsola
{

enum { LIMITA_GOALE = 64 };

/* dupa fiecare read() al consolei: true cand consola trebuie lasata (a LIMITA_GOALE-a citire fara date la rand) */
inline bool lasaDupaCitire(int rezultat, int &goale)
{
	if (rezultat > 0)
	{
		goale = 0;
		return false;
	}
	if (goale < LIMITA_GOALE)
		++goale;
	return goale >= LIMITA_GOALE;
}

}

#endif
