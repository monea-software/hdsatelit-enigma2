# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRandatoareStraine.py: randatoarele cerute de temele externe, pe care imaginea nu le are, cu numele din XML. Nu sunt fisiere proprii in
# Components/Renderer, ca un pachet de tema care aduce un fisier cu acelasi nume sa se instaleze fara conflict si sa ramana al lui
# (Components/HdsTemaExterna.py le arata importului numai cand nu exista fisierul). Modulul se incarca numai cand un ecran din tema cere
# unul dintre ele.
import time

from enigma import eLabel

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
