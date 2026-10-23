# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .HTMLComponent import HTMLComponent
from .GUIComponent import GUIComponent

from enigma import eEPGCache, eListbox, eListboxPythonMultiContent, \
	RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, RT_VALIGN_CENTER


from time import localtime, time
from ServiceReference import ServiceReference
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
import skin
from skin import getListFont, hasListFont, getParameterFromSkin

# the titles of the rows go through the automatic translation of the guide (Components/HdsTraducereEpg.py, "Tradu
# EPG"): only the rows being drawn are built here, so only the visible rows are translated; the translation from
# memory or the original at once, and the list is drawn again when a translation arrives (hdsTraducereEpg)
try:
	from Components import HdsTraducereEpg as _E
except Exception:
	_E = None

# The rows are drawn here; the skin can set their look (defaults = the 2011 look):
#   <alias name="EPGList0"/>: font of the events and row height (HDSatelit name); on the widget, as other skins write it,
#   EventFontSingle= (one channel and similar events) and EventFontMulti= (all channels) replace that font
#   <alias name="EPGList1"/>: font of the start and end time in the list of all channels
#   <hdsparameters>: EPGListIcon (x,y,w,h of the timer clock; x from the start of its column, the text moves
#   right of it; in the list of all channels the clock sits at the right end of the channel column) and
#   EPGListProgress (the height of the progress bar, centered in the row), EPGListSingleColumns and
#   EPGListMultiColumns (left margin, width of the day or channel column, width of the time column, space between
#   columns) and EPGListImage (the timer clocks). With EPGList0 in the skin the texts are centered in the row.

EPG_TYPE_SINGLE = 0
EPG_TYPE_MULTI = 1
EPG_TYPE_SIMILAR = 2

class Rect:
	def __init__(self, x, y, width, height):
		self.__left = x
		self.__top = y
		self.__width = width
		self.__height = height

	def left(self):
		return self.__left

	def top(self):
		return self.__top

	def height(self):
		return self.__height

	def width(self):
		return self.__width

class EPGList(HTMLComponent, GUIComponent):
	def __init__(self, type=EPG_TYPE_SINGLE, selChangedCB=None, timer = None):
		self.days = (_("Mon"), _("Tue"), _("Wed"), _("Thu"), _("Fri"), _("Sat"), _("Sun"))
		self.timer = timer
		self.onSelChanged = [ ]
		if selChangedCB is not None:
			self.onSelChanged.append(selChangedCB)
		GUIComponent.__init__(self)
		self.type=type
		self.l = eListboxPythonMultiContent()
		font, height = getListFont("EPGList0", ("Regular", 22))
		self.l.setFont(0, font)
		self.l.setFont(1, getListFont("EPGList1", ("Regular", 16))[0])
		if height:
			self.l.setItemHeight(height)
		# with the fonts of the skin the texts are centered in the row
		self.valign = hasListFont("EPGList0") and RT_VALIGN_CENTER or 0
		if type == EPG_TYPE_SINGLE:
			self.l.setBuildFunc(self.buildSingleEntry)
		elif type == EPG_TYPE_MULTI:
			self.l.setBuildFunc(self.buildMultiEntry)
		else:
			assert(type == EPG_TYPE_SIMILAR)
			self.l.setBuildFunc(self.buildSimilarEntry)
		self.epgcache = eEPGCache.getInstance()
		# the timer clocks: <hdsparameters> EPGListImage ("...%s.png", %s = epgclock, epgclock_add, epgclock_pre,
		# epgclock_post, epgclock_prepost), else the 2011 ones
		def clock(key):
			return skin.getListPixmap("EPGListImage", key, resolveFilename(SCOPE_CURRENT_SKIN, 'skin_default/icons/%s.png' % key))
		self.clock_pixmap, from_skin = clock('epgclock')
		self.clock_type = from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST
		self.clock_add_pixmap = clock('epgclock_add')[0]
		self.clock_pre_pixmap = clock('epgclock_pre')[0]
		self.clock_post_pixmap = clock('epgclock_post')[0]
		self.clock_prepost_pixmap = clock('epgclock_prepost')[0]
		# the clock box (x from the start of its column) and the space it takes from the text
		(self.clock_x, self.clock_y, self.clock_w, self.clock_h), skinned = getParameterFromSkin("EPGListIcon", (0, 0, 21, 21))
		self.clock_skinned = skinned

	def getEventFromId(self, service, eventid):
		event = None
		if self.epgcache is not None and eventid is not None:
			event = self.epgcache.lookupEventId(service.ref, eventid)
		return event

	def getCurrentChangeCount(self):
		if self.type == EPG_TYPE_MULTI and self.l.getCurrentSelection() is not None:
			return self.l.getCurrentSelection()[0]
		return 0

	def getCurrent(self):
		idx=0
		if self.type == EPG_TYPE_MULTI:
			idx += 1
		tmp = self.l.getCurrentSelection()
		if tmp is None:
			return ( None, None )
		eventid = tmp[idx+1]
		service = ServiceReference(tmp[idx])
		event = self.getEventFromId(service, eventid)
		return ( event, service )

	def moveUp(self):
		self.instance.moveSelection(self.instance.moveUp)

	def moveDown(self):
		self.instance.moveSelection(self.instance.moveDown)

	def connectSelectionChanged(self, func):
		if not self.onSelChanged.count(func):
			self.onSelChanged.append(func)

	def disconnectSelectionChanged(self, func):
		self.onSelChanged.remove(func)

	def selectionChanged(self):
		for x in self.onSelChanged:
			if x is not None:
				x()
#				try:
#					x()
#				except: # FIXME!!!
#					print "FIXME in EPGList.selectionChanged"
#					pass

	GUI_WIDGET = eListbox

	def applySkin(self, desktop, parent):
		# the event font on the widget, with the names other skins use (the other attributes go to the list box)
		mine = self.type == EPG_TYPE_MULTI and "EventFontMulti" or "EventFontSingle"
		if self.skinAttributes is not None:
			attribs = [ ]
			for (attrib, value) in self.skinAttributes:
				if attrib in ("EventFontSingle", "EventFontMulti"):
					if attrib == mine:
						try:
							self.l.setFont(0, skin.parseFont(value, ((1, 1), (1, 1))))
						except Exception as e:
							skin.skinWarning("EPGList: %s=\"%s\" not applied (%s)" % (attrib, value, e))
				else:
					attribs.append((attrib, value))
			self.skinAttributes = attribs
		return GUIComponent.applySkin(self, desktop, parent)

	def hdsTraducereEpg(self):
		"""Components/HdsTraducereEpg.py: a translation arrived (or the original was asked for): draw the rows again"""
		if getattr(self, "instance", None) is not None:
			self.l.invalidate()

	def hdsTitle(self, name):
		if _E is None or not name:
			return name
		return _E.text("titlu", name, self, False)

	def postWidgetCreate(self, instance):
		instance.setWrapAround(True)
		instance.selectionChanged.get().append(self.selectionChanged)
		instance.setContent(self.l)

	def preWidgetRemove(self, instance):
		instance.selectionChanged.get().remove(self.selectionChanged)
		instance.setContent(None)

	def recalcEntrySize(self):
		esize = self.l.getItemSize()
		width = esize.width()
		height = esize.height()
		# the columns from <hdsparameters>: EPGListSingleColumns (one channel and similar events) and
		# EPGListMultiColumns (all channels) = left margin, width of the day or channel column, width of the time
		# column, space between columns; the last column takes the rest of the row. Without them: the 2011 split.
		if self.type == EPG_TYPE_MULTI:
			cols, skinned = getParameterFromSkin("EPGListMultiColumns", (0, 0, 0, 0))
		else:
			cols, skinned = getParameterFromSkin("EPGListSingleColumns", (0, 0, 0, 0))
		if skinned:
			left, w1, w2, gap = cols
			x2 = left + w1 + gap
			x3 = x2 + w2 + gap
			first, second, third = Rect(left, 0, w1, height), Rect(x2, 0, w2, height), Rect(x3, 0, max(0, width - x3 - left), height)
			if self.type == EPG_TYPE_MULTI:
				self.service_rect, self.start_end_rect, self.descr_rect = first, second, third
				progress, skinned = getParameterFromSkin("EPGListProgress", 0)
				if not (skinned and 0 < progress < height):
					progress = max(1, height - 8)
				self.progress_rect = Rect(x2, (height - progress) // 2, w2, progress)
			else:
				self.weekday_rect, self.datetime_rect = first, second
				if self.type == EPG_TYPE_SINGLE:
					self.descr_rect = third
				else:
					self.service_rect = third
		elif self.type == EPG_TYPE_SINGLE:
			self.weekday_rect = Rect(0, 0, width//20*2-10, height)
			self.datetime_rect = Rect(width//20*2, 0, width//20*5-15, height)
			self.descr_rect = Rect(width//20*7, 0, width//20*13, height)
		elif self.type == EPG_TYPE_MULTI:
			xpos = 0;
			w = width//10*3;
			self.service_rect = Rect(xpos, 0, w-10, height)
			xpos += w;
			w = width//10*2;
			self.start_end_rect = Rect(xpos, 0, w-10, height)
			progress, skinned = getParameterFromSkin("EPGListProgress", 0)
			if skinned and 0 < progress < height:
				self.progress_rect = Rect(xpos, (height - progress) // 2, w-10, progress)
			else:
				self.progress_rect = Rect(xpos, 4, w-10, height-8)
			xpos += w
			w = width//10*5;
			self.descr_rect = Rect(xpos, 0, width, height)
		else: # EPG_TYPE_SIMILAR
			self.weekday_rect = Rect(0, 0, width//20*2-10, height)
			self.datetime_rect = Rect(width//20*2, 0, width//20*5-15, height)
			self.service_rect = Rect(width//20*7, 0, width//20*13, height)

	def getClockPixmap(self, refstr, beginTime, duration, eventId):
		pre_clock = 1
		post_clock = 2
		clock_type = 0
		endTime = beginTime + duration
		for x in self.timer.timer_list:
			if x.service_ref.ref.toString() == refstr:
				if x.eit == eventId:
					return self.clock_pixmap
				beg = x.begin
				end = x.end
				if beginTime > beg and beginTime < end and endTime > end:
					clock_type |= pre_clock
				elif beginTime < beg and endTime > beg and endTime < end:
					clock_type |= post_clock
		if clock_type == 0:
			return self.clock_add_pixmap
		elif clock_type == pre_clock:
			return self.clock_pre_pixmap
		elif clock_type == post_clock:
			return self.clock_post_pixmap
		else:
			return self.clock_prepost_pixmap
		
	def getPixmapForEntry(self, service, eventId, beginTime, duration):
		rec=beginTime and (self.timer.isInTimer(eventId, beginTime, duration, service))
		if rec:
			clock_pic = self.getClockPixmap(service, beginTime, duration, eventId)
		else:
			clock_pic = None
		return (clock_pic, rec)

	def buildSingleEntry(self, service, eventId, beginTime, duration, EventName):
		EventName = self.hdsTitle(EventName)
		(clock_pic, rec) = self.getPixmapForEntry(service, eventId, beginTime, duration)
		r1=self.weekday_rect
		r2=self.datetime_rect
		r3=self.descr_rect
		t = localtime(beginTime)
		res = [
			None, # no private data needed
			(eListboxPythonMultiContent.TYPE_TEXT, r1.left(), r1.top(), r1.width(), r1.height(), 0, RT_HALIGN_RIGHT | self.valign, self.days[t[6]]),
			(eListboxPythonMultiContent.TYPE_TEXT, r2.left(), r2.top(), r2.width(), r1.height(), 0, RT_HALIGN_RIGHT | self.valign, "%02d.%02d, %02d:%02d"%(t[2],t[1],t[3],t[4]))
		]
		if rec:
			icon, tx, tw = self.clockAndText(r3, clock_pic)
			res.extend((
				icon,
				(eListboxPythonMultiContent.TYPE_TEXT, tx, r3.top(), tw, r3.height(), 0, RT_HALIGN_LEFT | self.valign, EventName)
			))
		else:
			res.append((eListboxPythonMultiContent.TYPE_TEXT, r3.left(), r3.top(), r3.width(), r3.height(), 0, RT_HALIGN_LEFT | self.valign, EventName))
		return res

	def clockAndText(self, rect, clock_pic):
		"""(the clock entry, x and width of the text) for a column that starts with the timer clock"""
		if self.clock_skinned:
			x, y, w, h = skin.centerPixmap((rect.left() + self.clock_x, rect.top() + self.clock_y, self.clock_w, self.clock_h), clock_pic)
			shift = self.clock_x + self.clock_w + 12
			return (self.clock_type, x, y, w, h, clock_pic), rect.left() + shift, max(0, rect.width() - shift)
		return (self.clock_type, rect.left(), rect.top(), 21, 21, clock_pic), rect.left() + 25, rect.width()

	def buildSimilarEntry(self, service, eventId, beginTime, service_name, duration):
		(clock_pic, rec) = self.getPixmapForEntry(service, eventId, beginTime, duration)
		r1=self.weekday_rect
		r2=self.datetime_rect
		r3=self.service_rect
		t = localtime(beginTime)
		res = [
			None,  # no private data needed
			(eListboxPythonMultiContent.TYPE_TEXT, r1.left(), r1.top(), r1.width(), r1.height(), 0, RT_HALIGN_RIGHT | self.valign, self.days[t[6]]),
			(eListboxPythonMultiContent.TYPE_TEXT, r2.left(), r2.top(), r2.width(), r1.height(), 0, RT_HALIGN_RIGHT | self.valign, "%02d.%02d, %02d:%02d"%(t[2],t[1],t[3],t[4]))
		]
		if rec:
			icon, tx, tw = self.clockAndText(r3, clock_pic)
			res.extend((
				icon,
				(eListboxPythonMultiContent.TYPE_TEXT, tx, r3.top(), tw, r3.height(), 0, RT_HALIGN_LEFT | self.valign, service_name)
			))
		else:
			res.append((eListboxPythonMultiContent.TYPE_TEXT, r3.left(), r3.top(), r3.width(), r3.height(), 0, RT_HALIGN_LEFT | self.valign, service_name))
		return res

	def buildMultiEntry(self, changecount, service, eventId, beginTime, duration, EventName, nowTime, service_name):
		EventName = self.hdsTitle(EventName)
		(clock_pic, rec) = self.getPixmapForEntry(service, eventId, beginTime, duration)
		r1=self.service_rect
		r2=self.progress_rect
		r3=self.descr_rect
		r4=self.start_end_rect
		res = [ None ] # no private data needed
		if rec:
			if self.clock_skinned:
				# the clock at the right end of the channel column, the name stops before it
				tw = max(0, r1.width() - self.clock_w - 8)
				x, y, w, h = skin.centerPixmap((r1.left() + r1.width() - self.clock_w, r1.top() + self.clock_y, self.clock_w, self.clock_h), clock_pic)
			else:
				tw = r1.width()-21
				x, y, w, h = r1.left()+r1.width()-16, r1.top(), 21, 21
			res.extend((
				(eListboxPythonMultiContent.TYPE_TEXT, r1.left(), r1.top(), tw, r1.height(), 0, RT_HALIGN_LEFT | self.valign, service_name),
				(self.clock_type, x, y, w, h, clock_pic)
			))
		else:
			res.append((eListboxPythonMultiContent.TYPE_TEXT, r1.left(), r1.top(), r1.width(), r1.height(), 0, RT_HALIGN_LEFT | self.valign, service_name))
		if beginTime is not None:
			if nowTime < beginTime:
				begin = localtime(beginTime)
				end = localtime(beginTime+duration)
#				print "begin", begin
#				print "end", end
				res.extend((
					(eListboxPythonMultiContent.TYPE_TEXT, r4.left(), r4.top(), r4.width(), r4.height(), 1, RT_HALIGN_CENTER|RT_VALIGN_CENTER, "%02d.%02d - %02d.%02d"%(begin[3],begin[4],end[3],end[4])),
					(eListboxPythonMultiContent.TYPE_TEXT, r3.left(), r3.top(), r3.width(), r3.height(), 0, RT_HALIGN_LEFT | self.valign, EventName)
				))
			else:
				percent = int((nowTime - beginTime) * 100 / duration)
				res.extend((
					(eListboxPythonMultiContent.TYPE_PROGRESS, r2.left(), r2.top(), r2.width(), r2.height(), percent),
					(eListboxPythonMultiContent.TYPE_TEXT, r3.left(), r3.top(), r3.width(), r3.height(), 0, RT_HALIGN_LEFT | self.valign, EventName)
				))
		return res

	def queryEPG(self, list, buildFunc=None):
		if self.epgcache is not None:
			if buildFunc is not None:
				return self.epgcache.lookupEvent(list, buildFunc)
			else:
				return self.epgcache.lookupEvent(list)
		return [ ]

	def fillMultiEPG(self, services, stime=-1):
		#t = time()
		test = [ (service.ref.toString(), 0, stime) for service in services ]
		test.insert(0, 'X0RIBDTCn')
		self.list = self.queryEPG(test)
		self.l.setList(self.list)
		#print time() - t
		self.selectionChanged()

	def updateMultiEPG(self, direction):
		#t = time()
		test = [ x[3] and (x[1], direction, x[3]) or (x[1], direction, 0) for x in self.list ]
		test.insert(0, 'XRIBDTCn')
		tmp = self.queryEPG(test)
		cnt=0
		for x in tmp:
			changecount = self.list[cnt][0] + direction
			if changecount >= 0:
				if x[2] is not None:
					self.list[cnt]=(changecount, x[0], x[1], x[2], x[3], x[4], x[5], x[6])
			cnt+=1
		self.l.setList(self.list)
		#print time() - t
		self.selectionChanged()

	def fillSingleEPG(self, service):
		#t = time()
		test = [ 'RIBDT', (service.ref.toString(), 0, -1, -1) ]
		self.list = self.queryEPG(test)
		self.l.setList(self.list)
		#print time() - t
		self.selectionChanged()

	def sortSingleEPG(self, type):
		list = self.list
		if list:
			event_id = self.getSelectedEventId()
			if type == 1:
				list.sort(key=lambda x: (x[4] and x[4].lower(), x[2]))
			else:
				assert(type == 0)
				list.sort(key=lambda x: x[2])
			self.l.invalidate()
			self.moveToEventId(event_id)

	def getSelectedEventId(self):
		x = self.l.getCurrentSelection()
		return x and x[1]

	def moveToService(self,serviceref):
		if not serviceref:
			return
		index = 0
		refstr = serviceref.toString()
		for x in self.list:
			if x[1] == refstr:
				self.instance.moveSelectionTo(index)
				break
			index += 1
			
	def moveToEventId(self, eventId):
		if not eventId:
			return
		index = 0
		for x in self.list:
			if x[1] == eventId:
				self.instance.moveSelectionTo(index)
				break
			index += 1

	def fillSimilarList(self, refstr, event_id):
		t = time()
	 # search similar broadcastings
		if event_id is None:
			return
		l = self.epgcache.search(('RIBND', 1024, eEPGCache.SIMILAR_BROADCASTINGS_SEARCH, refstr, event_id))
		if l and len(l):
			l.sort(key=lambda x: x[2])
		self.l.setList(l)
		self.selectionChanged()
		print(time() - t)
