# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Intrarea Radio online: acordul de instalare, progresul si lista pluginului."""
from enigma import eTimer

from Components import HdsRadioOnline as R
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.ScaledSkin import scaledSkin


SKIN = """<screen name="HdsRadioOnline" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000A0F1A">
	<eLabel position="96,54" size="1728,80" backgroundColor="#0010162A" zPosition="1" />
	<eLabel position="96,132" size="1728,2" backgroundColor="#00374EA1" zPosition="2" />
	<eLabel text="HD SATELIT" position="128,74" size="180,40" font="{fBold};24" foregroundColor="#00FFFFFF" backgroundColor="#00374EA1" halign="center" valign="center" zPosition="2" />
	<widget name="titlu" position="330,60" size="1300,68" font="{fBold};46" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="2" />
	<eLabel position="96,300" size="1728,380" backgroundColor="#002A3350" zPosition="1" />
	<eLabel position="98,302" size="1724,376" backgroundColor="#0010162A" zPosition="2" />
	<widget name="text" position="136,340" size="1648,150" font="{fBold};40" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" zPosition="3" />
	<widget name="pas" position="136,510" size="1648,90" font="{fRegular};30" foregroundColor="#00C9D2E3" backgroundColor="#0010162A" valign="center" zPosition="3" />
	<widget name="progres" position="136,626" size="1648,12" borderWidth="0" foregroundColor="#009FB4FF" backgroundColor="#002A3350" zPosition="3" />
	<eLabel position="96,930" size="1728,2" backgroundColor="#002A3350" zPosition="1" />
	<widget name="tOk" position="128,950" size="1120,60" font="{fRegular};30" foregroundColor="#00F2F4F8" backgroundColor="#000A0F1A" valign="center" noWrap="1" zPosition="2" />
	<widget name="tExit" position="1300,950" size="484,60" font="{fRegular};30" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" halign="right" valign="center" noWrap="1" zPosition="2" />
</screen>"""


def _nume_font(nume):
	try:
		from skin import fontHds
		return fontHds(nume)
	except Exception:
		return nume


class HdsRadioOnline(Screen):
	ALLOW_SUSPEND = True

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skin = scaledSkin(SKIN.format(fRegular=_nume_font("Regular"), fBold=_nume_font("Bold")), 1920)
		self["titlu"] = Label(_("Radio online"))
		self["text"] = Label(_("Posturi de radio de pe internet"))
		self["pas"] = Label("")
		self["progres"] = ProgressBar()
		self["tOk"] = Label("")
		self["tExit"] = Label(_("EXIT: Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions"], {"ok": self.keyOk, "cancel": self.close}, -1)
		self.deschis = False
		self.intrebare = False
		self.inchis = False
		self.eroare_deschidere = False
		self._puls = 0
		self.tCeas = eTimer()
		self.tCeas.callback.append(self._arata)
		# Session permite un dialog modal abia dupa activarea ecranului.
		self.onFirstExecBegin.append(self._porneste)
		self.onClose.append(self._inchide)

	def _porneste(self):
		stare = R.pregatire().stare()
		if stare["faza"] == "gata":
			self._laPlugin()
			return
		if stare["faza"] in R.FAZE_ACTIVE:
			self._arata()
			self.tCeas.start(250)
		else:
			self._intreaba()

	def _intreaba(self):
		if self.intrebare or self.inchis:
			return
		self.intrebare = True
		self.session.openWithCallback(self._raspuns, MessageBox, R.text_confirmare(),
			type=MessageBox.TYPE_YESNO, default=False, title=_("Radio online"))

	def _raspuns(self, da):
		self.intrebare = False
		if self.inchis:
			return
		if not da:
			self.close()
			return
		R.pregatire().verifica(True)
		self._arata()
		if not self.deschis:
			self.tCeas.start(250)

	def _arata(self):
		if self.inchis or self.deschis or self.intrebare or self.eroare_deschidere:
			return
		stare = R.pregatire().stare()
		if stare["faza"] == "gata":
			self._laPlugin()
			return
		self["text"].setText(stare["text"])
		self["pas"].setText(stare.get("pas", ""))
		activ = stare["faza"] in R.FAZE_ACTIVE
		if activ:
			# Indicator de activitate: nu afisam un procent pe care instalatorul nu-l masoara.
			self._puls = (self._puls + 9) % 90
			self["progres"].setValue(10 + self._puls)
			self["progres"].show()
		else:
			self["progres"].hide()
		self["tOk"].setText(_("OK: Încearcă din nou") if stare["faza"] in ("lipsa", "eroare") else "")

	def _laPlugin(self):
		if self.deschis or self.inchis:
			return
		try:
			from Plugins.Extensions.RadioOnline import ecran, web
			# Pagina porneste si dupa instalarea fara repornirea interfetei.
			web.porneste(self.session)
			lista = ecran.deschide(self.session)
			lista.onClose.append(self._dupaPlugin)
			self.deschis = True
			self.tCeas.stop()
		except Exception as e:
			print("[HdsRadioOnline] deschiderea listei: %s" % type(e).__name__)
			self.eroare_deschidere = True
			self.tCeas.stop()
			self["progres"].hide()
			self["text"].setText(_("Radio online nu poate porni acum. Încearcă din nou."))
			self["pas"].setText("")
			self["tOk"].setText(_("OK: Încearcă din nou"))

	def _dupaPlugin(self):
		self.close()

	def keyOk(self):
		if self.deschis or self.inchis or self.intrebare:
			return
		if self.eroare_deschidere:
			self.eroare_deschidere = False
			self._laPlugin()
			return
		if R.pregatire().stare()["faza"] in ("nimic", "lipsa", "eroare", "de_instalat"):
			self._intreaba()

	def _inchide(self):
		self.inchis = True
		self.tCeas.stop()
