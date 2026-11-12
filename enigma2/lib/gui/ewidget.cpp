/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gui/ewidget.h>
#include <lib/gui/ewidgetdesktop.h>
#include <lib/gdi/desennetezit.h>

#include <algorithm>

extern void dumpRegion(const gRegion &region);

eWidget::eWidget(eWidget *parent): m_animation(this), m_parent(parent ? parent->child() : 0)
{
	m_vis = 0;
	m_layer = 0;
	m_desktop = 0;
	m_have_background_color = 0;
	m_corner_radius = 0;
	m_corner_edges = RADIUS_ALL;
	m_widget_border_width = 0;
	m_widget_alphablend = 0;
	m_widget_border_color = gRGB(0, 0, 0);
	m_gradient_vertical = 1;
	m_gradient_alphablend = 0;
	m_z_position = 0;
	m_client_offset = eSize(0, 0);
	if (m_parent)
		m_vis = wVisShow;
	if (m_parent)
	{
		insertIntoParent();
		m_parent->getStyle(m_style);
	}

	m_current_focus = 0;
	m_focus_owner = 0;
	m_notify_child_on_position_change = 1;
}

void eWidget::move(ePoint pos)
{
	pos = pos + m_client_offset;
	if (m_position == pos)
		return;

			/* ?? what about native move support? */
	invalidate();

	m_position = pos;
	event(evtChangedPosition);
	if (m_notify_child_on_position_change)
		for (ePtrList<eWidget>::iterator i(m_childs.begin()); i != m_childs.end(); ++i)
			i->event(evtParentChangedPosition);
	recalcClipRegionsWhenVisible(); /* always: the widget itself moved */
		/* try native move if supported. */
	if ((m_vis & wVisShow) && ((!m_desktop) || m_desktop->movedWidget(this)))
		invalidate();
}

void eWidget::resize(eSize size)
{
		/* same strategy as with move: we first check if
		   the size changed at all, and if it did, we
		   invalidate both the old and new area. 
		   TODO: check if either the old or new area
		   fits into the other completely, and invalidate
		   only once. */
	eSize old_size = m_size;
	eSize old_offset = m_client_offset;
	m_client_size = size;
	m_client_offset = eSize(0, 0);
	event(evtWillChangeSize, &size, &m_client_offset);
	if (old_size == m_size)
		return;
	move(position() - old_offset);
	invalidate();
	event(evtChangedSize);

	if (m_notify_child_on_position_change)
		for (ePtrList<eWidget>::iterator i(m_childs.begin()); i != m_childs.end(); ++i)
			i->event(evtParentChangedPosition); /* position/size is the same here */

	recalcClipRegionsWhenVisible();	invalidate();
}

void eWidget::invalidate(const gRegion &region)
{
		/* we determine the area to redraw, and re-position this
		   area to the absolute position, and then call the
		   desktop's invalidate() with that, which adds this
		   area into the dirty region. */
	gRegion res = m_visible_with_childs;
	if (region.valid())
		res &= region;

	if (res.empty())
		return;
	eWidget *root = this;
	ePoint abspos = position();
	int target_layer = m_layer;

	while (root && !root->m_desktop)
	{
		root = root->m_parent;
		/* widget scos de pe ecran: fereastra parinte s-a inchis, dar widgetul traieste (de ex. subtitrarea tinuta de
		   serviciu, golita cu clearPage dupa inchiderea ferestrei playerului); nu e nimic de redesenat */
		if (!root)
			return;
		if (root->m_layer != -1)
			target_layer = root->m_layer;
		abspos += root->position();
	}
	res.moveBy(abspos);
//	eDebug("region to invalidate:");
//	dumpRegion(res);
	root->m_desktop->invalidate(res, this, target_layer);
}

void eWidget::show()
{
	if (m_vis & wVisShow)
		return;

	m_vis |= wVisShow;
//	eDebug("show widget %p", this);
	notifyShowHide();

		/* TODO: optimize here to only recalc what's required. possibly merge with hide. */
	eWidget *root = this;
	ePoint abspos = position();
	int target_layer = m_layer;

	while (root && !root->m_desktop)
	{
		root = root->m_parent;
		if (!root)
		{
				/* oops: our root widget does not have a desktop associated. 
					probably somebody already erased the root, but tries some
					operations on a child window. 
									ignore them for now. */
			/* ASSERT(root); */
			return;
		}
		if (root->m_layer != -1)
			target_layer = root->m_layer;
		abspos += root->position();
	}

	root->m_desktop->recalcClipRegions(root);

	gRegion abs = m_visible_with_childs;
	abs.moveBy(abspos);
	root->m_desktop->invalidate(abs, this, target_layer);
}

void eWidget::hide()
{
		/* TODO: when hiding an upper level widget, widgets get hidden but keep the */
		/* wVisShow flag (because when the widget is shown again, the widgets must */
		/* become visible again. */
	if (!(m_vis & wVisShow))
		return;
	m_vis &= ~wVisShow;

		/* this is a workaround to the above problem. when we are in the delete phase, 
		   don't hide childs. */
	if (!(m_parent || m_desktop))
		return;
	notifyShowHide();

		/* TODO: optimize here to only recalc what's required. possibly merge with show. */
	eWidget *root = this;
	ePoint abspos = position();
	while (root && !root->m_desktop)
	{
		root = root->m_parent;
		if (!root)
			return;
		abspos += root->position();
	}
	ASSERT(root->m_desktop);

	gRegion abs = m_visible_with_childs;
	abs.moveBy(abspos);

	root->m_desktop->recalcClipRegions(root);
	root->m_desktop->invalidate(abs);
}

void eWidget::destruct()
{
	if (m_parent)
		m_parent->m_childs.remove(this);
	delete this;
}

void eWidget::setBackgroundColor(const gRGB &col)
{
	m_background_color = col;
	m_have_background_color = 1;
}

void eWidget::clearBackgroundColor()
{
	m_have_background_color = 0;
}

void eWidget::setCornerRadius(int radius)
{
	m_corner_radius = std::max(0, radius);
	invalidate();
}

void eWidget::setCornerEdges(int edges)
{
	m_corner_edges = edges & RADIUS_ALL;
	invalidate();
}

void eWidget::setBackgroundGradient(const gRGB &startcolor, const gRGB &midcolor, const gRGB &endcolor, int direction, int alphablend)
{
	m_background_gradient.clear();
	m_background_gradient.push_back(startcolor);
	/* the same middle and end colour is the two colour form ("start,end,direction") */
	if (!(midcolor == endcolor))
		m_background_gradient.push_back(midcolor);
	m_background_gradient.push_back(endcolor);
	m_gradient_vertical = direction != GRADIENT_HORIZONTAL;
	m_gradient_alphablend = alphablend != 0;
	if (direction == GRADIENT_OFF)
		m_background_gradient.clear();
	invalidate();
}

void eWidget::clearBackgroundGradient()
{
	if (m_background_gradient.empty())
		return;
	m_background_gradient.clear();
	invalidate();
}

/* The gradient fills the widget (with the corner radius) through the antialiased drawing (lib/gdi/desennetezit.h).
   Under it: nothing to clear when every colour is opaque and the corners are square (each pixel is replaced); the
   background colour of the nearest parent that has one, under rounded corners and under transparent colours with
   alphablend; fully transparent otherwise, so that a transparent colour replaces what was there, as a transparent
   backgroundColor does. Text drawn afterwards blends its edges with the middle colour. */
void eWidget::paintBackgroundGradient(gPainter &painter)
{
	const std::vector<gRGB> &g = m_background_gradient;
	bool opaque = true;
	for (std::vector<gRGB>::const_iterator i = g.begin(); i != g.end(); ++i)
		if (i->a)
			opaque = false;
	if (m_corner_radius || !opaque)
	{
		gRGB under(0, 0, 0, 255);
		if (m_corner_radius || m_gradient_alphablend)
		{
			eWidget *w = m_parent;
			while (w && (!w->m_have_background_color || w->child() != w))
				w = w->m_parent;
			if (w)
				under = w->m_background_color;
		}
		painter.setBackgroundColor(under);
		painter.clear();
	}
	gDesenNetezit forma;
	forma.forma = gDesenNetezit::dreptunghi;
	forma.x1 = size().width(); forma.y1 = size().height();
	forma.raza = m_corner_radius;
	forma.colturi = m_corner_edges;
	forma.gradient = g;
	forma.gradient_vertical = m_gradient_vertical;
	painter.desenNetezit(forma);
	gRGB middle = g[1];
	if (g.size() == 2)
		middle = gRGB((g[0].r + g[1].r + 1) / 2, (g[0].g + g[1].g + 1) / 2, (g[0].b + g[1].b + 1) / 2, (g[0].a + g[1].a + 1) / 2);
	painter.setBackgroundColor(middle);
}

void eWidget::setZPosition(int z)
{
	m_z_position = z;
	if (!m_parent)
		return;
	m_parent->m_childs.remove(this);
	insertIntoParent(); /* now at the new Z position */
}

void eWidget::setShapeFromPixmap(gPixmap *pixmap)
{
	gRegion shape;
	gSurface *s = pixmap ? pixmap->surface : 0;
	if (s && s->bpp == 32 && s->data)
	{
		int w = std::min(s->x, m_size.width()), h = std::min(s->y, m_size.height());
		for (int y = 0; y < h; ++y)
		{
			const unsigned int *row = (const unsigned int *)((const unsigned char *)s->data + y * s->stride);
			int x = 0;
			while (x < w)
			{
				while (x < w && (row[x] >> 24) < 128)
					++x;
				int start = x;
				while (x < w && (row[x] >> 24) >= 128)
					++x;
				if (x > start)
					shape |= gRegion(eRect(start, y, x - start, 1));
			}
		}
	}
	if (shape.empty())
		shape = gRegion(eRect(ePoint(0, 0), m_size));
	invalidate();
	m_clip_region = shape;
	recalcClipRegionsWhenVisible();
}

void eWidget::setTransparent(int transp)
{
	if (isTransparent() != transp)
	{
		if (transp)
			m_vis |= wVisTransparent;
		else
			m_vis &=~wVisTransparent;
		recalcClipRegionsWhenVisible();
	}
}

ePoint eWidget::getAbsolutePosition()
{
	eWidget *root = this;
	ePoint abspos = position();

	while (root && !root->m_desktop)
	{
		root = root->m_parent;
		ASSERT(root);
		abspos += root->position();
	}

	return abspos;
}

void eWidget::mayKillFocus()
{
	setFocus(0);
		/* when we have the focus, remove it first. */
	if (m_focus_owner)
		m_focus_owner->setFocus(0);
}

eWidget::~eWidget()
{
	hide();
	if (m_parent)
		m_parent->m_childs.remove(this);

	m_parent = 0;

		/* tell all childs that the parent is not anymore existing */
	ePtrList<eWidget>::iterator i(m_childs.begin());
	while (i != m_childs.end())
	{
		(*i)->parentRemoved();
		i = m_childs.erase(i);
	}
}

void eWidget::insertIntoParent()
{
	ePtrList<eWidget>::iterator i = m_parent->m_childs.begin();
	for(;;)
	{
		if ((i == m_parent->m_childs.end()) || (i->m_z_position > m_z_position))
		{
			m_parent->m_childs.insert(i, this);
			return;
		}
		++i;
	}
}

void eWidget::doPaint(gPainter &painter, const gRegion &r, int layer)
{
	if (m_visible_with_childs.empty())
		return;
	gRegion region = r, childs = r;
			/* we were in parent's space, now we are in local space */
	region.moveBy(-position());
	painter.moveOffset(position());
		/* check if there's anything for us to paint */
	if (layer == m_layer)
	{
		region &= m_visible_region;
		if (!region.empty())
		{
			painter.resetClip(region);
			event(evtPaint, &region, &painter);
			if (m_widget_border_width > 0)
				paintWidgetBorder(painter);
		}
	}

	childs.moveBy(-position());
		/* walk all childs */
	for (ePtrList<eWidget>::iterator i(m_childs.begin()); i != m_childs.end(); ++i)
		i->doPaint(painter, childs, layer);
	painter.moveOffset(-position());
}

void eWidget::setWidgetBorderWidth(int width)
{
	width = width > 0 ? width : 0;
	if (m_widget_border_width != width)
	{
		m_widget_border_width = width;
		invalidate();
	}
}

void eWidget::setWidgetBorderColor(const gRGB &color)
{
	m_widget_border_color = color;
	if (m_widget_border_width > 0)
		invalidate();
}

void eWidget::setWidgetAlphaBlend(int blend)
{
	blend = blend ? 1 : 0;
	if (m_widget_alphablend != blend)
	{
		m_widget_alphablend = blend;
		invalidate();
	}
}

void eWidget::paintWidgetBorder(gPainter &painter)
{
	/* only the band at the edges is drawn (the inside stays as the widget painted it); with rounded corners the
	   outside edge follows them, as the background does */
	int w = m_size.width(), h = m_size.height(), b = m_widget_border_width;
	if (w <= 0 || h <= 0)
		return;
	if (b * 2 >= w || b * 2 >= h)
		b = std::min(w, h) / 2;
	painter.setForegroundColor(m_widget_border_color);
	if (m_corner_radius <= 0)
	{
		painter.fill(eRect(0, 0, w, b));
		painter.fill(eRect(0, h - b, w, b));
		painter.fill(eRect(0, b, b, h - 2 * b));
		painter.fill(eRect(w - b, b, b, h - 2 * b));
		return;
	}
	gRegion band = gRegion(eRect(0, 0, w, h)) - gRegion(eRect(b, b, w - 2 * b, h - 2 * b));
	painter.clip(band);
	gDesenNetezit forma;
	forma.forma = gDesenNetezit::dreptunghi;
	forma.x0 = 0; forma.y0 = 0; forma.x1 = w; forma.y1 = h;
	forma.raza = m_corner_radius;
	forma.colturi = m_corner_edges;
	forma.culoare_pictor = 1;
	painter.desenNetezit(forma);
	painter.clippop();
}

void eWidget::recalcClipRegionsWhenVisible()
{
	eWidget *t = this;
	do
	{
		if (!(t->m_vis & wVisShow))
			break;
		if (t->m_desktop)
		{
			t->m_desktop->recalcClipRegions(t);
			break;
		}
		t = t->m_parent;
		ASSERT(t);
	} while(1);
}

void eWidget::parentRemoved()
{
	m_parent = 0;
}

int eWidget::event(int event, void *data, void *data2)
{
	switch (event)
	{
	case evtPaint:
	{
		gPainter &painter = *(gPainter*)data2;
	//		eDebug("eWidget::evtPaint");
//		dumpRegion(*(gRegion*)data);
		if (!isTransparent())
		{
			if (!m_background_gradient.empty())
				paintBackgroundGradient(painter);
			else if (!m_have_background_color)
			{
				ePtr<eWindowStyle> style;
				if (!getStyle(style))
					style->paintBackground(painter, ePoint(0, 0), size());
			} else
			{
				painter.setBackgroundColor(m_background_color);
				if (!m_corner_radius && !(m_widget_alphablend && m_background_color.a))
					painter.clear();
				else
				{
					/* Refacem fundalul de sub colturi inainte de amestec. */
					eWidget *w = m_parent;
					while (w && (!w->m_have_background_color || w->child() != w))
						w = w->m_parent;
					painter.setBackgroundColor(w ? w->m_background_color : gRGB(0, 0, 0, 255));
					painter.clear();
					gDesenNetezit forma;
					forma.forma = gDesenNetezit::dreptunghi;
					forma.x1 = size().width(); forma.y1 = size().height();
					forma.raza = m_corner_radius;
					forma.colturi = m_corner_edges;
					forma.culoare = m_background_color;
					painter.desenNetezit(forma);
					painter.setBackgroundColor(m_background_color);
				}
			}
		} else
		{
			eWidget *w = this;
			while (w && !w->m_have_background_color)
				w = w->m_parent;

			if (w)
				painter.setBackgroundColor(w->m_background_color);
		}
		break;
	}
	case evtKey:
		break;
	case evtWillChangeSize:
		m_size = *static_cast<eSize*>(data);
		break;
	case evtChangedSize:
		m_clip_region = gRegion(eRect(ePoint(0, 0),  m_size));
		break;
	case evtParentChangedPosition:
		for (ePtrList<eWidget>::iterator i(m_childs.begin()); i != m_childs.end(); ++i)
			i->event(evtParentChangedPosition);
		break;
	case evtFocusGot:
		m_focus_owner = (eWidget*)data;
		break;
	case evtFocusLost:
		m_focus_owner = 0;
		break;
	default:
		return -1;
	}
	return 0;
}

void eWidget::setFocus(eWidget *focus)
{
	if (m_current_focus)
		m_current_focus->event(evtFocusLost, this);
	m_current_focus = focus;

	if (m_current_focus)
		m_current_focus->event(evtFocusGot, this);
}

void eWidget::notifyShowHide()
{
	event(evtParentVisibilityChanged);
	for (ePtrList<eWidget>::iterator i(m_childs.begin()); i != m_childs.end(); ++i)
		i->notifyShowHide();
}
