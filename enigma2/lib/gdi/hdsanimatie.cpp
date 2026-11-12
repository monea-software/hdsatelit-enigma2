/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Animatiile ferestrelor desenate de enigma2: vezi lib/gdi/hdsanimatie.h.
 */
#include <lib/gdi/hdsanimatie.h>
#include <string.h>

int hdsAnimatieCurba(long t_us, long durata_us)
{
	if (durata_us <= 0 || t_us >= durata_us)
		return 256;
	if (t_us <= 0)
		return 0;
	/* 1 - (1 - t)^3, in virgula fixa (t in 1/4096) */
	long t = (t_us << 12) / durata_us;
	long r = 4096 - t;
	long r3 = (((r * r) >> 12) * r) >> 12;
	long e = 4096 - r3;
	return (int)((e * 256 + 2048) >> 12);
}

uint32_t hdsAnimatieAmesteca(uint32_t a, uint32_t b, unsigned f)
{
	if (f >= 256)
		return b;
	if (!(a >> 24))
	{
		if (!(b >> 24))
			return f < 128 ? a : b;
		a = b & 0x00FFFFFF;	/* transparent inainte: culoarea de dupa, numai opacitatea creste */
	}
	else if (!(b >> 24))
		b = a & 0x00FFFFFF;	/* transparent dupa: culoarea de inainte, numai opacitatea scade */
	unsigned g = 256 - f;
	uint32_t rb = (((a & 0x00FF00FF) * g + (b & 0x00FF00FF) * f) >> 8) & 0x00FF00FF;
	uint32_t ag = (((a >> 8) & 0x00FF00FF) * g + ((b >> 8) & 0x00FF00FF) * f) & 0xFF00FF00;
	return rb | ag;
}

#if defined(__ARM_NEON) || defined(__ARM_NEON__)
#include <arm_neon.h>
#define HDS_ANIMATIE_NEON 1
#endif

/*
 * Randul amestecat a doi vectori (aparitia treptata, randurile alunecarii si ale maririi). Pe ARM cu NEON (toate receptoarele
 * ARM ale noastre) 16 pixeli odata: pe .122 calculul pixel cu pixel al unui meniu 1776x1000 lua 45-180 ms pe cadru, iar
 * copierea in memoria video numai ~5 ms. Aceeasi regula ca hdsAnimatieAmesteca (transparentul ia culoarea celuilalt), cu
 * ponderi f8 = 0..255 si impartirea exacta la 255: capetele ies exact (f = 0: „inainte” pentru ochi; f = 256: exact „dupa”).
 */
static void amestecaRand(uint32_t *d, const uint32_t *a, const uint32_t *b, int w, unsigned f)
{
	if (f >= 256)
	{
		memcpy(d, b, (size_t)w * 4);
		return;
	}
	int x = 0;
#ifdef HDS_ANIMATIE_NEON
	unsigned f8 = (f * 255 + 128) >> 8;
	uint8x8_t vf = vdup_n_u8((uint8_t)f8), vg = vdup_n_u8((uint8_t)(255 - f8));
	uint8x16_t zero = vdupq_n_u8(0);
	for (; x + 16 <= w; x += 16)
	{
		uint8x16x4_t pa = vld4q_u8((const uint8_t *)(a + x));	/* val[0..3] = B, G, R, A */
		uint8x16x4_t pb = vld4q_u8((const uint8_t *)(b + x));
		uint8x16_t ta = vceqq_u8(pa.val[3], zero), tb = vceqq_u8(pb.val[3], zero);
		uint8x16_t numai_b = vbicq_u8(tb, ta);
		uint8x16x4_t r;
		for (int c = 0; c < 4; ++c)
		{
			uint8x16_t ca = pa.val[c], cb = pb.val[c];
			if (c < 3)
			{
				ca = vbslq_u8(ta, pb.val[c], pa.val[c]);	/* transparent inainte: culoarea de dupa */
				cb = vbslq_u8(numai_b, pa.val[c], pb.val[c]);	/* transparent dupa: culoarea de inainte */
			}
			uint16x8_t lo = vmlal_u8(vmull_u8(vget_low_u8(ca), vg), vget_low_u8(cb), vf);
			uint16x8_t hi = vmlal_u8(vmull_u8(vget_high_u8(ca), vg), vget_high_u8(cb), vf);
			/* x / 255 exact pentru x <= 255 * 255: (x + 128 + ((x + 128) >> 8)) >> 8 */
			lo = vaddq_u16(lo, vdupq_n_u16(128));
			hi = vaddq_u16(hi, vdupq_n_u16(128));
			r.val[c] = vcombine_u8(vshrn_n_u16(vsraq_n_u16(lo, lo, 8), 8), vshrn_n_u16(vsraq_n_u16(hi, hi, 8), 8));
		}
		vst4q_u8((uint8_t *)(d + x), r);
	}
#endif
	for (; x < w; ++x)
	{
		uint32_t pa = a[x], pb = b[x];
		d[x] = (pa == pb) ? pa : hdsAnimatieAmesteca(pa, pb, f);
	}
}

void hdsAnimatieCadru(uint32_t *dst, int pas_dst, const uint32_t *inainte, const uint32_t *dupa, int pas_src, int w, int h,
	int fel, int inchidere, int p, int *tabel)
{
	if (w <= 0 || h <= 0)
		return;
	if (p < 0)
		p = 0;
	if (p > 256)
		p = 256;
	unsigned f = (unsigned)p;
	static const uint32_t gol[1] = { 0 };

	if (fel == gHdsAnimatie::alunecare)
	{
		/* distanta: 1/24 din inaltimea zonei, intre 12 si 48 de pixeli */
		int d = h / 24;
		if (d < 12)
			d = 12;
		if (d > 48)
			d = 48;
		/* deschidere: „dupa” vine de jos (deplasarea scade spre 0); inchidere: „inainte” coboara (creste de la 0) */
		int dep = inchidere ? (d * p + 128) >> 8 : (d * (256 - p) + 128) >> 8;
		uint32_t *gol_rand = (uint32_t *)(tabel + w + h);
		memset(gol_rand, 0, (size_t)w * 4);
		for (int y = 0; y < h; ++y)
		{
			uint32_t *dr = dst + (long)y * pas_dst;
			const uint32_t *ra = inainte + (long)y * pas_src, *rb = dupa + (long)y * pas_src;
			int ys = y - dep;	/* randul din care vine imaginea care se misca */
			if (inchidere)
				ra = (ys >= 0) ? inainte + (long)ys * pas_src : 0;
			else
				rb = (ys >= 0) ? dupa + (long)ys * pas_src : 0;
			amestecaRand(dr, ra ? ra : gol_rand, rb ? rb : gol_rand, w, f);
		}
		return;
	}

	if (fel == gHdsAnimatie::marire)
	{
		/* scara in 1/256: deschidere 236 -> 256 (92% -> 100%) pe „dupa”; inchidere 256 -> 236 pe „inainte” */
		int s = inchidere ? 256 - ((20 * p) >> 8) : 236 + ((20 * p) >> 8);
		int cx = w / 2, cy = h / 2;
		int *col = tabel, *rnd = tabel + w;
		uint32_t *rand_mis = (uint32_t *)(tabel + w + h);
		/* coloanele: crescatoare, deci cele din zona sunt un singur interval [cx0, cx1); in afara lui pixelul e transparent */
		int cx0 = w, cx1 = 0;
		for (int x = 0; x < w; ++x)
		{
			int sx = cx + (((x - cx) * 256) / s);
			col[x] = (sx >= 0 && sx < w) ? sx : -1;
			if (col[x] >= 0)
			{
				if (x < cx0)
					cx0 = x;
				cx1 = x + 1;
			}
		}
		for (int y = 0; y < h; ++y)
		{
			int sy = cy + (((y - cy) * 256) / s);
			rnd[y] = (sy >= 0 && sy < h) ? sy : -1;
		}
		for (int y = 0; y < h; ++y)
		{
			uint32_t *dr = dst + (long)y * pas_dst;
			const uint32_t *fix = (inchidere ? dupa : inainte) + (long)y * pas_src;
			const uint32_t *mis = (rnd[y] >= 0) ? (inchidere ? inainte : dupa) + (long)rnd[y] * pas_src : gol;
			/* randul marit/micsorat adunat intai (pixel cu pixel), apoi amestecat ca la aparitia treptata */
			if (rnd[y] < 0 || cx0 >= cx1)
				memset(rand_mis, 0, (size_t)w * 4);
			else
			{
				if (cx0 > 0)
					memset(rand_mis, 0, (size_t)cx0 * 4);
				for (int x = cx0; x < cx1; ++x)
					rand_mis[x] = mis[col[x]];
				if (cx1 < w)
					memset(rand_mis + cx1, 0, (size_t)(w - cx1) * 4);
			}
			if (inchidere)
				amestecaRand(dr, rand_mis, fix, w, f);
			else
				amestecaRand(dr, fix, rand_mis, w, f);
		}
		return;
	}

	/* aparitia treptata (si orice fel necunoscut) */
	for (int y = 0; y < h; ++y)
		amestecaRand(dst + (long)y * pas_dst, inainte + (long)y * pas_src, dupa + (long)y * pas_src, w, f);
}

static volatile int s_oprire_generatie = 0;

void hdsAnimatieOpreste()
{
	__atomic_add_fetch(&s_oprire_generatie, 1, __ATOMIC_SEQ_CST);
}

#ifndef HDS_ANIMATIE_NUMAI_CADRE
#include <lib/gdi/gpixmap.h>
#include <lib/base/eerror.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static long acumUs()
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (long)t.tv_sec * 1000000L + t.tv_nsec / 1000;
}

/* HDS_ANIM_PROBA=<dosar> in mediu (numai pentru probe): cadrul de la mijloc si cel final, ca PAM, in dosar */
static void scrieProba(const char *nume, const uint32_t *src, int pas, int w, int h)
{
	const char *dosar = getenv("HDS_ANIM_PROBA");
	if (!dosar || !*dosar)
		return;
	char cale[512];
	snprintf(cale, sizeof(cale), "%s/%s.pam", dosar, nume);
	FILE *f = fopen(cale, "wb");
	if (!f)
		return;
	fprintf(f, "P7\nWIDTH %d\nHEIGHT %d\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n", w, h);
	unsigned char *rand = new unsigned char[w * 4];
	for (int y = 0; y < h; ++y)
	{
		const uint32_t *r = src + (long)y * pas;
		for (int x = 0; x < w; ++x)
		{
			rand[x * 4] = (r[x] >> 16) & 0xFF;
			rand[x * 4 + 1] = (r[x] >> 8) & 0xFF;
			rand[x * 4 + 2] = r[x] & 0xFF;
			rand[x * 4 + 3] = r[x] >> 24;
		}
		fwrite(rand, 1, w * 4, f);
	}
	delete[] rand;
	fclose(f);
}

int hdsAnimatieRuleaza(gSurface *ecran, const gSurface *inainte, const gSurface *dupa, const gHdsAnimatie &a,
	void (*arata)(void *), void *ctx)
{
	if (!ecran || !inainte || !dupa || !ecran->data || !inainte->data || !dupa->data)
		return 0;
	if (ecran->bpp != 32 || inainte->bpp != 32 || dupa->bpp != 32)
		return 0;
	/* zona taiata la toate cele trei suprafete */
	int x0 = a.x < 0 ? 0 : a.x, y0 = a.y < 0 ? 0 : a.y;
	int x1 = a.x + a.w, y1 = a.y + a.h;
	const gSurface *s[3] = { ecran, inainte, dupa };
	for (int i = 0; i < 3; ++i)
	{
		if (x1 > s[i]->x)
			x1 = s[i]->x;
		if (y1 > s[i]->y)
			y1 = s[i]->y;
	}
	int w = x1 - x0, h = y1 - y0;
	if (w <= 0 || h <= 0)
		return 0;
	if (inainte->stride != dupa->stride)
		return 0;

	int pas_e = ecran->stride / 4, pas_s = inainte->stride / 4;
	uint32_t *de = (uint32_t *)ecran->data + (long)y0 * pas_e + x0;
	const uint32_t *ia = (const uint32_t *)inainte->data + (long)y0 * pas_s + x0;
	const uint32_t *du = (const uint32_t *)dupa->data + (long)y0 * pas_s + x0;

	int generatie = __atomic_load_n(&s_oprire_generatie, __ATOMIC_SEQ_CST);
	long durata = (long)(a.durata_ms > 0 ? a.durata_ms : 200) * 1000L;
	int *tabel = new int[2 * w + h];
	/* cadrul se scrie direct in pagina vazuta (memoria video primeste scrieri late fara cost mare: pe .122, 7 MB in ~5 ms); ce
	   costa e citirea celor doua imagini din RAM: masurat pe .122, 1920x1080 = 31 ms pe cadru cu NEON, 44 fara, cu procesorul
	   liber, deci banda memoriei hotaraste; un tampon in plus ar mai adauga o scriere si o citire de marimea zonei */
	long start = acumUs(), primul = 0, calcul = 0;
	int cadre = 0, oprita = 0, mijloc = 0;
	for (;;)
	{
		long t = acumUs() - start;
		if (t >= durata)
			break;
		if (__atomic_load_n(&s_oprire_generatie, __ATOMIC_SEQ_CST) != generatie)
		{
			oprita = 1;
			break;
		}
		int p = hdsAnimatieCurba(t, durata);
		long c0 = acumUs();
		hdsAnimatieCadru(de, pas_e, ia, du, pas_s, w, h, a.fel, a.inchidere, p, tabel);
		calcul += acumUs() - c0;
		if (arata)
			arata(ctx);
		++cadre;
		if (!mijloc && p >= 128)
		{
			mijloc = 1;
			scrieProba("cadru-mijloc", de, pas_e, w, h);
		}
		/* cel mult ~60 de cadre pe secunda: o fereastra mica nu tine procesorul ocupat cu cadre pe care ecranul nu le arata */
		long ramas = 16000 - (acumUs() - start - t);
		if (ramas > 1000 && cadre > 1)
			usleep(ramas);
		if (cadre == 1)
		{
			primul = acumUs() - start - t;
			if (primul * 10 > durata * 6)
			{
				oprita = 2;	/* receptor prea lent pentru aceasta zona: direct imaginea finala */
				break;
			}
		}
	}
	delete[] tabel;
	for (int y = 0; y < h; ++y)
		memcpy(de + (long)y * pas_e, du + (long)y * pas_s, (size_t)w * 4);
	if (arata)
		arata(ctx);
	long total = acumUs() - start;
	scrieProba("cadru-final", de, pas_e, w, h);
	eDebug("[HdsAnimatie] fel %d %s zona %dx%d: %d cadre in %ld ms (primul cadru %ld ms, in medie %ld ms pe cadru)%s",
		a.fel, a.inchidere ? "inchidere" : "deschidere", w, h, cadre, total / 1000, primul / 1000,
		cadre ? calcul / cadre / 1000 : 0,
		oprita == 1 ? ", oprita (tasta sau alta animatie)" : oprita == 2 ? ", sarita (cadrul prea lent)" : "");
	return cadre;
}
#endif
