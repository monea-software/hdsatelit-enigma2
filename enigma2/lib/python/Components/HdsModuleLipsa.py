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
# motivul. Un pachet pe care feedul nu-l are se tine minte pe disc (LIPSA_FISIER): o zi, fara opkg update la fiecare pornire
# (0.7.5, vezi REINCERCARE_S). O singura incercare pe pachet si sesiune; cel mult MAX_PE_PLUGIN pachete pentru acelasi plugin; un pachet deja instalat, cu
# pluginul cazut tot pe el, nu se mai instaleaza (fara bucla). Ce se intampla se vede si in pagina web: motivul din lista pluginurilor
# care nu se deschid (textStare) si lucrarea in curs din /extensii.
# Nu importa nimic din enigma la incarcare (probele de pe PC); RADACINA pune un dosar in fata cailor de sistem, numai la probe. Nu arunca.
import json
import os
import re
import time

RADACINA = ""
HARTA = "/usr/share/enigma2/hds-module-pachete.json"
# 0.7.4 (P4, Eduard 11.11.2026 21:55): bibliotecile vechi ale programelor altora (de obicei module de acces) pe care le are feedul
# extern, cu pachetul care le aduce: un program care cade pe una din ele (Components/HdsBibliotecaLipsa.py citeste antetul ELF) o
# primeste prin aceeasi coada (cereBiblioteca). Numai numele de aici ajung la opkg.
BIBLIOTECI = {
	"libcrypto.so.1.0.0": "openssl10-compat",
	"libssl.so.1.0.0": "openssl10-compat",
	"libcrypto.so.1.1": "openssl11-compat",
	"libssl.so.1.1": "openssl11-compat",
	"libcrypto.so.3": "openssl3-compat",
	"libssl.so.3": "openssl3-compat",
	"libcrypt.so.1": "libxcrypt-compat",
	"ld-linux.so.3": "ld-linux-compat",
	"libcurl.so.4": "libcurl4",  # 13.11.2026: NCam_15.8 (RAED) cere si libcurl, pe care feedul extern il are (LIB)
}
OPKG_INFO = "/var/lib/opkg/info"
INTARZIERE_PORNIRE_MS = 20000
PAS_ASTEPTARE_MS = 60000
PAS_URMATOR_MS = 1500
VARSTA_LISTE_S = 3 * 24 * 3600
MAX_PE_PLUGIN = 3
MAX_ESECURI_LISTE = 3
DURATA_MESAJ_MS = 9000
# 0.7.5 (asistenta 821342, TODO 14.11 19:10): un pachet pe care feedul nu-l are (python3-fissix lipsea din feedul 0.7.4) pornea
# opkg update si "nu se instaleaza: lipsa" la FIECARE pornire a interfetei, fiindca rezultatul se tinea numai in memorie. Acum
# pachetul lipsa se tine minte pe disc (LIPSA_FISIER), cu ora si semnul listelor surselor noastre (semnListe). Timp de
# REINCERCARE_S, la pornirile urmatoare nu mai porneste opkg update: cu aceleasi liste nu se face nimic, iar cu liste schimbate
# (un opkg update al altcuiva, alt feed) se cauta in ele, fara descarcare. Dupa REINCERCARE_S, o incercare intreaga, ca inainte.
LIPSA_FISIER = "/etc/enigma2/hds-module-lipsa.json"
REINCERCARE_S = 24 * 3600

_MODUL = re.compile(r"No module named '([^']+)'")
_NUME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,200}\Z")

_lipsa = [None]      # {pachet: {"cand": ora primei lipse, "semn": semnListe()}}, citit din LIPSA_FISIER o data
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


def cereBiblioteca(biblioteca, cale, nume, cand="program", dupa=None):
	"""Pachetul din BIBLIOTECI pus in coada pentru programul de la `cale` (modulul `nume`), sau None. `dupa()` se cheama dupa o
	instalare reusita (de pilda: modulul de acces porneste din nou). Aceleasi reguli ca la cere(): o incercare pe pachet si sesiune,
	nimic pentru un pachet deja instalat."""
	try:
		pachet = BIBLIOTECI.get(biblioteca)
		if pachet is None or not _pachetBun(pachet):
			return None
		cale = cale or nume or ""
		if instalat(pachet):
			if pachet not in _rezultat:
				_rezultat[pachet] = {"stare": "instalat_dar_cade", "motiv": ""}
				_jurnal("%s e instalat, dar %s tot nu gaseste %s" % (pachet, nume, biblioteca))
			return None
		if pachet in _rezultat:
			return None
		el = next((x for x in _coada if x["pachet"] == pachet), None)
		if el is None:
			el = {"pachet": pachet, "modul": biblioteca, "fel": "biblioteca", "pluginuri": {}}
			_coada.append(el)
			_jurnal("in coada: %s (biblioteca %s, pentru %s)" % (pachet, biblioteca, nume))
		el["pluginuri"].setdefault(cale, {"nume": nume or cale.rsplit("/", 1)[-1], "cand": cand, "dupa": dupa})
		if _stare["pornit"]:
			_programeaza(PAS_URMATOR_MS)
		return pachet
	except Exception as e:
		_jurnal("cereBiblioteca: %r" % (e,))
		return None


def cerePachet(pachet, cine, nume, dupa=None):
	"""0.7.6 (NCP, TODO 15.11 10:27): un pachet al feedului nostru pus in coada pentru altceva decat un plugin cazut (de pilda pluginul
	de setari al unei teme straine, Components/HdsPartiTema.py), sau None. In liniste: fara mesajele "Se instalează modulul ...";
	`dupa(reusit)` se cheama la sfarsitul lucrarii opkg (True dupa instalare, False cand n-a reusit) si spune omului ce e de spus. Aceleasi reguli ca la
	cere(): numai din feedul HD Satelit, o incercare pe pachet si sesiune, lipsa din feed tinuta minte o zi, nimic daca e instalat."""
	try:
		if not _pachetBun(pachet) or instalat(pachet) or pachet in _rezultat:
			return None
		cine = cine or nume or pachet
		el = next((x for x in _coada if x["pachet"] == pachet), None)
		if el is None:
			el = {"pachet": pachet, "modul": pachet, "fel": "pachet", "pluginuri": {}}
			_coada.append(el)
			_jurnal("in coada: %s (pentru %s)" % (pachet, nume or cine))
		el["pluginuri"].setdefault(cine, {"nume": nume or cine, "cand": "pachet", "dupa": dupa})
		if _stare["pornit"]:
			_programeaza(PAS_URMATOR_MS)
		return pachet
	except Exception as e:
		_jurnal("cerePachet: %r" % (e,))
		return None


def _dupaPachet(el, reusit):
	for cale, v in el["pluginuri"].items():
		if callable(v.get("dupa")):
			try:
				v["dupa"](reusit)
			except Exception as e:
				_jurnal("dupa %s: %r" % (cale, e))


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
	try:
		# modulul de acces ales care n-a pornit la pornirea receptorului fiindca ii lipseste o biblioteca din feed (0.7.4, P4)
		from Components import HdsBibliotecaLipsa
		HdsBibliotecaLipsa.verificaAlese()
	except Exception as e:
		_jurnal("verificaAlese: %r" % (e,))
	try:
		# 0.7.5: modulul ales oprit de altcineva la repornirea interfetei porneste din nou, ca la pornirea receptorului
		from Components import HdsModuleAcces
		HdsModuleAcces.dupa_pornirea_interfetei()
	except Exception as e:
		_jurnal("dupa_pornirea_interfetei: %r" % (e,))
	try:
		# 0.7.7 (MGR/PLAN-078 punctul 5): oscam.srvid2 din lista de canale in dosarul modulului ales, cand omul nu are fisierul lui
		# (Components/HdsSrvid.py), pe un fir, dupa lucrul greu de la pornire
		from Components import HdsSrvid
		HdsSrvid.porneste()
	except Exception as e:
		_jurnal("HdsSrvid: %r" % (e,))
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


def _opkgRuleaza():
	"""alt opkg tine zavorul lui (SSH, web, o actualizare): aceeasi verificare ca la actualizari
	(Components/HdsActualizari.opkg_ocupat: /run/opkg.lock, citit din /proc/locks fara sa ia zavorul). Inainte se citea
	/var/run/opkg.lock, unde opkg din imagine nu-l pune niciodata, deci nu se vedea niciun opkg."""
	try:
		try:
			from Components.HdsActualizari import opkg_ocupat
		except ImportError:
			from HdsActualizari import opkg_ocupat
		return bool(opkg_ocupat(RADACINA or "/"))
	except Exception as e:
		_jurnal("zavorul opkg: %r" % (e,))
		return False


def _ocupat():
	try:
		X = _X()
		if X.lucrareInCurs() or X.descarcareInCurs():
			return True
	except Exception:
		pass
	return _opkgRuleaza()


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


# ---------------------------------------------------------------- pachetele lipsa din feed, tinute minte intre porniri

def semnListe(conf=None):
	"""semnul listelor surselor noastre: numele, adresa, marimea si ora fiecarei liste descarcate. Se schimba la orice opkg
	update care aduce alta lista si la schimbarea adresei feedului."""
	conf = conf or _configurare()
	parti = []
	for n, a in sorted(conf.surse):
		if not _sursaNoastra(conf, n, a):
			continue
		try:
			st = os.stat(os.path.join(_c(conf.lists_dir), n))
			parti.append("%s|%s|%d|%d" % (n, a, st.st_size, int(st.st_mtime)))
		except OSError:
			parti.append("%s|%s|-" % (n, a))
	return ";".join(parti)


def _citesteLipsa():
	if _lipsa[0] is None:
		d = {}
		try:
			with open(_c(LIPSA_FISIER), encoding="utf-8") as f:
				date = json.load(f)
			for p, v in (date.get("pachete") or {}).items():
				if _pachetBun(p) and isinstance(v, dict) and isinstance(v.get("cand"), (int, float)):
					d[p] = {"cand": float(v["cand"]), "semn": str(v.get("semn", ""))}
		except FileNotFoundError:
			pass
		except (OSError, ValueError, AttributeError) as e:
			_jurnal("%s: %s" % (LIPSA_FISIER, e))
		_lipsa[0] = d
	return _lipsa[0]


def _scrieLipsa():
	cale = _c(LIPSA_FISIER)
	try:
		nou = cale + ".nou"
		with open(nou, "w", encoding="utf-8") as f:
			json.dump({"format": 1, "pachete": _citesteLipsa()}, f, sort_keys=True)
		os.replace(nou, cale)
	except OSError as e:
		_jurnal("nu pot scrie %s: %s" % (LIPSA_FISIER, e))


def lipsaRecenta(pachet, conf=None, acum=None):
	"""None cand pachetul nu e tinut minte ca lipsa sau au trecut REINCERCARE_S (o incercare intreaga); altfel "aceleasi"
	(listele nu s-au schimbat de atunci) sau "schimbate" (se cauta in listele de acum, fara opkg update)."""
	v = _citesteLipsa().get(pachet)
	acum = time.time() if acum is None else acum
	if v is None or not 0 <= acum - v["cand"] < REINCERCARE_S:
		return None
	return "aceleasi" if v["semn"] == semnListe(conf) else "schimbate"


def tineMinteLipsa(pachet, conf=None, acum=None):
	"""pachetul lipsa din feed, cu semnul listelor de acum; ora ramane a primei lipse cat timp tine REINCERCARE_S"""
	d = _citesteLipsa()
	acum = time.time() if acum is None else acum
	v = d.get(pachet)
	cand = v["cand"] if v is not None and 0 <= acum - v["cand"] < REINCERCARE_S else acum
	d[pachet] = {"cand": cand, "semn": semnListe(conf)}
	_scrieLipsa()


def uitaLipsa(pachet):
	if _citesteLipsa().pop(pachet, None) is not None:
		_scrieLipsa()


def _textNeinstalat(el, motiv):
	if motiv != "lipsa":
		return _t("Altă sursă are o versiune mai nouă; nu o instalez singur.")
	if el.get("fel") == "biblioteca":
		return _t("Feedul HD Satelit nu are biblioteca.")
	return _t("Feedul HD Satelit nu are modulul.")


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
		amintire = lipsaRecenta(el["pachet"], conf)
		if amintire is not None:
			# lipsea din feed la o pornire de curand: fara opkg update; cu liste schimbate intre timp, cautat in ele
			versiune, motiv = provenienta(el["pachet"], conf) if amintire == "schimbate" else (None, "lipsa")
			if versiune is not None:
				_pornesteLucrarea(el, versiune)
				return
			_coada.pop(0)
			_rezultat[el["pachet"]] = {"stare": "lipsa" if motiv == "lipsa" else "refuzat", "motiv": _textNeinstalat(el, motiv)}
			if amintire == "schimbate" and motiv == "lipsa":
				tineMinteLipsa(el["pachet"], conf)
			_jurnal("%s nu se instaleaza: %s (tinut minte, listele %s; fara opkg update pana la %d ore)" % (
				el["pachet"], motiv, amintire, REINCERCARE_S // 3600))
			_programeaza(PAS_URMATOR_MS)
			return
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
			_rezultat[el["pachet"]] = {"stare": "lipsa" if motiv == "lipsa" else "refuzat", "motiv": _textNeinstalat(el, motiv)}
			if motiv == "lipsa":
				tineMinteLipsa(el["pachet"], conf)
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
	if primul is not None and primul.get("fel") != "pachet":
		_mesaj(_t("Modulul %s nu s-a instalat: %s") % (primul["modul"], motiv))


def planModul(el, versiune):
	"""planul lucrarii opkg (Components/HdsExtensiiLucru.Lucrare) pentru pachetul din coada"""
	X = _X()
	argumente = X.opkgArguments("install", [el["pachet"]])
	if argumente is None:
		return None
	if el.get("fel") == "pachet":
		titlu = el["pachet"]
	else:
		titlu = (_t("biblioteca %s") if el.get("fel") == "biblioteca" else _t("modulul %s")) % el["modul"]
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
	if el.get("fel") == "pachet":
		pass
	elif el.get("fel") == "biblioteca":
		_mesaj(_t("Se instalează biblioteca %s pentru %s.") % (el["modul"], _numePluginuri(el)))
	else:
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
			if el.get("fel") == "pachet":
				_jurnal("%s nu s-a instalat: %s" % (el["pachet"], motiv))
				_dupaPachet(el, False)
			elif el.get("fel") == "biblioteca":
				_mesaj(_t("Biblioteca %s nu s-a instalat: %s") % (el["modul"], motiv))
			else:
				_mesaj(_t("Modulul %s nu s-a instalat: %s") % (el["modul"], motiv))
			return
		_rezultat[el["pachet"]] = {"stare": "instalat", "motiv": ""}
		uitaLipsa(el["pachet"])
		if el.get("fel") == "pachet":
			_jurnal("%s instalat pentru %s" % (el["pachet"], _numePluginuri(el)))
			_dupaPachet(el, True)
			return
		if el.get("fel") == "biblioteca":
			# programele (module de acces) nu sunt pluginuri de activat: fiecare porneste din nou prin dupa(), dar numai dupa ultima
			# biblioteca pe care o mai asteapta (mgcamd cere trei pachete, deci trei elemente in coada: o pornire dupa primul ar cadea)
			nume = []
			for cale, v in el["pluginuri"].items():
				if any(cale in x["pluginuri"] for x in _coada):
					continue
				nume.append(v["nume"])
				if callable(v.get("dupa")):
					try:
						v["dupa"]()
					except Exception as e:
						_jurnal("dupa %s: %r" % (cale, e))
			_jurnal("%s instalat; pornite din nou: %s" % (el["pachet"], ", ".join(sorted(set(nume))) or "-"))
			if nume:
				_mesaj(_t("Biblioteca %s s-a instalat; %s pornește din nou.") % (el["modul"], ", ".join(sorted(set(nume)))))
			return
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
	_lipsa[0] = None
	del _coada[:]
	_rezultat.clear()
	_pePlugin.clear()
	_stare.update(sesiune=None, pornit=False, ceas=None, lucrare=None, liste=False, esecuri_liste=0)
