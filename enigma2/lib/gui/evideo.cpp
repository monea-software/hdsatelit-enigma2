/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gui/evideo.h>
#include <lib/gui/ewidgetdesktop.h>

/* HDSatelit (imaginea mica in fereastra listei de canale): ca eVideoWidget din enigma2-ul
   mai nou (lib/gui/evideo.cpp), care merge pe u57. Dupa dst_left/top/width/height se scrie si
   dst_apply=1: driverul HiSilicon are /proc/stb/vmpeg/N/dst_apply, iar nucleul din 2011 nu-l scria
   deloc. Ecranul intreg (0 0 0 0 + dst_apply) se pune la loc pe decodorul care a fost micsorat. */
static ePtr<eTimer> fullsizeTimer;
static int pendingFullsize;

static bool writeVideoProc(int decoder, const char *target, int value)
{
	char filename[128];
	snprintf(filename, sizeof(filename), "/proc/stb/vmpeg/%d/dst_%s", decoder, target);
	FILE *f = fopen(filename, "w");
	if (!f)
	{
		eDebug("[eVideoWidget] failed to open %s - %m", filename);
		return false;
	}
	fprintf(f, "%08x\n", value);
	fclose(f);
	return true;
}

/* left/top/width/height in coordonate 720x576; 0 0 0 0 = ecran intreg */
static void setVideoPosition(int decoder, int left, int top, int width, int height)
{
	eDebug("[eVideoWidget] decoder %d: %d,%d %dx%d (720x576)%s", decoder, left, top, width, height,
		(width || height) ? "" : " ecran intreg");
	if (writeVideoProc(decoder, "left", left)
		&& writeVideoProc(decoder, "top", top)
		&& writeVideoProc(decoder, "width", width)
		&& writeVideoProc(decoder, "height", height))
		writeVideoProc(decoder, "apply", 1);
}

void setFullsize()
{
	for (int decoder=0; decoder < 2; ++decoder)
	{
		if (pendingFullsize & (1 << decoder))
		{
			setVideoPosition(decoder, 0, 0, 0, 0);
			pendingFullsize &= ~(1 << decoder);
		}
	}
}

eVideoWidget::eVideoWidget(eWidget *parent)
	:eLabel(parent), m_fb_size(720, 576), m_state(0), m_decoder(1)
{
	if (!fullsizeTimer)
	{
		fullsizeTimer = eTimer::create(eApp);
		fullsizeTimer->timeout.connect(sigc::ptr_fun(setFullsize));
	}
	parent->setPositionNotifyChild(1);
//	setBackgroundColor(gRGB(0xFF000000));
}

int eVideoWidget::event(int event, void *data, void *data2)
{
	switch (event)
	{
	case evtChangedPosition:
	case evtParentChangedPosition:
		m_state &= ~1;
		updatePosition(!isVisible());
		break;
	case evtChangedSize:
		m_state |= 2;
		updatePosition(!isVisible());
		break;
	case evtParentVisibilityChanged:
		updatePosition(!isVisible());
		break;
	}
	return eLabel::event(event, data, data2);
}

eVideoWidget::~eVideoWidget()
{
	updatePosition(1);
}

void eVideoWidget::setFBSize(eSize size)
{
	m_fb_size = size;
}

void eVideoWidget::updatePosition(int disable)
{
	if (!disable)
		m_state |= 4;

	if (disable && !(m_state & 4))
	{
//		eDebug("was not visible!");
		return;
	}

	if ((m_state & 2) != 2)
	{
//		eDebug("no size!");
		return;
	}

//	eDebug("position %d %d -> %d %d", position().x(), position().y(), size().width(), size().height());

	eRect pos(0,0,0,0);
	if (!disable)
		pos = eRect(getAbsolutePosition(), size());
	else
		m_state &= ~4;

//	eDebug("abs position %d %d -> %d %d", pos.left(), pos.top(), pos.width(), pos.height());

	if (!disable && m_state & 8 && pos == m_user_rect)
	{
//		eDebug("matched");
		return;
	}

	if (!(m_state & 1))
	{
		m_user_rect = pos;
		m_state |= 1;
//		eDebug("set user rect pos!");
	}

//	eDebug("m_user_rect %d %d -> %d %d", m_user_rect.left(), m_user_rect.top(), m_user_rect.width(), m_user_rect.height());

	if (!disable)
	{
		/* HDSatelit: marginile se rotunjesc la cel mai apropiat punct din 720x576 (nu se taie),
		   iar dreptunghiul NU se mai mareste cu 4% pe fiecare parte (truc de overscan din era SD): imaginea
		   iesea din chenarul ferestrei si i se taiau marginile. */
		int fbw = m_fb_size.width() > 0 ? m_fb_size.width() : 720;
		int fbh = m_fb_size.height() > 0 ? m_fb_size.height() : 576;
		int left = (pos.left() * 720 + fbw / 2) / fbw;
		int top = (pos.top() * 576 + fbh / 2) / fbh;
		int right = ((pos.left() + pos.width()) * 720 + fbw / 2) / fbw;
		int bottom = ((pos.top() + pos.height()) * 576 + fbh / 2) / fbh;
		left = left < 0 ? 0 : (left > 720 ? 720 : left);
		top = top < 0 ? 0 : (top > 576 ? 576 : top);
		right = right < left ? left : (right > 720 ? 720 : right);
		bottom = bottom < top ? top : (bottom > 576 ? 576 : bottom);
		setVideoPosition(m_decoder, left, top, right - left, bottom - top);
		pendingFullsize &= ~(1 << m_decoder);
		m_state |= 8;
	}
	else
	{
		m_state &= ~8;
		pendingFullsize |= (1 << m_decoder);
		fullsizeTimer->start(100, true);
	}

}

void eVideoWidget::setDecoder(int decoder)
{
	m_decoder = decoder;
}
