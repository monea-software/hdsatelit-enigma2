/* SoftCSA: the CA PMT server socket and the softcam protocol 3 (control words over the socket). GPL-2.0-only.
 * Protocol 3 client code by WXbet, Betacentauri, 2026; the CA PMT list logic comes from the enigma2 CA handler.
 * Modificat de moneasoftware.com si hdsatelit.com, 2026: a server of its own (no lib/network in this tree), next to
 * the eDVBCAService of lib/dvb/pmt.cpp, which keeps its old client path to /tmp/camd.socket. */
#ifndef __DVB_CAHANDLER_H_
#define __DVB_CAHANDLER_H_

#ifndef SWIG

#include <lib/base/ebase.h>
#include <lib/base/buffer.h>
#include <lib/dvb/idvb.h>
#include <sigc++/sigc++.h>
#include <list>
#include <map>
#include <set>
#include <string>

/*
 * Two ways for a softcam to get the CA PMT objects:
 *  - the old one (lib/dvb/pmt.cpp, eDVBCAService): the softcam listens on /tmp/camd.socket and enigma2 connects to it
 *    once per service and writes the CA PMT ("pmt_mode = 0" in the softcam). Unchanged.
 *  - this one: enigma2 listens on /tmp/.listen.camd.socket, the softcam connects to it and stays connected ("pmt_mode
 *    = 6"). enigma2 sends CLIENT_INFO (protocol 3); after the SERVER_INFO answer it writes the whole list of CA PMT
 *    objects (ca_pmt_list_management first / more / last), then each change (only / add / update, CMD_NOT_SELECTED when
 *    a service goes). With protocol 3 every object starts with 0xA5 and a message id (the service id below), and the
 *    softcam can send control words back (CA_SET_DESCR): software descrambling of CSA-ALT (lib/dvb/csasession.h).
 * While a softcam is connected here, the old path does not write (the same CA PMT twice would start two descramblings).
 */

#define PMT_SERVER_SOCKET "/tmp/.listen.camd.socket"

/* ca_pmt_list_management values */
#define LIST_MORE 0x00
#define LIST_FIRST 0x01
#define LIST_LAST 0x02
#define LIST_ONLY 0x03
#define LIST_ADD 0x04
#define LIST_UPDATE 0x05

/* ca_pmt_cmd_id values */
#define CMD_OK_DESCRAMBLING 0x01
#define CMD_OK_MMI 0x02
#define CMD_QUERY 0x03
#define CMD_NOT_SELECTED 0x04

class eDVBCAHandler;
class eDVBCAService;

/* one softcam connected to PMT_SERVER_SOCKET; the descriptor is our end of the socket pair of eDVBCWHandler */
class ePMTClient: public sigc::trackable
{
	eDVBCAHandler *parent;
	int m_fd;
	ePtr<eSocketNotifier> m_sn;
	eIOBuffer m_in;
	unsigned char receivedTag[4];
	int receivedLength;
	unsigned char *receivedData;
	unsigned char receivedHeader[5];
	int m_protocolVersion;
	bool m_serverInfoReceived;
	std::string m_serverInfo;
	bool m_closed;

	void notifier(int what);
	void dataAvailable();
	bool processCaSetDescrPacket();
	bool processServerInfoPacket();
	bool processEcmInfoPacket();
	int bytesAvailable() const { return m_in.size(); }
	int readBlock(char *data, int len) { return m_in.read(data, len); }
public:
	ePMTClient(eDVBCAHandler *handler, int fd);
	~ePMTClient();
	void sendClientInfo();
	int writeBlock(const char *data, int len);
	/* capmt: 5 bytes protocol 3 header, then the CA PMT object of len bytes; the header goes only with protocol 3 */
	int writeCAPMTObject(const char *capmt, int len);
	bool ready() const { return m_serverInfoReceived && !m_closed; }
	bool closed() const { return m_closed; }
	int protocolVersion() const { return m_protocolVersion; }
	const std::string &serverInfo() const { return m_serverInfo; }
	int fd() const { return m_fd; }
};

class eDVBCAHandler: public sigc::trackable
{
	friend class ePMTClient;
	int m_listen_fd;
	ePtr<eSocketNotifier> m_listen_sn;
	std::list<ePMTClient*> clients;
	ePtr<eTimer> serviceLeft, m_cleanup;
	std::map<uint32_t, uint16_t> m_service_caid; /* service id -> CAID, from the softcam ECM_INFO */
	std::map<eServiceReferenceDVB, uint32_t> m_service_ids;
	uint32_t serviceIdCounter;
	bool m_protocol3_established; /* SERVER_INFO received from at least one client */
	unsigned long m_cw_count, m_ecm_info_count;
	/* proof that the softcam really delivers control words here (a softcam answering protocol 3 may not): the serial
	   of the softcam connection (one more at each SERVER_INFO), the control words received since then, and the
	   services (SID/TSID/ONID) for which control words came */
	unsigned long m_connection, m_cw_connection;
	std::set<uint64_t> m_cw_services;
	void noteCw(const eServiceReferenceDVB &service);
	/* /tmp/hds-softcsa.stat: the state and the counters (key=value), every 2 s when they changed; for the proofs and
	   the reports of the testers, since the interface log leaves out the lines about access modules */
	ePtr<eTimer> m_stat_timer;
	std::string m_stat_last;
	void writeStat();
	/* the verdicts of eDVBCSAEngine::checkKey (recorder thread) wake the main thread through this pipe; sendVerdicts
	   writes them to the softcams that announced "hdsk1" (DVBAPI_HDS_CW_REPORT) */
	int m_verdict_pipe[2];
	ePtr<eSocketNotifier> m_verdict_sn;
	void sendVerdicts(int what);

	void listenActivated(int what);
	void newConnection(int socket);
	void connectionLost(ePMTClient *client);
	void cleanupClients();
	void serviceGone();
	void distributeCAPMT();
	void serverInfoReceived(ePMTClient *client);
	static eDVBCAHandler *instance;
public:
	eDVBCAHandler();
	~eDVBCAHandler();
	static eDVBCAHandler *getInstance() { return instance; }

	/* service, parity, cw (8 bytes), caid, softcam service id (message id) */
	sigc::signal<void(eServiceReferenceDVB, int, const char*, uint16_t, uint32_t)> receivedCw;
	/* a softcam answered on the socket (SERVER_INFO): software descrambling may be possible now for a service already
	   playing (eDVBServicePlay::softCsaProgram) */
	sigc::signal<void()> softcamConnected;

	/* from eDVBCAService (pmt.cpp) */
	uint32_t serviceId(const eServiceReferenceDVB &ref);
	void serviceRegistered();
	void capmtBuilt(eDVBCAService *service, bool isUpdate);
	void serviceRemoved(eDVBCAService *service);
	void serviceListChanged();
	/* a softcam answered here (SERVER_INFO): the old path does not write */
	bool clientConnected() const { return m_protocol3_established; }

	int getServiceReference(eServiceReferenceDVB &service, uint32_t serviceId);

	/* state for Python (hdsSoftCsaStare): highest protocol of a connected softcam (-1 none), its info text */
	int protocolVersion() const;
	std::string serverInfo() const;
	unsigned long cwCount() const { return m_cw_count; }
	unsigned long connection() const { return m_connection; }
	/* control words came over the socket since the softcam connected (the softcam gives CSA-ALT to enigma2) */
	bool cwProven() const { return m_cw_connection > 0; }
	bool cwReceivedFor(const eServiceReferenceDVB &service) const;
	unsigned long ecmInfoCount() const { return m_ecm_info_count; }
	/* software descrambling can work: libdvbcsa loaded and a softcam with protocol 3 and the extended CW api */
	bool softCsaReady() const;
};

#endif /* SWIG */

/* for Python: {"biblioteca": libdvbcsa loaded, "versiune": its version, "client": a softcam answered on the new socket,
   "protocol": its protocol, "modul": its info text, "extins": extended CW api announced, "gata": software descrambling
   can work, "cuvinte": control words received, "ecm": ECM_INFO received, "descifrate" / "anulate" / "chei": counters of
   the engines, "active": software descrambling sessions active now} */
PyObject *hdsSoftCsaStare();
/* what the ECM of a service told on this receiver since start: 1 CSA-ALT, 0 not, -1 unknown */
int hdsSoftCsaCanal(const char *ref);
/* 2 control words came over the socket for the service (its software descrambling works), 1 its ECM says CSA-ALT,
   0 its ECM says not CSA-ALT, -1 unknown; all since start */

#endif /* __DVB_CAHANDLER_H_ */
