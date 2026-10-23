# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFontInterfata: "Fontul interfetei" (Meniu > Interfata si aspect). In stanga familiile livrate cu imaginea (cea
# folosita acum si cele fara literele limbii meniului sunt scrise in dreptul lor), in dreapta proba familiei de sub
# cursor (titlu, text, cifre, litere, randul ales, eticheta si valoare), desenata cu fisierele ei, fara sa schimbe
# interfata; jos descrierea, licenta, literele, marimea pe disc. Verde (sau OK) foloseste familia: se aplica pe loc
# ecranelor deschise de acum si ramane la pornire. Galben deschide Fonturile Google (descarcarea altor fonturi).
# Logica e in Components/HdsFontInterfata.py, aceeasi cu pagina web /font-interfata.
#
# Skinul: HdsFontInterfata din skin.xml (cadrul HdsCadru1776); pe alt skin, rezerva de mai jos, pe 1280, scalata.

from enigma import eListboxPythonMultiContent, getDesktop, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components import HdsFontInterfata as F
from Components import HdsMarimeText as T
from Components import HdsMarireText as MT
from Tools.ScaledSkin import scaledSkin

SKIN_REZERVA = """
<screen name="HdsFontInterfata" position="48,27" size="1184,666" backgroundColor="#0D10162A" flags="wfNoBorder" title="Fontul interfeței">
	<eLabel position="0,0" size="1184,1" backgroundColor="#99FFFFFF" zPosition="1" />
	<widget source="Title" render="Label" position="21,12" size="1024,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget source="global.CurrentTime" render="Label" position="1056,12" size="107,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" zPosition="1">
		<convert type="ClockToText">Format:%H:%M</convert>
	</widget>
	<eLabel position="21,59" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<widget name="lista" position="21,69" size="427,384" itemHeight="48" backgroundColor="#0D10162A" backgroundColorSelected="#00374EA1" foregroundColor="#00F2F4F8" foregroundColorSelected="#00FFFFFF" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
	<eLabel position="459,69" size="1,384" backgroundColor="#D9FFFFFF" zPosition="1" />
	<widget name="proba_titlu" position="469,69" size="693,43" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="proba_text" position="469,117" size="693,75" font="Regular;21" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
	<widget name="proba_cifre" position="469,197" size="693,37" font="Regular;21" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="proba_mic" position="469,240" size="693,29" font="Regular;16" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="469,277" size="693,40" backgroundColor="#00374EA1" zPosition="1" />
	<widget name="proba_ales" position="485,277" size="661,40" font="Regular;21" foregroundColor="#00FFFFFF" backgroundColor="#00374EA1" transparent="1" valign="center" noWrap="1" zPosition="2" />
	<widget name="proba_setare" position="469,323" size="440,40" font="Regular;21" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="proba_valoare" position="917,323" size="245,40" font="Bold;20" foregroundColor="#009FB4FF" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="21,477" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<widget name="descriere" position="21,485" size="1141,72" font="Regular;19" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
	<widget name="detalii" position="21,560" size="1141,23" font="Regular;16" foregroundColor="#00AEB9CC" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="stare" position="21,584" size="1141,27" font="Regular;16" foregroundColor="#00F5B83D" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="21,616" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<eLabel position="21,629" size="4,21" backgroundColor="#00E5484D" zPosition="1" />
	<widget name="key_red" position="32,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="307,629" size="4,21" backgroundColor="#0046B06A" zPosition="1" />
	<widget name="key_green" position="317,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="592,629" size="4,21" backgroundColor="#00E8B93A" zPosition="1" />
	<widget name="key_yellow" position="603,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
</screen>"""

# proba: (eticheta, rolul fontului, marimea la 1920, textul); textele sunt cele din "Marimea textului"
PROBA = (
	("proba_titlu", "bold", 40, T.PROBA[0][3]),
	("proba_text", "regular", 32, T.PROBA[1][3]),
	("proba_cifre", "regular", 32, "0123456789 · 20:15 · 87%"),
	("proba_mic", "cond", 24, T.PROBA[5][3]),
	("proba_ales", "regular", 32, T.PROBA[2][3]),
	("proba_setare", "regular", 32, T.PROBA[3][3]),
	("proba_valoare", "bold", 30, T.PROBA[4][3]),
)

CULORI = {"text": ("hdsText", 0xF2F4F8), "ales": ("hdsAmber", 0xF5B83D), "stins": ("hdsDisabled", 0x667085),
	"selectat": ("hdsSelText", 0xFFFFFF)}


def _factor():
	try:
		w = getDesktop(0).size().width()
		if w > 0:
			return w / 1920.0
	except Exception:
		pass
	return 1.0


def _culoare(cheie):
	nume, implicit = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			v = c.argb()
			return v & 0xFFFFFF if (v >> 24) == 0 else v
	except Exception:
		pass
	return implicit


class HdsFontInterfata(Screen):
	"""Fontul interfetei: Sus / Jos alege familia, proba se schimba pe loc, Verde o foloseste."""

	def __init__(self, session):
		self.skin = scaledSkin(SKIN_REZERVA)
		Screen.__init__(self, session)
		self.skinName = ["HdsFontInterfata"]
		self.setTitle(_("Fontul interfeței"))
		self.factor = _factor()
		self.limba = F.codLimba()
		self.acum = F.ales()
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
		for cheie, _rol, _baza, text in PROBA:
			self[cheie] = Label(_(text))
		self["descriere"] = Label("")
		self["detalii"] = Label("")
		self["stare"] = Label(_("Sus și Jos aleg fontul; proba din dreapta îl arată înainte să-l folosești."))
		self["key_red"] = Label(_("Renunță"))
		self["key_green"] = Label(_("Folosește fontul"))
		self["key_yellow"] = Label(_("Fonturi Google"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.foloseste,
			"green": self.foloseste,
			"cancel": self.close,
			"red": self.close,
			"yellow": self.fonturiGoogle,
		}, -1)
		self["lista"].onSelectionChanged.append(self.arata)
		self.onLayoutFinish.append(self.pregateste)

	def pregateste(self):
		lista = self["lista"]
		# fonturile puse din cod urmeaza Marimea textului (Components/HdsMarireText), iar cu textul marit randul creste
		# odata cu ele (_inaltime; la 100 % aceleasi numere)
		lista.l.setFont(0, MT.fontCod("Regular", int(32 * self.factor)))
		lista.l.setFont(1, MT.fontCod("Fixed", int(24 * self.factor)))
		# numele fiecarei familii scris cu fontul ei (fonturile 2, 3...; aliasurile de proba, fara sa schimbe interfata)
		for i, f in enumerate(F.FAMILII):
			lista.l.setFont(2 + i, MT.fontCod(F.aliasProba(f["id"], "regular") or "Regular", int(32 * self.factor)))
		lista.l.setItemHeight(self._inaltime())
		MT.randuriCod(lista, self._inaltime())
		try:
			self.latime = lista.instance.size().width()
		except Exception:
			self.latime = int(640 * self.factor)
		self.reface()
		for i, f in enumerate(F.FAMILII):
			if f["id"] == self.acum:
				lista.moveToIndex(i)
		self.arata()

	def _inaltime(self):
		return MT.inaltimeCod(int(72 * self.factor))

	def _rand(self, i, f):
		w, h = self.latime, self._inaltime()
		if f["id"] == self.acum:
			stare, culoare = _("folosit acum"), _culoare("ales")
		elif not F.potrivit(f["id"], self.limba):
			stare, culoare = _("fără literele limbii"), _culoare("stins")
		else:
			stare, culoare = "", _culoare("text")
		dreapta = int(w * 0.45)
		return [f["id"],
			MultiContentEntryText(pos=(int(24 * self.factor), 0), size=(w - dreapta - int(24 * self.factor), h), font=2 + i,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=f["nume"], color=_culoare("text"), color_sel=_culoare("selectat")),
			MultiContentEntryText(pos=(w - dreapta, 0), size=(dreapta - int(16 * self.factor), h), font=1,
				flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=stare, color=culoare, color_sel=_culoare("selectat")),
		]

	def reface(self):
		idx = self["lista"].getSelectionIndex() or 0
		self["lista"].setList([self._rand(i, f) for i, f in enumerate(F.FAMILII)])
		self["lista"].moveToIndex(min(idx, len(F.FAMILII) - 1))

	def _ales(self):
		i = self["lista"].getSelectionIndex()
		if i is None or i < 0 or i >= len(F.FAMILII):
			return F.FAMILII[0]
		return F.FAMILII[i]

	def arata(self):
		f = self._ales()
		for cheie, rol, baza, text in PROBA:
			eticheta = self[cheie]
			if eticheta.instance is None:
				continue
			alias = F.aliasProba(f["id"], rol)
			# fontul inaintea textului: setText redeseneaza cu fontul pus atunci; marimea ca a textelor din skin, cu
			# Marimea textului (proba arata fontul asa cum va fi in interfata)
			eticheta.instance.setFont(MT.fontCod(alias or "Regular", int(round(baza * self.factor))))
			eticheta.setText(_(text))
		self["descriere"].setText(_(f["descriere"]))
		self["detalii"].setText(_("Licență: %(licenta)s · Litere: %(litere)s · Pe disc: %(marime)s · De la: %(autor)s") % {
			"licenta": "SIL Open Font License 1.1", "litere": F.textLitere(f["id"], _),
			"marime": F.textMarime(F.marime(f["id"])), "autor": f["autor"]})

	def foloseste(self):
		f = self._ales()
		if f["id"] == self.acum:
			self.close(False)
			return
		bun, rezultat = F.seteaza(f["id"], limba=self.limba)
		if not bun:
			self["stare"].setText(_(rezultat))
			return
		self.acum = f["id"]
		self.reface()
		self.session.openWithCallback(lambda *a: self.close(True), MessageBox,
			_("Fontul interfeței e acum %s. Ecranele pe care le deschizi de acum îl folosesc; meniul din spate se schimbă "
				"când îl deschizi din nou.") % rezultat, MessageBox.TYPE_INFO, timeout=8)

	def fonturiGoogle(self):
		from Screens.HdsFonturi import HdsFonturi
		self.session.open(HdsFonturi)
