/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <csignal>
#include <cstring>
#include <cstdio>
#include <stdint.h>
#include <time.h>
#include <unistd.h>
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/gdi/accel.h>
#include <lib/base/eerror.h>
#include <lib/gdi/esize.h>
#include <lib/gdi/epoint.h>
#include <lib/gdi/erect.h>
#include <lib/gdi/gpixmap.h>

gAccel *gAccel::instance;

/*
 * HDSatelit, 0.3.0: 1 while a TDE call runs at drawing time (gAccel::blit and gAccel::fill, with the read back of the
 * pixels), else 0. main/bsod.cpp writes it into the cause of a crash (/tmp/hds-cadere.motiv): a crash during such a
 * call is the proof tools/enigma2.sh needs to turn the 2D acceleration off; any other crash is not put on its account.
 * Defined on every build (always 0 where there is no TDE).
 */
volatile sig_atomic_t hds_tde_in_lucru = 0;

/* On HiSilicon the Dreambox interface (FBIO_ACCEL) does not exist ("BCM accel interface not available - Operation
 * not permitted" in the log), so it is not even tried. */
#ifndef HAVE_HISILICON_ACCEL
#define BCM_ACCEL
#endif

#ifdef ATI_ACCEL
extern int ati_accel_init(void);
extern void ati_accel_close(void);
extern void ati_accel_blit(
		int src_addr, int src_width, int src_height, int src_stride,
		int dst_addr, int dst_width, int dst_height, int dst_stride,
		int src_x, int src_y, int width, int height,
		int dst_x, int dst_y);
extern void ati_accel_fill(
		int dst_addr, int dst_width, int dst_height, int dst_stride,
		int x, int y, int width, int height,
		unsigned long color);
#endif
#ifdef BCM_ACCEL
extern int bcm_accel_init(void);
extern void bcm_accel_close(void);
extern void bcm_accel_blit(
		int src_addr, int src_width, int src_height, int src_stride, int src_format,
		int dst_addr, int dst_width, int dst_height, int dst_stride,
		int src_x, int src_y, int width, int height,
		int dst_x, int dst_y, int dwidth, int dheight,
		int pal_addr, int flags);
extern void bcm_accel_fill(
		int dst_addr, int dst_width, int dst_height, int dst_stride,
		int x, int y, int width, int height,
		unsigned long color);
#endif

#ifdef HAVE_HISILICON_ACCEL
/*
 * HiSilicon 2D engine (TDE) on the u5x boxes (u57), through libhiaccel.so from the dinobot-libs-u57 package, five of
 * its functions (configure --with-libhiaccel).
 *
 * Fallback, always to the CPU drawing (the drawing of an image without the 2D engine):
 * - The library is loaded with dlopen only when the TDE is really used: enigma2 has no NEEDED entry for it and nothing
 *   is needed at build time, so the same binary starts on a box without the library, without /dev/hi_tde, or with
 *   another chip. RTLD_NOW: a symbol the library cannot resolve is a clean dlopen error, not an abort later.
 * - On unless turned off: a new image has no file and tries the TDE. /etc/enigma2/hds-fara-accel is the only switch
 *   that turns it off; it is written by the setting "2D acceleration" (the choice "off"), here after a crash (below),
 *   by tools/enigma2.sh after 3 unclean ends in 10 minutes, or by hand from ssh (touch; the way out when the screen is
 *   unusable). /etc/enigma2/hds-cu-accel, the file of the images where the TDE had to be turned on, is not read:
 *   present or missing, the TDE is on.
 * - What exists is checked first (/dev/hi_tde, the box type, the library file), before the setting, so the state file
 *   also tells a box that has no TDE ("lipsa-...": the setting and the web page are not shown) from one that has it.
 * - /etc/enigma2/hds-accel.pornire is written before dinobot_accel_init and removed after the probe: found at the next
 *   start (enigma2 or the receiver died while the TDE was started, even after a reboot) = hds-fara-accel is written
 *   with the reason and the TDE is not tried again until it is turned on again.
 * - /tmp/hds-accel.activ is written when the TDE is really used (after the probe) and removed when it stops being used
 *   (a failure while running) and at the clean end of enigma2 (~gAccel): found at the next start of the interface =
 *   enigma2 ended without its clean end while the TDE was in use (a crash, or a kill; tools/enigma2.sh puts it back
 *   after a SIGTERM end too, and removes it with the work mark after an end asked for by hds-watchdog, which is not a
 *   crash) = hds-fara-accel is written with the reason, so a crash of the library cannot restart the
 *   interface in a loop. In /tmp (RAM): a power cut or a reboot is not counted as a crash.
 * - /etc/enigma2/hds-accel.lucru is written (on the flash) when the TDE starts drawing and removed at the clean end,
 *   when it stops being used, and 10 minutes later by Components/HdsAccel2D.py (a timer of the main loop: the interface
 *   lived 10 minutes with the TDE). Found at start = the receiver itself restarted in those 10 minutes while the TDE
 *   was drawing (a kernel hang and the hardware watchdog, the sysrq reboot of hds-watchdog, or a power cut), which the
 *   mark in /tmp cannot see. Its first line counts such restarts in a row: the second one writes hds-fara-accel with
 *   the reason, so a TDE that hangs the kernel cannot restart the receiver in a loop, and one power cut is not enough.
 * - While running, every TDE call is timed and the first and last pixel it wrote are read back: too slow or wrong =
 *   the TDE is off until the next start of the interface (one warning in the log, the state file rewritten) and the
 *   same rectangle is drawn again by the CPU at once, so nothing is missing on the screen.
 *
 * - The library exports C++ (mangled) names; the five names below are copied from nm -D of libhiaccel.so (md5
 *   7f7394f5..., the same on the receiver) and the argument types from the declarations other enigma2 builds link with.
 * - Every call is synchronous: HI_TDE2_BeginJob, Bitblit or QuickFill, HI_TDE2_EndJob waiting for the end (at most
 *   100 kernel ticks: 100 ms at HZ=1000, 1 s at HZ=100; hi_tde.ko hands the value to schedule_timeout). The calls
 *   return nothing: an error or a timeout can be seen only from the time and the pixels (above).
 * - dinobot_accel_init() also returns 0 WITHOUT opening the TDE when /dev/si.pid (written by showiframe) is missing,
 *   so its result is not trusted alone: hisiInit() checks the conditions first and hisiProbe() checks the result
 *   (fill and copy in hidden accel memory, read back pixel by pixel) before anything reaches the screen.
 * Not used on purpose:
 * - dinobot_accel_register / dinibot_accel_notify: they copy 44 bytes of a gUnmanagedSurface laid out as in other
 *   enigma2 trees (our gSurface starts with "type", another layout) and copy a whole page on every flush for a double
 *   buffer this image does not have;
 * - 8 bpp sources: the library allocates and frees an MMZ block for the palette on every call;
 * - any blit flag: for the library every non-zero flag means alpha blending (alpha test too), and scaling on the
 *   TDE is soft (the DVB subtitles are scaled in software on purpose, see gPixmap::blit).
 */
#include <dlfcn.h>

typedef int (*hisi_init_fn)(void);
typedef void (*hisi_close_fn)(void);
typedef void (*hisi_blit_fn)(
		int src_addr, int src_width, int src_height, int src_stride, int src_format,
		int dst_addr, int dst_width, int dst_height, int dst_stride,
		int src_x, int src_y, int width, int height,
		int dst_x, int dst_y, int dwidth, int dheight,
		int pal_addr, int pal_size, int flags);
typedef void (*hisi_fill_fn)(
		int dst_addr, int dst_width, int dst_height, int dst_stride,
		int x, int y, int width, int height,
		unsigned long color);
typedef bool (*hisi_alpha_fn)(void);

/* the exported names: int dinobot_accel_init(), void dinobot_accel_close(), void dinobot_accel_blit(20 x int),
 * void dinobot_accel_fill(8 x int, unsigned long), bool dinobot_accel_has_alphablending() */
#define HISI_SYM_INIT "_Z18dinobot_accel_initv"
#define HISI_SYM_CLOSE "_Z19dinobot_accel_closev"
#define HISI_SYM_BLIT "_Z18dinobot_accel_blitiiiiiiiiiiiiiiiiiiii"
#define HISI_SYM_FILL "_Z18dinobot_accel_filliiiiiiiim"
#define HISI_SYM_ALPHA "_Z31dinobot_accel_has_alphablendingv"

/* where the library may be (dinobot-libs-u57 puts it in /usr/lib) */
static const char *const hisi_lib_paths[] = { "/usr/lib/libhiaccel.so", "/lib/libhiaccel.so" };

static struct
{
	hisi_init_fn init;
	hisi_close_fn close;
	hisi_blit_fn blit;
	hisi_fill_fn fill;
	hisi_alpha_fn has_alphablending;
} hisi;

/* restarts in a row found in HISI_WORK_MARK at this start (0 on a usual start), written back into it after the probe */
static int hisi_restarts;

/* exists = the TDE is never touched, everything is drawn by the CPU (the setting, a crash, ssh: touch ...); missing =
 * the TDE is tried, as a new image starts. Its first line (the reason) goes into the state file. */
#define HISI_OFF_FILE "/etc/enigma2/hds-fara-accel"
/* written before dinobot_accel_init, removed after the probe; found at start = the last start died in between */
#define HISI_START_MARK "/etc/enigma2/hds-accel.pornire"
/* exists while the TDE is in use; found at start = the last run of enigma2 did not end cleanly while using it */
#define HISI_RUN_MARK "/tmp/hds-accel.activ"
/* on the flash while the TDE draws, in the first 10 minutes; found at start = the receiver restarted meanwhile. Line 1:
 * how many restarts in a row it has seen before this one (the same path is in Components/HdsAccel2D.py) */
#define HISI_WORK_MARK "/etc/enigma2/hds-accel.lucru"
/* restarts in a row, with the TDE drawing in the first 10 minutes, that turn it off */
#define HISI_MAX_RESTARTS 2
/* what really happened: "pornit"/"oprit"/"asteapta", a code, details (read by the setting and the web page) */
#define HISI_STATE_FILE "/tmp/hds-accel.stare"
/* A TDE job is a system call round trip: small rectangles are faster on the CPU. The threshold
 * (GFX_SURFACE_FILL_ACCELERATION_THRESHOLD) is in bytes of the destination rectangle. */
#define HISI_MIN_BYTES 80000
/* a TDE call that takes this long hit the library's wait (100 kernel ticks) or the engine is stuck: a full HD fill
 * takes a few ms */
#define HISI_MAX_US 100000L

enum { HISI_ON = 0, HISI_OFF = 1, HISI_WAIT_PROBE = 2 };

static long hisi_us_since(const struct timespec &t0)
{
	struct timespec t1;
	clock_gettime(CLOCK_MONOTONIC, &t1);
	return (t1.tv_sec - t0.tv_sec) * 1000000L + (t1.tv_nsec - t0.tv_nsec) / 1000;
}

/* the 32 bpp pixel (x, y) of a surface, read from the memory (after a TDE job) */
static uint32_t hisi_pixel(const gSurface *s, int x, int y)
{
	return *(const volatile uint32_t *)((const unsigned char *)s->data + (long)y * s->stride + (long)x * 4);
}

/* the rectangle lies inside the surface */
static bool hisi_inside(const gSurface *s, const eRect &r)
{
	return (r.left() >= 0) && (r.top() >= 0) && (r.right() <= s->x) && (r.bottom() <= s->y);
}

/* the first line of a small text file (the reason in hds-fara-accel), without the end of line; empty if none */
static void hisi_first_line(const char *path, char *out, size_t n)
{
	out[0] = 0;
	FILE *f = fopen(path, "r");
	if (!f)
		return;
	if (!fgets(out, (int)n, f))
		out[0] = 0;
	fclose(f);
	out[strcspn(out, "\r\n")] = 0;
}

/* durable: on the flash before the next step (the start mark must survive a receiver that hangs right after it) */
static void hisi_write_file(const char *path, const char *text, bool durable = false)
{
	FILE *f = fopen(path, "w");
	if (f)
	{
		fputs(text, f);
		if (durable && (fflush(f) == 0))
			fsync(fileno(f));
		fclose(f);
	}
}

/* a function of the library, or 0 (a data pointer from dlsym, copied into the function pointer) */
template <typename T> static bool hisi_symbol(void *lib, const char *name, T &fn)
{
	static_assert(sizeof(T) == sizeof(void *), "dlsym gives a data pointer");
	void *p = dlsym(lib, name);
	fn = 0;
	if (!p)
		return false;
	memcpy(&fn, &p, sizeof(fn));
	return true;
}

/* the CPU fill of gPixmap::fill, only for the timing in the probe */
static void hisi_cpu_fill(unsigned char *base, int stride, int x0, int y0, int w, int h, uint32_t col)
{
	for (int y = y0; y < y0 + h; ++y)
	{
		uint32_t *d = (uint32_t *)(base + y * stride) + x0;
		for (int x = 0; x < w; ++x)
			*d++ = col;
	}
}

/* index of the first pixel of a w x h block that differs from "expected", or -1 */
static int hisi_compare(const unsigned char *base, int stride, const uint32_t *expected, int w, int h)
{
	for (int y = 0; y < h; ++y)
	{
		const volatile uint32_t *s = (const volatile uint32_t *)(base + y * stride);
		for (int x = 0; x < w; ++x)
			if (s[x] != expected[y * w + x])
				return y * w + x;
	}
	return -1;
}
#endif

gAccel::gAccel()
{
	m_accel_addr = 0;
	m_accel_phys_addr = 0;
	m_accel_size = 0;
	m_accel_allocation = 0;
	m_bcm_accel_state = 1; /* 0 = the Dreambox interface works */
	m_hisi_state = 1;      /* HISI_OFF */
	m_hisi_opened = 0;
	instance = this;

#ifdef ATI_ACCEL	
	ati_accel_init();
#endif
#ifdef BCM_ACCEL	
	m_bcm_accel_state = bcm_accel_init();
#endif
#ifdef HAVE_HISILICON_ACCEL
	hisiInit();
#endif
}

gAccel::~gAccel()
{
#ifdef ATI_ACCEL
	ati_accel_close();
#endif
#ifdef BCM_ACCEL
	if (!m_bcm_accel_state)
		bcm_accel_close();
#endif
#ifdef HAVE_HISILICON_ACCEL
	/* the library stays loaded until the process ends (no dlclose) */
	if (m_hisi_opened && hisi.close)
		hisi.close();
	m_hisi_opened = 0;
	/* the clean end of enigma2: the TDE did not take the interface down (nor the receiver) */
	if (access(HISI_RUN_MARK, F_OK) == 0)
		unlink(HISI_RUN_MARK);
	if (access(HISI_WORK_MARK, F_OK) == 0)
		unlink(HISI_WORK_MARK);
#endif
	instance = 0;
}

gAccel *gAccel::getInstance()
{
	return instance;
}
 
void gAccel::setAccelMemorySpace(void *addr, int phys_addr, int size)
{
	if (m_accel_allocation)
		delete[] m_accel_allocation;
	
	m_accel_size = size >> 12;
	
	m_accel_allocation = new int[m_accel_size];
	memset(m_accel_allocation, 0, sizeof(int)*m_accel_size);
	
	m_accel_addr = addr;
	m_accel_phys_addr = phys_addr;

#ifdef HAVE_HISILICON_ACCEL
	/* first call (720x576 at start): nothing is allocated yet, the probe can use the end of this memory */
	if (m_hisi_state == HISI_WAIT_PROBE)
		hisiProbe();
#endif
}

#ifdef HAVE_HISILICON_ACCEL
/* warn: a failure while running (one warning in the log); the start decisions are debug lines */
void gAccel::hisiSetState(int state, const char *code, const char *detail, bool warn)
{
	char text[240];
	snprintf(text, sizeof(text), "%s", detail ? detail : "");
	for (char *c = text; *c; ++c)
		if ((*c == '\n') || (*c == '\r'))
			*c = ' ';
	m_hisi_state = state;
	const char *word = state == HISI_ON ? "pornit" : (state == HISI_OFF ? "oprit" : "asteapta");
	if (warn)
		eWarning("[gAccel] TDE HiSilicon: %s (%s) %s; desenul ramane pe procesor pana la repornirea interfetei",
			word, code, text);
	else
		eDebug("[gAccel] TDE HiSilicon: %s (%s) %s", word, code, text);
	FILE *f = fopen(HISI_STATE_FILE, "w");
	if (f)
	{
		fprintf(f, "%s\n%s\n%s\n", word, code, text);
		fclose(f);
	}
}

void gAccel::hisiInit()
{
	char detail[200];
	m_hisi_state = HISI_OFF;
	hisi_restarts = 0;

	/* 1. is there a 2D engine this binary can use? Nothing of the library is loaded yet. */
	if (access("/dev/hi_tde", F_OK) != 0)
	{
		hisiSetState(HISI_OFF, "lipsa-tde", "/dev/hi_tde");
		return;
	}
	char box[16];
	box[0] = 0;
	FILE *f = fopen("/proc/stb/info/boxtype", "r");
	if (f)
	{
		if (!fgets(box, sizeof(box), f))
			box[0] = 0;
		fclose(f);
	}
	box[strcspn(box, "\r\n")] = 0;
	if (strncmp(box, "u5", 2) && strncmp(box, "u4", 2))
	{
		hisiSetState(HISI_OFF, "alt-receptor", box);
		return;
	}
	const char *lib = 0;
	for (unsigned int i = 0; i < sizeof(hisi_lib_paths) / sizeof(hisi_lib_paths[0]); ++i)
		if (access(hisi_lib_paths[i], F_OK) == 0)
		{
			lib = hisi_lib_paths[i];
			break;
		}
	if (!lib)
	{
		hisiSetState(HISI_OFF, "lipsa-biblioteca", "libhiaccel.so");
		return;
	}

	/* 2. the setting: on unless hds-fara-accel exists. The marks left from before mean nothing while the TDE is off:
	 * removed, so they cannot stop a later start the user chose (only when they exist: no flash write) */
	if (access(HISI_OFF_FILE, F_OK) == 0)
	{
		if (access(HISI_START_MARK, F_OK) == 0)
			unlink(HISI_START_MARK);
		if (access(HISI_RUN_MARK, F_OK) == 0)
			unlink(HISI_RUN_MARK);
		if (access(HISI_WORK_MARK, F_OK) == 0)
			unlink(HISI_WORK_MARK);
		hisi_first_line(HISI_OFF_FILE, detail, sizeof(detail));
		hisiSetState(HISI_OFF, "setare", detail[0] ? detail : HISI_OFF_FILE);
		return;
	}

	/* 3. the start before this one died between dinobot_accel_init and the end of the probe */
	if (access(HISI_START_MARK, F_OK) == 0)
	{
		unlink(HISI_START_MARK);
		if (access(HISI_WORK_MARK, F_OK) == 0)
			unlink(HISI_WORK_MARK);
		hisi_write_file(HISI_OFF_FILE, "oprita automat: pornirea placii 2D de data trecuta nu s-a terminat\n"
			"Se porneste din nou din setari (Accelerare 2D) sau se sterge acest fisier.\n", true);
		hisiSetState(HISI_OFF, "cadere", HISI_START_MARK);
		return;
	}
	/* the run before this one ended without the clean end of enigma2 while the TDE was in use */
	if (access(HISI_RUN_MARK, F_OK) == 0)
	{
		unlink(HISI_RUN_MARK);
		if (access(HISI_WORK_MARK, F_OK) == 0)
			unlink(HISI_WORK_MARK);
		hisi_write_file(HISI_OFF_FILE, "oprita automat: interfata s-a oprit neasteptat cat placa 2D era folosita\n"
			"Se porneste din nou din setari (Accelerare 2D) sau se sterge acest fisier.\n", true);
		hisiSetState(HISI_OFF, "cadere-in-lucru", HISI_RUN_MARK);
		return;
	}
	/* the receiver restarted (the mark in /tmp is gone) in the first 10 minutes of the last run that used the TDE: one
	 * restart may be a power cut, the second in a row turns the TDE off. The mark is removed now; the probe writes it
	 * again with the count. */
	if (access(HISI_WORK_MARK, F_OK) == 0)
	{
		hisi_first_line(HISI_WORK_MARK, detail, sizeof(detail));
		unlink(HISI_WORK_MARK);
		int seen = 0;
		for (const char *c = detail; (*c >= '0') && (*c <= '9') && (seen < 1000); ++c)
			seen = seen * 10 + (*c - '0');
		hisi_restarts = seen + 1;
		if (hisi_restarts >= HISI_MAX_RESTARTS)
		{
			char text[240];
			snprintf(text, sizeof(text), "oprita automat: receptorul a repornit de %d ori la rand in primele 10 minute cat "
				"placa 2D desena (blocare sau pana de curent)\n"
				"Se porneste din nou din setari (Accelerare 2D) sau se sterge acest fisier.\n", hisi_restarts);
			hisi_write_file(HISI_OFF_FILE, text, true);
			hisiSetState(HISI_OFF, "repornire", HISI_WORK_MARK);
			return;
		}
	}
	if (access("/dev/si.pid", F_OK) != 0)
	{
		hisiSetState(HISI_OFF, "lipsa-showiframe", "/dev/si.pid");
		return;
	}

	/* 4. the library and its five functions, then the engine; the mark stays until the end of the probe */
	hisi_write_file(HISI_START_MARK, "pornirea placii 2D in curs\n", true);
	void *handle = dlopen(lib, RTLD_NOW | RTLD_LOCAL);
	if (!handle)
	{
		const char *e = dlerror();
		unlink(HISI_START_MARK);
		snprintf(detail, sizeof(detail), "%s", e ? e : lib);
		hisiSetState(HISI_OFF, "biblioteca", detail);
		return;
	}
	const char *missing = 0;
	if (!hisi_symbol(handle, HISI_SYM_INIT, hisi.init))
		missing = HISI_SYM_INIT;
	else if (!hisi_symbol(handle, HISI_SYM_CLOSE, hisi.close))
		missing = HISI_SYM_CLOSE;
	else if (!hisi_symbol(handle, HISI_SYM_BLIT, hisi.blit))
		missing = HISI_SYM_BLIT;
	else if (!hisi_symbol(handle, HISI_SYM_FILL, hisi.fill))
		missing = HISI_SYM_FILL;
	else if (!hisi_symbol(handle, HISI_SYM_ALPHA, hisi.has_alphablending))
		missing = HISI_SYM_ALPHA;
	if (missing)
	{
		/* nothing of the library was called: it stays loaded but unused (no dlclose) */
		memset(&hisi, 0, sizeof(hisi));
		unlink(HISI_START_MARK);
		hisiSetState(HISI_OFF, "functie", missing);
		return;
	}
	int ret = hisi.init();
	/* dinobot_accel_close() is safe after any result: it closes only what init opened (its descriptors start at -1) */
	m_hisi_opened = 1;
	if (ret)
	{
		unlink(HISI_START_MARK);
		snprintf(detail, sizeof(detail), "dinobot_accel_init = %d", ret);
		hisiSetState(HISI_OFF, "init", detail);
		return;
	}
	snprintf(detail, sizeof(detail), "alfa pe placa: %s", hisi.has_alphablending() ? "da" : "nu");
	hisiSetState(HISI_WAIT_PROBE, "asteapta-proba", detail);
}

/* a TDE call gave a wrong result while running: the CPU draws from now on (the caller draws this rectangle again) */
void gAccel::hisiRuntimeFail(const char *what, long us, unsigned int got, unsigned int want)
{
	char detail[200];
	if (us >= HISI_MAX_US)
		snprintf(detail, sizeof(detail), "%s pe placa: %ld us (cel mult %ld us)", what, us, HISI_MAX_US);
	else
		snprintf(detail, sizeof(detail), "%s pe placa: pixelul are 0x%08x, trebuia 0x%08x", what, got, want);
	hisiSetState(HISI_OFF, "eroare", detail, true);
	/* the TDE is not used any more: a later crash or restart is not its doing */
	unlink(HISI_RUN_MARK);
	unlink(HISI_WORK_MARK);
}

void gAccel::hisiProbe()
{
	const int pw = 64, ph = 64, pstride = pw * 4, pbytes = pstride * ph;       /* two blocks of 16 KB */
	const int tw = 1920, th = 1080, tstride = tw * 4, tbytes = tstride * th;  /* one full HD page, for the timing */
	char detail[240];
	long total = (long)m_accel_size << 12;
	if (!m_accel_addr || !m_accel_phys_addr || total < 2L * pbytes)
	{
		unlink(HISI_START_MARK);
		snprintf(detail, sizeof(detail), "%ld octeti", total);
		hisiSetState(HISI_OFF, "memorie", detail);
		return;
	}
	bool timing = total >= 2L * pbytes + tbytes;
	/* at the END of the accel memory: nothing is allocated yet, and this part never becomes a framebuffer page,
	 * not even after the switch from 720x576 to 1920x1080 (the pages grow from the start) */
	long off = total - 2L * pbytes - (timing ? tbytes : 0);
	unsigned char *a = (unsigned char *)m_accel_addr + off;
	unsigned char *b = a + pbytes;
	unsigned char *t = b + pbytes;
	int pa = m_accel_phys_addr + (int)off, pb = pa + pbytes, pt = pb + pbytes;

	/* HISI_START_MARK is there since hisiInit, before dinobot_accel_init; removed at the end of the probe */
	uint32_t *ea = new uint32_t[pw * ph]; /* what block A must contain */
	uint32_t *eb = new uint32_t[pw * ph]; /* what block B must contain */
	const char *test = 0;
	int bad = -1;
	uint32_t got = 0, want = 0;

	/* 0. the CPU writes and reads back (the mapping itself) */
	memset(a, 0, pbytes);
	memset(b, 0, pbytes);
	for (int i = 0; i < pw * ph; ++i)
		ea[i] = eb[i] = 0;
	if ((bad = hisi_compare(a, pstride, ea, pw, ph)) >= 0)
		test = "procesor";
	/* 1. fill of the whole block */
	if (!test)
	{
		hisi.fill(pa, pw, ph, pstride, 0, 0, pw, ph, 0x5a3c96e1);
		for (int i = 0; i < pw * ph; ++i)
			ea[i] = 0x5a3c96e1;
		if ((bad = hisi_compare(a, pstride, ea, pw, ph)) >= 0)
			test = "umplere";
	}
	/* 2. fill of a rectangle inside: position and stride, the rest must stay as it was */
	if (!test)
	{
		hisi.fill(pa, pw, ph, pstride, 8, 16, 24, 12, 0x81c3e7ff);
		for (int y = 16; y < 28; ++y)
			for (int x = 8; x < 32; ++x)
				ea[y * pw + x] = 0x81c3e7ff;
		if ((bad = hisi_compare(a, pstride, ea, pw, ph)) >= 0)
			test = "umplere-dreptunghi";
	}
	/* 3. copy of the whole block A -> B, a pattern written by the CPU */
	if (!test)
	{
		for (int y = 0; y < ph; ++y)
		{
			uint32_t *d = (uint32_t *)(a + y * pstride);
			for (int x = 0; x < pw; ++x)
				d[x] = ea[y * pw + x] = ((uint32_t)(y * pw + x) * 2654435761u) ^ 0x13572468u;
		}
		hisi.blit(pa, pw, ph, pstride, 0, pb, pw, ph, pstride,
			0, 0, pw, ph, 0, 0, pw, ph, 0, 0, 0);
		for (int i = 0; i < pw * ph; ++i)
			eb[i] = ea[i];
		if ((bad = hisi_compare(b, pstride, eb, pw, ph)) >= 0)
			test = "copiere";
	}
	/* 4. copy of a rectangle to another place: source and destination offsets */
	if (!test)
	{
		hisi.blit(pa, pw, ph, pstride, 0, pb, pw, ph, pstride,
			4, 4, 32, 20, 24, 40, 32, 20, 0, 0, 0);
		for (int y = 0; y < 20; ++y)
			for (int x = 0; x < 32; ++x)
				eb[(40 + y) * pw + 24 + x] = ea[(4 + y) * pw + 4 + x];
		if ((bad = hisi_compare(b, pstride, eb, pw, ph)) >= 0)
			test = "copiere-dreptunghi";
	}
	if (test)
	{
		const uint32_t *e = strncmp(test, "copiere", 7) ? ea : eb;
		const unsigned char *m = strncmp(test, "copiere", 7) ? a : b;
		want = e[bad];
		got = *(const volatile uint32_t *)(m + (bad / pw) * pstride + (bad % pw) * 4);
	}
	delete[] ea;
	delete[] eb;

	long tde_big = -1, cpu_big = -1, tde_small = -1, cpu_small = -1;
	if (!test)
	{
		struct timespec t0;
		if (timing)
		{
			clock_gettime(CLOCK_MONOTONIC, &t0);
			hisi.fill(pt, tw, th, tstride, 0, 0, tw, th, 0);
			tde_big = hisi_us_since(t0);
			clock_gettime(CLOCK_MONOTONIC, &t0);
			hisi_cpu_fill(t, tstride, 0, 0, tw, th, 0);
			cpu_big = hisi_us_since(t0);
		}
		clock_gettime(CLOCK_MONOTONIC, &t0);
		for (int i = 0; i < 10; ++i)
			hisi.fill(pa, pw, ph, pstride, 0, 0, pw, ph, 0);
		tde_small = hisi_us_since(t0) / 10;
		clock_gettime(CLOCK_MONOTONIC, &t0);
		for (int i = 0; i < 10; ++i)
			hisi_cpu_fill(a, pstride, 0, 0, pw, ph, 0);
		cpu_small = hisi_us_since(t0) / 10;
	}
	/* leave the memory clean for the surfaces that will be allocated there */
	memset(a, 0, pbytes);
	memset(b, 0, pbytes);
	unlink(HISI_START_MARK);

	if (test)
	{
		snprintf(detail, sizeof(detail), "proba %s: pixelul %d are 0x%08x, trebuia 0x%08x (adresa 0x%x)",
			test, bad, (unsigned int)got, (unsigned int)want, (unsigned int)pa);
		hisiSetState(HISI_OFF, "proba", detail);
		return;
	}
	snprintf(detail, sizeof(detail),
		"adresa accel 0x%x; umplere 1920x1080: TDE %ld us, procesor %ld us; umplere 64x64: TDE %ld us, procesor %ld us",
		(unsigned int)m_accel_phys_addr, tde_big, cpu_big, tde_small, cpu_small);
	/* from here the TDE draws the screen: both marks removed at the clean end (~gAccel) or when it stops being used;
	 * the one on the flash also after 10 minutes (Components/HdsAccel2D.py) */
	char work[160];
	snprintf(work, sizeof(work), "%d\nporniri la rand cu placa 2D incheiate de o repornire a receptorului in primele 10 "
		"minute\n", hisi_restarts);
	hisi_write_file(HISI_WORK_MARK, work, true);
	hisi_write_file(HISI_RUN_MARK, "placa 2D folosita\n");
	hisiSetState(HISI_ON, "ok", detail);
}
#endif

int gAccel::blit(gSurface *dst, const gSurface *src, const eRect &p, const eRect &area, int flags)
{
#ifdef ATI_ACCEL
	ati_accel_blit(
		src->data_phys, src->x, src->y, src->stride,
		dst->data_phys, dst->x, dst->y, dst->stride, 
		area.left(), area.top(), area.width(), area.height(),
		p.x(), p.y());
	return 0;
#endif
#ifdef BCM_ACCEL
	if (!m_bcm_accel_state)
	{
		if (flags & (gPixmap::blitAlphaTest|gPixmap::blitAlphaBlend)) /* unsupported flags */
			return -1;
		unsigned long pal_addr = 0;
		int src_format = 0;
		if (src->bpp == 32)
			src_format = 0;
		else if ((src->bpp == 8) && src->clut.data)
		{
			src_format = 1;
			/* sync pal */
			int i;
			pal_addr = src->stride * src->y;
			__u32 *pal = (__u32*)(((unsigned char*)src->data) + pal_addr); /* 32 bit ARGB entries */
			pal_addr += src->data_phys;
			for (i = 0; i < src->clut.colors; ++i)
				*pal++ = src->clut.data[i].argb() ^ 0xFF000000;
		} else
			return -1; /* unsupported source format */

		bcm_accel_blit(
			src->data_phys, src->x, src->y, src->stride, src_format,
			dst->data_phys, dst->x, dst->y, dst->stride, 
			area.left(), area.top(), area.width(), area.height(),
			p.x(), p.y(), p.width(), p.height(),
			pal_addr, flags);
		return 0;
	}
#endif
#ifdef HAVE_HISILICON_ACCEL
	if (m_hisi_state == HISI_ON)
	{
		/* only plain copies 32 bpp -> 32 bpp: no flag (alpha, alpha test, scaling), no 8 bpp, no scaling, no copy
		 * inside the same surface (overlapping rectangles), nothing small (see the notes above) */
		if (flags || src->bpp != 32 || dst->bpp != 32 || src == dst)
			return -1;
		if (p.width() != area.width() || p.height() != area.height())
			return -1;
		if (area.width() * area.height() * 4 < HISI_MIN_BYTES)
			return -1;
		/* both rectangles inside their surfaces (what the check below reads back); else the CPU, as without TDE */
		if (!src->data || !dst->data || !hisi_inside(src, area) || !hisi_inside(dst, p))
			return -1;
		struct timespec t0;
		clock_gettime(CLOCK_MONOTONIC, &t0);
		hds_tde_in_lucru = 1;
		hisi.blit(
			src->data_phys, src->x, src->y, src->stride, 0,
			dst->data_phys, dst->x, dst->y, dst->stride,
			area.left(), area.top(), area.width(), area.height(),
			p.x(), p.y(), p.width(), p.height(),
			0, 0, 0);
		long us = hisi_us_since(t0);
		/* the first and the last pixel copied must be those of the source */
		uint32_t got = hisi_pixel(dst, p.left(), p.top()), want = hisi_pixel(src, area.left(), area.top());
		if (got == want)
		{
			got = hisi_pixel(dst, p.right() - 1, p.bottom() - 1);
			want = hisi_pixel(src, area.right() - 1, area.bottom() - 1);
		}
		hds_tde_in_lucru = 0;
		if ((us >= HISI_MAX_US) || (got != want))
		{
			hisiRuntimeFail("copiere", us, got, want);
			return -1; /* gPixmap::blit copies the same rectangle on the CPU */
		}
		return 0;
	}
#endif
	return -1;
}

int gAccel::fill(gSurface *dst, const eRect &area, unsigned long col)
{
#ifdef ATI_ACCEL
	ati_accel_fill(
		dst->data_phys, dst->x, dst->y, dst->stride, 
		area.left(), area.top(), area.width(), area.height(),
		col);
	return 0;
#endif
#ifdef BCM_ACCEL
	if (!m_bcm_accel_state) {
		bcm_accel_fill(
			dst->data_phys, dst->x, dst->y, dst->stride,
			area.left(), area.top(), area.width(), area.height(),
			col);
		return 0;
	}
#endif
#ifdef HAVE_HISILICON_ACCEL
	if (m_hisi_state == HISI_ON)
	{
		/* 32 bpp only (the library fills ARGB8888), and only big rectangles: small ones are faster on the CPU */
		if (dst->bpp != 32 || area.width() * area.height() * 4 < HISI_MIN_BYTES)
			return -1;
		if (!dst->data || !hisi_inside(dst, area))
			return -1;
		struct timespec t0;
		clock_gettime(CLOCK_MONOTONIC, &t0);
		hds_tde_in_lucru = 1;
		hisi.fill(
			dst->data_phys, dst->x, dst->y, dst->stride,
			area.left(), area.top(), area.width(), area.height(),
			col);
		long us = hisi_us_since(t0);
		/* the first and the last pixel must have the colour exactly (ARGB8888, as the probe checked) */
		const uint32_t want = (uint32_t)col;
		uint32_t got = hisi_pixel(dst, area.left(), area.top());
		if (got == want)
			got = hisi_pixel(dst, area.right() - 1, area.bottom() - 1);
		hds_tde_in_lucru = 0;
		if ((us >= HISI_MAX_US) || (got != want))
		{
			hisiRuntimeFail("umplere", us, got, want);
			return -1; /* gPixmap::fill fills the same rectangle on the CPU */
		}
		return 0;
	}
#endif
	return -1;
}

int gAccel::accelAlloc(void *&addr, int &phys_addr, int size)
{
	eDebug("accel %d bytes", size);
	if ((!size) || (!m_accel_allocation))
	{
		eDebug("size: %d, alloc %p", size, m_accel_allocation);
		addr = 0;
		phys_addr = 0;
		return -1;
	}
	
	size += 4095; size >>= 12;
	int i;
	
	int used = 0, free = 0, s = 0;
	for (i=0; i < m_accel_size; ++i)
	{
		if (m_accel_allocation[i] == 0)
			free++;
		else if (m_accel_allocation[i] == -1)
			used++;
		else
		{
			used++;
			s += m_accel_allocation[i];
		}
	}
	eDebug("accel memstat: used=%d kB, free %d kB, s %d kB", used * 4, free * 4, s * 4);

	for (i=0; i < m_accel_size - size; ++i)
	{
		int a;
		for (a=0; a<size; ++a)
			if (m_accel_allocation[i+a])
				break;
		if (a == size)
		{
			m_accel_allocation[i] = size;
			for (a=1; a<size; ++a)
				m_accel_allocation[i+a] = -1;
			addr = ((unsigned char*)m_accel_addr) + (i << 12);
			phys_addr = m_accel_phys_addr + (i << 12);
			return 0;
		}
	}
	eDebug("accel alloc failed\n");
	return -1;
}

void gAccel::accelFree(int phys_addr)
{
	phys_addr -= m_accel_phys_addr;
	phys_addr >>= 12;
	
	int size = m_accel_allocation[phys_addr];
	
	ASSERT(size > 0);
	
	while (size--)
		m_accel_allocation[phys_addr++] = 0;
}

eAutoInitP0<gAccel> init_gAccel(eAutoInitNumbers::graphic-2, "graphics acceleration manager");
