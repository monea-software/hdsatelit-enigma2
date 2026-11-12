/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_gui_ewidget_h
#define __lib_gui_ewidget_h

#include <lib/gdi/grc.h> /* for gRegion */
#include <lib/base/eptrlist.h> /* for eSmartPtrList */
#include <lib/gui/ewindowstyle.h> /* for eWindowStyle */
#include <lib/gui/ewidgetanimation.h>
#include <vector>

#define MAX_LAYER 16

class eWidgetDesktop;class eWidgetDesktop;

class eWidget
{
	friend class eWidgetDesktop;
public:
	eWidget(eWidget *parent);
	virtual ~eWidget();

	void move(ePoint pos);
	void resize(eSize size);
	
	ePoint position() const { return m_position; }
	eSize size() const { return m_size; }
	eSize csize() const { return m_client_size; }

	void invalidate(const gRegion &region = gRegion::invalidRegion());
	
		/* the window were to attach childs to. Normally, this 
		   is "this", but it can be overridden in case a widget
		   has a "client area", which is implemented as a child
		   widget. eWindow overrides this, for example. */
	virtual eWidget *child() { return this; }

	void show();
	void hide();
	
	void destruct();
	
	SWIG_VOID(int) getStyle(ePtr<eWindowStyle> &SWIG_NAMED_OUTPUT(style)) { if (!m_style) return 1; style = m_style; return 0; }
	void setStyle(eWindowStyle *style) { m_style = style; }
	
	void setBackgroundColor(const gRGB &col);
	void clearBackgroundColor();
	bool hasBackgroundColor() const { return m_have_background_color != 0; }
		/* HDSatelit: background gradient (backgroundGradient, or backgroundColor="start[,middle],end,direction" in
		   foreign skins): two colours when middle == end, else three, along GRADIENT_VERTICAL (top to bottom) or
		   GRADIENT_HORIZONTAL (left to right). Drawn only on widgets that are not transparent, before the background
		   colour, with the corner radius. alphablend: colours with transparency are mixed with the background colour of
		   the nearest parent that has one (sibling widgets below are not mixed in); without it they replace what is
		   there (the video shows through, as with a transparent background colour). */
	void setBackgroundGradient(const gRGB &startcolor, const gRGB &midcolor, const gRGB &endcolor, int direction, int alphablend);
	void clearBackgroundGradient();
	void setCornerRadius(int radius);
	int getCornerRadius() const { return m_corner_radius; }
		/* HDSatelit: which corners the radius rounds (RADIUS_*, cornerRadius="20;top"); the others stay square */
	void setCornerEdges(int edges);
	int getCornerEdges() const { return m_corner_edges; }
		/* HDSatelit 0.7.4: a border around the widget (widgetBorderWidth/widgetBorderColor of the skins written for
		   other images; on lists and windows also borderWidth/borderColor), drawn over the widget after it painted
		   itself, before its children, following cornerRadius; 0 = none (as before), black when no colour is given */
	void setWidgetBorderWidth(int width);
	void setWidgetBorderColor(const gRGB &color);
	int getWidgetBorderWidth() const { return m_widget_border_width; }
		/* HDSatelit 0.7.4: alphaBlend="1" (skins written for other images): a background colour with transparency is
		   mixed with the background of the nearest parent that has one, instead of replacing it (where the video
		   would show through); 0 = as before */
	void setWidgetAlphaBlend(int blend);

	enum
	{
		GRADIENT_OFF = 0,
		GRADIENT_VERTICAL = 1,
		GRADIENT_HORIZONTAL = 2
	};
	enum
	{
		RADIUS_TOP_LEFT = 1,
		RADIUS_TOP_RIGHT = 2,
		RADIUS_TOP = 3,
		RADIUS_BOTTOM_LEFT = 4,
		RADIUS_BOTTOM_RIGHT = 8,
		RADIUS_BOTTOM = 12,
		RADIUS_LEFT = 5,
		RADIUS_RIGHT = 10,
		RADIUS_ALL = 15
	};
	
	void setZPosition(int z);
	void setTransparent(int transp);
	/* HDSatelit: the widget covers only the opaque pixels (alpha >= 128) of a 32 bit pixmap drawn at its top left
	   corner, so the windows below stay visible around them (the mouse pointer, Components/HdsMouseUsb.py). A
	   transparent background would not do: in cmImmediate mode it shows the video plane, not the windows below.
	   Without opaque pixels (or with another kind of pixmap) the widget covers its whole rectangle again. */
	void setShapeFromPixmap(gPixmap *pixmap);
	void setShapeFromPixmap(ePtr<gPixmap> &pixmap) { setShapeFromPixmap((gPixmap*)pixmap); }
	
		/* untested code */
	int isVisible() { return (m_vis & wVisShow) && ((!m_parent) || m_parent->isVisible()); }
		/* ... */
		
	int isTransparent() { return m_vis & wVisTransparent; }
	
	ePoint getAbsolutePosition();
	
	eWidgetAnimation m_animation;
private:
	eWidgetDesktop *m_desktop;

	enum { 
		wVisShow = 1,
		wVisTransparent = 2,
	};
	
	int m_vis;	

	int m_layer;

	ePtrList<eWidget> m_childs;
	ePoint m_position;
	eSize m_size, m_client_size;
		/* will be accounted when there's a client offset */
	eSize m_client_offset;
	eWidget *m_parent;
	
	ePtr<eWindowStyle> m_style;
	
	void insertIntoParent();
	void doPaint(gPainter &painter, const gRegion &region, int layer);
	void recalcClipRegionsWhenVisible();
	
	void parentRemoved();
	
	gRGB m_background_color;
	int m_have_background_color;
	int m_corner_radius;
	int m_corner_edges;
	std::vector<gRGB> m_background_gradient;	/* empty, 2 or 3 colours */
	int m_gradient_vertical, m_gradient_alphablend;
	void paintBackgroundGradient(gPainter &painter);
	int m_widget_border_width;
	int m_widget_alphablend;
	gRGB m_widget_border_color;
	void paintWidgetBorder(gPainter &painter);
	
	eWidget *m_current_focus, *m_focus_owner;
	
	int m_z_position;
	int m_notify_child_on_position_change;
protected:
	void mayKillFocus();
public:

		// all in local space!
	gRegion	m_clip_region, m_visible_region, m_visible_with_childs;
	struct eWidgetDesktopCompBuffer *m_comp_buffer[MAX_LAYER];
	
	enum eWidgetEvent
	{
		evtPaint,
		evtKey,
		evtChangedPosition,
		evtChangedSize,
		
		evtParentChangedPosition,
		
		evtParentVisibilityChanged,
		evtWillChangePosition, /* new size is eRect *data */
		evtWillChangeSize,
		
		evtAction,
		
		evtFocusGot,
		evtFocusLost,
		
		evtUserWidget,
	};
	virtual int event(int event, void *data = 0, void *data2 = 0);
	void setFocus(eWidget *focus);

		/* enable this if you need the absolute position of the widget */
	void setPositionNotifyChild(int n) { m_notify_child_on_position_change = 1; }

	void notifyShowHide();
};

extern eWidgetDesktop *getDesktop(int which);

#endif
