/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_driver_rcconsole_h
#define __lib_driver_rcconsole_h

#include <termios.h>
#include <lib/driver/rc.h>

class eRCConsoleDriver: public eRCDriver
{
	struct termios ot;
protected:
	int handle;
	ePtr<eSocketNotifier> sn;
	int m_escape;	/* HDSatelit: 0, after ESC 1, after ESC [ 2, after ESC [ [ 3 */
	long m_utf8;	/* HDSatelit: the code point being put together from an UTF-8 sequence */
	int m_utf8left;	/* HDSatelit: continuation bytes still expected (0 = none) */
	void keyPressed(int);
public:
	eRCConsoleDriver(const char *filename);
	~eRCConsoleDriver();
	void flushBuffer() const
	{
		char data[16];
		if (handle != -1)
			while ( ::read(handle, data, 16) == 16 );
	}
	void lock() const
	{
		if ( sn )
			sn->stop();
	}
	void unlock() const
	{
		if ( sn )
			sn->start();
	}
};

class eRCConsole: public eRCDevice
{
public:
	void handleCode(long code);
	eRCConsole(eRCDriver *driver);
	const char *getDescription() const;
	const char *getKeyDescription(const eRCKey &key) const;
	int getKeyCompatibleCode(const eRCKey &key) const;
};

#endif
