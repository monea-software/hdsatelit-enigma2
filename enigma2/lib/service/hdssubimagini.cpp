/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdssubimagini: the decoders of the picture subtitles of films (VobSub, PGS); the description is in the header.
 * Every read is checked against the length of the data: a broken packet gives false (or -1), never a read outside.
 */
#include <lib/service/hdssubimagini.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

#include <algorithm>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <thread>

/* ------------------------------------------------------------------ VobSub */

eHdsVobSub::eHdsVobSub()
{
	/* the usual DVD colours when the film gives none: black, white, dark grey, light grey */
	static const uint32_t implicit[16] = { 0x000000, 0xf0f0f0, 0x303030, 0x808080, 0x000000, 0xf0f0f0, 0x303030, 0x808080,
		0x000000, 0xf0f0f0, 0x303030, 0x808080, 0x000000, 0xf0f0f0, 0x303030, 0x808080 };
	memcpy(m_paleta, implicit, sizeof(m_paleta));
	m_latime = 720;
	m_inaltime = 576;
}

void eHdsVobSub::paleta(const uint32_t rgb[16])
{
	for (int i = 0; i < 16; ++i)
		m_paleta[i] = rgb[i] & 0xFFFFFF;
}

bool eHdsVobSub::dinIdx(const std::string &text)
{
	bool gasit = false;
	size_t poz = 0;
	while (poz < text.size())
	{
		size_t capat = text.find('\n', poz);
		if (capat == std::string::npos)
			capat = text.size();
		std::string rand = text.substr(poz, capat - poz);
		poz = capat + 1;
		if (rand.compare(0, 8, "palette:") == 0)
		{
			uint32_t culori[16];
			int n = 0;
			const char *p = rand.c_str() + 8;
			while (*p && n < 16)
			{
				while (*p == ' ' || *p == ',' || *p == '\t' || *p == '\r')
					++p;
				if (!*p)
					break;
				char *sfarsit = 0;
				unsigned long v = strtoul(p, &sfarsit, 16);
				if (sfarsit == p)
					break;
				culori[n++] = (uint32_t)v;
				p = sfarsit;
			}
			if (n == 16)
			{
				paleta(culori);
				gasit = true;
			}
		}
		else if (rand.compare(0, 5, "size:") == 0)
		{
			int w = 0, h = 0;
			if (sscanf(rand.c_str() + 5, " %dx%d", &w, &h) == 2 && w > 0 && h > 0 && w <= 4096 && h <= 4096)
				marime(w, h);
		}
	}
	return gasit;
}

bool hdsSpuCamp(const uint8_t *d, size_t n, size_t start, int w, int h, int linie0, std::vector<uint8_t> &pixeli)
{
	size_t nib = start * 2;		/* position in nibbles */
	const size_t capat = n * 2;
	for (int y = linie0; y < h; y += 2)
	{
		int x = 0;
		while (x < w)
		{
			unsigned int v = 0;
			int cate = 0;
			/* a code has 1 to 4 nibbles: the value tells when it is complete */
			do
			{
				if (nib >= capat)
					return false;
				v = (v << 4) | ((nib & 1) ? (d[nib >> 1] & 0x0F) : (d[nib >> 1] >> 4));
				++nib;
				++cate;
			} while (cate < 4 && v < (cate == 1 ? 0x4u : cate == 2 ? 0x10u : 0x40u));
			int lungime = v >> 2;
			uint8_t culoare = v & 3;
			if (lungime == 0 || x + lungime > w)
				lungime = w - x;	/* to the end of the line */
			memset(&pixeli[(size_t)y * w + x], culoare, lungime);
			x += lungime;
		}
		if (nib & 1)
			++nib;		/* every line starts on a byte */
	}
	return true;
}

bool eHdsVobSub::decodeaza(const uint8_t *d, size_t n, eHdsPaginaImagine &pagina) const
{
	if (n < 4)
		return false;
	size_t marime = (d[0] << 8) | d[1];
	size_t tabel = (d[2] << 8) | d[3];
	if (marime > n)
		marime = n;
	if (tabel < 4 || tabel + 4 > marime)
		return false;
	uint8_t culoare[4] = { 0, 1, 2, 3 }, alfa[4] = { 0, 15, 15, 15 };
	int x1 = -1, x2 = -1, y1 = -1, y2 = -1;
	size_t camp1 = 0, camp2 = 0;
	int start = -1, stop = -1;
	size_t secventa = tabel;
	for (int pasi = 0; pasi < 32 && secventa + 4 <= marime; ++pasi)
	{
		int data = (d[secventa] << 8) | d[secventa + 1];
		size_t urmatoarea = (d[secventa + 2] << 8) | d[secventa + 3];
		size_t i = secventa + 4;
		bool gata = false;
		while (i < marime && !gata)
		{
			switch (d[i++])
			{
			case 0x00:	/* forced start */
			case 0x01:	/* start */
				if (start < 0)
					start = data;
				break;
			case 0x02:	/* stop */
				stop = data;
				break;
			case 0x03:
				if (i + 2 > marime)
					return false;
				culoare[3] = d[i] >> 4; culoare[2] = d[i] & 0x0F; culoare[1] = d[i + 1] >> 4; culoare[0] = d[i + 1] & 0x0F;
				i += 2;
				break;
			case 0x04:
				if (i + 2 > marime)
					return false;
				alfa[3] = d[i] >> 4; alfa[2] = d[i] & 0x0F; alfa[1] = d[i + 1] >> 4; alfa[0] = d[i + 1] & 0x0F;
				i += 2;
				break;
			case 0x05:
				if (i + 6 > marime)
					return false;
				x1 = (d[i] << 4) | (d[i + 1] >> 4);
				x2 = ((d[i + 1] & 0x0F) << 8) | d[i + 2];
				y1 = (d[i + 3] << 4) | (d[i + 4] >> 4);
				y2 = ((d[i + 4] & 0x0F) << 8) | d[i + 5];
				i += 6;
				break;
			case 0x06:
				if (i + 4 > marime)
					return false;
				camp1 = (d[i] << 8) | d[i + 1];
				camp2 = (d[i + 2] << 8) | d[i + 3];
				i += 4;
				break;
			case 0x07:	/* colour and contrast change inside the picture: its length is in the command */
				if (i + 2 > marime)
					return false;
				i += (d[i] << 8) | d[i + 1];
				break;
			case 0xFF:
				gata = true;
				break;
			default:
				gata = true;	/* unknown command: the rest of this sequence cannot be read */
				break;
			}
		}
		if (urmatoarea == secventa || urmatoarea < tabel)
			break;
		secventa = urmatoarea;
	}
	if (x1 < 0 || x2 < x1 || y2 < y1 || camp1 == 0 || camp2 == 0 || camp1 >= marime || camp2 >= marime)
		return false;
	int w = x2 - x1 + 1, h = y2 - y1 + 1;
	if (w > 4096 || h > 4096)
		return false;
	eHdsDreptunghi r;
	r.x = x1;
	r.y = y1;
	r.w = w;
	r.h = h;
	r.pixeli.assign((size_t)w * h, 0);
	if (!hdsSpuCamp(d, tabel, camp1, w, h, 0, r.pixeli) || !hdsSpuCamp(d, tabel, camp2, w, h, 1, r.pixeli))
		return false;
	memset(r.paleta, 0, sizeof(r.paleta));
	for (int c = 0; c < 4; ++c)
		r.paleta[c] = ((uint32_t)(alfa[c] * 17) << 24) | m_paleta[culoare[c] & 0x0F];
	r.culori = 4;
	pagina.latime = m_latime;
	pagina.inaltime = m_inaltime;
	pagina.start_ms = start > 0 ? (start << 10) / 90 : 0;
	pagina.stop_ms = stop >= 0 ? (stop << 10) / 90 : -1;
	pagina.gol = false;
	pagina.dreptunghiuri.clear();
	pagina.dreptunghiuri.push_back(r);
	return true;
}

/* ------------------------------------------------------------------ PGS */

bool hdsPgsRle(const uint8_t *d, size_t n, int w, int h, std::vector<uint8_t> &pixeli)
{
	pixeli.assign((size_t)w * h, 0);
	size_t i = 0;
	int x = 0, y = 0;
	while (i < n && y < h)
	{
		uint8_t c = d[i++];
		int lungime = 1;
		if (c == 0)
		{
			if (i >= n)
				break;
			uint8_t f = d[i++];
			if (f == 0)
			{
				/* end of the line */
				x = 0;
				++y;
				continue;
			}
			lungime = f & 0x3F;
			if (f & 0x40)
			{
				if (i >= n)
					return false;
				lungime = (lungime << 8) | d[i++];
			}
			if (f & 0x80)
			{
				if (i >= n)
					return false;
				c = d[i++];
			}
			else
				c = 0;
		}
		if (x + lungime > w)
			lungime = w - x;
		if (lungime > 0)
			memset(&pixeli[(size_t)y * w + x], c, lungime);
		x += lungime;
	}
	return y >= h - 1;
}

static uint32_t argbDinYcrcb(int y, int cr, int cb, int a)
{
	/* BT.709, limited range (16-235, 16-240) */
	double yy = (y - 16) * 255.0 / 219.0, pr = (cr - 128) * 255.0 / 224.0, pb = (cb - 128) * 255.0 / 224.0;
	int r = (int)(yy + 1.5748 * pr + 0.5), g = (int)(yy - 0.1873 * pb - 0.4681 * pr + 0.5), b = (int)(yy + 1.8556 * pb + 0.5);
	r = r < 0 ? 0 : r > 255 ? 255 : r;
	g = g < 0 ? 0 : g > 255 ? 255 : g;
	b = b < 0 ? 0 : b > 255 ? 255 : b;
	return ((uint32_t)a << 24) | (r << 16) | (g << 8) | b;
}

eHdsPgs::eHdsPgs()
{
	reset();
}

void eHdsPgs::reset()
{
	m_latime = 1920;
	m_inaltime = 1080;
	m_paleta_id = 0;
	m_palete.clear();
	m_obiecte.clear();
	m_compozitie.clear();
	m_are_pcs = false;
}

int eHdsPgs::adauga(const uint8_t *d, size_t n, std::vector<eHdsPaginaImagine> &pagini)
{
	int adaugate = 0;
	size_t i = 0;
	while (i < n)
	{
		if (i + 2 <= n && d[i] == 'P' && d[i + 1] == 'G')
		{
			if (i + 13 > n)
				break;
			i += 10;	/* "PG", PTS, DTS */
		}
		if (i + 3 > n)
			break;
		int tip = d[i];
		size_t lungime = (d[i + 1] << 8) | d[i + 2];
		i += 3;
		if (i + lungime > n)
		{
			reset();
			return -1;
		}
		segment(tip, d + i, lungime, pagini, adaugate);
		i += lungime;
	}
	return adaugate;
}

void eHdsPgs::segment(int tip, const uint8_t *d, size_t n, std::vector<eHdsPaginaImagine> &pagini, int &adaugate)
{
	switch (tip)
	{
	case 0x16:	/* PCS */
	{
		if (n < 11)
			return;
		int stare = d[7];
		if (stare & 0x80)	/* epoch start: nothing from before is valid */
		{
			m_palete.clear();
			m_obiecte.clear();
		}
		m_latime = (d[0] << 8) | d[1];
		m_inaltime = (d[2] << 8) | d[3];
		if (m_latime <= 0 || m_latime > 4096)
			m_latime = 1920;
		if (m_inaltime <= 0 || m_inaltime > 4096)
			m_inaltime = 1080;
		m_paleta_id = d[9];
		int obiecte = d[10];
		m_compozitie.clear();
		size_t i = 11;
		for (int k = 0; k < obiecte && i + 8 <= n; ++k)
		{
			Compozitie c;
			c.obiect = (d[i] << 8) | d[i + 1];
			c.fereastra = d[i + 2];
			c.taiat = (d[i + 3] & 0x80) != 0;
			c.x = (d[i + 4] << 8) | d[i + 5];
			c.y = (d[i + 6] << 8) | d[i + 7];
			i += 8;
			c.tx = c.ty = c.tw = c.th = 0;
			if (c.taiat)
			{
				if (i + 8 > n)
					break;
				c.tx = (d[i] << 8) | d[i + 1];
				c.ty = (d[i + 2] << 8) | d[i + 3];
				c.tw = (d[i + 4] << 8) | d[i + 5];
				c.th = (d[i + 6] << 8) | d[i + 7];
				i += 8;
			}
			m_compozitie.push_back(c);
		}
		m_are_pcs = true;
		break;
	}
	case 0x14:	/* PDS */
	{
		if (n < 2)
			return;
		std::vector<uint32_t> &p = m_palete[d[0]];
		if (p.size() != 256)
			p.assign(256, 0);
		for (size_t i = 2; i + 5 <= n; i += 5)
			p[d[i]] = argbDinYcrcb(d[i + 1], d[i + 2], d[i + 3], d[i + 4]);
		break;
	}
	case 0x15:	/* ODS */
	{
		if (n < 4)
			return;
		int id = (d[0] << 8) | d[1];
		int secventa = d[3];
		Obiect &o = m_obiecte[id];
		size_t i = 4;
		if (secventa & 0x80)	/* the first fragment: length and size */
		{
			if (n < 11)
				return;
			o.asteptat = ((d[4] << 16) | (d[5] << 8) | d[6]);
			o.asteptat = o.asteptat >= 4 ? o.asteptat - 4 : 0;
			o.w = (d[7] << 8) | d[8];
			o.h = (d[9] << 8) | d[10];
			o.rle.clear();
			i = 11;
		}
		if (o.rle.size() + (n - i) <= 16 * 1024 * 1024)
			o.rle.insert(o.rle.end(), d + i, d + n);
		break;
	}
	case 0x80:	/* END */
		if (m_are_pcs)
		{
			pagina(pagini);
			++adaugate;
		}
		m_are_pcs = false;
		break;
	default:	/* WDS and anything else: the places come from the composition */
		break;
	}
}

void eHdsPgs::pagina(std::vector<eHdsPaginaImagine> &pagini)
{
	eHdsPaginaImagine p;
	p.latime = m_latime;
	p.inaltime = m_inaltime;
	p.start_ms = 0;
	p.stop_ms = -1;
	std::map<int, std::vector<uint32_t> >::const_iterator paleta = m_palete.find(m_paleta_id);
	for (size_t k = 0; k < m_compozitie.size(); ++k)
	{
		const Compozitie &c = m_compozitie[k];
		std::map<int, Obiect>::const_iterator o = m_obiecte.find(c.obiect);
		if (o == m_obiecte.end() || o->second.w <= 0 || o->second.h <= 0 || o->second.w > 4096 || o->second.h > 4096)
			continue;
		eHdsDreptunghi r;
		std::vector<uint8_t> tot;
		if (!hdsPgsRle(o->second.rle.data(), o->second.rle.size(), o->second.w, o->second.h, tot))
			continue;
		int x0 = 0, y0 = 0, w = o->second.w, h = o->second.h;
		if (c.taiat && c.tw > 0 && c.th > 0 && c.tx + c.tw <= w && c.ty + c.th <= h)
		{
			x0 = c.tx;
			y0 = c.ty;
			w = c.tw;
			h = c.th;
		}
		r.x = c.x;
		r.y = c.y;
		r.w = w;
		r.h = h;
		r.pixeli.resize((size_t)w * h);
		for (int y = 0; y < h; ++y)
			memcpy(&r.pixeli[(size_t)y * w], &tot[(size_t)(y + y0) * o->second.w + x0], w);
		if (paleta != m_palete.end())
			for (int i = 0; i < 256; ++i)
				r.paleta[i] = paleta->second[i];
		else
			memset(r.paleta, 0, sizeof(r.paleta));
		r.culori = 256;
		p.dreptunghiuri.push_back(r);
	}
	p.gol = p.dreptunghiuri.empty();
	pagini.push_back(p);
}

/* ------------------------------------------------------------------ packets from the files */

bool hdsSpuDinPs(const std::vector<uint8_t> &s, std::vector<uint8_t> &spu)
{
	spu.clear();
	size_t poz = 0, total = 0;
	int subflux = -1;	/* the substream of the first pack: a file with several languages interleaves their packs */
	while (poz + 14 <= s.size())
	{
		if (s[poz] || s[poz + 1] || s[poz + 2] != 1 || s[poz + 3] != 0xBA)
			return false;
		size_t i = poz + 14 + (s[poz + 13] & 7);
		bool gasit = false;
		size_t urmatorul = s.size();
		while (i + 6 <= s.size())
		{
			if (s[i] || s[i + 1] || s[i + 2] != 1)
				return false;
			int id = s[i + 3];
			if (id == 0xBA)
			{
				urmatorul = i;
				break;
			}
			size_t len = (s[i + 4] << 8) | s[i + 5];
			if (id == 0xBD && i + 9 <= s.size())
			{
				size_t h = i + 9 + s[i + 8];
				size_t capat = i + 6 + len;
				if (h + 1 <= capat && capat <= s.size() && (s[h] & 0xE0) == 0x20 && (subflux < 0 || s[h] == subflux))
				{
					subflux = s[h];
					spu.insert(spu.end(), s.begin() + h + 1, s.begin() + capat);
					gasit = true;
				}
			}
			i += 6 + len;
		}
		if (gasit && !total && spu.size() >= 2)
			total = (spu[0] << 8) | spu[1];
		if (total && spu.size() >= total)
		{
			spu.resize(total);
			return true;
		}
		if (urmatorul >= s.size())
			break;
		poz = urmatorul;
	}
	return total && spu.size() >= total;
}

static bool citesteLa(FILE *f, long long offset, size_t lungime, std::vector<uint8_t> &date)
{
	date.clear();
	if (!f || fseeko(f, (off_t)offset, SEEK_SET) != 0)
		return false;
	date.resize(lungime);
	date.resize(fread(date.data(), 1, lungime, f));
	return !date.empty();
}

bool eHdsCititorImagini::citeste(FILE *&fisier, std::string &deschis, int fel, const std::string &cale,
	const std::string &info, const std::vector<Intrare> &intrari, int index, eHdsPaginaImagine &pagina)
{
	if (index < 0 || index >= (int)intrari.size())
		return false;
	if (!fisier || deschis != cale)
	{
		if (fisier)
			fclose(fisier);
		fisier = fopen(cale.c_str(), "rb");
		deschis = fisier ? cale : std::string();
		if (!fisier)
			return false;
	}
	std::vector<uint8_t> date;
	if (fel == VobSub)
	{
		/* a subtitle packet of a DVD is at most 64 KB, spread over PS packs of 2 KB with padding in between */
		std::vector<uint8_t> spu;
		if (!citesteLa(fisier, intrari[index].offset, 160 * 1024, date) || !hdsSpuDinPs(date, spu))
			return false;
		eHdsVobSub vob;
		vob.dinIdx(info);
		return vob.decodeaza(spu.data(), spu.size(), pagina);
	}
	/* Blu-ray: a display set that only changes an earlier one (neither epoch start nor acquisition point) is read
	   with the sets before it, back to the last one that starts anew */
	int primul = index;
	for (int j = index; j >= 0 && index - j < 32; --j)
	{
		std::vector<uint8_t> antet;
		if (!citesteLa(fisier, intrari[j].offset, 32, antet) || antet.size() < 21)
			break;
		/* "PG", PTS, DTS, type 0x16 (PCS), length, then the composition: its state is the 8th byte */
		primul = j;
		if (antet[0] == 'P' && antet[1] == 'G' && antet[10] == 0x16 && (antet[13 + 7] & 0xC0))
			break;
	}
	eHdsPgs pgs;
	std::vector<eHdsPaginaImagine> pagini;
	for (int j = primul; j <= index; ++j)
	{
		if (intrari[j].length <= 0 || intrari[j].length > 16 * 1024 * 1024 ||
				!citesteLa(fisier, intrari[j].offset, intrari[j].length, date))
			return false;
		pgs.adauga(date.data(), date.size(), pagini);
	}
	if (pagini.empty())
		return false;
	pagina = pagini.back();
	return true;
}

/* ------------------------------------------------------------------ the reading thread */

struct eHdsCititorImagini::Stare
{
	std::mutex lacat;
	std::condition_variable semnal;
	bool opreste, porneste;
	unsigned int generatie;
	int fel;
	std::string cale, info;
	std::shared_ptr<const std::vector<Intrare> > intrari;
	std::deque<int> cerute;
	struct Gata
	{
		bool bun;
		eHdsPaginaImagine pagina;
	};
	std::map<int, Gata> gata;
	Stare() : opreste(false), porneste(true), generatie(0), fel(0) {}
};

static void firCititor(std::shared_ptr<eHdsCititorImagini::Stare> st)
{
	FILE *fisier = NULL;
	std::string deschis;
	std::unique_lock<std::mutex> l(st->lacat);
	while (!st->opreste)
	{
		if (st->cerute.empty())
		{
			st->semnal.wait(l);
			continue;
		}
		int index = st->cerute.front();
		st->cerute.pop_front();
		if (st->gata.count(index) || !st->intrari)
			continue;
		unsigned int generatie = st->generatie;
		int fel = st->fel;
		std::string cale = st->cale, info = st->info;
		std::shared_ptr<const std::vector<eHdsCititorImagini::Intrare> > intrari = st->intrari;
		l.unlock();
		eHdsCititorImagini::Stare::Gata rezultat;
		rezultat.bun = eHdsCititorImagini::citeste(fisier, deschis, fel, cale, info, *intrari, index, rezultat.pagina);
		l.lock();
		if (generatie != st->generatie)
			continue;
		st->gata[index] = rezultat;
		/* a few pages are kept, the ones nearest to the packet asked for last */
		while (st->gata.size() > 6)
		{
			std::map<int, eHdsCititorImagini::Stare::Gata>::iterator departe = st->gata.begin();
			std::map<int, eHdsCititorImagini::Stare::Gata>::iterator ultimul = st->gata.end();
			--ultimul;
			if (std::abs(ultimul->first - index) > std::abs(departe->first - index))
				departe = ultimul;
			st->gata.erase(departe);
		}
	}
	l.unlock();
	if (fisier)
		fclose(fisier);
}

eHdsCititorImagini::eHdsCititorImagini() : m_stare(std::make_shared<Stare>())
{
}

eHdsCititorImagini::~eHdsCititorImagini()
{
	std::lock_guard<std::mutex> l(m_stare->lacat);
	m_stare->opreste = true;
	m_stare->semnal.notify_all();
}

void eHdsCititorImagini::configureaza(int fel, const std::string &cale, const std::string &info,
	const std::vector<Intrare> &intrari)
{
	std::shared_ptr<const std::vector<Intrare> > copie = std::make_shared<const std::vector<Intrare> >(intrari);
	std::lock_guard<std::mutex> l(m_stare->lacat);
	++m_stare->generatie;
	m_stare->fel = fel;
	m_stare->cale = cale;
	m_stare->info = info;
	m_stare->intrari = copie;
	m_stare->cerute.clear();
	m_stare->gata.clear();
	if (m_stare->porneste)
	{
		/* the thread starts with the first picture file and is detached: it holds the state, not the object */
		m_stare->porneste = false;
		std::thread(firCititor, m_stare).detach();
	}
}

bool eHdsCititorImagini::configurat(int fel, const std::string &cale, size_t cate) const
{
	std::lock_guard<std::mutex> l(m_stare->lacat);
	return m_stare->intrari && m_stare->fel == fel && m_stare->cale == cale && m_stare->intrari->size() == cate;
}

void eHdsCititorImagini::goleste()
{
	std::lock_guard<std::mutex> l(m_stare->lacat);
	++m_stare->generatie;
	m_stare->intrari.reset();
	m_stare->cale.clear();
	m_stare->cerute.clear();
	m_stare->gata.clear();
}

void eHdsCititorImagini::cere(int index)
{
	std::lock_guard<std::mutex> l(m_stare->lacat);
	if (!m_stare->intrari || index < 0 || index >= (int)m_stare->intrari->size() || m_stare->gata.count(index) ||
			std::find(m_stare->cerute.begin(), m_stare->cerute.end(), index) != m_stare->cerute.end())
		return;
	m_stare->cerute.push_back(index);
	m_stare->semnal.notify_one();
}

int eHdsCititorImagini::ia(int index, eHdsPaginaImagine &pagina)
{
	std::lock_guard<std::mutex> l(m_stare->lacat);
	if (!m_stare->intrari || index < 0 || index >= (int)m_stare->intrari->size())
		return -1;
	std::map<int, Stare::Gata>::iterator g = m_stare->gata.find(index);
	bool urmatorul = index + 1 < (int)m_stare->intrari->size() && !m_stare->gata.count(index + 1);
	if (g != m_stare->gata.end())
	{
		if (urmatorul && std::find(m_stare->cerute.begin(), m_stare->cerute.end(), index + 1) == m_stare->cerute.end())
		{
			m_stare->cerute.push_back(index + 1);
			m_stare->semnal.notify_one();
		}
		if (!g->second.bun)
			return -1;
		pagina = g->second.pagina;
		return 1;
	}
	/* the packet asked for goes first; older requests (a seek, a skipped line) are dropped */
	m_stare->cerute.clear();
	m_stare->cerute.push_back(index);
	if (urmatorul)
		m_stare->cerute.push_back(index + 1);
	m_stare->semnal.notify_one();
	return 0;
}
