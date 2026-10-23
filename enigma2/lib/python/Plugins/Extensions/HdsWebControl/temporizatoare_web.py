# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# temporizatoare_web.py: „Înregistrări programate” in interfata web (HdsWebControl).
#
# Pe televizor: tasta TIMER sau Meniu > Înregistrări (Screens/TimerEdit.py, TimerEditList), fereastra unei inregistrari
# (Screens/TimerEntry.py, TimerEntry) si jurnalul ei (TimerLog). Aici: aceeasi lista, cu aceeasi stare si aceleasi
# detalii, locul inregistrarilor noi cu spatiul liber (si drumul spre /stocare cand trebuie ales), adaugarea si
# modificarea cu aceleasi campuri ca fereastra (canal, ce face, repetarea si zilele, ziua, orele, nume, descriere,
# „După înregistrare”, locul), stergerea, oprirea / pornirea din nou (si cele trei alegeri pentru una repetata care
# merge acum), „Șterge cele terminate” si jurnalul unei inregistrari pe intelesul oricui.
#
# O SINGURA LOGICA: starea, detaliile, locul, orele implicite, oprirea celei repetate, modificarea cu verificarea
# suprapunerii si textele jurnalului vin din Components/HdsInregistrariProgramate.py (ca pe televizor); punerea si
# scoaterea unui temporizator din Components/HdsTemporizare.py (ca a doua bara si ghidul): la suprapunere se scurteaza
# intai cele care se lungesc singure, apoi se raporteaza lista suprapusa. Dupa orice schimbare se cheama
# RecordTimer.stateChanged, ca lista deschisa pe televizor sa se refaca singura.
#
# Lista: toate cele care nu s-au terminat (cel mult MAX_LISTA), apoi cele terminate, cele mai noi primele, cel mult
# MAX_TERMINATE; cate terminate nu se arata se spune separat („Șterge cele terminate” le scoate pe toate). Asa o lista cu
# sute de terminate nu ascunde una viitoare si raspunsul ramane scurt pe firul enigma2.
#
# Temporizatoarele nu au un numar al lor: fiecare primeste un id din canal, inceput, sfarsit si nume (numele poate avea
# octeti ne-UTF-8 din timers.xml, citit cu surrogateescape, deci codarea e cu surrogatepass); o cerere cu un id care nu
# mai exista (lista s-a schimbat intre timp) nu schimba nimic si cere reincarcarea paginii.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/temporizatoare                          lista, locul, orele implicite, locurile de ales
#   POST /api/temporizatoare-adauga?ref=&zi=AAAA-LL-ZZ&inceput=HH:MM&sfarsit=HH:MM&nume=&descriere=&doar_comuta=0|1
#        &repetare=o_data|zilnic|luni_vineri|zile&zile=0,1,..(0 = luni)&dupa=nimic|asteptare|oprire|automat&loc=
#        &decodare=acum|maitarziu (numai cu programul de decodare pe receptor, DECODAREA mai jos)
#   POST /api/temporizatoare-modifica?id=&... (aceleasi campuri; ref, nume, loc lipsa = neschimbate)
#   POST /api/temporizatoare-sterge?id=&confirmat=1            sterge una (Rosu)
#   POST /api/temporizatoare-opreste?id=&oprit=1|0             o opreste sau o porneste din nou (Galben)
#   POST /api/temporizatoare-opreste?id=&alegere=stoponlycurrent|stopall|stoponlycoming   una repetata care merge acum
#   POST /api/temporizatoare-curata?confirmat=1                sterge cele terminate (Albastru)
#   GET  /api/temporizatoare-jurnal?id=                        jurnalul unei inregistrari (INFO pe televizor)
#   POST /api/temporizatoare-jurnal-goleste?id=&confirmat=1    goleste jurnalul
#   GET  /temporizatoare                                      pagina
# Canalul se alege in pagina din listele de pe televizor, prin rutele paginii „Canale” (canale_web.py:
# /api/canale-buchete, /api/canale-lista, /api/canale-acum), nu dintr-o lista facuta a doua oara aici.
#
# DECODAREA: alegerea "Decriptează acum" / "Decodează mai târziu" a unei inregistrari (Components/HdsDecodare.py, ca
# randul "Decriptarea" din fereastra de pe televizor) exista in raspuns ("decodare") si in formular numai cu programul de
# decodare pe receptor; fara el campul din cerere nu se citeste si temporizatorul ramane cum e.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. Locul si spatiul liber se citesc pe un fir separat
# (HdsInregistrariProgramate.stareLocNou): raspunsul da ce se stie, iar pagina intreaba din nou peste cateva secunde.
# Pagina cere lista la 30 s si numai cat e vizibila. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe
# PC dau RecordTimer-ul, fabrica de temporizatoare, verificarea suprapunerii si numele canalelor.

import re
import time

MAX_TEXT = 120
MAX_REF = 200
MAX_LISTA = 300
MAX_TERMINATE = 50
_REF = re.compile(r"^[0-9A-Fa-f]{1,8}(:[0-9A-Fa-f]{1,8}){9}:[^\x00-\x1f]{0,160}$")
_ZI = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ORA = re.compile(r"^(\d{1,2}):(\d{2})$")
_ID = re.compile(r"^[0-9a-f]{12}$")
_ZILE = re.compile(r"^[0-6](,[0-6]){0,6}$")

REPETARI = ("o_data", "zilnic", "luni_vineri", "zile")
DUPA = (("nimic", 0), ("asteptare", 1), ("oprire", 2), ("automat", 3))


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _hip(H=None):
	if H is not None:
		return H
	from Components import HdsInregistrariProgramate
	return HdsInregistrariProgramate


def _ht(T=None):
	if T is not None:
		return T
	from Components import HdsTemporizare
	return HdsTemporizare


def _decodare(D=None):
	"""Components/HdsDecodare cand programul de decodare e pe receptor, altfel None (alegerea nu exista)."""
	if D is None:
		try:
			from Components import HdsDecodare as D
		except ImportError:
			return None
	try:
		return D if D.exista() else None
	except Exception:
		return None


def _rt(rt=None):
	if rt is not None:
		return rt
	import NavigationInstance
	return NavigationInstance.instance.RecordTimer


def _refText(t):
	try:
		sr = getattr(t, "service_ref", None)
		ref = getattr(sr, "ref", None)
		if ref is not None and hasattr(ref, "toString"):
			return ref.toString()
		return str(sr or "")
	except Exception:
		return ""


def idDe(t):
	"""Id-ul unui temporizator in pagina: din canal, inceput, sfarsit si nume (12 cifre hexazecimale)."""
	import hashlib
	cheie = u"%s|%d|%d|%s" % (_refText(t), int(t.begin), int(t.end), getattr(t, "name", "") or "")
	return hashlib.sha1(cheie.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def _text(s):
	"""Text pentru JSON: un nume cu octeti ne-UTF-8 (surogate) se arata cu semnul de inlocuire."""
	s = s or ""
	try:
		s.encode("utf-8")
		return s
	except UnicodeEncodeError:
		return s.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
	except AttributeError:
		return str(s)


def _gaseste(rt, id_, H):
	for t, procesat in H.listaDin(rt):
		if idDe(t) == id_:
			return t, procesat
	return None, False


def _schimbat(rt, t):
	"""Lista deschisa pe televizor (TimerEditList asculta on_state_change) se reface singura."""
	try:
		rt.stateChanged(t)
	except Exception as eroare:
		print("[HdsWebControl] temporizatoare: stateChanged: %s" % eroare)


def _repetare(repeated):
	"""(repetare, [zilele]) din bitii temporizatorului (bitul 0 = luni)."""
	repeated = int(repeated or 0) & 127
	zile = [z for z in range(7) if repeated & (1 << z)]
	if not repeated:
		return "o_data", zile
	if repeated == 127:
		return "zilnic", zile
	if repeated == 31:
		return "luni_vineri", zile
	return "zile", zile


def _ziOra(ts):
	"""(AAAA-LL-ZZ, HH:MM) in ora locala a receptorului: formularul paginii se umple cu ele, nu cu ora browserului
	(care poate fi in alt fus orar decat receptorul care citeste inapoi campurile)."""
	lt = time.localtime(int(ts))
	return "%d-%02d-%02d" % (lt.tm_year, lt.tm_mon, lt.tm_mday), "%02d:%02d" % (lt.tm_hour, lt.tm_min)


def _dupaNume(valoare):
	for nume, v in DUPA:
		if v == valoare:
			return nume
	return "automat"


def _intrare(t, procesat, H, acum=None):
	ruleaza = H.ruleaza(t)
	repetat = int(getattr(t, "repeated", 0) or 0)
	if getattr(t, "disabled", False):
		galben = "porneste"
	elif procesat:
		galben = None
	elif ruleaza:
		# una repetata care merge: cele trei alegeri de pe televizor; una simpla care merge nu se opreste cu Galben
		galben = "repetata" if repetat else None
	else:
		galben = "opreste"
	d = H.randuriDetalii(t, procesat, acum)
	repetare, zile = _repetare(repetat)
	st = H.stare(t, procesat, acum)
	zi = _ziOra((getattr(t, "repeatedbegindate", 0) or t.begin) if repetat else t.begin)[0]
	rez = {
		"id": idDe(t),
		"canal": _text(H.numeCanal(t)),
		"ref": _text(_refText(t)),
		"nume": _text(getattr(t, "name", "") or ""),
		"descriere": _text(getattr(t, "description", "") or ""),
		"inceput": int(t.begin),
		"sfarsit": int(t.end),
		"prima_zi": int(getattr(t, "repeatedbegindate", 0) or t.begin),
		"formular": {"zi": zi, "inceput": _ziOra(t.begin)[1], "sfarsit": _ziOra(t.end)[1]},
		"cand": _text(d["cand"]),
		"ce": _text(d["ce"]),
		"descriere_scurta": _text(d["descriere"]),
		"nu_poate": _text(d["nu_poate"]),
		"detalii": _text(H.detalii(t, procesat, acum)),
		"repetat": bool(repetat),
		"repetare": repetare,
		"zile": zile,
		"doar_comuta": bool(getattr(t, "justplay", False)),
		"dupa": _dupaNume(getattr(t, "afterEvent", 3)),
		"loc": _text(getattr(t, "dirname", None) or ""),
		"oprit": bool(getattr(t, "disabled", False)),
		"terminata": bool(procesat),
		"stare": st,
		"stare_text": _text(H.textStare(t, procesat, acum)),
		"ruleaza": ruleaza,
		"galben": galben,
		"jurnal": len(getattr(t, "log_entries", None) or []),
	}
	D = _decodare()
	if D is not None:
		rez["decodare"] = D.text(bool(getattr(t, "hdsDecodareMaiTarziu", False)))
	return rez


def _loc(H, L=None):
	rez = H.stareLocNou(L=L)
	return {"citit": bool(rez.get("citit")), "cale": rez.get("cale", ""), "bun": rez.get("bun"),
		"text": rez.get("text", ""), "detaliu": rez.get("detaliu", ""), "alege": bool(rez.get("alege")),
		"liber": rez.get("liber"), "total": rez.get("total")}


def _locuri(t=None, locuri=None):
	"""Locurile care se pot alege (ca in fereastra de pe televizor: dosarele filmelor, plus locul de acum)."""
	if locuri is None:
		locuri = []
		try:
			from Components.config import config
			locuri = list(config.movielist.videodirs.value or [])
		except Exception:
			locuri = []
		try:
			from Components.UsageConfig import preferredTimerPath, defaultMoviePath
			for x in (preferredTimerPath(), defaultMoviePath()):
				if x and x not in locuri:
					locuri.append(x)
		except Exception:
			pass
	locuri = list(locuri)
	d = getattr(t, "dirname", None) if t is not None else None
	if d and d not in locuri:
		locuri.append(d)
	return locuri


def _oreImplicite(H, acum=None):
	inceput, sfarsit = H.oreImplicite(acum)
	a, b = time.localtime(inceput), time.localtime(sfarsit)
	return {"zi": "%d-%02d-%02d" % (a.tm_year, a.tm_mon, a.tm_mday), "inceput": "%02d:%02d" % (a.tm_hour, a.tm_min),
		"sfarsit": "%02d:%02d" % (b.tm_hour, b.tm_min)}


def stare(rt=None, H=None, L=None, acum=None, locuri=None):
	"""Pentru GET /api/temporizatoare."""
	H = _hip(H)
	rt = _rt(rt)
	lista = H.listaDin(rt, False)
	active = [x for x in lista if not H.terminat(x[0], x[1])]
	terminate = [x for x in lista if H.terminat(x[0], x[1])]
	terminate.sort(key=lambda x: -int(x[0].begin))
	aratate = active[:MAX_LISTA] + terminate[:MAX_TERMINATE]
	rez = {
		"result": True,
		"temporizatoare": [_intrare(t, procesat, H, acum) for t, procesat in aratate],
		"numar": len(lista),
		"numar_terminate": len(terminate),
		"terminate_ascunse": max(0, len(terminate) - MAX_TERMINATE),
		"are_terminate": H.areTerminate(lista),
		"loc": _loc(H, L),
		"implicit": _oreImplicite(H, acum),
		"locuri": [_text(x) for x in _locuri(locuri=locuri)],
		"alegeri_repetata": [[_text(x), k] for x, k in H.alegeriRepetata()],
	}
	D = _decodare()
	rez["decodare"] = {"exista": D is not None, "implicit": D.text(D.implicit()) if D is not None else "acum"}
	if not lista:
		rez["gol"] = _t("Nu ai nicio înregistrare programată. Adaugă una mai jos sau alege o emisiune din ghidul TV.")
	return rez


def _cuMesaj(rez, bun, mesaj):
	rez.update({"result": bool(bun), "message": mesaj})
	return rez


def _momentul(zi, ora):
	"""(AAAA, LL, ZZ) + (HH, MM) -> secunde (ora locala a receptorului) sau None."""
	try:
		return int(time.mktime((zi[0], zi[1], zi[2], ora[0], ora[1], 0, 0, 0, -1)))
	except (OverflowError, ValueError):
		return None


def _citesteZi(text):
	m = _ZI.match(text or "")
	if not m:
		return None
	a, l, z = int(m.group(1)), int(m.group(2)), int(m.group(3))
	if not (2000 <= a <= 2100 and 1 <= l <= 12 and 1 <= z <= 31):
		return None
	return a, l, z


def _citesteOra(text):
	m = _ORA.match(text or "")
	if not m:
		return None
	h, mi = int(m.group(1)), int(m.group(2))
	if not (0 <= h <= 23 and 0 <= mi <= 59):
		return None
	return h, mi


def _numeSuprapuse(suprapuse, H):
	nume = []
	for x in (suprapuse or [])[1:6]:
		try:
			nume.append(u"%s (%s, %s)" % (_text(x.name or H.numeCanal(x)), _text(H.numeCanal(x)), H.textCand(x)))
		except Exception:
			continue
	return u"; ".join(nume)


def _mesajSuprapunere(suprapuse, H):
	alte = _numeSuprapuse(suprapuse, H)
	if alte:
		return _t("Se suprapune cu alte înregistrări programate: %s. Schimbă orele sau șterge una dintre ele.") % alte
	# TimerSanityCheck intoarce numai temporizatorul nou cand niciun tuner nu poate lua canalul
	return _t("Niciun tuner nu poate recepționa acest canal la ora aleasă.") + " " + _t("Verifică antena și tunerele.")


def _campuri(argumente, t, acum, locuri):
	"""Campurile ferestrei din argumentele cererii -> (campuri, None) sau (None, mesaj). `t` e temporizatorul
	modificat (None la adaugare): ce lipseste din cerere ramane cum e la el."""
	zi = _citesteZi(argumente.get("zi"))
	inceput = _citesteOra(argumente.get("inceput"))
	if "doar_comuta" in argumente or t is None:
		doar_comuta = argumente.get("doar_comuta") == "1"
	else:
		doar_comuta = bool(getattr(t, "justplay", False))
	if argumente.get("sfarsit"):
		sfarsit = _citesteOra(argumente.get("sfarsit"))
	else:
		sfarsit = inceput if doar_comuta else None
	if zi is None or inceput is None or sfarsit is None:
		return None, _t("Ziua și orele se scriu ca 2026-09-27 și 20:30.")
	begin = _momentul(zi, inceput)
	end = _momentul(zi, sfarsit)
	if begin is None or end is None:
		return None, _t("Ziua și orele se scriu ca 2026-09-27 și 20:30.")
	# ca pe televizor (TimerEntry.getBeginEnd): o ora de sfarsit inaintea celei de inceput e a doua zi
	if end < begin:
		end += 86400
	repetare = argumente.get("repetare") or ("o_data" if t is None else _repetare(getattr(t, "repeated", 0))[0])
	if repetare not in REPETARI:
		return None, _t("Valoare necunoscută pentru %s.") % "repetare"
	biti = 0
	if repetare == "zilnic":
		biti = 127
	elif repetare == "luni_vineri":
		biti = 31
	elif repetare == "zile":
		zile = argumente.get("zile", "")
		if not _ZILE.match(zile):
			return None, _t("Alege cel puțin o zi.")
		for z in zile.split(","):
			biti |= 1 << int(z)
	if not biti and (end if end > begin else begin + 60) <= acum:
		return None, _t("Ora aleasă a trecut deja.")
	campuri = {"begin": begin, "end": end, "justplay": doar_comuta, "repeated": biti,
		"repeatedbegindate": begin}
	if "dupa" in argumente:
		valori = dict(DUPA)
		if argumente["dupa"] not in valori:
			return None, _t("Valoare necunoscută pentru %s.") % "dupa"
		campuri["afterEvent"] = valori[argumente["dupa"]]
	if argumente.get("loc"):
		if argumente["loc"] not in _locuri(t, locuri):
			return None, _t("Alege locul din listă.")
		campuri["dirname"] = argumente["loc"]
	D = _decodare()
	if D is not None and "decodare" in argumente:
		mai_tarziu = D.dinCerere(argumente["decodare"])
		if mai_tarziu is None:
			return None, _t("Valoare necunoscută pentru %s.") % "decodare"
		campuri["hdsDecodareMaiTarziu"] = mai_tarziu and not doar_comuta
	if "descriere" in argumente:
		campuri["description"] = (argumente.get("descriere") or "").strip()[:MAX_TEXT]
	nume = (argumente.get("nume") or "").strip()[:MAX_TEXT]
	if nume:
		campuri["name"] = nume
	return campuri, None


def _serviciu(ref, serviciu):
	"""(ServiceReference, None) sau (None, mesaj)."""
	if not ref or len(ref) > MAX_REF or not _REF.match(ref):
		return None, _t("Alege canalul.")
	if serviciu is None:
		from ServiceReference import ServiceReference as serviciu
	sr = serviciu(ref)
	try:
		inregistrabil = sr.isRecordable()
	except Exception:
		inregistrabil = False
	if not inregistrabil:
		# 0.3.0: un program DVB-T2 / post DAB+ din satelit: limita, cu textul de pe televizor
		# (Components/HdsInregistrariProgramate.textLimitaInregistrare), fara referinta
		try:
			from Components import HdsInregistrariProgramate as HIP
			limita = HIP.textLimitaInregistrare(ref, _t)
		except Exception:
			limita = None
		if limita:
			return None, limita
		return None, _t("Pe canalul acesta nu se poate programa o înregistrare.")
	return sr, None


def _textLocProgramare(H):
	f = getattr(H, "textLocProgramare", None)
	try:
		return f() if f is not None else ""
	except Exception:
		return ""


def _mesajGata(intr, H, nume):
	if getattr(intr, "justplay", False):
		return _t("Gata: receptorul trece pe %s: %s.") % (_text(H.numeCanal(intr)) or nume, H.textCand(intr))
	return _t("Gata: „%s” se înregistrează: %s.") % (nume, H.textCand(intr))


def adauga(argumente, rt=None, H=None, T=None, fabrica=None, serviciu=None, acum=None, nume_din_ghid=None,
		loc_nou=None, locuri=None):
	"""POST /api/temporizatoare-adauga. `fabrica` (probele) primeste aceleasi argumente ca RecordTimerEntry,
	`serviciu` face ServiceReference, `nume_din_ghid(ref, moment)` da titlul emisiunii din ghid (sau "")."""
	H = _hip(H)
	T = _ht(T)
	rt = _rt(rt)
	acum = time.time() if acum is None else acum
	ref = argumente.get("ref", "")
	if not ref or len(ref) > MAX_REF or not _REF.match(ref):
		return _cuMesaj(stare(rt, H, locuri=locuri), False, _t("Alege canalul."))
	campuri, eroare = _campuri(argumente, None, acum, locuri)
	if eroare:
		return _cuMesaj(stare(rt, H, locuri=locuri), False, eroare)
	sr, eroare = _serviciu(ref, serviciu)
	if eroare:
		return _cuMesaj(stare(rt, H, locuri=locuri), False, eroare)
	nume = campuri.get("name", "")
	if not nume and nume_din_ghid is not None:
		try:
			nume = (nume_din_ghid(ref, campuri["begin"] + 60) or "")[:MAX_TEXT]
		except Exception:
			nume = ""
	if not nume:
		try:
			nume = (sr.getServiceName() or "")[:MAX_TEXT]
		except Exception:
			nume = ""
	loc = campuri.get("dirname")
	if loc is None:
		if loc_nou is None:
			try:
				from Components.UsageConfig import preferredTimerPath
				loc_nou = preferredTimerPath()
			except Exception:
				loc_nou = None
		loc = loc_nou
	if fabrica is None:
		from RecordTimer import RecordTimerEntry as fabrica
	extra = {}
	if "afterEvent" in campuri:
		extra["afterEvent"] = campuri["afterEvent"]
	intr = fabrica(sr, campuri["begin"], campuri["end"], nume, campuri.get("description", ""), None,
		justplay=campuri["justplay"], checkOldTimers=True, dirname=loc, **extra)
	if campuri["repeated"]:
		intr.repeated = campuri["repeated"]
		intr.repeatedbegindate = campuri["repeatedbegindate"]
	if "hdsDecodareMaiTarziu" in campuri:
		intr.hdsDecodareMaiTarziu = campuri["hdsDecodareMaiTarziu"]
	# temporizatorul de comutare (justplay): mesajele spun comutarea, nu inregistrarea
	comutare = bool(campuri["justplay"])
	try:
		rez, suprapuse = T.pune(intr, rt)
	except Exception as eroare:
		print("[HdsWebControl] temporizatoare: nu s-a putut pune: %s" % eroare)
		return _cuMesaj(stare(rt, H, locuri=locuri), False, _t("Receptorul nu a putut pune comutarea.") if comutare
			else _t("Receptorul nu a putut pune înregistrarea."))
	if rez != T.REZULTAT_PUS:
		return _cuMesaj(stare(rt, H, locuri=locuri), False,
			(_t("Nu am pus comutarea.") if comutare else _t("Nu am pus înregistrarea.")) + " " +
			_mesajSuprapunere(suprapuse, H))
	if not H.existaInca(rt, intr):
		# RecordTimer.record nu pune o dublura (TimerSanityCheck.doubleCheck) si intoarce tot None
		return _cuMesaj(stare(rt, H, locuri=locuri), False, _t("Există deja o comutare la fel.") if comutare else
			_t("Există deja o înregistrare la fel."))
	_schimbat(rt, intr)
	mesaj = _mesajGata(intr, H, _text(nume))
	if not getattr(intr, "justplay", False):
		# unde se va salva (sau ce e de facut fara disc), langa „Gata”: acelasi text ca randul locului de sus
		loc = _textLocProgramare(H)
		if loc:
			mesaj += " " + loc
	return _cuMesaj(stare(rt, H, locuri=locuri), True, mesaj)


def modifica(argumente, rt=None, H=None, verificare=None, serviciu=None, acum=None, locuri=None):
	"""POST /api/temporizatoare-modifica (Verde in fereastra unei inregistrari). Verificarea suprapunerii ca pe
	televizor; la suprapunere nu se schimba nimic. `verificare` (TimerSanityCheck) si `serviciu` sunt pentru probe."""
	H = _hip(H)
	rt = _rt(rt)
	acum = time.time() if acum is None else acum
	id_ = argumente.get("id", "")
	t, _procesat = _gaseste(rt, id_, H) if _ID.match(id_) else (None, False)
	if t is None:
		return _cuMesaj(stare(rt, H, locuri=locuri), False, _t("Lista s-a schimbat între timp. Reîncarcă pagina."))
	campuri, eroare = _campuri(argumente, t, acum, locuri)
	if eroare:
		return _cuMesaj(stare(rt, H, locuri=locuri), False, eroare)
	ref = argumente.get("ref", "")
	if ref and ref != _refText(t):
		sr, eroare = _serviciu(ref, serviciu)
		if eroare:
			return _cuMesaj(stare(rt, H, locuri=locuri), False, eroare)
		campuri["service_ref"] = sr
	if verificare is None:
		from Components.TimerSanityCheck import TimerSanityCheck as verificare
	bun, suprapuse = H.modifica(rt, t, campuri, verificare)
	nume = _text(t.name or H.numeCanal(t))
	if not bun:
		return _cuMesaj(stare(rt, H, locuri=locuri), False,
			_t("Nu am salvat schimbarea.") + " " + _mesajSuprapunere(suprapuse, H))
	_schimbat(rt, t)
	return _cuMesaj(stare(rt, H, locuri=locuri), True, _t("Am salvat „%s”: %s.") % (nume, H.textCand(t)))


def sterge(argumente, rt=None, H=None, T=None):
	"""POST /api/temporizatoare-sterge?id=&confirmat=1 (Rosu pe televizor)."""
	H = _hip(H)
	T = _ht(T)
	rt = _rt(rt)
	if argumente.get("confirmat") != "1":
		return _cuMesaj(stare(rt, H), False, _t("Se cere confirmarea (confirmat=1)."))
	id_ = argumente.get("id", "")
	t, _procesat = _gaseste(rt, id_, H) if _ID.match(id_) else (None, False)
	if t is None:
		return _cuMesaj(stare(rt, H), False, _t("Lista s-a schimbat între timp. Reîncarcă pagina."))
	nume = _text(t.name or H.numeCanal(t))
	if not T.scoate(t, rt):
		return _cuMesaj(stare(rt, H), False, _t("Receptorul nu a putut șterge înregistrarea."))
	_schimbat(rt, t)
	return _cuMesaj(stare(rt, H), True, _t("Am șters „%s”.") % nume)


def opreste(argumente, rt=None, H=None, verificare=None):
	"""POST /api/temporizatoare-opreste?id=&oprit=1|0 (Galben pe televizor), sau &alegere= pentru una repetata care
	merge acum. Pornirea din nou trece prin aceeasi verificare de suprapunere ca pe televizor (TimerSanityCheck);
	`verificare` e pentru probe."""
	H = _hip(H)
	rt = _rt(rt)
	id_ = argumente.get("id", "")
	oprit = argumente.get("oprit")
	alegere = argumente.get("alegere")
	if oprit not in ("0", "1") and alegere not in H.ALEGERI_REPETATA:
		return _cuMesaj(stare(rt, H), False, _t("Se alege cu oprit=1 (oprește) sau oprit=0 (pornește din nou)."))
	t, _procesat = _gaseste(rt, id_, H) if _ID.match(id_) else (None, False)
	if t is None:
		return _cuMesaj(stare(rt, H), False, _t("Lista s-a schimbat între timp. Reîncarcă pagina."))
	nume = _text(t.name or H.numeCanal(t))
	if alegere in H.ALEGERI_REPETATA:
		if not (H.ruleaza(t) and getattr(t, "repeated", 0)):
			return _cuMesaj(stare(rt, H), False, _t("„%s” nu merge acum. Reîncarcă pagina.") % nume)
		H.opresteRepetata(rt, t, alegere)
		_schimbat(rt, t)
		texte = dict((k, x) for x, k in H.alegeriRepetata())
		return _cuMesaj(stare(rt, H), True, u"%s: %s." % (nume, texte[alegere]))
	if oprit == "1":
		if t.disabled:
			return _cuMesaj(stare(rt, H), False, _t("„%s” era deja oprită.") % nume)
		if H.ruleaza(t):
			return _cuMesaj(stare(rt, H), False, _t("„%s” merge acum. Ca s-o oprești, șterge-o din listă; ce s-a "
				"înregistrat până acum rămâne.") % nume)
		t.disable()
		mesaj = _t("Am oprit „%s”; nu mai pornește.") % nume
	else:
		if not t.disabled:
			return _cuMesaj(stare(rt, H), False, _t("„%s” era deja pornită.") % nume)
		t.enable()
		if verificare is None:
			from Components.TimerSanityCheck import TimerSanityCheck as verificare
		v = verificare(rt.timer_list, t)
		if not v.check():
			t.disable()
			rt.timeChanged(t)
			rt.saveTimer()
			_schimbat(rt, t)
			return _cuMesaj(stare(rt, H), False, _t("Nu am pornit-o.") + " " + _mesajSuprapunere(v.getSimulTimerList(), H))
		if v.doubleCheck():
			t.disable()
			rt.timeChanged(t)
			rt.saveTimer()
			_schimbat(rt, t)
			return _cuMesaj(stare(rt, H), False, _t("Există deja o înregistrare la fel; am lăsat-o pe aceasta oprită."))
		mesaj = _t("Am pornit din nou „%s”.") % nume
	rt.timeChanged(t)
	# timeChanged() numai reordoneaza in memorie; saveTimer() o tine si dupa o repornire (ca pe televizor)
	rt.saveTimer()
	_schimbat(rt, t)
	return _cuMesaj(stare(rt, H), True, mesaj)


def curata(argumente, rt=None, H=None):
	"""POST /api/temporizatoare-curata?confirmat=1 (Albastru pe televizor)."""
	H = _hip(H)
	rt = _rt(rt)
	if argumente.get("confirmat") != "1":
		return _cuMesaj(stare(rt, H), False, _t("Se cere confirmarea (confirmat=1)."))
	if not H.areTerminate(H.listaDin(rt)):
		return _cuMesaj(stare(rt, H), False, _t("Nu era nimic terminat de șters."))
	rt.cleanup()
	rt.saveTimer()
	_schimbat(rt, None)
	return _cuMesaj(stare(rt, H), True, _t("Am șters înregistrările terminate."))


def jurnal(argumente, rt=None, H=None):
	"""GET /api/temporizatoare-jurnal?id= (INFO pe televizor): randurile pe intelesul oricui, cu mesajul original."""
	H = _hip(H)
	rt = _rt(rt)
	id_ = argumente.get("id", "")
	t, _procesat = _gaseste(rt, id_, H) if _ID.match(id_) else (None, False)
	if t is None:
		return {"result": False, "message": _t("Lista s-a schimbat între timp. Reîncarcă pagina.")}
	randuri = [dict(r, text=_text(r["text"]), original=_text(r["original"])) for r in H.jurnal(t)]
	rez = {"result": True, "id": id_, "nume": _text(t.name or H.numeCanal(t)), "jurnal": randuri}
	if not randuri:
		rez["gol"] = _t("Jurnalul este gol.")
	return rez


def golesteJurnal(argumente, rt=None, H=None):
	"""POST /api/temporizatoare-jurnal-goleste?id=&confirmat=1 (Albastru in jurnalul de pe televizor)."""
	H = _hip(H)
	rt = _rt(rt)
	if argumente.get("confirmat") != "1":
		return {"result": False, "message": _t("Se cere confirmarea (confirmat=1).")}
	id_ = argumente.get("id", "")
	t, _procesat = _gaseste(rt, id_, H) if _ID.match(id_) else (None, False)
	if t is None:
		return {"result": False, "message": _t("Lista s-a schimbat între timp. Reîncarcă pagina.")}
	t.log_entries = []
	rt.saveTimer()
	_schimbat(rt, t)
	rez = jurnal({"id": id_}, rt, H)
	rez["message"] = _t("Am golit jurnalul.")
	return rez


def _numeDinGhid(ref, moment):
	"""Titlul emisiunii din ghid la `moment` pe canalul `ref` (sau "")."""
	try:
		from enigma import eEPGCache, eServiceReference
		ev = eEPGCache.getInstance().lookupEventTime(eServiceReference(ref), int(moment))
		return (ev.getEventName() or "") if ev else ""
	except Exception:
		return ""


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	permise = set(("ref", "zi", "inceput", "sfarsit", "nume", "descriere", "doar_comuta", "repetare", "zile", "dupa",
		"loc", "id", "confirmat", "oprit", "alegere"))
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:24]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_REF].strip()
	return rez


def rute(baza, resource, rt=None, H=None, T=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class _Citeste(baza):
		lucru = None

		def render_GET(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class StareResource(_Citeste):
		"""GET /api/temporizatoare: numai citire."""
		lucru = staticmethod(lambda a: stare(rt, H))

	class JurnalResource(_Citeste):
		"""GET /api/temporizatoare-jurnal: numai citire."""
		lucru = staticmethod(lambda a: jurnal(a, rt=rt, H=H))

	class _Schimba(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class AdaugaResource(_Schimba):
		lucru = staticmethod(lambda a: adauga(a, rt=rt, H=H, T=T, nume_din_ghid=_numeDinGhid))

	class ModificaResource(_Schimba):
		lucru = staticmethod(lambda a: modifica(a, rt=rt, H=H))

	class StergeResource(_Schimba):
		lucru = staticmethod(lambda a: sterge(a, rt=rt, H=H, T=T))

	class OpresteResource(_Schimba):
		lucru = staticmethod(lambda a: opreste(a, rt=rt, H=H))

	class CurataResource(_Schimba):
		lucru = staticmethod(lambda a: curata(a, rt=rt, H=H))

	class GolesteResource(_Schimba):
		lucru = staticmethod(lambda a: golesteJurnal(a, rt=rt, H=H))

	class PaginaResource(resource.Resource):
		"""GET /temporizatoare: pagina „Înregistrări programate”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"temporizatoare": StareResource(),
		b"temporizatoare-adauga": AdaugaResource(),
		b"temporizatoare-modifica": ModificaResource(),
		b"temporizatoare-sterge": StergeResource(),
		b"temporizatoare-opreste": OpresteResource(),
		b"temporizatoare-curata": CurataResource(),
		b"temporizatoare-jurnal": JurnalResource(),
		b"temporizatoare-jurnal-goleste": GolesteResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /limbi si /ceas."""
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
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml, cu numele intrarii din meniu, tradus); modulul incarcat
	singur, fara pachet (probele de pe PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("timer_edit"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Înregistrări programate</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .loc{font-size:1rem;line-height:1.45;margin:0;}
  .loc.problema{color:#ffd27a;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .gol{font-size:1rem;line-height:1.5;margin:4px 0;}
  .temp{border-bottom:1px solid var(--bordura);padding:10px 0;display:grid;grid-template-columns:1fr auto;gap:8px 12px;align-items:start;}
  .temp:last-of-type{border-bottom:0;}
  .temp .titlu{font-weight:600;font-size:1rem;word-break:break-word;}
  .temp .cand{font-size:.92rem;margin-top:2px;}
  .temp .det{color:var(--text-slab);font-size:.85rem;margin-top:4px;white-space:pre-line;line-height:1.4;}
  .temp .nupoate{color:#ffd27a;font-size:.9rem;margin-top:4px;}
  .semn{display:inline-block;font-size:.75rem;padding:2px 8px;border-radius:10px;background:#242a33;margin-left:6px;vertical-align:middle;}
  .semn.merge{background:var(--rosu);color:#fff;}
  .semn.oprita{background:#3a3f48;}
  .semn.gata{background:#2a3a30;}
  .semn.nupoate{background:#5a4210;color:#ffe2a8;}
  .actiuni{display:grid;grid-template-columns:1fr 1fr;gap:6px;align-content:start;}
  .alegeri{grid-column:1 / -1;display:flex;flex-wrap:wrap;gap:8px;}
  .jurnal{grid-column:1 / -1;background:#0f1216;border:1px solid var(--bordura);border-radius:8px;padding:10px 12px;}
  .jurnal .r{padding:4px 0;border-bottom:1px solid var(--bordura);}
  .jurnal .r:last-child{border-bottom:0;}
  .jurnal .ora{color:var(--text-slab);font-size:.8rem;margin-right:8px;}
  .jurnal .orig{color:var(--text-slab);font-size:.75rem;display:block;}
  label{display:block;font-size:.9rem;margin:0 0 4px;color:var(--text-slab);}
  .campuri{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
  .campuri .lat{grid-column:1 / -1;}
  .zile{display:flex;flex-wrap:wrap;gap:6px 14px;}
  .zile label{display:flex;align-items:center;gap:6px;color:var(--text);margin:0;min-height:44px;}
  .zile input{width:auto;min-height:0;}
  select,input{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button.rosu{background:var(--rosu);border-color:var(--rosu);color:#fff;}
  button.galben{background:var(--galben);border-color:var(--galben);color:#241d00;}
  button.albastru{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  a.buton{display:inline-block;margin-top:10px;color:var(--text);}
  a.buton.ascuns{display:none;}
  @media (max-width:560px){ .campuri{grid-template-columns:1fr;} .temp{grid-template-columns:1fr;} .actiuni{display:flex;flex-wrap:wrap;} }
</style>
</head>
<body>
<main>
<h1>Înregistrări programate</h1>
<p class="mesaj" id="incarcare">Se citește lista...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Unde se salvează</h2>
    <p class="loc" id="loc"></p>
    <p class="nota" id="locDetaliu"></p>
    <a class="buton ascuns" id="alegeLoc" href="/stocare">Alege locul înregistrărilor</a>
  </section>
  <section class="card">
    <h2>Lista</h2>
    <p class="gol ascuns" id="gol"></p>
    <div id="lista"></div>
    <p class="nota ascuns" id="ascunse"></p>
    <div class="butoane"><button type="button" class="albastru ascuns" id="curata">Șterge cele terminate</button></div>
  </section>
  <section class="card" id="formular">
    <h2 id="titluFormular">Adaugă o înregistrare</h2>
    <div class="campuri">
      <div><label for="fila">Lista</label><select id="fila"><option value="tv">TV</option><option value="radio">Radio</option></select></div>
      <div><label for="buchet">Grupul de canale</label><select id="buchet"></select></div>
      <div class="lat"><label for="canal">Canalul</label><select id="canal"></select></div>
      <div><label for="ce">Ce face</label><select id="ce"><option value="0">Înregistrează</option><option value="1">Doar schimbă canalul</option></select></div>
      <div><label for="repetare">Când</label><select id="repetare"><option value="o_data">O singură dată</option><option value="zilnic">În fiecare zi</option><option value="luni_vineri">De luni până vineri</option><option value="zile">În zilele alese</option></select></div>
      <div class="lat ascuns" id="randZile"><label>Zilele</label><div class="zile" id="zile"></div></div>
      <div><label for="zi" id="etichetaZi">Ziua</label><input type="date" id="zi"></div>
      <div><label for="inceput">Ora de început</label><input type="time" id="inceput"></div>
      <div id="randSfarsit"><label for="sfarsit">Ora de sfârșit</label><input type="time" id="sfarsit"></div>
      <div class="lat"><label for="nume">Numele (dacă îl lași gol, se ia din ghidul TV)</label><input type="text" id="nume" maxlength="120"></div>
      <div class="lat"><label for="descriere">Descrierea</label><input type="text" id="descriere" maxlength="120"></div>
      <div id="randDupa"><label for="dupa">După înregistrare</label><select id="dupa"><option value="automat">Revine cum era înainte</option><option value="nimic">Nu face nimic</option><option value="asteptare">Trece în așteptare</option><option value="oprire">Se oprește de tot</option></select></div>
      <div id="randLoc"><label for="locAles">Locul înregistrării</label><select id="locAles"></select></div>
      <div id="randDecodare" class="ascuns"><label for="decodare">Decriptarea</label><select id="decodare"><option value="acum">Decriptează acum</option><option value="maitarziu">Decodează mai târziu</option></select></div>
    </div>
    <div class="butoane"><button type="button" class="verde" id="adauga">Adaugă</button><button type="button" class="ascuns" id="renunta">Renunță</button></div>
    <p class="nota">Pe televizor poți alege și direct o emisiune din ghidul TV: acolo marginile de dinainte și de după se pun singure.</p>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Aceeași listă este pe televizor, la tasta TIMER sau în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var DATE = null;
var CANALE_INCARCATE = false;
var EDITEZ = null;
var PRIMA = true;
var ZILE = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"];
function $(id){ return document.getElementById(id); }
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
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function semn(t){
  var s = document.createElement("span"); s.className = "semn"; s.textContent = t.stare_text;
  if(t.stare === "inregistreaza" || t.stare === "comutat" || t.stare === "incepe"){ s.classList.add("merge"); }
  else if(t.stare === "oprita"){ s.classList.add("oprita"); }
  else if(t.stare === "terminata"){ s.classList.add("gata"); }
  else if(t.stare === "nu_poate"){ s.classList.add("nupoate"); }
  return s;
}
function buton(text, clasa, fn){
  var b = document.createElement("button"); b.type = "button"; b.className = clasa; b.textContent = text;
  b.addEventListener("click", fn); return b;
}
function arataJurnal(r, t){
  var vechi = r.querySelector(".jurnal");
  if(vechi){ vechi.remove(); return; }
  var j = document.createElement("div"); j.className = "jurnal"; j.textContent = "Se citește jurnalul...";
  r.appendChild(j);
  cerere("/api/temporizatoare-jurnal?id=" + t.id).then(function(d){
    j.textContent = "";
    if(!d.result){ j.textContent = d.message || ""; return; }
    if(d.gol){ j.textContent = d.gol; return; }
    (d.jurnal || []).forEach(function(x){
      var rr = document.createElement("div"); rr.className = "r";
      var o = document.createElement("span"); o.className = "ora"; o.textContent = x.ora;
      var tx = document.createElement("span"); tx.textContent = x.text;
      var og = document.createElement("span"); og.className = "orig"; og.textContent = x.original;
      rr.appendChild(o); rr.appendChild(tx); rr.appendChild(og); j.appendChild(rr);
    });
    j.appendChild(buton("Golește jurnalul", "albastru", function(){
      if(!confirm("Golești jurnalul înregistrării „" + (t.nume || t.canal) + "”?")){ return; }
      trimite("/api/temporizatoare-jurnal-goleste", {id: t.id, confirmat: "1"}).then(function(){ j.remove(); });
    }));
  }).catch(function(){ j.textContent = "Receptorul nu răspunde."; });
}
function arataAlegeri(r, t){
  var vechi = r.querySelector(".alegeri");
  if(vechi){ vechi.remove(); return; }
  var a = document.createElement("div"); a.className = "alegeri";
  (DATE.alegeri_repetata || []).forEach(function(x){
    a.appendChild(buton(x[0], "galben", function(){ trimite("/api/temporizatoare-opreste", {id: t.id, alegere: x[1]}); }));
  });
  a.appendChild(buton("Renunță", "", function(){ a.remove(); }));
  r.appendChild(a);
}
function arataLista(d){
  var loc = d.loc || {};
  $("loc").textContent = loc.text || "";
  $("loc").classList.toggle("problema", loc.citit && !loc.bun);
  $("locDetaliu").textContent = loc.detaliu || "";
  $("alegeLoc").classList.toggle("ascuns", !loc.alege);
  $("gol").textContent = d.gol || "";
  $("gol").classList.toggle("ascuns", !d.gol);
  $("curata").classList.toggle("ascuns", !d.are_terminate);
  $("ascunse").textContent = d.terminate_ascunse ? "Mai sunt " + d.terminate_ascunse + " înregistrări terminate, mai vechi. „Șterge cele terminate” le scoate pe toate." : "";
  $("ascunse").classList.toggle("ascuns", !d.terminate_ascunse);
  var c = $("lista"); c.textContent = "";
  (d.temporizatoare || []).forEach(function(t){
    var r = document.createElement("div"); r.className = "temp";
    var st = document.createElement("div");
    var ti = document.createElement("div"); ti.className = "titlu"; ti.textContent = (t.nume || t.canal) + (t.nume && t.canal ? " · " + t.canal : "");
    ti.appendChild(semn(t));
    var ca = document.createElement("div"); ca.className = "cand"; ca.textContent = t.cand;
    st.appendChild(ti); st.appendChild(ca);
    if(t.nu_poate){ var np = document.createElement("div"); np.className = "nupoate"; np.textContent = t.nu_poate; st.appendChild(np); }
    var de = document.createElement("div"); de.className = "det"; de.textContent = t.ce + (t.descriere_scurta ? "\\n" + t.descriere_scurta : "");
    st.appendChild(de);
    var ac = document.createElement("div"); ac.className = "actiuni";
    ac.appendChild(buton("Modifică", "", function(){ incepeModificarea(t); }));
    if(t.galben === "opreste"){ ac.appendChild(buton("Oprește", "galben", function(){ trimite("/api/temporizatoare-opreste", {id: t.id, oprit: "1"}); })); }
    if(t.galben === "porneste"){ ac.appendChild(buton("Pornește", "galben", function(){ trimite("/api/temporizatoare-opreste", {id: t.id, oprit: "0"}); })); }
    if(t.galben === "repetata"){ ac.appendChild(buton("Oprește...", "galben", function(){ arataAlegeri(r, t); })); }
    ac.appendChild(buton("Jurnalul", "", function(){ arataJurnal(r, t); }));
    ac.appendChild(buton("Șterge", "rosu", function(){
      if(!confirm("Ștergi înregistrarea programată „" + (t.nume || t.canal) + "”?")){ return; }
      trimite("/api/temporizatoare-sterge", {id: t.id, confirmat: "1"});
    }));
    r.appendChild(st); r.appendChild(ac); c.appendChild(r);
  });
}
function umpleLocuri(d, ales){
  var s = $("locAles"); s.textContent = "";
  var o = document.createElement("option"); o.value = ""; o.textContent = "Locul obișnuit"; s.appendChild(o);
  (d.locuri || []).forEach(function(x){ var p = document.createElement("option"); p.value = x; p.textContent = x; s.appendChild(p); });
  if(ales && (d.locuri || []).indexOf(ales) === -1){ var q = document.createElement("option"); q.value = ales; q.textContent = ales; s.appendChild(q); }
  s.value = ales || "";
}
function citeste(){
  return cerere("/api/temporizatoare").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi lista."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    DATE = d; arataLista(d);
    if(PRIMA){ PRIMA = false; oreImplicite(); umpleLocuri(d, ""); $("decodare").value = decodareImplicita(); arataCampuri(); }
    if(!CANALE_INCARCATE){ CANALE_INCARCATE = true; incarcaBuchete(true); }
    if(d.loc && !d.loc.citit){ setTimeout(citeste, 2000); }
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cale, valori){
  var q = new URLSearchParams();
  Object.keys(valori).forEach(function(k){ q.set(k, valori[k]); });
  mesaj("Se trimite...");
  return cerere(cale, "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.temporizatoare){ DATE = d; arataLista(d); }
    return d;
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
var CANAL_ACUM = null;
function incarcaBuchete(cuAcum){
  var fila = $("fila").value;
  var p = cuAcum ? cerere("/api/canale-acum").then(function(a){ CANAL_ACUM = a && a.ref; }).catch(function(){}) : Promise.resolve();
  return p.then(function(){ return cerere("/api/canale-buchete?fila=" + fila); }).then(function(d){
    var s = $("buchet"); s.textContent = "";
    if(!d.result){ mesaj(d.message || "Lista de canale nu s-a putut citi.", true); return; }
    (d.buchete || []).forEach(function(b){ var o = document.createElement("option"); o.value = b.id; o.textContent = b.nume + " (" + b.numar + ")"; s.appendChild(o); });
    s.value = d.ales;
    return incarcaCanale();
  });
}
function optiuneGoala(){
  var s = $("canal");
  var o = document.createElement("option"); o.value = "";
  o.textContent = EDITEZ ? EDITEZ.canal + " (rămâne)" : "Alege canalul";
  s.appendChild(o);
}
function incarcaCanale(){
  var s = $("canal"); s.textContent = "";
  optiuneGoala();
  var fila = $("fila").value, buchet = $("buchet").value;
  var grup = s;
  function pagina(deLa){
    return cerere("/api/canale-lista?fila=" + fila + "&buchet=" + encodeURIComponent(buchet) + "&de_la=" + deLa + "&cate=200").then(function(d){
      if(!d.result){ mesaj(d.message || "Lista de canale nu s-a putut citi.", true); return; }
      (d.randuri || []).forEach(function(r){
        if(r.m){ grup = document.createElement("optgroup"); grup.label = r.nume; s.appendChild(grup); return; }
        var o = document.createElement("option"); o.value = r.ref; o.textContent = (r.n ? r.n + ". " : "") + r.nume;
        (grup === s ? s : grup).appendChild(o);
        if(!EDITEZ && CANAL_ACUM && r.ref === CANAL_ACUM){ o.selected = true; }
      });
      if(!d.gata && deLa + 200 < 2000){ return pagina(deLa + 200); }
    });
  }
  return pagina(0);
}
function oreImplicite(){
  var i = (DATE && DATE.implicit) || {};
  $("zi").value = i.zi || ""; $("inceput").value = i.inceput || ""; $("sfarsit").value = i.sfarsit || "";
}
function zileAlese(lista){
  var c = $("zile"); c.textContent = "";
  ZILE.forEach(function(nume, i){
    var l = document.createElement("label"); var b = document.createElement("input"); b.type = "checkbox"; b.value = i;
    b.checked = lista.indexOf(i) !== -1; l.appendChild(b); l.appendChild(document.createTextNode(nume)); c.appendChild(l);
  });
}
function areDecodare(){ return !!(DATE && DATE.decodare && DATE.decodare.exista); }
function decodareImplicita(){ return (DATE && DATE.decodare && DATE.decodare.implicit) || "acum"; }
function arataCampuri(){
  var zap = $("ce").value === "1", rep = $("repetare").value;
  $("randDecodare").classList.toggle("ascuns", zap || !areDecodare());
  $("randSfarsit").classList.toggle("ascuns", zap);
  $("randDupa").classList.toggle("ascuns", zap);
  $("randLoc").classList.toggle("ascuns", zap);
  $("randZile").classList.toggle("ascuns", rep !== "zile");
  $("etichetaZi").textContent = rep === "o_data" ? "Ziua" : "Începe din ziua";
}
function incepeModificarea(t){
  EDITEZ = t;
  $("titluFormular").textContent = "Modifică „" + (t.nume || t.canal) + "”";
  $("adauga").textContent = "Salvează";
  $("renunta").classList.remove("ascuns");
  $("ce").value = t.doar_comuta ? "1" : "0";
  $("repetare").value = t.repetare; zileAlese(t.zile || []);
  // ziua si orele in ora receptorului (le da el), nu in fusul orar al browserului
  $("zi").value = t.formular.zi; $("inceput").value = t.formular.inceput; $("sfarsit").value = t.formular.sfarsit;
  $("nume").value = t.nume; $("descriere").value = t.descriere; $("dupa").value = t.dupa;
  $("decodare").value = t.decodare || "acum";
  umpleLocuri(DATE, t.loc);
  incarcaCanale(); arataCampuri();
  $("formular").scrollIntoView({behavior: "smooth"});
}
function gataModificarea(){
  EDITEZ = null;
  $("titluFormular").textContent = "Adaugă o înregistrare";
  $("adauga").textContent = "Adaugă";
  $("renunta").classList.add("ascuns");
  $("nume").value = ""; $("descriere").value = ""; $("repetare").value = "o_data"; $("ce").value = "0"; $("dupa").value = "automat";
  $("decodare").value = decodareImplicita();
  zileAlese([]); oreImplicite(); umpleLocuri(DATE, ""); incarcaCanale(); arataCampuri();
}
$("fila").addEventListener("change", function(){ incarcaBuchete(false); });
$("buchet").addEventListener("change", incarcaCanale);
$("ce").addEventListener("change", arataCampuri);
$("repetare").addEventListener("change", arataCampuri);
$("renunta").addEventListener("click", function(){ gataModificarea(); mesaj(""); });
$("adauga").addEventListener("click", function(){
  if(!EDITEZ && !$("canal").value){ mesaj("Alege canalul.", true); return; }
  if(!$("zi").value || !$("inceput").value){ mesaj("Alege ziua și ora de început.", true); return; }
  var zap = $("ce").value === "1";
  if(!zap && !$("sfarsit").value){ mesaj("Alege ora de sfârșit.", true); return; }
  var zile = [];
  Array.prototype.forEach.call($("zile").querySelectorAll("input"), function(b){ if(b.checked){ zile.push(b.value); } });
  if($("repetare").value === "zile" && !zile.length){ mesaj("Alege cel puțin o zi.", true); return; }
  var v = {zi: $("zi").value, inceput: $("inceput").value, nume: $("nume").value, descriere: $("descriere").value,
    doar_comuta: $("ce").value, repetare: $("repetare").value, zile: zile.join(",")};
  if(!zap){ v.sfarsit = $("sfarsit").value; v.dupa = $("dupa").value; if($("locAles").value){ v.loc = $("locAles").value; } }
  if(!zap && areDecodare()){ v.decodare = $("decodare").value; }
  if($("canal").value){ v.ref = $("canal").value; }
  if(EDITEZ){
    v.id = EDITEZ.id;
    trimite("/api/temporizatoare-modifica", v).then(function(d){ if(d && d.result){ gataModificarea(); } });
  } else {
    trimite("/api/temporizatoare-adauga", v).then(function(d){ if(d && d.result){ $("nume").value = ""; $("descriere").value = ""; } });
  }
});
$("curata").addEventListener("click", function(){
  if(!confirm("Ștergi din listă înregistrările terminate?")){ return; }
  trimite("/api/temporizatoare-curata", {confirmat: "1"});
});
zileAlese([]); arataCampuri();
citeste();
setInterval(function(){ if(!document.hidden && !EDITEZ){ citeste(); } }, 30000);
document.addEventListener("visibilitychange", function(){ if(!document.hidden && !EDITEZ){ citeste(); } });
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Înregistrări programate"),
		N_("Se citește lista..."),
		N_("Unde se salvează"),
		N_("Alege locul înregistrărilor"),
		N_("Lista"),
		N_("Șterge cele terminate"),
		N_("Adaugă o înregistrare"),
		N_("Radio"),
		N_("Grupul de canale"),
		N_("Canalul"),
		N_("Ce face"),
		N_("Înregistrează"),
		N_("Doar schimbă canalul"),
		N_("Când"),
		N_("O singură dată"),
		N_("În fiecare zi"),
		N_("De luni până vineri"),
		N_("În zilele alese"),
		N_("Zilele"),
		N_("Ziua"),
		N_("Ora de început"),
		N_("Ora de sfârșit"),
		N_("Numele (dacă îl lași gol, se ia din ghidul TV)"),
		N_("Descrierea"),
		N_("După înregistrare"),
		N_("Revine cum era înainte"),
		N_("Nu face nimic"),
		N_("Trece în așteptare"),
		N_("Se oprește de tot"),
		N_("Locul înregistrării"),
		N_("Decriptarea"),
		N_("Decriptează acum"),
		N_("Decodează mai târziu"),
		N_("Adaugă"),
		N_("Renunță"),
		N_("Pe televizor poți alege și direct o emisiune din ghidul TV: acolo marginile de dinainte și de "
			"după se pun singure."),
		N_("Aceeași listă este pe televizor, la tasta TIMER sau în __DRUM_MENIU__."),
	),
	"js": (
		N_("marți"),
		N_("sâmbătă"),
		N_("duminică"),
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se citește jurnalul..."),
		N_("Golește jurnalul"),
		N_("Golești jurnalul înregistrării „"),
		N_("Receptorul nu răspunde."),
		N_("Renunță"),
		N_("Mai sunt"),
		N_("înregistrări terminate, mai vechi. „Șterge cele terminate” le scoate pe toate."),
		N_("Modifică"),
		N_("Oprește"),
		N_("Pornește"),
		N_("Oprește..."),
		N_("Jurnalul"),
		N_("Șterge"),
		N_("Ștergi înregistrarea programată „"),
		N_("Locul obișnuit"),
		N_("Receptorul nu a putut citi lista."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("Lista de canale nu s-a putut citi."),
		N_("(rămâne)"),
		N_("Alege canalul"),
		N_("Ziua"),
		N_("Începe din ziua"),
		N_("Modifică „"),
		N_("Salvează"),
		N_("Adaugă o înregistrare"),
		N_("Adaugă"),
		N_("Alege canalul."),
		N_("Alege ziua și ora de început."),
		N_("Alege ora de sfârșit."),
		N_("Alege cel puțin o zi."),
		N_("Ștergi din listă înregistrările terminate?"),
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
