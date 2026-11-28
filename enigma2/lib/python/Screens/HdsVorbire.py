# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
from Screens.Screen import Screen
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.Sources.CanvasSource import CanvasSource
from Components.ActionMap import ActionMap
from Components.config import getConfigListEntry
from Components import HdsVorbire as V
import re


class HdsVorbire(Screen, ConfigListScreen):
	def __init__(self, session):
		self.skin = '''<screen position="center,center" size="1080,670" title="Subtitrări din vorbire">
<widget name="config" position="25,50" size="730,180" scrollbarMode="showOnDemand" />
<widget source="qr" render="Canvas" position="790,50" size="260,260" />
<widget source="stare" render="Label" position="25,236" size="730,90" font="Regular;24" foregroundColor="#00f0c674" />
<widget source="ajutor" render="Label" position="25,330" size="1030,240" font="Regular;22" />
<widget source="adresa" render="Label" position="25,575" size="1030,40" font="Regular;25" />
<widget source="jos" render="Label" position="25,620" size="1030,40" font="Regular;25" />
</screen>'''
		from enigma import getDesktop
		marime = getDesktop(0).size()
		scara = min(1.0, (marime.width() - 40) / 1080.0, (marime.height() - 40) / 670.0)
		self.skin = re.sub(r'(position|size)="([0-9]+),([0-9]+)"', lambda m:
			'%s="%d,%d"' % (m[1], int(int(m[2]) * scara), int(int(m[3]) * scara)), self.skin)
		self.skin = self.skin.replace("Regular;25", "Regular;%d" % max(16, int(25 * scara)))
		self.skin = self.skin.replace("Regular;24", "Regular;%d" % max(15, int(24 * scara)))
		self.skin = self.skin.replace("Regular;22", "Regular;%d" % max(14, int(22 * scara)))
		Screen.__init__(self, session)
		self.setTitle(_("Subtitrări din vorbire"))
		s = self.ciorna = V.ciorna()
		self.initiale = self.valori()
		self.salvare = None
		self.asteaptaCheia = False
		from enigma import eTimer
		self.timerSalvare = eTimer()
		self.timerSalvare.callback.append(self.dupaSalvare)
		self.onClose.append(self.timerSalvare.stop)
		self.timerCheie = eTimer()
		self.timerCheie.callback.append(self.verificaCheia)
		self.onClose.append(self.timerCheie.stop)
		ConfigListScreen.__init__(self, [getConfigListEntry(_("Subtitrări din vorbire"), s.pornit),
			getConfigListEntry(_("Serviciul care ascultă"), s.serviciu), getConfigListEntry(_("Limba textului"), s.limba)], session=session)
		self["qr"] = CanvasSource()
		self["stare"] = StaticText("")
		self["ajutor"] = StaticText(_("Scanează codul cu telefonul. Pe pagina deschisă alegi Gemini (gratuit, fără card), îți faci cheia și o lipești acolo. Subtitrările pornesc singure.") + "\n\n" + V.confidentialitate())
		self["adresa"] = StaticText("http://hdsatelit.local/vorbire")
		self["jos"] = StaticText(_("Verde: salvează. Galben: cheile traducerii. Ieșire: renunță."))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {"ok": self.salveaza,
			"green": self.salveaza, "yellow": self.chei, "cancel": self.anuleaza}, -1)
		self.onLayoutFinish.append(self.qr)
		self.verificaCheia()
		self.timerCheie.start(1000)

	def qr(self):
		from Screens.HdsTraducereSubtitrari import _deseneazaQr
		_deseneazaQr(self, "qr", "http://hdsatelit.local/vorbire")

	def chei(self):
		from Screens.HdsTraducereSubtitrari import HdsTraducereSubtitrari
		self.session.open(HdsTraducereSubtitrari)

	def valori(self):
		return dict((k, getattr(self.ciorna, k).value) for k in ("pornit", "serviciu", "limba"))

	def areCheie(self):
		return any(V.cheiPuse().values())

	def verificaCheia(self):
		# The key comes from the phone page; the screen follows the key store, not the TV loop copy.
		if self.areCheie():
			if self.asteaptaCheia:
				self.close()
				return
			self["stare"].setText(_("Cheia e pusă: subtitrările din vorbire pot porni."))
		elif self.asteaptaCheia:
			self["stare"].setText(_("Lipsește cheia: scanează codul și lipește cheia pe telefon. Ecranul se închide singur când vine cheia."))
		else:
			self["stare"].setText(_("Lipsește cheia: scanează codul și lipește cheia pe telefon."))

	def salveaza(self):
		if self.salvare:
			return
		# Only what was changed here: the phone page may have turned speech on with the service of the new key.
		valori = dict((k, v) for k, v in self.valori().items() if v != self.initiale[k])
		if not valori:
			self.gata()
			return
		self.salvare = V.salveaza(valori)
		if self.salvare:
			self["jos"].setText(_("Se salvează setările."))
			self.timerSalvare.start(100)
		else:
			self["jos"].setText(V.stareSalvare()["mesaj_salvare"] or _("Se salvează setările."))

	def dupaSalvare(self):
		if not self.salvare or not self.salvare["gata"]:
			return
		self.timerSalvare.stop()
		if self.salvare["ok"]:
			self.salvare = None
			self.initiale = self.valori()
			self.gata()
		else:
			self.salvare = None
			self["jos"].setText(_("Setările nu s-au putut salva. Încearcă din nou."))

	def gata(self):
		# Speech on without a key: stay on the code and close by itself when the key arrives.
		if V.initConfig().pornit.value and not self.areCheie():
			self.asteaptaCheia = True
			self["jos"].setText(_("Verde: salvează. Galben: cheile traducerii. Ieșire: renunță."))
			self.verificaCheia()
			return
		self.close()

	def anuleaza(self):
		if not self.salvare:
			self.close()
