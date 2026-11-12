/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/base/eerror.h>
#include <lib/driver/rcconsole.h>
#include <lib/driver/hdsconsolacitire.h>
#include <lib/base/hdsjurnal.h>
#include <stdio.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>

eRCConsoleDriver::eRCConsoleDriver(const char *filename): eRCDriver(eRCInput::getInstance()), m_ot_ok(false),
	m_escape(false), m_utf8(0), m_utf8left(0), m_goale(0)
{
	/*
	 * HDSatelit: O_NOCTTY: the console is read only for the letters of a USB keyboard and must never become the
	 * controlling terminal of enigma2 (the job control of a controlling terminal can refuse the reads).
	 */
	handle=open(filename, O_RDONLY|O_NONBLOCK|O_NOCTTY);
	sn=0;
	if (handle<0)
	{
		eDebug("failed to open %s", filename);
		return;
	}

		/* set console mode */
	struct termios t;
	if (tcgetattr(handle, &t) != 0)
	{
		/*
		 * HDSatelit: not a terminal, so nothing to watch. The kernel of the Vu+ Duo 4K has no virtual terminals
		 * (CONFIG_VT is not set), so /dev/tty0 there is no console (for instance a regular file left by a write):
		 * poll() says readable for ever and read() gives 0, and the main loop held a core at 85-99% (0.7.1-0.7.3).
		 * Without virtual terminals no keyboard letters come through a console anyway.
		 */
		int err = errno;
		struct stat st;
		const char *fel = "?";
		if (fstat(handle, &st) == 0)
			fel = S_ISREG(st.st_mode) ? "regular file" : S_ISCHR(st.st_mode) ? "character device" : "other";
		eWarning("[eRCConsoleDriver] %s is not a terminal (%s, errno %d %s): not watched", filename, fel, err,
			strerror(err));
		hdsjurnal::scrief("consola", hdsjurnal::INFO, "tty0", "%s nu e terminal (%s, errno %d %s): consola nu se "
			"urmareste", filename, fel, err, strerror(err));
		close(handle);
		handle = -1;
		return;
	}
	ot = t;
	m_ot_ok = true;
	t.c_lflag &= ~(ECHO | ICANON | ECHOK | ECHOE | ECHONL);
	tcsetattr(handle, TCSANOW,&t);

	sn=eSocketNotifier::create(eApp, handle, eSocketNotifier::Read);
	CONNECT(sn->activated, eRCConsoleDriver::keyPressed);
}

eRCConsoleDriver::~eRCConsoleDriver()
{
 	if (handle>=0)
	{
		if (m_ot_ok)
			tcsetattr(handle,TCSANOW, &ot);
		close(handle);
	}
}

/*
 * HDSatelit: the console is left after hdsconsola::LIMITA_GOALE reads without data in a row (Vu+ Duo 4K: poll() said
 * readable about 100000 times a second and read() took nothing, so the main loop held a core at 85-99%). The notifier is
 * released, not only stopped: unlock() would start a stopped one again. One line says why, with what the next look
 * needs: the device number, the result of read(), errno and the process groups.
 */
void eRCConsoleDriver::lasaConsola(int rezultat, int err)
{
	struct stat st;
	unsigned int maj = 0, min = 0;
	if (fstat(handle, &st) == 0)
	{
		maj = major(st.st_rdev);
		min = minor(st.st_rdev);
	}
	int pgrp = (int)getpgrp(), tty_pgrp = (int)tcgetpgrp(handle), sid = (int)getsid(0), tty_sid = (int)tcgetsid(handle);
	eWarning("[eRCConsoleDriver] /dev/tty0 (%u:%u) left after %d reads without data in a row (read %d, errno %d %s, "
		"pgrp %d, tty pgrp %d, sid %d, tty sid %d): the letters of a USB keyboard no longer come through the console",
		maj, min, (int)hdsconsola::LIMITA_GOALE, rezultat, err, err ? strerror(err) : "-", pgrp, tty_pgrp, sid, tty_sid);
	hdsjurnal::scrief("consola", hdsjurnal::AVERT, "tty0", "/dev/tty0 (%u:%u) lasata dupa %d citiri fara date la rand "
		"(read %d, errno %d %s, pgrp %d, pgrp tty %d, sid %d, sid tty %d)", maj, min, (int)hdsconsola::LIMITA_GOALE,
		rezultat, err, err ? strerror(err) : "-", pgrp, tty_pgrp, sid, tty_sid);
	if (sn)
	{
		sn->stop();
		sn = 0;
	}
	if (m_ot_ok)
		tcsetattr(handle, TCSANOW, &ot);
	close(handle);
	handle = -1;
}

void eRCConsoleDriver::keyPressed(int)
{
	unsigned char data[16];
	unsigned char *d = data;
	int num = read(handle, data, 16);
	unsigned char code;
	long cp;

	/*
	 * HDSatelit: a read without data (0, or -1 whatever errno) is counted before anything else, also before the kmNone
	 * return below: live TV is kmNone and that is exactly when the main loop spun on /dev/tty0 (Vu+ Duo 4K). Without
	 * this check num = -1 also went into "while (num--)" and read far past data[] in the text modes.
	 */
	if (num <= 0)
	{
		int err = num < 0 ? errno : 0;
		if (hdsconsola::lasaDupaCitire(num, m_goale))
			lasaConsola(num, err);
		return;
	}
	hdsconsola::lasaDupaCitire(num, m_goale);

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
