/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gui/elistbox.h>
#include <lib/gui/elistboxcontent.h>
#include <lib/gdi/font.h>
#include <lib/python/python.h>
#include <algorithm>

/*
    The basic idea is to have an interface which gives all relevant list
    processing functions, and can be used by the listbox to browse trough
    the list.
    
    The listbox directly uses the implemented cursor. It tries hard to avoid
    iterating trough the (possibly very large) list, so it should be O(1),
    i.e. the performance should not be influenced by the size of the list.
    
    The list interface knows how to draw the current entry to a specified 
    offset. Different interfaces can be used to adapt different lists,
    pre-filter lists on the fly etc.
    
		cursorSave/Restore is used to avoid re-iterating the list on redraw.
		The current selection is always selected as cursor position, the
    cursor is then positioned to the start, and then iterated. This gives
    at most 2x m_items_per_page cursor movements per redraw, indepenent
    of the size of the list.
    
    Although cursorSet is provided, it should be only used when there is no
    other way, as it involves iterating trough the list.
 */

/*
    UTF-8 text of a Python string, for drawing a list entry.
    The conversion returns NULL and sets a Python error when the string
    cannot be encoded: a file name with bytes that are not UTF-8 comes from
    os.listdir with surrogates. That NULL went into std::string (abort) or
    left the error set for the next Python call. Here the error is cleared
    and the bad characters are drawn as '?'.
    fallback is returned for objects that are not strings. The result is
    valid while obj and buffer live.
 */
static const char *listboxText(ePyObject obj, std::string &buffer, const char *fallback)
{
	if (!obj || !PyUnicode_Check(obj))
		return fallback;
	const char *string = PyUnicode_AsUTF8(obj);
	if (string)
		return string;
	PyErr_Clear();
	/* bytes that are not UTF-8 (a FAT stick, an event from the transmitter with broken text) arrive as
	   surrogates U+DC80..U+DCFF: write them back as the original bytes, as the SWIG fragment in
	   enigma_python.i does, so the drawing (lib/gdi/font.cpp) shows them as Latin-1 instead of '?'. */
	ePyObject replaced = PyUnicode_AsEncodedString(obj, "utf-8", "surrogateescape");
	if (!replaced)
	{
		PyErr_Clear();
		replaced = PyUnicode_AsEncodedString(obj, "utf-8", "replace");
	}
	if (!replaced)
	{
		PyErr_Clear();
		return "";
	}
	char *data = 0;
	Py_ssize_t size = 0;
	if (PyBytes_AsStringAndSize(replaced, &data, &size) == 0)
		buffer.assign(data, (size_t)size);
	else
	{
		PyErr_Clear();
		buffer.clear();
	}
	Py_DECREF(replaced);
	return buffer.c_str();
}

/*
    HDSatelit: values of the settings lists (eListboxPythonConfigContent) that do not fit in their place.
    lineFits: the sum of the glyph advances (the trailing space of the cursor included) fits in `width`; a value that
    fits is drawn exactly as before.
    cursorShift: a text setting being written ("mtext", Components/config.py ConfigText) wider than its place moves
    sideways so that the marked glyphs (the cursor) stay between `left` and `right`: past the right edge the line moves
    left by the excess, before the left edge it moves right. The same rule for the input fields is in lib/gui/elabel.cpp.
 */
static bool lineFits(eTextPara *para, int width)
{
	int glyphs = para->size(), length = 0;
	for (int i = 0; i < glyphs; ++i)
		length += para->getGlyphBBox(i).width();
	return length <= width;
}

static int cursorShift(eTextPara *para, int first, int last, int left, int right)
{
	const eRect &a = para->getGlyphBBox(first), &b = para->getGlyphBBox(last);
	int dx = 0;
	if (b.right() > right)
		dx = right - b.right();
	if (a.left() + dx < left)
		dx = left - a.left();
	return dx;
}

/*
    HDSatelit: where the place of a value ("text", "mtext") starts in a settings row with a label. The label is drawn from
    the left of the row on one line, without a clip, and the value column starts at the separation of the list
    (Components/ConfigList.py: 200). With a larger font (the text size of the interface, config.osd.fontscale 80-130, or
    a long translation) the label is wider than that, and a long value, cut at its column, covered the end of the label.
    The place starts after the drawn label and a gap when the label is longer than the separation, but not after two
    thirds of the row, so that a very long label still leaves a third of the row to the value. With a label shorter than
    the separation nothing changes.
 */
static const int VALUE_GAP = 20;

static int valueStart(gFont *font, const std::string &label, int labelLeft, int separation, int rowWidth)
{
	if (label.empty() || !font || rowWidth <= 0)
		return separation;
		/* a label surely shorter than the separation (with the gap) is not measured: the place starts there */
	if (eDerulare::surelyFits(label, font, separation - labelLeft - VALUE_GAP))
		return separation;
	ePtr<eTextPara> para = new eTextPara(eRect(0, 0, rowWidth, 100));
	para->setFont(font);
	para->renderString(label.c_str(), 0);
	int start = labelLeft + para->getBoundBox().right() + VALUE_GAP;
	int limit = rowWidth * 2 / 3;
	if (start > limit)
		start = limit;
	return start > separation ? start : separation;
}

iListboxContent::~iListboxContent()
{
}

iListboxContent::iListboxContent(): m_listbox(0)
{
}

void iListboxContent::setListbox(eListbox *lb)
{
	m_listbox = lb;
	m_listbox->setItemHeight(getItemHeight());
}

int iListboxContent::currentCursorSelectable()
{
	return 1;
}

//////////////////////////////////////

DEFINE_REF(eListboxPythonStringContent);

eListboxPythonStringContent::eListboxPythonStringContent()
	:m_cursor(0), m_itemheight(25)
{
}

eListboxPythonStringContent::~eListboxPythonStringContent()
{
	Py_XDECREF(m_list);
}

void eListboxPythonStringContent::cursorHome()
{
	m_cursor = 0;
}

void eListboxPythonStringContent::cursorEnd()
{
	m_cursor = size();
}

int eListboxPythonStringContent::cursorMove(int count)
{
	m_cursor += count;
	
	if (m_cursor < 0)
		cursorHome();
	else if (m_cursor > size())
		cursorEnd();
	return 0;
}

int eListboxPythonStringContent::cursorValid()
{
	return m_cursor < size();
}

int eListboxPythonStringContent::cursorSet(int n)
{
	m_cursor = n;
	
	if (m_cursor < 0)
		cursorHome();
	else if (m_cursor > size())
		cursorEnd();
	return 0;
}

int eListboxPythonStringContent::cursorGet()
{
	return m_cursor;
}

int eListboxPythonStringContent::currentCursorSelectable()
{
	if (m_list && cursorValid())
	{
		ePyObject item = PyList_GET_ITEM(m_list, m_cursor);
		if (!PyTuple_Check(item))
			return 1;
		if (PyTuple_Size(item) >= 2)
			return 1;
	}
	return 0;
}

void eListboxPythonStringContent::cursorSave()
{
	m_saved_cursor = m_cursor;
}

void eListboxPythonStringContent::cursorRestore()
{
	m_cursor = m_saved_cursor;
}

int eListboxPythonStringContent::size()
{
	if (!m_list)
		return 0;
	return PyList_Size(m_list);
}
	
void eListboxPythonStringContent::setSize(const eSize &size)
{
	m_itemsize = size;
}

void eListboxPythonStringContent::paint(gPainter &painter, eWindowStyle &style, const ePoint &offset, int selected)
{
	ePtr<gFont> fnt = new gFont("Regular", 20);
	painter.clip(eRect(offset, m_itemsize));
	style.setStyle(painter, selected ? eWindowStyle::styleListboxSelected : eWindowStyle::styleListboxNormal);

	eListboxStyle *local_style = 0;
	bool cursorValid = this->cursorValid();

		/* get local listbox style, if present */
	if (m_listbox)
		local_style = m_listbox->getLocalStyle();

	if (local_style)
	{
		if (selected)
		{
			/* if we have a local background color set, use that. */
			if (local_style->m_background_color_selected_set)
				painter.setBackgroundColor(local_style->m_background_color_selected);
			/* same for foreground */
			if (local_style->m_foreground_color_selected_set)
				painter.setForegroundColor(local_style->m_foreground_color_selected);
		}
		else
		{
			/* if we have a local background color set, use that. */
			if (local_style->m_background_color_set)
				painter.setBackgroundColor(local_style->m_background_color);
			/* same for foreground */
			if (local_style->m_foreground_color_set)
				painter.setForegroundColor(local_style->m_foreground_color);
		}
	}

	/* if we have no transparent background */
	if (!local_style || !local_style->m_transparent_background)
	{
			/* blit background picture, if available (otherwise, clear only) */
		if (local_style && local_style->m_background && cursorValid)
			painter.blit(local_style->m_background, offset, eRect(), 0);
		else
			painter.clear();
	} else
	{
		if (local_style->m_background && cursorValid)
			painter.blit(local_style->m_background, offset, eRect(), gPainter::BT_ALPHATEST);
		else if (selected && !local_style->m_selection)
			painter.clear();
	}

	if (m_list && cursorValid)
	{
		int gray = 0;
		ePyObject item = PyList_GET_ITEM(m_list, m_cursor); // borrowed reference!
		painter.setFont((local_style && local_style->m_font) ? local_style->m_font : fnt);

			/* the user can supply tuples, in this case the first one will be displayed. */
		if (PyTuple_Check(item))
		{
			if (PyTuple_Size(item) == 1)
				gray = 1;
			item = PyTuple_GET_ITEM(item, 0);
		}

		if (selected && local_style && local_style->m_selection)
			painter.blit(local_style->m_selection, offset, eRect(), gPainter::BT_ALPHATEST);

		if (item == Py_None)
		{
				/* seperator */
			int half_height = m_itemsize.height() / 2;
			painter.fill(eRect(offset.x() + half_height, offset.y() + half_height - 2, m_itemsize.width() - m_itemsize.height(), 4));
		} else
		{
			std::string text_buffer;
			const char *string = listboxText(item, text_buffer, "<not-a-string>");
			ePoint text_offset = offset + (selected ? ePoint(2, 2) : ePoint(1, 1));
			int flags = 0;
			if (local_style)
			{
				if (local_style->m_text_offset_set)
					text_offset = ePoint(offset.x() + local_style->m_text_offset.x(), offset.y() + local_style->m_text_offset.y());
				if (local_style->m_valign == eListbox::alignCenter)
					flags |= gPainter::RT_VALIGN_CENTER;
				else if (local_style->m_valign == eListbox::alignBottom)
					flags |= gPainter::RT_VALIGN_BOTTOM;
			}
			if (gray)
				painter.setForegroundColor(gRGB(0x808080));
			/* the text box shrinks by the offset, so the text stays inside the item */
			eSize text_size(m_itemsize.width() - (text_offset.x() - offset.x()), m_itemsize.height() - (text_offset.y() - offset.y()));
				/* HDSatelit: a text wider than the row is cut at its edge, and scrolls on the selected row */
			eDerulare::drawLine(painter, (local_style && local_style->m_font) ? local_style->m_font : fnt, eRect(text_offset, text_size), string, flags,
				(selected && m_listbox) ? m_listbox->selectedRowScroller() : 0);
		}

		if (selected && (!local_style || !local_style->m_selection))
			style.drawFrame(painter, eRect(offset, m_itemsize), eWindowStyle::frameListboxEntry);
	}

	painter.clippop();
}

void eListboxPythonStringContent::setList(ePyObject list)
{
	Py_XDECREF(m_list);
	if (!PyList_Check(list))
	{
		m_list = ePyObject();
	} else
	{
		m_list = list;
		Py_INCREF(m_list);
	}

	if (m_listbox)
		m_listbox->entryReset(false);
}

PyObject *eListboxPythonStringContent::getCurrentSelection()
{
	if (!(m_list && cursorValid()))
		Py_RETURN_NONE;

	ePyObject r = PyList_GET_ITEM(m_list, m_cursor);
	Py_XINCREF(r);
	return r;
}

void eListboxPythonStringContent::invalidateEntry(int index)
{
	if (m_listbox)
		m_listbox->entryChanged(index);
}

void eListboxPythonStringContent::invalidate()
{
	if (m_listbox)
	{
		int s = size();
		if ( m_cursor >= s )
			m_listbox->moveSelectionTo(s?s-1:0);
		else
			m_listbox->invalidate();
	}
}

//////////////////////////////////////

void eListboxPythonConfigContent::paint(gPainter &painter, eWindowStyle &style, const ePoint &offset, int selected)
{
	ePtr<gFont> fnt = new gFont("Regular", 20);
	ePtr<gFont> fnt2 = new gFont("Regular", 16);
	eRect itemrect(offset, m_itemsize);
	eListboxStyle *local_style = 0;
	bool cursorValid = this->cursorValid();

	painter.clip(itemrect);
	style.setStyle(painter, selected ? eWindowStyle::styleListboxSelected : eWindowStyle::styleListboxNormal);

		/* get local listbox style, if present */
	if (m_listbox)
		local_style = m_listbox->getLocalStyle();

	if (local_style)
	{
		if (selected)
		{
			/* if we have a local background color set, use that. */
			if (local_style->m_background_color_selected_set)
				painter.setBackgroundColor(local_style->m_background_color_selected);
			/* same for foreground */
			if (local_style->m_foreground_color_selected_set)
				painter.setForegroundColor(local_style->m_foreground_color_selected);
		}
		else
		{
			/* if we have a local background color set, use that. */
			if (local_style->m_background_color_set)
				painter.setBackgroundColor(local_style->m_background_color);
			/* same for foreground */
			if (local_style->m_foreground_color_set)
				painter.setForegroundColor(local_style->m_foreground_color);
		}
	}

	if (!local_style || !local_style->m_transparent_background)
		/* if we have no transparent background */
	{
		/* blit background picture, if available (otherwise, clear only) */
		if (local_style && local_style->m_background && cursorValid)
			painter.blit(local_style->m_background, offset, eRect(), 0);
		else
			painter.clear();
	} else
	{
		if (local_style->m_background && cursorValid)
			painter.blit(local_style->m_background, offset, eRect(), gPainter::BT_ALPHATEST);
		else if (selected && !local_style->m_selection)
			painter.clear();
	}

	if (m_list && cursorValid)
	{
			/* get current list item */
		ePyObject item = PyList_GET_ITEM(m_list, m_cursor); // borrowed reference!
		ePyObject text, value;
		/* fonts and vertical alignment from the skin, when it gives them */
		if (local_style && local_style->m_font)
			fnt = local_style->m_font;
		if (local_style && local_style->m_secondfont)
			fnt2 = local_style->m_secondfont;
		int vflags = (local_style && local_style->m_valign == eListbox::alignCenter) ? gPainter::RT_VALIGN_CENTER : 0;
		painter.setFont(fnt);

		if (selected && local_style && local_style->m_selection)
			painter.blit(local_style->m_selection, offset, eRect(), gPainter::BT_ALPHATEST);

			/* the first tuple element is a string for the left side.
			   the second one will be called, and the result shall be an tuple.

			   of this tuple,
			   the first one is the type (string).
			   the second one is the value. */
		if (PyTuple_Check(item))
		{
				/* handle left part. get item from tuple, convert to string, display. */
			text = PyTuple_GET_ITEM(item, 0);
			text = PyObject_Str(text); /* creates a new object - old object was borrowed! */
			if (!text) /* __str__ raised: do not leave the error set */
				PyErr_Print();
			std::string label_buffer;
			const char *string = listboxText(text, label_buffer, "<not-a-string>");
			eSize item_left = eSize(m_seperation, m_itemsize.height());
			eSize item_right = eSize(m_itemsize.width() - m_seperation, m_itemsize.height());
			int label_dx = (local_style && local_style->m_text_offset_set) ? local_style->m_text_offset.x() : 0;
				/* HDSatelit: the label has the row up to its value (valueStart: after a label wider than the
				   separation, up to two thirds of the row), or the whole row without a value. A label wider than
				   that is cut before the value, and scrolls on the selected row. */
			eDerulare *scroller = (selected && m_listbox) ? m_listbox->selectedRowScroller() : 0;
			int value_start = valueStart(fnt, string, label_dx, m_seperation, m_itemsize.width());
			int label_right = PyTuple_Size(item) >= 2 ? std::max(m_seperation, value_start - VALUE_GAP) : m_itemsize.width();
			eDerulare::drawLine(painter, fnt, eRect(ePoint(offset.x() + label_dx, offset.y()), eSize(label_right - label_dx, item_left.height())), string, gPainter::RT_HALIGN_LEFT | vflags, scroller);

				/* when we have no label, align value to the left. (FIXME:
				   don't we want to specifiy this individually?) */
			int value_alignment_left = !*string;

				/* string may point into text, so text is released only after its last use */
			Py_XDECREF(text);

				/* now, handle the value. get 2nd part from tuple*/
			if (PyTuple_Size(item) >= 2) // when no 2nd entry is in tuple this is a non selectable entry without config part
				value = PyTuple_GET_ITEM(item, 1);

			if (value)
			{
				ePyObject args = PyTuple_New(1);
				PyTuple_SET_ITEM(args, 0, PyLong_FromLong(selected));

					/* CallObject will call __call__ which should return the value tuple */
				value = PyObject_CallObject(value, args);

				if (PyErr_Occurred())
					PyErr_Print();

				Py_DECREF(args);
					/* the PyInt was stolen. */
			}

				/*  check if this is really a tuple */
			if (value && PyTuple_Check(value))
			{
					/* convert type to string */
				ePyObject type = PyTuple_GET_ITEM(value, 0);
				std::string type_buffer;
				const char *atype = listboxText(type, type_buffer, 0);

				if (atype)
				{
					if (!strcmp(atype, "text"))
					{
						ePyObject pvalue = PyTuple_GET_ITEM(value, 1);
						std::string value_buffer;
						const char *value = listboxText(pvalue, value_buffer, "<not-a-string>");
						painter.setFont(fnt2);
						if (value_alignment_left)
							eDerulare::drawLine(painter, fnt2, eRect(offset, item_right), value, gPainter::RT_HALIGN_LEFT | vflags, scroller);
						else
						{
								/* HDSatelit: a value wider than its place (a long address, a long name) no longer runs
								   over the label on the left: it is cut at the place and shows its beginning, like a
								   text field without the cursor, and scrolls on the selected row (eDerulare). A value
								   that fits is drawn as before, on the right. The place starts at the column, or after
								   a label wider than the column (valueStart). */
							eRect column(offset + eSize(value_start, 0), eSize(m_itemsize.width() - value_start, m_itemsize.height()));
							eDerulare::drawLine(painter, fnt2, column, value, gPainter::RT_HALIGN_RIGHT | vflags, scroller);
						}

							/* pvalue is borrowed */
					} else if (!strcmp(atype, "slider"))
					{
							/* ("slider", value, size) from ConfigSlider.getMulti; a shorter tuple was read past its end */
						if (PyTuple_GET_SIZE(value) >= 3)
						{
							ePyObject pvalue = PyTuple_GET_ITEM(value, 1);
							ePyObject psize = PyTuple_GET_ITEM(value, 2);

								/* convert value and size to long. fallback to -1 and 100 on error; a number too large
								   for a long left an OverflowError set */
							long val = -1, size = 100;
							if (pvalue && PyLong_Check(pvalue))
							{
								val = PyLong_AsLong(pvalue);
								if (val == -1 && PyErr_Occurred())
									PyErr_Clear();
							}
							if (psize && PyLong_Check(psize))
							{
								size = PyLong_AsLong(psize);
								if (size == -1 && PyErr_Occurred())
								{
									PyErr_Clear();
									size = 100;
								}
							}

								/* calc. slider length. a size of 0 divided by zero; a size below 0 or a value outside
								   0..size drew outside the column. values within 0..size draw as before */
							int width = 0;
							if (size > 0 && val > 0)
								width = (int)((long long)item_right.width() * (val < size ? val : size) / size);
							int height = item_right.height();


								/* draw slider */
							//painter.fill(eRect(offset.x() + m_seperation, offset.y(), width, height));
							//hack - make it customizable
							painter.fill(eRect(offset.x() + m_seperation, offset.y() + 5, width, height-10));
						}

							/* pvalue is borrowed */
					} else if (!strcmp(atype, "mtext"))
					{
						ePyObject pvalue = PyTuple_GET_ITEM(value, 1);
						std::string text_buffer;
						const char *text = listboxText(pvalue, text_buffer, "<not-a-string>");
							/* HDSatelit: with a label wider than the column the place starts after it (valueStart) */
						int xoffs = value_alignment_left ? 0 : value_start;
						eSize area = value_alignment_left ? item_right : eSize(m_itemsize.width() - xoffs, m_itemsize.height());
						ePtr<eTextPara> para = new eTextPara(eRect(offset + eSize(xoffs, 0), area));
						para->setFont(fnt2);
						para->renderString(text, 0);
						para->realign(value_alignment_left ? eTextPara::dirLeft : eTextPara::dirRight);
						int glyphs = para->size();

						ePyObject plist;

						if (PyTuple_Size(value) >= 3)
							plist = PyTuple_GET_ITEM(value, 2);

						int entries = 0;

						if (plist && PyList_Check(plist))
							entries = PyList_Size(plist);

							/* HDSatelit: a value being written that does not fit in its place (from the end of the label,
							   or from the start of the row when there is no label, to the end of the row) is cut there
							   and moves sideways so that the marked glyphs, the cursor, stay visible (cursorShift
							   above). A value that fits is drawn exactly as before. */
						int placeLeft = offset.x() + xoffs, placeRight = offset.x() + m_itemsize.width();
						bool fits = lineFits(para, placeRight - placeLeft);
						int dx = 0;
						if (!fits)
						{
							int first = -1, lastMarked = -1;
							for (int i = 0; i < entries; ++i)
							{
								ePyObject entry = PyList_GET_ITEM(plist, i);
								int num = PyLong_Check(entry) ? PyLong_AsLong(entry) : -1;
								if (num == -1 && PyErr_Occurred())
									PyErr_Clear();
								if (num >= 0 && num < glyphs)
								{
									if (first == -1 || num < first)
										first = num;
									if (num > lastMarked)
										lastMarked = num;
								}
									/* entry is borrowed */
							}
							if (first != -1)
								dx = cursorShift(para, first, lastMarked, placeLeft, placeRight);
							painter.clip(eRect(placeLeft, offset.y(), placeRight - placeLeft, m_itemsize.height()));
						}

						int left=0, right=0, last=-1;
						eRect bbox;
						for (int i = 0; i < entries; ++i)
						{
							ePyObject entry = PyList_GET_ITEM(plist, i);
							int num = PyLong_Check(entry) ? PyLong_AsLong(entry) : -1;

							if ((num < 0) || (num >= glyphs))
								eWarning("glyph index %d in PythonConfigList out of bounds!", num);
							else
							{
								if (last+1 != num && last != -1) {
									bbox = eRect(left + dx, offset.y(), right-left, m_itemsize.height());
									painter.fill(bbox);
								}
								para->setGlyphFlag(num, GS_INVERT);
								bbox = para->getGlyphBBox(num);
								if (last+1 != num || last == -1)
									left = bbox.left();
								right = bbox.left() + bbox.width();
								last = num;
							}
								/* entry is borrowed */
						}
						if (last != -1) {
							bbox = eRect(left + dx, offset.y(), right-left, m_itemsize.height());
							painter.fill(bbox);
						}
						painter.renderPara(para, ePoint(dx, 0));
						if (!fits)
							painter.clippop();
							/* pvalue is borrowed */
							/* plist is 0 or borrowed */
					}
				}
					/* type is borrowed */
			} else if (value)
				eWarning("eListboxPythonConfigContent: second value of tuple is not a tuple.");
			if (value)
				Py_DECREF(value);
		}

		if (selected && (!local_style || !local_style->m_selection))
			style.drawFrame(painter, eRect(offset, m_itemsize), eWindowStyle::frameListboxEntry);
	}

	painter.clippop();
}

int eListboxPythonConfigContent::currentCursorSelectable()
{
	return eListboxPythonStringContent::currentCursorSelectable();
}

//////////////////////////////////////

	/* todo: make a real infrastructure here! */
RESULT SwigFromPython(ePtr<gPixmap> &res, PyObject *obj);

eListboxPythonMultiContent::eListboxPythonMultiContent()
	:m_clip(gRegion::invalidRegion()), m_old_clip(gRegion::invalidRegion())
{
}

eListboxPythonMultiContent::~eListboxPythonMultiContent()
{
	Py_XDECREF(m_buildFunc);
	Py_XDECREF(m_selectableFunc);
	Py_XDECREF(m_template);
}

void eListboxPythonMultiContent::setSelectionClip(eRect &rect, bool update)
{
	m_selection_clip = rect;
	if (m_listbox)
		rect.moveBy(ePoint(0, m_listbox->getEntryTop()));
	if (m_clip.valid())
		m_clip |= rect;
	else
		m_clip = rect;
	if (update && m_listbox)
		m_listbox->entryChanged(m_cursor);
}

static void clearRegionHelper(gPainter &painter, eListboxStyle *local_style, const ePoint &offset, ePyObject &pbackColor, bool cursorValid, bool clear=true)
{
	if (pbackColor)
	{
		unsigned int color = PyLong_AsUnsignedLongMask(pbackColor);
		painter.setBackgroundColor(gRGB(color));
	}
	else if (local_style)
	{
		if (local_style && local_style->m_background_color_set)
			painter.setBackgroundColor(local_style->m_background_color);
		if (local_style->m_background && cursorValid)
		{
			if (local_style->m_transparent_background)
				painter.blit(local_style->m_background, offset, eRect(), gPainter::BT_ALPHATEST);
			else
				painter.blit(local_style->m_background, offset, eRect(), 0);
			return;
		}
		else if (local_style->m_transparent_background)
			return;
	}
	if (clear)
		painter.clear();
}

static void clearRegionSelectedHelper(gPainter &painter, eListboxStyle *local_style, const ePoint &offset, ePyObject &pbackColorSelected, bool cursorValid, bool clear=true)
{
	if (pbackColorSelected)
	{
		unsigned int color = PyLong_AsUnsignedLongMask(pbackColorSelected);
		painter.setBackgroundColor(gRGB(color));
	}
	else if (local_style)
	{
		if (local_style && local_style->m_background_color_selected_set)
			painter.setBackgroundColor(local_style->m_background_color_selected);
		if (local_style->m_background && cursorValid)
		{
			if (local_style->m_transparent_background)
				painter.blit(local_style->m_background, offset, eRect(), gPainter::BT_ALPHATEST);
			else
				painter.blit(local_style->m_background, offset, eRect(), 0);
			return;
		}
	}
	if (clear)
		painter.clear();
}

static void clearRegion(gPainter &painter, eWindowStyle &style, eListboxStyle *local_style, ePyObject pforeColor, ePyObject pforeColorSelected, ePyObject pbackColor, ePyObject pbackColorSelected, int selected, gRegion &rc, eRect &sel_clip, const ePoint &offset, bool cursorValid, bool clear=true)
{
	if (selected && sel_clip.valid())
	{
		gRegion part = rc - sel_clip;
		if (!part.empty())
		{
			painter.clip(part);
			style.setStyle(painter, eWindowStyle::styleListboxNormal);
			clearRegionHelper(painter, local_style, offset, pbackColor, cursorValid, clear);
			painter.clippop();
			selected = 0;
		}
		part = rc & sel_clip;
		if (!part.empty())
		{
			painter.clip(part);
			style.setStyle(painter, eWindowStyle::styleListboxSelected);
			clearRegionSelectedHelper(painter, local_style, offset, pbackColorSelected, cursorValid, clear);
			painter.clippop();
			selected = 1;
		}
	}
	else if (selected)
	{
		style.setStyle(painter, eWindowStyle::styleListboxSelected);
		clearRegionSelectedHelper(painter, local_style, offset, pbackColorSelected, cursorValid, clear);
		if (local_style && local_style->m_selection)
			painter.blit(local_style->m_selection, offset, eRect(), gPainter::BT_ALPHATEST);
	}
	else
	{
		style.setStyle(painter, eWindowStyle::styleListboxNormal);
		clearRegionHelper(painter, local_style, offset, pbackColor, cursorValid, clear);
	}

	if (selected)
	{
		if (pforeColorSelected)
		{
			unsigned int color = PyLong_AsUnsignedLongMask(pforeColorSelected);
			painter.setForegroundColor(gRGB(color));
		}
		/* if we have a local foreground color set, use that. */
		else if (local_style && local_style->m_foreground_color_selected_set)
			painter.setForegroundColor(local_style->m_foreground_color_selected);
	}
	else
	{
		if (pforeColor)
		{
			unsigned int color = PyLong_AsUnsignedLongMask(pforeColor);
			painter.setForegroundColor(gRGB(color));
		}
		/* if we have a local foreground color set, use that. */
		else if (local_style && local_style->m_foreground_color_set)
			painter.setForegroundColor(local_style->m_foreground_color);
	}
}

static ePyObject lookupColor(ePyObject color, ePyObject data)
{
	if (color == Py_None)
		return ePyObject();

	if ((!color) && (!data))
		return color;

	unsigned int icolor = PyLong_AsUnsignedLongMask(color);

		/* check if we have the "magic" template color */
	if ((icolor & 0xFF000000) == 0xFF000000)
	{
		int index = icolor & 0xFFFFFF;
		if (PyTuple_GetItem(data, index) == Py_None)
			return ePyObject();
		return PyTuple_GetItem(data, index);
	}

	if (color == Py_None)
		return ePyObject();

	return color;
}

void eListboxPythonMultiContent::paint(gPainter &painter, eWindowStyle &style, const ePoint &offset, int selected)
{
	gRegion itemregion(eRect(offset, m_itemsize));
	eListboxStyle *local_style = 0;
	eRect sel_clip(m_selection_clip);
	bool cursorValid = this->cursorValid();
	if (sel_clip.valid())
		sel_clip.moveBy(offset);

		/* get local listbox style, if present */
	if (m_listbox)
		local_style = m_listbox->getLocalStyle();

	painter.clip(itemregion);
	clearRegion(painter, style, local_style, ePyObject(), ePyObject(), ePyObject(), ePyObject(), selected, itemregion, sel_clip, offset, cursorValid);

	ePyObject items, buildfunc_ret;

	if (m_list && cursorValid)
	{
			/* a multicontent list can be used in two ways:
				either each item is a list of (TYPE,...)-tuples,
				or there is a template defined, which is a list of (TYPE,...)-tuples,
				and the list is an unformatted tuple. The template then references items from the list.
			*/
		items = PyList_GET_ITEM(m_list, m_cursor); // borrowed reference!

		if (m_buildFunc)
		{
			if (PyCallable_Check(m_buildFunc))  // when we have a buildFunc then call it
			{
				if (PyTuple_Check(items))
					buildfunc_ret = items = PyObject_CallObject(m_buildFunc, items);
				else
					eDebug("items is no tuple");
			}
			else
				eDebug("buildfunc is not callable");
		}

		if (!items)
		{
			eDebug("eListboxPythonMultiContent: error getting item %d", m_cursor);
			goto error_out;
		}

		if (!m_template)
		{
			if (!PyList_Check(items))
			{
				eDebug("eListboxPythonMultiContent: list entry %d is not a list (non-templated)", m_cursor);
				goto error_out;
			}
		} else
		{
			if (!PyTuple_Check(items))
			{
				eDebug("eListboxPythonMultiContent: list entry %d is not a tuple (templated)", m_cursor);
				goto error_out;
			}
		}

		ePyObject data;

			/* if we have a template, use the template for the actual formatting. 
				we will later detect that "data" is present, and refer to that, instead
				of the immediate value. */
		int start = 1;
		if (m_template)
		{
			data = items;
			items = m_template;
			start = 0;
		}

		int size = PyList_Size(items);
		for (int i = start; i < size; ++i)
		{
			ePyObject item = PyList_GET_ITEM(items, i); // borrowed reference!

			if (!item)
			{
				eDebug("eListboxPythonMultiContent: ?");
				goto error_out;
			}

			if (!PyTuple_Check(item))
			{
				eDebug("eListboxPythonMultiContent did not receive a tuple.");
				goto error_out;
			}

			int size = PyTuple_Size(item);

			if (!size)
			{
				eDebug("eListboxPythonMultiContent receive empty tuple.");
				goto error_out;
			}

			int type = PyLong_AsLong(PyTuple_GET_ITEM(item, 0));

			switch (type)
			{
			case TYPE_TEXT: // text
			{
			/*
				(0, x, y, width, height, fnt, flags, "bla" [, color, colorSelected, backColor, backColorSelected, borderWidth, borderColor] )
			*/
				ePyObject px = PyTuple_GET_ITEM(item, 1),
							py = PyTuple_GET_ITEM(item, 2),
							pwidth = PyTuple_GET_ITEM(item, 3),
							pheight = PyTuple_GET_ITEM(item, 4),
							pfnt = PyTuple_GET_ITEM(item, 5),
							pflags = PyTuple_GET_ITEM(item, 6),
							pstring = PyTuple_GET_ITEM(item, 7),
							pforeColor, pforeColorSelected, pbackColor, pbackColorSelected, pborderWidth, pborderColor;

				if (!(px && py && pwidth && pheight && pfnt && pflags && pstring))
				{
					eDebug("eListboxPythonMultiContent received too small tuple (must be (TYPE_TEXT, x, y, width, height, fnt, flags, string [, color, backColor, backColorSelected, borderWidth, borderColor])");
					goto error_out;
				}

				if (size > 8)
					pforeColor = lookupColor(PyTuple_GET_ITEM(item, 8), data);

				if (size > 9)
					pforeColorSelected = lookupColor(PyTuple_GET_ITEM(item, 9), data);

				if (size > 10)
					pbackColor = lookupColor(PyTuple_GET_ITEM(item, 10), data);

				if (size > 11)
					pbackColorSelected = lookupColor(PyTuple_GET_ITEM(item, 11), data);

				if (size > 12)
				{
					pborderWidth = PyTuple_GET_ITEM(item, 12);
					if (pborderWidth == Py_None)
						pborderWidth=ePyObject();
				}
				if (size > 13)
					pborderColor = lookupColor(PyTuple_GET_ITEM(item, 13), data);

				if (PyLong_Check(pstring) && data) /* if the string is in fact a number, it refers to the 'data' list. */
				{
					pstring = PyTuple_GetItem(data, PyLong_AsLong(pstring));
					if (!pstring) /* index outside the 'data' list: IndexError, drawn as <not-a-string> */
						PyErr_Clear();
				}

							/* don't do anything if we have 'None' as string */
				if (pstring == Py_None)
					continue;

				std::string text_buffer;
				const char *string = listboxText(pstring, text_buffer, "<not-a-string>");
				int x = PyLong_AsLong(px) + offset.x();
				int y = PyLong_AsLong(py) + offset.y();
				int width = PyLong_AsLong(pwidth);
				int height = PyLong_AsLong(pheight);
				int flags = PyLong_AsLong(pflags);
				int fnt = PyLong_AsLong(pfnt);
				int bwidth = pborderWidth ? PyLong_AsLong(pborderWidth) : 0;

				if (m_font.find(fnt) == m_font.end())
				{
					eDebug("eListboxPythonMultiContent: specified font %d was not found!", fnt);
					goto error_out;
				}

				eRect rect(x+bwidth, y+bwidth, width-bwidth*2, height-bwidth*2);
				painter.clip(rect);

				{
					gRegion rc(rect);
					bool mustClear = (selected && pbackColorSelected) || (!selected && pbackColor);
					clearRegion(painter, style, local_style, pforeColor, pforeColorSelected, pbackColor, pbackColorSelected, selected, rc, sel_clip, offset, cursorValid, mustClear);
				}

				painter.setFont(m_font[fnt]);
					/* HDSatelit: a one-line text wider than its cell is cut at the edge, and scrolls on the selected row */
				eDerulare::drawLine(painter, m_font[fnt], rect, string, flags, (selected && m_listbox) ? m_listbox->selectedRowScroller() : 0);
				painter.clippop();

				// draw border
				if (bwidth)
				{
					eRect rect(eRect(x, y, width, height));
					painter.clip(rect);
					if (pborderColor)
					{
						unsigned int color = PyLong_AsUnsignedLongMask(pborderColor);
						painter.setForegroundColor(gRGB(color));
					}

					rect.setRect(x, y, width, bwidth);
					painter.fill(rect);

					rect.setRect(x, y+bwidth, bwidth, height-bwidth);
					painter.fill(rect);

					rect.setRect(x+bwidth, y+height-bwidth, width-bwidth, bwidth);
					painter.fill(rect);

					rect.setRect(x+width-bwidth, y+bwidth, bwidth, height-bwidth);
					painter.fill(rect);

					painter.clippop();
				}
				break;
			}
			case TYPE_PROGRESS_PIXMAP: // Progress
			/*
				(1, x, y, width, height, filled_percent, pixmap [, borderWidth, foreColor, backColor, backColorSelected] )
			*/
			case TYPE_PROGRESS: // Progress
			{
			/*
				(1, x, y, width, height, filled_percent [, borderWidth, foreColor, backColor, backColorSelected] )
			*/
				ePyObject px = PyTuple_GET_ITEM(item, 1),
							py = PyTuple_GET_ITEM(item, 2),
							pwidth = PyTuple_GET_ITEM(item, 3),
							pheight = PyTuple_GET_ITEM(item, 4),
							pfilled_perc = PyTuple_GET_ITEM(item, 5),
							ppixmap, pborderWidth, pforeColor, pforeColorSelected, pbackColor, pbackColorSelected;
				int idx = 6;
				if (type == TYPE_PROGRESS)
				{
					if (!(px && py && pwidth && pheight && pfilled_perc))
					{
						eDebug("eListboxPythonMultiContent received too small tuple (must be (TYPE_PROGRESS, x, y, width, height, filled percent [,border width, foreColor, backColor, backColorSelected]))");
						goto error_out;
					}
				}
				else
				{
					ppixmap = PyTuple_GET_ITEM(item, idx++);
					if (ppixmap == Py_None)
						continue;
					if (!(px && py && pwidth && pheight && pfilled_perc, ppixmap))
					{
						eDebug("eListboxPythonMultiContent received too small tuple (must be (TYPE_PROGRESS_PIXMAP, x, y, width, height, filled percent, pixmap, [,border width, foreColor, backColor, backColorSelected]))");
						goto error_out;
					}
				}

				if (size > idx)
				{
					pborderWidth = PyTuple_GET_ITEM(item, idx++);
					if (pborderWidth == Py_None)
						pborderWidth = ePyObject();
				}
				if (size > idx)
				{
					pforeColor = PyTuple_GET_ITEM(item, idx++);
					if (pforeColor == Py_None)
						pforeColor = ePyObject();
				}
				if (size > idx)
				{
					pforeColorSelected = PyTuple_GET_ITEM(item, idx++);
					if (pforeColorSelected == Py_None)
						pforeColorSelected=ePyObject();
				}
				if (size > idx)
				{
					pbackColor = PyTuple_GET_ITEM(item, idx++);
					if (pbackColor == Py_None)
						pbackColor=ePyObject();
				}
				if (size > idx)
				{
					pbackColorSelected = PyTuple_GET_ITEM(item, idx++);
					if (pbackColorSelected == Py_None)
						pbackColorSelected=ePyObject();
				}

				int x = PyLong_AsLong(px) + offset.x();
				int y = PyLong_AsLong(py) + offset.y();
				int width = PyLong_AsLong(pwidth);
				int height = PyLong_AsLong(pheight);
				int filled = PyLong_AsLong(pfilled_perc);

				if ((filled < 0) && data) /* if the string is in a negative number, it refers to the 'data' list. */
					filled = PyLong_AsLong(PyTuple_GetItem(data, -filled));
					
							/* don't do anything if percent out of range */
				if ((filled < 0) || (filled > 100))
					continue;

				int bwidth = pborderWidth ? PyLong_AsLong(pborderWidth) : 2;

				eRect rect(x, y, width, height);
				painter.clip(rect);

				{
					gRegion rc(rect);
					bool mustClear = (selected && pbackColorSelected) || (!selected && pbackColor);
					clearRegion(painter, style, local_style, pforeColor, pforeColorSelected, pbackColor, pbackColorSelected, selected, rc, sel_clip, offset, cursorValid, mustClear);
				}

				// border
				rect.setRect(x, y, width, bwidth);
				painter.fill(rect);

				rect.setRect(x, y+bwidth, bwidth, height-bwidth);
				painter.fill(rect);

				rect.setRect(x+bwidth, y+height-bwidth, width-bwidth, bwidth);
				painter.fill(rect);

				rect.setRect(x+width-bwidth, y+bwidth, bwidth, height-bwidth);
				painter.fill(rect);

				rect.setRect(x+bwidth, y+bwidth, (width-bwidth*2) * filled / 100, height-bwidth*2);

				// progress
				if (ppixmap)
				{
					ePtr<gPixmap> pixmap;
					if (PyLong_Check(ppixmap) && data) /* if the pixmap is in fact a number, it refers to the data list */
						ppixmap = PyTuple_GetItem(data, PyLong_AsLong(ppixmap));

					if (SwigFromPython(pixmap, ppixmap))
					{
						eDebug("eListboxPythonMultiContent (Pixmap) get pixmap failed");
						painter.clippop();
						continue;
					}
					painter.blit(pixmap, rect.topLeft(), rect, 0);
				}
				else
					painter.fill(rect);

				painter.clippop();
				break;
			}
			case TYPE_PIXMAP_ALPHABLEND:
			case TYPE_PIXMAP_ALPHATEST:
			case TYPE_PIXMAP: // pixmap
			{
			/*
				(2, x, y, width, height, pixmap [, backColor, backColorSelected] )
			*/

				ePyObject px = PyTuple_GET_ITEM(item, 1),
							py = PyTuple_GET_ITEM(item, 2),
							pwidth = PyTuple_GET_ITEM(item, 3),
							pheight = PyTuple_GET_ITEM(item, 4),
							ppixmap = PyTuple_GET_ITEM(item, 5),
							pbackColor, pbackColorSelected;

				if (!(px && py && pwidth && pheight && ppixmap))
				{
					eDebug("eListboxPythonMultiContent received too small tuple (must be (TYPE_PIXMAP, x, y, width, height, pixmap [, backColor, backColorSelected] ))");
					goto error_out;
				}

				if (PyLong_Check(ppixmap) && data) /* if the pixemap is in fact a number, it refers to the 'data' list. */
					ppixmap = PyTuple_GetItem(data, PyLong_AsLong(ppixmap));

							/* don't do anything if we have 'None' as pixmap */
				if (ppixmap == Py_None)
					continue;

				int x = PyLong_AsLong(px) + offset.x();
				int y = PyLong_AsLong(py) + offset.y();
				int width = PyLong_AsLong(pwidth);
				int height = PyLong_AsLong(pheight);
				ePtr<gPixmap> pixmap;
				if (SwigFromPython(pixmap, ppixmap))
				{
					eDebug("eListboxPythonMultiContent (Pixmap) get pixmap failed");
					goto error_out;
				}

				if (size > 6)
					pbackColor = lookupColor(PyTuple_GET_ITEM(item, 6), data);

				if (size > 7)
					pbackColorSelected = lookupColor(PyTuple_GET_ITEM(item, 7), data);

				eRect rect(x, y, width, height);
				painter.clip(rect);

				{
					gRegion rc(rect);
					bool mustClear = (selected && pbackColorSelected) || (!selected && pbackColor);
					clearRegion(painter, style, local_style, ePyObject(), ePyObject(), pbackColor, pbackColorSelected, selected, rc, sel_clip, offset, cursorValid, mustClear);
				}

				painter.blit(pixmap, rect.topLeft(), rect, (type == TYPE_PIXMAP_ALPHATEST) ? gPainter::BT_ALPHATEST : (type == TYPE_PIXMAP_ALPHABLEND) ? gPainter::BT_ALPHABLEND : 0);
				painter.clippop();
				break;
			}
			default:
				eWarning("eListboxPythonMultiContent received unknown type (%d)", type);
				goto error_out;
			}
		}
	}

	if (selected && !sel_clip.valid() && (!local_style || !local_style->m_selection))
		style.drawFrame(painter, eRect(offset, m_itemsize), eWindowStyle::frameListboxEntry);

error_out:
	if (buildfunc_ret)
		Py_DECREF(buildfunc_ret);

	painter.clippop();
}

void eListboxPythonMultiContent::setBuildFunc(ePyObject cb)
{
	Py_XDECREF(m_buildFunc);
	m_buildFunc=cb;
	Py_XINCREF(m_buildFunc);
}

void eListboxPythonMultiContent::setSelectableFunc(ePyObject cb)
{
	Py_XDECREF(m_selectableFunc);
	m_selectableFunc=cb;
	Py_XINCREF(m_selectableFunc);
}

int eListboxPythonMultiContent::currentCursorSelectable()
{
	/* each list-entry is a list of tuples. if the first of these is none, it's not selectable */
	if (m_list && cursorValid())
	{
		if (m_selectableFunc && PyCallable_Check(m_selectableFunc))
		{
			ePyObject args = PyList_GET_ITEM(m_list, m_cursor); // borrowed reference!
			if (PyTuple_Check(args))
			{
				ePyObject ret = PyObject_CallObject(m_selectableFunc, args);
				if (ret)
				{
					bool retval = ret == Py_True;
					Py_DECREF(ret);
					return retval;
				}
				eDebug("call m_selectableFunc failed!!! assume not callable");
			}
			else
				eDebug("m_list[m_cursor] is not a tuple!!! assume not callable");
		}
		else
		{
			ePyObject item = PyList_GET_ITEM(m_list, m_cursor);
			if (PyList_Check(item))
			{
				item = PyList_GET_ITEM(item, 0);
				if (item != Py_None)
					return 1;
			} else if (PyTuple_Check(item))
			{
				item = PyTuple_GET_ITEM(item, 0);
				if (item != Py_None)
					return 1;
			}
			else if (m_buildFunc && PyCallable_Check(m_buildFunc))
				return 1;
		}
	}
	return 0;
}

void eListboxPythonMultiContent::setFont(int fnt, gFont *font)
{
	if (font)
		m_font[fnt] = font;
	else
		m_font.erase(fnt);
}

void eListboxPythonMultiContent::setItemHeight(int height)
{
	m_itemheight = height;
	if (m_listbox)
		m_listbox->setItemHeight(height);
}

void eListboxPythonMultiContent::setList(ePyObject list)
{
	m_old_clip = m_clip = gRegion::invalidRegion();
	eListboxPythonStringContent::setList(list);
}

void eListboxPythonMultiContent::updateClip(gRegion &clip)
{
	if (m_clip.valid())
	{
		clip &= m_clip;
		if (m_old_clip.valid() && !(m_clip-m_old_clip).empty())
			m_clip -= m_old_clip;
		m_old_clip = m_clip;
	}
	else
		m_old_clip = m_clip = gRegion::invalidRegion();
}

void eListboxPythonMultiContent::entryRemoved(int idx)
{
	if (m_listbox)
		m_listbox->entryRemoved(idx);
}

void eListboxPythonMultiContent::setTemplate(ePyObject tmplate)
{
	Py_XDECREF(m_template);
	m_template = tmplate;
	Py_XINCREF(m_template);
}
