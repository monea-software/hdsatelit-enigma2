/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/service/listboxservice.h>
#include <lib/service/service.h>
#include <lib/gdi/font.h>
#include <lib/gdi/epng.h>
#include <lib/dvb/epgcache.h>
#include <lib/dvb/pmt.h>
#include <lib/dvb/db.h>
#include <lib/python/connections.h>

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <sys/stat.h>

void eListboxServiceContent::addService(const eServiceReference &service, bool beforeCurrent)
{
	if (beforeCurrent && m_size)
		m_list.insert(m_cursor, service);
	else
		m_list.push_back(service);
	if (m_size++)
	{
		++m_cursor_number;
		if (m_listbox)
			m_listbox->entryAdded(m_cursor_number-1);
	}
	else
	{
		m_cursor = m_list.begin();
		m_cursor_number=0;
		m_listbox->entryAdded(0);
	}
}

void eListboxServiceContent::removeCurrent()
{
	if (m_size && m_listbox)
	{
		if (m_cursor_number == --m_size)
		{
			m_list.erase(m_cursor--);
			if (m_size)
			{
				--m_cursor_number;
				m_listbox->entryRemoved(m_cursor_number+1);
			}
			else
				m_listbox->entryRemoved(m_cursor_number);
		}
		else
		{
			m_list.erase(m_cursor++);
			m_listbox->entryRemoved(m_cursor_number);
		}
	}
}

void eListboxServiceContent::FillFinished()
{
	m_size = m_list.size();
	cursorHome();

	if (m_listbox)
		m_listbox->entryReset();
}

void eListboxServiceContent::setRoot(const eServiceReference &root, bool justSet)
{
	m_list.clear();
	m_picon_requests.clear();
	m_root = root;

	if (justSet)
	{
		m_lst=0;
		return;
	}
	ASSERT(m_service_center);
	
	if (m_service_center->list(m_root, m_lst))
		eDebug("no list available!");
	else if (m_lst->getContent(m_list))
		eDebug("getContent failed");

	FillFinished();
}

void eListboxServiceContent::setCurrent(const eServiceReference &ref)
{
	int index=0;
	for (list::iterator i(m_list.begin()); i != m_list.end(); ++i, ++index)
		if ( *i == ref )
		{
			m_cursor = i;
			m_cursor_number = index;
			break;
		}
	if (m_listbox)
		m_listbox->moveSelectionTo(index);
}

void eListboxServiceContent::getCurrent(eServiceReference &ref)
{
	if (cursorValid())
		ref = *m_cursor;
	else
		ref = eServiceReference();
}

int eListboxServiceContent::getNextBeginningWithChar(char c)
{
//	printf("Char: %c\n", c);
	int index=0;
	for (list::iterator i(m_list.begin()); i != m_list.end(); ++i, ++index)
	{
		std::string text;
		ePtr<iStaticServiceInformation> service_info;
		m_service_center->info(*i, service_info);
		service_info->getName(*i, text);
//		printf("%c\n", text.c_str()[0]);
		int idx=0;
		int len=text.length();
		while ( idx <= len )
		{
			char cc = text[idx++];
			if ( cc >= 33 && cc < 127)
			{
				if (cc == c)
					return index;
				break;
			}
		}
	}
	return 0;
}

int eListboxServiceContent::getPrevMarkerPos()
{
	if (!m_listbox)
		return 0;
	list::iterator i(m_cursor);
	int index = m_cursor_number;
	while (index)
	{
		--i;
		--index;
		if (i->flags & eServiceReference::isMarker)
			break;
	}
	return index;
}

int eListboxServiceContent::getNextMarkerPos()
{
	if (!m_listbox)
		return 0;
	list::iterator i(m_cursor);
	int index = m_cursor_number;
	while (index < (m_size-1))
	{
		++i;
		++index;
		if (i->flags & eServiceReference::isMarker)
			break;
	}
	return index;
}

void eListboxServiceContent::initMarked()
{
	m_marked.clear();
}

void eListboxServiceContent::addMarked(const eServiceReference &ref)
{
	m_marked.insert(ref);
	if (m_listbox)
		m_listbox->entryChanged(lookupService(ref));
}

void eListboxServiceContent::removeMarked(const eServiceReference &ref)
{
	m_marked.erase(ref);
	if (m_listbox)
		m_listbox->entryChanged(lookupService(ref));
}

int eListboxServiceContent::isMarked(const eServiceReference &ref)
{
	return m_marked.find(ref) != m_marked.end();
}

/* the whole list is repainted (as setIgnoreService does): lookupService does not search, so entryChanged would not
   find the row */
void eListboxServiceContent::clearRecorded()
{
	if (m_recorded.empty())
		return;
	m_recorded.clear();
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

void eListboxServiceContent::addRecorded(const eServiceReference &ref)
{
	if (!m_recorded.insert(ref).second)
		return;
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

int eListboxServiceContent::isRecorded(const eServiceReference &ref)
{
	return m_recorded.find(ref) != m_recorded.end();
}

/* like the recorded services: the whole list is repainted when the set changes */
void eListboxServiceContent::clearStreamed()
{
	if (m_streamed.empty())
		return;
	m_streamed.clear();
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

void eListboxServiceContent::addStreamed(const eServiceReference &ref)
{
	if (!m_streamed.insert(ref).second)
		return;
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

int eListboxServiceContent::isStreamed(const eServiceReference &ref)
{
	return m_streamed.find(ref) != m_streamed.end();
}

void eListboxServiceContent::setStreamedLabel(const std::string &label)
{
	if (m_streamed_label == label)
		return;
	m_streamed_label = label;
	if (!m_streamed.empty() && m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

void eListboxServiceContent::markedQueryStart()
{
	m_marked_iterator = m_marked.begin();
}

int eListboxServiceContent::markedQueryNext(eServiceReference &ref)
{
	if (m_marked_iterator == m_marked.end())
		return -1;
	ref = *m_marked_iterator++;
	return 0;
}

int eListboxServiceContent::lookupService(const eServiceReference &ref)
{
		/* shortcut for cursor */
	if (ref == *m_cursor)
		return m_cursor_number;
		/* otherwise, search in the list.. */
	int index = 0;
	for (list::const_iterator i(m_list.begin()); i != m_list.end(); ++i, ++index);
	
		/* this is ok even when the index was not found. */
	return index;
}

void eListboxServiceContent::setVisualMode(int mode)
{
	for (int i=0; i < celElements; ++i)
	{
		m_element_position[i] = eRect();
		m_element_font[i] = 0;
	}

	m_visual_mode = mode;

	if (m_visual_mode == visModeSimple)
	{
		m_element_position[celServiceName] = eRect(ePoint(0, 0), m_itemsize);
		m_element_font[celServiceName] = new gFont("Regular", 23);
	}
}

void eListboxServiceContent::setElementPosition(int element, eRect where)
{
	if ((element >= 0) && (element < celElements))
		m_element_position[element] = where;
}

void eListboxServiceContent::setElementFont(int element, gFont *font)
{
	if ((element >= 0) && (element < celElements))
		m_element_font[element] = font;
}

void eListboxServiceContent::setPixmap(int type, ePtr<gPixmap> &pic)
{
	if ((type >=0) && (type < picElements))
		m_pixmaps[type] = pic;
}

void eListboxServiceContent::sort()
{
	if (!m_lst)
		m_service_center->list(m_root, m_lst);
	if (m_lst)
	{
		m_list.sort(iListableServiceCompare(m_lst));
			/* FIXME: is this really required or can we somehow keep the current entry? */
		cursorHome();
		if (m_listbox)
			m_listbox->entryReset();
	}
}

DEFINE_REF(eListboxServiceContent);

eListboxServiceContent::eListboxServiceContent()
	:m_visual_mode(visModeSimple), m_progressbar_height(6), m_progressbar_border_width(1), m_size(0), m_current_marked(false), m_numberoffset(0), m_itemheight(25), m_service_marks(0), m_picons_enabled(false), m_picon_clock(0)
{
	memset(m_color_set, 0, sizeof(m_color_set));
	cursorHome();
	eServiceCenter::getInstance(m_service_center);
}

void eListboxServiceContent::addPiconPath(const std::string &path)
{
	if (!path.empty() && m_picon_paths.size() < 10 && std::find(m_picon_paths.begin(), m_picon_paths.end(), path) == m_picon_paths.end())
		m_picon_paths.push_back(path.back() == '/' ? path : path + '/');
}

void eListboxServiceContent::setPiconsEnabled(bool enabled)
{
	if (m_picons_enabled == enabled)
		return;
	m_picons_enabled = enabled;
	invalidatePicons();
}

void eListboxServiceContent::invalidatePicons()
{
	m_picon_cache.clear();
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

std::string eListboxServiceContent::takePiconRequests()
{
	std::string result;
	for (const auto &ref : m_picon_requests)
		result += ref + '\n';
	m_picon_requests.clear();
	return result;
}

/* The native decoders allocate their surface before returning. Check the file header FIRST,
   also for manually installed picons: a small compressed image can claim a huge surface. */
static bool hdsSmallPicon(const std::string &file, bool png)
{
	FILE *in = fopen(file.c_str(), "rb");
	if (!in)
		return false;
	unsigned char b[24];
	bool valid = false;
	if (png)
	{
		if (fread(b, 1, sizeof(b), in) == sizeof(b) && !memcmp(b, "\x89PNG\r\n\x1a\n", 8)
			&& b[8] == 0 && b[9] == 0 && b[10] == 0 && b[11] == 13 && !memcmp(b + 12, "IHDR", 4))
		{
			unsigned long w = ((unsigned long)b[16] << 24) | ((unsigned long)b[17] << 16) | (b[18] << 8) | b[19];
			unsigned long h = ((unsigned long)b[20] << 24) | ((unsigned long)b[21] << 16) | (b[22] << 8) | b[23];
			valid = w && h && w <= 512 && h <= 512;
		}
	}
	else if (fread(b, 1, 2, in) == 2 && b[0] == 255 && b[1] == 0xd8)
	{
		while (ftell(in) >= 0 && ftell(in) < 256 * 1024)
		{
			if (fgetc(in) != 255)
				break;
			int marker;
			do { marker = fgetc(in); } while (marker == 255);
			if (marker <= 0 || marker == 0xda || marker == 0xd9 || fread(b, 1, 2, in) != 2)
				break;
			int length = (b[0] << 8) | b[1];
			if (length < 2)
				break;
			if (marker == 0xc0 || marker == 0xc1 || marker == 0xc2)
			{
				if (length >= 8 && fread(b, 1, 6, in) == 6)
				{
					int h = (b[1] << 8) | b[2], w = (b[3] << 8) | b[4];
					valid = b[0] == 8 && (b[5] == 1 || b[5] == 3) && w > 0 && h > 0 && w <= 512 && h <= 512;
				}
				break;
			}
			if ((marker >= 0xc0 && marker <= 0xcf && marker != 0xc4 && marker != 0xc8 && marker != 0xcc)
				|| fseek(in, length - 2, SEEK_CUR))
				break;
		}
	}
	fclose(in);
	return valid;
}

ePtr<gPixmap> eListboxServiceContent::servicePicon(const eServiceReference &ref)
{
	ePtr<gPixmap> pic;
	if (!m_picons_enabled || ref.flags & (eServiceReference::isDirectory | eServiceReference::isMarker))
		return pic;
	/* Capture actual painted rows, so alphabetic lists, Favorites and custom sorted lists all
	   request the right channels. Python drains these requests; paint itself never uses the network. */
	if ((ref.getUnsignedData(4) & 0xffff0000) == 0xfffe0000 && m_picon_requests.size() < 64)
		m_picon_requests.insert(ref.toString());
	std::string text = ref.toString(), base;
	std::vector<std::string> fields;
	size_t start = 0;
	for (int i = 0; i < 10; ++i)
	{
		size_t end = text.find(':', start);
		if (end == std::string::npos)
			return pic;
		fields.push_back(text.substr(start, end - start));
		start = end + 1;
	}
	auto makeName = [](const std::vector<std::string> &f) {
		std::string n;
		for (size_t i = 0; i < f.size(); ++i)
			n += (i ? "_" : "") + f[i];
		while (!n.empty() && n.back() == '_')
			n.pop_back();
		return n;
	};
	base = makeName(fields);
	auto cached = m_picon_cache.find(base);
	if (cached != m_picon_cache.end())
	{
		cached->second.second = ++m_picon_clock;
		return cached->second.first;
	}
	std::vector<std::string> names(1, base);
	if (fields[2] != "1" && fields[2] != "0")
	{
		auto f = fields;
		f[2] = "1";
		names.push_back(makeName(f));
	}
	if (fields[0] == "4097" || fields[0] == "5001" || fields[0] == "5002" || fields[0] == "5003" || fields[0] == "8193" || fields[0] == "8739")
	{
		fields[0] = "1";
		names.push_back(makeName(fields));
		fields[2] = "1";
		names.push_back(makeName(fields));
	}
	for (const auto &name : names)
	{
		for (const auto &path : m_picon_paths)
		{
			for (const char *ext : {".png", ".jpg"})
			{
				std::string file = path + name + ext;
				struct stat st;
				if (stat(file.c_str(), &st) || !S_ISREG(st.st_mode) || st.st_size <= 0 || st.st_size > 256 * 1024)
					continue;
				if (!hdsSmallPicon(file, ext[1] == 'p'))
					continue;
				if (ext[1] == 'p')
					loadPNG(pic, file.c_str());
				else
					loadJPG(pic, file.c_str());
				if (pic && (pic->size().width() > 512 || pic->size().height() > 512))
					pic = 0;
				if (pic)
					break;
			}
			if (pic)
				break;
		}
		if (pic)
			break;
	}
	/* At most 64 decoded logos (64 MiB for maximum-size RGBA files), including misses.
	   Evict one least-recently-used entry; no full cache flush while scrolling. */
	if (m_picon_cache.size() >= 64)
	{
		auto oldest = std::min_element(m_picon_cache.begin(), m_picon_cache.end(),
			[](const auto &a, const auto &b) { return a.second.second < b.second.second; });
		m_picon_cache.erase(oldest);
	}
	m_picon_cache[base] = std::make_pair(pic, ++m_picon_clock);
	return pic;
}

void eListboxServiceContent::setPathLabel(const std::string &marker, const std::string &label)
{
	if (marker.empty())
		return;
	for (std::vector<std::pair<std::string, std::string> >::iterator i = m_path_labels.begin(); i != m_path_labels.end(); ++i)
	{
		if (i->first == marker)
		{
			i->second = label;
			return;
		}
	}
	m_path_labels.push_back(std::make_pair(marker, label));
}

void eListboxServiceContent::clearPathLabels()
{
	m_path_labels.clear();
}

void eListboxServiceContent::setServiceMarks(int marks, const std::string &crypted, const std::string &satellite,
	const std::string &cable, const std::string &terrestrial)
{
	if (marks == m_service_marks && crypted == m_mark_crypted && satellite == m_mark_satellite && cable == m_mark_cable
		&& terrestrial == m_mark_terrestrial)
		return;
	m_service_marks = marks;
	m_mark_crypted = crypted;
	m_mark_satellite = satellite;
	m_mark_cable = cable;
	m_mark_terrestrial = terrestrial;
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

/* the marks of a DVB service row (setServiceMarks), "" for anything else: read from the service database at paint
   time, so CAIDs learned at a zap show at once */
std::string eListboxServiceContent::serviceMarks(const eServiceReference &ref) const
{
	if (!m_service_marks || ref.type != eServiceReference::idDVB || !ref.path.empty())
		return "";
	std::string marks;
	if (m_service_marks & markCrypted)
	{
		ePtr<eDVBService> service;
		eDVBDB *db = eDVBDB::getInstance();
		if (db && !db->getService((const eServiceReferenceDVB&)ref, service) && service &&
			(!service->m_ca.empty() || (service->m_flags & eDVBService::dxIsScrambledPMT)))
			marks = m_mark_crypted;
	}
	if (m_service_marks & markSource)
	{
		unsigned int orbpos = ref.getUnsignedData(4) >> 16;
		const std::string &source = (orbpos == 0xFFFF) ? m_mark_cable : (orbpos == 0xEEEE) ? m_mark_terrestrial :
			m_mark_satellite;
		if (!source.empty())
			marks += (marks.empty() ? "" : "  ") + source;
	}
	return marks;
}

/* like the streamed services: the list is repainted when a label changes */
void eListboxServiceContent::setRefLabel(const eServiceReference &ref, const std::string &label)
{
	std::map<eServiceReference, std::string>::iterator i = m_ref_labels.find(ref);
	if (label.empty())
	{
		if (i == m_ref_labels.end())
			return;
		m_ref_labels.erase(i);
	}
	else if (i != m_ref_labels.end())
	{
		if (i->second == label)
			return;
		i->second = label;
	}
	else
		m_ref_labels[ref] = label;
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

/* the operator's number of a service (the list of a cable network): drawn in the number column instead of the place */
void eListboxServiceContent::setRefNumber(const eServiceReference &ref, int number)
{
	std::map<eServiceReference, int>::iterator i = m_ref_numbers.find(ref);
	if (number <= 0)
	{
		if (i == m_ref_numbers.end())
			return;
		m_ref_numbers.erase(i);
	}
	else if (i != m_ref_numbers.end())
	{
		if (i->second == number)
			return;
		i->second = number;
	}
	else
		m_ref_numbers[ref] = number;
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

void eListboxServiceContent::clearRefNumbers()
{
	if (m_ref_numbers.empty())
		return;
	m_ref_numbers.clear();
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

void eListboxServiceContent::clearRefLabels()
{
	if (m_ref_labels.empty())
		return;
	m_ref_labels.clear();
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

std::string eListboxServiceContent::pathLabel(const eServiceReference &ref) const
{
	if (m_path_labels.empty() || ref.path.empty())
		return std::string();
	for (std::vector<std::pair<std::string, std::string> >::const_iterator i = m_path_labels.begin(); i != m_path_labels.end(); ++i)
		if (ref.path.find(i->first) != std::string::npos)
			return i->second;
	return std::string();
}

void eListboxServiceContent::setProgressbarHeight(int height)
{
	m_progressbar_height = height > 0 ? height : 6;
}

void eListboxServiceContent::setProgressbarBorderWidth(int width)
{
	m_progressbar_border_width = width >= 0 ? width : 1;
}

void eListboxServiceContent::setColor(int color, gRGB &col)
{
	if ((color >= 0) && (color < colorElements))
	{
		m_color_set[color] = true;
		m_color[color] = col;
	}
}

void eListboxServiceContent::cursorHome()
{
	if (m_current_marked && m_saved_cursor == m_list.end())
	{
		if (m_cursor_number >= m_size)
		{
			m_cursor_number = m_size-1;
			--m_cursor;
		}
		while (m_cursor_number)
		{
			std::iter_swap(m_cursor--, m_cursor);
			--m_cursor_number;
			if (m_listbox && m_cursor_number)
				m_listbox->entryChanged(m_cursor_number);
		}
	}
	else
	{
		m_cursor = m_list.begin();
		m_cursor_number = 0;
	}
}

void eListboxServiceContent::cursorEnd()
{
	if (m_current_marked && m_saved_cursor == m_list.end())
	{
		while (m_cursor != m_list.end())
		{
			list::iterator prev = m_cursor++;
			++m_cursor_number;
			if ( prev != m_list.end() && m_cursor != m_list.end() )
			{
				std::iter_swap(m_cursor, prev);
				if ( m_listbox )
					m_listbox->entryChanged(m_cursor_number);
			}
		}
	}
	else
	{
		m_cursor = m_list.end();
		m_cursor_number = m_size;
	}
}

int eListboxServiceContent::setCurrentMarked(bool state)
{
	bool prev = m_current_marked;
	m_current_marked = state;

	if (state != prev && m_listbox)
	{
		m_listbox->entryChanged(m_cursor_number);
		if (!state)
		{
			if (!m_lst)
				m_service_center->list(m_root, m_lst);
			if (m_lst)
			{
				ePtr<iMutableServiceList> list;
				if (m_lst->startEdit(list))
					eDebug("no editable list");
				else
				{
					eServiceReference ref;
					getCurrent(ref);
					if(!ref)
						eDebug("no valid service selected");
					else
					{
						int pos = cursorGet();
						eDebugNoNewLine("move %s to %d ", ref.toString().c_str(), pos);
						if (list->moveService(ref, cursorGet()))
							eDebug("failed");
						else
							eDebug("ok");
					}
				}
			}
			else
				eDebug("no list available!");
		}
	}

	return 0;
}

int eListboxServiceContent::cursorMove(int count)
{
	int prev = m_cursor_number, last = m_cursor_number + count;
	if (count > 0)
	{
		while(count && m_cursor != m_list.end())
		{
			list::iterator prev_it = m_cursor++;
			if ( m_current_marked && m_cursor != m_list.end() && m_saved_cursor == m_list.end() )
			{
				std::iter_swap(prev_it, m_cursor);
				if ( m_listbox && prev != m_cursor_number && last != m_cursor_number )
					m_listbox->entryChanged(m_cursor_number);
			}
			++m_cursor_number;
			--count;
	}
	} else if (count < 0)
	{
		while (count && m_cursor != m_list.begin())
		{
			list::iterator prev_it = m_cursor--;
			if ( m_current_marked && m_cursor != m_list.end() && prev_it != m_list.end() && m_saved_cursor == m_list.end() )
			{
				std::iter_swap(prev_it, m_cursor);
				if ( m_listbox && prev != m_cursor_number && last != m_cursor_number )
					m_listbox->entryChanged(m_cursor_number);
			}
			--m_cursor_number;
			++count;
		}
	}
	return 0;
}

int eListboxServiceContent::cursorValid()
{
	return m_cursor != m_list.end();
}

int eListboxServiceContent::cursorSet(int n)
{
	cursorHome();
	cursorMove(n);
	return 0;
}

int eListboxServiceContent::cursorGet()
{
	return m_cursor_number;
}

void eListboxServiceContent::cursorSave()
{
	m_saved_cursor = m_cursor;
	m_saved_cursor_number = m_cursor_number;
}

void eListboxServiceContent::cursorRestore()
{
	m_cursor = m_saved_cursor;
	m_cursor_number = m_saved_cursor_number;
	m_saved_cursor = m_list.end();
}

int eListboxServiceContent::size()
{
	return m_size;
}
	
void eListboxServiceContent::setSize(const eSize &size)
{
	m_itemsize = size;
	if (m_visual_mode == visModeSimple)
		setVisualMode(m_visual_mode);
}

void eListboxServiceContent::paint(gPainter &painter, eWindowStyle &style, const ePoint &offset, int selected)
{
	painter.clip(eRect(offset, m_itemsize));

	int marked = 0;

	if (m_current_marked && selected)
		marked = 2;
	else if (cursorValid() && isMarked(*m_cursor))
	{
		if (selected)
			marked = 2;
		else
			marked = 1;
	}
	else
		style.setStyle(painter, selected ? eWindowStyle::styleListboxSelected : eWindowStyle::styleListboxNormal);

	eListboxStyle *local_style = 0;

		/* get local listbox style, if present */
	if (m_listbox)
		local_style = m_listbox->getLocalStyle();

	if (marked == 1)  // marked
	{
		style.setStyle(painter, eWindowStyle::styleListboxMarked);
		if (m_color_set[markedForeground])
			painter.setForegroundColor(m_color[markedForeground]);
		if (m_color_set[markedBackground])
			painter.setBackgroundColor(m_color[markedBackground]);
	}
	else if (marked == 2) // marked and selected
	{
		style.setStyle(painter, eWindowStyle::styleListboxMarkedAndSelected);
		if (m_color_set[markedForegroundSelected])
			painter.setForegroundColor(m_color[markedForegroundSelected]);
		if (m_color_set[markedBackgroundSelected])
			painter.setBackgroundColor(m_color[markedBackgroundSelected]);
	}
	else if (local_style)
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
		if (local_style && local_style->m_background)
			painter.blit(local_style->m_background, offset, eRect(), 0);
		else
			painter.clear();
	} else
	{
		if (local_style->m_background)
			painter.blit(local_style->m_background, offset, eRect(), gPainter::BT_ALPHATEST);
		else if (selected && !local_style->m_selection)
			painter.clear();
	}

	if (cursorValid())
	{
			/* get service information */
		ePtr<iStaticServiceInformation> service_info;
		m_service_center->info(*m_cursor, service_info);
		eServiceReference ref = *m_cursor;
		bool isMarker = ref.flags & eServiceReference::isMarker;
		bool isPlayable = !(ref.flags & eServiceReference::isDirectory || isMarker);
		bool paintProgress = false;
		ePtr<eServiceEvent> evt;

		bool serviceAvail = true;
		bool notPlayable = false;

		if (!marked && isPlayable && service_info && m_is_playable_ignore.valid())
		{
			/* the question is whether the live service could switch to this service: network streams that stop for it
			   do not keep the service grey (lib/dvb/hdscedare.h) */
			eDVBZapQuery zap_query;
			notPlayable = !service_info->isPlayable(*m_cursor, m_is_playable_ignore);
		}
		if (notPlayable)
		{
			if (m_color_set[serviceNotAvail])
				painter.setForegroundColor(m_color[serviceNotAvail]);
			else
				painter.setForegroundColor(gRGB(0xbbbbbb));
			serviceAvail = false;
		}
		/* a service being recorded now: number and name in the recording color; the selected row keeps its colors,
		   readable on the selection */
		else if (!marked && !selected && isPlayable && m_color_set[serviceRecorded] && isRecorded(ref))
			painter.setForegroundColor(m_color[serviceRecorded]);

		if (selected && local_style && local_style->m_selection)
			painter.blit(local_style->m_selection, offset, eRect(), gPainter::BT_ALPHATEST);

		/* a service streamed to the network now (addStreamed): its mark at the right end of the row, the pixmap
		   picStreamed and the text of setStreamedLabel; the path label (if any) moves to its left */
		ePtr<eTextPara> mark_para;
		int mark_width = 0, mark_right = 0, mark_pixmap_width = 0;
		if (isPlayable && m_visual_mode == visModeComplex && isStreamed(ref))
		{
			const eRect &row = m_element_position[celServiceName];
			mark_right = row.left() + row.width();
			if (m_itemsize.width() > 0 && m_itemsize.width() < mark_right)
				mark_right = m_itemsize.width();
			if (m_pixmaps[picStreamed])
				mark_pixmap_width = m_pixmaps[picStreamed]->size().width();
			int text_width = 0;
			if (!m_streamed_label.empty() && m_element_font[celServiceInfo])
			{
				mark_para = new eTextPara(eRect(0, 0, m_itemsize.width(), m_itemsize.height()));
				mark_para->setFont(m_element_font[celServiceInfo]);
				mark_para->renderString(m_streamed_label.c_str());
				text_width = mark_para->getBoundBox().width();
			}
			if (mark_pixmap_width || text_width)
				mark_width = mark_pixmap_width + (mark_pixmap_width && text_width ? 6 : 0) + text_width + 16;
		}

		/* label of a service by its path (setPathLabel): kept free at the right end of the row; the row ends where the
		   item ends (m_itemsize: without the scrollbar), even if the name area is wider */
		std::string label;
		int label_width = 0, label_right = 0;
		if (isPlayable && m_visual_mode == visModeComplex && m_element_font[celServiceInfo])
		{
			std::map<eServiceReference, std::string>::const_iterator rl = m_ref_labels.find(ref);
			label = rl != m_ref_labels.end() ? rl->second : pathLabel(ref);
			if (label.empty())
				label = serviceMarks(ref);
			if (!label.empty())
			{
				ePtr<eTextPara> measure = new eTextPara(eRect(0, 0, m_itemsize.width(), m_itemsize.height()));
				measure->setFont(m_element_font[celServiceInfo]);
				measure->renderString(label.c_str());
				label_width = measure->getBoundBox().width() + 16;
				const eRect &row = m_element_position[celServiceName];
				label_right = row.left() + row.width();
				if (m_itemsize.width() > 0 && m_itemsize.width() < label_right)
					label_right = m_itemsize.width();
				label_right -= mark_width;
			}
		}
		/* where the labels at the right end of the row begin (0: none) */
		int labels_left = label_width ? label_right - label_width : (mark_width ? mark_right - mark_width : 0);

		int xoffset=0;  // used as offset when painting the folder/marker symbol or the serviceevent progress
		ePtr<gPixmap> service_picon;
		if (isPlayable && m_visual_mode == visModeComplex)
			service_picon = servicePicon(ref);

		for (int e = 0; e < celElements; ++e)
		{
			if (m_element_font[e])
			{
				int flags=gPainter::RT_VALIGN_CENTER,
					yoffs = 0,
					xoffs = xoffset;
				eRect &area = m_element_position[e];
				std::string text = "<n/a>";
				int reserved = 0;  // width kept free at the right for the label
				xoffset=0;

				switch (e)
				{
				case celServiceNumber:
				{
					if (m_cursor->flags & eServiceReference::isMarker)
						continue;
					char bla[12];
					if (!m_ref_numbers.empty())
					{
						/* the operator's numbers (setRefNumber): the number of the service, an empty cell without one */
						std::map<eServiceReference, int>::const_iterator rn = m_ref_numbers.find(*m_cursor);
						if (rn == m_ref_numbers.end())
							continue;
						snprintf(bla, sizeof(bla), "%d", rn->second);
						text = bla;
						flags|=gPainter::RT_HALIGN_RIGHT;
						break;
					}
				/* how we can do this better? :) */
					int markers_before=0;
					{
						list::iterator tmp=m_cursor;
						while(tmp != m_list.begin())
						{
							--tmp;
							if (tmp->flags & eServiceReference::isMarker)
								++markers_before;
						}
					}
					sprintf(bla, "%d", m_numberoffset + m_cursor_number + 1 - markers_before);
					text = bla;
					flags|=gPainter::RT_HALIGN_RIGHT;
					break;
				}
				case celServiceName:
				{
					if (service_picon && area.height() > 4)
					{
						int slot = std::min(96, area.height() * 2), h = area.height() - 4;
						int w = std::max(1, service_picon->size().width() * h / std::max(1, service_picon->size().height()));
						if (w > slot)
						{
							h = std::max(1, h * slot / w);
							w = slot;
						}
						eRect where(area.left() + xoffs + (slot - w) / 2, area.top() + (area.height() - h) / 2, w, h);
						where.moveBy(offset);
						painter.blitScale(service_picon, where, eRect(), gPainter::BT_ALPHABLEND);
						xoffs += slot + 8;
					}
					if (service_info)
						service_info->getName(*m_cursor, text);
					if (labels_left)
						reserved = std::max(0, area.left() + area.width() - labels_left);
					break;
				}
				case celServiceInfo:
				{
					bool has_event = isPlayable && service_info && !service_info->getEvent(*m_cursor, evt) && !evt->getEventName().empty();
					if (!has_event && label.empty())
						continue;
					if (serviceAvail)
					{
						if (!selected && m_color_set[serviceDescriptionColor])
							painter.setForegroundColor(m_color[serviceDescriptionColor]);
						else if (selected && m_color_set[serviceDescriptionColorSelected])
							painter.setForegroundColor(m_color[serviceDescriptionColorSelected]);
					}
					if (!label.empty())
					{
						/* right end of the row, vertically centered */
						eRect where(label_right - label_width + 16, area.top(), label_width - 16, area.height());
						ePtr<eTextPara> lpara = new eTextPara(where);
						lpara->setFont(m_element_font[e]);
						lpara->renderString(label.c_str());
						lpara->realign(eTextPara::dirRight);
						eRect lbox = lpara->getBoundBox();
						painter.renderPara(lpara, offset + ePoint(0, (area.height() - lbox.height()) / 2 - lbox.top()));
						if (!has_event)
							continue;
					}
					if (labels_left)
						reserved = std::max(0, area.left() + area.width() - labels_left);
					text = '(' + evt->getEventName() + ')';
					break;
				}
				}

				eRect tmp = area;
				tmp.setWidth(tmp.width()-xoffs-reserved);
				if (tmp.width() <= 0)
					continue;

				eTextPara *para = new eTextPara(tmp);
				para->setFont(m_element_font[e]);
				para->renderString(text.c_str());

				if (e == celServiceName)
				{
					eRect bbox = para->getBoundBox();
					int name_width = bbox.width()+8;
					m_element_position[celServiceInfo].setLeft(area.left()+name_width+xoffs);
					m_element_position[celServiceInfo].setTop(area.top());
					m_element_position[celServiceInfo].setWidth(area.width()-(name_width+xoffs));
					m_element_position[celServiceInfo].setHeight(area.height());
				}

					/* HDSatelit: a name or an event wider than its place is drawn from its beginning, cut cleanly at
					   the edge of the place, and scrolls on the selected row (eDerulare, lib/gui/elabel.h) */
				int overflow = para->getBoundBox().right() - tmp.right();
				if (overflow <= 1)
				{
					overflow = 0;
					if (flags & gPainter::RT_HALIGN_RIGHT)
						para->realign(eTextPara::dirRight);
					else if (flags & gPainter::RT_HALIGN_CENTER)
						para->realign(eTextPara::dirCenter);
					else if (flags & gPainter::RT_HALIGN_BLOCK)
						para->realign(eTextPara::dirBlock);
				}

				if (flags & gPainter::RT_VALIGN_CENTER)
				{
					eRect bbox = para->getBoundBox();
					int vcentered_top = (area.height() - bbox.height()) / 2;
					yoffs = vcentered_top - bbox.top();
				}

				if (overflow)
				{
					int dx = (selected && m_listbox) ? m_listbox->selectedRowScroller()->shift(overflow) : 0;
					painter.clip(eRect(offset.x() + xoffs + tmp.left(), offset.y() + tmp.top(), tmp.width(), tmp.height()));
					painter.renderPara(para, offset + ePoint(xoffs - dx, yoffs));
					painter.clippop();
				}
				else
					painter.renderPara(para, offset+ePoint(xoffs, yoffs));
			}
			else if (e == celServiceTypePixmap || e == celFolderPixmap || e == celMarkerPixmap)
			{
				int orbpos = m_cursor->getUnsignedData(4) >> 16;
				ePtr<gPixmap> &pixmap =
					(e == celFolderPixmap) ? m_pixmaps[picFolder] :
					(e == celMarkerPixmap) ? m_pixmaps[picMarker] :
					(m_cursor->flags & eServiceReference::isGroup) ? m_pixmaps[picServiceGroup] :
					(orbpos == 0xFFFF) ? m_pixmaps[picDVB_C] :
					(orbpos == 0xEEEE) ? m_pixmaps[picDVB_T] : m_pixmaps[picDVB_S];
				if (pixmap)
				{
					eSize pixmap_size = pixmap->size();
					int p = celServiceInfo;
					if (e == celFolderPixmap)
						p = celServiceName;
					else if (e == celMarkerPixmap)
						p = celServiceNumber;
					eRect area = m_element_position[p];
					int correction = (area.height() - pixmap_size.height()) / 2;

					if (isPlayable)
					{
						if (e != celServiceTypePixmap)
							continue;
						m_element_position[celServiceInfo] = area;
						m_element_position[celServiceInfo].setLeft(area.left() + pixmap_size.width() + 8);
						m_element_position[celServiceInfo].setWidth(area.width() - pixmap_size.width() - 8);
					}
					else if (m_cursor->flags & eServiceReference::isDirectory)
					{
						if (e != celFolderPixmap)
							continue;
						xoffset = pixmap_size.width() + 8;
					}
					else if (m_cursor->flags & eServiceReference::isMarker)
					{
						if (e != celMarkerPixmap)
							continue;
					}
					else
						eFatal("unknown service type in listboxservice");

					area.moveBy(offset);
					painter.clip(area);
					painter.blit(pixmap, offset+ePoint(area.left(), correction), area, gPainter::BT_ALPHATEST);
					painter.clippop();
				}
			}
			else if (e == celServiceEventProgressbar)
			{
				eRect area = m_element_position[celServiceEventProgressbar];
				if (area.width() > 0 && (isPlayable || isMarker))
				{
					// we schedule it to paint it as last element.. so we dont need to reset fore/background color
					paintProgress = isPlayable;
					xoffset = area.width() + 10;
				}
			}
		}
		if (mark_width)
		{
			int x = mark_right - mark_width + 16;
			if (mark_pixmap_width)
			{
				ePtr<gPixmap> &pixmap = m_pixmaps[picStreamed];
				painter.blit(pixmap, offset + ePoint(x, (m_itemsize.height() - pixmap->size().height()) / 2), eRect(), gPainter::BT_ALPHABLEND);
				x += mark_pixmap_width + 6;
			}
			if (mark_para)
			{
				int color = selected ? serviceStreamedSelected : serviceStreamed;
				if (m_color_set[color])
					painter.setForegroundColor(m_color[color]);
				eRect box = mark_para->getBoundBox();
				painter.renderPara(mark_para, offset + ePoint(x - box.left(), (m_itemsize.height() - box.height()) / 2 - box.top()));
			}
		}
		if (selected && (!local_style || !local_style->m_selection))
			style.drawFrame(painter, eRect(offset, m_itemsize), eWindowStyle::frameListboxEntry);
		if (paintProgress && evt)
		{
			eRect area = m_element_position[celServiceEventProgressbar];
			if (!selected && m_color_set[serviceEventProgressbarBorderColor])
				painter.setForegroundColor(m_color[serviceEventProgressbarBorderColor]);
			else if (selected && m_color_set[serviceEventProgressbarBorderColorSelected])
				painter.setForegroundColor(m_color[serviceEventProgressbarBorderColorSelected]);

			int border = m_progressbar_border_width;
			int progressH = m_progressbar_height;
			int progressX = area.left() + offset.x();
			int progressW = area.width() - 2 * border;
			int progressT = offset.y() + (m_itemsize.height() - progressH - 2*border) / 2;

			// paint progressbar frame
			painter.fill(eRect(progressX, progressT, area.width(), border));
			painter.fill(eRect(progressX, progressT + border, border, progressH));
			painter.fill(eRect(progressX, progressT + progressH + border, area.width(), border));
			painter.fill(eRect(progressX + area.width() - border, progressT + border, border, progressH));

			// calculate value
			time_t now = time(0);
			/* an event without duration must not divide by zero; the value stays inside the bar */
			int duration = evt->getDuration();
			int value = duration > 0 ? (int)(progressW * (now - evt->getBeginTime()) / duration) : 0;
			if (value < 0)
				value = 0;
			else if (value > progressW)
				value = progressW;

			eRect tmp = eRect(progressX + border, progressT + border, value, progressH);
			ePtr<gPixmap> &pixmap = m_pixmaps[picServiceEventProgressbar];
			if (pixmap)
			{
				area.moveBy(offset);
				painter.clip(area);
				painter.blit(pixmap, ePoint(progressX + border, progressT + border), tmp, gPainter::BT_ALPHATEST);
				painter.clippop();
			}
			else
			{
				if (!selected && m_color_set[serviceEventProgressbarColor])
					painter.setForegroundColor(m_color[serviceEventProgressbarColor]);
				else if (selected && m_color_set[serviceEventProgressbarColorSelected])
					painter.setForegroundColor(m_color[serviceEventProgressbarColorSelected]);
				painter.fill(tmp);
			}
		}
	}
	painter.clippop();
}

void eListboxServiceContent::setIgnoreService( const eServiceReference &service )
{
	m_is_playable_ignore=service;
	if (m_listbox && m_listbox->isVisible())
		m_listbox->invalidate();
}

void eListboxServiceContent::setItemHeight(int height)
{
	m_itemheight = height;
	if (m_listbox)
		m_listbox->setItemHeight(height);
}
