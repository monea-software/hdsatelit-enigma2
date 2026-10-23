/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
/*
 * Rescris pentru SDL2.
 */
#include <lib/driver/rcsdl.h>
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/driver/input_fake.h>

/*
 * Taste comode pentru o tastatura de PC (emulator): doar in modul kmNone,
 * ca literele sa ramana text in tastatura virtuala si in campurile de text.
 */
static int translateComfortKey(SDL_Keycode key)
{
	switch (key) {
	case SDLK_m:
	case SDLK_F12:
		return KEY_MENU;
	case SDLK_i:
		return KEY_INFO;
	case SDLK_e:
		return KEY_EPG;
	case SDLK_BACKSPACE:
		return KEY_EXIT;
	case SDLK_SPACE:
		return KEY_OK;
	case SDLK_PLUS:
	case SDLK_EQUALS:
	case SDLK_KP_PLUS:
		return KEY_VOLUMEUP;
	case SDLK_MINUS:
	case SDLK_KP_MINUS:
		return KEY_VOLUMEDOWN;
	case SDLK_t:
		return KEY_TEXT;
	case SDLK_a:
		return KEY_AUDIO;
	case SDLK_p:
		return KEY_PVR;
	case SDLK_s:
		return KEY_SUBTITLE;
	case SDLK_h:
		return KEY_HELP;
	case SDLK_r:
		return KEY_RED;
	case SDLK_g:
		return KEY_GREEN;
	case SDLK_y:
		return KEY_YELLOW;
	case SDLK_b:
		return KEY_BLUE;
	default:
		return KEY_RESERVED;
	}
}

/*
 * eSDLInputDevice
 */

eSDLInputDevice::eSDLInputDevice(eRCDriver *driver) : eRCDevice("SDL", driver), m_escape(false)
{
}

eSDLInputDevice::~eSDLInputDevice()
{
}

void eSDLInputDevice::handleCode(long arg)
{
	const SDL_KeyboardEvent *event = (const SDL_KeyboardEvent *)arg;
	const SDL_Keysym *key = &event->keysym;
	int km = input->getKeyboardMode();
	int flags = (event->type == SDL_KEYDOWN) ? eRCKey::flagMake : eRCKey::flagBreak;

	if (event->repeat)
		flags = eRCKey::flagRepeat;

	if (km != eRCInput::kmNone) {
		/* in modul text, caracterele tiparibile vin prin SDL_TEXTINPUT (handleText) */
		bool printable = key->sym >= SDLK_SPACE && key->sym < SDLK_DELETE;
		if (printable && !(key->mod & (KMOD_CTRL | KMOD_ALT | KMOD_GUI)))
			return;
	}

	int code = KEY_RESERVED;
	if (km == eRCInput::kmNone)
		code = translateComfortKey(key->sym);
	if (code == KEY_RESERVED)
		code = translateKey(key->sym);
	input->keyPressed(eRCKey(this, code, flags));
}

void eSDLInputDevice::handleText(const char *utf8)
{
	int km = input->getKeyboardMode();
	if (km == eRCInput::kmNone)
		return;

	/* decodare UTF-8 in puncte de cod */
	const unsigned char *s = (const unsigned char *)utf8;
	while (*s) {
		unsigned int cp;
		int extra;
		if (*s < 0x80) { cp = *s; extra = 0; }
		else if ((*s & 0xe0) == 0xc0) { cp = *s & 0x1f; extra = 1; }
		else if ((*s & 0xf0) == 0xe0) { cp = *s & 0x0f; extra = 2; }
		else if ((*s & 0xf8) == 0xf0) { cp = *s & 0x07; extra = 3; }
		else { ++s; continue; }
		++s;
		while (extra-- > 0 && (*s & 0xc0) == 0x80)
			cp = (cp << 6) | (*s++ & 0x3f);

		if (km == eRCInput::kmAscii) {
			if (m_escape) {
				if (cp != '[')
					m_escape = false;
				continue;
			}
			if (cp == 0x1b) {
				m_escape = true;
				continue;
			}
			if (cp > 255)
				continue;
		}
		input->keyPressed(eRCKey(this, cp, eRCKey::flagMake | eRCKey::flagAscii));
	}
}

const char *eSDLInputDevice::getDescription() const
{
	return "SDL";
}

int eSDLInputDevice::translateKey(SDL_Keycode key)
{
	switch (key) {
	case SDLK_BACKSPACE: return KEY_BACKSPACE;
	case SDLK_TAB: return KEY_TAB;
	case SDLK_CLEAR: return KEY_CLEAR;
	case SDLK_RETURN: return KEY_ENTER;
	case SDLK_PAUSE: return KEY_PAUSE;
	case SDLK_ESCAPE: return KEY_ESC;
	case SDLK_SPACE: return KEY_SPACE;
	case SDLK_DOLLAR: return KEY_DOLLAR;
	case SDLK_QUOTE: return KEY_APOSTROPHE;
	case SDLK_COMMA: return KEY_COMMA;
	case SDLK_MINUS: return KEY_MINUS;
	case SDLK_PERIOD: return KEY_DOT;
	case SDLK_SLASH: return KEY_SLASH;
	case SDLK_0: return KEY_0;
	case SDLK_1: return KEY_1;
	case SDLK_2: return KEY_2;
	case SDLK_3: return KEY_3;
	case SDLK_4: return KEY_4;
	case SDLK_5: return KEY_5;
	case SDLK_6: return KEY_6;
	case SDLK_7: return KEY_7;
	case SDLK_8: return KEY_8;
	case SDLK_9: return KEY_9;
	case SDLK_SEMICOLON: return KEY_SEMICOLON;
	case SDLK_EQUALS: return KEY_EQUAL;
	case SDLK_QUESTION: return KEY_QUESTION;
	case SDLK_LEFTBRACKET: return KEY_LEFTBRACE;
	case SDLK_BACKSLASH: return KEY_BACKSLASH;
	case SDLK_RIGHTBRACKET: return KEY_RIGHTBRACE;
	case SDLK_BACKQUOTE: return KEY_GRAVE;
	case SDLK_a: return KEY_A;
	case SDLK_b: return KEY_B;
	case SDLK_c: return KEY_C;
	case SDLK_d: return KEY_D;
	case SDLK_e: return KEY_E;
	case SDLK_f: return KEY_F;
	case SDLK_g: return KEY_G;
	case SDLK_h: return KEY_H;
	case SDLK_i: return KEY_I;
	case SDLK_j: return KEY_J;
	case SDLK_k: return KEY_K;
	case SDLK_l: return KEY_L;
	case SDLK_m: return KEY_M;
	case SDLK_n: return KEY_N;
	case SDLK_o: return KEY_O;
	case SDLK_p: return KEY_P;
	case SDLK_q: return KEY_Q;
	case SDLK_r: return KEY_R;
	case SDLK_s: return KEY_S;
	case SDLK_t: return KEY_T;
	case SDLK_u: return KEY_U;
	case SDLK_v: return KEY_V;
	case SDLK_w: return KEY_W;
	case SDLK_x: return KEY_X;
	case SDLK_y: return KEY_Y;
	case SDLK_z: return KEY_Z;
	case SDLK_DELETE: return KEY_DELETE;
	case SDLK_KP_0: return KEY_KP0;
	case SDLK_KP_1: return KEY_KP1;
	case SDLK_KP_2: return KEY_KP2;
	case SDLK_KP_3: return KEY_KP3;
	case SDLK_KP_4: return KEY_KP4;
	case SDLK_KP_5: return KEY_KP5;
	case SDLK_KP_6: return KEY_KP6;
	case SDLK_KP_7: return KEY_KP7;
	case SDLK_KP_8: return KEY_KP8;
	case SDLK_KP_9: return KEY_KP9;
	case SDLK_KP_PERIOD: return KEY_KPDOT;
	case SDLK_KP_DIVIDE: return KEY_KPSLASH;
	case SDLK_KP_MULTIPLY: return KEY_KPASTERISK;
	case SDLK_KP_MINUS: return KEY_KPMINUS;
	case SDLK_KP_PLUS: return KEY_KPPLUS;
	case SDLK_KP_ENTER: return KEY_KPENTER;
	case SDLK_KP_EQUALS: return KEY_KPEQUAL;
	case SDLK_UP: return KEY_UP;
	case SDLK_DOWN: return KEY_DOWN;
	case SDLK_RIGHT: return KEY_RIGHT;
	case SDLK_LEFT: return KEY_LEFT;
	case SDLK_INSERT: return KEY_INSERT;
	case SDLK_HOME: return KEY_HOME;
	case SDLK_END: return KEY_END;
	case SDLK_PAGEUP: return KEY_PAGEUP;
	case SDLK_PAGEDOWN: return KEY_PAGEDOWN;
	case SDLK_F1: return KEY_F1;
	case SDLK_F2: return KEY_F2;
	case SDLK_F3: return KEY_F3;
	case SDLK_F4: return KEY_F4;
	case SDLK_F5: return KEY_F5;
	case SDLK_F6: return KEY_F6;
	case SDLK_F7: return KEY_F7;
	case SDLK_F8: return KEY_F8;
	case SDLK_F9: return KEY_F9;
	case SDLK_F10: return KEY_F10;
	case SDLK_F11: return KEY_F11;
	case SDLK_F12: return KEY_F12;
	case SDLK_F13: return KEY_F13;
	case SDLK_F14: return KEY_F14;
	case SDLK_F15: return KEY_F15;
	case SDLK_NUMLOCKCLEAR: return KEY_NUMLOCK;
	case SDLK_CAPSLOCK: return KEY_CAPSLOCK;
	case SDLK_SCROLLLOCK: return KEY_SCROLLLOCK;
	case SDLK_RSHIFT: return KEY_RIGHTSHIFT;
	case SDLK_LSHIFT: return KEY_LEFTSHIFT;
	case SDLK_RCTRL: return KEY_RIGHTCTRL;
	case SDLK_LCTRL: return KEY_LEFTCTRL;
	case SDLK_RALT: return KEY_RIGHTALT;
	case SDLK_LALT: return KEY_LEFTALT;
	case SDLK_RGUI: return KEY_RIGHTMETA;
	case SDLK_LGUI: return KEY_LEFTMETA;
	case SDLK_MODE: return KEY_MODE;
	case SDLK_APPLICATION: return KEY_MENU;
	case SDLK_HELP: return KEY_HELP;
	case SDLK_PRINTSCREEN: return KEY_PRINT;
	case SDLK_SYSREQ: return KEY_SYSRQ;
	case SDLK_MENU: return KEY_MENU;
	case SDLK_POWER: return KEY_POWER;
	case SDLK_UNDO: return KEY_UNDO;
	default:
		eDebug("unhandled SDL keycode: %d", (int)key);
		return KEY_RESERVED;
	}
}

/*
 * eSDLInputDriver
 */

eSDLInputDriver *eSDLInputDriver::instance;

eSDLInputDriver::eSDLInputDriver() : eRCDriver(eRCInput::getInstance())
{
	ASSERT(instance == 0);
	instance = this;
}

eSDLInputDriver::~eSDLInputDriver()
{
	instance = 0;
}

void eSDLInputDriver::keyPressed(const SDL_KeyboardEvent *key)
{
	if (!enabled || input->islocked())
		return;

	std::list<eRCDevice*>::iterator i(listeners.begin());
	while (i != listeners.end()) {
		(*i)->handleCode((long)key);
		++i;
	}
}

void eSDLInputDriver::textInput(const char *utf8)
{
	if (!enabled || input->islocked())
		return;

	std::list<eRCDevice*>::iterator i(listeners.begin());
	while (i != listeners.end()) {
		eSDLInputDevice *dev = (eSDLInputDevice *)*i;
		dev->handleText(utf8);
		++i;
	}
}

class eRCSDLInit
{
private:
	eSDLInputDriver driver;
	eSDLInputDevice device;

public:
	eRCSDLInit(): driver(), device(&driver)
	{
	}
};

eAutoInitP0<eRCSDLInit> init_rcSDL(eAutoInitNumbers::rc+1, "SDL RC Driver");
