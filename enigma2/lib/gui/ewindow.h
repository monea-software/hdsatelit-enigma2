/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_gui_ewindow_h
#define __lib_gui_ewindow_h

#include <lib/gui/ewidget.h>
#include <lib/gui/ewindowstyle.h>
#include <lib/gui/elabel.h>

class eWidgetDesktop;

class eWindow: public eWidget
{
	friend class eWindowStyle;
public:
	eWindow(eWidgetDesktop *desktop, int z = 0);
	~eWindow();
	void setTitle(const std::string &string);
	std::string getTitle() const;
	eWidget *child() { return m_child; }
	
	enum {
		wfNoBorder = 1
	};

	void setBackgroundColor(const gRGB &col);
	void setCornerRadius(int radius);
		/* HDSatelit 0.7.4: the window border of the skins and plugins written for other images (borderWidth/borderColor
		   on <screen>, instance.setBorderWidth): the widget border of the client area (the window frame itself is covered by it) */
	void setBorderWidth(int width) { child()->setWidgetBorderWidth(width); }
	void setBorderColor(const gRGB &color) { child()->setWidgetBorderColor(color); }
	
	void setFlag(int flags);
	void clearFlag(int flags);

		/* HDSatelit 0.7.4: animatia ferestrei, cu numele din OE-Alliance (pluginurile si temele cheama setAnimationMode,
		   skin.py atributul animationMode): 0x00 oprita, 0x01 la aratare, 0x10 la ascundere, 0x11 amandoua; -1 = nealeasa
		   (ca 0x00; Session.open o porneste numai pe ecranele deschise modal, mytest.py). Desenul: eWidgetDesktop. */
	void setAnimationMode(int mode) { m_animation_mode = mode; }
	int getAnimationMode() const { return m_animation_mode; }
	void show();
	void hide();
#ifndef SWIG
		/* HDSatelit: the scroll of a title wider than the title bar (eDerulare, lib/gui/elabel.h) */
	eDerulare *titleScroller() { return &m_derulare; }
#endif
protected:
	enum eWindowEvents
	{
		evtTitleChanged = evtUserWidget,
	};
	int event(int event, void *data=0, void *data2=0);
private:
	std::string m_title;
	eWidget *m_child;
	int m_flags;
	eWidgetDesktop *m_desktop;
	int m_animation_mode;
#ifndef SWIG
	class Derulare: public eDerulare
	{
	public:
		Derulare(eWindow *window): m_window(window) { }
	protected:
		eWidget *scrollWidget() { return m_window; }
			/* only the decoration, like a new title */
		void scrollRedraw() { m_window->invalidate(m_window->m_visible_region); }
	private:
		eWindow *m_window;
	};
	Derulare m_derulare;
#endif
};

#endif
