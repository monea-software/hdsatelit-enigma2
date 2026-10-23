/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gui/ecanvas.h>
#include <lib/gdi/desennetezit.h>

eCanvas::eCanvas(eWidget *parent): ePixmap(parent)
{
}

void eCanvas::setSize(eSize size)
{
	setPixmap(new gPixmap(size, 32)); /* TODO: do we need 8bit surfaces? */
}

void eCanvas::clear(gRGB color)
{
	if (!m_pixmap)
		return;

	ePtr<gDC> d = new gDC(m_pixmap);
	gPainter p(d, eRect());
	p.resetClip(eRect(ePoint(0,0), m_pixmap->size()));
	p.setBackgroundColor(color);
	p.clear();

	invalidate();
}

void eCanvas::fillRect(eRect rect, gRGB color)
{
	if (!m_pixmap)
		return;

	ePtr<gDC> dc = new gDC(m_pixmap);

	gPainter p(dc);
	p.resetClip(eRect(ePoint(0,0), m_pixmap->size()));
	p.setForegroundColor(color);
	p.fill(rect);

	invalidate(rect);
}

void eCanvas::writeText(eRect rect, gRGB fg, gRGB bg, gFont *font, const char *string, int flags)
{
	ePtr<gDC> dc = new gDC(m_pixmap);

	gPainter p(dc);
	p.setFont(font);
	p.resetClip(eRect(ePoint(0,0), m_pixmap->size()));
	p.setForegroundColor(fg);
	p.setBackgroundColor(bg);
	p.renderText(rect, string, flags);

	invalidate(rect);
}

/* ------------------------------------------------------------------ HDSatelit: desen netezit */

void eCanvas::deseneazaNetezit(const gDesenNetezit &forma)
{
	if (!m_pixmap)
		return;
	eRect panza(ePoint(0, 0), m_pixmap->size());
	eRect atins = margineDesenNetezit(forma, panza);
	if (atins.empty())
		return;	/* forma fara sens sau cu totul in afara panzei: nici nu intra in coada */

	ePtr<gDC> dc = new gDC(m_pixmap);
	gPainter p(dc);
	p.resetClip(panza);
	p.desenNetezit(forma);

	invalidate(atins);
}

void eCanvas::drawLine(float x0, float y0, float x1, float y1, float width, gRGB color)
{
	gDesenNetezit f;
	f.forma = gDesenNetezit::linie;
	f.x0 = x0; f.y0 = y0; f.x1 = x1; f.y1 = y1;
	f.grosime = width;
	f.culoare = color;
	deseneazaNetezit(f);
}

void eCanvas::drawArc(float cx, float cy, float radius, float width, float startAngle, float sweepAngle, gRGB color, int roundCaps)
{
	gDesenNetezit f;
	f.forma = gDesenNetezit::arc;
	f.x0 = cx; f.y0 = cy;
	f.raza = radius; f.grosime = width;
	f.start = startAngle; f.unghi_arc = sweepAngle;
	f.capete_rotunde = roundCaps ? 1 : 0;
	f.culoare = color;
	deseneazaNetezit(f);
}

void eCanvas::drawRing(float cx, float cy, float radius, float width, gRGB color)
{
	drawArc(cx, cy, radius, width, 0.0f, 360.0f, color, 0);
}

void eCanvas::fillCircle(float cx, float cy, float radius, gRGB color)
{
	gDesenNetezit f;
	f.forma = gDesenNetezit::disc;
	f.x0 = cx; f.y0 = cy;
	f.raza = radius;
	f.culoare = color;
	deseneazaNetezit(f);
}

/* un numar din Python (int sau float); false daca nu e numar */
static bool numar(PyObject *o, float &v)
{
	if (!o || !(PyFloat_Check(o) || PyLong_Check(o)))
		return false;
	double d = PyFloat_AsDouble(o);
	if (PyErr_Occurred())
	{
		PyErr_Clear();
		return false;
	}
	v = (float)d;
	return true;
}

void eCanvas::fillPolygon(ePyObject points, gRGB color)
{
	gDesenNetezit f;
	f.forma = gDesenNetezit::poligon;
	f.culoare = color;
	PyObject *lista = points;
	if (!lista || !PySequence_Check(lista))
		return;
	PyObject *rapid = PySequence_Fast(lista, "fillPolygon: se asteapta o lista");
	if (!rapid)
	{
		PyErr_Clear();
		return;
	}
	Py_ssize_t n = PySequence_Fast_GET_SIZE(rapid);
	PyObject **el = PySequence_Fast_ITEMS(rapid);
	bool bun = n > 0 && n <= 2 * 4096;
	if (bun)
		f.puncte.reserve(2 * n);
	for (Py_ssize_t i = 0; bun && i < n; ++i)
	{
		float v;
		if (numar(el[i], v))
		{
			f.puncte.push_back(v);	/* lista plata */
			continue;
		}
		/* sau o pereche (x, y) */
		if (!PySequence_Check(el[i]) || PySequence_Size(el[i]) != 2)
		{
			PyErr_Clear();
			bun = false;
			break;
		}
		for (int k = 0; k < 2 && bun; ++k)
		{
			PyObject *c = PySequence_GetItem(el[i], k);	/* referinta noua */
			float w;
			if (numar(c, w))
				f.puncte.push_back(w);
			else
				bun = false;
			Py_XDECREF(c);
		}
	}
	Py_DECREF(rapid);
	if (PyErr_Occurred())
		PyErr_Clear();
	if (!bun || f.puncte.size() % 2)
		return;	/* element care nu e numar sau pereche, ori un numar fara pereche: nu desenam ceva ghicit */
	deseneazaNetezit(f);
}
