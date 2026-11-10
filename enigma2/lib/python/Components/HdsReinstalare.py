# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsReinstalare.py: pachetele din copia setarilor puse din nou din feeduri, dupa o imagine noua, fara nimic de facut de
# om. Punerea la loc a copiei (Components/HdsCopieSetari.py, cu enigma2 oprit, inainte de interfata) nu poate instala
# din internet: reteaua poate sa nu fie gata, iar feedul pluginurilor externe al imaginii il scrie abia interfata
# (Components/HdsPluginuriExterne.py). Ea lasa numai coada, aici:
#   /home/root/hds-restaurare/de-reinstalat.json   {"pachete": [[nume, fel]], "legaturi": {rel: tinta}, "incercari",
#                                                  "boot", "puse", "lipsa", "nereusite"}
#   /home/root/hds-restaurare/config-acces/        configurarile modulelor de acces (etc/tuxbox/config), copiate
#                                                  octet cu octet la punere, fara sa fie citite
#   /home/root/hds-restaurare/pluginuri.tar.gz    datele extensiilor, validate integral, puse dupa instalarea lor;
#                                                  .ipk-ul salvat are prioritate fata de feed, afara de o copie de pe
#                                                  alta baza (semnul pluginuri-alta-baza): atunci feedul e primul
# fel: "acces" (pachetul unui modul de acces conditionat al copiei, cand copia e de pe alta baza a imaginii: binarele ei
# nu merg aici, deci nu se copiaza) sau "plugin" (un plugin instalat de om, din lista copiei).
# Dupa pornirea interfetei (porneste, din HdsCopieSetari.porneste) si dupa repornirea ceruta pentru retea, pe un fir
# separat: opkg update, apoi opkg install pe fiecare nume lipsa (intai modulele de acces), coada scrisa dupa fiecare
# pachet (o cadere de curent nu pierde nimic). Dupa modulele de acces: configurarile si legatura aleasa
# (/etc/init.d/<fel> -> <fel>.<x>) puse din nou peste ce a scris instalarea, apoi modulul ales pornit. La sfarsit
# pluginurile se reincarca, o singura repornire a interfetei daca vreun plugin o cere, si un mesaj scurt: ce s-a pus,
# ce nu exista pentru imaginea aceasta (numai dupa un opkg update reusit), ce nu s-a putut instala.
# Fara retea sau cu opkg ocupat: se reincearca la urmatoarea pornire a receptorului, de cel mult MAX_INCERCARI ori.
# Modulul nu importa nimic din enigma2 la incarcare (probele de pe PC il folosesc direct, cu parametrul rad).
import gzip
import json
import os
import re
import shutil
import subprocess
import time

COADA = "de-reinstalat.json"
REZULTAT = "reinstalare.json"
DOSAR_CONFIG = "config-acces"
CONFIG_ACCES = "etc/tuxbox/config"
FEL_ACCES = "acces"
FEL_PLUGIN = "plugin"
PREFIX_PLUGIN = "enigma2-plugin-"
TIPAR_PACHET = re.compile(r"^[a-z0-9][a-z0-9+.-]{1,120}$")
TIPAR_LEGATURA = re.compile(r"^etc/(init\.d/[A-Za-z][A-Za-z0-9_-]{0,31}|rc[0-6S]\.d/[SK][0-9]{2}[A-Za-z][A-Za-z0-9_-]{0,31})$")
INIT_D = "/etc/init.d/"
TIPAR_TINTA = re.compile(r"^(\.\./init\.d/|%s)?[A-Za-z][A-Za-z0-9._+-]{0,95}$" % re.escape(INIT_D))
MAX_INCERCARI = 5
MAX_PACHETE = 200
INTARZIERE_S = 60
TERMEN_UPDATE_S = 300
TERMEN_INSTALARE_S = 600


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsReinstalare] %s" % text)


def _c(rad, rel):
	return os.path.join(rad or "/", *rel.split("/"))


def dosar(rad="/"):
	return _c(rad, "home/root/hds-restaurare")


def _scrie_json(cale, date):
	nou = cale + ".nou"
	d = os.path.dirname(cale)
	if not os.path.isdir(d):
		os.makedirs(d)
	with open(nou, "w", encoding="ascii") as f:
		json.dump(date, f, ensure_ascii=True, indent=1, sort_keys=True)
		f.flush()
		os.fsync(f.fileno())
	os.replace(nou, cale)


def _citeste_json(cale):
	try:
		with open(cale, "r", encoding="ascii", errors="replace") as f:
			date = json.load(f)
		return date if isinstance(date, dict) else None
	except (OSError, IOError, ValueError):
		return None


def _boot_id(rad):
	try:
		with open(_c(rad, "proc/sys/kernel/random/boot_id"), "r") as f:
			return f.read(64).strip()
	except (OSError, IOError):
		return ""


# ---------------------------------------------------------------- starea opkg

def _strofe(rad):
	try:
		with open(_c(rad, "var/lib/opkg/status"), "r", encoding="utf-8", errors="replace") as f:
			text = f.read(8 * 1024 * 1024)
	except (OSError, IOError):
		return []
	rez = []
	for strofa in re.split(r"\n\s*\n", text):
		campuri = {}
		for rand in strofa.splitlines():
			if ":" in rand and rand[:1] not in " \t":
				k, v = rand.split(":", 1)
				campuri[k.strip().lower()] = v.strip()
		if campuri.get("package"):
			rez.append(campuri)
	return rez


def _instalat(campuri):
	stare = campuri.get("status", "").split()
	return "installed" in stare and "not-installed" not in stare


def instalate(rad="/"):
	return set(c["package"] for c in _strofe(rad) if _instalat(c))


def pluginuri_puse_de_om(rad="/", exclus=()):
	"""Pluginurile (enigma2-plugin-*) instalate de om: instalate, nu ca dependente (Auto-Installed), cu alta ora de
	instalare decat a pachetelor imaginii (toate pachetele unei imagini scrise au aceeasi ora, cea a constructiei:
	cea mai des intalnita). `exclus`: nume de lasat afara (pachetele modulelor de acces, care au copia lor)."""
	strofe = [c for c in _strofe(rad) if _instalat(c)]
	ore = {}
	for c in strofe:
		t = c.get("installed-time", "")
		ore[t] = ore.get(t, 0) + 1
	ora_imaginii = max(ore, key=lambda t: ore[t]) if ore else ""
	rez = []
	for c in strofe:
		n = c["package"]
		if not n.startswith(PREFIX_PLUGIN) or not TIPAR_PACHET.match(n) or n in exclus:
			continue
		if c.get("auto-installed", "").lower() == "yes":
			continue
		if len(strofe) > 1 and c.get("installed-time", "") == ora_imaginii:
			continue
		rez.append(n)
	return sorted(set(rez))[:MAX_PACHETE]


def _in_liste(rad):
	"""Numele pachetelor din listele descarcate de opkg (lists_dir din /etc/opkg, implicit /var/lib/opkg/lists)."""
	lists = "var/lib/opkg/lists"
	try:
		from Components import HdsPachete as P
	except ImportError:
		try:
			import HdsPachete as P
		except ImportError:
			P = None
	if P is not None:
		try:
			lists = P.citeste_configurarea(rad).lists_dir.lstrip("/")
		except Exception:
			pass
	nume = set()
	d = _c(rad, lists)
	try:
		fisiere = sorted(os.listdir(d))
	except OSError:
		return nume
	for n in fisiere:
		cale = os.path.join(d, n)
		if not os.path.isfile(cale):
			continue
		try:
			with open(cale, "rb") as f:
				date = f.read(64 * 1024 * 1024)
			if date[:2] == b"\x1f\x8b":
				date = gzip.decompress(date)
		except (OSError, IOError, EOFError, ValueError):
			continue
		nume.update(re.findall(r"^Package:\s*(\S+)", date.decode("utf-8", "replace"), re.M))
	return nume


# ---------------------------------------------------------------- coada (scrisa de punerea la loc, fara retea)

def citeste(rad="/"):
	return _citeste_json(os.path.join(dosar(rad), COADA))


def adauga(rad, pachete, legaturi=None):
	"""Pune in coada [(nume, fel)] (fara dubluri) si legaturile alese ale modulelor; la fel FEL_ACCES copiaza octet cu
	octet configurarile modulelor (CONFIG_ACCES) in DOSAR_CONFIG, ca sa fie puse din nou dupa instalare. Intoarce
	cate nume noi au intrat."""
	rad = rad or "/"
	coada = citeste(rad) or {}
	lista = [list(p) for p in coada.get("pachete", []) if isinstance(p, list) and len(p) == 2]
	vazute = set(p[0] for p in lista)
	noi = 0
	for nume, fel in pachete:
		if fel in (FEL_ACCES, FEL_PLUGIN) and TIPAR_PACHET.match(nume or "") and nume not in vazute \
				and len(lista) < MAX_PACHETE:
			lista.append([nume, fel])
			vazute.add(nume)
			noi += 1
	leg = dict(coada.get("legaturi") or {})
	for rel, tinta in (legaturi or {}).items():
		if TIPAR_LEGATURA.match(rel) and TIPAR_TINTA.match(tinta or ""):
			leg[rel] = tinta
	if not lista:
		return 0
	coada.update(pachete=lista, legaturi=leg)
	coada["feluri"] = dict(coada.get("feluri") or {}, **dict(lista))
	coada.setdefault("incercari", 0)
	coada.setdefault("boot", "")
	for k in ("puse", "lipsa", "nereusite", "ipk_lipsa"):
		coada.setdefault(k, [])
	if any(f == FEL_ACCES for _n, f in lista):
		_pastreaza_config(rad)
	_scrie_json(os.path.join(dosar(rad), COADA), coada)
	return noi


def _pastreaza_config(rad):
	"""etc/tuxbox/config -> DOSAR_CONFIG, fisier cu fisier, ca atare (shutil.copyfile; nimic nu e deschis ca text)."""
	sursa = _c(rad, CONFIG_ACCES)
	tinta = os.path.join(dosar(rad), DOSAR_CONFIG)
	shutil.rmtree(tinta, ignore_errors=True)
	if not os.path.isdir(sursa) or os.path.islink(sursa):
		return 0
	n = 0
	for d, dosare, fisiere in os.walk(sursa):
		dosare[:] = [x for x in dosare if not os.path.islink(os.path.join(d, x))]
		rel = os.path.relpath(d, sursa)
		for f in fisiere:
			c = os.path.join(d, f)
			if os.path.isfile(c) and not os.path.islink(c):
				t = os.path.join(tinta, rel, f)
				if not os.path.isdir(os.path.dirname(t)):
					os.makedirs(os.path.dirname(t))
				shutil.copyfile(c, t)
				shutil.copymode(c, t)
				n += 1
	return n


def _pune_config_inapoi(rad):
	"""DOSAR_CONFIG -> etc/tuxbox/config, peste ce a scris instalarea (numai fisierele care difera, comparate octet cu
	octet de filecmp, fara interpretare). Intoarce cate fisiere au fost puse."""
	import filecmp
	sursa = os.path.join(dosar(rad), DOSAR_CONFIG)
	tinta = _c(rad, CONFIG_ACCES)
	n = 0
	for d, _dosare, fisiere in os.walk(sursa):
		rel = os.path.relpath(d, sursa)
		for f in fisiere:
			c = os.path.join(d, f)
			t = os.path.normpath(os.path.join(tinta, rel, f))
			if os.path.islink(t):
				continue
			if os.path.isfile(t) and filecmp.cmp(c, t, shallow=False):
				continue
			if not os.path.isdir(os.path.dirname(t)):
				os.makedirs(os.path.dirname(t))
			nou = t + ".hds-nou"
			shutil.copyfile(c, nou)
			shutil.copymode(c, nou)
			os.replace(nou, t)
			n += 1
	return n


def _pune_legaturile(rad, legaturi):
	n = 0
	for rel, tinta in sorted((legaturi or {}).items()):
		if not TIPAR_LEGATURA.match(rel) or not TIPAR_TINTA.match(tinta or ""):
			continue
		cale = _c(rad, rel)
		if os.path.lexists(cale) and not os.path.islink(cale):
			continue
		try:
			if os.path.islink(cale) and os.readlink(cale) == tinta:
				continue
			nou = cale + ".hds-nou"
			if os.path.lexists(nou):
				os.remove(nou)
			os.symlink(tinta, nou)
			os.replace(nou, cale)
			n += 1
		except (OSError, NotImplementedError, AttributeError):
			continue
	return n


# ---------------------------------------------------------------- lucrul (pe un fir separat, dupa pornirea interfetei)

def _opkg(rad, opkg):
	if opkg:
		return list(opkg)
	cale = os.environ.get("HDS_OPKG") or _c(rad, "usr/bin/opkg")
	return [cale] if os.path.isfile(cale) else None


def _ruleaza(comanda, termen):
	try:
		r = subprocess.run(comanda, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=termen)
		return r.returncode
	except Exception:
		return -1


def _copie():
	try:
		from Components import HdsCopieSetari as C
	except ImportError:
		import HdsCopieSetari as C
	return C


def _reinstaleaza_plugin(rad, nume, comanda, disponibile, actualizat, ultima, acum):
	"""Datele omului vin dupa instalare, inclusiv cand extensia exista deja."""
	try:
		instalat = nume in acum
		C = _copie()
		# dintr-o copie de pe alta baza a imaginii pachetul vine intai din feed (facut pentru baza de acum); .ipk-ul
		# salvat numai cand feedul nu-l are, si numai daca nu are programe facute pentru baza veche (ipk_din_copie)
		din_feed = nume in disponibile and getattr(C, "pluginuri_de_pe_alta_baza", lambda _r: False)(rad)
		local = None if instalat or din_feed else getattr(C, "ipk_din_copie", lambda _r, _n: None)(rad, nume)
		if not instalat and not local and nume not in disponibile:
			return ("lipsa" if actualizat else "nereusite" if ultima else "amanat"), False
		if not instalat and (comanda is None or _ruleaza(comanda + ["install", local or nume], TERMEN_INSTALARE_S) != 0):
			return ("nereusite" if ultima else "amanat"), False
		n = getattr(C, "pune_date_plugin", lambda _r, _n: 0)(rad, nume)
		return "gata", not instalat or bool(n)
	except Exception as eroare:
		_jurnal("datele extensiei %s: %s" % (nume, eroare.__class__.__name__))
		return ("nereusite" if ultima else "amanat"), False


def lucreaza(rad="/", opkg=None, porneste_modulul=None):
	"""Lucreaza coada. Intoarce None (nimic de facut), {"stare": "amanat"} (fara retea sau opkg ocupat: se reincearca
	la pornirea urmatoare) sau rezultatul final {"stare": "gata", "puse", "lipsa", "nereusite", "acces", "pluginuri"}
	(scris si in REZULTAT, pentru mesaj; coada si copia configurarilor se sterg)."""
	rad = rad or "/"
	cale = os.path.join(dosar(rad), COADA)
	coada = citeste(rad)
	if not coada or not coada.get("pachete"):
		return None
	comanda = _opkg(rad, opkg)
	boot = _boot_id(rad)
	if boot != coada.get("boot") or not boot:
		coada["incercari"] = int(coada.get("incercari") or 0) + 1
		coada["boot"] = boot
	_scrie_json(cale, coada)
	ultima = coada["incercari"] >= MAX_INCERCARI
	coada.setdefault("ipk_lipsa", [])
	coada.setdefault("feluri", dict(coada["pachete"]))
	actualizat = comanda is not None and _ruleaza(comanda + ["update"], TERMEN_UPDATE_S) == 0
	disponibile = _in_liste(rad)
	acum = instalate(rad)
	pachete = sorted(coada["pachete"], key=lambda p: 0 if p[1] == FEL_ACCES else 1)
	amanate = []
	acces_puse = 0
	for nume, fel in pachete:
		if fel == FEL_PLUGIN:
			stare, schimbat = _reinstaleaza_plugin(rad, nume, comanda, disponibile, actualizat, ultima, acum)
			if stare == "gata":
				if schimbat and nume not in coada["puse"]:
					coada["puse"].append(nume)
			elif stare == "amanat":
				amanate.append([nume, fel])
			else:
				if nume not in coada[stare]:
					coada[stare].append(nume)
				if stare == "lipsa" and nume not in coada["ipk_lipsa"]:
					coada["ipk_lipsa"].append(nume)
		elif nume in acum:
			if fel == FEL_ACCES:
				acces_puse += 1
		elif nume not in disponibile:
			# „nu exista” numai dupa o lista adusa acum; altfel poate fi o problema de retea
			if actualizat:
				coada["lipsa"].append(nume)
			elif ultima:
				coada["nereusite"].append(nume)
			else:
				amanate.append([nume, fel])
		elif comanda is not None and _ruleaza(comanda + ["install", nume], TERMEN_INSTALARE_S) == 0:
			coada["puse"].append(nume)
			if fel == FEL_ACCES:
				acces_puse += 1
		elif ultima:
			coada["nereusite"].append(nume)
		else:
			amanate.append([nume, fel])
		coada["pachete"] = [p for p in coada["pachete"] if p[0] != nume]
		_scrie_json(cale, dict(coada, pachete=coada["pachete"] + amanate))
	if acces_puse or coada.get("legaturi"):
		try:
			n = _pune_config_inapoi(rad)
			m = _pune_legaturile(rad, coada.get("legaturi"))
			_jurnal("modulele de acces: %d fisiere de configurare si %d legaturi puse din nou dupa instalare" % (n, m))
		except Exception as eroare:
			_jurnal("configurarile modulelor: %s" % eroare.__class__.__name__)
		if acces_puse and porneste_modulul is not None:
			try:
				porneste_modulul(rad)
			except Exception as eroare:
				_jurnal("pornirea modulului: %s" % eroare.__class__.__name__)
	if amanate:
		coada["pachete"] = amanate
		_scrie_json(cale, coada)
		_jurnal("raman %d pachete pentru pornirea urmatoare" % len(amanate))
		return {"stare": "amanat"}
	feluri = coada["feluri"]
	rez = {"stare": "gata", "puse": coada["puse"], "lipsa": coada["lipsa"], "nereusite": coada["nereusite"],
		"ipk_lipsa": coada["ipk_lipsa"],
		"pluginuri": [n for n in coada["puse"] if feluri.get(n) == FEL_PLUGIN], "cand": int(time.time()),
		"aratat": False}
	_scrie_json(os.path.join(dosar(rad), REZULTAT), rez)
	try:
		os.remove(cale)
	except OSError:
		pass
	shutil.rmtree(os.path.join(dosar(rad), DOSAR_CONFIG), ignore_errors=True)
	_jurnal("gata: puse %d, nu exista pentru imaginea aceasta %d, nereusite %d" % (len(rez["puse"]), len(rez["lipsa"]),
		len(rez["nereusite"])))
	return rez


def _scurt(nume):
	"""Numele aratat: fara enigma2-plugin-<categorie>-"""
	if nume.startswith(PREFIX_PLUGIN):
		rest = nume[len(PREFIX_PLUGIN):]
		return rest.split("-", 1)[1] if "-" in rest else rest
	return nume


def nota_coada(rad="/"):
	"""Nota din mesajul punerii la loc cand coada are ceva; „” altfel."""
	return _("Pluginurile și modulele de acces se pun din nou din internet sau din copie, cu setările lor.") if citeste(rad) else ""


def randuri_mesaj(rez):
	"""Cate un rand pentru fiecare fel de rezultat, cu felul lui: [(succes / avertisment / eroare, text)]."""
	randuri = []
	if rez.get("puse"):
		randuri.append(("succes", _("Pluginurile din copia setărilor, puse din nou: %s.") % ", ".join(_scurt(n) for n in rez["puse"])))
	if rez.get("lipsa"):
		randuri.append(("avertisment", _("Nu există încă pentru imaginea aceasta: %s.") % ", ".join(_scurt(n) for n in rez["lipsa"])))
	if rez.get("ipk_lipsa"):
		randuri.append(("avertisment", _("Lipsește și fișierul .ipk din copie pentru: %s.") % ", ".join(_scurt(n) for n in rez["ipk_lipsa"])))
	if rez.get("nereusite"):
		randuri.append(("eroare", _("Nu s-au putut instala acum: %s.") % ", ".join(_scurt(n) for n in rez["nereusite"])))
	return randuri


def mesaj(rez):
	"""Textul scurt de pe ecran dupa lucru; gol cand nu e nimic de spus."""
	return "\n".join(t for _f, t in randuri_mesaj(rez))


def fereastra(rez, nota=None):
	"""Ce primeste MessageBox dupa reinstalare: randurile, fara paragraf, iar felul ferestrei e cel mai rau dintre ele."""
	randuri = randuri_mesaj(rez)
	felurile = [f for f, _t in randuri]
	fel = "eroare" if "eroare" in felurile else "avertisment" if "avertisment" in felurile else "succes"
	return {"text": "", "titlu": _("Copia setărilor"), "fel": fel, "puncte": randuri + ([("nota", nota)] if nota else [])}


# ---------------------------------------------------------------- pe receptor

_VII = []


def porneste(session, rezultat_copie=None):
	"""Din HdsCopieSetari.porneste: dupa INTARZIERE_S (reteaua si feedul extern scris de mytest.py), lucrul pe un fir
	separat; nimic daca punerea la loc tocmai a cerut repornirea pentru retea (coada asteapta pornirea urmatoare)."""
	if rezultat_copie and rezultat_copie.get("repornire") == "ceruta":
		return
	_arata(session)
	if not citeste() or _VII:
		return
	from enigma import eTimer
	ceas = eTimer()

	def incepe():
		from Components.HdsCopieSetari import _porneste_modulul
		from Components.HdsImportSurse import Lucrare
		_VII.append(Lucrare(lambda: lucreaza("/", porneste_modulul=_porneste_modulul),
			lambda rez, eroare: _gata(session, rez, eroare)))
	try:
		ceas._legatura = ceas.timeout.connect(incepe)
	except AttributeError:
		ceas.callback.append(incepe)
	ceas.start(INTARZIERE_S * 1000, True)
	_VII.append(ceas)


def _gata(session, rez, eroare):
	del _VII[:]
	if eroare:
		_jurnal("lucrul s-a oprit: %s" % eroare)
		return
	if rez and rez.get("stare") == "gata":
		_arata(session)


def _arata(session):
	cale = os.path.join(dosar("/"), REZULTAT)
	rez = _citeste_json(cale)
	if not rez or rez.get("aratat"):
		return
	rez["aratat"] = True
	_scrie_json(cale, rez)
	repornire = False
	if rez.get("pluginuri"):
		try:
			from Components.HdsExtensiiLucru import reincarcaPluginuri
			repornire = reincarcaPluginuri()
		except Exception as eroare:
			_jurnal("reincarcarea pluginurilor: %s" % eroare.__class__.__name__)
	if not mesaj(rez):
		return
	from Tools import Notifications
	from Screens.MessageBox import MessageBox
	if repornire:
		f = fereastra(rez, _("Interfața repornește o dată acum, ca pluginurile noi să se încarce."))

		def reporneste(*_a):
			from Screens.Standby import TryQuitMainloop
			session.open(TryQuitMainloop, 3)
		Notifications.AddNotificationWithCallback(reporneste, MessageBox, f.pop("text"), type=MessageBox.TYPE_INFO, timeout=15, **f)
		return
	f = fereastra(rez)
	Notifications.AddPopup(f.pop("text"), MessageBox.TYPE_INFO, 20, "HdsReinstalare", **f)
