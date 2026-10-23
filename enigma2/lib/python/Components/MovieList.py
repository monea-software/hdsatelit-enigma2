# Modificat de moneasoftware.com si hdsatelit.com, 2026
import struct
from .GUIComponent import GUIComponent
from Tools.FuzzyDate import FuzzyTime
from ServiceReference import ServiceReference
from Components.MultiContent import MultiContentEntryText
from Components.config import config
from Components import HdsDecodare

from enigma import eListboxPythonMultiContent, eListbox, iServiceInformation, \
	RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER, eServiceReference, eServiceCenter
from skin import getListFont, hasListFont, getParameterFromSkin, listRect

# The rows are drawn here; the skin can set their look (HDSatelit names, defaults = the 2011 look), for each
# kind of list (Original, Compact, Minimal; the compact list with description uses the Compact fonts):
#   <alias name="MovieListOriginal0"/> ... "MovieListOriginal2", "MovieListCompact0"/"1", "MovieListMinimal0"/"1":
#   the fonts; the height of font 0 is the row height (it wins over itemHeight= of the widget)
#   x,y,w,h of each text (x below 0 counts from the right edge of the row, w of 0 or below reaches the right edge
#   minus |w|): MovieListOriginal{Name,Tags,Service,Description,Date,Length}, MovieListCompactDescr{Name,
#   Description,Date,Service,Length}, MovieListCompact{Name,Tags,Service,Date,Length}, MovieListMinimal{Name,
#   Length} and, with the description shown, MovieListMinimal{NameDate,Date}. "Tags" is also where the channel
#   goes when the recordings have no tags; "Service" is the channel when there are tags.

# HDSatelit: inregistrarile care asteapta decodarea ("Decodează mai târziu", Components/HdsDecodare.py) au dupa nume
# semnul "[Se decodează mai târziu]", in orice fel de lista; numai cu programul de decodare pe receptor (altfel nu se
# verifica nimic). Fisierele se verifica o data, la incarcarea listei.

cutsParser = struct.Struct(">QI")

def lastPlayPosFromCache(ref):
	return None

def moviePlayState(cutsFileName, ref, length):
	"""Returns None, 0..100 for percentage"""
	try:
		lastCut = None
		cutPTS = None
		with open(cutsFileName, 'rb') as fd:
			while True:
				data = fd.read(cutsParser.size)
				if len(data) < cutsParser.size:
					break
				cut, cutType = cutsParser.unpack(data)
				if cutType == 3:
					cutPTS = cut
				else:
					lastCut = cut
		last = lastPlayPosFromCache(ref)
		if last:
			if not lastCut and len(last) > 2:
				lastCut = last[2]
			if not cutPTS and len(last) > 1:
				cutPTS = last[1]
		if cutPTS is None:
			return None
		if not lastCut:
			if length and length > 0:
				lastCut = length * 90000
			else:
				return 0
		if cutPTS >= lastCut:
			return 100
		return (100 * cutPTS) // lastCut
	except Exception:
		last = lastPlayPosFromCache(ref)
		if last:
			if not length or length < 0:
				length = last[2] if len(last) > 2 else 0
			if length:
				if len(last) > 1 and last[1] >= length:
					return 100
				return (100 * last[1]) // length if len(last) > 1 else 0
			return 0
		return None


class MovieList(GUIComponent):
	SORT_ALPHANUMERIC = 1
	SORT_RECORDED = 2

	LISTTYPE_ORIGINAL = 1
	LISTTYPE_COMPACT_DESCRIPTION = 2
	LISTTYPE_COMPACT = 3
	LISTTYPE_MINIMAL = 4

	HIDE_DESCRIPTION = 1
	SHOW_DESCRIPTION = 2

	def __init__(self, root, list_type=None, sort_type=None, descr_state=None):
		GUIComponent.__init__(self)
		self.list_type = list_type or self.LISTTYPE_ORIGINAL
		self.descr_state = descr_state or self.HIDE_DESCRIPTION
		self.sort_type = sort_type or self.SORT_RECORDED

		self.l = eListboxPythonMultiContent()
		self.tags = set()
		self.hdsDeDecodat = set()
		
		if root is not None:
			self.reload(root)
		
		self.redrawList()
		self.l.setBuildFunc(self.buildMovieListEntry)
		
		self.onSelectionChanged = [ ]

	def connectSelChanged(self, fnc):
		if not fnc in self.onSelectionChanged:
			self.onSelectionChanged.append(fnc)

	def disconnectSelChanged(self, fnc):
		if fnc in self.onSelectionChanged:
			self.onSelectionChanged.remove(fnc)

	def selectionChanged(self):
		for x in self.onSelectionChanged:
			x()

	def setListType(self, type):
		self.list_type = type

	def setDescriptionState(self, val):
		self.descr_state = val

	def setSortType(self, type):
		self.sort_type = type

	def fontAliases(self):
		if self.list_type == MovieList.LISTTYPE_ORIGINAL:
			return (("MovieListOriginal0", ("Regular", 22, 75)), ("MovieListOriginal1", ("Regular", 18)), ("MovieListOriginal2", ("Regular", 16)))
		elif self.list_type == MovieList.LISTTYPE_COMPACT_DESCRIPTION or self.list_type == MovieList.LISTTYPE_COMPACT:
			return (("MovieListCompact0", ("Regular", 20, 37)), ("MovieListCompact1", ("Regular", 14)))
		else:
			return (("MovieListMinimal0", ("Regular", 20, 25)), ("MovieListMinimal1", ("Regular", 16)))

	def redrawList(self):
		for i, (alias, default) in enumerate(self.fontAliases()):
			font, height = getListFont(alias, default)
			self.l.setFont(i, font)
			if i == 0:
				self.l.setItemHeight(height)

	def applySkin(self, desktop, parent):
		ret = GUIComponent.applySkin(self, desktop, parent)
		# with the fonts of the skin the row height follows the kind of list, not itemHeight= of the widget
		if hasListFont(self.fontAliases()[0][0]):
			self.redrawList()
		return ret

	#
	# | name of movie              |
	#
	def buildMovieListEntry(self, serviceref, info, begin, len):
		if serviceref.flags & eServiceReference.mustDescent:
			return None

		width = self.l.getItemSize().width()

		if len <= 0: #recalc len when not already done
			cur_idx = self.l.getCurrentSelectionIndex()
			x = self.list[cur_idx]
			if config.usage.load_length_of_movies_in_moviellist.value:
				len = x[1].getLength(x[0]) #recalc the movie length...
			else:
				len = 0 #dont recalc movielist to speedup loading the list
			self.list[cur_idx] = (x[0], x[1], x[2], len) #update entry in list... so next time we don't need to recalc
		
		if len > 0:
			len = "%d:%02d" % (len // 60, len % 60)
		else:
			len = ""
		
		res = [ None ]
		
		txt = info.getName(serviceref)
		if self.hdsDeDecodat and serviceref.getPath() in self.hdsDeDecodat:
			txt = "%s  [%s]" % (txt, _(HdsDecodare.TXT_SEMN))
		service = ServiceReference(info.getInfoString(serviceref, iServiceInformation.sServiceref))
		description = info.getInfoString(serviceref, iServiceInformation.sDescription)
		tags = info.getInfoString(serviceref, iServiceInformation.sTags)

		begin_string = ""
		if begin > 0:
			t = FuzzyTime(begin)
			begin_string = t[0] + ", " + t[1]
		
		def text(name, default, font, align, value):
			rect, skinned = getParameterFromSkin(name, default)
			x, y, w, h = listRect(rect, width)
			res.append(MultiContentEntryText(pos=(x, y), size=(w, h), font = font, flags = align | (skinned and RT_VALIGN_CENTER or 0), text = value))

		if self.list_type == MovieList.LISTTYPE_ORIGINAL:
			text("MovieListOriginalName", (0, 0, -182, 30), 0, RT_HALIGN_LEFT, txt)
			if self.tags:
				text("MovieListOriginalTags", (-180, 0, 180, 30), 2, RT_HALIGN_RIGHT, tags)
				if service is not None:
					text("MovieListOriginalService", (200, 50, 200, 20), 1, RT_HALIGN_LEFT, service.getServiceName())
			else:
				if service is not None:
					text("MovieListOriginalTags", (-180, 0, 180, 30), 2, RT_HALIGN_RIGHT, service.getServiceName())
			text("MovieListOriginalDescription", (0, 30, 0, 20), 1, RT_HALIGN_LEFT, description)
			text("MovieListOriginalDate", (0, 50, 200, 20), 1, RT_HALIGN_LEFT, begin_string)
			text("MovieListOriginalLength", (-200, 50, 198, 20), 1, RT_HALIGN_RIGHT, len)
		elif self.list_type == MovieList.LISTTYPE_COMPACT_DESCRIPTION:
			text("MovieListCompactDescrName", (0, 0, -120, 20), 0, RT_HALIGN_LEFT, txt)
			text("MovieListCompactDescrDescription", (0, 20, -212, 17), 1, RT_HALIGN_LEFT, description)
			text("MovieListCompactDescrDate", (-120, 6, 120, 20), 1, RT_HALIGN_RIGHT, begin_string)
			if service is not None:
				text("MovieListCompactDescrService", (-212, 20, 154, 17), 1, RT_HALIGN_RIGHT, service.getServiceName())
			text("MovieListCompactDescrLength", (-58, 20, 58, 20), 1, RT_HALIGN_RIGHT, len)
		elif self.list_type == MovieList.LISTTYPE_COMPACT:
			text("MovieListCompactName", (0, 0, -77, 20), 0, RT_HALIGN_LEFT, txt)
			if self.tags:
				text("MovieListCompactTags", (-200, 20, 200, 17), 1, RT_HALIGN_RIGHT, tags)
				if service is not None:
					text("MovieListCompactService", (200, 20, 200, 17), 1, RT_HALIGN_LEFT, service.getServiceName())
			else:
				if service is not None:
					text("MovieListCompactTags", (-200, 20, 200, 17), 1, RT_HALIGN_RIGHT, service.getServiceName())
			text("MovieListCompactDate", (0, 20, 200, 17), 1, RT_HALIGN_LEFT, begin_string)
			text("MovieListCompactLength", (-75, 0, 75, 20), 0, RT_HALIGN_RIGHT, len)
		else:
			assert(self.list_type == MovieList.LISTTYPE_MINIMAL)
			if self.descr_state == MovieList.SHOW_DESCRIPTION:
				text("MovieListMinimalNameDate", (0, 0, -146, 20), 0, RT_HALIGN_LEFT, txt)
				text("MovieListMinimalDate", (-145, 4, 145, 20), 1, RT_HALIGN_RIGHT, begin_string)
			else:
				text("MovieListMinimalName", (0, 0, -77, 20), 0, RT_HALIGN_LEFT, txt)
				text("MovieListMinimalLength", (-75, 0, 75, 20), 0, RT_HALIGN_RIGHT, len)

		return res

	def moveToIndex(self, index):
		self.instance.moveSelectionTo(index)

	def getCurrentIndex(self):
		return self.instance.getCurrentIndex()

	def getCurrentEvent(self):
		l = self.l.getCurrentSelection()
		return l and l[0] and l[1] and l[1].getEvent(l[0])

	def getCurrent(self):
		l = self.l.getCurrentSelection()
		return l and l[0]

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setContent(self.l)
		instance.selectionChanged.get().append(self.selectionChanged)

	def preWidgetRemove(self, instance):
		instance.setContent(None)
		instance.selectionChanged.get().remove(self.selectionChanged)

	def reload(self, root = None, filter_tags = None):
		if root is not None:
			self.load(root, filter_tags)
		else:
			self.load(self.root, filter_tags)
		self.l.setList(self.list)

	def removeService(self, service):
		for l in self.list[:]:
			if l[0] == service:
				self.list.remove(l)
		self.l.setList(self.list)

	def __len__(self):
		return len(self.list)

	def load(self, root, filter_tags):
		# this lists our root service, then building a 
		# nice list
		
		self.list = [ ]
		self.hdsDeDecodat = set()
		decodare = HdsDecodare.exista()
		self.serviceHandler = eServiceCenter.getInstance()
		
		self.root = root
		list = self.serviceHandler.list(root)
		if list is None:
			print("listing of movies failed")
			list = [ ]	
			return
		tags = set()
		
		while 1:
			serviceref = list.getNext()
			if not serviceref.valid():
				break
			if serviceref.flags & eServiceReference.mustDescent:
				continue
		
			info = self.serviceHandler.info(serviceref)
			if info is None:
				continue
			begin = info.getInfo(serviceref, iServiceInformation.sTimeCreate)
		
			# convert space-seperated list of tags into a set
			this_tags = info.getInfoString(serviceref, iServiceInformation.sTags).split(' ')
			if this_tags == ['']:
				this_tags = []
			this_tags = set(this_tags)
			tags |= this_tags
		
			# filter_tags is either None (which means no filter at all), or 
			# a set. In this case, all elements of filter_tags must be present,
			# otherwise the entry will be dropped.			
			if filter_tags is not None and not this_tags.issuperset(filter_tags):
				continue
		
			self.list.append((serviceref, info, begin, -1))
			if decodare and HdsDecodare.deDecodat(HdsDecodare.caleDisc(serviceref.getPath())):
				self.hdsDeDecodat.add(serviceref.getPath())
		
		if self.sort_type == MovieList.SORT_ALPHANUMERIC:
			self.list.sort(key=self.buildAlphaNumericSortKey)
		else:
			# sort: key is 'begin'
			self.list.sort(key=lambda x: -x[2])
		
		# finally, store a list of all tags which were found. these can be presented
		# to the user to filter the list
		self.tags = tags

	def buildAlphaNumericSortKey(self, x):
		ref = x[0]
		info = self.serviceHandler.info(ref)
		name = info and info.getName(ref)
		return (name and name.lower() or "", -x[2])

	def moveTo(self, serviceref):
		count = 0
		for x in self.list:
			if x[0] == serviceref:
				self.instance.moveSelectionTo(count)
				return True
			count += 1
		return False
	
	def moveDown(self):
		self.instance.moveSelection(self.instance.moveDown)
