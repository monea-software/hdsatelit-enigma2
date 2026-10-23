/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_gui_ecanvas_h
#define __lib_gui_ecanvas_h

#include <lib/gui/epixmap.h>
#include <lib/python/python.h>

#ifndef SWIG
struct gDesenNetezit;
#endif

class eCanvas: public ePixmap
{
public:
	eCanvas(eWidget *parent);

	void setSize(eSize size);

	void clear(gRGB color);
	void fillRect(eRect rect, gRGB color);
	void writeText(eRect where, gRGB fg, gRGB bg, gFont *font, const char *string, int flags);

	/* HDSatelit: desen cu margini netede (lib/gdi/desennetezit.h). Coordonatele sunt in pixeli, cu
	   zecimale; pixelul i acopera [i, i+1]. Culoarea ca la fillRect (octetul de sus = transparenta,
	   0 = opac). Unghiurile in grade: 0 = dreapta, pozitiv = in sensul acelor de ceas pe ecran
	   (90 = jos, 180 = stanga, 270 = sus). Nimic nu iese din panza; intrarile fara sens (grosime sau
	   raza <= 0, NaN, infinit, coordonate peste +-1e6) nu deseneaza nimic. */
		/* linie groasa cu capete rotunde */
	void drawLine(float x0, float y0, float x1, float y1, float width, gRGB color);
		/* arc de cerc: `radius` = raza liniei de mijloc, `width` = grosimea; porneste la `startAngle` si
		   merge `sweepAngle` grade (cu semn; |sweepAngle| >= 360 = inel intreg); roundCaps 1 = capete
		   rotunde, 0 = capete drepte, taiate pe raza */
	void drawArc(float cx, float cy, float radius, float width, float startAngle, float sweepAngle, gRGB color, int roundCaps = 1);
		/* inel intreg (cerc gol): raza liniei de mijloc si grosimea */
	void drawRing(float cx, float cy, float radius, float width, gRGB color);
		/* cerc plin */
	void fillCircle(float cx, float cy, float radius, gRGB color);
		/* poligon plin (regula par-impar): lista plata [x0, y0, x1, y1, ...] sau lista de perechi
		   [(x0, y0), (x1, y1), ...]; intre 3 si 4096 de varfuri. Pentru forme mici (fiecare pixel se
		   masoara fata de toate laturile). */
	void fillPolygon(SWIG_PYOBJECT(ePyObject) points, gRGB color);
#ifndef SWIG
private:
	void deseneazaNetezit(const gDesenNetezit &forma);
#endif
};

#endif
