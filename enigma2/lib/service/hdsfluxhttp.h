/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsfluxhttp: a live MPEG transport stream read over HTTP, as the source of a playback channel. A service of type 1
 * whose path is an http:// address plays through the same hardware demux and decoders as a channel: eDVBServicePlay
 * gives this source to eDVBChannel::playSource, the file push thread writes it to the dvr device, and the PMT handler
 * picks the program by the service id of the reference, so teletext, subtitles and the audio tracks work as on any
 * channel. Two kinds of addresses:
 *  - a local relay of the image (http://127.0.0.1:<port>/... or localhost): the DVB-T2 programs from satellite (the
 *    relay decapsulates T2-MI and serves the TS of a PLP) and DAB+ from satellite;
 *  - a server on the network or on the internet: the IPTV channels saved with type 1, as the bouquet makers and the
 *    lists of other receivers write them (1:0:19:<sid>:<tsid>:<onid>:<namespace>:0:0:0:http%3a//host:port/...:Name),
 *    and the stream of another receiver (http://receiver:8001/<reference>), the same way as eHttpStream of the
 *    OE-Alliance enigma2. The address may carry a user and a password (http://user:password@host/...: HTTP Basic
 *    authentication) and request headers after a '#': http://host/path#User-Agent=Name&Referer=http://x/ (pairs
 *    Name=Value separated by '&'; User-Agent replaces the default one).
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
 *    (EINTR) or the next check of its stop flag ends the thread quickly. The connection is built over several reads
 *    (name, connect, request, answer), each one waiting at most WAIT_MS, with a deadline for each step; a host name
 *    is resolved by a small detached thread of its own, never by the push thread or the main thread, so a dead name
 *    server cannot hold a zap or the stop of the channel. When stop()'s signal falls between two system calls the
 *    current read() still runs to its end: a read waits at most WAIT_MS + GATHER_MS (80 ms) for data;
 *  - packets already in the buffer are served at once (only a look without waiting for more), so data received
 *    before a pause of the server is not held back by the next poll;
 *  - a refused or lost connection, an answer 5xx, a server that stops sending, are retried after a pause that grows
 *    to RETRY_MAX_MS (a relay can restart or still be starting; a provider can close a stream now and then). An
 *    answer 4xx (wrong user or password, a stream that is not there, a refused device) is NOT retried: the source
 *    writes one line in the log and gives no data until the channel is started again, so a receiver is never
 *    banned by a provider for asking every second. A redirection (301, 302, 303, 307, 308) is followed, at most
 *    REDIRECTS_MAX times; after a stream that played ends, the next connection starts again from the address of
 *    the reference (the address of a redirection usually expires);
 *  - the request is HTTP/1.0 (a server may not answer it with chunks); an answer in chunks anyway is refused;
 *  - the log never shows the path, the user or the password of an address on the network (the path of an IPTV
 *    address holds the user and the password): only host:port; the local relays are logged with their path;
 *  - https:// is not accepted here (the image has no TLS in enigma2): such a reference is left to its old path;
 *  - the start reserve (setStartReserve, before the push thread reads): the whole packets of the first milliseconds of
 *    the stream are kept and given to the push thread together, when the reserve is full, then the stream goes on as
 *    it comes. The decoders start with that much data in front of them, so a short gap in the arrival (a scheduling
 *    delay of the relay, a lost block of the satellite feed, the jitter of an internet stream) does not reach the
 *    picture and the sound at once. The reserve is taken once, at the first connection; it costs the same time at
 *    the start of the program.
 */
#ifndef __lib_service_hdsfluxhttp_h
#define __lib_service_hdsfluxhttp_h

#include <pthread.h>
#include <stdint.h>
#include <string>
#include <vector>
#include <sys/socket.h>
#include <lib/base/itssource.h>

struct eHdsFluxHttpNume;

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
		RESERVE_MAX_BYTES = 4 * 1024 * 1024, /* the reserve is given at this size even before its time */
		CONNECT_MS = 8000,      /* a server on the network: longest connect */
		NAME_MS = 10000,        /* longest wait for the name server */
		ANSWER_MS = 10000,      /* longest wait for the answer header after the request */
		SILENCE_MS = 15000,     /* a server on the network that sends nothing this long: a new connection */
		REDIRECTS_MAX = 5
	};
	eHdsFluxHttp();
	~eHdsFluxHttp();

	/* true for an http:// address this source can read (the decoded path of a reference) */
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

	/* where a request goes (public for the parser, which is a free function) */
	struct Tinta
	{
		std::string host;       /* name or address, without brackets */
		int port;
		std::string path;       /* request target, encoded */
		std::string auth;       /* base64 of user:password, or empty */
		bool local;             /* 127.0.0.1 / localhost: a relay of the image */
		Tinta(): port(0), local(false) {}
	};
private:
	Tinta m_start;                  /* the address of the reference */
	Tinta m_target;                 /* where the next request goes (m_start, or a redirection) */
	std::string m_agent;            /* User-Agent */
	std::string m_headers;          /* extra request headers, "Name: value\r\n" each */
	std::string m_label;            /* what the log shows of the address */
	bool m_valid;
	bool m_refused;                 /* an answer 4xx: no new attempt */
	int m_redirects;
	int m_fd;
	bool m_connecting;              /* connect() in progress on m_fd */
	int64_t m_deadline;             /* of the current step (connect, answer) */
	int64_t m_last_data;
	bool m_header_done;
	bool m_draining;                /* the server closed a stream: its whole packets left in m_buf go out first */
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
	/* the address of m_target.host */
	struct sockaddr_storage m_addr;
	socklen_t m_addr_len;
	std::string m_addr_host;        /* the host m_addr belongs to (empty = none) */
	eHdsFluxHttpNume *m_nume;       /* a name being resolved */
	int64_t m_nume_from;

	static int64_t nowMs();
	bool ownedByCaller();
	void setTarget(const Tinta &t);
	int haveAddress();
	int connectNow();
	int finishConnect();
	int sendRequest();
	void disconnect(int retry_ms, const char *why);
	void endOfStream(int retry_ms, const char *why);
	void refuse(const char *why);
	int parseHeader();
	void resync();
	int receive(int timeout_ms);
	size_t wholePackets() const;
	ssize_t holdReserve(void *buf, size_t count);
	ssize_t serveReserve(void *buf, size_t count);
};

#endif
