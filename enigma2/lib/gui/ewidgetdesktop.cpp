/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gui/ewidgetdesktop.h>
#include <lib/gui/ewidget.h>
#include <lib/base/ebase.h>
#include <lib/gdi/grc.h>
#include <lib/gdi/hdsanimatie.h>
#include <string.h>
#include <time.h>

extern void dumpRegion(const gRegion &region);

void eWidgetDesktop::addRootWidget(eWidget *root)
{
	ASSERT(!root->m_desktop);
	
	int invert_sense = 0;
		/* buffered mode paints back-to-front, while immediate mode is front-to-back. */
	if (m_comp_mode == cmBuffered)
		invert_sense = 1;
	
	ePtrList<eWidget>::iterator insert_position = m_root.begin();
	
	for (;;)
	{
		if ((insert_position == m_root.end()) || (invert_sense ^ (insert_position->m_z_position < root->m_z_position)))
		{
			m_root.insert(insert_position, root);
			break;
		}
		++insert_position;
	}
	
	root->m_desktop = this;

		/* the creation will be postponed. */
	for (int i = 0; i < MAX_LAYER; ++i)
		root->m_comp_buffer[i] = 0;
}

void eWidgetDesktop::removeRootWidget(eWidget *root)
{
	if (m_comp_mode == cmBuffered)
	{
		for (int i = 0; i < MAX_LAYER; ++i)
			removeBufferForWidget(root, i);
	}

	m_root.remove(root);
}

int eWidgetDesktop::movedWidget(eWidget *root)
{
	if (m_comp_mode != cmBuffered)
		return -1; /* native move not supported */

	for (int i = 0; i < MAX_LAYER; ++i)
	{
		if (root->m_comp_buffer[i])
			root->m_comp_buffer[i]->m_position = root->position();
//		redrawComposition(0);
	}

	return 0; /* native move ok */
}

void eWidgetDesktop::calcWidgetClipRegion(eWidget *widget, gRegion &parent_visible)
{
		/* start with our clip region, clipped with the parent's */
	if (widget->m_vis & eWidget::wVisShow)
	{
		widget->m_visible_region = widget->m_clip_region;
		widget->m_visible_region.moveBy(widget->position());
		widget->m_visible_region &= parent_visible; // in parent space!

		if (!widget->isTransparent())
				/* remove everything this widget will contain from parent's visible list, unless widget is transparent. */
			parent_visible -= widget->m_visible_region; // will remove child regions too!

			/* now prepare for recursing to childs */
		widget->m_visible_region.moveBy(-widget->position());            // now in local space
	} else
		widget->m_visible_region = gRegion();

	widget->m_visible_with_childs = widget->m_visible_region;
	
			/* add childs in reverse (Z) order - we're going from front-to-bottom here. */
	ePtrList<eWidget>::iterator i(widget->m_childs.end());
	
	for (;;)
	{
		if (i != widget->m_childs.end())
		{
			if (i->m_vis & eWidget::wVisShow)
				calcWidgetClipRegion(*i, widget->m_visible_region);
			else
				clearVisibility(*i);
		}
		if (i == widget->m_childs.begin())
			break;
		--i;
	}
}

void eWidgetDesktop::recalcClipRegions(eWidget *root)
{
	if (m_comp_mode == cmImmediate)
	{
		gRegion background_before = m_screen.m_background_region;
		
		m_screen.m_background_region = gRegion(eRect(ePoint(0, 0), m_screen.m_screen_size));
	
		for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
		{
			if (!(i->m_vis & eWidget::wVisShow))
			{
				clearVisibility(i);
				continue;
			}
			
			gRegion visible_before = i->m_visible_with_childs;

			calcWidgetClipRegion(*i, m_screen.m_background_region);
			
			gRegion redraw = (i->m_visible_with_childs - visible_before) | (visible_before - i->m_visible_with_childs);

			redraw.moveBy(i->position());
			
			invalidate(redraw);
		}
		
		gRegion redraw = (background_before - m_screen.m_background_region) | (m_screen.m_background_region - background_before);
		invalidate(redraw);
	} else if (m_comp_mode == cmBuffered)
	{
		if (!(root->m_vis & eWidget::wVisShow))
		{
			clearVisibility(root);
			for (int i = 0; i < MAX_LAYER; ++i)
				removeBufferForWidget(root, i);
			return;
		}

		for (int i = 0; i < MAX_LAYER; ++i)
		{
			eWidgetDesktopCompBuffer *comp = root->m_comp_buffer[i];

					/* TODO: layers might not be required to have the screen size, for memory reasons. */
			if ((i == 0 && !comp) || (comp && (root->size() != comp->m_screen_size)))
				createBufferForWidget(root, 0);

			comp = root->m_comp_buffer[i]; /* it might have changed. */
			
			if (!comp) 
				continue;  /* WAIT, don't we need to invalidate,whatever */

					/* CHECKME: don't we need to recalculate everything? after all, our buffer has changed and is likely to be cleared */
		 	gRegion visible_before = root->m_visible_with_childs;

			comp->m_background_region = gRegion(eRect(comp->m_position, comp->m_screen_size));

			gRegion visible_new = root->m_visible_with_childs - visible_before;
			gRegion visible_lost = visible_before - root->m_visible_with_childs;
			visible_new.moveBy(root->position());
			visible_lost.moveBy(root->position());

			invalidate(visible_new, root, i);
			invalidate(visible_lost, root, i);

			calcWidgetClipRegion(root, comp->m_background_region);
		}
	}
}

void eWidgetDesktop::invalidateWidgetLayer(const gRegion &region, const eWidget *widget, int layer)
{
	if (m_comp_mode == cmImmediate)
	{
		invalidate(region);
		return;
	}
	eWidgetDesktopCompBuffer *comp = widget->m_comp_buffer[layer];
	if (comp)
		comp->m_dirty_region |= region;
}

void eWidgetDesktop::invalidateWidget(const gRegion &region, const eWidget *widget, int layer)
{
	if (m_comp_mode == cmImmediate)
	{
		invalidate(region);
		return;
	}

	if (!(widget->m_vis & eWidget::wVisShow))
		return;

	gRegion mregion = region;
	if (layer == -1)
		for (int layer = 0; layer < MAX_LAYER; ++layer)
			invalidateWidgetLayer(mregion, widget, layer);
	else
		invalidateWidgetLayer(mregion, widget, layer);
}

void eWidgetDesktop::invalidate(const gRegion &region, const eWidget *widget, int layer)
{
	if (region.empty())
		return;

	if (m_timer && !m_require_redraw)
		m_timer->start(0, 1); // start singleshot redraw timer

	m_require_redraw = 1;

	if (m_comp_mode == cmImmediate)
	{
			/* in immediate mode, we don't care for widget and layer, we use the topmost. */
		m_screen.m_dirty_region |= region;
	} else
	{
		if (!widget)
			for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
				invalidateWidget(region, i);
		else
			invalidateWidget(region, widget, layer);
	}
}

void eWidgetDesktop::setBackgroundColor(eWidgetDesktopCompBuffer *comp, gRGB col)
{
	comp->m_background_color = col;

		/* if there's something visible from the background, redraw it with the new color. */
	if (comp->m_dc && comp->m_background_region.valid() && !comp->m_background_region.empty())
	{
			/* todo: split out "setBackgroundColor / clear"... maybe? */
		gPainter painter(comp->m_dc);
		painter.resetClip(comp->m_background_region);
		painter.setBackgroundColor(comp->m_background_color);
		painter.clear();
	}
}

void eWidgetDesktop::setBackgroundColor(gRGB col)
{
	setBackgroundColor(&m_screen, col);

	if (m_comp_mode == cmBuffered)
		for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
		{
			for (int l = 0; l < MAX_LAYER; ++l)
				if (i->m_comp_buffer[l])
					setBackgroundColor(i->m_comp_buffer[l], l ? gRGB(0, 0, 0, 0) : col); /* all layers above 0 will have a transparent background */
		}
}

void eWidgetDesktop::setPalette(gPixmap &pm)
{
//	if (m_comp_mode == cmImmediate)
	{
		ASSERT(m_screen.m_dc);
		gPainter painter(m_screen.m_dc);
		painter.setPalette(&pm);
	}
	
	if (m_comp_mode == cmBuffered)
	{
		for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
		{
			for (int l = 0; l < MAX_LAYER; ++l)
			{
				if (!i->m_comp_buffer[l])
					continue;
				ASSERT(i->m_comp_buffer[l]->m_dc);
				gPainter painter(i->m_comp_buffer[l]->m_dc);
				painter.setPalette(&pm);
			}
		}
	}
}

void eWidgetDesktop::paintBackground(eWidgetDesktopCompBuffer *comp)
{
	if (!comp)
		return;

	comp->m_dirty_region &= comp->m_background_region;
	
	gPainter painter(comp->m_dc);
	
	painter.resetClip(comp->m_dirty_region);
	painter.setBackgroundColor(comp->m_background_color);
	painter.clear();
	
	comp->m_dirty_region = gRegion();
}


void eWidgetDesktop::paintLayer(eWidget *widget, int layer)
{
	eWidgetDesktopCompBuffer *comp = (m_comp_mode == cmImmediate) ? &m_screen : widget->m_comp_buffer[layer];
	if (m_comp_mode == cmImmediate)
		ASSERT(layer == 0);
	if (!comp)
		return;
	gPainter painter(comp->m_dc);
	painter.moveOffset(-comp->m_position);
	widget->doPaint(painter, comp->m_dirty_region, layer);
	painter.resetOffset();
}

	/* the buffer has the size and the palette of the screen (the colours given by number are looked up in it); a
	   new size or palette length makes a new buffer (the drawing thread keeps the old one while it still uses it) */
bool eWidgetDesktop::hiddenBuffer(ePtr<gPixmap> &pm, ePtr<gDC> &dc)
{
	if (!m_screen.m_dc)
		return false;
	ePtr<gPixmap> screen;
	m_screen.m_dc->getPixmap(screen);
	if (!screen || !screen->surface || (screen->surface->bpp != 32) || !screen->surface->data)
		return false;
	eSize size = screen->size();
	gSurface *s = screen->surface;
	int colors = s->clut.data ? s->clut.colors : 0;
	if (!pm || (pm->size() != size) || (pm->surface->clut.colors != colors))
	{
		dc = 0;
		pm = new gPixmap(size, 32, 0);
		if (!pm->surface || !pm->surface->data)
		{
			pm = 0;
			return false;
		}
		if (colors > 0)
		{
			pm->surface->clut.data = new gRGB[colors];
			pm->surface->clut.colors = colors;
			memcpy(pm->surface->clut.data, s->clut.data, colors * sizeof(gRGB));
		}
		dc = new gDC(pm);
		eDebug("[eWidgetDesktop] hidden buffer %dx%d", size.width(), size.height());
	}
	else if ((colors > 0) && memcmp(pm->surface->clut.data, s->clut.data, colors * sizeof(gRGB)))
		memcpy(pm->surface->clut.data, s->clut.data, colors * sizeof(gRGB));
	return true;
}

	/* HDSatelit: in immediate mode the widgets draw straight into the page the screen shows (the receiver refuses the
	   manual blit, so fb->blit() does nothing): a dirty region is first filled with the window background (fully
	   transparent in a window over the picture), then the widgets over it are drawn one by one, and those half drawn
	   states are seen. A label that scrolls (lib/gui/elabel.cpp, a step every 50 ms) or any small change that repeats
	   then flickers like a strobe. A small dirty region (its rectangles together at most an eighth of the screen) is
	   therefore composed in a hidden 32 bpp buffer in RAM (the windows and the background exactly as paint() does), and
	   at the end the region is copied to the screen once, every pixel getting its final value directly. The drawing
	   itself goes to cached RAM instead of the video memory, so the extra copy costs about what the blending on the
	   video memory saved. A larger region (a whole menu, a big subtitle page) is drawn as before, with no extra copy.
	   Only a 32 bpp screen; otherwise, or without memory for the buffer, false = paint() as before. */
bool eWidgetDesktop::paintOffscreen()
{
	if (!m_screen.m_dc)
		return false;
	gRegion dirty = m_screen.m_dirty_region & gRegion(eRect(ePoint(0, 0), m_screen.m_screen_size));
	if (dirty.empty())
		return false;
	ePtr<gPixmap> screen;
	m_screen.m_dc->getPixmap(screen);
	if (!screen || !screen->surface || (screen->surface->bpp != 32) || !screen->surface->data)
		return false;
	eSize size = screen->size();
	long long area = 0;
	for (unsigned int i = 0; i < dirty.rects.size(); ++i)
		area += (long long)dirty.rects[i].width() * dirty.rects[i].height();
	if ((area <= 0) || (area * 8 > (long long)size.width() * size.height()))
		return false;
	if (!hiddenBuffer(m_offscreen, m_offscreen_dc))
		return false;
		/* nothing is read back from the screen: as in paint(), every pixel of the dirty region is drawn again, by the
		   topmost window over it or by the background */
	ePtr<gDC> visible = m_screen.m_dc;
	m_screen.m_dc = m_offscreen_dc;
	for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
		if (i->m_vis & eWidget::wVisShow)
			paintLayer(i, 0);
	paintBackground(&m_screen);
	m_screen.m_dc = visible;
	gPainter painter(visible);
	painter.resetClip(dirty);
	painter.blit(m_offscreen, ePoint(0, 0), eRect(), 0);
	painter.flush();
	return true;
}

/*
 * HDSatelit 0.7.4: animatiile ferestrelor desenate de enigma2 (lib/gdi/hdsanimatie.h).
 *
 * Un pas = o schimbare de ecran facuta de Python dintr-o data (Session.open: ecranul de dedesubt se ascunde si cel nou se
 * arata; Session.close: cel de sus se ascunde, cel de dedesubt se arata), intre doua paint(). Pasul porneste la prima
 * fereastra cu animatia ceruta (eWindow::setAnimationMode, pusa de Session.open numai pe ecranele deschise modal). Fiecare
 * fereastra care se arata sau se ascunde in pas isi compune intai zona in „inainte” (RAM), cu ce se vede inca, deci
 * imaginea „inainte” e exact ecranul de dinaintea pasului. La paint() zona (dreptunghiul care cuprinde ferestrele schimbate)
 * se compune in „dupa” (tamponul ascuns m_offscreen), iar operatia gOpcode::hdsAnimatie trece de la una la alta pe firul
 * gRC. Ce s-a mai schimbat in afara zonei se copiaza o data, ca in paintOffscreen. Din memoria video nu se citeste nimic.
 * Ferestrele aratate fara Session.open (bara canalului la zap, volumul, mesajele scurte, PiP, subtitrarile) nu pornesc
 * niciun pas: raman fara animatie si fara nicio intarziere.
 */
int eWidgetDesktop::s_anim_fel = 0;
int eWidgetDesktop::s_anim_durata_ms = 200;

static long hdsAcumMs()
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (long)t.tv_sec * 1000L + t.tv_nsec / 1000000L;
}

void eWidgetDesktop::hdsSetAnimatie(int fel, int durata_ms)
{
	s_anim_fel = (fel >= 0 && fel <= 3) ? fel : 0;
	s_anim_durata_ms = durata_ms < 80 ? 80 : (durata_ms > 600 ? 600 : durata_ms);
	eDebug("[HdsAnimatie] felul %d, %d ms", s_anim_fel, s_anim_durata_ms);
}

int eWidgetDesktop::hdsAnimatieFel()
{
	return s_anim_fel;
}

int eWidgetDesktop::hdsAnimatieDurata()
{
	return s_anim_durata_ms;
}

void eWidgetDesktop::hdsAnimatieInchidere()
{
	m_anim_urm_inchidere = 1;
}

void eWidgetDesktop::hdsAnimatieFaraPas()
{
	m_anim_fara = 1;
	m_anim_fara_ms = hdsAcumMs();
}

void eWidgetDesktop::hdsAnimatieTine()
{
	if (!s_anim_fel || (m_style_id != 0))
		return;
	m_anim_tine = 1;
	m_anim_tine_ms = hdsAcumMs();
}

void eWidgetDesktop::hdsAnimatieElibereaza()
{
	if (!m_anim_tine)
		return;
	m_anim_tine = 0;
	m_require_redraw = 1;
	if (m_timer)
		m_timer->start(0, 1);
}

void eWidgetDesktop::hdsInainteDeSchimbare(eWidget *root, int cere)
{
	if ((m_comp_mode != cmImmediate) || (m_style_id != 0) || !s_anim_fel || !m_screen.m_dc || !root)
		return;
	long acum = hdsAcumMs();
	if (m_anim_fara)
	{
		if (acum - m_anim_fara_ms <= 300)
			return;		/* pasul acesta e fara animatie */
		m_anim_fara = 0;
	}
	if (m_anim_armata && (acum - m_anim_cand_ms > 1000))
		m_anim_armata = 0;	/* un pas ramas fara paint (fereastra n-a mai aparut): uitat */
	if (!m_anim_armata)
	{
		if (!cere)
			return;
		m_anim_armata = 1;
		m_anim_regiune = gRegion();
		m_anim_cand_ms = acum;
		m_anim_inchidere = m_anim_urm_inchidere;
		m_anim_schimbari = 0;
		hdsAnimatieOpreste();	/* o animatie inca in curs sare la final; cea noua porneste dupa ea, pe firul gRC */
	}
	m_anim_urm_inchidere = 0;
	gRegion nou = gRegion(eRect(root->position(), root->size()) & eRect(ePoint(0, 0), m_screen.m_screen_size));
	nou -= m_anim_regiune;
	if (nou.empty())
		return;
	if (!hiddenBuffer(m_anim_inainte, m_anim_inainte_dc))
	{
		m_anim_armata = 0;
		return;
	}
		/* ca in paintOffscreen: ferestrele vazute acum si fundalul, numai in zona noua, in imaginea „inainte” */
	gRegion ramas = m_screen.m_dirty_region;
	ePtr<gDC> vizibil = m_screen.m_dc;
	m_screen.m_dirty_region = nou;
	m_screen.m_dc = m_anim_inainte_dc;
	for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
		if (i->m_vis & eWidget::wVisShow)
			paintLayer(i, 0);
	paintBackground(&m_screen);
	m_screen.m_dc = vizibil;
	m_screen.m_dirty_region = ramas;
	m_anim_regiune |= nou;
	++m_anim_schimbari;
}

bool eWidgetDesktop::paintAnimatie()
{
	m_anim_armata = 0;
	gRegion compus = m_anim_regiune;
	m_anim_regiune = gRegion();
	if (compus.empty() || !m_anim_inainte || !m_anim_inainte_dc || !s_anim_fel || (hdsAcumMs() - m_anim_cand_ms > 1000))
		return false;
	if (!hiddenBuffer(m_offscreen, m_offscreen_dc))
		return false;
	eRect ecran(ePoint(0, 0), m_screen.m_screen_size);
	eRect zona = compus.extends & ecran;
		/* sub 1% din ecran nu se vede nicio animatie: desen obisnuit */
	if ((long long)zona.width() * zona.height() * 100 < (long long)ecran.width() * ecran.height())
		return false;
	gRegion murdar = m_screen.m_dirty_region & gRegion(ecran);
		/* „dupa”: zona intreaga si ce mai e de desenat, compuse in tamponul ascuns */
	ePtr<gDC> vizibil = m_screen.m_dc;
	m_screen.m_dirty_region = murdar | gRegion(zona);
	m_screen.m_dc = m_offscreen_dc;
	for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
		if (i->m_vis & eWidget::wVisShow)
			paintLayer(i, 0);
	paintBackground(&m_screen);
	m_screen.m_dc = vizibil;
		/* in zona, ce nu s-a schimbat in pas (in afara ferestrelor schimbate) e la fel inainte si dupa */
	gRegion neschimbat = gRegion(zona) - compus;
	if (!neschimbat.empty())
	{
		gPainter p(m_anim_inainte_dc);
		p.resetClip(neschimbat);
		p.blit(m_offscreen, ePoint(0, 0), eRect(), 0);
	}
	gPainter painter(vizibil);
	gRegion afara = murdar - gRegion(zona);
	if (!afara.empty())
	{
		painter.resetClip(afara);
		painter.blit(m_offscreen, ePoint(0, 0), eRect(), 0);
	}
	painter.hdsAnimatie(m_anim_inainte, m_offscreen, zona, s_anim_fel, m_anim_inchidere, s_anim_durata_ms);
	painter.flush();
	eDebug("[HdsAnimatie] pas: %d schimbari, zona %d,%d %dx%d, %s", m_anim_schimbari, zona.left(), zona.top(),
		zona.width(), zona.height(), m_anim_inchidere ? "inchidere" : "deschidere");
	return true;
}

void eWidgetDesktop::paint()
{
	m_require_redraw = 0;

		/* animatia ferestrelor: intre Session.close si processDelay nu se deseneaza nimic (cel mult 100 ms); zona murdara
		   ramane si se deseneaza la eliberare sau la termen */
	if (m_anim_tine)
	{
		long ramas = 100 - (hdsAcumMs() - m_anim_tine_ms);
		if (ramas > 0)
		{
			m_require_redraw = 1;
			if (m_timer)
				m_timer->start(ramas, 1);
			return;
		}
		m_anim_tine = 0;
	}
		/* un pas oprit (hdsAnimatieFaraPas) se deseneaza pe loc; oprirea tine 300 ms (o redesenare ramasa din urma poate
		   veni inainte ca processDelay sa arate ecranul de dedesubt); directia ceruta tine numai pana aici */
	if (m_anim_fara)
	{
		m_anim_armata = 0;
		m_anim_regiune = gRegion();
		if (hdsAcumMs() - m_anim_fara_ms > 300)
			m_anim_fara = 0;
	}
	m_anim_urm_inchidere = 0;
	if ((m_comp_mode == cmImmediate) && m_anim_armata && paintAnimatie())
		return;

	if ((m_comp_mode == cmImmediate) && paintOffscreen())
		return;

		/* walk all root windows. */
	for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
	{

		if (!(i->m_vis & eWidget::wVisShow))
			continue;

		if (m_comp_mode == cmImmediate)
			paintLayer(i, 0);
		else
			for (int l = 0; l < MAX_LAYER; ++l)
			{
				paintLayer(i, l);
				paintBackground(i->m_comp_buffer[l]);
			}
	}

	if (m_comp_mode == cmImmediate)
		paintBackground(&m_screen);

	if (m_comp_mode == cmBuffered)
	{
//		redrawComposition(0);
	} else
	{
		gPainter painter(m_screen.m_dc);
		painter.flush();
	}
}

bool eWidgetDesktop::requestCaptureRedraw()
{
	/* Called on the GUI thread after hiding a secret window. A timeout is not a redraw acknowledgement. */
	m_require_redraw = 1;
	if (!m_screen.m_dc || m_screen.m_dc->islocked() || !gRC::getInstance())
		return false;
	invalidate(gRegion(eRect(ePoint(0, 0), m_screen.m_screen_size)));
	paint();
	if (m_comp_mode == cmBuffered)
	{
		redrawComposition(0);
		/* redrawComposition(0) has no notify/flush opcode to wake the renderer. */
		gPainter painter(m_screen.m_dc);
		painter.flush();
	}
	return true;
}

bool eWidgetDesktop::captureReady()
{
	/* m_require_redraw belongs to the GUI thread; isIdle locks the rendering queue. */
	gRC *rc = gRC::getInstance();
	return m_screen.m_dc && !m_screen.m_dc->islocked() && !m_require_redraw && rc && rc->isIdle();
}

void eWidgetDesktop::setDC(gDC *dc)
{
	m_screen.m_dc = dc;
	if (m_comp_mode == cmBuffered)
		redrawComposition(1);
}

void eWidgetDesktop::setRedrawTask(eMainloop &ml)
{
	if (m_mainloop)
	{
		m_timer = 0;
		m_mainloop = 0;
	}
	m_mainloop = &ml;
	m_timer = eTimer::create(m_mainloop);
	CONNECT(m_timer->timeout, eWidgetDesktop::paint);
	
	if (m_require_redraw)
		m_timer->start(0, 1);
}

void eWidgetDesktop::makeCompatiblePixmap(ePtr<gPixmap> &pm)
{
	makeCompatiblePixmap(*(pm.operator->()));
}

void eWidgetDesktop::makeCompatiblePixmap(gPixmap &pm)
{
	if (m_comp_mode != cmImmediate)
		return;
	
//	eDebug("widgetDesktop: make compatible pixmap of %p", &pm);
	if (!m_screen.m_dc)
	{
		eWarning("eWidgetDesktop: no DC to make pixmap compatible with!");
		return;
	}

	ePtr<gPixmap> target_pixmap;
	m_screen.m_dc->getPixmap(target_pixmap);
	
	if (!target_pixmap) {
		eDebug("no target pixmap! assuming bpp > 8 for accelerated graphics.");
		return;
	}
	
	if (target_pixmap->surface && target_pixmap->surface->bpp > 8)
		return;

	ePtr<gDC> pixmap_dc = new gDC(&pm);
	gPainter pixmap_painter(pixmap_dc);
	
	pixmap_painter.mergePalette(target_pixmap);
}

void eWidgetDesktop::setCompositionMode(int mode)
{
	m_comp_mode = mode;
	
	if (mode == cmBuffered)
		for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
			createBufferForWidget(*i, 0);
	else
		for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
			for (int l = 0; l < MAX_LAYER; ++l)
				removeBufferForWidget(*i, l);
}

eWidgetDesktop::eWidgetDesktop(eSize size): m_mainloop(0)
{
	m_screen.m_dirty_region = gRegion(eRect(ePoint(0, 0), size));
	m_screen.m_screen_size = size;
	m_require_redraw = 0;
	m_style_id = 0;
	m_anim_armata = m_anim_inchidere = m_anim_urm_inchidere = m_anim_schimbari = m_anim_fara = m_anim_tine = 0;
	m_anim_cand_ms = m_anim_fara_ms = m_anim_tine_ms = 0;

	CONNECT(gRC::getInstance()->notify, eWidgetDesktop::notify);
	setCompositionMode(cmImmediate);
}

eWidgetDesktop::~eWidgetDesktop()
{
		/* tell registered root windows that they no longer have a desktop. */
	for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); )
	{
		i->m_desktop = 0;
		i = m_root.erase(i);
	}
		/* destroy all buffers */
	setCompositionMode(-1);
}

void eWidgetDesktop::createBufferForWidget(eWidget *widget, int layer)
{
	removeBufferForWidget(widget, layer);

	eWidgetDesktopCompBuffer *comp = widget->m_comp_buffer[layer] = new eWidgetDesktopCompBuffer;

	eDebug("create buffer for widget layer %d, %d x %d\n", layer, widget->size().width(), widget->size().height());

	eRect bbox = eRect(widget->position(), widget->size());
	comp->m_position = bbox.topLeft();
	comp->m_dirty_region = gRegion(eRect(ePoint(0, 0), bbox.size()));
	comp->m_screen_size = bbox.size();
		/* TODO: configurable bit depth. */

		/* clone palette. FIXME. */
	ePtr<gPixmap> pm = new gPixmap(comp->m_screen_size, 32, 1), pm_screen;
	pm->surface->clut.data = new gRGB[256];
	pm->surface->clut.colors = 256;
	pm->surface->clut.start = 0;

	m_screen.m_dc->getPixmap(pm_screen);

	memcpy(pm->surface->clut.data, pm_screen->surface->clut.data, 256 * sizeof(gRGB));

	comp->m_dc = new gDC(pm);
}

void eWidgetDesktop::removeBufferForWidget(eWidget *widget, int layer)
{
	if (widget->m_comp_buffer[layer])
	{
		delete widget->m_comp_buffer[layer];
		widget->m_comp_buffer[layer] = 0;
	}
}

void eWidgetDesktop::redrawComposition(int notified)
{
	if (m_comp_mode != cmBuffered)
		return;
	
	ASSERT(m_screen.m_dc);
	
	gPainter p(m_screen.m_dc);
	p.resetClip(eRect(ePoint(0, 0), m_screen.m_screen_size));
	p.setBackgroundColor(m_screen.m_background_color);
	p.clear();
	
	for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
	{
		if (!i->isVisible())
			continue;
		for (int layer = 0; layer < MAX_LAYER; ++layer)
		{
			ePtr<gPixmap> pm;
			if (!i->m_comp_buffer[layer])
				continue;
			i->m_comp_buffer[layer]->m_dc->getPixmap(pm);
			p.blit(pm, i->m_comp_buffer[layer]->m_position, eRect(), gPixmap::blitAlphaBlend);
		}
	}

		// flip activates on next vsync. 	
	p.flip();
	p.waitVSync();

	if (notified)
		p.notify();

	for (ePtrList<eWidget>::iterator i(m_root.begin()); i != m_root.end(); ++i)
		if (i->m_animation.m_active)
			i->m_animation.tick(1);
}

void eWidgetDesktop::notify()
{
	redrawComposition(1);
}

void eWidgetDesktop::clearVisibility(eWidget *widget)
{
	widget->m_visible_with_childs = gRegion();
	for (ePtrList<eWidget>::iterator i(widget->m_childs.begin()); i != widget->m_childs.end(); ++i)
		clearVisibility(*i);
}

void eWidgetDesktop::resize(eSize size)
{
	m_screen.m_dirty_region = gRegion(eRect(ePoint(0, 0), size));
	m_screen.m_screen_size = size;
}
