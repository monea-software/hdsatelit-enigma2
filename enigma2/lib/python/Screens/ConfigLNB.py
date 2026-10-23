# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ConfigLNB.py - ecranul „Configurare LNB” (meniul „Orientarea și setarea antenei”, a doua intrare).
#
# Un ecran mai simplu pentru ACELEASI date ca „Setări tuner”: citeste si scrie config.Nims[n] (tipul LNB-ului si
# oscilatoarele, tensiunea, tonul de 22 kHz, tensiunea marita, portul DiSEqC, comenzile DiSEqC la 13 V) si le
# aplica nucleului ca „Setări tuner” (nimmanager.sec.update()). Nu mai exista niciun fisier separat: ecranul de
# dinainte scria /etc/enigma2/hdsconfig_lnb.conf, pe care nu il citea nimic, deci nu schimba nimic pe receptor.
#
# Inainte de orice scriere se vede tot ce se schimba (HdsLnbPrevizualizare); dupa aplicare se verifica semnalul pe
# programul care ruleaza, iar setarea ramane numai daca omul raspunde „Da”. „Nu”, EXIT sau 60 de secunde fara
# raspuns = intoarcere la ce era. Logica e in Components/HdsLnb.py (citire, plan) si Components/HdsLnbAplicare.py
# (aplicare, proba, intoarcere), aceleasi si pentru pagina web.

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import ConfigSelection, ConfigInteger, ConfigYesNo, getConfigListEntry
from Components.Label import Label
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components import HdsLnb
from Components import HdsLnbAplicare
from Tools.ScaledSkin import scaledSkin

FARA_TUNER = -1


def _doarCitit(text):
	"""rand care se vede, dar nu se schimba (o singura alegere)"""
	return ConfigSelection(choices=[("x", text)], default="x")


class ConfigLNB(Screen, ConfigListScreen):
	skinName = ["ConfigLNB", "NimSetup"]

	SKIN = """
	<screen name="ConfigLNB" position="center,center" size="1100,640" title="Configurare LNB">
		<widget name="config" position="20,16" size="1060,396" itemHeight="36" font="Regular;24" secondfont="Regular;16" scrollbarMode="showOnDemand" />
		<eLabel position="20,420" size="1060,1" backgroundColor="#4a5560" />
		<widget name="description" position="20,428" size="1060,112" font="Regular;21" foregroundColor="#b8c4ce" />
		<widget source="status" render="Label" position="20,544" size="1060,34" font="Regular;22" foregroundColor="#ffb040" noWrap="1" />
		<eLabel position="20,598" size="6,30" backgroundColor="#c02020" />
		<widget name="key_red" position="34,592" size="250,40" font="Regular;22" valign="center" />
		<eLabel position="300,598" size="6,30" backgroundColor="#20a020" />
		<widget name="key_green" position="314,592" size="250,40" font="Regular;22" valign="center" />
		<eLabel position="580,598" size="6,30" backgroundColor="#c0a000" />
		<widget name="key_yellow" position="594,592" size="250,40" font="Regular;22" valign="center" />
	</screen>
	"""

	def __init__(self, session):
		self.skin = scaledSkin(self.SKIN)
		Screen.__init__(self, session)
		# Screen.__init__ pune skinName = numele clasei (Screen.py:21); skinul HDSatelit nu are „ConfigLNB”, dar are
		# „NimSetup”, ecranul „Setări tuner”, cu aceleasi elemente (config, description, status, tastele)
		self.skinName = ["ConfigLNB", "NimSetup"]
		self.setTitle(_("Configurare LNB"))
		self.lista = []
		ConfigListScreen.__init__(self, self.lista, session=session)

		self["description"] = Label("")
		self["status"] = StaticText("")
		self["key_red"] = Label(_("Închide"))
		self["key_green"] = Label("")
		self["key_yellow"] = Label("")

		# OkCancelActions si ColorActions, inaintea listei (-2), ca la „Setări tuner” (Satconfig.py:420-431):
		# stanga, dreapta si cifrele raman ale listei; toate cele patru culori au o functie, deci nicio tasta nu
		# ajunge in jurnal ca actiune necunoscuta
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self._salveaza,
			"cancel": self._iesire,
			"red": self._iesire,
			"green": self._salveaza,
			"yellow": self._ceEraInainte,
			"blue": self._nimic,
		}, -2)

		self._cutie = None
		self._da_primul = False
		self._aplicat_aici = False
		self._serviciu = HdsLnbAplicare.serviciulCurent()
		self._tunere = HdsLnb.tunereSatelit()
		self._incarca(self._tunere[0] if self._tunere else FARA_TUNER)

		self["config"].onSelectionChanged.append(self._randSchimbat)
		HdsLnbAplicare.laSchimbare(self._aplicareSchimbata)
		self.onClose.append(self._laInchidere)
		self.onLayoutFinish.append(self._laInceput)

	def _laInceput(self):
		# textul marit (Marimea textului peste 100 %): randul listei (36 px) creste cu procentul, ca fontul (de la 125 %
		# literele randului se taiau jos); la 100 % nimic
		try:
			from Components import HdsMarireText as MT
			MT.randuriMarite(self["config"])
		except Exception as e:
			print("[ConfigLNB] textul marit: %s" % e)
		# cursorul porneste pe „Tipul LNB-ului”: acolo e singura alegere pe care o face cei mai multi
		if "tip" in self._chei:
			self["config"].setCurrentIndex(self._chei.index("tip"))
		self._randSchimbat()

	# ------------------------------------------------------------ modelul si ciorna

	def _incarca(self, slot):
		self._slot = slot
		self._el = {}
		if slot == FARA_TUNER:
			self._model = None
			self._alegeri = None
			self._elTuner = _doarCitit(_("niciunul"))
			self["status"].setText(_("Receptorul nu are niciun tuner de satelit."))
		else:
			self._model = HdsLnb.citeste(slot)
			self._alegeri = HdsLnb.alegeriDinModel(self._model)
			alegeri_tuner = []
			for s in self._tunere:
				if s == slot:
					alegeri_tuner.append((str(s), HdsLnb.textMod(self._model)))
				else:
					alegeri_tuner.append((str(s), HdsLnb.numeTuner(s)))
			self._elTuner = ConfigSelection(choices=alegeri_tuner, default=str(slot))
			lnburi = self._model["lnburi"]
			if len(lnburi) > 1:
				self._elLnb = ConfigSelection(choices=[(l["id"], l["eticheta"]) for l in lnburi], default=lnburi[0]["id"])
			else:
				self._elLnb = None
			self._el13V = ConfigYesNo(default=bool(self._model["diseqc13V"]))
			self["status"].setText(self._model["motiv"])
		self._construieste()

	def _lnbCurent(self):
		if not self._model or not self._model["lnburi"]:
			return None
		lnb_id = self._elLnb.value if self._elLnb is not None else self._model["lnburi"][0]["id"]
		for lnb in self._model["lnburi"]:
			if lnb["id"] == lnb_id:
				return lnb
		return self._model["lnburi"][0]

	def _element(self, lnb, camp):
		cheie = (lnb["id"], camp)
		el = self._el.get(cheie)
		if el is not None:
			return el
		if camp == "tip":
			alegeri = [(t, HdsLnb.textTip(t)) for t in HdsLnb.TIPURI_DE_ALES]
			el = ConfigSelection(choices=alegeri, default=lnb["tip"] if lnb["tip"] in HdsLnb.TIPURI_DE_ALES else None)
		elif camp in ("lofl", "lofh", "prag"):
			el = ConfigInteger(default=int(lnb[camp]), limits=(0, HdsLnb.PRAG_MEREU_JOS))
		elif camp == "tensiune":
			alegeri = [(v, HdsLnb.textTensiune(v)) for v in ("polarization", "13V", "18V")]
			if lnb["tensiune"] == HdsLnb.DIFERA:
				alegeri.append((HdsLnb.DIFERA, HdsLnb.textTensiune(HdsLnb.DIFERA)))
			el = ConfigSelection(choices=alegeri, default=lnb["tensiune"])
		elif camp == "ton":
			alegeri = [(v, HdsLnb.textTon(v)) for v in ("band", "on", "off")]
			if lnb["ton"] == HdsLnb.DIFERA:
				alegeri.append((HdsLnb.DIFERA, HdsLnb.textTon(HdsLnb.DIFERA)))
			el = ConfigSelection(choices=alegeri, default=lnb["ton"])
		elif camp == "tensiune_marita":
			el = ConfigYesNo(default=bool(lnb["tensiune_marita"]))
		elif camp == "comanda":
			alegeri = HdsLnb.alegeriPort()
			if lnb["comanda"] not in [a[0] for a in alegeri]:
				alegeri.append((lnb["comanda"], HdsLnb.textPort(lnb["comanda"])))
			el = ConfigSelection(choices=alegeri, default=lnb["comanda"])
		self._el[cheie] = el
		return el

	def _citesteCiorna(self):
		"""valorile randurilor in ciorna (numai cele create; celelalte au ramas ca in tuner)"""
		if not self._model:
			return
		for (lnb_id, camp), el in self._el.items():
			self._alegeri["lnb"][lnb_id][camp] = el.value
		self._alegeri["diseqc13V"] = bool(self._el13V.value)

	def _areSchimbari(self):
		if not self._model or not self._model["editabil"]:
			return False
		self._citesteCiorna()
		return HdsLnb.areSchimbari(self._model, self._alegeri)

	# ------------------------------------------------------------ randurile

	def _construieste(self):
		lista = [getConfigListEntry(_("Tuner"), self._elTuner, "tuner")]
		model = self._model
		lnb = self._lnbCurent()
		if model is not None and model["mod"] in ("simple", "advanced") and lnb is not None:
			simplu = model["mod"] == "simple"
			lista.append(getConfigListEntry(_("Antena"), _doarCitit(model["antena"]), "antena"))
			if self._elLnb is not None:
				lista.append(getConfigListEntry(_("LNB"), self._elLnb, "lnb"))
			if lnb["editabil_tip"]:
				tip = self._element(lnb, "tip")
				lista.append(getConfigListEntry(_("Tipul LNB-ului"), tip, "tip"))
				if tip.value == HdsLnb.TIP_PERSONALIZAT:
					lista.append(getConfigListEntry(_("Oscilator jos (MHz)"), self._element(lnb, "lofl"), "lofl"))
					lista.append(getConfigListEntry(_("Oscilator sus (MHz)"), self._element(lnb, "lofh"), "lofh"))
					lista.append(getConfigListEntry(_("Prag de bandă (MHz)"), self._element(lnb, "prag"), "prag"))
			else:
				lista.append(getConfigListEntry(_("Tipul LNB-ului"), _doarCitit(HdsLnb.textTip(lnb["tip"])), "unicable"))
			if lnb["editabil_rest"] and not simplu:
				lista.append(getConfigListEntry(_("Tensiune"), self._element(lnb, "tensiune"), "tensiune"))
				lista.append(getConfigListEntry(_("Ton 22 kHz"), self._element(lnb, "ton"), "ton"))
				lista.append(getConfigListEntry(_("Tensiune mărită (cablu lung)"), self._element(lnb, "tensiune_marita"),
					"tensiune_marita"))
			else:
				lista.append(getConfigListEntry(_("Tensiune"), _doarCitit(HdsLnb.textTensiune(lnb["tensiune"])), "fix"))
				lista.append(getConfigListEntry(_("Ton 22 kHz"), _doarCitit(HdsLnb.textTon(lnb["ton"])), "fix"))
			if lnb["editabil_port"] and not simplu:
				lista.append(getConfigListEntry(_("Port DiSEqC"), self._element(lnb, "comanda"), "port"))
			else:
				lista.append(getConfigListEntry(_("Port DiSEqC"), _doarCitit(HdsLnb.textDiseqc(lnb)), "fix"))
			lista.append(getConfigListEntry(_("Comenzi DiSEqC la 13 V"), self._el13V, "diseqc13V"))
			self._citesteCiorna()
			dupa = HdsLnb.lnbDupaAlegeri(model, self._alegeri, lnb["id"])
			lista.append(getConfigListEntry(_("Probă de calcul"), _doarCitit(HdsLnb.probaDeCalcul(dupa, _nm(),
				self._serviciu, model)), "proba"))
		index = self["config"].getCurrentIndex() if self.lista else 0
		# ConfigList cheama onSelectionChanged numai pentru randuri de doua elemente (ConfigList.py:62-71), deci
		# cheia de ajutor a fiecarui rand sta alaturi, nu in rand
		self._chei = [r[2] for r in lista]
		lista = [(r[0], r[1]) for r in lista]
		self.lista = lista
		self["config"].list = lista
		if self.instance is not None and index:
			self["config"].setCurrentIndex(min(index, len(lista) - 1))
		self._taste()

	def _taste(self):
		faza = HdsLnbAplicare.stare()["faza"]
		if faza != HdsLnbAplicare.LIBER and self._aplicat_aici:
			# in cele 3,5 s de dupa raspuns (REVENIRE) nu mai e nimic de intors: rosu inchide ecranul, iar programul
			# porneste singur, pe ceasul modulului
			self["key_red"].setText(_("Închide") if faza == HdsLnbAplicare.REVENIRE else _("Revin la ce era"))
			self["key_green"].setText("")
			self["key_yellow"].setText("")
			return
		self["key_red"].setText(_("Închide"))
		editabil = bool(self._model and self._model["editabil"])
		self["key_green"].setText(_("Save") if editabil else "")
		copie = self._slot != FARA_TUNER and HdsLnbAplicare.areCopieDeDinainte(self._slot)
		self["key_yellow"].setText(_("Ce era înainte") if copie else "")

	def _cheieCurenta(self):
		index = self["config"].getCurrentIndex()
		chei = getattr(self, "_chei", [])
		return chei[index] if index is not None and 0 <= index < len(chei) else ""

	def _randSchimbat(self):
		self["description"].setText(self._ajutor(self._cheieCurenta()))

	def _ajutor(self, cheie):
		simplu = bool(self._model and self._model["mod"] == "simple")
		if cheie == "tip":
			el = self._el.get((self._lnbCurent()["id"], "tip"))
			if simplu and el is not None and el.value != HdsLnb.TIP_UNIVERSAL:
				return _("În modul simplu, receptorul lucrează numai cu LNB universal. Dacă alegi alt tip, tunerul "
					"trece în modul avansat, cu aceiași sateliți și același motor. Vezi tot ce se schimbă înainte de salvare.")
			return _("Universal: aproape toate antenele Ku din România. Un oscilator: LNB vechi cu o singură frecvență. "
				"Banda C: antenele mari de bandă C. Personalizat: scrie valorile de pe eticheta LNB-ului.")
		if cheie in ("lofl", "lofh"):
			return _("Frecvența oscilatorului local, scrisă pe LNB, în MHz.")
		if cheie == "prag":
			return _("Peste această frecvență, receptorul folosește oscilatorul de sus și pornește tonul de 22 kHz.")
		if cheie == "tensiune":
			return _("13 V alege polarizarea verticală, 18 V pe cea orizontală. Lasă „după polarizare”, în afară de "
				"cazul în care un comutator cere altceva.")
		if cheie == "ton":
			return _("Tonul de 22 kHz alege banda de sus la LNB-ul universal sau ieșirea unui comutator de 22 kHz.")
		if cheie == "tensiune_marita":
			return _("Ridică puțin tensiunea spre LNB, pentru cabluri lungi. Cât anume, hotărăște placa tunerului.")
		if cheie == "port":
			return _("Portul comutatorului DiSEqC la care e legat acest LNB.")
		if cheie == "diseqc13V":
			return _("Trimite comenzile DiSEqC la 13 V. Unele comutatoare și motoare o cer.")
		if cheie == "proba":
			return _("Ce face receptorul pentru un transponder de pe acest satelit: frecvența intermediară, tensiunea "
				"și tonul.")
		if cheie == "unicable":
			return _("LNB-ul Unicable se configurează din Setări tuner.")
		if cheie in ("antena", "lnb", "fix"):
			return _("Comutatorul, sateliții și motorul se schimbă din Setări tuner.")
		if cheie == "tuner" and len(self._tunere) > 1:
			return _("Alege tunerul cu stânga și dreapta.")
		return ""

	# ------------------------------------------------------------ tastele listei

	def _ocupat(self):
		return self._aplicat_aici and HdsLnbAplicare.stare()["faza"] != HdsLnbAplicare.LIBER

	def keyLeft(self):
		if self._ocupat():
			return
		ConfigListScreen.keyLeft(self)
		self._dupaTasta()

	def keyRight(self):
		if self._ocupat():
			return
		ConfigListScreen.keyRight(self)
		self._dupaTasta()

	def keyNumberGlobal(self, number):
		if self._ocupat():
			return
		ConfigListScreen.keyNumberGlobal(self, number)
		self._dupaTasta()

	def _dupaTasta(self):
		cheie = self._cheieCurenta()
		if cheie == "tuner" and self._model is not None:
			nou = int(self._elTuner.value)
			if nou != self._slot:
				if self._areSchimbari():
					self._elTuner.value = str(self._slot)
					self["config"].invalidateCurrent()
					self["status"].setText(_("Salvează sau renunță întâi la schimbările de pe tunerul %s.")
						% self._model["litera"])
					return
				self._incarca(nou)
				self._randSchimbat()
			return
		self._construieste()
		self._randSchimbat()
		if self._model is not None and self._model["editabil"]:
			self["status"].setText("")

	# ------------------------------------------------------------ salvare, previzualizare, aplicare

	def _nimic(self):
		pass

	def _salveaza(self):
		if self._ocupat() or not self._model:
			return
		if not self._model["editabil"]:
			self["status"].setText(self._model["motiv"])
			return
		self._citesteCiorna()
		if not HdsLnb.areSchimbari(self._model, self._alegeri):
			self["status"].setText(_("Nu ai schimbat nimic."))
			return
		greseala = HdsLnb.valideaza(self._model, self._alegeri)
		if greseala:
			self["status"].setText(greseala)
			return
		ocupat = HdsLnbAplicare.motivOcupat(self.session, eu=self)
		if ocupat:
			self["status"].setText(ocupat)
			return
		plan = HdsLnb.planifica(self._model, self._alegeri, _nm(), self._serviciu)
		self.session.openWithCallback(self._dupaPrevizualizare, HdsLnbPrevizualizare, plan)

	def _ceEraInainte(self):
		if self._ocupat() or self._slot == FARA_TUNER:
			return
		if self._areSchimbari():
			self["status"].setText(_("Salvează sau renunță întâi la schimbările de pe tunerul %s.") % self._model["litera"])
			return
		plan = HdsLnbAplicare.planCeEraInainte(self._slot)
		if plan is None:
			self["status"].setText(_("Nu am setări de dinainte pentru acest tuner."))
			return
		ocupat = HdsLnbAplicare.motivOcupat(self.session, eu=self)
		if ocupat:
			self["status"].setText(ocupat)
			return
		self.session.openWithCallback(self._dupaPrevizualizare, HdsLnbPrevizualizare, plan)

	def _dupaPrevizualizare(self, plan=None):
		if not plan:
			return
		self._aplicat_aici = True
		reusit, motiv = HdsLnbAplicare.aplica(plan, "televizor")
		if not reusit:
			self._aplicat_aici = False
			self["status"].setText(motiv)
			self._reciteste()
			return
		self._aplicareSchimbata()

	def _aplicareSchimbata(self):
		"""ascultatorul modulului: proba, numaratoarea, pastrarea sau intoarcerea"""
		st = HdsLnbAplicare.stare()
		if not self._aplicat_aici:
			# schimbare pornita din pagina web: tunerul arata aici poate fi altul decat cel de acum
			if st["faza"] == HdsLnbAplicare.LIBER and not self._areSchimbari():
				self._reciteste()
			return
		faza = st["faza"]
		if faza == HdsLnbAplicare.PROBA:
			self["status"].setText(HdsLnbAplicare.APLICARE.textProba())
		elif faza == HdsLnbAplicare.CONFIRMARE:
			# caseta de mesaj a skinului are loc de trei randuri (skin.xml, HdsMessageBoxBase): sus rezultatul probei
			# si intrebarea, iar numaratoarea sta chiar in alegerea „Nu”, ca sa se vada mereu
			if self._cutie is None:
				# fara timeout-ul lui MessageBox: la expirare el apasa singur OK pe randul ales (MessageBox.py:103-110);
				# ceasul de 60 s e al modulului, care revine singur si inchide intrebarea de aici
				self._da_primul = HdsLnbAplicare.APLICARE.raspunsImplicit()
				text = "%s\n%s" % (HdsLnbAplicare.APLICARE.textProba(), _("Păstrezi noile setări?"))
				self._cutie = self.session.openWithCallback(self._raspuns, HdsLnbIntrebare, text, MessageBox.TYPE_YESNO,
					default=self._da_primul)
			if self._cutie is not None:
				self._cutie.puneAlegeri(self._alegeriIntrebare(st["secunde"]))
			self["status"].setText(HdsLnbAplicare.APLICARE.textProba())
		else:
			cutie = self._cutie
			self._cutie = None
			# se inchide numai daca e deasupra (Session.close cere asta, mytest.py:361); altfel raspunsul la ea
			# nu mai face nimic, fiindca pastreaza/revino nu mai au ce sa faca
			if cutie is not None and self.session.current_dialog is cutie:
				cutie.close(None)
			if faza == HdsLnbAplicare.LIBER:
				self._aplicat_aici = False
				self._reciteste()
			self["status"].setText(st["mesaj"])
		self._taste()

	def _alegeriIntrebare(self, secunde):
		"""aceleasi valori ca MessageBox (0 = da, 1 = nu, MessageBox.py:40-44 si 115-117), cu textul spus pe larg"""
		da = (_("Da, păstrez noile setări"), 0)
		nu = (_("Nu, revin la ce era (%d s)") % max(0, secunde), 1)
		return [da, nu] if self._da_primul else [nu, da]

	def _raspuns(self, raspuns):
		if raspuns is None:
			return
		self._cutie = None
		rezultat = HdsLnbAplicare.pastreaza() if raspuns else HdsLnbAplicare.revino("om")
		if rezultat is None:
			# intrebarea ramasese sub alt ecran (de exemplu standby), iar intre timp modulul a revenit singur: se
			# spune ce s-a intamplat, nu se pastreaza nimic
			self["status"].setText(HdsLnbAplicare.stare()["mesaj"])

	def _reciteste(self):
		mesaj = self["status"].getText()
		self._serviciu = HdsLnbAplicare.serviciulCurent()
		self._incarca(self._slot)
		if mesaj and self._model and self._model["editabil"]:
			self["status"].setText(mesaj)
		self._randSchimbat()

	# ------------------------------------------------------------ iesirea

	def _iesire(self):
		if self._ocupat():
			if HdsLnbAplicare.stare()["faza"] == HdsLnbAplicare.REVENIRE:
				# raspunsul e dat; modulul porneste singur programul peste cel mult 3,5 s, cu ecranul inchis sau nu
				self.close()
				return
			# in timpul probei sau al intrebarii, rosu si EXIT inseamna „revin la ce era”
			HdsLnbAplicare.revino("om")
			return
		if self._areSchimbari():
			self.session.openWithCallback(self._dupaIntrebareIesire, HdsLnbIntrebare, _("Închizi fără să salvezi?"),
				MessageBox.TYPE_YESNO, default=False)
			return
		self.close()

	def _dupaIntrebareIesire(self, raspuns):
		if raspuns:
			self.close()

	def _laInchidere(self):
		HdsLnbAplicare.faraAscultator(self._aplicareSchimbata)
		try:
			self["config"].onSelectionChanged.remove(self._randSchimbat)
		except ValueError:
			pass


def _nm():
	from Components.NimManager import nimmanager
	return nimmanager


class HdsLnbIntrebare(MessageBox):
	"""MessageBox, cu acelasi skin, dar fara „unknown action ... typo in keymap?” in jurnal: MessageBox se aboneaza
	la DirectionActions (MessageBox.py:53-66), iar harta trimite si ridicarea tastelor (leftUp, rightUp, upUp,
	downUp, keymap.xml), pentru care el nu are nicio functie."""

	def __init__(self, session, *argumente, **optiuni):
		MessageBox.__init__(self, session, *argumente, **optiuni)
		self.skinName = "MessageBox"
		actiuni = self.get("actions")
		if actiuni is not None and isinstance(getattr(actiuni, "actions", None), dict):
			for nume in ("leftUp", "rightUp", "upUp", "downUp"):
				actiuni.actions.setdefault(nume, self._nimic)

	def puneAlegeri(self, alegeri):
		"""alegerile cu textul lor, in aceeasi ordine si cu aceleasi valori ca ale MessageBox; randul ales ramane"""
		self.list = alegeri
		try:
			self["list"].setList(alegeri)
		except Exception:
			pass

	def _nimic(self):
		pass


class _TextDerulat(ScrollLabel):
	"""ScrollLabel care nu da atributul scrollbarMode al skinului mai departe etichetei: ScrollLabel pune toate
	atributele pe eLabel (ScrollLabel.py:19), iar eLabel nu il are, deci jurnalul ar primi „[Skin] eLabel: attribute
	scrollbarMode ... not applied”. Bara de derulare o deseneaza ScrollLabel oricum."""

	def applySkin(self, desktop, parent):
		if self.skinAttributes is not None:
			self.skinAttributes = [(a, v) for (a, v) in self.skinAttributes if a != "scrollbarMode"]
		return ScrollLabel.applySkin(self, desktop, parent)


class HdsLnbPrevizualizare(Screen):
	"""„Ce se schimbă”: randurile pentru om, avertismentele, motivul pentru care nu se poate aplica, iar jos fiecare
	cale din config.Nims.N cu valoarea de dinainte si de dupa. Verde „Aplică” inchide cu planul, rosu/EXIT fara."""
	skinName = ["HdsLnbPrevizualizare", "TextBox"]

	SKIN = """
	<screen name="HdsLnbPrevizualizare" position="center,center" size="1100,640" title="Ce se schimbă">
		<widget name="text" position="20,16" size="1060,560" font="Regular;22" />
		<eLabel position="20,598" size="6,30" backgroundColor="#c02020" />
		<widget name="key_red" position="34,592" size="250,40" font="Regular;22" valign="center" />
		<eLabel position="300,598" size="6,30" backgroundColor="#20a020" />
		<widget name="key_green" position="314,592" size="250,40" font="Regular;22" valign="center" />
	</screen>
	"""

	def __init__(self, session, plan):
		self.skin = scaledSkin(self.SKIN)
		Screen.__init__(self, session)
		self.skinName = ["HdsLnbPrevizualizare", "TextBox"]
		self.plan = plan
		self.setTitle(_("Ce era înainte") if plan.get("fel") == "inainte" else _("Ce se schimbă"))
		randuri = []
		if plan.get("oprire"):
			randuri.append(plan["oprire"])
			randuri.append("")
		randuri.extend(plan.get("rezumat") or [])
		if plan.get("avertismente"):
			randuri.append("")
			randuri.extend(plan["avertismente"])
		if not plan.get("oprire"):
			randuri.append("")
			randuri.append(_("După aplicare verific semnalul pe canalul care rulează, apoi te întreb dacă păstrezi "
				"setările. Dacă nu răspunzi în %d de secunde, revin singur la ce era.") % HdsLnbAplicare.SECUNDE_CONFIRMARE)
		detalii = HdsLnb.detalii(plan)
		if detalii:
			randuri.append("")
			randuri.append(_("Detalii"))
			randuri.extend(detalii)
		self["text"] = _TextDerulat("\n".join(randuri))
		self["key_red"] = Label(_("Înapoi"))
		self["key_green"] = Label("" if plan.get("oprire") else _("Aplică"))
		fara = self._nimic
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self._aplica,
			"cancel": self._inapoi,
			"red": self._inapoi,
			"green": self._aplica,
			"yellow": fara,
			"blue": fara,
			"up": self["text"].pageUp,
			"down": self["text"].pageDown,
			"upRepeated": self["text"].pageUp,
			"downRepeated": self["text"].pageDown,
			"left": self["text"].pageUp,
			"right": self["text"].pageDown,
			"leftRepeated": self["text"].pageUp,
			"rightRepeated": self["text"].pageDown,
			"upUp": fara,
			"downUp": fara,
			"leftUp": fara,
			"rightUp": fara,
		}, -1)

	def _nimic(self):
		pass

	def _aplica(self):
		if self.plan.get("oprire"):
			return
		self.close(self.plan)

	def _inapoi(self):
		self.close(None)
