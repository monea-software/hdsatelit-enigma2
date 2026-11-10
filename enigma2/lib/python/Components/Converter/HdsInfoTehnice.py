# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsInfoTehnice.py: datele tehnice ale canalului redat, in forma ceruta de temele externe (HdsConvertoareStraine il foloseste).
# Sursa: session.CurrentService. Textele vin din convertorul imaginii (Components/Converter/HdsInfo.py) si din
# HdsCommon, deci sunt aceleasi ca in barele skinului HDSatelit, in limba receptorului. Argumentele:
#   ResolutionString  marimea imaginii, felul ei si cadrele: "1920x1080i 25" (tipul Resolution al lui HdsInfo);
#   ServiceInfo       semnele canalului pe un rand: UHD / FHD / HD / SD, 16:9 sau 4:3, HDR, codecul video, 5.1,
#                     teletext, subtitrari, HbbTV (etichetele semnelor din barele imaginii);
#   CryptoBar         sistemele de acces ale canalului, cel prin care se decripteaza acum primul ("Irdeto / Nagravision
#                     +2"), acelasi text ca pagina accesului din a doua bara (HdsCommon.access_head);
#   All               trei randuri: accesul (ca CryptoBar, plus CAID-ul si timpul raspunsului cand se stiu, ca
#                     CryptoInfo); imaginea si sunetul (codecul, marimea, formatul, sunetul); receptia (ca TechLeft).
# Despre acces nu se arata nimic in plus fata de ce arata deja imaginea. Orice alt argument merge la HdsInfo.
# Se reciteste la evenimentele serviciului, ca HdsInfo; CryptoBar si All si la 2 secunde cat se vad (sistemul folosit
# se afla dupa primul raspuns al decodarii). Se incarca numai cand o tema il cere.

import time

from Components.Converter.Converter import Converter
from Components.Converter.HdsInfo import HdsInfo, M_VIDEO, EV_HBB
from Components.Converter.Poll import Poll

try:
	from Components.Converter import HdsCommon as C
except Exception:
	C = None

# argumentul -> metoda; cele cu acces se recitesc si la 2 secunde
TIPURI_TEHNICE = {
	"ResolutionString": "_hds_rezolutie",
	"ServiceInfo": "_hds_semne",
	"CryptoBar": "_hds_acces",
	"All": "_hds_toate",
}
CU_ACCES = ("_hds_acces", "_hds_toate")
POLL_ACCES_MS = 2000


class HdsInfoTehnice(Poll, HdsInfo):
	def __init__(self, arg):
		nume = str(arg or "").split(",")[0].strip()
		fn = TIPURI_TEHNICE.get(nume)
		# tipurile noi: evenimentele unui tip video al lui HdsInfo (pornire, informatii, imagine) si HbbTV (semnul lui)
		HdsInfo.__init__(self, "TechRight" if fn else arg)
		Poll.__init__(self)
		if fn:
			self._fn, self._isbool, self._mask, self._opts = fn, False, M_VIDEO | EV_HBB, ()
			if fn in CU_ACCES:
				self.poll_interval = POLL_ACCES_MS
				self.poll_enabled = True

	def changed(self, what):
		if what and what[0] == self.CHANGED_POLL:
			if self._fn in CU_ACCES:
				self._val = None
				Converter.changed(self, what)
			return
		HdsInfo.changed(self, what)

	def doSuspend(self, suspended):
		# ceasul de 2 secunde al tipurilor cu acces (Poll) si cronometrul tipurilor de timp trecute la HdsInfo
		Poll.doSuspend(self, suspended)
		HdsInfo.doSuspend(self, suspended)

	def destroy(self):
		try:
			Poll.destroy(self)
		except Exception:
			pass
		HdsInfo.destroy(self)

	# ------------------------------------------------------------ textele

	def _hds_rezolutie(self, r):
		return self._resolution(r)

	def _hds_semne(self, r):
		if r.info() is None:
			return u""
		semne = []
		for cond, cheie in (("_is_uhd", "flag_uhd"), ("_is_fhd", "flag_fhd"), ("_is_hd", "flag_hd"), ("_is_sd", "flag_sd")):
			if getattr(self, cond)(r):
				semne.append(C.tr(cheie))
				break
		if self._is_169(r):
			semne.append(C.tr("flag_169"))
		elif self._is_43(r):
			semne.append(u"4:3")
		if self._is_hdr(r):
			semne.append(C.tr("flag_hdr"))
		semne.append(self._video_codec(r))
		for cond, cheie in (("_is_51", "flag_51"), ("_has_txt", "flag_txt"), ("_has_sub", "flag_sub"),
				("_has_hbbtv", "flag_hbbtv")):
			if getattr(self, cond)(r):
				semne.append(C.tr(cheie))
		return C.join(semne)

	def _hds_acces(self, r):
		if r.info() is None:
			return u""
		return C.access_head(r)

	def _hds_raspuns(self, r):
		"""CAID-ul si timpul raspunsului decodarii de acum (ca CryptoInfo,ShortInfo), numai cand e al canalului."""
		caid = C.ecm_active(r)
		if caid <= 0:
			return u""
		d = C.ecm_info()
		ms = d.get("ms", -1) if 0.0 <= time.time() - d.get("mtime", 0.0) <= C.ECM_FRESH_S else -1
		return C.join([u"CAID %04X" % caid, (u"%d ms" % ms) if ms >= 0 else u""])

	def _hds_toate(self, r):
		if r.info() is None:
			return u""
		acces = C.join([self._hds_acces(r), self._hds_raspuns(r)])
		imagine = C.join([self._video_codec(r), self._resolution(r), self._format(r), self._audio(r)])
		return u"\n".join([acces, imagine, self._tech_left(r)])
