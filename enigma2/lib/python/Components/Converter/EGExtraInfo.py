# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# EGExtraInfo: convertorul cerut de temele scrise pentru alte imagini Enigma2 (12 teme din feeduri, 62 de folosiri; Premium-FHD
# il cere in bara canalului cu E-C-N). Tipurile, tabelul sistemelor si culorile barei sunt cele ale convertorului GPL-2.0 cu
# acelasi nume dintr-un enigma2 public (lib/python/Components/Converter/EGExtraInfo.py; nota autorilor: "Based on PliExtraInfo,
# recoded by meo"). Datele vin din ce stie imaginea despre decodare (Components/HdsEcm.py prin HdsCommon.ecm_info), nu din
# /tmp/ecm.info; adresele, cititoarele si porturile nu se arata niciodata. O valoare pe care nu o stim ramane goala.
#
# Tipurile (text): CamName, NetInfo, EcmInfo, E-C-N, CryptoBar; (boolean): CryptoCaid<Sistem>Available si
# CryptoCaid<Sistem>Selected, cu <Sistem> = Seca, Via, Irdeto, NDS, Conax, CryptoW, Beta, Nagra, Biss, Dre.
import time

from enigma import iServiceInformation
from Components.Converter.Converter import Converter
from Components.Converter.Poll import Poll
from Components.Element import cached

try:
	from Components.Converter import HdsCommon as C
except Exception:
	C = None

# (de la, pana la, numele, litera din bara), ca in convertorul original
CAID_DATA = (
	(0x1700, 0x17ff, "Beta", "B"),
	(0x600, 0x6ff, "Irdeto", "I"),
	(0x100, 0x1ff, "Seca", "S"),
	(0x500, 0x5ff, "Via", "V"),
	(0x1800, 0x18ff, "Nagra", "N"),
	(0x4ae0, 0x4ae1, "Dre", "D"),
	(0xd00, 0xdff, "CryptoW", "CW"),
	(0x900, 0x9ff, "NDS", "ND"),
	(0xb00, 0xbff, "Conax", "CO"),
	(0x2600, 0x2600, "Biss", "BI"),
)
_LITERA = dict((nume, litera) for _a, _b, nume, litera in CAID_DATA)
# culorile barei (codurile \c ale enigma2): sistemul care decodeaza, cele din canal, celelalte
CULOARE_ALES = "\\c0000??00"
CULOARE_CANAL = "\\c00????00"
CULOARE_ALTUL = "\\c007?7?7?"
CULOARE_SFARSIT = "\\c00??????"
# protocoalele care decodeaza singure, fara card si fara retea (in raspunsul modulului, "internal" e cititorul de card al
# receptorului, deci Card; HdsEcm.PROTOCOALE_LOCALE)
_EMU = ("emu", "constcw")


def ecmProaspat():
	"""Dictionarul ultimei decodari (HdsEcm.stare), numai daca e proaspat (HdsCommon.ECM_FRESH_S), altfel {}."""
	if C is None:
		return {}
	try:
		d = C.ecm_info() or {}
		if d.get("caid", -1) <= 0:
			return {}
		if not 0.0 <= time.time() - d.get("mtime", 0.0) <= C.ECM_FRESH_S:
			return {}
		return d
	except Exception:
		return {}


def _inSistem(caid, intrare):
	return isinstance(caid, int) and intrare[0] <= caid <= intrare[1]


def _tr(cheie, implicit):
	try:
		return C.tr(cheie) if C is not None else implicit
	except Exception:
		return implicit


class EGExtraInfo(Poll, Converter, object):
	def __init__(self, type):
		Converter.__init__(self, type)
		Poll.__init__(self)
		self.type = type
		self.poll_interval = 1000
		self.poll_enabled = True
		self.caid_data = CAID_DATA

	def _info(self):
		try:
			service = self.source.service
			return service and service.info()
		except Exception:
			return None

	@staticmethod
	def _criptat(info):
		try:
			return bool(info) and info.getInfo(iServiceInformation.sIsCrypted) == 1
		except Exception:
			return False

	@staticmethod
	def _caidsCanal(info):
		try:
			return [c for c in (info.getInfoObject(iServiceInformation.sCAIDs) or ()) if isinstance(c, int)]
		except Exception:
			return []

	@staticmethod
	def get_caName():
		if C is None:
			return ""
		try:
			return C.access_module_name() or ""
		except Exception:
			return ""

	def GetEcmInfo(self):
		"""Ce stie imaginea despre decodare, cu cheile convertorului original (fara adrese si cititoare)."""
		d = ecmProaspat()
		caid = d.get("caid", 0)
		prov = d.get("prov", -1)
		furnizor = ("%06X" % prov) if isinstance(prov, int) and prov > 0 else ""
		if d.get("prov_name"):
			furnizor = (furnizor + " " + d["prov_name"]).strip()
		return {
			"caid": "0x%04X" % caid if caid > 0 else "0x00",
			"pid": ("%04X" % d["pid"]) if d.get("pid", 0) > 0 else "",
			"provider": furnizor,
			"ecm_time": ("%d" % d["ms"]) if d.get("ms", -1) >= 0 else "",
			"protocol": d.get("protocol") or "",
			"local": d.get("local"),
		}

	@cached
	def getText(self):
		info = self._info()
		if not info:
			return ""
		criptat = self._criptat(info)
		if self.type == "CamName":
			return self.get_caName()
		if self.type == "CryptoBar":
			return self._bara(info)
		if self.type == "E-C-N":
			if not criptat:
				return "Fta"
			d = ecmProaspat()
			if not d:
				return ""
			if (d.get("protocol") or "").lower() in _EMU:
				return "Emulator"
			if d.get("local") is True:
				return "Card"
			if d.get("local") is False:
				return "Network"
			return ""
		if not criptat:
			return ""
		data = self.GetEcmInfo()
		if data["caid"] == "0x00":
			return ""
		if self.type == "EcmInfo":
			parti = ["CAID %s" % data["caid"][2:]]
			if data["provider"]:
				parti.append("%s: %s" % (_tr("provider", "Provider"), data["provider"]))
			return "     ".join(parti)
		if self.type == "NetInfo":
			parti = []
			if data["ecm_time"]:
				parti.append("%s: %s ms" % (_tr("ecm_time", "ECM time"), data["ecm_time"]))
			if data["pid"]:
				parti.append("PID: %s" % data["pid"])
			if data["protocol"]:
				parti.append("%s: %s" % (_tr("ecm_protocol", "Protocol"), data["protocol"]))
			if data["local"] is not None:
				parti.append(_tr("ecm_local", "local") if data["local"] else _tr("ecm_net", "over the network"))
			return "   ".join(parti)
		return ""

	text = property(getText)

	def _bara(self, info):
		ales = ecmProaspat().get("caid", -1) if self._criptat(info) else -1
		canal = self._caidsCanal(info)
		res = []
		for intrare in CAID_DATA:
			if _inSistem(ales, intrare):
				culoare = CULOARE_ALES
			elif any(_inSistem(c, intrare) for c in canal):
				culoare = CULOARE_CANAL
			else:
				culoare = CULOARE_ALTUL
			res.append(culoare + intrare[3])
		return " ".join(res) + CULOARE_SFARSIT

	@cached
	def getBool(self):
		info = self._info()
		if not info or not self.type.startswith("CryptoCaid"):
			return False
		rest = self.type[len("CryptoCaid"):]
		if rest.endswith("Available"):
			nume, ales = rest[:-len("Available")], False
		elif rest.endswith("Selected"):
			nume, ales = rest[:-len("Selected")], True
		else:
			return False
		litera = _LITERA.get(nume)
		if litera is None or not self._criptat(info):
			return False
		for intrare in CAID_DATA:
			if intrare[3] != litera:
				continue
			if ales:
				return _inSistem(ecmProaspat().get("caid", -1), intrare)
			return any(_inSistem(c, intrare) for c in self._caidsCanal(info))
		return False

	boolean = property(getBool)
