/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsgrad.h: furnizorul pus de scanare unui serviciu de satelit gasit numai in PAT (fara SDT) si repararea semnului
 * de grad stricat in acest furnizor, la citirea lamedb. Numai functii pure, fara enigma2, ca sa se probeze singure,
 * pe PC. Fisierul e scris numai cu caractere ASCII: octetii din afara ASCII apar ca secvente \x.
 *
 * Furnizorul: de forma "DVB-S2 8PSK 12271H 39.0<grad>E", in UTF-8 (gradul = octetii C2 B0), ca toate numele din lamedb.
 * Se pune in m_provider_name asa cum e, fara convertDVBUTF8 (care ar lua fiecare octet ca ISO-8859-1).
 *
 * Stricarea pe care o repara: gradul era in sursa octetul 0xB0 din ISO-8859-1, trecut apoi prin convertDVBUTF8
 * (tabelul 1, ISO-8859-1), care il facea C2 B0. Cand fisierul sursa a fost salvat ca UTF-8, octetul 0xB0 (nevalid in
 * UTF-8) a devenit U+FFFD (EF BF BD), iar convertDVBUTF8 a luat fiecare din cei trei octeti ca ISO-8859-1:
 * C3 AF C2 BF C2 BD (GRAD_STRICAT). Asa a ajuns in lamedb.
 *
 * Repararea e ingusta: numai un nume intreg de forma "DVB-S[2] <QPSK|8PSK> <cifre><H|V> <cifre>.<cifra>"
 * + GRAD_STRICAT + "E" sau "W" (exact ce scria scanarea), iar in el se inlocuiesc numai cei 6 octeti cu C2 B0.
 * Orice alt nume ramane neatins, chiar daca are aceeasi secventa.
 */

#ifndef __lib_dvb_hdsgrad_h
#define __lib_dvb_hdsgrad_h

#include <stddef.h>
#include <stdio.h>
#include <string>

namespace hdsgrad
{
	/* semnul de grad in UTF-8 */
	static const char GRAD[] = "\xc2\xb0";
	/* U+FFFD in UTF-8 (EF BF BD), fiecare octet trecut inca o data prin ISO-8859-1 */
	static const char GRAD_STRICAT[] = "\xc3\xaf\xc2\xbf\xc2\xbd";
	enum { GRAD_STRICAT_LUNG = 6 };

	/* Furnizorul unui serviciu de satelit fara SDT, la fel ca inainte in afara de grad: system 0 "DVB-S", altfel
	   "DVB-S2"; modulation 1 "QPSK", altfel "8PSK"; frecventa in kHz (scrisa in MHz, lipita de polarizare);
	   polarisation 0 "H", altfel "V"; orbital_position in zecimi de grad (0..3599), "W" numai la 0, altfel "E". */
	inline std::string furnizorScanare(int system, int modulation, unsigned int frequency, int polarisation,
		int orbital_position)
	{
		char s[96];
		snprintf(s, sizeof(s), "%s %s %u%c %d.%d%s%c",
			system ? "DVB-S2" : "DVB-S",
			modulation == 1 ? "QPSK" : "8PSK",
			frequency / 1000,
			polarisation ? 'V' : 'H',
			orbital_position / 10,
			orbital_position % 10,
			GRAD,
			orbital_position > 0 ? 'E' : 'W');
		return std::string(s);
	}

	inline bool _cifra(char c)
	{
		return c >= '0' && c <= '9';
	}

	/* true daca nume e intreg un furnizor de scanare cu gradul stricat (forma din antet) */
	inline bool furnizorStricat(const std::string &nume)
	{
		const size_t n = nume.size();
		if (n < 5 || nume.compare(0, 5, "DVB-S") != 0)
			return false;
		size_t i = 5;
		if (i < n && nume[i] == '2')
			++i;
		if (i >= n || nume[i] != ' ')
			return false;
		++i;
		if (n - i < 5 || (nume.compare(i, 5, "QPSK ") != 0 && nume.compare(i, 5, "8PSK ") != 0))
			return false;
		i += 5;
		/* frecventa, lipita de polarizare, apoi un spatiu */
		size_t inceput = i;
		while (i < n && _cifra(nume[i]))
			++i;
		if (i == inceput || i >= n || (nume[i] != 'H' && nume[i] != 'V'))
			return false;
		++i;
		if (i >= n || nume[i] != ' ')
			return false;
		++i;
		/* pozitia: cifre, punct, o cifra */
		inceput = i;
		while (i < n && _cifra(nume[i]))
			++i;
		if (i == inceput || i >= n || nume[i] != '.')
			return false;
		++i;
		if (i >= n || !_cifra(nume[i]))
			return false;
		++i;
		/* gradul stricat, apoi E sau W si sfarsitul numelui */
		if (n - i != (size_t)GRAD_STRICAT_LUNG + 1 || nume.compare(i, GRAD_STRICAT_LUNG, GRAD_STRICAT) != 0)
			return false;
		const char directia = nume[n - 1];
		return directia == 'E' || directia == 'W';
	}

	/* Repara pe loc gradul stricat dintr-un furnizor de scanare (numai forma din antet). true daca l-a schimbat. */
	inline bool reparaGradStricat(std::string &nume)
	{
		if (!furnizorStricat(nume))
			return false;
		nume.replace(nume.size() - 1 - GRAD_STRICAT_LUNG, GRAD_STRICAT_LUNG, GRAD);
		return true;
	}
}

#endif
