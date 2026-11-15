# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Despre film: afisul, descrierea, anul, genul, regia, actorii si notele unui film din ghid sau dintr-o inregistrare.

Fara nicio cheie si fara cont: datele vin din Wikidata (CC0) si din rezumatul Wikipediei (CC BY-SA, sursa scrisa pe ecran).
1. Filmul: identificarea facuta deja pentru subtitrari (HdsSubtitrariInternet/identificare.py): titlul, anul, titlul original,
   regizorul si durata din ghid (fara retea), apoi Wikidata. Cand nu e sigur care film e, ecranul arata lista (anul, titlul).
2. Fisa: o cerere wbgetentities pe film (genul P136, actorii P161, regia P57, notele P444 cu cine le da P447, legaturile
   spre Wikipedia), una pentru numele genurilor si ale oamenilor, apoi rezumatul Wikipediei in limba meniului (daca pagina
   exista; altfel engleza): descrierea scurta, primele fraze si afisul.
3. Afisul: descarcat o data, micsorat la marimea din ecran (HdsVodPoze.micsoreaza), tinut in /tmp/hds-despre-film cu plafon.
Totul pe un fir; ecranul primeste rezultatul prin `gata(fisa)` pe firul principal (cine apeleaza se ocupa de asta).
Fisele gasite se tin minte pana la repornirea interfetei (cel mult MAX_FISE), ca a doua deschidere sa nu mai ceara nimic.
4. TMDB (INB, 15.11.2026; TODO 14.11 22:14), a doua sursa, NUMAI cu cheia omului (pusa de el in ecran, Galben, sau in
   pagina web /despre-film; niciodata o cheie a noastra). Fara cheie nu pleaca nicio cerere spre TMDB si totul ramane ca
   inainte. Cu cheie: cand fisa din Wikidata nu are afisul, descrierea sau notele, ele (si genurile, durata, regia, actorii
   lipsa) vin din TMDB, prin ID-ul TMDB din Wikidata (P4947) sau prin cautarea titlului cu anul; cand Wikidata nu gaseste
   deloc filmul, fisa vine intreaga din TMDB. Cheia sta in CALE_CHEIE_TMDB (0600), nu in /etc/enigma2/settings; ecranul si
   pagina o pot numai scrie si sterge, iar starea spune doar daca e pusa si ultimele 4 semne. Mesajele si jurnalul nu
   scriu niciodata adresa cererii (are cheia in ea).
"""
import hashlib
import os
import re
import threading
from collections import OrderedDict

from Components.HdsSubtitrariInternet import identificare as I

DOSAR = "/tmp/hds-despre-film"
AFIS_LATIME = 300
AFIS_INALTIME = 450
MAX_AFIS_OCTETI = 3 * 1024 * 1024
MAX_DOSAR = 8 * 1024 * 1024
MAX_FISE = 60
MAX_ACTORI = 6
MAX_GENURI = 3
WIKI_REZUMAT = "https://%s.wikipedia.org/api/rest_v1/page/summary/%s"
WIKIDATA_PAGINA = "https://www.wikidata.org/wiki/%s"

# notele (P444) dupa cine le da (P447) si felul notei (P459); la Rotten Tomatoes numai nota criticilor
NOTE = (
	("IMDb", "Q37312", ("Q107218751",)),
	("Rotten Tomatoes", "Q105584", ("Q108403393",)),
	("Metacritic", "Q150248", ("Q106515043",)),
)

TMDB_API = "https://api.themoviedb.org/3"
TMDB_AFIS = "https://image.tmdb.org/t/p/w342"
TMDB_PAGINA = "https://www.themoviedb.org/movie/%d"
CALE_CHEIE_TMDB = "/etc/enigma2/hdsatelit/tmdb-cheie"
MAX_CANDIDATI_TMDB = 8
# cheia API (v3, 32 de semne hexazecimale) sau tokenul de citire (v4, JWT); amandoua se iau din contul omului
_CHEIE_V3 = re.compile(r"^[0-9a-fA-F]{32}$")
_CHEIE_V4 = re.compile(r"^eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")

_lacat = threading.Lock()
_fise = OrderedDict()


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def limbaMeniului():
	try:
		from Components.Language import language
		return (language.getLanguage() or "ro_RO").split("_")[0].lower() or "ro"
	except Exception:
		return "ro"


def _cheie(info):
	return "%s|%s|%s" % (I.normalizeaza(info.get("titlu") or u""), I.normalizeaza(info.get("original") or u""), info.get("an") or "")


def _data(v):
	t = (v or {}).get("time", "") if isinstance(v, dict) else ""
	return t[1:11] if len(t) >= 11 else ""


def note(claims):
	"""P444 -> [(sursa, nota)] in ordinea din NOTE; la fiecare sursa nota cea mai noua (P585), fara cele invechite."""
	rez = []
	for nume, qid, feluri in NOTE:
		alese = []
		for c in claims.get("P444") or []:
			if c.get("rank") == "deprecated":
				continue
			v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
			if not isinstance(v, str) or not v.strip():
				continue
			cal = c.get("qualifiers") or {}
			de = [((q.get("datavalue") or {}).get("value") or {}).get("id") for q in cal.get("P447") or []]
			if qid not in de:
				continue
			fel = [((q.get("datavalue") or {}).get("value") or {}).get("id") for q in cal.get("P459") or []]
			if fel and not set(fel) & set(feluri):
				continue
			cand = max([_data((q.get("datavalue") or {}).get("value")) for q in cal.get("P585") or []] or [""])
			alese.append((c.get("rank") == "preferred", cand, v.strip()))
		if alese:
			alese.sort()
			rez.append((nume, alese[-1][2]))
	return rez


def _iduri(claims, prop, maxim):
	rez = []
	for c in claims.get(prop) or []:
		if c.get("rank") == "deprecated":
			continue
		v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
		if isinstance(v, dict) and v.get("id") and v["id"] not in rez:
			rez.append(v["id"])
		if len(rez) >= maxim:
			break
	return rez


def _eticheta(entitate, limbi):
	et = (entitate or {}).get("labels") or {}
	for l in list(limbi) + ["mul"]:
		if (et.get(l) or {}).get("value"):
			return et[l]["value"]
	for v in et.values():
		if (v or {}).get("value"):
			return v["value"]
	return u""


def _titluWiki(sitelinks, limba):
	for l in (limba, "en"):
		s = (sitelinks or {}).get("%swiki" % l) or {}
		if s.get("title"):
			return l, s["title"]
	return "", ""


def fisa(candidat, limba=None, wd=None, cerere=None, json_din=None):
	"""Pe fir. Candidatul din identificare -> fisa filmului (dict). Ce nu vine (Wikipedia picata) ramane gol."""
	limba = limba or limbaMeniului()
	limbi = list(dict.fromkeys([limba, "en"]))
	if wd is None:
		wd = I.Wikidata(cerere=cerere, json_din=json_din) if (cerere and json_din) else I.Wikidata()
	qid = candidat["qid"]
	d = wd._get({"action": "wbgetentities", "ids": qid, "props": "claims|labels|descriptions|sitelinks",
		"languages": "|".join(limbi)})
	ent = (d.get("entities") or {}).get(qid) or {}
	cl = ent.get("claims") or {}
	genuri = _iduri(cl, "P136", MAX_GENURI)
	actori = _iduri(cl, "P161", MAX_ACTORI)
	regizori = _iduri(cl, "P57", 3)
	nume = {}
	ids = list(dict.fromkeys(genuri + regizori + actori))
	if ids:
		# numai etichetele (fara claims: fisele actorilor sunt mari); "mul" = eticheta comuna tuturor limbilor, pe care o au
		# acum multi oameni in locul celei in engleza sau romana
		try:
			nume = wd._get({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels",
				"languages": "|".join(limbi + ["mul"])}).get("entities") or {}
		except I.EroareIdentificare:
			nume = {}
	desc = ent.get("descriptions") or {}
	f = {
		"qid": qid,
		"titlu": _eticheta(ent, limbi) or candidat.get("titlu") or u"",
		"original": candidat.get("original") or u"",
		"an": candidat.get("an"),
		"durata_min": candidat.get("durata_min") or 0,
		"genuri": [n for n in (_eticheta(nume.get(i), limbi) for i in genuri) if n],
		"regie": [n for n in (_eticheta(nume.get(i), limbi) for i in regizori) if n],
		"actori": [n for n in (_eticheta(nume.get(i), limbi) for i in actori) if n],
		"note": note(cl),
		"descriere_scurta": next(((desc.get(l) or {}).get("value") for l in limbi if (desc.get(l) or {}).get("value")), u""),
		"rezumat": u"",
		"limba_rezumat": "",
		"afis_adresa": "",
		"afis": "",
		"surse": ["Wikidata"],
		"pagina": WIKIDATA_PAGINA % qid,
		"tmdb": _idTmdb(cl),
	}
	l, titlu = _titluWiki(ent.get("sitelinks"), limba)
	if titlu:
		try:
			j = _rezumat(l, titlu, wd.agent, cerere, json_din)
			if j is not None:
				f["rezumat"] = (j.get("extract") or u"").strip()
				f["limba_rezumat"] = l
				if j.get("description") and (l == limba or not f["descriere_scurta"]):
					f["descriere_scurta"] = j["description"]
				afis = ((j.get("thumbnail") or {}).get("source") or u"")
				if afis.startswith("https://upload.wikimedia.org/"):
					f["afis_adresa"] = afis
				f["surse"].append("Wikipedia")
				pagina = ((j.get("content_urls") or {}).get("desktop") or {}).get("page")
				if pagina:
					f["pagina"] = pagina
		except Exception:
			pass
	# Wikipedia in alta limba decat engleza are rar afisul (drepturile de autor): afisul din pagina engleza, numai el
	en = ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title")
	if not f["afis_adresa"] and en and l != "en":
		try:
			j = _rezumat("en", en, wd.agent, cerere, json_din) or {}
			afis = ((j.get("thumbnail") or {}).get("source") or u"")
			if afis.startswith("https://upload.wikimedia.org/"):
				f["afis_adresa"] = afis
		except Exception:
			pass
	return f


def _rezumat(limba, titlu, agent, cerere=None, json_din=None):
	"""Rezumatul unei pagini Wikipedia (dict) sau None."""
	from urllib.parse import quote
	cer = cerere or _cerereRetea()
	cod, antete, corp = cer("GET", WIKI_REZUMAT % (limba, quote(titlu.replace(" ", "_"), safe="")),
		{"User-Agent": agent, "Accept": "application/json"}, None)
	j = (json_din or _jsonRetea())(corp) if cod == 200 else None
	if isinstance(j, dict) and j.get("type") in ("standard", None):
		return j
	return None


def _cerereRetea():
	from Components.HdsSubtitrariInternet import retea
	return lambda metoda, adresa, antete, parametri: retea.cerere(metoda, adresa, antete, parametri)


def _jsonRetea():
	from Components.HdsSubtitrariInternet import retea
	return retea.json_din


def caleAfis(adresa):
	if not adresa:
		return ""
	return os.path.join(DOSAR, hashlib.sha1(adresa.encode("utf-8", "replace")).hexdigest()[:24] + ".jpg")


def aduAfis(adresa, cerere=None):
	"""Pe fir. Afisul micsorat la AFIS_LATIME x AFIS_INALTIME, ca fisier JPEG; "" daca nu se poate."""
	tinta = caleAfis(adresa)
	if not tinta:
		return ""
	if os.path.isfile(tinta):
		return tinta
	try:
		from Components.HdsSubtitrariInternet import retea
		cer = cerere or (lambda a: retea.cerere("GET", a, None, None, maxim=MAX_AFIS_OCTETI))
		cod, antete, date = cer(adresa)
		if cod != 200 or not date:
			return ""
		from Components.HdsVodPoze import micsoreaza
		jpeg = micsoreaza(date, AFIS_LATIME, AFIS_INALTIME, "poster")
		if not jpeg:
			return ""
		os.makedirs(DOSAR, exist_ok=True)
		_curata()
		tmp = tinta + ".tmp"
		with open(tmp, "wb") as fd:
			fd.write(jpeg)
		os.rename(tmp, tinta)
		return tinta
	except Exception:
		return ""


def _curata():
	try:
		fisiere = [os.path.join(DOSAR, n) for n in os.listdir(DOSAR)]
		fisiere = sorted((os.path.getmtime(p), os.path.getsize(p), p) for p in fisiere if os.path.isfile(p))
		total = sum(s for m, s, p in fisiere)
		for m, s, p in fisiere:
			if total <= MAX_DOSAR:
				break
			os.remove(p)
			total -= s
	except OSError:
		pass


def dinEveniment(event):
	"""Un eServiceEvent (ghid sau inregistrare) -> info pentru identificare (fara retea), sau None fara titlu."""
	if event is None:
		return None
	try:
		titlu = event.getEventName() or u""
		scurt = event.getShortDescription() or u""
		lung = event.getExtendedDescription() or u""
		inceput = event.getBeginTime() or 0
		durata = event.getDuration() or 0
	except Exception:
		return None
	return dinText(titlu, scurt, lung, inceput, durata)


_FILM = re.compile(r"(?i)\b(spielfilm|fernsehfilm|kinofilm|film|movie|filme|filmul|pel[ií]cula|tv-film)\b")


def pareFilm(titlu, scurt=u"", lung=u""):
	"""Fara retea: emisiunea pare film (anul productiei sau cuvantul film in textul scurt)? Numai pentru randul cu TEXT."""
	if not (titlu or u"").strip():
		return False
	if _FILM.search(scurt or u""):
		return True
	try:
		return bool(I.dinEveniment(titlu, scurt or u"", lung or u"", 0, 0).get("an"))
	except Exception:
		return False


def dinText(titlu, scurt=u"", lung=u"", inceput=0, durata=0):
	titlu = (titlu or u"").strip()
	if not titlu:
		return None
	return I.dinEveniment(titlu, scurt or u"", lung or u"", inceput or 0, durata or 0)


def cauta(info, limba=None, wd=None, cerere=None, json_din=None, cheie=None):
	"""Pe fir. -> {"stare": "gata" | "alege" | "niciunul" | "eroare", "fisa", "candidati", "mesaj"}.
	`cheie` = cheia TMDB a omului; None = cea pusa pe receptor (cheieTmdb()), "" = fara TMDB."""
	if not info:
		return {"stare": "niciunul", "fisa": None, "candidati": [], "mesaj": _t("Emisiunea nu are titlu în ghid.")}
	limba = limba or limbaMeniului()
	if cheie is None:
		cheie = cheieTmdb()
	# fisa facuta cu TMDB nu e aceeasi cu cea fara: cheia pusa sau scoasa nu da fisa veche din memorie
	k = _cheie(info) + ("|tmdb" if cheie else "")
	with _lacat:
		if k in _fise:
			_fise.move_to_end(k)
			return _fise[k]
	if cerere and json_din:
		wdId = I.Wikidata(cerere=cerere, json_din=json_din, dormi=lambda s: None, pauza=0)
	else:
		wdId = wd or I.Wikidata()
	r = I.identifica(info, I.limbiProbabile(limba), wdId)
	if r["stare"] in ("niciunul", "eroare"):
		rez = _numaiTmdb(info, cheie, limba, cerere, json_din) if cheie else None
		if rez is None:
			return {"stare": r["stare"], "fisa": None, "candidati": [], "mesaj": r.get("mesaj") or u""}
	elif r["stare"] == "mai_multe" and len(r["candidati"]) > 1:
		return {"stare": "alege", "fisa": None, "candidati": r["candidati"], "mesaj": r.get("mesaj") or u""}
	else:
		rez = deschide(r["candidati"][0], limba, cerere=cerere, json_din=json_din, wd=wd, cheie=cheie)
	if rez["stare"] == "gata":
		with _lacat:
			_fise[k] = rez
			while len(_fise) > MAX_FISE:
				_fise.popitem(last=False)
	return rez


def deschide(candidat, limba=None, cerere=None, json_din=None, wd=None, cheie=None):
	"""Pe fir. Fisa unui candidat ales (din lista) -> acelasi rezultat ca `cauta`. Un candidat numai din TMDB (cheia
	"tmdb", fara "qid") se deschide din TMDB."""
	limba = limba or limbaMeniului()
	if cheie is None:
		cheie = cheieTmdb()
	if candidat.get("tmdb") and not candidat.get("qid"):
		if not cheie:
			return {"stare": "eroare", "fisa": None, "candidati": [], "mesaj": _t("Cheia TMDB nu mai e pusă.")}
		try:
			m = _filmTmdb(candidat["tmdb"], cheie, limba, cerere, json_din)
		except EroareTmdb as e:
			return {"stare": "eroare", "fisa": None, "candidati": [], "mesaj": e.mesaj()}
		if not m:
			return {"stare": "niciunul", "fisa": None, "candidati": [], "mesaj": _t("Filmul nu s-a găsit.")}
		return {"stare": "gata", "fisa": fisaDinTmdb(m, limba), "candidati": [candidat], "mesaj": u""}
	try:
		if cerere and json_din:
			wdF = I.Wikidata(cerere=cerere, json_din=json_din, dormi=lambda s: None, pauza=0)
		else:
			wdF = wd or I.Wikidata()
		f = fisa(candidat, limba, wd=wdF, cerere=cerere, json_din=json_din)
	except I.EroareIdentificare as e:
		return {"stare": "eroare", "fisa": None, "candidati": [], "mesaj": u"%s" % e}
	except Exception as e:
		return {"stare": "eroare", "fisa": None, "candidati": [],
			"mesaj": _t("Fișa filmului nu s-a putut aduce: %s") % e.__class__.__name__}
	if cheie:
		f = completeazaTmdb(f, cheie, limba, cerere, json_din)
	return {"stare": "gata", "fisa": f, "candidati": [candidat], "mesaj": u""}


# ------------------------------------------------------------------ TMDB, numai cu cheia omului

class EroareTmdb(Exception):
	"""O cerere TMDB cazuta. Textul e numai felul erorii (niciodata adresa: are cheia in ea)."""

	def __init__(self, fel, cod=0):
		Exception.__init__(self, fel)
		self.fel = fel
		self.cod = cod

	def mesaj(self):
		if self.cod in (401, 403):
			return _t("TMDB nu primește cheia: verific-o pe themoviedb.org.")
		return _t("TMDB nu răspunde acum.")


def curataCheieTmdb(valoare):
	return u"".join((valoare or u"").split())


def felCheieTmdb(valoare):
	""""v3" (cheia API), "v4" (tokenul de citire) sau "" (nu e o cheie TMDB)."""
	v = curataCheieTmdb(valoare)
	if _CHEIE_V3.match(v):
		return "v3"
	if 100 <= len(v) <= 1000 and _CHEIE_V4.match(v):
		return "v4"
	return ""


def cheieTmdb(cale=None):
	"""Cheia pusa de om, sau "" (fara fisier sau fisier stricat)."""
	try:
		with open(cale or CALE_CHEIE_TMDB, encoding="utf-8") as fd:
			v = curataCheieTmdb(fd.read(2048))
	except (OSError, ValueError):
		return ""
	return v if felCheieTmdb(v) else ""


def _golesteFise():
	with _lacat:
		_fise.clear()


def puneCheieTmdb(valoare, cale=None):
	"""Scrie cheia omului (sau o sterge, cu valoare goala) -> (ok, mesaj). Fisier 0600, scris prin redenumire."""
	cale = cale or CALE_CHEIE_TMDB
	v = curataCheieTmdb(valoare)
	if not v:
		try:
			os.remove(cale)
		except FileNotFoundError:
			pass
		except OSError:
			return False, _t("Cheia TMDB nu s-a putut șterge.")
		_golesteFise()
		return True, _t("Cheia TMDB a fost ștearsă. Datele vin numai din Wikidata și Wikipedia.")
	fel = felCheieTmdb(v)
	if not fel:
		return False, _t("Nu pare o cheie TMDB: pune cheia API (32 de semne) sau tokenul de citire din contul tău de pe themoviedb.org.")
	if fel == "v3":
		v = v.lower()
	try:
		os.makedirs(os.path.dirname(cale), exist_ok=True)
		tmp = cale + ".tmp"
		fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		with os.fdopen(fd, "w", encoding="utf-8") as f:
			f.write(v + "\n")
		os.chmod(tmp, 0o600)
		os.replace(tmp, cale)
	except OSError:
		return False, _t("Cheia TMDB nu s-a putut scrie pe receptor.")
	_golesteFise()
	return True, _t("Cheia TMDB e pusă.")


def stareCheieTmdb(cale=None):
	"""Pentru ecran si pagina: daca e pusa si ultimele 4 semne, niciodata cheia."""
	v = cheieTmdb(cale)
	if v:
		return {"pusa": True, "capat": v[-4:], "text": _t("Cheia ta TMDB e pusă (se termină în %s): ce lipsește din Wikidata (afișul, descrierea, notele) vine din TMDB.") % v[-4:]}
	return {"pusa": False, "capat": "", "text": _t("Fără cheie TMDB: datele vin numai din Wikidata și Wikipedia. Cheia ta gratuită de pe themoviedb.org adaugă afișul și notele care lipsesc.")}


def _agent():
	try:
		from Components.HdsSubtitrariInternet import retea
		return retea.agent()
	except Exception:
		return "HDSatelit"


def _tmdb(cale, parametri, cheie, cerere=None, json_din=None):
	"""O cerere GET spre TMDB -> (cod, json sau None). Cheia v3 ca parametru, tokenul v4 in antet."""
	p = dict(parametri or {})
	antete = {"Accept": "application/json", "User-Agent": _agent()}
	if felCheieTmdb(cheie) == "v4":
		antete["Authorization"] = "Bearer " + cheie
	else:
		p["api_key"] = cheie
	cer = cerere or _cerereRetea()
	try:
		cod, ant, corp = cer("GET", TMDB_API + cale, antete, p)
	except Exception as e:
		raise EroareTmdb(e.__class__.__name__)
	if cod in (401, 403):
		raise EroareTmdb("cheia", cod)
	j = (json_din or _jsonRetea())(corp) if cod == 200 else None
	return cod, j


def verificaCheieTmdb(cheie, cerere=None, json_din=None):
	"""Pe fir. -> (True | False | None, mesaj): False = TMDB refuza cheia; None = nu s-a putut verifica acum."""
	try:
		cod, j = _tmdb("/configuration", {}, curataCheieTmdb(cheie), cerere, json_din)
	except EroareTmdb as e:
		return (False if e.cod in (401, 403) else None), e.mesaj()
	if cod == 200:
		return True, _t("TMDB primește cheia.")
	return None, _t("TMDB nu răspunde acum.")


def pastreazaCheieTmdb(valoare, cale=None, cerere=None, json_din=None):
	"""Pe fir. Ce face Salveaza din ecran si din pagina: o cheie refuzata de TMDB nu se scrie; una care nu se poate
	verifica acum (fara internet) se scrie, cu mesajul. Valoarea goala sterge cheia. -> (ok, mesaj)."""
	v = curataCheieTmdb(valoare)
	if v and not felCheieTmdb(v):
		return puneCheieTmdb(v, cale)
	if v:
		merge, mesaj = verificaCheieTmdb(v, cerere, json_din)
		if merge is False:
			return False, mesaj
		ok, scris = puneCheieTmdb(v, cale)
		if ok and merge is None:
			return True, u"%s %s" % (scris, _t("TMDB nu răspunde acum; o încerc la următorul film."))
		return ok, scris
	return puneCheieTmdb(u"", cale)


def _idTmdb(claims):
	"""ID-ul filmului in TMDB din Wikidata (P4947), ca numar, sau None."""
	for c in claims.get("P4947") or []:
		if c.get("rank") == "deprecated":
			continue
		v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
		if isinstance(v, str) and v.strip().isdigit():
			return int(v.strip())
	return None


def _anTmdb(m):
	d = (m.get("release_date") or "")[:4]
	return int(d) if d.isdigit() else None


def _cautaTmdb(titluri, an, cheie, limba, cerere=None, json_din=None):
	"""Filmele TMDB cu titlul (sau titlul original) ca in ghid si, daca se stie, anul (cel mult un an diferenta)."""
	gasite = OrderedDict()
	for titlu in dict.fromkeys(t for t in titluri if t):
		p = {"query": titlu, "language": limba, "include_adult": "false"}
		if an:
			p["year"] = str(an)
		cod, j = _tmdb("/search/movie", p, cheie, cerere, json_din)
		dorit = I.normalizeaza(titlu)
		for m in (j or {}).get("results") or []:
			if not isinstance(m, dict) or not isinstance(m.get("id"), int):
				continue
			if dorit not in (I.normalizeaza(m.get("title") or u""), I.normalizeaza(m.get("original_title") or u"")):
				continue
			a = _anTmdb(m)
			if an and a and abs(a - int(an)) > 1:
				continue
			gasite.setdefault(m["id"], m)
		if gasite:
			# titlul original a gasit filmul: titlul tradus nu mai cere inca o cautare
			break
	return list(gasite.values())


def _filmTmdb(tid, cheie, limba, cerere=None, json_din=None):
	cod, j = _tmdb("/movie/%d" % int(tid), {"language": limba, "append_to_response": "credits"}, cheie, cerere, json_din)
	return j if cod == 200 and isinstance(j, dict) and j.get("id") else None


def _noteTmdb(m):
	try:
		v, n = float(m.get("vote_average") or 0), int(m.get("vote_count") or 0)
	except (TypeError, ValueError):
		return []
	return [("TMDB", "%.1f/10" % v)] if v > 0 and n > 0 else []


def _afisTmdb(m):
	cale = m.get("poster_path") or ""
	return TMDB_AFIS + cale if isinstance(cale, str) and re.match(r"^/[A-Za-z0-9_\-]+\.(jpg|png)$", cale) else ""


def _oameniTmdb(m):
	cr = m.get("credits") or {}
	regie = [p.get("name") for p in cr.get("crew") or [] if p.get("job") == "Director" and p.get("name")][:3]
	actori = [p.get("name") for p in cr.get("cast") or [] if p.get("name")][:MAX_ACTORI]
	return regie, actori


def fisaDinTmdb(m, limba=None):
	"""Fisa intreaga din TMDB (filmul nu e in Wikidata), cu aceleasi chei ca `fisa`."""
	regie, actori = _oameniTmdb(m)
	return {
		"qid": "", "tmdb": m.get("id"),
		"titlu": m.get("title") or m.get("original_title") or u"",
		"original": m.get("original_title") or u"",
		"an": _anTmdb(m),
		"durata_min": int(m.get("runtime") or 0),
		"genuri": [g.get("name") for g in m.get("genres") or [] if g.get("name")][:MAX_GENURI],
		"regie": regie, "actori": actori, "note": _noteTmdb(m),
		"descriere_scurta": (m.get("tagline") or u"").strip(),
		"rezumat": (m.get("overview") or u"").strip(),
		"limba_rezumat": limba or limbaMeniului(),
		"afis_adresa": _afisTmdb(m), "afis": "",
		"surse": ["TMDB"],
		"pagina": TMDB_PAGINA % m["id"] if m.get("id") else "",
	}


def _lipsaTmdb(f):
	return not f.get("afis_adresa") or not (f.get("rezumat") or u"").strip() or not f.get("note")


def completeazaTmdb(f, cheie, limba=None, cerere=None, json_din=None):
	"""Pe fir. Fisa din Wikidata + ce ii lipseste, din TMDB. Fara cheie sau cu fisa intreaga: nicio cerere, fisa la fel.
	Filmul: ID-ul din Wikidata (P4947) sau, fara el, cautarea cu titlul si anul (numai cand iese un singur film)."""
	if not cheie or not f or not _lipsaTmdb(f):
		return f
	limba = limba or limbaMeniului()
	try:
		tid = f.get("tmdb")
		if not tid:
			gasite = _cautaTmdb([f.get("original"), f.get("titlu")], f.get("an"), cheie, limba, cerere, json_din)
			if len(gasite) != 1:
				return f
			tid = gasite[0]["id"]
		m = _filmTmdb(tid, cheie, limba, cerere, json_din)
	except EroareTmdb:
		return f
	if not m:
		return f
	pus = False
	if not f.get("afis_adresa") and _afisTmdb(m):
		f["afis_adresa"], pus = _afisTmdb(m), True
	if not (f.get("rezumat") or u"").strip() and (m.get("overview") or u"").strip():
		f["rezumat"], f["limba_rezumat"], pus = m["overview"].strip(), limba, True
	if not f.get("note") and _noteTmdb(m):
		f["note"], pus = _noteTmdb(m), True
	if not f.get("genuri") and m.get("genres"):
		f["genuri"] = [g.get("name") for g in m["genres"] if g.get("name")][:MAX_GENURI]
		pus = pus or bool(f["genuri"])
	if not f.get("durata_min") and m.get("runtime"):
		f["durata_min"], pus = int(m["runtime"]), True
	regie, actori = _oameniTmdb(m)
	if not f.get("regie") and regie:
		f["regie"], pus = regie, True
	if not f.get("actori") and actori:
		f["actori"], pus = actori, True
	f["tmdb"] = m.get("id")
	if pus and "TMDB" not in f.get("surse", []):
		f["surse"] = list(f.get("surse") or []) + ["TMDB"]
	return f


def _numaiTmdb(info, cheie, limba, cerere=None, json_din=None):
	"""Wikidata nu are filmul: cautarea in TMDB (titlul si titlul original din ghid, cu anul). -> rezultat sau None."""
	try:
		gasite = _cautaTmdb([info.get("original"), info.get("titlu")], info.get("an"), cheie, limba, cerere, json_din)
		if not gasite:
			return None
		if len(gasite) > 1:
			candidati = [{"tmdb": m["id"], "titlu": m.get("title") or u"", "original": m.get("original_title") or u"",
				"an": _anTmdb(m)} for m in gasite[:MAX_CANDIDATI_TMDB]]
			return {"stare": "alege", "fisa": None, "candidati": candidati, "mesaj": u""}
		m = _filmTmdb(gasite[0]["id"], cheie, limba, cerere, json_din)
	except EroareTmdb:
		return None
	if not m:
		return None
	return {"stare": "gata", "fisa": fisaDinTmdb(m, limba), "candidati": [{"tmdb": m["id"], "titlu": m.get("title") or u"",
		"an": _anTmdb(m)}], "mesaj": u""}


def textCandidat(c):
	"""Randul unui film din lista de ales: titlul, anul, titlul original."""
	t = c.get("titlu") or c.get("original") or c.get("qid") or u""
	if c.get("an"):
		t = u"%s (%s)" % (t, c["an"])
	if c.get("original") and I.normalizeaza(c["original"]) != I.normalizeaza(c.get("titlu") or u""):
		t = u"%s, %s" % (t, c["original"])
	return t


def randDetalii(f):
	"""Anul, genurile, durata: 2010 · stiintifico-fantastic, thriller · 148 min."""
	parti = []
	if f.get("an"):
		parti.append(u"%s" % f["an"])
	if f.get("genuri"):
		parti.append(u", ".join(f["genuri"]))
	if f.get("durata_min"):
		parti.append(_t("%d min") % f["durata_min"])
	return u"  ·  ".join(parti)


def randNote(f):
	return u"   ".join(u"%s %s" % (n, v) for n, v in f.get("note") or [])


def textLung(f):
	"""Descrierea, regia, actorii si sursa, pentru caseta cu derulare."""
	r = []
	if f.get("rezumat"):
		r.append(f["rezumat"])
	elif f.get("descriere_scurta"):
		r.append(f["descriere_scurta"])
	else:
		r.append(_t("Wikipedia nu are încă o descriere pentru acest film."))
	if f.get("regie"):
		r.append(_t("Regia: %s") % u", ".join(f["regie"]))
	if f.get("actori"):
		r.append(_t("Cu: %s") % u", ".join(f["actori"]))
	r.append(_t("Sursa: %s") % u", ".join(f.get("surse") or ["Wikidata"]))
	if "TMDB" in (f.get("surse") or []):
		r.append(atribuireTmdb())
	return u"\n\n".join(r)


def atribuireTmdb():
	"""Fraza ceruta de regulile TMDB oriunde se arata datele lor."""
	return _t("Acest produs folosește API-ul TMDB, dar nu este aprobat sau certificat de TMDB.")


class Cautare(object):
	"""O cautare pe fir pentru un ecran sau o pagina: `porneste(functie, *arg)`; rezultatul vine in `gata(rezultat)` pe firul
	enigma2 (reactor.callFromThread, ca HdsCeasHttps si HdsCautareOarba). `opreste()` la inchidere: rezultatul tarziu
	nu mai ajunge."""

	def __init__(self, gata):
		self._gata = gata
		self._viu = True

	def porneste(self, functie, *arg):
		def lucru():
			try:
				rez = functie(*arg)
			except Exception as e:
				rez = {"stare": "eroare", "fisa": None, "candidati": [], "mesaj": e.__class__.__name__}
			try:
				from twisted.internet import reactor
				reactor.callFromThread(self._preda, rez)
			except ImportError:
				self._preda(rez)
		t = threading.Thread(target=lucru, name="HdsDespreFilm")
		t.daemon = True
		t.start()

	def _preda(self, rez):
		if self._viu:
			self._gata(rez)

	def opreste(self):
		self._viu = False
