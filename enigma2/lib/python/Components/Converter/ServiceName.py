# -*- coding: utf-8 -*-
# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.Converter.Converter import Converter
from enigma import iServiceInformation, iPlayableService, iPlayableServicePtr
from Components.Element import cached

class ServiceName(Converter, object):
	NAME = 0
	PROVIDER = 1
	REFERENCE = 2

	def __init__(self, type):
		Converter.__init__(self, type)
		if type == "Provider":
			self.type = self.PROVIDER
		elif type == "Reference":
			self.type = self.REFERENCE
		else:
			self.type = self.NAME

	def getServiceInfoValue(self, info, what, ref=None):
		v = ref and info.getInfo(ref, what) or info.getInfo(what)
		if v != iServiceInformation.resIsString:
			return "N/A"
		return ref and info.getInfoString(ref, what) or info.getInfoString(what)

	@cached
	def getText(self):
		service = self.source.service
		if isinstance(service, iPlayableServicePtr):
			info = service and service.info()
			ref = None
		else: # reference
			info = service and self.source.info
			ref = service
		if info is None:
			return ""
		if self.type == self.NAME:
			name = ref and info.getName(ref)
			if name is None:
				name = info.getName()
			return name.replace('\xc2\x86', '').replace('\xc2\x87', '')
		elif self.type == self.PROVIDER:
			return self.getServiceInfoValue(info, iServiceInformation.sProvider, ref)
		elif self.type == self.REFERENCE:
			v = self.getServiceInfoValue(info, iServiceInformation.sServiceref, ref)
			# o referinta din lista de canale sau din ghid: informatia statica a unui canal DVB nu da sServiceref ("N/A"),
			# deci se da referinta insasi, ca sigla canalului (Renderer/Picon.py) sa se gaseasca si acolo
			if v == "N/A" and ref is not None:
				try:
					return ref.toString()
				except Exception:
					pass
			return v

	text = property(getText)

	def changed(self, what):
		if what[0] != self.CHANGED_SPECIFIC or what[1] in (iPlayableService.evStart,):
			Converter.changed(self, what)
