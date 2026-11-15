# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
#
# HDSatelit 0.7.5: ecranul „Montarea discurilor” (Meniu > Înregistrări și stocare). Pe fiecare rand un stick, un hard disk
# USB/SATA sau un card SD, cu locul lui din /media. OK deschide o singura lista: locurile de montare (Automat, /media/hdd,
# /media/usb, /media/usb2.., /media/mmc, numele etichetei), apoi „Demontează” sau „Montează la loc”. Nimic de confirmat:
# alegerea se aplica pe loc si ramane si dupa repornire. Logica (si pagina web /montare-discuri) e in
# Components/HdsMontareDiscuri.py; citirea discurilor merge pe un fir, cu termen (HarddiskSetup.HdsDiscCitire).
from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components import HdsMontareDiscuri as M
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Tools.ScaledSkin import scaledSkin
from enigma import eTimer

SKIN = """
<screen name="HdsMontareDiscuri" position="center,center" size="1100,620" backgroundColor="hdsPanelDialog" title="Montarea discurilor">
	<widget name="list" position="24,20" size="1052,400" itemHeight="50" font="HdsRegular;24" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" />
	<eLabel position="24,432" size="1052,1" backgroundColor="hdsLine" />
	<widget name="detalii" position="24,444" size="1052,80" font="HdsRegular;20" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" />
	<widget name="nota" position="24,530" size="1052,70" font="HdsRegular;18" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" />
</screen>"""


class HdsMontareDiscuri(Screen):
	def __init__(self, session):
		self.skin = scaledSkin(SKIN)
		Screen.__init__(self, session)
		self.skinName = ["HdsMontareDiscuri"]
		self.setTitle(_("Montarea discurilor"))
		self.randuri = []
		self["list"] = MenuList([_("Se citesc datele discului...")])
		self["detalii"] = Label("")
		self["nota"] = Label(_("OK: alege locul de montare (/media/hdd, /media/usb, /media/mmc...), demontează discul ca "
			"să-l scoți în siguranță sau montează-l la loc. Alegerea rămâne și după repornire."))
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"up": self.sus,
			"down": self.jos,
		}, -1)
		self.ceas = eTimer()
		self.ceas.callback.append(self.urmareste)
		self.onClose.append(self.ceas.stop)
		self.citind = False
		self.deAratat = None
		# citirea e alta fereastra: se deschide la prima executie, nu din onLayoutFinish (Session.open ar refuza-o)
		self.onFirstExecBegin.append(self.citeste)
		try:
			from Components.Harddisk import harddiskmanager
			harddiskmanager.on_partition_list_change.append(self.discuriSchimbate)
			self.onClose.append(lambda: harddiskmanager.on_partition_list_change.remove(self.discuriSchimbate))
		except (ImportError, ValueError):
			pass
		if M.inLucru():
			self.ceas.start(500, False)

	def sus(self):
		self["list"].up()
		self.arataDetalii()

	def jos(self):
		self["list"].down()
		self.arataDetalii()

	def discuriSchimbate(self, *argumente):
		if not M.inLucru() and not self.citind:
			self.citeste()

	def citeste(self):
		from Screens.HarddiskSetup import HdsDiscCitire
		self.citind = True
		self.session.openWithCallback(self.listaGata, HdsDiscCitire, M.lista)

	def listaGata(self, rez):
		self.citind = False
		if rez is None:
			return
		if rez["stare"] != "gata":
			self.randuri = []
			self["list"].setList([_("Discul nu răspunde la timp. Încearcă din nou.")])
			return
		self.randuri = rez["valoare"] or []
		if not self.randuri:
			self["list"].setList([_("Niciun hard disk și niciun stick USB găsit.")])
		else:
			self["list"].setList(["%s   %s   %s" % (r["nume"], r["marime"], M.textStare(r)) for r in self.randuri])
		self.arataDetalii()
		l, self.deAratat = self.deAratat, None
		if l is not None:
			self.session.open(MessageBox, l["mesaj"], MessageBox.TYPE_INFO if l["stare"] == M.GATA else MessageBox.TYPE_ERROR,
				timeout=10)

	def randAles(self):
		i = self["list"].getSelectedIndex()
		if 0 <= i < len(self.randuri):
			return self.randuri[i]
		return None

	def arataDetalii(self):
		r = self.randAles()
		text = ""
		if r is not None:
			parti = [M.textStare(r)]
			if r.get("sistem"):
				parti.append(_("Sistemul de fișiere: %s") % r["sistem"])
			if r.get("ales"):
				parti.append(_("Locul ales: %s") % ("/media/" + r["ales"]))
			text = ". ".join(parti)
		l = M.stareLucru()
		if l is not None:
			text = (text + "\n" if text else "") + l["mesaj"]
		self["detalii"].setText(text)

	def ok(self):
		r = self.randAles()
		if r is None or M.inLucru():
			return
		alegeri = []
		for valoare, text in r["alegeri"]:
			eticheta = _("Montează în %s") % text if valoare else _("Automat (primul nume liber)")
			if valoare == r["ales"]:
				eticheta += "  " + _("(ales acum)")
			alegeri.append((eticheta, (M.LOC, valoare)))
		if r["poate_demonta"]:
			alegeri.append((_("Demontează (poți scoate discul în siguranță)"), (M.DEMONTARE, None)))
		if r["poate_monta"]:
			alegeri.append((_("Montează la loc"), (M.MONTARE, None)))
		if not alegeri:
			self.session.open(MessageBox, M.textStare(r), MessageBox.TYPE_INFO, timeout=8)
			return
		self.session.openWithCallback(lambda ales: self.ales(r, ales), ChoiceBox, title=r["nume"], list=alegeri)

	def ales(self, r, ales):
		if not ales:
			return
		fel, nume = ales[1]
		bun, mesaj = M.porneste(fel, r["dispozitiv"], nume)
		if not bun:
			self.session.open(MessageBox, mesaj, MessageBox.TYPE_ERROR)
			return
		self.arataDetalii()
		self.ceas.start(500, False)

	def urmareste(self):
		l = M.stareLucru()
		if l is not None and l["stare"] == M.IN_LUCRU:
			self.arataDetalii()
			return
		self.ceas.stop()
		# intai lista noua, apoi mesajul rezultatului peste ea
		self.deAratat = l
		self.citeste()
