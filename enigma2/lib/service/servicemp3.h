/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __servicemp3_h
#define __servicemp3_h

#include <lib/base/message.h>
#include <lib/service/iservice.h>
#include <lib/dvb/pmt.h>
#include <lib/dvb/subtitle.h>
#include <lib/dvb/teletext.h>
#include <gst/gst.h>
/* for subtitles */
#include <lib/gui/esubtitle.h>
#include <lib/service/hdssubimagini.h>

#include <memory>
#include <set>
#include <utility>

class eStaticServiceMP3Info;

class eSubtitleWidget;

class eServiceFactoryMP3: public iServiceHandler
{
	DECLARE_REF(eServiceFactoryMP3);
public:
	eServiceFactoryMP3();
	virtual ~eServiceFactoryMP3();
	enum { id = 0x1001 };

		// iServiceHandler
	RESULT play(const eServiceReference &, ePtr<iPlayableService> &ptr);
	RESULT record(const eServiceReference &, ePtr<iRecordableService> &ptr);
	RESULT list(const eServiceReference &, ePtr<iListableService> &ptr);
	RESULT info(const eServiceReference &, ePtr<iStaticServiceInformation> &ptr);
	RESULT offlineOperations(const eServiceReference &, ePtr<iServiceOfflineOperations> &ptr);
private:
	ePtr<eStaticServiceMP3Info> m_service_info;
};

class eStaticServiceMP3Info: public iStaticServiceInformation
{
	DECLARE_REF(eStaticServiceMP3Info);
	friend class eServiceFactoryMP3;
	eStaticServiceMP3Info();
public:
	RESULT getName(const eServiceReference &ref, std::string &name);
	int getLength(const eServiceReference &ref);
	int getInfo(const eServiceReference &ref, int w);
};

typedef struct _GstElement GstElement;

typedef enum { atUnknown, atMPEG, atMP3, atAC3, atDTS, atAAC, atPCM, atOGG, atFLAC } audiotype_t;
/* The values are the third field of the subtitle tuples seen by Python (AudioSelection, HdsCommon, the web pages):
   new kinds are only ever appended, so the old numbers keep their meaning. stPlainText = text from the container
   (MKV, MP4, AVI); the values from stWebVTT on name the format of a subtitle file next to the film (read by
   Components/HdsSubtitrariFilm.py; stSRT, stSSA, stASS, stVOB and stPGS are used for files as well). */
typedef enum { stUnknown, stPlainText, stSSA, stASS, stSRT, stVOB, stPGS,
	stWebVTT, stMicroDVD, stSubViewer, stMPL2, stTMPlayer, stSAMI } subtype_t;
typedef enum { ctNone, ctMPEGTS, ctMPEGPS, ctMKV, ctAVI, ctMP4, ctVCD, ctCDA } containertype_t;

class eServiceMP3: public iPlayableService, public iPauseableService,
	public iServiceInformation, public iSeekableService, public iAudioTrackSelection, public iAudioChannelSelection, 
	public iSubtitleOutput, public iStreamedService, public iAudioDelay, public iCueSheet, public sigc::trackable
{
	DECLARE_REF(eServiceMP3);
public:
	virtual ~eServiceMP3();
	/* defined in servicemp3.cpp: the gate of the GStreamer callbacks and the thread of the film */
	struct Poarta;
	struct FirFilm;

		// iPlayableService
	RESULT connectEvent(const sigc::slot<void(iPlayableService*, int)> &event, ePtr<eConnection> &connection);
	RESULT start();
	RESULT stop();
	RESULT setTarget(int target);
	
	RESULT pause(ePtr<iPauseableService> &ptr);
	RESULT setSlowMotion(int ratio);
	RESULT setFastForward(int ratio);

	RESULT seek(ePtr<iSeekableService> &ptr);
	RESULT audioTracks(ePtr<iAudioTrackSelection> &ptr);
	RESULT audioChannel(ePtr<iAudioChannelSelection> &ptr);
	RESULT subtitle(ePtr<iSubtitleOutput> &ptr);
	RESULT audioDelay(ePtr<iAudioDelay> &ptr);

		// not implemented (yet)
	RESULT frontendInfo(ePtr<iFrontendInformation> &ptr) { ptr = 0; return -1; }
	RESULT subServices(ePtr<iSubserviceList> &ptr) { ptr = 0; return -1; }
	RESULT timeshift(ePtr<iTimeshiftService> &ptr) { ptr = 0; return -1; }
	RESULT cueSheet(ePtr<iCueSheet> &ptr);

	RESULT rdsDecoder(ePtr<iRdsDecoder> &ptr) { ptr = 0; return -1; }
	RESULT keys(ePtr<iServiceKeys> &ptr) { ptr = 0; return -1; }
	RESULT stream(ePtr<iStreamableService> &ptr) { ptr = 0; return -1; }

		// iPausableService
	RESULT pause();
	RESULT unpause();
	
	RESULT info(ePtr<iServiceInformation>&);
	
		// iSeekableService
	RESULT getLength(pts_t &SWIG_OUTPUT);
	RESULT seekTo(pts_t to);
	RESULT seekRelative(int direction, pts_t to);
	RESULT getPlayPosition(pts_t &SWIG_OUTPUT);
	RESULT setTrickmode(int trick);
	RESULT isCurrentlySeekable();

		// iServiceInformation
	RESULT getName(std::string &name);
	int getInfo(int w);
	std::string getInfoString(int w);
	PyObject *getInfoObject(int w);

		// iAudioTrackSelection	
	int getNumberOfTracks();
	RESULT selectTrack(unsigned int i);
	RESULT getTrackInfo(struct iAudioTrackInfo &, unsigned int n);
	int getCurrentTrack();

		// iAudioChannelSelection	
	int getCurrentChannel();
	RESULT selectChannel(int i);

		// iSubtitleOutput
	RESULT enableSubtitles(eWidget *parent, SWIG_PYOBJECT(ePyObject) entry);
	RESULT disableSubtitles(eWidget *parent);
	PyObject *getSubtitleList();
	PyObject *getCachedSubtitle();
	RESULT setExternalSubtitles(SWIG_PYOBJECT(ePyObject) entries);
	RESULT setExternalSubtitleCues(int index, SWIG_PYOBJECT(ePyObject) cues);
	RESULT setExternalSubtitlePictures(int index, int kind, const std::string &path, const std::string &info,
		SWIG_PYOBJECT(ePyObject) entries);
	RESULT setSubtitleDelay(int ms);
	int getSubtitleDelay();

		// iStreamedService
	RESULT streamed(ePtr<iStreamedService> &ptr);
	PyObject *getBufferCharge();
	int setBufferSize(int size);

		// iAudioDelay
	int getAC3Delay();
	int getPCMDelay();
	void setAC3Delay(int);
	void setPCMDelay(int);

		// iCueSheet: the marks and the last position of a film file (a file with a picture), in <film>.cuts next to
		// it, in the format of the recordings
	PyObject *getCutList();
	void setCutList(SWIG_PYOBJECT(ePyObject) list);
	void setCutListEnable(int enable);

	struct audioStream
	{
		GstPad* pad;
		audiotype_t type;
		std::string language_code; /* iso-639, if available. */
		std::string codec; /* clear text codec description */
		audioStream()
			:pad(0), type(atUnknown)
		{
		}
	};
	struct subtitleStream
	{
		GstPad* pad;
		subtype_t type;
		std::string language_code; /* iso-639, if available. */
		subtitleStream()
			:pad(0)
		{
		}
	};
	struct sourceStream
	{
		audiotype_t audiotype;
		containertype_t containertype;
		bool is_video;
		bool is_streaming;
		sourceStream()
			:audiotype(atUnknown), containertype(ctNone), is_video(FALSE), is_streaming(FALSE)
		{
		}
	};
	struct bufferInfo
	{
		int bufferPercent;
		int avgInRate;
		int avgOutRate;
		int64_t bufferingLeft;
		bufferInfo()
			:bufferPercent(0), avgInRate(0), avgOutRate(0), bufferingLeft(-1)
		{
		}
	};
	struct errorInfo
	{
		std::string error_message;
		std::string missing_codec;
	};

private:
	static int pcm_delay;
	static int ac3_delay;
	int m_currentAudioStream;
	int m_currentSubtitleStream;
	int selectAudioStream(int i);
	std::vector<audioStream> m_audioStreams;
	std::vector<subtitleStream> m_subtitleStreams;
	eSubtitleWidget *m_subtitle_widget;
	/* Fast winding: jumps from key frame to key frame every PAS_DERULARE_MS, made on the film thread; the target moves by
	   ratio x the step, the sound is muted while it lasts (only if it was not muted before). */
	int m_currentTrickRatio;		/* 0 = normal play, > 1 forward, < 0 backward */
	ePtr<eTimer> m_trick_timer;
	pts_t m_trick_target;
	bool m_trick_muted;
	void trickTick();
	void trickStop();
	void sunetulInapoi();
	/* the pipeline has prerolled once (the first ASYNC_DONE): a seek asked before that waits in m_pending_seek, fast
	   winding in m_pending_ratio */
	bool m_prerolled;
	pts_t m_pending_seek;
	int m_pending_ratio;
	bool m_watched_to_end;		/* EOS was reached and nothing was sought after it */
	RESULT realPlayPosition(pts_t &pts);
	/* the last position and length of the play, for stop() (m_position_timer takes them once a second) */
	pts_t m_last_position, m_last_length;
	ePtr<eTimer> m_position_timer;
	void positionTick();
	/* PAUSED (true) or PLAYING (false), set on the film thread */
	void cereStarea(bool pauza);
	/* the cue file: read on the film thread after start(), m_cues_timer looks for the result */
	std::multiset<std::pair<pts_t, unsigned int> > m_cue_entries;
	bool m_cues_loaded, m_cues_changed;
	ePtr<eTimer> m_cues_timer;
	void cuesPoll();
	/* why the film cannot be played: "kind|caps|video|text", read by Python as sUser+15 (Components/HdsFilmRedare.py) */
	std::string m_refuz;
	std::string m_capuri_lipsa;	/* the whole type of the last stream without a way to the decoder */
	void refuza(const char *fel, const std::string &capuri, const std::string &text);
	ePtr<eTimer> m_start_timer;
	void startTimeout();
	int m_n_video;			/* video streams at the last ASYNC_DONE, -1 unknown */
	std::shared_ptr<Poarta> m_poarta;
	std::shared_ptr<FirFilm> m_fir;
	friend class eServiceFactoryMP3;
	eServiceReference m_ref;
	int m_buffer_size;
	bufferInfo m_bufferInfo;
	errorInfo m_errorInfo;
	eServiceMP3(eServiceReference ref);
	sigc::signal<void(iPlayableService*, int)> m_event;
	enum
	{
		stIdle, stRunning, stStopped,
        };
        int m_state;
        GstElement *m_gst_playbin;
        GstTagList *m_stream_tags;

        struct Message
        {
                Message()
                        :type(-1)
                {}
                Message(int type)
                        :type(type)
                {}
                Message(int type, GstPad *pad)
                        :type(type)
                {
                        d.pad=pad;
                }

                int type;
                union {
                        GstPad *pad; // for msg type 3
                } d;
        };

        eFixedMessagePump<Message> m_pump;

        audiotype_t gstCheckAudioPad(GstStructure* structure);
        void gstBusCall(GstBus *bus, GstMessage *msg);
        /* the callbacks below get the Poarta of the service as user_data, never the service itself */
        static GstBusSyncReply gstBusSyncHandler(GstBus *bus, GstMessage *message, gpointer user_data);
	static void gstTextpadHasCAPS(GstPad *pad, GParamSpec * unused, gpointer user_data);
	void gstTextpadHasCAPS_synced(GstPad *pad);
        static GstFlowReturn gstCBsubtitleAvail(GstElement *element, gpointer user_data);  // GST1.0: "new-sample" expects a GstFlowReturn back, not void
        GstPad* gstCreateSubtitleSink(eServiceMP3* _this, subtype_t type);
	void gstPoll(const Message&);
        static void gstHTTPSourceSetAgent(GObject *source, GParamSpec *unused, gpointer user_data);

	struct SubtitlePage
	{
		/* Dvb: a picture subtitle of the container (VobSub, PGS), shown by the widget like a DVB page; an empty one
		   clears the screen */
		enum { Unknown, Pango, Vob, Dvb } type;
		ePangoSubtitlePage pango_page;
		eVobSubtitlePage vob_page;
		eDVBSubtitlePage dvb_page;
		int dvb_timeout;	/* ms, <= 0: until the next page */
	};
	eHdsVobSub m_vobsub;		/* the decoder of the DVD stream, with the palette of the stream (codec_data) */
	int m_vobsub_stream;		/* the stream whose palette is in m_vobsub, -1 none */
	eHdsPgs m_pgs;
	int m_pgs_stream;
	void pagesFromPicture(const eHdsPaginaImagine &p, gint64 pts_ns, gint64 duration_ns);

        std::list<SubtitlePage> m_subtitle_pages;
	pts_t m_page_end_pts;		/* the end of the container line on screen (film time), -1 none: kept over a pause */
	bool m_paused;			/* pause() was called: the subtitle timers wait for unpause() */
        ePtr<eTimer> m_subtitle_sync_timer;
        
        ePtr<eTimer> m_streamingsrc_timeout;
        pts_t m_prev_decoder_time;
        int m_decoder_time_valid_state;

        void pushSubtitles();
        void pullSubtitle();
        void sourceTimeout();
        int m_subs_to_pull;
        sourceStream m_sourceinfo;
	eSingleLock m_subs_to_pull_lock;
	gulong m_subs_to_pull_handler_id;

	RESULT seekToImpl(pts_t to);

	/* Subtitle files next to the film, read in Python (Components/HdsSubtitrariFilm.py) and handed over as lines
	   with their times. They are listed after the container streams with the numbers 100, 101, ... and shown by
	   the play position, so choosing one never touches the pipeline. While one of them is shown, the pages that
	   still come from the container stream are pulled and dropped. */
	struct externalCue
	{
		int start_ms, end_ms;
		std::string text;	/* lines separated by '\n', simple markup (<i>, <b>) kept for the widget */
		bool top;
	};
	/* a picture subtitle file (.idx+.sub, .sup): the packets stay in the file and are read one at a time, shortly
	   before their time, on the thread of m_picture_reader (a film has tens of megabytes of them) */
	typedef eHdsCititorImagini::Intrare externalPicture;
	struct externalSubtitle
	{
		std::string name, language;
		int type;
		int flags;			/* 1 forced (only the foreign lines), 2 for the deaf and hard of hearing */
		bool loaded;
		std::vector<externalCue> cues;
		int picture_kind;		/* stVOB or stPGS for a picture file, else 0 */
		std::string path, info;		/* the file of the packets; the .idx header (palette, size) */
		std::vector<externalPicture> pictures;
	};
	int m_picture_index;			/* the packet of the active file that is due now, -1 none */
	bool m_picture_ready;			/* m_picture_page holds that packet (or an empty page if it could not be read) */
	eHdsPaginaImagine m_picture_page;
	eHdsCititorImagini m_picture_reader;
	std::vector<externalSubtitle> m_external_subtitles;
	int m_external_active;		/* index in m_external_subtitles, -1 = a container stream or nothing */
	int m_subtitle_delay_ms;	/* > 0: the subtitles come later */
	ePtr<eTimer> m_external_timer;
	std::vector<int> m_external_shown;	/* the cues on screen now */
	void externalTick();
	void showExternalCues(const std::vector<int> &cues, int now_ms);
	void externalPictureTick(const externalSubtitle &s, int now_ms);

	gint m_aspect, m_width, m_height, m_framerate, m_progressive, m_gamma;
	std::string m_useragent;
};

#endif
