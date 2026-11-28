/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gdi/lcd.h>

#include <stdio.h>
#include <string.h>

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
static bool hdsLcdGeometry(int &xres, int &yres, int &bpp, bool *littleEndian = 0, bool *duo2 = 0)
{
	if (duo2)
		*duo2 = false;
	if (littleEndian)
		*littleEndian = false;
	bool bgr565le = false;
	char model[32] = {0};
	FILE *board = fopen("/proc/stb/info/model", "r");
	const bool dm9 = board && fscanf(board, "%31s", model) == 1 &&
		(!strcmp(model, "dm900") || !strcmp(model, "dm920"));
	if (board)
		fclose(board);
	// On Vu+ /proc/stb/info/model says "dm8000"; the real name is in /proc/stb/info/vumodel ("duo2").
	char vumodel[32] = {0};
	FILE *vu = fopen("/proc/stb/info/vumodel", "r");
	if (vu)
	{
		if (fscanf(vu, "%31s", vumodel) != 1)
			vumodel[0] = 0;
		fclose(vu);
	}
	if (!strcmp(model, "duo2") || !strcmp(model, "vuduo2") || !strcmp(vumodel, "duo2"))
	{
		// The Duo2 VFD is grayscale; its color TFT is a separate device.
		if (duo2)
			*duo2 = true;
		xres = 140; yres = 32; bpp = 8;
		return true;
	}
	if (dm9)
	{
		FILE *format = fopen("/proc/stb/lcd/colorformat", "r");
		char value[32] = {0};
		bgr565le = format && fscanf(format, "%31s", value) == 1 && !strcmp(value, "BGR_565_LE");
		if (format)
			fclose(format);
	}
	const char *nodes[] = {"xres", "yres", "bpp"};
	char text[3][32];
	for (int i = 0; i < 3; ++i)
	{
		char filename[64];
		snprintf(filename, sizeof(filename), "/proc/stb/lcd/%s", nodes[i]);
		FILE *f = fopen(filename, "r");
		// Dream lcd.ko can expose colorformat instead of bpp on DM9x0.
		if (!f && i == 2 && bgr565le)
		{
			strcpy(text[i], "10");
			continue;
		}
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
			if (littleEndian)
				*littleEndian = bgr565le && bpp == 16;
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
	hds_color_buffer = 0;
	bool littleEndian = false;
	bool color = hdsLcdGeometry(xres, yres, bpp, &littleEndian, &hds_duo2);
#ifdef NO_LCD
	// Fara antetele mono, folosim geometria cunoscuta a panoului.
	if (color)
#endif
	{
	lcdfd = open("/dev/dbox/oled0", hds_duo2 ? O_RDWR | O_NONBLOCK : O_RDWR);
	if (lcdfd < 0)
	{
		FILE *f=hds_duo2 ? 0 : fopen("/proc/stb/lcd/oled_brightness", "w");
		if (!f && !hds_duo2)
			f = fopen("/proc/stb/fp/oled_brightness", "w");
		if (f)
		{
			is_oled = 2;
			fclose(f);
		}
		lcdfd = open("/dev/dbox/lcd0", hds_duo2 ? O_RDWR | O_NONBLOCK : O_RDWR);
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
#else
		if (hds_duo2)
		{
			int binary = 1;
			ioctl(lcdfd, 0x1015, &binary);
		}
#endif
		if (color)
			is_oled = 3;
	}
	}
	instance=this;

	setSize(xres, yres, bpp);
	if (littleEndian)
		hds_color_buffer = new unsigned char[_stride * res.height()];
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
	delete [] hds_color_buffer;
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

int eDBoxLCD::writeHdsDuo2(int first, int second, int third, int fourth)
{
	if (!hds_duo2 || lcdfd < 0 || locked)
		return -1;
	// The segment engine owns this output. Do not modify the summary buffer.
	// hds_update controls only the competing desktop updates, as on LED panels.
	unsigned char pixels[140 * 32] = {0};
	const int masks[] = {first, second, third, fourth};
	// a, b, c, d, e, f, g, dot: rectangles inside each 35-pixel cell. The digits are 22 px high and 16 px wide,
	// centered on the 32 px panel (on the whole height they looked too big on a real Duo2).
	const int rects[8][4] = {
		{11, 5, 23, 7}, {23, 7, 25, 15}, {23, 17, 25, 25}, {11, 25, 23, 27},
		{9, 17, 11, 25}, {9, 7, 11, 15}, {11, 15, 23, 17}, {27, 25, 29, 27}
	};
	for (int digit = 0; digit < 4; ++digit)
		for (int bit = 0; bit < 8; ++bit)
			if (masks[digit] & (1 << bit))
				for (int y = rects[bit][1]; y < rects[bit][3]; ++y)
					for (int x = rects[bit][0]; x < rects[bit][2]; ++x)
						pixels[y * 140 + digit * 35 + x] = 255;
	// One nonblocking attempt. A short/refused frame is retried by the engine.
	return write(lcdfd, pixels, sizeof(pixels));
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
		{
			const unsigned char *frame = _buffer;
			const int length = _stride * res.height();
			if (hds_color_buffer)
			{
				const int padding = res.width() == 400 && res.height() == 240 ? 16 : 0;
				// Convert and align each physical row without changing drawing memory.
				// Black padding is per row; no pixel is borrowed from the row above.
				for (int row = 0; row < length; row += _stride)
				{
					memset(hds_color_buffer + row, 0, padding);
					for (int x = padding; x < _stride; x += 2)
					{
						const int src = row + x - padding;
						hds_color_buffer[row + x] = _buffer[src + 1];
						hds_color_buffer[row + x + 1] = _buffer[src];
					}
				}
				frame = hds_color_buffer;
			}
			{ static bool reported = false; if (write(lcdfd, frame, length) < 0 && !reported) { reported = true; eDebug("[LCD] write failed (%m)"); } }
		}
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

