# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Tools.Profile import profile

# workaround for required config entry dependencies.
from Screens.MovieSelection import MovieSelection

from .Screen import Screen

profile("LOAD:enigma")
from enigma import iPlayableService, eTimer

profile("LOAD:InfoBarGenerics")
from Screens.InfoBarGenerics import InfoBarShowHide, \
	InfoBarNumberZap, InfoBarChannelSelection, InfoBarMenu, InfoBarRdsDecoder, \
	InfoBarEPG, InfoBarSeek, InfoBarInstantRecord, \
	InfoBarAudioSelection, InfoBarSubtitleSelection, InfoBarAdditionalInfo, InfoBarNotifications, InfoBarDish, InfoBarUnhandledKey, \
	InfoBarSubserviceSelection, InfoBarShowMovies, InfoBarTimeshift,  \
	InfoBarServiceNotifications, InfoBarPVRState, InfoBarCueSheetSupport, InfoBarSimpleEventView, \
	InfoBarSummarySupport, InfoBarMoviePlayerSummarySupport, InfoBarTimeshiftState, InfoBarTeletextPlugin, InfoBarExtensions, \
	InfoBarSubtitleSupport, InfoBarPiP, InfoBarPlugins, InfoBarServiceErrorPopupSupport, InfoBarJobman, \
	InfoBarFilmRefuz

profile("LOAD:InitBar_Components")
from Components.ActionMap import HelpableActionMap
from Components.config import config, configfile
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase

profile("LOAD:HelpableScreen")
from Screens.HelpMenu import HelpableScreen

# HDSatelit (tastele Viper): tastele telecomenzii Viper care n-aveau nicio actiune in imagine (EPG,
# Mplay, Timer, Portal, FAV si doua din cele trei taste cu desen de ecran) primesc una aici. Contextele sunt folosite
# numai de bara (HdsInfobarActions) si de playerul inregistrarilor (MoviePlayerActions), ca sa nu apara
# „unknown action ... typo in keymap?” in alte ecrane care folosesc contextele comune. Sensul tastelor e cel obisnuit in enigma2
# (data/keymap.xml): KEY_EPG = EPGPressed, KEY_LIST = showMediaPlayer, KEY_TIME = openTimerList,
# KEY_WWW = showWWW, KEY_FAVORITES = openBouquetList, KEY_MODE = aspectSelection, KEY_SWITCHVIDEOMODE = vmodeSelection.
# Pe Viper desenul cu benzi laterale e pe tasta din mijloc (227), deci formatul imaginii
# e acolo (KEY_VMODE = toggleAspectRatio, legatura obisnuita); tasta din stanga (373) deschide setarile A/V.

def hdsAlegeFormatImagine(session):
	"""lista formatelor de imagine (config.av.aspectratio, ca in Setari); alegerea se aplica prin notificatorul din
	Components/AVSwitch.py si se salveaza pe loc"""
	from Screens.ChoiceBox import ChoiceBox
	element = config.av.aspectratio
	descrieri = element.description
	valori = list(element.choices)
	lista = [(descrieri[v], v) for v in valori]
	curent = valori.index(element.value) if element.value in valori else 0

	def ales(raspuns):
		if raspuns is None or raspuns[1] == element.value:
			return
		element.value = raspuns[1]
		element.save()
		configfile.save()

	session.openWithCallback(ales, ChoiceBox, title=_("Aspect ratio"), list=lista, selection=curent)


def hdsTeletextSauMesaj(ecran):
	"""TTX: un vizualizator de teletext instalat ca plugin, daca exista; altfel al imaginii (Screens/HdsTeletext.py);
	fara el (nucleu vechi), un mesaj limpede, nu o tasta moarta"""
	if getattr(ecran, "teletext_plugin", None) is not None:
		ecran.startTeletext()
		return
	try:
		from Screens.HdsTeletext import deschide
	except ImportError:
		deschide = None
	if deschide is not None and deschide(ecran.session):
		return
	from Screens.MessageBox import MessageBox
	ecran.session.open(MessageBox, _("Teletextul nu este încă în imagine. Subtitrările din teletext se aleg cu tasta SUBT."),
		MessageBox.TYPE_INFO, timeout=6)


def hdsHbbtvRosu(ecran):
	"""ROSU pe televizorul live: aplicatia HbbTV a canalului (Components/HdsHbbtvPornire.py). Fara aplicatie de
	pornit, 0: tasta merge mai departe, ca inainte."""
	try:
		from Components import HdsHbbtvPornire
	except ImportError as e:
		print("[InfoBar] tasta rosie: HdsHbbtvPornire lipseste:", e)
		return 0
	return HdsHbbtvPornire.apasaRosu(ecran)


def hdsFavoriteCanalVazut(ecran):
	"""FAV tinut apasat pe bara (si cand esti pe canal, nu numai in lista):
	canalul de acum intra in Favorite (Favorite TV sau radio, dupa canal), prin aceeasi functie ca tasta FAV din lista
	si steluta din web (Components/HdsFavorite.py). E deja acolo: intrebarea scurta de scoatere, cu Da ales. Ce s-a
	facut spune un mesaj care dispare singur dupa 3 s."""
	try:
		from Components import HdsFavorite
	except ImportError as e:
		print("[InfoBar] FAV tinut apasat: HdsFavorite lipseste:", e)
		return
	from Screens.MessageBox import MessageBox
	from Tools import Notifications

	def arata(text, eroare=False):
		Notifications.AddPopup(text, MessageBox.TYPE_ERROR if eroare else MessageBox.TYPE_INFO, 3, "HdsFavorite")

	ref = ecran.session.nav.getCurrentlyPlayingServiceReference()
	text = ref.toString() if ref is not None and ref.valid() else ""
	if not HdsFavorite.se_poate(text):
		arata(_("Canalul acesta nu se poate pune în buchete."), True)
		return
	from ServiceReference import ServiceReference
	nume = ServiceReference(ref).getServiceName() or ref.getName() or ""
	tip = HdsFavorite.tip_canal(text)
	ref_b = HdsFavorite.ref_favorite(tip)
	if HdsFavorite.este_in(text, ref_b):
		def raspuns(da=False):
			if da:
				rez = HdsFavorite.scoate(text, ref_b, tip, nume)
				arata(rez.mesaj(), not rez.ok)
		ecran.session.openWithCallback(raspuns, MessageBox, HdsFavorite.intrebare_scoatere(nume, ref_b),
			MessageBox.TYPE_YESNO)
		return
	rez = HdsFavorite.adauga(text, ref_b, tip, nume)
	arata(rez.mesaj(), not rez.ok)


def hdsPortalSauMesaj(ecran):
	"""Portal (KEY_WWW): lista extensiilor, fara intrebare, si peste ea, cateva secunde, starea HbbTV a canalului
	(Components/HdsPortal.py). Fara modul, numai lista extensiilor."""
	try:
		from Components import HdsPortal
	except ImportError as e:
		print("[InfoBar] tasta Portal: HdsPortal lipseste:", e)
		from Screens.PluginBrowser import PluginBrowser
		ecran.session.open(PluginBrowser)
		return
	HdsPortal.apasaPortal(ecran)


def hdsEsteCanal(ref):
	"""True cand referinta e a unui canal (TV, radio, flux din retea), nu a unui fisier de pe disc (filmele si
	inregistrarile au calea lor, care incepe cu /)."""
	if ref is None or not ref.valid():
		return False
	return not (ref.getPath() or "").startswith("/")


_hdsCeasDupaPlayer = []


def hdsDupaPlayer():
	"""Playerul de filme s-a inchis fiindca a pornit un canal peste film: evStart-ul canalului l-a primit playerul
	(era in varful stivei barelor), nu bara. Dupa ce bara ajunge din nou in fata, ecranul radio si bara se potrivesc
	cu ce merge, ca la un zap obisnuit."""
	ceas = eTimer()
	ceas.callback.append(_hdsDupaPlayer)
	ceas.start(0, True)
	_hdsCeasDupaPlayer[:] = [ceas]


def _hdsDupaPlayer():
	del _hdsCeasDupaPlayer[:]
	ib = InfoBar.instance
	if ib is None:
		return
	try:
		leg = getattr(ib, "hdsRadio", None)
		if leg is not None:
			leg.dupaListaRadio()
		ib.serviceStarted()
	except Exception as e:
		print("[InfoBar] dupa playerul inchis de un canal: %s" % e)
	# evStart si evUpdatedInfo ale canalului le-a primit playerul: bara alege acum sunetul si subtitrarea, ca dupa un zap
	# (fara asta canalul ramanea fara subtitrare pana la zapul urmator)
	try:
		alege = getattr(ib, "hdsAlegeDinNou", None)
		if alege is not None:
			alege()
	except Exception as e:
		print("[InfoBar] pistele dupa playerul inchis de un canal: %s" % e)


def hdsDeschideSetariVideo(session):
	"""rezolutia si frecventa, spatiul de culoare, HDR: Screens/VideoSetup.py, care intreaba dupa schimbare si se
	intoarce singur la modul vechi daca televizorul nu arata imaginea"""
	from Screens.VideoSetup import VideoSetup
	session.open(VideoSetup)


def hdsApasareLunga(porneste):
	"""Logica apasarii lungi a butoanelor colorate (Components/HdsTasteRapide.ApasareLunga); None fara modul (atunci
	harta lasa toate tastele mai departe)."""
	try:
		from Components.HdsTasteRapide import ApasareLunga
	except ImportError as e:
		print("[InfoBar] apasarea lunga a butoanelor colorate lipseste:", e)
		return None
	return ApasareLunga(porneste)


def hdsHbbtvDeschisa():
	"""Aplicatia HbbTV e deschisa acum (Components/HdsHbbtvPornire.deschisa); False fara modul."""
	try:
		from Components import HdsHbbtvPornire
	except ImportError:
		return False
	return HdsHbbtvPornire.deschisa()


def hdsFaActiuneaLunga(ecran, actiune):
	"""Actiunea aleasa pentru apasarea lunga a unui buton colorat (Components/HdsTasteRapide.ACTIUNI_DISPONIBILE), cu
	ecranul tastei ei: EPG (ca tasta EPG), meniul principal (MENU), lista extensiilor, meniul Informatii (ca POWER lung
	cu meniul lui), pistele audio, subtitrarile, lista de canale (OK)."""
	if actiune == "epg":
		ecran.showEventInfoPlugins()
	elif actiune == "menu":
		ecran.mainMenu()
	elif actiune == "plugins":
		from Screens.PluginBrowser import PluginBrowser
		ecran.session.open(PluginBrowser)
	elif actiune == "info":
		from Screens.Menu import MainMenu, mdom
		from Components.HdsTasteRapide import cauta_meniu
		nod = cauta_meniu(mdom.getroot(), "information")
		if nod is None:
			print("[InfoBar] apasare lunga: meniul information lipseste din menu.xml")
			return
		ecran.session.infobar = ecran
		ecran.session.openWithCallback(ecran.mainMenuClosed, MainMenu, nod)
	elif actiune == "audio":
		ecran.audioSelection()
	elif actiune == "subtitle":
		ecran.subtitleSelection()
	elif actiune == "channellist":
		ecran.openServiceList()
	else:
		print("[InfoBar] apasare lunga: actiune necunoscuta %r" % (actiune,))


class InfoBar(InfoBarBase, InfoBarShowHide,
	InfoBarNumberZap, InfoBarChannelSelection, InfoBarMenu, InfoBarEPG, InfoBarRdsDecoder,
	InfoBarInstantRecord, InfoBarAudioSelection, InfoBarSubtitleSelection,
	HelpableScreen, InfoBarAdditionalInfo, InfoBarNotifications, InfoBarDish, InfoBarUnhandledKey,
	InfoBarSubserviceSelection, InfoBarTimeshift, InfoBarSeek,
	InfoBarSummarySupport, InfoBarTimeshiftState, InfoBarTeletextPlugin, InfoBarExtensions,
	InfoBarPiP, InfoBarPlugins, InfoBarSubtitleSupport, InfoBarServiceErrorPopupSupport, InfoBarJobman,
	InfoBarFilmRefuz, Screen):
	
	ALLOW_SUSPEND = True
	instance = None

	def __init__(self, session):
		Screen.__init__(self, session)
		self["actions"] = HelpableActionMap(self, "InfobarActions",
			{
				"showMovies": (self.showMovies, _("Play recorded movies...")),
				"showRadio": (self.showRadio, _("Show the radio player...")),
				"showTv": (self.showTv, _("Show the tv player...")),
			}, prio=2)

		# HDSatelit: tastele Viper fara actiune inainte (vezi hdsAlegeFormatImagine mai sus)
		self["HdsTasteActions"] = HelpableActionMap(self, "HdsInfobarActions",
			{
				"ghidProgram": (self.showEventInfoPlugins, _("show single service EPG...")),
				"mediaPlayer": (self.hdsMediaPlayer, _("Media player")),
				"listaTimere": (self.hdsListaTimere, _("Înregistrări programate")),
				"extensii": (self.hdsExtensii, _("Lista extensiilor și dacă acest canal are HbbTV")),
				# FAV: scurt (la eliberare) lista pe Favorite, ca pana acum; tinut apasat canalul de acum in Favorite
				"favoriteApasat": self.hdsFavoriteApasat,
				"favoriteLung": (self.hdsFavoriteLung, _("FAV ținut apăsat: canalul de acum în Favorite sau scos de acolo")),
				"favorite": (self.hdsFavoriteEliberat, _("Favourites")),
				"formatImagine": (self.hdsFormatImagine, _("Aspect ratio")),
				"setariVideo": (self.hdsSetariVideo, _("A/V Settings")),
				"teletext": (self.hdsTeletext, _("View teletext...")),
				"hbbtvRosu": (self.hdsHbbtvRosu, _("Aplicația HbbTV a canalului (butonul roșu)")),
			}, prio=2)

		# HDSatelit: apasarea lunga a butoanelor colorate (data/keymap.xml, HdsTasteColorateActions), cu actiunea aleasa
		# in Butoane colorate si taste rapide (Components/HdsTasteRapide.py, ApasareLunga). Prioritatea -2: harta vede
		# apasarea inaintea ecranului radio (-1) si a hartilor barei, dar o lasa mai departe, deci apasarea scurta ramane
		# cum era; eliberarea e oprita numai dupa o apasare lunga facuta.
		self.hdsRosuLuat = False
		self.hdsTasteLungi = hdsApasareLunga(self.hdsPornesteTastaLunga)
		self["HdsTasteColorateActions"] = HelpableActionMap(self, "HdsTasteColorateActions",
			{
				"rosuApasat": lambda: self.hdsTastaApasata("red"),
				"rosuLung": (lambda: self.hdsTastaTinuta("red"), _("Roșu (apăsare lungă)")),
				"rosuEliberat": lambda: self.hdsTastaEliberata("red"),
				"verdeApasat": lambda: self.hdsTastaApasata("green"),
				"verdeLung": (lambda: self.hdsTastaTinuta("green"), _("Verde (apăsare lungă)")),
				"verdeEliberat": lambda: self.hdsTastaEliberata("green"),
				"galbenApasat": lambda: self.hdsTastaApasata("yellow"),
				"galbenLung": (lambda: self.hdsTastaTinuta("yellow"), _("Galben (apăsare lungă)")),
				"galbenEliberat": lambda: self.hdsTastaEliberata("yellow"),
				"albastruApasat": lambda: self.hdsTastaApasata("blue"),
				"albastruLung": (lambda: self.hdsTastaTinuta("blue"), _("Albastru (apăsare lungă)")),
				"albastruEliberat": lambda: self.hdsTastaEliberata("blue"),
			}, prio=-2)

		self.allowPiP = True
		
		for x in HelpableScreen, \
				InfoBarBase, InfoBarShowHide, \
				InfoBarNumberZap, InfoBarChannelSelection, InfoBarMenu, InfoBarEPG, InfoBarRdsDecoder, \
				InfoBarInstantRecord, InfoBarAudioSelection, InfoBarSubtitleSelection, InfoBarUnhandledKey, \
				InfoBarAdditionalInfo, InfoBarNotifications, InfoBarDish, InfoBarSubserviceSelection, \
				InfoBarTimeshift, InfoBarSeek, InfoBarSummarySupport, InfoBarTimeshiftState, \
				InfoBarTeletextPlugin, InfoBarExtensions, InfoBarPiP, InfoBarSubtitleSupport, InfoBarJobman, \
				InfoBarPlugins, InfoBarServiceErrorPopupSupport, InfoBarFilmRefuz:
			x.__init__(self)

		self.helpList.append((self["actions"], "InfobarActions", [("showMovies", _("view recordings..."))]))
		self.helpList.append((self["actions"], "InfobarActions", [("showRadio", _("hear radio..."))]))

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evUpdatedEventInfo: self.__eventInfoChanged
			})

		self.hdsPornesteEcranRadio()

		self.current_begin_time=0
		self.hdsRefEmisiune = None
		self.hdsRefLaListaRadio = None
		# intrarea in standby (Screens/Standby.py creste config.misc.standbyCounter) uita inceputul emisiunii tinut minte:
		# la trezire acelasi canal porneste din nou cu ecranul Standby inca deasupra barei (serviceStarted fara execing si
		# fara canal nou, deci fara current_begin_time = 0), iar primul EIT de dupa trezire ar fi luat drept emisiune noua
		# daca emisiunea s-a schimbat in standby (bara aparea singura la cateva secunde dupa trezire). Acum primul EIT
		# e emisiunea de acum; „Bara la schimbarea emisiunii” merge ca inainte pentru emisiunile noi de dupa trezire.
		config.misc.standbyCounter.addNotifier(self.hdsLaStandby, initial_call=False)
		# textul marit: orele emisiunii de acum din bara nu se mai lipesc de titlu (getattr: ecranele false ale probelor)
		getattr(self, "onLayoutFinish", []).append(self.hdsOreleMarite)
		assert InfoBar.instance is None, "class InfoBar is a singleton class and just one instance of this class is allowed!"
		InfoBar.instance = self
		# HDSatelit: copiile de teletext ale canalelor vazute, in fundal (Components/HdsTeletextCopie.py)
		try:
			from Components import HdsTeletextCopie
			HdsTeletextCopie.porneste(self.session)
		except ImportError as e:
			print("[InfoBar] copiile de teletext lipsesc:", e)
		# HDSatelit: mouse-ul pus direct in receptor: cursorul si clicurile (Components/HdsMouseUsb.py), pornit singur
		# la primul pachet al unui mouse, si la cald
		try:
			from Components import HdsMouseUsb
			HdsMouseUsb.porneste(self.session)
		except ImportError as e:
			print("[InfoBar] mouse-ul USB lipseste:", e)

	def hdsPornesteEcranRadio(self):
		"""Ecranul radio pe tot ecranul (Screens/HdsEcranRadio.py): fereastra de sub bara, aratata cat merge un post
		de radio, si harta tastelor ei (prioritatea -1, inaintea hartilor barei), pornita numai atunci. Fara ele (skin
		stricat, modul lipsa) bara merge ca inainte."""
		self.hdsListaRadioDeschisa = False
		self.hdsRadio = None
		try:
			from Screens import HdsEcranRadio
		except ImportError as e:
			print("[InfoBar] ecranul radio lipseste:", e)
			return
		leg = HdsEcranRadio.faLegatura(self)
		if leg is None:
			return
		self.hdsRadio = leg
		# OK, EXIT, sagetile, GALBEN (vizualizarea urmatoare), ALBASTRU (culorile urmatoare): HdsEcranRadio.actiuniHarta
		self["HdsRadioActions"] = HdsEcranRadio.HartaRadio(HdsEcranRadio.CONTEXTE_TASTE,
			HdsEcranRadio.actiuniHarta(leg), prio=-1)
		leg.legaHarta(self["HdsRadioActions"])

	def __onClose(self):
		InfoBar.instance = None

	# cat ramane intre capatul titlului emisiunii si ora de inceput de langa el, cu textul marit
	HDS_LOC_TITLU_ORA = 12

	def hdsOreleMarite(self):
		"""Textul marit (Marimea textului peste 100 %): orele emisiunii de acum din bara (ClockToText peste EventTime
		StartTime / EndTime, ca in tema Pro: inceputul aliniat la dreapta, langa titlu, apoi sfarsitul) aveau caseta
		facuta pentru 100 %, iar la 130 % inceputul iesea spre stanga pana in capatul titlului ("...(219)11:45- 12:15").
		O caseta de ora mai ingusta decat ora (masurata cu "88:88" in fontul ei) creste: cea aliniata la dreapta spre
		stanga, cealalta spre dreapta; un titlu de pe acelasi rand se opreste la HDS_LOC_TITLU_ORA px inaintea textului
		orei, iar un titlu din dreapta unei ore aliniate la stanga ("Urmeaza 11:45 titlul") incepe la fel de departe dupa ea
		(titlul care nu incape deruleaza). Geometria nu depinde de text: se potriveste o data, la asezare. La 100 % nu se
		schimba nimic."""
		try:
			from Components import HdsMarireText as M
			if not M.marit():
				return
			from enigma import ePoint, eSize
			ore, titluri = [], []
			for r in self.renderer:
				inst = getattr(r, "instance", None)
				conv = getattr(r, "source", None)
				if inst is None or conv is None or not hasattr(inst, "calculateSize"):
					continue
				fel = conv.__class__.__name__
				sub = getattr(conv, "source", None)
				ora = fel == "ClockToText" and sub is not None and sub.__class__.__name__ == "EventTime" and \
					str(getattr(sub, "converter_arguments", "")) in ("StartTime", "EndTime")
				if ora:
					ore.append((r, inst, str(getattr(conv, "converter_arguments", "") or "")))
				elif fel == "EventName":
					titluri.append(inst)
			for r, inst, fmt in ore:
				p, z = inst.position(), inst.size()
				x, y, w, h = p.x(), p.y(), z.width(), z.height()
				model = fmt[7:] if fmt.startswith("Format:") else "%H:%M"
				model = model.replace("%H", "88").replace("%M", "88")
				vechi = getattr(r, "text", "")
				inst.setText(model)
				nevoie = int(inst.calculateSize().width()) + 4
				inst.setText(vechi or "")
				dreapta = False
				try:
					dreapta = dict(r.skinAttributes or ()).get("halign") == "right"
				except Exception:
					pass
				if nevoie > w:
					if dreapta:
						x = x + w - nevoie
					w = nevoie
					inst.move(ePoint(x, y))
					inst.resize(eSize(w, h))
				for t in titluri:
					tp, tz = t.position(), t.size()
					if tp.y() >= y + h or tp.y() + tz.height() <= y:
						continue   # alt rand
					if dreapta and tp.x() < x:
						# ora aliniata la dreapta, titlul in stanga ei: titlul se opreste inaintea inceputului textului orei
						capat = x + w - nevoie - self.HDS_LOC_TITLU_ORA
						if tp.x() + tz.width() > capat:
							t.resize(eSize(max(1, capat - tp.x()), tz.height()))
					elif not dreapta and tp.x() > x:
						# ora aliniata la stanga, titlul in dreapta ei: titlul incepe dupa capatul textului orei
						inceput = x + nevoie + self.HDS_LOC_TITLU_ORA
						if tp.x() < inceput:
							t.move(ePoint(inceput, tp.y()))
							t.resize(eSize(max(1, tp.x() + tz.width() - inceput), tz.height()))
		except Exception as e:
			print("[InfoBar] orele cu textul marit: %s" % e)

	def hdsLaStandby(self, configElement=None):
		"""La intrarea in standby: inceputul emisiunii tinut minte se uita (vezi notifierul din __init__)."""
		self.current_begin_time = 0

	def __eventInfoChanged(self):
		if self.execing:
			service = self.session.nav.getCurrentService()
			old_begin_time = self.current_begin_time
			info = service and service.info()
			ptr = info and info.getEvent(0)
			self.current_begin_time = ptr and ptr.getBeginTime() or 0
			alt_post = self.hdsAltPostLaEmisiune()
			if config.usage.show_infobar_on_event_change.value:
				if old_begin_time and old_begin_time != self.current_begin_time:
					# emisiunea altui post nu e o emisiune noua: postul s-a schimbat fara serviceStarted la bara, deci
					# inceputul emisiunii postului vechi a ramas (lista radio separata o trateaza la inchidere,
					# hdsDupaListaRadio; aici raman celelalte cai). Pe un post de radio cu ecranul radio si „Bara la
					# schimbarea postului” pe Nu bara nu se arata; pe TV si cu Da ramane ca inainte
					radio = getattr(self, "hdsRadio", None)
					if alt_post and radio is not None and radio.faraBaraLaZap():
						return
					self.doShow()

	def hdsAltPostLaEmisiune(self):
		"""True cand emisiunea citita acum e a altui post decat emisiunea citita data trecuta (referinta tinuta in
		hdsRefEmisiune)."""
		text = self.hdsRefCurenta()
		alt = text != self.hdsRefEmisiune
		self.hdsRefEmisiune = text
		return alt

	def hdsRefCurenta(self):
		"""Textul referintei serviciului care merge acum ("" fara serviciu)."""
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		return ref.toString() if ref is not None else ""

	def hdsDupaListaRadio(self):
		"""Dupa lista radio separata (ChannelSelectionRadio, InfoBarBase): evStart-ul posturilor pornite din ea l-a
		primit lista, nu bara, iar Session.popCurrent arata din nou bara daca ea se vedea cand s-a deschis lista. Cand
		postul s-a schimbat cat lista era deschisa si merge un post de radio cu ecranul radio si „Bara la schimbarea
		postului” pe Nu (faraBaraLaZap), bara face ce face serviceStarted la un zap cu ea in fata: nu ramane pe ecran,
		iar emisiunea de acum a postului nou devine emisiunea citita (0 daca EIT-ul lui n-a sosit inca). Astfel primul
		EIT al postului nou nu e luat drept emisiune noua, iar o emisiune noua reala pe el arata bara ca inainte, si
		cand EIT-ul primei emisiuni a sosit cat lista era deschisa. Pe TV, cu Da si fara schimbare de post nu se
		schimba nimic."""
		ref_la_lista, self.hdsRefLaListaRadio = self.hdsRefLaListaRadio, None
		ref = self.hdsRefCurenta()
		if ref == ref_la_lista:
			return
		radio = getattr(self, "hdsRadio", None)
		if radio is None or not radio.faraBaraLaZap():
			return
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		ptr = info and info.getEvent(0)
		self.current_begin_time = ptr and ptr.getBeginTime() or 0
		self.hdsRefEmisiune = ref
		if self.shown:
			self.hide()
			self.hideTimer.stop()

	# metoda __checkServiceStarted era definita de doua
	# ori in aceasta clasa -- Python pastreaza doar ULTIMA definitie, deci aceasta (care oricum
	# apela self.__serviceStarted, o metoda care nici nu exista in clasa) era cod mort, inaccesibil.
	# Stearsa; a doua definitie (mai jos, dupa serviceStarted()) e cea chiar folosita.

	def serviceStarted(self):  #override from InfoBarShowHide
		new = self.servicelist.newServicePlayed()
		if self.execing:
			# pe un post de radio cu ecranul radio pornit bara nu se mai arata singura (setarea „Bara la schimbarea
			# postului”): ecranul radio are deja toate datele
			radio = getattr(self, "hdsRadio", None)
			if radio is not None and radio.faraBaraLaZap():
				self.current_begin_time = 0
				return
			InfoBarShowHide.serviceStarted(self)
			self.current_begin_time=0
		elif not self.__checkServiceStarted in self.onShown and new:
			self.onShown.append(self.__checkServiceStarted)

	def __checkServiceStarted(self):
		self.serviceStarted()
		self.onShown.remove(self.__checkServiceStarted)

	def showTv(self):
		self.showTvChannelList(True)

	def showRadio(self, faraPornire=False):
		# amandoua listele radio pornesc la deschidere config.radio.lastservice (ChannelSelectionRadio.onCreate, zap-ul
		# din setModeRadio): postul de radio care merge acum (pornit din cautare, din web, din cifre) devine ultimul
		# post, ca tasta RADIO sa nu-l schimbe; un canal TV nu il atinge.
		# faraPornire (sageata sus pe bara TV): numai lista radio, cu cursorul pe ultimul post; canalul de acum merge
		# pana se alege un post cu OK, iar EXIT il lasa neatins
		leg = getattr(self, "hdsRadio", None)
		ref_radio = leg.refRadioCurenta() if leg is not None else None
		if ref_radio and config.radio.lastservice.value != ref_radio:
			config.radio.lastservice.value = ref_radio
			config.radio.lastservice.save()
		if config.usage.e1like_radio_mode.value:
			self.showRadioChannelList(not faraPornire)
		else:
			self.rds_display.hide() # in InfoBarRdsDecoder
			self.hdsListaRadioDeschisa = True
			# serviciul de dinainte de lista, pentru hdsDupaListaRadio (lista porneste la deschidere ultimul post)
			self.hdsRefLaListaRadio = self.hdsRefCurenta()
			from Screens.ChannelSelection import ChannelSelectionRadio
			self.session.openWithCallback(self.ChannelSelectionRadioClosed, ChannelSelectionRadio, self, faraPornire)

	def ChannelSelectionRadioClosed(self, *arg):
		self.hdsListaRadioDeschisa = False
		# chemat dupa Session.popCurrent, deci dupa ce bara a fost aratata din nou (daca se vedea la deschiderea listei)
		self.hdsDupaListaRadio()
		# posturile alese in lista au pornit cat lista era deasupra: ecranul radio se potriveste acum cu ce merge
		leg = getattr(self, "hdsRadio", None)
		if leg is not None:
			leg.dupaListaRadio()
		# textul radio al barei ramane ascuns cat se vede ecranul radio: il are deja pe ecran
		try:
			from Components.HdsRadioSetari import ecran_radio_vizibil
			vizibil = ecran_radio_vizibil()
		except ImportError:
			vizibil = False
		if not vizibil:
			self.rds_display.show()  # in InfoBarRdsDecoder

	def showMovies(self):
		from Screens.MovieSelection import MovieSelection
		self.session.openWithCallback(self.movieSelected, MovieSelection)

	def hdsMediaPlayer(self):
		try:
			from Plugins.Extensions.MediaPlayer.plugin import MediaPlayer
		except ImportError as e:
			print("[InfoBar] tasta Mplay: playerul media lipseste:", e)
			return
		self.session.open(MediaPlayer)

	def hdsListaTimere(self):
		from Screens.TimerEdit import TimerEditList
		self.session.open(TimerEditList)

	def hdsExtensii(self):
		hdsPortalSauMesaj(self)

	def hdsHbbtvRosu(self):
		rez = hdsHbbtvRosu(self)
		# ROSU tinut apasat nu mai face si actiunea lunga cand apasarea lui a pornit aplicatia HbbTV (hdsTastaApasata
		# sterge semnul la fiecare apasare: harta apasarii lungi vine inaintea acesteia)
		self.hdsRosuLuat = bool(rez)
		return rez

	# butoanele colorate tinute apasat (harta HdsTasteColorateActions); fara modulul HdsTasteRapide, nimic nu se schimba
	def hdsTastaApasata(self, buton):
		if buton == "red":
			self.hdsRosuLuat = False
		t = getattr(self, "hdsTasteLungi", None)
		return t.apasat(buton) if t is not None else 0

	def hdsTastaTinuta(self, buton):
		t = getattr(self, "hdsTasteLungi", None)
		return t.lung(buton) if t is not None else 0

	def hdsTastaEliberata(self, buton):
		t = getattr(self, "hdsTasteLungi", None)
		return t.eliberat(buton) if t is not None else 0

	def hdsPornesteTastaLunga(self, buton, actiune):
		"""Actiunea apasarii lungi (ApasareLunga.porneste) -> True cand s-a facut. ROSU ramane al aplicatiei HbbTV cand
		apasarea lui a pornit-o sau cand ea e deschisa, iar tastele colorate raman ale ecranului radio cat se vede el:
		atunci False, si totul merge ca pana acum. O eroare a actiunii ramane numai in jurnal (nimic pe televizor)."""
		if buton == "red" and (getattr(self, "hdsRosuLuat", False) or hdsHbbtvDeschisa()):
			return False
		radio = getattr(self, "hdsRadio", None)
		if radio is not None and radio._tastaColorata():
			return False
		try:
			hdsFaActiuneaLunga(self, actiune)
		except Exception as e:
			print("[InfoBar] %s tinut apasat (%s): %s: %s" % (buton, actiune, type(e).__name__, e))
		return True

	def hdsFavorite(self):
		# ca tasta albastra din lista de canale: lista buchetelor (favoritele), apoi lista se deschide
		self.servicelist.showFavourites()
		self.session.execDialog(self.servicelist)

	# FAV are doua sensuri: apasarea scurta lucreaza la eliberare, cea lunga la flagLong; la apasare
	# (favoriteApasat) numai semnul se sterge, ca la tasta AUDIO (InfoBarAudioSelection)
	def hdsFavoriteApasat(self):
		self.hdsFavLung = False

	def hdsFavoriteLung(self):
		self.hdsFavLung = True
		hdsFavoriteCanalVazut(self)

	def hdsFavoriteEliberat(self):
		if getattr(self, "hdsFavLung", False):
			self.hdsFavLung = False
			return
		self.hdsFavorite()

	def hdsFormatImagine(self):
		hdsAlegeFormatImagine(self.session)

	def hdsSetariVideo(self):
		hdsDeschideSetariVideo(self.session)

	def hdsTeletext(self):
		hdsTeletextSauMesaj(self)

	def movieSelected(self, service):
		if service is not None:
			self.session.open(MoviePlayer, service)

class MoviePlayer(InfoBarBase, InfoBarShowHide, \
		InfoBarMenu, \
		InfoBarSeek, InfoBarShowMovies, InfoBarAudioSelection, InfoBarSubtitleSelection, HelpableScreen, InfoBarNotifications,
		InfoBarServiceNotifications, InfoBarPVRState, InfoBarCueSheetSupport, InfoBarSimpleEventView,
		InfoBarMoviePlayerSummarySupport, InfoBarSubtitleSupport, Screen, InfoBarTeletextPlugin,
		InfoBarServiceErrorPopupSupport, InfoBarExtensions, InfoBarPlugins, InfoBarPiP, InfoBarFilmRefuz):

	ENABLE_RESUME_SUPPORT = True
	ALLOW_SUSPEND = True
		
	def __init__(self, session, service):
		Screen.__init__(self, session)
		
		# HDSatelit (tastele Viper): EPG = detaliile emisiunii inregistrate, cele doua taste cu desen de
		# ecran ca in bara; tasta SUBT prin InfoBarSubtitleSelection (lipsea din player)
		self["actions"] = HelpableActionMap(self, "MoviePlayerActions",
			{
				"leavePlayer": (self.leavePlayer, _("leave movie player...")),
				"eventInfo": (self.openEventView, _("show event details")),
				"formatImagine": (self.hdsFormatImagine, _("Aspect ratio")),
				"setariVideo": (self.hdsSetariVideo, _("A/V Settings")),
				"teletext": (self.hdsTeletext, _("View teletext...")),
			})
		
		self.allowPiP = False
		
		for x in HelpableScreen, InfoBarShowHide, InfoBarMenu, \
				InfoBarBase, InfoBarSeek, InfoBarShowMovies, \
				InfoBarAudioSelection, InfoBarSubtitleSelection, InfoBarNotifications, InfoBarSimpleEventView, \
				InfoBarServiceNotifications, InfoBarPVRState, InfoBarCueSheetSupport, \
				InfoBarMoviePlayerSummarySupport, InfoBarSubtitleSupport, \
				InfoBarTeletextPlugin, InfoBarServiceErrorPopupSupport, InfoBarExtensions, \
				InfoBarPlugins, InfoBarPiP, InfoBarFilmRefuz:
			x.__init__(self)

		# 0.2.6: editorul de marcaje (Plugins/Extensions/HdsCutListEditor) e al
		# playerului, nu o extensie: un rand in lista tastei albastre, numai cand ce merge are marcaje (cue sheet)
		self.addExtension((self.hdsNumeEditorMarcaje, self.hdsEditorMarcaje, self.hdsAreMarcaje))

		self.lastservice = session.nav.getCurrentlyPlayingServiceReference()
		session.nav.playService(service)
		self.returning = False
		self.onClose.append(self.__onClose)
		# un canal pornit peste film din alt loc (web, aplicatiile de telefon, ghidul din web): playerul se inchide si
		# canalul ramane. Altfel playerul ramanea deschis pe canal: JOS deschidea lista de filme, iar ecranul radio nu
		# pornea (bara principala nu era in varful stivei).
		self.hdsCanalPeste = False
		self.hdsCeasCanal = eTimer()
		self.hdsCeasCanal.callback.append(self.hdsVerificaCanalul)
		self.hdsUrmaritorCanal = ServiceEventTracker(screen=self, eventmap={
			iPlayableService.evStart: self.hdsLaPornire,
		})
		self.onExecBegin.append(self.hdsLaPornire)

	def __onClose(self):
		self.hdsCeasCanal.stop()
		if self.hdsCanalPeste and hdsEsteCanal(self.session.nav.getCurrentlyPlayingServiceReference()):
			# canalul pornit peste film ramane; bara si ecranul radio il iau acum. O subtitrare pornita de player pe canal
			# se opreste cat fereastra lui mai exista (bara o alege din nou, in hdsDupaPlayer), iar evenimentele canalului
			# merg de acum la bara: altfel ramaneau ale playerului inchis si nu le mai primea nimeni
			if self.subtitles_enabled:
				self.subtitles_enabled = False
			ServiceEventTracker.hdsPreiaServiciul()
			hdsDupaPlayer()
			return
		self.session.nav.playService(self.lastservice)

	def hdsLaPornire(self):
		"""La evStart navigatia n-a pus inca referinta noua, iar la intoarcerea in fata raspunsul ecranului de deasupra
		(lista filmelor) vine dupa: verificarea se face imediat dupa."""
		self.hdsCeasCanal.start(0, True)

	def hdsVerificaCanalul(self):
		"""Daca merge un canal (nu un fisier de pe disc), playerul se inchide si canalul ramane. Cu alt ecran deasupra
		(lista filmelor, intrebarea de oprire) se inchide cand ajunge din nou in fata."""
		if not hdsEsteCanal(self.session.nav.getCurrentlyPlayingServiceReference()):
			self.hdsCanalPeste = False
			return
		self.hdsCanalPeste = True
		if self.session.current_dialog is not self or not self.execing:
			return
		print("[MoviePlayer] a pornit un canal peste film: playerul se inchide, canalul ramane")
		self.close()

	def hdsNumeEditorMarcaje(self):
		return _("Editor marcaje")

	def hdsAreMarcaje(self):
		"""True cand ce merge acum are marcaje (cue sheet): inregistrarile, nu fluxurile fara marcaje."""
		service = self.session.nav.getCurrentService()
		return service is not None and service.cueSheet() is not None

	def hdsEditorMarcaje(self):
		try:
			from Plugins.Extensions.HdsCutListEditor.plugin import deschide
		except ImportError as e:
			print("[MoviePlayer] editorul de marcaje lipseste:", e)
			return
		deschide(self.session)

	def handleLeave(self, how):
		self.is_closing = True
		if how == "ask":
			if config.usage.setup_level.index < 2: # -expert
				list = (
					(_("Yes"), "quit"),
					(_("No"), "continue")
				)
			else:
				# texte proprii: cele vechi erau traduse „lista de înregistrări” / „această înregistrare” si la filme
				list = (
					(_("Yes"), "quit"),
					(_("Da, înapoi la lista de filme"), "movielist"),
					(_("Da, și șterge filmul"), "quitanddelete"),
					(_("No"), "continue"),
					(_("No, but restart from begin"), "restart")
				)

			from Screens.ChoiceBox import ChoiceBox
			# acelasi text la filme si la inregistrari (textul vechi era tradus „... acestei înregistrări”); fereastra pe
			# masura listei (HdsFilmOprire2 sau HdsFilmOprire5 in HDSatelit/skin.xml), pe alte skinuri ChoiceBox
			self.session.openWithCallback(self.leavePlayerConfirmed, ChoiceBox, title=_("Oprești redarea?"), list = list,
				skin_name = ["HdsFilmOprire%d" % len(list)])
		else:
			self.leavePlayerConfirmed([True, how])

	def leavePlayer(self):
		self.handleLeave(config.usage.on_movie_stop.value)

	def hdsFormatImagine(self):
		hdsAlegeFormatImagine(self.session)

	def hdsSetariVideo(self):
		hdsDeschideSetariVideo(self.session)

	def hdsTeletext(self):
		hdsTeletextSauMesaj(self)

	def deleteConfirmed(self, answer):
		if answer:
			self.leavePlayerConfirmed((True, "quitanddeleteconfirmed"))
		else:
			# filmul nu se sterge si playerul ramane: intrebarea de reluare si mesajul de refuz lucreaza din nou
			self.is_closing = False

	def leavePlayerConfirmed(self, answer):
		answer = answer and answer[1]

		if answer in ("quitanddelete", "quitanddeleteconfirmed"):
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			from enigma import eServiceCenter
			serviceHandler = eServiceCenter.getInstance()
			info = serviceHandler.info(ref)
			name = info and info.getName(ref) or _("this recording")

			if answer == "quitanddelete":
				from Screens.MessageBox import MessageBox
				self.session.openWithCallback(self.deleteConfirmed, MessageBox, _("Do you really want to delete %s?") % name)
				return

			elif answer == "quitanddeleteconfirmed":
				offline = serviceHandler.offlineOperations(ref)
				if offline.deleteFromDisk(0):
					from Screens.MessageBox import MessageBox
					self.session.openWithCallback(self.close, MessageBox, _("You cannot delete this!"), MessageBox.TYPE_ERROR)
					return

		if answer in ("quit", "quitanddeleteconfirmed"):
			self.close()
		elif answer == "movielist":
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			self.returning = True
			# dupa un film refuzat (InfoBarFilmRefuz) cursorul trece pe filmul urmator
			urmatorul = getattr(self, "hdsListaUrmatorul", False)
			self.hdsListaUrmatorul = False
			from Screens.MovieSelection import MovieSelection
			self.session.openWithCallback(self.movieSelected, MovieSelection, ref, urmatorul)
			self.session.nav.stopService()
		else:
			# playerul ramane („Nu”, „Nu, de la început”, pauza la sfarsit, EXIT pe intrebare): intrebarea de reluare si
			# mesajul de refuz lucreaza din nou
			self.is_closing = False
			if answer == "restart":
				self.doSeek(0)
				self.setSeekState(self.SEEK_STATE_PLAY)

	def doEofInternal(self, playing):
		if not self.execing:
			return
		if not playing :
			return
		self.handleLeave(config.usage.on_movie_eof.value)

	def showMovies(self):
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		from Screens.MovieSelection import MovieSelection
		self.session.openWithCallback(self.movieSelected, MovieSelection, ref)

	def movieSelected(self, service):
		if service is not None:
			self.is_closing = False
			self.session.nav.playService(service)
			self.returning = False
		elif self.returning:
			self.close()
