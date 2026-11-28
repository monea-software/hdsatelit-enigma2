# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLocul.py (ecranul) - alegerea locului antenei pe televizor: locul aflat dupa internet (prima optiune, numai cand
# receptorul are ruta spre internet, scris pe loc, fara intrebare), tara si orasul din tabel, sau coordonatele scrise de
# mana. Locul il tine Components/HdsLocul.py (locul unic al motorului USALS); ecranul doar il arata si il schimba.
# Tabelul e in imagine (GeoNames, CC BY 4.0; orasele in /usr/share/enigma2/hds-locuri.tsv.gz). Cererea pe internet o
# face Components/HdsLoculInternet.py, spre serverul nostru. Din 0.8.0 (LOC2: implicit cat timp e internet)
# locul dupa internet e cel implicit: cat omul nu a ales singur un oras sau coordonate, ecranul il afla din nou la
# deschidere si il scrie fara intrebare (fara internet sau cu VPN-ul receptorului pornit ramane ultimul loc stiut).
#
# Il deschid: meniul „Orientarea și setarea antenei" > „Locul antenei", Rotirea antenei („Mergi la satelit" cu locul
# nestabilit si randul „Schimbă locul antenei"), Setari tuner (randul „Locul antenei"), Calculatorul de unghiuri si
# mesajul de ecran negru („Locul antenei nu e stabilit", OK). Se inchide cu True cand locul s-a schimbat.

from .Screen import Screen
from .MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.MenuList import MenuList
from Components.config import ConfigFloat, ConfigSelection, NoSave, getConfigListEntry
from Components.Sources.StaticText import StaticText
from Components import HdsLocul as L
from Components import HdsLoculInternet as I
from Tools.ScaledSkin import scaledSkin
from Tools.BoundFunction import boundFunction
from Tools.NumericalTextInput import NumericalTextInput
from enigma import eTimer

# eliberarea si tinerea sagetilor ajung si la listele de alegere (keymap.xml); fara efect, ca jurnalul sa nu scrie
# „unknown action" la fiecare apasare (acelasi lucru face Screens/HdsDishMotor.py)
TASTE_FARA_EFECT = ("leftUp", "rightUp", "upUp", "downUp", "leftRepeated", "rightRepeated", "upRepeated", "downRepeated")


def N_(text):
	return text


NOTA = N_("Motorul USALS calculează unghiul spre fiecare satelit din locul tău. Alege țara și orașul cel mai apropiat (o greșeală de câțiva kilometri nu contează) sau scrie coordonatele, dacă le știi exact.")
# cat de des intreaba ecranul starea cautarii dupa internet (cererea merge pe firul ei)
PAS_MS = 250
# etichetele tastelor colorate: scurte, fiindca lista de deasupra are textele intregi. "Afla locul dupa internet" avea 372
# px la marimea textului 115% (426 la 130%, 500-720 px in germana, maghiara, portugheza) intr-o tasta de 352 px si trecea pe
# doua randuri taiate; cele de aici au cel mult 299 px la 130%, in toate cele 13 limbi (masurat cu fontul skinului)
TASTA_LISTA = N_("Țara și orașul")
TASTA_DE_MANA = N_("Coordonatele")
TASTA_INTERNET = N_("După internet")
NOTA_DE_MANA = N_("Scrie cifrele cu tastele telecomenzii, cu trei zecimale (de exemplu 43.651). În America alege Vest, în emisfera sudică (de exemplu Brazilia sau Australia) alege Sud.")


def _fara_efect():
	pass


# cifrele ca la telefon, pentru cautarea in liste: 0 si 1 nu scriu nimic in nume de tari si orase, deci scriu cifra
LITERE_SMS = ("0", "1", "abc2", "def3", "ghi4", "jkl5", "mno6", "pqrs7", "tuv8", "wxyz9")
MAX_CAUTARE = 30
INDICIU_CAUTARE = N_("Scrie primele litere ca să găsești mai repede: tastele 0-9 ca la SMS, Verde = tastatura.")
NIMIC_GASIT = N_("Nimic nu se potrivește. Galben șterge o literă.")


class HdsLoculAlegere(Screen):
	"""Lista tarilor sau a oraselor, cu cautare dupa litere (LOC1, 26.11.2026: tabelul are acum toata lumea, ~245 de tari
	si pana la cateva sute de orase pe tara; lme, Canada, nu-si gasea tara). Pastreaza felul de chemare al ChoiceBox-ului
	de pana acum: title, list=[(textul aratat, valoarea)], selection; se inchide cu randul ales (tuplul din list) sau cu
	None. Literele: tastele 0-9 ca la SMS, tastatura USB, Verde (sau TEXT) tastatura de pe ecran; Galben sterge o
	litera, Rosu sterge tot. Lista arata numai randurile care contin literele scrise (fara semne: "sao" gaseste "São
	Paulo", "montr" gaseste "Montréal")."""
	SKIN = """
	<screen name="HdsLoculAlegere" position="center,center" size="1000,640" title="Alege">
		<widget source="cautare" render="Label" position="30,15" size="940,44" font="Regular;28" backgroundColor="#2a3350" valign="center" noWrap="1" transparent="0" />
		<widget source="indiciu" render="Label" position="30,64" size="940,56" font="Regular;19" foregroundColor="#aeb9cc" />
		<widget name="lista" position="30,126" size="940,450" itemHeight="45" font="Regular;26" scrollbarMode="showOnDemand" />
		<widget source="key_red" render="Label" position="30,590" size="300,40" zPosition="1" font="Regular;20" halign="center" valign="center" noWrap="1" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="350,590" size="300,40" zPosition="1" font="Regular;20" halign="center" valign="center" noWrap="1" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="670,590" size="300,40" zPosition="1" font="Regular;20" halign="center" valign="center" noWrap="1" backgroundColor="#a08000" transparent="0" />
	</screen>
	"""

	def __init__(self, session, title="", list=None, selection=0, keys=None, cautaInValoare=False, **k):
		self.skin = scaledSkin(self.SKIN)
		Screen.__init__(self, session)
		self.titlu = title
		self.setTitle(title)
		# `list` e numele parametrului din ChoiceBox (cine cheama ramane la fel), deci aici nu e functia list()
		self.toate = [r for r in (list or [])]
		# orasele se cauta dupa nume (valoarea randului), nu dupa textul cu coordonate (altfel "n" gasea orice "N")
		self.numeRand = (lambda r: r[1]) if cautaInValoare else (lambda r: r[0])
		self.text = ""
		self.inAsteptare = ""
		self.vazute = self.toate
		self.modTastatura = None
		self.sms = NumericalTextInput(nextFunc=self._literaConfirmata)
		self.sms.mapping = [x for x in LITERE_SMS]
		self["cautare"] = StaticText("")
		self["indiciu"] = StaticText(_(INDICIU_CAUTARE))
		self["lista"] = MenuList([r[0] for r in self.toate])
		self["key_red"] = StaticText(_("Șterge tot"))
		self["key_green"] = StaticText(_("Tastatură"))
		self["key_yellow"] = StaticText(_("Șterge litera"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.alege,
			"cancel": self.renunta,
			"red": self.stergeTot,
			"green": self.tastatura,
			"yellow": self.stergeLitera,
			"up": self._sus,
			"down": self._jos,
			"left": self._paginaSus,
			"right": self._paginaJos,
			"upRepeated": self._sus,
			"downRepeated": self._jos,
			"leftRepeated": self._paginaSus,
			"rightRepeated": self._paginaJos,
			"upUp": _fara_efect,
			"downUp": _fara_efect,
			"leftUp": _fara_efect,
			"rightUp": _fara_efect,
		}, -1)
		self["cifre"] = ActionMap(["NumberActions"], dict((str(i), boundFunction(self.cifra, i)) for i in range(10)), -1)
		self["ascii"] = ActionMap(["InputAsciiActions"], {"gotAsciiCode": self.ascii}, -1)
		self["text"] = ActionMap(["HdsCautareActions"], {"cautare": self.tastatura}, -1)
		self["sterge"] = ActionMap(["HdsTastaturaStergeActions"], {"deleteBackward": self.stergeLitera}, -1)
		self.selectieInitiala = selection if isinstance(selection, int) and 0 <= selection < len(self.toate) else 0
		self.onLayoutFinish.append(self._primaData)
		# la deschidere si la intoarcerea din tastatura de pe ecran (probele de pe PC au un ecran fals fara onExecBegin)
		if hasattr(self, "onExecBegin"):
			self.onExecBegin.append(self._modAscii)
		self.onClose.append(self._laInchidere)
		self._arataText()

	# ---- lista si cautarea

	def _primaData(self):
		if self.toate:
			self["lista"].moveToIndex(self.selectieInitiala)

	def _textCautat(self):
		return self.text + self.inAsteptare

	def _filtreaza(self):
		"""randurile care contin literele scrise; cursorul ramane pe randul ales, daca inca se vede"""
		text = self._textCautat()
		ales = self._curent()
		self.vazute = L.filtreaza(self.toate, text, self.numeRand) if text else self.toate
		self["lista"].setList([r[0] for r in self.vazute])
		i = self.vazute.index(ales) if ales in self.vazute and not text else 0
		if self.vazute:
			self["lista"].moveToIndex(i)
		self._arataText()

	def _arataText(self):
		text = self._textCautat()
		if text and not self.vazute:
			self["indiciu"].setText(_(NIMIC_GASIT))
		else:
			self["indiciu"].setText(_(INDICIU_CAUTARE))
		self["cautare"].setText("  " + _("Caută: %s") % (text + "_"))

	def _curent(self):
		try:
			i = self["lista"].getSelectionIndex()
		except Exception:
			return None
		if 0 <= i < len(self.vazute):
			return self.vazute[i]
		return None

	def _sus(self):
		self["lista"].up()

	def _jos(self):
		self["lista"].down()

	def _paginaSus(self):
		self["lista"].pageUp()

	def _paginaJos(self):
		self["lista"].pageDown()

	def alege(self):
		self.sms.nextKey()
		ales = self._curent()
		if ales is None:
			return
		self.close(ales)

	def renunta(self):
		self.close(None)

	# ---- literele

	def cifra(self, n):
		if len(self.text) >= MAX_CAUTARE:
			return
		litera = self.sms.getKey(n)  # alta tasta decat inainte: litera veche se confirma (_literaConfirmata)
		if litera is None:
			return
		self.inAsteptare = litera
		if len(LITERE_SMS[n]) == 1:
			self.sms.nextChar()
		self._filtreaza()

	def _literaConfirmata(self):
		if self.inAsteptare:
			self.text = (self.text + self.inAsteptare)[:MAX_CAUTARE]
			self.inAsteptare = ""
			self._arataText()

	def ascii(self):
		"""o tastatura USB: literele intra in cautare; ce nu e litera (Enter, Esc) merge mai departe (0)"""
		try:
			from enigma import getPrevAsciiCode
			cod = getPrevAsciiCode()
		except Exception:
			return 0
		if cod in (8, 127):
			self.stergeLitera()
			return 1
		ch = chr(cod)
		if not ch.isprintable():
			return 0
		self.sms.nextKey()
		self.text = (self.text + self.inAsteptare + ch)[:MAX_CAUTARE]
		self.inAsteptare = ""
		self._filtreaza()
		return 1

	def stergeLitera(self):
		if self.inAsteptare:
			self.sms.nextKey()
			self.inAsteptare = ""
		elif self.text:
			self.text = self.text[:-1]
		else:
			return 1
		self._filtreaza()
		return 1

	def stergeTot(self):
		self.sms.nextKey()
		self.text, self.inAsteptare = "", ""
		self._filtreaza()

	def tastatura(self):
		self.sms.nextKey()
		self.text += self.inAsteptare
		self.inAsteptare = ""
		from .VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(self._dinTastatura, VirtualKeyBoard, title=self.titlu, text=self.text)

	def _dinTastatura(self, text=None):
		if text is None:
			return
		self.text = text.strip()[:MAX_CAUTARE]
		self.inAsteptare = ""
		self._filtreaza()

	def _modAscii(self):
		"""tastatura USB scrie litere (nu taste de telecomanda) cat e deschisa lista; la inchidere, modul de dinainte"""
		try:
			from enigma import eRCInput
			rc = eRCInput.getInstance()
			if self.modTastatura is None:
				self.modTastatura = rc.getKeyboardMode()
			rc.setKeyboardMode(rc.kmAscii)
		except Exception:
			pass

	def _laInchidere(self):
		self.sms.nextKey()
		try:
			if self.modTastatura is not None:
				from enigma import eRCInput
				eRCInput.getInstance().setKeyboardMode(self.modTastatura)
		except Exception:
			pass


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
		<widget source="loc" render="Label" position="30,80" size="940,70" font="Regular;30" halign="center" valign="center" noWrap="1" />
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
		# True cat cautarea e cea pornita singura la deschidere (fara ferestre: numai randul de sus)
		self.singur = False
		self._orasDorit = None
		# ruta spre internet, citita local la deschidere: fara ea optiunea nu apare si nu pleaca nicio cerere
		self.cuInternet = I.retea()
		self["mesaj"] = StaticText(self._mesajRepaus())
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
		# locul dupa internet e cel implicit (LOC2): la deschidere se afla din nou si se scrie fara intrebare
		self.onLayoutFinish.append(self._cautaSingur)

	def _mesajRepaus(self):
		"""randul de sus cand nu se cauta: de ce s-a deschis ecranul, altfel felul locului (dupa internet sau ales)"""
		return self.mesajInitial or I.textFel()

	def _cautaSingur(self):
		if not self.cuInternet or self.cautand or not L.automat():
			return
		if not I.CAUTARE.porneste(scrie=True, actualizeaza_sec=self.actualizeaza_sec):
			return
		self.cautand = True
		self.singur = True
		self["mesaj"].setText(_(I.CAUT))
		self.ceas.start(PAS_MS, True)

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
			self["mesaj"].setText(self._mesajRepaus())
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
		"""omul alege locul dupa internet: de acum e iar cel implicit (si la pornire), iar locul gasit se scrie pe loc"""
		if not self.cuInternet:
			return
		L.alegeInternet()
		if self.cautand:
			# cautarea pornita singura la deschidere continua; rezultatul se arata acum ca pentru o alegere a omului
			self.singur = False
			I.CAUTARE.porneste(scrie=True, actualizeaza_sec=self.actualizeaza_sec)
			return
		self.singur = False
		if not I.CAUTARE.porneste(scrie=True, actualizeaza_sec=self.actualizeaza_sec):
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
		self["mesaj"].setText(self._mesajRepaus())
		self._rezultat(st)

	def _rezultat(self, st):
		"""locul gasit e deja scris (Cautare.porneste(scrie=True)): se arata; un refuz (antena se roteste, o
		inregistrare) sau o eroare (fara internet, serverul nu raspunde): la cautarea pornita singura numai in randul de
		sus, la cea ceruta de om fereastra, apoi lista, ca pana acum"""
		singur, self.singur = self.singur, False
		if st["stare"] == I.GASIT and st.get("scris") is None:
			# omul a ales intre timp singur locul: ramane al lui, fara nicio fereastra
			self._arata()
			return
		if st["stare"] == I.GASIT and st["gasit"] and st.get("scris"):
			self._arata()
			if not singur:
				self._dupa(True, "")
			return
		text = st.get("mesaj_scris") if st["stare"] == I.GASIT else st["mesaj"]
		if singur:
			self["mesaj"].setText(text or self._mesajRepaus())
			return
		if st["stare"] == I.GASIT:
			self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)
			return
		self.session.openWithCallback(lambda *a: self.lista(), MessageBox, st["mesaj"], MessageBox.TYPE_INFO)

	# ---- tara si orasul

	def lista(self, tara=None, oras=None):
		"""lista tarilor; `tara` si `oras` (locul gasit dupa internet, refuzat) sunt alese dinainte"""
		# toata lumea, cu numele in limba meniului si in ordinea lui (LOC1); aleasa dinainte: tara de data trecuta, altfel
		# tara limbii meniului (nu mai e Romania pentru oricine)
		tari = L.tariAfisate()
		curenta = tara or L.taraImplicita()
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
		lista = L.textOrase(orase)
		self.session.openWithCallback(lambda r: self._orasAles(cod, r), HdsLoculAlegere,
			title=_("Alege orașul (%s)") % L.numeTaraAfisat(cod), list=lista, keys=[], selection=ales, cautaInValoare=True)

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
		self.mesajInitial = ""
		self["mesaj"].setText(self._mesajRepaus())
		self._arata()
		self.session.open(MessageBox, _("Locul antenei este acum: %s") % L.textLoc(), MessageBox.TYPE_INFO, timeout=5)


class HdsLoculDeMana(Screen, ConfigListScreen):
	"""longitudinea si latitudinea in grade cu trei zecimale (cifrele telecomenzii), partea fata de Greenwich si fata de
	ecuator. Ordinea randurilor e cea din Setarile tunerului OE-Alliance (Longitude, East/West, Latitude, North/South):
	cine vine din alta imagine scrie numerele in ordinea cu care e obisnuit (asistenta 681415: 30 si 41 scrise invers).
	Sub randuri, locul scris in cuvinte ("41,000 N, 30,000 E"), pus la zi la fiecare schimbare."""
	SKIN = """
	<screen name="HdsLoculDeMana" position="center,center" size="900,440" title="Coordonatele antenei">
		<widget name="config" position="30,30" size="840,200" font="Regular;24" secondfont="Regular;16" itemHeight="48" scrollbarMode="showOnDemand" />
		<widget source="scris" render="Label" position="30,236" size="840,34" font="Regular;22" foregroundColor="#ffc250" />
		<widget source="nota" render="Label" position="30,274" size="840,96" font="Regular;20" />
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
		# gradele tastate ca la calculator: "30" si "030" dau 30 (Components/HdsLocul.py, campGrade; orion_bilo)
		self.lat = NoSave(L.campGrade(L.LAT_MAX // 1000, lat))
		self.nord = NoSave(ConfigSelection([("north", _("Nord")), ("south", _("Sud"))], "north" if lat >= 0 else "south"))
		self.lon = NoSave(L.campGrade(L.LON_MAX // 1000, lon))
		self.est = NoSave(ConfigSelection([("east", _("Est")), ("west", _("Vest"))], "east" if lon >= 0 else "west"))
		lista = [
			getConfigListEntry(_("Longitudinea (grade)"), self.lon),
			getConfigListEntry(_("Față de Greenwich"), self.est),
			getConfigListEntry(_("Latitudinea (grade)"), self.lat),
			getConfigListEntry(_("Față de ecuator"), self.nord),
		]
		ConfigListScreen.__init__(self, lista, session=session)
		self["scris"] = StaticText("")
		for element in (self.lon, self.est, self.lat, self.nord):
			element.addNotifier(self._arataScris, initial_call=False)
		self._arataScris()
		# nota fara Romania (LOC1): imaginea e pentru toata lumea; America e la vest, emisfera sudica la sud
		self["nota"] = StaticText(_(NOTA_DE_MANA))
		self["key_red"] = StaticText(_("Renunță"))
		self["key_green"] = StaticText(_("Salvează"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.salveaza,
			"green": self.salveaza,
			"red": self.renunta,
			"cancel": self.renunta,
		}, -2)

	def _valori(self):
		"""(lat_mii, lon_mii) cu semn, din randuri (nord si est pozitive)"""
		lat = int(self.lat.value[0]) * 1000 + int(self.lat.value[1])
		lon = int(self.lon.value[0]) * 1000 + int(self.lon.value[1])
		return (-lat if self.nord.value == "south" else lat), (-lon if self.est.value == "west" else lon)

	def _arataScris(self, *_a):
		lat, lon = self._valori()
		self["scris"].setText(_("Locul scris: %s") % L.textCoordonate(lat, lon, 3))

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
		# departe de tara receptorului, dar cu emisferele schimbate (sau latitudinea cu longitudinea) aproape: intai
		# intrebarea; "Da" (primul rand) scrie varianta, al doilea rand ce s-a scris, Iesire nu scrie nimic si lasa
		# coordonatele pe ecran (Components/HdsLocul.py, intrebareDeparte; aceeasi intrebare in web)
		intrebare, propus = L.intrebareDeparte(lat, lon)
		if intrebare:
			def raspuns(ales):
				if ales == "propus":
					self._scrie(propus[0], propus[1])
				elif ales == "scris":
					self._scrie(lat, lon)
			self.session.openWithCallback(raspuns, MessageBox, intrebare, MessageBox.TYPE_YESNO,
				list=[(_("Da"), "propus"), (_("Nu, păstrează ce am scris"), "scris")])
			return
		self._scrie(lat, lon)

	def _scrie(self, lat, lon):
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
