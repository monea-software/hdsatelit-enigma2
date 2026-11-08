/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdscitirifrontend.h: o singura citire a starii tunerului pe secunda, impartita de toti cititorii.
 *
 * DE CE: pe primul Vu+ Solo SE real (Broadcom BCM7241, MIPS, tunerul AVL6211 pe I2C) firul principal al enigma2 tinea
 * un nucleu la 95-99%, jumatate in nucleul Linux, cu intreruperea controlerului I2C (UPG_BSC) la sute pe secunda. Toate
 * citirile starii tunerului trec prin eDVBFrontend::readFrontendData (lib/dvb/frontend.cpp): FE_READ_BER, FE_READ_SNR,
 * FE_READ_SIGNAL_STRENGTH, FE_READ_STATUS, fiecare cu tranzactiile ei pe I2C. Peste zece cititori din Python (sursa
 * FrontendStatus, convertoarele temei, ecranul negru, culegerea, istoricul semnalului, pagina web, gasirea semnalului...)
 * le cer fiecare dupa ceasul lui, iar getFrontendStatus citea SNR-ul si starea de cate doua ori.
 *
 * CE FACE: pe fiecare tuner, ultima valoare bruta a fiecarei citiri (BER, SNR, nivel, stare) cu ora ei. O cerere in mai
 * putin de TTL de la citire primeste valoarea tinuta; altfel se face ioctl-ul. SNR-ul pentru calitate si pentru dB vine din
 * aceeasi citire, „prins” si „sincronizat” din aceeasi stare. TTL: TTL_MS (o citire pe secunda); TTL_LENT_MS cand un ioctl
 * dureaza in medie peste PRAG_LENT_US (I2C foarte lent). O eroare a ioctl-ului se tine si ea TTL (cu valoarea 0, nu cu
 * valoarea veche), ca un driver care refuza sa nu fie intrebat la fiecare cerere.
 * Citesc DIRECT (fara memorie, dar numarat): bucla SEC a acordarii (motorul, IF_TUNER_LOCKED) si timeout(). Memoria se
 * goleste la acordare, la deschiderea si inchiderea tunerului si la schimbarea starii venita de la driver (prins/pierdut),
 * deci pierderea semnalului se vede imediat ce driverul o anunta.
 *
 * CONTOARE (toate tunerele): cereri, cate au venit din memorie, ioctl-uri facute (si cate directe), erori, microsecunde in
 * ioctl. Atomice pe 32 de biti (pe MIPS de 32 de biti cele de 64 nu sunt atomice), deci se pot citi din orice fir; se
 * folosesc diferentele (modulo 2^32). Python le citeste cu enigma.getFrontendReadCounts() (frontend.h), raportul de
 * procesor (Components/HdsProcesorRaport.py) le pune la inceputul si la sfarsitul ferestrei lui.
 *
 * Fara nimic din enigma2: se poate compila si proba separat, cu un ceas si un ioctl false.
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */
#ifndef __lib_dvb_hdscitirifrontend_h
#define __lib_dvb_hdscitirifrontend_h

#include <atomic>
#include <time.h>

namespace hdscitiri
{

enum Fel { BER = 0, SNR = 1, NIVEL = 2, STARE = 3, NUMAR_FELURI = 4 };

static const int TTL_MS = 1000;              // o citire pe secunda
static const int TTL_LENT_MS = 2000;         // I2C foarte lent: o citire la doua secunde
static const unsigned int PRAG_LENT_US = 25000;  // un ioctl in medie peste 25 ms = I2C foarte lent

struct Valoare
{
	long long t_ms;
	unsigned int val;
	int err;
	bool are;
};

struct Memorie
{
	Valoare v[NUMAR_FELURI];
	unsigned int cost_us;   // media alunecatoare (1/8) a duratei unui ioctl pe tunerul acesta; 0 = nemasurat

	Memorie(): cost_us(0) { goleste(); }

	void goleste()
	{
		for (int i = 0; i < NUMAR_FELURI; ++i)
		{
			v[i].t_ms = 0;
			v[i].val = 0;
			v[i].err = 0;
			v[i].are = false;
		}
	}

	int ttlMs() const { return cost_us > PRAG_LENT_US ? TTL_LENT_MS : TTL_MS; }

	bool proaspata(Fel f, long long acum_ms) const
	{
		const Valoare &x = v[f];
		return x.are && acum_ms >= x.t_ms && acum_ms - x.t_ms < ttlMs();
	}

	void pune(Fel f, long long acum_ms, unsigned int val, int err, unsigned int durata_us)
	{
		v[f].t_ms = acum_ms;
		v[f].val = val;
		v[f].err = err;
		v[f].are = true;
		cost_us = cost_us ? (unsigned int)(((unsigned long long)cost_us * 7 + durata_us) / 8) : (durata_us ? durata_us : 1);
	}
};

struct Contoare
{
	std::atomic<unsigned int> cereri, din_memorie, ioctl, ioctl_direct, erori, us_ioctl;
	Contoare(): cereri(0), din_memorie(0), ioctl(0), ioctl_direct(0), erori(0), us_ioctl(0) {}
};

/* contoarele tuturor tunerelor (unul singur in program) */
inline Contoare &contoare()
{
	static Contoare c;
	return c;
}

/* ceasul monoton adevarat (in probe: alt ceas, cu ms() si us()) */
struct CeasMonoton
{
	long long ms() const { return us() / 1000; }
	long long us() const
	{
		struct timespec t;
		clock_gettime(CLOCK_MONOTONIC, &t);
		return (long long)t.tv_sec * 1000000LL + t.tv_nsec / 1000;
	}
};

/*
 * O cerere de citire. direct = fara memorie (bucla SEC, timeout()). citeste(val) face ioctl-ul si intoarce 0 sau errno
 * (val ramane 0 la eroare). err primeste eroarea citirii (tinute sau proaspete). Intoarce valoarea bruta.
 */
template <class Ceas, class Citeste>
unsigned int cere(Memorie &m, Fel f, bool direct, const Ceas &ceas, Citeste citeste, int &err)
{
	Contoare &c = contoare();
	c.cereri.fetch_add(1, std::memory_order_relaxed);
	long long acum = ceas.ms();
	if (!direct && m.proaspata(f, acum))
	{
		c.din_memorie.fetch_add(1, std::memory_order_relaxed);
		err = m.v[f].err;
		return m.v[f].val;
	}
	long long t0 = ceas.us();
	unsigned int val = 0;
	err = citeste(val);
	if (err)
		val = 0;
	long long d = ceas.us() - t0;
	unsigned int durata = d <= 0 ? 0 : (d > 0x7fffffffLL ? 0x7fffffffU : (unsigned int)d);
	c.ioctl.fetch_add(1, std::memory_order_relaxed);
	if (direct)
		c.ioctl_direct.fetch_add(1, std::memory_order_relaxed);
	if (err)
		c.erori.fetch_add(1, std::memory_order_relaxed);
	c.us_ioctl.fetch_add(durata, std::memory_order_relaxed);
	m.pune(f, acum, val, err, durata);
	return val;
}

}

#endif
