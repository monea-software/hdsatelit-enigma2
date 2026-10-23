# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsInregistrariProgramate.py: lista inregistrarilor programate (temporizatoarele din RecordTimer), textele ei si
# locul inregistrarilor cu spatiul liber, intr-un singur loc.
#
# Il folosesc ecranul „Înregistrări programate” (Screens/TimerEdit.py, TimerEditList) si pagina web
# (Plugins/Extensions/HdsWebControl/temporizatoare_web.py): aceeasi ordine a listei, aceeasi stare, aceleasi detalii,
# acelasi loc si acelasi spatiu liber, cu aceleasi texte.
#
# Ordinea: dupa ora de inceput; cu config.usage.timerlist_finished_timer_position = „la sfarsit”, cele terminate
# (procesate sau in starea StateEnded) trec la coada, tot dupa ora de inceput.
#
# Starea „nu pornește”: o inregistrare care inca asteapta (StateWaiting / StatePrepared) la PRAG_NU_POATE secunde dupa
# ora de inceput si al carei jurnal (RecordTimerEntry.log) are, dupa ultima reusita, o incercare cazuta. Cauza vine din
# codul jurnalului (17 fara disc, 1 fara tuner, 2 / 4 / 7 pregatirea, 13 pornirea).
#
# Locul unei inregistrari anume: dosarul ei, ca in RecordTimerEntry.calculateFilename (dosarul temporizatorului sau,
# fara el, config.usage.default_path). Daca locul e un disc adevarat o spune Components/HdsStocare.py (verificaDisc: nu
# RAM, nu memoria interna, marime minima). Citirea atinge discul (/proc/mounts, stat, statvfs; pe un stick FAT prima
# citire a spatiului liber poate parcurge toata tabela FAT, secunde intregi), deci merge pe un fir separat: cereLoc()
# porneste firul si intoarce ce se stie deja (sau None); fereastra unei inregistrari intreaba din nou dintr-un eTimer.
# Rezultatele se tin VARSTA_MAXIMA_LOC secunde; cel mult un fir de citire pe loc.
#
# Locul inregistrarilor NOI (lista de pe televizor si pagina web, stareLocNou): aceeasi logica si aceleasi texte ca
# ecranul „Locul înregistrărilor” si pagina /stocare (Components/HdsLocInregistrari.py: discurile conectate, „Folosește
# <disc> pentru înregistrări”, discul ales singur la prima inregistrare, intrebarea cand sunt mai multe); fara acel
# modul, citirea de mai sus. textLocProgramare: acelasi loc, pe scurt, in raspunsul unei programari din web.
#
# Tot aici, ca ecranul si pagina web sa faca acelasi lucru: orele implicite ale unei inregistrari noi, oprirea unei
# inregistrari repetate care merge (cele trei alegeri), campurile ferestrei unei inregistrari aplicate cu verificarea
# suprapunerii (modifica) si textele jurnalului pe intelesul oricui (textJurnal).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau listele, config-ul si cititorul lor.

import os
import re
import threading
import time

STARE_ASTEAPTA = "asteapta"
STARE_INCEPE = "incepe"
STARE_INREGISTREAZA = "inregistreaza"
STARE_COMUTAT = "comutat"
STARE_TERMINATA = "terminata"
STARE_OPRITA = "oprita"
STARE_NU_POATE = "nu_poate"

# starile din timer.TimerEntry (StateWaiting, StatePrepared, StateRunning, StateEnded)
_ASTEAPTA, _PREGATIT, _RULEAZA, _TERMINAT = 0, 1, 2, 3

# RecordTimer.AFTEREVENT: NONE, STANDBY, DEEPSTANDBY, AUTO
DUPA_NIMIC, DUPA_ASTEPTARE, DUPA_OPRIRE, DUPA_AUTOMAT = 0, 1, 2, 3

# un temporizator de comutare fara ora de sfarsit are sfarsitul egal cu inceputul (diferente de rotunjire sub 4 s)
PRAG_FARA_SFARSIT = 4

# cat timp (secunde) e buna o citire a locului; dupa atat, cererea urmatoare porneste o citire noua
VARSTA_MAXIMA_LOC = 30

# al treilea rand al detaliilor (starea si descrierea emisiunii) incape pe un singur rand al casetei (1712 px, HdsRegular
# 28): descrierea primeste ce ramane dupa textul starii, restul se taie cu „…”
MAX_RAND_STARE = 125
MAX_DESCRIERE = 110
MIN_DESCRIERE = 30

# secunde dupa ora de inceput de la care o inregistrare care inca asteapta si are o incercare cazuta „nu pornește”
PRAG_NU_POATE = 30

# o inregistrare noua fara emisiune din ghid: incepe peste INCEPE_PESTE_S si tine DURATA_IMPLICITA_S (televizor si web)
INCEPE_PESTE_S = 5 * 60
DURATA_IMPLICITA_S = 60 * 60

# codurile din jurnalul temporizatorului (RecordTimer.RecordTimerEntry.log)
COD_FARA_DISC = 17
# "Decodează mai târziu" (RecordTimer.tryPrepare, Components/HdsDecodare.py)
COD_DECODARE = 18
COD_FARA_CANAL = 1
COD_PREGATIRE = (2, 4, 7)
COD_PORNIRE = 13
# dupa unul din acestea incercarea a reusit (pregatita, pornita, oprita la sfarsit)
COD_REUSITA = (6, 11, 12)

# alegerile de pe televizor (si din web) pentru o inregistrare repetata care merge acum
ALEGERE_ACUM = "stoponlycurrent"
ALEGERE_TOT = "stopall"
ALEGERE_VIITOR = "stoponlycoming"
ALEGERI_REPETATA = (ALEGERE_ACUM, ALEGERE_TOT, ALEGERE_VIITOR)


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


# numele zilelor exista deja in traduceri (Screens/TimerEntry.py le foloseste la „zilele alese”)
ZILE = (N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"), N_("Friday"), N_("Saturday"), N_("Sunday"))

# aceleasi texte ca starea din randurile listei (Components/TimerList.py), ca randul si detaliile sa spuna la fel
TEXTE_STARE = {
	STARE_ASTEAPTA: N_("waiting"),
	STARE_INCEPE: N_("about to start"),
	STARE_INREGISTREAZA: N_("recording..."),
	STARE_COMUTAT: N_("zapped"),
	STARE_TERMINATA: N_("done!"),
	STARE_OPRITA: N_("disabled"),
	STARE_NU_POATE: N_("nu pornește"),
}

TEXTE_DUPA = {
	DUPA_NIMIC: N_("nu face nimic"),
	DUPA_ASTEPTARE: N_("trece în așteptare"),
	DUPA_OPRIRE: N_("se oprește de tot"),
	DUPA_AUTOMAT: N_("revine cum era înainte"),
}


# ------------------------------------------------------------------ lista

def _terminateLaSfarsit():
	try:
		from Components.config import config
		return bool(config.usage.timerlist_finished_timer_position.index)
	except Exception:
		return False


def _terminat(t, procesat):
	return procesat or getattr(t, "state", _ASTEAPTA) == _TERMINAT


def terminat(t, procesat):
	"""Procesata sau in starea StateEnded."""
	return _terminat(t, procesat)


def ordonate(active, procesate, terminate_la_sfarsit=False):
	"""[(temporizator, procesat)] in ordinea ecranului: dupa ora de inceput; cu terminate_la_sfarsit, cele terminate
	la coada (tot dupa ora de inceput)."""
	lista = [(t, False) for t in active] + [(t, True) for t in procesate]
	if terminate_la_sfarsit:
		lista.sort(key=lambda x: (_terminat(x[0], x[1]), int(x[0].begin)))
	else:
		lista.sort(key=lambda x: int(x[0].begin))
	return lista


def listaDin(rt, terminate_la_sfarsit=None):
	"""Lista ecranului din RecordTimer-ul dat (session.nav.RecordTimer)."""
	if terminate_la_sfarsit is None:
		terminate_la_sfarsit = _terminateLaSfarsit()
	return ordonate(list(rt.timer_list), list(rt.processed_timers), terminate_la_sfarsit)


def areTerminate(lista):
	"""Exista in lista macar una terminata si pornita (ce ar sterge „Șterge cele terminate”, RecordTimer.cleanup)."""
	for t, procesat in lista:
		if procesat and not getattr(t, "disabled", False):
			return True
	return False


def cauzaNuPoate(t):
	"""De ce nu porneste inregistrarea (text scurt) sau None: din jurnal, dupa ultima reusita, cea mai limpede cauza
	(fara disc, apoi fara tuner, apoi pornirea, apoi pregatirea)."""
	coduri = set()
	for intrare in reversed(list(getattr(t, "log_entries", None) or [])):
		try:
			cod, mesaj = int(intrare[1]), str(intrare[2])
		except (IndexError, TypeError, ValueError):
			continue
		if cod in COD_REUSITA:
			break
		if cod == COD_PORNIRE and not mesaj.startswith("start record"):
			continue
		coduri.add(cod)
	if COD_FARA_DISC in coduri:
		return _("nu am unde să înregistrez")
	if COD_FARA_CANAL in coduri:
		return _("niciun tuner nu poate recepționa canalul")
	if COD_PORNIRE in coduri:
		return _("înregistrarea nu a putut porni")
	if coduri & set(COD_PREGATIRE):
		return _("receptorul nu a putut pregăti înregistrarea")
	return None


def stare(t, procesat, acum=None):
	if getattr(t, "disabled", False):
		return STARE_OPRITA
	if procesat:
		return STARE_TERMINATA
	s = getattr(t, "state", _ASTEAPTA)
	if s in (_ASTEAPTA, _PREGATIT):
		acum = time.time() if acum is None else acum
		try:
			trecut = int(t.begin) + PRAG_NU_POATE < acum
		except (AttributeError, TypeError, ValueError):
			trecut = False
		if trecut and cauzaNuPoate(t):
			return STARE_NU_POATE
	if s == _PREGATIT:
		return STARE_INCEPE
	if s == _RULEAZA:
		return STARE_COMUTAT if getattr(t, "justplay", False) else STARE_INREGISTREAZA
	if s == _TERMINAT:
		return STARE_TERMINATA
	return STARE_ASTEAPTA


def textStare(t, procesat, acum=None):
	return _(TEXTE_STARE[stare(t, procesat, acum)])


def ruleaza(t):
	try:
		return bool(t.isRunning())
	except Exception:
		return getattr(t, "state", _ASTEAPTA) in (_PREGATIT, _RULEAZA)


# ------------------------------------------------------------------ textele

def ziText(ts):
	lt = time.localtime(int(ts))
	return "%s, %d.%02d.%d" % (_(ZILE[lt.tm_wday]), lt.tm_mday, lt.tm_mon, lt.tm_year)


def oraText(ts):
	lt = time.localtime(int(ts))
	return "%02d:%02d" % (lt.tm_hour, lt.tm_min)


def zileRepetare(repeated):
	"""Zilele unui temporizator repetat (bitul 0 = luni ... bitul 6 = duminica)."""
	repeated = int(repeated or 0)
	if repeated & 127 == 127:
		return _("în fiecare zi")
	if repeated & 127 == 31:
		return _("de luni până vineri")
	return ", ".join(_(ZILE[z]) for z in range(7) if repeated & (1 << z))


def faraSfarsit(t):
	return bool(getattr(t, "justplay", False)) and int(t.end) - int(t.begin) < PRAG_FARA_SFARSIT


def minute(t):
	return max(0, (int(t.end) - int(t.begin)) // 60)


def numeCanal(t):
	try:
		nume = t.service_ref.getServiceName() or ""
	except Exception:
		nume = ""
	# semnele de evidentiere DVB (0x86, 0x87) din numele venite de la emitator nu se arata
	return nume.replace(u"\u0086", u"").replace(u"\u0087", u"")


def textCand(t):
	"""Cand porneste: ziua si orele, sau zilele repetarii si orele."""
	if faraSfarsit(t):
		ore = _("la %s") % oraText(t.begin)
	else:
		ore = _("%s-%s (%d min)") % (oraText(t.begin), oraText(t.end), minute(t))
	if getattr(t, "repeated", 0):
		return _("Se repetă: %s, %s") % (zileRepetare(t.repeated), ore)
	return "%s, %s" % (ziText(t.begin), ore)


def textDupa(t):
	return _(TEXTE_DUPA.get(getattr(t, "afterEvent", DUPA_AUTOMAT), TEXTE_DUPA[DUPA_AUTOMAT]))


def locInregistrare(t=None, implicit=None):
	"""Dosarul in care merge inregistrarea: al temporizatorului, altfel locul implicit (config.usage.default_path)."""
	d = getattr(t, "dirname", None) if t is not None else None
	if d:
		return d
	if implicit is not None:
		return implicit
	try:
		from Components.config import config
		return config.usage.default_path.value
	except Exception:
		return "/hdd/movie/"


def locNou():
	"""Locul unei inregistrari noi puse de pe ecran (preferredTimerPath, ca TimerEditList.addCurrentTimer)."""
	try:
		from Components.UsageConfig import preferredTimerPath
		loc = preferredTimerPath()
	except Exception:
		loc = None
	return loc or locInregistrare()


def oreImplicite(acum=None):
	"""(inceput, sfarsit) pentru o inregistrare noua fara emisiune din ghid: peste INCEPE_PESTE_S, la minut fix, si
	DURATA_IMPLICITA_S. Aceleasi pe televizor (TimerEditList) si in pagina web."""
	acum = int(time.time() if acum is None else acum)
	inceput = (acum + INCEPE_PESTE_S + 59) // 60 * 60
	return inceput, inceput + DURATA_IMPLICITA_S


def _decodare():
	"""Components/HdsDecodare (inregistrarile "Decodează mai târziu"), sau None cand lipseste."""
	try:
		from Components import HdsDecodare
		return HdsDecodare
	except ImportError:
		return None


def textCe(t):
	"""Ce face: doar comuta sau inregistreaza (unde si ce face receptorul dupa); la una "Decodează mai târziu" (numai cu
	programul de decodare pe receptor) si semnul ei."""
	if getattr(t, "justplay", False):
		return _("Doar schimbă canalul, nu înregistrează.")
	text = _("Înregistrează în %s. După înregistrare: %s.") % (locInregistrare(t), textDupa(t))
	D = _decodare()
	if D is not None and D.seAplica(t):
		text += " %s." % _(D.TXT_SEMN)
	return text


def textStareRand(t, procesat, acum=None):
	"""„Stare: ...” sau, pentru una care nu porneste, cauza pe intelesul oricui."""
	if stare(t, procesat, acum) == STARE_NU_POATE:
		return _("Nu pornește: %s. Încerc din nou.") % cauzaNuPoate(t)
	return _("Stare: %s.") % textStare(t, procesat, acum)


def descriereScurta(t, loc_ocupat=0):
	"""Descrierea emisiunii pe un rand, taiata cu „…” ca, impreuna cu `loc_ocupat` caractere, sa incapa in
	MAX_RAND_STARE."""
	descriere = (getattr(t, "description", "") or "").strip().replace("\n", " ")
	maxim = max(MIN_DESCRIERE, min(MAX_DESCRIERE, MAX_RAND_STARE - loc_ocupat - 1))
	if len(descriere) > maxim:
		descriere = descriere[:maxim - 1].rstrip() + u"…"
	return descriere


def randuriDetalii(t, procesat, acum=None):
	"""Partile detaliilor: {cand, ce, stare, descriere, nu_poate}; ecranul le pune pe trei randuri, pagina web le
	foloseste separat (starea e acolo semnul de langa nume)."""
	stare_rand = textStareRand(t, procesat, acum)
	nu_poate = stare(t, procesat, acum) == STARE_NU_POATE
	return {
		"cand": textCand(t),
		"ce": textCe(t),
		"stare": stare_rand,
		"descriere": descriereScurta(t, len(stare_rand)),
		"nu_poate": stare_rand if nu_poate else "",
	}


def detalii(t, procesat, acum=None):
	"""Randurile de sub lista pentru temporizatorul ales: cand, ce face, starea (si descrierea emisiunii, scurtata)."""
	d = randuriDetalii(t, procesat, acum)
	randuri = [d["cand"], d["ce"]]
	randuri.append(("%s %s" % (d["stare"], d["descriere"])) if d["descriere"] else d["stare"])
	return "\n".join(randuri)


# ------------------------------------------------------------------ locul si spatiul liber

def marimeText(octeti):
	"""12,3 GB / 850 MB (virgula zecimala)."""
	if octeti is None:
		return ""
	gb = octeti / float(1024 ** 3)
	if gb >= 1:
		return ("%.1f GB" % gb).replace(".", ",")
	return "%d MB" % (octeti // (1024 ** 2))


def citesteLoc(cale, verifica=None, statvfs=None, text_motiv=None):
	"""Citirea propriu-zisa (atinge discul, deci numai pe un fir): {cale, bun, motiv, liber, total, text, detaliu}.
	`text` e fraza simpla, `detaliu` explicatia (spatiul liber sau cauza tehnica)."""
	if verifica is None or text_motiv is None:
		from Components import HdsStocare
		verifica = verifica or HdsStocare.verificaDisc
		text_motiv = text_motiv or HdsStocare.textMotiv
	statvfs = statvfs or getattr(os, "statvfs", None)
	bun, motiv = verifica(cale)
	rez = {"cale": cale, "bun": bool(bun), "motiv": motiv, "liber": None, "total": None}
	if bun:
		try:
			s = statvfs(cale)
			rez["liber"] = int(s.f_bavail) * int(s.f_frsize)
			rez["total"] = int(s.f_blocks) * int(s.f_frsize)
		except Exception:
			pass
		rez["text"] = _("Înregistrările se salvează în %s.") % cale
		if rez["liber"] is not None:
			rez["detaliu"] = _("Liber: %s din %s.") % (marimeText(rez["liber"]), marimeText(rez["total"]))
		else:
			rez["detaliu"] = ""
	else:
		rez["text"] = _("Nu am unde să înregistrez. Conectează un stick USB sau un hard disk.")
		detaliu = text_motiv(motiv, cale)
		rez["detaliu"] = (detaliu[:1].upper() + detaliu[1:] + ".") if detaliu else ""
	return rez


_zavor = threading.Lock()
_citiri = {}        # cale -> ultimul rezultat (cu „timp”)
_in_lucru = set()   # caile care au un fir de citire pornit


def _citesteSiTine(cale, citeste):
	try:
		rez = citeste(cale)
	except Exception as eroare:
		print("[HdsInregistrariProgramate] citirea locului %s: %s" % (cale, eroare))
		rez = {"cale": cale, "bun": False, "motiv": "eroare", "liber": None, "total": None,
			"text": _("Nu am putut citi locul înregistrărilor."), "detaliu": str(eroare)[:120]}
	rez["timp"] = time.time()
	with _zavor:
		_citiri[cale] = rez
		_in_lucru.discard(cale)


def _pornesteFir(cale, citeste):
	fir = threading.Thread(target=_citesteSiTine, args=(cale, citeste))
	fir.daemon = True
	fir.start()


def cereLoc(cale, din_nou=False, acum=None, citeste=None, porneste=None):
	"""Ultima citire a locului `cale` (dictionarul lui citesteLoc cu „timp”, sau None daca nu s-a citit inca) si,
	daca e mai veche de VARSTA_MAXIMA_LOC (sau din_nou), porneste o citire noua pe un fir. Nu atinge discul pe firul
	care o cheama. `citeste` si `porneste` sunt pentru probe (citirea si pornirea firului)."""
	acum = time.time() if acum is None else acum
	with _zavor:
		rez = _citiri.get(cale)
		vechi = rez is None or din_nou or acum - rez.get("timp", 0) >= VARSTA_MAXIMA_LOC
		pornesc = vechi and cale not in _in_lucru
		if pornesc:
			_in_lucru.add(cale)
	if pornesc:
		try:
			(porneste or _pornesteFir)(cale, citeste or citesteLoc)
		except Exception as eroare:
			print("[HdsInregistrariProgramate] firul de citire nu a pornit: %s" % eroare)
			with _zavor:
				_in_lucru.discard(cale)
	return dict(rez) if rez is not None else None


def seCiteste(cale):
	with _zavor:
		return cale in _in_lucru


def uitaCitirile():
	"""Pentru probe."""
	with _zavor:
		_citiri.clear()
		_in_lucru.clear()


# ------------------------------------------------------------------ locul inregistrarilor noi (lista si web)

def _lotStocare(L=None):
	"""Components/HdsLocInregistrari.py (discurile conectate si alegerea lor) sau None daca lipseste din imagine."""
	if L is not None:
		return L
	try:
		from Components import HdsLocInregistrari
		return HdsLocInregistrari
	except ImportError:
		return None


_scrise = set()


def _oDataInJurnal(text):
	"""O eroare care s-ar repeta la fiecare citire (ecranul intreaba la 250 ms, pagina la 30 s) se scrie o singura
	data."""
	if text not in _scrise:
		_scrise.add(text)
		print("[HdsInregistrariProgramate] %s" % text)


def _necitit(cale):
	return {"citit": False, "bun": None, "cale": cale, "text": _("Se citește locul înregistrărilor..."),
		"detaliu": "", "alege": False, "liber": None, "total": None, "se_citeste": True}


def stareLocNou(din_nou=False, L=None, cale=None):
	"""Unde merg inregistrarile noi, pentru lista de pe televizor si pagina web: {citit, bun, cale, text, detaliu,
	alege, liber, total, se_citeste}. `alege` spune ca ecranul „Locul înregistrărilor” are ce oferi (un disc bun care nu e ales, sau
	locul nu e bun). Pe firul enigma2 se citesc numai /proc/mounts si managerul de discuri; spatiul liber si
	verificarea discurilor merg pe fir (HdsLocInregistrari.cereStare)."""
	cale = cale or locNou()
	L = _lotStocare(L)
	if L is None:
		rez = cereLoc(cale, din_nou=din_nou)
		if rez is None:
			return _necitit(cale)
		return {"citit": True, "bun": bool(rez.get("bun")), "cale": cale, "text": rez.get("text", ""),
			"detaliu": rez.get("detaliu", ""), "alege": False, "liber": rez.get("liber"), "total": rez.get("total"),
			"se_citeste": seCiteste(cale)}
	cand, necit = [], []
	try:
		cand = L.candidati()
	except Exception as eroare:
		_oDataInJurnal("discurile montate: %s" % eroare)
	try:
		necit = L.necitite()
	except Exception as eroare:
		_oDataInJurnal("discurile necitite: %s" % eroare)
	stare_disc, se_citeste = L.cereStare(cand, cale, din_nou)
	if stare_disc is None:
		return _necitit(cale)
	t = L.texte(stare_disc, cand, necit, L.SCOP_MENIU, cale, None, se_citeste)
	loc = stare_disc.get("loc") or {}
	folosire = [r for r in t.get("randuri", []) if r.get("actiune") == L.ACT_FOLOSESTE]
	# mai multe discuri bune, niciunul tinut minte: nu e o problema (receptorul intreaba o data, la prima inregistrare)
	intrebare = bool(t.get("intrebare"))
	rez = {"citit": True, "bun": bool(t.get("bun")) or intrebare, "cale": cale, "liber": loc.get("liber"),
		"total": loc.get("total"), "alege": bool(folosire) or not t.get("bun"), "se_citeste": bool(se_citeste),
		"automat": t.get("automat"), "intrebare": intrebare}
	if t.get("automat") and t.get("bun"):
		# locul nu e pregatit inca, dar discul se alege singur la prima inregistrare (HdsLocInregistrari.decizie), poate
		# altul decat cel din cale: aceleasi fraze ca ecranul „Locul înregistrărilor” (numele discului si locul liber)
		rez["text"] = t.get("text", "")
		rez["detaliu"] = t.get("detaliu_loc", t.get("detaliu", ""))
	elif intrebare:
		rez["text"] = _("Am găsit mai multe discuri. La prima înregistrare te întreb pe care salvez.")
		rez["detaliu"] = t.get("detaliu_loc", "")
	elif rez["bun"]:
		folosit = [d for d in stare_disc.get("discuri") or [] if d.get("folosit")]
		if folosit:
			rez["text"] = _("Înregistrările noi se salvează pe „%s”.") % folosit[0].get("nume", "")
		else:
			rez["text"] = _("Înregistrările noi se salvează în %s.") % cale
		parti = []
		if loc.get("liber") is not None:
			parti.append(_("Liber: %s din %s.") % (marimeText(loc["liber"]), marimeText(loc["total"])))
		if folosit:
			parti.append(_("Dosarul: %s.") % cale)
		rez["detaliu"] = " ".join(parti)
	else:
		rez["text"] = t.get("text", "")
		# sub lista de pe televizor e un singur rand (cu „OK deschide meniul...” dupa el): ce e de facut; explicatiile
		# intregi (sfatul despre memoria interna, discurile rele sau necitite) sunt in ecranul „Locul înregistrărilor” si
		# in pagina /stocare
		rez["detaliu"] = t.get("detaliu", "") if t.get("cauta") else _("Conectează un stick USB sau un hard disk extern.")
	return rez


def textLocProgramare(L=None):
	"""Dupa o inregistrare programata din web (ghid_web, temporizatoare_web): unde se va salva, pe scurt, din ultima
	citire a discurilor (stareLocNou); „” cat nu e nicio citire. Fara niciun disc bun: ce e de facut pana la ora
	inregistrarii (omul care programeaza de pe telefon nu vede televizorul)."""
	try:
		rez = stareLocNou(L=L)
	except Exception as eroare:
		_oDataInJurnal("locul pentru raspunsul programarii: %s" % eroare)
		return ""
	if not rez.get("citit"):
		return ""
	if rez.get("bun"):
		return rez.get("text", "")
	return " ".join(x for x in (rez.get("text", ""), _("Conectează un stick USB sau un hard disk extern."),
		_("Conectează-l înainte de ora înregistrării.")) if x)


# ------------------------------------------------------------------ jurnalul unei inregistrari

_NUMAR = re.compile(r"-?\d+")


def _numar(mesaj):
	m = _NUMAR.search(mesaj or "")
	return int(m.group(0)) if m else 0


# evenimentele iRecordableService (lib/service/iservice.h): evStart, evEnd, evTunedIn, evTuneFailed, evRecordRunning,
# evRecordStopped, evNewProgramInfo, evRecordFailed, evRecordWriteError, evNewEventInfo
_EVENIMENTE = {
	0: N_("Scrierea pe disc a început."),
	1: N_("Scrierea pe disc s-a terminat."),
	3: N_("Canalul nu a putut fi recepționat."),
	7: N_("Înregistrarea a căzut."),
	8: N_("Nu se mai poate scrie pe disc. Poate e plin."),
}


def textJurnal(cod, mesaj):
	"""Un rand din jurnalul temporizatorului (RecordTimerEntry.log, in engleza) pe intelesul oricui. Mesajul original
	ramane langa el, mai mic, pentru cine cauta cauza tehnica."""
	mesaj = str(mesaj or "")
	try:
		cod = int(cod)
	except (TypeError, ValueError):
		return mesaj
	if cod == 0:
		return _("S-a ales numele fișierului.")
	if cod == 1:
		return _("Niciun tuner nu poate recepționa canalul acum.")
	if cod == 2:
		return _("Pregătirea înregistrării nu a mers.")
	if cod == 4:
		return _("Nu am putut scrie pe disc datele înregistrării.")
	if cod == 5:
		pas = _numar(mesaj)
		if pas == _PREGATIT:
			return _("Se pregătește.")
		if pas == _RULEAZA:
			return _("Pornește.")
		if pas == _TERMINAT:
			return _("Se termină.")
		return mesaj
	if cod == 6:
		return _("Pregătită; așteaptă ora de început.")
	if cod == 7:
		return _("Nu s-a putut pregăti.")
	if cod == 8:
		if mesaj.startswith("asking"):
			return _("Te întreb dacă pot schimba canalul.")
		return _("Nu e nevoie să schimb canalul privit.")
	if cod == 9:
		return _("Schimb canalul fără să întreb.")
	if cod == 10:
		return _("Încerc din nou peste %d secunde.") % _numar(mesaj)
	if cod == 11:
		if mesaj.startswith("wakeup"):
			return _("Receptorul pornește și trece pe canal.")
		if mesaj.startswith("start"):
			return _("Pornește înregistrarea.")
		return _("Trec pe canal.")
	if cod == 12:
		if mesaj.startswith("autoinc"):
			return _("Înregistrarea se prelungește cu %d minute.") % _numar(mesaj)
		return _("Înregistrarea s-a oprit.")
	if cod == 13:
		if mesaj.startswith("start record"):
			return _("Înregistrarea nu a pornit (eroarea %d).") % _numar(mesaj)
		return _("Am trecut pe canalul înregistrării.")
	if cod == 14:
		return _("Canalul nu s-a schimbat, deci înregistrarea probabil nu merge.")
	if cod == 15:
		return _("Ora înregistrării s-a schimbat.")
	if cod == 16:
		ev = _numar(mesaj)
		if ev in _EVENIMENTE:
			return _(_EVENIMENTE[ev])
		return _("Mesaj tehnic al înregistrării.")
	if cod == COD_FARA_DISC:
		loc = mesaj.split(" in ", 1)[1].rsplit(" (", 1)[0] if " in " in mesaj else ""
		return _("Nu am unde să înregistrez: %s nu este pe un stick sau pe un hard disk.") % loc
	if cod == COD_DECODARE:
		if mesaj.startswith("recording kept"):
			return _("Se înregistrează criptată, pentru decodarea de mai târziu.")
		return _("Canalul nu poate fi înregistrat criptat; se decriptează acum.")
	return mesaj


def oraJurnal(ts):
	"""Ora unui rand din jurnal: ZZ.LL.AAAA HH:MM."""
	lt = time.localtime(int(ts))
	return "%02d.%02d.%d %02d:%02d" % (lt.tm_mday, lt.tm_mon, lt.tm_year, lt.tm_hour, lt.tm_min)


def jurnal(t):
	"""[{moment, ora, text, original}] in ordinea din jurnal (cele mai vechi primele)."""
	rez = []
	for intrare in list(getattr(t, "log_entries", None) or []):
		try:
			moment, cod, mesaj = int(intrare[0]), intrare[1], str(intrare[2])
		except (IndexError, TypeError, ValueError):
			continue
		rez.append({"moment": moment, "ora": oraJurnal(moment), "text": textJurnal(cod, mesaj), "original": mesaj})
	return rez


# ------------------------------------------------------------------ o inregistrare repetata care merge acum

def alegeriRepetata():
	"""[(text, alegere)] pentru Galben pe o inregistrare repetata care merge (televizor si web)."""
	return [
		(_("Oprește acum, dar pornește data viitoare"), ALEGERE_ACUM),
		(_("Oprește acum și nu mai porni"), ALEGERE_TOT),
		(_("Lasă-o acum, dar nu mai porni data viitoare"), ALEGERE_VIITOR),
	]


def intrebareRepetata(t):
	if getattr(t, "justplay", False):
		return _("Schimbarea repetată a canalului merge acum. Ce faci?")
	return _("Înregistrarea repetată merge acum. Ce faci?")


def opresteRepetata(rt, t, alegere):
	"""Una din ALEGERI_REPETATA pe o inregistrare repetata care merge; salveaza. False pentru o alegere necunoscuta."""
	if alegere not in ALEGERI_REPETATA:
		return False
	if alegere in (ALEGERE_ACUM, ALEGERE_TOT):
		t.enable()
		t.processRepeated(findRunningEvent=False)
		rt.doActivate(t)
	if alegere in (ALEGERE_VIITOR, ALEGERE_TOT):
		t.disable()
	rt.timeChanged(t)
	rt.saveTimer()
	return True


def existaInca(rt, t):
	"""Temporizatorul e inca in RecordTimer (nu l-a scos altcineva: pagina web, ghidul, a doua bara)."""
	return t is not None and (t in rt.timer_list or t in rt.processed_timers)


# ------------------------------------------------------------------ campurile ferestrei (web)

CAMPURI = ("name", "description", "justplay", "begin", "end", "repeated", "repeatedbegindate", "afterEvent", "dirname",
	"service_ref", "hdsDecodareMaiTarziu")


def instantaneu(t):
	return dict((c, getattr(t, c, None)) for c in CAMPURI)


def reface(t, inainte):
	for c, v in inainte.items():
		setattr(t, c, v)


def aplicaCampuri(t, campuri):
	"""Pune pe temporizator campurile date ({name, description, justplay, begin, end, repeated, repeatedbegindate,
	afterEvent, dirname, service_ref, hdsDecodareMaiTarziu}); lipsa unui camp = neschimbat."""
	for c in CAMPURI:
		if c in campuri:
			setattr(t, c, campuri[c])


def modifica(rt, t, campuri, verificare):
	"""Ca Verde in fereastra unei inregistrari (TimerEditList.finishedEdit): campurile noi, verificarea suprapunerii
	(verificare = TimerSanityCheck), apoi timeChanged + saveTimer. La suprapunere totul revine cum era.
	-> (True, None) sau (False, lista suprapusa)."""
	inainte = instantaneu(t)
	aplicaCampuri(t, campuri)
	v = verificare(rt.timer_list, t)
	if not v.check():
		suprapuse = v.getSimulTimerList()
		reface(t, inainte)
		return False, suprapuse
	rt.timeChanged(t)
	rt.saveTimer()
	return True, None


# ------------------------------------------------------------------ canalele care nu se pot inregistra inca

# Posturile DAB+ si programele DVB-T2 din satelit vin printr-un releu local (Hds/DabT2: http://127.0.0.1:8889/t2/...,
# http://127.0.0.1:8898/dab/...), deci sunt referinte DVB cu cale. ServiceReference.isRecordable() primeste numai
# referintele DVB fara cale: RecordTimerEntry pune in locul lor o referinta goala si inregistrarea cadea cu „canal
# invalid” si referinta bruta (de exemplu Rai 4 HD din 5,0W). Inregistrarea fluxului
# releului nu e facuta inca (ar cere: isRecordable pentru fluxurile releului, scrierea fluxului http al releului intr-un
# .ts si tunerul tinut de releu cat dureaza inregistrarea). Pana atunci tasta REC (Screens/InfoBarGenerics.py),
# fereastra unei inregistrari (Screens/TimerEntry.py) si pagina web (HdsWebControl/temporizatoare_web.py) spun limita
# cu aceleasi texte, fara referinta.
T_CANAL_NEINREGISTRABIL = N_("Acest canal nu poate fi înregistrat.")
T_LIMITA_FLUX = {
	"t2": N_("Înregistrarea programelor DVB-T2 din satelit nu e încă posibilă."),
	"dab": N_("Înregistrarea posturilor DAB+ din satelit nu e încă posibilă."),
}
T_DETALIU_TEHNIC = N_("Detaliu tehnic: %s")


def _refText(ref, metode=("toString", "getPath")):
	"""Referinta ca text: din text, din eServiceReference (toString, getPath) sau din ServiceReference (.ref)."""
	if ref is None:
		return ""
	if isinstance(ref, str):
		return ref
	r = getattr(ref, "ref", ref)
	parti = []
	for metoda in metode:
		f = getattr(r, metoda, None)
		if f is None:
			continue
		try:
			v = f()
		except Exception:
			continue
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		if v:
			parti.append(v)
	return " ".join(parti)


def felNeinregistrabil(ref):
	"""'t2' / 'dab' cand referinta (text, eServiceReference sau ServiceReference) e a unui program DVB-T2 / post DAB+
	din satelit venit prin releul local, altfel None."""
	text = _refText(ref)
	if not text:
		return None
	try:
		from Components import HdsCapLista
	except ImportError:
		return None
	fel = HdsCapLista.fel_flux(text)
	return fel if fel in T_LIMITA_FLUX else None


def textLimitaInregistrare(ref, tr=_):
	"""Fraza limitei (DVB-T2 / DAB+ din satelit), tradusa, sau None pentru orice alt canal."""
	fel = felNeinregistrabil(ref)
	return tr(T_LIMITA_FLUX[fel]) if fel else None


def mesajNeinregistrabil(ref, tr=_):
	"""Mesajul de pe televizor pentru un canal care nu se poate inregistra: fraza simpla, apoi la DVB-T2 / DAB+ din
	satelit limita (fara referinta), la orice alt canal referinta ca detaliu tehnic (ca mesajele timeshift-ului)."""
	mesaj = tr(T_CANAL_NEINREGISTRABIL)
	limita = textLimitaInregistrare(ref, tr)
	if limita:
		return mesaj + "\n\n" + limita
	text = _refText(ref, ("toString",)) or _refText(ref)
	if text:
		return mesaj + "\n\n" + tr(T_DETALIU_TEHNIC) % text
	return mesaj
