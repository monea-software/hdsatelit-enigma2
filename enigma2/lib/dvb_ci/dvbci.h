/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __dvbci_dvbci_h
#define __dvbci_dvbci_h

#ifndef SWIG

#include <lib/base/ebase.h>
#include <lib/service/iservice.h>
#include <lib/python/python.h>
#include <set>
#include <queue>

class eDVBCISession;
class eDVBCIApplicationManagerSession;
class eDVBCICAManagerSession;
class eDVBCIMMISession;
class eDVBCICcSession;
class eDVBServicePMTHandler;
class eDVBCISlot;
class eDVBCIInterfaces;

struct queueData
{
	__u8 prio;
	unsigned char *data;
	unsigned int len;
	queueData( unsigned char *data, unsigned int len, __u8 prio = 0 )
		:prio(prio), data(data), len(len)
	{

	}
	bool operator < ( const struct queueData &a ) const
	{
		return prio < a.prio;
	}
};

enum data_source
{
	TUNER_A, TUNER_B, TUNER_C, TUNER_D, CI_A, CI_B, CI_C, CI_D
};

typedef std::pair<std::string, uint32_t> providerPair;
typedef std::set<providerPair> providerSet;
typedef std::set<uint16_t> caidSet;
typedef std::set<eServiceReference> serviceSet;

class eDVBCISlot: public iObject, public sigc::trackable
{
	friend class eDVBCIInterfaces;
	DECLARE_REF(eDVBCISlot);
	int slotid;
	int fd;
	ePtr<eSocketNotifier> notifier;
	int state;
	std::map<uint16_t, uint8_t> running_services;
	eDVBCIApplicationManagerSession *application_manager;
	eDVBCICAManagerSession *ca_manager;
	eDVBCIMMISession *mmi_session;
	std::priority_queue<queueData> sendqueue;
	caidSet possible_caids;
	serviceSet possible_services;
	providerSet possible_providers;
	int use_count;
	eDVBCISlot *linked_next; // needed for linked CI handling
	data_source current_source;
	int current_tuner;
	bool user_mapped;
	void data(int);
	bool plugged;
	/* slot pornit/oprit si intarzierea pornirii (din sursele GPL enigma2 OE-Alliance, depozitul enigma2 al stratului,
	   commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/dvb_ci/dvbci.cpp: openDevice, closeDevice, setEnabled) */
	eMainloop *m_context;
	ePtr<eTimer> startup_timeout;
	void openDevice();
	void closeDevice();
	/* CI+ (din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/dvb_ci/dvbci.h):
	   managerul de continut, parametrii descifrarii (demux, program, pid-uri, tuner), optiunile din setari si rutarea
	   fluxului prin modul in timpul autentificarii */
	eDVBCICcSession *cc_manager;
	int16_t m_ca_demux_id;
	uint16_t m_program_number;
	int m_video_pid;
	int m_audio_pid;
	int m_audio_number;
	int m_audio_pids[16];
	int m_tunernum;
	bool m_operator_profiles_disabled;
	int m_alt_ca_handling;
	bool m_ciPlusRoutingDone;
	bool m_ciplus_keys;  // cheile CI+ primite de la modul (dupa autentificare)
	int m_ciplus_routing_tunernum;
	std::string m_ciplus_routing_input;
	std::string m_ciplus_routing_ci_input;
	void readCIPlusSettings();
public:
	enum {stateRemoved, stateInserted, stateInvalid, stateResetted, stateDisabled};
	eDVBCISlot(eMainloop *context, int nr);
	~eDVBCISlot();
	
	int send(const unsigned char *data, size_t len);

	void setAppManager( eDVBCIApplicationManagerSession *session );
	void setMMIManager( eDVBCIMMISession *session );
	void setCAManager( eDVBCICAManagerSession *session );
	void setCCManager( eDVBCICcSession *session );
	eDVBCICcSession *getCCManager() { return cc_manager; }
	int getFd() { return fd; }
	int16_t getCADemuxID() { return m_ca_demux_id; }
	int getTunerNum() { return m_tunernum; }
	int getUseCount() { return use_count; }
	int getProgramNumber() { return (int)m_program_number; }
	int getVideoPid() { return m_video_pid; }
	int getAudioPid() { return m_audio_pid; }
	int getAudioNumber() { return m_audio_number; }
	int *getAudioPids() { return m_audio_pids; }
	int getDescramblingOptions() { return m_alt_ca_handling; }
	bool getIsOperatorProfileDisabled() { return m_operator_profiles_disabled; }
	bool ciplusRoutingDone() { return m_ciPlusRoutingDone; }
	void setCIPlusRoutingDone() { m_ciPlusRoutingDone = true; }
	int getCIPlusRoutingTunerNum() { return m_ciplus_routing_tunernum; }
	const std::string &getCIPlusRoutingInput() { return m_ciplus_routing_input; }
	const std::string &getCIPlusRoutingCIInput() { return m_ciplus_routing_ci_input; }
	void setCIPlusRoutingParameter(int tunernum, const std::string &input, const std::string &ci_input);
	int setCaParameter(eDVBServicePMTHandler *pmthandler);

	eDVBCIApplicationManagerSession *getAppManager() { return application_manager; }
	eDVBCIMMISession *getMMIManager() { return mmi_session; }
	eDVBCICAManagerSession *getCAManager() { return ca_manager; }

	int getState() { return state; }
	int getSlotID();
	int reset();
	int startMMI();
	int stopMMI();
	int answerText(int answer);
	int answerEnq(char *value);
	int cancelEnq();
	int getMMIState();
	int sendCAPMT(eDVBServicePMTHandler *ptr, const std::vector<uint16_t> &caids=std::vector<uint16_t>());
	void removeService(uint16_t program_number=0xFFFF);
	int getNumOfServices() { return running_services.size(); }
	int setSource(data_source source);
	int setClockRate(int);
	int setEnabled(bool enabled);
};

struct CIPmtHandler
{
	eDVBServicePMTHandler *pmthandler;
	eDVBCISlot *cislot;
	CIPmtHandler()
		:pmthandler(NULL), cislot(NULL)
	{}
	CIPmtHandler( const CIPmtHandler &x )
		:pmthandler(x.pmthandler), cislot(x.cislot)
	{}
	CIPmtHandler( eDVBServicePMTHandler *ptr )
		:pmthandler(ptr), cislot(NULL)
	{}
	bool operator==(const CIPmtHandler &x) const { return x.pmthandler == pmthandler; }
};

typedef std::list<CIPmtHandler> PMTHandlerList;

#endif // SWIG

class eDVBCIInterfaces
{
	DECLARE_REF(eDVBCIInterfaces);
	static eDVBCIInterfaces *instance;
	eSmartPtrList<eDVBCISlot> m_slots;
	eDVBCISlot *getSlot(int slotid);
	PMTHandlerList m_pmt_handlers; 
#ifndef SWIG
public:
#endif
	eDVBCIInterfaces();
	~eDVBCIInterfaces();

	void addPMTHandler(eDVBServicePMTHandler *pmthandler);
	void removePMTHandler(eDVBServicePMTHandler *pmthandler);
	void recheckPMTHandlers();
	void gotPMT(eDVBServicePMTHandler *pmthandler);
		/* a CI slot descrambles the service of this handler: SoftCSA (lib/dvb/csasession.h) leaves it to the module */
	bool isHandlerAssigned(eDVBServicePMTHandler *pmthandler);
	void ciRemoved(eDVBCISlot *slot);
	int getSlotState(int slot);

	int reset(int slot);
	int initialize(int slot);
	int startMMI(int slot);
	int stopMMI(int slot);
	int answerText(int slot, int answer);
	int answerEnq(int slot, char *value);
	int cancelEnq(int slot);
	int getMMIState(int slot);
	int sendCAPMT(int slot);
	int setInputSource(int tunerno, data_source source);
	int setCIClockRate(int slot, int rate);
	int setCIEnabled(int slot, bool enabled);
	/* CI+ (din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4) */
	void setCIPlusRouting(int slotid);
	void revertCIPlusRouting(int slotid);
	std::string getLanguage();
	int getCIPlusState(int slotid);
#ifdef SWIG
public:
#endif
	static eDVBCIInterfaces *getInstance();
	int getNumOfSlots() { return m_slots.size(); }
	PyObject *getDescrambleRules(int slotid);
	RESULT setDescrambleRules(int slotid, SWIG_PYOBJECT(ePyObject) );
	PyObject *readCICaIds(int slotid);
};

#endif
