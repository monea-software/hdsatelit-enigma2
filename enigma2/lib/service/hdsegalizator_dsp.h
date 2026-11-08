/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsegalizator_dsp.h: prelucrarea sunetului pentru egalizatorul din procesor (lib/service/hdsegalizator.cpp).
 * Fisierul nu depinde de enigma2, de GStreamer sau de ALSA, ca sa se poata proba singur pe PC.
 *
 * Sunetul intra ca esantioane float intretesute, stereo, la 48 kHz (asa il da conversia din GStreamer).
 *
 * Egalizator: 10 benzi la cate o octava (31 Hz ... 16 kHz, centrele 1000 * 2^(i-5) Hz), fiecare banda un filtru cu
 * varf (biquad, formulele publice din „Audio EQ Cookbook”), Q = sqrt(2) (latimea de o octava),
 * castig -24..+18 dB. Calculul e pe double, in forma directa I: la 31 Hz polii sunt foarte aproape de cercul unitate,
 * iar float ar aduce zgomot si oscilatii mici. O banda la 0 dB nu se calculeaza dupa stingerea reziduului anterior
 * (istoria ei se tine la zi, ca pornirea ei sa nu pocneasca).
 * Schimbarile nu sar: castigul fiecarei benzi se apropie de tinta cu cel mult PAS_DB pe fiecare bucata de BUCATA cadre
 * (12 dB in ~130 ms), iar coeficientii se refac numai pentru benzile care s-au miscat.
 * Castigul de dinainte (dupa benzi): numai cat cer varfurile adevarate ale sunetului. Varful fiecarei bucati, luat dupa
 * benzi, intra intr-o anvelopa care urca pe loc si coboara in REVENIRE_VARF_S; castigul tine anvelopa sub
 * PLAFON_INAINTE (-1 dBFS), fara sa scada vreodata mai mult decat cea mai mare ridicare a curbei (din raspunsul celor 10
 * filtre, pe PUNCTE_RASPUNS frecvente, la fiecare tinta noua) si fara sa urce peste 1. Asa, la un post cu loc pana la
 * plin (cum sunt cele mai multe), o banda ridicata se aude chiar mai tare, iar restul ramane la fel de tare ca fara
 * egalizator; numai un sunet deja aproape de plin coboara cat trebuie ca sa nu se strice. Ce scapa in primele
 * milisecunde prinde limitatorul.
 * Modul „Noapte”: compresor cu detector RMS (atac 10 ms, revenire 250 ms), prag -30 dBFS, raport 3:1, cot moale de
 * 6 dB, apoi +8 dB: partile incete urca, cele tari coboara.
 * Limitatorul de la capat (varf, fara intarziere): nimic nu trece de PLAFON; lucreaza rar, numai cand „Noapte” sau
 * nivelul ridica sunetul.
 * Rampa de pornire si de oprire: RAMPA_MS, ca intrarea si iesirea din egalizator sa nu pocneasca.
 *
 * Spectru: nivelul sunetului care iese (dupa egalizator, inainte de volum), pe aceleasi 10 benzi, din FFT pe FFT_N
 * esantioane (fereastra Hann), de 10 ori pe secunda, in dBFS; urca pe loc si coboara cu cel mult 60 dB/s, pentru desen.
 *
 * Potrivire: tamponul dintre decodare si placa de sunet, cu potrivirea ceasurilor. Postul trimite esantioanele dupa
 * ceasul lui, placa le cere dupa ceasul ei; diferenta (zeci de milionimi) ar goli sau ar umple tamponul in ore. Citirea
 * trece printr-o interpolare Hermite cu 4 puncte, cu raportul 1 + K * abaterea (plafonat la MAX_ABATERE), deci
 * tamponul ramane in jurul tintei fara sarituri auzite. Golul (postul se opreste) iese ca liniste, cu o coborare
 * scurta a ultimului esantion, apoi se asteapta din nou tinta. Un scriitor si un cititor, pe fire diferite.
 *
 * Canalele TV: sunetul din procesor trebuie sa se auda odata cu imaginea pe care placa o arata dupa
 * ceasul ei. CeasImagine tine PTS-ul imaginii citit periodic de la decodor (VIDEO_GET_PTS, prin servicedvb): afla singur
 * unitatea (driverul poate da ms sau 90 kHz), iar dintre citirile ultimelor secunde o ia pe cea mai apropiata de
 * schimbarea cadrului (cea mai mare diferenta fata de ceasul de perete), ca saltul de un cadru sa nu intre in sincron.
 * SincronImagine compara PTS-ul esantionului care urmeaza sa iasa cu PTS-ul imaginii din clipa in care se va auzi:
 * peste PRAG_S devreme -> tacere, peste PRAG_S tarziu -> aruncare, altfel raportul tamponului (Potrivire) se
 * potriveste incet, fara sarituri auzite.
 */

#ifndef __lib_service_hdsegalizator_dsp_h
#define __lib_service_hdsegalizator_dsp_h

#include <math.h>
#include <string.h>
#include <stdint.h>
#include <atomic>
#include <vector>

namespace hdsegal
{
	enum { BENZI = 10, CANALE = 2, RATA = 48000 };

	static const double CASTIG_MINIM_DB = -24.0;
	static const double CASTIG_MAXIM_DB = 18.0;
	static const double Q_BANDA = 1.41421356237;
	static const int BUCATA = 128;             /* cadre intre doua apropieri de tinta */
	static const double PAS_DB = 0.25;         /* cat se misca o banda pe bucata */
	static const int PUNCTE_RASPUNS = 160;     /* frecvente pentru raspunsul total, 20 Hz ... 20 kHz */
	static const double PLAFON = 0.966;        /* -0,3 dBFS */
	static const double PLAFON_INAINTE = 0.891; /* -1 dBFS: tinta castigului de dinainte, sub limitator */
	static const double REVENIRE_VARF_S = 3.0; /* anvelopa varfurilor coboara cu ~2,9 dB/s */
	static const double RAMPA_MS = 30.0;
	static const int FFT_N = 2048;
	static const int SPECTRU_PAS = 4800;       /* un spectru la 100 ms */
	static const double SPECTRU_MINIM_DB = -90.0;
	static const double ANTI_DENORMAL = 1e-20;
	static const double REZIDUU_OCOLIRE = 1e-12; /* cel mult -240 dBFS: istoria filtrului poate fi inlocuita cu intrarea */

	inline double frecventaBanda(int i)
	{
		return 1000.0 * pow(2.0, (double)(i - 5));
	}

	inline double dbLaLiniar(double db)
	{
		return pow(10.0, db / 20.0);
	}

	inline double limiteaza(double v, double jos, double sus)
	{
		return v < jos ? jos : (v > sus ? sus : v);
	}

	/* ---------------------------------------------------------------- un filtru biquad, forma directa I */
	struct Biquad
	{
		double b0, b1, b2, a1, a2;
		double x1[CANALE], x2[CANALE], y1[CANALE], y2[CANALE];

		Biquad() { identitate(); reseteaza(); }

		void identitate()
		{
			b0 = 1.0;
			b1 = b2 = a1 = a2 = 0.0;
		}

		void reseteaza()
		{
			for (int c = 0; c < CANALE; c++)
				x1[c] = x2[c] = y1[c] = y2[c] = 0.0;
		}

		/* filtru cu varf la f0, castig in dB, factor Q, la rata fs */
		void varf(double f0, double castig_db, double q, double fs)
		{
			/* La 0 dB numaratorul egaleaza numitorul, dar polii raman: reziduul vechi se stinge lin. */
			double A = pow(10.0, castig_db / 40.0);
			double w0 = 2.0 * M_PI * f0 / fs;
			double cw = cos(w0);
			double alfa = sin(w0) / (2.0 * q);
			double a0 = 1.0 + alfa / A;
			b0 = (1.0 + alfa * A) / a0;
			b1 = (-2.0 * cw) / a0;
			b2 = (1.0 - alfa * A) / a0;
			a1 = (-2.0 * cw) / a0;
			a2 = (1.0 - alfa / A) / a0;
		}

		/* modulul raspunsului la frecventa f (in dB) */
		double raspunsDb(double f, double fs) const
		{
			double w = 2.0 * M_PI * f / fs;
			double c1 = cos(w), s1 = sin(w), c2 = cos(2.0 * w), s2 = sin(2.0 * w);
			double nr = b0 + b1 * c1 + b2 * c2, ni = -(b1 * s1 + b2 * s2);
			double dr = 1.0 + a1 * c1 + a2 * c2, di = -(a1 * s1 + a2 * s2);
			double n = nr * nr + ni * ni, d = dr * dr + di * di;
			if (d <= 0.0 || n <= 0.0)
				return 0.0;
			return 10.0 * log10(n / d);
		}

		inline double pas(double x, int c)
		{
			double y = b0 * x + b1 * x1[c] + b2 * x2[c] - a1 * y1[c] - a2 * y2[c];
			x2[c] = x1[c];
			x1[c] = x;
			y2[c] = y1[c];
			y1[c] = y;
			return y;
		}

		/* banda ocolita: istoria urmeaza intrarea (iesirea = intrarea), ca pornirea ei sa plece din starea buna */
		inline void ocolire(double x, int c)
		{
			x2[c] = x1[c];
			x1[c] = x;
			y2[c] = y1[c];
			y1[c] = x;
		}

		bool poateOcoli() const
		{
			for (int c = 0; c < CANALE; c++)
				if (fabs(y1[c] - x1[c]) > REZIDUU_OCOLIRE || fabs(y2[c] - x2[c]) > REZIDUU_OCOLIRE)
					return false;
			return true;
		}
	};

	/* ---------------------------------------------------------------- setarile lantului */
	struct Setari
	{
		double benzi[BENZI];    /* dB, -24..+18 */
		bool noapte;
		int efect;              /* 0 = fara efect, 1..15 in ordinea interfetei */
		double nivel_db;        /* potrivirea tariei fata de sunetul placii, -12..+12 */
		double volum;           /* 0..1, volumul aplicat aici (1 cand il pune placa) */
		bool mut;

		Setari()
		{
			for (int i = 0; i < BENZI; i++)
				benzi[i] = 0.0;
			noapte = false;
			efect = 0;
			nivel_db = 0.0;
			volum = 1.0;
			mut = false;
		}
	};

	/* ---------------------------------------------------------------- FFT radix 2, pe loc */
	inline void fft(std::vector<double> &re, std::vector<double> &im)
	{
		const size_t n = re.size();
		for (size_t i = 1, j = 0; i < n; i++)
		{
			size_t bit = n >> 1;
			for (; j & bit; bit >>= 1)
				j ^= bit;
			j ^= bit;
			if (i < j)
			{
				double t = re[i];
				re[i] = re[j];
				re[j] = t;
				t = im[i];
				im[i] = im[j];
				im[j] = t;
			}
		}
		for (size_t lung = 2; lung <= n; lung <<= 1)
		{
			double unghi = -2.0 * M_PI / (double)lung;
			double wr = cos(unghi), wi = sin(unghi);
			for (size_t i = 0; i < n; i += lung)
			{
				double cr = 1.0, ci = 0.0;
				for (size_t k = 0; k < lung / 2; k++)
				{
					size_t a = i + k, b = i + k + lung / 2;
					double tr = re[b] * cr - im[b] * ci;
					double ti = re[b] * ci + im[b] * cr;
					re[b] = re[a] - tr;
					im[b] = im[a] - ti;
					re[a] += tr;
					im[a] += ti;
					double ncr = cr * wr - ci * wi;
					ci = cr * wi + ci * wr;
					cr = ncr;
				}
			}
		}
	}

	/* ---------------------------------------------------------------- spectrul pe cele 10 benzi */
	class Spectru
	{
	public:
		Spectru(): m_poz(0), m_numarate(0), m_re(FFT_N), m_im(FFT_N), m_fereastra(FFT_N), m_tampon(FFT_N, 0.0),
			m_suma_ferestrei(0.0), m_versiune(0)
		{
			for (int i = 0; i < FFT_N; i++)
			{
				m_fereastra[i] = 0.5 - 0.5 * cos(2.0 * M_PI * i / (FFT_N - 1));
				m_suma_ferestrei += m_fereastra[i];
			}
			for (int b = 0; b < BENZI; b++)
			{
				m_niv[b] = SPECTRU_MINIM_DB;
				m_nivCitit[b].store(SPECTRU_MINIM_DB);
			}
		}

		void adauga(const float *date, int cadre)
		{
			for (int i = 0; i < cadre; i++)
			{
				m_tampon[m_poz] = 0.5 * ((double)date[2 * i] + (double)date[2 * i + 1]);
				m_poz = (m_poz + 1) % FFT_N;
				if (++m_numarate >= SPECTRU_PAS)
				{
					m_numarate = 0;
					calculeaza();
				}
			}
		}

		/* nivelurile in dBFS (o sinusoida la plin = 0); versiunea creste la fiecare calcul */
		void citeste(double niv[BENZI], unsigned *versiune) const
		{
			for (int b = 0; b < BENZI; b++)
				niv[b] = m_nivCitit[b].load();
			if (versiune)
				*versiune = m_versiune.load();
		}

		void goleste()
		{
			for (int i = 0; i < FFT_N; i++)
				m_tampon[i] = 0.0;
			for (int b = 0; b < BENZI; b++)
			{
				m_niv[b] = SPECTRU_MINIM_DB;
				m_nivCitit[b].store(SPECTRU_MINIM_DB);
			}
		}

	private:
		void calculeaza()
		{
			for (int i = 0; i < FFT_N; i++)
			{
				m_re[i] = m_tampon[(m_poz + i) % FFT_N] * m_fereastra[i];
				m_im[i] = 0.0;
			}
			fft(m_re, m_im);
			const double latime = (double)RATA / FFT_N;
			/* o sinusoida la plin (amplitudine 1) are in varful ei (suma_ferestrei / 2)^2 */
			const double norma = 4.0 / (m_suma_ferestrei * m_suma_ferestrei);
			for (int b = 0; b < BENZI; b++)
			{
				double f = frecventaBanda(b);
				int k0 = (int)floor(f / M_SQRT2 / latime);
				int k1 = (int)ceil(f * M_SQRT2 / latime);
				if (k0 < 1)
					k0 = 1;
				if (k1 > FFT_N / 2 - 1)
					k1 = FFT_N / 2 - 1;
				if (k1 < k0)
					k1 = k0;
				double p = 0.0;
				for (int k = k0; k <= k1; k++)
					p += m_re[k] * m_re[k] + m_im[k] * m_im[k];
				/* fereastra Hann imparte energia unei sinusoide pe ~1,5 casute: suma pe banda o aduce inapoi */
				double db = p > 0.0 ? 10.0 * log10(p * norma / 1.5) : SPECTRU_MINIM_DB;
				if (db < SPECTRU_MINIM_DB)
					db = SPECTRU_MINIM_DB;
				if (db >= m_niv[b])
					m_niv[b] = db;
				else
					m_niv[b] = db > m_niv[b] - 6.0 ? db : m_niv[b] - 6.0;
				m_nivCitit[b].store(m_niv[b]);
			}
			m_versiune.fetch_add(1);
		}

		int m_poz, m_numarate;
		std::vector<double> m_re, m_im, m_fereastra, m_tampon;
		double m_suma_ferestrei;
		double m_niv[BENZI];
		std::atomic<double> m_nivCitit[BENZI];
		std::atomic<unsigned> m_versiune;
	};

	/* ---------------------------------------------------------------- efectele proprii, stereo, fara intarzierea caii directe
	 * Memoria se aloca numai la construirea sesiunii, pe firul de control. Cele patru inele se refolosesc;
	 * resetarea invalideaza numai numarul de esantioane scrise, fara golire mare pe firul audio.
	 * La schimbare: 30 ms catre sunetul direct, resetare O(1), 30 ms catre efectul nou. Cererile intermediare
	 * se reunesc in ultima tinta. Calea directa nu se opreste si nu asteapta ecoul/reverberatia.
	 * Reverberatiile folosesc patru intarzieri, amortizare cu un pol si matrice ortogonala /2;
	 * bucla are castig cel mult 0,84, deci energia libera scade. Nu exista biblioteci de efecte.
	 */
	class Efecte
	{
	public:
		enum { NUMAR = 16, CAPACITATE = 16384, LINII = 4 };
		Efecte(): m_memorie(CAPACITATE * LINII), m_cerut(0), m_activ(0), m_mix(0.0),
			m_sin(0.0), m_cos(1.0), m_rotSin(0.0), m_rotCos(1.0), m_feedback(0.0), m_amortizare(0.0),
			m_umed(0.0), m_jos(0.0), m_sus(0.0)
		{
			configureaza(0);
		}

		void seteaza(int efect) { m_cerut = efect >= 0 && efect < NUMAR ? efect : 0; }
		bool activa() const { return m_activ != 0 || m_cerut != 0; }

		/* Intoarce varful pentru detectorul deja existent al castigului de dinainte. */
		double prelucreaza(double *date, int n)
		{
			double varf = 0.0;
			for (int i = 0; i < n; i++)
			{
				pas(date + 2 * i);
				double v = fabs(date[2 * i]) > fabs(date[2 * i + 1]) ? fabs(date[2 * i]) : fabs(date[2 * i + 1]);
				if (v > varf)
					varf = v;
			}
			/* Oscilatorul recursiv nu cere trigonometrie pe esantion si nu deriva in rulari lungi. */
			if (m_activ >= 7 && m_activ <= 11)
			{
				double norma = 1.0 / sqrt(m_sin * m_sin + m_cos * m_cos);
				m_sin *= norma;
				m_cos *= norma;
			}
			return varf;
		}

	private:
		void configureaza(int efect)
		{
			m_activ = efect;
			for (int i = 0; i < LINII; i++)
			{
				m_poz[i] = m_valide[i] = 0;
				m_intarziere[i] = 1;
				m_filtrat[i] = m_f1[i] = m_f2[i] = 0.0;
				for (int c = 0; c < CANALE; c++)
					m_fazare[c][i] = 0.0;
			}
			m_sin = 0.0;
			m_cos = 1.0;
			double hz = 0.0;
			if (efect == 3)
			{
				m_intarziere[0] = 1103; m_intarziere[1] = 1429; m_intarziere[2] = 1693; m_intarziere[3] = 2017;
				m_feedback = 0.55; m_amortizare = 0.42; m_umed = 0.24;
			}
			else if (efect == 4)
			{
				m_intarziere[0] = 2141; m_intarziere[1] = 2909; m_intarziere[2] = 3469; m_intarziere[3] = 4057;
				m_feedback = 0.72; m_amortizare = 0.32; m_umed = 0.32;
			}
			else if (efect == 5)
			{
				m_intarziere[0] = 3911; m_intarziere[1] = 4937; m_intarziere[2] = 6211; m_intarziere[3] = 7919;
				m_feedback = 0.84; m_amortizare = 0.22; m_umed = 0.38;
			}
			else if (efect == 6)
			{
				m_intarziere[0] = 5521; m_intarziere[1] = 6673; m_intarziere[2] = 7993; m_intarziere[3] = 11587;
				m_feedback = 0.69; m_amortizare = 0.18; m_umed = 0.34;
			}
			else if (efect == 7) hz = 0.75;
			else if (efect == 8) hz = 0.23;
			else if (efect == 9) hz = 0.32;
			else if (efect == 10) hz = 5.0;
			else if (efect == 11) hz = 4.2;
			m_rotSin = sin(2.0 * M_PI * hz / RATA);
			m_rotCos = cos(2.0 * M_PI * hz / RATA);
			m_jos = 1.0 - exp(-2.0 * M_PI * (efect == 14 ? 450.0 : 180.0) / RATA);
			m_sus = 1.0 - exp(-2.0 * M_PI * (efect == 14 ? 2300.0 : 4200.0) / RATA);
		}

		inline double citeste(int linie, int inapoi) const
		{
			if (inapoi > m_valide[linie])
				return 0.0;
			int poz = m_poz[linie] - inapoi;
			if (poz < 0)
				poz += CAPACITATE;
			return m_memorie[linie * CAPACITATE + poz];
		}

		inline double fractionar(int linie, double inapoi) const
		{
			int n = (int)inapoi;
			double t = inapoi - n;
			return citeste(linie, n) * (1.0 - t) + citeste(linie, n + 1) * t;
		}

		inline void scrie(int linie, double x)
		{
			/* Limita de siguranta a memoriei nu se atinge cu semnal audio normal. */
			m_memorie[linie * CAPACITATE + m_poz[linie]] = (float)limiteaza(x, -256.0, 256.0);
			if (++m_poz[linie] == CAPACITATE)
				m_poz[linie] = 0;
			if (m_valide[linie] < CAPACITATE)
				m_valide[linie]++;
		}

		void pas(double *date)
		{
			const double pas_mix = 1.0 / (RAMPA_MS * 0.001 * RATA);
			if (m_activ != m_cerut)
			{
				m_mix -= pas_mix;
				if (m_mix <= 0.0)
				{
					m_mix = 0.0;
					configureaza(m_cerut);
				}
			}
			else if (m_activ != 0 && m_mix < 1.0)
			{
				m_mix += pas_mix;
				if (m_mix > 1.0)
					m_mix = 1.0;
			}
			if (!m_activ)
				return;
			double l = date[0], r = date[1], el = l, er = r;
			if (m_activ == 1 || m_activ == 2)
			{
				int d = m_activ == 1 ? 14880 : 13920;
				double a = citeste(0, d), b = citeste(1, d);
				m_filtrat[0] += 0.28 * (a - m_filtrat[0]);
				m_filtrat[1] += 0.28 * (b - m_filtrat[1]);
				/* Si intrarea memoriei urca lin: primul ecou nu incepe cu o muchie dupa 310 ms. */
				scrie(0, m_mix * l + (m_activ == 1 ? 0.38 * m_filtrat[0] : 0.46 * m_filtrat[1]));
				scrie(1, m_mix * r + (m_activ == 1 ? 0.38 * m_filtrat[1] : 0.46 * m_filtrat[0]));
				el = 0.82 * l + 0.32 * a;
				er = 0.82 * r + 0.32 * b;
			}
			else if (m_activ >= 3 && m_activ <= 6)
			{
				for (int j = 0; j < LINII; j++)
					m_filtrat[j] += m_amortizare * (citeste(j, m_intarziere[j]) - m_filtrat[j]);
				double a = m_filtrat[0], b = m_filtrat[1], c = m_filtrat[2], d = m_filtrat[3];
				scrie(0, 0.4 * m_mix * l + m_feedback * 0.5 * (a + b + c + d));
				scrie(1, 0.4 * m_mix * r + m_feedback * 0.5 * (a - b + c - d));
				scrie(2, 0.4 * m_mix * l + m_feedback * 0.5 * (a + b - c - d));
				scrie(3, 0.4 * m_mix * r + m_feedback * 0.5 * (a - b - c + d));
				el = (1.0 - m_umed) * l + m_umed * (a + c);
				er = (1.0 - m_umed) * r + m_umed * (b + d);
				if (m_activ == 6)
				{
					el += 0.14 * citeste(1, 3559);
					er += 0.14 * citeste(0, 5119);
				}
			}
			else if (m_activ == 7 || m_activ == 8 || m_activ == 11)
			{
				double baza = m_activ == 7 ? 600.0 : (m_activ == 8 ? 90.0 : 144.0);
				double adancime = m_activ == 7 ? 180.0 : (m_activ == 8 ? 80.0 : 96.0);
				double a = fractionar(0, baza + adancime * m_sin);
				double b = fractionar(1, baza + adancime * (m_activ == 11 ? m_sin : m_cos));
				scrie(0, m_mix * l + (m_activ == 8 ? 0.3 * a : 0.0));
				scrie(1, m_mix * r + (m_activ == 8 ? 0.3 * b : 0.0));
				/* Vibrato mixat: se pastreaza si aici cale directa fara intarziere (inclusiv la TV). */
				el = m_activ == 11 ? 0.15 * l + 0.85 * a : 0.74 * l + 0.26 * a;
				er = m_activ == 11 ? 0.15 * r + 0.85 * b : 0.74 * r + 0.26 * b;
			}
			else if (m_activ == 9)
			{
				double a = 0.35 + 0.22 * m_sin;
				for (int c = 0; c < CANALE; c++)
				{
					double x = c == 0 ? l : r;
					for (int j = 0; j < LINII; j++)
					{
						double y = -a * x + m_fazare[c][j];
						m_fazare[c][j] = x + a * y;
						x = y;
					}
					if (c == 0) el = 0.65 * l + 0.35 * x;
					else er = 0.65 * r + 0.35 * x;
				}
			}
			else if (m_activ == 10)
			{
				el = l * (0.77 + 0.23 * m_sin);
				er = r * (0.77 + 0.23 * m_sin);
			}
			else if (m_activ == 12)
			{
				el = l + 0.35 * (l - r);
				er = r + 0.35 * (r - l);
			}
			else if (m_activ == 13 || m_activ == 14)
			{
				double x = 0.5 * (l + r);
				m_f1[0] += m_jos * (x - m_f1[0]);
				x -= m_f1[0];
				m_f2[0] += m_sus * (x - m_f2[0]);
				double y = 1.4 * m_f2[0];
				if (m_activ == 13)
					y = y / (1.0 + 0.4 * fabs(y));
				el = er = y;
			}
			else if (m_activ == 15)
			{
				/* Atenueaza centrul peste 180 Hz; basul central ramane. Nu separa orice voce. */
				double mijloc = 0.5 * (l + r), lateral = 0.5 * (l - r);
				m_f1[0] += m_jos * (mijloc - m_f1[0]);
				el = m_f1[0] + lateral;
				er = m_f1[0] - lateral;
			}
			if (m_activ >= 7 && m_activ <= 11)
			{
				double s = m_sin * m_rotCos + m_cos * m_rotSin;
				m_cos = m_cos * m_rotCos - m_sin * m_rotSin;
				m_sin = s;
			}
			date[0] = l + m_mix * (el - l);
			date[1] = r + m_mix * (er - r);
		}

		std::vector<float> m_memorie;
		int m_cerut, m_activ;
		double m_mix;
		int m_poz[LINII], m_valide[LINII], m_intarziere[LINII];
		double m_filtrat[LINII], m_f1[LINII], m_f2[LINII], m_fazare[CANALE][LINII];
		double m_sin, m_cos, m_rotSin, m_rotCos, m_feedback, m_amortizare, m_umed, m_jos, m_sus;
	};

	/* ---------------------------------------------------------------- lantul de prelucrare */
	class Lant
	{
	public:
		Lant(): m_pregain_minim(1.0), m_pregain_tinta(1.0), m_pregain(1.0), m_varf(0.0), m_env(0.0), m_gr(1.0),
			m_lim(1.0), m_fade(0.0), m_fade_tinta(0.0), m_iesire(1.0), m_benziActive(0), m_limitari(0)
		{
			for (int i = 0; i < BENZI; i++)
			{
				m_acum[i] = 0.0;
				m_filtre[i].identitate();
			}
			recalculeazaPregain();
		}

		/* setarile noi (intre doua prelucrari, pe acelasi fir) */
		void seteaza(const Setari &s)
		{
			bool benziNoi = false;
			for (int i = 0; i < BENZI; i++)
			{
				double g = limiteaza(s.benzi[i], CASTIG_MINIM_DB, CASTIG_MAXIM_DB);
				if (g != m_s.benzi[i])
					benziNoi = true;
				m_s.benzi[i] = g;
			}
			m_s.noapte = s.noapte;
			m_s.efect = s.efect >= 0 && s.efect < Efecte::NUMAR ? s.efect : 0;
			m_efecte.seteaza(m_s.efect);
			m_s.nivel_db = limiteaza(s.nivel_db, -12.0, 12.0);
			m_s.volum = limiteaza(s.volum, 0.0, 1.0);
			m_s.mut = s.mut;
			if (benziNoi)
				recalculeazaPregain();
		}

		const Setari &setari() const { return m_s; }

		/* sus = sunetul urca in RAMPA_MS, altfel coboara */
		void rampa(bool sus) { m_fade_tinta = sus ? 1.0 : 0.0; }
		bool tacut() const { return m_fade == 0.0 && m_fade_tinta == 0.0; }

		/* sare direct la tinta (inceputul unui flux: fara apropiere pe benzi, fara rampa pe volum) */
		void aseazaBenzile()
		{
			for (int i = 0; i < BENZI; i++)
			{
				m_acum[i] = m_s.benzi[i];
				m_filtre[i].varf(frecventaBanda(i), m_acum[i], Q_BANDA, RATA);
				m_filtre[i].reseteaza();
			}
			m_pregain = m_pregain_tinta;
			m_iesire = m_s.mut ? 0.0 : dbLaLiniar(m_s.nivel_db) * m_s.volum;
			m_env = 0.0;
			m_gr = m_s.noapte ? dbLaLiniar(8.0) : 1.0;
			m_lim = 1.0;
		}

		/* castigul de dinainte de acum (dupa varfurile sunetului) si cel mai mic posibil (minus cea mai mare ridicare) */
		double pregainDb() const { return 20.0 * log10(m_pregain_tinta); }
		double pregainMinimDb() const { return 20.0 * log10(m_pregain_minim); }
		unsigned limitari() const { return m_limitari; }
		int benziActive() const { return m_benziActive; }

		/* raspunsul total al celor 10 filtre la f (dB), pentru tinta de acum, fara castigul de dinainte */
		double raspunsDb(double f) const
		{
			double s = 0.0;
			for (int i = 0; i < BENZI; i++)
			{
				if (m_s.benzi[i] == 0.0)
					continue;
				Biquad b;
				b.varf(frecventaBanda(i), m_s.benzi[i], Q_BANDA, RATA);
				s += b.raspunsDb(f, RATA);
			}
			return s;
		}

		void prelucreaza(float *date, int cadre)
		{
			int facut = 0;
			while (facut < cadre)
			{
				int n = cadre - facut;
				if (n > BUCATA)
					n = BUCATA;
				apropie();
				bucata(date + 2 * facut, n);
				facut += n;
			}
		}

	private:
		void recalculeazaPregain()
		{
			double maxim = 0.0;
			for (int k = 0; k < PUNCTE_RASPUNS; k++)
			{
				double f = 20.0 * pow(1000.0, (double)k / (PUNCTE_RASPUNS - 1));
				double r = raspunsDb(f);
				if (r > maxim)
					maxim = r;
			}
			m_pregain_minim = dbLaLiniar(-maxim);
			if (m_pregain_tinta < m_pregain_minim)
				m_pregain_tinta = m_pregain_minim;
		}

		/* benzile se apropie de tinta cu cel mult PAS_DB */
		void apropie()
		{
			m_benziActive = 0;
			for (int i = 0; i < BENZI; i++)
			{
				double t = m_s.benzi[i];
				if (m_acum[i] != t)
				{
					double d = t - m_acum[i];
					if (d > PAS_DB)
						d = PAS_DB;
					else if (d < -PAS_DB)
						d = -PAS_DB;
					m_acum[i] += d;
					if (fabs(m_acum[i] - t) < 1e-9)
						m_acum[i] = t;
					m_filtre[i].varf(frecventaBanda(i), m_acum[i], Q_BANDA, RATA);
				}
				if (m_acum[i] != 0.0)
					m_benziActive++;
			}
		}

		void bucata(float *date, int n)
		{
			/* Verificarea reziduului se face o data pe bucata, nu pentru fiecare esantion. */
			bool ocolite[BENZI];
			for (int b = 0; b < BENZI; b++)
				ocolite[b] = m_acum[b] == 0.0 && m_filtre[b].poateOcoli();
			/* intai benzile, cu varful bucatii dupa ele (castigul de dinainte vede varful bucatii pe care o scaleaza) */
			double varf_bucata = 0.0;
			for (int i = 0; i < n; i++)
			{
				double l = (double)date[2 * i] + ANTI_DENORMAL, r = (double)date[2 * i + 1] + ANTI_DENORMAL;
				for (int b = 0; b < BENZI; b++)
				{
					Biquad &f = m_filtre[b];
					if (ocolite[b])
					{
						f.ocolire(l, 0);
						f.ocolire(r, 1);
					}
					else
					{
						l = f.pas(l, 0);
						r = f.pas(r, 1);
					}
				}
				m_lucru[2 * i] = l;
				m_lucru[2 * i + 1] = r;
				double v = fabs(l) > fabs(r) ? fabs(l) : fabs(r);
				if (v > varf_bucata)
					varf_bucata = v;
			}
			/* Fara efect: o singura verificare pe bucata, fara acces la memoria efectelor.
			 * Efectul precede castigul automat, Noapte, Nivel si limitatorul final. */
			if (m_efecte.activa())
				varf_bucata = m_efecte.prelucreaza(m_lucru, n);
			m_varf *= exp(-(double)n / (REVENIRE_VARF_S * RATA));
			if (varf_bucata > m_varf)
				m_varf = varf_bucata;
			m_pregain_tinta = limiteaza(m_varf > PLAFON_INAINTE ? PLAFON_INAINTE / m_varf : 1.0, m_pregain_minim, 1.0);

			/* castigurile scalare trec liniar de la valoarea veche la cea noua pe lungimea bucatii */
			const double pregain0 = m_pregain;
			double pregain1 = m_pregain_tinta;
			const double pas_pre = dbLaLiniar(PAS_DB);
			if (pregain1 > pregain0 * pas_pre)
				pregain1 = pregain0 * pas_pre;
			else if (pregain1 < pregain0 / pas_pre)
				pregain1 = pregain0 / pas_pre;
			m_pregain = pregain1;

			/* volumul si nivelul: in sus cel mult ~1 dB pe bucata, in jos pe loc (liniar pe bucata) */
			const double tinta_iesire = m_s.mut ? 0.0 : dbLaLiniar(m_s.nivel_db) * m_s.volum;
			const double iesire0 = m_iesire;
			double iesire1 = tinta_iesire;
			if (iesire1 > iesire0)
			{
				double sus = iesire0 < 0.01 ? 0.01 : iesire0 * 1.12;
				if (iesire1 > sus)
					iesire1 = sus;
			}
			m_iesire = iesire1;

			const double pas_fade = 1.0 / (RAMPA_MS * 0.001 * RATA);
			const double k_atac = 1.0 - exp(-1.0 / (0.010 * RATA));
			const double k_revenire = 1.0 - exp(-1.0 / (0.250 * RATA));
			const double k_gr = 1.0 - exp(-1.0 / (0.005 * RATA));
			const double k_lim = 1.0 - exp(-1.0 / (0.080 * RATA));
			const bool noapte = m_s.noapte;

			for (int i = 0; i < n; i++)
			{
				double t = (double)(i + 1) / n;
				double l = m_lucru[2 * i], r = m_lucru[2 * i + 1];
				double g = pregain0 + (pregain1 - pregain0) * t;
				l *= g;
				r *= g;
				double tinta_gr = 1.0;
				if (noapte)
				{
					double p = 0.5 * (l * l + r * r);
					m_env += (p > m_env ? k_atac : k_revenire) * (p - m_env);
					double nivel = m_env > 1e-12 ? 10.0 * log10(m_env) : -120.0;
					/* prag -30 dBFS, raport 3:1, cot moale de 6 dB, apoi +8 dB */
					double peste = nivel + 30.0, red = 0.0;
					if (peste > 3.0)
						red = peste * (1.0 - 1.0 / 3.0);
					else if (peste > -3.0)
						red = (1.0 - 1.0 / 3.0) * (peste + 3.0) * (peste + 3.0) / 12.0;
					tinta_gr = dbLaLiniar(8.0 - red);
				}
				m_gr += k_gr * (tinta_gr - m_gr);
				double o = (iesire0 + (iesire1 - iesire0) * t) * m_gr;
				l *= o;
				r *= o;
				/* limitatorul: atac pe loc, revenire in ~80 ms */
				double varf = fabs(l) > fabs(r) ? fabs(l) : fabs(r);
				if (varf * m_lim > PLAFON)
				{
					m_lim = PLAFON / varf;
					m_limitari++;
				}
				else
				{
					m_lim += k_lim * (1.0 - m_lim);
					/* si revenirea trebuie sa respecte plafonul esantionului de acum */
					if (varf * m_lim > PLAFON)
					{
						m_lim = PLAFON / varf;
						m_limitari++;
					}
				}
				l *= m_lim;
				r *= m_lim;
				if (m_fade < m_fade_tinta)
				{
					m_fade += pas_fade;
					if (m_fade > m_fade_tinta)
						m_fade = m_fade_tinta;
				}
				else if (m_fade > m_fade_tinta)
				{
					m_fade -= pas_fade;
					if (m_fade < m_fade_tinta)
						m_fade = m_fade_tinta;
				}
				date[2 * i] = (float)(l * m_fade);
				date[2 * i + 1] = (float)(r * m_fade);
			}
		}

		Setari m_s;
		Efecte m_efecte;
		Biquad m_filtre[BENZI];
		double m_acum[BENZI];
		double m_pregain_minim, m_pregain_tinta, m_pregain, m_varf;
		double m_lucru[BUCATA * CANALE];
		double m_env, m_gr, m_lim, m_fade, m_fade_tinta, m_iesire;
		int m_benziActive;
		unsigned m_limitari;
	};

	/* ---------------------------------------------------------------- PTS pe 33 de biti (90 kHz) */
	const uint64_t MASCA_PTS = ((uint64_t)1 << 33) - 1;

	/* a - b, cu trecerea prin zero a ceasului de 33 de biti: in -2^32 .. 2^32-1 */
	inline int64_t diferentaPts(uint64_t a, uint64_t b)
	{
		int64_t d = (int64_t)((a - b) & MASCA_PTS);
		if (d >= ((int64_t)1 << 32))
			d -= (int64_t)1 << 33;
		return d;
	}

	/* ---------------------------------------------------------------- ceasul imaginii (canalele TV) */
	class CeasImagine
	{
	public:
		static const int FEREASTRA_MS = 3000;     /* citirile din care se alege cea de langa schimbarea cadrului */
		static const int VECHI_MS = 1000;         /* fara citire noua atata timp: ceasul nu se mai stie */
		static const int MASURA_MS = 800;         /* cat se masoara pentru unitate */
		static const int64_t SALT = 45000;        /* 500 ms: alt flux, ceasul porneste din nou */

		CeasImagine() { reseteaza(); }

		void reseteaza()
		{
			m_unitate = 0;
			m_prima_t = -1;
			m_prima = 0;
			m_ref_ok = false;
			m_ref = 0;
			m_n = 0;
			m_ultima_t = -1;
		}

		/* o citire a decodorului: `brut` cum il da driverul, `t_ms` ceasul monoton */
		void citire(long long brut, int64_t t_ms)
		{
			if (brut <= 0)
				return;
			if (m_unitate == 0)
			{
				if (m_prima_t < 0 || t_ms < m_prima_t)
				{
					m_prima_t = t_ms;
					m_prima = brut;
					return;
				}
				if (t_ms - m_prima_t < MASURA_MS)
					return;
				double rata = (double)(brut - m_prima) / (double)(t_ms - m_prima_t);
				if (rata > 0.5 && rata < 1.5)
					m_unitate = 1;
				else if (rata > 45.0 && rata < 135.0)
					m_unitate = 90;
				else
				{
					/* imaginea sta (pauza) sau a sarit: masurarea incepe din nou */
					m_prima_t = t_ms;
					m_prima = brut;
					return;
				}
			}
			uint64_t p90 = ((uint64_t)brut * (uint64_t)(m_unitate == 1 ? 90 : 1)) & MASCA_PTS;
			int64_t off = diferentaPts(p90, ((uint64_t)t_ms * 90u) & MASCA_PTS);
			int64_t abatere = off - (m_ref + cea_mai_buna());
			if (!m_ref_ok || abatere > SALT || abatere < -SALT)
			{
				m_ref = off;
				m_ref_ok = true;
				m_n = 0;
			}
			/* fereastra: cele mai vechi de FEREASTRA_MS ies */
			int k = 0;
			for (int i = 0; i < m_n; i++)
				if (t_ms - m_t[i] <= FEREASTRA_MS)
				{
					m_t[k] = m_t[i];
					m_d[k] = m_d[i];
					k++;
				}
			m_n = k;
			if (m_n == MAX_CITIRI)
			{
				for (int i = 1; i < m_n; i++)
				{
					m_t[i - 1] = m_t[i];
					m_d[i - 1] = m_d[i];
				}
				m_n--;
			}
			m_t[m_n] = t_ms;
			m_d[m_n] = off - m_ref;
			m_n++;
			m_ultima_t = t_ms;
		}

		/* PTS-ul imaginii la clipa `t_ms` (90 kHz, 33 de biti); false cand nu se stie (unitatea, citiri vechi) */
		bool la(int64_t t_ms, uint64_t &pts) const
		{
			if (m_unitate == 0 || !m_ref_ok || m_n == 0 || m_ultima_t < 0 || t_ms - m_ultima_t > VECHI_MS)
				return false;
			pts = (uint64_t)((int64_t)((uint64_t)t_ms * 90u & MASCA_PTS) + m_ref + cea_mai_buna()) & MASCA_PTS;
			return true;
		}

		int unitate() const { return m_unitate; }

	private:
		static const int MAX_CITIRI = 64;

		int64_t cea_mai_buna() const
		{
			if (m_n == 0)
				return 0;
			int64_t m = m_d[0];
			for (int i = 1; i < m_n; i++)
				if (m_d[i] > m)
					m = m_d[i];
			return m;
		}

		int m_unitate;                /* 0 inca nu se stie, 1 ms, 90 = 90 kHz */
		int64_t m_prima_t;
		long long m_prima;
		bool m_ref_ok;
		int64_t m_ref;
		int64_t m_t[MAX_CITIRI], m_d[MAX_CITIRI];
		int m_n;
		int64_t m_ultima_t;
	};

	/* ---------------------------------------------------------------- decizia de sincron (canalele TV) */
	struct SincronImagine
	{
		enum Fapta { MERGE, TACERE, ARUNCA };
		static constexpr double PRAG_S = 0.030;        /* peste atat: tacere sau aruncare; sub atat: raportul */
		static constexpr double K = 0.1;               /* 10 ms -> 1000 de milionimi */
		static constexpr double MAX_ABATERE = 0.002;   /* ca la Potrivire: neauzit */

		Fapta fapta;
		int cadre;            /* la TACERE (cate cadre de tacere inainte de sunet) si ARUNCA (cate se arunca) */
		double raport;        /* la MERGE: cadre de intrare pe cadru de iesire */
		double eroare_s;      /* > 0: sunetul ar iesi devreme */

		/* pts_sunet: PTS-ul esantionului care urmeaza sa intre in placa; intarziere_s: cat trece pana se aude (ALSA si
		   placa); pts_imagine: PTS-ul imaginii acum; potrivire_s: cat mai tarziu sa se auda sunetul (reglajul omului) */
		static SincronImagine decide(uint64_t pts_sunet, double intarziere_s, uint64_t pts_imagine, double potrivire_s)
		{
			SincronImagine d;
			d.eroare_s = (double)diferentaPts(pts_sunet, pts_imagine) / 90000.0 - intarziere_s + potrivire_s;
			d.cadre = 0;
			d.raport = 1.0;
			if (d.eroare_s > PRAG_S)
			{
				d.fapta = TACERE;
				d.cadre = (int)(d.eroare_s * RATA);
			}
			else if (d.eroare_s < -PRAG_S)
			{
				d.fapta = ARUNCA;
				d.cadre = (int)(-d.eroare_s * RATA);
			}
			else
			{
				d.fapta = MERGE;
				d.raport = 1.0 - limiteaza(K * d.eroare_s, -MAX_ABATERE, MAX_ABATERE);
			}
			return d;
		}
	};

	/* ---------------------------------------------------------------- tamponul cu potrivirea ceasurilor */
	class Potrivire
	{
	public:
		static constexpr double K = 0.02;             /* 50 ms peste tinta -> 1000 de milionimi mai repede */
		static constexpr double MAX_ABATERE = 0.002;  /* cel mult 2000 de milionimi (3,5 centi, neauzit) */
		static constexpr double SARITURA_S = 0.35;    /* peste atat deasupra tintei, surplusul se arunca */

		/* capacitate si tinta in cadre */
		Potrivire(int capacitate = RATA * 2, int tinta = RATA * 150 / 1000):
			m_cap(capacitate), m_tinta(tinta), m_tampon((size_t)capacitate * CANALE, 0.0f),
			m_scris(0), m_citit(0), m_poz(0.0), m_raport(1.0), m_umplere(0.0), m_asteapta(true), m_fix(false),
			m_extern(false), m_raport_extern(1.0), m_ultim_l(0.0), m_ultim_r(0.0), m_goluri(0), m_aruncate(0)
		{
			m_ist[0] = m_ist[1] = 0.0f;
		}

		/* scrie cadre (firul care decodeaza); ce nu incape se arunca si se numara */
		void scrie(const float *date, int cadre)
		{
			uint64_t s = m_scris.load(std::memory_order_relaxed), c = m_citit.load(std::memory_order_acquire);
			int liber = m_cap - (int)(s - c) - 1;
			if (liber < 0)
				liber = 0;
			if (cadre > liber)
			{
				m_aruncate.fetch_add(cadre - liber);
				cadre = liber;
			}
			for (int i = 0; i < cadre; i++)
			{
				size_t p = (size_t)((s + i) % m_cap) * CANALE;
				m_tampon[p] = date[2 * i];
				m_tampon[p + 1] = date[2 * i + 1];
			}
			m_scris.store(s + cadre, std::memory_order_release);
		}

		int umplere() const
		{
			return (int)(m_scris.load(std::memory_order_acquire) - m_citit.load(std::memory_order_acquire));
		}

		/* da exact `cadre` cadre de iesire (firul placii de sunet); -> cate au venit din tampon (restul liniste) */
		int citeste(float *iesire, int cadre)
		{
			int disponibil = umplere();
			if (m_asteapta)
			{
				if (disponibil < m_tinta)
				{
					linisteCoborata(iesire, 0, cadre);
					return 0;
				}
				m_asteapta = false;
				m_umplere = disponibil;
				m_poz = 0.0;
			}
			/* abaterea masurata incet (constanta ~2 s), raportul dupa ea */
			m_umplere += (disponibil - m_umplere) * ((double)cadre / (2.0 * RATA));
			double abatere = (m_umplere - m_tinta) / (double)RATA;
			if (abatere > SARITURA_S && !m_extern)
			{
				int arunca = disponibil - m_tinta;
				if (arunca > 0)
				{
					m_citit.fetch_add((uint64_t)arunca, std::memory_order_acq_rel);
					m_aruncate.fetch_add(arunca);
					disponibil -= arunca;
				}
				m_umplere = disponibil;
				abatere = 0.0;
			}
			m_raport = m_fix ? 1.0 : (m_extern ? m_raport_extern : 1.0 + limiteaza(K * abatere, -MAX_ABATERE, MAX_ABATERE));
			int produse = 0;
			for (int i = 0; i < cadre; i++)
			{
				/* Hermite: x-1 (ultimul cadru consumat), x0, x1, x2 */
				if (3 > disponibil)
				{
					m_goluri.fetch_add(1);
					m_asteapta = true;
					linisteCoborata(iesire, i, cadre);
					break;
				}
				double fr = m_poz;
				uint64_t baza = m_citit.load(std::memory_order_relaxed);
				for (int c = 0; c < CANALE; c++)
				{
					double xm1 = m_ist[c];
					double x0 = esantion(baza, 0, c);
					double x1 = esantion(baza, 1, c);
					double x2 = esantion(baza, 2, c);
					double c1 = 0.5 * (x1 - xm1);
					double c2 = xm1 - 2.5 * x0 + 2.0 * x1 - 0.5 * x2;
					double c3 = 0.5 * (x2 - xm1) + 1.5 * (x0 - x1);
					iesire[2 * i + c] = (float)(((c3 * fr + c2) * fr + c1) * fr + x0);
				}
				m_ultim_l = iesire[2 * i];
				m_ultim_r = iesire[2 * i + 1];
				produse++;
				m_poz += m_raport;
				int inainte = (int)m_poz;
				if (inainte > 0)
				{
					m_ist[0] = (float)esantion(baza, inainte - 1, 0);
					m_ist[1] = (float)esantion(baza, inainte - 1, 1);
					m_citit.store(baza + inainte, std::memory_order_release);
					disponibil -= inainte;
					m_poz -= inainte;
				}
			}
			return produse;
		}

		/* incepe din nou (flux nou): tamponul gol, asteapta tinta */
		void goleste()
		{
			m_citit.store(m_scris.load(std::memory_order_acquire), std::memory_order_release);
			m_asteapta = true;
			m_poz = 0.0;
		}

		/* fara potrivirea ceasurilor (sursa fara ceas propriu, de exemplu un fisier): raportul ramane 1 */
		void faraPotrivire() { m_fix = true; }

		/* canalele TV: raportul il da sincronul cu imaginea (SincronImagine), nu umplerea tamponului; saltul peste
		   SARITURA_S nu se mai face aici (il face sincronul, prin arunca) */
		void raportExtern(double r)
		{
			m_extern = true;
			m_raport_extern = limiteaza(r, 1.0 - MAX_ABATERE, 1.0 + MAX_ABATERE);
		}

		/* firul placii: arunca cel mult `cadre` cadre de la inceput (sunetul e in urma imaginii), lasand 3 pentru
		   interpolare; -> cate s-au aruncat */
		int arunca(int cadre)
		{
			int disponibil = umplere() - 3;
			if (cadre > disponibil)
				cadre = disponibil;
			if (cadre <= 0)
				return 0;
			uint64_t baza = m_citit.load(std::memory_order_relaxed) + (uint64_t)cadre;
			m_ist[0] = (float)esantion(baza, -1, 0);
			m_ist[1] = (float)esantion(baza, -1, 1);
			m_citit.store(baza, std::memory_order_release);
			m_aruncate.fetch_add(cadre);
			return cadre;
		}

		/* numarul cadrului care intra urmatorul (scriitorul) si al celui care iese urmatorul (cititorul), de la pornire */
		uint64_t scrise() const { return m_scris.load(std::memory_order_acquire); }
		uint64_t citite() const { return m_citit.load(std::memory_order_acquire); }
		double raport() const { return m_raport; }
		unsigned goluri() const { return m_goluri.load(); }
		unsigned aruncate() const { return m_aruncate.load(); }
		int tinta() const { return m_tinta; }
		bool asteapta() const { return m_asteapta; }

	private:
		double esantion(uint64_t baza, int k, int c) const
		{
			return m_tampon[(size_t)((baza + (uint64_t)(int64_t)k) % (uint64_t)m_cap) * CANALE + c];
		}

		/* ultimul esantion coboara la zero in cateva zeci de cadre, restul liniste (fara treapta care pocneste) */
		void linisteCoborata(float *iesire, int de_la, int cadre)
		{
			for (int i = de_la; i < cadre; i++)
			{
				m_ultim_l *= 0.93;
				m_ultim_r *= 0.93;
				if (fabs(m_ultim_l) < 1e-6)
					m_ultim_l = 0.0;
				if (fabs(m_ultim_r) < 1e-6)
					m_ultim_r = 0.0;
				iesire[2 * i] = (float)m_ultim_l;
				iesire[2 * i + 1] = (float)m_ultim_r;
			}
		}

		int m_cap, m_tinta;
		std::vector<float> m_tampon;
		std::atomic<uint64_t> m_scris, m_citit;
		double m_poz, m_raport, m_umplere;
		bool m_asteapta, m_fix, m_extern;
		double m_raport_extern;
		double m_ultim_l, m_ultim_r;
		float m_ist[CANALE];
		std::atomic<unsigned> m_goluri, m_aruncate;
	};

	/* float -> 16 biti, cu zgomot de rotunjire triunghiular de un bit, taiat la plin */
	class Conversie16
	{
	public:
		Conversie16(): m_stare(22222u) {}

		void converteste(const float *in, int16_t *out, int esantioane)
		{
			for (int i = 0; i < esantioane; i++)
			{
				double z = (aleator() - aleator()) / 4294967296.0;
				long r = lrint((double)in[i] * 32767.0 + z);
				if (r > 32767)
					r = 32767;
				else if (r < -32768)
					r = -32768;
				out[i] = (int16_t)r;
			}
		}

	private:
		double aleator()
		{
			m_stare = m_stare * 1664525u + 1013904223u;
			return (double)m_stare;
		}
		uint32_t m_stare;
	};
}

#endif
