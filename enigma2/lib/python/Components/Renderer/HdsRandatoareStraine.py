# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRandatoareStraine.py: randatoarele cerute de temele externe, pe care imaginea nu le are, cu numele din XML. Nu sunt fisiere proprii in
# Components/Renderer, ca un pachet de tema care aduce un fisier cu acelasi nume sa se instaleze fara conflict si sa ramana al lui
# (Components/HdsTemaExterna.py le arata importului numai cand nu exista fisierul). Modulul se incarca numai cand un ecran din tema cere
# unul dintre ele. Din 11.11.2026 numele fara fisier se vad la import si sub tema HD Satelit (Components/Converter/__init__.py), pentru
# pluginurile cu skin in cod; tot atunci: Cover, AudioIcon, SingleEpgList, AnalogClockLCD, RatingIconLabel.
import math
import os
import re
import time

from enigma import eLabel, ePixmap, eCanvas, eRect, eSize, ePoint, gRGB

from Components.Renderer.Renderer import Renderer
from Components.Renderer.Label import Label
from Components.Renderer.Picon import Picon
from Components.VariableText import VariableText

MAX_EMISIUNI = 10


def _evenimente(*nume):
	try:
		from enigma import iPlayableService as P
		return tuple(getattr(P, n) for n in nume if hasattr(P, n))
	except Exception:
		return ()


_EV_CANAL = _evenimente("evStart", "evEnd", "evUpdatedInfo")
_EV_VIDEO = _evenimente("evStart", "evEnd", "evUpdatedInfo", "evVideoSizeChanged", "evVideoProgressiveChanged")


class _Eticheta(Renderer, VariableText):
	GUI_WIDGET = eLabel

	def __init__(self):
		Renderer.__init__(self)
		VariableText.__init__(self)

	def connect(self, source):
		Renderer.connect(self, source)
		self.changed((self.CHANGED_DEFAULT,))


class ChannelNumber(_Eticheta):
	"""Numarul canalului redat, acelasi ca pe bara imaginii; nimic cand canalul nu are numar."""

	def changed(self, what):
		if what[0] == self.CHANGED_SPECIFIC and what[1] not in _EV_CANAL:
			return
		if what[0] == self.CHANGED_CLEAR:
			self.text = ""
			return
		self.text = self._numar()

	def _numar(self):
		try:
			from enigma import iServiceInformation
			from Components.Converter.HdsInfo import numar_canal
			service = self.source.service
			info = service and service.info()
			sref = info and info.getInfoString(iServiceInformation.sServiceref)
			n = numar_canal(self.source, sref) if sref else 0
			return str(n) if n > 0 else ""
		except Exception:
			return ""


def textMarime(latime, inaltime, progresiv=-1):
	if latime <= 0 or inaltime <= 0:
		return ""
	return "%dx%d%s" % (latime, inaltime, {0: "i", 1: "p"}.get(progresiv, ""))


class VideoSize(_Eticheta):
	"""Marimea imaginii canalului redat ("1920x1080", cu "i" sau "p" cand decodorul o spune); nimic fara imagine."""

	def changed(self, what):
		if what[0] == self.CHANGED_SPECIFIC and what[1] not in _EV_VIDEO:
			return
		if what[0] == self.CHANGED_CLEAR:
			self.text = ""
			return
		try:
			from enigma import iServiceInformation as I
			service = self.source.service
			info = service and service.info()
			if not info:
				self.text = ""
				return
			self.text = textMarime(info.getInfo(I.sVideoWidth), info.getInfo(I.sVideoHeight),
				info.getInfo(I.sProgressive) if hasattr(I, "sProgressive") else -1)
		except Exception:
			self.text = ""


def randuri(evenimente, n, spatii, eticheta=""):
	"""Textul pentru [(inceput, titlu), ...] (fara emisiunea de acum): cel mult n randuri, cu eticheta deasupra."""
	rez = [eticheta] if eticheta else []
	for inceput, titlu in evenimente[:n]:
		if not titlu:
			continue
		rez.append("%s%s%s" % (time.strftime("%H:%M", time.localtime(inceput)), " " * spatii, titlu))
	return "\n".join(rez) if len(rez) > (1 if eticheta else 0) else ""


class NextEpgInfo(_Eticheta):
	"""Emisiunile urmatoare ale canalului ales intr-o lista, din ghid, cate una pe rand. NumberOfItems (cate), noLabel (fara randul
	"Urmeaza"), numOfSpaces (spatii intre ora si titlu); timeColor se primeste si se lasa deoparte (eticheta are o singura culoare)."""

	def __init__(self):
		_Eticheta.__init__(self)
		self.cate = 1
		self.faraEticheta = False
		self.spatii = 2

	def applySkin(self, desktop, parent):
		atribute = []
		for (attrib, value) in self.skinAttributes or []:
			if attrib == "NumberOfItems":
				self.cate = max(1, min(MAX_EMISIUNI, int(value)))
			elif attrib == "noLabel":
				self.faraEticheta = value not in ("0", "")
			elif attrib == "numOfSpaces":
				self.spatii = max(0, min(10, int(value)))
			elif attrib not in ("timeColor", "Wrap"):
				atribute.append((attrib, value))
		self.skinAttributes = atribute
		return Renderer.applySkin(self, desktop, parent)

	def changed(self, what):
		if what[0] == self.CHANGED_CLEAR:
			self.text = ""
			return
		self.text = self._text()

	def _text(self):
		try:
			from enigma import eEPGCache
			ref = getattr(self.source, "service", None)
			if ref is None or not hasattr(ref, "toString"):
				return ""
			# de acum, cel mult cate + 1 (prima e cea de acum)
			gasite = eEPGCache.getInstance().lookupEvent(["IBT", (ref.toString(), 0, -1, 24 * 60)]) or []
			evenimente = [(b, t) for (_i, b, t) in gasite[1:self.cate + 1] if b]
			eticheta = ""
			if not self.faraEticheta:
				try:
					from Components.Converter import HdsCommon as C
					eticheta = C.tr("next")
				except Exception:
					eticheta = ""
			return randuri(evenimente, self.cate, self.spatii, eticheta)
		except Exception:
			return ""


class NextEvents(NextEpgInfo):
	pass


class VolumeText(_Eticheta):
	"""Volumul de acum ca numar (0-100), in fereastra volumului; sursa e ceasul, deci se reciteste cat fereastra se vede."""

	def changed(self, what):
		try:
			from enigma import eDVBVolumecontrol
			self.text = str(eDVBVolumecontrol.getInstance().getVolume())
		except Exception:
			self.text = ""


class VVolumeText(VolumeText):
	pass


try:
	# randatorul imaginii (Components/Renderer/RunningText.py: movetype, direction, steptime, startdelay ...); VRunningText,
	# numele din alte teme, e acelasi randator
	from Components.Renderer.RunningText import RunningText
except ImportError:
	class RunningText(Label):
		"""Rezerva, numai daca randatorul imaginii lipseste: o eticheta pe un rand, textul care nu incape deruleaza singur din
		eLabel. Atributul options se lasa deoparte."""

		def applySkin(self, desktop, parent):
			atribute = [(a, v) for (a, v) in (self.skinAttributes or []) if a != "options"]
			if not any(a == "noWrap" for (a, _v) in atribute):
				atribute.append(("noWrap", "1"))
			self.skinAttributes = atribute
			return Label.applySkin(self, desktop, parent)


class VRunningText(RunningText):
	pass


class RegularLabel(Label):
	pass


class Rectangle(Renderer):
	"""Un dreptunghi plin, de culoarea din backgroundColor."""
	GUI_WIDGET = eLabel


class PiconBg(Picon):
	"""Sigla canalului; alphatest si scale raman ale ei."""


class CiModuleControl(_Eticheta):
	"""Starea sloturilor CI. Receptoarele imaginii nu au slot CI, deci eticheta ramane goala; atributele se primesc si se lasa deoparte."""

	def applySkin(self, desktop, parent):
		self.skinAttributes = [(a, v) for (a, v) in (self.skinAttributes or []) if a not in ("allVisible", "colors", "noneColor", "useColor", "activeColor")]
		return Renderer.applySkin(self, desktop, parent)

	def changed(self, what):
		self.text = ""


def _atributeProprii(randator, nume):
	"""Scoate din skinAttributes atributele randatorului (dictionar nume -> valoare); restul ajung la widget."""
	proprii, rest = {}, []
	for (a, v) in (randator.skinAttributes or []):
		if a in nume:
			proprii[a] = v
		else:
			rest.append((a, v))
	randator.skinAttributes = rest
	return proprii


def _culoare(text, implicit):
	try:
		from skin import parseColor
		return parseColor(text)
	except Exception:
		return implicit


class Cover(Renderer):
	"""Coperta filmului redat sau ales: <fisier>.jpg/.png/.jpeg langa film, apoi imaginea cu numele dosarului, apoi folder.jpg; fara
	coperta, elementul se ascunde. Imaginea se potriveste in caseta."""
	GUI_WIDGET = ePixmap
	EXTENSII = (".jpg", ".png", ".jpeg")

	def __init__(self):
		Renderer.__init__(self)
		self.hdsCoperte = {}
		self.hdsCoperta = None

	def _cale(self):
		s = self.source
		ref = None
		for nume in ("getCurrentServiceReference", "getCurrentServiceRef"):
			f = getattr(s, nume, None)
			if f is not None:
				try:
					ref = f()
				except Exception:
					ref = None
				break
		if ref is None:
			ref = getattr(s, "service", None)
			if ref is not None and not hasattr(ref, "getPath"):
				ref = None
		if ref is None:
			try:
				nav = getattr(s, "navcore", None)
				ref = nav and nav.getCurrentlyPlayingServiceReference()
			except Exception:
				ref = None
		try:
			return ref.getPath() if ref is not None else ""
		except Exception:
			return ""

	def gaseste(self, cale):
		if not cale:
			return ""
		if cale in self.hdsCoperte:
			return self.hdsCoperte[cale]
		if os.path.isdir(cale):
			d = cale.rstrip("/")
			for coada in ("/bdmv", "/video_ts"):
				if d.lower().endswith(coada):
					d = d[:-len(coada)]
			baze = [os.path.join(d, os.path.basename(d)), os.path.join(d, "folder"), d]
		else:
			d = os.path.dirname(cale)
			baze = [os.path.splitext(cale)[0], os.path.join(d, os.path.basename(d)), os.path.join(d, "folder")]
		gasit = next((b + e for b in baze if b for e in self.EXTENSII if os.path.isfile(b + e)), "")
		self.hdsCoperte[cale] = gasit
		return gasit

	def changed(self, what):
		if not self.instance:
			return
		coperta = "" if what[0] == self.CHANGED_CLEAR else self.gaseste(self._cale())
		if coperta == self.hdsCoperta:
			return
		self.hdsCoperta = coperta
		if not coperta:
			self.instance.hide()
			return
		try:
			self.instance.setScale(1)
		except Exception:
			pass
		try:
			self.instance.setPixmapFromFile(coperta)
			self.instance.show()
		except Exception as e:
			print("[Cover] %s: %s" % (coperta, e))
			self.instance.hide()


class AudioIcon(Renderer):
	"""Imaginea <text>.png (de pilda numele codecului de sunet dat de convertor) din dosarul path= (cale intreaga sau fata de tema
	activa si de skin_default); fara imagine, elementul se ascunde."""
	GUI_WIDGET = ePixmap

	def __init__(self):
		Renderer.__init__(self)
		self.path = ""
		self.size = None
		self.hdsImagini = {}
		self.hdsImagine = None

	def applySkin(self, desktop, parent):
		a = _atributeProprii(self, ("path",))
		if "path" in a:
			self.path = os.path.join(a["path"], "")
		for (n, v) in self.skinAttributes:
			if n == "size" and len(v.split(",")) == 2:
				self.size = "x".join(x.strip() for x in v.split(","))
		return Renderer.applySkin(self, desktop, parent)

	def gaseste(self, nume):
		if not nume:
			return ""
		if nume in self.hdsImagini:
			return self.hdsImagini[nume]
		locuri = []
		if self.path.startswith("/"):
			locuri.append(self.path)
		try:
			from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
			locuri.append(os.path.join(resolveFilename(SCOPE_CURRENT_SKIN, ""), self.path))
		except Exception:
			pass
		locuri.append(os.path.join("/usr/share/enigma2/skin_default/", self.path))
		gasit = next((l + nume + ".png" for l in locuri if os.path.isfile(l + nume + ".png")), "")
		self.hdsImagini[nume] = gasit
		return gasit

	def changed(self, what):
		if not self.instance:
			return
		png = "" if what[0] == self.CHANGED_CLEAR else self.gaseste((getattr(self.source, "text", "") or "").strip())
		if not png:
			self.instance.hide()
		else:
			if png != self.hdsImagine:
				self.instance.setPixmapFromFile(png)
			self.instance.show()
		self.hdsImagine = png


class SingleEpgList(_Eticheta):
	"""Emisiunile de dupa cea de acum, pe canalul sursei: "HH:MM Titlu", cate un rand, cel mult maxEvents (implicit 4)."""

	def __init__(self):
		_Eticheta.__init__(self)
		self.maxEvents = 4

	def applySkin(self, desktop, parent):
		a = _atributeProprii(self, ("maxEvents",))
		try:
			self.maxEvents = max(1, int(a.get("maxEvents", self.maxEvents)))
		except ValueError:
			pass
		return Renderer.applySkin(self, desktop, parent)

	def changed(self, what):
		randuri = []
		try:
			ev = getattr(self.source, "event", None)
			service = getattr(self.source, "service", None)
			if ev is not None and service is not None:
				from enigma import eEPGCache
				ref = service.toString() if hasattr(service, "toString") else str(service)
				for e in (eEPGCache.getInstance().lookupEvent(["IBDT", (ref, 0, -1, -1)]) or [])[1:self.maxEvents + 1]:
					if e[3]:
						randuri.append("%s %s" % (time.strftime("%H:%M", time.localtime(e[1])), e[3]))
		except Exception as e:
			print("[SingleEpgList] %s" % e)
		self.text = "\n".join(randuri)


class AnalogClockLCD(Renderer):
	"""Un ac de ceas desenat (convertorul AnalogClock da "NN,hour/min/sec"): lungimea linesize, grosimea linewidth, centrul in
	mijlocul casetei positionwidth x positionheight; culoarea fColor (sau hColor/mColor/sColor), fondul bColor."""
	GUI_WIDGET = eCanvas

	def __init__(self):
		Renderer.__init__(self)
		self.fColor = gRGB(255, 255, 255, 0)
		self.bColor = gRGB(0, 0, 0, 255)
		self.linesize = 10
		self.linewidth = 1
		self.positionwidth = 1
		self.positionheight = 1
		self.hdsPozitie = None

	def applySkin(self, desktop, parent):
		a = _atributeProprii(self, ("bColor", "fColor", "hColor", "mColor", "sColor", "linesize", "linewidth", "positionwidth", "positionheight"))
		for n in ("fColor", "hColor", "mColor", "sColor"):
			if n in a:
				self.fColor = _culoare(a[n], self.fColor)
		if "bColor" in a:
			self.bColor = _culoare(a["bColor"], self.bColor)
		for n in ("linesize", "linewidth", "positionwidth", "positionheight"):
			try:
				if n in a:
					setattr(self, n, int(a[n]))
			except ValueError:
				pass
		return Renderer.applySkin(self, desktop, parent)

	def postWidgetCreate(self, instance):
		for (n, v) in (self.skinAttributes or []):
			if n == "size":
				try:
					l, i = (int(x) for x in v.split(","))
					instance.setSize(eSize(l, i))
				except Exception:
					pass
		instance.clear(self.bColor)

	def changed(self, what):
		if not self.instance or what[0] == self.CHANGED_CLEAR:
			return
		try:
			pozitie = int((getattr(self.source, "text", "") or "").split(",")[0])
		except ValueError:
			return
		if pozitie == self.hdsPozitie:
			return
		self.hdsPozitie = pozitie
		cx, cy = self.positionwidth / 2.0, self.positionheight / 2.0
		unghi = math.radians(pozitie * 6)
		x, y = cx + self.linesize * math.sin(unghi), cy - self.linesize * math.cos(unghi)
		self.instance.clear(self.bColor)
		try:
			self.instance.drawLine(cx, cy, x, y, float(self.linewidth), self.fColor)
		except Exception:
			# punct cu punct, cand canvasul nu are drawLine
			pasi = max(1, int(self.linesize))
			for k in range(pasi + 1):
				self.instance.fillRect(eRect(int(cx + (x - cx) * k / pasi), int(cy + (y - cy) * k / pasi), self.linewidth, self.linewidth), self.fColor)
		self.instance.show()


class RatingIconLabel(Renderer):
	"""Varsta minima a emisiunii (textul sursei: "12", "FSK 16" sau "12;#00ff0000" cu culoarea data) pe un fond colorat dupa
	colors="varsta:culoare,..."; caseta se lungeste spre extendDirection (right, left, none) cu sidesMargin; fara varsta, se ascunde."""
	GUI_WIDGET = eLabel

	def __init__(self):
		Renderer.__init__(self)
		self.colors = {}
		self.extendDirection = "right"
		self.sidesMargin = 20
		self.hdsLatime = 0
		self.hdsX = 0

	def applySkin(self, desktop, parent):
		a = _atributeProprii(self, ("colors", "extendDirection", "sidesMargin"))
		for parte in (a.get("colors") or "").split(","):
			k, _s, v = parte.partition(":")
			if k.strip().isdigit() and v.strip():
				self.colors[int(k)] = _culoare(v.strip(), None)
		self.extendDirection = a.get("extendDirection", self.extendDirection)
		try:
			self.sidesMargin = int(a.get("sidesMargin", self.sidesMargin))
		except ValueError:
			pass
		rez = Renderer.applySkin(self, desktop, parent)
		if self.instance:
			self.hdsLatime = self.instance.size().width()
			self.hdsX = self.instance.position().x()
		self.changed((self.CHANGED_DEFAULT,))
		return rez

	def _ascunde(self):
		if self.instance:
			self.instance.setText("")
			self.instance.hide()

	def changed(self, what):
		if not self.instance:
			return
		text = (getattr(self.source, "text", "") or "").strip() if what[0] != self.CHANGED_CLEAR else ""
		if not text:
			return self._ascunde()
		if ";" in text:
			varsta, _s, c = text.partition(";")
			if not varsta:
				return self._ascunde()
			culoare = _culoare(c, None)
		else:
			m = re.search(r"\d+", text.replace("+", ""))
			if not m:
				return self._ascunde()
			n = int(m.group())
			# varstele din ghid (0-15) inseamna varsta + 3
			if n <= 15:
				n += 3
			varsta = str(n)
			culoare = self.colors.get(n)
		self.instance.setNoWrap(1)
		self.instance.setText(varsta)
		latime = max(self.hdsLatime, self.instance.calculateSize().width() + self.sidesMargin)
		self.instance.setNoWrap(0)
		marime = self.instance.size()
		if self.extendDirection == "left":
			self.instance.move(ePoint(self.hdsX + self.hdsLatime - latime, self.instance.position().y()))
		if self.extendDirection != "none":
			self.instance.resize(eSize(latime, marime.height()))
		try:
			self.instance.setBackgroundColor(culoare if culoare is not None else gRGB(0x10000000))
		except Exception:
			pass
		self.instance.show()


# ---------------------------------------------------------------- Bhclock (agentul TM, 12.11.2026)

# Bhclock: numele cerut de o tema pentru acul unui ceas analogic (eGauge legat de o valoare 0-59, de pilda ClockToText cu Hours,
# Minutes sau Seconds pentru ac). Acelasi lucru il face EGclock (adus de TOT din OE-Alliance): acul pe eGauge sau, unde eGauge lipseste
# (enigma2-ul nostru), desenat pe eCanvas. Cod nou: numai numele.
from Components.Renderer.EGclock import EGclock as _EGclock


class Bhclock(_EGclock):
	pass

