/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_gui_elabel_h
#define __lib_gui_elabel_h

#include <lib/gui/ewidget.h>

#ifndef SWIG
	/* HDSatelit: a one-line text that does not fit in its box scrolls instead of being cut. The text stays ~2 s at
	   its beginning, moves slowly to the left until its end is visible, stays ~2 s, comes back to the beginning and
	   starts again. A text that fits is drawn exactly as before and never moves. One timer serves all the boxes that
	   scroll at a time; each tick redraws only those boxes (a label, or the selected row of a list), and a box that
	   is not visible stops until it is drawn again. The owner (eLabel, eListbox) gives the widget and the redraw. */
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
		/* during the paint: how far a text that overflows by `overflow` px is moved to the left now */
	int shift(int overflow);
		/* One line of text in `rect`, like gPainter::renderText(rect, text, flags) with `font` set. When it does not
		   fit, it is drawn left aligned from its beginning, cut cleanly at the edge of `rect` (no "..."), and moved by
		   `scroller` when one is given (the selected row of a list, a label). A text with several lines (RT_WRAP in a
		   box of two lines or more, or a new line in it) is drawn as before. Returns the overflow in px (0: fits). */
	static int drawLine(gPainter &painter, gFont *font, const eRect &rect, const std::string &text, int flags, eDerulare *scroller);
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
		alignBlock
	};
	
	void setVAlign(int align);
	void setHAlign(int align);
	
	void setForegroundColor(const gRGB &col);
	void setShadowColor(const gRGB &col);
	void setShadowOffset(const ePoint &offset);
	void setNoWrap(int nowrap);
	void clearForegroundColor();
	
	eSize calculateSize();
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
#ifndef SWIG
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
