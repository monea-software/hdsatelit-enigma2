# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFbcMutare.py - Vu+ 4K cu tunere FBC: dupa actualizarea la 0.7.4, setarile tunerului B trec singure pe tunerul A,
# o singura data, numai cand receptorul a dovedit ca antena e in mufa A.
#
# De ce: pana la 0.7.3 Components/HdsFbc._radacini nu citea forma „0=A, 1=B” a lui fbc_connect_choices (driverele
# Vu+ 4K, de pilda Duo4K cu 45308X FBC). Nicio intrare nu era radacina, rutarea nu pornea si toate demodulatoarele
# ramaneau pe mufa A. Cine avea cablul in mufa A si numai tunerul B configurat vedea canalele. Din 0.7.4 tunerul B e
# legat la mufa lui, B, unde nu e cablu: fara semnal pana se configureaza A.
#
# Poarta (citita fara niciun acord): perechea A, B = primele doua radacini ale aceluiasi set FBC, cu alegerile in
# forma cu litere (numai acolo era greseala; forma „0 1” era citita bine si inainte). A „nimic conectat”, B simplu
# sau avansat. Altfel nu e cazul: se scrie semnul si nu se mai verifica nimic. Fara FBC: nimic, nici semn.
# Cand alt tuner e legat de B (la fel cu, legat la, al doilea cablu, Unicable legat), nu se muta nimic: numai mesajul.
#
# Proba (in fundal, pe eTimer, cu proba tunerului B din Components/HdsTunerB.py, rolurile intoarse): canalul de
# satelit care merge pe B, fara semnal la doua citiri la rand. Daca B il prinde vreodata, cablul e in mufa B: semn,
# nimic schimbat. Altfel A se pune NUMAI IN MEMORIE „la fel ca B” si se acordeaza pe transponderul acelui canal, cu
# setarile lui B, pe mufa A. Canalul de pe B ramane pornit si se citeste la fiecare pas: daca B prinde in timpul
# probei, sau omul schimba canalul, nu se muta nimic.
#
# Mutarea (A a prins, B nu): canalul se opreste, valorile tunerului B trec pe A cu HdsLnbAplicare.scrieValori (in
# ordinea in care notificarile din NimManager fac sectiunile modului avansat, cu recitire), B trece pe „nimic
# conectat”, se salveaza, sec.update(), iar canalul porneste din nou dupa 3,5 s (nucleul tine canalul 3 s dupa
# oprire, lib/dvb/dvb.cpp). Randurile de dinainte si de dupa ale ambelor tunere se scriu in hds-tuner.log, ca mutarea
# sa se poata desface de mana. Un mesaj pe televizor (se inchide singur) si un rand in pagina web a tunerelor spun ce
# s-a intamplat. B ramane „ales de om” (hdsAlesDeOm), ca inainte: proba automata a tunerului B nu il mai atinge.
#
# Nesigur (nici A nu prinde, alt tuner e legat de B, copierea nu s-a potrivit, sau proba nu porneste deloc pe A de
# ESECURI_LA_PORNIRE ori: canalul brut nu se da, acordul e refuzat): nimic mutat; un mesaj pe televizor, o data, si
# randul din pagina web (cat timp A ramane neconfigurat si B configurat) spun ce e de facut.
# O proba care nu se poate face acum (standby, inregistrare, transmisie in retea, PiP, ecranul tunerului deschis,
# niciun canal de satelit pe B) se reia mai tarziu, fara semn. Canalul de pe B se poate citi si fara semnal: la un
# acord cazut nucleul pastreaza canalul (lib/dvb/pmt.cpp, state_failed), deci tunerul si parametrii ceruti raman.
#
# Semnul „o singura data”: config.misc.hds_fbc_mutare in settings, un cuvant pe pereche („1>0:mutat:<ora>”). O copie
# a setarilor de dinainte (fara semn) se judeca din nou. Logica de alegere e in functii fara enigma (probe pe PC).

import time

PRIMA_S = 20                  # dupa pornirea interfetei: canalul de pe B a avut timp sa prinda, daca poate
PAS_S = 15                    # citirea canalului de pe B, pana la proba
CITIRI_FARA_SEMNAL = 2        # canalul de pe B fara semnal la atatea citiri la rand
PROBA_S = 15                  # cat incearca A
PROBA_MOTOR_S = 90            # cu motor antena poate avea de rotit
MS_ELIBERARE = 3500           # nucleul tine canalul 3 s dupa oprire
ZILE_RAND_WEB = 14            # cat ramane in pagina web randul „mutat”
INCERCARI_PE_PORNIRE = 8      # probe incepute si nehotarate (omul schimba canalul): apoi abia la pornirea
                              # urmatoare, ca jurnalul sa nu se umple
ESECURI_LA_PORNIRE = 3        # proba care nu poate porni pe A (canalul brut nu se da, acordul e refuzat): dupa atatea
                              # pe o pornire, „nesigur” cu mesajul, ca omul sa nu ramana fara semnal si fara stire

MUTAT, B_ARE_SEMNAL, NESIGUR, NU_E_CAZUL = "mutat", "b_are_semnal", "nesigur", "nu_e_cazul"
FINALE = (MUTAT, B_ARE_SEMNAL, NESIGUR, NU_E_CAZUL)
CANDIDAT, LEGAT = "candidat", "legat"
LEGATURI = ("equal", "loopthrough", "satposdepends")
# valorile care tin de tunerul insusi, nu de antena: nu trec de pe B pe A
CHEI_PROPRII = ("connectedTo", "hdsAuto", "hdsTpProba", "hdsAlesDeOm", "toneAmplitude", "multiType",
	"advanced.unicableconnected", "advanced.unicableconnectedTo")

_sesiune = None
_ceas = None
_ceas_pornire = None
_proba = None
_citiri = {}                  # perechea -> (referinta canalului, cate citiri la rand fara semnal)
_incercari = 0                # probe incepute la pornirea de acum
_esecuri = 0                  # probe cazute chiar la pornire (in HdsTunerB.Proba.porneste), la pornirea de acum
_in_pornire = False           # proba e in porneste(): un „cedat” acum e un esec al probei, nu o intrerupere
_ultimul_motiv = ""           # ultimul motiv de amanare scris in jurnal (fiecare motiv o data)


def _jurnal(text):
	print("[HdsFbcMutare] %s" % text)


def _jurnal_tuner(text):
	"""hds-tuner.log (Components/HdsJurnal.py), langa randurile [configurare] ale tunerelor"""
	_jurnal(text)
	try:
		from Components import HdsJurnal
		HdsJurnal.info("tuner", "fbc", text)
	except Exception:
		pass


def litera(slot):
	return chr(ord("A") + int(slot))


def _int(text):
	try:
		return int(text)
	except (TypeError, ValueError):
		return None


# ---------------------------------------------------------------- reguli (fara enigma)
def perechi_fbc(tunere, citeste):
	"""[(A, B)]: sloturile primelor doua radacini ale fiecarui set FBC, numai cand alegerile sunt in forma cu litere
	(„0=A, 1=B”), singura citita gresit pana la 0.7.3. `citeste(frontend, cheie)` = HdsFbc._citeste."""
	from Components.HdsFbc import RADACINA
	grupe = {}
	for t in tunere:
		if getattr(t, "fbc_role", 0) != RADACINA or getattr(t, "fbc_set_id", None) is None:
			continue
		if t.frontend_id is None or t.frontend_id < 0:
			continue
		grupe.setdefault(t.fbc_set_id, []).append(t)
	rez = []
	for set_id in sorted(grupe):
		radacini = sorted(grupe[set_id], key=lambda t: t.frontend_id)
		if len(radacini) < 2:
			continue
		if "=" not in (citeste(radacini[0].frontend_id, "fbc_connect_choices") or ""):
			continue
		rez.append((radacini[0].slot, radacini[1].slot))
	return rez


def _valoare(cfg, cale, implicit=None):
	from Components import HdsLnb
	el = HdsLnb.element(cfg, cale)
	if el is None or HdsLnb._esteNimic(el):
		return implicit
	try:
		return el.value
	except Exception:
		return implicit


def _unicable_legat(cfg):
	return _valoare(cfg, "configMode") == "advanced" and bool(_valoare(cfg, "advanced.unicableconnected", False))


def poarta(a, b, cfg_de, altii):
	"""None (nu e cazul), CANDIDAT sau LEGAT (alt tuner tine de B: se probeaza, dar nu se muta). `cfg_de(slot)` =
	config.Nims[slot]; `altii` = sloturile celorlalti tuneri de satelit."""
	cfg_a, cfg_b = cfg_de(a), cfg_de(b)
	if _valoare(cfg_a, "configMode") != "nothing":
		return None
	if _valoare(cfg_b, "configMode") not in ("simple", "advanced"):
		return None
	if _unicable_legat(cfg_b):
		return LEGAT
	for slot in altii:
		if slot in (a, b):
			continue
		cfg = cfg_de(slot)
		mod = _valoare(cfg, "configMode")
		if mod in LEGATURI and _int(_valoare(cfg, "connectedTo")) == b:
			return LEGAT
		if _unicable_legat(cfg) and _int(_valoare(cfg, "advanced.unicableconnectedTo")) == b:
			return LEGAT
	return CANDIDAT


def cheie(a, b):
	"""cheia perechii in semn: de unde („1”) si unde („0”) se muta"""
	return "%d>%d" % (b, a)


def citeste_semn(text):
	"""{"1>0": (rezultat, ora)} din valoarea semnului; cuvintele necunoscute nu conteaza"""
	rez = {}
	for cuvant in (text or "").split():
		parti = cuvant.split(":")
		if len(parti) < 2 or parti[1] not in FINALE or ">" not in parti[0]:
			continue
		rez[parti[0]] = (parti[1], _int(parti[2]) if len(parti) > 2 else 0)
	return rez


def scrie_semn(semne):
	return " ".join("%s:%s:%d" % (k, semne[k][0], semne[k][1] or 0) for k in sorted(semne))


def text_mutat(a, b):
	return _("Antena este în mufa %(a)s. Receptorul a mutat singur setările tunerului %(b)s pe tunerul %(a)s, iar "
		"tunerul %(b)s a rămas neconfigurat. Nu trebuie să faci nimic.") % {"a": litera(a), "b": litera(b)}


def text_nesigur(a, b):
	return _("Tunerul %(b)s nu prinde semnal. Din versiunea 0.7.4 fiecare mufă a receptorului merge cu tunerul ei. "
		"Dacă antena este în mufa %(a)s: Meniu > Orientarea și setarea antenei > Setări tuner, configurează tunerul "
		"%(a)s la fel ca tunerul %(b)s, apoi pune tunerul %(b)s pe „nimic conectat”.") % {"a": litera(a), "b": litera(b)}


def frunze_de_mutat(cfg_b):
	"""[(cale, text)]: valorile tunerului B care trec pe A (fara ConfigNothing si fara cheile proprii tunerului)"""
	from Components import HdsLnbAplicare
	frunze = HdsLnbAplicare.instantaneu(cfg_b)[0]
	return sorted((cale, text) for cale, text in frunze.items() if cale not in CHEI_PROPRII)


def muta_in_memorie(cfg_a, cfg_b, verifica=None):
	"""Valorile lui B pe A si B pe „nimic conectat”, numai in `value` (nimic salvat). None daca s-a potrivit tot
	(recitirea din scrieValori si `verifica()`), altfel textul greselii, cu A si B puse la loc."""
	from Components import HdsLnbAplicare as LA
	perechi = frunze_de_mutat(cfg_b)
	frunze_a = LA.instantaneu(cfg_a)[0]
	nimic = LA._pastreazaNimic(cfg_a)
	# resturile vechi ale modului avansat al lui A (din settings) nu se amesteca peste setarile lui B: sectiunea
	# `advanced` facuta acum de NimManager.configModeChanged porneste goala
	avansat_vechi = cfg_a.content.stored_values.pop("advanced", None)
	mod_b = cfg_b.configMode.value
	try:
		LA.scrieValori(cfg_a, perechi)
		cfg_b.configMode.value = "nothing"
		if verifica is not None and not verifica():
			raise ValueError("satelitii tunerului A nu sunt cei ai lui B")
	except Exception as eroare:
		greseala = "%s: %s" % (type(eroare).__name__, eroare)
		try:
			cfg_b.configMode.value = mod_b
			rele = LA.restaureaza(cfg_a, frunze_a)
			LA._punLaLocNimic(cfg_a, nimic)
			if avansat_vechi is not None:
				cfg_a.content.stored_values["advanced"] = avansat_vechi
			if rele:
				greseala += " (nepuse la loc: %s)" % ", ".join(rele[:5])
		except Exception as e:
			greseala += " (intoarcerea: %r)" % (e,)
		return greseala
	return None


def salveaza(cfg_a, cfg_b):
	"""A intreg, modul lui B si „ales de om” pe B, apoi settings pe disc"""
	cfg_a.save()
	cfg_b.configMode.save()
	if "hdsAlesDeOm" in cfg_b.content.items:
		cfg_b.hdsAlesDeOm.value = True
		cfg_b.hdsAlesDeOm.save()
	from Components.config import configfile
	configfile.save()


# ---------------------------------------------------------------- starea pe receptor
def _nm():
	from Components.NimManager import nimmanager
	return nimmanager


def _cfg(slot):
	from Components.config import config
	return config.Nims[slot]


def _semn():
	from Components.config import config, ConfigText
	if "hds_fbc_mutare" not in config.misc.content.items:
		config.misc.hds_fbc_mutare = ConfigText(default="", fixed_size=False)
	return config.misc.hds_fbc_mutare


def _scrie_semn(semne):
	el = _semn()
	el.value = scrie_semn(semne)
	el.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		_jurnal("settings: %r" % (e,))


def _satelit_sloturi(nm):
	try:
		return list(nm.getNimListOfType("DVB-S"))
	except Exception:
		return [t.slot for t in nm.nim_slots if t.isCompatible("DVB-S")]


def de_judecat(scrie=False):
	"""[(A, B, CANDIDAT|LEGAT)]: perechile care asteapta proba. Cu `scrie` (numai la pornire, din valorile citite din
	settings), cele care nu sunt cazul primesc semnul; mai tarziu doar nu se mai probeaza (o valoare schimbata in
	ecranul tunerului si nesalvata nu lasa semn)."""
	nm = _nm()
	from Components import HdsFbc
	perechi = perechi_fbc(nm.nim_slots, HdsFbc._citeste)
	if not perechi:
		return []
	semne = citeste_semn(_semn().value)
	sloturi = _satelit_sloturi(nm)
	rez, schimbat = [], False
	for a, b in perechi:
		k = cheie(a, b)
		if k in semne:
			continue
		fel = poarta(a, b, _cfg, sloturi)
		if fel is None and scrie:
			semne[k] = (NU_E_CAZUL, int(time.time()))
			schimbat = True
			_jurnal("%s: nu e cazul (tunerul %s configurat sau %s neconfigurat)" % (k, litera(a), litera(b)))
		elif fel is not None:
			rez.append((a, b, fel))
	if schimbat:
		_scrie_semn(semne)
	return rez


def stare_web(acum=None):
	"""{slot: text} pentru pagina web a tunerelor: „mutat” pe tunerul A (ZILE_RAND_WEB zile), „nesigur” pe tunerul B
	cat timp A e tot neconfigurat si B configurat. Aceleasi texte ca pe televizor."""
	if acum is None:
		acum = time.time()
	rez = {}
	for k, (rezultat, ora) in citeste_semn(_semn().value).items():
		b, a = (_int(x) for x in k.split(">", 1))
		if a is None or b is None:
			continue
		if rezultat == MUTAT and acum - (ora or 0) < ZILE_RAND_WEB * 86400:
			rez[a] = text_mutat(a, b)
		elif rezultat == NESIGUR:
			try:
				if _valoare(_cfg(a), "configMode") == "nothing" and \
						_valoare(_cfg(b), "configMode") in ("simple", "advanced"):
					rez[b] = text_nesigur(a, b)
			except Exception:
				pass
	return rez


# ---------------------------------------------------------------- legaturile cu enigma2
def _nav():
	import NavigationInstance
	return NavigationInstance.instance


def _ref_text(ref):
	if ref is None:
		return None
	try:
		return ref.toString()
	except Exception:
		return str(ref)


def citeste_canalul():
	"""(prins, tuner, referinta ca text, serviciu) pentru canalul care merge, daca e de satelit si are tuner, altfel
	None. getFrontendStatus() fara argument intoarce dictionarul (lib/service/iservice.h)."""
	nav = _nav()
	serviciu = nav.getCurrentService() if nav is not None else None
	info = serviciu.frontendInfo() if serviciu is not None else None
	if info is None:
		return None
	date = info.getFrontendData() or {}
	tp = info.getTransponderData(True) or {}
	if tp.get("tuner_type") != "DVB-S":
		return None
	tuner = _int(date.get("tuner_number"))
	if tuner is None:
		return None
	stare = info.getFrontendStatus()
	prins = bool(stare.get("tuner_locked")) if isinstance(stare, dict) else False
	return prins, tuner, _ref_text(nav.getCurrentlyPlayingServiceReference()), serviciu


def _motiv_ocupat():
	"""de ce nu se poate proba acum (text pentru jurnal), sau "" """
	from Components import HdsTunerB
	if HdsTunerB._ecran_standby() is not None:
		return "standby"
	motiv = HdsTunerB._motiv_acum()
	if motiv:
		return motiv
	try:
		from Components import HdsLnbAplicare
		motiv = HdsLnbAplicare.motivOcupat(_sesiune)
	except Exception as e:
		motiv = "verificarea tunerului: %r" % (e,)
	return motiv or ""


def _clasa_proba():
	from Components import HdsTunerB

	class ProbaA(HdsTunerB.Proba):
		"""A pus in memorie „la fel ca B”, pe transponderul canalului de pe B (HdsTunerB.Proba, faza 1, cu rolurile
		intoarse: acolo `a` da setarile si `b` e tunerul probat). In plus: termenul ei (cu motor, mai lung) si canalul
		de pe B citit la fiecare pas: B prinde -> „b_prins”; alt canal sau alt tuner -> „cedat”."""

		def __init__(self, a, b, tp, ref, secunde, la_sfarsit):
			HdsTunerB.Proba.__init__(self, 1, b, a, "equal", tp, (), la_sfarsit)
			self.ref, self.secunde, self.slot_b = ref, secunde, b

		def _incepe_pas(self, pas, sloturi):
			HdsTunerB.Proba._incepe_pas(self, pas, sloturi)
			self.termen = time.monotonic() + self.secunde

		def _pas(self):
			try:
				citire = citeste_canalul()
			except Exception:
				citire = None
			if citire is None or citire[1] != self.slot_b or citire[2] != self.ref:
				return self._termina("cedat")
			if citire[0]:
				return self._termina("b_prins")
			return HdsTunerB.Proba._pas(self)

	return ProbaA


def _arata(text, timeout=-1):
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddNotification(MessageBox, text, MessageBox.TYPE_INFO, timeout=timeout)
	except Exception as e:
		_jurnal("mesajul de pe ecran: %r" % (e,))


def _hotaraste(a, b, rezultat, motiv=""):
	semne = citeste_semn(_semn().value)
	semne[cheie(a, b)] = (rezultat, int(time.time()))
	_scrie_semn(semne)
	_citiri.pop(cheie(a, b), None)
	_jurnal_tuner("tunerul %s fara semnal dupa 0.7.4: %s%s" % (litera(b), rezultat, (" (%s)" % motiv) if motiv else ""))
	if rezultat == NESIGUR:
		_arata(text_nesigur(a, b))


def _rand_tuner(slot):
	try:
		from Components import HdsJurnalTuner
		return HdsJurnalTuner.randTuner(_nm().nim_slots[slot])
	except Exception as e:
		return "%s: %r" % (litera(slot), e)


def _reporneste(ref):
	"""canalul oprit pentru mutare porneste din nou dupa MS_ELIBERARE, daca omul n-a pornit altul intre timp; in
	standby il ia ecranul Standby, la trezire"""
	global _ceas_pornire
	if ref is None:
		return

	def porneste_canalul():
		global _ceas_pornire
		_ceas_pornire = None
		nav = _nav()
		try:
			from Components import HdsTunerB
			standby = HdsTunerB._ecran_standby()
			if standby is not None:
				if getattr(standby, "prev_running_service", None) is None:
					standby.prev_running_service = ref
				return
			if nav.getCurrentlyPlayingServiceReference() is None:
				nav.playService(ref, checkParentalControl=False, forceRestart=True)
		except Exception as e:
			_jurnal("pornirea canalului: %r" % (e,))

	from enigma import eTimer
	_ceas_pornire = eTimer()
	_ceas_pornire.callback.append(porneste_canalul)
	_ceas_pornire.start(MS_ELIBERARE, True)


def _muta(a, b):
	"""A a prins cu setarile lui B, B nu: mutarea, o data. Intoarce rezultatul scris in semn."""
	nm, nav = _nm(), _nav()
	cfg_a, cfg_b = _cfg(a), _cfg(b)
	ref = nav.getCurrentlyPlayingServiceReference() if nav is not None else None
	try:
		nav.stopService()
	except Exception as e:
		_jurnal("oprirea canalului: %r" % (e,))
	inainte = (_rand_tuner(a), _rand_tuner(b))
	sateliti_b = [int(x[0]) for x in nm.getSatListForNim(b)]

	def verifica():
		return [int(x[0]) for x in nm.getSatListForNim(a)] == sateliti_b

	greseala = muta_in_memorie(cfg_a, cfg_b, verifica)
	if greseala is None:
		try:
			salveaza(cfg_a, cfg_b)
		except Exception as e:
			greseala = "salvarea: %r" % (e,)
	try:
		nm.sec.update()
	except Exception as e:
		_jurnal("sec: %r" % (e,))
	_reporneste(ref)
	if greseala is not None:
		_jurnal_tuner("mutarea %s -> %s nu s-a facut: %s" % (litera(b), litera(a), greseala))
		return NESIGUR, greseala
	_jurnal_tuner("setarile tunerului %s mutate pe %s (antena in mufa %s). Inainte: %s || %s. Dupa: %s || %s" % (
		litera(b), litera(a), litera(a), inainte[0], inainte[1], _rand_tuner(a), _rand_tuner(b)))
	_arata(text_mutat(a, b), 20)
	return MUTAT, ""


def _gata(a, b, fel, rezultat):
	global _proba, _esecuri
	_proba = None
	_jurnal("proba tunerului %s cu setarile lui %s: %s" % (litera(a), litera(b), rezultat))
	try:
		if rezultat == "prins":
			if fel == LEGAT:
				_hotaraste(a, b, NESIGUR, "alt tuner e legat de %s" % litera(b))
			else:
				final, motiv = _muta(a, b)
				_hotaraste(a, b, final, motiv)
		elif rezultat == "b_prins":
			_hotaraste(a, b, B_ARE_SEMNAL)
		elif rezultat == "neprins":
			_hotaraste(a, b, NESIGUR, "nici %s nu prinde" % litera(a))
		elif _in_pornire:
			# proba n-a pornit deloc pe A (canalul brut sau acordul): de cateva ori -> nesigur, cu mesajul
			_esecuri += 1
			_citiri.pop(cheie(a, b), None)
			if _esecuri >= ESECURI_LA_PORNIRE:
				_hotaraste(a, b, NESIGUR, "proba n-a putut porni pe %s" % litera(a))
		else:
			_citiri.pop(cheie(a, b), None)     # intrerupta (alt canal, inregistrare): se reia de la capat
	except Exception as e:
		_jurnal("dupa proba: %r" % (e,))
	_programeaza()


def _porneste_proba(a, b, fel, citire):
	global _proba, _incercari, _in_pornire
	_incercari += 1
	from Components import HdsTunerB
	from Components import HdsGasireSemnal as G
	prins, tuner, ref, serviciu = citire
	pozitii = [int(x[0]) for x in _nm().getSatListForNim(b)]
	tp = G.transponder_din_serviciu(serviciu, pozitii)
	if tp is None:
		_jurnal("canalul de pe %s nu are un transponder bun pentru proba" % litera(b))
		return False
	secunde = PROBA_MOTOR_S if HdsTunerB.are_motor(_cfg(b)) else PROBA_S
	_jurnal("proba: tunerul %s cu setarile lui %s, %d kHz, %d s" % (litera(a), litera(b), tp["frequency"], secunde))
	_proba = _clasa_proba()(a, b, tp, ref, secunde, lambda rezultat: _gata(a, b, fel, rezultat))
	_in_pornire = True
	try:
		_proba.porneste()
	except Exception as e:
		_jurnal("proba: %r" % (e,))
		if _proba is not None:
			_proba._termina("cedat")
	finally:
		_in_pornire = False
	return True


def bataie():
	"""O citire: canalul de pe B prinde -> B are semnal; fara semnal de CITIRI_FARA_SEMNAL ori la rand (acelasi canal)
	-> proba lui A. Intoarce True cat mai e ceva de judecat."""
	global _ultimul_motiv
	if _proba is not None:
		return True
	perechi = de_judecat()
	if not perechi:
		return False
	citire = citeste_canalul()
	pereche = None
	if citire is not None:
		for p in perechi:
			if p[1] == citire[1]:
				pereche = p
				break
	if pereche is None:
		_citiri.clear()
		return True
	a, b, fel = pereche
	k = cheie(a, b)
	if citire[0]:
		_hotaraste(a, b, B_ARE_SEMNAL)
		return len(perechi) > 1
	vechi = _citiri.get(k)
	n = vechi[1] + 1 if vechi is not None and vechi[0] == citire[2] else 1
	_citiri[k] = (citire[2], n)
	if n < CITIRI_FARA_SEMNAL:
		return True
	motiv = _motiv_ocupat()
	if motiv:
		if motiv != _ultimul_motiv:
			_jurnal("proba amanata: %s" % motiv)
		_ultimul_motiv = motiv
		return True
	_ultimul_motiv = ""
	if _incercari >= INCERCARI_PE_PORNIRE:
		_jurnal("%d probe nehotarate la pornirea asta: se reia la pornirea urmatoare" % _incercari)
		return False
	_porneste_proba(a, b, fel, citire)
	return True


def _bataie():
	try:
		mai_e = bataie()
	except Exception as e:
		# o greseala neasteptata nu se repeta la fiecare bataie: se reia la pornirea urmatoare
		_jurnal("bataie: %r" % (e,))
		mai_e = False
	if mai_e and _proba is None:
		_programeaza()


def _programeaza():
	if _ceas is not None and _proba is None:
		_ceas.start(PAS_S * 1000, True)


def porneste(session):
	"""Din mytest.py. Fara FBC cu forma cu litere, sau cu toate perechile judecate (semnul), nu face nimic."""
	global _sesiune, _ceas
	_sesiune = session
	if not de_judecat(scrie=True):
		return
	from enigma import eTimer
	_ceas = eTimer()
	_ceas.callback.append(_bataie)
	_ceas.start(PRIMA_S * 1000, True)
