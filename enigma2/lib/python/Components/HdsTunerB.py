# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTunerB.py - al doilea tuner de satelit (tunerul B) porneste singur, daca are semnal.
#
# De ce e oprit din fabrica (Components/NimManager.py, primul_satelit): un tuner fara cablu, pornit, ar fi ales pentru
# inregistrari si n-ar prinde nimic. Ca omul cu doua cabluri sa nu ramana cu B oprit fara sa stie, receptorul il
# probeaza singur, in fundal, fara nicio fereastra pe televizor:
#
# Proba 1 (dupa pornire, cand pe tunerul A merge un canal de satelit): B se pune in memorie „la fel ca A” (sau „al
# doilea cablu” cand A are motor; tunerul dependent nu poate misca motorul, lib/dvb/sec.cpp) si incearca, cel mult
# PROBA_S secunde, transponderul canalului de pe A. Canalul de pe A nu se opreste. Nimic nu se scrie in settings.
#
# Proba 2 (receptorul in standby, nefolosit): un singur transponder prins nu dovedeste ca B are cablul lui (un
# splitter pe cablul lui A trece si el proba 1, dar apoi tensiunea si tonul celor doi tuneri se bat). Intai A probeaza
# singur T2, un alt transponder de pe acelasi satelit, pe alta banda si alta polarizare (ca un transponder mort sa nu
# fie pus in seama lui B); apoi A ramane pe T1 si B pe T2 in acelasi timp: daca amandoi tin semnalul, B are cablul
# lui si porneste de tot (scris in settings). Daca nu, B ramane oprit: „configurarea automata n-a reusit”.
#
# Alegerea omului e sfanta: tunerul B salvat de mana (ecranul tunerului, chiar „neconfigurat”), sau o setare veche cu
# modul lui scris in settings, nu se mai probeaza si nu se mai schimba. Starea (config.Nims[B].hdsAuto) se vede in
# Setari tuner (Screens/Satconfig.py) si in pagina web (HdsWebControl/scanare_web.py).
#
# Totul pe eTimer, pe firul enigma2; nicio asteptare. Logica de alegere e in functii fara enigma (se probeaza pe PC).

import time

PROBA_S = 10                  # cat incearca B un transponder
PAS_MS = 250                  # citirea frontendurilor
PRINDERI_LA_RAND = 2          # „prins” = blocat la 2 citiri la rand
TINE_S = 2                    # proba 2: amandoi tin semnalul inca 2 s dupa ce l-au prins
PRIMA_PROBA_S = 90            # dupa pornirea interfetei
REINCERCARE_S = 60            # conditiile nu sunt indeplinite: se verifica din nou
PROBA2_DUPA_STANDBY_S = 60    # dupa intrarea in standby
FARA_INREGISTRARE_S = 300     # nicio proba cu o inregistrare programata mai devreme de atat
CANDIDATI_T2 = 3
BANDA_INALTA_KHZ = 11700000   # LNB universal: peste 11,7 GHz tonul de 22 kHz

# config.Nims[x].hdsAuto
NEPROBAT, JUMATATE, PORNIT, ESUAT = "", "jumatate", "pornit", "esuat"
CHEIE_RAND = "hds_tuner_b"    # randul din Setari tuner (Screens/Satconfig.py)

_proba = None                 # proba care merge acum
_sesiune = None
_ceas = None
_motiv = ""                   # de ce n-a pornit ultima proba ceruta de om (text pentru ecran si web)
_proba1_facuta = False        # proba 1 a pornit singura la pornirea de acum
_proba2_facuta = False        # proba 2 a pornit in standby-ul de acum
_ascultatori = []


def _jurnal(text):
	print("[HdsTunerB] %s" % text)


def _nm():
	from Components.NimManager import nimmanager
	return nimmanager


def _cfg(slot):
	from Components.config import config
	return config.Nims[slot]


def litera(slot):
	return chr(ord("A") + int(slot))


# ---------------------------------------------------------------- reguli (fara enigma)
def _fbc(slot):
	try:
		return bool(slot.isFBCLink())
	except Exception:
		return False


def perechea(nim_slots):
	"""(A, B): primul si al doilea tuner de satelit (sloturile), sau None cu mai putin de doi. Tunerii in plus nu se
	probeaza: legaturile interne FBC nu sunt cabluri."""
	sat = [s.slot for s in nim_slots if s.isCompatible("DVB-S") and not _fbc(s)]
	return (sat[0], sat[1]) if len(sat) >= 2 else None


def ales_de_om(cfg):
	"""True daca omul a ales ceva pentru tuner: salvat din ecranul lui (hdsAlesDeOm), sau modul scris in settings de
	o versiune veche sau de o copie, fara sa-l fi pornit proba (un receptor deja folosit, cu B neatins, nu are modul
	lui B scris: implicitul „nothing” nu se scrie)."""
	if "hdsAlesDeOm" in cfg.content.items and cfg.hdsAlesDeOm.value:
		return True
	stare = cfg.hdsAuto.value if "hdsAuto" in cfg.content.items else NEPROBAT
	if stare == PORNIT:
		return False
	return "configMode" in cfg.content.stored_values


def are_motor(cfg_a):
	"""A are motor: modul simplu cu pozitioner, sau avansat cu un LNB pe USALS / pozitii (3601-3604)."""
	mod = cfg_a.configMode.value
	if mod == "simple":
		return cfg_a.diseqcMode.value == "positioner"
	if mod == "advanced":
		try:
			for x in range(3601, 3605):
				if int(cfg_a.advanced.sat[x].lnb.value) != 0:
					return True
		except Exception:
			pass
	return False


def mod_pentru_b(cfg_a):
	"""Modul lui B cand porneste: „al doilea cablu” daca A are motor, altfel „la fel ca A”. None daca A nu e
	configurat de sine statator (simplu sau avansat)."""
	if cfg_a.configMode.value not in ("simple", "advanced"):
		return None
	return "satposdepends" if are_motor(cfg_a) else "equal"


def banda(tp):
	return 1 if tp["frequency"] >= BANDA_INALTA_KHZ else 0


def alege_t2(lista, t1, maxim=CANDIDATI_T2):
	"""Transponderele pentru proba 2, din lista satelitului lui T1 (dicturile „tp” din HdsGasireSemnal.transpondere):
	intai cele pe alta banda SI alta polarizare, apoi pe alta polarizare, apoi pe alta banda; niciodata T1. In fiecare
	grupa, cele mai apropiate de mijlocul benzii lor raman la rand dupa ordinea din lista."""
	grupe = ([], [], [])
	for tp in lista:
		if tp.get("orbital_position") != t1.get("orbital_position"):
			continue
		alta_pol = tp["polarisation"] != t1["polarisation"]
		alta_banda = banda(tp) != banda(t1)
		if alta_pol and alta_banda:
			grupe[0].append(tp)
		elif alta_pol:
			grupe[1].append(tp)
		elif alta_banda:
			grupe[2].append(tp)
	return (grupe[0] + grupe[1] + grupe[2])[:maxim]


def motiv_fara_proba(inregistrari, transmisii, pip, inregistrare_curand, ecran_tuner):
	"""Textul pentru om de ce proba nu poate porni acum, sau "" daca poate."""
	if inregistrari or inregistrare_curand:
		return _("Se înregistrează sau urmează o înregistrare. Proba se face după aceea.")
	if transmisii:
		return _("Un canal se trimite acum în rețea. Proba se face după aceea.")
	if pip:
		return _("Închide imaginea în imagine, apoi încearcă din nou.")
	if ecran_tuner:
		return _("Ecranul tunerului e deschis.")
	return ""


def text_stare(stare, slot_b, slot_a, motiv="", acum=False, web=False):
	"""(textul randului, ce face OK: "proba" | "manual"). Aceleasi texte pe televizor si in web; in web fara „OK: ...”
	(acolo e butonul)."""
	b, a = litera(slot_b), litera(slot_a)
	if acum:
		return _("Tuner %s: se probează...") % b, None
	if stare == PORNIT:
		return _("Tuner %s: pornit singur: a găsit semnal") % b, "manual"
	if stare == JUMATATE:
		# scurt, fara sa ceara ceva omului
		return _("Tuner %s: verificare automată în așteptare") % b, "manual"
	if stare == ESUAT:
		text = _("Tuner %s: configurarea automată n-a reușit.") % b
		if not web:
			text += " " + _("OK: încearcă din nou")
	else:
		text = _("Tuner %s: se probează singur când merge un canal pe tunerul %s.") % (b, a)
		if not web:
			text += " " + _("OK: încearcă acum")
	if motiv:
		# pe televizor (NimSelection, doua randuri cu RT_WRAP) motivul continua paragraful: pe rand nou iesea pe al
		# treilea rand, taiat, in limbile cu textul de baza mai lung de un rand (masurat: masoara_tuner_b_070.py)
		text += ("\n" if web else " ") + motiv
	return text, "proba"


# ---------------------------------------------------------------- starea pe receptor
def tunerul_b():
	"""(A, B): primul si al doilea tuner de satelit ale receptorului, sau None."""
	try:
		return perechea(_nm().nim_slots)
	except Exception:
		return None


def stare():
	"""Pentru ecran si web: None (receptor cu un tuner de satelit, sau B ales de om si nepornit de proba), altfel
	{"slot", "litera", "stare", "text", "ok"}."""
	pereche = tunerul_b()
	if pereche is None:
		return None
	a, b = pereche
	try:
		cfg = _cfg(b)
	except Exception:
		return None
	st = cfg.hdsAuto.value if "hdsAuto" in cfg.content.items else NEPROBAT
	if ales_de_om(cfg):
		return None
	if st != PORNIT and mod_pentru_b(_cfg(a)) is None:
		return None                  # A nu e configurat: nimic de probat
	acum = _proba is not None    # in timpul probei modul lui B e pus in memorie la fel ca A
	if not acum and st != PORNIT and cfg.configMode.value != "nothing":
		return None
	text, ok = text_stare(st, b, a, _motiv, acum)
	text_web = text_stare(st, b, a, _motiv, acum, web=True)[0]
	return {"slot": b, "litera": litera(b), "stare": st, "text": text, "text_web": text_web, "ok": ok,
		"acum": acum}


def _scrie(cfg, stare_noua):
	cfg.hdsAuto.value = stare_noua
	cfg.hdsAuto.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		_jurnal("settings: %r" % (e,))


def asculta(functie):
	if functie not in _ascultatori:
		_ascultatori.append(functie)


def nu_mai_asculta(functie):
	if functie in _ascultatori:
		_ascultatori.remove(functie)


def _anunta():
	for f in list(_ascultatori):
		try:
			f()
		except Exception as e:
			_jurnal("ascultator: %r" % (e,))


def ales_acum_de_om(slot):
	"""Din ecranul tunerului (Satconfig.NimSetup.keySave) si din web: omul a salvat ceva pentru tuner. De acum proba nu
	mai atinge tunerul."""
	opreste_proba()
	try:
		cfg = _cfg(slot)
		if "hdsAlesDeOm" in cfg.content.items and not cfg.hdsAlesDeOm.value:
			cfg.hdsAlesDeOm.value = True
			cfg.hdsAlesDeOm.save()
	except Exception as e:
		_jurnal("ales de om: %r" % (e,))


# ---------------------------------------------------------------- legaturile cu enigma2
def _nav():
	import NavigationInstance
	return NavigationInstance.instance


def _ecran_standby():
	import sys
	modul = sys.modules.get("Screens.Standby")
	return getattr(modul, "inStandby", None) if modul is not None else None


def _ecran_tuner_deschis():
	s = _sesiune
	try:
		dialog = s.current_dialog if s is not None else None
	except Exception:
		dialog = None
	return dialog is not None and dialog.__class__.__name__ == "NimSetup"


def _motiv_acum():
	from Components import HdsGasireSemnal as G
	inceput = G.urmatoarea_inregistrare()
	curand = inceput is not None and inceput - time.time() < FARA_INREGISTRARE_S
	try:
		inregistrari = bool(_nav().getRecordings())
	except Exception:
		inregistrari = False
	transmisii = bool(G._adrese_transmisie())
	pip = bool(getattr(_sesiune, "pipshown", False))
	return motiv_fara_proba(inregistrari, transmisii, pip, curand, _ecran_tuner_deschis())


def _t1_de_pe_a(a):
	"""Transponderul canalului de pe A, daca A il tine prins acum, sau None."""
	from Components import HdsGasireSemnal as G
	serviciu = _nav().getCurrentService()
	if serviciu is None:
		return None
	info = serviciu.frontendInfo()
	date = info.getFrontendData() if info is not None else None
	if not date or date.get("tuner_number") != a:
		return None
	st = info.getFrontendStatus() if hasattr(info, "getFrontendStatus") else None
	if st is not None and not st.get("tuner_locked", 1):
		return None
	pozitii = [int(x[0]) for x in _nm().getSatListForNim(a)]
	return G.transponder_din_serviciu(serviciu, pozitii)


class Proba(object):
	"""O proba (faza 1 sau 2). Pune B temporar in modul lui A, ia canale brute, acordeaza, citeste, si la sfarsit pune
	totul la loc (sau scrie B pornit). la_sfarsit(rezultat): "prins" | "neprins" | "cedat"."""

	def __init__(self, faza, a, b, mod, t1, candidati, la_sfarsit):
		self.faza, self.a, self.b, self.mod = faza, a, b, mod
		self.t1, self.candidati = t1, list(candidati)
		self.la_sfarsit = la_sfarsit
		self.canale = {}
		self.pas = ""
		self.termen = 0.0
		self.prinderi = {}
		self.tine_pana = None
		self.vechi = None
		self.ceas = None
		self.standby = None

	# ---- pornire
	def porneste(self):
		from enigma import eTimer
		cfg = _cfg(self.b)
		self.vechi = (cfg.configMode.value, cfg.connectedTo.value)
		cfg.connectedTo.value = str(self.a)
		cfg.configMode.value = self.mod
		_nm().sec.update()
		self.ceas = eTimer()
		self.ceas.callback.append(self._pas)
		if self.faza == 1:
			if not self._acord(self.b, self.t1):
				return self._termina("cedat")
			self._incepe_pas("b_t1", (self.b,))
		else:
			ecran = _ecran_standby()
			if ecran is None:
				return self._termina("cedat")
			# trezirea: canalele brute se lasa INAINTEA pornirii canalului (Standby.__onClose)
			ecran.onClose.insert(0, self._trezire)
			self.standby = ecran
			self._urmatorul_t2()
		return None

	def _acord(self, slot, tp):
		from enigma import eDVBResourceManager
		from Components import HdsGasireSemnal as G
		canal = self.canale.get(slot)
		if canal is None:
			canal = eDVBResourceManager.getInstance().allocateRawChannel(slot)
			if canal is None:
				_jurnal("tunerul %s nu e liber" % litera(slot))
				return False
			self.canale[slot] = canal
		fe = canal.getFrontend()
		if fe is None:
			return False
		if slot == self.a and self.mod == "satposdepends":
			# proba 2 acordeaza A pe pozitia pe care antena e deja; urma motorului afla totusi cine a cerut acordul
			G.anunta_motorul("tuner B: proba automata")
		cod = G.acordeaza(fe, tp)
		if cod != 0:
			_jurnal("acord refuzat pe %s: %s" % (litera(slot), cod))
			return False
		return True

	def _incepe_pas(self, pas, sloturi):
		self.pas = pas
		self.prinderi = dict((s, 0) for s in sloturi)
		self.tine_pana = None
		self.termen = time.monotonic() + PROBA_S
		self.ceas.start(PAS_MS, False)

	def _urmatorul_t2(self):
		if not self.candidati:
			return self._termina("nehotarat")
		self.t2 = self.candidati.pop(0)
		if not self._acord(self.a, self.t2):
			return self._termina("cedat")
		self._incepe_pas("a_t2", (self.a,))

	# ---- citire
	def _blocat(self, slot):
		canal = self.canale.get(slot)
		fe = canal.getFrontend() if canal is not None else None
		if fe is None:
			return False
		d = {}
		fe.getFrontendStatus(d)
		return bool(d.get("tuner_locked")) and d.get("tuner_state") != "TUNING"

	def _pas(self):
		if _motiv_acum():
			return self._termina("cedat")
		if self.faza == 2 and _ecran_standby() is None:
			return self._termina("cedat")
		acum = time.monotonic()
		toti = True
		for s in self.prinderi:
			if self._blocat(s):
				self.prinderi[s] += 1
			else:
				self.prinderi[s] = 0
				if self.pas == "ambii" and self.tine_pana is not None:
					return self._termina("neprins")      # cineva a pierdut semnalul: cablul e impartit
			if self.prinderi[s] < PRINDERI_LA_RAND:
				toti = False
		if toti:
			if self.pas == "b_t1":
				return self._termina("prins")
			if self.pas == "a_t2":
				# T2 merge pe A: acum A pe T1 si B pe T2, in acelasi timp
				if not (self._acord(self.a, self.t1) and self._acord(self.b, self.t2)):
					return self._termina("cedat")
				return self._incepe_pas("ambii", (self.a, self.b))
			if self.tine_pana is None:
				self.tine_pana = acum + TINE_S
			elif acum >= self.tine_pana:
				return self._termina("prins")
			return None
		if acum >= self.termen:
			if self.pas == "a_t2":
				return self._urmatorul_t2()          # transponderul nu merge nici pe A: urmatorul
			return self._termina("neprins")
		return None

	# ---- sfarsit
	def _trezire(self):
		self._termina("cedat")

	def opreste(self):
		self._termina("cedat")

	def _termina(self, rezultat):
		if self.ceas is not None:
			self.ceas.stop()
		if self.standby is not None:
			try:
				self.standby.onClose.remove(self._trezire)
			except ValueError:
				pass
			self.standby = None
		# canalele brute se lasa: frontendul se inchide singur dupa 3 s daca nu-l ia nimeni (lib/dvb/dvb.h)
		self.canale = {}
		cfg = _cfg(self.b)
		pornit = rezultat == "prins" and self.faza == 2
		if pornit:
			cfg.configMode.save()
			cfg.connectedTo.save()
		elif self.vechi is not None:
			cfg.configMode.value, cfg.connectedTo.value = self.vechi[0], self.vechi[1]
			try:
				_nm().sec.update()
			except Exception as e:
				_jurnal("sec: %r" % (e,))
		self.vechi = None
		la_sfarsit, self.la_sfarsit = self.la_sfarsit, None
		if la_sfarsit is not None:
			la_sfarsit(rezultat)
		return None


# ---------------------------------------------------------------- pornirea probelor
def _poate():
	"""(A, B, cfg_b, mod) daca B se poate proba acum, altfel None (fara text)."""
	pereche = tunerul_b()
	if pereche is None:
		return None
	a, b = pereche
	cfg_b = _cfg(b)
	if ales_de_om(cfg_b) or cfg_b.configMode.value != "nothing":
		return None
	if cfg_b.hdsAuto.value == PORNIT:
		return None
	mod = mod_pentru_b(_cfg(a))
	if mod is None:
		return None
	return a, b, cfg_b, mod


def incearca_proba1(de_om=False):
	"""Proba 1 acum, daca se poate. Intoarce textul motivului daca nu (gol daca a pornit sau nu e de facut)."""
	global _proba, _motiv
	if _proba is not None:
		return ""
	p = _poate()
	if p is None:
		return ""
	a, b, cfg_b, mod = p
	if cfg_b.hdsAuto.value == JUMATATE and not de_om:
		return ""
	if _ecran_standby() is not None:
		return _("Receptorul e în standby.")
	motiv = _motiv_acum()
	if not motiv:
		try:
			t1 = _t1_de_pe_a(a)
		except Exception as e:
			_jurnal("canalul de pe A: %r" % (e,))
			t1 = None
		if t1 is None:
			motiv = _("Pornește un canal de satelit pe tunerul %s, apoi încearcă din nou.") % litera(a)
	if motiv:
		if de_om:
			_motiv = motiv
			_anunta()
		return motiv
	_motiv = ""

	def gata(rezultat):
		global _proba
		_proba = None
		_jurnal("proba 1 pe %s: %s" % (litera(b), rezultat))
		if rezultat == "prins":
			cfg_b.hdsTpProba.value = _tp_text(t1)
			cfg_b.hdsTpProba.save()
			_scrie(cfg_b, JUMATATE)
		elif rezultat == "neprins":
			_scrie(cfg_b, ESUAT)
		_anunta()

	_proba = Proba(1, a, b, mod, t1, (), gata)
	_anunta()
	try:
		_proba.porneste()
	except Exception as e:
		_jurnal("proba 1: %r" % (e,))
		if _proba is not None:
			_proba._termina("cedat")
	return ""


def _tp_text(tp):
	from Components import HdsGasireSemnal as G
	return ",".join(str(int(tp[k])) for k in G.CAMPURI_NUCLEU)


def _tp_din_text(text):
	from Components import HdsGasireSemnal as G
	try:
		valori = [int(x) for x in (text or "").split(",")]
	except ValueError:
		return None
	if len(valori) != len(G.CAMPURI_NUCLEU):
		return None
	return dict(zip(G.CAMPURI_NUCLEU, valori))


def incearca_proba2():
	"""Proba 2, in standby. False numai daca trebuie incercata din nou mai tarziu (inregistrare, transmisie)."""
	global _proba
	if _proba is not None or _ecran_standby() is None:
		return True
	p = _poate()
	if p is None:
		return True
	a, b, cfg_b, mod = p
	if cfg_b.hdsAuto.value != JUMATATE:
		return True
	if _motiv_acum():
		return False
	t1 = _tp_din_text(cfg_b.hdsTpProba.value)
	if t1 is None:
		_scrie(cfg_b, NEPROBAT)
		return True
	from Components import HdsGasireSemnal as G
	lista, _sarite = G.transpondere(t1["orbital_position"], _nm().getNimListOfType("DVB-S2").count(b) > 0)
	candidati = alege_t2([x["tp"] for x in lista], t1)
	if not candidati:
		_jurnal("proba 2: niciun alt transponder pe alta banda sau polarizare; B ramane cum e")
		return True

	def gata(rezultat):
		global _proba
		_proba = None
		_jurnal("proba 2 pe %s: %s" % (litera(b), rezultat))
		if rezultat == "prins":
			_scrie(cfg_b, PORNIT)
		elif rezultat == "neprins":
			_scrie(cfg_b, ESUAT)
		_anunta()

	_proba = Proba(2, a, b, mod, t1, candidati, gata)
	try:
		_proba.porneste()
	except Exception as e:
		_jurnal("proba 2: %r" % (e,))
		if _proba is not None:
			_proba._termina("cedat")
	return True


def opreste_proba():
	if _proba is not None:
		_proba.opreste()


def ok_din_ecran(session, inapoi):
	"""OK pe randul din Setari tuner: proba din nou sau ecranul tunerului B (configurarea de mana)."""
	st = stare()
	if st is None:
		return
	if st["ok"] == "proba":
		incearca_proba1(de_om=True)
		inapoi()
		return
	from Screens.Satconfig import NimSetup
	session.openWithCallback(inapoi, NimSetup, st["slot"])


def _bataie():
	"""Ceasul de fundal: proba 1 o data pe pornire (cand se poate), proba 2 o data pe standby. Pana atunci, din minut
	in minut (receptor pornit direct in standby, niciun canal pe A, o inregistrare)."""
	global _proba1_facuta, _proba2_facuta
	p = _poate()
	if p is None:
		return
	if p[2].hdsAuto.value == JUMATATE:
		_proba1_facuta = True        # asteapta proba 2, in standby
	if _ecran_standby() is not None:
		if not _proba2_facuta:
			_proba2_facuta = incearca_proba2()
	elif not _proba1_facuta:
		incearca_proba1()
		_proba1_facuta = _proba is not None
	asteapta = not _proba1_facuta or (_ecran_standby() is not None and not _proba2_facuta)
	if asteapta and _ceas is not None and _poate() is not None:
		_ceas.start(REINCERCARE_S * 1000, True)


def _la_standby(element):
	global _proba2_facuta
	_proba2_facuta = False
	if _ceas is not None and _poate() is not None:
		_ceas.start(PROBA2_DUPA_STANDBY_S * 1000, True)


def porneste(session):
	"""Din mytest.py: prima proba la PRIMA_PROBA_S dupa pornire; proba 2 la intrarea in standby. Fara al doilea
	tuner de satelit, sau cu B ales de om, nu face nimic."""
	global _sesiune, _ceas
	_sesiune = session
	if _poate() is None:
		return
	from enigma import eTimer
	from Components.config import config
	_ceas = eTimer()
	_ceas.callback.append(_bataie)
	_ceas.start(PRIMA_PROBA_S * 1000, True)
	config.misc.standbyCounter.addNotifier(_la_standby, initial_call=False)
