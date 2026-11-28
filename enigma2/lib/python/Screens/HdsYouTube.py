# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Native YouTube screen (0.8.0, YTN1): Home (recommended for the receiver's country), Search (on-screen keyboard and
history), Live, History (watched films); channels and playlists open in the same list. OK plays the film in the image's
player (MPD for films, HLS for live). No browser, no account: data from Components/HdsYouTube.py.

YTN2 (0.8.0): a row of rubrics like YouTube's own (Home, Music with the charts of a chosen country, Gaming, News,
Sports, Podcasts, Live, Search, History), LEFT/RIGHT along it; the channel stops while the screen is open and a
backdrop in its colour stays under the keyboard and the menus.

YTN3 (0.8.x): the pages as a grid of tiles, like YouTube on a TV (Components/HdsYouTubeDale.py): the film's picture,
its title on two lines and the channel under it, the length on the picture; a shelf of a page is a row that moves
sideways. Arrows move in the grid, UP from the first row goes to the row of rubrics (LEFT/RIGHT there), CH+/CH- change
the rubric from anywhere. The pictures load on two threads (connections kept open), only for the visible tiles and one
row more, and are decoded one at a time; the list keeps only the visible rows and a move redraws two tiles. MENU >
Aspect: Dale / Listă keeps the list of YTN1/YTN2.

Keys: RED Home, GREEN Search, YELLOW Live, BLUE History, arrows in the grid (in the list: LEFT/RIGHT rubrics), CH+/CH-
rubrics, OK play/open, MENU options (country, channel of the film, related films, quality, aspect, how YouTube opens
from Applications, the youtube.com/tv page), EXIT back (inside a channel/playlist: to the previous list). The network
work runs on one worker thread; results come back to the main loop through a timer.
Web pair: HdsWebControl/youtube_web.py (/youtube: search and play on the TV)."""
import threading
from collections import OrderedDict

from enigma import eServiceReference, eTimer, ePicLoad, eListboxPythonMultiContent, gFont, RT_HALIGN_CENTER, \
	RT_VALIGN_CENTER, RT_WRAP, RT_HALIGN_LEFT, RT_VALIGN_TOP

from Components.ActionMap import ActionMap
from Components.config import config, ConfigSubsection, ConfigSelection, ConfigText
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components import HdsYouTube as Y
from Components import HdsYouTubeDale as D
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.ScaledSkin import scaledSkin


def N_(t):
	return t


config.plugins.hdsyoutube = ConfigSubsection()
config.plugins.hdsyoutube.calitate = ConfigSelection(default="720", choices=[("480", "480p"), ("720", "720p"), ("1080", "1080p")])
# how the YouTube card of Applications opens: "auto" = this screen on weak receivers (MIPS, little memory), the
# youtube.com/tv page on the others; "nativ" = always this screen; "pagina" = always the page (the old behaviour)
config.plugins.hdsyoutube.deschide = ConfigSelection(default="auto", choices=[
	("auto", N_("Automat")), ("nativ", N_("Ecranul YouTube HD Satelit")), ("pagina", N_("Pagina youtube.com/tv"))])

# the receiver's country for the music charts ("auto": where the receiver is, else its language); the other topic
# pages follow the receiver's internet address (YouTube ignores the country there)
config.plugins.hdsyoutube.tara = ConfigText(default="auto", fixed_size=False)

# how the pages look: tiles like YouTube on a TV (YTN3) or the list with the picture at the
# side (YTN1/YTN2)
config.plugins.hdsyoutube.aspect = ConfigSelection(default="dale", choices=[("dale", N_("Dale")), ("lista", N_("Listă"))])

# the player's bar (YTN8): the clip's data in a line under the title (channel, size, codec, bit rate, length, views)
config.plugins.hdsyoutube.date_bara = ConfigSelection(default="da", choices=[("da", N_("Da")), ("nu", N_("Nu"))])

# the next clip at the end of one (YTN8b): played by itself (Da/Nu), announced over the last seconds of the clip
config.plugins.hdsyoutube.redare_auto = ConfigSelection(default="da", choices=[("da", N_("Da")), ("nu", N_("Nu"))])
config.plugins.hdsyoutube.urmeaza = ConfigSelection(default="7", choices=[("5", "5 s"), ("7", "7 s"), ("10", "10 s")])

# the row of rubrics, left to right (LEFT/RIGHT move along it; the colour keys keep their four)
FILE = ("acasa", "muzica", "jocuri", "stiri", "sport", "podcast", "live", "cauta", "istoric")
TITLURI = {"acasa": N_("Acasă"), "muzica": N_("Muzică"), "jocuri": N_("Jocuri"), "stiri": N_("Știri"),
	"sport": N_("Sport"), "podcast": N_("Podcasturi"), "live": N_("În direct"), "cauta": N_("Caută"),
	"istoric": N_("Văzute")}
CULORI_FILE = {"acasa": "#009F1313", "live": "#00A08500", "cauta": "#001F8B24", "istoric": "#00184C9E"}
RUBRICI = dict(Y.RUBRICI)
FILA_PAUZA_MS = 300            # LEFT/RIGHT: the list of a rubric loads after the key rests this long
INTEROGARE_LIVE = N_("știri")      # "Caută în direct" without a word typed: live streams for this word
T_INCARC = N_("Se încarcă...")
T_GOL = N_("Nu am găsit nimic aici.")
T_EROARE = N_("YouTube nu răspunde acum (%s). Verifică internetul și încearcă din nou cu OK.")
T_NU_PORNESTE = N_("Filmul nu poate porni: %s")
T_CAUTA_NOU = N_("Caută ceva nou...")
T_MAI_MULTE = N_("Mai multe...")
T_NU_SE_REDA = N_("Filmul nu a putut fi redat acum. Încearcă din nou sau alege alt film.")
T_DESCRIERE = N_("YouTube pe ecranul HD Satelit, fără cont: recomandate, căutare, în direct. Pagina youtube.com/tv e în MENU.")
T_TASTE_LISTA = N_(u"OK: Pornește   ◄ ►: Rubrici   MENU: Opțiuni   EXIT: Înapoi")
T_TASTE_DALE = N_(u"OK: Pornește   ▲▼◄►: Alege   CH+/CH-: Rubrici   MENU: Opțiuni   EXIT: Înapoi")
T_ASPECT = N_("Aspect: %s")
T_DATE_BARA = N_("Datele detaliate în bara de redare: %s")
T_TASTE_REDARE = N_(u"OK: Pauză   ◄ ►: 10 s   ◄◄ ►►: 1 min   CH+/CH-: Următorul/Anteriorul   ▲▼: Alte clipuri   INFO: Detalii")
T_TASTE_RAND = N_(u"◄ ►: Alege   OK: Pornește   ▲▼ EXIT: Închide")
T_URMEAZA = N_("Urmează: %s")
T_URMEAZA_TASTE = N_("OK: Acum   EXIT: Anulează")
T_NUMARATOARE = N_("Anunțul clipului următor: %s")
T_REDARE_AUTO = N_("Redare automată: %s")
T_URMEAZA_TITLU = N_("Urmează")
T_ALTE_CLIPURI = N_("Alte clipuri")
T_DETALII = N_("Detalii")
T_PENTRU_TEHNICIENI = N_("Datele tehnice")
T_DESCRIERE_CLIP = N_("Descrierea")

# the tiles (YTN3): colours of the Stitch design (project "HD Satelit - YouTube nativ pe receptor (dale, YTN3)")
C_FOND = 0x000A0F1A
C_LOC = 0x00141B30              # a picture not loaded yet
C_TEXT_LOC = 0x001B2440         # a tile without a picture (search)
C_CHENAR = 0x00FFFFFF
C_TITLU, C_TITLU_ALES = 0x00C9D2E3, 0x00FFFFFF
C_AUTOR, C_AUTOR_ALES = 0x009AA6BF, 0x00B8C4DD
C_RAFT = 0x00F2F4F8
C_DURATA, C_DURATA_FOND = 0x00FFFFFF, 0x00101010
C_LIVE_FOND = 0x00C4302B
C_FILA, C_FILA_ALEASA = "#00C9D2E3", "#00FFD27A"
POZE_MEMORIE = 30               # decoded tile pictures kept (~230 KB each at 320x180): two screens of tiles
PAUZA_POZE_MS = 120             # the pictures are asked for when the arrow rests this long


def _font(nume):
	try:
		from skin import fontHds
		return fontHds(nume)
	except Exception:
		return nume


def receptorSlab():
	"""MIPS or under 700 MB of memory: the youtube.com/tv page is slow there (Solo SE: 3 of 10 arrows in 2.5 s)"""
	import platform
	if platform.machine().lower().startswith("mips"):
		return True
	try:
		with open("/proc/meminfo") as f:
			for linie in f:
				if linie.startswith("MemTotal:"):
					return int(linie.split()[1]) < 700 * 1024
	except (IOError, OSError, ValueError):
		pass
	return False


def nativDinAplicatii():
	"""True when the YouTube card of Applications opens this screen"""
	v = config.plugins.hdsyoutube.deschide.value
	return v == "nativ" or (v == "auto" and receptorSlab())


def limba():
	try:
		from Components.Language import language
		return language.getLanguage()
	except Exception:
		return "en_US"


def taraAutomata():
	"""the receiver's country (2 letters): where it is (Components/HdsGhidInternet.taraAcum: the address found at the
	first start, the time zone, the menu language), else from the menu language"""
	try:
		from Components.HdsGhidInternet import taraAcum
		d = taraAcum()
		t = (d.get("tara") or (d.get("candidati") or [""])[0] or "").upper()
		if len(t) == 2 and t.isalpha():
			return t
	except Exception as e:
		print("[HdsYouTube] country: %s" % e)
	return Y._limba_tara(limba())[1]


def taraTopuri():
	v = (config.plugins.hdsyoutube.tara.value or "auto").upper()
	return taraAutomata() if v == "AUTO" else v


def tari():
	"""[(code, name in the menu language)] for the charts, in the alphabetical order of the shown name. The countries
	probed for YouTube Music charts (the cable/terrestrial table's, plus the US); the names (YTN3)
	from the image's common country table (Components/HdsLocul: 245 countries translated in every language of the menu,
	the one of the antenna's place and of DVB-I), sorted like there (Romanian alphabet in Romanian)"""
	try:
		from Components.HdsListeCabluTerestru import ALFA3, nume_tara
		# AD, CN and UZ have no YouTube charts (HTTP 400, probed for 0.8.0): not offered
		vechi = [(c, nume_tara(a)) for c, a in ALFA3.items() if c not in ("YU", "AD", "CN", "UZ")]
	except Exception:
		vechi = []
	if not any(c == "US" for c, n in vechi):
		vechi.append(("US", "USA"))
	try:
		from Components import HdsLocul as L
		l = [(c, L.numeTaraAfisat(c) or n) for c, n in vechi]
		return sorted(l, key=lambda x: L.cheieAfisare(x[1]))
	except Exception as e:
		print("[HdsYouTube] country names: %s" % e)
		return sorted(vechi, key=lambda x: x[1])


def numeTara(cod):
	return dict(tari()).get(cod, cod)


# the tab row: one label per rubric, the four with a colour key keep their colour bar (YTN3: in the top bar, after the
# YouTube badge, as in the Stitch design; _aseazaFile fits them to the language)
FILE_X, FILE_CAPAT, FILE_Y, FILE_H = 256, 1480, 54, 44      # inside the title-safe area (54 px from the top)


def _skinFile():
	latime = (FILE_CAPAT - FILE_X) // len(FILE)
	r = []
	for i, f in enumerate(FILE):
		x = FILE_X + i * latime
		if f in CULORI_FILE:
			r.append('<widget name="b%d" position="%d,%d" size="6,%d" backgroundColor="%s" zPosition="2" />' % (i, x,
				FILE_Y, FILE_H, CULORI_FILE[f]))
		r.append('<widget name="f%d" position="%d,%d" size="%d,%d" font="{fRegular};26" foregroundColor="#00C9D2E3" '
			'backgroundColor="#000A0F1A" valign="center" noWrap="1" zPosition="2" />' % (i, x + 12, FILE_Y, latime - 16, FILE_H))
	return "\n\t".join(r)


# the grid (YTN3) and the list (YTN1/YTN2) share the space under the bar; only one of them is shown. The lines under
# them: the chosen tile's whole title and its views (moves when it does not fit), or the state; then the keys.
SKIN = """<screen name="HdsYouTube" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000A0F1A">
	<eLabel text="YouTube" position="96,54" size="140,44" font="{fBold};28" foregroundColor="#00FFFFFF" backgroundColor="#00C4302B" halign="center" valign="center" zPosition="2" />
	<widget name="titlu" position="1496,54" size="328,44" font="{fRegular};24" foregroundColor="#009FB4FF" backgroundColor="#000A0F1A" halign="right" valign="center" noWrap="1" zPosition="2" />
	""" + _skinFile() + """
	<eLabel position="96,102" size="1728,1" backgroundColor="#002A3350" zPosition="1" />
	<widget name="grila" position="%d,%d" size="%d,%d" backgroundColor="#000A0F1A" backgroundColorSelected="#000A0F1A" scrollbarMode="showNever" transparent="0" zPosition="2" />
	<widget name="lista" position="96,110" size="1080,812" font="{fRegular};30" itemHeight="58" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="#00374EA1" scrollbarMode="showOnDemand" transparent="0" zPosition="2" />
	<widget name="panou" position="1200,110" size="624,812" backgroundColor="#0010162A" zPosition="1" />
	<widget name="poza" position="1212,122" size="600,338" alphatest="off" zPosition="3" />
	<widget name="nume" position="1212,476" size="600,128" font="{fBold};30" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" zPosition="3" />
	<widget name="autor" position="1212,610" size="600,40" font="{fRegular};28" foregroundColor="#009FB4FF" backgroundColor="#0010162A" noWrap="1" zPosition="3" />
	<widget name="info" position="1212,654" size="600,140" font="{fRegular};26" foregroundColor="#00C9D2E3" backgroundColor="#0010162A" zPosition="3" />
	<widget name="masura" position="0,0" size="1000,40" font="{fRegular};22" noWrap="1" zPosition="-1" />
	<widget source="detalii" render="RunningText" options="movetype=swimming,startdelay=2500,steptime=40,step=3,repeat=2" position="128,958" size="1664,32" font="{fRegular};26" foregroundColor="#00F2F4F8" backgroundColor="#000A0F1A" valign="center" noWrap="1" zPosition="2" />
	<widget name="stare" position="128,958" size="1664,32" font="{fRegular};26" foregroundColor="#00FFD27A" backgroundColor="#000A0F1A" valign="center" noWrap="1" zPosition="3" />
	<widget name="taste" position="128,994" size="1664,30" font="{fRegular};22" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" valign="center" noWrap="1" zPosition="2" />
</screen>""" % (D.GRILA_X, D.GRILA_Y, D.LATIME_GRILA, D.RAND_H * D.RANDURI_VIZIBILE)


class Lucrator(object):
	"""one background thread for the network: the newest request wins; finished results are taken by the main loop"""

	def __init__(self, laGata):
		self.laGata = laGata
		self.lacat = threading.Lock()
		self.rezultate = []
		self.generatie = 0
		self.inLucru = 0          # threads not yet taken back; the timer runs only while there are some
		self.ceas = eTimer()
		try:
			self.ceas.callback.append(self._preia)
		except AttributeError:
			self._legatura = self.ceas.timeout.connect(self._preia)

	def porneste(self, eticheta, functie, *arg):
		self.generatie += 1
		gen = self.generatie

		def lucru():
			try:
				r = (True, functie(*arg))
			except Exception as e:
				r = (False, e)
			with self.lacat:
				self.rezultate.append((gen, eticheta, r))

		fir = threading.Thread(target=lucru, name="HdsYouTube")
		fir.daemon = True
		self.inLucru += 1
		fir.start()
		self.ceas.start(60, False)
		return gen

	def _preia(self):
		with self.lacat:
			gata, self.rezultate = self.rezultate, []
		self.inLucru -= len(gata)
		if self.inLucru <= 0:
			self.inLucru = 0
			self.ceas.stop()
		for gen, eticheta, r in gata:
			self.laGata(gen, eticheta, r)

	def opreste(self):
		self.ceas.stop()


class HdsYouTube(Screen):
	ALLOW_SUSPEND = True

	def __init__(self, session, fila="acasa"):
		Screen.__init__(self, session)
		self.skin = scaledSkin(SKIN.format(fRegular=_font("Regular"), fBold=_font("Bold")), 1920)
		self.yt = Y.YouTube(limba())
		self.tara = taraTopuri()
		if self.tara:
			self.yt.gl = self.tara       # Home and search for the receiver's country, not for its menu language
		for k in ("titlu", "nume", "autor", "info", "stare", "taste", "panou", "masura"):
			self[k] = Label("")
		self["detalii"] = StaticText("")
		for i, f in enumerate(FILE):
			self["f%d" % i] = Label(_(TITLURI[f]))
			if f in CULORI_FILE:
				self["b%d" % i] = Label("")
		self["lista"] = MenuList([])
		self["grila"] = MenuList([], content=eListboxPythonMultiContent)
		self["poza"] = Pixmap()
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions", "DirectionActions"], {
			"ok": self.ok, "cancel": self.inapoi, "menu": self.meniu,
			"red": lambda: self.fila("acasa"), "green": lambda: self.fila("cauta"),
			"yellow": lambda: self.fila("live"), "blue": lambda: self.fila("istoric"),
			"left": lambda: self.sageata("stanga"), "right": lambda: self.sageata("dreapta"),
			"up": lambda: self.sageata("sus"), "down": lambda: self.sageata("jos"),
		}, -1)
		# CH+/CH-: the rubrics from anywhere (in the grid the arrows move between tiles)
		self["rubrici"] = ActionMap(["ChannelSelectBaseActions"], {
			"nextBouquet": lambda: self.filaAlaturi(1), "prevBouquet": lambda: self.filaAlaturi(-1),
		}, -1)
		self.dale = config.plugins.hdsyoutube.aspect.value != "lista"
		self.focus = "grila"           # "grila" or "file" (the row of rubrics, reached with UP from the first row)
		self.grila = D.Grila()
		self.pixmapuri = OrderedDict()  # picture address -> (pixmap, width, height), the newest last
		self.deDecodat = []            # [(address, file)] waiting for the tile decoder
		self.decodez = None
		self.genPoze = 0
		self.dorite = set()
		self.ascultatorPoze = None     # the player's row of clips, told when one of its pictures is decoded (YTN8)
		self.scara = 1.0
		self.latimi = [len] * 5
		self.inainte = None
		self.filaAsteptata = None
		self.ceasFila = eTimer()
		try:
			self.ceasFila.callback.append(self._filaAsteptata)
		except AttributeError:
			self._legaturaFila = self.ceasFila.timeout.connect(self._filaAsteptata)
		self.elemente, self.cont, self.capat = [], None, "browse"
		self.stiva = []            # previous lists (channel/playlist opened from a list): (title, items, cont, capat, index)
		self.filaCurenta = fila
		self.titluLista = ""
		self.incarca = False
		self.pornesc = False
		self.lucrator = Lucrator(self._gata)
		self.genLista = self.genPoza = 0
		self.pozaCeruta = None
		self.incarcator = ePicLoad()
		try:
			self.incarcator.PictureData.get().append(self._pozaDecodata)
		except AttributeError:
			self._legaturaPoza = self.incarcator.PictureData.connect(self._pozaDecodata)
		self.ceasPoza = eTimer()
		try:
			self.ceasPoza.callback.append(self._cerePoza)
		except AttributeError:
			self._legaturaCeas = self.ceasPoza.timeout.connect(self._cerePoza)
		# the tile pictures: downloaded on two threads, decoded here one at a time at the tile's size
		self.descarcator = Y.Descarcator(self.yt)
		self.decodor = ePicLoad()
		try:
			self.decodor.PictureData.get().append(self._dalaDecodata)
		except AttributeError:
			self._legaturaDecodor = self.decodor.PictureData.connect(self._dalaDecodata)
		self.ceasPoze = self._ceas(self._preiaPoze)          # takes the downloads while there are some
		self.ceasCerePoze = self._ceas(self._cerePoze)       # asks for the pictures when the arrow rests
		self.ceasDecodor = self._ceas(self._decodorBlocat)   # a picture that never comes back from the decoder
		self["lista"].onSelectionChanged.append(self._selectie)
		self.onLayoutFinish.append(self._pornire)
		self.onClose.append(self._inchide)

	def _ceas(self, functie):
		c = eTimer()
		try:
			c.callback.append(functie)
		except AttributeError:
			self.__dict__.setdefault("_legaturi", []).append(c.timeout.connect(functie))
		return c

	# ------------------------------------------------------------------ lists
	def _pornire(self):
		try:
			m = self["poza"].instance.size()
			self.incarcator.setPara((m.width(), m.height(), 1, 1, False, 1, "#00000000"))
		except Exception as e:
			print("[HdsYouTube] picture: %s" % e)
		self._pregatesteGrila()
		self._aspect()
		# a full screen of ours, like the image's players: the channel stops while YouTube is open (no picture and no
		# sound of it behind the keyboard or the menus) and comes back on exit; a backdrop in YouTube's colour stays
		# under the windows opened from here (enigma2 hides this screen while another one is on top)
		try:
			self.inainte = self.session.nav.getCurrentlyPlayingServiceReference()
			self.session.nav.stopService()
		except Exception as e:
			print("[HdsYouTube] channel: %s" % e)
		arataFond(self.session)
		self._aseazaFile()
		self.fila(self.filaCurenta, forteaza=True)

	def _aseazaFile(self):
		"""the tab row fitted to the language: each tab as wide as its name (with the marker), one after the other;
		when they do not fit in the row, a smaller letter (26, 23, 20 px). Equal widths cut long names (ru, fr, pl)"""
		try:
			from enigma import ePoint, eSize, gFont
			e0 = self["f0"].instance
			x0, y, h = e0.position().x(), e0.position().y(), e0.size().height()
			ultim = self["f%d" % (len(FILE) - 1)].instance
			capat = ultim.position().x() + ultim.size().width()
			spatiu = max(8, (capat - x0) // 60)
			bara = max(3, h // 7)
			for marime in (26, 23, 20):
				m = marime * h // FILE_H       # the skin's 26 px on its row, scaled like the skin
				latimi = []
				for i, f in enumerate(FILE):
					inst = self["f%d" % i].instance
					inst.setFont(gFont(_font("Regular"), m))
					inst.setText(u"\u00a0▶ " + _(TITLURI[f]))
					latimi.append(inst.calculateSize().width() + 4)
				if sum(latimi) + (bara + 4 + spatiu) * len(FILE) <= capat - x0 + spatiu:
					break
			rest = max(0, (capat - x0) - sum(latimi) - (bara + 4 + spatiu) * len(FILE))
			adaos = rest // len(FILE)       # what is left is shared, so the row still spans the screen
			x = x0 - (bara + 4)
			for i, f in enumerate(FILE):
				if "b%d" % i in self:
					self["b%d" % i].instance.move(ePoint(x, y))
				self["f%d" % i].instance.move(ePoint(x + bara + 4, y))
				self["f%d" % i].instance.resize(eSize(latimi[i] + adaos, h))
				x += bara + 4 + latimi[i] + adaos + spatiu
		except Exception as e:
			print("[HdsYouTube] tabs: %s" % e)

	def filaAlaturi(self, pas):
		"""LEFT/RIGHT: the marker moves at once; the list loads when the key rests (FILA_PAUZA_MS), so holding the key
		over several rubrics does not start a request (and a JSON parse) for each one"""
		f0 = self.filaAsteptata or self.filaCurenta
		i = FILE.index(f0) if f0 in FILE else 0
		f = FILE[(i + pas) % len(FILE)]
		self.filaAsteptata = f
		self._marcheaza(f)
		self["titlu"].setText(_(TITLURI[f]))
		self.ceasFila.start(FILA_PAUZA_MS, True)

	def _filaAsteptata(self):
		f, self.filaAsteptata = self.filaAsteptata, None
		if f:
			# the search tab shows the history; the keyboard opens only with OK (moving along the row must not open it)
			self.fila(f, forteaza=True, faraTastatura=True)

	def _marcheaza(self, f):
		for i, x in enumerate(FILE):
			self["f%d" % i].setText(u"\u00a0" + (u"▶ " if x == f else "") + _(TITLURI[x]))   # no-break space: the J hook is not cut (the thin space is dropped)
		self._culoareFile(f)

	def _culoareFile(self, f=None):
		"""the chosen rubric in amber while the row of rubrics has the arrows (UP from the first row of tiles)"""
		f = f or self.filaAsteptata or self.filaCurenta
		try:
			from skin import parseColor
			for i, x in enumerate(FILE):
				inst = self["f%d" % i].instance
				if inst is not None:
					inst.setForegroundColor(parseColor(C_FILA_ALEASA if (x == f and self.focus == "file") else C_FILA))
					inst.invalidate()
		except Exception as e:
			print("[HdsYouTube] tab colour: %s" % e)

	# ------------------------------------------------------------------ the grid of tiles (YTN3)
	def _s(self, v):
		return int(round(v * self.scara))

	def _pregatesteGrila(self):
		"""the grid's fonts, row height and the letter widths, at the desktop's scale"""
		try:
			from enigma import getDesktop
			self.scara = getDesktop(0).size().width() / 1920.0
		except Exception:
			self.scara = 1.0
		s = self._s
		regular, bold = _font("Regular"), _font("Bold")
		self.fonturiGrila = [gFont(regular, s(D.FONT_TITLU)), gFont(regular, s(D.FONT_AUTOR)), gFont(bold, s(D.FONT_RAFT)),
			gFont(bold, s(D.FONT_ETICHETA)), gFont(regular, s(D.FONT_MARE))]
		l = self["grila"].l
		for i, f in enumerate(self.fonturiGrila):
			l.setFont(i, f)
		l.setItemHeight(s(D.RAND_H))
		inst = self["grila"].instance
		if inst is not None:
			if hasattr(inst, "setRedrawOnSelection"):
				inst.setRedrawOnSelection(False)       # the chosen tile comes from the row's tuple, not from the list
			inst.setSelectionEnable(0)
		self.latimi = [D.Latimi(self._masoara(f)) for f in self.fonturiGrila]

	def _masoara(self, font):
		def masoara(text):
			inst = self["masura"].instance
			inst.setFont(font)
			inst.setText(text)
			return inst.calculateSize().width()
		return masoara

	def _aspect(self):
		"""the tiles or the list (MENU > Aspect), with what belongs to each"""
		self.dale = config.plugins.hdsyoutube.aspect.value != "lista"
		self["masura"].hide()
		for k in ("lista", "panou", "poza", "nume", "autor", "info"):
			(self[k].hide if self.dale else self[k].show)()
		(self["grila"].show if self.dale else self["grila"].hide)()
		if not self.dale:
			self["poza"].hide()
			self.focus = "grila"
			self["detalii"].text = ""
		self["taste"].setText(_(T_TASTE_DALE if self.dale else T_TASTE_LISTA))

	def _stare(self, text):
		"""the state line (loading, errors) over the chosen tile's details"""
		self["stare"].setText(text or "")
		if text:
			self["stare"].show()
			self["detalii"].text = ""
		else:
			self["stare"].hide()
			if self.dale:
				e = self.grila.ales()
				self["detalii"].text = D.detalii(e) if e else ""

	def sageata(self, directie):
		if not self.dale:
			# the list (YTN2): UP/DOWN in the list, LEFT/RIGHT the rubrics
			if directie == "sus":
				self["lista"].up()
			elif directie == "jos":
				self["lista"].down()
			else:
				self.filaAlaturi(-1 if directie == "stanga" else 1)
			return
		if self.focus == "file":
			if directie in ("stanga", "dreapta"):
				self.filaAlaturi(-1 if directie == "stanga" else 1)
			elif directie == "jos":
				self._focusGrila()
			return
		rez = self.grila.muta(directie)
		if rez["iesire"] == "sus":
			self.focus = "file"
			self._culoareFile()
			if self.grila.randuri:
				self._refaDala(self.grila.r, self.grila.coloana())
			return
		if rez["iesire"]:
			return
		self._dupaMutare(rez)

	def _focusGrila(self):
		self.focus = "grila"
		self._culoareFile()
		if self.grila.randuri:
			self._refaDala(self.grila.r, self.grila.coloana())

	def _dupaMutare(self, rez):
		if rez["fereastra"]:
			self._refaGrila()
		else:
			lista = self["grila"].list
			sus = self.grila.sus
			for r in rez["randuri"]:
				k = r - sus
				if 0 <= k < len(lista):
					lista[k] = self._randGrila(r)
			if rez["dale"]:
				for r, k in rez["dale"]:
					self._deseneazaDala(r, k)
			else:
				for r in rez["randuri"]:
					if 0 <= r - sus < len(lista):
						self["grila"].l.invalidateEntry(r - sus)
		self._selectieGrila()

	def _refaDala(self, r, k):
		lista = self["grila"].list
		i = r - self.grila.sus
		if 0 <= i < len(lista):
			lista[i] = self._randGrila(r)
			self._deseneazaDala(r, k)

	def _deseneazaDala(self, r, k):
		"""only tile k of row r is drawn again (eListbox.entryPartChanged); the whole row on an older engine"""
		i = r - self.grila.sus
		inst = self["grila"].instance
		if inst is None or not 0 <= i < len(self["grila"].list):
			return
		if hasattr(inst, "entryPartChanged"):
			x, w = D.zona_dala(k)
			inst.entryPartChanged(i, self._s(x), self._s(w))
		else:
			self["grila"].l.invalidateEntry(i)

	def _refaGrila(self):
		"""all the visible rows built again (a new list, the window moved)"""
		self["grila"].setList([self._randGrila(r) for r in self.grila.vizibile_randuri()])

	def _titlu(self, e):
		"""the tile's title broken on two lines (measured once per item)"""
		t = e.get("_dala")
		if t is None:
			t = D.rupe_titlu(e.get("titlu") or "", self.latimi[0], self._s(D.POZA_L) - D.REZERVA)
			e["_dala"] = t
		return t

	def _randGrila(self, r):
		"""the tuple of row r: the shelf's title, then for each visible tile the frame (chosen), the picture or its
		place, the length or "live" on it, the title and the channel"""
		s = self._s
		T = eListboxPythonMultiContent.TYPE_TEXT
		rand = self.grila.randuri[r]
		intrari = [r]
		ales = self.focus == "grila"
		lat = s(D.LATIME_GRILA - 2 * D.CHENAR)
		if rand["raft"]:
			intrari.append((T, s(D.CHENAR), s(D.RAFT_Y), lat, s(D.RAFT_H), 2, RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				D.fara_taiere(D.taie_rand(rand["raft"], self.latimi[2], lat - D.REZERVA)), C_RAFT, C_RAFT, None, None))
		pl, ph = s(D.POZA_L), s(D.POZA_H)
		py = s(D.POZA_Y)
		for k in range(self.grila.coloane):
			i = rand["inceput"] + k
			if i >= len(rand["dale"]):
				break
			e = rand["dale"][i]
			aleasa = ales and r == self.grila.r and i == self.grila.c
			x = s(D.x_dala(k))
			if aleasa:
				c = s(D.CHENAR)
				intrari.append((T, x - c, py - c, pl + 2 * c, ph + 2 * c, 0, 0, "", None, None, C_CHENAR, C_CHENAR))
			fel = e.get("fel")
			if fel in ("cauta-nou", "cautare"):
				# the search tab: "search something new" and the history as tiles with words, no picture
				text = (u"+  " if fel == "cauta-nou" else u"» ") + (e.get("titlu") or "")
				intrari.append((T, x, py, pl, ph, 4, RT_HALIGN_CENTER | RT_VALIGN_CENTER | RT_WRAP, text, C_TITLU_ALES,
					C_TITLU_ALES, C_TEXT_LOC, C_TEXT_LOC))
				continue
			u = D.poza_dala(e)
			p = self.pixmapuri.get(u)
			if p is not None:
				self.pixmapuri.move_to_end(u)       # seen now: the last one to be forgotten
			if p is None or p[1] < pl or p[2] < ph:
				intrari.append((T, x, py, pl, ph, 0, 0, "", None, None, C_LOC, C_LOC))
			if p is not None:
				pw, pph = min(p[1], pl), min(p[2], ph)
				# a square channel picture sits in the middle of the tile
				intrari.append((eListboxPythonMultiContent.TYPE_PIXMAP, x + (pl - pw) // 2, py + (ph - pph) // 2, pw, pph,
					p[0], None, None, 0))
			eticheta, fond = None, C_DURATA_FOND
			if e.get("live"):
				eticheta, fond = _(u"În direct").upper(), C_LIVE_FOND
			elif fel in ("film", "lista") and e.get("durata"):
				eticheta = e["durata"]
			if eticheta:
				el = min(pl - s(16), D.eticheta_latime(eticheta, self.latimi[3]))
				eh = s(D.ETICHETA_H)
				intrari.append((T, x + pl - el - s(8), py + ph - eh - s(8), el, eh, 3, RT_HALIGN_CENTER | RT_VALIGN_CENTER,
					eticheta, C_DURATA, C_DURATA, fond, fond))
			titlu, _taiat = self._titlu(e)
			ct = C_TITLU_ALES if aleasa else C_TITLU
			intrari.append((T, x, s(D.TITLU_Y), pl, s(D.TITLU_H), 0, RT_HALIGN_LEFT | RT_VALIGN_TOP | RT_WRAP, D.fara_taiere(titlu), ct, ct,
				None, None))
			autor = e.get("autor") or ""
			if fel == "canal":
				autor = u"  ·  ".join(t for t in (_("Canal"), e.get("vizionari") or "") if t)
			elif fel == "lista":
				autor = u"  ·  ".join(t for t in (_("Listă"), autor) if t)
			if autor:
				ca = C_AUTOR_ALES if aleasa else C_AUTOR
				# right under the title, as on YouTube: one line higher when the title has one line
				ay = D.AUTOR_Y if u"\n" in titlu else D.AUTOR_Y - D.TITLU_H // 2
				intrari.append((T, x, s(ay), pl, s(D.AUTOR_H), 1, RT_HALIGN_LEFT | RT_VALIGN_CENTER,
					D.fara_taiere(D.taie_rand(autor, self.latimi[1], pl - D.REZERVA)), ca, ca, None, None))
		return intrari

	def _selectieGrila(self):
		"""the chosen tile's details under the grid; the next page when the end comes near; the pictures"""
		e = self.grila.ales()
		if not self["stare"].getText():
			self["detalii"].text = D.detalii(e) if e else ""
		if self.cont and not self.incarca and self.grila.aproape_de_capat():
			self._maiMulte()
		self.ceasCerePoze.start(PAUZA_POZE_MS, True)

	# ------------------------------------------------------------------ the tile pictures
	def _cerePoze(self):
		if not self.dale:
			return
		dorite = [(D.poza_dala(e), e) for e in D.de_descarcat(self.grila)]
		self.dorite = set(u for u, e in dorite)
		# a picture waiting for the decoder that is no longer wanted is dropped
		self.deDecodat = [x for x in self.deDecodat if x[0] in self.dorite]
		asteapta = set(x[0] for x in self.deDecodat)
		lipsa = [(u, e) for u, e in dorite if u not in self.pixmapuri and u not in asteapta and u != self.decodez]
		self.descarcator.cere(lipsa)
		if lipsa or self.deDecodat:
			self.ceasPoze.start(50, False)

	def _preiaPoze(self):
		for u, cale in self.descarcator.gata():
			if cale and u in self.dorite and u not in self.pixmapuri:
				self.deDecodat.append((u, cale))
		self._decodeazaUrmatoarea()
		if not self.descarcator.ocupat() and not self.deDecodat and self.decodez is None:
			self.ceasPoze.stop()

	def _decodeazaUrmatoarea(self):
		if self.decodez is not None or not self.deDecodat:
			return
		u, cale = self.deDecodat.pop(0)
		self.decodez = u
		try:
			self.decodor.setPara((self._s(D.POZA_L), self._s(D.POZA_H), 1, 1, False, 1, "#00000000"))
			if self.decodor.startDecode(cale):
				raise ValueError("startDecode")
			self.ceasDecodor.start(3000, True)
		except Exception as e:
			print("[HdsYouTube] tile picture %s: %s" % (cale, e))
			self.decodez = None

	def _decodorBlocat(self):
		print("[HdsYouTube] tile picture not decoded in 3 s: %s" % self.decodez)
		self.decodez = None
		self._decodeazaUrmatoarea()

	def _dalaDecodata(self, info=""):
		self.ceasDecodor.stop()
		u, self.decodez = self.decodez, None
		try:
			ptr = self.decodor.getData()
		except Exception:
			ptr = None
		if u and ptr is not None:
			try:
				w, h = ptr.size().width(), ptr.size().height()
			except Exception:
				w, h = self._s(D.POZA_L), self._s(D.POZA_H)
			self.pixmapuri[u] = (ptr, w, h)
			while len(self.pixmapuri) > POZE_MEMORIE:
				self.pixmapuri.popitem(last=False)
			self._arataPoza(u)
			if self.ascultatorPoze is not None:
				try:
					self.ascultatorPoze(u)
				except Exception as e:
					print("[HdsYouTube] row picture: %s" % e)
		self._decodeazaUrmatoarea()

	def _arataPoza(self, u):
		"""a decoded picture goes into the visible tiles that show it; only those tiles are drawn again"""
		if not self.dale:
			return
		g = self.grila
		lista = self["grila"].list
		for r in g.vizibile_randuri():
			rand = g.randuri[r]
			vazute = rand["dale"][rand["inceput"]:rand["inceput"] + g.coloane]
			ks = [k for k, e in enumerate(vazute) if D.poza_dala(e) == u]
			if ks and 0 <= r - g.sus < len(lista):
				lista[r - g.sus] = self._randGrila(r)
				for k in ks:
					self._deseneazaDala(r, k)

	def cerePoze(self, elemente, ascultator):
		"""the pictures of other tiles (the player's row of clips, YTN8), with the same downloader and decoder"""
		self.ascultatorPoze = ascultator
		dorite = [(D.poza_dala(e), e) for e in elemente if D.poza_dala(e)]
		self.dorite = set(u for u, e in dorite)
		self.deDecodat = [x for x in self.deDecodat if x[0] in self.dorite]
		asteapta = set(x[0] for x in self.deDecodat)
		lipsa = [(u, e) for u, e in dorite if u not in self.pixmapuri and u not in asteapta and u != self.decodez]
		self.descarcator.cere(lipsa)
		if lipsa or self.deDecodat:
			self.ceasPoze.start(50, False)

	def _uitaPoze(self):
		"""a new list: what was waiting for the old one is dropped (the decoded pictures stay, up to POZE_MEMORIE)"""
		self.descarcator.cere([])
		self.deDecodat = []
		self.dorite = set()

	def fila(self, f, forteaza=False, faraTastatura=False):
		if f == self.filaCurenta and not forteaza and not self.stiva:
			if f == "cauta" and not faraTastatura:
				self.tastatura()
			return
		self.filaCurenta, self.stiva = f, []
		self.filaAsteptata = None
		self.ceasFila.stop()
		self._marcheaza(f)
		if f == "acasa":
			self._cere(_(TITLURI[f]), "browse", self.yt.acasa)
		elif f == "muzica":
			self._cere(u"%s: %s" % (_(TITLURI[f]), numeTara(self.tara)), "tv:" + self.tara, self.yt.muzica, self.tara)
		elif f in RUBRICI:
			self._cere(_(TITLURI[f]), "tv:", self.yt.rubrica, RUBRICI[f])
		elif f == "cauta":
			self._arataCautari()
		else:
			self._arata(_(TITLURI[f]), self.yt.stare.vazute(), None, "browse")

	def _arataCautari(self):
		randuri = [{"fel": "cauta-nou", "id": "", "titlu": _(T_CAUTA_NOU)}]
		randuri += [{"fel": "cautare", "id": t, "titlu": t} for t in self.yt.stare.cautari()]
		self._arata(_(TITLURI["cauta"]), randuri, None, "search")

	def _cere(self, titlu, capat, functie, *arg):
		self.titluLista, self.capat = titlu, capat
		self["titlu"].setText(titlu)
		self._stare(_(T_INCARC))
		self.incarca = True
		self.genLista = self.lucrator.porneste("lista", functie, *arg)

	def _gata(self, gen, eticheta, r):
		ok, val = r
		if eticheta == "poza":
			if gen == self.genPoza and ok and val:
				try:
					self.incarcator.startDecode(val)
				except Exception as e:
					print("[HdsYouTube] decode: %s" % e)
			return
		if eticheta == "redare":
			self.pornesc = False
			self._stare("")
			if ok:
				self._reda(val[0], val[1])
			else:
				self.session.open(MessageBox, _(T_NU_PORNESTE) % val, MessageBox.TYPE_ERROR, timeout=10)
			return
		if gen != self.genLista:
			return
		self.incarca = False
		if not ok:
			self._stare(_(T_EROARE) % val)
			return
		e, cont = val
		if eticheta == "mai":
			self.elemente = [x for x in self.elemente if x["fel"] != "mai"] + e
			self.cont = cont
			if self.dale:
				self._stare("")
				self.grila.adauga(e)
				self._refaGrila()
				self._selectieGrila()
				return
			self._umple(pastreaza=True)
			self._stare("")
			return
		self._arata(self.titluLista, e, cont, self.capat)

	def _arata(self, titlu, elemente, cont, capat, index=0):
		self.titluLista, self.elemente, self.cont, self.capat = titlu, list(elemente), cont, capat
		self["titlu"].setText(titlu)
		self._stare("" if self.elemente else _(T_GOL))
		if self.dale:
			self._uitaPoze()
			self.grila = D.Grila(self.elemente)
			self.grila.puneIndex(index)
			self._refaGrila()
			self._selectieGrila()
			return
		self._umple(index=index)

	def _umple(self, pastreaza=False, index=0):
		rows = list(self.elemente)
		if self.cont:
			rows.append({"fel": "mai", "id": "", "titlu": _(T_MAI_MULTE)})
		self.elemente = rows
		poz = self["lista"].getSelectionIndex() if pastreaza else index
		self["lista"].setList([(self._rand(e), e) for e in rows])
		if rows:
			poz = min(poz, len(rows) - 1)
			if rows[poz]["fel"] == "raft" and poz + 1 < len(rows):
				poz += 1           # a shelf title is not something to open: start on its first film
			self["lista"].moveToIndex(poz)
		self._selectie()

	def _rand(self, e):
		if e["fel"] == "raft":
			return u"━━  %s" % e["titlu"]
		if e["fel"] == "film" and e.get("live"):
			return u"● %s" % e["titlu"]
		if e["fel"] == "canal":
			return u"%s: %s" % (_("Canal"), e["titlu"])
		if e["fel"] == "lista":
			return u"%s: %s" % (_("Listă"), e["titlu"])
		if e["fel"] == "cautare":
			return u"» %s" % e["titlu"]
		return e["titlu"]

	def _curent(self):
		if self.dale:
			return self.grila.ales()
		c = self["lista"].getCurrent()
		return c[1] if c else None

	def _index(self):
		"""the place of the chosen item, kept when a channel or a playlist is opened from it (EXIT comes back to it)"""
		if self.dale:
			return self.grila.pozitie()[0]
		return self["lista"].getSelectionIndex()

	def _selectie(self):
		if self.dale:
			return
		e = self._curent()
		self["poza"].hide()
		if not e or e["fel"] == "raft":
			self.pozaCeruta = None
			for k in ("nume", "autor", "info"):
				self[k].setText("")
			return
		self["nume"].setText(D.fara_taiere(e.get("titlu", "")))
		self["autor"].setText(D.fara_taiere(e.get("autor", "")))
		info = []
		if e.get("live"):
			info.append(_("În direct"))
		for k in ("durata", "vizionari", "data"):
			if e.get(k):
				info.append(e[k])
		if e["fel"] == "lista" and e.get("durata"):
			info = [_("%s filme") % e["durata"]]
		self["info"].setText(u"\n".join(info))
		self.pozaCeruta = e if e.get("poza") else None
		self.ceasPoza.start(250, True)
		if e["fel"] == "mai" and self.cont and not self.incarca:
			self._maiMulte()

	def _maiMulte(self):
		self.incarca = True
		self._stare(_(T_INCARC))
		self.genLista = self.lucrator.porneste("mai", self.yt.continua, self.capat, self.cont)

	# ------------------------------------------------------------------ thumbnail of the selected row
	def _cerePoza(self):
		e = self.pozaCeruta
		if e:
			self.genPoza = self.lucrator.porneste("poza", self.yt.poza, e)

	def _pozaDecodata(self, info=""):
		try:
			ptr = self.incarcator.getData()
			if ptr is not None:
				self["poza"].instance.setPixmap(ptr.__deref__() if hasattr(ptr, "__deref__") else ptr)
				self["poza"].show()
		except Exception as e:
			print("[HdsYouTube] picture: %s" % e)

	# ------------------------------------------------------------------ keys
	def ok(self):
		if self.dale and self.focus == "file":
			self.ceasFila.stop()
			if self.filaAsteptata:
				self._filaAsteptata()
			self._focusGrila()
			return
		e = self._curent()
		if e is None:
			if self.filaCurenta != "cauta":
				self.fila(self.filaCurenta, forteaza=True)    # after an error: OK tries again
			return
		f = e["fel"]
		if f == "cauta-nou":
			self.tastatura()
		elif f == "cautare":
			self._cauta(e["id"])
		elif f == "mai":
			if self.cont and not self.incarca:
				self._maiMulte()
		elif f == "canal":
			self._deschide(e["titlu"], "browse", self.yt.canal, e["id"])
		elif f == "lista":
			self._deschide(e["titlu"], "browse", self.yt.lista, e["id"])
		elif f == "film":
			self.porneste(e)

	def _deschide(self, titlu, capat, functie, *arg):
		self.stiva.append((self.titluLista, [x for x in self.elemente if x["fel"] != "mai"], self.cont, self.capat,
			self._index()))
		self._cere(titlu, capat, functie, *arg)

	def inapoi(self):
		if self.stiva:
			self.genLista += 1        # a list still loading is dropped
			titlu, e, cont, capat, index = self.stiva.pop()
			self._arata(titlu, e, cont, capat, index)
			return
		self.close()

	def tastatura(self):
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(self._dupaTastatura, VirtualKeyBoard, title=_("Caută pe YouTube"), text="")

	def _dupaTastatura(self, text=None):
		if text and text.strip():
			self._cauta(text.strip())

	def _cauta(self, text):
		self.yt.stare.adauga_cautare(text)
		self.stiva.append((self.titluLista, [x for x in self.elemente if x["fel"] != "mai"], self.cont, self.capat,
			self._index()))
		fel = "live" if self.filaCurenta == "live" else "film"
		self._cere(u"%s: %s" % (_("Caută"), text), "search", self.yt.cauta, text, fel)

	def porneste(self, e):
		if self.pornesc:
			return          # a second OK while the first film is being prepared
		self.pornesc = True
		self._stare(_("Pornesc filmul..."))
		inaltime = int(config.plugins.hdsyoutube.calitate.value)

		def lucru():
			return e, self.yt.redare(e["id"], inaltime)

		self.lucrator.porneste("redare", lucru)

	def _reda(self, e, r):
		self.yt.stare.adauga_vazut(e)
		# the films of the list it was started from: CH+/CH- and the row of clips in the player go along it, then
		# YouTube's related films (YTN8)
		filme = [x for x in self.elemente if x.get("fel") == "film"]
		i = next((k for k, x in enumerate(filme) if x.get("id") == e.get("id")), 0)
		reda(self.session, r, sir=Sir(self.yt, filme, i, self))

	def meniu(self):
		from Screens.ChoiceBox import ChoiceBox
		e = self._curent()
		alegeri = []
		if e and e.get("autor_id") and e["fel"] != "canal":
			alegeri.append((_("Canalul: %s") % (e.get("autor") or "?"), "canal"))
		if e and e["fel"] == "film":
			alegeri.append((_("Filme asemănătoare"), "inrudite"))
		if self.filaCurenta == "live":
			alegeri.append((_("Caută în direct"), "cauta-live"))
		auto = (config.plugins.hdsyoutube.tara.value or "auto").lower() == "auto"
		alegeri.append((u"%s: %s" % (_("Țara"), (u"%s (%s)" % (_("Automat"), numeTara(self.tara))) if auto else numeTara(self.tara)),
			"tara"))
		alegeri.append((_("Calitatea: %s") % config.plugins.hdsyoutube.calitate.getText(), "calitate"))
		alegeri.append((_(T_ASPECT) % _(config.plugins.hdsyoutube.aspect.getText()), "aspect"))
		alegeri.append((_(T_DATE_BARA) % _(config.plugins.hdsyoutube.date_bara.getText()), "date_bara"))
		alegeri.append((_(T_REDARE_AUTO) % _(config.plugins.hdsyoutube.redare_auto.getText()), "redare_auto"))
		alegeri.append((_(T_NUMARATOARE) % _(config.plugins.hdsyoutube.urmeaza.getText()), "urmeaza"))
		alegeri.append((_("YouTube din Aplicații: %s") % _(config.plugins.hdsyoutube.deschide.getText()), "deschide"))
		import os
		if os.path.exists("/usr/bin/hds-navigator"):
			alegeri.append((_("Deschide pagina youtube.com/tv"), "pagina"))
		if self.yt.stare.cautari():
			alegeri.append((_("Șterge căutările"), "sterge"))
		self.session.openWithCallback(self._dupaMeniu, ChoiceBox, title=_("YouTube"), list=alegeri)

	def _dupaMeniu(self, ales=None):
		if not ales:
			return
		a, e = ales[1], self._curent()
		if a == "canal" and e:
			self._deschide(e.get("autor") or _("Canal"), "browse", self.yt.canal, e["autor_id"])
		elif a == "inrudite" and e:
			self._deschide(_("Asemănătoare: %s") % e["titlu"], "next", self.yt.inrudite, e["id"])
		elif a == "cauta-live":
			self.tastatura()
		elif a == "tara":
			self._alegeTara()
		elif a == "calitate":
			self._schimba(config.plugins.hdsyoutube.calitate)
		elif a == "deschide":
			self._schimba(config.plugins.hdsyoutube.deschide)
		elif a == "aspect":
			self._schimba(config.plugins.hdsyoutube.aspect, self._schimbaAspect)
		elif a == "date_bara":
			self._schimba(config.plugins.hdsyoutube.date_bara)
		elif a == "urmeaza":
			self._schimba(config.plugins.hdsyoutube.urmeaza)
		elif a == "redare_auto":
			self._schimba(config.plugins.hdsyoutube.redare_auto)
		elif a == "pagina":
			deschidePagina(self.session)
		elif a == "sterge":
			self.yt.stare.sterge_cautari()
			if self.filaCurenta == "cauta" and not self.stiva:
				self._arataCautari()

	def _alegeTara(self):
		"""the country of the charts (Music) and of Home and search: Automat (where the receiver is) or any country"""
		from Screens.ChoiceBox import ChoiceBox
		lista = [(u"%s (%s)" % (_("Automat"), numeTara(taraAutomata())), "auto")] + [(n, c) for c, n in tari()]
		v = (config.plugins.hdsyoutube.tara.value or "auto")
		v = "auto" if v.lower() == "auto" else v.upper()
		sel = next((i for i, x in enumerate(lista) if x[1] == v), 0)

		def gata(ales=None):
			if not ales:
				return
			config.plugins.hdsyoutube.tara.value = ales[1]
			config.plugins.hdsyoutube.tara.save()
			config.plugins.hdsyoutube.save()
			self.tara = taraTopuri()
			self.yt.gl = self.tara
			if self.filaCurenta in ("muzica", "acasa"):
				self.fila(self.filaCurenta, forteaza=True)
		self.session.openWithCallback(gata, ChoiceBox, title=_("Țara"), list=lista, selection=sel)

	def _schimba(self, element, dupa=None):
		from Screens.ChoiceBox import ChoiceBox

		def gata(ales=None):
			if ales:
				element.value = ales[1]
				element.save()
				config.plugins.hdsyoutube.save()
				if dupa:
					dupa()
		self.session.openWithCallback(gata, ChoiceBox, title=_("YouTube"),
			list=[(_(t), v) for v, t in element.choices.choices], selection=[v for v, t in element.choices.choices].index(element.value))

	def _schimbaAspect(self):
		"""the same list again in the other aspect, on the same item"""
		elemente = [x for x in self.elemente if x["fel"] != "mai"]
		filme = [k for k, x in enumerate(elemente) if x["fel"] != "raft"]   # the list's index of each tile
		if self.dale:
			t = self.grila.pozitie()[0]          # tiles -> list
			i = filme[t] if t < len(filme) else 0
		else:
			li = self["lista"].getSelectionIndex() or 0
			i = len([k for k in filme if k < li])   # list -> tiles (the shelf titles are not tiles)
		self._aspect()
		self.pixmapuri.clear()
		self._arata(self.titluLista, elemente, self.cont, self.capat, i)

	def _inchide(self):
		self.lucrator.opreste()
		self.descarcator.opreste()
		self.ceasPoza.stop()
		self.ceasFila.stop()
		self.ceasPoze.stop()
		self.ceasCerePoze.stop()
		self.ceasDecodor.stop()
		self.pixmapuri.clear()
		ascundeFond(self.session, sterge=True)
		try:
			if self.inainte is not None:
				self.session.nav.playService(self.inainte)
		except Exception as e:
			print("[HdsYouTube] channel back: %s" % e)
		elibereazaMemoria()


SKIN_FOND = """<screen name="HdsYouTubeFond" position="0,0" size="1920,1080" flags="wfNoBorder" zPosition="-4" backgroundColor="#000A0F1A">
	<eLabel text="YouTube" position="96,54" size="140,44" font="{fBold};28" foregroundColor="#00FFFFFF" backgroundColor="#00C4302B" halign="center" valign="center" />
	<eLabel position="96,102" size="1728,1" backgroundColor="#002A3350" />
</screen>"""


class HdsYouTubeFond(Screen):
	"""the backdrop under the windows opened from the YouTube screen (keyboard, menus, messages): YouTube's colour,
	not the TV channel. Hidden while a film plays."""

	def __init__(self, session):
		self.skin = scaledSkin(SKIN_FOND.format(fBold=_font("Bold")), 1920)
		Screen.__init__(self, session)
		self.skinName = "HdsYouTubeFond"


_FOND = {"ecran": None, "arata": False}


def arataFond(session):
	try:
		if _FOND["ecran"] is None:
			_FOND["ecran"] = session.instantiateDialog(HdsYouTubeFond)
		_FOND["ecran"].show()
		_FOND["arata"] = True
	except Exception as e:
		print("[HdsYouTube] backdrop: %s" % e)


def ascundeFond(session, sterge=False):
	f = _FOND["ecran"]
	if f is None:
		return
	try:
		f.hide()
		if sterge:
			_FOND["ecran"], _FOND["arata"] = None, False
			session.deleteDialog(f)
	except Exception as e:
		print("[HdsYouTube] backdrop: %s" % e)


# bar 1 at the bottom (INFO), bar 2 over most of the screen (INFO again; the layout of the satellite channels' second
# bar: title, channel line, two columns of data, the description), the row of clips over bar 1 (UP/DOWN); all inside the
# title-safe area. Only the parts of the state shown are visible (HdsYouTubeRedare._aseaza).
SKIN_REDARE = """<screen name="HdsYouTubeRedare" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#ff000000">
	<widget name="b1_fond" position="96,880" size="1728,140" backgroundColor="#200A0F1A" zPosition="1" />
	<widget name="b1_bara" position="96,880" size="8,140" backgroundColor="#00C4302B" zPosition="2" />
	<widget source="titlu" render="RunningText" options="movetype=swimming,startdelay=2500,steptime=40,step=3,repeat=2" position="128,886" size="1400,44" font="{fBold};30" foregroundColor="#00F2F4F8" backgroundColor="#200A0F1A" noWrap="1" transparent="1" zPosition="2" />
	<widget name="timp" position="1540,886" size="260,44" font="{fRegular};28" foregroundColor="#00C9D2E3" backgroundColor="#200A0F1A" halign="right" transparent="1" zPosition="2" />
	<widget source="date" render="RunningText" options="movetype=swimming,startdelay=2500,steptime=40,step=3,repeat=2" position="128,930" size="1672,32" font="{fRegular};24" foregroundColor="#009FB4FF" backgroundColor="#200A0F1A" noWrap="1" transparent="1" zPosition="2" />
	<widget name="progres" position="128,968" size="1672,8" borderWidth="0" foregroundColor="#00C4302B" backgroundColor="#002A3350" zPosition="2" />
	<widget name="taste" position="128,982" size="1672,32" font="{fRegular};22" foregroundColor="#00C9D2E3" backgroundColor="#200A0F1A" noWrap="1" transparent="1" zPosition="2" />
	<widget name="b2_fond" position="96,96" size="1728,764" backgroundColor="#100A0F1A" zPosition="3" />
	<widget name="b2_bara" position="96,96" size="1728,6" backgroundColor="#00C4302B" zPosition="4" />
	<widget name="b2_titlu" position="128,116" size="1664,90" font="{fBold};34" foregroundColor="#00F2F4F8" backgroundColor="#100A0F1A" transparent="1" zPosition="4" />
	<widget name="b2_canal" position="128,210" size="1664,36" font="{fRegular};26" foregroundColor="#009FB4FF" backgroundColor="#100A0F1A" noWrap="1" transparent="1" zPosition="4" />
	<widget name="b2_clip_t" position="128,262" size="800,34" font="{fBold};26" foregroundColor="#00FFD27A" backgroundColor="#100A0F1A" transparent="1" zPosition="4" />
	<widget name="b2_clip" position="128,300" size="800,300" font="{fRegular};24" foregroundColor="#00E8ECF4" backgroundColor="#100A0F1A" transparent="1" zPosition="4" />
	<widget name="b2_teh_t" position="960,262" size="832,34" font="{fBold};26" foregroundColor="#00FFD27A" backgroundColor="#100A0F1A" transparent="1" zPosition="4" />
	<widget name="b2_teh" position="960,300" size="832,300" font="{fRegular};24" foregroundColor="#00E8ECF4" backgroundColor="#100A0F1A" transparent="1" zPosition="4" />
	<widget name="b2_desc_t" position="128,612" size="1664,34" font="{fBold};26" foregroundColor="#00FFD27A" backgroundColor="#100A0F1A" transparent="1" zPosition="4" />
	<widget name="b2_desc" position="128,650" size="1664,196" font="{fRegular};24" foregroundColor="#00C9D2E3" backgroundColor="#100A0F1A" transparent="1" zPosition="4" />
	<widget name="u_fond" position="1328,548" size="496,476" backgroundColor="#100A0F1A" zPosition="6" />
	<widget name="u_bara" position="1328,548" size="496,4" backgroundColor="#00C4302B" zPosition="7" />
	<widget name="u_eticheta" position="1344,560" size="360,40" font="{fBold};28" foregroundColor="#00FFD27A" backgroundColor="#100A0F1A" transparent="1" zPosition="7" />
	<widget name="u_numar" position="1704,560" size="104,40" font="{fBold};32" foregroundColor="#00FFFFFF" backgroundColor="#100A0F1A" halign="right" transparent="1" zPosition="7" />
	<widget name="u_poza" position="1344,608" size="464,261" alphatest="off" zPosition="7" />
	<widget name="u_titlu" position="1344,876" size="464,60" font="{fBold};22" foregroundColor="#00F2F4F8" backgroundColor="#100A0F1A" transparent="1" zPosition="7" />
	<widget name="u_canal" position="1344,938" size="464,28" font="{fRegular};20" foregroundColor="#009FB4FF" backgroundColor="#100A0F1A" noWrap="1" transparent="1" zPosition="7" />
	<widget name="u_taste" position="1344,972" size="464,40" font="{fRegular};20" foregroundColor="#00C9D2E3" backgroundColor="#100A0F1A" noWrap="1" transparent="1" zPosition="7" />
	<widget name="r_titlu" position="96,560" size="1728,36" font="{fBold};26" foregroundColor="#00F2F4F8" backgroundColor="#100A0F1A" zPosition="3" />
	<widget name="rand" position="%d,600" size="%d,%d" backgroundColor="#100A0F1A" backgroundColorSelected="#100A0F1A" scrollbarMode="showNever" zPosition="3" />
</screen>""" % (D.GRILA_X, D.LATIME_GRILA, D.RAND_H - D.RAFT_H)


class Sir(object):
	"""the clips around the one playing (YTN8): the films of the list it was started from, then YouTube's related films
	of the current clip; next/previous and the player's row of clips go along it"""

	def __init__(self, yt, filme=(), i=0, ecran=None):
		self.yt = yt
		self.filme = [x for x in filme if isinstance(x, dict) and x.get("id")]
		self.i = max(0, min(int(i), len(self.filme) - 1)) if self.filme else 0
		self.ecran = ecran           # the YouTube screen (its pictures), None from the web page
		self.inrudite = []
		self.detalii = {}

	def curent(self):
		return self.filme[self.i] if 0 <= self.i < len(self.filme) else None

	def urmatorul(self):
		"""the next film of the list, else the first related one not played yet"""
		if self.i + 1 < len(self.filme):
			return self.filme[self.i + 1]
		ids = set(x.get("id") for x in self.filme)
		return next((x for x in self.inrudite if x.get("id") not in ids and not x.get("live")), None)

	def anteriorul(self):
		return self.filme[self.i - 1] if self.i > 0 else None

	def treci(self, e):
		"""e becomes the clip playing: its place in the list, or added after the current one (a related film)"""
		for k, x in enumerate(self.filme):
			if x.get("id") == e.get("id"):
				self.i = k
				return
		self.filme.insert(self.i + 1, e)
		self.i += 1

	def randul(self):
		"""the clips of the row: those after the current one in the list, then the related ones"""
		ids = set()
		rez = []
		for x in self.filme[self.i + 1:] + self.filme[:self.i] + self.inrudite:
			if x.get("id") not in ids and x.get("fel", "film") == "film":
				ids.add(x.get("id"))
				rez.append(x)
		return rez[:30]


def _milioane(n):
	"""a count the short way (1,2 mil., 35 K), with the decimal comma"""
	try:
		n = int(n)
	except (TypeError, ValueError):
		return ""
	if n >= 1000000:
		return (u"%.1f mil." % (n / 1000000.0)).replace(".", ",", 1)
	if n >= 1000:
		return u"%d K" % (n // 1000)
	return u"%d" % n


def dateScurte(r, e=None):
	"""bar 1's data line: channel, size, codec, bit rate, length, views"""
	v = r.get("video") or {}
	a = r.get("audio") or {}
	parti = [r.get("autor") or (e or {}).get("autor") or ""]
	if v.get("inaltime"):
		parti.append(u"%dx%d%s" % (v.get("latime", 0), v["inaltime"], (u" %d fps" % v["fps"]) if v.get("fps") else ""))
	codecuri = [x.get("codec", "").split(".")[0] for x in (v, a) if x.get("codec")]
	if codecuri:
		parti.append(u" + ".join(codecuri))
	debit = (v.get("debit") or 0) + (a.get("debit") or 0)
	if debit:
		parti.append((u"%.1f Mb/s" % (debit / 1000000.0)).replace(".", ",") if debit >= 1000000 else u"%d kb/s" % (debit // 1000))
	if r.get("durata") and not r.get("live"):
		parti.append(_ceasText(r["durata"]))
	viz = _milioane(r.get("vizionari_nr")) if r.get("vizionari_nr") else (e or {}).get("vizionari", "")
	if viz:
		parti.append(viz)
	return u"  ·  ".join(p for p in parti if p)


def dateDetaliate(r, detalii=None, e=None):
	"""bar 2: (the clip's lines, the technical lines, the description)"""
	detalii = detalii or {}
	v = r.get("video") or {}
	a = r.get("audio") or {}
	clip = []
	# YouTube's own texts ("Publicat pe ...", "10 K de vizionări") are shown as they come, without a label
	for text in (detalii.get("data") or (e or {}).get("data"), (_("Vizionări") + u": " + _milioane(r["vizionari_nr"]))
			if r.get("vizionari_nr") else (e or {}).get("vizionari")):
		if text:
			clip.append(text)
	for eticheta, val in (
			(_("Aprecieri"), detalii.get("aprecieri")),
			(_("Durata"), _ceasText(r["durata"]) if r.get("durata") and not r.get("live") else (_("În direct") if r.get("live") else "")),
			(_("Capitole"), u", ".join(u"%s %s" % (_ceasText(s), n) for s, n in (r.get("capitole") or [])[:4])),
			(_("Subtitrări"), u", ".join(u"%s%s" % (s.get("nume") or s.get("limba"), u" (auto)" if s.get("automate") and
				"auto" not in (s.get("nume") or "").lower() else "")
				for s in (r.get("subtitrari") or [])[:6])),
			(_("Piste audio"), u", ".join(p.get("nume", "") for p in (r.get("piste_audio") or [])[:5]))):
		if val:
			clip.append(u"%s: %s" % (eticheta, val))
	teh = [u"ID: %s" % r.get("id", "")]
	fel = {"mpd": u"DASH (MPD)", "hls": u"HLS", "url": _("progresiv")}.get(r.get("fel"), r.get("fel") or "")
	teh.append(u"%s: %s   %s: %s" % (_("Tip"), fel, _("Client"), r.get("client", "")))
	if v:
		teh.append(u"%s: itag %s  %s  %sx%s  %s fps  %d kb/s" % (_("Video"), v.get("itag"), v.get("codec"), v.get("latime"),
			v.get("inaltime"), v.get("fps"), (v.get("debit") or 0) // 1000))
	if a:
		teh.append(u"%s: itag %s  %s  %d kb/s%s" % (_("Audio"), a.get("itag"), a.get("codec"), (a.get("debit") or 0) // 1000,
			(u"  " + a["limba"]) if a.get("limba") else ""))
	if v.get("marime") or a.get("marime"):
		teh.append((u"%s: %.1f MB" % (_("Mărime"), ((v.get("marime") or 0) + (a.get("marime") or 0)) / 1048576.0)).replace(".", ","))
	try:
		with open("/proc/stb/vmpeg/0/xres") as f1, open("/proc/stb/vmpeg/0/yres") as f2:
			x, y = int(f1.read().strip(), 16), int(f2.read().strip(), 16)
		if 0 < x < 10000:
			teh.append(u"%s: %dx%d" % (_("Imaginea redată"), x, y))
	except (IOError, OSError, ValueError):
		pass
	desc = (r.get("descriere") or "").strip()
	return u"\n".join(clip), u"\n".join(teh), desc[:600]


STAGNARE_S = 20
VERIFICARE_IMAGINE_S = 12      # the MPD start takes ~5 s on a ZGEMMA (dashdemux reads the index), a live ~3 s
# a film whose time is still 0:00 this long after the start did not start (seen on a ZGEMMA H8.2H: black screen at
# 0:00, the same film played when started again): it is started once more by itself, with fresh addresses (a new
# player answer and a new MPD); a film starts in 2-3 s there (5 s on the first index read). MIPS receivers (Vu+ Solo SE)
# were never measured: they get more time, so a slow but normal start is not torn down
PORNIRE_S = 9
PORNIRE_MIPS_S = 16


def _pornireS():
	import platform
	return PORNIRE_MIPS_S if platform.machine().lower().startswith("mips") else PORNIRE_S


ASTEPTARE_DECODOR_S = 3
JURNAL = "/tmp/hds-youtube/redare.log"     # the player's own journal (RAM, at most ~64 KB): what each start did


def jurnal(text):
	import os, time
	linie = "%s %s" % (time.strftime("%H:%M:%S"), text)
	print("[HdsYouTube] " + text)
	try:
		if os.path.exists(JURNAL) and os.path.getsize(JURNAL) > 64 * 1024:
			with open(JURNAL) as f:
				vechi = f.read()[-32 * 1024:]
			with open(JURNAL, "w") as f:
				f.write(vechi)
		with open(JURNAL, "a") as f:
			f.write(linie + "\n")
	except (IOError, OSError):
		pass
# the picture appears with the first second of sound on a ZGEMMA H8.2H (1.6-3.9 s after the start, measured on 40 films);
# sound for this long without a picture is the start that went wrong
IMAGINE_RAPIDA_S = 2
# new starts with fresh addresses before the person is told the film cannot play: on a ZGEMMA H8.2H one film needed four
# starts (the picture stream did not come three times, then it did), and each new start costs ~3 s
RELUARI_MAX = 3


def decodorOcupat():
	"""True while enigma2 still holds the video decoder (/dev/dvb/adapter0/video0): a stopped film's pipeline gives it
	back a moment after the stop (on its own thread); the TV side waits for the same thing (servicedvb, 3 s at most)"""
	import os
	try:
		for fd in os.listdir("/proc/self/fd"):
			try:
				if os.readlink("/proc/self/fd/" + fd) == "/dev/dvb/adapter0/video0":
					return True
			except OSError:
				pass
	except OSError:
		pass
	return False


def _ceasText(s):
	s = max(0, int(s))
	return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60) if s >= 3600 else "%d:%02d" % (s // 60, s % 60)


class HdsYouTubeRedare(Screen):
	"""a light player for weak receivers: the film runs as the current service (like a zap), this screen only shows the
	title and the time for a few seconds and takes the keys. The image's MoviePlayer took ~5 s of the main thread just to
	build its skin on a ZGEMMA (HdsPaznic). OK pause/continue, LEFT/RIGHT 10 s, UP/DOWN 1 minute, EXIT back to the
	list (the first EXIT with the bar hidden shows it); the previous channel comes back on exit; the end closes it."""
	ALLOW_SUSPEND = True

	def __init__(self, session, serviciu, r, sir=None):
		Screen.__init__(self, session)
		self.skin = scaledSkin(SKIN_REDARE.format(fRegular=_font("Regular"), fBold=_font("Bold")), 1920)
		from Components.ProgressBar import ProgressBar
		from Components.ServiceEventTracker import ServiceEventTracker
		from enigma import iPlayableService
		self.r, self.serviciu = r, serviciu
		self.sir = sir or Sir(Y.YouTube(limba()), [{"fel": "film", "id": r.get("id", ""), "titlu": r.get("titlu", "")}])
		self.stare_ecran = "nimic"     # what is shown: "nimic", "bara1", "bara2", "rand", "urmeaza"
		self["titlu"] = StaticText("")
		for k in ("timp", "taste", "b1_fond", "b1_bara", "b2_fond", "b2_bara", "b2_titlu", "b2_canal", "b2_clip_t",
				"b2_clip", "b2_teh_t", "b2_teh", "b2_desc_t", "b2_desc", "r_titlu", "u_fond", "u_bara", "u_eticheta", "u_titlu",
				"u_canal", "u_numar", "u_taste"):
			self[k] = Label("")
		self["u_poza"] = Pixmap()
		self.urmeazaGata = False       # the countdown runs: the next clip's addresses are fetched, not started yet
		self.urmeazaAnulat = False     # EXIT on the countdown: the clip ends and the list comes back
		self["date"] = StaticText("")
		self["progres"] = ProgressBar()
		self["rand"] = MenuList([], content=eListboxPythonMultiContent)
		self.randul, self.randAles, self.randInceput = [], 0, 0
		self._puneTitlul()
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions", "InfoActions", "NumberActions"], {
			"ok": self.ok, "cancel": self.iesire, "left": lambda: self.sageata(-1), "right": lambda: self.sageata(1),
			"up": self.comutaRandul, "down": self.comutaRandul, "info": self.info,
			"1": lambda: self.salt(-60), "3": lambda: self.salt(60), "4": lambda: self.salt(-300), "6": lambda: self.salt(300),
		}, -1)
		# << >> = 1 minute; CH+/CH- and >| |< = next/previous clip (only these actions of the contexts are taken)
		self["salturi"] = ActionMap(["MediaPlayerSeekActions"], {
			"seekBack": lambda: self.salt(-60), "seekFwd": lambda: self.salt(60)}, -1)
		self["clipuri"] = ActionMap(["ChannelSelectBaseActions", "MediaPlayerActions"], {
			"nextBouquet": lambda: self.sari(1), "prevBouquet": lambda: self.sari(-1),
			"next": lambda: self.sari(1), "previous": lambda: self.sari(-1)}, -1)
		self.urmeazaE, self.urmeazaS = None, 0
		self.schimb = None
		self.inainte = session.nav.getCurrentlyPlayingServiceReference()
		self.pe_pauza = False
		self.ascunde = 0
		self.ultimaPoz, self.pasiPeLoc = -1, 0
		self.ceas = eTimer()
		try:
			self.ceas.callback.append(self.pas)
		except AttributeError:
			self._legatura = self.ceas.timeout.connect(self.pas)
		self.urmaritor = ServiceEventTracker(screen=self, eventmap={iPlayableService.evEOF: self.sfarsit})
		self.onLayoutFinish.append(self.porneste)
		self.onClose.append(self.inchide)

	# ------------------------------------------------------------------ what is shown (YTN8)
	def _puneTitlul(self):
		r = self.r
		self["titlu"].text = (u"● " if r.get("live") else u"") + (r.get("titlu") or u"")
		self["date"].text = dateScurte(r, self.sir.curent()) if config.plugins.hdsyoutube.date_bara.value == "da" else ""
		self["taste"].setText(_("EXIT: Înapoi") if r.get("live") else _(T_TASTE_REDARE))
		self["b2_titlu"].setText(r.get("titlu") or "")
		self["b2_canal"].setText(D.fara_taiere(r.get("autor") or ""))
		self["b2_clip_t"].setText(_(T_DETALII))
		self["b2_teh_t"].setText(_(T_PENTRU_TEHNICIENI))
		self._puneDetaliile()

	def _puneDetaliile(self):
		clip, teh, desc = dateDetaliate(self.r, self.sir.detalii, self.sir.curent())
		self["b2_clip"].setText(clip)
		self["b2_teh"].setText(teh)
		self["b2_desc_t"].setText(_(T_DESCRIERE_CLIP) if desc else "")
		self["b2_desc"].setText(desc)

	def _aseaza(self, stare, secunde=0):
		"""one of: nothing, bar 1 (for `secunde`, 0 = until a key), bar 2, the row of clips, the "next" countdown"""
		self.stare_ecran = stare
		b1 = stare in ("bara1", "rand")
		for k in ("u_fond", "u_bara", "u_eticheta", "u_titlu", "u_canal", "u_numar", "u_taste"):
			(self[k].show if stare == "urmeaza" else self[k].hide)()
		if stare != "urmeaza":
			self["u_poza"].hide()
		for k in ("b1_fond", "b1_bara", "timp", "progres", "taste"):
			(self[k].show if b1 else self[k].hide)()
		# the title moves (RunningText): emptied while bar 1 is not shown, put back with it
		if b1:
			if not self["titlu"].text and getattr(self, "_titluSalvat", ""):
				self["titlu"].text = self._titluSalvat
		else:
			if self["titlu"].text:
				self._titluSalvat = self["titlu"].text
			self["titlu"].text = ""
		for k in ("b2_fond", "b2_bara", "b2_titlu", "b2_canal", "b2_clip_t", "b2_clip", "b2_teh_t", "b2_teh", "b2_desc_t", "b2_desc"):
			(self[k].show if stare == "bara2" else self[k].hide)()
		for k in ("r_titlu", "rand"):
			(self[k].show if stare == "rand" else self[k].hide)()
		self["date"].text = (dateScurte(self.r, self.sir.curent()) if b1 and config.plugins.hdsyoutube.date_bara.value == "da"
			else "")
		if stare == "nimic":
			self.hide()
		else:
			self.show()
		self.ascunde = secunde

	def info(self):
		"""INFO: bar 1, INFO again: bar 2 (details), INFO a third time: closed"""
		if self.stare_ecran in ("nimic", "rand"):
			self._aseaza("bara1", 8)
			self.pas()
		elif self.stare_ecran == "bara1":
			self._puneDetaliile()
			self._aseaza("bara2")
		elif self.stare_ecran == "bara2":
			self._aseaza("nimic")

	def ok(self):
		if self.stare_ecran == "rand":
			e = self.randul[self.randAles] if 0 <= self.randAles < len(self.randul) else None
			if e:
				self._aseaza("nimic")
				self.pornesteClip(e)
			return
		if self.stare_ecran == "urmeaza":
			self._urmeazaAcum()
			return
		self.pauza()

	def sageata(self, pas):
		if self.stare_ecran == "rand":
			n = len(self.randul)
			if not n:
				return
			vechi = self.randAles
			self.randAles = max(0, min(n - 1, self.randAles + pas))
			if self.randAles != vechi:
				if self.randAles < self.randInceput:
					self.randInceput = self.randAles
				elif self.randAles >= self.randInceput + D.COLOANE:
					self.randInceput = self.randAles - D.COLOANE + 1
				self._deseneazaRandul()
			return
		if self.stare_ecran == "urmeaza":
			return
		self.salt(10 * pas)

	def comutaRandul(self):
		"""UP/DOWN: the row of clips (the next ones of the list, then related); again: closed"""
		if self.stare_ecran == "rand":
			self._puneTitlul()
			self._aseaza("nimic")
			return
		if self.stare_ecran == "urmeaza":
			return
		self.randul = self.sir.randul()
		self.randAles, self.randInceput = 0, 0
		self["r_titlu"].setText(u"  " + _(T_ALTE_CLIPURI))
		self._pregatesteRandul()
		self._deseneazaRandul()
		self._aseaza("rand")
		self["taste"].setText(_(T_TASTE_RAND))
		e = self.sir.ecran
		if e is not None:
			e.cerePoze(self.randul[:D.COLOANE * 2], self._pozaRand)

	def _pregatesteRandul(self):
		if getattr(self, "_randGata", False):
			return
		self._randGata = True
		try:
			from enigma import getDesktop
			self.scara = getDesktop(0).size().width() / 1920.0
		except Exception:
			self.scara = 1.0
		s = lambda v: int(round(v * self.scara))
		l = self["rand"].l
		l.setFont(0, gFont(_font("Regular"), s(D.FONT_TITLU)))
		l.setFont(1, gFont(_font("Regular"), s(D.FONT_AUTOR)))
		l.setFont(2, gFont(_font("Bold"), s(D.FONT_ETICHETA)))
		l.setItemHeight(s(D.RAND_H - D.RAFT_H))
		inst = self["rand"].instance
		if inst is not None:
			if hasattr(inst, "setRedrawOnSelection"):
				inst.setRedrawOnSelection(False)
			inst.setSelectionEnable(0)

	def _deseneazaRandul(self):
		s = lambda v: int(round(v * getattr(self, "scara", 1.0)))
		T = eListboxPythonMultiContent.TYPE_TEXT
		pl, ph = s(D.POZA_L), s(D.POZA_H)
		py = s(D.CHENAR)
		pixmapuri = self.sir.ecran.pixmapuri if self.sir.ecran is not None else {}
		intrari = [0]
		for k in range(D.COLOANE):
			i = self.randInceput + k
			if i >= len(self.randul):
				break
			e = self.randul[i]
			x = s(D.x_dala(k))
			if i == self.randAles:
				c = s(D.CHENAR)
				intrari.append((T, x - c, py - c, pl + 2 * c, ph + 2 * c, 0, 0, "", None, None, C_CHENAR, C_CHENAR))
			p = pixmapuri.get(D.poza_dala(e))
			if p is None:
				intrari.append((T, x, py, pl, ph, 0, 0, "", None, None, C_LOC, C_LOC))
			else:
				intrari.append((eListboxPythonMultiContent.TYPE_PIXMAP, x, py, min(p[1], pl), min(p[2], ph), p[0], None, None, 0))
			if e.get("durata") and not e.get("live"):
				el = s(16 + 12 * len(e["durata"]))
				eh = s(D.ETICHETA_H)
				intrari.append((T, x + pl - el - s(8), py + ph - eh - s(8), el, eh, 2, RT_HALIGN_CENTER | RT_VALIGN_CENTER,
					e["durata"], C_DURATA, C_DURATA, C_DURATA_FOND, C_DURATA_FOND))
			ct = C_TITLU_ALES if i == self.randAles else C_TITLU
			intrari.append((T, x, py + ph + s(6), pl, s(D.TITLU_H), 0, RT_HALIGN_LEFT | RT_VALIGN_TOP | RT_WRAP,
				D.fara_taiere(e.get("titlu") or ""), ct, ct, None, None))
		self["rand"].setList([intrari])

	def _pozaRand(self, u):
		if self.stare_ecran == "rand" and any(D.poza_dala(e) == u for e in self.randul[self.randInceput:self.randInceput + D.COLOANE]):
			self._deseneazaRandul()

	# ------------------------------------------------------------------ another clip without leaving (YTN8)
	def sari(self, pas):
		"""CH+/CH- (>| |<): the next / previous clip of the list (after its end: YouTube's related films)"""
		e = self.sir.urmatorul() if pas > 0 else self.sir.anteriorul()
		if e:
			self._aseaza("nimic")
			self.pornesteClip(e)

	def pornesteClip(self, e, afiseaza=True):
		"""another clip in the same player: its addresses on a thread, then the service is swapped (afiseaza=False:
		during the "next" countdown, which shows its own screen)"""
		if self.schimb is not None:
			return
		if afiseaza:
			self["titlu"].text = e.get("titlu") or ""
			self["timp"].setText(_("Pornesc filmul..."))
			self._aseaza("bara1", 30)
		rezultat = []
		self.schimb = (e, rezultat)
		yt = self.sir.yt

		def lucru():
			try:
				rezultat.append((True, yt.redare(e["id"], int(config.plugins.hdsyoutube.calitate.value))))
			except Exception as x:
				rezultat.append((False, str(x)))
		fir = threading.Thread(target=lucru, name="HdsYouTubeClip")
		fir.daemon = True
		fir.start()

	def _schimbaGata(self):
		import time
		e, rezultat = self.schimb
		self.schimb = None
		ok, r = rezultat[0]
		if not ok:
			self.session.open(MessageBox, _(T_NU_PORNESTE) % r, MessageBox.TYPE_ERROR, timeout=8)
			self._puneTitlul()
			return
		self.sir.treci(e)
		self.sir.detalii, self.sir.inrudite = {}, []
		try:
			self.sir.yt.stare.adauga_vazut(e)
		except Exception:
			pass
		self.r = r
		self.serviciu = eServiceReference(Y.referinta(r))
		self.serviciu.setName(r.get("titlu") or "YouTube")
		self.session.nav.stopService()
		self.opritIntentionat = time.time()
		self.pe_pauza = False
		self.repornit, self.imagineVerificata, self.imagineRapida, self.inceput = False, False, False, False
		self.reluari = 0
		self.urmeazaAnulat, self.urmeazaE, self.urmeazaGata = False, None, False
		self.pornit = time.time()
		self._puneTitlul()
		self._pornesteServiciul()
		self._aseaza("bara1", 6)
		self._ceareDetalii()

	def _ceareDetalii(self):
		"""the publishing date, the likes and the related films of the clip playing (one "next" call, on a thread)"""
		sir, vid = self.sir, self.r.get("id")
		if not vid or self.r.get("live"):
			return

		def lucru():
			try:
				d, rel = sir.yt.urmeaza(vid)
				if self.r.get("id") == vid:
					sir.detalii, sir.inrudite = d, rel
			except Exception as x:
				print("[HdsYouTube] details: %s" % x)
		fir = threading.Thread(target=lucru, name="HdsYouTubeDetalii")
		fir.daemon = True
		fir.start()

	# ------------------------------------------------------------------ the end: "next" with a countdown
	def _urmeazaAnunta(self, ramas):
		"""the last seconds of the clip (YouTube TV's way): a small panel in the corner over the film with the next
		clip's picture, title, channel and the seconds left, while the film keeps playing; the next clip's addresses
		are fetched now, so it starts at once when this one ends (OK: now, EXIT: no next clip, back to the list)"""
		e = self.sir.urmatorul()
		if not e:
			return
		self.urmeazaE = e
		self.urmeazaGata = True
		self.pornesteClip(e, afiseaza=False)        # the addresses only; started at the end of this clip
		self["u_eticheta"].setText(_(T_URMEAZA_TITLU))
		self["u_titlu"].setText(D.fara_taiere(e.get("titlu") or ""))
		self["u_canal"].setText(D.fara_taiere(e.get("autor") or ""))
		self["u_numar"].setText(u"%d s" % max(0, ramas))
		self["u_taste"].setText(_(T_URMEAZA_TASTE))
		self["u_poza"].hide()
		self._aseaza("urmeaza")
		self._pozaUrmatorului(e)

	def _urmeazaPorneste(self):
		"""the end of the clip: the next one at once (its addresses were fetched during the countdown), else the list"""
		e = self.urmeazaE
		jurnal("end of the clip: next %s (cancelled %s, addresses %s)" % ((e or {}).get("id"), self.urmeazaAnulat,
			"ready" if self.schimb is not None and self.schimb[1] else "coming" if self.schimb is not None else "none"))
		if e is None or self.urmeazaAnulat or config.plugins.hdsyoutube.redare_auto.value != "da":
			self.close()
			return
		self._urmeazaAcum()

	def _pozaUrmatorului(self, e):
		"""the next clip's big picture (YouTube's 1280x720 thumbnail, else the 320x180 one), downloaded on a thread and
		decoded at 960x540"""
		yt = self.sir.yt
		vid = e.get("id") or ""
		rezultat = []
		self.urmeazaPoza = rezultat

		def lucru():
			cale = None
			for nume in ("hq720", "mqdefault"):
				try:
					cale = yt.poza(dict(e, fel="mare-" + nume), "https://i.ytimg.com/vi/%s/%s.jpg" % (vid, nume))
				except Exception:
					cale = None
				if cale:
					break
			rezultat.append(cale)
		fir = threading.Thread(target=lucru, name="HdsYouTubePozaMare")
		fir.daemon = True
		fir.start()

	def _pozaMareGata(self, cale):
		try:
			if not hasattr(self, "decodorMare"):
				self.decodorMare = ePicLoad()
				try:
					self.decodorMare.PictureData.get().append(self._pozaMareDecodata)
				except AttributeError:
					self._legaturaMare = self.decodorMare.PictureData.connect(self._pozaMareDecodata)
				m = self["u_poza"].instance.size()
				self.decodorMare.setPara((m.width(), m.height(), 1, 1, False, 1, "#000A0F1A"))
			self.decodorMare.startDecode(cale)
		except Exception as x:
			print("[HdsYouTube] next picture: %s" % x)

	def _pozaMareDecodata(self, info=""):
		try:
			ptr = self.decodorMare.getData()
			if ptr is not None and self.stare_ecran == "urmeaza":
				self["u_poza"].instance.setPixmap(ptr)
				self["u_poza"].show()
		except Exception as x:
			print("[HdsYouTube] next picture: %s" % x)

	def _urmeazaAcum(self):
		"""the next clip now (OK on the countdown, or the end of the clip): at once when its addresses are here"""
		e, self.urmeazaE = self.urmeazaE, None
		self.urmeazaGata = False
		if e is None:
			return
		self["titlu"].text = e.get("titlu") or ""
		self["timp"].setText(_("Pornesc filmul..."))
		self._aseaza("bara1", 30)
		if self.schimb is None:
			self.pornesteClip(e)
		elif self.schimb[1]:
			self._schimbaGata()
		# else: the addresses are still coming; pas() starts it when they are here

	def _urmeazaVerifica(self, poz, lung):
		"""from pas(): the countdown starts URMEAZA seconds before the end and counts down over the film"""
		if self.r.get("live") or self.pe_pauza or not lung or self.urmeazaAnulat or \
				config.plugins.hdsyoutube.redare_auto.value != "da" or self.schimb is not None and not self.urmeazaE:
			return
		try:
			n = int(config.plugins.hdsyoutube.urmeaza.value)
		except ValueError:
			n = 7
		ramas = lung - poz
		if self.stare_ecran == "urmeaza" and ramas <= 1 and self.pasiPeLoc >= 2 and self.schimb is not None:
			# the time stands at the end and no end event came (seen on a Vu+ after winding to the end): taken as the end
			jurnal("end of the clip by time (no end event)")
			self._urmeazaPorneste()
			return
		if self.stare_ecran == "urmeaza":
			if ramas > n + 2:              # wound back: the countdown goes away, the next clip's addresses stay
				self._aseaza("nimic")
			else:
				self["u_numar"].setText(u"%d s" % max(0, ramas))
		elif 0 < ramas <= n and self.stare_ecran in ("nimic", "bara1") and lung > n + 5:
			if self.urmeazaE is None:
				self._urmeazaAnunta(ramas)
			else:
				self._aseaza("urmeaza")

	def porneste(self):
		import time
		self.pornit = time.time()
		self.imagineVerificata = False
		self.repornit = False
		self.inceput = False           # the film's time has moved past 0
		self.reiau = None              # the fresh addresses being fetched (a list filled by the thread), or None
		self.imagineRapida = False     # the early check of the picture was done
		self.reluari = 0               # new starts made by the player for this clip (RELUARI_MAX)
		self.fondAscuns = _FOND["ecran"] is not None and _FOND["arata"]
		if self.fondAscuns:
			_FOND["ecran"].hide()       # the film is drawn by the board under the screens: the backdrop would cover it
		self._pornesteServiciul()
		self.arata()
		self.ceas.start(1000, False)
		self._ceareDetalii()

	def _pornesteServiciul(self):
		"""the film starts when the video decoder is free: a film stopped just before lets it go on GStreamer's own
		thread a moment later (servicemp3 stops the pipeline on its film thread), and a new film started meanwhile got
		no picture, only sound (seen on a ZGEMMA H8.2H: about one film in ten started right after another; the same
		film played when started again). At most ASTEPTARE_DECODOR_S, then it starts anyway."""
		import time
		self.astept = time.time()
		self._incearcaPornirea()

	def _incearcaPornirea(self):
		import time
		if self.astept is None:
			return
		if decodorOcupat() and time.time() - self.astept < ASTEPTARE_DECODOR_S:
			if not hasattr(self, "ceasDecodor"):
				self.ceasDecodor = eTimer()
				try:
					self.ceasDecodor.callback.append(self._incearcaPornirea)
				except AttributeError:
					self._legaturaDecodor = self.ceasDecodor.timeout.connect(self._incearcaPornirea)
			self.ceasDecodor.start(100, True)
			return
		asteptat = time.time() - self.astept
		if asteptat >= 0.1:
			jurnal("video decoder free after %.1f s" % asteptat)
		self.astept = None
		v = self.r.get("video") or {}
		jurnal("start %s %s itag %s %s %sx%s" % (self.r.get("id"), self.r.get("fel"), v.get("itag"), v.get("codec"),
			v.get("latime"), v.get("inaltime")))
		self.session.nav.playService(self.serviciu)
		self.pornit = time.time()
		self.imagineVazuta = False
		self.ultimaPoz, self.pasiPeLoc = -1, 0

	def _cautare(self):
		s = self.session.nav.getCurrentService()
		return s and s.seek()

	def _areImagine(self):
		"""False when the board shows no picture (the sound plays alone): the picture width of the video decoder; a
		240p film on a ZGEMMA H8.2H left it at ffffffff (YTN1). None when it cannot be read"""
		try:
			with open("/proc/stb/vmpeg/0/xres") as f:
				v = f.read().strip().lower()
		except (IOError, OSError):
			return None
		# only the exact "no picture" value counts; anything else (an older width, 0 on some boards) is not proof
		return False if v == "ffffffff" else None

	def _faraFluxVideo(self):
		"""True when the player has no video stream yet (width unknown); False when it cannot be read"""
		try:
			from enigma import iServiceInformation
			s = self.session.nav.getCurrentService()
			i = s and s.info()
			return bool(i) and i.getInfo(iServiceInformation.sVideoWidth) <= 0
		except Exception:
			return False

	def _pozitie(self):
		"""the film's time in seconds (0 when it cannot be read)"""
		c = self._cautare()
		p = c and c.getPlayPosition()
		return p[1] // 90000 if p and not p[0] else 0

	def _mergeSunetul(self):
		"""the film's time has moved at least 5 s (the sound plays); a live is taken as moving"""
		if self.r.get("live"):
			return True
		c = self._cautare()
		p = c and c.getPlayPosition()
		return bool(p and not p[0] and p[1] // 90000 >= 5)

	def _pornitDeja(self):
		"""True once the film's time has moved past 0:00 (a live counts as started)"""
		if self.inceput or self.r.get("live"):
			return True
		c = self._cautare()
		p = c and c.getPlayPosition()
		self.inceput = bool(p and not p[0] and p[1] > 0)
		return self.inceput

	def reia(self, motiv):
		"""the film started once more, by itself, with fresh addresses (the old ones may have been refused or the
		first segment did not come); the bar says so meanwhile. Without the film's id, the same service again."""
		import time
		self.repornit = True
		jurnal("restart (%s) after %.0f s: %s" % (motiv, time.time() - self.pornit, self.r.get("titlu")))
		self.arata(30)
		self["timp"].setText(_("Pornesc filmul..."))
		vid = self.r.get("id")
		if not vid:
			self._dinNou(None)
			return
		rezultat = []
		self.reiau = rezultat

		def lucru():
			try:
				rezultat.append(Y.YouTube(limba()).redare(vid, int(config.plugins.hdsyoutube.calitate.value)))
			except Exception as e:
				print("[HdsYouTube] restart: %s" % e)
				rezultat.append(None)
		fir = threading.Thread(target=lucru, name="HdsYouTubeReia")
		fir.daemon = True
		fir.start()

	def _dinNou(self, r):
		import time
		self.reiau = None
		if r:
			self.r.update(r)
			self.serviciu = eServiceReference(Y.referinta(self.r))
			self.serviciu.setName(self.r.get("titlu") or "YouTube")
		self.session.nav.stopService()
		self.opritIntentionat = time.time()
		self.pornit, self.imagineVerificata, self.inceput = time.time(), False, False
		self.imagineRapida = False     # each new start is checked again
		self._pornesteServiciul()
		self.arata()

	def pas(self):
		import time
		poza = getattr(self, "urmeazaPoza", None)
		if poza:
			self.urmeazaPoza = None
			if poza[0]:
				self._pozaMareGata(poza[0])
		if self.schimb is not None and not self.urmeazaGata:
			if self.schimb[1]:
				self._schimbaGata()
			return
		if getattr(self, "astept", None) is not None:
			return                     # waiting for the video decoder: the checks count from the real start
		if not getattr(self, "imagineVazuta", True) and not self.r.get("live"):
			# the first seconds in the player's journal: time, sound position, the board's picture, the stream's size
			dt = time.time() - self.pornit
			fara = self._faraFluxVideo()
			if not fara and self._areImagine() is not False:
				self.imagineVazuta = True
				jurnal("picture after %.1f s (sound at %d s)" % (dt, self._pozitie()))
			elif dt <= 16 and int(dt) % 2 == 0:
				jurnal("  %.0f s: sound at %d s, no picture yet (stream %s)" % (dt, self._pozitie(), "none" if fara else "yes"))
		if self.reiau is not None:
			if self.reiau:
				self._dinNou(self.reiau[0])
			return
		if not self.repornit and not self.pe_pauza and time.time() - self.pornit >= _pornireS() and not self._pornitDeja():
			self.reia("0:00")
			return
		if not self.imagineRapida and not self.pe_pauza and not self.r.get("live") and self._pozitie() >= IMAGINE_RAPIDA_S:
			self.imagineRapida = True
			# both signs: the player has no video stream AND the board shows no picture (on a Vu+ the stream's size is
			# not reported while the picture plays; on a ZGEMMA the board's width can keep the last film's value for a
			# moment, but it reads "no picture" by the 2nd second of sound when the stream is missing)
			if self._faraFluxVideo() and self._areImagine() is False and self.reluari < RELUARI_MAX:
				# the sound has played IMAGINE_RAPIDA_S and no video stream has reached the player (its size is still
				# unknown, -1). Measured on a ZGEMMA H8.2H (journal of 40 starts): the picture stream of the MPD came 6-12 s
				# late or not at all in about one start in ten, with the network fast (400 KB in 0.13 s from the same
				# addresses) and the decoder free; the same start again on the same MPD did not always help, a new start
				# (as when the person opens the film again) did. So: at once a new start with fresh addresses, before the
				# person waits for it (the board's picture width is not used here: it keeps the last film's value)
				self.reluari += 1
				self.reia("no video stream at %d s of sound, new start %d of %d" % (IMAGINE_RAPIDA_S, self.reluari, RELUARI_MAX))
				return
		if not self.imagineVerificata and time.time() - self.pornit >= VERIFICARE_IMAGINE_S and not self.pe_pauza and \
				self._mergeSunetul():
			self.imagineVerificata = True
			if self._areImagine() is False:
				# sound without picture (seen on a ZGEMMA H8.2H: the same film played the next time): new starts with
				# fresh addresses, up to RELUARI_MAX; only then the person is told instead of a black screen
				jurnal("no picture after %d s (new starts so far: %d): %s" % (VERIFICARE_IMAGINE_S, self.reluari,
					self.r.get("titlu")))
				if self.reluari >= RELUARI_MAX:
					self.blocat()
					return
				self.reluari += 1
				self.reia("no picture, new start %d of %d" % (self.reluari, RELUARI_MAX))
				return
		if self.r.get("live"):
			self["timp"].setText(_("În direct"))
			self["progres"].setValue(100)
		else:
			c = self._cautare()
			p = c and c.getPlayPosition()
			l = c and c.getLength()
			poz = p[1] // 90000 if p and not p[0] else 0
			lung = l[1] // 90000 if l and not l[0] and l[1] > 0 else int(self.r.get("durata") or 0)
			self["timp"].setText("%s / %s" % (_ceasText(poz), _ceasText(lung)) if lung else _ceasText(poz))
			self._urmeazaVerifica(poz, lung)
			self["progres"].setValue(int(100 * poz / lung) if lung else 0)
			# a film whose time does not move for STAGNARE_S (not paused) is stuck: the board did not start the
			# picture (seen with a 320x240 film on a ZGEMMA) or the network stopped; it never sends an end, so we tell
			if poz != self.ultimaPoz or self.pe_pauza:
				self.ultimaPoz, self.pasiPeLoc = poz, 0
			else:
				self.pasiPeLoc += 1
				if self.pasiPeLoc == STAGNARE_S:
					self.blocat()
					return
		if self.ascunde and not self.pe_pauza and self.stare_ecran == "bara1":
			self.ascunde -= 1
			if self.ascunde == 0:
				self._aseaza("nimic")

	def arata(self, secunde=5):
		if self.stare_ecran in ("bara2", "rand", "urmeaza"):
			self.pas()
			return
		self._aseaza("bara1", secunde)
		self.pas()

	def pauza(self):
		if not self.r.get("live"):
			s = self.session.nav.getCurrentService()
			p = s and s.pause()
			if p:
				if self.pe_pauza:
					p.unpause()
				else:
					p.pause()
				self.pe_pauza = not self.pe_pauza
		self.arata()

	def salt(self, secunde):
		c = self._cautare()
		if c and not self.r.get("live") and c.isCurrentlySeekable():
			c.seekRelative(1 if secunde > 0 else -1, abs(secunde) * 90000)
		self.arata()

	def blocat(self):
		self.ceas.stop()
		self.session.openWithCallback(lambda *r: self.close(), MessageBox, _(T_NU_SE_REDA), MessageBox.TYPE_ERROR, timeout=8)

	def sfarsit(self):
		import time
		if getattr(self, "astept", None) is not None or (self.schimb is not None and not self.urmeazaGata) or \
				time.time() - getattr(self, "opritIntentionat", 0) < 5:
			# the end of the film stopped on purpose a moment ago (another clip, a new start): not this film's end
			jurnal("end event ignored (film stopped on purpose)")
			return
		jurnal("end event at %s s" % self._pozitie())
		if time.time() - self.pornit < 8:
			# the end within seconds of the start is a failure (address refused, stream cut), not the end of the film
			self.session.openWithCallback(lambda *r: self.close(), MessageBox, _(T_NU_SE_REDA), MessageBox.TYPE_ERROR,
				timeout=8)
			return
		if self.r.get("live") or (self.schimb is not None and not self.urmeazaGata):
			self.close()
			return
		self._urmeazaPorneste()

	def iesire(self):
		"""EXIT closes what is open (bar, row, details, the countdown); with nothing open, back to the list"""
		if self.stare_ecran == "urmeaza":
			self.urmeazaAnulat = True
			self.urmeazaE, self.urmeazaGata = None, False
			self._aseaza("nimic")
			return
		if self.stare_ecran != "nimic":
			self._puneTitlul()
			self._aseaza("nimic")
			return
		self.close()

	def inchide(self):
		self.ceas.stop()
		self.astept = None
		if hasattr(self, "ceasDecodor"):
			self.ceasDecodor.stop()
		self.session.nav.stopService()
		if self.inainte is not None:
			self.session.nav.playService(self.inainte)
		if getattr(self, "fondAscuns", False) and _FOND["ecran"] is not None:
			_FOND["ecran"].show()
		ecran = self.sir.ecran
		if ecran is not None and ecran.ascultatorPoze is not None:
			# the row's pictures are no longer wanted: the screen asks again for those of its own tiles
			ecran.ascultatorPoze = None
			try:
				ecran._cerePoze()
			except Exception as e:
				print("[HdsYouTube] pictures back: %s" % e)
		elibereazaMemoria()


def elibereazaMemoria(dupa_s=3):
	"""the memory a stopped film left free given back to the system (glibc malloc_trim), on a thread a few seconds
	later (after the player's pipeline is gone). Measured on a ZGEMMA H8.2H (334 MB): after a YouTube film enigma2
	kept 10-33 MB of freed GStreamer buffers that malloc_trim returned; 40 films in a row: the Python objects did not
	grow (253 000), the memory stayed near 182-194 MB after the trim, while without it it went to 205-237 MB and the
	free memory of the receiver down to ~28 MB. Without glibc (or on an error) nothing happens."""
	def lucru():
		import time
		time.sleep(dupa_s)
		try:
			import ctypes
			ctypes.CDLL("libc.so.6").malloc_trim(0)
		except Exception as e:
			print("[HdsYouTube] malloc_trim: %s" % e)
	fir = threading.Thread(target=lucru, name="HdsYouTubeMemorie")
	fir.daemon = True
	fir.start()


def reda(session, r, dupa=None, sir=None):
	"""plays a HdsYouTube.redare() answer in the image's player; sir: the clips around it (Sir)"""
	serviciu = eServiceReference(Y.referinta(r))
	serviciu.setName(r.get("titlu") or "YouTube")
	if dupa:
		session.openWithCallback(dupa, HdsYouTubeRedare, serviciu, r, sir)
	else:
		session.open(HdsYouTubeRedare, serviciu, r, sir)


_CEASURI_WEB = []


def redaId(session, vid, gata=None):
	"""plays a film by its id (the web page's "play on the TV"); on a thread, the player opens on the main loop.
	gata(text_eroare_sau_None) is called on the main loop."""
	rezultat = []

	def lucru():
		try:
			yt = Y.YouTube(limba())
			r = yt.redare(vid, int(config.plugins.hdsyoutube.calitate.value))
			yt.stare.adauga_vazut({"fel": "film", "id": vid, "titlu": r.get("titlu", ""), "live": r.get("live")})
			rezultat.append((True, r))
		except Exception as e:
			rezultat.append((False, str(e)))

	ceas = eTimer()

	def verifica():
		if not rezultat:
			return
		ceas.stop()
		if pereche in _CEASURI_WEB:
			_CEASURI_WEB.remove(pereche)
		ok, val = rezultat[0]
		if ok:
			reda(session, val)
		elif not gata:
			session.open(MessageBox, _(T_NU_PORNESTE) % val, MessageBox.TYPE_ERROR, timeout=10)
		if gata:
			gata(None if ok else val)

	legatura = None
	try:
		ceas.callback.append(verifica)
	except AttributeError:
		legatura = ceas.timeout.connect(verifica)
	pereche = (ceas, legatura)
	_CEASURI_WEB.append(pereche)      # kept alive until its answer, also when several web requests overlap
	fir = threading.Thread(target=lucru, name="HdsYouTubeWeb")
	fir.daemon = True
	fir.start()
	ceas.start(100, False)


def deschidePagina(session):
	"""the youtube.com/tv page of Applications (the old way), in the image's browser"""
	from Components import HdsAplicatii as A
	from Plugins.Extensions.HdsNavigator.ecrane import HdsNavigatorEcran
	from Plugins.Extensions.HdsNavigator import lansator as L
	a = next((x for x in A.SCURTATURI_IMAGINE if x["id"] == "youtube"), None)
	a = A.scurtaturaBuna(a) if a else None
	if a:
		session.open(HdsNavigatorEcran, L.MOD_APLICATIE, a["url"], None, a)


def porneste(session, **_rest):
	session.open(HdsYouTube)
