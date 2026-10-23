/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <vector>
#include <lib/base/ebase.h>
#include <lib/dvb/dvbapi_compat.h>
#include <lib/base/eerror.h>
#include <lib/dvb/decoder.h>
#if HAVE_HISILICON
#include <lib/dvb/hdspazavideo.h>
#endif
#if HAVE_DVB_API_VERSION < 3 
#define audioStatus audio_status
#define videoStatus video_status
#define pesType pes_type
#define playState play_state
#define audioStreamSource_t audio_stream_source_t
#define videoStreamSource_t video_stream_source_t
#define streamSource stream_source
#define dmxPesFilterParams dmx_pes_filter_params
#define DMX_PES_VIDEO0 DMX_PES_VIDEO
#define DMX_PES_AUDIO0 DMX_PES_AUDIO
#define DMX_PES_PCR0 DMX_PES_PCR
#define DMX_PES_TELETEXT0 DMX_PES_TELETEXT
#define DMX_PES_VIDEO1 DMX_PES_VIDEO
#define DMX_PES_AUDIO1 DMX_PES_AUDIO
#define DMX_PES_PCR1 DMX_PES_PCR
#define DMX_PES_TELETEXT1 DMX_PES_TELETEXT
#include <ost/dmx.h>
#include <ost/video.h>
#include <ost/audio.h>
#else
#include <linux/dvb/audio.h>
#include <linux/dvb/video.h>
#include <linux/dvb/dmx.h>
#endif

#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <errno.h>

	/* these are quite new... */
#ifndef AUDIO_GET_PTS
#define AUDIO_GET_PTS              _IOR('o', 19, __u64)
#define VIDEO_GET_PTS              _IOR('o', 57, __u64)
#endif

DEFINE_REF(eDVBAudio);

eDVBAudio::eDVBAudio(eDVBDemux *demux, int dev)
	:m_demux(demux), m_dev(dev)
{
	char filename[128];
#if HAVE_DVB_API_VERSION < 3
	sprintf(filename, "/dev/dvb/card%d/audio%d", demux->adapter, dev);
#else
	sprintf(filename, "/dev/dvb/adapter%d/audio%d", demux->adapter, dev);
#endif
	m_fd = ::open(filename, O_RDWR);
	if (m_fd < 0)
		eWarning("%s: %m", filename);
#if HAVE_DVB_API_VERSION < 3
	sprintf(filename, "/dev/dvb/card%d/demux%d", demux->adapter, demux->demux);
#else
	sprintf(filename, "/dev/dvb/adapter%d/demux%d", demux->adapter, demux->demux);
#endif
	m_fd_demux = ::open(filename, O_RDWR);
	if (m_fd_demux < 0)
		eWarning("%s: %m", filename);
}

#if HAVE_DVB_API_VERSION < 3
int eDVBAudio::setPid(int pid, int type)
{
	if ((m_fd < 0) || (m_fd_demux < 0))
		return -1;

	int bypass = 0;

	switch (type)
	{
	case aMPEG:
		bypass = 1;
		break;
	case aAC3:
		bypass = 0;
		break;
		/*
	case aDTS:
		bypass = 2;
		break;
		*/
	}

	if (::ioctl(m_fd, AUDIO_SET_BYPASS_MODE, bypass) < 0)
		eDebug("failed (%m)");

	dmx_pes_filter_params pes;

	pes.pid      = pid;
	pes.input    = DMX_IN_FRONTEND;
	pes.output   = DMX_OUT_DECODER;
	pes.pes_type = m_dev ? DMX_PES_AUDIO1 : DMX_PES_AUDIO0; /* FIXME */
	pes.flags    = 0;
	eDebugNoNewLine("DMX_SET_PES_FILTER(0x%02x) - audio - ", pid);
	if (::ioctl(m_fd_demux, DMX_SET_PES_FILTER, &pes) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");

	return 0;
}

int eDVBAudio::startPid()
{
	eDebugNoNewLine("DEMUX_START - audio - ");
	if (::ioctl(m_fd_demux, DMX_START) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}

int eDVBAudio::start()
{
	eDebugNoNewLine("AUDIO_PLAY - ");
	if (::ioctl(m_fd, AUDIO_PLAY) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}

int eDVBAudio::stopPid()
{
	eDebugNoNewLine("DEMUX_STOP - audio - ");
	if (::ioctl(m_fd_demux, DMX_STOP) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}

int eDVBAudio::setAVSync(int val)
{
	eDebugNoNewLine("AUDIO_SET_AV_SYNC - ");
	if (::ioctl(m_fd, AUDIO_SET_AV_SYNC, val) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}
#else
int eDVBAudio::startPid(int pid, int type)
{
	if ((m_fd < 0) || (m_fd_demux < 0))
		return -1;

	// Oprim decodorul si demuxerul inainte de a schimba modul de bypass
	::ioctl(m_fd, AUDIO_STOP);
	::ioctl(m_fd_demux, DMX_STOP);

	int bypass = 0;

	switch (type)
	{
	case aMPEG:
		bypass = 1;
		break;
	case aAC3:
		bypass = 0;
		break;
	case aDTS:
		bypass = 2;
		break;
	case aAAC:
		bypass = 8;
		break;
	case aAACHE:
		bypass = 9;
		break;
	case aLPCM:
		bypass = 6;
		break;
	case aDTSHD:
		bypass = 0x10;
		break;
	case aDDP:
		bypass = 0x22; // E-AC-3; valoarea asteptata de driver pe aparatele ne-Dreambox (u57 inclus), aceeasi in dvbmediasink
		break;
	}

	eDebugNoNewLine("AUDIO_SET_BYPASS(%d) - ", bypass);
	if (::ioctl(m_fd, AUDIO_SET_BYPASS_MODE, bypass) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");

	dmx_pes_filter_params pes;

	pes.pid      = pid;
	pes.input    = DMX_IN_FRONTEND;
	pes.output   = DMX_OUT_DECODER;
	pes.pes_type = m_dev ? DMX_PES_AUDIO1 : DMX_PES_AUDIO0; /* FIXME */
	pes.flags    = 0;
	eDebugNoNewLine("DMX_SET_PES_FILTER(0x%02x) - audio - ", pid);
	if (::ioctl(m_fd_demux, DMX_SET_PES_FILTER, &pes) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	eDebugNoNewLine("DEMUX_START - audio - ");
	if (::ioctl(m_fd_demux, DMX_START) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");

	freeze();

	eDebugNoNewLine("AUDIO_PLAY - ");
	if (::ioctl(m_fd, AUDIO_PLAY) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
	return 0;

}
#endif

void eDVBAudio::stop()
{
	eDebugNoNewLine("AUDIO_STOP - ");
	if (::ioctl(m_fd, AUDIO_STOP) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
#if HAVE_DVB_API_VERSION > 2
	eDebugNoNewLine("DEMUX_STOP - audio - ");
	if (::ioctl(m_fd_demux, DMX_STOP) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
#endif
}

void eDVBAudio::flush()
{
	eDebugNoNewLine("AUDIO_CLEAR_BUFFER - ");
	if (::ioctl(m_fd, AUDIO_CLEAR_BUFFER) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
}

void eDVBAudio::freeze()
{
	eDebugNoNewLine("AUDIO_PAUSE - ");
	if (::ioctl(m_fd, AUDIO_PAUSE) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
}

void eDVBAudio::unfreeze()
{
	eDebugNoNewLine("AUDIO_CONTINUE - ");
	if (::ioctl(m_fd, AUDIO_CONTINUE) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
}

void eDVBAudio::setChannel(int channel)
{
	int val = AUDIO_STEREO;
	switch (channel)
	{
	case aMonoLeft: val = AUDIO_MONO_LEFT; break;
	case aMonoRight: val = AUDIO_MONO_RIGHT; break;
	default: break;
	}
	eDebugNoNewLine("AUDIO_CHANNEL_SELECT(%d) - ", val);
	if (::ioctl(m_fd, AUDIO_CHANNEL_SELECT, val) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
}

int eDVBAudio::getPTS(pts_t &now)
{
	if (::ioctl(m_fd, AUDIO_GET_PTS, &now) < 0)
		eDebug("AUDIO_GET_PTS failed (%m)");
	return 0;
}

eDVBAudio::~eDVBAudio()
{
	unfreeze();  // why unfreeze here... but not unfreeze video in ~eDVBVideo ?!?
	if (m_fd >= 0)
		::close(m_fd);
	if (m_fd_demux >= 0)
		::close(m_fd_demux);
}

DEFINE_REF(eDVBVideo);

#if HAVE_HISILICON
/* The driver keeps one selected video source for all decoders. While a still picture is open (source 0xff), the video
   commands of every decoder go to the picture players. So at most one picture is open at a time, it is closed before
   any decoder starts real video, and no picture is shown while another decoder has video. */
static eTSMPEGDecoder *hisiPictureOwner = NULL; /* decoder whose still picture holds video0, or NULL */
static int hisiVideoCount = 0; /* live eDVBVideo objects, on all decoders */
static std::string hisiPictureFile; /* file of the open picture, kept while hisiPictureOwner is set */

#endif
eDVBVideo::eDVBVideo(eDVBDemux *demux, int dev)
	: m_demux(demux), m_dev(dev),
	m_width(-1), m_height(-1), m_framerate(-1), m_aspect(-1), m_progressive(-1), m_gamma(-1)
{
#if HAVE_HISILICON
	hisiVideoCount++;
#endif
	char filename[128];
#if HAVE_DVB_API_VERSION < 3
	sprintf(filename, "/dev/dvb/card%d/video%d", demux->adapter, dev);
	m_fd_video = ::open("/dev/video", O_RDWR);
	if (m_fd_video < 0)
		eWarning("/dev/video: %m");
#else
	sprintf(filename, "/dev/dvb/adapter%d/video%d", demux->adapter, dev);
#endif
	m_fd = ::open(filename, O_RDWR);
	if (m_fd < 0)
		eWarning("%s: %m", filename);
	else
	{
		m_sn = eSocketNotifier::create(eApp, m_fd, eSocketNotifier::Priority);
		CONNECT(m_sn->activated, eDVBVideo::video_event);
	}
	eDebug("Video Device: %s", filename);
#if HAVE_DVB_API_VERSION < 3
	sprintf(filename, "/dev/dvb/card%d/demux%d", demux->adapter, demux->demux);
#else
	sprintf(filename, "/dev/dvb/adapter%d/demux%d", demux->adapter, demux->demux);
#endif
	m_fd_demux = ::open(filename, O_RDWR);
	if (m_fd_demux < 0)
		eWarning("%s: %m", filename);
	eDebug("demux device: %s", filename);
}

// not finally values i think.. !!
#define VIDEO_STREAMTYPE_MPEG2 0
#define VIDEO_STREAMTYPE_MPEG4_H264 1
#define VIDEO_STREAMTYPE_VC1 3
#define VIDEO_STREAMTYPE_MPEG4_Part2 4
#define VIDEO_STREAMTYPE_VC1_SM 5
#define VIDEO_STREAMTYPE_MPEG1 6
/* 7 pe tot ce nu e Dreambox (acolo 22): asa e STREAMTYPE_MPEG4_H265 in
   gstreamer1.0-plugin-dvbmediasink construit pentru u57 (--with-machine=u57, fara --with-dreambox) */
#define VIDEO_STREAMTYPE_H265_HEVC 7
/* AVS / AVS+ (stream_type 0x42): 16 duce in showiframe (e2VideoType2Hisi) la tipul AVS al decodorului HiSilicon */
#define VIDEO_STREAMTYPE_CAVS 16

#if HAVE_DVB_API_VERSION < 3
int eDVBVideo::setPid(int pid)
{
	if ((m_fd < 0) || (m_fd_demux < 0))
		return -1;
	dmx_pes_filter_params pes;

	pes.pid      = pid;
	pes.input    = DMX_IN_FRONTEND;
	pes.output   = DMX_OUT_DECODER;
	pes.pes_type = m_dev ? DMX_PES_VIDEO1 : DMX_PES_VIDEO0; /* FIXME */
	pes.flags    = 0;
	eDebugNoNewLine("DMX_SET_PES_FILTER(0x%02x) - video - ", pid);
	if (::ioctl(m_fd_demux, DMX_SET_PES_FILTER, &pes) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}

int eDVBVideo::startPid()
{
	eDebugNoNewLine("DEMUX_START - video - ");
	if (::ioctl(m_fd_demux, DMX_START) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}

int eDVBVideo::start()
{
	eDebugNoNewLine("VIDEO_PLAY - ");
	if (::ioctl(m_fd, VIDEO_PLAY) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}

int eDVBVideo::stopPid()
{
	eDebugNoNewLine("DEMUX_STOP - video - ");
	if (::ioctl(m_fd_demux, DMX_STOP) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}
#else
int eDVBVideo::startPid(int pid, int type)
{
	int streamtype = VIDEO_STREAMTYPE_MPEG2;

	if ((m_fd < 0) || (m_fd_demux < 0))
		return -1;
	dmx_pes_filter_params pes;

	switch(type)
	{
	default:
		/* un tip pe care nucleul nu il cunoaste ajunge pe MPEG-2, ca pana acum; pmt.cpp nu da decodorului pistele
		   necunoscute (AV1, H.266 VVC, AVS2, AVS3), deci aici nu ar trebui sa vina niciunul */
		eWarning("[eDVBVideo] tip video necunoscut %d, trimis ca MPEG-2", type);
		break;
	case MPEG2:
		break;
	case MPEG4_H264:
		streamtype = VIDEO_STREAMTYPE_MPEG4_H264;
		break;
	case MPEG1:
		streamtype = VIDEO_STREAMTYPE_MPEG1;
		break;
	case MPEG4_Part2:
		streamtype = VIDEO_STREAMTYPE_MPEG4_Part2;
		break;
	case VC1:
		streamtype = VIDEO_STREAMTYPE_VC1;
		break;
	case VC1_SM:
		streamtype = VIDEO_STREAMTYPE_VC1_SM;
		break;
	case H265_HEVC:
		streamtype = VIDEO_STREAMTYPE_H265_HEVC;
		break;
	case CAVS:
		streamtype = VIDEO_STREAMTYPE_CAVS;
		break;
	}

	eDebugNoNewLine("VIDEO_SET_STREAMTYPE %d - ", streamtype);
	if (::ioctl(m_fd, VIDEO_SET_STREAMTYPE, streamtype) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");

	pes.pid      = pid;
	pes.input    = DMX_IN_FRONTEND;
	pes.output   = DMX_OUT_DECODER;
	pes.pes_type = m_dev ? DMX_PES_VIDEO1 : DMX_PES_VIDEO0; /* FIXME */
	pes.flags    = 0;
	eDebugNoNewLine("DMX_SET_PES_FILTER(0x%02x) - video - ", pid);
	if (::ioctl(m_fd_demux, DMX_SET_PES_FILTER, &pes) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	eDebugNoNewLine("DEMUX_START - video - ");
	if (::ioctl(m_fd_demux, DMX_START) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	freeze();  // why freeze here?!? this is a problem when only a pid change is requested... because of the unfreeze logic in Decoder::setState
	eDebugNoNewLine("VIDEO_PLAY - ");
	if (::ioctl(m_fd, VIDEO_PLAY) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
	return 0;
}
#endif

void eDVBVideo::stop()
{
#if HAVE_DVB_API_VERSION > 2
	eDebugNoNewLine("DEMUX_STOP - video - ");
	if (::ioctl(m_fd_demux, DMX_STOP) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
#endif
	eDebugNoNewLine("VIDEO_STOP - ");
	if (::ioctl(m_fd, VIDEO_STOP, 1) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
}

void eDVBVideo::flush()
{
	eDebugNoNewLine("VIDEO_CLEAR_BUFFER - ");
	if (::ioctl(m_fd, VIDEO_CLEAR_BUFFER) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
}

void eDVBVideo::freeze()
{
	eDebugNoNewLine("VIDEO_FREEZE - ");
	if (::ioctl(m_fd, VIDEO_FREEZE) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
}

void eDVBVideo::unfreeze()
{
	eDebugNoNewLine("VIDEO_CONTINUE - ");
	if (::ioctl(m_fd, VIDEO_CONTINUE) < 0)
		eDebug("failed (%m)");
	else
		eDebug("ok");
}

int eDVBVideo::setSlowMotion(int repeat)
{
	eDebugNoNewLine("VIDEO_SLOWMOTION(%d) - ", repeat);
	int ret = ::ioctl(m_fd, VIDEO_SLOWMOTION, repeat);
	if (ret < 0)
		eDebug("failed(%m)");
	else
		eDebug("ok");
	return ret;
}

int eDVBVideo::setFastForward(int skip)
{
	eDebugNoNewLine("VIDEO_FAST_FORWARD(%d) - ", skip);
	int ret = ::ioctl(m_fd, VIDEO_FAST_FORWARD, skip);
	if (ret < 0)
		eDebug("failed(%m)");
	else
		eDebug("ok");
	return ret;
}

int eDVBVideo::getPTS(pts_t &now)
{
#if HAVE_DVB_API_VERSION < 3
	#define VIDEO_GET_PTS_OLD           _IOR('o', 1, unsigned int*)
	unsigned int pts;
	int ret = ::ioctl(m_fd_video, VIDEO_GET_PTS_OLD, &pts);
	now = pts;
	now *= 2;
#else
	int ret = ::ioctl(m_fd, VIDEO_GET_PTS, &now);
#endif
	if (ret < 0)
		eDebug("VIDEO_GET_PTS failed(%m)");
	return ret;
}

eDVBVideo::~eDVBVideo()
{
#if HAVE_HISILICON
	hisiVideoCount--;
#endif
	if (m_fd >= 0)
		::close(m_fd);
	if (m_fd_demux >= 0)
		::close(m_fd_demux);
#if HAVE_DVB_API_VERSION < 3
	if (m_fd_video >= 0)
		::close(m_fd_video);
#endif
}

void eDVBVideo::video_event(int)
{
#if HAVE_DVB_API_VERSION >= 3
	struct video_event evt;
	eDebugNoNewLine("VIDEO_GET_EVENT - ");
	if (::ioctl(m_fd, VIDEO_GET_EVENT, &evt) < 0)
		eDebug("failed (%m)");
	else
	{
		eDebug("ok");
		if (evt.type == VIDEO_EVENT_SIZE_CHANGED)
		{
			struct iTSMPEGDecoder::videoEvent event;
			event.type = iTSMPEGDecoder::videoEvent::eventSizeChanged;
			m_aspect = event.aspect = evt.u.size.aspect_ratio == 0 ? 2 : 3;  // convert dvb api to etsi
			m_height = event.height = evt.u.size.h;
			m_width = event.width = evt.u.size.w;
			/* emit */ m_event(event);
		}
		else if (evt.type == VIDEO_EVENT_FRAME_RATE_CHANGED)
		{
			struct iTSMPEGDecoder::videoEvent event;
			event.type = iTSMPEGDecoder::videoEvent::eventFrameRateChanged;
			m_framerate = event.framerate = evt.u.frame_rate;
			/* emit */ m_event(event);
		}
		else if (evt.type == 16 /*VIDEO_EVENT_PROGRESSIVE_CHANGED*/)
		{
			struct iTSMPEGDecoder::videoEvent event;
			event.type = iTSMPEGDecoder::videoEvent::eventProgressiveChanged;
			m_progressive = event.progressive = evt.u.frame_rate;
			/* emit */ m_event(event);
		}
		else if (evt.type == 17 /*VIDEO_EVENT_GAMMA_CHANGED*/)
		{
			/* dupa enigma2 (GPLv2). Valoarea vine in campul frame_rate:
			   0 gama traditionala SDR, 1 gama traditionala HDR, 2 SMPTE ST 2084 (HDR10), 3 HLG */
			struct iTSMPEGDecoder::videoEvent event;
			event.type = iTSMPEGDecoder::videoEvent::eventGammaChanged;
			m_gamma = event.gamma = evt.u.frame_rate;
			eDebug("[eDVBVideo] gamma %d (0 SDR, 1 HDR, 2 HDR10, 3 HLG)", m_gamma);
			/* emit */ m_event(event);
		}
		else
			eDebug("unhandled DVBAPI Video Event %d", evt.type);
	}
#else
#warning "FIXMEE!! Video Events not implemented for old api"
#endif
}

RESULT eDVBVideo::connectEvent(const sigc::slot<void(struct iTSMPEGDecoder::videoEvent)> &event, ePtr<eConnection> &conn)
{
	conn = new eConnection(this, m_event.connect(event));
	return 0;
}

#if HAVE_HISILICON
/* xres si yres sunt scrise in hexazecimal de driver (2d0, 240); framerate e zecimal, in miimi de cadre pe secunda
   (25000): citit cu %x ar da 0x25000 = 151552, adica 152 de cadre pe bara pana la primul eveniment de rata */
static int readMpegProc(const char *str, int decoder, bool hex = true)
#else
static int readMpegProc(const char *str, int decoder)
#endif
{
	int val = -1;
	char tmp[64];
	sprintf(tmp, "/proc/stb/vmpeg/%d/%s", decoder, str);
	FILE *f = fopen(tmp, "r");
	if (f)
	{
#if HAVE_HISILICON
		if (fscanf(f, hex ? "%x" : "%d", &val) != 1)
#else
		if (fscanf(f, "%x", &val) != 1)
#endif
			val = -1;
		fclose(f);
	}
	return val;
}

static int readApiSize(int fd, int &xres, int &yres, int &aspect)
{
#if HAVE_DVB_API_VERSION >= 3
	video_size_t size;
	if (!::ioctl(fd, VIDEO_GET_SIZE, &size))
	{
		xres = size.w;
		yres = size.h;
		aspect = size.aspect_ratio == 0 ? 2 : 3;  // convert dvb api to etsi
		return 0;
	}
//	eDebug("VIDEO_GET_SIZE failed (%m)");
#endif
	return -1;
}

static int readApiFrameRate(int fd, int &framerate)
{
#if HAVE_DVB_API_VERSION >= 3
	unsigned int frate;
	if (!::ioctl(fd, VIDEO_GET_FRAME_RATE, &frate))
	{
		framerate = frate;	
		return 0;
	}
//	eDebug("VIDEO_GET_FRAME_RATE failed (%m)");
#endif
	return -1;
}

int eDVBVideo::getWidth()
{
	if (m_width == -1)
		readApiSize(m_fd, m_width, m_height, m_aspect);
	if (m_width == -1)
		m_width = readMpegProc("xres", m_dev);
	return m_width;
}

int eDVBVideo::getHeight()
{
	if (m_height == -1)
		readApiSize(m_fd, m_width, m_height, m_aspect);
	if (m_height == -1)
		m_height = readMpegProc("yres", m_dev);
	return m_height;
}

int eDVBVideo::getAspect()
{
	if (m_aspect == -1)
		readApiSize(m_fd, m_width, m_height, m_aspect);
	if (m_aspect == -1)
		m_aspect = readMpegProc("aspect", m_dev);
	return m_aspect;
}

int eDVBVideo::getProgressive()
{
	if (m_progressive == -1)
		m_progressive = readMpegProc("progressive", m_dev);
	return m_progressive;
}

int eDVBVideo::getFrameRate()
{
	if (m_framerate == -1)
		readApiFrameRate(m_fd, m_framerate);
	if (m_framerate == -1)
#if HAVE_HISILICON
		m_framerate = readMpegProc("framerate", m_dev, false);
#else
		m_framerate = readMpegProc("framerate", m_dev);
#endif
	return m_framerate;
}

int eDVBVideo::getGamma()
{
	/* pana vine evenimentul 17 se citeste fisierul driverului,
	   in hexazecimal (/proc/stb/vmpeg/0/gamma exista pe u57 si da 0 pe un canal SDR) */
	if (m_gamma == -1)
		m_gamma = readMpegProc("gamma", m_dev);
	return m_gamma;
}

DEFINE_REF(eDVBPCR);

eDVBPCR::eDVBPCR(eDVBDemux *demux, int dev): m_demux(demux), m_dev(dev)
{
	char filename[128];
#if HAVE_DVB_API_VERSION < 3
	sprintf(filename, "/dev/dvb/card%d/demux%d", demux->adapter, demux->demux);
#else
	sprintf(filename, "/dev/dvb/adapter%d/demux%d", demux->adapter, demux->demux);
#endif
	m_fd_demux = ::open(filename, O_RDWR);
	if (m_fd_demux < 0)
		eWarning("%s: %m", filename);
}

#if HAVE_DVB_API_VERSION < 3
int eDVBPCR::setPid(int pid)
{
	if (m_fd_demux < 0)
		return -1;
	dmx_pes_filter_params pes;

	pes.pid      = pid;
	pes.input    = DMX_IN_FRONTEND;
	pes.output   = DMX_OUT_DECODER;
	pes.pes_type = DMX_PES_PCR;
	pes.flags    = 0;

	eDebugNoNewLine("DMX_SET_PES_FILTER(0x%02x) - pcr - ", pid);
	if (::ioctl(m_fd_demux, DMX_SET_PES_FILTER, &pes) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}

int eDVBPCR::startPid()
{
	if (m_fd_demux < 0)
		return -1;
	eDebugNoNewLine("DEMUX_START - pcr - ");
	if (::ioctl(m_fd_demux, DMX_START) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}
#else
int eDVBPCR::startPid(int pid)
{
	if (m_fd_demux < 0)
		return -1;
	dmx_pes_filter_params pes;

	pes.pid      = pid;
	pes.input    = DMX_IN_FRONTEND;
	pes.output   = DMX_OUT_DECODER;
	pes.pes_type = m_dev ? DMX_PES_PCR1 : DMX_PES_PCR0; /* FIXME */
	pes.flags    = 0;
	eDebugNoNewLine("DMX_SET_PES_FILTER(0x%02x) - pcr - ", pid);
	if (::ioctl(m_fd_demux, DMX_SET_PES_FILTER, &pes) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	eDebugNoNewLine("DEMUX_START - pcr - ");
	if (::ioctl(m_fd_demux, DMX_START) < 0)
	{
		eDebug("failed (%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}
#endif

void eDVBPCR::stop()
{
	eDebugNoNewLine("DEMUX_STOP - pcr - ");
	if (::ioctl(m_fd_demux, DMX_STOP) < 0)
		eDebug("failed(%m)");
	else
		eDebug("ok");
}

eDVBPCR::~eDVBPCR()
{
	if (m_fd_demux >= 0)
		::close(m_fd_demux);
}

DEFINE_REF(eDVBTText);

eDVBTText::eDVBTText(eDVBDemux *demux, int dev)
    :m_demux(demux), m_dev(dev)
{
	char filename[128];
#if HAVE_DVB_API_VERSION < 3
	sprintf(filename, "/dev/dvb/card%d/demux%d", demux->adapter, demux->demux);
#else
	sprintf(filename, "/dev/dvb/adapter%d/demux%d", demux->adapter, demux->demux);
#endif
	m_fd_demux = ::open(filename, O_RDWR);
	if (m_fd_demux < 0)
		eWarning("%s: %m", filename);
}

int eDVBTText::startPid(int pid)
{
	if (m_fd_demux < 0)
		return -1;
	dmx_pes_filter_params pes;

	pes.pid      = pid;
	pes.input    = DMX_IN_FRONTEND;
	pes.output   = DMX_OUT_DECODER;
	pes.pes_type = m_dev ? DMX_PES_TELETEXT1 : DMX_PES_TELETEXT0; // FIXME
	pes.flags    = 0;

	eDebugNoNewLine("DMX_SET_PES_FILTER(0x%02x) - ttx - ", pid);
	if (::ioctl(m_fd_demux, DMX_SET_PES_FILTER, &pes) < 0)
	{
		eDebug("failed(%m)");
		return -errno;
	}
	eDebug("ok");
	eDebugNoNewLine("DEMUX_START - ttx - ");
	if (::ioctl(m_fd_demux, DMX_START) < 0)
	{
		eDebug("failed(%m)");
		return -errno;
	}
	eDebug("ok");
	return 0;
}

void eDVBTText::stop()
{
	eDebugNoNewLine("DEMUX_STOP - ttx - ");
	if (::ioctl(m_fd_demux, DMX_STOP) < 0)
		eDebug("failed(%m)");
	else
		eDebug("ok");
}

eDVBTText::~eDVBTText()
{
	if (m_fd_demux >= 0)
		::close(m_fd_demux);
}

DEFINE_REF(eTSMPEGDecoder);

int eTSMPEGDecoder::setState()
{
	int res = 0;

	int noaudio = (m_state != statePlay) && (m_state != statePause);
	int nott = noaudio; /* actually same conditions */

	if ((noaudio && m_audio) || (!m_audio && !noaudio))
		m_changed |= changeAudio | changeState;

	if ((nott && m_text) || (!m_text && !nott))
		m_changed |= changeText | changeState;

	const char *decoder_states[] = {"stop", "pause", "play", "decoderfastforward", "trickmode", "slowmotion"};
	eDebug("decoder state: %s, vpid=%d, apid=%d", decoder_states[m_state], m_vpid, m_apid);

	int changed = m_changed;
#if HAVE_DVB_API_VERSION < 3
	bool checkAVSync = m_changed & (changeAudio|changeVideo|changePCR);
	if (m_changed & changeAudio && m_audio)
		m_audio->stopPid();
	if (m_changed & changeVideo && m_video)
		m_video->stopPid();
	if (m_changed & changePCR && m_pcr)
	{
		m_pcr->stop();
		m_pcr=0;
		if (!(m_pcrpid >= 0 && m_pcrpid < 0x1ff))
			m_changed &= ~changePCR;
	}
	if (m_changed & changeAudio && m_audio)
	{
		m_audio->stop();
		m_audio=0;
		if (!(m_apid >= 0 && m_apid < 0x1ff))
			m_changed &= ~changeAudio;
	}
	if (m_changed & changeVideo && m_video)
	{
		m_video->stop();
		m_video=0;
		m_video_event_conn=0;
		if (!(m_vpid >= 0 && m_vpid < 0x1ff))
			m_changed &= ~changeVideo;
	}
	if (m_changed & changeVideo)
	{
		m_video = new eDVBVideo(m_demux, m_decoder);
		m_video->connectEvent(sigc::mem_fun(*this, &eTSMPEGDecoder::video_event), m_video_event_conn);
		if (m_video->setPid(m_vpid))
			res -1;
	}
	if (m_changed & changePCR)
	{
		m_pcr = new eDVBPCR(m_demux, m_decoder);
		if (m_pcr->setPid(m_pcrpid))
			res = -1;
	}
	if (m_changed & changeAudio)
	{
		m_audio = new eDVBAudio(m_demux, m_decoder);
		if (m_audio->setPid(m_apid, m_atype))
			res = -1;
	}
	if (m_changed & changePCR)
	{
		if (m_pcr->startPid())
			res = -1;
		m_changed &= ~changePCR;
	}
	else if (checkAVSync && m_audio && m_video)
	{
		if (m_audio->setAVSync(1))
			res = -1;
	}
	if (m_changed & changeVideo)
	{
		if (m_video->startPid() || m_video->start())
			res = -1;
		m_changed &= ~changeVideo;
	}
	if (m_changed & changeAudio)
	{
		if (m_audio->start() || m_audio->startPid())
			res = -1;
		m_changed &= ~changeAudio;
	}
#else
	if (m_changed & changePCR)
	{
		if (m_pcr)
			m_pcr->stop();
		m_pcr = 0;
	}
	if (m_changed & changeVideo)
	{
		if (m_video)
		{
			m_video->stop();
			m_video = 0;
			m_video_event_conn = 0;
		}
	}
	if (m_changed & changeAudio)
	{
		if (m_audio)
			m_audio->stop();
		m_audio = 0;
	}
	if (m_changed & changeText)
	{
		if (m_text)
			m_text->stop();
		m_text = 0;
	}
	if (m_changed & changePCR)
	{
		if ((m_pcrpid >= 0) && (m_pcrpid < 0x1FFF))
		{
			m_pcr = new eDVBPCR(m_demux, m_decoder);
			if (m_pcr->startPid(m_pcrpid))
				res = -1;
		}
		m_changed &= ~changePCR;
	}
	if (m_changed & changeVideo)
	{
		if ((m_vpid >= 0) && (m_vpid < 0x1FFF))
		{
#if HAVE_HISILICON
			/* The still picture stays on its own player until closed. The driver keeps the last selected source
			   for all decoders and applies it to every video command (VIDEO_SET_STREAMTYPE, VIDEO_FREEZE,
			   VIDEO_PLAY, VIDEO_CONTINUE, VIDEO_STOP), not only to a later VIDEO_STOP: with source 0xff the real
			   video would start on the picture player. So the open picture, of this decoder or of another one,
			   is closed first (VIDEO_STOP on the picture player, source back to demux). */
			if (hisiPictureOwner)
				hisiPictureOwner->finishShowSinglePic();
#endif
			m_video = new eDVBVideo(m_demux, m_decoder);
			m_video->connectEvent(sigc::mem_fun(*this, &eTSMPEGDecoder::video_event), m_video_event_conn);
			if (m_video->startPid(m_vpid, m_vtype))
				res = -1;
		}
		m_changed &= ~changeVideo;
	}
	if (m_changed & changeAudio)
	{
		if ((m_apid >= 0) && (m_apid < 0x1FFF) && !noaudio)
		{
			m_audio = new eDVBAudio(m_demux, m_decoder);
			if (m_audio->startPid(m_apid, m_atype))
				res = -1;
		}
		m_changed &= ~changeAudio;
	}
	if (m_changed & changeText)
	{
		if ((m_textpid >= 0) && (m_textpid < 0x1FFF) && !nott)
		{
			m_text = new eDVBTText(m_demux, m_decoder);
			if (m_text->startPid(m_textpid))
				res = -1;
		}
		m_changed &= ~changeText;
	}
#endif

	if (changed & (changeState|changeVideo|changeAudio))
	{
					/* play, slowmotion, fast-forward */
		int state_table[6][4] = 
			{
				/* [stateStop] =                 */ {0, 0, 0},
				/* [statePause] =                */ {0, 0, 0},
				/* [statePlay] =                 */ {1, 0, 0},
				/* [stateDecoderFastForward] =   */ {1, 0, m_ff_sm_ratio},
				/* [stateHighspeedFastForward] = */ {1, 0, 1},
				/* [stateSlowMotion] =           */ {1, m_ff_sm_ratio, 0}
			};
		int *s = state_table[m_state];
		if (changed & (changeState|changeVideo) && m_video)
		{
			m_video->setSlowMotion(s[1]);
			m_video->setFastForward(s[2]);
			if (s[0])
				m_video->unfreeze();
			else
				m_video->freeze();
		}
		if (changed & (changeState|changeAudio) && m_audio)
		{
			if (s[0])
				m_audio->unfreeze();
			else
				m_audio->freeze();
		}
		m_changed &= ~changeState;
	}

#if HAVE_HISILICON
	/* The picture player keeps the picture until it is closed, and neither audio commands nor state changes reach it
	   while this decoder has no video. Sending the same file again would only cost a VIDEO_STOP that blanks the
	   screen and a VIDEO_PLAY on the picture player, in which the driver sleeps about 200 ms on this thread. A zap
	   reaches this point twice (set, then play or the audio track choice), a track change or a pause once more. */
	if (changed && !m_video && m_audio && m_radio_pic.length() && !(hisiPictureOwner == this && hisiPictureFile == m_radio_pic))
#else
	if (changed && !m_video && m_audio && m_radio_pic.length())
#endif
		showSinglePic(m_radio_pic.c_str());

	return res;
}

int eTSMPEGDecoder::m_pcm_delay=-1,
	eTSMPEGDecoder::m_ac3_delay=-1;

RESULT eTSMPEGDecoder::setHwPCMDelay(int delay)
{
	if (delay != m_pcm_delay )
	{
		FILE *fp = fopen("/proc/stb/audio/audio_delay_pcm", "w");
		if (fp)
		{
			fprintf(fp, "%x", delay*90);
			fclose(fp);
			m_pcm_delay = delay;
			return 0;
		}
	}
	return -1;
}

RESULT eTSMPEGDecoder::setHwAC3Delay(int delay)
{
	if ( delay != m_ac3_delay )
	{
		FILE *fp = fopen("/proc/stb/audio/audio_delay_bitstream", "w");
		if (fp)
		{
			fprintf(fp, "%x", delay*90);
			fclose(fp);
			m_ac3_delay = delay;
			return 0;
		}
	}
	return -1;
}


RESULT eTSMPEGDecoder::setPCMDelay(int delay)
{
	return m_decoder == 0 ? setHwPCMDelay(delay) : -1;
}

RESULT eTSMPEGDecoder::setAC3Delay(int delay)
{
	return m_decoder == 0 ? setHwAC3Delay(delay) : -1;
}

eTSMPEGDecoder::eTSMPEGDecoder(eDVBDemux *demux, int decoder)
	: m_demux(demux), 
		m_vpid(-1), m_vtype(-1), m_apid(-1), m_atype(-1), m_pcrpid(-1), m_textpid(-1),
		m_changed(0), m_decoder(decoder), m_video_clip_fd(-1), m_showSinglePicTimer(eTimer::create(eApp))
{
	demux->connectEvent(sigc::mem_fun(*this, &eTSMPEGDecoder::demux_event), m_demux_event_conn);
	CONNECT(m_showSinglePicTimer->timeout, eTSMPEGDecoder::finishShowSinglePic);
	m_state = stateStop;
}

eTSMPEGDecoder::~eTSMPEGDecoder()
{
	finishShowSinglePic();
	m_vpid = m_apid = m_pcrpid = m_textpid = pidNone;
	m_changed = -1;
	setState();
}

RESULT eTSMPEGDecoder::setVideoPID(int vpid, int type)
{
	if ((m_vpid != vpid) || (m_vtype != type))
	{
		m_changed |= changeVideo;
		m_vpid = vpid;
		m_vtype = type;
	}
	return 0;
}

RESULT eTSMPEGDecoder::setAudioPID(int apid, int type)
{
	if ((m_apid != apid) || (m_atype != type))
	{
		m_changed |= changeAudio;
		m_atype = type;
		m_apid = apid;
	}
	return 0;
}

int eTSMPEGDecoder::m_audio_channel = -1;

RESULT eTSMPEGDecoder::setAudioChannel(int channel)
{
	if (channel == -1)
		channel = ac_stereo;
	if (m_decoder == 0 && m_audio_channel != channel)
	{
		if (m_audio)
		{
			m_audio->setChannel(channel);
			m_audio_channel=channel;
		}
		else
			eDebug("eTSMPEGDecoder::setAudioChannel but no audio decoder exist");
	}
	return 0;
}

int eTSMPEGDecoder::getAudioChannel()
{
	return m_audio_channel == -1 ? ac_stereo : m_audio_channel;
}

RESULT eTSMPEGDecoder::setSyncPCR(int pcrpid)
{
	if (m_pcrpid != pcrpid)
	{
		m_changed |= changePCR;
		m_pcrpid = pcrpid;
	}
	return 0;
}

RESULT eTSMPEGDecoder::setTextPID(int textpid)
{
	if (m_textpid != textpid)
	{
		m_changed |= changeText;
		m_textpid = textpid;
	}
	return 0;
}

RESULT eTSMPEGDecoder::setSyncMaster(int who)
{
	return -1;
}

RESULT eTSMPEGDecoder::set()
{
	return setState();
}

RESULT eTSMPEGDecoder::play()
{
	if (m_state == statePlay)
	{
		if (!m_changed)
			return 0;
	} else  
	{
		m_state = statePlay;
		m_changed |= changeState;
	}
	return setState();
}

RESULT eTSMPEGDecoder::pause()
{
	if (m_state == statePause)
		return 0;
	m_state = statePause;
	m_changed |= changeState;
	return setState();
}

RESULT eTSMPEGDecoder::setFastForward(int frames_to_skip)
{
	if ((m_state == stateDecoderFastForward) && (m_ff_sm_ratio == frames_to_skip))
		return 0;

	m_state = stateDecoderFastForward;
	m_ff_sm_ratio = frames_to_skip;
	m_changed |= changeState;
	return setState();

//		return m_video->setFastForward(frames_to_skip);
}

RESULT eTSMPEGDecoder::setSlowMotion(int repeat)
{
	if ((m_state == stateSlowMotion) && (m_ff_sm_ratio == repeat))
		return 0;

	m_state = stateSlowMotion;
	m_ff_sm_ratio = repeat;
	m_changed |= changeState;
	return setState();
}

RESULT eTSMPEGDecoder::setTrickmode()
{
	if (m_state == stateTrickmode)
		return 0;

	m_state = stateTrickmode;
	m_changed |= changeState;
	return setState();
}

RESULT eTSMPEGDecoder::flush()
{
	if (m_audio)
		m_audio->flush();
	if (m_video)
		m_video->flush();
	return 0;
}

void eTSMPEGDecoder::demux_event(int event)
{
	switch (event)
	{
	case eDVBDemux::evtFlush:
		flush();
		break;
	default:
		break;
	}
}

RESULT eTSMPEGDecoder::getPTS(int what, pts_t &pts)
{
	if (what == 0) /* auto */
		what = m_video ? 1 : 2;

	if (what == 1) /* video */
	{
		if (m_video)
			return m_video->getPTS(pts);
		else
			return -1;
	}

	if (what == 2) /* audio */
	{
		if (m_audio)
			return m_audio->getPTS(pts);
		else
			return -1;
	}

	return -1;
}

RESULT eTSMPEGDecoder::setRadioPic(const std::string &filename)
{
	m_radio_pic = filename;
	return 0;
}

#if HAVE_HISILICON
/* When this file exists, a picture file without its own PES header is sent with a header that carries a PTS field
   (value 0) instead of the header without PTS. The driver accepts both: it hands the frame to the picture player
   with "no PTS" (0xffffffff) in the first case and with PTS 0 in the second. */
#define HISI_PICTURE_PTS_FLAG "/etc/enigma2/hds-poza-radio-pts"

/* Video PES header (stream 0xE0, unbounded length) with only a PTS field, laid out as in ISO/IEC 13818-1 2.4.3.6:
   marker bits '10' and PTS_DTS_flags '10', header data length 5, then the 33-bit PTS split 3/15/15 bits, each part
   followed by a marker bit. Returns the header length. */
static size_t hisiPesHeaderWithPts(unsigned char *out, unsigned long long pts)
{
	out[0] = 0x00;
	out[1] = 0x00;
	out[2] = 0x01;
	out[3] = 0xE0;
	out[4] = 0x00;
	out[5] = 0x00;
	out[6] = 0x80;
	out[7] = 0x80;
	out[8] = 0x05;
	out[9] = 0x21 | ((pts >> 29) & 0x0E);
	out[10] = (pts >> 22) & 0xFF;
	out[11] = 0x01 | ((pts >> 14) & 0xFE);
	out[12] = (pts >> 7) & 0xFF;
	out[13] = 0x01 | ((pts << 1) & 0xFE);
	return 14;
}

/* Stream type of a still picture file: H.264 when its first NAL unit (after the PES header, if the file has one) is
   a sequence parameter set (7) or an access unit delimiter (9); MPEG-2 otherwise. An MPEG-2 sequence header
   (00 00 01 B3) never matches: read as a NAL header, 0xB3 has the forbidden bit set. */
static int hisiPictureStreamType(const unsigned char *data, size_t len)
{
	size_t pos = 0;
	if (len >= 9 && data[0] == 0x00 && data[1] == 0x00 && data[2] == 0x01 && (data[3] >> 4) == 0xE)
		pos = 9 + data[8];
	if (pos + 4 <= len && data[pos] == 0x00 && data[pos + 1] == 0x00 && data[pos + 2] == 0x00 && data[pos + 3] == 0x01)
		pos += 4;
	else if (pos + 3 <= len && data[pos] == 0x00 && data[pos + 1] == 0x00 && data[pos + 2] == 0x01)
		pos += 3;
	else
		return VIDEO_STREAMTYPE_MPEG2;
	if (pos >= len || (data[pos] & 0x80))
		return VIDEO_STREAMTYPE_MPEG2;
	int nal_type = data[pos] & 0x1F;
	return (nal_type == 7 || nal_type == 9) ? VIDEO_STREAMTYPE_MPEG4_H264 : VIDEO_STREAMTYPE_MPEG2;
}

/* The kernel lines that tell whether the picture player has the shared memory: when the daemon reports the player
   running after VIDEO_PLAY, the driver prints HISI_KMSG_REPORT and then, in the same call, HISI_KMSG_STARTED only when
   its pointer to the shared memory is set */
#define HISI_KMSG_REPORT "yyyyyyyyyyyyyyyyy"
#define HISI_KMSG_STARTED "-->video start"

/* One record of /dev/kmsg ("<level>,<seq>,<time>,<flags>;<text>\n", maybe followed by " KEY=value" lines) moves the
   state: 0 nothing seen, 1 the report without the start line after it, 2 the start line after the report */
static int hisiKmsgStep(int state, const char *record, size_t len)
{
	const char *text = (const char *)memchr(record, ';', len);
	if (!text)
		return state;
	++text;
	size_t n = (size_t)(record + len - text);
	const char *eol = (const char *)memchr(text, '\n', n);
	if (eol)
		n = (size_t)(eol - text);
	while (n && (text[n - 1] == ' ' || text[n - 1] == '\t' || text[n - 1] == '\r'))
		--n;
	if (n == sizeof(HISI_KMSG_REPORT) - 1 && !memcmp(text, HISI_KMSG_REPORT, n))
		return 1;
	if (state == 1 && n == sizeof(HISI_KMSG_STARTED) - 1 && !memcmp(text, HISI_KMSG_STARTED, n))
		return 2;
	return state;
}

/* Reads the records written to /dev/kmsg since kmsg was moved to its end, before VIDEO_PLAY on the picture player.
   0: the driver got the report of the player without its shared memory, a write() would crash the kernel; 1 otherwise
   (the start line came, or no report came yet: then the check of /proc/vmallocinfo made before opening video0 holds) */
static int hisiPictureStarted(int kmsg)
{
	if (kmsg < 0)
		return 1;
	int state = 0;
	char record[8192];
	for (int attempt = 0; attempt < 2; ++attempt)
	{
		for (int k = 0; k < 4096; ++k)
		{
			ssize_t n = read(kmsg, record, sizeof(record));
			if (n > 0)
				state = hisiKmsgStep(state, record, (size_t)n);
			else if (!(n < 0 && errno == EPIPE)) /* EPIPE: records overwritten meanwhile, the next read goes on */
				break;
		}
		if (state != 1)
			break;
		/* both lines come from one call of the driver: when only the first one is there, look once more */
		usleep(20000);
	}
	return state != 1;
}

#endif
RESULT eTSMPEGDecoder::showSinglePic(const char *filename)
{
	if (m_decoder == 0)
	{
		eDebug("showSinglePic %s", filename);
		int f = open(filename, O_RDONLY);
		if (f >= 0)
		{
			struct stat s;
			fstat(f, &s);
#if HAVE_HISILICON
			/* video0 stays open after a picture (no timer below): close the open picture first, also when it
			   belongs to another decoder instance, so that at most one picture holds video0 */
			if (hisiPictureOwner)
				hisiPictureOwner->finishShowSinglePic();
			/* source 0xff would move the video commands of the other decoder to the picture players */
			if (hisiVideoCount > (m_video ? 1 : 0))
			{
				eDebug("[eTSMPEGDecoder] %s: video runs on another decoder, picture not shown", filename);
				close(f);
				return 0;
			}
			/* without the memory the driver shares with the platform daemon (hisiEsMemoryMapped, lib/dvb/hdspazavideo.h)
			   the first write() on video0 is a kernel oops: video0 is not even opened */
			int mapped = hisiEsMemoryMapped();
			if (mapped != 1)
			{
				eWarning("[eTSMPEGDecoder] %s: %s, a write on video0 would crash the kernel; picture not shown", filename,
					mapped == 0 ? "the video driver has no memory shared with the platform daemon (its mapping failed for "
					"lack of kernel vmalloc space; a restart of the receiver brings it back)" :
					"/proc/vmallocinfo cannot be read, so the memory of the video driver cannot be checked");
				close(f);
				return 0;
			}
#endif
			if (m_video_clip_fd == -1)
				m_video_clip_fd = open("/dev/dvb/adapter0/video0", O_WRONLY);
#if HAVE_HISILICON
			if (m_video_clip_fd >= 0)
				hisiPictureOwner = this;
#endif
			if (m_video_clip_fd >= 0)
			{
				bool seq_end_avail = false;
				size_t pos=0;
				unsigned char pes_header[] = { 0x00, 0x00, 0x01, 0xE0, 0x00, 0x00, 0x80, 0x00, 0x00 };
				unsigned char seq_end[] = { 0x00, 0x00, 0x01, 0xB7 };
				/* on the heap: a large file must not overflow the stack */
				std::vector<unsigned char> iframe(s.st_size > 0 ? s.st_size : 0);
				unsigned char stuffing[8192];
				int streamtype = VIDEO_STREAMTYPE_MPEG2;
				memset(stuffing, 0, 8192);
				ssize_t rd = s.st_size >= 4 ? read(f, iframe.data(), s.st_size) : -1;
				if (rd != s.st_size)
					eDebug("[eTSMPEGDecoder] %s: short or broken picture file, not shown", filename);
				else
				{
#if HAVE_HISILICON
					/* the picture counts as open (setState then does not send it again) only when VIDEO_PLAY and every
					   write reached the driver; after a failure the next setState sends it once more */
					bool hisiSent = true;
					/* false when the driver started the picture player without its shared memory: nothing is written */
					bool hisiWrite = true;
					auto writeAll = [this, &hisiSent, &hisiWrite](const unsigned char *data, size_t len)
					{
						if (!hisiWrite)
						{
							hisiSent = false;
							return;
						}
						if (write(m_video_clip_fd, data, len) < 0)
						{
							hisiSent = false;
							eDebug("[eTSMPEGDecoder] write picture to decoder failed (%m)");
						}
					};
					streamtype = hisiPictureStreamType(iframe.data(), s.st_size);
					const unsigned char *header = pes_header;
					size_t header_len = sizeof(pes_header);
					unsigned char header_pts[14];
					if (access(HISI_PICTURE_PTS_FLAG, F_OK) == 0)
					{
						header_len = hisiPesHeaderWithPts(header_pts, 0);
						header = header_pts;
					}
					eDebug("[eTSMPEGDecoder] picture %s: stream type %d, PES header %s", filename, streamtype,
						(iframe[3] >> 4) == 0xE ? "from the file" : (header == pes_header ? "without PTS" : "with PTS"));
					/* the kernel records written from here on tell whether VIDEO_PLAY could start the picture player
					   with the shared memory (hisiPictureStarted) */
					int kmsg = open("/dev/kmsg", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
					if (kmsg >= 0 && lseek(kmsg, 0, SEEK_END) < 0)
					{
						close(kmsg);
						kmsg = -1;
					}
					/* video0 and audio0 share one player here: source 0xff puts the picture on the separate
					   picture player, source MEMORY would rebuild the shared player without audio */
					if (ioctl(m_video_clip_fd, VIDEO_SELECT_SOURCE, 0xff) < 0)
						eDebug("VIDEO_SELECT_SOURCE 0xff (picture player) failed (%m)");
#else
					auto writeAll = [this](const unsigned char *data, size_t len)
					{
						if (write(m_video_clip_fd, data, len) < 0)
							eDebug("[eTSMPEGDecoder] write picture to decoder failed (%m)");
					};
					if (ioctl(m_video_clip_fd, VIDEO_SELECT_SOURCE, VIDEO_SOURCE_MEMORY) < 0)
						eDebug("VIDEO_SELECT_SOURCE MEMORY failed (%m)");
#endif
					if (ioctl(m_video_clip_fd, VIDEO_SET_STREAMTYPE, streamtype) < 0)
						eDebug("VIDEO_SET_STREAMTYPE failed(%m)");
#if HAVE_HISILICON
					if (ioctl(m_video_clip_fd, VIDEO_PLAY) < 0)
					{
						hisiSent = false;
						eDebug("VIDEO_PLAY failed (%m)");
					}
#else
					if (ioctl(m_video_clip_fd, VIDEO_PLAY) < 0)
						eDebug("VIDEO_PLAY failed (%m)");
#endif
					if (ioctl(m_video_clip_fd, VIDEO_CONTINUE) < 0)
						eDebug("video: VIDEO_CONTINUE: %m");
					if (ioctl(m_video_clip_fd, VIDEO_CLEAR_BUFFER) < 0)
						eDebug("video: VIDEO_CLEAR_BUFFER: %m");
#if HAVE_HISILICON
					/* the last check before the first write(): did the driver have its shared memory when the daemon
					   reported the picture player running? */
					hisiWrite = hisiPictureStarted(kmsg);
					if (kmsg >= 0)
						close(kmsg);
					if (!hisiWrite)
						eWarning("[eTSMPEGDecoder] %s: the video driver started the picture player without the memory it "
							"shares with the platform daemon, a write on video0 would crash the kernel; picture not written",
							filename);
#endif
					while(pos <= (size_t)(s.st_size-4) && !(seq_end_avail = (!iframe[pos] && !iframe[pos+1] && iframe[pos+2] == 1 && iframe[pos+3] == 0xB7)))
						++pos;
					if ((iframe[3] >> 4) != 0xE) // no pes header
#if HAVE_HISILICON
						writeAll(header, header_len);
#else
						writeAll(pes_header, sizeof(pes_header));
#endif
					else
						iframe[4] = iframe[5] = 0x00;
					writeAll(iframe.data(), s.st_size);
					if (!seq_end_avail)
						writeAll(seq_end, sizeof(seq_end));
					writeAll(stuffing, 8192);
#if HAVE_HISILICON
					/* no timer here: the picture stays on the picture player until it is closed by the next
					   picture, by the start of real video on any decoder or by the destructor (finishShowSinglePic) */
					if (hisiSent)
						hisiPictureFile = filename;
					else if (!hisiWrite)
						finishShowSinglePic(); /* picture player stopped and video0 closed; ioctls are safe there */
					else
						eDebug("[eTSMPEGDecoder] picture %s not fully sent, the next state change sends it again", filename);
#else
					m_showSinglePicTimer->start(150, true);
#endif
				}
#if HAVE_HISILICON
				/* nothing was sent for a short or broken file: close video0 without any command, so that no later
				   VIDEO_STOP goes out with source demux, which would reach the player that carries the audio */
				if (rd != s.st_size)
				{
					close(m_video_clip_fd);
					m_video_clip_fd = -1;
					hisiPictureOwner = NULL;
					hisiPictureFile.clear();
				}
#endif
			}
			close(f);
		}
		else
		{
			eDebug("couldnt open %s", filename);
			return -1;
		}
	}
	else
	{
		eDebug("only show single pics on first decoder");
		return -1;
	}
	return 0;
}

void eTSMPEGDecoder::finishShowSinglePic()
{
	if (m_video_clip_fd >= 0)
	{
		if (ioctl(m_video_clip_fd, VIDEO_STOP, 0) < 0)
			eDebug("VIDEO_STOP failed (%m)");
		if (ioctl(m_video_clip_fd, VIDEO_SELECT_SOURCE, VIDEO_SOURCE_DEMUX) < 0)
				eDebug("VIDEO_SELECT_SOURCE DEMUX failed (%m)");
		close(m_video_clip_fd);
		m_video_clip_fd = -1;
	}
#if HAVE_HISILICON
	if (hisiPictureOwner == this)
	{
		hisiPictureOwner = NULL;
		hisiPictureFile.clear();
	}
#endif
}

RESULT eTSMPEGDecoder::connectVideoEvent(const sigc::slot<void(struct videoEvent)> &event, ePtr<eConnection> &conn)
{
	conn = new eConnection(this, m_video_event.connect(event));
	return 0;
}

void eTSMPEGDecoder::video_event(struct videoEvent event)
{
	/* emit */ m_video_event(event);
}

int eTSMPEGDecoder::getVideoWidth()
{
	if (m_video)
		return m_video->getWidth();
	return -1;
}

int eTSMPEGDecoder::getVideoHeight()
{
	if (m_video)
		return m_video->getHeight();
	return -1;
}

int eTSMPEGDecoder::getVideoProgressive()
{
	if (m_video)
		return m_video->getProgressive();
	return -1;
}

int eTSMPEGDecoder::getVideoFrameRate()
{
	if (m_video)
		return m_video->getFrameRate();
	return -1;
}

int eTSMPEGDecoder::getVideoAspect()
{
	if (m_video)
		return m_video->getAspect();
	return -1;
}

int eTSMPEGDecoder::getVideoGamma()
{
	if (m_video)
		return m_video->getGamma();
	return -1;
}
