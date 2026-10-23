/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_dvb_dvbmid_h
#define __lib_dvb_dvbmid_h

#ifndef SWIG
#include <map>
#include <lib/base/buffer.h>
#include <lib/dvb/idvb.h>
#include <lib/dvb/dvb.h>
#include <lib/dvb/idemux.h>
#include <lib/dvb/esection.h>
#include <lib/dvb/hdsait.h>
#include <lib/python/python.h>
#include <dvbsi++/program_map_section.h>
#include <dvbsi++/program_association_section.h>

#include <sys/socket.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>

class eDVBCAService;
class eDVBScan;

struct channel_data: public sigc::trackable
{
	ePtr<eDVBChannel> m_channel;
	ePtr<eConnection> m_stateChangedConn;
	int m_prevChannelState;
	int m_dataDemux;
};

// TODO .. put all static stuff into a 'eDVBCAServiceHandler class'

typedef std::map<eServiceReferenceDVB, eDVBCAService*> CAServiceMap;
typedef std::map<iDVBChannel*, channel_data*> ChannelMap;

class eDVBCAService: public sigc::trackable
{
	eIOBuffer m_buffer;
	ePtr<eSocketNotifier> m_sn;
	eServiceReferenceDVB m_service;
	uint8_t m_used_demux[32];
	unsigned int m_prev_build_hash;

	int m_sock, m_clilen; 
	struct sockaddr_un m_servaddr;
	unsigned int m_sendstate;
	unsigned char m_capmt[2048];
	ePtr<eTimer> m_retryTimer;
	void sendCAPMT();
	void Connect();
	void socketCB(int what);

	static void DVBChannelAdded(eDVBChannel*);
	static void DVBChannelStateChanged(iDVBChannel*);
	static CAServiceMap exist;
	static ChannelMap exist_channels;
	static ePtr<eConnection> m_chanAddedConn;
	static channel_data *getChannelData(eDVBChannelID &chid);

	eDVBCAService();
	~eDVBCAService();
public:
	static void registerChannelCallback(eDVBResourceManager *res_mgr);
	static RESULT register_service( const eServiceReferenceDVB &ref, int demux_nums[2], eDVBCAService *&caservice );
	static RESULT unregister_service( const eServiceReferenceDVB &ref, int demux_nums[2], eTable<ProgramMapSection> *ptr );
	void buildCAPMT(eTable<ProgramMapSection> *ptr);
};

#endif

class eDVBServicePMTHandler: public sigc::trackable
{
#ifndef SWIG
	friend class eDVBCAService;
	eServiceReferenceDVB m_reference;
	ePtr<eDVBService> m_service;

	int m_last_channel_state;
	eDVBCAService *m_ca_servicePtr;
	ePtr<eDVBScan> m_dvb_scan; // for sdt scan

	eAUTable<eTable<ProgramMapSection> > m_PMT;
	eAUTable<eTable<ProgramAssociationSection> > m_PAT;

	eUsePtr<iDVBChannel> m_channel;
	eUsePtr<iDVBPVRChannel> m_pvr_channel;
	ePtr<eDVBResourceManager> m_resourceManager;
	ePtr<iDVBDemux> m_demux, m_pvr_demux_tmp;

	void channelStateChanged(iDVBChannel *);
	ePtr<eConnection> m_channelStateChanged_connection;
	void channelEvent(iDVBChannel *, int event);
	ePtr<eConnection> m_channelEvent_connection;
	void SDTScanEvent(int);
	ePtr<eConnection> m_scan_event_connection;

	void PMTready(int error);
	void PATready(int error);
	
	int m_pmt_pid;
	
	int m_use_decode_demux;
	uint8_t m_decode_demux_num;
	ePtr<eTimer> m_no_pat_entry_delay;

		/* AIT-ul HbbTV (lib/dvb/hdsait.h), numai cand e cerut (eDVBServicePlay, pe canalul redat): PID-ul vine din
		   PMT, tabela se urmareste cat ruleaza canalul (o versiune noua se citeste singura, eAUTable), aplicatiile
		   se tin aici pentru getHbbtvInfo */
	bool m_ait_wanted;
	int m_ait_pid;          /* PID-ul pe care se citeste: -1 nimic pornit, 0 PMT-ul nu are AIT HbbTV */
	int m_ait_version;      /* -1 cat nu s-a citit */
	std::vector<hdsait::Aplicatie> m_ait_apps;
	ePtr<eTimer> m_ait_retry, m_ait_signal;
	eAUTable<eTable<eHdsAitSection> > m_AIT;
	void updateAIT();
	void AITready(int error);
	void AITretry();
	void AITsignal();

		/* HDSatelit: the channel uses of this handler give way to a zap (lib/dvb/hdscedare.h). While they are counted,
		   m_yielding_channel and m_yielding_uses say on which channel and how many: free() and every tune take them
		   back before the channel goes */
	bool m_yields_to_zap;
	eDVBChannel *m_yielding_channel;
	int m_yielding_uses;
	void updateYieldingUses();
	void clearYieldingUses();

		/* CA PMT-ul canalului viu din fereastra principala trimis din memorie: ultimul PMT vazut al unui serviciu
		   criptat se tine minte (numai in memorie, pmt.cpp); la urmatorul zap pe el, cand decodorul porneste din
		   PID-urile tinute minte, CA PMT-ul pleaca imediat spre programul de decriptare, fara sa astepte PAT si PMT.
		   Cand vine PMT-ul adevarat, buildCAPMT nu retrimite acelasi CA PMT (PID-ul PMT, masca, versiunea) si trimite
		   o actualizare daca s-a schimbat. m_ca_din_memorie: permis (setCaDinMemorie, din eDVBServicePlay::start);
		   m_ca_din_memorie_trimis: a plecat din memorie, deci la primul PMT adevarat CI-ul se reverifica, ca la prima
		   inscriere */
	bool m_ca_din_memorie;
	bool m_ca_din_memorie_trimis;
	void trimiteCaDinMemorie();
	void tinePmtMinte(eTable<ProgramMapSection> *ptr);

		/* inregistrarea "decodeaza mai tarziu" (setDecodareMaiTarziu, din eDVBServiceRecord): serviciul nu se inscrie la
		   modulul de acces conditionat si nici la modulele CI, deci nimeni nu trimite chei pentru PID-urile lui si
		   pachetele ajung pe disc criptate, neschimbate */
	bool m_decodare_mai_tarziu;
public:
	eDVBServicePMTHandler();
	~eDVBServicePMTHandler();
#endif

#ifdef SWIG
private:
	eDVBServicePMTHandler();
public:
#endif

	enum
	{
		eventNoResources,  // a requested resource couldn't be allocated
		eventTuneFailed,   // tune failed
		eventNoPAT,        // no pat could be received (timeout)
		eventNoPATEntry,   // no pat entry for the corresponding SID could be found
		eventNoPMT,        // no pmt could be received (timeout)
		eventNewProgramInfo, // we just received a PMT
		eventTuned,        // a channel was sucessfully (re-)tuned in, you may start additional filters now
		
		eventPreStart,     // before start filepush thread
		eventSOF,          // seek pre start
		eventEOF,          // a file playback did end
		
		eventMisconfiguration, // a channel was not found in any list, or no frontend was found which could provide this channel

		eventHBBTVInfo,    // AIT-ul HbbTV s-a citit, s-a schimbat sau a disparut (getHbbtvInfo); nu e o stare a acordarii
	};
#ifndef SWIG
	sigc::signal<void(int)> serviceEvent;

	struct videoStream
	{
		int pid;
		int component_tag;
		/* numerotarea driverului: valoarea = VIDEO_SET_STREAMTYPE trimis driverului; egala cu eDVBVideo din
		   decoder.h (servicedvb.cpp trece tipul direct in setVideoPID si il scrie in cVTYPE, c:05 din lamedb) */
		enum { vtMPEG2, vtMPEG4_H264, vtVC1 = 3, vtMPEG4_Part2, vtVC1_SM, vtMPEG1, vtH265_HEVC,
			/* AVS / AVS+ (stream_type 0x42): 16 e tipul AVS al decodorului HiSilicon (tabela din showiframe) */
			vtCAVS = 16 };
		int type;
	};
	
	struct audioStream
	{
		int pid,
		    rdsPid; // hack for some radio services which transmit radiotext on different pid (i.e. harmony fm, HIT RADIO FFH, ...)
		enum { atMPEG, atAC3, atDTS, atAAC, atAACHE, atLPCM, atDTSHD, atDDP }; /* egala cu eDVBAudio din decoder.h */
		int type; // mpeg2, ac3, dts, ...
		
		int component_tag;
		std::string language_code; /* iso-639, if available. */
	};

	struct subtitleStream
	{
		int pid;
		int subtitling_type;  	/*  see ETSI EN 300 468 table 26 component_type
									when stream_content is 0x03
									0x10..0x13, 0x20..0x23 is used for dvb subtitles
									0x01 is used for teletext subtitles */
		union
		{
			int composition_page_id;  // used for dvb subtitles
			int teletext_page_number;  // used for teletext subtitles
		};
		union
		{
			int ancillary_page_id;  // used for dvb subtitles
			int teletext_magazine_number;  // used for teletext subtitles
		};
		std::string language_code;
		bool operator<(const subtitleStream &s) const
		{
			if (pid != s.pid)
				return pid < s.pid;
			if (teletext_page_number != s.teletext_page_number)
				return teletext_page_number < s.teletext_page_number;
			return teletext_magazine_number < s.teletext_magazine_number;
		}
	};

	struct program
	{
		struct capid_pair
		{
			uint16_t caid;
			int capid;
			bool operator< (const struct capid_pair &t) const { return t.caid < caid; }
		};
		std::vector<videoStream> videoStreams;
		std::vector<audioStream> audioStreams;
		int defaultAudioStream;
		std::vector<subtitleStream> subtitleStreams;
		std::list<capid_pair> caids;
		int pcrPid;
		int pmtPid;
		int textPid;
		int aitPid;   /* AIT HbbTV din PMT: -1 PMT necitit (program din cache), 0 fara AIT, altfel PID-ul */
		/* pistele din PMT pe care nucleul nu le recunoaste (nici video, nici sunet, nici subtitrare sau teletext):
		   PID-ul, stream_type si format_identifier din registration_descriptor (0 fara el). Nu ajung niciodata la
		   decodor; Python le citeste prin iServiceInformation::sPisteNecunoscute, pentru mesajul cu numele formatului
		   (AV1, H.266 VVC, AVS2, AVS3...). Cel mult MAX_PISTE_NECUNOSCUTE. */
		struct pistaNecunoscuta
		{
			int pid;
			int stream_type;
			uint32_t inregistrare;
		};
		enum { MAX_PISTE_NECUNOSCUTE = 8 };
		std::vector<pistaNecunoscuta> pisteNecunoscute;
		bool isCrypted() { return !caids.empty(); }
		PyObject *createPythonObject();
	};

	int getProgramInfo(program &program);
	int getDataDemux(ePtr<iDVBDemux> &demux);
	int getDecodeDemux(ePtr<iDVBDemux> &demux);
	PyObject *getCaIds(bool pair=false); // caid / ecmpid pair
	
	int getPVRChannel(ePtr<iDVBPVRChannel> &pvr_channel);
	int getServiceReference(eServiceReferenceDVB &service) { service = m_reference; return 0; }
	int getService(ePtr<eDVBService> &service) { service = m_service; return 0; }
	int getPMT(ePtr<eTable<ProgramMapSection> > &ptr) { return m_PMT.getCurrent(ptr); }
	int getChannel(eUsePtr<iDVBChannel> &channel);
	void resetCachedProgram() { m_have_cached_program = false; }
		/* citirea AIT-ului HbbTV (oprita din oficiu); se cere inainte de tune / tuneExt */
	void setAITReading(bool on) { m_ait_wanted = on; }
		/* CA PMT-ul din memorie (vezi m_ca_din_memorie); oprit din oficiu, se cere inainte de tune / tuneExt */
	void setCaDinMemorie(bool on) { m_ca_din_memorie = on; }
		/* fara inscriere la modulul de acces si la CI (vezi m_decodare_mai_tarziu); se cere inainte de tune / tuneExt */
	void setDecodareMaiTarziu(bool on) { m_decodare_mai_tarziu = on; }
	bool decodareMaiTarziu() const { return m_decodare_mai_tarziu; }
		/* the channel uses of this handler give way to a zap: a network stream that stops when the live service needs
		   the tuner (lib/dvb/hdscedare.h); before or after tune */
	void setYieldsToZap(bool yields);
		/* {"pid", "versiune", "aplicatii": [...]} pentru Python (iServiceInformation::sHBBTVAit), textele ca octeti */
	PyObject *getHbbtvInfo();
	void sendEventNoPatEntry();

	/* deprecated interface */
	int tune(eServiceReferenceDVB &ref, int use_decode_demux, eCueSheet *sg=0, bool simulate=false, eDVBService *service = 0);

	/* new interface */
	int tuneExt(eServiceReferenceDVB &ref, int use_decode_demux, ePtr<iTsSource> &, const char *streaminfo_file, eCueSheet *sg=0, bool simulate=false, eDVBService *service = 0);

	void free();
private:
	bool m_have_cached_program;
	program m_cached_program;
#endif
};

#endif
