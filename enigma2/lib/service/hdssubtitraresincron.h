/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdssubtitraresincron.h: when the first page of the subtitle queue (DVB or teletext) of a DVB service is shown
 * (eDVBServicePlay::checkSubtitleTiming, servicedvb.cpp). Header only, without enigma2: the PC test
 * (subtitrari_timeshift_074_proba.cpp) uses it as it is.
 *
 * The page is shown when its PTS reaches the PTS of the decoder (under 20 ms), as before. What changed (0.7.4, a
 * paused timeshift on a SF8008: the subtitles went on in the pause and stayed ahead of the picture after PLAY;
 * measured on a Viper 4K V20 with a recording):
 *  - PAUSED (the decoder paused, not fast forward or slow motion): nothing is shown and no timer runs; the pages wait
 *    in the queue and go on, in sync, after PLAY. The page on screen stays until its own hide timer.
 *  - PLAYBACK FROM A FILE (a recording, the timeshift buffer; not a channel and not a network stream):
 *     - the demux of these boxes reads tens of seconds ahead of the picture (about 30-45 s at 1.2 Mbit/s): a page
 *       up to FEREASTRA_FISIER ahead waits for its time (on a channel the limit stays 20 s, a PTS further away is
 *       broken there); before, after a pause in the subtitles longer than 20 s, every page came more than 20 s
 *       ahead into an empty queue and was shown at once, and the subtitles stayed about 30 s ahead to the end; a long
 *       wait reads the PTS again at least every REVERIFICARE_MS (a jump of the PTS is seen within a second);
 *     - for a short time after the decoder starts, after a jump and after PLAY (LINISTE_*), the PTS of the decoder
 *       can still be the one of the stream before (measured: a page 37 s ahead shown at once): the page waits until
 *       that time is over;
 *     - a decoder that gives no PTS (an error or 0) makes the page wait (retried every REINCERCARE_MS), at most
 *       FARA_PTS_MAX_MS from the first missing reading; then it is shown at once as before, so that a decoder that
 *       never answers does not stop the subtitles.
 *  - On a channel and on a network stream everything is as before: no PTS = pos 0, so shown at once.
 */
#ifndef __lib_service_hdssubtitraresincron_h
#define __lib_service_hdssubtitraresincron_h

#include <stdint.h>

namespace hdssub
{

enum Fel
{
	ARATA = 0,	/* show the page now */
	ASTEAPTA = 1,	/* wait ms, then look again */
	STAI = 2	/* paused: nothing, no timer (PLAY looks again) */
};

struct Hotarare
{
	Fel fel;
	int ms;
	const char *motiv;	/* for the log */
};

static const int64_t FEREASTRA_CANAL = 20LL * 90000;	/* 90 kHz, as before */
static const int64_t FEREASTRA_FISIER = 180LL * 90000;
static const int LINISTE_PORNIRE_MS = 1000;	/* a new decoder, a jump */
static const int LINISTE_PLAY_MS = 500;		/* PLAY after a pause */
static const int REINCERCARE_MS = 200;
static const int REVERIFICARE_MS = 1000;	/* from a file, the longest wait before the PTS is read again */
static const int FARA_PTS_MAX_MS = 3000;
static const int PRAG_MS = 20;			/* under this, the page is shown now (as before) */

struct Stare
{
	bool pauza;			/* m_is_paused, without fast forward or slow motion */
	bool din_fisier;		/* a recording or the timeshift buffer is played */
	int64_t acum_ms;		/* a monotonic clock */
	int64_t liniste_pana_ms;	/* until then the PTS of the decoder is not trusted (din_fisier only) */
	bool are_pts;			/* getPTS answered with a value other than 0 */
	int64_t pos;			/* the PTS of the decoder (90 kHz) when are_pts */
	int64_t fara_pts_de_la_ms;	/* the first missing reading of the run, 0 = none; kept by the caller */
};

/* the first page of the queue: pagina_are_pts (teletext without PTS: shown at once, as before), show_time (90 kHz);
   updates s.fara_pts_de_la_ms */
inline Hotarare hotarare(Stare &s, bool pagina_are_pts, int64_t show_time)
{
	Hotarare h;
	if (s.pauza)
	{
		h.fel = STAI;
		h.ms = 0;
		h.motiv = "paused";
		return h;
	}
	if (!pagina_are_pts)
	{
		h.fel = ARATA;
		h.ms = 0;
		h.motiv = "page without PTS";
		return h;
	}
	if (s.din_fisier && s.acum_ms < s.liniste_pana_ms)
	{
		h.fel = ASTEAPTA;
		h.ms = (int)(s.liniste_pana_ms - s.acum_ms);
		h.motiv = "decoder settling";
		return h;
	}
	int64_t pos = s.are_pts ? s.pos : 0;
	if (s.are_pts)
		s.fara_pts_de_la_ms = 0;
	else if (s.din_fisier)
	{
		if (!s.fara_pts_de_la_ms)
			s.fara_pts_de_la_ms = s.acum_ms;
		if (s.acum_ms - s.fara_pts_de_la_ms < FARA_PTS_MAX_MS)
		{
			h.fel = ASTEAPTA;
			h.ms = REINCERCARE_MS;
			h.motiv = "no PTS from the decoder yet";
			return h;
		}
		/* no PTS for too long: at once (with pos 0 a page with a small PTS would have waited for ever) */
		h.fel = ARATA;
		h.ms = 0;
		h.motiv = "no PTS from the decoder, immediate show";
		return h;
	}
	int64_t diff = show_time - pos;
	int64_t fereastra = s.din_fisier ? FEREASTRA_FISIER : FEREASTRA_CANAL;
	if (diff < 0)
	{
		h.fel = ARATA;
		h.ms = 0;
		h.motiv = "late";
		return h;
	}
	if (diff > fereastra)
	{
		h.fel = ARATA;
		h.ms = 0;
		h.motiv = "invalid, immediate show";
		return h;
	}
	if (diff / 90 < PRAG_MS)
	{
		h.fel = ARATA;
		h.ms = 0;
		h.motiv = "on time";
		return h;
	}
	h.fel = ASTEAPTA;
	h.ms = (int)(diff / 90);
	/* from a file the wait can be long (up to FEREASTRA_FISIER): the PTS of the decoder is read again at least every
	   REVERIFICARE_MS, so that a jump of it (a splice of the broadcaster kept in the timeshift buffer) is seen */
	if (s.din_fisier && h.ms > REVERIFICARE_MS)
		h.ms = REVERIFICARE_MS;
	h.motiv = "subtitle delay";
	return h;
}

}

#endif
