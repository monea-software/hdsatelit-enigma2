# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPornireMultipla.py: lista imaginilor din meniul de oprire, pentru
# receptoare cu bootoptions sau kexec instalat (SystemInfo["HdsMultiboot"]).
#
# La deschidere ecranul cauta imaginile instalate in memorie, pe card, pe stick si pe HDD (Components/HdsPornireMultipla.py:
# STARTUP_N de pe partitia bootoptions sau, la Vu+ 4K cu kexec, de pe radacina flash de la /boot, cu Recovery ca locul 0,
# nucleul si sistemul fiecarui loc), pe un fir separat, ca interfata sa nu stea, si le arata, oricare ar fi locul pornit,
# cu imaginea pornita acum marcata; locurile goale nu apar. OK (sau VERDE) pe o imagine: o intrebare scurta, apoi
# STARTUP scris sigur si repornirea receptorului in ea. Daca la repornire receptorul intreaba (o inregistrare, o lucrare) si
# raspunzi Nu, STARTUP se pune la loc. Un loc care nu se alege spune de ce pe rand, iar OK arata motivul intreg. Cat ecranul
# e deschis, lista se reface singura cand se pune sau se scoate un disc. ROSU inchide. Aceeasi lista si aceeasi alegere in
# web: cardul flash din /alimentare (HdsWebControl/alimentare_web.py).
# Caseta notei are loc si pentru explicatia pornirii cazute, cu litere marite.
# Pe receptoarele cu incarcatorul producatorului in STARTUP_RECOVERY (SF8008, Viper 4K V10 si inruditele) ultimul rand e
# "Porneste in incarcator": o intrebare, apoi o singura pornire in incarcator (Components/HdsPornireMultipla.
# pornesteIncarcator); la Nu pe ecranul de repornire se pune la loc numai STARTUP_ONCE.

import threading
import time

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components import HdsPornireMultipla as P


class HdsPornireMultipla(Screen):
	skin = """
	<screen name="HdsPornireMultipla" resolution="1920,1080" position="72,40" size="1240,1000" backgroundColor="hdsPanelDialog" flags="wfNoBorder" title="Repornește în altă imagine">
		<panel name="HdsCadru1240" />
		<widget name="lista" position="32,104" size="1176,536" itemHeight="56" font="HdsRegular;32" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" scrollbarMode="showOnDemand" textOffset="16,0" zPosition="2" />
		<eLabel position="32,652" size="1176,1" backgroundColor="hdsDivider" zPosition="1" />
		<widget source="nota" render="Label" position="32,664" size="1176,252" font="HdsRegular;26" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" halign="left" valign="top" zPosition="1" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["HdsPornireMultipla"]
		self.setTitle(_(P.TITLU))
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText("")
		self["lista"] = MenuList([])
		self["nota"] = StaticText(_(P.CAUT))
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.alege,
			"green": self.alege,
			"cancel": self.close,
			"red": self.close,
		}, -2)
		self.stare = {"locuri": []}
		self.citire = None      # ce intoarce firul citirii cat merge
		self.semn = None        # discurile puse la ultima citire
		self.inchis = False
		self._semnCompatibil = callable(getattr(P, "semnDiscuri", None))
		self["lista"].onSelectionChanged.append(self.butoane)
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.citeste)
		self.ceasFir = eTimer()
		self.ceasFir.callback.append(self.veziFirul)
		self.ceasDiscuri = eTimer()
		self.ceasDiscuri.callback.append(self.veziDiscurile)
		self.onClose.append(self.opresteCeasurile)
		self.ceas.start(50, True)

	def opresteCeasurile(self):
		self.inchis = True
		self.citire = None
		self.ceas.stop()
		self.ceasFir.stop()
		self.ceasDiscuri.stop()

	def citeste(self, verifica=False):
		"""Citirea listei pe un fir: mounturile si citirile de pe card nu tin interfata pe loc."""
		if self.inchis or self.citire is not None:
			return
		self.citire = citire = {}
		semnVechi = self.semn
		stareVeche = self.stare
		semnCompatibil = self._semnCompatibil

		def lucreaza():
			inceput = time.time()
			try:
				semn = P.semnDiscuri() if semnCompatibil else None
				citire["semn"] = semn
				if verifica and semn == semnVechi and not stareVeche.get("eroare") and not stareVeche.get("indisponibil"):
					citire["neschimbat"] = True
					stare = stareVeche
				elif P.disponibil():
					stare = P.locuri()
				else:
					stare = {"locuri": [], "indisponibil": True}
			except Exception as e:
				print("[HdsPornireMultipla] %s" % type(e).__name__)
				stare = {"locuri": [], "eroare": True, "verificare_esuata": True}
			print("[HdsPornireMultipla] lista: %d locuri in %d ms" % (len(stare["locuri"]), (time.time() - inceput) * 1000))
			citire["stare"] = stare

		fir = threading.Thread(target=lucreaza, name="HdsPornireMultipla")
		fir.daemon = True
		try:
			fir.start()
		except RuntimeError:
			citire["stare"] = {"locuri": [], "eroare": True, "verificare_esuata": True}
		self.ceasFir.start(100, False)

	def veziFirul(self):
		if self.inchis or self.citire is None or "stare" not in self.citire:
			return
		self.ceasFir.stop()
		self.semn = self.citire.get("semn")
		neschimbat = self.citire.get("neschimbat", False)
		self.stare, self.citire = self.citire["stare"], None
		if neschimbat:
			return
		ales = self._ales()
		randuri = [(text, l) for text, l in zip(P.randuri(self.stare), self.stare["locuri"])]
		if self.stare.get("incarcator"):
			randuri.append((self.stare["incarcator"]["imagine"], self.stare["incarcator"]))
		self["lista"].setList(randuri)
		if ales:
			for i, (_text, l) in enumerate(randuri):
				if l["loc"] == ales["loc"]:
					self["lista"].moveToIndex(i)
					break
		if self._semnCompatibil and not self.stare.get("indisponibil") and not self.stare.get("verificare_esuata"):
			self["nota"].setText(P.nota(self.stare))
		else:
			nota = P.nota(self.stare)
			if self.stare.get("indisponibil"):
				nota = _("Pornirea multiplă nu este disponibilă acum.")
			elif self.stare.get("verificare_esuata"):
				nota = _("Nu am putut verifica pornirea multiplă. Nu se poate alege altă imagine acum.")
			if not self._semnCompatibil:
				nota = _("Ecranul și componenta pornirii multiple nu au aceeași versiune. Lista se poate citi, dar schimbarea discurilor nu se urmărește automat.") + "\n\n" + nota
			self["nota"].setText(nota)
		self.butoane()
		if self._semnCompatibil:
			self.ceasDiscuri.start(2000, False)

	def veziDiscurile(self):
		"""S-a pus sau s-a scos un disc: lista se reface, ca omul sa nu aiba de deschis ecranul din nou."""
		if self._semnCompatibil:
			self.citeste(verifica=True)

	def _ales(self):
		rand = self["lista"].getCurrent()
		return rand[1] if rand else None

	def butoane(self):
		l = self._ales()
		self["key_green"].setText(_(P.BUTON) if l and l.get("alegere") else "")

	def alege(self):
		from Screens.MessageBox import MessageBox
		if self.inchis:
			return
		l = self._ales()
		if not l:
			return
		if l.get("acum"):
			self.session.open(MessageBox, _(P.DEJA), MessageBox.TYPE_INFO, timeout=5)
			return
		if not l.get("alegere"):
			self.session.open(MessageBox, P.textRefuz(l), MessageBox.TYPE_ERROR, timeout=10)
			return
		if l.get("fel") == "incarcator":
			date = l.get("date")
			self.session.openWithCallback(lambda da: self.confirmatIncarcator(da, date), MessageBox,
				_(P.INTREBARE_INCARCATOR), MessageBox.TYPE_YESNO, default=True)
			return
		asteptat = (l.get("date"), l["imagine"])
		self.session.openWithCallback(lambda da, loc=l["loc"]: self.confirmat(da, loc, asteptat), MessageBox,
			_(P.INTREBARE) % l["imagine"], MessageBox.TYPE_YESNO, default=True)

	def confirmatIncarcator(self, da, date):
		if not da or self.inchis:
			return
		# scrierea pe un fir (Components/HdsPornireMultipla.pornesteIncarcator); o greseala vine inapoi in dupaIncarcator
		ok, text = P.pornesteIncarcator(self.session, asteptat=date, rezultat=self.dupaIncarcator)
		if not ok:
			self.dupaIncarcator(ok, text)

	def dupaIncarcator(self, ok, text):
		if ok or self.inchis:
			return
		from Screens.MessageBox import MessageBox
		self.session.open(MessageBox, text, MessageBox.TYPE_ERROR, timeout=10)
		self.citeste()

	def confirmat(self, da, loc, asteptat=None):
		if not da or self.inchis:
			return
		ok, text = P.reporneste(self.session, loc, asteptat=asteptat)
		if not ok:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, text, MessageBox.TYPE_ERROR, timeout=10)
			self.citeste()


class HdsKexecInstalare(Screen):
	"""Pornire multipla Vu+ (Kexec), din meniul Putere numai pe Vu+ 4K pornit direct din flash, fara pornire multipla
	(SystemInfo["HdsKexecInstalabil"]). VERDE: aduce pachetul kexec-multiboot-<masina> din feedul extern (daca nu e deja),
	o singura intrebare, apoi Components/HdsPornireMultipla.kexecInstaleaza (verificarile si scrierea, acolo) si
	repornirea. Aceeasi instalare in web: cardul kexec din /alimentare (HdsWebControl/alimentare_web.py)."""
	skin = """
	<screen name="HdsKexecInstalare" resolution="1920,1080" position="center,center" size="1240,560" title="Pornire multiplă Vu+ (Kexec)">
		<widget source="nota" render="Label" position="30,25" size="1180,450" font="Regular;28" halign="left" valign="top" />
		<widget source="key_red" render="Label" position="30,505" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="310,505" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_(P.KEXEC_TITLU))
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText("")
		self["nota"] = StaticText("")
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.instaleaza,
			"green": self.instaleaza,
			"cancel": self.inchide,
			"red": self.inchide,
		}, -2)
		self.lucreaza = False
		self.arata()

	def arata(self):
		st = P.kexecStare()
		self.stare = st
		if st["instalabil"]:
			self["nota"].setText(_(P.KEXEC_DESPRE))
			self["key_green"].setText(_(P.KEXEC_BUTON))
		else:
			self["nota"].setText(_(st["motiv"]))
			self["key_green"].setText("")

	def inchide(self):
		if not self.lucreaza:
			self.close()

	def instaleaza(self):
		from Screens.MessageBox import MessageBox
		if self.lucreaza or not self.stare.get("instalabil"):
			return
		self.session.openWithCallback(self.confirmat, MessageBox, _(P.KEXEC_INTREBARE), MessageBox.TYPE_YESNO,
			default=False)

	def confirmat(self, da):
		if not da:
			return
		self.lucreaza = True
		self["key_green"].setText("")
		if P.kexecStare()["fisiere"]:
			self.scrie()
			return
		self["nota"].setText(_(P.KEXEC_DESCARC))
		from Components.Console import Console
		self.consola = Console()
		self.consola.ePopen(P.kexecComandaPachet(self.stare["masina"]), self.descarcat)

	def descarcat(self, rezultat, cod, *_a):
		print("[HdsKexecInstalare] opkg: %r" % (cod,))
		if not P.kexecStare()["fisiere"]:
			self.lucreaza = False
			self.arata()
			self["nota"].setText(_(P.KEXEC_FARA_PACHET))
			return
		self.scrie()

	def scrie(self):
		self["nota"].setText(_(P.KEXEC_SCRIU))
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.scrieAcum)
		self.ceas.start(300, True)   # textul apare inainte de scrierea partitiei (o secunda sau doua)

	def scrieAcum(self):
		ok, text = P.kexecInstaleaza()
		self["nota"].setText(text)
		if not ok:
			self.lucreaza = False
			return
		from Screens.Standby import TryQuitMainloop
		self.session.open(TryQuitMainloop, 2)


class HdsPornireStick(Screen):
	"""Imagini pe stick, numai pe ZGEMMA H8.2H Plus / H8.2H SE (SystemInfo["HdsPornireStick"]; Components/HdsPornireStick.py).
	Lista: memoria interna si locurile linuxrootfsN de pe stick, cu numele si versiunea fiecarei imagini. OK/VERDE: porneste
	imaginea de acum inainte (repornire); GALBEN: o singura data; ALBASTRU: sterge locul; MENU: pune o imagine intr-un loc
	liber (din feedul nostru, dintr-o arhiva de pe stick sau de la o adresa; cu sau fara setarile de acum) sau pregateste
	stickul (singura intrebare: sterge stickul). Citirea listei si lucrarile lungi merg pe fire; nota arata progresul.
	Aceleasi lucruri in web: cardul stick din /alimentare (HdsWebControl/alimentare_web.py)."""
	skin = """
	<screen name="HdsPornireStick" resolution="1920,1080" position="72,40" size="1240,1000" backgroundColor="hdsPanelDialog" flags="wfNoBorder" title="Imagini pe stick">
		<panel name="HdsCadru1240" />
		<widget name="lista" position="32,104" size="1176,560" itemHeight="56" font="HdsRegular;30" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" scrollbarMode="showOnDemand" textOffset="16,0" zPosition="2" />
		<eLabel position="32,676" size="1176,1" backgroundColor="hdsDivider" zPosition="1" />
		<widget source="nota" render="Label" position="32,688" size="1176,228" font="HdsRegular;26" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" halign="left" valign="top" zPosition="1" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		from Components import HdsPornireStick as S
		self.S = S
		self.skinName = ["HdsPornireStick"]
		self.setTitle(_(S.TITLU))
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText("")
		self["key_yellow"] = StaticText("")
		self["key_blue"] = StaticText("")
		self["key_menu"] = StaticText(_("Mai mult"))
		self["lista"] = MenuList([])
		self["nota"] = StaticText(_(S.CAUT))
		self["actions"] = ActionMap(["SetupActions", "ColorActions", "MenuActions"], {
			"ok": lambda: self.porneste(False),
			"green": lambda: self.porneste(False),
			"yellow": lambda: self.porneste(True),
			"blue": self.sterge,
			"menu": self.meniu,
			"cancel": self.close,
			"red": self.close,
		}, -2)
		self.stare = {"locuri": []}
		self.citire = None
		self.inchis = False
		self.lucram = False
		self.rezultat = ""
		self["lista"].onSelectionChanged.append(self.butoane)
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.veziFirul)
		self.onClose.append(self.opreste)
		if self.S.stareLucrare()["lucreaza"]:
			self.lucram = True
			self.ceas.start(500, False)
		else:
			self.citeste()

	def opreste(self):
		self.inchis = True
		self.ceas.stop()

	def citeste(self):
		if self.inchis or self.citire is not None:
			return
		self.citire = citire = {}

		def lucreaza():
			try:
				citire["stare"] = self.S.locuri()
			except Exception as e:
				print("[HdsPornireStick] %r" % (e,))
				citire["stare"] = {"locuri": [], "eroare": True}
		fir = threading.Thread(target=lucreaza, name="HdsPornireStick")
		fir.daemon = True
		fir.start()
		self.ceas.start(300, False)

	def veziFirul(self):
		if self.inchis:
			return
		l = self.S.stareLucrare()
		if l["lucreaza"]:
			self.lucram = True
			self["nota"].setText(l["text"])
			return
		if self.lucram:
			# lucrarea s-a terminat: rezultatul ramane deasupra notei, lista se reciteste
			self.lucram = False
			self.rezultat = l["text"]
			self.citire = None
			self.citeste()
			return
		if self.citire is None or "stare" not in self.citire:
			return
		self.stare, self.citire = self.citire["stare"], None
		self.ceas.stop()
		ales = self._ales()
		randuri = list(zip(self.S.randuri(self.stare), self.stare["locuri"]))
		self["lista"].setList(randuri)
		if ales:
			for i, (_t, x) in enumerate(randuri):
				if x["loc"] == ales["loc"]:
					self["lista"].moveToIndex(i)
		nota = self.S.nota(self.stare)
		self["nota"].setText((self.rezultat + "\n" + nota) if self.rezultat else nota)
		self.rezultat = ""
		self.butoane()

	def _ales(self):
		r = self["lista"].getCurrent()
		return r[1] if r else None

	def butoane(self):
		l = self._ales() or {}
		de_acum = l.get("porneste") or (l.get("acum") and not l.get("implicit") and self.stare.get("stick"))
		self["key_green"].setText(_("Pornește de acum") if de_acum else "")
		self["key_yellow"].setText(_("Pornește o dată") if l.get("porneste") else "")
		self["key_blue"].setText(_("Șterge locul") if l.get("sterge") else "")

	def porneste(self, o_data):
		from Screens.MessageBox import MessageBox
		l = self._ales()
		if not l or self.lucram:
			return
		if l.get("acum") and (o_data or l.get("implicit")):
			self.session.open(MessageBox, _(self.S.DEJA), MessageBox.TYPE_INFO, timeout=5)
			return
		if not l.get("acum") and not l.get("porneste"):
			self.session.open(MessageBox, _(self.S.NU_PORNESTE) % l["loc"], MessageBox.TYPE_ERROR, timeout=8)
			return
		# fara intrebare (Eduard: singura intrebare e la stergerea stickului); TryQuitMainloop intreaba singur la o
		# inregistrare in curs, iar Nu acolo pune la loc STARTUP (HdsPornireStick.inapoi)
		ok, text = self.S.reporneste(self.session, l["loc"], o_data, dupa_ms=2500)
		self.session.open(MessageBox, text, MessageBox.TYPE_INFO if ok else MessageBox.TYPE_ERROR, timeout=3 if ok else 8)
		if not ok or l.get("acum"):
			self.citeste()

	def sterge(self):
		l = self._ales()
		if not l or not l.get("sterge") or self.lucram:
			return
		loc = l["loc"]
		self._lucreaza("sterge", lambda: self.S.stergeLoc(loc))

	def _lucreaza(self, ce, functie):
		from Screens.MessageBox import MessageBox
		ok, text = self.S.pornesteLucrare(ce, functie)
		if not ok:
			self.session.open(MessageBox, text, MessageBox.TYPE_ERROR, timeout=5)
			return
		self.lucram = True
		self["nota"].setText(text)
		self.ceas.start(500, False)

	def meniu(self):
		if self.lucram:
			return
		from Screens.ChoiceBox import ChoiceBox
		alegeri = []
		if self.stare.get("stick"):
			alegeri += [(_(self.S.SURSA_FEED), "feed"), (_(self.S.SURSA_ZIP), "zip"), (_(self.S.SURSA_ADRESA), "adresa")]
		for d in self.stare.get("discuri", []):
			alegeri.append(("%s %s (%s, %s)" % (_("Pregătește stickul"), d["disc"], d["nume"] or "USB",
				self.S._marimeText(d["marime"])), "pregateste:" + d["disc"]))
		if not alegeri:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, _(self.S.NICIUN_DISC), MessageBox.TYPE_INFO, timeout=5)
			return
		self.session.openWithCallback(self.meniuAles, ChoiceBox, title=_(self.S.TITLU), list=alegeri)

	def meniuAles(self, ales):
		if not ales:
			return
		from Screens.MessageBox import MessageBox
		from Screens.ChoiceBox import ChoiceBox
		ce = ales[1]
		if ce.startswith("pregateste:"):
			disc = ce.split(":", 1)[1]
			d = [x for x in self.stare.get("discuri", []) if x["disc"] == disc]
			if not d:
				return
			text = _(self.S.INTREBARE_PREGATIRE) % {"disc": ("%s %s" % (disc, d[0]["nume"])).strip(),
				"marime": self.S._marimeText(d[0]["marime"])}
			self.session.openWithCallback(lambda da: da and self._lucreaza("pregateste",
				lambda: self.S.pregatesteStick(disc)), MessageBox, text, MessageBox.TYPE_YESNO, default=False)
		elif ce == "feed":
			self.cuSetari({"fel": "feed"})
		elif ce == "zip":
			zipuri = self.S.zipuri()
			if not zipuri:
				self.session.open(MessageBox, _(self.S.NICIUN_ZIP), MessageBox.TYPE_INFO, timeout=6)
				return
			self.session.openWithCallback(lambda a: a and self.cuSetari({"fel": "zip", "cale": a[1]}), ChoiceBox,
				title=_(self.S.SURSA_ZIP), list=[("%s (%s)" % (z["nume"], z["marime"]), z["cale"]) for z in zipuri])
		elif ce == "adresa":
			from Screens.VirtualKeyBoard import VirtualKeyBoard
			self.session.openWithCallback(lambda a: a and self.cuSetari({"fel": "adresa", "adresa": a.strip()}),
				VirtualKeyBoard, title=_(self.S.SURSA_ADRESA), text="https://")

	def cuSetari(self, sursa):
		from Screens.ChoiceBox import ChoiceBox
		self.session.openWithCallback(lambda a: a and self._lucreaza("instaleaza",
			lambda: self.S.instaleaza(sursa, "", a[1])), ChoiceBox, title=_(self.S.TITLU),
			list=[(_(self.S.CU_SETARI), True), (_(self.S.FARA_SETARI), False)])
