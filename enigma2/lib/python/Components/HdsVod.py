# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Filme si seriale (VOD) din televiziunea prin internet: stratul de sursa.

Ecranele (Screens/HdsFilmeSeriale.py) si pagina web (HdsWebControl/filme_seriale_web.py) vorbesc NUMAI cu functiile de aici,
asa ca o alta sursa (portal Stalker, o biblioteca media de acasa cu API asemanator) intra cu o clasa noua, fara ecrane noi.
Nicio adresa de flux, niciun utilizator si nicio parola nu ies din strat: titlurile poarta numai id-ul, numele, nota, anul si
adresa posterului (care merge la HdsVodPoze, nu la pagina web).

Masurat pe 13.11.2026 cu un cont Xtream real (145.656 de filme, 44.127 de seriale): lista intreaga a filmelor cere 44 s, o
categorie 0,5 s, pagina unui film 0,3 s. Deci randurile se cer pe categorie, la nevoie; lista intreaga se citeste numai pentru
„Adăugate recent” (o data pe zi, in fundal, se tin minte primele 60) si pentru cautare (din mers, primele 100 gasite).
"""
import heapq
import json
import os
import re
import threading
import time
import uuid
from collections import OrderedDict

from Components import HdsIptvSurse as I
from Components import HdsIptvClient as C


def N_(text):
	return text


def _tradus(text):
	try:
		return _(text)
	except NameError:  # probele de pe PC
		return text


FILME, SERIALE = "filme", "seriale"
MAX_RAND = 3000                 # titluri tinute dintr-o categorie (cea mai mare la furnizorul probat: 2.408)
MAX_RANDURI = 16                # categorii tinute in memorie
PASTREAZA_S = 3600
MAX_RECENTE = 60
RECENTE_S = 24 * 3600
MAX_CAUTARE = 100
TERMEN_CAUTARE_S = 90
MAX_EPISOADE = 3000
MAX_SEZOANE = 200
MAX_LUCRARI = 48
_NUMAR = re.compile(r"^[0-9]{1,12}$")
_EXT = re.compile(r"^[A-Za-z0-9]{1,5}$")
_PREFIX = re.compile(r"^[\s|\[\(]*([A-Za-z]{2,5})[\s|\]\):\-]")
_AN = re.compile(r"\((19[0-9]{2}|20[0-9]{2})\)\s*$")

E_FARA_SURSA = N_("Nu ai niciun cont IPTV cu filme. Adaugă contul primit de la furnizor în Meniu > IPTV.")
E_NU_RASPUNDE = N_("Serverul furnizorului nu răspunde. Încearcă din nou peste câteva clipe.")
E_LIPSA = N_("Titlul nu mai este la furnizor.")
E_OCUPAT = N_("Se încarcă alte pagini. Încearcă din nou peste câteva clipe.")
E_EXPIRAT = N_("Pagina a expirat. Deschide-o din nou.")


def _numar(v):
	v = str(v if v is not None else "").strip()
	return v if _NUMAR.fullmatch(v) else ""


def _text(v, maxim=2000):
	if not isinstance(v, (str, int, float)):
		return ""
	return " ".join("".join(c if ord(c) >= 32 and ord(c) != 127 else " " for c in str(v)).split())[:maxim]


def _poza(v):
	if isinstance(v, list):
		v = v[0] if v else ""
	v = str(v or "").strip()
	return v[:I.MAX_ADRESA] if v.lower().startswith(("http://", "https://")) and " " not in v else ""


def _nota(v):
	try:
		n = float(str(v).replace(",", "."))
	except (TypeError, ValueError):
		return ""
	return "%.1f" % n if 0 < n <= 10 else ""


def _an(*valori):
	for v in valori:
		m = re.search(r"(19[0-9]{2}|20[0-9]{2})", str(v or ""))
		if m:
			return m.group(1)
	return ""


def _durata(secunde, text=""):
	try:
		s = int(float(secunde))
	except (TypeError, ValueError):
		s = 0
	if s <= 0:
		m = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})$", str(text or "").strip())
		if m:
			s = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
		else:
			m = re.match(r"^(\d{1,4})\s*(min)?", str(text or "").strip())
			s = int(m.group(1)) * 60 if m else 0
	return s if 0 < s < 48 * 3600 else 0


_PREFIX_TITLU = re.compile(r"^\s*[|\[(]\s*[A-Za-z]{2,5}\s*[|\])]\s*[-:]?\s*")


def numeCurat(nume):
	"""Numele de afisat al unui titlu, fara prefixul de tara al furnizorului („|DE| Der Pate (1972)” -> „Der Pate (1972)”)."""
	n = I.numeCurat(nume)
	return _PREFIX_TITLU.sub("", n).strip() or n


def _numeFaraAn(nume):
	return _AN.sub("", nume).strip() or nume


def textDurata(secunde):
	"""1 h 52 min / 48 min; gol la 0."""
	if not secunde:
		return ""
	m = (int(secunde) + 30) // 60
	return (_tradus(N_("%d h %02d min")) % (m // 60, m % 60)) if m >= 60 else (_tradus(N_("%d min")) % m)


def prefixLimba(nume):
	m = _PREFIX.match(nume or "")
	return m.group(1).upper() if m else ""


# Prefixele de tara/limba pe care furnizorii le pun in numele categoriilor („|DE| KINO”, „AT | SPORT”), dupa limba interfetei:
# o limba vorbita in mai multe tari aduce toate tarile ei (germana: DE, AT, CH). Tara din limba aleasa (de_AT) vine prima.
PREFIXE_LIMBA = {
	"ro": ("RO", "MD"), "de": ("DE", "GER", "AT", "CH"), "en": ("EN", "ENG", "UK", "GB", "US", "IE", "CA", "AU"),
	"fr": ("FR", "BE", "CH", "CA"), "it": ("IT", "ITA", "CH"), "es": ("ES", "SPA", "LAT", "MX", "AR"), "pt": ("PT", "BR"),
	"nl": ("NL", "BE"), "pl": ("PL", "POL"), "tr": ("TR", "TUR"), "hu": ("HU", "HUN"), "cs": ("CZ", "CS", "SK"),
	"sk": ("SK", "CZ"), "bg": ("BG", "BUL"), "el": ("GR", "GRE", "CY"), "ru": ("RU", "RUS"), "uk": ("UA", "UKR"),
	"sr": ("RS", "SRB", "EXYU", "YU"), "hr": ("HR", "CRO", "EXYU", "YU"), "sl": ("SI", "SLO", "EXYU"), "bs": ("BA", "EXYU"),
	"mk": ("MK", "EXYU"), "sq": ("AL", "ALB", "XK"), "ar": ("AR", "ARB", "ARAB"), "fa": ("IR", "PER"), "sv": ("SE", "SWE"),
	"da": ("DK", "DAN"), "nb": ("NO", "NOR"), "no": ("NO", "NOR"), "fi": ("FI", "FIN"), "lt": ("LT",), "lv": ("LV",),
	"et": ("EE", "EST"), "he": ("IL", "ISR"), "hi": ("IN", "IND"), "ja": ("JP",), "ko": ("KR",), "zh": ("CN", "CHN", "TW", "HK"),
}


def prefixeTara(limba):
	"""„de_AT” -> ("AT", "DE", "GER", "CH"); „ro_RO” -> ("RO", "MD"); o limba necunoscuta -> codul ei."""
	limba = (limba or "").replace("-", "_")
	cod, _s, tara = limba.partition("_")
	cod, tara = cod.lower()[:3], tara.upper()[:3]
	rez = list(PREFIXE_LIMBA.get(cod, (cod.upper(),) if cod else ()))
	if tara and tara in rez:
		rez.remove(tara)
	return tuple(([tara] if tara else []) + rez)


def ordoneazaCategorii(categorii, limba):
	"""Categoriile tarii (dupa limba interfetei) intai, apoi cele pentru toate limbile, apoi engleza, apoi restul, in ordinea
	furnizorului. Cu „Categoriile țării mele primele” = Nu, ordinea furnizorului neatinsa."""
	if not activ("tara"):
		return list(categorii)
	tari = prefixeTara(limba)
	engleza = PREFIXE_LIMBA["en"]
	def loc(c):
		p = prefixLimba(c[1])
		if p and p in tari:
			return tari.index(p) * 0.01
		if p in ("MULTI", "MULT", "ALL", "INT"):
			return 1
		if p in engleza:
			return 2
		return 3
	return [c for _i, c in sorted(enumerate(categorii), key=lambda x: (loc(x[1]), x[0]))]


def activ(functie):
	"""Setarile Da/Nu din „Funcțiile televiziunii prin internet”: poze, continua, recente, tara (Da cand nu exista config, pe PC)."""
	try:
		from Components.config import config
		return bool(getattr(config.usage, "hds_vod_" + functie).value)
	except Exception:
		return True


def _limbaReceptor():
	try:
		from Components.config import config
		return config.osd.language.value or "ro_RO"
	except Exception:
		return "ro"


def _pista(d, fel):
	"""Pista audio sau video din raspunsul furnizorului (un dict ffprobe) -> text scurt."""
	if not isinstance(d, dict):
		return ""
	codec = _text(d.get("codec_name"), 20).upper().replace("EAC3", "E-AC-3").replace("AC3", "AC-3")
	if fel == "video":
		try:
			l, h = int(d.get("width") or 0), int(d.get("height") or 0)
		except (TypeError, ValueError):
			l, h = 0, 0
		parti = []
		if h >= 2000 or l >= 3800:
			parti.append("4K")
		elif h >= 1000 or l >= 1900:
			parti.append("1080p")
		elif h >= 700:
			parti.append("720p")
		elif h:
			parti.append("%dp" % h)
		if codec:
			parti.append(codec)
		tr = str(d.get("color_transfer") or "")
		if tr == "smpte2084":
			parti.append("HDR10")
		elif tr == "arib-std-b67":
			parti.append("HLG")
		return " ".join(parti)
	tags = d.get("tags") if isinstance(d.get("tags"), dict) else {}
	limba = _text(tags.get("language"), 8)
	try:
		canale = int(d.get("channels") or 0)
	except (TypeError, ValueError):
		canale = 0
	parti = [x for x in (limba.upper() if limba and limba != "und" else "", {6: "5.1", 8: "7.1", 2: "2.0", 1: "1.0"}.get(canale, ""), codec) if x]
	return " ".join(parti)


class Sursa(object):
	"""Forma comuna a unei surse de filme si seriale. Toate functiile ruleaza pe firul de lucru (au retea)."""
	fel = ""

	def __init__(self, s):
		self.s = s
		self.id = s.get("id") or ""
		self.nume = _text(s.get("nume") or s.get("name"), 80) or self.id

	def categorii(self, tip):
		raise NotImplementedError

	def rand(self, tip, categorie):
		raise NotImplementedError

	def toate(self, tip):
		"""Toate titlurile, din mers (generator); numai pentru recente si cautare."""
		raise NotImplementedError

	def detalii(self, tip, titlu_id):
		raise NotImplementedError

	def referinta(self, cheie):
		"""Referinta de redare (prin releul local, fara date de acces in ea)."""
		return I.refCanal(self.id, cheie) if I.cheieBuna(cheie) else None


class SursaXtream(Sursa):
	fel = "xtream"
	_ACTIUNI = {FILME: ("get_vod_categories", "get_vod_streams", "get_vod_info", "vod_id"),
		SERIALE: ("get_series_categories", "get_series", "get_series_info", "series_id")}

	def _lista(self, actiune, parametri=None):
		return C.listaXtream(self.s, actiune, parametri)

	def categorii(self, tip):
		rez = []
		for c in self._lista(self._ACTIUNI[tip][0]):
			if isinstance(c, dict) and _numar(c.get("category_id")):
				rez.append((_numar(c.get("category_id")), I.numeCurat(c.get("category_name")) or "?"))
			if len(rez) >= I.MAX_GRUPE:
				break
		return rez

	def _titlu(self, tip, f):
		if not isinstance(f, dict):
			return None
		if tip == FILME:
			tid = _numar(f.get("stream_id"))
			ext = str(f.get("container_extension") or "mp4").lower()
			if not tid or not _EXT.fullmatch(ext):
				return None
			nume = numeCurat(f.get("name"))
			return {"id": tid, "cheie": "v%s.%s" % (tid, ext), "nume": nume, "poza": _poza(f.get("stream_icon")),
				"nota": _nota(f.get("rating")), "an": _an(f.get("year"), nume), "adaugat": int(_numar(f.get("added")) or 0)} if nume else None
		tid = _numar(f.get("series_id"))
		nume = numeCurat(f.get("name"))
		if not tid or not nume:
			return None
		return {"id": tid, "cheie": "", "nume": nume, "poza": _poza(f.get("cover")), "nota": _nota(f.get("rating")),
			"an": _an(f.get("releaseDate"), f.get("release_date"), nume), "adaugat": int(_numar(f.get("last_modified")) or 0)}

	def rand(self, tip, categorie):
		rez = []
		lista = self._lista(self._ACTIUNI[tip][1], {"category_id": categorie})
		try:
			for f in lista:
				t = self._titlu(tip, f)
				if t:
					rez.append(t)
					if len(rez) >= MAX_RAND:
						break
		finally:
			inchide = getattr(lista, "close", None)
			if inchide:
				inchide()
		return rez

	def toate(self, tip):
		lista = self._lista(self._ACTIUNI[tip][1])
		try:
			for f in lista:
				t = self._titlu(tip, f)
				if t:
					yield t
		finally:
			inchide = getattr(lista, "close", None)
			if inchide:
				inchide()

	def detalii(self, tip, titlu_id):
		actiune, cheie = self._ACTIUNI[tip][2], self._ACTIUNI[tip][3]
		d = C.dateXtream(self.s, actiune, {cheie: titlu_id})
		if not isinstance(d, dict):
			raise C.EroareIptv(E_LIPSA)
		info = d.get("info") if isinstance(d.get("info"), dict) else {}
		rez = {"id": titlu_id, "tip": tip,
			"nume": _numeFaraAn(numeCurat(info.get("name") or (d.get("movie_data") or {}).get("name") or "")),
			"descriere": _text(info.get("plot") or info.get("description"), 1500),
			"gen": _text(info.get("genre"), 120), "tara": _text(info.get("country"), 60),
			"regia": _text(info.get("director"), 120), "actori": _text(info.get("cast") or info.get("actors"), 300),
			"nota": _nota(info.get("rating")),
			"an": _an(info.get("releasedate"), info.get("release_date"), info.get("releaseDate"), info.get("name")),
			"poster": _poza(info.get("cover_big") or info.get("movie_image") or info.get("cover")),
			"fundal": _poza(info.get("backdrop_path")),
			"trailer": _text(info.get("youtube_trailer"), 20) if re.fullmatch(r"[A-Za-z0-9_\-]{6,20}", str(info.get("youtube_trailer") or "")) else "",
			"varsta": _text(info.get("age") or info.get("mpaa_rating"), 10)}
		if tip == FILME:
			md = d.get("movie_data") if isinstance(d.get("movie_data"), dict) else {}
			ext = str(md.get("container_extension") or "mp4").lower()
			if not _EXT.fullmatch(ext):
				raise C.EroareIptv(E_LIPSA)
			rez["cheie"] = "v%s.%s" % (titlu_id, ext)
			rez["durata"] = _durata(info.get("duration_secs"), info.get("duration"))
			rez["video"] = _pista(info.get("video"), "video")
			rez["audio"] = _pista(info.get("audio"), "audio")
			return rez
		rez["durata"] = _durata(0, info.get("episode_run_time"))
		episoade = d.get("episodes") if isinstance(d.get("episodes"), dict) else {}
		sezoane, total = [], 0
		for numar in sorted((k for k in episoade if _numar(k)), key=int)[:MAX_SEZOANE]:
			lista = []
			for e in episoade[numar] if isinstance(episoade[numar], list) else ():
				if total >= MAX_EPISOADE or not isinstance(e, dict):
					break
				eid = _numar(e.get("id"))
				ext = str(e.get("container_extension") or "mp4").lower()
				if not eid or not _EXT.fullmatch(ext):
					continue
				ei = e.get("info") if isinstance(e.get("info"), dict) else {}
				lista.append({"id": eid, "cheie": "e%s.%s" % (eid, ext), "numar": _text(e.get("episode_num"), 6),
					"nume": I.numeCurat(e.get("title")) or eid, "descriere": _text(ei.get("plot"), 600),
					"durata": _durata(ei.get("duration_secs"), ei.get("duration")), "poza": _poza(ei.get("movie_image"))})
				total += 1
			if lista:
				sezoane.append({"numar": numar, "episoade": lista})
		rez["sezoane"] = sezoane
		return rez


# Alte surse (de facut): Stalker (type=vod, get_ordered_list paginat, create_link type=vod: cere o cheie noua in releu,
# HdsIptvAdrese.adresa) si bibliotecile media de acasa (Emby / Jellyfin: /Items, /Shows/{id}/Seasons, /Videos/{id}/stream,
# /Sessions/Playing/Progress), cu aceeasi forma: categorii, rand, toate, detalii, referinta.
_CLASE = {"xtream": SursaXtream}


def surse():
	"""Sursele care au filme si seriale, in ordinea din IPTV."""
	rez = []
	for s in I.citesteSurse():
		cls = _CLASE.get(s.get("fel"))
		if cls is not None:
			rez.append(cls(s))
	return rez


def sursa(sursa_id):
	for x in surse():
		if x.id == sursa_id:
			return x
	return None


def publicSurse():
	return [{"id": x.id, "nume": x.nume, "fel": x.fel} for x in surse()]


# ------------------------------------------------------------------ memoria (randuri, categorii, recente)

_lacatDate = threading.Lock()
_randuri = OrderedDict()        # (sid, tip, categorie) -> (ora, [titluri])
_categorii = {}                 # (sid, tip) -> (ora, [(id, nume)])


def _dinMemorie(depozit, cheie, maxim=None):
	with _lacatDate:
		v = depozit.get(cheie)
		if v and time.monotonic() - v[0] < PASTREAZA_S:
			if isinstance(depozit, OrderedDict):
				depozit.move_to_end(cheie)
			return v[1]
	return None


def _inMemorie(depozit, cheie, valoare, maxim=None):
	with _lacatDate:
		depozit[cheie] = (time.monotonic(), valoare)
		if maxim and isinstance(depozit, OrderedDict):
			while len(depozit) > maxim:
				depozit.popitem(last=False)
	return valoare


def golesteMemoria():
	with _lacatDate:
		_randuri.clear()
		_categorii.clear()


def _caleRecente(sid, tip):
	return os.path.join(I.DOSAR, "vod-recente-%s-%s.json" % (sid, tip))


def recenteDinDisc(sid, tip):
	"""(ora, titluri) din ultima citire a listei intregi, sau (0, [])."""
	try:
		with open(_caleRecente(sid, tip), encoding="utf-8") as f:
			d = json.load(f)
		if isinstance(d, dict) and isinstance(d.get("titluri"), list):
			return float(d.get("ora") or 0), [t for t in d["titluri"] if isinstance(t, dict)][:MAX_RECENTE]
	except (IOError, OSError, ValueError):
		pass
	return 0, []


def _recenteNoi(src, tip):
	cele = heapq.nlargest(MAX_RECENTE, src.toate(tip), key=lambda t: t.get("adaugat") or 0)
	try:
		os.makedirs(I.DOSAR, mode=0o700, exist_ok=True)
		I._scrie(_caleRecente(src.id, tip), json.dumps({"ora": time.time(), "titluri": cele}, ensure_ascii=False).encode("utf-8"), 0o600)
	except (IOError, OSError):
		pass
	return cele


def recenteDeAdus(sid, tip):
	ora, _t = recenteDinDisc(sid, tip)
	return not (0 <= time.time() - ora < RECENTE_S)


def cauta(src, tip, text, gasite=None):
	"""Titlurile al caror nume contine textul (fara diferenta de litere mari), primele MAX_CAUTARE. gasite: lista in care se pun
	pe masura ce se gasesc (ecranul le arata din mers)."""
	text = (text or "").casefold().strip()
	rez = gasite if gasite is not None else []
	if not text:
		return rez
	inceput = time.monotonic()
	for t in src.toate(tip):
		if text in t["nume"].casefold():
			t["tip"] = tip
			rez.append(t)
			if len(rez) >= MAX_CAUTARE:
				break
		if time.monotonic() - inceput > TERMEN_CAUTARE_S:
			break
	return rez


# ------------------------------------------------------------------ lucrarile (pe doua fire: scurte si lungi)

def lucreaza(fel, sid, tip="", arg="", gasite=None):
	"""Un raspuns public (fara adrese de flux sau date de acces). Ruleaza pe firul de lucru."""
	src = sursa(sid)
	if src is None:
		return {"result": False, "message": E_FARA_SURSA}
	if tip not in (FILME, SERIALE):
		return {"result": False, "message": E_LIPSA}
	try:
		if fel == "categorii":
			v = _dinMemorie(_categorii, (sid, tip))
			if v is None:
				v = _inMemorie(_categorii, (sid, tip), ordoneazaCategorii(src.categorii(tip), _limbaReceptor()))
			return {"result": True, "categorii": [{"id": a, "nume": b} for a, b in v]}
		if fel == "rand":
			if not _numar(arg):
				return {"result": False, "message": E_LIPSA}
			v = _dinMemorie(_randuri, (sid, tip, arg))
			if v is None:
				v = _inMemorie(_randuri, (sid, tip, arg), src.rand(tip, arg), MAX_RANDURI)
			return {"result": True, "titluri": v}
		if fel == "recente":
			if not activ("recente"):
				return {"result": True, "titluri": [], "oprit": True}
			ora, v = recenteDinDisc(sid, tip)
			if arg == "aduce" or not v:
				v = _recenteNoi(src, tip)
			return {"result": True, "titluri": v}
		if fel == "detalii":
			if not _numar(arg):
				return {"result": False, "message": E_LIPSA}
			return {"result": True, "detalii": src.detalii(tip, arg)}
		if fel == "cauta":
			return {"result": True, "titluri": cauta(src, tip, arg, gasite)}
	except C.EroareIptv as e:
		return {"result": False, "message": e.mesaj}
	except Exception as e:
		# exceptiile HTTP pot avea adresa cu parola in ele: nu ies nici in pagina, nici in jurnal
		print("[HdsVod] %s: %s" % (fel, type(e).__name__))
		return {"result": False, "message": E_NU_RASPUNDE}
	return {"result": False, "message": E_LIPSA}


_lacat = threading.Lock()
_lucrari = OrderedDict()
_cozi = {"scurt": [], "lung": []}
_fire = {}
LUNGI = ("recente", "cauta")


def _bucla(coada):
	while True:
		with _lacat:
			if not _cozi[coada]:
				_fire.pop(coada, None)
				return
			cheie = _cozi[coada].pop()        # cea mai noua intai: omul a mers mai departe
			lucrare = _lucrari.get(cheie)
		if lucrare is None:
			continue
		rez = lucreaza(*lucrare["argumente"], gasite=lucrare["gasite"])
		with _lacat:
			lucrare["rezultat"] = rez
			lucrare["gata"] = time.monotonic()


def _curata():
	acum = time.monotonic()
	for cheie, l in list(_lucrari.items()):
		if l.get("gata") and acum - l["gata"] > 300:
			del _lucrari[cheie]


def cere(fel, sid, tip="", arg=""):
	"""Cheia lucrarii, imediat (rezultatul il citeste ecranul cu rezultat(cheie)); gol = prea multe lucrari."""
	argumente = (fel, sid, tip, _text(arg, 80))
	coada = "lung" if fel in LUNGI else "scurt"
	with _lacat:
		_curata()
		for cheie, l in _lucrari.items():
			if l["argumente"] == argumente and not (l.get("gata") and fel == "recente" and arg == "aduce"):
				if not l.get("gata") and cheie in _cozi[coada]:
					_cozi[coada].remove(cheie)
					_cozi[coada].append(cheie)
				return cheie
		if len(_lucrari) >= MAX_LUCRARI:
			gata = [k for k, l in _lucrari.items() if l.get("gata")]
			if not gata:
				return ""
			del _lucrari[gata[0]]
		cheie = uuid.uuid4().hex
		_lucrari[cheie] = {"argumente": argumente, "gasite": []}
		_cozi[coada].append(cheie)
		if coada not in _fire:
			fir = threading.Thread(target=_bucla, args=(coada,), name="HdsVod-" + coada)
			fir.daemon = True
			_fire[coada] = fir
			fir.start()
	return cheie


def rezultat(cheie):
	with _lacat:
		l = _lucrari.get(cheie)
		if l is None:
			return {"result": False, "lucreaza": False, "message": E_EXPIRAT}
		if not l.get("gata"):
			return {"result": True, "lucreaza": True, "titluri": list(l["gasite"])}
		return dict(l["rezultat"], lucreaza=False)


def renunta(cheie):
	"""Ecranul nu mai vrea rezultatul: o lucrare care n-a inceput iese din coada."""
	with _lacat:
		for coada in _cozi.values():
			if cheie in coada:
				coada.remove(cheie)
				_lucrari.pop(cheie, None)
