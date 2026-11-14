# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptv4K: „Găsește canalele 4K reale” (Meniu > Setări > Surse Internet). Un singur ecran: starea (cate verificate din cate, cate 4K,
# cate HDR), bara de progres, apoi canalele 4K gasite si cate canale „4K” sunt de fapt HD. VERDE porneste (toti candidatii), ROSU
# opreste. Logica: Components/HdsIptv4K.py; pereche web: /iptv-4k (HdsWebControl/internet_web.py).

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components.ScrollLabel import ScrollLabel
from Components import HdsIptv4K as K
from Components import HdsIptvSurse as I


def textStare(st, rez):
	"""Randul de sus, acelasi in web (internet_web.stareIptv4k)."""
	if st.get("lucreaza"):
		return _("Se verifică %d din %d canale · 4K adevărat: %d · HDR: %d") % (st.get("facute", 0), st.get("total", 0),
			st.get("gasite", 0), st.get("hdr", 0))
	n4k = sum(1 for v in rez.values() if v and v[0] >= K.LATIME_4K)
	nhdr = sum(1 for v in rez.values() if v and len(v) > 3 and v[3])
	if not rez:
		return _("Nicio căutare încă. Apasă VERDE: receptorul citește câteva secunde din fiecare canal cu 4K, UHD sau HDR în nume.")
	text = _("Verificate: %d canale · 4K adevărat: %d · HDR: %d") % (len(rez), n4k, nhdr)
	if st.get("mesaj"):
		text += " · " + _(st["mesaj"])
	return text


def textLista(rez):
	"""Canalele 4K gasite (codecul, cadrele, HDR), apoi cate canale „4K” sunt de fapt HD."""
	buni, fals = [], 0
	for k, v in sorted(rez.items(), key=lambda kv: (kv[1][6] if len(kv[1]) > 6 else "")):
		if len(v) < 7:
			continue
		if v[0] >= K.LATIME_4K:
			buni.append("%s · %dx%d %s%s" % (v[6], v[0], v[1], v[2], (" · " + v[3]) if v[3] else ""))
		elif v[0]:
			fals += 1
	rand = [_("4K adevărat (și în lista de canale, grupa „4K adevărat”):")] + (buni or [_("niciunul")])
	if fals:
		rand += ["", _("%d canale au 4K în nume, dar trimit HD (semnul „de fapt 1080p” în listă).") % fals]
	return "\n".join(rand)


class HdsIptv4K(Screen):
	skin = """
	<screen name="HdsIptv4K" resolution="1920,1080" position="center,center" size="1500,820" title="Găsește canalele 4K reale">
		<widget name="stare" position="30,20" size="1440,80" font="Regular;30" />
		<widget name="bara" position="30,110" size="1440,14" foregroundColor="#004fd18b" backgroundColor="#002a3350" />
		<widget name="lista" position="30,145" size="1440,580" font="Regular;28" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,750" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="390,750" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Găsește canalele 4K reale"))
		self["stare"] = Label("")
		self["bara"] = ProgressBar()
		self["lista"] = ScrollLabel("")
		self["key_red"] = Button(_("Oprește"))
		self["key_green"] = Button(_("Pornește"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"cancel": self.close,
			"ok": self.porneste,
			"green": self.porneste,
			"red": self.opreste,
			"up": self["lista"].pageUp,
			"down": self["lista"].pageDown,
		}, -1)
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.improspateaza)
		self.onLayoutFinish.append(self.improspateaza)
		self.onClose.append(self.ceas.stop)
		self.ceas.start(1000, False)

	def porneste(self):
		if not I.areSurse():
			self["stare"].setText(_("Nu ai nicio sursă de televiziune prin internet."))
			return
		if K.omulSeUita():
			self["stare"].setText(_(K.T_OPRITA_PRIVIRE))
			return
		K.porneste(tot=not K.deContinuat())    # continua o cautare neterminata, ca in web
		self.improspateaza()

	def opreste(self):
		K.opreste()
		self.improspateaza()

	def improspateaza(self):
		st, rez = K.stare(), K.rezultate()
		self["stare"].setText(textStare(st, rez))
		total = st.get("total") or 0
		self["bara"].setValue(int(100 * st.get("facute", 0) / total) if total else 0)
		text = textLista(rez)
		if getattr(self, "_text", None) != text:
			self._text = text
			self["lista"].setText(text)
