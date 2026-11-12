/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_listbox_h
#define __lib_listbox_h

#include <lib/gui/ewidget.h>
#include <lib/gui/elabel.h>
#include <vector>
#include <connection.h>

class eListbox;
class eSlider;

class iListboxContent: public iObject
{
public:
	virtual ~iListboxContent()=0;
	
		/* indices go from 0 to size().
		   the end is reached when the cursor is on size(), 
		   i.e. one after the last entry (this mimics 
		   stl behavior)
		   
		   cursors never invalidate - they can become invalid
		   when stuff is removed. Cursors will always try
		   to stay on the same data, however when the current
		   item is removed, this won't work. you'll be notified
		   anyway. */
#ifndef SWIG	
protected:
	iListboxContent();
	friend class eListbox;
	virtual void updateClip(gRegion &){ };
	virtual void cursorHome()=0;
	virtual void cursorEnd()=0;
	virtual int cursorMove(int count=1)=0;
	virtual int cursorValid()=0;
	virtual int cursorSet(int n)=0;
	virtual int cursorGet()=0;
	
	virtual void cursorSave()=0;
	virtual void cursorRestore()=0;
	
	virtual int size()=0;
	
	virtual int currentCursorSelectable();
	
	void setListbox(eListbox *lb);
	
	// void setOutputDevice ? (for allocating colors, ...) .. requires some work, though
	virtual void setSize(const eSize &size)=0;
	
		/* the following functions always refer to the selected item */
	virtual void paint(gPainter &painter, eWindowStyle &style, const ePoint &offset, int selected)=0;
	
	virtual int getItemHeight()=0;
		/* HDSatelit 0.7.4: the item width a content asks for (the itemWidth of a template); 0 = the list width */
	virtual int getItemWidth() { return 0; }
	
	eListbox *m_listbox;
#endif
};

#ifndef SWIG
struct eListboxStyle
{
	ePtr<gPixmap> m_background, m_selection;
	int m_transparent_background;
	gRGB m_background_color, m_background_color_selected, m_foreground_color, m_foreground_color_selected;
	int m_background_color_set, m_foreground_color_set, m_background_color_selected_set, m_foreground_color_selected_set;
	/* newer skins: font, second font (value column), text offset and vertical alignment; unset = old behaviour */
	ePtr<gFont> m_font, m_secondfont;
	/* HDSatelit 0.7.4: the font of the title rows of a settings list (an entry without a value; headerFont) */
	ePtr<gFont> m_headerfont;
	ePoint m_text_offset;
	int m_text_offset_set;
	int m_valign;
	/* HDSatelit 0.7.4, the rows of the skins written for other images: [0] the other rows, [1] the selected row;
	   rounded corners (radius, corner bits as eWidget RADIUS_*) and a gradient of 2-3 colours (empty = none) */
	int m_item_radius[2], m_item_edges[2];
	std::vector<gRGB> m_item_gradient[2];
	int m_item_gradient_vertical[2];

		/*
			{m_transparent_background m_background_color_set m_background}
			{0 0 0} use global background color
			{0 1 x} use background color
			{0 0 p} use background picture
			{1 x 0} use transparent background
			{1 x p} use transparent background picture
		*/
};
#endif

class eListbox: public eWidget
{
	void updateScrollBar();
public:
	eListbox(eWidget *parent);
	~eListbox();

	PSignal0<void> selectionChanged;

	enum {
		showOnDemand,
		showAlways,
		showNever
	};
	void setScrollbarMode(int mode);
	void setScrollbarSliderBorderWidth(int width);
	/* HDSatelit 0.7.4: the width of the scroll bar in pixels, from the skin (scrollbarWidth); 0 = as before (a sixteenth of
	   the list, 18 to 22) */
	void setScrollbarWidth(int width);
	/* HDSatelit 0.7.4: the scroll bar look from the skins written for other images (scrollbarForegroundColor,
	   scrollbarBackgroundColor, scrollbarBorderColor, scrollbarRadius, scrollbarOffset); unset = as before (the
	   window style colours, square corners, 5 points between the rows and the bar) */
	void setScrollbarForegroundColor(gRGB &col);
	void setScrollbarBackgroundColor(gRGB &col);
	void setScrollbarBorderColor(gRGB &col);
	void setScrollbarRadius(int radius);
	void setScrollbarOffset(int offset);
		/* the picture of the moving part of the bar (scrollbarSliderPicture, scrollbarForegroundPixmap, sliderPixmap) */
	void setScrollbarForegroundPixmap(ePtr<gPixmap> &pixmap);
	void setScrollbarBackgroundPixmap(ePtr<gPixmap> &pixmap);
	/* HDSatelit 0.7.4, for plugins written for other images: false = the list does not move by itself on the
	   arrow/page keys (the plugin moves it), true = as before; enableAutoNavigation is the other name. getPageCount =
	   how many pages the entries fill. */
	void allowNativeKeys(bool allow);
	void enableAutoNavigation(bool allow) { allowNativeKeys(allow); }
	int getPageCount();
	/* HDSatelit 0.7.4: the rows as in the skins written for other images (itemCornerRadius, itemCornerRadiusSelected,
	   itemGradient, itemGradientSelected): rounded corners and a gradient behind the text; edges = the rounded corners
	   (1 top left, 2 top right, 4 bottom left, 8 bottom right, 15 all); direction 1 vertical, 2 horizontal (as
	   eWidget GRADIENT_*). Unset: the rows look exactly as before. A selection or background picture wins. */
	void setItemCornerRadius(int radius, int edges);
	void setItemCornerRadiusSelected(int radius, int edges);
	void setItemGradient(const gRGB &start, const gRGB &middle, const gRGB &end, int direction, int alphablend);
	void setItemGradientSelected(const gRGB &start, const gRGB &middle, const gRGB &end, int direction, int alphablend);
	void setWrapAround(bool);
		/* HDSatelit: 0 = the list jumps a whole page when the selection leaves it (the old way, the default);
		   n > 0 = the list moves one row at a time and keeps n rows visible below and above the selection while
		   there are more rows, so the rows that do not fit are seen coming instead of hiding on a next page */
	void setScrollMargin(int rows);
		/* HDSatelit: for a list whose rows hold several cells (the tile menu): the selection does not change how a row
		   looks, so moving it redraws nothing, and only the cell that changed is redrawn (x, width in the list) */
	void setRedrawOnSelection(bool redraw);
	void entryPartChanged(int index, int x, int width);

	void setContent(iListboxContent *content);

/*	enum Movement {
		moveUp,
		moveDown,
		moveTop,
		moveEnd,
		justCheck
	}; */

	int getCurrentIndex();
	void moveSelection(long how);
	void moveSelectionTo(int index);
	void moveToEnd();
	bool atBegin();
	bool atEnd();

	/* HDSatelit 0.7.4: moveLeft/moveRight for horizontal and grid lists (skins and plugins written for other images):
	   one item to the left/right; in a vertical list the same as moveUp/moveDown. No comments inside the enum:
	   lib/actions/parseactions.py reads it token by token. */
	enum ListboxActions {
		moveUp,
		moveDown,
		moveTop,
		moveEnd,
		pageUp,
		pageDown,
		justCheck,
		moveLeft,
		moveRight
	};

	/* HDSatelit 0.7.4: the layout of the skins written for other images (listOrientation, itemWidth, itemSpacing,
	   itemAlignment). orVertical with no spacing = the list as it always was (every function takes the old way).
	   orHorizontal = one row of items of itemWidth, LEFT/RIGHT move by one, UP/DOWN by a page; orGrid = rows of
	   items, LEFT/RIGHT by one, UP/DOWN by a row. itemSpacing = the gap between items (x, y). itemAlignment = where the
	   block of items sits in the list when it is smaller than the list (and "justify": the gaps grow to fill it). */
	enum { orVertical = 1, orHorizontal = 2, orGrid = 3 };
	enum {
		itemAlignLeftTop = 0, itemAlignCenterTop = 1, itemAlignRightTop = 2, itemAlignJustifyTop = 3,
		itemAlignLeftMiddle = 4, itemAlignCenterMiddle = 5, itemAlignRightMiddle = 6, itemAlignJustifyMiddle = 7,
		itemAlignLeftBottom = 8, itemAlignCenterBottom = 9, itemAlignRightBottom = 10, itemAlignJustifyBottom = 11,
		itemAlignJustifyLeft = 12, itemAlignJustifyCenter = 13, itemAlignJustifyRight = 14, itemAlignJustifyFull = 15
	};
	void setOrientation(int orientation);
	int getOrientation() const { return m_orientation; }
	void setItemWidth(int w);
	int getItemWidth() const { return m_itemwidth; }
	void setItemSpacing(const ePoint &spacing);
	void setItemAlignment(int alignment);
		/* the colour of the gaps between the items (spacingColor); unset = the list background */
	void setSpacingColor(const gRGB &col);
		/* a line between the rows (separatorLineColor/separatorLineSize of the skins written for other images), at the
		   bottom of every row but the last; size 0 = none (as before) */
	void setSeparatorColor(const gRGB &col);
	void setSeparatorSize(int size);

	/* HDSatelit: pagina din tastele care au si alt rost,
	   CH/PAGE + si - pe Viper (singura tasta de pagina a ei). Contextul se leaga cu prioritatea 1, dupa hartile
	   Python (0), deci lista de canale, ghidul si playerul media isi pastreaza Buchet+/-, iar in celelalte liste
	   (meniu, setari, alegeri) tasta da pagina. ListboxActions se leaga cu prioritatea 0 si ar fi luat-o inaintea lor. */
	enum ListboxFallbackActions {
		fallbackPageUp,
		fallbackPageDown
	};

	void setItemHeight(int h);
	int getItemHeight() const { return m_itemheight; }
	int getTopIndex() const { return m_top; }
	int getItemsPerPage() const { return m_items_per_page; }
	void setSelectionEnable(int en);

	void setBackgroundColor(gRGB &col);
	void setBackgroundColorSelected(gRGB &col);
	void setForegroundColor(gRGB &col);
	void setForegroundColorSelected(gRGB &col);
	void setBackgroundPicture(ePtr<gPixmap> &pixmap);
	void setSelectionPicture(ePtr<gPixmap> &pixmap);

	enum { alignTop, alignCenter, alignBottom };
	void setFont(gFont *font);
	void setSecondFont(gFont *font);
	void setHeaderFont(gFont *font);
	void setTextOffset(const ePoint &offset);
	void setVAlign(int align);

#ifndef SWIG
	struct eListboxStyle *getLocalStyle(void);
		/* the background of one row with the corners/gradient above (the list contents call it before their own
		   clear); false = nothing to do, the row is cleared as before. On true the painter has the row colours again
		   (the background colour is the middle of a gradient, for the edges of the letters). */
	bool paintItemBackground(gPainter &painter, eWindowStyle &style, const eRect &rect, int selected);

		/* entryAdded: an entry was added *before* the given index. it's index is the given number. */
	void entryAdded(int index);
		/* entryRemoved: an entry with the given index was removed. */
	void entryRemoved(int index);
		/* entryChanged: the entry with the given index was changed and should be redrawn. */
	void entryChanged(int index);
		/* the complete list changed. you should not attemp to keep the current index. */
	void entryReset(bool cursorHome=true);

	int getEntryTop();
	void invalidate(const gRegion &region = gRegion::invalidRegion());
		/* HDSatelit: the scroll of the texts of the selected row that do not fit (eDerulare, lib/gui/elabel.h);
		   a content gives it to eDerulare::drawLine only for the selected row */
	eDerulare *selectedRowScroller() { return &m_derulare; }
protected:
	int event(int event, void *data=0, void *data2=0);
	void recalcSize();

private:
	int m_scrollbar_mode, m_prev_scrollbar_page;
	int m_scrollbar_slider_border_width;
	int m_scrollbar_width;
		/* the scroll bar look from the skin; m_scrollbar_offset -1 = the old gap of 5 points */
	gRGB m_scrollbar_foreground, m_scrollbar_background, m_scrollbar_border;
	bool m_have_scrollbar_foreground, m_have_scrollbar_background, m_have_scrollbar_border;
	int m_scrollbar_radius, m_scrollbar_offset;
	ePtr<gPixmap> m_scrollbar_pixmap, m_scrollbar_background_pixmap;
	bool m_native_keys;
	void applyScrollbarStyle();
	int scrollbarGap() const { return m_scrollbar_offset >= 0 ? m_scrollbar_offset : 5; }
	bool m_content_changed;
		/* HDSatelit: the width the rows were last given (updateScrollBar); when the scroll bar comes or goes it
		   changes, and then every row is drawn again (not only the old and the new selected one) */
	int m_content_width;
	bool m_enabled_wrap_around;

	int m_top, m_selected;
	int m_itemheight;
	int m_items_per_page;
		/* the flexible layout (setOrientation...): unused while flexLayout() is false */
	int m_orientation, m_itemwidth, m_item_alignment;
	ePoint m_spacing;
	gRGB m_spacing_color;
	bool m_have_spacing_color;
	gRGB m_separator_color;
	int m_separator_size;
	void paintSeparator(gPainter &painter, const eRect &item);
	int m_cols, m_rows, m_pitch_x, m_pitch_y, m_origin_x, m_origin_y, m_item_w;
	bool flexLayout() const { return m_orientation != orVertical || m_spacing.x() || m_spacing.y(); }
	eRect itemRect(int k) const;	/* the place of the k-th visible item (k = index - m_top) */
	void recalcFlex();
	int m_scroll_margin;
	bool m_redraw_on_selection;
	int m_selection_enabled;
	ePtr<iListboxContent> m_content;
	eSlider *m_scrollbar;
	eListboxStyle m_style;
	class Derulare: public eDerulare
	{
	public:
		Derulare(eListbox *listbox): m_listbox(listbox) { }
	protected:
		eWidget *scrollWidget() { return m_listbox; }
		void scrollRedraw() { m_listbox->entryChanged(m_listbox->m_selected); }
	private:
		eListbox *m_listbox;
	};
	Derulare m_derulare;
#endif
};

#endif
