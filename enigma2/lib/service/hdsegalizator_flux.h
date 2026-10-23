/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsegalizator_flux.h: citirea fluxurilor audio pentru egalizatorul din procesor (lib/service/hdsegalizator.cpp).
 * Fisierul nu depinde de enigma2, de GStreamer sau de ALSA, ca sa se poata proba singur pe PC.
 *
 * - debitMpeg(): debitul unui flux MPEG audio (MP1/MP2/MP3) din antetul cadrelor (indicele de debit), numai cand dupa
 *   cadru urmeaza alt antet la distanta lungimii lui (un 0xFFF oarecare din date nu se ia drept antet).
 * - LatmLaAdts: un cadru LOAS (sincronizarea 0x2B7 + AudioMuxElement cu configuratia in flux, ISO/IEC 14496-3 1.7.3)
 *   -> cadre ADTS. Configuratia (StreamMuxConfig cu AudioSpecificConfig) se citeste cand vine si se tine minte pentru
 *   cadrele cu useSameStreamMux; fiecare subcadru (AAC brut, care nu incepe neaparat la margine de octet) primeste un
 *   antet ADTS de 7 octeti, fara CRC. Asa un decodor care stie numai ADTS (faad) decodeaza si posturile LATM.
 *   Se primeste: un singur program cu un singur strat, frameLengthType 0, obiectul audio al miezului 1..4 (Main, LC,
 *   SSR, LTP), cadre de 1024 de esantioane, configuratia de canale 1..7. HE-AAC (SBR / PS semnalate explicit) trece
 *   cu obiectul miezului, iar decodorul gaseste SBR in cadre (semnalarea implicita). Altfel nesuportat() spune de ce
 *   nu (atunci ramane decodorul LATM, daca imaginea il are).
 */

#ifndef __lib_service_hdsegalizator_flux_h
#define __lib_service_hdsegalizator_flux_h

#include <stddef.h>
#include <stdint.h>
#include <vector>

namespace hdsegal
{
	/* ---------------------------------------------------------------- MPEG audio: debitul din antet */

	/* un antet MPEG audio la d[0..3] -> debitul (kbit/s) si lungimea cadrului (octeti), sau false */
	inline bool antetMpeg(const uint8_t *d, int &kbit, int &lungime)
	{
		static const short debite[2][3][15] = {
			/* MPEG-1: stratul I, II, III */
			{ { 0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448 },
			  { 0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384 },
			  { 0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320 } },
			/* MPEG-2 si 2.5 (esantionarea injumatatita): stratul I, II, III */
			{ { 0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256 },
			  { 0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160 },
			  { 0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160 } } };
		static const int esantionari[3] = { 44100, 48000, 32000 };
		if (d[0] != 0xFF || (d[1] & 0xE0) != 0xE0)
			return false;
		int versiune = (d[1] >> 3) & 3;     /* 0 = 2.5, 1 = rezervat, 2 = MPEG-2, 3 = MPEG-1 */
		int strat = (d[1] >> 1) & 3;        /* 1 = III, 2 = II, 3 = I */
		int idx = d[2] >> 4, sr = (d[2] >> 2) & 3, umplere = (d[2] >> 1) & 1;
		if (versiune == 1 || strat == 0 || idx == 0 || idx == 15 || sr == 3)
			return false;
		int s = 3 - strat;                  /* 0 = I, 1 = II, 2 = III */
		int v = versiune == 3 ? 0 : 1;
		kbit = debite[v][s][idx];
		int rata = esantionari[sr] >> (versiune == 3 ? 0 : (versiune == 2 ? 1 : 2));
		if (s == 0)
			lungime = (12 * kbit * 1000 / rata + umplere) * 4;
		else if (s == 2 && v == 1)
			lungime = 72 * kbit * 1000 / rata + umplere;
		else
			lungime = 144 * kbit * 1000 / rata + umplere;
		return lungime > 4;
	}

	/* debitul (kbit/s) al primului cadru confirmat de antetul cadrului urmator, sau 0 */
	inline int debitMpeg(const uint8_t *d, size_t n)
	{
		for (size_t i = 0; i + 4 <= n; i++)
		{
			int kbit, lungime;
			if (!antetMpeg(d + i, kbit, lungime))
				continue;
			size_t urm = i + (size_t)lungime;
			int kbit2, lungime2;
			if (urm + 4 <= n && antetMpeg(d + urm, kbit2, lungime2) && ((d[i + 1] ^ d[urm + 1]) & 0xFE) == 0)
				return kbit;
		}
		return 0;
	}

	/* ---------------------------------------------------------------- citirea pe biti */
	class Biti
	{
	public:
		Biti(const uint8_t *d, size_t n): m_d(d), m_n(n * 8), m_poz(0), m_rau(false) {}

		uint32_t ia(int k)
		{
			uint32_t v = 0;
			for (int i = 0; i < k; i++)
			{
				if (m_poz >= m_n)
				{
					m_rau = true;
					return 0;
				}
				v = (v << 1) | ((m_d[m_poz >> 3] >> (7 - (m_poz & 7))) & 1);
				m_poz++;
			}
			return v;
		}

		void sari(size_t k)
		{
			if (m_poz + k > m_n)
			{
				m_rau = true;
				m_poz = m_n;
			}
			else
				m_poz += k;
		}

		size_t pozitie() const { return m_poz; }
		size_t ramasi() const { return m_n > m_poz ? m_n - m_poz : 0; }
		bool rau() const { return m_rau; }

	private:
		const uint8_t *m_d;
		size_t m_n, m_poz;
		bool m_rau;
	};

	/* ---------------------------------------------------------------- LOAS / LATM -> ADTS */

	/* ce ia antetul ADTS din AudioSpecificConfig */
	struct ConfigAac
	{
		int profil;          /* obiectul audio al miezului - 1 (0 Main, 1 LC, 2 SSR, 3 LTP) */
		int idx_esantionare; /* 0..12 */
		int canale;          /* 1..7 */
		bool sbr, ps;        /* semnalate explicit */
		ConfigAac(): profil(-1), idx_esantionare(-1), canale(-1), sbr(false), ps(false) {}
	};

	class LatmLaAdts
	{
	public:
		LatmLaAdts(): m_are_config(false), m_nesuportat(false), m_subcadre(0), m_cadre_facute(0) {}

		/* un cadru LOAS intreg (cu cei 3 octeti de sincronizare si lungime) -> cadrele ADTS adaugate in `adts`;
		   -> numarul de cadre ADTS scrise (0: fara configuratie inca, sau configuratie nesuportata) */
		int cadru(const uint8_t *loas, size_t n, std::vector<uint8_t> &adts)
		{
			if (n < 4 || loas[0] != 0x56 || (loas[1] & 0xE0) != 0xE0)
				return 0;
			size_t lungime = (((size_t)loas[1] & 0x1F) << 8) | loas[2];
			if (lungime + 3 > n)
				return 0;
			Biti b(loas + 3, lungime);
			/* useSameStreamMux = 0: configuratia vine in cadru. Un cadru stricat se sare si configuratia de dinainte
			   ramane; una nesuportata o uita. */
			if (!b.ia(1) && !citesteConfig(b))
			{
				if (m_nesuportat)
					m_are_config = false;
				return 0;
			}
			if (!m_are_config)
				return 0;
			int scrise = 0;
			for (int sub = 0; sub <= m_subcadre; sub++)
			{
				/* PayloadLengthInfo (allStreamsSameTimeFraming, frameLengthType 0): octeti adunati cat sunt 255 */
				size_t octeti = 0;
				uint32_t t;
				do
				{
					t = b.ia(8);
					octeti += t;
				} while (t == 255 && !b.rau());
				if (b.rau() || octeti == 0 || octeti + 7 > 8191 || octeti * 8 > b.ramasi())
					break;
				size_t inceput = adts.size();
				adts.resize(inceput + 7 + octeti);
				antetAdts(&adts[inceput], 7 + octeti);
				for (size_t k = 0; k < octeti; k++)
					adts[inceput + 7 + k] = (uint8_t)b.ia(8);
				scrise++;
			}
			m_cadre_facute += scrise;
			return scrise;
		}

		bool areConfig() const { return m_are_config; }
		/* s-a vazut o configuratie pe care ADTS nu o poate duce */
		bool nesuportat() const { return m_nesuportat; }
		const ConfigAac &config() const { return m_asc; }
		unsigned long cadreFacute() const { return m_cadre_facute; }

	private:
		static uint32_t valoareLatm(Biti &b)
		{
			int octeti = (int)b.ia(2) + 1;
			uint32_t v = 0;
			for (int i = 0; i < octeti; i++)
				v = (v << 8) | b.ia(8);
			return v;
		}

		static int obiectAudio(Biti &b)
		{
			int o = (int)b.ia(5);
			return o == 31 ? 32 + (int)b.ia(6) : o;
		}

		/* AudioSpecificConfig pana la sfarsitul GASpecificConfig; ce urmeaza (daca e) sare cel care stie lungimea */
		static bool citesteAsc(Biti &b, ConfigAac &c)
		{
			c = ConfigAac();
			int obiect = obiectAudio(b);
			int idx = (int)b.ia(4);
			if (idx == 15)
				b.ia(24);
			int canale = (int)b.ia(4);
			if (obiect == 5 || obiect == 29)
			{
				c.sbr = true;
				c.ps = obiect == 29;
				if (b.ia(4) == 15)           /* esantionarea de dupa SBR */
					b.ia(24);
				obiect = obiectAudio(b);
			}
			if (obiect < 1 || obiect > 4 || idx > 12 || canale < 1 || canale > 7)
				return false;
			/* GASpecificConfig: frameLengthFlag (cadrele de 960 nu se pot spune in ADTS), dependsOnCoreCoder,
			   extensionFlag (numai la obiectele ER, care nu merg in ADTS) */
			if (b.ia(1))
				return false;
			if (b.ia(1))
				b.ia(14);
			if (b.ia(1) || b.rau())
				return false;
			c.profil = obiect - 1;
			c.idx_esantionare = idx;
			c.canale = canale;
			return true;
		}

		/* StreamMuxConfig -> false la o configuratie care nu se poate duce in ADTS (m_nesuportat) sau la un cadru stricat */
		bool citesteConfig(Biti &b)
		{
			m_nesuportat = false;
			int versiune = (int)b.ia(1);
			if (versiune && b.ia(1))          /* audioMuxVersionA */
			{
				m_nesuportat = true;
				return false;
			}
			if (versiune)
				valoareLatm(b);               /* taraBufferFullness */
			int acelasi_timp = (int)b.ia(1);
			int subcadre = (int)b.ia(6);
			int programe = (int)b.ia(4);
			int straturi = (int)b.ia(3);
			if (!acelasi_timp || programe != 0 || straturi != 0)
			{
				m_nesuportat = true;
				return false;
			}
			ConfigAac c;
			if (versiune)
			{
				uint32_t lung = valoareLatm(b);
				size_t start = b.pozitie();
				if (!citesteAsc(b, c))
				{
					m_nesuportat = true;
					return false;
				}
				size_t folositi = b.pozitie() - start;
				if (lung < folositi)
					return false;
				b.sari(lung - folositi);
			}
			else if (!citesteAsc(b, c))
			{
				m_nesuportat = true;
				return false;
			}
			if (b.ia(3) != 0)                 /* frameLengthType */
			{
				m_nesuportat = true;
				return false;
			}
			b.ia(8);                          /* latmBufferFullness */
			if (b.ia(1))                      /* otherDataPresent */
			{
				if (versiune)
					valoareLatm(b);
				else
				{
					uint32_t esc;
					do
					{
						esc = b.ia(1);
						b.ia(8);
					} while (esc && !b.rau());
				}
			}
			if (b.ia(1))                      /* crcCheckPresent */
				b.ia(8);
			if (b.rau())
				return false;
			m_asc = c;
			m_subcadre = subcadre;
			m_are_config = true;
			return true;
		}

		void antetAdts(uint8_t *h, size_t lungime) const
		{
			h[0] = 0xFF;
			h[1] = 0xF1;                      /* MPEG-4, stratul 0, fara CRC */
			h[2] = (uint8_t)((m_asc.profil << 6) | (m_asc.idx_esantionare << 2) | ((m_asc.canale >> 2) & 1));
			h[3] = (uint8_t)(((m_asc.canale & 3) << 6) | ((lungime >> 11) & 3));
			h[4] = (uint8_t)((lungime >> 3) & 0xFF);
			h[5] = (uint8_t)(((lungime & 7) << 5) | 0x1F);   /* plinul tamponului 0x7FF (debit variabil) */
			h[6] = 0xFC;                                     /* ... si un singur bloc de date in cadru */
		}

		ConfigAac m_asc;
		bool m_are_config, m_nesuportat;
		int m_subcadre;
		unsigned long m_cadre_facute;
	};
}

#endif
