# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMotorComenzi.py - comenzile DiSEqC 1.2 ale motorului de antena, intr-un singur loc.
#
# Ecranul „Rotirea antenei" (Screens/HdsDishMotor.py) si pagina web cheama aceleasi functii, cu aceleasi intrebari si
# aceleasi plafoane de timp. Nicio comanda nu ocoleste modulul. Toate functiile publice se intorc imediat; asteptarile
# (tonul oprit, tensiunea, mersul motorului) se fac numai cu eTimer, fara sleep si fara bucle: bucla principala nu sta
# niciodata (paznicul hds-watchdog opreste enigma2 dupa 60 s de tacere).
#
# Octetii vin din Components/DishMath.py (specificatia Eutelsat DiSEqC 1.2), trimisi numai daca trec de
# DishMath.isAllowed; cu lacatul de proba /etc/enigma2/hds-fara-motor trec numai oprirea si pornirea limitelor.
#
# Siguranta, pe scurt:
#   - orice miscare are plafon de timp; la plafon se trimite oprirea (E0 31 60 de doua ori, la 50 ms, ca sec.cpp:764-767);
#   - cat se misca motorul, orice comanda noua doar il opreste (in afara de inca un pas in aceeasi directie);
#   - nicio comanda a noastra cat ruleaza o secventa a nucleului pe tunerul nostru (revizia M1): dupa fiecare acord al
#     nostru asteptam sa nu mai fie „TUNING", cel mult ASTEPTARE_SECVENTA_S;
#   - oprirea unei miscari pornite de nucleu („Mergi la satelit"): intai acordul de referinta (golește secventa cu 6E,
#     frontend.cpp:2441), apoi tonul oprit si oprirea dubla;
#   - cu limitele oprite nu pleaca nicio comanda „mergi la" (revizia M2), iar miscarea continua merge cel mult 10 s;
#     semnul /etc/enigma2/hds-motor-limite-oprite le porneste la prima folosire daca enigma2 a cazut intre timp (M3);
#   - la iesirea din ecran, la standby, la cedarea tunerului si la orice eroare: oprirea, limitele pornite, programul
#     la loc.
import json
import os
import time

from Components import DishMath
try:
	from Components import HdsGrade
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsGrade
from Components import HdsMotorTuner as T

# marimile pasului (Sus / Jos in ecran)
PASI = (1, 2, 5, 10, 20)
# plafoanele (se ajusteaza dupa proba pe motor)
PAS_BAZA_S = 1.5
PAS_PE_PAS_S = 0.3
PAS_MAX_S = 10.0
CONTINUU_S = 30
CONTINUU_FARA_LIMITE_S = 10
POZITIE_MAX_S = 180
# cat mai asteptam peste timpul maxim calculat de nucleu la „Mergi la satelit" (sec.cpp:857-863)
NUCLEU_REZERVA_S = 8
# cel mai mult cat asteptam ca secventa nucleului de dupa un acord al nostru (fara comanda de motor) sa treaca de
# tensiune si ton: cu valorile din config.sec (NimManager.py:1003-1064) e sub 1 s fara comutatoare DiSEqC
ASTEPTARE_SECVENTA_S = 1.5
# intervalul dintre cele doua opriri (sec.cpp:766)
INTRE_OPRIRI_MS = 50
# pauza dintre doua mesaje DiSEqC trimise de noi unul dupa altul (66 apoi 6A 00)
INTRE_MESAJE_MS = 120
# pagina web: paza miscarii continue si tunerul dat inapoi cand pagina tace
WEB_MENTINE_S = 5
WEB_LIBER_S = 120
# inregistrarile: refuz sub un minut, avertisment sub 10 minute, oprire la un minut inainte
INREGISTRARE_REFUZ_S = 60
INREGISTRARE_AVERTISMENT_S = 600
# cat asteptam, la luarea tunerului, o miscare a nucleului inceputa inainte (un zap chiar atunci)
ASTEPTARE_NUCLEU_PAS_MS = 500
FISIER_LIMITE_OPRITE = "/etc/enigma2/hds-motor-limite-oprite"

_unic = None


def comenzi():
	"""obiectul unic al procesului (creat la prima cerere)"""
	global _unic
	if _unic is None:
		_unic = ComenziMotor()
	return _unic


def _cfg(nume, implicit):
	"""o intarziere din config.sec (aceleasi valori ca nucleul, NimManager.py:1003-1064)"""
	try:
		from Components.config import config
		return int(getattr(config.sec, nume).value)
	except Exception:
		return implicit


def gradeScurt(orbital):
	"""19,2°E / 5,0°V din pozitia nucleului (0..3599), in limba meniului („5.0°W" in engleza, Components/HdsGrade.py);
	numai pentru afisaj"""
	if orbital is None or orbital < 0:
		return ""
	return HdsGrade.pozitie(DishMath.orbitalToDegrees(orbital))


def satelitText(orbital):
	nume = T.numeSatelit(orbital)
	return "%s %s" % (gradeScurt(orbital), nume) if nume else gradeScurt(orbital)


def _scrieSemn(cale):
	nou = cale + ".nou"
	with open(nou, "w", encoding="utf-8") as f:
		f.write("limitele motorului au fost oprite din Rotirea antenei\n")
	os.replace(nou, cale)


def _stergeSemn(cale):
	try:
		os.remove(cale)
	except OSError:
		pass


def N_(text):
	"""marcaj pentru xgettext (--keyword=N_), fara efect; textul se traduce la folosire"""
	return text


# ------------------------------------------------------------------ ce a trimis receptorul despre limite
#
# Motorul DiSEqC 1.2 nu raspunde (comenzile merg intr-un singur sens, limitele stau in motor), deci starea limitelor nu
# se poate citi din el. Receptorul tine minte ce a trimis el: ultima comanda despre limite (cu ora si, la pornirile
# singure, de ce) si cand a pus limita de est si pe cea de vest (cu pozitia antenei, cand o stie). Fisierul se scrie
# numai la o comanda de limite (rar), in .nou si apoi os.replace; se citeste o data, la prima cerere.
FISIER_LIMITE = "/etc/enigma2/hds-motor-limite.json"
# sub ora asta (1.1.2020) ceasul receptorului nu e potrivit inca: ora nu se tine minte
ORA_VALIDA_DE_LA = 1577836800
# comenzile tinute minte; toate in afara de limite_oprite lasa limitele pornite (memorarea si limitele de est/vest le
# pornesc: specificatia DiSEqC 1.2 si 6A 00 trimis de noi dupa ele)
COMENZI_LIMITE = ("limite_pornite", "limite_oprite", "limita_est", "limita_vest", "memoreaza")
CAUZE_LIMITE = ("", "iesire", "ramase_oprite", "cedare")
_COMANDA_TEXT = {
	"limite_pornite": N_("Pornește limitele"),
	"limite_oprite": N_("Oprește limitele"),
	"limita_est": N_("Limita de est este aici"),
	"limita_vest": N_("Limita de vest este aici"),
	"memoreaza": N_("Memorează aici poziția"),
}
_CAUZA_TEXT = {
	"iesire": N_("trimisă singură la ieșire"),
	"ramase_oprite": N_("trimisă singură: rămăseseră oprite"),
	"cedare": N_("trimisă singură la cedarea tunerului"),
}

_limite = None


def _oraValida(ora):
	try:
		ora = int(ora)
	except (TypeError, ValueError):
		return None
	return ora if ora >= ORA_VALIDA_DE_LA else None


def _curataLimite(v):
	r = {}
	u = v.get("ultima")
	if isinstance(u, dict) and u.get("comanda") in COMENZI_LIMITE:
		r["ultima"] = {"comanda": u["comanda"], "cauza": u.get("cauza") if u.get("cauza") in CAUZE_LIMITE else "",
			"ora": _oraValida(u.get("ora"))}
	for parte in ("est", "vest"):
		p = v.get(parte)
		if isinstance(p, dict):
			try:
				orbital = int(p.get("orbital", -1))
			except (TypeError, ValueError):
				orbital = -1
			r[parte] = {"ora": _oraValida(p.get("ora")), "orbital": orbital if 0 <= orbital < 3600 else -1}
	return r


def limiteCitite():
	"""ce s-a tinut minte, pe slotul tunerului: {"<slot>": {"ultima": {comanda, cauza, ora}, "est": {ora, orbital},
	"vest": {...}}}; citit de pe disc o singura data"""
	global _limite
	if _limite is None:
		_limite = {}
		try:
			with open(FISIER_LIMITE, encoding="utf-8") as f:
				date = json.load(f)
			for cheie, v in (date.get("sloturi") or {}).items():
				if isinstance(v, dict):
					_limite[str(cheie)] = _curataLimite(v)
		except (IOError, OSError):
			pass
		except Exception as e:
			T.jurnal("jurnalul limitelor e stricat, il ignor: %r" % (e,))
	return _limite


def _scrieLimite():
	nou = FISIER_LIMITE + ".nou"
	try:
		with open(nou, "w", encoding="utf-8") as f:
			json.dump({"versiune": 1, "sloturi": limiteCitite()}, f, sort_keys=True)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, FISIER_LIMITE)
		return True
	except Exception as e:
		T.jurnal("jurnalul limitelor nu a putut fi scris: %r" % (e,))
		try:
			os.remove(nou)
		except OSError:
			pass
		return False


def noteazaLimite(slot, comanda, cauza="", orbital=None):
	"""o comanda de limite care a plecat spre motor; `orbital` = pozitia antenei cand se pune o limita (None =
	nestiuta). Intoarce True daca s-a scris pe disc. O eroare de aici nu ajunge la comanda."""
	if comanda not in COMENZI_LIMITE:
		return False
	try:
		ora = _oraValida(T.acumPerete())
		r = limiteCitite().setdefault(str(slot if slot is not None else -1), {})
		r["ultima"] = {"comanda": comanda, "cauza": cauza if cauza in CAUZE_LIMITE else "", "ora": ora}
		if comanda in ("limita_est", "limita_vest"):
			r["est" if comanda == "limita_est" else "vest"] = {"ora": ora,
				"orbital": orbital if orbital is not None and 0 <= orbital < 3600 else -1}
		T.jurnal("limite: %s%s" % (comanda, (" (%s)" % cauza) if cauza else ""))
		return _scrieLimite()
	except Exception as e:
		T.jurnal("jurnalul limitelor: %r" % (e,))
		return False


def limiteInfo(slot=None, stare="necunoscut"):
	"""Ce stie receptorul despre limitele motorului de pe `slot` (None sau -1: motorul cu cea mai noua comanda tinuta
	minte). `stare` = starea din pornirea asta a interfetei (ComenziMotor.limite); cand e „necunoscut”, starea vine din
	ultima comanda tinuta minte. Intoarce {"stare", "ultima", "cauza", "ora", "est", "vest"}; est/vest = {ora, orbital}
	sau None (nepuse de acest receptor)."""
	toate = limiteCitite()
	if slot is not None and slot >= 0:
		# numai motorul acestui tuner: limitele altui motor nu sunt ale lui
		r = toate.get(str(slot))
	else:
		r = max(toate.values(), key=lambda v: (v.get("ultima") or {}).get("ora") or 0) if toate else None
	r = r or {}
	u = r.get("ultima") or {}
	if stare not in ("pornite", "oprite"):
		if os.path.exists(FISIER_LIMITE_OPRITE):
			# semnul M3 se scrie inaintea comenzii 63, jurnalul dupa ea: o cadere intre ele lasa limitele oprite
			stare = "oprite"
		elif u.get("comanda"):
			stare = "oprite" if u["comanda"] == "limite_oprite" else "pornite"
	return {"stare": stare if stare in ("pornite", "oprite") else "necunoscut", "ultima": u.get("comanda") or "",
		"cauza": u.get("cauza") or "", "ora": u.get("ora"), "est": r.get("est"), "vest": r.get("vest")}


def oraText(ora):
	"""zi.luna.an ora:min (ziua, luna, anul, ora locala); fara ora potrivita (ceasul receptorului nepus atunci): „ora necunoscută”"""
	if not ora:
		return _("ora necunoscută")
	return time.strftime("%d.%m.%Y %H:%M", time.localtime(ora))


def limiteTexte(info):
	"""Textele limitelor, aceleasi pe televizor si in web: {"scurt" (banda de pe televizor), "stare", "est", "vest",
	"nota"}."""
	comanda = _(_COMANDA_TEXT[info["ultima"]]) if info["ultima"] in _COMANDA_TEXT else ""
	if comanda and info["cauza"] in _CAUZA_TEXT:
		comanda = "%s (%s)" % (comanda, _(_CAUZA_TEXT[info["cauza"]]))
	ora = oraText(info["ora"])
	if info["stare"] == "oprite":
		scurt = _("Limitele sunt oprite. Pornesc singure la ieșire.")
		stare = _("Limitele: oprite. Ultima comandă trimisă de acest receptor: %s, %s. Pornesc singure la ieșire.") % (
			comanda or _("Oprește limitele"), ora)
	elif info["stare"] == "pornite" and comanda:
		scurt = _("Limite: pornite, ultima comandă %s") % (time.strftime("%d.%m %H:%M", time.localtime(info["ora"]))
			if info["ora"] else _("ora necunoscută"))
		stare = _("Limitele: pornite. Ultima comandă trimisă de acest receptor: %s, %s.") % (comanda, ora)
	elif info["stare"] == "pornite":
		scurt = _("Limite: pornite")
		stare = _("Limitele: pornite.")
	else:
		scurt = _("Limite: nu se știe")
		stare = _("Limitele: nu se știe. Acest receptor nu a trimis încă nicio comandă despre limite.")
	rez = {"scurt": scurt, "stare": stare,
		"nota": _("Motorul nu poate spune receptorului dacă limitele sunt pornite: aici e ce a trimis acest receptor.")}
	# randurile scurte de pe televizor (fereastra „Limite”): Est: pusă <zi.luna.an ora:min>, antena pe 30,0°E
	for parte, eticheta in (("est", N_("Est: %s")), ("vest", N_("Vest: %s"))):
		p = info.get(parte)
		if not p:
			valoare = _("nepusă de acest receptor")
		elif p.get("orbital", -1) >= 0:
			valoare = _("pusă %s, antena pe %s") % (oraText(p.get("ora")), gradeScurt(p["orbital"]))
		else:
			valoare = _("pusă %s") % oraText(p.get("ora"))
		rez[parte + "_scurt"] = _(eticheta) % valoare
	for parte, fara, cu, cu_loc in (
			("est", N_("Limita de est: nepusă de acest receptor."), N_("Limita de est: pusă de acest receptor, %s."),
				N_("Limita de est: pusă de acest receptor, %s, cu antena pe %s.")),
			("vest", N_("Limita de vest: nepusă de acest receptor."), N_("Limita de vest: pusă de acest receptor, %s."),
				N_("Limita de vest: pusă de acest receptor, %s, cu antena pe %s."))):
		p = info.get(parte)
		if not p:
			rez[parte] = _(fara)
		elif p.get("orbital", -1) >= 0:
			rez[parte] = _(cu_loc) % (oraText(p.get("ora")), gradeScurt(p["orbital"]))
		else:
			rez[parte] = _(cu) % oraText(p.get("ora"))
	return rez


class ComenziMotor(object):
	def __init__(self):
		self.stare = "liber"
		self.slot = None
		self.stapan = None
		self.tuner = None
		self.limite = "necunoscut"
		self.pas_index = 0
		self.pozitie_stiuta = None
		self.referinta = None
		self.miscare = None
		self.ultima_miscare = None
		self.mesaj = ""
		self.mesaj_la = 0.0
		self.eroare = False
		self._nucleu_pana = 0.0
		self._tensiune_motor = False
		self._t_secv = None
		self._dupa = None
		self._t_plafon = None
		self._t_reacord = None
		self._t_paza = None
		self._t_nucleu = None
		self._t_asteptare = None
		self._asteapta = None
		self._dupa_oprire = None
		self._la_standby = False
		self._mesaj_eliberare = None
		self._mesaj_dupa_oprire = None
		self._erori_la_rand = 0
		self._trebuie_update = False
		self._web_mentine = 0.0
		self._web_ultima = 0.0
		self._semnal = None
		self._semnal_la = -10.0
		self._masca_legata = None
		self._standby_legat = False
		self._asteptare_pana = 0.0
		# programul oprit de noi, ramas fara stapan dupa o cedare si paza lui
		self._program_datorat = None
		self._t_datorat = None
		# urma motorului: cine a cerut comanda de acum si ce ("ecran"/"web", actiunea), spus nucleului chiar inaintea
		# fiecarei comenzi (_anunta); _ce_oprire = de ce pleaca oprirea (o tasta, plafonul, pagina tacuta, eliberarea)
		self._cerere = None
		self._ce_oprire = "oprire"
		self._leagaStandby()

	# ------------------------------------------------------------------ mesaje si stare

	def _spune(self, text, eroare=False):
		self.mesaj = text
		self.mesaj_la = T.acum()
		self.eroare = eroare
		if text:
			T.jurnal(text if not eroare else "eroare: %s" % text)

	def seMisca(self):
		return self.stare in ("misca_manual", "misca_nucleu")

	def ocupat(self):
		return self.stare in ("pregatire", "trimite", "oprire", "eliberare")

	def alegeSlot(self, slot):
		"""tunerul cu motor ales (cand sunt mai multe); numai cat nu e luat"""
		if self.tuner is not None:
			return False
		if slot in [s for s, _n in T.tunereCuMotor()]:
			self.slot = slot
			return True
		return False

	def _slotAles(self):
		cu_motor = [s for s, _n in T.tunereCuMotor()]
		if self.slot in cu_motor:
			return self.slot
		return cu_motor[0] if cu_motor else None

	def pasCurent(self):
		return PASI[self.pas_index]

	# ------------------------------------------------------------------ cronometre

	def _dupaMs(self, ms, functie):
		"""urmatorul pas al secventei, pe un singur eTimer"""
		self._dupa = functie
		if self._t_secv is None:
			self._t_secv = T.cronometru(self._bateSecv)
		self._t_secv.start(max(1, int(ms)), True)

	def _bateSecv(self):
		functie, self._dupa = self._dupa, None
		if functie is not None:
			self._sigur(functie)

	def _anuleazaSecv(self):
		self._dupa = None
		if self._t_secv is not None:
			self._t_secv.stop()

	def _sigur(self, functie):
		"""orice exceptie din secventa: oprirea incercata, textul pe ecran, nimic iesit din modul"""
		try:
			functie()
		except Exception as e:
			T.jurnal("exceptie in secventa: %r" % (e,))
			self._laEroare(None)

	def _pornestePlafon(self, secunde):
		if self._t_plafon is None:
			self._t_plafon = T.cronometru(self._laPlafon)
		self._t_plafon.start(max(1, int(secunde * 1000)), True)

	def _opresteCronometre(self):
		self._anuleazaSecv()
		for t in (self._t_plafon, self._t_nucleu, self._t_asteptare):
			if t is not None:
				t.stop()
		self._anuleazaReacord()

	def _anuleazaReacord(self):
		if self._t_reacord is not None:
			self._t_reacord.stop()

	# ------------------------------------------------------------------ frontendul

	def _fe(self):
		return self.tuner.frontend if self.tuner is not None else None

	def _tonOprit(self):
		from enigma import iDVBFrontend
		self._fe().setTone(iDVBFrontend.toneOff)

	def _tensiuneaMotorului(self):
		"""18 V cand nucleul roteste motorul acestui tuner pe 18 V (fara masurarea curentului, fara
		Unicable; lib/dvb/hdsrotire.h), altfel 13 V, ca ramura cu masurare si ca o imagine fara functia hdsRotireLa18V"""
		from enigma import iDVBFrontend
		try:
			if int(T.controlSec().hdsRotireLa18V(self.slot)) == 1:
				return iDVBFrontend.voltage18
		except Exception:
			pass
		return iDVBFrontend.voltage13

	def _puneTensiuneaMotorului(self):
		self._fe().setVoltage(self._tensiuneaMotorului())

	def _anunta(self, ce=None):
		"""Urma motorului (lib/dvb/hdsurmamotor.cpp): nucleul afla cine cere comanda care pleaca acum, "<cine>: motor
		<actiune>" (cine = ecran sau web, cel care a cerut-o; actiunea data sau cea ceruta ultima data)."""
		stapan, cerut = self._cerere or (None, "comanda")
		T.anuntaCererea("%s: motor %s" % (stapan or self.stapan or "ecran", ce or cerut))

	def _trimiteOcteti(self, octeti, ce=None):
		"""un mesaj DiSEqC; intoarce 0 daca driverul l-a primit. `ce` = actiunea spusa urmei motorului (implicit cea
		ceruta, _cerere)"""
		if not DishMath.isAllowed(octeti):
			T.jurnal("comanda refuzata de paza: %s" % DishMath.toHex(octeti))
			return -1000
		if T.lacatProba() and not DishMath.isSafeOnly(octeti):
			T.jurnal("lacatul de proba a oprit comanda %s" % DishMath.toHex(octeti))
			return -1001
		self._anunta(ce)
		from enigma import eDVBDiseqcCommand
		cmd = eDVBDiseqcCommand()
		cmd.setCommandString(DishMath.toHex(octeti))
		rez = self._fe().sendDiseqc(cmd)
		try:
			rez = int(rez or 0)
		except Exception:
			rez = -1
		T.jurnal("DiSEqC %s pe tunerul %s: %s" % (DishMath.toHex(octeti), T.numeTuner(self.slot), "primita" if rez == 0 else "cod %d" % rez))
		return rez

	def _nucleulLucreaza(self):
		"""True cat e posibil sa ruleze inca secventa nucleului pornita de un acord al nostru (revizia M1)"""
		if T.acum() >= self._nucleu_pana:
			return False
		if self.tuner is not None and self.tuner.stareAcord() not in ("TUNING", ""):
			self._nucleu_pana = 0.0
			return False
		return True

	def _candNucleulLiber(self, functie):
		if not self._nucleulLucreaza():
			functie()
			return
		self._dupaMs(100, lambda: self._candNucleulLiber(functie))

	def _acorda(self, tp, fara_motor):
		ok = self.tuner.acorda(tp, fara_motor)
		self._tensiune_motor = False
		self._nucleu_pana = T.acum() + ASTEPTARE_SECVENTA_S
		self._semnal = None
		return ok

	def _comanda(self, octeti, porneste_motorul, apoi, ce=None):
		"""ton oprit, 25 ms (spec 4.2 p. 8, sec.cpp:740-745), tensiunea motorului si 500 ms numai pentru comenzile care
		pornesc motorul (ca ramura fara masurarea curentului din sec.cpp: 18 V cand nucleul roteste motorul pe 18 V, altfel
		13 V), apoi mesajul. Tensiunea ramane pana la acordul de referinta de dupa oprire. Chemata numai cu nucleul liber."""
		self._anuleazaReacord()
		self.stare = "trimite"
		self._tonOprit()

		def trimite():
			rez = self._trimiteOcteti(octeti, ce)
			if rez != 0:
				self._laEroare(rez)
				return
			if porneste_motorul:
				try:
					from Components import HdsAfisaj
					HdsAfisaj.motorPornit()
				except Exception:
					pass
			apoi()

		def dupa_ton():
			if porneste_motorul and not self._tensiune_motor:
				self._puneTensiuneaMotorului()
				self._tensiune_motor = True
				self._dupaMs(_cfg("delay_after_voltage_change_before_motor_command", 500), trimite)
			else:
				trimite()

		self._dupaMs(_cfg("delay_after_continuous_tone_disable_before_diseqc", 25), dupa_ton)

	# ------------------------------------------------------------------ disponibil / luarea tunerului

	def motivIndisponibil(self):
		motiv = T.motivIndisponibil()
		if motiv:
			return motiv
		slot = self._slotAles()
		if self.tuner is None and slot is not None and T.inregistrarePeAntena(slot):
			return _("O înregistrare folosește acum antena. Comenzile pornesc după ce se termină.")
		return None

	def _cere(self, stapan, lucru, ce="comanda"):
		"""porneste `lucru` (un lant de comenzi) cand tunerul e luat si nucleul e liber; `ce` = actiunea, pentru urma
		motorului"""
		motiv = self.motivIndisponibil()
		if motiv:
			self._spune(motiv)
			return False, motiv
		self._cerere = (stapan or "ecran", ce)
		if stapan == "web":
			self._web_ultima = T.acum()
		if self.stapan is None:
			self.stapan = stapan
		self.eroare = False
		self._asteapta = lucru
		if self.tuner is None:
			if self.stare == "pregatire":
				return True, ""
			return self._ia()
		if self.stare == "pregatire":
			# se asteapta tunerul sau secventa nucleului: comanda noua o inlocuieste pe cea amanata
			return True, ""
		self._anuleazaReacord()
		if self._nucleulLucreaza():
			self.stare = "pregatire"
		self._candNucleulLiber(self._ruleazaAmanata)
		return True, ""

	def _ruleazaAmanata(self):
		"""porneste comanda amanata; fiecare lant isi pune singur starea (trimite, misca_...)"""
		lucru, self._asteapta = self._asteapta, None
		self.stare = "gata"
		self._erori_la_rand = 0
		if lucru is not None:
			self._sigur(lucru)

	def _tastaInMiscare(self, pas_est=None, stapan=None):
		"""(True, rezultat) daca tasta s-a folosit pentru oprire sau a fost ignorata. Cat se misca motorul sau pleaca o
		comanda, orice tasta de comanda doar opreste; singura exceptie e inca un pas in aceeasi directie. Cat se trimite
		oprirea sau se da tunerul inapoi, tastele de comanda nu fac nimic (comanda noua se da dupa oprire)."""
		if self.stare in ("oprire", "eliberare"):
			return True, (True, "")
		if self.seMisca():
			m = self.miscare or {}
			if pas_est is not None and self.stare == "misca_manual" and m.get("tip") == "pas" and m.get("est") == bool(pas_est):
				self._cerere = (stapan or "ecran", "pas")
				return True, self._incaUnPas(pas_est)
			self._cerere = (stapan or "ecran", "oprire")
			return True, self._opresteLaTasta()
		if self.stare == "trimite":
			self._cerere = (stapan or "ecran", "oprire")
			return True, self._opresteLaTasta()
		return False, None

	def ia(self, stapan):
		"""luarea tunerului fara nicio comanda (pagina web, dupa confirmare)"""
		if self.tuner is not None:
			return True, ""
		return self._cere(stapan, lambda: None)

	def _ia(self):
		slot = self._slotAles()
		secunde = T.secundePanaLaInregistrare()
		if secunde is not None and secunde <= INREGISTRARE_REFUZ_S:
			text = _("Peste mai puțin de un minut pornește o înregistrare. Comenzile motorului nu pornesc acum.")
			self._asteapta = None
			self.stapan = None
			self._spune(text)
			return False, text
		self.slot = slot
		self.stare = "pregatire"
		sec = T.controlSec()
		try:
			miscand = sec is not None and sec.hdsRotorMovingSlot() == slot
		except Exception:
			miscand = False
		if miscand:
			try:
				secunde_nucleu = max(0, int(sec.hdsRotorSeconds(slot)))
			except Exception:
				secunde_nucleu = 360
			self._asteptare_pana = T.acum() + secunde_nucleu + 5
			try:
				tinta = sec.hdsRotorToOrbital(slot)
			except Exception:
				tinta = -1
			self._spune(_("Antena încă merge spre %s. Comenzile pornesc după ce ajunge.") % (satelitText(tinta) or _("satelitul programului")))
			self._asteaptaNucleulDinProgram()
			return True, ""
		self._iaAcum()
		return True, ""

	def _asteaptaNucleulDinProgram(self):
		if self.stare != "pregatire" or self.tuner is not None:
			return
		sec = T.controlSec()
		try:
			miscand = sec.hdsRotorMovingSlot() == self.slot
		except Exception:
			miscand = False
		if miscand and T.acum() < self._asteptare_pana:
			if self._t_asteptare is None:
				self._t_asteptare = T.cronometru(lambda: self._sigur(self._asteaptaNucleulDinProgram))
			self._t_asteptare.start(ASTEPTARE_NUCLEU_PAS_MS, True)
			return
		self._iaAcum()

	def _iaAcum(self):
		slot = self.slot
		# transponderul programului se citeste inainte ca LuareTuner sa il opreasca
		tp_program, semnal = T.programPeTuner(slot)
		self.pozitie_stiuta = None
		if tp_program is not None and semnal:
			self.pozitie_stiuta = tp_program["orbital_position"]
		if self.referinta is None:
			self.referinta = tp_program
		self.tuner = T.TunerMotor(slot, la_cedare=self.cedeaza)
		self._predaProgramulDatorat()
		secunde = T.secundePanaLaInregistrare()
		if secunde is not None and secunde <= INREGISTRARE_AVERTISMENT_S:
			self._spune(_("Peste %d minute pornește o înregistrare. Comenzile se opresc atunci singure.") % max(1, int(secunde // 60)))
		self.tuner.ia(lambda ok, motiv: self._sigur(lambda: self._tunerLuat(ok, motiv)))

	def _tunerLuat(self, ok, motiv=""):
		if self.tuner is None:
			return
		if not ok:
			# LuareTuner a pus deja programul la loc
			self._asteapta = None
			self._elibereazaTot(pune_programul=False)
			if motiv == "inregistrare":
				self._spune(_("O înregistrare folosește acum antena. Comenzile pornesc după ce se termină."))
			else:
				self._spune(_("Tunerul cu motor e folosit de altcineva (o transmisie în rețea sau o extensie)."))
			return
		T.jurnal("tunerul %s luat pentru comenzile motorului" % T.numeTuner(self.slot))
		self._leagaMasca()
		self._pornestePaza()
		if self.referinta is None:
			self.referinta = self._referintaImplicita()
		if self.referinta is None or not self._acorda(self.referinta, True):
			orbital = self.referinta["orbital_position"] if self.referinta else -1
			self._asteapta = None
			self._elibereazaTot(pune_programul=True)
			if self.referinta is None:
				self._spune(_("Pentru satelitul ales nu există niciun transponder în lista de sateliți, deci receptorul nu are ce acorda."), eroare=True)
			else:
				self._spune(_("Tunerul nu a putut fi pregătit pe %s.") % satelitText(orbital), eroare=True)
			return
		self._candNucleulLiber(self._dupaLuare)

	def _referintaImplicita(self):
		"""transponderul de referinta cand programul nu era pe tunerul cu motor: ultima tinta a nucleului, pozitia
		stiuta de nucleu, altfel primul satelit al tunerului"""
		sec = T.controlSec()
		candidati = []
		for nume in ("hdsRotorToOrbital", "hdsKnownRotorPosition"):
			try:
				valoare = int(getattr(sec, nume)(self.slot))
				if valoare >= 0:
					candidati.append(valoare)
			except Exception:
				continue
		candidati += [o for o, _n in T.sateliti(self.slot)]
		for orbital in candidati:
			tp = T.alegeTransponder(T.transpondereBune(orbital, self.slot))
			if tp:
				return tp
		return None

	def _dupaLuare(self):
		self.stare = "gata"
		if os.path.exists(FISIER_LIMITE_OPRITE):
			# M3: limitele au ramas oprite (enigma2 a cazut sau s-a luat curentul intre 63 si 6A 00)
			def gata():
				_stergeSemn(FISIER_LIMITE_OPRITE)
				self.limite = "pornite"
				noteazaLimite(self.slot, "limite_pornite", "ramase_oprite")
				self._spune(_("Limitele au rămas oprite la ultima folosire; le-am pornit."))
				self._laSfarsitDeComanda(reacord=True)
			self._comanda(DishMath.limitsOn(), False, gata, ce="limite pornite (ramase oprite)")
			return
		self._laSfarsitDeComanda(reacord=False)

	def _laSfarsitDeComanda(self, reacord):
		"""comanda s-a terminat (fara miscare): comanda amanata, daca e, altfel acordul la loc (tonul a fost oprit)"""
		self.stare = "gata"
		if self._asteapta is not None:
			self._candNucleulLiber(self._ruleazaAmanata)
			return
		if reacord:
			self._programeazaReacord()
		elif self._dupa_oprire is not None:
			urmatorul, self._dupa_oprire = self._dupa_oprire, None
			urmatorul()

	def _programeazaReacord(self):
		"""acordul de referinta la loc, ca semnalul citit sa fie adevarat (tonul si tensiunea au fost ale noastre).
		Orice comanda noua il anuleaza (revizia M1)."""
		if self._dupa_oprire is not None:
			urmatorul, self._dupa_oprire = self._dupa_oprire, None
			urmatorul()
			return
		if self._t_reacord is None:
			self._t_reacord = T.cronometru(lambda: self._sigur(self._reacordeaza))
		self._t_reacord.start(_cfg("delay_after_motor_stop_command", 500), True)

	def _reacordeaza(self):
		if self.tuner is None or self.stare != "gata" or self.referinta is None:
			return
		if not self._acorda(self.referinta, True):
			self._spune(_("Tunerul nu a putut fi pregătit pe %s.") % satelitText(self.referinta["orbital_position"]), eroare=True)
		else:
			self._erori_la_rand = 0

	# ------------------------------------------------------------------ miscarile manuale

	def _pornesteMiscare(self, tip, est, octeti, plafon_s, la=-1, cmd=-1, pozitie=None, stapan=None):
		sec = T.controlSec()
		de_la = self.pozitie_stiuta if self.pozitie_stiuta is not None else -1
		self._uitaPozitia()
		try:
			# hdsNoteRotorMovement inaintea lui setRotorMoving: altfel ceasul unei miscari vechi se reia (sec.cpp:1528-1538)
			sec.hdsNoteRotorMovement(self.slot, de_la, la, cmd, 0, int(plafon_s + 0.999))
			sec.setRotorMoving(self.slot, True)
		except Exception as e:
			T.jurnal("starea miscarii nu a putut fi notata: %r" % (e,))
		self.pozitie_stiuta = None
		if self.mesaj and T.acum() - self.mesaj_la > 1.0:
			# un mesaj vechi („Motorul s-a oprit") ar minti cat merge miscarea noua; cel de acum (sub o secunda, de
			# exemplu limitele pornite la luarea tunerului) ramane
			self._spune("")
		self.miscare = {"tip": tip, "est": est, "octeti": list(octeti), "pornit": T.acum(), "plafon_s": float(plafon_s),
			"la": la, "pozitie": pozitie, "stapan": stapan or self.stapan}
		self.stare = "misca_manual"
		self._pornestePlafon(plafon_s)

	def _uitaPozitia(self):
		"""dupa o miscare manuala nucleul nu mai stie unde e antena (sec.cpp:735): o uitam, ca la urmatorul acord sa trimita
		din nou comanda. Fara functia din nucleu (imagine veche): sec.update() o singura data, la iesire (revizia m5f)."""
		sec = T.controlSec()
		try:
			sec.hdsForgetRotorPosition(self.slot)
		except AttributeError:
			self._trebuie_update = True
		except Exception as e:
			T.jurnal("pozitia nu a putut fi uitata: %r" % (e,))
			self._trebuie_update = True

	def _laPlafon(self):
		if self.seMisca():
			T.jurnal("plafonul de timp al miscarii a trecut; opresc motorul")
			self._opreste(ce="oprire la plafonul de timp")

	def _plafonPas(self, pasi):
		return min(PAS_MAX_S, PAS_BAZA_S + PAS_PE_PAS_S * pasi)

	def pas(self, est, stapan="ecran"):
		"""un pas (de marimea aleasa) spre est sau vest; in timpul unui pas in aceeasi directie, inca un pas"""
		oprit, rez = self._tastaInMiscare(pas_est=est, stapan=stapan)
		if oprit:
			return rez
		refuz = self._refuzLacat()
		if refuz:
			return False, refuz
		pasi = self.pasCurent()
		octeti = DishMath.drive(bool(est), steps=pasi)

		def lucru():
			self._comanda(octeti, True, lambda: self._pornesteMiscare("pas", bool(est), octeti, self._plafonPas(pasi), stapan=stapan))
		return self._cere(stapan, lucru, "pas")

	def _incaUnPas(self, est):
		pasi = self.pasCurent()
		octeti = DishMath.drive(bool(est), steps=pasi)
		self._t_plafon.stop()

		def dupa():
			self.stare = "misca_manual"
			self.miscare["octeti"] = list(octeti)
			self.miscare["plafon_s"] = (T.acum() - self.miscare["pornit"]) + self._plafonPas(pasi)
			self._pornestePlafon(self._plafonPas(pasi))
		self._comanda(octeti, True, dupa)
		return True, ""

	def continuu(self, est, stapan="ecran"):
		"""miscare fara oprire pana la a doua apasare sau pana la plafon; timpul e trimis si in comanda (68 1E = 30 s),
		ca motoarele care il inteleg sa se opreasca singure si daca enigma2 nu mai trimite oprirea"""
		oprit, rez = self._tastaInMiscare(stapan=stapan)
		if oprit:
			return rez
		refuz = self._refuzLacat()
		if refuz:
			return False, refuz
		secunde = CONTINUU_FARA_LIMITE_S if self.limite == "oprite" else CONTINUU_S
		octeti = DishMath.drive(bool(est), seconds=secunde)
		if stapan == "web":
			self._web_mentine = T.acum()

		def lucru():
			self._comanda(octeti, True, lambda: self._pornesteMiscare("continuu", bool(est), octeti, secunde, stapan=stapan))
		return self._cere(stapan, lucru, "continuu")

	def laPozitie(self, pozitie, stapan="ecran"):
		"""E0 31 6B nn: motorul merge singur la pozitia memorata N (1..255)"""
		oprit, rez = self._tastaInMiscare(stapan=stapan)
		if oprit:
			return rez
		try:
			pozitie = int(pozitie)
		except Exception:
			pozitie = -1
		if not 1 <= pozitie <= 255:
			return False, _("Poziția trebuie să fie un număr între 1 și 255.")
		return self._mergiLa(pozitie, stapan)

	def laReferinta(self, stapan="ecran"):
		"""E0 31 6B 00: pozitia de referinta a motorului"""
		oprit, rez = self._tastaInMiscare(stapan=stapan)
		if oprit:
			return rez
		return self._mergiLa(0, stapan)

	def _mergiLa(self, pozitie, stapan):
		refuz = self._refuzLacat() or self._refuzFaraLimite()
		if refuz:
			return False, refuz
		octeti = DishMath.gotoStored(pozitie)
		slot = self._slotAles()
		la = T.pozitieLegata(slot, pozitie) if pozitie else -1
		plafon = float(POZITIE_MAX_S)
		if la >= 0 and self.pozitie_stiuta is not None:
			# ca nucleul (sec.cpp:857-863): 0,5 grade pe secunda plus rezerva
			distanta = abs(la - self.pozitie_stiuta) % 3600
			distanta = min(distanta, 3600 - distanta) / 10.0
			plafon = min(plafon, distanta / 0.5 + 5)

		def lucru():
			if la >= 0:
				tp = T.alegeTransponder(T.transpondereBune(la, slot))
				if tp:
					self.referinta = tp   # M4: semnalul se citeste de acum pe satelitul ales
			self._comanda(octeti, True, lambda: self._pornesteMiscare("referinta" if pozitie == 0 else "pozitie", None, octeti,
				plafon, la=la, cmd=pozitie, pozitie=pozitie, stapan=stapan))
		return self._cere(stapan, lucru, "la_referinta" if pozitie == 0 else "la_pozitie")

	# ------------------------------------------------------------------ mergi la satelit (nucleul calculeaza USALS)

	def laSatelit(self, orbital, stapan="ecran"):
		"""acord pe un transponder al satelitului cu comanda de motor lasata nucleului: el calculeaza unghiul USALS
		(sec.cpp:497-548), trimite oprirea dubla si 6E, asteapta semnalul si noteaza miscarea (sec.cpp:852-921)"""
		oprit, rez = self._tastaInMiscare(stapan=stapan)
		if oprit:
			return rez
		refuz = self._refuzLacat() or self._refuzFaraLimite()
		if refuz:
			return False, refuz
		try:
			orbital = int(orbital)
		except Exception:
			orbital = -1
		slot = self._slotAles()
		if orbital not in [o for o, _n in T.sateliti(slot)]:
			return False, _("Pentru satelitul ales nu există niciun transponder în lista de sateliți, deci receptorul nu are ce acorda.")
		# calculul USALS cere locul antenei (Components/HdsLocul.py); fara el nucleul nici nu are satelitul
		refuz = T.refuzFaraLoc(slot, orbital)
		if refuz:
			return False, refuz
		tp = T.alegeTransponder(T.transpondereBune(orbital, slot))
		if tp is None:
			return False, _("Pentru satelitul ales nu există niciun transponder în lista de sateliți, deci receptorul nu are ce acorda.")

		def lucru():
			self.referinta = tp   # M4
			# comanda de motor o trimite nucleul in acord: urma afla inainte cine a cerut-o
			self._anunta()
			if not self._acorda(tp, False):
				self.stare = "gata"
				self._spune(_("Tunerul nu a putut fi pregătit pe %s.") % satelitText(orbital), eroare=True)
				return
			self._uitaPozitia()
			sec = T.controlSec()
			try:
				secunde = int(sec.hdsRotorSeconds(self.slot))
			except Exception:
				secunde = _cfg("motor_running_timeout", 360)
			if secunde <= 0:
				secunde = _cfg("motor_running_timeout", 360)
			self.pozitie_stiuta = None
			self.miscare = {"tip": "satelit", "est": None, "octeti": [], "pornit": T.acum(),
				"plafon_s": float(secunde + NUCLEU_REZERVA_S), "la": orbital, "pozitie": None, "vazut": False,
				"stapan": stapan}
			self.stare = "misca_nucleu"
			self._spune(_("Receptorul așteaptă semnal pe %s ca să știe că antena a ajuns.") % transponderText(tp))
			self._urmaresteNucleul()
		return self._cere(stapan, lucru, "la_satelit")

	def _urmaresteNucleul(self):
		if self.stare != "misca_nucleu" or self.miscare is None:
			return
		sec = T.controlSec()
		try:
			miscand = sec.hdsRotorMovingSlot() == self.slot
		except Exception:
			miscand = False
		trecut = T.acum() - self.miscare["pornit"]
		if miscand:
			self.miscare["vazut"] = True
		elif self.miscare["vazut"] or (trecut > 5 and self.tuner.stareAcord() != "TUNING"):
			self._nucleulAAjuns()
			return
		if trecut >= self.miscare["plafon_s"]:
			T.jurnal("timpul maxim al motorului a trecut fara semnal; opresc motorul")
			self._opreste(ce="oprire, timpul maxim trecut fara semnal")
			return
		if self._t_nucleu is None:
			self._t_nucleu = T.cronometru(lambda: self._sigur(self._urmaresteNucleul))
		self._t_nucleu.start(500, True)

	def _nucleulAAjuns(self):
		semnal = self.tuner.semnal() if self.tuner is not None else {"prins": False}
		orbital = self.miscare["la"]
		self.ultima_miscare = dict(self.miscare, oprit_la=T.acum(), oprita_de_noi=False)
		self.miscare = None
		self.stare = "gata"
		self._tensiune_motor = False
		# nucleul trece tinta drept pozitie stiuta si fara semnal, la expirarea timpului (revizia M5): noi o stim numai
		# cu semnal
		self.pozitie_stiuta = orbital if semnal.get("prins") else None
		if semnal.get("prins"):
			self._spune(_("Antena a ajuns pe %s, semnal recepționat.") % satelitText(orbital))
		else:
			self._spune(_("Antena a ajuns pe %s, dar încă nu are semnal.") % satelitText(orbital))
		self._laSfarsitDeComanda(reacord=False)

	# ------------------------------------------------------------------ oprirea

	def _opresteLaTasta(self):
		self._opreste()
		return True, ""

	def opreste(self, stapan="ecran"):
		"""Oprire. Cat nu se misca nimic si tunerul nu e luat, nu face nimic (o apasare din greseala nu opreste programul)."""
		self._cerere = (stapan or "ecran", "oprire")
		if self.seMisca() or (self.stare == "trimite" and self.miscare is not None):
			self._opreste()
			return True, ""
		if self.stare == "trimite":
			# o comanda de miscare poate fi deja pe drum (tonul oprit, tensiunea motorului): o oprire in plus nu strica nimic
			self._opreste()
			return True, ""
		if self.stare == "pregatire":
			self._asteapta = None
			if self.tuner is None or self.tuner.frontend is None:
				self._elibereazaTot(pune_programul=True)
				self._spune(_("Comanda a fost anulată."))
				return True, ""
			self._spune(_("Comanda a fost anulată."))
			return True, ""
		return True, ""

	def _opreste(self, apoi=None, ce="oprire"):
		self._ce_oprire = ce
		if apoi is not None:
			self._dupa_oprire = apoi
		if self.tuner is None or self.tuner.frontend is None:
			if apoi is not None:
				self._dupa_oprire = None
				apoi()
			return
		self._opresteCronometre()
		self._asteapta = None
		tip = self.miscare["tip"] if self.miscare else ""
		self.stare = "oprire"
		if tip == "satelit":
			# M1: intai acordul de referinta, care golește secventa nucleului (cu 6E si tonul final), apoi oprirea
			if not self._acorda(self.referinta, True):
				T.jurnal("acordul de oprire nu a mers; trimit oprirea direct")
				self._nucleu_pana = 0.0
			self._candNucleulLiber(self._oprireDubla)
			return
		self._oprireDubla()

	def _oprireDubla(self):
		self.stare = "oprire"
		self._tonOprit()
		rezultate = []

		def a_doua():
			rezultate.append(self._trimiteOcteti(DishMath.halt(), self._ce_oprire))
			self._dupaOprireDubla(rezultate)

		def prima():
			rezultate.append(self._trimiteOcteti(DishMath.halt(), self._ce_oprire))
			self._dupaMs(INTRE_OPRIRI_MS, a_doua)

		self._dupaMs(_cfg("delay_after_continuous_tone_disable_before_diseqc", 25), prima)

	def _dupaOprireDubla(self, rezultate):
		sec = T.controlSec()
		try:
			sec.setRotorMoving(self.slot, False)
		except Exception:
			pass
		if self.miscare is not None:
			# antena s-a oprit undeva pe drum: nici noi, nici nucleul nu stim unde
			self._uitaPozitia()
			self.ultima_miscare = dict(self.miscare, oprit_la=T.acum(), oprita_de_noi=True)
			self.miscare = None
			self.pozitie_stiuta = None
		mesaj, self._mesaj_dupa_oprire = self._mesaj_dupa_oprire, None
		if all(r != 0 for r in rezultate):
			self._spune(_("Nici oprirea nu a putut fi trimisă. Dacă antena încă se mișcă, oprește receptorul din buton."), eroare=True)
		else:
			self._spune(mesaj or _("Motorul s-a oprit"))
		self.stare = "gata"
		self._programeazaReacord()

	def _laEroare(self, cod):
		"""comanda refuzata de driver sau o exceptie: oprirea incercata pe loc, textul pe ecran"""
		self._opresteCronometre()
		self._asteapta = None
		rez = -1
		if self._fe() is not None:
			try:
				self._tonOprit()
				rez = self._trimiteOcteti(DishMath.halt(), "oprire dupa eroare")
			except Exception:
				rez = -1
			try:
				T.controlSec().setRotorMoving(self.slot, False)
			except Exception:
				pass
		if self.miscare is not None:
			self._uitaPozitia()
			self.ultima_miscare = dict(self.miscare, oprit_la=T.acum(), oprita_de_noi=True)
			self.miscare = None
		self.stare = "gata" if self.tuner is not None else "liber"
		if rez != 0:
			self._spune(_("Nici oprirea nu a putut fi trimisă. Dacă antena încă se mișcă, oprește receptorul din buton."), eroare=True)
		elif cod is None:
			self._spune(_("Comanda nu a putut fi trimisă din cauza unei erori în receptor. Am trimis oprirea."), eroare=True)
		elif cod in (-1000, -1001):
			self._spune(_("Mod de probă: se pot trimite numai oprirea și pornirea limitelor."), eroare=True)
		else:
			self._spune(_("Tunerul nu a acceptat comanda (cod %d). Am trimis oprirea.") % cod, eroare=True)
		# o eroare care se repeta (de exemplu chiar la acordul la loc) nu are voie sa porneasca o bucla de opriri si
		# acorduri: dupa a doua la rand acordul la loc nu se mai programeaza; comanda urmatoare a omului il reia
		self._erori_la_rand += 1
		if self.tuner is not None and self._erori_la_rand <= 1:
			self._programeazaReacord()

	# ------------------------------------------------------------------ limite si memorare

	def confirmare(self, actiune, pozitie=None):
		"""textul intrebarii pentru comenzile care suprascriu ceva (acelasi pe televizor si in web), sau None"""
		if actiune == "memoreaza":
			text = _("Poziția %d din memoria motorului se înlocuiește cu poziția de acum. Continui?") % int(pozitie)
			orbital = T.pozitieLegata(self._slotAles(), int(pozitie))
			if orbital >= 0:
				text = "%s\n%s" % (_("În setările tunerului, poziția %d e folosită pentru %s.") % (int(pozitie), satelitText(orbital)), text)
			return text
		if actiune == "limita_est":
			return _("Limita de est se mută în poziția de acum a antenei. Continui?")
		if actiune == "limita_vest":
			return _("Limita de vest se mută în poziția de acum a antenei. Continui?")
		if actiune == "limite_oprite":
			return _("Fără limite, motorul poate duce antena în opritor și rupe cablul. Oprește-le numai ca să pui limite noi, cu ochii pe antenă. Pornesc singure la ieșire. Le oprești?")
		return None

	def _refuzLacat(self):
		if T.lacatProba():
			return _("Mod de probă: se pot trimite numai oprirea și pornirea limitelor.")
		return None

	def _refuzFaraLimite(self):
		if self.limite == "oprite":
			return _("Pornește întâi limitele: fără ele, antena poate merge până în opritor.")
		return None

	def memoreaza(self, pozitie, confirmat=False, stapan="ecran"):
		oprit, rez = self._tastaInMiscare(stapan=stapan)
		if oprit:
			return rez
		try:
			pozitie = int(pozitie)
		except Exception:
			pozitie = -1
		if not 1 <= pozitie <= 255:
			return False, _("Poziția trebuie să fie un număr între 1 și 255.")
		if not confirmat:
			return False, self.confirmare("memoreaza", pozitie)
		refuz = self._refuzLacat()
		if refuz:
			return False, refuz

		def gata():
			# spec 4.2 p. 20: dupa memorare limitele sunt pornite
			self.limite = "pornite"
			_stergeSemn(FISIER_LIMITE_OPRITE)
			noteazaLimite(self.slot, "memoreaza")
			self._spune(_("Poziția %d a fost memorată în motor. Limitele sunt pornite.") % pozitie)
			self._laSfarsitDeComanda(reacord=True)

		return self._cere(stapan, lambda: self._comanda(DishMath.store(pozitie), False, gata), "memoreaza")

	def _limita(self, est, confirmat, stapan):
		oprit, rez = self._tastaInMiscare(stapan=stapan)
		if oprit:
			return rez
		if not confirmat:
			return False, self.confirmare("limita_est" if est else "limita_vest")
		refuz = self._refuzLacat()
		if refuz:
			return False, refuz

		def porneste_limitele():
			self._dupaMs(INTRE_MESAJE_MS, lambda: self._comanda(DishMath.limitsOn(), False, gata))

		# pozitia antenei cand se pune limita (None dupa pasi sau miscare continua: nestiuta), luata la cerere
		orbital = self.pozitie_stiuta

		def gata():
			# 66/67 pornesc limitele numai „recomandat" (spec); 6A 00 trimis de noi face starea adevarata
			self.limite = "pornite"
			_stergeSemn(FISIER_LIMITE_OPRITE)
			noteazaLimite(self.slot, "limita_est" if est else "limita_vest", orbital=orbital)
			if est:
				self._spune(_("Limita de est a fost pusă aici. Limitele sunt pornite."))
			else:
				self._spune(_("Limita de vest a fost pusă aici. Limitele sunt pornite."))
			self._laSfarsitDeComanda(reacord=True)

		octeti = DishMath.limitEast() if est else DishMath.limitWest()
		return self._cere(stapan, lambda: self._comanda(octeti, False, porneste_limitele), "limita_est" if est else "limita_vest")

	def limitaEst(self, confirmat=False, stapan="ecran"):
		return self._limita(True, confirmat, stapan)

	def limitaVest(self, confirmat=False, stapan="ecran"):
		return self._limita(False, confirmat, stapan)

	def limitePornite(self, stapan="ecran"):
		oprit, rez = self._tastaInMiscare(stapan=stapan)
		if oprit:
			return rez

		def gata():
			self.limite = "pornite"
			_stergeSemn(FISIER_LIMITE_OPRITE)
			noteazaLimite(self.slot, "limite_pornite")
			self._spune(_("Limite: pornite"))
			self._laSfarsitDeComanda(reacord=True)
		return self._cere(stapan, lambda: self._comanda(DishMath.limitsOn(), False, gata), "limite_pornite")

	def limiteOprite(self, confirmat=False, stapan="ecran"):
		"""63 (Limits Off) numai cu avertismentul confirmat. De ce nu deloc: limitele soft se largesc numai trecand pe
		langa cele vechi, iar fara 63 cine le-a pus prea stramt nu le mai poate muta (proiectul B, H-M4). Cat sunt oprite:
		miscarea continua 10 s, nicio comanda „mergi la", rosu in banda, 6A 00 la iesire si la prima folosire (M3)."""
		oprit, rez = self._tastaInMiscare(stapan=stapan)
		if oprit:
			return rez
		if not confirmat:
			return False, self.confirmare("limite_oprite")
		refuz = self._refuzLacat()
		if refuz:
			return False, refuz

		def trimite():
			try:
				_scrieSemn(FISIER_LIMITE_OPRITE)
			except Exception as e:
				T.jurnal("semnul limitelor oprite nu a putut fi scris: %r" % (e,))
				self.stare = "gata"
				self._spune(_("Limitele nu au fost oprite: receptorul nu a putut ține minte asta pe disc."), eroare=True)
				return

			def gata():
				self.limite = "oprite"
				noteazaLimite(self.slot, "limite_oprite")
				self._spune(_("Limitele sunt oprite. Pornesc singure la ieșire."))
				self._laSfarsitDeComanda(reacord=True)
			self._comanda(DishMath.limitsOff(), False, gata)
		return self._cere(stapan, trimite, "limite_oprite")

	def marimePas(self, delta):
		self.pas_index = max(0, min(len(PASI) - 1, self.pas_index + (1 if delta > 0 else -1)))
		return True, _("Pas: %d") % self.pasCurent()

	# ------------------------------------------------------------------ web

	def mentine(self, stapan="web"):
		"""pagina web e inca deschisa; fara asta, miscarea continua pornita din web se opreste dupa WEB_MENTINE_S"""
		self._web_mentine = T.acum()
		self._web_ultima = T.acum()
		return True, ""

	# ------------------------------------------------------------------ darea tunerului inapoi

	def elibereaza(self, stapan=None, la_standby=False, mesaj=None):
		"""Oprire daca merge, limitele pornite daca au ramas oprite, uitarea pozitiei, tunerul dat inapoi, programul la
		loc (sau dat ecranului Standby). Lantul se termina si dupa ce ecranul s-a inchis: sta aici, nu in ecran.
		`mesaj` se arata la sfarsit (de ce s-a dat tunerul inapoi)."""
		if stapan is not None and self.stapan is not None and stapan != self.stapan and not la_standby:
			return False, ""
		self._la_standby = self._la_standby or la_standby
		if mesaj:
			self._mesaj_eliberare = mesaj
			self._spune(mesaj)
		if self.tuner is None or self.tuner.frontend is None:
			if self.stare == "pregatire" or self.tuner is not None:
				self._opresteCronometre()
				self._elibereazaTot(pune_programul=True)
			# dupa o cedare tunerul nu mai e al nostru, dar programul oprit de noi da (G3): porneste acum daca tunerul e
			# liber, altfel cand se elibereaza
			self._pazaDatorat()
			return True, ""
		if self.stare == "eliberare":
			return True, ""
		self._asteapta = None
		if self.seMisca() or self.stare in ("trimite", "oprire"):
			self._opreste(apoi=self._eliberareLimite, ce="oprire la eliberarea tunerului")
			return True, ""
		self._opresteCronometre()
		self._candNucleulLiber(self._eliberareLimite)
		return True, ""

	def _eliberareLimite(self):
		self._anuleazaReacord()
		if self.limite == "oprite" or os.path.exists(FISIER_LIMITE_OPRITE):
			self.stare = "eliberare"

			def gata():
				self.limite = "pornite"
				_stergeSemn(FISIER_LIMITE_OPRITE)
				noteazaLimite(self.slot, "limite_pornite", "iesire")
				self._eliberareFinal()

			def trimite():
				self._comanda(DishMath.limitsOn(), False, gata, ce="limite pornite la eliberarea tunerului")
				self.stare = "eliberare"
			self._candNucleulLiber(trimite)
			return
		self._eliberareFinal()

	def _eliberareFinal(self):
		self._elibereazaTot(pune_programul=True)

	def _elibereazaTot(self, pune_programul):
		self._opresteCronometre()
		self._opresteDupaLuare()
		if self._trebuie_update and self.miscare is None:
			self._actualizeazaSec()
		la_standby, self._la_standby = self._la_standby, False
		if self.tuner is not None:
			self.tuner.elibereaza(reda_canalul=pune_programul, la_standby=la_standby)
		self.tuner = None
		self.stare = "liber"
		self.stapan = None
		self.miscare = None
		self.referinta = None
		self.pozitie_stiuta = None
		self._tensiune_motor = False
		self._nucleu_pana = 0.0
		self._dupa_oprire = None
		self._semnal = None
		T.jurnal("tunerul dat inapoi, programul %s" % ("dat ecranului Standby" if la_standby else
			("pus la loc" if pune_programul else "neatins de noi")))
		mesaj, self._mesaj_eliberare = self._mesaj_eliberare, None
		if mesaj:
			self._spune(mesaj)

	def _actualizeazaSec(self):
		"""rezerva din H-M2 pentru o imagine fara hdsForgetRotorPosition: sec.update() uita pozitia pe TOATE tunerele
		(sec.cpp:1000-1035), deci numai la iesire, cu motorul oprit si fara nicio inregistrare in curs (revizia m5f)"""
		try:
			import NavigationInstance
			if NavigationInstance.instance is not None and NavigationInstance.instance.getRecordings():
				T.jurnal("pozitia motorului nu a fost uitata: o inregistrare e in curs")
				return
			from Components.NimManager import nimmanager
			nimmanager.sec.update()
			self._trebuie_update = False
			T.jurnal("pozitia motorului uitata prin sec.update() (nucleul nu are hdsForgetRotorPosition)")
		except Exception as e:
			T.jurnal("sec.update() a dat eroare: %r" % (e,))

	# ------------------------------------------------------------------ paza: standby, inregistrari, web, tunere legate

	def _leagaStandby(self):
		if self._standby_legat:
			return
		try:
			from Components.config import config
			config.misc.standbyCounter.addNotifier(self._laStandby, initial_call=False)
			self._standby_legat = True
		except Exception:
			pass

	def _laStandby(self, element=None):
		if self.tuner is not None or self.stare == "pregatire":
			T.jurnal("standby: opresc motorul si dau tunerul inapoi")
			self.elibereaza(None, la_standby=True)

	def _pornestePaza(self):
		if self._t_paza is None:
			self._t_paza = T.cronometru(lambda: self._sigur(self._paza))
		self._t_paza.start(1000, True)

	def _paza(self):
		if self.tuner is None:
			return
		acum = T.acum()
		m = self.miscare
		if m is not None and m.get("stapan") == "web" and m.get("tip") == "continuu" and acum - self._web_mentine > WEB_MENTINE_S:
			self._opreste(ce="oprire, pagina nu mai raspunde")
			self._mesaj_dupa_oprire = _("Mișcarea s-a oprit: pagina nu a mai răspuns.")
		elif self.stapan == "web" and not self.seMisca() and not self.ocupat() and acum - self._web_ultima > WEB_LIBER_S:
			self.elibereaza("web")
			return
		secunde = T.secundePanaLaInregistrare()
		if (secunde is not None and secunde <= INREGISTRARE_REFUZ_S) or T.inregistrarePeAntena(self.slot):
			if self.stare != "eliberare":
				self.elibereaza(None, mesaj=_("Pornește o înregistrare. Motorul s-a oprit și programul a revenit."))
			return
		self._t_paza.start(1000, True)

	def _opresteDupaLuare(self):
		if self._t_paza is not None:
			self._t_paza.stop()
		self._dezleagaMasca()

	def _leagaMasca(self):
		try:
			from enigma import eDVBResourceManager
			semnal = eDVBResourceManager.getInstance().frontendUseMaskChanged
			semnal.get().append(self._laMasca)
			self._masca_legata = semnal
		except Exception:
			self._masca_legata = None

	def _dezleagaMasca(self):
		if self._masca_legata is not None:
			try:
				self._masca_legata.get().remove(self._laMasca)
			except Exception:
				pass
		self._masca_legata = None

	def _laMasca(self, masca):
		"""un tuner legat de antena a inceput sa lucreze (o inregistrare, un zap pe el): motorul se opreste"""
		try:
			if self.tuner is None:
				return
			for legat in T.tunereLegate(self.slot):
				if masca & (1 << legat):
					self.elibereaza(None, mesaj=_("Un alt tuner legat de antenă a început să lucreze. Motorul s-a oprit."))
					return
		except Exception as e:
			T.jurnal("masca tunerelor: %r" % (e,))

	# ------------------------------------------------------------------ coordonatorul comun (HdsDab, HdsT2mi)

	def cedeaza(self, motiv=""):
		"""Chemata SINCRON prin LuareTuner.cedeaza cand coordonatorul HdsComun da tunerul altei extensii (revizia
		m5g.2, coordonator.py:34-42): oprirea si limitele se trimit acum, o data, fara eTimer, pe frontendul tinut de
		noi, apoi tunerul se da (programul nu se pune: porneste ce vrea extensia care a cerut)."""
		if self.tuner is None or self.tuner.frontend is None:
			return
		T.jurnal("tunerul e cerut de altcineva (%s); opresc motorul" % motiv)
		self._opresteCronometre()
		try:
			self._tonOprit()
			if self.seMisca() or self.stare in ("trimite", "oprire"):
				self._trimiteOcteti(DishMath.halt(), "oprire la cedarea tunerului")
				self._trimiteOcteti(DishMath.halt(), "oprire la cedarea tunerului")
				try:
					T.controlSec().setRotorMoving(self.slot, False)
				except Exception:
					pass
				self._uitaPozitia()
			if self.limite == "oprite" and self._trimiteOcteti(DishMath.limitsOn(), "limite pornite la cedarea tunerului") == 0:
				self.limite = "pornite"
				_stergeSemn(FISIER_LIMITE_OPRITE)
				noteazaLimite(self.slot, "limite_pornite", "cedare")
		except Exception as e:
			T.jurnal("oprirea la cedare: %r" % (e,))
		if self.miscare is not None:
			self.ultima_miscare = dict(self.miscare, oprit_la=T.acum(), oprita_de_noi=True)
		self.miscare = None
		# Programul oprit de noi nu se mai arunca. Cine a cerut tunerul nu l-a oprit el (l-a gasit
		# oprit), deci nici nu il pune la loc: Gasire semnal din web, de exemplu, nu porneste nimic la sfarsit. Il tinem
		# aici si il pornim cand tunerul se elibereaza, numai daca atunci nu merge nimic: programul unei extensii (DAB+,
		# T2-MI) sau un zap facut intre timp raman (_programulDatorat).
		datorat = None
		try:
			datorat = self.tuner.luare.uita_canalul()
		except Exception as e:
			T.jurnal("programul oprit la cedare: %r" % (e,))
		self._elibereazaTot(pune_programul=False)
		if datorat is not None:
			self._program_datorat = datorat
			self._pornestePazaDatorat()
			self._spune(_("Tunerul a fost cerut de altă funcție a receptorului. Motorul s-a oprit, iar programul revine când tunerul se eliberează."))
		else:
			self._spune(_("Tunerul a fost cerut de altă funcție a receptorului. Motorul s-a oprit."))

	# ------------------------------------------------------------------ programul oprit la o cedare (G3)

	def _pornestePazaDatorat(self):
		if self._t_datorat is None:
			self._t_datorat = T.cronometru(self._pazaDatorat)
		self._t_datorat.start(1000, True)

	def _pazaDatorat(self):
		"""o data pe secunda cat exista un program datorat; se opreste singura cand datoria s-a stins"""
		try:
			gata = self._programulDatorat()
		except Exception as e:
			# programul curent nu se poate citi: partea sigura e sa nu pornim nimic peste
			T.jurnal("programul oprit la cedare: %r" % (e,))
			self._program_datorat = None
			gata = True
		if gata:
			if self._t_datorat is not None:
				self._t_datorat.stop()
		else:
			self._pornestePazaDatorat()

	def _programulDatorat(self):
		"""Programul oprit de noi si ramas fara stapan dupa o cedare. Porneste numai „in liniste": tunerul nu mai e tinut
		de nimeni prin coordonator, nu merge niciun program, nu e deschis ecranul Standby si nicio comanda a motorului nu
		asteapta tunerul. Daca intre timp a pornit alt program, alegerea aceea ramane si datoria se sterge; in standby
		programul il primeste ecranul Standby, care il porneste la trezire (Standby.py:71-74). True = datoria s-a stins."""
		ref = self._program_datorat
		if ref is None:
			return True
		if self.tuner is not None or self.stare == "pregatire":
			return False
		if T.programCurent() is not None:
			self._program_datorat = None
			T.jurnal("programul oprit la cedare ramane oprit: intre timp a pornit alt program")
			return True
		standby = T.ecranStandby()
		if standby is not None:
			self._program_datorat = None
			if getattr(standby, "prev_running_service", None) is None:
				standby.prev_running_service = ref
				T.jurnal("programul oprit la cedare e dat ecranului Standby")
			return True
		if T.tunerLaAltcineva():
			return False
		self._program_datorat = None
		T.jurnal("tunerul s-a eliberat; programul oprit la cedare porneste din nou")
		T.pornesteProgramul(ref)
		return True

	def _predaProgramulDatorat(self):
		"""o comanda noua ia tunerul inainte sa porneasca programul datorat: il preia luarea noua (TunerMotor.
		tineMinteProgramul) si il pune la loc la iesire, ca pe orice program oprit de ea; daca intre timp a pornit alt
		program, ramane acela"""
		ref, self._program_datorat = self._program_datorat, None
		if self._t_datorat is not None:
			self._t_datorat.stop()
		if ref is None:
			return
		try:
			if T.programCurent() is None:
				self.tuner.tineMinteProgramul(ref)
		except Exception as e:
			T.jurnal("programul oprit la cedare: %r" % (e,))

	# ------------------------------------------------------------------ semnalul

	def semnal(self):
		"""semnalul pe transponderul de referinta, citit cel mult o data pe secunda si numai cu tunerul liber de
		secventa nucleului (altfel citirea ar minti)"""
		if self.tuner is None or self.stare != "gata" or self._nucleulLucreaza():
			return None
		acum = T.acum()
		if self._semnal is None or acum - self._semnal_la >= 1.0:
			self._semnal = self.tuner.semnal()
			self._semnal_la = acum
		return self._semnal

	# ------------------------------------------------------------------ starea, pentru ecran, web si HdsMotorStare

	def stareDict(self):
		acum = T.acum()
		m = self.miscare
		slot = self.slot if self.slot is not None else self._slotAles()
		d = {
			"stare": self.stare,
			"slot": slot if slot is not None else -1,
			"tuner": T.numeTuner(slot) if slot is not None else "",
			"stapan": self.stapan or "",
			"limite": self.limite,
			"pas": self.pasCurent(),
			"pozitie_stiuta": self.pozitie_stiuta if self.pozitie_stiuta is not None else -1,
			"eroare": bool(self.eroare),
			"motiv": self.mesaj,
			"motiv_de_acum_s": round(acum - self.mesaj_la, 1) if self.mesaj else None,
			"lacat_proba": T.lacatProba(),
			"tuner_luat": self.tuner is not None and self.tuner.frontend is not None,
			"manual": bool(m is not None and m["tip"] != "satelit" and self.stare in ("misca_manual", "trimite", "oprire")),
			"actiune": m["tip"] if m is not None else "",
			"directie": "",
			"comanda": "",
			"octeti": "",
			"pozitie": m.get("pozitie") if m is not None else None,
			"oprire_automata_s": None,
			"ultima_manuala_ms": -1,
			"ultima_oprire_ms": -1,
			"ultima_actiune": "",
			"referinta": transponderText(self.referinta) if self.referinta else "",
			"referinta_satelit": satelitText(self.referinta["orbital_position"]) if self.referinta else "",
			"semnal": None,
		}
		info = limiteInfo(slot, self.limite)
		d["limite_stare"] = info["stare"]
		d["limite_texte"] = limiteTexte(info)
		if m is not None:
			if m.get("est") is not None:
				d["directie"] = "est" if m["est"] else "vest"
			if m.get("octeti"):
				d["octeti"] = " ".join("%02X" % b for b in m["octeti"])
				d["comanda"] = "%02X" % m["octeti"][2]
			d["oprire_automata_s"] = max(0, int(round(m["plafon_s"] - (acum - m["pornit"]))))
		u = self.ultima_miscare
		if m is None and u is not None and u.get("tip") != "satelit" and u.get("oprit_la") is not None:
			d["ultima_manuala_ms"] = int((acum - u["oprit_la"]) * 1000)
		if m is None and u is not None and u.get("oprita_de_noi") and u.get("oprit_la") is not None:
			# orice miscare oprita de noi, si „Mergi la satelit" oprit pe drum: antena nu a ajuns
			# nicaieri stiut, iar „a ajuns" al nucleului (setRotorMoving(false) pus de acordul de referinta,
			# frontend.cpp:2471-2472) nu are voie sa ajunga pe ecran
			d["ultima_oprire_ms"] = int((acum - u["oprit_la"]) * 1000)
			d["ultima_actiune"] = u.get("tip") or ""
		semnal = self.semnal()
		if semnal is not None:
			d["semnal"] = dict(semnal)
		return d


def stareComenzi():
	"""starea comenzilor ca dictionar simplu (fara obiecte enigma); nu arunca niciodata. Fara obiectul unic (nimeni
	nu a dat inca vreo comanda) intoarce starea de repaus, fara sa creeze nimic."""
	gol = {"stare": "liber", "slot": -1, "tuner": "", "stapan": "", "limite": "necunoscut", "pas": PASI[0],
		"pozitie_stiuta": -1, "eroare": False, "motiv": "", "motiv_de_acum_s": None, "lacat_proba": False,
		"tuner_luat": False, "manual": False, "actiune": "", "directie": "", "comanda": "", "octeti": "", "pozitie": None,
		"oprire_automata_s": None, "ultima_manuala_ms": -1, "ultima_oprire_ms": -1, "ultima_actiune": "", "referinta": "",
		"referinta_satelit": "", "semnal": None}
	try:
		if _unic is None:
			info = limiteInfo(None, "necunoscut")
			gol["limite_stare"] = info["stare"]
			gol["limite_texte"] = limiteTexte(info)
			return gol
		return _unic.stareDict()
	except Exception as e:
		T.jurnal("starea comenzilor: %r" % (e,))
		return gol


def transponderText(tp):
	return T.transponderText(tp)
