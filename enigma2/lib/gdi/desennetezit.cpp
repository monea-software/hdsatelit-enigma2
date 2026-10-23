/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Desen netezit pe suprafete de 32 de biti. Vezi desennetezit.h pentru conventii.
 *
 * Cum se socoteste acoperirea: pentru fiecare pixel se ia distanta semnata d de la centrul lui pana la
 * marginea formei (negativa inauntru). Acoperirea este 0,5 - d, taiata la 0..1: un pixel cu centrul chiar
 * pe margine e acoperit pe jumatate, unul la o jumatate de pixel inauntru e plin. Pe margini drepte asta e
 * exact aria acoperita a pixelului; pe curbe cu raza de cativa pixeli e o aproximare foarte buna.
 *
 * Ce se parcurge: numai pixelii care pot fi atinsi. Pentru cerc, inel si arc, pe fiecare rand se socotesc
 * direct capetele benzii (din r +- grosime/2 +- 1), nu tot patratul; pentru linie, banda de pe fiecare rand se
 * ia din distanta pana la dreapta suport. Poligonul parcurge dreptunghiul lui si e gandit pentru forme mici
 * (antena, sageti), fiindca fiecare pixel se masoara fata de toate laturile.
 *
 * Sectorul arcului se testeaza cu produse vectoriale fata de directiile de start si de sfarsit, fara atan2 pe
 * pixel. Totul in float (pe ARM fara NEON-ul folosit aici, float si double costa cam la fel; float e destul
 * pentru coordonatele de ecran, iar intrarile peste +-1e6 se resping).
 */

#include <lib/gdi/desennetezit.h>

#include <math.h>
#include <stdint.h>

namespace
{

const float LIMITA_COORDONATE = 1000000.0f;
const unsigned int MAX_VARFURI = 4096;

inline bool finit(float v)
{
	return isfinite(v) && fabsf(v) <= LIMITA_COORDONATE;
}

inline float taie(float v, float jos, float sus)
{
	return v < jos ? jos : (v > sus ? sus : v);
}

/* Amestec "over" cu alfa drept. `sa` = opacitatea sursei 0..255 (acoperire x opacitatea culorii).
   Pixelul din suprafata: 0xAARRGGBB cu AA = opacitate. */
inline void amesteca(uint32_t *p, int sr, int sg, int sb, int sa)
{
	if (sa <= 0)
		return;
	if (sa >= 255)
	{
		*p = 0xFF000000u | ((uint32_t)sr << 16) | ((uint32_t)sg << 8) | (uint32_t)sb;
		return;
	}
	uint32_t d = *p;
	int da = (int)(d >> 24), dr = (int)((d >> 16) & 0xFF), dg = (int)((d >> 8) & 0xFF), db = (int)(d & 0xFF);
	int rest = 255 - sa;
	if (da == 255)
	{
		/* cazul obisnuit: fundalul panzei e opac */
		int r = (sr * sa + dr * rest + 127) / 255;
		int g = (sg * sa + dg * rest + 127) / 255;
		int b = (sb * sa + db * rest + 127) / 255;
		*p = 0xFF000000u | ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;
		return;
	}
	int dw = (da * rest + 127) / 255;	/* cat mai ramane din opacitatea fundalului */
	int oa = sa + dw;
	if (oa <= 0)
	{
		*p = 0;
		return;
	}
	int r = (sr * sa + dr * dw + oa / 2) / oa;
	int g = (sg * sa + dg * dw + oa / 2) / oa;
	int b = (sb * sa + db * dw + oa / 2) / oa;
	if (r > 255) r = 255;
	if (g > 255) g = 255;
	if (b > 255) b = 255;
	*p = ((uint32_t)oa << 24) | ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;
}

/* culoarea si opacitatea ei, gata de amestec */
struct Pensula
{
	int r, g, b, opac;
	uint32_t *pixeli;
	int pas;	/* octeti pe rand */

	inline void pune(int x, int y, float acoperire)
	{
		if (acoperire <= 0.0f)
			return;
		int a;
		if (acoperire >= 1.0f)
			a = opac;
		else
			a = (int)(acoperire * (float)opac + 0.5f);
		amesteca((uint32_t *)((uint8_t *)pixeli + (size_t)y * pas) + x, r, g, b, a);
	}
};

inline float acoperire(float d)
{
	return taie(0.5f - d, 0.0f, 1.0f);
}

/* distanta de la (px,py) la segmentul (ax,ay)-(bx,by) */
inline float distantaSegment(float px, float py, float ax, float ay, float bx, float by)
{
	float vx = bx - ax, vy = by - ay;
	float wx = px - ax, wy = py - ay;
	float l2 = vx * vx + vy * vy;
	float t = 0.0f;
	if (l2 > 0.0f)
		t = taie((wx * vx + wy * vy) / l2, 0.0f, 1.0f);
	float dx = wx - t * vx, dy = wy - t * vy;
	return sqrtf(dx * dx + dy * dy);
}

/* Dreptunghiul de lucru: marginile formei (in float, deja cu +-1 pentru netezire) taiate cu dreptunghiul
   `r`, abia apoi trecute in intregi. Intoarce false daca nu ramane nimic. */
inline bool fereastra(float fx0, float fy0, float fx1, float fy1, const eRect &r, int &x0, int &y0, int &x1, int &y1)
{
	fx0 = taie(floorf(fx0), (float)r.left(), (float)r.right());
	fx1 = taie(ceilf(fx1), (float)r.left(), (float)r.right());
	fy0 = taie(floorf(fy0), (float)r.top(), (float)r.bottom());
	fy1 = taie(ceilf(fy1), (float)r.top(), (float)r.bottom());
	x0 = (int)fx0; x1 = (int)fx1; y0 = (int)fy0; y1 = (int)fy1;
	return x0 < x1 && y0 < y1;
}

/* capetele intregi ale unui interval [a, b] de pe rand, taiate la [lo, hi) */
inline bool interval(float a, float b, int lo, int hi, int &i0, int &i1)
{
	a = taie(floorf(a), (float)lo, (float)hi);
	b = taie(ceilf(b), (float)lo, (float)hi);
	i0 = (int)a; i1 = (int)b;
	return i0 < i1;
}

/* ------------------------------------------------------------------ forme validate, in coordonatele suprafetei */

struct Forma
{
	int tip;
	float x0, y0, x1, y1, raza, jum;	/* jum = grosime / 2 */
	bool inel_intreg;
	bool capete_rotunde;
	float u0x, u0y, u1x, u1y;		/* directiile de start si de sfarsit ale arcului */
	float unghi_arc;			/* 0 < unghi_arc < 360 */
	std::vector<float> puncte;
	float mx0, my0, mx1, my1;		/* marginile, cu +1 pentru netezire */
};

bool pregateste(const gDesenNetezit &d, float ox, float oy, Forma &f)
{
	f.tip = d.forma;
	switch (d.forma)
	{
	case gDesenNetezit::linie:
	{
		if (!finit(d.x0) || !finit(d.y0) || !finit(d.x1) || !finit(d.y1) || !finit(d.grosime) || !(d.grosime > 0.0f))
			return false;
		f.x0 = d.x0 + ox; f.y0 = d.y0 + oy; f.x1 = d.x1 + ox; f.y1 = d.y1 + oy;
		f.jum = d.grosime * 0.5f;
		float m = f.jum + 1.0f;
		f.mx0 = fminf(f.x0, f.x1) - m; f.mx1 = fmaxf(f.x0, f.x1) + m;
		f.my0 = fminf(f.y0, f.y1) - m; f.my1 = fmaxf(f.y0, f.y1) + m;
		return true;
	}
	case gDesenNetezit::disc:
	{
		if (!finit(d.x0) || !finit(d.y0) || !finit(d.raza) || !(d.raza > 0.0f))
			return false;
		f.x0 = d.x0 + ox; f.y0 = d.y0 + oy; f.raza = d.raza;
		float m = f.raza + 1.0f;
		f.mx0 = f.x0 - m; f.mx1 = f.x0 + m; f.my0 = f.y0 - m; f.my1 = f.y0 + m;
		return true;
	}
	case gDesenNetezit::arc:
	{
		if (!finit(d.x0) || !finit(d.y0) || !finit(d.raza) || !(d.raza > 0.0f) || !finit(d.grosime) || !(d.grosime > 0.0f)
			|| !isfinite(d.start) || !isfinite(d.unghi_arc))
			return false;
		f.x0 = d.x0 + ox; f.y0 = d.y0 + oy; f.raza = d.raza; f.jum = d.grosime * 0.5f;
		f.capete_rotunde = d.capete_rotunde != 0;
		float start = d.start, arc = d.unghi_arc;
		if (arc == 0.0f)
			return false;
		f.inel_intreg = fabsf(arc) >= 360.0f;
		if (!f.inel_intreg)
		{
			if (arc < 0.0f)
			{
				/* acelasi arc, parcurs invers: pornim de la celalalt capat */
				start += arc;
				arc = -arc;
			}
			start = fmodf(start, 360.0f);
			if (start < 0.0f)
				start += 360.0f;
			f.unghi_arc = arc;
			const float grad = (float)M_PI / 180.0f;
			f.u0x = cosf(start * grad); f.u0y = sinf(start * grad);
			f.u1x = cosf((start + arc) * grad); f.u1y = sinf((start + arc) * grad);
		}
		float m = f.raza + f.jum + 1.0f;
		f.mx0 = f.x0 - m; f.mx1 = f.x0 + m; f.my0 = f.y0 - m; f.my1 = f.y0 + m;
		return true;
	}
	case gDesenNetezit::poligon:
	{
		size_t n = d.puncte.size() / 2;
		if (n < 3 || n > MAX_VARFURI)
			return false;
		f.puncte.resize(n * 2);
		for (size_t i = 0; i < n; ++i)
		{
			float x = d.puncte[2 * i], y = d.puncte[2 * i + 1];
			if (!finit(x) || !finit(y))
				return false;
			f.puncte[2 * i] = x + ox;
			f.puncte[2 * i + 1] = y + oy;
			if (i == 0)
			{
				f.mx0 = f.mx1 = x + ox;
				f.my0 = f.my1 = y + oy;
			}
			else
			{
				f.mx0 = fminf(f.mx0, x + ox); f.mx1 = fmaxf(f.mx1, x + ox);
				f.my0 = fminf(f.my0, y + oy); f.my1 = fmaxf(f.my1, y + oy);
			}
		}
		f.mx0 -= 1.0f; f.my0 -= 1.0f; f.mx1 += 1.0f; f.my1 += 1.0f;
		return true;
	}
	default:
		return false;
	}
}

/* ------------------------------------------------------------------ rasterizarea, pe un dreptunghi de taiere */

void linie(const Forma &f, const eRect &r, Pensula &p)
{
	int x0, y0, x1, y1;
	if (!fereastra(f.mx0, f.my0, f.mx1, f.my1, r, x0, y0, x1, y1))
		return;
	/* dreapta suport: nx*x + ny*y + c = 0, cu (nx, ny) unitar; pe rand, pixelii atinsi sunt in banda
	   |nx*x + ny*y + c| <= jum + 1 (capetele rotunde stau si ele in banda asta) */
	float vx = f.x1 - f.x0, vy = f.y1 - f.y0;
	float l2 = vx * vx + vy * vy;
	float l = sqrtf(l2);
	float nx = 0.0f, ny = 0.0f, c = 0.0f;
	if (l > 0.0f)
	{
		nx = -vy / l; ny = vx / l;
		c = -(nx * f.x0 + ny * f.y0);
	}
	bool banda = l > 0.0f && fabsf(nx) > 1e-4f;
	/* miezul: pixelii la cel mult jum-0,5 de dreapta suport si cu proiectia in interiorul segmentului au
	   acoperirea 1, fara radical (bara de progres, de exemplu, e aproape numai miez) */
	float k = f.jum - 0.5f;
	bool are_miez = l > 0.0f && k > 0.0f;
	float m = f.jum + 1.0f;
	for (int y = y0; y < y1; ++y)
	{
		float py = (float)y + 0.5f;
		int a = x0, b = x1;
		if (banda)
		{
			float s0 = (-m - ny * py - c) / nx, s1 = (m - ny * py - c) / nx;
			if (s0 > s1) { float t = s0; s0 = s1; s1 = t; }
			if (!interval(s0 - 0.5f, s1 + 0.5f, x0, x1, a, b))
				continue;
		}
		int ma = b, mb = b;
		if (are_miez)
		{
			/* conditia pe distanta pana la dreapta: un interval de x (sau tot randul, daca linia e orizontala) */
			float lo = -1e30f, hi = 1e30f;
			if (banda)
			{
				float s0 = (-k - ny * py - c) / nx, s1 = (k - ny * py - c) / nx;
				lo = fminf(s0, s1); hi = fmaxf(s0, s1);
			}
			else if (fabsf(ny * py + c) > k)
				lo = 1e30f;
			/* proiectia pe segment intre 0 si 1: t = ((px-x0)*vx + (py-y0)*vy) / l2 */
			float w = (py - f.y0) * vy;
			if (fabsf(vx) > 1e-6f)
			{
				float t0 = f.x0 - w / vx, t1 = f.x0 + (l2 - w) / vx;
				lo = fmaxf(lo, fminf(t0, t1)); hi = fminf(hi, fmaxf(t0, t1));
			}
			else if (w < 0.0f || w > l2)
				lo = 1e30f;
			if (lo <= hi)
			{
				/* pixelii cu centrul x+0,5 in [lo, hi] */
				float s0 = ceilf(lo - 0.5f), s1 = floorf(hi - 0.5f);
				if (s0 <= s1)
				{
					ma = (int)taie(s0, (float)a, (float)b);
					mb = (int)taie(s1 + 1.0f, (float)a, (float)b);
				}
			}
		}
		for (int x = a; x < b; ++x)
		{
			if (x == ma && ma < mb)
			{
				for (; x < mb; ++x)
					p.pune(x, y, 1.0f);
				if (x >= b)
					break;
			}
			float d = distantaSegment((float)x + 0.5f, py, f.x0, f.y0, f.x1, f.y1) - f.jum;
			p.pune(x, y, acoperire(d));
		}
	}
}

void disc(const Forma &f, const eRect &r, Pensula &p)
{
	int x0, y0, x1, y1;
	if (!fereastra(f.mx0, f.my0, f.mx1, f.my1, r, x0, y0, x1, y1))
		return;
	float afara = f.raza + 1.0f, miez = f.raza - 1.0f;
	for (int y = y0; y < y1; ++y)
	{
		float dy = (float)y + 0.5f - f.y0;
		if (fabsf(dy) >= afara)
			continue;
		float xs = sqrtf(afara * afara - dy * dy);
		int a, b;
		if (!interval(f.x0 - xs - 0.5f, f.x0 + xs + 0.5f, x0, x1, a, b))
			continue;
		/* miezul, unde acoperirea e sigur 1: fara radical pe pixel */
		int ma = b, mb = b;
		if (miez > 0.0f && fabsf(dy) < miez)
		{
			float xi = sqrtf(miez * miez - dy * dy);
			/* pixelii cu centrul la cel mult raza-1 de centru sunt plini: acolo nu se mai socoteste nimic */
			float s0 = ceilf(f.x0 - xi - 0.5f), s1 = floorf(f.x0 + xi - 0.5f);
			if (s0 <= s1)
			{
				ma = (int)taie(s0, (float)a, (float)b);
				mb = (int)taie(s1 + 1.0f, (float)a, (float)b);
			}
		}
		for (int x = a; x < b; ++x)
		{
			if (x == ma && ma < mb)
			{
				for (; x < mb; ++x)
					p.pune(x, y, 1.0f);
				if (x >= b)
					break;
			}
			float dx = (float)x + 0.5f - f.x0;
			float d = sqrtf(dx * dx + dy * dy) - f.raza;
			p.pune(x, y, acoperire(d));
		}
	}
}

/* v in sectorul care pleaca din u0 si merge unghi_arc grade in sensul pozitiv */
inline bool inSector(const Forma &f, float vx, float vy)
{
	float c0 = f.u0x * vy - f.u0y * vx;	/* > 0: v e dupa u0 */
	float c1 = vx * f.u1y - vy * f.u1x;	/* > 0: v e inainte de u1 */
	if (f.unghi_arc <= 180.0f)
		return c0 >= 0.0f && c1 >= 0.0f;
	/* peste 180: e in sector daca NU e strict in sectorul ramas (de la u1 la u0, sub 180) */
	float r0 = f.u1x * vy - f.u1y * vx;
	float r1 = vx * f.u0y - vy * f.u0x;
	return !(r0 > 0.0f && r1 > 0.0f);
}

inline float distantaArc(const Forma &f, float vx, float vy)
{
	float lung = sqrtf(vx * vx + vy * vy);
	float inel = fabsf(lung - f.raza) - f.jum;
	if (f.inel_intreg)
		return inel;
	if (inSector(f, vx, vy))
	{
		if (f.capete_rotunde)
			return inel;
		/* capete drepte: si distanta pana la cele doua raze de capat, pe dinauntru. O raza conteaza numai
		   pentru punctele din fata ei (produs scalar > 0) si de partea sectorului (produs vectorial >= 0):
		   la arcuri peste 180 de grade, un punct din sector poate fi in fata razei de start dar de cealalta
		   parte a ei, departe de capat (proba cu arcul de 300 de grade a prins asta: lipsea o cincime). */
		float e = 1e30f;
		float c0 = f.u0x * vy - f.u0y * vx, c1 = vx * f.u1y - vy * f.u1x;
		if (c0 >= 0.0f && vx * f.u0x + vy * f.u0y > 0.0f)
			e = fminf(e, c0);
		if (c1 >= 0.0f && vx * f.u1x + vy * f.u1y > 0.0f)
			e = fminf(e, c1);
		return fmaxf(inel, -e);
	}
	if (f.capete_rotunde)
	{
		float ax = f.raza * f.u0x - vx, ay = f.raza * f.u0y - vy;
		float bx = f.raza * f.u1x - vx, by = f.raza * f.u1y - vy;
		return sqrtf(fminf(ax * ax + ay * ay, bx * bx + by * by)) - f.jum;
	}
	/* capete drepte: distanta pana la segmentele de capat (de-a lungul razei, de la r-jum la r+jum) */
	float ri = f.raza - f.jum, re = f.raza + f.jum;
	float d0 = distantaSegment(vx, vy, ri * f.u0x, ri * f.u0y, re * f.u0x, re * f.u0y);
	float d1 = distantaSegment(vx, vy, ri * f.u1x, ri * f.u1y, re * f.u1x, re * f.u1y);
	return fminf(d0, d1);
}

void arc(const Forma &f, const eRect &r, Pensula &p)
{
	int x0, y0, x1, y1;
	if (!fereastra(f.mx0, f.my0, f.mx1, f.my1, r, x0, y0, x1, y1))
		return;
	float afara = f.raza + f.jum + 1.0f, gol = f.raza - f.jum - 1.0f;
	for (int y = y0; y < y1; ++y)
	{
		float dy = (float)y + 0.5f - f.y0;
		if (fabsf(dy) >= afara)
			continue;
		float xs = sqrtf(afara * afara - dy * dy);
		/* pe rand: una sau doua benzi, [c-xs, c-xi] si [c+xi, c+xs], unde xi e golul din mijloc */
		float xi = -1.0f;
		if (gol > 0.0f && fabsf(dy) < gol)
			xi = sqrtf(gol * gol - dy * dy);
		float benzi[2][2];
		int nb = 0;
		if (xi > 0.0f)
		{
			benzi[0][0] = f.x0 - xs - 0.5f; benzi[0][1] = f.x0 - xi + 0.5f;
			benzi[1][0] = f.x0 + xi - 0.5f; benzi[1][1] = f.x0 + xs + 0.5f;
			nb = 2;
		}
		else
		{
			benzi[0][0] = f.x0 - xs - 0.5f; benzi[0][1] = f.x0 + xs + 0.5f;
			nb = 1;
		}
		int ultim = x0;
		for (int k = 0; k < nb; ++k)
		{
			int a, b;
			if (!interval(benzi[k][0], benzi[k][1], x0, x1, a, b))
				continue;
			if (a < ultim)
				a = ultim;	/* benzile nu se suprapun, dar nici un pixel nu se amesteca de doua ori */
			for (int x = a; x < b; ++x)
				p.pune(x, y, acoperire(distantaArc(f, (float)x + 0.5f - f.x0, dy)));
			if (b > ultim)
				ultim = b;
		}
	}
}

void poligon(const Forma &f, const eRect &r, Pensula &p)
{
	int x0, y0, x1, y1;
	if (!fereastra(f.mx0, f.my0, f.mx1, f.my1, r, x0, y0, x1, y1))
		return;
	const size_t n = f.puncte.size() / 2;
	const float *v = &f.puncte[0];
	for (int y = y0; y < y1; ++y)
	{
		float py = (float)y + 0.5f;
		for (int x = x0; x < x1; ++x)
		{
			float px = (float)x + 0.5f;
			float d2 = 1e30f;
			bool inauntru = false;
			for (size_t i = 0, j = n - 1; i < n; j = i++)
			{
				float ax = v[2 * j], ay = v[2 * j + 1], bx = v[2 * i], by = v[2 * i + 1];
				/* regula par-impar: raza orizontala spre dreapta */
				if ((ay > py) != (by > py) && px < ax + (py - ay) * (bx - ax) / (by - ay))
					inauntru = !inauntru;
				float ex = bx - ax, ey = by - ay, wx = px - ax, wy = py - ay;
				float l2 = ex * ex + ey * ey;
				float t = l2 > 0.0f ? taie((wx * ex + wy * ey) / l2, 0.0f, 1.0f) : 0.0f;
				float dx = wx - t * ex, dy = wy - t * ey;
				float q = dx * dx + dy * dy;
				if (q < d2)
					d2 = q;
			}
			if (!inauntru && d2 >= 2.25f)
				continue;	/* mai departe de 1,5 pixeli de margine, pe dinafara: nimic */
			float d = sqrtf(d2);
			p.pune(x, y, acoperire(inauntru ? -d : d));
		}
	}
}

} /* namespace */

void deseneazaNetezit(gSurface *s, const gRegion &taiere, const ePoint &offset, const gDesenNetezit &d)
{
	if (!s || !s->data || s->bpp != 32 || s->x <= 0 || s->y <= 0)
		return;
	int opac = 255 - (int)d.culoare.a;
	if (opac <= 0)
		return;
	Forma f;
	if (!pregateste(d, (float)offset.x(), (float)offset.y(), f))
		return;

	Pensula p;
	p.r = d.culoare.r; p.g = d.culoare.g; p.b = d.culoare.b; p.opac = opac;
	p.pixeli = (uint32_t *)s->data;
	p.pas = s->stride;

	const eRect suprafata(0, 0, s->x, s->y);
	for (std::vector<eRect>::const_iterator i = taiere.rects.begin(); i != taiere.rects.end(); ++i)
	{
		eRect r = *i & suprafata;
		if (r.empty())
			continue;
		switch (f.tip)
		{
		case gDesenNetezit::linie: linie(f, r, p); break;
		case gDesenNetezit::disc: disc(f, r, p); break;
		case gDesenNetezit::arc: arc(f, r, p); break;
		case gDesenNetezit::poligon: poligon(f, r, p); break;
		}
	}
}

eRect margineDesenNetezit(const gDesenNetezit &d, const eRect &limite)
{
	Forma f;
	if (!pregateste(d, 0.0f, 0.0f, f))
		return eRect(0, 0, 0, 0);
	int x0, y0, x1, y1;
	if (!fereastra(f.mx0, f.my0, f.mx1, f.my1, limite, x0, y0, x1, y1))
		return eRect(0, 0, 0, 0);
	return eRect(x0, y0, x1 - x0, y1 - y0);
}
