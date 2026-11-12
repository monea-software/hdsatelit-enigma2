/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_gui_ewidgetdesktop_h
#define __lib_gui_ewidgetdesktop_h

#include <lib/gdi/grc.h>
#include <lib/base/eptrlist.h>

class eWidget;
class eMainloop;
class eTimer;

		/* an eWidgetDesktopCompBuffer is a composition buffer. in 
		   immediate composition  mode, we only have one composition 
		   buffer - the screen.
		   in buffered mode, we have one buffer for each widget, plus
		   the screen.
		   
		   even in buffered mode, we have a background region, because
		   a window can be arbitrary shaped. the screen size acts as a bounding
		   box in these cases. */

struct eWidgetDesktopCompBuffer
{
	ePoint m_position;
	eSize m_screen_size;
	gRegion m_dirty_region;
	gRegion m_background_region;
	ePtr<gDC> m_dc;
	gRGB m_background_color;
};

class eWidgetDesktop: public sigc::trackable
{
public:
	eWidgetDesktop(eSize screen);
	~eWidgetDesktop();
	void addRootWidget(eWidget *root);
	void removeRootWidget(eWidget *root);
	
		/* try to move widget content. */
		/* returns -1 if there's no move support. */
		/* call this after recalcClipRegions for that widget. */
		/* you probably want to invalidate if -1 was returned. */
	int movedWidget(eWidget *root);
	
	void recalcClipRegions(eWidget *root);
	
	void invalidateWidgetLayer(const gRegion &region, const eWidget *widget, int layer);
	void invalidateWidget(const gRegion &region, const eWidget *widget, int layer = -1);
	void invalidate(const gRegion &region, const eWidget *widget = 0, int layer = -1);
	void paintLayer(eWidget *widget, int layer);
	void paint();
	/* Main-thread capture barrier: redraw current windows, then poll until gRC finished. */
	bool requestCaptureRedraw();
	bool captureReady();
	void setDC(gDC *dc);
	
	void setBackgroundColor(gRGB col);
	void setBackgroundColor(eWidgetDesktopCompBuffer *comp, gRGB col);
	
	void setPalette(gPixmap &pm);
	
	void setRedrawTask(eMainloop &ml);

	void makeCompatiblePixmap(ePtr<gPixmap> &pm);
	void makeCompatiblePixmap(gPixmap &pm);
	
	enum {
		cmImmediate,
		cmBuffered
	};
	
	void setCompositionMode(int mode);
	
	int getStyleID() { return m_style_id; }
	void setStyleID(int id) { m_style_id = id; }
	
	void resize(eSize size);
	eSize size() const { return m_screen.m_screen_size; }

		/* HDSatelit 0.7.4: animatiile ferestrelor desenate de enigma2 (lib/gdi/hdsanimatie.h), numai pe desktopul
		   televizorului, in modul imediat, pe 32 de biti. Felul (0 oprit, 1 aparitie treptata, 2 alunecare scurta, 3 marire
		   usoara) si durata le pun setAnimation_current/speed (main/enigma.cpp) cand placa nu are /proc/stb/fb/animation_*. */
	static void hdsSetAnimatie(int fel, int durata_ms);
	static int hdsAnimatieFel();
	static int hdsAnimatieDurata();
		/* Session.close: schimbarea care urmeaza e o inchidere (alunecarea coboara, marirea scade) */
	void hdsAnimatieInchidere();
		/* Session.open/close/execDialog: ecranul care se deschide sau se inchide acum nu are animatie (bara, lista de canale,
		   ghidul...): schimbarile din urmatoarele 300 ms se deseneaza pe loc, chiar daca ecranul de dedesubt are animatie */
	void hdsAnimatieFaraPas();
		/* Session.close tine desenul pana cand processDelay a aratat ecranul de dedesubt (hdsAnimatieElibereaza), cel mult
		   100 ms: altfel o redesenare ramasa din urma ar rupe inchiderea in doi pasi (fereastra pleaca spre imagine, apoi cea
		   de dedesubt apare singura) */
	void hdsAnimatieTine();
	void hdsAnimatieElibereaza();
#ifndef SWIG
		/* eWindow::show/hide, chiar inainte de schimbare: cere = fereastra are animatia pornita (setAnimationMode). Prima
		   cerere porneste un pas; in pasul pornit, fiecare fereastra care se arata sau se ascunde isi compune zona in imaginea
		   „inainte” (in RAM), cu ce se vede inca. La urmatorul paint() zona schimbata trece de la „inainte” la „dupa”. */
	void hdsInainteDeSchimbare(eWidget *root, int cere);
#endif
private:
	ePtrList<eWidget> m_root;
	void calcWidgetClipRegion(eWidget *widget, gRegion &parent_visible);
	void paintBackground(eWidgetDesktopCompBuffer *comp);
	
	eMainloop *m_mainloop;
	ePtr<eTimer> m_timer;
	
	int m_comp_mode;
	int m_require_redraw;
	
	eWidgetDesktopCompBuffer m_screen;
	
	void createBufferForWidget(eWidget *widget, int layer);
	void removeBufferForWidget(eWidget *widget, int layer);
	
	void redrawComposition(int notifed);
	void notify();
	
	void clearVisibility(eWidget *widget);
	
	int m_style_id;

		/* HDSatelit: a small dirty region is composed in a hidden buffer, then copied to the screen once
		   (ewidgetdesktop.cpp, paintOffscreen) */
	bool paintOffscreen();
	ePtr<gPixmap> m_offscreen;
	ePtr<gDC> m_offscreen_dc;
		/* a hidden 32 bpp buffer with the size and palette of the screen (m_offscreen, m_anim_inainte) */
	bool hiddenBuffer(ePtr<gPixmap> &pm, ePtr<gDC> &dc);

		/* HDSatelit 0.7.4: animatia ferestrelor (vezi hdsInainteDeSchimbare) */
	bool paintAnimatie();
	ePtr<gPixmap> m_anim_inainte;
	ePtr<gDC> m_anim_inainte_dc;
	gRegion m_anim_regiune;		/* zona deja compusa in „inainte” in pasul curent */
	int m_anim_armata, m_anim_inchidere, m_anim_urm_inchidere, m_anim_schimbari, m_anim_fara, m_anim_tine;
	long m_anim_cand_ms, m_anim_fara_ms, m_anim_tine_ms;
	static int s_anim_fel, s_anim_durata_ms;
};

#endif
