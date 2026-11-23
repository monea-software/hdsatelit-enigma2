# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# meniu_web.py: tot meniul receptorului (tasta MENU) in interfata web (HdsWebControl).
#
# Fiecare intrare de meniu are pereche in interfata web, intr-una din trei forme: pagina proprie, motorul generic de
# meniuri, „deschide pe TV”. Pagina /meniu e motorul generic: tot data/menu.xml, cu aceleasi
# reguli ca televizorul (Screens/Menu.py: level= fata de nivelul utilizatorului, requires= din SystemInfo, ordinea dupa
# weight, semnul „(în lucru)” / „(netestat)”), iar la fiecare intrare:
# - pagina ei proprie, cand are una (atributul web= din menu.xml);
# - pagina generica de setari /setari?id=..., la intrarile <setup id="..."/> (setari_web.py);
# - „Deschide pe televizor”: ecranul adevarat se deschide pe televizor, deci valorile si regulile sunt chiar ale lui.
# Nu se deschid pe televizor din aceasta pagina: intrarile <code> (nu se ruleaza cod din menu.xml la o cerere din retea)
# si oprirea sau repornirea receptorului (Standby, TryQuitMainloop): un clic in browser nu opreste receptorul sub cel
# care se uita. Fiecare dintre ele are pagina ei (web=): oprirea, repornirea si standby-ul
# sunt in /alimentare, resetarea in /resetare-fabrica, proba DiSEqC in /proba-diseqc, fiecare actiune cu confirmare in
# doi pasi (meniu_comun_web.py), ca orice
# ecran sa aiba pereche in web; butonul de aici ramane fara ele, deci nimic nu se opreste fara confirmare.
# Extensiile puse de om care se agata de un meniu prin cod (WHERE_MENU) nu sunt in menu.xml; din 0.7.5 (MLW) apar si
# aici, la locul lor de pe televizor, cu aceleasi chei de ordine si ascundere (vezi _cuExtensii mai jos), iar
# "Deschide pe televizor" le porneste ca OK in meniu. Ale imaginii au intrarea lor in menu.xml din 0.2.6 (de exemplu
# importul de canale, Media, setarile skinului).
#
# Motorul de meniu e cel din scanare_web.py (acelasi fisier citit, aceleasi reguli de vizibilitate); acolo se deschid
# pe televizor numai intrarile din sectiunile Scanare si Antena, aici oricare dintre cele de mai sus.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/meniu                        arborele meniului, cum il vede televizorul acum
#   POST /api/meniu-televizor?id=<entryID> deschide intrarea pe televizor (o extensie: id=ext.<cheie>&meniu=<cheie>)
#   POST /api/meniu-ordine?meniu=&id=&fel= ordinea si ascunderea intrarilor (Components/HdsMeniuOrdine, ca MENU pe
#                                          televizor): fel = sus, jos, inceput, sfarsit, ascunde, arata, fabrica (un
#                                          meniu), fabrica-tot
#   GET  /meniu                            pagina; /meniuri e aceeasi pagina, deschisa pe fila Aranjeaza
#
# Fiecare intrare are in pagina ancora i-<entryID>: meniul de sus al paginilor (cadru_web.py) duce acolo la intrarile care
# se deschid numai pe televizor; grupa ei se deschide si randul e ales.

# ecranele care opresc sau repornesc receptorul (Screens/Standby.py): nu se deschid din web
NEDESCHISE = frozenset((("Standby", "Standby"), ("Standby", "TryQuitMainloop")))
MAX_ADANCIME = 6


def _sw():
	from . import scanare_web
	return scanare_web


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsWebControl] meniu: %s" % text)


def _descriere(nod, limba=None):
	"""0.7.7 (DRG, darog69 forum 789 #2379): descrierea scurta a intrarii (atributul description din menu.xml), tradusa ca
	pe televizor (Screens/Menu.textDescriere): "" fara traducere cand limba nu e romana, ca sa nu apara fraze in romana."""
	msgid = nod.get("description") or ""
	if not msgid:
		return ""
	tradus = _t(msgid)
	if tradus and tradus != msgid:
		return tradus
	if limba is None:
		try:
			from Components.Language import language
			limba = language.getLanguage() or ""
		except Exception:
			limba = "ro"
	return msgid if str(limba).lower().startswith("ro") else ""


def _seDeschide(tinta):
	"""(se deschide pe televizor?, motivul daca nu)."""
	W = _sw()
	if tinta is None:
		return False, "gol"
	if tinta["fel"] == "setup":
		return bool(tinta.get("id")), "" if tinta.get("id") else "gol"
	if tinta["fel"] == "cod":
		return False, "cod"
	if (tinta["modul"], tinta["ecran"]) in NEDESCHISE:
		return False, "oprire"
	if not W._seDeschidePeTelevizor(tinta):
		return False, "cod"
	return True, ""


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


_MOTIVE = {
	"cod": N_("Se deschide numai din telecomandă."),
	"oprire": N_("Oprirea și repornirea se dau numai din telecomandă."),
	"gol": "",
}


# ---------------------------------------------------------------- legatura spre setarile web ale unui plugin
# FWC3/FWC4: o intrare care deschide pe televizor ecranul Setup al unui plugin (Setup(..., plugin="Categorie/Nume"))
# primeste si legatura /setari?id=Categorie/Nume/cheie, numai cand cheia exista in registrul setarilor pluginurilor
# (setari_web._ecranePlugin, acelasi pe care il foloseste ruta /setari). FIRUL: tot ce se face la randare ruleaza pe
# firul enigma2 si citeste NUMAI memoria: callbackul se recunoaste din obiectele lui deja incarcate (__code__.co_names,
# __code__.co_consts, __globals__, __mro__), fara codul sursa si fara disc; registrul (listdir si setup.xml-urile
# pluginurilor) il citeste un fir de fundal intr-o memorie schimbata dintr-o bucata. Cat memoria nu e gata, intrarea
# arata ca inainte (numai deschiderea pe televizor); firul principal nu asteapta nimic.

_REGISTRU = {"chei": None, "cand": 0.0, "lucreaza": False, "fir": None}
REGISTRU_VIATA = 120.0     # secunde dupa care registrul se reciteste in fundal (plugin instalat sau scos intre timp)


def _citesteRegistru(ecrane):
	"""Pe firul de fundal: cheile registrului, puse in memorie dintr-o bucata. Nu ridica nimic."""
	import time
	try:
		chei = frozenset(ecrane())
	except Exception as eroare:
		_jurnal("registrul setarilor pluginurilor: %s" % eroare)
		chei = _REGISTRU["chei"] if _REGISTRU["chei"] is not None else frozenset()
	_REGISTRU["chei"] = chei
	_REGISTRU["cand"] = time.monotonic()
	_REGISTRU["lucreaza"] = False


def _pornesteRegistru():
	"""Porneste firul de fundal (cel mult unul o data); firul principal nu il asteapta."""
	import threading
	try:
		from .setari_web import _ecranePlugin
	except Exception as eroare:
		_jurnal("registrul setarilor pluginurilor: %s" % eroare)
		return
	_REGISTRU["lucreaza"] = True
	try:
		fir = threading.Thread(target=_citesteRegistru, args=(_ecranePlugin,), name="HdsWebMeniuSetari")
		fir.daemon = True
		_REGISTRU["fir"] = fir
		fir.start()
	except Exception as eroare:
		_REGISTRU["lucreaza"] = False
		_jurnal("firul registrului setarilor: %s" % eroare)


def _cheiRegistru(setari):
	"""Cheile registrului din memorie (o data pe arbore), sau None cat nu sunt citite; cere recitirea in fundal cand
	lipsesc sau sunt vechi."""
	if "chei" not in setari:
		import time
		chei = _REGISTRU["chei"]
		if (chei is None or time.monotonic() - _REGISTRU["cand"] > REGISTRU_VIATA) and not _REGISTRU["lucreaza"]:
			_pornesteRegistru()
		setari["chei"] = chei
	return setari["chei"]


def _setupApel(apel, pozitie):
	"""Citeste numai argumentele literale ale Setup; nu executa expresii."""
	import ast
	try:
		if any(k.arg is None for k in apel.keywords):
			return ""
		valori = {k.arg: ast.literal_eval(k.value) for k in apel.keywords if k.arg in ("setup", "plugin")}
		cheie = valori.get("setup") or ast.literal_eval(apel.args[pozitie])
		plugin = valori.get("plugin")
		if isinstance(cheie, str) and isinstance(plugin, str):
			return plugin + "/" + cheie
	except (ValueError, TypeError, IndexError, SyntaxError):
		pass
	return ""


def _setupNod(nod):
	"""Recunoaste un ecran Setup(plugin=...) cu argumente literale din meniul XML (din memorie)."""
	import ast
	for x in nod:
		if x.tag == "screen" and x.get("module") == "Setup" and x.get("screen", "Setup") == "Setup":
			try:
				return _setupApel(ast.parse("f(" + (x.text or "") + ")", mode="eval").body, 0)
			except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
				return ""
	return ""


def _esteSetup(clasa):
	return isinstance(clasa, type) and clasa.__module__ == "Screens.Setup" and clasa.__name__ == "Setup"


def _texte(valori):
	return {x for x in valori if isinstance(x, str)}


def _texteConstructor(clasa):
	"""Textele constante ale __init__ al unei clase derivate din Setup care cheama constructorul parintelui; None altfel."""
	import types
	init = getattr(clasa, "__init__", None)
	if not isinstance(init, types.FunctionType) or "__init__" not in init.__code__.co_names:
		return None
	return _texte(init.__code__.co_consts)


def _texteExtensie(functie, adancime=0):
	"""Textele constante ale unui callback care deschide Setup (direct, prin import local sau printr-o clasa derivata),
	sau None. Numai obiecte deja in memorie: nu se citeste sursa, nu se importa si nu se executa nimic. Functiile
	imbricate (co_consts le tine ca obiecte cod) nu se cerceteaza."""
	import functools
	import types
	if adancime > 2:
		return None
	if isinstance(functie, functools.partial):
		texte = _texteExtensie(functie.func, adancime + 1)
		if texte is None:
			return None
		return texte | _texte(functie.args) | _texte((functie.keywords or {}).values())
	if type(functie).__module__ == "Tools.BoundFunction" and type(functie).__name__ == "boundFunction":
		texte = _texteExtensie(getattr(functie, "fnc", None), adancime + 1)
		if texte is None:
			return None
		return texte | _texte(getattr(functie, "args", ()) or ()) | _texte((getattr(functie, "kwargs", None) or {}).values())
	if isinstance(functie, types.MethodType):
		functie = functie.__func__
	if not isinstance(functie, types.FunctionType):
		return None
	cod = functie.__code__
	nume = cod.co_names
	if "open" not in nume and "openWithCallback" not in nume:
		return None
	globale = functie.__globals__
	if "Screens.Setup" in nume or any(n not in cod.co_varnames and _esteSetup(globale.get(n)) for n in nume):
		return _texte(cod.co_consts)
	texte = None
	for n in nume:
		clasa = globale.get(n)
		if n in cod.co_varnames or not isinstance(clasa, type) or _esteSetup(clasa):
			continue
		try:
			derivata = any(_esteSetup(c) for c in clasa.__mro__[1:])
		except Exception:
			derivata = False
		if derivata:
			t = _texteConstructor(clasa)
			if t is not None:
				texte = (texte or set()) | t
	return texte


def _alegeCheie(texte, chei):
	"""Cheia registrului "Categorie/Nume/cheie" ale carei doua parti sunt amandoua texte ale callbackului; "" cand nu
	e niciuna sau sunt mai multe (ambiguu: ramane numai deschiderea pe televizor)."""
	if not texte or not chei:
		return ""
	gasite = []
	for c in chei:
		plugin, _sep, cheie = c.rpartition("/")
		if plugin in texte and cheie in texte:
			gasite.append(c)
			if len(gasite) > 1:
				return ""
	return gasite[0] if gasite else ""


def _setupXml(nod, setari):
	"""setup_web al unei intrari din menu.xml cu Setup(plugin=...): cheia, daca e in registrul din memorie."""
	cheie = _setupNod(nod)
	if not cheie:
		return ""
	chei = _cheiRegistru(setari)
	return cheie if chei and cheie in chei else ""


def _setupExtensie(functie, setari):
	"""setup_web al unei extensii WHERE_MENU: cheia aleasa din textele callbackului si registrul din memorie."""
	try:
		texte = _texteExtensie(functie)
	except Exception:
		return ""
	if not texte:
		return ""
	return _alegeCheie(texte, _cheiRegistru(setari))


def _intrare(nod, setari=None):
	W = _sw()
	tinta = W._tinta(nod)
	merge, motiv = _seDeschide(tinta)
	motiv = _MOTIVE.get(motiv, "")
	return {
		"tip": "intrare",
		"id": nod.get("entryID") or "",
		"text": W._cuSemn(nod),
		"descriere": _descriere(nod),
		"web": nod.get("web") or "",
		"pictograma": nod.get("pictograma") or "",
		"ordine_id": _cheieIntrare(nod),
		"setup": tinta["id"] if tinta is not None and tinta["fel"] == "setup" else "",
		"setup_web": _setupXml(nod, setari if setari is not None else {}),
		"televizor": merge,
		# un text gol nu trece prin _(): gettext ar da antetul fisierului .po; o intrare cu pagina web nu are motiv (pagina
		# ei e calea din browser)
		"motiv": _t(motiv) if motiv and not merge and not nod.get("web") else "",
	}


def _grup(nod, nivel, adancime, setari=None):
	W = _sw()
	if setari is None:
		setari = {}
	copii = []
	cheie = _cheieMeniu(nod)
	if adancime < MAX_ADANCIME:
		for x in W._copiiVizibili(nod, nivel):
			if x.tag == "item":
				copii.append((W._greutate(x), _intrare(x, setari)))
			elif x.tag == "menu":
				copii.append((W._greutate(x), _grup(x, nivel, adancime + 1, setari)))
		copii = _cuExtensii(nod, cheie, copii, setari)
	copii = [c for _g, c in copii]
	return {"tip": "grup", "id": nod.get("entryID") or nod.get("key") or "", "text": W._cuSemn(nod),
		"descriere": _descriere(nod), "web": nod.get("web") or "", "pictograma": nod.get("pictograma") or "", "cheie": cheie,
		"ordine_id": _cheieIntrare(nod), "copii": _ordineaOmului(cheie, copii)}


# ---------------------------------------------------------------- extensiile agatate de meniu (WHERE_MENU)
# MLW (0.7.5): extensiile puse de om care se agata de un meniu prin cod (PluginDescriptor.WHERE_MENU) apar si aici, la
# locul lor, ca pe televizor (Screens/Menu.py, Menu.__init__): aceleasi intrari (Components/HdsPluginuriImagine,
# meniuriUtilizator, dupa <id val> al meniului), intrarea din menu.xml cu acelasi id inlocuita de extensie, greutatea
# extensiei (50 fara ea) si aceeasi sortare stabila dupa greutate, apoi ordinea omului cu aceleasi chei
# (HdsMeniuOrdine.cheieIntrare(id-ul extensiei, numele ei)). Mutarea si ascunderea de aici se vad deci si pe televizor,
# iar "Deschide pe televizor" cheama functia extensiei, ca OK pe televizor. O extensie care cade nu strica pagina.

ID_EXTENSIE = "ext."
_EXTENSII_SCRISE = set()


def _idMeniu(nod):
	"""<id val> al meniului (cu el cer extensiile intrarile lor, ca pe televizor), sau None."""
	i = nod.find("id") if hasattr(nod, "find") else None
	return (i.get("val") or None) if i is not None else None


def _intrariExtensii(nod):
	"""[(nume, functie, id, greutate)] date de extensiile omului pentru meniul `nod`; [] fara <id> sau la o eroare."""
	id_meniu = _idMeniu(nod)
	if not id_meniu:
		return []
	try:
		from Components.PluginComponent import plugins
		from Components.HdsPluginuriImagine import meniuriUtilizator
		return [x for x in (meniuriUtilizator(plugins, id_meniu) or []) if len(x) > 1]
	except Exception as eroare:
		# o singura data pe meniu si fel de eroare: arborele se face la multe pagini (bara de sus, setarile)
		cheie = (id_meniu, type(eroare).__name__)
		if cheie not in _EXTENSII_SCRISE:
			_EXTENSII_SCRISE.add(cheie)
			_jurnal("extensiile meniului %s: %s" % (id_meniu, eroare))
		return []


def _cheieExtensie(x):
	"""Cheia de ordine a unei extensii, aceeasi ca pe televizor (Menu.py: intrareMeniu(nume, ..., id) -> cheieTuplu)."""
	O = _ordine()
	id_ = x[2] if len(x) > 2 else None
	nume = x[0] if x[0] is not None else ""
	if O is None:
		return str(id_ or nume)
	return O.cheieIntrare(id_, nume)


def _idAncora(cheie):
	"""Id-ul intrarii unei extensii in pagina (ancora i-<id>, cererea de deschidere): numai litere, cifre, _ . -"""
	import re
	return (ID_EXTENSIE + re.sub(r"[^A-Za-z0-9_.-]", "_", cheie))[:64]


def _greutateExtensie(x):
	try:
		return int((x[3] if len(x) > 3 else None) or 50)
	except (TypeError, ValueError):
		return 50


def _cuExtensii(nod, cheie, copii, setari=None):
	"""copii = [(greutate, intrare)] din menu.xml; intoarce lista cu extensiile meniului puse ca pe televizor."""
	if setari is None:
		setari = {}
	for x in _intrariExtensii(nod):
		id_ext = x[2] if len(x) > 2 else None
		# ca pe televizor: o extensie cu id-ul unei intrari de-a noastre ii ia locul
		for i, (_g, c) in enumerate(copii):
			if id_ext and c.get("id") == id_ext:
				del copii[i]
				break
		k = _cheieExtensie(x)
		copii.append((_greutateExtensie(x), {
			"tip": "intrare", "id": _idAncora(k), "text": str(x[0] or ""), "web": "", "pictograma": "extensie",
			"ordine_id": k, "setup": "", "setup_web": _setupExtensie(x[1], setari),
			"televizor": True, "motiv": "", "extensie": True}))
	copii.sort(key=lambda t: t[0])
	return copii


def _nodMeniuVizibil(nod, cheie, nivel, adancime=0):
	"""Nodul <menu> vizibil acum cu cheia de ordine `cheie` (HdsMeniuOrdine.cheieMeniu), sau None."""
	if _cheieMeniu(nod) == cheie:
		return nod
	if adancime >= MAX_ADANCIME:
		return None
	W = _sw()
	for x in W._copiiVizibili(nod, nivel):
		if x.tag == "menu":
			gasit = _nodMeniuVizibil(x, cheie, nivel, adancime + 1)
			if gasit is not None:
				return gasit
	return None


def deschideExtensie(meniu, id_intrare, sesiune=None):
	"""POST /api/meniu-televizor?meniu=<cheie>&id=ext.<cheie>: extensia din meniul dat, gasita din nou prin extensiile
	instalate (nimic din cerere nu se ruleaza), pornita pe televizor ca OK in meniu: functia ei cu sesiunea."""
	W = _sw()
	radacina = W._radacinaMeniu()
	principal = radacina.find("menu") if radacina is not None else None
	nod = _nodMeniuVizibil(principal, meniu, W._nivelUtilizator()) if principal is not None and meniu else None
	if nod is None:
		return {"result": False, "message": _t("Meniul nu e pe receptor.")}
	gasita = None
	for x in _intrariExtensii(nod):
		if _idAncora(_cheieExtensie(x)) == id_intrare:
			gasita = x
			break
	if gasita is None or not callable(gasita[1]):
		return {"result": False, "message": _t("Intrarea nu e în meniu.")}
	if sesiune is None:
		sesiune = W._sesiune()
	refuz = W._ocupat(sesiune)
	if refuz:
		return {"result": False, "message": refuz}
	try:
		gasita[1](sesiune)
	except Exception as eroare:
		_jurnal("extensia %s pe televizor: %s" % (id_intrare, eroare))
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor (%s).") % eroare}
	return {"result": True, "message": _t("S-a deschis pe televizor: %s.") % str(gasita[0] or "")}


# ---------------------------------------------------------------- ordinea si ascunderea (MENU pe televizor)
# Aceeasi ordine ca pe televizor (Components/HdsMeniuOrdine): copiii fiecarui grup in ordinea omului, iar cei ascunsi
# pe televizor raman in arbore cu "ascuns": true (paginile lor de setari si drumurile spre ele raman), pagina ii arata
# cu semnul lor. Fara modul (probele vechi), ordinea din fabrica.

def _ordine():
	try:
		from Components import HdsMeniuOrdine
		return HdsMeniuOrdine
	except ImportError:
		return None


def _cheieMeniu(nod):
	O = _ordine()
	return O.cheieMeniu(nod) if O is not None else (nod.get("key") or "")


def _cheieIntrare(nod):
	"""Cheia intrarii ca pe televizor: entryID, sau "t:" + numele tradus fara semne (Menu.addItem)."""
	O = _ordine()
	if O is None:
		return nod.get("entryID") or ""
	return O.cheieIntrare(nod.get("entryID"), _t(nod.get("text") or "??"))


def _ordineaOmului(cheie, copii):
	O = _ordine()
	if O is None:
		return copii
	try:
		chei = [c.get("ordine_id") or "" for c in copii]
		ordinea = O.ordoneaza(chei, O.ordine(cheie))
		ascunse = O.ascunse(cheie)
	except Exception as eroare:
		_jurnal("ordinea omului in %s: %s" % (cheie, eroare))
		return copii
	rez = []
	for i in ordinea:
		c = copii[i]
		c["ascuns"] = bool(chei[i]) and chei[i] in ascunse
		rez.append(c)
	return rez


_PASI = {"sus": -1, "jos": 1, "inceput": -1000, "sfarsit": 1000}


def _grupDupaCheie(g, cheie):
	if g.get("cheie") == cheie:
		return g
	for c in g.get("copii", []):
		if c.get("tip") == "grup":
			gasit = _grupDupaCheie(c, cheie)
			if gasit is not None:
				return gasit
	return None


def schimbaOrdinea(arg):
	"""POST /api/meniu-ordine: {"result", "message", "meniu": arborele nou}. Meniul si intrarea trebuie sa fie in
	arborele de acum (nimic scris pentru chei necunoscute)."""
	O = _ordine()
	if O is None or O.setari() is None:
		return {"result": False, "message": _t("Ordinea meniului nu se poate schimba pe acest receptor.")}
	fel = arg.get("fel", "")
	if fel == "fabrica-tot":
		O.fabrica()
		return dict(arbore(), message=_t("Toate meniurile au ordinea din fabrică."))
	a = arbore()
	if not a.get("result"):
		return a
	g = _grupDupaCheie(a["meniu"], arg.get("meniu", ""))
	if g is None:
		return {"result": False, "message": _t("Meniul nu e pe receptor.")}
	cheie = g["cheie"]
	if fel == "fabrica":
		O.fabrica(cheie)
		return dict(arbore(), message=_t("Meniul are ordinea din fabrică."))
	chei = [c.get("ordine_id") or "" for c in g["copii"]]
	id_ = arg.get("id", "")
	if not id_ or id_ not in chei:
		return {"result": False, "message": _t("Intrarea nu e în meniu.")}
	if fel in _PASI:
		gata = O.muta(cheie, chei, id_, _PASI[fel]) is not None
		mesaj = _t("Ordinea s-a schimbat și pe televizor.")
	elif fel in ("ascunde", "arata"):
		gata = O.ascunde(cheie, id_, fel == "ascunde")
		mesaj = _t("Intrarea e ascunsă pe televizor.") if fel == "ascunde" else _t("Intrarea se vede din nou pe televizor.")
	else:
		return {"result": False, "message": _t("Comandă necunoscută.")}
	if not gata:
		return dict(arbore(), message=_t("Intrarea e deja la capăt."))
	return dict(arbore(), message=mesaj)


def arbore():
	"""GET /api/meniu: {"result", "meniu": grupul principal}."""
	W = _sw()
	radacina = W._radacinaMeniu()
	if radacina is None:
		return {"result": False, "message": _t("Meniul receptorului nu se poate citi.")}
	principal = radacina.find("menu")
	if principal is None:
		return {"result": False, "message": _t("Meniul receptorului nu se poate citi.")}
	g = _grup(principal, W._nivelUtilizator(), 0)
	g["text"] = _t("Meniu principal")
	return {"result": True, "meniu": g}


def sectiune(id_meniu):
	"""Grupa vizibila folosita si de navigarea din paginile categoriei."""
	def cauta(g):
		if g.get("id") == id_meniu:
			return g
		for c in g.get("copii", []):
			if c.get("tip") == "grup":
				gasit = cauta(c)
				if gasit is not None:
					return gasit
		return None

	a = arbore()
	return cauta(a["meniu"]) if a.get("result") else None


def _cauta(nod, id_intrare, nivel, parinti, adancime=0):
	"""(nodul vizibil cu entryID-ul dat, lista parintilor lui) sau (None, None)."""
	W = _sw()
	if adancime > MAX_ADANCIME:
		return None, None
	for x in W._copiiVizibili(nod, nivel):
		if x.tag == "item" and x.get("entryID") == id_intrare:
			return x, parinti + [nod]
		if x.tag == "menu":
			gasit, lant = _cauta(x, id_intrare, nivel, parinti + [nod], adancime + 1)
			if gasit is not None:
				return gasit, lant
	return None, None


# nivelul la care se cauta drumul spre o intrare: peste orice level= din menu.xml, ca drumul sa se poata arata si cand
# intrarea e ascunsa la nivelul ales acum pe receptor (requires= ramane: ce nu exista pe receptor nu are drum)
_NIVEL_ORICARE = 99


def _cautaDrum(nod, id_intrare, parinti, adancime=0):
	"""Lista nodurilor de la primul nivel pana la intrarea (<item>) sau grupul (<menu>) cu entryID-ul sau key-ul dat,
	sau None."""
	W = _sw()
	if adancime > MAX_ADANCIME:
		return None
	for x in W._copiiVizibili(nod, _NIVEL_ORICARE):
		if x.get("entryID") == id_intrare or (x.tag == "menu" and x.get("key") == id_intrare):
			return parinti + [x]
		if x.tag == "menu":
			gasit = _cautaDrum(x, id_intrare, parinti + [x], adancime + 1)
			if gasit is not None:
				return gasit
	return None


def drum(id_intrare):
	"""Numele de pe televizor, traduse ca acolo si fara semnele de stare, de la primul nivel al meniului pana la
	intrare: ["Setări", "Sunet și subtitrări", "Limba sunetului și a subtitrărilor"]; [] daca nu e in meniu."""
	W = _sw()
	radacina = W._radacinaMeniu()
	principal = radacina.find("menu") if radacina is not None else None
	if principal is None or not id_intrare:
		return []
	noduri = _cautaDrum(principal, id_intrare, []) or []
	return [_t(x.get("text") or "") for x in noduri]


def drumText(id_intrare):
	"""„Meniu, „Setări”, „Sunet și subtitrări”, „Limba sunetului și a subtitrărilor”” (text simplu, pentru mesaje);
	numai „Meniu” daca intrarea nu e in meniu."""
	# cuvantul Meniu si ghilimelele sunt ale limbii meniurilor: drumul intra in pagini dupa traducerea lor
	# (__DRUM_MENIU__), deci _traducePagina nu il vede
	ghilimele = _t("„%s”")
	if ghilimele.count("%s") != 1:
		ghilimele = u"\u201e%s\u201d"
	return ", ".join([_t("Meniu")] + [ghilimele % n for n in drum(id_intrare)])


def _hrefNod(nod):
	"""Destinatia unei trepte a drumului, calculata din nodul meniului (memorie), aceeasi ca in meniul de sus al
	paginilor: grupa, pagina web, setarile imaginii sau randul intrarii in /meniu (setarile web ale unui plugin raman
	butonul in plus din /meniu)."""
	if nod.tag == "menu":
		return hrefIntrare({"tip": "grup", "id": nod.get("entryID") or nod.get("key") or "", "web": nod.get("web") or ""})
	tinta = _sw()._tinta(nod)
	merge, _motiv = _seDeschide(tinta)
	return hrefIntrare({"tip": "intrare", "id": nod.get("entryID") or "", "web": nod.get("web") or "",
		"setup": tinta["id"] if tinta is not None and tinta["fel"] == "setup" else "",
		"televizor": merge})


def drumHtml(id_intrare):
	"""drumText scapat pentru HTML (numele au "&"), cu fiecare treapta clicabila: acelasi text ca drumText, iar numele
	fiecarei trepte e legatura spre grupa, pagina sau setarile ei (aceleasi destinatii ca meniul de sus al paginilor).
	Ca drumText, citeste numai arborele meniului din memorie (o verificare a fisierului, ca pe HEAD)."""
	import html
	W = _sw()
	radacina = W._radacinaMeniu()
	principal = radacina.find("menu") if radacina is not None else None
	noduri = (_cautaDrum(principal, id_intrare, []) or []) if principal is not None and id_intrare else []
	ghilimele = _t("„%s”")
	if ghilimele.count("%s") != 1:
		ghilimele = u"„%s”"
	inainte, _sep, dupa = ghilimele.partition("%s")

	def legatura(text, href):
		text = html.escape(text, quote=False)
		return '<a href="%s">%s</a>' % (html.escape(href, quote=True), text) if href else text

	rez = [legatura(_t("Meniu"), "/meniu")]
	for nod in noduri:
		try:
			href = _hrefNod(nod)
		except Exception as eroare:
			_jurnal("drumul spre %s: %s" % (id_intrare, eroare))
			href = ""
		rez.append(html.escape(inainte, quote=False) + legatura(_t(nod.get("text") or ""), href) + html.escape(dupa, quote=False))
	return ", ".join(rez)


def hrefIntrare(c):
	"""Destinatia de citire comuna drumului, grupelor si intrarilor din meniu."""
	from urllib.parse import quote
	if c.get("web"):
		return c["web"]
	setup = c.get("setup_web") or c.get("setup")
	if setup:
		return "/setari?id=" + quote(setup, safe="")
	id_ = c.get("id") or ""
	if id_ and (c.get("tip") == "grup" or c.get("televizor")):
		return "/meniu#" + ("g-" if c.get("tip") == "grup" else "i-") + quote(id_, safe="")
	return ""


def cheiSetup():
	"""[(cheia din setup.xml, textul intrarii)] pentru intrarile <setup> vizibile acum (ce poate deschide si
	televizorul), fara dubluri, in ordinea din meniu. Pentru setari_web.py."""
	rez = []
	vazute = set()

	def _umbla(g):
		for c in g.get("copii", []):
			if c["tip"] == "grup":
				_umbla(c)
			elif c.get("setup") and c["setup"] not in vazute:
				vazute.add(c["setup"])
				rez.append((c["setup"], c["text"]))
	a = arbore()
	if a.get("result"):
		_umbla(a["meniu"])
	return rez


def deschide(id_intrare, sesiune=None):
	"""POST /api/meniu-televizor?id=: deschide pe televizor o intrare vizibila, dupa entryID. Modulul, ecranul si
	argumentele vin din menu.xml, nu din cerere."""
	W = _sw()
	radacina = W._radacinaMeniu()
	principal = radacina.find("menu") if radacina is not None else None
	if principal is None or not id_intrare:
		return {"result": False, "message": _t("Intrarea nu e în meniu.")}
	nod, parinti = _cauta(principal, id_intrare, W._nivelUtilizator(), [])
	if nod is None:
		return {"result": False, "message": _t("Intrarea „%s” nu e în meniu.") % id_intrare[:40]}
	tinta = W._tinta(nod)
	merge, motiv = _seDeschide(tinta)
	if not merge:
		return {"result": False, "message": _t(_MOTIVE.get(motiv) or "Se deschide numai din telecomandă.")}
	if sesiune is None:
		sesiune = W._sesiune()
	refuz = W._ocupat(sesiune)
	if refuz:
		return {"result": False, "message": refuz}
	# ca meniul de pe televizor: un nod parinte cu flushConfigOnClose salveaza setarile la inchidere
	salveaza = any(p.get("flushConfigOnClose") for p in parinti)

	def _laIesire(*_rezultat):
		if salveaza:
			try:
				from Components.config import configfile
				configfile.save()
			except Exception as eroare:
				_jurnal("salvarea setarilor dupa %s: %s" % (id_intrare, eroare))

	try:
		if tinta["fel"] == "setup":
			from Screens.Setup import Setup
			dlg = sesiune.openWithCallback(_laIesire, Setup, tinta["id"])
		else:
			import importlib
			modul = importlib.import_module("Screens." + tinta["modul"])
			ecran = getattr(modul, tinta["ecran"])
			dlg = sesiune.openWithCallback(_laIesire, ecran, *tinta["argumente"])
	except Exception as eroare:
		_jurnal("deschiderea %s pe televizor: %s" % (id_intrare, eroare))
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor (%s).") % eroare}
	if dlg is None:
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor. Detalii în jurnalul receptorului.")}
	return {"result": True, "message": _t("S-a deschis pe televizor: %s.") % _t(nod.get("text") or "")}


def argumente(request):
	rez = {}
	for cheie, valori in (getattr(request, "args", None) or {}).items():
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		# meniu: cheia meniului unei extensii (MLW), langa id-ul ei (ext.<cheie>)
		if cheie not in ("id", "meniu"):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v).strip()
	return rez


def argumenteOrdine(request):
	"""meniu, id, fel din cerere."""
	rez = {}
	for cheie, valori in (getattr(request, "args", None) or {}).items():
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ("meniu", "id", "fel"):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v).strip()
	return rez


def rute(baza, resource):
	class ArboreResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, arbore())
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class TelevizorResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				arg = argumente(request)
				id_ = arg.get("id", "")
				if id_.startswith(ID_EXTENSIE):
					return self._raspunde(request, deschideExtensie(arg.get("meniu", ""), id_))
				return self._raspunde(request, deschide(id_))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			request.setHeader(b"allow", b"POST")
			return self._eroare(request, _t("Folosește POST pentru această acțiune."), 405)

	class OrdineResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, schimbaOrdinea(argumenteOrdine(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {b"meniu": ArboreResource(), b"meniu-televizor": TelevizorResource(), b"meniu-ordine": OrdineResource()}
	return api, PaginaResource()


def pagina(request):
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


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meniul receptorului</title>
<style>__STIL_COMUN__
  main{max-width:880px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  details{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;margin:0 0 10px;}
  details details{margin:8px 0 8px 0;background:#181c23;}
  summary{cursor:pointer;padding:12px 14px;font-size:1rem;min-height:44px;display:flex;align-items:center;gap:10px;}
  summary a{font-size:.85rem;}
  .copii{padding:0 12px 8px;}
  .intrare{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px 12px;padding:8px 2px;border-top:1px solid var(--bordura);}
  .intrare .nume{font-size:.95rem;}
  .pictograma{display:inline-block;width:22px;height:22px;flex:none;background:currentColor;
    -webkit-mask:var(--pictograma) center/contain no-repeat;
    mask:var(--pictograma) center/contain no-repeat;}
  .intrare .nume{display:flex;align-items:center;gap:10px;}
  .intrare .actiuni{display:flex;flex-wrap:wrap;gap:8px;align-items:center;}
  .intrare .motiv{color:var(--text-slab);font-size:.8rem;}
  .intrare .text{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1 1 240px;}
  .descriere{color:var(--text-slab);font-size:.82rem;line-height:1.35;overflow-wrap:anywhere;}
  .copii > .descriere{margin:2px 2px 6px;}
  .unic{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;margin:0 0 10px;padding:4px 14px;}
  .unic .intrare{border-top:0;}
  .unic .nume{font-size:1rem;}
  button{min-height:44px;padding:6px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;font-size:.85rem;cursor:pointer;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .intrare.ales{background:#22304a;border-radius:8px;padding-left:8px;padding-right:8px;}
  form.cauta-setari{display:flex;gap:8px;margin:0 0 14px;}
  form.cauta-setari input{flex:1;min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  form.cauta-setari button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .fila{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px;}
  .ascuns-semn{color:var(--text-slab);font-size:.8rem;border:1px solid var(--bordura);border-radius:6px;padding:1px 6px;}
  .ascuns > .nume, .ascuns > .text, summary.ascuns{opacity:.6;}
  .aranjare{display:none;gap:6px;align-items:center;flex-wrap:wrap;}
  body.aranjeaza .aranjare{display:inline-flex;}
  body.aranjeaza .actiuni-normale{display:none;}
  .aranjare button{min-width:44px;font-size:1rem;}
  .aranjare label{display:inline-flex;align-items:center;gap:6px;font-size:.85rem;min-height:44px;}
  #fabrica-tot{display:none;}
  body.aranjeaza #fabrica-tot{display:inline-block;}
</style>
</head>
<body>
<main>
<h1>Meniul receptorului</h1>
<p><a href="/setari?deschis=1">Setările deschise pe televizor</a></p>
<p><a href="/skin">Listă sau dale pe televizor</a></p>
<form class="cauta-setari" action="/cauta-setari" method="get" role="search"><input type="search" name="q" maxlength="60" placeholder="Caută în meniu" aria-label="Caută în meniu" autocomplete="off"><button type="submit">Caută</button></form>
<p class="nota">Același meniu ca la tasta MENU, cu aceleași intrări pentru nivelul ales pe receptor. La fiecare intrare: pagina ei din interfața web, dacă are, pagina de setări sau „Deschide pe televizor”.</p>
<div class="fila"><button type="button" id="aranjeaza">Aranjează meniul</button><button type="button" id="fabrica-tot">Ordinea din fabrică pentru tot meniul</button></div>
<p class="nota" id="nota-aranjare" hidden>Mută intrările cu săgețile și bifează ce nu vrei să vezi în meniul de pe televizor. Se salvează pe loc; intrările ascunse rămân aici și în căutare. Pe televizor: MENU pe o intrare.</p>
<p class="mesaj" id="mesaj">Se citește meniul...</p>
<div id="meniu"></div>
<p class="nota">Extensiile instalate care se agață de meniu apar la locul lor, ca pe televizor, și se mută sau se ascund la fel. Oprirea, repornirea și standby-ul receptorului se dau din pagina Alimentare și repornire, cu confirmare, sau din telecomandă.</p>
</main>
<script>
var CFG = __CONFIG__;
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
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function legatura(href, text){ var a = document.createElement("a"); a.href = adresa(href); a.textContent = text; return a; }
function pictograma(nume, parinte){
  if(!/^[a-z0-9-]{1,40}$/.test(nume || "")){ return; }
  var p = document.createElement("span"); p.className = "pictograma";
  p.setAttribute("aria-hidden", "true");
  p.style.setProperty("--pictograma", "url(/cadru/meniu-" + nume + ".png)");
  parinte.insertBefore(p, parinte.firstChild);
}
function deschide(id, meniu, oglinda){
  var q = new URLSearchParams(); q.set("id", id);
  if(meniu){ q.set("meniu", meniu); }
  mesaj("Se deschide pe televizor...");
  cerere("/api/meniu-televizor", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result && oglinda){ location.href = adresa("/setari?deschis=1"); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function semnAscuns(c, parinte){
  if(!c.ascuns){ return; }
  var s = document.createElement("span"); s.className = "ascuns-semn"; s.textContent = "ascunsă pe televizor";
  parinte.appendChild(s);
}
function schimba(meniu, id, fel){
  var q = new URLSearchParams(); q.set("meniu", meniu || ""); q.set("id", id || ""); q.set("fel", fel);
  mesaj("Se salvează...");
  cerere("/api/meniu-ordine", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.meniu){ deseneaza(d.meniu, id); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function butonAranjare(text, eticheta, lucru){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text;
  b.title = eticheta; b.setAttribute("aria-label", eticheta);
  b.addEventListener("click", function(e){ e.preventDefault(); e.stopPropagation(); lucru(); });
  return b;
}
function aranjare(c, meniu, i, n){
  var a = document.createElement("span"); a.className = "aranjare";
  var sus = butonAranjare("↑", "Mai sus", function(){ schimba(meniu, c.ordine_id, "sus"); });
  var jos = butonAranjare("↓", "Mai jos", function(){ schimba(meniu, c.ordine_id, "jos"); });
  sus.disabled = i === 0; jos.disabled = i === n - 1;
  a.appendChild(sus); a.appendChild(jos);
  var l = document.createElement("label"); var x = document.createElement("input"); x.type = "checkbox"; x.checked = !!c.ascuns;
  x.addEventListener("change", function(){ schimba(meniu, c.ordine_id, x.checked ? "ascunde" : "arata"); });
  l.addEventListener("click", function(e){ e.stopPropagation(); });
  l.appendChild(x); l.appendChild(document.createTextNode("Ascunsă pe televizor"));
  a.appendChild(l);
  return a;
}
function intrare(c, meniu, i, n){
  var div = document.createElement("div"); div.className = "intrare" + (c.ascuns ? " ascuns" : "");
  if(c.id){ div.id = "i-" + c.id; }
  div.setAttribute("data-ordine", c.ordine_id || "");
  var nume = document.createElement("span"); nume.className = "nume"; nume.textContent = c.text;
  pictograma(c.pictograma, nume); semnAscuns(c, nume);
  if(c.extensie){ var e = document.createElement("span"); e.className = "ascuns-semn"; e.textContent = "extensie instalată"; nume.appendChild(e); }
  var text = document.createElement("span"); text.className = "text"; text.appendChild(nume);
  if(c.descriere){ var ds = document.createElement("span"); ds.className = "descriere"; ds.textContent = c.descriere; text.appendChild(ds); }
  div.appendChild(text);
  if(c.ordine_id && meniu){ div.appendChild(aranjare(c, meniu, i, n)); }
  var a = document.createElement("span"); a.className = "actiuni actiuni-normale";
  if(c.web){ a.appendChild(legatura(c.web, "Pagina web")); }
  if(c.setup_web || c.setup){ a.appendChild(legatura("/setari?id=" + encodeURIComponent(c.setup_web || c.setup), "Setări în web")); }
  if(c.televizor){ var b = document.createElement("button"); b.type = "button"; b.textContent = "Deschide pe televizor"; b.addEventListener("click", function(){ deschide(c.id, c.extensie ? meniu : ""); }); a.appendChild(b); }
  else if(c.motiv){ var m = document.createElement("span"); m.className = "motiv"; m.textContent = c.motiv; a.appendChild(m); }
  if(c.televizor){
    var o = document.createElement("button"); o.type = "button"; o.textContent = "Deschide și arată aici";
    o.addEventListener("click", function(){ deschide(c.id, c.extensie ? meniu : "", true); }); a.appendChild(o);
  }
  div.appendChild(a);
  return div;
}
function grup(g, deschis, meniu, i, n){
  var d = document.createElement("details"); if(deschis){ d.open = true; }
  if(g.id){ d.id = "g-" + g.id; }
  d.setAttribute("data-ordine", g.ordine_id || "");
  var s = document.createElement("summary"); s.appendChild(document.createTextNode(g.text));
  if(g.ascuns){ s.className = "ascuns"; }
  pictograma(g.pictograma, s); semnAscuns(g, s);
  if(g.web){ var w = legatura(g.web, "Pagina web"); w.className = "actiuni-normale"; s.appendChild(w); }
  if(g.ordine_id && meniu){ s.appendChild(aranjare(g, meniu, i, n)); }
  d.appendChild(s);
  var c = document.createElement("div"); c.className = "copii";
  if(g.descriere){ var ds = document.createElement("p"); ds.className = "descriere"; ds.textContent = g.descriere; c.appendChild(ds); }
  var k = g.copii.length;
  g.copii.forEach(function(x, j){ c.appendChild(x.tip === "grup" ? grup(x, false, g.cheie, j, k) : intrare(x, g.cheie, j, k)); });
  d.appendChild(c);
  return d;
}
// tot meniul din nou (dupa o schimbare), cu aceleasi grupe deschise si intrarea mutata in vedere
function deseneaza(principal, ales){
  var m = $("meniu");
  var deschise = {};
  Array.prototype.forEach.call(m.querySelectorAll("details[open]"), function(d){ deschise[d.id] = true; });
  m.textContent = "";
  var n = principal.copii.length;
  principal.copii.forEach(function(x, i){
    if(x.tip === "grup"){ m.appendChild(grup(x, false, principal.cheie, i, n)); return; }
    var u = document.createElement("div"); u.className = "unic"; u.appendChild(intrare(x, principal.cheie, i, n)); m.appendChild(u);
  });
  Array.prototype.forEach.call(m.querySelectorAll("details"), function(d){ if(deschise[d.id]){ d.open = true; } });
  if(ales){
    Array.prototype.forEach.call(m.querySelectorAll("[data-ordine]"), function(x){
      if(x.getAttribute("data-ordine") === ales){ x.scrollIntoView({block: "nearest"}); }
    });
  }
}
function aranjeaza(da){
  document.body.classList.toggle("aranjeaza", da);
  $("aranjeaza").textContent = da ? "Gata" : "Aranjează meniul";
  $("nota-aranjare").hidden = !da;
}
$("aranjeaza").addEventListener("click", function(){ aranjeaza(!document.body.classList.contains("aranjeaza")); });
$("fabrica-tot").addEventListener("click", function(){ schimba("", "", "fabrica-tot"); });
// /meniu#i-<entryID> (din meniul de sus, la intrarile care se deschid numai pe televizor): grupa intrarii se
// deschide, iar randul ei e ales si adus in fata. /meniu#g-<id> (o treapta din calea paginii, grupa fara pagina ei,
// cadru_web._hrefGrupa): grupa se deschide, cu cele de deasupra ei, si vine sus
function arataDinAdresa(){
  var vechi = document.querySelector(".intrare.ales"); if(vechi){ vechi.classList.remove("ales"); }
  var h = location.hash.slice(1);
  try{ h = decodeURIComponent(h); }catch(e){ return; }
  if(!/^[ig]-[A-Za-z0-9_.-]{1,64}$/.test(h) && !/^[ig]-[^\\u0000-\\u001f\\u007f]{1,256}$/.test(h)){ return; }
  var x = $(h); if(!x){ return; }
  for(var p = x; p; p = p.parentNode){ if(p.tagName === "DETAILS"){ p.open = true; } }
  if(h.charAt(0) === "g"){ x.scrollIntoView({block: "start"}); return; }
  x.classList.add("ales");
  x.scrollIntoView({block: "center"});
}
window.addEventListener("hashchange", arataDinAdresa);
cerere("/api/meniu").then(function(d){
  if(!d.result){ mesaj(d.message, true); return; }
  mesaj("");
  deseneaza(d.meniu);
  // /meniuri: aceeasi pagina, direct pe fila Aranjeaza
  if(location.pathname.split("/")[1] === "meniuri" || location.hash === "#aranjeaza"){ aranjeaza(true); }
  arataDinAdresa();
}).catch(function(){ mesaj("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true); });
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Meniul receptorului"),
		N_("Caută"),
		N_("Același meniu ca la tasta MENU, cu aceleași intrări pentru nivelul ales pe receptor. La fiecare "
			"intrare: pagina ei din interfața web, dacă are, pagina de setări sau „Deschide pe televizor”."),
		N_("Se citește meniul..."),
		N_("Extensiile instalate care se agață de meniu apar la locul lor, ca pe televizor, și se mută sau se ascund "
			"la fel. Oprirea, repornirea și standby-ul receptorului se dau din pagina Alimentare și repornire, cu "
			"confirmare, sau din telecomandă."),
		N_("Caută în meniu"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se deschide pe televizor..."),
		N_("Receptorul nu răspunde."),
		N_("Pagina web"),
		N_("Setări în web"),
		N_("Deschide pe televizor"),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
	),
}


TEXTE_PAGINA["html"] += (N_("Listă sau dale pe televizor"),)
TEXTE_PAGINA["html"] += (N_("Setările deschise pe televizor"),)
TEXTE_PAGINA["js"] += (N_("Deschide și arată aici"),)
# MNH (0.7.5): fila Aranjeaza (ordinea si ascunderea intrarilor, ca MENU pe televizor)
TEXTE_PAGINA["html"] += (
	N_("Aranjează meniul"),
	N_("Ordinea din fabrică pentru tot meniul"),
	N_("Mută intrările cu săgețile și bifează ce nu vrei să vezi în meniul de pe televizor. Se salvează pe loc; "
		"intrările ascunse rămân aici și în căutare. Pe televizor: MENU pe o intrare."),
)
TEXTE_PAGINA["js"] += (
	# MLW (0.7.5): semnul extensiilor agatate de meniu
	N_("extensie instalată"),
	N_("ascunsă pe televizor"),
	N_("Se salvează..."),
	N_("Mai sus"),
	N_("Mai jos"),
	N_("Ascunsă pe televizor"),
	N_("Gata"),
	N_("Aranjează meniul"),
)


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
