/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsait.cpp: citirea unei sectiuni AIT (vezi hdsait.h). Sintaxa: ETSI TS 102 809 cap. 5.3.4 (sectiunea), 5.3.5
 * (application_descriptor, application_name_descriptor), 5.3.6 (transport_protocol_descriptor: caruselul de obiecte si
 * HTTP), 5.3.7 (simple_application_location, application_usage, simple_application_boundary); parental_rating din
 * ETSI EN 300 468.
 */

#include <lib/dvb/hdsait.h>

namespace hdsait
{

static uint32_t g_tabel[256];
static bool g_tabel_gata = false;

static void faTabel()
{
	for (uint32_t i = 0; i < 256; ++i)
	{
		uint32_t c = i << 24;
		for (int k = 0; k < 8; ++k)
			c = (c & 0x80000000u) ? ((c << 1) ^ 0x04C11DB7u) : (c << 1);
		g_tabel[i] = c;
	}
	g_tabel_gata = true;
}

uint32_t crc32(const uint8_t *date, size_t n)
{
	if (!g_tabel_gata)
		faTabel();
	uint32_t c = 0xFFFFFFFFu;
	for (size_t i = 0; i < n; ++i)
		c = (c << 8) ^ g_tabel[((c >> 24) ^ date[i]) & 0xFF];
	return c;
}

size_t lungime(const uint8_t *date, size_t n)
{
	if (!date || n < 3)
		return 0;
	return 3 + (((size_t)(date[1] & 0x0F) << 8) | date[2]);
}

static inline unsigned u16(const uint8_t *b)
{
	return ((unsigned)b[0] << 8) | b[1];
}

static inline unsigned l12(const uint8_t *b)
{
	return ((unsigned)(b[0] & 0x0F) << 8) | b[1];
}

/* un descriptor: eticheta, inceputul continutului si lungimea lui (continutul e intreg in sectiune) */
struct Desc
{
	unsigned tag;
	const uint8_t *c;
	size_t n;
};

/* descriptorii dintre i si capat; false cand unul trece de capat */
static bool descriptori(const uint8_t *b, size_t i, size_t capat, std::vector<Desc> &rez)
{
	while (i < capat)
	{
		if (i + 2 > capat)
			return false;
		size_t n = b[i + 1];
		if (i + 2 + n > capat)
			return false;
		Desc d;
		d.tag = b[i];
		d.c = b + i + 2;
		d.n = n;
		rez.push_back(d);
		i += 2 + n;
	}
	return true;
}

/* transport_protocol_descriptor -> false cand selectorul nu se poate citi deloc */
static bool transport(const Desc &d, Transport &t)
{
	if (d.n < 3)
		return false;
	t.protocol = u16(d.c);
	t.eticheta = d.c[2];
	t.la_distanta = 0;
	t.onid = t.tsid = t.sid = 0;
	t.tag = -1;
	const uint8_t *s = d.c + 3;
	size_t n = d.n - 3;
	if (t.protocol == PROTOCOL_CARUSEL)
	{
		if (n < 1)
			return false;
		if (s[0] & 0x80)
		{
			if (n < 8)
				return false;
			t.la_distanta = 1;
			t.onid = u16(s + 1);
			t.tsid = u16(s + 3);
			t.sid = u16(s + 5);
			t.tag = s[7];
		}
		else
		{
			if (n < 2)
				return false;
			t.tag = s[1];
		}
		return true;
	}
	if (t.protocol == PROTOCOL_HTTP)
	{
		/* { URL_base_length, URL_base, URL_extension_count, { URL_extension_length, URL_extension } } de cate ori
		   incape; o parte taiata incheie citirea (ce s-a citit pana atunci ramane) */
		size_t q = 0;
		bool prima = true;
		while (q < n && t.adrese.size() < MAX_ADRESE)
		{
			size_t lb = s[q];
			if (q + 1 + lb > n)
				break;
			std::string baza((const char *)s + q + 1, lb);
			q += 1 + lb;
			if (lb)
				t.adrese.push_back(baza);
			if (q >= n)
				break;
			unsigned ext = s[q++];
			bool taiat = false;
			for (unsigned k = 0; k < ext; ++k)
			{
				if (q >= n)
				{
					taiat = true;
					break;
				}
				size_t le = s[q];
				if (q + 1 + le > n)
				{
					taiat = true;
					break;
				}
				if (prima && lb && t.extensii.size() < MAX_EXTENSII)
					t.extensii.push_back(std::string((const char *)s + q + 1, le));
				q += 1 + le;
			}
			if (lb)
				prima = false;
			if (taiat)
				break;
		}
		return !t.adrese.empty();
	}
	return true;
}

/* application_descriptor (0x00) -> false cand e stricat (atunci nu se ia nimic din el) */
static bool descriptorAplicatie(const Desc &d, Aplicatie &a)
{
	if (d.n < 1)
		return false;
	size_t p = d.c[0];
	if (p % 5 || 1 + p + 2 > d.n)
		return false;
	for (size_t q = 1; q + 5 <= 1 + p; q += 5)
	{
		if (a.profile.size() >= MAX_PROFILE)
			break;
		Profil pr;
		pr.profil = u16(d.c + q);
		pr.major = d.c[q + 2];
		pr.minor = d.c[q + 3];
		pr.micro = d.c[q + 4];
		a.profile.push_back(pr);
	}
	unsigned f = d.c[1 + p];
	a.legat = (f >> 7) & 1;
	a.vizibilitate = (f >> 5) & 3;
	a.prioritate = d.c[2 + p];
	for (size_t q = 3 + p; q < d.n && a.etichete.size() < MAX_ETICHETE; ++q)
		a.etichete.push_back(d.c[q]);
	return true;
}

/* primul nume din application_name_descriptor (0x01) -> false cand nu are niciun nume intreg */
static bool numeAplicatie(const Desc &d, Aplicatie &a)
{
	if (d.n < 4)
		return false;
	size_t ln = d.c[3];
	if (4 + ln > d.n)
		return false;
	a.limba.assign((const char *)d.c, 3);
	a.nume.assign((const char *)d.c + 4, ln);
	return true;
}

static void limite(const Desc &d, Aplicatie &a)
{
	if (d.n < 1)
		return;
	unsigned k = d.c[0];
	size_t q = 1;
	for (unsigned i = 0; i < k && a.limite.size() < MAX_LIMITE; ++i)
	{
		if (q >= d.n)
			break;
		size_t l = d.c[q];
		if (q + 1 + l > d.n)
			break;
		a.limite.push_back(std::string((const char *)d.c + q + 1, l));
		q += 1 + l;
	}
}

static void varste(const Desc &d, Aplicatie &a)
{
	for (size_t q = 0; q + 4 <= d.n && a.varste.size() < MAX_VARSTE; q += 4)
		a.varste.push_back(std::make_pair(std::string((const char *)d.c + q, 3), (unsigned)d.c[q + 3]));
}

static const Transport *cautaEticheta(const std::vector<Transport> &lista, unsigned e)
{
	for (size_t i = 0; i < lista.size(); ++i)
		if (lista[i].eticheta == e)
			return &lista[i];
	return 0;
}

/* aplicatia din descriptorii ei si din cei comuni */
static void aplicatie(const std::vector<Desc> &proprii, const std::vector<Desc> &comuni, Aplicatie &a)
{
	a.prioritate = a.vizibilitate = a.legat = -1;
	a.utilizare = -1;
	bool are_descriptor = false, are_nume = false, are_cale = false;
	std::vector<Transport> tp, tc;
	for (size_t i = 0; i < proprii.size(); ++i)
	{
		const Desc &d = proprii[i];
		switch (d.tag)
		{
		case 0x00:
			if (!are_descriptor)
				are_descriptor = descriptorAplicatie(d, a);
			break;
		case 0x01:
			if (!are_nume)
				are_nume = numeAplicatie(d, a);
			break;
		case 0x02:
		{
			Transport t;
			if (transport(d, t))
				tp.push_back(t);
			break;
		}
		case 0x15:
			if (!are_cale)
			{
				a.cale.assign((const char *)d.c, d.n);
				are_cale = true;
			}
			break;
		case 0x16:
			if (a.utilizare < 0 && d.n >= 1)
				a.utilizare = d.c[0];
			break;
		case 0x17:
			limite(d, a);
			break;
		case 0x55:
			varste(d, a);
			break;
		default:
			break;
		}
	}
	for (size_t i = 0; i < comuni.size(); ++i)
	{
		const Desc &d = comuni[i];
		if (d.tag == 0x02)
		{
			Transport t;
			if (transport(d, t))
				tc.push_back(t);
		}
		else if (d.tag == 0x01 && !are_nume)
			are_nume = numeAplicatie(d, a);
		else if (d.tag == 0x15 && !are_cale)
		{
			a.cale.assign((const char *)d.c, d.n);
			are_cale = true;
		}
	}
	/* transporturile in ordinea etichetelor: intai cel din bucla aplicatiei, apoi cel comun cu aceeasi eticheta */
	for (size_t i = 0; i < a.etichete.size() && a.transporturi.size() < MAX_TRANSPORTURI; ++i)
	{
		bool vazuta = false;
		for (size_t j = 0; j < i; ++j)
			if (a.etichete[j] == a.etichete[i])
				vazuta = true;
		if (vazuta)
			continue;
		const Transport *t = cautaEticheta(tp, a.etichete[i]);
		if (!t)
			t = cautaEticheta(tc, a.etichete[i]);
		if (t)
			a.transporturi.push_back(*t);
	}
	if (a.transporturi.empty())
	{
		const std::vector<Transport> &lista = tp.empty() ? tc : tp;
		for (size_t i = 0; i < lista.size() && a.transporturi.size() < MAX_TRANSPORTURI; ++i)
			a.transporturi.push_back(lista[i]);
	}
}

int citeste(const uint8_t *date, size_t n, Sectiune &s)
{
	s = Sectiune();
	size_t l = lungime(date, n);
	if (l < 16 || l > n || l > MAX_SECTIUNE)
		return E_SCURTA;
	if (date[0] != TID || !(date[1] & 0x80) || !(date[5] & 0x01))
		return E_ANTET;
	if (crc32(date, l))
		return E_CRC;
	size_t sfarsit = l - 4;
	size_t lc = l12(date + 8);
	if (10 + lc + 2 > sfarsit)
		return E_STRUCTURA;
	std::vector<Desc> comuni;
	if (!descriptori(date, 10, 10 + lc, comuni))
		return E_STRUCTURA;
	size_t i = 10 + lc;
	size_t la = l12(date + i);
	i += 2;
	size_t capat = i + la;
	if (capat > sfarsit)
		return E_STRUCTURA;
	Sectiune rez;
	rez.tip = u16(date + 3) & 0x7FFF;
	rez.test = (date[3] >> 7) & 1;
	rez.versiune = (date[5] >> 1) & 0x1F;
	rez.numar = date[6];
	rez.ultima = date[7];
	while (i < capat)
	{
		if (i + 9 > capat)
			return E_STRUCTURA;
		size_t ld = l12(date + i + 7);
		if (i + 9 + ld > capat)
			return E_STRUCTURA;
		std::vector<Desc> proprii;
		if (!descriptori(date, i + 9, i + 9 + ld, proprii))
			return E_STRUCTURA;
		if (rez.aplicatii.size() < MAX_APLICATII)
		{
			Aplicatie a;
			a.org = ((uint32_t)date[i] << 24) | ((uint32_t)date[i + 1] << 16) | ((uint32_t)date[i + 2] << 8) | date[i + 3];
			a.id = u16(date + i + 4);
			a.cod = date[i + 6];
			aplicatie(proprii, comuni, a);
			rez.aplicatii.push_back(a);
		}
		i += 9 + ld;
	}
	s.tip = rez.tip;
	s.test = rez.test;
	s.versiune = rez.versiune;
	s.numar = rez.numar;
	s.ultima = rez.ultima;
	s.aplicatii.swap(rez.aplicatii);
	return BUN;
}

}

eHdsAitSection::eHdsAitSection(const uint8_t *date)
{
	m_eroare = hdsait::citeste(date, hdsait::MAX_SECTIUNE, m_sectiune);
}
