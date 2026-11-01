/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsjurnaltuner.h: jurnalul tunerelor si al acordarii (/home/root/logs/hds-tuner.log, forma din lib/base/hdsjurnal.h).
 * Chemat din frontend.cpp (cate un rand in fiecare loc), ca sa se poata afla dupa o problema la un tester ce tunere are
 * receptorul, ce s-a cerut fiecaruia si ce a raspuns driverul.
 *
 * CE SE SCRIE (numai date tehnice: tunerul, sistemul, frecventa, polarizarea, rata de simboluri, FEC, pozitia orbitala,
 * comenzile LNB/DiSEqC/Unicable, semnalul, timpii; fara canal):
 *   [detectare] la prima deschidere a fiecarui tuner: litera, numele driverului, ce sisteme poate, multistream, API-ul;
 *               deschiderea cazuta (EROARE, cu errno).
 *   [acordare]  INFO la semnal prins: parametrii, comenzile LNB din secventa (tensiunea, tonul 22 kHz, DiSEqC 1.0/1.1,
 *               Unicable, toneburst, motorul), cat a durat pana la semnal, SNR-ul; AVERT la "fara semnal" dupa
 *               timpul de asteptare, cu bitii de stare ai driverului (semnal, purtatoare, viterbi, sincronizare);
 *               EROARE cand driverul refuza parametrii (FE_SET_PROPERTY / FE_SET_FRONTEND, errno).
 *   [semnal]    AVERT la semnalul pierdut dupa ce era prins; reacordarile dupa pierdere au frana (un rand la 30 s pe
 *               tuner, cele sarite numarate in randul urmator), ca o ploaie sa nu impinga din fisier restul.
 *   [sistem]    schimbarea sistemului pe un tuner combinat (DVB-C <-> DVB-T), reusita sau refuzata.
 * SCANAREA (/home/root/logs/hds-scanare.log, namespace hdsjscan, chemat din scan.cpp): pornirea (cate transpondere,
 * steagurile), fiecare transponder (parametrii; prins in cat timp si cate servicii noi, sau fara semnal dupa cat
 * timp) si sfarsitul (cercetate, fara semnal, servicii gasite, durata). Fara numele serviciilor gasite.
 * Exemplu: "2026-10-29T08:14:02Z [INFO] [acordare] A DVB-S2 8PSK 11054 H 27500 3/4 19.2E | lnb 18V 22k DiSEqC1.0
 *   port 2 | semnal in 412 ms snr 12.40 dB"
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */
#ifndef __lib_dvb_hdsjurnaltuner_h
#define __lib_dvb_hdsjurnaltuner_h

#include <lib/base/hdsjurnal.h>
#include <lib/dvb/frontendparms.h>

class iDVBFrontendParameters;

namespace hdsjtuner
{

/* ce stie jurnalul despre acordarea de acum a unui tuner (membru in eDVBFrontend) */
struct Stare
{
	long long pornit_ms;    /* tune(): ceasul monoton, 0 = nicio acordare in asteptare */
	int reacordare;         /* acordarea vine dupa semnalul pierdut */
	int prins_o_data;       /* a fost semnal dupa ultima acordare (pentru "semnal pierdut") */
	char parametri[160];
	char lnb[160];
	hdsjurnal::Frana frana_reacordare;
	hdsjurnal::Frana frana_pierdut;
	Stare();
};

/* detectarea: prima deschidere a tunerului in procesul de acum (tipuri = bitii 1 << feSatellite/feCable/feTerrestrial) */
void deschis(int slot, int dvbid, const char *nume, int tipuri, int multistream, int api);
void deschidereCazuta(int slot, int dvbid, int err);

/* tune(): parametrii (reacordare = 1 cand starea era "semnal pierdut") */
void acordareSat(Stare &s, int slot, const eDVBFrontendParametersSatellite &p, int reacordare);
void acordareCablu(Stare &s, int slot, const eDVBFrontendParametersCable &p, int reacordare);
void acordareTerestru(Stare &s, int slot, const eDVBFrontendParametersTerrestrial &p, int reacordare);

/* textul parametrilor (si pentru randurile de esec ale zap-ului si ale scanarii) */
void textSat(char *buf, size_t n, const eDVBFrontendParametersSatellite &p);
void textCablu(char *buf, size_t n, const eDVBFrontendParametersCable &p);
void textTerestru(char *buf, size_t n, const eDVBFrontendParametersTerrestrial &p);

/* secventa SEC, pe masura ce se executa (tuneLoopInt) */
void tensiune(Stare &s, int voltaj);
void ton(Stare &s, int ton);
void diseqc(Stare &s, const unsigned char *d, int len);
void toneburst(Stare &s, int b);

/* rezultatul: semnal prins (snr_db100 = SNR in sutimi de dB, < 0 necunoscut), fara semnal dupa timpul de asteptare
   (status = bitii FE_READ_STATUS, < 0 necunoscuti), semnal pierdut, parametri refuzati de driver */
void prins(Stare &s, int slot, int snr_db100);
void faraSemnal(Stare &s, int slot, int status);
void pierdut(Stare &s, int slot);
void refuzat(Stare &s, int slot, const char *apel, int err);

/* tunerul combinat: sistemul schimbat (spre = "DVB-C" / "DVB-T"), err = 0 reusit */
void sistem(int slot, const char *spre, int err);

/* textul oricaror parametri (satelit, cablu, terestru) */
void textParametri(char *buf, size_t n, iDVBFrontendParameters *p);

}

namespace hdsjscan
{

/* starea jurnalului unei scanari (membru in eDVBScan) */
struct Stare
{
	long long pornit_ms, tp_ms;
	size_t servicii_inainte;
	char tp[160];
	Stare();
};

void pornita(Stare &s, size_t transpondere, int steaguri);
void transponder(Stare &s, iDVBFrontendParameters *p, size_t servicii);
void prins(Stare &s, size_t servicii);
void faraSemnal(Stare &s);
void gata(Stare &s, size_t cercetate, size_t fara_semnal, size_t servicii);

}

#endif
