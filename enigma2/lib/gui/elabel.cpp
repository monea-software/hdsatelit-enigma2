/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gui/elabel.h>
#include <lib/gdi/font.h>
#include <lib/base/ebase.h>
#include <fribidi/fribidi.h>
#include <algorithm>
#include <map>
#include <set>

/* Codurile valide schimba numai culoarea. Cele incomplete raman text literal. */
static bool hdsParseTextColors(const std::string &source, std::string &plain, std::vector<size_t> &starts, std::vector<unsigned int> &colors)
{
	plain.clear();
	starts.clear();
	colors.clear();
	size_t pos = 0;
	while (pos < source.size())
	{
		bool valid = source.size() - pos >= 10 && source[pos] == '\\' && source[pos + 1] == 'c';
		unsigned int color = 0;
		if (valid)
		{
			size_t n = pos + 2;
			while (n < pos + 10)
			{
				unsigned char ch = source[n];
				int digit = -1;
				if (ch >= '0' && ch <= '9')
				{
					digit = ch - '0';
				}
				else if (ch >= 'a' && ch <= 'f')
				{
					digit = ch - 'a' + 10;
				}
				else if (ch >= 'A' && ch <= 'F')
				{
					digit = ch - 'A' + 10;
				}
				else if (ch >= ':' && ch <= '?')
				{
					/* 0.7.4 (AJPanel, forum 588): the old notation writes A..F as : ; < = > ?, as in the GPL enigma2 sources (OE-Alliance) */
					digit = ch - ':' + 10;
				}
				if (digit < 0)
				{
					valid = false;
					break;
				}
				color = (color << 4) | digit;
				++n;
			}
		}
		if (valid)
		{
			starts.push_back(plain.size());
			colors.push_back(color);
			pos += 10;
		}
		else
		{
			plain.push_back(source[pos]);
			++pos;
		}
	}
	return !colors.empty();
}

struct hdsColorText
{
	std::string text;
	std::vector<size_t> starts;
	std::vector<unsigned int> colors;

	hdsColorText(const std::string &source)
	{
		/* 0.7.4: \C (back to the colour of the widget) is drawn by eTextPara (lib/gdi/font.cpp) with the \c codes of the same
		   text, so such a text stays whole here */
		if (source.find("\\c") == std::string::npos || source.find("\\C") != std::string::npos)
			text = source;
		else
			hdsParseTextColors(source, text, starts, colors);
	}
};

void shape(std::vector<unsigned long> &string, const std::vector<unsigned long> &text);

static void hdsAlignText(eTextPara *para, int flags)
{
	if (flags & gPainter::RT_HALIGN_RIGHT)
		para->realign(eTextPara::dirRight);
	else if (flags & gPainter::RT_HALIGN_CENTER)
		para->realign(eTextPara::dirCenter);
	else if (flags & gPainter::RT_HALIGN_BLOCK)
		para->realign(eTextPara::dirBlock);
	else if (flags & gPainter::RT_HALIGN_LEFT_EXPLICIT)
		para->realign(eTextPara::dirLeft);
}

/* Aceeasi decodare si aceeasi ordine vizuala ca eTextPara. Prefixele formate de
   shape stabilesc inceputurile; o ligatura pastreaza culoarea primei litere. */
static std::vector<int> hdsGlyphColors(const hdsColorText &text, gFont *font)
{
	std::vector<unsigned long> logical, shaped;
	std::vector<size_t> byteOffsets;
	const char *begin = text.text.c_str(), *p = begin;
	while (*p)
	{
		byteOffsets.push_back(p - begin);
		unsigned int unicode = (unsigned char)*p++;
		if (unicode & 0x80)
		{
			int follow = ((unicode & 0xE0) == 0xC0) ? 1 : ((unicode & 0xF0) == 0xE0) ? 2 : ((unicode & 0xF8) == 0xF0) ? 3 : 0;
			int n = 0;
			while (n < follow && (((unsigned char)p[n]) & 0xC0) == 0x80)
				++n;
			if (follow && n == follow)
			{
				unicode &= 0xFF >> (follow + 2);
				for (n = 0; n < follow; ++n)
					unicode = (unicode << 6) | ((unsigned char)*p++ & 0x3F);
			}
		}
		logical.push_back(unicode);
	}
	shape(shaped, logical);
	if (shaped.empty())
		return std::vector<int>();
	std::vector<int> shapedColors(shaped.size(), -1);
	for (size_t c = 0; c < text.starts.size(); ++c)
	{
		size_t count = std::lower_bound(byteOffsets.begin(), byteOffsets.end(), text.starts[c]) - byteOffsets.begin();
		std::vector<unsigned long> prefix(logical.begin(), logical.begin() + count), prefixShape;
		shape(prefixShape, prefix);
		if (prefixShape.size() < shapedColors.size())
			std::fill(shapedColors.begin() + prefixShape.size(), shapedColors.end(), c);
	}
	std::vector<FriBidiChar> input(shaped.begin(), shaped.end()), visual(shaped.size());
	std::vector<FriBidiStrIndex> visualToLogical(shaped.size());
	FriBidiCharType direction = FRIBIDI_TYPE_ON;
	if (!fribidi_log2vis(&input[0], input.size(), &direction, &visual[0], 0, &visualToLogical[0], 0))
		return std::vector<int>();
	std::vector<int> result;
	std::map<unsigned long, bool> available;
	for (size_t i = 0; i < visual.size(); ++i)
	{
		if (visualToLogical[i] < 0 || (size_t)visualToLogical[i] >= shapedColors.size())
			return std::vector<int>();
		unsigned long chr = visual[i];
		if (chr == '\\' && i + 1 < visual.size() && (visual[i + 1] == 'n' || visual[i + 1] == 'r' || visual[i + 1] == 't'))
		{
			++i;
			continue;
		}
		if (chr == '\t' || chr == '\n' || chr == '\r' || chr == 0x8A || chr == 0xE08A ||
			chr == 0x86 || chr == 0xE086 || chr == 0x87 || chr == 0xE087)
			continue;
		if (chr == 0x2010 || chr == 0xAD)
			chr = '-';
		if (available.find(chr) == available.end())
			available[chr] = eTextPara::missingGlyphs(font->family, std::vector<unsigned long>(1, chr)) == 0;
		if (available[chr])
			result.push_back(shapedColors[visualToLogical[i]]);
	}
	return result;
}

/* Fiecare culoare are un paragraf complet, cu aceeasi masurare, aliniere si
   impartire pe linii. Glifele celorlalte culori sunt ascunse, fara decuparea
   marginilor lor netezite. Paragrafele trimise firului de desen nu se modifica. */
static void hdsRenderColorPara(gPainter &painter, gFont *font, const eRect &rect, const hdsColorText &text,
	int flags, eTextPara *base, const ePoint &offset, int markedPos = -1)
{
	if (text.colors.empty())
	{
		painter.renderPara(base, offset);
		return;
	}
	std::vector<int> colors = hdsGlyphColors(text, font);
	if (colors.size() != (size_t)base->size())
	{
		/* Daca fontul refuza o glifa la desen, textul intreg ramane lizibil. */
		painter.renderPara(base, offset);
		return;
	}
	std::vector<int> layers(1, -1);
	for (size_t c = 0; c < text.colors.size(); ++c)
	{
		int same = -1;
		for (size_t n = 1; n < layers.size(); ++n)
			if (text.colors[layers[n]] == text.colors[c])
				same = layers[n];
		if (same >= 0)
			std::replace(colors.begin(), colors.end(), (int)c, same);
		else if (std::find(colors.begin(), colors.end(), (int)c) != colors.end())
			layers.push_back(c);
	}
	std::vector<ePtr<eTextPara> > paragraphs;
	std::vector<int> paragraphColors;
	for (size_t layer = 0; layer < layers.size(); ++layer)
	{
		int color = layers[layer];
		if (std::find(colors.begin(), colors.end(), color) == colors.end())
			continue;
		ePtr<eTextPara> para = new eTextPara(rect);
		para->setFont(font);
		para->renderString(text.text.c_str(), (flags & gPainter::RT_WRAP) ? RS_WRAP : 0);
		hdsAlignText(para, flags);
		if ((size_t)para->size() != colors.size())
		{
			painter.renderPara(base, offset);
			return;
		}
		for (int glyph = 0; glyph < para->size(); ++glyph)
		{
			if (colors[glyph] != color)
				para->setGlyphFlag(glyph, GS_SOFTHYPHEN);
			if (markedPos == -2 || markedPos == glyph)
				para->setGlyphFlag(glyph, GS_INVERT);
		}
		paragraphs.push_back(para);
		paragraphColors.push_back(color);
	}
	for (size_t layer = 0; layer < paragraphs.size(); ++layer)
	{
		int color = paragraphColors[layer];
		if (color >= 0)
			painter.setForegroundColor(gRGB(text.colors[color]));
		painter.renderPara(paragraphs[layer], offset);
	}
}

static void hdsRenderColorText(gPainter &painter, gFont *font, const eRect &rect, const hdsColorText &text, int flags)
{
	if (text.colors.empty())
	{
		painter.renderText(rect, text.text, flags);
		return;
	}
	ePtr<eTextPara> para = new eTextPara(rect);
	para->setFont(font);
	para->renderString(text.text.c_str(), (flags & gPainter::RT_WRAP) ? RS_WRAP : 0);
	hdsAlignText(para, flags);
	int dy = 0;
	if (flags & gPainter::RT_VALIGN_CENTER)
	{
		eRect box = para->getBoundBox();
		dy = rect.top() + (rect.height() - box.height()) / 2 - box.top();
	}
	hdsRenderColorPara(painter, font, rect, text, flags, para, ePoint(0, dy));
}

	/* HDSatelit: the scroll of a one-line text that does not fit (elabel.h). A tick every 50 ms moves the text by 2 px
	   (40 px per second, slow enough to read while it moves); the two stops last 40 ticks (2 s). An overflow of at most
	   1 px (rounding of the glyph edges) counts as fitting. */
static const int scrollTickMs = 50, scrollStepPx = 2, scrollHoldTicks = 40, scrollTolerancePx = 1;
	/* never freed: a label destroyed while the program ends must still find it */
static std::set<eDerulare*> &scrollRunning = *new std::set<eDerulare*>;
static eTimer *scrollTimer = 0;

eDerulare::eDerulare(): m_running(false), m_phase(0), m_ticks(0), m_pos(0), m_end(0), m_seen(0)
{
}

eDerulare::~eDerulare()
{
	stop();
}

void eDerulare::reset()
{
	m_phase = 0;
	m_ticks = 0;
	m_pos = 0;
}

void eDerulare::beginPaint()
{
	m_seen = 0;
}

void eDerulare::endPaint(bool painted)
{
	if (!painted)
		return;
	m_end = m_seen;
	if (m_end <= 0)
	{
		stop();
		reset();
	}
	else if (m_pos > m_end)
		m_pos = m_end;
}

int eDerulare::shift(int overflow)
{
	if (overflow <= 0)
		return 0;
	if (overflow > m_seen)
		m_seen = overflow;
	if (!m_running)
	{
		reset();
		if (m_end < overflow)
			m_end = overflow;
		start();
	}
	return m_pos < overflow ? m_pos : overflow;
}

void eDerulare::start()
{
	if (m_running)
		return;
	m_running = true;
	scrollRunning.insert(this);
	if (!scrollTimer)
	{
			/* one reference kept for the whole run: the main loop takes and drops its own around each tick */
		scrollTimer = eTimer::create(eApp);
		scrollTimer->AddRef();
		scrollTimer->timeout.connect(sigc::ptr_fun(&eDerulare::tickAll));
	}
	if (!scrollTimer->isActive())
		scrollTimer->start(scrollTickMs, false);
}

void eDerulare::stop()
{
	if (!m_running)
		return;
	m_running = false;
	scrollRunning.erase(this);
	if (scrollRunning.empty() && scrollTimer)
		scrollTimer->stop();
}

void eDerulare::tick()
{
	eWidget *widget = scrollWidget();
	if (!widget || !widget->isVisible())
	{
			/* hidden: it starts again from the beginning when it is drawn again */
		stop();
		reset();
		return;
	}
	if (m_phase == 0)
	{
		if (++m_ticks >= scrollHoldTicks)
		{
			m_phase = 1;
			m_ticks = 0;
		}
	}
	else if (m_phase == 1)
	{
		m_pos += scrollStepPx;
		if (m_pos >= m_end)
		{
			m_pos = m_end;
			m_phase = 2;
			m_ticks = 0;
		}
		scrollRedraw();
	}
	else if (++m_ticks >= scrollHoldTicks)
	{
		reset();
		scrollRedraw();
	}
}

void eDerulare::tickAll()
{
		/* a copy: a tick can stop its own scroll (and a redraw can start another one) */
	std::set<eDerulare*> running(scrollRunning);
	for (std::set<eDerulare*>::iterator i = running.begin(); i != running.end(); ++i)
		if (scrollRunning.count(*i))
			(*i)->tick();
	if (scrollRunning.empty() && scrollTimer)
		scrollTimer->stop();
}

bool eDerulare::surelyFits(const std::string &text, const gFont *font, int width)
{
		/* no glyph of the skin fonts is wider than 1.25 times the font size: a text with fewer characters than the
		   width allows for that fits without being measured */
	int chars = 0;
	for (std::string::const_iterator c = text.begin(); c != text.end(); ++c)
		if ((*c & 0xC0) != 0x80)
			++chars;
	return chars * (font->pointSize + font->pointSize / 4) <= width;
}

bool eDerulare::oneLine(const gFont *font, int height)
{
	float line = fontRenderClass::getInstance() ? fontRenderClass::getInstance()->getLineHeight(*font) : 0;
	if (line <= 0)
		line = font->pointSize;
	return height < 2 * line;
}

int eDerulare::drawLine(gPainter &painter, gFont *font, const eRect &rect, const std::string &text, int flags, eDerulare *scroller)
{
	return drawLine(painter, font, rect, text, flags, scroller, false);
}

int eDerulare::drawLine(gPainter &painter, gFont *font, const eRect &rect, const std::string &source, int flags, eDerulare *scroller, bool textColors)
{
	hdsColorText colored(textColors ? source : "");
	const std::string &text = textColors ? colored.text : source;
	if (text.empty() || !font || rect.width() <= 0 || text.find('\n') != std::string::npos ||
		surelyFits(text, font, rect.width()) || ((flags & gPainter::RT_WRAP) && !oneLine(font, rect.height())))
	{
		if (textColors && font)
			hdsRenderColorText(painter, font, rect, colored, flags);
		else
			painter.renderText(rect, text, flags);
		return 0;
	}
	ePtr<eTextPara> para = new eTextPara(rect);
	para->setFont(font);
	para->renderString(text.c_str(), 0);
	if (!para->size())
		return 0;
	eRect bounds = para->getBoundBox();
	int overflowLeft = rect.left() - bounds.left();
	int overflowRight = bounds.right() - rect.right();
	int overflow = (overflowLeft > 0 ? overflowLeft : 0) + (overflowRight > 0 ? overflowRight : 0);
	if (overflow <= scrollTolerancePx)
	{
			/* it fits: the same drawing as renderText (lib/gdi/grc.cpp), with the line measured here */
		if (flags & gPainter::RT_HALIGN_RIGHT)
			para->realign(eTextPara::dirRight);
		else if (flags & gPainter::RT_HALIGN_CENTER)
			para->realign(eTextPara::dirCenter);
		else if (flags & gPainter::RT_HALIGN_BLOCK)
			para->realign(eTextPara::dirBlock);
		else if (flags & gPainter::RT_HALIGN_LEFT_EXPLICIT)
			para->realign(eTextPara::dirLeft);
		overflow = 0;
	}
	else
		para->realign(para->isRightToLeft() ? eTextPara::dirRight : eTextPara::dirLeft);
	int dy = 0;
	if (flags & gPainter::RT_VALIGN_CENTER)
	{
		eRect bbox = para->getBoundBox();
		dy = rect.top() + (rect.height() - bbox.height()) / 2 - bbox.top();
	}
	if (!overflow)
	{
		if (textColors)
			hdsRenderColorPara(painter, font, rect, colored, flags & ~gPainter::RT_WRAP, para, ePoint(0, dy));
		else
			painter.renderPara(para, ePoint(0, dy));
		return 0;
	}
	int dx = scroller ? scroller->shift(overflow) : 0;
	if (!para->isRightToLeft())
		dx = -dx;
	painter.clip(rect);
	if (textColors)
		hdsRenderColorPara(painter, font, rect, colored, 0, para, ePoint(dx, dy));
	else
		painter.renderPara(para, ePoint(dx, dy));
	painter.clippop();
	return overflow;
}

	/* HDSatelit: the line of a text field with a cursor (Components/Input.py: InputBox, PinInput) is not wrapped. When
	   it is wider than the label, it moves sideways so that the glyph under the cursor stays inside: past the right edge
	   the whole line moves left by the excess, before the left edge it moves right. A line that fits (the sum of the
	   glyph advances, the trailing space of the cursor included) is drawn exactly as before (0). The same rule for the
	   text settings in lists is in lib/gui/elistboxcontent.cpp. */
static int cursorShift(eTextPara *para, int glyph, int width)
{
	int glyphs = para->size(), length = 0;
	for (int i = 0; i < glyphs; ++i)
		length += para->getGlyphBBox(i).width();
	if (length <= width)
		return 0;
	eRect cursor = para->getGlyphBBox(glyph);
	int dx = 0;
	if (cursor.right() > width)
		dx = width - cursor.right();
	if (cursor.left() + dx < 0)
		dx = -cursor.left();
	return dx;
}

/* HDSatelit 0.7.4: the painter moved into the padding and clipped to the text area for the text of a label */
struct hdsPadding
{
	gPainter &painter;
	ePoint origin;
	bool on;
	hdsPadding(gPainter &p, const ePoint &o, const eSize &area, bool use): painter(p), origin(o), on(use)
	{
		if (on)
		{
			painter.moveOffset(origin);
			painter.clip(eRect(ePoint(0, 0), area));
		}
	}
	~hdsPadding()
	{
		if (on)
		{
			painter.clippop();
			painter.moveOffset(ePoint(-origin.x(), -origin.y()));
		}
	}
};

eLabel::eLabel(eWidget *parent, int markedPos): eWidget(parent), m_derulare(this), m_overflow(-1), m_measured(0)
{
	m_pos = markedPos;
	ePtr<eWindowStyle> style;
	getStyle(style);
	
	style->getFont(eWindowStyle::fontStatic, m_font);
	
		/* Keep automatic text direction unless the skin sets halign. */
	m_valign = alignTop;
	m_halign = alignAuto;
	
	m_have_foreground_color = 0;
	m_have_shadow_color = 0;
	
	m_nowrap = 0;
	m_text_border_width = 0;
	m_padding_left = m_padding_top = m_padding_right = m_padding_bottom = 0;
	m_fontscale_type = 0;
	m_fontscale_floor = 0;
	m_font_scaled_valid = false;
	m_underline = 0;
}

void eLabel::setUnderline(int underline)
{
	m_underline = underline ? 1 : 0;
	invalidate();
}

void eLabel::paintUnderline(gPainter &painter, const eSize &area, const std::string &text, int flags)
{
	/* the text measured as renderText lays it out (wrap, alignment), the line one point under it */
	ePtr<eTextPara> para = new eTextPara(eRect(0, 0, area.width(), area.height()));
	para->setFont(m_font);
	para->renderString(text.c_str(), (flags & gPainter::RT_WRAP) ? RS_WRAP : 0);
	if (flags & gPainter::RT_HALIGN_CENTER)
		para->realign(eTextPara::dirCenter);
	else if (flags & gPainter::RT_HALIGN_RIGHT)
		para->realign(eTextPara::dirRight);
	else if (flags & gPainter::RT_HALIGN_BLOCK)
		para->realign(eTextPara::dirBlock);
	eRect box = para->getBoundBox();
	if (box.empty())
		return;
	int dy = 0;
	if (flags & gPainter::RT_VALIGN_CENTER)
		dy = (area.height() - box.height()) / 2 - box.top();
	else if (flags & gPainter::RT_VALIGN_BOTTOM)
		dy = area.height() - box.height() - box.top();
	int y = box.bottom() + dy + 1;
	if (y >= area.height())
		y = area.height() - 1;
	painter.fill(eRect(box.left(), y, box.width(), 1));
}

void eLabel::setFontScale(int type, int floor)
{
	m_fontscale_type = (type == 1 || type == 2) ? type : 0;
	m_fontscale_floor = floor;
	m_font_scaled_valid = false;
	m_overflow = -1;
	invalidate();
}

ePtr<gFont> eLabel::scaledFont(const eSize &area, const std::string &text)
{
	/* the font for the text of this paint: the skin font, or a smaller one when fontScale is set and the text is
	   wider than the label; measured again only when the text, the font or the size changed */
	if (!m_fontscale_type || !m_font || text.empty() || area.width() <= 0)
		return m_font;
	if (!m_font_scaled_valid)
	{
		m_font_scaled_valid = true;
		m_font_scaled = m_font;
		ePtr<eTextPara> para = new eTextPara(eRect(0, 0, 100000, area.height() > 0 ? area.height() : 1));
		para->setFont(m_font);
		para->renderString(text.c_str(), 0);
		int w = para->getBoundBox().width();
		if (w > area.width())
		{
			int size = m_font->pointSize;
			int floor = m_fontscale_floor < 0 ? size + m_fontscale_floor : m_fontscale_floor;
			int fit = (int)((long long)size * area.width() / w);
			int newsize = fit > floor ? fit : floor;
			if (newsize > 0 && newsize < size)
				m_font_scaled = new gFont(m_font->family, newsize);
		}
	}
	return m_font_scaled;
}

/* HDSatelit 0.7.4: the label font swapped for the scaled one during a paint (fontScale), put back after */
struct hdsFontScale
{
	ePtr<gFont> &font;
	ePtr<gFont> saved;
	hdsFontScale(ePtr<gFont> &f, const ePtr<gFont> &scaled): font(f), saved(f)
	{
		font = scaled;
	}
	~hdsFontScale()
	{
		font = saved;
	}
};

void eLabel::setPadding(int left, int top, int right, int bottom)
{
	m_padding_left = left > 0 ? left : 0;
	m_padding_top = top > 0 ? top : 0;
	m_padding_right = right > 0 ? right : 0;
	m_padding_bottom = bottom > 0 ? bottom : 0;
	m_overflow = -1;
	invalidate();
}

eSize eLabel::textSize() const
{
	int w = size().width() - m_padding_left - m_padding_right, h = size().height() - m_padding_top - m_padding_bottom;
	return eSize(w > 0 ? w : 0, h > 0 ? h : 0);
}

int eLabel::event(int event, void *data, void *data2)
{
	switch (event)
	{
	case evtPaint:
	{
		ePtr<eWindowStyle> style;
		
		getStyle(style);
		
		eWidget::event(event, data, data2);

		gPainter &painter = *(gPainter*)data2;
			/* HDSatelit 0.7.4: padding (skins written for other images): the text in the widget minus the padding, the
			   background and the border on the whole widget */
		eSize tsize = textSize();
		hdsPadding padding(painter, ePoint(m_padding_left, m_padding_top), tsize, hasPadding());
		hdsColorText colored(m_text);
		hdsFontScale fontscale(m_font, scaledFont(tsize, colored.text));
		
		if (m_pos != -1)
		{
			style->setStyle(painter, eWindowStyle::styleLabel);
			ePtr<eTextPara> para = new eTextPara(eRect(0, 0, tsize.width(), tsize.height()));
			para->setFont(m_font);
			para->renderString(colored.text.empty()?0:colored.text.c_str(), 0);

			if (m_halign == alignLeft)
				para->realign(eTextPara::dirLeft);
			else if (m_halign == alignCenter)
				para->realign(eTextPara::dirCenter);
			else if (m_halign == alignRight)
				para->realign(eTextPara::dirRight);
			else if (m_halign == alignBlock)
				para->realign(eTextPara::dirBlock);

			int glyphs = para->size();
				/* HDSatelit: the line moved sideways so that the cursor stays inside (cursorShift above) */
			int dx = (m_pos >= 0 && m_pos < glyphs) ? cursorShift(para, m_pos, tsize.width()) : 0;

			if (m_pos == -2) {  /* All glyphs inverted */
				eRect bbox;
				int left = 0, right = 0;
				for (int i=0; i<glyphs; i++)
					para->setGlyphFlag(i, GS_INVERT);
				if (glyphs > 0) {
					bbox = para->getGlyphBBox(0);
					left = bbox.left();
					bbox = para->getGlyphBBox(glyphs-1);
					right = bbox.left() + bbox.width();
				}
				bbox = eRect(left, 0, right-left, tsize.height());
				painter.fill(bbox);
			} else if ((m_pos < 0) || (m_pos >= glyphs))
				eWarning("glyph index %d in eLabel out of bounds!", m_pos);
			else
			{
				para->setGlyphFlag(m_pos, GS_INVERT);
				eRect bbox;
				bbox = para->getGlyphBBox(m_pos);
				bbox = eRect(bbox.left() + dx, 0, bbox.width(), tsize.height());
				painter.fill(bbox);
			}

			int textFlags = m_halign == alignLeft ? gPainter::RT_HALIGN_LEFT_EXPLICIT :
				m_halign == alignCenter ? gPainter::RT_HALIGN_CENTER :
				m_halign == alignRight ? gPainter::RT_HALIGN_RIGHT :
				m_halign == alignBlock ? gPainter::RT_HALIGN_BLOCK : 0;
			hdsRenderColorPara(painter, m_font, eRect(0, 0, tsize.width(), tsize.height()), colored,
				textFlags, para, ePoint(dx, 0), m_pos);
			if (!colored.colors.empty())
				style->setStyle(painter, eWindowStyle::styleLabel);
			return 0;
		} else
		{
			painter.setFont(m_font);
			style->setStyle(painter, eWindowStyle::styleLabel);
			
			if (m_have_shadow_color)
				painter.setForegroundColor(m_shadow_color);
			else if (m_have_foreground_color)
				painter.setForegroundColor(m_foreground_color);
			
			int flags = 0;
			if (m_valign == alignTop)
				flags |= gPainter::RT_VALIGN_TOP;
			else if (m_valign == alignCenter)
				flags |= gPainter::RT_VALIGN_CENTER;
			else if (m_valign == alignBottom)
				flags |= gPainter::RT_VALIGN_BOTTOM;
	
			if (m_halign == alignLeft)
				flags |= gPainter::RT_HALIGN_LEFT_EXPLICIT;
			else if (m_halign == alignCenter)
				flags |= gPainter::RT_HALIGN_CENTER;
			else if (m_halign == alignRight)
				flags |= gPainter::RT_HALIGN_RIGHT;
			else if (m_halign == alignBlock)
				flags |= gPainter::RT_HALIGN_BLOCK;
			
			if (!m_nowrap)
				flags |= gPainter::RT_WRAP;

				/* HDSatelit: a one-line text wider than the label scrolls (eDerulare); it is measured once for
				   each text, font and size, and the same line is drawn moved at each step */
			if (m_overflow < 0)
				measureLine();
			m_derulare.beginPaint();
			if (m_overflow > 0)
			{
				int dx = m_derulare.shift(m_overflow);
				if (!m_line->isRightToLeft())
					dx = -dx;
				int dy = 0;
				if (m_valign == alignCenter)
				{
					eRect bbox = m_line->getBoundBox();
					dy = (tsize.height() - bbox.height()) / 2 - bbox.top();
				}
				if (m_have_shadow_color)
					painter.renderPara(m_line, ePoint(dx - m_shadow_offset.x(), dy - m_shadow_offset.y()));
				else
				{
					if (m_text_border_width > 0)
						paintTextBorder(painter, eRect(), std::string(), 0, m_line,
							ePoint(dx - m_shadow_offset.x(), dy - m_shadow_offset.y()));
					hdsRenderColorPara(painter, m_font, eRect(0, 0, tsize.width(), tsize.height()), colored,
						0, m_line, ePoint(dx - m_shadow_offset.x(), dy - m_shadow_offset.y()));
				}
				if (m_have_shadow_color)
				{
					if (m_text_border_width > 0)
						paintTextBorder(painter, eRect(), std::string(), 0, m_line, ePoint(dx, dy));
					if (!m_have_foreground_color)
						style->setStyle(painter, eWindowStyle::styleLabel);
					else
						painter.setForegroundColor(m_foreground_color);
					painter.setBackgroundColor(m_text_border_width > 0 ? m_text_border_color : m_shadow_color);
					hdsRenderColorPara(painter, m_font, eRect(0, 0, tsize.width(), tsize.height()), colored,
						0, m_line, ePoint(dx, dy));
				}
				if (!colored.colors.empty())
				{
					style->setStyle(painter, eWindowStyle::styleLabel);
					if (m_have_foreground_color)
						painter.setForegroundColor(m_foreground_color);
				}
				m_derulare.endPaint(true);
				return 0;
			}
			m_derulare.endPaint(true);

				/* if we don't have shadow, m_shadow_offset will be 0,0 */
			eRect textRect(-m_shadow_offset.x(), -m_shadow_offset.y(), tsize.width(), tsize.height());
			if (m_have_shadow_color)
				painter.renderText(textRect, colored.text, flags);
			else
			{
				if (m_text_border_width > 0)
					paintTextBorder(painter, textRect, colored.text, flags, 0, ePoint(0, 0));
				hdsRenderColorText(painter, m_font, textRect, colored, flags);
			}
			
			if (m_have_shadow_color)
			{
				if (m_text_border_width > 0)
					paintTextBorder(painter, eRect(0, 0, tsize.width(), tsize.height()), colored.text, flags, 0, ePoint(0, 0));
				if (!m_have_foreground_color)
					style->setStyle(painter, eWindowStyle::styleLabel);
				else
					painter.setForegroundColor(m_foreground_color);
				painter.setBackgroundColor(m_text_border_width > 0 ? m_text_border_color : m_shadow_color);
				hdsRenderColorText(painter, m_font, eRect(0, 0, tsize.width(), tsize.height()), colored, flags);
			}
			if (m_underline && !colored.text.empty())
				paintUnderline(painter, tsize, colored.text, flags);
			if (!colored.colors.empty())
			{
				style->setStyle(painter, eWindowStyle::styleLabel);
				if (m_have_foreground_color)
					painter.setForegroundColor(m_foreground_color);
			}
			
			return 0;
		}
	}
	case evtChangedText:
		m_font_scaled_valid = false;
		m_overflow = -1;
		m_derulare.reset();
		invalidate();
		return 0;
		/* HDSatelit: a new font, alignment or size is measured again at the next paint; the scroll starts again only
		   when the overflow changed (a converter that sets the same font again at each refresh does not stop it) */
	case evtChangedFont:
		m_font_scaled_valid = false;
	case evtChangedAlignment:
	case evtChangedMarkedPos:
		m_overflow = -1;
		invalidate();
		return 0;
	case evtChangedSize:
		m_font_scaled_valid = false;
		m_overflow = -1;
		return eWidget::event(event, data, data2);
	default:
		return eWidget::event(event, data, data2);
	}
}

void eLabel::setText(const std::string &string)
{
	if (m_text == string)
		return;
	m_text = string;
	event(evtChangedText);
}

void eLabel::setMarkedPos(int markedPos)
{
	m_pos = markedPos;
	event(evtChangedMarkedPos);
}

void eLabel::setFont(gFont *font)
{
	m_font = font;
	event(evtChangedFont);
}

gFont* eLabel::getFont()
{
	return m_font;
}

void eLabel::setVAlign(int align)
{
	m_valign = align;
	event(evtChangedAlignment);
}

void eLabel::setHAlign(int align)
{
	m_halign = align;
	event(evtChangedAlignment);
}

void eLabel::setForegroundColor(const gRGB &col)
{
	if ((!m_have_foreground_color) || !(m_foreground_color == col))
	{
		m_foreground_color = col;
		m_have_foreground_color = 1;
		invalidate();
	}
}

void eLabel::setShadowColor(const gRGB &col)
{
	if ((!m_have_shadow_color) || !(m_shadow_color == col))
	{
		m_shadow_color = col;
		m_have_shadow_color = 1;
		invalidate();
	}
}

void eLabel::setShadowOffset(const ePoint &offset)
{
	m_shadow_offset = offset;
}

void eLabel::setBorderColor(const gRGB &col)
{
	m_text_border_color = col;
	invalidate();
}

void eLabel::setBorderWidth(int width)
{
	m_text_border_width = width < 0 ? 0 : (width > 3 ? 3 : width);
	invalidate();
}

/* The font engine has no stroked glyphs: the outline is the text drawn in the outline colour at every whole offset
   within the width (8 copies for 1 point, 20 for 2, 36 for 3), under the text. The glyph blit writes a colour taken
   between the painter background and foreground for each pixel it touches (it does not mix with the surface), so the
   copies are drawn with the outline colour on both sides: a soft edge of one copy cannot lighten a pixel already set by
   another. Afterwards the text colour comes back and the glyph edges of the text blend with the outline colour (as they
   do with the shadow colour). */
void eLabel::paintTextBorder(gPainter &painter, const eRect &rect, const std::string &text, int flags, eTextPara *line, const ePoint &offset)
{
	int w = m_text_border_width;
	painter.setForegroundColor(m_text_border_color);
	painter.setBackgroundColor(m_text_border_color);
	for (int y = -w; y <= w; ++y)
		for (int x = -w; x <= w; ++x)
		{
			if ((!x && !y) || x * x + y * y > w * w + w)
				continue;
			if (line)
				painter.renderPara(line, ePoint(offset.x() + x, offset.y() + y));
			else
				painter.renderText(eRect(rect.left() + x, rect.top() + y, rect.width(), rect.height()), text, flags);
		}
	if (m_have_foreground_color)
		painter.setForegroundColor(m_foreground_color);
	else
	{
		ePtr<eWindowStyle> style;
		if (!getStyle(style))
			style->setStyle(painter, eWindowStyle::styleLabel);
	}
	painter.setBackgroundColor(m_text_border_color);
}

void eLabel::setNoWrap(int nowrap)
{
	if (m_nowrap != nowrap)
	{
		m_nowrap = nowrap;
		m_overflow = -1;
		invalidate();
	}
}

void eLabel::clearForegroundColor()
{
	if (m_have_foreground_color)
	{
		m_have_foreground_color = 0;
		invalidate();
	}
}

eLabel::~eLabel()
{
}

void eLabel::measureLine()
{
	hdsColorText colored(m_text);
	const std::string &text = colored.text;
		/* HDSatelit: only a text without a cursor, on one line (noWrap, or a label too low for two lines) */
	m_overflow = 0;
	m_line = 0;
	if (m_pos == -1 && m_font && !text.empty() && textSize().width() > 0 && text.find('\n') == std::string::npos &&
		!eDerulare::surelyFits(text, m_font, textSize().width()) && (m_nowrap || eDerulare::oneLine(m_font, textSize().height())))
	{
		ePtr<eTextPara> para = new eTextPara(eRect(0, 0, textSize().width(), textSize().height()));
		para->setFont(m_font);
		para->renderString(text.c_str(), 0);
		eRect bounds = para->getBoundBox();
		int overflowLeft = -bounds.left();
		int overflowRight = bounds.right() - textSize().width();
		int overflow = (overflowLeft > 0 ? overflowLeft : 0) + (overflowRight > 0 ? overflowRight : 0);
		if (para->size() && overflow > scrollTolerancePx)
		{
			m_overflow = overflow;
			m_line = para;
		}
	}
	if (m_overflow != m_measured)
	{
		m_measured = m_overflow;
		m_derulare.reset();
	}
}

eSize eLabel::calculateSize()
{
	hdsColorText colored(m_text);
	ePtr<eTextPara> p = new eTextPara(eRect(0, 0, textSize().width(), textSize().height()));
	
	p->setFont(m_font);
	p->renderString(colored.text.empty()?0:colored.text.c_str(), m_nowrap ? 0 : RS_WRAP);
	
	eRect bbox = p->getBoundBox();
	/* HDSatelit 0.7.4: with the padding around the text, as the widget needs it */
	return eSize(bbox.width() + m_padding_left + m_padding_right, bbox.height() + m_padding_top + m_padding_bottom);
}

eSize eLabel::calculateTextSize(gFont *font, const std::string &string, eSize targetSize, bool nowrap)
{
	/* the colour codes of a text (\c...) are not drawn, so they are not measured either; no font = nothing to measure */
	if (!font || string.empty() || targetSize.width() <= 0)
		return eSize(0, 0);
	hdsColorText colored(string);
	ePtr<eTextPara> p = new eTextPara(eRect(0, 0, targetSize.width(), targetSize.height() > 0 ? targetSize.height() : 1));
	p->setFont(font);
	p->renderString(colored.text.empty() ? 0 : colored.text.c_str(), nowrap ? 0 : RS_WRAP);
	return p->getBoundBox().size();
}
