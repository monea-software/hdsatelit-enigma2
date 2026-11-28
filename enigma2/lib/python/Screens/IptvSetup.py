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
from Components.config import ConfigText, ConfigPassword, ConfigSelection, ConfigYesNo, getConfigListEntry

from Components import HdsIptvSurse as I
from Components import HdsIptvClient as C
from Components import HdsIptvLucru as L
from Components import HdsVod as V


def N_(text):
	return text


def _transferInFir(ecran, lucru, gata):
	"""Fisierele mari nu tin firul interfetei; inchiderea opreste callbackul."""
	import threading
	from enigma import eTimer
	if getattr(ecran, '_transferOcupat', False):
		return
	ecran._transferOcupat = True
	stare = {'inchis': False, 'gata': False}
	ceas = eTimer()
	def inchide():
		stare['inchis'] = True
		ceas.stop()
	def verifica():
		if not stare['gata']:
			return
		ceas.stop()
		ecran._transferOcupat = False
		if not stare['inchis']:
			gata(stare['rezultat'])
	def fir():
		try:
			stare['rezultat'] = lucru()
		except Exception:
			stare['rezultat'] = None
		stare['gata'] = True
	ceas.callback.append(verifica)
	ecran.onClose.append(inchide)
	ceas.start(100, False)
	threading.Thread(target=fir, name='IptvTransfer', daemon=True).start()


# 0.7.7 (FLM2, Eduard 16.11 11:01): aplicatia IPTV are pe loc tot ce da sursa: OK deschide pagina ei (IptvCont), cu Canale TV,
# Filme si Seriale; bifele grupelor din lista de canale trec in MENU
T_OK_SURSA = N_("OK: canalele, filmele și serialele. MENU: date de acces și grupele.")
T_CANALE_TV = N_("Canale TV")
T_FILME = N_("Filme")
T_SERIALE = N_("Seriale")


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
	parti.extend(p[k] for k in ("adresa", "server", "portal", "utilizator", "parola") if p.get(k))
	if p.get("mac"):
		parti.append(_("Adresa MAC") + ": " + p["mac"])
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
	if p.get("neconectata"):
		return _(I.T_NECONECTATA), "atentie"
	if p.get("eroare"):
		return _("Nu merge"), "rau"
	if not p.get("ora"):
		return _("Se încarcă"), "lucru"
	# 0.7.7 (IPX, e-mailurile 6514 si 6520): fara HTTPS sursa tot merge (pana in 0.7.6 eticheta galbena "Fără HTTPS" statea in locul
	# lui "Merge"); propozitia despre HTTPS ramane in randul de sus (mesajSursa). Nu si in randul mic al cartelei: acolo ar taia
	# expirarea (masurat cu HdsRegular 25 px: 1156 px pe 1149 in romana, 1210 pe 1073 in turca)
	return _("Merge"), "bine"


def mesajSursa(p):
	"""Propozitia intreaga despre cartela aleasa, in randul de sus (acolo textul lung se deruleaza)."""
	if p.get("eroare"):
		return _(p["eroare"])
	parti = []
	if p.get("fara_https"):
		parti.append(_(I.T_FARA_HTTPS))
	if p.get("taiate"):
		# 0.7.7 (BQT, Ozgur e-mailul 6514): exact ce a intrat, canalele TV si filmele separat (acelasi text in web)
		parti.append(C.textTaiate(p, _))
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
		# 0.7.5 (IPI): starea contului Xtream, ceruta pe un fir numai cat ecranul e deschis (config.usage.hds_iptv_cont)
		self._conturi = {}
		self._ceasCont = eTimer()
		self._ceasCont.callback.append(self._ghid)
		self.onLayoutFinish.append(self._pregatesteLista)
		self.onLayoutFinish.append(self._arata)
		L.asculta(self._laRezultat)
		self.onClose.append(self._laInchidere)

	def _laInchidere(self):
		self._ceasStare.stop()
		self._ceasCont.stop()
		L.nuAsculta(self._laRezultat)

	def _stareCont(self, p):
		"""Starea contului sursei alese: din memoria ecranului, altfel cerere pe un fir (o data pe deschidere). -> dict sau None."""
		if p is None or p.get("fel") != "xtream" or p.get("neconectata"):
			return None
		sid = p["id"]
		if sid in self._conturi:
			return self._conturi[sid]
		self._conturi[sid] = None
		s = I.sursa(sid)
		if s is None or s.get("neconectata"):
			return None
		import threading

		def lucru():
			rez = False             # False = cerut, nu se stie (serverul nu raspunde, functia oprita); None = inca se asteapta
			try:
				rez = C.stareContXtream(s) or False
			except Exception as e:
				print("[IptvSetup] starea contului: %s" % type(e).__name__)
			self._conturi[sid] = rez
		threading.Thread(target=lucru, name="IptvStareCont", daemon=True).start()
		self._ceasCont.start(700, True)
		return None

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
		# space71 (19.11.2026): preluarea automata a listelor M3U gasite si cererile in asteptare (IptvPreluare)
		rand.append(_randCartela("liste_m3u", _("Liste M3U găsite"), "", "", c["chenar_ales"], *a))
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

	def _peListeM3u(self):
		"""Cursorul pe randul listelor M3U gasite (cel de dupa randul de adaugare)."""
		try:
			lista = self["lista"]
			return lista.instance is not None and lista.getSelectionIndex() == len(self._surse) + 1
		except (KeyError, TypeError, AttributeError):
			return False

	def _ghid(self):
		if self._peListeM3u():
			self["ghid"].setText(_("OK: alegi dacă listele M3U găsite intră singure în IPTV."))
			return
		p = self._aleasa()
		if p is not None:
			if p["fel"] == "demo":
				taste = _("OK: despre lista demo.")
			else:
				taste = _(T_OK_SURSA)
			cont = self._stareCont(p)
			text_cont = C.textStareCont(cont) if cont else ""
			if text_cont:
				# starea contului spune ea data expirarii: nu de doua ori
				self["ghid"].setText("%s %s: %s. %s %s" % (taste, p["nume"], detaliuSursa(dict(p, expira=0)), text_cont,
					mesajSursa(dict(p, expira=0))))
			else:
				self["ghid"].setText("%s %s: %s. %s" % (taste, p["nume"], detaliuSursa(p), mesajSursa(p)))
			if p.get("fel") == "xtream" and self._conturi.get(p["id"], 0) is None and self._ceasCont is not None:
				self._ceasCont.start(700, True)
		elif self._surse:
			self["ghid"].setText(_("MENU: importă sau exportă surse IPTV.") + " " + _("Canalele apar în lista de canale, la Sateliți, pe rândul IPTV."))
		else:
			self["ghid"].setText(_("MENU: importă sau exportă surse IPTV.") + " " + _("Adaugă lista sau contul primit de la furnizorul tău. Canalele apar singure în lista de canale."))

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
		if p is None and self._peListeM3u():
			self.session.openWithCallback(self._dupaFormular, IptvPreluare)
		elif p is None:
			self._adauga()
		elif p["fel"] == "demo":
			self.session.open(IptvDespre)
		else:
			# 0.7.7 (FLM2): pagina sursei, cu tot ce da ea (canale, filme, seriale); un canal pornit de acolo inchide si meniurile
			self.session.openWithCallback(self._dupaCont, IptvCont, p["id"])

	def _dupaCont(self, inchide=False):
		if inchide:
			self.close(True)
		else:
			self._arata()

	def _meniuSursa(self):
		p = self._aleasa()
		from Screens.ChoiceBox import ChoiceBox
		actiuni = []
		if p is not None and p["fel"] != "demo":
			actiuni = [(_("Date de acces"), "date"), (_("Grupele"), "grupe")]
			actiuni.append((_("Player și piconuri"), "optiuni"))
		actiuni.extend([(_("Importă surse IPTV din fișier"), "import_stalker"), (_("Exportă toate sursele IPTV"), "export_stalker")])
		self.session.openWithCallback(self._alegeCont, ChoiceBox, title=p["nume"] if p else _("Surse IPTV"), list=actiuni)

	def _alegeCont(self, ales=None):
		if ales and ales[1] == "import_stalker":
			self.session.openWithCallback(self._importStalker, IptvFisierStalker)
			return
		if ales and ales[1] == "export_stalker":
			from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleFisier
			self.session.openWithCallback(self._exportStalker, HdsEditorCanaleFisier, "dosar")
			return
		p = self._aleasa()
		if not ales or not p:
			return
		if ales[1] == "grupe":
			self.session.openWithCallback(self._dupaFormular, IptvGrupe, p["id"])
		elif ales[1] == "optiuni":
			self.session.openWithCallback(self._dupaFormular, IptvOptiuni, p["id"])
		else:
			self.session.openWithCallback(self._dupaFormular, IptvDateAcces, p["fel"], p["id"])

	def _importStalker(self, cale=None):
		if cale:
			from Components import HdsIptvTransfer as F
			self['ghid'].setText(_("Se încarcă"))
			def gata(date):
				self.session.openWithCallback(self._dupaFormular, IptvImportStalker, date or dict(surse=[], rele=[], eroare=F.T_CITIRE))
			_transferInFir(self, lambda: F.citesteFisier(cale), gata)

	def _exportStalker(self, ales=None):
		if not ales or ales[0] != "dosar":
			return
		from Components import HdsIptvTransfer as F
		self['ghid'].setText(_("Se încarcă"))
		def gata(cale):
			self['ghid'].setText(_("Sursele IPTV au fost exportate în %s.") % cale if cale else _("Exportul nu s-a putut scrie. Alege un dosar cu spațiu liber."))
		_transferInFir(self, lambda: F.exportaFisier(ales[1]), gata)

	def _adauga(self):
		if len(self._surse) >= I.MAX_SURSE:
			self["ghid"].setText(I.textSursePline(_))
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


class IptvFisierStalker(Screen):
	"""Alegere locala. EXIT nu citeste si nu schimba nimic."""
	skin = """
	<screen name="IptvFisierStalker" resolution="1920,1080" position="center,center" size="1240,700" title="IPTV">
		<widget name="hds_cale" position="10,10" size="1220,36" font="Regular;22" noWrap="1" />
		<widget name="lista" position="10,52" size="1220,480" scrollbarMode="showOnDemand" />
		<widget name="hds_stare" position="10,52" size="1220,480" font="Regular;22" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget name="ghid" position="10,540" size="1220,90" font="Regular;24" />
		<widget name="key_red" position="10,650" size="300,40" font="Regular;24" />
		<widget name="key_green" position="320,650" size="300,40" font="Regular;24" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		from Components.FileList import FileList
		from Components.HdsNavigator import HdsPanouFisiere
		self.setTitle(_("Importă surse IPTV din fișier"))
		self["lista"] = FileList(None)
		self.panou = HdsPanouFisiere(self, self["lista"], details=False)
		self["ghid"] = Label(_("Alege fișierul text, JSON sau HD Satelit de pe stick ori disc. Formatul se recunoaște singur."))
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Alege"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self._alege, "green": self._alege, "red": self.close, "cancel": self.close}, -2)

	def _alege(self):
		lista = self["lista"]
		if lista.canDescent():
			lista.descent()
			return
		nume = lista.getFilename()
		if nume:
			self.close(nume if os.path.isabs(nume) else os.path.join(lista.getCurrentDirectory() or "", nume))


class IptvImportStalker(Screen):
	"""Rezumatul este singurul pas inaintea adaugarii lotului."""
	skin = """
	<screen name="IptvImportStalker" resolution="1920,1080" position="center,center" size="1240,700" title="IPTV">
		<widget name="text" position="20,20" size="1200,570" font="Regular;28" />
		<widget name="key_red" position="20,630" size="450,50" font="Regular;26" />
		<widget name="key_green" position="650,630" size="550,50" font="Regular;26" />
	</screen>"""

	def __init__(self, session, date):
		Screen.__init__(self, session)
		from Components.ScrollLabel import ScrollLabel
		from Components import HdsIptvTransfer as F
		self.setTitle(_("Importă surse IPTV din fișier"))
		self.date = date
		self.gata = False
		self["text"] = ScrollLabel(_("Se încarcă"))
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button("")
		self._pregatit = False
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self._adauga, "green": self._adauga, "cancel": self.close, "red": self.close,
			"up": self["text"].pageUp, "down": self["text"].pageDown}, -2)
		self.onLayoutFinish.append(self._pregateste)

	def _pregateste(self):
		from Components import HdsIptvTransfer as F
		_transferInFir(self, lambda: F.rezumat(self.date), self._dupaRezumat)

	def _dupaRezumat(self, rez):
		from Components import HdsIptvTransfer as F
		if rez is None:
			self['text'].setText(_(F.T_SURSE_CITIRE))
			return
		self._pregatit = bool(rez['noi'] and not rez.get('eroare'))
		self['text'].setText(F.textRezumat(rez, _) + "\n\n" + _("Importul adaugă sursele fără să le încerce la portal. Cele existente rămân neschimbate."))
		self['key_green'].setText(_("Adaugă sursele") if self._pregatit else "")

	def _adauga(self):
		if getattr(self, '_transferOcupat', False):
			return
		if self.gata:
			self.close()
			return
		if not self._pregatit:
			return
		from Components import HdsIptvTransfer as F
		date = self.date
		self['text'].setText(_("Se încarcă"))
		_transferInFir(self, lambda: F.adauga(date), self._dupaImport)

	def _dupaImport(self, rez):
		from Components import HdsIptvTransfer as F
		if rez is None:
			self['text'].setText(_("Sursele nu s-au putut salva. Verifică spațiul liber."))
			return
		self.gata = True
		self.date = None
		self["text"].setText(F.textRezumat(rez, _))
		self["key_green"].setText(_("Înapoi"))


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

	# textele se traduc la afisare (_arata); N_ le arata lui xgettext
	FELURI = (
		("m3u", N_("Playlist"), N_("O adresă de internet sau un fișier de pe stick.")),
		("xtream", N_("Cont"), N_("Server, utilizator și parolă.")),
		("stalker", N_("Portal"), N_("Adresa portalului și adresa MAC.")),
		("demo", N_("Listă demo"), N_("Canale gratuite care permit asta, cu acordul lor la vedere.")),
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


# randurile fiecarui fel: (cheia sursei, numele randului, e parola); numele, titlurile si ghidul se traduc la afisare (N_)
_RANDURI = {
	"m3u": (("adresa", N_("Adresa listei"), False), ("nume", N_("Nume (opțional)"), False)),
	"xtream": (("server", N_("Server"), False), ("utilizator", N_("Utilizator"), False), ("parola", N_("Parolă"), True), ("nume", N_("Nume (opțional)"), False)),
	"stalker": (("portal", N_("Adresa portalului"), False), ("mac", N_("Adresa MAC"), False), ("nume", N_("Nume (opțional)"), False)),
}
_TITLURI = {"m3u": N_("Playlist"), "xtream": N_("Cont"), "stalker": N_("Portal")}
_GHID = {
	"m3u": N_("Scrie adresa listei sau alege fișierul de pe stick cu tasta galbenă. OK deschide tastatura."),
	"xtream": N_("Scrie datele primite de la furnizor. OK deschide tastatura."),
	"stalker": N_("Pentru un abonament legat de alt receptor, scrie aici adresa MAC de pe acela. Unii furnizori nu permit două receptoare pornite în același timp cu aceeași adresă."),
}


T_SE_VERIFICA = N_("Se verifică legătura cu serverul...")
T_PLAYER = N_("Player în buchete")


def alegeriPlayer():
	"""Playerele buchetelor IPTV (HdsIptvSurse.PLAYERE) la adaugarea sursei; aceleasi ca in Player si piconuri (IptvOptiuni)."""
	return [("4097", _("4097 (implicit)")), ("5001", "5001 (gstreamer)"), ("5002", "5002 (exteplayer3)")]


_ANTETE = (("user_agent", N_("Agent utilizator (opțional)"), False), ("referer", N_("Referer (opțional)"), False))


class IptvDateAcces(Screen, ConfigListScreen):
	"""Formularul unei surse: un rand pe camp, OK deschide tastatura, Verde verifica si salveaza. Cat se verifica, ecranul asteapta;
	daca serverul refuza, omul vede de ce si poate schimba pe loc. O sursa noua care nu merge nu ramane in lista."""
	skin = """
	<screen name="IptvDateAcces" resolution="1920,1080" position="center,center" size="1500,800" title="Date de acces">
		<widget name="config" position="30,30" size="1440,420" font="Regular;30" secondfont="Regular;28" itemHeight="64" scrollbarMode="showOnDemand" />
		<widget source="ghid" render="Label" position="30,470" size="1440,50" font="Regular;26" noWrap="1" valign="center" />
		<widget name="stare" position="30,530" size="1440,170" font="Regular;28" valign="top" />
		<widget name="mac_vechi" conditional="mac_vechi" position="30,660" size="1440,45" font="Regular;26" />
		<widget source="key_red" render="Label" position="30,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="390,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" conditional="key_yellow" position="750,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
	</screen>
	"""

	def __init__(self, session, fel="m3u", sursa_id=None):
		if fel == "stalker":
			self.skin = self.skin.replace('size="1440,170"', 'size="1440,120"')
			self.skin = self.skin.replace('position="30,470" size="1440,50"', 'position="30,452" size="1440,96"').replace('noWrap="1"', 'noWrap="0"')
			self.skin = self.skin.replace('position="30,530" size="1440,120"', 'position="30,552" size="1440,100"')
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
		elif fel == "stalker":
			self["key_yellow"] = Label(_("Fă o adresă MAC"))
			self["mac_vechi"] = Label("")
			self.mac_dinainte = None
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"red": self.close,
			"green": self.salveaza,
			"yellow": self.galben,
		}, -2)
		self.campuri = {}
		lista = []
		identitate = (("x_user_agent", N_("X-User-Agent (opțional)"), False), ("stb_type", N_("Tip decodor (opțional)"), False)) if fel == "stalker" else ()
		for cheie, nume, e_parola in _RANDURI.get(fel, ()) + _ANTETE + identitate:
			if e_parola:
				el = _ParolaNoua(default=self.vechi.get(cheie) or "", fixed_size=False)
			else:
				# kreidlerboy, LinuxSat #971520: derulam antetele lungi fara a taia valoarea salvata.
				implicit = I.macReceptor() if cheie == "mac" and fel == "stalker" and not sursa_id else ""
				el = ConfigText(default=self.vechi.get(cheie) or implicit, fixed_size=False,
					visible_width=60 if cheie in ("user_agent", "referer", "x_user_agent", "stb_type") else False)
			self.campuri[cheie] = el
			lista.append(getConfigListEntry(_(nume), el))
			if cheie == "nume":
				# XTP0 (0.8.0, ozgurc67): playerul buchetelor se alege si la adaugare, nu numai in Player si piconuri;
				# din fabrica cel de acum (4097 la o sursa noua, al sursei la editare), deci nimic de facut daca nu vrei altul
				el = ConfigSelection(default=I.playerSursa(self.vechi), choices=alegeriPlayer())
				self.campuri["player"] = el
				lista.append(getConfigListEntry(_(T_PLAYER), el))
		self.list = lista
		self["config"].list = self.list
		if vechi and fel == "xtream":
			self["stare"].setText(_("Parola se vede și după salvare. Un rând gol o lasă cum e."))
		elif fel == "stalker":
			self["stare"].setText(_("Adresa nouă trebuie dată furnizorului. Pentru un cont mutat de pe alt receptor, scrie adresa de acolo. Se păstrează numai la Salvează."))
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
		if isinstance(el, ConfigSelection):
			self.keyRight()       # randul playerului: OK trece la playerul urmator, ca sageata dreapta
			return
		e_parola = isinstance(el, ConfigPassword)

		def gata(text, el=el, rand=x):
			if text is None:
				return
			el.value = text if e_parola else text.strip()
			el.validateMarker()
			if e_parola:
				el.scrisa = True
			self["config"].invalidate(rand)
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(gata, VirtualKeyBoard, title=x[0], text=el.value,
			hdsSecret=e_parola)

	def galben(self):
		if self.astept:
			return
		if self.fel == "stalker":
			mac = I.macNouaStalker()
			if not self.mac_dinainte:
				self.mac_dinainte = self.campuri["mac"].value
			if self.mac_dinainte:
				self["mac_vechi"].setText(_("Adresa de dinainte:") + " " + self.mac_dinainte)
			self.campuri["mac"].value = mac
			self["config"].list = self.list
			self["stare"].setText(_("Adresa nouă trebuie dată furnizorului. Pentru un cont mutat de pe alt receptor, scrie adresa de acolo. Se păstrează numai la Salvează."))
			return
		if self.fel != "m3u":
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
		# XTP0: playerul pleaca numai daca omul l-a schimbat; altfel un cont adaugat din nou isi pastreaza playerul
		if date.get("player") == I.playerSursa(self.vechi):
			date.pop("player", None)
		if self.fel == "xtream" and not date.get("parola"):
			date["parola"] = self.vechi.get("parola") or ""
		return date

	def salveaza(self):
		if self.astept:
			return
		if self.fel == "stalker":
			sursa, eroare = C.verificaDate(self.fel, self._date(), sursa_id=self.sursa_id)
		else:
			sursa, eroare = C.verificaDate(self.fel, self._date())
		if eroare:
			self["stare"].setText(_(eroare))
			return
		self.astept = sursa["id"]
		if L.adaugaSiCere(sursa) is None:
			self.astept = None
			self["stare"].setText(I.textSursePline(_))
			return
		if self.sursa_id and self.sursa_id != sursa["id"]:
			# Alta adresa sau alt utilizator: e alta sursa, iar cea veche pleaca.
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


class IptvPreluare(Screen, ConfigListScreen):
	"""Preluarea automata a listelor M3U gasite (Da din fabrica) si cererile in asteptare, ca in pagina web /iptv.
	Totul din memorie (Components/HdsIptvFisier): nimic de pe disc pe firul interfetei."""
	skin = IptvDateAcces.skin

	def __init__(self, session):
		from Components import HdsIptvFisier as F
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=None)
		self.setTitle(_("Liste M3U găsite"))
		# camp temporar: Renunta lasa setarea cum era
		self.automat = ConfigYesNo(default=F.preluareAutomata())
		self["config"].list = [getConfigListEntry(_(F.T_AUTOMAT), self.automat)]
		self["ghid"] = StaticText(_(F.T_NOTA_AUTOMAT))
		self["stare"] = Label("")
		self["key_red"] = StaticText(_("Renunță"))
		self["key_green"] = StaticText(_("Salvează"))
		self["key_yellow"] = Button(_("Liste în așteptare"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close, "red": self.close, "green": self.salveaza,
			"ok": self.keyRight, "yellow": self._cereri}, -2)
		self.onLayoutFinish.append(self._arataStare)

	def _arataStare(self, mesaj=""):
		from Components import HdsIptvFisier as F
		n = len(F.stareListe()["cereri"])
		text = _("Liste în așteptare: %d.") % n if n else _("Nu sunt liste în așteptare.")
		self["stare"].setText(("%s %s" % (mesaj, text)).strip())

	def salveaza(self):
		from Components import HdsIptvFisier as F
		F.seteazaPreluare(self.automat.value)
		self.close(True)

	def _cereri(self):
		from Components import HdsIptvFisier as F
		from Screens.ChoiceBox import ChoiceBox
		cereri = F.stareListe()["cereri"]
		if not cereri:
			self._arataStare()
			return
		self.session.openWithCallback(self._aleasa, ChoiceBox, title=_("Liste în așteptare"),
			list=[(r["nume"], r) for r in cereri])

	def _aleasa(self, ales=None):
		if not ales:
			return
		from Components import HdsIptvFisier as F
		from Screens.MessageBox import MessageBox
		r = ales[1]

		def raspuns(da=None):
			if da in ("da", "nu"):
				self._arataStare(F.raspunde(r["jeton"], da == "da")["message"])
		self.session.openWithCallback(raspuns, MessageBox, r["text"], type=MessageBox.TYPE_YESNO,
			list=[(_(F.T_DA), "da"), (_(F.T_NU), "nu"), (_(F.T_TARZIU), "tarziu")])


class IptvOptiuni(Screen, ConfigListScreen):
	"""Aceleasi doua optiuni pe televizor si in web, fara rescrierea datelor de acces."""
	skin = IptvDateAcces.skin

	def __init__(self, session, sursa_id):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=None)
		self.sursa_id = sursa_id
		s = I.sursa(sursa_id) or {}
		self.setTitle(_("Player și piconuri"))
		self.player = ConfigSelection(default=I.playerSursa(s), choices=[
			("4097", _("4097 (implicit)")), ("5001", "5001 (gstreamer)"), ("5002", "5002 (exteplayer3)")])
		self.piconuri = ConfigYesNo(default=s.get("piconuri") is True)
		self["config"].list = [getConfigListEntry(_("Player în buchete"), self.player),
			getConfigListEntry(_("Descarcă piconurile sursei"), self.piconuri)]
		self["ghid"] = StaticText(_("Setările se aplică acestei surse. Piconurile existente se păstrează."))
		self["stare"] = Label(_("Playerul ales trebuie să fie instalat pe receptor."))
		self["key_red"] = StaticText(_("Renunță"))
		self["key_green"] = StaticText(_("Salvează"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close, "red": self.close, "green": self.salveaza, "ok": self.keyRight}, -2)

	def salveaza(self):
		eroare = C.salveazaOptiuni(self.sursa_id, {"player": self.player.value, "piconuri": self.piconuri.value})
		if eroare:
			self["stare"].setText(_(eroare))
		else:
			self.close(True)


def textRandCont(fel, r):
	"""Textul unui rand din pagina sursei (IptvCont, fara enigma2, si in probe): r = datele randului."""
	if fel == "sectiune":
		return u"%s  ·  %s" % (r["titlu"], r["numar"]) if r.get("numar") else r["titlu"]
	if fel == "grupa":
		return u"%s  ·  %s" % (r["nume"], textCanale(r["n"]))
	if fel == "canal":
		return r["nume"]
	if fel == "categorie":
		return r["nume"]
	if fel == "sezon":
		return _("Sezonul %s") % r["numar"]
	if fel == "episod":
		return u"%s%s%s" % (("%s. " % r["numar"]) if r.get("numar") else "", r["nume"],
			(u"  ·  " + V.textDurata(r["durata"])) if r.get("durata") else "")
	parti = [r.get("nume") or ""]
	if r.get("nota"):
		parti.append(r["nota"].replace(".", ","))
	return u"  ·  ".join(parti)


def sectiuniSursa(p):
	"""Randurile de sus ale paginii sursei: Canale TV (cu numarul, deja stiut), Filme (la un playlist cu numarul lor), Seriale (cont
	Xtream). Fara nimic cerut furnizorului: filmele si serialele se cer cand omul deschide randul."""
	rez = [{"cheie": "canale", "titlu": _(T_CANALE_TV), "numar": textCanale(p["canale"]) if p.get("canale") else ""}]
	if p.get("fel") == "xtream":
		rez.append({"cheie": V.FILME, "titlu": _(T_FILME), "numar": ""})
		rez.append({"cheie": V.SERIALE, "titlu": _(T_SERIALE), "numar": ""})
	elif p.get("fel") == "m3u" and I.areFilme(p):
		# dupa fisierul filmelor (un playlist adus inainte de 0.7.7 isi are inca filmele in lista de canale, pana la aducere)
		rez.append({"cheie": V.FILME, "titlu": _(T_FILME), "numar": str(I.numarFilme(p))})
	return rez


class IptvCont(Screen):
	"""0.7.7 (FLM2, Eduard 16.11 11:01: 'Omul cand intra in aplicatie vrea sa aiba pe toate acolo'): pagina unei surse din aplicatia
	IPTV. Sus: Canale TV, Filme, Seriale (ce are sursa); OK deschide, EXIT urca un nivel, iar titlul spune mereu al cui e
	('Cont de proba › Filme › Actiune'). Canale TV: grupele, apoi canalele (OK porneste canalul si inchide meniurile). Filme:
	categoriile, apoi titlurile (OK porneste filmul de unde ai ramas, in acelasi player ca Filme si seriale, cu aceeasi pozitie).
	Seriale: categoriile, serialele, sezoanele, episoadele (dupa un episod porneste singur urmatorul). GALBEN cauta in filme sau
	seriale, ALBASTRU arata descrierea. Lista e compacta (STANGA / DREAPTA = pagina) si nu cere nimic furnizorului pana nu
	deschide omul un rand; canalele se citesc din fisierul sursei pe un fir, filmele si serialele prin Components/HdsVod (pe firele
	lui), ca in Filme si seriale. Perechea web: pagina /iptv, butonul 'Deschide' (HdsWebControl/internet_web.py)."""
	skin = """
	<screen name="IptvCont" resolution="1920,1080" position="center,center" size="1500,800" title="IPTV">
		<widget name="ghid" position="30,20" size="1440,50" font="Regular;26" noWrap="1" valign="center" />
		<widget name="lista" position="30,80" size="1440,620" font="Regular;30" itemHeight="52" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="390,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" position="750,730" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget name="key_blue" position="1110,730" size="360,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	def __init__(self, session, sursa_id, sectiune=None):
		Screen.__init__(self, session)
		from enigma import eTimer
		self.sursa_id = sursa_id
		self.p = next((x for x in I.citesteSursePublic() if x["id"] == sursa_id), {"id": sursa_id, "fel": "", "nume": ""})
		self.numeSursa = self.p.get("nume") or _(I.NUME_FEL.get(self.p.get("fel"), "IPTV"))
		self["lista"] = MenuList([])
		self["ghid"] = Label("")
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Deschide"))
		self["key_yellow"] = Button("")
		self["key_blue"] = Button("")
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "InfobarEPGActions"], {
			"cancel": self._inapoi, "red": self._inapoi, "ok": self._ok, "green": self._ok,
			"yellow": self._cauta, "blue": self._descriere, "showEventInfo": self._descriere,
			"up": self._sus, "down": self._jos, "left": self._paginaSus, "right": self._paginaJos,
		}, -2)
		# nivelurile: dict(fel, titlu, randuri, index, tip, ...); cel de sus e pe ecran
		self._niveluri = []
		self._cheie = None          # lucrarea HdsVod asteptata
		self._dupaLucrare = None
		self._fir = None            # firul care citeste canalele
		self._canale = None         # [(grupa, [(cheie, nume, directa)])], citite o data pe deschidere
		self._ceas = eTimer()
		self._ceas.callback.append(self._verifica)
		self.onClose.append(self._laInchidere)
		self._sectiune = sectiune
		# metoda legata, nu lambda: GUISkin.createGUIScreen ia orice alt fel de functie din onLayoutFinish drept cod de executat
		self.onLayoutFinish.append(self._laInceput)

	def _laInceput(self):
		if self.p.get("neconectata"):
			L.cere(self.sursa_id)
		self._intra("sectiuni", None, [("sectiune", r) for r in sectiuniSursa(self.p)])
		if self._sectiune:
			self._deschideSectiune(self._sectiune)

	def _laInchidere(self):
		self._ceas.stop()
		if self._cheie:
			V.renunta(self._cheie)
		self._cheie = None
		self._canale = None

	# ---------------------------------------------------------------- nivelurile

	def _intra(self, fel, titlu, randuri, **date):
		nivel = dict(date, fel=fel, titlu=titlu, randuri=randuri, index=0)
		self._niveluri.append(nivel)
		self._arata()

	def _nivel(self):
		return self._niveluri[-1] if self._niveluri else None

	def _arata(self, mesaj=""):
		n = self._nivel()
		if n is None:
			return
		drum = [self.numeSursa] + [x["titlu"] for x in self._niveluri if x["titlu"]]
		self.setTitle(u" › ".join(drum))
		self["lista"].setList([(textRandCont(fel, r), (fel, r)) for fel, r in n["randuri"]])
		self["lista"].moveToIndex(min(n["index"], max(0, len(n["randuri"]) - 1)))
		tip = n.get("tip")
		self["key_yellow"].setText(_("Caută") if tip in (V.FILME, V.SERIALE) else "")
		self["key_blue"].setText(_("Descriere") if n["fel"] in ("titluri", "episoade") else "")
		self["key_green"].setText(_("Pornește") if n["fel"] in ("canale", "episoade") or (n["fel"] == "titluri" and tip == V.FILME)
			else _("Deschide"))
		self._ghid(mesaj)

	def _ales(self):
		cur = self["lista"].getCurrent()
		return cur[1] if cur else (None, None)

	def _ghid(self, mesaj=""):
		n = self._nivel()
		if mesaj:
			self["ghid"].setText(mesaj)
		elif not n["randuri"]:
			self["ghid"].setText(_("Niciun rezultat."))
		else:
			fel, r = self._ales()
			self["ghid"].setText(textRandCont(fel, r) if fel else "")

	def _tine(self):
		n = self._nivel()
		if n is not None and self["lista"].instance is not None:
			n["index"] = self["lista"].getSelectionIndex()

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

	def _inapoi(self):
		self._dupaConectare = None
		if self._cheie:
			V.renunta(self._cheie)
			self._cheie = None
			self._ceas.stop()
		if len(self._niveluri) > 1:
			self._niveluri.pop()
			self._arata()
		else:
			self.close(False)

	# ---------------------------------------------------------------- asteptarile (canalele pe un fir, filmele prin HdsVod)

	def _asteapta(self, cheie, dupa):
		if not cheie:
			self._ghid(_(V.E_OCUPAT))
			return
		self._cheie, self._dupaLucrare = cheie, dupa
		self["ghid"].setText(_("Se încarcă..."))
		self._ceas.start(300, False)

	def _verifica(self):
		if getattr(self, "_dupaConectare", None):
			if L.inLucru(self.sursa_id):
				return
			dupa, self._dupaConectare = self._dupaConectare, None
			self._ceas.stop()
			s = I.sursa(self.sursa_id) or {}
			if s.get("eroare"):
				self._ghid(_(s["eroare"]))
			else:
				self._cereCanale(dupa)
			return
		if self._fir is not None:
			if self._fir.is_alive():
				return
			self._fir = None
			dupa, self._dupaLucrare = self._dupaLucrare, None
			self._ceas.stop()
			if dupa:
				dupa(None)
			return
		if not self._cheie:
			self._ceas.stop()
			return
		rez = V.rezultat(self._cheie)
		if rez.get("lucreaza"):
			return
		self._ceas.stop()
		self._cheie = None
		dupa, self._dupaLucrare = self._dupaLucrare, None
		if not rez.get("result"):
			self._ghid(_(rez.get("message") or V.E_NU_RASPUNDE))
			return
		if dupa:
			dupa(rez)

	def _cereCanale(self, dupa):
		if "neconectata" in self.p and not self.p.get("canale") and L.inLucru(self.sursa_id):
			self._dupaConectare = dupa
			self["ghid"].setText(_("Se încarcă..."))
			self._ceas.start(300, False)
			return
		if self._canale is not None:
			dupa(None)
			return
		import threading
		s = I.sursa(self.sursa_id) or {}

		def lucru():
			try:
				self._canale = I.grupeCanale(s) if s else []
			except Exception as e:
				print("[IptvCont] canalele: %s" % type(e).__name__)
				self._canale = []
		self._dupaLucrare = dupa
		self["ghid"].setText(_("Se încarcă..."))
		self._fir = threading.Thread(target=lucru, name="IptvContCanale")
		self._fir.daemon = True
		self._fir.start()
		self._ceas.start(200, False)

	# ---------------------------------------------------------------- OK

	def _deschideSectiune(self, cheie):
		for i, (fel, r) in enumerate(self._nivel()["randuri"]):
			if r.get("cheie") == cheie:
				self["lista"].moveToIndex(i)
				self._ok()
				return

	def _ok(self):
		fel, r = self._ales()
		if fel is None or self._cheie or self._fir is not None or getattr(self, "_dupaConectare", None):
			return
		self._tine()
		if fel == "sectiune":
			if r["cheie"] == "canale":
				self._cereCanale(lambda _rez: self._intra("grupe", r["titlu"], [("grupa", {"nume": g, "n": len(c), "canale": c})
					for g, c in (self._canale or [])]))
			else:
				tip = r["cheie"]
				self._asteapta(V.cere("categorii", self.sursa_id, tip), lambda rez: self._intra("categorii", r["titlu"],
					[("categorie", c) for c in rez.get("categorii") or []], tip=tip))
		elif fel == "grupa":
			self._intra("canale", r["nume"], [("canal", {"cheie": k, "nume": nume, "directa": d}) for k, nume, d in r["canale"]])
		elif fel == "canal":
			self._pornesteCanal(r)
		elif fel == "categorie":
			tip = self._nivel()["tip"]
			self._asteapta(V.cere("rand", self.sursa_id, tip, r["id"]), lambda rez: self._intra("titluri", r["nume"],
				[("titlu", t) for t in rez.get("titluri") or []], tip=tip))
		elif fel == "titlu":
			tip = r.get("tip") or self._nivel().get("tip") or V.FILME
			if tip == V.SERIALE:
				self._asteapta(V.cere("detalii", self.sursa_id, V.SERIALE, r["id"]), lambda rez: self._intra("sezoane", r["nume"],
					[("sezon", sz) for sz in (rez.get("detalii") or {}).get("sezoane") or []], tip=V.SERIALE, serial=r,
					detalii=rez.get("detalii") or {}))
			else:
				self._pornesteFilm(r)
		elif fel == "sezon":
			n = self._nivel()
			self._intra("episoade", _("Sezonul %s") % r["numar"], [("episod", e) for e in r.get("episoade") or []], tip=V.SERIALE,
				serial=n.get("serial"), detalii=n.get("detalii"), sezon=r)
		elif fel == "episod":
			self._pornesteEpisod(r)

	def _pornesteCanal(self, r):
		try:
			from enigma import eServiceReference
			serviciu = eServiceReference(I.refCanal(self.sursa_id, r["cheie"], r.get("directa")))
			serviciu.setName(r["nume"])
			self.session.nav.playService(serviciu)
		except Exception as e:
			print("[IptvCont] canalul: %s" % type(e).__name__)
			self._ghid(_("Canalul nu a pornit. Încearcă din nou."))
			return
		self.close(True)

	def _src(self):
		return V.sursa(self.sursa_id)

	def _pornesteFilm(self, t):
		from Screens.HdsFilmeSeriale import reda, pozitieTitlu
		from Components import HdsVodPozitii as Z
		src = self._src()
		if src is None or not t.get("cheie"):
			self._ghid(_(V.E_LIPSA))
			return
		reda(self.session, src, t["cheie"], {"nume": t["nume"], "poza": t.get("poza", ""), "tip": V.FILME},
			pozitieTitlu(src, Z.cheie(src.id, t["cheie"])), lambda *a: self._arata())

	def _pornesteEpisod(self, e):
		from Screens.HdsFilmeSeriale import reda, pozitieTitlu
		from Components import HdsVodPozitii as Z
		src = self._src()
		n = self._nivel()
		if src is None:
			self._ghid(_(V.E_LIPSA))
			return
		d, serial, sz = n.get("detalii") or {}, n.get("serial") or {}, n.get("sezon") or {}
		meta = {"nume": e["nume"], "poza": e.get("poza") or serial.get("poza", ""), "tip": V.SERIALE, "serial": serial.get("id", ""),
			"serial_nume": d.get("nume") or serial.get("nume", ""), "sezon": sz.get("numar", ""), "numar": e.get("numar", "")}
		ep = sz.get("episoade") or []
		i = next((k for k, x in enumerate(ep) if x.get("cheie") == e.get("cheie")), len(ep))
		urmatoare = [(x["cheie"], dict(meta, nume=x["nume"], numar=x.get("numar", ""))) for x in ep[i + 1:i + 30]]
		reda(self.session, src, e["cheie"], meta, pozitieTitlu(src, Z.cheie(src.id, e["cheie"])), lambda *a: self._arata(), urmatoare)

	# ---------------------------------------------------------------- GALBEN, ALBASTRU

	def _cauta(self):
		tip = (self._nivel() or {}).get("tip")
		if tip not in (V.FILME, V.SERIALE) or self._cheie:
			return
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(lambda text=None, tip=tip: self._dupaCautare(tip, text), VirtualKeyBoard,
			title=_("Caută seriale") if tip == V.SERIALE else _("Caută"), text="")

	def _dupaCautare(self, tip, text=None):
		text = (text or "").strip()[:80]
		if not text:
			return
		self._tine()
		self._asteapta(V.cere("cauta", self.sursa_id, tip, text), lambda rez: self._intra("titluri", text,
			[("titlu", dict(t, tip=tip)) for t in rez.get("titluri") or []], tip=tip))

	def _descriere(self):
		n = self._nivel()
		fel, r = self._ales()
		if n is None or n["fel"] not in ("titluri", "episoade") or fel is None or self._cheie:
			return
		if fel == "episod":
			self.session.open(IptvTextSerial, textRandCont(fel, r), r.get("descriere") or _("Nu există descriere."))
			return
		tip = n.get("tip") or V.FILME

		def arata(rez):
			d = rez.get("detalii") or {}
			rand = u"  ·  ".join(x for x in (d.get("an"), V.textDurata(d.get("durata")), d.get("gen")) if x)
			self.session.open(IptvTextSerial, d.get("nume") or r["nume"], (rand + "\n\n" if rand else "") + (d.get("descriere") or
				_("Nu există descriere.")))
			self._ghid()
		self._asteapta(V.cere("detalii", self.sursa_id, tip, r["id"]), arata)


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
