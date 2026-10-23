# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPaznic.py: legatura dintre enigma2 si paznicul receptorului (hds-watchdog.py, reteta hdsatelit-watchdog).
#
# De ce: la o scanare de mai multi sateliti cu motor paznicul oprea enigma2 la jumatatea ei. Paznicul se uita numai la
# interfata web (/api/statusinfo): daca tacea 60 de secunde, trimitea
# SIGTERM. Interfata web merge pe aceeasi bucla cu enigma2, deci orice operatie lunga de pe firul principal (o mutare de
# motor, un acord greu) o facea sa taca, iar paznicul lua asta drept blocare.
#
# Ce face acest modul (paznicul citeste, nu scrie nimic in enigma2):
#   1. BATAIA: la fiecare BATAIE_S secunde, un eTimer de pe firul principal scrie CALE_BATAIE (/var/run e in RAM pe
#      receptor) cu pid-ul procesului, ceasul monoton (time.monotonic(), adica CLOCK_MONOTONIC, acelasi pentru toate
#      procesele; nu sare cand ora se muta prin NTP sau transponder) si semnul „ocupat”. Daca firul principal
#      se blocheaza, bataia se opreste. E al doilea semn de viata, pe langa interfata web: paznicul reporneste interfata
#      numai cand AMANDOUA tac (sau numai bataia, cand interfata web e oprita din setari), niciodata numai pe tacerea web.
#   2. SEMNUL „OCUPAT”: scanarea (Components/ServiceScan), citirea pistelor (HdsPisteCanale.Actualizare) si rotirea
#      antenei (isRotorMoving, citit la fiecare bataie) spun pana cand (ceas monoton) paznicul sa astepte, chiar daca
#      bataia s-a oprit. Semnul se scrie PE LOC la inceput (nu la urmatoarea bataie), ca sa fie pe disc si cand firul se
#      blocheaza imediat dupa pornire. Cat tine lucrul, fiecare bataie il prelungeste; o inregistrare uitata (lucru
#      oprit fara liber()) cade singura dupa OCUPAT_MAXIM_S.
#   3. SETARILE (config.hds_paznic): paznicul le citeste din /etc/enigma2/settings, unde enigma2 scrie numai valorile
#      schimbate. Valorile implicite de aici sunt aceleasi cu cele din hds-watchdog.py (INTERFATA_IMPLICIT,
#      ASTEPTARE_IMPLICITA_S, ASTEPTARI_PERMISE_S); testul test_paznic_sistem le compara.
#   4. STAREA: paznicul scrie CALE_STARE la fiecare verificare; ecranul „Paznicul receptorului” (Screens/HdsPaznic.py)
#      si pagina web /paznic (HdsWebControl/paznic_web.py) o citesc de aici, cu aceleasi texte.
#   5. REDAREA (nivelul 5 al paznicului: decodorul video care nu mai porneste din lipsa de memorie in
#      nucleu): fiecare bataie scrie si ce reda interfata (redare=tv: un serviciu cu pista video, in afara standby-ului;
#      radio, standby, nimic) si daca o inregistrare merge sau incepe in INREGISTRARE_CURAND_S secunde (inregistrare=1).
#      Paznicul reporneste receptorul pentru decodor numai cu redare=tv si inregistrare=0; cand ele lipsesc sau nu se
#      pot citi (redare= gol, inregistrare=-1) nu reporneste nimic.
#   6. MEMORIA POZELOR SI A FILMELOR: cand demonul platformei nu si-a putut mapa la pornire
#      memoria prin care driverul video primeste poza posturilor de radio si filmele, paznicul scrie in stare
#      memorie_es=lipsa si memorie_es_cheie=<pid-ul demonului>. enigma2 nu mai scrie atunci in video0 si audio0 (nucleul
#      ar cadea, lib/dvb/hdspazavideo.h), deci poza radio si filmele nu merg pana la repornirea receptorului. Niciun
#      mesaj pe televizor: ecranul si pagina paznicului arata starea ca informatie (stare()["avertisment"]), iar
#      repornirea in standby (punctul 7) o socoteste ca memorie sub prag.
#   7. MEMORIA DECODORULUI (Components/HdsMemorieDriver.py): cea mai mare bucata libera din vmalloc, masurata inainte
#      de esecul de la punctul 6. Bataia tine cea mai mica masuratoare din afara standby-ului si intreaba repornirea in
#      standby (config.hds_paznic.repornire_noapte); stare() da valoarea (memorie_driver) pentru ecran si web. Niciun
#      mesaj pe televizor.
#
# Paznicul placii (watchdog-ul hardware, 60 s) si oprirea la un blocaj de nucleu (fir in stare D) raman mereu pornite;
# setarea de aici priveste numai repornirea interfetei cand nu mai raspunde.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import os
import time

CALE_BATAIE = "/var/run/hds-paznic.bataie"
CALE_STARE = "/var/run/hds-paznic.stare"
CALE_JURNAL = "/home/root/hds-watchdog.log"

BATAIE_S = 10                   # cat de des scrie bucla principala bataia
DURATA_SCANARE_S = 20 * 60      # cat asteapta paznicul dupa ultima bataie a unei scanari (o mutare de motor, un acord greu)
DURATA_PISTE_S = 10 * 60        # citirea pistelor: pe fiecare transponder asteapta motorul cat merge, apoi 30 s semnalul
DURATA_MOTOR_S = 6 * 60         # o rotire de la un capat la altul, la viteza cea mai mica presupusa de nucleu
OCUPAT_MAXIM_S = 6 * 3600       # o inregistrare „ocupat” mai veche de atat se socoteste uitata si se scoate
INREGISTRARE_CURAND_S = 10 * 60 # o inregistrare care incepe in atatea secunde conteaza ca inregistrare in curs

# ce reda interfata (redare= in bataie)
REDARE_TV = "tv"
REDARE_RADIO = "radio"
REDARE_STANDBY = "standby"
REDARE_NIMIC = "nimic"
REDARI = (REDARE_TV, REDARE_RADIO, REDARE_STANDBY, REDARE_NIMIC)

# aceleasi valori ca in hds-watchdog.py (testul test_paznic_sistem le compara)
INTERFATA_IMPLICIT = True
ASTEPTARE_IMPLICITA_S = 120
ASTEPTARI_PERMISE_S = (60, 120, 300)

# memoria pozelor si a filmelor (memorie_es= in starea paznicului)
MEMORIE_ES_LIPSA = "lipsa"

# motivele din semnul „ocupat” (cuvinte scurte, fara spatii; paznicul le scrie in jurnal asa cum sunt)
MOTIV_SCANARE = "scanare"
MOTIV_PISTE = "piste"
MOTIV_MOTOR = "motor"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def monotonic():
	return time.monotonic()


def _jurnal(text):
	print("[HdsPaznic] %s" % text)


# ---------------------------------------------------------------- setarile

def initConfig():
	"""config.hds_paznic: „Reporneste interfata cand nu mai raspunde” si „Asteapta inainte de repornire”."""
	from Components.config import config
	if "hds_paznic" in config.content.items:
		return
	from Components.config import ConfigSubsection, ConfigYesNo, ConfigSelection
	config.hds_paznic = ConfigSubsection()
	config.hds_paznic.interfata = ConfigYesNo(default=INTERFATA_IMPLICIT)
	config.hds_paznic.asteptare = ConfigSelection(default=str(ASTEPTARE_IMPLICITA_S), choices=alegeriAsteptare())


def alegeriAsteptare():
	return [(str(s), textDurata(s)) for s in ASTEPTARI_PERMISE_S]


def textDurata(secunde):
	secunde = int(round(secunde))
	if secunde < 90:
		if secunde == 60:
			return _("un minut")
		return _("%d secunde") % secunde
	minute = int(round(secunde / 60.0))
	if minute == 1:
		return _("un minut")
	return _("%d minute") % minute


# ---------------------------------------------------------------- semnul „ocupat” si bataia

class Bataie(object):
	"""Registrul „ocupat” si bataia scrisa pe disc. Un singur obiect pe proces (bataie())."""

	def __init__(self, cale=None, ceas=None, pid=None, rotor=None, redare=None, standby=None):
		self.cale = cale or CALE_BATAIE
		self.ceas = ceas or monotonic
		self.pid = pid if pid is not None else os.getpid()
		self.rotor = rotor if rotor is not None else _rotorSeMisca
		self.redare = redare if redare is not None else _redareAcum
		self.redareFel = ""     # una din REDARI la ultima citire; "" = nu se stie
		self.inregistrare = -1  # 1: inregistrare acum sau curand, 0: niciuna, -1: nu se stie
		self.eroareRedare = None
		self.ocupat = {}        # cheie -> [motiv, durata_s, inceput, pana_la]
		self.eroareScriere = None
		self.timer = None
		self.scrieri = 0
		# memoria decodorului: cea mai mica masuratoare se tine numai in afara standby-ului
		self.standby = standby if standby is not None else _inStandby

	# ---- registrul ----

	def incepe(self, cheie, motiv, durata_s):
		"""Un lucru lung incepe (sau continua): paznicul asteapta cel putin durata_s de la ultima bataie. Se scrie pe loc."""
		acum = self.ceas()
		vechi = self.ocupat.get(cheie)
		inceput = vechi[2] if vechi else acum
		self.ocupat[cheie] = [motiv, float(durata_s), inceput, acum + float(durata_s)]
		self.scrie(acum)

	def termina(self, cheie):
		"""Lucrul s-a terminat (sau s-a oprit): semnul lui dispare. Se scrie pe loc."""
		if self.ocupat.pop(cheie, None) is not None:
			self.scrie()

	def _curata(self, acum):
		for cheie, (motiv, durata, inceput, pana) in list(self.ocupat.items()):
			if acum - inceput > OCUPAT_MAXIM_S:
				_jurnal("semnul „ocupat” %s (%s) tine de peste %d ore, il scot" % (cheie, motiv, OCUPAT_MAXIM_S // 3600))
				del self.ocupat[cheie]
			else:
				# cat timp lucrul inca e inregistrat, fiecare bataie il prelungeste
				self.ocupat[cheie][3] = acum + durata

	def semn(self, acum=None):
		"""(motive, pana_la): motivele lucrurilor in curs, fara repetari, si termenul cel mai departat (0 = nimic)."""
		if acum is None:
			acum = self.ceas()
		motive = []
		pana = 0.0
		for motiv, durata, inceput, pana_la in self.ocupat.values():
			if pana_la <= acum:
				continue
			if motiv not in motive:
				motive.append(motiv)
			pana = max(pana, pana_la)
		return motive, pana

	# ---- bataia ----

	def pas(self):
		"""O bataie (din eTimer, pe firul principal). Nu arunca niciodata: o eroare aici nu are voie sa lase paznicul
		fara bataie din cauza unui defect al bataii insesi, cand interfata web e oprita."""
		try:
			acum = self.ceas()
			try:
				if self.rotor():
					vechi = self.ocupat.get(MOTIV_MOTOR)
					self.ocupat[MOTIV_MOTOR] = [MOTIV_MOTOR, float(DURATA_MOTOR_S), vechi[2] if vechi else acum,
						acum + DURATA_MOTOR_S]
				else:
					self.ocupat.pop(MOTIV_MOTOR, None)
			except Exception as e:
				_jurnal("rotirea antenei nu se poate citi: %r" % (e,))
			self.citesteRedarea()
			self._curata(acum)
			self.scrie(acum)
		except Exception as e:
			_jurnal("bataia: %r" % (e,))
		self.verificaMemoriaDriver()

	def verificaMemoriaDriver(self):
		"""Memoria decodorului (Components/HdsMemorieDriver.py): citirile memoriei (crezute numai dupa un minut sub
		prag), cea mai mica masuratoare din afara standby-ului si repornirea in standby. Nimic pe ecran. Nu arunca."""
		try:
			from Components import HdsMemorieDriver as M
		except ImportError:
			return
		try:
			M.pasMasuratoare(self.standby)
			M.repornireStandby().pas()
		except Exception as e:
			_jurnal("memoria decodorului: %r" % (e,))

	def citesteRedarea(self):
		"""redareFel si inregistrare din self.redare(); la orice eroare sau raspuns strain: „nu se stie” (o singura linie
		in jurnal pana la urmatoarea citire reusita). Nu arunca."""
		try:
			fel, inregistrare = self.redare()
			if fel not in REDARI or inregistrare not in (0, 1):
				raise ValueError("raspuns strain: %r" % ((fel, inregistrare),))
			self.redareFel, self.inregistrare = fel, int(inregistrare)
			self.eroareRedare = None
		except Exception as e:
			self.redareFel, self.inregistrare = "", -1
			if self.eroareRedare is None:
				_jurnal("redarea nu se poate citi: %r" % (e,))
			self.eroareRedare = repr(e)

	def text(self, acum):
		motive, pana = self.semn(acum)
		return ("pid=%d\nbataie=%.3f\nocupat=%s\nocupat_pana=%.3f\nredare=%s\ninregistrare=%d\n"
			% (self.pid, acum, ",".join(motive), pana, self.redareFel, self.inregistrare))

	def scrie(self, acum=None):
		if acum is None:
			acum = self.ceas()
		nou = self.cale + ".nou"
		try:
			with open(nou, "w") as f:
				f.write(self.text(acum))
			os.replace(nou, self.cale)
			self.scrieri += 1
			if self.eroareScriere is not None:
				_jurnal("bataia se scrie din nou in %s" % self.cale)
			self.eroareScriere = None
		except (OSError, IOError) as e:
			if self.eroareScriere is None:
				_jurnal("nu pot scrie bataia in %s: %s" % (self.cale, e))
			self.eroareScriere = str(e)

	def porneste(self):
		from enigma import eTimer
		if self.timer is None:
			self.timer = eTimer()
			self.timer.callback.append(self.pas)
		self.pas()
		self.timer.start(BATAIE_S * 1000, False)

	def opreste(self):
		if self.timer is not None:
			self.timer.stop()
		try:
			os.remove(self.cale)
		except OSError:
			pass


def textMemorieEs(activ=None):
	"""Informatia de pe ecranul si pagina paznicului cand memoria pozelor si a filmelor lipseste (niciun mesaj pe
	televizor), cu propozitia eliberarii dupa setarea repornirii in standby."""
	text = _("Filmele și imaginea posturilor de radio nu pot porni acum; canalele TV merg.")
	try:
		from Components import HdsMemorieDriver
		text += " " + HdsMemorieDriver.textEliberare(HdsMemorieDriver.activaStandby() if activ is None else activ)
	except Exception:
		pass
	return text


def _inStandby():
	from Screens import Standby
	return Standby.inStandby is not None


def _rotorSeMisca():
	try:
		from enigma import eDVBSatelliteEquipmentControl
		sec = eDVBSatelliteEquipmentControl.getInstance()
	except Exception:
		return False
	if sec is None:
		return False
	return bool(sec.isRotorMoving())


def _redareAcum():
	"""(redare, inregistrare) din enigma2. redare: „standby” cat ecranul Standby e deschis, „tv” pentru un serviciu cu
	pista video, „radio” pentru unul fara, „nimic” fara serviciu. inregistrare: 1 cand o inregistrare merge sau incepe in
	INREGISTRARE_CURAND_S secunde, altfel 0. Arunca daca navigatia lipseste (bataia scrie atunci „nu se stie”)."""
	import NavigationInstance
	nav = NavigationInstance.instance
	if nav is None:
		raise RuntimeError("navigatia nu e pornita")
	inregistrare = 0
	if nav.getRecordings():
		inregistrare = 1
	else:
		urmatoarea = nav.RecordTimer.getNextRecordingTime()
		if urmatoarea > 0 and urmatoarea - time.time() < INREGISTRARE_CURAND_S:
			inregistrare = 1
	from Screens import Standby
	if Standby.inStandby is not None:
		return REDARE_STANDBY, inregistrare
	serviciu = nav.getCurrentService()
	info = serviciu and serviciu.info()
	if not info:
		return REDARE_NIMIC, inregistrare
	from enigma import iServiceInformation
	return (REDARE_TV if info.getInfo(iServiceInformation.sVideoPID) > 0 else REDARE_RADIO), inregistrare


_unic = [None]


def bataie():
	if _unic[0] is None:
		_unic[0] = Bataie()
	return _unic[0]


def porneste():
	"""Din mytest.py, dupa pornirea sesiunii: setarile si bataia."""
	initConfig()
	bataie().porneste()
	_jurnal("bataia pornita (%s, la %d s)" % (bataie().cale, BATAIE_S))
	# setarea repornirii de noapte si, dupa o repornire de noapte, intrarea in standby
	try:
		from Components import HdsMemorieDriver
		HdsMemorieDriver.porneste()
	except Exception as e:
		_jurnal("memoria decodorului: %r" % (e,))


def opreste():
	"""Din mytest.py, la iesirea din enigma2: bataia se opreste si fisierul ei se sterge (procesul urmator scrie altul)."""
	if _unic[0] is not None:
		_unic[0].opreste()


def ocupat(cheie, motiv, durata_s):
	"""Pentru scanare, citirea pistelor si alte lucruri lungi: nu arunca niciodata."""
	try:
		bataie().incepe(cheie, motiv, durata_s)
	except Exception as e:
		_jurnal("ocupat(%s): %r" % (cheie, e))


def liber(cheie):
	try:
		bataie().termina(cheie)
	except Exception as e:
		_jurnal("liber(%s): %r" % (cheie, e))


# ---------------------------------------------------------------- starea, pentru ecran si web

def citesteCheiValori(cale, maxim=4096):
	try:
		with open(cale, "r") as f:
			text = f.read(maxim)
	except (OSError, IOError):
		return None
	d = {}
	for rand in text.splitlines():
		cheie, semn, valoare = rand.partition("=")
		if semn:
			d[cheie.strip()] = valoare.strip()
	return d


def _intreg(valoare, implicit=0):
	try:
		return int(float(valoare))
	except (TypeError, ValueError):
		return implicit


def _procesExista(pid):
	return pid > 0 and os.path.exists("/proc/%d" % pid)


def textMotiv(motiv):
	return {
		MOTIV_SCANARE: _("scanarea canalelor"),
		MOTIV_PISTE: _("citirea pistelor canalelor"),
		MOTIV_MOTOR: _("rotirea antenei"),
	}.get(motiv, motiv)


def textMotive(motive):
	return ", ".join(textMotiv(m) for m in motive if m)


def stare(cale_stare=None, acum=None, pid_paznic_viu=None):
	"""Starea pentru ecran si web: dictionar simplu, cu textul gata de aratat. Nu arunca."""
	cale_stare = cale_stare or CALE_STARE
	acum = monotonic() if acum is None else acum
	viu = pid_paznic_viu or _procesExista
	d = citesteCheiValori(cale_stare)
	rez = {
		"ruleaza": False,
		"stare": "necunoscut",
		"text": "",
		"detaliu": "",
		"placa": False,
		"placa_secunde": 0,
		"ocupat": [],
		"ocupat_text": "",
		"ocupat_ramas_s": 0,
		"bataie_varsta_s": -1,
		"reporniri": 0,
		"ultima_actiune": "",
		"ultima_actiune_ora": 0,
		"verificat_acum_s": -1,
		"memorie_es": "",
		"memorie_es_cheie": "",
		"avertisment": "",
		"memorie_driver": {},
	}
	# memoria decodorului (vmalloc) se masoara aici, pe receptor: nu depinde de paznic; numai informatie
	try:
		from Components import HdsMemorieDriver
		rez["memorie_driver"] = HdsMemorieDriver.stare()
	except Exception:
		pass
	try:
		b = bataie()
		motive, pana = b.semn()
		rez["ocupat"] = motive
		rez["ocupat_text"] = textMotive(motive)
		rez["ocupat_ramas_s"] = int(max(0, pana - b.ceas())) if pana else 0
	except Exception:
		pass
	if not d:
		rez["text"] = _("Paznicul nu rulează sau nu a scris încă nicio stare (imagine fără el, sau pornirea abia a început).")
		return rez
	pid = _intreg(d.get("pid"))
	verificat = d.get("verificat")
	try:
		vechime = acum - float(verificat)
	except (TypeError, ValueError):
		vechime = -1
	rez["verificat_acum_s"] = int(vechime) if vechime >= 0 else -1
	rez["ruleaza"] = bool(viu(pid)) and 0 <= vechime <= 90
	rez["stare"] = d.get("stare", "necunoscut")
	rez["detaliu"] = d.get("detaliu", "")
	rez["placa"] = d.get("placa") == "1"
	rez["placa_secunde"] = _intreg(d.get("placa_secunde"))
	rez["bataie_varsta_s"] = _intreg(d.get("bataie_varsta"), -1)
	rez["reporniri"] = _intreg(d.get("reporniri"))
	rez["ultima_actiune"] = d.get("ultima_actiune", "")
	rez["ultima_actiune_ora"] = _intreg(d.get("ultima_actiune_ora"))
	if not rez["ocupat"] and d.get("ocupat"):
		rez["ocupat"] = [m for m in d.get("ocupat", "").split(",") if m]
		rez["ocupat_text"] = textMotive(rez["ocupat"])
		rez["ocupat_ramas_s"] = _intreg(d.get("ocupat_ramas"))
	rez["memorie_es"] = d.get("memorie_es", "")
	rez["memorie_es_cheie"] = d.get("memorie_es_cheie", "")
	# numai de la un paznic viu: o stare veche (paznicul oprit) nu mai spune nimic despre receptorul de acum
	if rez["ruleaza"] and rez["memorie_es"] == MEMORIE_ES_LIPSA:
		rez["avertisment"] = textMemorieEs()
	rez["text"] = textStare(rez)
	return rez


def stareEs(cale_stare=None, acum=None, pid_paznic_viu=None):
	"""Numai memoria pozelor si a filmelor, din starea paznicului (pentru repornirea in standby): {'ruleaza',
	'memorie_es', 'memorie_es_cheie'}; ruleaza = paznicul viu, cu stare noua. Nu arunca."""
	rez = {"ruleaza": False, "memorie_es": "", "memorie_es_cheie": ""}
	try:
		d = citesteCheiValori(cale_stare or CALE_STARE)
		if not d:
			return rez
		acum = monotonic() if acum is None else acum
		vechime = acum - float(d.get("verificat"))
		rez["ruleaza"] = bool((pid_paznic_viu or _procesExista)(_intreg(d.get("pid")))) and 0 <= vechime <= 90
		rez["memorie_es"] = d.get("memorie_es", "")
		rez["memorie_es_cheie"] = d.get("memorie_es_cheie", "")
	except Exception:
		pass
	return rez


def textStare(s):
	if not s.get("ruleaza"):
		return _("Paznicul nu rulează acum (fără stare nouă de peste un minut).")
	fel = s.get("stare")
	if fel == "oprit":
		text = _("Repornirea interfeței este oprită din setări. Paznicul plăcii rămâne pornit.")
	elif fel == "ocupat":
		text = _("Interfața lucrează la: %s. Paznicul așteaptă să termine.") % (s.get("ocupat_text") or _("un lucru lung"))
	elif fel == "fara-bataie":
		text = _("Paznicul așteaptă primul semn de viață al interfeței.")
	elif fel == "web-raspunde":
		text = _("Interfața nu a mai trimis semn de viață, dar interfața web răspunde. Paznicul nu o repornește.")
	elif fel == "blocat":
		text = _("Interfața nu a mai răspuns. Paznicul a repornit-o.")
	else:
		text = _("Paznicul supraveghează interfața.")
	if s.get("placa"):
		text += " " + (_("Paznicul plăcii: pornit, %d secunde.") % s["placa_secunde"] if s.get("placa_secunde")
			else _("Paznicul plăcii: pornit."))
	return text


def ultimeleRanduriJurnal(cale=None, randuri=8, maxim=16384):
	"""Ultimele randuri din jurnalul paznicului (texte tehnice, fara diacritice), pentru ecran si web."""
	cale = cale or CALE_JURNAL
	try:
		with open(cale, "rb") as f:
			try:
				f.seek(-maxim, os.SEEK_END)
			except (OSError, IOError):
				f.seek(0)
			date = f.read(maxim)
	except (OSError, IOError):
		return []
	text = date.decode("utf-8", "replace")
	return [r for r in text.splitlines() if r.strip()][-randuri:]


# ---------------------------------------------------------------- schimbarea setarilor (ecran si web)

def seteaza(interfata=None, asteptare=None, noapte=None):
	"""Schimba si salveaza setarile (pe disc, ca paznicul sa le vada la urmatoarea verificare). Intoarce (reusit, mesaj).
	noapte = repornirea de noapte cand memoria decodorului e farmitata (Components/HdsMemorieDriver.py)."""
	from Components.config import config, configfile
	initConfig()
	if noapte is not None:
		from Components import HdsMemorieDriver
		HdsMemorieDriver.initConfig()
		config.hds_paznic.repornire_noapte.value = bool(noapte)
		config.hds_paznic.repornire_noapte.save()
	if asteptare is not None:
		try:
			secunde = int(asteptare)
		except (TypeError, ValueError):
			return False, _("Timpul de așteptare nu este unul din cele permise.")
		if secunde not in ASTEPTARI_PERMISE_S:
			return False, _("Timpul de așteptare nu este unul din cele permise.")
		config.hds_paznic.asteptare.value = str(secunde)
		config.hds_paznic.asteptare.save()
	if interfata is not None:
		config.hds_paznic.interfata.value = bool(interfata)
		config.hds_paznic.interfata.save()
	configfile.save()
	return True, _("Salvat. Paznicul folosește setarea de la următoarea verificare (cel mult 15 secunde).")
