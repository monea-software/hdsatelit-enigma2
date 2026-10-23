# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ServiceEventTracker import ServiceEventTracker
from Components.ActionMap import NumberActionMap
from Components.ConfigList import ConfigListScreen
from Components.ChoiceList import ChoiceList, ChoiceEntryComponent
from Components.config import config, ConfigSubsection, getConfigListEntry, ConfigNothing, ConfigSelection, ConfigOnOff, \
	ConfigElement, KEY_LEFT, KEY_RIGHT
from Components.MultiContent import MultiContentEntryText
from Components.Sources.List import List
from Components.Sources.Boolean import Boolean
from Components.SystemInfo import SystemInfo

from enigma import iPlayableService

from Tools.ISO639 import LanguageCodes
from Tools.BoundFunction import boundFunction
import re
FOCUS_CONFIG, FOCUS_STREAMS = list(range(2))


def _pistaActiva():
	"""Semnul randului care merge acum (campul 5 al tuplului din streams). Text propriu, nu msgid-ul „Running”: acela
	are in alte limbi sensul de program pornit sau de instalare, iar aici e pista aleasa."""
	return _("Activă")


def _aceeasiSubtitrare(a, b):
	"""HDSatelit: aceeasi subtitrare dupa primele 4 campuri (tip, pid, pagina, magazin/pagina
	auxiliara). Subtitrarea pornita singura vine din getCachedSubtitle cu 4 campuri, randurile listei au 5,
	deci comparatia intreaga (==) nu le potrivea niciodata: randul pornit nu era marcat, iar OK pe el nu o oprea."""
	try:
		return bool(a) and bool(b) and len(a) >= 4 and len(b) >= 4 and tuple(a[:4]) == tuple(b[:4])
	except TypeError:
		return False


def _tineMinte(functie, *argumente):
	"""HDSatelit: ce alege omul de mana aici (pista audio, partea audio stanga/stereo/
	dreapta, o subtitrare sau nicio subtitrare) se tine minte pe canal, pentru totdeauna, si are intaietate fata de
	preferinte (Components/HdsPisteLimbi.py). Fara modul (inca lipsa din Components/Makefile.am) nu se tine minte
	nimic."""
	try:
		from Components import HdsPisteLimbi
	except ImportError:
		return
	except Exception as e:
		print("[AudioSelection] Components/HdsPisteLimbi.py nu se poate incarca: %s" % e)
		return
	try:
		getattr(HdsPisteLimbi, functie)(*argumente)
	except Exception as e:
		print("[AudioSelection] alegerea nu s-a putut tine minte pe canal: %s" % e)
[PAGE_AUDIO, PAGE_SUBTITLES] = ["audio", "subtitles"]


def _film():
	"""Components/HdsSubtitrariFilm.py (subtitrarile din fisierele de langa film), sau None."""
	try:
		from Components import HdsSubtitrariFilm
		return HdsSubtitrariFilm
	except ImportError:
		return None
	except Exception as e:
		print("[AudioSelection] Components/HdsSubtitrariFilm.py nu se poate incarca: %s" % e)
		return None


def _cautaSubtitrariInternet(session, **kwargs):
	"""Randul "Caută subtitrări pe internet" (0.3.2): descarcarea subtitrarilor e in imagine
	(Components/HdsSubtitrariInternet/ecrane.py), nu mai e pluginul separat cu descriptorul WHERE_AUDIOMENU. Se cheama ca
	un plugin (runPlugin: session=, servicelist=); modulul se incarca abia la apasare."""
	from Components.HdsSubtitrariInternet.ecrane import cautaPeInternet
	cautaPeInternet(session)


def _potrivireSubtitrare(session, **kwargs):
	"""Randul "Potrivirea subtitrării…" (subtitrarea de pe internet pe un canal TV sau o inregistrare): bara de potrivire
	deasupra imaginii (Components/HdsSubtitrariInternet/ecrane.py)."""
	from Components.HdsSubtitrariInternet.ecrane import potrivire
	potrivire(session)


def _tv():
	"""Components/HdsSubtitrariInternet/tv.py (subtitrarile de pe internet pe canale TV si inregistrari .ts), sau None."""
	try:
		from Components.HdsSubtitrariInternet import tv
		return tv
	except ImportError:
		return None
	except Exception as e:
		print("[AudioSelection] Components/HdsSubtitrariInternet/tv.py nu se poate incarca: %s" % e)
		return None


def _numeLimba(cod):
	"""Numele limbii unei subtitrari (tradus), din codul din lista serviciului („ron”, „ro”, „eng”)."""
	try:
		from Components import HdsPisteLimbi
		c = HdsPisteLimbi.limbaCanonica(cod)
		if c:
			return HdsPisteLimbi.numeLimba(c)
	except Exception:
		pass
	if cod in LanguageCodes:
		return LanguageCodes[cod][0]
	return cod


# codurile ISO 639 locale (qaa-qtz): de obicei versiunea originala a emisiunii; qad e descrierea audio
_COD_LOCAL = re.compile(r"^q[a-t][a-z]$")
# limba pistei de sunet cand nu e o limba: aceleasi etichete ca playerul din web (HdsWebControl/player.js, tv_web.py)
_SUNET_NEDEFINIT = frozenset(("", "und", "unk", "xxx", "---"))
_SUNET_DESCRIERE = frozenset(("qad", "nar"))
_SUNET_ORIGINAL = frozenset(("orig", "original", "originalton", "ov", "vo", "vos"))


def _limbaSunet(cod):
	"""Eticheta limbii unei piste de sunet, tradusa: numele limbii („Germană”, nu „German”), „Nedefinită” pentru und si
	codul gol, „Descriere audio” pentru qad / nar (si textul componentei care spune asta, „Audiodeskription”),
	„Limba originală” pentru qaa-qtz si „Originalton”, „Altă limbă” pentru mis."""
	c = (cod or "").strip()
	low = c.lower()
	if low in _SUNET_NEDEFINIT:
		return _("Nedefinită")
	if low in _SUNET_DESCRIERE:
		return _("Descriere audio")
	if low == "mis":
		return _("Altă limbă")
	if low in _SUNET_ORIGINAL or _COD_LOCAL.match(low):
		return _("Limba originală")
	try:
		from Components import HdsPisteLimbi
		if HdsPisteLimbi.esteDescriereAudio(c):
			return _("Descriere audio")
	except Exception:
		pass
	return _numeLimba(c)


# eticheta subtitrarii dupa tipul din lista serviciului (subtype_t, lib/service/servicemp3.h): textul din film e „Text”,
# un fisier are numele formatului; un tip necunoscut nu mai poate da o eroare de index
_ETICHETE_TIP = {1: "Text", 2: "SSA", 3: "ASS", 4: "SRT", 5: "VobSub", 6: "PGS", 7: "VTT", 8: "SUB", 9: "SUB",
	10: "MPL2", 11: "TMPlayer", 12: "SAMI"}
# numerele fisierelor de langa film in lista serviciului (Components/HdsSubtitrariFilm.py, INDEX_FISIER)
_PRIMUL_FISIER = 100
# randul de la sfarsitul listei subtitrarilor la un film: „Alege alt fișier…” (navigatorul de fisiere)
ALEGE_FISIER = "alege-fisier"
# pasii intarzierii: OK pe rand ii schimba (0,1 s -> 1 s -> 10 s); tastele 1 si 3 muta cu 1 s
_PASI_INTARZIERE = (100, 1000, 10000)


def _setariSunet():
	"""Components/HdsSetariSunet.py (intarzierea pistei pe canal), sau None."""
	try:
		from Components import HdsSetariSunet
		return HdsSetariSunet
	except Exception as e:
		print("[AudioSelection] Components/HdsSetariSunet.py nu se poate incarca: %s" % e)
		return None


def _downmixAcum(nume, rezerva):
	"""ce face acum driverul (Components/AVSwitch.downmixAcum), altfel valoarea randului"""
	try:
		from Components.AVSwitch import downmixAcum
		v = downmixAcum(nume)
	except Exception:
		v = None
	return rezerva if v is None else v


class _ConfigIntarziere(ConfigElement):
	"""Intarzierea subtitrarilor la filmul care merge (ms): stanga/dreapta o muta cu pasul ales, OK schimba pasul.
	Nu se salveaza in setari: se tine minte pe film (Components/HdsSubtitrariFilm.py)."""

	def __init__(self, ms, pas=100, maxim=600000):
		ConfigElement.__init__(self)
		self._value = int(ms)
		self.default = 0
		self.pas = pas if pas in _PASI_INTARZIERE else 100
		self.maxim = maxim
		self.save_disabled = True

	def handleKey(self, key):
		if key == KEY_LEFT:
			self.value = max(-self.maxim, self._value - self.pas)
		elif key == KEY_RIGHT:
			self.value = min(self.maxim, self._value + self.pas)

	def schimbaPasul(self):
		i = _PASI_INTARZIERE.index(self.pas) if self.pas in _PASI_INTARZIERE else 0
		self.pas = _PASI_INTARZIERE[(i + 1) % len(_PASI_INTARZIERE)]

	def getText(self):
		f = _film()
		if f is None:
			return "%d ms" % self._value
		return _("%s (pas %s)") % (f.textIntarziere(self._value), f.textIntarziere(self.pas).lstrip("+"))

	def getMulti(self, selected):
		return ("text", self.getText())

# HDSatelit: primul rand din lista subtitrarilor
# (tasta SUB) e „Fără subtitrări”, cu acelasi text ca pagina 3 si ca /piste in web. OK pe el opreste subtitrarea si tine
# minte alegerea pe canal (HdsPisteLimbi, ca alegerea „Fără subtitrări” din pagina 3). Randul are in locul tuplului
# acest semn, pe care getSubtitleList nu il da niciodata.
FARA_SUBTITRARI = "fara-subtitrari"
# cate pluginuri WHERE_AUDIOMENU primesc rand in ecran (randul "Caută subtitrări pe internet" al imaginii, din 0.3.2,
# nu e plugin si nu se numara)
_MAX_PLUGINURI = 3

class AudioSelection(Screen, ConfigListScreen):
	def __init__(self, session, infobar=None, page=PAGE_AUDIO):
		Screen.__init__(self, session)

		self["streams"] = List([])
		self["key_red"] = Boolean(False)
		self["key_green"] = Boolean(False)
		self["key_yellow"] = Boolean(True)
		self["key_blue"] = Boolean(False)
		
		ConfigListScreen.__init__(self, [])
		self.infobar = infobar or self.session.infobar

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evUpdatedInfo: self.__updatedInfo
			})
		self.cached_subtitle_checked = False
		self.__selected_subtitle = None
        
		self["actions"] = NumberActionMap(["ColorActions", "SetupActions", "DirectionActions"],
		{
			"red": self.keyRed,
			"green": self.keyGreen,
			"yellow": self.keyYellow,
			"blue": self.keyBlue,
			"ok": self.keyOk,
			"cancel": self.cancel,
			"up": self.keyUp,
			"down": self.keyDown,
			"1": self.keyNumberGlobal,
			"2": self.keyNumberGlobal,
			"3": self.keyNumberGlobal,
			"4": self.keyNumberGlobal,
			"5": self.keyNumberGlobal,
			"6": self.keyNumberGlobal,
			"7": self.keyNumberGlobal,
			"8": self.keyNumberGlobal,
			"9": self.keyNumberGlobal,
		}, -2)

		self.settings = ConfigSubsection()
		choicelist = [(PAGE_AUDIO,_("audio tracks")), (PAGE_SUBTITLES,_("Subtitles"))]
		self.settings.menupage = ConfigSelection(choices = choicelist, default=page)
		self.colorRows = {}
		self.pluginRow = None
		self.onLayoutFinish.append(self.__layoutFinished)

	def __layoutFinished(self):
		self["config"].instance.setSelectionEnable(False)
		self.focus = FOCUS_STREAMS
		self.settings.menupage.addNotifier(self.fillList)

	def fillList(self, arg=None):
		streams = []
		conflist = []
		selectedidx = 0
		# HDSatelit: tasta colorata -> randul ei (rosu AC3 downmix, verde canalul, galben meniul,
		# albastru pluginul), tinut minte cand se face lista; inainte era pozitia fixa 0-3, pe care randul DTS o muta
		self.colorRows = {}
		self.pluginRow = None
		self.randIntarziere = None

		if self.settings.menupage.getValue() == PAGE_AUDIO:
			self.setTitle(_("Select audio track"))
			service = self.session.nav.getCurrentService()
			self.audioTracks = audio = service and service.audioTracks()
			n = audio and audio.getNumberOfTracks() or 0
			if SystemInfo["CanDownmixAC3"]:
				self.settings.downmix = ConfigOnOff(default=_downmixAcum("ac3", config.av.downmix_ac3.value))
				self.settings.downmix.addNotifier(self.changeAC3Downmix, initial_call = False)
				self.colorRows[0] = len(conflist)
				conflist.append(getConfigListEntry(_("AC3 downmix"), self.settings.downmix))
				self["key_red"].setBoolean(True)

			# DTS downmix, ca in enigma2-ul mai nou, fara tasta colorata
			if SystemInfo.get("CanDownmixDTS"):
				self.settings.downmix_dts = ConfigOnOff(default=_downmixAcum("dts", config.av.downmix_dts.value))
				self.settings.downmix_dts.addNotifier(self.changeDTSDownmix, initial_call = False)
				conflist.append(getConfigListEntry(_("DTS downmix"), self.settings.downmix_dts))

			if n > 0:
				self.audioChannel = service.audioChannel()
				if self.audioChannel:
					choicelist = [("0",_("left")), ("1",_("stereo")), ("2", _("right"))]
					self.settings.channelmode = ConfigSelection(choices = choicelist, default = str(self.audioChannel.getCurrentChannel()))
					self.settings.channelmode.addNotifier(self.changeMode, initial_call = False)
					self.colorRows[1] = len(conflist)
					conflist.append(getConfigListEntry(_("Channel"), self.settings.channelmode))
					self["key_green"].setBoolean(True)
				else:
					conflist.append(('',))
					self["key_green"].setBoolean(False)
				# HDSatelit: intarzierea pistei de acum pe canalul de acum, adunata la cea a iesirii
				# (Components/HdsSetariSunet.py); numai cu placa care o primeste si pe un canal DVB
				s = _setariSunet() if SystemInfo.get("HdsSunetIntarziere") else None
				pista = s.intarzierePista() if s is not None else None
				if pista is not None:
					self.settings.hds_intarziere_pista = ConfigSelection(choices=s.alegeriPista(), default=str(pista["ms"]))
					self.settings.hds_intarziere_pista.addNotifier(self.changeIntarzierePista, initial_call=False)
					conflist.append(getConfigListEntry(_(s.ETICHETA_PISTA), self.settings.hds_intarziere_pista))
				selectedAudio = self.audioTracks.getCurrentTrack()
				for x in range(n):
					number = str(x + 1)
					i = audio.getTrackInfo(x)
					languages = i.getLanguage().split('/')
					description = i.getDescription() or _("<unknown>")
					selected = ""
					language = ""

					if selectedAudio == x:
						selected = _pistaActiva()
						selectedidx = x

					# HDSatelit: numele limbilor traduse, ca la subtitrari; codurile care nu sunt o limba cu eticheta lor
					language = " / ".join(_limbaSunet(lang) for lang in languages)

					streams.append((x, "", number, description, language, selected))

			else:
				streams = []
				conflist.append(('',))
				self["key_green"].setBoolean(False)

		elif self.settings.menupage.getValue() == PAGE_SUBTITLES:
			self.setTitle(_("Subtitle selection"))
			self["key_red"].setBoolean(False)
			self["key_green"].setBoolean(False)
			# la un film din fisier: intarzierea, codarea (fisier text) si cadrele pe secunda (MicroDVD), pe filmul acesta
			self.randIntarziere = None
			film = _film()
			stare = film.stare(self.session) if film is not None else {"film": False}
			self.laFilm = bool(stare["film"])
			if stare["film"]:
				self.settings.intarziere = _ConfigIntarziere(stare["intarziere_ms"], getattr(self, "pasIntarziere", 100))
				self.settings.intarziere.addNotifier(self.changeIntarziere, initial_call=False)
				self.randIntarziere = len(conflist)
				conflist.append(getConfigListEntry(_("Întârzierea subtitrării"), self.settings.intarziere))
				if stare["e_text"]:
					alegeri = []
					for cod, text in film.CODARI:
						if cod == film.CODARE_AUTO and stare["codare_gasita"]:
							alegeri.append((cod, "%s: %s" % (_(text), _(film.numeCodare(stare["codare_gasita"])))))
						else:
							alegeri.append((cod, _(text)))
					self.settings.codare = ConfigSelection(choices=alegeri, default=stare["codare"])
					self.settings.codare.addNotifier(self.changeCodare, initial_call=False)
					eticheta = _("Codarea (pare greșită)") if stare["mesaj"] else _("Codarea")
					conflist.append(getConfigListEntry(eticheta, self.settings.codare))
				if stare["e_microdvd"]:
					self.settings.fps = ConfigSelection(choices=[(c, _(t)) for c, t in film.FPS_ALEGERI], default=stare["fps"])
					self.settings.fps.addNotifier(self.changeFps, initial_call=False)
					conflist.append(getConfigListEntry(_("Cadre pe secundă"), self.settings.fps))
			# pe un canal TV cu imagine sau la o inregistrare .ts: cautarea pe internet (randul de jos) si, cu o subtitrare
			# de pe internet pornita, potrivirea ei (Components/HdsSubtitrariInternet/tv.py)
			self.laTv = False
			self.potrivireTv = False
			tv = _tv() if not stare["film"] else None
			if tv is not None:
				try:
					self.laTv = tv.peServiciuDvb()
					self.potrivireTv = self.laTv and tv.activ(self.session)
				except Exception as e:
					print("[AudioSelection] subtitrarea de pe internet: %s" % e)
			if self.potrivireTv:
				from Components.HdsSubtitrariInternet.ecrane import RandTv
				sesiune = self.session

				def _replica():
					st = tv.stare(sesiune)
					return "%s  %s" % (st.get("pozitie_text") or "", (st.get("replica") or "").replace("\n", " / ")[:28])
				self.settings.hds_replica = RandTv(_replica, lambda: tv.salt(sesiune, -1), lambda: tv.salt(sesiune, 1))
				conflist.append(getConfigListEntry(_("Replica: < dinainte, următoarea >"), self.settings.hds_replica))
				self.settings.hds_reclama = RandTv(lambda: _("ceasul stă") if tv.stare(sesiune).get("reclama") else _("ceasul merge"),
					lambda: tv.reclama(sesiune), lambda: tv.reclama(sesiune))
				conflist.append(getConfigListEntry(_("Reclamă"), self.settings.hds_reclama))
			if not stare["film"]:
				# canalele: randurile goale de sub pistele lor raman (asezarea de dinainte); la film setarile de mai sus
				while len(conflist) < 2:
					conflist.append(('',))

			if self.subtitlesEnabled():
				sel = self.infobar.selected_subtitle
			else:
				sel = None

			# primul rand: „Fără subtitrări” (vezi FARA_SUBTITRARI), pornit cand nu merge nicio subtitrare
			streams.append((FARA_SUBTITRARI, "", "", _("Fără subtitrări"), "", "" if sel else _pistaActiva()))
			idx = 1

			subtitlelist = self.getSubtitleList()

			if len(subtitlelist):
				for x in subtitlelist:
					number = str(x[1])
					description = "?"
					language = _("<unknown>")
					selected = ""

					if sel and _aceeasiSubtitrare(x, sel):
						selected = _pistaActiva()
						selectedidx = idx
					
					if x[4] and x[4] != "und":
						language = _numeLimba(x[4]) or language
					if len(x) > 5 and x[5]:
						language = _("%s, pentru surzi") % language

					if x[0] == 0:
						description = "DVB"
						number = "%x" % (x[1])

					elif x[0] == 1:
						description = "TTX"
						number = "%x%02x" % (x[3],x[2])

					elif x[0] == 2:
						description = _ETICHETE_TIP.get(x[2], _("<unknown>"))
						number = str(x[1] + 1)	# pista din film, numarata de la 1 (ca in web)
						if x[1] >= _PRIMUL_FISIER:
							# un fisier de langa film: formatul si numele scurt; fara numar (100, 101 nu spun nimic)
							number = ""
							if len(x) > 6 and x[6]:
								# numai partea care deosebeste fisierele („ro.forced.srt”), nu numele filmului
								description = "%s  %s" % (description, film.numeAfisat(x[6], stare.get("nume", ""),
									bool(x[4] and x[4] != "und")))

					streams.append((x, "", number, description, language, selected))
					idx += 1
			# fara subtitrari pe canal ramane numai randul „Fără subtitrări” (inainte lista era goala)
			if self.randIntarziere is not None:
				streams.append((ALEGE_FISIER, "", "", _("Alege alt fișier…"), "", ""))

		self.colorRows[2] = len(conflist)
		conflist.append(getConfigListEntry(_("Menu"), self.settings.menupage))

		from Components.PluginComponent import plugins
		from Plugins.Plugin import PluginDescriptor
		
		# pluginurile WHERE_AUDIOMENU: cate un rand fiecare (cel mult _MAX_PLUGINURI), tasta albastra pe primul. Un
		# descriptor poate spune pe ce pagina are sens (hdsPagina = "audio" / "subtitles") si ca merge numai la un film din
		# fisier (hdsNumaiFilm); fara aceste campuri apare peste tot, ca inainte. In playerul de filme (fara runPlugin in
		# bara) pluginul se cheama direct, cu sesiunea, ca InfoBarPlugins.runPlugin.
		self.pluginRows = {}
		pagina = self.settings.menupage.getValue()
		laFilm = getattr(self, "laFilm", False) if pagina == PAGE_SUBTITLES else False
		laTv = getattr(self, "laTv", False) if pagina == PAGE_SUBTITLES else False
		# 0.3.2: "Caută subtitrări pe internet" (descarcarea subtitrarilor, in imagine, nu plugin) e primul rand in locul
		# pluginurilor, numai pe pagina subtitrarilor, la un film din fisier, pe un canal TV cu imagine si la o inregistrare
		# .ts; tasta albastra pe el. Se cheama ca un plugin (runPlugin). Cu o subtitrare de pe internet pornita pe canal,
		# dupa el "Potrivirea subtitrării…" (bara de potrivire).
		if laFilm or laTv:
			self["key_blue"].setBoolean(True)
			self.colorRows[3] = self.pluginRow = len(conflist)
			self.pluginRows[len(conflist)] = _cautaSubtitrariInternet
			conflist.append(getConfigListEntry(_("Caută subtitrări pe internet"), ConfigNothing()))
		if laTv and getattr(self, "potrivireTv", False):
			self.pluginRows[len(conflist)] = _potrivireSubtitrare
			conflist.append(getConfigListEntry(_("Potrivirea subtitrării…"), ConfigNothing()))
		for p in plugins.getPlugins(where=PluginDescriptor.WHERE_AUDIOMENU)[:_MAX_PLUGINURI]:
			# descriptorul pluginului vechi HdsSubtitleDownloader, ramas pe un receptor care l-a pus din feed (opkg nu il
			# scoate singur), ar dubla randul de mai sus
			if (getattr(p, "path", None) or "").rstrip("/").endswith("/Extensions/HdsSubtitleDownloader"):
				continue
			if getattr(p, "hdsPagina", None) not in (None, pagina):
				continue
			if getattr(p, "hdsNumaiFilm", False) and not laFilm:
				continue
			if self.pluginRow is None:
				self["key_blue"].setBoolean(True)
				self.colorRows[3] = self.pluginRow = len(conflist)
			self.pluginRows[len(conflist)] = p
			conflist.append(getConfigListEntry(p.name, ConfigNothing()))
		if self.pluginRow is None:
			self["key_blue"].setBoolean(False)

		self["config"].list = conflist
		self["config"].l.setList(conflist)

		self["streams"].list = streams
		self["streams"].setIndex(selectedidx)

	def __updatedInfo(self):
		self.fillList()

	def getSubtitleList(self):
		s = self.infobar and self.infobar.getCurrentServiceSubtitle()
		l = s and s.getSubtitleList() or [ ]
		return l

	def subtitlesEnabled(self):
		return self.infobar.subtitles_enabled

	def enableSubtitle(self, subtitles):
		if subtitles and self.infobar.subtitles_enabled and _aceeasiSubtitrare(self.infobar.selected_subtitle, subtitles):
			return
		if subtitles or self.infobar.subtitles_enabled:
			self.infobar.subtitles_enabled = False
		self.infobar.selected_subtitle = subtitles
		if subtitles:
			self.infobar.subtitles_enabled = True

	def changeAC3Downmix(self, downmix):
		# pune valoarea, trece iesirea pe Manual daca era pe Automat, o singura scriere, salveaza (Components/AVSwitch.py)
		from Components.AVSwitch import setDownmix
		setDownmix("ac3", bool(downmix.getValue()))

	def changeDTSDownmix(self, downmix):
		from Components.AVSwitch import setDownmix
		setDownmix("dts", bool(downmix.getValue()))

	def hasConfigPart(self):
		"""randul curent are o setare (nu e un rand gol pus doar ca sa pastreze asezarea)"""
		current = self["config"].getCurrent()
		return current is not None and len(current) > 1

	def changeMode(self, mode):
		if mode is not None and self.audioChannel:
			self.audioChannel.selectChannel(int(mode.getValue()))
			_tineMinte("noteazaParteDeMana", self.session)

	def changeIntarzierePista(self, element):
		s = _setariSunet()
		if s is not None:
			s.seteazaIntarzierePista(int(element.value))

	def changeIntarziere(self, element):
		f = _film()
		if f is not None:
			reusit, ms = f.alegeIntarziere(ms=element.value)
			if not reusit:
				element._value = ms

	def changeCodare(self, element):
		f = _film()
		if f is not None:
			f.alegeCodare(element.value)

	def changeFps(self, element):
		f = _film()
		if f is not None:
			f.alegeFps(element.value)

	def _peIntarziere(self):
		return (self.focus == FOCUS_CONFIG and getattr(self, "randIntarziere", None) is not None and
			self["config"].getCurrentIndex() == self.randIntarziere)

	def alegeFisier(self):
		"""„Alege alt fișier…”: navigatorul de fisiere din dosarul filmului; fisierul ales intra in lista si porneste."""
		from Screens.HdsSubtitrariFilm import HdsAlegeSubtitrare
		dosar = None
		try:
			import os
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			dosar = os.path.dirname(ref.getPath()) if ref is not None else None
		except Exception:
			dosar = None
		self.session.openWithCallback(self.__fisierAles, HdsAlegeSubtitrare, dosar)

	def __fisierAles(self, ales=None):
		"""`ales`: (calea, numarul in lista serviciului) de la navigator, care a adaugat deja fisierul; None = inapoi."""
		f = _film()
		if not ales or f is None:
			return
		cale, numar = ales
		tuplu = f.tupluPentru(numar)
		if tuplu:
			self.enableSubtitle(tuplu)
			_tineMinte("noteazaSubtitrare", self.session, tuplu)
		self.close(0)

	def changeAudio(self, audio):
		track = int(audio)
		if isinstance(track, int):
			if self.session.nav.getCurrentService().audioTracks().getNumberOfTracks() > track:
				self.audioTracks.selectTrack(track)
				s = _setariSunet()
				if s is not None:
					s.laSchimbareaPistei()   # intarzierea pistei noi, dupa ce placa o porneste

	def keyLeft(self):
		if self.focus == FOCUS_CONFIG:
			if self.hasConfigPart():
				ConfigListScreen.keyLeft(self)
		elif self.focus == FOCUS_STREAMS:
			self["streams"].setIndex(0)

	def runPlugin(self, p):
		if hasattr(self.infobar, "runPlugin"):
			self.infobar.runPlugin(p)
		else:
			p(session=self.session)

	def keyRight(self, config = False):
		if config or self.focus == FOCUS_CONFIG:
			p = getattr(self, "pluginRows", {}).get(self["config"].getCurrentIndex())
			if p is not None:
				self.runPlugin(p)
			elif self.hasConfigPart():
				ConfigListScreen.keyRight(self)
		if self.focus == FOCUS_STREAMS and self["streams"].count() and config == False:
			self["streams"].setIndex(self["streams"].count()-1)

	def keyRed(self):
		if self["key_red"].getBoolean():
			self.colorkey(0)

	def keyGreen(self):
		if self["key_green"].getBoolean():
			self.colorkey(1)

	def keyYellow(self):
		if self["key_yellow"].getBoolean():
			self.colorkey(2)

	def keyBlue(self):
		if self["key_blue"].getBoolean():
			self.colorkey(3)

	def colorkey(self, idx):
		row = self.colorRows.get(idx)
		if row is None:
			return
		self["config"].setCurrentIndex(row)
		self.keyRight(True)

	def keyUp(self):
		if self.focus == FOCUS_CONFIG:
			self["config"].instance.moveSelection(self["config"].instance.moveUp)
		elif self.focus == FOCUS_STREAMS:
			if self["streams"].getIndex() == 0:
				self["config"].instance.setSelectionEnable(True)
				self["streams"].style = "notselected"
				self["config"].setCurrentIndex(len(self["config"].getList())-1)
				self.focus = FOCUS_CONFIG
			else:
				self["streams"].selectPrevious()

	def keyDown(self):
		if self.focus == FOCUS_CONFIG:
			if self["config"].getCurrentIndex() < len(self["config"].getList())-1:
				self["config"].instance.moveSelection(self["config"].instance.moveDown)
			else:
				self["config"].instance.setSelectionEnable(False)
				self["streams"].style = "default"
				self.focus = FOCUS_STREAMS
		elif self.focus == FOCUS_STREAMS:
			self["streams"].selectNext()

	def keyNumberGlobal(self, number):
		if self._peIntarziere() and number in (1, 3):
			# pe randul intarzierii: 1 = cu o secunda mai devreme, 3 = cu o secunda mai tarziu
			e = self.settings.intarziere
			e.value = max(-e.maxim, min(e.maxim, e.value + (1000 if number == 3 else -1000)))
			self["config"].invalidateCurrent()
			return
		# randul pe care scrie numarul apasat (pistele din film sunt numarate de la 1, dupa „Fără subtitrări”); fara un
		# asemenea rand (canalele: pid-uri in hexazecimal), randul al n-lea, ca inainte (1 = „Fără subtitrări”)
		randuri = self["streams"].list
		for i, rand in enumerate(randuri):
			if rand[2] == str(number):
				self["streams"].setIndex(i)
				self.keyOk()
				return
		if number <= len(randuri):
			self["streams"].setIndex(number - 1)
			self.keyOk()

	def keyOk(self):
		if self.focus == FOCUS_STREAMS and self["streams"].list:
			cur = self["streams"].getCurrent()
			if self.settings.menupage.getValue() == PAGE_AUDIO and cur[0] is not None:
				self.changeAudio(cur[0])
				_tineMinte("noteazaAudio", self.session, int(cur[0]))
				self.__updatedInfo()
			if self.settings.menupage.getValue() == PAGE_SUBTITLES and cur[0] == ALEGE_FISIER:
				self.alegeFisier()
				return
			if self.settings.menupage.getValue() == PAGE_SUBTITLES and cur[0] == FARA_SUBTITRARI:
				# „Fără subtitrări”: oprita si tinuta minte pe canal, si cand era deja oprita (ca pagina 3)
				self.enableSubtitle(None)
				_tineMinte("noteazaSubtitrare", self.session, None)
				self.__updatedInfo()
			elif self.settings.menupage.getValue() == PAGE_SUBTITLES and cur[0] is not None:
				if self.subtitlesEnabled() and _aceeasiSubtitrare(self.infobar.selected_subtitle, cur[0]):
					self.enableSubtitle(None)
					_tineMinte("noteazaSubtitrare", self.session, None)
					selectedidx = self["streams"].getIndex()
					self.__updatedInfo()
					self["streams"].setIndex(selectedidx)
				else:
					self.enableSubtitle(cur[0])
					_tineMinte("noteazaSubtitrare", self.session, cur[0])
					self.__updatedInfo()
			self.close(0)
		elif self._peIntarziere():
			self.settings.intarziere.schimbaPasul()
			self.pasIntarziere = self.settings.intarziere.pas
			self["config"].invalidateCurrent()
		elif self.focus == FOCUS_CONFIG:
			self.keyRight()

	def cancel(self):
		self.close(0)

class SubtitleSelection(AudioSelection):
	def __init__(self, session, infobar=None):
		AudioSelection.__init__(self, session, infobar, page=PAGE_SUBTITLES)
		self.skinName = ["AudioSelection"]
