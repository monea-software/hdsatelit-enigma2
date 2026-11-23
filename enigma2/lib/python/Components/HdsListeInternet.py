# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsListeInternet.py: listele de canale gata facute ale autorilor cunoscuti, alese, descarcate si instalate din
# receptor, fara ecran. Le folosesc ecranul "Liste de canale de pe internet" (Screens/HdsListeInternet.py, deschis din
# Meniu > Scanare > Liste implicite de canale) si pagina web /liste-internet (HdsWebControl/liste_internet_web.py),
# deci amandoua vad aceleasi liste si fac aceeasi instalare.
#
# Autorii (AUTORI, un rand fiecare, deci unul se poate opri cu un singur rand): fiecare cu adresa lui publica
# oficiala, citita direct de receptor; pe serverele noastre nu sta nicio copie a listelor. Cei din AUTORI isi tin listele
# ca arhive zip intr-un depozit GitHub (lista fisierelor prin api.github.com, fisierele de pe raw.githubusercontent.com)
# si le dau anume pentru incarcatoarele de liste din receptoare. Un al treilea autor (VHANNIBAL, cu lista de pe situl lui
# pe care o citeste pluginul lui oficial) e scris mai jos, dar e oprit: situl lui interzice publicarea listelor in pluginuri.
# Numai HTTPS verificat, fara proxy din mediu si fara redirectionari, numai spre GAZDE, cu termen si cu marimea
# limitata. Cand o lista nu se poate citi (fara internet, GitHub care cere o pauza dupa multe cereri), ceilalti autori
# raman; catalogul citit se tine minte TINUT_MINTE_S secunde.
#
# Felul listei (un satelit, doi, mai multi, motor) si pozitiile se afla din numele ei; data, tot din nume (sau din
# lista autorului), fara alte cereri. Antena receptorului (antena(), pe firul enigma2) da felul ales la deschidere si
# ordinea: intai listele cu exact satelitii antenei, apoi cele care ii cuprind pe toti, apoi restul.
#
# Instalarea foloseste importul de canale al imaginii (Components/HdsImportSurse.py, acelasi ca la "Import canale si
# setari"): arhiva descarcata devine o sursa ca arhiva trimisa din calculator, apoi zavorul importului (ocupa),
# pregatirea, copia de siguranta automata a listelor de acum (hds-backup-setari-<data>, se pastreaza ultimele cinci),
# scrierea, buchetele imaginii puse la loc si reincarcarea listei pe firul enigma2 (incheie_importul). In plus fata de
# import, aici raman ale omului: favoritele (userbouquet.favourites.tv / .radio, cand au canale) si buchetele lui de
# internet (numai fluxuri, nu depind de lista de canale), cu randul lor in index (pastrate_in_pregatire).
#
# Punerea la loc: in dosarul copiei facute de instalare se scrie SEMN (ce lista s-a instalat si ce fisiere noi a adus).
# "Pune la loc" importa inapoi cea mai noua copie cu semn, sterge fisierele aduse de lista care nu erau in copie si
# scoate semnul. O copie stearsa intre timp (raman cinci) inseamna nimic de pus la loc. Nimic nu se scrie in afara de
# /etc/enigma2 (prin import) si de dosarul descarcarii din /tmp, sters la sfarsit.
#
# Firele: citirea catalogului si instalarea merg pe firul lor (HdsImportSurse.Lucrare); pe firul enigma2 raman
# antena(), textul settings de acum (pentru copie) si reincarcarea listei. Fisierul nu importa nimic din enigma2 la
# incarcare: probele de pe PC il folosesc direct.

import glob
import datetime
import hashlib
import html
import io
import json
import os
import re
import shutil
import ssl
import tempfile
import threading
import time
import zipfile

from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

# ---------------------------------------------------------------- autorii

# (cheia, numele aratat, felul listei, depozitul GitHub sau adresa listei)
VHANNIBAL = {"cheie": "vhannibal", "nume": "Vhannibal", "fel": "vhannibal", "lista": "https://www.vhannibal.net/asd.php", "baza": "https://www.vhannibal.net/"}
AUTORI = (
	{"cheie": "ciefp", "nume": "Ciefp", "fel": "github", "depozit": "ciefp/ciefpsettings-enigma2-zipped", "ramura": "master"},
	{"cheie": "morpheus883", "nume": "Morpheus883", "fel": "github", "depozit": "morpheus883/enigma2-zipped", "ramura": "master"},
	# VHANNIBAL,  scos pana la hotarare: vhannibal.net interzice publicarea listelor lor in pluginuri
)
GAZDE = ("api.github.com", "raw.githubusercontent.com") + (("www.vhannibal.net",) if VHANNIBAL in AUTORI else ())
API_GITHUB = "https://api.github.com/repos/%s/contents/?ref=%s"
RAW_GITHUB = "https://raw.githubusercontent.com/%s/%s/%s"
AGENT = "HDSatelit-Liste/1 (+https://www.hdsatelit.com)"

FELURI = ("toate", "unu", "doi", "multi", "motor")
DOSAR_DESCARCARI = "/tmp/hds-liste-internet"
CALE_ETC = "/etc/enigma2"
SEMN = "hds-liste-internet.json"
TERMEN_S = 25.0                       # o cerere
TERMEN_TOTAL_S = 90.0                 # o descarcare intreaga
MAX_CATALOG = 1024 * 1024             # lista unui autor
MAX_DESCARCARE = 16 * 1024 * 1024     # o arhiva (cele mai mari au sub 3 MB)
TINUT_MINTE_S = 30 * 60
PAUZA_S = 3 * 60                      # dupa o citire cazuta, alta numai cerut de om (fortat) sau dupa pauza
TOLERANTA = 6                         # zecimi de grad: 19E al unui autor e 19.2E al altuia
MAX_LISTE = 200
OPTIUNE_AUTO = "hds-liste-actualizare.json"
INTERVAL_AUTO_S = 6 * 60 * 60

TIPAR_CIEFP = re.compile(r"^ciefp-E2-(?:(\d+)sat[A-Za-z]?-)?((?:[0-9.]+[EeWw]-?)+)-(\d{2})\.(\d{2})\.(\d{4})\.zip$")
TIPAR_MORPHEUS = re.compile(r"^E2_Morph883_([A-Za-z0-9.\-]+)_(\d{2})(\d{2})(\d{2})\.zip$")
TIPAR_POZ = re.compile(r"^([0-9]{1,3}(?:\.[0-9])?)([EeWw])$")
TIPAR_RAND_VH = re.compile(r'<td>\s*<a href="(autosetting/download\.php\?id=(\d{1,4})&(?:amp;)?action=download)">(.+?)</a>\s*</td>'
	r'\s*<td>\s*(\d{6})\s*</td>', re.S | re.I)
TIPAR_NUMAR_VH = re.compile(r"([0-9]{1,3}(?:[.,][0-9])?)\s*(?:°|&deg;|\xb0)?\s*([EW])?", re.I)
TIPAR_RAND_INDEX = re.compile(r'^#SERVICE:?\s+1:7:\d+:.*FROM BOUQUET\s+"([^"]+)"', re.I)


class _TiparBuchet(object):
	"""Numele fisierelor de buchet: aceeasi regula ca la import (HdsImportSurse.TIPAR_BUCHET: litere cu diacritice, spatii
	si & primite, caile si caracterele de control nu), luata la folosire."""

	def match(self, nume):
		return _I().TIPAR_BUCHET.match(nume)


TIPAR_BUCHET = _TiparBuchet()

FAVORITE =("userbouquet.favourites.tv", "userbouquet.favourites.radio")
INDEXURI = ("bouquets.tv", "bouquets.radio")
PREFIX_IMAGINE = "userbouquet.hds_"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsListeInternet] %s" % text)


def _I():
	from Components import HdsImportSurse
	return HdsImportSurse


def _autor(cheie):
	for a in AUTORI + (VHANNIBAL,):
		if a["cheie"] == cheie:
			return a
	raise KeyError(cheie)


# ---------------------------------------------------------------- texte (aceleasi pe televizor si in web)

def text_fel(fel):
	return {
		"toate": _("Toate"),
		"unu": _("Un satelit"),
		"doi": _("Doi sateliți"),
		"multi": _("Mai mulți sateliți"),
		"motor": _("Motor"),
	}.get(fel, fel)


def text_autor(cheie):
	if not cheie:
		return _("Toți autorii")
	for a in AUTORI:
		if a["cheie"] == cheie:
			return a["nume"]
	return cheie


def text_intro():
	return _("Listele gata făcute de %s, după sateliții antenei tale. Lista de acum se păstrează și se pune la loc cu "
		"un buton.") % ", ".join(a["nume"] for a in AUTORI)


def text_instalata(semn):
	"""Randul listei instalate de ultima instalare (din semnul copiei ei), sau ""."""
	i = (semn or {}).get("lista") or {}
	if not i:
		return ""
	return _("Instalată acum: %s (%s)") % ("%s: %s" % (i.get("autor", ""), i.get("nume", "")), i.get("data", ""))


def text_schimbata():
	return _("Lista aleasă s-a schimbat la autor. Citesc din nou listele.")


def text_gol():
	return _("Nicio listă pentru alegerea asta. Schimbă sateliții sau autorul.")


def text_ajutor():
	return _("Stânga și dreapta: sateliții. Albastru: autorul. OK: instalează lista.")


# ---------------------------------------------------------------- pozitiile si felul listelor

def pozitie(text):
	"""'19E', '19.2E', '0.8w', '30W' -> pozitia in zecimi de grad spre est (0..3599); None daca nu e o pozitie."""
	m = TIPAR_POZ.match((text or "").strip())
	if not m:
		return None
	zecimi = int(round(float(m.group(1)) * 10))
	if zecimi > 1800:
		return None
	if m.group(2) in "Ww":
		return (3600 - zecimi) % 3600
	return zecimi


def text_pozitie(p):
	"""1920 -> '19.2°E', 3592 -> '0.8°W'."""
	if p is None:
		return ""
	if p > 1800:
		v, d = 3600 - p, "W"
	else:
		v, d = p, "E"
	if v % 10:
		return "%d.%d°%s" % (v // 10, v % 10, d)
	return "%d°%s" % (v // 10, d)


def fel_din_pozitii(pozitii, motor=False):
	if motor:
		return "motor"
	n = len(pozitii or ())
	if n == 1:
		return "unu"
	if n == 2:
		return "doi"
	return "multi" if n > 2 else ""


def _aproape(a, b):
	d = abs(a - b) % 3600
	return min(d, 3600 - d) <= TOLERANTA


def _cuprinde(mari, mici):
	return all(any(_aproape(x, y) for y in mari) for x in mici)


def potrivire(lista, ant):
	"""0 = exact satelitii antenei (sau motor la motor), 1 = ii cuprinde pe toti, 2 = restul."""
	if not ant or not (ant.get("pozitii") or ant.get("fel") == "motor"):
		return 2
	if ant.get("fel") == "motor":
		return 0 if lista["fel"] == "motor" else 2
	if lista["fel"] == "motor":
		return 1
	ale, are = lista["pozitii"], ant["pozitii"]
	if _cuprinde(ale, are):
		return 0 if _cuprinde(are, ale) else 1
	return 2


def _scurt(pozitii, motor_text=""):
	if motor_text:
		return motor_text
	if len(pozitii) <= 3:
		return ", ".join(text_pozitie(p) for p in pozitii)
	return _("%d sateliți (%s - %s)") % (len(pozitii), text_pozitie(pozitii[0]), text_pozitie(pozitii[-1]))


def _lista(autor, id_lista, nume, url, zi, luna, an, pozitii, motor=False, marime=0, terestru=False, extra=""):
	try:
		timp = time.mktime((an, luna, zi, 12, 0, 0, 0, 0, -1))
	except (OverflowError, ValueError):
		timp = 0
	return {
		"id": "%s:%s" % (autor["cheie"], id_lista),
		"autor": autor["cheie"],
		"autor_nume": autor["nume"],
		"nume": nume,
		"url": url,
		"data": "%02d.%02d.%04d" % (zi, luna, an),
		"timp": timp,
		"pozitii": list(pozitii),
		"fel": fel_din_pozitii(pozitii, motor),
		"terestru": bool(terestru),
		"marime": int(marime or 0),
		"detalii": extra,
	}


def liste_ciefp(intrari, autor=None):
	"""Lista fisierelor din depozitul lui Ciefp (raspunsul api.github.com/.../contents) -> listele cunoscute."""
	autor = autor or _autor("ciefp")
	rez = []
	for e in _intrari_valide(intrari):
		if e.get("type") != "file":
			continue
		nume = e.get("name") or ""
		m = TIPAR_CIEFP.match(nume)
		if not m:
			continue
		poz = [pozitie(t) for t in m.group(2).strip("-").split("-") if t]
		if not poz or None in poz:
			continue
		motor = not m.group(1)
		zi, luna, an = int(m.group(3)), int(m.group(4)), int(m.group(5))
		if not _data_valida(zi, luna, an):
			continue
		if motor:
			scurt = _("Motor %s - %s") % (text_pozitie(poz[0]), text_pozitie(poz[-1]))
			poz_lista = []
		else:
			scurt = _scurt(poz)
			poz_lista = poz
		url = RAW_GITHUB % (autor["depozit"], autor["ramura"], quote(nume))
		rez.append(_lista(autor, nume, scurt, url, zi, luna, an, poz_lista, motor, e.get("size"),
			extra=(" - " if motor else ", ").join(text_pozitie(p) for p in poz)))
		rez[-1]["sha"] = e.get("sha", "")
	return rez


def liste_morpheus(intrari, autor=None):
	"""Lista fisierelor din depozitul lui Morpheus883 -> listele cunoscute (pachetul tuturor listelor se sare)."""
	autor = autor or _autor("morpheus883")
	rez = []
	for e in _intrari_valide(intrari):
		if e.get("type") != "file":
			continue
		nume = e.get("name") or ""
		m = TIPAR_MORPHEUS.match(nume)
		if not m:
			continue
		zi, luna, an = int(m.group(2)), int(m.group(3)), 2000 + int(m.group(4))
		if not _data_valida(zi, luna, an):
			continue
		url = RAW_GITHUB % (autor["depozit"], autor["ramura"], quote(nume))
		corp = m.group(1)
		if corp.lower() == "motor":
			rez.append(_lista(autor, nume, _("Motor"), url, zi, luna, an, [], True, e.get("size")))
			rez[-1]["sha"] = e.get("sha", "")
			continue
		poz = [pozitie(t) for t in corp.split("-") if t]
		if not poz or None in poz:
			continue
		rez.append(_lista(autor, nume, _scurt(poz), url, zi, luna, an, poz, False, e.get("size"),
			extra=", ".join(text_pozitie(p) for p in poz)))
		rez[-1]["sha"] = e.get("sha", "")
	return rez


def _data_valida(zi, luna, an):
	try:
		datetime.date(an, luna, zi)
		return True
	except ValueError:
		return False


def _intrari_valide(intrari):
	for e in intrari or []:
		if not isinstance(e, dict) or not isinstance(e.get("name"), str):
			continue
		marime = e.get("size", 0)
		if not isinstance(marime, int) or isinstance(marime, bool) or not 0 <= marime <= MAX_DESCARCARE:
			continue
		sha = e.get("sha", "")
		if not isinstance(sha, str) or (sha and not re.match(r"^[0-9a-f]{40}$", sha)):
			continue
		yield e


def varianta(lista):
	"""Stable author variant, including A/B distinctions, without the release date."""
	id_lista = lista.get("id", "")
	if not isinstance(id_lista, str) or ":" not in id_lista:
		return ""
	autor, nume = id_lista.split(":", 1)
	if autor == "ciefp" and TIPAR_CIEFP.match(nume):
		return autor + ":" + nume.rsplit("-", 1)[0]
	if autor == "morpheus883" and TIPAR_MORPHEUS.match(nume):
		return autor + ":" + nume.rsplit("_", 1)[0]
	return ""


def _pozitii_vhannibal(nume):
	"""Pozitiile din numele unei liste ('Dual 13, 19°E', 'Trial 13, 19°E, 30°W'): directia se aplica si numerelor
	dinaintea ei fara directie."""
	text = nume.split("+", 1)[0]
	numere = TIPAR_NUMAR_VH.findall(text)
	rez, fara = [], []
	for numar, directie in numere:
		v = numar.replace(",", ".")
		if not directie:
			fara.append(v)
			continue
		for x in fara + [v]:
			p = pozitie(x + directie)
			if p is not None:
				rez.append(p)
		fara = []
	for x in fara:
		p = pozitie(x + "E")
		if p is not None:
			rez.append(p)
	return rez


def liste_vhannibal(text, autor=None):
	"""Pagina cu lista oficiala a lui Vhannibal (latin-1) -> listele; randurile cu piconuri se sar."""
	autor = autor or VHANNIBAL
	if isinstance(text, bytes):
		text = text.decode("latin-1", "replace")
	rez = []
	for cale, id_vh, nume, data in TIPAR_RAND_VH.findall(text):
		nume = html.unescape(re.sub(r"<[^>]+>", "", nume)).strip()
		if not nume or "picon" in nume.lower():
			continue
		if nume.lower().startswith("vhannibal "):
			nume = nume[len("vhannibal "):].strip()
		mic = nume.lower()
		terestru = "dtt" in mic
		if mic.startswith("hot bird"):
			poz, motor = [130], False
		elif mic.startswith("dual") and not _pozitii_vhannibal(nume):
			poz, motor = [130, 192], False
		else:
			poz = _pozitii_vhannibal(nume)
			motor = mic.startswith("motor") or not poz
			if motor:
				poz = []
		an, luna, zi = 2000 + int(data[0:2]), int(data[2:4]), int(data[4:6])
		url = autor["baza"] + html.unescape(cale)
		rez.append(_lista(autor, id_vh, nume, url, zi, luna, an, poz, motor, 0, terestru,
			extra=", ".join(text_pozitie(p) for p in poz)))
	return rez


# ---------------------------------------------------------------- descarcarea

class EroareDescarcare(Exception):
	pass


class _FaraRedirectionari(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		raise EroareDescarcare(_("Serverul autorului a trimis în altă parte."))


def gazda_permisa(url):
	m = re.match(r"^https://([A-Za-z0-9.-]+)(?::[0-9]{1,5})?(?:/|$)", url or "")
	return bool(m) and m.group(1).lower() in GAZDE


def citeste(url, limita, termen_s=TERMEN_S, total_s=TERMEN_TOTAL_S, accept=None, context=None):
	"""Octetii de la url (numai HTTPS spre GAZDE, fara redirectionari, cel mult `limita`). EroareDescarcare cu textul
	pentru om."""
	if not gazda_permisa(url):
		raise EroareDescarcare(_("Adresa nu e a unui autor cunoscut."))
	if context is None:
		context = ssl.create_default_context()
	deschide = build_opener(ProxyHandler({}), HTTPSHandler(context=context), _FaraRedirectionari())
	antete = {"User-Agent": AGENT, "Accept-Encoding": "identity"}
	if accept:
		antete["Accept"] = accept
	inceput = time.time()
	try:
		with deschide.open(Request(url, headers=antete), timeout=termen_s) as r:
			cod = r.getcode()
			if cod != 200:
				raise EroareDescarcare(_("Serverul autorului a răspuns cu %d.") % cod)
			lungime = r.headers.get("Content-Length")
			if lungime is not None and lungime.isdigit() and int(lungime) > limita:
				raise EroareDescarcare(_("Fișierul descărcat e prea mare."))
			date = bytearray()
			while True:
				if time.time() - inceput > total_s:
					raise EroareDescarcare(_("Descărcarea a durat prea mult."))
				bucata = r.read(min(65536, limita + 1 - len(date)))
				if not bucata:
					break
				date.extend(bucata)
				if len(date) > limita:
					raise EroareDescarcare(_("Fișierul descărcat e prea mare."))
			if lungime is not None and lungime.isdigit() and len(date) != int(lungime):
				raise EroareDescarcare(_("Descărcarea nu e întreagă."))
			return bytes(date)
	except EroareDescarcare:
		raise
	except Exception as eroare:
		cod = getattr(eroare, "code", None)
		if cod in (403, 429):
			raise EroareDescarcare(_("Serverul autorului cere o pauză. Încearcă din nou peste o oră."))
		if cod:
			raise EroareDescarcare(_("Serverul autorului a răspuns cu %d.") % cod)
		_jurnal("%s: %s" % (url.split("?", 1)[0], eroare.__class__.__name__))
		raise EroareDescarcare(_("Receptorul nu are legătură cu internetul."))


def catalog_autor(autor, citeste_url=None):
	"""Listele unui autor (citite acum de la el)."""
	citeste_url = citeste_url or citeste
	if autor["fel"] == "github":
		date = citeste_url(API_GITHUB % (autor["depozit"], autor["ramura"]), MAX_CATALOG,
			accept="application/vnd.github+json")
		try:
			intrari = json.loads(date.decode("utf-8"))
		except ValueError:
			raise EroareDescarcare(_("Lista autorului nu se poate citi."))
		if not isinstance(intrari, list):
			raise EroareDescarcare(_("Lista autorului nu se poate citi."))
		if autor["cheie"] == "ciefp":
			return liste_ciefp(intrari, autor)
		return liste_morpheus(intrari, autor)
	if autor["fel"] == "vhannibal":
		return liste_vhannibal(citeste_url(autor["lista"], MAX_CATALOG), autor)
	return []


def catalog(autori=None, citeste_url=None):
	"""(listele tuturor autorilor, {cheia autorului: textul erorii}). Ruleaza pe un fir separat."""
	liste, erori = [], {}
	for autor in autori or AUTORI:
		try:
			liste.extend(catalog_autor(autor, citeste_url)[:MAX_LISTE])
		except EroareDescarcare as eroare:
			erori[autor["cheie"]] = str(eroare)
		except Exception as eroare:
			_jurnal("lista %s: %s" % (autor["cheie"], eroare))
			erori[autor["cheie"]] = _("Lista autorului nu se poate citi.")
	return liste, erori


# ---------------------------------------------------------------- antena si ordinea

def antena(nm=None):
	"""{"fel", "pozitii"} dupa tunerele de satelit ale receptorului (pe firul enigma2): motor daca un tuner are rotor,
	altfel pozitiile satelitilor configurati (fara dubluri)."""
	try:
		if nm is None:
			from Components.NimManager import nimmanager as nm
		pozitii = set()
		for slot in range(len(nm.nim_slots)):
			try:
				if nm.getRotorSatListForNim(slot):
					return {"fel": "motor", "pozitii": []}
			except Exception:
				pass
			try:
				for s in nm.getSatListForNim(slot) or []:
					pozitii.add(int(s[0]) % 3600)
			except Exception:
				continue
		poz = sorted(pozitii)
		return {"fel": fel_din_pozitii(poz), "pozitii": poz}
	except Exception as eroare:
		_jurnal("antena: %s" % eroare)
		return {"fel": "", "pozitii": []}


def fel_implicit(ant):
	return (ant or {}).get("fel") or "toate"


def filtreaza(liste, fel="toate", autor="", ant=None):
	"""Listele felului si autorului alese, intai cele potrivite antenei, apoi dupa autor, apoi dupa numarul
	satelitilor."""
	ordine_autor = dict((a["cheie"], i) for i, a in enumerate(AUTORI))
	rez = [l for l in liste if (fel in ("", "toate") or l["fel"] == fel) and (not autor or l["autor"] == autor)]
	rez.sort(key=lambda l: (potrivire(l, ant), ordine_autor.get(l["autor"], 99), l["terestru"], len(l["pozitii"]),
		l["nume"].lower()))
	return rez


def descriere(lista, ant=None, cu_nume=True):
	"""Textul de sub lista pentru lista aleasa (in web fara primul rand, numele e deasupra). Satelitii se scriu numai
	cand numele nu ii spune pe toti."""
	randuri = ["%s: %s" % (lista["autor_nume"], lista["nume"])] if cu_nume else []
	if lista.get("detalii") and lista["detalii"] not in lista["nume"]:
		randuri.append((_("Motor: %s") if lista["fel"] == "motor" else _("Sateliți: %s")) % lista["detalii"])
	randuri.append(_("Actualizată: %s") % lista["data"])
	if potrivire(lista, ant) == 0 and ant and (ant.get("pozitii") or ant.get("fel") == "motor"):
		randuri.append(_("Potrivită antenei tale."))
	return "\n".join(randuri)


# ---------------------------------------------------------------- favoritele si buchetele de internet ale omului

def _randuri(cale):
	try:
		with io.open(cale, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
			return f.read()
	except (OSError, IOError):
		return None


def _servicii(text):
	"""Randurile #SERVICE care nu sunt etichete (1:64)."""
	D = _date_lamedb()
	return ["#SERVICE " + i._ref_brut for i in D.citeste_buchet("", text or "", lambda: 0).intrari
		if i.fel not in ("marcaj", "spatiu")]


def _fara_lista(servicii):
	"""Buchetul nu depinde de lista de canale (lamedb): numai fluxuri de internet si buchete din el (IPTV, Radio online,
	DVB-I ale imaginii si ale omului au sub-buchete), sau gol."""
	for s in servicii:
		mic = s.lower()
		if "%3a//" in mic or "http" in mic or re.match(r"^#service\s+1:7:", mic):
			continue
		return False
	return True


def buchete_de_pastrat(dest=CALE_ETC):
	"""[(indexul, numele fisierului, randul din index sau None)]: favoritele omului cu canale si buchetele din indexul de
	acum care nu depind de lista de canale (internet: IPTV, Radio online, DVB-I, fluxurile omului). Buchetele
	userbouquet.hds_* le pune la loc importul."""
	rez = []
	vazute = set()
	for index in INDEXURI:
		text = _randuri(os.path.join(dest, index)) or ""
		for rand in text.split("\n"):
			if rand in ("", "\r"):
				break
			m = TIPAR_RAND_INDEX.match(rand.strip())
			if not m:
				continue
			nume = m.group(1)
			if nume in vazute or not TIPAR_BUCHET.match(nume) or nume.startswith(PREFIX_IMAGINE):
				continue
			servicii = _servicii(_randuri(os.path.join(dest, nume)))
			if (nume in FAVORITE and servicii) or (nume not in FAVORITE and _fara_lista(servicii)):
				vazute.add(nume)
				rez.append((index, nume, rand.rstrip("\r\n")))
	for nume in FAVORITE:
		if nume not in vazute and _servicii(_randuri(os.path.join(dest, nume))):
			rez.append(("bouquets.radio" if nume.endswith(".radio") else "bouquets.tv", nume, None))
	return rez


def _date_lamedb():
	from Components import HdsEditorCanaleDate
	return HdsEditorCanaleDate


def _citeste_baza(dest):
	D = _date_lamedb()
	for nume in ("lamedb", "lamedb5"):
		cale = os.path.join(dest, nume)
		if os.path.lexists(cale):
			if os.path.islink(cale) or not os.path.isfile(cale):
				raise ValueError("lamedb link")
			with open(cale, "rb") as f:
				return D.citeste_lamedb(f.read())
	return D.Lamedb()


def _scrie_atomic(cale, date):
	"""Fisier temporar propriu, apoi inlocuire; nu refoloseste temporarele omului."""
	fd, nou = tempfile.mkstemp(prefix=".hds-lista-", dir=os.path.dirname(cale))
	try:
		with os.fdopen(fd, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		if os.path.isfile(cale) and not os.path.islink(cale):
			shutil.copymode(cale, nou)
		os.replace(nou, cale)
	finally:
		if os.path.exists(nou):
			os.remove(nou)


def _uneste_ct(pregatit, vechi):
	"""Pastreaza C/T dupa identitatea completa; satelitii raman cei ai listei alese."""
	noi = _citeste_baza(pregatit)
	chei = {k for k, t in vechi.transpondere.items() if t.fel in ("c", "t")}
	for k in chei:
		if k in noi.transpondere and noi.transpondere[k].fel not in ("c", "t"):
			raise ValueError("transponder conflict")
		noi.transpondere[k] = vechi.transpondere[k]
	servicii = {k: s for k, s in vechi.servicii.items() if s.tp_cheie in chei}
	noi.servicii.update(servicii)
	if chei or noi.versiune != 4 or not os.path.isfile(os.path.join(pregatit, "lamedb")):
		_scrie_atomic(os.path.join(pregatit, "lamedb"), noi.text().encode("utf-8", "surrogateescape"))
	# Se importa numai formatul nativ, fara o a doua lista cu date diferite.
	cale5 = os.path.join(pregatit, "lamedb5")
	if os.path.isfile(cale5):
		os.remove(cale5)
	return set(servicii)


def _buchete_ct(dest, chei, pastrate):
	"""Pastreaza buchetele mixte, parintii si copiii lor, inclusiv alternativele si ciclurile."""
	D = _date_lamedb()
	legaturi, ct = {}, set()
	def local(nume):
		return bool(D._NUME_FISIER.match(nume))

	pendinte = [n for n in os.listdir(dest) if local(n) and n.endswith((".tv", ".radio"))
		and n.startswith(("userbouquet.", "subbouquet.", "alternatives."))]
	indexuri = {}
	for index in INDEXURI:
		cale = os.path.join(dest, index)
		text = ""
		if os.path.lexists(cale):
			if os.path.islink(cale) or not os.path.isfile(cale):
				raise ValueError("index not regular")
			with io.open(cale, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
				text = f.read()
		intrari = D.citeste_buchet(index, text, lambda: 0).intrari
		indexuri[index] = [(i.fisier, "#SERVICE " + i._ref_brut) for i in intrari
			if i.fisier and local(i.fisier) and i.fel in ("subbuchet", "alternative")]
		pendinte.extend(n for n, _r in indexuri[index])
	while pendinte:
		nume = pendinte.pop()
		if nume in legaturi:
			continue
		cale = os.path.join(dest, nume)
		if os.path.islink(cale):
			raise ValueError("bouquet link")
		if not os.path.exists(cale):
			continue
		if not os.path.isfile(cale):
			raise ValueError("bouquet not regular")
		copii = set()
		with io.open(cale, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
			text = f.read()
		for intrare in D.citeste_buchet(nume, text, lambda: 0).intrari:
			r = intrare.r
			if r.k5() in chei:
				ct.add(nume)
			f = r.fisier()
			if f and local(f) and r.fel() in ("subbuchet", "alternative"):
				copii.add(f)
		legaturi[nume] = copii
		pendinte.extend(copii - legaturi.keys())
	# Parintii raman si cand numai un sub-buchet contine canale C/T.
	while True:
		parinti = {n for n, copii in legaturi.items() if copii & ct} - ct
		if not parinti:
			break
		ct.update(parinti)
	rez = list(pastrate)
	vazute = {n for _i, n, _r in rez}
	for index in INDEXURI:
		for nume, rand in indexuri[index]:
			if nume in ct and nume not in vazute:
				vazute.add(nume)
				rez.append((index, nume, rand))
	# Cele nelegate raman nelegate, dar fisierele lor nu se suprascriu nici la acelasi nume.
	vazute.update(ct)
	# Numai graful C/T primeste protectia noua; ceilalti sateliti se inlocuiesc ca inainte.
	pendinte = list(ct)
	parcurse = set(ct)
	while pendinte:
		for nume in legaturi.get(pendinte.pop(), ()):
			if nume in legaturi and nume not in parcurse:
				parcurse.add(nume)
				vazute.add(nume)
				pendinte.append(nume)
	# Indexurile principale raman cele ale listei alese, chiar intr-un ciclu.
	return rez, vazute - set(INDEXURI)


def _importa_sigur(pregatit, dest, text_setari, sursa, dupa_import=None):
	"""Foloseste copia exacta a importului; pune la loc toate fisierele atinse la eroare."""
	I = _I()
	plan = fisiere_lista(pregatit) | set(INDEXURI) | {I.NUME_ORIGINE}
	for nume in plan:
		cale = os.path.join(dest, nume)
		if os.path.lexists(cale + ".nou") or os.path.islink(cale) or (os.path.lexists(cale) and not os.path.isfile(cale)):
			raise ValueError("destination unavailable")
	inainte = {n for n in plan if os.path.isfile(os.path.join(dest, n))}
	copie = []

	def salveaza(d):
		r = I.copie_de_siguranta(d, text_setari=text_setari)
		if not r[2]:
			copie.append(r[0])
		return r

	try:
		rez = I.importa(pregatit, {"canale": True}, dest=dest, text_setari=text_setari, sursa=sursa, copie=salveaza)
		if rez.get("ok"):
			if dupa_import is not None:
				dupa_import(copie[0])
			return rez
	except Exception:
		if not copie:
			raise
	if copie:
		erori = []
		for nume in sorted(plan, key=lambda n: n == "lamedb"):
			try:
				cale = os.path.join(dest, nume)
				if nume in inainte:
					with open(os.path.join(copie[0], nume), "rb") as f:
						date = f.read()
					aceleasi = False
					if os.path.isfile(cale):
						with open(cale, "rb") as f:
							aceleasi = f.read() == date
					if not aceleasi:
						_scrie_atomic(cale, date)
				elif os.path.isfile(cale):
					os.remove(cale)
				if os.path.isfile(cale + ".nou"):
					os.remove(cale + ".nou")
			except OSError:
				erori.append(nume)
		if erori:
			return {"ok": False, "canale": 0, "mesaje": [_("Instalarea s-a oprit. Punerea la loc nu s-a terminat; "
				"copia de siguranță este în %s.") % os.path.basename(copie[0])]}
		# Keep the previous installation and its undo visible after a complete rollback.
		try:
			_scrie_atomic(os.path.join(copie[0], SEMN), b'{"esec_revenit": true}')
		except OSError:
			pass
		return {"ok": False, "canale": 0, "mesaje": [_("Instalarea nu a mers. Lista de dinainte a fost pusă la loc.")]}
	return rez


def nume_buchet(dest, nume):
	"""Numele aratat al buchetului (randul #NAME din fisierul lui), altfel numele fisierului fara userbouquet si tip."""
	for rand in (_randuri(os.path.join(dest, nume)) or "").splitlines()[:5]:
		if rand.upper().startswith("#NAME "):
			text = rand[6:].strip()
			if text:
				return text
	return re.sub(r"^userbouquet\.|\.(tv|radio)$", "", nume)


def _rand_index(index, nume):
	tip = 2 if index.endswith(".radio") else 1
	return '#SERVICE 1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % (tip, nume)


def pastrate_in_pregatire(dosar, pastrate):
	"""In dosarul pregatit de import (cel din care se copiaza): fisierele listei cu acelasi nume ca ale omului ies (ale
	omului raman pe receptor), iar randurile lor intra in index (favoritele sus, buchetele de internet la sfarsit).
	Intoarce numele pastrate."""
	nume_pastrate = []
	for index, nume, rand in pastrate:
		cale = os.path.join(dosar, nume)
		if os.path.isfile(cale) and not os.path.islink(cale):
			os.remove(cale)
		cale_index = os.path.join(dosar, index)
		text = _randuri(cale_index)
		if text is None:
			continue
		randuri = text.splitlines()
		# Enigma2 nu citeste randurile aflate dupa primul rand gol.
		sfarsit = next((i for i, r in enumerate(randuri) if not r), len(randuri))
		are = set(m.group(1) for m in (TIPAR_RAND_INDEX.match(r.strip()) for r in randuri[:sfarsit]) if m)
		nume_pastrate.append(nume)
		if nume in are:
			continue
		capat = "\r\n" if "\r\n" in text else "\n"
		rand_nou = rand or _rand_index(index, nume)
		if nume in FAVORITE:
			loc = 1 if randuri and randuri[0].upper().startswith("#NAME") else 0
			randuri.insert(loc, rand_nou)
		else:
			randuri.insert(sfarsit, rand_nou)
		with io.open(cale_index + ".nou", "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
			f.write(capat.join(randuri) + capat)
		os.replace(cale_index + ".nou", cale_index)
	return nume_pastrate


# ---------------------------------------------------------------- instalarea si punerea la loc (firul lor)

def fisiere_lista(dest=CALE_ETC):
	"""Numele fisierelor listei de canale de pe receptor (ce poate aduce o lista)."""
	I = _I()
	try:
		nume = os.listdir(dest)
	except OSError:
		return set()
	return set(n for n in nume if (n in I.FISIERE_CANALE or TIPAR_BUCHET.match(n))
		and os.path.isfile(os.path.join(dest, n)))


def _copii(dest):
	I = _I()
	return set(d for d in glob.glob(os.path.join(dest, I.PREFIX_COPIE_RECEPTOR + "*")) if os.path.isdir(d))


def _scrie_semn(dosar_copie, date):
	_scrie_atomic(os.path.join(dosar_copie, SEMN), json.dumps(date, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def ultima_instalare(dest=CALE_ETC):
	"""(dosarul copiei, semnul) cand cea mai noua copie de siguranta a receptorului e a unei instalari de aici, altfel
	(None, None). O copie mai noua (alt import, o punere la loc) inseamna ca lista s-a schimbat de atunci: punerea la loc
	ar sterge si schimbarea aceea, deci nu se mai ofera (ramane copia, in Import canale si setari)."""
	I = _I()
	copii = sorted(d for d in glob.glob(os.path.join(dest, I.PREFIX_COPIE_RECEPTOR + "*"))
		if os.path.isdir(d) and not os.path.islink(d))
	if not copii:
		return None, None
	for dosar in reversed(copii):
		try:
			with io.open(os.path.join(dosar, SEMN), "r", encoding="utf-8") as f:
				semn = json.load(f)
		except (OSError, IOError, ValueError):
			return None, None
		if isinstance(semn, dict) and semn.get("esec_revenit") is True:
			continue
		return (dosar, semn) if isinstance(semn, dict) else (None, None)
	return None, None


def _salveaza_arhiva(lista, date, dosar):
	if os.path.islink(dosar):
		raise EroareDescarcare(_("Fișierul descărcat nu se poate scrie pe receptor."))
	shutil.rmtree(dosar, ignore_errors=True)
	os.makedirs(dosar)
	nume = re.sub(r"[^A-Za-z0-9._-]+", "_", "%s-%s" % (lista["autor"], lista["id"].split(":", 1)[-1]))[:120]
	if not nume.lower().endswith(".zip"):
		nume += ".zip"
	cale = os.path.join(dosar, nume)
	with open(cale, "wb") as f:
		f.write(date)
	return cale


def sursa_descarcata(lista, cale, dosar):
	"""Arhiva descarcata ca sursa a importului (ca arhiva trimisa din calculator), sau None cand nu are canale."""
	I = _I()
	try:
		if not zipfile.is_zipfile(cale):
			return None
	except OSError:
		return None
	gasite = I.cauta_pe_mediu({"fel": "calculator", "punct": dosar, "eticheta": ""}, time.time() + I.TERMEN_S,
		adancime=0, max_arhiva=MAX_DESCARCARE)
	for s in gasite:
		# o lista de canale are lamedb; buchetele singure ar lasa lista veche cu indexul altei liste
		if s.get("cale") == cale and s.get("canale"):
			s["mediu"] = "internet"
			s["mediu_nume"] = _("Descărcată de pe internet")
			return s
	return None


def instaleaza(lista, text_setari=None, dest=CALE_ETC, dosar=DOSAR_DESCARCARI, citeste_url=None, dest_tmp=None, anulat=None):
	"""Tine importul ocupat pana se termina pregatirea, revenirea si semnul copiei."""
	with _I()._InLucru():
		return _instaleaza(lista, text_setari, dest, dosar, citeste_url, dest_tmp, anulat)


def _instaleaza(lista, text_setari, dest, dosar, citeste_url, dest_tmp, anulat=None):
	"""Pe firul instalarii: descarcarea, verificarea, apoi importul canalelor (copia de siguranta, scrierea), cu
	favoritele si buchetele de internet ale omului pastrate, si semnul in copie. Lista nu se reincarca aici
	(incheie_importul, pe firul enigma2). Intoarce rezultatul importului, cu "lista" si "pastrate"."""
	I = _I()
	dest_tmp = dest_tmp or I.DOSAR_TMP
	citeste_url = citeste_url or citeste
	lucru = None
	try:
		try:
			date = citeste_url(lista["url"], MAX_DESCARCARE, total_s=TERMEN_TOTAL_S)
			if anulat and anulat():
				return _fara_actualizare()
			if lista.get("sha"):
				sha = hashlib.sha1(b"blob " + str(len(date)).encode("ascii") + b"\0" + date).hexdigest()
				if sha != lista["sha"]:
					raise EroareDescarcare(text_schimbata())
			lucru = tempfile.mkdtemp(prefix=os.path.basename(dosar) + "-", dir=os.path.dirname(dosar))
			cale = _salveaza_arhiva(lista, date, lucru)
		except EroareDescarcare as eroare:
			return {"ok": False, "mesaje": [_("Descărcarea nu a mers: %s") % eroare]}
		except (OSError, IOError):
			return {"ok": False, "mesaje": [_("Descărcarea nu a mers: %s") %
				_("Fișierul descărcat nu se poate scrie pe receptor.")]}
		sursa = sursa_descarcata(lista, cale, lucru)
		if sursa is None:
			return {"ok": False, "mesaje": [_("Fișierul descărcat nu are o listă de canale.")]}
		pastrate = buchete_de_pastrat(dest)
		inainte = fisiere_lista(dest)
		try:
			pregatit, motiv = I.pregateste(sursa, dest_tmp)
			if pregatit is None:
				return {"ok": False, "mesaje": [_("Importul nu a pornit: %s.") % motiv]}
			baza_stricata = False
			try:
				vechi = _citeste_baza(dest)
			except _date_lamedb().Stricat:
				# O lista valida poate repara baza locala; copia pastreaza octetii originali.
				vechi = _date_lamedb().Lamedb()
				baza_stricata = True
			chei_ct = _uneste_ct(pregatit, vechi)
			pastrate, protejate = _buchete_ct(dest, chei_ct, pastrate)
			for nume in protejate:
				cale_b = os.path.join(pregatit, nume)
				if os.path.isfile(cale_b):
					os.remove(cale_b)
			nume_pastrate = pastrate_in_pregatire(pregatit, pastrate)
			lista_instalata = {"id": lista["id"], "autor": lista["autor_nume"], "nume": lista["nume"], "data": lista["data"]}
			lista_instalata.update(varianta=varianta(lista), sha=lista.get("sha", ""), timp=lista.get("timp", 0))
			def semn_instalare(copie):
				_scrie_semn(copie, {"lista": lista_instalata,
					"cand": int(time.time()), "fisiere_noi": sorted(fisiere_lista(dest) - inainte)})

			if anulat and anulat():
				return _fara_actualizare()
			rez = _importa_sigur(pregatit, dest, text_setari, sursa, semn_instalare)
		except (OSError, ValueError):
			return {"ok": False, "mesaje": [_("Instalarea nu a pornit: listele de canale nu s-au putut pregăti în siguranță.")]}
		finally:
			I.curata_tmp(dest_tmp)
		rez["lista"] = lista_instalata
		rez["pastrate"] = nume_pastrate
		rez["ct_pastrate"] = len(chei_ct) if rez.get("ok") else 0
		if rez.get("canale"):
			mesaje = rez.setdefault("mesaje", [])
			mesaje.insert(0, _("Lista %s e instalată. Lista de dinainte e păstrată și se poate pune la loc.")
				% ("%s: %s" % (lista["autor_nume"], lista["nume"])))
			if baza_stricata:
				rez["baza_stricata"] = True
				mesaje.insert(1, _("Lista locală era deteriorată. Am păstrat copia exactă, dar canalele de cablu și terestre nu au putut fi recuperate."))
			elif chei_ct:
				mesaje.insert(1, _("Am păstrat canalele tale de cablu și terestre și buchetele care le folosesc."))
			elif nume_pastrate:
				mesaje.insert(1, _("Am păstrat favoritele și buchetele tale de internet: %s.")
					% ", ".join(nume_buchet(dest, n) for n in nume_pastrate))
		return rez
	finally:
		if lucru is not None:
			shutil.rmtree(lucru, ignore_errors=True)


def _in_index(dest):
	rez = set()
	for index in INDEXURI:
		for rand in (_randuri(os.path.join(dest, index)) or "").splitlines():
			m = TIPAR_RAND_INDEX.match(rand.strip())
			if m:
				rez.add(m.group(1))
	return rez


def pune_la_loc(dosar_copie, semn, text_setari=None, dest=CALE_ETC):
	"""Pe firul lucrarii: lista din copia facuta la instalare se importa inapoi, fisierele aduse de lista care nu erau
	in copie si nu mai sunt in index se sterg, semnul se scoate."""
	I = _I()
	sursa = None
	for s in I.copii_receptor(dest):
		if os.path.normpath(s["cale"]) == os.path.normpath(dosar_copie):
			sursa = s
			break
	if sursa is None or not sursa.get("canale"):
		return {"ok": False, "mesaje": [_("Nu este nicio listă de pus la loc.")]}
	rez = I.importa(dosar_copie, {"canale": True}, dest=dest, text_setari=text_setari, sursa=sursa)
	if rez.get("canale"):
		in_copie = set(os.listdir(dosar_copie))
		folosite = _in_index(dest)
		sterse = 0
		for nume in (semn or {}).get("fisiere_noi") or []:
			if not (TIPAR_BUCHET.match(nume) or nume in I.FISIERE_CANALE) or nume in in_copie or nume in folosite:
				continue
			cale = os.path.join(dest, nume)
			if os.path.isfile(cale) and not os.path.islink(cale):
				try:
					os.remove(cale)
					sterse += 1
				except OSError:
					pass
		rez["sterse"] = sterse
		try:
			os.remove(os.path.join(dosar_copie, SEMN))
		except OSError:
			pass
		rez.setdefault("mesaje", []).insert(0, _("Lista de dinainte e pusă la loc."))
	return rez


# ---------------------------------------------------------------- starea comuna (televizor si web)

_AUTOMAT = False
_AUTO_GENERATIE = 0
_AUTO_CEAS = None
_AUTO_CITESTE = False
_AUTO_INCARCAT = False
_AUTO_ABONATI = []


def text_automat():
	if not _AUTO_INCARCAT:
		return _("Se citește opțiunea de actualizare automată...")
	return _("Actualizare automată: %s (MENU)") % (_("Da") if _AUTOMAT else _("Nu"))


def citeste_automat(dest=CALE_ETC):
	cale = os.path.join(dest, OPTIUNE_AUTO)
	if not os.path.lexists(cale):
		return False
	if os.path.islink(cale) or not os.path.isfile(cale):
		raise ValueError("automatic option not regular")
	with open(cale, "rb") as f:
		date = f.read(1025)
	if len(date) > 1024:
		raise ValueError("automatic option too large")
	date = json.loads(date.decode("utf-8"))
	if not isinstance(date, dict) or type(date.get("automat")) is not bool:
		raise ValueError("automatic option invalid")
	return date["automat"]


def salveaza_automat(activ, dest=CALE_ETC):
	"""Worker only; private atomic file, no global settings rewrite."""
	if type(activ) is not bool:
		raise ValueError("automatic option invalid")
	cale = os.path.join(dest, OPTIUNE_AUTO)
	if os.path.lexists(cale) and (os.path.islink(cale) or not os.path.isfile(cale)):
		raise ValueError("automatic option not regular")
	try:
		vechi = citeste_automat(dest)
	except (ValueError, UnicodeError):
		vechi = None
	if activ != vechi:
		_scrie_atomic(cale, json.dumps({"automat": activ}).encode("ascii"))
	return {"ok": True, "automat": activ, "mesaje": [_("Actualizarea automată este pornită.") if activ else
		_("Actualizarea automată este oprită.")]}


def _fara_actualizare():
	return {"ok": True, "mesaje": []}


def _cauta_actualizarea(dest, citeste_catalog=None):
	if not citeste_automat(dest):
		return None
	_dosar, semn = ultima_instalare(dest)
	instalata = (semn or {}).get("lista") or {}
	cheie = varianta(instalata)
	if not cheie:
		return None
	autor = _autor(cheie.split(":", 1)[0])
	noi = (citeste_catalog or catalog_autor)(autor)
	aceleasi = [l for l in noi if varianta(l) == cheie]
	if not aceleasi:
		return None
	noua = max(aceleasi, key=lambda l: l["timp"])
	vechi = time.mktime(time.strptime(instalata["data"], "%d.%m.%Y"))
	zi_noua = time.mktime(time.strptime(noua["data"], "%d.%m.%Y"))
	if instalata.get("sha") and noua.get("sha") == instalata["sha"]:
		return None
	if zi_noua < vechi or (zi_noua == vechi and (not instalata.get("sha") or not noua.get("sha"))):
		return None
	return noua


def actualizeaza(text_setari=None, dest=CALE_ETC, dosar=DOSAR_DESCARCARI, citeste_url=None,
		dest_tmp=None, citeste_catalog=None, anulat=None):
	"""Fresh author catalog, exact installed variant, shared backup and C/T import."""
	with _I()._InLucru():
		try:
			if (anulat and anulat()) or not citeste_automat(dest):
				return _fara_actualizare()
			noua = _cauta_actualizarea(dest, citeste_catalog)
			if noua is None:
				return _fara_actualizare()
			if anulat and anulat():
				return _fara_actualizare()
			return instaleaza(noua, text_setari, dest, dosar, citeste_url, dest_tmp, anulat)
		except (OSError, ValueError, KeyError, EroareDescarcare):
			return {"ok": False, "mesaje": [_("Actualizarea automată nu a mers. Lista instalată a rămas neschimbată.")]}


def porneste_setare_automat(activ, la_sfarsit=None):
	global _AUTO_GENERATIE
	if type(activ) is not bool:
		return "invalid", None

	def gata(rez):
		global _AUTOMAT, _AUTO_INCARCAT
		if rez and rez.get("ok"):
			_AUTOMAT = activ
			_AUTO_INCARCAT = True
			_anunta_automat()
			if activ and _AUTO_CEAS is not None:
				_AUTO_CEAS.start(1000, True)
		if la_sfarsit:
			la_sfarsit(rez)

	l = _porneste_lucrul("optiune", lambda text: salveaza_automat(activ), gata, cu_setari=False)
	if l is not None:
		_AUTO_GENERATIE += 1
	return ("pornit" if l is not None else "ocupat"), l


def porneste_actualizarea():
	"""Timer callback on the main thread; all file and network IO is on Lucrare."""
	global _AUTO_CITESTE
	if _AUTO_CITESTE:
		return None
	_AUTO_CITESTE = True
	generatie = _AUTO_GENERATIE
	lucrare, terminat = [], []

	def lucru():
		activ = citeste_automat()
		try:
			return activ, _cauta_actualizarea(CALE_ETC) if activ else None, False
		except (OSError, ValueError, KeyError, EroareDescarcare):
			return activ, None, True

	def gata(rez, eroare):
		global _AUTOMAT, _AUTO_CITESTE, _AUTO_INCARCAT
		terminat.append(True)
		_AUTO_CITESTE = False
		for l in lucrare:
			_scoate(l)
		if generatie != _AUTO_GENERATIE:
			return
		_AUTO_INCARCAT = True
		if isinstance(rez, tuple):
			_AUTOMAT, noua, esuat = rez
			if noua is not None:
				_porneste_lucrul("actualizare", lambda text: actualizeaza(text,
					citeste_catalog=lambda a: [noua], anulat=lambda: generatie != _AUTO_GENERATIE), None)
		else:
			esuat = True
		if esuat:
			_STARE["ultimul"] = {"ok": False, "mesaje": [_("Actualizarea automată nu a mers. Lista instalată a rămas neschimbată.")]}
		_anunta_automat()

	try:
		l = _I().Lucrare(lucru, gata)
	except Exception:
		_AUTO_CITESTE = False
		raise
	lucrare.append(l)
	_tine(l, terminat)
	return l


def _anunta_automat():
	for functie in list(_AUTO_ABONATI):
		try:
			functie()
		except Exception:
			pass


def demareaza_automat():
	"""One process timer, also when the TV list screen has never been opened."""
	global _AUTO_CEAS
	if _AUTO_CEAS is not None:
		return
	try:
		from enigma import eTimer
		ceas = eTimer()
		def tic():
			try:
				porneste_actualizarea()
			finally:
				ceas.start(INTERVAL_AUTO_S * 1000, True)
		ceas.callback.append(tic)
		_AUTO_CEAS = ceas
		ceas.start(1000, True)
	except ImportError:
		return

_STARE = {"liste": [], "erori": {}, "cand": 0, "incercat": 0, "citeste": False, "lucreaza": "", "ultimul": None}
_ZAVOR = threading.Lock()
_VII = []


def stare():
	return _STARE


def are_catalog_proaspat(acum=None):
	return bool(_STARE["liste"]) and (acum or time.time()) - _STARE["cand"] < TINUT_MINTE_S


def _de_citit(fortat, acum=None):
	"""O citire noua: ceruta de om, sau catalogul nu e proaspat si ultima incercare nu e de acum cateva minute (fara
	internet pagina web ar cere altfel o citire la fiecare intrebare)."""
	acum = acum or time.time()
	if fortat:
		return True
	if are_catalog_proaspat(acum):
		return False
	return acum - _STARE["incercat"] >= PAUZA_S


def uneste(vechi, noi, erori):
	"""Listele noi; ale autorilor care n-au raspuns acum raman cele citite inainte."""
	return list(noi) + [l for l in vechi if l["autor"] in erori]


def lista_dupa_id(id_lista):
	for l in _STARE["liste"]:
		if l["id"] == id_lista:
			return l
	return None


def _tine(l, terminat):
	if not terminat:
		_VII.append(l)


def _scoate(l):
	if l in _VII:
		_VII.remove(l)


def porneste_citirea(la_sfarsit=None, fortat=False):
	"""Citeste catalogul (pe firul lui) daca nu e proaspat; la_sfarsit() pe firul enigma2. None cand nu era nevoie sau
	o citire merge deja."""
	with _ZAVOR:
		if _STARE["citeste"] or not _de_citit(fortat):
			return None
		_STARE["citeste"] = True
		_STARE["incercat"] = time.time()
	lucrare, terminat = [], []

	def _gata(rez, eroare):
		terminat.append(True)
		if isinstance(rez, tuple):
			liste, erori = rez
		else:
			_jurnal("catalogul: %s" % eroare)
			liste, erori = [], dict((a["cheie"], "") for a in AUTORI)
		toate = uneste(_STARE["liste"], liste, erori)
		_STARE.update(liste=toate, erori=erori, cand=time.time() if liste else _STARE["cand"], citeste=False)
		for l in lucrare:
			_scoate(l)
		if la_sfarsit is not None:
			la_sfarsit()

	try:
		l = _I().Lucrare(catalog, _gata)
	except Exception:
		_STARE["citeste"] = False
		raise
	lucrare.append(l)
	_tine(l, terminat)
	return l


def _porneste_lucrul(fel, functie, la_sfarsit, cu_setari=True):
	I = _I()
	if not I.ocupa():
		return None
	_STARE["lucreaza"] = fel
	lucrare, terminat = [], []

	def _gata(rez, eroare):
		terminat.append(True)
		for l in lucrare:
			_scoate(l)

		def dupa(rezultat):
			_STARE["lucreaza"] = ""
			_STARE["ultimul"] = rezultat
			if la_sfarsit is not None:
				la_sfarsit(rezultat)
		I.incheie_importul(rez, eroare, dupa=dupa)

	try:
		text = I.text_setari_acum() if cu_setari else None
		l = I.Lucrare(lambda: functie(text), _gata)
	except Exception as eroare:
		_STARE["lucreaza"] = ""
		I.elibereaza({"ok": False, "mesaje": [_("Importul nu a pornit: %s.") % eroare]})
		raise
	lucrare.append(l)
	_tine(l, terminat)
	return l


def porneste_instalarea(id_lista, la_sfarsit=None):
	"""Pe firul enigma2: ("pornit"|"ocupat"|"necunoscuta", lucrarea)."""
	lista = lista_dupa_id(id_lista)
	if lista is None:
		return "necunoscuta", None
	l = _porneste_lucrul("instaleaza", lambda text: instaleaza(lista, text), la_sfarsit)
	return ("pornit" if l is not None else "ocupat"), l


def porneste_punerea_la_loc(la_sfarsit=None):
	"""Pe firul enigma2: ("pornit"|"ocupat"|"nimic", lucrarea)."""
	dosar, semn = ultima_instalare()
	if dosar is None:
		return "nimic", None
	l = _porneste_lucrul("pune", lambda text: pune_la_loc(dosar, semn, text), la_sfarsit)
	return ("pornit" if l is not None else "ocupat"), l


def lista_publica(l, ant=None):
	return {"id": l["id"], "autor": l["autor"], "autor_nume": l["autor_nume"], "nume": l["nume"], "data": l["data"],
		"fel": l["fel"], "terestru": l["terestru"], "potrivita": potrivire(l, ant) == 0 and bool(ant and (
			ant.get("pozitii") or ant.get("fel") == "motor")), "descriere": descriere(l, ant, cu_nume=False)}


def stare_publica(ant=None):
	"""Ce vad ecranul si pagina web (fara adresele de descarcare)."""
	_dosar, semn = ultima_instalare()
	ultimul = _STARE.get("ultimul") or None
	erori = _STARE.get("erori") or {}
	return {
		"automat": _AUTOMAT,
		"automat_incarcat": _AUTO_INCARCAT,
		"citeste": _STARE["citeste"],
		"lucreaza": _STARE["lucreaza"],
		"liste": [lista_publica(l, ant) for l in filtreaza(_STARE["liste"], "toate", "", ant)],
		"erori": [_("Nu am putut citi listele de la %s.") % text_autor(c) + (" " + t if t else "")
			for c, t in sorted(erori.items()) if c],
		"autori": [{"cheie": a["cheie"], "nume": a["nume"]} for a in AUTORI],
		"feluri": [{"cheie": f, "nume": text_fel(f)} for f in FELURI],
		"fel_implicit": fel_implicit(ant),
		"instalata": (semn or {}).get("lista"),
		"instalata_text": text_instalata(semn),
		"poate_pune_la_loc": semn is not None,
		"ultimul": {"ok": bool(ultimul.get("ok")), "mesaje": list(ultimul.get("mesaje") or [])} if ultimul else None,
	}
