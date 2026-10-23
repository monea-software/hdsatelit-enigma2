# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTemaInterfata: "Tema interfeței" (Meniu > Interfata si aspect), tema meniurilor de pe televizor: Clasic (aerisita,
# ca pana acum) sau Pro (densa, dupa ecranele Stitch ale temei Pro). Doua cartonase cu previzualizare; Stanga / Dreapta
# aleg, Verde sau OK aplica, Galben aduce cursorul pe tema implicita (Clasic), Rosu sau EXIT inchide fara schimbare.
# Aplicarea scrie setarea (config.skin.tema_tv) si intreaba daca interfata se reporneste acum, pe calea sigura
# (TryQuitMainloop 3, ca "Repornește interfața" din meniu): skinul se citeste numai la pornire. Logica e in
# Components/HdsTemaTv.py, aceeasi cu pagina web /tema-tv. Tema de aici NU schimba tema interfetei web (alta setare).
#
# Skinul: HdsTemaInterfata din skin.xml (Clasic) si din skin_pro.xml (Pro); pe alt skin, rezerva de mai jos, pe 1280.
# Tema e a skinului HDSatelit: cu alt skin ales, mesajul spune de ce nu se poate alege (HdsTemaTv.textAltSkin).

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components import HdsTemaTv as T
from Tools.ScaledSkin import scaledSkin

SKIN_REZERVA = """
<screen name="HdsTemaInterfata" position="48,27" size="1184,666" backgroundColor="#0D10162A" flags="wfNoBorder" title="Tema interfeței">
	<eLabel position="0,0" size="1184,1" backgroundColor="#99FFFFFF" zPosition="1" />
	<widget source="Title" render="Label" position="21,12" size="1024,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget source="global.CurrentTime" render="Label" position="1056,12" size="107,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" zPosition="1">
		<convert type="ClockToText">Format:%H:%M</convert>
	</widget>
	<eLabel position="21,59" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<widget name="subtitlu" position="21,69" size="700,32" font="Regular;21" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="indiciu" position="730,69" size="432,32" font="Regular;17" foregroundColor="#00AEB9CC" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" noWrap="1" zPosition="1" />
	<widget name="chenar_clasic_sus" position="21,109" size="565,3" backgroundColor="#009FB4FF" zPosition="3" />
	<widget name="chenar_clasic_jos" position="21,437" size="565,3" backgroundColor="#009FB4FF" zPosition="3" />
	<widget name="chenar_clasic_st" position="21,109" size="3,331" backgroundColor="#009FB4FF" zPosition="3" />
	<widget name="chenar_clasic_dr" position="583,109" size="3,331" backgroundColor="#009FB4FF" zPosition="3" />
	<widget name="nume_clasic" position="37,117" size="300,40" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="2" />
	<widget name="stare_clasic" position="340,117" size="230,40" font="Regular;16" foregroundColor="#004FD18B" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" noWrap="1" zPosition="2" />
	<widget name="scurt_clasic" position="37,157" size="533,27" font="Regular;17" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="2" />
	<ePixmap pixmap="tema/clasic.jpg" position="37,189" size="533,160" zPosition="2" />
	<widget name="descriere_clasic" position="37,355" size="533,77" font="Regular;16" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" zPosition="2" />
	<widget name="chenar_pro_sus" position="597,109" size="565,3" backgroundColor="#009FB4FF" zPosition="3" />
	<widget name="chenar_pro_jos" position="597,437" size="565,3" backgroundColor="#009FB4FF" zPosition="3" />
	<widget name="chenar_pro_st" position="597,109" size="3,331" backgroundColor="#009FB4FF" zPosition="3" />
	<widget name="chenar_pro_dr" position="1159,109" size="3,331" backgroundColor="#009FB4FF" zPosition="3" />
	<widget name="nume_pro" position="613,117" size="300,40" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="2" />
	<widget name="stare_pro" position="916,117" size="230,40" font="Regular;16" foregroundColor="#004FD18B" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" noWrap="1" zPosition="2" />
	<widget name="scurt_pro" position="613,157" size="533,27" font="Regular;17" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="2" />
	<ePixmap pixmap="tema/pro.jpg" position="613,189" size="533,160" zPosition="2" />
	<widget name="descriere_pro" position="613,355" size="533,77" font="Regular;16" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" zPosition="2" />
	<widget name="nota" position="21,453" size="1141,53" font="Regular;17" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
	<widget name="mesaj" position="21,509" size="1141,53" font="Regular;17" foregroundColor="#00F5B83D" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
	<eLabel position="21,616" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<eLabel position="21,629" size="4,21" backgroundColor="#00E5484D" zPosition="1" />
	<widget name="key_red" position="32,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="307,629" size="4,21" backgroundColor="#0046B06A" zPosition="1" />
	<widget name="key_green" position="317,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="592,629" size="4,21" backgroundColor="#00E8B93A" zPosition="1" />
	<widget name="key_yellow" position="603,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
</screen>"""

CHENARE = ("sus", "jos", "st", "dr")


class HdsTemaInterfata(Screen):
	"""Tema interfetei de pe televizor: Stanga / Dreapta alege, Verde sau OK aplica."""

	def __init__(self, session):
		self.skin = scaledSkin(SKIN_REZERVA)
		Screen.__init__(self, session)
		self.skinName = ["HdsTemaInterfata"]
		self.setTitle(_("Tema interfeței"))
		self["subtitlu"] = Label(_("Alege cum arată meniurile pe televizor"))
		self["indiciu"] = Label(_("Stânga și Dreapta aleg tema"))
		for t in T.TEME:
			self["nume_" + t] = Label(_(T.NUME[t]))
			self["stare_" + t] = Label("")
			self["scurt_" + t] = Label(_(T.SCURT[t]))
			self["descriere_" + t] = Label(_(T.DESCRIERE[t]))
			for c in CHENARE:
				self["chenar_%s_%s" % (t, c)] = Label("")
		self["nota"] = Label(_("Tema de pe televizor e separată de tema interfeței web: aceea se alege în browser, la Setări, și rămâne cum e."))
		self["mesaj"] = Label("")
		self["key_red"] = Label(_("Renunță"))
		self["key_green"] = Label(_("Aplică"))
		self["key_yellow"] = Label(_("Implicită (Clasic)"))
		actiuni = {
			"ok": self.aplica,
			"green": self.aplica,
			"cancel": self.close,
			"red": self.close,
			"yellow": self.implicita,
			"left": self.stanga,
			"right": self.dreapta,
		}
		# celelalte actiuni din DirectionActions (sus, jos, tasta tinuta, tasta ridicata) nu fac nimic aici; fara ele
		# jurnalul scrie "unknown action DirectionActions/rightUp" la fiecare apasare
		for nume in ("up", "down", "upRepeated", "downRepeated", "leftRepeated", "rightRepeated", "upUp", "downUp",
				"leftUp", "rightUp"):
			actiuni[nume] = self.nimic
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni, -1)
		self.cursor = T.aleasa()
		self.onLayoutFinish.append(self.arata)
		getattr(self, "onLayoutFinish", []).append(self._descrieriMarite)

	def _descrieriMarite(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): descrierea de sub poza fiecarei teme are
		loc de doua randuri, intre poza si chenarul de jos (la 115 % al treilea rand, "legenda tastelor jos.", se pierdea).
		Fontul descrierii scade cu cate un pixel pana cand ea incape, dar nu sub marimea de la 100 %, la care incape.
		La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			for t in T.NUME:
				w = self.get("descriere_" + t)
				if w is not None and w.instance is not None:
					MT.potrivesteFont(w.instance, w.instance.size().height(), MT.marimeFont(w.instance))
		except Exception as e:
			print("[HdsTemaInterfata] textul marit: %s" % e)

	def arata(self):
		s = T.stare(traducere=_)
		for tema in s["teme"]:
			t = tema["id"]
			if not tema["disponibila"]:
				text = _("Lipsește din skin")
			elif tema["activa"] and tema["aleasa"]:
				text = _("Tema de acum")
			elif tema["aleasa"]:
				text = _("Aleasă, după repornire")
			elif tema["activa"]:
				text = _("Pe ecran până la repornire")
			else:
				text = ""
			self["stare_" + t].setText(text)
			for c in CHENARE:
				w = self["chenar_%s_%s" % (t, c)]
				if t == self.cursor:
					w.show()
				else:
					w.hide()
		if not s["skin_imaginii"]:
			self["mesaj"].setText(s["nota_skin"])
		elif s["repornire"]:
			self["mesaj"].setText(_("Tema %s se vede după repornirea interfeței.") % _(T.NUME[s["aleasa"]]))
		elif not s["pro_disponibil"]:
			self["mesaj"].setText(_("Tema Pro lipsește din skinul instalat. Actualizează skinul HDSatelit."))
		else:
			self["mesaj"].setText(_("Tema nouă se vede după repornirea interfeței: câteva secunde, receptorul nu se oprește."))

	def nimic(self):
		pass

	def stanga(self):
		self.cursor = T.TEME[0]
		self.arata()

	def dreapta(self):
		self.cursor = T.TEME[-1]
		self.arata()

	def implicita(self):
		self.cursor = T.IMPLICITA
		self.arata()

	def aplica(self):
		tema = self.cursor
		if tema == T.aleasa() and tema == T.activa():
			self.close(False)
			return
		bun, mesaj, schimbata = T.seteaza(tema, traducere=_)
		if not bun:
			self["mesaj"].setText(mesaj)
			return
		self.arata()
		if not schimbata:
			self["mesaj"].setText(mesaj)
			return
		self.session.openWithCallback(self.reporneste, MessageBox,
			_("Tema %s se vede după repornirea interfeței. O repornești acum? Receptorul nu se oprește; interfața pornește "
				"din nou în câteva secunde, pe același canal.") % _(T.NUME[tema]), MessageBox.TYPE_YESNO)

	def reporneste(self, da=False):
		if da:
			from Screens.Standby import TryQuitMainloop
			self.session.open(TryQuitMainloop, 3)
		else:
			self.arata()
