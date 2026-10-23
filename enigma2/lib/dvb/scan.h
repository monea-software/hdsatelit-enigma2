/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_dvb_scan_h
#define __lib_dvb_scan_h

#include <dvbsi++/service_description_section.h>
#include <dvbsi++/network_information_section.h>
#include <dvbsi++/bouquet_association_section.h>
#include <dvbsi++/program_association_section.h>
#include <dvbsi++/program_map_section.h>

#include <set>

#include <lib/dvb/idemux.h>
#include <lib/dvb/esection.h>
#include <lib/dvb/db.h>
#include <lib/dvb/hdsretea.h>

struct service
{
	service(unsigned short pmtPid)
		:pmtPid(pmtPid), serviceType(0xFF), scrambled(false)
	{
	}
	unsigned short pmtPid;
	unsigned char serviceType;
	bool scrambled;
};

class eDVBScan: public sigc::trackable, public iObject
{
	DECLARE_REF(eDVBScan);
		/* chid helper functions: */
		
		/* heuristically determine if onid/tsid is valid */
	int isValidONIDTSID(int orbital_position, eOriginalNetworkID onid, eTransportStreamID tsid);
		/* build dvb namespace */
	eDVBNamespace buildNamespace(eOriginalNetworkID onid, eTransportStreamID tsid, unsigned long hash);
	
		/* scan resources */	
	eUsePtr<iDVBChannel> m_channel;
	ePtr<iDVBDemux> m_demux;
	
		/* infrastructure */
	void stateChange(iDVBChannel *);
	ePtr<eConnection> m_stateChanged_connection;

		/* state handling */	
	RESULT nextChannel();
	
	RESULT startFilter();	
	enum { readyPAT=1, readySDT=2, readyNIT=4, readyBAT=8,
	       validPAT=16, validSDT=32, validNIT=64, validBAT=128};

		/* scan state variables */
	int m_channel_state;
	int m_ready, m_ready_all;

	std::map<eDVBChannelID, ePtr<iDVBFrontendParameters> > m_new_channels;
	std::map<eDVBChannelID, ePyObjectWrapper> m_tuner_data; // data read from tuner for every new channel

	std::map<eServiceReferenceDVB, ePtr<eDVBService> > m_new_services;
	std::map<eServiceReferenceDVB, ePtr<eDVBService> >::iterator m_last_service;
		/* HDSatelit: the services of m_new_services that came from an SDT (the others were found only in PAT/PMT) */
	std::set<eServiceReferenceDVB> m_sdt_services;
		/* HDSatelit: what the NITs read in this scan say (network id and name, announced transponders, logical channel
		   numbers), for the result of the last scan in the web interface; nothing of it goes to the channel list.
		   NIT-ul se citeste la cautarea in retea si, numai pentru informatie, la cablu pe o frecventa
		   (hdsNitInformativ, lib/dvb/hdsretea.h). */
	hdsretea::Colector m_networks;
	std::map<iDVBFrontendParameters*, unsigned int> m_network_on_tp; /* network id of the NIT read on a tuned transponder */
	std::map<iDVBFrontendParameters*, eDVBChannelID> m_nit_chid; /* tsid/onid announced for a transponder added from a NIT */
	std::list<ePtr<iDVBFrontendParameters> > m_nit_chid_refs; /* keeps those transponders alive: the keys stay unique */
	void hdsNoteNIT();
	void hdsNoteFromNIT(const eDVBChannelID &chid, iDVBFrontendParameters *feparm);

	std::map<unsigned short, service> m_pmts_to_read;
	std::map<unsigned short, service>::iterator m_pmt_in_progress;
	bool m_pmt_running;
	bool m_abort_current_pmt;

	std::list<ePtr<iDVBFrontendParameters> > m_ch_toScan, m_ch_scanned, m_ch_unavailable;
	ePtr<iDVBFrontendParameters> m_ch_current;
	eDVBChannelID m_chid_current;
	eTransportStreamID m_pat_tsid;

	ePtr<eTable<ServiceDescriptionSection> > m_SDT;
	ePtr<eTable<NetworkInformationSection> > m_NIT;
	ePtr<eTable<BouquetAssociationSection> > m_BAT;
	ePtr<eTable<ProgramAssociationSection> > m_PAT;
	ePtr<eTable<ProgramMapSection> > m_PMT;

	void SDTready(int err);
	void NITready(int err);
	void BATready(int err);
	void PATready(int err);
	void PMTready(int err);

	void addKnownGoodChannel(const eDVBChannelID &chid, iDVBFrontendParameters *feparm);
	void addChannelToScan(const eDVBChannelID &chid, iDVBFrontendParameters *feparm);

	int sameChannel(iDVBFrontendParameters *ch1, iDVBFrontendParameters *ch2, bool exact=false) const;

	void channelDone();
	
	sigc::signal<void(int)> m_event;
	RESULT processSDT(eDVBNamespace dvbnamespace, const ServiceDescriptionSection &sdt);
	
	int m_flags;
	int m_num_new_services; /* HDSatelit: services not in the channel list before this scan, -1 until insertInto */
	bool m_usePAT;
	bool m_scan_debug;
	ePyObject m_additional_tsid_onid_check_func;
	bool m_show_add_tsid_onid_check_failed_msg;
public:
	eDVBScan(iDVBChannel *channel, bool usePAT=true, bool debug=true );
	~eDVBScan();

	enum {
		scanNetworkSearch = 1, scanSearchBAT = 2,
		scanRemoveServices = 4, scanDontRemoveFeeds = 8,
		scanDontRemoveUnscanned = 16,
		clearToScanOnFirstNIT = 32, scanOnlyFree = 64,
		/* HDSatelit: NIT-ul se asteapta si se pastreaza (reteaua, numerele canalelor), dar frecventele anuntate
		   nu intra in scanare; pus numai la cablu pe o frecventa (Screens/ScanerCablu.py) */
		hdsNitInformativ = 128 };

	void start(const eSmartPtrList<iDVBFrontendParameters> &known_transponders, int flags);

	enum { evtUpdate, evtNewService, evtFinish, evtFail };
	RESULT connectEvent(const sigc::slot<void(int)> &event, ePtr<eConnection> &connection);
	void insertInto(iDVBChannelList *db, bool dontRemoveNewFlags=false);
	
	void getStats(int &transponders_done, int &transponders_total, int &services);
		/* HDSatelit: for the scan screen (time left, final summary) */
	int getNumUnavailable() const { return (int)m_ch_unavailable.size(); }
	int getLastServiceType();
	int getNumNewServices() const { return m_num_new_services; }
	void getLastServiceName(std::string &name);
		/* HDSatelit: read only, for the result of the last scan in the web interface. Every service read in this
		   scan, old and new: [(sid, namespace, tsid, onid, service type, name, provider, [caid], from SDT)].
		   Every transponder tried: [(system, orbital position, frequency, polarisation, symbol rate, tuned,
		   has a channel id, namespace, tsid, onid, tsid from NIT, onid from NIT, network id of the NIT read on it,
		   cable modulation)], -1 where unknown. Every network whose NIT was read: [(network id, name,
		   [private data specifiers], [(tsid, onid, system, kHz, ksymb/s, modulation, fec, orbital position,
		   polarisation, DVB-S2)], [(tsid, onid, sid, logical channel number, visible, tag, private data specifier,
		   channel list)], [(tsid, onid, tag, private data specifier, bytes)], truncated)]. Nothing is written to the
		   channel list. */
	PyObject *getFoundServices();
	PyObject *getScannedTransponders();
	PyObject *getNetworks();
	RESULT getFrontend(ePtr<iDVBFrontend> &);
	RESULT getCurrentTransponder(ePtr<iDVBFrontendParameters> &);
	eDVBChannelID getCurrentChannelID() { return m_chid_current; }
};

#endif
