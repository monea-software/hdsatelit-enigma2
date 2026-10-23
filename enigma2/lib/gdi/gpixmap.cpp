/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <cstdlib>
#include <cstring>
#include <lib/gdi/gpixmap.h>
#include <lib/gdi/region.h>
#include <lib/gdi/accel.h>
#include <lib/gdi/hdsgpu.h>
#include <byteswap.h>

#ifndef BYTE_ORDER
#error "no BYTE_ORDER defined!"
#endif

gLookup::gLookup()
	:size(0), lookup(0)
{
}

gLookup::gLookup(int size, const gPalette &pal, const gRGB &start, const gRGB &end)
	:size(0), lookup(0)
{
	build(size, pal, start, end);
}

void gLookup::build(int _size, const gPalette &pal, const gRGB &start, const gRGB &end)
{
	if (lookup)
	{
		delete [] lookup;
		lookup=0;
		size=0;
	}
	size=_size;
	if (!size)
		return;
	lookup=new gColor[size];
	
	for (int i=0; i<size; i++)
	{
		gRGB col;
		if (i)
		{
			int rdiff=-start.r+end.r;
			int gdiff=-start.g+end.g;
			int bdiff=-start.b+end.b;
			int adiff=-start.a+end.a;
			rdiff*=i; rdiff/=(size-1);
			gdiff*=i; gdiff/=(size-1);
			bdiff*=i; bdiff/=(size-1);
			adiff*=i; adiff/=(size-1);
			col.r=start.r+rdiff;
			col.g=start.g+gdiff;
			col.b=start.b+bdiff;
			col.a=start.a+adiff;
		} else
			col=start;
		lookup[i]=pal.findColor(col);
	}
}

gSurface::gSurface()
{
	x = 0;
	y = 0;
	bpp = 0;
	bypp = 0;
	stride = 0;
	data = 0;
	data_phys = 0;
	clut.colors = 0;
	clut.data = 0;
	type = 0;
}

gSurface::gSurface(eSize size, int _bpp, int accel)
{
	x = size.width();
	y = size.height();
	bpp = _bpp;

	switch (bpp)
	{
	case 8:
		bypp = 1;
		break;
	case 15:
	case 16:
		bypp = 2;
		break;
	case 24:		// never use 24bit mode
	case 32:
		bypp = 4;
		break;
	default:
		bypp = (bpp+7)/8;
	}

	stride = x*bypp;
	
	data = 0;
	data_phys = 0;
	
	if (accel)
	{
		stride += 63;
		stride &=~63;
		
		int pal_size = 0;
		if (bpp == 8)
			pal_size = 256 * 4;
		
		if (gAccel::getInstance())
			eDebug("accel memory: %d", gAccel::getInstance()->accelAlloc(data, data_phys, y * stride + pal_size));
		else
			eDebug("no accel available");
	}
	
	clut.colors = 0;
	clut.data = 0;

	if (!data)
		data = new unsigned char [y * stride];
	
	type = 1;
}

gSurface::~gSurface()
{
	if (type)
	{
		if (data_phys)
			gAccel::getInstance()->accelFree(data_phys);
		else
			delete [] (unsigned char*)data;

		delete [] clut.data;
	}
}

gPixmap *gPixmap::lock()
{
	contentlock.lock(1);
	return this;
}

void gPixmap::unlock()
{
	contentlock.unlock(1);
}

void gPixmap::fill(const gRegion &region, const gColor &color)
{
	unsigned int i;
	for (i=0; i<region.rects.size(); ++i)
	{
		const eRect &area = region.rects[i];
		if (area.empty())
			continue;

		if (surface->bpp == 8)
		{
			for (int y=area.top(); y<area.bottom(); y++)
		 		memset(((__u8*)surface->data)+y*surface->stride+area.left(), color.color, area.width());
		} else if (surface->bpp == 16)
		{
			__u32 icol;

			if (surface->clut.data && color < surface->clut.colors)
				icol=(surface->clut.data[color].a<<24)|(surface->clut.data[color].r<<16)|(surface->clut.data[color].g<<8)|(surface->clut.data[color].b);
			else
				icol=0x10101*color;
#if BYTE_ORDER == LITTLE_ENDIAN
			__u16 col = bswap_16(((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19);
#else
			__u16 col = ((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19;
#endif
			for (int y=area.top(); y<area.bottom(); y++)
			{
				__u16 *dst=(__u16*)(((__u8*)surface->data)+y*surface->stride+area.left()*surface->bypp);
				int x=area.width();
				while (x--)
					*dst++=col;
			}
		} else if (surface->bpp == 32)
		{
			__u32 col;

			if (surface->clut.data && color < surface->clut.colors)
				col=(surface->clut.data[color].a<<24)|(surface->clut.data[color].r<<16)|(surface->clut.data[color].g<<8)|(surface->clut.data[color].b);
			else
				col=0x10101*color;
			
			col^=0xFF000000;
			
			if (surface->data_phys && gAccel::getInstance())
				if (!gAccel::getInstance()->fill(surface,  area, col))
					continue;

			for (int y=area.top(); y<area.bottom(); y++)
			{
				__u32 *dst=(__u32*)(((__u8*)surface->data)+y*surface->stride+area.left()*surface->bypp);
				int x=area.width();
				while (x--)
					*dst++=col;
			}
		}	else
			eWarning("couldn't fill %d bpp", surface->bpp);
	}
}

void gPixmap::fill(const gRegion &region, const gRGB &color)
{
	unsigned int i;
	for (i=0; i<region.rects.size(); ++i)
	{
		const eRect &area = region.rects[i];
		if (area.empty())
			continue;

		if (surface->bpp == 32)
		{
			__u32 col;

			col = color.argb();
			col^=0xFF000000;

			if (surface->data_phys && gAccel::getInstance())
				if (!gAccel::getInstance()->fill(surface,  area, col))
					continue;

			for (int y=area.top(); y<area.bottom(); y++)
			{
				__u32 *dst=(__u32*)(((__u8*)surface->data)+y*surface->stride+area.left()*surface->bypp);
				int x=area.width();
				while (x--)
					*dst++=col;
			}
		} else if (surface->bpp == 16)
		{
			__u32 icol = color.argb();
#if BYTE_ORDER == LITTLE_ENDIAN
			__u16 col = bswap_16(((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19);
#else
			__u16 col = ((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19;
#endif
			for (int y=area.top(); y<area.bottom(); y++)
			{
				__u16 *dst=(__u16*)(((__u8*)surface->data)+y*surface->stride+area.left()*surface->bypp);
				int x=area.width();
				while (x--)
					*dst++=col;
			}
		}	else
			eWarning("couldn't rgbfill %d bpp", surface->bpp);
	}
}

static inline void blit_8i_to_32(__u32 *dst, __u8 *src, __u32 *pal, int width)
{
	while (width--)
		*dst++=pal[*src++];
}

static inline void blit_8i_to_32_at(__u32 *dst, __u8 *src, __u32 *pal, int width)
{
	while (width--)
	{
		if (!(pal[*src]&0x80000000))
		{
			src++;
			dst++;
		} else
			*dst++=pal[*src++];
	}
}

static inline void blit_8i_to_16(__u16 *dst, __u8 *src, __u32 *pal, int width)
{
	while (width--)
		*dst++=pal[*src++] & 0xFFFF;
}

static inline void blit_8i_to_16_at(__u16 *dst, __u8 *src, __u32 *pal, int width)
{
	while (width--)
	{
		if (!(pal[*src]&0x80000000))
		{
			src++;
			dst++;
		} else
			*dst++=pal[*src++] & 0xFFFF;
	}
}

		/* WARNING, this function is not endian safe! */
static void blit_8i_to_32_ab(__u32 *dst, __u8 *src, __u32 *pal, int width)
{
	while (width--)
	{
#define BLEND(x, y, a) (y + (((x-y) * a)>>8))
		__u32 srccol = pal[*src++];
		__u32 dstcol = *dst;
		unsigned char sb = srccol & 0xFF;
		unsigned char sg = (srccol >> 8) & 0xFF;
		unsigned char sr = (srccol >> 16) & 0xFF;
		unsigned char sa = (srccol >> 24) & 0xFF;

		unsigned char db = dstcol & 0xFF;
		unsigned char dg = (dstcol >> 8) & 0xFF;
		unsigned char dr = (dstcol >> 16) & 0xFF;
		unsigned char da = (dstcol >> 24) & 0xFF;

		da = BLEND(0xFF, da, sa) & 0xFF;
		dr = BLEND(sr, dr, sa) & 0xFF;
		dg = BLEND(sg, dg, sa) & 0xFF;
		db = BLEND(sb, db, sa) & 0xFF;

#undef BLEND
		*dst++ = db | (dg << 8) | (dr << 16) | (da << 24);
	}
}

/* the largest source or destination side for a scaled blit: the 16.16 fixed point in gPixmap::blit and the
   integer steps in blit_scaled_sw stay far from overflow */
static const int blit_scale_max = 16384;

/* one pixel of blit_8i_to_32_ab (same formula), so a scaled pixmap blends exactly like an unscaled one */
static inline __u32 blend_8i_pixel(__u32 srccol, __u32 dstcol)
{
	int sb = srccol & 0xFF;
	int sg = (srccol >> 8) & 0xFF;
	int sr = (srccol >> 16) & 0xFF;
	int sa = (srccol >> 24) & 0xFF;
	int db = dstcol & 0xFF;
	int dg = (dstcol >> 8) & 0xFF;
	int dr = (dstcol >> 16) & 0xFF;
	int da = (dstcol >> 24) & 0xFF;
	da = (da + (((0xFF - da) * sa) >> 8)) & 0xFF;
	dr = (dr + (((sr - dr) * sa) >> 8)) & 0xFF;
	dg = (dg + (((sg - dg) * sa) >> 8)) & 0xFF;
	db = (db + (((sb - db) * sa) >> 8)) & 0xFF;
	return (__u32)db | ((__u32)dg << 8) | ((__u32)dr << 16) | ((__u32)da << 24);
}

/* one pixel of the 32 bpp alpha blend in gPixmap::blit (same formula, bytes in memory order) */
static inline void blend_32_pixel(unsigned char *dst, const unsigned char *src)
{
	int sa = src[3], sr = src[2], sg = src[1], sb = src[0];
	int da = dst[3], dr = dst[2], dg = dst[1], db = dst[0];
	dst[3] = (unsigned char)(da + ((0xFF - da) * sa) / 256);
	dst[2] = (unsigned char)(dr + ((sr - dr) * sa) / 256);
	dst[1] = (unsigned char)(dg + ((sg - dg) * sa) / 256);
	dst[0] = (unsigned char)(db + ((sb - db) * sa) / 256);
}

/*
 * One screen row of the scaled blit. d[0..width-1] gets the source pixels s[rx], rx = 0, 1, ... growing by
 * inc_q and by one more whenever rem (the remainder, started by the caller) reaches den; the caller has read
 * exactly the columns this row can reach into s (the steps are exact integers, so rx never passes them).
 * Transparency as in the unscaled blit. Kept out of line on purpose: inlined into gPixmap::blit, -Os kept these
 * values on the stack and the loop took about 27 ARM instructions a pixel; here each loop is about 10.
 */
static void __attribute__((noinline)) blit_scaled_row_8(__u32 *d, const __u8 *s, const __u32 *pal, int width, int rem, int inc_q, int inc_r, int den, int flag)
{
	int rx = 0;
	if (flag & gPixmap::blitAlphaTest)
	{
		for (int x = 0; x < width; ++x)
		{
			const __u32 c = pal[s[rx]];
			if (c & 0x80000000)
				d[x] = c;
			rx += inc_q;
			rem += inc_r;
			if (rem >= den)
			{
				rem -= den;
				++rx;
			}
		}
	}
	else if (flag & gPixmap::blitAlphaBlend)
	{
		for (int x = 0; x < width; ++x)
		{
			d[x] = blend_8i_pixel(pal[s[rx]], d[x]);
			rx += inc_q;
			rem += inc_r;
			if (rem >= den)
			{
				rem -= den;
				++rx;
			}
		}
	}
	else
	{
		for (int x = 0; x < width; ++x)
		{
			d[x] = pal[s[rx]];
			rx += inc_q;
			rem += inc_r;
			if (rem >= den)
			{
				rem -= den;
				++rx;
			}
		}
	}
}

static void __attribute__((noinline)) blit_scaled_row_32(__u32 *d, const __u32 *s, int width, int rem, int inc_q, int inc_r, int den, int flag)
{
	int rx = 0;
	if (flag & gPixmap::blitAlphaTest)
	{
		for (int x = 0; x < width; ++x)
		{
			const __u32 c = s[rx];
			if (c & 0xFF000000)
				d[x] = c;
			rx += inc_q;
			rem += inc_r;
			if (rem >= den)
			{
				rem -= den;
				++rx;
			}
		}
	}
	else if (flag & gPixmap::blitAlphaBlend)
	{
		for (int x = 0; x < width; ++x)
		{
			blend_32_pixel((unsigned char*)(d + x), (const unsigned char*)(s + rx));
			rx += inc_q;
			rem += inc_r;
			if (rem >= den)
			{
				rem -= den;
				++rx;
			}
		}
	}
	else
	{
		for (int x = 0; x < width; ++x)
		{
			d[x] = s[rx];
			rx += inc_q;
			rem += inc_r;
			if (rem >= den)
			{
				rem -= den;
				++rx;
			}
		}
	}
}

/* two premultiplied ARGB colours mixed as c0 * (256 - w) / 256 + c1 * w / 256, w 0..255, two channels at a time
   (each 8-bit channel times at most 256 stays inside its 16-bit lane) */
static inline __u32 lerp_argb(__u32 c0, __u32 c1, unsigned int w)
{
	const unsigned int iw = 256 - w;
	const __u32 rb = (((c0 & 0x00FF00FF) * iw + (c1 & 0x00FF00FF) * w) >> 8) & 0x00FF00FF;
	const __u32 ag = ((((c0 >> 8) & 0x00FF00FF) * iw + ((c1 >> 8) & 0x00FF00FF) * w) >> 8) & 0x00FF00FF;
	return rb | (ag << 8);
}

/* straight ARGB -> premultiplied ARGB (r * a / 255, rounded) */
static inline __u32 premultiply_argb(__u32 c)
{
	const unsigned int a = c >> 24;
	if (a == 0xFF)
		return c;
	if (a == 0)
		return 0;
	const unsigned int r = (((c >> 16) & 0xFF) * a + 127) / 255;
	const unsigned int g = (((c >> 8) & 0xFF) * a + 127) / 255;
	const unsigned int b = ((c & 0xFF) * a + 127) / 255;
	return (a << 24) | (r << 16) | (g << 8) | b;
}

/*
 * Enlarging plain copy with bilinear filtering (DVB subtitles: the 720x576 page on the 1920x1080 window, about
 * 2.7 times wider and 1.9 times higher). With the nearest pixel every source pixel became a block of 2-3 screen
 * pixels (very pixelated). Here each screen pixel mixes the 4 source pixels around its
 * centre, weighted by distance, like the hardware scalers do.
 * The mix is done on premultiplied colour (r*a, g*a, b*a, a): the transparent pixels around the letters have any
 * colour (often black) and would otherwise darken the edges. The result is written with straight alpha, as the
 * unscaled blit writes it.
 * Screen pixel centre x maps to source x = (x - pos.left + 0.5) * srcw / pw - 0.5, kept inside 0..srcw-1, the
 * same for y (16.16 fixed point, 8-bit weights), so a pixel is the same however the clip cuts the area.
 * Two passes: each source row needed is mixed horizontally once into hrow[] (premultiplied), and each screen row
 * mixes the two cached rows around it. The used part of a source row is read once with memcpy (the source may be
 * in uncached framebuffer memory). No allocation: 2 x 16 KB rows, 16 KB source row, palette on the stack.
 * Returns false (nothing drawn) when the area or the source span is too wide for the row buffers.
 */
static bool __attribute__((noinline)) blit_scaled_bilinear(gSurface *dst, const gSurface *src, const eRect &pos, const eRect &area)
{
	const int srcw = src->x, srch = src->y;
	const int pw = pos.width(), ph = pos.height();
	const int width = area.width();
	enum { row_max = blit_scale_max / 4 }; /* 4096 pixels */
	if ((width <= 0) || (width > row_max))
		return false;

	const int max_fx = (srcw - 1) << 16, max_fy = (srch - 1) << 16;
	/* source x (16.16) of column x is ((2 * (x - pos.left) + 1) * srcw << 16) / (2 * pw) - 0.5, kept exact from
	   column to column as quotient and remainder of den_x (no drift, no division per pixel) */
	const int den_x = 2 * pw;
	const long long num_first = ((2LL * (area.left() - pos.left()) + 1) * srcw) << 16;
	const int q_first = (int)(num_first / den_x), r_first = (int)(num_first % den_x);
	const int inc_q = (int)((2LL * srcw << 16) / den_x), inc_r = (int)((2LL * srcw << 16) % den_x);
	const int fx_first = q_first - 32768;
	const int fx_last = (int)((((2LL * (area.right() - 1 - pos.left()) + 1) * srcw) << 16) / den_x) - 32768;
	const int sx_lo = (fx_first <= 0) ? 0 : ((fx_first >= max_fx) ? (srcw - 1) : (fx_first >> 16));
	int sx_hi = ((fx_last <= 0) ? 0 : ((fx_last >= max_fx) ? (srcw - 1) : (fx_last >> 16))) + 1;
	if (sx_hi > srcw - 1)
		sx_hi = srcw - 1;
	const int span_px = sx_hi - sx_lo + 1;
	if ((span_px <= 0) || (span_px * src->bypp > (int)(sizeof(__u32) * row_max)))
		return false;

	__u32 srow[row_max];      /* 16 KB: the used part of one source row, as read */
	__u32 hrow[2][row_max];   /* 2 x 16 KB: source rows mixed horizontally, premultiplied */
	int hrow_sy[2] = { -1, -1 };
	__u32 ppal[256];          /* premultiplied palette (8 bpp) */
	unsigned int recip[256];  /* 255 * 65536 / a, to undo the premultiplication */

	if (src->bpp == 8)
	{
		for (int i = 0; i < 256; ++i)
		{
			__u32 c;
			if (src->clut.data && (i < src->clut.colors))
				c = ((__u32)src->clut.data[i].a << 24) | ((__u32)src->clut.data[i].r << 16) | ((__u32)src->clut.data[i].g << 8) | (__u32)src->clut.data[i].b;
			else
				c = 0x010101 * i;
			ppal[i] = premultiply_argb(c ^ 0xFF000000); /* clut a is transparency: 0 = opaque */
		}
	}
	recip[0] = 0;
	for (int a = 1; a < 256; ++a)
		recip[a] = (255u * 65536u + (unsigned int)a / 2) / (unsigned int)a;

	for (int y = area.top(); y < area.bottom(); ++y)
	{
		int fy = (int)((((2LL * (y - pos.top()) + 1) * srch) << 16) / (2LL * ph)) - 32768;
		if (fy < 0)
			fy = 0;
		else if (fy > max_fy)
			fy = max_fy;
		const int sy0 = fy >> 16;
		const int sy1 = (sy0 < srch - 1) ? (sy0 + 1) : sy0;
		const unsigned int wy = (fy >> 8) & 0xFF;

		int slot[2];
		const int want[2] = { sy0, sy1 };
		for (int k = 0; k < 2; ++k)
		{
			const int sy = want[k];
			if (hrow_sy[0] == sy)
				slot[k] = 0;
			else if (hrow_sy[1] == sy)
				slot[k] = 1;
			else
			{
				/* fill the slot that does not hold the other row of this screen row */
				const int t = (k == 1) ? (1 - slot[0]) : ((hrow_sy[0] == sy1) ? 1 : 0);
				memcpy(srow, (const __u8*)src->data + sy * src->stride + sx_lo * src->bypp, span_px * src->bypp);
				__u32 *h = hrow[t];
				int fq = q_first, fr = r_first;
				for (int x = 0; x < width; ++x)
				{
					const int fx = fq - 32768;
					fq += inc_q;
					fr += inc_r;
					if (fr >= den_x)
					{
						fr -= den_x;
						++fq;
					}
					const int f = (fx <= 0) ? 0 : ((fx >= max_fx) ? max_fx : fx);
					const int i0 = (f >> 16) - sx_lo;
					const int i1 = ((f >> 16) < srcw - 1) ? (i0 + 1) : i0;
					__u32 c0, c1;
					if (src->bpp == 8)
					{
						c0 = ppal[((const __u8*)srow)[i0]];
						c1 = ppal[((const __u8*)srow)[i1]];
					}
					else
					{
						c0 = premultiply_argb(srow[i0]);
						c1 = premultiply_argb(srow[i1]);
					}
					h[x] = (c0 == c1) ? c0 : lerp_argb(c0, c1, (f >> 8) & 0xFF);
				}
				hrow_sy[t] = sy;
				slot[k] = t;
			}
		}

		const __u32 *h0 = hrow[slot[0]], *h1 = hrow[slot[1]];
		__u32 *d = (__u32*)((__u8*)dst->data + y * dst->stride) + area.left();
		for (int x = 0; x < width; ++x)
		{
			const __u32 c = (h0[x] == h1[x]) ? h0[x] : lerp_argb(h0[x], h1[x], wy);
			const unsigned int a = c >> 24;
			if ((a == 0xFF) || (a == 0))
			{
				d[x] = a ? c : 0;
				continue;
			}
			unsigned int r = ((((c >> 16) & 0xFF) * recip[a]) + 32768) >> 16;
			unsigned int g = ((((c >> 8) & 0xFF) * recip[a]) + 32768) >> 16;
			unsigned int b = (((c & 0xFF) * recip[a]) + 32768) >> 16;
			if (r > 0xFF) r = 0xFF;
			if (g > 0xFF) g = 0xFF;
			if (b > 0xFF) b = 0xFF;
			d[x] = (a << 24) | (r << 16) | (g << 8) | b;
		}
	}
	return true;
}

/*
 * Enlarging an 8 bpp page with sharp, smooth edges (DVB subtitles). Bilinear mixing alone left every edge 2-3
 * screen pixels wide, i.e. blurred. Here the mixed values are then pulled back to a sharp edge:
 * - coverage: the 4 source pixels around the screen pixel centre are mixed by distance (as bilinear), then the
 *   ramp is steepened by the scale factor and smoothed (smoothstep), so the edge between the letter and the
 *   transparent background is about one screen pixel wide, following a smooth curve (the 0.5 line of the mixed
 *   field), not the staircase of the source pixels;
 * - colour: the visible colours are mixed the same way, then the lightness of the mix is steepened on one scale for
 *   the whole page (from its darkest to its lightest visible palette colour, e.g. black outline and white fill),
 *   so the fill and the outline also meet at a sharp edge, without jumps between neighbouring pixels. Pixels whose
 *   4 neighbours are identical are copied as they are (the fast path).
 * Mapping as in blit_scaled_bilinear: exact quotient and remainder, the same pixel however the clip cuts the area.
 * Written with straight alpha, like the unscaled blit. No allocation (row buffers and tables on the stack).
 * Returns false (nothing drawn) when the source is not 8 bpp or the area is too wide.
 */
static bool __attribute__((noinline)) blit_scaled_sharp_8(gSurface *dst, const gSurface *src, const eRect &pos, const eRect &area)
{
	const int srcw = src->x, srch = src->y;
	const int pw = pos.width(), ph = pos.height();
	const int width = area.width();
	enum { row_max = blit_scale_max / 4 }; /* 4096 pixels */
	if ((src->bpp != 8) || (width <= 0) || (width > row_max) || (srcw > blit_scale_max))
		return false;

	/* per screen column: the two source columns and the weight of the second (0..255) */
	short col0[row_max], col1[row_max];
	unsigned char colw[row_max];
	{
		const int max_fx = (srcw - 1) << 16;
		const int den_x = 2 * pw;
		const long long num_first = ((2LL * (area.left() - pos.left()) + 1) * srcw) << 16;
		int fq = (int)(num_first / den_x), fr = (int)(num_first % den_x);
		const int inc_q = (int)((2LL * srcw << 16) / den_x), inc_r = (int)((2LL * srcw << 16) % den_x);
		for (int x = 0; x < width; ++x)
		{
			const int fx = fq - 32768;
			fq += inc_q;
			fr += inc_r;
			if (fr >= den_x)
			{
				fr -= den_x;
				++fq;
			}
			const int f = (fx <= 0) ? 0 : ((fx >= max_fx) ? max_fx : fx);
			col0[x] = (short)(f >> 16);
			col1[x] = (short)(((f >> 16) < srcw - 1) ? ((f >> 16) + 1) : (f >> 16));
			colw[x] = (unsigned char)((f >> 8) & 0xFF);
		}
	}

	/* palette: straight colour, alpha, lightness */
	__u32 pal[256];
	unsigned char alpha[256], light[256];
	for (int i = 0; i < 256; ++i)
	{
		__u32 c;
		if (src->clut.data && (i < src->clut.colors))
			c = ((__u32)src->clut.data[i].a << 24) | ((__u32)src->clut.data[i].r << 16) | ((__u32)src->clut.data[i].g << 8) | (__u32)src->clut.data[i].b;
		else
			c = 0x010101 * i;
		c ^= 0xFF000000; /* clut a is transparency: 0 = opaque */
		pal[i] = c;
		alpha[i] = c >> 24;
		light[i] = (unsigned char)((((c >> 16) & 0xFF) * 77 + ((c >> 8) & 0xFF) * 150 + (c & 0xFF) * 29) >> 8);
	}

	/* the page's dark and light end: darkest and lightest visible palette colour (black outline, white fill) */
	int lmin = 256, lmax = -1, cmin_r = 0, cmin_g = 0, cmin_b = 0, cmax_r = 0, cmax_g = 0, cmax_b = 0;
	for (int i = 0; i < ((src->clut.data && (src->clut.colors < 256)) ? src->clut.colors : 256); ++i)
	{
		if (!alpha[i])
			continue;
		if (light[i] < lmin)
		{
			lmin = light[i];
			cmin_r = (pal[i] >> 16) & 0xFF; cmin_g = (pal[i] >> 8) & 0xFF; cmin_b = pal[i] & 0xFF;
		}
		if (light[i] > lmax)
		{
			lmax = light[i];
			cmax_r = (pal[i] >> 16) & 0xFF; cmax_g = (pal[i] >> 8) & 0xFF; cmax_b = pal[i] & 0xFF;
		}
	}

	/* steepen by the enlargement, then smoothstep: sharp[v] for v 0..255 */
	unsigned char sharp[256];
	{
		const int k = (int)((256LL * ((pw * srch > ph * srcw) ? pw : ph)) / ((pw * srch > ph * srcw) ? srcw : srch)); /* 8.8 */
		for (int v = 0; v < 256; ++v)
		{
			int t = 128 * 256 + (v - 128) * k; /* 8.8 around the middle */
			t = (t < 0) ? 0 : ((t > 255 * 256) ? 255 * 256 : t);
			const long long u = t; /* 0..65280 */
			sharp[v] = (unsigned char)((u * u * (3 * 65280LL - 2 * u)) / (65280LL * 65280LL * 256LL));
		}
	}

	unsigned char rows[2][blit_scale_max]; /* 2 x 16 KB: raw source rows */
	int rows_sy[2] = { -1, -1 };
	const int max_fy = (srch - 1) << 16;

	for (int y = area.top(); y < area.bottom(); ++y)
	{
		int fy = (int)((((2LL * (y - pos.top()) + 1) * srch) << 16) / (2LL * ph)) - 32768;
		if (fy < 0)
			fy = 0;
		else if (fy > max_fy)
			fy = max_fy;
		const int want[2] = { fy >> 16, ((fy >> 16) < srch - 1) ? ((fy >> 16) + 1) : (fy >> 16) };
		const unsigned int wy = (fy >> 8) & 0xFF;
		int slot[2];
		for (int k = 0; k < 2; ++k)
		{
			if (rows_sy[0] == want[k])
				slot[k] = 0;
			else if (rows_sy[1] == want[k])
				slot[k] = 1;
			else
			{
				const int t = (k == 1) ? (1 - slot[0]) : ((rows_sy[0] == want[1]) ? 1 : 0);
				memcpy(rows[t], (const __u8*)src->data + want[k] * src->stride, srcw);
				rows_sy[t] = want[k];
				slot[k] = t;
			}
		}
		const unsigned char *r0 = rows[slot[0]], *r1 = rows[slot[1]];
		__u32 *d = (__u32*)((__u8*)dst->data + y * dst->stride) + area.left();
		for (int x = 0; x < width; ++x)
		{
			const unsigned char p00 = r0[col0[x]], p10 = r0[col1[x]], p01 = r1[col0[x]], p11 = r1[col1[x]];
			if ((p00 == p10) && (p00 == p01) && (p00 == p11))
			{
				d[x] = alpha[p00] ? pal[p00] : 0;
				continue;
			}
			const unsigned int wx = colw[x];
			/* weights 0..256 in total */
			const unsigned int w00 = ((256 - wx) * (256 - wy)) >> 8, w10 = (wx * (256 - wy)) >> 8;
			const unsigned int w01 = ((256 - wx) * wy) >> 8, w11 = (wx * wy) >> 8;
			const unsigned int wsum = w00 + w10 + w01 + w11;
			const unsigned int a = (w00 * alpha[p00] + w10 * alpha[p10] + w01 * alpha[p01] + w11 * alpha[p11]) / (wsum ? wsum : 1);
			const unsigned int as = sharp[a];
			if (as == 0)
			{
				d[x] = 0;
				continue;
			}
			/* smooth mix of the visible colour (weighted by distance and visibility), then its lightness pulled to
			   the page's dark or light end, so the outline and the fill meet at a sharp edge; one scale for the
			   whole page, so neighbouring pixels never jump between different pairs of colours */
			const unsigned char p[4] = { p00, p10, p01, p11 };
			const unsigned int w[4] = { w00, w10, w01, w11 };
			unsigned int sr = 0, sg = 0, sb = 0, sw = 0;
			for (int i = 0; i < 4; ++i)
			{
				const unsigned int wa = w[i] * alpha[p[i]]; /* <= 256 * 255 */
				const __u32 ci = pal[p[i]];
				sr += wa * ((ci >> 16) & 0xFF);
				sg += wa * ((ci >> 8) & 0xFF);
				sb += wa * (ci & 0xFF);
				sw += wa;
			}
			int cr = sw ? (int)(sr / sw) : 0, cg = sw ? (int)(sg / sw) : 0, cb = sw ? (int)(sb / sw) : 0;
			if (lmax > lmin)
			{
				const int lb = (cr * 77 + cg * 150 + cb * 29) >> 8;
				int pv = ((lb - lmin) * 255) / (lmax - lmin);
				pv = (pv < 0) ? 0 : ((pv > 255) ? 255 : pv);
				const int lt = lmin + (sharp[pv] * (lmax - lmin)) / 255;
				if ((lt > lb) && (lmax > lb))
				{
					const int k = ((lt - lb) * 256) / (lmax - lb);
					cr += ((cmax_r - cr) * k) >> 8; cg += ((cmax_g - cg) * k) >> 8; cb += ((cmax_b - cb) * k) >> 8;
				}
				else if ((lt < lb) && (lb > lmin))
				{
					const int k = ((lb - lt) * 256) / (lb - lmin);
					cr += ((cmin_r - cr) * k) >> 8; cg += ((cmin_g - cg) * k) >> 8; cb += ((cmin_b - cb) * k) >> 8;
				}
			}
			const __u32 c = ((__u32)cr << 16) | ((__u32)cg << 8) | (__u32)cb;
			d[x] = ((__u32)as << 24) | c;
		}
	}
	return true;
}

/*
 * Scaled blit in software, for surfaces the accelerator does not handle. On the receiver the DVB subtitle page
 * is 720x576 and the subtitle window 1920x1080; before this nothing was drawn ("unimplemented: scale on
 * non-accel surfaces").
 * pos:  where the whole source lands on dst (any size, larger or smaller than the source);
 * area: the part of pos drawn now, already cut to the clip rectangle and to dst.
 * Enlarging with a plain copy goes to blit_scaled_sharp_8 (8 bpp, the DVB subtitles; after the subtitle scale mode,
 * gPixmap::setSubtitleScaleMode: hdsgpu first, or the nearest pixel) or blit_scaled_bilinear (32 bpp).
 * Nearest neighbour: each destination pixel takes the source pixel under its centre,
 *   src_x = ((2 * (x - pos.left) + 1) * src_width) / (2 * pos.width), the same for y,
 * computed for x with a quotient and a remainder, without a division per pixel. A pixel gets the same source
 * pixel however the clip cuts the area, and the source is never read outside 0..width-1, 0..height-1.
 * Transparency as in the unscaled blit: 8 bpp with palette like blit_8i_to_32 / _at / _ab, 32 bpp like the
 * 32 -> 32 branch. Destination 32 bpp only (the caller checks).
 * Speed (the receiver has a Cortex-A53 that runs mostly at 400 MHz):
 * - the source is often in accel memory, i.e. in the framebuffer, which the CPU maps without cache (/dev/fb0
 *   is write-combine), so every read there is a full memory access. Each source row is read once, with memcpy
 *   (burst reads), into srow[] (only the columns this area uses) and kept while the next screen rows map to the
 *   same source row. A 32 bpp area using more than 4096 source columns reads the source in place.
 * - plain copy (DVB subtitles): a screen row depends only on its source row, so it is made once in drow[] and
 *   copied with memcpy to every screen row with the same source row (213 screen rows from 114 for a subtitle
 *   region). Areas wider than 4096 pixels, alpha test and alpha blend go straight to the screen.
 * - the per-pixel loops are blit_scaled_row_8 / _32.
 * No allocation: srow[] and drow[] (16 KB each) and the palette (1 KB) are on the stack, in this function only
 * (not inlined, so the unscaled blits keep their small stack frame).
 */
static void __attribute__((noinline)) blit_scaled_sw(gSurface *dst, const gSurface *src, const eRect &pos, const eRect &area, int flag)
{
	const int srcw = src->x, srch = src->y;
	const int pw = pos.width(), ph = pos.height();
	if ((srcw <= 0) || (srch <= 0) || (pw <= 0) || (ph <= 0) || area.empty() || !src->data || !dst->data)
		return;
	if ((srcw > blit_scale_max) || (srch > blit_scale_max) || (pw > blit_scale_max) || (ph > blit_scale_max))
		return;
	if ((dst->bpp != 32) || ((src->bpp != 8) && (src->bpp != 32)))
		return; /* the caller checks this already */
	if ((area.left() < pos.left()) || (area.top() < pos.top()) || (area.right() > pos.right()) || (area.bottom() > pos.bottom()))
		return; /* area is always inside pos; anything else would be a caller error */

	/* enlarging with a plain copy (DVB subtitles): mixed, not blocks; too wide areas stay on the nearest pixel */
	if (!(flag & (gPixmap::blitAlphaTest | gPixmap::blitAlphaBlend)) && (pw >= srcw) && (ph >= srch))
	{
		if (src->bpp != 8)
		{
			/* 32 bpp: smooth mix */
			if (blit_scaled_bilinear(dst, src, pos, area))
				return;
		}
		else
		{
			/* 8 bpp (DVB subtitles), as chosen in the settings: the nearest pixel (below), or sharp smooth edges,
			   on the GPU when chosen and possible, else on the CPU (the same picture) */
			const int mode = gPixmap::getSubtitleScaleMode();
			if (mode != gPixmap::subtitleScaleNearest)
			{
				if ((mode == gPixmap::subtitleScaleGpu) && hdsgpu::blitScaled8(dst, src, pos, area))
					return;
				if (blit_scaled_sharp_8(dst, src, pos, area))
					return;
			}
		}
	}

	/* source column of area.left() as quotient and remainder of den_x; each next pixel adds inc_q and inc_r */
	const int den_x = 2 * pw;
	const long long num_x = (2LL * (area.left() - pos.left()) + 1) * srcw;
	const int start_sx = (int)(num_x / den_x);
	const int start_rem = (int)(num_x % den_x);
	const int inc_q = (2 * srcw) / den_x;
	const int inc_r = (2 * srcw) % den_x;
	const int den_y = 2 * ph;
	const int width = area.width();

	/* the source columns this area reads are start_sx .. end_sx (the column only grows with x) */
	int end_sx = (int)(((2LL * (area.right() - 1 - pos.left()) + 1) * srcw) / den_x);
	if (end_sx >= srcw)
		end_sx = srcw - 1;
	const int span = (end_sx - start_sx + 1) * src->bypp; /* bytes of one source row this area reads */

	__u32 srow[blit_scale_max / 4]; /* 16 KB: the used part of the current source row */
	__u32 drow[blit_scale_max / 4]; /* 16 KB: plain copy, one finished screen row (up to 4096 pixels) */
	const bool src_buffered = (span > 0) && (span <= (int)sizeof(srow));
	const bool dst_buffered = !(flag & (gPixmap::blitAlphaTest | gPixmap::blitAlphaBlend)) && (width <= (int)(sizeof(drow) / sizeof(drow[0])));
	int srow_sy = -1, drow_sy = -1;

	__u32 pal[256];
	if (src->bpp == 8)
	{
		for (int i = 0; i < 256; ++i)
		{
			if (src->clut.data && (i < src->clut.colors))
				pal[i] = ((__u32)src->clut.data[i].a << 24) | ((__u32)src->clut.data[i].r << 16) | ((__u32)src->clut.data[i].g << 8) | (__u32)src->clut.data[i].b;
			else
				pal[i] = 0x010101 * i;
			pal[i] ^= 0xFF000000;
		}
	}

	for (int y = area.top(); y < area.bottom(); ++y)
	{
		int sy = (int)(((2LL * (y - pos.top()) + 1) * srch) / den_y);
		if (sy >= srch)
			sy = srch - 1;
		__u32 *d = (__u32*)((__u8*)dst->data + y * dst->stride) + area.left();
		if (dst_buffered && (sy == drow_sy))
		{
			memcpy(d, drow, width * sizeof(__u32)); /* same source row as the screen row above */
			continue;
		}
		const __u8 *s = (const __u8*)src->data + sy * src->stride + start_sx * src->bypp;
		if (src_buffered)
		{
			if (sy != srow_sy)
			{
				memcpy(srow, s, span);
				srow_sy = sy;
			}
			s = (const __u8*)srow;
		}
		__u32 *out = dst_buffered ? drow : d;
		if (src->bpp == 8)
			blit_scaled_row_8(out, s, pal, width, start_rem, inc_q, inc_r, den_x, flag);
		else
			blit_scaled_row_32(out, (const __u32*)s, width, start_rem, inc_q, inc_r, den_x, flag);
		if (dst_buffered)
		{
			memcpy(d, drow, width * sizeof(__u32));
			drow_sy = sy;
		}
	}
}

/* the subtitle scale mode (gpixmap.h): written by Python on the main thread, read by the drawing thread */
static int subtitle_scale_mode = gPixmap::subtitleScaleSharp;

void gPixmap::setSubtitleScaleMode(int mode)
{
	if ((mode < subtitleScaleNearest) || (mode > subtitleScaleGpu))
		mode = subtitleScaleSharp;
	if (__atomic_exchange_n(&subtitle_scale_mode, mode, __ATOMIC_RELAXED) != mode)
		eDebug("[gPixmap] DVB subtitles enlarged: %s", (mode == subtitleScaleNearest) ? "nearest pixel" :
			((mode == subtitleScaleGpu) ? "on the GPU, sharp on the CPU as fallback" : "sharp, on the CPU"));
}

int gPixmap::getSubtitleScaleMode()
{
	return __atomic_load_n(&subtitle_scale_mode, __ATOMIC_RELAXED);
}

void setSubtitleScaleMode(int mode)
{
	gPixmap::setSubtitleScaleMode(mode);
}

int getSubtitleScaleMode()
{
	return gPixmap::getSubtitleScaleMode();
}

#define FIX 0x10000

void gPixmap::blit(const gPixmap &src, const eRect &_pos, const gRegion &clip, int flag)
{
//	eDebug("blit: -> %d.%d %d:%d -> %d.%d %d:%d, flags=%d",
//		_pos.x(), _pos.y(), _pos.width(), _pos.height(),
//		clip.extends.x(), clip.extends.y(), clip.extends.width(), clip.extends.height(),
//		flag);
	eRect pos = _pos;
	
//	eDebug("source size: %d %d", src.size().width(), src.size().height());
	
	if (!(flag & blitScale)) /* pos' size is valid only when scaling */
		pos = eRect(pos.topLeft(), src.size());
	else if (pos.size() == src.size()) /* no scaling required */
		flag &= ~blitScale;

	int scale_x = FIX, scale_y = FIX;
	
	if (flag & blitScale)
	{
		/* nothing to draw, and no division by zero below. This was ASSERT(width) / ASSERT(height), which in
		   the DEBUG build is eFatal: a DVB subtitle region of width or height 0 from a damaged stream would
		   stop enigma2 instead of drawing nothing. */
		if ((src.size().width() <= 0) || (src.size().height() <= 0) || (pos.width() <= 0) || (pos.height() <= 0))
			return;
		if ((src.size().width() > blit_scale_max) || (src.size().height() > blit_scale_max) || (pos.width() > blit_scale_max) || (pos.height() > blit_scale_max))
		{
			eWarning("blit: scale %dx%d -> %dx%d is too large, not drawn", src.size().width(), src.size().height(), pos.width(), pos.height());
			return;
		}
		scale_x = pos.size().width() * FIX / src.size().width();
		scale_y = pos.size().height() * FIX / src.size().height();
	}
	
//	eDebug("SCALE %x %x", scale_x, scale_y);

	for (unsigned int i=0; i<clip.rects.size(); ++i)
	{
//		eDebug("clip rect: %d %d %d %d", clip.rects[i].x(), clip.rects[i].y(), clip.rects[i].width(), clip.rects[i].height());
		eRect area = pos; /* pos is the virtual (pre-clipping) area on the dest, which can be larger/smaller than src if scaling is enabled */
		area&=clip.rects[i];
		area&=eRect(ePoint(0, 0), size());

		if (area.empty())
			continue;

		eRect srcarea = area;
		srcarea.moveBy(-pos.x(), -pos.y());

//		eDebug("srcarea before scale: %d %d %d %d",
//			srcarea.x(), srcarea.y(), srcarea.width(), srcarea.height());
		
		if (flag & blitScale)
			srcarea = eRect(srcarea.x() * FIX / scale_x, srcarea.y() * FIX / scale_y, srcarea.width() * FIX / scale_x, srcarea.height() * FIX / scale_y);

//		eDebug("srcarea after scale: %d %d %d %d",
//			srcarea.x(), srcarea.y(), srcarea.width(), srcarea.height());

		/* Scaled blits from 8 bpp (the DVB subtitle pages, 720x576 drawn on the 1920x1080 OSD) never go to the
		 * accelerator: blit_scaled_sharp_8 below keeps the letter edges crisp, the 2D engine (TDE on HiSilicon) would
		 * scale them soft. */
		bool scaled_from_8bpp = (flag & blitScale) && (src.surface->bpp == 8);
		if (!scaled_from_8bpp && (surface->data_phys && src.surface->data_phys) && (gAccel::getInstance()))
			if (!gAccel::getInstance()->blit(surface, src.surface, area, srcarea, flag))
				continue;

		if (flag & blitScale)
		{
			/* no accelerator, or it refused: scale in software (DVB subtitles: 720x576 page on the 1920x1080 window) */
			if ((surface->bpp == 32) && ((src.surface->bpp == 8) || (src.surface->bpp == 32)))
				blit_scaled_sw(surface, src.surface, pos, area, flag);
			else
				eWarning("unimplemented: scale %dbpp -> %dbpp on non-accel surfaces", src.surface->bpp, surface->bpp);
			continue;
		}

		if ((surface->bpp == 8) && (src.surface->bpp==8))
		{
			__u8 *srcptr=(__u8*)src.surface->data;
			__u8 *dstptr=(__u8*)surface->data;

			srcptr+=srcarea.left()*src.surface->bypp+srcarea.top()*src.surface->stride;
			dstptr+=area.left()*surface->bypp+area.top()*surface->stride;
			for (int y=0; y<area.height(); y++)
			{
				if (flag & (blitAlphaTest|blitAlphaBlend))
				{
  		      // no real alphatest yet
					int width=area.width();
					unsigned char *src=(unsigned char*)srcptr;
					unsigned char *dst=(unsigned char*)dstptr;
						// use duff's device here!
					while (width--)
					{
						if (!*src)
						{
							src++;
							dst++;
						} else
							*dst++=*src++;
					}
				} else
					memcpy(dstptr, srcptr, area.width()*surface->bypp);
				srcptr+=src.surface->stride;
				dstptr+=surface->stride;
			}
		} else if ((surface->bpp == 32) && (src.surface->bpp==32))
		{
			__u32 *srcptr=(__u32*)src.surface->data;
			__u32 *dstptr=(__u32*)surface->data;

			srcptr+=srcarea.left()+srcarea.top()*src.surface->stride/4;
			dstptr+=area.left()+area.top()*surface->stride/4;
			for (int y=0; y<area.height(); y++)
			{
				if (flag & blitAlphaTest)
				{
					int width=area.width();
					/* 32 bpp pixels are 4 bytes: __u32, never unsigned long (8 bytes on 64 bit) */
					__u32 *src=srcptr;
					__u32 *dst=dstptr;

					while (width--)
					{
						if (!((*src)&0xFF000000))
						{
							src++;
							dst++;
						} else
							*dst++=*src++;
					}
				} else if (flag & blitAlphaBlend)
				{
					// uh oh. this is only until hardware accel is working.

					int width=area.width();
							// ARGB color space!
					unsigned char *src=(unsigned char*)srcptr;
					unsigned char *dst=(unsigned char*)dstptr;

#define BLEND(x, y, a) (y + ((x-y) * a)/256)
					while (width--)
					{
						unsigned char sa = src[3];
						unsigned char sr = src[2];
						unsigned char sg = src[1];
						unsigned char sb = src[0];

						unsigned char da = dst[3];
						unsigned char dr = dst[2];
						unsigned char dg = dst[1];
						unsigned char db = dst[0];

						dst[3] = BLEND(0xFF, da, sa);
						dst[2] = BLEND(sr, dr, sa);
						dst[1] = BLEND(sg, dg, sa);
						dst[0] = BLEND(sb, db, sa);
#undef BLEND

						src += 4; dst += 4;
					}
				} else
					memcpy(dstptr, srcptr, area.width()*surface->bypp);
				srcptr+=src.surface->stride/4;
				dstptr+=surface->stride/4;
			}
		} else if ((surface->bpp == 32) && (src.surface->bpp==8))
		{	
			__u8 *srcptr=(__u8*)src.surface->data;
			__u8 *dstptr=(__u8*)surface->data; // !!
			__u32 pal[256];

			for (int i=0; i<256; ++i)
			{
				if (src.surface->clut.data && (i<src.surface->clut.colors))
					pal[i]=(src.surface->clut.data[i].a<<24)|(src.surface->clut.data[i].r<<16)|(src.surface->clut.data[i].g<<8)|(src.surface->clut.data[i].b);
				else
					pal[i]=0x010101*i;
				pal[i]^=0xFF000000;
			}

			srcptr+=srcarea.left()*src.surface->bypp+srcarea.top()*src.surface->stride;
			dstptr+=area.left()*surface->bypp+area.top()*surface->stride;
			for (int y=0; y<area.height(); y++)
			{
				int width=area.width();
				unsigned char *psrc=(unsigned char*)srcptr;
				__u32 *dst=(__u32*)dstptr;
				if (flag & blitAlphaTest)
					blit_8i_to_32_at(dst, psrc, pal, width);
				else if (flag & blitAlphaBlend)
					blit_8i_to_32_ab(dst, psrc, pal, width);
				else
					blit_8i_to_32(dst, psrc, pal, width);
				srcptr+=src.surface->stride;
				dstptr+=surface->stride;
			}
		} else if ((surface->bpp == 16) && (src.surface->bpp==8))
		{
			__u8 *srcptr=(__u8*)src.surface->data;
			__u8 *dstptr=(__u8*)surface->data; // !!
			__u32 pal[256];

			for (int i=0; i<256; ++i)
			{
				__u32 icol;
				if (src.surface->clut.data && (i<src.surface->clut.colors))
					icol=(src.surface->clut.data[i].a<<24)|(src.surface->clut.data[i].r<<16)|(src.surface->clut.data[i].g<<8)|(src.surface->clut.data[i].b);
				else
					icol=0x010101*i;
#if BYTE_ORDER == LITTLE_ENDIAN
				pal[i] = bswap_16(((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19);
#else
				pal[i] = ((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19;
#endif
				pal[i]^=0xFF000000;
			}

			srcptr+=srcarea.left()*src.surface->bypp+srcarea.top()*src.surface->stride;
			dstptr+=area.left()*surface->bypp+area.top()*surface->stride;

			if (flag & blitAlphaBlend)
				eWarning("ignore unsupported 8bpp -> 16bpp alphablend!");

			for (int y=0; y<area.height(); y++)
			{
				int width=area.width();
				unsigned char *psrc=(unsigned char*)srcptr;
				__u16 *dst=(__u16*)dstptr;
				if (flag & blitAlphaTest)
					blit_8i_to_16_at(dst, psrc, pal, width);
				else
					blit_8i_to_16(dst, psrc, pal, width);
				srcptr+=src.surface->stride;
				dstptr+=surface->stride;
			}
		} else if ((surface->bpp == 16) && (src.surface->bpp==32))
		{
			__u8 *srcptr=(__u8*)src.surface->data;
			__u8 *dstptr=(__u8*)surface->data;

			srcptr+=srcarea.left()+srcarea.top()*src.surface->stride;
			dstptr+=area.left()+area.top()*surface->stride;

			if (flag & blitAlphaBlend)
				eWarning("ignore unsupported 32bpp -> 16bpp alphablend!");

			for (int y=0; y<area.height(); y++)
			{
				int width=area.width();
				__u32 *srcp=(__u32*)srcptr;
				__u16 *dstp=(__u16*)dstptr;

				if (flag & blitAlphaTest)
				{
					while (width--)
					{
						if (!((*srcp)&0xFF000000))
						{
							srcp++;
							dstp++;
						} else
						{
							__u32 icol = *srcp++;
#if BYTE_ORDER == LITTLE_ENDIAN
							*dstp++ = bswap_16(((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19);
#else
							*dstp++ = ((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19;
#endif
						}
					}
				} else
				{
					while (width--)
					{
						__u32 icol = *srcp++;
#if BYTE_ORDER == LITTLE_ENDIAN
						*dstp++ = bswap_16(((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19);
#else
						*dstp++ = ((icol & 0xFF) >> 3) << 11 | ((icol & 0xFF00) >> 10) << 5 | (icol & 0xFF0000) >> 19;
#endif
					}
				}
				srcptr+=src.surface->stride;
				dstptr+=surface->stride;
			}
		} else
			eWarning("cannot blit %dbpp from %dbpp", surface->bpp, src.surface->bpp);
	}
}

#undef FIX

void gPixmap::mergePalette(const gPixmap &target)
{
	if ((!surface->clut.colors) || (!target.surface->clut.colors))
		return;

	gColor *lookup=new gColor[surface->clut.colors];

	for (int i=0; i<surface->clut.colors; i++)
		lookup[i].color=target.surface->clut.findColor(surface->clut.data[i]);
	
	delete [] surface->clut.data;
	surface->clut.colors=target.surface->clut.colors;
	surface->clut.data=new gRGB[surface->clut.colors];
	memcpy(surface->clut.data, target.surface->clut.data, sizeof(gRGB)*surface->clut.colors);

	__u8 *dstptr=(__u8*)surface->data;

	for (int ay=0; ay<surface->y; ay++)
	{
		for (int ax=0; ax<surface->x; ax++)
			dstptr[ax]=lookup[dstptr[ax]];
		dstptr+=surface->stride;
	}
	
	delete [] lookup;
}

static inline int sgn(int a)
{
	if (a < 0)
		return -1;
	else if (!a)
		return 0;
	else
		return 1;
}

void gPixmap::line(const gRegion &clip, ePoint start, ePoint dst, gColor color)
{
	__u8 *srf8 = 0;
	__u16 *srf16 = 0;
	__u32 *srf32 = 0;
	int stride = surface->stride;

	if (clip.rects.empty())
		return;

	__u16 col16;
	__u32 col = 0;
	if (surface->bpp == 8)
		srf8 = (__u8*)surface->data;
	else
	{
		srf32 = (__u32*)surface->data;
		if (surface->clut.data && color < surface->clut.colors)
			col=(surface->clut.data[color].a<<24)|(surface->clut.data[color].r<<16)|(surface->clut.data[color].g<<8)|(surface->clut.data[color].b);
		else
			col=0x10101*color;
		col^=0xFF000000;
	}

	if (surface->bpp == 16)
#if BYTE_ORDER == LITTLE_ENDIAN
		col16=bswap_16(((col & 0xFF) >> 3) << 11 | ((col & 0xFF00) >> 10) << 5 | (col & 0xFF0000) >> 19);
#else
		col16=((col & 0xFF) >> 3) << 11 | ((col & 0xFF00) >> 10) << 5 | (col & 0xFF0000) >> 19;
#endif

	int xa = start.x(), ya = start.y(), xb = dst.x(), yb = dst.y();
	int dx, dy, x, y, s1, s2, e, temp, swap, i;
	dy=abs(yb-ya);
	dx=abs(xb-xa);
	s1=sgn(xb-xa);
	s2=sgn(yb-ya);
	x=xa;
	y=ya;
	if (dy>dx)
	{
		temp=dx;
		dx=dy;
		dy=temp;
		swap=1;
	} else
		swap=0;
	e = 2*dy-dx;

	int lasthit = 0;
	for(i=1; i<=dx; i++)
	{
				/* i don't like this clipping loop, but the only */
				/* other choice i see is to calculate the intersections */
				/* before iterating through the pixels. */
				
				/* one could optimize this because of the ordering */
				/* of the bands. */
				
		lasthit = 0;
		int a = lasthit;
		
			/* if last pixel was invisble, first check bounding box */
		if (a == -1)
		{
				/* check if we just got into the bbox again */
			if (clip.extends.contains(x, y))
				lasthit = a = 0;
			else
				goto fail;
		} else if (!clip.rects[a].contains(x, y))
		{
			do
			{
				++a;
				if ((unsigned int)a == clip.rects.size())
					a = 0;
				if (a == lasthit)
				{
					goto fail;
					lasthit = -1;
				}
			} while (!clip.rects[a].contains(x, y));
			lasthit = a;
		}

		if (srf8)
			srf8[y * stride + x] = color;
		else if (srf16)
			srf16[y * stride/2 + x] = col16;
		else
			srf32[y * stride/4 + x] = col;
fail:
		while (e>=0)
		{
			if (swap==1)
				x+=s1;
			else
				y+=s2;
			e-=2*dx;
		}

		if (swap==1)
			y+=s2;
		else
			x+=s1;
		e+=2*dy;
	}
}

gColor gPalette::findColor(const gRGB &rgb) const
{
		/* grayscale? */
	if (!data)
		return (rgb.r + rgb.g + rgb.b) / 3;
	
	int difference=1<<30, best_choice=0;
	for (int t=0; t<colors; t++)
	{
		int ttd;
		int td=(signed)(rgb.r-data[t].r); td*=td; td*=(255-data[t].a);
		ttd=td;
		if (ttd>=difference)
			continue;
		td=(signed)(rgb.g-data[t].g); td*=td; td*=(255-data[t].a);
		ttd+=td;
		if (ttd>=difference)
			continue;
		td=(signed)(rgb.b-data[t].b); td*=td; td*=(255-data[t].a);
		ttd+=td;
		if (ttd>=difference)
			continue;
		td=(signed)(rgb.a-data[t].a); td*=td; td*=255;
		ttd+=td;
		if (ttd>=difference)
			continue;
		if (!ttd)
			return t;
		difference=ttd;
		best_choice=t;
	}
	return best_choice;
}

DEFINE_REF(gPixmap);

gPixmap::~gPixmap()
{
	if (must_delete_surface)
		delete surface;
}

gPixmap::gPixmap(gSurface *surface)
	:surface(surface), must_delete_surface(false)
{
}

gPixmap::gPixmap(eSize size, int bpp, int accel)
	:must_delete_surface(true)
{
	surface = new gSurface(size, bpp, accel);
}

