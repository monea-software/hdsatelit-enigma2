/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_gdi_hdsgpu_h
#define __lib_gdi_hdsgpu_h

/*
 * hdsgpu: the DVB subtitle pages (8 bpp with a palette) enlarged on the GPU, with the same sharp, smooth edges as
 * blit_scaled_sharp_8 in gpixmap.cpp, which stays the fallback for anything that does not work.
 * Written for the Mali-450 MP2 of the Amiko Viper 4K V20 (u57, HiSilicon Hi3798MV200) through libMali (EGL + OpenGL
 * ES 2.0, Utgard r8p0); any EGL + GLES 2.0 library works (the probe on the PC uses Mesa).
 *
 * How it runs:
 * - In the enigma2 process. libEGL and libGLESv2 are loaded with dlopen at the first page that needs them (nothing is
 *   linked, nothing is loaded while the mode is not "GPU"); all EGL/GL calls are made on one thread of this module
 *   (the EGL context belongs to it). The drawing thread hands the page over and waits at most a short deadline; after
 *   that, or on any error, it draws on the CPU (gpixmap.cpp) and the GPU result is thrown away.
 * - libMali never touches the framebuffer: MALI_NEVERBLIT=1 (a fake display, no /dev/fb*) and MALI_NOCLEAR=1 are set
 *   just before the first EGL call and put back right after eglInitialize; the /dev/fb* descriptors and mappings of
 *   the process are counted before and after, and the GPU is given up if they grew. Off-screen only: a 16x16 pbuffer
 *   and framebuffer objects, the result read back with glReadPixels.
 * - Safety files: /etc/enigma2/hds-fara-gpu (exists = the GPU is never used), /etc/enigma2/hds-gpu.pornire (around
 *   the start) and /tmp/hds-gpu.lucru (around every job): found at the next start, they mean enigma2 died inside
 *   the GPU library, and hds-fara-gpu is written. State for people: /tmp/hds-gpu.stare.
 */

#include <lib/gdi/erect.h>

struct gSurface;

namespace hdsgpu
{

/*
 * Enlarges the 8 bpp page src (palette: src->clut) so that all of it lands on pos of dst (32 bpp ARGB8888) and
 * writes only area (inside pos and inside dst), exactly like blit_scaled_sharp_8. Returns true when area has been
 * written; false when nothing has been written (GPU off, not ready yet, busy, too large, error, deadline): the
 * caller draws it on the CPU. The first call starts the GPU in the background and returns false.
 */
bool blitScaled8(gSurface *dst, const gSurface *src, const eRect &pos, const eRect &area);

enum
{
	stateIdle = 0,	/* nothing loaded yet */
	stateStarting,	/* the GPU thread is loading the library and preparing the programs */
	stateReady,	/* pages go to the GPU */
	stateOff	/* given up until enigma2 restarts (reason: stateReason) */
};
int state();
const char *stateReason();

/* Paths, libraries, deadlines, and faults for the probes. The defaults are the receiver's. */
struct Options
{
	const char *egl_libs[3];	/* tried in order; NULL ends the list */
	const char *gles_libs[3];
	const char *off_file;		/* /etc/enigma2/hds-fara-gpu */
	const char *start_mark;		/* /etc/enigma2/hds-gpu.pornire */
	const char *job_mark;		/* /tmp/hds-gpu.lucru */
	const char *state_file;		/* /tmp/hds-gpu.stare */
	const char *fb_prefixes[3];	/* device paths that count as the framebuffer; NULL ends the list */
	int deadline_ms;		/* the drawing thread waits at most deadline_ms + deadline_ms_per_mpixel * */
	int deadline_ms_per_mpixel;	/*   (million destination pixels), and never more than deadline_max_ms */
	int deadline_max_ms;
	int max_timeouts;		/* this many deadlines missed in a row: the GPU is given up */
	int test_delay_ms;		/* probes only: the GPU thread sleeps this long before each job */
	int test_bad_shader;		/* probes only: 1 = a fragment shader that does not compile */
	int test_no_mali_env;		/* probes only: 1 = MALI_* not set (to see the framebuffer check work) */
};
Options defaultOptions();
/* before the first blitScaled8, or after shutdown() */
void setOptions(const Options &options);
/* probes: wait until the GPU is ready (true) or off (false), at most timeout_ms */
bool waitReady(int timeout_ms);
/* probes: stop the GPU thread, release EGL, forget the state (enigma2 never calls it: the process just exits) */
void shutdown();

}

#endif
