# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDvbIRezerva: trecerea singura pe internet cand satelitul nu se receptioneaza si intoarcerea pe satelit cand revine,
# plus mesajul pentru canalele DVB-I oprite pentru tara omului.
#
# Cum merge (o bataie la BATAIE_MS pe firul enigma2, pornita de pluginul DVB-I la pornirea sesiunii):
#   - pe un canal de satelit care are si varianta de internet (Components/HdsDvbIDate.legaturaRef) si cu setarea
#     "Trecere singura pe internet" pornita, tunerul fara semnal PRAG_S secunde la rand, cu antena oprita => programul
#     trece pe adresa de internet a canalului (aceeasi lista, acelasi serviciu), cu numele canalului in referinta (bara
#     arata numele, nu adresa .mpd) si un mesaj scurt. Canalul tinut minte ramane cel de satelit;
#   - cat antena e in drum nu se trece pe internet: semnalul lipseste pentru ca antena nu a ajuns, nu pentru ca satelitul
#     nu se receptioneaza. Rotirea in curs pe tunerul programului, dupa nucleu (Mediu.rotire, lib/dvb/sec.cpp): motorul
#     in mers (de la SET_ROTOR_MOVING pana la oprire, inclusiv tinerea pe 18 V si asteptarea semnalului de la capat),
#     comanda notata si motorul inca nepornit (proba de semnal cu antena pe loc si opririle dinaintea comenzii; dupa o
#     proba prinsa starea ramane asa pana la urmatoarea comanda, de aceea se crede cel mult ROTIRE_ANUNTATA_S de la
#     prima vedere) sau o mutare a readucerii (mai jos). Numaratoarea PRAG_S incepe din nou dupa oprirea motorului:
#     trecerea vine numai daca si cu antena oprita satelitul tot nu se receptioneaza. Pe un tuner fara motor (sau pe o
#     imagine fara functiile nucleului) totul ramane ca inainte;
#   - cat merge internetul, transponderul canalului se incearca pe tunerul liber, FARA comanda de motor
#     (HdsMotorTuner.acordFaraMotor, ca verificarea readucerii), la PASI_S; prins de PRINDERI ori la rand => programul se
#     intoarce pe satelit;
#   - regula antenei (15.10): antena nu se roteste des; intai verificarea pe alte transpondere ale aceluiasi satelit.
#     Pe un receptor cu motor, readucerea (Components/HdsMotorPozitie.py) vede programul inlocuit ca program al
#     tunerului, fara semnal (programInlocuit, refSatelit, esteRefRezerva): verificarea pe referinte merge cat imaginea
#     vine de pe internet (tunerul e liber, deci nimic nu se opreste); daca nicio referinta nu se prinde, readucerea
#     cere programul de satelit inapoi (predaSatelitului: internetul se opreste, iar tunerul verificarii pune la loc
#     canalul de satelit, deci nucleul trimite comanda de motor ca pana acum). Pasii rotirilor raman ai readucerii;
#     cat o rotire e in curs, aici nu se trece pe internet;
#   - un zap al omului, standby-ul sau oprirea setarii opresc totul fara alt zap;
#   - un canal DVB-I pornit (din buchetul DVB-I sau prin trecere) si oprit pentru tara omului (incercarea din casa:
#     Components/HdsDvbIIncercare, 403/451/401) => mesajul cu tasta spre setarea VPN (Screens/HdsDvbI.HdsDvbIOprit),
#     cel mult o data la MESAJ_PAUZA_S pe canal; o incercare mai veche de REINCERCARE_S se face din nou la pornire.
#
# Legatura cu enigma2 sta in Mediu (inlocuit in probele de pe PC); logica e in Paznic.
from __future__ import absolute_import, unicode_literals

import sys
import threading
import time

BATAIE_MS = 2000
PRAG_S = 6                    # satelitul fara semnal atatea secunde: internet (Fara semnal din bara apare la 4 s)
# comanda de motor notata de nucleu si motorul inca nepornit: proba de semnal (16 x 250 ms) cu tonul, tensiunea si
# pauzele ei, plus o bataie; o stare mai veche (proba prinsa, secventa intrerupta) nu mai opreste trecerea
ROTIRE_ANUNTATA_S = 15
PASI_S = (20, 40, 60, 120, 300)   # incercarile transponderului canalului cat merge internetul, apoi la 300 s
PRINDERI = 2                  # citiri cu semnal la rand pentru intoarcere
ASTEPTARE_PROBA_S = 8         # cat se asteapta semnalul la o incercare
MESAJ_PAUZA_S = 30 * 60       # acelasi canal oprit pe tara: mesajul cel mult o data in atat
REINCERCARE_S = 10 * 60       # la pornirea unui canal DVB-I, o incercare mai veche de atat se face din nou
STARI_FARA_TRECERE = ("oprit_tara", "adresa_moarta")


def N_(text):
	return text


T_PE_INTERNET = N_("Satelitul nu se recepționează: %s merge acum de pe internet.")
T_INAPOI = N_("Satelitul se recepționează din nou: %s merge iar de pe satelit.")
T_OPRIT = N_("Canalul e oprit pentru țara ta")
T_OPRIT_TEXT = N_("%s nu se poate vedea de pe internet de aici: televiziunea a răspuns cu codul %d (acces oprit). Îl poți vedea cu VPN-ul receptorului pornit, cu o adresă din %s. După pornirea VPN-ului, canalul se încearcă din nou singur.")
T_OPRIT_REZERVA = N_("Satelitul nu se recepționează, iar %s nu se poate vedea de pe internet de aici: televiziunea a răspuns cu codul %d (acces oprit). Îl poți vedea cu VPN-ul receptorului pornit, cu o adresă din %s.")
T_MOARTA = N_("Adresa canalului nu mai răspunde")
T_MOARTA_TEXT = N_("%s nu se poate vedea de pe internet: adresa lui din lista DVB-I nu mai răspunde (cod %d). Lista se reîncarcă singură din oră în oră; dacă televiziunea pune o adresă nouă, canalul merge iar.")
T_TARA_LISTEI = N_("țara listei")
T_VPN_NAVIGATOR = N_("Acum VPN-ul duce numai navigatorul: în setarea VPN, la Ce trece prin VPN, alege tot traficul.")


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def cheie(ref):
	"""referinta fara nume, cu campurile ca numere si calea decodata: aceeasi pentru textul scris de noi si pentru
	toString() al nucleului (care o codifica din nou in felul lui); () pentru o referinta goala"""
	p = (ref or "").split(":")
	if len(p) < 10:
		return ()
	campuri = []
	for x in p[:10]:
		try:
			campuri.append(int(x, 16))
		except ValueError:
			campuri.append(x.lower())
	cale = p[10] if len(p) > 10 else ""
	for cod, car in (("%3a", ":"), ("%3A", ":"), ("%20", " "), ("%25", "%")):
		cale = cale.replace(cod, car)
	return tuple(campuri) + (cale,)


def acelasi(a, b):
	return bool(a) and bool(b) and cheie(a) == cheie(b)


# ------------------------------------------------------------------ legatura cu enigma2
class Mediu(object):
	"""Tot ce atinge enigma2; probele de pe PC dau unul fals cu aceleasi metode."""

	def __init__(self, sesiune=None):
		self.sesiune = sesiune

	def acum(self):
		return time.monotonic()

	def _nav(self):
		try:
			import NavigationInstance
			return NavigationInstance.instance
		except Exception:
			return None

	def refCurent(self):
		nav = self._nav()
		try:
			ref = nav and nav.getCurrentlyPlayingServiceReference()
			return ref.toString() if ref is not None and ref.valid() else ""
		except Exception:
			return ""

	def semnal(self):
		"""(slot, blocat) pentru programul de acum; (-1, None) cand nu e pe un tuner sau nu se poate citi"""
		try:
			from Components import HdsMotorTuner as T
			serviciu = self._nav().getCurrentService()
			info = serviciu and serviciu.frontendInfo()
			if not info:
				return -1, None
			slot = (info.getFrontendData() or {}).get("tuner_number", -1)
			return slot, bool(T._stareServiciu(info).get("tuner_locked"))
		except Exception:
			return -1, None

	def transponder(self, slot):
		"""transponderul programului de acum (forma acordului fara motor), citit cat merge"""
		try:
			from Components import HdsMotorTuner as T
			return T.programPeTuner(slot)[0]
		except Exception:
			return None

	def porneste(self, ref_text):
		nav = self._nav()
		if nav is None:
			return
		from enigma import eServiceReference
		try:
			nav.playService(eServiceReference(ref_text), checkParentalControl=False)
		except TypeError:
			nav.playService(eServiceReference(ref_text))

	def opreste(self):
		nav = self._nav()
		if nav is not None:
			nav.stopService()

	def refObiect(self, ref_text):
		from enigma import eServiceReference
		return eServiceReference(ref_text)

	def setari(self):
		from Components import HdsDvbISetari as S
		return S.citeste()

	def legatura(self, ref):
		from Components import HdsDvbIDate as D
		return D.legaturaRef(ref)

	def canalDvbI(self, ref):
		from Components import HdsDvbIDate as D
		return D.canalUrl(D.urlDinRef(ref))

	def stareUrl(self, url):
		from Components import HdsDvbIDate as D
		return D.stareUrl(url)

	def readucere(self):
		"""starea readucerii antenei (Components/HdsMotorPozitie.stareReaducere), fara sa incarce modulul"""
		m = sys.modules.get("Components.HdsMotorPozitie")
		try:
			return m.stareReaducere() if m is not None else {"activa": False}
		except Exception:
			return {"activa": False}

	def motorMerge(self, slot):
		try:
			from Components import HdsMotorTuner as T
			sec = T.controlSec()
			return sec is not None and int(sec.hdsRotorMovingSlot()) == slot
		except Exception:
			return False

	def rotire(self, slot):
		"""ce face motorul tunerului `slot` dupa nucleu (lib/dvb/sec.cpp): ("merge", None) cat motorul e in mers;
		("anuntata", (de_la, la, comanda)) cand comanda e notata (hdsNoteRotorMovement), dar motorul inca nu a pornit
		(ceasul miscarii porneste la SET_ROTOR_MOVING, dupa proba de semnal); ("", None) altfel, pe un tuner fara motor
		si pe o imagine fara functiile nucleului"""
		try:
			from Components import HdsMotorTuner as T
			sec = T.controlSec()
			if sec is None:
				return "", None
			misca = int(sec.hdsRotorMovingSlot()) == slot
			if not sec.hdsRotorInfoValid(slot):
				return ("merge", None) if misca else ("", None)
			trecut = int(sec.hdsRotorElapsedMs(slot))
			oprit = int(sec.hdsRotorStoppedMs(slot))
			if misca or (trecut >= 0 and oprit < 0):
				return "merge", None
			if trecut < 0 and oprit < 0:
				return "anuntata", (int(sec.hdsRotorFromOrbital(slot)), int(sec.hdsRotorToOrbital(slot)),
					int(sec.hdsRotorCmd(slot)))
		except Exception:
			pass
		return "", None

	def standby(self):
		try:
			from Screens import Standby
			return Standby.inStandby is not None
		except Exception:
			return False

	def internetMerge(self):
		try:
			from Components import HdsStareRetea
			return HdsStareRetea.internet()
		except Exception:
			return None

	def anunta(self, text):
		try:
			from Tools import Notifications
			from Screens.MessageBox import MessageBox
			Notifications.AddPopup(text, MessageBox.TYPE_INFO, 6, "HdsDvbIRezerva")
		except Exception as e:
			print("[HdsDvbIRezerva] mesajul: %r" % (e,))

	def mesajOprit(self, titlu, text, cu_vpn, la_inchidere):
		if self.sesiune is None:
			return
		try:
			from Screens.HdsDvbI import HdsDvbIOprit
			self.sesiune.openWithCallback(la_inchidere, HdsDvbIOprit, text, titlu, cu_vpn)
		except Exception as e:
			print("[HdsDvbIRezerva] ecranul canalului oprit: %r" % (e,))

	def vpnNumaiNavigator(self):
		try:
			from Components import HdsVpn
			s = HdsVpn.stare()
			return s.get("legatura") == "conectat" and s.get("mod") == "navigator"
		except Exception:
			return False

	def taraCanalului(self, canal):
		try:
			from Components import HdsDvbISetari as S
			tara = S.citeste().get("tara", "")
			return S.numeTara(tara) if tara else _t(T_TARA_LISTEI)
		except Exception:
			return _t(T_TARA_LISTEI)

	def incearcaInFundal(self, url, la_gata):
		"""incercarea din casa a unei adrese pe un fir; la_gata(stare, cod) pe firul enigma2"""
		def fir():
			try:
				from Components import HdsDvbIIncercare as I
				from Components import HdsDvbIDate as D
				st, cod = I.incearca(url)
				D.noteazaIncercari({url: (st, cod)})
			except Exception as e:
				print("[HdsDvbIRezerva] incercarea %s: %r" % (url, e))
				return
			try:
				from twisted.internet import reactor
				reactor.callFromThread(la_gata, st, cod)
			except Exception:
				pass
		threading.Thread(target=fir, name="HdsDvbI-incercare-canal", daemon=True).start()

	def proba(self, slot, tp, la_gata):
		"""transponderul canalului incercat pe tunerul liber, fara comanda de motor; la_gata(True / False) pe firul enigma2.
		Nu opreste nimic: daca tunerul nu se poate lua fara oprirea programului, raspunsul e False."""
		Proba(slot, tp, la_gata).porneste()


class Proba(object):
	"""O incercare a transponderului canalului de satelit pe tunerul liber (LuareTuner + acordFaraMotor + citiri)."""

	def __init__(self, slot, tp, la_gata):
		self.slot, self.tp, self.la_gata = slot, tp, la_gata
		self.ceas = None
		self.citiri = 0
		self.prinderi = 0
		self.gata = False

	def porneste(self):
		# alocarea directa, fara LuareTuner: cu internetul pe televizor tunerul e liber; daca nu e (o inregistrare, o
		# extensie), nu se opreste nimic si incercarea se socoteste fara semnal
		try:
			from enigma import eDVBResourceManager
			canal = eDVBResourceManager.getInstance().allocateRawChannel(self.slot)
			fe = canal.getFrontend() if canal is not None else None
		except Exception:
			canal, fe = None, None
		if fe is None:
			self._termina(False)
			return
		self.canal, self.fe = canal, fe
		from Components import HdsMotorTuner as T
		if T.acordFaraMotor(fe, self.tp) != 0:
			self._termina(False)
			return
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self._citeste)
		self.ceas.start(500, False)

	def _citeste(self):
		self.citiri += 1
		try:
			d = {}
			self.fe.getFrontendStatus(d)
			blocat = bool(d.get("tuner_locked")) and str(d.get("tuner_state", "")) != "TUNING"
		except Exception:
			blocat = False
		self.prinderi = self.prinderi + 1 if blocat else 0
		if self.prinderi >= PRINDERI:
			self._termina(True)
		elif self.citiri * 0.5 >= ASTEPTARE_PROBA_S:
			self._termina(False)

	def _termina(self, prins):
		if self.gata:
			return
		self.gata = True
		if self.ceas is not None:
			self.ceas.stop()
		# canalul brut se lasa: frontendul se inchide singur (lib/dvb/dvb.h, dec_use)
		self.canal = self.fe = None
		try:
			self.la_gata(prins)
		except Exception as e:
			print("[HdsDvbIRezerva] dupa proba: %r" % (e,))


# ------------------------------------------------------------------ logica
class Paznic(object):
	def __init__(self, mediu):
		self.m = mediu
		self.activa = None        # trecerea pe internet in curs (dict) sau None
		self.fara_de = None       # de cand programul de satelit de acum e fara semnal
		self.urmarit = ""         # programul de satelit urmarit
		self.fara_trecere = ""    # programul pe care nu se trece pe internet pana la urmatorul zap (varianta oprita)
		self.dvbi_vazut = ""      # ultimul canal DVB-I pornit (pentru mesajul si incercarea la pornire)
		self.mesaje = {}          # url -> ora ultimului mesaj
		self.jurnal = []          # ce s-a facut (pentru probe si pentru /api)
		self.anuntata = None      # ((slot, de_la, la, comanda), prima vedere) a comenzii de motor notate si nepornite
		self.astept_rotirea = False   # s-a scris in jurnal ca trecerea asteapta oprirea antenei
		self._setari = (0, None)

	def _noteaza(self, text):
		print("[HdsDvbIRezerva] %s" % text)
		self.jurnal.append(text)
		del self.jurnal[:-50]

	def setari(self):
		"""setarile, citite din nou cel mult o data la 10 s"""
		acum = self.m.acum()
		if self._setari[1] is None or acum - self._setari[0] > 10:
			try:
				self._setari = (acum, self.m.setari())
			except Exception:
				self._setari = (acum, {})
		return self._setari[1] or {}

	def pornita(self):
		s = self.setari()
		return str(s.get("activ", "da")).lower() in ("da", "yes", "1", "true") and \
			str(s.get("rezerva", "da")).lower() in ("da", "yes", "1", "true")

	# ---- ce intreaba readucerea antenei (Components/HdsMotorPozitie.py)
	def programInlocuit(self, slot):
		a = self.activa
		if a is None or a["slot"] != slot or not acelasi(self.m.refCurent(), a["internet"]):
			return None
		return a["orbital"]

	def refSatelit(self):
		a = self.activa
		if a is not None and acelasi(self.m.refCurent(), a["internet"]):
			return a["sat"]
		return None

	def esteRefRezerva(self, ref):
		a = self.activa
		return a is not None and acelasi(ref, a["internet"])

	def probaInCurs(self, slot):
		"""True cat incercarea transponderului canalului tine tunerul `slot` (canalul brut, pana la ASTEPTARE_PROBA_S):
		readucerea asteapta, ca LuareTuner sa nu opreasca imaginea de pe internet ca sa ia tunerul"""
		a = self.activa
		return a is not None and a["slot"] == slot and bool(a["proba"])

	def predaSatelitului(self, slot, luare=None):
		"""readucerea nu a prins nicio referinta si roteste antena: internetul se opreste, iar tunerul verificarii pune
		la loc programul de satelit (ca dupa o verificare care l-a oprit). -> True daca era o trecere aici"""
		a = self.activa
		if a is None or a["slot"] != slot:
			return False
		self.activa = None
		self.fara_de = None
		self._noteaza("readucerea roteste antena: inapoi pe satelit (%s)" % a["nume"])
		if acelasi(self.m.refCurent(), a["internet"]):
			self.m.opreste()
		if luare is not None:
			try:
				luare.oldref = self.m.refObiect(a["sat"])
				luare.am_oprit_canalul = True
			except Exception as e:
				print("[HdsDvbIRezerva] programul de satelit pentru readucere: %r" % (e,))
		return True

	# ---- bataia
	def bate(self):
		acum = self.m.acum()
		ref = self.m.refCurent()
		if self.activa is not None:
			self._bateInternet(acum, ref)
			return
		if ref != self.urmarit:
			self.urmarit = ref
			self.fara_de = None
			self.fara_trecere = ""
			self.astept_rotirea = False
		if not ref or ref == self.fara_trecere:
			return
		if ref.startswith("4097:"):
			self._canalDvbI(acum, ref)
			return
		self.dvbi_vazut = ""
		if not ref.startswith("1:"):
			return
		leg = self.m.legatura(ref)
		if leg is None or not self.pornita() or self.m.standby():
			self.fara_de = None
			return
		slot, blocat = self.m.semnal()
		if blocat is None or slot < 0:
			return
		# citita si cu semnal: prima vedere a unei comenzi notate si nepornite se tine minte cat mai devreme
		rotire = self._rotireInCurs(slot, acum)
		if not rotire:
			self.astept_rotirea = False
		if blocat:
			self.fara_de = None
			return
		r = self.m.readucere()
		if r.get("activa") and r.get("slot") == slot and r.get("in_curs"):
			# o rotire (sau o ocolire) e in curs: programul de satelit ramane al readucerii
			self.fara_de = None
			return
		if rotire:
			# antena e in drum: numaratoarea incepe din nou dupa oprirea motorului
			if not self.astept_rotirea:
				self.astept_rotirea = True
				self._noteaza("fara semnal pe %s cat antena se roteste: trecerea pe internet asteapta oprirea motorului"
					% leg["nume"])
			self.fara_de = None
			return
		if self.fara_de is None:
			self.fara_de = acum
			return
		if acum - self.fara_de < PRAG_S:
			return
		st, cod, _ora = self.m.stareUrl(leg["url"])
		if st in STARI_FARA_TRECERE:
			self.fara_de = None
			self.fara_trecere = ref   # pe acest program nu se mai incearca pana la urmatorul zap
			if st == "oprit_tara":
				self._mesajOprit(acum, leg["url"], leg["nume"], cod, rezerva=True)
			return
		if self.m.internetMerge() is False:
			return
		tp = self.m.transponder(slot)
		internet = leg["ref"] + ":" + leg["nume"].replace(":", " ")
		self.activa = {"sat": ref, "internet": internet, "slot": slot, "orbital": self._orbital(ref, tp),
			"url": leg["url"], "nume": leg["nume"], "tp": tp, "pornita_la": acum, "pas": 0,
			"urmatoarea": acum + PASI_S[0], "proba": False, "prinse": 0}
		self.fara_de = None
		self._noteaza("fara semnal pe %s de %d s: trece pe internet (%s)" % (leg["nume"], PRAG_S, leg["url"]))
		self.m.porneste(internet)
		self.m.anunta(_t(T_PE_INTERNET) % leg["nume"])

	def _rotireInCurs(self, slot, acum):
		"""True cat antena tunerului `slot` e in drum: motorul in mers, sau comanda notata si motorul inca nepornit cel
		mult ROTIRE_ANUNTATA_S de la prima vedere a aceleiasi comenzi (o stare ramasa de la o proba prinsa nu opreste
		trecerea, nici dupa un zap pe acelasi satelit, care nu trimite comanda noua)"""
		stare, comanda = self.m.rotire(slot)
		if stare == "merge":
			self.anuntata = None
			return True
		if stare != "anuntata":
			self.anuntata = None
			return False
		cheie = (slot,) + tuple(comanda)
		if self.anuntata is None or self.anuntata[0] != cheie:
			self.anuntata = (cheie, acum)
		return acum - self.anuntata[1] < ROTIRE_ANUNTATA_S

	def _orbital(self, ref, tp):
		if tp and tp.get("orbital_position") is not None:
			try:
				return int(tp["orbital_position"])
			except (TypeError, ValueError):
				pass
		try:
			ns = int(ref.split(":")[6], 16)
			return (ns >> 16) & 0xFFFF
		except (IndexError, ValueError):
			return -1

	def _bateInternet(self, acum, ref):
		a = self.activa
		if not acelasi(ref, a["internet"]):
			# zap-ul omului, standby-ul sau readucerea au pornit altceva: nimic de pus la loc
			self.activa = None
			self.urmarit = ref
			self.fara_de = None
			self._noteaza("trecerea pe internet s-a terminat: alt program (%s)" % (ref or "nimic"))
			return
		if not self.pornita():
			self._inapoi("setarea oprita")
			return
		if a["proba"] or acum < a["urmatoarea"] or a["tp"] is None:
			return
		r = self.m.readucere()
		if r.get("activa") and r.get("slot") == a["slot"] and (r.get("verificare") or r.get("ocolire") or r.get("in_curs")):
			return   # tunerul e al readucerii acum
		if self.m.motorMerge(a["slot"]):
			return
		a["proba"] = True
		self.m.proba(a["slot"], a["tp"], self._dupaProba)

	def _dupaProba(self, prins):
		a = self.activa
		if a is None:
			return
		a["proba"] = False
		acum = self.m.acum()
		if prins:
			self._inapoi("transponderul canalului se receptioneaza")
			return
		a["pas"] = min(a["pas"] + 1, len(PASI_S) - 1)
		a["urmatoarea"] = acum + PASI_S[a["pas"]]

	def _inapoi(self, motiv):
		a = self.activa
		self.activa = None
		self.fara_de = None
		self.urmarit = a["sat"]
		self._noteaza("inapoi pe satelit (%s): %s" % (a["nume"], motiv))
		if acelasi(self.m.refCurent(), a["internet"]):
			self.m.porneste(a["sat"])
			self.m.anunta(_t(T_INAPOI) % a["nume"])

	# ---- canalele DVB-I pornite (mesajul pentru cele oprite pe tara)
	def _canalDvbI(self, acum, ref):
		if ref == self.dvbi_vazut:
			return
		self.dvbi_vazut = ref
		c = self.m.canalDvbI(ref)
		if c is None:
			return
		url = c["url"]
		st, cod, ora = self.m.stareUrl(url)
		if st == "oprit_tara":
			self._mesajOprit(acum, url, c["nume"], cod)
		elif st == "adresa_moarta":
			self._mesajMoarta(acum, url, c["nume"], cod)
		if not st or time.time() - ora > REINCERCARE_S:
			self.m.incearcaInFundal(url, lambda s, k, r=ref, u=url, n=c["nume"]: self._dupaIncercare(r, u, n, s, k))

	def _dupaIncercare(self, ref, url, nume, st, cod):
		if self.m.refCurent() != ref:
			return
		if st == "oprit_tara":
			self._mesajOprit(self.m.acum(), url, nume, cod)
		elif st == "adresa_moarta":
			self._mesajMoarta(self.m.acum(), url, nume, cod)

	def _poateMesaj(self, acum, url):
		ultima = self.mesaje.get(url)
		if ultima is not None and acum - ultima < MESAJ_PAUZA_S:
			return False
		self.mesaje[url] = acum
		return True

	def _mesajOprit(self, acum, url, nume, cod, rezerva=False):
		if not self._poateMesaj(acum, url):
			return
		tara = self.m.taraCanalului(url)
		text = (_t(T_OPRIT_REZERVA) if rezerva else _t(T_OPRIT_TEXT)) % (nume, int(cod or 403), tara)
		if self.m.vpnNumaiNavigator():
			text += " " + _t(T_VPN_NAVIGATOR)
		self._noteaza("canal oprit pentru tara: %s (%s)" % (nume, cod))
		self.m.mesajOprit(_t(T_OPRIT), text, True, lambda *r: self._dupaMesaj(url, *r))

	def _mesajMoarta(self, acum, url, nume, cod):
		if not self._poateMesaj(acum, url):
			return
		self.m.mesajOprit(_t(T_MOARTA), _t(T_MOARTA_TEXT) % (nume, int(cod or 404)), False, lambda *r: None)

	def _dupaMesaj(self, url, vpn_deschis=False, *rest):
		"""dupa setarea VPN canalul se incearca din nou; daca merge si e inca pe ecran, porneste iar"""
		if not vpn_deschis:
			return
		ref = self.m.refCurent()

		def gata(st, cod, r=ref):
			if st == "merge" and self.m.refCurent() == r and r:
				self.dvbi_vazut = ""
				self.m.porneste(r)
		self.m.incearcaInFundal(url, gata)


# ------------------------------------------------------------------ instanta (o sesiune)
_PAZNIC = [None]
_CEAS = [None]


def porneste(sesiune):
	"""din pluginul DVB-I, la pornirea sesiunii: bataia la BATAIE_MS pe firul enigma2"""
	if _PAZNIC[0] is not None:
		return _PAZNIC[0]
	p = Paznic(Mediu(sesiune))
	_PAZNIC[0] = p
	try:
		from enigma import eTimer
		c = eTimer()
		c.callback.append(_bateSigur)
		c.start(BATAIE_MS, False)
		_CEAS[0] = c
	except Exception as e:
		print("[HdsDvbIRezerva] ceasul: %r" % (e,))
	return p


def _bateSigur():
	p = _PAZNIC[0]
	if p is None:
		return
	try:
		p.bate()
	except Exception as e:
		print("[HdsDvbIRezerva] bataia: %r" % (e,))


def programInlocuit(slot):
	"""orbitalul satelitului canalului inlocuit acum de internet pe tunerul `slot`, sau None (HdsMotorPozitie)"""
	p = _PAZNIC[0]
	return p.programInlocuit(slot) if p is not None else None


def refSatelit():
	p = _PAZNIC[0]
	return p.refSatelit() if p is not None else None


def esteRefRezerva(ref):
	p = _PAZNIC[0]
	return p.esteRefRezerva(ref) if p is not None else False


def predaSatelitului(slot, luare=None):
	p = _PAZNIC[0]
	return p.predaSatelitului(slot, luare) if p is not None else False


def probaInCurs(slot):
	p = _PAZNIC[0]
	return p.probaInCurs(slot) if p is not None else False


def stare():
	"""pentru pagina web si probe: trecerea in curs, fara obiecte"""
	p = _PAZNIC[0]
	if p is None or p.activa is None:
		return {"activa": False}
	a = p.activa
	return {"activa": True, "nume": a["nume"], "url": a["url"], "slot": a["slot"], "orbital": a["orbital"]}
