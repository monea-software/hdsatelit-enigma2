/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_gui_elabel_h
#define __lib_gui_elabel_h

#include <lib/gui/ewidget.h>

#ifndef SWIG
	/* One-line overflow waits at the start, scrolls towards the end, waits and repeats.
	   RTL starts at the right. One timer redraws only visible scrolling widgets. */
class eDerulare
{
public:
	eDerulare();
	virtual ~eDerulare();
		/* the text, the font, the size or the selected row changed: back to the beginning */
	void reset();
		/* around a paint of the box: the scroll goes as far as the widest text that overflowed in it */
	void beginPaint();
	void endPaint(bool painted);
		/* Scroll distance; the drawing chooses the sign from the text direction. */
	int shift(int overflow);
		/* One line in rect; overflow scrolls from the logical beginning (right for RTL).
		   Multiline text keeps its wrapping. Returns the overflow in px (0: fits). */
	static int drawLine(gPainter &painter, gFont *font, const eRect &rect, const std::string &text, int flags, eDerulare *scroller);
		/* Codurile de culoare sunt optionale; apelantul restabileste apoi stilul de baza. */
	static int drawLine(gPainter &painter, gFont *font, const eRect &rect, const std::string &text, int flags, eDerulare *scroller, bool textColors);
		/* true when `text` is surely narrower than `width` px with `font`, without measuring it */
	static bool surelyFits(const std::string &text, const gFont *font, int width);
		/* true when a box `height` px tall holds only one line of `font` */
	static bool oneLine(const gFont *font, int height);
protected:
	virtual eWidget *scrollWidget() = 0;
	virtual void scrollRedraw() = 0;
private:
	void start();
	void stop();
	void tick();
	static void tickAll();
	bool m_running;
	int m_phase, m_ticks, m_pos, m_end, m_seen;
};
#endif

class eLabel: public eWidget
{
public:
	eLabel(eWidget *parent, int markedPos = -1);
	void setText(const std::string &string);
	void setMarkedPos(int markedPos);
	void setFont(gFont *font);
	gFont* getFont();

	enum
	{
		alignLeft,
		alignTop=alignLeft,
		alignCenter,
		alignRight,
		alignBottom=alignRight,
		alignBlock,
		alignAuto
	};
	
	void setVAlign(int align);
	void setHAlign(int align);
	
	void setForegroundColor(const gRGB &col);
	void setShadowColor(const gRGB &col);
	void setShadowOffset(const ePoint &offset);
		/* HDSatelit: the outline of the text (borderColor/borderWidth on labels in skins, also called
		   textBorderColor/textBorderWidth); black when only the width is given, at most 3 points */
	void setBorderColor(const gRGB &col);
	void setBorderWidth(int width);
	void setTextBorderColor(const gRGB &col) { setBorderColor(col); }
	void setTextBorderWidth(int width) { setBorderWidth(width); }
	void setNoWrap(int nowrap);
		/* HDSatelit 0.7.4: the space between the edges and the text (padding="left,top,right,bottom" of the skins written
		   for other images); 0 = as before */
	void setPadding(int left, int top, int right, int bottom);
		/* HDSatelit 0.7.4: fontScale of the skins written for other images, only where the skin asks for it: a text too
		   wide for the label is drawn with smaller letters until it fits (type 1 "size", 2 "width": both make the
		   letters smaller here), not below the floor (floor < 0: the font size plus floor). 0 = as before (a one-line
		   text that does not fit scrolls) */
	void setFontScale(int type, int floor);
		/* HDSatelit 0.7.4: underline="1" (skins written for other images): a line of one point under the text, in the
		   text colour; 0 = as before */
	void setUnderline(int underline);
	void clearForegroundColor();
	
	eSize calculateSize();
		/* HDSatelit 0.7.4, the call of the plugins written for other images (eLabel.calculateTextSize(font, text,
		   eSize(w, h)[, nowrap])): the size of a text in a font inside targetSize, wrapped unless nowrap, without a
		   label (nothing is drawn or invalidated) */
	static eSize calculateTextSize(gFont *font, const std::string &string, eSize targetSize, bool nowrap = false);
	~eLabel();
protected:
	ePtr<gFont> m_font;
	int m_valign, m_halign;
	std::string m_text;
	int event(int event, void *data=0, void *data2=0);
	int m_pos;
private:
	int m_have_foreground_color, m_have_shadow_color;
	gRGB m_foreground_color, m_shadow_color;
	ePoint m_shadow_offset;
	int m_nowrap;
	int m_padding_left, m_padding_top, m_padding_right, m_padding_bottom;
	int m_fontscale_type, m_fontscale_floor;
	int m_underline;
	void paintUnderline(gPainter &painter, const eSize &area, const std::string &text, int flags);
	ePtr<gFont> m_font_scaled;
	bool m_font_scaled_valid;
	ePtr<gFont> scaledFont(const eSize &area, const std::string &text);
	bool hasPadding() const { return m_padding_left || m_padding_top || m_padding_right || m_padding_bottom; }
	eSize textSize() const;
	gRGB m_text_border_color;
	int m_text_border_width;
#ifndef SWIG
		/* the text in the outline colour at every offset of the outline width (static text or the scrolling line) */
	void paintTextBorder(gPainter &painter, const eRect &rect, const std::string &text, int flags, eTextPara *line, const ePoint &offset);
		/* HDSatelit: the scroll of a one-line text that does not fit (eDerulare above) */
	class Derulare: public eDerulare
	{
	public:
		Derulare(eLabel *label): m_label(label) { }
	protected:
		eWidget *scrollWidget() { return m_label; }
		void scrollRedraw() { m_label->invalidate(); }
	private:
		eLabel *m_label;
	};
	Derulare m_derulare;
		/* the text measured on one line: -1 not yet, 0 fits or more lines, else how many px it overflows; and the
		   last measured value, to restart the scroll only when it changed */
	int m_overflow, m_measured;
	ePtr<eTextPara> m_line;
	void measureLine();
#endif
	
	enum eLabelEvent
	{
		evtChangedText = evtUserWidget,
		evtChangedFont,
		evtChangedAlignment,
		evtChangedMarkedPos
	};
};

#endif
