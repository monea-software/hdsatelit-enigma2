/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <csignal>
#include <cstdio>
#include <dlfcn.h>
#include <fstream>
#include <pthread.h>
#include <sstream>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <lib/base/eenv.h>
#include <lib/base/eerror.h>
#include <lib/base/nconfig.h>
#include <lib/gdi/font.h>
#include <lib/gdi/gmaindc.h>

#if defined(__MIPSEL__)
#include <asm/ptrace.h>
#elif defined(__x86_64__) || defined(__aarch64__) || defined(__arm__)
#include <ucontext.h>
#else
/* no register dump for this architecture: the crash screen still shows the log */
#define NO_OOPS_SUPPORT
#endif

#include "xmlgenerator.h"
#include "version_info.h"

/************************************************/

#define CRASH_EMAILADDR "https://hdsatelit.com"
#define INFOFILE "/maintainer.info"
/* HDSatelit: dosarul jurnalelor de cadere, pe memoria interna (vezi bsodFatal) */
#define CRASH_LOG_DIR "/home/root/logs"

/*
 * HDSatelit, 0.3.0: the cause of the crash for tools/enigma2.sh, which decides from it whether the crash goes on the
 * account of the 2D acceleration (only with proof, never for any crash). bsodFatal writes it (in RAM, next to the crash
 * log; .nou, then rename) and the script reads and removes it after enigma2 ends:
 *   fel=semnal, semnal=, pc=, lr=, tde=   a fatal signal: the library (or the program) where PC and LR were, with the
 *                                         offset (dladdr: libhiaccel.so is loaded by dlopen at an address that the
 *                                         crash log alone cannot place), and whether a TDE call was running then
 *   fel=python                            an uncaught Python exception (the traceback is in the crash log)
 *   fel=eroare, componenta=               another fatal error (eFatal)
 *   jurnal=                               the crash log
 */
#define HDS_CADERE_MOTIV "/tmp/hds-cadere.motiv"
/* 1 while lib/gdi/accel.cpp runs a TDE call at drawing time */
extern volatile sig_atomic_t hds_tde_in_lucru;
static int s_semnal;
static int s_tde;
static char s_pc[192] = "", s_lr[192] = "";

static void hdsDescrieAdresa(unsigned long adresa, char *text, size_t marime)
{
	Dl_info info;
	if (adresa && dladdr((void *)adresa, &info) && info.dli_fname)
		snprintf(text, marime, "%s+0x%lx", info.dli_fname, adresa - (unsigned long)info.dli_fbase);
	else
		snprintf(text, marime, "0x%lx", adresa);
}

static void hdsScrieMotiv(const char *component, const std::string &logfile)
{
	std::string nou = std::string(HDS_CADERE_MOTIV) + ".nou";
	FILE *m = fopen(nou.c_str(), "w");
	if (!m)
		return;
	if (s_semnal)
		fprintf(m, "fel=semnal\nsemnal=%d\npc=%s\nlr=%s\ntde=%d\n", s_semnal, s_pc, s_lr, s_tde);
	else if (!component)
		fprintf(m, "fel=python\n");
	else
		fprintf(m, "fel=eroare\ncomponenta=%s\n", component);
	fprintf(m, "jurnal=%s\n", logfile.c_str());
	fclose(m);
	rename(nou.c_str(), HDS_CADERE_MOTIV);
}

#define RINGBUFFER_SIZE 16384
static char ringbuffer[RINGBUFFER_SIZE];
static unsigned int ringbuffer_head;

static void addToLogbuffer(const char *data, unsigned int len)
{
	while (len)
	{
		unsigned int remaining = RINGBUFFER_SIZE - ringbuffer_head;

		if (remaining > len)
			remaining = len;

		memcpy(ringbuffer + ringbuffer_head, data, remaining);
		len -= remaining;
		data += remaining;
		ringbuffer_head += remaining;
		ASSERT(ringbuffer_head <= RINGBUFFER_SIZE);
		if (ringbuffer_head == RINGBUFFER_SIZE)
			ringbuffer_head = 0;
	}
}

static const std::string getLogBuffer()
{
	unsigned int begin = ringbuffer_head;
	while (ringbuffer[begin] == 0)
	{
		++begin;
		if (begin == RINGBUFFER_SIZE)
			begin = 0;
		if (begin == ringbuffer_head)
			return "";
	}

	if (begin < ringbuffer_head)
		return std::string(ringbuffer + begin, ringbuffer_head - begin);
	else
		return std::string(ringbuffer + begin, RINGBUFFER_SIZE - begin) + std::string(ringbuffer, ringbuffer_head);
}

static void addToLogbuffer(int level, const std::string &log)
{
	addToLogbuffer(log.c_str(), log.size());
}

static const std::string getConfigString(const std::string &key, const std::string &defaultValue)
{
	/* only the settings file: this runs inside a signal handler, where calling into Python
	   (without its lock, possibly from another thread) crashes a second time */
	std::string value = defaultValue;

	// get value from enigma2 settings file
	std::ifstream in(eEnv::resolve("${sysconfdir}/enigma2/settings").c_str());
	if (in.good()) {
		do {
			std::string line;
			std::getline(in, line);
			size_t size = key.size();
			if (!key.compare(0, size, line) && line[size] == '=') {
				value = line.substr(size + 1);
				break;
			}
		} while (in.good());
		in.close();
	}

	return value;
}

static bool getConfigBool(const std::string &key, bool defaultValue)
{
	std::string value = getConfigString(key, defaultValue ? "true" : "false");
	const char *cvalue = value.c_str();

	if (!strcasecmp(cvalue, "true"))
		return true;
	if (!strcasecmp(cvalue, "false"))
		return false;

	return defaultValue;
}

/*
 * The crash screen uses the faces HdsBold, HdsRegular and Regular, which the skin registers (skin.xml). A crash
 * before the skin is read (an exception while mytest.py imports its modules) finds none of them, and one under
 * another skin may miss the first two: renderText then draws nothing. A missing face is registered here from the
 * font files of the image. AddFont ends in eFatal, and so in bsodFatal again, on a file that is not a font: only
 * a readable file is passed, and the re-entry guard in bsodFatal stops a second pass.
 */
static void bsodEnsureFace(const char *face, const char *file)
{
	fontRenderClass *render = fontRenderClass::getInstance();
	if (!render)
		return;
	ePtr<Font> probe;
	if (render->getFont(probe, face, 20) == 0)
		return;
	static const char *const dirs[] = { "${datadir}/enigma2/HDSatelit/fonts/", "${datadir}/fonts/" };
	for (unsigned int i = 0; i < sizeof(dirs) / sizeof(dirs[0]); ++i)
	{
		std::string path = eEnv::resolve(std::string(dirs[i]) + file);
		struct stat st;
		if (access(path.c_str(), R_OK) == 0 && stat(path.c_str(), &st) == 0 && S_ISREG(st.st_mode) && st.st_size > 0)
		{
			render->AddFont(path, face, 100);
			return;
		}
	}
	eDebug("[bsod] no font file for %s", face);
}

/* bsodFatal runs once: a fatal error while it runs (a font file that fails to load, a fault while drawing) would
   start it again from the top; in the same thread the process ends at once, another thread waits for the first one
   to end the process */
static volatile sig_atomic_t bsod_active = 0;
static pthread_t bsod_thread;

void bsodFatal(const char *component)
{
	if (bsod_active)
	{
		if (pthread_equal(bsod_thread, pthread_self()))
			raise(SIGKILL);
		for (;;)
			pause();
	}
	bsod_thread = pthread_self();
	bsod_active = 1;

	std::ostringstream os;
	os << time(0);

	// HDSatelit: pe Viper 4K V20 /media e un tmpfs de 64 KB, deci /media/hdd nu e disc: jurnalul se
	// pierdea la repornire sau nu incapea. Acum sta in CRASH_LOG_DIR, pe memoria interna (aceeasi cale in mytest.py,
	// Screens/HdsCrashlogAutoSubmit.py si hds-watchdog.py, care pastreaza numai ultimele jurnale). Daca dosarul nu se
	// poate scrie, jurnalul merge in /tmp, ca sa existe macar pana la repornire.
	std::string logfile(std::string(CRASH_LOG_DIR "/enigma2_crash_") + os.str() + ".log");

	mkdir(CRASH_LOG_DIR, 0755); /* lipseste pe o imagine noua; daca exista deja, eroarea nu conteaza */
	FILE *f = fopen(logfile.c_str(), "wb");
	if (!f)
	{
		logfile = "/tmp/enigma2_crash_" + os.str() + ".log";
		f = fopen(logfile.c_str(), "wb");
	}

	hdsScrieMotiv(component, logfile);

	std::string lines = getLogBuffer();
	
		/* find python-tracebacks, and extract "  File "-strings */
	size_t start = 0;
	
	std::string crash_emailaddr = CRASH_EMAILADDR;
	std::string crash_component = "enigma2";

	if (component)
		crash_component = component;
	else
	{
		while ((start = lines.find("\n  File \"", start)) != std::string::npos)
		{
			start += 9;
			size_t end = lines.find("\"", start);
			if (end == std::string::npos)
				break;
			end = lines.rfind("/", end);
				/* skip a potential prefix to the path */
			size_t path_prefix = lines.find("/usr/", start);
			if (path_prefix != std::string::npos && path_prefix < end)
				start = path_prefix;

			if (end == std::string::npos)
				break;

			std::string filename(lines.substr(start, end - start) + INFOFILE);
			std::ifstream in(filename.c_str());
			if (in.good()) {
				std::getline(in, crash_emailaddr) && std::getline(in, crash_component);
				in.close();
			}
		}
	}

	if (f)
	{
		time_t t = time(0);
		struct tm tm;
		char tm_str[32];

		localtime_r(&t, &tm);
		strftime(tm_str, sizeof(tm_str), "%a %b %_d %T %Y", &tm);

		XmlGenerator xml(f);

		xml.open("hdsatelitimage");

		xml.open("enigma2");
		xml.string("crashdate", tm_str);
		xml.string("compiledate", __DATE__);
		xml.string("contactemail", crash_emailaddr);
		xml.comment("Please email this crashlog to above address");

		xml.string("skin", getConfigString("config.skin.primary_skin", "Default Skin"));
		xml.string("sourcedate", enigma2_date);
		xml.string("branch", enigma2_branch);
		xml.string("rev", enigma2_rev);
		xml.string("version", PACKAGE_VERSION);
		xml.close();

		/* the log first: it is the most useful part and must be on disk if a later step fails */
		xml.open("crashlogs");
		xml.cDataFromString("enigma2crashlog", lines);
		xml.close();
		fflush(f);

		xml.open("image");
		xml.stringFromFile("receivermodel", "/proc/stb/info/model");
		xml.stringFromFile("kernelcmdline", "/proc/cmdline");
		xml.stringFromFile("nimsockets", "/proc/bus/nim_sockets");
		if (!getConfigBool("config.plugins.crashlogautosubmit.sendAnonCrashlog", true)) {
			xml.cDataFromFile("receiverca", "/proc/stb/info/ca");
			xml.cDataFromFile("enigma2settings", eEnv::resolve("${sysconfdir}/enigma2/settings"), ".password=");
		}
		if (getConfigBool("config.plugins.crashlogautosubmit.addNetwork", false)) {
			xml.cDataFromFile("networkinterfaces", "/etc/network/interfaces");
			xml.cDataFromFile("dns", "/etc/resolv.conf");
			xml.cDataFromFile("defaultgateway", "/etc/default_gw");
		}
		/* /etc/wpa_supplicant.conf is never added: it holds WiFi passwords */
		xml.cDataFromFile("imageversion", "/etc/image-version");
		xml.cDataFromFile("imageissue", "/etc/issue.net");
		xml.close();
		fflush(f);

		xml.open("software");
		xml.cDataFromCmd("enigma2software", "opkg list_installed | grep enigma2");
		xml.cDataFromCmd("receiversoftware", "opkg list_installed");
		xml.cDataFromCmd("gstreamersoftware", "opkg list_installed | grep gst");
		xml.close();
		fflush(f);

		xml.open("checksums");
		xml.cDataFromCmd("pythonMD5sum", "find " + eEnv::resolve("${libdir}/enigma2/python/") + " -name \"*.py\" | xargs md5sum");
		xml.close();

		xml.close();

		fclose(f);
	}

	ePtr<gMainDC> my_dc;
	gMainDC::getInstance(my_dc);

	/* every size follows the frame: before the skin is read it is still the start frame (720x576 on the
	   receiver, scaled to the whole television), later the frame of the skin */
	const int w = my_dc->size().width();
	const int h = my_dc->size().height();
	const int margin = w / 20;
	const int top = h / 14;
	const int sizeTitle = h / 24;
	const int sizeText = h / 30;
	const int sizeTrace = h / 40 > 12 ? h / 40 : 12;

	bsodEnsureFace("HdsBold", "HdsBold.ttf");
	bsodEnsureFace("HdsRegular", "HdsRegular.ttf");
	bsodEnsureFace("Regular", "HdsRegular.ttf");

	gPainter p(my_dc);
	p.resetOffset();
	p.resetClip(eRect(ePoint(0, 0), my_dc->size()));
	p.setBackgroundColor(gRGB(0x0A0E17));
	p.setForegroundColor(gRGB(0xF8FAFC));
	p.clear();

	/* the gold bar of the skin */
	const int bar = h / 150 > 3 ? h / 150 : 3;
	p.setForegroundColor(gRGB(0xF59E0B));
	p.fill(eRect(margin, top, w - 2 * margin, bar));

	/* one plain sentence as the title, then what happens next; the technical part comes last and smaller */
	int y = top + bar + h / 40;
	const int titleHeight = sizeTitle * 3 / 2;
	ePtr<gFont> fontTitle = new gFont("HdsBold", sizeTitle);
	p.setFont(fontTitle);
	p.setForegroundColor(gRGB(0xF59E0B));
	p.renderText(eRect(margin, y, w - 2 * margin, titleHeight), "Receptorul repornește interfața", gPainter::RT_HALIGN_LEFT);
	y += titleHeight + h / 80;

	const int textHeight = sizeText * 4 * 13 / 10 + 4;
	ePtr<gFont> fontText = new gFont("HdsRegular", sizeText);
	p.setFont(fontText);
	p.setForegroundColor(gRGB(0xF8FAFC));
	std::string text("A apărut o eroare în programul receptorului. Interfața pornește din nou singură în câteva secunde.\n"
		"Detaliile sunt salvate în " + logfile);
	p.renderText(eRect(margin, y, w - 2 * margin, textHeight), text, gPainter::RT_WRAP | gPainter::RT_HALIGN_LEFT);
	y += textHeight + h / 60;

	/* the end of the log, where the error is: as many lines as fit, the last line (the error itself) at the bottom */
	const int pad = sizeTrace / 2 + 2;
	eRect traceArea = eRect(margin, y, w - 2 * margin, h - top - y);
	p.setForegroundColor(gRGB(0x151F32));
	p.fill(traceArea);

	ePtr<gFont> fontTrace = new gFont("Regular", sizeTrace);
	int lineHeight = 0;
	if (fontRenderClass::getInstance())
		lineHeight = (int)fontRenderClass::getInstance()->getLineHeight(*fontTrace);
	if (lineHeight <= 0)
		lineHeight = sizeTrace * 5 / 4;
	int maxLines = (traceArea.height() - 2 * pad) / lineHeight;
	if (maxLines < 1)
		maxLines = 1;

	size_t tail = lines.size();
	while (tail > 0 && lines[tail - 1] == '\n')
		--tail;
	start = tail;
	for (int i = 0; i < maxLines && start > 0; ++i)
	{
		size_t nl = lines.rfind('\n', start - 1);
		if (nl == std::string::npos)
		{
			start = 0;
			break;
		}
		start = nl;
	}
	if (start < tail && lines[start] == '\n')
		++start;

	p.setFont(fontTrace);
	p.setForegroundColor(gRGB(0x38BDF8));
	p.renderText(eRect(margin + pad, y + pad, w - 2 * margin - 2 * pad, traceArea.height() - 2 * pad),
		lines.substr(start, tail - start), gPainter::RT_HALIGN_LEFT);
	p.flush();
	/* the render thread shows its spinner at 100,100 of the frame after 2 s of a busy main thread, over the text:
	   the painting above has already hidden a spinner shown before, then the spinner stays off (the process ends below) */
	usleep(200 * 1000);
	if (gRC::getInstance())
		gRC::getInstance()->setSpinnerDC(0);
	sleep(10);

	raise(SIGKILL);
}

#if defined(__MIPSEL__)
void oops(const mcontext_t &context, int dumpcode)
{
	eDebug("PC: %08lx", (unsigned long)context.pc);
	int i;
	for (i=0; i<32; ++i)
	{
		eDebugNoNewLine(" %08x", (int)context.gregs[i]);
		if ((i&3) == 3)
			eDebug("%s", "");
	}
		/* this is temporary debug stuff. */
	if (dumpcode && ((unsigned long)context.pc) > 0x10000) /* not a zero pointer */
	{
		eDebug("As a final action, i will try to dump a bit of code.");
		eDebug("I just hope that this won't crash.");
		int i;
		eDebugNoNewLine("%08lx:", (unsigned long)context.pc);
		for (i=0; i<0x20; ++i)
			eDebugNoNewLine(" %02x", ((unsigned char*)context.pc)[i]);
		eDebug(" (end)");
	}
}
#elif defined(__x86_64__)
void oops(const mcontext_t &context, int dumpcode)
{
	/* order of the REG_* indexes in <sys/ucontext.h>: R8 .. RIP */
	static const char * const names[] = { "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15",
		"RDI", "RSI", "RBP", "RBX", "RDX", "RAX", "RCX", "RSP", "RIP" };
	(void)dumpcode;
	eDebug("PC: %016llx", (unsigned long long)context.gregs[REG_RIP]);
	for (int i = 0; i <= REG_RIP; ++i)
		eDebug(" %-3s %016llx", names[i], (unsigned long long)context.gregs[i]);
}
#elif defined(__aarch64__)
void oops(const mcontext_t &context, int dumpcode)
{
	(void)dumpcode;
	eDebug("PC: %016llx SP: %016llx fault address: %016llx", (unsigned long long)context.pc,
		(unsigned long long)context.sp, (unsigned long long)context.fault_address);
	for (int i = 0; i < 31; ++i)
		eDebug(" X%-2d %016llx", i, (unsigned long long)context.regs[i]);
}
#elif defined(__arm__)
void oops(const mcontext_t &context, int dumpcode)
{
	(void)dumpcode;
	eDebug("PC: %08lx LR: %08lx SP: %08lx fault address: %08lx", (unsigned long)context.arm_pc,
		(unsigned long)context.arm_lr, (unsigned long)context.arm_sp, (unsigned long)context.fault_address);
	eDebug(" R0 %08lx  R1 %08lx  R2 %08lx  R3 %08lx", (unsigned long)context.arm_r0, (unsigned long)context.arm_r1,
		(unsigned long)context.arm_r2, (unsigned long)context.arm_r3);
	eDebug(" R4 %08lx  R5 %08lx  R6 %08lx  R7 %08lx", (unsigned long)context.arm_r4, (unsigned long)context.arm_r5,
		(unsigned long)context.arm_r6, (unsigned long)context.arm_r7);
	eDebug(" R8 %08lx  R9 %08lx R10 %08lx  FP %08lx", (unsigned long)context.arm_r8, (unsigned long)context.arm_r9,
		(unsigned long)context.arm_r10, (unsigned long)context.arm_fp);
	eDebug(" IP %08lx CPSR %08lx", (unsigned long)context.arm_ip, (unsigned long)context.arm_cpsr);
}
#endif

void handleFatalSignal(int signum, siginfo_t *si, void *ctx)
{
	s_semnal = signum;
	s_tde = hds_tde_in_lucru;
#ifndef NO_OOPS_SUPPORT
	ucontext_t *uc = (ucontext_t*)ctx;

	oops(uc->uc_mcontext, signum == SIGSEGV || signum == SIGABRT);

	/* HDSatelit: where PC and LR were (the library and the offset), and whether the TDE was drawing (see above) */
	unsigned long pc = 0, lr = 0;
#if defined(__arm__)
	pc = uc->uc_mcontext.arm_pc;
	lr = uc->uc_mcontext.arm_lr;
#elif defined(__aarch64__)
	pc = uc->uc_mcontext.pc;
	lr = uc->uc_mcontext.regs[30];
#elif defined(__x86_64__)
	pc = uc->uc_mcontext.gregs[REG_RIP];
#elif defined(__MIPSEL__)
	pc = uc->uc_mcontext.pc;
	lr = uc->uc_mcontext.gregs[31];
#endif
	hdsDescrieAdresa(pc, s_pc, sizeof(s_pc));
	hdsDescrieAdresa(lr, s_lr, sizeof(s_lr));
#endif
	eDebug("[bsod] semnalul %d, PC in %s, LR in %s, placa 2D in lucru: %s", signum, s_pc[0] ? s_pc : "?",
		s_lr[0] ? s_lr : "?", s_tde ? "da" : "nu");
	eDebug("-------");
	bsodFatal("enigma2, signal");
}

void bsodCatchSignals()
{
	struct sigaction act;
	act.sa_sigaction = handleFatalSignal;
	act.sa_flags = SA_RESTART | SA_SIGINFO;
	if (sigemptyset(&act.sa_mask) == -1)
		perror("sigemptyset");
	
		/* start handling segfaults etc. */
	sigaction(SIGSEGV, &act, 0);
	sigaction(SIGILL, &act, 0);
	sigaction(SIGBUS, &act, 0);
	sigaction(SIGABRT, &act, 0);
}

void bsodLogInit()
{
	logOutput.connect(sigc::ptr_fun(static_cast<void (*)(int, const std::string &)>(&addToLogbuffer)));
}
