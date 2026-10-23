/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_service_listboxservice_h
#define __lib_service_listboxservice_h

#include <lib/gdi/gpixmap.h>
#include <lib/gui/elistbox.h>
#include <lib/service/iservice.h>
#include <map>
#include <set>
#include <string>
#include <vector>

class eListboxServiceContent: public virtual iListboxContent
{
	DECLARE_REF(eListboxServiceContent);
public:
	eListboxServiceContent();

	void addService(const eServiceReference &ref, bool beforeCurrent=false);
	void removeCurrent();
	void FillFinished();

	void setIgnoreService( const eServiceReference &service );
	void setRoot(const eServiceReference &ref, bool justSet=false);
	void getCurrent(eServiceReference &ref);
	
	int getNextBeginningWithChar(char c);
	int getPrevMarkerPos();
	int getNextMarkerPos();
	
		/* support for marked services */
	void initMarked();
	void addMarked(const eServiceReference &ref);
	void removeMarked(const eServiceReference &ref);
	int isMarked(const eServiceReference &ref);

		/* services being recorded now, given from Python (the running record timers): in their rows the number and
		   the name use the color serviceRecorded (skin: colorServiceRecorded), when the skin sets it */
	void clearRecorded();
	void addRecorded(const eServiceReference &ref);
	int isRecorded(const eServiceReference &ref);

		/* services streamed to the network now (Components/HdsTransmisie.py), given from Python: a mark at the right
		   end of their rows (complex mode), also on the selected row: the pixmap picStreamed and the text of
		   setStreamedLabel, in the colors serviceStreamed / serviceStreamedSelected when the skin sets them */
	void clearStreamed();
	void addStreamed(const eServiceReference &ref);
	int isStreamed(const eServiceReference &ref);
	void setStreamedLabel(const std::string &label);

		/* this is NOT thread safe! */
	void markedQueryStart();
	int markedQueryNext(eServiceReference &ref);

	int lookupService(const eServiceReference &ref);
	void setCurrent(const eServiceReference &ref);

	enum {
		visModeSimple,
		visModeComplex
	};
	
	void setVisualMode(int mode);
	
		/* only in complex mode: */
	enum {
		celServiceNumber,
		celMarkerPixmap,
		celFolderPixmap,
		celServiceEventProgressbar,
		celServiceName,
		celServiceTypePixmap,
		celServiceInfo, // "now" event
		celElements
	};

	enum {
		picDVB_S,
		picDVB_T,
		picDVB_C,
		picServiceGroup,
		picFolder,
		picMarker,
		picServiceEventProgressbar,
		picStreamed,
		picElements
	};

	void setElementPosition(int element, eRect where);
	void setElementFont(int element, gFont *font);
	void setPixmap(int type, ePtr<gPixmap> &pic);
	
	void sort();

	int setCurrentMarked(bool);

	void setNumberOffset(int offset) { m_numberoffset = offset; }
	
	int getItemHeight() { return m_itemheight; }
	void setItemHeight(int height);

	enum {
		markedForeground,
		markedForegroundSelected,
		markedBackground,
		markedBackgroundSelected,
		serviceNotAvail,
		serviceEventProgressbarColor,
		serviceEventProgressbarColorSelected,
		serviceEventProgressbarBorderColor,
		serviceEventProgressbarBorderColorSelected,
		serviceDescriptionColor,
		serviceDescriptionColorSelected,
		serviceRecorded,
		serviceStreamed,
		serviceStreamedSelected,
		colorElements
	};
	
	void setColor(int color, gRGB &col);
	void setProgressbarHeight(int height);
	void setProgressbarBorderWidth(int width);

		/* a short label at the right end of the rows whose service path contains `marker` (complex mode), e.g.
		   "127.0.0.1:8898/dab/" -> "DAB+"; drawn with the info font and color, the event text keeps the rest */
	void setPathLabel(const std::string &marker, const std::string &label);
	void clearPathLabels();
		/* a short label on the rows of given services, drawn like the path label and in its place (
		   "DVB-I" on a satellite channel that also has its internet variant, the state of a DVB-I channel tried from
		   home); an empty label removes it. Given from Python (Components/ServiceList.py) for the services of the list */
	void setRefLabel(const eServiceReference &ref, const std::string &label);
	void clearRefLabels();
		/* the number of given services in the number column, instead of the place of the row: the operator's own
		   channel numbers (23 = TVR 1, with the gaps of the operator), given from Python for the list of a cable
		   network (Components/ServiceList.py, Components/HdsRetele.py). While numbers are set, a row without one has
		   an empty number; clearRefNumbers() brings back the counting of the rows */
	void setRefNumber(const eServiceReference &ref, int number);
	void clearRefNumbers();
protected:
	void cursorHome();
	void cursorEnd();
	int cursorMove(int count=1);
	int cursorValid();
	int cursorSet(int n);
	int cursorGet();

	void cursorSave();
	void cursorRestore();
	int size();
	
	// void setOutputDevice ? (for allocating colors, ...) .. requires some work, though
	void setSize(const eSize &size);
	
		/* the following functions always refer to the selected item */
	void paint(gPainter &painter, eWindowStyle &style, const ePoint &offset, int selected);
	
	int m_visual_mode;
		/* for complex mode */
	eRect m_element_position[celElements];
	ePtr<gFont> m_element_font[celElements];
	ePtr<gPixmap> m_pixmaps[picElements];
	gRGB m_color[colorElements];
	bool m_color_set[colorElements];
	int m_progressbar_height, m_progressbar_border_width;
private:
	typedef std::list<eServiceReference> list;
	
	list m_list;
	list::iterator m_cursor, m_saved_cursor;
	
	int m_cursor_number, m_saved_cursor_number;
	int m_size;
	
	eSize m_itemsize;
	ePtr<iServiceHandler> m_service_center;
	ePtr<iListableService> m_lst;
	
	eServiceReference m_root;

		/* support for marked services */
	std::set<eServiceReference> m_marked;
	std::set<eServiceReference>::const_iterator m_marked_iterator;

		/* services being recorded now (addRecorded) */
	std::set<eServiceReference> m_recorded;
		/* services streamed to the network now (addStreamed) and the text of their mark */
	std::set<eServiceReference> m_streamed;
	std::string m_streamed_label;

		/* support for movemode */
	bool m_current_marked;

	int m_numberoffset;

	eServiceReference m_is_playable_ignore;

	int m_itemheight;

	std::vector<std::pair<std::string, std::string> > m_path_labels;
	std::string pathLabel(const eServiceReference &ref) const;
	std::map<eServiceReference, std::string> m_ref_labels;
	std::map<eServiceReference, int> m_ref_numbers;
};

#endif
