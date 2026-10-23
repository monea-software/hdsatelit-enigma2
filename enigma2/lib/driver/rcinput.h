/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __rcdbox_h
#define __rcdbox_h

#include <lib/driver/rc.h>

class eRCDeviceInputDev: public eRCDevice
{
	int iskeyboard;
	bool ismouse;	/* HDSatelit: relative pointer (REL_X, REL_Y, BTN_LEFT): a mouse, a touchpad, an air mouse */
public:
	void handleCode(long code);
	eRCDeviceInputDev(eRCInputEventDriver *driver);
	const char *getDescription() const;
	void setExclusive(bool);
	bool isKeyboard() const { return iskeyboard; }
};

#endif
