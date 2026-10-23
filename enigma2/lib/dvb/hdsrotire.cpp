/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsrotire.cpp: motorul antenei rotit pe 18 V pe tunerele care nu pot masura curentul motorului (vezi hdsrotire.h).
 * Scris de la zero pentru imaginea HD Satelit.
 */

#include <lib/dvb/hdsrotire.h>
#include <lib/dvb/sec.h>
#include <lib/dvb/rotor_calc.h>

#include <math.h>
#include <stdlib.h>

/* lib/dvb/rotor_calc.cpp (fara declaratie in rotor_calc.h) */
double calcElevation(double SatLon, double SiteLat, double SiteLon, int Height_over_ocean);

namespace hdsrotire
{

Model::Model()
	: pus(0), viteza_est(VITEZA_PRESUPUSA), viteza_vest(VITEZA_PRESUPUSA), arc(0), arc_vest(0.0), arc_est(0.0)
{
}

static double vitezaBuna(int mgrade)
{
	double v = mgrade / 1000.0;
	if (!(v >= VITEZA_MIN))
		return VITEZA_MIN;
	return v > VITEZA_MAX ? VITEZA_MAX : v;
}

void Model::puneViteze(int viteza_est_mgrade, int viteza_vest_mgrade)
{
	pus = 1;
	viteza_est = vitezaBuna(viteza_est_mgrade);
	viteza_vest = vitezaBuna(viteza_vest_mgrade);
}

void Model::puneArc(int vest_zecimi, int est_zecimi)
{
	arc = vest_zecimi < est_zecimi ? 1 : 0;
	arc_vest = vest_zecimi / 10.0;
	arc_est = est_zecimi / 10.0;
}

Zona::Zona()
	: stiuta(0), motor(0), jos(0.0), sus(0.0)
{
}

Plan::Plan()
	: pe18(0), plecare(PLECARE_NECUNOSCUTA), grade(0.0), est(0), tinta18(0), tinere_ms(0)
{
}

Loc loc(double latitudine, int sud, double longitudine, int vest)
{
	Loc l;
	l.lat = sud ? -latitudine : latitudine;
	l.lon = vest ? 360.0 - longitudine : longitudine;
	l.are = (latitudine != 0.0 || longitudine != 0.0) ? 1 : 0;
	return l;
}

double unghiOrbital(int orbital)
{
	double grade = (orbital < 0 ? -orbital : orbital) / 10.0;
	while (grade > 180.0)
		grade -= 360.0;
	return grade;
}

double unghiMotor(int orbital, const Loc &l, int *ok)
{
	if (ok)
		*ok = 0;
	if (!l.are || orbital < 0)
		return unghiOrbital(orbital);
	/* aceleasi intrari ca sec.cpp la comanda 6E */
	double sat = (orbital < 0 ? -orbital : orbital) / 10.0;
	if (calcElevation(sat, l.lat, l.lon, 0) < -90.0)
		return unghiOrbital(orbital);
	double unghi_orar = calcSatHourangle(sat, l.lat, l.lon);
	if (unghi_orar != unghi_orar)
		return unghiOrbital(orbital);
	double unghi;
	if (l.lat >= 0)
		unghi = 180.0 - unghi_orar;          /* sub 180: est (0xE000 in sec.cpp) */
	else
		unghi = unghi_orar < 180.0 ? -unghi_orar : 360.0 - unghi_orar;
	if (ok)
		*ok = 1;
	return unghi;
}

/* unghiurile plecarii si tintei in acelasi spatiu: de motor daca amandoua se pot calcula, altfel orbitale */
static int unghiuri(int de_la, int la, const Loc &l, double *a_de_la, double *a_la)
{
	int ok1 = 1, ok2 = 0;
	double u2 = unghiMotor(la, l, &ok2);
	double u1 = de_la >= 0 ? unghiMotor(de_la, l, &ok1) : 0.0;
	if (ok1 && ok2)
	{
		*a_de_la = u1;
		*a_la = u2;
		return 1;
	}
	*a_de_la = de_la >= 0 ? unghiOrbital(de_la) : 0.0;
	*a_la = unghiOrbital(la);
	return 0;
}

Plan planifica(int de_la, int la, int tinta18, const Loc &l, const Model &m, const Zona &z)
{
	Plan p;
	p.tinta18 = tinta18 ? 1 : 0;
	double a_de_la, a_la;
	int motor = unghiuri(de_la, la, l, &a_de_la, &a_la);
	double viteza_min = m.viteza_est < m.viteza_vest ? m.viteza_est : m.viteza_vest;
	double viteza = viteza_min;
	if (de_la >= 0)
	{
		p.plecare = PLECARE_STIUTA;
		p.grade = fabs(a_la - a_de_la);
		p.est = a_la > a_de_la ? 1 : (a_la < a_de_la ? -1 : 0);
		if (p.est > 0)
			viteza = m.viteza_est;
		else if (p.est < 0)
			viteza = m.viteza_vest;
	}
	else if (z.stiuta && z.motor == motor)
	{
		p.plecare = PLECARE_ZONA;
		double d1 = fabs(a_la - z.jos), d2 = fabs(a_la - z.sus);
		p.grade = d1 > d2 ? d1 : d2;
	}
	else
	{
		p.plecare = PLECARE_NECUNOSCUTA;
		if (motor && m.arc)
		{
			double d1 = a_la - m.arc_vest, d2 = m.arc_est - a_la;
			p.grade = d1 > d2 ? d1 : d2;
			if (p.grade < 0.0)
				p.grade = 0.0;
		}
		else
			p.grade = ARC_FIZIC_GRADE;
	}
	if (p.grade < PRAG_GRADE)
	{
		/* mutare de 0 grade: secventa de dinainte, fara 18 V */
		p.pe18 = 0;
		p.tinere_ms = 0;
		return p;
	}
	p.pe18 = 1;
	if (p.tinta18)
		p.tinere_ms = 0;   /* tinta e chiar pe 18 V: bucla de semnal poate porni imediat */
	else
	{
		double ms = MARJA * p.grade / viteza * 1000.0 + REZERVA_MS;
		p.tinere_ms = ms > 2000000000.0 ? 2000000000 : (int)ceil(ms);
	}
	return p;
}

void plafoneaza(Plan &p, int mrt_s)
{
	if (!p.pe18 || p.tinta18)
		return;
	if (mrt_s > 0 && p.tinere_ms > mrt_s * 1000)
		p.tinere_ms = mrt_s * 1000;
	if (p.tinere_ms < 1000)
		p.tinere_ms = 1000;
}

Zona zonaDupa(int de_la, int la, const Loc &l, const Zona &z)
{
	Zona n;
	double a_de_la, a_la;
	int motor = unghiuri(de_la, la, l, &a_de_la, &a_la);
	if (de_la >= 0)
	{
		n.stiuta = 1;
		n.motor = motor;
		n.jos = a_de_la < a_la ? a_de_la : a_la;
		n.sus = a_de_la < a_la ? a_la : a_de_la;
	}
	else if (z.stiuta && z.motor == motor)
	{
		n = z;
		if (a_la < n.jos)
			n.jos = a_la;
		if (a_la > n.sus)
			n.sus = a_la;
	}
	return n;
}

Transpondere::Transpondere()
	: pusa(0)
{
}

Secventa::Secventa()
	: comanda(0), v13(0), v18(0), tensiune(0), ton(0), diseqc13v(0), dupa_tensiune_ms(0), dupa_diseqc_ms(0),
	dupa_ton_ms(0), mrt_s(0), tunetimeout(0), proba(0), dupa_ton_oprit_ms(0)
{
}

int puneTranspondere(Transpondere &t, const char *text)
{
	t.lista.clear();
	t.pusa = 0;
	const char *p = text;
	while (p && *p)
	{
		long v[4];
		int k = 0;
		for (; k < 4; ++k)
		{
			char *capat = 0;
			v[k] = strtol(p, &capat, 10);
			if (!capat || capat == p)
				break;
			p = capat;
		}
		if (k == 4 && v[0] >= 0 && v[0] < 3600 && v[1] >= 0 && v[1] <= 3 && v[2] > 0 && v[2] < 100000000L && v[3] > 0
			&& v[3] < 1000000000L)
		{
			Transponder x;
			x.orbital = (int)v[0];
			x.polarizare = (int)v[1];
			x.frecventa = (int)v[2];
			x.rata = (int)v[3];
			t.lista.push_back(x);
		}
		while (*p && *p != ';')
			++p;
		if (*p == ';')
			++p;
	}
	t.pusa = t.lista.empty() ? 0 : 1;
	return (int)t.lista.size();
}

int areGeaman(const Transpondere &t, int orbital, int polarizare, int frecventa, int rata)
{
	if (!t.pusa)
		return -1;
	int marja = rata / 100 > 1000 ? rata / 100 : 1000;
	for (std::vector<Transponder>::const_iterator x = t.lista.begin(); x != t.lista.end(); ++x)
	{
		/* tensiunea LNB-ului (sec.cpp: polarizarea fara bitul vertical = 18 V) alege ce se prinde, nu numele polarizarii */
		if (x->orbital == orbital || (x->polarizare & 1) != (polarizare & 1))
			continue;
		if (abs(x->frecventa - frecventa) <= GEAMAN_KHZ && abs(x->rata - rata) <= marja)
			return 1;
	}
	return 0;
}

int probaPosibila(const Plan &p)
{
	return (p.plecare == PLECARE_NECUNOSCUTA && p.pe18 && !p.tinta18 && p.tinere_ms > 0) ? 1 : 0;
}

int secventaFaraMasurare(eSecCommandList &seq, const Secventa &s, const Plan &p)
{
	bool pe18 = p.pe18 != 0;
	bool tinere = pe18 && !p.tinta18 && p.tinere_ms > 0;
	bool proba = s.proba && tinere;
	int v_comanda = (pe18 && !s.diseqc13v) ? s.v18 : s.v13;
	eSecCommand::rotor cmd;
	eSecCommand::pair compare;

	/* tensiunea pentru comanda (sec.cpp: GOTO +9 sare peste aceste trei cand a pus-o el) */
	compare.voltage = v_comanda;
	compare.steps = +3;
	seq.push_back(eSecCommand(eSecCommand::IF_VOLTAGE_GOTO, compare));
	seq.push_back(eSecCommand(eSecCommand::SET_VOLTAGE, compare.voltage));
	seq.push_back(eSecCommand(eSecCommand::SLEEP, s.dupa_tensiune_ms));  // wait 150msec after voltage change

	seq.push_back(eSecCommand(eSecCommand::INVALIDATE_CURRENT_ROTORPARMS));

	/* proba de semnal pe tinta cu antena pe loc (hdsrotire.h); saltul spre capat se pune dupa ce exista capatul */
	eSecCommandList::iterator salt_prinsa = seq.end();
	int poz_salt = 0;
	if (proba)
	{
		seq.push_back(eSecCommand(eSecCommand::HDS_PROBA_SEMNAL, PROBA_PORNITA));
		compare.voltage = s.tensiune;
		compare.steps = +2;
		seq.push_back(eSecCommand(eSecCommand::IF_VOLTAGE_GOTO, compare));
		seq.push_back(eSecCommand(eSecCommand::SET_VOLTAGE, s.tensiune));
		compare.tone = s.ton;
		compare.steps = +3;
		seq.push_back(eSecCommand(eSecCommand::IF_TONE_GOTO, compare));
		seq.push_back(eSecCommand(eSecCommand::SET_TONE, s.ton));
		seq.push_back(eSecCommand(eSecCommand::SLEEP, s.dupa_ton_ms));
		seq.push_back(eSecCommand(eSecCommand::SET_FRONTEND, 0));
		eSecCommand::rotor semnal;
		semnal.direction = 1;
		semnal.deltaA = 0;
		semnal.steps = +3;
		semnal.okcount = 0;
		seq.push_back(eSecCommand(eSecCommand::SET_TIMEOUT, PROBA_PASI));
		seq.push_back(eSecCommand(eSecCommand::SLEEP, 250));
		seq.push_back(eSecCommand(eSecCommand::IF_TUNER_LOCKED_GOTO, semnal));
		seq.push_back(eSecCommand(eSecCommand::IF_TIMEOUT_GOTO, +4));
		seq.push_back(eSecCommand(eSecCommand::GOTO, -3));
		/* prins: randul din urma, apoi direct la UPDATE_CURRENT_ROTORPARAMS si SET_ROTOR_STOPPED de la capat */
		seq.push_back(eSecCommand(eSecCommand::HDS_PROBA_SEMNAL, PROBA_PRINSA));
		poz_salt = seq.size();
		seq.push_back(eSecCommand(eSecCommand::GOTO, 0));
		salt_prinsa = seq.end();
		--salt_prinsa;
		/* fara semnal: comanda de motor pleaca fara ton si pe tensiunea ei, ca inainte */
		seq.push_back(eSecCommand(eSecCommand::HDS_PROBA_SEMNAL, PROBA_FARA_SEMNAL));
		compare.tone = iDVBFrontend::toneOff;
		compare.steps = +3;
		seq.push_back(eSecCommand(eSecCommand::IF_TONE_GOTO, compare));
		seq.push_back(eSecCommand(eSecCommand::SET_TONE, iDVBFrontend::toneOff));
		seq.push_back(eSecCommand(eSecCommand::SLEEP, s.dupa_ton_oprit_ms));
		compare.voltage = v_comanda;
		compare.steps = +3;
		seq.push_back(eSecCommand(eSecCommand::IF_VOLTAGE_GOTO, compare));
		seq.push_back(eSecCommand(eSecCommand::SET_VOLTAGE, v_comanda));
		seq.push_back(eSecCommand(eSecCommand::SLEEP, s.dupa_tensiune_ms));
	}

	seq.push_back(eSecCommand(eSecCommand::SET_ROTOR_MOVING));
	seq.push_back(eSecCommand(eSecCommand::SEND_DISEQC, *s.comanda));
	int dupa_comanda_ms = 0;
	if (pe18 && v_comanda != s.v18)
	{
		/* DiSEqC pe 13 V la acest satelit: comanda a plecat pe 13 V, motorul merge pe 18 V */
		seq.push_back(eSecCommand(eSecCommand::SLEEP, s.dupa_diseqc_ms));
		seq.push_back(eSecCommand(eSecCommand::SET_VOLTAGE, s.v18));
		dupa_comanda_ms = s.dupa_diseqc_ms;
	}
	seq.push_back(eSecCommand(eSecCommand::SLEEP, 1000)); // sleep one second before change voltage or tone

	compare.voltage = s.tensiune;
	compare.steps = tinere ? +4 : +3;
	seq.push_back(eSecCommand(eSecCommand::IF_VOLTAGE_GOTO, compare)); // correct final voltage?
	if (tinere)
	{
		/* tinta pe 13 V: 18 V ramane cat dureaza mutarea estimata, socotita de la comanda */
		int rest = p.tinere_ms - 1000 - dupa_comanda_ms;
		seq.push_back(eSecCommand(eSecCommand::SLEEP, rest > 0 ? rest : 0));
		seq.push_back(eSecCommand(eSecCommand::HDS_ROTIRE_GATA));
	}
	else
		seq.push_back(eSecCommand(eSecCommand::SLEEP, 2000));  // wait 2 second before set high voltage
	seq.push_back(eSecCommand(eSecCommand::SET_VOLTAGE, s.tensiune));

	compare.tone = s.ton;
	compare.steps = +3;
	seq.push_back(eSecCommand(eSecCommand::IF_TONE_GOTO, compare));
	seq.push_back(eSecCommand(eSecCommand::SET_TONE, s.ton));
	seq.push_back(eSecCommand(eSecCommand::SLEEP, s.dupa_ton_ms));
	seq.push_back(eSecCommand(eSecCommand::SET_FRONTEND, 0));

	int bucla_s = s.mrt_s;
	int total_s = s.mrt_s;
	if (tinere)
	{
		/* inainte bucla pornea la 1 s dupa comanda (tinta pe 13 V); acum la capatul tinerii */
		int tinere_s = (p.tinere_ms + 999) / 1000;
		bucla_s = s.mrt_s + 1 - tinere_s;
		if (bucla_s < BUCLA_MIN_S)
			bucla_s = BUCLA_MIN_S;
		total_s = tinere_s + bucla_s;
	}

	cmd.direction = 1;  // check for running rotor
	cmd.deltaA = 0;
	cmd.steps = +3;
	cmd.okcount = 0;
	seq.push_back(eSecCommand(eSecCommand::SET_TIMEOUT, bucla_s * 4));  // mrt is in seconds... our SLEEP time is 250ms.. so * 4
	seq.push_back(eSecCommand(eSecCommand::SLEEP, 250));  // 250msec delay
	seq.push_back(eSecCommand(eSecCommand::IF_TUNER_LOCKED_GOTO, cmd));
	seq.push_back(eSecCommand(eSecCommand::IF_TIMEOUT_GOTO, +5));
	seq.push_back(eSecCommand(eSecCommand::GOTO, -3));  // goto loop start
	if (proba)
		salt_prinsa->steps = seq.size() - poz_salt;   /* saltul probei prinse: pe comanda de mai jos */
	seq.push_back(eSecCommand(eSecCommand::UPDATE_CURRENT_ROTORPARAMS));
	seq.push_back(eSecCommand(eSecCommand::SET_ROTOR_STOPPED));
	seq.push_back(eSecCommand(eSecCommand::GOTO, +4));
	seq.push_back(eSecCommand(eSecCommand::START_TUNE_TIMEOUT, (int)s.tunetimeout));
	seq.push_back(eSecCommand(eSecCommand::SET_FRONTEND, 1));
	seq.push_back(eSecCommand(eSecCommand::GOTO, -5));
	return total_s;
}

}
