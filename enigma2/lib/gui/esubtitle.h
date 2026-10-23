/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_gui_subtitle_h
#define __lib_gui_subtitle_h

#include <lib/gui/ewidget.h>
#include <lib/dvb/teletext.h>
#include <lib/dvb/subtitle.h>
#include <lib/python/python.h>

#ifndef SWIG
#include <list>
#include <string>
#include <vector>
#endif

struct ePangoSubtitlePageElement
{
	gRGB m_color;
	bool m_have_color;
	std::string m_pango_line;
	eRect m_area;
	ePangoSubtitlePageElement(const gRGB &color, const std::string &text)
		: m_color(color), m_have_color(true), m_pango_line(text)
	{
	}
	ePangoSubtitlePageElement(const std::string &text)
		: m_have_color(false), m_pango_line(text)
	{
	}
};

struct ePangoSubtitlePage
{
	pts_t m_show_pts;
	int m_timeout; /* in milliseconds */
	std::vector<ePangoSubtitlePageElement> m_elements;
	bool m_top;	/* the lines go at the top of the picture ({\an8} in ASS and SRT files), not at the bottom */
	ePangoSubtitlePage() : m_show_pts(0), m_timeout(0), m_top(false) {}
	void clear() { m_elements.clear(); }
};

struct eVobSubtitlePage
{
	pts_t m_show_pts;
	int m_timeout; /* in milliseconds */
	ePtr<gPixmap> m_pixmap;
};

class eDVBTeletextSubtitlePage;
class eDVBSubtitlePage;

class eSubtitleWidget: public eWidget, public sigc::trackable
{
public:
	eSubtitleWidget(eWidget *parent);
	~eSubtitleWidget();
	
	void setPage(const eDVBTeletextSubtitlePage &p);
	void setPage(const eDVBSubtitlePage &p);
	void setPage(const ePangoSubtitlePage &p);
	/* a DVB page that has arrived and will be shown in delay_ms (the service keeps it until its PTS): with OCR on, the
	   page is sent for recognition now, so that its text can be ready when setPage shows it. Without OCR: nothing. */
	void prefetchPage(const eDVBSubtitlePage &p, int delay_ms);
	/* how long the page shown now stays at most (ms); a DVB page stays 7.5 s, a film subtitle as long as its player
	   says (a DVD or Blu-ray line can be longer, and a paused film keeps its line) */
	void setPageTimeout(int timeout_ms);
	/* everything off the screen now (a jump in the film, a stop, another subtitle file); with the translation on, the
	   display queue too */
	void clearPage();
	/* the line of the subtitle has ended (servicemp3: the end of a line of a subtitle file, the empty page of a PGS or
	   DVB film subtitle). Without the display queue this is clearPage(); with it only the original of the last page
	   ends: its translation stays as long as the original stayed and at least its reading time. */
	void endPage();
	void setPixmap(ePtr<gPixmap> &pixmap, gRegion changed, eRect dest = eRect(0, 0, 720, 576));

	typedef enum { Subtitle_TTX, Subtitle_Regular, Subtitle_Bold, Subtitle_Italic, Subtitle_MAX } subfont_t;
	struct eSubtitleStyle
	{
		subfont_t face;
		int have_foreground_color, have_shadow_color;
		gRGB foreground_color, shadow_color;
		ePoint shadow_offset;
		ePtr<gFont> font;
	};

	static void setFontStyle(subfont_t face, gFont *font, int autoColor, const gRGB &col, const gRGB &shadowCol, const ePoint &shadowOffset);

	/* setStyle: how the TEXT subtitles look (teletext, subtitles from files and the text read from DVB subtitle
	   pictures; the DVB pictures themselves stay as the broadcaster sends them). Set from
	   Components/HdsSubtitrariAspect.py, at start and on every change; the text on screen is laid out again right
	   away. Colors are 0xRRGGBB.
	     font              alias of a registered font (addFont) for the letters; "" = the fonts of the skin
	                       (<subtitles>). An alias that is not registered is replaced by the skin fonts (warning).
	     font_bold         alias of the bold variant of `font`; "" = none (the letters are thickened by drawing)
	     weight            0 as in the skin (teletext thick, files normal), 1 normal, 2 thick, 3 very thick
	     size              percent of the letter size given by the skin, 50..200
	     color             -1 = the broadcast colors (teletext colors, the skin color for files), else the color
	     outline           dark edge around the letters: 0 none, 1 thin, 2 normal, 3 thick, 4 very thick
	     outline_color     color of the edge
	     shadow            shadow under the letters: 0 or 1
	     shadow_color      color of the shadow
	     shadow_direction  where the shadow falls: 0 up, 1 up right, 2 right, 3 down right, 4 down, 5 down left,
	                       6 left, 7 up left
	     shadow_distance   percent of the usual distance, 25..400
	     shadow_softness   0 hard (sharp edge), 1 soft, 2 very soft
	     background        0 none, 1 a box behind every line, 2 one box behind all lines
	     background_color  color of the box
	     background_opacity percent, 0..100
	     bottom            distance of the lowest line from the bottom edge, percent of the height, 0..40
	     line_spacing      percent of the usual distance between lines, 50..200
	   Values out of range are brought into range (with a warning). */
	static void setStyle(const std::string &font, const std::string &font_bold, int weight, int size, int color,
		int outline, int outline_color, int shadow, int shadow_color, int shadow_direction, int shadow_distance,
		int shadow_softness, int background, int background_color, int background_opacity, int bottom,
		int line_spacing);
	/* A text subtitle for the settings preview: drawn with the current look and kept on screen until
	   clearPage(); lines are split at a newline. */
	void showSample(const std::string &text);
	/* The translation test: the original lines, then the translation lines under them, drawn as with the
	   translation under the original (the translation in its own warm light yellow). Kept until clearPage(). */
	void showTranslationSample(const std::string &original, const std::string &translation);

	/* DVB subtitle pictures read as text (OCR, "Magnification of DVB subtitles" = OCR). The recognition runs in the
	   hds-ocr service; Components/HdsOcrSubtitrari.py talks to it. The widget is made by the service
	   (enableSubtitles), not by Python, so the link is static and a page is found again by its generation (one
	   counter for all subtitle widgets, never 0).
	     setOcrHandler(f)   f(generation, regions, delay_ms) is called once for every DVB page: when it arrives
	                        (prefetchPage, delay_ms = time until it is shown) or, if it did not arrive that way, when
	                        it is shown (setPage, delay_ms = -1). regions = [(x, y, width, height, stride, palette,
	                        pixels)], palette = [(r, g, b, transparency)] as in gRGB, pixels = bytes (stride bytes per
	                        row), coordinates in the DVB page (720x576 or the size from the DDS).
	                        f returns False: no OCR for this page, the picture is shown (at once, or when the page is
	                        shown). True: the answer comes through setOcrText or showOcrBitmap with the same
	                        generation, later or already during the call (a page the module knows). None = no OCR.
	     setOcrWait(ms)     how long nothing is shown while the text of a page on screen is awaited (default 500 ms);
	                        then the picture is shown and the text, if it still comes, takes its place. 0 = the
	                        picture at once. A page whose text arrived before it was shown does not wait at all.
	     setOcrText(generation, lines)
	                        lines = [(text, x, y, width, height, baseline, ARGB of the letters, A = opacity)], top
	                        to bottom, in DVB page coordinates. Drawn like teletext, with the look set by setStyle;
	                        a page whose text was in the upper part of the picture stays at the top. For a page not
	                        shown yet, the lines are kept until setPage shows it.
	     showOcrBitmap(generation)
	                        the text was not good enough: the picture is shown (now, or when the page is shown).
	   An answer for a generation that is no longer on screen or awaited (a newer page, cleared, widget gone) is
	   ignored. */
	static void setOcrHandler(SWIG_PYOBJECT(ePyObject) handler);
	static void setOcrWait(int ms);
	static void setOcrText(int generation, SWIG_PYOBJECT(ePyObject) lines);
	static void showOcrBitmap(int generation);

	/* Automatic translation of the TEXT subtitles (teletext, subtitles from files, the text read from DVB pages);
	   the services and the memory are in Components/HdsTraducereSubtitrari.py, the timing on screen is here (the
	   display queue, see esubtitle.cpp).
	     setTranslationHandler(f)  f(generation, texts, kind, delay_ms) is called for every text page about to be
	                        shown (not the settings preview): texts = [str], one per text element (a teletext element
	                        is the text of one color, a file subtitle line, an OCR line); kind 0 teletext, 1 file,
	                        2 text of a DVB page. generation > 0 for a page shown now (delay_ms = -1); generation 0
	                        for a teletext page that has arrived and will be shown in delay_ms (prefetchText): only
	                        a hint, nothing comes back for it. f returns a list of str of the same length: the
	                        translation, ready now; True: the translation comes later through setTranslation with
	                        the same generation; None (or f fails): the page will not be translated, its original is
	                        shown with the mark (setTranslationMark); anything else (False): the original is shown as
	                        it is (a subtitle already in the target language). None as f = no translation.
	                        With f set, every page waits in the display queue: nothing is shown until its
	                        translation is there (never the original first), a page stays at least as long as its
	                        original would have stayed and at least its reading time, the pages keep their order.
	     setTranslationMode(under) 0 the translation is shown instead of the original (with its colors), 1 under it
	                        (the original keeps its color, the translation is drawn in a warm light yellow,
	                        #fff3b0, or in white when the original already has that color).
	     setTranslationWait(ms)    the longest time a page waits, with nothing on screen, for its text (OCR) and its
	                        translation (0..15000 ms, default 2000), counted from when its original was to be shown;
	                        then its original is shown with the mark and its translation is no longer used.
	     setTranslation(generation, texts)
	                        texts = [str], same length as the texts given to f. An empty str drops that element
	                        (with the translation instead of the original); all empty = the original as it is. An
	                        empty list = the translation will not come: the original with the mark. For a
	                        generation that no longer waits (shown in original, cleared, widget gone): ignored.
	     setTranslationMark(text)  put before the original of a page that was not translated ("" = nothing).
	     setReadingTime(base_ms, per_char_ms, min_ms, max_ms)  the reading time of a translated page:
	                        base_ms + per_char_ms per letter of the shown translation, between min_ms and max_ms
	                        (default 700, 60, 1500, 7000).
	     prefetchText(page, delay_ms)  a teletext page that arrived before its PTS (the DVB service). */
	static void setTranslationHandler(SWIG_PYOBJECT(ePyObject) handler);
	static void setTranslationMode(int under);
	static void setTranslationWait(int ms);
	static void setTranslation(int generation, SWIG_PYOBJECT(ePyObject) texts);
	static void setTranslationMark(const std::string &text);
	static void setReadingTime(int base_ms, int per_char_ms, int min_ms, int max_ms);
#ifndef SWIG
	void prefetchText(const eDVBTeletextSubtitlePage &p, int delay_ms);
#endif

protected:
	int event(int event, void *data=0, void *data2=0);
private:
	int m_dvb_page_ok;
	eDVBSubtitlePage m_dvb_page;

	ePtr<eTimer> m_hide_subtitles_timer;

	gRegion m_visible_region;

	static eSubtitleStyle subtitleStyles[Subtitle_MAX];

	ePtr<gPixmap> m_pixmap;  // pixmap to paint on next evtPaint
	eRect m_pixmap_dest;

#ifndef SWIG
	/* the look set by setStyle (the same for every subtitle widget) */
	struct eTextStyle
	{
		std::string font, font_bold;
		int weight, size, color, outline, outline_color, shadow, shadow_color, shadow_direction, shadow_distance,
			shadow_softness, background, background_color, background_opacity, bottom, line_spacing;
		bool operator==(const eTextStyle &o) const;
	};
	static eTextStyle s_style;
	/* the live widgets: after setStyle, the text on screen is laid out again */
	static std::list<eSubtitleWidget*> s_widgets;

	/* one text element of the page, kept so that it can be laid out again */
	struct eTextElement
	{
		std::string text;	/* without markup */
		subfont_t face;
		gRGB color;			/* color sent by the broadcast / the file */
		int have_color;
		int translated = 0;	/* 1: a translation shown under the original, drawn in the translation color */
	};
	std::vector<eTextElement> m_text_elements;
	int m_text_ok;
	ePtr<gPixmap> m_text_pixmap;	/* the whole text page, ARGB: background, shadow, outline and letters */
	ePoint m_text_position;
	bool m_text_top;	/* lines from the top edge down (OCR text of a DVB page that was at the top) */

	void setTextElements(const std::vector<eTextElement> &elements);
	void layoutText();

	/* OCR of the DVB pages (see setOcrHandler) */
	static ePyObject s_ocr_handler;
	static int s_ocr_generation;
	static int s_ocr_wait_ms;
	int m_ocr_generation;		/* the page on screen waits for its text: its generation, else 0 */
	ePtr<eTimer> m_ocr_timer;	/* the wait before the picture is shown */
	/* a page sent for recognition when it arrived (prefetchPage), not shown yet: found again by setPage through its
	   show time and its region pictures (the same ePtr objects travel in the service queue) */
	enum { OCR_WAITING, OCR_TEXT, OCR_PICTURE };
	struct eOcrPrefetch
	{
		int generation;
		pts_t show_time;
		std::vector<ePtr<gPixmap> > pictures;
		std::vector<ePoint> positions;
		int state;			/* OCR_WAITING, OCR_TEXT (lines kept) or OCR_PICTURE */
		ePyObject lines;	/* owned reference when state == OCR_TEXT */
	};
	std::list<eOcrPrefetch> m_ocr_prefetch;
	static int nextOcrGeneration();
	static ePyObject ocrRegions(const eDVBSubtitlePage &page);
	static bool callOcrHandler(int generation, ePyObject regions, int delay_ms);
	void dropPrefetch(std::list<eOcrPrefetch>::iterator it);
	int askOcr();
	void ocrWaitOver();
	void showOcrText(ePyObject lines);
	void showDvbBitmap();

	/* translation of the text pages (see setTranslationHandler) */
	static ePyObject s_translation_handler;
	static int s_translation_generation;
	static int s_translation_under;
	static int s_translation_wait_ms;
	static std::string s_translation_mark;
	static int s_reading_base_ms, s_reading_char_ms, s_reading_min_ms, s_reading_max_ms;
	/* the clock of the display queue, in ms (CLOCK_MONOTONIC; the PC tests put their own) */
	static long long (*s_clock)();
	ePtr<eTimer> m_translation_timer;	/* the next change in the display queue */
	void showTextPage(const std::vector<eTextElement> &elements, int kind);
	static ePyObject translationTexts(const std::vector<eTextElement> &elements);
	static ePyObject callTranslationHandler(int generation, ePyObject texts, int kind, int delay_ms);

	/* the display queue (translation on): every page that comes, in order; the first one is on screen once it is ready */
	enum { Q_OCR, Q_TRANSLATION, Q_READY };		/* waits for its text (DVB), for its translation; ready to show */
	enum { Q_TEXT, Q_PICTURE };
	struct eQueuedPage
	{
		int id;
		int state;
		int content;			/* Q_TEXT, or Q_PICTURE: a DVB page shown as its picture */
		int kind;				/* 0 teletext, 1 file, 2 text of a DVB page */
		bool top;
		long long arrival;		/* when its original was to be shown */
		long long original_end;	/* when its original was to go (next page, empty page, hide timer); -1 = not yet */
		bool ended_by_next;		/* the next page took the place of its original (no empty page between) */
		bool superseded;		/* the next page repeats it and adds to it: it may take its place at once */
		long long deadline;		/* Q_OCR, Q_TRANSLATION: nothing on screen for it until then at most */
		long long ready_at, shown_at;	/* -1 = not yet */
		int min_ms;				/* its reading time (0 for an original or a picture) */
		int ocr_generation, translation_generation;
		std::vector<eTextElement> original, shown;
		eDVBSubtitlePage dvb;	/* the DVB page (its text is read from it, or it is shown as a picture) */
	};
	std::list<eQueuedPage> m_queue;
	int m_queue_ids;
	bool m_queue_on_screen;		/* the first page of the queue is on screen */
	bool m_queue_busy, m_queue_again;
	std::list<eQueuedPage>::iterator queueFind(int id);
	void queueStart();
	void queueText(const std::vector<eTextElement> &elements, int kind, bool top);
	void queueDvb(const eDVBSubtitlePage &p);
	int queueNew(long long now);
	void queueEnd(bool by_next, long long now);
	void queueTextKnown(int id, const std::vector<eTextElement> &elements, int kind, bool top);
	void queueOcrLines(int id, ePyObject lines);
	void queuePicture(eQueuedPage &q, long long now);
	bool queueTranslated(eQueuedPage &q, ePyObject texts, long long now);
	void queueOriginal(eQueuedPage &q, bool mark, long long now);
	void queueAdvance();
	void queueShow(const eQueuedPage &q);
	void queueClear();
	void showNothing();
	void hideTimeout();
	static int readingTime(const std::vector<eTextElement> &elements);
	static bool ocrElements(ePyObject lines, const eDVBSubtitlePage &page, std::vector<eTextElement> &elements, bool &top);
#endif
};

#endif
