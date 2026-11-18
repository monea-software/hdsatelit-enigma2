# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# acces_conditionat_web.py: „Acces condiționat” in interfata web (HdsWebControl), perechea ecranelor „Module de acces
# condiționat” (Screens/CamSetup.py) si „Informații despre decriptare” (Screens/CamInfo.py) din meniul Acces condiționat.
#
# Modulele instalate (scripturile /etc/init.d/<fel>.<x>: intai modulele obisnuite, apoi serverele de carduri), care e
# ales la pornirea receptorului, care ruleaza, procesul care lucreaza si memoria lui; alegerea, pornirea, oprirea si
# repornirea. O SINGURA LOGICA: citirea si comenzile sunt Components/HdsModuleAcces.py (Operatie: pas cu pas, o
# singura comanda deodata pentru televizor si web, numai scripturile modulelor, fara interpretor de comenzi); procesul
# aratat si textele rezultatelor sunt cele ale ecranului (CamSetup.pid_de_aratat, text_rezultat, text_pas).
# Randurile din /tmp/ecm.info nu ajung in pagina (pot avea numele si adresele cititoarelor): pagina spune numai daca
# receptorul decripteaza acum si deschide pe televizor ecranul cu toate detaliile. Pagina nu trece spre modul (fara
# proxy): interfetele web ale modulelor sunt pe /interfete-cam.
# 0.2.8 (perechea butonului Albastru din ecranul de pe televizor): „Deschide pe televizor” pe
# cardul „Pagina web a modulului” deschide interfata web a modulului care ruleaza PE TELEVIZOR, in navigatorul imaginii,
# prin ruta navigatorului (POST /api/navigator-cam, navigator_web.py, aceeasi poarta si acelasi CSRF). Pentru butonul
# din randul unui modul activ se primesc numai portul si protocolul configurate; gazda este cea din browser.
# Utilizatorul si parola interfetei nu se citesc aici. Textele noi ale cardului se traduc (TEXTE_CAM, 13 limbi);
# restul paginii e scris in romana, ca pana acum.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/acces-conditionat            modulele pe feluri, cine e ales, cine ruleaza, comanda in curs / ultima
#   GET  /api/acces-conditionat-interfete  portul si protocolul configurate ale modulelor active, citite pe un fir
#   GET  /api/acces-conditionat-dosare     dosarele de setari ale tuturor modulelor, citite pe un fir
#   POST /api/acces-conditionat-comanda?cerere=alege|porneste|opreste|reporneste&fel=<fel>[&sufix=<x>]
#                                          porneste comanda si raspunde pe loc; rezultatul vine apoi prin GET; <fel> e
#                                          numele felului asa cum il da GET (campul "fel"), citit de pe receptor
#   GET  /acces-conditionat                pagina
# „Deschide pe televizor” foloseste ruta meniului: POST /api/meniu-televizor?id=cam_setup|cam_info (meniu_web.py).
# Rutele nu s-au schimbat la trecerea pe nume neutre; numai valoarea lui fel vine acum de pe receptor (aceeasi ca
# inainte pe acelasi receptor), deci paginile si aplicatiile care o iau din GET merg mai departe fara redirectare.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. Citirea e cea a ecranului (cateva fisiere mici din
# /etc/init.d si /proc, HdsModuleAcces.citeste); configurarile pentru linkuri se citesc separat pe un fir;
# scripturile ruleaza in eConsoleAppContainer, fara sa fie asteptate.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul H (Components.HdsModuleAcces) si
# ecranul E (Screens.CamSetup).
# 0.7.1: cardul „Stream Relay” (GET da si stream_relay, din Components/HdsStreamRelay.stare): cate canale are lista,
# de unde se adauga (lista de canale de pe televizor, pagina Canale), daca releul raspunde si de ce nu (modulul ales
# oprit, niciun modul, modulul fara releu), cu legaturile spre pagina Canale si spre setarile Stream Relay.
# 0.7.4 (11.11.2026): GET da si icam, randul din ecranul modulelor (Components/HdsSoftCsa.randModul) cand un modul
# ruleaza si SoftCSA nu e gata cu el (OSCam-smod nu descifreaza ICAM): sta in cardul „Acum”; "" altfel.
# 0.7.7 (16.11.2026; LinuxSat 164183 #970691 si #970816): la un modul care nu ruleaza, GET da si "nepornit" {motiv, text, buton}:
# de ce nu poate porni (Components/HdsModulNepornit.diagnosticPeEcran, aceeasi fraza ca pe televizor) si butonul
# „Pune <modul> din feedul HD Satelit”; "inlocuire" = mersul acelei lucrari (HdsModulNepornit.stareWeb).
#   POST /api/acces-conditionat-inlocuieste?fel=<fel>&sufix=<x>   pachetul nostru al modulului, instalat, ales si pornit
#                                          (HdsModulNepornit.porneste, pe un fir; raspunde pe loc, mersul vine prin GET;
#                                          0.7.7, MG4: verificarea si starea din raspuns vin din citirea modulelor de pe fir)
# 0.7.7: GET da si "din_feed": modulele din feedurile HD Satelit care nu sunt instalate (HdsModulNepornit.dinFeed), cu
# {pachet, fel, nume, versiune, descriere, buton}; in pagina, cate un rand sub modulele instalate ale felului, cu butonul
# "Pune <modul> din feedul HD Satelit", ca pe televizor.
#   POST /api/acces-conditionat-inlocuieste?fel=<fel>&pachet=<pachet>   modulul din feed (numai un pachet din "din_feed"),
#                                          instalat, ales si pornit (HdsModulNepornit.porneste cu pachetul)
# 0.7.7 (MGR/PLAN-078 punctul 3): cardul cu cititoarele, clientii si jurnalul modulului care ruleaza, aceleasi randuri ca pe
# televizor in Informatii despre decriptare (Components/HdsJurnalModul.py, din interfata web a modulului, pe receptor).
# Spre deosebire de ecm.info (de mai sus), randurile acestea au numele cititoarelor si jurnalul modulului (fara adresele
# cititoarelor), deci le primesc NUMAI cererile din reteaua de acasa, ca pagina modulului insusi, oricum ar intra cererea.
#   GET  /api/acces-conditionat-jurnal     {result, modul, linii}: linii = textele ecranului (titlurile fara spatii in fata,
#                                          randurile cu doua spatii in fata), pe un fir; o citire odata
import re
import time

ARGUMENTE = ("cerere", "fel", "sufix", "pachet")
MAX_VALOARE = 64
# acelasi tipar ca HdsModuleAcces._SUFIX_BUN (Operatie il verifica din nou pe lista citita chiar atunci)
_SUFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


# numele felurilor, ca in meniul de pe televizor: primul fel aratat (al modulelor obisnuite, acelasi msgid ca titlul
# ecranului) si celelalte (serverele de carduri)
ETICHETA_PRINCIPAL = N_("Module de acces condiționat")
ETICHETA_ALTE = N_("Servere de carduri")

# comanda pornita din web: pasul de acum si ultimul rezultat (al oricarei comenzi pornite de aici)
_STARE = {"pas": None, "ultima": None}
_STEAG_WEB = [False]
_STEAG_DOSARE = [False]


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _h(H=None):
	if H is not None:
		return H
	from Components import HdsModuleAcces
	return HdsModuleAcces


def _ecran(E=None):
	if E is not None:
		return E
	from Screens import CamSetup
	return CamSetup


def _jurnal(text):
	print("[HdsWebControl] acces conditionat: %s" % text)


def _memorie(H, sistem, pid, randuri=None):
	"""{"kb": VmRSS, "fire": Threads} din /proc/<pid>/status (HdsModuleAcces.memorie), fara valorile care lipsesc; cu
	`randuri` (0.7.7: citite pe fir, Screens/CamSetup.citesteEcranul), din ele, fara alta citire"""
	rez = {}
	for r in (H.memorie(sistem, pid) if randuri is None else randuri):
		parti = r.split()
		if len(parti) > 1 and parti[1].isdigit():
			if parti[0] == "VmRSS:":
				rez["kb"] = int(parti[1])
			elif parti[0] == "Threads:":
				rez["fire"] = int(parti[1])
	return rez


def _nepornit(N=None):
	"""Components.HdsModulNepornit (probele dau unul); None cand nu se poate incarca."""
	if N is not None:
		return N
	try:
		from Components import HdsModulNepornit as N
		return N
	except Exception as eroare:
		_jurnal("HdsModulNepornit: %r" % (eroare,))
		return None


def _modul(H, E, sistem, e, N=None, citita=None):
	"""Randul unui modul; cu `citita` (0.7.7: Screens/CamSetup.citesteEcranul, facuta pe un fir) procesul aratat, memoria si
	diagnosticul vin din ea, fara alte citiri pe firul enigma2."""
	m = {"sufix": e.sufix, "descriere": e.descriere or "", "ales": bool(e.ales), "ruleaza": bool(e.pids),
		"versiune": getattr(e, "versiune", "") or ""}
	cheie = (getattr(e, "fel", ""), e.sufix)
	if e.pids:
		if citita is not None and cheie in citita.get("pid", {}):
			pid = citita["pid"][cheie]
			m["memorie"] = _memorie(H, sistem, pid, citita["memorie"].get(cheie, [])) if pid is not None else {}
		else:
			pid = E.pid_de_aratat(sistem, e.pids)
			m["memorie"] = _memorie(H, sistem, pid) if pid is not None else {}
		m["pid"] = pid
		m["procese"] = len(e.pids)
	else:
		# 0.7.7: de ce nu poate porni si butonul din feedul nostru (aceleasi texte ca pe televizor)
		N = _nepornit(N)
		try:
			if citita is not None and cheie in citita.get("nepornit", {}):
				d = citita["nepornit"][cheie]
			else:
				d = N.diagnosticPeEcran(sistem, cheie[0], e.sufix) if N is not None else None
			if d:
				m["nepornit"] = {"motiv": d.get("motiv") or "", "text": N.text(d), "buton": N.textOferta(e.sufix)}
		except Exception as eroare:
			_jurnal("modulul %s: %r" % (e.sufix, eroare))
	return m


def _comanda(H):
	o = H.in_curs()
	if o is not None:
		pas = _STARE["pas"] if _STARE["pas"] and _STARE["pas"].get("operatie") == id(o) else None
		return {"in_curs": True, "text": pas["text"] if pas else _t("Așteaptă să se termine comanda de acum.")}
	return {"in_curs": False, "ultima": _STARE["ultima"]}


def stare(H=None, E=None, SR=None, SC=None, N=None, citita=None):
	"""Pentru GET /api/acces-conditionat. `SR` e Components.HdsStreamRelay, `SC` Components.HdsSoftCsa, `N`
	Components.HdsModulNepornit (probele dau unele false). `citita` (0.7.7): citirea modulelor facuta pe un fir
	(Screens/CamSetup.citesteEcranul, vezi _stareDinFir); fara ea, citirea se face aici."""
	H = _h(H)
	E = _ecran(E)
	N = _nepornit(N)
	sistem = H.SistemAcces()
	feluri = []
	decripteaza = False
	ruleaza = False
	stari = citita["stari"] if citita is not None else H.feluri_de_aratat(sistem)
	for i, st in enumerate(stari):
		feluri.append({
			"fel": st.fel,
			"eticheta": _t(ETICHETA_PRINCIPAL if i == 0 else ETICHETA_ALTE),
			"niciunul_ales": st.ales_emulator() is None,
			"legatura": st.legatura,
			"module": [_modul(H, E, sistem, e, N, citita) for e in st.emulatoare],
			"fara_script": list(st.fara_script),
		})
		decripteaza = decripteaza or bool(st.ecm)
		ruleaza = ruleaza or any(e.pids for e in st.emulatoare)
	if citita is not None and hasattr(H, "ModuleCitite"):
		# 0.7.7: motivul releului ia modulele din citirea de pe fir (HdsModuleAcces.ModuleCitite), fara alta citire
		SR = _ReleuCuModule(SR, H.ModuleCitite(stari))
	rez = {"result": True, "feluri": feluri, "sufix_gol": H.SUFIX_GOL, "decripteaza_acum": decripteaza,
		"comanda": _comanda(H), "stream_relay": _streamRelay(H, SR), "icam": _icam(ruleaza, SC)}
	rez.update(_inAfaraListei(H, E, sistem, stari, citita["alte"] if citita is not None else None))
	rez["din_feed"] = _dinFeed(N, [st.fel for st in stari])
	try:
		rez["inlocuire"] = N.stareWeb() if N is not None else None
	except Exception as eroare:
		_jurnal("inlocuire: %r" % (eroare,))
		rez["inlocuire"] = None
	return rez


def _dinFeed(N, feluri):
	"""0.7.7: modulele din feed care nu sunt instalate, numai ale felurilor aratate, cu textul butonului; [] fara ele"""
	f = getattr(N, "dinFeed", None) if N is not None else None
	if f is None:
		return []
	try:
		return [dict(x, buton=N.textOfertaFeed(x)) for x in f() if x.get("fel") in feluri]
	except Exception as eroare:
		_jurnal("modulele din feed: %r" % (eroare,))
		return []


def inlocuieste(argumente, H=None, E=None, N=None, cu_stare=True, citita=None):
	"""POST /api/acces-conditionat-inlocuieste: „Pune <modul> din feedul HD Satelit” pentru un modul instalat care nu ruleaza
	(Components/HdsModulNepornit.porneste, pe un fir), sau, cu `pachet`, pentru un modul din feed care nu e instalat (numai un
	pachet din lista "din_feed" de acum). Raspunde pe loc; mersul vine prin GET ("inlocuire").
	0.7.7 (MG4): `citita` = citirea modulelor facuta pe un fir (Screens/CamSetup.citesteEcranul, prin _stareDinFir): felurile si
	modulul (daca e instalat, daca ruleaza) se iau din ea, fara alta citire pe firul enigma2; fara ea se citesc acum, ca pana
	acum. `cu_stare`=False da numai result si message (starea o pune _stareDinFir din aceeasi citire)."""
	H = _h(H)
	E = _ecran(E)
	N = _nepornit(N)
	st = (lambda: stare(H, E, N=N)) if cu_stare else dict
	sistem = H.SistemAcces()
	fel = argumente.get("fel") or ""
	sufix = argumente.get("sufix") or ""
	if N is None:
		return _cuMesaj(st(), False, _t("Comanda nu a pornit."))
	feluri = [s.fel for s in citita["stari"]] if citita is not None else H.feluri(sistem)
	pachet = argumente.get("pachet") or ""
	if pachet:
		x = [x for x in _dinFeed(N, feluri) if x["pachet"] == pachet and x["fel"] == fel]
		if not x:
			return _cuMesaj(st(), False, _t("Modulul ales nu există."))
		if not N.porneste(fel, x[0]["nume"], pachet=pachet):
			return _cuMesaj(st(), False, _t("Așteaptă să se termine comanda de acum."))
		_jurnal("pune din feed %s %s" % (fel, pachet))
		return _cuMesaj(st(), True, N.stareWeb().get("text") or _t("Comanda a pornit."))
	if fel not in feluri or not _SUFIX.match(sufix):
		return _cuMesaj(st(), False, _t("Modulul ales nu există."))
	e = _emulatorCitit(H, sistem, fel, sufix, citita)
	if e is None:
		return _cuMesaj(st(), False, _t("Modulul ales nu există."))
	if e.pids:
		return _cuMesaj(st(), False, E.text_rezultat({"ok": True, "motiv": "ruleaza_deja", "nume": sufix}))
	if not N.porneste(fel, sufix):
		return _cuMesaj(st(), False, _t("Așteaptă să se termine comanda de acum."))
	_jurnal("inlocuieste %s %s" % (fel, sufix))
	return _cuMesaj(st(), True, N.stareWeb().get("text") or _t("Comanda a pornit."))


def _emulatorCitit(H, sistem, fel, sufix, citita=None):
	"""0.7.7 (MG4): modulul <fel>.<sufix> din citirea de pe fir (`citita`, citesteEcranul), altfel citit acum; None cand nu e"""
	if citita is None:
		return H.citeste(sistem, fel).emulator(sufix)
	for s in citita["stari"]:
		if s.fel == fel:
			return s.emulator(sufix)
	return None


def _inAfaraListei(H, E, sistem, stari, alte=None):
	"""MDA (darog69, forum 479 #2447): ce ruleaza in afara listei, cu textele ecranului (Screens/CamSetup.text_alt,
	detalii_alt, text_ci): modulele pornite de alt program si modulul CI din fiecare slot. Numai citire. `alte` (0.7.7):
	modulele pornite de alt program, citite deja pe un fir."""
	rez = {"alte": [], "ci": []}
	try:
		for a in (H.pornite_de_alt_program(sistem, stari) if alte is None else alte):
			rez["alte"].append({"text": E.text_alt(a), "detalii": E.detalii_alt(a), "pid": a["pids"][0]})
		for slot, cod, nume in H.sloturi_ci():
			rez["ci"].append({"slot": slot, "stare": cod, "text": E.text_ci(slot, cod, nume)})
	except Exception as e:
		_jurnal("in afara listei: %r" % (e,))
	return rez


def _icam(ruleaza, SC=None):
	"""Randul ICAM (Components/HdsSoftCsa.randModul): modulul care ruleaza nu descifreaza canalele ICAM, sau "".
	`SC` e Components.HdsSoftCsa (probele dau unul fals)."""
	if not ruleaza:
		return ""
	try:
		if SC is None:
			from Components import HdsSoftCsa as SC
		return SC.randModul(_t, True)
	except Exception as eroare:
		_jurnal("ICAM: %r" % (eroare,))
		return ""


def _streamRelay(H, SR=None):
	"""Cardul Stream Relay: cate canale are lista, de unde se adauga, daca releul raspunde si de ce nu (aceleasi randuri
	ca ecranul setarilor Stream Relay, HdsStreamRelay.stare), sau None cand nu se pot citi."""
	try:
		if SR is None:
			from Components import HdsStreamRelay as SR
		s = SR.stare(H=H)
		return {"canale": s["canale"], "asculta": s["asculta"], "linii": list(s["linii"])}
	except Exception as eroare:
		_jurnal("Stream Relay: %r" % (eroare,))
		return None


class _ReleuCuModule(object):
	"""0.7.7: Components/HdsStreamRelay (sau `SR`, la probe) cu modulele deja citite (HdsModuleAcces.ModuleCitite) ca H."""

	def __init__(self, SR, H):
		self.SR = SR
		self.H = H

	def stare(self, H=None):
		SR = self.SR
		if SR is None:
			from Components import HdsStreamRelay as SR
		return SR.stare(H=self.H)


def _cuMesaj(rez, reusit, mesaj):
	rez = dict(rez)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def comanda(argumente, H=None, E=None, ceas=None, cu_stare=True):
	"""POST /api/acces-conditionat-comanda. Verifica cererea, porneste HdsModuleAcces.Operatie si raspunde pe loc;
	pasii si rezultatul (text_pas, text_rezultat) se tin aici pentru GET. Refuza cand ruleaza deja o comanda (de pe
	televizor sau din web). Felul trebuie sa fie unul de pe receptor (HdsModuleAcces.feluri); fara fel, primul.
	0.7.7 (IPE): `cu_stare`=False da numai result si message, fara starea modulelor: ComandaResource o adauga din citirea
	de pe fir (_stareDinFir), ca Verde si Rosu din pagina sa nu citeasca toate modulele pe firul enigma2. Cand comanda a
	pornit, atunci se intoarce o functie: result si message se socotesc la plecarea raspunsului (_cuAdaos)."""
	H = _h(H)
	E = _ecran(E)
	ceas = ceas or time.time
	st = stare if cu_stare else (lambda H, E: {})
	cerere = argumente.get("cerere") or ""
	feluri_receptor = H.feluri(H.SistemAcces())
	fel = argumente.get("fel") or (feluri_receptor[0] if feluri_receptor else "")
	sufix = argumente.get("sufix") or None
	if cerere not in H.CERERI:
		return _cuMesaj(st(H, E), False, _t("Comanda „%s” nu există.") % cerere[:MAX_VALOARE])
	if fel not in feluri_receptor or (sufix is not None and not _SUFIX.match(sufix)):
		return _cuMesaj(st(H, E), False, _t("Modulul ales nu există."))
	if cerere == "alege" and sufix is None:
		return _cuMesaj(st(H, E), False, _t("Modulul ales nu există."))
	if H.in_curs() is not None:
		return _cuMesaj(st(H, E), False, _t("Așteaptă să se termine comanda de acum."))
	gata = []
	operatie = [None]

	def laPas(actiune, nume):
		_STARE["pas"] = {"operatie": id(operatie[0]), "text": E.text_pas(actiune, nume)}

	def laFinal(r):
		_STARE["pas"] = None
		_STARE["ultima"] = {"ok": bool(r.get("ok")), "motiv": r.get("motiv") or "", "text": E.text_rezultat(r),
			"cand": int(ceas())}
		_jurnal("%s %s %s: %s" % (cerere, fel, sufix or "-", r.get("motiv")))
		gata.append(r)

	o = H.Operatie(cerere, fel=fel, sufix=sufix, la_pas=laPas, la_final=laFinal)
	operatie[0] = o
	_STARE["pas"] = None
	if not o.porneste() or gata:
		# terminata pe loc (nimic de facut, necunoscut, ocupat) sau fara niciun script de asteptat
		r = gata[0] if gata else (o.rezultat or {})
		return _cuMesaj(st(H, E), bool(r.get("ok")), E.text_rezultat(r) if r else _t("Comanda nu a pornit."))

	def raspuns():
		# 0.7.7 (IPE): pe receptor planul se citeste pe fir, deci un refuz (nimic pornit, ruleaza deja) sau primul pas vin dupa
		# porneste(); fara stare (cu_stare=False) raspunsul se socoteste abia cand pleaca, cu ce s-a intamplat pana atunci
		if gata:
			r = gata[0]
			return _cuMesaj(st(H, E), bool(r.get("ok")), E.text_rezultat(r))
		pas = _STARE["pas"]
		return _cuMesaj(st(H, E), True, pas["text"] if pas else _t("Comanda a pornit."))
	return raspuns() if cu_stare else raspuns


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, numai cheile stiute, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ARGUMENTE:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_VALOARE].strip()
	return rez


# ---------------------------------------------------------------- cheile publice (0.7.7)
# Cardul "Cheile publice (SoftCam.Key)", perechea randului din ecranul modulelor: aceeasi lucrare si aceleasi texte, traduse pe
# receptor (Components/HdsCheiPublice.py). Nimic nu se aduce singur, numai la butonul omului.
#   GET  /api/acces-conditionat-chei          {in_lucru, ok, mesaj, adresa, adresa_fabrica, ultima, fisiere, texte}, din memorie
#   POST /api/acces-conditionat-chei-cerere?cerere=adu|adresa[&adresa=<adresa>]
#                                          adu: descarca acum, pe un fir (raspunde pe loc; mersul vine prin GET);
#                                          adresa: adresa noua a omului (gol = cea din fabrica)
# Adresa nu trece prin argumente(), care taie la MAX_VALOARE: se citeste aici, cel mult HdsCheiPublice.ADRESA_MAXIM.
def _chei(K=None):
	if K is not None:
		return K
	from Components import HdsCheiPublice as K
	return K


def stare_chei(K=None):
	return dict(_chei(K).stareWeb(), result=True)


def argument_lung(request, nume, maxim):
	"""Un argument al cererii (si din corpul unui POST de formular), taiat la `maxim`; "" cand lipseste."""
	args = getattr(request, "args", None) or {}
	valori = args.get(nume.encode("ascii")) or args.get(nume) or []
	v = valori[0] if valori else b""
	if isinstance(v, bytes):
		v = v.decode("utf-8", "replace")
	return str(v)[:maxim].strip()


def cerere_chei(cerere, adresa="", K=None):
	"""POST /api/acces-conditionat-chei-cerere."""
	K = _chei(K)
	if cerere == "adu":
		if not K.porneste():
			return _cuMesaj(stare_chei(K), False, _t("Așteaptă să se termine comanda de acum."))
		_jurnal("cheile publice: aducere pornita")
		return _cuMesaj(stare_chei(K), True, K.stareWeb().get("mesaj") or _t("Comanda a pornit."))
	if cerere == "adresa":
		ok, mesaj = K.puneAdresa(adresa)
		return _cuMesaj(stare_chei(K), ok, mesaj)
	return _cuMesaj(stare_chei(K), False, _t("Comanda nu a pornit."))


def interfete_web(H=None):
	"""Date publice limitate la modul, port si protocol; fara sondarea paginii modulului."""
	try:
		return {"result": True, "interfete": _h(H).interfete_web()}
	except Exception:
		return {"result": False, "interfete": [], "message": _t("Adresele interfețelor web nu s-au putut citi.")}


def dosare_configurare(H=None):
	"""Numai caile si existenta dosarelor; fara continutul fisierelor de setari."""
	try:
		return {"result": True, "dosare": _h(H).dosare_configurare()}
	except Exception:
		return {"result": False, "dosare": []}


# 0.7.7: GET /api/acces-conditionat citeste modulele pe un fir (Screens/CamSetup.citesteEcranul,
# Components/HdsModuleAcces.CitirePeFir) si raspunde de pe firul enigma2. Pagina intreaba la 5 s, iar citirea facuta pe firul
# enigma2 il tinea 0,3-0,4 s, si 4,8-7,4 s cat calcula alt fir Python (masurat pe receptorul de probe; HdsModuleAcces, citirea pe un fir).
# Cererile venite cat merge o citire primesc aceeasi citire.
_CITIRE_WEB = {"cititor": None, "cereri": []}


def _cuAdaos(rez, adaos):
	if callable(adaos):
		adaos = adaos()      # comanda pornita: result si message de acum (comanda(cu_stare=False))
	if adaos:
		rez = dict(rez)
		rez.update(adaos)
	return rez


def _pentruCerere(H, E, citita, adaos=None, inainte=None):
	"""Raspunsul unei cereri din citirea `citita` (None: starea se citeste acum): intai inainte(citita) (0.7.7, MG4: comanda
	hotarata si pornita din aceeasi citire, pe firul enigma2), apoi starea, apoi campurile ei (adaos)."""
	if inainte is not None:
		adaos = inainte(citita)
	return _cuAdaos(stare(H, E, citita=citita), adaos)


def _stareDinFir(resursa, request, H=None, E=None, adaos=None, inainte=None):
	"""Raspunsul GET cu citirea pe un fir; intoarce NOT_DONE_YET. Pe un sistem de proba (HdsModuleAcces.citire_pe_fir: o
	radacina intr-un dosar) raspunsul se da pe loc, ca inainte. O citire pornita inainte de sfarsitul unei comenzi
	(HdsModuleAcces.generatie) e veche: atunci starea se citeste din nou, pe loc. `adaos` (0.7.7, IPE): campurile puse peste
	stare in raspunsul acestei cereri (result si message ale unei comenzi, POST). `inainte(citita)` (0.7.7, MG4): pe firul
	enigma2, dupa citire si inainte de stare, da campurile acestei cereri (POST Pune <modul> din feed: verificarea si pornirea
	din aceeasi citire, ca starea din raspuns sa arate deja lucrarea pornita); o eroare a ei da 500 numai cererii ei."""
	Hm = _h(H)
	sistem = Hm.SistemAcces()
	if not hasattr(Hm, "CitirePeFir") or not Hm.citire_pe_fir(sistem):
		return resursa._raspunde(request, _pentruCerere(H, E, None, adaos, inainte))
	Em = _ecran(E)
	Hm.pregateste_la_schimbare(sistem)    # pe firul enigma2, numai cand s-a schimbat ceva (citirea de pe fir nu pregateste)
	cerere = (request, adaos, inainte)
	_CITIRE_WEB["cereri"].append(cerere)
	c = _CITIRE_WEB["cititor"]
	if c is None:
		c = _CITIRE_WEB["cititor"] = Hm.CitirePeFir()
	if not c.in_curs():
		generatie = Hm.generatie()

		def gata(rezultat, eroare):
			cereri, _CITIRE_WEB["cereri"] = _CITIRE_WEB["cereri"], []
			if eroare is not None:
				_jurnal("citirea pe fir: %r" % (eroare,))
			citita = rezultat[1] if rezultat is not None and rezultat[0] == Hm.generatie() else None
			for r, adaos_r, inainte_r in cereri:
				try:
					corp = resursa._raspunde(r, _pentruCerere(H, E, citita, adaos_r, inainte_r))
				except Exception as e:
					corp = resursa._eroare(r, _t("Eroare pe receptor: %s") % e, 500)
				try:
					r.write(corp)
					r.finish()
				except Exception as e:
					_jurnal("raspunsul nu a plecat (client plecat?): %r" % (e,))
		try:
			c.porneste(lambda: (generatie, Em.citesteEcranul(sistem)), gata)
		except Exception:
			_CITIRE_WEB["cereri"].remove(cerere)
			raise
	from twisted.web.server import NOT_DONE_YET
	return NOT_DONE_YET


# ---------------------------------------------------------------- cititoarele, clientii si jurnalul modulului (0.7.7)
_STEAG_JURNAL = [False]
# portul interfetei modulului aratat (tinut JURNAL_INTERFATA_S) si pauza de dupa o parola care nu merge (failban)
_JURNAL = {"cheie": None, "interfata": None, "cand": 0.0, "oprit_pana": 0.0}
JURNAL_INTERFATA_S = 60.0
JURNAL_PAROLA_S = 600.0


def _jurnalModul(J=None):
	if J is not None:
		return J
	from Components import HdsJurnalModul
	return HdsJurnalModul


def modul_aratat(H, E):
	"""(nume, pid, eticheta) al modulului ca in Informatii despre decriptare: intai cel ales care ruleaza, apoi primul
	pornit (felurile in ordinea lor), apoi unul pornit de alt program; (None, None, "") cand nu ruleaza niciunul"""
	sistem = H.SistemAcces()
	stari = H.feluri_de_aratat(sistem)
	for st in stari:
		pornite = st.pornite()
		ales = st.ales_emulator()
		if ales is not None and ales.pids:
			pornite = [ales] + [e for e in pornite if e is not ales]
		if pornite:
			e = pornite[0]
			return e.sufix, E.pid_de_aratat(sistem, e.pids), H.eticheta_modul(e)
	for a in H.pornite_de_alt_program(sistem, stari):
		return a["nume"], E.pid_de_aratat(sistem, a["pids"]), a["nume"]
	return None, None, ""


def jurnal_modul(H=None, E=None, J=None, ceas=None):
	"""GET /api/acces-conditionat-jurnal, pe un fir: randurile cititoarelor, clientilor si jurnalului modulului care
	ruleaza (HdsJurnalModul.randuri_text, aceleasi ca pe televizor); linii [] cand nu ruleaza niciun modul sau modulul
	nu are interfata web din familia lui. O eroare (un proces disparut in timpul citirii) da {"result": False}."""
	try:
		return _jurnal_modul(H, E, J, ceas)
	except Exception as eroare:
		_jurnal("jurnalul modulului: %s" % eroare.__class__.__name__)
		return {"result": False, "modul": "", "linii": []}


def _jurnal_modul(H, E, J, ceas):
	H, E, J = _h(H), _ecran(E), _jurnalModul(J)
	acum = (ceas or time.time)()
	nume, pid, eticheta = modul_aratat(H, E)
	if nume is None:
		return {"result": True, "modul": "", "linii": []}
	cheie = (nume, pid)
	if _JURNAL["cheie"] != cheie:
		_JURNAL.update(cheie=cheie, interfata=None, cand=0.0, oprit_pana=0.0)
	if not _JURNAL["cand"] or acum - _JURNAL["cand"] > JURNAL_INTERFATA_S:
		_JURNAL.update(interfata=J.interfata_pentru(nume, pid, H), cand=acum)
	i = _JURNAL["interfata"]
	if not i:
		return {"result": True, "modul": eticheta, "linii": []}
	if acum < _JURNAL["oprit_pana"]:
		rez = {"ok": False, "eroare": J.PAROLA}
	else:
		rez = J.citeste(i["port"], i.get("protocol") or "http", nume)
		if rez.get("eroare") == J.PAROLA:
			_JURNAL["oprit_pana"] = acum + JURNAL_PAROLA_S
	return {"result": True, "modul": eticheta, "linii": J.randuri_text(rez, _t)}


def din_casa(request, P=None):
	"""True numai pentru o cerere din reteaua de acasa (aceeasi verificare ca pagina)"""
	try:
		if P is None:
			from . import plugin as P
		return bool(P._esteAdresaLocala(P._adresaClient(request)))
	except Exception:
		return False


def rute(baza, resource, H=None, E=None, pe_fir=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/acces-conditionat: numai citire (0.7.7: pe un fir, _stareDinFir)."""

		def render_GET(self, request):
			try:
				return _stareDinFir(self, request, H, E)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ComandaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				# 0.7.7 (IPE): comanda porneste pe loc, starea modulelor din raspuns vine din citirea de pe fir
				return _stareDinFir(self, request, H, E, adaos=comanda(argumente(request), H, E, cu_stare=False))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class InlocuiesteResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				# 0.7.7 (MG4): verificarea, pornirea si starea din raspuns din aceeasi citire de pe fir, nu de pe firul enigma2
				a = argumente(request)
				return _stareDinFir(self, request, H, E,
					inainte=lambda citita: inlocuieste(a, H, E, cu_stare=False, citita=citita))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class CheiResource(baza):
		"""GET /api/acces-conditionat-chei: starea cheilor publice, din memorie."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare_chei())
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class CheiCerereResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, cerere_chei(argumente(request).get("cerere") or "",
					argument_lung(request, "adresa", _chei().ADRESA_MAXIM)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class InterfeteWebResource(baza):
		def render_GET(self, request):
			if _STEAG_WEB[0]:
				return self._raspunde(request, {"result": False, "interfete": []})
			lucru = pe_fir
			if lucru is None:
				from .meniu_comun_web import peFir
				lucru = peFir
			return lucru(request, lambda: interfete_web(H), _STEAG_WEB, 10)

	class DosareResource(baza):
		def render_GET(self, request):
			if _STEAG_DOSARE[0]:
				return self._raspunde(request, {"result": False, "dosare": [], "ocupat": True})
			lucru = pe_fir
			if lucru is None:
				from .meniu_comun_web import peFir
				lucru = peFir
			return lucru(request, lambda: dosare_configurare(H), _STEAG_DOSARE, 10)

	class JurnalResource(baza):
		"""GET /api/acces-conditionat-jurnal (0.7.7): numai din reteaua de acasa, pe un fir, o citire odata."""

		def render_GET(self, request):
			if not din_casa(request):
				return self._eroare(request, _t("Acces permis doar din rețeaua locală."), 403)
			if _STEAG_JURNAL[0]:
				return self._raspunde(request, {"result": False, "ocupat": True, "linii": []})
			lucru = pe_fir
			if lucru is None:
				from .meniu_comun_web import peFir
				lucru = peFir
			return lucru(request, lambda: jurnal_modul(H, E), _STEAG_JURNAL, 15)

	class PaginaResource(resource.Resource):
		"""GET /acces-conditionat: pagina „Acces condiționat”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"acces-conditionat-chei": CheiResource(),
		b"acces-conditionat-chei-cerere": CheiCerereResource(),
		b"acces-conditionat": StareResource(),
		b"acces-conditionat-comanda": ComandaResource(),
		b"acces-conditionat-inlocuieste": InlocuiesteResource(),
		b"acces-conditionat-interfete": InterfeteWebResource(),
		b"acces-conditionat-dosare": DosareResource(),
		b"acces-conditionat-jurnal": JurnalResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /ceas, /limbi, /video si /sunet."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


# textele cardului „Pagina web a modulului” (0.2.8), traduse la afisare
TEXTE_CAM = {
	"__T_CAM_NOTA__": N_("Pagina web a modulului care rulează se deschide pe televizor, neschimbată, cu toate comenzile ei. Dacă cere utilizator și parolă, receptorul le dă singur, din setările modulului; dacă nu le găsește, le scrii cu telecomanda."),
	"__T_CAM_TV__": N_("Deschide pe televizor"),
	"__T_CAM_FARA__": N_("Niciun modul nu rulează acum, deci nu e nicio pagină web de deschis."),
	"__T_CAM_TELEFON__": N_("Din telefon sau calculator, pagina se deschide din lista interfețelor web:"),
}


def pagina_text(stil, config_pagina):
	import html
	text = _traducePagina(PAGINA)
	for cheie, sablon in TEXTE_CAM.items():
		text = text.replace(cheie, html.escape(_t(sablon), quote=False))
	return text.replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("cam_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acces condiționat</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1rem;margin:0 0 8px;color:var(--text-slab);font-weight:normal;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .modul{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 12px;padding:12px 0;border-top:1px solid var(--bordura);}
  .modul:first-of-type{border-top:0;padding-top:4px;}
  .modul .stanga{min-width:0;flex:1 1 260px;}
  .modul .nume{font-size:1rem;overflow-wrap:anywhere;}
  .modul .detaliu{color:var(--text-slab);font-size:.875rem;margin-top:3px;overflow-wrap:anywhere;line-height:1.4;}
  .modul .dosar{min-width:0;max-width:100%;}
  .dosar .cale-dosar{display:block;max-width:100%;color:var(--text);}
  .semn{display:inline-block;font-size:.8rem;border-radius:999px;padding:3px 10px;margin-left:6px;white-space:nowrap;background:#242a33;color:var(--text-slab);vertical-align:middle;}
  .semn.pornit{background:var(--verde);color:#fff;}
  .semn.ales{background:#2d3b66;color:#dfe6ff;}
  .adresa-chei{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:10px;}
  .adresa-chei input{flex:1 1 260px;min-width:0;min-height:44px;box-sizing:border-box;padding:6px 8px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  .butoane{display:flex;gap:8px;flex-wrap:wrap;}
  button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .buton-web{display:inline-flex;align-items:center;min-height:44px;min-width:0;max-width:100%;box-sizing:border-box;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);color:var(--text);text-decoration:none;}
  .acum{font-size:1.02rem;line-height:1.45;margin:0;}
  .nota{color:var(--text-slab);font-size:.875rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .legaturi{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:.9rem;}
  .legaturi a{color:var(--text);}
  .rand-jurnal{font-family:monospace;font-size:.82rem;margin:2px 0 0;overflow-wrap:anywhere;}
  @media (max-width:560px){ .butoane button{flex:1 1 auto;} }
</style>
</head>
<body>
<main>
<h1>Acces condiționat</h1>
<p class="mesaj" id="incarcare">Se citesc modulele de pe receptor...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Acum</h2>
    <p class="acum" id="decriptare"></p>
    <p class="nota" id="comanda"></p>
    <p class="nota ascuns" id="icam"></p>
    <div id="inafara"></div>
  </section>
  <div id="feluri"></div>
  <section class="card ascuns" id="chei">
    <h2 id="cheiTitlu"></h2>
    <p class="acum" id="cheiUltima"></p>
    <div class="butoane"><button type="button" class="verde" id="cheiAdu"></button></div>
    <p class="nota" id="cheiNota"></p>
    <p class="mesaj" id="cheiMesaj"></p>
    <div class="adresa-chei"><label for="cheiAdresa" id="cheiEticheta"></label><input id="cheiAdresa" type="url" maxlength="512" spellcheck="false" autocomplete="off"><button type="button" id="cheiSalveaza"></button></div>
    <p class="nota" id="cheiNotaAdresa"></p>
  </section>
  <section class="card ascuns" id="releu">
    <h2>Stream Relay</h2>
    <div id="releuStare"></div>
    <div class="legaturi"><a id="releuCanale" href="/canale">Lista de canale</a><a id="releuSetari" href="/setari?id=hds_stream_relay">Setările Stream Relay</a></div>
  </section>
  <section class="card ascuns" id="jurnalCard">
    <h2 id="jurnalTitlu"></h2>
    <div id="jurnalLinii"></div>
  </section>
  <section class="card">
    <h2>Pe televizor</h2>
    <div class="butoane">
      <button type="button" data-televizor="cam_setup">Deschide pe televizor: Module de acces condiționat</button>
      <button type="button" data-televizor="cam_info">Deschide pe televizor: Informații despre decriptare</button>
    </div>
    <p class="nota">Ce decriptează acum modulul (canalul, timpul de răspuns) se vede pe televizor, în Informații despre decriptare.</p>
  </section>
  <section class="card">
    <h2>Pagina web a modulului</h2>
    <p class="nota">Unele module au o pagină web proprie (setările, cititoarele, liniile).</p>
    <p class="nota">__T_CAM_NOTA__</p>
    <div class="butoane"><button type="button" id="camTv">__T_CAM_TV__</button></div>
    <p class="nota ascuns" id="camFara">__T_CAM_FARA__</p>
    <p class="nota">__T_CAM_TELEFON__</p>
    <div class="legaturi"><a id="interfete" href="/interfete-cam">Interfețele web ale modulelor</a></div>
  </section>
  <p class="nota">Aceleași comenzi sunt pe televizor, în __DRUM_MENIU__.</p>
  <p class="mesaj" id="mesaj"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var D = null;
var INTERFETE = [];
var interfeteInLucru = false;
var DOSARE = null;
var dosareInLucru = false;
var dosareEroare = false;
var semnaturaLista = null;
var randuriProcese = [];
var ocupat = false;
var astept = false;     // o comanda trimisa de aici merge inca: la sfarsit, rezultatul ei ia locul mesajului
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
$("interfete").href = adresa("/interfete-cam");
$("releuCanale").href = adresa("/canale");
$("releuSetari").href = adresa("/setari?id=hds_stream_relay");
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function el(tip, clasa, text){
  var e = document.createElement(tip);
  if(clasa){ e.className = clasa; }
  if(text !== undefined && text !== null){ e.textContent = String(text); }
  return e;
}
function mb(kb){ return (kb / 1024).toFixed(1).replace(".", ",") + " MB"; }
function adresaInterfataModul(interfata){
  if(!interfata || (interfata.protocol !== "http" && interfata.protocol !== "https")){ return null; }
  var port = Number(interfata.port);
  if(!Number.isInteger(port) || port < 1 || port > 65535){ return null; }
  var gazda = location.hostname;
  if(gazda.indexOf(":") !== -1 && gazda.charAt(0) !== "["){ gazda = "[" + gazda + "]"; }
  return interfata.protocol + "://" + gazda + ":" + port + "/";
}
function detaliiProces(m){
  if(!m.ruleaza){ return "Nu rulează."; }
  var t = "Rulează, procesul " + m.pid;
  var mem = m.memorie || {};
  if(mem.kb !== undefined){ t += ", memorie " + mb(mem.kb); }
  if(mem.fire !== undefined){ t += ", " + mem.fire + (mem.fire === 1 ? " fir" : (mem.fire < 20 ? " fire" : " de fire")); }
  if(m.procese > 1){ t += " (" + m.procese + " procese)"; }
  return t + ".";
}
function buton(text, clasa, fel, cerereNume, sufix, intrebare){
  var b = el("button", clasa || "", text);
  b.type = "button";
  b.addEventListener("click", function(){
    if(intrebare && !window.confirm(intrebare)){ return; }
    trimite(cerereNume, fel, sufix);
  });
  return b;
}
function detaliuDosar(f, m){
  var loc = el("div", "detaliu dosar");
  loc.appendChild(el("div", "hds-derulant", "Dosar de setări:"));
  var d = (DOSARE || []).find(function(d){ return d.fel === f.fel && d.sufix === m.sufix; });
  if(d && d.dosar){
    var cale = el(d.exista ? "a" : "span", "cale-dosar hds-derulant", d.dosar);
    cale.title = d.dosar;
    // Exploratorul merge din browser, fara jetonul panoului; din casa fara autentificare.
    if(d.exista){ cale.href = "/fisiere?cale=" + encodeURIComponent(d.dosar); }
    loc.appendChild(cale);
    if(!d.exista){ loc.appendChild(el("div", "hds-derulant", "Dosarul nu există încă.")); }
  } else {
    loc.appendChild(el("div", "hds-derulant", DOSARE === null && !dosareEroare
      ? "Se citește dosarul de setări..." : "Dosarul de setări nu a putut fi determinat."));
  }
  return loc;
}
function randModul(f, m){
  var rand = el("div", "modul");
  var stanga = el("div", "stanga");
  var nume = el("div", "nume", m.sufix + (m.versiune ? " " + m.versiune : ""));
  if(m.ales){ nume.appendChild(el("span", "semn ales", "ales")); }
  nume.appendChild(el("span", "semn" + (m.ruleaza ? " pornit" : ""), m.ruleaza ? "rulează" : "oprit"));
  stanga.appendChild(nume);
  if(m.descriere){ stanga.appendChild(el("div", "detaliu", m.descriere)); }
  var proces = el("div", "detaliu", detaliiProces(m) + (m.ales ? " Pornește la fiecare pornire a receptorului." : ""));
  stanga.appendChild(proces);
  randuriProcese.push({fel: f.fel, sufix: m.sufix, element: proces});
  // 0.7.7: de ce nu poate porni (textul vine tradus de pe receptor)
  if(m.nepornit && m.nepornit.text){ stanga.appendChild(el("div", "detaliu", m.nepornit.text)); }
  stanga.appendChild(detaliuDosar(f, m));
  rand.appendChild(stanga);
  var b = el("div", "butoane");
  if(m.nepornit && m.nepornit.buton){
    // 0.7.7: pachetul nostru al aceluiasi modul, instalat, ales si pornit
    var bi = el("button", "verde", m.nepornit.buton);
    bi.type = "button";
    bi.addEventListener("click", function(){ inlocuieste(f.fel, m.sufix); });
    b.appendChild(bi);
  }
  if(!m.ales){
    b.appendChild(buton("Alege", m.nepornit ? "" : "verde", f.fel, "alege", m.sufix,
      "Se alege " + m.sufix + ": modulul de acum se oprește, iar " + m.sufix + " pornește acum și la fiecare pornire a receptorului. Continui?"));
  } else if(!m.ruleaza){
    b.appendChild(buton("Pornește", "verde", f.fel, "porneste", m.sufix));
  }
  if(m.ruleaza){
    INTERFETE.forEach(function(i){
      if(i.fel !== f.fel || i.sufix !== m.sufix){ return; }
      var adresaWeb = adresaInterfataModul(i);
      if(!adresaWeb){ return; }
      var a = el("a", "buton-web hds-derulant", "Interfața web");
      a.href = adresaWeb; a.target = "_blank"; a.rel = "noopener noreferrer";
      b.appendChild(a);
    });
    b.appendChild(buton("Oprește", "", f.fel, "opreste", m.sufix,
      "Se oprește " + m.sufix + ": canalele criptate nu se mai văd până îl pornești din nou. Continui?"));
  }
  if(m.ales || m.ruleaza){
    b.appendChild(buton("Repornește", "", f.fel, "reporneste", m.sufix));
  }
  rand.appendChild(b);
  return rand;
}
function randFeed(f, x){
  // 0.7.7: un modul din feedul HD Satelit care nu e instalat (textele vin traduse de pe receptor)
  var rand = el("div", "modul");
  var stanga = el("div", "stanga");
  stanga.appendChild(el("div", "nume", x.nume + (x.versiune ? " " + x.versiune : "")));
  if(x.descriere){ stanga.appendChild(el("div", "detaliu", x.descriere)); }
  rand.appendChild(stanga);
  var b = el("div", "butoane");
  var bi = el("button", "verde", x.buton);
  bi.type = "button";
  bi.addEventListener("click", function(){ inlocuieste(f.fel, "", x.pachet); });
  b.appendChild(bi);
  rand.appendChild(b);
  return rand;
}
function randNiciunul(f){
  var rand = el("div", "modul");
  var stanga = el("div", "stanga");
  var nume = el("div", "nume", "Niciunul");
  if(f.niciunul_ales){ nume.appendChild(el("span", "semn ales", "ales")); }
  stanga.appendChild(nume);
  stanga.appendChild(el("div", "detaliu", "La pornirea receptorului nu pornește niciun modul."));
  rand.appendChild(stanga);
  if(!f.niciunul_ales){
    var b = el("div", "butoane");
    b.appendChild(buton("Alege", "", f.fel, "alege", D.sufix_gol,
      "La pornirea receptorului nu va mai porni niciun modul, iar cel de acum se oprește. Continui?"));
    rand.appendChild(b);
  }
  return rand;
}
function arata(d){
  D = d;
  $("decriptare").textContent = d.decripteaza_acum
    ? "Receptorul decriptează acum un canal."
    : "Receptorul nu decriptează acum niciun canal (canalul de acum nu este criptat sau niciun modul nu îl decriptează).";
  // modulul pornit nu descifreaza canalele ICAM (textul vine tradus, "" cand nu e cazul)
  $("icam").textContent = d.icam || "";
  $("icam").classList.toggle("ascuns", !d.icam);
  // MDA: modulul pornit de alt program si modulul CI din slot (textele vin traduse), cu legatura spre pagina CI
  var afara = $("inafara"); afara.textContent = "";
  (d.alte || []).forEach(function(a){
    afara.appendChild(el("p", "acum", a.text));
    (a.detalii || []).forEach(function(t){ afara.appendChild(el("p", "nota", t)); });
    // interfata web a modulului pornit de alt program (fel gol, pid = al randului lui)
    INTERFETE.forEach(function(i){
      if(i.fel || !i.pid || i.pid !== a.pid){ return; }
      var adresaWeb = adresaInterfataModul(i);
      if(!adresaWeb){ return; }
      var p = el("p", "acum"), w = el("a", "buton-web hds-derulant", "Interfața web");
      w.href = adresaWeb; w.target = "_blank"; w.rel = "noopener noreferrer";
      p.appendChild(w); afara.appendChild(p);
    });
  });
  (d.ci || []).forEach(function(c){
    var p = el("p", "acum"), a = el("a", "", c.text);
    a.href = adresa("/common-interface"); p.appendChild(a); afara.appendChild(p);
  });
  var c = d.comanda || {};
  ocupat = !!c.in_curs;
  if(c.in_curs){ $("comanda").textContent = c.text || ""; }
  else if(c.ultima){ $("comanda").textContent = "Ultima comandă din pagină: " + c.ultima.text; }
  else { $("comanda").textContent = ""; }
  // 0.7.7: lucrarea „Pune <modul> din feedul HD Satelit” (textele vin traduse de pe receptor)
  var inl = d.inlocuire;
  if(inl && inl.in_lucru){ ocupat = true; $("comanda").textContent = inl.text || ""; }
  if(asteptInlocuire && inl && !inl.in_lucru){
    asteptInlocuire = false;
    if(inl.text){ mesaj(inl.text, !inl.ok); }
  }
  if(astept && !c.in_curs){
    astept = false;
    if(c.ultima){ mesaj(c.ultima.text, !c.ultima.ok); }
  }
  // Pastreaza nodurile si derularea cailor cand se schimba numai cifrele proceselor.
  var semnatura = JSON.stringify(d.feluri || [], function(k, v){
    return k === "pid" || k === "procese" || k === "memorie" ? undefined : v;
  }) + JSON.stringify([INTERFETE, DOSARE, DOSARE === null && dosareEroare, d.din_feed || []]);
  if(semnaturaLista !== semnatura){
    semnaturaLista = semnatura;
    randuriProcese = [];
    var loc = $("feluri"); loc.textContent = "";
    (d.feluri || []).forEach(function(f){
      var card = el("section", "card");
      card.appendChild(el("h2", "", f.eticheta));
      if(!f.module.length){
        card.appendChild(el("p", "nota", "Nu este instalat niciun modul de acces condiționat. După ce se instalează pachetul unui modul, acesta apare aici."));
      } else {
        card.appendChild(randNiciunul(f));
        f.module.forEach(function(m){ card.appendChild(randModul(f, m)); });
      }
      (d.din_feed || []).forEach(function(x){ if(x.fel === f.fel){ card.appendChild(randFeed(f, x)); } });
      if(f.fara_script && f.fara_script.length){
        card.appendChild(el("p", "nota", "Programe fără script de pornire, care nu se pot porni de aici: " + f.fara_script.join(", ")));
      }
      loc.appendChild(card);
    });
  } else {
    randuriProcese.forEach(function(r){
      var f = (d.feluri || []).find(function(f){ return f.fel === r.fel; });
      var m = f && (f.module || []).find(function(m){ return m.sufix === r.sufix; });
      if(m){
        var text = detaliiProces(m) + (m.ales ? " Pornește la fiecare pornire a receptorului." : "");
        if(r.element.textContent !== text){ r.element.textContent = text; }
      }
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll("#feluri button"), function(b){ b.disabled = ocupat; });
  // pagina web a modulului pe televizor: numai cand ruleaza un modul
  var ruleaza = (d.feluri || []).some(function(f){ return (f.module || []).some(function(m){ return m.ruleaza; }); })
    || !!(d.alte && d.alte.length);
  $("camTv").disabled = !ruleaza;
  $("camFara").classList.toggle("ascuns", ruleaza);
  // Stream Relay: cate canale are lista, de unde se adauga, daca releul raspunde si de ce nu (textele vin traduse)
  var sr = d.stream_relay, loc2 = $("releuStare");
  loc2.textContent = "";
  (sr && sr.linii || []).forEach(function(t, i){ loc2.appendChild(el("p", i ? "nota" : "acum", t)); });
  $("releu").classList.toggle("ascuns", !sr);
}
$("camTv").addEventListener("click", function(){
  mesaj("Se deschide pe televizor...");
  cerere("/api/navigator-cam", "POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
var jurnalInLucru = false, jurnalCitit = 0;
function citesteJurnal(){
  // cititoarele, clientii si jurnalul modulului care ruleaza (aceleasi randuri ca pe televizor, deja traduse); cel mult
  // o data la 10 s (receptorul cauta modulul in /proc la fiecare cerere)
  if(jurnalInLucru || Date.now() - jurnalCitit < 10000){ return; }
  jurnalInLucru = true;
  jurnalCitit = Date.now();
  cerere("/api/acces-conditionat-jurnal").then(function(d){
    if(d.ocupat){ return; }
    var linii = d.result ? (d.linii || []) : [];
    $("jurnalCard").classList.toggle("ascuns", !linii.length);
    $("jurnalTitlu").textContent = d.modul || "";
    var loc = $("jurnalLinii");
    loc.textContent = "";
    linii.forEach(function(t){
      var rand = t.indexOf("  ") === 0;
      loc.appendChild(el("p", rand ? "nota rand-jurnal" : "acum", rand ? t.slice(2) : t));
    });
  }).catch(function(){}).then(function(){ jurnalInLucru = false; });
}
function citeste(){
  citesteInterfete();
  citesteDosare();
  citesteJurnal();
  return cerere("/api/acces-conditionat").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi modulele."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function citesteInterfete(){
  if(interfeteInLucru){ return; }
  interfeteInLucru = true;
  cerere("/api/acces-conditionat-interfete").then(function(d){
    if(d.result){ INTERFETE = d.interfete || []; if(D){ arata(D); } }
  }).catch(function(){}).then(function(){ interfeteInLucru = false; });
}
function citesteDosare(){
  if(dosareInLucru){ return; }
  dosareInLucru = true;
  return cerere("/api/acces-conditionat-dosare").then(function(d){
    if(d.result){ DOSARE = d.dosare || []; dosareEroare = false; }
    else if(!d.ocupat){ dosareEroare = true; }
  }).catch(function(){ dosareEroare = true; }).then(function(){
    dosareInLucru = false;
    if(D){ arata(D); }
  });
}
var asteptInlocuire = false;
function inlocuieste(fel, sufix, pachet){
  var q = new URLSearchParams();
  q.set("fel", fel);
  if(pachet){ q.set("pachet", pachet); } else { q.set("sufix", sufix); }
  mesaj("Se trimite...");
  cerere("/api/acces-conditionat-inlocuieste", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    asteptInlocuire = !!d.result;
    if(d.feluri){ arata(d); }
    setTimeout(citeste, 1500);
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function trimite(cerereNume, fel, sufix){
  var q = new URLSearchParams();
  q.set("cerere", cerereNume); q.set("fel", fel);
  if(sufix){ q.set("sufix", sufix); }
  mesaj("Se trimite...");
  cerere("/api/acces-conditionat-comanda", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    astept = !!(d.result && d.comanda && d.comanda.in_curs);
    if(d.feluri){ arata(d); }
    if(ocupat){ setTimeout(citeste, 1500); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
Array.prototype.forEach.call(document.querySelectorAll("[data-televizor]"), function(b){
  b.addEventListener("click", function(){
    var q = new URLSearchParams(); q.set("id", b.getAttribute("data-televizor"));
    mesaj("Se deschide pe televizor...");
    cerere("/api/meniu-televizor", "POST", q).then(function(d){ mesaj(d.message, !d.result); })
      .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
  });
});
function bucla(){
  var pas = ocupat ? 1500 : 5000;
  (document.hidden ? Promise.resolve() : citeste()).then(function(){ setTimeout(bucla, ocupat ? 1500 : pas); });
}
bucla();
// cheile publice (SoftCam.Key): textele vin traduse de pe receptor; campul adresei nu se rescrie cat il schimba omul
var cheiAdresaAtinsa = false;
var cheiAstept = false;
function arataChei(d){
  if(!d || !d.texte){ return; }
  var t = d.texte;
  $("cheiTitlu").textContent = t.titlu; $("cheiAdu").textContent = t.buton; $("cheiNota").textContent = t.nota;
  $("cheiEticheta").textContent = t.eticheta_adresa; $("cheiSalveaza").textContent = t.salveaza;
  $("cheiNotaAdresa").textContent = t.nota_adresa;
  $("cheiUltima").textContent = d.ultima || "";
  $("cheiMesaj").textContent = d.message || d.mesaj || "";
  $("cheiMesaj").classList.toggle("eroare", d.result === false || (!!d.mesaj && !d.ok && !d.in_lucru));
  if(!cheiAdresaAtinsa){ $("cheiAdresa").value = d.adresa || ""; }
  $("cheiAdu").disabled = !!d.in_lucru;
  $("chei").classList.remove("ascuns");
  if(d.in_lucru && !cheiAstept){ cheiAstept = true; setTimeout(citesteChei, 1000); }
}
function citesteChei(){
  cheiAstept = false;
  cerere("/api/acces-conditionat-chei").then(arataChei).catch(function(){});
}
function cerereChei(q){
  cerere("/api/acces-conditionat-chei-cerere", "POST", q).then(function(d){
    // adresa salvata: campul ia adresa de pe receptor; adresa refuzata ramane in camp, cu mesajul
    if(q.get("cerere") === "adresa" && d.result){ cheiAdresaAtinsa = false; }
    arataChei(d);
  }).catch(function(){ $("cheiMesaj").textContent = "Receptorul nu răspunde."; $("cheiMesaj").classList.add("eroare"); });
}
$("cheiAdu").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("cerere", "adu"); cerereChei(q);
});
$("cheiAdresa").addEventListener("input", function(){ cheiAdresaAtinsa = true; });
$("cheiSalveaza").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("cerere", "adresa"); q.set("adresa", $("cheiAdresa").value); cerereChei(q);
});
citesteChei();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Acces condiționat"),
		N_("Se citesc modulele de pe receptor..."),
		N_("Acum"),
		N_("Pe televizor"),
		N_("Deschide pe televizor: Module de acces condiționat"),
		N_("Deschide pe televizor: Informații despre decriptare"),
		N_("Ce decriptează acum modulul (canalul, timpul de răspuns) se vede pe televizor, în Informații "
			"despre decriptare."),
		N_("Pagina web a modulului"),
		N_("Unele module au o pagină web proprie (setările, cititoarele, liniile)."),
		N_("Interfețele web ale modulelor"),
		N_("Aceleași comenzi sunt pe televizor, în __DRUM_MENIU__."),
		N_("Stream Relay"),
		N_("Lista de canale"),
		N_("Setările Stream Relay"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Nu rulează."),
		N_("Rulează, procesul"),
		N_(", memorie"),
		N_("fir"),
		N_("fire"),
		N_("de fire"),
		N_("rulează"),
		N_("Pornește la fiecare pornire a receptorului."),
		N_("Alege"),
		N_("Se alege"),
		N_(": modulul de acum se oprește, iar"),
		N_("pornește acum și la fiecare pornire a receptorului. Continui?"),
		N_("Pornește"),
		N_("Oprește"),
		N_("Se oprește"),
		N_(": canalele criptate nu se mai văd până îl pornești din nou. Continui?"),
		N_("Repornește"),
		N_("Interfața web"),
		N_("Dosar de setări:"),
		N_("Dosarul nu există încă."),
		N_("Se citește dosarul de setări..."),
		N_("Dosarul de setări nu a putut fi determinat."),
		N_("Niciunul"),
		N_("La pornirea receptorului nu pornește niciun modul."),
		N_("La pornirea receptorului nu va mai porni niciun modul, iar cel de acum se oprește. Continui?"),
		N_("Receptorul decriptează acum un canal."),
		N_("Receptorul nu decriptează acum niciun canal (canalul de acum nu este criptat sau niciun modul "
			"nu îl decriptează)."),
		N_("Ultima comandă din pagină:"),
		N_("Nu este instalat niciun modul de acces condiționat. După ce se instalează pachetul unui modul, "
			"acesta apare aici."),
		N_("Programe fără script de pornire, care nu se pot porni de aici:"),
		N_("Se deschide pe televizor..."),
		N_("Receptorul nu răspunde."),
		N_("Receptorul nu a putut citi modulele."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
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
