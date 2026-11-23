/*
 * Copyright (C) 2026 moneasoftware.com si hdsatelit.com
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_dvb_hdsunicable_h
#define __lib_dvb_hdsunicable_h

/* Calculul comenzilor, fara acces la tuner. Frecventele sunt in kHz. */
namespace hdsunicable
{

enum { EN50494 = 0, EN50607 = 1 };

struct Comanda
{
	unsigned char data[6];
	int len;
	int frecventa_tuner;
	int frecventa_comanda;
	unsigned int tuning_word;
	Comanda() : len(0), frecventa_tuner(0), frecventa_comanda(0), tuning_word(0)
	{
		for (int i = 0; i < 6; ++i)
			data[i] = 0;
	}
};

inline bool valid(int format, int ub, int pin)
{
	return (format == EN50494 || format == EN50607) && ub >= 0 &&
		ub < (format == EN50607 ? 32 : 8) && pin >= -1 && pin <= 255;
}

inline int pozitie(int format, int configurata, int lnb, int pozitii)
{
	int maxim = format == EN50607 ? 64 : 2;
	if ((format != EN50494 && format != EN50607) || pozitii < 1 ||
		pozitii > maxim || configurata < 0 || configurata > maxim || lnb < 1)
		return 0;
	if (configurata)
		return configurata;
	return format == EN50607 ? ((lnb - 1) % pozitii) + 1 : ((lnb & 1) ? 1 : 2);
}

/* SATCR retine si protocolul/PIN-ul pentru oprire. Indicii vechi raman identici. */
inline int memoreaza(int format, int ub, int pin)
{
	return valid(format, ub, pin) ? ub | (format << 5) | ((pin + 1) << 6) : -1;
}

inline bool calculeaza(int format, int ub, int vco, int frecventa_if,
	int banda, int pozitie, int pin, Comanda &c)
{
	c = Comanda();
	if (!valid(format, ub, pin) || vco < 950000 || vco > 2150000 ||
		banda < 0 || banda > 3 || pozitie < 1 ||
		pozitie > (format == EN50607 ? 64 : 2) ||
		frecventa_if < 0)
		return false;
	if (format == EN50607)
	{
		if (frecventa_if < 100500 || frecventa_if > 2150000)
			return false;
		int mhz = (frecventa_if + 500) / 1000;
		/* Cuvantul are 11 biti; ultimii 3 MHz se compenseaza in tuner. */
		if (mhz > 2147)
			mhz = 2147;
		unsigned int t = mhz - 100;
		c.len = pin < 0 ? 4 : 5;
		c.data[0] = pin < 0 ? 0x70 : 0x71;
		c.data[1] = (unsigned char)((ub << 3) | (t >> 8));
		c.data[2] = (unsigned char)t;
		c.data[3] = (unsigned char)(((pozitie - 1) << 2) | banda);
		if (pin >= 0)
			c.data[4] = (unsigned char)pin;
		c.frecventa_comanda = mhz * 1000;
		c.tuning_word = (c.data[1] << 16) | (c.data[2] << 8) | c.data[3];
	}
	else
	{
		/* Aceeasi rotunjire de 4 MHz ca in acordarea existenta. */
		long long calcul = ((long long)frecventa_if + vco - 1400000 + 2000) / 4000;
		if (calcul < 1 || calcul > 1023)
			return false;
		int t = (int)calcul;
		c.tuning_word = (unsigned int)(t | (banda << 10) |
			((pozitie - 1) << 12) | (ub << 13));
		c.len = pin < 0 ? 5 : 6;
		c.data[0] = 0xE0;
		c.data[1] = 0x10;
		c.data[2] = pin < 0 ? 0x5A : 0x5C;
		c.data[3] = (unsigned char)(c.tuning_word >> 8);
		c.data[4] = (unsigned char)c.tuning_word;
		if (pin >= 0)
			c.data[5] = (unsigned char)pin;
		c.frecventa_comanda = t * 4000 + 1400000 - vco;
	}
	c.frecventa_tuner = vco + c.frecventa_comanda - frecventa_if;
	return true;
}

/* UNI1 (21.11.2026): timpii comenzii pe fir, numai pentru Unicable/JESS. Secventa veche tinea 18 V doar 20 ms
   inainte de comanda si 50 ms dupa ea (setarile generale DiSEqC, din OE-A 2016), iar o comanda EN50494 de 5 octeti
   dureaza ~82 ms pe fir (15 ms + 5 x 9 biti x 1,5 ms). Cand driverul intoarce ioctl-ul inainte ca mesajul sa plece
   (alte imagini Enigma2 masoara asta si adauga pana la 94 ms), 18 V coborat dupa 50 ms poate taia comanda: banda ramane pe
   transponderul vechi ("postul nu mai emite pe aceasta frecventa") sau fara semnal (cauza probabila, nemasurata). Ca in alte
   imagini (UNICABLE_DELAY_AFTER_CHANGE_VOLTAGE_BEFORE_SWITCH_CMDS 75, UNICABLE_DELAY_AFTER_LAST_DISEQC_CMD 150); unele au 75 si
   100 pentru tot DiSEqC-ul. O valoare configurata mai mare ramane. DiSEqC-ul obisnuit (fara Unicable) nu e atins. */
enum { PAUZA_18V_MS = 75, PAUZA_DUPA_COMANDA_MS = 150, REACORDARI_MAX = 1 };

inline int pauza18V(int configurat)
{
	return configurat > PAUZA_18V_MS ? configurat : PAUZA_18V_MS;
}

inline int pauzaDupaComanda(int configurat)
{
	return configurat > PAUZA_DUPA_COMANDA_MS ? configurat : PAUZA_DUPA_COMANDA_MS;
}

/* UNR1: ceasul alimentarii apartine tunerului fizic, nu acordarii anulate.
   Schimbarile 13/18 V nu repornesc ceasul; oprirea sau un refuz il invalideaza. */
struct Alimentare
{
	long long pornire_ms;
	Alimentare(): pornire_ms(-1) {}
	void tensiune(bool pornita, bool acceptata, long long acum_ms)
	{
		if (!acceptata || !pornita)
			pornire_ms = -1;
		else if (pornire_ms < 0)
			pornire_ms = acum_ms;
	}
	int ramasa(int configurat, long long acum_ms) const
	{
		const int durata = configurat > 2700 ? configurat : 2700;
		if (pornire_ms < 0)
			return 0;
		const long long trecut = acum_ms - pornire_ms;
		return trecut >= durata ? 0 : (trecut > 0 ? durata - (int)trecut : durata);
	}
};

/* UNI1: o acordare Unicable/JESS esuata (fara semnal la capatul timpului de asteptare) pe un canal gestionat (zap,
   inregistrare; nu cautarea si nu ecranele cu canal brut, care n-au parametri tinuti) se mai incearca o data, cu
   comanda trimisa din nou, inainte sa se spuna "fara semnal" (alte imagini reacordeaza la orice esec, fara limita).
   satelit = acordarea curenta a canalului e de satelit (din parametrii ei, nu din starea tunerului: SATCR ramane de la o
   acordare Unicable si dupa o acordare pe cablu sau terestru pe acelasi tuner, fiindca numai sec.cpp il scrie, la satelit);
   satcr = valoarea SATCR a tunerului, scrisa de sec.cpp la ACEASTA acordare de satelit (-1 fara Unicable), facute =
   reacordarile deja facute pentru acordarea asta. Fara satelit cu Unicable: nimic, ca pe HEAD. */
inline bool reacordeazaDupaEsec(bool satelit, long satcr, bool gestionat, int facute)
{
	return satelit && satcr != -1 && gestionat && facute >= 0 && facute < REACORDARI_MAX;
}

inline bool opreste(int stare, Comanda &c)
{
	c = Comanda();
	if (stare < 0 || stare > 0x7FFF)
		return false;
	int ub = stare & 31, format = (stare >> 5) & 1;
	int pin = (stare >> 6) - 1;
	if (!valid(format, ub, pin))
		return false;
	if (format == EN50607)
	{
		c.len = pin < 0 ? 4 : 5;
		c.data[0] = pin < 0 ? 0x70 : 0x71;
		c.data[1] = (unsigned char)(ub << 3);
		if (pin >= 0)
			c.data[4] = (unsigned char)pin;
	}
	else
	{
		c.len = pin < 0 ? 5 : 6;
		c.data[0] = 0xE0;
		c.data[1] = 0x10;
		c.data[2] = pin < 0 ? 0x5A : 0x5C;
		c.data[3] = (unsigned char)(ub << 5);
		if (pin >= 0)
			c.data[5] = (unsigned char)pin;
	}
	return true;
}

}
#endif
