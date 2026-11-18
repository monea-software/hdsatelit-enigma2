# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsModulNepornit.py: modulul de acces care nu poate porni (0.7.7, 16.11.2026). Un modul pus din pachetul altui autor arata in
# ecranul modulelor numai raspunsul scriptului lui („Script response (code 1): /usr/softcams/ncam is missing”, sau „...: line 9
# /usr/bin/oscam: ...” si „nu a pornit”), iar omul crede ca imaginii ii lipsesc fisiere. Aici, doua lucruri:
#   - diagnostic(): de ce nu porneste, intr-o fraza: programul scris in script lipseste, nu are drept de pornire, e facut pentru
#     alt procesor, ii lipseste incarcatorul sau o biblioteca. Numai citire (scriptul si antetul ELF al programului), nimic
#     pornit; aratat in ecranul modulelor (Screens/CamSetup.py) si in pagina web (HdsWebControl/acces_conditionat_web.py) sub
#     modulul care nu ruleaza. Bibliotecile vechi pe care feedul le are se pun deja singure (Components/HdsBibliotecaLipsa.py);
#     atunci fraza spune asta;
#   - porneste(): la o apasare a omului (OK pe randul modulului, prima alegere, sau butonul din pagina web), pachetul NOSTRU al
#     aceluiasi modul (acelasi nume de modul; cu „-emu” cand numele modulului strain il are) din feedurile HD Satelit
#     (HdsModuleLipsa.provenienta) se instaleaza (sau se reinstaleaza, cand scriptul stricat e chiar al lui), apoi e ales in locul
#     celui stricat si pornit (HdsModuleAcces.Operatie „alege”, aceeasi ca Verde). Pachetul strain ramane instalat, setarile
#     omului raman, nu se sterge nimic; fara --force-overwrite: daca opkg refuza (un fisier al altui pachet), alegerea de
#     dinainte ramane si omul afla de ce. Nimic nu se instaleaza singur, numai la cererea omului (a doua parere, 16.11.2026).
#   - dinFeed() (0.7.7): modulele din feedurile HD Satelit care NU sunt instalate, aratate in ecranul modulelor si in
#     pagina web sub cele instalate, fiecare cu "Pune <modul> din feedul HD Satelit"; OK le instaleaza, le alege si le porneste
#     (porneste(..., pachet=<pachetul din lista>)), dintr-o apasare, fara drumul prin Extensii. Vezi sectiunea de la coada.
# Logica nu are nume de module: felul, scriptul si programul vin de pe receptor, iar pachetul nostru se gaseste dupa forma
# numelui (HdsReinstalare.rest_acces / familie_modul, ca la restaurarea setarilor); numele din comentarii sunt numai exemplele
# cazurilor reale.
# Nu importa nimic din enigma la incarcare (probele de pe PC); `rad` si `sistem` se dau la probe.
import os
import posixpath
import re
import subprocess
import time

try:
	from Components import HdsBibliotecaLipsa as B
	from Components import HdsReinstalare as R
	from Components.HdsInterfeteCam import DOSAR_SCRIPTURI, SCRIPT_MAXIM, SUFIX_GOL, _CALE_ABSOLUTA, _desface, \
		variabile_script
except ImportError:  # probe pe PC: modulul incarcat din dosarul Components
	import HdsBibliotecaLipsa as B
	import HdsReinstalare as R
	from HdsInterfeteCam import DOSAR_SCRIPTURI, SCRIPT_MAXIM, SUFIX_GOL, _CALE_ABSOLUTA, _desface, variabile_script

MOTIVE = ("program_lipsa", "neexecutabil", "alt_procesor", "biblioteca_lipsa")
DOSARE_BIBLIOTECI = ("/lib", "/usr/lib")
# dosarele in care pachetele modulelor isi pun programele (in afara de /usr/<fel>s, dosarul felului)
DOSARE_PROGRAME = ("/usr/bin", "/usr/sbin", "/usr/local/bin", "/var/bin", "/usr/camd", "/usr/emu", "/var/emu", "/usr/cam")
# variabilele scripturilor OE-A care tin calea programului (numele variabilei, nu al vreunui modul)
_VAR_PROGRAM = re.compile(r"(?:^|_)(?:DAEMON|BINARY|BIN|BINARYFILE|EXEC|EXE|PROG|PROGRAM)$")
_CUVANT_MODUL = re.compile(r"cams?d?[0-9]*$")
_NUME_PROGRAM = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.+-]{0,63}$")
# e_machine -> numele procesorului, pentru om
PROCESOARE = {8: "MIPS", 40: "ARM", 183: "ARM 64-bit", 3: "x86", 62: "x86-64", 42: "SH4", 20: "PowerPC"}
TERMEN_UPDATE_S = 300
TERMEN_INSTALARE_S = 600
IESIRE_MAXIM = 600

_stare = {"lucrare": None, "fel": "", "sufix": "", "faza": "", "text": "", "ok": False, "cand": 0}
_ascultatori = []
_cache = {}


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsModulNepornit] %s" % text)


# ---------------------------------------------------------------- diagnosticul (numai citire)

def _cuvinte(text):
	return [c for c in re.split(r"[^a-z0-9]+", (text or "").lower()) if c]


def _familie(*nume):
	"""numele modulului (ultimul cuvant terminat in cam/cams/camd) din sufixul scriptului sau din numele pachetului; "" altfel"""
	for n in nume:
		f = R.familie_modul(n or "")
		if f:
			return f
	return ""


def programe(sistem, fel, sufix):
	"""Caile programului scrise in scriptul <fel>.<sufix>, existente sau nu: cele din variabilele de tip DAEMON, cele din
	dosarul felului (/usr/<fel>s) si, din dosarele de programe, cele cu numele modulului. Fara unelte de sistem."""
	try:
		text = sistem.citeste(DOSAR_SCRIPTURI + "/" + fel + "." + sufix, SCRIPT_MAXIM)
	except (OSError, IOError):
		return []
	valori = variabile_script(text)
	rez = []

	def adauga(p):
		p = (p or "").rstrip("/")
		d, n = posixpath.split(p)
		if p.startswith("/") and _NUME_PROGRAM.match(n) and p not in rez and not n.endswith((".pid", ".log", ".conf", ".cfg",
				".key", ".sh", ".txt", ".info", ".json", ".xml", ".list", ".lock")):
			rez.append(p)
	for k, v in sorted(valori.items()):
		if _VAR_PROGRAM.search(k) and v.startswith("/") and " " not in v:
			adauga(v)
	dosar_fel = "/usr/" + fel + "s"
	for m in _CALE_ABSOLUTA.finditer(_desface(text, valori)):
		p = m.group(1).rstrip("/")
		d, n = posixpath.split(p)
		if d == dosar_fel or (d in DOSARE_PROGRAME and any(_CUVANT_MODUL.search(c) for c in _cuvinte(n))):
			adauga(p)
	return rez[:8]


def _biblioteca_exista(sistem, nume):
	return any(sistem.exista(d + "/" + nume) for d in DOSARE_BIBLIOTECI)


def _harta_bibliotecilor():
	try:
		from Components.HdsModuleLipsa import BIBLIOTECI
	except ImportError:
		try:
			from HdsModuleLipsa import BIBLIOTECI
		except ImportError:
			return {}
	return BIBLIOTECI


def diagnostic(sistem, fel, sufix, masina=None, harta=None):
	"""None (nu se vede de ce n-ar porni) sau {"motiv", "program", "detaliu", "din_feed"}: primul program al scriptului care nu
	poate porni si de ce. `masina` = e_machine al receptorului (implicit HdsBibliotecaLipsa.masinaNoastra())."""
	if harta is None:
		harta = _harta_bibliotecilor()
	noi = B.masinaNoastra() if masina is None else masina
	for p in programe(sistem, fel, sufix):
		if not sistem.exista(p):
			return {"motiv": "program_lipsa", "program": p, "detaliu": "", "din_feed": False}
		real = sistem.tinta(p)
		if not sistem.exista(real):
			return {"motiv": "program_lipsa", "program": p, "detaliu": "", "din_feed": False}
		if not sistem.executabil(p):
			return {"motiv": "neexecutabil", "program": p, "detaliu": "", "din_feed": False}
		elf = B.citesteElf(sistem.cale(real))
		if elf is None:
			continue   # un script sau alt fel de fisier: nu se vede mai mult de aici
		e_machine, interpretor, biblioteci = elf
		if noi is not None and e_machine != noi:
			return {"motiv": "alt_procesor", "program": p, "detaliu": PROCESOARE.get(e_machine, "e_machine %d" % e_machine),
				"din_feed": False}
		if interpretor.startswith("/") and not sistem.exista(interpretor):
			n = interpretor.rsplit("/", 1)[-1]
			return {"motiv": "biblioteca_lipsa", "program": p, "detaliu": interpretor, "din_feed": n in harta}
		for b in biblioteci:
			if "/" not in b and not _biblioteca_exista(sistem, b):
				return {"motiv": "biblioteca_lipsa", "program": p, "detaliu": b, "din_feed": b in harta}
	return None


def diagnosticPeEcran(sistem, fel, sufix):
	"""diagnostic() tinut minte dupa marimea si ora scriptului si a programelor lui (ecranul il cere la fiecare mutare a
	cursorului si la 5 s; antetul ELF se citeste o data)."""
	try:
		semn = [fel, sufix]
		for p in [DOSAR_SCRIPTURI + "/" + fel + "." + sufix] + programe(sistem, fel, sufix):
			try:
				st = os.stat(sistem.cale(p))
				semn.append((p, st.st_size, int(st.st_mtime), st.st_mode))
			except OSError:
				semn.append((p, None))
		cheie = repr(semn)
		if cheie not in _cache:
			if len(_cache) > 32:
				_cache.clear()
			_cache[cheie] = diagnostic(sistem, fel, sufix)
		return _cache[cheie]
	except Exception as e:
		_jurnal("diagnostic %s.%s: %r" % (fel, sufix, e))
		return None


def text(d):
	"""Fraza pentru om (ecranul si pagina web)."""
	if not d:
		return ""
	m, p, x = d.get("motiv"), d.get("program", ""), d.get("detaliu", "")
	if m == "program_lipsa":
		return _("Modulul nu este întreg: lipsește programul %s.") % p
	if m == "neexecutabil":
		return _("Programul %s nu are drept de pornire.") % p
	if m == "alt_procesor":
		return _("Programul %s este făcut pentru alt procesor (%s) și nu poate porni pe acest receptor.") % (p, x)
	if m == "biblioteca_lipsa" and d.get("din_feed"):
		return _("Programului %s îi lipsește %s; fișierul vine singur din feedul HD Satelit.") % (p, x)
	if m == "biblioteca_lipsa":
		return _("Programului %s îi lipsește %s, care nu este în imagine.") % (p, x)
	return ""


def numeModul(sufix, pachet=""):
	"""Numele modulului pentru om, cum il scrie scriptul (NCam din NCam_15.8), cu „-emu” cand numele il are."""
	f = _familie(sufix, pachet)
	if not f:
		return sufix
	i = (sufix or "").lower().find(f)
	nume = sufix[i:i + len(f)] if i >= 0 else f
	if "emu" in _cuvinte(sufix) + _cuvinte(pachet) and "emu" not in _cuvinte(nume):
		nume += "-emu"
	return nume


def textOferta(sufix, pachet=""):
	return _("Pune %s din feedul HD Satelit") % numeModul(sufix, pachet)


def randOk(sufix):
	"""Randul din detaliile ecranului modulelor: ce face OK pe modulul care nu poate porni."""
	return _("Apasă OK: %s.") % textOferta(sufix)


# ---------------------------------------------------------------- pachetul nostru al aceluiasi modul

def proprietar(rad, cale):
	"""Pachetul care a pus fisierul `cale` (din /var/lib/opkg/info/*.list), sau ""."""
	d = R._c(rad, "var/lib/opkg/info")
	try:
		nume = sorted(os.listdir(d))
	except OSError:
		return ""
	for n in nume:
		if not n.endswith(".list"):
			continue
		try:
			with open(os.path.join(d, n), "r", encoding="utf-8", errors="replace") as f:
				for rand in f.read(512 * 1024).splitlines():
					if rand.split("\t", 1)[0].strip() == cale:
						return n[:-5]
		except (OSError, IOError):
			continue
	return ""


def inlocuitor(fel, sufix, pachet_strain, disponibile):
	"""(pachetul nostru, reinstalare) pentru modulul <fel>.<sufix>, din `disponibile` (numele din listele feedurilor), sau
	(None, False). Scriptul stricat al unui pachet nostru = acelasi pachet, reinstalat."""
	if pachet_strain and pachet_strain in disponibile and R.rest_acces(pachet_strain):
		return pachet_strain, True
	ale_noastre = {}
	for n in disponibile:
		r = R.rest_acces(n)
		if r:
			ale_noastre.setdefault(r, []).append(n)
	f = _familie(sufix, pachet_strain)
	if f:
		emu = "emu" in _cuvinte(sufix) + _cuvinte(pachet_strain)
		for rest in ((f + "-emu", f) if emu else (f,)):
			if rest in ale_noastre:
				p = sorted(ale_noastre[rest])[0]
				return p, p == pachet_strain
	p = R.pachet_din_feed(pachet_strain or sufix, disponibile) if (pachet_strain or sufix) else None
	return (p, p == pachet_strain) if p else (None, False)


TIPAR_SCRIPT = re.compile(r"^/?etc/init\.d/([A-Za-z][A-Za-z0-9_-]{0,31})\.([A-Za-z0-9][A-Za-z0-9._+-]{0,63})$")


def scriptulPachetului(rad, pachet, fel):
	"""Sufixul scriptului <fel>.<x> pus de `pachet` (din .list-ul lui), sau ""."""
	try:
		with open(R._c(rad, "var/lib/opkg/info/%s.list" % pachet), "r", encoding="utf-8", errors="replace") as f:
			randuri = f.read(256 * 1024).splitlines()
	except (OSError, IOError):
		return ""
	for rand in randuri:
		m = TIPAR_SCRIPT.match(rand.split("\t", 1)[0].strip())
		if m and m.group(1) == fel and m.group(2) != SUFIX_GOL and os.path.isfile(R._c(rad, "etc/init.d/%s.%s" % m.groups())):
			return m.group(2)
	return ""


def _al_nostru(pachet):
	"""True cand cea mai noua versiune a pachetului e intr-un feed HD Satelit (HdsModuleLipsa.provenienta)."""
	try:
		try:
			from Components import HdsModuleLipsa as M
		except ImportError:
			import HdsModuleLipsa as M
		versiune, _motiv = M.provenienta(pachet)
		return versiune is not None
	except Exception as e:
		_jurnal("provenienta %s: %r" % (pachet, e))
		return False


def _scurt(iesire):
	"""ultimele randuri ale lui opkg, fara adrese cu nume si parola"""
	randuri = [re.sub(r"(https?://)[^/@\s]*@", r"\1", r.strip()) for r in (iesire or "").splitlines() if r.strip()]
	return " / ".join(randuri[-2:])[:IESIRE_MAXIM]


def pune(rad, fel, sufix, opkg=None, al_nostru=None, ruleaza=None, pachet=None):
	"""Pe un fir separat: opkg update, pachetul nostru al modulului instalat (sau reinstalat), scriptul lui aflat. Intoarce
	{"ok", "motiv", "pachet", "sufix_nou", "eroare"}; motivele: gata, fara_opkg, lipsa_din_feed, strain, nu_s_a_instalat,
	fara_script. `opkg`, `al_nostru(pachet)` si `ruleaza(comanda, termen) -> (cod, iesire)` se dau la probe. Cu `pachet` (un
	modul din feed care nu e instalat, din dinFeed) se instaleaza exact acel pachet, fara potrivirea dupa numele modulului."""
	al_nostru = al_nostru or _al_nostru
	ruleaza = ruleaza or _ruleaza
	rez = {"ok": False, "motiv": "", "pachet": "", "sufix_nou": "", "eroare": ""}
	comanda = R._opkg(rad, opkg)
	if comanda is None:
		rez["motiv"] = "fara_opkg"
		return rez
	cod, iesire = ruleaza(comanda + ["update"], TERMEN_UPDATE_S)
	if cod != 0:
		_jurnal("opkg update: cod %s (%s)" % (cod, _scurt(iesire)))
	if pachet:
		pachet, reinstalare = (pachet if pachet in R._in_liste(rad) else None), False
	else:
		strain = proprietar(rad, DOSAR_SCRIPTURI + "/" + fel + "." + sufix)
		pachet, reinstalare = inlocuitor(fel, sufix, strain, R._in_liste(rad))
	if not pachet:
		rez["motiv"] = "lipsa_din_feed"
		return rez
	rez["pachet"] = pachet
	if not al_nostru(pachet):
		rez["motiv"] = "strain"
		return rez
	argv = comanda + ["install"] + (["--force-reinstall"] if reinstalare else []) + [pachet]
	cod, iesire = ruleaza(argv, TERMEN_INSTALARE_S)
	_jurnal("%s: cod %s" % (" ".join(argv[1:]), cod))
	if cod != 0:
		rez["motiv"] = "nu_s_a_instalat"
		rez["eroare"] = _scurt(iesire)
		return rez
	rez["sufix_nou"] = scriptulPachetului(rad, pachet, fel)
	if not rez["sufix_nou"]:
		rez["motiv"] = "fara_script"
		return rez
	rez["ok"], rez["motiv"] = True, "gata"
	return rez


def _ruleaza(comanda, termen):
	try:
		r = subprocess.run(comanda, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=termen)
		return r.returncode, r.stdout.decode("utf-8", "replace")[-8192:]
	except Exception as e:
		return -1, str(e)


def textRezultat(r, nume):
	"""Fraza de dupa instalare (inainte de alegere), cand nu s-a putut."""
	m = (r or {}).get("motiv")
	if m == "fara_opkg":
		return _("Pe receptor nu este opkg; modulul nu se poate pune.")
	if m == "lipsa_din_feed":
		return _("Feedul HD Satelit nu are modulul %s pentru acest receptor (sau receptorul nu are internet acum).") % nume
	if m == "strain":
		return _("%s are o versiune mai nouă în altă sursă; nu îl instalez singur.") % r.get("pachet", nume)
	if m == "nu_s_a_instalat":
		return _("%s nu s-a putut instala: %s") % (r.get("pachet", nume), r.get("eroare") or "-")
	if m == "fara_script":
		return _("%s s-a instalat, dar nu are script de pornire.") % r.get("pachet", nume)
	return ""


# ---------------------------------------------------------------- pe receptor: lucrarea si alegerea

def inLucru():
	return _stare["lucrare"] is not None


def stareWeb():
	"""Pentru pagina web: {"in_lucru", "fel", "sufix", "text", "ok", "cand"}."""
	return {"in_lucru": inLucru(), "fel": _stare["fel"], "sufix": _stare["sufix"], "text": _stare["text"],
		"ok": bool(_stare["ok"]), "cand": _stare["cand"]}


def asculta(f):
	if f not in _ascultatori:
		_ascultatori.append(f)


def lasa(f):
	if f in _ascultatori:
		_ascultatori.remove(f)


def _anunta(textul, ok, gata):
	_stare["text"], _stare["ok"], _stare["cand"] = textul, ok, int(time.time())
	if gata:
		_stare["lucrare"] = None
		_jurnal("gata (%s): %s" % ("bun" if ok else "nu", textul))
	for f in list(_ascultatori):
		try:
			f(textul, ok, gata)
		except Exception as e:
			_jurnal("ascultator: %r" % (e,))
	if gata and textul and not _ascultatori:
		# ecranul modulelor nu e deschis (lucrarea pornita din pagina web, sau ecranul inchis intre timp): mesajul pe televizor
		try:
			from Tools import Notifications
			from Screens.MessageBox import MessageBox
			Notifications.AddPopup(textul, MessageBox.TYPE_INFO if ok else MessageBox.TYPE_ERROR, 15, "HdsModulNepornit")
		except Exception as e:
			_jurnal("mesajul: %r" % (e,))


def porneste(fel, sufix, rad="/", lucrare=None, operatie=None, pachet=None):
	"""La cererea omului: pune pachetul nostru al modulului <fel>.<sufix> pe un fir, apoi il alege si il porneste. False cand
	merge deja o lucrare sau o comanda a modulelor. `lucrare` (HdsImportSurse.Lucrare) si `operatie`
	(HdsModuleAcces.Operatie) se dau la probe. Cu `pachet` (un rand din dinFeed): exact acel pachet, iar numele aratat e al
	modulului din numele pachetului."""
	try:
		from Components import HdsModuleAcces as H
	except ImportError:
		import HdsModuleAcces as H
	if inLucru() or H.in_curs() is not None:
		return False
	if lucrare is None:
		from Components.HdsImportSurse import Lucrare as lucrare
	operatie = operatie or H.Operatie
	nume = (R.rest_acces(pachet) or pachet) if pachet else numeModul(sufix)
	_stare.update({"fel": fel, "sufix": sufix, "faza": "instalare"})
	_anunta(_("Se pune %s din feedul HD Satelit...") % nume, False, False)

	def dupaAlegere(r):
		if r.get("ok"):
			_anunta(_("%s din feedul HD Satelit e pus și pornit.") % nume, True, True)
		else:
			try:
				from Screens.CamSetup import text_rezultat
				t = text_rezultat(r)
			except Exception:
				t = r.get("motiv") or ""
			_anunta(t, False, True)

	def gata(r, eroare):
		if eroare or not r:
			_anunta(_("%s nu s-a putut instala: %s") % (nume, eroare or "-"), False, True)
			return
		if not r.get("ok"):
			_anunta(textRezultat(r, nume), False, True)
			return
		_stare["faza"] = "alegere"
		_anunta(_("Se pornește %s...") % r["sufix_nou"], False, False)
		try:
			o = operatie("alege", fel=fel, sufix=r["sufix_nou"], la_final=dupaAlegere)
			o.porneste()
		except Exception as e:
			_anunta(_("%s nu a pornit.") % r["sufix_nou"] + " (%s)" % e, False, True)
	_stare["lucrare"] = True    # ocupat inainte de fir: o lucrare care termina pe loc il elibereaza ea insasi
	if pachet:
		obiect = lucrare(lambda: pune(rad, fel, sufix, pachet=pachet), gata)
	else:
		obiect = lucrare(lambda: pune(rad, fel, sufix), gata)
	if _stare["lucrare"] is True:
		_stare["lucrare"] = obiect   # tinut in viata pana la sfarsit (eTimer-ul lucrarii)
	return True


# ---------------------------------------------------------------- modulele din feedurile noastre care nu sunt instalate
# Ca omul sa nu caute modulul in Extensii, apoi sa vina inapoi in Acces conditionat ca sa-l aleaga: sub modulele instalate stau
# modulele din feedurile HD Satelit care nu sunt instalate, fiecare cu "Pune <modul> din feedul HD Satelit" (OK: instalat, ales,
# pornit, cu porneste(..., pachet=)). Pachetele se afla dupa forma numelui (enigma2-plugin-<categoria modulelor>-<modul>,
# HdsReinstalare.rest_acces; felul = categoria la singular, ca dosarul programelor /usr/<fel>s), numai cele a caror cea mai noua
# versiune, pe arhitecturile receptorului, e intr-un feed HD Satelit (alt feed cu o versiune mai noua: randul nu apare, iar pune()
# il refuza oricum). Listele opkg se citesc pe un fir, o data pe fiecare schimbare a lor (marimea si ora fiecarei liste), numai
# blocurile pachetelor de module; pe firul enigma2 ramane numai o privire in dosarul listelor si cate un stat pe rand. Cand lipsesc
# listele surselor noastre (receptorul abia scris) sau sunt mai vechi de VARSTA_LISTE_S, firul face intai opkg update, o data pe
# pornirea interfetei si numai cand opkg nu lucreaza. Fara opkg (probele de pe PC): nimic.
VARSTA_LISTE_S = 3 * 24 * 3600
_SFARSIT_NEMODUL = ("-dbg", "-dev", "-src", "-doc", "-staticdev", "-ptest")
_feed = {"semn": None, "lista": [], "in_lucru": False, "update_facut": False}


def _pachetDeModul(nume):
	"""(fel, modul) pentru enigma2-plugin-<categoria modulelor>-<modul>, sau (None, None)"""
	rest = R.rest_acces(nume)
	if not rest or rest.endswith(_SFARSIT_NEMODUL) or "-locale-" in rest:
		return None, None
	return nume.split("-")[2][:-1], rest


def strofeModule(text):
	"""Strofele pachetelor de module dintr-o lista opkg (Packages): numai blocurile lor se desfac."""
	try:
		from Components import HdsPachete as P
	except ImportError:
		import HdsPachete as P
	rez = []
	for bloc in text.split("\n\n"):
		bloc = bloc.strip("\n")
		if not bloc.startswith("Package:"):
			continue
		if _pachetDeModul(bloc.split("\n", 1)[0][8:].strip())[0] is None:
			continue
		rez += P.strofe_din_text(bloc)
	return rez


def moduleDinListe(surse, arhitecturi):
	"""[{"pachet", "fel", "nume", "versiune", "descriere"}] din `surse` = [(a_noastra, [strofe])], dupa nume: pachetele de module
	a caror cea mai noua versiune pe arhitecturile receptorului e intr-o sursa de-a noastra (la versiuni egale castiga a noastra,
	ca la HdsModuleLipsa.provenienta)."""
	try:
		from Components import HdsPachete as P
	except ImportError:
		import HdsPachete as P
	cele_mai_noi = {}
	for a_noastra, strofe in surse:
		for s in strofe:
			p = s.get("package", "")
			if _pachetDeModul(p)[0] is None or not P.nume_valid(p):
				continue
			if not P._arhitectura_buna(s.get("architecture", ""), arhitecturi):
				continue
			v = s.get("version", "")
			b = cele_mai_noi.get(p)
			if b is not None:
				c = P.compara_versiuni(v, b[0])
				if c < 0 or (c == 0 and (b[1] or not a_noastra)):
					continue
			cele_mai_noi[p] = (v, bool(a_noastra), s)
	rez = []
	for p, (v, a_noastra, s) in cele_mai_noi.items():
		if not a_noastra:
			continue
		fel, nume = _pachetDeModul(p)
		descriere = (s.get("description", "") or "").split("\n", 1)[0].strip()[:120]
		rez.append({"pachet": p, "fel": fel, "nume": nume, "versiune": v[:64], "descriere": descriere})
	rez.sort(key=lambda x: (x["fel"], x["nume"]))
	return rez


def _surseNoastre(conf, nume, adresa):
	try:
		from Components import HdsModuleLipsa as M
	except ImportError:
		import HdsModuleLipsa as M
	return M._sursaNoastra(conf, nume, adresa)


def _conf(rad):
	try:
		from Components import HdsPachete as P
	except ImportError:
		import HdsPachete as P
	return P.citeste_configurarea(rad)


def semnListe(rad, conf):
	"""marimea si ora fiecarei liste opkg: se schimba la orice opkg update"""
	d = R._c(rad, conf.lists_dir.lstrip("/"))
	try:
		return tuple(sorted((n, st.st_size, int(st.st_mtime)) for n, st in
			((n, os.stat(os.path.join(d, n))) for n in os.listdir(d))))
	except OSError:
		return ()


def listeVechi(rad, conf, a_noastra=None, acum=None):
	"""True cand o sursa de-a noastra nu are lista descarcata sau lista e mai veche de VARSTA_LISTE_S (sau nu e nicio sursa
	de-a noastra)"""
	a_noastra = a_noastra or _surseNoastre
	acum = time.time() if acum is None else acum
	noastre = [n for n, a in conf.surse if a_noastra(conf, n, a)]
	if not noastre:
		return True
	for n in noastre:
		try:
			if acum - os.path.getmtime(os.path.join(R._c(rad, conf.lists_dir.lstrip("/")), n)) > VARSTA_LISTE_S:
				return True
		except OSError:
			return True
	return False


def _opkgOcupat(rad):
	try:
		try:
			from Components.HdsActualizari import opkg_ocupat
		except ImportError:
			from HdsActualizari import opkg_ocupat
		return bool(opkg_ocupat(rad))
	except Exception as e:
		_jurnal("lacatul opkg: %r" % (e,))
		return False


def reface(rad, comanda, a_noastra=None, ruleaza=None, ocupat=None):
	"""Pe fir: opkg update cand trebuie (o data pe pornirea interfetei), apoi lista modulelor din feed, tinuta in _feed."""
	a_noastra = a_noastra or _surseNoastre
	ruleaza = ruleaza or _ruleaza
	ocupat = ocupat or _opkgOcupat
	try:
		conf = _conf(rad)
		if not _feed["update_facut"] and listeVechi(rad, conf, a_noastra) and not ocupat(rad):
			_feed["update_facut"] = True
			cod, iesire = ruleaza(comanda + ["update"], TERMEN_UPDATE_S)
			_jurnal("modulele din feed: opkg update, cod %s%s" % (cod, (" (%s)" % _scurt(iesire)) if cod else ""))
			conf = _conf(rad)
		semn = semnListe(rad, conf)
		surse = []
		d = R._c(rad, conf.lists_dir.lstrip("/"))
		for n, a in conf.surse:
			f = os.path.join(d, n)
			if not os.path.isfile(f):
				continue
			try:
				with open(f, "r", encoding="utf-8", errors="replace") as fh:
					text = fh.read()
			except (OSError, IOError):
				continue
			surse.append((a_noastra(conf, n, a), strofeModule(text)))
		_feed["lista"] = moduleDinListe(surse, conf.arhitecturi)
		_feed["semn"] = semn
	except Exception as e:
		_jurnal("modulele din feed: %r" % (e,))
	finally:
		_feed["in_lucru"] = False


def _peFir(functie):
	import threading
	fir = threading.Thread(target=functie, name="hds-module-feed")
	fir.daemon = True
	fir.start()


def dinFeed(rad="/", opkg=None, a_noastra=None, pe_fir=None):
	"""Pentru ecranul modulelor si pagina web, pe firul enigma2: [{"pachet", "fel", "nume", "versiune", "descriere"}], modulele
	din feedurile noastre care nu sunt instalate, din ultima citire a listelor (cele instalate intre timp nu mai apar). Cand
	listele s-au schimbat de la ultima citire, porneste citirea din nou pe un fir; randurile apar la urmatoarea reimprospatare.
	`opkg`, `a_noastra(conf, nume, adresa)` si `pe_fir(functie)` se dau la probe."""
	comanda = R._opkg(rad, opkg)
	if comanda is None:
		return []
	try:
		conf = _conf(rad)
		semn = semnListe(rad, conf)
		if semn != _feed["semn"] and not _feed["in_lucru"]:
			_feed["in_lucru"] = True
			try:
				(pe_fir or _peFir)(lambda: reface(rad, comanda, a_noastra))
			except Exception as e:
				_feed["in_lucru"] = False
				_jurnal("modulele din feed: firul %r" % (e,))
		info = R._c(rad, conf.info_dir.lstrip("/"))
		return [dict(x) for x in _feed["lista"] if not os.path.exists(os.path.join(info, x["pachet"] + ".control"))]
	except Exception as e:
		_jurnal("modulele din feed: %r" % (e,))
		return []


def textOfertaFeed(x):
	"""Randul unui modul din feed (dinFeed) in lista: Pune <modul> din feedul HD Satelit"""
	return _("Pune %s din feedul HD Satelit") % x["nume"]


def randOkFeed(x):
	return _("Apasă OK: %s.") % textOfertaFeed(x)
