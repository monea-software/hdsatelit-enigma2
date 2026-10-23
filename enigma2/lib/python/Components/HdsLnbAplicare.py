# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLnbAplicare.py - tot ce atinge setarile tunerului si nucleul pentru „Configurare LNB”, intr-un singur loc,
# pentru ecranul de pe televizor (Screens/ConfigLNB.py) si pentru pagina web.
#
# Cum se aplica (la fel ca „Setări tuner”, Screens/Satconfig.py:223-235, cu doua diferente cerute de siguranta):
#   1. valorile noi se pun numai in `value` al elementelor din config.Nims[n], iar nucleul le primeste prin
#      nimmanager.sec.update() (NimManager.py:134-250 si 252-480 citesc numai `.value`);
#   2. `saved_value` ramane cel vechi pana la confirmare. configfile.save() scrie numai saved_value
#      (config.py:1611-1640), deci orice scriere a setarilor in cele 60 de secunde, inclusiv cea de la oprirea
#      programului (mytest.py:601-602), pune pe disc tot setarile de dinainte. Daca receptorul se opreste,
#      cade sau e oprit de paznic inainte de confirmare, porneste singur pe ce era: nu trebuie niciun carlig la
#      pornire si nicio setare neconfirmata nu poate ramane pe disc.
#      O singura exceptie, fara urmari in nucleu: la trecerea din modul simplu in cel avansat, resturile
#      `advanced.lnb.N` / `advanced.sat.X` din settings pe care nu le foloseste nimic (niciun satelit spre LNB-ul N,
#      satelit care nu mai e in lista) nu se mai scriu, fiindca ConfigSubDict scrie numai copiii creati
#      (config.py:1516-1522); la fel se intampla cand tunerul trece in avansat din „Setări tuner”. La intoarcere se
#      pune la loc chiar obiectul ConfigNothing de dinainte, cu dictul lui intreg, deci urmatoarea scriere pune
#      inapoi si resturile: dupa intoarcere, settings e ca inainte;
#   3. la „Păstrez” se face save() pe campurile schimbate si configfile.save(); la „Nu”, EXIT sau dupa 60 de
#      secunde valorile de dinainte se pun inapoi in `value` (campurile nou create iau iar valoarea lor de la
#      creare, load()), apoi iar sec.update().
#
# Nicio exceptie nu iese din modul spre enigma2: aplica(), pastreaza(), revino() si fiecare pas pe eTimer se pazesc
# singure. O cadere se termina cu intoarcerea la ce era, un mesaj adevarat pentru om si un rand in jurnal; altfel
# exceptia ar ajunge in ePython::call, care cheama bsodFatal (lib/python/python.cpp:201-209, main/bsod.cpp) si
# opreste enigma2.
#
# Proba de semnal: dupa sec.update() programul care ruleaza NU e reacordat. Si nici repornirea lui imediata nu
# ajunge: acelasi program ia canalul pastrat inca 3 s dupa ultima folosire (lib/dvb/dvb.cpp:597-612, 664-686),
# deci fara acord nou si fara setarile noi, iar proba ar arata semnal cu setarile VECHI. De aceea programul se
# opreste, se asteapta 3,5 s pe eTimer si abia apoi porneste din nou. Nimic nu asteapta in bucla principala:
# fiecare pas e pe eTimer (paznicul opreste enigma2 dupa 60 s de tacere).
# Semnalul se crede numai daca e acelasi program si a pornit pe un tuner care foloseste LNB-urile schimbate: la
# pornire nucleul alege iar tunerul (allocateFrontend dupa scorul canTune, dvb.cpp:358-389), deci cand LNB-ul nou nu
# mai poate acorda canalul, acesta poate ajunge pe alt tuner, cu LNB-ul lui neschimbat.

import copy
import json
import os
import time
import traceback

from Components import HdsLnb

CALE_INAINTE = "/etc/enigma2/hds-lnb-inainte.json"
# fisierul ecranului vechi, scris si necitit de nimeni; se sterge o data, la prima schimbare pastrata
CALE_FISIER_VECHI = "/etc/enigma2/hdsconfig_lnb.conf"

SECUNDE_CONFIRMARE = 60
SECUNDE_PROBA = 20
MS_ELIBERARE_CANAL = 3500
MS_PROBA = 500
# fereastra in care tunerul poate avea setarea neconfirmata tine cel mult 3,5 + 20 + 60 + 3,5 s; o inregistrare
# programata care s-ar pregati in ea s-ar acorda cu setarea neconfirmata, deci atunci nu se aplica nimic
SECUNDE_FARA_INREGISTRARE = 120

LIBER = "liber"
PROBA = "proba"
CONFIRMARE = "confirmare"
REVENIRE = "revenire"

# ecranele care tin tunerul sau setarile lui; cat e deschis unul, nu se aplica nimic din pagina web
ECRANE_OCUPATE = ("NimSetup", "ServiceScan", "ScanSetup", "ScanerSatelit", "ScanerMaiMultiSateliti", "Satfinder",
	"HdsDishMotorEcran", "PositionerSetup", "HdsPositionerSetup", "DiseqcTester", "HdsDabPrincipal",
	"HdsT2miPrincipal", "ConfigLNB")
NUME_COORDONATOR = "hdsatelit_hds_coordonator"


def _jurnal(text):
	print("[HdsLnbAplicare] %s" % text)


def _descrie(eroare):
	"""exceptia intr-un singur rand, cu locul unde a cazut (jurnalul nu primeste un „Traceback” intreg)"""
	loc = ""
	try:
		cadru = traceback.extract_tb(eroare.__traceback__)[-1]
		loc = " la %s:%d" % (os.path.basename(cadru.filename), cadru.lineno)
	except Exception:
		pass
	return "%s: %s%s" % (type(eroare).__name__, eroare, loc)


def _nimmanager():
	from Components.NimManager import nimmanager
	return nimmanager


def _navigatie():
	try:
		import NavigationInstance
		return NavigationInstance.instance
	except Exception:
		return None


def _standby():
	"""ecranul Standby cat timp receptorul e in standby (Screens/Standby.py:81-84), altfel None"""
	try:
		from Screens.Standby import inStandby
	except Exception:
		return None
	return inStandby


def _pipDeschis():
	try:
		from Screens.InfoBar import InfoBar
		bara = InfoBar.instance
		return bool(bara is not None and getattr(bara.session, "pipshown", False))
	except Exception:
		return False


def _referinta(ref):
	"""textul unei referinte de program, ca doua referinte sa se poata compara (pe receptor sunt eServiceReference)"""
	if ref is None:
		return None
	try:
		return ref.toString()
	except Exception:
		return str(ref)


def _ceas(functie):
	from enigma import eTimer
	t = eTimer()
	try:
		t.callback.append(functie)
		legatura = None
	except AttributeError:
		legatura = t.timeout.connect(functie)
	return t, legatura


def _scrieAtomic(cale, text):
	"""in .nou, fsync, apoi os.replace (cu reincercari); fisierul adevarat nu se deschide niciodata cu „w” """
	nou = cale + ".nou"
	with open(nou, "w", encoding="utf-8") as f:
		f.write(text)
		f.flush()
		try:
			os.fsync(f.fileno())
		except OSError:
			pass
	ultima = None
	for _i in range(5):
		try:
			os.replace(nou, cale)
			return
		except OSError as eroare:
			ultima = eroare
	raise ultima


def _ordonate(perechi):
	"""ordinea in care notificarile din NimManager fac ce trebuie: configMode face `advanced` (1347-1379),
	sat.*.lnb face sectiunile LNB (1306-1345), lnb.*.lof si lnb.*.diseqcMode fac campurile lor (1208-1304)"""
	def rang(pereche):
		cale = pereche[0]
		if cale == "configMode":
			return 0
		if cale.startswith("advanced.sat.") and cale.endswith(".lnb"):
			return 1
		if cale.startswith("advanced.lnb.") and cale.endswith(".lof"):
			return 2
		if cale.startswith("advanced.lnb.") and cale.endswith(".diseqcMode"):
			return 3
		return 4
	return sorted(perechi, key=rang)


def instantaneu(cfg):
	"""(frunze, adormite): valoarea ca text a fiecarei frunze a tunerului si, pentru `advanced` cand e ConfigNothing,
	valorile vechi din settings pe care le tine in saved_value (config.py:1558-1571), puse pe cai"""
	frunze = {}
	adormite = {}
	for cale, el in HdsLnb.frunze(cfg):
		if HdsLnb._esteNimic(el):
			if isinstance(el.saved_value, dict):
				_aplatizeaza(el.saved_value, cale, adormite)
			continue
		try:
			frunze[cale] = HdsLnb.textElement(el)
		except Exception:
			pass
	return frunze, adormite


def _aplatizeaza(dictionar, prefix, rez):
	for cheie, valoare in dictionar.items():
		cale = "%s.%s" % (prefix, cheie)
		if isinstance(valoare, dict):
			_aplatizeaza(valoare, cale, rez)
		else:
			rez[cale] = valoare


def _pastreazaNimic(cfg):
	"""in modul simplu: (obiectul ConfigNothing al lui `advanced`, o copie adanca a dictului din saved_value), luate
	inainte de orice scriere; altfel None"""
	el = HdsLnb.element(cfg, "advanced")
	if el is None or not HdsLnb._esteNimic(el):
		return None
	return el, copy.deepcopy(el.saved_value)


def _punLaLocNimic(cfg, nimic):
	"""la intoarcere, acelasi ConfigNothing in locul sectiunii `advanced` facute de conversie
	(NimManager.configModeChanged), ca settings sa primeasca iar dictul intreg, cu resturile pe care sectiunea nu le
	scrie. Ordinea conteaza: atribuirea pune in saved_value ce tine sectiunea parinte (config.py:1545-1551), iar dupa
	un configfile.save() in fereastra acolo e deja dictul fara resturi; de aceea copia buna se pune DUPA. O conversie
	de mai tarziu face `advanced` din nou din el, ca la pornire."""
	if nimic is None:
		return
	obiect, dictionar = nimic
	try:
		if HdsLnb._valoare(cfg, "configMode") == "advanced":
			# modul nu s-a intors: fara sectiune, updateAdvanced ar cadea
			return
		if HdsLnb.element(cfg, "advanced") is not obiect:
			cfg.advanced = obiect
		obiect.saved_value = copy.deepcopy(dictionar)
	except Exception as eroare:
		_jurnal("punerea la loc a lui advanced (%s)" % _descrie(eroare))


class EroareScriere(Exception):
	pass


def scrieValori(cfg, perechi):
	"""pune valorile numai in `value`, in ordinea buna, apoi reciteste; orice camp care nu primeste exact textul
	cerut (element lipsa, alegere necunoscuta) opreste totul cu EroareScriere"""
	for cale, text in _ordonate(perechi):
		el = HdsLnb.element(cfg, cale)
		if el is None or HdsLnb._esteNimic(el):
			raise EroareScriere(cale)
		if HdsLnb.textElement(el) != text:
			el.value = el.fromstring(text)
	for cale, text in perechi:
		el = HdsLnb.element(cfg, cale)
		if el is None or HdsLnb.textElement(el) != text:
			raise EroareScriere(cale)


def restaureaza(cfg, frunze):
	"""valorile de dinainte inapoi in `value`: frunzele care existau iau textul din instantaneu, cele nou create
	iau valoarea lor de la creare (load(): saved_value sau implicit). saved_value nu se atinge. Intoarce lista
	cailor care nu s-au potrivit la recitire (se scrie in jurnal, nu se reia)."""
	perechi = []
	noi = []
	for cale, el in HdsLnb.frunze(cfg):
		if HdsLnb._esteNimic(el):
			continue
		if cale in frunze:
			perechi.append((cale, frunze[cale]))
		else:
			noi.append((cale, el))
	for cale, text in _ordonate(perechi):
		el = HdsLnb.element(cfg, cale)
		if el is not None and HdsLnb.textElement(el) != text:
			try:
				el.value = el.fromstring(text)
			except Exception as eroare:
				_jurnal("intoarcerea campului %s: %s" % (cale, eroare))
	for cale, el in noi:
		try:
			el.load()
		except Exception as eroare:
			_jurnal("campul nou %s: %s" % (cale, eroare))
	rele = []
	for cale, text in frunze.items():
		el = HdsLnb.element(cfg, cale)
		if el is None or HdsLnb._esteNimic(el) or HdsLnb.textElement(el) != text:
			rele.append(cale)
	return rele


def _schimbateDupa(date, cfg):
	"""caile care s-au schimbat de la pastrare (din „Setări tuner”, „Rotirea antenei” sau din alt loc): valoarea de
	acum fata de cea scrisa in copie la pastrare, pe caile care exista si acum si atunci. Caile care nu mai exista
	(de exemplu `advanced` dupa o repornire in modul simplu) nu schimba nimic din ce face intoarcerea."""
	dupa = date.get("dupa") or {}
	acum = instantaneu(cfg)[0]
	return sorted(cale for cale, text in acum.items() if cale in dupa and dupa[cale] != text)


def serviciulCurent():
	"""programul care ruleaza, daca e de satelit: tunerul, orbitalul, frecventa (kHz), polarizarea si referinta"""
	nav = _navigatie()
	if nav is None:
		return None
	try:
		serviciu = nav.getCurrentService()
		info = serviciu and serviciu.frontendInfo()
		if info is None:
			return None
		date = info.getFrontendData() or {}
		tp = info.getTransponderData(True) or {}
		if tp.get("tuner_type") != "DVB-S":
			return None
		return {"slot": int(date.get("tuner_number", -1)), "orbital": int(tp.get("orbital_position", -1)),
			"frecventa": int(tp.get("frequency", 0)), "polarizare": int(tp.get("polarization", 0)),
			"ref": nav.getCurrentlyPlayingServiceReference()}
	except Exception as eroare:
		_jurnal("programul care ruleaza: %s" % eroare)
		return None


def citesteSemnal():
	"""(prins, calitate_procent, tuner): semnalul programului care ruleaza si tunerul pe care l-a pus nucleul
	(tuner_number din getFrontendData, frontend.cpp:1483; lipseste cat timp canalul nu are inca tuner).
	getFrontendStatus() FARA argument intoarce dictionarul (lib/service/iservice.h:452, servicedvb.cpp:2061-2076).
	Calitatea e pe scara 0-65536 numai cand nucleul stie sa o calculeze in dB (frontend.cpp:960-966); altfel e
	SNR-ul brut, cu alta scara, si nu se arata niciun procent. None pe locul a ce nu se stie."""
	nav = _navigatie()
	try:
		serviciu = nav and nav.getCurrentService()
		info = serviciu and serviciu.frontendInfo()
		stare = info.getFrontendStatus() if info is not None else None
		date = info.getFrontendData() if info is not None else None
	except Exception:
		return None, None, None
	tuner = None
	if isinstance(date, dict) and date.get("tuner_number") is not None:
		try:
			tuner = int(date.get("tuner_number"))
		except (TypeError, ValueError):
			tuner = None
	if not isinstance(stare, dict) or "tuner_locked" not in stare:
		return None, None, tuner
	prins = bool(stare.get("tuner_locked"))
	calitate = None
	if prins and stare.get("tuner_signal_quality_db") is not None:
		try:
			calitate = max(0, min(100, int(stare.get("tuner_signal_quality", 0)) * 100 // 65536))
		except (TypeError, ValueError):
			calitate = None
	return prins, calitate, tuner


def _motivInregistrare(nav):
	"""de ce nu se poate aplica acum din cauza inregistrarilor, sau None"""
	if nav is None:
		return None
	try:
		inregistrari = nav.getRecordings()
	except Exception:
		inregistrari = None
	if inregistrari:
		return _("Se înregistrează acum. Schimbă LNB-ul după ce se termină înregistrarea.")
	try:
		# urmatoarea pregatire a unei inregistrari, ca Navigation.py:36 (-1: niciuna)
		urmatoarea = float(nav.RecordTimer.getNextRecordingTime())
	except Exception:
		return None
	if 0 <= urmatoarea and urmatoarea - time.time() <= SECUNDE_FARA_INREGISTRARE:
		return _("În mai puțin de două minute pornește o înregistrare programată. Schimbă LNB-ul după ce se termină.")
	return None


def _neprimite():
	return _("Setările de dinainte sunt puse la loc, dar tunerul nu le-a primit acum. Repornește receptorul.")


class _Aplicare(object):
	def __init__(self):
		self.faza = LIBER
		self.plan = None
		self.slot = -1
		self.frunze = None
		self.adormite = None
		self.nimic = None
		self.legate = set()
		self.ascultatori = []
		self.secunde = 0
		self.mesaj = ""
		self.ref = None
		self.proba = {}
		self.de_unde = ""
		self._pas = None
		self._ceasObj = None
		self._legatura = None
		self._inceput_proba = 0.0

	# ------------------------------------------------------------ ceas si ascultatori

	def _porneste(self, ms, pas):
		if self._ceasObj is None:
			self._ceasObj, self._legatura = _ceas(self._bate)
		self._pas = pas
		self._ceasObj.start(ms, True)

	def _opreste(self):
		self._pas = None
		if self._ceasObj is not None:
			self._ceasObj.stop()

	def _bate(self):
		pas = self._pas
		self._pas = None
		if pas is None:
			return
		try:
			pas()
		except Exception as eroare:
			_jurnal("pasul %s a cazut (%s)" % (getattr(pas, "__name__", "?"), _descrie(eroare)))
			self._dupaCadere()

	def _dupaCadere(self):
		"""dupa o exceptie: inapoi la ce era; faza ajunge LIBER sau are un ceas pornit, deci nu ramane agatata pe
		setarea neconfirmata, fara expirare"""
		if self.faza in (PROBA, CONFIRMARE):
			try:
				self.revino("eroare")
			except Exception as eroare:
				_jurnal("intoarcerea dupa cadere (%s)" % _descrie(eroare))
		if self.faza != LIBER and self._pas is None:
			self.faza = LIBER
			self.ref = None
			self._anunta()

	def _anunta(self):
		for f in list(self.ascultatori):
			try:
				f()
			except Exception as eroare:
				_jurnal("ascultator: %s" % eroare)

	# ------------------------------------------------------------ starea

	def stare(self):
		return {"faza": self.faza, "slot": self.slot, "secunde": self.secunde, "mesaj": self.mesaj,
			"proba": dict(self.proba), "intrebare": self.intrebare() if self.faza == CONFIRMARE else "",
			"rezumat": list(self.plan["rezumat"]) if self.plan else [], "de_unde": self.de_unde}

	def textProba(self):
		p = self.proba
		if self.faza == PROBA:
			return _("Verific semnalul pe %s") % p.get("satelit", "")
		if not p.get("facuta"):
			return p.get("motiv", "")
		if p.get("prins"):
			if p.get("calitate") is not None:
				return _("Semnal recepționat pe %s, calitate %d %%.") % (p.get("satelit", ""), p["calitate"])
			return _("Semnal recepționat pe %s.") % p.get("satelit", "")
		return _("Nu recepționez semnal pe %s cu noile setări.") % p.get("satelit", "")

	def intrebare(self):
		return "%s\n%s %s" % (self.textProba(), _("Păstrezi noile setări?"),
			_("Dacă nu răspunzi, revin singur la ce era. Secunde rămase: %d.") % max(0, self.secunde))

	def raspunsImplicit(self):
		"""cursorul intrebarii: pe „Da” numai cand s-a prins semnal (revizia, M6)"""
		return bool(self.proba.get("prins"))

	def _motivFaza(self):
		if self.faza == REVENIRE:
			return _("Receptorul pornește din nou programul. Încearcă peste câteva secunde.")
		return _("O altă schimbare de LNB așteaptă confirmarea.")

	# ------------------------------------------------------------ aplicarea

	def _actualizeazaNucleul(self, nm):
		"""sec.update() pazit: (True, ms) sau (False, ms), cu caderea scrisa in jurnal"""
		t0 = time.time()
		try:
			nm.sec.update()
		except Exception as eroare:
			_jurnal("sec.update() a cazut (%s)" % _descrie(eroare))
			return False, int((time.time() - t0) * 1000)
		return True, int((time.time() - t0) * 1000)

	def _intoarce(self, nm, cfg, frunze, nimic, nucleu=True):
		"""singurul drum inapoi, pentru orice cadere si pentru „Nu”: valorile de dinainte (restaureaza), `advanced`
		pus la loc cand era ConfigNothing, apoi sec.update() (numai daca nucleul primise ceva). True cand nucleul are
		iar setarile de dinainte. Nu arunca."""
		try:
			rele = restaureaza(cfg, frunze)
			if rele:
				_jurnal("la intoarcere %d campuri nu s-au potrivit (primul: %s); nu reiau" % (len(rele), rele[0]))
		except Exception as eroare:
			_jurnal("intoarcerea valorilor a cazut (%s)" % _descrie(eroare))
		_punLaLocNimic(cfg, nimic)
		if not nucleu:
			return True
		return self._actualizeazaNucleul(nm)[0]

	def aplica(self, plan, de_unde="televizor", nm=None):
		"""(True, "") daca s-a aplicat si a pornit proba, altfel (False, motivul). Nu arunca."""
		nm = nm or _nimmanager()
		if self.faza != LIBER:
			return False, self._motivFaza()
		if plan.get("oprire"):
			return False, plan["oprire"]
		if not plan.get("tinta") or not plan.get("schimbari"):
			return False, _("Nu ai schimbat nimic.")
		motiv = _motivInregistrare(_navigatie())
		if motiv:
			return False, motiv
		litera = chr(ord("A") + plan["slot"])
		try:
			cfg = nm.getNimConfig(plan["slot"])
			if HdsLnb.amprenta(cfg) != plan.get("amprenta"):
				return False, _("Setările tunerului s-au schimbat între timp. Verifică din nou.")
			serviciu = serviciulCurent()
			frunze, adormite = instantaneu(cfg)
			nimic = _pastreazaNimic(cfg)
		except Exception as eroare:
			# nimic scris inca: tunerul e cum era
			_jurnal("citirea tunerului %s inainte de aplicare a cazut (%s)" % (litera, _descrie(eroare)))
			return False, _("Nu am putut aplica setările (%s). Am revenit la ce era.") % _("eroare internă, scrisă în jurnal")
		# de aici pana la proba totul e pazit: o exceptie dintr-un notificator al lui NimManager (la `el.value = ...`)
		# sau din sec.update() se termina cu intoarcerea la ce era, nu cu ecranul de eroare al lui enigma2
		cauza = None
		nucleu = False
		durata = 0
		try:
			inainte = set(nm.getConfiguredSats() or ())
			scrieValori(cfg, plan["tinta"])
			nucleu = True
			t0 = time.time()
			nm.sec.update()
			durata = int((time.time() - t0) * 1000)
			dupa = set(nm.getConfiguredSats() or ())
			if dupa != inainte:
				cauza = _("alți sateliți")
				_jurnal("satelitii configurati s-au schimbat (%d inainte, %d dupa); intorc la ce era" % (len(inainte),
					len(dupa)))
		except EroareScriere as eroare:
			cauza = str(eroare)
			_jurnal("campul %s nu a primit valoarea ceruta; intorc la ce era" % eroare)
		except Exception as eroare:
			cauza = _("eroare internă, scrisă în jurnal")
			_jurnal("aplicarea pe tunerul %s a cazut (%s); intorc la ce era" % (litera, _descrie(eroare)))
		if cauza is not None:
			if self._intoarce(nm, cfg, frunze, nimic, nucleu):
				return False, _("Nu am putut aplica setările (%s). Am revenit la ce era.") % cauza
			return False, "%s %s" % (_("Nu am putut aplica setările."), _neprimite())
		self.faza = PROBA
		self.plan = plan
		self.slot = plan["slot"]
		self.frunze = frunze
		self.adormite = adormite
		self.nimic = nimic
		self.legate = HdsLnb.tunereCuAcelasiLnb(nm, self.slot, plan.get("motor_schimbat", plan.get("motor")))
		self.de_unde = de_unde
		self.mesaj = ""
		self.ref = None
		self.proba = {"facuta": False, "prins": None, "calitate": None, "satelit": "", "motiv": ""}
		_jurnal("tunerul %s: %d campuri schimbate, sec.update() %d ms, din %s" % (litera, len(plan["schimbari"]),
			durata, de_unde))
		try:
			self._pornesteProba(serviciu, nm)
		except Exception as eroare:
			_jurnal("pornirea probei a cazut (%s)" % _descrie(eroare))
			self._dupaCadere()
			return False, self.mesaj
		self._anunta()
		return True, ""

	def _pornesteProba(self, serviciu, nm):
		if serviciu is None or serviciu.get("slot") not in self.legate:
			self.proba["motiv"] = _("Nu am putut verifica semnalul: nu rula niciun canal de satelit pe acest tuner.")
			self._intraInConfirmare()
			return
		if serviciu.get("orbital") not in self.plan.get("sateliti", ()):
			self.proba["motiv"] = _("Canalul care rula e pe alt LNB decât cel schimbat, deci nu am ce verifica.")
			self._intraInConfirmare()
			return
		if _pipDeschis():
			# canalul impartit cu imaginea din imagine nu se reacordeaza (dvb.cpp:615-624): proba ar arata semnalul
			# prins cu setarile vechi, deci nu se face
			self.proba["motiv"] = _("Nu am putut verifica semnalul: imaginea în imagine (PiP) ține canalul deschis.")
			self._intraInConfirmare()
			return
		nav = _navigatie()
		self.ref = serviciu.get("ref")
		self.proba["satelit"] = HdsLnb._numeSatelit(nm, serviciu["orbital"])
		try:
			nav.stopService()
		except Exception as eroare:
			_jurnal("oprirea programului pentru proba: %s" % eroare)
		self._porneste(MS_ELIBERARE_CANAL, self._reacordeazaPentruProba)

	def _reacordeaza(self):
		"""porneste din nou programul oprit; True numai daca a pornit acum. In standby nu porneste nimic: il da
		ecranului Standby, care il porneste la trezire (Standby.py:73-75). Standby tine minte programul numai cand
		l-a oprit el (52-58); aici programul era deja oprit de noi, deci fara asta la trezire ecranul ramanea negru."""
		nav = _navigatie()
		if nav is None or self.ref is None:
			return False
		standby = _standby()
		if standby is not None:
			try:
				if getattr(standby, "prev_running_service", None) is None and \
						getattr(standby, "paused_service", None) is None:
					standby.prev_running_service = self.ref
					_jurnal("in standby: programul porneste la trezire")
			except Exception as eroare:
				_jurnal("programul pentru trezire (%s)" % _descrie(eroare))
			return False
		try:
			nav.playService(self.ref, checkParentalControl=False, forceRestart=True)
		except Exception as eroare:
			_jurnal("pornirea programului (%s)" % _descrie(eroare))
			return False
		return True

	def _reacordeazaPentruProba(self):
		if not self._reacordeaza():
			if _standby() is not None:
				self._probaNefacuta(_("Nu am putut verifica semnalul: receptorul a intrat în standby."), "standby")
			else:
				self._probaNefacuta(_("Nu am putut verifica semnalul: programul nu a pornit din nou."),
					"programul nu a pornit")
			return
		self._inceput_proba = time.time()
		self._porneste(MS_PROBA, self._bataieProba)

	def _refCurenta(self):
		nav = _navigatie()
		try:
			return _referinta(nav.getCurrentlyPlayingServiceReference()) if nav is not None else None
		except Exception:
			return None

	def _probaNefacuta(self, motiv, pentru_jurnal):
		self.proba.update({"facuta": False, "prins": None, "calitate": None, "motiv": motiv})
		_jurnal("proba nefacuta: %s" % pentru_jurnal)
		self._intraInConfirmare()

	def _bataieProba(self):
		prins, calitate, tuner = citesteSemnal()
		trecut = time.time() - self._inceput_proba
		acum = self._refCurenta()
		if acum is not None and acum != _referinta(self.ref):
			# temporizator de comutare, pagina web sau alt ecran: semnalul ar fi al altui program
			self._probaNefacuta(_("Nu am putut verifica semnalul: între timp a pornit alt canal."), "alt canal")
			return
		if tuner is not None and tuner not in self.legate:
			self._probaNefacuta(_("Nu am putut verifica semnalul: canalul a pornit pe tunerul %s, care nu folosește "
				"acest LNB.") % chr(ord("A") + tuner), "canalul pe tunerul %s" % chr(ord("A") + tuner))
			return
		if prins and tuner is not None:
			self.proba.update({"facuta": True, "prins": True, "calitate": calitate})
			_jurnal("proba: semnal prins in %.1f s" % trecut)
			self._intraInConfirmare()
			return
		if trecut >= SECUNDE_PROBA:
			if prins:
				# prins, dar nucleul nu a spus pe ce tuner: nu se poate sti daca e LNB-ul schimbat
				self._probaNefacuta(_("Nu am putut verifica semnalul: nu știu pe ce tuner a pornit canalul."),
					"tuner necunoscut")
				return
			self.proba.update({"facuta": True, "prins": False, "calitate": None})
			_jurnal("proba: fara semnal dupa %d s" % SECUNDE_PROBA)
			self._intraInConfirmare()
			return
		self._anunta()
		self._porneste(MS_PROBA, self._bataieProba)

	def _intraInConfirmare(self):
		self.faza = CONFIRMARE
		self.secunde = SECUNDE_CONFIRMARE
		self._anunta()
		self._porneste(1000, self._secunda)

	def _secunda(self):
		if self.faza != CONFIRMARE:
			return
		self.secunde -= 1
		if self.secunde <= 0:
			self.revino("expirat")
			return
		self._anunta()
		self._porneste(1000, self._secunda)

	# ------------------------------------------------------------ pastrarea si intoarcerea

	def pastreaza(self, nm=None):
		"""nu arunca: daca salvarea cade, saved_value se pune inapoi si tunerul se intoarce la ce era"""
		if self.faza not in (PROBA, CONFIRMARE):
			return None
		# pastrat chiar in cele 3,5 s de eliberare a canalului: programul porneste abia dupa ele, fara proba
		asteapta_program = self._pas == self._reacordeazaPentruProba
		self._opreste()
		salvate = []
		try:
			nm = nm or _nimmanager()
			cfg = nm.getNimConfig(self.slot)
			for cale, _text in self.plan["tinta"]:
				el = HdsLnb.element(cfg, cale)
				if el is not None and not HdsLnb._esteNimic(el):
					salvate.append((el, el.saved_value))
					el.save()
		except Exception as eroare:
			# altfel urmatorul configfile.save() ar scrie o stare pe jumatate noua
			for el, vechi in reversed(salvate):
				try:
					el.saved_value = vechi
				except Exception:
					pass
			_jurnal("pastrarea a cazut (%s); intorc la ce era" % _descrie(eroare))
			self.revino("eroare", nm)
			return self.mesaj
		try:
			from Components.config import configfile
			configfile.save()
		except Exception as eroare:
			_jurnal("scrierea setarilor (%s)" % _descrie(eroare))
		try:
			# „dupa” = starea de la pastrare: „Ce era înainte” se foloseste numai cat tunerul a ramas asa (m2)
			_scrieAtomic(CALE_INAINTE, json.dumps({"slot": self.slot, "cand": time.strftime("%d.%m.%Y %H:%M"),
				"frunze": self.frunze, "adormite": self.adormite, "rezumat": self.plan.get("rezumat", []),
				"dupa": instantaneu(cfg)[0]}, ensure_ascii=False, indent=1, sort_keys=True))
		except Exception as eroare:
			_jurnal("copia de dinainte (%s): %s" % (CALE_INAINTE, eroare))
		self._stergeFisierulVechi()
		_jurnal("tunerul %s: setarile noi pastrate" % chr(ord("A") + self.slot))
		self.mesaj = _("Am păstrat noile setări.")
		self.nimic = None
		self.faza = LIBER
		if asteapta_program:
			self.faza = REVENIRE
			try:
				self._porneste(MS_ELIBERARE_CANAL, self._reiaProgramul)
			except Exception as eroare:
				_jurnal("ceasul pentru program (%s)" % _descrie(eroare))
				self.faza = LIBER
		if self.faza == LIBER:
			self.ref = None
		self._anunta()
		return self.mesaj

	def _stergeFisierulVechi(self):
		try:
			if os.path.isfile(CALE_FISIER_VECHI):
				os.remove(CALE_FISIER_VECHI)
				_jurnal("sters %s: il scria ecranul vechi si nu il citea nimic" % CALE_FISIER_VECHI)
		except OSError as eroare:
			_jurnal("stergerea %s: %s" % (CALE_FISIER_VECHI, eroare))

	def _inregistrariAtinse(self):
		"""cate inregistrari merg acum pe un tuner cu LNB-ul schimbat si pe un satelit al lui. La aplicare nu era
		niciuna (aplica() refuza altfel), deci au pornit in fereastra, acordate cu setarile noi; sec.update() nu le
		reacordeaza."""
		nav = _navigatie()
		try:
			inregistrari = list(nav.getRecordings() or []) if nav is not None else []
		except Exception:
			return 0
		sateliti = set(self.plan.get("sateliti", ())) if self.plan else set()
		n = 0
		for inregistrare in inregistrari:
			try:
				info = inregistrare.frontendInfo()
				date = info.getFrontendData() or {}
				tp = info.getTransponderData(True) or {}
				if int(date.get("tuner_number", -1)) in self.legate and int(tp.get("orbital_position", -1)) in sateliti:
					n += 1
			except Exception:
				continue
		return n

	def revino(self, motiv="om", nm=None):
		"""idempotent: a doua chemare (de exemplu raspunsul la o intrebare deja inchisa) nu mai face nimic. Nu arunca:
		faza ajunge REVENIRE (cu ceas) sau LIBER, oricum ar merge sec.update()."""
		if self.faza not in (PROBA, CONFIRMARE):
			return None
		self._opreste()
		primit = False
		try:
			nm = nm or _nimmanager()
			primit = self._intoarce(nm, nm.getNimConfig(self.slot), self.frunze, self.nimic)
		except Exception as eroare:
			_jurnal("intoarcerea a cazut (%s)" % _descrie(eroare))
		self.nimic = None
		_jurnal("tunerul %s: intors la setarile de dinainte (%s)%s" % (chr(ord("A") + self.slot), motiv,
			"" if primit else "; nucleul nu le-a primit"))
		if not primit:
			self.mesaj = _neprimite()
		elif motiv == "eroare":
			self.mesaj = _("A apărut o eroare (scrisă în jurnal), deci am revenit la setările de dinainte.")
		else:
			self.mesaj = _("Am revenit la setările de dinainte.")
		atinse = self._inregistrariAtinse()
		if atinse:
			_jurnal("%d inregistrari pornite in fereastra pe LNB-ul schimbat" % atinse)
			self.mesaj = "%s %s" % (self.mesaj, _("În timpul probei a pornit o înregistrare pe acest LNB, acordată cu "
				"setările noi. Verifică înregistrarea."))
		self.faza = LIBER
		if self.ref is not None:
			# programul a mers cu setarile noi: si el trebuie reacordat, cu aceeasi asteptare a canalului pastrat
			self.faza = REVENIRE
			nav = _navigatie()
			try:
				nav.stopService()
			except Exception as eroare:
				_jurnal("oprirea programului la intoarcere: %s" % eroare)
			try:
				self._porneste(MS_ELIBERARE_CANAL, self._reiaProgramul)
			except Exception as eroare:
				_jurnal("ceasul pentru program (%s)" % _descrie(eroare))
				self.faza = LIBER
				self.ref = None
		self._anunta()
		return self.mesaj

	def _reiaProgramul(self):
		self._reacordeaza()
		self.ref = None
		self.faza = LIBER
		self._anunta()

	# ------------------------------------------------------------ „Ce era înainte”

	def copiaDeDinainte(self, slot):
		"""copia scrisa la ultima pastrare pe acest tuner, sau None. O copie fara starea de dupa pastrare (scrisa de
		o versiune dinainte a ecranului) nu se foloseste: nu se poate sti daca tunerul s-a schimbat de atunci."""
		try:
			with open(CALE_INAINTE, encoding="utf-8") as f:
				date = json.load(f)
		except (OSError, ValueError):
			return None
		if not isinstance(date, dict) or date.get("slot") != slot or not isinstance(date.get("frunze"), dict) or \
				not isinstance(date.get("dupa"), dict):
			return None
		return date

	def copieFolosibila(self, slot, nm=None):
		"""copia, numai daca tunerul e inca asa cum l-a lasat pastrarea (altfel „Ce era înainte” ar anula si ce s-a
		schimbat intre timp din alt loc)"""
		date = self.copiaDeDinainte(slot)
		if date is None:
			return None
		try:
			nm = nm or _nimmanager()
			return None if _schimbateDupa(date, nm.getNimConfig(slot)) else date
		except Exception as eroare:
			_jurnal("copia de dinainte (%s)" % _descrie(eroare))
			return None

	def planCeEraInainte(self, slot, nm=None):
		"""planul care duce tunerul inapoi la setarile de dinainte de ultima schimbare pastrata; trece prin aceeasi
		proba si confirmare ca orice schimbare. Dupa pastrare, copia devine starea de acum, deci doua intoarceri la
		rand duc inapoi la punctul de plecare. Daca tunerul s-a schimbat si din alt loc dupa pastrare, planul are
		oprire (nu se aplica), cu caile schimbate spuse."""
		nm = nm or _nimmanager()
		date = self.copiaDeDinainte(slot)
		if date is None:
			return None
		cfg = nm.getNimConfig(slot)
		frunze = date["frunze"]
		adormite = date.get("adormite") or {}
		tinta = []
		for cale, el in HdsLnb.frunze(cfg):
			if HdsLnb._esteNimic(el):
				continue
			if cale in frunze:
				tinta.append((cale, frunze[cale]))
			elif cale in adormite:
				tinta.append((cale, adormite[cale]))
			else:
				tinta.append((cale, el.tostring(el.default)))
		plan = {"slot": slot, "tinta": [], "schimbari": [], "rezumat": [], "avertismente": [], "oprire": "",
			"trece_in_avansat": False, "amprenta": HdsLnb.amprenta(cfg), "sateliti": [], "lnb_schimbate": [],
			"motor": False, "motor_schimbat": False, "fel": "inainte"}
		for cale, text in _ordonate(tinta):
			el = HdsLnb.element(cfg, cale)
			acum = HdsLnb.textElement(el)
			if acum != text:
				plan["tinta"].append((cale, text))
				plan["schimbari"].append((cale, acum, text))
		model = HdsLnb.citeste(slot, nm)
		plan["motor"] = bool(model.get("motor"))
		# nu se stie care LNB se intoarce: se socoteste si al doilea cablu al motorului (proba de semnal)
		plan["motor_schimbat"] = plan["motor"]
		# proba numai pe satelitii al caror drum il schimba intoarcerea (LNB-urile atinse, dupa lnbPentruSatelit), nu pe
		# toti: un satelit cu LNB-ul lui anume, neatins, ar da „Semnal prins” pentru „toti satelitii”
		plan["sateliti"] = HdsLnb.satelitiAtinsi(model, [cale for cale, _acum, _text in plan["schimbari"]])
		plan["rezumat"].append(_("Revin la setările de dinainte de %s?") % date.get("cand", ""))
		for rand in date.get("rezumat") or []:
			plan["rezumat"].append(_("Anulez: %s") % rand)
		schimbate_dupa = _schimbateDupa(date, cfg)
		if schimbate_dupa:
			plan["oprire"] = _("După ultima schimbare de LNB, setările tunerului s-au schimbat și din alt loc (de "
				"exemplu din Setări tuner), deci nu mai pot reveni sigur la ce era.")
			cai = ", ".join(schimbate_dupa[:3])
			if len(schimbate_dupa) > 3:
				cai = _("%s și încă %d") % (cai, len(schimbate_dupa) - 3)
			plan["avertismente"].append(_("Schimbate din alt loc: %s.") % cai)
		elif not plan["schimbari"]:
			plan["oprire"] = _("Nu ai schimbat nimic.")
		elif HdsLnb.receptorCuMotor(nm, model):
			plan["avertismente"].append(HdsLnb.avertismentMotor())
		return plan

	# ------------------------------------------------------------ cine mai tine tunerul

	def motivOcupat(self, sesiune=None, eu=None):
		"""de ce nu se poate aplica acum, sau None; `eu` e ecranul care intreaba (nu se socoteste pe el)"""
		if self.faza != LIBER:
			return self._motivFaza()
		motiv = _motivInregistrare(_navigatie())
		if motiv:
			return motiv
		import sys
		modul = sys.modules.get(NUME_COORDONATOR)
		coordonator = getattr(modul, "coordonator", None) if modul is not None else None
		detinator = getattr(coordonator, "detinator", None) if coordonator is not None else None
		if detinator is not None:
			return _("Tunerul e folosit acum de %s. Oprește-l, apoi încearcă din nou.") % getattr(detinator, "nume", "?")
		if sesiune is not None:
			dialoguri = [sesiune.current_dialog] + [x[0] for x in getattr(sesiune, "dialog_stack", [])]
			for d in dialoguri:
				if d is None or d is eu:
					continue
				if d.__class__.__name__ in ECRANE_OCUPATE:
					try:
						titlu = d.getTitle() or d.__class__.__name__
					except Exception:
						titlu = d.__class__.__name__
					return _("Pe televizor e deschis ecranul „%s”. Închide-l, apoi încearcă din nou.") % titlu
		return None


APLICARE = _Aplicare()


# ------------------------------------------------------------------ interfata modulului

def stare():
	return APLICARE.stare()


def laSchimbare(functie):
	if functie not in APLICARE.ascultatori:
		APLICARE.ascultatori.append(functie)


def faraAscultator(functie):
	if functie in APLICARE.ascultatori:
		APLICARE.ascultatori.remove(functie)


def aplica(plan, de_unde="televizor", nm=None):
	return APLICARE.aplica(plan, de_unde, nm)


def pastreaza(nm=None):
	return APLICARE.pastreaza(nm)


def revino(motiv="om", nm=None):
	return APLICARE.revino(motiv, nm)


def planCeEraInainte(slot, nm=None):
	return APLICARE.planCeEraInainte(slot, nm)


def areCopieDeDinainte(slot, nm=None):
	"""tasta galbena „Ce era înainte” se arata numai cand copia se poate folosi"""
	return APLICARE.copieFolosibila(slot, nm) is not None


def motivOcupat(sesiune=None, eu=None):
	return APLICARE.motivOcupat(sesiune, eu)
