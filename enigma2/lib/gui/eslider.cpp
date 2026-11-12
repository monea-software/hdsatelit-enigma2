/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gui/eslider.h>
#include <lib/gdi/desennetezit.h>
#include <algorithm>

bool eSlider::m_gradient_enabled = true;

void eSlider::setForegroundGradientEnabled(int enabled)
{
	// Se aplica tuturor barelor la urmatoarea redesenare.
	m_gradient_enabled = enabled != 0;
}

eSlider::eSlider(eWidget *parent)
	:eWidget(parent), m_have_border_color(false), m_have_foreground_color(false), m_have_start(false),
	m_min(0), m_max(100), m_value(0), m_start(0), m_orientation(orHorizontal),
	m_orientation_swapped(0), m_border_width(0), m_gradient_vertical(0), m_is_scrollbar(false)
{
}

void eSlider::setBackgroundPixmap(ePtr<gPixmap> &pixmap)
{
	m_background_pixmap = pixmap;
	invalidate();
}

void eSlider::setPixmap(ePtr<gPixmap> &pixmap)
{
	setPixmap(pixmap.operator->());
}

void eSlider::setPixmap(gPixmap *pixmap)
{
	m_pixmap = pixmap;
	event(evtChangedSlider);
}

void eSlider::setBorderWidth(int pixel)
{
	m_border_width=pixel;
	invalidate();
}

void eSlider::setForegroundColor(const gRGB &color)
{
	m_foreground_color = color;
	m_have_foreground_color = true;
	invalidate();
}

void eSlider::setBorderColor(const gRGB &color)
{
	m_border_color=color;
	m_have_border_color=true;
	invalidate();
}

void eSlider::setForegroundGradient(const gRGB &first, const gRGB &last, int vertical)
{
	m_gradient.clear();
	m_gradient.push_back(first);
	m_gradient.push_back(last);
	m_gradient_vertical = vertical != 0;
	invalidate();
}

void eSlider::setForegroundGradient(const gRGB &first, const gRGB &middle, const gRGB &last, int vertical)
{
	setForegroundGradient(first, last, vertical);
	m_gradient.insert(m_gradient.begin() + 1, middle);
}

int eSlider::event(int event, void *data, void *data2)
{
	switch (event)
	{
	case evtPaint:
	{
		ePtr<eWindowStyle> style;

		eSize s(size());
		getStyle(style);
			/* paint background */
		eWidget::event(evtPaint, data, data2);
		if (m_background_pixmap)
			((gPainter*)data2)->blit(m_background_pixmap, ePoint(0, 0), eRect(), gPainter::BT_ALPHATEST);

		gPainter &painter = *(gPainter*)data2;

		style->setStyle(painter, eWindowStyle::styleLabel); // TODO - own style
			/* HDSatelit 0.7.4: the Scrollbar and Slider colours of the window style, when the skin gives them and the bar has
			   no colour of its own */
		gRGB style_fg, style_bg, style_border;
		int style_set = 0;
		style->sliderColors(m_is_scrollbar, style_fg, style_bg, style_border, style_set);
		if ((style_set & 2) && !hasBackgroundColor() && !m_background_pixmap)
		{
			painter.setBackgroundColor(style_bg);
			painter.clear();
		}
		if (m_have_foreground_color)
			painter.setForegroundColor(m_foreground_color);
		else if (style_set & 1)
			painter.setForegroundColor(style_fg);
		
		if (!m_pixmap && ((m_gradient_enabled && !m_gradient.empty()) || getCornerRadius()))
		{
			const eRect &r = m_currently_filled.extends;
			gDesenNetezit forma;
			forma.forma = gDesenNetezit::dreptunghi;
			forma.x0 = r.left(); forma.y0 = r.top(); forma.x1 = r.right(); forma.y1 = r.bottom();
			forma.raza = getCornerRadius();
			forma.culoare_pictor = 1;
			if (m_gradient_enabled)
				forma.gradient = m_gradient;
			forma.gradient_vertical = m_gradient_vertical;
			painter.desenNetezit(forma);
		}
		else if (!m_pixmap)
			painter.fill(m_currently_filled);
		else
			painter.blit(m_pixmap, ePoint(0, 0), m_currently_filled.extends, isTransparent() ? gPainter::BT_ALPHATEST : 0);

// border
		if (m_have_border_color)
			painter.setForegroundColor(m_border_color);
		else if (style_set & 4)
			painter.setForegroundColor(style_border);
		painter.fill(eRect(0, 0, s.width(), m_border_width));
		painter.fill(eRect(0, m_border_width, m_border_width, s.height()-m_border_width));
		painter.fill(eRect(m_border_width, s.height()-m_border_width, s.width()-m_border_width, m_border_width));
		painter.fill(eRect(s.width()-m_border_width, m_border_width, m_border_width, s.height()-m_border_width));

		return 0;
	}
	case evtChangedSlider:
	{
		int num_pix = 0, start_pix = 0;
		gRegion old_currently_filled = m_currently_filled;

		int pixsize = (m_orientation == orHorizontal) ? size().width() : size().height();

		if (m_min < m_max)
		{
			long long val_range = (long long)m_max - m_min;
			int start = std::max(m_min, std::min(m_max, m_start));
			int end = std::max(start, std::min(m_max, m_value));
			start_pix = (int)(((long long)pixsize * (start - (long long)m_min)
				+ val_range - 1) / val_range);
			int end_pix = (int)(((long long)pixsize * (end - (long long)m_min)
				+ val_range - 1) / val_range);
			num_pix = end_pix - start_pix;

			if (m_orientation_swapped)
				start_pix = pixsize - num_pix - start_pix;
		}

		if  (start_pix < 0)
		{
			num_pix += start_pix;
			start_pix = 0;
		}
		
		if (num_pix < 0)
			num_pix = 0;

		if (m_orientation == orHorizontal)
			m_currently_filled = eRect(start_pix, 0, num_pix, size().height());
		else
			m_currently_filled = eRect(0, start_pix, size().width(), num_pix);

		if (!m_gradient.empty() || getCornerRadius())
		{
			/* Culorile si capatul rotunjit se schimba si in zona ramasa plina. */
			invalidate(old_currently_filled | m_currently_filled);
			return 0;
		}

			// redraw what *was* filled before and now isn't.
		invalidate(m_currently_filled - old_currently_filled);
			// redraw what wasn't filled before and is now.
		invalidate(old_currently_filled - m_currently_filled);
		
		return 0;
	}
	case evtChangedSize:
		eWidget::event(event, data, data2);
		return this->event(evtChangedSlider);
	default:
		return eWidget::event(event, data, data2);
	}
}

void eSlider::setValue(int value)
{
	m_value = value;
	event(evtChangedSlider);
}

void eSlider::setStartEnd(int start, int end)
{
	m_value = end;
	m_start = start;
	m_have_start = true;
	event(evtChangedSlider);
}

void eSlider::setOrientation(int orientation, int swapped)
{
	m_orientation = orientation;
	m_orientation_swapped = swapped;
	event(evtChangedSlider);
}

void eSlider::setRange(int min, int max)
{
	if (!m_have_start)
		m_start = min;
	m_min = min;
	m_max = max;
	event(evtChangedSlider);
}
