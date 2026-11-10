# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Setari comune pentru vreme si panoul de pe televizor.
# Cautarea scrie numai in coada ei. Ceasul interfetei citeste rezultatul.

import queue
import threading

from enigma import ePoint, eTimer, getDesktop

from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components import HdsVremea as V
from Tools.LoadPixmap import LoadPixmap
from Tools.ScaledSkin import scaledSkin


UNITATI = (("C", "Celsius"), ("F", "Fahrenheit"), ("K", "Kelvin"))
LOCURI = (("nu", "Nu"), ("bara", "Bara de informații"),
	("principal", "Ecranul principal"), ("ambele", "Ambele"))


def locOsd(mod, bara):
	"""Locul panoului acum, sau nimic cand alegerea il ascunde."""
	if bara and mod in ("bara", "ambele"):
		return "bara"
	if not bara and mod in ("principal", "ambele"):
		return "principal"
	return ""


def _interval(date, zi, unitate):
	minim = date.get(zi + "_min")
	maxim = date.get(zi + "_max")
	if minim is None or maxim is None:
		return ""
	return "%s / %s" % (V.textTemperatura(minim, unitate), V.textTemperatura(maxim, unitate))


def _poza(widget, cale):
	"""Poza de pe disc se citeste numai cand se schimba calea."""
	if cale == getattr(widget, "_hds_vremea_cale", None):
		return
	widget._hds_vremea_cale = cale
	try:
		ptr = LoadPixmap(cale, cached=True) if cale else None
	except Exception:
		ptr = None
	widget.setPixmap(ptr)
	if ptr is not None:
		widget.show()
	else:
		widget.hide()


def _textScurt(widget, text, latime=None):
	"""Text intreg cand incape, altfel cu trei puncte la capat."""
	instanta = widget.instance
	if instanta is None:
		widget.setText(text)
		return text
	latime = latime or instanta.size().width()
	cheie = (text, latime)
	if cheie == getattr(widget, "_hds_vremea_text", None):
		return widget._hds_vremea_scurt
	widget.setText(text)
	rezultat = text
	while len(text) > 1 and instanta.calculateSize().width() > latime:
		text = text[:-1]
		rezultat = text.rstrip() + "..."
		widget.setText(rezultat)
	widget._hds_vremea_text = cheie
	widget._hds_vremea_scurt = rezultat
	return rezultat


def _cautaFir(nume, rezultat):
	rezultat.put(V.cautaOraseRezultat(nume))


SKIN_SETARI = """
<screen name="HdsVremea" position="48,27" size="1184,666"
	backgroundColor="#0D10162A" flags="wfNoBorder" title="Vremea">
	<widget source="Title" render="Label" position="24,12" size="1100,48"
		font="Bold;28" foregroundColor="#00F2F4F8" transparent="1" />
	<eLabel position="24,68" size="1136,1" backgroundColor="#99FFFFFF" />
	<widget name="lista" position="24,96" size="660,180" itemHeight="60"
		font="Regular;23" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A"
		backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF"
		transparent="1" scrollbarMode="showNever" />
	<widget name="pictograma" position="756,94" size="112,112" alphatest="blend" scale="1" />
	<widget name="oras" position="704,216" size="456,90" font="Regular;23"
		foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" itemHeight="90"
		backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF"
		transparent="1" scrollbarMode="showNever" />
	<widget name="acum" position="704,316" size="456,92" font="Bold;26"
		foregroundColor="#00F2F4F8" transparent="1" />
	<widget name="prognoza" position="704,420" size="456,128" font="Regular;21"
		foregroundColor="#00C9D2E3" transparent="1" />
	<widget name="masura" position="24,96" size="660,60" font="Regular;23" noWrap="1" />
	<widget name="nota" position="24,310" size="660,190" font="Regular;22"
		foregroundColor="#00C9D2E3" transparent="1" />
	<widget name="mesaj" position="24,520" size="1136,72" font="Regular;22"
		foregroundColor="#00F5B83D" transparent="1" />
	<eLabel position="24,612" size="1136,1" backgroundColor="#99FFFFFF" />
	<widget name="key_red" position="24,626" size="250,32" font="Regular;21"
		foregroundColor="#00E5484D" transparent="1" />
	<widget name="key_yellow" position="416,626" size="350,32" font="Regular;21"
		foregroundColor="#00E8B93A" transparent="1" />
	<widget name="key_blue" position="820,626" size="340,32" font="Regular;21"
		foregroundColor="#003D7BE0" transparent="1" />
</screen>"""


class HdsVremea(Screen):
	"""Fiecare alegere se salveaza pe loc, fara alta confirmare."""

	def __init__(self, session, cautare=""):
		self.skin = scaledSkin(SKIN_SETARI)
		Screen.__init__(self, session)
		self.setTitle(_("Vremea"))
		V.initConfig()
		self.inchis = False
		self.cautare = None
		self.cautareInitiala = cautare if isinstance(cautare, str) else ""
		self.orasDreapta = False
		self["lista"] = MenuList([])
		self["oras"] = MenuList([])
		for nume in ("acum", "prognoza", "nota", "mesaj", "masura"):
			self[nume] = Label("")
		self["masura"].hide()
		self["pictograma"] = Pixmap()
		self["key_red"] = Label(_("Închide"))
		self["key_yellow"] = Label(_("Oraș automat"))
		self["key_blue"] = Label(_("Caută oraș"))
		self["nota"].setText(_("OK alege. Stânga și Dreapta schimbă unitatea sau locul afișării. "
			"Alegerile se păstrează imediat.\n\n"
			"Unitatea și orașul sunt comune cu afișajul din față și cu interfața web."))
		actiuni = {"ok": self.alege, "cancel": self.close, "red": self.close,
			"yellow": self.automat, "blue": self.cauta, "up": lambda: self.vertical(-1),
			"down": lambda: self.vertical(1), "left": lambda: self.schimba(-1),
			"right": lambda: self.schimba(1)}
		for tasta in ("up", "down"):
			actiuni[tasta + "Repeated"] = actiuni[tasta]
		for tasta in ("upUp", "downUp", "leftUp", "rightUp", "leftRepeated", "rightRepeated"):
			actiuni[tasta] = lambda: None
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni, -1)
		self.ceas = eTimer()
		self.ceas.callback.append(self.arata)
		self.ceasCautare = eTimer()
		self.ceasCautare.callback.append(self.rezultatCautare)
		self.onLayoutFinish.append(self.arata)
		self.onLayoutFinish.append(self._cautaInitial)
		self.onShown.append(self.porneste)
		self.onHide.append(self.ceas.stop)
		self.onClose.append(self.inchide)

	def porneste(self):
		self._afisajVremea(True)
		self.arata()
		self.ceas.start(10000, False)

	def inchide(self):
		self._afisajVremea(False)
		self.inchis = True
		self.ceas.stop()
		self.ceasCautare.stop()
		self.cautare = None

	def _afisajVremea(self, deschis):
		try:
			from Components import HdsAfisajColor as C
			C.vremeDeschisa(self, deschis)
		except Exception:
			pass

	def arata(self):
		if self.inchis:
			return
		s = V.setari()
		oras = s.get("oras_nume") or _("Automat, după fusul orar sau țară")
		index = self["lista"].getSelectionIndex() or 0
		latime = self["lista"].instance.size().width() - 24 if self["lista"].instance else None
		textOras = _textScurt(self["masura"], _("Oraș: %s") % oras, latime)
		self["lista"].setList([textOras,
			_("Unitate: %s") % _(dict(UNITATI).get(s.get("unitate"), "Celsius")),
			_("Vremea pe TV: %s") % _(dict(LOCURI).get(s.get("tema"), "Nu"))])
		self["lista"].moveToIndex(index)
		d = V.date()
		unitate = s.get("unitate", "C")
		if d and d.get("temperatura") is not None:
			self._arataOras(d.get("oras", ""))
			self["acum"].setText("%s\n%s" % (
				V.textTemperatura(d["temperatura"], unitate), _(d.get("stare", ""))))
			linii = []
			for zi, titlu in (("azi", _("Azi")), ("maine", _("Mâine"))):
				interval = _interval(d, zi, unitate)
				if interval:
					linii.append("%s: %s" % (titlu, interval))
			self["prognoza"].setText("\n".join(linii))
			_poza(self["pictograma"], d.get("pictograma", ""))
		else:
			self._arataOras(s.get("oras_nume") or _("Oraș automat"))
			self["acum"].setText(_("Vremea nu este disponibilă acum."))
			self["prognoza"].setText(_("Datele apar automat când sunt disponibile."))
			_poza(self["pictograma"], "")
		self._focusOras()

	def _arataOras(self, text):
		instanta = self["oras"].instance
		latime = instanta.size().width() - 24 if instanta else None
		self["oras"].setList([_textScurt(self["masura"], text, latime)])

	def _focusOras(self):
		self["lista"].selectionEnabled(not self.orasDreapta)
		self["oras"].selectionEnabled(self.orasDreapta)

	def vertical(self, pas):
		if self.orasDreapta:
			self.orasDreapta = False
			self._focusOras()
		else:
			(self["lista"].up if pas < 0 else self["lista"].down)()

	def salveaza(self, schimbari):
		bun, mesaj = V.seteaza(schimbari)
		self["mesaj"].setText(mesaj)
		if bun:
			self.arata()

	def automat(self):
		if self.cautare is None:
			self.salveaza({"oras": ""})

	def _alegeriRand(self):
		index = self["lista"].getSelectionIndex() or 0
		return ("unitate", UNITATI) if index == 1 else ("tema", LOCURI)

	def schimba(self, pas):
		if self.cautare is not None:
			return
		if self.orasDreapta:
			if pas < 0:
				self.orasDreapta = False
				self._focusOras()
			return
		if not self["lista"].getSelectionIndex():
			if pas > 0:
				self.orasDreapta = True
				self._focusOras()
			return
		cheie, alegeri = self._alegeriRand()
		valori = [v for v, _t in alegeri]
		acum = V.setari().get(cheie)
		index = valori.index(acum) if acum in valori else 0
		self.salveaza({cheie: valori[(index + pas) % len(valori)]})

	def alege(self):
		if self.cautare is not None:
			return
		if self.orasDreapta or not self["lista"].getSelectionIndex():
			self.cauta()
			return
		cheie, alegeri = self._alegeriRand()
		valori = [v for v, _t in alegeri]
		acum = V.setari().get(cheie)
		index = valori.index(acum) if acum in valori else 0

		def gata(ales):
			if ales is not None and not self.inchis:
				self.salveaza({cheie: ales[1]})
		self.session.openWithCallback(gata, ChoiceBox, title=_("Alege"),
			list=[(_(nume), valoare) for valoare, nume in alegeri], selection=index)

	def cauta(self):
		if self.cautare is not None:
			return
		self.session.openWithCallback(self.pornesteCautarea, VirtualKeyBoard,
			title=_("Numele orașului"), text="")

	def _cautaInitial(self):
		nume = self.cautareInitiala
		self.cautareInitiala = ""
		if nume:
			self.pornesteCautarea(nume)

	def pornesteCautarea(self, nume):
		if self.inchis or self.cautare is not None or not nume or not nume.strip():
			return
		rezultat = queue.Queue(maxsize=1)
		self.cautare = rezultat
		self["mesaj"].setText(_("Se caută orașul..."))
		fir = threading.Thread(target=_cautaFir, args=(nume.strip(), rezultat))
		fir.daemon = True
		fir.start()
		self.ceasCautare.start(200, False)

	def rezultatCautare(self):
		if self.inchis or self.cautare is None:
			return
		try:
			rezultat = self.cautare.get_nowait()
		except queue.Empty:
			return
		self.cautare = None
		self.ceasCautare.stop()
		orase = rezultat["orase"]
		if not rezultat["result"] or not orase:
			self["mesaj"].setText(rezultat["message"])
			return
		self["mesaj"].setText("")
		self.session.openWithCallback(self.orasAles, ChoiceBox, title=_("Alege orașul"),
			list=[(oras["nume"], oras) for oras in orase])

	def orasAles(self, ales):
		if ales is not None and not self.inchis:
			oras = ales[1]
			self.salveaza({"oras": V.codOras(oras)})


SKIN_OSD = """
<screen name="HdsVremeaOsd" position="880,48" size="352,120"
	backgroundColor="#2610162A" flags="wfNoBorder" zPosition="3">
	<widget name="pictograma" position="10,10" size="78,78" alphatest="blend" scale="1" />
	<widget name="temperatura" position="98,8" size="244,36" font="Bold;27"
		foregroundColor="#00F2F4F8" transparent="1" noWrap="1" />
	<widget name="oras" position="98,46" size="244,28" font="Regular;21"
		foregroundColor="#00C9D2E3" transparent="1" noWrap="1" />
	<widget name="stare" position="10,90" size="332,26" font="Regular;19"
		foregroundColor="#00C9D2E3" transparent="1" noWrap="1" />
</screen>"""


class HdsVremeaOsd(Screen):
	"""Panou mic, fara taste proprii, folosit de bara principala."""

	def __init__(self, session):
		self.skin = scaledSkin(SKIN_OSD)
		Screen.__init__(self, session)
		for nume in ("temperatura", "oras", "stare"):
			self[nume] = Label("")
		self["pictograma"] = Pixmap()
		self.ultimele = None

	def actualizeaza(self, date, unitate):
		texte = (V.textTemperatura(date["temperatura"], unitate),
			date.get("oras", ""), _(date.get("stare", "")))
		if texte != self.ultimele:
			for nume, text in zip(("temperatura", "oras", "stare"), texte):
				_textScurt(self[nume], text)
			self.ultimele = texte
		_poza(self["pictograma"], date.get("pictograma", ""))

	def aseaza(self, loc, bara):
		if self.instance is None:
			return
		marime = getDesktop(0).size()
		f = marime.width() / 1280.0
		margine = int(48 * f)
		latime, inaltime = self.instance.size().width(), self.instance.size().height()
		x = marime.width() - margine - latime
		y = margine
		if loc == "bara" and bara.instance is not None:
			p, s = bara.instance.position(), bara.instance.size()
			x = p.x() + s.width() - latime
			y = p.y() - inaltime - int(8 * f)
			if y < 0:
				y = p.y() + s.height() + int(8 * f)
		x = max(0, min(x, marime.width() - latime))
		y = max(0, min(y, marime.height() - inaltime))
		self.instance.move(ePoint(x, y))


class LegaturaVremea(object):
	"""Panoul traieste cat bara; niciun fir de retea nu atinge fereastra."""

	def __init__(self, bara):
		self.bara = bara
		self.panou = bara.session.instantiateDialog(HdsVremeaOsd)
		self.panou.hide()
		self.ceas = eTimer()
		self.ceas.callback.append(self.actualizeaza)
		bara.onShow.append(self.actualizeaza)
		bara.onHide.append(self.ascunde)
		bara.onClose.append(self.inchide)
		self.ceas.start(1000, False)

	def ascunde(self):
		if self.panou is not None:
			self.panou.hide()

	def inchide(self):
		self.ceas.stop()
		if self.panou is not None:
			self.bara.session.deleteDialog(self.panou)
			self.panou = None
		self.bara = None

	def actualizeaza(self):
		try:
			self._actualizeaza()
		except Exception:
			self.ascunde()

	def _actualizeaza(self):
		b = self.bara
		if b is None or self.panou is None:
			self.ascunde()
			return
		s = V.setari()
		loc = locOsd(s.get("tema", "nu"), bool(b.shown))
		if not loc or not b.execing or b.session.current_dialog is not b:
			self.ascunde()
			return
		from Screens.Standby import inStandby
		if inStandby is not None or b._hdsSecondaVizibila():
			self.ascunde()
			return
		service = b.session.nav.getCurrentService()
		ref = b.session.nav.getCurrentlyPlayingServiceReference()
		if service is None or ref is None:
			self.ascunde()
			return
		from Components.HdsRadioDate import este_radio
		if este_radio(service, ref.toString()):
			self.ascunde()
			return
		d = V.date()
		if not d or d.get("temperatura") is None:
			self.ascunde()
			return
		self.panou.actualizeaza(d, s.get("unitate", "C"))
		self.panou.aseaza(loc, b)
		self.panou.show()
