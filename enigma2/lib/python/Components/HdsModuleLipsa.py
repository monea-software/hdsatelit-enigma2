# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsModuleLipsa.py: un plugin care cade fiindca ii lipseste un modul Python (ModuleNotFoundError) primeste modulul singur, din
# feedul nostru, fara intrebare si fara repornirea interfetei (06.11.2026, lotul module-lipsa-071; Eduard: modulele mici in imagine, cele
# mari in feedul imaginii, descarcate automat cand le cere un plugin).
#
# Harta modul -> pachet: HARTA (data/hds-module-pachete.json, in /usr/share/enigma2), facuta din pachetele .ipk ale feedului de
# lucru-sesiune/oe-60/pluginuri-compat/unelte/module_inventar.py (caile usr/lib/python3.14/...), nu scrisa de mana. Numai un modul din
# harta porneste ceva; numele altor module nu ajung niciodata la opkg.
#
# Cand:
#   - la citirea listei de pluginuri (Components/PluginComponent.py: readPluginList -> dupaCitire): pluginul cazut la import cu un modul
#     din harta intra in coada; prima citire e la pornire, inainte de sesiune, deci coada asteapta porneste(session) din mytest.py si
#     INTARZIERE_PORNIRE_MS (interfata intai);
#   - la deschiderea unui plugin (Plugins/Plugin.py reportError), la un ecran cazut (mytest.py handleScreenCrash) si la o eroare din C++
#     (Components/HdsPluginExtern.py): aceeasi coada, iar la sfarsit mesajul spune "deschide-l din nou".
# Cum: o lucrare opkg a gestionarului de extensii (Components/HdsExtensiiLucru.Lucrare: aceeasi coada pentru televizor si pagina web,
# acelasi jurnal hds-extensii.log), una odata. Cu opkg ocupat (alta lucrare, o descarcare a listei, zavorul opkg) se reincearca peste
# PAS_ASTEPTARE_MS, fara sa se piarda incercarea. Listele surselor noastre lipsa sau mai vechi de VARSTA_LISTE_S: intai opkg update, o
# data pe sesiune; o descarcare cazuta (de pilda fara internet inca, la pornire) se reia de MAX_ESECURI_LISTE ori. Pachetul se
# instaleaza numai daca cea mai noua versiune din toate listele e intr-un feed HD Satelit (feedul de pluginuri externe sau al
# imaginii; opkg alege singur cea mai noua, deci altfel ar lua-o din sursa altcuiva). Dupa instalare lista
# pluginurilor se citeste din nou (Lucrare); pluginul care acum se incarca intra in liste pe loc (PluginComponent.activeazaAcum).
# Pe ecran: mesajul mic al imaginii (Screens/HdsAnuntRetea), nemodal: "Se instalează modulul X pentru Y.", apoi "Y este gata." sau
# motivul. O singura incercare pe pachet si sesiune; cel mult MAX_PE_PLUGIN pachete pentru acelasi plugin; un pachet deja instalat, cu
# pluginul cazut tot pe el, nu se mai instaleaza (fara bucla). Ce se intampla se vede si in pagina web: motivul din lista pluginurilor
# care nu se deschid (textStare) si lucrarea in curs din /extensii.
# Nu importa nimic din enigma la incarcare (probele de pe PC); RADACINA pune un dosar in fata cailor de sistem, numai la probe. Nu arunca.
import json
import os
import re
import time

RADACINA = ""
HARTA = "/usr/share/enigma2/hds-module-pachete.json"
OPKG_INFO = "/var/lib/opkg/info"
OPKG_LACAT = "/var/run/opkg.lock"
INTARZIERE_PORNIRE_MS = 20000
PAS_ASTEPTARE_MS = 60000
PAS_URMATOR_MS = 1500
VARSTA_LISTE_S = 3 * 24 * 3600
MAX_PE_PLUGIN = 3
MAX_ESECURI_LISTE = 3
DURATA_MESAJ_MS = 9000

_MODUL = re.compile(r"No module named '([^']+)'")
_NUME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,200}\Z")

_harta = [None]
_coada = []          # [{"pachet", "modul", "pluginuri": {cale: {"nume", "cand"}}}], in ordinea cererilor
_rezultat = {}       # pachet -> {"stare": instalat | esuat | refuzat | lipsa | instalat_dar_cade, "motiv": text}
_pePlugin = {}       # calea pluginului -> cate pachete i s-au instalat in sesiunea asta
_stare = {"sesiune": None, "pornit": False, "ceas": None, "lucrare": None, "liste": False, "esecuri_liste": 0}


def N_(text):
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsModuleLipsa] %s" % text)


def _c(cale):
	return RADACINA + cale if RADACINA else cale


# ---------------------------------------------------------------- harta si cererile

def harta():
	"""{modul: pachet} din HARTA, citita o data; {} cand lipseste sau e stricata"""
	if _harta[0] is None:
		h = {}
		try:
			with open(_c(HARTA), encoding="utf-8") as f:
				date = json.load(f)
			if date.get("format") == 1 and isinstance(date.get("module"), dict):
				h = dict((m, p) for m, p in date["module"].items() if _NUME.match(m) and _pachetBun(p))
		except (OSError, ValueError, AttributeError) as e:
			_jurnal("harta %s: %s" % (HARTA, e))
		_harta[0] = h
	return _harta[0]


def _pachetBun(nume):
	return isinstance(nume, str) and re.match(r"^[a-z0-9][a-z0-9+.\-]{0,120}\Z", nume) is not None


def modulDinEroare(eroare):
	"""numele modulului lipsa dintr-o exceptie (ModuleNotFoundError.name) sau din textul ei; None altfel"""
	if isinstance(eroare, ImportError) and getattr(eroare, "name", None) and "No module named" in str(eroare):
		return eroare.name
	gasit = _MODUL.search(str(eroare or ""))
	return gasit.group(1) if gasit else None


def pachetPentru(modul):
	"""pachetul din harta pentru modul (cel mai lung prefix cu puncte: Crypto.Cipher -> Crypto), sau None"""
	if not modul or not _NUME.match(modul):
		return None
	h = harta()
	parti = modul.split(".")
	for i in range(len(parti), 0, -1):
		p = h.get(".".join(parti[:i]))
		if p:
			return p
	return None


def instalat(pachet):
	return os.path.exists(_c("%s/%s.control" % (OPKG_INFO, pachet)))


def cere(eroare, cale, nume, cand="incarcare"):
	"""Pachetul pus in coada pentru pluginul de la `cale`, sau None (modul in afara hartii, deja incercat, deja instalat)."""
	try:
		modul = modulDinEroare(eroare)
		pachet = pachetPentru(modul)
		if pachet is None:
			return None
		cale = cale or nume or ""
		if instalat(pachet):
			# pachetul e pe receptor si pluginul tot cade pe el: nu e o lipsa a imaginii; o singura data in jurnal
			if pachet not in _rezultat:
				_rezultat[pachet] = {"stare": "instalat_dar_cade", "motiv": ""}
				_jurnal("%s e instalat, dar %s tot nu gaseste %s" % (pachet, nume, modul))
			return None
		if pachet in _rezultat:
			return None
		if _pePlugin.get(cale, 0) >= MAX_PE_PLUGIN:
			return None
		el = next((x for x in _coada if x["pachet"] == pachet), None)
		if el is None:
			el = {"pachet": pachet, "modul": modul, "pluginuri": {}}
			_coada.append(el)
			_jurnal("in coada: %s (modulul %s, pentru %s)" % (pachet, modul, nume))
		el["pluginuri"].setdefault(cale, {"nume": nume or cale.rsplit("/", 1)[-1], "cand": cand})
		if _stare["pornit"]:
			_programeaza(PAS_URMATOR_MS)
		return pachet
	except Exception as e:
		_jurnal("cere: %r" % (e,))
		return None


def dupaCitire(plugins):
	"""Dupa readPluginList: pluginurile cazute la import pe un modul din harta (erori cu "modul")."""
	try:
		for e in list(getattr(plugins, "erori", {}).values()):
			if e.get("modul"):
				cere(ImportError("No module named '%s'" % e["modul"]), e.get("path"), e.get("nume"), "incarcare")
	except Exception as e:
		_jurnal("dupaCitire: %r" % (e,))


def dinExceptie(eroare, cale=None, nume=None):
	"""Un plugin cazut la deschidere (ecran, functie, apel din C++) pe un modul lipsa."""
	return cere(eroare, cale, nume, "deschidere")


def textStare(modul):
	"""Motivul pentru om din lista pluginurilor care nu se deschid (televizor si web), sau None (ramane "Lipsește modulul X")."""
	pachet = pachetPentru(modul)
	if pachet is None:
		return None
	if _stare["lucrare"] is not None and _stare["lucrare"]["pachet"] == pachet:
		return _t("Se instalează modulul %s") % modul
	if any(x["pachet"] == pachet for x in _coada):
		return _t("Modulul %s se instalează în curând") % modul
	r = _rezultat.get(pachet)
	if r and r["stare"] in ("esuat", "refuzat", "lipsa"):
		return _t("Lipsește modulul %s. Nu s-a putut instala: %s") % (modul, r["motiv"])
	return None


# ---------------------------------------------------------------- lucrul, unul odata

def porneste(session):
	"""Din mytest.py, dupa crearea sesiunii: coada (cererile de la pornire) incepe dupa INTARZIERE_PORNIRE_MS."""
	_stare["sesiune"] = session
	_stare["pornit"] = True
	if _coada:
		_programeaza(INTARZIERE_PORNIRE_MS)


def _programeaza(ms):
	try:
		from enigma import eTimer
	except ImportError:
		return
	if _stare["ceas"] is None:
		_stare["ceas"] = eTimer()
		_stare["ceas"].callback.append(_urmatorul)
	if not _stare["ceas"].isActive():
		_stare["ceas"].start(ms, True)


def _X():
	from Components import HdsExtensiiLucru
	return HdsExtensiiLucru


def _lacatViu(cale):
	"""alt program tine zavorul lui opkg (lockf, ca libopkg)"""
	try:
		import fcntl
	except ImportError:
		return False
	try:
		with open(cale, "ab") as f:
			fcntl.lockf(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
			fcntl.lockf(f.fileno(), fcntl.LOCK_UN)
		return False
	except (OSError, IOError):
		return True


def _ocupat():
	try:
		X = _X()
		if X.lucrareInCurs() or X.descarcareInCurs():
			return True
	except Exception:
		pass
	return os.path.exists(_c(OPKG_LACAT)) and _lacatViu(_c(OPKG_LACAT))


def _configurare():
	from Components import HdsPachete
	return HdsPachete.citeste_configurarea(RADACINA or "/")


def _sursaNoastra(conf, nume, adresa):
	"""sursa e un feed HD Satelit: al imaginii (stb.hdsatelit.com, https) sau cel de pluginuri externe, nu una adaugata de om"""
	try:
		import types
		X = _X()
		return X.felFeed(types.SimpleNamespace(configurare=conf), nume, adresa) in (X.FEED_HDS, X.FEED_EXTERN)
	except Exception as e:
		_jurnal("sursa %s: %r" % (nume, e))
		return False


def listeVechi(conf=None, acum=None):
	"""True cand o sursa de-a noastra nu are lista descarcata sau lista e mai veche de VARSTA_LISTE_S"""
	conf = conf or _configurare()
	acum = time.time() if acum is None else acum
	noastre = [(n, a) for n, a in conf.surse if _sursaNoastra(conf, n, a)]
	if not noastre:
		return True
	for n, _a in noastre:
		f = os.path.join(_c(conf.lists_dir), n)
		try:
			if acum - os.path.getmtime(f) > VARSTA_LISTE_S:
				return True
		except OSError:
			return True
	return False


def candidati(pachet, conf=None):
	"""[(versiune, sursa, a_noastra)] pentru pachet, din listele tuturor surselor, pe arhitecturile receptorului"""
	from Components import HdsPachete as P
	conf = conf or _configurare()
	rez = []
	for n, a in conf.surse:
		f = os.path.join(_c(conf.lists_dir), n)
		if not os.path.isfile(f):
			continue
		try:
			for s in P.citeste_strofe(f):
				if s.get("package") == pachet and P._arhitectura_buna(s.get("architecture", ""), conf.arhitecturi):
					rez.append((s.get("version", ""), n, _sursaNoastra(conf, n, a)))
		except Exception as e:
			_jurnal("lista %s: %r" % (n, e))
	return rez


def provenienta(pachet, conf=None):
	"""(versiunea de instalat, None) cand cea mai noua versiune a pachetului e intr-un feed de-al nostru; altfel (None, motivul)"""
	from Components import HdsPachete as P
	c = candidati(pachet, conf)
	if not c:
		return None, "lipsa"
	cel_mai_nou = c[0]
	for x in c[1:]:
		if P.compara_versiuni(x[0], cel_mai_nou[0]) > 0 or (P.compara_versiuni(x[0], cel_mai_nou[0]) == 0 and x[2] and not cel_mai_nou[2]):
			cel_mai_nou = x
	if not cel_mai_nou[2]:
		return None, "straina"
	return cel_mai_nou[0], None


def _mesaj(text):
	s = _stare["sesiune"]
	if s is None or not text:
		return
	try:
		from Screens import HdsAnuntRetea
		HdsAnuntRetea.arata(s, text, "", DURATA_MESAJ_MS)
	except Exception as e:
		_jurnal("mesaj: %r" % (e,))


def _numePluginuri(el):
	return ", ".join(sorted(set(v["nume"] for v in el["pluginuri"].values())))


def _urmatorul():
	"""Primul pachet din coada: lista surselor, provenienta, lucrarea opkg. Chemat de ceas."""
	try:
		if not _coada or _stare["lucrare"] is not None:
			return
		if _ocupat():
			_programeaza(PAS_ASTEPTARE_MS)
			return
		el = _coada[0]
		conf = _configurare()
		if not _stare["liste"] and listeVechi(conf):
			_stare["liste"] = True
			_actualizeazaListele()
			return
		versiune, motiv = provenienta(el["pachet"], conf)
		if versiune is None:
			if motiv == "lipsa" and not _stare["liste"]:
				# pachetul poate fi nou in feed: o data, lista din nou
				_stare["liste"] = True
				_actualizeazaListele()
				return
			_coada.pop(0)
			text = _t("Feedul HD Satelit nu are modulul.") if motiv == "lipsa" else _t("Altă sursă are o versiune mai nouă; nu o instalez singur.")
			_rezultat[el["pachet"]] = {"stare": "lipsa" if motiv == "lipsa" else "refuzat", "motiv": text}
			_jurnal("%s nu se instaleaza: %s" % (el["pachet"], motiv))
			_programeaza(PAS_URMATOR_MS)
			return
		_pornesteLucrarea(el, versiune)
	except Exception as e:
		_jurnal("urmatorul: %r" % (e,))


def _actualizeazaListele():
	X = _X()
	_jurnal("opkg update inainte de instalare")
	d = X.pornesteDescarcarea()

	def gata(eveniment, parametru):
		if eveniment == X.IpkgComponent.EVENT_DONE:
			d.removeCallback(gata)
			if parametru == 0:
				_stare["esecuri_liste"] = 0
				_programeaza(PAS_URMATOR_MS)
				return
			_jurnal("opkg update: cod %s" % parametru)
			listaCazuta(X)
	d.addCallback(gata)


def listaCazuta(X=None):
	"""opkg update n-a mers (fara internet inca, la o pornire cu Wi-Fi lent; serverul nu raspunde): se reincearca de cel mult
	MAX_ESECURI_LISTE ori la PAS_ASTEPTARE_MS, fara sa se piarda incercarea pachetelor; dupa aceea pachetele din coada raman
	neinstalate in sesiunea asta, cu motivul descarcarii (nu "feedul nu are modulul", care ar fi neadevarat)."""
	X = X or _X()
	_stare["esecuri_liste"] = _stare.get("esecuri_liste", 0) + 1
	if _stare["esecuri_liste"] < MAX_ESECURI_LISTE:
		_stare["liste"] = False
		_programeaza(PAS_ASTEPTARE_MS)
		return
	try:
		motiv = (X.STARE.get("descarcare") or {}).get("motiv") or _t("Operațiunea nu a reușit.")
	except Exception:
		motiv = _t("Operațiunea nu a reușit.")
	primul = _coada[0] if _coada else None
	for el in _coada:
		_rezultat[el["pachet"]] = {"stare": "esuat", "motiv": motiv}
	del _coada[:]
	_jurnal("listele surselor nu se descarca (%d incercari): %s" % (_stare["esecuri_liste"], motiv))
	if primul is not None:
		_mesaj(_t("Modulul %s nu s-a instalat: %s") % (primul["modul"], motiv))


def planModul(el, versiune):
	"""planul lucrarii opkg (Components/HdsExtensiiLucru.Lucrare) pentru pachetul din coada"""
	X = _X()
	argumente = X.opkgArguments("install", [el["pachet"]])
	if argumente is None:
		return None
	titlu = _t("modulul %s") % el["modul"]
	return {"fel": "instaleaza", "titlu": titlu, "nume": titlu, "subtitlu": _numePluginuri(el), "icoana": "altele", "randuri": [],
		"nota": "", "externe": [], "notaCuloare": "", "buton": N_("Instalează"), "argumente": argumente, "repornire": False,
		"pachete": [el["pachet"]], "tinte": [{"nume": el["pachet"], "titlu": el["pachet"], "la": versiune, "de": "", "acces": False}],
		"automat": True}


def _pornesteLucrarea(el, versiune):
	X = _X()
	plan = planModul(el, versiune)
	if plan is None:
		_coada.pop(0)
		_rezultat[el["pachet"]] = {"stare": "esuat", "motiv": _t("Numele pachetului nu este valid.")}
		return
	_stare["lucrare"] = el
	l = X.Lucrare(plan)

	def ascultator(eveniment, *date):
		if eveniment == "gata":
			l.lasa(ascultator)
			dupaLucrare(el, l)
	l.asculta(ascultator)
	_jurnal("instalez %s %s pentru %s" % (el["pachet"], versiune, _numePluginuri(el)))
	_mesaj(_t("Se instalează modulul %s pentru %s.") % (el["modul"], _numePluginuri(el)))
	l.porneste()


def dupaLucrare(el, lucrare, plugins=None):
	"""Sfarsitul lucrarii opkg: pluginurile care acum se incarca intra in liste, mesajul pe ecran, urmatorul din coada."""
	try:
		if _coada and _coada[0] is el:
			_coada.pop(0)
		elif el in _coada:
			_coada.remove(el)
		_stare["lucrare"] = None
		rez = getattr(lucrare, "rezultat", None) or {}
		if not rez.get("reusit"):
			motiv = rez.get("stare") or _t("Operațiunea nu a reușit.")
			_rezultat[el["pachet"]] = {"stare": "esuat", "motiv": motiv}
			_mesaj(_t("Modulul %s nu s-a instalat: %s") % (el["modul"], motiv))
			return
		_rezultat[el["pachet"]] = {"stare": "instalat", "motiv": ""}
		if plugins is None:
			from Components.PluginComponent import plugins
		erori = dict((e.get("path"), e) for e in getattr(plugins, "erori", {}).values())
		gata, cad, deschide = [], [], []
		for cale, v in el["pluginuri"].items():
			_pePlugin[cale] = _pePlugin.get(cale, 0) + 1
			if v["cand"] == "deschidere":
				deschide.append(v["nume"])
			elif cale in erori:
				cad.append((v["nume"], erori[cale]))
			else:
				gata.append(cale)
		pornite = []
		if gata and hasattr(plugins, "activeazaAcum"):
			pornite = plugins.activeazaAcum(gata, _stare["sesiune"])
		if gata:
			# rezultatul lucrarii (pagina web, ecranul extensiilor deschis): fara "repornește interfața" pentru pluginul pornit acum
			rez.update(stare=_t("Gata"), butoane=[N_("Închide")], ales=0, repornire=False, culoare="bun")
		texte = []
		for cale in gata:
			texte.append(_t("%s este gata.") % el["pluginuri"][cale]["nume"])
		for nume in deschide:
			texte.append(_t("Modulul %s s-a instalat. Deschide din nou %s.") % (el["modul"], nume))
		for nume, e in cad:
			# alt modul lipsa: dupaCitire l-a pus deja in coada; altfel motivul
			if not e.get("modul"):
				texte.append(_t("%s tot nu pornește: %s") % (nume, ((e.get("mesaj") or "").splitlines() or [""])[0][:120]))
		_jurnal("%s instalat; gata: %s; pornite acum: %d" % (el["pachet"], ", ".join(gata) or "-", len(pornite or [])))
		_mesaj(" ".join(texte))
	except Exception as e:
		_jurnal("dupaLucrare: %r" % (e,))
	finally:
		if _coada:
			_programeaza(PAS_URMATOR_MS)


def _reseteaza():
	"""numai pentru probe: starea modulului ca la pornire"""
	_harta[0] = None
	del _coada[:]
	_rezultat.clear()
	_pePlugin.clear()
	_stare.update(sesiune=None, pornit=False, ceas=None, lucrare=None, liste=False, esecuri_liste=0)
