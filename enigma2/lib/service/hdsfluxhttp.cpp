/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsfluxhttp: live TS over HTTP (a local relay or a server on the network), as an iTsSource for a playback channel
 * (see hdsfluxhttp.h).
 */
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <lib/base/eerror.h>
#include <lib/service/hdsfluxhttp.h>

DEFINE_REF(eHdsFluxHttp);

/* the User-Agent of a server on the network: the one the enigma2 of OE-Alliance sends for these streams, so a
   provider sees the same client as on the other receivers that play type 1; a local relay gets ours, as before */
static const char AGENT_RETEA[] = "HbbTV/1.1.1 (+PVR+RTSP+DL; Sonic; TV44; 1.32.455; 2.002) Bee/3.5";
static const char AGENT_LOCAL[] = "HDSatelit";

static int hexValue(char c)
{
	if (c >= '0' && c <= '9')
		return c - '0';
	if (c >= 'a' && c <= 'f')
		return c - 'a' + 10;
	if (c >= 'A' && c <= 'F')
		return c - 'A' + 10;
	return -1;
}

/* the request target: the bytes a request line cannot carry (controls, space, non-ASCII) as %XX */
static std::string encodeTarget(const std::string &s)
{
	static const char hex[] = "0123456789ABCDEF";
	std::string r;
	for (size_t i = 0; i < s.size(); ++i)
	{
		unsigned char c = (unsigned char)s[i];
		if (c <= 0x20 || c >= 0x7f)
		{
			r += '%';
			r += hex[c >> 4];
			r += hex[c & 15];
		}
		else
			r += (char)c;
	}
	return r;
}

static std::string base64(const std::string &in)
{
	static const char t[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
	std::string r;
	size_t i = 0;
	while (i + 2 < in.size())
	{
		unsigned v = ((unsigned char)in[i] << 16) | ((unsigned char)in[i + 1] << 8) | (unsigned char)in[i + 2];
		r += t[(v >> 18) & 63];
		r += t[(v >> 12) & 63];
		r += t[(v >> 6) & 63];
		r += t[v & 63];
		i += 3;
	}
	if (i + 1 == in.size())
	{
		unsigned v = (unsigned char)in[i] << 16;
		r += t[(v >> 18) & 63];
		r += t[(v >> 12) & 63];
		r += "==";
	}
	else if (i + 2 == in.size())
	{
		unsigned v = ((unsigned char)in[i] << 16) | ((unsigned char)in[i + 1] << 8);
		r += t[(v >> 18) & 63];
		r += t[(v >> 12) & 63];
		r += t[(v >> 6) & 63];
		r += '=';
	}
	return r;
}

static bool startsNoCase(const std::string &s, const char *prefix)
{
	size_t n = strlen(prefix);
	return s.size() >= n && strncasecmp(s.c_str(), prefix, n) == 0;
}

static bool hostChar(char c)
{
	return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_';
}

/* the request headers after '#': Name=Value pairs separated by '&'; a bad pair is skipped (never sent half) */
static void parseHeaders(const std::string &frag, std::string *agent, std::string *headers)
{
	size_t p = 0;
	while (p <= frag.size())
	{
		size_t amp = frag.find('&', p);
		std::string pair = frag.substr(p, amp == std::string::npos ? std::string::npos : amp - p);
		p = amp == std::string::npos ? frag.size() + 1 : amp + 1;
		size_t eq = pair.find('=');
		if (eq == std::string::npos || eq == 0 || eq + 1 >= pair.size())
			continue;
		std::string name = pair.substr(0, eq), value = pair.substr(eq + 1);
		bool good = name.size() <= 64 && value.size() <= 1024;
		for (size_t i = 0; good && i < name.size(); ++i)
			good = (name[i] >= 'a' && name[i] <= 'z') || (name[i] >= 'A' && name[i] <= 'Z') || (name[i] >= '0' && name[i] <= '9') || name[i] == '-' || name[i] == '_';
		for (size_t i = 0; good && i < value.size(); ++i)
			good = value[i] != '\r' && value[i] != '\n' && value[i] != '\0';
		if (!good)
			continue;
		if (!strcasecmp(name.c_str(), "User-Agent"))
		{
			if (agent)
				*agent = value;
		}
		else if (strcasecmp(name.c_str(), "Host") && strcasecmp(name.c_str(), "Connection") &&
			strcasecmp(name.c_str(), "Content-Length") && strcasecmp(name.c_str(), "Transfer-Encoding"))
		{
			if (headers)
				*headers += name + ": " + value + "\r\n";
		}
	}
}

/* http://[user:password@]host[:port][/path][?query][#Name=Value&...] (the decoded path of a reference) */
static bool parseAddress(const std::string &address, eHdsFluxHttp::Tinta &t, std::string *agent, std::string *headers)
{
	if (!startsNoCase(address, "http://") || address.size() <= 7)
		return false;
	std::string url = address, frag;
	size_t hash = url.find('#');
	if (hash != std::string::npos)
	{
		frag = url.substr(hash + 1);
		url.erase(hash);
	}
	std::string rest = url.substr(7);
	size_t end = rest.find_first_of("/?");
	std::string authority = end == std::string::npos ? rest : rest.substr(0, end);
	std::string path = end == std::string::npos ? std::string("/") : rest.substr(end);
	if (path[0] == '?')
		path.insert(0, "/");
	std::string auth;
	size_t at = authority.rfind('@');
	if (at != std::string::npos)
	{
		/* the path of a reference arrives decoded (eServiceReference decodes every %XX): the user and the password
		   are taken as they are, so a '%' in a password stays a '%'; the last '@' ends them */
		std::string user = authority.substr(0, at);
		authority.erase(0, at + 1);
		if (!user.empty())
			auth = base64(user);
	}
	std::string host, digits;
	bool have_port = false;
	if (!authority.empty() && authority[0] == '[')
	{
		size_t close = authority.find(']');
		if (close == std::string::npos)
			return false;
		host = authority.substr(1, close - 1);
		std::string after = authority.substr(close + 1);
		if (!after.empty())
		{
			if (after[0] != ':')
				return false;
			digits = after.substr(1);
			have_port = true;
		}
		for (size_t i = 0; i < host.size(); ++i)
			if (!(hexValue(host[i]) >= 0 || host[i] == ':' || host[i] == '.'))
				return false;
	}
	else
	{
		size_t colon = authority.rfind(':');
		if (colon != std::string::npos)
		{
			host = authority.substr(0, colon);
			digits = authority.substr(colon + 1);
			have_port = true;
		}
		else
			host = authority;
		for (size_t i = 0; i < host.size(); ++i)
			if (!hostChar(host[i]))
				return false;
	}
	if (host.empty() || host.size() > 253)
		return false;
	long port = 80;
	if (have_port && !digits.empty())
	{
		if (digits.size() > 5)
			return false;
		port = 0;
		for (size_t i = 0; i < digits.size(); ++i)
		{
			if (digits[i] < '0' || digits[i] > '9')
				return false;
			port = port * 10 + (digits[i] - '0');
		}
		if (port < 1 || port > 65535)
			return false;
	}
	std::string target = encodeTarget(path);
	if (target.size() > 4096)
		return false;
	t.host = host;
	t.port = (int)port;
	t.path = target;
	t.auth = auth;
	t.local = host == "127.0.0.1" || !strcasecmp(host.c_str(), "localhost");
	if (agent || headers)
		parseHeaders(frag, agent, headers);
	return true;
}

/* a host name resolved by a detached thread: the source and the thread each hold a reference, the last one frees */
struct eHdsFluxHttpNume
{
	pthread_mutex_t lock;
	int refs;
	bool done, ok;
	std::string host;               /* set before the thread starts, never changed */
	struct sockaddr_storage addr;
	socklen_t len;
};

static void numeRelease(eHdsFluxHttpNume *n)
{
	pthread_mutex_lock(&n->lock);
	bool last = --n->refs == 0;
	pthread_mutex_unlock(&n->lock);
	if (last)
	{
		pthread_mutex_destroy(&n->lock);
		delete n;
	}
}

static void *numeThread(void *p)
{
	eHdsFluxHttpNume *n = (eHdsFluxHttpNume *)p;
	struct addrinfo hints, *res = NULL;
	memset(&hints, 0, sizeof(hints));
	hints.ai_family = AF_UNSPEC;
	hints.ai_socktype = SOCK_STREAM;
	hints.ai_flags = AI_ADDRCONFIG;
	int r = getaddrinfo(n->host.c_str(), NULL, &hints, &res);
	pthread_mutex_lock(&n->lock);
	if (!r && res)
	{
		/* IPv4 first: many homes have no IPv6 route even when the name has an AAAA record */
		struct addrinfo *pick = res;
		for (struct addrinfo *a = res; a; a = a->ai_next)
			if (a->ai_family == AF_INET)
			{
				pick = a;
				break;
			}
		if (pick->ai_addrlen <= sizeof(n->addr))
		{
			memcpy(&n->addr, pick->ai_addr, pick->ai_addrlen);
			n->len = pick->ai_addrlen;
			n->ok = true;
		}
	}
	n->done = true;
	pthread_mutex_unlock(&n->lock);
	if (res)
		freeaddrinfo(res);
	numeRelease(n);
	return NULL;
}

eHdsFluxHttp::eHdsFluxHttp()
	:m_valid(false), m_refused(false), m_redirects(0), m_fd(-1), m_connecting(false), m_deadline(0), m_last_data(0),
	m_header_done(false), m_draining(false), m_have(0), m_position(0), m_retry_at(0), m_retry_ms(RETRY_MS), m_connections(0),
	m_have_reader(false), m_received(0), m_dropped(0), m_failure_logged(false), m_reserve_ms(0), m_reserving(false),
	m_reserve_from(0), m_reserve_pos(0), m_addr_len(0), m_nume(0), m_nume_from(0)
{
	memset(&m_addr, 0, sizeof(m_addr));
	m_creator = pthread_self();
	pthread_mutex_init(&m_reader_lock, NULL);
}

eHdsFluxHttp::~eHdsFluxHttp()
{
	if (m_fd >= 0)
		::close(m_fd);
	if (m_nume)
		numeRelease(m_nume);
	if (m_connections)
		eDebug("[eHdsFluxHttp] %s: closed after %d connection(s), %llu bytes received, %llu bytes dropped to resync",
			m_label.c_str(), m_connections, (unsigned long long)m_received, (unsigned long long)m_dropped);
	pthread_mutex_destroy(&m_reader_lock);
}

bool eHdsFluxHttp::accepts(const std::string &url)
{
	Tinta t;
	return parseAddress(url, t, NULL, NULL);
}

int eHdsFluxHttp::open(const std::string &url)
{
	Tinta t;
	std::string agent;
	m_headers.clear();
	if (!parseAddress(url, t, &agent, &m_headers))
	{
		m_valid = false;
		/* the address itself is not written: it can hold a user and a password */
		eDebug("[eHdsFluxHttp] not an http:// address this source can read");
		return -1;
	}
	m_agent = !agent.empty() ? agent : t.local ? std::string(AGENT_LOCAL) : std::string(AGENT_RETEA);
	m_start = t;
	setTarget(t);
	m_valid = true;
	return 0;
}

void eHdsFluxHttp::setTarget(const Tinta &t)
{
	m_target = t;
	if (t.local)
		m_label = t.path;
	else
	{
		char port[8];
		snprintf(port, sizeof(port), "%d", t.port);
		m_label = (t.host.find(':') != std::string::npos ? "[" + t.host + "]" : t.host) + ":" + port;
	}
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
		eDebug("[eHdsFluxHttp] %s: %s, new attempt in %d ms", m_label.c_str(), why, retry_ms);
	m_failure_logged = true;
	/* a host that failed before giving a stream is looked up again (its address may have changed) */
	if (!m_header_done)
		m_addr_host.clear();
	m_fd = -1;
	m_connecting = false;
	m_have = 0;
	m_header_done = false;
	/* the next attempt starts again from the address of the reference: a redirection usually expires */
	m_redirects = 0;
	if (m_target.host != m_start.host || m_target.port != m_start.port || m_target.path != m_start.path)
		setTarget(m_start);
	m_retry_at = nowMs() + retry_ms;
	m_retry_ms = retry_ms * 2 > RETRY_MAX_MS ? (int)RETRY_MAX_MS : retry_ms * 2;
}

/* the server ended a stream that played: the whole packets already received still go out (read() gives them before
   the next connection), only a broken packet at the end is dropped. Before, the end of the relay's stream threw away
   what was in the buffer (up to GATHER_BYTES while a short read gathered) */
void eHdsFluxHttp::endOfStream(int retry_ms, const char *why)
{
	size_t keep = wholePackets();
	disconnect(retry_ms, why);
	m_have = keep;
	m_draining = keep > 0;
}

/* an answer 4xx: the server refuses this stream; asking again every few seconds would not change it, and a provider
   can ban a receiver that does. The channel started again (zap) makes a new source. */
void eHdsFluxHttp::refuse(const char *why)
{
	if (m_fd >= 0)
		::close(m_fd);
	m_fd = -1;
	m_connecting = false;
	m_have = 0;
	m_header_done = false;
	m_refused = true;
	eDebug("[eHdsFluxHttp] %s: %s; no new attempt until the channel is started again", m_label.c_str(), why);
}

/* the address of m_target.host in m_addr. 0, or -1 with errno EAGAIN (still resolving, or failed and the retry is
   set) or EINTR (stop requested) */
int eHdsFluxHttp::haveAddress()
{
	const std::string &host = m_target.host;
	if (!m_addr_host.empty() && m_addr_host == host)
		return 0;
	memset(&m_addr, 0, sizeof(m_addr));
	struct sockaddr_in *a4 = (struct sockaddr_in *)&m_addr;
	struct sockaddr_in6 *a6 = (struct sockaddr_in6 *)&m_addr;
	if (m_target.local)
	{
		a4->sin_family = AF_INET;
		a4->sin_addr.s_addr = htonl(INADDR_LOOPBACK);
		m_addr_len = sizeof(*a4);
		m_addr_host = host;
		return 0;
	}
	if (inet_pton(AF_INET, host.c_str(), &a4->sin_addr) == 1)
	{
		a4->sin_family = AF_INET;
		m_addr_len = sizeof(*a4);
		m_addr_host = host;
		return 0;
	}
	memset(&m_addr, 0, sizeof(m_addr));
	if (inet_pton(AF_INET6, host.c_str(), &a6->sin6_addr) == 1)
	{
		a6->sin6_family = AF_INET6;
		m_addr_len = sizeof(*a6);
		m_addr_host = host;
		return 0;
	}
	/* a name: resolved by a thread of its own (getaddrinfo can wait for seconds and does not stop on a signal) */
	if (m_nume && m_nume->host != host)
	{
		numeRelease(m_nume);
		m_nume = 0;
	}
	if (!m_nume)
	{
		eHdsFluxHttpNume *n = new eHdsFluxHttpNume;
		pthread_mutex_init(&n->lock, NULL);
		n->refs = 2;
		n->done = n->ok = false;
		n->host = host;
		memset(&n->addr, 0, sizeof(n->addr));
		n->len = 0;
		pthread_attr_t attr;
		pthread_attr_init(&attr);
		pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
		pthread_attr_setstacksize(&attr, 256 * 1024);
		/* the thread gets no signal: SIGUSR1 is for the push thread */
		sigset_t all, old;
		sigfillset(&all);
		pthread_sigmask(SIG_BLOCK, &all, &old);
		pthread_t tid;
		int r = pthread_create(&tid, &attr, numeThread, n);
		pthread_sigmask(SIG_SETMASK, &old, NULL);
		pthread_attr_destroy(&attr);
		if (r)
		{
			n->refs = 1;
			numeRelease(n);
			disconnect(m_retry_ms, "no thread for the name lookup");
			errno = EAGAIN;
			return -1;
		}
		m_nume = n;
		m_nume_from = nowMs();
	}
	pthread_mutex_lock(&m_nume->lock);
	bool done = m_nume->done, ok = m_nume->ok;
	if (done && ok)
	{
		memcpy(&m_addr, &m_nume->addr, sizeof(m_addr));
		m_addr_len = m_nume->len;
	}
	pthread_mutex_unlock(&m_nume->lock);
	if (!done)
	{
		int64_t left = m_nume_from + NAME_MS - nowMs();
		if (left <= 0)
		{
			numeRelease(m_nume);
			m_nume = 0;
			disconnect(m_retry_ms, "the name server does not answer");
			errno = EAGAIN;
			return -1;
		}
		struct timespec t;
		t.tv_sec = 0;
		t.tv_nsec = (long)(left < WAIT_MS ? left : (int64_t)WAIT_MS) * 1000000L;
		if (nanosleep(&t, NULL) < 0 && errno == EINTR)
			return -1;
		errno = EAGAIN;
		return -1;
	}
	numeRelease(m_nume);
	m_nume = 0;
	if (!ok)
	{
		disconnect(m_retry_ms, "host name not found");
		errno = EAGAIN;
		return -1;
	}
	m_addr_host = host;
	return 0;
}

/* -1 with errno EINTR (stop requested) or EAGAIN (no connection yet, try again later); 0 = request sent */
int eHdsFluxHttp::connectNow()
{
	if (haveAddress() < 0)
		return -1;
	int fd = ::socket(m_addr.ss_family, SOCK_STREAM, 0);
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
	if (m_addr.ss_family == AF_INET6)
		((struct sockaddr_in6 *)&m_addr)->sin6_port = htons((uint16_t)m_target.port);
	else
		((struct sockaddr_in *)&m_addr)->sin_port = htons((uint16_t)m_target.port);
	m_fd = fd;
	if (::connect(fd, (struct sockaddr *)&m_addr, m_addr_len) == 0)
		return sendRequest();
	if (errno != EINPROGRESS)
	{
		disconnect(m_retry_ms, "connection refused");
		errno = EAGAIN;
		return -1;
	}
	/* a local relay answers at once or not at all; a server on the network gets its time over several reads */
	m_connecting = true;
	m_deadline = nowMs() + (m_target.local ? (int)WAIT_MS : (int)CONNECT_MS);
	return finishConnect();
}

/* one wait of at most WAIT_MS for the connect in progress. As connectNow() */
int eHdsFluxHttp::finishConnect()
{
	struct pollfd pf;
	pf.fd = m_fd;
	pf.events = POLLOUT;
	pf.revents = 0;
	int64_t left = m_deadline - nowMs();
	int r = ::poll(&pf, 1, left <= 0 ? 0 : left < WAIT_MS ? (int)left : (int)WAIT_MS);
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
		if (nowMs() >= m_deadline)
			disconnect(m_retry_ms, "connection timed out");
		errno = EAGAIN;
		return -1;
	}
	int err = 0;
	socklen_t len = sizeof(err);
	if (getsockopt(m_fd, SOL_SOCKET, SO_ERROR, &err, &len) < 0 || err)
	{
		disconnect(m_retry_ms, "connection refused");
		errno = EAGAIN;
		return -1;
	}
	m_connecting = false;
	return sendRequest();
}

int eHdsFluxHttp::sendRequest()
{
	std::string host;
	if (m_target.local)
	{
		char h[32];
		snprintf(h, sizeof(h), "127.0.0.1:%d", m_target.port);
		host = h;
	}
	else
	{
		host = m_target.host.find(':') != std::string::npos ? "[" + m_target.host + "]" : m_target.host;
		if (m_target.port != 80)
		{
			char p[8];
			snprintf(p, sizeof(p), ":%d", m_target.port);
			host += p;
		}
	}
	std::string request = "GET " + m_target.path + " HTTP/1.0\r\nHost: " + host + "\r\nUser-Agent: " + m_agent + "\r\n";
	if (!m_target.local)
		request += "Accept: */*\r\n";
	if (!m_target.auth.empty())
		request += "Authorization: Basic " + m_target.auth + "\r\n";
	request += m_headers;
	request += "Connection: close\r\n\r\n";
	if (::send(m_fd, request.data(), request.size(), MSG_NOSIGNAL) != (ssize_t)request.size())
	{
		disconnect(m_retry_ms, "request not sent");
		errno = EAGAIN;
		return -1;
	}
	m_connections++;
	m_have = 0;
	m_draining = false;
	m_header_done = false;
	m_deadline = nowMs() + ANSWER_MS;
	m_last_data = nowMs();
	return 0;
}

/* 1 = header read and accepted (body starts at m_buf), 0 = header not complete yet, -1 = bad answer (retry later),
   2 = redirected (the next read connects to the new address), 3 = refused (4xx) */
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
	std::string header((const char *)m_buf, end);
	size_t line = header.find_first_of("\r\n");
	std::string status = header.substr(0, line < 80 ? line : 80);
	int code = 0;
	if (status.compare(0, 7, "HTTP/1.") == 0 && status.size() >= 12 && status[8] == ' ')
		code = atoi(status.substr(9, 3).c_str());
	/* the headers this source needs: Location and Transfer-Encoding */
	std::string location;
	bool chunked = false;
	size_t p = line;
	while (p < header.size())
	{
		while (p < header.size() && (header[p] == '\r' || header[p] == '\n'))
			++p;
		size_t e = header.find_first_of("\r\n", p);
		if (e == std::string::npos)
			e = header.size();
		std::string h = header.substr(p, e - p);
		p = e;
		size_t colon = h.find(':');
		if (colon == std::string::npos)
			continue;
		std::string name = h.substr(0, colon), value = h.substr(colon + 1);
		while (!value.empty() && (value[0] == ' ' || value[0] == '\t'))
			value.erase(0, 1);
		while (!value.empty() && (value[value.size() - 1] == ' ' || value[value.size() - 1] == '\t'))
			value.erase(value.size() - 1);
		if (!strcasecmp(name.c_str(), "Location"))
			location = value;
		else if (!strcasecmp(name.c_str(), "Transfer-Encoding") && strcasestr(value.c_str(), "chunked"))
			chunked = true;
	}
	if (code == 200 || code == 206)
	{
		if (chunked)
		{
			/* a server may not send chunks to an HTTP/1.0 request; the chunk sizes would break the packets */
			eDebug("[eHdsFluxHttp] %s: the server answers in chunks, which an HTTP/1.0 request does not allow", m_label.c_str());
			return -1;
		}
		memmove(m_buf, m_buf + end, m_have - end);
		m_have -= end;
		m_header_done = true;
		m_retry_ms = RETRY_MS;
		m_redirects = 0;
		eDebug("[eHdsFluxHttp] %s: stream connected (connection %d)", m_label.c_str(), m_connections);
		m_failure_logged = false;
		return 1;
	}
	if (code == 301 || code == 302 || code == 303 || code == 307 || code == 308)
	{
		if (location.empty())
		{
			eDebug("[eHdsFluxHttp] %s: answer %d without an address", m_label.c_str(), code);
			return -1;
		}
		if (++m_redirects > REDIRECTS_MAX)
		{
			eDebug("[eHdsFluxHttp] %s: more than %d redirections", m_label.c_str(), (int)REDIRECTS_MAX);
			return -1;
		}
		Tinta t;
		if (location.compare(0, 2, "//") == 0)
			location = "http:" + location;
		if (startsNoCase(location, "https://"))
		{
			eDebug("[eHdsFluxHttp] %s: answer %d, redirected to an https address (this source has no TLS)", m_label.c_str(), code);
			return 3;
		}
		if (startsNoCase(location, "http://"))
		{
			if (!parseAddress(location, t, NULL, NULL))
			{
				eDebug("[eHdsFluxHttp] %s: answer %d with an address this source cannot read", m_label.c_str(), code);
				return -1;
			}
		}
		else
		{
			/* a relative address: the same server; an absolute path, or one next to the current one */
			t = m_target;
			if (location[0] == '/')
				t.path = encodeTarget(location);
			else
			{
				std::string base = m_target.path.substr(0, m_target.path.find('?'));
				t.path = base.substr(0, base.rfind('/') + 1) + encodeTarget(location);
			}
		}
		std::string from = m_label;
		::close(m_fd);
		m_fd = -1;
		m_connecting = false;
		m_have = 0;
		m_header_done = false;
		setTarget(t);
		m_retry_at = nowMs();
		eDebug("[eHdsFluxHttp] %s: answer %d, redirected to %s", from.c_str(), code, m_label.c_str());
		return 2;
	}
	if (code >= 400 && code < 500 && code != 408 && code != 429)
	{
		eDebug("[eHdsFluxHttp] %s: answer %d", m_label.c_str(), code);
		return 3;
	}
	eDebug("[eHdsFluxHttp] %s: answer \"%s\"", m_label.c_str(), status.c_str());
	return -1;
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
		if (m_header_done)
			endOfStream(RETRY_MS, m_target.local ? "the relay closed the stream" : "the server closed the stream");
		else
			disconnect(m_retry_ms, m_target.local ? "the relay closed the stream" : "the server closed the stream");
		errno = EAGAIN;
		return -1;
	}
	m_have += (size_t)n;
	m_received += (uint64_t)n;
	m_last_data = nowMs();
	if (!m_header_done)
	{
		int h = parseHeader();
		if (h == 3)
		{
			refuse("the server refuses the stream");
			errno = EAGAIN;
			return -1;
		}
		if (h < 0)
		{
			disconnect(RETRY_MAX_MS / 2, "no usable answer");
			errno = EAGAIN;
			return -1;
		}
		if (h == 0 || h == 2)
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
		eDebug("[eHdsFluxHttp] %s: start reserve given after %lld ms: %u bytes", m_label.c_str(),
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
	if (!m_valid)
	{
		errno = EINVAL;
		return -1;
	}
	if (m_refused)
	{
		/* nothing more from this server; the push thread keeps asking, a pause per call keeps it quiet */
		struct timespec t;
		t.tv_sec = 0;
		t.tv_nsec = (long)WAIT_MS * 1000000L;
		if (nanosleep(&t, NULL) < 0 && errno == EINTR)
			return -1;
		errno = EAGAIN;
		return -1;
	}
	if (!m_reserving && !m_reserve.empty())
		return serveReserve(buf, count);
	if (m_fd < 0 && m_draining)
	{
		/* the last packets of a stream the server closed, before the next connection */
		size_t n = m_have < count ? m_have : count;
		n -= n % PACKET;
		if (n)
		{
			memcpy(buf, m_buf, n);
			memmove(m_buf, m_buf + n, m_have - n);
			m_have -= n;
			m_position += n;
		}
		if (m_have < (size_t)PACKET)
		{
			m_have = 0;
			m_draining = false;
		}
		if (n)
			return (ssize_t)n;
	}
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
	if (m_connecting)
	{
		if (finishConnect() == 0)
			errno = EAGAIN;
		return -1;
	}
	/* a server on the network that does not answer, or stops sending, gets a new connection (a local relay may pause
	   on purpose, it keeps its connection as before) */
	if (!m_target.local)
	{
		int64_t now = nowMs();
		if (!m_header_done && now >= m_deadline)
		{
			disconnect(m_retry_ms, "no answer from the server");
			errno = EAGAIN;
			return -1;
		}
		if (m_header_done && now - m_last_data >= SILENCE_MS)
		{
			disconnect(RETRY_MS, "the server sends nothing");
			errno = EAGAIN;
			return -1;
		}
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
	return m_valid;
}
