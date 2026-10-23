/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_gdi_sdl_h
#define __lib_gdi_sdl_h

/*
 * Rescris pentru SDL2.
 * Ecranul pe PC: enigma2 deseneaza intr-o suprafata software ARGB8888, iar firul SDL
 * o copiaza intr-o textura si o afiseaza in fereastra.
 */

#include <lib/base/thread.h>
#include <lib/gdi/gmaindc.h>

#include <SDL.h>
#include <mutex>

class gSDLDC: public gMainDC, public eThread, public sigc::trackable
{
private:
	SDL_Window *m_window;
	SDL_Renderer *m_renderer;
	SDL_Texture *m_texture;
	SDL_Surface *m_screen;
	SDL_Surface *m_old_screen; /* freed only at the next resolution change: gRC may still draw in it */
	int m_texture_w, m_texture_h;
	std::mutex m_lock;
	void exec(const gOpcode *opcode);

	gSurface m_surface;

	eFixedMessagePump<SDL_Event> m_pump;
	void keyEvent(const SDL_Event &event);
	void pumpEvent(const SDL_Event &event);
	virtual void thread();

	enum event {
		EV_SET_VIDEO_MODE,
		EV_FLIP,
		EV_QUIT,
	};

	void pushEvent(enum event code, intptr_t data1 = 0, intptr_t data2 = 0);
	void evSetVideoMode(int xres, int yres);
	void evFlip();
	void destroyVideo();

public:
	void setResolution(int xres, int yres);
	gSDLDC();
	virtual ~gSDLDC();
	int islocked() { return 0; }
};

#endif
