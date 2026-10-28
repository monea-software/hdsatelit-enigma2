# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsBetaTester.py: ecranele programului de beta testeri. Meniu > Setari > Beta tester (ultima intrare din Setari).
# Logica e in Components/HdsBetaTester.py; aceleasi ecrane in interfata web: /beta-tester
# (HdsWebControl/betatester_web.py).
#
# - HdsBetaTester: intrarea din meniu. Cine nu e inscris (sau are acordul pe o nota mai veche) vede intai ecranul
#   acordului; dupa „Sunt de acord” ramane aici, in meniul testerului: mesajul, „Ce am trimis”, raspunsurile echipei,
#   datele pe care le trimite, „Ce trimit acum”, aparitia publica, nota, iesirea cu stergerea. Meniul testerului nu
#   exista inainte de inscriere.
# - HdsBetaAcord: felurile de date, toate bifate din fabrica, fiecare cu randul lui scurt (sub lista, la randul ales);
#   numele si e-mailul optionale; bifa notei, singura nebifata, deasupra butonului; Verde „Sunt de acord” merge numai
#   cu ea; Rosu „Renunt”; Galben deschide nota. Nimic nu pleaca inainte de „Sunt de acord”.
# - HdsBetaDate: bifele, numele si e-mailul, schimbate oricand.
# - HdsBetaText: un text lung (Ce trimit acum, raspunsurile, nota cu codul QR si adresa).
# - HdsBetaTrimise: „Ce am trimis”.
# - HdsBetaMesaj: mesajul (Greseala / Idee / Intrebare), cu jurnalul ultimei erori si captura meniurilor numai daca
#   omul le bifeaza. Captura: dupa Verde ecranele se inchid, omul are CAPTURA_ASTEPTARE_S secunde sa deschida ecranul
#   despre care scrie, apoi captura (numai meniurile) se face singura si mesajul intra in coada.
# - HdsBetaPublic, HdsBetaLegareQr: numele public, e-mailul pentru cont, legarea unui cont de pe forum prin codul QR
#   sau prin codul de 6 cifre aratat de site, dezlegarea. Fara parole pe receptor.

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.ConfigList import ConfigListScreen
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.Sources.CanvasSource import CanvasSource
from Components.Sources.StaticText import StaticText
from Components.config import ConfigYesNo, ConfigText, ConfigSelection, getConfigListEntry
from Components import HdsBetaTester as B
from Screens.MessageBox import MessageBox

B.initConfig()

ROSU = "#9f1313"
VERDE = "#1f771f"
GALBEN = "#a08000"
ALBASTRU = "#185090"


TOATE_TASTELE = ("key_red", "key_green", "key_yellow", "key_blue")


def _taste(y, latime=1240, x=30, chei=TOATE_TASTELE):
	"""Tastele colorate `chei` pe randul y, fiecare pe locul ei (rosu, verde, galben, albastru); cele nefolosite nu
	apar deloc (nici in skin, nici in ecran), ca sa nu ramana dreptunghiuri colorate goale."""
	lat = (latime - 3 * 20) // 4
	rez = []
	for i, (nume, culoare) in enumerate((("key_red", ROSU), ("key_green", VERDE), ("key_yellow", GALBEN),
			("key_blue", ALBASTRU))):
		if nume not in chei:
			continue
		rez.append('<widget name="%s" position="%d,%d" size="%d,40" zPosition="1" font="Regular;20" '
			'halign="center" valign="center" backgroundColor="%s" transparent="0" />' % (nume, x + i * (lat + 20), y, lat,
			culoare))
	return "\n\t\t".join(rez)


def ecranAsistenta():
	"""Ecranul Cere ajutor de la distanta (modulul asistentei: Screens.HdsAsistenta.HdsAsistenta, numai cu
	SystemInfo["HdsAsistenta"] adevarat, pus de mytest.py), sau None: randul nu apare."""
	try:
		from Components.SystemInfo import SystemInfo
		if not SystemInfo.get("HdsAsistenta"):
			return None
		from Screens.HdsAsistenta import HdsAsistenta
		return HdsAsistenta
	except Exception:
		return None


def randCanalTesteri(A):
	"""Randul Primeste intai versiunile pentru testeri: Da/Nu (modulul canalului testerilor) si starea."""
	pornit = B.canalTesteriPornit(A)
	return "%s: %s" % (_(A.TEXT_BIFA_TESTERI), _("Da") if pornit else _("Nu")), pornit


def ecranProbe():
	"""Ecranul „Probele receptorului” (alt modul al imaginii), sau None daca lipseste: randul nu apare."""
	try:
		from Screens.HdsProbe import HdsProbe
		return HdsProbe
	except Exception:
		return None


def _deseneazaQr(ecran, sursa, text):
	"""Codul QR al textului pe CanvasSource-ul `sursa` (marimea din widget). -> True daca s-a desenat."""
	c = ecran[sursa]
	latime = inaltime = 0
	for r in getattr(ecran, "renderer", []) or []:
		if getattr(r, "source", None) is c and r.instance is not None:
			latime, inaltime = r.instance.size().width(), r.instance.size().height()
	if not latime:
		return False
	try:
		from Components.HdsQr import deseneaza
		deseneaza(c, text, latime, inaltime)
		c.flush()
		return True
	except Exception as e:
		print("[HdsBetaTester] codul QR: %s" % e)
		return False


class HdsBetaTester(Screen):
	skin = """
	<screen name="HdsBetaTester" resolution="1920,1080" position="center,center" size="1300,760" title="Beta tester">
		<widget name="lista" position="30,25" size="1240,440" font="Regular;24" itemHeight="48" scrollbarMode="showOnDemand" />
		<widget source="text" render="Label" position="30,480" size="1240,200" font="Regular;19" halign="left" valign="top" />
		%s
	</screen>
	""" % _taste(700, chei=("key_red", "key_green"))

	RANDURI = (
		("mesaj", B.N_("Trimite un mesaj")),
		("trimite_acum", B.N_("Trimite acum")),
		("trimise", B.N_("Ce am trimis")),
		("raspunsuri", B.N_("Răspunsurile echipei")),
		("date", B.N_("Datele pe care le trimit")),
		("acum", B.N_("Ce trimit acum")),
		("probe", B.N_("Probele receptorului")),
		("asistenta", B.N_("Cere ajutor de la distanță")),
		("canal_testeri", ""),          # eticheta si starea vin din Components.HdsActualizari (canalul testerilor)
		("public", B.N_("Apariția publică")),
		("nota", B.N_("Nota de confidențialitate")),
		("iesire", B.N_("Ieși din program și șterge datele")),
	)

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Beta tester"))
		self.ecran_dedesubt = B.ultimulEcranTitlu(session)
		self["lista"] = MenuList([])
		self["text"] = StaticText("")
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Deschide"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"red": self.close,
			"ok": self.deschide,
			"green": self.deschide,
		}, -2)
		self._cerere = None
		self._numar = ""
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self._asteapta)
		self.onClose.append(self.ceas.stop)
		self.ceasNumar = eTimer()
		self.ceasNumar.callback.append(self._numarul)
		self.onClose.append(self.ceasNumar.stop)
		self.onFirstExecBegin.append(self._laInceput)
		B.ceNumar()
		self.ceasNumar.start(1000, False)
		self.reface()

	def _numarul(self):
		"""Randul cu numarul de testeri ai modelului, cand vine raspunsul (ecranul nu il asteapta)."""
		B._culegeNumar()
		rand = B.randNumar()
		if rand != self._numar:
			self._numar = rand
			self.reface()
		if B._starea.get("cerere_numar") is None:
			self.ceasNumar.stop()

	def _laInceput(self):
		if not B.inscris():
			self.session.openWithCallback(self._dupaAcord, HdsBetaAcord)
			return
		self._cereRaspunsuri()

	def _dupaAcord(self, *_r):
		if not B.inscris():
			self.close()
			return
		self.reface()

	def _cereRaspunsuri(self):
		b = B.initConfig()
		if B.inscris(b) and self._cerere is None:
			self._cerere = B.Cerere(B.adresaServer(b), "raspunsuri", {"v": B.PROTOCOL, "id": b.id.value})
			self._cerere.start()
			self.ceas.start(500, False)

	def _asteapta(self):
		c = self._cerere
		if c is None or not c.gata:
			return
		self.ceas.stop()
		self._cerere = None
		if 200 <= c.cod < 300:
			B.tineRaspunsuri(c.raspuns)
		self.reface()

	def reface(self):
		b = B.initConfig()
		noi = B.raspunsuriNoi()
		randuri = []
		for cheie, text in self.RANDURI:
			if (cheie == "probe" and ecranProbe() is None) or (cheie == "asistenta" and ecranAsistenta() is None):
				continue
			if cheie == "canal_testeri":
				A = B.modulCanalTesteri()
				if A is None:
					continue
				randuri.append((randCanalTesteri(A)[0], cheie))
				continue
			t = _(text)
			if cheie == "raspunsuri" and noi:
				t = "%s (%s)" % (t, _("un răspuns nou") if noi == 1 else _("%d răspunsuri noi") % noi)
			randuri.append((t, cheie))
		self["lista"].setList(randuri)
		if B.inscris(b):
			ultima = B.randUltimaTrimitere()
			if b.automat.value:
				# fara punctul de la capatul propozitiei inaintea parantezei
				ultima = ultima.rstrip(".") + " " + _("(automat în fiecare zi)")
			parti = [B.randNumar(), ultima, _("Identificatorul tău: %s\nAcordul din %s, nota de confidențialitate versiunea %d.\n"
				"Pentru ștergerea datelor fără receptor, scrie la contact@hdsatelit.com cu identificatorul.")
				% (b.id.value, B.oraLocala(b.acord.value), int(b.nota.value))]
			self["text"].setText("\n".join(p for p in parti if p))
		else:
			self["text"].setText("")

	def deschide(self):
		ales = self["lista"].getCurrent()
		if not ales or not B.inscris():
			return
		cheie = ales[1]
		if cheie == "mesaj":
			self.session.open(HdsBetaMesaj, self.ecran_dedesubt)
		elif cheie == "trimite_acum":
			_ok, text = B.trimiteAcum()
			self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=5)
		elif cheie == "probe":
			e = ecranProbe()
			if e is not None:
				self.session.open(e)
		elif cheie == "asistenta":
			e = ecranAsistenta()
			if e is not None:
				self.session.open(e)
		elif cheie == "canal_testeri":
			self.schimbaCanalTesteri()
		elif cheie == "trimise":
			self.session.open(HdsBetaTrimise)
		elif cheie == "raspunsuri":
			B.marcheazaVazute()
			self.session.openWithCallback(lambda *r: self.reface(), HdsBetaText, _("Răspunsurile echipei"),
				B.textRaspunsuri())
		elif cheie == "date":
			self.session.open(HdsBetaDate)
		elif cheie == "acum":
			self.session.open(HdsBetaText, _("Ce trimit acum"), B.ultimulPachet() or _("Încă nu a plecat niciun pachet."))
		elif cheie == "public":
			self.session.open(HdsBetaPublic)
		elif cheie == "nota":
			self.session.open(HdsBetaText, _("Nota de confidențialitate"), _(B.NOTA_SCURTA), B.ADRESA_NOTA)
		elif cheie == "iesire":
			self.session.openWithCallback(self._dupaIesire, MessageBox, _("Ieși din programul de beta testeri? Serverul "
				"șterge toate datele trimise de acest receptor, iar pe receptor nu mai rămâne nimic."),
				MessageBox.TYPE_YESNO, default=False)

	def schimbaCanalTesteri(self):
		"""OK pe „Primeste intai versiunile pentru testeri”: bifa se schimba prin Components.HdsActualizari (scrie sau
		sterge sursa canalului, apoi cauta singur); pornita = nota canalului, nereusita = mesajul lui."""
		A = B.modulCanalTesteri()
		if A is None:
			return
		pornit = randCanalTesteri(A)[1]
		try:
			ok = A.actualizari.testeri(not pornit)
			mesaj = getattr(A.actualizari, "mesaj", "") or ""
		except Exception as e:
			print("[HdsBetaTester] canalul testerilor: %s" % e)
			ok, mesaj = False, ""
		self.reface()
		if ok and not pornit:
			text = _(A.TEXT_NOTA_TESTERI) if hasattr(A, "TEXT_NOTA_TESTERI") else ""
		elif ok:
			text = ""
		else:
			text = mesaj or _("Nu s-a putut.") + " " + _("Încearcă din nou.")
		if text:
			self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=10)

	def _dupaIesire(self, raspuns):
		if not raspuns:
			return
		_ok, text = B.iesire()
		self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=8)
		self.close()


class HdsBetaAcord(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsBetaAcord" resolution="1920,1080" position="center,center" size="1400,880" title="Beta tester">
		<widget source="antet" render="Label" position="30,20" size="1340,110" font="Regular;20" halign="left" valign="top" />
		<widget name="config" position="30,140" size="1340,420" font="Regular;22" secondfont="Regular;20" itemHeight="42" scrollbarMode="showOnDemand" />
		<widget source="descriere" render="Label" position="30,575" size="1340,90" font="Regular;19" halign="left" valign="top" />
		<widget source="stare" render="Label" position="30,675" size="1340,120" font="Regular;20" halign="left" valign="top" />
		%s
	</screen>
	""" % _taste(820, 1340, chei=("key_red", "key_green", "key_yellow"))

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Beta tester"))
		b = B.initConfig()
		inapoi = B.notaVeche(b)
		self.bife = dict((fel, ConfigYesNo(default=bool(getattr(b, fel).value) if inapoi else True)) for fel in B.FELURI)
		self.automat = ConfigYesNo(default=bool(b.automat.value) if inapoi else True)
		self.nume = ConfigText(default=b.nume.value, fixed_size=False)
		self.email = ConfigText(default=b.email.value, fixed_size=False)
		self.nota = ConfigYesNo(default=False)
		self["antet"] = StaticText(_(B.ANTET_ACORD))
		self._numar = ""
		from enigma import eTimer
		self.ceasNumar = eTimer()
		self.ceasNumar.callback.append(self._numarul)
		self.onClose.append(self.ceasNumar.stop)
		B.ceNumar()
		self.ceasNumar.start(1000, False)
		self["descriere"] = StaticText("")
		self["stare"] = StaticText(_("Nota de confidențialitate s-a schimbat: citește-o și dă din nou acordul.")
			if inapoi else "")
		self["key_red"] = Button(_("Renunț"))
		self["key_green"] = Button(_("Sunt de acord"))
		self["key_yellow"] = Button(_("Nota de confidențialitate"))
		self.list = []
		ConfigListScreen.__init__(self, self.list, session=session)
		self["actiuni"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keyOK,
			"green": self.deAcord,
			"yellow": self.arataNota,
			"cancel": self.renunta,
			"red": self.renunta,
		}, -2)
		self["config"].onSelectionChanged.append(self._descriere)
		self.creeaza()
		self._numarul()

	def _numarul(self):
		B._culegeNumar()
		rand = B.randNumar()
		if rand != self._numar:
			self._numar = rand
			self["antet"].setText(_(B.ANTET_ACORD) + ("\n" + rand if rand else ""))
		if B._starea.get("cerere_numar") is None:
			self.ceasNumar.stop()

	def creeaza(self):
		self.list = [getConfigListEntry(B.eticheta(fel), self.bife[fel], fel) for fel in B.FELURI]
		self.list.append(getConfigListEntry(_(B.AUTOMAT[0]), self.automat, "automat"))
		self.list.append(getConfigListEntry(_("Numele (opțional)"), self.nume, "nume"))
		self.list.append(getConfigListEntry(_("E-mailul (opțional)"), self.email, "email"))
		self.list.append(getConfigListEntry(_(B.BIFA_NOTA), self.nota, "nota"))
		self["config"].list = self.list
		self["config"].setList(self.list)
		self._descriere()

	def _descriere(self):
		cur = self["config"].getCurrent()
		cheie = cur[2] if cur and len(cur) > 2 else ""
		if cheie in B.FELURI:
			text = B.randScurt(cheie)
		elif cheie == "automat":
			text = _(B.AUTOMAT[1])
		elif cheie == "nume":
			text = _("Numai ca să te putem întreba ceva despre o problemă găsită pe receptorul tău. Nu apare public.")
		elif cheie == "email":
			text = _("Numai pentru răspunsurile echipei. Nu apare public și se șterge la cerere.")
		elif cheie == "nota":
			text = _("Galben deschide nota. Fără această bifă nu pleacă nimic.")
		else:
			text = ""
		self["descriere"].setText(text)

	def arataNota(self):
		self.session.open(HdsBetaText, _("Nota de confidențialitate"), _(B.NOTA_SCURTA), B.ADRESA_NOTA)

	def deAcord(self):
		if not self.nota.value:
			self["stare"].setText(_("Bifează întâi „%s”") % _(B.BIFA_NOTA))
			return
		if not any(c.value for c in self.bife.values()):
			self["stare"].setText(_("Bifează cel puțin un fel de date sau alege Renunț."))
			return
		ok, text = B.acceptaAcord(dict((fel, c.value) for fel, c in self.bife.items()), self.nume.value,
			self.email.value, automat=self.automat.value)
		if not ok:
			self["stare"].setText(text)
			return
		self.session.openWithCallback(lambda *r: self.close(True), MessageBox, text, MessageBox.TYPE_INFO, timeout=6)

	def renunta(self):
		self.close(False)


class HdsBetaDate(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsBetaDate" resolution="1920,1080" position="center,center" size="1400,760" title="Datele pe care le trimit">
		<widget name="config" position="30,25" size="1340,340" font="Regular;22" secondfont="Regular;20" itemHeight="42" scrollbarMode="showOnDemand" />
		<widget source="descriere" render="Label" position="30,380" size="1340,100" font="Regular;19" halign="left" valign="top" />
		<widget source="stare" render="Label" position="30,490" size="1340,180" font="Regular;20" halign="left" valign="top" />
		%s
	</screen>
	""" % _taste(700, 1340, chei=("key_red", "key_green"))

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Datele pe care le trimit"))
		b = B.initConfig()
		self.bife = dict((fel, ConfigYesNo(default=bool(getattr(b, fel).value))) for fel in B.FELURI)
		self.automat = ConfigYesNo(default=bool(b.automat.value))
		self.nume = ConfigText(default=b.nume.value, fixed_size=False)
		self.email = ConfigText(default=b.email.value, fixed_size=False)
		self["descriere"] = StaticText("")
		self["stare"] = StaticText(_("Un fel debifat nu mai pleacă de acum; serverul îl refuză și el."))
		self["key_red"] = Button(_("Cancel"))
		self["key_green"] = Button(_("Save"))
		self.list = [getConfigListEntry(B.eticheta(fel), self.bife[fel], fel) for fel in B.FELURI]
		self.list.append(getConfigListEntry(_(B.AUTOMAT[0]), self.automat, "automat"))
		self.list.append(getConfigListEntry(_("Numele (opțional)"), self.nume, "nume"))
		self.list.append(getConfigListEntry(_("E-mailul (opțional)"), self.email, "email"))
		ConfigListScreen.__init__(self, self.list, session=session)
		self["actiuni"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keyOK,
			"green": self.salveaza,
			"cancel": self.close,
			"red": self.close,
		}, -2)
		self["config"].onSelectionChanged.append(self._descriere)
		self._descriere()

	def _descriere(self):
		cur = self["config"].getCurrent()
		cheie = cur[2] if cur and len(cur) > 2 else ""
		self["descriere"].setText(B.randScurt(cheie) if cheie in B.FELURI else (_(B.AUTOMAT[1]) if cheie == "automat"
			else ""))

	def salveaza(self):
		ok, text = B.schimbaBife(dict((fel, c.value) for fel, c in self.bife.items()), self.nume.value,
			self.email.value, automat=self.automat.value)
		if ok:
			self.session.openWithCallback(lambda *r: self.close(), MessageBox, text, MessageBox.TYPE_INFO, timeout=5)
		else:
			self["stare"].setText(text)


class HdsBetaText(Screen):
	skin = """
	<screen name="HdsBetaText" resolution="1920,1080" position="center,center" size="1500,860" title="Beta tester">
		<widget name="text" position="30,25" size="1060,760" font="Regular;20" />
		<widget source="qr" render="Canvas" position="1120,40" size="350,350" zPosition="2" />
		<widget source="adresa" render="Label" position="1080,400" size="410,120" font="Regular;17" halign="center" valign="top" />
		<widget source="key_red" render="Label" position="30,800" size="300,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
	</screen>
	"""

	def __init__(self, session, titlu, text, adresa=""):
		Screen.__init__(self, session)
		self.setTitle(titlu)
		self.adresa = adresa
		self["text"] = ScrollLabel(text)
		self["qr"] = CanvasSource()
		self["adresa"] = StaticText((_("Scanează cu telefonul sau deschide:") + "\n" + B.ADRESA_NOTA_SCURTA) if adresa
			else "")
		self["key_red"] = StaticText(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
			"up": self["text"].pageUp,
			"down": self["text"].pageDown,
			"left": self["text"].pageUp,
			"right": self["text"].pageDown,
		}, -2)
		self.onLayoutFinish.append(self._qr)

	def _qr(self):
		if self.adresa:
			_deseneazaQr(self, "qr", self.adresa)
			return
		# fara adresa (Ce trimit acum, raspunsurile): locul codului ascuns, nu un patrat gol
		for r in getattr(self, "renderer", []) or []:
			if getattr(r, "source", None) is self["qr"] and getattr(r, "instance", None) is not None:
				r.instance.hide()


class HdsBetaTrimise(Screen):
	skin = """
	<screen name="HdsBetaTrimise" resolution="1920,1080" position="center,center" size="1300,760" title="Ce am trimis">
		<widget name="lista" position="30,25" size="1240,600" font="Regular;21" itemHeight="40" scrollbarMode="showOnDemand" />
		<widget source="text" render="Label" position="30,635" size="1240,50" font="Regular;18" halign="left" valign="top" />
		<widget source="key_red" render="Label" position="30,700" size="300,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Ce am trimis"))
		randuri = ["%s   %s   %s   %s" % r for r in B.randuriTrimise()]
		self["lista"] = MenuList(randuri or [_("Încă nu a plecat nimic.")])
		self["text"] = StaticText(_("Ultimele %d, cel mai nou sus. Fără internet, pachetele așteaptă în coadă.") %
			B.TRIMISE_MAX)
		self["key_red"] = StaticText(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
		}, -2)


# mesajul care asteapta captura (dupa CAPTURA_ASTEPTARE_S secunde, cu ecranele inchise)
_asteptare = {"timer": None, "mesaj": None}


def _capturaSiMesaj():
	m = _asteptare.get("mesaj")
	_asteptare["mesaj"] = None
	if not m:
		return
	captura = B.capturaOsd()
	ok, text = B.mesaj(m["fel"], m["text"], m["ecran"], m["jurnal"], captura, contor=B.contor())
	print("[HdsBetaTester] mesajul cu captura: %s (%s)" % (ok, "captura" if captura else "fara captura"))


def _programeazaCaptura(mesaj_):
	from enigma import eTimer
	t = _asteptare.get("timer")
	if t is None:
		t = eTimer()
		t.callback.append(_capturaSiMesaj)
		_asteptare["timer"] = t
	_asteptare["mesaj"] = mesaj_
	t.start(B.CAPTURA_ASTEPTARE_S * 1000, True)


class HdsBetaMesaj(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsBetaMesaj" resolution="1920,1080" position="center,center" size="1400,760" title="Trimite un mesaj">
		<widget name="config" position="30,25" size="1340,260" font="Regular;22" secondfont="Regular;20" itemHeight="42" scrollbarMode="showOnDemand" />
		<widget source="text" render="Label" position="30,300" size="1340,180" font="Regular;20" halign="left" valign="top" />
		<widget source="stare" render="Label" position="30,490" size="1340,180" font="Regular;20" halign="left" valign="top" />
		%s
	</screen>
	""" % _taste(700, 1340, chei=("key_red", "key_green", "key_yellow"))

	def __init__(self, session, ecran=""):
		Screen.__init__(self, session)
		self.setTitle(_("Trimite un mesaj"))
		self.fel = ConfigSelection(choices=[(f, _(B.FELURI_MESAJ_TEXT[f])) for f in B.FELURI_MESAJ], default="greseala")
		self.textul = ConfigText(default="", fixed_size=False)
		self.ecran = ConfigText(default=ecran or "", fixed_size=False)
		self.jurnal = ConfigYesNo(default=False)
		self.captura = ConfigYesNo(default=False)
		self["text"] = StaticText("")
		self["stare"] = StaticText(_("Mesajul pleacă cu identificatorul anonim al receptorului, ca toate datele. "
			"Răspunsul echipei apare în „Răspunsurile echipei”."))
		self["key_red"] = Button(_("Cancel"))
		self["key_green"] = Button(_("Trimite"))
		self["key_yellow"] = Button(_("Scrie mesajul"))
		self.list = [
			getConfigListEntry(_("Felul"), self.fel),
			getConfigListEntry(_("Mesajul"), self.textul),
			getConfigListEntry(_("Ecranul sau funcția (opțional)"), self.ecran),
			getConfigListEntry(_("Atașează jurnalul ultimei erori"), self.jurnal),
			getConfigListEntry(_("Atașează o captură a ecranului (numai meniurile)"), self.captura),
		]
		ConfigListScreen.__init__(self, self.list, session=session)
		self["actiuni"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keyOK,
			"green": self.trimite,
			"yellow": self.scrie,
			"cancel": self.close,
			"red": self.close,
		}, -2)
		self._arata()

	def _arata(self):
		self["text"].setText(self.textul.value or _("Galben: scrie mesajul cu tastatura de pe ecran."))

	def scrie(self):
		from Components.ConfigList import deschideTastatura
		deschideTastatura(self.session, self.textul, _("Mesajul"), lambda t: self._arata())

	def keyOK(self):
		ConfigListScreen.keyOK(self)
		self._arata()

	def trimite(self):
		text = (self.textul.value or "").strip()
		if not text:
			self["stare"].setText(_("Scrie întâi mesajul."))
			return
		if self.captura.value:
			_programeazaCaptura({"fel": self.fel.value, "text": text, "ecran": self.ecran.value,
				"jurnal": bool(self.jurnal.value)})
			self.session.open(MessageBox, _("Ai %d secunde: închide meniurile și deschide ecranul despre care scrii. "
				"Captura se face singură, numai cu meniurile, apoi mesajul pleacă.") % B.CAPTURA_ASTEPTARE_S,
				MessageBox.TYPE_INFO, timeout=5)
			self.close()
			return
		ok, mesaj = B.mesaj(self.fel.value, text, self.ecran.value, bool(self.jurnal.value), None, contor=B.contor())
		if ok:
			self.session.openWithCallback(lambda *r: self.close(), MessageBox, mesaj, MessageBox.TYPE_INFO, timeout=5)
		else:
			self["stare"].setText(mesaj)


class HdsBetaPublic(Screen, ConfigListScreen):
	SABLON = """
	<screen name="HdsBetaPublic" resolution="1920,1080" position="center,center" size="1400,760" title="Apariția publică">
		<widget source="text" render="Label" position="30,20" size="1340,130" font="Regular;20" halign="left" valign="top" />
		<widget name="config" position="30,160" size="1340,180" font="Regular;22" secondfont="Regular;20" itemHeight="42" scrollbarMode="showOnDemand" />
		<widget source="stare" render="Label" position="30,355" size="1340,320" font="Regular;20" halign="left" valign="top" />
		%s
	</screen>
	"""
	skin = SABLON % _taste(700, 1340)
	skin_fara_forum = SABLON % _taste(700, 1340, chei=("key_red", "key_green", "key_blue"))

	def __init__(self, session):
		self.forum = B.legareForum()
		if not self.forum:
			self.skin = HdsBetaPublic.skin_fara_forum
		Screen.__init__(self, session)
		self.setTitle(_("Apariția publică"))
		b = B.initConfig()
		self.nume = ConfigText(default=b.public.value, fixed_size=False)
		self.email = ConfigText(default="", fixed_size=False)
		self.cod = ConfigText(default="", fixed_size=False)
		self["text"] = StaticText(_("Opțional: apari cu un nume ales de tine pe pagina testerilor de pe site și la "
			"modelul tău. Fără parole pe receptor.") + ((" " + _("E-mailul (opțional) îți face un cont pe forum: "
			"primești o legătură și îți pui parola acolo, de pe orice aparat.")) if self.forum else ""))
		self["stare"] = StaticText(_("Se citește starea..."))
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Salvează"))
		if self.forum:
			self["key_yellow"] = Button(_("Cod QR pentru telefon"))
		self["key_blue"] = Button(_("Nu mai apar public"))
		self.list = [getConfigListEntry(_("Numele public"), self.nume)]
		if self.forum:
			self.list.append(getConfigListEntry(_("E-mailul pentru cont (opțional)"), self.email))
			self.list.append(getConfigListEntry(_("Codul de 6 cifre de pe site (OK după ce îl scrii)"), self.cod))
		ConfigListScreen.__init__(self, self.list, session=session)
		self["actiuni"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keyOK,
			"green": self.salveaza,
			"yellow": self.qr,
			"blue": self.dezleaga,
			"cancel": self.close,
			"red": self.close,
		}, -2)
		self._cerere = None
		self._dupa = None
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self._asteapta)
		self.onClose.append(self.ceas.stop)
		self.onLayoutFinish.append(lambda: self._porneste("profil-stare", self._arataProfil))

	def _porneste(self, ruta, dupa, **campuri):
		if self._cerere is not None:
			return
		self._cerere = B.cerereProfil(ruta, **campuri)
		if self._cerere is None:
			self["stare"].setText(_("Nu ești înscris în programul de beta testeri."))
			return
		self._dupa = dupa
		self["stare"].setText(_("Se trimite..."))
		self.ceas.start(500, False)

	def _asteapta(self):
		c = self._cerere
		if c is None or not c.gata:
			return
		self.ceas.stop()
		self._cerere = None
		ok, text = B.mesajRaspunsProfil(c)
		if not ok:
			self["stare"].setText(text)
			return
		self._dupa(c.raspuns)

	def _arataProfil(self, raspuns):
		profil = raspuns.get("profil")
		b = B.initConfig()
		b.public.value = (profil or {}).get("nume_public") or ""
		B.salveaza(b)
		self["stare"].setText(B.textProfil(profil))

	def keyOK(self):
		cur = self["config"].getCurrent()
		if cur and cur[1] is self.cod and self.cod.value:
			self.leaga()
			return
		ConfigListScreen.keyOK(self)

	def salveaza(self):
		nume = B.textNume(self.nume.value, B.NUME_PUBLIC_MAX)
		email = B.textNume(self.email.value, B.EMAIL_MAX)
		if nume and not B.numePublicValid(nume):
			self["stare"].setText(_("Numele public are 2-40 de semne: litere, cifre, spațiu, punct, liniuță."))
			return
		if not B.emailValid(email):
			self["stare"].setText(_("Adresa de e-mail nu pare bună."))
			return
		campuri = {"nume_public": nume or None}
		if self.forum:
			campuri["email"] = email or None
		self._porneste("profil", self._arataProfil, **campuri)

	def leaga(self):
		cod = (self.cod.value or "").strip()
		if not B._COD6.match(cod):
			self["stare"].setText(_("Codul are 6 cifre. Îl vezi pe site, pe pagina de legare, când ești conectat."))
			return
		self._porneste("leaga", self._arataProfil, cod=cod)

	def dezleaga(self):
		self._porneste("dezleaga", self._arataProfil)

	def qr(self):
		if not self.forum:
			return
		self.session.openWithCallback(lambda *r: self._porneste("profil-stare", self._arataProfil), HdsBetaLegareQr)


class HdsBetaLegareQr(Screen):
	skin = """
	<screen name="HdsBetaLegareQr" resolution="1920,1080" position="center,center" size="1300,760" title="Leagă cu contul de pe forum">
		<widget source="text" render="Label" position="30,25" size="760,600" font="Regular;21" halign="left" valign="top" />
		<widget source="qr" render="Canvas" position="830,40" size="430,430" zPosition="2" />
		<widget source="adresa" render="Label" position="830,480" size="430,140" font="Regular;18" halign="center" valign="top" />
		<widget source="key_red" render="Label" position="30,700" size="300,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Leagă cu contul de pe forum"))
		self["text"] = StaticText(_("Se cere un cod de legare..."))
		self["qr"] = CanvasSource()
		self["adresa"] = StaticText("")
		self["key_red"] = StaticText(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
		}, -2)
		self._cerere = None
		self._adresa = ""
		self._incercari = 0
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self._asteapta)
		self.stare = eTimer()
		self.stare.callback.append(self._cereStarea)
		self.onClose.append(self.ceas.stop)
		self.onClose.append(self.stare.stop)
		self.onLayoutFinish.append(self._cereCod)

	def _cereCod(self):
		self._cerere = B.cerereProfil("cod-legare")
		if self._cerere is not None:
			self.ceas.start(500, False)

	def _cereStarea(self):
		self._incercari += 1
		if self._incercari * B.STARE_LEGARE_S > B.LEGARE_MAX_S:
			self.stare.stop()
			self["text"].setText(_("Codul a expirat. Deschide din nou ecranul pentru un cod nou."))
			return
		if self._cerere is None:
			self._cerere = B.cerereProfil("profil-stare")
			if self._cerere is not None:
				self.ceas.start(500, False)

	def _asteapta(self):
		c = self._cerere
		if c is None or not c.gata:
			return
		self.ceas.stop()
		self._cerere = None
		ok, text = B.mesajRaspunsProfil(c)
		if not ok:
			self["text"].setText(text)
			self.stare.stop()
			return
		if "cod" in c.raspuns and "adresa" in c.raspuns:
			self._adresa = str(c.raspuns.get("adresa") or "")[:200]
			if not self._adresa.startswith("https://"):
				self["text"].setText(_("Serverul a dat o adresă greșită."))
				return
			_deseneazaQr(self, "qr", self._adresa)
			self["adresa"].setText(self._adresa.replace("https://", ""))
			self["text"].setText(_("Scanează codul cu telefonul pe care ești conectat pe forumul imaginii și apasă "
				"„Leagă și arată-mă ca tester”. Codul e valabil 10 minute și se folosește o singură dată."))
			self.stare.start(B.STARE_LEGARE_S * 1000, False)
			return
		profil = c.raspuns.get("profil")
		if profil and profil.get("cont"):
			self.stare.stop()
			b = B.initConfig()
			b.public.value = profil.get("nume_public") or ""
			B.salveaza(b)
			self["text"].setText(B.textProfil(profil))
