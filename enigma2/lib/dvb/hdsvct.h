/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsvct.h: tabelul ATSC cu numele canalelor (Virtual Channel Table, ATSC A/65): TVCT (table_id 0xC8) si CVCT (0xC9), pe
 * PID-ul de baza PSIP 0x1FFB, langa MGT (0xC7). In America multe transpondere (cablul QAM, unele transpondere de satelit)
 * n-au SDT DVB: fara VCT canalele lor ies cu numele facut din frecventa ("3925V SID 0x01"). Numai functii pure si std, fara
 * enigma2 si fara libdvbsi++ (care n-are VCT), ca sa se probeze singur, pe PC. Folosit de scan.cpp.
 *
 * Forma sectiunii VCT: antetul lung (8 octeti: table_id, section_length, transport_stream_id, versiunea,
 * section_number, last_section_number), protocol_version (0), num_channels_in_section, apoi fiecare canal: short_name
 * 7 x UTF-16 (14 octeti), 4 biti rezervati + major 10 + minor 10 + modulation_mode 8 (4 octeti), carrier_frequency (4),
 * channel_TSID (2), program_number (2), ETM_location 2 / access_controlled 1 / hidden 1 / 2 biti (la CVCT path_select,
 * out_of_band) / hide_guide 1 / 3 rezervati / service_type 6 (2 octeti), source_id (2), 6 rezervati + descriptors_length
 * 10 (2), descriptorii; dupa canale 6 rezervati + additional_descriptors_length 10 si descriptorii; CRC32.
 * Numele lung: extended_channel_name_descriptor (0xA0) cu un multiple_string_structure: number_strings, fiecare sir cu
 * limba (3 octeti) si number_segments, fiecare segment cu compression_type, mode, number_bytes si octetii. Se citesc numai
 * segmentele necomprimate (compression_type 0) in mode 0x00-0x33 (octetul e partea de jos a codului Unicode, mode partea
 * de sus) si 0x3F (UTF-16); orice altceva (Huffman, SCSU, Taiwan) lasa numele scurt.
 *
 * Asteptarea (scan.cpp): VCT-ul se asteapta numai dupa ce a venit pe transponderul acordat o sectiune PSIP buna (MGT sau
 * VCT, cu CRC-ul bun si forma intreaga); fara ea (Europa) nu se asteapta nimic in plus. De la prima sectiune buna VCT-ul
 * are RAGAZ_MS (inmultit la ratele mici, ca celelalte tabele) sa vina intreg, apoi se renunta. Masurat: pe 350 de
 * transpondere reale din Europa PAT, SDT si PMT-urile se termina la jumatate din ele in mai putin de 750 ms de la
 * semnal, deci un ragaz pornit la prindere pentru toate le-ar fi intarziat; dupa A/65 MGT-ul se repeta la cel mult
 * 150 ms si VCT-ul la cel mult 400 ms, deci de la prima sectiune PSIP VCT-ul intreg vine intr-un ciclu.
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */

#ifndef __lib_dvb_hdsvct_h
#define __lib_dvb_hdsvct_h

#include <stdint.h>
#include <stddef.h>
#include <string>
#include <vector>

namespace hdsvct
{

enum
{
	PID_PSIP = 0x1FFB,
	TID_MGT = 0xC7,
	TID_TVCT = 0xC8,
	TID_CVCT = 0xC9,
	TAG_NUME_LUNG = 0xA0,
	RAGAZ_MS = 750,
	MAX_SECTIUNE = 4096,        /* tamponul cititorului de sectiuni; section_length are 12 biti */
	MAX_CANALE = 2048,
	MAX_NUME = 255,             /* octeti UTF-8 */
	PROGRAM_ANALOGIC = 0xFFFF
};

/* CRC-ul MPEG-2 (polinomul 0x04C11DB7, pornit de la 0xFFFFFFFF, fara inversare): peste o sectiune intreaga, cu CRC-ul ei
   la coada, da 0 */
inline uint32_t crc32Mpeg(const uint8_t *d, size_t n)
{
	uint32_t crc = 0xFFFFFFFFu;
	for (size_t i = 0; i < n; ++i)
	{
		crc ^= (uint32_t)d[i] << 24;
		for (int b = 0; b < 8; ++b)
			crc = (crc & 0x80000000u) ? (crc << 1) ^ 0x04C11DB7u : (crc << 1);
	}
	return crc;
}

/* lungimea unei sectiuni lungi (antet, corp si CRC) cand forma si CRC-ul sunt bune, altfel 0; max = cati octeti are
   tamponul */
inline size_t lungimeBuna(const uint8_t *d, size_t max)
{
	if (!d || max < 3)
		return 0;
	if (!(d[1] & 0x80))         /* section_syntax_indicator */
		return 0;
	size_t n = 3 + (((size_t)(d[1] & 0x0F) << 8) | d[2]);
	if (n < 12 || n > max || n > (size_t)MAX_SECTIUNE)
		return 0;
	if (crc32Mpeg(d, n) != 0)
		return 0;
	return n;
}

/* un cod Unicode la coada textului UTF-8; caracterele de control, surogatele singure si codurile fara sens nu intra */
inline void punUtf8(std::string &s, uint32_t c)
{
	if (c < 0x20 || (c >= 0x7F && c < 0xA0) || (c >= 0xD800 && c <= 0xDFFF) || c == 0xFEFF || c == 0xFFFE ||
			c == 0xFFFF || c > 0x10FFFF)
		return;
	if (c < 0x80)
		s += (char)c;
	else if (c < 0x800)
	{
		s += (char)(0xC0 | (c >> 6));
		s += (char)(0x80 | (c & 0x3F));
	}
	else if (c < 0x10000)
	{
		s += (char)(0xE0 | (c >> 12));
		s += (char)(0x80 | ((c >> 6) & 0x3F));
		s += (char)(0x80 | (c & 0x3F));
	}
	else
	{
		s += (char)(0xF0 | (c >> 18));
		s += (char)(0x80 | ((c >> 12) & 0x3F));
		s += (char)(0x80 | ((c >> 6) & 0x3F));
		s += (char)(0x80 | (c & 0x3F));
	}
}

/* fara spatiile de la margini si cel mult MAX_NUME octeti, taiat la marginea unui caracter */
inline std::string curata(const std::string &s)
{
	size_t a = 0, b = s.size();
	while (a < b && s[a] == ' ')
		++a;
	while (b > a && s[b - 1] == ' ')
		--b;
	std::string r = s.substr(a, b - a);
	if (r.size() > (size_t)MAX_NUME)
	{
		size_t n = MAX_NUME;
		while (n > 0 && ((unsigned char)r[n] & 0xC0) == 0x80)
			--n;
		r.resize(n);
		while (!r.empty() && r[r.size() - 1] == ' ')
			r.resize(r.size() - 1);
	}
	return r;
}

/* unitati UTF-16 (octetul de sus intai) la coada textului; la_zero: 0x0000 incheie textul (numele scurt se umple cu el) */
inline void adaugaUtf16(std::string &s, const uint8_t *p, size_t unitati, bool la_zero)
{
	for (size_t i = 0; i < unitati; ++i)
	{
		uint32_t c = ((uint32_t)p[2 * i] << 8) | p[2 * i + 1];
		if (c == 0 && la_zero)
			break;
		if (c >= 0xD800 && c <= 0xDBFF && i + 1 < unitati)
		{
			uint32_t jos = ((uint32_t)p[2 * i + 2] << 8) | p[2 * i + 3];
			if (jos >= 0xDC00 && jos <= 0xDFFF)
			{
				c = 0x10000 + ((c - 0xD800) << 10) + (jos - 0xDC00);
				++i;
			}
		}
		punUtf8(s, c);
	}
}

/* numele scurt: 7 unitati UTF-16 */
inline std::string numeScurt(const uint8_t *p)
{
	std::string s;
	adaugaUtf16(s, p, 7, true);
	return curata(s);
}

/* multiple_string_structure (n octeti): primul sir care se citeste intreg (toate segmentele necomprimate, intr-un mode
   stiut) si nu iese gol; "" daca niciunul sau daca structura iese din cei n octeti */
inline std::string dinSiruri(const uint8_t *p, size_t n)
{
	if (!p || n < 1)
		return std::string();
	int siruri = p[0];
	size_t poz = 1;
	for (int i = 0; i < siruri; ++i)
	{
		if (poz + 4 > n)
			return std::string();
		int segmente = p[poz + 3];          /* dupa limba (3 octeti) */
		poz += 4;
		std::string text;
		bool bun = true;
		for (int j = 0; j < segmente; ++j)
		{
			if (poz + 3 > n)
				return std::string();
			int compresie = p[poz], mod = p[poz + 1];
			size_t lung = p[poz + 2];
			poz += 3;
			if (poz + lung > n)
				return std::string();
			const uint8_t *o = p + poz;
			if (compresie != 0)
				bun = false;
			else if (mod <= 0x33)
			{
				for (size_t k = 0; k < lung; ++k)
					punUtf8(text, ((uint32_t)mod << 8) | o[k]);
			}
			else if (mod == 0x3F && !(lung & 1))
				adaugaUtf16(text, o, lung / 2, false);
			else
				bun = false;
			poz += lung;
		}
		if (bun)
		{
			text = curata(text);
			if (!text.empty())
				return text;
		}
	}
	return std::string();
}

/* numele lung din descriptorii unui canal (extended_channel_name_descriptor), "" daca nu e */
inline std::string numeLung(const uint8_t *p, size_t n)
{
	size_t poz = 0;
	while (poz + 2 <= n)
	{
		int tag = p[poz];
		size_t lung = p[poz + 1];
		if (poz + 2 + lung > n)
			break;
		if (tag == TAG_NUME_LUNG)
		{
			std::string s = dinSiruri(p + poz + 2, lung);
			if (!s.empty())
				return s;
		}
		poz += 2 + lung;
	}
	return std::string();
}

struct Canal
{
	int major, minor;
	int tsid;                   /* channel_TSID: fluxul in care e canalul */
	int program;                /* program_number = service_id; 0xFFFF canal analogic, 0 neatribuit */
	int tip;                    /* service_type: 1 analogic, 2 televiziune, 3 radio, 4 date */
	bool ascuns;                /* hidden */
	std::string scurt, lung;
};

struct Sectiune
{
	int tabel, tsid, versiune, numar, ultima;
	std::vector<Canal> canale;
};

/* o sectiune TVCT sau CVCT intreaga si buna (CRC, current_next_indicator 1, protocol_version 0, toate lungimile in
   sectiune); altfel false */
inline bool citesteVct(const uint8_t *d, size_t max, Sectiune &s)
{
	size_t n = lungimeBuna(d, max);
	if (!n || (d[0] != TID_TVCT && d[0] != TID_CVCT))
		return false;
	if (!(d[5] & 0x01) || d[8] != 0 || d[6] > d[7])
		return false;
	size_t sfarsit = n - 4;     /* fara CRC */
	if (sfarsit < 12)
		return false;
	s.tabel = d[0];
	s.tsid = (d[3] << 8) | d[4];
	s.versiune = (d[5] >> 1) & 0x1F;
	s.numar = d[6];
	s.ultima = d[7];
	s.canale.clear();
	int numar_canale = d[9];
	size_t poz = 10;
	for (int i = 0; i < numar_canale; ++i)
	{
		if (poz + 32 > sfarsit)
			return false;
		const uint8_t *c = d + poz;
		Canal k;
		k.scurt = numeScurt(c);
		k.major = ((c[14] & 0x0F) << 6) | (c[15] >> 2);
		k.minor = ((c[15] & 0x03) << 8) | c[16];
		k.tsid = (c[22] << 8) | c[23];
		k.program = (c[24] << 8) | c[25];
		k.ascuns = (c[26] & 0x10) != 0;
		k.tip = c[27] & 0x3F;
		size_t descriptori = ((size_t)(c[30] & 0x03) << 8) | c[31];
		poz += 32;
		if (poz + descriptori > sfarsit)
			return false;
		k.lung = numeLung(d + poz, descriptori);
		poz += descriptori;
		s.canale.push_back(k);
	}
	if (poz + 2 > sfarsit)
		return false;
	size_t adaugati = ((size_t)(d[poz] & 0x03) << 8) | d[poz + 1];
	return poz + 2 + adaugati <= sfarsit;
}

/* o sectiune MGT intreaga si buna (aceleasi verificari, tabelele anuntate si descriptorii in sectiune) */
inline bool mgtBun(const uint8_t *d, size_t max)
{
	size_t n = lungimeBuna(d, max);
	if (!n || d[0] != TID_MGT || !(d[5] & 0x01) || d[8] != 0)
		return false;
	size_t sfarsit = n - 4;
	if (sfarsit < 11)
		return false;
	int tabele = (d[9] << 8) | d[10];
	size_t poz = 11;
	for (int i = 0; i < tabele; ++i)
	{
		/* table_type 2, PID 2, versiunea 1, number_bytes 4, table_type_descriptors_length 2 */
		if (poz + 11 > sfarsit)
			return false;
		size_t descriptori = ((size_t)(d[poz + 9] & 0x0F) << 8) | d[poz + 10];
		poz += 11 + descriptori;
		if (poz > sfarsit)
			return false;
	}
	if (poz + 2 > sfarsit)
		return false;
	size_t descriptori = ((size_t)(d[poz] & 0x0F) << 8) | d[poz + 1];
	return poz + 2 + descriptori <= sfarsit;
}

/* numele de pus pe canal: cel lung (descriptorul 0xA0) daca e, altfel cel scurt */
inline std::string numeCanal(const Canal &c)
{
	return !c.lung.empty() ? c.lung : c.scurt;
}

/* numele din VCT castiga numai cand serviciul n-are nume din SDT: gasit numai in PAT/PMT (numele facut din frecventa)
   sau cu numele din SDT gol; un nume adevarat din SDT ramane */
inline bool vctCastiga(bool din_sdt, const std::string &nume_acum)
{
	return !din_sdt || curata(nume_acum).empty();
}

/* numele facut de scanare din frecventa pentru un serviciu gasit numai in PAT (scan.cpp: "%d%c SID 0x%02x" pe satelit,
   cu H sau V, "%d SID 0x%02x" pe cablu si terestru) */
inline bool numeDinFrecventa(const std::string &n)
{
	size_t i = 0, cifre = 0;
	while (i < n.size() && n[i] >= '0' && n[i] <= '9')
		++i, ++cifre;
	if (!cifre)
		return false;
	if (i < n.size() && (n[i] == 'H' || n[i] == 'V'))
		++i;
	static const char sid[] = " SID 0x";
	if (n.compare(i, sizeof(sid) - 1, sid) != 0)
		return false;
	i += sizeof(sid) - 1;
	size_t hexa = 0;
	while (i < n.size() && ((n[i] >= '0' && n[i] <= '9') || (n[i] >= 'a' && n[i] <= 'f') || (n[i] >= 'A' && n[i] <= 'F')))
		++i, ++hexa;
	return hexa > 0 && i == n.size();
}

/* In lista de canale (insertInto): numele din VCT al unui serviciu deja stiut inlocuieste numele de acum numai cand acesta
   e gol sau facut din frecventa; un nume bun (de pilda din SDT-ul unei cautari de dinainte) ramane. Pe un transponder fara
   SDT la aceasta cautare (cablul american, transponderele numai ATSC) numele din lista poate veni numai din VCT sau din
   frecventa: acolo inlocuieste orice nume, ca o redenumire facuta de post in VCT sa ajunga in lista. */
inline bool vctInlocuiesteInLista(const std::string &nume_lista, bool transponder_fara_sdt)
{
	return transponder_fara_sdt || curata(nume_lista).empty() || numeDinFrecventa(nume_lista);
}

/* canalul VCT al serviciului sid din acest flux: program_number = sid si channel_TSID = TSID-ul fluxului (cel din antetul
   VCT sau cel din PAT, < 0 = necunoscut). Un canal din alt flux (VCT-ul poate anunta si canalele altor frecvente) sau unul
   analogic nu se ia. */
inline const Canal *canalPentru(const std::vector<Canal> &canale, int sid, int tsid_vct, int tsid_pat)
{
	if (sid <= 0 || sid >= PROGRAM_ANALOGIC)
		return 0;
	for (size_t i = 0; i < canale.size(); ++i)
	{
		const Canal &c = canale[i];
		if (c.program == sid && (c.tsid == tsid_vct || (tsid_pat >= 0 && c.tsid == tsid_pat)))
			return &c;
	}
	return 0;
}

/* VCT-ul transponderului de acum: sectiunile venite pe PID-ul PSIP, in ordinea sosirii, cu ora lor (ms de la acordare) */
class Colector
{
	struct Tabel
	{
		int versiune, ultima, tsid, primite;
		std::vector<bool> are;
		std::vector<std::vector<Canal> > canale;
	};
	Tabel m_tabel[2];           /* 0 TVCT, 1 CVCT */
	bool m_armat;
	long m_armat_ms;
	int m_complet;              /* -1, sau tabelul intreg (0 TVCT, 1 CVCT): primul intreg ramane */
	std::vector<Canal> m_canale;

	static void golesteTabel(Tabel &t)
	{
		t.versiune = t.ultima = t.tsid = -1;
		t.primite = 0;
		t.are.clear();
		t.canale.clear();
	}
public:
	/* ce a facut o sectiune (biti): a pornit asteptarea, a incheiat VCT-ul */
	enum { NIMIC = 0, ARMAT = 1, COMPLET = 2 };

	Colector()
	{
		goleste();
	}

	void goleste()
	{
		golesteTabel(m_tabel[0]);
		golesteTabel(m_tabel[1]);
		m_armat = false;
		m_armat_ms = -1;
		m_complet = -1;
		m_canale.clear();
	}

	/* o sectiune de pe PID-ul PSIP; numai MGT si VCT bune conteaza, orice altceva (STT, RRT, sectiuni stricate) nu */
	int adauga(const uint8_t *d, size_t max, long acum_ms)
	{
		int r = NIMIC;
		if (m_complet >= 0 || !d)
			return r;
		Sectiune s;
		bool vct = citesteVct(d, max, s);
		if (!vct && !mgtBun(d, max))
			return r;
		if (!m_armat)
		{
			m_armat = true;
			m_armat_ms = acum_ms;
			r |= ARMAT;
		}
		if (!vct)
			return r;
		int i = s.tabel == TID_CVCT ? 1 : 0;
		Tabel &t = m_tabel[i];
		if (t.versiune != s.versiune || t.ultima != s.ultima || t.tsid != s.tsid)
		{
			/* alta versiune (sau alt tabel pe acelasi PID): se strange de la capat */
			golesteTabel(t);
			t.versiune = s.versiune;
			t.ultima = s.ultima;
			t.tsid = s.tsid;
			t.are.assign(s.ultima + 1, false);
			t.canale.assign(s.ultima + 1, std::vector<Canal>());
		}
		if (!t.are[s.numar])
		{
			t.are[s.numar] = true;
			t.primite++;
		}
		t.canale[s.numar] = s.canale;
		if (t.primite == t.ultima + 1)
		{
			m_complet = i;
			m_canale.clear();
			for (size_t k = 0; k < t.canale.size(); ++k)
				for (size_t j = 0; j < t.canale[k].size() && m_canale.size() < (size_t)MAX_CANALE; ++j)
					m_canale.push_back(t.canale[k][j]);
			r |= COMPLET;
		}
		return r;
	}

	bool armat() const { return m_armat; }
	long armatMs() const { return m_armat_ms; }
	bool complet() const { return m_complet >= 0; }
	int tabel() const { return m_complet < 0 ? -1 : (m_complet ? TID_CVCT : TID_TVCT); }
	int tsid() const { return m_complet < 0 ? -1 : m_tabel[m_complet].tsid; }
	const std::vector<Canal> &canale() const { return m_canale; }

	/* termenul trecut: asteptarea pornita, VCT-ul inca neintreg, ragaz_ms trecute de la prima sectiune buna */
	bool expirat(long acum_ms, long ragaz_ms) const
	{
		return m_armat && m_complet < 0 && acum_ms - m_armat_ms >= ragaz_ms;
	}
};

}

#endif
