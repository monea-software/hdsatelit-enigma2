# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# scanare_web.py: scanarea canalelor si orientarea antenei in interfata web (HdsWebControl).
#
# La tasta MENU primele doua intrari sunt „Scanare" si „Orientarea și setarea antenei"; orice ecran de pe receptor
# are pereche in interfata web. Aici sunt aceleasi doua sectiuni si aceleasi feluri de scanare, cu pornirea cautarii
# din browser si starea ei (procent, canale gasite, transpondere, timp ramas, rezultat).
#
# O SINGURA SURSA DE ADEVAR, NIMIC SCRIS A DOUA OARA:
# - sectiunile, grupurile si felurile (ordinea si textele) se citesc din menu.xml, cu aceleasi reguli ca Menu.py
#   (greutate, nivel). Pozitia unei intrari se scrie numai in menu.xml. Web-ul
#   recunoaste o intrare dupa tinta ei (modulul, ecranul si felul dat ca argument), nu dupa locul in care sta, deci
#   o mutare in menu.xml se vede singura si aici;
# - ce se cere nucleului vine din pregateste() al fiecarui scaner (Screens/ScanerSatelit.py, ScanerCablu.py,
#   ScanerTerestru.py), aceeasi functie pe care o foloseste ecranul de pe televizor;
# - cautarea ruleaza pe televizor, in ecranul ServiceScan (Screens/ServiceScan.py), exact ca atunci cand e pornita
#   din telecomanda; web-ul il deschide si ii citeste starea din etichetele lui si din Components/ServiceScan.py.
#   DVB-T2 si DAB+ prin satelit: pagina arata intai planul (unde se roteste antena, cat dureaza: plan_fluxuri din
#   ScanerSatelit.py) si cere confirmarea, apoi deschide pe televizor ecranul Screens/HdsScanareFluxuri.py cu
#   cautarea pornita; ii citeste starea (stare_web) si ii trimite alegerile de la sfarsit (Ascultă un post, Înapoi
#   la canalul meu, Caută din nou), deci televizorul si pagina arata acelasi lucru;
# - calculatorul de unghiuri foloseste formula din Screens/PositionerSetup.py;
# - rezultatul ultimei scanari (GET /api/scanare-ultima: transponderele si toate serviciile citite din SDT) il tine
#   Components/HdsScanareUltima.py, scris de Components/ServiceScan.py din nucleu; aici numai se trimite.
#
# FIRUL ENIGMA2: tot ce atinge config, nimmanager, sesiunea sau ecranele ruleaza pe firul principal (reactorul e
# chiar bucla enigma2). Singurul lucru lung, citirea listelor mari (cables.xml are ~800 KB, terrestrial.xml ~360 KB),
# se face pe un fir separat, care citeste numai fisiere; raspunsul pleaca dupa un eTimer, nu dupa reactor.callLater
# (masurat pe receptor: 90 s cu callLater, 1,5 s cu eTimer).
#
# POARTA: resursele API mostenesc HdsJsonResource din plugin.py (reteaua locala, apoi ?token= sau cookie-ul
# browserului asociat; cu cookie, ce schimba ceva cere POST, aceeasi origine si antetul CSRF al panoului). Antetul
# Host e verificat inainte, in _CerereHds.process. Pagina are aceeasi poarta ca /ecrane.
#
# TEXTE: pagina si mesajele de aici sunt in romana, ca restul interfetei web. Textele care vin din scanere (motive,
# previzualizari) si din menu.xml trec prin _(), deci vin in limba aleasa pe receptor.
#
# Fisierul nu importa nimic din enigma2 la incarcare: plugin.py il incarca abia cand construieste rutele, iar
# probele de pe PC (teste/test_scanare_web.py) il pot incarca fara receptor.

import ast
import json
import os
import threading
import time
import xml.etree.ElementTree as ET

CALE_MENIU = None           # probele pun aici un menu.xml; pe receptor: resolveFilename(SCOPE_SKIN, "menu.xml")

# cheia paginii -> key-ul nodului din menu.xml (Menu.py deschide nodul, la tasta MENU)
SECTIUNI = (("scanare", "scan"), ("antena", "hds_antena"))

SCANERE = ("satelit", "cablu", "terestru")

# tinta din menu.xml (modul, ecran) -> scanerul; felul vine ca argument (<screen ...>"fel"</screen>)
TINTE_SCANARE = {
	("ScanerSatelit", "ScanerSatelit"): "satelit",
	("ScanerCablu", "ScanerCablu"): "cablu",
	("ScanerTerestru", "ScanerTerestru"): "terestru",
}
# „Mai mulți sateliți" are ecranul lui, fara argument
TINTE_FEL_FIX = {("ScanerMaiMultiSateliti", "ScanerMaiMultiSateliti"): ("satelit", "mai_multi")}

# tinta din menu.xml -> cartela din sectiunea antenei
TINTE_ANTENA = {
	("Satconfig", "NimSelection"): "tuner",
	("ConfigLNB", "ConfigLNB"): "lnb",
	("HdsDishMotor", "HdsDishMotorEcran"): "motor",
	("PositionerSetup", "HdsPositionerSetup"): "calculator",
	("Satfinder", "Satfinder"): "semnal",
	("HdsLocul", "HdsLoculEcran"): "locul",
}

# Fluxul (ISI) si secventa PLS se cer ca pe televizor: randurile vin din ScanerSatelit.campuri_manual (cu
# „Multistream” pe Da). T2-MI PLP-ID nu e aici: DVB-T2 prin satelit are felul lui.

MAX_ARGUMENTE = 60
MAX_POZITII = 400
MAX_TEXT_ARGUMENT = 200

# LNB-ul pe care il pune nucleul in modul simplu (Components/NimManager.py, addLNBSimple: 9750/10600/11700 MHz)
LNB_UNIVERSAL = {"lof_jos": 9750, "lof_sus": 10600, "prag": 11700}


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsWebControl] scanare: %s" % text)


# ------------------------------------------------------------------ menu.xml
_MENIU = {"cale": None, "semn": None, "radacina": None}


def _caleMeniu():
	if CALE_MENIU:
		return CALE_MENIU
	try:
		from Tools.Directories import resolveFilename, SCOPE_SKIN
		return resolveFilename(SCOPE_SKIN, "menu.xml")
	except Exception:
		return "/usr/share/enigma2/menu.xml"


def _radacinaMeniu():
	"""Radacina lui menu.xml, citita o data si recitita numai cand fisierul se schimba (~30 KB)."""
	cale = _caleMeniu()
	try:
		semn = os.path.getmtime(cale)
	except OSError:
		semn = None
	if _MENIU["radacina"] is None or _MENIU["cale"] != cale or _MENIU["semn"] != semn:
		try:
			radacina = ET.parse(cale).getroot()
		except Exception as eroare:
			_jurnal("nu pot citi %s: %s" % (cale, eroare))
			radacina = None
		_MENIU.update(cale=cale, semn=semn, radacina=radacina)
	return _MENIU["radacina"]


def _nivelUtilizator():
	"""config.usage.setup_level.index, ca in Menu.py (0 simplu, 1 intermediar, 2 expert); 0 daca nu se poate citi."""
	try:
		from Components.config import config
		return int(config.usage.setup_level.index)
	except Exception:
		return 0


def _cerintaIndeplinita(nod):
	"""Atributul requires= din menu.xml, cu aceleasi reguli ca Menu.py (addItem/addMenu)."""
	cerinta = nod.get("requires")
	if not cerinta:
		return True
	try:
		from Components.SystemInfo import SystemInfo
	except Exception:
		return True
	if cerinta[0] == "!":
		return not SystemInfo.get(cerinta[1:], False)
	return bool(SystemInfo.get(cerinta, False))


def _greutate(nod):
	try:
		return int(nod.get("weight", 50))
	except (TypeError, ValueError):
		return 50


def _copiiVizibili(nod, nivel):
	"""Copiii unui <menu>, filtrati si ordonati ca in Menu.__init__: <item> numai cu level <= nivelul
	utilizatorului, <menu> mereu, apoi sortarea stabila dupa weight."""
	copii = []
	for x in nod:
		if x.tag == "item":
			try:
				nivel_intrare = int(x.get("level", 0))
			except (TypeError, ValueError):
				nivel_intrare = 0
			if nivel_intrare <= nivel and _cerintaIndeplinita(x):
				copii.append(x)
		elif x.tag == "menu" and _cerintaIndeplinita(x):
			copii.append(x)
	copii.sort(key=_greutate)
	return copii


def _tinta(intrare):
	"""Ce deschide intrarea pe televizor: {"fel": "ecran", "modul", "ecran", "argumente"} (argumentele numai daca
	sunt valori simple, citite cu ast.literal_eval, niciodata cu eval), {"fel": "cod", "text"} sau None."""
	for x in intrare:
		if x.tag == "screen":
			modul = x.get("module") or ""
			ecran = x.get("screen") or modul
			text = (x.text or "").strip()
			argumente = ()
			if text:
				try:
					argumente = ast.literal_eval("(" + text + ",)")
				except (ValueError, SyntaxError):
					argumente = None
			return {"fel": "ecran", "modul": modul, "ecran": ecran, "argumente": argumente}
		if x.tag == "code":
			return {"fel": "cod", "text": x.text or ""}
		if x.tag == "setup":
			return {"fel": "setup", "id": x.get("id") or ""}
	return None


def _recunoaste(tinta):
	"""(scaner, fel) pentru o intrare de scanare, ("antena", cheie) pentru una de antena, altfel (None, None)."""
	if not tinta:
		return None, None
	if tinta["fel"] == "ecran":
		pereche = (tinta["modul"], tinta["ecran"])
		if pereche in TINTE_FEL_FIX:
			return TINTE_FEL_FIX[pereche]
		scaner = TINTE_SCANARE.get(pereche)
		argumente = tinta["argumente"]
		if scaner and argumente and isinstance(argumente[0], str):
			return scaner, argumente[0]
		if pereche in TINTE_ANTENA:
			return "antena", TINTE_ANTENA[pereche]
	elif tinta["fel"] == "cod" and "DiseqcTester" in tinta["text"]:
		return "antena", "diseqc"
	return None, None


def _seDeschidePeTelevizor(tinta):
	"""Web-ul deschide pe televizor numai ecrane din Screens cu argumente simple (fara <code>, fara eval)."""
	return bool(tinta and tinta["fel"] == "ecran" and tinta["argumente"] is not None
		and tinta["modul"].isidentifier() and tinta["ecran"].isidentifier())


def _cuSemn(nod):
	"""Numele tradus al nodului, cu semnul „(în lucru)” / „(netestat)” din atributul stare=,
	acelasi ca pe televizor (Screens/Menu.py si Components/HdsStareMeniu.py); fara modul, numele simplu."""
	try:
		from Components import HdsStareMeniu
		return HdsStareMeniu.textNod(nod, _t)
	except ImportError:
		return _t(nod.get("text") or "??")


def _descriereIntrare(nod):
	tinta = _tinta(nod)
	scaner, fel = _recunoaste(tinta)
	return {
		"tip": "intrare",
		"id": nod.get("entryID") or "",
		"text": _cuSemn(nod),
		"web": nod.get("web") or "",
		"scaner": scaner if scaner in SCANERE else None,
		"antena": fel if scaner == "antena" else None,
		"fel": fel if scaner in SCANERE else None,
		"televizor": _seDeschidePeTelevizor(tinta),
	}


def _nodSectiune(radacina, cheie_meniu):
	if radacina is None:
		return None
	for nod in radacina.iter("menu"):
		if nod.get("key") == cheie_meniu:
			return nod
	return None


def structura():
	"""Cele doua sectiuni, asa cum le arata televizorul la tasta MENU: [{"cheie", "id", "titlu", "web", "copii"}], cu
	copiii in ordinea din Menu.py; un copil e un grup (submeniu) cu intrarile lui sau o intrare. Extensiile agatate
	de un meniu prin cod (de exemplu importul de canale, agatat de „scan") nu sunt in menu.xml si nu apar aici."""
	radacina = _radacinaMeniu()
	nivel = _nivelUtilizator()
	sectiuni = []
	for cheie, cheie_meniu in SECTIUNI:
		nod = _nodSectiune(radacina, cheie_meniu)
		if nod is None:
			continue
		copii = []
		for copil in _copiiVizibili(nod, nivel):
			if copil.tag == "item":
				copii.append(_descriereIntrare(copil))
				continue
			intrari = [_descriereIntrare(x) for x in _copiiVizibili(copil, nivel) if x.tag == "item"]
			scanere = set(x["scaner"] for x in intrari if x["scaner"])
			copii.append({
				"tip": "grup",
				"id": copil.get("entryID") or "",
				"cheie": scanere.pop() if len(scanere) == 1 else (copil.get("entryID") or ""),
				"titlu": _cuSemn(copil),
				"web": copil.get("web") or "",
				"copii": intrari,
			})
		sectiuni.append({"cheie": cheie, "id": nod.get("entryID") or "", "titlu": _cuSemn(nod),
			"web": nod.get("web") or "", "salveaza": bool(nod.get("flushConfigOnClose")), "copii": copii})
	return sectiuni


def _cautaVizibil(nod, id_intrare, nivel):
	"""Intrarea cu entryID-ul dat printre cele pe care televizorul le arata (_copiiVizibili, si in submeniuri)."""
	for copil in _copiiVizibili(nod, nivel):
		if copil.tag == "item" and copil.get("entryID") == id_intrare:
			return copil
		if copil.tag == "menu":
			gasit = _cautaVizibil(copil, id_intrare, nivel)
			if gasit is not None:
				return gasit
	return None


def _intrareDupaId(id_intrare):
	"""(nodul intrarii, sectiunea ei) pentru un entryID din cele doua sectiuni, altfel (None, None). Numai intrarile
	pe care le arata si televizorul: level= fata de nivelul utilizatorului si requires=, cu aceleasi reguli ca
	Menu.py: /api/scanare-televizor nu deschide ce televizorul ascunde (de exemplu „Liste implicite de canale”,
	level 1, pentru un utilizator pe nivelul simplu)."""
	radacina = _radacinaMeniu()
	nivel = _nivelUtilizator()
	for _cheie, cheie_meniu in SECTIUNI:
		sectiune = _nodSectiune(radacina, cheie_meniu)
		if sectiune is None:
			continue
		nod = _cautaVizibil(sectiune, id_intrare, nivel)
		if nod is not None:
			return nod, sectiune
	return None, None


# ------------------------------------------------------------------ scanerele (importate abia la folosire)
def _modulScaner(scaner):
	if scaner == "satelit":
		import Screens.ScanerSatelit as modul
	elif scaner == "cablu":
		import Screens.ScanerCablu as modul
	elif scaner == "terestru":
		import Screens.ScanerTerestru as modul
	else:
		return None
	return modul


_LACAT_CITIRE = threading.Lock()


def caiDeCitit(scaner):
	"""Pe firul enigma2, inainte de firul separat: caile fisierelor de date. Aflarea lor trece prin enigma2
	(eEnv.resolve, resolveFilename), deci nu se face pe celalalt fir; acolo se citesc numai fisierele."""
	cai = {}
	try:
		if scaner == "satelit":
			from Components import HdsOperatoriSatelit
			cai["operatori"] = HdsOperatoriSatelit.cale_date()
		elif scaner == "terestru":
			import Components.HdsListeCabluTerestru as liste
			cai["romania"] = liste._cale_date(liste.FISIER_ROMANIA)
	except Exception as eroare:
		_jurnal("caile fisierelor de date: %s" % eroare)
	return cai


def incalzeste(scaner, cai=None):
	"""Pe firul separat: citeste o data listele mari ale scanerului, ca raspunsul de pe firul enigma2 sa le gaseasca
	deja in memorie. Numai fisiere (cables.xml, terrestrial.xml, terestru-romania.json, operatori-satelit.json), cu
	caile aflate inainte pe firul enigma2 (caiDeCitit): nimic din config, nimmanager sau ecrane. Doua cereri deodata
	nu citesc acelasi fisier de doua ori (lacatul). Aceleasi cai ca pe firul enigma2, deci aceeasi memorie."""
	cai = cai or {}
	with _LACAT_CITIRE:
		if scaner == "satelit":
			from Components import HdsOperatoriSatelit
			HdsOperatoriSatelit.incarca(cai.get("operatori"))
		elif scaner in ("cablu", "terestru"):
			import Components.HdsListeCabluTerestru as liste
			if scaner == "cablu":
				liste.liste_cablu()
			else:
				liste.liste_terestre(cale_romania=cai.get("romania"))


def _optiuni(lista):
	return [{"cod": str(cod), "text": text} for cod, text in lista or []]


def _valoareInLista(camp, implicit_primul=True):
	"""Valoarea unui camp de tip lista care nu mai e in lista lui trece pe prima, ca in ecran (_normalizeaza)."""
	coduri = [o["cod"] for o in camp["optiuni"] if o.get("cod") is not None]
	if coduri and camp["valoare"] not in coduri and implicit_primul:
		camp["valoare"] = coduri[0]


def _camp(cheie, eticheta, tip, optiuni=None, valoare="", nota=""):
	return {"cheie": cheie, "eticheta": eticheta, "tip": tip, "optiuni": optiuni or [], "valoare": valoare,
		"nota": nota}


# ---- satelitul
def _valoriSatelit(S, fel, cerere):
	"""Valorile ecranului de satelit (ultimele folosite, din fisierul lui de configurare), peste care vin cele din
	cerere. Operatorul fiecarui fel sta in campul lui (CAMP_OPERATOR), dar pregateste() il vrea sub "operator"."""
	c = S._citeste_config()
	c.pop("tip", None)
	v = dict(c)
	if fel in S.CAMP_OPERATOR:
		v["operator"] = c.get(S.CAMP_OPERATOR[fel], "")
	for cheie, valoare in (cerere or {}).items():
		if cheie == "pozitii":
			continue
		if cheie in c or cheie == "operator":
			v[cheie] = valoare
	v["fel"] = fel
	# o pozitie trimisa de mai multe ori se cauta o data (si pregateste() le deduplica)
	pozitii = []
	for p in (cerere or {}).get("pozitii") or []:
		if str(p).lstrip("-").isdigit() and p not in pozitii:
			pozitii.append(p)
	v["pozitii"] = pozitii
	return v


def _antenaSatelit(S):
	"""(nimmanager, slot, [(pozitie, nume)], motor) pentru primul tuner de satelit; slot None fara tuner."""
	nim = S._nimmanager()
	if nim is None:
		return None, None, [], False
	try:
		slot = S.slot_satelit(nim)
	except Exception as eroare:
		_jurnal("tunerele nu se pot citi: %s" % eroare)
		return nim, None, [], False
	if slot is None:
		return nim, None, [], False
	return nim, slot, S.sateliti_tuner(nim, slot), S.are_motor(nim, slot)


def _campuriSatelit(S, fel, v):
	"""Aceleasi randuri ca ScanerSatelit._campuri, cu aceleasi texte (deci cu traducerile lor)."""
	nim, slot, sateliti, motor = _antenaSatelit(S)
	pozitii = [p for p, _n in sateliti]
	# tunerul poate alege fluxul: operatorii multistream se pot cauta, ca pe televizor (ScanerSatelit.tuner_multistream)
	ms = bool(nim is not None and slot is not None and S.tuner_multistream(nim, slot))
	campuri = []
	if fel in ("transponder", "satelit", "manual"):
		camp = _camp("pozitie", _t("Satelit (poziție orbitală)"), "lista",
			[{"cod": str(p), "text": nume or S.text_pozitie(p)} for p, nume in sateliti], str(v.get("pozitie", "")))
		_valoareInLista(camp)
		v["pozitie"] = camp["valoare"]
		campuri.append(camp)
	if fel == "transponder":
		bune = []
		orbpos = S._int(v.get("pozitie"), None)
		if nim is not None and orbpos is not None:
			try:
				bune, _sarite = S.transpondere_satelit(orbpos, nim.getTransponders(orbpos))
			except Exception as eroare:
				_jurnal("transponderele satelitului %s: %s" % (orbpos, eroare))
		camp = _camp("transponder", _t("Transponder"), "lista",
			[{"cod": S.cheie_tp(t), "text": S._descriere_tp(t)} for t in bune], str(v.get("transponder", "")))
		_valoareInLista(camp)
		v["transponder"] = camp["valoare"]
		campuri.append(camp)
		camp = _camp("retea", _t("Căutare în rețea"), "lista", _optiuni(S.DA_NU), str(v.get("retea", "0")))
		_valoareInLista(camp)
		v["retea"] = camp["valoare"]
		campuri.append(camp)
	elif fel in S.CAMP_OPERATOR:
		optiuni, prima_buna, ids = [], None, []
		nota = ""
		for i, (titlu, lista) in enumerate(S.grupe(fel)):
			optiuni.append({"cod": None, "grupa": True, "text": titlu})
			if i == 0 and not lista:
				nota = _t("%s: niciun operator de acest fel. Operatorii din alte țări sunt în lista „Operator”.") \
					% titlu
			for op in lista:
				# ca in lista de alegere de pe televizor (ScanerSatelit.intrari_alegere): randul sta sub titlul tarii,
				# deci fara prefixul felului si fara tara
				nume = S.nume_in_grupa(op) if hasattr(S, "nume_in_grupa") else op["nume"]
				text = "%s, %s" % (nume, S.text_pozitie(op["pozitie"]))
				vede = not pozitii or op["pozitie"] in pozitii
				if op["cere_multistream"] and not ms:
					text += " " + _t("(tunerul nu alege fluxul)")
				elif not vede:
					text += " " + _t("(antena nu vede satelitul)")
				elif prima_buna is None:
					prima_buna = op["id"]
				optiuni.append({"cod": op["id"], "text": text})
				ids.append(op["id"])
		valoare = str(v.get("operator", ""))
		if valoare not in ids:
			valoare = prima_buna or (ids[0] if ids else "")
		v["operator"] = valoare
		campuri.append(_camp("operator", _t("Operator"), "lista", optiuni, valoare, nota))
	elif fel == "manual":
		for cheie, eticheta, tip, lista in S.ScanerSatelit.campuri_manual(v):
			valoare = str(v.get(cheie, ""))
			if tip != "lista":
				campuri.append(_camp(cheie, eticheta, "numeric", None, valoare))
				continue
			# numai valorile pe care nucleul le primeste pentru sistemul ales, ca stanga/dreapta pe televizor
			permise = [str(x) for x in S._coduri_permise(cheie, v, lista)]
			optiuni = [{"cod": str(c), "text": text} for c, text in lista if str(c) in permise]
			if valoare not in permise:
				if cheie in ("fec", "mod") and S._sistem_nucleu(v) == S.SISTEM_DVB_S2:
					text = _t("de ales, DVB-S2 nu primește Auto")
				else:
					text = S._nume_valoare(lista, S._int(valoare, valoare))
				optiuni.insert(0, {"cod": valoare, "text": text})
			campuri.append(_camp(cheie, eticheta, "lista", optiuni, valoare))
	elif fel == "mai_multi":
		alese = [str(p) for p in v.get("pozitii") or []]
		camp = _camp("pozitii", _t("Sateliți"), "bife",
			[{"cod": str(p), "text": nume or S.text_pozitie(p)} for p, nume in sateliti],
			[p for p in alese if p in [str(x) for x in pozitii]])
		campuri.append(camp)
	return campuri, {"motor": motor, "slot": slot, "are_tuner": slot is not None}


def _valoriPregateste(S, fel, v):
	valori = dict(v)
	if fel == "mai_multi":
		valori["pozitii"] = [S._int(p, None) for p in v.get("pozitii") or []]
	return valori


# ---- cablul si terestrul
def _valoriCabluTerestru(scaner, M, fel, cerere):
	import Screens.ScanerCablu as C
	clasa = M.ScanerCablu if scaner == "cablu" else M.ScanerTerestru
	c = C.citeste_config(clasa.CALE_CONFIG, M.config_implicit())
	try:
		# configuratia scrisa de o versiune veche, ca pe televizor: la terestru frecventa in Hz devine MHz, la cablu un
		# operator din alta tara, salvat inainte ca alegerea omului sa fie tinuta minte, trece pe primul din tara lui
		c = clasa.potriveste_config(None, c)
	except Exception as eroare:
		_jurnal("configuratia veche (%s): %s" % (scaner, eroare))
	v = dict(c)
	for cheie, valoare in (cerere or {}).items():
		if cheie in c and cheie != "operator_ales":
			v[cheie] = valoare
	v["fel"] = fel
	return v


def _campuriCabluTerestru(M, fel, v):
	campuri = []
	for cheie, eticheta, tip, optiuni in M.campuri(fel):
		valoare = str(v.get(cheie, ""))
		if tip == "alegere":
			randuri, note = [], []
			for text, cod in M.alegeri(cheie):
				if cod is None and text[:1] == " ":
					# rand de nota (fara cheie, tras spre dreapta; HdsListeCabluTerestru.este_nota): sub lista, ca pe
					# televizor, nu titlu de grupa in lista
					note.append(text.strip())
				elif cod is not None and str(cod).startswith("fel:"):
					# randul care pe televizor deschide alt fel de scanare (Orange -> „Toată banda”): aici nota, cu drumul
					nota_fel = getattr(M, "text_nota_web", None)
					note.append((nota_fel(str(cod)) if nota_fel else "") or text.strip())
				elif cod is None:
					randuri.append({"cod": None, "grupa": True, "text": text.strip()})
				else:
					randuri.append({"cod": str(cod), "text": text.strip()})
			campuri.append(_camp(cheie, eticheta, "lista", randuri, valoare, " ".join(note)))
		elif tip == "lista":
			camp = _camp(cheie, eticheta, "lista", _optiuni(optiuni), valoare)
			_valoareInLista(camp)
			v[cheie] = camp["valoare"]
			campuri.append(camp)
		else:
			campuri.append(_camp(cheie, eticheta, "numeric", None, valoare))
	return campuri


# ---- comun
def _previzualizare(rez):
	"""Ce se va cauta, sau de ce nu se poate: acelasi raspuns ca la pornire, fara listele de transpondere."""
	if rez.get("eroare"):
		return {"eroare": rez["eroare"]}
	p = {"text": rez.get("text", ""), "intrebare": rez.get("intrebare", "")}
	if rez.get("transpondere") is not None:
		p["transpondere"] = len(rez["transpondere"])
	if rez.get("de_ales"):
		p["de_ales"] = True
	return p


def _numeFel(scaner, fel):
	for sectiune in structura():
		for copil in sectiune["copii"]:
			for x in copil.get("copii", [copil]):
				if x.get("scaner") == scaner and x.get("fel") == fel:
					return x["text"]
	return fel


def campuri(scaner, fel, cerere=None):
	"""Randurile felului (aceleasi ca pe televizor), cu valorile ultimei folosiri peste care vin cele din cerere, plus
	previzualizarea: ce se va cauta sau de ce nu se poate. Numai citire: nu scrie nimic si nu porneste nimic."""
	M = _modulScaner(scaner)
	if M is None:
		return {"result": False, "message": _t("Scaner necunoscut: %s.") % scaner}
	feluri = [f for f, _n in M.FELURI] if scaner == "satelit" else list(M.FELURI)
	if fel not in feluri:
		return {"result": False, "message": _t("Felul de scanare „%s” nu există la %s.") % (fel, scaner)}
	info = {}
	if scaner == "satelit":
		v = _valoriSatelit(M, fel, cerere)
		randuri, info = _campuriSatelit(M, fel, v)
		try:
			rez = M.pregateste(fel, _valoriPregateste(M, fel, v))
		except Exception as eroare:
			_jurnal("previzualizarea %s/%s: %s" % (scaner, fel, eroare))
			rez = {"eroare": _t("Previzualizarea nu a mers: %s") % eroare}
	else:
		v = _valoriCabluTerestru(scaner, M, fel, cerere)
		randuri = _campuriCabluTerestru(M, fel, v)
		try:
			rez = M.pregateste(fel, v)
		except Exception as eroare:
			_jurnal("previzualizarea %s/%s: %s" % (scaner, fel, eroare))
			rez = {"eroare": _t("Previzualizarea nu a mers: %s") % eroare}
	raspuns = {"result": True, "scaner": scaner, "fel": fel, "titlu": _numeFel(scaner, fel), "campuri": randuri,
		"previzualizare": _previzualizare(rez), "motor": bool(info.get("motor")), "stare": stare()}
	if scaner == "satelit" and "hdscomun" in rez:
		raspuns["plan"] = _planFluxuri(M, rez)
	# felurile cu „(în lucru)” in menu.xml: de ce (ScanerSatelit.text_in_lucru, acelasi text ca pe televizor)
	if scaner == "satelit" and hasattr(M, "text_in_lucru"):
		try:
			raspuns["in_lucru"] = M.text_in_lucru(fel, _caleMeniu())
		except Exception as eroare:
			_jurnal("textul starii %s: %s" % (fel, eroare))
	return raspuns


def _planFluxuri(M, rez):
	"""Planul scanarii DAB+ / DVB-T2 (ScanerSatelit.plan_fluxuri, acelasi ca pe televizor): randurile (operator,
	satelit, transponder, antena, durata) si textul cu ce se intampla la sfarsit. None daca nu se poate face."""
	try:
		plan = M.plan_fluxuri(rez, _sesiune())
	except Exception as eroare:
		_jurnal("planul scanarii: %s" % eroare)
		return None
	return {"randuri": [[str(e), str(v)] for e, v in plan.get("randuri") or []], "text": plan.get("text", "")}


# ------------------------------------------------------------------ cautarea pe televizor
# Starea cautarii pornite din web. Una singura o data, fie ServiceScan, fie ecranul scanarii DVB-T2 / DAB+ prin
# satelit (HdsScanareFluxuri); una pornita din telecomanda se vede si ea (ecranul ei deschis pe televizor).
_LUCRU = {"dialog": None, "fluxuri": None, "final": None, "scaner": "", "fel": "", "titlu": "", "text": "",
	"pornit": None}


def _sesiune():
	"""Sesiunea enigma2 tinuta de plugin.py (porneste(), la WHERE_SESSIONSTART)."""
	try:
		from . import plugin
		return getattr(plugin, "_sesiune", None)
	except Exception:
		return None


def _inStandby():
	try:
		from Screens import Standby     # cu from: merge si cand pachetul nu are inca atributul submodulului
		return Standby.inStandby is not None
	except Exception:
		return False


def _dialoguri(sesiune):
	"""Ferestrele deschise pe televizor: cea din fata, apoi cele de sub ea."""
	deschise = []
	curent = getattr(sesiune, "current_dialog", None)
	if curent is not None:
		deschise.append(curent)
	for x in getattr(sesiune, "dialog_stack", None) or []:
		deschise.append(x[0] if isinstance(x, tuple) else x)
	return deschise


def _dialogScanare(sesiune):
	"""(fereastra ServiceScan deschisa, pornita din web?) sau (None, False)."""
	if sesiune is None:
		return None, False
	deschise = _dialoguri(sesiune)
	al_nostru = _LUCRU["dialog"]
	if al_nostru is not None:
		if any(d is al_nostru for d in deschise):
			return al_nostru, True
		_LUCRU["dialog"] = None
	try:
		from Screens.ServiceScan import ServiceScan
	except Exception:
		return None, False
	for d in deschise:
		if isinstance(d, ServiceScan):
			_urmareste(d)
			return d, False
	return None, False


def _urmareste(dlg):
	"""La inchiderea ferestrei (Exit pe televizor sau Opreste din web) se pastreaza ultima stare, ca pagina sa
	arate rezultatul si dupa aceea. onClose ruleaza inainte ca fereastra sa-si stearga componentele (Screen.doClose)."""
	if getattr(dlg, "_hds_web_urmarit", False):
		return
	try:
		dlg._hds_web_urmarit = True

		def _laInchidere():
			try:
				final = _citesteDialog(dlg)
			except Exception as eroare:
				_jurnal("starea de la inchidere: %s" % eroare)
				final = {"fel_lucru": "dvb", "gata": True}
			final.update(inchisa=True, in_curs=False)
			if not final.get("gata"):
				final["oprita"] = True       # inchisa inainte de sfarsit (Exit pe televizor sau Opreste din web)
			if _LUCRU["dialog"] is dlg:
				final.update(din_web=True, scaner=_LUCRU["scaner"], fel=_LUCRU["fel"], titlu=_LUCRU["titlu"],
					text=_LUCRU["text"])
				_LUCRU["dialog"] = None
			else:
				final["din_web"] = False
			_LUCRU["final"] = final

		dlg.onClose.append(_laInchidere)
	except Exception as eroare:
		_jurnal("nu pot urmari fereastra de scanare: %s" % eroare)


def _textEticheta(dlg, nume):
	try:
		eticheta = dlg.get(nume)
		if eticheta is None:
			return ""
		text = eticheta.getText()
		return text if isinstance(text, str) else str(text or "")
	except Exception:
		return ""


def _reteaGasita(cscan):
	"""Reteaua citita din NIT la sfarsitul scanarii, ca in caseta de pe televizor (Components/ServiceScan.hdsTexteRetea:
	titlul, numele, datele, indiciul, traduse), plus frecventele anuntate de ea (Components/HdsRetele.py), sau None."""
	try:
		texte = cscan.hdsTexteRetea()
	except Exception:
		return None
	if not texte:
		return None
	rez = dict(texte)
	try:
		from Components import HdsRetele
		r = HdsRetele.retea(cscan.hdsReteaPrincipala()["cheie"]) or {}
		muxuri = sorted(r.get("multiplexuri") or [], key=lambda m: (m.get("f_khz") or 0))
		rez["frecvente"] = [{"mhz": "%g" % ((m.get("f_khz") or 0) / 1000.0), "mod": m.get("mod") or "",
			"sr": m.get("sr"), "tsid": m.get("tsid")} for m in muxuri]
		rez["frecvente_titlu"] = _("Frecvențe anunțate: %d") % len(muxuri)
		# capul tabelului scurt (unitatile), ca tabelul sa incapa si pe telefon
		rez["frecvente_coloane"] = ["MHz", _("Modulație"), "kS/s", "TSID"]
	except Exception:
		rez["frecvente"] = []
	return rez


def _citesteDialog(dlg):
	"""Starea unei ferestre ServiceScan: aceleasi texte pe care le arata televizorul (etichetele ei) si numerele din
	Components/ServiceScan.py. Numai citire: nu cheama nimic care schimba starea (de ex. etaSeconds)."""
	st = {
		"fel_lucru": "dvb",
		"stare_text": _textEticheta(dlg, "scan_state"),
		"timp_ramas": _textEticheta(dlg, "scan_eta"),
		"transpondere_text": _textEticheta(dlg, "scan_transponders"),
		"retea": _textEticheta(dlg, "network"),
		"transponder": _textEticheta(dlg, "transponder"),
		"trecere": _textEticheta(dlg, "pass"),
		"procent": None, "canale": None, "transpondere": None, "gata": False, "eroare": False,
	}
	rezultat = _textEticheta(dlg, "scan_result")
	st["rezultat"] = [r for r in rezultat.split("\n") if r.strip()] if rezultat else []
	try:
		lista = dlg.get("servicelist")
		st["ultimele"] = [str(x) for x in (getattr(lista, "list", None) or [])][-10:]
	except Exception:
		st["ultimele"] = []
	cscan = None
	try:
		cscan = dlg.get("scan")
	except Exception:
		cscan = None
	if cscan is None:
		return st
	try:
		gata = bool(cscan.isDone())
	except AttributeError:
		gata = False                # starea se pune abia la pornirea cautarii (CScan.doRun)
	st["gata"] = gata
	st["eroare"] = gata and getattr(cscan, "state", None) == getattr(cscan, "Error", 4)
	if gata:
		st["retea_gasita"] = _reteaGasita(cscan)
	nucleu = getattr(cscan, "scan", None)      # sters intre treceri (execEnd), deci cu getattr
	try:
		canale = int(getattr(cscan, "foundServices", 0) or 0)
		if not gata and nucleu is not None and not getattr(cscan, "passFinished", False):
			canale += int(nucleu.getNumServices())
		st["canale"] = canale
	except Exception:
		pass
	try:
		if gata:
			st["procent"] = 100
		elif nucleu is not None:
			st["procent"] = max(0, min(100, int(nucleu.getProgress())))
	except Exception:
		pass
	try:
		if gata:
			facute = int(cscan.tpDoneBase)
			st["transpondere"] = [facute, max(int(cscan.tpTotalBase), facute)]
		else:
			facute, total = cscan.overallCounts()
			st["transpondere"] = [int(facute), int(total)]
	except Exception:
		pass
	try:
		st["secunde_ramase"] = None if gata else cscan.etaShown
	except Exception:
		st["secunde_ramase"] = None
	return st


def _dialogFluxuri(sesiune):
	"""(ecranul scanarii DVB-T2 / DAB+ deschis pe televizor, pornit din web?) sau (None, False)."""
	if sesiune is None:
		return None, False
	deschise = _dialoguri(sesiune)
	al_nostru = _LUCRU["fluxuri"]
	if al_nostru is not None:
		if any(d is al_nostru for d in deschise):
			return al_nostru, True
		_LUCRU["fluxuri"] = None
	try:
		from Screens.HdsScanareFluxuri import HdsScanareFluxuri
	except Exception:
		return None, False
	for d in deschise:
		if isinstance(d, HdsScanareFluxuri):
			_urmaresteFluxuri(d)
			return d, False
	return None, False


def _stareFluxuri(dlg):
	"""Starea ecranului scanarii DVB-T2 / DAB+ in forma paginii: fata ecranului (inainte, in curs, sfarsit), textul
	de pe televizor, grupele si posturile gasite (fara referinte: pagina alege dupa pozitia in lista)."""
	w = dlg.stare_web()
	fata = w.get("fata")
	return {"fel_lucru": "fluxuri", "fluxuri": w, "titlu_ecran": w.get("titlu", ""),
		"stare_text": w.get("text") or (w.get("plan") or {}).get("text", ""),
		"gata": fata in ("sfarsit", "inchis"), "in_curs": fata == "in_curs", "eroare": w.get("faza") == "esuat",
		"canale": len(w.get("posturi") or []), "procent": None, "rezultat": [],
		"text_brut": _textBrutFluxuri(dlg, fata)}


def _textBrutFluxuri(dlg, fata):
	"""Textul brut al scanarii (raspunsul detectorului si notele, ca ALBASTRU pe televizor), numai la sfarsit.
	Se face o singura data pe ecran (json.dumps pe firul enigma2), apoi se da din memorie la fiecare cerere."""
	if fata not in ("sfarsit", "inchis"):
		return ""
	gata = getattr(dlg, "_hds_web_text_brut", None)
	if gata is not None:
		return gata
	try:
		c = getattr(dlg, "cautare", None)
		text = c.text_brut() if c is not None else ""
	except Exception as eroare:
		_jurnal("textul brut al scanarii DAB+/DVB-T2: %s" % eroare)
		return ""
	text = text if isinstance(text, str) else str(text)
	try:
		dlg._hds_web_text_brut = text
	except Exception:
		pass
	return text


def _urmaresteFluxuri(dlg):
	"""La inchiderea ecranului (alegere pe televizor, din pagina sau EXIT) ramane ultima stare, cu alegerea facuta."""
	if getattr(dlg, "_hds_web_urmarit", False):
		return
	try:
		dlg._hds_web_urmarit = True

		def _laInchidere():
			try:
				final = _stareFluxuri(dlg)
			except Exception as eroare:
				_jurnal("starea de la inchiderea scanarii DAB+/DVB-T2: %s" % eroare)
				final = {"fel_lucru": "fluxuri", "gata": True, "fluxuri": {}}
			alegere, text = (getattr(dlg, "rezultat", None) or (None, ""))
			final.update(inchisa=True, in_curs=False, gata=True, alegere=alegere,
				rezultat=[text] if text else [], oprita=alegere in ("oprit", "renuntat"))
			if _LUCRU["fluxuri"] is dlg:
				final.update(din_web=True, scaner=_LUCRU["scaner"], fel=_LUCRU["fel"], titlu=_LUCRU["titlu"],
					text=_LUCRU["text"])
				_LUCRU["fluxuri"] = None
			else:
				final["din_web"] = False
			_LUCRU["final"] = final

		dlg.onClose.append(_laInchidere)
	except Exception as eroare:
		_jurnal("nu pot urmari ecranul scanarii DAB+/DVB-T2: %s" % eroare)


def stare():
	"""Starea cautarii, pentru pagina: {"activ": False} cand nu e nimic, altfel ce arata televizorul."""
	sesiune = _sesiune()
	dlgf, din_web = _dialogFluxuri(sesiune)
	if dlgf is not None:
		st = _stareFluxuri(dlgf)
		st.update(activ=True, din_web=din_web, poate_opri=getattr(sesiune, "current_dialog", None) is dlgf)
		if din_web:
			st.update(scaner=_LUCRU["scaner"], fel=_LUCRU["fel"], titlu=_LUCRU["titlu"], text=_LUCRU["text"])
		else:
			st["titlu"] = st["titlu_ecran"]
		return st
	dlg, din_web = _dialogScanare(sesiune)
	if dlg is not None:
		st = _citesteDialog(dlg)
		st.update(activ=True, din_web=din_web, in_curs=not st["gata"],
			poate_opri=getattr(sesiune, "current_dialog", None) is dlg)
		if din_web:
			st.update(scaner=_LUCRU["scaner"], fel=_LUCRU["fel"], titlu=_LUCRU["titlu"], text=_LUCRU["text"])
		return st
	if _LUCRU["final"] is not None:
		st = dict(_LUCRU["final"])
		st.update(activ=False, in_curs=False, poate_opri=False)
		return st
	return {"activ": False, "in_curs": False}


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire, cu _t."""
	return text


MESAJ_FARA_SCANARE = N_("Nicio scanare de canale de la pornirea receptorului.")


def ultima():
	"""Raspunsul gata facut (octeti JSON) al ultimei scanari de servicii, din Components/HdsScanareUltima.py (scris de
	Components/ServiceScan.py), sau None cand nu a fost nicio scanare de la pornirea receptorului. Numai citire."""
	try:
		from Components import HdsScanareUltima
	except ImportError as eroare:
		_jurnal("rezultatul ultimei scanari: %s" % eroare)
		return None
	return HdsScanareUltima.raspuns()


def _ocupat(sesiune):
	"""Textul refuzului cand nu se poate porni ceva nou pe televizor, altfel None."""
	if sesiune is None:
		return (_t("Interfața web nu are încă legătura cu ecranul receptorului. Așteaptă pornirea completă a "
			"receptorului sau repornește-l, apoi încearcă din nou."))
	if _inStandby():
		return _t("Receptorul este în standby. Pornește-l din telecomandă, apoi încearcă din nou.")
	dlgf, _din_web = _dialogFluxuri(sesiune)
	if dlgf is not None:
		if dlgf.fata == "sfarsit":
			return (_t("Pe televizor e deschis rezultatul scanării DAB+ sau DVB-T2. Alege acolo sau în pagină ce "
				"pornești sau întoarce-te la canalul tău, apoi pornește căutarea nouă."))
		return _t("O scanare DAB+ sau DVB-T2 e deschisă pe televizor. Așteaptă să se termine sau oprește-o.")
	dlg, _din_web = _dialogScanare(sesiune)
	if dlg is not None:
		try:
			gata = bool(dlg.get("scan") is not None and dlg["scan"].isDone())
		except Exception:
			gata = False
		if gata:
			return (_t("Pe televizor e încă deschis rezultatul căutării de dinainte. Închide-l (butonul din pagină sau "
				"tasta Exit), apoi pornește căutarea nouă."))
		return _t("O căutare e deja în curs pe receptor. Așteaptă să se termine sau oprește-o.")
	return None


def _salveazaConfigSatelit(S, fel, v):
	"""Ca ecranul de pe televizor la Verde (_scrie_config): ultimele valori raman pentru data viitoare, si pe
	televizor, si in pagina."""
	c = S._citeste_config()
	c.pop("tip", None)
	for cheie in list(c.keys()):
		if cheie in v and cheie not in ("operator", "operator_dvbt2", "operator_dab"):
			c[cheie] = str(v[cheie])
	if fel in S.CAMP_OPERATOR and v.get("operator"):
		c[S.CAMP_OPERATOR[fel]] = str(v["operator"])
	c["fel"] = fel
	S._scrie_config(c)


def _salveazaConfigCabluTerestru(scaner, M, fel, v):
	import Screens.ScanerCablu as C
	clasa = M.ScanerCablu if scaner == "cablu" else M.ScanerTerestru
	c = C.citeste_config(clasa.CALE_CONFIG, M.config_implicit())
	for cheie in list(c.keys()):
		if cheie in v:
			c[cheie] = str(v[cheie])
	c["fel"] = fel
	# cautarea pornita din pagina cu un operator = alegerea omului (ca _la_schimbare pe televizor): nu se mai muta
	if fel == "operator" and "operator_ales" in c:
		c["operator_ales"] = "1"
	C.scrie_config(clasa.CALE_CONFIG, c, clasa.ANTET_CONFIG)


def _pornesteFluxuri(S, sesiune, rez):
	"""DVB-T2 / DAB+ prin satelit, dupa confirmarea din pagina: ecranul scanarii se deschide pe televizor cu cautarea
	pornita (fata „in curs"). -> None sau textul refuzului."""
	try:
		from Screens.HdsScanareFluxuri import HdsScanareFluxuri
		dlg = sesiune.open(HdsScanareFluxuri, rez, True)
	except Exception as eroare:
		_jurnal("ecranul scanarii DAB+/DVB-T2 nu s-a deschis: %s" % eroare)
		return _t("Ecranul scanării nu s-a deschis pe televizor (%s). Încearcă din nou.") % eroare
	if dlg is None:
		return _t("Ecranul scanării nu s-a deschis pe televizor. Detalii în jurnalul receptorului.")
	_LUCRU["fluxuri"] = dlg
	_urmaresteFluxuri(dlg)
	return None


def fluxuri(actiune, post=None):
	"""Alegerea din pagina pentru ecranul scanarii DVB-T2 / DAB+ de pe televizor: „asculta" (postul cu numarul
	`post` din lista gasita; antena ramane pe satelitul scanat), „inapoi" (canalul de dinainte), „din_nou" (aceeasi
	scanare inca o data) sau „porneste" (fata „inainte" deschisa din telecomanda). Ca tastele de pe televizor."""
	sesiune = _sesiune()
	dlg, _din_web = _dialogFluxuri(sesiune)
	if dlg is None:
		return {"result": False, "message": _t("Nicio scanare DAB+ sau DVB-T2 nu e deschisă pe televizor."),
			"stare": stare()}
	if getattr(sesiune, "current_dialog", None) is not dlg:
		return {"result": False, "message": (_t("Pe televizor e deschisă altă fereastră peste scanare. Închide-o întâi "
			"(tasta EXIT), apoi încearcă din nou.")), "stare": stare()}
	try:
		if actiune == "asculta" and dlg.fata == "sfarsit":
			try:
				index = int(post)
			except (TypeError, ValueError):
				index = -1
			ok, motiv = dlg.asculta(index)
			return {"result": bool(ok), "message": _t("Pornit pe televizor.") if ok else (motiv or ""),
				"stare": stare()}
		if actiune == "inapoi" and dlg.fata == "sfarsit":
			dlg.inapoi()
			return {"result": True, "message": _t("Canalul de dinainte pornește pe televizor."), "stare": stare()}
		if actiune == "din_nou" and dlg.fata == "sfarsit":
			dlg.din_nou()
			return {"result": True, "message": _t("Scanarea a pornit din nou pe televizor."), "stare": stare()}
		if actiune == "porneste" and dlg.fata == "inainte":
			dlg.porneste()
			return {"result": True, "message": _t("Scanarea a pornit pe televizor."), "stare": stare()}
	except Exception as eroare:
		_jurnal("alegerea %s la scanarea DAB+/DVB-T2: %s" % (actiune, eroare))
		return {"result": False, "message": _t("Pe receptor a apărut o eroare: %s") % eroare, "stare": stare()}
	return {"result": False, "message": _t("Acum nu se poate face asta: ecranul de pe televizor e la alt pas."),
		"stare": stare()}


def porneste(scaner, fel, cerere=None, confirmat=False):
	"""Porneste pe televizor felul de scanare ales, cu valorile date. Acelasi drum ca Verde in ecran: pregateste(),
	apoi ServiceScan (sau CautareFluxuri la DVB-T2 si DAB+ prin satelit). Doua raspunsuri cer inca un pas din pagina:
	„intrebare" (o scanare lunga sau DVB-T2 pe care nucleul nu il stie inca: se porneste numai cu confirmat) si
	„de_ales" (DVB-S2 fara FEC: se alege modulatia si FEC-ul, apoi se trimite din nou)."""
	M = _modulScaner(scaner)
	if M is None:
		return {"result": False, "message": _t("Scaner necunoscut: %s.") % scaner}
	feluri = [f for f, _n in M.FELURI] if scaner == "satelit" else list(M.FELURI)
	if fel not in feluri:
		return {"result": False, "message": _t("Felul de scanare „%s” nu există la %s.") % (fel, scaner)}
	sesiune = _sesiune()
	refuz = _ocupat(sesiune)
	if refuz:
		return {"result": False, "message": refuz, "stare": stare()}
	if scaner == "satelit":
		v = _valoriSatelit(M, fel, cerere)
		_campuriSatelit(M, fel, v)          # aceleasi normalizari ca in ecran (satelitul, transponderul, operatorul)
		rez = M.pregateste(fel, _valoriPregateste(M, fel, v))
	else:
		v = _valoriCabluTerestru(scaner, M, fel, cerere)
		_campuriCabluTerestru(M, fel, v)
		rez = M.pregateste(fel, v)
	if rez.get("eroare"):
		return {"result": False, "message": rez["eroare"]}
	if rez.get("de_ales"):
		return {"result": False, "message": rez.get("text", ""),
			"de_ales": [{"text": text, "mod": str(mf[0]), "fec": str(mf[1])} for text, mf in rez["de_ales"]]}
	if rez.get("intrebare") and not confirmat:
		return {"result": False, "message": rez.get("text", ""), "intrebare": rez["intrebare"]}
	if "hdscomun" in rez and not confirmat:
		# DVB-T2 / DAB+: intai planul (unde se roteste antena si cat dureaza), ca pe televizor, apoi confirmarea
		plan = _planFluxuri(M, rez) or {"randuri": [], "text": rez.get("text", "")}
		return {"result": False, "message": rez.get("text", ""), "intrebare": plan["text"], "plan": plan["randuri"],
			"buton_da": _t("Pornește scanarea")}
	_LUCRU.update(scaner=scaner, fel=fel, titlu=_numeFel(scaner, fel), text=rez.get("text", ""),
		pornit=time.time(), final=None, fluxuri=None)
	if "hdscomun" in rez:
		eroare = _pornesteFluxuri(M, sesiune, rez)
		if eroare:
			return {"result": False, "message": eroare}
		_salveazaConfigSatelit(M, fel, v)
		return {"result": True, "message": rez.get("text", ""), "stare": stare()}
	try:
		if scaner == "satelit":
			for tp in rez["transpondere"]:
				motiv = M.motiv_refuz(tp)      # poarta finala, ca ScanerSatelit._porneste
				if motiv:
					return {"result": False, "message": _t("Transponderul %s nu poate fi căutat: %s.") % (
						M._descriere_tp(tp), motiv)}
			from enigma import eDVBFrontendParametersSatellite
			lista = [{"transponders": [M.in_parametri(eDVBFrontendParametersSatellite, tp) for tp in rez["transpondere"]],
				"feid": rez["slot"], "flags": rez["flags"], "hds_fel": "satelit/%s" % fel}]   # felul, pentru /api/scanare-ultima
		else:
			lista = M.cerere_scanare(rez)
		from Screens.ServiceScan import ServiceScan
		dlg = sesiune.open(ServiceScan, lista)
	except Exception as eroare:
		# Session.open cade daca televizorul e chiar intre doua ferestre (in_exec fals); se poate incerca din nou
		_jurnal("ServiceScan nu s-a deschis: %s" % eroare)
		return {"result": False, "message": _t("Ecranul de căutare nu s-a deschis pe televizor (%s). Încearcă din "
			"nou.") % eroare}
	if dlg is None:
		return {"result": False, "message": _t("Ecranul de căutare nu s-a deschis pe televizor. Detalii în jurnalul "
			"receptorului.")}
	_LUCRU["dialog"] = dlg
	_urmareste(dlg)
	try:
		if scaner == "satelit":
			_salveazaConfigSatelit(M, fel, v)
		else:
			_salveazaConfigCabluTerestru(scaner, M, fel, v)
	except Exception as eroare:
		_jurnal("ultimele valori nu s-au salvat: %s" % eroare)
	_jurnal("cautare pornita din web: %s/%s" % (scaner, fel))
	return {"result": True, "message": rez.get("text", ""), "stare": stare()}


def opreste():
	"""Opreste cautarea (sau inchide rezultatul ramas pe televizor), ca tasta Exit in ServiceScan. La scanarea
	DVB-T2 / DAB+: in timpul ei o opreste, iar la sfarsit inseamna „Înapoi la canalul meu" (acelasi lucru ca EXIT
	pe televizor, unde e scris pe tasta rosie)."""
	sesiune = _sesiune()
	dlgf, _din_web = _dialogFluxuri(sesiune)
	if dlgf is not None:
		if getattr(sesiune, "current_dialog", None) is not dlgf:
			return {"result": False, "message": (_t("Pe televizor e deschisă altă fereastră peste scanare. Închide-o "
				"întâi (tasta EXIT), apoi încearcă din nou.")), "stare": stare()}
		fata = dlgf.fata
		try:
			dlgf.iesire()
		except Exception as eroare:
			_jurnal("oprirea scanarii DAB+/DVB-T2: %s" % eroare)
			return {"result": False, "message": _t("Scanarea nu s-a oprit (%s).") % eroare, "stare": stare()}
		if fata == "in_curs":
			text = _t("Scanarea s-a oprit. Canalul de dinainte pornește din nou.")
		elif fata == "sfarsit":
			text = _t("Canalul de dinainte pornește pe televizor.")
		else:
			text = _t("Scanarea nu a pornit.")
		return {"result": True, "message": text, "stare": stare()}
	dlg, _din_web = _dialogScanare(sesiune)
	if dlg is None:
		return {"result": False, "message": _t("Nicio căutare deschisă pe televizor."), "stare": stare()}
	if getattr(sesiune, "current_dialog", None) is not dlg:
		# Session.close cere ca fereastra sa fie cea din fata; altfel s-ar inchide abia cand iese cea de deasupra
		return {"result": False, "message": (_t("Pe televizor e deschisă altă fereastră peste căutare. Închide-o "
			"întâi (tasta Exit), apoi încearcă din nou.")), "stare": stare()}
	try:
		gata = bool(dlg.get("scan") is not None and dlg["scan"].isDone())
	except Exception:
		gata = False
	try:
		dlg.close()
	except Exception as eroare:
		_jurnal("inchiderea ferestrei de scanare: %s" % eroare)
		return {"result": False, "message": _t("Fereastra de căutare nu s-a închis (%s).") % eroare, "stare": stare()}
	return {"result": True, "message": _t("Rezultatul s-a închis pe televizor.") if gata else _t("Căutarea s-a oprit."),
		"stare": stare()}


def deschidePeTelevizor(id_intrare):
	"""Deschide pe televizor ecranul unei intrari din cele doua sectiuni (Setari tuner, Configurare LNB, ...). Numai
	intrari din menu.xml, dupa entryID; modulul, ecranul si argumentele vin din menu.xml, nu din cerere."""
	nod, sectiune = _intrareDupaId(id_intrare)
	if nod is None:
		return {"result": False, "message": _t("Intrarea „%s” nu e în secțiunile de scanare și antenă.") % id_intrare}
	tinta = _tinta(nod)
	if not _seDeschidePeTelevizor(tinta):
		return {"result": False, "message": _t("Această intrare se deschide numai din telecomandă.")}
	sesiune = _sesiune()
	refuz = _ocupat(sesiune)
	if refuz:
		return {"result": False, "message": refuz}
	salveaza = bool(sectiune is not None and sectiune.get("flushConfigOnClose"))

	def _laIesire(*_rezultat):
		# nodul din meniu salveaza setarile la iesire (flushConfigOnClose); deschis din web, la fel
		if salveaza:
			try:
				from Components.config import configfile
				configfile.save()
			except Exception as eroare:
				_jurnal("salvarea setarilor dupa %s: %s" % (id_intrare, eroare))

	try:
		import importlib
		modul = importlib.import_module("Screens." + tinta["modul"])
		ecran = getattr(modul, tinta["ecran"])
		dlg = sesiune.openWithCallback(_laIesire, ecran, *tinta["argumente"])
	except Exception as eroare:
		_jurnal("deschiderea %s pe televizor: %s" % (id_intrare, eroare))
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor (%s).") % eroare}
	if dlg is None:
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor. Detalii în jurnalul "
			"receptorului.")}
	return {"result": True, "message": _t("S-a deschis pe televizor: %s.") % _t(nod.get("text") or "")}


# ------------------------------------------------------------------ antena (numai citire)
def _valoareConfig(sectiune, nume, implicit=None):
	try:
		return getattr(sectiune, nume).value
	except Exception:
		return implicit


# tipul din Components/HdsLnb.py -> valoarea lui advanced.lnb[k].lof, ca in cartela
_FEL_DIN_TIP = {"universal": "universal_lnb", "banda_c": "c_band", "unicable": "unicable"}


def _lnbDinModel(slot):
	"""LNB-urile tunerului din Components/HdsLnb.py (aceeasi citire ca „Configurare LNB”), cu „toți sateliții”
	(sat[3601..3604] spre LNB 33..36, gruparea din updateAdvanced) inclus:
	dupa o trecere in modul avansat cu motor, satelitii nu au LNB anume, iar citirea de mai jos nu gasea nimic."""
	from Components import HdsLnb
	rez = []
	for l in HdsLnb.citeste(slot)["lnburi"]:
		intrare = {"numar": l["numar"], "fel": _FEL_DIN_TIP.get(l["tip"], "user_defined"), "sateliti": list(l["sateliti"]),
			"toti": bool(l["toti"]), "lof_jos": l["lofl"], "lof_sus": l["lofh"], "prag": l["prag"]}
		if l["tip"] == "banda_c":
			intrare["prag"] = None
		rez.append(intrare)
	return rez


def _lnbTuner(cfg, mod, pozitii, slot=None):
	"""LNB-ul asa cum il vede nucleul: in modul simplu e mereu universal (NimManager.addLNBSimple); in modul
	avansat, LNB-urile din Components/HdsLnb.py (cu „toți sateliții”), altfel LNB-ul fiecarui satelit, din
	config.Nims[n].advanced."""
	if mod == "simple":
		return [dict(LNB_UNIVERSAL, fel="universal_lnb", sateliti=[])]
	if mod != "advanced":
		return []
	if slot is not None:
		try:
			din_model = _lnbDinModel(slot)
			if din_model:
				return din_model
		except Exception as eroare:
			_jurnal("LNB-urile tunerului %s: %s" % (slot, eroare))
	pe_lnb = {}
	for p in pozitii:
		try:
			numar = int(cfg.advanced.sat[p].lnb.value)
		except Exception:
			continue
		if numar:
			pe_lnb.setdefault(numar, []).append(p)
	rez = []
	for numar in sorted(pe_lnb):
		try:
			lnb = cfg.advanced.lnb[numar]
		except Exception:
			continue
		fel = _valoareConfig(lnb, "lof", "")
		intrare = {"numar": numar, "fel": fel, "sateliti": pe_lnb[numar]}
		if fel == "universal_lnb":
			intrare.update(LNB_UNIVERSAL)
		elif fel == "c_band":
			intrare.update(lof_jos=5150, lof_sus=5150, prag=None)
		elif fel == "user_defined":
			intrare.update(lof_jos=_valoareConfig(lnb, "lofl"), lof_sus=_valoareConfig(lnb, "lofh"),
				prag=_valoareConfig(lnb, "threshold"))
		rez.append(intrare)
	return rez


def _coordonateUsals(cfg):
	try:
		lat = float(cfg.latitude.float)
		lon = float(cfg.longitude.float)
	except Exception:
		return None
	if _valoareConfig(cfg, "latitudeOrientation", "north") != "north":
		lat = -lat
	if _valoareConfig(cfg, "longitudeOrientation", "east") != "east":
		lon = -lon
	return {"latitudine": round(lat, 3), "longitudine": round(lon, 3)}


def _tunere():
	from Components.NimManager import nimmanager
	try:
		from Components.config import config
		nims = config.Nims
	except Exception:
		nims = None
	from Screens.ScanerSatelit import text_pozitie
	tunere = []
	for n in getattr(nimmanager, "nim_slots", []) or []:
		t = {"slot": n.slot, "litera": chr(ord("A") + n.slot), "descriere": "", "mod": "",
			"satelit": False, "cablu": False, "terestru": False}
		try:
			t["descriere"] = n.friendly_full_description
		except Exception:
			pass
		try:
			t["mod"] = n.config_mode
		except Exception:
			pass
		for cheie, tip in (("satelit", "DVB-S"), ("cablu", "DVB-C"), ("terestru", "DVB-T")):
			try:
				t[cheie] = bool(n.isCompatible(tip))
			except Exception:
				pass
		if t["satelit"]:
			try:
				sateliti = [(x[0], x[1]) for x in nimmanager.getSatListForNim(n.slot) or []]
			except Exception:
				sateliti = []
			try:
				t["motor"] = bool(nimmanager.getRotorSatListForNim(n.slot))
			except Exception:
				t["motor"] = False
			t["sateliti"] = [{"pozitie": p, "text": text_pozitie(p), "nume": nume} for p, nume in sateliti]
			cfg = None
			try:
				cfg = nims[n.slot]
			except Exception:
				cfg = None
			if cfg is not None:
				t["diseqc"] = _valoareConfig(cfg, "diseqcMode", "") if t["mod"] == "simple" else ""
				if t["mod"] == "simple" and t["diseqc"] == "positioner" and _locStabilit():
					t["usals"] = _coordonateUsals(cfg)
					if t["usals"]:
						# scris de receptor, ca pe televizor (Components/HdsGrade.py): „45,300 N, 23,270 E”
						from Components import HdsGrade
						t["usals_text"] = HdsGrade.coordonate(t["usals"]["latitudine"], t["usals"]["longitudine"], 3)
				t["lnb"] = _lnbTuner(cfg, t["mod"], [p for p, _n in sateliti], n.slot)
		tunere.append(t)
	return tunere


def _semnal():
	"""Semnalul canalului care ruleaza acum (tunerul, prinderea, calitatea, SNR-ul, puterea), din frontendInfo al
	serviciului. La serviciu getFrontendStatus() nu are argument si intoarce dictionarul (lib/service/iservice.h)."""
	rez = {"are": False}
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		serviciu = nav.getCurrentService() if nav is not None else None
		info = serviciu.frontendInfo() if serviciu is not None else None
		if info is None:
			return rez
		st = info.getFrontendStatus() or {}
		date = info.getFrontendData() or {}
	except Exception as eroare:
		_jurnal("semnalul nu se poate citi: %s" % eroare)
		return rez
	rez["are"] = True
	try:
		from ServiceReference import ServiceReference
		rez["canal"] = ServiceReference(nav.getCurrentlyPlayingServiceReference()).getServiceName()
	except Exception:
		rez["canal"] = ""

	def procent(cheie):
		try:
			return max(0, min(100, int(st.get(cheie)) * 100 // 65536))
		except (TypeError, ValueError):
			return None

	rez["stare"] = str(st.get("tuner_state") or "")
	rez["prins"] = bool(st.get("tuner_locked"))
	rez["calitate"] = procent("tuner_signal_quality")
	rez["putere"] = procent("tuner_signal_power")
	try:
		db = st.get("tuner_signal_quality_db")
		rez["snr_db"] = None if db is None else round(int(db) / 100.0, 1)
	except (TypeError, ValueError):
		rez["snr_db"] = None
	try:
		rez["ber"] = int(st.get("tuner_bit_error_rate"))
	except (TypeError, ValueError):
		rez["ber"] = None
	try:
		rez["tuner"] = chr(ord("A") + int(date.get("tuner_number")))
	except (TypeError, ValueError):
		rez["tuner"] = ""
	return rez


def _numarDinText(text, minim, maxim):
	try:
		x = float(str(text).replace(",", "."))
	except (TypeError, ValueError):
		return None
	if x != x or not minim <= x <= maxim:
		return None
	return x


def _locStabilit():
	"""locul antenei (Components/HdsLocul.py): fara el copiile din Setari tuner sunt neutre si nu se arata"""
	try:
		from Components import HdsLocul
		return HdsLocul.stabilit()
	except Exception:
		return False


def _calculator(lat=None, lon=None):
	"""Unghiurile antenei spre fiecare satelit din satellites.xml, cu formula calculatorului de pe televizor
	(Screens/PositionerSetup.py). Locul: cel dat in cerere, altfel locul antenei (Components/HdsLocul.py, acelasi ca
	pe televizor si ca la motorul USALS). Numai citire: locul din cerere nu se salveaza."""
	from Screens.PositionerSetup import calculeazaUnghiuri, orbpozToGrade, initConfigPositioner
	from Components.NimManager import nimmanager
	from Components.config import config
	from Screens.ScanerSatelit import text_pozitie
	from Components import HdsGrade
	initConfigPositioner()
	lat_cerut = _numarDinText(lat, -90, 90) if lat not in (None, "") else None
	lon_cerut = _numarDinText(lon, -180, 180) if lon not in (None, "") else None
	rez = {"sursa": "setari", "eroare": ""}
	if (lat not in (None, "") and lat_cerut is None) or (lon not in (None, "") and lon_cerut is None):
		rez["eroare"] = _t("Latitudinea se scrie între -90 și 90, longitudinea între -180 și 180 (grade, cu virgulă "
			"sau punct).")
	if lat_cerut is not None and lon_cerut is not None:
		rez.update(sursa="cerere", latitudine=lat_cerut, longitudine=lon_cerut)
	else:
		from Components import HdsLocul
		loc = HdsLocul.grade()
		if loc is None:
			rez.update(sursa="nestabilit", sateliti=[], eroare=_t("Locul antenei nu e stabilit. Alege-l în pagina "
				"Locul "
				"antenei (/antena/locul); aici se poate calcula și pentru un loc scris mai sus."), latitudine=0.0,
				longitudine=0.0)
			return rez
		rez["latitudine"], rez["longitudine"] = loc
	sateliti = []
	for x in getattr(nimmanager, "satList", None) or []:
		pozitie, nume = x[0], x[1]
		az, el, skew = calculeazaUnghiuri(rez["latitudine"], rez["longitudine"], orbpozToGrade(pozitie))
		# unghiurile si ca text, cu separatorul limbii meniului, ca pe televizor (Screens/PositionerSetup.py)
		sateliti.append({"pozitie": pozitie, "text": text_pozitie(pozitie), "nume": nume, "azimut": round(az, 1),
			"elevatie": round(el, 1), "skew": round(skew, 1), "vizibil": el > 0,
			"azimut_text": HdsGrade.numar(az, 1) + u"°", "elevatie_text": HdsGrade.numar(el, 1) + u"°",
			"skew_text": HdsGrade.numar(skew, 1) + u"°"})
	sateliti.sort(key=lambda s: orbpozToGrade(s["pozitie"]))
	rez["sateliti"] = sateliti
	return rez


def antena(lat=None, lon=None, doar=""):
	"""Datele sectiunii „Orientarea și setarea antenei": tunerele (modul, satelitii, motorul, LNB-ul), semnalul
	canalului curent si unghiurile antenei. Numai citire; setarile se schimba din ecranele de pe televizor."""
	rez = {"result": True}
	if doar == "semnal":
		rez["semnal"] = _semnal()
		return rez
	try:
		rez["tunere"] = _tunere()
	except Exception as eroare:
		_jurnal("tunerele: %s" % eroare)
		rez["tunere"] = []
	rez["semnal"] = _semnal()
	try:
		rez["calculator"] = _calculator(lat, lon)
	except Exception as eroare:
		_jurnal("calculatorul de unghiuri: %s" % eroare)
		rez["calculator"] = {"eroare": _t("Calculatorul nu a mers: %s") % eroare, "sateliti": []}
	try:
		from Components import HdsLocul
		rez["locul"] = HdsLocul.stare()
	except Exception as eroare:
		_jurnal("locul antenei: %s" % eroare)
		rez["locul"] = {"stabilit": False, "text": ""}
	return rez


# ------------------------------------------------------------------ cererea HTTP
def argumente(request):
	"""Argumentele cererii (adresa si corpul formularului), ca text: {cheie: text}, iar "pozitii" ca lista. Fara
	jeton, cel mult MAX_ARGUMENTE chei, numai chei scurte din litere mici, cifre si _."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:MAX_ARGUMENTE]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 40 or not all(c.islower() or c.isdigit() or c == "_" for c in cheie):
			continue
		texte = []
		for v in (valori or [])[:MAX_POZITII]:
			if isinstance(v, bytes):
				v = v.decode("utf-8", "replace")
			texte.append(str(v)[:MAX_TEXT_ARGUMENT].strip())
		if cheie == "pozitii":
			rez[cheie] = texte
		else:
			rez[cheie] = texte[0] if texte else ""
	return rez


def rute(baza, resource, NOT_DONE_YET):
	"""Resursele: (rutele de sub /api, resursa paginii). `baza` e HdsJsonResource din plugin.py: fiecare cerere trece
	prin aceeasi poarta ca restul interfetei; `schimbaCeva = True` la ce porneste sau opreste ceva pe televizor."""

	_ceasuri = []           # eTimer-ele in curs; fara referinta pastrata, GC-ul le culege si raspunsul nu mai vine
	_legaturi = []          # variantele vechi de SWIG cer pastrarea obiectului de conexiune

	class _PeFir(baza):
		"""Citirea listelor mari pe un fir separat, apoi raspunsul pe firul enigma2, dupa un eTimer (tiparul de la
		fonturi, fara reactor.callLater). `citire` atinge numai fisiere; `lucru` ruleaza pe firul enigma2."""

		TIMEOUT_S = 60

		def _peFir(self, request, citire, lucru):
			from enigma import eTimer
			rezultat_fir = {}
			pornit = time.time()

			def _fir():
				try:
					citire()
					rezultat_fir["gata"] = True
				except Exception as eroare:
					rezultat_fir["eroare"] = str(eroare)

			def _trimite(corp, cod=200):
				try:
					request.setResponseCode(cod)
					request.setHeader(b"content-type", b"application/json; charset=utf-8")
					request.setHeader(b"cache-control", b"no-store")
					request.write(json.dumps(corp, ensure_ascii=False).encode("utf-8", "replace"))
					request.finish()
				except Exception as eroare:
					_jurnal("nu am putut trimite raspunsul (client plecat?): %s" % eroare)

			ceas = eTimer()
			_ceasuri.append(ceas)

			def _opreste():
				try:
					ceas.stop()
				except Exception:
					pass
				try:
					_ceasuri.remove(ceas)
				except ValueError:
					pass

			def _verifica():
				if "gata" in rezultat_fir or "eroare" in rezultat_fir:
					_opreste()
					if "eroare" in rezultat_fir:
						# o lista care nu se poate citi nu opreste cererea: scanerul spune singur ce lipseste
						_jurnal("citirea listelor: %s" % rezultat_fir["eroare"])
					try:
						corp = lucru()
					except Exception as eroare:
						_jurnal("eroare: %s" % eroare)
						_trimite({"result": False, "message": _t("Eroare pe receptor: %s") % eroare}, 500)
						return
					_trimite(corp)
				elif time.time() - pornit > self.TIMEOUT_S:
					_opreste()
					_trimite({"result": False, "message": _t("Citirea listelor a durat prea mult.")}, 504)

			try:
				ceas.callback.append(_verifica)
			except AttributeError:
				_legaturi.append(ceas.timeout.connect(_verifica))
			threading.Thread(target=_fir, daemon=True).start()
			ceas.start(100, False)
			return NOT_DONE_YET

	class ScanareResource(_PeFir):
		"""GET /api/scanare: fara `scaner`, cele doua sectiuni din menu.xml si starea cautarii; cu `scaner` si `fel`,
		randurile felului, cu valorile date si previzualizarea. Numai citire."""

		def render_GET(self, request):
			cerere = argumente(request)
			scaner = cerere.pop("scaner", "")
			fel = cerere.pop("fel", "")
			if not scaner:
				return self._raspunde(request, {"result": True, "sectiuni": structura(), "stare": stare()})
			if scaner not in SCANERE:
				return self._eroare(request, _t("Scaner necunoscut: %s.") % scaner)
			cai = caiDeCitit(scaner)
			return self._peFir(request, lambda: incalzeste(scaner, cai), lambda: campuri(scaner, fel, cerere))

	class PornesteResource(_PeFir):
		"""POST /api/scanare-porneste?scaner=&fel=&...: porneste cautarea pe televizor. Cu `confirmat=1` dupa o
		intrebare. Schimba ceva pe receptor: cu cookie cere POST, aceeasi origine si antetul CSRF."""
		schimbaCeva = True

		def render_POST(self, request):
			cerere = argumente(request)
			scaner = cerere.pop("scaner", "")
			fel = cerere.pop("fel", "")
			confirmat = cerere.pop("confirmat", "") in ("1", "da", "true")
			if scaner not in SCANERE:
				return self._eroare(request, _t("Scaner necunoscut: %s.") % scaner)
			cai = caiDeCitit(scaner)
			return self._peFir(request, lambda: incalzeste(scaner, cai),
				lambda: porneste(scaner, fel, cerere, confirmat))

		def render_GET(self, request):
			return self.render_POST(request)     # numai cu ?token= (scripturi); din browser poarta cere POST

	class StareResource(baza):
		"""GET /api/scanare-stare: starea cautarii (procent, canale, transpondere, timp ramas, rezultat)."""

		def render_GET(self, request):
			st = stare()
			st["result"] = True
			return self._raspunde(request, st)

	class UltimaResource(baza):
		"""GET /api/scanare-ultima: rezultatul ultimei scanari de servicii (transponderele incercate si toate serviciile
		citite din SDT, vechi si noi), tinut pana la scanarea urmatoare. Numai citire: lista de canale si lamedb nu se
		ating. Fara nicio scanare de la pornire: 200 cu result false (ruta exista, nu e nimic de dat)."""

		def render_GET(self, request):
			octeti = ultima()
			if octeti is None:
				return self._raspunde(request, {"result": False, "message": _t(MESAJ_FARA_SCANARE)})
			request.setResponseCode(200)
			request.setHeader(b"content-type", b"application/json; charset=utf-8")
			request.setHeader(b"cache-control", b"no-store")
			return octeti

	class OpresteResource(baza):
		"""POST /api/scanare-opreste: opreste cautarea sau inchide rezultatul ramas pe televizor."""
		schimbaCeva = True

		def render_POST(self, request):
			return self._raspunde(request, opreste())

		def render_GET(self, request):
			return self.render_POST(request)

	class FluxuriResource(baza):
		"""POST /api/scanare-fluxuri?actiune=asculta&post=<n> | inapoi | din_nou | porneste: alegerea pentru ecranul
		scanarii DVB-T2 / DAB+ de pe televizor. Schimba ceva pe receptor: cu cookie cere POST si antetul CSRF."""
		schimbaCeva = True

		def render_POST(self, request):
			cerere = argumente(request)
			return self._raspunde(request, fluxuri(cerere.get("actiune", ""), cerere.get("post")))

		def render_GET(self, request):
			return self.render_POST(request)     # numai cu ?token= (scripturi); din browser poarta cere POST

	class TelevizorResource(baza):
		"""POST /api/scanare-televizor?id=<entryID>: deschide pe televizor ecranul unei intrari din cele doua sectiuni."""
		schimbaCeva = True

		def render_POST(self, request):
			return self._raspunde(request, deschidePeTelevizor(argumente(request).get("id", "")))

		def render_GET(self, request):
			return self.render_POST(request)

	class AntenaResource(baza):
		"""GET /api/antena[?lat=&lon=][&doar=semnal]: tunerele, LNB-ul, semnalul si unghiurile. Numai citire."""

		def render_GET(self, request):
			cerere = argumente(request)
			return self._raspunde(request, antena(cerere.get("lat"), cerere.get("lon"), cerere.get("doar", "")))

	class PaginaResource(resource.Resource):
		"""GET /scanare[/...] si /antena[/...]: aceeasi pagina, cu sectiunea si felul luate din adresa."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"scanare": ScanareResource(),
		b"scanare-porneste": PornesteResource(),
		b"scanare-stare": StareResource(),
		b"scanare-ultima": UltimaResource(),
		b"scanare-opreste": OpresteResource(),
		b"scanare-fluxuri": FluxuriResource(),
		b"scanare-televizor": TelevizorResource(),
		b"antena": AntenaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /ecrane: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
	neconectat primeste pagina de asociere. Pagina porneste cautari, deci cu cookie primeste tokenul CSRF."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")   # jetonul de pe SERVER, nu cel primit
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", P._STIL_COMUN).replace("__CONFIG__",
		config_pagina).encode("utf-8", "replace")


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scanare și antenă</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .file{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px;}
  .file button{flex:1 1 90px;min-height:44px;padding:10px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .file button[aria-selected="true"]{background:var(--accent);border-color:var(--accent);color:#fff;}
  .feluri{display:grid;grid-template-columns:1fr;gap:8px;margin:0 0 12px;}
  @media(min-width:560px){.feluri{grid-template-columns:1fr 1fr;}}
  .feluri button{min-height:44px;padding:10px 12px;border-radius:8px;border:1px solid var(--bordura);background:var(--panou);color:var(--text);font:inherit;text-align:left;cursor:pointer;}
  .feluri button[aria-pressed="true"]{border-color:var(--accent);box-shadow:inset 4px 0 0 var(--accent);}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .card h2{font-size:1rem;margin:0 0 10px;}
  .card.evidentiat{border-color:var(--accent);}
  label.eticheta{display:block;margin:12px 0 4px;color:var(--text-slab);font-size:.9rem;}
  select,input.text{width:100%;min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font-size:16px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .bife{max-height:340px;overflow:auto;border:1px solid var(--bordura);border-radius:8px;padding:4px 10px;background:#0f1216;}
  .bife label{display:flex;gap:10px;align-items:center;min-height:38px;font-size:.95rem;cursor:pointer;}
  .bife input{width:20px;height:20px;flex:none;}
  .previz{margin:14px 0 0;padding:10px 12px;border-radius:8px;background:#0f1216;line-height:1.45;font-size:.92rem;min-height:1.4em;}
  .eroare{color:#ffb4a8;}
  .inlucru{margin:8px 0 4px;padding:10px 12px;border:1px solid var(--galben);border-radius:8px;line-height:1.45;font-size:.9rem;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
  .buton{min-height:44px;padding:10px 18px;border-radius:8px;border:none;background:var(--accent);color:#fff;font:inherit;cursor:pointer;}
  .buton.secundar{background:transparent;border:1px solid var(--bordura);color:var(--text);}
  .buton[disabled]{opacity:.5;cursor:default;}
  a.buton{display:inline-flex;align-items:center;text-decoration:none;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;}
  .intrebare{margin:12px 0 0;padding:12px;border:1px solid var(--galben);border-radius:8px;line-height:1.45;}
  .intrebare label{display:flex;gap:10px;align-items:center;min-height:38px;cursor:pointer;}
  .bara{height:14px;border-radius:7px;background:#0f1216;border:1px solid var(--bordura);overflow:hidden;margin:4px 0 10px;}
  .bara div{height:100%;width:0;background:var(--accent);transition:width .4s;}
  .linie{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--bordura);font-size:.92rem;}
  .linie:last-child{border-bottom:none;}
  .linie span:first-child{color:var(--text-slab);flex:none;}
  .linie span:last-child{text-align:right;overflow-wrap:anywhere;}
  ul.rezultat{margin:8px 0 0;padding-left:20px;line-height:1.5;}
  .retea{margin:12px 0 0;padding:12px 14px;border:1px solid var(--bordura);border-radius:10px;line-height:1.5;}
  .retea small{display:block;color:var(--text-slab);font-size:.8rem;letter-spacing:.04em;}
  .retea b{display:block;font-size:1.3rem;margin:2px 0 4px;overflow-wrap:anywhere;}
  .retea table{border-collapse:collapse;width:100%;font-size:.88rem;font-variant-numeric:tabular-nums;margin:6px 0 0;}
  .retea td,.retea th{padding:4px 6px;border-bottom:1px solid var(--bordura);text-align:right;}
  .retea th{color:var(--text-slab);font-weight:600;white-space:normal;overflow-wrap:normal;word-break:keep-all;font-size:.82rem;}
  html.hds-cadru .retea table th{text-transform:none;letter-spacing:0;}
  .retea .tabel{max-width:100%;overflow-x:auto;}
  .retea summary{cursor:pointer;min-height:44px;line-height:44px;}
  .plan{margin:10px 0 0;}
  .plan .nota{margin-top:8px;}
  .posturi{margin:10px 0 0;border-top:1px solid var(--bordura);}
  #textBrut{margin:10px 0 0;} #textBrut summary{cursor:pointer;min-height:44px;line-height:44px;}
  pre.brut{font-family:monospace;font-size:.78rem;line-height:1.4;white-space:pre-wrap;word-break:break-word;max-height:360px;overflow:auto;margin:0;}
  .post{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .post div{flex:1;min-width:0;}
  .post b{display:block;font-weight:600;overflow-wrap:anywhere;}
  .post small{color:var(--text-slab);}
  .post .buton{flex:none;min-height:40px;padding:8px 14px;}
  .grupaPosturi{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:14px 0 6px;border-bottom:2px solid var(--bordura);}
  .grupaPosturi b{font-weight:700;overflow-wrap:anywhere;}
  .grupaPosturi small{color:var(--text-slab);flex:none;}
  .tabel{overflow-x:auto;}
  table{width:100%;border-collapse:collapse;font-size:.9rem;}
  td,th{padding:6px 4px;border-bottom:1px solid var(--bordura);text-align:left;vertical-align:top;}
  th{color:var(--text-slab);font-weight:normal;white-space:nowrap;}
  .subtitlu{margin:14px 0 2px;font-weight:600;}
  .subtitlu:first-of-type{margin-top:0;}
  .doua{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
  .ascuns{display:none !important;}
  footer{margin:16px 0 0;color:var(--text-slab);font-size:.85rem;display:flex;flex-wrap:wrap;gap:8px 18px;}
</style>
</head>
<body>
<main>
<h1>Scanare și antenă</h1>
<div class="file" role="tablist" id="sectiuni"></div>
<div class="mesaj" id="incarcare" role="status">Se citește meniul receptorului...</div>

<section id="panouScanare" class="ascuns">
  <div class="file" role="tablist" id="grupuri"></div>
  <div class="feluri" id="feluri"></div>
  <div class="card ascuns" id="formular">
    <h2 id="titluFel"></h2>
    <p class="inlucru ascuns" id="inLucru" role="note"></p>
    <form id="campuri" autocomplete="off" onsubmit="return false"></form>
    <div class="previz" id="previz" role="status"></div>
    <div class="intrebare ascuns" id="intrebare">
      <div id="intrebareText"></div>
      <div id="deAles"></div>
      <div class="butoane">
        <button type="button" class="buton" id="intrebareDa">Caută totuși</button>
        <button type="button" class="buton secundar" id="intrebareNu">Renunță</button>
      </div>
    </div>
    <div class="butoane">
      <button type="button" class="buton" id="cauta">Caută acum</button>
    </div>
    <div class="mesaj" id="mesajCautare" role="status"></div>
  </div>
</section>

<section id="panouAntena" class="ascuns"></section>

<div class="card ascuns" id="cardStare">
  <h2 id="titluStare">Căutarea de pe televizor</h2>
  <div class="bara"><div id="bara"></div></div>
  <div id="liniiStare"></div>
  <ul class="rezultat" id="rezultat"></ul>
  <div class="retea ascuns" id="reteaGasita"><small id="reteaTitlu"></small><b id="reteaNume"></b><div id="reteaDate"></div><p class="nota" id="reteaIndiciu"></p><details id="reteaFrecvente"><summary id="reteaFrecventeTitlu"></summary><div class="tabel"><table><thead><tr id="reteaFrecventeCap"></tr></thead><tbody id="reteaFrecventeRanduri"></tbody></table></div></details></div>
  <div class="posturi ascuns" id="posturiGasite"></div>
  <details class="ascuns" id="textBrut"><summary>Text brut</summary><p class="nota">Răspunsul detectorului și notele scanării, așa cum le arată televizorul pe tasta albastră.</p><pre class="brut" id="textBrutPre"></pre></details>
  <p class="nota ascuns" id="pisteDupa">Pistele canalelor găsite (teletext, subtitrări, limbile sunetului, HbbTV) se citesc din <a href="/cautare">Căutare canale</a>, cu „Actualizează pistele”. La închiderea căutării, televizorul întreabă și el, dacă au rămas canale cu pistele necitite.</p>
  <div class="butoane">
    <button type="button" class="buton ascuns" id="dinNou">Caută din nou</button>
    <button type="button" class="buton secundar ascuns" id="opreste">Oprește căutarea</button>
  </div>
  <div class="mesaj" id="mesajStare" role="status"></div>
</div>

<footer>
  <a href="/motor">Rotirea antenei</a>
  <a href="/programatori">Pentru programatori</a>
</footer>
</main>
<script>
var CFG = __CONFIG__;
var S = {structura: null, sectiune: "scanare", grup: "", scaner: "", fel: "", valori: {}, campuri: null,
  asteptare: null, ceasStare: null, ceasSemnal: null, antena: null, tintaAntena: "", nrCampuri: 0};

function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){
      return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."};
    });
  });
}
function el(tag, clasa, text){
  var e = document.createElement(tag);
  if(clasa){ e.className = clasa; }
  if(text !== undefined && text !== null){ e.textContent = text; }
  return e;
}
function goleste(e){ while(e.firstChild){ e.removeChild(e.firstChild); } }
function arata(e, da){ e.classList.toggle("ascuns", !da); }
function mesaj(e, text, eroare){ e.textContent = text || ""; e.classList.toggle("eroare", !!eroare); }
function linie(parinte, stanga, dreapta){
  if(dreapta === undefined || dreapta === null || dreapta === ""){ return; }
  var r = el("div", "linie");
  r.appendChild(el("span", "", stanga));
  r.appendChild(el("span", "", String(dreapta)));
  parinte.appendChild(r);
}
function zecimal(x){ return (Math.round(x * 10) / 10).toFixed(1).replace(".", ","); }
function buton(text, secundar, apasare){
  var b = el("button", secundar ? "buton secundar" : "buton", text);
  b.type = "button";
  b.addEventListener("click", apasare);
  return b;
}

// ---- adresa paginii: /scanare/<scaner>/<fel> si /antena/<cartela>
function dinAdresa(){
  var p = location.pathname.split("/").filter(function(x){ return x; });
  return {sectiune: p[0] === "antena" ? "antena" : "scanare",
    a: (p[1] || "").replace(/-/g, "_"), b: (p[2] || "").replace(/-/g, "_")};
}
function scrieAdresa(){
  var cale = "/" + S.sectiune;
  if(S.sectiune === "scanare" && S.grup){
    cale += "/" + S.grup.replace(/_/g, "-");
    if(S.fel){ cale += "/" + S.fel.replace(/_/g, "-"); }
  }
  if(S.sectiune === "antena" && S.tintaAntena){ cale += "/" + S.tintaAntena.replace(/_/g, "-"); }
  try{ history.replaceState(null, "", cale + location.search); }catch(e){}
}

// ---- sectiunile si grupurile, din meniul receptorului
function sectiune(cheie){
  var lista = (S.structura && S.structura.sectiuni) || [];
  for(var i = 0; i < lista.length; i++){ if(lista[i].cheie === cheie){ return lista[i]; } }
  return null;
}
function grupuriScanare(){
  var s = sectiune("scanare");
  if(!s){ return []; }
  var grupuri = s.copii.filter(function(c){ return c.tip === "grup"; });
  var directe = s.copii.filter(function(c){ return c.tip === "intrare"; });
  if(directe.length){ grupuri = grupuri.concat([{tip: "grup", cheie: "alte", titlu: "Alte intrări", copii: directe}]); }
  return grupuri;
}
function grup(cheie){
  var g = grupuriScanare();
  for(var i = 0; i < g.length; i++){ if(g[i].cheie === cheie){ return g[i]; } }
  return null;
}
function deseneazaSectiuni(){
  var cutie = $("sectiuni");
  goleste(cutie);
  S.structura.sectiuni.forEach(function(s){
    var b = buton(s.titlu, false, function(){ alegeSectiunea(s.cheie); });
    b.className = "";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", s.cheie === S.sectiune ? "true" : "false");
    cutie.appendChild(b);
  });
}
function alegeSectiunea(cheie){
  S.sectiune = cheie;
  deseneazaSectiuni();
  arata($("panouScanare"), cheie === "scanare");
  arata($("panouAntena"), cheie === "antena");
  if(cheie === "antena"){ incarcaAntena(); } else { opresteSemnalul(); }
  scrieAdresa();
}
function deseneazaGrupuri(){
  var cutie = $("grupuri");
  goleste(cutie);
  grupuriScanare().forEach(function(g){
    var b = buton(g.titlu, false, function(){ alegeGrupul(g.cheie, ""); });
    b.className = "";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", g.cheie === S.grup ? "true" : "false");
    cutie.appendChild(b);
  });
}
function alegeGrupul(cheie, fel){
  var g = grup(cheie);
  if(!g){ return; }
  S.grup = cheie;
  deseneazaGrupuri();
  var cutie = $("feluri");
  goleste(cutie);
  var ales = null;
  g.copii.forEach(function(x){
    if(x.scaner && x.fel){
      var b = buton(x.text, false, function(){ alegeFelul(x); });
      b.className = "";
      b.setAttribute("aria-pressed", "false");
      b.dataset.fel = x.scaner + "/" + x.fel;
      cutie.appendChild(b);
      if(fel && x.fel === fel){ ales = x; }
    } else {
      cutie.appendChild(cartelaTelevizor(x));
    }
  });
  if(ales){ alegeFelul(ales); } else { S.fel = ""; arata($("formular"), false); scrieAdresa(); }
}
function alegeFelul(x){
  S.scaner = x.scaner;
  S.fel = x.fel;
  S.valori = {};
  Array.prototype.forEach.call($("feluri").children, function(b){
    if(b.dataset && b.dataset.fel){ b.setAttribute("aria-pressed", b.dataset.fel === x.scaner + "/" + x.fel ? "true" : "false"); }
  });
  $("titluFel").textContent = x.text;
  arata($("formular"), true);
  arata($("intrebare"), false);
  mesaj($("mesajCautare"), "");
  scrieAdresa();
  incarcaCampuri();
}
function cartelaTelevizor(x){
  var c = el("div", "card");
  c.appendChild(el("h2", "", x.text));
  c.appendChild(el("p", "nota", "Acest ecran se folosește pe televizor."));
  var m = el("div", "mesaj");
  if(x.televizor){ c.appendChild(butoane([buton("Deschide pe televizor", true, function(){ deschidePeTelevizor(x.id, m); })])); }
  c.appendChild(m);
  return c;
}
function butoane(lista){
  var d = el("div", "butoane");
  lista.forEach(function(b){ d.appendChild(b); });
  return d;
}

// ---- campurile felului (aceleasi randuri ca pe televizor) si previzualizarea
function parametri(){
  var p = new URLSearchParams();
  p.set("scaner", S.scaner);
  p.set("fel", S.fel);
  Object.keys(S.valori).forEach(function(k){
    var v = S.valori[k];
    if(Array.isArray(v)){ v.forEach(function(x){ p.append(k, x); }); } else { p.set(k, v); }
  });
  return p;
}
function incarcaCampuri(){
  var nr = ++S.nrCampuri;
  mesaj($("previz"), "Se pregătește...");
  cerere("/api/scanare?" + parametri().toString()).then(function(d){
    if(nr !== S.nrCampuri){ return; }
    if(!d.result){ goleste($("campuri")); mesaj($("previz"), d.message, true); return; }
    S.campuri = d;
    deseneazaCampuri(d);
    var il = $("inLucru"); il.textContent = d.in_lucru || ""; il.classList.toggle("ascuns", !d.in_lucru);
    deseneazaPrevizualizarea(d.previzualizare || {}, d.plan);
    if(d.stare){ deseneazaStarea(d.stare); }
  }).catch(function(){
    if(nr === S.nrCampuri){ mesaj($("previz"), "Receptorul nu răspunde.", true); }
  });
}
function deseneazaCampuri(d){
  var f = $("campuri");
  var focus = document.activeElement && document.activeElement.id;
  var derulari = {};
  Array.prototype.forEach.call(f.querySelectorAll(".bife"), function(b){ derulari[b.id] = b.scrollTop; });
  goleste(f);
  S.valori = {};
  d.campuri.forEach(function(c){
    var id = "c_" + c.cheie;
    var l = el("label", "eticheta", c.eticheta);
    l.htmlFor = id;
    f.appendChild(l);
    if(c.tip === "lista"){
      var s = el("select");
      s.id = id;
      var grupa = null, gasit = false;
      c.optiuni.forEach(function(o){
        if(o.grupa){ grupa = el("optgroup"); grupa.label = o.text; s.appendChild(grupa); return; }
        var op = el("option", "", o.text);
        op.value = o.cod;
        if(o.cod === c.valoare){ op.selected = true; gasit = true; }
        (grupa || s).appendChild(op);
      });
      if(!gasit){
        var gol = el("option", "", c.optiuni.length ? "Alege din listă" : "Lista e goală");
        gol.value = "";
        gol.disabled = true;
        gol.selected = true;
        s.insertBefore(gol, s.firstChild);
      }
      s.addEventListener("change", function(){ S.valori[c.cheie] = s.value; incarcaCampuri(); });
      f.appendChild(s);
      S.valori[c.cheie] = c.valoare;
    } else if(c.tip === "bife"){
      var cutie = el("div", "bife");
      cutie.id = id;
      var alese = c.valoare || [];
      c.optiuni.forEach(function(o){
        var r = el("label");
        var b = el("input");
        b.type = "checkbox";
        b.value = o.cod;
        b.checked = alese.indexOf(o.cod) !== -1;
        b.addEventListener("change", function(){ S.valori[c.cheie] = bifate(cutie); incarcaCampuri(); });
        r.appendChild(b);
        r.appendChild(el("span", "", o.text));
        cutie.appendChild(r);
      });
      f.appendChild(cutie);
      var lista = [];
      if(!d.motor){ lista.push(buton("Bifează toți", true, function(){ bifeaza(cutie, true, c.cheie); })); }
      lista.push(buton("Niciunul", true, function(){ bifeaza(cutie, false, c.cheie); }));
      f.appendChild(butoane(lista));
      if(d.motor){ f.appendChild(el("p", "nota", "Antena are motor: bifează numai sateliții pe care vrei să îi cauți, antena se rotește spre fiecare.")); }
      if(derulari[id]){ cutie.scrollTop = derulari[id]; }
      S.valori[c.cheie] = alese.slice();
    } else {
      var i = el("input", "text");
      i.id = id;
      i.type = "text";
      i.inputMode = "decimal";
      i.value = c.valoare || "";
      i.addEventListener("change", function(){ S.valori[c.cheie] = i.value.trim(); incarcaCampuri(); });
      f.appendChild(i);
      S.valori[c.cheie] = c.valoare || "";
    }
    if(c.nota){ f.appendChild(el("p", "nota", c.nota)); }
  });
  if(focus){ var e = $(focus); if(e){ e.focus(); } }
}
function bifate(cutie){
  return Array.prototype.filter.call(cutie.querySelectorAll("input"), function(b){ return b.checked; })
    .map(function(b){ return b.value; });
}
function bifeaza(cutie, da, cheie){
  Array.prototype.forEach.call(cutie.querySelectorAll("input"), function(b){ b.checked = da; });
  S.valori[cheie] = bifate(cutie);
  incarcaCampuri();
}
function deseneazaPrevizualizarea(p, plan){
  if(p.eroare){ mesaj($("previz"), p.eroare, true); return; }
  var text = p.text || "";
  if(p.intrebare){ text += (text ? " " : "") + p.intrebare; }
  mesaj($("previz"), text || "Gata de căutare.");
  // DVB-T2 / DAB+ prin satelit: planul de pe televizor (unde se roteste antena, cat dureaza, ce urmeaza)
  if(plan && plan.randuri && plan.randuri.length){
    var cutie = el("div", "plan");
    plan.randuri.forEach(function(r){ linie(cutie, r[0], r[1]); });
    if(plan.text){ cutie.appendChild(el("p", "nota", plan.text)); }
    // perechea randului „Fluxuri și setări” din ecranul scanarii de pe televizor: pagina /dabt2 (dabt2_web.py)
    var caleP = location.pathname.replace(/[/]+$/, ""), felFlux = caleP.slice(-6) === "/dvbt2" ? "t2" : (caleP.slice(-4) === "/dab" ? "dab" : "");
    if(felFlux){
      var pf = el("p", "nota", "Lista fluxurilor, adăugarea de mână și setările: ");
      var af = el("a", "", "Fluxuri și setări"); af.href = "/dabt2?fel=" + felFlux;
      pf.appendChild(af); cutie.appendChild(pf);
    }
    $("previz").appendChild(cutie);
  }
}
function plural(n, unu, multe){
  // regula romaneasca: singularul cu litere (unu = "un post", "o secundă"), pluralul fara "de": 2 posturi, 20 posturi
  if(n === 1){ return unu; }
  return n + " " + multe;
}
function durata(s){
  s = Math.max(0, parseInt(s, 10) || 0);
  if(s < 60){ return plural(s, "o secundă", "secunde"); }
  return Math.floor(s / 60) + " min " + ("0" + (s % 60)).slice(-2) + " s";
}
function citesteCampurile(){
  Array.prototype.forEach.call($("campuri").querySelectorAll("input.text"), function(i){
    S.valori[i.id.slice(2)] = i.value.trim();
  });
}

// ---- pornirea: intrebarea (cautare lunga, DVB-T2) si alegerea FEC-ului la DVB-S2 se fac aici, apoi se trimite iar
function cauta(confirmat, alegere){
  citesteCampurile();
  var p = parametri();
  if(confirmat){ p.set("confirmat", "1"); }
  if(alegere){ p.set("mod", alegere.mod); p.set("fec", alegere.fec); }
  $("cauta").disabled = true;
  mesaj($("mesajCautare"), "Se pornește căutarea pe televizor...");
  cerere("/api/scanare-porneste", "POST", p).then(function(d){
    $("cauta").disabled = false;
    if(d.result){
      arata($("intrebare"), false);
      mesaj($("mesajCautare"), d.message || "Căutarea a pornit pe televizor.");
      mesaj($("mesajStare"), "");
      if(d.stare){ deseneazaStarea(d.stare); }
      try{ $("cardStare").scrollIntoView({block: "nearest", behavior: "smooth"}); }catch(e){}
      if(alegere){ S.valori.mod = alegere.mod; S.valori.fec = alegere.fec; incarcaCampuri(); }
      planificaStarea(1000);
      return;
    }
    if(d.intrebare){ arataIntrebarea(d.intrebare, null, d.plan, d.buton_da); mesaj($("mesajCautare"), ""); return; }
    if(d.de_ales){ arataIntrebarea(d.message, d.de_ales); mesaj($("mesajCautare"), ""); return; }
    mesaj($("mesajCautare"), d.message || "Căutarea nu a pornit.", true);
    if(d.stare){ deseneazaStarea(d.stare); }
  }).catch(function(){
    $("cauta").disabled = false;
    mesaj($("mesajCautare"), "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true);
  });
}
function arataIntrebarea(text, deAles, plan, butonDa){
  // planul (DVB-T2 / DAB+) e deja in previzualizarea de deasupra: aici numai textul si butoanele
  S.asteptare = deAles;
  $("intrebareText").textContent = text || "";
  var cutie = $("deAles");
  goleste(cutie);
  if(deAles){
    deAles.forEach(function(x, i){
      var r = el("label");
      var b = el("input");
      b.type = "radio";
      b.name = "deAles";
      b.value = String(i);
      b.checked = i === 0;
      r.appendChild(b);
      r.appendChild(el("span", "", x.text));
      cutie.appendChild(r);
    });
    $("intrebareDa").textContent = "Caută cu aceasta";
  } else {
    $("intrebareDa").textContent = butonDa || "Caută totuși";
  }
  arata($("intrebare"), true);
}
$("intrebareDa").addEventListener("click", function(){
  if(S.asteptare){
    var ales = $("deAles").querySelector("input:checked");
    var x = S.asteptare[ales ? parseInt(ales.value, 10) : 0];
    S.asteptare = null;
    cauta(false, x);
  } else {
    cauta(true, null);
  }
});
$("intrebareNu").addEventListener("click", function(){
  S.asteptare = null;
  arata($("intrebare"), false);
  mesaj($("mesajCautare"), "Căutarea nu a pornit.");
});
$("cauta").addEventListener("click", function(){ arata($("intrebare"), false); cauta(false, null); });

// ---- starea cautarii de pe televizor (se cere din nou abia dupa raspuns, niciodata pe un cronometru fix)
function planificaStarea(ms){
  if(S.ceasStare){ clearTimeout(S.ceasStare); }
  S.ceasStare = setTimeout(incarcaStarea, ms);
}
function incarcaStarea(){
  S.ceasStare = null;
  cerere("/api/scanare-stare").then(function(d){
    deseneazaStarea(d);
    if(d.activ){ planificaStarea(document.hidden ? 5000 : (d.in_curs ? 1500 : 4000)); }
  }).catch(function(){ planificaStarea(5000); });
}
// reteaua citita la sfarsitul scanarii (aceleasi texte ca pe televizor, deja traduse) si frecventele ei
function deseneazaReteaua(r){
  var cutie = $("reteaGasita");
  arata(cutie, !!(r && r.nume));
  if(!r || !r.nume){ return; }
  $("reteaTitlu").textContent = r.titlu || "";
  $("reteaNume").textContent = r.nume;
  var date = $("reteaDate");
  goleste(date);
  (r.date || "").split("\\n").forEach(function(x){ if(x){ date.appendChild(el("div", "", x)); } });
  $("reteaIndiciu").textContent = r.indiciu || "";
  arata($("reteaIndiciu"), !!r.indiciu);
  var fr = r.frecvente || [];
  arata($("reteaFrecvente"), fr.length > 0);
  $("reteaFrecventeTitlu").textContent = r.frecvente_titlu || "";
  var cap = $("reteaFrecventeCap");
  goleste(cap);
  (r.frecvente_coloane || []).forEach(function(x){ cap.appendChild(el("th", "", x)); });
  var corp = $("reteaFrecventeRanduri");
  goleste(corp);
  fr.forEach(function(m){
    var tr = el("tr", "", "");
    [m.mhz, m.mod, m.sr, m.tsid].forEach(function(v){ tr.appendChild(el("td", "", v === null || v === undefined ? "" : String(v))); });
    corp.appendChild(tr);
  });
}
function deseneazaStarea(d){
  var card = $("cardStare");
  if(!d || (!d.activ && !d.inchisa)){ arata(card, false); return; }
  arata(card, true);
  var titlu = d.titlu ? "Căutarea: " + d.titlu : "Căutarea de pe televizor";
  if(d.activ && d.din_web === false){ titlu += " (pornită din telecomandă)"; }
  $("titluStare").textContent = titlu;
  $("bara").style.width = (d.procent === null || d.procent === undefined ? 0 : d.procent) + "%";
  var linii = $("liniiStare");
  goleste(linii);
  var fel = d.in_curs ? "în curs" : (d.oprita ? "oprită" : (d.eroare ? "terminată cu eroare" : "terminată"));
  var f = d.fel_lucru === "fluxuri" ? (d.fluxuri || {}) : null;
  arata($("bara").parentNode, !f);          // scanarea DAB+ / DVB-T2 nu are procent: pasii sunt in randuri
  if(f && f.fata === "inainte"){ fel = "așteaptă pornirea pe televizor"; }
  if(f && f.fata === "sfarsit"){
    fel = d.eroare ? "nu a mers" : ((f.posturi || []).length ? "terminată, alege ce pornești" : "terminată, nimic găsit");
  }
  if(f && d.alegere === "asculta"){ fel = "terminată, postul ales merge pe televizor"; }
  if(f && d.alegere === "inapoi"){ fel = "terminată, canalul de dinainte merge pe televizor"; }
  linie(linii, "Starea", fel);
  if(f){
    var unu = f.fel === "dab" ? "un post" : "un program", multe = f.fel === "dab" ? "posturi" : "programe";
    linie(linii, "Satelitul", f.satelit);
    linie(linii, "Transponderul", f.transponder);
    linie(linii, "Pe televizor", d.stare_text);
    linie(linii, "Detaliul tehnic", f.detaliu);
    if(f.fata === "sfarsit" && f.fara_sunet && (f.posturi || []).length){
      linie(linii, "Ascultarea", "nu merge încă pe acest receptor (în lucru)");
    }
    if(f.fata === "in_curs"){ linie(linii, "Timp scurs", durata(f.secunde)); }
    (f.grupe || []).forEach(function(g){
      linie(linii, g.nume, g.stare === "invat" ? "citesc lista..." : plural(g.numar || 0, unu, multe));
    });
    if(f.fata === "sfarsit" && f.pozitie_inainte && f.are_canal){ linie(linii, "Canalul tău era pe", f.pozitie_inainte); }
  } else {
    linie(linii, "Pe televizor", d.stare_text);
    linie(linii, "Canale găsite", d.canale);
    if(d.transpondere){ linie(linii, "Transpondere", d.transpondere[0] + " din " + d.transpondere[1]); }
    if(d.in_curs){ linie(linii, "Timp rămas", d.timp_ramas); }
    linie(linii, "Recepție", d.retea);
    linie(linii, "Transponder", d.in_curs ? d.transponder : "");
    linie(linii, "Trecerea", d.trecere);
    if(d.in_curs && d.ultimele && d.ultimele.length){ linie(linii, "Ultimele canale", d.ultimele.slice(-5).join(", ")); }
  }
  var rez = $("rezultat");
  goleste(rez);
  (d.rezultat || []).forEach(function(r){ rez.appendChild(el("li", "", r)); });
  deseneazaReteaua(d.retea_gasita);
  // pereche web a intrebarii de pe televizor dupa o scanare terminata cu canale (Screens/ServiceScan.hdsPisteDupaScanare)
  arata($("pisteDupa"), !!(d.inchisa && d.gata && d.canale > 0 && d.fel_lucru !== "fluxuri"));
  deseneazaPosturile(d, f);
  var brut = (f && d.text_brut) ? d.text_brut : "";
  arata($("textBrut"), !!brut);
  if($("textBrutPre").textContent !== brut){ $("textBrutPre").textContent = brut; }
  var b = $("opreste");
  arata(b, !!d.activ);
  b.textContent = d.in_curs ? "Oprește căutarea" : "Închide rezultatul pe televizor";
  if(f){
    if(f.fata === "sfarsit"){ b.textContent = f.text_inapoi || "Înapoi la canalul meu"; }
    else if(f.fata === "inainte"){ b.textContent = "Renunță"; }
    else if(f.fata === "in_curs"){ b.textContent = "Oprește scanarea"; }
  }
  // al doilea buton: „Pornește scanarea" cand ecranul de pe televizor asteapta pornirea (deschis din telecomanda),
  // „Caută din nou" cand scanarea s-a terminat fara rezultat
  var dn = $("dinNou");
  var inainte = !!(f && d.activ && f.fata === "inainte");
  arata(dn, inainte || !!(f && d.activ && f.fata === "sfarsit" && !(f.posturi || []).length));
  dn.textContent = inainte ? "Pornește scanarea" : "Caută din nou";
  dn.setAttribute("data-actiune", inainte ? "porneste" : "din_nou");
}
// ---- DVB-T2 / DAB+ prin satelit: posturile gasite pe ansambluri (multiplexuri), ca pe televizor: capul grupei cu
// numarul posturilor, apoi posturile ei, fiecare cu butonul lui (ca OK pe randul lui la televizor)
function deseneazaPosturile(d, f){
  var cutie = $("posturiGasite");
  var posturi = f && d.activ && f.fata === "sfarsit" ? (f.posturi || []) : [];
  // ca tasta verde de pe televizor: „Pornește” si la DAB+ cat ascultarea e „(în lucru)”
  var textButon = f && f.fel === "dab" && !f.fara_sunet ? "Ascultă" : "Pornește";
  // lista se reface numai cand s-a schimbat: altfel starea citita din nou ar inlocui butoanele sub degetul omului
  var semn = JSON.stringify([posturi, textButon]);
  if(semn === S.posturiSemn){ return; }
  S.posturiSemn = semn;
  goleste(cutie);
  arata(cutie, posturi.length > 0);
  var unu = f && f.fel === "dab" ? "post" : "program", multe = f && f.fel === "dab" ? "posturi" : "programe";
  var numar = {};
  posturi.forEach(function(p){ numar[p.grup] = (numar[p.grup] || 0) + 1; });
  var grupa = null;
  // numarul trimis la „asculta” e locul postului in lista intreaga (posturi() pe receptor), nu in grupa
  posturi.forEach(function(p, i){
    if(p.grup !== grupa){
      grupa = p.grup;
      var g = el("div", "grupaPosturi");
      g.appendChild(el("b", "", p.grup));
      g.appendChild(el("small", "", plural(numar[p.grup], unu, multe)));
      cutie.appendChild(g);
    }
    var r = el("div", "post");
    var t = el("div");
    t.appendChild(el("b", "", p.nume));
    if(f.fel !== "dab" && p.fel){ t.appendChild(el("small", "", p.fel)); }
    r.appendChild(t);
    r.appendChild(buton(textButon, false, function(){ alegeFlux("asculta", i, this); }));
    cutie.appendChild(r);
  });
}
function alegeFlux(actiune, post, b){
  var p = new URLSearchParams();
  p.set("actiune", actiune);
  if(post !== null && post !== undefined){ p.set("post", String(post)); }
  if(b){ b.disabled = true; }
  cerere("/api/scanare-fluxuri", "POST", p).then(function(d){
    if(b){ b.disabled = false; }
    mesaj($("mesajStare"), d.message, !d.result);
    if(d.stare){ deseneazaStarea(d.stare); }
    planificaStarea(1000);
  }).catch(function(){
    if(b){ b.disabled = false; }
    mesaj($("mesajStare"), "Receptorul nu răspunde.", true);
  });
}
$("dinNou").addEventListener("click", function(){ alegeFlux(this.getAttribute("data-actiune") || "din_nou", null, this); });
$("opreste").addEventListener("click", function(){
  var b = $("opreste");
  b.disabled = true;
  cerere("/api/scanare-opreste", "POST", new URLSearchParams()).then(function(d){
    b.disabled = false;
    mesaj($("mesajStare"), d.message, !d.result);
    if(d.stare){ deseneazaStarea(d.stare); }
    planificaStarea(1000);
  }).catch(function(){
    b.disabled = false;
    mesaj($("mesajStare"), "Receptorul nu răspunde.", true);
  });
});

// ---- orientarea si setarea antenei (numai citire; ecranele de setari se deschid pe televizor)
var MODURI = {simple: "simplu", advanced: "avansat", nothing: "oprit (nimic conectat)", loopthrough: "legat prin alt tuner",
  satposdepends: "depinde de alt tuner", equal: "la fel ca alt tuner", enabled: "pornit"};
var DISEQC = {single: "un singur satelit", toneburst_a_b: "Toneburst A/B", diseqc_a_b: "DiSEqC A/B",
  diseqc_a_b_c_d: "DiSEqC A/B/C/D", positioner: "motor (USALS)", positioner_select: "motor, sateliți aleși"};
var LNB = {universal_lnb: "universal", c_band: "banda C", user_defined: "definit de utilizator", unicable: "Unicable",
  jess: "JESS"};

function incarcaAntena(lat, lon){
  var cale = "/api/antena";
  if(lat !== undefined){ cale += "?lat=" + encodeURIComponent(lat) + "&lon=" + encodeURIComponent(lon); }
  cerere(cale).then(function(d){
    if(!d.result){ mesaj($("incarcare"), d.message, true); arata($("incarcare"), true); return; }
    var calculator = S.antena && S.antena.calculator;
    S.antena = d;
    deseneazaAntena(calculator && lat !== undefined ? calculator.ales : null);
    planificaSemnalul(2000);
  }).catch(function(){ mesaj($("incarcare"), "Receptorul nu răspunde.", true); arata($("incarcare"), true); });
}
function intrariAntena(){
  var s = sectiune("antena");
  if(!s){ return []; }
  var lista = [];
  s.copii.forEach(function(c){ if(c.tip === "grup"){ lista = lista.concat(c.copii); } else { lista.push(c); } });
  return lista;
}
function deseneazaAntena(satelitAles){
  var panou = $("panouAntena");
  goleste(panou);
  intrariAntena().forEach(function(x){
    var c = el("div", "card");
    var cheie = x.antena || x.id;
    c.id = "antena-" + cheie;
    c.appendChild(el("h2", "", x.text));
    var m = el("div", "mesaj");
    if(x.antena === "tuner"){ cartelaTunere(c); }
    else if(x.antena === "lnb"){ cartelaLnb(c); legaturaPagina(c, x, "Schimbă LNB-ul"); }
    else if(x.antena === "motor"){
      c.appendChild(el("p", "nota", "Unde se află antena și cât mai are de mers, pe pagina rotirii."));
      var a = el("a", "buton", "Deschide pagina rotirii");
      a.href = x.web || "/motor";
      c.appendChild(butoane([a]));
    }
    else if(x.antena === "calculator"){ cartelaCalculator(c, satelitAles); }
    else if(x.antena === "locul"){
      var loc = (S.antena && S.antena.locul) || {};
      c.appendChild(el("p", "mesaj" + (loc.stabilit ? "" : " avert"), loc.stabilit ? loc.text :
        "Nestabilit: motorul USALS nu rotește antena spre niciun satelit până nu alegi locul."));
      legaturaPagina(c, x, "Schimbă locul antenei");
    }
    else if(x.antena === "semnal"){ cartelaSemnal(c); legaturaPagina(c, x, "Deschide Găsire semnal"); }
    else if(x.antena === "diseqc"){
      c.appendChild(el("p", "nota", "Proba trimite comenzi la comutator sau la motor și arată pe televizor ce răspunde fiecare intrare. Se pornește din telecomandă."));
    }
    else { c.appendChild(el("p", "nota", "Acest ecran se folosește pe televizor.")); }
    if(x.televizor && x.antena !== "motor"){
      c.appendChild(butoane([buton("Deschide pe televizor", true, function(){ deschidePeTelevizor(x.id, m); })]));
    }
    c.appendChild(m);
    panou.appendChild(c);
  });
  if(S.tintaAntena){
    var tinta = $("antena-" + S.tintaAntena);
    if(tinta){ tinta.classList.add("evidentiat"); tinta.scrollIntoView({block: "start"}); }
  }
}
// pagina web a unei intrari (web= din menu.xml), cand intrarea are una: /antena/lnb si /antena/semnal (antena_web.py)
function legaturaPagina(c, x, text){
  if(!x.web){ return; }
  var a = el("a", "buton", text);
  a.href = adresa(x.web);
  c.appendChild(butoane([a]));
}
function tunereSatelit(){
  return ((S.antena && S.antena.tunere) || []).filter(function(t){ return t.satelit; });
}
function cartelaTunere(c){
  var tunere = (S.antena && S.antena.tunere) || [];
  if(!tunere.length){ c.appendChild(el("p", "nota", "Receptorul nu arată niciun tuner.")); return; }
  tunere.forEach(function(t){
    c.appendChild(el("p", "subtitlu", t.descriere || ("Tuner " + t.litera)));
    var tipuri = [];
    if(t.satelit){ tipuri.push("satelit"); }
    if(t.cablu){ tipuri.push("cablu"); }
    if(t.terestru){ tipuri.push("terestru"); }
    linie(c, "Recepție", tipuri.join(", "));
    linie(c, "Mod", MODURI[t.mod] || t.mod);
    if(t.satelit){
      if(t.diseqc){ linie(c, "Comutare", DISEQC[t.diseqc] || t.diseqc); }
      linie(c, "Motor", t.motor ? "da" : "nu");
      if(t.usals){ linie(c, "Locul pentru USALS", t.usals_text); }
      if(t.sateliti && t.sateliti.length){
        linie(c, "Sateliți", t.motor ? t.sateliti.length + " (toți din lista motorului)" :
          t.sateliti.map(function(s){ return s.text; }).join(", "));
      }
    }
  });
  c.appendChild(el("p", "nota", "Setările se schimbă pe televizor, în ecranul Setări tuner."));
}
function cartelaLnb(c){
  var tunere = tunereSatelit();
  if(!tunere.length){ c.appendChild(el("p", "nota", "Receptorul nu are tuner de satelit.")); return; }
  tunere.forEach(function(t){
    var lnb = t.lnb || [];
    if(!lnb.length){ linie(c, "Tuner " + t.litera, MODURI[t.mod] || t.mod || "-"); return; }
    lnb.forEach(function(l){
      var nume = "Tuner " + t.litera + (l.numar ? ", LNB " + l.numar : "");
      var text = LNB[l.fel] || l.fel || "-";
      if(l.lof_jos){
        text += ": " + l.lof_jos + (l.lof_sus && l.lof_sus !== l.lof_jos ? " / " + l.lof_sus : "") + " MHz";
        if(l.prag){ text += ", prag " + l.prag + " MHz"; }
      }
      linie(c, nume, text);
    });
    if(t.mod === "simple"){ c.appendChild(el("p", "nota", "În modul simplu receptorul folosește LNB-ul universal de mai sus.")); }
  });
  c.appendChild(el("p", "nota", "Tipul, oscilatoarele, tensiunea, tonul și portul se schimbă pe pagina Configurare LNB, cu verificarea semnalului înainte de păstrare."));
}
function cartelaCalculator(c, satelitAles){
  var k = (S.antena && S.antena.calculator) || {sateliti: []};
  if(k.eroare && !k.sateliti.length && k.sursa !== "nestabilit"){ c.appendChild(el("p", "nota eroare", k.eroare)); return; }
  var doua = el("div", "doua");
  var cLat = el("div"), cLon = el("div");
  var lLat = el("label", "eticheta", "Latitudine (grade, nord +)"), lLon = el("label", "eticheta", "Longitudine (grade, est +)");
  var iLat = el("input", "text"), iLon = el("input", "text");
  iLat.id = "calcLat"; iLon.id = "calcLon"; lLat.htmlFor = "calcLat"; lLon.htmlFor = "calcLon";
  iLat.inputMode = iLon.inputMode = "decimal";
  iLat.value = zecimal(k.latitudine || 0); iLon.value = zecimal(k.longitudine || 0);
  cLat.appendChild(lLat); cLat.appendChild(iLat); cLon.appendChild(lLon); cLon.appendChild(iLon);
  doua.appendChild(cLat); doua.appendChild(cLon);
  c.appendChild(doua);
  var lSat = el("label", "eticheta", "Satelitul");
  lSat.htmlFor = "calcSat";
  var s = el("select");
  s.id = "calcSat";
  var peTuner = [];
  tunereSatelit().forEach(function(t){ if(!t.motor){ (t.sateliti || []).forEach(function(x){ peTuner.push(x.pozitie); }); } });
  var implicit = satelitAles !== null && satelitAles !== undefined ? satelitAles :
    (peTuner.indexOf(192) !== -1 || !peTuner.length ? 192 : peTuner[0]);
  var grupaAntenei = null, grupaToti = s;
  if(peTuner.length){
    grupaAntenei = el("optgroup"); grupaAntenei.label = "Pe antena ta"; s.appendChild(grupaAntenei);
    grupaToti = el("optgroup"); grupaToti.label = "Toți sateliții"; s.appendChild(grupaToti);
  }
  function optiune(x, ales){
    var o = el("option", "", x.nume || x.text);
    o.value = String(x.pozitie);
    if(ales){ o.selected = true; }
    return o;
  }
  k.sateliti.forEach(function(x){
    var peAntena = peTuner.indexOf(x.pozitie) !== -1;
    if(grupaAntenei && peAntena){ grupaAntenei.appendChild(optiune(x, x.pozitie === implicit)); }
    grupaToti.appendChild(optiune(x, x.pozitie === implicit && !(grupaAntenei && peAntena)));
  });
  c.appendChild(lSat);
  c.appendChild(s);
  var rez = el("div");
  c.appendChild(rez);
  function arataUnghiurile(){
    goleste(rez);
    var poz = parseInt(s.value, 10);
    k.ales = poz;
    k.sateliti.forEach(function(x){
      if(x.pozitie !== poz){ return; }
      // scrise de receptor, cu separatorul limbii meniului, ca pe televizor
      linie(rez, "Azimut", x.azimut_text);
      linie(rez, "Elevație", x.elevatie_text);
      linie(rez, "Rotirea LNB-ului (skew)", x.skew_text);
      if(!x.vizibil){ rez.appendChild(el("p", "nota eroare", "Satelitul e sub orizont din locul acesta.")); }
    });
  }
  s.addEventListener("change", arataUnghiurile);
  arataUnghiurile();
  if(k.eroare){ c.appendChild(el("p", "nota eroare", k.eroare)); }
  c.appendChild(el("p", "nota", k.sursa === "cerere" ? "Calculat pentru locul scris mai sus. Locul salvat pe receptor nu s-a schimbat." :
    (k.sursa === "nestabilit" ? "" : "Locul e locul antenei, același ca pe televizor și ca la motor (pagina Locul antenei).")));
  c.appendChild(butoane([buton("Calculează", false, function(){
    incarcaAntena(iLat.value.trim().replace(",", "."), iLon.value.trim().replace(",", "."));
  })]));
}
function cartelaSemnal(c){
  var cutie = el("div");
  cutie.id = "semnal";
  c.appendChild(cutie);
  deseneazaSemnalul(S.antena && S.antena.semnal);
  c.appendChild(el("p", "nota", "Semnalul canalului care rulează acum, citit din 2 în 2 secunde. Pentru un transponder anume, cu nivelul și calitatea citite des, deschide Găsire semnal."));
}
function deseneazaSemnalul(s){
  var cutie = $("semnal");
  if(!cutie){ return; }
  goleste(cutie);
  if(!s || !s.are){ cutie.appendChild(el("p", "nota", "Niciun canal nu rulează acum pe receptor.")); return; }
  linie(cutie, "Canal", s.canal);
  linie(cutie, "Tuner", s.tuner);
  linie(cutie, "Semnal recepționat", s.prins ? "da" : "nu");
  if(s.calitate !== null){ linie(cutie, "Calitate", s.calitate + "%"); }
  if(s.snr_db !== null){ linie(cutie, "SNR", zecimal(s.snr_db) + " dB"); }
  if(s.putere !== null){ linie(cutie, "Putere", s.putere + "%"); }
  if(s.ber !== null){ linie(cutie, "BER", s.ber); }
}
function planificaSemnalul(ms){
  opresteSemnalul();
  if(S.sectiune !== "antena" || !$("semnal")){ return; }
  S.ceasSemnal = setTimeout(incarcaSemnalul, ms);
}
function opresteSemnalul(){
  if(S.ceasSemnal){ clearTimeout(S.ceasSemnal); S.ceasSemnal = null; }
}
function incarcaSemnalul(){
  S.ceasSemnal = null;
  if(S.sectiune !== "antena"){ return; }
  if(document.hidden){ planificaSemnalul(5000); return; }
  cerere("/api/antena?doar=semnal").then(function(d){
    if(d.result){ deseneazaSemnalul(d.semnal); }
    planificaSemnalul(2000);
  }).catch(function(){ planificaSemnalul(5000); });
}
function deschidePeTelevizor(id, m){
  var p = new URLSearchParams();
  p.set("id", id);
  mesaj(m, "Se deschide pe televizor...");
  cerere("/api/scanare-televizor", "POST", p).then(function(d){
    mesaj(m, d.message, !d.result);
  }).catch(function(){ mesaj(m, "Receptorul nu răspunde.", true); });
}

// ---- pornirea paginii
function pornestePagina(){
  cerere("/api/scanare").then(function(d){
    if(!d.result){ mesaj($("incarcare"), d.message || "Meniul receptorului nu se poate citi.", true); return; }
    if(!d.sectiuni || !d.sectiuni.length){
      mesaj($("incarcare"), "Meniul receptorului nu se poate citi, deci nu am ce arăta. Detalii în jurnalul receptorului.", true);
      return;
    }
    S.structura = d;
    arata($("incarcare"), false);
    var a = dinAdresa();
    S.sectiune = sectiune(a.sectiune) ? a.sectiune : d.sectiuni[0].cheie;
    var grupuri = grupuriScanare();
    var cheie = a.sectiune === "scanare" && grup(a.a) ? a.a : (grupuri.length ? grupuri[0].cheie : "");
    if(cheie){ alegeGrupul(cheie, a.sectiune === "scanare" ? a.b : ""); }
    if(a.sectiune === "antena"){ S.tintaAntena = a.a; }
    alegeSectiunea(S.sectiune);
    deseneazaStarea(d.stare);
    if(d.stare && d.stare.activ){ planificaStarea(1500); }
  }).catch(function(){
    mesaj($("incarcare"), "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true);
  });
}
pornestePagina();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Scanare și antenă"),
		N_("Se citește meniul receptorului..."),
		N_("Caută totuși"),
		N_("Renunță"),
		N_("Caută acum"),
		N_("Căutarea de pe televizor"),
		N_("Text brut"),
		N_("Răspunsul detectorului și notele scanării, așa cum le arată televizorul pe tasta albastră."),
		N_("Pistele canalelor găsite (teletext, subtitrări, limbile sunetului, HbbTV) se citesc din <a "
			"href=\"/cautare\">Căutare canale</a>, cu „Actualizează pistele”. La închiderea căutării, "
			"televizorul întreabă și el, dacă au rămas canale cu pistele necitite."),
		N_("Caută din nou"),
		N_("Oprește căutarea"),
		N_("Rotirea antenei"),
		N_("Pentru programatori"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Alte intrări"),
		N_("Acest ecran se folosește pe televizor."),
		N_("Deschide pe televizor"),
		N_("Se pregătește..."),
		N_("Receptorul nu răspunde."),
		N_("Alege din listă"),
		N_("Lista e goală"),
		N_("Bifează toți"),
		N_("Niciunul"),
		N_("Antena are motor: bifează numai sateliții pe care vrei să îi cauți, antena se rotește spre "
			"fiecare."),
		N_("Gata de căutare."),
		N_("Lista fluxurilor, adăugarea de mână și setările:"),
		N_("Fluxuri și setări"),
		N_("o secundă"),
		N_("un post"),
		N_("un program"),
		N_("Se pornește căutarea pe televizor..."),
		N_("Căutarea a pornit pe televizor."),
		N_("Căutarea nu a pornit."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Caută cu aceasta"),
		N_("Caută totuși"),
		N_("Căutarea:"),
		N_("Căutarea de pe televizor"),
		N_("(pornită din telecomandă)"),
		N_("în curs"),
		N_("oprită"),
		N_("terminată cu eroare"),
		N_("terminată"),
		N_("așteaptă pornirea pe televizor"),
		N_("nu a mers"),
		N_("terminată, alege ce pornești"),
		N_("terminată, nimic găsit"),
		N_("terminată, postul ales merge pe televizor"),
		N_("terminată, canalul de dinainte merge pe televizor"),
		N_("Starea"),
		N_("Satelitul"),
		N_("Transponderul"),
		N_("Pe televizor"),
		N_("Detaliul tehnic"),
		N_("Ascultarea"),
		N_("nu merge încă pe acest receptor (în lucru)"),
		N_("Timp scurs"),
		N_("citesc lista..."),
		N_("Canalul tău era pe"),
		N_("Canale găsite"),
		N_("Transpondere"),
		N_("din"),
		N_("Timp rămas"),
		N_("Recepție"),
		N_("Transponder"),
		N_("Trecerea"),
		N_("Ultimele canale"),
		N_("Oprește căutarea"),
		N_("Închide rezultatul pe televizor"),
		N_("Înapoi la canalul meu"),
		N_("Renunță"),
		N_("Oprește scanarea"),
		N_("Pornește scanarea"),
		N_("Caută din nou"),
		N_("Ascultă"),
		N_("Pornește"),
		N_("oprit (nimic conectat)"),
		N_("legat prin alt tuner"),
		N_("depinde de alt tuner"),
		N_("la fel ca alt tuner"),
		N_("un singur satelit"),
		N_("Toneburst A/B"),
		N_("motor (USALS)"),
		N_("motor, sateliți aleși"),
		N_("banda C"),
		N_("definit de utilizator"),
		N_("Schimbă LNB-ul"),
		N_("Unde se află antena și cât mai are de mers, pe pagina rotirii."),
		N_("Deschide pagina rotirii"),
		N_("Nestabilit: motorul USALS nu rotește antena spre niciun satelit până nu alegi locul."),
		N_("Schimbă locul antenei"),
		N_("Deschide Găsire semnal"),
		N_("Proba trimite comenzi la comutator sau la motor și arată pe televizor ce răspunde fiecare "
			"intrare. Se pornește din telecomandă."),
		N_("Receptorul nu arată niciun tuner."),
		N_("Tuner"),
		N_("Mod"),
		N_("Comutare"),
		N_("Motor"),
		N_("Locul pentru USALS"),
		N_("Sateliți"),
		N_("(toți din lista motorului)"),
		N_("Setările se schimbă pe televizor, în ecranul Setări tuner."),
		N_("Receptorul nu are tuner de satelit."),
		N_(", prag"),
		N_("În modul simplu receptorul folosește LNB-ul universal de mai sus."),
		N_("Tipul, oscilatoarele, tensiunea, tonul și portul se schimbă pe pagina Configurare LNB, cu "
			"verificarea semnalului înainte de păstrare."),
		N_("Latitudine (grade, nord +)"),
		N_("Longitudine (grade, est +)"),
		N_("Pe antena ta"),
		N_("Toți sateliții"),
		N_("Azimut"),
		N_("Elevație"),
		N_("Rotirea LNB-ului (skew)"),
		N_("Satelitul e sub orizont din locul acesta."),
		N_("Calculat pentru locul scris mai sus. Locul salvat pe receptor nu s-a schimbat."),
		N_("Locul e locul antenei, același ca pe televizor și ca la motor (pagina Locul antenei)."),
		N_("Calculează"),
		N_("Semnalul canalului care rulează acum, citit din 2 în 2 secunde. Pentru un transponder anume, cu "
			"nivelul și calitatea citite des, deschide Găsire semnal."),
		N_("Niciun canal nu rulează acum pe receptor."),
		N_("Canal"),
		N_("Semnal recepționat"),
		N_("Calitate"),
		N_("Putere"),
		N_("Se deschide pe televizor..."),
		N_("Meniul receptorului nu se poate citi."),
		N_("Meniul receptorului nu se poate citi, deci nu am ce arăta. Detalii în jurnalul receptorului."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
