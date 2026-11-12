#ifndef __lib_gui_epixmap_h
#define __lib_gui_epixmap_h

#include <lib/gui/ewidget.h>

class ePixmap: public eWidget
{
	int m_alphatest;
	int m_scale;
public:
	ePixmap(eWidget *parent);

	void setPixmap(gPixmap *pixmap);
	void setPixmap(ePtr<gPixmap> &pixmap);
	void setPixmapFromFile(const char *filename);
	void setAlphatest(int alphatest); /* 1 for alphatest, 2 for alphablend */
	/* 0 = the picture as it is, at 0,0; 1 = stretched over the whole widget (as before). HDSatelit 0.7.4, the scale
	   names of the skins written for other images (keepAspect, centerScaled, leftTop, moveCenter, fill...): the
	   bits below; an older image without them stretches the picture, as with 1 */
	enum {
		scaleNone = 0, scaleStretch = 1, scaleKeepAspect = 2, scaleFill = 4, scaleMove = 8,
		scaleHCenter = 16, scaleRight = 32, scaleVCenter = 64, scaleBottom = 128
	};
	void setScale(int scale);
		/* the names of the images the plugins are written for: the flags of gPainter there (BT_SCALE 4,
		   BT_KEEP_ASPECT_RATIO 8, BT_HALIGN_CENTER 16, BT_HALIGN_RIGHT 32, BT_VALIGN_CENTER 64, BT_VALIGN_BOTTOM 128),
		   turned into the bits above */
	void setPixmapScale(int flags);
	void setPixmapScaleFlags(int flags) { setPixmapScale(flags); }
	void setBorderWidth(int pixel);
	void setBorderColor(const gRGB &color);
protected:
	ePtr<gPixmap> m_pixmap;
	int event(int event, void *data=0, void *data2=0);
	void checkSize();
private:
	enum eLabelEvent
	{
		evtChangedPixmap = evtUserWidget,
	};
	bool m_have_border_color;
	int m_border_width;
	gRGB m_border_color;
};

#endif
