# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMeniuOrdine: ordinea si ascunderea intrarilor din meniurile receptorului (tasta MENU), aceeasi pentru televizor
# (Screens/Menu.py) si pentru interfata web (HdsWebControl/meniu_web.py: /meniu si fila Aranjeaza, /meniuri).
# Cerut pe LinuxSat (tamiciav7, 14.11.2026 20:03), dupa ordonarea pluginurilor din Extensii (EXD, hoolman).
#
# - Fiecare meniu are ordinea lui, dupa key-ul nodului <menu> din menu.xml (mainmenu, setup, gui_menu...): aceeasi
#   intrare pusa in doua meniuri (copie= din MST) se muta si se ascunde separat in fiecare.
# - O intrare e cunoscuta dupa entryID; intrarile fara entryID (randurile adaugate de MenuUpdater au "undefined") dupa
#   numele lor ("t:" + nume), ca ascunderea uneia sa nu le ascunda pe toate.
# - Ordinea salvata e lista cheilor in ordinea omului. O intrare noua (venita cu o actualizare sau cu un plugin) sta
#   dupa vecina ei de fabrica, nu la coada; fara ordine salvata ramane ordinea de fabrica (weight), nimic schimbat.
# - Randul "Cauta in meniu" (pus de Menu.py deasupra) nu intra aici: nu se muta si nu se ascunde.
# - Setarile: config.plugins.hdsmeniuri.ordine (JSON {meniu: [chei]}) si .ascunse (JSON {meniu: [chei]}), salvate pe
#   loc. Fara setari (probele de pe PC fara Components.config adevarat) totul ramane ca din fabrica.
# - "Arata intrarile ascunse" tine pana la repornirea interfetei (aratAscunse): intrarile ascunse apar in meniu cu
#   semnul lor, ca sa poata fi aratate din nou. Cautarea in meniu le gaseste oricum.

import json
import unicodedata

ID_CAUTARE = "hds_cauta_meniu"
MAX_CHEIE = 120
MAX_MENIURI = 200
MAX_INTRARI = 300

_SETARI = []
_STARE = {"arata": False}


def setari():
	"""config.plugins.hdsmeniuri (ordine, ascunse), facuta o singura data; None fara setari adevarate (probele)."""
	if _SETARI:
		return _SETARI[0]
	try:
		from Components.config import config, ConfigSubsection, ConfigText
		c = getattr(config.plugins, "hdsmeniuri", None)
		if c is None:
			c = ConfigSubsection()
			c.ordine = ConfigText(default="", fixed_size=False)
			c.ascunse = ConfigText(default="", fixed_size=False)
			config.plugins.hdsmeniuri = c
	except Exception:
		return None
	_SETARI.append(c)
	return c


def _citeste(element):
	try:
		d = json.loads(element.value or "{}")
	except (TypeError, ValueError, AttributeError):
		return {}
	if not isinstance(d, dict):
		return {}
	rez = {}
	for meniu, chei in list(d.items())[:MAX_MENIURI]:
		if isinstance(meniu, str) and isinstance(chei, list):
			rez[meniu] = [k for k in chei[:MAX_INTRARI] if isinstance(k, str) and 0 < len(k) <= MAX_CHEIE]
	return rez


def _scrie(element, d):
	d = dict((m, v) for m, v in d.items() if v)
	element.value = json.dumps(d, ensure_ascii=False, separators=(",", ":"), sort_keys=True) if d else ""
	element.save()


def _salveazaFisierul():
	try:
		from Components.config import configfile
		configfile.save()
	except Exception as eroare:
		print("[HdsMeniuOrdine] salvarea setarilor: %s" % eroare)


def _toate(fel):
	c = setari()
	if c is None:
		return {}
	return _citeste(getattr(c, fel))


def ordine(meniu):
	return list(_toate("ordine").get(meniu or "", []))


def ascunse(meniu):
	return set(_toate("ascunse").get(meniu or "", []))


def personalizat(meniu=None):
	"""Are meniul (sau oricare, cu None) o ordine sau intrari ascunse puse de om?"""
	o, a = _toate("ordine"), _toate("ascunse")
	if meniu is None:
		return bool(o or a)
	return bool(o.get(meniu) or a.get(meniu))


def cheieMeniu(nod):
	"""Cheia meniului: key-ul nodului <menu>, altfel <id val>, entryID sau titlul."""
	if nod is None:
		return ""
	cheie = nod.get("key")
	if not cheie:
		i = nod.find("id") if hasattr(nod, "find") else None
		cheie = (i.get("val") if i is not None else None) or nod.get("entryID") or nod.get("text") or ""
	return cheie[:MAX_CHEIE]


def cheieIntrare(entryID, nume=""):
	"""Cheia unei intrari: entryID, sau "t:" + numele cand nu are (MenuUpdater pune "undefined")."""
	if entryID and entryID != "undefined":
		return str(entryID)[:MAX_CHEIE]
	return ("t:" + (nume or ""))[:MAX_CHEIE]


def cheieTuplu(t):
	"""Cheia tuplului de meniu din Menu.py: (titlu, functie, entryID, greutate, titlu_simplu, stare, glif[, cheie]);
	a opta valoare o pune Menu._cuSemnAscuns (numele aratat are atunci semnul "ascunsa")."""
	if len(t) > 7 and t[7]:
		return t[7]
	return cheieIntrare(t[2] if len(t) > 2 else None, t[4] if len(t) > 4 else (t[0] if t else ""))


def ordoneaza(chei, salvata):
	"""Indicii lui `chei` (ordinea de fabrica) in ordinea omului: cele din `salvata` in ordinea ei; una noua sta imediat
	dupa vecina ei de fabrica (sau la inceput, daca nu are vecina in ordine)."""
	loc = dict((k, i) for i, k in enumerate(salvata))
	if not loc:
		return list(range(len(chei)))
	ranguri = []
	ultim = -1.0
	pas = 0
	for i, k in enumerate(chei):
		if k in loc:
			ultim = float(loc[k])
			pas = 0
			ranguri.append((ultim, 0, i))
		else:
			pas += 1
			ranguri.append((ultim, pas, i))
	ranguri.sort()
	return [r[2] for r in ranguri]


def numeTuplu(t):
	"""The name shown for a menu tuple of Menu.py (titlu_simplu, else titlu)."""
	if len(t) > 4 and isinstance(t[4], str) and t[4]:
		return t[4]
	return t[0] if t and isinstance(t[0], str) else ""


# 0.8.0 FX3: "Sortare automată A-Z" for every menu (Nu from the factory): the
# entries in alphabetical order of their shown name, in place of the person's order (kept, it comes back with Nu);
# hidden entries stay hidden. The same on TV (MENU in a menu) and on the web page /meniu (fila Aranjează).
def _sortare():
	c = setari()
	if c is None:
		return None
	if not hasattr(c, "sortare_az"):
		try:
			from Components.config import ConfigYesNo
			c.sortare_az = ConfigYesNo(default=False)
		except Exception:
			return None
	return c.sortare_az


def sortareAZ():
	e = _sortare()
	return bool(e is not None and e.value)


def seteazaSortareAZ(da):
	e = _sortare()
	if e is None:
		return False
	e.value = bool(da)
	e.save()
	_salveazaFisierul()
	return True


def ordineaAZ(nume):
	"""Indices of `nume` in alphabetical order (Unicode, without case and accents; equal names keep their order)."""
	return sorted(range(len(nume)), key=lambda i: (_cheieAlfabeticaExtensie(nume[i]), i))


def aplica(meniu, intrari, cheie=cheieTuplu, aratate=(), nume=numeTuplu):
	"""(intrarile in ordinea omului, lista lui ascunsa_sau_nu pentru fiecare). Fara "Arata intrarile ascunse" si in
	afara de cele din `aratate`, intrarile ascunse lipsesc din prima lista. Cu Sortare automata A-Z, ordinea e dupa
	nume (nume(x) = numele aratat)."""
	chei = [cheie(x) for x in intrari]
	if sortareAZ():
		ordinea = ordineaAZ([nume(x) for x in intrari])
	else:
		ordinea = ordoneaza(chei, ordine(meniu))
	asc = ascunse(meniu)
	arata = aratAscunse()
	rez, semne = [], []
	for i in ordinea:
		k = chei[i]
		e_ascunsa = k in asc
		if e_ascunsa and not arata and k not in aratate:
			continue
		rez.append(intrari[i])
		semne.append(e_ascunsa)
	return rez, semne


def salveazaOrdinea(meniu, chei_noi):
	"""Ordinea noua a meniului (cheile in ordinea vazuta). Cheile din ordinea veche care nu se vad acum (ascunse) isi
	pastreaza locul dupa vecina lor de dinainte."""
	if setari() is None or not meniu:
		return False
	toate = _toate("ordine")
	veche = toate.get(meniu, [])
	noua = [k for k in chei_noi if k and k != ID_CAUTARE]
	vazute = set(noua)
	for i, k in enumerate(veche):
		if k in vazute:
			continue
		poz = 0
		for j in range(i - 1, -1, -1):
			if veche[j] in noua:
				poz = noua.index(veche[j]) + 1
				break
		noua.insert(poz, k)
		vazute.add(k)
	toate[meniu] = noua[:MAX_INTRARI]
	_scrie(setari().ordine, toate)
	_salveazaFisierul()
	return True


def muta(meniu, chei, cheie_, pas):
	"""Muta intrarea `cheie_` cu `pas` locuri intre `chei` (ordinea vazuta acum) si salveaza. Intoarce lista noua,
	sau None cand nu se poate (margine, cheie necunoscuta, fara setari). pas mare = pana la capat."""
	chei = [k for k in chei if k != ID_CAUTARE]
	if cheie_ not in chei:
		return None
	i = chei.index(cheie_)
	j = max(0, min(len(chei) - 1, i + pas))
	if i == j:
		return None
	chei.insert(j, chei.pop(i))
	if not salveazaOrdinea(meniu, chei):
		return None
	return chei


def ascunde(meniu, cheie_, da=True):
	c = setari()
	if c is None or not meniu or not cheie_ or cheie_ == ID_CAUTARE:
		return False
	toate = _toate("ascunse")
	lista = [k for k in toate.get(meniu, []) if k != cheie_]
	if da:
		lista.append(cheie_)
	toate[meniu] = lista[:MAX_INTRARI]
	_scrie(c.ascunse, toate)
	_salveazaFisierul()
	return True


def fabrica(meniu=None):
	"""Ordinea din fabrica si nimic ascuns: pentru un meniu, sau pentru toate cu None."""
	c = setari()
	if c is None:
		return False
	for fel in ("ordine", "ascunse"):
		toate = _toate(fel)
		if meniu is None:
			toate = {}
		else:
			toate.pop(meniu, None)
		_scrie(getattr(c, fel), toate)
	_salveazaFisierul()
	return True


def aratAscunse():
	return bool(_STARE["arata"])


def comutaAratAscunse(da=None):
	_STARE["arata"] = (not _STARE["arata"]) if da is None else bool(da)
	return _STARE["arata"]


def nrAscunse(meniu, chei=None):
	"""Cate intrari ale meniului sunt ascunse (numai dintre `chei`, cand e dat: cele care exista acum)."""
	a = ascunse(meniu)
	if chei is not None:
		a = a & set(chei)
	return len(a)


def _configSortareExtensii(lucru):
	"""Completeaza setarile existente, fara sa atinga ordinea manuala."""
	c = lucru.configExtensii()
	if c is None:
		return None
	if not hasattr(c, 'sortare_az'):
		try:
			from Components.config import ConfigYesNo
			c.sortare_az = ConfigYesNo(default=False)
		except ImportError:
			return None
	return c.sortare_az


def sortareExtensii(lucru):
	e = _configSortareExtensii(lucru)
	return bool(e.value) if e is not None else False


def identitateExtensie(lucru, rand, pluginuri):
	"""Identitatea intrarii; ordinea si ascunderea raman pe dosarul pluginului."""
	id_ = lucru.idRand(rand)
	if not id_ or rand[0] != 'plugin':
		return id_
	vecini = [p for p in pluginuri if lucru.idPlugin(getattr(p, 'path', '')) == id_]
	if len(vecini) <= 1:
		return id_
	def semn(p):
		f = getattr(p, 'fnc', None)
		if isinstance(f, dict):
			f = f.get(2)
		return (str(getattr(p, 'name', '') or ''), str(getattr(p, 'description', '') or ''),
			getattr(f, '__module__', ''), getattr(f, '__qualname__', ''))
	s = semn(rand[1])
	# Identical descriptors still need distinct rows during this inventory's life.
	sufix = ':%x' % id(rand[1]) if sum(semn(p) == s for p in vecini) > 1 else ''
	return id_ + ':' + json.dumps(s, ensure_ascii=True, separators=(',', ':')) + sufix


def _scrieSortareExtensii(cale, da, scrie):
	"""Worker: schimba numai cheia proprie, atomic, apoi verifica octetii de pe disc."""
	exista = True
	try:
		with open(cale, 'rb') as f:
			vechi = f.read()
	except FileNotFoundError:
		vechi = b''
		exista = False
	cheie = b'config.plugins.hdsextensii.sortare_az='
	text = b''.join(r for r in vechi.splitlines(keepends=True) if not r.startswith(cheie))
	if da:
		if text and not text.endswith(b'\n'):
			text += b'\n'
		text += cheie + b'true\n'
	ok = True
	if not exista or text != vechi:
		ok = scrie(cale, text)
	try:
		with open(cale, 'rb') as f:
			citit = f.read()
	except FileNotFoundError:
		return False, ''
	return bool(ok and citit == text), citit.decode('utf-8', 'surrogateescape')


def _cacheSortareExtensii(cale, functie, *args):
	"""Worker: intoarce si textul citit, fara obiecte config."""
	try:
		ok = functie(*args)
	except Exception:
		ok = False
	try:
		with open(cale, 'rb') as f:
			text = f.read().decode('utf-8', 'surrogateescape')
	except FileNotFoundError:
		text = ''
	except OSError:
		return False, None
	return ok, text


def salveazaSortareExtensii(lucru, da):
	"""Intoarce Deferred(bool); config numai pe main, IO numai pe worker."""
	from twisted.internet.defer import Deferred, succeed
	from twisted.internet.threads import deferToThread
	from Components import config as C
	e = _configSortareExtensii(lucru)
	if e is None:
		return succeed(False)
	da = bool(da)
	tranzactie = None
	cache = C.configfile._scris
	try:
		if C._amanaScriereSetari(C.configfile.CONFIG_FILE):
			return succeed(False)
		tranzactie = C.TranzactieSetari()
		cale = C.configfile.CONFIG_FILE
		d = deferToThread(tranzactie.ruleaza, _scrieSortareExtensii, cale, da, C._scrieSigur)
	except Exception:
		if tranzactie is not None:
			tranzactie.inchide(fortat=True)
		return succeed(False)
	rez = Deferred()
	def confirmaCache(text):
		nonlocal cache
		if text is not None:
			cache = text
		if cache is not None:
			C.configfile._scris = cache
			# Same verified lines in pickle order avoid a redundant heartbeat write.
			# Keep disk's channel values and never hide a saved RAM change.
			try:
				ram = C._canalDinBaza(C.config.pickle(), cache)
				def valori(t):
					return sorted(r for r in t.split('\n') if r and not r.startswith('#'))
				if valori(ram) == valori(cache):
					C.configfile._scris = ram
			except Exception:
				pass
	def termina(ok):
		# Other saves made during IO are flushed from a fresh snapshot on main.
		try:
			cereri = tranzactie.preia()
			if cereri:
				def confirma(r):
					_, text = r
					confirmaCache(text)
					termina(ok)
				def esec(_f):
					# Saved RAM stays queued for the ordinary settings heartbeat.
					confirmaCache(None)
					tranzactie.inchide(fortat=True)
					rez.callback(ok)
				deferToThread(_cacheSortareExtensii, cale, tranzactie.termina, cereri).addCallbacks(confirma, esec)
				return
			tranzactie.inchide()
		except Exception:
			tranzactie.inchide(fortat=True)
		rez.callback(ok)
	def gata(r):
		ok, text = r
		if ok:
			e.value = da
			e.save()
		confirmaCache(text)
		termina(bool(ok))
	def esec(_f):
		confirmaCache(None)
		termina(False)
	d.addCallbacks(gata, esec)
	return rez


def _cheieAlfabeticaExtensie(nume):
	"""Comparare Unicode fara diferente de majuscule, cu accente secundare, fara locale."""
	nume = unicodedata.normalize('NFKD', (nume or '').casefold())
	baza = ''.join(c for c in nume if not unicodedata.combining(c))
	return baza, nume


def aplicaSortareExtensii(lucru, randuri, fila, az=None):
	"""Sorteaza doar locurile pluginurilor obisnuite; actualizarile si restul raman."""
	if fila != 'instalate' or not (sortareExtensii(lucru) if az is None else az):
		return randuri
	locuri = [i for i, r in enumerate(randuri) if r[0] == 'plugin' and not lucru._areActualizare(r)]
	ordonate = sorted((randuri[i] for i in locuri), key=lambda r: _cheieAlfabeticaExtensie(r[1].name))
	rez = list(randuri)
	for i, r in zip(locuri, ordonate):
		rez[i] = r
	return rez
