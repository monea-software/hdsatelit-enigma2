/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsspectru.cpp: nivelul sunetului pe 32 de benzi, din cadrele comprimate (vezi hdsspectru.h).
 *
 * Ce se citeste din fiecare format (numai pana unde apare nivelul; restul cadrului se lasa):
 * - AAC (ADTS, LATM/LOAS; LC si HE-AAC): elementele SCE / CPE / LFE ale blocului, cu sectiunile, factorii de scala,
 *   impulsurile, TNS si liniile spectrale (cartile Huffman 1-11). Liniile se aduc la marimea lor adevarata
 *   (|q|^(4/3) * 2^((sf-100)/4)), cu stereo M/S, stereo de intensitate, zgomotul PNS si filtrul TNS, ca in decodor;
 *   nu se face transformarea inversa, deci nu apar esantioane. Energia liniilor se aduna pe benzile de fs/64. La
 *   HE-AAC benzile de peste miez vin din anvelopa SBR a primului element audio.
 * - AC-3 si E-AC-3: toate blocurile cadrului; mantisele se citesc (lungimea lor iese din alocarea bitilor, calculata ca
 *   in decodor), deci liniile au marimea adevarata (mantisa * 2^-exponent), cu cuplajul, rematricea si extensia
 *   spectrala E-AC-3. Pe cadru, pe fiecare banda, blocul cel mai tare.
 * - DTS: factorii de scala ai celor 32 de subbenzi ale nucleului (primul subcadru).
 * - PCM SMPTE 302M: esantioanele, cu o transformare Fourier de 128 de puncte pe cel mult 16 ferestre din pachet.
 *
 * Nivelul unei benzi, in dB fata de semnalul plin, se aduce pe scara factorilor de scala MPEG Layer II (indicele 0..62,
 * 2 dB pe treapta), cu o constanta pe format, masurata pe aceeasi muzica codata in fiecare format. Centrul intra in
 * amandoua partile la jumatate de putere, spatele la fel; LFE nu intra.
 */

#include <lib/dvb/hdsspectru.h>
#include <lib/dvb/hdsspectru_tabele.h>
#include <math.h>
#include <cmath>
#include <string.h>
#include <new>

namespace hdsspectru
{

/* ---------------------------------------------------------------- constante */

static const uint32_t CADRU_MAX = 65540;        /* cel mai mare cadru primit (PES 302M: 4 + 65535) */
static const int CAPAT = 8;                     /* zerouri dupa cadru, pentru citirile de 4 octeti */

/* dB fata de semnalul plin = 10*log10(energie) + constanta formatului */
static const double CALIB_AAC = -143.8;
/* energia benzilor SBR (anvelopa, in domeniul QMF) adusa la scara liniilor AAC: +26,3 dB, masurat pe muzica HE-AAC fata
   de sunetul decodat (benzile SBR la acelasi nivel ca miezul) */
static const double CALIB_SBR = 427.0;
static const double CALIB_AC3 = 8.9;
static const double CALIB_DTS = -118.2;
static const double CALIB_PCM = -26.8;

/* ---------------------------------------------------------------- citirea bitilor */

struct Biti
{
	const uint8_t *d;
	uint32_t poz;
	uint32_t sf;
	bool rau;

	void init(const uint8_t *date, uint32_t octeti)
	{
		d = date;
		poz = 0;
		sf = octeti * 8;
		rau = false;
	}
	/* urmatorii n biti (1..25), fara sa inainteze; dupa capat: zero */
	uint32_t priveste(int n) const
	{
		if (poz >= sf)
			return 0;
		const uint8_t *p = d + (poz >> 3);
		uint32_t v = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
		return (v << (poz & 7)) >> (32 - n);
	}
	void sari(uint32_t n)
	{
		if (poz > sf || n > sf - poz)
		{
			rau = true;
			poz = sf;
			return;
		}
		poz += n;
	}
	uint32_t ia(int n)
	{
		if (n <= 0)
			return 0;
		if (n > 25)
		{
			uint32_t sus = ia(n - 16);
			return (sus << 16) | ia(16);
		}
		uint32_t v = priveste(n);
		sari(n);
		return v;
	}
	bool ia1()
	{
		return ia(1) != 0;
	}
	/* alinierea la octet, fata de pozitia `fata` */
	void aliniaza(uint32_t fata = 0)
	{
		uint32_t r = (poz - fata) & 7;
		if (r)
			sari(8 - r);
	}
	uint32_t ramase() const
	{
		return sf > poz ? sf - poz : 0;
	}
};

/* ---------------------------------------------------------------- coduri Huffman */

struct IntrareVlc
{
	int16_t val;        /* simbolul sau, in primul nivel, inceputul subtabelului */
	uint8_t lung;       /* lungimea codului (in subtabel: bitii de dupa primul nivel); 0 = nu e simbol */
	uint8_t sub;        /* bitii subtabelului (numai in primul nivel) */
};

struct Vlc
{
	int maxim;
	int prim;
	IntrareVlc *t;
	bool bun;
};

/* Tabelul de decodare pe doua niveluri. Refuza (bun = false) un cod care nu e prefix complet: fiecare intrare trebuie
   acoperita exact o data. */
static void construiesteVlc(Vlc &v, int n, const uint32_t *coduri, const uint8_t *lungimi)
{
	v.bun = false;
	v.t = 0;
	v.maxim = 0;
	v.prim = 0;
	for (int i = 0; i < n; i++)
		if (lungimi[i] > v.maxim)
			v.maxim = lungimi[i];
	if (v.maxim < 1 || v.maxim > 25)
		return;
	v.prim = v.maxim < 9 ? v.maxim : 9;
	int subBiti[512];
	memset(subBiti, 0, sizeof(subBiti));
	for (int i = 0; i < n; i++)
	{
		int l = lungimi[i];
		if (l < 1 || (coduri[i] >> l) != 0)
			return;
		if (l > v.prim)
		{
			int pre = coduri[i] >> (l - v.prim);
			if (l - v.prim > subBiti[pre])
				subBiti[pre] = l - v.prim;
		}
	}
	int marime = 1 << v.prim;
	for (int p = 0; p < (1 << v.prim); p++)
		if (subBiti[p])
			marime += 1 << subBiti[p];
	if (marime > 32767)
		return;
	IntrareVlc *t = new (std::nothrow) IntrareVlc[marime];
	if (!t)
		return;
	memset(t, 0, sizeof(IntrareVlc) * marime);
	int loc = 1 << v.prim;
	for (int p = 0; p < (1 << v.prim); p++)
		if (subBiti[p])
		{
			t[p].val = loc;
			t[p].sub = subBiti[p];
			loc += 1 << subBiti[p];
		}
	for (int i = 0; i < n; i++)
	{
		int l = lungimi[i];
		uint32_t c = coduri[i];
		if (l <= v.prim)
		{
			int baza = c << (v.prim - l);
			for (int j = 0; j < (1 << (v.prim - l)); j++)
			{
				IntrareVlc &e = t[baza + j];
				if (e.lung || e.sub)
				{
					delete[] t;
					return;
				}
				e.val = i;
				e.lung = l;
			}
		}
		else
		{
			int pre = c >> (l - v.prim);
			int sb = subBiti[pre];
			int rest = c & ((1u << (l - v.prim)) - 1);
			int baza = t[pre].val + (rest << (sb - (l - v.prim)));
			for (int j = 0; j < (1 << (sb - (l - v.prim))); j++)
			{
				IntrareVlc &e = t[baza + j];
				if (e.lung)
				{
					delete[] t;
					return;
				}
				e.val = i;
				e.lung = l - v.prim;
			}
		}
	}
	for (int p = 0; p < (1 << v.prim); p++)
		if (!t[p].lung && !t[p].sub)
		{
			delete[] t;
			return;
		}
	for (int p = 1 << v.prim; p < marime; p++)
		if (!t[p].lung)
		{
			delete[] t;
			return;
		}
	v.t = t;
	v.bun = true;
}

static inline int decodeaza(Biti &b, const Vlc &v)
{
	uint32_t w = b.priveste(v.maxim);
	const IntrareVlc &e = v.t[w >> (v.maxim - v.prim)];
	if (e.lung)
	{
		b.sari(e.lung);
		return e.val;
	}
	if (e.sub)
	{
		const IntrareVlc &f = v.t[e.val + ((w >> (v.maxim - v.prim - e.sub)) & ((1u << e.sub) - 1))];
		if (f.lung)
		{
			b.sari(v.prim + f.lung);
			return f.val;
		}
	}
	b.rau = true;
	return 0;
}

/* ---------------------------------------------------------------- tabelele facute o data */

static const int PUTERE_MAX = 8208;             /* 8191 (cartea 11) + 15 (un impuls) + 2 */

struct Tabele
{
	Vlc spectru[11];
	Vlc sf;
	float putere43[PUTERE_MAX];
	float castig[256];          /* 2^((i-100)/4) */
	uint8_t invers[256];        /* bitii octetului in ordine inversa (302M) */
	float fereastra[128];       /* Hann, pentru PCM */
	float cosT[64], sinT[64];
	bool bun;

	Tabele()
	{
		bun = true;
		for (int k = 0; k < 11; k++)
		{
			uint32_t c[289];
			for (int i = 0; i < hdsAacMarimi[k]; i++)
				c[i] = hdsAacCoduri[k][i];
			construiesteVlc(spectru[k], hdsAacMarimi[k], c, hdsAacLungimi[k]);
			bun = bun && spectru[k].bun;
		}
		construiesteVlc(sf, 121, hdsAacCodSf, hdsAacLungSf);
		bun = bun && sf.bun;
		for (int i = 0; i < PUTERE_MAX; i++)
			putere43[i] = (float)pow((double)i, 4.0 / 3.0);
		for (int i = 0; i < 256; i++)
		{
			castig[i] = (float)pow(2.0, (i - 100) / 4.0);
			int r = 0;
			for (int j = 0; j < 8; j++)
				if (i & (1 << j))
					r |= 0x80 >> j;
			invers[i] = r;
		}
		for (int i = 0; i < 128; i++)
			fereastra[i] = (float)(0.5 - 0.5 * cos(2.0 * M_PI * (i + 0.5) / 128.0));
		for (int i = 0; i < 64; i++)
		{
			cosT[i] = (float)cos(2.0 * M_PI * i / 128.0);
			sinT[i] = (float)-sin(2.0 * M_PI * i / 128.0);
		}
	}
};

static const Tabele &tabele()
{
	static Tabele t;
	return t;
}

/* ---------------------------------------------------------------- energia pe benzi */

enum { STANGA = 0, DREAPTA = 1, CENTRU = 2, AMBELE = 3 };

/* Energia unui cadru pe benzile de fs/64, pe doua parti (stanga, dreapta) */
struct Acum
{
	double e[2][BENZI];
	int sce, cpe;               /* elementele / canalele audio intalnite (fara LFE) */

	void goleste()
	{
		memset(e, 0, sizeof(e));
		sce = cpe = 0;
	}
	/* energia liniei k din `linii` (care acopera 0..fs/2) */
	inline void adauga(int parte, int k, int linii, double en)
	{
		int b = (int)(((long)k * BENZI) / linii);
		if (b >= BENZI)
			b = BENZI - 1;
		if (parte == CENTRU)
		{
			e[0][b] += 0.5 * en;
			e[1][b] += 0.5 * en;
		}
		else if (parte == AMBELE)
		{
			e[0][b] += en;
			e[1][b] += en;
		}
		else
			e[parte][b] += en;
	}
};

/* energie -> indicele factorului de scala MPEG (dB = 6,02 - 2,0069 * indice) */
static void spreIndici(const Acum &a, double calib, uint8_t niv[2][BENZI])
{
	for (int p = 0; p < 2; p++)
		for (int b = 0; b < BENZI; b++)
		{
			double en = a.e[p][b];
			if (!(en > 1e-30))
			{
				niv[p][b] = GOL;
				continue;
			}
			if (!std::isfinite(en))
			{
				/* un cadru stricat (intensitate AAC uriasa, TNS de ordin mare) poate duce energia peste double: banda
				   la maxim, fara conversia inf -> int (comportare nedefinita) */
				niv[p][b] = 0;
				continue;
			}
			double db = 10.0 * log10(en) + calib;
			double i = (6.02 - db) / 2.0069;
			int k = (int)floor(i + 0.5);
			if (k < 0)
				k = 0;
			if (k > 62)
				k = 62;
			niv[p][b] = k;
		}
}

/* ---------------------------------------------------------------- SBR (HE-AAC): benzile de sus */

/* Miezul AAC al unui flux HE-AAC acopera numai partea de jos a sunetului; partea de sus o reface decodorul din datele
   SBR (ISO/IEC 14496-3, 4.6.18). Aici se citesc antetul SBR (din el ies benzile SBR, in subbenzile QMF de fs/128) si
   anvelopa fiecarui canal: energia fiecarei benzi SBR in fiecare perioada de timp (1,5 sau 3 dB pe treapta), adica
   exact energia pe care o va avea partea de sus dupa refacere. Zgomotul si armonicile se citesc numai ca sa se treaca
   peste ele. Anvelopele se leaga de la un cadru la altul (diferente in timp), deci starea se tine intre cadre. */

enum { SBR_FIXFIX = 0, SBR_FIXVAR = 1, SBR_VARFIX = 2, SBR_VARVAR = 3 };
enum { SBR_T_ENV_15 = 0, SBR_F_ENV_15, SBR_T_BAL_15, SBR_F_BAL_15, SBR_T_ENV_30, SBR_F_ENV_30, SBR_T_BAL_30,
	SBR_F_BAL_30, SBR_T_ZGOMOT_30, SBR_T_ZGOMOT_BAL_30 };

/* deplasarea benzii de start dupa esantionarea SBR: 16; 22,05; 24; 32; 44,1-64; peste 64 kHz */
static const int8_t SBR_START[6][16] = {
	{ -8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7 },
	{ -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 9, 11, 13 },
	{ -5, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 9, 11, 13, 16 },
	{ -6, -4, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 9, 11, 13, 16 },
	{ -4, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 9, 11, 13, 16, 20 },
	{ -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 9, 11, 13, 16, 20, 24 },
};
static const int SBR_LOG2_SUS[6] = { 0, 1, 2, 2, 3, 3 };
static const int SBR_ENV_MAX = 5;
static const int SBR_BENZI_MAX = 48;

struct TabeleSbr
{
	Vlc v[10];
	bool bun;

	TabeleSbr()
	{
		bun = true;
		for (int k = 0; k < 10; k++)
		{
			construiesteVlc(v[k], hdsSbrMarimi[k], hdsSbrCoduri[k], hdsSbrLungimi[k]);
			bun = bun && v[k].bun;
		}
	}
};

static const TabeleSbr &tabeleSbr()
{
	static TabeleSbr t;
	return t;
}

struct CanalSbr
{
	int numEnv, numNoise, ampRes;
	int freqRes[SBR_ENV_MAX + 2];       /* [0]: ultima a cadrului de dinainte */
	int tEnv[SBR_ENV_MAX + 2];
	int dfEnv[SBR_ENV_MAX + 1], dfNoise[3];
	int envQ[SBR_ENV_MAX + 2][SBR_BENZI_MAX + 1];   /* [0]: ultima anvelopa a cadrului de dinainte */
	int noiseQ[3][6];
};

class Sbr
{
public:
	bool tabele;
	int fs;
	int n[2], nq;
	int fHigh[65], fLow[33];
	double e[2][BENZI];         /* energia benzilor de sus in cadrul de acum, pe benzile iesirii (fs/64) */
	int canale;                 /* 1 (dupa un SCE) sau 2 (dupa un CPE); 0: nimic in cadrul de acum */

	Sbr()
	{
		reset();
	}
	void reset()
	{
		tabele = false;
		fs = 0;
		antetVazut = false;
		memset(ch, 0, sizeof(ch));
		memset(e, 0, sizeof(e));
		canale = 0;
		startFreq = stopFreq = xover = freqScale = alterScale = noiseBands = -1;
	}
	/* extensia SBR a elementului dinainte (SCE: 1 canal, CPE: 2); b e pozitionat dupa tipul extensiei */
	bool citeste(Biti &b, bool crc, int canaleElement, int fsIesire, bool l960);

private:
	bool antetVazut;
	int ampResAntet, startFreq, stopFreq, xover, freqScale, alterScale, noiseBands;
	bool coupling;
	CanalSbr ch[2];
	int slots;

	bool antet(Biti &b);
	bool faTabele();
	bool grila(Biti &b, CanalSbr &c);
	bool anvelopa(Biti &b, CanalSbr &c, int canal);
	bool zgomot(Biti &b, CanalSbr &c, int canal);
	void energie();
};

bool Sbr::antet(Biti &b)
{
	int amp = b.ia(1);
	int st = b.ia(4), sp = b.ia(4), xo = b.ia(3);
	b.ia(2);
	bool extra1 = b.ia1(), extra2 = b.ia1();
	int fsc = 2, alt = 1, nb = 2;
	if (extra1)
	{
		fsc = b.ia(2);
		alt = b.ia(1);
		nb = b.ia(2);
	}
	if (extra2)
		b.ia(6);
	if (b.rau)
		return false;
	ampResAntet = amp;
	if (st != startFreq || sp != stopFreq || xo != xover || fsc != freqScale || alt != alterScale || nb != noiseBands)
	{
		startFreq = st;
		stopFreq = sp;
		xover = xo;
		freqScale = fsc;
		alterScale = alt;
		noiseBands = nb;
		tabele = faTabele();
	}
	antetVazut = true;
	return true;
}

/* latimile a `n` benzi logaritmice intre start si stop (ca in standard, in float) */
static void benziLog(int16_t *latimi, int start, int stop, int n)
{
	float baza = powf((float)stop / start, 1.0f / n);
	float prod = start;
	int prev = start;
	for (int k = 0; k < n - 1; k++)
	{
		prod *= baza;
		int acum = (int)lrintf(prod);
		latimi[k] = acum - prev;
		prev = acum;
	}
	latimi[n - 1] = stop - prev;
}

static void sorteaza(int16_t *v, int n)
{
	for (int i = 1; i < n; i++)
	{
		int16_t x = v[i];
		int j = i - 1;
		while (j >= 0 && v[j] > x)
		{
			v[j + 1] = v[j];
			j--;
		}
		v[j + 1] = x;
	}
}

/* tabelul master si tabelele de frecvente (4.6.18.3.2); false la valori din afara standardului */
bool Sbr::faTabele()
{
	int idx;
	switch (fs)
	{
	case 16000: idx = 0; break;
	case 22050: idx = 1; break;
	case 24000: idx = 2; break;
	case 32000: idx = 3; break;
	case 44100: case 48000: case 64000: idx = 4; break;
	case 88200: case 96000: idx = 5; break;
	default: return false;
	}
	int prag = fs < 32000 ? 3000 : (fs < 64000 ? 4000 : 5000);
	int startMin = ((prag << 7) + (fs >> 1)) / fs;
	int stopMin = ((prag << 8) + (fs >> 1)) / fs;
	int k0 = startMin + SBR_START[idx][startFreq];
	int k2;
	if (stopFreq < 14)
	{
		int16_t dk[13];
		benziLog(dk, stopMin, 64, 13);
		sorteaza(dk, 13);
		k2 = stopMin;
		for (int k = 0; k < stopFreq; k++)
			k2 += dk[k];
	}
	else if (stopFreq == 14)
		k2 = 2 * k0;
	else
		k2 = 3 * k0;
	if (k2 > 64)
		k2 = 64;
	int maxQmf = fs <= 32000 ? 48 : (fs == 44100 ? 35 : 32);
	if (k0 <= 0 || k2 <= k0 || k2 - k0 > maxQmf)
		return false;
	int fMaster[65];
	int nMaster;
	if (!freqScale)
	{
		int dk = alterScale + 1;
		nMaster = ((k2 - k0 + (dk & 2)) >> dk) << 1;
		if (nMaster <= 0 || nMaster > 64 || xover >= nMaster)
			return false;
		for (int k = 1; k <= nMaster; k++)
			fMaster[k] = dk;
		int dif = k2 - k0 - nMaster * dk;
		if (dif < 0)
		{
			fMaster[1]--;
			fMaster[2] -= dif < -1;
		}
		else if (dif)
			fMaster[nMaster]++;
		fMaster[0] = k0;
		for (int k = 1; k <= nMaster; k++)
			fMaster[k] += fMaster[k - 1];
	}
	else
	{
		int jumatati = 7 - freqScale;
		bool doua = 49 * k2 > 110 * k0;
		int k1 = doua ? 2 * k0 : k2;
		int n0 = (int)lrintf(jumatati * log2f(k1 / (float)k0)) * 2;
		if (n0 <= 0 || n0 > 48)
			return false;
		int16_t vk0[49];
		benziLog(vk0 + 1, k0, k1, n0);
		sorteaza(vk0 + 1, n0);
		int vdk0max = vk0[n0];
		int acc0[49];
		acc0[0] = k0;
		for (int k = 1; k <= n0; k++)
		{
			if (vk0[k] <= 0)
				return false;
			acc0[k] = acc0[k - 1] + vk0[k];
		}
		if (doua)
		{
			float invwarp = alterScale ? 0.76923076923076923077f : 1.0f;
			int n1 = (int)lrintf(jumatati * invwarp * log2f(k2 / (float)k1)) * 2;
			if (n1 <= 0 || n1 > 48 || n0 + n1 > 64)
				return false;
			int16_t vk1[49];
			benziLog(vk1 + 1, k1, k2, n1);
			int vdk1min = vk1[1];
			for (int k = 2; k <= n1; k++)
				if (vk1[k] < vdk1min)
					vdk1min = vk1[k];
			if (vdk1min < vdk0max)
			{
				sorteaza(vk1 + 1, n1);
				int schimb = vdk0max - vk1[1];
				int alt = (vk1[n1] - vk1[1]) >> 1;
				if (alt < schimb)
					schimb = alt;
				vk1[1] += schimb;
				vk1[n1] -= schimb;
			}
			sorteaza(vk1 + 1, n1);
			int acc1[49];
			acc1[0] = k1;
			for (int k = 1; k <= n1; k++)
			{
				if (vk1[k] <= 0)
					return false;
				acc1[k] = acc1[k - 1] + vk1[k];
			}
			nMaster = n0 + n1;
			if (xover >= nMaster)
				return false;
			for (int k = 0; k <= n0; k++)
				fMaster[k] = acc0[k];
			for (int k = 1; k <= n1; k++)
				fMaster[n0 + k] = acc1[k];
		}
		else
		{
			nMaster = n0;
			if (xover >= nMaster)
				return false;
			for (int k = 0; k <= n0; k++)
				fMaster[k] = acc0[k];
		}
	}
	n[1] = nMaster - xover;
	n[0] = (n[1] + 1) >> 1;
	if (n[1] <= 0 || n[1] > SBR_BENZI_MAX)
		return false;
	for (int k = 0; k <= n[1]; k++)
		fHigh[k] = fMaster[xover + k];
	int kx = fHigh[0];
	if (kx + fHigh[n[1]] - kx > 64 || kx > 32)
		return false;
	fLow[0] = fHigh[0];
	int imp = n[1] & 1;
	for (int k = 1; k <= n[0]; k++)
		fLow[k] = fHigh[2 * k - imp];
	nq = (int)lrintf(noiseBands * log2f(k2 / (float)kx));
	if (nq < 1)
		nq = 1;
	if (nq > 5)
		return false;
	return true;
}

bool Sbr::grila(Biti &b, CanalSbr &c)
{
	c.freqRes[0] = c.freqRes[c.numEnv];
	c.ampRes = ampResAntet;
	int clasa = b.ia(2);
	int urma = slots;
	int ptr = 0;
	switch (clasa)
	{
	case SBR_FIXFIX:
	{
		int ne = 1 << b.ia(2);
		if (ne > SBR_ENV_MAX)
			return false;
		c.numEnv = ne;
		if (ne == 1)
			c.ampRes = 0;
		c.tEnv[0] = 0;
		c.tEnv[ne] = urma;
		int pas = (urma + (ne >> 1)) / ne;
		for (int i = 0; i < ne - 1; i++)
			c.tEnv[i + 1] = c.tEnv[i] + pas;
		int r = b.ia(1);
		for (int i = 1; i <= ne; i++)
			c.freqRes[i] = r;
		break;
	}
	case SBR_FIXVAR:
	{
		urma += b.ia(2);
		int nr = b.ia(2);
		c.numEnv = nr + 1;
		c.tEnv[0] = 0;
		c.tEnv[c.numEnv] = urma;
		for (int i = 0; i < nr; i++)
			c.tEnv[c.numEnv - 1 - i] = c.tEnv[c.numEnv - i] - 2 * (int)b.ia(2) - 2;
		ptr = b.ia(SBR_LOG2_SUS[c.numEnv]);
		for (int i = 0; i < c.numEnv; i++)
			c.freqRes[c.numEnv - i] = b.ia(1);
		break;
	}
	case SBR_VARFIX:
	{
		c.tEnv[0] = b.ia(2);
		int nl = b.ia(2);
		c.numEnv = nl + 1;
		c.tEnv[c.numEnv] = urma;
		for (int i = 0; i < nl; i++)
			c.tEnv[i + 1] = c.tEnv[i] + 2 * (int)b.ia(2) + 2;
		ptr = b.ia(SBR_LOG2_SUS[c.numEnv]);
		for (int i = 1; i <= c.numEnv; i++)
			c.freqRes[i] = b.ia(1);
		break;
	}
	default:
	{
		c.tEnv[0] = b.ia(2);
		urma += b.ia(2);
		int nl = b.ia(2), nr = b.ia(2);
		int ne = nl + nr + 1;
		if (ne > SBR_ENV_MAX)
			return false;
		c.numEnv = ne;
		c.tEnv[ne] = urma;
		for (int i = 0; i < nl; i++)
			c.tEnv[i + 1] = c.tEnv[i] + 2 * (int)b.ia(2) + 2;
		for (int i = 0; i < nr; i++)
			c.tEnv[ne - 1 - i] = c.tEnv[ne - i] - 2 * (int)b.ia(2) - 2;
		ptr = b.ia(SBR_LOG2_SUS[ne]);
		for (int i = 1; i <= ne; i++)
			c.freqRes[i] = b.ia(1);
		break;
	}
	}
	if (ptr > c.numEnv + 1 || b.rau)
		return false;
	for (int i = 1; i <= c.numEnv; i++)
		if (c.tEnv[i - 1] >= c.tEnv[i])
			return false;
	c.numNoise = c.numEnv > 1 ? 2 : 1;
	return true;
}

bool Sbr::anvelopa(Biti &b, CanalSbr &c, int canal)
{
	const TabeleSbr &T = tabeleSbr();
	bool bal = coupling && canal == 1;
	int delta = bal ? 2 : 1;
	int biti, tv, fv;
	if (bal)
	{
		biti = c.ampRes ? 5 : 6;
		tv = c.ampRes ? SBR_T_BAL_30 : SBR_T_BAL_15;
		fv = c.ampRes ? SBR_F_BAL_30 : SBR_F_BAL_15;
	}
	else
	{
		biti = c.ampRes ? 6 : 7;
		tv = c.ampRes ? SBR_T_ENV_30 : SBR_T_ENV_15;
		fv = c.ampRes ? SBR_F_ENV_30 : SBR_F_ENV_15;
	}
	int imp = n[1] & 1;
	for (int i = 0; i < c.numEnv; i++)
	{
		int r = c.freqRes[i + 1];
		int nb = n[r];
		if (c.dfEnv[i])
		{
			for (int j = 0; j < nb; j++)
			{
				int k;
				if (r == c.freqRes[i])
					k = j;
				else if (r)
					k = (j + imp) >> 1;
				else
					k = j ? 2 * j - imp : 0;
				int v = c.envQ[i][k] + delta * (decodeaza(b, T.v[tv]) + hdsSbrDeplasare[tv]);
				if (v < 0 || v > 127)
					return false;
				c.envQ[i + 1][j] = v;
			}
		}
		else
		{
			c.envQ[i + 1][0] = delta * (int)b.ia(biti);
			for (int j = 1; j < nb; j++)
			{
				int v = c.envQ[i + 1][j - 1] + delta * (decodeaza(b, T.v[fv]) + hdsSbrDeplasare[fv]);
				if (v < 0 || v > 127)
					return false;
				c.envQ[i + 1][j] = v;
			}
		}
		if (b.rau)
			return false;
	}
	memcpy(c.envQ[0], c.envQ[c.numEnv], sizeof(c.envQ[0]));
	return true;
}

bool Sbr::zgomot(Biti &b, CanalSbr &c, int canal)
{
	const TabeleSbr &T = tabeleSbr();
	bool bal = coupling && canal == 1;
	int delta = bal ? 2 : 1;
	int tv = bal ? SBR_T_ZGOMOT_BAL_30 : SBR_T_ZGOMOT_30;
	int fv = bal ? SBR_F_BAL_30 : SBR_F_ENV_30;
	for (int i = 0; i < c.numNoise; i++)
	{
		if (c.dfNoise[i])
		{
			for (int j = 0; j < nq; j++)
			{
				int v = c.noiseQ[i][j] + delta * (decodeaza(b, T.v[tv]) + hdsSbrDeplasare[tv]);
				if (v < 0 || v > 30)
					return false;
				c.noiseQ[i + 1][j] = v;
			}
		}
		else
		{
			c.noiseQ[i + 1][0] = delta * (int)b.ia(5);
			for (int j = 1; j < nq; j++)
			{
				int v = c.noiseQ[i + 1][j - 1] + delta * (decodeaza(b, T.v[fv]) + hdsSbrDeplasare[fv]);
				if (v < 0 || v > 30)
					return false;
				c.noiseQ[i + 1][j] = v;
			}
		}
		if (b.rau)
			return false;
	}
	memcpy(c.noiseQ[0], c.noiseQ[c.numNoise], sizeof(c.noiseQ[0]));
	return true;
}

/* 2^(q/2) pentru anvelopa la 1,5 dB (ampRes 0), 2^q la 3 dB */
static inline double putereSbr(int q, int ampRes)
{
	return ampRes ? ldexp(1.0, q) : ldexp(1.0, q >> 1) * ((q & 1) ? M_SQRT2 : 1.0);
}

/* energia pe benzile iesirii: E pe fiecare subbanda QMF a benzii SBR, cu ponderea timpului fiecarei anvelope */
void Sbr::energie()
{
	memset(e, 0, sizeof(e));
	for (int c = 0; c < canale; c++)
	{
		CanalSbr &d = ch[c];
		double total = d.tEnv[d.numEnv] - d.tEnv[0];
		if (total <= 0)
			continue;
		for (int i = 0; i < d.numEnv; i++)
		{
			double w = (d.tEnv[i + 1] - d.tEnv[i]) / total;
			int r = d.freqRes[i + 1];
			const int *tab = r ? fHigh : fLow;
			for (int j = 0; j < n[r]; j++)
			{
				double en;
				if (coupling)
				{
					int q0 = ch[0].envQ[i + 1][j], q1 = ch[1].envQ[i + 1][j];
					int pan = ch[0].ampRes ? 12 : 24;
					double t1 = putereSbr(q0, ch[0].ampRes) * 128.0;
					double t2 = putereSbr(pan - q1, ch[0].ampRes);
					double s = t1 / (1.0 + t2);
					en = c == 0 ? s : s * t2;
				}
				else
					en = putereSbr(d.envQ[i + 1][j], d.ampRes) * 64.0;
				for (int k = tab[j]; k < tab[j + 1] && k < 64; k++)
					e[c][k >> 1] += w * en;
			}
		}
	}
}

bool Sbr::citeste(Biti &b, bool crc, int canaleElement, int fsIesire, bool l960)
{
	canale = 0;
	if (!tabeleSbr().bun)
		return false;
	if (fsIesire != fs)
	{
		reset();
		fs = fsIesire;
	}
	slots = l960 ? 15 : 16;
	if (crc)
		b.ia(10);
	if (b.ia1() && !antet(b))
		return false;
	if (!antetVazut || !tabele)
		return false;
	if (canaleElement == 1)
	{
		coupling = false;
		if (b.ia1())
			b.ia(4);
		CanalSbr &c = ch[0];
		if (!grila(b, c))
			return false;
		for (int i = 0; i < c.numEnv; i++)
			c.dfEnv[i] = b.ia(1);
		for (int i = 0; i < c.numNoise; i++)
			c.dfNoise[i] = b.ia(1);
		b.sari(2 * nq);                                 /* filtrarea inversa */
		if (!anvelopa(b, c, 0))
			return false;
	}
	else
	{
		if (b.ia1())
			b.ia(8);
		coupling = b.ia1();
		if (coupling)
		{
			if (!grila(b, ch[0]))
				return false;
			/* grila celui de-al doilea canal e a primului; din cadrul de dinainte raman frecventa si anvelopa lui */
			ch[1].freqRes[0] = ch[1].freqRes[ch[1].numEnv];
			for (int i = 1; i <= SBR_ENV_MAX; i++)
				ch[1].freqRes[i] = ch[0].freqRes[i];
			memcpy(ch[1].tEnv, ch[0].tEnv, sizeof(ch[1].tEnv));
			ch[1].numEnv = ch[0].numEnv;
			ch[1].numNoise = ch[0].numNoise;
			ch[1].ampRes = ch[0].ampRes;
			for (int c = 0; c < 2; c++)
			{
				for (int i = 0; i < ch[c].numEnv; i++)
					ch[c].dfEnv[i] = b.ia(1);
				for (int i = 0; i < ch[c].numNoise; i++)
					ch[c].dfNoise[i] = b.ia(1);
			}
			b.sari(2 * nq);
			if (!anvelopa(b, ch[0], 0) || !zgomot(b, ch[0], 0) || !anvelopa(b, ch[1], 1))
				return false;
		}
		else
		{
			if (!grila(b, ch[0]) || !grila(b, ch[1]))
				return false;
			for (int c = 0; c < 2; c++)
			{
				for (int i = 0; i < ch[c].numEnv; i++)
					ch[c].dfEnv[i] = b.ia(1);
				for (int i = 0; i < ch[c].numNoise; i++)
					ch[c].dfNoise[i] = b.ia(1);
			}
			b.sari(4 * nq);
			if (!anvelopa(b, ch[0], 0) || !anvelopa(b, ch[1], 1))
				return false;
		}
	}
	if (b.rau)
		return false;
	canale = canaleElement;
	energie();
	return true;
}

/* ---------------------------------------------------------------- AAC */

static const int FRECVENTE_AAC[13] = { 96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025,
	8000, 7350 };
static const uint8_t TNS_MAX_LUNG[13] = { 31, 31, 34, 40, 42, 51, 46, 46, 42, 42, 42, 39, 39 };
static const uint8_t TNS_MAX_SCURT[13] = { 9, 9, 10, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14 };
static const int TNS_ORDIN_MAX = 20;
static const int SFB_MAX = 52;

/* indicele esantionarii pentru o frecventa data explicit (ISO/IEC 14496-3, tabelul 4.82) */
static int indiceFrecventa(int fs)
{
	static const int praguri[12] = { 92017, 75132, 55426, 46009, 37566, 27713, 23004, 18783, 13856, 11502, 9391, 0 };
	for (int i = 0; i < 12; i++)
		if (fs >= praguri[i])
			return i;
	return 11;
}

struct ConfigAac
{
	bool bun;
	int aot;            /* tipul obiectului nucleului */
	int idx;            /* indicele esantionarii nucleului, 0..12 */
	int fs;
	int fsIesire;       /* cu SBR semnalat: al sunetului auzit */
	int canale;         /* channel_configuration */
	bool l960;          /* ferestre de 960 de linii */
	bool sbr, ps;
};

struct IcsInfo
{
	int secv;
	int maxSfb;
	int nrFerestre;
	int nrGrupe;
	int lungGrup[8];
	int nrBenzi;
	const uint16_t *benzi;
	int linii;
	int tnsMax;
};

struct CanalAac
{
	IcsInfo ics;
	uint8_t cb[8][SFB_MAX];
	int sf[8][SFB_MAX];
	int nrPuls;
	int pulsPoz[4];
	int pulsAmp[4];
	int tnsNf[8];
	int tnsLung[8][4];
	int tnsOrdin[8][4];
	int tnsDir[8][4];
	float tnsLpc[8][4][TNS_ORDIN_MAX];
	bool areTns;
	int16_t q[1024];
	float spec[1024];
};

static int tipObiect(Biti &b)
{
	int t = b.ia(5);
	if (t == 31)
		t = 32 + b.ia(6);
	return t;
}

/* program_config_element: se citeste numai ca sa se treaca peste el */
static bool pce(Biti &b, uint32_t fata)
{
	b.ia(4);
	b.ia(2);
	b.ia(4);
	int nf = b.ia(4), ns = b.ia(4), nb = b.ia(4), nl = b.ia(2), na = b.ia(3), nc = b.ia(4);
	if (b.ia1())
		b.ia(4);
	if (b.ia1())
		b.ia(4);
	if (b.ia1())
		b.ia(3);
	b.sari(5 * (nf + ns + nb) + 4 * nl + 4 * na + 5 * nc);
	b.aliniaza(fata);
	int c = b.ia(8);
	b.sari(8 * c);
	return !b.rau;
}

/* AudioSpecificConfig. lungime: bitii configuratiei cand se stiu (LATM cu audioMuxVersion 1), altfel -1. */
static bool configuratie(Biti &b, ConfigAac &c, int lungime)
{
	uint32_t start = b.poz;
	memset(&c, 0, sizeof(c));
	int aot = tipObiect(b);
	int idx = b.ia(4);
	int fs = idx == 15 ? (int)b.ia(24) : (idx < 13 ? FRECVENTE_AAC[idx] : 0);
	c.canale = b.ia(4);
	c.fsIesire = fs;
	if (aot == 5 || aot == 29)
	{
		c.sbr = true;
		c.ps = aot == 29;
		int idx2 = b.ia(4);
		c.fsIesire = idx2 == 15 ? (int)b.ia(24) : (idx2 < 13 ? FRECVENTE_AAC[idx2] : fs);
		aot = tipObiect(b);
	}
	c.aot = aot;
	if (aot == 1 || aot == 2 || aot == 3 || aot == 4 || aot == 6 || aot == 7 || aot == 17 || aot == 19 || aot == 20
		|| aot == 21 || aot == 22 || aot == 23)
	{
		c.l960 = b.ia1();
		if (b.ia1())
			b.ia(14);
		bool ext = b.ia1();
		if (c.canale == 0 && !pce(b, start))
			return false;
		if (aot == 6 || aot == 20)
			b.ia(3);
		if (ext)
		{
			if (aot == 22)
			{
				b.ia(5);
				b.ia(11);
			}
			if (aot == 17 || aot == 19 || aot == 20 || aot == 23)
				b.ia(3);
			b.ia(1);
		}
	}
	else
		return false;
	/* semnalarea SBR la coada (compatibila), numai cand se stie lungimea */
	if (lungime > 0 && !c.sbr)
	{
		int folosit = (int)(b.poz - start);
		if (lungime - folosit >= 16 && b.priveste(11) == 0x2b7)
		{
			b.ia(11);
			int ext = tipObiect(b);
			if (ext == 5 && b.ia1())
			{
				c.sbr = true;
				int idx2 = b.ia(4);
				c.fsIesire = idx2 == 15 ? (int)b.ia(24) : (idx2 < 13 ? FRECVENTE_AAC[idx2] : fs);
				folosit = (int)(b.poz - start);
				if (lungime - folosit >= 12 && b.priveste(11) == 0x548)
				{
					b.ia(11);
					c.ps = b.ia1();
				}
			}
		}
	}
	if (fs <= 0)
		return false;
	c.fs = fs;
	c.idx = idx < 13 ? idx : indiceFrecventa(fs);
	c.bun = !b.rau && (aot == 1 || aot == 2 || aot == 4);
	return c.bun;
}

class Aac
{
public:
	ConfigAac cfg;
	/* LATM */
	bool latmBun;
	int lungimeCadru;       /* frameLengthType 0 */
	bool sbrGasit;
	int canaleVazute;
	bool lfeVazut;
	Sbr sbr;                /* benzile de sus ale primului element audio (HE-AAC) */
	double sbrPondere;      /* cat din energia SBR intra in fiecare parte (0,5 la centrul unui flux multicanal) */
	/* textul radio (CititorDse): elementele se citesc numai ca sa se treaca peste ele (fara cuantizare, TNS, energie,
	   SBR), iar octetii DSE se adauga in dseTampon */
	bool numaiElemente;
	uint8_t *dseTampon;
	uint32_t dseLung, dseMax;

	Aac()
	{
		numaiElemente = false;
		dseTampon = 0;
		dseLung = dseMax = 0;
		reset();
	}
	void reset()
	{
		memset(&cfg, 0, sizeof(cfg));
		latmBun = false;
		lungimeCadru = 0;
		sbrGasit = false;
		canaleVazute = 0;
		lfeVazut = false;
		sbr.reset();
		sbrPondere = 1.0;
	}
	int adts(const uint8_t *d, uint32_t n, Acum &a);
	int latm(const uint8_t *d, uint32_t n, Acum &a);
	int esantionare() const
	{
		if (cfg.sbr)
			return cfg.fsIesire;
		if (sbrGasit && cfg.fs <= 24000)
			return cfg.fs * 2;
		return cfg.fs;
	}

private:
	CanalAac can[2];
	bool bloc(Biti &b, Acum &a);
	bool icsInfo(Biti &b, IcsInfo &x);
	bool ics(Biti &b, CanalAac &c, bool comun);
	bool sectiuni(Biti &b, CanalAac &c);
	bool factori(Biti &b, CanalAac &c, int gg);
	bool tns(Biti &b, CanalAac &c);
	bool spectral(Biti &b, CanalAac &c);
	void cuantizare(CanalAac &c);
	void aplicaTns(CanalAac &c);
	void energie(const CanalAac &c, int parte, Acum &a);
	bool muxConfig(Biti &b);
};

bool Aac::icsInfo(Biti &b, IcsInfo &x)
{
	b.ia(1);
	x.secv = b.ia(2);
	b.ia(1);
	int idx = cfg.idx;
	if (x.secv == 2)
	{
		x.maxSfb = b.ia(4);
		int grupare = b.ia(7);
		x.nrFerestre = 8;
		x.nrGrupe = 1;
		x.lungGrup[0] = 1;
		for (int i = 0; i < 7; i++)
		{
			if (grupare & (1 << (6 - i)))
				x.lungGrup[x.nrGrupe - 1]++;
			else
				x.lungGrup[x.nrGrupe++] = 1;
		}
		x.benzi = cfg.l960 ? hdsAacBenzi120[idx] : hdsAacBenzi128[idx];
		x.nrBenzi = cfg.l960 ? hdsAacNrBenzi120[idx] : hdsAacNrBenzi128[idx];
		x.linii = cfg.l960 ? 120 : 128;
		x.tnsMax = TNS_MAX_SCURT[idx];
	}
	else
	{
		x.maxSfb = b.ia(6);
		x.nrFerestre = 1;
		x.nrGrupe = 1;
		x.lungGrup[0] = 1;
		x.benzi = cfg.l960 ? hdsAacBenzi960[idx] : hdsAacBenzi1024[idx];
		x.nrBenzi = cfg.l960 ? hdsAacNrBenzi960[idx] : hdsAacNrBenzi1024[idx];
		x.linii = cfg.l960 ? 960 : 1024;
		x.tnsMax = TNS_MAX_LUNG[idx];
		/* predictia (Main, LTP) schimba liniile in resturi: fara ea nivelul ar fi gresit, deci cadrul se lasa */
		if (b.ia1())
			return false;
	}
	if (x.maxSfb > x.nrBenzi || x.nrBenzi > SFB_MAX)
		return false;
	return !b.rau;
}

bool Aac::sectiuni(Biti &b, CanalAac &c)
{
	const IcsInfo &x = c.ics;
	int biti = x.nrFerestre == 8 ? 3 : 5;
	int esc = (1 << biti) - 1;
	for (int g = 0; g < x.nrGrupe; g++)
	{
		int k = 0;
		while (k < x.maxSfb)
		{
			int cb = b.ia(4);
			if (cb == 12 || b.rau)
				return false;
			int lung = 0, inc;
			do
			{
				inc = b.ia(biti);
				lung += inc;
			}
			while (inc == esc && !b.rau);
			if (lung == 0 || k + lung > x.maxSfb || b.rau)
				return false;
			for (int i = 0; i < lung; i++)
				c.cb[g][k++] = cb;
		}
	}
	return true;
}

bool Aac::factori(Biti &b, CanalAac &c, int gg)
{
	const IcsInfo &x = c.ics;
	const Vlc &v = tabele().sf;
	int sf = gg, is = 0, zg = gg - 90;
	bool primulZgomot = true;
	for (int g = 0; g < x.nrGrupe; g++)
		for (int s = 0; s < x.maxSfb; s++)
		{
			int cb = c.cb[g][s];
			if (cb == 0)
				c.sf[g][s] = 0;
			else if (cb == 14 || cb == 15)
			{
				is += decodeaza(b, v) - 60;
				c.sf[g][s] = is;
			}
			else if (cb == 13)
			{
				if (primulZgomot)
				{
					primulZgomot = false;
					zg += (int)b.ia(9) - 256;
				}
				else
					zg += decodeaza(b, v) - 60;
				c.sf[g][s] = zg;
			}
			else
			{
				sf += decodeaza(b, v) - 60;
				if (sf < 0 || sf > 255)
					return false;
				c.sf[g][s] = sf;
			}
			if (b.rau)
				return false;
		}
	return true;
}

bool Aac::tns(Biti &b, CanalAac &c)
{
	const IcsInfo &x = c.ics;
	bool scurt = x.nrFerestre == 8;
	c.areTns = true;
	for (int w = 0; w < x.nrFerestre; w++)
	{
		int nf = b.ia(scurt ? 1 : 2);
		c.tnsNf[w] = nf;
		if (!nf)
			continue;
		int rez = b.ia(1) + 3;
		for (int f = 0; f < nf; f++)
		{
			c.tnsLung[w][f] = b.ia(scurt ? 4 : 6);
			int ordin = b.ia(scurt ? 3 : 5);
			if (ordin > TNS_ORDIN_MAX)
				return false;
			c.tnsOrdin[w][f] = ordin;
			if (!ordin)
				continue;
			c.tnsDir[w][f] = b.ia(1);
			int biti = rez - b.ia(1);
			float parcor[TNS_ORDIN_MAX];
			double iq = ((1 << (rez - 1)) - 0.5) / (M_PI / 2.0);
			double iqm = ((1 << (rez - 1)) + 0.5) / (M_PI / 2.0);
			for (int i = 0; i < ordin; i++)
			{
				int v = b.ia(biti);
				if (v >= (1 << (biti - 1)))
					v -= 1 << biti;
				parcor[i] = (float)sin(v / (v >= 0 ? iq : iqm));
			}
			/* din coeficientii de reflexie in cei ai filtrului (recurenta Levinson) */
			float *lpc = c.tnsLpc[w][f];
			float tmp[TNS_ORDIN_MAX];
			for (int m = 0; m < ordin; m++)
			{
				float r = parcor[m];
				for (int i = 0; i < m; i++)
					tmp[i] = lpc[i] + r * lpc[m - 1 - i];
				for (int i = 0; i < m; i++)
					lpc[i] = tmp[i];
				lpc[m] = r;
			}
		}
	}
	return !b.rau;
}

static inline int escape(Biti &b)
{
	int n = 0;
	while (b.ia1())
	{
		if (++n > 8)
		{
			b.rau = true;
			return 0;
		}
	}
	return (1 << (n + 4)) + (int)b.ia(n + 4);
}

bool Aac::spectral(Biti &b, CanalAac &c)
{
	const IcsInfo &x = c.ics;
	const Tabele &T = tabele();
	memset(c.q, 0, sizeof(c.q));
	int w0 = 0;
	for (int g = 0; g < x.nrGrupe; g++)
	{
		for (int s = 0; s < x.maxSfb; s++)
		{
			int cb = c.cb[g][s];
			if (cb == 0 || cb > 11)
				continue;
			const Vlc &v = T.spectru[cb - 1];
			int start = x.benzi[s];
			int lat = x.benzi[s + 1] - start;
			for (int w = w0; w < w0 + x.lungGrup[g]; w++)
			{
				int16_t *q = c.q + w * x.linii + start;
				if (cb <= 4)
				{
					for (int k = 0; k < lat; k += 4)
					{
						int idx = decodeaza(b, v);
						int val[4] = { idx / 27, (idx / 9) % 3, (idx / 3) % 3, idx % 3 };
						for (int j = 0; j < 4; j++)
						{
							if (cb <= 2)
								val[j] -= 1;
							else if (val[j] && b.ia1())
								val[j] = -val[j];
							q[k + j] = val[j];
						}
					}
				}
				else
				{
					int mod = cb <= 6 ? 9 : (cb <= 8 ? 8 : (cb <= 10 ? 13 : 17));
					for (int k = 0; k < lat; k += 2)
					{
						int idx = decodeaza(b, v);
						int y = idx / mod, z = idx % mod;
						if (cb <= 6)
						{
							y -= 4;
							z -= 4;
						}
						else
						{
							bool ny = y && b.ia1();
							bool nz = z && b.ia1();
							if (cb == 11)
							{
								if (y == 16)
									y = escape(b);
								if (z == 16)
									z = escape(b);
							}
							if (ny)
								y = -y;
							if (nz)
								z = -z;
						}
						q[k] = y;
						q[k + 1] = z;
					}
				}
				if (b.rau)
					return false;
			}
		}
		w0 += x.lungGrup[g];
	}
	return true;
}

bool Aac::ics(Biti &b, CanalAac &c, bool comun)
{
	int gg = b.ia(8);
	if (!comun && !icsInfo(b, c.ics))
		return false;
	if (!sectiuni(b, c) || !factori(b, c, gg))
		return false;
	c.nrPuls = 0;
	if (b.ia1())
	{
		if (c.ics.nrFerestre == 8)
			return false;
		c.nrPuls = b.ia(2) + 1;
		int s = b.ia(6);
		if (s >= c.ics.nrBenzi)
			return false;
		int poz = c.ics.benzi[s];
		for (int i = 0; i < c.nrPuls; i++)
		{
			poz += b.ia(5);
			c.pulsPoz[i] = poz;
			c.pulsAmp[i] = b.ia(4);
		}
		if (poz >= c.ics.linii)
			return false;
	}
	c.areTns = false;
	if (b.ia1() && !tns(b, c))
		return false;
	if (b.ia1())            /* controlul castigului: numai profilul SSR */
		return false;
	if (!spectral(b, c))
		return false;
	for (int i = 0; i < c.nrPuls; i++)
	{
		int16_t &v = c.q[c.pulsPoz[i]];
		if (v > 0)
			v += c.pulsAmp[i];
		else
			v -= c.pulsAmp[i];
	}
	if (!numaiElemente)
		cuantizare(c);
	return !b.rau;
}

void Aac::cuantizare(CanalAac &c)
{
	const IcsInfo &x = c.ics;
	const Tabele &T = tabele();
	memset(c.spec, 0, sizeof(c.spec));
	int w0 = 0;
	for (int g = 0; g < x.nrGrupe; g++)
	{
		for (int s = 0; s < x.maxSfb; s++)
		{
			int cb = c.cb[g][s];
			if (cb == 0 || cb > 11)
				continue;
			float gain = T.castig[c.sf[g][s]];
			for (int w = w0; w < w0 + x.lungGrup[g]; w++)
			{
				int o = w * x.linii;
				for (int k = x.benzi[s]; k < x.benzi[s + 1]; k++)
				{
					int v = c.q[o + k];
					int a = v < 0 ? -v : v;
					if (a >= PUTERE_MAX)
						a = PUTERE_MAX - 1;
					float m = T.putere43[a] * gain;
					c.spec[o + k] = v < 0 ? -m : m;
				}
			}
		}
		w0 += x.lungGrup[g];
	}
}

void Aac::aplicaTns(CanalAac &c)
{
	if (!c.areTns)
		return;
	const IcsInfo &x = c.ics;
	int limita = x.tnsMax < x.maxSfb ? x.tnsMax : x.maxSfb;
	for (int w = 0; w < x.nrFerestre; w++)
	{
		int jos = x.nrBenzi;
		for (int f = 0; f < c.tnsNf[w]; f++)
		{
			int sus = jos;
			jos = sus - c.tnsLung[w][f];
			if (jos < 0)
				jos = 0;
			int ordin = c.tnsOrdin[w][f];
			if (!ordin)
				continue;
			int a = x.benzi[jos < limita ? jos : limita];
			int z = x.benzi[sus < limita ? sus : limita];
			int n = z - a;
			if (n <= 0)
				continue;
			float *s = c.spec + w * x.linii;
			int pas = 1, p = a;
			if (c.tnsDir[w][f])
			{
				pas = -1;
				p = z - 1;
			}
			const float *lpc = c.tnsLpc[w][f];
			for (int m = 0; m < n; m++, p += pas)
			{
				float v = s[p];
				int cate = m < ordin ? m : ordin;
				for (int i = 1; i <= cate; i++)
					v -= lpc[i - 1] * s[p - i * pas];
				s[p] = v;
			}
		}
	}
}

/* Energia liniilor unui canal (si a benzilor de zgomot PNS) spre partea data. Fereastra scurta: suma pe cele 8
   ferestre inmultita cu 8 (liniile ferestrei scurte au, pentru acelasi semnal, a opta parte din energia celor
   lungi). */
void Aac::energie(const CanalAac &c, int parte, Acum &a)
{
	const IcsInfo &x = c.ics;
	double f = x.nrFerestre == 8 ? 8.0 : 1.0;
	int sfarsit = x.benzi[x.maxSfb];
	for (int w = 0; w < x.nrFerestre; w++)
	{
		const float *s = c.spec + w * x.linii;
		for (int k = 0; k < sfarsit; k++)
		{
			float v = s[k];
			if (v != 0.0f)
				a.adauga(parte, k, x.linii, f * (double)v * v);
		}
	}
	int w0 = 0;
	for (int g = 0; g < x.nrGrupe; g++)
	{
		for (int s = 0; s < x.maxSfb; s++)
		{
			if (c.cb[g][s] != 13)
				continue;
			int lat = x.benzi[s + 1] - x.benzi[s];
			if (lat <= 0)
				continue;
			int v = c.sf[g][s];
			if (v > 400)
				v = 400;
			if (v < -400)
				v = -400;
			double en = f * pow(2.0, 0.5 * v) * x.lungGrup[g] / lat;
			for (int k = x.benzi[s]; k < x.benzi[s + 1]; k++)
				a.adauga(parte, k, x.linii, en);
		}
		w0 += x.lungGrup[g];
	}
}

/* raw_data_block: elementele pana la END. CCE sau un element necunoscut opreste citirea, cu ce s-a strans pana
   atunci. */
bool Aac::bloc(Biti &b, Acum &a)
{
	uint32_t fata = 0;
	int sce = 0, cpe = 0;
	int ultimul = 0;            /* canalele ultimului element audio (1 SCE, 2 CPE), pentru extensia SBR de dupa el */
	bool sbrCitit = false;
	sbr.canale = 0;
	Acum centru;
	centru.goleste();
	Acum fata2;
	fata2.goleste();
	for (int elemente = 0; elemente < 64; elemente++)
	{
		if (b.rau)
			return false;
		int id = b.ia(3);
		if (id == 7)
			break;
		switch (id)
		{
		case 0:         /* SCE */
		case 3:         /* LFE */
		{
			b.ia(4);
			if (!ics(b, can[0], false))
				return false;
			if (!numaiElemente)
				aplicaTns(can[0]);
			if (id == 0)
			{
				if (!numaiElemente)
					energie(can[0], AMBELE, centru);
				sce++;
				ultimul = sce + cpe == 1 ? 1 : 0;
			}
			else
			{
				lfeVazut = true;
				ultimul = 0;
			}
			break;
		}
		case 1:         /* CPE */
		{
			b.ia(4);
			bool comun = b.ia1();
			int ms = 0;
			uint8_t folosit[8][SFB_MAX];
			memset(folosit, 0, sizeof(folosit));
			if (comun)
			{
				if (!icsInfo(b, can[0].ics))
					return false;
				can[1].ics = can[0].ics;
				ms = b.ia(2);
				if (ms == 3)
					return false;
				if (ms == 1)
				{
					for (int g = 0; g < can[0].ics.nrGrupe; g++)
						for (int s = 0; s < can[0].ics.maxSfb; s++)
							folosit[g][s] = b.ia(1);
				}
				else if (ms == 2)
					memset(folosit, 1, sizeof(folosit));
			}
			if (!ics(b, can[0], comun) || !ics(b, can[1], comun))
				return false;
			if (numaiElemente)
			{
				cpe++;
				ultimul = sce + cpe == 1 ? 2 : 0;
				break;
			}
			if (comun)
			{
				const IcsInfo &x = can[0].ics;
				int w0 = 0;
				for (int g = 0; g < x.nrGrupe; g++)
				{
					for (int s = 0; s < x.maxSfb; s++)
					{
						int cb0 = can[0].cb[g][s], cb1 = can[1].cb[g][s];
						if (cb1 == 14 || cb1 == 15)
						{
							/* stereo de intensitate: dreapta = stanga * 2^(-is/4), cu semn */
							int is = can[1].sf[g][s];
							if (is > 400)
								is = 400;
							if (is < -400)
								is = -400;
							float sc = (float)pow(2.0, -0.25 * is);
							if ((cb1 == 14) != (ms && folosit[g][s]))
								sc = -sc;
							for (int w = w0; w < w0 + x.lungGrup[g]; w++)
								for (int k = x.benzi[s]; k < x.benzi[s + 1]; k++)
									can[1].spec[w * x.linii + k] = can[0].spec[w * x.linii + k] * sc;
						}
						else if (ms && folosit[g][s] && cb0 <= 11 && cb1 <= 11)
						{
							for (int w = w0; w < w0 + x.lungGrup[g]; w++)
								for (int k = x.benzi[s]; k < x.benzi[s + 1]; k++)
								{
									float m = can[0].spec[w * x.linii + k], d = can[1].spec[w * x.linii + k];
									can[0].spec[w * x.linii + k] = m + d;
									can[1].spec[w * x.linii + k] = m - d;
								}
						}
					}
					w0 += x.lungGrup[g];
				}
			}
			aplicaTns(can[0]);
			aplicaTns(can[1]);
			if (cpe == 0)
			{
				energie(can[0], STANGA, fata2);
				energie(can[1], DREAPTA, fata2);
			}
			else
			{
				/* al doilea element stereo (spatele): la jumatate de putere */
				Acum spate;
				spate.goleste();
				energie(can[0], STANGA, spate);
				energie(can[1], DREAPTA, spate);
				for (int p = 0; p < 2; p++)
					for (int k = 0; k < BENZI; k++)
						fata2.e[p][k] += 0.5 * spate.e[p][k];
			}
			cpe++;
			ultimul = sce + cpe == 1 ? 2 : 0;
			break;
		}
		case 4:         /* DSE */
		{
			b.ia(4);
			bool alin = b.ia1();
			int n = b.ia(8);
			if (n == 255)
				n += b.ia(8);
			if (alin)
				b.aliniaza(fata);
			if (dseTampon && n > 0 && b.ramase() >= 8u * n)
			{
				/* textul radio (UECP) al postului, cand il pune aici: octetii in ordinea lor */
				for (int k = 0; k < n; k++)
				{
					uint32_t v = b.ia(8);
					if (dseLung < dseMax)
						dseTampon[dseLung++] = (uint8_t)v;
				}
			}
			else
				b.sari(8 * n);
			break;
		}
		case 5:         /* PCE */
			if (!pce(b, fata))
				return false;
			break;
		case 6:         /* FIL */
		{
			int n = b.ia(4);
			if (n == 15)
				n += (int)b.ia(8) - 1;
			if (n > 0)
			{
				int tip = b.priveste(4);
				if (tip == 13 || tip == 14)
				{
					sbrGasit = true;
					/* SBR-ul primului element audio: benzile de sus */
					int fsSbr = cfg.sbr ? cfg.fsIesire : 2 * cfg.fs;
					if (ultimul && !sbrCitit && fsSbr == 2 * cfg.fs && !numaiElemente)
					{
						Biti p = b;
						p.sf = p.poz + 8 * n < p.sf ? p.poz + 8 * n : p.sf;
						p.ia(4);
						if (!sbr.citeste(p, tip == 14, ultimul, fsSbr, cfg.l960))
							sbr.canale = 0;
						sbrCitit = true;
					}
				}
				b.sari(8 * n);
			}
			ultimul = 0;
			break;
		}
		default:        /* CCE: nu apare in emisie; ce s-a strans ramane */
			elemente = 64;
			break;
		}
	}
	if (b.rau && sce + cpe == 0)
		return false;
	if (sce + cpe == 0)
		return false;
	/* un singur canal: mono. Altfel centrul (si al doilea centru) la jumatate de putere in fiecare parte. */
	double fc = (sce == 1 && cpe == 0) ? 1.0 : 0.5;
	for (int p = 0; p < 2; p++)
		for (int k = 0; k < BENZI; k++)
			a.e[p][k] += fata2.e[p][k] + fc * centru.e[p][k];
	a.sce = sce;
	a.cpe = cpe;
	canaleVazute = sce + 2 * cpe;
	sbrPondere = (sce == 1 && cpe == 0) || sbr.canale == 2 ? 1.0 : 0.5;
	return true;
}

int Aac::adts(const uint8_t *d, uint32_t n, Acum &a)
{
	if (n < 7 || d[0] != 0xFF || (d[1] & 0xF6) != 0xF0)
		return 0;
	bool faraCrc = d[1] & 1;
	int profil = (d[2] >> 6) + 1;
	int idx = (d[2] >> 2) & 15;
	int canale = ((d[2] & 1) << 2) | (d[3] >> 6);
	int lung = ((d[3] & 3) << 11) | (d[4] << 3) | (d[5] >> 5);
	int blocuri = (d[6] & 3) + 1;
	if (idx > 12 || lung < 7 || (uint32_t)lung > n)
		return 0;
	if (cfg.idx != idx || cfg.aot != profil || cfg.canale != canale || !cfg.bun)
	{
		memset(&cfg, 0, sizeof(cfg));
		cfg.aot = profil;
		cfg.idx = idx;
		cfg.fs = FRECVENTE_AAC[idx];
		cfg.fsIesire = cfg.fs;
		cfg.canale = canale;
		cfg.bun = profil == 1 || profil == 2 || profil == 4;
	}
	if (!cfg.bun)
		return 0;
	uint32_t antet = 7;
	if (!faraCrc)
		antet += 2 * blocuri;       /* pozitiile blocurilor (cand sunt mai multe) si CRC-ul */
	if (antet >= (uint32_t)lung)
		return 0;
	Biti b;
	b.init(d + antet, lung - antet);
	return bloc(b, a) ? 1 : 0;
}

static int valoareLatm(Biti &b)
{
	int cati = b.ia(2);
	int v = 0;
	for (int i = 0; i <= cati; i++)
		v = (v << 8) | b.ia(8);
	return v;
}

bool Aac::muxConfig(Biti &b)
{
	latmBun = false;
	int versiune = b.ia(1);
	if (versiune && b.ia1())        /* audioMuxVersionA: nu se foloseste in emisie */
		return false;
	if (versiune)
		valoareLatm(b);
	b.ia(1);                        /* allStreamsSameTimeFraming */
	b.ia(6);                        /* numSubFrames */
	if (b.ia(4))                    /* numProgram: numai un program */
		return false;
	if (b.ia(3))                    /* numLayer: numai un strat */
		return false;
	ConfigAac c;
	if (!versiune)
	{
		if (!configuratie(b, c, -1))
			return false;
	}
	else
	{
		int lung = valoareLatm(b);
		uint32_t p0 = b.poz;
		if (!configuratie(b, c, lung))
			return false;
		int folosit = (int)(b.poz - p0);
		if (folosit > lung)
			return false;
		b.sari(lung - folosit);
	}
	int tip = b.ia(3);
	if (tip == 0)
		b.ia(8);
	else
		return false;               /* lungime fixa, CELP, HVXC: nu in emisie */
	if (b.ia1())
	{
		if (versiune)
			valoareLatm(b);
		else
		{
			int esc;
			do
			{
				esc = b.ia(1);
				b.ia(8);
			}
			while (esc && !b.rau);
		}
	}
	if (b.ia1())
		b.ia(8);
	if (b.rau)
		return false;
	if (c.idx != cfg.idx || c.aot != cfg.aot || c.fs != cfg.fs)
		sbrGasit = false;
	cfg = c;
	latmBun = true;
	return true;
}

int Aac::latm(const uint8_t *d, uint32_t n, Acum &a)
{
	if (n < 4 || d[0] != 0x56 || (d[1] & 0xE0) != 0xE0)
		return 0;
	uint32_t lung = (((uint32_t)d[1] & 0x1F) << 8) | d[2];
	if (lung + 3 > n)
		return 0;
	Biti b;
	b.init(d + 3, lung);
	if (!b.ia1())
	{
		if (!muxConfig(b))
			return 0;
	}
	if (!latmBun)
		return 0;
	/* PayloadLengthInfo (frameLengthType 0) pentru primul subcadru */
	uint32_t octeti = 0;
	int t;
	do
	{
		t = b.ia(8);
		octeti += t;
	}
	while (t == 255 && !b.rau);
	if (b.rau || octeti * 8 > b.ramase())
		return 0;
	Biti p = b;
	p.sf = p.poz + octeti * 8;
	return bloc(p, a) ? 1 : 0;
}

/* ---------------------------------------------------------------- AC-3 si E-AC-3 */

/* Toate blocurile cadrului (6 la AC-3), fiecare cu exponentii si mantisele lui: ca sa se ajunga la blocul urmator
   trebuie trecut peste mantisele celui de acum, iar lungimea lor iese numai din alocarea bitilor (A/52, 7.2), care se
   calculeaza aici la fel ca in decodor. Cu mantisele citite, liniile au marimea lor adevarata (mantisa * 2^-exponent).
   Nivelul unei benzi pe cadru e cel mai mare dintre blocuri (un sunet scurt dintr-un singur bloc se vede).
   Unde mantisele nu se pot citi (E-AC-3 cu AHT sau cu esantionarea redusa), numai exponentii blocului 0. */

static const int AC3_CANALE[8] = { 2, 1, 2, 3, 3, 4, 4, 5 };
/* partea fiecarui canal fbw, in ordinea din flux: 1+1, C, L R, L C R, L R S, L C R S, L R Ls Rs, L C R Ls Rs */
static const uint8_t AC3_PARTE[8][5] = {
	{ STANGA, DREAPTA }, { AMBELE }, { STANGA, DREAPTA }, { STANGA, CENTRU, DREAPTA }, { STANGA, DREAPTA, CENTRU },
	{ STANGA, CENTRU, DREAPTA, CENTRU }, { STANGA, DREAPTA, STANGA, DREAPTA },
	{ STANGA, CENTRU, DREAPTA, STANGA, DREAPTA },
};
/* canalele din spate (se aduna la jumatate de putere) */
static const uint8_t AC3_SPATE[8][5] = {
	{ 0, 0 }, { 0 }, { 0, 0 }, { 0, 0, 0 }, { 0, 0, 1 }, { 0, 0, 0, 1 }, { 0, 0, 1, 1 }, { 0, 0, 0, 1, 1 },
};
static const int REMATRICE[5] = { 13, 25, 37, 61, 253 };
static const uint8_t CPL_IMPLICIT[18] = { 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1 };
static const uint8_t SPX_IMPLICIT[17] = { 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1 };
/* energia medie a unei linii fara biti cu zgomot (dither): mantisa uniforma in +-0,707 */
static const double ENERGIE_ZGOMOT = 0.1667;
/* numai exponenti (fara mantise): energia medie a mantisei fata de 2^-2e, masurata pe muzica (calibreaza.py) */
static const double ENERGIE_FARA_MANTISE = 0.30;

enum { CPL_CH = 0, DBA_REUTILIZARE = 0, DBA_NOU = 1, DBA_FARA = 2 };

struct StareAc3
{
	/* din antet si din audfrm */
	bool eac3;
	int acmod, nfch, lfeon, lfeCh, nch, nblk, srShift, fscod;
	bool blkswe, dithflage, bamode, fgainSintaxa, dbaSintaxa, skipSintaxa, convertor;
	int snrStrat;
	int cplStre[6], cplInu[6];
	int strat[6][7];
	bool aht;
	/* ce trece de la un bloc la altul */
	bool dither[7];
	bool blksw[7];
	int cplinu;
	bool inCpl[7];
	int cplStart, cplEnd, nCpl;
	uint8_t cplStruct[18];
	uint8_t cplMarimi[22];
	bool fazaFolosita;
	double cplCo[7][22];
	bool primeleCoCpl[7];
	bool spxinu;
	bool inSpx[7];
	int spxStart, spxEnd, nSpx;
	uint8_t spxStruct[17];
	uint8_t spxMarimi[22];
	double spxCo[7][22];
	bool primeleCoSpx[7];
	int nRem;
	bool rem[4];
	int start[7], end[7], grupe[7];
	uint8_t exps[7][256];
	int sdecay, fdecay, sgain, dbknee, podea;
	int fgain[7], snr[7];
	int cplFleak, cplSleak;
	bool primulLeak;
	int dbaMod[7], dbaSeg[7];
	uint8_t dbaOff[7][8], dbaLung[7][8], dbaVal[7][8];
	int16_t psd[7][256];
	int16_t bandPsd[7][50];
	int16_t masca[7][50];
	uint8_t bap[7][256];
	float coef[7][256];
};

/* exponentii grupati: 7 biti pe trei diferente; str 1..3 = D15, D25, D45 */
static bool exponenti(Biti &b, int str, int grupe, int abs, uint8_t *dest, int loc)
{
	int prev = abs;
	int dim = 1 << (str - 1);
	int j = 0;
	for (int i = 0; i < grupe; i++)
	{
		int g = b.ia(7);
		if (g >= 125 || b.rau)
			return false;
		int dd[3] = { g / 25, (g % 25) / 5, g % 5 };
		for (int k = 0; k < 3; k++)
		{
			prev += dd[k] - 2;
			if (prev < 0 || prev > 24)
				return false;
			for (int r = 0; r < dim; r++)
				if (j < loc)
					dest[j++] = prev;
		}
	}
	return true;
}

/* structura benzilor (cuplaj, extensie) din subbenzi de 12 linii. `st`: structura tinuta de la un bloc la altul
   (indicele = subbanda), pusa pe cea implicita in blocul 0. -> numarul benzilor, 0 la eroare. */
static int structura(Biti &b, bool citeste, int blk, int sub0, int sub1, const uint8_t *implicit, int lung,
	uint8_t *st, uint8_t *marimi)
{
	int n = sub1 - sub0;
	if (n <= 0 || n > 22 || sub1 > lung)
		return 0;
	if (!blk)
		memcpy(st, implicit, lung);
	if (citeste)
		for (int i = 1; i < n; i++)
			st[sub0 + i] = b.ia(1);
	int nb = 0;
	marimi[0] = 12;
	for (int i = 1; i < n; i++)
	{
		if (st[sub0 + i])
			marimi[nb] += 12;
		else
			marimi[++nb] = 12;
	}
	return nb + 1;
}

/* ---- alocarea bitilor (A/52, 7.2.2) */

static void psdBenzi(const uint8_t *exps, int start, int end, int16_t *psd, int16_t *bandPsd)
{
	for (int k = start; k < end; k++)
		psd[k] = 3072 - (exps[k] << 7);
	int k = start;
	int banda = hdsAc3BandaLiniei[start];
	do
	{
		int v = psd[k++];
		int sf = hdsAc3InceputBanda[banda + 1] < end ? hdsAc3InceputBanda[banda + 1] : end;
		for (; k < sf; k++)
		{
			int mx = v > psd[k] ? v : psd[k];
			int adr = mx - ((v + psd[k] + 1) >> 1);
			if (adr > 255)
				adr = 255;
			v = mx + hdsAc3AdunareLog[adr];
		}
		bandPsd[banda++] = v;
	}
	while (banda < 50 && end > hdsAc3InceputBanda[banda]);
}

static inline int compensareJos1(int a, int b0, int b1, int c)
{
	if (b0 + 256 == b1)
		return c;
	if (b0 > b1)
		return a - 64 > 0 ? a - 64 : 0;
	return a;
}

static inline int compensareJos(int a, int b0, int b1, int banda)
{
	if (banda < 7)
		return compensareJos1(a, b0, b1, 384);
	if (banda < 20)
		return compensareJos1(a, b0, b1, 320);
	return a - 128 > 0 ? a - 128 : 0;
}

static inline int maxim(int a, int b)
{
	return a > b ? a : b;
}

static bool mascaAc3(const StareAc3 &s, int ch, int start, int end, int16_t *masca)
{
	const int16_t *bp = s.bandPsd[ch];
	int ex[50];
	bool lfe = ch == s.lfeCh;
	int fg = s.fgain[ch];
	if (end <= 0 || end > 253)
		return false;
	int b0 = hdsAc3BandaLiniei[start];
	int b1 = hdsAc3BandaLiniei[end - 1] + 1;
	int inceput, rapid = 0, lent = 0;
	if (b0 == 0)
	{
		int jos = 0;
		jos = compensareJos1(jos, bp[0], bp[1], 384);
		ex[0] = bp[0] - fg - jos;
		jos = compensareJos1(jos, bp[1], bp[2], 384);
		ex[1] = bp[1] - fg - jos;
		inceput = 7;
		for (int b = 2; b < 7; b++)
		{
			if (!(lfe && b == 6))
				jos = compensareJos1(jos, bp[b], bp[b + 1], 384);
			rapid = bp[b] - fg;
			lent = bp[b] - s.sgain;
			ex[b] = rapid - jos;
			if (!(lfe && b == 6) && bp[b] <= bp[b + 1])
			{
				inceput = b + 1;
				break;
			}
		}
		int sf1 = b1 < 22 ? b1 : 22;
		for (int b = inceput; b < sf1; b++)
		{
			if (!(lfe && b == 6))
				jos = compensareJos(jos, bp[b], bp[b + 1], b);
			rapid = maxim(rapid - s.fdecay, bp[b] - fg);
			lent = maxim(lent - s.sdecay, bp[b] - s.sgain);
			ex[b] = maxim(rapid - jos, lent);
		}
		inceput = 22;
	}
	else
	{
		inceput = b0;
		rapid = (s.cplFleak << 8) + 768;
		lent = (s.cplSleak << 8) + 768;
	}
	for (int b = inceput; b < b1; b++)
	{
		rapid = maxim(rapid - s.fdecay, bp[b] - fg);
		lent = maxim(lent - s.sdecay, bp[b] - s.sgain);
		ex[b] = maxim(rapid, lent);
	}
	for (int b = b0; b < b1; b++)
	{
		int t = s.dbknee - bp[b];
		if (t > 0)
			ex[b] += t >> 2;
		int prag = hdsAc3PragAuz[(b >> s.srShift) * 3 + s.fscod];
		masca[b] = maxim(prag, ex[b]);
	}
	int mod = s.dbaMod[ch];
	if (mod == DBA_REUTILIZARE || mod == DBA_NOU)
	{
		int b = b0;
		for (int seg = 0; seg < s.dbaSeg[ch]; seg++)
		{
			b += s.dbaOff[ch][seg];
			if (b >= 50 || s.dbaLung[ch][seg] > 50 - b)
				return false;
			int v = s.dbaVal[ch][seg];
			int delta = (v >= 4 ? v - 3 : v - 4) * 128;
			for (int i = 0; i < s.dbaLung[ch][seg]; i++)
				masca[b++] += delta;
		}
	}
	return true;
}

static void trepteAc3(const int16_t *masca, const int16_t *psd, int start, int end, int snr, int podea, uint8_t *bap)
{
	if (snr == -960)
	{
		memset(bap + start, 0, end - start);
		return;
	}
	int k = start;
	int banda = hdsAc3BandaLiniei[start];
	int sf;
	do
	{
		int m = (maxim(masca[banda] - snr - podea, 0) & 0x1FE0) + podea;
		sf = hdsAc3InceputBanda[++banda];
		if (sf > end)
			sf = end;
		for (; k < sf; k++)
		{
			int adr = (psd[k] - m) >> 5;
			if (adr < 0)
				adr = 0;
			if (adr > 63)
				adr = 63;
			bap[k] = hdsAc3Treapta[adr];
		}
	}
	while (end > sf && banda < 50);
}

/* ---- mantisele */

struct Grupe
{
	int b1, b2, b4;
	float m1[2], m2[2], m4;
};

static inline float simetric(int cod, int nivele)
{
	return (float)(2 * cod - (nivele - 1)) / nivele;
}

static bool mantise(Biti &b, StareAc3 &s, int ch, int start, int end, Grupe &g)
{
	const uint8_t *bap = s.bap[ch];
	float *c = s.coef[ch];
	bool zgomot = ch == CPL_CH || s.dither[ch];
	for (int k = start; k < end; k++)
	{
		float m;
		switch (bap[k])
		{
		case 0:
			m = zgomot ? -1.0f : 0.0f;          /* se socoteste mai jos cu energia medie a zgomotului */
			break;
		case 1:
			if (g.b1)
				m = g.m1[--g.b1];
			else
			{
				int v = b.ia(5);
				if (v >= 27)
					return false;
				m = simetric(v / 9, 3);
				g.m1[1] = simetric((v % 9) / 3, 3);
				g.m1[0] = simetric(v % 3, 3);
				g.b1 = 2;
			}
			break;
		case 2:
			if (g.b2)
				m = g.m2[--g.b2];
			else
			{
				int v = b.ia(7);
				if (v >= 125)
					return false;
				m = simetric(v / 25, 5);
				g.m2[1] = simetric((v % 25) / 5, 5);
				g.m2[0] = simetric(v % 5, 5);
				g.b2 = 2;
			}
			break;
		case 3:
		{
			int v = b.ia(3);
			if (v >= 7)
				return false;
			m = simetric(v, 7);
			break;
		}
		case 4:
			if (g.b4)
			{
				g.b4 = 0;
				m = g.m4;
			}
			else
			{
				int v = b.ia(7);
				if (v >= 121)
					return false;
				m = simetric(v / 11, 11);
				g.m4 = simetric(v % 11, 11);
				g.b4 = 1;
			}
			break;
		case 5:
		{
			int v = b.ia(4);
			if (v >= 15)
				return false;
			m = simetric(v, 15);
			break;
		}
		default:
		{
			int q = hdsAc3Cuantizare[bap[k]];
			int v = b.ia(q);
			if (v >= (1 << (q - 1)))
				v -= 1 << q;
			m = (float)v / (float)(1 << (q - 1));
			break;
		}
		}
		c[k] = m;
	}
	return !b.rau;
}

/* 2^(-2e) pentru exponentii 0..24 */
struct PutereExp
{
	double v[25];
	PutereExp()
	{
		for (int e = 0; e < 25; e++)
			v[e] = ldexp(1.0, -2 * e);
	}
};

static inline double putereExp(int e)
{
	static const PutereExp t;
	return t.v[e < 0 ? 0 : (e > 24 ? 24 : e)];
}

/* energia liniei k a canalului ch, dupa exponent si mantisa (-1 = linie fara biti, cu zgomot) */
static inline double energieLinie(const StareAc3 &s, int ch, int k)
{
	float m = s.coef[ch][k];
	double e = putereExp(s.exps[ch][k]);
	if (m == -1.0f)
		return e * ENERGIE_ZGOMOT;
	return e * (double)m * m;
}

/* ---- blocurile */

static bool strategieCuplaj(Biti &b, StareAc3 &s, int blk)
{
	if (!s.eac3)
		s.cplinu = b.ia(1);
	if (s.cplinu)
	{
		if (s.acmod < 2)
			return false;
		if (s.eac3 && b.ia1())      /* cuplajul imbunatatit: nu se foloseste in emisie */
			return false;
		if (s.eac3 && s.acmod == 2)
			s.inCpl[1] = s.inCpl[2] = true;
		else
			for (int ch = 1; ch <= s.nfch; ch++)
				s.inCpl[ch] = b.ia1();
		if (s.acmod == 2)
			s.fazaFolosita = b.ia1();
		int s0 = b.ia(4);
		int s1 = s.spxinu ? (s.spxStart - 37) / 12 : (int)b.ia(4) + 3;
		if (s0 >= s1)
			return false;
		s.cplStart = s0 * 12 + 37;
		s.cplEnd = s1 * 12 + 37;
		s.nCpl = structura(b, !s.eac3 || b.ia1(), blk, s0, s1, CPL_IMPLICIT, 18, s.cplStruct, s.cplMarimi);
		if (!s.nCpl)
			return false;
	}
	else
	{
		for (int ch = 1; ch <= s.nfch; ch++)
		{
			s.inCpl[ch] = false;
			s.primeleCoCpl[ch] = true;
		}
		s.primulLeak = s.eac3;
		s.fazaFolosita = false;
	}
	return true;
}

/* Un bloc audio: campurile, exponentii, alocarea, mantisele; energia lui pe benzi in `a`. mantiseDa = false: numai
   pana la exponenti (energia din exponenti). -> false la orice abatere de la standard. */
static bool blocAc3(Biti &b, StareAc3 &s, int blk, bool mantiseDa, Acum &a)
{
	int nfch = s.nfch;
	for (int ch = 1; ch <= nfch; ch++)
		s.blksw[ch] = s.blkswe ? b.ia1() : false;
	if (s.dithflage)
		for (int ch = 1; ch <= nfch; ch++)
			s.dither[ch] = b.ia1();
	for (int i = 0; i < (s.acmod == 0 ? 2 : 1); i++)
		if (b.ia1())
			b.ia(8);
	/* extensia spectrala (E-AC-3) */
	if (s.eac3 && (!blk || b.ia1()))
	{
		s.spxinu = b.ia1();
		if (s.spxinu)
		{
			if (s.acmod == 1)
				s.inSpx[1] = true;
			else
			{
				int m = b.ia(nfch);
				for (int ch = nfch; ch >= 1; ch--)
				{
					s.inSpx[ch] = m & 1;
					m >>= 1;
				}
			}
			int dst = b.ia(2);
			int s0 = b.ia(3) + 2;
			if (s0 > 7)
				s0 += s0 - 7;
			int s1 = b.ia(3) + 5;
			if (s1 > 7)
				s1 += s1 - 7;
			if (s0 >= s1 || dst * 12 + 25 >= s0 * 12 + 25)
				return false;
			s.spxStart = s0 * 12 + 25;
			s.spxEnd = s1 * 12 + 25;
			s.nSpx = structura(b, b.ia1(), blk, s0, s1, SPX_IMPLICIT, 17, s.spxStruct, s.spxMarimi);
			if (!s.nSpx)
				return false;
		}
	}
	if (!s.eac3 || !s.spxinu)
	{
		s.spxinu = false;
		for (int ch = 1; ch <= nfch; ch++)
		{
			s.inSpx[ch] = false;
			s.primeleCoSpx[ch] = true;
		}
	}
	if (s.spxinu)
	{
		for (int ch = 1; ch <= nfch; ch++)
		{
			if (!s.inSpx[ch])
			{
				s.primeleCoSpx[ch] = true;
				continue;
			}
			if (s.primeleCoSpx[ch] || b.ia1())
			{
				s.primeleCoSpx[ch] = false;
				b.ia(5);                            /* amestecul cu zgomot */
				int master = b.ia(2) * 3;
				for (int k = 0; k < s.nSpx; k++)
				{
					int e = b.ia(4);
					int m = b.ia(2);
					m = e == 15 ? m << 1 : m + 4;
					/* linia de dupa amestec are varianta 1, inmultita cu coordonata */
					s.spxCo[ch][k] = ldexp((double)m, 2 - e - master);
				}
			}
		}
	}
	/* cuplajul */
	if (s.eac3 ? (s.acmod > 1 && s.cplStre[blk]) : b.ia1())
	{
		if (s.eac3)
			s.cplinu = s.cplInu[blk];
		if (!strategieCuplaj(b, s, blk))
			return false;
	}
	else if (!s.eac3)
	{
		if (!blk)
			return false;
	}
	else if (s.acmod > 1)
		s.cplinu = s.cplInu[blk];
	if (s.cplinu)
	{
		bool exista = false;
		for (int ch = 1; ch <= nfch; ch++)
		{
			if (!s.inCpl[ch])
			{
				s.primeleCoCpl[ch] = true;
				continue;
			}
			if ((s.eac3 && s.primeleCoCpl[ch]) || b.ia1())
			{
				s.primeleCoCpl[ch] = false;
				exista = true;
				int master = b.ia(2) * 3;
				for (int k = 0; k < s.nCpl; k++)
				{
					int e = b.ia(4);
					int m = b.ia(4);
					double v = e == 15 ? m / 16.0 : (m + 16) / 32.0;
					s.cplCo[ch][k] = ldexp(8.0 * v, -(e + master));
				}
			}
			else if (!blk)
				return false;
		}
		if (s.acmod == 2 && exista)
			for (int k = 0; k < s.nCpl; k++)
				if (s.fazaFolosita)
					b.ia(1);
	}
	/* rematricea */
	if (s.acmod == 2)
	{
		if ((s.eac3 && !blk) || b.ia1())
		{
			s.nRem = 4;
			if (s.cplinu && s.cplStart <= 61)
				s.nRem -= 1 + (s.cplStart == 37);
			else if (s.spxinu && s.spxStart <= 61)
				s.nRem--;
			for (int i = 0; i < s.nRem; i++)
				s.rem[i] = b.ia1();
		}
		else if (!blk)
			s.nRem = 0;
	}
	/* strategiile exponentilor */
	int *str = s.strat[blk];
	if (!s.eac3)
		for (int ch = s.cplinu ? 0 : 1; ch <= s.nch; ch++)
			str[ch] = b.ia(ch == s.lfeCh ? 1 : 2);
	if (!s.cplinu)
		str[CPL_CH] = 0;
	for (int ch = 1; ch <= nfch; ch++)
	{
		s.start[ch] = 0;
		if (!str[ch])
		{
			if (!blk)
				return false;
			continue;
		}
		if (s.inCpl[ch])
			s.end[ch] = s.cplStart;
		else if (s.inSpx[ch])
			s.end[ch] = s.spxStart;
		else
		{
			int bw = b.ia(6);
			if (bw > 60)
				return false;
			s.end[ch] = bw * 3 + 73;
		}
		int dim = 3 << (str[ch] - 1);
		s.grupe[ch] = (s.end[ch] + dim - 4) / dim;
	}
	if (s.cplinu)
	{
		s.start[CPL_CH] = s.cplStart;
		s.end[CPL_CH] = s.cplEnd;
		if (str[CPL_CH])
			s.grupe[CPL_CH] = (s.cplEnd - s.cplStart) / (3 << (str[CPL_CH] - 1));
		else if (!blk)
			return false;
	}
	if (s.lfeon)
	{
		s.start[s.lfeCh] = 0;
		s.end[s.lfeCh] = 7;
		s.grupe[s.lfeCh] = 2;
		if (!blk && !str[s.lfeCh])
			return false;
	}
	/* exponentii */
	for (int ch = s.cplinu ? 0 : 1; ch <= s.nch; ch++)
	{
		if (!str[ch])
			continue;
		int abs = b.ia(4) << (ch == CPL_CH ? 1 : 0);
		if (ch == CPL_CH)
		{
			if (!exponenti(b, str[ch], s.grupe[ch], abs, s.exps[ch] + s.start[ch], 256 - s.start[ch]))
				return false;
		}
		else
		{
			if (abs > 24)
				return false;
			s.exps[ch][0] = abs;
			if (!exponenti(b, str[ch], s.grupe[ch], abs, s.exps[ch] + 1, 255))
				return false;
			if (ch != s.lfeCh)
				b.ia(2);                /* gainrng */
		}
	}
	if (b.rau)
		return false;
	if (mantiseDa)
	{
		/* parametrii alocarii */
		if (s.bamode)
		{
			if (b.ia1())
			{
				s.sdecay = hdsAc3ScadereLenta[b.ia(2)] >> s.srShift;
				s.fdecay = hdsAc3ScadereRapida[b.ia(2)] >> s.srShift;
				s.sgain = hdsAc3CastigLent[b.ia(2)];
				s.dbknee = hdsAc3DbPeBit[b.ia(2)];
				s.podea = hdsAc3Podea[b.ia(3)];
			}
			else if (!blk)
				return false;
		}
		if (!s.eac3 || !blk)
		{
			if (s.snrStrat && b.ia1())
			{
				int csnr = ((int)b.ia(6) - 15) * 16;
				int snr = 0;
				int prim = s.cplinu ? 0 : 1;
				for (int ch = prim; ch <= s.nch; ch++)
				{
					if (ch == prim || s.snrStrat == 2)
						snr = (csnr + (int)b.ia(4)) * 4;
					s.snr[ch] = snr;
					if (!s.eac3)
						s.fgain[ch] = hdsAc3CastigRapid[b.ia(3)];
				}
			}
			else if (!s.eac3 && !blk)
				return false;
		}
		if (s.fgainSintaxa && b.ia1())
		{
			for (int ch = s.cplinu ? 0 : 1; ch <= s.nch; ch++)
				s.fgain[ch] = hdsAc3CastigRapid[b.ia(3)];
		}
		else if (s.eac3 && !blk)
		{
			for (int ch = 0; ch <= s.nch; ch++)
				s.fgain[ch] = hdsAc3CastigRapid[4];
		}
		if (s.convertor && b.ia1())
			b.ia(10);
		if (s.cplinu)
		{
			if (s.primulLeak || b.ia1())
			{
				s.cplFleak = b.ia(3);
				s.cplSleak = b.ia(3);
			}
			else if (!s.eac3 && !blk)
				return false;
			s.primulLeak = false;
		}
		if (s.dbaSintaxa && b.ia1())
		{
			for (int ch = s.cplinu ? 0 : 1; ch <= nfch; ch++)
			{
				s.dbaMod[ch] = b.ia(2);
				if (s.dbaMod[ch] == 3)
					return false;
			}
			for (int ch = s.cplinu ? 0 : 1; ch <= nfch; ch++)
				if (s.dbaMod[ch] == DBA_NOU)
				{
					s.dbaSeg[ch] = b.ia(3) + 1;
					for (int k = 0; k < s.dbaSeg[ch]; k++)
					{
						s.dbaOff[ch][k] = b.ia(5);
						s.dbaLung[ch][k] = b.ia(4);
						s.dbaVal[ch][k] = b.ia(3);
					}
				}
		}
		else if (!blk)
		{
			for (int ch = 0; ch <= s.nch; ch++)
				s.dbaMod[ch] = DBA_FARA;
		}
		if (s.skipSintaxa && b.ia1())
		{
			int l = b.ia(9);
			b.sari(8 * l);
		}
		if (b.rau)
			return false;
		/* alocarea si mantisele */
		for (int ch = s.cplinu ? 0 : 1; ch <= s.nch; ch++)
		{
			if (s.end[ch] <= s.start[ch])
				continue;
			psdBenzi(s.exps[ch], s.start[ch], s.end[ch], s.psd[ch], s.bandPsd[ch]);
			if (!mascaAc3(s, ch, s.start[ch], s.end[ch], s.masca[ch]))
				return false;
			trepteAc3(s.masca[ch], s.psd[ch], s.start[ch], s.end[ch], s.snr[ch], s.podea, s.bap[ch]);
		}
		Grupe g;
		memset(&g, 0, sizeof(g));
		bool cplCitit = false;
		for (int ch = 1; ch <= s.nch; ch++)
		{
			if (!mantise(b, s, ch, s.start[ch], s.end[ch], g))
				return false;
			if (ch <= nfch && s.inCpl[ch] && !cplCitit)
			{
				if (!mantise(b, s, CPL_CH, s.cplStart, s.cplEnd, g))
					return false;
				cplCitit = true;
			}
		}
		if (b.rau)
			return false;
	}
	/* energia blocului pe linii, pentru fiecare canal fbw */
	double en[6][256];
	for (int ch = 1; ch <= nfch; ch++)
	{
		for (int k = 0; k < 256; k++)
			en[ch][k] = 0.0;
		for (int k = 0; k < s.end[ch] && k < 256; k++)
			en[ch][k] = mantiseDa ? energieLinie(s, ch, k) : putereExp(s.exps[ch][k]) * ENERGIE_FARA_MANTISE;
		if (s.cplinu && s.inCpl[ch])
		{
			int k = s.cplStart;
			for (int bnd = 0; bnd < s.nCpl; bnd++)
			{
				double c2 = s.cplCo[ch][bnd] * s.cplCo[ch][bnd];
				for (int j = 0; j < s.cplMarimi[bnd] && k < s.cplEnd && k < 256; j++, k++)
				{
					double e = mantiseDa ? energieLinie(s, CPL_CH, k)
						: putereExp(s.exps[CPL_CH][k]) * ENERGIE_FARA_MANTISE;
					if (mantiseDa && s.coef[CPL_CH][k] == -1.0f && !s.dither[ch])
						e = 0.0;
					en[ch][k] = e * c2;
				}
			}
		}
		if (s.spxinu && s.inSpx[ch])
		{
			int k = s.spxStart;
			for (int bnd = 0; bnd < s.nSpx; bnd++)
			{
				double c2 = s.spxCo[ch][bnd] * s.spxCo[ch][bnd];
				for (int j = 0; j < s.spxMarimi[bnd] && k < s.spxEnd && k < 256; j++, k++)
					en[ch][k] = c2;
			}
		}
		if (s.blksw[ch])
			for (int k = 0; k < 256; k++)
				en[ch][k] *= 2.0;           /* doua transformari de 256: fiecare linie are jumatate din energie */
	}
	if (s.acmod == 2)
	{
		/* benzile rematrice: in flux sunt suma si diferenta */
		int sf = s.end[1] < s.end[2] ? s.end[1] : s.end[2];
		for (int r = 0; r < s.nRem; r++)
		{
			if (!s.rem[r])
				continue;
			for (int k = REMATRICE[r]; k < REMATRICE[r + 1] && k < sf; k++)
			{
				if (mantiseDa)
				{
					double e0 = putereExp(s.exps[1][k]), e1 = putereExp(s.exps[2][k]);
					float m0 = s.coef[1][k] == -1.0f ? 0.0f : s.coef[1][k];
					float m1 = s.coef[2][k] == -1.0f ? 0.0f : s.coef[2][k];
					double x = sqrt(e0) * m0, y = sqrt(e1) * m1;
					en[1][k] = (x + y) * (x + y);
					en[2][k] = (x - y) * (x - y);
				}
				else
				{
					double t = en[1][k] + en[2][k];
					en[1][k] = en[2][k] = t;
				}
			}
		}
	}
	for (int ch = 1; ch <= nfch; ch++)
	{
		int parte = AC3_PARTE[s.acmod][ch - 1];
		double fc = AC3_SPATE[s.acmod][ch - 1] ? 0.5 : 1.0;
		for (int k = 0; k < 256; k++)
			if (en[ch][k] > 0.0)
				a.adauga(parte, k, 256, fc * en[ch][k]);
	}
	return true;
}

/* Blocurile cadrului: energia pe benzi a fiecaruia, iar pe cadru cea mai mare. */
static bool blocuriAc3(Biti &b, StareAc3 &s, Acum &a)
{
	bool mantiseDa = !s.aht && s.srShift <= 2 && !(s.eac3 && s.srShift);
	for (int ch = 0; ch < 7; ch++)
	{
		s.dither[ch] = true;
		s.primeleCoCpl[ch] = s.primeleCoSpx[ch] = true;
		s.dbaMod[ch] = DBA_FARA;
		s.dbaSeg[ch] = 0;
		s.inCpl[ch] = s.inSpx[ch] = false;
		s.fgain[ch] = hdsAc3CastigRapid[4];
		s.end[ch] = s.start[ch] = 0;
	}
	s.cplinu = 0;
	s.spxinu = false;
	s.nRem = 0;
	s.primulLeak = s.eac3;          /* AC-3: bitul cplleake e mereu in flux */
	s.cplFleak = s.cplSleak = 0;
	if (s.eac3 && !s.bamode)
	{
		s.sdecay = hdsAc3ScadereLenta[2];
		s.fdecay = hdsAc3ScadereRapida[1];
		s.sgain = hdsAc3CastigLent[1];
		s.dbknee = hdsAc3DbPeBit[2];
		s.podea = hdsAc3Podea[7];
	}
	int facute = 0;
	for (int blk = 0; blk < s.nblk; blk++)
	{
		Acum bloc;
		bloc.goleste();
		if (!blocAc3(b, s, blk, mantiseDa, bloc))
		{
			if (blk == 0 && mantiseDa)
			{
				/* blocul 0 fara mantise: macar exponentii lui (cadrul se citeste inca o data de la inceput) */
				return false;
			}
			break;
		}
		for (int p = 0; p < 2; p++)
			for (int k = 0; k < BENZI; k++)
				if (bloc.e[p][k] > a.e[p][k])
					a.e[p][k] = bloc.e[p][k];
		facute++;
		if (!mantiseDa)
			break;
	}
	a.sce = s.acmod == 1 ? 1 : 0;
	a.cpe = s.acmod == 1 ? 0 : 1;
	return facute > 0;
}

static int fsAc3(int fscod)
{
	static const int f[3] = { 48000, 44100, 32000 };
	return fscod < 3 ? f[fscod] : 0;
}

/* -> esantionarea, 0 daca nu e un cadru bun */
static int cadruAc3(const uint8_t *d, uint32_t n, Acum &a, Info &info, StareAc3 &s)
{
	for (int incercare = 0; incercare < 2; incercare++)
	{
		Biti b;
		b.init(d, n);
		if (b.ia(16) != 0x0B77)
			return 0;
		b.ia(16);
		int fscod = b.ia(2);
		b.ia(6);
		int bsid = b.ia(5);
		if (fscod == 3 || bsid > 10)
			return 0;
		b.ia(3);
		int acmod = b.ia(3);
		if ((acmod & 1) && acmod != 1)
			b.ia(2);
		if (acmod & 4)
			b.ia(2);
		if (acmod == 2)
			b.ia(2);
		int lfeon = b.ia(1);
		for (int i = 0; i < (acmod ? 1 : 2); i++)
		{
			b.ia(5);
			if (b.ia1())
				b.ia(8);
			if (b.ia1())
				b.ia(8);
			if (b.ia1())
				b.ia(7);
		}
		b.ia(2);
		/* coduri de timp (sau, la bsid 6, informatiile de amestec): acelasi numar de biti */
		if (b.ia1())
			b.ia(14);
		if (b.ia1())
			b.ia(14);
		if (b.ia1())
		{
			int l = b.ia(6);
			b.sari((l + 1) * 8);
		}
		memset(s.strat, 0, sizeof(s.strat));
		memset(s.snr, 0, sizeof(s.snr));
		memset(s.bandPsd, 0, sizeof(s.bandPsd));
		s.eac3 = false;
		s.acmod = acmod;
		s.nfch = AC3_CANALE[acmod];
		s.lfeon = lfeon;
		s.lfeCh = lfeon ? s.nfch + 1 : -1;
		s.nch = s.nfch + lfeon;
		s.nblk = 6;
		s.srShift = bsid > 8 ? bsid - 8 : 0;
		s.fscod = fscod;
		s.blkswe = s.dithflage = s.bamode = s.dbaSintaxa = s.skipSintaxa = true;
		s.fgainSintaxa = s.convertor = false;
		s.snrStrat = 2;
		/* a doua incercare: numai exponentii blocului 0 */
		s.aht = incercare == 1;
		Acum x;
		x.goleste();
		if (!blocuriAc3(b, s, x))
			continue;
		memcpy(a.e, x.e, sizeof(x.e));
		a.sce = x.sce;
		a.cpe = x.cpe;
		int fs = fsAc3(fscod) >> s.srShift;
		info.esantionare = fs;
		info.canale = s.nfch;
		info.lfe = lfeon;
		info.profil = bsid;
		return fs;
	}
	return 0;
}

static int log2Sus(int v)
{
	int n = 0;
	while ((1 << n) < v)
		n++;
	return n;
}

static int cadruEac3(const uint8_t *d, uint32_t n, Acum &a, Info &info, bool &ignorat, StareAc3 &s)
{
	ignorat = false;
	for (int incercare = 0; incercare < 2; incercare++)
	{
		Biti b;
		b.init(d, n);
		if (b.ia(16) != 0x0B77)
			return 0;
		int strmtyp = b.ia(2);
		int substream = b.ia(3);
		int frmsiz = b.ia(11);
		int fscod = b.ia(2);
		int nblk, fs, srShift = 0;
		if (fscod == 3)
		{
			int f2 = b.ia(2);
			if (f2 == 3)
				return 0;
			static const int r[3] = { 24000, 22050, 16000 };
			fs = r[f2];
			nblk = 6;
			srShift = 1;
		}
		else
		{
			static const int nb[4] = { 1, 2, 3, 6 };
			nblk = nb[b.ia(2)];
			fs = fsAc3(fscod);
		}
		int acmod = b.ia(3);
		int lfeon = b.ia(1);
		int bsid = b.ia(5);
		if (bsid <= 10 || bsid > 16 || strmtyp == 3)
			return 0;
		if (strmtyp == 1 || substream != 0)
		{
			/* flux dependent (canale in plus) sau alt program: barele vin din programul 0 */
			ignorat = true;
			return 0;
		}
		int nfch = AC3_CANALE[acmod];
		for (int i = 0; i < (acmod ? 1 : 2); i++)
		{
			b.ia(5);
			if (b.ia1())
				b.ia(8);
		}
		if (b.ia1())                    /* mixmdate */
		{
			if (acmod > 2)
			{
				b.ia(2);
				if (acmod & 1)
					b.ia(6);
				if (acmod & 4)
					b.ia(6);
			}
			if (lfeon && b.ia1())
				b.ia(5);
			if (strmtyp == 0)
			{
				for (int i = 0; i < (acmod ? 1 : 2); i++)
					if (b.ia1())
						b.ia(6);
				if (b.ia1())
					b.ia(6);
				switch (b.ia(2))
				{
				case 1:
					b.ia(5);
					break;
				case 2:
					b.ia(12);
					break;
				case 3:
					b.sari((b.ia(5) + 2) * 8);
					break;
				}
				if (acmod < 2)
					for (int i = 0; i < (acmod ? 1 : 2); i++)
						if (b.ia1())
							b.ia(14);
				if (b.ia1())
					for (int i = 0; i < nblk; i++)
						if (nblk == 1 || b.ia1())
							b.ia(5);
			}
		}
		if (b.ia1())                    /* infomdate */
		{
			b.ia(5);
			if (acmod == 2)
				b.ia(4);
			if (acmod >= 6)
				b.ia(2);
			for (int i = 0; i < (acmod ? 1 : 2); i++)
				if (b.ia1())
					b.ia(8);
			if (fscod != 3)
				b.ia(1);
		}
		if (strmtyp == 0 && nblk != 6)
			b.ia(1);
		if (strmtyp == 2 && (nblk == 6 || b.ia1()))
			b.ia(6);
		if (b.ia1())
		{
			int l = b.ia(6);
			b.sari((l + 1) * 8);
		}
		/* audfrm */
		memset(s.strat, 0, sizeof(s.strat));
		memset(s.snr, 0, sizeof(s.snr));
		memset(s.bandPsd, 0, sizeof(s.bandPsd));
		s.eac3 = true;
		s.acmod = acmod;
		s.nfch = nfch;
		s.lfeon = lfeon;
		s.lfeCh = lfeon ? nfch + 1 : -1;
		s.nch = nfch + lfeon;
		s.nblk = nblk;
		s.srShift = srShift;
		s.fscod = fscod == 3 ? 0 : fscod;
		bool expstre = true, ahte = false;
		if (nblk == 6)
		{
			expstre = b.ia1();
			ahte = b.ia1();
		}
		s.snrStrat = b.ia(2);
		bool transproce = b.ia1();
		s.blkswe = b.ia1();
		s.dithflage = b.ia1();
		s.bamode = b.ia1();
		s.fgainSintaxa = b.ia1();
		s.dbaSintaxa = b.ia1();
		s.skipSintaxa = b.ia1();
		bool spxattene = b.ia1();
		s.convertor = strmtyp == 0;
		int ncpl = 0;
		for (int blk = 0; blk < 6; blk++)
			s.cplStre[blk] = s.cplInu[blk] = 0;
		if (acmod > 1)
		{
			for (int blk = 0; blk < nblk; blk++)
			{
				s.cplStre[blk] = blk == 0 || b.ia1();
				s.cplInu[blk] = s.cplStre[blk] ? b.ia(1) : s.cplInu[blk - 1];
				ncpl += s.cplInu[blk];
			}
		}
		if (expstre)
		{
			for (int blk = 0; blk < nblk; blk++)
				for (int ch = s.cplInu[blk] ? 0 : 1; ch <= nfch; ch++)
					s.strat[blk][ch] = b.ia(2);
		}
		else
		{
			/* tabelul strategiilor pe cadru: primul bloc D15 la 0-3, D25 la 4-15, D45 la 16-31; dupa el, cu
			   mantisele citite, strategiile blocurilor urmatoare conteaza, deci tabelul intreg */
			static const uint8_t t[32][6] = {
				{ 1, 0, 0, 0, 0, 0 }, { 1, 0, 0, 0, 0, 3 }, { 1, 0, 0, 0, 2, 0 }, { 1, 0, 0, 0, 3, 3 },
				{ 2, 0, 0, 2, 0, 0 }, { 2, 0, 0, 2, 0, 3 }, { 2, 0, 0, 3, 2, 0 }, { 2, 0, 0, 3, 3, 3 },
				{ 2, 0, 1, 0, 0, 0 }, { 2, 0, 2, 0, 0, 3 }, { 2, 0, 2, 0, 2, 0 }, { 2, 0, 2, 0, 3, 3 },
				{ 2, 0, 3, 2, 0, 0 }, { 2, 0, 3, 2, 0, 3 }, { 2, 0, 3, 3, 2, 0 }, { 2, 0, 3, 3, 3, 3 },
				{ 3, 1, 0, 0, 0, 0 }, { 3, 1, 0, 0, 0, 3 }, { 3, 2, 0, 0, 2, 0 }, { 3, 2, 0, 0, 3, 3 },
				{ 3, 2, 0, 2, 0, 0 }, { 3, 2, 0, 2, 0, 3 }, { 3, 2, 0, 3, 2, 0 }, { 3, 2, 0, 3, 3, 3 },
				{ 3, 3, 1, 0, 0, 0 }, { 3, 3, 2, 0, 0, 3 }, { 3, 3, 2, 0, 2, 0 }, { 3, 3, 2, 0, 3, 3 },
				{ 3, 3, 3, 2, 0, 0 }, { 3, 3, 3, 2, 0, 3 }, { 3, 3, 3, 3, 2, 0 }, { 3, 3, 3, 3, 3, 3 },
			};
			for (int ch = (acmod > 1 && ncpl) ? 0 : 1; ch <= nfch; ch++)
			{
				int k = b.ia(5);
				for (int blk = 0; blk < 6; blk++)
					s.strat[blk][ch] = t[k][blk];
			}
		}
		if (lfeon)
			for (int blk = 0; blk < nblk; blk++)
				s.strat[blk][s.lfeCh] = b.ia(1);
		if (strmtyp == 0 && (nblk == 6 || b.ia1()))
			b.sari(5 * nfch);
		s.aht = incercare == 1;
		if (ahte)
		{
			for (int ch = ncpl == 6 ? 0 : 1; ch <= s.nch; ch++)
			{
				bool poate = true;
				for (int blk = 1; blk < 6; blk++)
					if (s.strat[blk][ch] != 0 || (ch == 0 && s.cplStre[blk]))
					{
						poate = false;
						break;
					}
				if (poate && b.ia1())
					s.aht = true;
			}
		}
		if (s.snrStrat == 0)
		{
			int csnr = ((int)b.ia(6) - 15) * 16;
			int snr = (csnr + (int)b.ia(4)) * 4;
			for (int ch = 0; ch < 7; ch++)
				s.snr[ch] = snr;
		}
		if (transproce)
			for (int ch = 1; ch <= nfch; ch++)
				if (b.ia1())
					b.ia(18);
		if (spxattene)
			for (int ch = 1; ch <= nfch; ch++)
				if (b.ia1())
					b.ia(5);
		if (nblk > 1 && b.ia1())
			b.sari((nblk - 1) * (4 + log2Sus(frmsiz + 1)));
		if (b.rau)
			return 0;
		Acum x;
		x.goleste();
		if (!blocuriAc3(b, s, x))
			continue;
		memcpy(a.e, x.e, sizeof(x.e));
		a.sce = x.sce;
		a.cpe = x.cpe;
		info.esantionare = fs;
		info.canale = nfch;
		info.lfe = lfeon;
		info.profil = bsid;
		return fs;
	}
	return 0;
}

/* ---------------------------------------------------------------- DTS (nucleul) */

static const int DTS_FS[16] = { 0, 8000, 16000, 32000, 0, 0, 11025, 22050, 44100, 0, 0, 12000, 24000, 48000, 0, 0 };
static const int DTS_CANALE[10] = { 1, 2, 2, 2, 2, 3, 3, 4, 4, 5 };
/* partea fiecarui canal al nucleului, in ordinea din flux: A, A B, L R, S D (suma, diferenta), Lt Rt, C L R, L R S,
   C L R S, L R Ls Rs, C L R Ls Rs */
static const uint8_t DTS_PARTE[10][5] = {
	{ AMBELE }, { STANGA, DREAPTA }, { STANGA, DREAPTA }, { STANGA, DREAPTA }, { STANGA, DREAPTA },
	{ CENTRU, STANGA, DREAPTA }, { STANGA, DREAPTA, CENTRU }, { CENTRU, STANGA, DREAPTA, CENTRU },
	{ STANGA, DREAPTA, STANGA, DREAPTA }, { CENTRU, STANGA, DREAPTA, STANGA, DREAPTA },
};
static const uint8_t DTS_SPATE[10][5] = {
	{ 0 }, { 0, 0 }, { 0, 0 }, { 0, 0 }, { 0, 0 }, { 0, 0, 0 }, { 0, 0, 1 }, { 0, 0, 0, 1 }, { 0, 0, 1, 1 },
	{ 0, 0, 0, 1, 1 },
};
static const uint8_t DTS_BITI_SEL[10] = { 1, 2, 2, 2, 2, 3, 3, 3, 3, 3 };
static const uint8_t DTS_GRUP_SEL[10] = { 1, 3, 3, 3, 3, 7, 7, 7, 7, 7 };

struct TabeleDts
{
	Vlc alocare[5];
	Vlc tranzitie[4];
	Vlc scala[5];
	bool bun;

	TabeleDts()
	{
		bun = true;
		for (int k = 0; k < 5; k++)
		{
			construiesteVlc(alocare[k], 12, hdsDtsCodAlocare[k], hdsDtsLungAlocare[k]);
			construiesteVlc(scala[k], 129, hdsDtsCodScala[k], hdsDtsLungScala[k]);
			bun = bun && alocare[k].bun && scala[k].bun;
		}
		for (int k = 0; k < 4; k++)
		{
			construiesteVlc(tranzitie[k], 4, hdsDtsCodTranzitie[k], hdsDtsLungTranzitie[k]);
			bun = bun && tranzitie[k].bun;
		}
	}
};

static const TabeleDts &tabeleDts()
{
	static TabeleDts t;
	return t;
}

/* factorul de scala (valoarea din tabel) sau -1 */
static int scalaDts(Biti &b, int &idx, int sel, const TabeleDts &T)
{
	if (sel < 5)
		idx += decodeaza(b, T.scala[sel]) - 64;
	else
		idx = b.ia(sel + 1);
	int v = 0;
	if (sel > 5)
		v = (idx >= 0 && idx < 128) ? (int)hdsDtsScala7[idx] : 0;
	else
		v = (idx >= 0 && idx < 64) ? (int)hdsDtsScala6[idx] : 0;
	return v > 0 ? v : -1;
}

static int cadruDts(const uint8_t *d, uint32_t n, Acum &a, Info &info)
{
	const TabeleDts &T = tabeleDts();
	if (!T.bun)
		return 0;
	Biti b;
	b.init(d, n);
	if (b.ia(32) != 0x7FFE8001u)
		return 0;
	b.ia(1);
	if (b.ia(5) + 1 != 32)
		return 0;
	bool crc = b.ia1();
	int npcm = b.ia(7) + 1;
	int fsize = b.ia(14) + 1;
	int amode = b.ia(6);
	int sr = b.ia(4);
	b.ia(5);
	if (b.ia1() || (npcm & 7) || fsize < 96 || amode > 9 || !DTS_FS[sr])
		return 0;
	b.ia(4);
	b.ia(3);
	b.ia(2);
	int lfe = b.ia(2);
	if (lfe == 3)
		return 0;
	b.ia(1);
	if (crc)
		b.ia(16);
	b.ia(1);
	b.ia(4);
	b.ia(2);
	b.ia(3);
	bool sumaFata = b.ia1();
	b.ia(1);
	b.ia(4);
	/* antetul codarii */
	b.ia(4);
	int nch = b.ia(3) + 1;
	if (nch != DTS_CANALE[amode])
		return 0;
	int subs[5], vq[5], joint[5], tsel[5], ssel[5], bsel[5], qsel[5][10];
	for (int ch = 0; ch < nch; ch++)
	{
		subs[ch] = b.ia(5) + 2;
		if (subs[ch] > 32)
			return 0;
	}
	for (int ch = 0; ch < nch; ch++)
	{
		vq[ch] = b.ia(5) + 1;
		if (vq[ch] > subs[ch])
			vq[ch] = subs[ch];
	}
	for (int ch = 0; ch < nch; ch++)
	{
		joint[ch] = b.ia(3);
		if (joint[ch] > nch)
			return 0;
	}
	for (int ch = 0; ch < nch; ch++)
		tsel[ch] = b.ia(2);
	for (int ch = 0; ch < nch; ch++)
	{
		ssel[ch] = b.ia(3);
		if (ssel[ch] == 7)
			return 0;
	}
	for (int ch = 0; ch < nch; ch++)
	{
		bsel[ch] = b.ia(3);
		if (bsel[ch] == 7)
			return 0;
	}
	for (int k = 0; k < 10; k++)
		for (int ch = 0; ch < nch; ch++)
			qsel[ch][k] = b.ia(DTS_BITI_SEL[k]);
	for (int k = 0; k < 10; k++)
		for (int ch = 0; ch < nch; ch++)
			if (qsel[ch][k] < DTS_GRUP_SEL[k])
				b.ia(2);
	if (crc)
		b.ia(16);
	/* primul subcadru: pana la factorii de scala */
	int nssf = b.ia(2) + 1;
	b.ia(3);
	uint8_t pm[5][32];
	for (int ch = 0; ch < nch; ch++)
		for (int s = 0; s < subs[ch]; s++)
			pm[ch][s] = b.ia(1);
	for (int ch = 0; ch < nch; ch++)
		for (int s = 0; s < subs[ch]; s++)
			if (pm[ch][s])
				b.ia(12);
	int ab[5][32];
	for (int ch = 0; ch < nch; ch++)
		for (int s = 0; s < vq[ch]; s++)
		{
			int v = bsel[ch] < 5 ? decodeaza(b, T.alocare[bsel[ch]]) + 1 : (int)b.ia(bsel[ch] - 1);
			if (v > 26)
				return 0;
			ab[ch][s] = v;
		}
	int tm[5][32];
	for (int ch = 0; ch < nch; ch++)
		for (int s = 0; s < vq[ch]; s++)
			tm[ch][s] = (nssf > 1 && ab[ch][s]) ? decodeaza(b, T.tranzitie[tsel[ch]]) : 0;
	double en[5][32];
	memset(en, 0, sizeof(en));
	for (int ch = 0; ch < nch; ch++)
	{
		int idx = 0;
		for (int s = 0; s < vq[ch]; s++)
		{
			if (!ab[ch][s])
				continue;
			int v = scalaDts(b, idx, ssel[ch], T);
			if (v < 0)
				return 0;
			if (tm[ch][s])
			{
				int v2 = scalaDts(b, idx, ssel[ch], T);
				if (v2 < 0)
					return 0;
				if (v2 > v)
					v = v2;
			}
			en[ch][s] = (double)v * v;
		}
		for (int s = vq[ch]; s < subs[ch]; s++)
		{
			int v = scalaDts(b, idx, ssel[ch], T);
			if (v < 0)
				return 0;
			en[ch][s] = (double)v * v;
		}
	}
	if (b.rau)
		return 0;
	/* codarea in comun: subbenzile de sus ale canalului vin din canalul sursa */
	for (int ch = 0; ch < nch; ch++)
		if (joint[ch])
		{
			int src = joint[ch] - 1;
			for (int s = subs[ch]; s < subs[src] && s < 32; s++)
				en[ch][s] = en[src][s];
		}
	if (amode == 3 || (sumaFata && nch >= 2))
	{
		/* suma si diferenta: fiecare parte primeste energia amandurora */
		int l = (amode == 5 || amode == 7 || amode == 9) ? 1 : 0;
		for (int s = 0; s < 32; s++)
		{
			double t = en[l][s] + en[l + 1][s];
			en[l][s] = en[l + 1][s] = t;
		}
	}
	for (int ch = 0; ch < nch; ch++)
	{
		int parte = DTS_PARTE[amode][ch];
		double fc = DTS_SPATE[amode][ch] ? 0.5 : 1.0;
		for (int s = 0; s < 32; s++)
			if (en[ch][s] > 0.0)
				a.adauga(parte, s, 32, fc * en[ch][s]);
	}
	a.sce = amode == 0 ? 1 : 0;
	a.cpe = amode == 0 ? 0 : 1;
	info.esantionare = DTS_FS[sr];
	info.canale = nch;
	info.lfe = lfe ? 1 : 0;
	info.profil = 0;
	return DTS_FS[sr];
}

/* ---------------------------------------------------------------- PCM SMPTE 302M */

static void fft128(float *re, float *im, const Tabele &T)
{
	/* inversarea bitilor indicilor */
	for (int i = 1, j = 0; i < 128; i++)
	{
		int bit = 64;
		for (; j & bit; bit >>= 1)
			j ^= bit;
		j ^= bit;
		if (i < j)
		{
			float t = re[i];
			re[i] = re[j];
			re[j] = t;
			t = im[i];
			im[i] = im[j];
			im[j] = t;
		}
	}
	for (int lung = 2; lung <= 128; lung <<= 1)
	{
		int pas = 128 / lung;
		for (int i = 0; i < 128; i += lung)
			for (int k = 0; k < lung / 2; k++)
			{
				float c = T.cosT[k * pas], s = T.sinT[k * pas];
				float xr = re[i + k + lung / 2] * c - im[i + k + lung / 2] * s;
				float xi = re[i + k + lung / 2] * s + im[i + k + lung / 2] * c;
				re[i + k + lung / 2] = re[i + k] - xr;
				im[i + k + lung / 2] = im[i + k] - xi;
				re[i + k] += xr;
				im[i + k] += xi;
			}
	}
}

static const int FERESTRE_PCM_MAX = 16;

/* -> 48000, 0 daca nu e un cadru PCM bun; *nePcm = 1 cand pachetul poarta alt fel de sunet (SMPTE 337M) */
static int cadruS302m(const uint8_t *d, uint32_t n, Acum &a, Info &info, bool &nePcm)
{
	const Tabele &T = tabele();
	nePcm = false;
	if (n < 5)
		return 0;
	uint32_t h = ((uint32_t)d[0] << 24) | ((uint32_t)d[1] << 16) | ((uint32_t)d[2] << 8) | d[3];
	uint32_t marime = h >> 16;
	int canale = ((h >> 14) & 3) * 2 + 2;
	int biti = ((h >> 4) & 3) * 4 + 16;
	if (biti > 24 || marime + 4 != n)
		return 0;
	int octetiPereche = biti == 16 ? 5 : (biti == 20 ? 6 : 7);
	int perechi = canale / 2;
	int grup = octetiPereche * perechi;
	int esantioane = marime / grup;
	if (esantioane < 128)
		return 0;
	const uint8_t *p = d + 4;
	const uint8_t *r = T.invers;
	/* esantionul k al perechii c, ca intreg cu semn pe 32 de biti (aliniat sus) */
	int32_t st[128], dr[128];
	double eSt[64], eDr[64];
	memset(eSt, 0, sizeof(eSt));
	memset(eDr, 0, sizeof(eDr));
	/* ferestre de 128 intinse peste tot pachetul (cel mult 16: 2048 de esantioane din cele 1920-2000 ale unui pachet
	   de 40 ms; la mai multe, cu goluri egale intre ele) */
	int ferestre = esantioane / 128;
	if (ferestre > FERESTRE_PCM_MAX)
		ferestre = FERESTRE_PCM_MAX;
	for (int f = 0; f < ferestre; f++)
	{
		int start = ferestre > 1 ? (int)((long)(esantioane - 128) * f / (ferestre - 1)) : 0;
		for (int c = 0; c < perechi && c < 4; c++)
		{
			for (int k = 0; k < 128; k++)
			{
				const uint8_t *q = p + (long)(start + k) * grup + c * octetiPereche;
				uint32_t x, y;
				if (biti == 24)
				{
					x = ((uint32_t)r[q[2]] << 24) | ((uint32_t)r[q[1]] << 16) | ((uint32_t)r[q[0]] << 8);
					y = ((uint32_t)r[q[6] & 0xf0] << 28) | ((uint32_t)r[q[5]] << 20) | ((uint32_t)r[q[4]] << 12)
						| ((uint32_t)r[q[3] & 0x0f] << 4);
				}
				else if (biti == 20)
				{
					x = ((uint32_t)r[q[2] & 0xf0] << 28) | ((uint32_t)r[q[1]] << 20) | ((uint32_t)r[q[0]] << 12);
					y = ((uint32_t)r[q[5] & 0xf0] << 28) | ((uint32_t)r[q[4]] << 20) | ((uint32_t)r[q[3]] << 12);
				}
				else
				{
					x = ((uint32_t)r[q[1]] << 24) | ((uint32_t)r[q[0]] << 16);
					y = ((uint32_t)r[q[4] & 0xf0] << 28) | ((uint32_t)r[q[3]] << 20) | ((uint32_t)r[q[2]] << 12);
					y &= 0xFFFF0000u;
				}
				if (c == 0)
				{
					st[k] = (int32_t)x;
					dr[k] = (int32_t)y;
				}
				else
				{
					/* celelalte perechi (centru, spate): la jumatate de putere */
					st[k] = st[k] / 2 + ((int32_t)x) / 2;
					dr[k] = dr[k] / 2 + ((int32_t)y) / 2;
				}
			}
			if (c == 0 && f == 0)
			{
				/* preambulul SMPTE 337M (sunet comprimat purtat in 302M): Pa, Pb in aceeasi pereche */
				for (int k = 0; k < 128; k++)
				{
					uint32_t pa = (uint32_t)st[k] >> (32 - biti), pb = (uint32_t)dr[k] >> (32 - biti);
					bool e337 = (biti == 16 && pa == 0xF872 && pb == 0x4E1F)
						|| (biti == 20 && pa == 0x6F872 && pb == 0x54E1F)
						|| (biti == 24 && pa == 0x96F872 && pb == 0xA54E1F);
					if (e337)
					{
						nePcm = true;
						return 0;
					}
				}
			}
		}
		for (int parte = 0; parte < 2; parte++)
		{
			float re[128], im[128];
			const int32_t *s = parte ? dr : st;
			for (int k = 0; k < 128; k++)
			{
				re[k] = (float)(s[k] * (1.0 / 2147483648.0)) * T.fereastra[k];
				im[k] = 0.0f;
			}
			fft128(re, im, T);
			double *e = parte ? eDr : eSt;
			for (int k = 0; k < 64; k++)
				e[k] += (double)re[k] * re[k] + (double)im[k] * im[k];
		}
	}
	for (int k = 0; k < 64; k++)
	{
		a.adauga(STANGA, k, 64, eSt[k] / ferestre);
		a.adauga(DREAPTA, k, 64, eDr[k] / ferestre);
	}
	a.sce = 0;
	a.cpe = 1;
	info.esantionare = 48000;
	info.canale = canale;
	info.lfe = 0;
	info.profil = 0;
	info.biti = biti;
	return 48000;
}

/* ---------------------------------------------------------------- nucleul */

class Nucleu
{
public:
	Aac aac;
	StareAc3 ac3;
	Info inf;
	unsigned bune, rele;
	uint8_t *tampon;

	Nucleu() : bune(0), rele(0)
	{
		memset(&inf, 0, sizeof(inf));
		tampon = new (std::nothrow) uint8_t[CADRU_MAX + CAPAT];
	}
	~Nucleu()
	{
		delete[] tampon;
	}
};

Nucleu *creeaza()
{
	Nucleu *n = new (std::nothrow) Nucleu();
	if (n && !n->tampon)
	{
		delete n;
		return 0;
	}
	return n;
}

void distruge(Nucleu *n)
{
	delete n;
}

void reseteaza(Nucleu *n)
{
	if (!n)
		return;
	n->aac.reset();
	memset(&n->inf, 0, sizeof(n->inf));
	n->bune = n->rele = 0;
}

int cadru(Nucleu *n, int fel, const uint8_t *date, size_t lungime, uint8_t niv[2][BENZI], int *mono)
{
	if (!n || !date || lungime < 4 || lungime > CADRU_MAX)
		return 0;
	const Tabele &T = tabele();
	if (!T.bun)
		return 0;
	memcpy(n->tampon, date, lungime);
	memset(n->tampon + lungime, 0, CAPAT);
	const uint8_t *d = n->tampon;
	uint32_t l = (uint32_t)lungime;
	Acum a;
	a.goleste();
	double calib = 0.0;
	int fs = 0;
	bool ignorat = false;
	switch (fel)
	{
	case FEL_ADTS:
	case FEL_LATM:
	{
		int r = fel == FEL_ADTS ? n->aac.adts(d, l, a) : n->aac.latm(d, l, a);
		if (!r)
			break;
		calib = CALIB_AAC;
		fs = n->aac.esantionare();
		if (fs > n->aac.cfg.fs)
		{
			/* SBR: liniile nucleului acopera numai partea de jos a sunetului auzit */
			int f = fs / n->aac.cfg.fs;
			if (f < 1)
				f = 1;
			for (int p = 0; p < 2; p++)
			{
				double v[BENZI];
				for (int k = 0; k < BENZI; k++)
				{
					v[k] = 0.0;
					for (int j = 0; j < f && k * f + j < BENZI; j++)
						v[k] += a.e[p][k * f + j];
				}
				memcpy(a.e[p], v, sizeof(v));
			}
		}
		if (n->aac.sbr.canale && fs == 2 * n->aac.cfg.fs)
		{
			/* benzile de sus din SBR, pe benzile iesirii (dupa ce miezul a fost adus pe ele) */
			const Sbr &s = n->aac.sbr;
			double f = n->aac.sbrPondere * CALIB_SBR;
			for (int k = 0; k < BENZI; k++)
			{
				if (s.canale == 1)
				{
					a.e[0][k] += f * s.e[0][k];
					a.e[1][k] += f * s.e[0][k];
				}
				else
				{
					a.e[0][k] += f * s.e[0][k];
					a.e[1][k] += f * s.e[1][k];
				}
			}
		}
		n->inf.esantionare = fs;
		n->inf.canale = n->aac.canaleVazute;
		n->inf.lfe = n->aac.lfeVazut;
		n->inf.profil = n->aac.cfg.aot;
		n->inf.sbr = n->aac.cfg.sbr || n->aac.sbrGasit;
		n->inf.ps = n->aac.cfg.ps;
		break;
	}
	case FEL_AC3:
		fs = cadruAc3(d, l, a, n->inf, n->ac3);
		calib = CALIB_AC3;
		break;
	case FEL_EAC3:
		fs = cadruEac3(d, l, a, n->inf, ignorat, n->ac3);
		calib = CALIB_AC3;
		break;
	case FEL_DTS:
		fs = cadruDts(d, l, a, n->inf);
		calib = CALIB_DTS;
		break;
	case FEL_S302M:
	{
		bool altceva = false;
		fs = cadruS302m(d, l, a, n->inf, altceva);
		calib = CALIB_PCM;
		if (altceva)
			n->inf.biti = -1;
		break;
	}
	default:
		break;
	}
	if (!fs)
	{
		if (!ignorat)
			n->rele++;
		return 0;
	}
	n->bune++;
	spreIndici(a, calib, niv);
	*mono = (a.sce == 1 && a.cpe == 0) ? 1 : 0;
	return 1;
}

void info(const Nucleu *n, Info *i)
{
	if (n && i)
		*i = n->inf;
}

void contoare(const Nucleu *n, unsigned *bune, unsigned *rele)
{
	*bune = n ? n->bune : 0;
	*rele = n ? n->rele : 0;
}

/* ---------------------------------------------------------------- textul radio al posturilor AAC (DSE) */

class CititorDse
{
public:
	Aac aac;
	uint8_t tampon[DSE_CADRU_MAX + CAPAT];

	CititorDse()
	{
		aac.numaiElemente = true;
	}
};

CititorDse *creeazaDse()
{
	return new (std::nothrow) CititorDse();
}

void distrugeDse(CititorDse *c)
{
	delete c;
}

size_t lungimeAac(int fel, const uint8_t *d, size_t n)
{
	if (!d)
		return 0;
	if (fel == FEL_LATM)
	{
		if (n < 3 || d[0] != 0x56 || (d[1] & 0xE0) != 0xE0)
			return 0;
		size_t l = 3 + ((((size_t)d[1] & 0x1F) << 8) | d[2]);
		return l >= 4 ? l : 0;
	}
	if (fel == FEL_ADTS)
	{
		if (n < 7 || d[0] != 0xFF || (d[1] & 0xF6) != 0xF0 || ((d[2] >> 2) & 15) > 12)
			return 0;
		size_t l = (((size_t)d[3] & 3) << 11) | ((size_t)d[4] << 3) | (d[5] >> 5);
		return l >= 7 ? l : 0;
	}
	return 0;
}

int dse(CititorDse *c, int fel, const uint8_t *date, size_t lungime, uint8_t *iesire, size_t max)
{
	if (!c || !date || !iesire || lungime < 4 || lungime > DSE_CADRU_MAX || (fel != FEL_ADTS && fel != FEL_LATM))
		return -1;
	const Tabele &T = tabele();
	if (!T.bun)
		return -1;
	/* ca la cadru(): o copie cu zerouri dupa ea (Biti::priveste citeste 4 octeti) */
	memcpy(c->tampon, date, lungime);
	memset(c->tampon + lungime, 0, CAPAT);
	Acum a;
	a.goleste();
	c->aac.dseTampon = iesire;
	c->aac.dseMax = (uint32_t)(max < 0x10000 ? max : 0x10000);
	c->aac.dseLung = 0;
	int r = fel == FEL_ADTS ? c->aac.adts(c->tampon, (uint32_t)lungime, a) : c->aac.latm(c->tampon, (uint32_t)lungime, a);
	int n = (int)c->aac.dseLung;
	c->aac.dseTampon = 0;
	c->aac.dseMax = c->aac.dseLung = 0;
	if (!r && !n)
		return -1;
	return n;
}

}

/* ---------------------------------------------------------------- legatura cu Python */

#ifndef HDS_SPECTRU_FARA_PYTHON

eHdsSpectru::eHdsSpectru()
{
	m_nucleu = hdsspectru::creeaza();
}

eHdsSpectru::~eHdsSpectru()
{
	hdsspectru::distruge(m_nucleu);
}

void eHdsSpectru::reset()
{
	hdsspectru::reseteaza(m_nucleu);
}

static PyObject *tuplu32(const uint8_t *v)
{
	PyObject *t = PyTuple_New(hdsspectru::BENZI);
	if (!t)
		return 0;
	for (int i = 0; i < hdsspectru::BENZI; i++)
		PyTuple_SET_ITEM(t, i, PyLong_FromLong(v[i]));
	return t;
}

PyObject *eHdsSpectru::cadru(int fel, PyObject *date)
{
	char *p = 0;
	Py_ssize_t n = 0;
	if (!m_nucleu || !date)
		Py_RETURN_NONE;
	if (PyBytes_Check(date))
	{
		if (PyBytes_AsStringAndSize(date, &p, &n) < 0)
		{
			PyErr_Clear();
			Py_RETURN_NONE;
		}
	}
	else if (PyByteArray_Check(date))
	{
		p = PyByteArray_AsString(date);
		n = PyByteArray_Size(date);
	}
	else
		Py_RETURN_NONE;
	uint8_t niv[2][hdsspectru::BENZI];
	int mono = 0, r = 0;
	/* bytes nu se schimba cat timp apelantul il tine; bytearray se copiaza inainte de a lasa GIL-ul */
	if (PyBytes_Check(date))
	{
		Py_BEGIN_ALLOW_THREADS
		r = hdsspectru::cadru(m_nucleu, fel, (const uint8_t *)p, (size_t)n, niv, &mono);
		Py_END_ALLOW_THREADS
	}
	else
		r = hdsspectru::cadru(m_nucleu, fel, (const uint8_t *)p, (size_t)n, niv, &mono);
	if (!r)
		Py_RETURN_NONE;
	PyObject *f0 = tuplu32(niv[0]);
	PyObject *f1 = 0;
	if (mono)
	{
		f1 = Py_None;
		Py_INCREF(Py_None);
	}
	else
		f1 = tuplu32(niv[1]);
	if (!f0 || !f1)
	{
		Py_XDECREF(f0);
		Py_XDECREF(f1);
		PyErr_Clear();
		Py_RETURN_NONE;
	}
	PyObject *rez = PyTuple_New(2);
	if (!rez)
	{
		Py_DECREF(f0);
		Py_DECREF(f1);
		PyErr_Clear();
		Py_RETURN_NONE;
	}
	PyTuple_SET_ITEM(rez, 0, f0);
	PyTuple_SET_ITEM(rez, 1, f1);
	return rez;
}

static void pune(PyObject *d, const char *cheie, long v)
{
	PyObject *o = PyLong_FromLong(v);
	if (o)
	{
		PyDict_SetItemString(d, cheie, o);
		Py_DECREF(o);
	}
}

PyObject *eHdsSpectru::info()
{
	PyObject *d = PyDict_New();
	if (!d)
	{
		PyErr_Clear();
		Py_RETURN_NONE;
	}
	hdsspectru::Info i;
	memset(&i, 0, sizeof(i));
	hdsspectru::info(m_nucleu, &i);
	unsigned bune = 0, rele = 0;
	hdsspectru::contoare(m_nucleu, &bune, &rele);
	pune(d, "esantionare", i.esantionare);
	pune(d, "canale", i.canale);
	pune(d, "lfe", i.lfe);
	pune(d, "profil", i.profil);
	pune(d, "sbr", i.sbr);
	pune(d, "ps", i.ps);
	pune(d, "biti", i.biti);
	pune(d, "bune", (long)bune);
	pune(d, "rele", (long)rele);
	return d;
}

#endif
