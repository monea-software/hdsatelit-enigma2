/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gdi/lcd.h>

#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <stdlib.h>

#if defined(HAVE_DBOX_FP_H) && defined(HAVE_DBOX_LCD_KS0713_H)
#include <dbox/fp.h>
#include <dbox/lcd-ks0713.h>
#else
#define NO_LCD 1
#endif

#include <lib/gdi/esize.h>
#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/gdi/glcddc.h>

eDBoxLCD *eDBoxLCD::instance;

eLCD::eLCD()
{
	lcdfd = -1;
	locked=0;
	hds_update=1;
	_buffer=0;
}

void eLCD::setSize(int xres, int yres, int bpp)
{
	res = eSize(xres, yres);
	_buffer=new unsigned char[xres * yres * bpp/8];
	memset(_buffer, 0, res.height()*res.width()*bpp/8);
	_stride=res.width()*bpp/8;
	eDebug("lcd buffer %p %d bytes, stride %d", _buffer, xres*yres*bpp/8, _stride);
}

eLCD::~eLCD()
{
	delete [] _buffer;
}

int eLCD::lock()
{
	if (locked || lcdfd < 0)
		return -1;

	locked=1;
	return lcdfd;
}

void eLCD::unlock()
{
	locked=0;
}

// Geometria trebuie sa fie intreaga si plauzibila inainte de desen.
static bool hdsLcdGeometry(int &xres, int &yres, int &bpp)
{
	const char *nodes[] = {"xres", "yres", "bpp"};
	char text[3][32];
	for (int i = 0; i < 3; ++i)
	{
		char filename[64];
		snprintf(filename, sizeof(filename), "/proc/stb/lcd/%s", nodes[i]);
		FILE *f = fopen(filename, "r");
		if (!f)
			return false;
		int read = fscanf(f, "%31s", text[i]);
		fclose(f);
		if (read != 1)
			return false;
	}
	const int bases[] = {16, 10};
	for (int base = 0; base < 2; ++base)
	{
		long size[3];
		bool valid = true;
		for (int i = 0; i < 3; ++i)
		{
			char *end;
			size[i] = strtol(text[i], &end, bases[base]);
			valid = valid && end != text[i] && *end == 0;
		}
		if (valid && size[0] >= 320 && size[0] <= 1920 &&
			size[1] >= 180 && size[1] <= 1080 &&
			(size[2] == 16 || size[2] == 24 || size[2] == 32))
		{
			xres = size[0]; yres = size[1]; bpp = size[2];
			return true;
		}
	}
	return false;
}

eDBoxLCD::eDBoxLCD()
{
	int xres=132, yres=64, bpp=8;
	is_oled = 0;
	inverted = 0;
	bool color = hdsLcdGeometry(xres, yres, bpp);
#ifdef NO_LCD
	// Fara antetele mono, numai geometria color autorizeaza cadrele.
	if (color)
#endif
	{
	lcdfd = open("/dev/dbox/oled0", O_RDWR);
	if (lcdfd < 0)
	{
		FILE *f=fopen("/proc/stb/lcd/oled_brightness", "w");
		if (!f)
			f = fopen("/proc/stb/fp/oled_brightness", "w");
		if (f)
		{
			is_oled = 2;
			fclose(f);
		}
		lcdfd = open("/dev/dbox/lcd0", O_RDWR);
	} else
	{
		eDebug("found OLED display!");
		is_oled = 1;
	}

	if (lcdfd<0)
		eDebug("couldn't open LCD - load lcd.o!");
	else
	{
#ifndef NO_LCD
		int i=LCD_MODE_BIN;
		ioctl(lcdfd, LCD_IOCTL_ASC_MODE, &i);
#endif
		if (color)
			is_oled = 3;
	}
	}
	instance=this;

	setSize(xres, yres, bpp);
}

void eDBoxLCD::setInverted(unsigned char inv)
{
	inverted=inv;
	update();
}

int eDBoxLCD::setLCDContrast(int contrast)
{
#ifndef NO_LCD
	int fp;
	if((fp=open("/dev/dbox/fp0", O_RDWR))<=0)
	{
		eDebug("[LCD] can't open /dev/dbox/fp0");
		return(-1);
	}

	if(ioctl(lcdfd, LCD_IOCTL_SRV, &contrast))
	{
		eDebug("[LCD] can't set lcd contrast");
	}
	close(fp);
#endif
	return(0);
}

int eDBoxLCD::setLCDBrightness(int brightness)
{
	brightness = brightness < 0 ? 0 : (brightness > 255 ? 255 : brightness);
	eDebug("setLCDBrightness %d", brightness);
	FILE *f=fopen("/proc/stb/lcd/oled_brightness", "w");
	if (!f)
		f = fopen("/proc/stb/fp/oled_brightness", "w");
	if (f)
	{
		if (fprintf(f, "%d", brightness) == 0)
			eDebug("write /proc/stb/lcd/oled_brightness failed!! (%m)");
		fclose(f);
	}
	else
	{
#ifndef NO_LCD
		int fp;
		if((fp=open("/dev/dbox/fp0", O_RDWR))<=0)
		{
			eDebug("[LCD] can't open /dev/dbox/fp0");
			return(-1);
		}

		if(ioctl(fp, FP_IOCTL_LCD_DIMM, &brightness)<=0)
			eDebug("[LCD] can't set lcd brightness (%m)");
		close(fp);
#endif
	}
	return(0);
}

eDBoxLCD::~eDBoxLCD()
{
	if (lcdfd>=0)
	{
		close(lcdfd);
		lcdfd=-1;
	}
}

eDBoxLCD *eDBoxLCD::getInstance()
{
	return instance;
}

void eDBoxLCD::update()
{
	if (lcdfd >= 0 && !locked && hds_update)
	{
		if (!is_oled || is_oled == 2)
		{
			unsigned char raw[132*8];
			int x, y, yy;
			for (y=0; y<8; y++)
			{
				for (x=0; x<132; x++)
				{
					int pix=0;
					for (yy=0; yy<8; yy++)
					{
						pix|=(_buffer[(y*8+yy)*132+x]>=108)<<yy;
					}
					raw[y*132+x]=(pix^inverted);
				}
			}
			{ static bool reported = false; if (write(lcdfd, raw, 132*8) < 0 && !reported) { reported = true; eDebug("[LCD] write failed (%m)"); } }
		}
		else if (is_oled == 3)
			{ static bool reported = false; if (write(lcdfd, _buffer, _stride * res.height()) < 0 && !reported) { reported = true; eDebug("[LCD] write failed (%m)"); } }
		else
		{
			unsigned char raw[64*64];
			int x, y;
			memset(raw, 0, 64*64);
			for (y=0; y<64; y++)
			{
				int pix=0;
				for (x=0; x<128 / 2; x++)
				{
					pix = (_buffer[y*132 + x * 2 + 2] & 0xF0) |(_buffer[y*132 + x * 2 + 1 + 2] >> 4);
					if (inverted)
						pix = 0xFF - pix;
					raw[y*64+x] = pix;
				}
			}
			{ static bool reported = false; if (write(lcdfd, raw, 64*64) < 0 && !reported) { reported = true; eDebug("[LCD] write failed (%m)"); } }
		}
	}
}

