/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsjurnal.h: jurnalele componentelor imaginii, in aceeasi forma pentru C++ si pentru Python (Components/HdsJurnal.py,
 * care in enigma2 scrie tot prin functiile de aici, prin enigma.hdsJurnalScrie: un singur fir scrie si roteste fiecare
 * fisier).
 *
 * FISIERUL: /home/root/logs/hds-<componenta>.log (dosarul se schimba cu HDS_JURNAL_DIR: emulatorul, probele de pe PC).
 * La ROTIRE_OCTETI (256 KB) fisierul devine .log.1, iar .log.1 devine .log.2 (doua fisiere vechi, cel mult ~768 KB pe
 * componenta). Componenta: litere mici, cifre si "-", cel mult 32 de semne (altfel "diverse").
 *
 * RANDUL: "AAAA-LL-ZZTHH:MM:SSZ [NIVEL] [modul] mesaj", ora in UTC. NIVEL: INFO, AVERT, EROARE. Ceasul receptorului
 * poate fi 1970 pana la ora din satelit sau din retea, de aceea primul rand scris intr-un fisier dupa pornirea
 * procesului spune si timpul de la pornirea placii ("[jurnal] pornit ... up=12.3s").
 *
 * CURATAREA (curata): mesajul ramane pe un rand (capetele de linie si semnele de control devin spatiu), adresele IPv4 si
 * MAC intregi se acopera (192.168.x.x, a8:f2:1b:xx:xx:xx), iar valoarea de dupa cheie=, parola=, jeton=, token=, key=,
 * password=, psk=, secret=, ssid= devine ***.
 *
 * CONFIDENTIALITATEA (regula celor care cheama): un rand INFO are numai date tehnice (tunerul, frecventa, polarizarea,
 * rata de simboluri, sistemul, semnalul, timpii, codecul), fara canal (nume, referinta serviciului), fara ce vede sau
 * inregistreaza omul, fara nume de retele. La un esec (AVERT, EROARE) randul poate spune si canalul (numele, referinta,
 * transponderul, SID-ul, PID-urile, codecul), ca sa se poata afla exact canalul care nu merge.
 *
 * FIRUL CARE CHEAMA NU ASTEAPTA: randul se formeaza pe stiva si intra intr-o teava neblocanta (sub PIPE_BUF, deci intreg
 * sau deloc); cand teava e plina randul se numara ca pierdut si se spune intr-un rand AVERT la urmatoarea scriere
 * reusita. Un fir separat (pornit la primul rand, desprins) muta randurile in fisiere, le trece pe disc (fdatasync, ca
 * sa ramana si dupa o repornire facuta de paznic) si roteste fisierele, numai la capat de rand. Un fisier sters de
 * mana (Jurnalele sistemului) se face din nou la randul urmator.
 *
 * Scris de la zero pentru imaginea HD Satelit; firul de scriere urmeaza lib/dvb/hdsurmamotor.cpp.
 */
#ifndef __lib_base_hdsjurnal_h
#define __lib_base_hdsjurnal_h

#include <stddef.h>
#include <time.h>

namespace hdsjurnal
{

enum { ROTIRE_OCTETI = 256 * 1024, FISIERE_VECHI = 2, LUNGIME_MESAJ = 900, LUNGIME_RAND = 1024 };

extern const char INFO[];
extern const char AVERT[];
extern const char EROARE[];

/* randul fara capat de linie, cu mesajul deja curatat; intoarce lungimea (0 daca nu incape) */
size_t formeaza(char *buf, size_t n, const struct timespec &utc, const char *nivel, const char *modul, const char *mesaj);

/* curata mesajul pe loc (vezi sus); intoarce lungimea noua */
size_t curata(char *mesaj);

/* 1 daca numele componentei e bun pentru fisier ([a-z0-9-], 1..32 de semne) */
int numeBun(const char *componenta);

/* scrie un rand in hds-<componenta>.log; nu asteapta niciodata */
void scrie(const char *componenta, const char *nivel, const char *modul, const char *mesaj);
void scrief(const char *componenta, const char *nivel, const char *modul, const char *fmt, ...)
	__attribute__((format(printf, 4, 5)));

/* Frana pentru randurile care se pot repeta des (semnalul pierdut pe ploaie, reacordarile): cel mult un rand la
   pauza_ms; lasa() spune daca randul de acum se scrie si, atunci, cate s-au sarit de la cel scris inainte. Numai de
   pe un singur fir (fiecare obiect al lui). */
class Frana
{
public:
	explicit Frana(int pauza_ms);
	bool lasa(unsigned long &sarite);
private:
	int m_pauza_ms;
	double m_ultim;
	unsigned long m_sarite;
};

/* ceasul monoton in ms (pentru timpii pasilor) */
long long monotonMs();

/* pentru probe: dosarul jurnalelor si asteptarea pana cand firul a scris tot ce era in teava (cel mult ms; 0 = gata) */
const char *dosar();
int asteaptaScrierea(int ms);

}

/* pentru Python (enigma.hdsJurnalScrie): mesajul vine curatat de Components/HdsJurnal.py si se curata inca o data */
void hdsJurnalScrie(const char *componenta, const char *nivel, const char *modul, const char *mesaj);

#endif
