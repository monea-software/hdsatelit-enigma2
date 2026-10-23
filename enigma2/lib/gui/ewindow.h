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
	
	void setFlag(int flags);
	void clearFlag(int flags);
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
