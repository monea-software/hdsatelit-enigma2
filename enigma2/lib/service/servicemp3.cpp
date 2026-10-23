/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
	/* note: this requires gstreamer 1.0.x and a big list of plugins. */
	/* The places changed from the GStreamer 0.10 API are marked "GST1.0" below. The file is built only with
	   --with-gstreamer=yes (lib/service/Makefile.am, `if HAVE_GSTREAMER`). */
#include <lib/base/ebase.h>
#include <lib/base/eerror.h>
#include <lib/base/init_num.h>
#include <lib/base/init.h>
#include <lib/base/nconfig.h>
#include <lib/base/object.h>
#include <lib/dvb/decoder.h>
#include <lib/dvb/volume.h>
#if HAVE_HISILICON
#include <lib/dvb/hdspazavideo.h>
#endif
#include <lib/components/file_eraser.h>
#include <lib/gui/esubtitle.h>
#include <lib/service/servicemp3.h>
#include <lib/service/service.h>
#include <lib/gdi/gpixmap.h>

#include <algorithm>
#include <cstdlib>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <gst/gst.h>
#include <gst/pbutils/missing-plugins.h>
#include <sys/stat.h>
#include <dirent.h>
#include <endian.h>
#include <arpa/inet.h>

#define HTTP_TIMEOUT 10

/* the film files played here: the extension, the container and whether it carries a picture */
static const struct
{
	const char *extensie;
	containertype_t container;
	bool video;
} felurileFilmelor[] = {
	{ "mp2", ctNone, false }, { "mp3", ctNone, false }, { "ogg", ctNone, false }, { "wav", ctNone, false },
	{ "wave", ctNone, false }, { "flac", ctNone, false }, { "m4a", ctMP4, false }, { "mka", ctMKV, false },
	{ "opus", ctNone, false }, { "aac", ctNone, false }, { "ac3", ctNone, false }, { "dts", ctNone, false },
	{ "mpg", ctMPEGPS, true }, { "mpeg", ctMPEGPS, true }, { "vob", ctMPEGPS, true }, { "dat", ctVCD, true },
	{ "mkv", ctMKV, true }, { "webm", ctMKV, true }, { "avi", ctAVI, true }, { "divx", ctAVI, true },
	{ "mp4", ctMP4, true }, { "m4v", ctMP4, true }, { "mov", ctMP4, true }, { "3gp", ctMP4, true },
	{ "flv", ctNone, true }, { "ogv", ctNone, true },
};

/* how long the main loop waits for the stop of a pipeline before it goes on without it (the film thread finishes the
   stop on its own); a normal stop takes some tens of milliseconds */
static const int ASTEPTARE_OPRIRE_MS = 2500;
/* the step of fast winding: one jump every PAS_DERULARE_MS, of ratio x PAS_DERULARE_MS of film time */
static const int PAS_DERULARE_MS = 500;
/* a local film that has not prerolled and has not moved after this long is reported as not starting */
static const int ASTEPTARE_PORNIRE_MS = 30000;
/* the last position is kept only after the first minute and before the last one (pts, 90 kHz) */
static const pts_t MARGINE_RELUARE = 60 * 90000LL;

/* ------------------------------------------------------------------ the gate of the GStreamer callbacks */

/* GStreamer calls the bus sync handler, the "new-sample" of the subtitle appsink, "notify::caps" of the text pads and
   "notify::source" on its own threads. They get this gate, not the service: stop() closes it before the pipeline is
   handed to the film thread, so a callback that comes during the teardown, or after the service is gone, does nothing.
   The gate lives as long as the pipeline (the service and the film thread both hold it). */
struct eServiceMP3::Poarta
{
	std::mutex lacat;
	eServiceMP3 *serviciu;
	explicit Poarta(eServiceMP3 *s) : serviciu(s) {}
	void inchide()
	{
		std::lock_guard<std::mutex> l(lacat);
		serviciu = NULL;
	}
};

/* ------------------------------------------------------------------ the film thread */

/* The calls that can wait on the disk, the network or the decoder driver run on this thread, never on the main loop:
   every change of state (the start, the pause, the play after a pause), reading the cue file, every jump (a number
   key, the resume, a jump from the web page, the steps of fast winding) and the stop of the pipeline. The main loop
   only posts the job and goes on. Of each kind only the last job asked is kept, and they run in this order: state,
   cue file, jump; a job still waiting when the stop comes is dropped. A change of state takes the state lock of the
   pipeline, and a jump or a stop waits for the streaming threads: on this thread none of them can hold the main loop.
   It holds its own reference to the pipeline and the gate and nothing of the service, so the service may be destroyed
   while a stop is still running.
   The stop sends FLUSH_START to the sink pads first: the sinks of the receiver write in a loop that waits in poll()
   for room in the decoder while the base class holds its preroll lock, and a change of state waits for that lock;
   FLUSH_START wakes the loop (the sink marks itself flushing and writes to its unlock socket) before the base class
   takes the lock. Then the pipeline goes to NULL and the cue file is written. */
typedef std::vector<std::pair<pts_t, unsigned int> > listaCues;

struct eServiceMP3::FirFilm
{
	std::mutex lacat;
	std::condition_variable semnal;
	GstElement *pipeline;
	std::shared_ptr<Poarta> poarta;
	std::string cale;			/* the film file; "<cale>.cuts" is the cue file */
	bool citeste, citit;			/* the cue file: asked, read (cues holds it) */
	listaCues cues;
	bool salt;				/* a jump is waiting: only the last one asked is kept */
	bool salt_derulare;			/* the waiting jump is a step of fast winding (the end of the winding drops it) */
	gint64 salt_ns;
	int salt_fel;				/* GstSeekFlags */
	bool schimba_starea;			/* a change of state is waiting: PAUSED when pauza, PLAYING otherwise */
	bool pauza;
	bool opreste, oprit;
	int ms_oprire;
	bool scrie;				/* write (or remove, when empty) the cue file after the stop */
	listaCues de_scris;
	FirFilm() : pipeline(NULL), citeste(false), citit(false), salt(false), salt_derulare(false), salt_ns(0), salt_fel(0),
		schimba_starea(false), pauza(false), opreste(false), oprit(false), ms_oprire(0), scrie(false) {}
};

/* the cue file: pairs of (position, kind), big-endian 64 + 32 bit, as the recordings have them */
static bool citesteCues(const std::string &fisier, listaCues &cues)
{
	cues.clear();
	FILE *f = fopen(fisier.c_str(), "rb");
	if (!f)
		return false;
	unsigned char rand[12];
	while (cues.size() < 10000 && fread(rand, sizeof(rand), 1, f) == 1)
	{
		uint64_t unde;
		uint32_t ce;
		memcpy(&unde, rand, 8);
		memcpy(&ce, rand + 8, 4);
		unde = be64toh(unde);
		ce = ntohl(ce);
		if (ce > 3)
			break;
		cues.push_back(std::make_pair((pts_t)unde, (unsigned int)ce));
	}
	fclose(f);
	return true;
}

/* written to "<cue file>.tmp" and renamed over it; an empty list removes the cue file. Only while the film is still
   there (a stick taken out keeps nothing). A place that cannot be written (read-only NTFS, a read-only share) is said
   once in the log. */
static void scrieCues(const std::string &film, const listaCues &cues)
{
	struct stat s;
	if (::stat(film.c_str(), &s) != 0)
		return;
	std::string fisier = film + ".cuts";
	if (cues.empty())
	{
		if (::unlink(fisier.c_str()) == 0)
			eDebug("[eServiceMP3] cue file removed: %s", fisier.c_str());
		return;
	}
	std::string temporar = fisier + ".tmp";
	FILE *f = fopen(temporar.c_str(), "wb");
	if (!f)
	{
		/* two stops that ran past their time may write at once, each on its own film thread */
		static std::mutex lacat_spus;
		static std::string spus;
		std::string dosar = film.substr(0, film.rfind('/') + 1);
		std::lock_guard<std::mutex> l(lacat_spus);
		if (spus != dosar)
		{
			eDebug("[eServiceMP3] the last position cannot be kept in %s (%m)", dosar.c_str());
			spus = dosar;
		}
		return;
	}
	bool bun = true;
	for (unsigned int i = 0; i < cues.size() && bun; ++i)
	{
		unsigned char rand[12];
		uint64_t unde = htobe64((uint64_t)cues[i].first);
		uint32_t ce = htonl(cues[i].second);
		memcpy(rand, &unde, 8);
		memcpy(rand + 8, &ce, 4);
		bun = fwrite(rand, sizeof(rand), 1, f) == 1;
	}
	if (fclose(f) != 0)
		bun = false;
	if (!bun || ::rename(temporar.c_str(), fisier.c_str()) != 0)
	{
		eDebug("[eServiceMP3] the cue file could not be written: %s (%m)", fisier.c_str());
		::unlink(temporar.c_str());
	}
}

/* FLUSH_START on the sink pads of the picture, the sound and the subtitles (see FirFilm) */
static void golesteSinkurile(GstElement *pipeline)
{
	static const char *sinkuri[] = { "audio-sink", "video-sink", "text-sink" };
	for (unsigned int i = 0; i < sizeof(sinkuri) / sizeof(sinkuri[0]); ++i)
	{
		GstElement *sink = NULL;
		g_object_get(G_OBJECT(pipeline), sinkuri[i], &sink, NULL);
		if (!sink)
			continue;
		GstPad *pad = gst_element_get_static_pad(sink, "sink");
		if (pad)
		{
			gst_pad_send_event(pad, gst_event_new_flush_start());
			gst_object_unref(pad);
		}
		gst_object_unref(sink);
	}
}

static void firFilm(std::shared_ptr<eServiceMP3::FirFilm> f)
{
	std::unique_lock<std::mutex> l(f->lacat);
	while (!f->opreste)
	{
		if (f->schimba_starea)
		{
			f->schimba_starea = false;
			GstState stare = f->pauza ? GST_STATE_PAUSED : GST_STATE_PLAYING;
			l.unlock();
			if (gst_element_set_state(f->pipeline, stare) == GST_STATE_CHANGE_FAILURE)
				eDebug("[eServiceMP3] the change to %s failed", gst_element_state_get_name(stare));
			l.lock();
			continue;
		}
		if (f->citeste)
		{
			f->citeste = false;
			std::string fisier = f->cale + ".cuts";
			l.unlock();
			listaCues cues;
			citesteCues(fisier, cues);
			l.lock();
			f->cues.swap(cues);
			f->citit = true;
			continue;
		}
		if (f->salt)
		{
			f->salt = false;
			f->salt_derulare = false;
			gint64 ns = f->salt_ns;
			int fel = f->salt_fel;
			l.unlock();
			if (!gst_element_seek(f->pipeline, 1.0, GST_FORMAT_TIME, (GstSeekFlags)fel, GST_SEEK_TYPE_SET, ns,
					GST_SEEK_TYPE_NONE, GST_CLOCK_TIME_NONE))
				eDebug("[eServiceMP3] the jump to %" GST_TIME_FORMAT " failed", GST_TIME_ARGS(ns));
			l.lock();
			continue;
		}
		f->semnal.wait(l);
	}
	l.unlock();
	std::chrono::steady_clock::time_point t0 = std::chrono::steady_clock::now();
	golesteSinkurile(f->pipeline);
	gst_element_set_state(f->pipeline, GST_STATE_NULL);
	int ms = (int)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - t0).count();
	l.lock();
	f->oprit = true;
	f->ms_oprire = ms;
	bool scrie = f->scrie;
	listaCues de_scris;
	de_scris.swap(f->de_scris);
	std::string cale = f->cale;
	f->semnal.notify_all();
	l.unlock();
	eDebug("[eServiceMP3] stop: done in %d ms", ms);
	if (scrie)
		scrieCues(cale, de_scris);
	gst_object_unref(f->pipeline);
	f->pipeline = NULL;
}

/* The sink of playbin for "audio-sink" or "video-sink" only while it is in use: a sink set on playbin stays there when
   the film has no such track (or the track was left out), and a sink that never started has no position to give. */
static GstElement *sinkFolosit(GstElement *playbin, const char *proprietate)
{
	GstElement *sink = NULL;
	g_object_get(G_OBJECT(playbin), proprietate, &sink, NULL);
	if (!sink)
		return NULL;
	GstObject *parinte = gst_object_get_parent(GST_OBJECT(sink));
	if (!parinte)
	{
		gst_object_unref(sink);
		return NULL;
	}
	gst_object_unref(parinte);
	return sink;
}

/* the video0 and audio0 nodes the process already holds when a film starts (the decoder of the channel before, a
   still picture): one line in the log for the tests on the receiver */
static void numaraDecodoare(int &video, int &audio)
{
	video = audio = 0;
	DIR *d = opendir("/proc/self/fd");
	if (!d)
		return;
	struct dirent *e;
	char tinta[256];
	while ((e = readdir(d)) != NULL)
	{
		if (e->d_name[0] == '.')
			continue;
		std::string cale = std::string("/proc/self/fd/") + e->d_name;
		ssize_t n = readlink(cale.c_str(), tinta, sizeof(tinta) - 1);
		if (n <= 0)
			continue;
		tinta[n] = 0;
		if (strstr(tinta, "/dvb/adapter0/video0"))
			++video;
		else if (strstr(tinta, "/dvb/adapter0/audio0"))
			++audio;
	}
	closedir(d);
}

/* the state and the wait channel of every thread of the process, once, when a stop does not end in time */
static void scrieStareaFirelor()
{
	DIR *d = opendir("/proc/self/task");
	if (!d)
		return;
	struct dirent *e;
	std::string linie;
	int cate = 0;
	while ((e = readdir(d)) != NULL && cate < 64)
	{
		if (e->d_name[0] == '.')
			continue;
		char buf[512], wchan[64] = "";
		std::string dosar = std::string("/proc/self/task/") + e->d_name;
		FILE *f = fopen((dosar + "/stat").c_str(), "r");
		if (!f)
			continue;
		size_t n = fread(buf, 1, sizeof(buf) - 1, f);
		fclose(f);
		buf[n] = 0;
		/* "tid (comm) S ...": the name may hold spaces, the state follows the last ')' */
		char *paranteza = strrchr(buf, ')');
		char *nume = strchr(buf, '(');
		char stare = paranteza && paranteza[1] == ' ' ? paranteza[2] : '?';
		std::string comm = nume && paranteza && paranteza > nume ? std::string(nume + 1, paranteza - nume - 1) : "?";
		f = fopen((dosar + "/wchan").c_str(), "r");
		if (f)
		{
			size_t m = fread(wchan, 1, sizeof(wchan) - 1, f);
			wchan[m] = 0;
			fclose(f);
		}
		linie += std::string(" ") + e->d_name + ":" + comm + ":" + stare + ":" + (wchan[0] ? wchan : "-");
		++cate;
	}
	closedir(d);
	eDebug("[eServiceMP3] threads (tid:name:state:wait):%s", linie.c_str());
}

// eServiceFactoryMP3

eServiceFactoryMP3::eServiceFactoryMP3()
{
	ePtr<eServiceCenter> sc;
	
	eServiceCenter::getPrivInstance(sc);
	if (sc)
	{
		/* a file with an extension of this list is shown in the movie list and played here; the formats that have no
		   way to the decoder of the receiver are refused with a message when they start (Components/HdsFilmRedare.py) */
		std::list<std::string> extensions;
		for (unsigned int i = 0; i < sizeof(felurileFilmelor) / sizeof(felurileFilmelor[0]); ++i)
			extensions.push_back(felurileFilmelor[i].extensie);
		sc->addServiceFactory(eServiceFactoryMP3::id, this, extensions);
	}

	m_service_info = new eStaticServiceMP3Info();
}

eServiceFactoryMP3::~eServiceFactoryMP3()
{
	ePtr<eServiceCenter> sc;
	
	eServiceCenter::getPrivInstance(sc);
	if (sc)
		sc->removeServiceFactory(eServiceFactoryMP3::id);
}

DEFINE_REF(eServiceFactoryMP3)

	// iServiceHandler
RESULT eServiceFactoryMP3::play(const eServiceReference &ref, ePtr<iPlayableService> &ptr)
{
		// check resources...
	ptr = new eServiceMP3(ref);
	return 0;
}

RESULT eServiceFactoryMP3::record(const eServiceReference &ref, ePtr<iRecordableService> &ptr)
{
	ptr=0;
	return -1;
}

RESULT eServiceFactoryMP3::list(const eServiceReference &, ePtr<iListableService> &ptr)
{
	ptr=0;
	return -1;
}

RESULT eServiceFactoryMP3::info(const eServiceReference &ref, ePtr<iStaticServiceInformation> &ptr)
{
	ptr = m_service_info;
	return 0;
}

class eMP3ServiceOfflineOperations: public iServiceOfflineOperations
{
	DECLARE_REF(eMP3ServiceOfflineOperations);
	eServiceReference m_ref;
public:
	eMP3ServiceOfflineOperations(const eServiceReference &ref);
	
	RESULT deleteFromDisk(int simulate);
	RESULT getListOfFilenames(std::list<std::string> &);
	RESULT reindex();
};

DEFINE_REF(eMP3ServiceOfflineOperations);

eMP3ServiceOfflineOperations::eMP3ServiceOfflineOperations(const eServiceReference &ref): m_ref((const eServiceReference&)ref)
{
}

RESULT eMP3ServiceOfflineOperations::deleteFromDisk(int simulate)
{
	if (simulate)
		return 0;
	else
	{
		std::list<std::string> res;
		if (getListOfFilenames(res))
			return -1;
		
		eBackgroundFileEraser *eraser = eBackgroundFileEraser::getInstance();
		if (!eraser)
			eDebug("FATAL !! can't get background file eraser");
		
		for (std::list<std::string>::iterator i(res.begin()); i != res.end(); ++i)
		{
			eDebug("Removing %s...", i->c_str());
			if (eraser)
				eraser->erase(i->c_str());
			else
				::unlink(i->c_str());
		}
		
		return 0;
	}
}

RESULT eMP3ServiceOfflineOperations::getListOfFilenames(std::list<std::string> &res)
{
	res.clear();
	res.push_back(m_ref.path);
	/* the marks and the last position go with the film, as for the recordings (a missing file is skipped by the
	   eraser); a new film with the same name starts clean */
	res.push_back(m_ref.path + ".cuts");
	return 0;
}

RESULT eMP3ServiceOfflineOperations::reindex()
{
	return -1;
}


RESULT eServiceFactoryMP3::offlineOperations(const eServiceReference &ref, ePtr<iServiceOfflineOperations> &ptr)
{
	ptr = new eMP3ServiceOfflineOperations(ref);
	return 0;
}

// eStaticServiceMP3Info


// eStaticServiceMP3Info is seperated from eServiceMP3 to give information
// about unopened files.

// probably eServiceMP3 should use this class as well, and eStaticServiceMP3Info
// should have a database backend where ID3-files etc. are cached.
// this would allow listing the mp3 database based on certain filters.

DEFINE_REF(eStaticServiceMP3Info)

eStaticServiceMP3Info::eStaticServiceMP3Info()
{
}

RESULT eStaticServiceMP3Info::getName(const eServiceReference &ref, std::string &name)
{
	if ( ref.name.length() )
		name = ref.name;
	else
	{
		size_t last = ref.path.rfind('/');
		if (last != std::string::npos)
			name = ref.path.substr(last+1);
		else
			name = ref.path;
	}
	return 0;
}

int eStaticServiceMP3Info::getLength(const eServiceReference &ref)
{
	return -1;
}

int eStaticServiceMP3Info::getInfo(const eServiceReference &ref, int w)
{
	switch (w)
	{
	case iServiceInformation::sTimeCreate:
	{
		struct stat s;
		if(stat(ref.path.c_str(), &s) == 0)
		{
		  return s.st_mtime;
		}
		return iServiceInformation::resNA;
	}
	default: break;
	}
	return iServiceInformation::resNA;
}
 

// eServiceMP3
int eServiceMP3::ac3_delay,
    eServiceMP3::pcm_delay;

eServiceMP3::eServiceMP3(eServiceReference ref)
	:m_ref(ref), m_pump(eApp, 1)
{
	m_trick_timer = eTimer::create(eApp);
	m_trick_target = 0;
	m_trick_muted = false;
	m_prerolled = false;
	m_pending_seek = -1;
	m_pending_ratio = 0;
	m_watched_to_end = false;
	m_last_position = -1;
	m_last_length = -1;
	m_position_timer = eTimer::create(eApp);
	m_cues_loaded = false;
	m_cues_changed = false;
	m_cues_timer = eTimer::create(eApp);
	m_start_timer = eTimer::create(eApp);
	m_n_video = -1;
	m_poarta = std::make_shared<Poarta>(this);
	m_subs_to_pull_handler_id = 0;
	m_subtitle_sync_timer = eTimer::create(eApp);
	m_streamingsrc_timeout = 0;
	m_stream_tags = 0;
	m_currentAudioStream = -1;
	m_currentSubtitleStream = 0;
	m_subtitle_widget = 0;
	m_currentTrickRatio = 0;
	m_subs_to_pull = 0;
	m_buffer_size = 1*1024*1024;
	m_prev_decoder_time = -1;
	m_decoder_time_valid_state = 0;
	m_errorInfo.missing_codec = "";
	m_external_active = -1;
	m_subtitle_delay_ms = 0;
	m_vobsub_stream = -1;
	m_pgs_stream = -1;
	m_picture_index = -1;
	m_picture_ready = false;
	m_page_end_pts = -1;
	m_paused = false;
	m_external_timer = eTimer::create(eApp);

	CONNECT(m_trick_timer->timeout, eServiceMP3::trickTick);
	CONNECT(m_position_timer->timeout, eServiceMP3::positionTick);
	CONNECT(m_cues_timer->timeout, eServiceMP3::cuesPoll);
	CONNECT(m_start_timer->timeout, eServiceMP3::startTimeout);
	CONNECT(m_subtitle_sync_timer->timeout, eServiceMP3::pushSubtitles);
	CONNECT(m_external_timer->timeout, eServiceMP3::externalTick);
	CONNECT(m_pump.recv_msg, eServiceMP3::gstPoll);
	m_aspect = m_width = m_height = m_framerate = m_progressive = m_gamma = -1;

	m_state = stIdle;
	eDebug("eServiceMP3::construct!");

	const char *filename = m_ref.path.c_str();
	const char *ext = strrchr(filename, '.');
	if (!ext)
		ext = filename;

	m_sourceinfo.is_video = FALSE;
	m_sourceinfo.audiotype = atUnknown;
	if (ext != filename)
	{
		for (unsigned int i = 0; i < sizeof(felurileFilmelor) / sizeof(felurileFilmelor[0]); ++i)
			if (!strcasecmp(ext + 1, felurileFilmelor[i].extensie))
			{
				m_sourceinfo.containertype = felurileFilmelor[i].container;
				m_sourceinfo.is_video = felurileFilmelor[i].video;
				break;
			}
		if (!strcasecmp(ext, ".ts"))
		{
			m_sourceinfo.containertype = ctMPEGTS;
			m_sourceinfo.is_video = TRUE;
		}
		else if (!strcasecmp(ext, ".m4a") || !strcasecmp(ext, ".aac"))
			m_sourceinfo.audiotype = atAAC;
		else if (!strcasecmp(ext, ".mp3"))
			m_sourceinfo.audiotype = atMP3;
	}
	/* a track of an audio CD: /autofs/<drive>/track-NN.wav */
	size_t lungime = strlen(filename);
	if (!strncmp(filename, "/autofs/", 8) && lungime >= 13 && !strncmp(filename + lungime - 13, "/track-", 7) &&
			!strcasecmp(ext, ".wav"))
		m_sourceinfo.containertype = ctCDA;
	static const char *fluxuri[] = { "http://", "https://", "udp://", "rtp://", "mms://", "rtsp://", "rtspt://" };
	for (unsigned int i = 0; i < sizeof(fluxuri) / sizeof(fluxuri[0]); ++i)
		if (!strncmp(filename, fluxuri[i], strlen(fluxuri[i])))
			m_sourceinfo.is_streaming = TRUE;

	gchar *uri;

	if ( m_sourceinfo.is_streaming )
	{
		uri = g_strdup_printf ("%s", filename);
		m_streamingsrc_timeout = eTimer::create(eApp);;
		CONNECT(m_streamingsrc_timeout->timeout, eServiceMP3::sourceTimeout);

		std::string config_str;
		if( ePythonConfigQuery::getConfigValue("config.mediaplayer.useAlternateUserAgent", config_str) == 0 )
		{
			if ( config_str == "True" )
				ePythonConfigQuery::getConfigValue("config.mediaplayer.alternateUserAgent", m_useragent);
		}
		if ( m_useragent.length() == 0 )
			m_useragent = "Dream Multimedia Dreambox Enigma2 Mediaplayer";
	}
	else if ( m_sourceinfo.containertype == ctCDA )
	{
		int i_track = atoi(filename+18);
		uri = g_strdup_printf ("cdda://%i", i_track);
	}
	else if ( m_sourceinfo.containertype == ctVCD )
	{
		/* a .dat file that cannot be read as a file is a track of a video CD; one byte tells it (the old read of
		   128 KiB, on the stack, blocked the main loop on a slow disk) */
		int fd = open(filename, O_RDONLY);
		char octet;
		int ret = fd >= 0 ? read(fd, &octet, 1) : -1;
		if (fd >= 0)
			close(fd);
		if ( ret == -1 ) // this is a "REAL" VCD
			uri = g_strdup_printf ("vcd://");
		else
			uri = g_filename_to_uri(filename, NULL, NULL);
	}
	else
		uri = g_filename_to_uri(filename, NULL, NULL);

	eDebug("eServiceMP3::playbin uri=%s", uri);

	m_gst_playbin = gst_element_factory_make("playbin", "playbin");  // GST1.0: "playbin2" -> "playbin"
	if (!m_gst_playbin)
	{
		m_errorInfo.error_message = "failed to create GStreamer pipeline!\n";
		m_refuz = "pipeline|||";
	}
	else
	{
		g_object_set (G_OBJECT (m_gst_playbin), "uri", uri, NULL);
		int flags = 0x47; // ( GST_PLAY_FLAG_VIDEO | GST_PLAY_FLAG_AUDIO | GST_PLAY_FLAG_NATIVE_VIDEO | GST_PLAY_FLAG_TEXT );
		g_object_set (G_OBJECT (m_gst_playbin), "flags", flags, NULL);
		/* The sinks of the decoder of the receiver are set here, not left to the ranks: the registry of the receiver
		   also has pulsesink (a higher rank, no sound server) and alsasink, and playbin could give the sound to one of
		   them. The names keep "videosink" and "audiosink": the errors of the sinks are told apart by them
		   (GST_MESSAGE_ERROR). Without dvbmediasink (the emulator on the PC) playbin chooses by rank, as before. */
		GstElement *sinkImagine = gst_element_factory_make("dvbvideosink", "dvbvideosink");
		if (sinkImagine)
			g_object_set (G_OBJECT (m_gst_playbin), "video-sink", sinkImagine, NULL);
		else
			eDebug("eServiceMP3::dvbvideosink is missing: playbin chooses the picture sink by rank");
		GstElement *sinkSunet = gst_element_factory_make("dvbaudiosink", "dvbaudiosink");
		if (sinkSunet)
			g_object_set (G_OBJECT (m_gst_playbin), "audio-sink", sinkSunet, NULL);
		else
			eDebug("eServiceMP3::dvbaudiosink is missing: playbin chooses the sound sink by rank");
	}
#if HAVE_HISILICON
	/* The sinks write the file to video0 and audio0: without the memory the video driver shares with the platform
	   daemon the first of these writes is a kernel oops (lib/dvb/hdspazavideo.h). The pipeline, still in NULL (no
	   device opened or written), is dropped then: start() tells the player (evUser+16) and the reason is in
	   sUser+15. */
	if (m_gst_playbin)
	{
		int mapped = hisiEsMemoryMapped();
		if (mapped != 1)
		{
			eWarning("[eServiceMP3] %s, a write of the sinks on video0 or audio0 would crash the kernel; the file is not "
				"played", mapped == 0 ? "the video driver has no memory shared with the platform daemon (its mapping failed "
				"for lack of kernel vmalloc space; a restart of the receiver brings it back)" :
				"/proc/vmallocinfo cannot be read, so the memory of the video driver cannot be checked");
			gst_object_unref(GST_OBJECT(m_gst_playbin));
			m_gst_playbin = NULL;
			m_errorInfo.error_message = "the video decoder has no memory for files, a restart of the receiver brings it "
				"back\n";
			m_refuz = std::string("decodor|||") + (mapped == 0 ? "no memory shared with the platform daemon" :
				"/proc/vmallocinfo unreadable");
		}
	}
#endif

	g_free(uri);

	/* Text streams in a container that are not UTF-8 (Matroska asks for UTF-8, some files are not): the demuxer
	   converts them from the encoding in GST_SUBTITLE_ENCODING, read at every conversion. It is set here, on the main
	   thread and before this pipeline has threads of its own, from "Default encoding" of the film subtitles
	   (Components/HdsSubtitrariFilm.py); without the setting, Central European (the Romanian files). The conversion
	   needs the glibc gconv module of that encoding in the image. */
	{
		static const char *codari[][2] = {
			{ "cp1250", "WINDOWS-1250" }, { "iso8859_2", "ISO-8859-2" }, { "iso8859_16", "ISO-8859-16" },
			{ "iso8859_15", "ISO-8859-15" }, { "cp1252", "WINDOWS-1252" }, { "cp1251", "WINDOWS-1251" },
			{ "cp1253", "WINDOWS-1253" }, { "cp1254", "WINDOWS-1254" } };
		std::string aleasa;
		const char *codare = "WINDOWS-1250";
		if (ePythonConfigQuery::getConfigValue("config.subtitles.hds_film_codare", aleasa) == 0)
			for (unsigned int i = 0; i < sizeof(codari) / sizeof(codari[0]); ++i)
				if (aleasa == codari[i][0])
					codare = codari[i][1];
		setenv("GST_SUBTITLE_ENCODING", codare, 1);
	}

	GstElement *subsink = m_gst_playbin ? gst_element_factory_make("appsink", "subtitle_sink") : NULL;
	if (!subsink)
		eDebug("eServiceMP3::no subtitles: the appsink element is missing");
	else
	{
		m_subs_to_pull_handler_id = g_signal_connect (subsink, "new-sample", G_CALLBACK (gstCBsubtitleAvail), m_poarta.get());  // GST1.0: "new-buffer" -> "new-sample"
		/* The subtitle types that decodebin treats as final (gst/playback/gstrawcaps.h in GStreamer 1.x): with all of
		   them accepted, a text stream chosen by playbin can never end in not-negotiated and stop the film. The types
		   that are not drawn (DVB and XSUB pictures from a container) are dropped in pullSubtitle and not listed. The
		   names from GStreamer 0.10 (text/plain, text/x-pango-markup, video/x-dvd-subpicture) are no longer produced
		   by any element of the image. ASS/SSA stay out: playbin puts ssaparse in front and the text comes plain.
		   application/x-subtitle-unknown is a Matroska track the demuxer does not know (WebVTT, DVB): playbin hands it
		   to this sink as it is; WebVTT is read here as text (felNecunoscut), the others are dropped and not listed. */
		GstCaps *caps = gst_caps_from_string("text/x-raw; subpicture/x-dvd; subpicture/x-dvb; subpicture/x-xsub; subpicture/x-pgs; "
			"application/x-subtitle-unknown");
		g_object_set (G_OBJECT (subsink), "caps", caps, NULL);
		gst_caps_unref(caps);
		g_object_set (G_OBJECT (m_gst_playbin), "text-sink", subsink, NULL);
	}

	if ( m_gst_playbin )
	{
		GstBus *bus = gst_pipeline_get_bus (GST_PIPELINE (m_gst_playbin));
		gst_bus_set_sync_handler(bus, gstBusSyncHandler, m_poarta.get(), NULL);  // GST1.0: the 4th argument (GDestroyNotify) is required
		gst_object_unref(bus);
		/* Subtitle files next to the film (film.srt, film.ro.srt, .sub, .ass, ...) are found and read by
		   Components/HdsSubtitrariFilm.py and come through setExternalSubtitles; the old "suburi" for film.srt
		   would list that file twice. */
		if ( m_sourceinfo.is_streaming )
		{
			g_signal_connect (G_OBJECT (m_gst_playbin), "notify::source", G_CALLBACK (gstHTTPSourceSetAgent), m_poarta.get());
		}
		/* the film thread, with its own references; it waits for its jobs */
		m_fir = std::make_shared<FirFilm>();
		m_fir->pipeline = GST_ELEMENT(gst_object_ref(m_gst_playbin));
		m_fir->poarta = m_poarta;
		m_fir->cale = m_ref.path;
		std::thread(firFilm, m_fir).detach();
		setBufferSize(m_buffer_size);
	} else
		/* the player is told in start(): nothing listens to the events of this service yet */
		eDebug("eServiceMP3::sorry, can't play: %s",m_errorInfo.error_message.c_str());
}

eServiceMP3::~eServiceMP3()
{
	if (m_state == stRunning)
		stop();
	else if (m_state == stIdle && m_fir)
	{
		/* never started: the film thread ends and lets the pipeline go (it is in NULL already) */
		m_poarta->inchide();
		std::lock_guard<std::mutex> l(m_fir->lacat);
		m_fir->opreste = true;
		m_fir->semnal.notify_all();
	}

	delete m_subtitle_widget;

	if (m_stream_tags)
		gst_tag_list_unref(m_stream_tags);  // GST1.0: gst_tag_list_free -> gst_tag_list_unref (GstTagList is refcounted in 1.0)

	if (m_gst_playbin)
	{
		/* the film thread holds its own reference until the pipeline is in NULL */
		gst_object_unref (GST_OBJECT (m_gst_playbin));
		eDebug("eServiceMP3::destruct!");
	}
}

DEFINE_REF(eServiceMP3);

RESULT eServiceMP3::connectEvent(const sigc::slot<void(iPlayableService*, int)> &event, ePtr<eConnection> &connection)
{
	connection = new eConnection((iPlayableService*)this, m_event.connect(event));
	return 0;
}

RESULT eServiceMP3::start()
{
	ASSERT(m_state == stIdle);

	m_state = stRunning;
	if (m_gst_playbin)
	{
		int video = 0, audio = 0;
		numaraDecodoare(video, audio);
		eDebug("eServiceMP3::starting pipeline (video0 open %d, audio0 open %d times before the film)", video, audio);
		/* the start runs on the film thread: opening the file may wait for a disk that sleeps */
		cereStarea(false);
		if (!m_sourceinfo.is_streaming)
		{
			/* The marks and the last position belong to the films (a file with a picture), read on the film thread,
			   cuesPoll takes them. The music of the media player keeps no place and asks no question. */
			if (m_sourceinfo.is_video)
			{
				{
					std::lock_guard<std::mutex> l(m_fir->lacat);
					m_fir->citeste = true;
					m_fir->semnal.notify_all();
				}
				m_cues_timer->start(20, false);
			}
			m_start_timer->start(ASTEPTARE_PORNIRE_MS, true);
		}
	}

	m_event(this, evStart);
	/* without playbin nothing plays: the player is told now */
	if (!m_gst_playbin)
		m_event((iPlayableService*)this, evUser+16);

	return 0;
}

/* a change of state for the film thread (see FirFilm): PAUSED or PLAYING */
void eServiceMP3::cereStarea(bool pauza)
{
	if (!m_fir)
		return;
	std::lock_guard<std::mutex> l(m_fir->lacat);
	m_fir->schimba_starea = true;
	m_fir->pauza = pauza;
	m_fir->semnal.notify_all();
}

/* The position and the length of the film while it plays, once a second: stop() keeps the last position from these
   values and asks nothing of the sinks (a sink that hangs would hold the main loop before the bounded wait). During
   fast winding the position is the target of the winding. */
void eServiceMP3::positionTick()
{
	if (m_state != stRunning || !m_prerolled || m_currentTrickRatio)
		return;
	pts_t p = 0;
	realPlayPosition(p);
	if (m_last_length <= 0)
		getLength(p);
}

/* the cue file has been read (or found missing): the list is taken once, evCuesheetChanged lets the player ask about
   the last position (InfoBarCueSheetSupport) and the bar show the marks */
void eServiceMP3::cuesPoll()
{
	if (!m_fir || m_state != stRunning)
	{
		m_cues_timer->stop();
		return;
	}
	listaCues cues;
	{
		std::lock_guard<std::mutex> l(m_fir->lacat);
		if (!m_fir->citit)
			return;
		cues.swap(m_fir->cues);
	}
	m_cues_timer->stop();
	/* marks set from Python before the file was read are kept with the ones of the file */
	for (unsigned int i = 0; i < cues.size(); ++i)
		m_cue_entries.insert(cues[i]);
	m_cues_loaded = true;
	eDebug("eServiceMP3::cue file: %d entries", (int)cues.size());
	m_position_timer->start(1000, false);
	m_event((iPlayableService*)this, evCuesheetChanged);
}

/* a local film that never prerolled and never moved: said to the player like a missing format, the stop stays with it */
void eServiceMP3::startTimeout()
{
	if (m_state != stRunning || m_prerolled || !m_refuz.empty())
		return;
	pts_t pozitie = 0;
	if (realPlayPosition(pozitie) == 0 && pozitie > 0)
		return;
	eDebug("eServiceMP3::the film has not started after %d s", ASTEPTARE_PORNIRE_MS / 1000);
	refuza("pornire", "", "");
	m_event((iPlayableService*)this, evUser+16);
}

/* the reason of a refusal, kept for sUser+15; the first one stays */
void eServiceMP3::refuza(const char *fel, const std::string &capuri, const std::string &text)
{
	if (!m_refuz.empty())
		return;
	std::string t = text;
	std::replace(t.begin(), t.end(), '|', '/');
	std::replace(t.begin(), t.end(), '\n', ' ');
	std::string c = capuri;
	std::replace(c.begin(), c.end(), '|', '/');
	m_refuz = std::string(fel) + "|" + c + "|" + (m_n_video < 0 ? "?" : (m_n_video > 0 ? "1" : "0")) + "|" + t;
	eDebug("eServiceMP3::the film cannot be played: %s", m_refuz.c_str());
}

void eServiceMP3::sourceTimeout()
{
	eDebug("eServiceMP3::http source timeout! issuing eof...");
	m_event((iPlayableService*)this, evEOF);
}

RESULT eServiceMP3::stop()
{
	ASSERT(m_state != stIdle);

	if (m_state == stStopped)
		return -1;

	eDebug("eServiceMP3::stop %s: begin", m_ref.path.c_str());
	/* Nothing before the bounded wait asks the sinks or opens the decoder: the position and the length are the last
	   ones of the play (positionTick, or the target of the fast winding), and the sound muted by the winding comes
	   back only after the pipeline is stopped. */
	bool derulare = m_currentTrickRatio != 0;
	bool reda_sunetul = m_trick_muted;
	if (derulare)
		eDebug("eServiceMP3::fast winding ends at %lld ms (stop)", (long long)(m_trick_target / 90));
	m_currentTrickRatio = 0;
	m_pending_ratio = 0;
	m_trick_muted = false;
	m_trick_timer->stop();
	m_position_timer->stop();
	m_cues_timer->stop();
	m_start_timer->stop();
	m_subtitle_sync_timer->stop();
	m_external_timer->stop();

	/* the last position of a film (a file with a picture); written by the film thread after the stop */
	bool scrie = false;
	listaCues de_scris;
	if (m_gst_playbin && m_cues_loaded && m_sourceinfo.is_video && !m_sourceinfo.is_streaming)
	{
		pts_t pozitie = derulare ? m_trick_target : m_last_position, lungime = m_last_length;
		bool are_pozitie = pozitie >= 0, are_lungime = lungime > 0;
		std::multiset<std::pair<pts_t, unsigned int> > noi;
		pts_t ultima = -1;
		for (std::multiset<std::pair<pts_t, unsigned int> >::iterator i = m_cue_entries.begin(); i != m_cue_entries.end(); ++i)
		{
			if (i->second == 3)
				ultima = i->first;
			else
				noi.insert(*i);
		}
		bool sfarsit = m_watched_to_end || (are_pozitie && are_lungime && pozitie > lungime - MARGINE_RELUARE);
		pts_t pastrata = ultima;
		if (sfarsit)
			pastrata = -1;			/* seen to the end: the next time it starts from the beginning */
		else if (are_pozitie && are_lungime && pozitie >= MARGINE_RELUARE)
			pastrata = pozitie;		/* in the first minute the place kept before stays */
		if (pastrata >= 0)
			noi.insert(std::make_pair(pastrata, 3u));
		bool schimbat = m_cues_changed || pastrata != ultima;
		if (schimbat && ultima >= 0 && pastrata >= 0 && std::abs((long long)(pastrata - ultima)) < 90000 && !m_cues_changed)
			schimbat = false;		/* less than a second away: nothing to write */
		if (schimbat)
		{
			scrie = true;
			de_scris.assign(noi.begin(), noi.end());
		}
		m_cue_entries.swap(noi);
	}
	m_state = stStopped;

	if (!m_fir)
	{
		if (reda_sunetul)
			sunetulInapoi();
		return 0;
	}
	/* nothing of GStreamer reaches this service any more; the film thread stops the pipeline */
	m_poarta->inchide();
	std::unique_lock<std::mutex> l(m_fir->lacat);
	m_fir->salt = false;
	m_fir->schimba_starea = false;
	m_fir->scrie = scrie;
	m_fir->de_scris.swap(de_scris);
	m_fir->opreste = true;
	m_fir->semnal.notify_all();
	bool la_timp = m_fir->semnal.wait_for(l, std::chrono::milliseconds(ASTEPTARE_OPRIRE_MS), [this] { return m_fir->oprit; });
	l.unlock();
	if (!la_timp)
	{
		eDebug("eServiceMP3::stop: the pipeline is still stopping after %d ms, the film thread goes on with it",
			ASTEPTARE_OPRIRE_MS);
		scrieStareaFirelor();
	}
	if (reda_sunetul)
		sunetulInapoi();
	return 0;
}

/* the sound muted by fast winding comes back (the same way as the MUTE key); after a stop that ran past its time the
   old pipeline may still hold audio0, which the log of the stop shows */
void eServiceMP3::sunetulInapoi()
{
	eDVBVolumecontrol *volum = eDVBVolumecontrol::getInstance();
	if (volum && volum->isMuted())
	{
		volum->volumeUnMute();
		eDebug("eServiceMP3::the sound muted by fast winding is on again");
	}
}

RESULT eServiceMP3::setTarget(int target)
{
	return -1;
}

RESULT eServiceMP3::pause(ePtr<iPauseableService> &ptr)
{
	ptr=this;
	return 0;
}

RESULT eServiceMP3::setSlowMotion(int ratio)
{
	/* the decoder of the receiver gets the stream through the sinks at their own pace: a slower rate has no way to it
	   (the player does not offer slow motion for films, Screens/InfoBarGenerics.py, InfoBarSeek) */
	eDebug("eServiceMP3::setSlowMotion ratio=%d: not available for films", ratio);
	return -1;
}

RESULT eServiceMP3::setFastForward(int ratio)
{
	eDebug("eServiceMP3::setFastForward ratio=%i", ratio);
	if (!m_gst_playbin || m_state != stRunning)
		return -1;
	if (ratio == 0 || ratio == 1)
	{
		trickStop();
		return 0;
	}
	if (!(isCurrentlySeekable() & 2) || !m_fir)
		return -1;
	if (!m_prerolled)
	{
		/* asked before the pipeline is ready (>> in the first moments): the winding starts at the first ASYNC_DONE,
		   so the bar that already shows ">> 2x" tells the truth */
		m_pending_ratio = ratio;
		return 0;
	}
	/* winding back from the end: the place is kept again at the stop */
	if (ratio < 0)
		m_watched_to_end = false;
	if (!m_currentTrickRatio)
	{
		/* from the place of a jump still waiting on the film thread, else from the place shown */
		pts_t pozitie = -1;
		{
			std::lock_guard<std::mutex> l(m_fir->lacat);
			if (m_fir->salt && !m_fir->salt_derulare)
				pozitie = m_fir->salt_ns / 11111;
		}
		if (pozitie < 0 && realPlayPosition(pozitie) < 0)
			pozitie = 0;
		m_trick_target = pozitie;
		/* the pieces of sound between the jumps would be heard: muted while winding, unless it was muted already */
		eDVBVolumecontrol *volum = eDVBVolumecontrol::getInstance();
		if (volum && !volum->isMuted())
		{
			volum->volumeMute();
			m_trick_muted = true;
		}
		if (m_paused)
		{
			cereStarea(false);
			m_paused = false;
		}
		/* the subtitles of the old place go; the pages of the new one come after the winding */
		m_subtitle_pages.clear();
		m_subtitle_sync_timer->stop();
		m_external_timer->stop();
		m_external_shown.clear();
		if (m_subtitle_widget)
			m_subtitle_widget->clearPage();
		m_page_end_pts = -1;
	}
	m_currentTrickRatio = ratio;
	trickTick();
	if (m_currentTrickRatio)
		m_trick_timer->start(PAS_DERULARE_MS, false);
	return 0;
}

/* One step of fast winding: the target moves by ratio x PAS_DERULARE_MS and the film thread jumps to the key frame at
   or after it (forward) or at or before it (backward). The film plays on between the jumps; forward, while the key
   frame of the last jump is still at or after the target, it plays up to it without a new jump, so with key frames far
   apart the speed stays the one chosen. At the ends the player is told: evEOF near the end (it pauses there and asks
   seekTo(-1)), evSOF at the beginning (it plays on from 0). */
void eServiceMP3::trickTick()
{
	if (!m_currentTrickRatio || m_state != stRunning || !m_fir)
	{
		m_trick_timer->stop();
		return;
	}
	pts_t pas = (pts_t)m_currentTrickRatio * PAS_DERULARE_MS * 90;
	int fel = GST_SEEK_FLAG_FLUSH | GST_SEEK_FLAG_KEY_UNIT;
	if (m_currentTrickRatio > 0)
	{
		m_trick_target += pas;
		pts_t lungime = 0;
		if (getLength(lungime) == 0 && lungime > 0 && m_trick_target >= lungime - 2 * 90000)
		{
			m_trick_target = lungime > 90000 ? lungime - 90000 : 0;
			m_trick_timer->stop();
			m_event((iPlayableService*)this, evEOF);
			return;
		}
		pts_t acum = 0;
		if (realPlayPosition(acum) == 0 && acum >= m_trick_target)
			return;
		fel |= GST_SEEK_FLAG_SNAP_AFTER;
	}
	else
	{
		m_trick_target += pas;
		if (m_trick_target <= 0)
		{
			m_trick_target = 0;
			m_trick_timer->stop();
			m_event((iPlayableService*)this, evSOF);
			return;
		}
		fel |= GST_SEEK_FLAG_SNAP_BEFORE;
	}
	std::lock_guard<std::mutex> l(m_fir->lacat);
	m_fir->salt = true;
	m_fir->salt_derulare = true;
	m_fir->salt_ns = (gint64)m_trick_target * 11111LL;
	m_fir->salt_fel = fel;
	m_fir->semnal.notify_all();
}

/* back to normal play (or to a pause, which the caller sets): the sound comes back if the winding muted it */
void eServiceMP3::trickStop()
{
	m_pending_ratio = 0;
	if (!m_currentTrickRatio)
		return;
	eDebug("eServiceMP3::fast winding ends at %lld ms", (long long)(m_trick_target / 90));
	m_currentTrickRatio = 0;
	m_trick_timer->stop();
	/* a step of the winding still waiting on the film thread would jump after the play goes on; a plain jump asked
	   meanwhile (the restart, a number key) stays */
	if (m_fir)
	{
		std::lock_guard<std::mutex> l(m_fir->lacat);
		if (m_fir->salt && m_fir->salt_derulare)
			m_fir->salt = false;
	}
	if (m_trick_muted)
	{
		m_trick_muted = false;
		sunetulInapoi();
	}
	m_prev_decoder_time = -1;
	m_decoder_time_valid_state = 0;
	if (m_external_active >= 0)
		m_external_timer->start(50, true);
}

		// iPausableService
RESULT eServiceMP3::pause()
{
	if (!m_gst_playbin || m_state != stRunning)
		return -1;

	/* PLAYING -> PAUSED waits for the preroll lock of the sinks: on the film thread (see FirFilm) */
	trickStop();
	cereStarea(true);
	m_paused = true;
	m_subtitle_sync_timer->stop();
	/* the widget counts the time of a line on the wall clock: during a pause the line of the film stays */
	if (m_subtitle_widget && m_page_end_pts >= 0 && m_external_active < 0)
		m_subtitle_widget->setPageTimeout(3600 * 1000);

	return 0;
}

RESULT eServiceMP3::unpause()
{
	if (!m_gst_playbin || m_state != stRunning)
		return -1;

	trickStop();
	cereStarea(false);
	m_paused = false;
	if (!m_subtitle_pages.empty())
		m_subtitle_sync_timer->start(10, true);
	/* ...and after it, the line has the time it had left */
	pts_t pozitie = 0;
	if (m_subtitle_widget && m_page_end_pts >= 0 && m_external_active < 0 && getPlayPosition(pozitie) >= 0)
	{
		int ramas = (int)((m_page_end_pts - pozitie) / 90);
		if (ramas > 0)
			m_subtitle_widget->setPageTimeout(ramas);
		else
		{
			/* the line ended during the pause (with the translation on, its translation keeps its time) */
			m_subtitle_widget->endPage();
			m_page_end_pts = -1;
		}
	}

	return 0;
}

	/* iSeekableService */
RESULT eServiceMP3::seek(ePtr<iSeekableService> &ptr)
{
	ptr = this;
	return 0;
}

RESULT eServiceMP3::getLength(pts_t &pts)
{
	if (!m_gst_playbin)
		return -1;

	if (m_state != stRunning)
		return -1;

	GstFormat fmt = GST_FORMAT_TIME;
	gint64 len;
	
	if (!gst_element_query_duration(m_gst_playbin, fmt, &len))  // GST1.0: al doilea argument e acum GstFormat direct, nu pointer
		return -1;
		/* len is in nanoseconds. we have 90 000 pts per second. */
	
	pts = len / 11111;
	if (pts > 0)
		m_last_length = pts;
	return 0;
}

/* The jump goes to the film thread and the main loop goes on: a flushing seek waits for the streaming threads and may
   read the file on the thread that asks (an MKV without an index, an AVI without idx1, a slow stick). Only the last
   jump asked is kept; its failure is said in the log by the film thread. */
RESULT eServiceMP3::seekToImpl(pts_t to)
{
	if (!m_fir)
		return -1;
	std::lock_guard<std::mutex> l(m_fir->lacat);
	m_fir->salt = true;
	m_fir->salt_derulare = false;
	m_fir->salt_ns = (gint64)to * 11111LL;
	m_fir->salt_fel = GST_SEEK_FLAG_FLUSH;
	m_fir->semnal.notify_all();
	m_last_position = to;
	return 0;
}

RESULT eServiceMP3::seekTo(pts_t to)
{
	RESULT ret = -1;

	if (!m_gst_playbin || m_state != stRunning)
		return -1;
	if (to < 0)
	{
		/* -1: about one second before the end (where the player stops after winding forward to the end) */
		pts_t lungime = 0;
		if (getLength(lungime) < 0 || lungime <= 0)
			return -1;
		to = lungime > 90000 ? lungime - 90000 : 0;
	}
	else
		m_watched_to_end = false;
	if (m_currentTrickRatio)
	{
		/* during fast winding a jump moves the winding itself */
		m_trick_target = to;
		return 0;
	}
	if (!m_prerolled)
	{
		/* the pipeline is not ready yet (the resume question may come first): the jump waits for ASYNC_DONE */
		m_pending_seek = to;
		return 0;
	}

	{
		/* The seek runs without m_subs_to_pull_lock: a flushing seek waits for the streaming threads, and the text
		   branch may be inside gstCBsubtitleAvail waiting for that lock (the main loop stopped for good, seen in the
		   emulator right after a change of subtitle stream while paused). The flush empties the appsink, the pages
		   waiting here are dropped below; the lock only guards the counter. */
		if (!(ret = seekToImpl(to)))
		{
			m_subtitle_pages.clear();
			m_prev_decoder_time = -1;
			m_decoder_time_valid_state = 0;
			m_pgs.reset();
			{
				eSingleLocker l(m_subs_to_pull_lock);
				m_subs_to_pull = 0;
			}
			/* the line of the old position goes; the pages of the new one come from the demuxer (a line that began
			   before the new position comes only if the demuxer sends it again) */
			if (m_subtitle_widget)
				m_subtitle_widget->clearPage();
			m_page_end_pts = -1;
			/* a subtitle file follows the new position at once */
			if (m_external_active >= 0)
			{
				m_external_shown.clear();
				m_picture_index = -1;
				if (m_subtitle_widget)
					m_subtitle_widget->clearPage();
				m_external_timer->start(50, true);
			}
		}
	}

	return ret;
}


RESULT eServiceMP3::seekRelative(int direction, pts_t to)
{
	if (!m_gst_playbin || m_state != stRunning)
		return -1;

	pts_t ppos;
	if (!m_prerolled && m_pending_seek >= 0)
		ppos = m_pending_seek;
	else if (getPlayPosition(ppos) < 0)
		return -1;
	ppos += to * direction;
	if (ppos < 0)
		ppos = 0;
	seekTo(ppos);

	return 0;
}

RESULT eServiceMP3::getPlayPosition(pts_t &pts)
{
	/* during fast winding the bar follows the target, not the key frame shown a moment ago */
	if (m_currentTrickRatio && m_state == stRunning)
	{
		pts = m_trick_target;
		return 0;
	}
	return realPlayPosition(pts);
}

RESULT eServiceMP3::realPlayPosition(pts_t &pts)
{
	GstFormat fmt = GST_FORMAT_TIME;
	gint64 pos;
	GstElement *sink;
	pts = 0;

	if (!m_gst_playbin)
		return -1;
	if (m_state != stRunning)
		return -1;

	/* the sound sink when the sound plays, else the picture sink (a film whose sound track was left out) */
	sink = sinkFolosit(m_gst_playbin, "audio-sink");
	if (!sink)
		sink = sinkFolosit(m_gst_playbin, "video-sink");

	if (!sink)
		return -1;

	gchar *name = gst_element_get_name(sink);
	gboolean use_get_decoder_time = strstr(name, "dvbaudiosink") || strstr(name, "dvbvideosink");
	g_free(name);

	gboolean gasit = TRUE;
	if (use_get_decoder_time)
		g_signal_emit_by_name(sink, "get-decoder-time", &pos);
	else
		/* the position of the sound (or picture) sink, not of the whole playbin: a bin answers with the largest
		   position of its sinks, and the subtitle appsink (sync=FALSE) is always ahead, by as much as the demuxer
		   sends the text early (seconds); the subtitles then came too late and a seek seemed to stop the film */
		gasit = gst_element_query_position(sink, fmt, &pos);  // GST1.0: al doilea argument e acum GstFormat direct, nu pointer

	gst_object_unref(sink);

	if (!gasit) {
		eDebug("gst_element_query_position failed in getPlayPosition");
		return -1;
	}

	/* pos is in nanoseconds. we have 90 000 pts per second. */
	pts = pos / 11111;
	/* the last position of the play, kept for stop() (not the key frames shown during fast winding) */
	if (!m_currentTrickRatio && pts >= 0)
		m_last_position = pts;
	return 0;
}

RESULT eServiceMP3::setTrickmode(int trick)
{
		/* trickmode is not yet supported by our dvbmediasinks. */
	return -1;
}

RESULT eServiceMP3::isCurrentlySeekable()
{
	/* 1 = jumps, 2 = fast winding. A film file has both (winding by jumps between key frames, trickTick); a stream from
	   the network only the jumps, each of them waits for the network. */
	if (!m_gst_playbin || m_state != stRunning)
		return 0;
	if (m_sourceinfo.is_streaming)
		return 1;
	return 3;
}

RESULT eServiceMP3::cueSheet(ePtr<iCueSheet> &ptr)
{
	/* only the films (a file with a picture) keep marks and the last position; a song asks nothing */
	if (m_sourceinfo.is_streaming || !m_sourceinfo.is_video || !m_gst_playbin)
	{
		ptr = 0;
		return -1;
	}
	ptr = this;
	return 0;
}

PyObject *eServiceMP3::getCutList()
{
	ePyObject lista = PyList_New(0);
	for (std::multiset<std::pair<pts_t, unsigned int> >::iterator i = m_cue_entries.begin(); i != m_cue_entries.end(); ++i)
	{
		ePyObject tuplu = PyTuple_New(2);
		PyTuple_SET_ITEM(tuplu, 0, PyLong_FromLongLong(i->first));
		PyTuple_SET_ITEM(tuplu, 1, PyLong_FromLong(i->second));
		PyList_Append(lista, tuplu);
		Py_DECREF(tuplu);
	}
	return lista;
}

void eServiceMP3::setCutList(ePyObject list)
{
	if (!list || !PyList_Check(list))
		return;
	std::multiset<std::pair<pts_t, unsigned int> > noi;
	Py_ssize_t n = PyList_Size(list);
	for (Py_ssize_t i = 0; i < n && noi.size() < 10000; ++i)
	{
		PyObject *e = PyList_GET_ITEM(list, i);
		if (!PyTuple_Check(e) || PyTuple_Size(e) != 2 || !PyLong_Check(PyTuple_GET_ITEM(e, 0)) ||
				!PyLong_Check(PyTuple_GET_ITEM(e, 1)))
			continue;
		long long unde = PyLong_AsLongLong(PyTuple_GET_ITEM(e, 0));
		long ce = PyLong_AsLong(PyTuple_GET_ITEM(e, 1));
		if (PyErr_Occurred())
		{
			PyErr_Clear();
			continue;
		}
		if (unde < 0 || ce < 0 || ce > 3)
			continue;
		/* START and STOP of the cut editor (0, 1) are not kept: a film always plays whole (setCutListEnable) */
		if (ce < 2)
			continue;
		noi.insert(std::make_pair((pts_t)unde, (unsigned int)ce));
	}
	m_cue_entries.swap(noi);
	m_cues_changed = true;
	m_event((iPlayableService*)this, evCuesheetChanged);
}

void eServiceMP3::setCutListEnable(int enable)
{
	/* the cut marks only show where the parts are; the film always plays whole */
}

RESULT eServiceMP3::info(ePtr<iServiceInformation>&i)
{
	i = this;
	return 0;
}

RESULT eServiceMP3::getName(std::string &name)
{
	std::string title = m_ref.getName();
	if (title.empty())
	{
		name = m_ref.path;
		/* a stream from the network: the parameters of the address (often an access token) stay off the screen */
		if (m_sourceinfo.is_streaming)
			name = name.substr(0, name.find_first_of("?#"));
		size_t n = name.rfind('/');
		if (n != std::string::npos)
			name = name.substr(n + 1);
	}
	else
		name = title;
	return 0;
}

int eServiceMP3::getInfo(int w)
{
	const gchar *tag = 0;

	switch (w)
	{
	case sServiceref: return m_ref;
	case sVideoHeight: return m_height;
	case sVideoWidth: return m_width;
	case sFrameRate: return m_framerate;
	case sProgressive: return m_progressive;
	case sGamma: return m_gamma;
	case sAspect: return m_aspect;
	case sTagTitle:
	case sTagArtist:
	case sTagAlbum:
	case sTagTitleSortname:
	case sTagArtistSortname:
	case sTagAlbumSortname:
	case sTagDate:
	case sTagComposer:
	case sTagGenre:
	case sTagComment:
	case sTagExtendedComment:
	case sTagLocation:
	case sTagHomepage:
	case sTagDescription:
	case sTagVersion:
	case sTagISRC:
	case sTagOrganization:
	case sTagCopyright:
	case sTagCopyrightURI:
	case sTagContact:
	case sTagLicense:
	case sTagLicenseURI:
	case sTagCodec:
	case sTagAudioCodec:
	case sTagVideoCodec:
	case sTagEncoder:
	case sTagLanguageCode:
	case sTagKeywords:
	case sTagChannelMode:
	case sUser+12:
	case sUser+15:
		return resIsString;
	case sTagTrackGain:
	case sTagTrackPeak:
	case sTagAlbumGain:
	case sTagAlbumPeak:
	case sTagReferenceLevel:
	case sTagBeatsPerMinute:
	case sTagImage:
	case sTagPreviewImage:
	case sTagAttachment:
		return resIsPyObject;
	case sTagTrackNumber:
		tag = GST_TAG_TRACK_NUMBER;
		break;
	case sTagTrackCount:
		tag = GST_TAG_TRACK_COUNT;
		break;
	case sTagAlbumVolumeNumber:
		tag = GST_TAG_ALBUM_VOLUME_NUMBER;
		break;
	case sTagAlbumVolumeCount:
		tag = GST_TAG_ALBUM_VOLUME_COUNT;
		break;
	case sTagBitrate:
		tag = GST_TAG_BITRATE;
		break;
	case sTagNominalBitrate:
		tag = GST_TAG_NOMINAL_BITRATE;
		break;
	case sTagMinimumBitrate:
		tag = GST_TAG_MINIMUM_BITRATE;
		break;
	case sTagMaximumBitrate:
		tag = GST_TAG_MAXIMUM_BITRATE;
		break;
	case sTagSerial:
		tag = GST_TAG_SERIAL;
		break;
	case sTagEncoderVersion:
		tag = GST_TAG_ENCODER_VERSION;
		break;
	case sTagCRC:
		tag = "has-crc";
		break;
	default:
		return resNA;
	}

	if (!m_stream_tags || !tag)
		return 0;
	
	guint value;
	if (gst_tag_list_get_uint(m_stream_tags, tag, &value))
		return (int) value;

	return 0;
}

std::string eServiceMP3::getInfoString(int w)
{
	if ( !m_stream_tags && w < sUser && w > 26 )
		return "";
	const gchar *tag = 0;
	switch (w)
	{
	case sTagTitle:
		tag = GST_TAG_TITLE;
		break;
	case sTagArtist:
		tag = GST_TAG_ARTIST;
		break;
	case sTagAlbum:
		tag = GST_TAG_ALBUM;
		break;
	case sTagTitleSortname:
		tag = GST_TAG_TITLE_SORTNAME;
		break;
	case sTagArtistSortname:
		tag = GST_TAG_ARTIST_SORTNAME;
		break;
	case sTagAlbumSortname:
		tag = GST_TAG_ALBUM_SORTNAME;
		break;
	case sTagDate:
		GDate *date;
		if (gst_tag_list_get_date(m_stream_tags, GST_TAG_DATE, &date))
		{
			gchar res[5];
 			g_date_strftime (res, sizeof(res), "%Y-%M-%D", date); 
			return (std::string)res;
		}
		break;
	case sTagComposer:
		tag = GST_TAG_COMPOSER;
		break;
	case sTagGenre:
		tag = GST_TAG_GENRE;
		break;
	case sTagComment:
		tag = GST_TAG_COMMENT;
		break;
	case sTagExtendedComment:
		tag = GST_TAG_EXTENDED_COMMENT;
		break;
	case sTagLocation:
		tag = GST_TAG_LOCATION;
		break;
	case sTagHomepage:
		tag = GST_TAG_HOMEPAGE;
		break;
	case sTagDescription:
		tag = GST_TAG_DESCRIPTION;
		break;
	case sTagVersion:
		tag = GST_TAG_VERSION;
		break;
	case sTagISRC:
		tag = GST_TAG_ISRC;
		break;
	case sTagOrganization:
		tag = GST_TAG_ORGANIZATION;
		break;
	case sTagCopyright:
		tag = GST_TAG_COPYRIGHT;
		break;
	case sTagCopyrightURI:
		tag = GST_TAG_COPYRIGHT_URI;
		break;
	case sTagContact:
		tag = GST_TAG_CONTACT;
		break;
	case sTagLicense:
		tag = GST_TAG_LICENSE;
		break;
	case sTagLicenseURI:
		tag = GST_TAG_LICENSE_URI;
		break;
	case sTagCodec:
		tag = GST_TAG_CODEC;
		break;
	case sTagAudioCodec:
		tag = GST_TAG_AUDIO_CODEC;
		break;
	case sTagVideoCodec:
		tag = GST_TAG_VIDEO_CODEC;
		break;
	case sTagEncoder:
		tag = GST_TAG_ENCODER;
		break;
	case sTagLanguageCode:
		tag = GST_TAG_LANGUAGE_CODE;
		break;
	case sTagKeywords:
		tag = GST_TAG_KEYWORDS;
		break;
	case sTagChannelMode:
		tag = "channel-mode";
		break;
	case sUser+12:
		return m_errorInfo.error_message;
	case sUser+15:
		return m_refuz;
	default:
		return "";
	}
	if ( !tag || !m_stream_tags )
		return "";
	gchar *value;
	if (gst_tag_list_get_string(m_stream_tags, tag, &value))
	{
		std::string res = value;
		g_free(value);
		return res;
	}
	return "";
}

PyObject *eServiceMP3::getInfoObject(int w)
{
	const gchar *tag = 0;
	bool isBuffer = false;
	switch (w)
	{
		case sTagTrackGain:
			tag = GST_TAG_TRACK_GAIN;
			break;
		case sTagTrackPeak:
			tag = GST_TAG_TRACK_PEAK;
			break;
		case sTagAlbumGain:
			tag = GST_TAG_ALBUM_GAIN;
			break;
		case sTagAlbumPeak:
			tag = GST_TAG_ALBUM_PEAK;
			break;
		case sTagReferenceLevel:
			tag = GST_TAG_REFERENCE_LEVEL;
			break;
		case sTagBeatsPerMinute:
			tag = GST_TAG_BEATS_PER_MINUTE;
			break;
		case sTagImage:
			tag = GST_TAG_IMAGE;
			isBuffer = true;
			break;
		case sTagPreviewImage:
			tag = GST_TAG_PREVIEW_IMAGE;
			isBuffer = true;
			break;
		case sTagAttachment:
			tag = GST_TAG_ATTACHMENT;
			isBuffer = true;
			break;
		default:
			break;
	}

	/* an information this player does not have (the screens ask for every kind of service), or no tags yet: no
	   GStreamer call with a NULL tag or list (each one was a GStreamer-CRITICAL line in the log) */
	if ( !tag )
		Py_RETURN_NONE;
	if ( !m_stream_tags )
	{
		if ( isBuffer )
			Py_RETURN_NONE;
		return PyFloat_FromDouble(0.0);
	}

	if ( isBuffer )
	{
		const GValue *gv_buffer = gst_tag_list_get_value_index(m_stream_tags, tag, 0);
		if ( gv_buffer )
		{
			GstBuffer *buffer;
			buffer = gst_value_get_buffer (gv_buffer);
			// GST1.0: GST_BUFFER_DATA/SIZE (macro-uri directe pe pointer) au disparut -- bufferul
			// se acceseaza acum prin gst_buffer_map/GstMapInfo. PyBuffer_FromMemory era API Python 2
			// (nu exista in Python 3.13, la care a fost adus restul depozitului) -- inlocuit cu
			// PyBytes_FromStringAndSize (copiaza datele): o vedere fara copiere (PyMemoryView) ar
			// ramane agatata dupa gst_buffer_unmap de mai jos, iar bufferul GStreamer nu poate ramane
			// mapat pe durata de viata a obiectului Python -- copierea e mai sigura pentru date de tag
			// (coperta/atasament), mici si rar cerute, nu date de flux pe calea fierbinte.
			GstMapInfo map;
			if (!gst_buffer_map(buffer, &map, GST_MAP_READ))
				return 0;
			PyObject *rezultat = PyBytes_FromStringAndSize((const char*)map.data, map.size);
			gst_buffer_unmap(buffer, &map);
			return rezultat;
		}
	}
	else
	{
		gdouble value = 0.0;
		gst_tag_list_get_double(m_stream_tags, tag, &value);
		return PyFloat_FromDouble(value);
	}

	return 0;
}

RESULT eServiceMP3::audioChannel(ePtr<iAudioChannelSelection> &ptr)
{
	ptr = this;
	return 0;
}

RESULT eServiceMP3::audioTracks(ePtr<iAudioTrackSelection> &ptr)
{
	ptr = this;
	return 0;
}

RESULT eServiceMP3::subtitle(ePtr<iSubtitleOutput> &ptr)
{
	ptr = this;
	return 0;
}

RESULT eServiceMP3::audioDelay(ePtr<iAudioDelay> &ptr)
{
	ptr = this;
	return 0;
}

int eServiceMP3::getNumberOfTracks()
{
 	return m_audioStreams.size();
}

int eServiceMP3::getCurrentTrack()
{
	if (m_currentAudioStream == -1)
		g_object_get (G_OBJECT (m_gst_playbin), "current-audio", &m_currentAudioStream, NULL);
	return m_currentAudioStream;
}

RESULT eServiceMP3::selectTrack(unsigned int i)
{
	pts_t ppos;
	getPlayPosition(ppos);
	ppos -= 90000;
	if (ppos < 0)
		ppos = 0;

	int ret = selectAudioStream(i);
	if (!ret) {
		/* flush */
		seekTo(ppos);
	}

	return ret;
}

int eServiceMP3::selectAudioStream(int i)
{
	int current_audio;
	g_object_set (G_OBJECT (m_gst_playbin), "current-audio", i, NULL);
	g_object_get (G_OBJECT (m_gst_playbin), "current-audio", &current_audio, NULL);
	if ( current_audio == i )
	{
		eDebug ("eServiceMP3::switched to audio stream %i", current_audio);
		m_currentAudioStream = i;
		return 0;
	}
	return -1;
}

int eServiceMP3::getCurrentChannel()
{
	return STEREO;
}

RESULT eServiceMP3::selectChannel(int i)
{
	eDebug("eServiceMP3::selectChannel(%i)",i);
	return 0;
}

RESULT eServiceMP3::getTrackInfo(struct iAudioTrackInfo &info, unsigned int i)
{
 	if (i >= m_audioStreams.size())
		return -2;
	info.m_description = m_audioStreams[i].codec;
/*	if (m_audioStreams[i].type == atMPEG)
		info.m_description = "MPEG";
	else if (m_audioStreams[i].type == atMP3)
		info.m_description = "MP3";
	else if (m_audioStreams[i].type == atAC3)
		info.m_description = "AC3";
	else if (m_audioStreams[i].type == atAAC)
		info.m_description = "AAC";
	else if (m_audioStreams[i].type == atDTS)
		info.m_description = "DTS";
	else if (m_audioStreams[i].type == atPCM)
		info.m_description = "PCM";
	else if (m_audioStreams[i].type == atOGG)
		info.m_description = "OGG";
	else if (m_audioStreams[i].type == atFLAC)
		info.m_description = "FLAC";
	else
		info.m_description = "???";*/
	if (info.m_language.empty())
		info.m_language = m_audioStreams[i].language_code;
	return 0;
}

/* A Matroska subtitle track unknown to matroskademux 1.28 comes as application/x-subtitle-unknown, without its codec
   ID, with the CodecPrivate (if any) as codec_data. WebVTT is read as text: D_WEBVTT/SUBTITLES (the WebM form, written
   by the usual tools without CodecPrivate) and S_TEXT/WEBVTT (the Matroska form, with the "WEBVTT" header as
   CodecPrivate; *forma_matroska = true). DVB (S_DVBSUB: a CodecPrivate of 5 bytes, the two page ids and the subtitling
   type) and every other CodecPrivate give stUnknown: the track is not listed and its buffers are dropped. A track
   without CodecPrivate that is not text after all is caught by textWebVtt (valid UTF-8 without control characters). */
static subtype_t felNecunoscut(const GstStructure *str, bool *forma_matroska = NULL)
{
	if (forma_matroska)
		*forma_matroska = false;
	const GValue *cd = str ? gst_structure_get_value(str, "codec_data") : NULL;
	if (!cd || !GST_VALUE_HOLDS_BUFFER(cd))
		return stWebVTT;
	subtype_t tip = stUnknown;
	GstBuffer *b = gst_value_get_buffer(cd);
	GstMapInfo m;
	if (b && gst_buffer_map(b, &m, GST_MAP_READ))
	{
		const char *p = (const char*)m.data;
		size_t n = m.size;
		if (n >= 3 && !memcmp(p, "\xEF\xBB\xBF", 3))
		{
			p += 3;
			n -= 3;
		}
		if (n >= 6 && !memcmp(p, "WEBVTT", 6))
		{
			tip = stWebVTT;
			if (forma_matroska)
				*forma_matroska = true;
		}
		else
			eDebug("[eServiceMP3] unknown subtitle track with %d bytes of codec data (DVB has 5): not listed", (int)m.size);
		gst_buffer_unmap(b, &m);
	}
	return tip;
}

subtype_t getSubtitleType(GstPad* pad, gchar *g_codec=NULL)
{
	subtype_t type = stUnknown;
	GstCaps* caps = pad ? gst_pad_get_current_caps(pad) : NULL;  /* GST1.0: gst_pad_get_negotiated_caps -> gst_pad_get_current_caps */

	if ( caps )
	{
		GstStructure* str = gst_caps_get_structure(caps, 0);
		const gchar *g_type = gst_structure_get_name(str);
		eDebug("getSubtitleType::subtitle probe caps type=%s", g_type);

		/* GStreamer 1.x names: every text stream (SRT, SSA/ASS through ssaparse, tx3g, WebVTT, GAB2 in AVI) comes as
		   text/x-raw with format utf8 or pango-markup; the list calls it "Text" (stPlainText), the label says where
		   it comes from, not the internal form */
		if ( !strcmp(g_type, "text/x-raw") )
			type = stPlainText;
		else if ( !strcmp(g_type, "subpicture/x-dvd") )
			type = stVOB;
		else if ( !strcmp(g_type, "subpicture/x-pgs") )
			type = stPGS;
		else if ( !strcmp(g_type, "application/x-subtitle-unknown") )
			type = felNecunoscut(str);
		else
			eDebug("getSubtitleType::unsupported subtitle caps %s (%s)", g_type, g_codec ? g_codec : "-");
		gst_caps_unref(caps);
	}
	else if ( g_codec )
	{
		eDebug("getSubtitleType::subtitle probe codec tag=%s", g_codec);
		if ( !strcmp(g_codec, "VOB") )
			type = stVOB;
		else if ( !strcmp(g_codec, "SubStation Alpha") || !strcmp(g_codec, "SSA") )
			type = stSSA;
		else if ( !strcmp(g_codec, "ASS") )
			type = stASS;
		else if ( !strcmp(g_codec, "UTF-8 plain text") )
			type = stPlainText;
		else
			eDebug("getSubtitleType::unsupported subtitle codec %s", g_codec);
	}
	else
		eDebug("getSubtitleType::unidentifiable subtitle stream!");

	return type;
}

void eServiceMP3::gstBusCall(GstBus *bus, GstMessage *msg)
{
	if (!msg)
		return;
	gchar *sourceName;
	GstObject *source;
	source = GST_MESSAGE_SRC(msg);
	if (!GST_IS_OBJECT(source))
		return;
	sourceName = gst_object_get_name(source);
#if 0
	gchar *string;
	if (gst_message_get_structure(msg))
		string = gst_structure_to_string(gst_message_get_structure(msg));
	else
		string = g_strdup(GST_MESSAGE_TYPE_NAME(msg));
	eDebug("eTsRemoteSource::gst_message from %s: %s", sourceName, string);
	g_free(string);
#endif
	switch (GST_MESSAGE_TYPE (msg))
	{
		case GST_MESSAGE_EOS:
			/* seen to the end: the last position is not kept (a later jump back clears this) */
			m_watched_to_end = true;
			m_event((iPlayableService*)this, evEOF);
			break;
		case GST_MESSAGE_STATE_CHANGED:
		{
			if(GST_MESSAGE_SRC(msg) != GST_OBJECT(m_gst_playbin))
				break;

			GstState old_state, new_state;
			gst_message_parse_state_changed(msg, &old_state, &new_state, NULL);
		
			if(old_state == new_state)
				break;
	
			eDebug("eServiceMP3::state transition %s -> %s", gst_element_state_get_name(old_state), gst_element_state_get_name(new_state));
	
			GstStateChange transition = (GstStateChange)GST_STATE_TRANSITION(old_state, new_state);
	
			switch(transition)
			{
				case GST_STATE_CHANGE_NULL_TO_READY:
				{
				}	break;
				case GST_STATE_CHANGE_READY_TO_PAUSED:
				{
					GstElement *appsink = gst_bin_get_by_name(GST_BIN(m_gst_playbin), "subtitle_sink");
 					if (appsink)
 					{
 						g_object_set (G_OBJECT (appsink), "max-buffers", 2, NULL);
 						g_object_set (G_OBJECT (appsink), "sync", FALSE, NULL);
 						g_object_set (G_OBJECT (appsink), "emit-signals", TRUE, NULL);
 						eDebug("eServiceMP3::appsink properties set!");
 						gst_object_unref(appsink);
 					}
					setAC3Delay(ac3_delay);
					setPCMDelay(pcm_delay);
				}	break;
				case GST_STATE_CHANGE_PAUSED_TO_PLAYING:
				{
					if ( m_sourceinfo.is_streaming && m_streamingsrc_timeout )
						m_streamingsrc_timeout->stop();
				}	break;
				case GST_STATE_CHANGE_PLAYING_TO_PAUSED:
				{
				}	break;
				case GST_STATE_CHANGE_PAUSED_TO_READY:
				{
				}	break;
				case GST_STATE_CHANGE_READY_TO_NULL:
				{
				}	break;
				default:
					break;
			}
			break;
		}
		case GST_MESSAGE_ERROR:
		{
			/* Every error is told to the player once, with its reason in sUser+15: until now only a codec refused by a
			   sink was told, and a film whose pipeline failed (no demuxer for MPEG-PS, Theora decoded to pictures no
			   sink takes, a file that cannot be read) stayed black without a word. The events: evUser+10 / +11 a codec
			   refused by the sound / picture sink, evUser+12 a missing element (the text of the media player is in
			   sUser+12, set by the missing-plugin message), evUser+16 any other error. The text of GStreamer stays in
			   the log and in sUser+15, never in sUser+12. The pipeline is not stopped here: the player shows the
			   message and leaves, and eNavigation stops the service as for any other end. */
			gchar *debug = NULL;
			GError *err = NULL;
			gst_message_parse_error (msg, &err, &debug);
			eWarning("Gstreamer error: %s (%i) from %s", err->message, err->code, sourceName );
			const char *fel = "eroare";
			int eveniment = evUser+16;
			const std::string &lipsa = m_errorInfo.missing_codec;
			if ( err->domain == GST_STREAM_ERROR && err->code == GST_STREAM_ERROR_CODEC_NOT_FOUND )
			{
				if ( g_strrstr(sourceName, "videosink") )
				{
					fel = "video";
					eveniment = evUser+11;
				}
				else if ( g_strrstr(sourceName, "audiosink") )
				{
					fel = "sunet";
					eveniment = evUser+10;
				}
				else if ( lipsa.empty() )
					fel = "format";
				else
				{
					fel = "componenta";
					eveniment = evUser+12;
				}
			}
			/* a missing element that stopped the pipeline (not a track left out while the rest plays, "lipsa") */
			else if ( !lipsa.empty() )
			{
				fel = "componenta";
				eveniment = evUser+12;
			}
			else if ( debug && strstr(debug, "not-negotiated") )
				fel = "negociere";
			else if ( err->domain == GST_STREAM_ERROR && (err->code == GST_STREAM_ERROR_TYPE_NOT_FOUND ||
					err->code == GST_STREAM_ERROR_WRONG_TYPE || err->code == GST_STREAM_ERROR_DEMUX ||
					err->code == GST_STREAM_ERROR_DECODE || err->code == GST_STREAM_ERROR_FORMAT) )
				fel = "format";
			else if ( err->domain == GST_RESOURCE_ERROR )
				fel = "fisier";
			g_free (debug);
			bool primul = m_refuz.empty();
			refuza(fel, m_capuri_lipsa.empty() ? lipsa : m_capuri_lipsa, err->message ? err->message : "");
			if ( primul )
			{
				m_start_timer->stop();
				m_event((iPlayableService*)this, eveniment);
			}
			g_error_free(err);
			break;
		}
		case GST_MESSAGE_INFO:
		{
			gchar *debug;
			GError *inf;
	
			gst_message_parse_info (msg, &inf, &debug);
			g_free (debug);
			if ( inf->domain == GST_STREAM_ERROR && inf->code == GST_STREAM_ERROR_DECODE )
			{
				if ( g_strrstr(sourceName, "videosink") )
					m_event((iPlayableService*)this, evUser+14);
			}
			g_error_free(inf);
			break;
		}
		case GST_MESSAGE_TAG:
		{
			GstTagList *tags, *result;
			gst_message_parse_tag(msg, &tags);
	
			result = gst_tag_list_merge(m_stream_tags, tags, GST_TAG_MERGE_REPLACE);
			if (result)
			{
				if (m_stream_tags)
					gst_tag_list_unref(m_stream_tags);
				m_stream_tags = result;
			}
	
			const GValue *gv_image = gst_tag_list_get_value_index(tags, GST_TAG_IMAGE, 0);
			if ( gv_image )
			{
				GstBuffer *buf_image;
				buf_image = gst_value_get_buffer (gv_image);
				int fd = open("/tmp/.id3coverart", O_CREAT|O_WRONLY|O_TRUNC, 0644);
				GstMapInfo map_image;
				int ret = -1;
				if (gst_buffer_map(buf_image, &map_image, GST_MAP_READ))
				{
					ret = write(fd, map_image.data, map_image.size);  // GST1.0: GST_BUFFER_DATA/SIZE -> gst_buffer_map/GstMapInfo
					gst_buffer_unmap(buf_image, &map_image);
				}
				close(fd);
				eDebug("eServiceMP3::/tmp/.id3coverart %d bytes written ", ret);
				m_event((iPlayableService*)this, evUser+13);
			}
			gst_tag_list_unref(tags);
			m_event((iPlayableService*)this, evUpdatedInfo);
			break;
		}
		case GST_MESSAGE_ASYNC_DONE:
		{
			if(GST_MESSAGE_SRC(msg) != GST_OBJECT(m_gst_playbin))
				break;

			bool primul = !m_prerolled;
			m_prerolled = true;
			m_start_timer->stop();
			/* the jumps of fast winding bring ASYNC_DONE too (with sinks that preroll): the streams stay the same */
			if ( !primul && m_currentTrickRatio )
				break;

			GstTagList *tags;
			gint i, n_video = 0, n_audio = 0, n_text = 0;

			g_object_get (m_gst_playbin, "n-video", &n_video, NULL);
			g_object_get (m_gst_playbin, "n-audio", &n_audio, NULL);
			g_object_get (m_gst_playbin, "n-text", &n_text, NULL);
			m_n_video = n_video;

			eDebug("eServiceMP3::async-done - %d video, %d audio, %d subtitle", n_video, n_audio, n_text);

			/* nothing that can be played: the player is told (the old stop() here left eNavigation with a stopped
			   service it still counted as running) */
			if ( n_video + n_audio <= 0 && m_refuz.empty() )
			{
				bool lipsa = !m_errorInfo.missing_codec.empty();
				refuza(lipsa ? "lipsa" : "nimic", m_capuri_lipsa, "");
				m_event((iPlayableService*)this, lipsa ? evUser+12 : evUser+16);
			}

			m_audioStreams.clear();
			m_subtitleStreams.clear();

			for (i = 0; i < n_audio; i++)
			{
				audioStream audio;
				gchar *g_codec, *g_lang;
				GstPad* pad = 0;
				g_signal_emit_by_name (m_gst_playbin, "get-audio-pad", i, &pad);
				GstCaps* caps = gst_pad_get_current_caps(pad);  /* GST1.0: gst_pad_get_negotiated_caps -> gst_pad_get_current_caps */
				if (!caps)
					continue;
				GstStructure* str = gst_caps_get_structure(caps, 0);
				const gchar *g_type = gst_structure_get_name(str);
				audio.type = gstCheckAudioPad(str);
				g_codec = g_strdup(g_type);
				g_lang = g_strdup_printf ("und");
				g_signal_emit_by_name (m_gst_playbin, "get-audio-tags", i, &tags);
				if ( tags && GST_IS_TAG_LIST(tags)  /* GST1.0: gst_is_tag_list -> macro GST_IS_TAG_LIST */ )
				{
					gst_tag_list_get_string(tags, GST_TAG_AUDIO_CODEC, &g_codec);
					gst_tag_list_get_string(tags, GST_TAG_LANGUAGE_CODE, &g_lang);
					gst_tag_list_unref(tags);
				}
				audio.language_code = std::string(g_lang);
				audio.codec = std::string(g_codec);
				eDebug("eServiceMP3::audio stream=%i codec=%s language=%s", i, g_codec, g_lang);
				m_audioStreams.push_back(audio);
				g_free (g_lang);
				g_free (g_codec);
				gst_caps_unref(caps);
			}

			for (i = 0; i < n_text; i++)
			{
				gchar *g_codec = NULL, *g_lang = NULL;
				g_signal_emit_by_name (m_gst_playbin, "get-text-tags", i, &tags);
				subtitleStream subs;
//				int ret;

				if ( tags && GST_IS_TAG_LIST(tags)  /* GST1.0: gst_is_tag_list -> macro GST_IS_TAG_LIST */ )
				{
					gst_tag_list_get_string(tags, GST_TAG_LANGUAGE_CODE, &g_lang);
					gst_tag_list_get_string(tags, GST_TAG_SUBTITLE_CODEC, &g_codec);
					gst_tag_list_unref(tags);
				}
				if ( !g_lang )
					g_lang = g_strdup("und");

				subs.language_code = std::string(g_lang);
				eDebug("eServiceMP3::subtitle stream=%i language=%s codec=%s", i, g_lang, g_codec ? g_codec : "-");
				
				GstPad* pad = 0;
				g_signal_emit_by_name (m_gst_playbin, "get-text-pad", i, &pad);
				/* ASYNC_DONE comes again after every seek: the caps watch is put on a pad only once */
				if ( pad && !g_object_get_data(G_OBJECT (pad), "hds-caps-watch") )
				{
					g_object_set_data(G_OBJECT (pad), "hds-caps-watch", GINT_TO_POINTER(1));
					g_signal_connect (G_OBJECT (pad), "notify::caps", G_CALLBACK (gstTextpadHasCAPS), m_poarta.get());
				}
				subs.type = getSubtitleType(pad, g_codec);
				if ( pad )
					gst_object_unref(pad);

				m_subtitleStreams.push_back(subs);
				g_free (g_lang);
				g_free (g_codec);
			}
			m_event((iPlayableService*)this, evUpdatedEventInfo);
			/* the Python side (InfoBarSubtitleSupport, Components/HdsPisteLimbi.py) chooses the subtitle on
			   evUpdatedInfo; the stream list is complete only now */
			m_event((iPlayableService*)this, evUpdatedInfo);

			/* a stream without a way to the decoder: the picture when no picture plays, the sound when no sound track
			   plays (a missing codec of a track that is not chosen, a second audio track in TrueHD for one, is not told) */
			if ( primul && m_errorInfo.missing_codec != "" && m_refuz.empty() )
			{
				if ( ( m_errorInfo.missing_codec.find("video/") == 0 && n_video == 0 ) ||
						( m_errorInfo.missing_codec.find("audio/") == 0 && getNumberOfTracks() == 0 ) )
				{
					refuza("lipsa", m_capuri_lipsa, "");
					m_event((iPlayableService*)this, evUser+12);
				}
			}
			/* a jump asked before the pipeline was ready (the resume question, a number key) */
			if ( primul && m_pending_seek >= 0 && m_state == stRunning )
			{
				pts_t p = m_pending_seek;
				m_pending_seek = -1;
				seekTo(p);
			}
			/* fast winding asked before the pipeline was ready (from the place of that jump, if one was asked) */
			if ( primul && m_pending_ratio && m_state == stRunning )
			{
				int r = m_pending_ratio;
				m_pending_ratio = 0;
				setFastForward(r);
			}
			break;
		}
		case GST_MESSAGE_ELEMENT:
		{
			if (const GstStructure *msgstruct = gst_message_get_structure(msg))
			{
				if ( gst_is_missing_plugin_message(msg) )
				{
					GstCaps *caps;
					gst_structure_get (msgstruct, "detail", GST_TYPE_CAPS, &caps, NULL);
					gchar *text_caps = gst_caps_to_string(caps);
					std::string codec = text_caps ? text_caps : "";
					g_free(text_caps);
					gchar *description = gst_missing_plugin_message_get_description(msg);
					/* a subtitle stream without a reader (WebVTT or DVB in MKV, TTML in MP4) is skipped by playbin and the
					   film plays on: it is not a missing codec for the error message of the player */
					bool subtitrare = codec.find("application/x-subtitle") == 0 || codec.find("subpicture/") == 0 ||
						codec.find("text/") == 0 || codec.find("application/ttml") == 0 || codec.find("application/x-ass") == 0 ||
						codec.find("application/x-ssa") == 0;
					if ( description && subtitrare )
						eDebug("eServiceMP3::no reader for the subtitle stream %s, skipped", codec.c_str());
					else if ( description )
					{
						eDebug("eServiceMP3::m_errorInfo.missing_codec = %s", codec.c_str());
						m_errorInfo.error_message = "GStreamer plugin " + (std::string)description + " not available!\n";
						m_errorInfo.missing_codec = codec.substr(0,(codec.find_first_of(',')));
						/* the whole type for the message (the fourcc of an unknown AVI stream, systemstream of MPEG-PS) */
						m_capuri_lipsa = codec.substr(0, 200);
					}
					g_free(description);
					gst_caps_unref(caps);
				}
				else
				{
					const gchar *eventname = gst_structure_get_name(msgstruct);
					if ( eventname )
					{
						if (!strcmp(eventname, "eventSizeChanged") || !strcmp(eventname, "eventSizeAvail"))
						{
							gst_structure_get_int (msgstruct, "aspect_ratio", &m_aspect);
							gst_structure_get_int (msgstruct, "width", &m_width);
							gst_structure_get_int (msgstruct, "height", &m_height);
							if (strstr(eventname, "Changed"))
								m_event((iPlayableService*)this, evVideoSizeChanged);
						}
						else if (!strcmp(eventname, "eventFrameRateChanged") || !strcmp(eventname, "eventFrameRateAvail"))
						{
							gst_structure_get_int (msgstruct, "frame_rate", &m_framerate);
							if (strstr(eventname, "Changed"))
								m_event((iPlayableService*)this, evVideoFramerateChanged);
						}
						else if (!strcmp(eventname, "eventProgressiveChanged") || !strcmp(eventname, "eventProgressiveAvail"))
						{
							gst_structure_get_int (msgstruct, "progressive", &m_progressive);
							if (strstr(eventname, "Changed"))
								m_event((iPlayableService*)this, evVideoProgressiveChanged);
						}
						else if (!strcmp(eventname, "eventGammaChanged"))
						{
							/* dupa enigma2 (GPLv2): dvbmediasink-ul nou
							   (a147a35, instalat pe receptor) trimite evenimentul 17 al decodorului ca "eventGammaChanged",
							   cu aceleasi valori: 0 SDR, 1 HDR, 2 HDR10, 3 HLG */
							gst_structure_get_int (msgstruct, "gamma", &m_gamma);
							m_event((iPlayableService*)this, evVideoGammaChanged);
						}
					}
				}
			}
			break;
		}
		case GST_MESSAGE_BUFFERING:
		{
			GstBufferingMode mode;
			gst_message_parse_buffering(msg, &(m_bufferInfo.bufferPercent));
			gst_message_parse_buffering_stats(msg, &mode, &(m_bufferInfo.avgInRate), &(m_bufferInfo.avgOutRate), &(m_bufferInfo.bufferingLeft));
			m_event((iPlayableService*)this, evBuffering);
			break;
		}
		case GST_MESSAGE_STREAM_STATUS:
		{
			GstStreamStatusType type;
			GstElement *owner;
			gst_message_parse_stream_status (msg, &type, &owner);
			if ( type == GST_STREAM_STATUS_TYPE_CREATE && m_sourceinfo.is_streaming )
			{
				if ( GST_IS_PAD(source) )
					owner = gst_pad_get_parent_element(GST_PAD(source));
				else if ( GST_IS_ELEMENT(source) )
					owner = GST_ELEMENT(source);
				else
					owner = 0;
				if ( owner )
				{
					GstElementFactory *factory = gst_element_get_factory(GST_ELEMENT(owner));
					const gchar *name = gst_plugin_feature_get_name(GST_PLUGIN_FEATURE(factory));
					if (!strcmp(name, "souphttpsrc"))
					{
						m_streamingsrc_timeout->start(HTTP_TIMEOUT*1000, true);
						g_object_set (G_OBJECT (owner), "timeout", HTTP_TIMEOUT, NULL);
						eDebug("eServiceMP3::GST_STREAM_STATUS_TYPE_CREATE -> setting timeout on %s to %is", name, HTTP_TIMEOUT);
					}
					
				}
				if ( GST_IS_PAD(source) )
					gst_object_unref(owner);
			}
			break;
		}
		default:
			break;
	}
	g_free (sourceName);
}

GstBusSyncReply eServiceMP3::gstBusSyncHandler(GstBus *bus, GstMessage *message, gpointer user_data)
{
	Poarta *poarta = (Poarta*)user_data;
	std::lock_guard<std::mutex> l(poarta->lacat);
	if (poarta->serviciu)
		poarta->serviciu->m_pump.send(Message(1));
		/* wake */
	return GST_BUS_PASS;
}

void eServiceMP3::gstHTTPSourceSetAgent(GObject *object, GParamSpec *unused, gpointer user_data)
{
	Poarta *poarta = (Poarta*)user_data;
	std::lock_guard<std::mutex> l(poarta->lacat);
	eServiceMP3 *_this = poarta->serviciu;
	if (!_this)
		return;
	GstElement *source = NULL;
	g_object_get(_this->m_gst_playbin, "source", &source, NULL);
	if (!source)
		return;
	/* only the network sources have a user agent */
	if (g_object_class_find_property(G_OBJECT_GET_CLASS(source), "user-agent"))
		g_object_set (G_OBJECT (source), "user-agent", _this->m_useragent.c_str(), NULL);
	gst_object_unref(source);
}

audiotype_t eServiceMP3::gstCheckAudioPad(GstStructure* structure)
{
	if (!structure)
		return atUnknown;

	if ( gst_structure_has_name (structure, "audio/mpeg"))
	{
		gint mpegversion, layer = -1;
		if (!gst_structure_get_int (structure, "mpegversion", &mpegversion))
			return atUnknown;

		switch (mpegversion) {
			case 1:
				{
					gst_structure_get_int (structure, "layer", &layer);
					if ( layer == 3 )
						return atMP3;
					else
						return atMPEG;
					break;
				}
			case 2:
				return atAAC;
			case 4:
				return atAAC;
			default:
				return atUnknown;
		}
	}

	else if ( gst_structure_has_name (structure, "audio/x-ac3") || gst_structure_has_name (structure, "audio/ac3") )
		return atAC3;
	else if ( gst_structure_has_name (structure, "audio/x-dts") || gst_structure_has_name (structure, "audio/dts") )
		return atDTS;
	else if ( gst_structure_has_name (structure, "audio/x-raw-int") )
		return atPCM;

	return atUnknown;
}

void eServiceMP3::gstPoll(const Message &msg)
{
	/* after stop() the pipeline belongs to the film thread: what is still queued is only dropped */
	bool viu = m_state != stStopped && m_gst_playbin;
	if (msg.type == 1)
	{
		if (!m_gst_playbin)
			return;
		GstBus *bus = gst_pipeline_get_bus (GST_PIPELINE (m_gst_playbin));
		GstMessage *message;
		while ((message = gst_bus_pop(bus)))
		{
			if (viu && m_state != stStopped)
				gstBusCall(bus, message);
			gst_message_unref (message);
		}
		gst_object_unref(bus);
	}
	else if (msg.type == 2)
	{
		if (viu)
			pullSubtitle();
	}
	else if (msg.type == 3)
	{
		if (viu)
			gstTextpadHasCAPS_synced(msg.d.pad);
		else
			gst_object_unref(msg.d.pad);
	}
	else
		eDebug("gstPoll unhandled Message %d\n", msg.type);
}

eAutoInitPtr<eServiceFactoryMP3> init_eServiceFactoryMP3(eAutoInitNumbers::service+1, "eServiceFactoryMP3");

GstFlowReturn eServiceMP3::gstCBsubtitleAvail(GstElement *appsink, gpointer user_data)
{
	// GST1.0: "new-sample" (formerly "new-buffer") returns a GstFlowReturn; pullSubtitle() takes the samples itself
	Poarta *poarta = (Poarta*)user_data;
	std::lock_guard<std::mutex> lp(poarta->lacat);
	eServiceMP3 *_this = poarta->serviciu;
	if (!_this)
		return GST_FLOW_OK;
	eSingleLocker l(_this->m_subs_to_pull_lock);
	++_this->m_subs_to_pull;
	_this->m_pump.send(Message(2));
	return GST_FLOW_OK;
}

void eServiceMP3::gstTextpadHasCAPS(GstPad *pad, GParamSpec * unused, gpointer user_data)
{
	Poarta *poarta = (Poarta*)user_data;
	std::lock_guard<std::mutex> l(poarta->lacat);
	if (!poarta->serviciu)
		return;

	gst_object_ref (pad);

	poarta->serviciu->m_pump.send(Message(3, pad));
}

// after messagepump
void eServiceMP3::gstTextpadHasCAPS_synced(GstPad *pad)
{
	GstCaps *caps;

	g_object_get (G_OBJECT (pad), "caps", &caps, NULL);

	if (caps)
	{
		gchar *text = gst_caps_to_string(caps);
		eDebug("gstTextpadHasCAPS:: signal::caps = %s", text);
		g_free(text);
	}

	if (caps)
	{
		subtitleStream subs;

//		eDebug("gstGhostpadHasCAPS_synced %p %d", pad, m_subtitleStreams.size());

		if (m_currentSubtitleStream >= 0 && m_currentSubtitleStream < (int)m_subtitleStreams.size())
			subs = m_subtitleStreams[m_currentSubtitleStream];
		else {
			subs.type = stUnknown;
			subs.pad = pad;
		}

		if ( subs.type == stUnknown )
		{
			GstTagList *tags;
//			eDebug("gstGhostpadHasCAPS::m_subtitleStreams[%i].type == stUnknown...", m_currentSubtitleStream);

			gchar *g_lang;
			g_signal_emit_by_name (m_gst_playbin, "get-text-tags", m_currentSubtitleStream, &tags);

			g_lang = NULL;
			if ( tags && GST_IS_TAG_LIST(tags)  /* GST1.0: gst_is_tag_list -> macro GST_IS_TAG_LIST */ )
			{
				gst_tag_list_get_string(tags, GST_TAG_LANGUAGE_CODE, &g_lang);
				gst_tag_list_unref(tags);
			}
			if ( !g_lang )
				g_lang = g_strdup("und");

			subs.language_code = std::string(g_lang);
			subs.type = getSubtitleType(pad);

			if (m_currentSubtitleStream >= 0 && m_currentSubtitleStream < (int)m_subtitleStreams.size())
				m_subtitleStreams[m_currentSubtitleStream] = subs;
			else if (m_subtitleStreams.empty())
				m_subtitleStreams.push_back(subs);

			g_free (g_lang);
		}

//		eDebug("gstGhostpadHasCAPS:: m_gst_prev_subtitle_caps=%s equal=%i",gst_caps_to_string(m_gst_prev_subtitle_caps),gst_caps_is_equal(m_gst_prev_subtitle_caps, caps));

		gst_caps_unref (caps);
	}

	gst_object_unref (pad);
}

/* A text line of a subtitle: the position codes {\an7}, {\an8}, {\an9} (ASS, also used in SRT files) put the lines at
   the top of the picture; every other {\...} code is removed, as ssaparse does. */
static std::string faraCoduriAss(const std::string &text, bool &sus)
{
	std::string rezultat;
	rezultat.reserve(text.size());
	size_t i = 0, n = text.size();
	while (i < n)
	{
		if (text[i] == '{' && i + 1 < n && text[i + 1] == '\\')
		{
			size_t sfarsit = text.find('}', i);
			if (sfarsit != std::string::npos && sfarsit - i < 256)
			{
				std::string cod = text.substr(i, sfarsit - i + 1);
				if (cod.find("\\an7") != std::string::npos || cod.find("\\an8") != std::string::npos ||
						cod.find("\\an9") != std::string::npos)
					sus = true;
				i = sfarsit + 1;
				continue;
			}
		}
		rezultat += text[i++];
	}
	return rezultat;
}

/* valid UTF-8 without control characters other than the newline and the tab */
static bool textCurat(const std::string &t)
{
	size_t i = 0, n = t.size();
	while (i < n)
	{
		unsigned char c = (unsigned char)t[i];
		if (c < 0x80)
		{
			if ((c < 0x20 && c != '\n' && c != '\t') || c == 0x7F)
				return false;
			++i;
			continue;
		}
		int urmatori = (c & 0xE0) == 0xC0 ? 1 : (c & 0xF0) == 0xE0 ? 2 : (c & 0xF8) == 0xF0 ? 3 : -1;
		if (urmatori < 0 || c == 0xC0 || c == 0xC1 || i + urmatori >= n)
			return false;
		for (int k = 1; k <= urmatori; ++k)
			if (((unsigned char)t[i + k] & 0xC0) != 0x80)
				return false;
		i += urmatori + 1;
	}
	return true;
}

/* One WebVTT cue from a Matroska track (see felNecunoscut): "identifier\nsettings\npayload" in the WebM form, only the
   payload in the Matroska form (its settings are in BlockAdditions, which the demuxer does not give). The setting
   "line:" puts the cue at the top when it counts from the top (a number >= 0, or a percent under 50). The timestamp
   tags (<00:01.000>) and &nbsp; &lrm; &rlm; are taken out here; the other tags (<c>, <v>, <lang>, <ruby>) and &amp;
   &lt; &gt; are taken out by the widget, which keeps <i> and <b>. "" = nothing to show (an empty cue, or not text). */
static std::string textWebVtt(const std::string &bloc, bool forma_matroska, bool &sus)
{
	std::string text = bloc;
	if (!forma_matroska)
	{
		size_t a = text.find('\n');
		size_t b = a == std::string::npos ? std::string::npos : text.find('\n', a + 1);
		if (b == std::string::npos)
			return "";
		std::string setari = text.substr(a + 1, b - a - 1);
		size_t l = setari.find("line:");
		if (l != std::string::npos && (l == 0 || setari[l - 1] == ' ' || setari[l - 1] == '\t'))
		{
			const char *v = setari.c_str() + l + 5;
			char *sf = NULL;
			double x = strtod(v, &sf);
			if (sf && sf != v)
				sus = *sf == '%' ? x < 50 : x >= 0;
		}
		text = text.substr(b + 1);
	}
	std::string r;
	r.reserve(text.size());
	size_t i = 0, n = text.size();
	while (i < n)
	{
		if (text[i] == '<' && i + 1 < n && isdigit((unsigned char)text[i + 1]))
		{
			size_t k = text.find('>', i);
			if (k != std::string::npos && k - i < 32)
			{
				i = k + 1;
				continue;
			}
		}
		if (text[i] == '&')
		{
			if (!text.compare(i, 6, "&nbsp;"))
			{
				r += ' ';
				i += 6;
				continue;
			}
			if (!text.compare(i, 5, "&lrm;") || !text.compare(i, 5, "&rlm;"))
			{
				i += 5;
				continue;
			}
		}
		r += text[i++];
	}
	size_t inceput = r.find_first_not_of("\n ");
	if (inceput == std::string::npos)
		return "";
	size_t sfarsit = r.find_last_not_of("\n ");
	r = r.substr(inceput, sfarsit - inceput + 1);
	return textCurat(r) ? r : "";
}

void eServiceMP3::pullSubtitle()
{
	GstElement *sink;
	g_object_get (G_OBJECT (m_gst_playbin), "text-sink", &sink, NULL);

	if (sink)
	{
		/* Everything the appsink holds is taken, without waiting: "try-pull-sample" with a zero timeout returns at once
		   (NULL when nothing is queued, and at the end of the film), while "pull-sample" waited for the next sample and,
		   once the counter of signals had gone below zero (it is zeroed at a seek or a change of stream while signals
		   were still on their way), spun without end at the end of the film. The pages wait here until their time
		   (at most MAX_PAGINI), so the text branch never holds the demuxer back. While a subtitle file is shown, the
		   pages of the container stream are dropped at once. */
		static const unsigned int MAX_PAGINI = 32;
		bool arunca = m_external_active >= 0;
		while (arunca || m_subtitle_pages.size() < MAX_PAGINI)
		{
			GstBuffer *buffer = NULL;
			/* the type comes from the caps of the sample itself: after a change of stream a page of the old one can
			   still be here, and it must not be read as the new kind */
			subtype_t tip = stUnknown;
			bool webvtt_matroska = false;	/* a WebVTT cue in the Matroska form (only the payload) */
			{
				/* no m_subs_to_pull_lock around the appsink: the lock only guards the counter (see seekTo) */
				GstSample *sample = NULL;
				g_signal_emit_by_name (sink, "try-pull-sample", (GstClockTime)0, &sample);
				if (!sample)
				{
					eSingleLocker l(m_subs_to_pull_lock);
					m_subs_to_pull = 0;
					break;
				}
				{
					eSingleLocker l(m_subs_to_pull_lock);
					if (m_subs_to_pull > 0)
						--m_subs_to_pull;
				}
				/* the sample is owned: its buffer is kept on its own (gst_buffer_ref), unref'd below */
				buffer = gst_buffer_ref(gst_sample_get_buffer(sample));
				GstCaps *caps_mostra = gst_sample_get_caps(sample);
				const gchar *nume_caps = caps_mostra && gst_caps_get_size(caps_mostra) > 0 ?
					gst_structure_get_name(gst_caps_get_structure(caps_mostra, 0)) : NULL;
				if (nume_caps && !strcmp(nume_caps, "text/x-raw"))
					tip = stPlainText;
				else if (nume_caps && !strcmp(nume_caps, "subpicture/x-dvd"))
					tip = stVOB;
				else if (nume_caps && !strcmp(nume_caps, "subpicture/x-pgs"))
					tip = stPGS;
				else if (nume_caps && !strcmp(nume_caps, "application/x-subtitle-unknown"))
					tip = felNecunoscut(gst_caps_get_structure(caps_mostra, 0), &webvtt_matroska);
				else if (!nume_caps && m_currentSubtitleStream >= 0 && m_currentSubtitleStream < (int)m_subtitleStreams.size())
					tip = m_subtitleStreams[m_currentSubtitleStream].type;
				/* a DVD stream brings its 16 colours and its size in codec_data (the .idx header, the CodecPrivate of
				   the MKV track): read once for every stream */
				if (tip == stVOB && m_vobsub_stream != m_currentSubtitleStream)
				{
					m_vobsub = eHdsVobSub();
					if (m_height == 480)
						m_vobsub.marime(720, 480);
					GstCaps *caps = gst_sample_get_caps(sample);
					const GValue *cd = caps ? gst_structure_get_value(gst_caps_get_structure(caps, 0), "codec_data") : NULL;
					if (cd && GST_VALUE_HOLDS_BUFFER(cd))
					{
						GstMapInfo m;
						GstBuffer *b = gst_value_get_buffer(cd);
						if (b && gst_buffer_map(b, &m, GST_MAP_READ))
						{
							m_vobsub.dinIdx(std::string((const char*)m.data, m.size));
							gst_buffer_unmap(b, &m);
						}
					}
					m_vobsub_stream = m_currentSubtitleStream;
				}
				gst_sample_unref(sample);
			}
			if (buffer)
			{
				GstMapInfo map;
				bool are_date = gst_buffer_map(buffer, &map, GST_MAP_READ);
				gint64 buf_pos = GST_BUFFER_PTS(buffer);  // GST1.0: GST_BUFFER_TIMESTAMP -> GST_BUFFER_PTS
				gint64 duration_ns = GST_BUFFER_DURATION(buffer);
				size_t len = are_date ? map.size : 0;

				if ( are_date && !arunca && tip != stUnknown )
				{
					if ( tip == stPlainText || tip == stSSA || tip == stASS || tip == stSRT || tip == stWebVTT )
					{
						std::string line((const char*)map.data, len);  // GST1.0: GST_BUFFER_DATA -> GstMapInfo.data (mapat mai sus)
						/* lines from files written on Windows keep their "\r\n" through the demuxer; the widget splits at
						   "\n" only */
						line.erase(std::remove(line.begin(), line.end(), '\r'), line.end());
						eDebug("got new text subtitle @ buf_pos = %lld ns (in pts=%lld): '%s' ", (long long)buf_pos, (long long)(buf_pos/11111), line.c_str());
						gRGB rgbcol(0xD0,0xD0,0xD0);
						SubtitlePage page;
						page.type = SubtitlePage::Pango;
						if (tip == stWebVTT)
							line = textWebVtt(line, webvtt_matroska, page.pango_page.m_top);
						if (tip == stWebVTT && line.empty())
							eDebug("[eServiceMP3] a WebVTT cue without text (or not text) is skipped");
						else
						{
							page.pango_page.m_elements.push_back(ePangoSubtitlePageElement(rgbcol, faraCoduriAss(line, page.pango_page.m_top)));
							page.pango_page.m_show_pts = buf_pos / 11111L;
							/* a text of unknown length (GST_CLOCK_TIME_NONE) gets the widget default */
							page.pango_page.m_timeout = GST_CLOCK_TIME_IS_VALID(duration_ns) ? (int)(duration_ns / 1000000) : 0;
							m_subtitle_pages.push_back(page);
						}
					}
					else if ( tip == stVOB )
					{
						eHdsPaginaImagine pagina;
						if (m_vobsub.decodeaza(map.data, len, pagina))
							pagesFromPicture(pagina, buf_pos, duration_ns);
						else
							eDebug("[eServiceMP3] a DVD subtitle packet could not be read (%d bytes)", (int)len);
					}
					else if ( tip == stPGS )
					{
						if (m_pgs_stream != m_currentSubtitleStream)
						{
							m_pgs.reset();
							m_pgs_stream = m_currentSubtitleStream;
						}
						std::vector<eHdsPaginaImagine> pagini;
						if (m_pgs.adauga(map.data, len, pagini) < 0)
							eDebug("[eServiceMP3] a Blu-ray subtitle packet could not be read (%d bytes)", (int)len);
						for (unsigned int k = 0; k < pagini.size(); ++k)
							pagesFromPicture(pagini[k], buf_pos, duration_ns);
					}
					else
					{
						eDebug("unsupported subpicture... ignoring");
					}
				}
				if (are_date)
					gst_buffer_unmap(buffer, &map);
				gst_buffer_unref(buffer);
			}
		}
		gst_object_unref(sink);
		/* the first page waiting gets its timer (pushSubtitles pulls again when the list is empty) */
		if (!m_subtitle_pages.empty() && !m_subtitle_sync_timer->isActive())
			pushSubtitles();
	}
	else
		eDebug("no subtitle sink!");
}

/* a decoded picture subtitle -> the page the widget draws for DVB subtitles (8-bit regions with their palette; gRGB
   keeps the transparency in a, 0 = opaque) */
static void paginaDvb(const eHdsPaginaImagine &p, eDVBSubtitlePage &dvb)
{
	dvb.m_regions.clear();
	dvb.m_display_size = eSize(p.latime, p.inaltime);
	for (unsigned int k = 0; k < p.dreptunghiuri.size(); ++k)
	{
		const eHdsDreptunghi &r = p.dreptunghiuri[k];
		if (r.w <= 0 || r.h <= 0)
			continue;
		eDVBSubtitleRegion regiune;
		regiune.m_position = ePoint(r.x, r.y);
		regiune.m_pixmap = new gPixmap(eSize(r.w, r.h), 8, 1);
		gSurface *sf = regiune.m_pixmap->surface;
		int culori = r.culori > 0 && r.culori <= 256 ? r.culori : 256;
		sf->clut.colors = culori;
		sf->clut.data = new gRGB[culori];
		for (int c = 0; c < culori; ++c)
			sf->clut.data[c] = gRGB((r.paleta[c] >> 16) & 0xFF, (r.paleta[c] >> 8) & 0xFF, r.paleta[c] & 0xFF,
				255 - (int)(r.paleta[c] >> 24));
		for (int y = 0; y < r.h; ++y)
			memcpy((uint8_t*)sf->data + (size_t)y * sf->stride, &r.pixeli[(size_t)y * r.w], r.w);
		dvb.m_regions.push_back(regiune);
	}
}

/* the pages of a picture from the container: the picture at its time (plus the start of the DVD packet), and, when
   the packet says when it ends, an empty page then; the list stays in the order of the times */
void eServiceMP3::pagesFromPicture(const eHdsPaginaImagine &p, gint64 pts_ns, gint64 duration_ns)
{
	SubtitlePage pagina;
	pagina.type = SubtitlePage::Dvb;
	paginaDvb(p, pagina.dvb_page);
	pts_t start = pts_ns / 11111L + (pts_t)p.start_ms * 90;
	pagina.dvb_page.m_show_time = start;
	pagina.dvb_timeout = p.stop_ms > p.start_ms ? p.stop_ms - p.start_ms :
		(p.stop_ms < 0 && GST_CLOCK_TIME_IS_VALID(duration_ns) && duration_ns > 0 ? (int)(duration_ns / 1000000) : 0);
	std::vector<SubtitlePage> noi;
	noi.push_back(pagina);
	if (!p.gol && pagina.dvb_timeout > 0)
	{
		SubtitlePage gol;
		gol.type = SubtitlePage::Dvb;
		gol.dvb_page.m_display_size = pagina.dvb_page.m_display_size;
		gol.dvb_page.m_show_time = start + (pts_t)pagina.dvb_timeout * 90;
		gol.dvb_timeout = 0;
		noi.push_back(gol);
	}
	/* OCR: the picture goes to the recognition now, before its time, so that its text can be ready when it is shown
	   (as on the channels, eDVBServicePlay::newDVBSubtitlePage); setPage finds it again by its time and pictures */
	if (m_subtitle_widget && !pagina.dvb_page.m_regions.empty())
	{
		pts_t acum = 0;
		int ms = 0;
		if (getPlayPosition(acum) == 0)
			ms = (int)((pagina.dvb_page.m_show_time + (pts_t)m_subtitle_delay_ms * 90 - acum) / 90);
		m_subtitle_widget->prefetchPage(pagina.dvb_page, ms > 0 ? ms : 0);
	}
	for (unsigned int k = 0; k < noi.size(); ++k)
	{
		pts_t t = noi[k].dvb_page.m_show_time;
		std::list<SubtitlePage>::iterator it = m_subtitle_pages.end();
		while (it != m_subtitle_pages.begin())
		{
			std::list<SubtitlePage>::iterator inainte = it;
			--inainte;
			pts_t ti = inainte->type == SubtitlePage::Dvb ? inainte->dvb_page.m_show_time : inainte->pango_page.m_show_pts;
			if (ti <= t)
				break;
			it = inainte;
		}
		m_subtitle_pages.insert(it, noi[k]);
	}
}

void eServiceMP3::pushSubtitles()
{
	while ( !m_subtitle_pages.empty() )
	{
		SubtitlePage &frontpage = m_subtitle_pages.front();
		pts_t running_pts;
		gint64 diff_ms = 0;
		gint64 show_pts = 0;

		getPlayPosition(running_pts);

		/* while paused the position stands still: it would look "not valid" for ever and the 25 ms timer would run
		   without end */
		if (m_decoder_time_valid_state < 4 && !m_paused) {
			++m_decoder_time_valid_state;
			if (m_prev_decoder_time == running_pts)
				m_decoder_time_valid_state = 0;
			if (m_decoder_time_valid_state < 4) {
//				if (m_decoder_time_valid_state)
//					eDebug("%d: decoder time not valid! prev %lld, now %lld\n", m_decoder_time_valid_state, m_prev_decoder_time/90, running_pts/90);
//				else
//					eDebug("%d: decoder time not valid! now %lld\n", m_decoder_time_valid_state, running_pts/90);
				m_subtitle_sync_timer->start(25, true);
				m_prev_decoder_time = running_pts;
				break;
			}
		}

		int durata_ms = 0;
		if (frontpage.type == SubtitlePage::Pango)
		{
			show_pts = frontpage.pango_page.m_show_pts;
			durata_ms = frontpage.pango_page.m_timeout;
		}
		else if (frontpage.type == SubtitlePage::Dvb)
		{
			show_pts = frontpage.dvb_page.m_show_time;
			durata_ms = frontpage.dvb_timeout;
		}
		/* the delay chosen for this film (> 0 = later); the pages come shortly before their time, so a large negative
		   delay can only move them as far as they come early */
		show_pts += (gint64)m_subtitle_delay_ms * 90;
		/* a page is late only when its end has passed: after a seek or a change of stream the line that is still
		   running is shown for the time it has left (before, anything that had started 100 ms earlier was dropped) */
		gint64 end_pts = show_pts + (gint64)(durata_ms > 0 ? durata_ms : 5000) * 90;

		diff_ms = ( show_pts - running_pts ) / 90;
		eDebug("check subtitle: decoder: %lld, show_pts: %lld, diff: %lld ms", (long long)(running_pts/90), (long long)(show_pts/90), (long long)diff_ms);

		if ( running_pts >= end_pts )
		{
			eDebug("subtitle too late... drop");
			m_subtitle_pages.pop_front();
		}
		else if ( diff_ms > 20 )
		{
			/* paused: the page waits without a timer, unpause() looks again */
			if (m_paused)
				break;
			eDebug("start timer");
			m_subtitle_sync_timer->start(diff_ms, true);
			break;
		}
		else // immediate show
		{
			if ( m_subtitle_widget )
			{
				eDebug("show!\n");
				if ( frontpage.type == SubtitlePage::Pango)
				{
					if (diff_ms < 0 && durata_ms > 0)
						frontpage.pango_page.m_timeout = (int)((end_pts - running_pts) / 90);
					m_subtitle_widget->setPage(frontpage.pango_page);
					m_page_end_pts = durata_ms > 0 ? end_pts : -1;
				}
				else if ( frontpage.type == SubtitlePage::Dvb )
				{
					if (frontpage.dvb_page.m_regions.empty())
					{
						/* the end of the line (with the translation on, its translation keeps its time) */
						m_subtitle_widget->endPage();
						m_page_end_pts = -1;
					}
					else
					{
						m_subtitle_widget->setPage(frontpage.dvb_page);
						m_page_end_pts = durata_ms > 0 ? end_pts : -1;
						/* the empty page queued after it (DVD: its stop time) or the next display set (Blu-ray)
						   takes it away at the right time; the widget's clock runs on during a pause, so it is only
						   a guard: long when the empty page is sure to come */
						m_subtitle_widget->setPageTimeout(durata_ms > 0 ? 60000 : 30000);
					}
				}
				m_subtitle_widget->show();
			}
			m_subtitle_pages.pop_front();
		}
	}
	if (m_subtitle_pages.empty())
		pullSubtitle();
}

/* ------------------------------------------------------------------ the subtitle files next to the film */

/* Python text -> UTF-8; text that is not valid Unicode (surrogates) is replaced, never an error left set */
static std::string textPython(PyObject *o)
{
	if (!o || !PyUnicode_Check(o))
		return std::string();
	const char *utf8 = PyUnicode_AsUTF8(o);
	if (utf8)
		return std::string(utf8);
	PyErr_Clear();
	ePyObject octeti = PyUnicode_AsEncodedString(o, "utf-8", "replace");
	if (!octeti)
	{
		PyErr_Clear();
		return std::string();
	}
	std::string rezultat(PyBytes_AsString(octeti), PyBytes_Size(octeti));
	Py_DECREF(octeti);
	return rezultat;
}

static long intregPython(PyObject *o, long implicit)
{
	if (!o || !PyLong_Check(o))
		return implicit;
	long v = PyLong_AsLong(o);
	if (v == -1 && PyErr_Occurred())
	{
		PyErr_Clear();
		return implicit;
	}
	return v;
}

/* the limits keep a broken or huge list from filling the memory of the receiver */
static const unsigned int MAX_FISIERE = 64;
static const unsigned int MAX_REPLICI = 200000;
static const size_t MAX_TEXT_REPLICA = 2000;
static const int MAX_INTARZIERE_MS = 600000;

RESULT eServiceMP3::setExternalSubtitles(ePyObject entries)
{
	if (!entries || !PySequence_Check(entries))
		return -1;
	ePyObject lista = PySequence_Fast(entries, "a list of subtitle files");
	if (!lista)
	{
		PyErr_Clear();
		return -1;
	}
	std::string activ = (m_external_active >= 0 && m_external_active < (int)m_external_subtitles.size()) ?
		m_external_subtitles[m_external_active].name : std::string();
	std::vector<externalSubtitle> noi;
	Py_ssize_t n = PySequence_Fast_GET_SIZE(lista);
	for (Py_ssize_t i = 0; i < n && noi.size() < MAX_FISIERE; ++i)
	{
		PyObject *e = PySequence_Fast_GET_ITEM(lista, i);
		if (!PyTuple_Check(e) || PyTuple_Size(e) < 4)
			continue;
		externalSubtitle s;
		s.name = textPython(PyTuple_GET_ITEM(e, 0));
		s.language = textPython(PyTuple_GET_ITEM(e, 1));
		s.type = (int)intregPython(PyTuple_GET_ITEM(e, 2), stUnknown);
		s.flags = (int)intregPython(PyTuple_GET_ITEM(e, 3), 0);
		s.loaded = false;
		if (s.name.empty())
			continue;
		if (s.language.empty())
			s.language = "und";
		s.picture_kind = 0;
		/* a file already known keeps its lines (or its pictures) */
		for (unsigned int k = 0; k < m_external_subtitles.size(); ++k)
			if (m_external_subtitles[k].name == s.name && m_external_subtitles[k].loaded)
			{
				s.cues.swap(m_external_subtitles[k].cues);
				s.pictures.swap(m_external_subtitles[k].pictures);
				s.picture_kind = m_external_subtitles[k].picture_kind;
				s.path = m_external_subtitles[k].path;
				s.info = m_external_subtitles[k].info;
				s.loaded = true;
				break;
			}
		noi.push_back(s);
	}
	Py_DECREF(lista);
	m_external_subtitles.swap(noi);
	int acum = -1;
	if (!activ.empty())
		for (unsigned int k = 0; k < m_external_subtitles.size(); ++k)
			if (m_external_subtitles[k].name == activ)
				acum = k;
	if (m_external_active >= 0 && acum < 0)
	{
		/* the file shown is no longer in the list */
		m_external_timer->stop();
		m_external_shown.clear();
		if (m_subtitle_widget)
			m_subtitle_widget->clearPage();
	}
	if (acum != m_external_active)
		m_picture_index = -1;
	m_external_active = acum;
	eDebug("[eServiceMP3] subtitle files next to the film: %d", (int)m_external_subtitles.size());
	m_event((iPlayableService*)this, evUpdatedInfo);
	return 0;
}

RESULT eServiceMP3::setExternalSubtitleCues(int index, ePyObject cues)
{
	if (index < 0 || index >= (int)m_external_subtitles.size() || !cues || !PySequence_Check(cues))
		return -1;
	ePyObject lista = PySequence_Fast(cues, "a list of subtitle lines");
	if (!lista)
	{
		PyErr_Clear();
		return -1;
	}
	std::vector<externalCue> replici;
	Py_ssize_t n = PySequence_Fast_GET_SIZE(lista);
	replici.reserve(n < (Py_ssize_t)MAX_REPLICI ? n : MAX_REPLICI);
	for (Py_ssize_t i = 0; i < n && replici.size() < MAX_REPLICI; ++i)
	{
		PyObject *e = PySequence_Fast_GET_ITEM(lista, i);
		if (!PyTuple_Check(e) || PyTuple_Size(e) < 3)
			continue;
		externalCue c;
		c.start_ms = (int)intregPython(PyTuple_GET_ITEM(e, 0), -1);
		c.end_ms = (int)intregPython(PyTuple_GET_ITEM(e, 1), -1);
		c.text = textPython(PyTuple_GET_ITEM(e, 2));
		c.top = PyTuple_Size(e) > 3 && PyObject_IsTrue(PyTuple_GET_ITEM(e, 3)) == 1;
		if (c.start_ms < 0 || c.end_ms <= c.start_ms || c.text.empty())
			continue;
		if (c.text.size() > MAX_TEXT_REPLICA)
			c.text.resize(MAX_TEXT_REPLICA);
		replici.push_back(c);
	}
	Py_DECREF(lista);
	std::stable_sort(replici.begin(), replici.end(),
		[](const externalCue &a, const externalCue &b) { return a.start_ms < b.start_ms; });
	externalSubtitle &s = m_external_subtitles[index];
	s.cues.swap(replici);
	s.loaded = true;
	eDebug("[eServiceMP3] subtitle file %d (%s): %d lines", index, s.name.c_str(), (int)s.cues.size());
	if (index == m_external_active)
	{
		m_external_shown.clear();
		if (m_subtitle_widget)
			m_subtitle_widget->clearPage();
		externalTick();
	}
	return 0;
}

RESULT eServiceMP3::setExternalSubtitlePictures(int index, int kind, const std::string &path, const std::string &info,
	ePyObject entries)
{
	if (index < 0 || index >= (int)m_external_subtitles.size() || (kind != stVOB && kind != stPGS) || path.empty() ||
			!entries || !PySequence_Check(entries))
		return -1;
	ePyObject lista = PySequence_Fast(entries, "a list of picture packets");
	if (!lista)
	{
		PyErr_Clear();
		return -1;
	}
	std::vector<externalPicture> imagini;
	Py_ssize_t n = PySequence_Fast_GET_SIZE(lista);
	for (Py_ssize_t i = 0; i < n && imagini.size() < MAX_REPLICI; ++i)
	{
		PyObject *e = PySequence_Fast_GET_ITEM(lista, i);
		if (!PyTuple_Check(e) || PyTuple_Size(e) < 3)
			continue;
		externalPicture x;
		x.start_ms = (int)intregPython(PyTuple_GET_ITEM(e, 0), -1);
		x.offset = PyLong_Check(PyTuple_GET_ITEM(e, 1)) ? PyLong_AsLongLong(PyTuple_GET_ITEM(e, 1)) : -1;
		if (PyErr_Occurred())
		{
			PyErr_Clear();
			x.offset = -1;
		}
		x.length = (int)intregPython(PyTuple_GET_ITEM(e, 2), -1);
		if (x.start_ms < 0 || x.offset < 0 || x.length < 0 || x.length > 16 * 1024 * 1024)
			continue;
		imagini.push_back(x);
	}
	Py_DECREF(lista);
	std::stable_sort(imagini.begin(), imagini.end(),
		[](const externalPicture &a, const externalPicture &b) { return a.start_ms < b.start_ms; });
	externalSubtitle &s = m_external_subtitles[index];
	s.picture_kind = kind;
	s.path = path;
	s.info = info;
	s.pictures.swap(imagini);
	s.cues.clear();
	s.loaded = true;
	eDebug("[eServiceMP3] subtitle file %d (%s): %d pictures", index, s.name.c_str(), (int)s.pictures.size());
	if (index == m_external_active)
	{
		m_picture_index = -1;
		m_external_shown.clear();
		if (m_subtitle_widget)
			m_subtitle_widget->clearPage();
		externalTick();
	}
	return 0;
}

/* The picture of the chosen file that is due now. The packet is read on the thread of m_picture_reader: while it is
   being read the tick comes again after 20 ms. The reader reads the packet after it ahead, so a line is normally
   ready before its time. When the packet that is due changes, the old picture goes from the screen. */
void eServiceMP3::externalPictureTick(const externalSubtitle &s, int now_ms)
{
	const std::vector<externalPicture> &p = s.pictures;
	if (!m_picture_reader.configurat(s.picture_kind, s.path, p.size()))
	{
		m_picture_reader.configureaza(s.picture_kind, s.path, s.info, p);
		m_picture_index = -1;
		m_picture_ready = false;
	}
	int i = (int)(std::upper_bound(p.begin(), p.end(), now_ms,
		[](int t, const externalPicture &x) { return t < x.start_ms; }) - p.begin()) - 1;
	int pana = 500;
	if (i + 1 < (int)p.size() && p[i + 1].start_ms - now_ms < pana)
		pana = p[i + 1].start_ms - now_ms;
	if (i != m_picture_index)
	{
		m_picture_index = i;
		m_picture_ready = false;
		if (!m_external_shown.empty())
		{
			m_subtitle_widget->endPage();
			m_external_shown.clear();
		}
	}
	bool activ = false;
	if (i < 0)
	{
		/* before the first picture: it is read ahead */
		if (!p.empty())
			m_picture_reader.cere(0);
	}
	else
	{
		if (!m_picture_ready)
		{
			int r = m_picture_reader.ia(i, m_picture_page);
			if (r == 0)
			{
				m_external_timer->start(20, true);
				return;
			}
			if (r < 0)
			{
				eDebug("[eServiceMP3] picture %d of %s could not be read", i, s.name.c_str());
				m_picture_page = eHdsPaginaImagine();
			}
			m_picture_ready = true;
		}
		int start = p[i].start_ms + m_picture_page.start_ms;
		int stop = m_picture_page.stop_ms >= 0 ? p[i].start_ms + m_picture_page.stop_ms : -1;
		activ = !m_picture_page.gol && now_ms >= start && (stop < 0 || now_ms < stop);
		if (now_ms < start && start - now_ms < pana)
			pana = start - now_ms;
		if (activ && stop >= 0 && stop - now_ms < pana)
			pana = stop - now_ms;
	}
	if (activ && m_external_shown.empty())
	{
		eDVBSubtitlePage dvb;
		paginaDvb(m_picture_page, dvb);
		m_subtitle_widget->setPage(dvb);
		/* the ticks take it away at its end; the widget's own timeout is only a guard, long enough for a pause */
		int stop = m_picture_page.stop_ms >= 0 ? p[i].start_ms + m_picture_page.stop_ms : -1;
		m_subtitle_widget->setPageTimeout((stop > now_ms ? stop - now_ms : 0) + 60000);
		m_subtitle_widget->show();
		m_external_shown.push_back(i);
	}
	else if (!activ && !m_external_shown.empty())
	{
		/* the end of the picture (with the translation on, its translation keeps its time) */
		m_subtitle_widget->endPage();
		m_external_shown.clear();
	}
	if (pana < 10)
		pana = 10;
	m_external_timer->start(pana, true);
}

RESULT eServiceMP3::setSubtitleDelay(int ms)
{
	if (ms > MAX_INTARZIERE_MS)
		ms = MAX_INTARZIERE_MS;
	if (ms < -MAX_INTARZIERE_MS)
		ms = -MAX_INTARZIERE_MS;
	m_subtitle_delay_ms = ms;
	if (m_external_active >= 0)
		externalTick();
	return 0;
}

int eServiceMP3::getSubtitleDelay()
{
	return m_subtitle_delay_ms;
}

/* The lines of the chosen file at the play position (minus the delay), then a wake-up for the next change: the next
   line that starts or the first one on screen that ends, at most half a second later (a seek or a pause is seen
   within that time). The cues are sorted by their start; lines that overlap (two speakers) are shown together. */
void eServiceMP3::externalTick()
{
	m_external_timer->stop();
	if (m_external_active < 0 || m_external_active >= (int)m_external_subtitles.size() || !m_subtitle_widget)
		return;
	const externalSubtitle &s = m_external_subtitles[m_external_active];
	pts_t pozitie = 0;
	if (m_state != stRunning || getPlayPosition(pozitie) < 0)
	{
		m_external_timer->start(250, true);
		return;
	}
	int acum = (int)(pozitie / 90) - m_subtitle_delay_ms;
	if (s.picture_kind)
	{
		externalPictureTick(s, acum);
		return;
	}
	const std::vector<externalCue> &c = s.cues;
	/* the first line that starts after now */
	size_t urmatoarea = std::upper_bound(c.begin(), c.end(), acum,
		[](int t, const externalCue &x) { return t < x.start_ms; }) - c.begin();
	std::vector<int> active;
	for (size_t k = urmatoarea, pasi = 0; k > 0 && pasi < 16; --k, ++pasi)
		if (c[k - 1].end_ms > acum)
			active.insert(active.begin(), (int)(k - 1));
	if (active != m_external_shown)
		showExternalCues(active, acum);
	int pana = 500;
	if (urmatoarea < c.size() && c[urmatoarea].start_ms - acum < pana)
		pana = c[urmatoarea].start_ms - acum;
	for (unsigned int k = 0; k < active.size(); ++k)
		if (c[active[k]].end_ms - acum < pana)
			pana = c[active[k]].end_ms - acum;
	if (pana < 10)
		pana = 10;
	m_external_timer->start(pana, true);
}

void eServiceMP3::showExternalCues(const std::vector<int> &cues, int now_ms)
{
	m_external_shown = cues;
	if (!m_subtitle_widget || m_external_active < 0)
		return;
	if (cues.empty())
	{
		/* the end of the line (with the translation on, its translation keeps its time) */
		m_subtitle_widget->endPage();
		return;
	}
	const std::vector<externalCue> &c = m_external_subtitles[m_external_active].cues;
	gRGB rgbcol(0xD0,0xD0,0xD0);
	ePangoSubtitlePage pagina;
	int sfarsit = c[cues[0]].end_ms;
	for (unsigned int k = 0; k < cues.size(); ++k)
	{
		const externalCue &x = c[cues[k]];
		size_t inceput = 0;
		while (inceput <= x.text.size())
		{
			size_t capat = x.text.find('\n', inceput);
			if (capat == std::string::npos)
				capat = x.text.size();
			std::string rand = x.text.substr(inceput, capat - inceput);
			if (!rand.empty())
				pagina.m_elements.push_back(ePangoSubtitlePageElement(rgbcol, rand));
			inceput = capat + 1;
		}
		if (x.top)
			pagina.m_top = true;
		if (x.end_ms < sfarsit)
			sfarsit = x.end_ms;
	}
	/* the next wake-up takes the page away at the end of the line; the widget's own timeout is only a guard, long
	   enough that a paused film keeps its subtitle on screen */
	pagina.m_timeout = sfarsit - now_ms + 60000;
	pagina.m_show_pts = 0;
	m_subtitle_widget->setPage(pagina);
	m_subtitle_widget->show();
}

RESULT eServiceMP3::enableSubtitles(eWidget *parent, ePyObject tuple)
{
	eDebug ("eServiceMP3::enableSubtitles m_currentSubtitleStream=%i this=%p",m_currentSubtitleStream, this);
	int pid;
	gint text_pid = 0;

	/* (2, stream, type, ...): at least the kind, the number and the type */
	if (!PyTuple_Check(tuple) || PyTuple_Size(tuple) < 3 || !PyLong_Check(PyTuple_GET_ITEM(tuple, 1)) ||
			!PyLong_Check(PyTuple_GET_ITEM(tuple, 2)))
	{
		eDebug("eServiceMP3::enableSubtitles needs a tuple as 2nd argument!\n"
			"for gst subtitles (2, subtitle_stream_count, subtitle_type)");
		return -1;
	}
	pid = PyLong_AsLong(PyTuple_GET_ITEM(tuple, 1));

	{
		/* No m_subs_to_pull_lock around g_object_set: the pages are handled on this thread only (pullSubtitle), the
		   lock guards the counter, and holding it while playbin switches the stream can stop both sides (see seekTo).
		   Pages of the old stream still queued are read by the type in their own caps and dropped as late. */
		if (pid >= 100)
		{
			/* a file next to the film: the pipeline is not touched */
			if (pid - 100 >= (int)m_external_subtitles.size())
			{
				eDebug("eServiceMP3::enableSubtitles no subtitle file %d", pid - 100);
				return -1;
			}
			m_external_active = pid - 100;
			m_picture_index = -1;
			m_subtitle_pages.clear();
			m_subtitle_sync_timer->stop();
		}
		else
		{
			m_external_active = -1;
			m_external_timer->stop();
			if (m_currentSubtitleStream != pid)
			{
				m_pgs.reset();
				m_pgs_stream = pid;
				m_vobsub_stream = -1;
				g_object_set (G_OBJECT (m_gst_playbin), "current-text", pid, NULL);
				eDebug ("eServiceMP3::enableSubtitles g_object_set current-text = %i", pid);
				/* what the appsink still holds came from the old stream */
				GstElement *sink = NULL;
				g_object_get (G_OBJECT (m_gst_playbin), "text-sink", &sink, NULL);
				if (sink)
				{
					for (int k = 0; k < 64; ++k)
					{
						GstSample *vechi = NULL;
						g_signal_emit_by_name (sink, "try-pull-sample", (GstClockTime)0, &vechi);
						if (!vechi)
							break;
						gst_sample_unref(vechi);
					}
					gst_object_unref(sink);
				}
				m_currentSubtitleStream = pid;
				{
					eSingleLocker l(m_subs_to_pull_lock);
					m_subs_to_pull = 0;
				}
				m_prev_decoder_time = -1;
				m_subtitle_pages.clear();
			}
		}
		m_external_shown.clear();
		m_page_end_pts = -1;

		/* the widget of an earlier choice goes first, it would stay over the picture otherwise */
		delete m_subtitle_widget;
		m_subtitle_widget = new eSubtitleWidget(parent);
		m_subtitle_widget->resize(parent->size()); /* full size */

		if (m_external_active >= 0)
			eDebug ("eServiceMP3::switched to subtitle file %d (%s)", m_external_active, m_external_subtitles[m_external_active].name.c_str());
		else
		{
			g_object_get (G_OBJECT (m_gst_playbin), "current-text", &text_pid, NULL);
			eDebug ("eServiceMP3::switched to subtitle stream %i", text_pid);
		}
	}

	/* no evUpdatedInfo here (the DVB service sends none either): the Python side chooses the subtitle on that event and
	   would call this function again from inside it, before its own state says the subtitle is on */
	if (m_external_active >= 0)
		externalTick();

	return 0;
}

RESULT eServiceMP3::disableSubtitles(eWidget *parent)
{
	eDebug("eServiceMP3::disableSubtitles");
	/* "No subtitles": the widget goes; a container stream keeps flowing and its pages are dropped when their time
	   passes (switching the text flag off in playbin during the film would reconfigure the sinks) */
	m_subtitle_pages.clear();
	m_external_active = -1;
	m_external_timer->stop();
	m_external_shown.clear();
	m_page_end_pts = -1;
	delete m_subtitle_widget;
	m_subtitle_widget = 0;
	return 0;
}

PyObject *eServiceMP3::getCachedSubtitle()
{
	/* the choice per film is kept by Components/HdsSubtitrariFilm.py */
	Py_RETURN_NONE;
}

PyObject *eServiceMP3::getSubtitleList()
{
// 	eDebug("eServiceMP3::getSubtitleList");
	ePyObject l = PyList_New(0);
	int stream_idx = 0;

	for (std::vector<subtitleStream>::iterator IterSubtitleStream(m_subtitleStreams.begin()); IterSubtitleStream != m_subtitleStreams.end(); ++IterSubtitleStream)
	{
		subtype_t type = IterSubtitleStream->type;
		switch(type)
		{
		case stUnknown:
			break;
		default:
		{
			ePyObject tuple = PyTuple_New(5);
//			eDebug("eServiceMP3::getSubtitleList idx=%i type=%i, code=%s", stream_idx, int(type), (IterSubtitleStream->language_code).c_str());
			PyTuple_SET_ITEM(tuple, 0, PyLong_FromLong(2));
			PyTuple_SET_ITEM(tuple, 1, PyLong_FromLong(stream_idx));
			PyTuple_SET_ITEM(tuple, 2, PyLong_FromLong(int(type)));
			PyTuple_SET_ITEM(tuple, 3, PyLong_FromLong(0));
			PyTuple_SET_ITEM(tuple, 4, PyUnicode_FromString((IterSubtitleStream->language_code).c_str()));
			PyList_Append(l, tuple);
			Py_DECREF(tuple);
		}
		}
		stream_idx++;
	}
	/* the files next to the film: (2, 100 + index, type, 0, language, for the deaf, name) */
	for (unsigned int i = 0; i < m_external_subtitles.size(); ++i)
	{
		const externalSubtitle &s = m_external_subtitles[i];
		ePyObject tuple = PyTuple_New(7);
		PyTuple_SET_ITEM(tuple, 0, PyLong_FromLong(2));
		PyTuple_SET_ITEM(tuple, 1, PyLong_FromLong(100 + i));
		PyTuple_SET_ITEM(tuple, 2, PyLong_FromLong(s.type));
		PyTuple_SET_ITEM(tuple, 3, PyLong_FromLong(0));
		PyTuple_SET_ITEM(tuple, 4, PyUnicode_DecodeUTF8(s.language.data(), s.language.size(), "replace"));
		PyTuple_SET_ITEM(tuple, 5, PyLong_FromLong((s.flags & 2) ? 1 : 0));
		PyTuple_SET_ITEM(tuple, 6, PyUnicode_DecodeUTF8(s.name.data(), s.name.size(), "replace"));
		PyList_Append(l, tuple);
		Py_DECREF(tuple);
	}
	eDebug("eServiceMP3::getSubtitleList finished");
	return l;
}

RESULT eServiceMP3::streamed(ePtr<iStreamedService> &ptr)
{
	ptr = this;
	return 0;
}

PyObject *eServiceMP3::getBufferCharge()
{
	ePyObject tuple = PyTuple_New(5);
	PyTuple_SET_ITEM(tuple, 0, PyLong_FromLong(m_bufferInfo.bufferPercent));
	PyTuple_SET_ITEM(tuple, 1, PyLong_FromLong(m_bufferInfo.avgInRate));
	PyTuple_SET_ITEM(tuple, 2, PyLong_FromLong(m_bufferInfo.avgOutRate));
	PyTuple_SET_ITEM(tuple, 3, PyLong_FromLong(m_bufferInfo.bufferingLeft));
	PyTuple_SET_ITEM(tuple, 4, PyLong_FromLong(m_buffer_size));
	return tuple;
}

int eServiceMP3::setBufferSize(int size)
{
	m_buffer_size = size;
	g_object_set (G_OBJECT (m_gst_playbin), "buffer-size", m_buffer_size, NULL);
	return 0;
}

int eServiceMP3::getAC3Delay()
{
	return ac3_delay;
}

int eServiceMP3::getPCMDelay()
{
	return pcm_delay;
}

void eServiceMP3::setAC3Delay(int delay)
{
	ac3_delay = delay;
	if (!m_gst_playbin || m_state != stRunning)
		return;
	else
	{
		GstElement *sink;
		int config_delay_int = delay;
		g_object_get (G_OBJECT (m_gst_playbin), "video-sink", &sink, NULL);

		if (sink)
		{
			std::string config_delay;
			if(ePythonConfigQuery::getConfigValue("config.av.generalAC3delay", config_delay) == 0)
				config_delay_int += atoi(config_delay.c_str());
			gst_object_unref(sink);
		}
		else
		{
			eDebug("dont apply ac3 delay when no video is running!");
			config_delay_int = 0;
		}

		g_object_get (G_OBJECT (m_gst_playbin), "audio-sink", &sink, NULL);

		if (sink)
		{
			gchar *name = gst_element_get_name(sink);
			if (strstr(name, "dvbaudiosink"))
				eTSMPEGDecoder::setHwAC3Delay(config_delay_int);
			g_free(name);
			gst_object_unref(sink);
		}
	}
}

void eServiceMP3::setPCMDelay(int delay)
{
	pcm_delay = delay;
	if (!m_gst_playbin || m_state != stRunning)
		return;
	else
	{
		GstElement *sink;
		int config_delay_int = delay;
		g_object_get (G_OBJECT (m_gst_playbin), "video-sink", &sink, NULL);

		if (sink)
		{
			std::string config_delay;
			if(ePythonConfigQuery::getConfigValue("config.av.generalPCMdelay", config_delay) == 0)
				config_delay_int += atoi(config_delay.c_str());
			gst_object_unref(sink);
		}
		else
		{
			eDebug("dont apply pcm delay when no video is running!");
			config_delay_int = 0;
		}

		g_object_get (G_OBJECT (m_gst_playbin), "audio-sink", &sink, NULL);

		if (sink)
		{
			gchar *name = gst_element_get_name(sink);
			if (strstr(name, "dvbaudiosink"))
				eTSMPEGDecoder::setHwPCMDelay(config_delay_int);
			else
			{
				/* another audio sink (the PC emulator): playbin shifts the audio against the video with "av-offset"
				   (ns); playbin has no "ts-offset" (that was a GLib-CRITICAL line in the log) */
				gint64 offset = config_delay_int;
				offset *= 1000000; // milli to nano
				if (g_object_class_find_property(G_OBJECT_GET_CLASS(m_gst_playbin), "av-offset"))
					g_object_set (G_OBJECT (m_gst_playbin), "av-offset", offset, NULL);
			}
			g_free(name);
			gst_object_unref(sink);
		}
	}
}

