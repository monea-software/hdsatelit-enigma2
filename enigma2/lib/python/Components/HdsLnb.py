# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLnb.py - LNB-ul tunerelor de satelit, citit din setarile ADEVARATE ale tunerului si planificat inainte de
# orice scriere. Modulul nu scrie nimic si nu cere enigma la import, deci ruleaza si pe PC, in probe.
#
# Un singur adevar: config.Nims[n], acelasi pe care il arata „Setări tuner” (Screens/Satconfig.py) si pe care il
# trimite nucleului SecConfigure.update() (Components/NimManager.py: modul simplu 134-250, avansat 252-480).
# Ecranul „Configurare LNB” (Screens/ConfigLNB.py) si pagina web folosesc aceleasi functii de aici; scrierea,
# proba de semnal si intoarcerea sunt in HdsLnbAplicare.py.
#
# Ce stie nucleul despre LNB (din cod, nu presupus):
#   - modul simplu: LNB-ul e MEREU universal 9750/10600, prag 11700 (NimManager.py:59-62); tensiunea dupa
#     polarizare si tonul dupa banda (73-80, 97-103), cu o singura exceptie: la DiSEqC A/B si A/B/C/D cu
#     „Set Voltage and 22KHz” oprit, 13 V fix si fara ton (199-213, 84-85);
#   - modul avansat: tipul pe fiecare LNB (advanced.lnb[k].lof: universal_lnb, unicable, c_band, user_defined,
#     NimManager.py:1098-1102), oscilatoarele in MHz (1316-1318, inmultite cu 1000 la 325-327 si 340-342);
#     tensiunea si tonul pe fiecare satelit (advanced.sat[x], 1357-1379); „toti satelitii” = sat[3601..3604] spre
#     LNB 33..36 (267-275), cu tensiunea si tonul luate de pe sat[3601..3604] (455-459);
#   - banda de sus cand frecventa e STRICT peste prag (sec.cpp:374-375), oscilatorul dupa banda (379),
#     frecventa intermediara = |f - oscilator| (384-386), tunerul refuzat daca ea iese din 900-2200 MHz (218-224),
#     tensiunea dupa polarizare (389-396), tonul dupa banda (397-402). Toate frecventele nucleului sunt in kHz.

import hashlib

FI_MIN_KHZ = 900000
FI_MAX_KHZ = 2200000
# pragul „niciodata banda de sus”: limita de sus a campului threshold (NimManager.py:1316-1318)
PRAG_MEREU_JOS = 99999
OSCILATOR_10750 = 10750
NIMIC_CONECTAT = 3601
TOTI_SATELITII = (3601, 3602, 3603, 3604)
LNB_MOTOR = 33

TIP_UNIVERSAL = "universal"
TIP_UN_OSCILATOR = "un_oscilator_10750"
TIP_BANDA_C = "banda_c"
TIP_PERSONALIZAT = "personalizat"
TIP_UNICABLE = "unicable"
TIPURI_DE_ALES = (TIP_UNIVERSAL, TIP_UN_OSCILATOR, TIP_BANDA_C, TIP_PERSONALIZAT)

DIFERA = "difera"
PORTURI = ("A", "B", "C", "D")
COMANDA_PORT = {"A": "AA", "B": "AB", "C": "BA", "D": "BB"}
NUMAR_PORT = {"A": 1, "B": 2, "C": 3, "D": 4}
MOTOR = "motor"
# satelitii alesi, in aceasta ordine, pentru „Probă de calcul” cand canalul care ruleaza nu e pe LNB-ul aratat
PREFERATI = (130, 192, 235, 282, 3592, 90)

# campurile pe care le poate schimba omul, pe fiecare LNB
CAMPURI_LNB = ("tip", "lofl", "lofh", "prag", "tensiune", "ton", "tensiune_marita", "comanda")


# ------------------------------------------------------------------ texte pentru om

def textTip(tip):
	if tip == TIP_UNIVERSAL:
		return _("Universal (9750/10600, prag 11700)")
	if tip == TIP_UN_OSCILATOR:
		return _("Un oscilator 10750 (Ku)")
	if tip == TIP_BANDA_C:
		return _("Banda C (5150)")
	if tip == TIP_PERSONALIZAT:
		return _("Personalizat")
	if tip == TIP_UNICABLE:
		return _("Unicable (se schimbă din Setări tuner)")
	return tip


def textTensiune(valoare):
	if valoare == "polarization":
		return _("după polarizare (13 V / 18 V)")
	if valoare == "13V":
		return _("13 V mereu")
	if valoare == "18V":
		return _("18 V mereu")
	if valoare == DIFERA:
		return _("diferă pe sateliți (rămân cum sunt)")
	return valoare


def textTon(valoare):
	if valoare == "band":
		return _("după bandă")
	if valoare == "on":
		return _("pornit mereu")
	if valoare == "off":
		return _("oprit mereu")
	if valoare == DIFERA:
		return _("diferă pe sateliți (rămân cum sunt)")
	return valoare


def textPort(comanda):
	"""valoarea lui commitedDiseqcCommand (NimManager.py:1186-1187) spusa simplu"""
	if comanda in (None, "", "none"):
		return _("fără")
	for port in PORTURI:
		if COMANDA_PORT[port] == comanda:
			return port
	try:
		numar = int(comanda)
	except (TypeError, ValueError):
		return comanda
	if 0xF0 <= numar <= 0xFF:
		return _("Intrarea %d") % (numar - 0xF0 + 1)
	return comanda


def alegeriPort():
	"""alegerile comenzii DiSEqC 1.0/1.1 a unui LNB, in valorile nucleului (NimManager.py:1186-1187)"""
	rez = [("none", textPort("none"))]
	for port in PORTURI:
		rez.append((COMANDA_PORT[port], port))
	for y in range(16):
		rez.append((str(0xF0 | y), textPort(str(0xF0 | y))))
	return rez


def textDiseqc(lnb):
	"""randul „Port DiSEqC” cand nu se poate schimba de aici"""
	if lnb.get("diseqc") == "1_2":
		return _("1.2, motor")
	if lnb.get("diseqc") == "none":
		return _("fără")
	if lnb.get("toneburst") in ("A", "B") and lnb.get("comanda") in (None, "", "none"):
		return _("toneburst %s") % lnb["toneburst"]
	return textPort(lnb.get("comanda"))


def _numeSatelit(nm, orbital):
	try:
		nume = nm.getSatName(orbital)
	except Exception:
		nume = ""
	if not nume or nume == "N/A":
		# satelit fara nume in satellites.xml: pozitia in limba meniului (Components/HdsGrade.py)
		try:
			from Components.HdsGrade import pozitieOrbitala
		except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
			from HdsGrade import pozitieOrbitala
		return pozitieOrbitala(orbital) or str(orbital)
	return nume


def _listaNume(nm, orbitali):
	nume = [_numeSatelit(nm, o) for o in orbitali]
	if len(nume) <= 2:
		return ", ".join(nume)
	return _("%s și încă %d") % (", ".join(nume[:2]), len(nume) - 2)


# ------------------------------------------------------------------ plimbarea prin arborele config

def _esteSectiune(nod):
	"""ConfigSubsection: are `content` in __dict__ (config.py:1552-1556); __getattr__ al ei arunca KeyError, deci
	nu se foloseste hasattr"""
	d = getattr(nod, "__dict__", None)
	return isinstance(d, dict) and "content" in d and isinstance(getattr(d["content"], "items", None), dict)


def _esteNimic(nod):
	"""ConfigNothing: locul lui `advanced` in modul simplu (NimManager.py:1476)"""
	try:
		from Components.config import ConfigNothing
	except Exception:
		return type(nod).__name__ == "ConfigNothing"
	return isinstance(nod, ConfigNothing)


def _intSauNimic(text):
	try:
		return int(text)
	except (TypeError, ValueError):
		return None


def _copil(nod, parte):
	if _esteSectiune(nod):
		return nod.__dict__["content"].items.get(parte)
	if isinstance(nod, dict):
		numar = _intSauNimic(parte)
		if numar is not None and dict.__contains__(nod, numar):
			return dict.__getitem__(nod, numar)
		if dict.__contains__(nod, parte):
			return dict.__getitem__(nod, parte)
		return None
	if isinstance(nod, list):
		numar = _intSauNimic(parte)
		if numar is not None and 0 <= numar < len(nod):
			return list.__getitem__(nod, numar)
		return None
	return None


def element(radacina, cale):
	"""elementul de la `cale` (ex. „advanced.lnb.33.lofl”) sub config.Nims[n], sau None"""
	nod = radacina
	for parte in cale.split("."):
		nod = _copil(nod, parte)
		if nod is None:
			return None
	return nod


def _cheieSortare(cheie):
	numar = _intSauNimic(cheie)
	return (0, numar, "") if numar is not None else (1, 0, str(cheie))


def frunze(nod, prefix=""):
	"""(cale, element) pentru fiecare frunza de sub `nod`, in ordine stabila; ConfigNothing e si el frunza"""
	if _esteSectiune(nod):
		copii = nod.__dict__["content"].items
		for nume in sorted(copii, key=_cheieSortare):
			for x in frunze(copii[nume], prefix + "." + nume if prefix else nume):
				yield x
	elif isinstance(nod, dict):
		for cheie in sorted(dict.keys(nod), key=_cheieSortare):
			for x in frunze(dict.__getitem__(nod, cheie), prefix + "." + str(cheie) if prefix else str(cheie)):
				yield x
	elif isinstance(nod, list):
		for i in range(len(nod)):
			for x in frunze(list.__getitem__(nod, i), prefix + "." + str(i) if prefix else str(i)):
				yield x
	else:
		yield prefix, nod


def textElement(el):
	"""valoarea ca text, ca in settings (tostring, config.py:82-84 si subclasele)"""
	return el.tostring(el.value)


def amprenta(cfg):
	"""sha1 pe toate valorile tunerului: pagina web o trimite inapoi la aplicare, ca un plan facut pe o stare
	care s-a schimbat intre timp (de pe televizor sau din „Setări tuner”) sa nu mai fie aplicat"""
	h = hashlib.sha1()
	for cale, el in frunze(cfg):
		if _esteNimic(el):
			continue
		try:
			h.update(("%s=%s\n" % (cale, textElement(el))).encode("utf-8", "replace"))
		except Exception:
			h.update(("%s=?\n" % cale).encode("utf-8"))
	return h.hexdigest()


def _valoare(sectiune, nume, implicit=None):
	el = _copil(sectiune, nume)
	if el is None or _esteNimic(el):
		return implicit
	try:
		return el.value
	except Exception:
		return implicit


def _nimmanager():
	from Components.NimManager import nimmanager
	return nimmanager


# ------------------------------------------------------------------ oscilatoare si calculul nucleului

def oscilatoareKhz(lnb):
	"""(jos, sus, prag) in kHz, exact cum le pune nucleul pentru tipul LNB-ului (NimManager.py:304-342); None la
	Unicable (acolo frecventa intermediara o alege comutatorul, iar nucleul nu verifica 900-2200, sec.cpp:216)"""
	tip = lnb.get("tip")
	if tip == TIP_UNIVERSAL:
		return 9750000, 10600000, 11700000
	if tip == TIP_BANDA_C:
		return 5150000, 5150000, 5150000
	if tip == TIP_UN_OSCILATOR:
		return OSCILATOR_10750 * 1000, OSCILATOR_10750 * 1000, PRAG_MEREU_JOS * 1000
	if tip == TIP_PERSONALIZAT:
		return int(lnb.get("lofl") or 0) * 1000, int(lnb.get("lofh") or 0) * 1000, int(lnb.get("prag") or 0) * 1000
	return None


def calcul(osc, frecventa_khz, polarizare, tensiune="polarization", ton="band"):
	"""ce face nucleul pentru un transponder (sec.cpp:218-224, 374-402), cu frecventa in kHz si polarizarea ca in
	satellites.xml (0 H, 1 V, 2 L, 3 R; bitul „vertical” e 1, frontendparms.h:16)"""
	jos, sus, prag = osc
	banda_sus = frecventa_khz > prag
	oscilator = sus if banda_sus else jos
	fi = abs(int(frecventa_khz) - int(oscilator))
	vertical = bool(int(polarizare) & 1)
	if tensiune == "13V":
		volti = 13
	elif tensiune == "18V":
		volti = 18
	else:
		volti = 13 if vertical else 18
	if ton == "on":
		ton_pornit = True
	elif ton == "off":
		ton_pornit = False
	else:
		ton_pornit = banda_sus
	return {"banda_sus": banda_sus, "oscilator_khz": oscilator, "fi_khz": fi,
		"acceptat": FI_MIN_KHZ <= fi <= FI_MAX_KHZ, "volti": volti, "ton": ton_pornit}


def _transpondere(nm, orbital):
	try:
		return list(nm.getTransponders(orbital) or [])
	except Exception:
		return []


def verificaFI(lnb, nm, sateliti=None):
	"""cate transpondere cunoscute (satellites.xml, nimmanager.getTransponders, frecventa in kHz) se pot acorda
	cu LNB-ul, pe TOT setul de sateliti pe care il serveste (la motor: toti)"""
	rez = {"total_tp": 0, "bune_tp": 0, "total_sat": 0, "bune_sat": 0, "pe_satelit": {}, "cunoscut": True}
	osc = oscilatoareKhz(lnb)
	if osc is None:
		rez["cunoscut"] = False
		return rez
	for orbital in (lnb.get("sateliti") if sateliti is None else sateliti):
		tp = _transpondere(nm, orbital)
		if not tp:
			continue
		bune = 0
		for t in tp:
			if calcul(osc, t[1], t[3])["acceptat"]:
				bune += 1
		rez["pe_satelit"][orbital] = (bune, len(tp))
		rez["total_tp"] += len(tp)
		rez["bune_tp"] += bune
		rez["total_sat"] += 1
		if bune:
			rez["bune_sat"] += 1
	return rez


def _polLitera(polarizare):
	return {0: "H", 1: "V", 2: "L", 3: "R"}.get(int(polarizare), "?")


def probaDeCalcul(lnb, nm, serviciu=None, model=None):
	"""textul randului „Probă de calcul”: un transponder adevarat de pe un satelit al LNB-ului si ce face nucleul
	cu el. Se ia canalul care ruleaza, daca e pe acest LNB, altfel un satelit cunoscut. Cu `model`, numai satelitii
	pe care LNB-ul chiar ii serveste (un satelit cu LNB-ul lui anume nu trece prin „toti satelitii”, R1)."""
	osc = oscilatoareKhz(lnb)
	if osc is None:
		return _("LNB-ul Unicable se configurează din Setări tuner.")
	sateliti = list(lnb.get("sateliti") or [])
	if model is not None:
		sateliti = satelitiServiti(model, lnb) or sateliti
	alegere = None
	if serviciu and serviciu.get("orbital") in sateliti and serviciu.get("frecventa"):
		alegere = (serviciu["orbital"], serviciu["frecventa"], serviciu.get("polarizare", 0))
	if alegere is None:
		ordine = [o for o in PREFERATI if o in sateliti] + [o for o in sateliti if o not in PREFERATI]
		prima = None
		for orbital in ordine:
			tp = sorted(_transpondere(nm, orbital), key=lambda t: t[1])
			if tp and prima is None:
				prima = (orbital, tp[0][1], tp[0][3])
			for t in tp:
				if calcul(osc, t[1], t[3])["acceptat"]:
					alegere = (orbital, t[1], t[3])
					break
			if alegere is not None:
				break
		if alegere is None:
			alegere = prima
	if alegere is None:
		return _("Nu știu niciun transponder de pe acești sateliți.")
	orbital, frecventa, polarizare = alegere
	tensiune = lnb.get("tensiune") if lnb.get("tensiune") != DIFERA else "polarization"
	ton = lnb.get("ton") if lnb.get("ton") != DIFERA else "band"
	c = calcul(osc, frecventa, polarizare, tensiune, ton)
	cap = _numeSatelit(nm, orbital)
	if not c["acceptat"]:
		return _("%s, %d MHz %s: %s") % (cap, frecventa // 1000, _polLitera(polarizare),
			_("nu se poate acorda (FI în afara 900-2200 MHz)"))
	# tonul cu msgid-urile „on” / „off” (traduse in toate limbile: ro „pornit” /
	# „oprit”); „oprit” era comun cu CamSetup.py si se traducea „stopped” („tone stopped”)
	return _("%s, %d MHz %s: FI %d MHz, %s, ton %s") % (cap, frecventa // 1000, _polLitera(polarizare),
		c["fi_khz"] // 1000, "%d V" % c["volti"], _("on") if c["ton"] else _("off"))


# ------------------------------------------------------------------ citirea tunerului

def _lnb(**campuri):
	lnb = {"id": "", "eticheta": "", "numar": None, "port": None, "sateliti": [], "toti": False,
		"tip": TIP_UNIVERSAL, "lofl": 9750, "lofh": 10600, "prag": 11700,
		"tensiune": "polarization", "ton": "band", "tensiune_marita": False,
		"diseqc": "none", "comanda": "none", "toneburst": "none", "fast": False,
		"editabil_tip": True, "editabil_rest": False, "editabil_port": False}
	lnb.update(campuri)
	return lnb


def _tipDinConfig(sectiune):
	lof = _valoare(sectiune, "lof", "universal_lnb")
	lofl = int(_valoare(sectiune, "lofl", 9750) or 0)
	lofh = int(_valoare(sectiune, "lofh", 10600) or 0)
	prag = int(_valoare(sectiune, "threshold", 11700) or 0)
	if lof == "universal_lnb":
		return TIP_UNIVERSAL, 9750, 10600, 11700
	if lof == "c_band":
		return TIP_BANDA_C, 5150, 5150, 5150
	if lof == "unicable":
		return TIP_UNICABLE, lofl, lofh, prag
	if lofl == lofh == OSCILATOR_10750 and prag == PRAG_MEREU_JOS:
		return TIP_UN_OSCILATOR, lofl, lofh, prag
	return TIP_PERSONALIZAT, lofl, lofh, prag


def _unic(valori):
	valori = set(valori)
	if len(valori) == 1:
		return valori.pop()
	return DIFERA


def _citesteSimplu(model, cfg, nm):
	dm = _valoare(cfg, "diseqcMode", "single")
	model["diseqcMode"] = dm
	fast = False
	tensiune, ton = "polarization", "band"
	if dm in ("diseqc_a_b", "diseqc_a_b_c_d"):
		# numai aici trimite update() fastDiSEqC si setVoltageTone (NimManager.py:199-213)
		fast = bool(_valoare(cfg, "simpleDiSEqCOnlyOnSatChange", False))
		if not _valoare(cfg, "simpleDiSEqCSetVoltageTone", True):
			tensiune, ton = "13V", "off"
	if dm == "positioner":
		sateliti = [x[0] for x in nm.satList]
		model["lnburi"].append(_lnb(id=MOTOR, eticheta=_("Motor: toți sateliții"), numar=LNB_MOTOR, sateliti=sateliti,
			toti=True, diseqc="1_2", tensiune=tensiune, ton=ton))
		model["antena"] = _("motor USALS, toți sateliții")
		model["motor"] = True
		return
	porturi = {"single": ("A",), "toneburst_a_b": ("A", "B"), "diseqc_a_b": ("A", "B"),
		"diseqc_a_b_c_d": PORTURI}.get(dm, ())
	trimite = bool(_valoare(cfg, "simpleSingleSendDiSEqC", False))
	for port in porturi:
		el = _copil(cfg, "diseqc" + port)
		try:
			orbital = el.orbital_position
		except Exception:
			orbital = None
		if orbital is None or orbital == NIMIC_CONECTAT:
			continue
		if dm == "single":
			diseqc, comanda, toneburst = ("1_0", "AA", "none") if trimite else ("none", "none", "none")
			eticheta = _numeSatelit(nm, orbital)
		elif dm == "toneburst_a_b":
			diseqc, comanda, toneburst = "1_0", "none", port
			eticheta = _("Port %s: %s") % (port, _numeSatelit(nm, orbital))
		else:
			diseqc, comanda, toneburst = "1_0", COMANDA_PORT[port], "none"
			eticheta = _("Port %s: %s") % (port, _numeSatelit(nm, orbital))
		model["lnburi"].append(_lnb(id=port, eticheta=eticheta, numar=NUMAR_PORT[port], port=port,
			sateliti=[orbital], diseqc=diseqc, comanda=comanda, toneburst=toneburst, fast=fast,
			tensiune=tensiune, ton=ton))
	if dm == "single":
		model["antena"] = _("un singur LNB, cu DiSEqC pe portul A") if trimite else _("un singur LNB, fără DiSEqC")
	elif dm == "toneburst_a_b":
		model["antena"] = _("toneburst A/B")
	elif dm == "diseqc_a_b":
		model["antena"] = _("comutator DiSEqC A/B")
	elif dm == "diseqc_a_b_c_d":
		model["antena"] = _("comutator DiSEqC A/B/C/D")


def _citesteAvansat(model, cfg, nm):
	adv = _copil(cfg, "advanced")
	sat = _copil(adv, "sat") if adv is not None else None
	lnburi = _copil(adv, "lnb") if adv is not None else None
	if sat is None or lnburi is None:
		model["motiv"] = _("Nu pot citi setările tunerului %s.") % model["litera"]
		return
	pe_lnb = {}
	toti = set()
	# aceeasi grupare ca updateAdvanced (NimManager.py:267-283)
	for x in TOTI_SATELITII:
		s = _copil(sat, str(x))
		numar = _intSauNimic(_valoare(s, "lnb", "0")) if s is not None else 0
		if numar:
			pe_lnb.setdefault(numar, []).extend([y[0] for y in nm.satList])
			toti.add(numar)
	for y in nm.satList:
		s = _copil(sat, str(y[0]))
		numar = _intSauNimic(_valoare(s, "lnb", "0")) if s is not None else 0
		if numar:
			pe_lnb.setdefault(numar, []).append(y[0])
	for numar in sorted(pe_lnb):
		sectiune = _copil(lnburi, str(numar))
		if sectiune is None or not _esteSectiune(sectiune):
			continue
		tip, lofl, lofh, prag = _tipDinConfig(sectiune)
		if numar > 32:
			sati = [_copil(sat, str(3604 - (36 - numar)))]
		else:
			sati = [_copil(sat, str(o)) for o in pe_lnb[numar]]
		sati = [s for s in sati if s is not None]
		dm = _valoare(sectiune, "diseqcMode", "none")
		if numar in toti:
			eticheta = _("Motor: toți sateliții") if numar == LNB_MOTOR else _("Motor (LNB %d): toți sateliții") % numar
			model["motor"] = True
		else:
			eticheta = _("LNB %d: %s") % (numar, _listaNume(nm, pe_lnb[numar]))
			if dm == "1_2":
				model["motor"] = True
		model["lnburi"].append(_lnb(id=str(numar), eticheta=eticheta, numar=numar, sateliti=list(pe_lnb[numar]),
			toti=numar in toti, tip=tip, lofl=lofl, lofh=lofh, prag=prag,
			tensiune=_unic([_valoare(s, "voltage", "polarization") for s in sati]) if sati else "polarization",
			ton=_unic([_valoare(s, "tonemode", "band") for s in sati]) if sati else "band",
			tensiune_marita=bool(_valoare(sectiune, "increased_voltage", False)),
			diseqc=dm, comanda=_valoare(sectiune, "commitedDiseqcCommand", "none"),
			toneburst=_valoare(sectiune, "toneburst", "none"), fast=bool(_valoare(sectiune, "fastDiseqc", False)),
			editabil_tip=tip != TIP_UNICABLE, editabil_rest=tip != TIP_UNICABLE,
			editabil_port=tip != TIP_UNICABLE and dm in ("1_0", "1_1")))
	if len(model["lnburi"]) == 1:
		model["antena"] = model["lnburi"][0]["eticheta"]
	elif model["lnburi"]:
		# numarul dupa substantiv: in romana „20 de LNB-uri”, dar „2 LNB-uri”; asa textul e bun pentru orice numar
		model["antena"] = _("LNB-uri: %d") % len(model["lnburi"])


def tunereSatelit(nm=None):
	nm = nm or _nimmanager()
	try:
		return list(nm.getNimListOfType("DVB-S"))
	except Exception:
		return []


def numeTuner(slot, nm=None):
	nm = nm or _nimmanager()
	try:
		nume = nm.getNimName(slot)
	except Exception:
		nume = ""
	return "%s: %s" % (chr(ord("A") + slot), nume) if nume else chr(ord("A") + slot)


def citeste(slot, nm=None):
	"""modelul tunerului, acelasi pentru ecran si pentru pagina web"""
	nm = nm or _nimmanager()
	litera = chr(ord("A") + slot)
	model = {"slot": slot, "litera": litera, "nume": numeTuner(slot, nm), "mod": "nothing", "diseqcMode": "",
		"editabil": False, "motiv": "", "diseqc13V": False, "lnburi": [], "antena": "", "amprenta": "",
		"motor": False}
	try:
		cfg = nm.getNimConfig(slot)
		model["amprenta"] = amprenta(cfg)
		mod = _valoare(cfg, "configMode", "nothing")
		model["mod"] = mod
		model["diseqc13V"] = bool(_valoare(cfg, "diseqc13V", False))
		if mod == "simple":
			_citesteSimplu(model, cfg, nm)
		elif mod == "advanced":
			_citesteAvansat(model, cfg, nm)
		elif mod in ("equal", "loopthrough", "satposdepends"):
			spre = _intSauNimic(_valoare(cfg, "connectedTo", ""))
			model["motiv"] = _("Tunerul %s folosește setările tunerului %s.") % (
				litera, chr(ord("A") + spre) if spre is not None else "?")
		else:
			model["motiv"] = _("Tunerul %s nu e configurat. Configurează-l întâi din Setări tuner.") % litera
	except Exception as eroare:
		print("[HdsLnb] citirea tunerului %s: %s" % (litera, eroare))
		model["motiv"] = _("Nu pot citi setările tunerului %s.") % litera
		model["lnburi"] = []
	if not model["motiv"] and not model["lnburi"]:
		model["motiv"] = _("Pe tunerul %s nu e legat niciun satelit. Alege sateliții din Setări tuner.") % litera
	model["editabil"] = not model["motiv"]
	return model


def textMod(model):
	if model["mod"] == "simple":
		return _("%s (mod simplu)") % model["nume"]
	if model["mod"] == "advanced":
		return _("%s (mod avansat)") % model["nume"]
	return model["nume"]


def lnbPentruSatelit(slot, orbital, nm=None, model=None):
	"""LNB-ul care serveste un satelit, cu „toti satelitii” (sat[3601..3604]) inclus; alocarea anume a
	satelitului are intaietate. Bara de informatii are aceeasi regula scrisa la ea (HdsCommon._adv_sat_lnb, fara
	import de aici: convertorul citeste la fiecare schimbare a barei); proba test_V3_bara_si_ecranul_dau_acelasi_lnb
	le tine egale."""
	model = model or citeste(slot, nm)
	anume = [l for l in model["lnburi"] if orbital in l["sateliti"] and not l["toti"]]
	if anume:
		return anume[0]
	toate = [l for l in model["lnburi"] if orbital in l["sateliti"]]
	return toate[0] if toate else None


def _lnbDupaSatelit(model):
	"""orbital -> id-ul LNB-ului care il serveste, dupa regula lui lnbPentruSatelit (primul LNB cu alocare anume,
	altfel primul „toti satelitii”), socotit o singura data pentru tot tunerul"""
	ales = {}
	for toti in (False, True):
		for lnb in model["lnburi"]:
			if bool(lnb["toti"]) == toti:
				for orbital in lnb["sateliti"]:
					ales.setdefault(orbital, lnb["id"])
	return ales


def satelitiServiti(model, lnb):
	"""satelitii pe care LNB-ul chiar ii serveste la acord: cei pentru care lnbPentruSatelit il alege. Un satelit
	cu LNB-ul lui anume nu trece prin „toti satelitii”, desi nucleul il pune in ambele (NimManager.py:267-283; canTune
	pastreaza primul LNB la egalitate, sec.cpp:230). Proba de semnal, numaratoarea FI si avertismentul canalului se
	fac numai pe ei. In ordinea listei LNB-ului, fara dubluri."""
	ales = _lnbDupaSatelit(model)
	rez, vazuti = [], set()
	for orbital in lnb["sateliti"]:
		if orbital not in vazuti and ales.get(orbital) == lnb["id"]:
			vazuti.add(orbital)
			rez.append(orbital)
	return rez


def satelitiAtinsi(model, cai):
	"""satelitii al caror drum de acord il schimba scrierea cailor date (relative la config.Nims[slot]): cei serviti
	de un LNB schimbat (advanced.lnb.N.*, iar advanced.sat.3601-3604.* sunt tensiunea si tonul LNB-urilor 33-36,
	ca in _tintaAvansat), un satelit cu setarile lui (advanced.sat.X.*) si, la orice alta cale (modul, comenzile la
	13 V, modul simplu, alocarea „toti satelitii”), toti satelitii tunerului"""
	toti = set()
	for lnb in model["lnburi"]:
		toti.update(lnb["sateliti"])
	numere, rez = set(), set()
	for cale in cai:
		parti = cale.split(".")
		numar = _intSauNimic(parti[2]) if len(parti) > 3 and parti[0] == "advanced" else None
		if numar is not None and parti[1] == "lnb":
			numere.add(numar)
		elif numar is not None and parti[1] == "sat" and numar in TOTI_SATELITII and parti[3] != "lnb":
			numere.add(numar - 3604 + 36)
		elif numar is not None and parti[1] == "sat" and numar not in TOTI_SATELITII:
			rez.add(numar)
		else:
			return sorted(toti)
	for lnb in model["lnburi"]:
		if lnb["numar"] in numere:
			rez.update(satelitiServiti(model, lnb))
	return sorted(rez)


def tunereCuAcelasiLnb(nm, slot, cu_motor=False):
	"""sloturile ale caror frontenduri folosesc LNB-urile tunerului `slot`: el insusi, tunerele „equal to” si cele
	legate (masca LNB-ului, NimManager.py:47-56 si 291-299) si, cand e vorba de LNB-ul cu motor, al doilea cablu al
	motorului (satposdepends, 86-89 si 363-366). Dictionarele sunt cele facute de ultimul sec.update() (143-181)."""
	rez = set([slot])
	sec = getattr(nm, "sec", None)
	for nume in (("equal", "linked", "satposdepends") if cu_motor else ("equal", "linked")):
		try:
			rez.update(int(x) for x in (getattr(sec, nume, None) or {}).get(slot, []))
		except Exception:
			pass
	return rez


def receptorCuMotor(nm=None, model=None):
	"""un motor pe oricare tuner de satelit al receptorului (`model` = tunerul deja citit, ca sa nu se citeasca iar)"""
	nm = nm or _nimmanager()
	if model is not None and model.get("motor"):
		return True
	for slot in tunereSatelit(nm):
		if model is not None and slot == model.get("slot"):
			continue
		try:
			if citeste(slot, nm).get("motor"):
				return True
		except Exception:
			continue
	return False


def avertismentMotor():
	"""sec.update() uita pozitia motorului pe TOATE frontendurile (sec.cpp:1020-1021), oricare tuner s-ar fi
	schimbat, deci comanda pleaca din nou la prima acordare pe motor: la proba, daca proba e pe motor, altfel la
	urmatoarea schimbare de canal"""
	return _("După aplicare, receptorul trimite din nou comanda motorului la prima acordare pe motor (proba de "
		"semnal sau următoarea schimbare de canal). Dacă antena e deja acolo, abia se mișcă.")


# ------------------------------------------------------------------ ciorna si planul

def alegeriDinModel(model):
	alegeri = {"diseqc13V": model["diseqc13V"], "lnb": {}}
	for lnb in model["lnburi"]:
		alegeri["lnb"][lnb["id"]] = dict((c, lnb[c]) for c in CAMPURI_LNB)
	return alegeri


def _lnbCuAlegeri(lnb, alegere):
	nou = dict(lnb)
	nou.update(alegere)
	if nou["tip"] == TIP_UNIVERSAL:
		nou["lofl"], nou["lofh"], nou["prag"] = 9750, 10600, 11700
	elif nou["tip"] == TIP_BANDA_C:
		nou["lofl"], nou["lofh"], nou["prag"] = 5150, 5150, 5150
	elif nou["tip"] == TIP_UN_OSCILATOR:
		nou["lofl"], nou["lofh"], nou["prag"] = OSCILATOR_10750, OSCILATOR_10750, PRAG_MEREU_JOS
	return nou


def lnbDupaAlegeri(model, alegeri, lnb_id):
	for lnb in model["lnburi"]:
		if lnb["id"] == lnb_id:
			return _lnbCuAlegeri(lnb, alegeri["lnb"].get(lnb_id, {}))
	return None


def _lnbSchimbat(lnb, nou):
	if nou["tip"] != lnb["tip"]:
		return True
	if nou["tip"] == TIP_PERSONALIZAT and (nou["lofl"], nou["lofh"], nou["prag"]) != (lnb["lofl"], lnb["lofh"], lnb["prag"]):
		return True
	for camp in ("tensiune", "ton", "tensiune_marita", "comanda"):
		if nou[camp] != lnb[camp]:
			return True
	return False


def schimbate(model, alegeri):
	"""id-urile LNB-urilor care difera fata de tuner"""
	rez = []
	for lnb in model["lnburi"]:
		if _lnbSchimbat(lnb, _lnbCuAlegeri(lnb, alegeri["lnb"].get(lnb["id"], {}))):
			rez.append(lnb["id"])
	return rez


def areSchimbari(model, alegeri):
	return bool(schimbate(model, alegeri)) or bool(alegeri.get("diseqc13V")) != bool(model["diseqc13V"])


def valideaza(model, alegeri):
	"""greseala de scriere a omului, spusa inainte de previzualizare, sau None"""
	for lnb in model["lnburi"]:
		nou = _lnbCuAlegeri(lnb, alegeri["lnb"].get(lnb["id"], {}))
		if nou["tip"] != TIP_PERSONALIZAT:
			continue
		if int(nou["lofl"] or 0) <= 0:
			return _("Oscilatorul de jos nu poate fi 0.")
		if int(nou["lofh"] or 0) < int(nou["lofl"] or 0):
			return _("Oscilatorul de sus nu poate fi mai mic decât cel de jos.")
	return None


def _textDa(valoare):
	# aceleasi cuvinte ca ConfigYesNo (config.py:439)
	return _("yes") if valoare else _("no")


def _tintaConversie(model, alegeri, cfg, nm, tinta, rezumat, oprire):
	"""simplu -> avansat, cu TOATE campurile scrise explicit: la trecere, `advanced` ia valorile vechi ramase in
	settings (config.py:1558-1571), deci nimic nu se lasa pe implicit"""
	dm = model["diseqcMode"]
	pe_lnb = {}
	for lnb in model["lnburi"]:
		numar = lnb["numar"]
		if not lnb["toti"]:
			for orbital in lnb["sateliti"]:
				if orbital in pe_lnb:
					oprire.append(_("Același satelit e pe două porturi (%s). Schimbă întâi din Setări tuner.")
						% _numeSatelit(nm, orbital))
				pe_lnb[orbital] = numar
	tinta.append(("configMode", "advanced"))
	for y in nm.satList:
		tinta.append(("advanced.sat.%d.lnb" % y[0], str(pe_lnb.get(y[0], 0))))
	are_motor = any(l["toti"] for l in model["lnburi"])
	for x in TOTI_SATELITII:
		tinta.append(("advanced.sat.%d.lnb" % x, str(LNB_MOTOR) if (are_motor and x == 3601) else "0"))
	for lnb in model["lnburi"]:
		nou = _lnbCuAlegeri(lnb, alegeri["lnb"].get(lnb["id"], {}))
		baza = "advanced.lnb.%d." % lnb["numar"]
		tinta.extend(_campuriLof(baza, nou))
		if lnb["numar"] > 32:
			tinta.append((baza + "diseqcMode", "1_2"))
		else:
			tinta.append((baza + "diseqcMode", lnb["diseqc"]))
		tinta.append((baza + "increased_voltage", "false"))
		tinta.append((baza + "toneburst", lnb["toneburst"]))
		tinta.append((baza + "commitedDiseqcCommand", lnb["comanda"]))
		tinta.append((baza + "fastDiseqc", "true" if lnb["fast"] else "false"))
		tinta.append((baza + "sequenceRepeat", "false"))
		tinta.append((baza + "commandOrder1_0", "ct"))
		tinta.append((baza + "commandOrder", "ct"))
		tinta.append((baza + "uncommittedDiseqcCommand", "0"))
		tinta.append((baza + "diseqcRepeats", "none"))
		tinta.append((baza + "prio", "-1"))
		if lnb["toti"]:
			for camp in ("longitude", "longitudeOrientation", "latitude", "latitudeOrientation", "powerMeasurement",
					"powerThreshold", "turningSpeed", "fastTurningBegin", "fastTurningEnd"):
				el = _copil(cfg, camp)
				if el is not None and not _esteNimic(el):
					tinta.append((baza + camp, textElement(el)))
			pozitii = [3601]
		else:
			pozitii = lnb["sateliti"]
		for orbital in pozitii:
			s = "advanced.sat.%d." % orbital
			tinta.append((s + "voltage", lnb["tensiune"]))
			tinta.append((s + "tonemode", lnb["ton"]))
			tinta.append((s + "usals", "true"))
			tinta.append((s + "rotorposition", "1"))
		if nou["tip"] != lnb["tip"] or nou["tip"] == TIP_PERSONALIZAT:
			rezumat.append(_("%s: %s în loc de %s") % (lnb["eticheta"], _textTipCuCifre(nou), textTip(lnb["tip"])))
	if are_motor:
		rezumat.insert(0, _("Tunerul trece din modul simplu în modul avansat. Sateliții și motorul rămân aceiași."))
	else:
		rezumat.insert(0, _("Tunerul trece din modul simplu în modul avansat, cu aceiași sateliți."))
	if dm not in ("single", "toneburst_a_b", "diseqc_a_b", "diseqc_a_b_c_d", "positioner"):
		oprire.append(_("Nu pot citi setările tunerului %s.") % model["litera"])


def _textTipCuCifre(lnb):
	if lnb["tip"] == TIP_PERSONALIZAT:
		return "%s %d/%d, %s %d" % (textTip(lnb["tip"]), int(lnb["lofl"]), int(lnb["lofh"]), _("prag"), int(lnb["prag"]))
	return textTip(lnb["tip"])


def _campuriLof(baza, nou):
	tip = nou["tip"]
	if tip == TIP_UNIVERSAL:
		return [(baza + "lof", "universal_lnb"), (baza + "lofl", "9750"), (baza + "lofh", "10600"),
			(baza + "threshold", "11700")]
	if tip == TIP_BANDA_C:
		return [(baza + "lof", "c_band"), (baza + "lofl", "5150"), (baza + "lofh", "5150"),
			(baza + "threshold", "5150")]
	return [(baza + "lof", "user_defined"), (baza + "lofl", str(int(nou["lofl"]))),
		(baza + "lofh", str(int(nou["lofh"]))), (baza + "threshold", str(int(nou["prag"])))]


def _tintaAvansat(model, alegeri, tinta, rezumat):
	for lnb in model["lnburi"]:
		nou = _lnbCuAlegeri(lnb, alegeri["lnb"].get(lnb["id"], {}))
		if not _lnbSchimbat(lnb, nou):
			continue
		baza = "advanced.lnb.%d." % lnb["numar"]
		if lnb["numar"] > 32:
			pozitii = [3604 - (36 - lnb["numar"])]
		else:
			pozitii = list(lnb["sateliti"])
		if nou["tip"] != lnb["tip"] or (nou["tip"] == TIP_PERSONALIZAT and
				(nou["lofl"], nou["lofh"], nou["prag"]) != (lnb["lofl"], lnb["lofh"], lnb["prag"])):
			if lnb["tip"] != TIP_UNICABLE:
				tinta.extend(_campuriLof(baza, nou))
				rezumat.append(_("%s: %s în loc de %s") % (lnb["eticheta"], _textTipCuCifre(nou), _textTipCuCifre(lnb)))
		if nou["tensiune"] != lnb["tensiune"] and nou["tensiune"] != DIFERA:
			for orbital in pozitii:
				tinta.append(("advanced.sat.%d.voltage" % orbital, nou["tensiune"]))
			rezumat.append(_("%s: %s în loc de %s") % ("%s, %s" % (lnb["eticheta"], _("Tensiune")),
				textTensiune(nou["tensiune"]), textTensiune(lnb["tensiune"])))
		if nou["ton"] != lnb["ton"] and nou["ton"] != DIFERA:
			for orbital in pozitii:
				tinta.append(("advanced.sat.%d.tonemode" % orbital, nou["ton"]))
			rezumat.append(_("%s: %s în loc de %s") % ("%s, %s" % (lnb["eticheta"], _("Ton 22 kHz")),
				textTon(nou["ton"]), textTon(lnb["ton"])))
		if bool(nou["tensiune_marita"]) != bool(lnb["tensiune_marita"]):
			tinta.append((baza + "increased_voltage", "true" if nou["tensiune_marita"] else "false"))
			rezumat.append(_("%s: %s în loc de %s") % ("%s, %s" % (lnb["eticheta"], _("Tensiune mărită (cablu lung)")),
				_textDa(nou["tensiune_marita"]), _textDa(lnb["tensiune_marita"])))
		if nou["comanda"] != lnb["comanda"] and lnb["editabil_port"]:
			tinta.append((baza + "commitedDiseqcCommand", nou["comanda"]))
			rezumat.append(_("%s: %s în loc de %s") % ("%s, %s" % (lnb["eticheta"], _("Port DiSEqC")),
				textPort(nou["comanda"]), textPort(lnb["comanda"])))


def planifica(model, alegeri, nm=None, serviciu=None):
	"""Ce s-ar scrie, fara sa se atinga nimic. Planul are:
	tinta       - lista ordonata (cale, text) sub config.Nims[slot], cu TOATE campurile starii noi;
	schimbari   - (cale, inainte, dupa) pentru fiecare cale din tinta care difera (inainte None = camp nou);
	rezumat     - randurile pentru om; avertismente; oprire (de ce nu se poate aplica, gol daca se poate);
	sateliti    - orbitalii serviti de LNB-urile schimbate (proba de semnal se face numai pe ei)."""
	nm = nm or _nimmanager()
	cfg = nm.getNimConfig(model["slot"])
	plan = {"slot": model["slot"], "tinta": [], "schimbari": [], "rezumat": [], "avertismente": [], "oprire": "",
		"trece_in_avansat": False, "amprenta": model["amprenta"], "sateliti": [], "lnb_schimbate": [],
		"motor": bool(model.get("motor")), "motor_schimbat": False, "fel": "schimbare"}
	if not model["editabil"]:
		plan["oprire"] = model["motiv"]
		return plan
	greseala = valideaza(model, alegeri)
	if greseala:
		plan["oprire"] = greseala
		return plan
	ids = schimbate(model, alegeri)
	plan["lnb_schimbate"] = ids
	# LNB-ul cu motor e intre cele schimbate (sau comenzile la 13 V, care se aplica tuturor): atunci si al doilea
	# cablu al motorului foloseste schimbarea (NimManager.py:86-89, 363-366)
	pe_id = dict((l["id"], l) for l in model["lnburi"])
	plan["motor_schimbat"] = any(pe_id[i]["toti"] or pe_id[i]["diseqc"] == "1_2" for i in ids) or \
		(bool(alegeri.get("diseqc13V")) != bool(model["diseqc13V"]) and bool(model.get("motor")))
	legate = tunereCuAcelasiLnb(nm, model["slot"], plan["motor_schimbat"])
	tinta, rezumat, oprire = plan["tinta"], plan["rezumat"], []
	if bool(alegeri.get("diseqc13V")) != bool(model["diseqc13V"]):
		tinta.append(("diseqc13V", "true" if alegeri.get("diseqc13V") else "false"))
		rezumat.append(_("%s: %s în loc de %s") % ("%s, %s" % (_("Tuner"), _("Comenzi DiSEqC la 13 V")),
			_textDa(alegeri.get("diseqc13V")), _textDa(model["diseqc13V"])))
		# se aplica tuturor satelitilor tunerului
		for lnb in model["lnburi"]:
			plan["sateliti"].extend(lnb["sateliti"])
	if model["mod"] == "simple":
		conversie = [i for i in ids if _lnbCuAlegeri(dict((l["id"], l) for l in model["lnburi"])[i],
			alegeri["lnb"].get(i, {}))["tip"] != TIP_UNIVERSAL]
		if conversie:
			plan["trece_in_avansat"] = True
			_tintaConversie(model, alegeri, cfg, nm, tinta, rezumat, oprire)
	elif model["mod"] == "advanced":
		_tintaAvansat(model, alegeri, tinta, rezumat)
	for lnb in model["lnburi"]:
		if lnb["id"] in ids:
			# numai satelitii pe care LNB-ul chiar ii serveste: cei cu LNB anume trec prin LNB-ul lor (R1)
			plan["sateliti"].extend(satelitiServiti(model, lnb))
	plan["sateliti"] = sorted(set(plan["sateliti"]))
	# FI: oprire numai cand LNB-ul nou nu poate acorda nimic din tot ce serveste (revizia, B1)
	for lnb_id in ids:
		nou = lnbDupaAlegeri(model, alegeri, lnb_id)
		serviti = satelitiServiti(model, nou)
		if not serviti:
			# un al doilea „toti satelitii” (nucleul il foloseste pe primul) sau un LNB ai carui sateliti au toti LNB-ul
			# lor anume: la acord nu trece nimic prin el, deci nu are ce opri sau numara
			continue
		fi = verificaFI(nou, nm, serviti)
		if not fi["cunoscut"] or fi["total_tp"] == 0:
			if fi["cunoscut"]:
				plan["avertismente"].append(_("Pe %s nu știu niciun transponder, deci nu pot verifica frecvența "
					"intermediară.") % _listaNume(nm, serviti))
			continue
		if fi["bune_tp"] == 0:
			oprire.append(_("Cu acest LNB, receptorul nu poate acorda niciun transponder de pe %s: frecvența "
				"intermediară iese din 900-2200 MHz.") % _listaNume(nm, serviti))
			continue
		if fi["bune_tp"] < fi["total_tp"]:
			# cifrele stau dupa substantive, ca textul sa fie corect si la „20 de” (romana cere „de” de la 20 in sus)
			plan["avertismente"].append("%s: %s" % (nou["eticheta"], _("Cu acest LNB se pot acorda numai o parte "
				"din transponderele cunoscute: %d din %d, pe sateliți: %d din %d.") % (fi["bune_tp"], fi["total_tp"],
				fi["bune_sat"], fi["total_sat"])))
		# canalul poate rula si pe un tuner „equal to” sau legat, care foloseste acelasi LNB
		if serviciu and serviciu.get("slot") in legate and serviciu.get("orbital") in serviti \
				and serviciu.get("frecventa"):
			osc = oscilatoareKhz(nou)
			if osc is not None and not calcul(osc, serviciu["frecventa"], serviciu.get("polarizare", 0))["acceptat"]:
				plan["avertismente"].append(_("Canalul care rulează acum (pe %s) nu se mai poate acorda cu acest LNB.")
					% _numeSatelit(nm, serviciu["orbital"]))
	if tinta and receptorCuMotor(nm, model):
		plan["avertismente"].append(avertismentMotor())
	if oprire:
		plan["oprire"] = oprire[0]
	for cale, text in tinta:
		el = element(cfg, cale)
		inainte = None if (el is None or _esteNimic(el)) else textElement(el)
		if inainte != text:
			plan["schimbari"].append((cale, inainte, text))
	if not plan["schimbari"] and not plan["oprire"]:
		plan["oprire"] = _("Nu ai schimbat nimic.")
	return plan


def detalii(plan):
	"""randurile „Detalii”: fiecare cale din config.Nims.N, inainte si dupa; alocarile „fara LNB” ale satelitilor
	ramasi se strang intr-un singur rand"""
	randuri = []
	fara_lnb = 0
	for cale, inainte, dupa in plan["schimbari"]:
		if inainte is None and dupa == "0" and cale.startswith("advanced.sat.") and cale.endswith(".lnb"):
			# „toti satelitii” 2-4 (3602-3604) nu sunt sateliti: intra in acelasi rand, fara sa fie numarati
			if _intSauNimic(cale.split(".")[2]) not in TOTI_SATELITII:
				fara_lnb += 1
			continue
		randuri.append("config.Nims.%d.%s: %s -> %s" % (plan["slot"], cale, _("(nou)") if inainte is None else inainte,
			dupa))
	if fara_lnb:
		randuri.append(_("Sateliți fără LNB anume (advanced.sat.*.lnb = 0): încă %d.") % fara_lnb)
	return randuri
