/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsfluxhttp: live TS over HTTP from a local relay, as an iTsSource for a playback channel (see hdsfluxhttp.h).
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <lib/base/eerror.h>
#include <lib/service/hdsfluxhttp.h>

DEFINE_REF(eHdsFluxHttp);

/* http://127.0.0.1:<port>/<path> or http://localhost:<port>/<path>; the path goes into the request line, so only
   printable ASCII without spaces is accepted */
static bool parseUrl(const std::string &url, int &port, std::string &path)
{
	static const char scheme[] = "http://";
	const size_t n = sizeof(scheme) - 1;
	if (url.size() <= n || url.compare(0, n, scheme) != 0)
		return false;
	std::string rest = url.substr(n);
	size_t slash = rest.find('/');
	std::string hostport = slash == std::string::npos ? rest : rest.substr(0, slash);
	std::string p = slash == std::string::npos ? std::string("/") : rest.substr(slash);
	size_t colon = hostport.rfind(':');
	if (colon == std::string::npos)
		return false;
	std::string host = hostport.substr(0, colon), digits = hostport.substr(colon + 1);
	if (host != "127.0.0.1" && host != "localhost")
		return false;
	if (digits.empty() || digits.size() > 5)
		return false;
	long v = 0;
	for (size_t i = 0; i < digits.size(); ++i)
	{
		if (digits[i] < '0' || digits[i] > '9')
			return false;
		v = v * 10 + (digits[i] - '0');
	}
	if (v < 1 || v > 65535 || p.size() > 1024)
		return false;
	for (size_t i = 0; i < p.size(); ++i)
	{
		unsigned char c = (unsigned char)p[i];
		if (c <= 0x20 || c >= 0x7f)
			return false;
	}
	port = (int)v;
	path = p;
	return true;
}

eHdsFluxHttp::eHdsFluxHttp()
	:m_port(0), m_fd(-1), m_header_done(false), m_have(0), m_position(0), m_retry_at(0), m_retry_ms(RETRY_MS),
	m_connections(0), m_have_reader(false), m_received(0), m_dropped(0), m_failure_logged(false), m_reserve_ms(0),
	m_reserving(false), m_reserve_from(0), m_reserve_pos(0)
{
	m_creator = pthread_self();
	pthread_mutex_init(&m_reader_lock, NULL);
}

eHdsFluxHttp::~eHdsFluxHttp()
{
	if (m_fd >= 0)
		::close(m_fd);
	if (m_connections)
		eDebug("[eHdsFluxHttp] %s: closed after %d connection(s), %llu bytes received, %llu bytes dropped to resync",
			m_path.c_str(), m_connections, (unsigned long long)m_received, (unsigned long long)m_dropped);
	pthread_mutex_destroy(&m_reader_lock);
}

bool eHdsFluxHttp::accepts(const std::string &url)
{
	int port;
	std::string path;
	return parseUrl(url, port, path);
}

int eHdsFluxHttp::open(const std::string &url)
{
	if (!parseUrl(url, m_port, m_path))
	{
		m_port = 0;
		eDebug("[eHdsFluxHttp] not a local stream address: %s", url.c_str());
		return -1;
	}
	return 0;
}

void eHdsFluxHttp::setStartReserve(int ms)
{
	m_reserve_ms = ms < 0 ? 0 : ms > RESERVE_MAX_MS ? (int)RESERVE_MAX_MS : ms;
	m_reserving = m_reserve_ms > 0;
}

int64_t eHdsFluxHttp::nowMs()
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

/* the first reader other than the creating thread becomes the owner */
bool eHdsFluxHttp::ownedByCaller()
{
	pthread_t self = pthread_self();
	pthread_mutex_lock(&m_reader_lock);
	if (!m_have_reader && !pthread_equal(m_creator, self))
	{
		m_reader = self;
		m_have_reader = true;
	}
	bool owned = m_have_reader && pthread_equal(m_reader, self);
	pthread_mutex_unlock(&m_reader_lock);
	return owned;
}

void eHdsFluxHttp::disconnect(int retry_ms, const char *why)
{
	if (m_fd >= 0)
		::close(m_fd);
	if (!m_failure_logged || m_header_done)
		eDebug("[eHdsFluxHttp] %s: %s, new attempt in %d ms", m_path.c_str(), why, retry_ms);
	m_failure_logged = true;
	m_fd = -1;
	m_have = 0;
	m_header_done = false;
	m_retry_at = nowMs() + retry_ms;
	m_retry_ms = retry_ms * 2 > RETRY_MAX_MS ? (int)RETRY_MAX_MS : retry_ms * 2;
}

/* -1 with errno EINTR (stop requested) or EAGAIN (no connection yet, try again later) */
int eHdsFluxHttp::connectNow()
{
	int fd = ::socket(AF_INET, SOCK_STREAM, 0);
	if (fd < 0)
	{
		disconnect(m_retry_ms, "no socket");
		errno = EAGAIN;
		return -1;
	}
	fcntl(fd, F_SETFD, FD_CLOEXEC);
	fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
	int size = 1024 * 1024;
	setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &size, sizeof(size));
	struct sockaddr_in a;
	memset(&a, 0, sizeof(a));
	a.sin_family = AF_INET;
	a.sin_port = htons((uint16_t)m_port);
	a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
	m_fd = fd;
	if (::connect(fd, (struct sockaddr *)&a, sizeof(a)) < 0)
	{
		if (errno != EINPROGRESS)
		{
			disconnect(m_retry_ms, "connection refused");
			errno = EAGAIN;
			return -1;
		}
		struct pollfd pf;
		pf.fd = fd;
		pf.events = POLLOUT;
		pf.revents = 0;
		int r = ::poll(&pf, 1, WAIT_MS);
		if (r < 0 && errno == EINTR)
		{
			::close(fd);
			m_fd = -1;
			errno = EINTR;
			return -1;
		}
		int err = 0;
		socklen_t len = sizeof(err);
		if (r <= 0 || getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &len) < 0 || err)
		{
			disconnect(m_retry_ms, r == 0 ? "connection timed out" : "connection refused");
			errno = EAGAIN;
			return -1;
		}
	}
	char request[1200];
	int n = snprintf(request, sizeof(request), "GET %s HTTP/1.0\r\nHost: 127.0.0.1:%d\r\nUser-Agent: HDSatelit\r\n"
		"Connection: close\r\n\r\n", m_path.c_str(), m_port);
	if (n <= 0 || (size_t)n >= sizeof(request) || ::send(fd, request, n, MSG_NOSIGNAL) != n)
	{
		disconnect(m_retry_ms, "request not sent");
		errno = EAGAIN;
		return -1;
	}
	m_connections++;
	m_have = 0;
	m_header_done = false;
	return 0;
}

/* 1 = header read and accepted (body starts at m_buf), 0 = header not complete yet, -1 = bad answer */
int eHdsFluxHttp::parseHeader()
{
	size_t end = 0;
	for (size_t i = 0; i + 1 < m_have; ++i)
	{
		if (m_buf[i] == '\n' && m_buf[i + 1] == '\n')
		{
			end = i + 2;
			break;
		}
		if (i + 3 < m_have && m_buf[i] == '\r' && m_buf[i + 1] == '\n' && m_buf[i + 2] == '\r' && m_buf[i + 3] == '\n')
		{
			end = i + 4;
			break;
		}
	}
	if (!end)
		return m_have >= (size_t)HEADER_MAX ? -1 : 0;
	size_t line = 0;
	while (line < end && m_buf[line] != '\r' && m_buf[line] != '\n')
		++line;
	std::string status((const char *)m_buf, line < 80 ? line : 80);
	if (status.compare(0, 7, "HTTP/1.") != 0 || status.size() < 12 || status.compare(8, 4, " 200") != 0)
	{
		eDebug("[eHdsFluxHttp] %s: answer \"%s\"", m_path.c_str(), status.c_str());
		return -1;
	}
	memmove(m_buf, m_buf + end, m_have - end);
	m_have -= end;
	m_header_done = true;
	m_retry_ms = RETRY_MS;
	eDebug("[eHdsFluxHttp] %s: stream connected (connection %d)", m_path.c_str(), m_connections);
	m_failure_logged = false;
	return 1;
}

/* drops bytes in front of the first sync byte that is followed by another one a packet later (or that is too close
   to the end of the data to be checked yet) */
void eHdsFluxHttp::resync()
{
	size_t p = 0;
	while (p < m_have && !(m_buf[p] == 0x47 && (p + (size_t)PACKET >= m_have || m_buf[p + PACKET] == 0x47)))
		++p;
	if (p)
	{
		memmove(m_buf, m_buf + p, m_have - p);
		m_have -= p;
		m_dropped += p;
	}
}

/* one poll and one recv. 0 = data (or header) taken in, -1 with errno EINTR or EAGAIN */
int eHdsFluxHttp::receive(int timeout_ms)
{
	if (m_have >= sizeof(m_buf))
		return 0;
	struct pollfd pf;
	pf.fd = m_fd;
	pf.events = POLLIN;
	pf.revents = 0;
	int r = ::poll(&pf, 1, timeout_ms);
	if (r < 0)
	{
		if (errno == EINTR)
			return -1;
		disconnect(m_retry_ms, "poll failed");
		errno = EAGAIN;
		return -1;
	}
	if (r == 0)
	{
		errno = EAGAIN;
		return -1;
	}
	ssize_t n = ::recv(m_fd, m_buf + m_have, sizeof(m_buf) - m_have, 0);
	if (n < 0)
	{
		if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)
		{
			if (errno == EWOULDBLOCK)
				errno = EAGAIN;
			return -1;
		}
		disconnect(m_retry_ms, "receive failed");
		errno = EAGAIN;
		return -1;
	}
	if (n == 0)
	{
		disconnect(m_header_done ? (int)RETRY_MS : m_retry_ms, "the relay closed the stream");
		errno = EAGAIN;
		return -1;
	}
	m_have += (size_t)n;
	m_received += (uint64_t)n;
	if (!m_header_done)
	{
		int h = parseHeader();
		if (h < 0)
		{
			disconnect(RETRY_MAX_MS / 2, "no usable answer");
			errno = EAGAIN;
			return -1;
		}
		if (h == 0)
		{
			errno = EAGAIN;
			return -1;
		}
	}
	resync();
	return 0;
}

/* bytes of whole packets at the start of the buffer, each one starting with the sync byte */
size_t eHdsFluxHttp::wholePackets() const
{
	size_t n = m_have - m_have % PACKET;
	for (size_t i = 0; i < n; i += PACKET)
		if (m_buf[i] != 0x47)
			return i;
	return n;
}

/* the start reserve: the whole packets received so far move into the reserve; when it holds m_reserve_ms of stream
   (time from its first packet) or RESERVE_MAX_BYTES, it is given out (serveReserve), otherwise EAGAIN */
ssize_t eHdsFluxHttp::holdReserve(void *buf, size_t count)
{
	size_t n = m_header_done ? wholePackets() : 0;
	if (n)
	{
		if (m_reserve.empty())
		{
			m_reserve_from = nowMs();
			m_reserve.reserve(1024 * 1024);
		}
		m_reserve.insert(m_reserve.end(), m_buf, m_buf + n);
		memmove(m_buf, m_buf + n, m_have - n);
		m_have -= n;
	}
	else if (m_header_done && m_have >= (size_t)PACKET && m_buf[0] != 0x47)
		resync();
	if (!m_reserve.empty() && (nowMs() - m_reserve_from >= m_reserve_ms || m_reserve.size() >= (size_t)RESERVE_MAX_BYTES))
	{
		m_reserving = false;
		m_reserve_pos = 0;
		eDebug("[eHdsFluxHttp] %s: start reserve given after %lld ms: %u bytes", m_path.c_str(),
			(long long)(nowMs() - m_reserve_from), (unsigned)m_reserve.size());
		return serveReserve(buf, count);
	}
	errno = EAGAIN;
	return -1;
}

/* the reserve in reads of at most count bytes (whole packets), before anything newer; its memory goes at the end */
ssize_t eHdsFluxHttp::serveReserve(void *buf, size_t count)
{
	size_t n = m_reserve.size() - m_reserve_pos;
	if (n > count)
		n = count;
	memcpy(buf, &m_reserve[m_reserve_pos], n);
	m_reserve_pos += n;
	if (m_reserve_pos >= m_reserve.size())
	{
		std::vector<unsigned char>().swap(m_reserve);
		m_reserve_pos = 0;
	}
	m_position += n;
	return (ssize_t)n;
}

ssize_t eHdsFluxHttp::read(off_t offset, void *buf, size_t count)
{
	(void)offset;
	if (!ownedByCaller())
	{
		/* the creating thread (main loop) never waits; another thread that does not own the stream pauses a little,
		   so a caller that retries at once on EAGAIN does not spin */
		if (!pthread_equal(m_creator, pthread_self()))
		{
			struct timespec t;
			t.tv_sec = 0;
			t.tv_nsec = (long)NOT_OWNER_MS * 1000000L;
			if (nanosleep(&t, NULL) < 0 && errno == EINTR)
				return -1;
		}
		errno = EAGAIN;
		return -1;
	}
	count -= count % PACKET;
	if (!count)
		return 0;
	if (m_port <= 0)
	{
		errno = EINVAL;
		return -1;
	}
	if (!m_reserving && !m_reserve.empty())
		return serveReserve(buf, count);
	if (m_fd < 0)
	{
		int64_t wait = m_retry_at - nowMs();
		if (wait > 0)
		{
			if (wait > WAIT_MS)
				wait = WAIT_MS;
			struct timespec t;
			t.tv_sec = 0;
			t.tv_nsec = (long)wait * 1000000L;
			if (nanosleep(&t, NULL) < 0 && errno == EINTR)
				return -1;
			errno = EAGAIN;
			return -1;
		}
		/* the connection poll was this call's wait: the answer is read by the next call */
		if (connectNow() == 0)
			errno = EAGAIN;
		return -1;
	}
	/* packets already in the buffer are served at once, with only a look (no wait) for more */
	bool buffered = m_header_done && m_have >= (size_t)PACKET;
	if (receive(buffered ? 0 : (int)WAIT_MS) < 0 && (!buffered || errno == EINTR || m_fd < 0))
	{
		/* the time of a reserve also runs out while the relay sends nothing */
		if (m_reserving && errno == EAGAIN && !m_reserve.empty() && m_fd >= 0)
			return holdReserve(buf, count);
		return -1;
	}
	if (m_reserving)
		return holdReserve(buf, count);
	/* a short read is followed by a short wait for more, so the dvr device gets fewer, larger writes */
	size_t ready = m_have - m_have % PACKET;
	if (ready < (size_t)GATHER_BYTES && ready < count && m_fd >= 0)
	{
		int64_t end = nowMs() + GATHER_MS;
		while (ready < (size_t)GATHER_BYTES && ready < count && m_fd >= 0)
		{
			int64_t left = end - nowMs();
			if (left <= 0 || receive((int)left) < 0)
				break;
			ready = m_have - m_have % PACKET;
		}
		/* a failed receive() may have emptied the buffer (disconnect(): the relay closed the stream) or dropped bytes
		   (resync()): the count is taken again, otherwise the copy below would use the old one and move
		   m_have - n bytes with n > m_have (a size near 4 GB, the heap overwritten) */
		ready = m_have - m_have % PACKET;
	}
	size_t n = ready < count ? ready : count;
	if (n > m_have)
		n = 0;
	/* whole packets only, each one starting with the sync byte: a break ends the read before it */
	for (size_t i = 0; i < n; i += PACKET)
	{
		if (m_buf[i] != 0x47)
		{
			n = i;
			break;
		}
	}
	if (!n)
	{
		if (m_have >= (size_t)PACKET && m_buf[0] != 0x47)
			resync();
		errno = EAGAIN;
		return -1;
	}
	memcpy(buf, m_buf, n);
	memmove(m_buf, m_buf + n, m_have - n);
	m_have -= n;
	m_position += n;
	return (ssize_t)n;
}

off_t eHdsFluxHttp::lseek(off_t offset, int whence)
{
	if (whence == SEEK_CUR && offset == 0)
		return m_position;
	errno = ESPIPE;
	return -1;
}

off_t eHdsFluxHttp::length()
{
	return -1;
}

int eHdsFluxHttp::valid()
{
	return m_port > 0;
}
