# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# IptvSetup.py: televiziunea prin internet, pe televizor (Meniu > Setari > Surse Internet > IPTV). Ecranul arata listele si
# conturile omului, ca niste cartele cu stare (desenul: design-web-stitch/skin-pro/iptv); omul alege ce i-a dat furnizorul
# (playlist, cont, portal), scrie, iar canalele apar singure in lista de canale, la Sateliti, pe randul IPTV, fara repornire.
# Pagina web /iptv (HdsWebControl/internet_web.py) face acelasi lucru.
#
# Logica e in Components/HdsIptvSurse.py (sursele, buchetele), HdsIptvClient.py (serverul furnizorului) si HdsIptvLucru.py
# (firul de lucru): aici nu se atinge reteaua si nu se tine nicio parola mai mult decat dureaza scrisul ei. Parola nu se arata:
# randul ei incepe gol, iar la o sursa existenta gol inseamna 'ramane cum e'.
#
# Imaginea e numai un client. Nu ofera continut si nu trimite omul spre vreun furnizor.

import os
import time

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Button import Button
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.config import ConfigText, ConfigPassword, getConfigListEntry

from Components import HdsIptvSurse as I
from Components import HdsIptvClient as C
from Components import HdsIptvLucru as L
from Components import HdsIptvSeriale as S


def N_(text):
	return text


# ------------------------------------------------------------------ cartelele

_CULORI = {
	"fond": ("hdsPanelSolid", 0x10162A),
	"chenar": ("hdsTrack", 0x2A3350),
	"fond_ales": (None, 0x16234D),
	"chenar_ales": ("hdsBrand", 0x374EA1),
	"text": ("hdsText", 0xF2F4F8),
	"text_ales": ("hdsSelText", 0xFFFFFF),
	"mic": ("hdsText2", 0xC9D2E3),
	"sters": ("hdsLabel", 0xAEB9CC),
	"inchis": ("hdsPanelSolid", 0x10162A),
	"bine": ("hdsGood", 0x4FD18B),
	"atentie": ("hdsAmber", 0xF5B83D),
	"rau": ("hdsBad", 0xFF6B5E),
	"lucru": (None, 0x3B82F6),
	"alb": ("white", 0xFFFFFF),
}


def _culoare(nume, rezerva):
	if nume:
		try:
			from skin import colorNames
			return colorNames[nume].argb() & 0xFFFFFF
		except Exception:
			pass
	return rezerva


def _culori():
	return dict((k, _culoare(*v)) for k, v in _CULORI.items())


def _cartela(lat, inalt, gol, c, chenar, margine):
	"""Spatiul dintre cartele, chenarul si fondul (acelasi desen ca lista imaginilor de pe stick)."""
	from Components.MultiContent import MultiContentEntryText as T
	sus = inalt - gol
	return [
		T(pos=(0, sus), size=(lat + margine, gol), font=0, text="", backcolor=c["fond"], backcolor_sel=c["fond"]),
		T(pos=(lat, 0), size=(margine, sus), font=0, text="", backcolor=c["fond"], backcolor_sel=c["fond"]),
		T(pos=(0, 0), size=(lat, sus), font=0, text="", backcolor=c["chenar"], backcolor_sel=c["chenar_ales"]),
		T(pos=(chenar, chenar), size=(lat - 2 * chenar, sus - 2 * chenar), font=0, text="", backcolor=c["fond"],
			backcolor_sel=c["fond_ales"]),
	]


def _randCartela(cheie, titlu, detaliu, eticheta, culoare, lat, inalt, f, c, margine, pe_eticheta=None):
	"""Randul din lista: semnul in fata, titlul, randul mic si, la dreapta, eticheta starii (poate lipsi). `f`: scara fata de 1920."""
	from enigma import RT_HALIGN_CENTER, RT_HALIGN_LEFT, RT_VALIGN_CENTER
	from Components.MultiContent import MultiContentEntryText as T
	gol, chenar = int(14 * f), max(2, int(3 * f))
	sus = inalt - gol
	semn, x = int(30 * f), int(26 * f)
	xt = x + semn + int(26 * f)
	st = RT_HALIGN_LEFT | RT_VALIGN_CENTER
	rez = [cheie] + _cartela(lat, inalt, gol, c, chenar, margine)
	rez.append(T(pos=(x, (sus - semn) // 2), size=(semn, semn), font=0, text="", backcolor=culoare, backcolor_sel=culoare))
	xe = lat - int(26 * f)
	if eticheta:
		le = int(len(eticheta) * 19 * f) + int(44 * f)
		he = int(62 * f)
		xe = xe - le
		rez.append(T(pos=(xe, (sus - he) // 2), size=(le, he), font=2, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=eticheta,
			color=pe_eticheta or c["inchis"], color_sel=pe_eticheta or c["inchis"], backcolor=culoare, backcolor_sel=culoare))
	lt = max(10, xe - xt - int(20 * f))
	if detaliu:
		rez.append(T(pos=(xt, int(10 * f)), size=(lt, int(50 * f)), font=0, flags=st, text=titlu, color=c["text"],
			color_sel=c["text_ales"], backcolor=c["fond"], backcolor_sel=c["fond_ales"]))
		rez.append(T(pos=(xt, int(60 * f)), size=(lt, int(38 * f)), font=1, flags=st, text=detaliu, color=c["sters"],
			color_sel=c["mic"], backcolor=c["fond"], backcolor_sel=c["fond_ales"]))
	else:
		rez.append(T(pos=(xt, chenar), size=(lt, sus - 2 * chenar), font=0, flags=st, text=titlu, color=c["text"],
			color_sel=c["text_ales"], backcolor=c["fond"], backcolor_sel=c["fond_ales"]))
	return rez


def textCanale(n):
	try:
		from Components.HdsIndexCanale import text_numar
		return text_numar(n)
	except Exception:
		return str(n)


def textOra(ora):
	"""Cand s-a adus lista ultima oara: azi la 08:10 sau data."""
	if not ora:
		return ""
	t = time.localtime(ora)
	if time.strftime("%Y%m%d", t) == time.strftime("%Y%m%d"):
		return _("azi, %s") % time.strftime("%H:%M", t)
	return time.strftime("%d.%m.%Y", t)


def textExpirare(ora):
	try:
		return (_("Expiră la %s") % time.strftime("%d.%m.%Y", time.localtime(int(ora)))) if ora else ""
	except (TypeError, ValueError, OverflowError, OSError):
		return ""


def detaliuSursa(p):
	"""Randul mic al cartelei: felul, gazda, canalele si cand s-a adus lista; la o eroare, eroarea."""
	if p.get("eroare"):
		return _(p["eroare"])
	parti = [_(I.NUME_FEL.get(p["fel"], p["fel"]))]
	if p.get("gazda"):
		parti.append(p["gazda"])
	if p.get("canale"):
		parti.append(textCanale(p["canale"]))
	if p.get("ora"):
		parti.append(textOra(p["ora"]))
	if textExpirare(p.get("expira")):
		parti.append(textExpirare(p["expira"]))
	return u"  ·  ".join(parti)


def stareSursa(p, lucreaza):
	"""(eticheta, cheia culorii): ce se vede in dreapta cartelei."""
	if lucreaza:
		return _("Se încarcă"), "lucru"
	if p.get("eroare"):
		return _("Nu merge"), "rau"
	if not p.get("ora"):
		return _("Se încarcă"), "lucru"
	if p.get("fara_https"):
		return _("Fără HTTPS"), "atentie"
	return _("Merge"), "bine"


def mesajSursa(p):
	"""Propozitia intreaga despre cartela aleasa, in randul de sus (acolo textul lung se deruleaza)."""
	if p.get("eroare"):
		return _(p["eroare"])
	parti = []
	if p.get("fara_https"):
		parti.append(_(I.T_FARA_HTTPS))
	if p.get("taiate"):
		parti.append(_("Lista are prea multe canale: au intrat primele %d.") % I.MAX_CANALE)
	if p.get("sarite"):
		parti.append(_("Câteva rânduri din listă nu se pot folosi și au fost sărite: %d.") % p["sarite"])
	if textExpirare(p.get("expira")):
		parti.append(textExpirare(p["expira"]))
	if p.get("epg_stare") == "lucreaza":
		parti.append(_("Se încarcă ghidul TV..."))
	elif p.get("epg_mesaj"):
		parti.append(_(p["epg_mesaj"]))
		if p.get("epg_evenimente"):
			parti.append(_("%d programe.") % p["epg_evenimente"])
	return " ".join(parti) or _("Canalele apar în lista de canale, la Sateliți, pe rândul IPTV.")


class _EcranCartele(Screen):
	"""Lista de cartele, comuna celor doua ecrane: fonturile si marimile, din latimea listei din skin."""

	def _pregatesteLista(self):
		from enigma import getDesktop, gFont
		lista = self["lista"]
		try:
			import skin
			p = int(skin.getFontScalePercent())
		except Exception:
			p = 100
		scara = getDesktop(0).size().width() / 1920.0
		f = scara * p / 100.0
		self._inaltimeRand = int(123 * f)
		lista.l.setFont(0, gFont(skin.fontHds("Regular"), int(34 * f)))
		lista.l.setFont(1, gFont(skin.fontHds("Regular"), int(25 * f)))
		lista.l.setFont(2, gFont(skin.fontHds("Bold"), int(27 * f)))
		lista.l.setItemHeight(self._inaltimeRand)
		self._scaraRand = f
		self._margineRand = int(24 * scara)
		self._latimeRand = lista.instance.size().width() - self._margineRand
		self._culoriRand = _culori()


class IptvSetup(_EcranCartele):
	skin = """
	<screen name="IptvSetup" resolution="1920,1080" position="center,center" size="1500,800" title="IPTV">
		<widget name="ghid" position="30,20" size="1440,50" font="Regular;26" noWrap="1" valign="center" />
		<widget name="lista" position="30,80" size="1440,620" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="390,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" position="750,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget name="key_blue" position="1110,730" size="360,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle("IPTV")
		from enigma import eListboxPythonMultiContent, eTimer
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
		self["ghid"] = Label("")
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Adaugă"))
		self["key_yellow"] = Button(_("Actualizează"))
		self["key_blue"] = Button(_("Șterge"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "MenuActions"], {
			"cancel": self.close,
			"red": self.close,
			"ok": self._ok,
			"menu": self._meniuSursa,
			"green": self._adauga,
			"yellow": self._actualizeaza,
			"blue": self._sterge,
			"up": self._sus,
			"down": self._jos,
			"left": self._paginaSus,
			"right": self._paginaJos,
		}, -2)
		self._surse = []
		self._ceasStare = eTimer()
		self._ceasStare.callback.append(self._arata)
		self.onLayoutFinish.append(self._pregatesteLista)
		self.onLayoutFinish.append(self._arata)
		L.asculta(self._laRezultat)
		self.onClose.append(self._laInchidere)

	def _laInchidere(self):
		self._ceasStare.stop()
		L.nuAsculta(self._laRezultat)

	def _laRezultat(self, sursa_id, mesaj, schimbat):
		self._arata()

	def _arata(self):
		ales = self._aleasa()
		self._surse = I.citesteSursePublic()
		rand = []
		a = (self._latimeRand, self._inaltimeRand, self._scaraRand, self._culoriRand, self._margineRand)
		c = self._culoriRand
		index = 0
		for i, p in enumerate(self._surse):
			if ales and p["id"] == ales["id"]:
				index = i
			eticheta, culoare = stareSursa(p, L.inLucru(p["id"]))
			rand.append(_randCartela(p["id"], p["nume"] or _(I.NUME_FEL.get(p["fel"], "IPTV")), detaliuSursa(p), eticheta.upper(), c[culoare], *a,
				pe_eticheta=c["alb"] if culoare in ("lucru",) else c["inchis"]))
		rand.append(_randCartela("adauga", _("Adaugă o listă, un cont sau un portal"), "", "", c["chenar_ales"], *a))
		self["lista"].setList(rand)
		self["lista"].moveToIndex(index)
		self._ghid()
		if any(p.get("epg_stare") == "lucreaza" for p in self._surse):
			self._ceasStare.start(2000, True)
		else:
			self._ceasStare.stop()

	def _aleasa(self):
		"""Sursa de sub cursor, sau None pe randul 'Adaugă'."""
		i = self["lista"].getSelectionIndex() if self["lista"].instance is not None else 0
		return self._surse[i] if 0 <= i < len(self._surse) else None

	def _ghid(self):
		p = self._aleasa()
		if p is not None:
			if p["fel"] == "xtream":
				taste = _("OK: grupele. MENU: date de acces și seriale.")
			elif p["fel"] == "demo":
				taste = _("OK: despre lista demo.")
			else:
				taste = _("OK: grupele. MENU: date de acces.")
			self["ghid"].setText("%s %s: %s. %s" % (taste, p["nume"], detaliuSursa(p), mesajSursa(p)))
		elif self._surse:
			self["ghid"].setText(_("Canalele apar în lista de canale, la Sateliți, pe rândul IPTV."))
		else:
			self["ghid"].setText(_("Adaugă lista sau contul primit de la furnizorul tău. Canalele apar singure în lista de canale."))

	def _sus(self):
		self["lista"].up()
		self._ghid()

	def _jos(self):
		self["lista"].down()
		self._ghid()

	def _paginaSus(self):
		self["lista"].pageUp()
		self._ghid()

	def _paginaJos(self):
		self["lista"].pageDown()
		self._ghid()

	def _ok(self):
		p = self._aleasa()
		if p is None:
			self._adauga()
		elif p["fel"] == "demo":
			self.session.open(IptvDespre)
		else:
			self.session.openWithCallback(self._dupaFormular, IptvGrupe, p["id"])

	def _meniuSursa(self):
		p = self._aleasa()
		if p is None or p["fel"] == "demo":
			return
		from Screens.ChoiceBox import ChoiceBox
		actiuni = [(_("Date de acces"), "date")]
		if p["fel"] == "xtream":
			actiuni.append((_("Seriale"), "seriale"))
		self.session.openWithCallback(self._alegeCont, ChoiceBox, title=p["nume"], list=actiuni)

	def _alegeCont(self, ales=None):
		p = self._aleasa()
		if not ales or not p:
			return
		if ales[1] == "seriale":
			self.session.open(IptvSeriale, p["id"])
		else:
			self.session.openWithCallback(self._dupaFormular, IptvDateAcces, p["fel"], p["id"])

	def _adauga(self):
		if len(self._surse) >= I.MAX_SURSE:
			self["ghid"].setText(_(C.E_PREA_MULTE))
			return
		self.session.openWithCallback(self._alesFel, IptvAlege)

	def _alesFel(self, fel=None):
		if not fel:
			return
		if fel == "demo":
			self._demo()
		else:
			self.session.openWithCallback(self._dupaFormular, IptvDateAcces, fel)

	def _demo(self):
		"""Lista demo vine ca pachet din feedul imaginii; o pune firul de lucru, iar cartela arata cum merge."""
		L.adaugaSiCere(I.sursaDemo())
		self._arata()

	def _dupaFormular(self, *rezultat):
		self._arata()

	def _actualizeaza(self):
		p = self._aleasa()
		if p is None:
			L.cereToate()
		else:
			L.cere(p["id"])
		self._arata()

	def _sterge(self):
		p = self._aleasa()
		if p is None:
			return
		from Screens.MessageBox import MessageBox
		self.session.openWithCallback(lambda da, i=p["id"]: self._stergeDa(i, da), MessageBox,
			_("Ștergi %s? Canalele ei dispar de la rândul IPTV. Cele puse de tine în Favorite rămân, dar nu mai pornesc.") % (p["nume"] or _(I.NUME_FEL.get(p["fel"], "IPTV"))),
			MessageBox.TYPE_YESNO, default=False)

	def _stergeDa(self, sursa_id, da):
		if da and L.stergeSiReface(sursa_id):
			self._arata()


def textRandGrupa(r):
	"""Randul din lista grupelor: numele, cate grupe are o tara, cate canale."""
	parti = [r["nume"]]
	if r.get("grupe"):
		parti.append(_(I.T_GRUPE_N) % r["grupe"])
	parti.append(textCanale(r["canale"]))
	if r.get("partial"):
		parti.append(_(I.T_GRUPE_PARTE))
	return u"  ·  ".join(parti)


class IptvGrupe(Screen):
	"""Ce grupe si tari se vad din lista unei surse: o lista cu bife. OK schimba bifa; la iesire se aplica singur."""
	skin = """
	<screen name="IptvGrupe" resolution="1920,1080" position="center,center" size="1500,800" title="Grupele">
		<widget name="ghid" position="30,20" size="1440,50" font="Regular;26" noWrap="1" valign="center" />
		<widget name="lista" position="30,80" size="1440,620" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="390,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" position="750,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
	</screen>
	"""

	def __init__(self, session, sursa_id):
		Screen.__init__(self, session)
		self.setTitle(_("Grupele"))
		from Components.SelectionList import SelectionList
		self.sursa_id = sursa_id
		s = I.sursa(sursa_id) or {"id": sursa_id}
		self.catalog = I.citesteCatalog(s)
		self.ascunse = set(s.get("ascunse") or ())
		self.taiate = int(s.get("taiate") or 0)
		self.canale = int(s.get("canale") or 0)
		self["lista"] = SelectionList([])
		self["ghid"] = Label("")
		self["key_red"] = Button(_("Ascunde tot"))
		self["key_green"] = Button(_("Arată tot"))
		self["key_yellow"] = Button(_("Caută"))
		self.cauta = ""
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"cancel": self._iesi,
			"ok": self._ok,
			"red": self._ascundeTot,
			"green": self._arataTot,
			"yellow": self._cauta,
			"up": self["lista"].up,
			"down": self["lista"].down,
			"left": self["lista"].pageUp,
			"right": self["lista"].pageDown,
		}, -2)
		self.onLayoutFinish.append(self._arata)

	def _arata(self):
		lista = self["lista"]
		index = lista.getSelectionIndex() if lista.instance is not None else 0
		from Components.SelectionList import SelectionEntryComponent
		randuri = I.randuriGrupe({"id": self.sursa_id, "ascunse": sorted(self.ascunse), "grupe_lista": [[None, g[0], g[1]] for g in self.catalog]})
		if self.cauta:
			randuri = [r for r in randuri if self.cauta.lower() in r["nume"].lower()]
		lista.list = [SelectionEntryComponent(textRandGrupa(r), r["cheie"], i, r["vizibil"]) for i, r in enumerate(randuri)]
		lista.setList(lista.list)
		if lista.list:
			lista.moveToIndex(min(index, len(lista.list) - 1))
		if self.cauta:
			self["ghid"].setText(_("Caut: %s. EXIT arată iar toată lista.") % self.cauta)
		elif self.taiate:
			self["ghid"].setText(_(I.T_GRUPE_TAIATE) % {"vazute": self.canale, "toate": self.canale + self.taiate})
		else:
			self["ghid"].setText(_(I.T_GRUPE_GHID))

	def _ok(self):
		curent = self["lista"].getCurrent()
		if curent:
			self.ascunse = I.comutaGrupa(self.ascunse, self.catalog, curent[0][1])
			self._arata()

	def _ascundeTot(self):
		self.ascunse = I.ascundeTot(self.catalog)
		self._arata()

	def _arataTot(self):
		self.ascunse = set()
		self._arata()

	def _cauta(self):
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(self._dupaCautare, VirtualKeyBoard, title=_("Caută o grupă sau o țară"), text=self.cauta)

	def _dupaCautare(self, text=None):
		if text is not None:
			self.cauta = text.strip()
			self["lista"].moveToIndex(0)
			self._arata()

	def _iesi(self):
		if self.cauta:
			self.cauta = ""
			self._arata()
			return
		L.aplicaAscunse(self.sursa_id, self.ascunse)
		self.close()


class IptvAlege(_EcranCartele):
	"""Ce i-a dat furnizorul: playlist, cont sau portal; plus lista demo."""
	skin = """
	<screen name="IptvAlege" resolution="1920,1080" position="center,center" size="1500,800" title="Adaugă">
		<widget name="ghid" position="30,20" size="1440,50" font="Regular;26" noWrap="1" valign="center" />
		<widget name="lista" position="30,80" size="1440,620" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="390,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	FELURI = (
		("m3u", "Playlist", "O adresă de internet sau un fișier de pe stick."),
		("xtream", "Cont", "Server, utilizator și parolă."),
		("stalker", "Portal", "Adresa portalului și adresa MAC."),
		("demo", "Listă demo", "Canale gratuite care permit asta, cu acordul lor la vedere."),
	)

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Adaugă"))
		from enigma import eListboxPythonMultiContent
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
		self["ghid"] = Label(_("Alege ce ți-a dat furnizorul."))
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Alege"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"red": self.close,
			"ok": self._ok,
			"green": self._ok,
		}, -2)
		self.onLayoutFinish.append(self._pregatesteLista)
		self.onLayoutFinish.append(self._arata)

	def _arata(self):
		a = (self._latimeRand, self._inaltimeRand, self._scaraRand, self._culoriRand, self._margineRand)
		c = self._culoriRand
		self["lista"].setList([_randCartela(fel, _(titlu), _(detaliu), "", c["chenar_ales"] if fel != "demo" else c["sters"], *a)
			for fel, titlu, detaliu in self.FELURI])

	def _ok(self):
		i = self["lista"].getSelectionIndex()
		if 0 <= i < len(self.FELURI):
			self.close(self.FELURI[i][0])


class _ParolaNoua(ConfigPassword):
	"""Parola scrisa acum pe televizor: se vede in clar (ConfigPassword cu `scrisa`); goala, randul ramane gol (un rand
	gol lasa parola salvata cum e, deci "nepusă" ar spune altceva)."""

	def getMulti(self, selected):
		if not self.text:
			return ("text", "")
		return ConfigPassword.getMulti(self, selected)


# randurile fiecarui fel: (cheia sursei, numele randului, e parola)
_RANDURI = {
	"m3u": (("adresa", "Adresa listei", False), ("nume", "Nume (opțional)", False)),
	"xtream": (("server", "Server", False), ("utilizator", "Utilizator", False), ("parola", "Parolă", True), ("nume", "Nume (opțional)", False)),
	"stalker": (("portal", "Adresa portalului", False), ("mac", "Adresa MAC", False), ("nume", "Nume (opțional)", False)),
}
_TITLURI = {"m3u": "Playlist", "xtream": "Cont", "stalker": "Portal"}
_GHID = {
	"m3u": "Scrie adresa listei sau alege fișierul de pe stick cu tasta galbenă. OK deschide tastatura.",
	"xtream": "Scrie datele primite de la furnizor. OK deschide tastatura.",
	"stalker": "Scrie adresa portalului și adresa MAC primite de la furnizor. OK deschide tastatura.",
}


T_SE_VERIFICA = N_("Se verifică legătura cu serverul...")
_ANTETE = (("user_agent", N_("Agent utilizator (opțional)"), False), ("referer", N_("Referer (opțional)"), False))


class IptvDateAcces(Screen, ConfigListScreen):
	"""Formularul unei surse: un rand pe camp, OK deschide tastatura, Verde verifica si salveaza. Cat se verifica, ecranul asteapta;
	daca serverul refuza, omul vede de ce si poate schimba pe loc. O sursa noua care nu merge nu ramane in lista."""
	skin = """
	<screen name="IptvDateAcces" resolution="1920,1080" position="center,center" size="1500,800" title="Date de acces">
		<widget name="config" position="30,30" size="1440,420" font="Regular;30" secondfont="Regular;28" itemHeight="64" scrollbarMode="showOnDemand" />
		<widget source="ghid" render="Label" position="30,470" size="1440,50" font="Regular;26" noWrap="1" valign="center" />
		<widget name="stare" position="30,530" size="1440,170" font="Regular;28" valign="top" />
		<widget source="key_red" render="Label" position="30,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="390,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" conditional="key_yellow" position="750,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
	</screen>
	"""

	def __init__(self, session, fel="m3u", sursa_id=None):
		Screen.__init__(self, session)
		# fara sesiune: fara fereastra de ajutor a tastelor cu cifre, care ar sta pe marginea ecranului; textul se scrie cu tastatura (OK)
		ConfigListScreen.__init__(self, [], session=None)
		self.fel = fel
		self.sursa_id = sursa_id
		self.astept = None
		self.setTitle(_(_TITLURI.get(fel, "IPTV")))
		vechi = I.sursa(sursa_id) if sursa_id else None
		self.vechi = vechi or {}
		self["ghid"] = StaticText(_(_GHID.get(fel, "")))
		self["stare"] = Label("")
		self["key_red"] = StaticText(_("Renunță"))
		self["key_green"] = StaticText(_("Salvează"))
		if fel == "m3u":
			self["key_yellow"] = Label(_("De pe stick"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"red": self.close,
			"green": self.salveaza,
			"yellow": self.galben,
		}, -2)
		self.campuri = {}
		lista = []
		for cheie, nume, e_parola in _RANDURI.get(fel, ()) + _ANTETE:
			if e_parola:
				el = _ParolaNoua(default="", fixed_size=False)
			else:
				el = ConfigText(default=self.vechi.get(cheie) or "", fixed_size=False)
			self.campuri[cheie] = el
			lista.append(getConfigListEntry(_(nume), el))
		self.list = lista
		self["config"].list = self.list
		if vechi and fel == "xtream":
			self["stare"].setText(_("Parola nu se arată. Un rând gol o lasă cum e."))
		self["ghid"].setText(_(_GHID.get(fel, "")) + " " + _("Agent utilizator și Referer: goale folosesc valorile implicite."))
		L.asculta(self._laRezultat)
		self.onClose.append(self._laInchidere)

	def _laInchidere(self):
		L.nuAsculta(self._laRezultat)

	def keyOK(self):
		x = self["config"].getCurrent()
		if not x or self.astept:
			return
		el = x[1]
		e_parola = isinstance(el, ConfigPassword)

		def gata(text, el=el, rand=x):
			if text is None:
				return
			el.value = text if e_parola else text.strip()
			if e_parola:
				el.scrisa = True
			self["config"].invalidate(rand)
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(gata, VirtualKeyBoard, title=x[0], text="" if e_parola else el.value,
			hdsSecret=e_parola)

	def galben(self):
		if self.fel != "m3u" or self.astept:
			return
		from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleFisier
		self.session.openWithCallback(self._fisierAles, HdsEditorCanaleFisier, "import")

	def _fisierAles(self, ales=None):
		if not ales or ales[0] != "fisier":
			return
		if I.adresaListaBuna(ales[1]) is None:
			self["stare"].setText(_("Alege un fișier .m3u sau .m3u8 de pe stick."))
			return
		self.campuri["adresa"].value = ales[1]
		if not self.campuri["nume"].value:
			self.campuri["nume"].value = os.path.splitext(os.path.basename(ales[1]))[0]
		self["config"].invalidateCurrent()
		self["config"].list = self.list
		self.salveaza()

	def _date(self):
		date = dict((k, el.value) for k, el in self.campuri.items())
		if self.fel == "xtream" and not date.get("parola"):
			date["parola"] = self.vechi.get("parola") or ""
		return date

	def salveaza(self):
		if self.astept:
			return
		sursa, eroare = C.verificaDate(self.fel, self._date())
		if eroare:
			self["stare"].setText(_(eroare))
			return
		self.astept = sursa["id"]
		if L.adaugaSiCere(sursa) is None:
			self.astept = None
			self["stare"].setText(_(C.E_PREA_MULTE))
			return
		if self.sursa_id and self.sursa_id != sursa["id"]:
			# altă adresă sau alt utilizator: e altă sursă, iar cea veche pleacă
			L.stergeSiReface(self.sursa_id)
			self.sursa_id = None
		self["stare"].setText(_(T_SE_VERIFICA))

	def _laRezultat(self, sursa_id, mesaj, schimbat):
		if sursa_id != self.astept:
			return
		self.astept = None
		if mesaj:
			self["stare"].setText(_(mesaj))
			return
		s = I.sursa(sursa_id) or {}
		from Screens.MessageBox import MessageBox
		text = _("Gata: %s. Le găsești în lista de canale, la Sateliți, pe rândul IPTV.") % textCanale(int(s.get("canale") or 0))
		if s.get("fara_https"):
			text += "\n" + _(I.T_FARA_HTTPS)
		self.session.openWithCallback(lambda *a: self.close(True), MessageBox, text, MessageBox.TYPE_INFO, timeout=8)


class IptvSeriale(_EcranCartele):
	"""Serial, sezon, episod; numai pagini de cate 50, reteaua pe fir separat."""
	skin = """
	<screen name="IptvSeriale" resolution="1920,1080" position="center,center" size="1500,800" title="Seriale">
		<widget name="ghid" position="30,20" size="1440,50" font="Regular;26" noWrap="1" valign="center" />
		<widget name="lista" position="30,80" size="1440,620" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,730" size="340,50" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" />
		<widget name="key_green" position="390,730" size="340,50" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" />
		<widget name="key_yellow" position="750,730" size="340,50" font="Regular;24" halign="center" valign="center" backgroundColor="#a08000" />
		<widget name="key_blue" position="1110,730" size="360,50" font="Regular;24" halign="center" valign="center" backgroundColor="#18188b" />
	</screen>
	"""

	def __init__(self, session, sursa_id):
		Screen.__init__(self, session)
		from enigma import eListboxPythonMultiContent, eTimer
		self.sursa_id = sursa_id
		self.serial, self.sezon, self.pagina, self.cautare = "", "", 0, ""
		self._drum, self._randuri, self._date, self._cheie = [], [], {}, None
		self.setTitle(_("Seriale"))
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
		self["ghid"] = Label("")
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Alege"))
		self["key_yellow"] = Button(_("Caută"))
		self["key_blue"] = Button(_("Pagina următoare"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "InfobarEPGActions"], {
			"cancel": self._inapoi, "red": self._inapoi, "ok": self._ok, "green": self._ok,
			"yellow": self._galben, "blue": self._urmatoarea, "left": self._precedenta, "right": self._urmatoarea,
			"up": self._sus, "down": self._jos, "showEventInfo": self._descriere,
		}, -2)
		self._ceas = eTimer()
		self._ceas.callback.append(self._rezultat)
		self.onLayoutFinish.append(self._pregatesteLista)
		self.onLayoutFinish.append(self._cere)
		self.onClose.append(self._inchide)

	def _inchide(self):
		self._ceas.stop()
		self._cheie = None

	def _cere(self):
		self._randuri, self._date = [], {}
		self["lista"].setList([])
		self["ghid"].setText(_("Se încarcă..."))
		self._cheie = S.cere(self.sursa_id, self.serial, self.sezon, self.pagina, self.cautare)
		if not self._cheie:
			self["ghid"].setText(_(S.E_OCUPAT))
			return
		self._ceas.start(400, False)
		self._rezultat()

	def _rezultat(self):
		if not self._cheie:
			return
		rez = S.rezultat(self._cheie)
		if rez.get("lucreaza"):
			return
		self._ceas.stop()
		if not rez.get("result"):
			self["ghid"].setText(_(rez.get("message") or S.E_DATE))
			return
		self._date, self._randuri = rez, rez.get("randuri", [])
		self.setTitle((rez.get("titlu") or _("Seriale")) + " · " + _("Pagina %d") % (self.pagina + 1))
		self["key_green"].setText(_("Redă pe televizor") if self.sezon else _("Alege"))
		self["key_yellow"].setText(_("Descriere") if self.serial else _("Caută"))
		self["key_blue"].setText(_("Pagina următoare") if rez.get("altele") else "")
		a = (self._latimeRand, self._inaltimeRand, self._scaraRand, self._culoriRand, self._margineRand)
		c = self._culoriRand
		self["lista"].setList([_randCartela(r["id"], self._nume(r), r.get("durata") or r.get("descriere") or "", "",
			c["chenar_ales"], *a) for r in self._randuri])
		self._ghid()

	def _nume(self, rand):
		if not self.serial:
			return rand["nume"]
		if not self.sezon:
			return _("Sezonul %s") % rand["numar"]
		return ((_('Episodul %s') % rand["numar"]) + ": " if rand.get("numar") else "") + rand["nume"]

	def _aleasa(self):
		i = self["lista"].getSelectionIndex()
		return self._randuri[i] if 0 <= i < len(self._randuri) else None

	def _ghid(self):
		r = self._aleasa()
		text = (self._nume(r) + ". " + (r.get("descriere") or self._date.get("descriere") or "")) if r else _("Niciun rezultat.")
		if self._date.get("message"):
			text += " " + _(self._date["message"])
		self["ghid"].setText(text)

	def _sus(self):
		self["lista"].up()
		self._ghid()

	def _jos(self):
		self["lista"].down()
		self._ghid()

	def _ok(self):
		rand = self._aleasa()
		if not rand:
			return
		if self.sezon:
			ref = S.episodDinPagina(self._cheie, rand["cheie"])
			if ref:
				try:
					from enigma import eServiceReference
					serviciu = eServiceReference(ref)
					serviciu.setName(rand["nume"])
					self.session.nav.playService(serviciu)
					self.close()
				except Exception:
					self["ghid"].setText(_("Episodul nu a pornit. Încearcă din nou."))
			else:
				self["ghid"].setText(_(S.E_EXPIRAT))
			return
		self._drum.append((self.serial, self.sezon, self.pagina, self.cautare))
		if self.serial:
			self.sezon = rand["id"]
		else:
			self.serial = rand["id"]
		self.pagina = 0
		self._cere()

	def _inapoi(self):
		if self._drum:
			self.serial, self.sezon, self.pagina, self.cautare = self._drum.pop()
			self._cere()
		else:
			self.close()

	def _urmatoarea(self):
		if self._date.get("altele"):
			self.pagina += 1
			self._cere()

	def _precedenta(self):
		if self.pagina:
			self.pagina -= 1
			self._cere()

	def _galben(self):
		if self.serial:
			self._descriere()
		else:
			from Screens.VirtualKeyBoard import VirtualKeyBoard
			self.session.openWithCallback(self._cauta, VirtualKeyBoard, title=_("Caută seriale"), text=self.cautare)

	def _cauta(self, text=None):
		if text is not None:
			self.cautare, self.pagina = text.strip()[:80], 0
			self._cere()

	def _descriere(self):
		rand = self._aleasa()
		if rand:
			self.session.open(IptvTextSerial, self._nume(rand), rand.get("descriere") or self._date.get("descriere") or _("Nu există descriere."))


class IptvTextSerial(Screen):
	skin = """
	<screen name="IptvTextSerial" resolution="1920,1080" position="center,center" size="1500,800" title="Descriere">
		<widget name="text" position="30,20" size="1440,690" font="Regular;28" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,730" size="340,50" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" />
	</screen>
	"""

	def __init__(self, session, titlu, text):
		Screen.__init__(self, session)
		from Components.ScrollLabel import ScrollLabel
		self.setTitle(titlu)
		self["text"] = ScrollLabel(titlu + "\n\n" + text)
		self["key_red"] = Button(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"cancel": self.close, "red": self.close, "ok": self.close, "up": self["text"].pageUp,
			"down": self["text"].pageDown, "left": self["text"].pageUp, "right": self["text"].pageDown,
		}, -2)


class IptvDespre(Screen):
	"""Lista demo: fiecare canal cu pagina lui oficiala si citatul din care reiese ca permite redarea."""
	skin = """
	<screen name="IptvDespre" resolution="1920,1080" position="center,center" size="1500,800" title="Listă demo">
		<widget name="text" position="30,20" size="1440,690" font="Regular;28" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		from Components.ScrollLabel import ScrollLabel
		self.setTitle(_("Listă demo"))
		self["text"] = ScrollLabel(textDemo())
		self["key_red"] = Button(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
			"up": self["text"].pageUp,
			"down": self["text"].pageDown,
			"left": self["text"].pageUp,
			"right": self["text"].pageDown,
		}, -2)


def textDemo():
	date = C.citesteDemo() or {}
	randuri = []
	for g in date.get("grupe") or ():
		if isinstance(g, dict):
			randuri.append(I.numeCurat(g.get("nume")))
			for c in g.get("canale") or ():
				if isinstance(c, dict):
					randuri.append("")
					randuri.append(I.numeCurat(c.get("nume")))
					for k in ("citat", "atribuire", "pagina"):
						if c.get(k):
							randuri.append(str(c[k]))
	return "\n".join(randuri)
