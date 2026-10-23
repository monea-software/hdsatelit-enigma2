/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_dvb_hdspazademux_h
#define __lib_dvb_hdspazademux_h

/*
 * Guard of the record channel of a demux on the HiSilicon boxes.
 *
 * The DVB driver of these boxes keeps ONE record channel per demux (demux 0 and 1 only), shared by every recording,
 * stream and timeshift that records on that demux. It is created when the first PID of the first recording arrives
 * and destroyed when the last PID of the last one leaves. Each destruction leaves its 4 MB record buffer mapped in the
 * kernel (vmalloc) and in RAM until the next boot; after some tens of them the video decoder has no room left and the
 * picture is gone until a reboot.
 *
 * While no recording runs on a covered demux (after the first one ended), the guard holds a filter of its own there,
 * output TSDEMUX_TAP like a recording, on GUARD_PID. The record channel is then never destroyed and no buffer is lost.
 *
 * Why GUARD_PID is 0x000F, and neither PID 0 nor 0x1FFF:
 * - A PID added for recording shares the channel of a section or PES filter that is open on the same PID (the PAT,
 *   the PMT, the EIT of the TV), and a section filter opened later on that PID is attached to any channel found on it,
 *   play or record. Held by a guard on PID 0, the shared PAT channel was left as a record channel after a zap to
 *   another transponder and the new PAT filter got no data. Nobody filters 0x000F: ISO/IEC 13818-1 reserves
 *   0x0004-0x000F (DVB uses 0x0010-0x001F for its tables), so the guard always gets a record channel of its own,
 *   which no section or PES filter can ever be attached to, and no packet comes to it.
 * - The driver marks a free PID entry of a recording with 0x1FFF and gives 0x1FFF to every new channel until its PID
 *   is set; a guard on 0x1FFF would not be removed properly, and null packets do come.
 * - A PID other than 0 does not open one of the 3 recording groups of the driver.
 *
 * The guard opens when the last recording of the demux stops, after its other PIDs are out and before its first one
 * (the PAT) goes, so it joins a group with one entry left. It closes as soon as the first PID of the next recording is
 * in the driver, before the other PIDs come. It opens the demux device directly: it holds no tuner, no channel and no
 * demux of the resource manager, it is never read and it writes nothing to disk. It lives as long as enigma2: at the
 * end of enigma2 the record channel goes once.
 */

// ==== HDS_PAZA_DEMUX_INCEPUT ====
// The bookkeeping, without side effects and with no headers at all: built and tested alone on a PC
// (teste/test_paza_memorie_driver.py). hdspazademux.cpp does what it decides.
namespace hdspaza
{
	enum
	{
		DEMUX_COUNT = 2,     // demux 0 and 1 of adapter 0: the only ones the driver records on
		GUARD_PID = 0x000F   // reserved by MPEG-2 systems: never filtered, never on the air (see above)
	};

	enum Action
	{
		NOTHING,
		OPEN_GUARD,
		CLOSE_GUARD
	};

	struct Demux
	{
		int recorders; // recordings running on this demux (started and not yet stopping)
		bool guard;    // the guard filter is open
	};

	// Index of the covered demux, or -1: the guard is only for demux 0 and 1 of adapter 0.
	inline int slot(int adapter, int demux)
	{
		return (adapter == 0 && demux >= 0 && demux < DEMUX_COUNT) ? demux : -1;
	}

	// The first PID of a recording of this demux is in the driver: it keeps the record channel now, so an open guard
	// is closed before the other PIDs of the recording come.
	inline Action started(Demux &d)
	{
		++d.recorders;
		return d.guard ? CLOSE_GUARD : NOTHING;
	}

	// A running recording of this demux has removed its other PIDs and is about to remove the first one. When it is
	// the last recording, the guard is opened first, so the record channel never loses its last PID.
	inline Action stopping(Demux &d)
	{
		if (d.recorders > 0)
			--d.recorders;
		return (d.recorders == 0 && !d.guard) ? OPEN_GUARD : NOTHING;
	}

	// What the glue did: the guard is open only when the device answered.
	inline void opened(Demux &d, bool ok)
	{
		d.guard = ok;
	}

	inline void closed(Demux &d)
	{
		d.guard = false;
	}
}
// ==== HDS_PAZA_DEMUX_SFARSIT ====

/* Called by eDVBTSRecorder (lib/dvb/demux.cpp, HiSilicon only): Started right after the first PID of a recording is
   started, Stopping when a running recording has removed its other PIDs, before its first PID is stopped. */
void hdsPazaRecorderStarted(int adapter, int demux);
void hdsPazaRecorderStopping(int adapter, int demux);

#endif
