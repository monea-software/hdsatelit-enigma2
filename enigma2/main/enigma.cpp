/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <unistd.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/ioctl.h>
#include <libsig_comp.h>

#include <lib/actions/action.h>
#include <lib/driver/rc.h>
#include <lib/driver/rcmapper.h>
#include <lib/base/ioprio.h>
#include <lib/base/ebase.h>
#include <lib/base/eenv.h>
#include <lib/base/eerror.h>
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/gdi/gmaindc.h>
#include <lib/gdi/glcddc.h>
#include <lib/gdi/grc.h>
#include <lib/gdi/epng.h>
#include <lib/gdi/font.h>
#include <lib/gui/ebutton.h>
#include <lib/gui/elabel.h>
#include <lib/gui/elistboxcontent.h>
#include <lib/gui/ewidget.h>
#include <lib/gui/ewidgetdesktop.h>
#include <lib/gui/ewindow.h>
#include <lib/python/connections.h>
#include <lib/python/python.h>

#include "bsod.h"
#include "version_info.h"

#ifdef HAVE_GSTREAMER
#include <gst/gst.h>
#endif

#ifdef OBJECT_DEBUG
int object_total_remaining;

void object_dump()
{
	printf("%d items left\n", object_total_remaining);
}
#endif

static eWidgetDesktop *wdsk, *lcddsk;

static int prev_ascii_code;

int getPrevAsciiCode()
{
	int ret = prev_ascii_code;
	prev_ascii_code = 0;
	return ret;
}

/*
 * HDSatelit: fiecare tasta trece prin eRCMapper (lib/driver/rcmapper.h): traducerea telecomenzilor
 * asociate si captura cititorului de coduri. Apasarea lunga se numara inainte, deci ajunge si ea in cititor;
 * tasta tradusa pleaca spre eActionMap cu numele si codul telecomenzii receptorului.
 */
static void deliverKey(eActionMap *actions, const eRCKey &key, int flags)
{
	std::string device = key.producer->getIdentifier();
	int code = key.code;
	eRCMapper *mapper = eRCMapper::getInstance();
	if (mapper && mapper->process(key.producer, device, code, flags))
		return;

	if (flags & eRCKey::flagAscii)
	{
		prev_ascii_code = code;
		actions->keyPressed(device, 510 /* faked KEY_ASCII */, 0);
	}
	else
		actions->keyPressed(device, code, flags);
}

void keyEvent(const eRCKey &key)
{
	static eRCKey last(0, 0, 0);
	static int num_repeat;

	ePtr<eActionMap> ptr;
	eActionMap::getInstance(ptr);

	if ((key.code == last.code) && (key.producer == last.producer) && key.flags & eRCKey::flagRepeat)
		num_repeat++;
	else
	{
		num_repeat = 0;
		last = key;
	}

	if (num_repeat == 4)
	{
		deliverKey(ptr, key, eRCKey::flagLong);
		num_repeat++;
	}

	deliverKey(ptr, key, key.flags);
}

/************************************************/
#include <unistd.h>
#include <lib/components/scan.h>
#include <lib/dvb/idvb.h>
#include <lib/dvb/dvb.h>
#include <lib/dvb/db.h>
#include <lib/dvb/dvbtime.h>
#include <lib/dvb/epgcache.h>

class eMain: public eApplication, public sigc::trackable
{
	eInit init;

	ePtr<eDVBDB> m_dvbdb;
	ePtr<eDVBResourceManager> m_mgr;
	ePtr<eDVBLocalTimeHandler> m_locale_time_handler;
	ePtr<eEPGCache> m_epgcache;

public:
	eMain()
	{
		init.setRunlevel(eAutoInitNumbers::main);
		/* TODO: put into init */
		m_dvbdb = new eDVBDB();
		m_mgr = new eDVBResourceManager();
		m_locale_time_handler = new eDVBLocalTimeHandler();
		m_epgcache = new eEPGCache();
		m_mgr->setChannelList(m_dvbdb);
	}
	
	~eMain()
	{
		m_dvbdb->saveServicelist();
		m_mgr->releaseCachedChannel();
	}
};

int exit_code;

int main(int argc, char **argv)
{
#ifdef MEMLEAK_CHECK
	atexit(DumpUnfreed);
#endif

#ifdef OBJECT_DEBUG
	atexit(object_dump);
#endif

#ifdef HAVE_GSTREAMER
	gst_init(&argc, &argv);
#endif

	// set pythonpath if unset
	setenv("PYTHONPATH", eEnv::resolve("${libdir}/enigma2/python").c_str(), 0);
	printf("PYTHONPATH: %s\n", getenv("PYTHONPATH"));
	
	bsodLogInit();

	ePython python;
	eMain main;

#if 1
	ePtr<gMainDC> my_dc;
	gMainDC::getInstance(my_dc);
	
	//int double_buffer = my_dc->haveDoubleBuffering();

	ePtr<gLCDDC> my_lcd_dc;
	gLCDDC::getInstance(my_lcd_dc);


		/* ok, this is currently hardcoded for arabic. */
			/* some characters are wrong in the regular font, force them to use the replacement font */
	for (int i = 0x60c; i <= 0x66d; ++i)
		eTextPara::forceReplacementGlyph(i);
	eTextPara::forceReplacementGlyph(0xfdf2);
	for (int i = 0xfe80; i < 0xff00; ++i)
		eTextPara::forceReplacementGlyph(i);

	eWidgetDesktop dsk(eSize(720, 576));
	eWidgetDesktop dsk_lcd(my_lcd_dc->size());

	dsk.setStyleID(0);
	dsk_lcd.setStyleID(my_lcd_dc->size().width() == 96 ? 2 : 1);

/*	if (double_buffer)
	{
		eDebug(" - double buffering found, enable buffered graphics mode.");
		dsk.setCompositionMode(eWidgetDesktop::cmBuffered);
	} */
	
	wdsk = &dsk;
	lcddsk = &dsk_lcd;

	dsk.setDC(my_dc);
	dsk_lcd.setDC(my_lcd_dc);

	ePtr<gPixmap> m_pm;
	loadPNG(m_pm, eEnv::resolve("${datadir}/enigma2/skin_default/pal.png").c_str());
	if (!m_pm)
	{
		eFatal("pal.png not found!");
	} else
		dsk.setPalette(*m_pm);

	dsk.setBackgroundColor(gRGB(0,0,0,0xFF));
#endif

		/* redrawing is done in an idle-timer, so we have to set the context */
	dsk.setRedrawTask(main);
	dsk_lcd.setRedrawTask(main);
	
	
	eDebug("Loading spinners...");
	
	{
		int i;
#define MAX_SPINNER 64
		ePtr<gPixmap> wait[MAX_SPINNER];
		for (i=0; i<MAX_SPINNER; ++i)
		{
			char filename[64];
			std::string rfilename;
			snprintf(filename, sizeof(filename), "${datadir}/enigma2/skin_default/spinner/wait%d.png", i + 1);
			rfilename = eEnv::resolve(filename);
			loadPNG(wait[i], rfilename.c_str());
			
			if (!wait[i])
			{
				if (!i)
					eDebug("failed to load %s! (%m)", rfilename.c_str());
				else
					eDebug("found %d spinner!\n", i);
				break;
			}
		}
		if (i)
			/* HDSatelit: in coltul stanga-sus, in zona sigura a ecranului (48 px de la margini, fisa de design Stitch) */
			my_dc->setSpinner(eRect(ePoint(48, 48), wait[0]->size()), wait, i);
		else
			my_dc->setSpinner(eRect(48, 48, 0, 0), wait, 1);
	}
	
	gRC::getInstance()->setSpinnerDC(my_dc);

	eRCInput::getInstance()->keyEvent.connect(sigc::ptr_fun(keyEvent));
	
	printf("executing main\n");
	
	bsodCatchSignals();

	setIoPrio(IOPRIO_CLASS_BE, 3);

//	python.execute("mytest", "__main__");
	/*
	 * execFile returns non-zero when mytest.py ends with an uncaught exception (PyRun_SimpleFile prints the
	 * traceback and returns -1) or cannot be opened. Only runScreenTest() sits in the try that calls
	 * quitMainloop(5); an exception in the module level imports before it left exit_code at 0, which
	 * enigma2.sh reads as a requested restart: no crash screen, no crash log, not counted as a crash, and
	 * init disables the respawn after ten quick restarts. Such an end takes the Python crash path below.
	 * A code already set by quitMainloop() is kept.
	 */
	if (python.execFile(eEnv::resolve("${libdir}/enigma2/python/mytest.py").c_str()) != 0 && exit_code == 0)
		exit_code = 5;

	extern void setFullsize(); // definend in lib/gui/evideo.cpp
	setFullsize();

	if (exit_code == 5) /* python crash */
	{
		eDebug("(exit code 5)");
		bsodFatal(0);
	}
	
	dsk.paint();
	dsk_lcd.paint();

	{
		gPainter p(my_lcd_dc);
		p.resetClip(eRect(ePoint(0, 0), my_lcd_dc->size()));
		p.clear();
		p.flush();
	}

	return exit_code;
}

eWidgetDesktop *getDesktop(int which)
{
	return which ? lcddsk : wdsk;
}

eApplication *getApplication()
{
	return eApp;
}

void quitMainloop(int exitCode)
{
	FILE *f = fopen("/proc/stb/fp/was_timer_wakeup", "w");
	if (f)
	{
		fprintf(f, "%d", 0);
		fclose(f);
	}
	else
	{
		int fd = open("/dev/dbox/fp0", O_WRONLY);
		if (fd >= 0)
		{
			if (ioctl(fd, 10 /*FP_CLEAR_WAKEUP_TIMER*/) < 0)
				eDebug("FP_CLEAR_WAKEUP_TIMER failed (%m)");
			close(fd);
		}
		else
			eDebug("open /dev/dbox/fp0 for wakeup timer clear failed!(%m)");
	}
	exit_code = exitCode;
	eApp->quit(0);
}

static void sigterm_handler(int num)
{
	quitMainloop(128 + num);
}

void runMainloop()
{
	struct sigaction act;

	act.sa_handler = sigterm_handler;
	act.sa_flags = SA_RESTART;

	if (sigemptyset(&act.sa_mask) == -1)
		perror("sigemptyset");
	if (sigaction(SIGTERM, &act, 0) == -1)
		perror("SIGTERM");

	eApp->runLoop();
}

const char *getEnigmaVersionString()
{
	/* "0.6.7 2026-10-25": versiunea din AC_INIT si data comiterii (forma citita de Components/About.py), fara numele
	   ramurii git */
	static std::string version = std::string(PACKAGE_VERSION) + ' ' + enigma2_date;
	return version.c_str();
}

#include <malloc.h>

void dump_malloc_stats(void)
{
#if defined(__GLIBC__) && (__GLIBC__ > 2 || (__GLIBC__ == 2 && __GLIBC_MINOR__ >= 33))
	struct mallinfo2 mi = mallinfo2(); /* mallinfo is deprecated and overflows past 2 GB */
	eDebug("MALLOC: %zu total", mi.uordblks);
#else
	struct mallinfo mi = mallinfo();
	eDebug("MALLOC: %d total", mi.uordblks);
#endif
}
