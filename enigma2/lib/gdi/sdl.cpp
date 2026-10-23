/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
/*
 * Rescris pentru SDL2.
 */
#include <lib/gdi/sdl.h>
#include <lib/actions/action.h>
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/driver/rc.h>
#include <lib/driver/input_fake.h>
#include <lib/driver/rcsdl.h>

#include <SDL.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstring>
#include <sys/mman.h>

/*
 * Mouse in emulator: clic dreapta = EXIT (Inapoi, tasta folosita cel mai des), clic pe
 * rotita (mijloc) = MENU, rotita = sus/jos. Aceleasi gesturi are
 * mouse-ul din interfata web a receptorului (Components/HdsMouseEcran.py).
 * Clicul stanga se scrie in /tmp/e2mouse ("click x y clicuri"), unde il citeste pluginul
 * de emulator care stie ce lista sau buton e sub mouse. Fara cititor, scrierea nu face nimic.
 */
static void sdlSendRcKey(int code)
{
	eRCInput *input = eRCInput::getInstance();
	eRCDevice *device = input ? input->getDevice("SDL") : nullptr;
	if (!device || input->islocked())
		return;
	input->keyPressed(eRCKey(device, code, eRCKey::flagMake));
	input->keyPressed(eRCKey(device, code, eRCKey::flagBreak));
}

static void sdlWriteFifo(const char *linie)
{
	int fd = open("/tmp/e2mouse", O_WRONLY | O_NONBLOCK);
	if (fd >= 0) {
		if (write(fd, linie, strlen(linie)) < 0)
			eDebug("[gSDLDC] mouse write failed");
		close(fd);
	}
}

/* tras cu butonul stang pe bara de derulare (scrollbar) a listelor -- inainte
 * doar SDL_MOUSEBUTTONDOWN ajungea aici, SDL_MOUSEMOTION/SDL_MOUSEBUTTONUP nu erau nici
 * macar trimise mai departe de thread()/pumpEvent(). Cat butonul stang e tinut apasat,
 * fiecare miscare trimite "drag x y" pe acelasi FIFO /tmp/e2mouse; la ridicare, "dragend".
 * Pluginul EmulatorMouse (Python) decide daca miscarea cade pe o lista/scrollbar si muta
 * selectia proportional -- partea C++ doar transmite pozitiile, nu stie nimic despre ecrane. */
static bool s_mouseLeftDown = false;

static void sdlMouseEvent(const SDL_Event &event)
{
	if (event.type == SDL_MOUSEWHEEL) {
		int y = event.wheel.y;
		if (event.wheel.direction == SDL_MOUSEWHEEL_FLIPPED)
			y = -y;
		if (y > 0)
			sdlSendRcKey(KEY_UP);
		else if (y < 0)
			sdlSendRcKey(KEY_DOWN);
		return;
	}
	if (event.type == SDL_MOUSEMOTION) {
		if (s_mouseLeftDown) {
			char linie[64];
			int n = snprintf(linie, sizeof(linie), "drag %d %d\n", event.motion.x, event.motion.y);
			if (n > 0)
				sdlWriteFifo(linie);
		}
		return;
	}
	if (event.type == SDL_MOUSEBUTTONUP) {
		if (event.button.button == SDL_BUTTON_LEFT && s_mouseLeftDown) {
			s_mouseLeftDown = false;
			char linie[64];
			int n = snprintf(linie, sizeof(linie), "dragend %d %d\n", event.button.x, event.button.y);
			if (n > 0)
				sdlWriteFifo(linie);
		}
		return;
	}
	switch (event.button.button) {
	case SDL_BUTTON_RIGHT:
		sdlSendRcKey(KEY_EXIT);
		break;
	case SDL_BUTTON_MIDDLE:
		sdlSendRcKey(KEY_MENU);
		break;
	case SDL_BUTTON_LEFT: {
		s_mouseLeftDown = true;
		char linie[64];
		int n = snprintf(linie, sizeof(linie), "click %d %d %d\n", event.button.x, event.button.y, event.button.clicks);
		if (n > 0)
			sdlWriteFifo(linie);
		break;
	}
	}
}

/*
 * Meniurile cu alfa pentru fereastra emulatorului (imaginea canalelor sub meniuri): cand exista HDS_OSD_SHM (de ex.
 * /dev/shm/hds-osd), la fiecare desen suprafata meniurilor (ARGB, cu alfa adevarat) se copiaza intr-o memorie partajata.
 * punte.py o citeste si o trimite ferestrei, care pune imaginea canalului dedesubt.
 */
static void sdlOsdShm(SDL_Surface *osd)
{
	static int checked = 0;
	static const char *path = nullptr;
	static unsigned char *mem = nullptr;
	static size_t size = 0;
	if (!checked) {
		checked = 1;
		path = getenv("HDS_OSD_SHM");
		if (path && !*path)
			path = nullptr;
	}
	if (!path || !osd || !osd->pixels)
		return;
	size_t need = 24 + (size_t)osd->pitch * osd->h;
	if (!mem) {
		int fd = open(path, O_RDWR | O_CREAT | O_CLOEXEC, 0644);
		if (fd < 0 || ftruncate(fd, need) < 0) {
			if (fd >= 0)
				close(fd);
			eWarning("[gSDLDC] OSD shm %s: %m", path);
			path = nullptr;
			return;
		}
		void *m = mmap(nullptr, need, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
		close(fd);
		if (m == MAP_FAILED) {
			eWarning("[gSDLDC] OSD shm mmap: %m");
			path = nullptr;
			return;
		}
		mem = (unsigned char *)m;
		size = need;
		uint32_t hdr[5] = { (uint32_t)osd->w, (uint32_t)osd->h, (uint32_t)osd->pitch, 0, 0 };
		memcpy(mem + 4, hdr, sizeof(hdr));
		memcpy(mem, "HOSD", 4);
		eDebug("[gSDLDC] OSD with alpha in %s (%dx%d)", path, osd->w, osd->h);
	}
	if (need > size)
		return;
	uint32_t seq;
	memcpy(&seq, mem + 16, 4);
	seq |= 1;
	memcpy(mem + 16, &seq, 4);
	memcpy(mem + 24, osd->pixels, (size_t)osd->pitch * osd->h);
	seq++;
	memcpy(mem + 16, &seq, 4);
}

gSDLDC::gSDLDC() : m_window(0), m_renderer(0), m_texture(0), m_screen(0), m_old_screen(0), m_texture_w(0), m_texture_h(0), m_pump(eApp, 1)
{
	if (SDL_Init(SDL_INIT_VIDEO) < 0) {
		eWarning("Could not initialize SDL: %s", SDL_GetError());
		return;
	}

	CONNECT(m_pump.recv_msg, gSDLDC::pumpEvent);

	m_surface.type = 0;
	m_surface.clut.colors = 256;
	m_surface.clut.data = new gRGB[m_surface.clut.colors]; /* gRGB() zeroes every entry */

	/* the drawing surface exists before anything can draw: created here, not in the SDL thread */
	setResolution(720, 576);

	m_pixmap = new gPixmap(&m_surface);

	run();
}

gSDLDC::~gSDLDC()
{
	pushEvent(EV_QUIT);
	kill();
	destroyVideo();
	SDL_Quit();
}

void gSDLDC::keyEvent(const SDL_Event &event)
{
	eSDLInputDriver *driver = eSDLInputDriver::getInstance();

	if (!driver)
		return;

	if (event.type == SDL_TEXTINPUT)
		driver->textInput(event.text.text);
	else
		driver->keyPressed(&event.key);
}

void gSDLDC::pumpEvent(const SDL_Event &event)
{
	switch (event.type) {
	case SDL_KEYDOWN:
	case SDL_KEYUP:
	case SDL_TEXTINPUT:
		keyEvent(event);
		break;
	case SDL_MOUSEBUTTONDOWN:
	case SDL_MOUSEBUTTONUP:
	case SDL_MOUSEMOTION:
	case SDL_MOUSEWHEEL:
		sdlMouseEvent(event);
		break;
	case SDL_QUIT:
		eDebug("SDL Quit");
		extern void quitMainloop(int exit_code);
		quitMainloop(0);
		break;
	}
}

void gSDLDC::pushEvent(enum event code, intptr_t data1, intptr_t data2)
{
	SDL_Event event;

	SDL_zero(event);
	event.type = SDL_USEREVENT;
	event.user.code = code;
	event.user.data1 = (void *)data1;
	event.user.data2 = (void *)data2;

	SDL_PushEvent(&event);
}

void gSDLDC::exec(const gOpcode *o)
{
	switch (o->opcode) {
	case gOpcode::flush:
		pushEvent(EV_FLIP);
		break;
	default:
		gDC::exec(o);
		break;
	}
}

void gSDLDC::setResolution(int xres, int yres)
{
	{
		std::lock_guard<std::mutex> lock(m_lock);
		if (m_screen && m_screen->w == xres && m_screen->h == yres)
			return;

		SDL_Surface *screen = SDL_CreateRGBSurfaceWithFormat(0, xres, yres, 32, SDL_PIXELFORMAT_ARGB8888);
		if (!screen) {
			eWarning("Could not create %dx%d SDL surface: %s", xres, yres, SDL_GetError());
			return;
		}
		if (m_old_screen)
			SDL_FreeSurface(m_old_screen);
		m_old_screen = m_screen;
		m_screen = screen;

		m_surface.x = m_screen->w;
		m_surface.y = m_screen->h;
		m_surface.bpp = m_screen->format->BitsPerPixel;
		m_surface.bypp = m_screen->format->BytesPerPixel;
		m_surface.stride = m_screen->pitch;
		m_surface.data = m_screen->pixels;
	}
	/* window and texture belong to the SDL thread */
	pushEvent(EV_SET_VIDEO_MODE, xres, yres);
}

/*
 * SDL thread below...
 */

void gSDLDC::destroyVideo()
{
	if (m_texture)
		SDL_DestroyTexture(m_texture);
	if (m_renderer)
		SDL_DestroyRenderer(m_renderer);
	if (m_window)
		SDL_DestroyWindow(m_window);
	if (m_screen)
		SDL_FreeSurface(m_screen);
	if (m_old_screen)
		SDL_FreeSurface(m_old_screen);
	m_texture = 0;
	m_renderer = 0;
	m_window = 0;
	m_screen = 0;
	m_old_screen = 0;
}

void gSDLDC::evSetVideoMode(int xres, int yres)
{
	std::lock_guard<std::mutex> lock(m_lock);

	if (m_window && m_texture && m_texture_w == xres && m_texture_h == yres)
		return;

	if (m_window) {
		SDL_SetWindowSize(m_window, xres, yres);
		/* a resize keeps the old corner: center again, or a 1920x1080 skin starts at 600,252 */
		SDL_SetWindowPosition(m_window, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED);
	} else {
		m_window = SDL_CreateWindow("HD Satelit", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
			xres, yres, SDL_WINDOW_RESIZABLE);
		if (!m_window) {
			eFatal("Could not create SDL window: %s", SDL_GetError());
			return;
		}
		m_renderer = SDL_CreateRenderer(m_window, -1, 0);
		if (!m_renderer) {
			eFatal("Could not create SDL renderer: %s", SDL_GetError());
			return;
		}
		SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "linear");
		SDL_StartTextInput();
	}

	if (m_texture)
		SDL_DestroyTexture(m_texture);
	m_texture_w = m_texture_h = 0;
	SDL_RenderSetLogicalSize(m_renderer, xres, yres);
	m_texture = SDL_CreateTexture(m_renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, xres, yres);
	if (!m_texture) {
		eFatal("Could not create SDL texture: %s", SDL_GetError());
		return;
	}
	/* zonele transparente ale meniului (alfa 0) se vad pe negru, ca un ecran fara imagine video */
	SDL_SetTextureBlendMode(m_texture, SDL_BLENDMODE_BLEND);
	m_texture_w = xres;
	m_texture_h = yres;
}

void gSDLDC::evFlip()
{
	std::lock_guard<std::mutex> lock(m_lock);

	/* between a resolution change and its EV_SET_VIDEO_MODE the sizes differ: skip that frame */
	if (!m_texture || !m_screen || m_screen->w != m_texture_w || m_screen->h != m_texture_h)
		return;
	SDL_UpdateTexture(m_texture, NULL, m_screen->pixels, m_screen->pitch);
	SDL_SetRenderDrawColor(m_renderer, 0, 0, 0, 255);
	SDL_RenderClear(m_renderer);
	SDL_RenderCopy(m_renderer, m_texture, NULL, NULL);
	SDL_RenderPresent(m_renderer);
}

void gSDLDC::thread()
{
	hasStarted();

	bool stop = false;
	while (!stop) {
		SDL_Event event;
		if (SDL_WaitEvent(&event)) {
			switch (event.type) {
			case SDL_KEYDOWN:
			case SDL_KEYUP:
			case SDL_TEXTINPUT:
			case SDL_QUIT:
			case SDL_MOUSEBUTTONDOWN:
			case SDL_MOUSEBUTTONUP:
			case SDL_MOUSEMOTION:
			case SDL_MOUSEWHEEL:
				m_pump.send(event);
				break;
			case SDL_WINDOWEVENT:
				if (event.window.event == SDL_WINDOWEVENT_EXPOSED || event.window.event == SDL_WINDOWEVENT_SIZE_CHANGED)
					evFlip();
				break;
			case SDL_USEREVENT:
				switch (event.user.code) {
				case EV_SET_VIDEO_MODE:
					evSetVideoMode((int)(intptr_t)event.user.data1, (int)(intptr_t)event.user.data2);
					break;
				case EV_FLIP:
					sdlOsdShm(m_screen);
					evFlip();
					break;
				case EV_QUIT:
					stop = true;
					break;
				}
				break;
			}
		}
	}
}

eAutoInitPtr<gSDLDC> init_gSDLDC(eAutoInitNumbers::graphic-1, "gSDLDC");
