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
import threading
import time

COADA = "de-reinstalat.json"
REZULTAT = "reinstalare.json"
DOSAR_CONFIG = "config-acces"
CONFIG_ACCES = "etc/tuxbox/config"
FEL_ACCES = "acces"
# 0.7.6 (RSC): modulul pe care copia il are numai prin configurarile lui (etc/tuxbox/config/<modul>.*), fara pachet: nu se
# instaleaza singur (poate l-a scos omul), ci se intreaba, cu Da, cand feedul il are
FEL_ACCES_INTREBARE = "acces-intrebare"
FEL_PLUGIN = "plugin"
PREFIX_PLUGIN = "enigma2-plugin-"
# 0.7.6 (RSC, asistenta 430032): pachetul unui modul de acces din copie se cauta in feed si dupa numele lui la noi
# (pachet_din_feed): copia poate avea un modul pus din alt feed sau de un panou, cu alt nume pentru acelasi modul.
# Fara niciun nume de modul scris aici (ca HdsImportExtra): pachetele modulelor se recunosc dupa categorie
# (enigma2-plugin-<categorie>-<rest>, categoria de forma TIPAR_CATEGORIE_ACCES, ca HdsPachete), modulul dupa cuvant.
TIPAR_CATEGORIE_ACCES = re.compile(r"^[a-z]+cams$")
TIPAR_CUVANT_MODUL = re.compile(r"cams?d?[0-9]*$")   # ca HdsCopieSetari._nume_de_modul
# inceputul numelui unui pachet de modul din alt feed: [enigma2-[plugin-]]<categorie, la singular sau plural>-
TIPAR_INCEPUT_STRAIN = re.compile(r"^(?:enigma2-(?:plugin-)?)?[a-z]+cams?-")
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


def rest_acces(nume):
	"""<rest> din enigma2-plugin-<categorie>-<rest> cand categoria e a modulelor de acces; "" altfel."""
	parti = (nume or "").split("-")
	if len(parti) > 3 and nume.startswith(PREFIX_PLUGIN) and TIPAR_CATEGORIE_ACCES.match(parti[2]):
		return "-".join(parti[3:])
	return ""


def familie_modul(nume):
	"""Numele modulului din numele unui pachet sau al unui fisier de configurare: ultimul cuvant terminat in cam, cams
	sau camd (cu cifre sau nu) care nu e categoria (forma TIPAR_CATEGORIE_ACCES); "" cand nu are. Fara lista de nume."""
	gasit = ""
	for cuvant in re.split(r"[^a-z0-9]+", (nume or "").lower()):
		if cuvant and TIPAR_CUVANT_MODUL.search(cuvant) and not TIPAR_CATEGORIE_ACCES.match(cuvant):
			gasit = cuvant
	return gasit


def pachet_din_feed(nume, disponibile, familie=True):
	"""Pachetul din `disponibile` pentru modulul de acces `nume` din copie (un nume de pachet sau numai numele
	modulului), sau None: acelasi nume; pachetul nostru cu acelasi rest (<categorie straina>-<rest> ->
	enigma2-plugin-<categoria noastra>-<rest>); apoi, cu `familie`, pachetul nostru al aceluiasi modul (restul egal cu
	modulul, altfel primul rest <modul>-*)."""
	if not nume:
		return None
	if nume in disponibile:
		return nume
	ale_noastre = {}
	for n in disponibile:
		r = rest_acces(n)
		if r:
			ale_noastre.setdefault(r, []).append(n)
	m = TIPAR_INCEPUT_STRAIN.match(nume)
	rest = rest_acces(nume) or (nume[m.end():] if m else "")
	if rest and rest in ale_noastre:
		return sorted(ale_noastre[rest])[0]
	if not familie:
		return None
	modul = familie_modul(nume)
	if not modul:
		return None
	if modul in ale_noastre:
		return sorted(ale_noastre[modul])[0]
	rude = sorted(n for r, lista in ale_noastre.items() if r.startswith(modul + "-") for n in lista)
	return rude[0] if rude else None


def tinta_acces(nume, acum, disponibile):
	"""Ce pachet pune modulul `nume` din copie: acelasi pachet (instalat sau din feed, si sub numele nostru), altfel
	ruda lui (acelasi modul) deja instalata, altfel ruda din feed, altfel el."""
	return (pachet_din_feed(nume, acum, False) or pachet_din_feed(nume, disponibile, False)
		or pachet_din_feed(nume, acum) or pachet_din_feed(nume, disponibile) or nume)


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
		if fel in (FEL_ACCES, FEL_ACCES_INTREBARE, FEL_PLUGIN) and TIPAR_PACHET.match(nume or "") and nume not in vazute \
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
	if any(f in (FEL_ACCES, FEL_ACCES_INTREBARE) for _n, f in lista):
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


TIPAR_SCRIPT_PACHET = re.compile(r"^/?etc/init\.d/([A-Za-z][A-Za-z0-9_-]{0,31})\.([A-Za-z0-9][A-Za-z0-9._+-]{0,63})$")
SUFIX_GOL = "None"

# Comun cu alegerea manuala; numai operatii de disc pe firele de lucru.
_ZAVOR_ALEGERI = threading.RLock()
_ALEGERI = {}


def _semn_alegere(cale):
	try:
		tinta = os.readlink(cale) if os.path.islink(cale) else ""
		try:
			s = os.lstat(cale)
			semn = (s.st_dev, s.st_ino, s.st_mtime_ns)
		except OSError:
			semn = None
		return tinta, semn, _ALEGERI.get(os.path.abspath(cale), 0)
	except OSError:
		return None, None, _ALEGERI.get(os.path.abspath(cale), 0)


def _alegeri_acum(rad, legaturi):
	"""Snapshot inainte de opkg; include si felurile absente din copia veche."""
	with _ZAVOR_ALEGERI:
		relative = {r for r in (legaturi or {}) if TIPAR_LEGATURA.match(r)}
		try:
			relative.update("etc/init.d/" + n for n in os.listdir(_c(rad, "etc/init.d"))
				if TIPAR_LEGATURA.match("etc/init.d/" + n) and os.path.islink(_c(rad, "etc/init.d/" + n))
				and os.path.basename(os.readlink(_c(rad, "etc/init.d/" + n))).startswith(n + "."))
		except OSError:
			pass
		return {_c(rad, r): _semn_alegere(_c(rad, r)) for r in relative}


def _pastreaza_alegerea(cale, alegeri, tinta=None):
	if alegeri is None:
		return False
	# Apelantul tine zavorul pana dupa inlocuirea atomica.
	acum = _semn_alegere(cale)
	if cale in alegeri and acum != alegeri[cale]:
		return True
	if _ALEGERI.get(os.path.abspath(cale), 0):
		return True
	ales = acum[0] or ""
	if ales.endswith("." + SUFIX_GOL) and os.path.basename(os.path.dirname(cale)) == "init.d":
		try:
			from Components.HdsModuleAcces import SEMN_NICIUNUL
		except ImportError:
			from HdsModuleAcces import SEMN_NICIUNUL
		rad = os.path.dirname(os.path.dirname(os.path.dirname(cale)))
		if os.path.exists(_c(rad, SEMN_NICIUNUL.lstrip("/") + os.path.basename(cale))):
			return True
	return bool(ales and not ales.endswith("." + SUFIX_GOL)
		and ales != tinta and os.path.isfile(os.path.join(os.path.dirname(cale), os.path.basename(ales))))


def alege_scriptul(rad, pachet, alegeri=None):
	"""0.7.6 (RSC): legatura aleasa a felului (etc/init.d/<fel>) spre scriptul <fel>.<x> al pachetului pus acum, numai
	cand felul n-are inca un script ales care exista (lipsa, locul gol <fel>.None sau un script care nu mai e): un
	modul pus din feed sub numele nostru are alt script decat cel din copie, iar pachetul nu alege singur. Intoarce
	cate legaturi a pus."""
	n = 0
	try:
		with open(_c(rad, "var/lib/opkg/info/%s.list" % pachet), "r", encoding="utf-8", errors="replace") as f:
			randuri = f.read(256 * 1024).splitlines()
	except (OSError, IOError):
		return 0
	for rand in randuri:
		m = TIPAR_SCRIPT_PACHET.match(rand.split("\t", 1)[0].strip())
		if not m or m.group(2) == SUFIX_GOL or not os.path.isfile(_c(rad, "etc/init.d/%s.%s" % m.groups())):
			continue
		cale = _c(rad, "etc/init.d/" + m.group(1))
		with _ZAVOR_ALEGERI:
			if _pastreaza_alegerea(cale, alegeri):
				continue
			n += _alege_scriptul_la_scriere(rad, cale, m)
	return n


def _alege_scriptul_la_scriere(rad, cale, m):
	"""Sub zavor: verificarea si scrierea sunt aceeasi operatie."""
	try:
		if os.path.lexists(cale) and not os.path.islink(cale):
			return 0
		tinta = os.readlink(cale) if os.path.islink(cale) else ""
		if tinta and not tinta.endswith("." + SUFIX_GOL) and os.path.isfile(_c(rad, "etc/init.d/" + os.path.basename(tinta))):
			return 0
		nou = cale + ".hds-nou"
		if os.path.lexists(nou):
			os.remove(nou)
		os.symlink("%s.%s" % m.groups(), nou)
		os.replace(nou, cale)
		return 1
	except (OSError, NotImplementedError, AttributeError):
		return 0


def _pune_legaturile(rad, legaturi, alegeri=None):
	"""Legaturile alese puse din nou. Legatura aleasa a unui fel (etc/init.d/<fel>) numai spre un script care exista
	acum: un pachet care nu s-a instalat (nu exista in feed, sau scriptul lui are alt nume aici) nu lasa o legatura
	spre nimic, iar alegerea de dinainte ramane."""
	n = 0
	for rel, tinta in sorted((legaturi or {}).items()):
		if not TIPAR_LEGATURA.match(rel) or not TIPAR_TINTA.match(tinta or ""):
			continue
		if rel.startswith("etc/init.d/") and not os.path.isfile(_c(rad, "etc/init.d/" + os.path.basename(tinta))):
			continue
		cale = _c(rad, rel)
		with _ZAVOR_ALEGERI:
			if _pastreaza_alegerea(cale, alegeri, tinta):
				continue
			n += _pune_legatura_la_scriere(cale, tinta)
	return n


def _pune_legatura_la_scriere(cale, tinta):
	"""Inlocuire atomica sub acelasi zavor ca alegerea manuala."""
	try:
		if os.path.lexists(cale) and not os.path.islink(cale):
			return 0
		if os.path.islink(cale) and os.readlink(cale) == tinta:
			return 0
		nou = cale + ".hds-nou"
		if os.path.lexists(nou):
			os.remove(nou)
		os.symlink(tinta, nou)
		os.replace(nou, cale)
		return 1
	except (OSError, NotImplementedError, AttributeError):
		return 0


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
	alegeri = _alegeri_acum(rad, coada.get("legaturi"))
	comanda = _opkg(rad, opkg)
	boot = _boot_id(rad)
	if boot != coada.get("boot") or not boot:
		coada["incercari"] = int(coada.get("incercari") or 0) + 1
		coada["boot"] = boot
	_scrie_json(cale, coada)
	ultima = coada["incercari"] >= MAX_INCERCARI
	coada.setdefault("ipk_lipsa", [])
	coada.setdefault("feluri", dict(coada["pachete"]))
	actualizat = comanda is not None and _ruleaza(comanda + _argumenteUpdate(rad), TERMEN_UPDATE_S) == 0
	disponibile = _in_liste(rad)
	acum = instalate(rad)
	pachete = sorted(coada["pachete"], key=lambda p: 0 if p[1] == FEL_ACCES else 1)
	amanate = []
	acces_puse = 0
	acces_noi = []
	for nume, fel in pachete:
		if fel == FEL_ACCES_INTREBARE:
			# numai intrebarea (rez["acces_de_pus"]), cand modulul nu e pe receptor si feedul il are
			# orice pachet al aceluiasi modul deja instalat ajunge (copia stia numai configurarile, nu pachetul)
			tinta = pachet_din_feed(nume, acum) or tinta_acces(nume, acum, disponibile)
			if tinta in acum:
				pass
			elif tinta in disponibile:
				coada.setdefault("de_intrebat", [])
				if nume not in coada["de_intrebat"]:
					coada["de_intrebat"].append(nume)
			elif not actualizat and not ultima:
				amanate.append([nume, fel])
		elif fel == FEL_PLUGIN:
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
		elif tinta_acces(nume, acum, disponibile) in acum:
			acces_puse += 1
		elif tinta_acces(nume, acum, disponibile) not in disponibile:
			# „nu exista” numai dupa o lista adusa acum; altfel poate fi o problema de retea
			if actualizat:
				coada["lipsa"].append(nume)
			elif ultima:
				coada["nereusite"].append(nume)
			else:
				amanate.append([nume, fel])
		elif comanda is not None and _ruleaza(comanda + ["install", tinta_acces(nume, acum, disponibile)],
				TERMEN_INSTALARE_S) == 0:
			tinta = tinta_acces(nume, acum, disponibile)
			if tinta != nume:
				_jurnal("modulul de acces din copie %s: pus din feed ca %s" % (nume, tinta))
				coada.setdefault("inlocuite", {})[nume] = tinta
			coada["puse"].append(tinta)
			acces_noi.append(tinta)
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
			m = _pune_legaturile(rad, coada.get("legaturi"), alegeri)
			m += sum(alege_scriptul(rad, x, alegeri) for x in acces_noi)
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
	# modulele de acces din copie care nu sunt pe receptor: cele care exista (sau pot exista) in feed se pun la un Da
	# (intrebarea de pe televizor si butonul din pagina web, pune_modulele); cele pe care feedul nu le are, numai spuse
	rez["acces_de_pus"] = [n for n in coada["nereusite"] if feluri.get(n) == FEL_ACCES] + [n for n in
		coada.get("de_intrebat") or [] if n not in coada["nereusite"]]
	rez["acces_lipsa"] = [n for n in coada["lipsa"] if feluri.get(n) == FEL_ACCES]
	if coada.get("inlocuite"):
		rez["inlocuite"] = coada["inlocuite"]
	if rez["acces_de_pus"]:
		rez["legaturi"] = coada.get("legaturi") or {}
	_scrie_json(os.path.join(dosar(rad), REZULTAT), rez)
	try:
		os.remove(cale)
	except OSError:
		pass
	if not rez["acces_de_pus"]:
		# configurarile pastrate raman pentru Da: instalarea de atunci le pune din nou peste ce scrie pachetul
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
	acces_lipsa = set(rez.get("acces_lipsa") or [])
	acces_de_pus = set(rez.get("acces_de_pus") or [])
	lipsa = [n for n in rez.get("lipsa") or [] if n not in acces_lipsa]
	nereusite = [n for n in rez.get("nereusite") or [] if n not in acces_de_pus]
	if rez.get("puse"):
		randuri.append(("succes", _("Pluginurile din copia setărilor, puse din nou: %s.") % ", ".join(_scurt(n) for n in rez["puse"])))
	if acces_de_pus:
		randuri.append(("eroare", _("Modulul de acces din copie nu e instalat încă: %s.") % ", ".join(
			_scurt(n) for n in rez["acces_de_pus"])))
	if acces_lipsa:
		randuri.append(("avertisment", _("Modulul de acces din copie nu există pentru imaginea aceasta: %s. Setările lui au "
			"rămas pe receptor.") % ", ".join(_scurt(n) for n in rez["acces_lipsa"])))
	if lipsa:
		randuri.append(("avertisment", _("Nu există încă pentru imaginea aceasta: %s.") % ", ".join(_scurt(n) for n in lipsa)))
	if rez.get("ipk_lipsa"):
		randuri.append(("avertisment", _("Lipsește și fișierul .ipk din copie pentru: %s.") % ", ".join(_scurt(n) for n in rez["ipk_lipsa"])))
	if nereusite:
		randuri.append(("eroare", _("Nu s-au putut instala acum: %s.") % ", ".join(_scurt(n) for n in nereusite)))
	return randuri


# ---------------------------------------------------------------- modulele de acces din copie, puse la un Da (0.7.6, RSC)

def module_de_pus(rad="/"):
	"""Modulele de acces din copie care nu s-au putut instala (reinstalarea s-a incheiat fara ele, dar feedul le poate
	avea): numele din copie; [] fara."""
	rez = _citeste_json(os.path.join(dosar(rad), REZULTAT)) or {}
	return [n for n in rez.get("acces_de_pus") or [] if isinstance(n, str) and TIPAR_PACHET.match(n)]


def intrebare_module(nume):
	"""Intrebarea de pe televizor si din pagina web pentru modulele din `nume`; "" fara."""
	if not nume:
		return ""
	scurte = ", ".join(_scurt(n) for n in nume)
	if len(nume) == 1:
		return _("Modulul %s din copie nu e instalat. Îl pun acum?") % scurte
	return _("Modulele %s din copie nu sunt instalate. Le pun acum?") % scurte


def pune_modulele(rad="/", opkg=None, porneste_modulul=None):
	"""Raspunsul Da: opkg update, apoi fiecare modul din module_de_pus din feed (acelasi nume sau al nostru, tinta_acces),
	configurarile pastrate puse din nou peste ce a scris instalarea, legaturile alese si modulul pornit. Rezultatul
	reinstalarii se aduce la zi (televizorul si pagina web citesc acelasi fisier). Intoarce {"puse", "nereusite",
	"lipsa"} (numele din copie; la puse numele pachetului pus)."""
	rad = rad or "/"
	cale_rez = os.path.join(dosar(rad), REZULTAT)
	rez = _citeste_json(cale_rez) or {}
	de_pus = module_de_pus(rad)
	r = {"puse": [], "nereusite": [], "lipsa": []}
	if not de_pus:
		return r
	alegeri = _alegeri_acum(rad, rez.get("legaturi"))
	comanda = _opkg(rad, opkg)
	actualizat = comanda is not None and _ruleaza(comanda + _argumenteUpdate(rad), TERMEN_UPDATE_S) == 0
	disponibile = _in_liste(rad)
	acum = instalate(rad)
	inlocuite = dict(rez.get("inlocuite") or {})
	for nume in de_pus:
		tinta = tinta_acces(nume, acum, disponibile)
		if tinta in acum:
			r["puse"].append(tinta)
		elif tinta not in disponibile:
			r["lipsa" if actualizat else "nereusite"].append(nume)
			continue
		elif comanda is not None and _ruleaza(comanda + ["install", tinta], TERMEN_INSTALARE_S) == 0:
			r["puse"].append(tinta)
		else:
			r["nereusite"].append(nume)
			continue
		if tinta != nume:
			inlocuite[nume] = tinta
	if r["puse"]:
		with _ZAVOR_ALEGERI:
			r["alegere_pastrata"] = any(_pastreaza_alegerea(c, alegeri,
				(rez.get("legaturi") or {}).get(os.path.relpath(c, rad).replace(os.sep, "/"))) for c in alegeri
				if os.path.dirname(c) == _c(rad, "etc/init.d"))
		try:
			n = _pune_config_inapoi(rad)
			m = _pune_legaturile(rad, rez.get("legaturi"), alegeri)
			m += sum(alege_scriptul(rad, x, alegeri) for x in r["puse"])
			_jurnal("modulele de acces puse la cerere: %s; %d fisiere de configurare si %d legaturi puse din nou" % (
				", ".join(r["puse"]), n, m))
		except Exception as eroare:
			_jurnal("configurarile modulelor: %s" % eroare.__class__.__name__)
		if porneste_modulul is not None and not r["alegere_pastrata"]:
			try:
				porneste_modulul(rad)
			except Exception as eroare:
				_jurnal("pornirea modulului: %s" % eroare.__class__.__name__)
	rez["puse"] = list(rez.get("puse") or []) + [n for n in r["puse"] if n not in (rez.get("puse") or [])]
	rez["nereusite"] = [n for n in rez.get("nereusite") or [] if n not in de_pus] + r["nereusite"]
	rez["lipsa"] = list(rez.get("lipsa") or []) + r["lipsa"]
	rez["acces_lipsa"] = list(rez.get("acces_lipsa") or []) + r["lipsa"]
	rez["acces_de_pus"] = r["nereusite"]
	if inlocuite:
		rez["inlocuite"] = inlocuite
	rez["raspuns"] = "" if r["nereusite"] else "da"
	if not r["nereusite"]:
		rez.pop("legaturi", None)
		shutil.rmtree(os.path.join(dosar(rad), DOSAR_CONFIG), ignore_errors=True)
	_scrie_json(cale_rez, rez)
	_jurnal("modulele din copie la cerere: puse %d, nu exista %d, nereusite %d" % (len(r["puse"]), len(r["lipsa"]),
		len(r["nereusite"])))
	return r


def mesaj_module(r):
	"""Textul de dupa Da (televizor si pagina web)."""
	randuri = []
	if r.get("mesaj"):
		return r["mesaj"]
	if r.get("puse"):
		text = (_("Modulul de acces e instalat: %s. Alegerea ta a rămas păstrată.") if r.get("alegere_pastrata") else
			_("Modulul de acces e pus și pornit: %s."))
		randuri.append(text % ", ".join(_scurt(n) for n in r["puse"]))
	if r.get("lipsa"):
		randuri.append(_("Modulul de acces din copie nu există pentru imaginea aceasta: %s. Setările lui au rămas pe "
			"receptor.") % ", ".join(_scurt(n) for n in r["lipsa"]))
	if r.get("nereusite"):
		randuri.append(_("Modulul %s nu s-a putut instala acum (fără internet sau feedul nu răspunde). Te întreb din nou la "
			"următoarea pornire.") % ", ".join(_scurt(n) for n in r["nereusite"]))
	return "\n".join(randuri)


def refuza_modulele(rad="/"):
	"""Raspunsul Nu: televizorul nu mai intreaba; pagina web pastreaza butonul."""
	cale_rez = os.path.join(dosar(rad), REZULTAT)
	rez = _citeste_json(cale_rez)
	if rez and rez.get("acces_de_pus"):
		rez["raspuns"] = "nu"
		_scrie_json(cale_rez, rez)


def de_intrebat(rad="/"):
	"""Modulele de intrebat acum pe televizor: cele de pus, daca omul n-a spus Nu si nu l-am intrebat la pornirea
	aceasta a receptorului; [] altfel."""
	rez = _citeste_json(os.path.join(dosar(rad), REZULTAT)) or {}
	if rez.get("raspuns") == "nu" or (rez.get("intrebat") and rez.get("intrebat") == _boot_id(rad)):
		return []
	return module_de_pus(rad)


_MODULE = []
_CITIRE_MODULE = []
_CACHE_MODULE = {"nume": [], "mesaj": "", "eroare": False, "cand": 0}
_GENERATIE_MODULE = 0
_ULTIM_MODULE = None


def _citeste_starea_modulelor():
	nume = module_de_pus("/")
	rez = _citeste_json(os.path.join(dosar("/"), REZULTAT)) or {}
	text, eroare = mesaj(rez) if nume else "", False
	if _ULTIM_MODULE and _ULTIM_MODULE[0] == tuple(nume):
		text, eroare = _ULTIM_MODULE[1:]
	return {"nume": nume, "mesaj": text, "eroare": eroare, "cand": time.monotonic()}


def stare_module_pe_fir():
	"""Interfata primeste un snapshot; discul se citeste numai pe firul lucrarii."""
	try:
		import enigma
	except ImportError:
		# Consumator fara interfata Enigma2 (unelte locale).
		return _citeste_starea_modulelor()
	if not _CITIRE_MODULE and not _MODULE and time.monotonic() - _CACHE_MODULE["cand"] >= 1:
		from Components.HdsImportSurse import Lucrare
		generatie = _GENERATIE_MODULE
		_CITIRE_MODULE.append(None)
		def gata(st, eroare):
			del _CITIRE_MODULE[:]
			if not _MODULE and generatie == _GENERATIE_MODULE:
				if eroare:
					_CACHE_MODULE.update(mesaj=_("Starea modulelor din copie nu se poate citi acum. Copia a rămas păstrată."),
						eroare=True, cand=time.monotonic())
				else:
					_CACHE_MODULE.update(st)
		try:
			l = Lucrare(_citeste_starea_modulelor, gata)
			if _CITIRE_MODULE:
				_CITIRE_MODULE[0] = l
		except Exception:
			del _CITIRE_MODULE[:]
			_CACHE_MODULE.update(mesaj=_("Starea modulelor din copie nu se poate citi acum. Copia a rămas păstrată."),
				eroare=True, cand=time.monotonic())
	return dict(_CACHE_MODULE, nume=list(_CACHE_MODULE["nume"]))


def _alt_modul_ales():
	"""Numai metadate si legaturi, pe firul lucrarii, inainte de opkg."""
	rez = _citeste_json(os.path.join(dosar("/"), REZULTAT)) or {}
	with _ZAVOR_ALEGERI:
		for rel, tinta in (rez.get("legaturi") or {}).items():
			if not TIPAR_LEGATURA.match(rel) or not rel.startswith("etc/init.d/"):
				continue
			cale = _c("/", rel)
			if not os.path.islink(cale):
				continue
			ales = os.path.basename(os.readlink(cale))
			if ales != os.path.basename(tinta) and not ales.endswith("." + SUFIX_GOL) \
					and os.path.isfile(_c("/", "etc/init.d/" + ales)):
				return True
	return False


def module_in_lucru():
	return bool(_MODULE)


def porneste_modulele(la_sfarsit=None):
	"""pune_modulele pe un fir separat (opkg poate dura minute), din intrebarea de pe televizor sau din pagina web; la
	sfarsit o fereastra pe televizor cu mesaj_module si la_sfarsit(r). False daca lucreaza deja."""
	global _GENERATIE_MODULE
	if _MODULE:
		return False
	from Components.HdsCopieSetari import _porneste_modulul
	from Components.HdsImportSurse import Lucrare

	def gata(r, eroare):
		global _ULTIM_MODULE
		del _MODULE[:]
		if eroare:
			_jurnal("modulele la cerere s-au oprit")
			r = {"puse": [], "lipsa": [], "nereusite": list(_CACHE_MODULE["nume"]),
				"mesaj": _("Modulul nu s-a putut porni acum. Încearcă din nou."), "eroare": True}
		else:
			r, st = r
			_CACHE_MODULE.update(st)
		text = mesaj_module(r or {})
		_ULTIM_MODULE = (tuple(_CACHE_MODULE["nume"]), text,
			bool(r.get("nereusite") or r.get("lipsa") or r.get("eroare")))
		_CACHE_MODULE.update(mesaj=text, eroare=_ULTIM_MODULE[2], cand=time.monotonic())
		if text:
			from Tools import Notifications
			from Screens.MessageBox import MessageBox
			Notifications.AddPopup(text, MessageBox.TYPE_ERROR if _ULTIM_MODULE[2] else MessageBox.TYPE_INFO,
				20, "HdsReinstalareModule", titlu=_("Copia setărilor"))
		if la_sfarsit is not None:
			la_sfarsit(r)
	def lucru():
		if _alt_modul_ales():
			r = {"puse": [], "lipsa": [], "nereusite": [], "eroare": True,
				"mesaj": _("Ai ales deja alt modul. Instalarea din copie nu a pornit, ca să păstreze alegerea ta. Copia a rămas păstrată.")}
		else:
			r = pune_modulele("/", porneste_modulul=_porneste_modulul)
		return r, _citeste_starea_modulelor()
	_MODULE.append(None)
	_GENERATIE_MODULE += 1
	try:
		l = Lucrare(lucru, gata)
		if _MODULE:
			_MODULE[0] = l
	except Exception:
		del _MODULE[:]
		raise
	return True


def _intreaba_modulele(session, randuri=None):
	"""Intrebarea cu Da pentru modulele din copie (de_intrebat), fara termen; `randuri`: randurile rezultatului de
	aratat sub ea, cand vin in aceeasi fereastra."""
	nume = de_intrebat("/")
	if not nume:
		return
	cale_rez = os.path.join(dosar("/"), REZULTAT)
	rez = _citeste_json(cale_rez) or {}
	rez["intrebat"] = _boot_id("/")
	_scrie_json(cale_rez, rez)
	from Tools import Notifications
	from Screens.MessageBox import MessageBox

	def raspuns(da):
		if da:
			porneste_modulele()
		else:
			refuza_modulele("/")
	optiuni = {"titlu": _("Copia setărilor")}
	if randuri:
		optiuni["puncte"] = randuri
	Notifications.AddNotificationWithCallback(raspuns, MessageBox, intrebare_module(nume), type=MessageBox.TYPE_YESNO,
		default=True, **optiuni)


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
	"""Rezultatul reinstalarii, o data; apoi, cata vreme un modul de acces din copie nu e instalat, intrebarea cu Da
	(o data la fiecare pornire a receptorului, pana la Da reusit sau Nu). Cand ambele vin acum: o singura fereastra,
	intrebarea cu randurile rezultatului sub ea."""
	try:
		intrebare_cu_randuri = _arata_rezultatul(session)
	except Exception as eroare:
		_jurnal("rezultatul: %s" % eroare.__class__.__name__)
		intrebare_cu_randuri = None
	if intrebare_cu_randuri is False:
		return   # interfata reporneste pentru pluginuri: intrebarea vine la pornirea urmatoare
	try:
		_intreaba_modulele(session, intrebare_cu_randuri)
	except Exception as eroare:
		_jurnal("intrebarea modulelor: %s" % eroare.__class__.__name__)


def _arata_rezultatul(session):
	"""Fereastra rezultatului; intoarce randurile ei cand le ia intrebarea modulelor (o singura fereastra), False cand
	interfata reporneste, None altfel."""
	cale = os.path.join(dosar("/"), REZULTAT)
	rez = _citeste_json(cale)
	if not rez or rez.get("aratat"):
		return None
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
		return None
	from Tools import Notifications
	from Screens.MessageBox import MessageBox
	if repornire:
		f = fereastra(rez, _("Interfața repornește o dată acum, ca pluginurile noi să se încarce."))

		def reporneste(*_a):
			from Screens.Standby import TryQuitMainloop
			session.open(TryQuitMainloop, 3)
		Notifications.AddNotificationWithCallback(reporneste, MessageBox, f.pop("text"), type=MessageBox.TYPE_INFO, timeout=15, **f)
		return False
	if de_intrebat("/"):
		# randul "nu e instalat încă" il spune chiar intrebarea
		randul_modulului = randuri_mesaj({"acces_de_pus": rez.get("acces_de_pus") or []})
		return [x for x in randuri_mesaj(rez) if x not in randul_modulului]
	f = fereastra(rez)
	Notifications.AddPopup(f.pop("text"), MessageBox.TYPE_INFO, 20, "HdsReinstalare", **f)
	return None


def _argumenteUpdate(rad="/"):
	"""OPK1 (0.8.0): ['update'], or ['-f', <conf>, 'update'] when a dead foreign source is skipped (HdsSurseOpkg)"""
	try:
		try:
			from Components import HdsSurseOpkg
		except ImportError:
			import HdsSurseOpkg
		return HdsSurseOpkg.argumente_update(rad)
	except Exception as e:
		print("[HdsSurseOpkg] %r" % (e,))
		return ["update"]
