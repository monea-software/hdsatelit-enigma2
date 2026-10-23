/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/driver/rcinput.h>

#include <lib/base/eerror.h>

#include <sys/ioctl.h>
#include <linux/input.h>
#include <sys/stat.h>
#include <sys/inotify.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <algorithm>
#include <list>
#include <set>
#include <vector>

#include <lib/base/ebase.h>
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/driver/input_fake.h>
#include <lib/driver/rcmapper.h>

void eRCDeviceInputDev::handleCode(long rccode)
{
	struct input_event *ev = (struct input_event *)rccode;
	eRCMapper *mapper = eRCMapper::getInstance();
	/*
	 * HDSatelit: a mouse (or the pointer of a keyboard with a touchpad): movement, wheel and the mouse buttons go
	 * to eRCMapper, which hands them to Python (Components/HdsMouseUsb.py) once per EV_SYN. The buttons are no
	 * longer keys: BTN_LEFT used to reach eActionMap as an unbound key.
	 */
	if (ismouse && (ev->type == EV_REL || ev->type == EV_SYN ||
		(ev->type == EV_KEY && ev->code >= BTN_MOUSE && ev->code < BTN_JOYSTICK)))
	{
		if (mapper)
			mapper->noteMouse(ev->type, ev->code, ev->value);
		return;
	}
	/* HDSatelit: codul brut al tastelor USB (codul HID, trimis inaintea tastei) pentru cititor */
	if (ev->type == EV_MSC && ev->code == MSC_SCAN)
	{
		if (mapper)
			mapper->noteScan(this, ev->value);
		return;
	}
	if (ev->type!=EV_KEY)
		return;

//	eDebug("%x %x %x", ev->value, ev->code, ev->type);

	/* o tastatura asociata ca telecomanda (tastele neasociate oprite) nu scrie text: toate codurile ei merg la
	   traducere, ca in lista de canale si in setari (kmAscii) sa mearga butoanele ei asociate */
	bool remote = mapper && mapper->isRemote(id);
	int km = (iskeyboard && !remote) ? input->getKeyboardMode() : eRCInput::kmNone;

//	eDebug("keyboard mode %d", km);

	if (km == eRCInput::kmAll)
		return;

	if (km == eRCInput::kmAscii && !(mapper && mapper->isMapped(id, ev->code)))
	{
//		eDebug("filtering.. %d", ev->code);
		bool filtered = ( ev->code > 0 && ev->code < 61 );
		switch (ev->code)
		{
			case KEY_RESERVED:
			case KEY_ESC:
			case KEY_TAB:
			case KEY_BACKSPACE:
			case KEY_ENTER:
			case KEY_LEFTCTRL:
			case KEY_RIGHTSHIFT:
			case KEY_LEFTALT:
			case KEY_CAPSLOCK:
			case KEY_INSERT:
			case KEY_DELETE:
			case KEY_MUTE:
			/* HDSatelit: F1 and F2 (red, green: cancel, save in the setup screens) print nothing on the console */
			case KEY_F1:
			case KEY_F2:
				filtered=false;
			default:
				break;
		}
		if (filtered)
			return;
//		eDebug("passed!");
	}

	switch (ev->value)
	{
	case 0:
		/*emit*/ input->keyPressed(eRCKey(this, ev->code, eRCKey::flagBreak));
		break;
	case 1:
		/*emit*/ input->keyPressed(eRCKey(this, ev->code, 0));
		break;
	case 2:
		/*emit*/ input->keyPressed(eRCKey(this, ev->code, eRCKey::flagRepeat));
		break;
	}
}

eRCDeviceInputDev::eRCDeviceInputDev(eRCInputEventDriver *driver)
	:eRCDevice(driver->getDeviceName(), driver), iskeyboard(false), ismouse(false)
{
	if (strcasestr(id.c_str(), "keyboard") != NULL)
		iskeyboard = true;
	/*
	 * HDSatelit: a keyboard is also recognised by its keys (A, Z and the space bar), not only by "keyboard" in
	 * its name: many wireless receivers call themselves "USB Receiver" and were grabbed like a remote control,
	 * so their letters never reached the console. A mouse is recognised by REL_X, REL_Y and BTN_LEFT. The
	 * receiver's own devices (names starting with "dreambox ") are never keyboards or mice.
	 */
	if (!eRCMapper::isOwnDevice(id))
	{
		if (!iskeyboard && driver->hasCode(EV_KEY, KEY_A) && driver->hasCode(EV_KEY, KEY_Z) &&
			driver->hasCode(EV_KEY, KEY_SPACE))
			iskeyboard = true;
		ismouse = driver->hasCode(EV_REL, REL_X) && driver->hasCode(EV_REL, REL_Y) && driver->hasCode(EV_KEY, BTN_LEFT);
	}
	setExclusive(true);
	eDebug("Input device \"%s\" is %sa keyboard%s.", id.c_str(), iskeyboard ? "" : "not ",
		ismouse ? " and a mouse" : "");
}

void eRCDeviceInputDev::setExclusive(bool b)
{
	/* o tastatura se ia exclusiv numai daca e asociata ca telecomanda (altfel scrie text prin consola) */
	eRCMapper *mapper = eRCMapper::getInstance();
	if (!iskeyboard)
		driver->setExclusive(b);
	else
		driver->setExclusive(b && mapper && mapper->isRemote(id));
}

const char *eRCDeviceInputDev::getDescription() const
{
	return id.c_str();
}

/*
 * HDSatelit: dispozitivele de intrare se cauta si la cald. La pornire se citeste /dev/input intreg
 * (vechea bucla se oprea la primul numar lipsa), apoi un inotify pe /dev/input deschide fiecare eventN nou
 * (un dongle USB bagat dupa pornire) si il inchide pe cel sters. Dispozitivele se tin dupa cale, nu dupa
 * nume: interfetele aceluiasi dongle au adesea acelasi nume. Un dispozitiv scos se inchide si singur, la
 * POLLHUP (eRCInputEventDriver::closeGone), iar stergerea obiectelor se face dintr-un eTimer, nu din
 * notificarea lui. Fara /dev/input (emulatorul), fara cautare la cald si fara nicio alta urmare.
 */
class eInputDeviceInit: public sigc::trackable
{
	struct Entry
	{
		std::string path;
		eRCInputEventDriver *driver;
		eRCDeviceInputDev *device;
	};
	std::list<Entry> m_entries;
	int m_inotify;
	ePtr<eSocketNotifier> m_notifier;
	ePtr<eTimer> m_sweep, m_retry;
	std::set<std::string> m_retryPaths;

	static bool isEventName(const char *name)
	{
		if (strncmp(name, "event", 5) || !name[5])
			return false;
		for (const char *p = name + 5; *p; ++p)
			if (*p < '0' || *p > '9')
				return false;
		return true;
	}

	bool openDevice(const std::string &path)
	{
		for (std::list<Entry>::iterator i = m_entries.begin(); i != m_entries.end(); ++i)
			if (i->path == path && !i->driver->isGone())
				return true;
		struct stat s;
		if (stat(path.c_str(), &s) || !S_ISCHR(s.st_mode))
			return false;
		eRCInputEventDriver *driver = new eRCInputEventDriver(path.c_str());
		if (!driver->isOpen())
		{
			delete driver;
			return false;
		}
		Entry e;
		e.path = path;
		e.driver = driver;
		e.device = new eRCDeviceInputDev(driver);
		if (eRCInput::getInstance()->islocked())
			e.device->setExclusive(false);
		driver->gone.connect(sigc::mem_fun(*this, &eInputDeviceInit::scheduleSweep));
		m_entries.push_back(e);
		return true;
	}

	void removeEntry(std::list<Entry>::iterator i)
	{
		eDebug("[eInputDeviceInit] input device %s removed (%s)", i->path.c_str(), i->device->getDescription());
		delete i->device;
		delete i->driver;
		m_entries.erase(i);
	}

	void scheduleSweep()
	{
		if (m_sweep)
			m_sweep->start(0, true);
	}

	void sweep()
	{
		for (std::list<Entry>::iterator i = m_entries.begin(); i != m_entries.end(); )
		{
			std::list<Entry>::iterator n = i;
			++n;
			if (i->driver->isGone())
				removeEntry(i);
			i = n;
		}
	}

	void retry()
	{
		std::set<std::string> paths;
		paths.swap(m_retryPaths);
		for (std::set<std::string>::iterator i = paths.begin(); i != paths.end(); ++i)
			if (openDevice(*i))
				eDebug("[eInputDeviceInit] new input device %s", i->c_str());
	}

	void inotifyEvent(int)
	{
		char buf[4096] __attribute__((aligned(__alignof__(struct inotify_event))));
		while (1)
		{
			ssize_t n = read(m_inotify, buf, sizeof(buf));
			if (n <= 0)
				break;
			for (char *p = buf; p < buf + n; )
			{
				struct inotify_event *ev = (struct inotify_event *)p;
				p += sizeof(struct inotify_event) + ev->len;
				if (!ev->len || !isEventName(ev->name))
					continue;
				std::string path = std::string("/dev/input/") + ev->name;
				if (ev->mask & IN_DELETE)
				{
					m_retryPaths.erase(path);
					for (std::list<Entry>::iterator i = m_entries.begin(); i != m_entries.end(); ++i)
						if (i->path == path)
						{
							removeEntry(i);
							break;
						}
				}
				else if (ev->mask & (IN_CREATE | IN_ATTRIB))
				{
					if (openDevice(path))
					{
						m_retryPaths.erase(path);
						if (ev->mask & IN_CREATE)
							eDebug("[eInputDeviceInit] new input device %s", path.c_str());
					}
					else if (ev->mask & IN_CREATE)
					{
						/* nodul abia facut nu se deschide intotdeauna din prima: inca o incercare dupa 300 ms */
						m_retryPaths.insert(path);
						m_retry->start(300, true);
					}
				}
			}
		}
	}

public:
	eInputDeviceInit(): m_inotify(-1)
	{
		std::vector<int> numbers;
		DIR *d = opendir("/dev/input");
		if (d)
		{
			struct dirent *e;
			while ((e = readdir(d)) != NULL)
				if (isEventName(e->d_name))
					numbers.push_back(atoi(e->d_name + 5));
			closedir(d);
		}
		std::sort(numbers.begin(), numbers.end());
		int found = 0;
		for (std::vector<int>::iterator i = numbers.begin(); i != numbers.end(); ++i)
		{
			char filename[64];
			snprintf(filename, sizeof(filename), "/dev/input/event%d", *i);
			if (openDevice(filename))
				++found;
		}
		eDebug("Found %d input devices!", found);

		m_sweep = eTimer::create(eApp);
		CONNECT(m_sweep->timeout, eInputDeviceInit::sweep);
		m_retry = eTimer::create(eApp);
		CONNECT(m_retry->timeout, eInputDeviceInit::retry);
		if (d)
		{
			m_inotify = inotify_init1(IN_NONBLOCK | IN_CLOEXEC);
			if (m_inotify >= 0 && inotify_add_watch(m_inotify, "/dev/input", IN_CREATE | IN_DELETE | IN_ATTRIB) >= 0)
			{
				m_notifier = eSocketNotifier::create(eApp, m_inotify, eSocketNotifier::Read);
				CONNECT(m_notifier->activated, eInputDeviceInit::inotifyEvent);
			}
			else
			{
				eDebug("[eInputDeviceInit] no hotplug for input devices (%m)");
				if (m_inotify >= 0)
					close(m_inotify);
				m_inotify = -1;
			}
		}
	}

	~eInputDeviceInit()
	{
		m_notifier = 0;
		if (m_inotify >= 0)
			close(m_inotify);
		while (!m_entries.empty())
		{
			delete m_entries.back().device;
			delete m_entries.back().driver;
			m_entries.pop_back();
		}
	}
};

eAutoInitP0<eInputDeviceInit> init_rcinputdev(eAutoInitNumbers::rc+1, "input device driver");
