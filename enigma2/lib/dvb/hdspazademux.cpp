/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * The glue of the record channel guard (see hdspazademux.h): the device calls for what hdspaza decides. It is called
 * only from the HiSilicon parts of lib/dvb/demux.cpp, by the recordings (the main thread); a lock keeps the
 * bookkeeping whole should a recording ever start or stop on another thread.
 */

#include <lib/dvb/hdspazademux.h>
#include <lib/dvb/dvbapi_compat.h>
#include <lib/base/eerror.h>
#include <lib/base/elock.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

namespace
{
	pthread_mutex_t g_guard_lock = PTHREAD_MUTEX_INITIALIZER;
	hdspaza::Demux g_guard[hdspaza::DEMUX_COUNT] = { { 0, false }, { 0, false } };
	int g_guard_fd[hdspaza::DEMUX_COUNT] = { -1, -1 };

	/* A filter like the first PID of a recording (eDVBTSRecorder::start), on GUARD_PID. Not inherited by the
	   programs enigma2 starts (O_CLOEXEC): the guard ends with enigma2. */
	int openGuard(int adapter, int demux)
	{
		char name[64];
		snprintf(name, sizeof(name), "/dev/dvb/adapter%d/demux%d", adapter, demux);
		int fd = ::open(name, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
		if (fd < 0)
		{
			eWarning("[HdsPazaDemux] demux%d: %s cannot be opened (%m), the record channel goes with the recording",
				demux, name);
			return -1;
		}
		dmx_pes_filter_params flt;
		memset(&flt, 0, sizeof(flt));
		flt.pid = hdspaza::GUARD_PID;
		flt.input = DMX_IN_FRONTEND;
		flt.output = DMX_OUT_TSDEMUX_TAP;
		flt.pes_type = DMX_PES_OTHER;
		flt.flags = 0;
		if (::ioctl(fd, DMX_SET_PES_FILTER, &flt) < 0 || ::ioctl(fd, DMX_START) < 0)
		{
			eWarning("[HdsPazaDemux] demux%d: the guard filter on PID 0x%04x did not start (%m), the record channel "
				"goes with the recording", demux, (unsigned)hdspaza::GUARD_PID);
			::close(fd);
			return -1;
		}
		return fd;
	}

	void closeGuard(int k)
	{
		if (g_guard_fd[k] < 0)
			return;
		if (::ioctl(g_guard_fd[k], DMX_STOP) < 0)
			eWarning("[HdsPazaDemux] demux%d: DMX_STOP of the guard: %m", k);
		::close(g_guard_fd[k]);
		g_guard_fd[k] = -1;
	}
}

void hdsPazaRecorderStarted(int adapter, int demux)
{
	int k = hdspaza::slot(adapter, demux);
	if (k < 0)
		return;
	singleLock s(g_guard_lock);
	if (hdspaza::started(g_guard[k]) == hdspaza::CLOSE_GUARD)
	{
		closeGuard(k);
		hdspaza::closed(g_guard[k]);
		eDebug("[HdsPazaDemux] demux%d: a recording holds the record channel, guard closed", demux);
	}
}

void hdsPazaRecorderStopping(int adapter, int demux)
{
	int k = hdspaza::slot(adapter, demux);
	if (k < 0)
		return;
	singleLock s(g_guard_lock);
	if (hdspaza::stopping(g_guard[k]) == hdspaza::OPEN_GUARD)
	{
		g_guard_fd[k] = openGuard(adapter, demux);
		hdspaza::opened(g_guard[k], g_guard_fd[k] >= 0);
		if (g_guard_fd[k] >= 0)
			eDebug("[HdsPazaDemux] demux%d: the last recording stops, the guard keeps the record channel (PID 0x%04x)",
				demux, (unsigned)hdspaza::GUARD_PID);
	}
}
