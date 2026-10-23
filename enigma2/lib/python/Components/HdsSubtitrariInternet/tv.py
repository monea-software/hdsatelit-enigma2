# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# tv.py: subtitrari de pe internet pe un canal TV in direct si pe o inregistrare .ts (serviciul DVB,
# lib/service/servicedvb.cpp), pentru filmele date fara subtitrare.
#
# DRUMUL (tasta SUB > "Caută subtitrări pe internet", sau pagina web /descarcare-subtitrari):
# 1. filmul de acum din EIT (canal: emisiunea care merge; inregistrare: emisiunea din .eit), identificat in Wikidata
#    fara cheie (identificare.py): ID-ul IMDb, titlul original, anul; omul alege cand nu e sigur sau scrie titlul;
# 2. cautarea la sursele imaginii dupa ID (lucru.py, surse/*), plus fisierele deja pe receptor (descarcate inainte pentru
#    acelasi film, sau langa inregistrare): o reluare a filmului nu mai cere o descarcare;
# 3. salvarea: langa inregistrare; pe canal in DOSARE (discul, altfel /tmp), cu ID-ul IMDb in nume;
# 4. incarcarea in serviciu (incarca): replicile citite cu Components/HdsSubtitrariFilm.py (formatele, codarea), date
#    serviciului ca fisier 100 (setExternalSubtitles / Cues) si pornite; viteza automata din fps-ul subtitrarii (de la
#    sursa, altfel 23,976) si al canalului (25 sau 50: x 23,976 / 25); pozitia de pornire: pe canal ora de inceput din EPG,
#    la inregistrare inceputul emisiunii fata de pornirea inregistrarii;
# 5. reglajul (bara "Potrivirea subtitrării" din ecrane.py si pagina web): replica urmatoare / dinainte (replica aleasa
#    incepe acum), +/- 0,5 s, "Reclamă" (ceasul subtitrarii sta cat tine pauza si merge din acelasi loc), "Acum începe
#    filmul", viteza.
# Ceasul e al serviciului (PTS-ul decodorului pe canal, pozitia la inregistrare), deci timeshift-ul si derularea
# inregistrarii merg singure. O schimbare de canal pierde subtitrarea din serviciu (serviciul nou nu o are); ea se tine
# minte pe canal (memoria de mai jos, numai in RAM) si, la intoarcerea pe acelasi canal in aceeasi emisiune (sau pe
# aceeasi inregistrare), revine singura, cu viteza si potrivirea de dinainte (reia, chemata de
# Components/HdsPisteLimbi.aplicaSubtitrare la serviciul nou). Fisierul ramane pe receptor si apare primul la cautarea
# urmatoare a aceluiasi film.
#
# FIRELE: identificarea, cautarea, listarea dosarelor si citirea fisierului merg pe fire; serviciul se atinge numai pe
# firul enigma2 (eTimer). Partea de sus (pana la "legatura cu enigma2") nu cere enigma: se probeaza pe PC.

import os
import re
import threading
import time
import unicodedata

from . import identificare as ID


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabele se traduc la folosire."""
	return text


def _t(text):
	if not text:
		return text or u""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


INDEX = 100                 # numarul subtitrarii in lista serviciului (una singura pe serviciu)
PAS_MS = 500                # "+/- 0,5 s"
FPS_IMPLICIT = 23.976       # fps-ul unei subtitrari fara fps de la sursa (copiile WEB si Blu-ray)
# (dosarul, punctul de montare care trebuie sa existe sau None), ca salvare.DOSARE_REZERVA
DOSARE = (("/media/hdd/subtitrari", "/media/hdd"), ("/tmp/hds-subtitrari", None))
MAX_LOCALE = 20
# vitezele: fps-ul copiei pe care s-a facut subtitrarea; "auto" = de la sursa, altfel 23,976
VITEZE = ("auto", "23.976", "24", "1")
EXTENSII_SUB = (".srt", ".sub", ".ass", ".ssa", ".vtt", ".smi", ".sami", ".txt", ".mpl")


def familieCanal(fps_canal):
	"""Cadrele pe secunda in care merge un film pe canal: 25 (canalele de 25 si 50), 23,976 pe canalele de 29,97 / 59,94
	(acolo filmul ramane la viteza lui, prin 3:2), altfel fps-ul canalului; fara fps (-1, radio, emulator): 25."""
	try:
		f = float(fps_canal)
	except (TypeError, ValueError):
		return 25.0
	if f > 1000:
		f /= 1000.0
	if f <= 0:
		return 25.0
	for baza, rezultat, toleranta in ((24.0, 24.0, 0.01), (23.976, 23.976, 0.05), (25.0, 25.0, 0.3), (50.0, 25.0, 0.3),
			(29.97, 23.976, 0.3), (59.94, 23.976, 0.3), (30.0, 23.976, 0.3), (60.0, 23.976, 0.3)):
		if abs(f - baza) < toleranta:
			return rezultat
	return 25.0


def fpsSubtitrare(cod, fps_sursa):
	"""fps-ul copiei subtitrarii dupa alegerea omului (VITEZE) si ce a dat sursa; None la "1" (fara schimbare)."""
	if cod == "1":
		return None
	if cod in ("23.976", "24"):
		return float(cod)
	try:
		f = float(fps_sursa)
		if 10.0 <= f <= 120.0:
			return f
	except (TypeError, ValueError):
		pass
	return FPS_IMPLICIT


def factorViteza(cod, fps_sursa, fps_canal):
	"""Factorul de viteza pentru serviciu (setSubtitleSpeed): timpii fisierului x factor. 23,976 pe un canal de 25 ->
	0,95904; aceeasi viteza -> 1; o subtitrare de 29,97 / 30 (seriale americane) ramane la 1."""
	s = fpsSubtitrare(cod, fps_sursa)
	if s is None or not (23.0 <= s <= 25.5):
		return 1.0
	f = s / familieCanal(fps_canal)
	return f if 0.5 <= f <= 2.0 else 1.0


def textViteza(cod, fps_sursa, fps_canal):
	"""de la 23,976 la 25 cadre/s / Fără schimbare (pentru ecrane si web; sagetile nu sunt in fontul skinului)."""
	s = fpsSubtitrare(cod, fps_sursa)
	c = familieCanal(fps_canal)
	f = factorViteza(cod, fps_sursa, fps_canal)
	if s is None or abs(f - 1.0) < 0.0005:
		return _t("Fără schimbare")
	return _t("de la %s la %s cadre/s") % (_numar(s), _numar(c))


def _numar(f):
	t = (u"%.3f" % f).rstrip(u"0").rstrip(u".")
	return t.replace(u".", u",")


def textPozitie(ms):
	"""Pozitia in film: 1:23:45 / 12:05 / -0:30 (inainte de inceput)."""
	try:
		ms = int(ms)
	except (TypeError, ValueError):
		return u""
	semn = u"-" if ms < 0 else u""
	s = abs(ms) // 1000
	if s >= 3600:
		return u"%s%d:%02d:%02d" % (semn, s // 3600, s // 60 % 60, s % 60)
	return u"%s%d:%02d" % (semn, s // 60, s % 60)


def intarziereInitiala(fel, ceas_ms, acum_s, inceput_s, durata_s, creata_s=0):
	"""Intarzierea de pornire (ceasul serviciului la inceputul filmului).
	canal: filmul a inceput la ora din EPG, deci la ceasul de acum minus timpul trecut de atunci (in afara emisiunii:
	acum incepe); inregistrare: inceputul emisiunii fata de pornirea inregistrarii (ceasul = pozitia in fisier)."""
	if fel == "inregistrare":
		if inceput_s and creata_s and abs(inceput_s - creata_s) <= 3 * 3600:
			return int(max(0, inceput_s - creata_s) * 1000)
		return 0
	if inceput_s and acum_s >= inceput_s - 600 and (not durata_s or acum_s <= inceput_s + durata_s + 1800):
		return int(ceas_ms - (acum_s - inceput_s) * 1000)
	return int(ceas_ms)


def slug(text):
	"""Un nume de fisier din titlu: litere fara diacritice, cifre si cratime."""
	t = unicodedata.normalize("NFKD", u"%s" % (text or u""))
	t = u"".join(c for c in t if not unicodedata.combining(c))
	t = re.sub(r"[^A-Za-z0-9]+", u"-", t).strip(u"-")
	return t[:60] or u"film"


def bazaNume(film):
	"""Numele (fara extensie) al subtitrarii salvate pentru un film de pe canal: tt0133093-The-Matrix-1999."""
	parti = []
	if film.get("imdb"):
		parti.append(film["imdb"])
	parti.append(slug(film.get("titlu") or u""))
	if film.get("an"):
		parti.append(u"%s" % film["an"])
	return u"-".join(parti)


def dosarCanal(este_montat=None):
	"""Dosarul subtitrarilor de pe canale: /media/hdd/subtitrari daca discul e montat, altfel /tmp/hds-subtitrari."""
	if este_montat is None:
		from .salvare import montat as este_montat
	for dosar, montare in DOSARE:
		if montare and not este_montat(montare):
			continue
		return dosar
	return DOSARE[-1][0]


def fisiereLocale(film, dosare=None, listeaza=os.listdir):
	"""Subtitrarile deja pe receptor pentru filmul de pe canal: in DOSARE, cele care incep cu ID-ul IMDb (sau cu numele
	facut din titlu, fara ID). -> [{"cale", "nume"}], cele mai noi intai (dupa nume)."""
	rez = []
	cheie = film.get("imdb") or u""
	baza = bazaNume(dict(film, imdb=u"")) if not cheie else u""
	for dosar in (dosare or [d for d, m in DOSARE]):
		try:
			nume = listeaza(dosar)
		except (OSError, IOError):
			continue
		for n in sorted(nume, reverse=True):
			if os.path.splitext(n)[1].lower() not in EXTENSII_SUB:
				continue
			if (cheie and n.startswith(cheie + u"-")) or (baza and n.startswith(baza)):
				rez.append({"cale": os.path.join(dosar, n), "nume": n})
				if len(rez) >= MAX_LOCALE:
					return rez
	return rez


class FilmTv(object):
	"""Filmul de pe serviciul DVB de acum: emisiunea din EIT, identificarea, subtitrarea pusa, viteza aleasa."""

	def __init__(self, ref, ptr, fel, cale, eveniment):
		self.ref = ref
		self.ptr = ptr
		self.fel = fel                # "canal" sau "inregistrare"
		self.cale = cale              # calea inregistrarii ("" pe canal)
		self.eveniment = eveniment    # {"titlu", "scurt", "extins", "inceput", "durata", "creata", "canal"}
		self.info = ID.dinEveniment(eveniment.get("titlu"), eveniment.get("scurt"), eveniment.get("extins"),
			eveniment.get("inceput"), eveniment.get("durata"))
		self.lacat = threading.Lock()
		self.identificare = {"stare": "nepornita", "candidati": [], "mesaj": u""}
		self.ales = None              # candidatul ales (dict din identificare) sau None
		self.text_om = None           # titlul scris de om
		self.locale = []              # fisierele deja pe receptor
		self.subtitrare = None        # {"cale", "nume", "fps", "limba", "replici"} pusa in serviciu
		self.viteza = "auto"
		self.mesaj = u""
		self.lucreaza = False

	def pentruCautare(self):
		"""Filmul pentru lucru.cauta: {"titlu", "an", "imdb", "tmdb"}."""
		with self.lacat:
			a = self.ales
			text = self.text_om
		if a is not None:
			return {"titlu": a.get("original") or a.get("titlu") or self.info.get("titlu"), "an": a.get("an") or self.info.get("an"),
				"imdb": a.get("imdb") or u"", "tmdb": a.get("tmdb") or u""}
		return {"titlu": text or self.info.get("original") or self.info.get("titlu"), "an": self.info.get("an"),
			"imdb": u"", "tmdb": u""}

	def caleSalvare(self, este_montat=None):
		"""Unde se salveaza: langa inregistrare (calea ei), pe canal un nume in dosarul subtitrarilor."""
		if self.fel == "inregistrare" and self.cale:
			return self.cale
		# cai de receptor (Linux), si in probele de pe PC
		return dosarCanal(este_montat).rstrip(u"/") + u"/" + bazaNume(self.pentruCautare()) + u".ts"

	def stareIdentificare(self):
		with self.lacat:
			d = dict(self.identificare)
			d["candidati"] = [dict(c) for c in self.identificare.get("candidati") or []]
			d["ales"] = dict(self.ales) if self.ales else None
			d["text_om"] = self.text_om
			d["lucreaza"] = self.lucreaza
		return d


def identificaPeFir(f, limbi=None, wd=None, gata=None):
	"""Porneste identificarea filmului f pe un fir; la sfarsit, sigur = ales singur. Fisierele locale se cauta tot aici."""
	with f.lacat:
		if f.lucreaza:
			return False
		f.lucreaza = True
		f.identificare = {"stare": "cauta", "candidati": [], "mesaj": _t("Se caută filmul în Wikidata...")}
		info = dict(f.info)
		if f.text_om:
			info.update({"titlu": f.text_om, "original": u""})

	def lucru():
		try:
			if not info.get("titlu") and not info.get("original"):
				rez = {"stare": "niciunul", "candidati": [], "mesaj": _t("Emisiunea de acum nu are titlu în ghid. Scrie titlul.")}
			else:
				rez = ID.identifica(info, limbi, wd)
		except Exception as e:      # nimic nu scapa dintr-un fir
			rez = {"stare": "eroare", "candidati": [], "mesaj": _t("Identificarea nu a mers: %s") % e.__class__.__name__}
		with f.lacat:
			f.identificare = rez
			f.ales = rez["candidati"][0] if rez["stare"] == "sigur" else None
			f.lucreaza = False
		listeazaLocale(f)
		if gata is not None:
			gata(f)
	fir = threading.Thread(target=lucru, name="HdsSubtitrariTv")
	fir.daemon = True
	fir.start()
	return True


def listeazaLocale(f):
	"""Pe fir: fisierele de pe receptor pentru filmul ales (langa inregistrare, sau in DOSARE dupa ID / titlu)."""
	try:
		if f.fel == "inregistrare" and f.cale:
			from Components import HdsSubtitrariFilm as SF
			gasite = [{"cale": g["cale"], "nume": g["nume"]} for g in SF.gasesteFisiere(f.cale)
				if g.get("ext") in EXTENSII_SUB][:MAX_LOCALE]
		else:
			gasite = fisiereLocale(f.pentruCautare())
	except Exception as e:
		print("[HdsSubtitrariTv] fisierele de pe receptor: %s" % e.__class__.__name__)
		gasite = []
	with f.lacat:
		f.locale = gasite


def alegeCandidat(f, i):
	with f.lacat:
		c = f.identificare.get("candidati") or []
		if not (0 <= i < len(c)):
			return False
		f.ales = dict(c[i])
	listeazaLocale(f)
	return True


def scrieTitlu(f, text, limbi=None, wd=None, gata=None):
	"""Titlul scris de om: identificarea din nou cu el (anul din EIT ramane)."""
	text = (text or u"").strip()[:120]
	if not text:
		return False
	with f.lacat:
		f.text_om = text
		f.ales = None
	return identificaPeFir(f, limbi, wd, gata)


# ------------------------------------------------------------------ memoria pe canal (intoarcerea pe canal)
# Ce trebuie ca subtitrarea sa revina pe un serviciu nou (al carui ceas porneste de la 0) se tine minte pe referinta
# serviciului, numai in RAM: fisierul, fps-ul de la sursa, viteza aleasa, emisiunea, lungimea filmului dupa replici si
# potrivirea. Potrivirea se noteaza la punere si dupa fiecare reglaj (Navigation nu anunta nimic inainte sa opreasca
# serviciul): pe canal, timpul real trecut din film (ceasul minus intarzierea) la o ora de ceas; la intoarcere filmul a
# mers mai departe cat a trecut de atunci, afara de pauza 'Reclamă' (atunci ceasul subtitrarii sta si revine oprit).
# Pe o inregistrare ceasul e pozitia in fisier, deci intarzierea notata ramane buna.

MAX_MEMORIE = 8             # cate servicii se tin minte; pleaca cel notat cel mai demult
_MEMORIE = {}


def lungimeReplici(replici):
	"""Sfarsitul ultimei replici (ms, in timpul fisierului): pana acolo tine filmul dupa subtitrare; 0 fara replici."""
	try:
		return max(int(r[1]) for r in replici) if replici else 0
	except (TypeError, ValueError, IndexError):
		return 0


def noteaza(memorie, cheie, date, ceas_ms, intarziere_ms, factor, pauza, acum):
	"""Tine minte subtitrarea serviciului `cheie` (referinta ca text). date: {"fel", "cale", "fps", "viteza", "inceput",
	"durata", "lungime_ms", "ales", "text_om"}; o emisiune necunoscuta acum (ghidul inca necitit dupa intoarcere) nu o
	sterge pe cea notata inainte. -> intrarea, sau None fara ceas."""
	if not cheie or ceas_ms is None or int(ceas_ms) < 0:
		return None
	intrare = dict(date)
	vechi = memorie.get(cheie)
	if vechi is not None and not intrare.get("inceput") and vechi.get("cale") == intrare.get("cale"):
		intrare["inceput"], intrare["durata"] = vechi.get("inceput") or 0, vechi.get("durata") or 0
	intrare.update({"pozitie_ms": int(ceas_ms) - int(intarziere_ms), "intarziere_ms": int(intarziere_ms),
		"factor": float(factor or 1.0), "pauza": bool(pauza), "timp": float(acum)})
	memorie[cheie] = intrare
	while len(memorie) > MAX_MEMORIE:
		del memorie[min(memorie, key=lambda k: memorie[k]["timp"])]
	return intrare


def trecutMs(intrare, acum):
	"""Timpul real trecut din film acum (ms, pe ceasul serviciului), dupa potrivirea notata."""
	trecut = int(intrare["pozitie_ms"])
	if not intrare.get("pauza"):
		trecut += int((acum - intrare["timp"]) * 1000)
	return trecut


def deRefacut(memorie, cheie, inceput_acum, acum):
	"""Intrarea de pus la loc pe serviciul `cheie`, sau None (si intrarea se uita cand nu mai tine de ce merge). Pe o
	inregistrare: mereu. Pe un canal: aceeasi emisiune dupa ghid (inceputul ei, cand il stiu amandoua); fara ghid de o
	parte, cat timp filmul nu s-a terminat dupa subtitrare (sfarsitul ultimei replici, la viteza aleasa)."""
	intrare = memorie.get(cheie)
	if intrare is None:
		return None
	if intrare.get("fel") == "inregistrare":
		return intrare
	inceput = intrare.get("inceput") or 0
	if inceput and inceput_acum:
		bun = int(inceput_acum) == int(inceput)
	else:
		lungime = intrare.get("lungime_ms") or 0
		bun = bool(lungime) and trecutMs(intrare, acum) <= lungime * (intrare.get("factor") or 1.0)
	if not bun:
		memorie.pop(cheie, None)
		return None
	return intrare


def intarziereRefacuta(intrare, ceas_ms, acum):
	"""Intarzierea pe serviciul nou: pe canal ceasul de acum minus timpul real trecut din film; pe inregistrare cea
	notata (ceasul e pozitia in fisier)."""
	if intrare.get("fel") == "inregistrare":
		return int(intrare["intarziere_ms"])
	return int(ceas_ms) - trecutMs(intrare, acum)


def uita(cheie=None, memorie=None):
	"""Uita subtitrarea tinuta minte a serviciului `cheie` (a tuturor, cu cheie None)."""
	memorie = _MEMORIE if memorie is None else memorie
	if cheie is None:
		memorie.clear()
	else:
		memorie.pop(cheie, None)


# ================================================================== legatura cu enigma2 (importuri tarzii)

_FILM = [None]
_CEAS = [None]
_COADA = []
_REIA = [None]              # serviciul (getPtrString) pentru care s-a hotarat deja punerea la loc
MESAJ_REVENIRE_S = 5
TXT_REVENITA = N_("Subtitrarea de pe internet a revenit, potrivită ca înainte.")
TXT_REVENITA_OPRITA = N_("Subtitrarea de pe internet a revenit, cu ceasul oprit (Reclamă). Pornește-l când reîncepe filmul.")


def _nav():
	try:
		import NavigationInstance
		return NavigationInstance.instance
	except Exception:
		return None


def _ptr(service):
	try:
		return service.getPtrString()
	except Exception:
		return u"%s" % id(service)


def _serviciu():
	nav = _nav()
	if nav is None:
		return None, None
	try:
		return nav.getCurrentService(), nav.getCurrentlyPlayingServiceReference()
	except Exception:
		return None, None


def felServiciu(service, ref):
	"""("canal" | "inregistrare", calea inregistrarii) pentru un serviciu DVB cu imagine, altfel (None, "")."""
	if service is None or ref is None:
		return None, u""
	try:
		cale = ref.getPath() or u""
	except Exception:
		cale = u""
	try:
		from Components import HdsSubtitrariFilm as SF
		if SF.esteFilm(cale):
			return None, u""
	except ImportError:
		pass
	try:
		from enigma import iServiceInformation
		info = service.info()
		if info is not None and info.getInfo(iServiceInformation.sVideoPID) == -1:
			return None, u""       # radio: fara film
	except Exception:
		pass
	if not cale or cale.startswith("http"):
		return "canal", u""
	if cale.startswith("/") and cale.lower().endswith(".ts"):
		return "inregistrare", cale
	return None, u""


def peServiciuDvb():
	"""Merge acum un canal TV cu imagine sau o inregistrare .ts (tasta SUB arata atunci cautarea pe internet)."""
	service, ref = _serviciu()
	return felServiciu(service, ref)[0] is not None


def _eveniment(service, ref, fel, cale):
	ev = None
	creata = 0
	canal = u""
	try:
		if fel == "inregistrare":
			from enigma import eServiceCenter, iServiceInformation
			info = eServiceCenter.getInstance().info(ref)
			ev = info and info.getEvent(ref)
			creata = info.getInfo(ref, iServiceInformation.sTimeCreate) if info else 0
			canal = (info.getName(ref) if info else u"") or u""
		else:
			info = service.info()
			ev = info and info.getEvent(0)
			canal = (info.getName() if info else u"") or u""
	except Exception as e:
		print("[HdsSubtitrariTv] emisiunea: %s" % e.__class__.__name__)
	d = {"titlu": u"", "scurt": u"", "extins": u"", "inceput": 0, "durata": 0, "creata": creata or 0, "canal": canal}
	if ev is not None:
		try:
			d.update({"titlu": ev.getEventName() or u"", "scurt": ev.getShortDescription() or u"",
				"extins": ev.getExtendedDescription() or u"", "inceput": ev.getBeginTime() or 0, "durata": ev.getDuration() or 0})
		except Exception:
			pass
	if not d["titlu"] and fel == "inregistrare":
		d["titlu"] = d["canal"] or os.path.splitext(os.path.basename(cale))[0]
	return d


def filmulDeAcum(session=None, creeaza=True):
	"""FilmTv pentru serviciul DVB de acum (canal cu imagine sau inregistrare .ts), sau None. Acelasi obiect cat
	merge acelasi serviciu si aceeasi emisiune (pe canal, o emisiune noua = alt film)."""
	service, ref = _serviciu()
	fel, cale = felServiciu(service, ref)
	if fel is None:
		return None
	try:
		text_ref = ref.toString()
	except Exception:
		text_ref = u""
	ptr = _ptr(service)
	f = _FILM[0]
	if f is not None and f.ref == text_ref and f.ptr == ptr:
		if fel == "canal" and f.subtitrare is None and not f.lucreaza:
			ev = _eveniment(service, ref, fel, cale)
			if ev.get("inceput") and ev.get("inceput") != f.eveniment.get("inceput"):
				f = None
		if f is not None:
			return f
	if not creeaza:
		return None
	f = FilmTv(text_ref, ptr, fel, cale, _eveniment(service, ref, fel, cale))
	_FILM[0] = f
	return f


def _sub(f=None):
	"""iSubtitleOutput al serviciului de acum, numai daca e serviciul filmului f."""
	service, ref = _serviciu()
	if service is None or (f is not None and _ptr(service) != f.ptr):
		return None
	try:
		return service.subtitle()
	except Exception:
		return None


def _fpsCanal():
	service, ref = _serviciu()
	try:
		from enigma import iServiceInformation
		info = service and service.info()
		return info.getInfo(iServiceInformation.sFrameRate) if info else -1
	except Exception:
		return -1


def _infobar(session=None):
	try:
		from Components import HdsPisteLimbi as L
		return L, L.infobarActiv(session)
	except Exception:
		return None, None


def tuplu(sub):
	"""Tuplul subtitrarii noastre din lista serviciului, sau None."""
	try:
		for t in sub.getSubtitleList() or []:
			if len(t) > 1 and int(t[0]) == 2 and int(t[1]) == INDEX:
				return tuple(t)
	except Exception:
		pass
	return None


def activ(session=None, f=None):
	"""Subtitrarea de pe internet merge acum pe serviciul DVB (pornita in fereastra subtitrarilor)."""
	f = f or filmulDeAcum(session, creeaza=False)
	if f is None or f.subtitrare is None:
		return False
	sub = _sub(f)
	if sub is None:
		return False
	L, ib = _infobar(session)
	if L is None:
		return False
	pornita = L.subtitrare_pornita(ib)
	return bool(pornita) and len(pornita) > 1 and int(pornita[0]) == 2 and int(pornita[1]) == INDEX


def _porneste(functie, ms=50):
	from enigma import eTimer
	if _CEAS[0] is None:
		_CEAS[0] = eTimer()
		_CEAS[0].callback.append(_bate)
	_COADA.append(functie)
	_CEAS[0].start(ms, True)


def _bate():
	while _COADA:
		functie = _COADA.pop(0)
		try:
			functie()
		except Exception as e:
			print("[HdsSubtitrariTv] %s" % e)


def citesteFisier(cale):
	"""Pe fir: fisierul de subtitrare -> (intrarea cercetata, replicile pentru serviciu) sau (None, mesaj)."""
	from Components import HdsSubtitrariFilm as SF
	date = SF.citesteOcteti(cale)
	if not date:
		return None, _t("Fișierul de subtitrare nu se poate citi.")
	n = os.path.basename(cale)
	intrare = {"cale": cale, "nume": n, "ext": os.path.splitext(n)[1].lower(), "rest": os.path.splitext(n)[0],
		"marime": len(date)}
	intrari = SF.cercetaFisier(intrare, date[:SF.OCTETI_PROBA], SF.CODARE_AUTO, SF._setari()[0])
	intrari = [e for e in intrari if e.get("tip") in SF.TIPURI_TEXT]
	if not intrari:
		return None, _t("Fișierul acesta nu este o subtitrare text.")
	e = intrari[0]
	implicita, virgula = SF._setari()[0], SF._setari()[1]
	fps = SF.fpsAles(None, e.get("fps_fisier"), 25.0) if e.get("tip") == SF.TIP_MICRODVD else None
	replici, folosita, rea = SF.citesteIntreg(e, date, SF.CODARE_AUTO, implicita, virgula, fps)
	if not replici:
		return None, _t("Fișierul nu are nicio replică.")
	e["replici"] = len(replici)
	return e, replici


def incarca(session, cale, fps=None, gata=None, refacere=None):
	"""Pe firul enigma2: subtitrarea `cale` intra in serviciul DVB de acum (citita pe un fir, pusa pe firul enigma2) si
	porneste, cu viteza automata si pozitia de pornire. -> (True, mesaj) cand citirea a pornit, (False, mesaj) altfel.
	`gata(reusit, mesaj)` pe firul enigma2, dupa punere. `refacere`: intrarea din memorie (reia), cu viteza, potrivirea
	si pauza de dinainte in locul celor de pornire."""
	f = filmulDeAcum(session)
	if f is None:
		return False, _t("Acum nu merge un canal TV sau o înregistrare.")
	# pana la punere nu e nicio subtitrare "pusa" (ecranul cautarii asteapta pe cea noua, nu pe cea veche)
	f.subtitrare = None
	f.mesaj = _t("Se încarcă subtitrarea...")

	def lucru():
		try:
			e, replici = citesteFisier(cale)
		except Exception as ex:
			e, replici = None, _t("Fișierul nu s-a putut citi: %s") % ex.__class__.__name__
		_porneste(lambda: _pune(session, f, cale, fps, e, replici, gata, refacere))
	fir = threading.Thread(target=lucru, name="HdsSubtitrariTv")
	fir.daemon = True
	fir.start()
	return True, _t("Se încarcă subtitrarea...")


def _pune(session, f, cale, fps, e, replici, gata=None, refacere=None):
	"""Pe firul enigma2: fisierul citit intra in serviciu si porneste (cu `refacere`: ca inainte de schimbarea
	canalului)."""
	def gata_(reusit, mesaj):
		f.mesaj = mesaj
		print("[HdsSubtitrariTv] %s" % mesaj)
		if gata is not None:
			gata(reusit, mesaj)
	if e is None:
		return gata_(False, replici)
	sub = _sub(f)
	if sub is None:
		return gata_(False, _t("Canalul s-a schimbat; subtitrarea nu s-a pus."))
	from Components import HdsSubtitrariFilm as SF
	flags = (SF.FLAG_FORCED if e.get("forced") else 0) | (SF.FLAG_SURZI if e.get("surzi") else 0)
	if sub.setExternalSubtitles([(e["nume"], e.get("limba") or u"und", e["tip"], flags)]) < 0 or \
			sub.setExternalSubtitleCues(0, replici) < 0:
		return gata_(False, _t("Serviciul nu primește subtitrarea."))
	fps_canal = _fpsCanal()
	if refacere is not None and refacere.get("viteza") in VITEZE:
		f.viteza = refacere["viteza"]
	sub.setSubtitleSpeed(factorViteza(f.viteza, fps, fps_canal))
	ceas = sub.getSubtitleClock()
	ev = f.eveniment
	if refacere is not None:
		sub.setSubtitleDelay(intarziereRefacuta(refacere, ceas, time.time()))
	else:
		sub.setSubtitleDelay(intarziereInitiala(f.fel, ceas, time.time(), ev.get("inceput"), ev.get("durata"), ev.get("creata")))
	t = tuplu(sub)
	L, ib = _infobar(session)
	if L is not None and ib is not None:
		pornita = L.subtitrare_pornita(ib)
		if pornita and len(pornita) > 1 and int(pornita[0]) == 2 and int(pornita[1]) == INDEX:
			# a doua subtitrare pe acelasi canal: are acelasi tuplu (2, 100, ...), deci fara oprire alegerea n-ar porni-o
			# din nou, iar serviciul a lasat-o pe cea veche (alt nume) si nu arata nimic
			L.alege_subtitrare(ib, None, manual=False)
	if t is None or L is None or ib is None or not L.alege_subtitrare(ib, t, manual=False):
		return gata_(False, _t("Subtitrarea nu s-a putut porni."))
	f.subtitrare = {"cale": cale, "nume": e["nume"], "fps": fps, "limba": e.get("limba") or u"und",
		"replici": e.get("replici") or len(replici), "lungime_ms": lungimeReplici(replici)}
	if refacere is not None:
		oprita = bool(refacere.get("pauza")) and sub.setSubtitleClockPaused(1) == 0
		_noteazaAcum(f, sub)
		return gata_(True, _t(TXT_REVENITA_OPRITA) if oprita else _t(TXT_REVENITA))
	_noteazaAcum(f, sub)
	return gata_(True, _t("Subtitrarea a pornit (%d replici). Potrivește-o cu replica următoare sau dinainte.") %
		f.subtitrare["replici"])


def _noteazaAcum(f, sub):
	"""Potrivirea de acum a subtitrarii filmului f, tinuta minte pe serviciu (pentru intoarcerea pe el)."""
	if f is None or sub is None or f.subtitrare is None:
		return None
	try:
		ceas = sub.getSubtitleClock()
		intarziere = sub.getSubtitleDelay()
		factor = sub.getSubtitleSpeed() or 1.0
		pauza = sub.getSubtitleClockPaused()
	except Exception as ex:
		print("[HdsSubtitrariTv] potrivirea nu se poate nota: %s" % ex.__class__.__name__)
		return None
	with f.lacat:
		ales = dict(f.ales) if f.ales else None
		text_om = f.text_om
	date = {"fel": f.fel, "cale": f.subtitrare["cale"], "fps": f.subtitrare.get("fps"), "viteza": f.viteza,
		"inceput": f.eveniment.get("inceput") or 0, "durata": f.eveniment.get("durata") or 0,
		"lungime_ms": f.subtitrare.get("lungime_ms") or 0, "ales": ales, "text_om": text_om}
	return noteaza(_MEMORIE, f.ref, date, ceas, intarziere, factor, pauza, time.time())


def _anunta(text):
	"""Un mesaj scurt pe televizor, care pleaca singur."""
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text=text, type=MessageBox.TYPE_INFO, timeout=MESAJ_REVENIRE_S, id="HdsSubtitrareRevenita")
	except Exception as ex:
		print("[HdsSubtitrariTv] mesajul: %s" % ex.__class__.__name__)


def reia(session=None):
	"""Pe firul enigma2, la un serviciu nou (Components/HdsPisteLimbi.aplicaSubtitrare): subtitrarea de pe internet
	tinuta minte pentru acest canal (aceeasi emisiune) sau pentru aceasta inregistrare revine singura, cu viteza si
	potrivirea de dinainte. O singura data pe serviciu. -> True daca a pornit punerea."""
	if not _MEMORIE:
		return False
	service, ref = _serviciu()
	fel, cale = felServiciu(service, ref)
	if fel is None:
		return False
	ptr = _ptr(service)
	if _REIA[0] == ptr:
		return False
	_REIA[0] = ptr
	try:
		cheie = ref.toString()
	except Exception:
		return False
	if cheie not in _MEMORIE:
		return False
	ev = _eveniment(service, ref, fel, cale)
	intrare = deRefacut(_MEMORIE, cheie, ev.get("inceput") if fel == "canal" else 0, time.time())
	if intrare is None:
		print("[HdsSubtitrariTv] subtitrarea tinuta minte nu mai tine de emisiunea de acum")
		return False
	f = filmulDeAcum(session)
	if f is None or f.subtitrare is not None:
		return False
	with f.lacat:
		f.ales = dict(intrare["ales"]) if intrare.get("ales") else None
		f.text_om = intrare.get("text_om")
	if fel != "canal":
		dupa = "inregistrare"
	elif ev.get("inceput") and intrare.get("inceput"):
		dupa = "ghid"
	else:
		dupa = "replici"
	print("[HdsSubtitrariTv] subtitrarea de dinainte revine (%s): %s" % (dupa, os.path.basename(intrare["cale"])))

	def gata(reusit, mesaj):
		if reusit:
			_anunta(mesaj)
		else:
			uita(cheie)
	reusit, mesaj = incarca(session, intrare["cale"], intrare.get("fps"), gata, refacere=intrare)
	return reusit


def uitaRef(ref):
	"""Omul a ales alta subtitrare (sau niciuna) pe serviciul `ref`: cea de pe internet nu mai revine la intoarcere."""
	try:
		uita(ref.toString())
	except Exception:
		pass


# ------------------------------------------------------------------ reglajul (bara de potrivire si web)

def _subActiv(session=None):
	f = filmulDeAcum(session, creeaza=False)
	if f is None or f.subtitrare is None:
		return None, None
	return f, _sub(f)


def salt(session, directie):
	"""Replica urmatoare (1) sau dinainte (-1) incepe acum. -> True/False"""
	f, sub = _subActiv(session)
	if not sub or sub.jumpSubtitle(1 if directie > 0 else -1) != 0:
		return False
	_noteazaAcum(f, sub)
	return True


def muta(session, ms):
	"""+ms: subtitrarea mai tarziu; -ms: mai devreme."""
	f, sub = _subActiv(session)
	if sub is None or sub.setSubtitleDelay(int(sub.getSubtitleDelay()) + int(ms)) != 0:
		return False
	_noteazaAcum(f, sub)
	return True


def reclama(session, pornita=None):
	"""Tasta "Reclamă": ceasul subtitrarii sta (si nimic pe ecran) sau merge din acelasi loc. -> starea noua sau None."""
	f, sub = _subActiv(session)
	if sub is None:
		return None
	nou = (not sub.getSubtitleClockPaused()) if pornita is None else bool(pornita)
	if sub.setSubtitleClockPaused(1 if nou else 0) < 0:
		return None
	_noteazaAcum(f, sub)
	return nou


def acumIncepe(session):
	"""Filmul incepe acum (inceputul fisierului = acum)."""
	f, sub = _subActiv(session)
	if sub is None:
		return False
	ceas = sub.getSubtitleClock()
	if ceas < 0 or sub.setSubtitleDelay(ceas) != 0:
		return False
	_noteazaAcum(f, sub)
	return True


def alegeViteza(session, cod):
	if cod not in VITEZE:
		return False
	f, sub = _subActiv(session)
	if f is None or sub is None:
		return False
	f.viteza = cod
	if sub.setSubtitleSpeed(factorViteza(cod, f.subtitrare.get("fps"), _fpsCanal())) != 0:
		return False
	_noteazaAcum(f, sub)
	return True


def opreste(session):
	"""Subtitrarea de pe internet se opreste (fisierul ramane in serviciu: din tasta SUB se poate porni din nou) si nu
	mai revine la intoarcerea pe canal."""
	f = filmulDeAcum(session, creeaza=False)
	if f is not None:
		uita(f.ref)
	L, ib = _infobar(session)
	return bool(L is not None and ib is not None and L.alege_subtitrare(ib, None, manual=False))


def stare(session=None):
	"""Pentru ecrane si web: filmul, identificarea, fisierele locale, subtitrarea pusa si potrivirea."""
	f = filmulDeAcum(session)
	if f is None:
		return {"tv": False}
	idf = f.stareIdentificare()
	with f.lacat:
		locale = [dict(x) for x in f.locale]
	rez = {"tv": True, "fel": f.fel, "canal": f.eveniment.get("canal") or u"", "emisiune": f.eveniment.get("titlu") or u"",
		"info": dict(f.info), "identificare": idf, "film": f.pentruCautare(), "locale": locale,
		"subtitrare": dict(f.subtitrare) if f.subtitrare else None, "activ": False, "mesaj": f.mesaj}
	sub = _sub(f) if f.subtitrare else None
	if sub is not None and f.subtitrare:
		ceas = sub.getSubtitleClock()
		intarziere = sub.getSubtitleDelay()
		viteza = sub.getSubtitleSpeed() or 1.0
		pozitie = int(round((ceas - intarziere) / viteza)) if ceas >= 0 else 0
		fps_canal = _fpsCanal()
		rez.update({"activ": activ(session, f), "pozitie_ms": pozitie, "pozitie_text": textPozitie(pozitie),
			"intarziere_ms": intarziere, "viteza": round(viteza, 5), "viteza_cod": f.viteza,
			"viteza_text": textViteza(f.viteza, f.subtitrare.get("fps"), fps_canal),
			"vitezele": [[c, textVitezaCod(c, f.subtitrare.get("fps"), fps_canal)] for c in VITEZE],
			"reclama": bool(sub.getSubtitleClockPaused()), "replica": sub.getSubtitleCueText(0) or u"",
			"urmatoarea": sub.getSubtitleCueText(1) or u""})
	return rez


def textVitezaCod(cod, fps_sursa, fps_canal):
	"""Textul unei alegeri de viteza: "Automat (de la 23,976 la 25 cadre/s)", "de la 24 la 25 cadre/s", "Fără schimbare"."""
	if cod == "auto":
		return _t("Automat (%s)") % textViteza(cod, fps_sursa, fps_canal)
	return textViteza(cod, fps_sursa, fps_canal)
