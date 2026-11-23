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


def N_(text):
	"""Marcajul textelor din tabele (xgettext --keyword=N_); traducerea se face la afisare, cu _()."""
	return text


UNITATI = (("C", N_("Celsius")), ("F", N_("Fahrenheit")), ("K", N_("Kelvin")))
# "Bara canalului": vremea mica in bara (pictograma si temperatura), in locul pus de tema; pe temele fara el, panoul plutitor
LOCURI = (("nu", N_("Nu")), ("bara", N_("Bara canalului")),
	("principal", N_("Ecranul principal")), ("ambele", N_("Ambele")))
ZILE = (("1", N_("1 zi")), ("2", N_("2 zile")), ("3", N_("3 zile")))
SCARI = (("100", "100%"), ("85", "85%"), ("75", "75%"))
# VRM6: unde sta vremea cand e in bara canalului (Components/HdsVremea.LOCURI_BARA); "sus" din fabrica
LOCURI_BARA = (("sus", N_("Sus, lângă ceas")), ("jos", N_("Jos în dreapta, mai mare")))

# Locul vremii in bara canalului (tema HDSatelit, Clasic si Pro): doua widgeturi cu nume in ecranul InfoBar al temei, cu
# conditional="..." (o alta clasa care ia acelasi ecran din skin nu le cere). Pictograma sta in stanga locului, temperatura
# dupa ea; codul le aseaza la fiecare pas dupa textul vecinilor din dreapta (timpul ramas, data, REC).
NUME_POZA = "hdsVremeaPoza"
NUME_TEXT = "hdsVremeaText"


def locOsd(mod, bara):
	"""Locul panoului acum, sau nimic cand alegerea il ascunde."""
	if bara and mod in ("bara", "ambele"):
		return "bara"
	if bara and mod == "principal":
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
	widget._hds_vremea_are = ptr is not None
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


def _semnalInchis():
	pass


SKIN_SETARI = """
<screen name="HdsVremea" position="48,27" size="1184,666"
	backgroundColor="#0D10162A" flags="wfNoBorder" title="Vremea">
	<widget source="Title" render="Label" position="24,12" size="1100,48"
		font="Bold;28" foregroundColor="#00F2F4F8" transparent="1" />
	<eLabel position="24,68" size="1136,1" backgroundColor="#99FFFFFF" />
	<widget name="lista" position="24,96" size="660,288" itemHeight="48"
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
	<widget name="nota" position="24,396" size="660,150" font="Regular;22"
		foregroundColor="#00C9D2E3" transparent="1" />
	<widget name="mesaj" position="24,550" size="1136,60" font="Regular;22"
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
		self["nota"].setText(_("OK alege. Stânga și Dreapta schimbă opțiunea. "
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
			_("Vremea pe TV: %s") % _(dict(LOCURI).get(s.get("tema"), "Nu")),
			_("Prognoza din colț: %s") % _(dict(ZILE).get(s.get("zile", "1"), "1 zi")),
			_("Scara panoului meteo: %s") % dict(SCARI).get(s.get("scara", "100"), "100%"),
			_("Locul vremii în bara canalului: %s") % _(dict(LOCURI_BARA).get(s.get("loc_bara", "sus"), "Sus, lângă ceas"))])
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
		return {1: ("unitate", UNITATI), 2: ("tema", LOCURI),
			3: ("zile", ZILE), 4: ("scara", SCARI), 5: ("loc_bara", LOCURI_BARA)}.get(index, ("tema", LOCURI))

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


def skinOsd(zile, scara):
	"""Build geometry once, preserving the compact default exactly."""
	from xml.etree import ElementTree as ET
	root = ET.fromstring(SKIN_OSD)
	root.set("size", "352,%d" % (120 + 32 * (int(zile) - 1)))
	for i, nume in enumerate(("maine", "poimaine")[:int(zile) - 1]):
		ET.SubElement(root, "widget", name=nume, position="10,%d" % (122 + i * 32),
			size="332,28", font="Regular;19", foregroundColor="#00C9D2E3", transparent="1", noWrap="1")
	factor = int(scara) / 100.0
	if factor != 1:
		for el in root.iter():
			for atribut in ("size", "position"):
				if el.get(atribut):
					el.set(atribut, ",".join(str(round(int(v) * factor)) for v in el.get(atribut).split(",")))
			if el.get("font"):
				font, marime = el.get("font").split(";")
				el.set("font", "%s;%d" % (font, round(int(marime) * factor)))
	return ET.tostring(root, encoding="unicode")


class HdsVremeaOsd(Screen):
	"""Panou mic, fara taste proprii, folosit de bara principala."""

	def __init__(self, session, zile=None, scara=None):
		s = V.setari()
		self.zile = zile or (s.get("zile", "1") if s.get("tema") == "principal" else "1")
		self.scara = scara or s.get("scara", "100")
		self.skin = scaledSkin(skinOsd(self.zile, self.scara))
		Screen.__init__(self, session)
		for nume in ("temperatura", "oras", "stare") + ("maine", "poimaine")[:int(self.zile) - 1]:
			self[nume] = Label("")
		self["pictograma"] = Pixmap()
		self.ultimele = None
		self.pozitie = None

	def actualizeaza(self, date, unitate):
		texte = (V.textTemperatura(date["temperatura"], unitate),
			date.get("oras", ""), _(date.get("stare", "")))
		if texte != self.ultimele:
			for nume, text in zip(("temperatura", "oras", "stare"), texte):
				_textScurt(self[nume], text)
			self.ultimele = texte
		_poza(self["pictograma"], date.get("pictograma", ""))
		for nume, titlu in (("maine", _("Mâine")), ("poimaine", _("Poimâine")))[:int(self.zile) - 1]:
			interval = _interval(date, nume, unitate)
			_textScurt(self[nume], "%s: %s" % (titlu, interval) if interval else "")

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
		if (x, y) != self.pozitie:
			self.instance.move(ePoint(x, y))
			self.pozitie = (x, y)


def _cutie(inst):
	p, m = inst.position(), inst.size()
	return p.x(), p.y(), m.width(), m.height()


def _atribute(element):
	try:
		return dict(getattr(element, "skinAttributes", None) or ())
	except (TypeError, ValueError):
		return {}


def margineLibera(ecran, x0, y0, x1, y1, ale_mele=(), z=0):
	"""Unde incepe, la dreapta lui x0, primul lucru desenat pe randul y0..y1 al ecranului (pixeli), sau x1.
	Se uita la elementele care se vad si ating locul [x0, x1) pe acel rand: o eticheta transparenta conteaza cu textul
	ei (cea aliniata la dreapta, ca timpul ramas sau data, de unde incepe textul; una goala deloc); o caseta plina (REC)
	sau o poza conteaza intreaga, afara de fundalurile de sub vreme (zPosition sub `z`, ca fundalul casetei Pro). Ce
	incepe inaintea lui x0 si intra in loc lasa locul fara nimic (x0)."""
	limita = x1
	elemente = list(getattr(ecran, "renderer", None) or []) + list(getattr(ecran, "additionalWidgets", None) or [])
	for el in elemente:
		inst = getattr(el, "instance", None)
		if inst is None or id(el) in ale_mele:
			continue
		try:
			if not inst.isVisible():
				continue
			x, y, l, i = _cutie(inst)
		except Exception:
			continue
		if y + i <= y0 or y >= y1 or x + l <= x0 or x >= limita:
			continue
		a = _atribute(el)
		if a.get("transparent") == "1" and hasattr(inst, "calculateSize"):
			try:
				text = inst.calculateSize().width()
			except Exception:
				text = l
			if text <= 0:
				continue
			alinie = a.get("halign", "left")
			if alinie == "right":
				inceput = x + max(0, l - text)
			elif alinie == "center":
				inceput = x + max(0, (l - text) // 2)
			else:
				inceput = x
			sfarsit = inceput + min(text, l)
		else:
			try:
				if int(a.get("zPosition", "0")) < z:
					continue
			except ValueError:
				pass
			inceput, sfarsit = x, x + l
		if sfarsit <= x0:
			continue
		limita = min(limita, max(x0, inceput))
	return limita


def asezareInBara(loc, latimeText, limita):
	"""Ce incape din vreme in locul ei din bara, fara sa atinga vecinul din dreapta.
	loc = (xPoza, yPoza, latimePoza, inaltimePoza, xText, yText, latimeText, inaltimeText) din skin, in pixeli;
	latimeText = cat ocupa temperatura; limita = margineLibera(...).
	-> (ce, xPoza, xText, latimeCasetei): ce = "tot" (pictograma si temperatura), "text" (numai temperatura) sau ""."""
	xp, _yp, lp, _ip, xt, _yt, lt, _it = loc
	pas = max(2, lp // 6)       # intre pictograma si temperatura
	aer = max(4, lp // 4)       # inaintea vecinului din dreapta
	dreapta = min(xt + lt, limita - aer)
	if latimeText <= 0:
		return "", xp, xp, 0
	x = xp + lp + pas
	if x + latimeText <= dreapta:
		return "tot", xp, x, dreapta - x
	if xp + latimeText <= dreapta:
		return "text", xp, xp, dreapta - xp
	return "", xp, xp, 0


class LegaturaVremea(object):
	"""Vremea traieste cat bara; niciun fir de retea nu atinge fereastra. Cu "Bara canalului" (sau "Ambele", cat se vede
	bara) vremea sta in bara, in locul pus de tema (NUME_POZA, NUME_TEXT); o tema fara loc (temele straine) primeste
	panoul plutitor, ca inainte. Panoul din colt urmeaza prima bara."""

	def __init__(self, bara):
		self.bara = bara
		bara[NUME_POZA] = Pixmap()
		bara[NUME_TEXT] = Label("")
		self.loc = None
		self.inBara = None
		self.geometrie = None
		self.panou = bara.session.instantiateDialog(HdsVremeaOsd)
		self.panou.hide()
		self.ceas = eTimer()
		self.ceas.callback.append(self.actualizeaza)
		self.legaturi = []
		self._leaga(bara, "onLayoutFinish", self._dupaSkin)
		self._leaga(bara, "onShow", self.actualizeaza)
		self._leaga(bara, "onHide", self.ascunde)
		self._leaga(bara, "onExecEnd", self.ascunde)
		self._leaga(bara, "onClose", self.inchide)
		self._leaga(bara.session.nav, "event", self._serviciu)
		second = getattr(bara, "secondInfoBarScreen", None)
		self._leaga(second, "onShow", self.ascunde)
		self._leaga(second, "onHide", self.actualizeaza)
		self.standby = None
		try:
			from Components.config import config
			self.standby = config.misc.standbyCounter
			self.standby.addNotifier(self._standby, initial_call=False)
		except (ImportError, AttributeError):
			self.standby = None
		self.ceas.start(1000, False)

	def _leaga(self, obiect, nume, functie):
		lista = getattr(obiect, nume, None)
		if lista is not None:
			lista.append(functie)
			self.legaturi.append((lista, functie))

	def _standby(self, element):
		self.ascunde()

	def _serviciu(self, eveniment):
		from enigma import iPlayableService
		if eveniment == iPlayableService.evEnd:
			self.ascunde()
		elif eveniment == iPlayableService.evStart:
			self.actualizeaza()

	def _dupaSkin(self):
		"""Locul din tema, citit o data: numai cand tema are amandoua widgeturile."""
		self.ascunde()
		self.loc = None
		self.inBara = None
		self.geometrie = None
		b = self.bara
		if b is None:
			return
		try:
			poza, text = b[NUME_POZA].instance, b[NUME_TEXT].instance
		except (KeyError, AttributeError, TypeError):
			return
		if poza is None or text is None:
			return
		self.loc = _cutie(poza) + _cutie(text)
		self._ascundeInBara()

	def _ascundeInBara(self):
		if self.inBara is False or self.loc is None:
			return
		self.inBara = False
		for nume in (NUME_POZA, NUME_TEXT):
			self.bara[nume].hide()

	def ascunde(self):
		if self.panou is not None:
			self.panou.hide()
		if self.bara is not None:
			self._ascundeInBara()

	def inchide(self):
		self.ceas.stop()
		if self.actualizeaza in self.ceas.callback:
			self.ceas.callback.remove(self.actualizeaza)
		for lista, functie in self.legaturi:
			if functie in lista:
				if self.bara is not None and lista is self.bara.onClose:
					# Screen iterates this list directly; preserve the next callback's index.
					lista[lista.index(functie)] = _semnalInchis
				else:
					lista.remove(functie)
		self.legaturi = []
		if self.standby is not None:
			self.standby.removeNotifier(self._standby)
			self.standby = None
		b, panou = self.bara, self.panou
		self.ascunde()
		self.bara = None
		self.panou = None
		if b is not None and panou is not None:
			b.session.deleteDialog(panou)

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
		# VRM6: "Jos in dreapta, mai mare" = panoul din coltul barei (ca pe temele fara loc), nu randul din bara
		if loc == "bara" and self.loc is not None and s.get("loc_bara", "sus") != "jos":
			self.panou.hide()
			self._arataInBara(d, s.get("unitate", "C"))
			return
		self._ascundeInBara()
		zile = s.get("zile", "1") if loc == "principal" else "1"
		scara = s.get("scara", "100")
		if (getattr(self.panou, "zile", "1"), getattr(self.panou, "scara", "100")) != (zile, scara):
			vechi = self.panou
			vechi.hide()
			# A failed instantiation leaves the old panel available for a retry.
			nou = b.session.instantiateDialog(HdsVremeaOsd, zile=zile, scara=scara)
			self.panou = nou
			b.session.deleteDialog(vechi)
		self.panou.actualizeaza(d, s.get("unitate", "C"))
		self.panou.aseaza(loc, b)
		self.panou.show()

	def _arataInBara(self, date, unitate):
		"""Pictograma si temperatura in locul din bara; fara loc destul, intai pleaca pictograma, apoi tot."""
		b = self.bara
		poza, text = b[NUME_POZA], b[NUME_TEXT]
		t = V.textTemperatura(date["temperatura"], unitate)
		if getattr(text, "_hds_vremea_text", None) != t:
			text.setText(t)
			text._hds_vremea_text = t
		latime = text.instance.calculateSize().width()
		xp, yp, lp, ip, xt, yt, lt, it = self.loc
		try:
			z = int(_atribute(text).get("zPosition", "0"))
		except ValueError:
			z = 0
		limita = margineLibera(b, xp, min(yp, yt), xt + lt, max(yp + ip, yt + it), (id(poza), id(text)), z)
		ce, _xPoza, xText, latimeCasetei = asezareInBara(self.loc, latime, limita)
		if not ce:
			self._ascundeInBara()
			return
		from enigma import eSize
		geometrie = (text.instance, xText, yt, latimeCasetei, it)
		if geometrie != self.geometrie:
			text.instance.move(ePoint(xText, yt))
			text.instance.resize(eSize(latimeCasetei, it))
			self.geometrie = geometrie
		cale = date.get("pictograma", "") if ce == "tot" else ""
		if cale:
			_poza(poza, cale)
		if cale and getattr(poza, "_hds_vremea_are", False):
			poza.show()
		else:
			poza.hide()
		self.inBara = True
		text.show()
