# Modificat de moneasoftware.com si hdsatelit.com, 2026
import os
import struct
import threading
from .GUIComponent import GUIComponent
from Tools.FuzzyDate import FuzzyTime
from ServiceReference import ServiceReference
from Components.MultiContent import MultiContentEntryText
from Components.config import config
from Components import HdsDecodare

from enigma import eListboxPythonMultiContent, eListbox, iServiceInformation, \
	RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER, eServiceReference, eServiceCenter
from skin import getListFont, hasListFont, getParameterFromSkin, listRect
from Components.SkinIcon import nativ, pictograma, fontPictograme

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

# OE-Alliance: a skin with MovieListNativeIcons=1 gets in front of the name the state of the recording as a glyph of
# the font <alias name="MovieListIcons"/> (enigma2icons by default): MovieListIcon_unwatched, MovieListIcon_part_1_4 ..
# part_4_4 = code[,color[,selected color]] (font 3 of the list; the name moves right by the glyph). Skins without
# these parameters (ours) draw the rows exactly as before.
_FONT_GLIFE = 3

cutsParser = struct.Struct(">QI")

_MUTARE_LACAT = threading.Lock()


def caiInregistrariActive(session):
	"""Fisiere in curs de inregistrare sau redare, verificate pe firul interfetei."""
	nav = session.nav
	active = []
	temporizatoare = getattr(getattr(nav, "RecordTimer", None), "timer_list", ())
	for t in temporizatoare:
		pornit = getattr(t, "record_service", None) is not None
		if not pornit and callable(getattr(t, "isRunning", None)):
			pornit = t.isRunning() and not getattr(t, "justplay", False)
		if pornit:
			cale = getattr(t, "Filename", "") or getattr(t, "filename", "")
			if cale:
				active.extend((cale, cale + ".ts"))
	# O inregistrare care nu are un temporizator cunoscut nu se muta pe ghicite.
	if nav.getRecordings() and not active:
		raise ValueError(_("Nu se pot verifica înregistrările în curs."))
	ref = nav.getCurrentlyPlayingServiceReference()
	if ref is not None:
		cale = ref.getPath() or ""
		if os.path.isabs(cale):
			active.append(cale)
	return tuple(active)


def _mutaFaraInlocuire(sursa, tinta):
	"""Mutare atomica pe acelasi disc, fara suprascriere nici daca apare un fisier intre verificari."""
	if os.name == "nt":
		os.rename(sursa, tinta)
		return
	try:
		import ctypes
		libc = ctypes.CDLL(None, use_errno=True)
		redenumeste = getattr(libc, "renameat2", None)
	except ImportError:
		redenumeste = None
	if redenumeste is None:
		# Legaturile dure pastreaza aceeasi protectie pe un Python fara ctypes.
		# Un disc fara acest suport refuza operatia inainte sa se atinga sursa.
		os.link(sursa, tinta)
		try:
			os.unlink(sursa)
		except OSError:
			os.unlink(tinta)
			raise
		return
	redenumeste.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
	redenumeste.restype = ctypes.c_int
	if redenumeste(-100, os.fsencode(sursa), -100, os.fsencode(tinta), 1):
		cod = ctypes.get_errno()
		raise OSError(cod, os.strerror(cod), tinta)


def mutaInregistrarea(cale, destinatie, active=()):
	"""Muta filmul cu fisierele asociate pe acelasi disc. Orice refuz lasa sursele intacte.
	Un esec dupa prima redenumire readuce fisierele deja mutate; nu se inlocuieste niciun fisier existent."""
	import stat
	from Components.HdsSubtitrariFilm import EXTENSII as extensiiSubtitrari
	from Components.HdsPisteLimbi import limbaCanonica
	def peDisc(text):
		return os.fsdecode(text.encode("utf-8", "surrogateescape"))
	cale = os.path.abspath(peDisc(cale))
	destinatie = os.path.abspath(peDisc(destinatie))
	with _MUTARE_LACAT:
		if not os.path.isdir(destinatie):
			raise ValueError(_("Dosarul de destinație nu există."))
		if os.path.islink(cale) or not stat.S_ISREG(os.lstat(cale).st_mode):
			raise ValueError(_("Se pot muta numai filme obișnuite, fără legături simbolice."))
		if os.path.samefile(os.path.dirname(cale), destinatie):
			raise ValueError(_("Filmul este deja în acest dosar."))
		if os.stat(cale).st_dev != os.stat(destinatie).st_dev:
			raise ValueError(_("Alege un dosar de pe același disc pentru mutare."))
		cheie = lambda c: os.path.normcase(os.path.realpath(peDisc(c)))
		if cheie(cale) in {cheie(c) for c in active if c}:
			raise ValueError(_("Oprește înregistrarea sau redarea înainte de mutare."))
		fisiere = [cale]
		for sufix in (".meta", ".ap", ".sc", ".cuts", ".hdsdecodare"):
			if os.path.lexists(cale + sufix):
				fisiere.append(cale + sufix)
		if cale.lower().endswith(".ts") and os.path.lexists(cale[:-3] + ".eit"):
			fisiere.append(cale[:-3] + ".eit")
		prefix = os.path.basename(cale) + "."
		baza = os.path.splitext(os.path.basename(cale))[0]
		for nume in sorted(os.listdir(os.path.dirname(cale))):
			if nume.startswith(prefix) and len(nume[len(prefix):]) == 3 and nume[len(prefix):].isdigit():
				fisiere.append(os.path.join(os.path.dirname(cale), nume))
			# Numai numele exact al filmului, eventual urmat de o limba cunoscuta.
			# Un alt film care doar incepe cu acelasi cuvant nu isi pierde subtitrarea.
			radacina, extensie = os.path.splitext(nume)
			if extensie.lower() not in extensiiSubtitrari or nume == os.path.basename(cale):
				continue
			potriveste = radacina.casefold() == baza.casefold()
			if not potriveste and radacina.casefold().startswith(baza.casefold() + "."):
				limba = radacina[len(baza) + 1:]
				potriveste = limba.isalpha() and limbaCanonica(limba) is not None
			if potriveste:
				fisiere.append(os.path.join(os.path.dirname(cale), nume))
		plan = [(f, os.path.join(destinatie, os.path.basename(f))) for f in fisiere]
		for sursa, tinta in plan:
			if os.path.islink(sursa) or not stat.S_ISREG(os.lstat(sursa).st_mode):
				raise ValueError(_("Un fișier asociat nu poate fi mutat în siguranță."))
			if os.path.lexists(tinta):
				raise ValueError(_("În destinație există deja un fișier cu același nume."))
		mutate = []
		try:
			for sursa, tinta in plan:
				_mutaFaraInlocuire(sursa, tinta)
				mutate.append((sursa, tinta))
		except OSError:
			erori = []
			for sursa, tinta in reversed(mutate):
				try:
					_mutaFaraInlocuire(tinta, sursa)
				except OSError:
					erori.append(tinta)
			if erori:
				raise OSError(_("Mutarea s-a oprit. Verifică fișierele din ambele dosare: %s") % ", ".join(erori))
			raise
	return plan[0][1]

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
				self.hdsMarimeGlifa = default[1]
		if nativ("MovieListNativeIcons"):
			self.l.setFont(_FONT_GLIFE, fontPictograme("MovieListIcons", self.hdsMarimeGlifa))

	def hdsGlifaStare(self, serviceref, length):
		"""SkinIcon of the state of a recording (OE-Alliance, MovieListNativeIcons): watched part or unwatched; else None.
		The state is read once per file (until the list is loaded again)."""
		if not nativ("MovieListNativeIcons"):
			return None
		cale = serviceref.getPath()
		stari = self.__dict__.setdefault("hdsStari", {})
		if cale not in stari:
			parte = moviePlayState(cale + ".cuts", serviceref, length if isinstance(length, int) else 0)
			stari[cale] = "part_%d_4" % min(4, parte // 25) if parte else "unwatched"
		return pictograma("MovieList", stari[cale]) or (stari[cale] != "unwatched" and pictograma("MovieList", "unwatched") or None)

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
		
		glyph = self.hdsGlifaStare(serviceref, len)
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
			if glyph is not None and name.endswith(("Name", "NameDate")):
				# OE-Alliance: the glyph of the state in front of the name, as tall as the name
				s = max(1, h)
				res.append(glyph.entry((x, y), (s, h), _FONT_GLIFE))
				x, w = x + s + 8, max(0, w - s - 8)
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
		self.hdsStari = {}
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

# numele cerute de pluginuri
MOVIE_EXTENSIONS = frozenset((".ts", ".stream", ".mp4", ".mkv", ".mpg", ".mpeg", ".mpe", ".avi", ".vob", ".m2ts", ".mts", ".m4v", ".mov", ".flv", ".wmv", ".divx", ".iso", ".img", ".webm"))
AUDIO_EXTENSIONS = frozenset((".mp3", ".mp2", ".m4a", ".m2a", ".mka", ".flac", ".ogg", ".oga", ".dts", ".wav", ".wave", ".wma", ".ac3", ".aac"))
DVD_EXTENSIONS = frozenset((".iso", ".img", ".nrg"))
IMAGE_EXTENSIONS = frozenset((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".jpe", ".svg"))
KNOWN_EXTENSIONS = MOVIE_EXTENSIONS | AUDIO_EXTENSIONS | DVD_EXTENSIONS | IMAGE_EXTENSIONS


class StubInfo:
	"""Informatia unui fisier care nu e serviciu: numele, marimea si data din disc."""
	def getName(self, serviceref):
		return os.path.split(serviceref.getPath())[1]

	def getLength(self, serviceref):
		return -1

	def getEvent(self, serviceref, *args):
		return None

	def isPlayable(self):
		return True

	def getInfo(self, serviceref, w):
		try:
			if w == iServiceInformation.sTimeCreate:
				return os.stat(serviceref.getPath()).st_ctime
			if w == iServiceInformation.sFileSize:
				return os.stat(serviceref.getPath()).st_size
			if w == iServiceInformation.sDescription:
				return serviceref.getPath()
		except OSError:
			pass
		return 0

	def getInfoString(self, serviceref, w):
		return ""


justStubInfo = StubInfo()


def resetMoviePlayState(cutsFileName, ref=None):
	"""Scoate pozitia de redare (reperul de tip 3) din fisierul .cuts."""
	try:
		with open(cutsFileName, "rb") as f:
			date = f.read()
		pastrate = []
		for i in range(0, len(date) - len(date) % cutsParser.size, cutsParser.size):
			if cutsParser.unpack_from(date, i)[1] != 3:
				pastrate.append(date[i:i + cutsParser.size])
		with open(cutsFileName, "wb") as f:
			f.write(b"".join(pastrate))
	except OSError:
		pass
