#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <memory.h>
#include <linux/kd.h>

#include <lib/gdi/fb.h>

#ifndef FBIO_WAITFORVSYNC
#define FBIO_WAITFORVSYNC _IOW('F', 0x20, __u32)
#endif

#ifndef FBIO_BLIT
#define FBIO_SET_MANUAL_BLIT _IOW('F', 0x21, __u8)
#define FBIO_BLIT 0x22
#endif

#ifdef HAVE_DREAMBOX_ION
/*
 * HD Satelit (ION1, forum 529): Dreambox DM7080, DM820, DM900, DM920 and DM520, with the option
 * "Dreambox: memoria ecranului si accelerarea (ION)" on (Components/HdsDreamboxIon.py).
 *
 * What the Dream framebuffer driver does (bcmfb in the Dream modules; CONFIG_ION=y in all five kernels):
 * - it allocates the screen pages when a mode is set, so right after the receiver starts the memory is only as
 *   large as the boot mode and a 1920x1080 interface does not fit in the mapping made at start (the first start
 *   of the interface stops in SetMode; the second start finds the larger memory and stays up);
 * - smem_len is only the screen pages: nothing is left after them for the 2D engine.
 * What this code does, only with the option on (without it everything below is skipped and fbClass works as on
 * every other receiver):
 * 1. before the one mapping, if the memory is smaller than two 1920x1080x32 pages, the driver is asked once for
 *    that mode, so it allocates the large memory first; then the mapping is made once and never moved (no remap
 *    while the drawing thread runs). Every later SetMode checks that the driver kept the same memory (same
 *    physical start, enough length) and otherwise stops the interface cleanly (eFatal), never drawing outside;
 * 2. the memory for the 2D engine is one buffer from /dev/ion (the BMEM heap of the Dream modules), mapped and
 *    handed to gAccel once (gFBDC::setResolution through accelIon), so changing the mode never resets the table of
 *    surfaces that still live in it. Any failure (no /dev/ion, an unknown ABI, no physical address) leaves the
 *    2D engine without memory, as before;
 * 3. a start mark on the flash (HDS_DREAM_SEMN) is written at start and removed by Python after 2 minutes of a
 *    living interface, or by the clean end (~fbClass); found at the next start = the last start with the option
 *    did not live (a stop, a crash, a power cut in the first 2 minutes): the option is
 *    turned off by itself (no restart loop on a receiver nobody watches) and fbClass works as before.
 * The state of the start is in HDS_DREAM_STARE (word, code, detail), read by the setting and the web page.
 * ION ABI: the staging driver of the 3.14 kernels (dm900, dm920) plus the Dream ioctl number 8 for the physical
 * address. The 3.4 kernels (dm7080, dm820, dm520) are not checked here: a different ABI gives an ioctl error, and
 * then the 2D engine simply has no memory.
 */
#ifndef HDS_DREAM_PORNIT
#define HDS_DREAM_PORNIT "/etc/enigma2/hds-dreambox-ion"
#endif
#ifndef HDS_DREAM_SEMN
#define HDS_DREAM_SEMN "/etc/enigma2/hds-dreambox-ion.pornire"
#endif
#ifndef HDS_DREAM_STARE
#define HDS_DREAM_STARE "/tmp/hds-dreambox-ion.stare"
#endif
#ifndef HDS_DREAM_ION
#define HDS_DREAM_ION "/dev/ion"
#endif
/* the largest interface asked for before the mapping: two pages of 1920x1080x32 */
#define HDS_DREAM_X 1920
#define HDS_DREAM_Y 1080
/* the ION interface, written from the kernel ABI (32-bit userland on all five receivers) */
struct hds_ion_alloc { size_t len; size_t align; unsigned int heap_mask; unsigned int flags; int handle; };
struct hds_ion_handle { int handle; };
struct hds_ion_fd { int handle; int fd; };
struct hds_ion_phys { int handle; unsigned long addr; size_t len; };
#define HDS_ION_ALLOC _IOWR('I', 0, struct hds_ion_alloc)
#define HDS_ION_FREE _IOWR('I', 1, struct hds_ion_handle)
#define HDS_ION_SHARE _IOWR('I', 4, struct hds_ion_fd)
#define HDS_ION_PHYS _IOWR('I', 8, struct hds_ion_phys)
/* the heap the Dream modules register for BMEM: the first id after the generic heap types */
#define HDS_ION_HEAP_BMEM (1u << 6)
#endif

fbClass *fbClass::instance;

fbClass *fbClass::getInstance()
{
	return instance;
}

fbClass::fbClass(const char *fb)
{
	m_manual_blit=-1;
	m_dream_on=0;
	m_ion_virt=0;
	m_ion_phys=0;
	m_ion_size=0;
	m_ion_fd=-1;
	m_ion_given=0;
	instance=this;
	locked=0;
	available=0;
	reportedMemory=0;
	cmap.start=0;
	cmap.len=256;
	cmap.red=red;
	cmap.green=green;
	cmap.blue=blue;
	cmap.transp=trans;

	fd=open(fb, O_RDWR);
	if (fd<0)
	{
		perror(fb);
		goto nolfb;
	}


	if (ioctl(fd, FBIOGET_VSCREENINFO, &screeninfo)<0)
	{
		perror("FBIOGET_VSCREENINFO");
		goto nolfb;
	}
	
	memcpy(&oldscreen, &screeninfo, sizeof(screeninfo));

	fb_fix_screeninfo fix;
	if (ioctl(fd, FBIOGET_FSCREENINFO, &fix)<0)
	{
		perror("FBIOGET_FSCREENINFO");
		goto nolfb;
	}
#ifdef HAVE_DREAMBOX_ION
	dreamPregatesteEcranul(fix);
#endif

	available=fix.smem_len;
	reportedMemory=fix.smem_len;
	m_phys_mem = fix.smem_start;
	eDebug("%dk video mem", available/1024);
	lfb=(unsigned char*)mmap(0, available, PROT_WRITE|PROT_READ, MAP_SHARED, fd, 0);
	if (lfb == MAP_FAILED)
	{
		perror("mmap");
		eWarning("[fb] maparea memoriei ecranului a esuat: %u octeti", fix.smem_len);
		goto nolfb;
	}

#ifdef HAVE_DREAMBOX_ION
	if (m_dream_on)
		dreamAlocaIon();
#endif
	showConsole(0);

	enableManualBlit();
	return;
nolfb:
	lfb=0;
	available=0;
	printf("framebuffer not available.\n");
	return;
}

int fbClass::showConsole(int state)
{
	int fd=open("/dev/tty0", O_RDWR);
	if(fd>=0)
	{
		if(ioctl(fd, KDSETMODE, state?KD_TEXT:KD_GRAPHICS)<0)
		{
			eDebug("setting /dev/tty0 status failed.");
		}
		close(fd);
	}
	return 0;
}

int fbClass::SetMode(unsigned int nxRes, unsigned int nyRes, unsigned int nbpp)
{
	screeninfo.xres_virtual=screeninfo.xres=nxRes;
	screeninfo.yres_virtual=(screeninfo.yres=nyRes)*2;
	screeninfo.height=0;
	screeninfo.width=0;
	screeninfo.xoffset=screeninfo.yoffset=0;
	screeninfo.bits_per_pixel=nbpp;

	switch (nbpp) {
	case 16:
		// ARGB 1555
		screeninfo.transp.offset = 15;
		screeninfo.transp.length = 1;
		screeninfo.red.offset = 10;
		screeninfo.red.length = 5;
		screeninfo.green.offset = 5;
		screeninfo.green.length = 5;
		screeninfo.blue.offset = 0;
		screeninfo.blue.length = 5;
		break;
	case 32:
		// ARGB 8888
		screeninfo.transp.offset = 24;
		screeninfo.transp.length = 8;
		screeninfo.red.offset = 16;
		screeninfo.red.length = 8;
		screeninfo.green.offset = 8;
		screeninfo.green.length = 8;
		screeninfo.blue.offset = 0;
		screeninfo.blue.length = 8;
		break;
	}

	if (ioctl(fd, FBIOPUT_VSCREENINFO, &screeninfo)<0)
	{
		// try single buffering
		screeninfo.yres_virtual=screeninfo.yres=nyRes;
		
		if (ioctl(fd, FBIOPUT_VSCREENINFO, &screeninfo)<0)
		{
			perror("FBIOPUT_VSCREENINFO");
			printf("fb failed\n");
			// HD Satelit: driverul a refuzat modul (hi_fb pe HiSilicon nu trece de 1920x1080; tema Fury-FHD pe 2K,
			// forum 948). Modul de pe placa a ramas cel vechi: xRes/yRes/stride/paginile se iau de pe placa, ca
			// setOffset si gFBDC sa nu lucreze cu marimea ceruta si refuzata.
			citesteModulPlacii();
			eWarning("[fb] SetMode refused: wanted %dx%dx%d, the framebuffer stays at %dx%dx%d", nxRes, nyRes, nbpp, xRes, yRes, bpp);
			return -1;
		}
		eDebug(" - double buffering not available.");
	} else
		eDebug(" - double buffering available!");
	
	m_number_of_pages = screeninfo.yres_virtual / nyRes;
	
	if (ioctl(fd, FBIOGET_VSCREENINFO, &screeninfo)<0)
		eFatal("[fb] nu pot citi modul ecranului dupa SetMode");
	
	if ((screeninfo.xres!=nxRes) && (screeninfo.yres!=nyRes) && (screeninfo.bits_per_pixel!=nbpp))
	{
		eDebug("SetMode failed: wanted: %dx%dx%d, got %dx%dx%d",
			nxRes, nyRes, nbpp,
			screeninfo.xres, screeninfo.yres, screeninfo.bits_per_pixel);
	}
	xRes=screeninfo.xres;
	yRes=screeninfo.yres;
	bpp=screeninfo.bits_per_pixel;
	fb_fix_screeninfo fix;
	if (ioctl(fd, FBIOGET_FSCREENINFO, &fix)<0)
	{
		perror("FBIOGET_FSCREENINFO");
		eFatal("[fb] nu pot citi memoria ecranului dupa SetMode");
	}
	stride=fix.line_length;
#ifdef HAVE_DREAMBOX_ION
	dreamVerificaMod(fix);
#endif
	verificaMemoria(fix);
	const unsigned long long bytes = (unsigned long long)stride * yRes;
	memset(lfb, 0, bytes < (unsigned int)available ? (size_t)bytes : (size_t)available);
	return 0;
}

void fbClass::verificaMemoria(const fb_fix_screeninfo &fix)
{
	eWarning("[fb] memorie: inainte=%u dupa=%u mapata=%u stride=%u virtual=%ux%u bpp=%u",
		reportedMemory, fix.smem_len, (unsigned int)available, fix.line_length,
		screeninfo.xres_virtual, screeninfo.yres_virtual, screeninfo.bits_per_pixel);
	reportedMemory = fix.smem_len;
	// Include the back page: gFBDC uses it after SetMode returns. No remapping,
	// so existing surfaces and the crash screen keep their mapped addresses.
	const unsigned int rows = screeninfo.yres_virtual > yRes ? screeninfo.yres_virtual : yRes;
	const unsigned long long bytes = (unsigned long long)fix.line_length * rows;
	if (bytes > (unsigned int)available)
		eFatal("[fb] memoria ecranului ceruta %llu depaseste maparea %u", bytes, (unsigned int)available);
}

void fbClass::citesteModulPlacii()
{
	if (ioctl(fd, FBIOGET_VSCREENINFO, &screeninfo) < 0)
		eFatal("[fb] nu pot citi modul ecranului dupa SetMode refuzat");
	xRes = screeninfo.xres;
	yRes = screeninfo.yres;
	bpp = screeninfo.bits_per_pixel;
	m_number_of_pages = yRes ? screeninfo.yres_virtual / yRes : 1;
	fb_fix_screeninfo fix;
	if (ioctl(fd, FBIOGET_FSCREENINFO, &fix) < 0)
		eFatal("[fb] nu pot citi memoria ecranului dupa SetMode refuzat");
	stride = fix.line_length;
#ifdef HAVE_DREAMBOX_ION
	dreamVerificaMod(fix);
#endif
	verificaMemoria(fix);
}

int fbClass::accelIon(void *&addr, int &phys, int &size)
{
	/* with the option on the memory after the pages is NOT given to the 2D engine even when ION failed: the mapping
	 * is the grown one, so at 720x576 that memory looks free, but 1920x1080 takes it for the pages and gAccel would
	 * reset its table under living surfaces. Without ION the 2D engine simply has no memory (as on the Dream driver
	 * at 1920x1080 before). */
	if (!m_ion_virt)
		return m_dream_on ? 2 : 0;
	if (m_ion_given)
		return 2;
	addr = m_ion_virt;
	phys = (int)(unsigned int)m_ion_phys;
	size = m_ion_size;
	m_ion_given = 1;
	return 1;
}

#ifdef HAVE_DREAMBOX_ION
void fbClass::dreamStare(const char *word, const char *code, const char *detail)
{
	FILE *f = fopen(HDS_DREAM_STARE, "w");
	if (f)
	{
		fprintf(f, "%s\n%s\n%s\n", word, code, detail);
		fclose(f);
	}
}

void fbClass::dreamPregatesteEcranul(fb_fix_screeninfo &fix)
{
	if (access(HDS_DREAM_PORNIT, F_OK) != 0)
	{
		dreamStare("oprit", "setare", "");
		return;
	}
	if (access(HDS_DREAM_SEMN, F_OK) == 0)
	{
		/* the last start with the option on did not live 2 minutes: off by itself, the old way from now */
		unlink(HDS_DREAM_PORNIT);
		unlink(HDS_DREAM_SEMN);
		eWarning("[fb] Dreambox ION: pornirea de data trecuta nu a trait, optiunea s-a oprit singura");
		dreamStare("oprit", "cadere", "");
		return;
	}
	FILE *f = fopen(HDS_DREAM_SEMN, "w");
	if (!f)
	{
		/* without the mark a failing start could repeat: do not use the new way */
		eWarning("[fb] Dreambox ION: nu pot scrie semnul de pornire, raman pe calea veche");
		dreamStare("oprit", "semn", HDS_DREAM_SEMN);
		return;
	}
	fputs("1\n", f);
	fclose(f);
	m_dream_on = 1;
	dreamStare("pornit", "memorie", "");

	const unsigned long long want = (unsigned long long)HDS_DREAM_X * 4 * HDS_DREAM_Y * 2;
	if (fix.smem_len >= want)
		return;
	fb_var_screeninfo mode = screeninfo;
	mode.xres = mode.xres_virtual = HDS_DREAM_X;
	mode.yres = HDS_DREAM_Y;
	mode.yres_virtual = HDS_DREAM_Y * 2;
	mode.xoffset = mode.yoffset = 0;
	mode.height = mode.width = 0;
	mode.bits_per_pixel = 32;
	mode.transp.offset = 24; mode.transp.length = 8;
	mode.red.offset = 16; mode.red.length = 8;
	mode.green.offset = 8; mode.green.length = 8;
	mode.blue.offset = 0; mode.blue.length = 8;
	if (ioctl(fd, FBIOPUT_VSCREENINFO, &mode) < 0)
	{
		mode.yres_virtual = HDS_DREAM_Y;
		if (ioctl(fd, FBIOPUT_VSCREENINFO, &mode) < 0)
		{
			eWarning("[fb] Dreambox ION: driverul a refuzat %dx%d inainte de mapare", HDS_DREAM_X, HDS_DREAM_Y);
			return;
		}
	}
	fb_fix_screeninfo grown;
	if (ioctl(fd, FBIOGET_FSCREENINFO, &grown) < 0)
	{
		eWarning("[fb] Dreambox ION: nu pot citi memoria ecranului dupa marire");
		return;
	}
	eWarning("[fb] Dreambox ION: memoria ecranului inainte de mapare %u -> %u", fix.smem_len, grown.smem_len);
	fix = grown;
}

void fbClass::dreamVerificaMod(const fb_fix_screeninfo &fix)
{
	if (!m_dream_on)
		return;
	/* the mapping made at start must still be the memory of the driver: same start, long enough */
	if ((unsigned int)fix.smem_start != (unsigned int)m_phys_mem)
		eFatal("[fb] Dreambox ION: memoria ecranului s-a mutat de la %x la %x", (unsigned int)m_phys_mem,
			(unsigned int)fix.smem_start);
	const unsigned int rows = screeninfo.yres_virtual > yRes ? screeninfo.yres_virtual : yRes;
	const unsigned long long bytes = (unsigned long long)fix.line_length * rows;
	if (bytes > fix.smem_len)
		eFatal("[fb] Dreambox ION: modul cere %llu octeti, driverul are %u", bytes, fix.smem_len);
}

void fbClass::dreamAlocaIon()
{
	int ion = open(HDS_DREAM_ION, O_RDWR | O_CLOEXEC);
	if (ion < 0)
	{
		eWarning("[fb] Dreambox ION: %s lipseste, accelerarea ramane fara memorie", HDS_DREAM_ION);
		dreamStare("pornit", "lipsa-ion", HDS_DREAM_ION);
		return;
	}
	const char *why = "alocare";
	for (int mib = 32; mib >= 4; mib /= 2)
	{
		const unsigned int size = (unsigned int)mib << 20;
		struct hds_ion_alloc a;
		memset(&a, 0, sizeof(a));
		a.len = size;
		a.align = 4096;
		a.heap_mask = HDS_ION_HEAP_BMEM;
		if (ioctl(ion, HDS_ION_ALLOC, &a) < 0)
			continue; /* maybe a smaller buffer fits */
		struct hds_ion_handle h;
		memset(&h, 0, sizeof(h));
		h.handle = a.handle;
		struct hds_ion_phys ph;
		memset(&ph, 0, sizeof(ph));
		ph.handle = a.handle;
		const int got_phys = ioctl(ion, HDS_ION_PHYS, &ph);
		const unsigned long long start = ph.addr, end = start + size;
		/* gAccel keeps physical addresses in an int: the buffer may not cross 0x80000000 */
		if (got_phys < 0 || !start || (start & 4095) || ph.len < size || end > 0x100000000ULL ||
			(start < 0x80000000ULL && end > 0x80000000ULL))
		{
			why = got_phys < 0 ? "adresa" : "adresa-gresita";
			ioctl(ion, HDS_ION_FREE, &h);
			break;
		}
		struct hds_ion_fd sh;
		memset(&sh, 0, sizeof(sh));
		sh.handle = a.handle;
		const int shared = ioctl(ion, HDS_ION_SHARE, &sh);
		ioctl(ion, HDS_ION_FREE, &h); /* the shared fd keeps the buffer */
		if (shared < 0 || sh.fd < 0)
		{
			why = "impartire";
			break;
		}
		void *v = mmap(0, size, PROT_WRITE|PROT_READ, MAP_SHARED, sh.fd, 0);
		if (v == MAP_FAILED || !v)
		{
			close(sh.fd);
			why = "mapare";
			break;
		}
		m_ion_virt = (unsigned char*)v;
		m_ion_phys = (unsigned long)start;
		m_ion_size = (int)size;
		m_ion_fd = sh.fd;
		close(ion);
		char detail[64];
		snprintf(detail, sizeof(detail), "%u kB la 0x%08llx", size / 1024, start);
		eWarning("[fb] Dreambox ION: memoria accelerarii %s", detail);
		dreamStare("pornit", "ok", detail);
		return;
	}
	close(ion);
	eWarning("[fb] Dreambox ION: nu am memorie pentru accelerare (%s), accelerarea ramane fara memorie", why);
	dreamStare("pornit", why, "");
}
#endif


int fbClass::setOffset(int off)
{
	screeninfo.xoffset = 0;
	screeninfo.yoffset = off;
	return ioctl(fd, FBIOPAN_DISPLAY, &screeninfo);
}

int fbClass::waitVSync()
{
	int c = 0;
	return ioctl(fd, FBIO_WAITFORVSYNC, &c);
}

void fbClass::blit()
{
	if (m_manual_blit == 1) {
		if (ioctl(fd, FBIO_BLIT) < 0)
			perror("FBIO_BLIT");
	}
}

fbClass::~fbClass()
{
	if (available)
		ioctl(fd, FBIOPUT_VSCREENINFO, &oldscreen);
	if (lfb)
		munmap(lfb, available);
	if (m_ion_virt)
		munmap(m_ion_virt, m_ion_size);
	if (m_ion_fd >= 0)
		close(m_ion_fd);
#ifdef HAVE_DREAMBOX_ION
	/* a clean end (a restart of the interface) is not a failed start */
	if (m_dream_on)
		unlink(HDS_DREAM_SEMN);
#endif
	showConsole(1);
	disableManualBlit();
}

int fbClass::PutCMAP()
{
	return ioctl(fd, FBIOPUTCMAP, &cmap);
}

int fbClass::lock()
{
	if (locked)
		return -1;
	if (m_manual_blit == 1)
	{
		locked = 2;
		disableManualBlit();
	}
	else
		locked = 1;
	return fd;
}

void fbClass::unlock()
{
	if (!locked)
		return;
	if (locked == 2)  // re-enable manualBlit
		enableManualBlit();
	locked=0;
	SetMode(xRes, yRes, bpp);
	PutCMAP();
}

void fbClass::enableManualBlit()
{
	unsigned char tmp = 1;
	if (ioctl(fd,FBIO_SET_MANUAL_BLIT, &tmp)<0)
		perror("FBIO_SET_MANUAL_BLIT");
	else
		m_manual_blit = 1;
}

void fbClass::disableManualBlit()
{
	unsigned char tmp = 0;
	if (ioctl(fd,FBIO_SET_MANUAL_BLIT, &tmp)<0) 
		perror("FBIO_SET_MANUAL_BLIT");
	else
		m_manual_blit = 0;
}

