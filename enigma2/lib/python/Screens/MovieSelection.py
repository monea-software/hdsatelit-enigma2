# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.Button import Button
from Components.ActionMap import HelpableActionMap, ActionMap
from Components.MenuList import MenuList
from Components.MovieList import MovieList
from Components.DiskInfo import DiskInfo
from Components.Pixmap import Pixmap
from Components.Label import Label
from Components.PluginComponent import plugins
from Components.config import config, ConfigSubsection, ConfigText, ConfigInteger, ConfigLocations, ConfigSet
from Components.Sources.ServiceEvent import ServiceEvent
from Components import HdsDecodare
from Components.UsageConfig import defaultMoviePath

from Plugins.Plugin import PluginDescriptor

from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.LocationBox import MovieLocationBox
from Screens.HelpMenu import HelpableScreen

from Tools.Directories import *
from Tools.BoundFunction import boundFunction

from enigma import eServiceReference, eServiceCenter, eTimer, eSize

import os
import threading

config.movielist = ConfigSubsection()
config.movielist.moviesort = ConfigInteger(default=MovieList.SORT_RECORDED)
config.movielist.listtype = ConfigInteger(default=MovieList.LISTTYPE_ORIGINAL)
config.movielist.description = ConfigInteger(default=MovieList.HIDE_DESCRIPTION)
config.movielist.last_videodir = ConfigText(default=resolveFilename(SCOPE_HDD))
config.movielist.last_timer_videodir = ConfigText(default=resolveFilename(SCOPE_HDD))
config.movielist.videodirs = ConfigLocations(default=[resolveFilename(SCOPE_HDD)])
config.movielist.first_tags = ConfigText(default="")
config.movielist.second_tags = ConfigText(default="")
config.movielist.last_selected_tags = ConfigSet([], default=[])
# ultimul film ales din lista (referinta ca text): lista se deschide cu cursorul pe el
config.movielist.hds_ultimul_film = ConfigText(default="")


def _marime(octeti):
	"""Marimea unui fisier pe intelesul oricui, fara zecimale: „1234 MB” sub 10 GB, „12 GB” peste."""
	if octeti >= 10 * 1000 ** 3:
		return _("%s GB") % int(round(octeti / 1000.0 ** 3))
	return _("%s MB") % max(1, int(round(octeti / 1000.0 ** 2)))


def caleDisc(cale):
	"""Calea unui serviciu (textul UTF-8 dat de enigma2) ca nume de fisier pentru Python: enigma2 ruleaza cu locale-ul C,
	deci un nume cu diacritice trebuie trecut prin octetii lui (os.fsdecode), altfel os.stat da UnicodeEncodeError."""
	try:
		return os.fsdecode(cale.encode("utf-8", "surrogateescape"))
	except (UnicodeError, AttributeError):
		return cale


def citesteDetalii(cale):
	"""Marimea fisierului si ultima pozitie din <film>.cuts (tipul 3), citite de pe disc; ruleaza pe firul detaliilor
	(un disc care doarme poate tine o secunda). {"marime": octeti sau None, "loc": pts sau None}."""
	rez = {"marime": None, "loc": None}
	cale = caleDisc(cale)
	try:
		rez["marime"] = os.stat(cale).st_size
	except (OSError, ValueError):
		return rez
	try:
		with open(cale + ".cuts", "rb") as f:
			date = f.read(12 * 1000)
		for i in range(0, len(date) - 11, 12):
			unde = int.from_bytes(date[i:i + 8], "big")
			if int.from_bytes(date[i + 8:i + 12], "big") == 3:
				rez["loc"] = unde
	except (OSError, ValueError):
		pass
	return rez


class _DetaliiFilm(object):
	"""Detaliile filmului ales, citite pe un fir separat (numai ultima cerere conteaza) si predate firului enigma2
	printr-un eTimer care se uita la 50 ms cat timp e ceva de predat."""

	def __init__(self, gata):
		self.gata = gata
		self.lacat = threading.Lock()
		self.cerere = None
		self.rezultat = None
		self.fir = None
		self.ceas = eTimer()
		self.ceas.callback.append(self._verifica)

	def cere(self, cheie, cale):
		with self.lacat:
			self.cerere = (cheie, cale)
		self._porneste()
		self.ceas.start(50, False)

	def _porneste(self):
		if self.fir is None or not self.fir.is_alive():
			self.fir = threading.Thread(target=self._lucreaza, name="HdsDetaliiFilm", daemon=True)
			self.fir.start()

	def _lucreaza(self):
		while True:
			with self.lacat:
				cerere, self.cerere = self.cerere, None
			if cerere is None:
				return
			try:
				rezultat = citesteDetalii(cerere[1])
			except Exception as eroare:
				print("[MovieSelection] detaliile filmului: %s" % eroare)
				rezultat = {"marime": None, "loc": None}
			with self.lacat:
				self.rezultat = (cerere[0], rezultat)

	def _verifica(self):
		with self.lacat:
			rezultat, self.rezultat = self.rezultat, None
			asteapta = self.cerere is not None
		if rezultat is not None:
			self.gata(*rezultat)
		viu = self.fir is not None and self.fir.is_alive()
		if asteapta and not viu:
			self._porneste()
		elif not asteapta and not viu:
			with self.lacat:
				gol = self.rezultat is None
			if gol:
				self.ceas.stop()

	def opreste(self):
		self.ceas.stop()
		self.gata = lambda *a: None


def stergeFilmul(session, csel, service, dupa):
	"""Stergerea unui film sau a unei inregistrari din lista, cu intrebare (tasta rosie si meniul listei)."""
	serviceHandler = eServiceCenter.getInstance()
	offline = serviceHandler.offlineOperations(service)
	info = serviceHandler.info(service)
	name = info and info.getName(service) or _("this recording")
	if offline is None or offline.deleteFromDisk(1):
		session.openWithCallback(dupa, MessageBox, _("You cannot delete this!"), MessageBox.TYPE_ERROR)
		return

	def confirmat(da):
		if not da:
			return dupa()
		offline = eServiceCenter.getInstance().offlineOperations(service)
		if offline is None or offline.deleteFromDisk(0):
			session.openWithCallback(dupa, MessageBox, _("Delete failed!"), MessageBox.TYPE_ERROR)
			return
		csel["list"].removeService(service)
		csel["freeDiskSpace"].update()
		dupa()
	session.openWithCallback(confirmat, MessageBox, _("Do you really want to delete %s?") % (name))


def setPreferredTagEditor(te):
	global preferredTagEditor
	try:
		if preferredTagEditor == None:
			preferredTagEditor = te
			print("Preferred tag editor changed to ", preferredTagEditor)
		else:
			print("Preferred tag editor already set to ", preferredTagEditor)
			print("ignoring ", te)
	except:
		preferredTagEditor = te
		print("Preferred tag editor set to ", preferredTagEditor)

def getPreferredTagEditor():
	global preferredTagEditor
	return preferredTagEditor

setPreferredTagEditor(None)

class MovieContextMenu(Screen):
	def __init__(self, session, csel, service):
		Screen.__init__(self, session)
		self.csel = csel
		self.service = service

		self["actions"] = ActionMap(["OkCancelActions"],
			{
				"ok": self.okbuttonClick,
				"cancel": self.cancelClick
			})

		menu = [(_("delete..."), self.delete)]
		menu.extend([(p.description, boundFunction(self.execPlugin, p)) for p in plugins.getPlugins(PluginDescriptor.WHERE_MOVIELIST)])

		if config.movielist.moviesort.value == MovieList.SORT_ALPHANUMERIC:
			menu.append((_("sort by date"), boundFunction(self.sortBy, MovieList.SORT_RECORDED)))
		else:
			menu.append((_("alphabetic sort"), boundFunction(self.sortBy, MovieList.SORT_ALPHANUMERIC)))
		
		menu.extend((
			(_("list style default"), boundFunction(self.listType, MovieList.LISTTYPE_ORIGINAL)),
			(_("list style compact with description"), boundFunction(self.listType, MovieList.LISTTYPE_COMPACT_DESCRIPTION)),
			(_("list style compact"), boundFunction(self.listType, MovieList.LISTTYPE_COMPACT)),
			(_("list style single line"), boundFunction(self.listType, MovieList.LISTTYPE_MINIMAL))
		))

		if config.movielist.description.value == MovieList.SHOW_DESCRIPTION:
			menu.append((_("hide extended description"), boundFunction(self.showDescription, MovieList.HIDE_DESCRIPTION)))
		else:
			menu.append((_("show extended description"), boundFunction(self.showDescription, MovieList.SHOW_DESCRIPTION)))
		# ce fac tastele colorate ale listei, si aici, ca sa se ajunga la ele cu sagetile si OK
		menu.append((_("Alt dosar"), boundFunction(self.dinLista, csel.doPathSelect)))
		if csel.tags:
			menu.append((_("Etichete"), boundFunction(self.dinLista, csel.showTagsSelect)))
		if csel.selected_tags:
			menu.append((_("Toate filmele"), boundFunction(self.dinLista, csel.showAll)))
		self["menu"] = MenuList(menu)

	def okbuttonClick(self):
		self["menu"].getCurrent()[1]()

	def cancelClick(self):
		self.close(False)

	def sortBy(self, newType):
		config.movielist.moviesort.value = newType
		self.csel.setSortType(newType)
		self.csel.reloadList()
		self.close()

	def listType(self, newType):
		config.movielist.listtype.value = newType
		self.csel.setListType(newType)
		self.csel.list.redrawList()
		self.close()

	def showDescription(self, newType):
		config.movielist.description.value = newType
		self.csel.setDescriptionState(newType)
		self.csel.updateDescription()
		self.close()

	def execPlugin(self, plugin):
		plugin(session=self.session, service=self.service)

	def dinLista(self, functie):
		self.close()
		functie()

	def delete(self):
		stergeFilmul(self.session, self.csel, self.service, self.close)

class SelectionEventInfo:
	def __init__(self):
		self["Service"] = ServiceEvent()
		self.list.connectSelChanged(self.__selectionChanged)
		self.timer = eTimer()
		self.timer.callback.append(self.updateEventInfo)
		self.onShown.append(self.updateEventInfo)

	def __selectionChanged(self):
		if self.execing:
			self.timer.start(50, True)

	def updateEventInfo(self):
		serviceref = self.getCurrent()
		self["Service"].newService(serviceref)

class MovieSelection(Screen, HelpableScreen, SelectionEventInfo):
	"""Lista filmelor si a inregistrarilor dintr-un dosar. selectedmovie: filmul pe care sta cursorul (fara el, ultimul
	film ales din lista); urmatorul: cursorul trece pe filmul de dupa el (dupa un film pe care receptorul nu l-a putut
	reda, ca un OK sa nu il porneasca din nou). La dreapta: numele (la filmele fara descriere), marimea si formatul,
	locul unde s-a ramas (din <film>.cuts) si dosarul, citite pe un fir separat. Tastele colorate: stergere, ordinea,
	alt dosar, etichetele (sau meniul listei); toate sunt si in meniul listei."""

	def __init__(self, session, selectedmovie = None, urmatorul = False):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		if selectedmovie is None and config.movielist.hds_ultimul_film.value:
			selectedmovie = eServiceReference(config.movielist.hds_ultimul_film.value)
		self.urmatorul = urmatorul
		self["hdsNume"] = Label("")
		self["hdsDetalii"] = Label("")
		self.detalii = _DetaliiFilm(self.detaliiGata)
		self.onClose.append(self.detalii.opreste)

		self.tags = [ ]
		if selectedmovie:
			self.selected_tags = config.movielist.last_selected_tags.value
		else:
			self.selected_tags = None
		self.selected_tags_ele = None

		self.movemode = False
		self.bouquet_mark_edit = False

		self.delayTimer = eTimer()
		self.delayTimer.callback.append(self.updateHDDData)

		self["waitingtext"] = Label(_("Please wait... Loading list..."))

		# create optional description border and hide immediately
		self["DescriptionBorder"] = Pixmap()
		self["DescriptionBorder"].hide()

		if not fileExists(config.movielist.last_videodir.value):
			config.movielist.last_videodir.value = defaultMoviePath()
			config.movielist.last_videodir.save()
		self.current_ref = eServiceReference("2:0:1:0:0:0:0:0:0:0:" + config.movielist.last_videodir.value)

		self["list"] = MovieList(None,
			config.movielist.listtype.value,
			config.movielist.moviesort.value,
			config.movielist.description.value)

		self.list = self["list"]
		self.selectedmovie = selectedmovie

		# Need list for init
		SelectionEventInfo.__init__(self)

		self["key_red"] = Button(_("Șterge"))
		self["key_green"] = Button("")
		self["key_yellow"] = Button(_("Alt dosar"))
		self["key_blue"] = Button("")

		self["freeDiskSpace"] = self.diskinfo = DiskInfo(config.movielist.last_videodir.value, DiskInfo.FREE, update=False)

		if config.usage.setup_level.index >= 2: # expert+
			self["InfobarActions"] = HelpableActionMap(self, "InfobarActions", 
				{
					"showMovies": (self.doPathSelect, _("select the movie path")),
				})


		self["MovieSelectionActions"] = HelpableActionMap(self, "MovieSelectionActions",
			{
				"contextMenu": (self.doContext, _("menu")),
				"showEventInfo": (self.showEventInformation, _("show event details")),
			})

		self["ColorActions"] = HelpableActionMap(self, "ColorActions",
			{
				"red": (self.stergeFilm, _("Șterge")),
				"green": (self.schimbaOrdinea, _("sort by date") + " / " + _("alphabetic sort")),
				"yellow": (self.doPathSelect, _("Alt dosar")),
				"blue": (self.tastaAlbastra, _("Etichete")),
			})

		self["OkCancelActions"] = HelpableActionMap(self, "OkCancelActions",
			{
				"cancel": (self.abort, _("exit movielist")),
				"ok": (self.movieSelected, _("select movie")),
			})

		self.onShown.append(self.go)
		self.onLayoutFinish.append(self.saveListsize)
		self.inited = False

	def updateDescription(self):
		if config.movielist.description.value == MovieList.SHOW_DESCRIPTION:
			self["DescriptionBorder"].show()
			self["list"].instance.resize(eSize(self.listWidth, self.listHeight-self["DescriptionBorder"].instance.size().height()))
		else:
			self["Service"].newService(None)
			self["DescriptionBorder"].hide()
			self["list"].instance.resize(eSize(self.listWidth, self.listHeight))

	def showEventInformation(self):
		from Screens.EventView import EventViewSimple
		from ServiceReference import ServiceReference
		evt = self["list"].getCurrentEvent()
		if evt:
			self.session.open(EventViewSimple, evt, ServiceReference(self.getCurrent()))

	def go(self):
		if not self.inited:
		# ouch. this should redraw our "Please wait..."-text.
		# this is of course not the right way to do this.
			self.delayTimer.start(10, 1)
			self.inited=True

	def saveListsize(self):
			listsize = self["list"].instance.size()
			self.listWidth = listsize.width()
			self.listHeight = listsize.height()
			self.updateDescription()

	def updateHDDData(self):
		self.reloadList(self.selectedmovie)
		self["waitingtext"].visible = False

	def moveTo(self):
		self["list"].moveTo(self.selectedmovie)

	def getCurrent(self):
		return self["list"].getCurrent()

	def movieSelected(self):
		current = self.getCurrent()
		if current is not None and HdsDecodare.deDecodat(caleDisc(current.getPath())):
			# o inregistrare "Decodează mai târziu" inca nedecodata: un mesaj simplu, nu ecran negru (Components/HdsDecodare.py)
			self.session.open(MessageBox, _(HdsDecodare.TXT_PORNIRE), MessageBox.TYPE_INFO)
			return
		if current is not None:
			config.movielist.hds_ultimul_film.value = current.toString()
			config.movielist.hds_ultimul_film.save()
			self.saveconfig()
			self.close(current)

	def updateEventInfo(self):
		SelectionEventInfo.updateEventInfo(self)
		self.cereDetalii()

	def cereDetalii(self):
		"""Numele si detaliile randului ales; ce vine de pe disc (marimea, locul) vine pe firul detaliilor."""
		ref = self.getCurrent()
		self["hdsNume"].setText("")
		self["hdsDetalii"].setText("")
		if ref is None:
			return
		info = eServiceCenter.getInstance().info(ref)
		eveniment = info and info.getEvent(ref)
		if eveniment is None and info is not None:
			self["hdsNume"].setText(info.getName(ref) or "")
		self.detalii.cere(ref.toString(), ref.getPath())

	def detaliiGata(self, cheie, rez):
		ref = self.getCurrent()
		if ref is None or ref.toString() != cheie:
			return
		randuri = []
		cale = ref.getPath()
		fel = os.path.splitext(cale)[1][1:].upper()
		if rez.get("marime") is not None:
			randuri.append(" · ".join(x for x in (fel, _marime(rez["marime"])) if x))
		lungime = None
		try:
			intrare = self["list"].list[self["list"].getCurrentIndex()]
			if intrare[0] == ref and intrare[3] > 0:
				lungime = intrare[3] * 90000
		except (AttributeError, IndexError, TypeError):
			pass
		try:
			from Components.HdsFilmRedare import textTimp
		except ImportError:
			textTimp = None
		if lungime and textTimp is not None:
			randuri.append(_("Lungime: %s") % textTimp(lungime))
		if rez.get("loc") and textTimp is not None:
			randuri.append(_("Ai rămas la %s.") % textTimp(rez["loc"], lungime))
		randuri.append(_("Dosarul: %s") % config.movielist.last_videodir.value)
		self["hdsDetalii"].setText("\n".join(randuri))

	def stergeFilm(self):
		current = self.getCurrent()
		if current is not None:
			stergeFilmul(self.session, self, current, lambda *raspuns: self.updateEventInfo())

	def schimbaOrdinea(self):
		if config.movielist.moviesort.value == MovieList.SORT_ALPHANUMERIC:
			config.movielist.moviesort.value = MovieList.SORT_RECORDED
		else:
			config.movielist.moviesort.value = MovieList.SORT_ALPHANUMERIC
		self.setSortType(config.movielist.moviesort.value)
		self.reloadList()

	def tastaAlbastra(self):
		if self.tags:
			self.showTagsSelect()
		else:
			self.doContext()

	def doContext(self):
		current = self.getCurrent()
		if current is not None:
			self.session.open(MovieContextMenu, self, current)

	def abort(self):
		self.saveconfig()
		self.close(None)

	def saveconfig(self):
		config.movielist.last_selected_tags.value = self.selected_tags
		config.movielist.moviesort.save()
		config.movielist.listtype.save()
		config.movielist.description.save()

	def getTagDescription(self, tag):
		# TODO: access the tag database
		return tag

	def updateTags(self):
		# get a list of tags available in this list
		self.tags = list(self["list"].tags)

		if not self.tags:
			# by default, we do not display any filtering options
			self.tag_first = ""
			self.tag_second = ""
		else:
			tmp = config.movielist.first_tags.value
			if tmp in self.tags:
				self.tag_first = tmp
			else:
				self.tag_first = "<"+_("Tag 1")+">"
			tmp = config.movielist.second_tags.value
			if tmp in self.tags:
				self.tag_second = tmp
			else:
				self.tag_second = "<"+_("Tag 2")+">"
		# verde: ordinea in care trece lista la apasare; albastru: etichetele, sau meniul listei cand nu sunt etichete
		if config.movielist.moviesort.value == MovieList.SORT_ALPHANUMERIC:
			self["key_green"].text = _("După dată")
		else:
			self["key_green"].text = _("Alfabetic")
		if self.tags:
			self["key_blue"].text = _("Etichete")
		else:
			self["key_blue"].text = _("Meniu")

	def setListType(self, type):
		self["list"].setListType(type)

	def setDescriptionState(self, val):
		self["list"].setDescriptionState(val)

	def setSortType(self, type):
		self["list"].setSortType(type)

	def reloadList(self, sel = None, home = False):
		if not fileExists(config.movielist.last_videodir.value):
			path = defaultMoviePath()
			config.movielist.last_videodir.value = path
			config.movielist.last_videodir.save()
			self.current_ref = eServiceReference("2:0:1:0:0:0:0:0:0:0:" + path)
			self["freeDiskSpace"].path = path
		if sel is None:
			sel = self.getCurrent()
		self["list"].reload(self.current_ref, self.selected_tags)
		# filmele de pe stick sau disc si inregistrarile stau in aceeasi lista; dosarul e in detaliile din dreapta
		title = _("Filme și înregistrări")
		# selected_tags e None (fara filtru) sau lista etichetelor alese, goala dupa un film ales fara eticheta: numai o
		# eticheta aleasa intra in titlu (altfel ramanea „Filme și înregistrări -”)
		if self.selected_tags:
			title += " - " + ','.join(self.selected_tags)
		self.setTitle(title)
		if sel and self["list"].moveTo(sel):
			if self.urmatorul and self["list"].getCurrentIndex() + 1 < len(self["list"]):
				self["list"].moveToIndex(self["list"].getCurrentIndex() + 1)
		elif home:
			self["list"].moveToIndex(0)
		self.urmatorul = False
		self.updateTags()
		self["freeDiskSpace"].update()
		self.updateEventInfo()

	def doPathSelect(self):
		self.session.openWithCallback(
			self.gotFilename,
			MovieLocationBox,
			_("Please select the movie path..."),
			config.movielist.last_videodir.value
		)

	def gotFilename(self, res):
		if res is not None and res is not config.movielist.last_videodir.value:
			if fileExists(res):
				config.movielist.last_videodir.value = res
				config.movielist.last_videodir.save()
				self.current_ref = eServiceReference("2:0:1:0:0:0:0:0:0:0:" + res)
				self["freeDiskSpace"].path = res
				self.reloadList(home = True)
			else:
				self.session.open(
					MessageBox,
					_("Directory %s nonexistent.") % (res),
					type = MessageBox.TYPE_ERROR,
					timeout = 5
					)

	def showAll(self):
		self.selected_tags_ele = None
		self.selected_tags = None
		self.reloadList(home = True)

	def showTagsN(self, tagele):
		if not self.tags:
			self.showTagWarning()
		elif not tagele or (self.selected_tags and tagele.value in self.selected_tags) or not tagele.value in self.tags:
			self.showTagsMenu(tagele)
		else:
			self.selected_tags_ele = tagele
			self.selected_tags = set([tagele.value])
			self.reloadList(home = True)

	def showTagsFirst(self):
		self.showTagsN(config.movielist.first_tags)

	def showTagsSecond(self):
		self.showTagsN(config.movielist.second_tags)

	def showTagsSelect(self):
		self.showTagsN(None)

	def tagChosen(self, tag):
		if tag is not None and tag[0] is None:
			self.showAll()
		elif tag is not None:
			self.selected_tags = set([tag[0]])
			if self.selected_tags_ele:
				self.selected_tags_ele.value = tag[0]
				self.selected_tags_ele.save()
			self.reloadList(home = True)

	def showTagsMenu(self, tagele):
		self.selected_tags_ele = tagele
		list = [(tag, self.getTagDescription(tag)) for tag in self.tags ]
		# primul rand arata iar toate filmele (tasta rosie nu mai face asta), numai cand lista e filtrata
		if self.selected_tags:
			list.insert(0, (None, _("Toate filmele")))
		self.session.openWithCallback(self.tagChosen, ChoiceBox, title=_("Please select tag to filter..."), list = list)

	def showTagWarning(self):
		self.session.open(MessageBox, _("No tags are set on these movies."), MessageBox.TYPE_ERROR)
