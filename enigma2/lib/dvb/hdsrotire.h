/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsrotire.h: motorul antenei rotit pe 18 V pe tunerele care nu pot masura curentul motorului.
 *
 * DE CE: motorul (DiSEqC 1.2 / USALS) e alimentat din tensiunea LNB-ului. Ramura obisnuita din sec.cpp (fara masurarea
 * curentului) pornea motorul pe 13 V si trecea pe tensiunea transponderului tinta abia dupa ~3 s, deci spre o tinta pe
 * polarizarea verticala (13 V) motorul mergea tot drumul pe 13 V. Pe receptorul de proba (Viper 4K V20)
 * comanda spre 19,2E data pe un transponder vertical nu a adus semnalul de 4 ori la rand, iar aceeasi comanda data pe
 * unul orizontal (18 V dupa 3 s) l-a adus in 16 s: pe 13 V motorul e prea slab (vant, frecare) si se opreste pe drum.
 *
 * CE FACE (numai pe ramura fara masurarea curentului si fara Unicable/JESS; ramura cu masurare ramane cum era):
 *   - 18 V inainte de comanda de motor (6E sau 6B); cu "DiSEqC pe 13 V" la satelit comanda pleaca pe 13 V si 18 V vine
 *     imediat dupa ea;
 *   - tinta pe 18 V (orizontala): tensiunea ramane, bucla de semnal porneste ca inainte, fara cele 2 s de asteptare;
 *   - tinta pe 13 V (verticala): 18 V se tine cat dureaza mutarea estimata, cu marja, apoi tensiunea si tonul tintei si
 *     bucla obisnuita de semnal (semnalul vertical nu se poate prinde pe 18 V);
 *   - o mutare de 0 grade nu trece deloc pe 18 V: secventa e exact cea de dinainte.
 * Durata: drumul in grade de motor (unghiul orar USALS din locul antenei, aceeasi formula ca sec.cpp la comanda 6E;
 * fara loc, diferenta orbitala) si viteza motorului invatata din mutarile lui (Components/HdsMotorViteza.py, modelul
 * T = t0 + grade / viteza, pus din Python prin hdsSetRotorModel; pana atunci presupunerea de acolo). t0 (pornirea si
 * confirmarea semnalului) nu e mers, deci nu intra in tinere: tinerea pe 18 V = MARJA * grade / viteza + REZERVA_MS,
 * cel mult timpul maxim al nucleului pentru mutarea asta (mrt).
 * Plecarea: pozitia crezuta de nucleu; daca nu se stie, dar mutarea de dinainte a fost intrerupta (zap in mers), antena
 * e undeva intre capetele ei (zona), deci drumul cel mai lung de acolo; altfel cel mai lung drum posibil: de la marginea
 * cea mai departata a arcului vizibil (pusa din Python prin hdsSetRotorArc), fara arc ARC_FIZIC_GRADE, tot cel mult mrt
 * (MOTOR_RUNNING_TIMEOUT, pus de Components/HdsMotorPlafon.py din acelasi model).
 *
 * PROBA DE SEMNAL INAINTEA COMENZII (numai plecarea necunoscuta, cu tinta pe 13 V): antena se roteste cat mai rar, iar
 * dupa o pozitie uitata (flash, o miscare de mana, setarile motorului schimbate) ea sta de cele mai multe ori chiar pe
 * satelitul tintei. Fara proba, comanda pleca spre tinta cu drumul cel mai lung, deci 18 V tinut zeci de secunde si
 * "Antena se roteste" pe ecran tot atat, cu antena pe loc. Acum, inainte de SET_ROTOR_MOVING: tensiunea si tonul
 * tintei, acordarea si o bucla scurta de semnal (PROBA_PASI citiri la 250 ms; IF_TUNER_LOCKED_GOTO cere 5 citiri bune
 * la rand). Semnal prins: nicio comanda de motor, pozitia crezuta devine tinta (UPDATE_CURRENT_ROTORPARAMS de la
 * capatul secventei), afisajul nu porneste deloc. Fara semnal: tonul oprit (comanda DiSEqC pleaca fara ton),
 * tensiunea comenzii, apoi secventa de dinainte. Comanda HDS_PROBA_SEMNAL lasa randul "proba_semnal" in urma motorului.
 * Paza: o blocare pe acelasi transponder al ALTUI satelit ar lasa antena acolo, cu pozitia crezuta gresita (si cu
 * semnal, deci nimic din Python nu ar mai porni readucerea). In secventa nu se poate citi TSID/ONID (ar trebui demux),
 * de aceea proba se face numai cand transponderul tintei nu are geaman pe alt satelit al motorului: aceeasi tensiune
 * (polarizarea H/L sau V/R), frecventa la cel mult GEAMAN_KHZ, rata la 1 % (aceeasi regula ca referintele readucerii
 * din Components/HdsMotorPozitie.py). Lista transponderelor satelitilor motorului o pune Python
 * (Components/HdsMotorPlafon.py, hdsSetRotorTransponders); fara lista, fara proba.
 *
 * Fisierul nu scrie nimic si nu cheama enigma2 (in afara de rotor_calc): se compileaza si intr-o proba pe PC, impreuna
 * cu un interpretor al secventei.
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */
#ifndef __lib_dvb_hdsrotire_h
#define __lib_dvb_hdsrotire_h

#include <vector>

class eSecCommandList;
class eDVBDiseqcCommand;

namespace hdsrotire
{

/* presupunerea de dinainte de primul model pus din Python si marginile vitezei (Components/HdsMotorViteza.py) */
constexpr double VITEZA_PRESUPUSA = 1.2;
constexpr double VITEZA_MIN = 0.3;
constexpr double VITEZA_MAX = 6.0;
/* tinerea = MARJA * grade / viteza + REZERVA_MS. Viteza invatata vine pana acum mai ales din mutari pe 13 V (mai
   incete decat pe 18 V), deci marja reala e mai mare; REZERVA_MS acopera si pornirea motorului (~0,3 s) */
constexpr double MARJA = 1.2;
constexpr int REZERVA_MS = 1500;
/* drumul cel mai lung al unui motor USALS (-80..+80 grade), cand nici plecarea, nici arcul vizibil nu se stiu */
constexpr double ARC_FIZIC_GRADE = 160.0;
/* sub atat (o zecime de grad rotunjita in jos) mutarea e de 0 grade */
constexpr double PRAG_GRADE = 0.05;
/* bucla de semnal de dupa tinere dureaza cel putin atat (secunde) */
constexpr int BUCLA_MIN_S = 10;
/* proba de semnal inaintea comenzii: citiri la 250 ms (4 s). Din ele, 5 citiri bune la rand confirma semnalul, deci
   tunerul are cel mult ~2,7 s sa prinda transponderul */
constexpr int PROBA_PASI = 16;
/* geamanul unui transponder pe alt satelit: frecventa la cel mult atatia kHz (ca HdsMotorPozitie.VERIFICARE_GEAMAN_KHZ) */
constexpr int GEAMAN_KHZ = 3000;

enum { PLECARE_STIUTA = 0, PLECARE_ZONA = 1, PLECARE_NECUNOSCUTA = 2 };
/* valoarea comenzii HDS_PROBA_SEMNAL: inceputul probei, semnal prins, fara semnal in timpul probei */
enum { PROBA_PORNITA = 0, PROBA_PRINSA = 1, PROBA_FARA_SEMNAL = 2 };
/* de ce s-a facut sau nu proba (urma motorului, randul comenzii): 0 = nu se cere (plecarea se stie, tinta pe 18 V),
   1 = facuta (si fara semnal, altfel comanda nu mai pleaca), 2 = sarita: transponderul are geaman, 3 = sarita: lista
   transponderelor nu e pusa */
enum { PROBA_NECERUTA = 0, PROBA_FACUTA = 1, PROBA_GEAMAN = 2, PROBA_FARA_LISTA = 3 };

/* modelul timpului unei mutari pe un tuner (cheia = slotul), pus din Python */
struct Model
{
	int pus;             /* 0 = presupunerea */
	double viteza_est;   /* grade de motor pe secunda, spre est */
	double viteza_vest;
	int arc;             /* 1 = marginile arcului vizibil se stiu */
	double arc_vest;     /* unghiul motorului la marginea de vest a arcului vizibil (grade, est pozitiv) */
	double arc_est;
	Model();
	void puneViteze(int viteza_est_mgrade, int viteza_vest_mgrade);
	void puneArc(int vest_zecimi, int est_zecimi);   /* vest >= est = arcul nu se stie */
};

/* unde poate fi antena cand nucleul nu-i stie pozitia: intre doua unghiuri (capetele unei mutari intrerupte) */
struct Zona
{
	int stiuta;
	int motor;           /* 1 = unghiuri de motor, 0 = unghiuri orbitale (fara loc) */
	double jos, sus;
	Zona();
};

/* locul antenei, exact cum il foloseste sec.cpp la comanda 6E */
struct Loc
{
	double lat;          /* SiteLat: sud negativ */
	double lon;          /* SiteLon: 0..360 (vest = 360 - longitudine) */
	int are;             /* 0 = latitudinea si longitudinea sunt 0 (nepuse): se lucreaza cu diferenta orbitala */
};

/* hotararea pentru o mutare */
struct Plan
{
	int pe18;            /* 1 = motorul se roteste pe 18 V */
	int plecare;         /* PLECARE_* */
	double grade;        /* drumul estimat (la plecare necunoscuta: cel mai lung posibil), grade de motor */
	int est;             /* +1 spre est, -1 spre vest, 0 nu se stie */
	int tinta18;         /* 1 = tensiunea tintei e 18 V (polarizarea orizontala) */
	int tinere_ms;       /* cat ramane 18 V de la comanda; 0 = nu e nevoie (tinta pe 18 V sau mutare de 0 grade) */
	Plan();
};

Loc loc(double latitudine, int sud, double longitudine, int vest);
/* unghiul motorului (grade, est pozitiv) pentru pozitia orbitala `orbital` (zecimi, 0..3599 ca in sec.cpp); *ok = 0
   cand nu se poate calcula (fara loc, satelit sub orizont) */
double unghiMotor(int orbital, const Loc &l, int *ok);
/* unghiul orbital (grade, est pozitiv, -180..180), folosit fara loc */
double unghiOrbital(int orbital);
/* hotararea: de_la = pozitia crezuta (-1 necunoscuta), la = tinta (zecimi) */
Plan planifica(int de_la, int la, int tinta18, const Loc &l, const Model &m, const Zona &z);
/* tinerea cel mult mrt_s (timpul maxim al nucleului pentru mutarea asta) si cel putin 1 s */
void plafoneaza(Plan &p, int mrt_s);
/* zona antenei dupa ce pleaca mutarea de_la -> la (pentru urmatoarea acordare, daca asta se intrerupe) */
Zona zonaDupa(int de_la, int la, const Loc &l, const Zona &z);

/* un transponder al unui satelit al motorului (satellites.xml), cum il pune Python */
struct Transponder
{
	int orbital;         /* zecimi, 0..3599 ca in sec.cpp */
	int polarizare;      /* 0 H, 1 V, 2 L, 3 R (eDVBFrontendParametersSatellite) */
	int frecventa;       /* kHz */
	int rata;            /* simboluri pe secunda */
};

/* transponderele satelitilor unui motor; pusa = 0: lista nu se stie (atunci nu se face proba) */
struct Transpondere
{
	int pusa;
	std::vector<Transponder> lista;
	Transpondere();
};

/* lista din textul pus de Python: "orbital polarizare frecventa rata" despartite prin ';' (randurile stricate se
   sar); intoarce cate s-au pus. O lista goala lasa pusa = 0. */
int puneTranspondere(Transpondere &t, const char *text);
/* 1 = pe alt satelit e un transponder pe aceeasi tensiune (H/L sau V/R), cu frecventa la cel mult GEAMAN_KHZ si rata
   la 1 % (cel putin 1000): tunerul l-ar prinde si cu antena acolo; 0 = niciunul; -1 = lista nu e pusa */
int areGeaman(const Transpondere &t, int orbital, int polarizare, int frecventa, int rata);
/* 1 = mutarea e una pentru care proba are rost: plecarea necunoscuta, motorul pe 18 V, tinta pe 13 V cu tinere */
int probaPosibila(const Plan &p);

/* ce ii trebuie secventei ramurii fara masurare (sec.cpp) */
struct Secventa
{
	const eDVBDiseqcCommand *comanda;  /* 6E sau 6B */
	int v13, v18;                      /* VOLTAGE(13) si VOLTAGE(18) din sec.cpp (cu tensiunea marita, 14/19 V) */
	int tensiune, ton;                 /* ale transponderului tinta */
	int diseqc13v;                     /* satelitul cere DiSEqC pe 13 V */
	int dupa_tensiune_ms;              /* DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_MOTOR_CMD */
	int dupa_diseqc_ms;                /* DELAY_AFTER_LAST_DISEQC_CMD */
	int dupa_ton_ms;                   /* DELAY_AFTER_FINAL_CONT_TONE_CHANGE */
	int mrt_s;                         /* timpul maxim al buclei de semnal, cum il calculeaza sec.cpp */
	unsigned int tunetimeout;
	int proba;                         /* 1 = intai semnalul tintei cu antena pe loc (probaPosibila si fara geaman) */
	int dupa_ton_oprit_ms;             /* DELAY_AFTER_CONT_TONE_DISABLE_BEFORE_DISEQC (tonul oprit dupa proba) */
	Secventa();
};

/* adauga la `seq` ramura fara masurarea curentului (proba de semnal daca s.proba, motorul, tinerea, tensiunea si tonul
   tintei, bucla de semnal); intoarce timpul maxim total in secunde de la SET_ROTOR_MOVING (pentru hdsNoteRotorMovement;
   proba de dinainte nu intra). Primele trei comenzi sunt mereu verificarea tensiunii, punerea ei si asteptarea, iar a
   patra INVALIDATE_CURRENT_ROTORPARMS: sec.cpp sare peste primele trei (GOTO +9) cand tensiunea era oprita si a pus-o
   el. Proba vine dupa INVALIDATE_CURRENT_ROTORPARMS. */
int secventaFaraMasurare(eSecCommandList &seq, const Secventa &s, const Plan &p);

}

#endif
