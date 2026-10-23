/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
/* Invelisul dintre enigma2 si codorul nostru MPEG-2: dintr-un gPixmap iese direct
   fisierul .mvi pe care il arata showiframe la pornirea receptorului.
   Poza se aduce la 1920x1080 mai devreme, de ePicLoad (setPara cu 1920, 1080). */

#include <stdio.h>
#include <unistd.h>

#include <lib/base/eerror.h>
#include <lib/gdi/emvi.h>
#include <lib/gdi/mpeg2intra.h>

int saveMVI(const char *filename, gPixmap *pixmap, int quantiser_scale_code)
{
	if (!filename || !pixmap)
		return -1;

	gSurface *surface = pixmap->surface;
	if (!surface)
		return -2;

	if (surface->bypp != 4)
	{
		eDebug("saveMVI: %s are %d octeti pe pixel, trebuie 4 (32 de biti)", filename, surface->bypp);
		return -3;
	}
	if (surface->x != mpeg2intra::LATIME || surface->y != mpeg2intra::INALTIME)
	{
		eDebug("saveMVI: %s e de %dx%d, trebuie %dx%d", filename, surface->x, surface->y,
			mpeg2intra::LATIME, mpeg2intra::INALTIME);
		return -4;
	}
	if (!surface->data)
		return -5;

	/* cele trei planuri: Y pe 1088 de randuri, croma pe 544 (4:2:0), in total vreo 3 MB */
	std::vector<unsigned char> planY((size_t)mpeg2intra::LATIME * mpeg2intra::INALTIME_CODATA);
	std::vector<unsigned char> planCb((size_t)mpeg2intra::LATIME_CROMA * mpeg2intra::INALTIME_CROMA);
	std::vector<unsigned char> planCr(planCb.size());

	mpeg2intra::dinBGRA((const unsigned char *)surface->data, surface->stride,
		&planY[0], &planCb[0], &planCr[0]);

	std::vector<unsigned char> date;
	int r = mpeg2intra::codeaza(&planY[0], &planCb[0], &planCr[0], quantiser_scale_code, date);
	if (r)
	{
		eDebug("saveMVI: codorul a raspuns %d (cuantizare %d)", r, quantiser_scale_code);
		return -6;
	}

	FILE *fp = fopen(filename, "wb");
	if (!fp)
	{
		eDebug("saveMVI: nu pot scrie %s", filename);
		return -7;
	}
	if (fwrite(&date[0], 1, date.size(), fp) != date.size())
	{
		eDebug("saveMVI: scrierea lui %s a ramas la jumatate", filename);
		fclose(fp);
		unlink(filename);
		return -8;
	}
	fclose(fp);

	eDebug("saveMVI: %s gata, %d octeti, cuantizare %d", filename, (int)date.size(),
		quantiser_scale_code);
	return 0;
}
