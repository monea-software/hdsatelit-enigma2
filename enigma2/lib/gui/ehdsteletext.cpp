/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * ehdsteletext.cpp: widgetul paginii de teletext (vezi ehdsteletext.h).
 *
 * Ce s-a luat din esubtitle.cpp (acelasi fel de lucru, scris din nou aici):
 *  - eTextPara::blit nu amesteca, scrie culoarea gata amestecata; litera se scrie alb pe negru pe o ciorna de 32 de
 *    biti si se ia numai acoperirea, din octetul rosu (acoperirea deplina iese 239);
 *  - un gDC nou are zona de taiere goala: fara ea blit nu deseneaza nimic;
 *  - gPainter::blit tine poza pana o deseneaza firul gRC: la fiecare compunere se face o poza noua.
 */
#include <lib/gui/ehdsteletext.h>
#include <lib/gdi/grc.h>
#include <lib/gdi/font.h>
#include <lib/base/eerror.h>

#include <map>
#include <string.h>
#include <time.h>

/* acoperirea deplina a unei litere scrise de eTextPara::blit pe 32 de biti */
static const int ACOPERIRE_PLINA = 239;

/* pagina venita din nou in carusel: cate treceri ale ceasului ecranului (250 ms) se asteapta cel mult sa se termine de
   primit inainte de comparare (o pagina vine in cateva zeci de ms; o pagina care nu se mai linisteste, de pilda
   subtitrarile, se compara oricum dupa atatea treceri) */
static const int AMANARI_MAX = 4;

/* randurile 1-24 ale celulelor (corpul), unul dupa altul in tabel */
static const size_t CORP_OCTETI = (size_t)(hdsttx::RANDURI - 1) * hdsttx::COLOANE * sizeof(hdsttx::Celula);

/* traducerea: celulele corpului si semnul "celula ramane" */
static const int TRAD_CELULE = (hdsttx::RANDURI - 1) * hdsttx::COLOANE;
static const uint32_t TRAD_RAMANE = 1;

/* crc32 (polinomul lui zlib, ca zlib.crc32 din Python) al celulelor corpului, fiecare scrisa ca in eHdsTeletext::pagina:
   codul pe 4 octeti (cel mic intai), mozaicul, culoarea, fundalul, atributele */
static int amprentaCorpului(const hdsttx::Celula celule[hdsttx::RANDURI][hdsttx::COLOANE])
{
	uint32_t crc = 0xFFFFFFFFu;
	for (int r = 1; r < hdsttx::RANDURI; r++)
		for (int c = 0; c < hdsttx::COLOANE; c++)
		{
			const hdsttx::Celula &ce = celule[r][c];
			uint8_t o[8] = { (uint8_t)(ce.cod & 0xFF), (uint8_t)((ce.cod >> 8) & 0xFF), (uint8_t)((ce.cod >> 16) & 0xFF),
				(uint8_t)((ce.cod >> 24) & 0xFF), ce.mozaic, ce.fata, ce.fundal, ce.atribute };
			for (int b = 0; b < 8; b++)
			{
				crc ^= o[b];
				for (int k = 0; k < 8; k++)
					crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
			}
		}
	return (int)(~crc & 0x7FFFFFFFu);
}

/* UTF-8 -> puncte Unicode; o secventa stricata da U+FFFD */
static void dinUtf8(const char *text, std::vector<uint32_t> &iesire)
{
	iesire.clear();
	if (!text)
		return;
	const unsigned char *p = (const unsigned char *)text;
	while (*p)
	{
		uint32_t c = *p++;
		int urm = 0;
		if (c >= 0xF8)
			c = 0xFFFD;
		else if (c >= 0xF0)
		{
			c &= 0x07;
			urm = 3;
		}
		else if (c >= 0xE0)
		{
			c &= 0x0F;
			urm = 2;
		}
		else if (c >= 0xC0)
		{
			c &= 0x1F;
			urm = 1;
		}
		else if (c >= 0x80)
			c = 0xFFFD;
		for (; urm > 0; urm--)
		{
			if ((*p & 0xC0) != 0x80)
			{
				c = 0xFFFD;
				break;
			}
			c = (c << 6) | (*p++ & 0x3F);
		}
		iesire.push_back(c);
	}
}

/* ------------------------------------------------------------------ literele fontului din skin */

class eHdsTeletextGlife: public hdsttx::Glife
{
public:
	eHdsTeletextGlife() : m_l(0), m_i(0), m_marime(0), m_sus(0), m_cw(0), m_ch(0) {}

	void configureaza(const std::string &familie, int l, int i)
	{
		if (familie == m_familie && l == m_l && i == m_i && m_font)
			return;
		m_familie = familie;
		m_l = l;
		m_i = i;
		m_cache.clear();
		m_cw = 4 * l;
		m_ch = 3 * i;
		m_ciorna = new gPixmap(eSize(m_cw, m_ch), 32);
		m_dc = new gDC(m_ciorna);
		m_dc->getClip() = gRegion(eRect(0, 0, m_cw, m_ch));
		/* marimea: cea mai mare la care literele inalte si cele cu coada (si un accent pe majuscula) incap in celula */
		m_marime = i * 92 / 100;
		for (int incercari = 0; incercari < 24 && m_marime > 6; incercari++)
		{
			m_font = new gFont(m_familie, m_marime);
			int sus, jos;
			if (cerneala("\xc3\x82\xc3\x89gjpqy|", sus, jos) && jos - sus + 1 <= i - i / 20)
			{
				m_sus = sus - (i - (jos - sus + 1)) / 2;
				return;
			}
			m_marime -= m_marime > 30 ? 2 : 1;
		}
		m_font = new gFont(m_familie, m_marime);
		m_sus = i;
	}

	const uint8_t *acoperire(uint32_t cod, int latime, int inaltime)
	{
		if (!m_font || m_l <= 0)
			return 0;
		uint64_t cheie = ((uint64_t)cod << 32) | ((uint64_t)(latime & 0xFFFF) << 16) | (uint64_t)(inaltime & 0xFFFF);
		std::map<uint64_t, std::vector<uint8_t> >::iterator g = m_cache.find(cheie);
		if (g != m_cache.end())
			return g->second.empty() ? 0 : &g->second[0];
		std::vector<uint8_t> &rez = m_cache[cheie];
		std::vector<uint8_t> baza;
		if (!litera(cod, baza))
			return 0;
		if (latime == m_l && inaltime == m_i)
			rez.swap(baza);
		else
			intinde(baza, m_l, m_i, rez, latime, inaltime);
		return rez.empty() ? 0 : &rez[0];
	}

private:
	std::string m_familie;
	int m_l, m_i, m_marime, m_sus, m_cw, m_ch;
	ePtr<gFont> m_font;
	ePtr<gPixmap> m_ciorna;
	ePtr<gDC> m_dc;
	std::map<uint64_t, std::vector<uint8_t> > m_cache;

	/* scrie textul pe ciorna (alb pe negru); fals = nimic scris */
	bool scrie(const char *text)
	{
		gSurface *s = m_ciorna->surface;
		for (int y = 0; y < s->y; y++)
			memset((uint8_t *)s->data + (size_t)y * s->stride, 0, (size_t)s->x * 4);
		ePtr<eTextPara> para = new eTextPara(eRect(m_l / 2, m_i, 3 * m_l, 2 * m_i));
		para->setFont(m_font);
		if (para->renderString(text, 0) < 0)
			return false;
		para->blit(*m_dc, ePoint(0, 0), gRGB(0, 0, 0, 255), gRGB(255, 255, 255, 255));
		return true;
	}

	bool cerneala(const char *text, int &sus, int &jos)
	{
		if (!scrie(text))
			return false;
		gSurface *s = m_ciorna->surface;
		sus = -1;
		jos = -1;
		for (int y = 0; y < s->y; y++)
		{
			const uint8_t *r = (const uint8_t *)s->data + (size_t)y * s->stride;
			for (int x = 0; x < s->x; x++)
				if (r[x * 4 + 2] > 40)
				{
					if (sus < 0)
						sus = y;
					jos = y;
					break;
				}
		}
		return sus >= 0;
	}

	static void utf8(uint32_t c, char *o)
	{
		if (c < 0x80)
		{
			o[0] = (char)c;
			o[1] = 0;
		}
		else if (c < 0x800)
		{
			o[0] = (char)(0xC0 | (c >> 6));
			o[1] = (char)(0x80 | (c & 0x3F));
			o[2] = 0;
		}
		else
		{
			o[0] = (char)(0xE0 | ((c >> 12) & 0x0F));
			o[1] = (char)(0x80 | ((c >> 6) & 0x3F));
			o[2] = (char)(0x80 | (c & 0x3F));
			o[3] = 0;
		}
	}

	/* litera in celula de baza (m_l x m_i): randurile [m_sus, m_sus + m_i) ale ciornei, cerneala centrata pe
	   orizontala, stransa daca e mai lata decat celula */
	bool litera(uint32_t cod, std::vector<uint8_t> &iesire)
	{
		if (cod > 0xFFFF)
			return false;
		char text[8];
		utf8(cod, text);
		if (!scrie(text))
			return false;
		gSurface *s = m_ciorna->surface;
		int x0 = s->x, x1 = -1;
		for (int y = 0; y < m_i; y++)
		{
			int sy = m_sus + y;
			if (sy < 0 || sy >= s->y)
				continue;
			const uint8_t *r = (const uint8_t *)s->data + (size_t)sy * s->stride;
			for (int x = 0; x < s->x; x++)
				if (r[x * 4 + 2])
				{
					if (x < x0)
						x0 = x;
					if (x > x1)
						x1 = x;
				}
		}
		if (x1 < x0)
			return false;
		int lat = x1 - x0 + 1;
		int tinta = lat <= m_l - 1 ? lat : m_l - 1;
		int dx = (m_l - tinta) / 2;
		iesire.assign((size_t)m_l * m_i, 0);
		for (int y = 0; y < m_i; y++)
		{
			int sy = m_sus + y;
			if (sy < 0 || sy >= s->y)
				continue;
			const uint8_t *r = (const uint8_t *)s->data + (size_t)sy * s->stride;
			uint8_t *o = &iesire[(size_t)y * m_l];
			for (int x = 0; x < tinta; x++)
			{
				int v;
				if (tinta == lat)
					v = r[(x0 + x) * 4 + 2];
				else
				{
					/* media pe bucata de cerneala care cade in pixelul x */
					int a = x0 + x * lat / tinta, b = x0 + (x + 1) * lat / tinta;
					if (b <= a)
						b = a + 1;
					int suma = 0;
					for (int k = a; k < b; k++)
						suma += r[k * 4 + 2];
					v = suma / (b - a);
				}
				v = v * 255 / ACOPERIRE_PLINA;
				o[dx + x] = (uint8_t)(v > 255 ? 255 : v);
			}
		}
		return true;
	}

	/* intinderea biliniara a acoperirii (literele duble) */
	static void intinde(const std::vector<uint8_t> &in, int l, int i, std::vector<uint8_t> &out, int L, int I)
	{
		out.assign((size_t)L * I, 0);
		for (int y = 0; y < I; y++)
		{
			int fy = (int)(((long)(2 * y + 1) * i * 256) / (2 * I)) - 128;
			if (fy < 0)
				fy = 0;
			int y0 = fy >> 8, ty = fy & 255, y1 = y0 + 1 < i ? y0 + 1 : i - 1;
			for (int x = 0; x < L; x++)
			{
				int fx = (int)(((long)(2 * x + 1) * l * 256) / (2 * L)) - 128;
				if (fx < 0)
					fx = 0;
				int x0 = fx >> 8, tx = fx & 255, x1 = x0 + 1 < l ? x0 + 1 : l - 1;
				int a = in[(size_t)y0 * l + x0], b = in[(size_t)y0 * l + x1];
				int c = in[(size_t)y1 * l + x0], d = in[(size_t)y1 * l + x1];
				int sus = a * (256 - tx) + b * tx, jos = c * (256 - tx) + d * tx;
				out[(size_t)y * L + x] = (uint8_t)((sus * (256 - ty) + jos * ty) >> 16);
			}
		}
	}
};

/* ------------------------------------------------------------------ widgetul */

eHdsTeletextWidget::eHdsTeletextWidget(eWidget *parent)
	: eWidget(parent), m_glife(new eHdsTeletextGlife()), m_familie("Regular"), m_peste(0), m_arata_ascuns(0),
	  m_stinse(0), m_are_intermitente(0), m_hd(0), m_sursa(-1), m_ms(0), m_contur(0), m_umbra(0), m_relief(0),
	  m_pagina(100), m_subcod(-1), m_subcod_aratat(-1), m_gasita(0),
	  m_v_pagina(0), m_v_antet(0), m_v_colector(0), m_v_vazut(0), m_amanari(0), m_cere_antet(0), m_cere_corp(0), m_l(0), m_i(0), m_x0(0), m_y0(0),
	  m_trad_pagina(0), m_trad_amprenta(0), m_amprenta(-1), m_trad_aratata(0)
{
	memset(m_celule, 0, sizeof(m_celule));
	memset(m_compus, 0, sizeof(m_compus));
	culoareaFundalului();
}

eHdsTeletextWidget::~eHdsTeletextWidget()
{
	delete m_glife;
}

void eHdsTeletextWidget::culoareaFundalului()
{
	/* in enigma2 gRGB.a = 0 e opac, 255 transparent */
	setBackgroundColor(m_peste ? gRGB(0, 0, 0, 255) : gRGB(0, 0, 0, 0));
}

void eHdsTeletextWidget::setFont(gFont *font)
{
	if (font && !font->family.empty() && font->family != m_familie)
	{
		m_familie = font->family;
		reface(true, true);
	}
}

void eHdsTeletextWidget::setPeste(int peste)
{
	peste = peste ? 1 : 0;
	if (peste == m_peste)
		return;
	m_peste = peste;
	culoareaFundalului();
	reface(true, true);
	invalidate();
}

void eHdsTeletextWidget::setArataAscuns(int arata)
{
	arata = arata ? 1 : 0;
	if (arata == m_arata_ascuns)
		return;
	m_arata_ascuns = arata;
	reface(true, true);
}

void eHdsTeletextWidget::setStare(const char *stare)
{
	std::string s = stare ? std::string(stare, strnlen(stare, 8)) : std::string();
	if (s == m_stare)
		return;
	m_stare = s;
	reface(true, false);
}

int eHdsTeletextWidget::setPagina(int pagina, int subcod)
{
	if (pagina != m_pagina || subcod != m_subcod)
	{
		if (pagina != m_pagina)
		{
			/* alta pagina: traducerea celei vechi nu mai trebuie (se pune oricum numai peste pagina ei) */
			m_trad_litere.clear();
			m_trad_culori.clear();
			m_trad_pagina = 0;
		}
		m_pagina = pagina;
		m_subcod = subcod;
		/* alta pagina: se reface oricum, si cand noua lipseste (altfel ar ramane corpul celei vechi) */
		m_v_pagina = 0xFFFFFFFFu;
		m_v_antet = 0;
	}
	return actualizeaza();
}

eHdsTeletext *eHdsTeletextWidget::sursa()
{
	return m_sursa < 0 ? eHdsTeletext::getInstance() : eHdsTeletext::copie(m_sursa);
}

void eHdsTeletextWidget::setHd(int hd)
{
	hd = hd ? 1 : 0;
	if (hd == m_hd)
		return;
	m_hd = hd;
	reface(true, true);
}

void eHdsTeletextWidget::setContur(int contur)
{
	contur = contur ? 1 : 0;
	if (contur == m_contur)
		return;
	m_contur = contur;
	reface(true, true);
}

void eHdsTeletextWidget::setUmbra(int umbra)
{
	umbra = umbra ? 1 : 0;
	if (umbra == m_umbra)
		return;
	m_umbra = umbra;
	reface(true, true);
}

void eHdsTeletextWidget::setRelief(int relief)
{
	relief = relief ? 1 : 0;
	if (relief == m_relief)
		return;
	m_relief = relief;
	/* relieful se vede numai la neted */
	if (m_hd)
		reface(true, true);
}

void eHdsTeletextWidget::setSursa(int s)
{
	s = s < 0 ? -1 : (s ? 1 : 0);
	if (s == m_sursa)
		return;
	m_sursa = s;
	m_v_pagina = 0xFFFFFFFFu;
	m_v_antet = 0;
	actualizeaza();
}

void eHdsTeletextWidget::setFaza(int stinse)
{
	stinse = stinse ? 1 : 0;
	if (stinse == m_stinse)
		return;
	m_stinse = stinse;
	if (m_are_intermitente)
	{
		/* corpul are amandoua fazele gata (reface): numai se schimba poza; antetul (un rand) se reface */
		reface(true, false);
		invalidate(eRect(m_x0, m_y0 + m_i, hdsttx::COLOANE * m_l, (hdsttx::RANDURI - 1) * m_i));
	}
}

int eHdsTeletextWidget::actualizeaza()
{
	hdsttx::Colector &col = sursa()->colector();
	int p = hdsttx::paginaDinZecimal(m_pagina);
	const hdsttx::Subpagina *sp = p != hdsttx::PAGINA_FARA ? col.gaseste(p, m_subcod) : 0;
	uint32_t vp = sp ? (sp->versiune ^ ((uint32_t)sp->subcod << 20)) + 1 : 0;
	uint32_t va = col.versiuneAntet((p >> 8) & 0xF);
	/* memoria golita (zap): totul din nou */
	bool golita = col.numarSubpagini() == 0 && m_v_colector != 0;
	m_v_colector = col.numarSubpagini();
	if (golita || m_v_pagina == 0xFFFFFFFFu)
	{
		/* alta pagina, alta sursa sau memoria golita: pe loc, intreaga */
		m_v_pagina = m_v_vazut = vp;
		m_v_antet = va;
		m_amanari = 0;
		reface(true, true);
	}
	else if (vp != m_v_pagina)
	{
		/* pagina a venit din nou (versiunea creste la fiecare pachet, si cand continutul e acelasi): intai se asteapta
		   sa se termine de primit (versiunea neschimbata de la trecerea de dinainte), apoi se recompune numai ce s-a
		   schimbat la vedere; cat se asteapta, numai antetul (ceasul) */
		if (vp != m_v_vazut && m_amanari < AMANARI_MAX)
		{
			m_v_vazut = vp;
			m_amanari++;
			if (va != m_v_antet)
			{
				m_v_antet = va;
				refaSchimbat(false);
			}
		}
		else
		{
			m_v_pagina = m_v_vazut = vp;
			m_v_antet = va;
			m_amanari = 0;
			refaSchimbat(true);
		}
	}
	else if (va != m_v_antet)
	{
		m_v_antet = va;
		refaSchimbat(false);
	}
	m_gasita = sp ? 1 : 0;
	m_subcod_aratat = sp ? sp->subcod : -1;
	return m_gasita;
}

void eHdsTeletextWidget::aseaza()
{
	eSize s = size();
	/* pagina 4:3: inaltimea celulei din 96% din inaltime, latimea 5/6 din ea (40 x 5/6 = 33,3 = 25 x 4/3) */
	int i = s.height() * 96 / 100 / hdsttx::RANDURI;
	int l = i * 5 / 6;
	if (l * hdsttx::COLOANE > s.width())
	{
		l = s.width() / hdsttx::COLOANE;
		i = l * 6 / 5;
	}
	if (i < 3)
		i = 3;
	if (l < 2)
		l = 2;
	m_l = l;
	m_i = i;
	m_x0 = (s.width() - hdsttx::COLOANE * l) / 2;
	m_y0 = (s.height() - hdsttx::RANDURI * i) / 2;
	m_poza_antet = 0;
	m_poza_corp = 0;
	m_poza_corp_stinsa = 0;
}

void eHdsTeletextWidget::randeazaCelule()
{
	hdsttx::Colector &col = sursa()->colector();
	int p = hdsttx::paginaDinZecimal(m_pagina);
	const hdsttx::Subpagina *sp = p != hdsttx::PAGINA_FARA ? col.gaseste(p, m_subcod) : 0;
	uint16_t control = 0;
	const uint8_t *rulant = col.antetRulant(p != hdsttx::PAGINA_FARA ? (p >> 8) & 0xF : 1, &control);
	hdsttx::randeaza(col, sp, p != hdsttx::PAGINA_FARA ? p : 0x100, m_stare.c_str(), rulant, control, m_celule);
	m_amprenta = amprentaCorpului(m_celule);
	puneTraducerea();
}

void eHdsTeletextWidget::puneTraducerea()
{
	m_trad_aratata = 0;
	if ((int)m_trad_litere.size() != TRAD_CELULE || m_trad_pagina != m_pagina || m_trad_amprenta != m_amprenta)
		return;
	bool cu_culori = (int)m_trad_culori.size() == TRAD_CELULE;
	for (int k = 0; k < TRAD_CELULE; k++)
	{
		uint32_t cod = m_trad_litere[k];
		if (cod == TRAD_RAMANE)
			continue;
		hdsttx::Celula &ce = m_celule[1 + k / hdsttx::COLOANE][k % hdsttx::COLOANE];
		/* jumatatile literelor duble le deseneaza celula lor de sus sau din stanga */
		if (ce.atribute & (hdsttx::A_JUMATATE_JOS | hdsttx::A_JUMATATE_DREAPTA))
			continue;
		ce.cod = cod < 0x20 ? 0x20 : cod;
		ce.mozaic = 0;
		char f = cu_culori ? m_trad_culori[k] : '-';
		if (f >= '0' && f <= '7')
			ce.fata = (uint8_t)(f - '0');
	}
	m_trad_aratata = 1;
}

int eHdsTeletextWidget::setTraducere(int pagina, int amprenta, const char *litere, const char *culori)
{
	std::vector<uint32_t> l;
	dinUtf8(litere, l);
	std::string c = culori ? std::string(culori) : std::string();
	if ((int)l.size() != TRAD_CELULE || (!c.empty() && (int)c.size() != TRAD_CELULE))
	{
		eDebug("[eHdsTeletextWidget] traducerea paginii %d are %d litere si %d culori: nefolosita", pagina, (int)l.size(),
			(int)c.size());
		return 0;
	}
	if (pagina == m_trad_pagina && amprenta == m_trad_amprenta && l == m_trad_litere && c == m_trad_culori)
		return 1;
	m_trad_litere.swap(l);
	m_trad_culori.swap(c);
	m_trad_pagina = pagina;
	m_trad_amprenta = amprenta;
	if (pagina == m_pagina)
		reface(false, true);
	return 1;
}

void eHdsTeletextWidget::stergeTraducere()
{
	bool era = !m_trad_litere.empty();
	m_trad_litere.clear();
	m_trad_culori.clear();
	m_trad_pagina = 0;
	if (era)
		reface(false, true);
}

void eHdsTeletextWidget::reface(bool antet, bool corp)
{
	if (m_l <= 0)
		return;
	cere(antet, corp);
}

void eHdsTeletextWidget::refaSchimbat(bool cu_corp)
{
	if (m_l <= 0)
		return;
	randeazaCelule();
	/* fata de celulele din pozele de acum (nu fata de m_celule de dinainte: o refacere numai a antetului randeaza si
	   corpul, fara sa-l compuna) */
	bool antet = memcmp(m_celule[0], m_compus[0], sizeof(m_celule[0])) != 0;
	bool corp = cu_corp && (!m_poza_corp || memcmp(&m_celule[1][0], &m_compus[1][0], CORP_OCTETI) != 0);
	if (antet || corp)
		cere(antet || corp, corp);
	else if (cu_corp)
		eDebug("[eHdsTeletextWidget] pagina %d primita din nou, neschimbata: nu se recompune", m_pagina);
}

void eHdsTeletextWidget::cere(bool antet, bool corp)
{
	/* compunerea se face la desen (evtPaint), o singura data pentru toate cererile de pana atunci: la deschidere
	   vin pe rand marimea din skin, marimea ecranului, HD, peste imagine, sursa si pagina, si fiecare cerea o compunere */
	if (antet && !m_cere_antet)
	{
		m_cere_antet = 1;
		invalidate(eRect(m_x0, m_y0, hdsttx::COLOANE * m_l, m_i));
	}
	if (corp && !m_cere_corp)
	{
		m_cere_corp = 1;
		invalidate(eRect(m_x0, m_y0 + m_i, hdsttx::COLOANE * m_l, (hdsttx::RANDURI - 1) * m_i));
	}
}

void eHdsTeletextWidget::compuneCerute()
{
	if (!m_cere_antet && !m_cere_corp)
		return;
	bool antet = m_cere_antet != 0, corp = m_cere_corp != 0;
	m_cere_antet = m_cere_corp = 0;
	if (m_l <= 0)
		return;
	randeazaCelule();
	compunePoze(antet || corp, corp);
}

void eHdsTeletextWidget::compunePoze(bool antet, bool corp)
{
	m_glife->configureaza(m_familie, m_l, m_i);
	hdsttx::Aspect a;
	a.l = m_l;
	a.i = m_i;
	a.peste = m_peste != 0;
	a.contur = m_i >= 30 ? 2 : 1;
	a.stinge_intermitente = m_stinse != 0;
	a.arata_ascuns = m_arata_ascuns != 0;
	a.hd = m_hd != 0;
	a.cu_contur = m_contur != 0;
	a.cu_umbra = m_umbra != 0;
	a.relief = a.hd && m_relief != 0;
	struct timespec t0, t1;
	clock_gettime(CLOCK_MONOTONIC, &t0);
	int intermitente = 0;
	if (antet)
	{
		ePtr<gPixmap> poza = new gPixmap(eSize(hdsttx::COLOANE * m_l, m_i), 32);
		intermitente |= hdsttx::compune(m_celule, 0, 1, a, *m_glife, (uint32_t *)poza->surface->data,
			poza->surface->stride / 4);
		m_poza_antet = poza;
		memcpy(m_compus[0], m_celule[0], sizeof(m_celule[0]));
	}
	if (corp)
	{
		/* faza aprinsa intotdeauna; daca pagina are litere intermitente, si faza stinsa, o data: clipitul numai schimba poza */
		ePtr<gPixmap> poza = new gPixmap(eSize(hdsttx::COLOANE * m_l, (hdsttx::RANDURI - 1) * m_i), 32);
		a.stinge_intermitente = false;
		m_are_intermitente = hdsttx::compune(m_celule, 1, hdsttx::RANDURI, a, *m_glife,
			(uint32_t *)poza->surface->data, poza->surface->stride / 4) | intermitente;
		m_poza_corp = poza;
		memcpy(&m_compus[1][0], &m_celule[1][0], CORP_OCTETI);
		m_poza_corp_stinsa = 0;
		if (m_are_intermitente)
		{
			/* faza stinsa: copia celei aprinse, recompusa numai pe randurile cu intermitente (si vecinii lor); intreaga
			   numai cand clipeste mozaic legat in HD */
			ePtr<gPixmap> stinsa = new gPixmap(eSize(hdsttx::COLOANE * m_l, (hdsttx::RANDURI - 1) * m_i), 32);
			a.stinge_intermitente = true;
			if (!hdsttx::compuneStinsa(m_celule, a, *m_glife, (const uint32_t *)poza->surface->data,
					(uint32_t *)stinsa->surface->data, stinsa->surface->stride / 4))
				hdsttx::compune(m_celule, 1, hdsttx::RANDURI, a, *m_glife, (uint32_t *)stinsa->surface->data,
					stinsa->surface->stride / 4);
			m_poza_corp_stinsa = stinsa;
		}
	}
	clock_gettime(CLOCK_MONOTONIC, &t1);
	m_ms = (int)((t1.tv_sec - t0.tv_sec) * 1000 + (t1.tv_nsec - t0.tv_nsec) / 1000000);
	if (corp)
	{
		/* "HD" = teletextul neted (numele intern); randul il citesc probele */
		eDebug("[eHdsTeletextWidget] pagina %d compusa in %d ms (%s, %s)", m_pagina, m_ms, m_hd ? "HD" : "clasic",
			m_peste ? "peste imagine" : "pe tot ecranul");
		if (a.cu_contur || a.cu_umbra || a.relief)
			eDebug("[eHdsTeletextWidget] optiunile: contur %d, umbra %d, relief %d", a.cu_contur ? 1 : 0, a.cu_umbra ? 1 : 0,
				a.relief ? 1 : 0);
	}
}

int eHdsTeletextWidget::event(int event, void *data, void *data2)
{
	switch (event)
	{
	case evtPaint:
	{
		gPainter &painter = *(gPainter*)data2;
		eWidget::event(event, data, data2);
		/* compunerile cerute de la desenul de dinainte, o singura data */
		compuneCerute();
		/* fereastra s-a curatat chiar inainte (transparent sau negru): copia pastreaza transparenta intocmai */
		if (m_poza_antet)
			painter.blit(m_poza_antet, ePoint(m_x0, m_y0), eRect(), 0);
		ePtr<gPixmap> corp = (m_stinse && m_poza_corp_stinsa) ? m_poza_corp_stinsa : m_poza_corp;
		if (corp)
			painter.blit(corp, ePoint(m_x0, m_y0 + m_i), eRect(), 0);
		return 0;
	}
	case evtChangedSize:
		aseaza();
		reface(true, true);
		return eWidget::event(event, data, data2);
	default:
		return eWidget::event(event, data, data2);
	}
}
