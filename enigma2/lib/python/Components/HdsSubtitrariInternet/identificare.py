# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# identificare.py: filmul de pe un canal TV (sau dintr-o inregistrare .ts), din ghidul programelor (EIT), pentru cautarea
# subtitrarilor dupa ID-ul lui IMDb (tv.py).
#
# 1. Din EIT (dinEveniment, fara retea): titlul, anul (in textul scurt "Spielfilm USA 2006", "Action, USA 2016",
#    "(2019)", "SUA, 2019", apoi in cel lung; nu datele de difuzare, zi.luna.an), titlul original (in paranteza dupa
#    tara si an sau in titlu, "Originaltitel:", "Titlu original:"), regizorul ("Regie:", "Regia:", "Director:"), durata.
# 2. Wikidata, fara cheie (cauta, pe fir): wbsearchentities cu titlul original (in engleza), apoi cu titlul din EPG in
#    limbile probabile ale ghidului; wbgetentities pe rezultate: ID-ul IMDb (P345), ID-ul TMDb (P4947), anul (P577),
#    titlul original (P1476), regizorul (P57), durata (P2047), felul (P31). Raman filmele cu ID IMDb si, daca EIT-ul
#    are anul, cu anul la +/- 1. Mai multi: regizorul (eticheta lui), apoi durata (filmul nu e mai lung decat emisiunea,
#    care are si reclamele). Datele Wikidata sunt CC0.
#    Rezultatul: {"stare": "sigur" | "mai_multe" | "niciunul" | "eroare", "candidati": [...], "mesaj"}; "sigur" numai cu
#    un singur film ramas si cu anul din EIT; fara an (titlurile romanesti) omul confirma.
# Reguli Wikidata: User-Agent descriptiv cu adresa sitului, pauza intre cereri, la 429 se asteapta cat cere Retry-After
# (cel mult MAX_ASTEPTARE_S), o singura data; cel mult MAX_CERERI cereri pe o identificare.

import re
import time
import unicodedata

WIKIDATA = "https://www.wikidata.org/w/api.php"
MAX_CERERI = 8
PAUZA_S = 1.0
MAX_ASTEPTARE_S = 10
MAX_CANDIDATI = 8
# felurile de film (P31): film, film de lung metraj, film TV, film de animatie, film documentar, film mut, film 3D
FELURI_FILM = frozenset(("Q11424", "Q24869", "Q506240", "Q202866", "Q93204", "Q226730", "Q229390", "Q24862",
	"Q17123180", "Q20650540"))

_AN = r"(?:19[2-9]\d|20[0-4]\d)"
# un an care nu e intr-o data (zi.luna.an, an-luna-zi) si nu e o ora
_AN_LIBER = re.compile(r"(?<![\d.:/-])(" + _AN + r")(?![\d:.]\d|-\d)")
_DATA = re.compile(r"\b\d{1,2}\.\d{1,2}\.\s?" + _AN + r"\b")
# "Spielfilm USA 2006", "Action, USA/GB 2017", "Drama, Frankreich 2019", "SUA, 2019", "Romania 2021" (literele cu sedila
# din EIT-urile vechi, scrise ca \u015e \u0162 \u015f \u0163)
_TARA_AN = re.compile(r"(?:^|[,(]\s*|\b(?:Spielfilm|Fernsehfilm|Film|Kinofilm|Komödie|Drama|Thriller)\s+)"
	r"([A-ZÄÖÜÂÎȘȚ\u015e\u0162][\w./ ÄÖÜäöüâîășț\u015f\u0163-]{1,40}?)[ ,]+(" + _AN + r")\b")
_AN_PARANTEZA = re.compile(r"\((" + _AN + r")\)")
_ORIGINAL_ETICHETA = re.compile(r"(?i)\b(?:originaltitel|original\s*title|titlu\s*original|titre\s*original|"
	r"titolo\s*originale|título\s*original|eredeti\s*cím)\s*[:=]\s*([^\n;|]{2,100})")
_REGIZOR = re.compile(r"(?i)\b(?:regie|regia|regizor|regizat\s+de|directed\s+by|director|réalisation|rendező|"
	r"režie|reżyseria)\s*[:=]?\s+([^\n;|,(]{3,60})")
_PARANTEZA = re.compile(r"\(([^()]{2,100})\)")
_PREFIXE_TITLU = re.compile(r"(?i)^(?:film|spielfilm|kinofilm|cinema|premier[aă]|premiere|filmul serii|"
	r"filmul s[aă]pt[aă]m[aâ]nii)\s*[:\-]\s*")


def _text(x):
	if x is None:
		return u""
	if isinstance(x, bytes):
		return x.decode("utf-8", "replace")
	return u"%s" % x


def normalizeaza(text):
	"""Pentru comparatii: fara diacritice, litere mici, numai litere si cifre."""
	t = unicodedata.normalize("NFKD", _text(text))
	t = u"".join(c for c in t if not unicodedata.combining(c))
	return u"".join(c for c in t.lower() if c.isalnum())


def _an(text):
	"""Primul an din text care nu e intr-o data de difuzare."""
	t = _DATA.sub(u" ", text or u"")
	m = _TARA_AN.search(t)
	if m:
		return m.group(2)
	m = _AN_PARANTEZA.search(t)
	if m:
		return m.group(1)
	m = _AN_LIBER.search(t)
	return m.group(1) if m else u""


def _pareOriginal(text, titlu):
	"""Un text din paranteza care poate fi titlul original (nu un an, nu o tara cu an, nu "OV", nu "HD")."""
	t = text.strip()
	if not t or re.match(r"^\W*" + _AN + r"\W*$", t) or len(t) < 2:
		return False
	if re.search(r"\b" + _AN + r"\b", t) and len(t) < 30:
		return False
	if t.upper() in ("OV", "OMU", "HD", "UHD", "4K", "16:9", "DOLBY", "VO", "VOST", "R", "AD", "UT", "SUB"):
		return False
	if normalizeaza(t) == normalizeaza(titlu):
		return False
	return bool(re.search(r"[A-Za-zÀ-ž]{2}", t))


def dinEveniment(titlu, scurt=u"", extins=u"", inceput=0, durata=0):
	"""Ce se poate citi din EIT. -> {"titlu", "an", "original", "regizor", "durata_min", "inceput", "durata"}."""
	titlu = _text(titlu).strip()
	scurt = _text(scurt).strip()
	extins = _text(extins).strip()
	original = u""
	# titlul original in titlu: "Vânătorul (Play Dirty)"
	m = _PARANTEZA.search(titlu)
	if m and _pareOriginal(m.group(1), titlu[:m.start()]):
		original = m.group(1).strip()
		titlu = (titlu[:m.start()] + titlu[m.end():]).strip(u" -:")
	# anul din titlu ("Titlu (2019)") se scoate din titlu
	m = _AN_PARANTEZA.search(titlu)
	an_titlu = u""
	if m:
		an_titlu = m.group(1)
		titlu = (titlu[:m.start()] + titlu[m.end():]).strip(u" -:")
	titlu = _PREFIXE_TITLU.sub(u"", titlu).strip()
	an = an_titlu or _an(scurt) or _an(extins)
	if not original:
		m = _ORIGINAL_ETICHETA.search(scurt + u"\n" + extins)
		if m:
			original = m.group(1).strip(u" .")
	if not original:
		# "Spielfilm USA 2006 (The Departed)": paranteza din textul scurt
		for m in _PARANTEZA.finditer(scurt):
			if _pareOriginal(m.group(1), titlu):
				original = m.group(1).strip()
				break
	regizor = u""
	m = _REGIZOR.search(scurt + u"\n" + extins)
	if m:
		regizor = re.split(r"\s+(?:und|and|si|și|et|e|y)\s+", m.group(1).strip(u" ."))[0].strip()
	try:
		durata = int(durata or 0)
	except (TypeError, ValueError):
		durata = 0
	try:
		inceput = int(inceput or 0)
	except (TypeError, ValueError):
		inceput = 0
	return {"titlu": titlu[:120], "an": an, "original": original[:120], "regizor": regizor[:60],
		"durata": durata, "durata_min": durata // 60 if durata else 0, "inceput": inceput}


# ------------------------------------------------------------------ Wikidata

class EroareIdentificare(Exception):
	"""Textul pentru om."""


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


class Wikidata(object):
	"""Cererile catre Wikidata ale unei identificari (cel mult MAX_CERERI), cu pauza intre ele. `cerere` si `dormi` se
	pot da din probe."""

	def __init__(self, cerere=None, json_din=None, agent=None, dormi=time.sleep, pauza=PAUZA_S):
		if cerere is None or json_din is None:
			from . import retea
			cerere = cerere or retea.cerere
			json_din = json_din or retea.json_din
			agent = agent or (retea.agent() + " (https://hdsatelit.com)")
		self.cerere = cerere
		self.json_din = json_din
		self.agent = agent or "HDSatelit (https://hdsatelit.com)"
		self.dormi = dormi
		self.pauza = pauza
		self.cereri = 0
		self._ultima = 0.0

	def _get(self, parametri):
		if self.cereri >= MAX_CERERI:
			raise EroareIdentificare(_t("Prea multe cereri pentru un singur film."))
		for incercare in range(2):
			asteapta = self._ultima + self.pauza - time.time()
			if asteapta > 0 and self.cereri:
				self.dormi(asteapta)
			self.cereri += 1
			self._ultima = time.time()
			p = dict(parametri)
			p["format"] = "json"
			cod, antete, corp = self.cerere("GET", WIKIDATA, {"User-Agent": self.agent, "Accept": "application/json"}, p)
			if cod == 429 and incercare == 0:
				try:
					secunde = int((antete or {}).get("retry-after") or 5)
				except ValueError:
					secunde = 5
				self.dormi(min(MAX_ASTEPTARE_S, max(1, secunde)))
				continue
			if cod != 200:
				raise EroareIdentificare(_t("Wikidata nu răspunde cum trebuie (cod %d).") % cod)
			return self.json_din(corp) or {}
		raise EroareIdentificare(_t("Wikidata cere o pauză. Încearcă peste un minut."))

	def cauta(self, text, limba):
		d = self._get({"action": "wbsearchentities", "search": text[:100], "language": limba, "uselang": limba,
			"type": "item", "limit": 10})
		return [x.get("id") for x in d.get("search") or [] if x.get("id")]

	def entitati(self, ids, limbi):
		if not ids:
			return {}
		d = self._get({"action": "wbgetentities", "ids": "|".join(ids[:50]), "props": "claims|labels",
			"languages": "|".join(limbi)})
		return d.get("entities") or {}


def _valori(claims, prop):
	rez = []
	for c in claims.get(prop) or []:
		v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
		if v is not None:
			rez.append(v)
	return rez


def candidat(qid, entitate, limbi):
	"""O entitate Wikidata -> candidatul (sau None daca nu are ID IMDb de film)."""
	cl = entitate.get("claims") or {}
	imdb = [v for v in _valori(cl, "P345") if isinstance(v, str) and re.match(r"^tt\d{5,10}$", v)]
	if not imdb:
		return None
	ani = []
	for v in _valori(cl, "P577"):
		t = (v or {}).get("time", "") if isinstance(v, dict) else ""
		m = re.match(r"^[+-](\d{4})", t)
		if m:
			ani.append(int(m.group(1)))
	feluri = [(v or {}).get("id") for v in _valori(cl, "P31") if isinstance(v, dict)]
	original = u""
	for v in _valori(cl, "P1476"):
		if isinstance(v, dict) and v.get("text"):
			original = v["text"]
			break
	durata = 0
	for v in _valori(cl, "P2047"):
		try:
			if isinstance(v, dict) and (v.get("unit") or "").endswith("Q7727"):
				durata = int(float(v.get("amount")))
				break
		except (TypeError, ValueError):
			pass
	etichete = entitate.get("labels") or {}
	titlu = u""
	for l in limbi:
		if (etichete.get(l) or {}).get("value"):
			titlu = etichete[l]["value"]
			break
	tmdb = [v for v in _valori(cl, "P4947") if isinstance(v, str) and v.isdigit()]
	return {"qid": qid, "imdb": imdb[0], "tmdb": tmdb[0] if tmdb else u"", "titlu": titlu or original,
		"original": original, "an": min(ani) if ani else None, "ani": sorted(set(ani)), "film": bool(set(feluri) & FELURI_FILM),
		"feluri": feluri, "regizori": [(v or {}).get("id") for v in _valori(cl, "P57") if isinstance(v, dict)],
		"regizor": u"", "durata_min": durata}


def _anPotrivit(c, an):
	if not an:
		return True
	try:
		an = int(an)
	except (TypeError, ValueError):
		return True
	return any(abs(a - an) <= 1 for a in c["ani"])


def limbiProbabile(limbaReceptor=u"ro"):
	"""Limbile in care se cauta titlul din EPG: a receptorului, engleza, germana (Astra), apoi romana."""
	rez = []
	for l in (limbaReceptor, "en", "de", "ro"):
		l = (l or "").split("_")[0].lower()
		if l and l not in rez:
			rez.append(l)
	return rez[:3]


def identifica(info, limbi=None, wd=None):
	"""Pe fir. info = dinEveniment(...). -> {"stare", "candidati", "mesaj"} (vezi capul fisierului)."""
	wd = wd or Wikidata()
	limbi = limbi or limbiProbabile()
	etichete = list(dict.fromkeys(list(limbi) + ["en"]))
	cautari = []
	if info.get("original"):
		cautari.append((info["original"], "en"))
	for l in limbi:
		if info.get("titlu"):
			cautari.append((info["titlu"], l))
	vazute = set()
	gasiti = []
	try:
		for text, limba in cautari:
			if (normalizeaza(text), limba) in vazute:
				continue
			vazute.add((normalizeaza(text), limba))
			ids = wd.cauta(text, limba)
			ids = [i for i in ids if i not in [g["qid"] for g in gasiti]]
			if not ids:
				continue
			ent = wd.entitati(ids, etichete)
			noi = []
			for i in ids:
				c = candidat(i, ent.get(i) or {}, etichete)
				if c is None or not _anPotrivit(c, info.get("an")):
					continue
				if not c["film"] and not info.get("an"):
					continue
				noi.append(c)
			gasiti.extend(noi)
			# cu anul cunoscut, un film gasit dupa titlul original (sau primul titlu) ajunge
			if gasiti and info.get("an"):
				break
			# fara an: filmele cu exact titlul original din EIT ajung (titlul tradus ar aduce alte filme, "Vânătorul" ->
			# Blade Runner)
			if info.get("original") and any(normalizeaza(c["original"] or c["titlu"]) == normalizeaza(info["original"])
					for c in gasiti):
				gasiti = [c for c in gasiti if normalizeaza(c["original"] or c["titlu"]) == normalizeaza(info["original"])]
				break
	except EroareIdentificare as e:
		if not gasiti:
			return {"stare": "eroare", "candidati": [], "mesaj": u"%s" % e}
	except Exception as e:
		if not gasiti:
			return {"stare": "eroare", "candidati": [], "mesaj": _t("Identificarea nu a mers: %s") % e.__class__.__name__}
	# filmele inaintea altor feluri (seriale, episoade)
	filme = [c for c in gasiti if c["film"]]
	if filme:
		gasiti = filme
	gasiti = gasiti[:MAX_CANDIDATI]
	if len(gasiti) > 1 and info.get("regizor"):
		_regizori(wd, gasiti, etichete)
		nume = normalizeaza(info["regizor"].split()[-1]) if info["regizor"].split() else u""
		potriviti = [c for c in gasiti if nume and nume in normalizeaza(c.get("regizor"))]
		if potriviti:
			gasiti = potriviti
	if len(gasiti) > 1 and info.get("durata_min"):
		d = info["durata_min"]
		potriviti = [c for c in gasiti if c["durata_min"] and d * 0.5 <= c["durata_min"] <= d * 1.05]
		if potriviti:
			gasiti = potriviti
	if not gasiti:
		return {"stare": "niciunul", "candidati": [],
			"mesaj": _t("Filmul nu s-a găsit în Wikidata. Scrie titlul original sau caută după titlu.")}
	if len(gasiti) == 1 and info.get("an"):
		return {"stare": "sigur", "candidati": gasiti, "mesaj": u""}
	return {"stare": "mai_multe", "candidati": gasiti,
		"mesaj": _t("Alege filmul din listă (nu e sigur care este).")}


def _regizori(wd, candidati, limbi):
	ids = []
	for c in candidati:
		ids.extend(c["regizori"][:3])
	ids = list(dict.fromkeys(i for i in ids if i))[:40]
	if not ids:
		return
	try:
		ent = wd.entitati(ids, limbi)
	except Exception:
		return
	for c in candidati:
		nume = []
		for i in c["regizori"][:3]:
			et = (ent.get(i) or {}).get("labels") or {}
			for l in limbi:
				if (et.get(l) or {}).get("value"):
					nume.append(et[l]["value"])
					break
		c["regizor"] = u", ".join(nume)
