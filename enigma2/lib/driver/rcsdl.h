/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_driver_rcsdl_h
#define __lib_driver_rcsdl_h

/*
 * Rescris pentru SDL2.
 */

#include <lib/driver/rc.h>

#include <SDL.h>

class eSDLInputDevice : public eRCDevice
{
private:
	bool m_escape;
	int translateKey(SDL_Keycode key);

public:
	eSDLInputDevice(eRCDriver *driver);
	~eSDLInputDevice();

	virtual void handleCode(long arg);
	void handleText(const char *utf8);
	virtual const char *getDescription() const;
};

class eSDLInputDriver : public eRCDriver
{
private:
	static eSDLInputDriver *instance;

public:
	eSDLInputDriver();
	~eSDLInputDriver();

	static eSDLInputDriver *getInstance() { return instance; }

	void keyPressed(const SDL_KeyboardEvent *key);
	void textInput(const char *utf8);
};

#endif
