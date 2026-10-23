/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsfluxhttp: a live MPEG transport stream read over HTTP from a local relay (127.0.0.1), as the source of a
 * playback channel. A service of type 1 whose path is http://127.0.0.1:<port>/... (the DVB-T2 programs from satellite:
 * the relay decapsulates T2-MI and serves the TS of a PLP) plays through the same hardware demux and decoders as a
 * channel: eDVBServicePlay gives this source to eDVBChannel::playSource, the file push thread writes it to the dvr
 * device, and the PMT handler picks the program by the service id of the reference, so teletext, subtitles and the
 * audio tracks work as on any channel.
 *
 * Rules of the source:
 *  - only the file push thread reads: the first thread that calls read() owns the stream, except the thread that
 *    made the source (the main thread, in createTsSource), which never owns it: eDVBServicePMTHandler::tuneExt reads
 *    the source there for a reference with service id 0 (eDVBTSTools::findPMT) before the push thread starts, and
 *    owning the stream there would leave the push thread without data. A read from the creating thread gets EAGAIN
 *    at once and takes nothing; a read from any other thread that does not own the stream waits NOT_OWNER_MS first,
 *    so a loop that retries at once on EAGAIN (eFilePushThread) cannot spin a core;
 *  - read() returns whole 188-byte packets aligned on the sync byte (the push thread drops the tail of a short read,
 *    which for a stream would lose the alignment for good); the offset is ignored;
 *  - nothing blocks for long: every wait is a poll of at most WAIT_MS, so the SIGUSR1 of eFilePushThread::stop()
 *    (EINTR) or the next check of its stop flag ends the thread quickly. stop() sends the signal only once; when it
 *    falls between two system calls the current read() still runs to its end, so one read() waits at most once: a
 *    new connection returns EAGAIN right after the request is sent, and a read waits at most WAIT_MS + GATHER_MS
 *    (80 ms) for data;
 *  - packets already in the buffer are served at once (only a look without waiting for more), so data received
 *    before a pause of the relay is not held back by the next poll;
 *  - the connection is made by the reading thread; a refused or lost connection, or an answer other than 200, is
 *    retried after a pause that grows to RETRY_MAX_MS (the relay can restart or still be starting);
 *  - only loopback addresses are accepted: the source never connects to another machine;
 *  - the start reserve (setStartReserve, before the push thread reads): the whole packets of the first milliseconds of
 *    the stream are kept and given to the push thread together, when the reserve is full, then the stream goes on as
 *    it comes. The decoders start with that much data in front of them, so a short gap in the arrival (a scheduling
 *    delay of the relay, a lost block of the satellite feed) does not reach the picture and the sound at once. The
 *    reserve is taken once, at the first connection; it costs the same time at the start of the program.
 */
#ifndef __lib_service_hdsfluxhttp_h
#define __lib_service_hdsfluxhttp_h

#include <pthread.h>
#include <stdint.h>
#include <string>
#include <vector>
#include <lib/base/itssource.h>

class eHdsFluxHttp: public iTsSource
{
	DECLARE_REF(eHdsFluxHttp);
public:
	enum
	{
		PACKET = 188,
		BUFFER = 65536 + 2 * 188,
		HEADER_MAX = 8192,
		WAIT_MS = 50,           /* longest poll in one read() */
		GATHER_MS = 30,         /* after a short read, wait this long for more data (fewer, larger writes) */
		GATHER_BYTES = 32768,
		RETRY_MS = 500,
		RETRY_MAX_MS = 4000,
		NOT_OWNER_MS = 20,      /* pause of a thread that does not own the stream, before EAGAIN */
		RESERVE_MAX_MS = 1000,  /* longest start reserve */
		RESERVE_MAX_BYTES = 4 * 1024 * 1024 /* the reserve is given at this size even before its time */
	};
	eHdsFluxHttp();
	~eHdsFluxHttp();

	/* true for http://127.0.0.1:<port>/... and http://localhost:<port>/... (the decoded path of a reference) */
	static bool accepts(const std::string &url);
	/* parses the address; the connection is made later, by the reading thread. 0 or -1 */
	int open(const std::string &url);
	/* the start reserve in milliseconds (0 = none, at most RESERVE_MAX_MS); before the first read */
	void setStartReserve(int ms);

	// iTsSource
	off_t lseek(off_t offset, int whence);
	ssize_t read(off_t offset, void *buf, size_t count);
	off_t length();
	int valid();

	/* counters for the log */
	uint64_t received() const { return m_received; }
	uint64_t dropped() const { return m_dropped; }
private:
	int m_port;
	std::string m_path;
	int m_fd;
	bool m_header_done;
	size_t m_have;
	unsigned char m_buf[BUFFER];
	off_t m_position;
	int64_t m_retry_at;
	int m_retry_ms;
	int m_connections;
	bool m_have_reader;
	pthread_t m_reader;
	pthread_t m_creator;            /* never owns the stream (see the rules above) */
	pthread_mutex_t m_reader_lock;
	uint64_t m_received, m_dropped;
	bool m_failure_logged;
	int m_reserve_ms;
	bool m_reserving;               /* holding the start of the stream */
	int64_t m_reserve_from;         /* when the first packet of the reserve came */
	std::vector<unsigned char> m_reserve;
	size_t m_reserve_pos;           /* next byte of the reserve to serve */

	static int64_t nowMs();
	bool ownedByCaller();
	int connectNow();
	void disconnect(int retry_ms, const char *why);
	int parseHeader();
	void resync();
	int receive(int timeout_ms);
	size_t wholePackets() const;
	ssize_t holdReserve(void *buf, size_t count);
	ssize_t serveReserve(void *buf, size_t count);
};

#endif
