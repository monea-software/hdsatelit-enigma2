# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Satfinder.py - ecranul „Găsire semnal” (MENU > Orientarea și setarea antenei > Găsire semnal).
#
# Ecranul e subțire: lista de câmpuri, tastele și afișarea. Tot ce ține de tuner (luarea lui, oprirea și punerea la
# loc a canalului, acordul DVB-S / DVB-S2, așteptarea motorului, citirea semnalului, verdictul, textele) e în
# Components/HdsGasireSemnal.py, pe care îl folosește și pagina web. Clasa și skinName rămân „Satfinder”, deci
# data/menu.xml și skinul nu se schimbă.
#
# Pornire: se deschide măsurând transponderul canalului de pe ecran (citit înainte de orice oprire), deci „Semnal
# prins” apare din prima dacă antena e în regulă. Canalul se oprește numai dacă ține tunerul și pornește la loc la
# ieșire. Butonul verde duce transponderul în scanerul de satelit (Screens/ScanerSatelit.py, felul „manual”).
# Motorul nu se comandă de aici: comenzile stau în „Rotirea antenei” (un singur drum spre un loc). Cât e deschis
# ecranul, panoul automat al motorului stă ascuns, ca să nu acopere lista, barele și întrebările.
#
# GST7: si tunerele terestre (DVB-T/T2) si de cablu (DVB-C). Pe ele, in locul randurilor Satelit si Transponder sta
# un singur rand, „Frecvența”, cu lista regiunii sau a furnizorului din Setari tuner (HdsGasireSemnal.frecvente_tc)
# si „Introdus de mână”; verdele duce frecventa in scanerul terestru sau de cablu, felul „manual”. Un receptor numai
# cu tunere de satelit vede ecranul ca pana acum.
#
# Ecranul spune modulului cine="ecran" la fiecare cerere; orice alt apelant (pagina web) primește refuz cât e
# deschis ecranul (Masurare, în Components/HdsGasireSemnal.py).
#
# GSW2 (Eduard 27.11.2026): pe transponderul programului de acum măsurarea citește tunerul programului și nu îl
# oprește (modul A, în modul); primul rând, „Transponderul canalului de acum”, alege cu OK satelitul și transponderul
# programului și pornește măsurarea; fără program de satelit (IPTV) ecranul pornește pe satelitul pe care stă antena
# (HdsGasireSemnal.pozitie_implicita), nu pe primul din listă; un satelit în afara cursei motorului, prea jos sau sub
# orizont se acordează numai după „Da” (HdsGasireSemnal.text_departe).

from Screens.Screen import Screen
from Components.ConfigList import ConfigListScreen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from Components.Sources.Source import Source
from Components.config import ConfigSelection, ConfigNumber, getConfigListEntry
from Components import HdsGasireSemnal
from enigma import eTimer

MANUAL = "manual"
PRAG_ALEGERE = 6              # listele mai lungi se aleg dintr-o fereastră (OK), ca în scaner
INTARZIERE_ACORD_MS = 400     # apăsările repetate pe stânga/dreapta nu fac zece acorduri


class SursaSemnal(Source):
	"""Sursa barelor din skin: convertorul FrontendInfo citește snr, snr_db, agc, ber, lock, frontend_type,
	slot_number. Se umple din starea măsurării, fără a doua citire a frontendului. Fiecare ecran își face
	instanța lui: la închidere enigma2 cheamă destroy(), iar Source.destroy() golește obiectul."""

	def __init__(self):
		Source.__init__(self)
		self.snr = self.snr_db = self.agc = self.ber = self.lock = None
		self.frontend_type = "DVB-S"
		self.slot_number = None

	def pune(self, stare):
		self.snr = stare.get("calitate_bruta")
		self.agc = stare.get("nivel_brut")
		self.ber = stare.get("ber")
		self.lock = bool(stare.get("blocat"))
		self.snr_db = None
		# GST7: la terestru si cablu, felul tunerului si calitatea in dB cand tunerul o da (sutimi, ca FrontendInfo)
		self.frontend_type = {"T": "DVB-T", "C": "DVB-C"}.get(stare.get("fel"), "DVB-S")
		if stare.get("calitate_db_tc") is not None:
			self.snr_db = int(round(stare["calitate_db_tc"] * 100))
		self.slot_number = stare.get("slot")
		self.changed((self.CHANGED_ALL,))


def _panouMotor(ascuns):
	"""Panoul automat al motorului (Screens/HdsDishMotor.py, pus peste program de InfoBar) ar ieși peste listă, peste
	bare și peste întrebarea de la ieșire cât se rotește antena. Cât e deschis ecranul îl cerem ascuns prin
	Components/HdsMotorStare.py (panou_automat_oprit), pe care panoul îl citește la fiecare bătaie; cererea e a
	noastră („gasire_semnal”), deci nu o atinge pe a ecranului „Rotirea antenei”. Importul e păzit: cu un
	HdsMotorStare fără funcție, ecranul merge mai departe, doar cu panoul peste el."""
	try:
		from Components.HdsMotorStare import panou_automat_oprit
	except ImportError:
		return
	panou_automat_oprit("gasire_semnal", ascuns)


class Satfinder(ConfigListScreen, Screen):
	skinName = ["Satfinder"]

	def __init__(self, session):
		Screen.__init__(self, session)
		self.masurare = HdsGasireSemnal.masurare()
		self.tunere = HdsGasireSemnal.tunere()
		self.cTuner = self.cSatelit = self.cTransponder = None
		self.cListaTC = None          # GST7: randul „Frecvența” al unui tuner terestru sau de cablu
		self._frecventeTC = []
		self._transpondere = []
		self._sarite = 0
		self._tpAles = None
		self._numericSchimbat = False
		self._inAlegere = None
		self._afisat = {}
		self._valori = {}
		self._fereastraCanale = None
		self._textCanale = None
		self._program = None          # GSW2: programul de acum (citit la deschidere, înainte de orice oprire)
		self.cProgram = None
		self._confirmatPoz = None     # satelitul departat pentru care s-a spus deja „Da”

		if self.tunere:
			self._creeazaCampurile()
		# „areSateliti”: un tuner pe care se poate masura (de satelit cu sateliti, sau terestru, sau de cablu)
		areSateliti = any(t["sateliti"] or t.get("fel", "S") != "S" for t in self.tunere)

		self["header"] = Label("")
		self["description"] = Label("")
		# Label, nu StaticText: panoul HdsCadru1776 arată textul unui StaticText numai pe ecranele cu ScreenPath.
		# Verde și galben există când măcar un tuner are sateliți; pe un tuner fără sateliți ales din rândul Tuner
		# spun de ce nu fac nimic (_faraSateliti).
		self["key_red"] = Label(_("Închide"))
		if areSateliti:
			self["key_green"] = Label(_("Caută canale"))
			self["key_yellow"] = Label(_("Acordează din nou"))
			# TRL6: canalele de pe transponderul prins (PAT si SDT), fara scanare si fara salvare
			self["key_blue"] = Label(_("Canalele de aici"))
		if areSateliti:
			# fără tuner de satelit setat barele nu apar deloc (conditional="Frontend" în skin), deci nici „N/A”
			self["Frontend"] = SursaSemnal()
		self["postext"] = StaticText(_("Antena:"))
		self["pos"] = StaticText("")
		self["tsidtext"] = StaticText(_("TS ID:"))
		self["tsid"] = StaticText("")
		self["onidtext"] = StaticText(_("ON ID:"))
		self["onid"] = StaticText("")

		# Orice actiune din harti are functie, altfel jurnalul scrie "unknown action" (albastrul: canalele de pe
		# transponder, TRL6; motorul se comanda din "Rotirea antenei").
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.keyOk,
			"cancel": self.keyCancel,
			"red": self.keyCancel,
			"green": self.keyGo,
			"yellow": self.keyYellow,
			"blue": self.keyBlue,
		}, -2)

		self.list = []
		ConfigListScreen.__init__(self, self.list, session=session, on_change=self.changedConfig)
		self._ceasAcord = eTimer()
		self._ceasAcord.callback.append(self._acordeazaCampurile)
		self._construiesteLista()
		self["config"].onSelectionChanged.append(self._randSchimbat)

		self.masurare.ecran_deschis = True
		self.masurare.asculta(self._laStare)
		self.onLayoutFinish.append(self._laAsezare)
		self.onClose.append(self._laInchidere)

	# ---------------------------------------------------------------- câmpurile
	def _creeazaCampurile(self):
		# transponderul canalului de pe ecran, citit acum, înainte ca măsurarea să oprească ceva
		tpInitial, tunerInitial = None, self.tunere[0]
		try:
			self._program = HdsGasireSemnal.program_acum(self.tunere)
		except Exception as e:
			print("[Satfinder] programul de acum: %r" % (e,))
			self._program = None
		for t in self.tunere:
			if self._program is not None and t["slot"] == self._program["slot"]:
				tpInitial, tunerInitial = self._program["tp"], t
				break
		pozInitiala = None
		if tpInitial is not None:
			if HdsGasireSemnal.fel_tp(tpInitial) == HdsGasireSemnal.FEL_SATELIT:
				# antena e deja acolo (programul merge pe el): fără întrebare chiar dacă e departe
				self._confirmatPoz = tpInitial["orbital_position"]
			self.cProgram = ConfigSelection(choices=[("program", HdsGasireSemnal.text_transponder(tpInitial))], default="program")
		else:
			for t in self.tunere:
				if t.get("fel", "S") == "S" and t["sateliti"]:
					tunerInitial, pozInitiala = t, HdsGasireSemnal.pozitie_implicita(t)
					break
		self.cTuner = ConfigSelection(choices=[(str(t["slot"]), t["nume"]) for t in self.tunere],
			default=str(tunerInitial["slot"]))
		self._creeazaManual()
		self._pregatesteTuner(tpInitial, pozInitiala)

	def _tunerCurent(self):
		for t in self.tunere:
			if str(t["slot"]) == self.cTuner.value:
				return t
		return self.tunere[0]

	def _creeazaManual(self):
		def alegeri(lista):
			return [(str(cod), nume) for cod, nume in lista]
		# numerele se scriu ca in setarile imaginii (ConfigNumber): la intrarea pe rand tot numarul e ales, prima cifra
		# tastata incepe un numar nou, fara zerouri in fata (2200 peste 22000: "2200", nu Stanga de 5 ori si "02200");
		# Stanga / Dreapta muta cursorul pentru o singura cifra. Zero si rata pe care tunerul nu o primeste le refuza
		# HdsGasireSemnal.transponder_din_campuri, cu textul lui. Ecranul nu are HelpWindow si VKeyIcon, deci
		# ConfigListScreen.handleInputHelpers nu cauta fereastra literelor (pe care ConfigNumber nu o face).
		self.cFrecventa = ConfigNumber(default=11766)
		self.cRata = ConfigNumber(default=27500)
		self.cPol = ConfigSelection(choices=alegeri(HdsGasireSemnal.polarizari()), default="0")
		self.cSistem = ConfigSelection(choices=alegeri(HdsGasireSemnal.sisteme(True)), default="0")
		self.cFecS = ConfigSelection(choices=alegeri(HdsGasireSemnal.fec_dvbs()), default="0")
		self.cMod = ConfigSelection(choices=alegeri(HdsGasireSemnal.modulatii_dvbs2()), default="2")
		self.cFecS2 = ConfigSelection(choices=alegeri(HdsGasireSemnal.fec_dvbs2()), default="3")
		self.cRolloff = ConfigSelection(choices=alegeri(HdsGasireSemnal.rolloffuri()), default="0")
		self.cPilot = ConfigSelection(choices=alegeri(HdsGasireSemnal.piloti()), default="2")
		# GST7: frecventa terestra sau de cablu scrisa de mana (MHz), latimea si sistemul (PLP automat), rata si QAM
		self.cFrecventaTC = ConfigNumber(default=474)
		self.cLatime = ConfigSelection(choices=alegeri(HdsGasireSemnal.latimi()), default="0")
		self.cSistemT = ConfigSelection(choices=alegeri(HdsGasireSemnal.sisteme_terestre()), default="1")
		self.cRataC = ConfigNumber(default=6900)
		self.cModC = ConfigSelection(choices=alegeri(HdsGasireSemnal.modulatii_cablu()), default="0")

	def _pregatesteTuner(self, tpInitial=None, pozInitiala=None):
		t = self._tunerCurent()
		# DVB-S2 se poate alege numai dacă tunerul îl are
		self.cSistem.setChoices([(str(c), n) for c, n in HdsGasireSemnal.sisteme(t["s2"])], default="0")
		self.cListaTC = None
		if t.get("fel", "S") != "S":
			self.cSatelit = self.cTransponder = None
			self._pregatesteTC(tpInitial)
			return
		if not t["sateliti"]:
			self.cSatelit = self.cTransponder = None
			return
		pozitii = [str(s["poz"]) for s in t["sateliti"]]
		if tpInitial is not None:
			implicit = str(tpInitial["orbital_position"])
		elif pozInitiala is not None:
			implicit = str(pozInitiala)
		else:
			implicit = pozitii[0]
		self.cSatelit = ConfigSelection(choices=[(str(s["poz"]), HdsGasireSemnal.text_satelit(s))
			for s in t["sateliti"]], default=implicit if implicit in pozitii else pozitii[0])
		self._pregatesteSatelit(tpInitial)

	def _pregatesteSatelit(self, tpInitial=None):
		t = self._tunerCurent()
		poz = int(self.cSatelit.value)
		self._transpondere, self._sarite = HdsGasireSemnal.transpondere(poz, t["s2"])
		alegeri = [(str(i), HdsGasireSemnal.text_transponder(e["tp"])) for i, e in enumerate(self._transpondere)]
		alegeri.append((MANUAL, _("Introdus de mână")))
		implicit = "0" if self._transpondere else MANUAL
		if tpInitial is not None:
			i = HdsGasireSemnal.potriveste(tpInitial, self._transpondere)
			implicit = str(i) if i >= 0 else MANUAL
			self._tpAles = tpInitial
		elif self._transpondere:
			self._tpAles = self._transpondere[0]["tp"]
		elif self._tpAles is not None:
			self._tpAles = dict(self._tpAles, orbital_position=poz)
		self.cTransponder = ConfigSelection(choices=alegeri, default=implicit)
		if implicit == MANUAL and self._tpAles is not None:
			self._umpleManual(self._tpAles)

	def _pregatesteTC(self, tpInitial=None):
		"""Randul „Frecvența” al tunerului terestru sau de cablu: lista din Setari tuner, apoi „Introdus de mână”."""
		t = self._tunerCurent()
		self._frecventeTC, _nume = HdsGasireSemnal.frecvente_tc(t["slot"], t["fel"])
		alegeri = [(str(i), e["text"]) for i, e in enumerate(self._frecventeTC)]
		alegeri.append((MANUAL, _("Introdus de mână")))
		implicit = "0" if self._frecventeTC else MANUAL
		if tpInitial is not None and HdsGasireSemnal.fel_tp(tpInitial) == t["fel"]:
			i = HdsGasireSemnal.potriveste_tc(tpInitial, self._frecventeTC)
			implicit = str(i) if i >= 0 else MANUAL
			self._tpAles = tpInitial
		elif self._frecventeTC:
			self._tpAles = self._frecventeTC[0]["tp"]
		self.cFrecventaTC.value = 474 if t["fel"] == HdsGasireSemnal.FEL_TERESTRU else 346
		self.cListaTC = ConfigSelection(choices=alegeri, default=implicit)
		if implicit == MANUAL and self._tpAles is not None:
			self._umpleManualTC(self._tpAles)

	def _umpleManualTC(self, tp):
		fel = HdsGasireSemnal.fel_tp(tp)
		if fel != self._tunerCurent().get("fel"):
			return
		if fel == HdsGasireSemnal.FEL_TERESTRU:
			self.cFrecventaTC.value = int(round(tp["frequency"] / 1000000.0))
			self.cLatime.value = str(tp["bandwidth"])
			self.cSistemT.value = str(tp["system"]) if tp.get("system") in (0, 1) else "1"
		else:
			self.cFrecventaTC.value = int(round(tp["frequency"] / 1000.0))
			self.cRataC.value = tp["symbol_rate"] // 1000
			self.cModC.value = str(tp["modulation"])

	def _umpleManual(self, tp):
		self.cFrecventa.value = tp["frequency"] // 1000
		self.cRata.value = tp["symbol_rate"] // 1000
		self.cPol.value = str(tp["polarisation"])
		self.cSistem.value = str(tp["system"])
		if tp["system"] == HdsGasireSemnal.SISTEM_DVB_S2:
			self.cMod.value = str(tp["modulation"])
			self.cFecS2.value = str(tp["fec"])
			self.cRolloff.value = str(tp["rolloff"])
			self.cPilot.value = str(tp["pilot"])
		else:
			self.cFecS.value = str(tp["fec"])

	def _construiesteLista(self):
		lista = []
		if self.tunere:
			if self.cProgram is not None:
				lista.append(getConfigListEntry(_("Transponderul canalului de acum"), self.cProgram))
			if len(self.tunere) > 1:
				lista.append(getConfigListEntry(_("Tuner"), self.cTuner))
			if self.cListaTC is not None:
				lista.append(getConfigListEntry(_("Frecvența"), self.cListaTC))
				if self.cListaTC.value == MANUAL:
					lista.append(getConfigListEntry(_("Frecvența (MHz)"), self.cFrecventaTC))
					if self._tunerCurent().get("fel") == HdsGasireSemnal.FEL_TERESTRU:
						lista.append(getConfigListEntry(_("Lățimea de bandă"), self.cLatime))
						lista.append(getConfigListEntry(_("Sistem"), self.cSistemT))
					else:
						lista.append(getConfigListEntry(_("Rata de simbol (kSymb/s)"), self.cRataC))
						lista.append(getConfigListEntry(_("Modulație"), self.cModC))
			elif self.cSatelit is not None:
				lista.append(getConfigListEntry(_("Satelit"), self.cSatelit))
				lista.append(getConfigListEntry(_("Transponder"), self.cTransponder))
				if self.cTransponder.value == MANUAL:
					# aceleași texte ca în scanerul în care duce verdele (Screens/ScanerSatelit.py)
					lista.append(getConfigListEntry(_("Frecvența (MHz)"), self.cFrecventa))
					lista.append(getConfigListEntry(_("Rata de simbol (kSymb/s)"), self.cRata))
					lista.append(getConfigListEntry(_("Polarizare"), self.cPol))
					lista.append(getConfigListEntry(_("Sistem"), self.cSistem))
					if self.cSistem.value == str(HdsGasireSemnal.SISTEM_DVB_S2):
						lista.append(getConfigListEntry(_("Modulație"), self.cMod))
						lista.append(getConfigListEntry("FEC", self.cFecS2))
						lista.append(getConfigListEntry("Roll-off", self.cRolloff))
						lista.append(getConfigListEntry(_("Pilot"), self.cPilot))
					else:
						lista.append(getConfigListEntry("FEC", self.cFecS))
		self.list = lista
		self["config"].list = lista
		self._tineMinteValorile()

	def _tpDinCampuri(self):
		"""(tp, extra, eroare) din câmpuri: transponderul ales din listă sau cel bătut de mână, exact cum e bătut."""
		t = self._tunerCurent()
		if self.cListaTC is not None:
			extra = {"tsid": -1, "onid": -1, "sarite": 0, "fara_lista": False}
			if self.cListaTC.value != MANUAL:
				return self._frecventeTC[int(self.cListaTC.value)]["tp"], extra, ""
			valori = {"frecventa": self.cFrecventaTC.value, "latime": self.cLatime.value, "sistem": self.cSistemT.value,
				"sr": self.cRataC.value, "mod": self.cModC.value}
			tp, eroare = HdsGasireSemnal.transponder_din_campuri_tc(valori, t["fel"])
			return tp, extra, eroare
		poz = int(self.cSatelit.value)
		if self.cTransponder.value != MANUAL:
			e = self._transpondere[int(self.cTransponder.value)]
			return e["tp"], {"tsid": e["tsid"], "onid": e["onid"], "sarite": self._sarite, "fara_lista": False}, ""
		s2 = self.cSistem.value == str(HdsGasireSemnal.SISTEM_DVB_S2)
		valori = {"frecventa": self.cFrecventa.value, "sr": self.cRata.value, "pol": self.cPol.value,
			"sistem": self.cSistem.value, "fec": self.cFecS2.value if s2 else self.cFecS.value,
			"mod": self.cMod.value, "rolloff": self.cRolloff.value, "pilot": self.cPilot.value}
		tp, eroare = HdsGasireSemnal.transponder_din_campuri(valori, poz, t["s2"])
		return tp, {"tsid": -1, "onid": -1, "sarite": self._sarite, "fara_lista": not self._transpondere}, eroare

	# ---------------------------------------------------------------- măsurarea
	def _pornesteMasurarea(self):
		if not self.tunere:
			self.masurare.porneste(None, None, "ecran", self.session)
			return
		t = self._tunerCurent()
		if self.cSatelit is None and self.cListaTC is None:
			self.masurare.porneste(t["slot"], None, "ecran", self.session, s2=t["s2"])
			return
		tp, extra, eroare = self._tpDinCampuri()
		if eroare:
			self.masurare.arata_refuz(eroare, t["slot"], cine="ecran")
			return
		self._tpAles = tp
		self._cuVoie(tp, lambda: self.masurare.porneste(t["slot"], tp, "ecran", self.session, extra, t["s2"]))

	def _cuVoie(self, tp, actiune):
		"""GSW2 D: spre un satelit în afara cursei motorului, prea jos sau sub orizont comanda pleacă numai după „Da”;
		altfel actiune() acum. Satelitul pe care e deja măsurarea (antena e acolo) nu mai întreabă."""
		if tp is None or HdsGasireSemnal.fel_tp(tp) != HdsGasireSemnal.FEL_SATELIT:
			return actiune()
		poz = tp["orbital_position"]
		m = self.masurare
		if poz == self._confirmatPoz or (m.tp is not None and HdsGasireSemnal.fel_tp(m.tp) == HdsGasireSemnal.FEL_SATELIT
				and m.tp.get("orbital_position") == poz and m.faza not in ("oprita", "refuzat")):
			return actiune()
		t = self._tunerCurent()
		sat = HdsGasireSemnal.satelit_din(t, poz) if t.get("motor") else None
		text = HdsGasireSemnal.text_departe(sat) if sat else ""
		if not text:
			return actiune()
		self._actiuneDupaVoie = (poz, actiune)
		from Screens.MessageBox import MessageBox
		self.session.openWithCallback(self._dupaVoie, MessageBox, text, MessageBox.TYPE_YESNO, default=False)

	def _dupaVoie(self, da):
		poz, actiune = getattr(self, "_actiuneDupaVoie", (None, None))
		self._actiuneDupaVoie = None
		if da and actiune is not None:
			self._confirmatPoz = poz
			actiune()

	def _laProgram(self):
		"""GSW2 B: OK pe „Transponderul canalului de acum”: tunerul, satelitul și transponderul programului, apoi
		măsurarea (pe transponderul lui, fără oprirea programului)."""
		p = self._program
		if p is None:
			return
		self._ceasAcord.stop()
		self._numericSchimbat = False
		self.cTuner.value = str(p["slot"])
		self._valori[id(self.cTuner)] = self.cTuner.value
		self._pregatesteTuner(p["tp"])
		self._construiesteLista()
		self._pornesteMasurarea()

	def _programeazaAcord(self):
		self._ceasAcord.start(INTARZIERE_ACORD_MS, True)

	def _acordeazaCampurile(self):
		self._ceasAcord.stop()
		self._numericSchimbat = False
		if self.cSatelit is None and self.cListaTC is None:
			return
		tp, extra, eroare = self._tpDinCampuri()
		if eroare:
			self.masurare.arata_refuz(eroare, self._tunerCurent()["slot"], cine="ecran")
			return
		self._tpAles = tp
		if self.masurare.tp == tp and self.masurare.faza not in ("oprita", "refuzat"):
			return
		self._cuVoie(tp, lambda: self.masurare.schimba(tp, extra, cine="ecran"))

	def _laStare(self, stare):
		"""Ascultătorul măsurării: se schimbă pe ecran numai ce s-a schimbat."""
		valori = {
			"header": stare["verdict"],
			"description": "\n".join(stare["detalii"]),
			"pos": stare["pozitie_text"],
			"tsid": stare["tsid_text"],
			"onid": stare["onid_text"],
		}
		for cheie, text in valori.items():
			if self._afisat.get(cheie) != text:
				self._afisat[cheie] = text
				self[cheie].setText(text)
		if "Frontend" in self:
			self["Frontend"].pune(stare)
		self._puneCanalele(stare)

	# ---------------------------------------------------------------- tastele și schimbările
	def _tineMinteValorile(self):
		self._valori = dict((id(x[1]), x[1].value) for x in self["config"].list)

	def changedConfig(self):
		"""ConfigListScreen o cheamă după orice tastă de pe rând (și după cele care nu schimbă nimic: săgeata în
		interiorul unui număr, o literă de pe tastatură). Se lucrează numai dacă valoarea chiar s-a schimbat."""
		cur = self["config"].getCurrent()
		if cur is None:
			return
		obiect = cur[1]
		if self._valori.get(id(obiect)) == obiect.value:
			return
		self._valori[id(obiect)] = obiect.value
		self._laSchimbare(obiect)

	def _laSchimbare(self, obiect):
		if obiect is self.cTuner:
			self._pregatesteTuner()
			self._construiesteLista()
			self._pornesteMasurarea()
			return
		if obiect is self.cSatelit:
			self._pregatesteSatelit()
			self._construiesteLista()
			self._programeazaAcord()
			return
		if obiect is self.cTransponder:
			if self.cTransponder.value == MANUAL and self._tpAles is not None:
				self._umpleManual(self._tpAles)
			self._construiesteLista()
			self._programeazaAcord()
			return
		if obiect is self.cListaTC:
			if self.cListaTC.value == MANUAL and self._tpAles is not None:
				self._umpleManualTC(self._tpAles)
			self._construiesteLista()
			self._programeazaAcord()
			return
		if obiect is self.cFrecventaTC or obiect is self.cRataC:
			self._numericSchimbat = True
			return
		if obiect is self.cFrecventa or obiect is self.cRata:
			# cifrele se bat pe rând: nu se acordează la fiecare cifră (21494 MHz în drum spre 11494), ci la
			# ieșirea de pe rând sau la OK
			self._numericSchimbat = True
			return
		if obiect is self.cSistem:
			self._construiesteLista()
		self._programeazaAcord()

	def _randSchimbat(self):
		if self._numericSchimbat:
			cur = self["config"].getCurrent()
			if cur is None or cur[1] not in (self.cFrecventa, self.cRata, self.cFrecventaTC, self.cRataC):
				self._programeazaAcord()

	def keyOk(self):
		cur = self["config"].getCurrent()
		if cur is None:
			return
		obiect = cur[1]
		if obiect is self.cProgram:
			self._laProgram()
			return
		if isinstance(obiect, ConfigSelection) and (obiect is self.cSatelit or obiect is self.cTransponder
				or obiect is self.cListaTC or len(obiect.choices) > PRAG_ALEGERE):
			self._alege(cur[0], obiect)
			return
		self.keyYellow()

	def _alege(self, titlu, obiect):
		intrari, selectie = [], 0
		for i, x in enumerate(obiect.choices.choices):
			cheie, text = x if isinstance(x, tuple) else (x, x)
			intrari.append((text, cheie))
			if cheie == obiect.value:
				selectie = i
		self._inAlegere = obiect
		from Screens.ChoiceBox import ChoiceBox
		self.session.openWithCallback(self._dupaAlegere, ChoiceBox, title=titlu, list=intrari, selection=selectie)

	def _dupaAlegere(self, rezultat=None):
		obiect, self._inAlegere = self._inAlegere, None
		if obiect is None or not rezultat:
			return
		if rezultat[1] == obiect.value:
			return
		obiect.value = rezultat[1]
		self._valori[id(obiect)] = obiect.value
		self["config"].invalidateCurrent()
		self._laSchimbare(obiect)

	def _faraSateliti(self):
		"""True când tunerul ales nu are niciun satelit (cu mai multe tunere, din rândul Tuner se poate alege unul
		nesetat): verde și galben nu au ce face și spun de ce, în loc să tacă sub etichetele lor."""
		if self.cSatelit is not None or self.cListaTC is not None:
			return False
		if "key_green" in self:
			self.masurare.spune_scurt(_("Pe acest tuner nu se poate acorda și nici căuta canale. Alege alt tuner din rândul „Tuner”."))
		return True

	def keyYellow(self):
		"""Acordează din nou: câmpurile schimbate se acordează acum; altfel același transponder, încă o dată."""
		if self._faraSateliti():
			return
		tp, extra, eroare = self._tpDinCampuri()
		self._ceasAcord.stop()
		self._numericSchimbat = False
		if eroare:
			self.masurare.arata_refuz(eroare, self._tunerCurent()["slot"], cine="ecran")
			return
		self._tpAles = tp
		if self.masurare.tp != tp:
			self._cuVoie(tp, lambda: self.masurare.schimba(tp, extra, cine="ecran"))
		else:
			self.masurare.reacordeaza(cine="ecran")

	def keyBlue(self):
		"""Albastru: canalele de pe transponderul prins (nume, TV sau radio, liber sau codat), citite din PAT si SDT,
		intr-o fereastra; lista de canale a receptorului nu se schimba."""
		if self._faraSateliti():
			return
		reusit, text = self.masurare.cere_canale(cine="ecran")
		if not reusit:
			self.masurare.spune_scurt(text)
			return
		from Screens.TextBox import TextBox
		self._textCanale = HdsGasireSemnal.text_canale(self.masurare.stare())
		self._fereastraCanale = self.session.openWithCallback(self._dupaCanale, TextBox, self._textCanale,
			title=_("Canalele de aici"))

	def _puneCanalele(self, stare):
		f = self._fereastraCanale
		if f is None:
			return
		text = HdsGasireSemnal.text_canale(stare)
		if text != self._textCanale:
			self._textCanale = text
			try:
				f["text"].setText(text)
			except Exception as e:
				print("[Satfinder] fereastra canalelor: %s" % e)

	def _dupaCanale(self, *argumente):
		self._fereastraCanale = None
		self._textCanale = None

	def keyGo(self):
		"""Verde: duce transponderul de aici în scanerul de satelit, cu toate valorile, felul „manual”.
		Tunerul se dă înapoi înainte (altfel scanarea nu găsește niciun tuner liber); canalul rămâne oprit și
		pornește la loc la ieșirea din Găsire semnal."""
		if self._faraSateliti():
			return
		tp, extra, eroare = self._tpDinCampuri()
		if eroare:
			self.masurare.arata_refuz(eroare, self._tunerCurent()["slot"], cine="ecran")
			return
		self._ceasAcord.stop()
		if self.cListaTC is not None:
			self._scanerTC(tp)
			return
		config_initial = {
			"pozitie": str(tp["orbital_position"]),
			"frecventa": tp["frequency"] // 1000,
			"sr": tp["symbol_rate"] // 1000,
			"pol": str(tp["polarisation"]),
			"sistem": str(tp["system"]),
			"fec": str(tp["fec"]),
			"mod": str(tp["modulation"]),
			"rolloff": str(tp["rolloff"]),
			"pilot": str(tp["pilot"]),
			"inversare": str(tp["inversion"]),
			"tip": "1",    # un singur transponder, cel de aici (felul „manual” al scanerului)
		}
		self.masurare.opreste(reda_canalul=False, cine="ecran")
		from Screens.ScanerSatelit import ScanerSatelit
		self.session.openWithCallback(self._dupaScaner, ScanerSatelit, config_initial=config_initial)

	def _scanerTC(self, tp):
		"""Verde pe un tuner terestru sau de cablu: frecventa de aici in scanerul lui, felul „manual” (aceleasi chei ca
		setarile scanerului: frecventa in MHz). La terestrul fara sistem in lista merge sistemul incercat acum."""
		L = HdsGasireSemnal._liste()
		if HdsGasireSemnal.fel_tp(tp) == HdsGasireSemnal.FEL_TERESTRU:
			sistem = tp.get("system")
			if sistem not in (0, 1):
				sistem = self.masurare._sistem_acordat if self.masurare._sistem_acordat in (0, 1) else 1
			config_initial = {"frecventa": L.mhz(tp["frequency"]), "sistem": str(sistem), "banda": str(tp["bandwidth"]),
				"mod": str(tp["modulation"]), "plp": ""}
			from Screens.ScanerTerestru import ScanerTerestru as Scaner
		else:
			config_initial = {"frecventa": L.mhz(tp["frequency"] * 1000), "sr": str(tp["symbol_rate"] // 1000),
				"mod": str(tp["modulation"])}
			from Screens.ScanerCablu import ScanerCablu as Scaner
		self.masurare.opreste(reda_canalul=False, cine="ecran")
		self.session.openWithCallback(self._dupaScaner, Scaner, fel="manual", config_initial=config_initial)

	def _dupaScaner(self, *argumente):
		"""Înapoi din scaner: se ia din nou tunerul și măsurarea continuă (canalul de la început rămâne cel de pus
		la loc la ieșire)."""
		self._pornesteMasurarea()

	def keyCancel(self):
		if self.masurare.iesirea_opreste_antena():
			from Screens.MessageBox import MessageBox
			self.session.openWithCallback(self._dupaIntrebareIesire, MessageBox,
				_("Antena se rotește încă. Dacă ieși acum, motorul se oprește din drum, iar antena merge unde trebuie la următorul canal de satelit. Ieși?"),
				MessageBox.TYPE_YESNO)
			return
		self.close()

	def _dupaIntrebareIesire(self, da):
		if da:
			self.close()

	# ---------------------------------------------------------------- deschidere, închidere
	def _laAsezare(self):
		self.setTitle(_("Găsire semnal"))
		_panouMotor(True)
		self._pornesteMasurarea()

	def _laInchidere(self):
		self._ceasAcord.stop()
		self.masurare.nu_mai_asculta(self._laStare)
		self.masurare.ecran_deschis = False
		self.masurare.opreste(reda_canalul=True, cine="ecran")
		_panouMotor(False)
