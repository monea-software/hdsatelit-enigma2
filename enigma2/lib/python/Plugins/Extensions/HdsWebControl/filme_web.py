# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# filme_web.py: „Filmul de acum” in interfata web (HdsWebControl), perechea playerului de filme si a listei de filme de
# pe televizor.
#
# Pe televizor: lista de filme (Screens/MovieSelection.py: filmele si inregistrarile unui dosar, locul unde s-a ramas),
# playerul de filme (MoviePlayer, Screens/InfoBar.py) cu InfoBarSeek (pauza, salturile cu cifrele, derularea cu >> si
# <<), intrebarea de reluare (InfoBarCueSheetSupport) si mesajul pentru un film care nu se poate reda (InfoBarFilmRefuz,
# textele in Components/HdsFilmRedare.py); setarile „La pornirea / oprirea / sfârșitul unui film”
# (config.usage.on_movie_start, on_movie_stop, on_movie_eof, in setup.xml la Personalizare).
# Aici: ce film merge (un fisier; un flux numai cand l-a pornit playerul de filme, nu un canal de pe internet din bara
# principala), pozitia si lungimea, starea (redare, pauza, derulare, oprit dupa un refuz), locul tinut minte in
# <film>.cuts, mesajul de refuz, butoanele (pauza si redare, salturi, derulare, „Sari la”), cele trei setari si lista
# filmelor din dosarul listei de pe televizor, cu locul unde s-a ramas si pornirea unui film („Reia” sau „De la
# început”, fara intrebare pe televizor).
# Comenzile trec prin bara filmului de pe televizor (InfoBarSeek), ca televizorul sa arate aceeasi stare (">> 8x",
# pauza); fara ea (un film pornit fara player), direct prin serviciu.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/filme                                            filmul de acum si setarile
#   POST /api/filme-comanda?fa=pauza|redare|inainte|inapoi     pauza, redare, derulare (ca >> si << pe telecomanda)
#   POST /api/filme-comanda?fa=salt&secunde=-60..               salt inainte sau inapoi
#   POST /api/filme-comanda?fa=la&secunde=N                     sari la o pozitie
#   POST /api/filme-seteaza?pornire=ask&oprire=..&sfarsit=..    setarile (oricare dintre ele)
#   GET  /api/filme-lista                                      filmele din dosarul listei de filme
#   POST /api/filme-porneste?cale=..&de_la=loc|inceput          porneste pe televizor un film de sub locurile filmelor
#                                                              (si din subdosare: PORNIREA, mai jos)
#   GET  /filme                                                pagina
#
# DECODAREA: o inregistrare "Decodează mai târziu" inca nedecodata (Components/HdsDecodare.py, numai cu programul de
# decodare pe receptor) are in lista "semn_decodare" (acelasi semn ca lista de pe televizor), iar pornirea ei raspunde cu
# mesajul de pe televizor in loc sa dea ecran negru.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; comenzile sunt scurte (servicemp3 face salturile, pauza si
# redarea pe firul filmului, lib/service/servicemp3.cpp). Lista filmelor citeste discul (dosarul, marimile, fisierele
# .cuts si .meta) pe un fir separat; rezultatul se preda firului enigma2 printr-un eTimer, iar raspunsul pleaca la
# sfarsit (NOT_DONE_YET). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau sesiunea, bara,
# setarile si modulul de texte ale lor.

import os

TIP_FILM = 4097
# o inregistrare (.ts) merge ca serviciu DVB cu cale (1:0:0:0:0:0:0:0:0:0:<cale>, _referinta); un canal viu are tot
# tipul 1, dar fara cale
TIP_DVB = 1
SALT_MAX_S = 6 * 3600
MAX_TEXT = 40
MAX_CALE = 1024
MAX_FILME = 500
# fisiere numarate intr-un dosar (numai data si marimea) inainte de alegerea celor mai noi MAX_FILME: un dosar urias nu
# tine firul listei la nesfarsit
MAX_CANDIDATI = 10000
TERMEN_LISTA_S = 20
# fisierele listei de filme de pe televizor care au imagine: filmele servicemp3 (felurileFilmelor din servicemp3.cpp) si
# inregistrarile (.ts); muzica din acelasi dosar nu e aici
EXTENSII_FILME = ("mkv", "webm", "mp4", "m4v", "mov", "3gp", "avi", "divx", "mpg", "mpeg", "vob", "dat", "flv", "ogv")
EXTENSIE_INREGISTRARE = "ts"


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# (numele in cerere, setarea din config.usage, eticheta: aceeasi ca pe televizor, in setup.xml)
SETARI = (
	("pornire", "on_movie_start", N_("La pornirea unui film")),
	("oprire", "on_movie_stop", N_("La oprirea unui film")),
	("sfarsit", "on_movie_eof", N_("La sfârșitul unui film")),
)
# ce raspuns la intrebarea de reluare aduce pornirea din pagina (InfoBarCueSheetSupport.hdsPornireFilm)
PORNIRI = {"loc": "resume", "inceput": "beginning"}

TXT_FARA_FILM = N_("Niciun film nu merge acum.")
TXT_FARA_DERULARE = N_("Derularea rapidă nu merge la acest film. Poți sări înainte sau înapoi.")
TXT_COMANDA = N_("Comanda nu există.")
TXT_SECUNDE = N_("Numărul de secunde nu este bun.")
TXT_FACUT = N_("Gata.")
TXT_NU_MERGE = N_("Receptorul nu a putut face asta acum.")
TXT_ALEGERE = N_("Alegerea „%s” nu există pentru „%s”.")
TXT_NIMIC = N_("Nu s-a trimis nicio setare.")
TXT_SALVAT = N_("Salvat.")
TXT_REDARE = N_("Redare")
TXT_PAUZA = N_("Pauză")
TXT_SFARSIT = N_("Sfârșit")
TXT_INAINTE = N_("Derulare înainte %s")
TXT_INAPOI = N_("Derulare înapoi %s")
TXT_OPRIT = N_("Oprit: filmul nu se poate reda.")
TXT_DOSAR = N_("Dosarul filmelor nu se poate citi.")
TXT_LISTA_INCETA = N_("Discul nu a răspuns la timp. Încearcă încă o dată.")
TXT_FILM_LIPSA = N_("Filmul nu este într-un dosar al filmelor de pe receptor.")
TXT_ALT_ECRAN = N_("Pe televizor este deschis alt ecran. Închide-l și încearcă încă o dată.")
TXT_PORNESTE = N_("Filmul pornește pe televizor.")


def _config(cfg=None):
	if cfg is not None:
		return cfg
	from Components.config import config
	return config


def _f(F=None):
	if F is not None:
		return F
	from Components import HdsFilmRedare
	return HdsFilmRedare


def baraFilmului():
	"""Bara de pe televizor care are serviciul (varful stivei ServiceEventTracker), daca stie derularea (InfoBarSeek)."""
	try:
		from Components.ServiceEventTracker import ServiceEventTracker
		stiva = ServiceEventTracker.InfoBarStack
		if stiva:
			bara = stiva[-1]
			if hasattr(bara, "setSeekState") and hasattr(bara, "doSeekRelative") and hasattr(bara, "seekstate"):
				return bara
	except Exception as e:
		print("[HdsWebControl] filme: bara filmului: %s" % e)
	return None


def _pts(rezultat):
	"""(eroare, pts) de la getPlayPosition / getLength -> pts sau None."""
	try:
		if rezultat and not rezultat[0] and rezultat[1] >= 0:
			return int(rezultat[1])
	except (TypeError, IndexError):
		pass
	return None


def textStare(semn):
	"""Semnul barei (">", "||", "END", ">> 8x", "<< 4x") pe intelesul oricui."""
	semn = (semn or "").strip()
	if semn in ("", ">"):
		return _t(TXT_REDARE)
	if semn == "||":
		return _t(TXT_PAUZA)
	if semn == "END":
		return _t(TXT_SFARSIT)
	if semn.startswith(">>"):
		return _t(TXT_INAINTE) % semn[2:].strip()
	if semn.startswith("<<"):
		return _t(TXT_INAPOI) % semn[2:].strip()
	return semn


def adresaFaraAcces(cale):
	"""Adresa unui flux fara utilizator, parola si parametri („http://u:p@gazda:8080/f.mkv?t=1” ->
	„http://gazda:8080/f.mkv”): abonamentele de pe internet tin adesea datele de acces in adresa."""
	schema, sep, rest = (cale or "").partition("://")
	if not sep:
		return cale or ""
	rest = rest.split("?", 1)[0].split("#", 1)[0]
	gazda, bara, drum = rest.partition("/")
	gazda = gazda.rsplit("@", 1)[-1]
	return schema + "://" + gazda + bara + drum


def _filmul(sesiune, bara=None, F=None):
	"""(referinta, serviciul) filmului care merge, sau (None, None). Un flux de pe internet conteaza numai cand l-a
	pornit playerul de filme (bara are leavePlayer): un canal de pe internet din bara principala nu e un film."""
	if sesiune is None:
		return None, None
	try:
		ref = sesiune.nav.getCurrentlyPlayingServiceReference()
		serviciu = sesiune.nav.getCurrentService()
	except Exception:
		return None, None
	if ref is None or serviciu is None:
		return None, None
	tip = getattr(ref, "type", None)
	if tip != TIP_FILM and not (tip == TIP_DVB and (ref.getPath() or "")):
		return None, None
	if F is not None and F.esteFlux(ref.getPath() or "") and not hasattr(bara, "leavePlayer"):
		return None, None
	return ref, serviciu


def _locTinutMinte(serviciu):
	try:
		cue = serviciu.cueSheet()
		lista = cue.getCutList() if cue is not None else []
	except Exception:
		return None
	ultima = None
	for pts, fel in lista or []:
		if fel == 3:
			ultima = int(pts)
	return ultima


def _descriereFilm(sesiune, bara, F):
	ref, serviciu = _filmul(sesiune, bara, F)
	if ref is None:
		return None
	cale = ref.getPath() or ""
	flux = F.esteFlux(cale)
	info = serviciu.info()
	seek = serviciu.seek()
	nume = ""
	try:
		nume = info.getName() if info is not None else ""
	except Exception:
		nume = ""
	if not nume:
		nume = cale.rsplit("/", 1)[-1]
	if flux:
		# numele unui flux fara datele de acces si fara parametrii adresei (adesea o cheie de abonament)
		nume = adresaFaraAcces(nume) if "://" in nume else nume.split("?", 1)[0].split("#", 1)[0].rsplit("@", 1)[-1]
	pozitie = lungime = None
	derulare = False
	if seek is not None:
		pozitie = _pts(seek.getPlayPosition())
		lungime = _pts(seek.getLength())
		try:
			derulare = bool(seek.isCurrentlySeekable() & 2)
		except Exception:
			derulare = False
	video = sunet = ""
	verdict = None
	if info is not None:
		try:
			from enigma import iServiceInformation
			video = info.getInfoString(iServiceInformation.sTagVideoCodec) or ""
			sunet = info.getInfoString(iServiceInformation.sTagAudioCodec) or ""
		except Exception:
			pass
		v = F.verdictDinInfo(info, cale)
		verdict = v.dict() if v is not None else None
	oprit = bool(verdict and verdict.get("refuza"))
	ultima = _locTinutMinte(serviciu)
	semn = bara.seekstate[3] if bara is not None and getattr(bara, "seekstate", None) else ">"
	return {
		"nume": nume,
		"cale": adresaFaraAcces(cale) if flux else cale,
		"flux": flux,
		"pozitie": pozitie // 90000 if pozitie is not None else None,
		"lungime": lungime // 90000 if lungime is not None else None,
		"text_pozitie": F.textTimp(pozitie, lungime),
		"text_lungime": F.textTimp(lungime),
		"stare": _t(TXT_OPRIT) if oprit else textStare(semn),
		"pauza": semn in ("||", "END"),
		"oprit": oprit,
		"derulare": derulare and not oprit,
		"imagine": video,
		"sunet": sunet,
		"loc": ultima // 90000 if ultima is not None else None,
		"text_loc": F.textTimp(ultima, lungime) if ultima is not None else "",
		"refuz": verdict,
	}


def _alegeri(element):
	rez = []
	for x in element.choices.choices:
		if isinstance(x, tuple):
			rez.append([str(x[0]), _t(x[1]) if x[1] else str(x[0])])
		else:
			rez.append([str(x), str(x)])
	return rez


def stare(sesiune=None, bara=None, cfg=None, F=None):
	"""Pentru GET /api/filme."""
	F = _f(F)
	c = _config(cfg)
	if bara is None:
		bara = baraFilmului()
	setari = {}
	for nume, cheie, eticheta in SETARI:
		element = getattr(c.usage, cheie)
		setari[nume] = {"eticheta": _t(eticheta), "valoare": str(element.value), "alegeri": _alegeri(element)}
	return {
		"result": True,
		"film": _descriereFilm(sesiune, bara, F),
		"ordine": [x[0] for x in SETARI],
		"setari": setari,
	}


def _secunde(text, minim, maxim):
	try:
		n = int(str(text).strip())
	except (TypeError, ValueError):
		return None
	if n < minim or n > maxim:
		return None
	return n


def comanda(argumente, sesiune=None, bara=None, cfg=None, F=None):
	"""POST /api/filme-comanda: ca tastele playerului de pe televizor."""
	F = _f(F)
	if bara is None:
		bara = baraFilmului()

	def _raspuns(bun, text):
		rez = stare(sesiune, bara, cfg, F)
		rez.update({"result": bun, "message": _t(text)})
		return rez

	ref, serviciu = _filmul(sesiune, bara, F)
	if ref is None:
		return _raspuns(False, TXT_FARA_FILM)
	fa = argumente.get("fa", "")
	seek = serviciu.seek()
	pauza = serviciu.pause()
	try:
		if fa == "pauza":
			if bara is not None:
				if bara.seekstate != bara.SEEK_STATE_PAUSE:
					bara.pauseService()
			elif pauza is not None:
				pauza.pause()
		elif fa == "redare":
			if bara is not None:
				bara.unPauseService()
			elif pauza is not None:
				pauza.unpause()
		elif fa in ("salt", "la"):
			if seek is None:
				return _raspuns(False, TXT_NU_MERGE)
			if fa == "salt":
				s = _secunde(argumente.get("secunde"), -SALT_MAX_S, SALT_MAX_S)
				if not s:
					return _raspuns(False, TXT_SECUNDE)
				if bara is not None:
					bara.doSeekRelative(s * 90000)
				else:
					seek.seekRelative(1 if s > 0 else -1, abs(s) * 90000)
			else:
				lungime = _pts(seek.getLength())
				maxim = lungime // 90000 if lungime else SALT_MAX_S
				s = _secunde(argumente.get("secunde"), 0, maxim)
				if s is None:
					return _raspuns(False, TXT_SECUNDE)
				if bara is not None:
					bara.doSeek(s * 90000)
				else:
					seek.seekTo(s * 90000)
		elif fa in ("inainte", "inapoi"):
			if seek is None or not (seek.isCurrentlySeekable() & 2):
				return _raspuns(False, TXT_FARA_DERULARE)
			if bara is not None:
				if fa == "inainte":
					bara.seekFwd()
				else:
					bara.seekBack()
			elif pauza is not None:
				viteza = _config(cfg).seek.enter_forward.value if fa == "inainte" else _config(cfg).seek.enter_backward.value
				pauza.setFastForward(int(viteza) if fa == "inainte" else -int(viteza))
		else:
			return _raspuns(False, TXT_COMANDA)
	except Exception as e:
		print("[HdsWebControl] filme: comanda %s: %s" % (fa, e))
		return _raspuns(False, TXT_NU_MERGE)
	return _raspuns(True, TXT_FACUT)


def seteaza(argumente, sesiune=None, bara=None, cfg=None, F=None, configfile=None):
	"""POST /api/filme-seteaza: fiecare valoare trimisa trebuie sa fie printre alegeri, altfel nu se schimba nimic."""
	c = _config(cfg)
	noi = {}
	for nume, cheie, eticheta in SETARI:
		if nume not in argumente:
			continue
		element = getattr(c.usage, cheie)
		valoare = None
		for x in element.choices.choices:
			v = x[0] if isinstance(x, tuple) else x
			if str(v) == argumente[nume]:
				valoare = v
		if valoare is None:
			rez = stare(sesiune, bara, cfg, F)
			rez.update({"result": False, "message": _t(TXT_ALEGERE) % (argumente[nume][:MAX_TEXT], _t(eticheta))})
			return rez
		noi[cheie] = valoare
	if not noi:
		rez = stare(sesiune, bara, cfg, F)
		rez.update({"result": False, "message": _t(TXT_NIMIC)})
		return rez
	for cheie, valoare in noi.items():
		element = getattr(c.usage, cheie)
		element.value = valoare
		element.save()
	if configfile is None:
		from Components.config import configfile
	configfile.save()
	rez = stare(sesiune, bara, cfg, F)
	rez.update({"result": True, "message": _t(TXT_SALVAT)})
	return rez


# ------------------------------------------------------------------------------------------------ lista filmelor

def dosarFilme(cfg=None):
	"""Dosarul listei de filme de pe televizor (config.movielist.last_videodir, pus de Screens/MovieSelection.py la
	importul lui), altfel dosarul inregistrarilor."""
	c = _config(cfg)
	if cfg is None:
		try:
			import Screens.MovieSelection  # noqa: F401  (config.movielist exista numai dupa import)
		except Exception as e:
			print("[HdsWebControl] filme: lista de filme: %s" % e)
	try:
		dosar = c.movielist.last_videodir.value
	except (AttributeError, KeyError):
		dosar = ""
	if not dosar:
		try:
			dosar = c.usage.default_path.value
		except (AttributeError, KeyError):
			dosar = "/media/hdd/movie/"
	return dosar


def _extensie(nume):
	return nume.rsplit(".", 1)[-1].lower() if "." in nume else ""


def _afisat(text):
	"""Un nume de pe disc pentru pagina: enigma2 ruleaza cu locale-ul C, deci os.listdir da diacriticele ca octeti
	scapati (surrogateescape); octetii se citesc ca UTF-8."""
	try:
		return os.fsencode(text).decode("utf-8", "replace")
	except (UnicodeError, TypeError):
		return text


def _caleDisc(cale):
	"""Calea venita de la pagina (text UTF-8) ca nume de fisier pentru Python (invers lui _afisat)."""
	try:
		return os.fsdecode(cale.encode("utf-8", "surrogateescape"))
	except (UnicodeError, AttributeError):
		return cale


def _deschideObisnuit(cale):
	"""Fisierul de langa film (.cuts, .meta) deschis pentru citire numai daca e un fisier obisnuit; None pentru o
	legatura (ar putea arata in afara locului, de pilda spre un fisier cu parole), o teava sau un dispozitiv (citirea
	s-ar putea bloca si ar tine firul listei) si pentru orice eroare."""
	import stat
	try:
		if os.path.islink(cale):
			return None
		fd = os.open(cale, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
			| getattr(os, "O_BINARY", 0))
	except (OSError, ValueError):
		return None
	try:
		if stat.S_ISREG(os.fstat(fd).st_mode):
			return os.fdopen(fd, "rb")
	except OSError:
		pass
	os.close(fd)
	return None


def _locDinCuts(cale):
	"""Ultima pozitie (tipul 3) din <film>.cuts: perechi de 8 + 4 octeti big-endian, ca la inregistrari."""
	f = _deschideObisnuit(cale + ".cuts")
	if f is None:
		return None
	try:
		with f:
			date = f.read(12 * 1000)
	except OSError:
		return None
	loc = None
	for i in range(0, len(date) - 11, 12):
		if int.from_bytes(date[i + 8:i + 12], "big") == 3:
			loc = int.from_bytes(date[i:i + 8], "big")
	return loc


def _titluInregistrare(cale):
	"""Titlul unei inregistrari din <inregistrare>.meta (al doilea rand), sau „”."""
	f = _deschideObisnuit(cale + ".meta")
	if f is None:
		return ""
	try:
		with f:
			randuri = f.read(4096).decode("utf-8", "replace").split("\n")
	except OSError:
		return ""
	return randuri[1].strip() if len(randuri) > 1 else ""


def _decodare(D=None):
	"""Components/HdsDecodare cand programul de decodare e pe receptor, altfel None (DECODAREA, sus)."""
	if D is None:
		try:
			from Components import HdsDecodare as D
		except ImportError:
			return None
	try:
		return D if D.exista() else None
	except Exception:
		return None


def citesteLista(dosar, alfabetic=False, F=None, D=None):
	"""Filmele si inregistrarile din dosar, cu marimea, data si locul unde s-a ramas. Citeste discul: ruleaza pe firul
	listei (sau pe PC, in probe). None daca dosarul nu se poate citi."""
	F = _f(F)
	D = _decodare(D)
	try:
		nume_fisiere = os.listdir(dosar)
	except OSError as e:
		print("[HdsWebControl] filme: dosarul %s: %s" % (dosar, e))
		return None
	import stat as _stat
	candidati = []
	for nume in nume_fisiere:
		ext = _extensie(nume)
		if ext not in EXTENSII_FILME and ext != EXTENSIE_INREGISTRARE:
			continue
		cale = os.path.join(dosar, nume)
		try:
			st = os.stat(cale)
		except OSError:
			continue
		if not _stat.S_ISREG(st.st_mode):
			continue
		candidati.append((st.st_mtime, nume, ext, cale, st))
		if len(candidati) >= MAX_CANDIDATI:
			break
	# cele mai noi intai: intr-un dosar cu mai mult de MAX_FILME raman cele mai noi, nu cele venite primele din listdir
	# (ordinea discului); .meta si .cuts se citesc numai pentru cele pastrate
	candidati.sort(key=lambda x: -x[0])
	intrari = []
	for _mtime, nume, ext, cale, st in candidati[:MAX_FILME]:
		titlu = _titluInregistrare(cale) if ext == EXTENSIE_INREGISTRARE else ""
		loc = _locDinCuts(cale)
		intrari.append({
			"cale": _afisat(cale),
			"nume": titlu or _afisat(nume),
			"fel": ext.upper(),
			"marime": st.st_size,
			"data": int(st.st_mtime),
			"loc": loc // 90000 if loc is not None else None,
			"text_loc": F.textTimp(loc) if loc is not None else "",
		})
		if D is not None and ext == EXTENSIE_INREGISTRARE and D.deDecodat(cale):
			intrari[-1]["semn_decodare"] = _t(D.TXT_SEMN)
	if alfabetic:
		intrari.sort(key=lambda x: (x["nume"].lower(), -x["data"]))
	else:
		intrari.sort(key=lambda x: -x["data"])
	return intrari


def raspunsLista(intrari, dosar):
	if intrari is None:
		return {"result": False, "message": _t(TXT_DOSAR), "dosar": dosar, "filme": []}
	return {"result": True, "dosar": dosar, "filme": intrari}


def _alfabetic(cfg=None):
	try:
		return _config(cfg).movielist.moviesort.value == 1   # MovieList.SORT_ALPHANUMERIC
	except (AttributeError, KeyError):
		return False


class _FirLista(object):
	"""Citirea listei pe un fir separat, cate una odata; cererile venite cat ea ruleaza primesc acelasi rezultat.
	Rezultatul se preda firului enigma2 printr-un eTimer (40 ms); dupa TERMEN_LISTA_S raspunsul pleaca cu mesajul de
	disc lent, iar firul isi termina lucrul singur."""

	def __init__(self):
		self.asteapta = []
		self.gata = None
		self.fir = None
		self.pornit = 0.0
		self.ceas = None

	def cere(self, dosar, alfabetic, F, dupa):
		import threading
		import time
		self.asteapta.append(dupa)
		if self.fir is None:
			self.gata = None
			self.pornit = time.monotonic()

			def _lucreaza():
				try:
					rez = citesteLista(dosar, alfabetic, F)
				except Exception as e:
					print("[HdsWebControl] filme: lista: %s" % e)
					rez = None
				self.gata = (dosar, rez)
			self.fir = threading.Thread(target=_lucreaza, name="HdsWebFilme", daemon=True)
			self.fir.start()
		if self.ceas is None:
			from enigma import eTimer
			self.ceas = eTimer()
			self.ceas.callback.append(self._verifica)
		if not self.ceas.isActive():
			self.ceas.start(40, False)

	def _verifica(self):
		import time
		gata = self.gata
		if gata is None and time.monotonic() - self.pornit < TERMEN_LISTA_S:
			return
		self.ceas.stop()
		asteapta, self.asteapta = self.asteapta, []
		if gata is None:
			rez = {"result": False, "message": _t(TXT_LISTA_INCETA), "filme": []}
		else:
			rez = raspunsLista(gata[1], gata[0])
			self.fir = None
		for dupa in asteapta:
			try:
				dupa(rez)
			except Exception as e:
				print("[HdsWebControl] filme: raspunsul listei: %s" % e)


_firLista = _FirLista()


# PORNIREA (/api/filme-porneste): orice film de sub locurile filmelor (locuriFilme: dosarele filmelor din setari,
# dosarul implicit si dosarul de acum al listei de pe televizor), si din subdosarele lor, cu aceleasi paze ca dosarul
# unei inregistrari puse din aplicatii (dirname la /api/timeradd, aplicatii_web.dosarCerut si _radacina): textul caii
# absolut, fara „..”, fara caractere de control, cel mult MAX_CALE; calea REALA (dupa toate legaturile) sub calea reala
# a unui loc, iar un loc care e chiar radacina („/”) nu se primeste; terminatia cunoscuta si la calea reala; un fisier
# obisnuit. Inainte se primea numai un fisier direct din dosarul listei (proba de noapte 13-14.10: filmele din
# /media/hdd/movie/filme-proba/ nu se puteau porni din web).

def locuriFilme(cfg=None):
	"""Locurile filmelor, cu „/” la coada, ca locurile inregistrarilor din aplicatii (temporizatoare_web._locuri):
	config.movielist.videodirs, config.usage.default_path, plus dosarul de acum al listei de filme (dosarFilme)."""
	c = _config(cfg)
	try:
		lista = list(c.movielist.videodirs.value or [])
	except (AttributeError, KeyError, TypeError):
		lista = []
	try:
		lista.append(c.usage.default_path.value)
	except (AttributeError, KeyError):
		pass
	lista.append(dosarFilme(cfg))
	rez = []
	for x in lista:
		x = (x or "").strip() if isinstance(x, str) else ""
		if x and not x.endswith("/"):
			x += "/"
		if x and x not in rez:
			rez.append(x)
	return rez or ["/media/hdd/movie/"]


def caleCeruta(text):
	"""Calea unui film venita din cerere, verificata numai ca text (ca aplicatii_web.dosarCerut): absoluta, fara „..”,
	fara \\x00 sau alte caractere de control, cel mult MAX_CALE. -> textul sau None."""
	if not text or len(text) > MAX_CALE or any(ord(ch) < 0x20 or 0x7f <= ord(ch) <= 0x9f for ch in text):
		return None
	if not os.path.isabs(text) or ".." in text.replace("\\", "/").split("/"):
		return None
	return text


def filmSubLocuri(disc, locuri):
	"""Calea pe disc a filmului: calea reala sub calea reala a unui loc (nu „/”), terminatia cunoscuta si la calea
	reala, un fisier obisnuit (ca aplicatii_web._radacina si _deschideFlux). -> True / False."""
	real = os.path.realpath(disc)
	ext = _extensie(os.path.basename(real))
	if ext not in EXTENSII_FILME and ext != EXTENSIE_INREGISTRARE:
		return False
	for loc in locuri:
		r = os.path.realpath(loc)
		if os.path.dirname(r) == r:
			continue
		if real.startswith(r.rstrip(os.sep) + os.sep):
			return os.path.isfile(real)
	return False


def porneste(argumente, sesiune=None, cfg=None, deschide=None, F=None):
	"""POST /api/filme-porneste: un film de sub locurile filmelor (PORNIREA, sus), pornit pe televizor. de_la=loc reia
	de unde s-a ramas, de_la=inceput porneste de la inceput, fara ele intrebarea de pe televizor ramane cum e setata."""
	cale = caleCeruta(argumente.get("cale", ""))
	ext = _extensie(cale or "")
	bun = cale is not None and (ext in EXTENSII_FILME or ext == EXTENSIE_INREGISTRARE)
	if bun:
		# pentru Python calea trece prin octetii ei, pentru enigma2 (referinta) ramane textul UTF-8
		bun = filmSubLocuri(_caleDisc(cale), [_caleDisc(x) for x in locuriFilme(cfg)])
	if not bun:
		return {"result": False, "message": _t(TXT_FILM_LIPSA)}
	D = _decodare()
	if D is not None and ext == EXTENSIE_INREGISTRARE and D.deDecodat(_caleDisc(cale)):
		return {"result": False, "message": _t(D.TXT_PORNIRE)}
	mod = PORNIRI.get(argumente.get("de_la", ""))
	if deschide is None:
		deschide = deschideFilmul
	reusit, text = deschide(sesiune, cale, mod)
	return {"result": reusit, "message": _t(text)}


def _referinta(cale):
	from enigma import eServiceReference
	if _extensie(cale) == EXTENSIE_INREGISTRARE:
		return eServiceReference("1:0:0:0:0:0:0:0:0:0:" + cale)
	return eServiceReference(TIP_FILM, 0, cale)


_ceasuri = []


def _maiTarziu(ms, functie):
	from enigma import eTimer
	ceas = eTimer()

	def _bate():
		if ceas in _ceasuri:
			_ceasuri.remove(ceas)
		functie()
	ceas.callback.append(_bate)
	_ceasuri.append(ceas)
	ceas.start(ms, True)


def deschideFilmul(sesiune, cale, mod, dupaLista=False):
	"""Pe televizor: in playerul de filme deschis, filmul se schimba; peste bara principala se deschide playerul; lista
	de filme deschisa se inchide intai. Raspunsul la intrebarea de reluare (mod) ajunge in hdsPornireFilm, legat de cale.
	(reusit, text)."""
	if sesiune is None:
		return False, TXT_NU_MERGE
	from Screens.InfoBar import InfoBar, MoviePlayer
	dialog = sesiune.current_dialog
	if dialog.__class__.__name__ == "MovieSelection" and not dupaLista:
		dialog.close(None)
		_maiTarziu(400, lambda: deschideFilmul(sesiune, cale, mod, True))
		return True, TXT_PORNESTE
	ref = _referinta(cale)
	ales = (mod, cale) if mod else None
	if isinstance(dialog, MoviePlayer):
		dialog.hdsPornireFilm = ales
		dialog.movieSelected(ref)
	elif isinstance(dialog, InfoBar):
		# o inregistrare isi are semnele la pornire (intrebarea vine inainte ca open() sa se intoarca), un film dupa
		# citirea lor pe firul lui: raspunsul sta pe clasa cat dureaza open(), apoi pe fereastra, daca nu l-a folosit
		MoviePlayer.hdsPornireFilm = ales
		try:
			player = sesiune.open(MoviePlayer, ref)
		finally:
			MoviePlayer.hdsPornireFilm = None
		if ales and "hdsPornireFilm" not in player.__dict__:
			player.hdsPornireFilm = ales
	else:
		if dupaLista:
			print("[HdsWebControl] filme: dupa inchiderea listei e deschis %s" % dialog.__class__.__name__)
		return False, TXT_ALT_ECRAN
	try:
		from Components.config import config
		config.movielist.hds_ultimul_film.value = ref.toString()
		config.movielist.hds_ultimul_film.save()
	except (AttributeError, KeyError):
		pass
	return True, TXT_PORNESTE


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute (calea unui film pana la
	MAX_CALE, restul pana la MAX_TEXT)."""
	permise = set(x[0] for x in SETARI) | set(("fa", "secunde", "cale", "de_la"))
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_CALE if cheie == "cale" else MAX_TEXT].strip()
	return rez


def rute(baza, resource, sesiune=None, NOT_DONE_YET=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	e o functie care da sesiunea enigma2; cu NOT_DONE_YET (twisted.web.server) lista filmelor se citeste pe un fir si
	raspunsul pleaca la sfarsit, fara el (probele de pe PC) pe loc."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/filme: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(_ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ListaResource(baza):
		"""GET /api/filme-lista: numai citire; discul se citeste pe firul listei."""

		def render_GET(self, request):
			try:
				dosar = dosarFilme()
				alfabetic = _alfabetic()
				if NOT_DONE_YET is None:
					return self._raspunde(request, raspunsLista(citesteLista(dosar, alfabetic), dosar))
				obiect = self

				def _trimite(rez):
					try:
						request.write(obiect._raspunde(request, rez))
						request.finish()
					except Exception as e:
						print("[HdsWebControl] filme: raspunsul listei nu a plecat: %s" % e)
				_firLista.cere(dosar, alfabetic, _f(), _trimite)
				return NOT_DONE_YET
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request), sesiune=_ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class ComandaResource(_Schimba):
		lucru = staticmethod(comanda)

	class SeteazaResource(_Schimba):
		lucru = staticmethod(seteaza)

	class PornesteResource(_Schimba):
		lucru = staticmethod(porneste)

	class PaginaResource(resource.Resource):
		"""GET /filme: pagina „Filmul de acum”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"filme": StareResource(),
		b"filme-comanda": ComandaResource(),
		b"filme-seteaza": SeteazaResource(),
		b"filme-lista": ListaResource(),
		b"filme-porneste": PornesteResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /limbi."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("usage_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Filmul de acum</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(160px,300px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  select,input{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;box-sizing:border-box;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .nume{font-size:1.05rem;font-weight:600;word-break:break-word;margin:0 0 4px;}
  .stare{color:var(--text-slab);font-size:.92rem;margin:0 0 10px;}
  .bara{height:10px;border-radius:5px;background:#0f1216;border:1px solid var(--bordura);overflow:hidden;margin:6px 0 4px;}
  .bara div{height:100%;width:0;background:var(--albastru);}
  .timp{display:flex;justify-content:space-between;font-size:.9rem;color:var(--text-slab);}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
  .butoane button{flex:1 1 auto;}
  .sari{display:grid;grid-template-columns:1fr auto;gap:8px;margin-top:12px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .refuz{border:1px solid #8a3a30;background:#2a1714;border-radius:8px;padding:10px 12px;margin:0 0 10px;line-height:1.45;}
  .refuz .tehnic{color:var(--text-slab);font-size:.8rem;margin-top:4px;word-break:break-word;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .film{padding:10px 0;border-bottom:1px solid var(--bordura);}
  .film:last-child{border-bottom:0;}
  .film .detalii{color:var(--text-slab);font-size:.85rem;margin:2px 0 0;}
  .film .butoane{margin-top:8px;}
  .film .butoane button{flex:0 1 auto;min-width:150px;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Filmul de acum</h1>
<p class="mesaj" id="incarcare">Se citește filmul...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Filmul</h2>
    <p class="nota" id="faraFilm">Niciun film nu merge acum. Pornește unul din lista de mai jos sau de pe televizor, din lista de filme.</p>
    <div id="film" class="ascuns">
      <div class="refuz ascuns" id="refuz"><div id="refuzText"></div><div class="tehnic" id="refuzTehnic"></div></div>
      <p class="nume" id="nume"></p>
      <p class="stare" id="stare"></p>
      <div class="bara"><div id="progres"></div></div>
      <div class="timp"><span id="pozitie"></span><span id="lungime"></span></div>
      <div class="butoane">
        <button type="button" data-fa="inapoi" id="bInapoi" title="Derulare înapoi, ca tasta &lt;&lt;">&lt;&lt; Înapoi</button>
        <button type="button" data-fa="salt" data-s="-60">−1 min</button>
        <button type="button" data-fa="salt" data-s="-10">−10 s</button>
        <button type="button" id="bPauza">Pune pauză</button>
        <button type="button" data-fa="salt" data-s="10">+10 s</button>
        <button type="button" data-fa="salt" data-s="60">+1 min</button>
        <button type="button" data-fa="inainte" id="bInainte" title="Derulare înainte, ca tasta &gt;&gt;">Înainte &gt;&gt;</button>
      </div>
      <p class="nota ascuns" id="faraDerulare">Derularea rapidă nu merge la acest film (de exemplu la filmele de pe internet). Poți sări înainte sau înapoi cu butoanele de minute și secunde.</p>
      <div class="sari">
        <input type="text" id="la" inputmode="numeric" placeholder="Sari la, de exemplu 1:05:30" aria-label="Sari la">
        <button type="button" id="bLa">Sari</button>
      </div>
      <p class="nota" id="loc"></p>
      <p class="nota" id="formate"></p>
    </div>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <section class="card">
    <h2>Filmele din dosar</h2>
    <p class="nota" id="dosar">Aceleași filme ca în lista de filme de pe televizor.</p>
    <div id="listaFilme"></div>
    <div class="butoane"><button type="button" id="bLista">Citește lista din nou</button></div>
    <p class="mesaj" id="mesajLista"></p>
  </section>
  <section class="card">
    <h2>Setările filmelor</h2>
    <div id="randuri"></div>
    <div class="butoane"><button type="button" class="verde" id="salveaza">Salvează</button></div>
    <p class="mesaj" id="mesajSetari"></p>
    <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__ (cu nivelul de meniu Expert). Locul unde ai rămas se ține minte lângă film, în fișierul cu același nume și terminația .cuts, numai după primul minut și dacă stick-ul sau discul se poate scrie.</p>
  </section>
</div>
</main>
<script>
var CFG = __CONFIG__;
var DATE = null;
var SCHIMBAT = false;
function $(id){ return document.getElementById(id); }
function el(tag, cls, text){ var e = document.createElement(tag); if(cls){ e.className = cls; } if(text !== undefined){ e.textContent = text; } return e; }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(unde, text, eroare){ var m = $(unde); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function secunde(text){
  var p = String(text || "").trim().split(":"), s = 0;
  if(!p.length || p.length > 3){ return null; }
  for(var i = 0; i < p.length; i++){
    if(!/^\\d+$/.test(p[i])){ return null; }
    s = s * 60 + parseInt(p[i], 10);
  }
  return s;
}
function arataFilm(f){
  $("faraFilm").classList.toggle("ascuns", !!f);
  $("film").classList.toggle("ascuns", !f);
  if(!f){ return; }
  $("nume").textContent = f.nume;
  $("stare").textContent = f.stare;
  $("pozitie").textContent = f.text_pozitie;
  $("lungime").textContent = f.text_lungime;
  $("progres").style.width = (f.lungime && f.pozitie !== null) ? Math.min(100, Math.round(100 * f.pozitie / f.lungime)) + "%" : "0";
  $("bPauza").textContent = f.pauza ? "Redă" : "Pune pauză";
  Array.prototype.forEach.call(document.querySelectorAll("#film button, #film input"), function(b){ b.disabled = !!f.oprit; });
  $("bInainte").disabled = !f.derulare;
  $("bInapoi").disabled = !f.derulare;
  $("faraDerulare").classList.toggle("ascuns", !!f.derulare || !!f.oprit);
  $("loc").textContent = f.text_loc ? ("Locul ținut minte pentru film: " + f.text_loc + ".") : "";
  var formate = [];
  if(f.imagine){ formate.push("imagine " + f.imagine); }
  if(f.sunet){ formate.push("sunet " + f.sunet); }
  $("formate").textContent = formate.length ? ("Formatul: " + formate.join(", ") + ".") : "";
  var r = f.refuz;
  $("refuz").classList.toggle("ascuns", !r);
  if(r){
    $("refuzText").textContent = r.titlu + (r.detaliu ? " " + r.detaliu : "");
    $("refuzTehnic").textContent = r.tehnic || "";
  }
}
function setariDiferite(d){
  return (d.ordine || []).some(function(n){ var s = $("s_" + n); return !s || s.value !== d.setari[n].valoare; });
}
function areFocus(){ var a = document.activeElement; return !!(a && a.tagName === "SELECT"); }
function arataSetari(d){
  var c = $("randuri"); c.textContent = "";
  (d.ordine || []).forEach(function(n){
    var s = d.setari[n];
    var rand = el("div", "rand");
    var l = el("label", "", s.eticheta); l.setAttribute("for", "s_" + n);
    var sel = el("select"); sel.id = "s_" + n;
    (s.alegeri || []).forEach(function(a){ var o = el("option", "", a[1]); o.value = a[0]; sel.appendChild(o); });
    sel.value = s.valoare;
    sel.addEventListener("change", function(){ SCHIMBAT = true; });
    rand.appendChild(l); rand.appendChild(sel); c.appendChild(rand);
  });
  SCHIMBAT = false;
}
function arata(d, cuSetari){
  DATE = d;
  arataFilm(d.film);
  // listele de alegere se refac numai cand pe receptor s-a schimbat ceva si omul nu lucreaza in ele
  if(cuSetari || (!SCHIMBAT && !areFocus() && setariDiferite(d))){ arataSetari(d); }
}
function citeste(cuSetari){
  return cerere("/api/filme").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi filmul."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d, cuSetari);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."; });
}
function trimite(cale, valori, cuSetari, unde){
  var q = new URLSearchParams();
  Object.keys(valori).forEach(function(k){ q.set(k, valori[k]); });
  mesaj(unde, "Se trimite...");
  return cerere(cale, "POST", q).then(function(d){
    mesaj(unde, d.message, !d.result);
    if(d.setari){ arata(d, cuSetari && d.result); }
    return d;
  }).catch(function(){ mesaj(unde, "Receptorul nu răspunde.", true); });
}
function marime(o){ return o >= 1e10 ? Math.round(o / 1e9) + " GB" : Math.max(1, Math.round(o / 1e6)) + " MB"; }
function data(s){
  var d = new Date(s * 1000);
  function doua(n){ return (n < 10 ? "0" : "") + n; }
  return doua(d.getDate()) + "." + doua(d.getMonth() + 1) + "." + d.getFullYear() + " " + doua(d.getHours()) + ":" + doua(d.getMinutes());
}
function pornesteFilm(f, deLa){
  var v = {cale: f.cale};
  if(deLa){ v.de_la = deLa; }
  trimite("/api/filme-porneste", v, false, "mesajLista").then(function(){ setTimeout(function(){ citeste(false); }, 1500); });
}
function randFilm(f){
  var r = el("div", "film");
  r.appendChild(el("p", "nume", f.nume));
  r.appendChild(el("p", "detalii", [f.fel, marime(f.marime), data(f.data)].join(" · ")));
  if(f.text_loc){ r.appendChild(el("p", "detalii", "Ai rămas la " + f.text_loc + ".")); }
  if(f.semn_decodare){ r.appendChild(el("p", "detalii", f.semn_decodare)); }
  var b = el("div", "butoane");
  if(f.text_loc){
    var reia = el("button", "verde", "Reia de la " + f.text_loc); reia.type = "button";
    reia.addEventListener("click", function(){ pornesteFilm(f, "loc"); });
    var inceput = el("button", "", "De la început"); inceput.type = "button";
    inceput.addEventListener("click", function(){ pornesteFilm(f, "inceput"); });
    b.appendChild(reia); b.appendChild(inceput);
  } else {
    var porn = el("button", "verde", "Pornește"); porn.type = "button";
    porn.addEventListener("click", function(){ pornesteFilm(f, ""); });
    b.appendChild(porn);
  }
  r.appendChild(b);
  return r;
}
function citesteLista(){
  mesaj("mesajLista", "Se citește lista...");
  $("bLista").disabled = true;
  return cerere("/api/filme-lista").then(function(d){
    $("bLista").disabled = false;
    var c = $("listaFilme"); c.textContent = "";
    if(d.dosar){ $("dosar").textContent = "Dosarul " + d.dosar + ", ca în lista de filme de pe televizor."; }
    if(!d.result){ mesaj("mesajLista", d.message || "Lista nu se poate citi.", true); return; }
    (d.filme || []).forEach(function(f){ c.appendChild(randFilm(f)); });
    mesaj("mesajLista", (d.filme || []).length ? "" : "Dosarul nu are filme.");
  }).catch(function(){ $("bLista").disabled = false; mesaj("mesajLista", "Receptorul nu răspunde.", true); });
}
Array.prototype.forEach.call(document.querySelectorAll("button[data-fa]"), function(b){
  b.addEventListener("click", function(){
    var v = {fa: b.getAttribute("data-fa")};
    if(b.getAttribute("data-s")){ v.secunde = b.getAttribute("data-s"); }
    trimite("/api/filme-comanda", v, false, "mesaj");
  });
});
$("bPauza").addEventListener("click", function(){
  trimite("/api/filme-comanda", {fa: (DATE && DATE.film && DATE.film.pauza) ? "redare" : "pauza"}, false, "mesaj");
});
$("bLa").addEventListener("click", function(){
  var s = secunde($("la").value);
  if(s === null){ mesaj("mesaj", "Scrie locul ca minute:secunde sau ore:minute:secunde, de exemplu 1:05:30.", true); return; }
  trimite("/api/filme-comanda", {fa: "la", secunde: String(s)}, false, "mesaj");
});
$("salveaza").addEventListener("click", function(){
  var v = {};
  (DATE.ordine || []).forEach(function(n){ var s = $("s_" + n); if(s){ v[n] = s.value; } });
  trimite("/api/filme-seteaza", v, true, "mesajSetari");
});
$("bLista").addEventListener("click", citesteLista);
citeste(true).then(citesteLista);
setInterval(function(){ citeste(false); }, 2000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Filmul de acum"),
		N_("Se citește filmul..."),
		N_("Filmul"),
		N_("Niciun film nu merge acum. Pornește unul din lista de mai jos sau de pe televizor, din lista de "
			"filme."),
		N_("&lt;&lt; Înapoi"),
		N_("−1 min"),
		N_("Pune pauză"),
		N_("+1 min"),
		N_("Înainte &gt;&gt;"),
		N_("Derularea rapidă nu merge la acest film (de exemplu la filmele de pe internet). Poți sări "
			"înainte sau înapoi cu butoanele de minute și secunde."),
		N_("Sari"),
		N_("Filmele din dosar"),
		N_("Aceleași filme ca în lista de filme de pe televizor."),
		N_("Citește lista din nou"),
		N_("Setările filmelor"),
		N_("Salvează"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__ (cu nivelul de meniu Expert). Locul unde "
			"ai rămas se ține minte lângă film, în fișierul cu același nume și terminația .cuts, numai după "
			"primul minut și dacă stick-ul sau discul se poate scrie."),
		N_("Derulare înapoi, ca tasta &lt;&lt;"),
		N_("Derulare înainte, ca tasta &gt;&gt;"),
		N_("Sari la, de exemplu 1:05:30"),
		N_("Sari la"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Redă"),
		N_("Pune pauză"),
		N_("Locul ținut minte pentru film:"),
		N_("Formatul:"),
		N_("Receptorul nu a putut citi filmul."),
		N_("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("Receptorul nu răspunde."),
		N_("Ai rămas la"),
		N_("Reia de la"),
		N_("De la început"),
		N_("Pornește"),
		N_("Se citește lista..."),
		N_("Dosarul"),
		N_(", ca în lista de filme de pe televizor."),
		N_("Lista nu se poate citi."),
		N_("Dosarul nu are filme."),
		N_("Scrie locul ca minute:secunde sau ore:minute:secunde, de exemplu 1:05:30."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
