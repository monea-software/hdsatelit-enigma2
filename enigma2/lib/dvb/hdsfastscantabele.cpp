/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsfastscantabele.cpp: citirea tabelelor FastScan FNT (0xBC) si FST (0xBD), vezi hdsfastscantabele.h. Sintaxa sectiunii
 * lungi si a descriptorilor 0x40 (numele retelei), 0x41 (lista serviciilor), 0x43 (livrarea prin satelit) si 0x48
 * (serviciul): ETSI EN 300 468. Descriptorul 0x83 al numerelor de canal are aici forma tabelelor FastScan: 4 octeti pe canal,
 * sid pe 16 biti, apoi un cuvant de 16 biti cu semnul „ascuns” pe bitul 14 si numarul pe bitii 0-13.
 */

#include <lib/dvb/hdsfastscantabele.h>

namespace hdsfastscan
{

static uint16_t r16(const uint8_t *p)
{
	return (uint16_t)((p[0] << 8) | p[1]);
}

static unsigned int lungime12(const uint8_t *p)
{
	return r16(p) & 0x0fff;
}

static unsigned int pid13(const uint8_t *p)
{
	return r16(p) & 0x1fff;
}

/* cifrele BCD din n semi-octeti, incepand cu semi-octetul de sus al lui p[0] */
static unsigned int bcd(const uint8_t *p, int semiocteti)
{
	unsigned int v = 0;
	for (int i = 0; i < semiocteti; ++i)
	{
		unsigned int c = (i & 1) ? (p[i / 2] & 0x0f) : (p[i / 2] >> 4);
		v = v * 10 + (c > 9 ? 9 : c);
	}
	return v;
}

uint32_t crc32(const uint8_t *date, size_t lungime)
{
	uint32_t crc = 0xffffffff;
	for (size_t i = 0; i < lungime; ++i)
	{
		crc ^= (uint32_t)date[i] << 24;
		for (int b = 0; b < 8; ++b)
			crc = (crc & 0x80000000) ? (crc << 1) ^ 0x04c11db7 : (crc << 1);
	}
	return crc;
}

size_t lungimeSectiune(const uint8_t *s, size_t lungime)
{
	if (lungime < 3)
		return 0;
	size_t total = 3 + lungime12(s + 1);
	return total <= lungime ? total : 0;
}

int pozitieOrbitala(uint16_t valoare, bool est)
{
	uint8_t b[2] = { (uint8_t)(valoare >> 8), (uint8_t)(valoare & 0xff) };
	int poz = (int)bcd(b, 4);
	if (poz > 1800)
		poz = 1800;
	if (poz && !est)
		poz = 3600 - poz;
	return poz;
}

bool citesteLivrareSatelit(const uint8_t *d, size_t lungime, Transponder &tp)
{
	if (lungime < 13 || d[0] != 0x43 || d[1] < 11 || (size_t)d[1] + 2 > lungime)
		return false;
	tp.frecventa = bcd(d + 2, 8) * 10;
	tp.pozitie = pozitieOrbitala(r16(d + 6), (d[8] & 0x80) != 0);
	tp.polarizare = (d[8] >> 5) & 0x03;
	tp.rolloff = (d[8] >> 3) & 0x03;
	tp.sistem = (d[8] >> 2) & 0x01;
	tp.modulatie = d[8] & 0x03;
	/* DVB-S nu are 8PSK: o valoare gresita in tabela se acorda ca QPSK (ca la descriptorul din NIT, frontend.cpp) */
	if (tp.sistem == 0 && tp.modulatie == 2)
		tp.modulatie = 1;
	tp.simboluri = bcd(d + 9, 7) * 100;
	tp.fec = d[12] & 0x0f;
	if (tp.fec != 15 && tp.fec > 9)
		tp.fec = 0;
	tp.areLivrare = true;
	return true;
}

/* antetul comun al unei sectiuni lungi: tabela ceruta, lungimea in tampon, loc de CRC; capat = inceputul CRC-ului */
static bool antet(const uint8_t *s, size_t lungime, int tid, size_t minim, size_t &capat)
{
	size_t total = lungimeSectiune(s, lungime);
	if (!total || s[0] != tid || total < minim + 4)
		return false;
	capat = total - 4;
	return true;
}

static void citesteDescriptoriTransponder(const uint8_t *s, size_t poz, size_t capat, Transponder &tp)
{
	while (poz + 2 <= capat)
	{
		const uint8_t *d = s + poz;
		size_t lung = 2 + d[1];
		if (poz + lung > capat)
			break;
		switch (d[0])
		{
		case 0x83: /* numerele canalelor (forma FastScan) */
			for (size_t i = 2; i + 4 <= lung; i += 4)
			{
				Canal c;
				uint16_t w = r16(d + i + 2);
				c.sid = r16(d + i);
				c.ascuns = (w >> 14) & 0x01;
				c.numar = w & 0x3fff;
				tp.canale.push_back(c);
			}
			break;
		case 0x43:
			citesteLivrareSatelit(d, lung, tp);
			break;
		case 0x41: /* lista serviciilor: sid + tip */
			for (size_t i = 2; i + 3 <= lung; i += 3)
			{
				ServiciuTp sv;
				sv.sid = r16(d + i);
				sv.tip = d[i + 2];
				tp.servicii.push_back(sv);
			}
			break;
		}
		poz += lung;
	}
}

bool citesteFnt(const uint8_t *s, size_t lungime, Fnt &fnt)
{
	size_t capat;
	if (!antet(s, lungime, TID_FNT, 12, capat))
		return false;
	fnt.versiune = (s[5] >> 1) & 0x1f;
	fnt.numarSectiune = s[6];
	fnt.ultimaSectiune = s[7];
	fnt.numeRetea.clear();
	fnt.transpondere.clear();

	size_t capatRetea = 10 + lungime12(s + 8);
	if (capatRetea + 2 > capat)
		return false;
	for (size_t poz = 10; poz + 2 <= capatRetea; )
	{
		const uint8_t *d = s + poz;
		size_t lung = 2 + d[1];
		if (poz + lung > capatRetea)
			break;
		if (d[0] == 0x40 && fnt.numeRetea.empty())
			fnt.numeRetea.assign((const char *)d + 2, d[1]);
		poz += lung;
	}

	size_t poz = capatRetea + 2;
	size_t capatBucla = poz + lungime12(s + capatRetea);
	if (capatBucla > capat)
		capatBucla = capat;
	while (poz + 6 <= capatBucla)
	{
		size_t capatTp = poz + 6 + lungime12(s + poz + 4);
		if (capatTp > capatBucla)
			break;
		Transponder tp;
		tp.tsid = r16(s + poz);
		tp.onid = r16(s + poz + 2);
		tp.areLivrare = false;
		tp.frecventa = tp.simboluri = 0;
		tp.pozitie = tp.polarizare = tp.fec = tp.sistem = tp.modulatie = tp.rolloff = 0;
		citesteDescriptoriTransponder(s, poz + 6, capatTp, tp);
		fnt.transpondere.push_back(tp);
		poz = capatTp;
	}
	return true;
}

bool citesteFst(const uint8_t *s, size_t lungime, Fst &fst)
{
	size_t capat;
	if (!antet(s, lungime, TID_FST, 8, capat))
		return false;
	fst.versiune = (s[5] >> 1) & 0x1f;
	fst.numarSectiune = s[6];
	fst.ultimaSectiune = s[7];
	fst.servicii.clear();

	size_t poz = 8;
	while (poz + 18 <= capat)
	{
		const uint8_t *e = s + poz;
		size_t capatSv = poz + 18 + lungime12(e + 16);
		if (capatSv > capat)
			break;
		Serviciu sv;
		sv.onid = r16(e);
		sv.tsid = r16(e + 2);
		sv.sid = r16(e + 4);
		sv.pidVideo = pid13(e + 6);
		sv.pidSunet = pid13(e + 8);
		sv.pidEcmVideo = pid13(e + 10);
		sv.pidEcmSunet = pid13(e + 12);
		sv.pidPcr = pid13(e + 14);
		sv.areDescriptor = false;
		sv.tip = 0;
		for (size_t q = poz + 18; q + 2 <= capatSv; )
		{
			const uint8_t *d = s + q;
			size_t lung = 2 + d[1];
			if (q + lung > capatSv)
				break;
			if (d[0] == 0x48 && !sv.areDescriptor && lung >= 5)
			{
				size_t lf = d[3];
				if (4 + lf + 1 <= lung)
				{
					size_t ln = d[4 + lf];
					if (5 + lf + ln <= lung)
					{
						sv.tip = d[2];
						sv.furnizor.assign((const char *)d + 4, lf);
						sv.nume.assign((const char *)d + 5 + lf, ln);
						sv.areDescriptor = true;
					}
				}
			}
			q += lung;
		}
		fst.servicii.push_back(sv);
		poz = capatSv;
	}
	return true;
}

std::vector<std::string> imparteSectiuni(const std::string &continut)
{
	std::vector<std::string> sectiuni;
	const uint8_t *p = (const uint8_t *)continut.data();
	size_t rest = continut.size();
	while (rest >= 3)
	{
		size_t total = lungimeSectiune(p, rest);
		if (!total)
			break;
		sectiuni.push_back(std::string((const char *)p, total));
		p += total;
		rest -= total;
	}
	return sectiuni;
}

}
