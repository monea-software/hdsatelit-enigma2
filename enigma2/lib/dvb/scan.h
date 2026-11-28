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
#include <lib/dvb/hdsjurnaltuner.h>
#include <lib/dvb/hdsvct.h>

class SatelliteDeliverySystemDescriptor;

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
	       validPAT=16, validSDT=32, validNIT=64, validBAT=128,
	       /* HDSatelit (0.8.0): VCT-ul ATSC; in m_ready_all numai dupa o sectiune PSIP buna (lib/dvb/hdsvct.h) */
	       readyVCT=256, validVCT=512};

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
	/* HDSatelit (0.8.0): descriptorul de satelit al unei intrari din NIT (actual sau al altei retele) */
	void hdsSatelitDinNit(SatelliteDeliverySystemDescriptor &d, eOriginalNetworkID onid, eTransportStreamID tsid,
		bool s2_gasit, int s2_isi, int s2_gold, bool alta_retea);
	/* HDSatelit (0.8.0, lib/dvb/hdsvct.h): numele canalelor din VCT-ul ATSC (TVCT/CVCT, PID 0x1FFB), numai la cautarea pornita
	   cu start(), nu la actualizarea listei din fundal de la zap. Cititorul brut porneste odata cu PAT-ul; VCT-ul se asteapta
	   numai dupa o sectiune PSIP buna, cel mult hdsvct::RAGAZ_MS de la ea. */
	bool m_hds_cautare;
	ePtr<iDVBSectionReader> m_hds_psip;
	long long m_hds_psip_t0; /* cand a pornit cititorul (hdsjurnal::monotonMs), pentru ora sectiunilor */
	ePtr<eConnection> m_hds_psip_conn;
	ePtr<eTimer> m_hds_vct_plafon;
	hdsvct::Colector m_hds_vct;
	/* serviciile numite din VCT -> transponderul lor n-a avut SDT la aceasta cautare (hdsvct::vctInlocuiesteInLista) */
	std::map<eServiceReferenceDVB, bool> m_hds_nume_vct;
	bool m_hds_tp_cu_sdt; /* transponderul de acum a dat SDT-ul (processSDT) */
	void hdsPornestePsip();
	void hdsOpresteVct();
	void hdsSectiunePsip(const __u8 *data);
	void hdsVctPlafon();
	const hdsvct::Canal *hdsCanalVct(int sid);
	void hdsNumeleDinVct();
	/* HDSatelit (0.8.0): NIT-ul altor retele (0x41) la cautarea in retea pe satelit: cules fara asteptare (cititor brut,
	   nu intra in m_ready_all), prelucrat la sfarsitul transponderului cu regulile de pozitie ale NIT-ului actual, fara
	   indreptarea est/vest (hdsscanreguli::pozitieDinNit) */
	ePtr<iDVBSectionReader> m_hds_nit_alt;
	ePtr<eConnection> m_hds_nit_alt_conn;
	std::map<unsigned int, std::vector<__u8> > m_hds_nit_alt_sectiuni; /* (network_id << 8 | section_number) -> sectiunea */
	void hdsPornesteNitAlt();
	void hdsOpresteNitAlt();
	void hdsSectiuneNitAlt(const __u8 *data);
	void hdsNitAltaRetea();
	bool hdsStiutPentruNitAlt(iDVBFrontendParameters *feparm);
	/* AMRZ (24.11.2026): ce aduce NIT other se tine deoparte si se pune in coada abia cand lista si NIT-ul actual s-au terminat
	   (nextChannel), ca partea lor de cautare sa ramana exact ca inainte */
	std::list<std::pair<eDVBChannelID, ePtr<iDVBFrontendParameters> > > m_hds_nit_alt_amanate;
	/* NIT9 (24.11.2026): intrarile venite numai din NIT other (tinute vii aici, ca adresele sa nu se refoloseasca) si
	   descriptorul propriu al fiecarui transponder din NIT-urile actuale citite ((ONID << 16 | TSID, pozitia) -> parametrii);
	   la insertInto un transponder prins din NIT other ia descriptorul propriu sau pastreaza lista (hdsParametriNitAlt) */
	std::list<ePtr<iDVBFrontendParameters> > m_hds_din_nit_alt;
	std::map<std::pair<unsigned int, int>, eDVBFrontendParametersSatellite> m_hds_nit_propriu;
	void hdsParametriNitAlt(iDVBChannelList *db);
	/* HDSatelit (0.8.0, lib/dvb/hdsscanreguli.h): acelasi TSID si ONID pe doua transpondere prinse in aceeasi cautare
	   (namespace-ul cu frecventa numai pentru al doilea) si, la sfarsit, ns_orb pentru cel pe care lista il avea deja */
	eDVBNamespace hdsNamespaceLaColiziune(eDVBNamespace ns, eOriginalNetworkID onid, eTransportStreamID tsid,
		unsigned long hash);
	std::map<eDVBChannelID, std::list<eDVBChannelID> > m_hds_coliziuni; /* (ns_orb, tsid, onid) -> ceilalti, pe ns_frecventa */
	std::map<eDVBChannelID, std::string> m_hds_continut; /* serviciile din SDT ale fiecarui transponder prins (SID si nume) */
	std::string hdsContinutSdt();
	void hdsColiziuniLaSfarsit(iDVBChannelList *db);
	void hdsMutaCanal(const eDVBChannelID &din, const eDVBChannelID &spre);
	sigc::signal<void(int)> m_event;
	RESULT processSDT(eDVBNamespace dvbnamespace, const ServiceDescriptionSection &sdt);
	
	int m_flags;
	int m_num_new_services; /* HDSatelit: services not in the channel list before this scan, -1 until insertInto */
	hdsjscan::Stare m_hds_jurnal; /* HDSatelit: jurnalul scanarii (lib/dvb/hdsjurnaltuner.h) */
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
