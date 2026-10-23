# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLocul.py (ecranul) - alegerea locului antenei pe televizor: locul aflat dupa internet (prima optiune, numai cand
# receptorul are ruta spre internet, scris numai dupa confirmare), tara si orasul din tabel, sau coordonatele scrise de
# mana. Locul il tine Components/HdsLocul.py (locul unic al motorului USALS); ecranul doar il arata si il schimba.
# Tabelul e in imagine (Components/HdsLocuriDate.py, GeoNames, CC BY 4.0). Cererea pe internet o face
# Components/HdsLoculInternet.py, spre serverul nostru, numai cand omul alege "Afla locul dupa internet".
#
# Il deschid: meniul „Orientarea și setarea antenei" > „Locul antenei", Rotirea antenei („Mergi la satelit" cu locul
# nestabilit si randul „Schimbă locul antenei"), Setari tuner (randul „Locul antenei"), Calculatorul de unghiuri si
# mesajul de ecran negru („Locul antenei nu e stabilit", OK). Se inchide cu True cand locul s-a schimbat.

from .Screen import Screen
from .ChoiceBox import ChoiceBox
from .MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.MenuList import MenuList
from Components.config import ConfigFloat, ConfigSelection, NoSave, getConfigListEntry
from Components.Sources.StaticText import StaticText
from Components import HdsLocul as L
from Components import HdsLoculInternet as I
from Tools.ScaledSkin import scaledSkin
from enigma import eTimer

# eliberarea si tinerea sagetilor ajung si la listele de alegere (keymap.xml); fara efect, ca jurnalul sa nu scrie
# „unknown action" la fiecare apasare (acelasi lucru face Screens/HdsDishMotor.py)
TASTE_FARA_EFECT = ("leftUp", "rightUp", "upUp", "downUp", "leftRepeated", "rightRepeated", "upRepeated", "downRepeated")


def N_(text):
	return text


NOTA = N_("Motorul USALS calculează unghiul spre fiecare satelit din locul tău. Alege țara și orașul cel mai apropiat (o greșeală de câțiva kilometri nu contează) sau scrie coordonatele, dacă le știi exact.")
# cat de des intreaba ecranul starea cautarii dupa internet (cererea merge pe firul ei)
PAS_MS = 250
# intrebarea cu locul gasit are 9-12 randuri (loc, coordonate, sursa, explicatia): MessageBox o creste pana la atatea
# randuri (cat incape pe ecran), ca omul sa citeasca intrebarea intreaga, nu pe pagini
RANDURI_INTREBARE = 14
# etichetele tastelor colorate: scurte, fiindca lista de deasupra are textele intregi. "Afla locul dupa internet" avea 372
# px la marimea textului 115% (426 la 130%, 500-720 px in germana, maghiara, portugheza) intr-o tasta de 352 px si trecea pe
# doua randuri taiate; cele de aici au cel mult 299 px la 130%, in toate cele 13 limbi (masurat cu fontul skinului)
TASTA_LISTA = N_("Țara și orașul")
TASTA_DE_MANA = N_("Coordonatele")
TASTA_INTERNET = N_("După internet")


def _fara_efect():
	pass


class HdsLoculAlegere(ChoiceBox):
	"""lista tarilor sau a oraselor: ChoiceBox-ul imaginii, fara scurtaturi pe culori"""

	def __init__(self, session, **k):
		ChoiceBox.__init__(self, session, **k)
		self.skinName = ["ChoiceBox"]
		harta = self.get("actions")
		if harta is not None:
			for nume in TASTE_FARA_EFECT:
				harta.actions.setdefault(nume, _fara_efect)


class HdsLoculEcran(Screen):
	"""Locul de acum si felurile de a-l schimba, intr-o lista: "Afla locul dupa internet" (prima, numai cand receptorul
	are ruta spre internet), "Alege tara si orasul", "Scrie coordonatele". OK alege randul; culorile sunt scurtaturile
	(verde lista, galben coordonatele, albastru internetul). `mesaj` (de exemplu refuzul unei miscari USALS) se scrie
	deasupra; `actualizeaza_sec`=False cand cine deschide face singur sec.update() (Setari tuner, la salvare).
	Tasta albastra e un Label ca celelalte trei, fara convertor: un Label sub ConditionalShowHide nu se creeaza (Label
	cere source.text, iar convertorul nu-l are); fara internet textul ei e gol. Etichetele tastelor sunt cele scurte
	(TASTA_*), pe un rand (noWrap); nota sursei are loc de 3 randuri (atatea are la marimea textului 130%)."""
	SKIN = """
	<screen name="HdsLoculEcran" position="center,center" size="1000,600" title="Locul antenei">
		<widget source="mesaj" render="Label" position="30,15" size="940,60" font="Regular;22" foregroundColor="#ffc250" valign="center" />
		<widget source="loc" render="Label" position="30,80" size="940,70" font="Regular;30" halign="center" valign="center" />
		<widget name="optiuni" position="30,160" size="940,150" itemHeight="50" font="Regular;26" scrollbarMode="showOnDemand" />
		<widget source="nota" render="Label" position="30,320" size="940,120" font="Regular;21" />
		<widget source="sursa" render="Label" position="30,445" size="940,92" font="Regular;17" foregroundColor="#8fa0b0" />
		<widget source="key_red" render="Label" position="30,540" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" noWrap="1" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="265,540" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" noWrap="1" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="500,540" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" noWrap="1" backgroundColor="#a08000" transparent="0" />
		<widget source="key_blue" render="Label" position="735,540" size="235,40" zPosition="1" font="Regular;20" halign="center" valign="center" noWrap="1" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	def __init__(self, session, mesaj=None, actualizeaza_sec=True):
		self.skin = scaledSkin(self.SKIN)
		Screen.__init__(self, session)
		self.setTitle(_("Locul antenei"))
		self.schimbat = False
		self.actualizeaza_sec = actualizeaza_sec
		self.mesajInitial = mesaj or ""
		self.cautand = False
		self._orasDorit = None
		# ruta spre internet, citita local la deschidere: fara ea optiunea nu apare si nu pleaca nicio cerere
		self.cuInternet = I.retea()
		self["mesaj"] = StaticText(self.mesajInitial)
		self["loc"] = StaticText("")
		self["optiuni"] = MenuList(self._optiuni())
		self["nota"] = StaticText(_(NOTA))
		self["sursa"] = StaticText(_(I.NOTA_SURSA) % L.ATRIBUIRE)
		self["key_red"] = StaticText(_("Închide"))
		self["key_green"] = StaticText(_(TASTA_LISTA))
		self["key_yellow"] = StaticText(_(TASTA_DE_MANA))
		self["key_blue"] = StaticText(_(TASTA_INTERNET) if self.cuInternet else "")
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.alege,
			"green": self.lista,
			"yellow": self.deMana,
			"blue": self.internet,
			"red": self.inchide,
			"cancel": self.inchide,
		}, -1)
		self.ceas = eTimer()
		self.ceas.callback.append(self._urmareste)
		self.onClose.append(self.ceas.stop)
		# locul scris din alta parte (pagina web) se vede aici fara sa inchizi ecranul
		L.laSchimbare(self._locSchimbat)
		self.onClose.append(lambda: L.nuMaiAscultaLaSchimbare(self._locSchimbat))
		self._arata()

	def _optiuni(self):
		"""randurile listei, in ordine: locul dupa internet (numai cu ruta spre internet), lista, coordonatele"""
		rez = []
		if self.cuInternet:
			rez.append((_(I.OPTIUNE), "internet"))
		rez.append((_("Alege țara și orașul"), "lista"))
		rez.append((_("Scrie coordonatele"), "mana"))
		return rez

	def _arata(self):
		self["loc"].setText(_("Locul antenei: %s") % L.textLoc())

	def _locSchimbat(self):
		"""locul s-a scris (HdsLocul.seteaza) cat timp ecranul e deschis, de exemplu din pagina web: se arata locul nou,
		iar cine a deschis ecranul afla la inchidere ca locul s-a schimbat. Mesajul de deasupra (de ce s-a deschis
		ecranul) nu mai e de actualitate; cat se cauta, ramane 'Caut locul...'."""
		self.schimbat = True
		self.mesajInitial = ""
		if not self.cautand:
			self["mesaj"].setText("")
		self._arata()

	def inchide(self):
		self.close(self.schimbat)

	def alege(self):
		ales = self["optiuni"].getCurrent()
		fel = ales[1] if ales else "lista"
		if fel == "internet":
			self.internet()
		elif fel == "mana":
			self.deMana()
		else:
			self.lista()

	# ---- locul dupa internet (Components/HdsLoculInternet.py)

	def internet(self):
		if not self.cuInternet or self.cautand:
			return
		if not I.CAUTARE.porneste():
			# ruta a disparut intre timp: nicio cerere; omul afla de ce si primeste lista
			self.cuInternet = False
			self["optiuni"].setList(self._optiuni())
			self["key_blue"].setText("")
			self._rezultat(I.CAUTARE.stare())
			return
		self.cautand = True
		self["mesaj"].setText(_(I.CAUT))
		self.ceas.start(PAS_MS, True)

	def _urmareste(self):
		st = I.CAUTARE.stare()
		if st["stare"] == I.LUCREAZA:
			self.ceas.start(PAS_MS, True)
			return
		self.cautand = False
		self["mesaj"].setText(self.mesajInitial)
		self._rezultat(st)

	def _rezultat(self, st):
		"""locul gasit: intrebarea (Da = locul se scrie, Nu = lista, cu tara si orasul gasite alese); altfel mesajul
		(fara internet, serverul nu raspunde, raspuns stricat), apoi lista, ca pana acum"""
		if st["stare"] == I.GASIT and st["gasit"]:
			self.session.openWithCallback(lambda da: self._raspuns(da, st), MessageBox, st["intrebare"],
				MessageBox.TYPE_YESNO, default=True, randuri=RANDURI_INTREBARE)
			return
		self.session.openWithCallback(lambda *a: self.lista(), MessageBox, st["mesaj"], MessageBox.TYPE_INFO)

	def _raspuns(self, da, st):
		if da:
			self._dupa(*I.CAUTARE.foloseste(st["semn"], actualizeaza_sec=self.actualizeaza_sec))
			return
		# lista se deschide pe orasul din tabel cel mai apropiat de locul gasit (orasul gasit poate lipsi din tabel)
		g = st["gasit"]
		self.lista(g.get("tara_lista") or None, g.get("oras_lista") or None)

	# ---- tara si orasul

	def lista(self, tara=None, oras=None):
		"""lista tarilor; `tara` si `oras` (locul gasit dupa internet, refuzat) sunt alese dinainte"""
		tari = L.tari()
		curenta = tara or L.stare().get("tara") or "RO"
		ales = 0
		for i, (cod, _nume) in enumerate(tari):
			if cod == curenta:
				ales = i
		self._orasDorit = (tara, oras) if tara and oras else None
		self.session.openWithCallback(self._taraAleasa, HdsLoculAlegere, title=_("Alege țara"),
			list=[(nume, cod) for cod, nume in tari], keys=[], selection=ales)

	def _taraAleasa(self, rezultat):
		if not rezultat:
			return
		cod = rezultat[1]
		orase = L.orase(cod)
		if not orase:
			return
		st = L.stare()
		dorit = st.get("oras") if st.get("tara") == cod else {"RO": u"București", "MD": u"Chișinău"}.get(cod)
		if self._orasDorit is not None and self._orasDorit[0] == cod:
			dorit = self._orasDorit[1]
		ales = 0
		for i, (nume, _lat, _lon) in enumerate(orase):
			if nume == dorit:
				ales = i
		lista = [("%s   (%s)" % (nume, L.textCoordonate(lat, lon)), nume) for nume, lat, lon in orase]
		self.session.openWithCallback(lambda r: self._orasAles(cod, r), HdsLoculAlegere,
			title=_("Alege orașul (%s)") % L.numeTara(cod), list=lista, keys=[], selection=ales)

	def _orasAles(self, cod, rezultat):
		if not rezultat:
			return
		loc = L.gasesteOras(cod, rezultat[1])
		if loc is None:
			self._dupa(False, _(L.MESAJ_ORAS))
			return
		self._dupa(*L.seteaza(loc[0], loc[1], cod, rezultat[1], L.SURSA_TABEL, actualizeaza_sec=self.actualizeaza_sec))

	# ---- coordonatele scrise de mana

	def deMana(self):
		self.session.openWithCallback(self._dinMana, HdsLoculDeMana, actualizeaza_sec=self.actualizeaza_sec)

	def _dinMana(self, schimbat=False):
		if schimbat:
			self._dupa(True, "")

	def _dupa(self, ok, text):
		if not ok:
			self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)
			return
		self.schimbat = True
		self["mesaj"].setText("")
		self.mesajInitial = ""
		self._arata()
		self.session.open(MessageBox, _("Locul antenei este acum: %s") % L.textLoc(), MessageBox.TYPE_INFO, timeout=5)


class HdsLoculDeMana(Screen, ConfigListScreen):
	"""latitudinea si longitudinea in grade cu trei zecimale (cifrele telecomenzii), emisfera si partea de Greenwich"""
	SKIN = """
	<screen name="HdsLoculDeMana" position="center,center" size="900,440" title="Coordonatele antenei">
		<widget name="config" position="30,30" size="840,200" font="Regular;24" secondfont="Regular;16" itemHeight="48" scrollbarMode="showOnDemand" />
		<widget source="nota" render="Label" position="30,250" size="840,110" font="Regular;20" />
		<widget source="key_red" render="Label" position="30,380" size="290,40" zPosition="1" font="Regular;21" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="580,380" size="290,40" zPosition="1" font="Regular;21" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session, actualizeaza_sec=True):
		self.skin = scaledSkin(self.SKIN)
		Screen.__init__(self, session)
		self.setTitle(_("Coordonatele antenei"))
		self.actualizeaza_sec = actualizeaza_sec
		lat, lon = L.locul() or (0, 0)
		self.lat = NoSave(ConfigFloat(default=[abs(lat) // 1000, abs(lat) % 1000], limits=[(0, 90), (0, 999)]))
		self.nord = NoSave(ConfigSelection([("north", _("Nord")), ("south", _("Sud"))], "north" if lat >= 0 else "south"))
		self.lon = NoSave(ConfigFloat(default=[abs(lon) // 1000, abs(lon) % 1000], limits=[(0, 180), (0, 999)]))
		self.est = NoSave(ConfigSelection([("east", _("Est")), ("west", _("Vest"))], "east" if lon >= 0 else "west"))
		lista = [
			getConfigListEntry(_("Latitudinea (grade)"), self.lat),
			getConfigListEntry(_("Emisfera"), self.nord),
			getConfigListEntry(_("Longitudinea (grade)"), self.lon),
			getConfigListEntry(_("Față de Greenwich"), self.est),
		]
		ConfigListScreen.__init__(self, lista, session=session)
		self["nota"] = StaticText(_("Cifrele se scriu cu tastele telecomenzii, cu trei zecimale (de exemplu 44.426 pentru 44,426 grade). România e la nord și la est de Greenwich."))
		self["key_red"] = StaticText(_("Renunță"))
		self["key_green"] = StaticText(_("Salvează"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.salveaza,
			"green": self.salveaza,
			"red": self.renunta,
			"cancel": self.renunta,
		}, -2)

	def renunta(self):
		self.close(False)

	def salveaza(self):
		lat = int(self.lat.value[0]) * 1000 + int(self.lat.value[1])
		lon = int(self.lon.value[0]) * 1000 + int(self.lon.value[1])
		if lat > L.LAT_MAX or lon > L.LON_MAX:
			self.session.open(MessageBox, _(L.MESAJ_LIMITE), MessageBox.TYPE_ERROR)
			return
		if self.nord.value == "south":
			lat = -lat
		if self.est.value == "west":
			lon = -lon
		ok, text = L.seteaza(lat, lon, "", "", L.SURSA_MANA, actualizeaza_sec=self.actualizeaza_sec)
		if not ok:
			self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)
			return
		self.close(True)


def deschide(session, apoi=None, mesaj=None, actualizeaza_sec=True):
	"""alegerea locului; `apoi(schimbat)` dupa inchidere"""
	def gata(schimbat=False):
		if apoi is not None:
			apoi(bool(schimbat))
	session.openWithCallback(gata, HdsLoculEcran, mesaj=mesaj, actualizeaza_sec=actualizeaza_sec)
