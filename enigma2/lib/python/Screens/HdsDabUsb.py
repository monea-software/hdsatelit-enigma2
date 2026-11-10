# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDabUsb.py: intrarea „Radio DAB+ prin USB” din Scanare. Cu pluginul DabTerestru instalat se deschide direct ecranul lui. Fara el se
# deschide ecranul de aici: starea stickului si, cu un singur OK, pregatirea (descarca si instaleaza programul de receptie). La sfarsitul
# instalarii ecranul se inlocuieste singur cu al pluginului, fara repornire.
# Tot lucrul e in Components/HdsDabUsb.py, acelasi cu al paginii web /dab-terestru; aici se arata numai starea, de doua ori pe secunda.
from enigma import eTimer

from Components import HdsDabUsb as D
from Components.ActionMap import ActionMap
from Components.Label import Label
from Screens.Screen import Screen
from Tools.ScaledSkin import scaledSkin

SKIN = """<screen name="HdsDabUsbPregatire" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000A0F1A">
	<eLabel position="96,54" size="1728,80" backgroundColor="#0010162A" zPosition="1" />
	<eLabel position="96,132" size="1728,2" backgroundColor="#00374EA1" zPosition="2" />
	<eLabel text="HD SATELIT" position="128,74" size="180,40" font="{fBold};24" foregroundColor="#00FFFFFF" backgroundColor="#00374EA1" halign="center" valign="center" zPosition="2" />
	<widget name="titlu" position="330,60" size="1300,68" font="{fBold};46" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="2" />
	<eLabel position="96,180" size="1728,160" backgroundColor="#002A3350" zPosition="1" />
	<eLabel position="98,182" size="1724,156" backgroundColor="#0010162A" zPosition="2" />
	<widget name="stickBara" position="96,180" size="8,160" backgroundColor="#00667085" zPosition="3" />
	<widget name="stickNume" position="136,196" size="1380,60" font="{fBold};40" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="3" />
	<widget name="stickRand" position="136,262" size="1650,60" font="{fRegular};30" foregroundColor="#00C9D2E3" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="3" />
	<widget name="stickStare" position="1540,204" size="250,48" font="{fBold};28" foregroundColor="#000A0F1A" backgroundColor="#00667085" halign="center" valign="center" noWrap="1" zPosition="3" />
	<eLabel position="96,380" size="1728,300" backgroundColor="#002A3350" zPosition="1" />
	<eLabel position="98,382" size="1724,296" backgroundColor="#0010162A" zPosition="2" />
	<widget name="pregTitlu" position="136,400" size="1650,60" font="{fBold};40" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="3" />
	<widget name="pregText" position="136,470" size="1650,190" font="{fRegular};32" foregroundColor="#00C9D2E3" backgroundColor="#0010162A" valign="top" zPosition="3" />
	<eLabel position="96,930" size="1728,2" backgroundColor="#002A3350" zPosition="1" />
	<eLabel text="OK" position="124,954" size="62,40" font="{fRegular};24" foregroundColor="#00F2F4F8" backgroundColor="#002A3350" halign="center" valign="center" zPosition="2" />
	<widget name="tOk" position="196,950" size="760,48" font="{fRegular};30" foregroundColor="#00F2F4F8" backgroundColor="#000A0F1A" valign="center" noWrap="1" zPosition="2" />
	<eLabel text="EXIT" position="1540,954" size="82,40" font="{fRegular};24" foregroundColor="#00F2F4F8" backgroundColor="#002A3350" halign="center" valign="center" zPosition="2" />
	<widget name="tExit" position="1632,950" size="192,48" font="{fRegular};30" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" valign="center" noWrap="1" zPosition="2" />
</screen>"""

CULORI = {"bun": 0x4FD18B, "galben": 0xF1C40F, "rau": 0xFF6B5E}


def _nume_font(nume):
	try:
		from skin import fontHds
		return fontHds(nume)
	except Exception:
		return nume


def _ecranPlugin():
	"""Clasa ecranului pluginului, sau None cand pluginul lipseste ori nu se incarca."""
	if not D.plugin_instalat():
		return None
	try:
		from Plugins.Extensions.DabTerestru.ecran import DabTerestru
		return DabTerestru
	except Exception as e:
		print("[HdsDabUsb] pluginul nu se incarca: %s: %s" % (type(e).__name__, e))
		return None


def HdsDabUsb(session, *argumente):
	"""Ce deschide meniul: ecranul pluginului, daca e, altfel pregatirea."""
	ecran = _ecranPlugin()
	return ecran(session) if ecran is not None else HdsDabUsbPregatire(session)


class HdsDabUsbPregatire(Screen):
	ALLOW_SUSPEND = True

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skin = scaledSkin(SKIN.format(fRegular=_nume_font("Regular"), fBold=_nume_font("Bold")), 1920)
		self["titlu"] = Label(_("Radio DAB+ prin USB"))
		self["stickBara"] = Label("")
		self["stickNume"] = Label("")
		self["stickRand"] = Label("")
		self["stickStare"] = Label("")
		self["pregTitlu"] = Label(_("Pregătește recepția DAB+"))
		self["pregText"] = Label("")
		self["tOk"] = Label("")
		self["tExit"] = Label(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions"], {"ok": self.keyOk, "cancel": self.close}, -1)
		self.culoare = None
		self.deschis = False
		self.tCeas = eTimer()
		self.tCeas.callback.append(self._arata)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self.tCeas.stop)

	def _porneste(self):
		D.pregatire().verifica()
		self._arata()
		self.tCeas.start(500)

	def _coloreaza(self, culoare):
		if culoare == self.culoare:
			return
		self.culoare = culoare
		from enigma import gRGB
		for w in ("stickBara", "stickStare"):
			inst = self[w].instance
			if inst is not None:
				inst.setBackgroundColor(gRGB(CULORI.get(culoare, 0x667085)))
				inst.invalidate()

	def _arata(self):
		fel, stick = D.fel_stare(D.inventar())
		t = D.text_stare(fel, stick)
		self["stickNume"].setText(t["titlu"])
		self["stickRand"].setText(t["rand"])
		self["stickStare"].setText(t["eticheta"])
		self._coloreaza(t["culoare"])
		s = D.pregatire().stare()
		if s["faza"] == "gata":
			self._laPlugin()
			return
		text, ok = s["text"], ""
		if s["faza"] == "de_instalat":
			text = "%s\n%s" % (s["text"], _("Se instalează o singură dată. Mărime: %s.") % _marime(s["marime"]))
			ok = _("Pregătește recepția DAB+")
		elif s["faza"] in ("lipsa", "eroare"):
			ok = _("Încearcă din nou")
		elif s["faza"] == "instalare" and s["pas"]:
			text = "%s\n%s" % (s["text"], s["pas"])
		self["pregText"].setText(text)
		self["tOk"].setText(ok)

	def _laPlugin(self):
		if self.deschis:
			return
		ecran = _ecranPlugin()
		if ecran is None:
			self["pregText"].setText(_("Instalarea s-a terminat, dar programul nu pornește. Repornește interfața."))
			self["tOk"].setText("")
			return
		self.deschis = True
		self.tCeas.stop()
		self.session.openWithCallback(self.close, ecran)

	def keyOk(self):
		P = D.pregatire()
		s = P.stare()
		if s["faza"] == "de_instalat":
			P.instaleaza()
		elif s["faza"] in ("lipsa", "eroare", "nimic"):
			P.verifica(True)
		self._arata()


def _marime(octeti):
	try:
		from Components.HdsPachete import marime_text
		return marime_text(octeti) or _("necunoscută")
	except Exception:
		return _("necunoscută")
