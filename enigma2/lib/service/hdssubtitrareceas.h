/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdssubtitrareceas.h: the clock of the subtitle files shown on a DVB service (a channel, its timeshift, a .ts
 * recording; servicedvb.cpp) and the search in their lines. Header only, without enigma2: the PC test
 * (subtitrari_tv_live_proba.cpp) uses it as it is.
 *
 * THE CLOCK (milliseconds, its own zero):
 * - on a channel and in its timeshift the source is the PTS of the decoder (90 kHz, 33 bits): the clock moves by the
 *   difference between two readings, taken modulo 2^33 (the PTS turns over every 26.5 hours). On a live channel a
 *   jump of the PTS that does not agree with the time that passed (more than PRAG_SALT_MS apart) is a splice of the
 *   broadcaster (a regional advertisement, a new encoder): the clock then moves by the time that passed. In timeshift
 *   (and on the reading where timeshift starts or stops) a jump is a seek of the viewer and the clock follows it;
 *   above MAX_SALT_MS it is a broken reading and the time that passed is used;
 * - on a recording the source is the play position (90 kHz from the start of the file, as the seek bar shows it):
 *   the clock starts at that position and follows its seeks;
 * - a reading that does not come (no decoder yet, after a zap) moves the clock by the time that passed;
 * - paused ("Reclama", the advertisement key): the readings go on, the clock does not move; it goes on from the same
 *   place when the pause ends.
 *
 * THE LINES: sorted by their start (ms in the time of the file). The time of the file now is
 * (clock - delay) / speed: speed 23.976 / 25 = 0.95904 for a subtitle made on a 23.976 fps copy of a film that the
 * channel shows at 25 fps (the film runs 4.27 % faster), delay = the clock when the film was at its start.
 */
#ifndef __lib_service_hdssubtitrareceas_h
#define __lib_service_hdssubtitrareceas_h

#include <stdint.h>
#include <string>
#include <vector>
#include <algorithm>

struct eHdsReplicaExterna
{
	int start_ms;
	int end_ms;
	std::string text;	/* lines separated by a newline */
	bool top;		/* shown at the top of the picture */
};

class eHdsCeasSubtitrare
{
public:
	enum { SURSA_PTS = 0, SURSA_POZITIE = 1 };
	/* a PTS jump on a live channel that differs from the time that passed by more than this is a splice */
	static const int64_t PRAG_SALT_MS = 1000;
	/* a jump larger than this (6 hours) is a broken reading, also in timeshift and on a recording */
	static const int64_t MAX_SALT_MS = 6LL * 3600 * 1000;

	eHdsCeasSubtitrare() { reset(); }

	/* the next reading starts the clock again (at 0, or at the play position of a recording) */
	void reset()
	{
		m_valid = false;
		m_paused = false;
		m_have_last = false;
		m_last_value = 0;
		m_last_wall = 0;
		m_last_source = SURSA_PTS;
		m_clock90 = 0;
		m_lipituri = 0;
		m_ultimul_salt_ms = 0;
	}

	/* the difference b - a of two PTS values, between -2^32 and 2^32 (the PTS has 33 bits) */
	static int64_t diferentaPts(int64_t a, int64_t b)
	{
		const int64_t modul = 1LL << 33;
		int64_t d = (b - a) % modul;
		if (d < 0)
			d += modul;
		if (d >= (modul >> 1))
			d -= modul;
		return d;
	}

	/* one reading. wall_ms: a monotonic clock in ms; have_value: the source answered; value: PTS or position (90 kHz);
	   seek: a jump of the source is a seek of the viewer (timeshift, recording, or timeshift started or stopped now) */
	void sample(int64_t wall_ms, bool have_value, int64_t value, int source, bool seek)
	{
		if (!m_valid)
		{
			m_valid = true;
			m_last_wall = wall_ms;
			m_have_last = have_value;
			m_last_value = value;
			m_last_source = source;
			m_clock90 = (source == SURSA_POZITIE && have_value && value > 0) ? value : 0;
			return;
		}
		int64_t perete = wall_ms - m_last_wall;
		if (perete < 0)
			perete = 0;
		int64_t pas90 = perete * 90;
		if (have_value && m_have_last && source == m_last_source)
		{
			int64_t d = (source == SURSA_PTS) ? diferentaPts(m_last_value, value) : (value - m_last_value);
			int64_t d_ms = d / 90;
			if (d_ms > MAX_SALT_MS || d_ms < -MAX_SALT_MS)
				pas90 = perete * 90;
			else if (seek || source == SURSA_POZITIE)
				pas90 = d;
			else if (d_ms - perete > PRAG_SALT_MS || d_ms - perete < -PRAG_SALT_MS)
			{
				pas90 = perete * 90;
				++m_lipituri;
				m_ultimul_salt_ms = d_ms - perete;
			}
			else
				pas90 = d;
		}
		if (!m_paused)
			m_clock90 += pas90;
		m_last_wall = wall_ms;
		if (have_value)
		{
			m_last_value = value;
			m_last_source = source;
		}
		m_have_last = have_value;
	}

	bool valid() const { return m_valid; }
	int64_t ms() const { return m_clock90 / 90; }
	bool paused() const { return m_paused; }
	void setPaused(bool paused) { m_paused = paused; }
	/* for the log: did the last reading answer, how many splices were passed over, the size of the last one */
	bool areCitire() const { return m_have_last; }
	int lipituri() const { return m_lipituri; }
	int64_t ultimulSaltMs() const { return m_ultimul_salt_ms; }

private:
	bool m_valid, m_paused, m_have_last;
	int64_t m_last_value, m_last_wall, m_clock90;
	int m_last_source;
	int m_lipituri;
	int64_t m_ultimul_salt_ms;
};

/* the time of the file (ms) for a clock value, and the clock value of a time of the file */
inline int64_t hdsTimpFisier(int64_t clock_ms, int64_t delay_ms, double speed)
{
	double t = (double)(clock_ms - delay_ms) / speed;
	return (int64_t)(t < 0 ? t - 0.5 : t + 0.5);
}

inline int64_t hdsTimpCeas(int64_t file_ms, int64_t delay_ms, double speed)
{
	double t = (double)file_ms * speed;
	return (int64_t)(t < 0 ? t - 0.5 : t + 0.5) + delay_ms;
}

/* the index of the first line that starts after t (cues.size() if none) */
inline size_t hdsReplicaUrmatoare(const std::vector<eHdsReplicaExterna> &c, int64_t t)
{
	return std::upper_bound(c.begin(), c.end(), t,
		[](int64_t x, const eHdsReplicaExterna &r) { return x < (int64_t)r.start_ms; }) - c.begin();
}

/* the lines on screen at t (at most 16 back from the next one: lines that overlap, two speakers), in order */
inline void hdsReplicaActive(const std::vector<eHdsReplicaExterna> &c, int64_t t, std::vector<int> &active)
{
	active.clear();
	size_t urmatoarea = hdsReplicaUrmatoare(c, t);
	for (size_t k = urmatoarea, pasi = 0; k > 0 && pasi < 16; --k, ++pasi)
		if ((int64_t)c[k - 1].end_ms > t)
			active.insert(active.begin(), (int)(k - 1));
}

/* "the next line" / "the line before" (the viewer hears a line and wants it on screen now): the index of the line
   that must start now, or -1. A line that starts within TOLERANTA_SALT_MS from t counts as started (after a jump the
   clock is read again and rounded, so the line chosen a moment ago may still be a few ms in the future).
     direction > 0: the first line that starts after t (a line that started now, after an earlier jump, counts as on
                    screen, so a second press goes one further);
     direction < 0: the line before the first one on screen; with nothing on screen, the last line that started. */
static const int64_t TOLERANTA_SALT_MS = 50;

inline int hdsTintaSalt(const std::vector<eHdsReplicaExterna> &c, int64_t t, int direction)
{
	if (c.empty() || direction == 0)
		return -1;
	t += TOLERANTA_SALT_MS;
	size_t urmatoarea = hdsReplicaUrmatoare(c, t);
	if (direction > 0)
		return urmatoarea < c.size() ? (int)urmatoarea : -1;
	std::vector<int> active;
	hdsReplicaActive(c, t, active);
	int tinta = active.empty() ? (int)urmatoarea - 1 : active[0] - 1;
	return tinta >= 0 ? tinta : -1;
}

#endif
