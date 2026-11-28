/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsscanreguli.h: regulile cautarii obisnuite care depind de rata de simboluri (purtatoarele inguste, de pilda in banda C
 * din America) si de ce spune driverul dupa prindere. Numai functii pure, fara enigma2, ca sa se probeze singure, pe PC.
 * Folosit de frontend.cpp (prinderea) si scan.cpp (tabelele, unirea a doua intrari, coliziunea TSID/ONID).
 *
 * Unitati: frecventele in kHz, ratele in simboluri pe secunda (ca in eDVBFrontendParametersSatellite), timpii in ms.
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */

#ifndef __lib_dvb_hdsscanreguli_h
#define __lib_dvb_hdsscanreguli_h

namespace hdsscanreguli
{

/* ---------------------------------------------------------------------------------------------------------------------
 * Prinderea (frontend.cpp): frecventa citita de la driver dupa prindere, fata de cea ceruta (amandoua frecventa
 * intermediara, in kHz). O prindere "departe" e o purtatoare vecina sau transponderul de dinainte: tabelele ei ar intra in
 * lista sub parametrii celui cerut. Pragul: macar DEPARTE_MIN_KHZ, iar la ratele mari de doua ori rata (in kHz), cat
 * ocupa purtatoarea cu marginile ei; o abatere a convertorului (cativa MHz) ramane mult sub prag.
 * Necunoscuta: driverul nu da citirea (0, eroare) sau o da in afara benzii intermediare a tunerului (BANDA_L_MIN_KHZ ..
 * BANDA_L_MAX_KHZ): in Hz, in MHz sau frecventa de pe satelit (de pilda 3700-4200 MHz in banda C); la fel cand nici cea
 * ceruta nu e in banda (convertor fara frecventa intermediara obisnuita). Atunci nu se hotaraste nimic.
 * ------------------------------------------------------------------------------------------------------------------- */
enum { DEPARTE_MIN_KHZ = 20000, BANDA_L_MIN_KHZ = 900000, BANDA_L_MAX_KHZ = 2200000 };
enum Prindere { PRINDERE_NECUNOSCUTA = 0, PRINDERE_APROAPE = 1, PRINDERE_DEPARTE = 2 };

inline long pragDeparteKhz(long rata_sym)
{
	long dublu = rata_sym > 0 ? 2 * (rata_sym / 1000) : 0;
	return dublu > DEPARTE_MIN_KHZ ? dublu : (long)DEPARTE_MIN_KHZ;
}

inline long abatere(long a, long b)
{
	return a > b ? a - b : b - a;
}

inline int prindere(long ceruta_khz, long citita_khz, long rata_sym)
{
	if (ceruta_khz < BANDA_L_MIN_KHZ || ceruta_khz > BANDA_L_MAX_KHZ)
		return PRINDERE_NECUNOSCUTA;
	if (citita_khz < BANDA_L_MIN_KHZ || citita_khz > BANDA_L_MAX_KHZ)
		return PRINDERE_NECUNOSCUTA;
	return abatere(ceruta_khz, citita_khz) > pragDeparteKhz(rata_sym) ? PRINDERE_DEPARTE : PRINDERE_APROAPE;
}

inline const char *textPrindere(int p)
{
	return p == PRINDERE_DEPARTE ? "departe" : p == PRINDERE_APROAPE ? "aproape" : "necunoscuta";
}

/* Hotararea "departe = pierdut" e pornita numai pentru driverele masurate: lista de nume din fisierul de pornire (un nume
   pe rand, cum il spune driverul in FE_GET_INFO; "*" = toate, numai pentru probe: un driver nemasurat poate da frecventa
   altfel decat crede regula). Fara fisier sau fara numele driverului: numai jurnalul. continut = textul fisierului
   (NULL = fisier lipsa), nume = numele driverului. */
inline bool driverInLista(const char *continut, const char *nume)
{
	if (!continut || !nume || !*nume)
		return false;
	const char *p = continut;
	while (*p)
	{
		while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')
			++p;
		const char *inceput = p;
		while (*p && *p != '\r' && *p != '\n')
			++p;
		const char *sfarsit = p;
		while (sfarsit > inceput && (sfarsit[-1] == ' ' || sfarsit[-1] == '\t'))
			--sfarsit;
		long n = (long)(sfarsit - inceput);
		if (n == 1 && *inceput == '*')
			return true;
		if (n > 0 && *inceput != '#')
		{
			long i = 0;
			while (i < n && nume[i] && nume[i] == inceput[i])
				++i;
			if (i == n && !nume[i])
				return true;
		}
	}
	return false;
}

/* ---------------------------------------------------------------------------------------------------------------------
 * Pozitia din NIT (scan.cpp): descriptorul de satelit (0x43) al unei intrari, fata de satelitul acordat (amandoua ca in
 * enigma2: 192 = 19,2E, 3550 = 5,0V). Sub 0,5 grade e acelasi satelit (se ia pozitia acordata). NIT-ul retelei acordate
 * (0x40) mai primeste o indreptare, ca pana acum: steagul est/vest gresit (pozitia in oglinda fata de meridianul 0). NIT-ul
 * altor retele (0x41) nu: acolo intrarile chiar descriu alti sateliti, iar perechile in oglinda sunt sateliti adevarati
 * (4,8E si 5,0V, 7,0E si 7,0V); cu indreptarea, transponderele lor ar fi venit pe satelitul acordat. Orice altceva: alt
 * satelit, intrarea se arunca.
 * ------------------------------------------------------------------------------------------------------------------- */
enum { POZITIE_ALT_SATELIT = 0, POZITIE_ACEEASI = 1, POZITIE_EST_VEST = 2 };

inline int pozitieDinNit(int acordata, int din_nit, bool alta_retea)
{
	if (abatere(acordata, din_nit) < 5)
		return POZITIE_ACEEASI;
	if (alta_retea)
		return POZITIE_ALT_SATELIT;
	return abatere(abatere(3600, acordata), din_nit) < 5 ? POZITIE_EST_VEST : POZITIE_ALT_SATELIT;
}

/* ---------------------------------------------------------------------------------------------------------------------
 * Tabelele (scan.cpp): la ratele mici fluxul are putini octeti pe secunda, iar emitatorii purtatoarelor inguste repeta
 * PAT-ul si PMT-urile rar; plafonul fix de 4 s le pierdea si transponderul iesea gol. Sub 1 MS/s plafonul se intreita, de
 * la 1 la 4 MS/s se dubleaza; peste 4 MS/s ramane cum era. Rata 0 (necunoscuta, cablu, terestru): neschimbat.
 * ------------------------------------------------------------------------------------------------------------------- */
inline int factorTabele(long rata_sym)
{
	if (rata_sym <= 0)
		return 1;
	if (rata_sym < 1000000)
		return 3;
	if (rata_sym < 4000000)
		return 2;
	return 1;
}

inline int timpTabel(int baza_ms, long rata_sym)
{
	return baza_ms * factorTabele(rata_sym);
}

/* ---------------------------------------------------------------------------------------------------------------------
 * Unirea a doua intrari de satelit (scan.cpp, sameChannel): pana acum orice doua intrari la sub 4 MHz (frecventa plus
 * diferenta ratelor) erau aceeasi, deci a doua purtatoare ingusta de langa una prinsa nu se mai cauta. Doua purtatoare
 * diferite nu pot sta mai aproape decat cam latimea lor; fereastra de unire e 2/3 din rata mai mica (in kHz), intre
 * FEREASTRA_MIN_KHZ si FEREASTRA_MAX_KHZ. La 6 MS/s si peste ramane 4 MHz, ca inainte. O rata 0 (necunoscuta): 4 MHz.
 * Se aplica numai termenului de frecventa; diferenta ratelor si restul comparatiei raman ale lui calculateDifference.
 * ------------------------------------------------------------------------------------------------------------------- */
enum { FEREASTRA_MIN_KHZ = 500, FEREASTRA_MAX_KHZ = 4000 };

inline long fereastraUnireKhz(long rata1_sym, long rata2_sym)
{
	long rata = rata1_sym < rata2_sym ? rata1_sym : rata2_sym;
	if (rata <= 0)
		return FEREASTRA_MAX_KHZ;
	long f = (rata / 1000) * 2 / 3;
	if (f < FEREASTRA_MIN_KHZ)
		return FEREASTRA_MIN_KHZ;
	if (f > FEREASTRA_MAX_KHZ)
		return FEREASTRA_MAX_KHZ;
	return f;
}

/* NIT9 (24.11.2026): rata si frecventa se judeca fiecare cu masura ei. calculateDifference aduna abaterea frecventei (kHz)
   cu a ratei (simboluri/s), deci 29900 fata de 30000 kS/s (100000) nu iesea niciodata aceeasi intrare, desi e aceeasi
   purtatoare (pe 13E, 12673 V: lista DVB-S2 30000, NIT-ul altei retele DVB-S 29900). Acum: aceeasi pozitie, polarizare,
   flux (partea mare a diferentei, de la DIFERENTA_ALTA_INTRARE in sus, ramane a lui calculateDifference), frecventele in
   fereastra ratei mai mici si ratele la cel mult MARJA_RATA_PROMILE la mie din cea mai mare (macar MARJA_RATA_MIN_SYM, ca
   pragul vechi, deci purtatoarele inguste nu se unesc mai usor decat inainte; o rata 0 se uneste numai cu 0).
   27500 fata de 30000 (8 %) raman intrari diferite (variantele vechi au regula lor, hdsAltaVarianta). OE-Alliance: suma
   sub 2000 pe DVB-S (scan.cpp, offset), deci nici ea nu uneste 29900 cu 30000. */
enum { DIFERENTA_ALTA_INTRARE = 1 << 26, MARJA_RATA_PROMILE = 20, MARJA_RATA_MIN_SYM = 4000 };

inline bool aceeasiRata(long rata1_sym, long rata2_sym)
{
	long mare = rata1_sym > rata2_sym ? rata1_sym : rata2_sym;
	long marja = mare / 1000 * MARJA_RATA_PROMILE;
	if (marja < MARJA_RATA_MIN_SYM)
		marja = MARJA_RATA_MIN_SYM;
	return abatere(rata1_sym, rata2_sym) <= marja;
}

/* aceeasi intrare de satelit: nimic diferit in afara frecventei si a ratei (diferenta_veche sub DIFERENTA_ALTA_INTRARE),
   frecventele in fereastra ratei mai mici si ratele in marja */
inline bool aceeasiIntrare(int diferenta_veche, long frecventa1_khz, long frecventa2_khz, long rata1_sym, long rata2_sym)
{
	if (diferenta_veche < 0 || diferenta_veche >= DIFERENTA_ALTA_INTRARE)
		return false;
	return abatere(frecventa1_khz, frecventa2_khz) < fereastraUnireKhz(rata1_sym, rata2_sym) &&
		aceeasiRata(rata1_sym, rata2_sym);
}

/* NIT9: parametrii scrisi in lista pentru un transponder prins care a venit NUMAI din NIT-ul altei retele. NIT other
   descrie transponderele altei retele din auzite (pe 13E: 12673 V DVB-S QPSK 29900, cand reteaua lui proprie, citita chiar
   pe el, spune DVB-S2 8PSK 30000). Intai descriptorul propriu din NIT-ul actual citit pe acel transponder (aceeasi
   polarizare, frecventa in fereastra), apoi ce avea lista, apoi (transponder nou) parametrii din NIT other. */
enum { PARAMETRI_DIN_NIT_ALT = 0, PARAMETRI_DIN_NIT_PROPRIU = 1, PARAMETRI_DIN_LISTA = 2 };

inline int parametriPentruNitAlt(bool are_nit_propriu, bool nit_propriu_potrivit, bool in_lista)
{
	if (are_nit_propriu && nit_propriu_potrivit)
		return PARAMETRI_DIN_NIT_PROPRIU;
	if (in_lista)
		return PARAMETRI_DIN_LISTA;
	return PARAMETRI_DIN_NIT_ALT;
}

/* ---------------------------------------------------------------------------------------------------------------------
 * Coliziunea TSID/ONID (scan.cpp): pe unii sateliti (de pilda 55.6W in banda C) acelasi TSID si ONID stau pe mai multe
 * transpondere. Cu ONID-ul valid namespace-ul n-are frecventa, deci al doilea transponder il suprascria pe primul in
 * lista. Doua transpondere prinse cu acelasi (namespace, TSID, ONID) sunt doua transpondere diferite cand sunt pe
 * polarizari diferite sau mai departe unul de altul decat poate fi aceeasi purtatoare: macar COLIZIUNE_MIN_KHZ si macar
 * rata mai mare (in kHz). Mai aproape e aceeasi purtatoare intrata de doua ori: pe 13E reteaua CANAL+ anunta TSID 11100
 * la 10722,9, 10727 si 10728 (rate 29900-30000); cu un prag fix de 2 MHz, doua dintre ele prinse pe aceeasi purtatoare
 * s-ar fi despartit in doua transpondere cu aceleasi canale.
 * ------------------------------------------------------------------------------------------------------------------- */
enum { COLIZIUNE_MIN_KHZ = 2000 };

inline long pragColiziuneKhz(long rata1_sym, long rata2_sym)
{
	long rata = (rata1_sym > rata2_sym ? rata1_sym : rata2_sym) / 1000;
	return rata > COLIZIUNE_MIN_KHZ ? rata : (long)COLIZIUNE_MIN_KHZ;
}

inline bool transpondereDiferite(long frecventa1_khz, int polarizare1, long rata1_sym, long frecventa2_khz, int polarizare2,
	long rata2_sym)
{
	return polarizare1 != polarizare2 ||
		abatere(frecventa1_khz, frecventa2_khz) > pragColiziuneKhz(rata1_sym, rata2_sym);
}

/* un transponder deja stiut sub un (namespace, TSID, ONID): in cautarea de acum sau in lista de canale */
struct Vazut
{
	bool exista;
	long frecventa;
	int polarizare;
	long rata;
};

inline Vazut vazut(long frecventa_khz, int polarizare, long rata_sym)
{
	Vazut v;
	v.exista = true;
	v.frecventa = frecventa_khz;
	v.polarizare = polarizare;
	v.rata = rata_sym;
	return v;
}

inline Vazut nevazut()
{
	Vazut v;
	v.exista = false;
	v.frecventa = 0;
	v.polarizare = 0;
	v.rata = 0;
	return v;
}

inline bool diferite(const Vazut &a, const Vazut &b)
{
	return transpondereDiferite(a.frecventa, a.polarizare, a.rata, b.frecventa, b.polarizare, b.rata);
}

/* Transponderul prins (frecventa, polarizare) are ONID valid, deci namespace-ul fara frecventa (ns_orb). Primeste
   namespace-ul cu frecventa (ns_frecventa) numai la o coliziune adevarata:
   - in cautarea de acum (ns_orb, TSID, ONID) e deja al altui transponder (diferit dupa transpondereDiferite) cu alt continut
     in SDT (serviciile, numele); acelasi continut e acelasi flux prins din doua intrari (purtatoarea vecina, polarizarea
     gresita, acelasi program pe doua fascicule) si ramane unit, ca inainte. La purtatoarele inguste (fereastra de unire sub
     4 MHz, rate sub 6 MS/s), cu alt continut ajunge ca frecventele sa fie peste fereastra: doua purtatoare de 1 MS/s la
     1 MHz sunt doua transpondere; la ratele mari ramane pragul de mai sus (un SDT schimbat intre doua citiri ale aceleiasi
     purtatori nu desparte nimic in Europa);
   - lista de canale are deja perechea despartita de o cautare de dinainte: (ns_frecventa, TSID, ONID) pentru acest
     transponder SI (ns_orb, TSID, ONID) la alt transponder.
   Altfel ramane ns_orb, exact ca inainte: un transponder mutat pe alta frecventa (acelasi TSID si ONID, frecventa veche
   moarta) isi pastreaza canalele, buchetele si temporizatoarele. */
inline bool namespaceCuFrecventa(Vazut acum, Vazut in_cautare, bool acelasi_continut, Vazut lista_orb,
	bool lista_are_ns_frecventa)
{
	if (!acum.exista)
		return false;
	if (in_cautare.exista && !acelasi_continut && (diferite(acum, in_cautare) ||
			(fereastraUnireKhz(acum.rata, in_cautare.rata) < FEREASTRA_MAX_KHZ &&
			abatere(acum.frecventa, in_cautare.frecventa) >= fereastraUnireKhz(acum.rata, in_cautare.rata))))
		return true;
	if (lista_are_ns_frecventa && lista_orb.exista && diferite(acum, lista_orb))
		return true;
	return false;
}

/* La sfarsitul cautarii, intr-un grup de coliziune (cel prins primul are ns_orb, ceilalti ns_frecventa): ns_orb il
   pastreaza transponderul pe care lista il are deja sub (ns_orb, TSID, ONID), ca bucheturile omului sa arate tot ce
   aratau, oricare ar fi ordinea cautarii. Intoarce indexul din grup care trebuie sa aiba ns_orb (0 = cel prins primul,
   neschimbat). Fara intrare in lista sau fara niciun transponder al grupului langa ea: 0. */
inline int pastratorNamespace(const Vazut *grup, int n, Vazut lista_orb)
{
	if (!lista_orb.exista || n <= 0)
		return 0;
	if (grup[0].exista && !diferite(grup[0], lista_orb))
		return 0;
	for (int i = 1; i < n; ++i)
		if (grup[i].exista && !diferite(grup[i], lista_orb))
			return i;
	return 0;
}

}

#endif
