#ifndef __FB_H
#define __FB_H

#include <lib/base/eerror.h>
#include <linux/fb.h>

class fbClass
{
	int fd;
	unsigned int xRes, yRes, stride, bpp;
	int available; // Bytes mapped at startup; never changed by SetMode.
	unsigned int reportedMemory;
	void verificaMemoria(const fb_fix_screeninfo &fix);
	struct fb_var_screeninfo screeninfo, oldscreen;
	fb_cmap cmap;
	__u16 red[256], green[256], blue[256], trans[256];
	static fbClass *instance;
	int locked;

	int m_manual_blit;
	int m_number_of_pages;
	int m_phys_mem;
	/* HD Satelit (ION1): Dreambox memory for the 2D engine from /dev/ion, separate from the screen pages.
	 * Declared on every build, so all files see one layout; used only with HAVE_DREAMBOX_ION and the option on. */
	int m_dream_on;            /* 1 = the option was on at start and nothing stopped it */
	unsigned char *m_ion_virt; /* mapping of the ION buffer, 0 = none */
	unsigned long m_ion_phys;
	int m_ion_size;
	int m_ion_fd;              /* shared buffer fd, kept open while mapped */
	int m_ion_given;           /* 1 = already handed to gAccel (its table must not be reset) */
	void dreamPregatesteEcranul(fb_fix_screeninfo &fix);
	void dreamAlocaIon();
	void dreamStare(const char *word, const char *code, const char *detail);
	void dreamVerificaMod(const fb_fix_screeninfo &fix);
#ifdef SWIG
	fbClass(const char *fb="/dev/fb0");
	~fbClass();
public:
#else
public:
	unsigned char *lfb;
	void enableManualBlit();
	void disableManualBlit();
	int showConsole(int state);
	int SetMode(unsigned int xRes, unsigned int yRes, unsigned int bpp);
	void citesteModulPlacii(); // HD Satelit: xRes/yRes/bpp/stride/paginile de pe placa (dupa un SetMode refuzat)
	unsigned int getXRes() { return xRes; }
	unsigned int getYRes() { return yRes; }
	int Available() { return available; }
	
	int getNumPages() { return m_number_of_pages; }
	
	unsigned long getPhysAddr() { return m_phys_mem; }
	/* HD Satelit (ION1): 0 = the option is off: the memory after the screen pages is used, as before;
	 * 1 = ION memory, hand it to gAccel now; 2 = do nothing (ION memory already handed over, or the option is on
	 * and ION failed: then the 2D engine gets no memory at all) */
	int accelIon(void *&addr, int &phys, int &size);
	
	int setOffset(int off);
	int waitVSync();
	void blit();
	unsigned int Stride() { return stride; }
	fb_cmap *CMAP() { return &cmap; }

	fbClass(const char *fb="/dev/fb0");
	~fbClass();
	
			// low level gfx stuff
	int PutCMAP();
#endif
	static fbClass *getInstance();

	int lock();
	void unlock();
	int islocked() { return locked; }
};

#endif
