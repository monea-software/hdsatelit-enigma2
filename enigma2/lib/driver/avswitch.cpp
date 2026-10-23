/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <string.h>

#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/base/eerror.h>
#include <lib/base/ebase.h>
#include <lib/driver/avswitch.h>

eAVSwitch *eAVSwitch::instance = 0;

eAVSwitch::eAVSwitch()
{
	ASSERT(!instance);
	instance = this;
	m_video_mode = 0;
	m_fp_fd = open("/dev/dbox/fp0", O_RDONLY|O_NONBLOCK);
	if (m_fp_fd == -1)
	{
		eDebug("couldnt open /dev/dbox/fp0 to monitor vcr scart slow blanking changed!");
		m_fp_notifier=0;
	}
	else
	{
		m_fp_notifier = eSocketNotifier::create(eApp, m_fp_fd, eSocketNotifier::Read|POLLERR);
		CONNECT(m_fp_notifier->activated, eAVSwitch::fp_event);
	}
}

#ifndef FP_IOCTL_GET_EVENT
#define FP_IOCTL_GET_EVENT 20
#endif

#ifndef FP_IOCTL_GET_VCR
#define FP_IOCTL_GET_VCR 7
#endif

#ifndef FP_EVENT_VCR_SB_CHANGED
#define FP_EVENT_VCR_SB_CHANGED 1
#endif

int eAVSwitch::getVCRSlowBlanking()
{
	int val=0;
	if (m_fp_fd >= 0)
	{
		FILE *f = fopen("/proc/stb/fp/vcr_fns", "r");
		if (f)
		{
			if (fscanf(f, "%d", &val) != 1)
				eDebug("read /proc/stb/fp/vcr_fns failed!! (%m)");
			fclose(f);
		}
		else if (ioctl(m_fp_fd, FP_IOCTL_GET_VCR, &val) < 0)
			eDebug("FP_GET_VCR failed (%m)");
	}
	return val;
}

void eAVSwitch::fp_event(int what)
{
	if (what & POLLERR) // driver not ready for fp polling
	{
		eDebug("fp driver not read for polling.. so disable polling");
		m_fp_notifier->stop();
	}
	else
	{
		FILE *f = fopen("/proc/stb/fp/events", "r");
		if (f)
		{
			int events;
			if (fscanf(f, "%d", &events) != 1)
				eDebug("read /proc/stb/fp/events failed!! (%m)");
			else if (events & FP_EVENT_VCR_SB_CHANGED)
				/* emit */ vcr_sb_notifier(getVCRSlowBlanking());
			fclose(f);
		}
		else
		{
			int val = FP_EVENT_VCR_SB_CHANGED;  // ask only for this event
			if (ioctl(m_fp_fd, FP_IOCTL_GET_EVENT, &val) < 0)
				eDebug("FP_IOCTL_GET_EVENT failed (%m)");
			else if (val & FP_EVENT_VCR_SB_CHANGED)
				/* emit */ vcr_sb_notifier(getVCRSlowBlanking());
		}
	}
}

eAVSwitch::~eAVSwitch()
{
	if ( m_fp_fd >= 0 )
		close(m_fp_fd);
}

eAVSwitch *eAVSwitch::getInstance()
{
	return instance;
}

bool eAVSwitch::haveScartSwitch()
{
	char tmp[255];
	int fd = open("/proc/stb/avs/0/input_choices", O_RDONLY);
	if(fd < 0) {
		eDebug("cannot open /proc/stb/avs/0/input_choices");
		return false;
	}
	/* the /proc text has no terminator: read one byte less and terminate it */
	ssize_t n = read(fd, tmp, sizeof(tmp) - 1);
	close(fd);
	if (n <= 0)
		return false;
	tmp[n] = 0;
	return !!strstr(tmp, "scart");
}

void eAVSwitch::setInput(int val)
{
	/*
	0-encoder
	1-scart
	2-aux
	*/

	const char *input[] = {"encoder", "scart", "aux"};

	int fd;
	
	if((fd = open("/proc/stb/avs/0/input", O_WRONLY)) < 0) {
		eDebug("cannot open /proc/stb/avs/0/input");
		return;
	}

	{ if (write(fd, input[val], strlen(input[val])) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
	close(fd);
}

void eAVSwitch::setColorFormat(int format)
{
	/*
	0-CVBS
	1-RGB
	2-S-Video
	*/
	const char *cvbs="cvbs";
	const char *rgb="rgb";
	const char *svideo="svideo";
	const char *yuv="yuv";
	int fd;
	
	if((fd = open("/proc/stb/avs/0/colorformat", O_WRONLY)) < 0) {
		printf("cannot open /proc/stb/avs/0/colorformat\n");
		return;
	}
	switch(format) {
		case 0:
			{ if (write(fd, cvbs, strlen(cvbs)) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
			break;
		case 1:
			{ if (write(fd, rgb, strlen(rgb)) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
			break;
		case 2:
			{ if (write(fd, svideo, strlen(svideo)) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
			break;
		case 3:
			{ if (write(fd, yuv, strlen(yuv)) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
			break;
	}	
	close(fd);
}

void eAVSwitch::setAspectRatio(int ratio)
{
	/*
	0-4:3 Letterbox
	1-4:3 PanScan
	2-16:9
	3-16:9 forced ("panscan")
	4-16:10 Letterbox
	5-16:10 PanScan
	6-16:9 forced ("letterbox")
	*/
	const char *aspect[] = {"4:3", "4:3", "any", "16:9", "16:10", "16:10", "16:9", "16:9"};
	const char *policy[] = {"letterbox", "panscan", "bestfit", "panscan", "letterbox", "panscan", "letterbox"};

	int fd;
	if((fd = open("/proc/stb/video/aspect", O_WRONLY)) < 0) {
		eDebug("cannot open /proc/stb/video/aspect");
		return;
	}
//	eDebug("set aspect to %s", aspect[ratio]);
	{ if (write(fd, aspect[ratio], strlen(aspect[ratio])) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
	close(fd);

	if((fd = open("/proc/stb/video/policy", O_WRONLY)) < 0) {
		eDebug("cannot open /proc/stb/video/policy");
		return;
	}
//	eDebug("set ratio to %s", policy[ratio]);
	{ if (write(fd, policy[ratio], strlen(policy[ratio])) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
	close(fd);

}

void eAVSwitch::setVideomode(int mode)
{
	const char *pal="pal";
	const char *ntsc="ntsc";
	
	if (mode == m_video_mode)
		return;

	if (mode == 2)
	{
		int fd1 = open("/proc/stb/video/videomode_50hz", O_WRONLY);
		if(fd1 < 0) {
			eDebug("cannot open /proc/stb/video/videomode_50hz");
			return;
		}
		int fd2 = open("/proc/stb/video/videomode_60hz", O_WRONLY);
		if(fd2 < 0) {
			eDebug("cannot open /proc/stb/video/videomode_60hz");
			close(fd1);
			return;
		}
		{ if (write(fd1, pal, strlen(pal)) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
		{ if (write(fd2, ntsc, strlen(ntsc)) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
		close(fd1);
		close(fd2);
	}
	else
	{
		int fd = open("/proc/stb/video/videomode", O_WRONLY);
		if(fd < 0) {
			eDebug("cannot open /proc/stb/video/videomode");
			return;
		}
		switch(mode) {
			case 0:
				{ if (write(fd, pal, strlen(pal)) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
				break;
			case 1:
				{ if (write(fd, ntsc, strlen(ntsc)) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
				break;
			default:
				eDebug("unknown videomode %d", mode);
		}
		close(fd);
	}

	m_video_mode = mode;
}

void eAVSwitch::setWSS(int val) // 0 = auto, 1 = auto(4:3_off)
{
	int fd;
	if((fd = open("/proc/stb/denc/0/wss", O_WRONLY)) < 0) {
		eDebug("cannot open /proc/stb/denc/0/wss");
		return;
	}
	const char *wss[] = {
		"off", "auto", "auto(4:3_off)", "4:3_full_format", "16:9_full_format",
		"14:9_letterbox_center", "14:9_letterbox_top", "16:9_letterbox_center",
		"16:9_letterbox_top", ">16:9_letterbox_center", "14:9_full_format"
	};
	{ if (write(fd, wss[val], strlen(wss[val])) < 0) eDebug("[eAVSwitch] write failed (%m)"); }
//	eDebug("set wss to %s", wss[val]);
	close(fd);
}

//FIXME: correct "run/startlevel"
eAutoInitP0<eAVSwitch> init_avswitch(eAutoInitNumbers::rc, "AVSwitch Driver");
