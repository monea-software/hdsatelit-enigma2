/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/driver/rc.h>

#include <asm/types.h>
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <linux/input.h>

#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/base/eerror.h>

/*
 *  note on the enigma input layer:
 *  the enigma input layer (rc*) supports n different devices which
 *  all have completely different interfaces, mapped down to 32bit + 
 *  make/break/release codes mapped down (via xml files) to "actions".
 *  this was necessary to support multiple remote controls with proprietary
 *  interfaces. now everybody is using input devices, and thus adding
 *  another input layer seems to be a bit overkill. BUT:
 *  image a remote control with two hundred buttons. each and every function
 *  in enigma can be bound to a button. no need to use them twice. 
 *  for example, you would have KEY_MENU assigned to a menu for setup etc.,
 *  but no audio and video settings, since you have special keys for that,
 *  and you don't want to display a big menu with entries that are available
 *  with another single key.
 *  then image a remote control with ten buttons. do you really want to waste
 *  KEY_MENU for a simple menu? you need the audio/video settings there too.
 *  take this just as a (bad) example. another (better) example might be front-
 *  button-keys. usually you have KEY_UP, KEY_DOWN, KEY_POWER. you don't want
 *  them to behave like the remote-control-KEY_UP, KEY_DOWN and KEY_POWER,
 *  don't you? 
 *  so here we can map same keys of different input devices to different 
 *  actions. have fun.
 */

eRCDevice::eRCDevice(std::string id, eRCDriver *driver): driver(driver), id(id)
{
	input=driver->getInput();
	driver->addCodeListener(this);
	eRCInput::getInstance()->addDevice(id, this);
}

eRCDevice::~eRCDevice()
{
	driver->removeCodeListener(this);
	eRCInput::getInstance()->removeDevice(id, this);
}

eRCDriver::eRCDriver(eRCInput *input): input(input), enabled(1)
{
}

eRCDriver::~eRCDriver()
{
	for (std::list<eRCDevice*>::iterator i=listeners.begin(); i!=listeners.end(); ++i)
		delete *i;
}

void eRCShortDriver::keyPressed(int)
{
	__u16 rccode;
	while (1)
	{
		if (read(handle, &rccode, 2)!=2)
			break;
		if (enabled && !input->islocked())
			for (std::list<eRCDevice*>::iterator i(listeners.begin()); i!=listeners.end(); ++i)
				(*i)->handleCode(rccode);
	}
}

eRCShortDriver::eRCShortDriver(const char *filename): eRCDriver(eRCInput::getInstance())
{
	handle=open(filename, O_RDONLY|O_NONBLOCK);
	if (handle<0)
	{
		eDebug("failed to open %s", filename);
		sn=0;
	} else
	{
		sn=eSocketNotifier::create(eApp, handle, eSocketNotifier::Read);
		CONNECT(sn->activated, eRCShortDriver::keyPressed);
	}
}

eRCShortDriver::~eRCShortDriver()
{
	if (handle>=0)
		close(handle);
}

void eRCInputEventDriver::keyPressed(int what)
{
	struct input_event ev;
	while (handle >= 0)
	{
		ssize_t n = read(handle, &ev, sizeof(struct input_event));
		if (n != sizeof(struct input_event))
		{
			if (n < 0 && errno == ENODEV)
				closeGone();
			break;
		}
		if (enabled && !input->islocked())
			for (std::list<eRCDevice*>::iterator i(listeners.begin()); i!=listeners.end(); ++i)
				(*i)->handleCode((long)&ev);
	}
	/* HDSatelit: un dispozitiv USB scos da POLLHUP/POLLERR fara POLLIN; cu numai Read cerut, bucla
	   principala nu chema pe nimeni si primea imediat acelasi lucru (procesorul la maximum, jurnalul plin) */
	if (what & (POLLHUP | POLLERR))
		closeGone();
}

void eRCInputEventDriver::closeGone()
{
	if (m_gone)
		return;
	m_gone = true;
	if (sn)
		sn->stop();
	if (handle >= 0)
		close(handle);
	handle = -1;
	m_grabbed = false;
	/*emit*/ gone();
}

eRCInputEventDriver::eRCInputEventDriver(const char *filename): eRCDriver(eRCInput::getInstance()), m_grabbed(false), m_gone(false)
{
	handle=open(filename, O_RDONLY|O_NONBLOCK);
	if (handle<0)
	{
		eDebug("failed to open %s", filename);
		sn=0;
	} else
	{
		sn=eSocketNotifier::create(eApp, handle, eSocketNotifier::Read | eSocketNotifier::Error | eSocketNotifier::Hungup);
		CONNECT(sn->activated, eRCInputEventDriver::keyPressed);
	}
}

std::string eRCInputEventDriver::getDeviceName()
{
	/* HDSatelit: la un nume de 128 de octeti sau mai lung nucleul nu pune terminatorul */
	char name[128]="";
	if (handle >= 0 && ::ioctl(handle, EVIOCGNAME(sizeof(name) - 1), name) < 0)
		name[0] = 0;
	name[sizeof(name) - 1] = 0;
	return name;
}

bool eRCInputEventDriver::hasCode(int type, int code)
{
	unsigned char bits[KEY_MAX / 8 + 1];
	if (handle < 0 || code < 0 || code > KEY_MAX)
		return false;
	memset(bits, 0, sizeof(bits));
	if (::ioctl(handle, EVIOCGBIT(type, sizeof(bits)), bits) < 0)
		return false;
	return (bits[code / 8] >> (code % 8)) & 1;
}

void eRCInputEventDriver::setExclusive(bool b)
{
	/*
	 * HDSatelit: the remote control is grabbed without any condition.
	 * The old code grabbed only when bit 0x1E of EVIOCGBIT(0) was set, a marker of the old Dreambox
	 * kernels that no current kernel sets (the Viper remote reports EV=0x100013). Without the grab the
	 * kernel keyboard handler also got every remote key and wrote it on /dev/tty0, where the Console RC
	 * driver read it as ASCII: in the channel list (kmAscii) Left gave "ESC [ 1 8 ~", the '8' went to
	 * ServiceList.moveToChar and the list jumped to its first entry instead of one page back.
	 * m_grabbed avoids a second EVIOCGRAB on an already grabbed device (EBUSY) at eRCInput::unlock().
	 */
	if (handle >= 0 && b != m_grabbed)
	{
		int grab = b;
		if (::ioctl(handle, EVIOCGRAB, grab) < 0)
			eDebug("[eRCInputEventDriver] EVIOCGRAB(%d) failed: %m", grab);
		else
			m_grabbed = b;
	}
}

eRCInputEventDriver::~eRCInputEventDriver()
{
	if (handle>=0)
		close(handle);
}

eRCConfig::eRCConfig()
{
	reload();
}

eRCConfig::~eRCConfig()
{
	save();
}

void eRCConfig::set( int delay, int repeat )
{
	rdelay = delay;
	rrate = repeat;
}

void eRCConfig::reload()
{
	rdelay=500;
	rrate=100;
}

void eRCConfig::save()
{
}

eRCInput *eRCInput::instance;

eRCInput::eRCInput()
{
	ASSERT( !instance);
	instance=this;
	locked = 0;
	keyboardMode = kmNone;
}

eRCInput::~eRCInput()
{
}

void eRCInput::close()
{
}

bool eRCInput::open()
{
	return false;
}

void eRCInput::lock()
{
	locked=1;
	for (std::multimap<std::string,eRCDevice*,lstr>::iterator i=devices.begin(); i != devices.end(); ++i)
		i->second->setExclusive(false);
}

void eRCInput::unlock()
{
	locked=0;
	for (std::multimap<std::string,eRCDevice*,lstr>::iterator i=devices.begin(); i != devices.end(); ++i)
		i->second->setExclusive(true);
}

void eRCInput::addDevice(const std::string &id, eRCDevice *dev)
{
	devices.insert(std::pair<std::string,eRCDevice*>(id, dev));
}

void eRCInput::removeDevice(const std::string &id, eRCDevice *dev)
{
	/* numai intrarea acestui dispozitiv, nu si a altuia cu acelasi nume */
	std::pair<std::multimap<std::string,eRCDevice*,lstr>::iterator, std::multimap<std::string,eRCDevice*,lstr>::iterator> r = devices.equal_range(id);
	for (std::multimap<std::string,eRCDevice*,lstr>::iterator i = r.first; i != r.second; )
	{
		if (!dev || i->second == dev)
			devices.erase(i++);
		else
			++i;
	}
}

eRCDevice *eRCInput::getDevice(const std::string &id)
{
	std::multimap<std::string,eRCDevice*,lstr>::iterator i=devices.find(id);
	if (i == devices.end())
	{
		eDebug("failed, possible choices are:");
		for (std::multimap<std::string,eRCDevice*,lstr>::iterator i=devices.begin(); i != devices.end(); ++i)
			eDebug("%s", i->first.c_str());
		return 0;
	}
	return i->second;
}

std::multimap<std::string,eRCDevice*,eRCInput::lstr> &eRCInput::getDevices()
{
	return devices;
}

eAutoInitP0<eRCInput> init_rcinput(eAutoInitNumbers::rc, "RC Input layer");
