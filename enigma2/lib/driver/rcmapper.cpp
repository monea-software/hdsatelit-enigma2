/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * HDSatelit: telecomenzile asociate, cititorul de coduri si proba tastelor. Descrierea e in
 * rcmapper.h.
 */
#include <lib/driver/rcmapper.h>

#include <string.h>
#include <time.h>
#include <linux/input.h>

#include <lib/actions/action.h>
#include <lib/base/eerror.h>
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/driver/rc.h>

static const char NATIVE_NAME[] = "dreambox advanced remote control (native)";
static const unsigned int MAX_EVENTS = 256;
static const long long EXIT_DOUBLE_MS = 2000;
static const long long HOLD_EXIT_MS = 3000;
/* ascultarea (pagina web) vede si tastele telecomenzii receptorului, deci si un PIN: cel mult 2 minute, ca
   cititorul de pe televizor, oricat ar cere cine o porneste (revizia Telecomenzi, P25) */
static const int MAX_LISTEN_SECONDS = 120;
/* cate pachete de mouse asteapta cel mult in coada (Python o goleste la fiecare cateva milisecunde) */
static const unsigned int MAX_MOUSE = 64;

/* codurile Linux ale celor 53 de butoane ale telecomenzii receptorului (Amiko Viper 4K V20); acelasi tabel cu
   BUTOANE_VIPER din lib/python/Components/HdsTelecomenziDate.py (teste/test_telecomenzi.py le compara) */
static const int viper_codes[] = {
	116, 113, 373, 227, 438, 2, 3, 4, 5, 6, 7, 8, 9, 10, 412, 11, 407, 365, 358, 103, 105, 352, 106, 108,
	139, 174, 392, 388, 370, 115, 114, 402, 403, 398, 399, 400, 401, 393, 150, 395, 359, 165, 168, 208, 163,
	119, 128, 207, 167, 377, 138, 364, 385,
};

eRCMapper *eRCMapper::instance;

eRCMapper::eRCMapper()
	:m_defaultViper(true), m_mode(captureOff), m_idleSeconds(0), m_totalSeconds(0), m_heartbeatSeconds(0),
	m_start(0), m_lastKey(0), m_lastTouch(0), m_lastExitCode(-1), m_lastExitTime(0), m_holdStart(0),
	m_holdDone(false), m_seq(0), m_scanProducer(0), m_scan(-1),
	m_mouseDx(0), m_mouseDy(0), m_mouseWheel(0), m_mouseButtons(0), m_mousePending(false), m_lastKeyboard(false)
{
	if (!instance)
		instance = this;
}

eRCMapper::~eRCMapper()
{
	if (m_timer)
		m_timer->stop();
	if (instance == this)
		instance = 0;
}

eRCMapper *eRCMapper::getInstance()
{
	return instance;
}

long long eRCMapper::now()
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

bool eRCMapper::isOwnDevice(const std::string &device)
{
	return device.compare(0, 9, "dreambox ") == 0;
}

bool eRCMapper::isViperCode(int code)
{
	for (unsigned int i = 0; i < sizeof(viper_codes) / sizeof(viper_codes[0]); ++i)
		if (viper_codes[i] == code)
			return true;
	return false;
}

bool eRCMapper::isRemote(const std::string &device) const
{
	return m_blockUnmapped.find(device) != m_blockUnmapped.end();
}

bool eRCMapper::isMapped(const std::string &device, int code) const
{
	return m_table.find(Key(device, code)) != m_table.end();
}

void eRCMapper::clear()
{
	m_table.clear();
	m_blockUnmapped.clear();
}

void eRCMapper::add(const std::string &device, int code, int targetCode)
{
	if (isOwnDevice(device) || !isViperCode(targetCode) || code <= 0 || code > KEY_MAX)
		return;
	m_table[Key(device, code)] = targetCode;
}

void eRCMapper::setBlockUnmapped(const std::string &device, bool block)
{
	if (isOwnDevice(device))
		return;
	if (block)
		m_blockUnmapped.insert(device);
	else
		m_blockUnmapped.erase(device);
}

void eRCMapper::setDefaultViper(bool on)
{
	m_defaultViper = on;
}

void eRCMapper::apply()
{
	eRCInput *input = eRCInput::getInstance();
	if (!input)
		return;
	/* setExclusive hotaraste singur (eRCDeviceInputDev): tastaturile se iau exclusiv numai daca sunt telecomenzi */
	bool locked = input->islocked();
	std::multimap<std::string, eRCDevice*, eRCInput::lstr> &devices = input->getDevices();
	for (std::multimap<std::string, eRCDevice*, eRCInput::lstr>::iterator i = devices.begin(); i != devices.end(); ++i)
		i->second->setExclusive(!locked);
}

int eRCMapper::getTableSize()
{
	return (int)m_table.size();
}

bool eRCMapper::swallowsDevice(const std::string &device) const
{
	switch (m_mode)
	{
	case captureAll:
		return true;
	case captureOthers:
		return !isOwnDevice(device);
	default:
		return false;
	}
}

int eRCMapper::setCapture(int mode, int idleSeconds, int totalSeconds, int heartbeatSeconds)
{
	if (mode == captureOff)
	{
		if (m_mode != captureOff)
			stopCapture(endRequested);
		return 1;
	}
	if (mode != captureAll && mode != captureOthers && mode != captureListen)
		return 0;
	/* fara ascultator nu se opreste nimic: altfel nimeni nu ar mai putea iesi din captura */
	if ((mode == captureAll || mode == captureOthers) && !rawKey.hasPython())
	{
		eDebug("[eRCMapper] capture %d refused: nobody listens", mode);
		return 0;
	}
	bool fresh = m_mode == captureOff;
	m_mode = mode;
	m_idleSeconds = idleSeconds > 0 ? idleSeconds : 0;
	m_totalSeconds = totalSeconds > 0 ? totalSeconds : 0;
	if (mode == captureListen && (m_totalSeconds == 0 || m_totalSeconds > MAX_LISTEN_SECONDS))
		m_totalSeconds = MAX_LISTEN_SECONDS;
	m_heartbeatSeconds = heartbeatSeconds > 0 ? heartbeatSeconds : 0;
	long long t = now();
	m_start = m_lastKey = m_lastTouch = t;
	m_lastExitCode = -1;
	m_holdDone = false;
	m_holdKey = Key("", -1);
	if (fresh)
	{
		m_held.clear();
		m_events.clear();
	}
	if (!m_timer)
	{
		m_timer = eTimer::create(eApp);
		CONNECT(m_timer->timeout, eRCMapper::onTimer);
	}
	m_timer->start(500, false);
	eDebug("[eRCMapper] capture %d on (%d s without keys, %d s total, %d s heartbeat)", mode, m_idleSeconds,
		m_totalSeconds, m_heartbeatSeconds);
	return 1;
}

int eRCMapper::getCaptureMode()
{
	return m_mode;
}

int eRCMapper::getCaptureSecondsLeft()
{
	if (m_mode == captureOff)
		return 0;
	long long t = now();
	long long left = -1;
	if (m_totalSeconds)
		left = m_start + m_totalSeconds * 1000LL - t;
	if (m_idleSeconds)
	{
		long long idle = m_lastKey + m_idleSeconds * 1000LL - t;
		if (left < 0 || idle < left)
			left = idle;
	}
	if (left < 0)
		return m_totalSeconds || m_idleSeconds ? 0 : -1;
	return (int)((left + 999) / 1000);
}

void eRCMapper::touch()
{
	m_lastTouch = now();
}

void eRCMapper::onTimer()
{
	if (m_mode == captureOff)
	{
		m_timer->stop();
		return;
	}
	long long t = now();
	if (m_heartbeatSeconds && t - m_lastTouch > m_heartbeatSeconds * 1000LL)
		stopCapture(endHeartbeat);
	else if (m_totalSeconds && t - m_start > m_totalSeconds * 1000LL)
		stopCapture(endTotal);
	else if (m_idleSeconds && t - m_lastKey > m_idleSeconds * 1000LL)
		stopCapture(endIdle);
}

void eRCMapper::stopCapture(int reason)
{
	if (m_mode == captureOff)
		return;
	int mode = m_mode;
	m_mode = captureOff;
	if (m_timer)
		m_timer->stop();
	/* tastele inca apasate: eliberarea lor nu ajunge la ecranul de dupa captura */
	for (std::set<Key>::iterator i = m_held.begin(); i != m_held.end(); ++i)
		if (mode == captureAll || (mode == captureOthers && !isOwnDevice(i->first)))
			m_releaseWait.insert(*i);
	m_held.clear();
	m_events.clear();
	eDebug("[eRCMapper] capture %d off (%d)", mode, reason);
	/*emit*/ captureEnded(reason);
}

void eRCMapper::noteScan(eRCDevice *producer, int value)
{
	m_scanProducer = producer;
	m_scan = value;
}

bool eRCMapper::process(eRCDevice *producer, std::string &device, int &code, int flags)
{
	int scan = -1;
	if (producer && producer == m_scanProducer)
		scan = m_scan;
	if (flags != eRCKey::flagLong)
		m_scanProducer = 0;

	bool ascii = flags & eRCKey::flagAscii;
	int kind = ascii ? eRCKey::flagAscii : flags;
	if (ascii || kind == eRCKey::flagMake)
		m_lastKeyboard = ascii || (producer && producer->isKeyboard());
	Key key(device, code);

	/* traducerea */
	int target = -1;
	bool drop = false;
	if (!ascii && !isOwnDevice(device))
	{
		std::map<Key, int>::const_iterator it = m_table.find(key);
		if (it != m_table.end())
			target = it->second;
		else if (m_blockUnmapped.find(device) != m_blockUnmapped.end())
			drop = true;
		else if (m_defaultViper && isViperCode(code))
			target = code;
		else if (m_defaultViper && producer && producer->isKeyboard())
			target = keyboardTarget(code, flags);
	}

	if (m_mode == captureOff)
	{
		if (!m_releaseWait.empty() && !ascii)
		{
			std::set<Key>::iterator w = m_releaseWait.find(key);
			if (w != m_releaseWait.end())
			{
				if (kind == eRCKey::flagMake)
					m_releaseWait.erase(w);	/* eliberarea s-a pierdut: tasta apasata din nou merge normal */
				else
				{
					if (kind == eRCKey::flagBreak)
						m_releaseWait.erase(w);
					return true;
				}
			}
		}
	}
	else if (!ascii && kind != eRCKey::flagMake && m_held.find(key) == m_held.end())
	{
		/* o tasta apasata inainte de captura: eliberarea si repetarile ei nu se arata */
		if (swallowsDevice(device))
			return true;
	}
	else
	{
		bool swallow = swallowsDevice(device);
		long long t = now();
		if (!ascii)
		{
			if (kind == eRCKey::flagMake)
				m_held.insert(key);
			else if (kind == eRCKey::flagBreak)
				m_held.erase(key);
		}
		if (m_mode != captureOthers || !isOwnDevice(device))
			m_lastKey = t;

		Event e;
		e.seq = ++m_seq;
		e.ms = t;
		e.device = device;
		e.code = code;
		e.flags = kind;
		e.target = target;
		e.scan = scan;
		m_events.push_back(e);
		while (m_events.size() > MAX_EVENTS)
			m_events.pop_front();

		/* iesirea din captureAll, in C++: EXIT, MENU sau ESC de doua ori in 2 s, sau orice tasta tinuta 3 s */
		int reason = -1;
		if (m_mode == captureAll && !ascii)
		{
			int effective = target >= 0 ? target : code;
			if (kind == eRCKey::flagMake)
			{
				m_holdKey = key;
				m_holdStart = t;
				m_holdDone = false;
				if (effective == KEY_EXIT || effective == KEY_MENU || effective == KEY_ESC)
				{
					if (m_lastExitCode == effective && t - m_lastExitTime <= EXIT_DOUBLE_MS)
						reason = endExitKeys;
					m_lastExitCode = effective;
					m_lastExitTime = t;
				}
				else
					m_lastExitCode = -1;
			}
			else if ((kind == eRCKey::flagRepeat || kind == eRCKey::flagLong) && key == m_holdKey && !m_holdDone
				&& t - m_holdStart >= HOLD_EXIT_MS)
			{
				m_holdDone = true;
				reason = endHold;
			}
			else if (kind == eRCKey::flagBreak && key == m_holdKey)
				m_holdKey = Key("", -1);
		}

		int seq = m_seq;
		/*emit*/ rawKey(seq);
		if (reason >= 0)
			stopCapture(reason);
		if (swallow)
			return true;
	}

	if (drop)
		return true;
	if (target >= 0)
	{
		device = NATIVE_NAME;
		code = target;
	}
	return false;
}

int eRCMapper::keyboardDefault(int code, int keyboardMode)
{
	bool text = keyboardMode != eRCInput::kmNone;
	switch (code)
	{
	case KEY_ENTER:
	case KEY_KPENTER:
		return KEY_OK;
	case KEY_ESC:
		return KEY_EXIT;
	case KEY_BACKSPACE:
		return text ? -1 : KEY_EXIT;   /* cand se scrie text, Backspace sterge (KeyboardInputActions) */
	case KEY_SPACE:
		return text ? -1 : KEY_OK;     /* ca in emulator (rcsdl.cpp) */
	case KEY_F1:
		return KEY_RED;
	case KEY_F2:
		return KEY_GREEN;
	case KEY_F3:
		return KEY_YELLOW;
	case KEY_F4:
		return KEY_BLUE;
	case KEY_F5:
	case KEY_COMPOSE:                 /* tasta de meniu de langa Ctrl-ul din dreapta */
		return KEY_MENU;
	case KEY_F6:
		return KEY_INFO;
	case KEY_F7:
		return KEY_EPG;
	case KEY_KPPLUS:
		return text ? -1 : KEY_VOLUMEUP;
	case KEY_KPMINUS:
		return text ? -1 : KEY_VOLUMEDOWN;
	case KEY_KP0:
		return text ? -1 : KEY_0;
	case KEY_KP1:
		return text ? -1 : KEY_1;
	case KEY_KP2:
		return text ? -1 : KEY_2;
	case KEY_KP3:
		return text ? -1 : KEY_3;
	case KEY_KP4:
		return text ? -1 : KEY_4;
	case KEY_KP5:
		return text ? -1 : KEY_5;
	case KEY_KP6:
		return text ? -1 : KEY_6;
	case KEY_KP7:
		return text ? -1 : KEY_7;
	case KEY_KP8:
		return text ? -1 : KEY_8;
	case KEY_KP9:
		return text ? -1 : KEY_9;
	default:
		return -1;
	}
}

int eRCMapper::keyboardTarget(int code, int flags)
{
	/* sensul se hotaraste la apasare si ramane pana la eliberare (o tasta Esc care inchide un ecran de setari nu
	   isi schimba sensul intre apasare si eliberare) */
	std::map<int, int>::iterator i = m_keyboardHeld.find(code);
	if (flags == eRCKey::flagMake || i == m_keyboardHeld.end())
	{
		eRCInput *input = eRCInput::getInstance();
		int target = keyboardDefault(code, input ? input->getKeyboardMode() : (int)eRCInput::kmNone);
		if (flags == eRCKey::flagBreak)
			return target;
		m_keyboardHeld[code] = target;
		return target;
	}
	int target = i->second;
	if (flags == eRCKey::flagBreak)
		m_keyboardHeld.erase(i);
	return target;
}

void eRCMapper::noteMouse(int type, int code, int value)
{
	if (type == EV_REL)
	{
		if (code == REL_X)
			m_mouseDx += value;
		else if (code == REL_Y)
			m_mouseDy += value;
		else if (code == REL_WHEEL)
			m_mouseWheel += value;
		else
			return;
		m_mousePending = true;
	}
	else if (type == EV_KEY)
	{
		int bit = code == BTN_LEFT ? 1 : code == BTN_RIGHT ? 2 : code == BTN_MIDDLE ? 4 : 0;
		if (!bit || value == 2)
			return;
		if (value)
			m_mouseButtons |= bit;
		else
			m_mouseButtons &= ~bit;
		m_mousePending = true;
	}
	else if (type == EV_SYN && code == SYN_REPORT && m_mousePending)
	{
		m_mousePending = false;
		bool empty = m_mouse.empty();
		if (!empty && m_mouse.back().buttons == m_mouseButtons)
		{
			m_mouse.back().dx += m_mouseDx;
			m_mouse.back().dy += m_mouseDy;
			m_mouse.back().wheel += m_mouseWheel;
		}
		else
		{
			MousePacket p;
			p.dx = m_mouseDx;
			p.dy = m_mouseDy;
			p.wheel = m_mouseWheel;
			p.buttons = m_mouseButtons;
			m_mouse.push_back(p);
			while (m_mouse.size() > MAX_MOUSE)
				m_mouse.pop_front();
		}
		m_mouseDx = m_mouseDy = m_mouseWheel = 0;
		if (empty)
			/*emit*/ mouseEvent((int)m_mouse.size());
	}
}

bool eRCMapper::lastKeyFromKeyboard()
{
	return m_lastKeyboard;
}

PyObject *eRCMapper::getMouse()
{
	ePyObject list = PyList_New(0);
	if (!list)
		return list;
	for (std::deque<MousePacket>::const_iterator i = m_mouse.begin(); i != m_mouse.end(); ++i)
	{
		ePyObject tuple = PyTuple_New(4);
		PyTuple_SET_ITEM(tuple, 0, PyLong_FromLong(i->dx));
		PyTuple_SET_ITEM(tuple, 1, PyLong_FromLong(i->dy));
		PyTuple_SET_ITEM(tuple, 2, PyLong_FromLong(i->wheel));
		PyTuple_SET_ITEM(tuple, 3, PyLong_FromLong(i->buttons));
		PyList_Append(list, tuple);
		Py_DECREF(tuple);
	}
	m_mouse.clear();
	return list;
}

PyObject *eRCMapper::getEvents(int afterSequence)
{
	ePyObject list = PyList_New(0);
	if (!list)
		return list;
	for (std::deque<Event>::const_iterator i = m_events.begin(); i != m_events.end(); ++i)
	{
		if (i->seq <= afterSequence)
			continue;
		ePyObject name = PyUnicode_DecodeUTF8(i->device.data(), (Py_ssize_t)i->device.size(), "replace");
		if (!name)
		{
			PyErr_Clear();
			name = PyUnicode_FromString("?");
		}
		ePyObject tuple = PyTuple_New(7);
		PyTuple_SET_ITEM(tuple, 0, PyLong_FromLong(i->seq));
		PyTuple_SET_ITEM(tuple, 1, PyLong_FromLongLong(i->ms));
		PyTuple_SET_ITEM(tuple, 2, name);
		PyTuple_SET_ITEM(tuple, 3, PyLong_FromLong(i->code));
		PyTuple_SET_ITEM(tuple, 4, PyLong_FromLong(i->flags));
		PyTuple_SET_ITEM(tuple, 5, PyLong_FromLong(i->target));
		PyTuple_SET_ITEM(tuple, 6, PyLong_FromLong(i->scan));
		PyList_Append(list, tuple);
		Py_DECREF(tuple);
	}
	return list;
}

int eRCMapper::getLastSequence()
{
	return m_seq;
}

PyObject *eRCMapper::getDevices()
{
	ePyObject list = PyList_New(0);
	eRCInput *input = eRCInput::getInstance();
	if (!list || !input)
		return list;
	std::multimap<std::string, eRCDevice*, eRCInput::lstr> &devices = input->getDevices();
	std::string last;
	for (std::multimap<std::string, eRCDevice*, eRCInput::lstr>::iterator i = devices.begin(); i != devices.end(); ++i)
	{
		if (i != devices.begin() && i->first == last)
			continue;
		last = i->first;
		ePyObject name = PyUnicode_DecodeUTF8(last.data(), (Py_ssize_t)last.size(), "replace");
		if (!name)
		{
			PyErr_Clear();
			continue;
		}
		PyList_Append(list, name);
		Py_DECREF(name);
	}
	return list;
}

void eRCMapper::inject(int code, int flags)
{
	if (code <= 0 || code > KEY_MAX || flags < eRCKey::flagMake || flags > eRCKey::flagRepeat)
		return;
	eRCInput *input = eRCInput::getInstance();
	if (input)
	{
		/* cautare fara jurnal (getDevice scrie lista la fiecare ratare) si fara pointer tinut minte: un
		   dispozitiv poate disparea la cald */
		std::multimap<std::string, eRCDevice*, eRCInput::lstr> &devices = input->getDevices();
		std::multimap<std::string, eRCDevice*, eRCInput::lstr>::iterator i = devices.find(NATIVE_NAME);
		if (i != devices.end())
		{
			input->keyPressed(eRCKey(i->second, code, flags));
			return;
		}
	}
	ePtr<eActionMap> ptr;
	eActionMap::getInstance(ptr);
	if (ptr)
		ptr->keyPressed(NATIVE_NAME, code, flags);
}

/* inaintea dispozitivelor de intrare (rc+1), ca eRCDeviceInputDev sa-l gaseasca de la prima tasta */
eAutoInitP0<eRCMapper> init_rcmapper(eAutoInitNumbers::rc, "RC mapper");
