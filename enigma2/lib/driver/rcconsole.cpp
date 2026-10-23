/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/base/eerror.h>
#include <lib/driver/rcconsole.h>
#include <stdio.h>
#include <fcntl.h>

eRCConsoleDriver::eRCConsoleDriver(const char *filename): eRCDriver(eRCInput::getInstance()), m_escape(false),
	m_utf8(0), m_utf8left(0)
{
	handle=open(filename, O_RDONLY|O_NONBLOCK);
	if (handle<0)
	{
		eDebug("failed to open %s", filename);
		sn=0;
	} else
	{
		sn=eSocketNotifier::create(eApp, handle, eSocketNotifier::Read);
		CONNECT(sn->activated, eRCConsoleDriver::keyPressed);
	}
	
		/* set console mode */
	struct termios t;
	tcgetattr(handle, &t);
	ot = t;
	t.c_lflag &= ~(ECHO | ICANON | ECHOK | ECHOE | ECHONL);
	tcsetattr(handle, TCSANOW,&t);
}

eRCConsoleDriver::~eRCConsoleDriver()
{
	tcsetattr(handle,TCSANOW, &ot);
 	if (handle>=0)
		close(handle);
}

void eRCConsoleDriver::keyPressed(int)
{
	unsigned char data[16];
	unsigned char *d = data;
	int num = read(handle, data, 16);
	unsigned char code;
	long cp;
	
	int km = input->getKeyboardMode();

	if (km == eRCInput::kmNone)
	{
		m_utf8left = 0;
		return;
	}

	while (num--)
	{
		code = *d++;
		/*
		 * HDSatelit: the keyboard of the console is in Unicode mode (K_UNICODE, the kernel default), so a letter
		 * that is not ASCII (the Romanian letters on AltGr of eng.kmap: a with breve, a and i with circumflex,
		 * s and t with comma below) comes as an UTF-8 sequence. It is put together here and goes on as one code
		 * point, like the characters of the SDL keyboard in the emulator (rcsdl.cpp); Python reads it with
		 * chr(getPrevAsciiCode()). A sequence may be split between two reads; a broken one is dropped.
		 */
		cp = code;
		if (code >= 0xc0)
		{
			m_utf8left = code < 0xe0 ? 1 : code < 0xf0 ? 2 : code < 0xf8 ? 3 : 0;
			m_utf8 = code & (0x3f >> m_utf8left);
			continue;
		}
		if (code >= 0x80)
		{
			if (!m_utf8left)
				continue;
			m_utf8 = (m_utf8 << 6) | (code & 0x3f);
			if (--m_utf8left)
				continue;
			cp = m_utf8;
			/* C1 control characters, overlong forms of ASCII, surrogates */
			if (cp < 0xa0 || (cp >= 0xd800 && cp < 0xe000) || cp > 0x10ffff)
				continue;
		}
		else
			m_utf8left = 0;
//		eDebug("console code %02x\n", code);
		if (km == eRCInput::kmAscii) {
			/*
			 * HDSatelit: the escape sequence of a key is skipped up to its final byte: ESC [ 1 5 ~ (F5),
			 * ESC [ 3 ~ (Delete), ESC [ D (Left), ESC [ [ A (F1). The old code stopped at the first byte after
			 * '[', so the digits of F5-F12 were typed into the text fields. A byte after a lone ESC (not '[')
			 * is a normal character again.
			 */
			if (m_escape == 1) {
				m_escape = 0;
				if (cp == '[') {
					m_escape = 2;
					continue;
				}
			} else if (m_escape == 2) {
				if (cp == '[')
					m_escape = 3;
				else if (cp >= 0x40 && cp <= 0x7e)
					m_escape = 0;
				continue;
			} else if (m_escape == 3) {
				m_escape = 0;
				continue;
			}

			if (cp == 27) // escape code
				m_escape = 1;

			/*
			 * HDSatelit: "~" is a character again: the sequences of Insert, Delete, Page Up/Down and F5-F12 end
			 * with it, but they are skipped whole above.
			 */
			if ((cp < 32) ||	// control characters
			    (cp == 0x7f))	// backspace
				continue;
		}

		for (std::list<eRCDevice*>::iterator i(listeners.begin()); i!=listeners.end(); ++i)
		{
//			eDebug("ascii %02lx", cp);
			(*i)->handleCode(cp);
		}
	}
}

void eRCConsole::handleCode(long code)
{
	input->keyPressed(eRCKey(this, code, eRCKey::flagAscii));
}

eRCConsole::eRCConsole(eRCDriver *driver)
			: eRCDevice("Console", driver)
{
}

const char *eRCConsole::getDescription() const
{
	return "Console";
}

const char *eRCConsole::getKeyDescription(const eRCKey &key) const
{
	return 0;
}

int eRCConsole::getKeyCompatibleCode(const eRCKey &key) const
{
	return key.code;
}

class eRCConsoleInit
{
	eRCConsoleDriver driver;
	eRCConsole device;
public:
	eRCConsoleInit(): driver("/dev/tty0"), device(&driver)
	{
	}
};

eAutoInitP0<eRCConsoleInit> init_rcconsole(eAutoInitNumbers::rc+1, "Console RC Driver");
