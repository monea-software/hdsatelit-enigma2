# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLocuriLista: locuri adaugate de extensii in lista de canale pe sateliti, ca un satelit: un rand la acelasi nivel cu Astra sau
# Cablu, cu dosarele extensiei sub el, canalele in buchete adevarate, pornite prin lista obisnuita, cu eticheta locului in dreapta
# randului (si in buchetele amestecate ale omului). Nimic din logica listei nu stie ce extensie e; IPTV are drumul lui, facut inainte.
#
# Ce face o extensie: la WHERE_AUTOSTART (se cheama si la instalare, cu needsRestart=False) cheama inregistreaza(...) cu locul ei.
# Registrul sta pe disc (/etc/enigma2/hds_locuri/<id>.json), cu ce trebuie ca locul sa fie curatat si cand extensia nu mai e:
# - buchetul radacina si prefixul grupelor (dosarele de sub rand), legate din bouquets.tv sau bouquets.radio;
# - marcajul caii: o bucata din adresa fiecarui canal al locului (de obicei o adresa locala 127.0.0.1:<port>/<cale>/);
# - eticheta (din dreapta randului) si felul (in panoul listei), date de extensie, deja traduse;
# - dosarul siglelor, cand extensia isi aduce singura siglele (numele fisierului: ca in Renderer/Picon.nume_sigle).
# Doua lucruri raman numai in memorie: la_intrare (chemata cand omul intra intr-un dosar al locului, ca grupa sa se umple atunci, nu
# toate odata) si text_gol (ce vede omul peste o grupa goala, „Se incarca...” sau eroarea).
#
# Dezinstalarea: pachetul sterge numai fisierele lui. La deschiderea listei si dupa opkg (Components/HdsExtensiiLucru.py),
# curataOrfane() gaseste locurile al caror dosar de plugin nu mai exista si scoate tot: randul din index, grupele si randurile
# canalelor din orice buchet, si din Favorite (un post fara extensia lui n-ar mai porni, iar omul n-ar sti de ce). Apoi reincarca
# buchetele, ca nucleul sa nu le scrie la loc din memorie.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau dosarele prin parametri.
import json
import os
import re

try:
	from Components import HdsCapLista as _Cap
except ImportError:  # probele de pe PC
	_Cap = None

DIRECTOR = "/etc/enigma2"
DOSAR = "/etc/enigma2/hds_locuri"
PLUGINURI = "/usr/lib/enigma2/python/Plugins"
_ID = re.compile(r"^[a-z0-9_]{1,32}\Z")
_FISIER = re.compile(r"^[A-Za-z0-9_.\-]{1,100}\Z")
_PLUGIN = re.compile(r"^(?:Extensions|SystemPlugins)/[A-Za-z0-9_]{1,64}\Z")
_MARCAJ = re.compile(r"^127\.0\.0\.1:[0-9]{1,5}/[A-Za-z0-9_\-]{1,32}/\Z")
_BUCHET = re.compile(r'FROM BOUQUET "([^"/]{1,100})"')
MODURI = {"tv": 1, "radio": 2}

_VII = {}          # id -> {"la_intrare": f, "text_gol": f}: ce a dat extensia in sesiunea asta
_CACHE = {"semn": None, "locuri": []}


def _jurnal(text):
	print("[HdsLocuriLista] %s" % text)


def _semn(cale):
	try:
		st = os.stat(cale)
		return (st.st_mtime, st.st_size, st.st_ino)
	except OSError:
		return None


def _scrie(cale, text):
	"""Atomic: un buchet taiat pe jumatate ar pierde canale."""
	nou = cale + ".nou"
	with open(nou, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
		f.write(text)
		f.flush()
		os.fsync(f.fileno())
	os.replace(nou, cale)


def _citeste(cale):
	try:
		with open(cale, encoding="utf-8", errors="surrogateescape", newline="") as f:
			return f.read()
	except (IOError, OSError):
		return None


def _valid(d):
	return (isinstance(d, dict) and bool(_ID.match(str(d.get("id")))) and d.get("mod") in MODURI and bool(_FISIER.match(str(d.get("buchet"))))
		and bool(_FISIER.match(str(d.get("prefix")))) and bool(_MARCAJ.match(str(d.get("marcaj")))) and bool(_PLUGIN.match(str(d.get("plugin"))))
		and isinstance(d.get("nume"), str) and bool(d["nume"]))


def _citesteRegistrul(dosar=DOSAR):
	rez = []
	try:
		nume = sorted(os.listdir(dosar))
	except OSError:
		return rez
	for n in nume:
		if not n.endswith(".json"):
			continue
		try:
			d = json.loads(_citeste(os.path.join(dosar, n)) or "")
		except ValueError:
			continue
		if _valid(d):
			rez.append(d)
	return rez


def locuri(mod=None, dosar=DOSAR, pluginuri=PLUGINURI):
	"""Locurile din registru ale caror extensii exista, in ordine stabila. Se citeste din nou numai cand registrul se schimba."""
	semn = _semn(dosar)
	if semn != _CACHE["semn"]:
		_CACHE["semn"] = semn
		_CACHE["locuri"] = _citesteRegistrul(dosar)
		_puneInCapLista(_CACHE["locuri"])
	rez = [d for d in _CACHE["locuri"] if os.path.isdir(os.path.join(pluginuri, d["plugin"]))]
	return [d for d in rez if mod is None or d["mod"] == mod]


def _puneInCapLista(lista):
	if _Cap is not None:
		_Cap.CAI_EXTRA[:] = [d["marcaj"] for d in lista]


def inregistreaza(id_loc, nume, mod, buchet, prefix, marcaj, eticheta, plugin, fel="", sigle="", la_intrare=None, text_gol=None,
		dosar=DOSAR, director=DIRECTOR):
	"""Locul unei extensii. Se poate chema la fiecare pornire: scrie numai ce s-a schimbat. -> True daca s-a schimbat ceva pe disc
	(atunci cine cheama reincarca buchetele, dupa ce isi scrie si grupele: reincarca())."""
	d = {"id": id_loc, "nume": nume, "mod": mod, "buchet": buchet, "prefix": prefix, "marcaj": marcaj, "eticheta": eticheta, "plugin": plugin,
		"fel": fel, "sigle": sigle}
	if not _valid(d):
		_jurnal("loc respins: %r" % (id_loc,))
		return False
	_VII[id_loc] = {"la_intrare": la_intrare, "text_gol": text_gol}
	schimbat = False
	os.makedirs(dosar, exist_ok=True)
	cale = os.path.join(dosar, id_loc + ".json")
	text = json.dumps(d, ensure_ascii=False, sort_keys=True)
	if _citeste(cale) != text:
		_scrie(cale, text)
		_CACHE["semn"] = None
		schimbat = True
	if sigle:
		try:
			os.makedirs(sigle, exist_ok=True)
		except OSError as e:
			_jurnal("dosarul siglelor: %s" % e)
	return _leagaIndex(d, director) or schimbat


def _randIndex(d):
	return '#SERVICE 1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet\r\n' % (MODURI[d["mod"]], d["buchet"])


def _leagaIndex(d, director=DIRECTOR):
	"""Randul radacinii in bouquets.<mod>, la sfarsit: numerele canalelor omului nu se muta. Nucleul incarca un buchet numai prin index."""
	cale = os.path.join(director, "bouquets." + d["mod"])
	text = _citeste(cale)
	if text is None:
		text = "#NAME Bouquets (%s)\r\n" % ("TV" if d["mod"] == "tv" else "Radio")
	if ('FROM BOUQUET "%s"' % d["buchet"]) in text:
		return False
	if text and not text.endswith("\n"):
		text += "\r\n"
	_scrie(cale, text + _randIndex(d))
	return True


def refRadacina(d):
	return '1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % (MODURI[d["mod"]], d["buchet"])


def fisierDinCale(cale):
	m = _BUCHET.search(cale or "")
	return m.group(1) if m else None


def locDosar(cale, mod=None):
	"""Locul caruia ii apartine un dosar (radacina sau o grupa), sau None."""
	fisier = fisierDinCale(cale)
	if not fisier:
		return None
	for d in locuri(mod):
		if fisier == d["buchet"] or fisier.startswith(d["prefix"]):
			return d
	return None


def locCanal(cale, mod=None):
	"""Locul unui canal, dupa bucata din adresa lui; merge si in buchetele amestecate ale omului."""
	if not cale:
		return None
	c = cale.replace("%3a", ":").replace("%3A", ":")
	for d in locuri(mod):
		if d["marcaj"] in c:
			return d
	return None


def etichete():
	"""[(marcaj, eticheta)] pentru ServiceList.setPathLabel."""
	return [(d["marcaj"], d["eticheta"]) for d in locuri() if d.get("eticheta")]


def dosareSigle():
	return [d["sigle"] for d in locuri() if d.get("sigle") and os.path.isdir(d["sigle"])]


def semnatura(mod=None):
	"""Se schimba cand se schimba locurile sau dosarele lor de sus: lista pe sateliti se reface."""
	return tuple((d["id"], _semn(os.path.join(DIRECTOR, d["buchet"]))) for d in locuri(mod))


def laIntrare(cale, gata):
	"""Omul intra intr-un dosar al unui loc. `gata()`: pe firul enigma2, cand grupa s-a schimbat. -> True cand extensia a preluat
	intrarea (lista nu mai intra in dosar)."""
	d = locDosar(cale)
	f = (_VII.get(d["id"]) or {}).get("la_intrare") if d else None
	if f is None:
		return False
	try:
		return bool(f(fisierDinCale(cale), gata))
	except Exception as e:
		_jurnal("la intrare: %s: %s" % (type(e).__name__, e))
		return False


def textGol(cale):
	"""Ce vede omul peste o grupa goala: „Se incarca...”, eroarea, sau nimic."""
	d = locDosar(cale)
	f = (_VII.get(d["id"]) or {}).get("text_gol") if d else None
	if f is None:
		return ""
	try:
		return f(fisierDinCale(cale)) or ""
	except Exception as e:
		_jurnal("text gol: %s: %s" % (type(e).__name__, e))
		return ""


def reincarca():
	"""Buchetele din nou in nucleu. Pe firul enigma2."""
	try:
		from enigma import eDVBDB
		eDVBDB.getInstance().reloadBouquets()
	except Exception as e:
		_jurnal("reincarcarea: %s: %s" % (type(e).__name__, e))


def _curataBuchet(text, marcaj_codat, buchet, prefix):
	"""Textul unui buchet fara randurile locului: canalele (dupa adresa) si legaturile spre dosarele lui, cu descrierea de sub ele."""
	rez = []
	sari = False
	schimbat = False
	for r in text.splitlines(True):
		if r.startswith("#SERVICE"):
			m = _BUCHET.search(r)
			fisier = m.group(1) if m else None
			sari = marcaj_codat in r.lower() or fisier == buchet or (fisier is not None and fisier.startswith(prefix))
			if sari:
				schimbat = True
				continue
		elif r.startswith("#DESCRIPTION") and sari:
			sari = False
			continue
		else:
			sari = False
		rez.append(r)
	return ("".join(rez), schimbat)


def _stergeLoc(d, director=DIRECTOR):
	marcaj = d["marcaj"].replace(":", "%3a").lower()
	try:
		nume = os.listdir(director)
	except OSError:
		return
	for n in nume:
		cale = os.path.join(director, n)
		if n == d["buchet"] or n.startswith(d["prefix"]):
			try:
				os.unlink(cale)
			except OSError as e:
				_jurnal("%s: %s" % (n, e))
			continue
		if n.endswith((".tv", ".radio")) and os.path.isfile(cale):
			text = _citeste(cale)
			if text is None:
				continue
			nou, schimbat = _curataBuchet(text, marcaj, d["buchet"], d["prefix"])
			if schimbat:
				_scrie(cale, nou)


def curataOrfane(dosar=DOSAR, director=DIRECTOR, pluginuri=PLUGINURI):
	"""Locurile fara extensie: scoase de tot. -> True daca s-a curatat ceva (buchetele s-au reincarcat)."""
	if not os.path.isdir(dosar):
		return False
	orfane = [d for d in _citesteRegistrul(dosar) if not os.path.isdir(os.path.join(pluginuri, d["plugin"]))]
	if not orfane:
		return False
	for d in orfane:
		_jurnal("extensia %s nu mai e: scot locul %s" % (d["plugin"], d["id"]))
		_stergeLoc(d, director)
		_VII.pop(d["id"], None)
		try:
			os.unlink(os.path.join(dosar, d["id"] + ".json"))
		except OSError as e:
			_jurnal("registrul: %s" % e)
	_CACHE["semn"] = None
	if dosar == DOSAR:
		reincarca()
	return True
