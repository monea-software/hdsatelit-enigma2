/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsurmamotor.h: urma comenzilor trimise motorului antenei (DiSEqC 1.2, adresa de pozitioner 0x30..0x32), pastrata pe
 * disc. enigma2 scrie numai pe consola, iar dupa o repornire nu ramane nimic: cand antena ajunge in alta pozitie trebuie
 * sa se poata afla cine a trimis comanda, cand, pe ce acordare si unde credea nucleul ca e antena.
 *
 * CE SE SCRIE (un rand JSON pe eveniment, in /home/root/logs/hds-motor.log, rotit in hds-motor.log.1 la 128 KB):
 *   - "comanda": fiecare mesaj de motor dat driverului (eDVBFrontend::sendDiseqc), din secventa unei acordari (cale
 *     "acordare") sau trimis direct din Python (cale "directa"), cu octetii, numele comenzii, unghiul sau pozitia,
 *     raspunsul driverului, cine a cerut-o, canalul si transponderul, pozitia crezuta inainte;
 *   - "goto_omis": o acordare pe satelitul pe care nucleul crede ca e deja antena (sec.cpp nu trimite nimic motorului);
 *     la reacordarea dupa pierderea semnalului cel mult un rand la 30 s pe tuner, altfel cel mult unul la 10 minute
 *     (cele sarite se numara in randul urmator);
 *   - "pozitie_crezuta": pozitia tinuta de nucleu schimbata din Python (puneri la pornire, uitari dupa miscari manuale);
 *   - "readucere": readucerea antenei dupa pierderea semnalului (Components/HdsMotorPozitie.py): pornirea, semnalul
 *     revenit (dupa cat timp, cat a mers motorul), fara semnal (si cand e urmatoarea incercare), incheierea, refuzul.
 *   - "tensiune_rotire": motorul rotit pe 18 V spre o tinta pe 13 V (lib/dvb/hdsrotire.h): capatul tinerii ("gata",
 *     urmeaza tensiunea tintei) sau mersul oprit in timpul ei ("intrerupta"), cu cat a tinut si cat era estimat;
 *     randul comenzii de motor are si el tensiunea de rotire, a tintei, tinerea estimata, drumul, plecarea si, la
 *     plecarea necunoscuta, ce a fost cu proba de semnal ("proba": fara_semnal, geaman, fara_lista).
 *   - "proba_semnal": proba de semnal pe tinta cu antena pe loc, inaintea comenzii de motor (lib/dvb/hdsrotire.h):
 *     "prinsa" (nicio comanda de motor nu mai pleaca, antena era deja acolo) sau "fara_semnal" (urmeaza comanda), cu
 *     fereastra probei si cat a durat.
 *
 * CINE A CERUT-O: motivul pus din C++ pe durata unei acordari (clasa Motiv: televizorul, o inregistrare, reacordarea,
 * scanarea), cererea anuntata din Python (anuntaCerere, de exemplu pagina web a motorului) si, cand firul are interpretorul,
 * lantul de apeluri Python de atunci (fisier:linie functie, cel mult 5 niveluri).
 *
 * FIRUL PRINCIPAL NU ASTEAPTA: randul se scrie intr-o teava neblocanta (un rand pierdut se numara si se spune in randul
 * urmator), iar un fir separat il muta in fisier, il trece pe disc (fdatasync, ca sa ramana si dupa o repornire facuta de
 * paznic) si roteste fisierul. Dosarul se poate schimba cu HDS_URMA_MOTOR_DIR (emulatorul, probele de pe PC).
 *
 * Scris de la zero pentru imaginea HD Satelit. Valorile comenzilor: specificatia DiSEqC 1.2 (Eutelsat), aceleasi ca in
 * lib/dvb/sec.cpp si Components/DishMath.py.
 */
#ifndef __lib_dvb_hdsurmamotor_h
#define __lib_dvb_hdsurmamotor_h

#include <stddef.h>
#include <time.h>

namespace hdsurma
{

enum { ROTIRE_OCTETI = 128 * 1024 };

/* ce se stie despre o acordare: cine a cerut-o, spre ce, si ce a hotarat sec.cpp pentru motor */
struct Acordare
{
	char motiv[96];   /* "televizor", "inregistrare", "reacordare dupa pierderea semnalului", "scanare", "acordare" */
	char canal[72];   /* referinta serviciului, daca se stie */
	char cerere[96];  /* cererea anuntata din Python (anuntaCerere), daca era valabila */
	char python[256]; /* lantul de apeluri Python, daca acordarea a venit din Python */
	char tp[48];      /* "11464 H 22000" */
	int orbital;      /* satelitul acordarii, zecimi de grad (3600 - x pentru vest), -1 necunoscut */
	int rotor_de_la;  /* pozitia crezuta de nucleu inainte (ROTOR_POS), -1 necunoscuta */
	int rotor_cmd;    /* comanda de motor calculata de sec.cpp pentru aceasta acordare, -1 niciuna */
	int rotor_cmd_vechi; /* ultima comanda tinuta de nucleu cand s-a hotarat (ROTOR_CMD), -1 necunoscuta */
	double mono_s;    /* ceasul monoton la acordare */
	/* lib/dvb/hdsrotire.h: cu ce tensiune pleaca motorul pe ramura fara masurarea curentului;
	   intra numai in randul comenzii de motor (6E, 6B) a acordarii */
	int rotire_tensiune;      /* 18 sau 13; 0 = nehotarat aici (ramura cu masurare, Unicable, fara motor) */
	int rotire_tinta;         /* tensiunea transponderului tinta: 18 sau 13 */
	int rotire_plan_ms;       /* cat se tine 18 V dupa comanda (tinta pe 13 V), 0 = deloc */
	int rotire_grade_zecimi;  /* drumul estimat (la plecare necunoscuta: cel mai lung posibil), zecimi de grad */
	int rotire_plecare;       /* 0 stiuta, 1 zona (o mutare intrerupta), 2 necunoscuta */
	int rotire_proba;         /* hdsrotire::PROBA_NECERUTA, _FACUTA, _GEAMAN, _FARA_LISTA */
	void goleste();
};

/* Motivul acordarilor pornite cat traieste obiectul (pe firul curent). Un camp 0 lasa motivul de deasupra (de exemplu
   pmt.cpp pune numai canalul, sub motivul pus de serviciu). */
class Motiv
{
public:
	Motiv(const char *motiv, const char *canal = 0);
	~Motiv();
private:
	const char *m_motiv_vechi;
	const char *m_canal_vechi;
	Motiv(const Motiv &);
	Motiv &operator=(const Motiv &);
};

/* cererea anuntata din Python (pagina web a motorului, ecranele): un text scurt, valabil ttl_ms */
void anuntaCerere(const char *text, int ttl_ms);

/* completeaza motivul, canalul, cererea anuntata si lantul Python; motiv_implicit cand nu e pus niciun Motiv */
void completeazaCine(Acordare &a, const char *motiv_implicit);

/* textul transponderului: frecventa in MHz, polarizarea, rata de simboluri */
void textTp(char *buf, size_t n, unsigned int frecventa_khz, int polarizare, unsigned int sr);

/* 1 daca octetii sunt o comanda pentru un pozitioner DiSEqC (cadru E0..E3, adresa 0x30..0x32, comanda 0x60..0x6F) */
int esteMotor(const unsigned char *d, int len);
/* numele comenzii, pentru oameni si pentru pagina web */
const char *numeComanda(const unsigned char *d, int len);
/* unghiul comenzii 6E in zecimi de grad (est pozitiv, vest negativ); 0 si *ok = 0 daca nu e 6E */
int unghiZecimi(const unsigned char *d, int len, int *ok);

/* tot ce intra intr-un rand */
struct Eveniment
{
	const char *tip;              /* "comanda", "goto_omis", "pozitie_crezuta" */
	int slot;
	const unsigned char *octeti;  /* "comanda" */
	int lungime;
	int rezultat;                 /* raspunsul driverului (0 = primita, altfel -errno) */
	int ret_driver;               /* ce a intors ioctl-ul cand a reusit, daca nu e 0 (SF8008: 1); 0 = nu se scrie */
	const char *cale;             /* "acordare" sau "directa" */
	const Acordare *acordare;     /* acordarea (sau, la cale directa, ultima acordare a tunerului si cine a cerut acum) */
	long crezuta;                 /* pozitia crezuta de nucleu cand s-a hotarat, zecimi de grad, -1 necunoscuta */
	long crezuta_cmd;             /* ultima comanda de motor tinuta de nucleu, -1 */
	int spre;                     /* "pozitie_crezuta": pozitia noua, -1 = uitata */
	int spre_cmd;
	unsigned long omise;          /* "goto_omis": cate randuri de acelasi fel s-au sarit de la ultimul */
	const char *faza;             /* "readucere": pornita, semnal_revenit, fara_semnal, incheiata, refuzata */
	int incercare;                /* "readucere": a cata incercare din sirul de acum (1, 2, ...) */
	long fara_semnal_ms;          /* "readucere": de cat timp e fara semnal, -1 nu se stie */
	long dupa_ms;                 /* "readucere": de la pornirea incercarii, -1 nu se stie */
	long mers_ms;                 /* "readucere": cat a mers motorul pana la oprire (semnal sau timpul maxim), -1 */
	long urmatoarea_s;            /* "readucere": peste cat incepe urmatoarea incercare, -1 niciuna */
	long cod;                     /* "readucere": raspunsul nucleului la refuz (hdsReaduceAntena), 0 altfel */
	int tensiune;                 /* "tensiune_rotire": tensiunea tinuta (18) */
	long plan_ms;                 /* "tensiune_rotire": tinerea estimata */
	long tinut_ms;                /* "tensiune_rotire": cat a tinut de la pornirea motorului, -1 nu se stie */
	Eveniment();
};

/* randul JSON (fara capat de linie); intoarce lungimea, 0 daca nu incape */
size_t formeaza(char *buf, size_t n, const Eveniment &e, const struct timespec &real, const struct timespec &mono,
	const char *pornire, unsigned long pierdute);

/* scrie evenimentul in urma (si pe consola); nu asteapta niciodata */
void noteaza(const Eveniment &e);

/* cele trei evenimente, chemate din frontend.cpp si sec.cpp */
void comandaTrimisa(int slot, const unsigned char *d, int len, int rezultat, const char *cale, const Acordare &a,
	long crezuta, long crezuta_cmd, int ret_driver = 0);

/* raspunsul unui ioctl dupa conventia Linux: numai o valoare negativa e eroare (atunci -errno); un driver care
   intoarce un numar pozitiv la reusita (hi-dvb.ko pe SF8008: 1) a reusit, iar errno ramas de la alt apel nu conteaza */
inline int rezultatIoctl(int ret, int err) { return ret < 0 ? -err : 0; }
void gotoOmis(int slot, const Acordare &a, long ultima_cmd);
void pozitieCrezuta(int slot, long de_la, long de_la_cmd, int spre, int spre_cmd);
/* un rand "readucere" (chemat din sec.cpp, hdsMotorReaducere) */
void readucere(int slot, const char *faza, int incercare, int orbital, long crezuta, long fara_semnal_ms,
	long dupa_ms, long mers_ms, long urmatoarea_s, long cod);
/* un rand "tensiune_rotire" (sec.cpp: hdsRotireGata si setRotorMoving); acordarea 0 = cine a oprit
   mersul (motivul de acum) */
void tensiuneRotire(int slot, const char *faza, long plan_ms, long tinut_ms, int orbital, long crezuta,
	const Acordare *acordare);
/* un rand "proba_semnal" (sec.cpp: hdsProbaSemnal): faza "prinsa" sau "fara_semnal", fereastra probei si cat a durat
   (ms, -1 = nu se stie) */
void probaSemnal(int slot, const char *faza, long fereastra_ms, long durata_ms, int orbital, long crezuta,
	const Acordare *acordare);

/* pentru probe: dosarul urmei, asteptarea pana cand firul a scris tot ce era in teava (cel mult ms) si pauzele dintre
   doua randuri "goto_omis" pe acelasi tuner (implicit 30 s la reacordare, 600 s la celelalte) */
const char *dosar();
int asteaptaScrierea(int ms);
void pauzeOmis(int reacordare_s, int altele_s);

}

#endif
