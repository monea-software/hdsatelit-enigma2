/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gui/elistbox.h>
#include <lib/gui/elistboxcontent.h>
#include <lib/gui/eslider.h>
#include <lib/actions/action.h>
#include <lib/gui/ewindowstyle.h>
#include <lib/gdi/desennetezit.h>
#include <algorithm>

eListbox::eListbox(eWidget *parent) :
	eWidget(parent), m_scrollbar_mode(showNever), m_prev_scrollbar_page(-1),
	m_scrollbar_slider_border_width(1),
	m_scrollbar_width(0),
	m_have_scrollbar_foreground(false), m_have_scrollbar_background(false), m_have_scrollbar_border(false),
	m_scrollbar_radius(0), m_scrollbar_offset(-1), m_native_keys(true),
	m_content_changed(false), m_content_width(-1), m_enabled_wrap_around(false), m_top(0), m_selected(0), m_itemheight(25),
	m_items_per_page(0), m_orientation(orVertical), m_itemwidth(0), m_item_alignment(itemAlignLeftTop), m_spacing(0, 0),
	m_cols(1), m_rows(0), m_pitch_x(0), m_pitch_y(0), m_origin_x(0), m_origin_y(0), m_item_w(0), m_have_spacing_color(false), m_separator_size(0), m_scroll_margin(0), m_redraw_on_selection(true), m_selection_enabled(1), m_scrollbar(NULL), m_style(),
	m_derulare(this)
{
//	setContent(new eListboxStringContent());

	ePtr<eActionMap> ptr;
	eActionMap::getInstance(ptr);
	ptr->bindAction("ListboxActions", 0, 0, this);
	/* HDSatelit: dupa hartile Python (vezi ListboxFallbackActions in elistbox.h) */
	ptr->bindAction("ListboxFallbackActions", 1, 1, this);
}

eListbox::~eListbox()
{
	if (m_content && m_content->m_listbox == this)
		m_content->setListbox(0);
	if (m_scrollbar)
		delete m_scrollbar;
	
	ePtr<eActionMap> ptr;
	eActionMap::getInstance(ptr);
	ptr->unbindAction(this, 0);
	ptr->unbindAction(this, 1);
}

void eListbox::setScrollbarMode(int mode)
{
	m_scrollbar_mode = mode;
	if (m_scrollbar)
	{
		if (m_scrollbar_mode == showNever)
		{
			delete m_scrollbar;
			m_scrollbar=0;
		}
	}
	else
	{
		m_scrollbar = new eSlider(this);
		m_scrollbar->setIsScrollbar(true);
		m_scrollbar->hide();
		m_scrollbar->setBorderWidth(m_scrollbar_slider_border_width);
		m_scrollbar->setOrientation(eSlider::orVertical);
		m_scrollbar->setRange(0,100);
		applyScrollbarStyle();
	}
		/* HDSatelit: the skin may set the scroll bar mode after the size and the row height (attribute order); the
		   bar is then decided now, when the list opens, and not only at the first move of the selection */
	m_content_changed = true;
	if (m_items_per_page)
		updateScrollBar();
}

void eListbox::setScrollbarSliderBorderWidth(int width)
{
	// La noi, cadrul barei este desenat deja de eSlider.
	m_scrollbar_slider_border_width = width > 0 ? width : 0;
	if (m_scrollbar)
		m_scrollbar->setBorderWidth(m_scrollbar_slider_border_width);
}

void eListbox::setScrollbarWidth(int width)
{
	/* darog69 (forumul nostru 1028, 11.11.2026): scrollbarWidth="8" din tema era primit si ignorat, bara ramanea de
	   18-22 de puncte */
	m_scrollbar_width = width > 0 ? width : 0;
	m_content_changed = true;
	updateScrollBar();
}

void eListbox::applyScrollbarStyle()
{
	/* the colours, the corners and the border of the bar, given to the eSlider whenever it exists (the skin may
	   set them before or after scrollbarMode) */
	if (!m_scrollbar)
		return;
	if (m_have_scrollbar_foreground)
		m_scrollbar->setForegroundColor(m_scrollbar_foreground);
	if (m_have_scrollbar_background)
		m_scrollbar->setBackgroundColor(m_scrollbar_background);
	if (m_have_scrollbar_border)
		m_scrollbar->setBorderColor(m_scrollbar_border);
	if (m_scrollbar_radius > 0)
		m_scrollbar->setCornerRadius(m_scrollbar_radius);
	if (m_scrollbar_pixmap)
		m_scrollbar->setPixmap(m_scrollbar_pixmap);
	if (m_scrollbar_background_pixmap)
		m_scrollbar->setBackgroundPixmap(m_scrollbar_background_pixmap);
}

void eListbox::setScrollbarBackgroundPixmap(ePtr<gPixmap> &pixmap)
{
	m_scrollbar_background_pixmap = pixmap;
	applyScrollbarStyle();
}

void eListbox::allowNativeKeys(bool allow)
{
	if (m_native_keys == allow)
		return;
	m_native_keys = allow;
	ePtr<eActionMap> ptr;
	eActionMap::getInstance(ptr);
	if (allow)
	{
		/* the same two bindings as in the constructor */
		ptr->bindAction("ListboxActions", 0, 0, this);
		ptr->bindAction("ListboxFallbackActions", 1, 1, this);
	}
	else
	{
		ptr->unbindAction(this, 0);
		ptr->unbindAction(this, 1);
	}
}

int eListbox::getPageCount()
{
	if (!m_content || m_items_per_page <= 0)
		return 0;
	int entries = m_content->size();
	return (entries + m_items_per_page - 1) / m_items_per_page;
}

void eListbox::setScrollbarForegroundPixmap(ePtr<gPixmap> &pixmap)
{
	m_scrollbar_pixmap = pixmap;
	applyScrollbarStyle();
}

void eListbox::setScrollbarForegroundColor(gRGB &col)
{
	m_scrollbar_foreground = col;
	m_have_scrollbar_foreground = true;
	applyScrollbarStyle();
}

void eListbox::setScrollbarBackgroundColor(gRGB &col)
{
	m_scrollbar_background = col;
	m_have_scrollbar_background = true;
	applyScrollbarStyle();
}

void eListbox::setScrollbarBorderColor(gRGB &col)
{
	m_scrollbar_border = col;
	m_have_scrollbar_border = true;
	applyScrollbarStyle();
}

void eListbox::setScrollbarRadius(int radius)
{
	m_scrollbar_radius = radius > 0 ? radius : 0;
	applyScrollbarStyle();
}

void eListbox::setScrollbarOffset(int offset)
{
	/* the gap between the rows and the bar: skins for other images count the bar as width + offset */
	m_scrollbar_offset = offset > 0 ? offset : 0;
	m_content_changed = true;
	updateScrollBar();
}

static void itemGradient(std::vector<gRGB> &gradient, int &vertical, const gRGB &start, const gRGB &middle, const gRGB &end, int direction)
{
	/* as eWidget::setBackgroundGradient: middle == end means two colours */
	gradient.clear();
	gradient.push_back(start);
	if (!(middle == end))
		gradient.push_back(middle);
	gradient.push_back(end);
	vertical = direction != 2;
}

void eListbox::setItemCornerRadius(int radius, int edges)
{
	m_style.m_item_radius[0] = radius > 0 ? radius : 0;
	m_style.m_item_edges[0] = edges;
	invalidate();
}

void eListbox::setItemCornerRadiusSelected(int radius, int edges)
{
	m_style.m_item_radius[1] = radius > 0 ? radius : 0;
	m_style.m_item_edges[1] = edges;
	invalidate();
}

void eListbox::setItemGradient(const gRGB &start, const gRGB &middle, const gRGB &end, int direction, int alphablend)
{
	itemGradient(m_style.m_item_gradient[0], m_style.m_item_gradient_vertical[0], start, middle, end, direction);
	invalidate();
}

void eListbox::setItemGradientSelected(const gRGB &start, const gRGB &middle, const gRGB &end, int direction, int alphablend)
{
	itemGradient(m_style.m_item_gradient[1], m_style.m_item_gradient_vertical[1], start, middle, end, direction);
	invalidate();
}

bool eListbox::paintItemBackground(gPainter &painter, eWindowStyle &style, const eRect &rect, int selected)
{
	int i = selected ? 1 : 0;
	const eListboxStyle &s = m_style;
	if (!s.m_item_radius[i] && s.m_item_gradient[i].empty())
		return false;
	if (selected ? (bool)s.m_selection : (bool)s.m_background)
		return false;
	/* under the rounded corners: the background of the other rows (nothing on a transparent list) */
	style.setStyle(painter, eWindowStyle::styleListboxNormal);
	if (s.m_background_color_set)
		painter.setBackgroundColor(s.m_background_color);
	if (!s.m_transparent_background)
		painter.clear();
	/* the row: its gradient, or its background colour with rounded corners */
	style.setStyle(painter, selected ? eWindowStyle::styleListboxSelected : eWindowStyle::styleListboxNormal);
	if (selected && s.m_background_color_selected_set)
		painter.setBackgroundColor(s.m_background_color_selected);
	else if (!selected && s.m_background_color_set)
		painter.setBackgroundColor(s.m_background_color);
	if (s.m_item_gradient[i].empty() && !selected && s.m_transparent_background)
	{
		/* a transparent list without its own row colour: nothing to draw under the text */
	}
	else
	{
		gDesenNetezit forma;
		forma.forma = gDesenNetezit::dreptunghi;
		forma.x0 = rect.left(); forma.y0 = rect.top(); forma.x1 = rect.right(); forma.y1 = rect.bottom();
		forma.raza = s.m_item_radius[i];
		forma.colturi = s.m_item_edges[i] ? s.m_item_edges[i] : 15;
		if (!s.m_item_gradient[i].empty())
		{
			forma.gradient = s.m_item_gradient[i];
			forma.gradient_vertical = s.m_item_gradient_vertical[i];
		}
		else
			forma.culoare_pictor = 2;	/* the background colour of the painter */
		painter.desenNetezit(forma);
	}
	/* the colours of the text, as the list contents set them before their clear */
	if (selected)
	{
		if (s.m_foreground_color_selected_set)
			painter.setForegroundColor(s.m_foreground_color_selected);
	}
	else if (s.m_foreground_color_set)
		painter.setForegroundColor(s.m_foreground_color);
	if (!s.m_item_gradient[i].empty())
		painter.setBackgroundColor(s.m_item_gradient[i][s.m_item_gradient[i].size() / 2]);
	return true;
}

void eListbox::setOrientation(int orientation)
{
	if (orientation != orHorizontal && orientation != orGrid)
		orientation = orVertical;
	if (m_orientation == orientation)
		return;
	m_orientation = orientation;
	recalcSize();
	invalidate();
}

void eListbox::setItemWidth(int w)
{
	w = w > 0 ? w : 0;
	if (m_itemwidth == w)
		return;
	m_itemwidth = w;
	if (flexLayout())
	{
		recalcSize();
		invalidate();
	}
}

void eListbox::setItemSpacing(const ePoint &spacing)
{
	ePoint s(spacing.x() > 0 ? spacing.x() : 0, spacing.y() > 0 ? spacing.y() : 0);
	if (s == m_spacing)
		return;
	m_spacing = s;
	recalcSize();
	invalidate();
}

void eListbox::setItemAlignment(int alignment)
{
	m_item_alignment = alignment & 15;
	if (flexLayout())
	{
		recalcSize();
		invalidate();
	}
}

void eListbox::setSpacingColor(const gRGB &col)
{
	m_spacing_color = col;
	m_have_spacing_color = true;
	if (flexLayout())
		invalidate();
}

void eListbox::setSeparatorColor(const gRGB &col)
{
	m_separator_color = col;
	if (!m_separator_size)
		m_separator_size = 1;
	invalidate();
}

void eListbox::setSeparatorSize(int size)
{
	m_separator_size = size > 0 ? size : 0;
	invalidate();
}

void eListbox::paintSeparator(gPainter &painter, const eRect &item)
{
	int h = m_separator_size < item.height() ? m_separator_size : item.height();
	painter.setForegroundColor(m_separator_color);
	painter.fill(eRect(item.left(), item.bottom() - h, item.width(), h));
}

void eListbox::recalcFlex()
{
	/* items of itemWidth x itemHeight with the gaps between them; how many fit, and where the block starts */
	int w = size().width(), h = size().height();
	int iw = (m_orientation != orVertical && m_itemwidth > 0) ? m_itemwidth : w;
	int ih = m_itemheight;
	int sx = m_spacing.x(), sy = m_spacing.y();
	if (iw > w)
		iw = w;
	m_cols = (m_orientation == orVertical) ? 1 : std::max(1, (w + sx) / std::max(1, iw + sx));
	m_rows = (m_orientation == orHorizontal) ? 1 : (h + sy) / std::max(1, ih + sy);
	m_items_per_page = m_cols * m_rows;
	m_item_w = iw;
	m_pitch_x = iw + sx;
	m_pitch_y = ih + sy;
	int ha = m_item_alignment & 3, va = (m_item_alignment >> 2) & 3;
	if (m_item_alignment >= itemAlignJustifyLeft)
	{
		/* JustifyLeft/Center/Right: the columns spread over the width, the rows as top/middle/bottom... read as top */
		ha = 3;
		va = 0;
	}
	int freex = w - (m_cols * iw + (m_cols - 1) * sx), freey = h - (m_rows * ih + (m_rows - 1) * sy);
	m_origin_x = m_origin_y = 0;
	if (freex > 0)
	{
		if (ha == 1)
			m_origin_x = freex / 2;
		else if (ha == 2)
			m_origin_x = freex;
		else if (ha == 3 && m_cols > 1)
			m_pitch_x = iw + sx + freex / (m_cols - 1);
	}
	if (freey > 0 && m_rows > 0)
	{
		if (va == 1)
			m_origin_y = freey / 2;
		else if (va == 2)
			m_origin_y = freey;
		else if (va == 3 && m_rows > 1)
			m_pitch_y = ih + sy + freey / (m_rows - 1);
	}
	if (m_content)
		m_content->setSize(eSize(iw, ih));
}

eRect eListbox::itemRect(int k) const
{
	if (!flexLayout())
		return eRect(0, m_itemheight * k, size().width(), m_itemheight);
	int cols = m_cols > 0 ? m_cols : 1;
	return eRect(m_origin_x + (k % cols) * m_pitch_x, m_origin_y + (k / cols) * m_pitch_y, m_item_w, m_itemheight);
}

void eListbox::setWrapAround(bool state)
{
	m_enabled_wrap_around = state;
}

void eListbox::setScrollMargin(int rows)
{
	m_scroll_margin = rows > 0 ? rows : 0;
	if (m_content && m_items_per_page)
		moveSelection(justCheck);
}

void eListbox::setRedrawOnSelection(bool redraw)
{
	m_redraw_on_selection = redraw;
}

void eListbox::entryPartChanged(int index, int x, int width)
{
	if ((m_top <= index) && (index < (m_top + m_items_per_page)))
	{
		eRect r = itemRect(index - m_top);
		gRegion inv = eRect(r.left() + x, r.top(), width, m_itemheight);
		invalidate(inv);
	}
}

void eListbox::setContent(iListboxContent *content)
{
	// Continutul Python poate fi refolosit dupa inchiderea ecranului.
	if (m_content && m_content->m_listbox == this)
		m_content->setListbox(0);
	m_content = content;
	if (content)
		m_content->setListbox(this);
	entryReset();
}

bool eListbox::atBegin()
{
	if (m_content && !m_selected)
		return true;
	return false;
}

bool eListbox::atEnd()
{
	if (m_content && m_content->size() == m_selected+1)
		return true;
	return false;
}

void eListbox::moveToEnd()
{
	if (!m_content)
		return;
	/* move to last existing one ("end" is already invalid) */
	m_content->cursorEnd(); m_content->cursorMove(-1);
	/* current selection invisible? */
	if (m_top + m_items_per_page <= m_content->cursorGet())
	{
		int rest = m_content->size() % m_items_per_page;
		if (rest)
			m_top = m_content->cursorGet() - rest + 1;
		else
			m_top = m_content->cursorGet() - m_items_per_page + 1;
		if (m_top < 0)
			m_top = 0;
	}
}

void eListbox::moveSelection(long dir)
{
		/* refuse to do anything without a valid list. */
	if (!m_content)
		return;
		/* if our list does not have one entry, don't do anything. */
	if (!m_items_per_page)
		return;
		/* we need the old top/sel to see what we have to redraw */
	int oldtop = m_top;
	int oldsel = m_selected;
		/* HDSatelit 0.7.4: left/right = one item; in a grid up/down = one row (m_cols items) */
	int step = 1;
	if (dir == moveLeft)
		dir = moveUp;
	else if (dir == moveRight)
		dir = moveDown;
	else if ((dir == moveUp || dir == moveDown) && m_orientation == orGrid && m_cols > 1)
		step = m_cols;
		/* first, move cursor */
	switch (dir)
	{
	case moveUp:
	{
		if (step > 1)
		{
			if (m_content->cursorGet() >= step)
				m_content->cursorMove(-step);
			else if (m_enabled_wrap_around)
				moveToEnd();
			break;
		}
		m_content->cursorMove(-1);
		if (m_enabled_wrap_around && oldsel == m_content->cursorGet())  // must wrap around ?
			moveToEnd();
		break;
	}
	case moveDown:
		if (step > 1)
		{
			int cur = m_content->cursorGet(), n = m_content->size();
			if (cur + step < n)
				m_content->cursorMove(step);
			else if (m_enabled_wrap_around)
			{
				m_top = 0;
				m_content->cursorHome();
			}
			else if (cur / step < (n - 1) / step)
				moveToEnd();	/* a shorter last row below: its last item */
			break;
		}
		m_content->cursorMove(1);
			/* ok - we could have reached the end. So we do wrap around. */
		if (!m_content->cursorValid())
		{
			if (m_enabled_wrap_around)
			{
				m_top = 0;
				m_content->cursorHome();
			}
			else
				m_content->cursorMove(-1);
		}
		break;
	case pageUp:
		if (m_content->cursorGet() >= m_items_per_page)
		{
			m_content->cursorMove(-m_items_per_page);
			m_top -= m_items_per_page;
			if (m_top < 0)
				m_top = 0;
		} else
		{
			m_top = 0;
			m_content->cursorHome();
		}
		break;
	case moveTop:
		m_content->cursorHome();
		m_top = 0; /* align with top, speeds up process */
		break;
	case pageDown:
		m_content->cursorMove(m_items_per_page);
		if (m_content->cursorValid())
			break;
				/* fall through */
	case moveEnd:
		moveToEnd();
		break;
	case justCheck:
		break;
	}
	
	if (m_content->cursorValid() && !m_content->currentCursorSelectable())
	{
			/* ok, our cursor position is valid (i.e. in list), but not selectable. */
			
			/* when moving up, continue until we found a valid position. */
		if ((dir == moveUp) || (dir == pageDown))
		{
			while (m_content->cursorGet())
			{
				m_content->cursorMove(-1);
				if (m_content->currentCursorSelectable())
				{
					break;
				}
			}
		} else
		{
				/* else move down */
			while (m_content->cursorValid())
			{
				m_content->cursorMove(+1);
				if (m_content->currentCursorSelectable())
				{
					break;
				}
			}
			
			if (!m_content->cursorValid())
				m_content->cursorMove(-1);
		}
		
		if (!m_content->currentCursorSelectable())
			m_content->cursorSet(oldsel);
	}
	
		/* note that we could be on an invalid cursor position, but we don't
		   care. this only happens on empty lists, and should have almost no
		   side effects. */
	
		/* now, look wether the current selection is out of screen */
	m_selected = m_content->cursorGet();
	if (m_scroll_margin > 0 && m_items_per_page > 2 * m_scroll_margin && !flexLayout())
	{
			/* HDSatelit: row by row (setScrollMargin): the selection stays at least m_scroll_margin rows from the
			   bottom and the top edge while there are more rows beyond them; the last page is aligned at the bottom */
		int jos = m_items_per_page - 1 - m_scroll_margin;
		if (m_selected - m_top > jos)
			m_top = m_selected - jos;
		if (m_selected - m_top < m_scroll_margin)
			m_top = m_selected - m_scroll_margin;
		int ultimul_top = m_content->size() - m_items_per_page;
		if (m_top > ultimul_top)
			m_top = ultimul_top;
		if (m_top < 0)
			m_top = 0;
	}
	else
	{
		while (m_selected < m_top)
		{
			m_top -= m_items_per_page;
			if (m_top < 0)
				m_top = 0;
		}
		while (m_selected >= m_top + m_items_per_page)
			/* m_top should be always valid here as it's selected */
			m_top += m_items_per_page;
	}

	if (oldsel != m_selected)
	{
			/* HDSatelit: the newly selected row starts its texts from the beginning */
		m_derulare.reset();
		/* emit */ selectionChanged();
	}

	updateScrollBar();

	if (m_top != oldtop)
		invalidate();
	else if (m_selected != oldsel && m_redraw_on_selection)
	{
   /* redraw the old and newly selected */
		gRegion inv = itemRect(m_selected - m_top);
		inv |= itemRect(oldsel - m_top);
		invalidate(inv);
	}
}

void eListbox::moveSelectionTo(int index)
{
	if (m_content)
	{
		m_content->cursorHome();
		m_content->cursorMove(index);
		moveSelection(justCheck);
	}
}

int eListbox::getCurrentIndex()
{
	if (m_content && m_content->cursorValid())
		return m_content->cursorGet();
	return 0;
}

void eListbox::updateScrollBar()
{
	if (!m_content || m_scrollbar_mode == showNever )
		return;
	int entries = m_content->size();
	if (m_content_changed && flexLayout() && m_orientation != orVertical)
	{
		/* HDSatelit 0.7.4: the items keep their width (recalcFlex); a grid has the bar on the right over its
		   free edge, a horizontal list none */
		m_content_changed = false;
		if (m_scrollbar)
		{
			if (m_orientation == orGrid && (entries > m_items_per_page || m_scrollbar_mode == showAlways))
			{
				int sbarwidth = m_scrollbar_width > 0 ? m_scrollbar_width : 10;
				m_scrollbar->move(ePoint(size().width() - sbarwidth, 0));
				m_scrollbar->resize(eSize(sbarwidth, size().height()));
				m_scrollbar->show();
			}
			else
				m_scrollbar->hide();
		}
		if (m_orientation != orGrid)
			return;
	}
	if (m_content_changed)
	{
		int width = size().width();
		int height = size().height();
		m_content_changed = false;
		int content_width = width;
		if (entries > m_items_per_page || m_scrollbar_mode == showAlways)
		{
			int sbarwidth=width/16;
			if (sbarwidth < 18)
				sbarwidth = 18;
			if (sbarwidth > 22)
				sbarwidth = 22;
			if (m_scrollbar_width > 0)
				sbarwidth = m_scrollbar_width < width / 2 ? m_scrollbar_width : width / 2;
			m_scrollbar->move(ePoint(width-sbarwidth, 0));
			m_scrollbar->resize(eSize(sbarwidth, height));
			content_width = width - sbarwidth - scrollbarGap();
			m_content->setSize(eSize(content_width, m_itemheight));
			m_scrollbar->show();
		}
		else
		{
			m_content->setSize(eSize(width, m_itemheight));
			m_scrollbar->hide();
		}
			/* HDSatelit: the rows got another width (the bar came or went): all of them are drawn again, otherwise
			   the rows not repainted by the move keep their old width and their values end under the bar */
		if (content_width != m_content_width)
		{
			if (m_content_width >= 0)
			{
				m_derulare.reset();
				invalidate();
			}
			m_content_width = content_width;
		}
	}
	if (m_items_per_page && entries)
	{
			/* HDSatelit: row by row (setScrollMargin) the bar follows the first visible row, not the page */
		int curVisiblePage = m_scroll_margin > 0 ? m_top : m_top / m_items_per_page;
		if (m_prev_scrollbar_page != curVisiblePage)
		{
			m_prev_scrollbar_page = curVisiblePage;
			int start, vis;
			if (m_scroll_margin > 0)
			{
				start = (m_top * 100) / entries;
				vis = (m_items_per_page * 100 + entries - 1) / entries;
				if (vis > 100)
					vis = 100;
			}
			else
			{
				int pages = entries / m_items_per_page;
				if ((pages*m_items_per_page) < entries)
					++pages;
				start=(m_top*100)/(pages*m_items_per_page);
				vis=(m_items_per_page*100+pages*m_items_per_page-1)/(pages*m_items_per_page);
			}
			if (vis < 3)
				vis=3;
			m_scrollbar->setStartEnd(start,start+vis);
		}
	}
}

int eListbox::getEntryTop()
{
	if (flexLayout())
		return itemRect(m_selected - m_top).top();
	return (m_selected - m_top) * m_itemheight;
}

int eListbox::event(int event, void *data, void *data2)
{
	switch (event)
	{
	case evtPaint:
	{
		ePtr<eWindowStyle> style;
		
		if (!m_content)
			return eWidget::event(event, data, data2);
		ASSERT(m_content);
		
		getStyle(style);
		
		if (!m_content)
			return 0;
		
		gPainter &painter = *(gPainter*)data2;
		
		m_content->cursorSave();
		m_content->cursorMove(m_top - m_selected);
		
		gRegion entryrect = eRect(0, 0, size().width(), m_itemheight);
		const gRegion &paint_region = *(gRegion*)data;
			/* HDSatelit: the scroll goes as far as the widest text of the selected row, when that row is drawn */
		bool selected_painted = false;
		m_derulare.beginPaint();

		if (flexLayout())
		{
			/* HDSatelit 0.7.4: horizontal/grid lists and gaps between items: the list background under the gaps and
			   the empty places, then every visible item in its own place */
			if (!m_style.m_transparent_background || m_have_spacing_color)
			{
				style->setStyle(painter, eWindowStyle::styleListboxNormal);
				if (m_have_spacing_color)
					painter.setBackgroundColor(m_spacing_color);
				else if (m_style.m_background_color_set)
					painter.setBackgroundColor(m_style.m_background_color);
				painter.clear();
			}
			for (int i = 0; i < m_items_per_page && m_content->cursorValid(); ++i)
			{
				eRect r = itemRect(i);
				if (!(paint_region & gRegion(r)).empty())
				{
					int selected = m_selected == m_content->cursorGet() && m_content->size() && m_selection_enabled;
					if (selected)
						selected_painted = true;
					m_content->paint(painter, *style, r.topLeft(), selected);
					if (m_separator_size && m_content->cursorGet() + 1 < m_content->size())
						paintSeparator(painter, r);
				}
				m_content->cursorMove(+1);
			}
			m_content->cursorRestore();
			m_derulare.endPaint(selected_painted);
			return 0;
		}

		for (int y = 0, i = 0; i <= m_items_per_page; y += m_itemheight, ++i)
		{
			gRegion entry_clip_rect = paint_region & entryrect;

			if (!entry_clip_rect.empty())
			{
				int selected = m_selected == m_content->cursorGet() && m_content->size() && m_selection_enabled;
				if (selected)
					selected_painted = true;
				m_content->paint(painter, *style, ePoint(0, y), selected);
				if (m_separator_size && m_content->cursorGet() + 1 < m_content->size())
					paintSeparator(painter, eRect(0, y, m_content_width > 0 ? m_content_width : size().width(), m_itemheight));
			}

				/* (we could clip with entry_clip_rect, but 
				   this shouldn't change the behavior of any
				   well behaving content, so it would just
				   degrade performance without any gain.) */

			m_content->cursorMove(+1);
			entryrect.moveBy(ePoint(0, m_itemheight));
		}

		// clear/repaint empty/unused space between scrollbar and listboxentrys
		if (m_scrollbar && m_scrollbar->isVisible())
		{
			style->setStyle(painter, eWindowStyle::styleListboxNormal);
			int gap = scrollbarGap();
			if (gap > 0)
			{
				painter.clip(eRect(m_scrollbar->position() - ePoint(gap,0), eSize(gap,m_scrollbar->size().height())));
				painter.clear();
				painter.clippop();
			}
		}

		m_content->cursorRestore();
		m_derulare.endPaint(selected_painted);

		return 0;
	}

	case evtChangedSize:
		m_derulare.reset();
		recalcSize();
		return eWidget::event(event, data, data2);
		
	case evtAction:
		if (isVisible())
		{
			long how = (long)data2;
			if ((long)data == 1) /* ListboxFallbackActions */
				how = (how == fallbackPageUp) ? pageUp : pageDown;
			else if (m_orientation != orVertical)
			{
				/* HDSatelit 0.7.4: LEFT/RIGHT (pageUp/pageDown in the key map) move by one item; in a horizontal
				   list UP/DOWN go a page, in a grid a row */
				if (how == pageUp)
					how = moveLeft;
				else if (how == pageDown)
					how = moveRight;
				else if (m_orientation == orHorizontal && how == moveUp)
					how = pageUp;
				else if (m_orientation == orHorizontal && how == moveDown)
					how = pageDown;
			}
			moveSelection(how);
			return 1;
		}
		return 0;
	default:
		return eWidget::event(event, data, data2);
	}
}

void eListbox::recalcSize()
{
	m_content_changed=true;
	m_prev_scrollbar_page=-1;
	if (flexLayout())
	{
		recalcFlex();
		moveSelection(justCheck);
		return;
	}
	if (m_content)
		m_content->setSize(eSize(size().width(), m_itemheight));
	m_items_per_page = size().height() / m_itemheight;

	if (m_items_per_page < 0) /* TODO: whyever - our size could be invalid, or itemheigh could be wrongly specified. */
 		m_items_per_page = 0;

	moveSelection(justCheck);
}

void eListbox::setItemHeight(int h)
{
	if (h)
		m_itemheight = h;
	else
		m_itemheight = 20;
	recalcSize();
}

void eListbox::setSelectionEnable(int en)
{
	if (m_selection_enabled == en)
		return;
	m_selection_enabled = en;
	entryChanged(m_selected); /* redraw current entry */
}

void eListbox::entryAdded(int index)
{
	if (m_content && (m_content->size() % m_items_per_page) == 1)
		m_content_changed=true;
	/* manage our local pointers. when the entry was added before the current position, we have to advance. */
		
		/* we need to check <= - when the new entry has the (old) index of the cursor, the cursor was just moved down. */
	if (index <= m_selected)
		++m_selected;
	if (index <= m_top)
		++m_top;
		
		/* we have to check wether our current cursor is gone out of the screen. */
		/* moveSelection will check for this case */
	moveSelection(justCheck);
	
		/* now, check if the new index is visible. */
	if ((m_top <= index) && (index < (m_top + m_items_per_page)))
	{
			/* todo, calc exact invalidation... */
		invalidate();
	}
}

void eListbox::entryRemoved(int index)
{
	if (m_content && !(m_content->size() % m_items_per_page))
		m_content_changed=true;

	if (index == m_selected && m_content)
		m_selected = m_content->cursorGet();

	if (m_content && m_content->cursorGet() >= m_content->size())
		moveSelection(moveUp);
	else
		moveSelection(justCheck);

	if ((m_top <= index) && (index < (m_top + m_items_per_page)))
	{
			/* todo, calc exact invalidation... */
		invalidate();
	}
}

void eListbox::entryChanged(int index)
{
	if ((m_top <= index) && (index < (m_top + m_items_per_page)))
	{
		gRegion inv = itemRect(index - m_top);
		invalidate(inv);
	}
}

void eListbox::entryReset(bool selectionHome)
{
	m_derulare.reset();
	m_content_changed = true;
	m_prev_scrollbar_page = -1;
	int oldsel;

	if (selectionHome)
	{
		if (m_content)
			m_content->cursorHome();
		m_top = 0;
		m_selected = 0;
	}
	
	if (m_content && (m_selected >= m_content->size()))
	{
		if (m_content->size())
			m_selected = m_content->size() - 1;
		else
			m_selected = 0;
		m_content->cursorSet(m_selected);
	}
	
	oldsel = m_selected;
	moveSelection(justCheck);
		/* if oldsel != m_selected, selectionChanged was already 
		   emitted in moveSelection. we want it in any case, so otherwise,
		   emit it now. */
	if (oldsel == m_selected)
		/* emit */ selectionChanged();
	invalidate();
}

void eListbox::setBackgroundColor(gRGB &col)
{
	m_style.m_background_color = col;
	m_style.m_background_color_set = 1;
}

void eListbox::setBackgroundColorSelected(gRGB &col)
{
	m_style.m_background_color_selected = col;
	m_style.m_background_color_selected_set = 1;
}

void eListbox::setForegroundColor(gRGB &col)
{
	m_style.m_foreground_color = col;
	m_style.m_foreground_color_set = 1;
}

void eListbox::setForegroundColorSelected(gRGB &col)
{
	m_style.m_foreground_color_selected = col;
	m_style.m_foreground_color_selected_set = 1;
}

void eListbox::setFont(gFont *font)
{
	m_style.m_font = font;
	invalidate();
}

void eListbox::setSecondFont(gFont *font)
{
	m_style.m_secondfont = font;
	invalidate();
}

void eListbox::setHeaderFont(gFont *font)
{
	m_style.m_headerfont = font;
	invalidate();
}

void eListbox::setTextOffset(const ePoint &offset)
{
	m_style.m_text_offset = offset;
	m_style.m_text_offset_set = 1;
	invalidate();
}

void eListbox::setVAlign(int align)
{
	m_style.m_valign = align;
	invalidate();
}

void eListbox::setBackgroundPicture(ePtr<gPixmap> &pm)
{
	m_style.m_background = pm;
}

void eListbox::setSelectionPicture(ePtr<gPixmap> &pm)
{
	m_style.m_selection = pm;
}

void eListbox::invalidate(const gRegion &region)
{
	gRegion tmp(region);
	if (m_content)
		m_content->updateClip(tmp);
	eWidget::invalidate(tmp);
}

struct eListboxStyle *eListbox::getLocalStyle(void)
{
		/* transparency is set directly in the widget */
	m_style.m_transparent_background = isTransparent();
	return &m_style;
}
