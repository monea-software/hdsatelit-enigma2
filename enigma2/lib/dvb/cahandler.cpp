/* SoftCSA: the CA PMT server socket and the softcam protocol 3 (control words over the socket). GPL-2.0-only.
 * Protocol 3 client code by WXbet, Betacentauri, 2026; the CA PMT list logic comes from the enigma2 CA handler.
 * Modificat de moneasoftware.com si hdsatelit.com, 2026: a server of its own (no lib/network in this tree), next to
 * the eDVBCAService of lib/dvb/pmt.cpp, which keeps its old client path to /tmp/camd.socket. */
#include <unistd.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <errno.h>
#include <poll.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <arpa/inet.h>
#include <linux/dvb/ca.h>
#include <string>
#include <vector>
#include <mutex>

#include <lib/dvb/cahandler.h>
#include <lib/dvb/pmt.h>
#include <lib/dvb/cwhandler.h>
#include <lib/dvb/csaengine.h>
#include <lib/dvb/csasession.h>
#include <lib/base/eerror.h>
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/python/python.h>

ePMTClient::ePMTClient(eDVBCAHandler *handler, int fd)
	: parent(handler), m_fd(fd), m_in(1024), receivedLength(0), receivedData(NULL), m_protocolVersion(-1),
	m_serverInfoReceived(false), m_closed(false)
{
	receivedTag[0] = 0;
	memset(receivedHeader, 0, sizeof(receivedHeader));
	int flags = fcntl(m_fd, F_GETFL, 0);
	if (flags >= 0)
		fcntl(m_fd, F_SETFL, flags | O_NONBLOCK);
	m_sn = eSocketNotifier::create(eApp, m_fd, eSocketNotifier::Read | eSocketNotifier::Priority |
		eSocketNotifier::Error | eSocketNotifier::Hungup);
	CONNECT(m_sn->activated, ePMTClient::notifier);
}

ePMTClient::~ePMTClient()
{
	m_sn = 0;
	/* only our end of the socket pair: the thread of eDVBCWHandler sees it closed and closes the softcam socket itself
	   (closing that one from here could hit a descriptor number already reused while the thread still polls it) */
	if (m_fd >= 0)
		::close(m_fd);
	delete[] receivedData;
}

void ePMTClient::notifier(int what)
{
	if (m_closed)
		return;
	if (what & (eSocketNotifier::Read | eSocketNotifier::Priority))
	{
		char buf[4096];
		while (true)
		{
			ssize_t n = ::read(m_fd, buf, sizeof(buf));
			if (n > 0)
			{
				m_in.write(buf, n);
				if (n < (ssize_t)sizeof(buf))
					break;
				continue;
			}
			if (n == 0)
				what |= eSocketNotifier::Hungup;
			else if (errno != EAGAIN && errno != EINTR)
				what |= eSocketNotifier::Error;
			break;
		}
		if (m_in.size())
			dataAvailable();
	}
	if (what & (eSocketNotifier::Hungup | eSocketNotifier::Error))
	{
		m_closed = true;
		m_sn->stop();
		if (parent)
			parent->connectionLost(this);
	}
}

void ePMTClient::dataAvailable()
{
	while (1)
	{
		/* this handler might be called multiple times (by the socket notifier), till we have the complete message */

		if (receivedLength < 1)
		{
			if (bytesAvailable() < 6) return;
			receivedLength = readBlock((char*)receivedHeader, 1);
			// check softcam protocol version -> version 3 starts with 0xA5
			if ((m_protocolVersion == 3 || m_protocolVersion == -1) && receivedHeader[0] == 0xA5)
			{
				// Softcam protocol 3: read 4 byte msgid + first byte of tag
				readBlock((char*)receivedHeader, 5);
				receivedTag[0] = receivedHeader[4];
			}
			else if (m_protocolVersion == 3 && receivedHeader[0] != 0xA5)
			{
				eDebug("[ePMTClient] Error: Packet malformed! Byte %02X read instead of 0xA5 (message start) -> skip available bytes", receivedHeader[0]);
				m_in.clear();
				// Reset state machine after error to allow recovery
				receivedLength = 0;
				memset(receivedHeader, 0, 5);
				continue; // Try to parse next packet
			}
			else
				receivedTag[0] = receivedHeader[0];
		}

		if (receivedLength < 4)
		{
			if (bytesAvailable() < 3) return;
			receivedLength += readBlock((char*)receivedTag + receivedLength, 4 - receivedLength);
			if (receivedLength < 4) return;
		}

		if (receivedTag[0] == 0x40 && receivedTag[1] == 0x10 && receivedTag[2] == 0x6F && receivedTag[3] == 0x86) // DVBAPI_CA_SET_DESCR (0x40106F86)
		{
			if (!processCaSetDescrPacket()) return;
		}
		else if (receivedTag[0] == 0x40 && receivedTag[1] == 0x0C && receivedTag[2] == 0x6F && receivedTag[3] == 0x88) // DVBAPI_CA_SET_DESCR_MODE (0x400C6F88)
		{
			// CA_SET_DESCR_MODE packet structure (after 0xA5 + msgid + tag): adapter index (1) + ca_descr_mode (12)
			int skipLength = 13;
			if (bytesAvailable() < skipLength)
				return;
			char skipBuf[16];
			readBlock(skipBuf, skipLength);
		}
		else if (receivedTag[0] == 0xFF && receivedTag[1] == 0xFF && receivedTag[2] == 0x00 && receivedTag[3] == 0x02) // DVBAPI_SERVER_INFO (0xFFFF0002)
		{
			if (!processServerInfoPacket()) return;
		}
		else if (receivedTag[0] == 0xFF && receivedTag[1] == 0xFF && receivedTag[2] == 0x00 && receivedTag[3] == 0x03) // DVBAPI_ECM_INFO (0xFFFF0003)
		{
			if (!processEcmInfoPacket()) return;
		}
		else
		{
			// Unknown packet type - log and skip
			eDebug("[ePMTClient] Unknown packet tag: %02X %02X %02X %02X (msgid: %02X%02X%02X%02X) - skipping",
				receivedTag[0], receivedTag[1], receivedTag[2], receivedTag[3],
				receivedHeader[0], receivedHeader[1], receivedHeader[2], receivedHeader[3]);
		}

		delete[] receivedData;
		receivedData = NULL;
		receivedLength = 0;
		memset(receivedHeader, 0, 5);
		receivedTag[0] = 0;
	}
}

int ePMTClient::writeBlock(const char *data, int len)
{
	int done = 0, waits = 0;
	while (done < len && !m_closed)
	{
		ssize_t w = ::write(m_fd, data + done, len - done);
		if (w > 0)
		{
			done += w;
			continue;
		}
		if (w < 0 && errno == EINTR)
			continue;
		if (w < 0 && errno == EAGAIN && ++waits <= 10)
		{
			/* the socket pair is drained by the thread of eDVBCWHandler: wait for it a moment */
			struct pollfd pfd;
			pfd.fd = m_fd;
			pfd.events = POLLOUT;
			pfd.revents = 0;
			poll(&pfd, 1, 50);
			continue;
		}
		eDebug("[ePMTClient] write failed after %d of %d bytes (%m)", done, len);
		break;
	}
	return done;
}

void ePMTClient::sendClientInfo()
{
	// Send CLIENT_INFO to request Protocol 3 from the softcam
	// Note: CLIENT_INFO is sent WITHOUT 0xA5 wrapper - the protocol version
	// field (0x0003) tells the softcam we want Protocol 3 responses
	char data[20];
	memset(data, 0, sizeof(data));
	data[0] = 0xFF; // DVBAPI_CLIENT_INFO 0xFFFF0001
	data[1] = 0xFF;
	data[2] = 0x00;
	data[3] = 0x01;
	data[4] = 0x00; // DVBAPI_PROTOCOL_VERSION 3
	data[5] = 0x03;
	memcpy(data + 7, "Enigma2", 7);
	data[6] = 7;    // Text length

	eDebug("[ePMTClient] sendClientInfo");
	writeBlock((const char*)data, 14);
}

bool ePMTClient::processCaSetDescrPacket()
{
	// CA_SET_DESCR packet structure (Protocol 3):
	// - adapter index: 1 byte
	// - ca_descr_t: index(4) + parity(4) + cw(8) = 16 bytes
	// Total: 17 bytes after tag
	// Note: serviceId is in msgid (receivedHeader[0-3])
	int readDataLength = receivedLength - 4;
	int fixDataLength = 17;
	int read;
	uint32_t serviceId;

	if (receivedData == NULL)
		receivedData = new unsigned char[fixDataLength];
	if (bytesAvailable() < fixDataLength - readDataLength) return false;
	read = readBlock((char*)receivedData + readDataLength, fixDataLength - readDataLength);
	receivedLength += read;
	readDataLength += read;
	if (readDataLength == fixDataLength)
	{
		ca_descr_t descr;
		memcpy(&descr, receivedData + 1, sizeof(ca_descr_t));
		descr.index = ntohl(descr.index);
		descr.parity = ntohl(descr.parity);
		memcpy(&serviceId, receivedHeader, sizeof(uint32_t)); // msgid
		serviceId = ntohl(serviceId);
		parent->m_cw_count++;

		eServiceReferenceDVB service;
		if (parent->getServiceReference(service, serviceId) == 0)
		{
			/* the control word itself is never written to the log */
			eDebug("[ePMTClient] CaSetDescr: ServiceId %u, Parity %u, service %s", serviceId, descr.parity, service.toString().c_str());
			// Get CAID from ECM_INFO (if available)
			uint16_t caid = 0;
			std::map<uint32_t, uint16_t>::const_iterator it = parent->m_service_caid.find(serviceId);
			if (it != parent->m_service_caid.end())
				caid = it->second;
			parent->noteCw(service);
			parent->receivedCw(service, descr.parity, (const char*)descr.cw, caid, serviceId);
		}
		else
			eDebug("[ePMTClient] CaSetDescr: ServiceId %u, Parity %u, no service", serviceId, descr.parity);
		return true;
	}
	return false;
}

bool ePMTClient::processServerInfoPacket()
{
	// SERVER_INFO packet structure:
	// - protocol version: 2 bytes (network byte order)
	// - info string length: 1 byte
	// - info string: variable
	int readDataLength = receivedLength - 4;
	int fixDataLength = 3; // 2 byte protocol version + 1 byte info len
	int read;

	if (receivedData == NULL)
		receivedData = new unsigned char[260]; // max 256 byte info + 3 bytes header + 1 NULL byte

	if (readDataLength < fixDataLength)
	{
		if (bytesAvailable() < fixDataLength - readDataLength) return false;
		read = readBlock((char*)receivedData + readDataLength, fixDataLength - readDataLength);
		receivedLength += read;
		readDataLength += read;
	}
	if (readDataLength >= fixDataLength)
	{
		readDataLength -= fixDataLength;
		int infoLength = receivedData[2];
		if (bytesAvailable() < infoLength - readDataLength) return false;
		read = readBlock((char*)receivedData + fixDataLength + readDataLength, infoLength - readDataLength);
		receivedLength += read;
		readDataLength += read;
		if (readDataLength == infoLength)
		{
			uint16_t serverProtocolVersion;
			memcpy(&serverProtocolVersion, receivedData, sizeof(uint16_t));
			serverProtocolVersion = ntohs(serverProtocolVersion);
			if (serverProtocolVersion < 3)
				m_protocolVersion = serverProtocolVersion;
			else
				m_protocolVersion = 3;
			receivedData[fixDataLength + infoLength] = '\0';
			m_serverInfo = std::string((const char*)receivedData + fixDataLength);
			eDebug("[ePMTClient] ServerInfo: Protocol %u, Info: %s", serverProtocolVersion, m_serverInfo.c_str());

			m_serverInfoReceived = true;
			if (parent)
				parent->serverInfoReceived(this);
			return true;
		}
	}
	return false;
}

bool ePMTClient::processEcmInfoPacket()
{
	// ECM_INFO packet structure (Protocol 3):
	// - adapter index: 1 byte
	// - program number: 2 bytes
	// - caid: 2 bytes
	// - pid: 2 bytes
	// - provid: 4 bytes
	// - ecmTime: 4 bytes
	// = 15 bytes fixed part
	// - cardsystem: 1 byte len + string
	// - reader: 1 byte len + string
	// - from: 1 byte len + string
	// - protocol: 1 byte len + string
	// - hops: 1 byte
	// Note: serviceId is in msgid (receivedHeader[0-3])
	int readDataLength = receivedLength - 4;
	int fixDataLength = 15;
	int read, pos = 0, i = 0, old_pos = 0;
	uint32_t serviceId, providerId, ecmTime;
	uint16_t program, caid, pid;
	int hops = -1;
	unsigned char cardsystem[257];
	unsigned char reader[257];
	unsigned char from[257];
	unsigned char protocol[257];
	unsigned char* dest = cardsystem;

	cardsystem[0] = reader[0] = from[0] = protocol[0] = '\0';
	if (receivedData == NULL)
	{
		receivedData = new unsigned char[1041];
		memset(receivedData, 0 , 1041);
	}
	if (readDataLength < fixDataLength)
	{
		if (bytesAvailable() < fixDataLength - readDataLength) return false;
		read = readBlock((char*)receivedData + readDataLength, fixDataLength - readDataLength);
		receivedLength += read;
		readDataLength += read;
	}
	if (readDataLength >= fixDataLength)
	{
		readDataLength -= fixDataLength;
		while (bytesAvailable())
		{
			// read cardsystem name, reader, from, protocol strings
			while (pos < readDataLength && i < 4)
			{
				old_pos = pos + 1;
				pos += receivedData[fixDataLength + pos] + 1; // 1 byte string len
				i++;
			}
			if (pos == readDataLength && i > 0) // string i fully read
			{
				if (i == 1)
					dest = cardsystem;
				else if (i == 2)
					dest = reader;
				else if (i == 3)
					dest = from;
				else if (i == 4)
					dest = protocol;

				unsigned char* str = receivedData + fixDataLength + old_pos;
				if (pos - old_pos > 0)
				{
					memcpy(dest, str, pos - old_pos);
					dest[pos - old_pos] = '\0';
				}
				else
					dest[0] = '\0';

				if (i == 4)
				{
					read = readBlock((char*)receivedData + fixDataLength + readDataLength, 1);
					hops = receivedData[fixDataLength + readDataLength];

					// Extract fixed fields
					memcpy(&serviceId, receivedHeader, sizeof(uint32_t)); // msgid
					serviceId = ntohl(serviceId);

					memcpy(&program, receivedData + 1, sizeof(uint16_t));
					program = ntohs(program);
					memcpy(&caid, receivedData + 3, sizeof(uint16_t));
					caid = ntohs(caid);
					memcpy(&pid, receivedData + 5, sizeof(uint16_t));
					pid = ntohs(pid);
					memcpy(&providerId, receivedData + 7, sizeof(uint32_t));
					providerId = ntohl(providerId);
					memcpy(&ecmTime, receivedData + 11, sizeof(uint32_t));
					ecmTime = ntohl(ecmTime);

					// Store CAID for this service (will be sent with next CW)
					parent->m_service_caid[serviceId] = caid;
					parent->m_ecm_info_count++;
					eDebug("[ePMTClient] ECM Info msgid %u | sid %04X caid %04X pid %04X prov %06X | %ums | %s via %s hops %d", serviceId, program, caid, pid, providerId, ecmTime, reader, protocol, hops);

					return true;
				}
			}

			int bytesToRead = (pos == readDataLength) ? 1 : pos - readDataLength;
			if (bytesAvailable() < bytesToRead) return false;
			read = readBlock((char*)receivedData + fixDataLength + readDataLength, bytesToRead);
			receivedLength += read;
			readDataLength += read;
		}
	}
	return false;
}

int ePMTClient::writeCAPMTObject(const char* capmt, int len)
{
	if (m_protocolVersion == 3)
		return writeBlock(capmt, len + 5);
	return writeBlock(capmt + 5, len); // skip the protocol 3 header
}

/*
 * Identify whether the connecting client is capable of dvbapi Protocol 3.
 * Uses SO_PEERCRED to get the PID, then reads /proc/<pid>/exe (or /proc/<pid>/comm) to
 * determine the binary. Old softcams which crash on CLIENT_INFO are left out; all the
 * others are assumed Protocol 3 capable.
 */
static bool isProtocol3CapableClient(int socket_fd)
{
	struct ucred cred;
	socklen_t len = sizeof(cred);
	if (getsockopt(socket_fd, SOL_SOCKET, SO_PEERCRED, &cred, &len) != 0)
	{
		eDebug("[eDVBCAHandler] SO_PEERCRED failed: %m, treating as legacy client");
		return false;
	}

	char exe_path[256];
	std::string proc_path = "/proc/" + std::to_string(cred.pid) + "/exe";
	ssize_t n = readlink(proc_path.c_str(), exe_path, sizeof(exe_path) - 1);
	if (n <= 0)
	{
		proc_path = "/proc/" + std::to_string(cred.pid) + "/comm";
		int fd = ::open(proc_path.c_str(), O_RDONLY | O_CLOEXEC);
		if (fd < 0)
		{
			eDebug("[eDVBCAHandler] open(%s) failed: %m, treating as legacy client", proc_path.c_str());
			return false;
		}
		n = ::read(fd, exe_path, sizeof(exe_path) - 1);
		::close(fd);
		if (n <= 0)
		{
			eDebug("[eDVBCAHandler] read(%s) failed: %m, treating as legacy client", proc_path.c_str());
			return false;
		}
		while (n > 0 && (exe_path[n - 1] == '\n' || exe_path[n - 1] == '\r'))
			--n;
	}
	exe_path[n] = '\0';

	const char* basename = strrchr(exe_path, '/');
	basename = basename ? basename + 1 : exe_path;

	/* softcams which do not know Protocol 3 */
	static const char* const legacy_softcams[] = {
		"cccam", "doscam", "evocamd", "gbox", "mgcamd",
		"newcs", "rqcamd", "scam", "wicardd", nullptr
	};

	for (const char* const* p = legacy_softcams; *p; ++p)
	{
		if (strncasecmp(basename, *p, strlen(*p)) == 0)
		{
			eDebug("[eDVBCAHandler] Legacy client identified: %s (pid %d), skipping Protocol 3", basename, cred.pid);
			return false;
		}
	}

	eDebug("[eDVBCAHandler] Protocol 3 capable client: %s (pid %d)", basename, cred.pid);
	return true;
}

eDVBCAHandler *eDVBCAHandler::instance = NULL;

/* HDSatelit 0.7.4: the verdicts on the keys (eDVBCSAEngine::checkKey, recorder thread) waiting for the main thread.
   A small ring under a lock and a non-blocking pipe: the recorder thread never waits for the main loop (a full ring or
   pipe loses the verdict and counts it). */
namespace
{
	struct KeyVerdict
	{
		uint8_t cw[8];
		uint8_t parity;
		uint8_t works;
	};
	const int VERDICTS_MAX = 32;
	std::mutex g_verdicts_lock;
	KeyVerdict g_verdicts[VERDICTS_MAX];
	int g_verdicts_count = 0;
	int g_verdict_wake = -1;  // write end of eDVBCAHandler::m_verdict_pipe

	void queueKeyVerdict(const uint8_t *cw, int parity, bool works)
	{
		{
			std::lock_guard<std::mutex> l(g_verdicts_lock);
			if (g_verdicts_count >= VERDICTS_MAX)
			{
				g_csa_counters.verdicts_lost.fetch_add(1, std::memory_order_relaxed);
				return;
			}
			KeyVerdict &v = g_verdicts[g_verdicts_count++];
			memcpy(v.cw, cw, 8);
			v.parity = parity ? 1 : 0;
			v.works = works ? 1 : 0;
		}
		const char c = 1;
		ssize_t w __attribute__((unused)) = ::write(g_verdict_wake, &c, 1);  // EAGAIN: a wake is pending already
	}

	/* "hdsk1" in the capabilities after "; " of the SERVER_INFO text: the softcam reads DVBAPI_HDS_CW_REPORT */
	bool takesKeyVerdicts(const std::string &info)
	{
		size_t p = info.rfind("; ");
		if (p == std::string::npos)
			return false;
		std::string caps = "," + info.substr(p + 2) + ",";
		return caps.find(",hdsk1,") != std::string::npos;
	}
}

void eDVBCAHandler::sendVerdicts(int)
{
	char buf[64];
	while (::read(m_verdict_pipe[0], buf, sizeof(buf)) > 0)
		;
	KeyVerdict v[VERDICTS_MAX];
	int n;
	{
		std::lock_guard<std::mutex> l(g_verdicts_lock);
		n = g_verdicts_count;
		memcpy(v, g_verdicts, n * sizeof(KeyVerdict));
		g_verdicts_count = 0;
	}
	for (int i = 0; i < n; ++i)
	{
		/* protocol 3: 0xA5, message id (4), DVBAPI_HDS_CW_REPORT 0xFFFF0F01, length (1), then version 1, verdict
		   (1 = the key worked), parity, the control word half (8) */
		unsigned char msg[21] = { 0xA5, 0, 0, 0, 0, 0xFF, 0xFF, 0x0F, 0x01, 11, 1 };
		msg[11] = v[i].works;
		msg[12] = v[i].parity;
		memcpy(msg + 13, v[i].cw, 8);
		bool sent = false;
		for (std::list<ePMTClient*>::iterator it = clients.begin(); it != clients.end(); ++it)
			if ((*it)->ready() && (*it)->protocolVersion() == 3 && takesKeyVerdicts((*it)->serverInfo()) &&
				(*it)->writeBlock((const char*)msg, sizeof(msg)) == (int)sizeof(msg))
				sent = true;
		(sent ? g_csa_counters.verdicts_sent : g_csa_counters.verdicts_lost).fetch_add(1, std::memory_order_relaxed);
	}
}

eDVBCAHandler::eDVBCAHandler()
	: m_listen_fd(-1), serviceLeft(eTimer::create(eApp)), m_cleanup(eTimer::create(eApp)), serviceIdCounter(1),
	m_protocol3_established(false), m_cw_count(0), m_ecm_info_count(0), m_connection(0), m_cw_connection(0)
{
	if (instance == NULL)
		instance = this;
	CONNECT(serviceLeft->timeout, eDVBCAHandler::serviceGone);
	CONNECT(m_cleanup->timeout, eDVBCAHandler::cleanupClients);
	m_stat_timer = eTimer::create(eApp);
	CONNECT(m_stat_timer->timeout, eDVBCAHandler::writeStat);
	m_stat_timer->start(2000, false);

	m_verdict_pipe[0] = m_verdict_pipe[1] = -1;
	if (instance == this && ::pipe2(m_verdict_pipe, O_NONBLOCK | O_CLOEXEC) == 0)
	{
		m_verdict_sn = eSocketNotifier::create(eApp, m_verdict_pipe[0], eSocketNotifier::Read);
		CONNECT(m_verdict_sn->activated, eDVBCAHandler::sendVerdicts);
		g_verdict_wake = m_verdict_pipe[1];
		g_csa_key_verdict.store(queueKeyVerdict, std::memory_order_release);
	}

	::unlink(PMT_SERVER_SOCKET);
	m_listen_fd = ::socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
	if (m_listen_fd < 0)
	{
		eWarning("[eDVBCAHandler] socket failed (%m)");
		return;
	}
	struct sockaddr_un addr;
	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	strncpy(addr.sun_path, PMT_SERVER_SOCKET, sizeof(addr.sun_path) - 1);
	if (::bind(m_listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0 || ::listen(m_listen_fd, 5) < 0)
	{
		eWarning("[eDVBCAHandler] cannot listen on %s (%m)", PMT_SERVER_SOCKET);
		::close(m_listen_fd);
		m_listen_fd = -1;
		return;
	}
	::chmod(PMT_SERVER_SOCKET, 0666);
	m_listen_sn = eSocketNotifier::create(eApp, m_listen_fd, eSocketNotifier::Read);
	CONNECT(m_listen_sn->activated, eDVBCAHandler::listenActivated);
	eDebug("[eDVBCAHandler] listening on %s", PMT_SERVER_SOCKET);
}

eDVBCAHandler::~eDVBCAHandler()
{
	if (instance == this)
		instance = NULL;
	if (m_verdict_pipe[0] >= 0)
	{
		/* a verdict already in queueKeyVerdict may still write one byte: the pipe is left open (one per process) */
		g_csa_key_verdict.store(nullptr, std::memory_order_release);
		m_verdict_sn = 0;
	}
	for (std::list<ePMTClient*>::iterator it = clients.begin(); it != clients.end(); ++it)
		delete *it;
	clients.clear();
	m_listen_sn = 0;
	if (m_listen_fd >= 0)
	{
		::close(m_listen_fd);
		::unlink(PMT_SERVER_SOCKET);
	}
}

void eDVBCAHandler::listenActivated(int what)
{
	while (true)
	{
		int fd = ::accept4(m_listen_fd, NULL, NULL, SOCK_CLOEXEC);
		if (fd < 0)
			break;
		newConnection(fd);
	}
}

void eDVBCAHandler::newConnection(int socket)
{
	/* SO_PEERCRED must be called on the original accept() fd */
	bool protocol3_capable = isProtocol3CapableClient(socket);

	// Route through eDVBCWHandler proxy for MainLoop-independent CW delivery
	int client_fd = eDVBCWHandler::getInstance()->addConnection(socket);
	if (client_fd < 0)
	{
		eWarning("[eDVBCAHandler] eDVBCWHandler proxy failed, rejecting connection");
		::close(socket);
		return;
	}
	ePMTClient *client = new ePMTClient(this, client_fd);
	clients.push_back(client);

	/* nothing is sent before the SERVER_INFO answer: the softcam takes the protocol of a demux from the first CA PMT */
	if (protocol3_capable)
		client->sendClientInfo();
	/* old softcams get nothing here: they have the old path (/tmp/camd.socket) */
}

void eDVBCAHandler::connectionLost(ePMTClient *client)
{
	eDebug("[eDVBCAHandler] client disconnected");
	/* deleted from the main loop, outside the callback of its own socket notifier */
	m_cleanup->start(0, true);
}

void eDVBCAHandler::cleanupClients()
{
	bool had = m_protocol3_established;
	for (std::list<ePMTClient*>::iterator it = clients.begin(); it != clients.end(); )
	{
		if ((*it)->closed())
		{
			delete *it;
			it = clients.erase(it);
		}
		else
			++it;
	}
	bool any = false;
	for (std::list<ePMTClient*>::iterator it = clients.begin(); it != clients.end(); ++it)
		if ((*it)->ready())
			any = true;
	m_protocol3_established = any;
	if (had && !any)
	{
		eDebug("[eDVBCAHandler] last Protocol 3 client disconnected, falling back to legacy sendCAPMT");
		eDVBCAService::resendLegacy();
	}
}

static uint64_t tripletKey(const eServiceReferenceDVB &ref)
{
	return ((uint64_t)ref.getOriginalNetworkID().get() << 32) | ((uint64_t)ref.getTransportStreamID().get() << 16) |
		(uint64_t)ref.getServiceID().get();
}

void eDVBCAHandler::noteCw(const eServiceReferenceDVB &service)
{
	if (!m_cw_connection++)
		eDebug("[eDVBCAHandler] the softcam delivers control words over the socket (software descrambling works)");
	m_cw_services.insert(tripletKey(service));
}

void eDVBCAHandler::writeStat()
{
	char text[1024];
	/* 0.7.4: schimbari_paritate, chei_intarziate (cuvantul venit dupa schimbare), asteptari, asteptare_ms (in total),
	   asteptare_max_ms, asteptari_expirate (eDVBCSAEngine::releaseHolds); chei_verificate, chei_gresite
	   (cheia unei perioade noi care nu descifreaza un inceput de PES: linia modulului a dat un cuvant gresit) */
	int n = snprintf(text, sizeof(text),
		"biblioteca=%d\nclient=%d\nprotocol=%d\ngata=%d\nconexiune=%lu\ndovedit=%d\ncuvinte=%lu\ncuvinte_legatura=%lu\n"
		"ecm=%lu\nservicii_cu_cuvinte=%zu\nactive=%d\ndescifrate=%llu\nanulate=%llu\nchei=%llu\n"
		"schimbari_paritate=%llu\nchei_intarziate=%llu\nasteptari=%llu\nasteptare_ms=%llu\nasteptare_max_ms=%llu\n"
		"asteptari_expirate=%llu\nchei_verificate=%llu\nchei_gresite=%llu\nverdicte_trimise=%llu\nverdicte_pierdute=%llu\n",
		eDVBCSAEngine::isAvailable() ? 1 : 0, m_protocol3_established ? 1 : 0, protocolVersion(), softCsaReady() ? 1 : 0,
		m_connection, (m_protocol3_established && m_cw_connection) ? 1 : 0, m_cw_count, m_cw_connection, m_ecm_info_count,
		m_cw_services.size(), eDVBCSASession::activeCount(), g_csa_counters.descrambled.load(),
		g_csa_counters.nulled.load(), g_csa_counters.keys.load(), g_csa_counters.flips.load(),
		g_csa_counters.late.load(), g_csa_counters.waits.load(), g_csa_counters.wait_ms.load(),
		g_csa_counters.wait_max_ms.load(), g_csa_counters.wait_expired.load(), g_csa_counters.key_checks.load(),
		g_csa_counters.bad_keys.load(), g_csa_counters.verdicts_sent.load(), g_csa_counters.verdicts_lost.load());
	if (n <= 0 || n >= (int)sizeof(text) || m_stat_last == text)
		return;
	m_stat_last = text;
	const char *tmp = "/tmp/hds-softcsa.stat.tmp";
	int fd = ::open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
	if (fd < 0)
		return;
	bool ok = ::write(fd, text, n) == n;
	::close(fd);
	if (!ok || ::rename(tmp, "/tmp/hds-softcsa.stat") < 0)
		::unlink(tmp);
}

bool eDVBCAHandler::cwReceivedFor(const eServiceReferenceDVB &service) const
{
	return m_cw_services.count(tripletKey(service)) > 0;
}

void eDVBCAHandler::serverInfoReceived(ePMTClient *client)
{
	m_connection++;
	m_cw_connection = 0;
	m_protocol3_established = true;
	distributeCAPMT();
	softcamConnected();
}

uint32_t eDVBCAHandler::serviceId(const eServiceReferenceDVB &ref)
{
	/* the same id for a service every time, so the softcam always sees the same message id for it */
	std::map<eServiceReferenceDVB, uint32_t>::const_iterator it = m_service_ids.find(ref);
	if (it != m_service_ids.end())
		return it->second;
	uint32_t id = serviceIdCounter++;
	m_service_ids[ref] = id;
	return id;
}

void eDVBCAHandler::serviceRegistered()
{
	serviceLeft->stop();
}

void eDVBCAHandler::capmtBuilt(eDVBCAService *service, bool isUpdate)
{
	if (!m_protocol3_established)
		return;
	int list_management = isUpdate ? LIST_UPDATE : (eDVBCAService::numberOfBuiltServices() == 1 ? LIST_ONLY : LIST_ADD);
	bool sent = false;
	for (std::list<ePMTClient*>::iterator it = clients.begin(); it != clients.end(); ++it)
		if ((*it)->ready() && service->writeCAPMTObject(*it, list_management) > 0)
			sent = true;
	if (sent)
		service->notifyCapmtSent();
}

void eDVBCAHandler::serviceRemoved(eDVBCAService *service)
{
	/* the softcam stops descrambling this service (switching to a free service would leave it descrambling) */
	if (!m_protocol3_established || service->getCAPMTVersion() < 0)
		return;
	for (std::list<ePMTClient*>::iterator it = clients.begin(); it != clients.end(); ++it)
	{
		if ((*it)->ready())
		{
			eDebug("[eDVBCAHandler] sending CMD_NOT_SELECTED for service %s", service->toString().c_str());
			service->writeCAPMTObject(*it, LIST_UPDATE, CMD_NOT_SELECTED);
		}
	}
}

void eDVBCAHandler::serviceListChanged()
{
	distributeCAPMT();
	/* the clients close only when no service comes back for a while (a standby cycle); 10 s, not 2: a zap with a slow
	   PMT left the list empty for more than 2 s and the softcam was dropped in the middle of the zap */
	serviceLeft->startLongTimer(10);
}

void eDVBCAHandler::serviceGone()
{
	if (eDVBCAService::numberOfServices())
		return;
	// A standby cycle removes the last service and later starts the same one
	// again. Drop Protocol 3 clients here so the softcam cannot retain the old
	// demux/descrambler association across that cycle. The client reconnects
	// and receives a fresh CAPMT when playback resumes.
	if (!clients.empty())
		eDebug("[eDVBCAHandler] no more services, closing %zu client connections", clients.size());
	for (std::list<ePMTClient*>::iterator it = clients.begin(); it != clients.end(); ++it)
		delete *it;
	clients.clear();
	m_protocol3_established = false;
}

void eDVBCAHandler::distributeCAPMT()
{
	/* the list of CA PMT objects to each connected client; only services with a CA PMT built */
	std::vector<eDVBCAService*> ready_services;
	eDVBCAService::builtServices(ready_services);
	if (ready_services.empty())
		return;
	for (std::list<ePMTClient*>::iterator it = clients.begin(); it != clients.end(); ++it)
	{
		if (!(*it)->ready())
			continue;
		for (size_t idx = 0; idx < ready_services.size(); ++idx)
		{
			unsigned char list_management = (idx == 0) ? LIST_FIRST : LIST_MORE;
			if (idx == ready_services.size() - 1)
				list_management |= LIST_LAST;
			ready_services[idx]->writeCAPMTObject(*it, list_management);
		}
	}
}

int eDVBCAHandler::getServiceReference(eServiceReferenceDVB &service, uint32_t serviceId)
{
	return eDVBCAService::findById(serviceId, service);
}

int eDVBCAHandler::protocolVersion() const
{
	int v = -1;
	for (std::list<ePMTClient*>::const_iterator it = clients.begin(); it != clients.end(); ++it)
		if ((*it)->ready() && (*it)->protocolVersion() > v)
			v = (*it)->protocolVersion();
	return v;
}

std::string eDVBCAHandler::serverInfo() const
{
	for (std::list<ePMTClient*>::const_iterator it = clients.begin(); it != clients.end(); ++it)
		if ((*it)->ready())
			return (*it)->serverInfo();
	return "";
}

static bool extendedCw(const std::string &info)
{
	/* the capabilities after "; " in the info text: e1... = extended CW api, the key follows the mode */
	size_t p = info.rfind("; ");
	if (p == std::string::npos)
		return false;
	std::string caps = "," + info.substr(p + 2) + ",";
	return caps.find(",e1") != std::string::npos;
}

/* defined only where the recorder can descramble (lib/dvb/demux.cpp, every receiver since 0.7.4): elsewhere the weak symbol
   stays 0 and software descrambling is not offered (the relay goes on as before) */
extern bool hdsSoftCsaInRecorder __attribute__((weak));

static bool recorderCanDescramble()
{
	return &hdsSoftCsaInRecorder != 0 && hdsSoftCsaInRecorder;
}

bool eDVBCAHandler::softCsaReady() const
{
	if (!recorderCanDescramble() || !eDVBCSAEngine::isAvailable())
		return false;
	for (std::list<ePMTClient*>::const_iterator it = clients.begin(); it != clients.end(); ++it)
		if ((*it)->ready() && (*it)->protocolVersion() >= 3 && extendedCw((*it)->serverInfo()))
			return true;
	return false;
}

extern void PutToDict(ePyObject &dict, const char*key, long value); // defined in dvb/frontend.cpp
extern void PutToDict(ePyObject &dict, const char*key, const char *value);

PyObject *hdsSoftCsaStare()
{
	ePyObject r = PyDict_New();
	eDVBCAHandler *h = eDVBCAHandler::getInstance();
	bool lib = eDVBCSAEngine::isAvailable();
	PutToDict(r, "biblioteca", (long)lib);
	PutToDict(r, "receptor", (long)recorderCanDescramble());
	PutToDict(r, "versiune", lib ? eDVBCSAEngine::getLibraryVersion().c_str() : "");
	PutToDict(r, "client", (long)(h && h->clientConnected()));
	PutToDict(r, "protocol", (long)(h ? h->protocolVersion() : -1));
	std::string info = h ? h->serverInfo() : std::string();
	PutToDict(r, "modul", info.c_str());
	PutToDict(r, "extins", (long)extendedCw(info));
	PutToDict(r, "gata", (long)(h && h->softCsaReady()));
	PutToDict(r, "cuvinte", (long)(h ? h->cwCount() : 0));
	PutToDict(r, "ecm", (long)(h ? h->ecmInfoCount() : 0));
	PutToDict(r, "descifrate", (long)g_csa_counters.descrambled.load());
	PutToDict(r, "anulate", (long)g_csa_counters.nulled.load());
	PutToDict(r, "chei", (long)g_csa_counters.keys.load());
	PutToDict(r, "chei_verificate", (long)g_csa_counters.key_checks.load());
	PutToDict(r, "chei_gresite", (long)g_csa_counters.bad_keys.load());
	PutToDict(r, "active", (long)eDVBCSASession::activeCount());
	PutToDict(r, "conexiune", (long)(h ? h->connection() : 0));
	PutToDict(r, "dovedit", (long)(h && h->clientConnected() && h->cwProven()));
	return r;
}

int hdsSoftCsaCanal(const char *ref)
{
	if (!ref || !*ref)
		return -1;
	eServiceReference r{std::string(ref)};
	if (r.type != eServiceReference::idDVB)
		return -1;
	eDVBCAHandler *h = eDVBCAHandler::getInstance();
	if (h && h->cwReceivedFor((eServiceReferenceDVB&)r))
		return 2;
	return eDVBCSASession::cachedCsaAlt((eServiceReferenceDVB&)r);
}

eAutoInitP0<eDVBCAHandler> init_eDVBCAHandler(eAutoInitNumbers::dvb, "CA handler (softcam socket)");
