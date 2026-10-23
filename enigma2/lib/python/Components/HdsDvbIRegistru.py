# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDvbIRegistru: registrele de liste DVB-I ("lista listelor") si citirea raspunsului lor, ca omul sa aleaga tara si
# lista fara sa scrie adrese de mana. Raspunsul unui registru e un document ServiceListEntryPoints: furnizori, fiecare
# cu listele lui (nume, adresa, tarile tinta). Citirea foloseste numai numele locale ale elementelor, deci merge pe
# toate versiunile schemei; documentele cu DOCTYPE/ENTITY se resping (ca listele insesi).
from __future__ import absolute_import, unicode_literals

import xml.etree.ElementTree as ET

try:
	from urllib.request import Request, urlopen
except ImportError:  # Python 2
	from urllib2 import Request, urlopen

# Registrele care raspund (verificate din Romania): cel mondial, cel german si unul cu liste din mai multe tari.
REGISTRE = (
	("https://query.slrdb.org/providers", "mondial"),
	("https://csr.dvb-i-slr.de/query", "Germania"),
	("https://csr.dtv.fi/api/query", "mai multe tari"),
)
MAX_RASPUNS = 2 * 1024 * 1024


def _local(tag):
	return tag.split("}")[-1]


def _copii(el, nume):
	return [c for c in list(el) if _local(c.tag) == nume]


def _text(el):
	return (el.text or "").strip() if el is not None else ""


def _primul(el, nume):
	for c in el.iter():
		if _local(c.tag) == nume and _text(c):
			return _text(c)
	return ""


def citeste(xml_bytes):
	"""[{"furnizor", "lista", "adresa", "tari": [..]}] din raspunsul unui registru; [] la orice greseala"""
	if not xml_bytes or len(xml_bytes) > MAX_RASPUNS:
		return []
	cap = xml_bytes[:4096].upper()
	if b"<!DOCTYPE" in cap or b"<!ENTITY" in cap:
		return []
	try:
		rad = ET.fromstring(xml_bytes)
	except Exception:
		return []
	liste = []
	for oferta in rad.iter():
		if _local(oferta.tag) != "ProviderOffering":
			continue
		prov = _copii(oferta, "Provider")
		furnizor = _primul(prov[0], "Name") if prov else ""
		for sl in _copii(oferta, "ServiceListOffering"):
			nume = ""
			for c in sl.iter():
				if _local(c.tag) == "ServiceListName" and _text(c):
					nume = _text(c)
					break
			adresa = ""
			for c in sl.iter():
				if _local(c.tag) == "URI" and _text(c).startswith(("http://", "https://")):
					adresa = _text(c)
					break
			if not adresa:
				continue
			tari = sorted(set(_text(c) for c in sl.iter() if _local(c.tag) == "TargetCountry" and _text(c)))
			liste.append({"furnizor": furnizor, "lista": nume or furnizor, "adresa": adresa, "tari": tari})
	return liste


def pentruTara(liste, tara):
	"""listele pentru o tara (cod ISO cu 3 litere, ca DEU); cele fara tara tinta raman, fiind pentru oricine"""
	tara = (tara or "").upper()
	return [l for l in liste if not l["tari"] or tara in [t.upper() for t in l["tari"]]]


def intreaba(adresa, termen=10, deschide=None):
	"""listele unui registru, [] daca nu raspunde; 'deschide' inlocuieste urlopen in teste. Nu arunca."""
	deschide = deschide or urlopen
	try:
		r = deschide(Request(adresa, headers={"User-Agent": "HDSatelit"}), timeout=termen)
		try:
			return citeste(r.read(MAX_RASPUNS + 1))
		finally:
			r.close()
	except Exception:
		return []


def toateTarile(liste):
	return sorted(set(t for l in liste for t in l["tari"]))


# ------------------------------------------------------------------ toate registrele, tinute minte pe disc
# Registrele raspund cu liste de proba (demonstratii, liste de la targuri, adrese din retele locale) amestecate cu cele
# adevarate. Omul alege tara; listele ei care nu sunt de proba se iau singure, cele de proba raman de bifat de mana.
# Raspunsul tuturor registrelor sta in CALE (JSON), ca ecranul si pagina web sa nu intrebe registrele pe firul enigma2.
CALE = "/etc/enigma2/hdsdvbi-registre.json"
VECHIME_MAX_S = 24 * 3600
CUVINTE_PROBA = ("test", "demo", "staging", "example", "uat", "messe", "ibc", "poc", "5g", "pilot", "reference",
	"localhost")


def adresaPublica(adresa):
	"""False pentru adresele din retele locale (localhost, 127.x, 10.x, 172.16-31.x, 192.168.x, .local): o lista din
	registru cu o asemenea adresa nu e a nimanui de pe internet"""
	try:
		gazda = adresa.split("://", 1)[1].split("/", 1)[0].split("@")[-1]
	except IndexError:
		return False
	if gazda.startswith("["):
		return False
	gazda = gazda.split(":", 1)[0].lower()
	if not gazda or gazda == "localhost" or gazda.endswith(".local") or gazda.endswith(".localhost"):
		return False
	p = gazda.split(".")
	if len(p) == 4 and all(x.isdigit() for x in p):
		a, b = int(p[0]), int(p[1])
		if a in (0, 10, 127) or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or (a == 169 and b == 254):
			return False
	return True


def deProba(lista):
	"""True pentru o lista de proba (numele, furnizorul sau adresa spun test, demonstratie, pregatire ...)"""
	text = " ".join((lista.get("lista", ""), lista.get("furnizor", ""), lista.get("adresa", ""))).lower()
	return any(c in text for c in CUVINTE_PROBA)


def intreabaToate(termen=10, deschide=None, acum=None, registre=None):
	"""intreaba toate registrele (pe firul celui care cheama). -> {"ora", "registre": [{"adresa", "nume", "liste"}],
	"liste": [...]}: "liste" fara dubluri (aceeasi adresa din doua registre o data, cu tarile unite), fara adresele
	din retele locale, fiecare cu "registru" (adresa registrului) si "proba"; "liste" -1 la un registru care nu a
	raspuns"""
	import time
	rez = {"ora": int(time.time() if acum is None else acum), "registre": [], "liste": []}
	dupa_adresa = {}
	for adresa, nume in (registre or REGISTRE):
		liste = intreaba(adresa, termen=termen, deschide=deschide)
		rez["registre"].append({"adresa": adresa, "nume": nume, "liste": len(liste) if liste else -1})
		for l in liste:
			if not adresaPublica(l["adresa"]):
				continue
			vechi = dupa_adresa.get(l["adresa"])
			if vechi is not None:
				vechi["tari"] = sorted(set(vechi["tari"]) | set(l["tari"]))
				continue
			nou = dict(l)
			nou["registru"] = adresa
			nou["proba"] = deProba(l)
			dupa_adresa[l["adresa"]] = nou
			rez["liste"].append(nou)
	return rez


def aleTarii(liste, tara):
	"""numai listele care au tara printre tarile tinta (fara cele "pentru oricine": in registre acelea sunt probe)"""
	tara = (tara or "").upper()
	return [l for l in liste if tara and tara in [t.upper() for t in l.get("tari", [])]]


def implicite(liste, tara):
	"""adresele listelor tarii care se iau singure: toate cele care nu sunt de proba"""
	return [l["adresa"] for l in aleTarii(liste, tara) if not l.get("proba")]


def tari(liste):
	"""[(cod, cate liste, cate nu sunt de proba)] pentru fiecare tara din registre, in ordinea codului"""
	n = {}
	for l in liste:
		for t in l.get("tari", []):
			t = t.upper()
			a, b = n.get(t, (0, 0))
			n[t] = (a + 1, b + (0 if l.get("proba") else 1))
	return [(t, a, b) for t, (a, b) in sorted(n.items())]


def salveaza(raspuns, cale=None):
	"""scrie raspunsul registrelor (prin .nou si redenumire). -> True daca s-a scris"""
	import json
	import os
	cale = cale or CALE
	nou = cale + ".nou"
	try:
		with open(nou, "w", encoding="utf-8") as f:
			json.dump(raspuns, f)
		os.replace(nou, cale)
		_CITIT.update(semn=None, date=None)
		return True
	except (IOError, OSError, TypeError, ValueError):
		try:
			os.unlink(nou)
		except OSError:
			pass
		return False


_CITIT = {"semn": None, "date": None}


def incarca(cale=None):
	"""raspunsul tinut minte ({"ora": 0, "registre": [], "liste": []} daca lipseste sau e stricat); citit din nou numai
	cand fisierul se schimba"""
	import json
	import os
	cale = cale or CALE
	try:
		st = os.stat(cale)
		semn = (cale, st.st_mtime_ns, st.st_size, st.st_ino)
	except OSError:
		return {"ora": 0, "registre": [], "liste": []}
	if _CITIT["semn"] == semn and _CITIT["date"] is not None:
		return _CITIT["date"]
	try:
		with open(cale, encoding="utf-8") as f:
			date = json.load(f)
		if not isinstance(date, dict) or not isinstance(date.get("liste"), list):
			raise ValueError("forma")
	except (IOError, OSError, ValueError):
		return {"ora": 0, "registre": [], "liste": []}
	date.setdefault("ora", 0)
	date.setdefault("registre", [])
	_CITIT.update(semn=semn, date=date)
	return date


def deIntrebat(raspuns, acum=None):
	"""True cand raspunsul tinut minte lipseste, e mai vechi de VECHIME_MAX_S sau nu are nicio lista"""
	import time
	acum = time.time() if acum is None else acum
	return not raspuns.get("liste") or acum - raspuns.get("ora", 0) > VECHIME_MAX_S or acum < raspuns.get("ora", 0)
