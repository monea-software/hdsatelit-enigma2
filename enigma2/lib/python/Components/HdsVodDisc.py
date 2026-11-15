# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Filme si seriale (VOD): sursa 'Pe disc'. Filmele de pe HDD, stick, USB si dosarele de retea montate, in acelasi ecran ca filmele
furnizorului IPTV (Screens/HdsFilmeSeriale.py), fara nimic de pus.

- Ce se cauta: inregistrarile receptorului (.ts, cu titlul si descrierea din .ts.meta) si fisierele video (mkv, mp4, avi, ts ...),
  in /media/<disc> si in locurile din retea deja montate (/media/net/*, /media/autofs/* montate). Cautarea ruleaza pe firul de lucru,
  cu plafon de timp si de fisiere, si se tine minte INDEX_S secunde.
- Numele: HdsSubtitrariInternet/film.informatii (titlul fara calitate si codec, anul, S01E02 / 1x02). Episoadele aceluiasi titlu fac
  un serial, cu sezoanele in ordine; un fisier numit numai 'S01E02' ia numele dosarului (peste 'Season 1' / 'Sezonul 1').
- Afisul, in ordine: poza de langa film (<nume>.jpg, poster.jpg, folder.jpg, cover.jpg), afisul din fisa filmului (HdsDespreFilm:
  Wikidata si Wikipedia, fara cheie; adusa numai pentru afisele care se vad, pe firul pozelor), imaginea din film (captura facuta de
  player la prima redare, grab -v), altfel un afis desenat cu titlul. ffmpeg-ul imaginii e numai pentru sunet: nu scoate cadre.
- Redarea: direct din fisier (1: pentru .ts, 4097: pentru restul), deci reluarea, .cuts si subtitrarile de langa film merg ca la
  lista de filme.
"""
import hashlib
import json
import os
import re
import threading
import time

from Components import HdsVod as V

SID = "d15c0001"                 # sursa 'Pe disc': un singur id, fix (8 hex, ca sursele IPTV)
RADACINI = ["/media"]
EXT_FILM = frozenset((".ts", ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".m2ts", ".mts", ".mpg", ".mpeg", ".wmv", ".webm", ".flv",
	".vob", ".divx", ".ogm"))
MIN_OCTETI = 30 * 1024 * 1024    # sub atat e o mostra sau un trailer (inregistrarile .ts au .meta si raman)
MAX_FISIERE = 6000
MAX_ADANCIME = 6
TERMEN_CAUTARE_S = 25
INDEX_S = 600
MAX_FISE = 400
CADRU_DUPA_S = 120
_SARITE = frozenset(("lost+found", "$recycle.bin", "system volume information", "picon", "piconuri", "timeshift", "backup",
	"logs", "epg", "swap", "tmp", "trash", ".trash", "recycler", "found.000", "@eadir", "#recycle"))
_SEZON_DOSAR = re.compile(r"(?i)^(season|sezonul|sezon|staffel|saison|temporada|stagione|series)\s*\d{1,3}$|^s\d{1,2}$")
_ID = re.compile(r"^[0-9a-z]{1,24}$")
POZE_LANGA = ("poster.jpg", "folder.jpg", "cover.jpg", "poster.png", "folder.png")
DOSAR_CADRE = ".hds-vod"
DOSAR_CADRE_TMP = "/tmp/hds-vod-cadre"
CALE_FISE = "/etc/enigma2/hds_vod_disc.json"


def N_(text):
	return text


T_TOATE = N_("Toate filmele")
T_TOATE_SERIALE = N_("Toate serialele")
T_INREGISTRARI = N_("Înregistrări")
T_RETEA = N_("Rețea: %s")
E_GOL = N_("Nu am găsit filme pe discuri, stick-uri sau în locurile din rețea.")


def _id(text):
	return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


def _cheieSerial(titlu):
	return "".join(c for c in titlu.casefold() if c.isalnum())


def _film():
	from Components.HdsSubtitrariInternet import film
	return film


# ------------------------------------------------------------------ locurile si cautarea

def locuri():
	"""[(cale, eticheta)]: discurile montate in /media si locurile din retea montate, fara dubluri (hdd -> sda1)."""
	rez, vazute = [], set()
	for r in RADACINI:
		try:
			nume = sorted(os.listdir(r))
		except OSError:
			continue
		for n in nume:
			cale = os.path.join(r, n)
			if n in ("net", "autofs"):
				try:
					sub = sorted(os.listdir(cale))
				except OSError:
					sub = []
				for s in sub:
					c = os.path.join(cale, s)
					# un loc autofs nemontat nu se atinge: l-ar monta (si un server oprit ar tine firul pe loc)
					if _montat(c):
						rez.append((c, V._tradus(T_RETEA) % s))
				continue
			if n.startswith(".") or not _montat(cale):
				continue
			rez.append((cale, n.upper() if n in ("hdd", "usb") else n))
	fara = []
	for cale, eticheta in rez:
		real = os.path.realpath(cale)
		if real not in vazute:
			vazute.add(real)
			fara.append((cale, eticheta))
	return fara


def _montat(cale):
	try:
		return os.path.ismount(cale) or (RADACINI != ["/media"] and os.path.isdir(cale))
	except OSError:
		return False


def _citesteMeta(cale):
	"""Inregistrarea receptorului: (titlu, descriere, ora) din .ts.meta, sau None."""
	try:
		with open(cale + ".meta", "rb") as f:
			randuri = f.read(8192).decode("utf-8", "replace").split("\n")
	except (IOError, OSError):
		return None
	titlu = V._text(randuri[1] if len(randuri) > 1 else "", 200)
	if not titlu:
		return None
	try:
		ora = int(randuri[3]) if len(randuri) > 3 and randuri[3].strip() else 0
	except ValueError:
		ora = 0
	return titlu, V._text(randuri[2] if len(randuri) > 2 else "", 600), ora


def _numeDosar(cale):
	"""Numele serialului din dosare, peste 'Season 1'."""
	d = os.path.dirname(cale)
	for _i in range(3):
		n = os.path.basename(d)
		if not n:
			return ""
		if not _SEZON_DOSAR.match(n.strip()):
			return _film().informatii(n + ".mkv")["titlu"] or n
		d = os.path.dirname(d)
	return ""


def analizeaza(cale, marime=0, ora=0):
	"""Un fisier -> dict: titlu, an, sezon, episod, inregistrare, descriere, adaugat."""
	info = _film().informatii(cale)
	rez = {"cale": cale, "titlu": info["titlu"], "an": info["an"] or "", "sezon": info["sezon"], "episod": info["episod"],
		"inregistrare": False, "descriere": "", "adaugat": int(ora or 0), "marime": marime}
	if cale.lower().endswith(".ts"):
		m = _citesteMeta(cale)
		if m:
			rez.update(titlu=m[0], descriere=m[1], inregistrare=True, sezon=None, episod=None)
			if m[2]:
				rez["adaugat"] = m[2]
			rez["an"] = ""
	if rez["sezon"] is not None and (not info["titlu"] or info["titlu"] == info["release"] or re.match(r"(?i)^s\d", info["titlu"])):
		rez["titlu"] = _numeDosar(cale) or rez["titlu"]
	return rez


def cauta(radacini=None, termen=TERMEN_CAUTARE_S):
	"""-> (fisiere [(cale, marime, ora, loc)], locuri). Cel mult MAX_FISIERE, cel mult `termen` secunde."""
	inceput = time.monotonic()
	gasite, loc = [], locuri() if radacini is None else radacini
	for radacina, eticheta in loc:
		stiva = [(radacina, 0)]
		while stiva:
			if len(gasite) >= MAX_FISIERE or time.monotonic() - inceput > termen:
				return gasite, loc
			dosar, adancime = stiva.pop()
			try:
				intrari = list(os.scandir(dosar))
			except OSError:
				continue
			for e in intrari:
				n = e.name
				if n.startswith(".") or n.lower() in _SARITE:
					continue
				try:
					if e.is_dir(follow_symlinks=False):
						if adancime < MAX_ADANCIME:
							stiva.append((e.path, adancime + 1))
						continue
					ext = os.path.splitext(n)[1].lower()
					if ext not in EXT_FILM:
						continue
					st = e.stat()
				except OSError:
					continue
				if st.st_size < MIN_OCTETI and not (ext == ".ts" and os.path.exists(e.path + ".meta")):
					continue
				gasite.append((e.path, st.st_size, int(st.st_mtime), radacina))
	return gasite, loc


def grupeaza(fisiere):
	"""Fisierele -> (filme {id: titlu}, seriale {id: serial}). Serialul: nume, an, adaugat, loc, sezoane {numar: [episoade]}."""
	filme, seriale = {}, {}
	for cale, marime, ora, loc in fisiere:
		a = analizeaza(cale, marime, ora)
		if a["sezon"] is not None and a["episod"] is not None:
			k = _cheieSerial(a["titlu"]) or _id(os.path.dirname(cale))
			sid = _id("serial/" + k)
			s = seriale.setdefault(sid, {"id": sid, "nume": a["titlu"], "an": a["an"], "adaugat": 0, "loc": loc,
				"dosar": os.path.dirname(cale), "sezoane": {}})
			s["adaugat"] = max(s["adaugat"], a["adaugat"])
			ep = dict(a, id=_id(cale), loc=loc)
			s["sezoane"].setdefault(a["sezon"], []).append(ep)
		else:
			fid = _id(cale)
			filme[fid] = dict(a, id=fid, loc=loc)
	for s in seriale.values():
		for lista in s["sezoane"].values():
			lista.sort(key=lambda e: (e["episod"], e["cale"]))
	return filme, seriale


# ------------------------------------------------------------------ afisele

_lacatFise = threading.Lock()
_fise = None                     # cale -> {"afis": adresa, "descriere", "gen", "regia", "actori", "an", "nota"} sau {} (negasit)


def _incarcaFise():
	global _fise
	if _fise is None:
		try:
			with open(CALE_FISE, encoding="utf-8") as f:
				d = json.load(f)
			_fise = d if isinstance(d, dict) else {}
		except (IOError, OSError, ValueError):
			_fise = {}
	return _fise


def fisaTinuta(cale):
	with _lacatFise:
		return _incarcaFise().get(cale)


def _tine(cale, fisa):
	with _lacatFise:
		d = _incarcaFise()
		d[cale] = fisa
		while len(d) > MAX_FISE:
			d.pop(next(iter(d)))
		try:
			from Components import HdsIptvSurse as I
			I._scrie(CALE_FISE, json.dumps(d, ensure_ascii=False).encode("utf-8"), 0o644)
		except (IOError, OSError, ImportError):
			pass


def cautaFisa(titlu, an="", descriere=""):
	"""Pe fir. Fisa filmului din HdsDespreFilm (Wikidata + Wikipedia) -> dict sau {} (negasit). None = nu se poate acum (fara retea,
	modulul lipsa): se incearca alta data."""
	try:
		from Components import HdsDespreFilm as D
	except ImportError:
		return None
	info = D.dinText("%s (%s)" % (titlu, an) if an else titlu, descriere or u"")
	if not info:
		return {}
	r = D.cauta(info)
	if r.get("stare") == "alege":
		cand = [c for c in r.get("candidati") or [] if an and str(c.get("an") or "") == str(an)]
		if len(cand) != 1:
			return {}
		r = D.deschide(cand[0])
	if r.get("stare") == "eroare":
		return None
	f = r.get("fisa")
	if r.get("stare") != "gata" or not f:
		return {}
	return {"afis": f.get("afis_adresa") or "", "descriere": V._text(f.get("rezumat") or f.get("descriere_scurta"), 1500),
		"gen": ", ".join(f.get("genuri") or [])[:120], "regia": ", ".join(f.get("regie") or [])[:120],
		"actori": ", ".join(f.get("actori") or [])[:300], "an": str(f.get("an") or ""), "titlu": V._text(f.get("titlu"), 200)}


def fisa(cale, titlu, an="", descriere=""):
	"""Fisa tinuta minte sau cautata acum (pe fir)."""
	f = fisaTinuta(cale)
	if f is not None:
		return f
	f = cautaFisa(titlu, an, descriere)
	if f is None:
		return {}
	_tine(cale, f)
	return f


def pozaLanga(cale):
	"""O poza pusa de om langa film: <nume>.jpg/.png sau poster/folder/cover din dosar (si din dosarul serialului)."""
	baza = os.path.splitext(cale)[0]
	for ext in (".jpg", ".png", "-poster.jpg"):
		if os.path.isfile(baza + ext):
			return baza + ext
	d = os.path.dirname(cale)
	for _i in range(2):
		for n in POZE_LANGA:
			p = os.path.join(d, n)
			if os.path.isfile(p):
				return p
		if not _SEZON_DOSAR.match(os.path.basename(d)):
			break
		d = os.path.dirname(d)
	return ""


def caleCadru(cale, loc=None):
	"""Unde sta imaginea din film: pe acelasi disc (dosar ascuns), altfel in /tmp."""
	nume = _id(cale) + ".jpg"
	if loc:
		return os.path.join(loc, DOSAR_CADRE, nume)
	return os.path.join(DOSAR_CADRE_TMP, nume)


def _cadruGata(cale, loc):
	for p in ((caleCadru(cale, loc), caleCadru(cale)) if loc else (caleCadru(cale),)):
		if os.path.isfile(p):
			return p
	return ""


def poza(t):
	"""Adresa afisului pentru HdsVodPoze: o cale locala sau 'cadru:<cale>#<n>'."""
	p = pozaLanga(t["cale"])
	if p:
		return p
	f = fisaTinuta(t["cale"])
	if f and f.get("afis"):
		return f["afis"]
	return "cadru:%s#%d" % (t["cale"], 1 if _cadruGata(t["cale"], t.get("loc")) else 0)


def cadru(cale):
	"""Pe firul pozelor (HdsVodPoze). Octetii afisului unui film fara poza: fisa (Wikidata), imaginea din film, afisul cu titlul."""
	loc = next((l for l, _e in locuri() if cale.startswith(l.rstrip("/") + "/")), None)
	gata = _cadruGata(cale, loc)
	if gata:
		with open(gata, "rb") as f:
			return f.read(3 * 1024 * 1024)
	a = analizeaza(cale)
	f = fisa(cale, a["titlu"], a["an"], a["descriere"]) if not a["sezon"] else {}
	if f.get("afis"):
		from Components import HdsVodPoze as P
		return P._citeste(f["afis"])
	return afisTitlu(a["titlu"])


def _font(marime):
	from PIL import ImageFont
	for c in ("/usr/share/fonts/Barlow-Bold.ttf", "/usr/share/fonts/nmsbd.ttf", "/usr/share/fonts/OpenSans-Bold.ttf", "/usr/share/fonts/DejaVuSans-Bold.ttf",
		"/usr/share/fonts/LiberationSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"):
		if os.path.isfile(c):
			try:
				return ImageFont.truetype(c, marime)
			except (IOError, OSError):
				pass
	return ImageFont.load_default()


def afisTitlu(titlu, latime=342, inaltime=513):
	"""Un afis simplu: degrade in culorile temei si titlul, pe randuri (JPEG)."""
	import io
	from PIL import Image, ImageDraw
	img = Image.new("RGB", (latime, inaltime))
	d = ImageDraw.Draw(img)
	for y in range(inaltime):
		k = y / float(inaltime)
		d.line([(0, y), (latime, y)], fill=(int(16 + 20 * k), int(30 + 24 * k), int(58 + 40 * k)))
	font = _font(34)
	cuvinte, randuri, rand = (titlu or "?").split(), [], ""
	for c in cuvinte:
		proba = (rand + " " + c).strip()
		if d.textlength(proba, font=font) <= latime - 40 or not rand:
			rand = proba
		else:
			randuri.append(rand)
			rand = c
	if rand:
		randuri.append(rand)
	randuri = randuri[:6]
	y = (inaltime - 44 * len(randuri)) // 2
	for r in randuri:
		w = d.textlength(r, font=font)
		d.text(((latime - w) / 2, y), r, font=font, fill=(242, 244, 248))
		y += 44
	b = io.BytesIO()
	img.save(b, "JPEG", quality=85)
	return b.getvalue()


def salveazaCadru(cale, loc=None):
	"""In timpul redarii (playerul): imaginea de pe ecran, numai video (grab -v), ca afis al filmului. -> calea sau ""."""
	if pozaLanga(cale) or _cadruGata(cale, loc):
		return ""
	import subprocess
	try:
		p = subprocess.run(["grab", "-q", "-s", "-v", "-j", "80", "-r", "480"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
			timeout=15)
	except (OSError, subprocess.SubprocessError):
		return ""
	date = p.stdout or b""
	if p.returncode != 0 or len(date) < 2000 or not date.startswith(b"\xff\xd8"):
		return ""
	for tinta in ((caleCadru(cale, loc), caleCadru(cale)) if loc else (caleCadru(cale),)):
		try:
			os.makedirs(os.path.dirname(tinta), exist_ok=True)
			with open(tinta + ".nou", "wb") as f:
				f.write(date)
			os.replace(tinta + ".nou", tinta)
			return tinta
		except (IOError, OSError):
			continue
	return ""


# ------------------------------------------------------------------ sursa

def _codeaza(cale):
	return cale.replace("%", "%25").replace(":", "%3a")


def referintaFisier(cale):
	return ("1:0:0:0:0:0:0:0:0:0:" if cale.lower().endswith(".ts") else "4097:0:0:0:0:0:0:0:0:0:") + _codeaza(cale)


class SursaDisc(V.Sursa):
	fel = "disc"
	grupa = "disc"
	cu_recente_locale = True

	def __init__(self):
		V.Sursa.__init__(self, {"id": SID, "nume": V._tradus(N_("Pe disc"))})
		self._lacat = threading.Lock()
		self._index = None               # (ora, filme, seriale, locuri)

	def idBun(self, x):
		return bool(_ID.match(x or ""))

	def index(self, nou=False):
		with self._lacat:
			if not nou and self._index and time.monotonic() - self._index[0] < INDEX_S:
				return self._index[1:]
		fisiere, loc = cauta()
		filme, seriale = grupeaza(fisiere)
		with self._lacat:
			self._index = (time.monotonic(), filme, seriale, loc)
		return filme, seriale, loc

	def _titluFilm(self, f):
		return {"id": f["id"], "cheie": "v" + f["id"], "nume": f["titlu"], "poza": poza(f), "nota": "", "an": f["an"],
			"adaugat": f["adaugat"]}

	def _titluSerial(self, s):
		prim = s["sezoane"][min(s["sezoane"])][0]
		p = pozaLanga(prim["cale"]) or poza(prim)
		return {"id": s["id"], "cheie": "", "nume": s["nume"], "poza": p, "nota": "", "an": s["an"], "adaugat": s["adaugat"]}

	def categorii(self, tip):
		filme, seriale, loc = self.index()
		lista = filme if tip == V.FILME else seriale
		if not lista:
			return []
		rez = [("toate", V._tradus(T_TOATE if tip == V.FILME else T_TOATE_SERIALE))]
		if tip == V.FILME and any(f["inregistrare"] for f in filme.values()):
			rez.append(("inreg", V._tradus(T_INREGISTRARI)))
		folosite = set(x["loc"] for x in lista.values())
		if len(folosite) > 1:
			for cale, eticheta in loc:
				if cale in folosite:
					rez.append(("l" + _id(cale)[:10], eticheta))
		return rez

	def _toate(self, tip):
		filme, seriale, _l = self.index()
		if tip == V.FILME:
			return [self._titluFilm(f) for f in sorted(filme.values(), key=lambda f: -f["adaugat"])]
		return [self._titluSerial(s) for s in sorted(seriale.values(), key=lambda s: -s["adaugat"])]

	def rand(self, tip, categorie):
		filme, seriale, _l = self.index()
		lista = list((filme if tip == V.FILME else seriale).values())
		if categorie == "inreg":
			lista = [f for f in lista if f.get("inregistrare")]
		elif categorie.startswith("l"):
			lista = [x for x in lista if "l" + _id(x["loc"])[:10] == categorie]
		elif tip == V.FILME and categorie == "toate":
			lista = [f for f in lista if not f.get("inregistrare")] or lista
		lista.sort(key=lambda x: -x["adaugat"])
		fa = self._titluFilm if tip == V.FILME else self._titluSerial
		return [fa(x) for x in lista[:V.MAX_RAND]]

	def toate(self, tip):
		for t in self._toate(tip):
			yield t

	def recente(self, tip):
		return self._toate(tip)[:V.MAX_RECENTE]

	def detalii(self, tip, titlu_id):
		filme, seriale, _l = self.index()
		if tip == V.FILME:
			f = filme.get(titlu_id)
			if f is None:
				raise V.C.EroareIptv(V.E_LIPSA)
			fi = {} if f["inregistrare"] else fisa(f["cale"], f["titlu"], f["an"], f["descriere"])
			p = poza(f)
			return {"id": f["id"], "tip": tip, "cheie": "v" + f["id"], "nume": f["titlu"],
				"descriere": f["descriere"] or fi.get("descriere", ""), "gen": fi.get("gen", ""), "tara": "",
				"regia": fi.get("regia", ""), "actori": fi.get("actori", ""), "nota": "", "an": f["an"] or fi.get("an", ""),
				"poster": p, "fundal": p if not p.startswith("cadru:") else "", "trailer": "", "varsta": "", "durata": 0,
				"video": "", "audio": "", "cale": f["cale"]}
		s = seriale.get(titlu_id)
		if s is None:
			raise V.C.EroareIptv(V.E_LIPSA)
		t = self._titluSerial(s)
		sezoane = []
		for numar in sorted(s["sezoane"]):
			ep = []
			for e in s["sezoane"][numar]:
				ep.append({"id": e["id"], "cheie": "e" + e["id"], "numar": str(e["episod"]),
					"nume": V._tradus(N_("Episodul %s")) % e["episod"], "descriere": "", "durata": 0, "poza": poza(e)})
			sezoane.append({"numar": str(numar), "episoade": ep})
		return {"id": s["id"], "tip": tip, "nume": s["nume"], "descriere": "", "gen": "", "tara": "", "regia": "", "actori": "",
			"nota": "", "an": s["an"], "poster": t["poza"], "fundal": "", "trailer": "", "varsta": "", "durata": 0, "sezoane": sezoane}

	def _cale(self, cheie):
		if not cheie or cheie[0] not in "ve":
			return None
		filme, seriale, _l = self.index()
		x = filme.get(cheie[1:])
		if x is None:
			for s in seriale.values():
				for lista in s["sezoane"].values():
					for e in lista:
						if e["id"] == cheie[1:]:
							x = e
		return x

	def referinta(self, cheie):
		x = self._cale(cheie)
		return referintaFisier(x["cale"]) if x and os.path.isfile(x["cale"]) else None

	def inRedare(self, cheie, pozitie, durata):
		"""Playerul, la 30 s: dupa CADRU_DUPA_S, o data, imaginea din film pentru afis (pe un fir, grab dureaza ~1 s)."""
		if pozitie is None or pozitie < CADRU_DUPA_S or cheie in getattr(self, "_cadre", set()):
			return
		self._cadre = getattr(self, "_cadre", set()) | {cheie}
		x = self._cale(cheie)
		if x is None:
			return
		fir = threading.Thread(target=salveazaCadru, args=(x["cale"], x.get("loc")), name="HdsVodDisc-cadru")
		fir.daemon = True
		fir.start()


_sursa = None


def sursa():
	"""Sursa 'Pe disc', una singura (indexul ei se tine minte)."""
	global _sursa
	if _sursa is None:
		_sursa = SursaDisc()
	return _sursa
