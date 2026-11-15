# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HDSatelit 0.7.5: ecranul "Sigle canale (piconuri)" (Meniu > Setari > Interfata si aspect, si OK pe setarea Siglele
# canalelor cand nu e nicio sigla). Omul pune un set de sigle fara FTP: de la o adresa scrisa de el sau de pe un stick sau
# disc (o arhiva sau un dosar). Totul dintr-o privire: locul (cu spatiul liber, ales singur), bifa "Numai canalele din
# lista mea" (din fabrica da), apoi o tasta. Actualizarea (aceeasi sursa) si dezinstalarea (numai ce am pus noi), tot cu
# o tasta; numai dezinstalarea cere confirmare. Logica si lucrul pe fir: Components/HdsPiconInstalare.py; pagina web:
# /piconuri (HdsWebControl/piconuri_web.py), aceleasi functii.
import os

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.FileList import FileList
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components import HdsPiconInstalare as P
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Tools.ScaledSkin import scaledSkin
from enigma import eTimer

# Asezarea dupa designul din Stitch (proiectul HD Satelit, ecranul "Sigle canale (piconuri)", 14.11.2026): lista la
# stanga, la dreapta 4 sigle din locul ales (previzualizarea setului pus), starea sub o linie, legenda tastelor colorate.
SKIN = """
<screen name="HdsPiconuri" position="center,center" size="1100,620" backgroundColor="hdsPanelDialog" title="Sigle canale (piconuri)">
	<widget name="list" position="24,20" size="720,300" itemHeight="50" font="HdsRegular;24" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" />
	<eLabel position="764,20" size="312,300" backgroundColor="hdsPanelSoft" />
	<widget name="titluSigle" position="780,26" size="280,30" font="HdsRegular;18" foregroundColor="hdsText2" backgroundColor="hdsPanelSoft" transparent="1" />
	<widget name="sigla0" position="780,62" size="120,56" alphatest="blend" />
	<widget name="nume0" position="912,62" size="156,56" font="HdsRegular;17" foregroundColor="hdsText2" backgroundColor="hdsPanelSoft" valign="center" transparent="1" />
	<widget name="sigla1" position="780,126" size="120,56" alphatest="blend" />
	<widget name="nume1" position="912,126" size="156,56" font="HdsRegular;17" foregroundColor="hdsText2" backgroundColor="hdsPanelSoft" valign="center" transparent="1" />
	<widget name="sigla2" position="780,190" size="120,56" alphatest="blend" />
	<widget name="nume2" position="912,190" size="156,56" font="HdsRegular;17" foregroundColor="hdsText2" backgroundColor="hdsPanelSoft" valign="center" transparent="1" />
	<widget name="sigla3" position="780,254" size="120,56" alphatest="blend" />
	<widget name="nume3" position="912,254" size="156,56" font="HdsRegular;17" foregroundColor="hdsText2" backgroundColor="hdsPanelSoft" valign="center" transparent="1" />
	<eLabel position="24,336" size="1052,1" backgroundColor="hdsLine" />
	<widget name="detalii" position="24,348" size="1052,96" font="HdsRegular;22" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" />
	<eLabel position="24,454" size="1052,1" backgroundColor="hdsLine" />
	<eLabel position="24,474" size="16,16" backgroundColor="#0a9e4c" />
	<widget name="key_green" position="48,466" size="230,32" font="HdsRegular;19" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" />
	<eLabel position="290,474" size="16,16" backgroundColor="#d9a400" />
	<widget name="key_yellow" position="314,466" size="270,32" font="HdsRegular;19" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" />
	<eLabel position="596,474" size="16,16" backgroundColor="#2c55c8" />
	<widget name="key_blue" position="620,466" size="200,32" font="HdsRegular;19" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" />
	<eLabel position="832,474" size="16,16" backgroundColor="#d03a2f" />
	<widget name="key_red" position="856,466" size="220,32" font="HdsRegular;19" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" />
	<widget name="nota" position="24,510" size="1052,94" font="HdsRegular;18" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" />
</screen>"""

SKIN_ALEGERE = """
<screen name="HdsPiconuriAlege" position="center,center" size="1100,620" backgroundColor="hdsPanelDialog" title="Alege arhiva sau dosarul">
	<widget name="cale" position="24,16" size="1052,34" font="HdsRegular;22" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" />
	<widget name="list" position="24,58" size="1052,450" itemHeight="45" font="HdsRegular;22" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" />
	<widget name="nota" position="24,520" size="1052,84" font="HdsRegular;18" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" />
</screen>"""

ARHIVE = r"(?i)^.*\.(zip|tar|tgz|gz|xz|txz|bz2|tbz2|ipk)$"

# randurile ecranului; PORNIT (0.7.5, LCF, dorinelu forumul 795 #2479): setarea Da/Nu Siglele canalelor
# (config.usage.hds_piconuri), primul rand, ca sa fie unde omul cauta siglele, nu numai jos in Setari generale
LOC, NUMAI_LISTA, ADRESA, STICK, ACTUALIZARE, DEZINSTALARE, PORNIT = range(7)


def _pornite():
	try:
		from Components.config import config
		return bool(config.usage.hds_piconuri.value)
	except Exception:
		return True


class HdsPiconuriAlege(Screen):
	"""Rasfoirea unui stick sau disc: OK pe o arhiva o alege, OK pe un dosar intra in el, VERDE alege dosarul de acum."""

	def __init__(self, session, inceput="/media/"):
		self.skin = scaledSkin(SKIN_ALEGERE)
		Screen.__init__(self, session)
		self.skinName = ["HdsPiconuriAlege"]
		self.setTitle(_("Alege arhiva sau dosarul cu sigle"))
		if not os.path.isdir(inceput):
			inceput = "/"
		self["list"] = FileList(inceput, showDirectories=True, showFiles=True, matchingPattern=ARHIVE)
		self["cale"] = Label("")
		self["nota"] = Label(_("OK: intră în dosar sau alege arhiva (zip, tar, tar.gz, tar.xz, ipk). "
			"VERDE: alege dosarul în care ești (siglele .png din el și din dosarele lui). EXIT: înapoi."))
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.ok,
			"green": self.alegeDosarul,
			"cancel": lambda: self.close(None),
		}, -1)
		self["list"].onSelectionChanged.append(self.arataCalea)
		self.onLayoutFinish.append(self.arataCalea)

	def arataCalea(self):
		self["cale"].setText(self["list"].getCurrentDirectory() or "/")

	def ok(self):
		l = self["list"]
		if l.canDescent():
			l.descent()
			self.arataCalea()
		elif l.getFilename():
			self.close(l.getFilename())

	def alegeDosarul(self):
		d = self["list"].getCurrentDirectory()
		if d:
			self.close(d)


class HdsPiconuri(Screen):
	def __init__(self, session):
		self.skin = scaledSkin(SKIN)
		Screen.__init__(self, session)
		self.skinName = ["HdsPiconuri"]
		self.setTitle(_("Sigle canale (piconuri)"))
		self.locuri = P.locuri()
		self.loc = P.loc_implicit(self.locuri)
		self.numaiLista = True
		self.adresa = ""
		self.randuri = []
		self.eraOcupat = False
		self["list"] = MenuList([])
		self["detalii"] = Label("")
		self["nota"] = Label(_("Imaginea nu are seturi proprii: alegi tu de unde le iei (o adresă sau un stick). "
			"Siglele se văd pe loc. Dezinstalarea șterge numai ce s-a pus de aici."))
		self["key_green"] = Label(_("De la o adresă"))
		self["key_yellow"] = Label(_("De pe stick sau disc"))
		self["key_blue"] = Label(_("Actualizează"))
		self["key_red"] = Label(_("Dezinstalează"))
		self["titluSigle"] = Label("")
		for i in range(4):
			self["sigla%d" % i] = Pixmap()
			self["nume%d" % i] = Label("")
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"green": lambda: self.fa(ADRESA),
			"yellow": lambda: self.fa(STICK),
			"blue": lambda: self.fa(ACTUALIZARE),
			"red": lambda: self.fa(DEZINSTALARE),
		}, -1)
		self.ceas = eTimer()
		self.ceas.callback.append(self.urmareste)
		self.onClose.append(self.ceas.stop)
		self.onLayoutFinish.append(self.umple)
		j = P.citeste_jurnal(self.loc)
		if j and j.get("fel") == "adresa":
			self.adresa = j.get("sursa", "")
		if P.Lucru.ocupat:
			self.ceas.start(500, False)

	def locAles(self):
		for l in self.locuri:
			if l["cale"] == self.loc:
				return l
		return None

	def umple(self):
		l = self.locAles()
		j = P.citeste_jurnal(self.loc)
		loc = "%s  (%s %s)" % (l["nume"], P.marime_text(l["liber"]), _("liberi")) if l else self.loc
		self.randuri = [
			(PORNIT, "%s: %s" % (_("Siglele canalelor (piconuri)"), _("Da") if _pornite() else _("Nu"))),
			(LOC, _("Locul: %s") % loc),
			(NUMAI_LISTA, _("Numai canalele din lista mea: %s") % (_("Da") if self.numaiLista else _("Nu"))),
			(ADRESA, _("Instalează de la o adresă")),
			(STICK, _("Instalează de pe stick sau disc")),
		]
		if j:
			self.randuri.append((ACTUALIZARE, _("Actualizează siglele (aceeași sursă)")))
			self.randuri.append((DEZINSTALARE, _("Dezinstalează siglele puse aici")))
		poz = self["list"].getSelectedIndex() if self["list"].list else 0
		self["list"].setList([t for _f, t in self.randuri])
		self["list"].moveToIndex(min(poz, len(self.randuri) - 1))
		self["key_blue"].setText(_("Actualizează") if j else "")
		self["key_red"].setText(_("Dezinstalează") if j else "")
		self.arataStarea()
		self.arataSigle(j)

	def arataSigle(self, j):
		"""Cel mult 4 sigle din locul ales (intai cele puse de aici), ca previzualizare."""
		nume = [n for n in (j or {}).get("fisiere", [])][:4]
		if len(nume) < 4:
			try:
				for n in sorted(os.listdir(self.loc)):
					if len(nume) >= 4:
						break
					if n.lower().endswith(".png") and not n.startswith("picon_default") and n not in nume:
						nume.append(n)
			except OSError:
				pass
		self["titluSigle"].setText(_("Previzualizare") if nume else _("Încă nicio siglă aici"))
		from Tools.LoadPixmap import LoadPixmap
		for i in range(4):
			p, l = self["sigla%d" % i], self["nume%d" % i]
			png = None
			if i < len(nume):
				try:
					png = LoadPixmap(os.path.join(self.loc, nume[i]), width=93, height=56)
				except Exception:
					png = None
			if png is not None and p.instance:
				try:
					p.instance.setScale(1)
				except Exception:
					pass
				p.instance.setPixmap(png)
				p.show()
			else:
				p.hide()
			l.setText(nume[i][:-4][:18] if i < len(nume) else "")

	def arataStarea(self):
		s = P.Lucru.stare()
		if s["ocupat"]:
			self["detalii"].setText(s["text"])
			return
		l = self.locAles()
		j = P.citeste_jurnal(self.loc)
		parti = []
		if not _pornite():
			parti.append(_("Siglele sunt oprite. OK pe primul rând le pornește."))
		if l:
			parti.append(_("Sigle aici: %d") % l["sigle"])
		if j:
			parti.append(_("Puse din acest ecran: %d, de la %s") % (len(j.get("fisiere", [])), j.get("sursa", "")))
		else:
			parti.append(_("Alege o adresă sau o arhivă de pe stick. Se scriu numai siglele canalelor tale."))
		self["detalii"].setText("\n".join(parti))

	def ok(self):
		i = self["list"].getSelectedIndex()
		if 0 <= i < len(self.randuri):
			self.fa(self.randuri[i][0])

	def fa(self, fel):
		if fel == PORNIT:
			self.schimbaPornirea()
			return
		if P.Lucru.ocupat:
			self.session.open(MessageBox, _("Se instalează deja. Așteaptă să se termine."), MessageBox.TYPE_INFO, timeout=5)
			return
		if fel == LOC:
			alegeri = [("%s  (%s %s, %d %s)" % (l["nume"], P.marime_text(l["liber"]), _("liberi"), l["sigle"], _("sigle")),
				l["cale"]) for l in self.locuri]
			self.session.openWithCallback(self.locNou, ChoiceBox, title=_("Unde se pun siglele?"), list=alegeri)
		elif fel == NUMAI_LISTA:
			self.numaiLista = not self.numaiLista
			self.umple()
		elif fel == ADRESA:
			from Screens.VirtualKeyBoard import VirtualKeyBoard
			self.session.openWithCallback(self.adresaScrisa, VirtualKeyBoard,
				title=_("Adresa arhivei cu sigle (zip, tar.gz, tar.xz, ipk)"), text=self.adresa or "https://")
		elif fel == STICK:
			self.session.openWithCallback(self.caleAleasa, HdsPiconuriAlege)
		elif fel == ACTUALIZARE:
			if P.citeste_jurnal(self.loc):
				self.porneste(P.actualizeaza, self.loc)
		elif fel == DEZINSTALARE:
			if P.citeste_jurnal(self.loc):
				self.session.openWithCallback(self.dezinstaleaza, MessageBox,
					_("Ștergi siglele puse din acest ecran? Siglele tale de dinainte rămân."), MessageBox.TYPE_YESNO,
					default=False)

	def schimbaPornirea(self):
		"""Da/Nu pe setarea Siglele canalelor; HdsPiconBare o aplica pe loc pe bare si in lista (notificatorul ei)."""
		try:
			from Components.config import config, configfile
			el = config.usage.hds_piconuri
			el.value = not el.value
			el.save()
			configfile.save()
		except Exception as eroare:
			print("[HdsPiconuri] setarea siglelor: %s" % eroare)
		self.umple()

	def locNou(self, ales):
		if ales:
			self.loc = ales[1]
			self.umple()

	def adresaScrisa(self, text):
		if text and text.strip() not in ("", "https://", "http://"):
			self.adresa = text.strip()
			self.porneste(P.instaleaza_din_adresa, self.adresa, self.loc, self.numaiLista)

	def caleAleasa(self, cale):
		if cale:
			self.porneste(P.instaleaza_din_cale, cale, self.loc, self.numaiLista)

	def dezinstaleaza(self, da):
		if not da:
			return
		try:
			n = P.dezinstaleaza(self.loc)
			mesaj = _("Am șters %d sigle.") % n
		except P.Eroare as e:
			mesaj = str(e)
		self.locuri = P.locuri()
		self.umple()
		self.session.open(MessageBox, mesaj, MessageBox.TYPE_INFO, timeout=8)

	def porneste(self, functie, *argumente):
		if P.Lucru.porneste(functie, *argumente):
			self.eraOcupat = True
			self.ceas.start(500, False)
			self.arataStarea()

	def urmareste(self):
		s = P.Lucru.stare()
		self["detalii"].setText(s["text"])
		if s["ocupat"]:
			self.eraOcupat = True
			return
		self.ceas.stop()
		if self.eraOcupat:
			self.eraOcupat = False
			self.locuri = P.locuri()
			self.umple()
			self.session.open(MessageBox, s["text"], MessageBox.TYPE_ERROR if s["eroare"] else MessageBox.TYPE_INFO,
				timeout=10)
