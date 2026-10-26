# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# cautare_web.py: „Căutare canale” in interfata web (HdsWebControl), perechea ecranului de pe televizor.
#
# Pe televizor, cautarea de canale (Screens/HdsCautareCanale.py, din lista de canale) are numele si randurile de
# filtre pe doua coloane, cu randurile pistelor: „Are” (teletext, subtitrari DVB, subtitrari teletext, HbbTV), „Format
# sunet”, „Sunet” (mono, stereo, multicanal), „Piste sunet”, „Limbă sunet” si „Subtitrare”. Aici sunt aceleasi randuri,
# in aceleasi doua coloane pe un ecran lat, cu aceleasi reguli (in acelasi rand SAU, intre randuri SI; cu numai Radio /
# DAB+ alese in „Tip”, randurile imaginii se ascund), plus pistele stiute ale fiecarui canal gasit si „Actualizeaza
# pistele”.
#
# O SINGURA LOGICA: indexul vine din Screens/HdsCautareCanale.index_cu_piste() (Components/HdsIndexCanale.py cu
# masuratorile si baza pistelor din Components/HdsPisteCanale.py), exact ce foloseste ecranul; trecerea prin canale e
# aceeasi (porneste_actualizare, cu ecranul de progres pe televizor si aceeasi intrebare cand antena are motor).
#
# Rute (toate prin poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat;
# ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/cautare-canale?text=..&tip=tv,radio&rez=..&acces=..&sistem=..&cod=..&poz=192,cablu&are=ttx,hbbtv
#        &fsunet=ac3,eac3&msunet=multi&psunet=2,3&lsunet=ron&lsub=eng&max=200
#                                                         randurile de filtre (cu numarul de canale) si canalele gasite
#   GET  /api/cautare-canale?<aceleasi filtre>&refs=1     referintele tuturor canalelor gasite (cel mult
#        vezi_live_web.MAX_EXPORT), pentru playlistul listei
#   POST /api/cautare-actualizeaza?fel=gasite|fara|toate&<aceleasi filtre>[&confirmat=1][&de_la_capat=1]
#        fara confirmat: intrebarea (durata, motorul; „Continui de unde a rămas?” cand ultima trecere s-a oprit in
#        ultimele 24 de ore, ca pe televizor); cu confirmat=1: porneste trecerea pe televizor (continuata, afara de
#        de_la_capat=1)
#   GET  /api/cautare-actualizeaza-stare                  starea trecerii (transponderul, canalele citite) sau ultima
#   POST /api/cautare-actualizeaza-opreste                opreste trecerea si revine la canalul de dinainte
#   GET  /api/istoric-semnal, POST /api/istoric-semnal-sterge  istoricul semnalului pe pozitii (Components/
#        HdsIstoricSemnal.py): pozitiile prinse, ultimul semnal, zilele, calitatea; stergerea lui. La Actualizeaza,
#        intrebarea are neprinse (pozitiile fara semnal niciodata); confirmat=1 cu neprinse=incearca le incearca,
#        altfel (neprinse=lasa sau nimic) se lasa, ca pe televizor
#   POST /api/cautare-actualizeaza-sari                   „Sari peste satelitul acesta” (GALBEN pe televizor): lasa
#        transponderele ramase de pe pozitia de acum si trece la urmatoarea
#   POST /api/cautare-culegere?mod=oprita|canal|transponder   culegerea pistelor la vizionare (aceeasi setare ca pe
#        televizor, config.usage.hds_culegere_piste, Components/HdsPisteCanale.py)
#   GET  /cautare                                         pagina
# Canalul gasit se porneste pe televizor cu /api/zap (aceeasi poarta).
#
# VEZI LIVE SI PLAYLISTURI, ca in pagina /canale si cu acelasi cod (vezi_live_web.py si aparate_web.py, puse in pagina
# la servire): fiecare canal gasit are "Vezi live" (fereastra cu playerul comun /tv/player.js; un canal pe care
# transmisia nu-l poate lua fara televizor muta televizorul prin /api/zap, ca "Porneste pe televizor", apoi imaginea
# urmeaza televizorul; mesajele pentru criptate si pentru eroarea de decodare sunt ale playerului), cu "Descarca
# playlist (M3U)" al canalului sub imagine. "Exporta playlist (M3U)" ia toate canalele gasite (refs=1) si cere fisierul
# la POST /api/tv-m3u. "Adresa fixa pentru un aparat" face din cautarea de acum sursa "filtru" a unui aparat
# (aparate_web.sursaDin), cand se potriveste (aparat_din). Pagina are politica continutului paginii /tv (tv_web.CSP_TV).
# RANDURILE CARE ARATA LA FEL (acelasi nume si aceleasi semne, de pilda acelasi canal pe trei SID-uri ale aceluiasi
# transponder): "deosebire" spune ce le deosebeste (frecventa si polarizarea, furnizorul sau SID-ul;
# HdsIndexCanale.deosebiri), pe canalele aratate.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (reactorul e bucla enigma2), apelurile sunt scurte si
# directe. Indexul nu se face aici: vine din memorie (HdsCautareCanale.index_pentru_web); cand inca nu exista, se
# pregateste in fundal si raspunsul are "pregatire": true (pagina intreaba din nou peste putin). Fisierul nu importa
# nimic din enigma2 la incarcare: probele de pe PC dau un furnizor fals (M).
#
# Numerele de langa optiuni: cate canale ar ramane cu optiunea bifata, tinand cont de celelalte randuri alese (in
# acelasi rand optiunile se aduna cu „sau”), ca filtrele de pe televizor si pagina Canale (HdsIndexCanale.Index.
# numara_fatetat), numai printre canalele care se potrivesc cu numele cautat; fara nimic ales si fara text, numerele
# de pe tot indexul. O optiune cu 0 se vede, estompata.
#
# Memoria paginii (ca memoria cautarii de pe televizor): numele cautat si filtrele stau in adresa (dupa #, deci nu
# ajung la receptor si nu se amesteca cu ?token=) si in localStorage-ul browserului; la o incarcare noua (telefonul
# care a descarcat fila din fundal, Inapoi la panou si iar Cautare) pagina cere aceleasi filtre. Canalul pornit din
# pagina ramane marcat in lista, iar la incarcare lista se deruleaza la el. „Șterge filtrele” goleste si memoria.

MAX_TEXT = 40
MAX_REZULTATE = 300
IMPLICIT_REZULTATE = 200
FELURI_ACTUALIZARE = ("gasite", "fara", "toate")
# ce arata un rand (campurile din _canal): doua randuri cu aceleasi valori arata la fel (pune_deosebiri)
VIZIBIL = ("nume", "pozitie", "tip", "ansamblu", "rez", "cod", "sunet", "acces")


def N_(text):
	"""marcheaza textul pentru xgettext (po/Makefile.am --keyword=N_); traducerea se face la folosire, cu _t"""
	return text


# textele noi ale paginii, traduse la servire (__TEXTE__ in script, __T_<cheie>__ in HTML)
TEXTE = {
	"aparat_radio": N_("Un aparat primește numai canale TV, iar printre canalele găsite sunt și posturi de radio. Alege TV "
		"la rândul Tip."),
	"export_titlu": N_("Canalele găsite acum, ca playlist pentru un player din casă"),
}


def _vecin(nume):
	"""Un modul din acelasi dosar (vezi_live_web, aparate_web); pe PC, cand fisierul e incarcat singur, din cale."""
	import importlib
	import sys
	try:
		return importlib.import_module("." + nume, __package__) if __package__ else _dinCale(nume, sys)
	except ImportError:
		return _dinCale(nume, sys)


def _dinCale(nume, sys):
	import importlib.util
	import os
	if nume in sys.modules:
		return sys.modules[nume]
	spec = importlib.util.spec_from_file_location(nume, os.path.join(os.path.dirname(os.path.abspath(__file__)),
		nume + ".py"))
	modul = importlib.util.module_from_spec(spec)
	sys.modules[nume] = modul
	spec.loader.exec_module(modul)
	return modul


class _Furnizor(object):
	"""Modulele adevarate ale imaginii, importate abia la prima cerere."""

	@property
	def X(self):
		from Components import HdsIndexCanale
		return HdsIndexCanale

	@property
	def P(self):
		from Components import HdsPisteCanale
		return HdsPisteCanale

	@property
	def S(self):
		from Screens import HdsCautareCanale
		return HdsCautareCanale

	@property
	def I(self):
		from Components import HdsIstoricSemnal
		return HdsIstoricSemnal

	def sesiune(self):
		from . import plugin
		return getattr(plugin, "_sesiune", None)


def _m(M=None):
	return M if M is not None else _Furnizor()


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _index(M):
	"""Indexul pentru pagina: din memorie, fara sa-l faca pe firul enigma2 (None cat se pregateste primul)."""
	f = getattr(M.S, "index_pentru_web", None)
	return f() if f is not None else M.S.index_cu_piste()


def _pregatire():
	return {"result": False, "pregatire": True, "message": _t("Se pregătește lista de canale…")}


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:24]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:400].strip()
	return rez


def selectie_din(argumente_, index, X):
	"""{grup: set(valori)} numai cu valorile care exista in index (o valoare necunoscuta se ignora); cu numai Radio /
	DAB+ in „Tip”, randurile imaginii (ascunse) nu filtreaza."""
	sel = dict((g, set()) for g in X.GRUPURI)
	for g in X.GRUPURI:
		text = argumente_.get(g)
		if not text:
			continue
		existente = dict((str(v), v) for v, _e, _n in index.optiuni.get(g, ()))
		for bucata in text.split(",")[:64]:
			v = existente.get(bucata.strip())
			if v is not None:
				sel[g].add(v)
	if _numai_radio(X, sel):
		for g in getattr(X, "GRUPURI_IMAGINE", ()):
			sel[g] = set()
	return sel


def _numai_radio(X, sel):
	f = getattr(X, "numai_radio", None)
	return bool(f and f(sel))


def _coloana(X, g):
	return "stanga" if g in getattr(X, "COLOANA_STANGA", ()) else "dreapta"


_FATETE = {}


def numere_fatetate(index, sel, text=""):
	"""{grup: {valoare: numar}} cu filtrele alese, printre canalele care se potrivesc cu textul cautat
	(Index.numara_fatetat pe Index.canale_pentru_text), sau None fara nimic ales si fara text; ultima numarare tinuta
	minte (aceeasi cerere de doua ori, de pilda pagina reincarcata)."""
	text = (text or "").strip()
	if not any(sel.values()) and not text:
		return None
	cheie = (id(index), index.masurari_marcaj[1], index.piste_aplicate, text.lower(),
		tuple(sorted((g, tuple(sorted(map(str, v)))) for g, v in sel.items() if v)))
	vechi = _FATETE.get("ultima")
	if vechi is not None and vechi[0] == cheie and vechi[1] is index:
		return vechi[2]
	rez = index.numara_fatetat(index.canale_pentru_text(text), sel)
	_FATETE["ultima"] = (cheie, index, rez)
	return rez


def _eticheta_tip(X, tip):
	f = getattr(X, "eticheta_tip", None)
	return f(tip) if f is not None else X.ETICHETA_TIP.get(tip, "")


def _canal(c, X, P, baza):
	rec = baza.inregistrare(c.cheie_mas) if c.cheie_mas else None
	piste = P.rezumat(rec) if rec else None
	if piste is None and "ttx" in c.are:
		piste = {"sunet": [], "dvb": [], "ttx": [], "teletext": True, "hbbtv": None, "data": 0}
	nume_afisat = getattr(c, "nume_afisat", None)
	sunet = []
	if hasattr(X, "eticheta_format_sunet"):
		sunet = [t for t in (X.eticheta_format_sunet(c), X.eticheta_mod_sunet(c)) if t]
	return {
		"nume": nume_afisat() if nume_afisat else c.nume,
		"fara_nume": bool(getattr(c, "fara_nume", False)),
		"ref": c.ref,
		"pozitie": c.eticheta_pozitie(),
		"tip": _eticheta_tip(X, c.tip),
		"rez": c.rez_eticheta,
		"cod": c.eticheta_cod(),
		"sunet": " ".join(sunet),
		"acces": c.eticheta_acces(),
		# posturile DAB+ / DVB-T2 din satelit: ansamblul (marcajul din buchet), ca pe televizor
		"ansamblu": getattr(c, "ansamblu", "") or "",
		"piste": piste,
	}


def pune_deosebiri(canale, randuri, X):
	"""In fiecare rand, "deosebire": ce il deosebeste de randurile care arata la fel (aceleasi campuri VIZIBIL:
	HdsIndexCanale.deosebiri, frecventa si polarizarea, furnizorul sau SID-ul); "" la celelalte."""
	f = getattr(X, "deosebiri", None)
	perechi = list(zip(canale, randuri))
	d = f(perechi, nume=lambda p: p[0].cheie, vizibil=lambda p: tuple(p[1].get(k) for k in VIZIBIL),
		canal=lambda p: p[0]) if f is not None else {}
	for p in perechi:
		p[1]["deosebire"] = d.get(id(p), "")


def eticheta_cautare(index, text, sel):
	"""Cautarea de acum pentru om, fara titlu: textul si filtrele alese ("canal+, H.265, 13,0E"); "" fara nimic."""
	parti = index.parti_titlu(sel) if hasattr(index, "parti_titlu") else []
	return ", ".join(([text] if text else []) + list(parti))


def refs_gasite(gasite, eticheta, X):
	"""GET /api/cautare-canale?...&refs=1: referintele canalelor gasite, fiecare o data, cel mult MAX_EXPORT (cat
	primeste un playlist), cu grupul si numele fisierului si cate canale, ca text; "nota" cand lista e taiata."""
	maxim = _vecin("vezi_live_web").MAX_EXPORT
	refs, vazute = [], set()
	for c in gasite:
		if c.ref and c.ref not in vazute:
			vazute.add(c.ref)
			refs.append(c.ref)
			if len(refs) >= maxim:
				break
	rez = {"result": True, "refs": refs, "total": len(gasite), "grup": _t("Căutare canale"),
		"eticheta": eticheta or _t("Căutare canale"), "numar": X.text_numar(len(refs))}
	if len(refs) >= maxim and len(gasite) > len(refs):
		rez["nota"] = _t("Playlistul are primele %s din %d găsite.") % (X.text_numar(len(refs)), len(gasite))
	return rez


def aparat_din(text, sel, gasite):
	"""Cautarea de acum ca sursa "filtru" a unui aparat din casa (aparate_web.sursaDin: lista "Toate canalele" TV a
	paginii /canale, cu acelasi text si aceleasi filtre). Se potriveste cand printre canalele gasite nu e niciun post de
	radio: un aparat primeste numai canale TV, deci altfel ar primi alta lista decat cea gasita."""
	filtre = dict((g, sorted(str(v) for v in valori)) for g, valori in sel.items() if valori)
	potrivit = bool(gasite) and not any(getattr(c, "radio", False) for c in gasite)
	return {"potrivit": potrivit, "buchet": "toate", "text": text, "filtre": filtre}


def _titlu(index, text, sel, X):
	if hasattr(X, "titlu_cautare") and hasattr(index, "parti_titlu"):
		# ca pe televizor: optiunile aceluiasi rand sub un singur prefix; in pagina titlul se poate rupe pe randuri
		return X.titlu_cautare(_t("Căutare canale"), text, index.parti_titlu(sel))
	active = ["„%s”" % text] if text else []
	for g in X.GRUPURI:
		for v, eticheta, _n in index.optiuni.get(g, ()):
			if v in sel[g]:
				active.append(index.eticheta_titlu(g, eticheta))
	return _t("Căutare canale") + (": " + ", ".join(active) if active else "")


def cauta(argumente_, M=None):
	"""GET /api/cautare-canale."""
	M = _m(M)
	X, P = M.X, M.P
	index = _index(M)
	if index is None:
		return _pregatire()
	text = (argumente_.get("text") or "")[:MAX_TEXT]
	sel = selectie_din(argumente_, index, X)
	try:
		maxim = max(1, min(MAX_REZULTATE, int(argumente_.get("max") or IMPLICIT_REZULTATE)))
	except ValueError:
		maxim = IMPLICIT_REZULTATE
	gasite = index.filtreaza(text, sel)
	eticheta = eticheta_cautare(index, text, sel)
	if argumente_.get("refs") == "1":
		return refs_gasite(gasite, eticheta, X)
	baza = P.baza()
	afisate = gasite[:maxim]
	randuri = [_canal(c, X, P, baza) for c in afisate]
	pune_deosebiri(afisate, randuri, X)
	grupuri = []
	vizibile = index.grupuri_vizibile(fara_imagine=True) if _numai_radio(X, sel) else index.grupuri_vizibile()
	fatete = numere_fatetate(index, sel, text)
	for g in vizibile:
		optiuni = []
		for v, e, n in index.optiuni.get(g, ()):
			if fatete is not None:
				n = fatete.get(g, {}).get(v, 0)
			optiuni.append({"v": str(v), "eticheta": e, "n": n, "ales": v in sel[g]})
		if not optiuni:
			continue
		grupuri.append({
			"g": g,
			"titlu": X.semnPiste(X.titlu(g)) if g in X.GRUPURI_PISTE else X.titlu(g),
			"piste": g in X.GRUPURI_PISTE,
			"coloana": _coloana(X, g),
			"ordine": X.GRUPURI.index(g),
			"optiuni": optiuni,
		})
	cu_piste = index.canale_cu_piste()
	return {
		"result": True,
		"titlu": _titlu(index, text, sel, X),
		"grupuri": grupuri,
		"total": len(gasite),
		"numar": X.text_numar(len(gasite)),
		"canale": randuri,
		"toate": len(index.canale),
		# textul si filtrele, pentru om (fereastra aparatului, numele playlistului) si sursa aparatului
		"eticheta": eticheta,
		"aparat": aparat_din(text, sel, gasite),
		"cu_piste": cu_piste,
		# ca indiciul de pe televizor („la 234 de canale din 1197”); pluralul romanesc din text_numar, nu din pagina;
		# la zero alta fraza, ca pe televizor
		"stiute": (_t("Pistele se știu la %s din %d.") % (X.text_numar(cu_piste), len(index.canale)) if cu_piste > 0 else
			_t("Pistele nu se știu încă la niciun canal din %d.") % len(index.canale)),
		# semnul cautarii dupa piste, ca pe televizor (HdsIndexCanale.STARE_PISTE)
		"buton_actualizeaza": X.semnPiste(_t("Actualizează pistele")),
		"nota": _t("Pistele (teletext, subtitrări, limbile și formatul sunetului, HbbTV) se află singure când te uiți la un "
			"canal, după alegerea de mai jos. Mono, stereo sau 5.1 se află din datele transmise de canal: din ghidul "
			"programelor, când îl trimite, la vizionare, și la „Actualizează pistele”, care trece pe televizor prin "
			"transpondere, pe rând. În același rând opțiunile se adună cu „sau”, între rânduri cu „și”; numerele de "
			"lângă opțiuni sunt ale felului ales la „Tip”."),
		"actualizat": getattr(baza, "actualizat", 0),
		"actualizare": M.S.stare_actualizare(),
		"culegere": culegere(M),
	}


def culegere(M=None):
	"""Setarea culegerii la vizionare: valoarea si alegerile, aceleasi ca randul de pe televizor."""
	P = _m(M).P
	return {"valoare": P.culegere(), "alegeri": [[v, t] for v, t in P.textCulegeri()]}


def seteaza_culegere(argumente_, M=None):
	"""POST /api/cautare-culegere?mod=...: pune si salveaza setarea; o valoare necunoscuta nu schimba nimic."""
	M = _m(M)
	if not M.P.seteaza_culegere(argumente_.get("mod") or ""):
		return {"result": False, "message": _t("Citirea pistelor se alege cu oprita, canal sau transponder. "
			"Nu s-a schimbat nimic."),
			"culegere": culegere(M)}
	return {"result": True, "message": _t("Salvat."), "culegere": culegere(M)}


def _canaleActualizare(argumente_, M):
	X = M.X
	index = _index(M)
	if index is None:
		return None, "pregatire"
	fel = argumente_.get("fel") or "fara"
	if fel not in FELURI_ACTUALIZARE:
		return None, fel
	toate = M.S.canale_de_citit(index.canale)
	if fel == "toate":
		return toate, fel
	if fel == "fara":
		return [c for c in toate if M.S.fara_piste(c)], fel
	sel = selectie_din(argumente_, index, X)
	return M.S.canale_de_citit(index.filtreaza((argumente_.get("text") or "")[:MAX_TEXT], sel)), fel


def actualizeaza(argumente_, M=None):
	"""POST /api/cautare-actualizeaza: fara confirmat = intrebarea; cu confirmat=1 = pornirea pe televizor."""
	M = _m(M)
	P = M.P
	canale, fel = _canaleActualizare(argumente_, M)
	if canale is None and fel == "pregatire":
		return _pregatire()
	if canale is None:
		return {"result": False, "message": _t("Felul se alege cu gasite, fara sau toate.")}
	grupuri = P.transpondere_din_canale(canale)
	if not grupuri:
		return {"result": False, "message": _t("Niciun canal de satelit, cablu sau terestru de citit.")}
	motor = P.are_motor()
	# reluarea (ca pe televizor, HdsCautareCanale._aleasActualizare): ultima trecere oprita in ultimele 24 de ore
	rel = None if argumente_.get("de_la_capat") == "1" else P.reluare(grupuri, P.citeste_stare())
	facute, inainte = None, 0
	if rel is not None:
		toate = len(grupuri)
		grupuri, inainte, facute = rel
		canale = [c for g in grupuri for c in g.canale]
	# pozitiile pe care receptorul n-a prins niciodata semnal (ca pe televizor, HdsCautareCanale._intreaba): lasate
	# (neprinse=lasa, si cand pagina nu trimite nimic), sau incercate (neprinse=incearca)
	neprinse = P.pozitii_neprinse(grupuri) if hasattr(P, "pozitii_neprinse") else []
	fara = P.fara_pozitii(grupuri, neprinse) if neprinse else grupuri
	if not fara:
		neprinse = []
	if argumente_.get("confirmat") != "1":
		rez = {"result": False, "confirmare": P.text_confirmare(grupuri, motor), "motor": motor,
			"transpondere": len(grupuri), "canale": len(canale)}
		if neprinse:
			rez["neprinse"] = P.text_neprinse(neprinse, fara, motor)
			rez["neprinse_n"] = len(neprinse)
		if rel is not None:
			rez["reluare"] = P.text_reluare(inainte, toate)
		return rez
	sesiune = M.sesiune()
	if sesiune is None:
		return {"result": False, "message": _t("Receptorul nu e gata (sesiunea enigma2 lipsește).")}
	kw = {}
	if neprinse and argumente_.get("neprinse") == "incearca":
		kw["neprinse"] = neprinse
	elif neprinse:
		grupuri, kw["lasate"] = fara, neprinse
		canale = [c for g in grupuri for c in g.canale]
	if facute:
		eroare = M.S.porneste_actualizare(sesiune, grupuri, motor, facute=facute, inainte=inainte, **kw)
	else:
		eroare = M.S.porneste_actualizare(sesiune, grupuri, motor, **kw)
	if eroare:
		return {"result": False, "message": eroare}
	n = len(grupuri)
	return {"result": True, "message": _t("Pornit pe televizor: %s, %s.") % (P.ngettext("%d transponder", "%d transpondere", n) % n,
		M.X.text_numar(len(canale))), "actualizare": M.S.stare_actualizare()}


def stare_actualizare(M=None):
	"""GET /api/cautare-actualizeaza-stare."""
	M = _m(M)
	stare = M.S.stare_actualizare()
	rez = {"result": True, "stare": stare}
	if stare and not stare.get("activ"):
		rez["text"] = M.P.text_rezultat(stare)
	return rez


def istoric_semnal(M=None):
	"""GET /api/istoric-semnal: pozitiile pe care acest receptor a prins semnal (Components/HdsIstoricSemnal.py), de la
	est la vest, cu ultimul semnal, zilele, calitatea cea mai buna si transponderele prinse."""
	M = _m(M)
	ist = M.I.istoric()
	pozitii = ist.rezumat()
	rez = {"result": True, "pozitii": pozitii, "transpondere": len(ist.tp), "numai_citire": bool(ist.numai_citire)}
	# pozitiile aduse din alta lista pe care receptorul n-a receptionat semnal (semnul din lista Sateliti)
	aduse = M.I.text_aduse(M.I.aduse_fara_semnal(list(M.I.origine().aduse()), ist))
	if aduse:
		rez["aduse"] = aduse
	return rez


def sterge_istoric(M=None):
	"""POST /api/istoric-semnal-sterge: istoricul uitat (de exemplu dupa ce setarile au venit de pe alt receptor)."""
	M = _m(M)
	if M.I.istoric().uita():
		return {"result": True, "message": _t("Istoricul semnalului a fost șters."), "pozitii": []}
	return {"result": False, "message": _t("Istoricul semnalului nu se poate scrie acum.")}


def opreste_actualizare(M=None):
	"""POST /api/cautare-actualizeaza-opreste."""
	M = _m(M)
	if M.S.opreste_actualizare():
		return {"result": True, "message": _t("Oprit. Receptorul revine la canalul de dinainte.")}
	return {"result": False, "message": _t("Nicio actualizare a pistelor nu merge acum.")}


def sari_pozitia(M=None):
	"""POST /api/cautare-actualizeaza-sari."""
	M = _m(M)
	pozitia = M.S.sari_pozitia_actualizare()
	if pozitia:
		return {"result": True, "message": _t("Sărit peste %s. Trec la poziția următoare.") % pozitia,
			"actualizare": M.S.stare_actualizare()}
	return {"result": False, "message": _t("Nicio actualizare a pistelor nu merge acum.")}


def rute(baza, resource, M=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class CautaResource(baza):
		"""GET /api/cautare-canale: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, cauta(argumente(request), M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare_actualizare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True

		def fa(self, a):
			raise NotImplementedError

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.fa(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class ActualizeazaResource(_Schimba):
		def fa(self, a):
			return actualizeaza(a, M)

	class OpresteResource(_Schimba):
		def fa(self, a):
			return opreste_actualizare(M)

	class SariResource(_Schimba):
		def fa(self, a):
			return sari_pozitia(M)

	class CulegereResource(_Schimba):
		def fa(self, a):
			return seteaza_culegere(a, M)

	class IstoricResource(baza):
		"""GET /api/istoric-semnal: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, istoric_semnal(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class IstoricStergeResource(_Schimba):
		def fa(self, a):
			return sterge_istoric(M)

	class PaginaResource(resource.Resource):
		"""GET /cautare: pagina „Căutare canale”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"cautare-canale": CautaResource(),
		b"cautare-actualizeaza": ActualizeazaResource(),
		b"cautare-actualizeaza-stare": StareResource(),
		b"cautare-actualizeaza-opreste": OpresteResource(),
		b"cautare-actualizeaza-sari": SariResource(),
		b"cautare-culegere": CulegereResource(),
		b"istoric-semnal": IstoricResource(),
		b"istoric-semnal-sterge": IstoricStergeResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /subtitrari: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
	neconectat primeste pagina de asociere. Pagina schimba ceva pe receptor, deci cu cookie primeste tokenul CSRF."""
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
	# playerul "Vezi live": aceeasi politica a continutului ca pagina /tv (scripturi de pe receptor, MediaSource)
	try:
		from . import tv_web
		request.setHeader(b"content-security-policy", tv_web.CSP_TV)
	except Exception as eroare:
		print("[HdsWebControl] cautare: politica playerului: %s" % eroare)
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def texte():
	"""{cheie: textul tradus in limba interfetei}"""
	return dict((k, _t(v)) for k, v in TEXTE.items())


def pagina_text(stil, config_pagina):
	"""Pagina cu bucatile comune (vezi_live_web, aparate_web) si textele traduse, inaintea datelor omului (configuratia
	paginii), ca un nume de browser sa nu poata fi luat drept loc de text."""
	import html
	import json
	pagina = _vecin("vezi_live_web").inPagina(_vecin("aparate_web").inPagina(_traducePagina(PAGINA)))
	tx = json.dumps(texte(), ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
	pagina = pagina.replace("__TEXTE__", tx)
	for k, v in texte().items():
		pagina = pagina.replace("__T_%s__" % k, html.escape(v, quote=True))
	return pagina.replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Căutare canale</title>
<style>__STIL_COMUN__
  main{max-width:1100px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 12px;overflow-wrap:anywhere;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px;margin:0 0 12px;}
  #text{width:100%;box-sizing:border-box;min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  #grupuri{display:grid;grid-template-columns:1fr;gap:0 20px;}
  .coloana{display:contents;}
  @media (min-width:900px){
    #grupuri{grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);}
    .coloana{display:block;}
    .coloana .grup:last-child{border-bottom:0;}
  }
  .grup{display:grid;grid-template-columns:110px 1fr;gap:8px;align-items:start;padding:6px 0;border-bottom:1px solid var(--bordura);}
  .canal .nume.fara{color:var(--text);font-weight:normal;font-style:italic;opacity:.85;}
  .grup .nume{color:var(--text-slab);padding-top:9px;font-size:.92rem;}
  .optiuni{display:flex;flex-wrap:wrap;gap:6px;}
  .optiuni button{min-height:36px;padding:6px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;font-size:.9rem;cursor:pointer;}
  .optiuni button.ales{background:#f5b83d;color:#10162a;border-color:#f5b83d;}
  .optiuni button small{opacity:.7;margin-left:6px;}
  .optiuni button.zero{opacity:.45;}
  .bara{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin:0 0 8px;}
  .numar{color:#f5b83d;font-weight:bold;}
  .butoane{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}
  .butoane button,.butoane select{min-height:40px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  .canal{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 12px;padding:10px 0;border-bottom:1px solid var(--bordura);}
  .canal:last-child{border-bottom:0;}
  .canal .nume{font-weight:bold;overflow-wrap:anywhere;}
  .canal .semne{color:var(--text-slab);font-size:.86rem;}
  .canal .piste{grid-column:1 / -1;color:var(--text-slab);font-size:.86rem;line-height:1.45;overflow-wrap:anywhere;}
  .canal button.porneste{min-height:40px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#1f771f;color:#fff;font:inherit;cursor:pointer;}
  /* butoanele randului: "Porneste pe televizor" si "Vezi live" (vezi_live_web.py), unul sub altul cand nu incap */
  .canal .actiuni{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;align-items:flex-start;}
  .canal .actiuni .ghid{min-height:40px;}
  .canal .deosebire{color:#f5b83d;font-weight:bold;}
  .lista-butoane{margin:0 0 8px;}
  .lista-butoane button.nu-merge{opacity:.65;}
  .canal.pornit{box-shadow:inset 4px 0 0 #f5b83d;padding-left:12px;background:rgba(245,184,61,.08);}
  .canal .acum{display:none;color:#f5b83d;font-size:.86rem;font-weight:bold;}
  .canal.pornit .acum{display:block;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:8px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .grup{grid-template-columns:1fr;} .grup .nume{padding-top:0;}
    .canal{grid-template-columns:minmax(0,1fr);} .canal .actiuni{justify-content:flex-start;} }
__APARATE_STIL__
__LIVE_STIL__
</style>
</head>
<body>
<main>
<h1 id="titlu">Căutare canale</h1>
<section class="card">
  <input id="text" type="search" maxlength="40" placeholder="Numele canalului (orice parte din nume)" autocomplete="off">
  <div id="grupuri"></div>
  <div class="butoane" style="margin-top:10px"><button type="button" id="sterge">Șterge filtrele</button></div>
</section>
<section class="card">
  <div class="bara">
    <span class="numar" id="numar">Se citește lista...</span>
    <span class="butoane">
      <select id="fel" aria-label="Ce canale">
        <option value="fara">canalele fără piste știute</option>
        <option value="gasite">canalele găsite acum</option>
        <option value="toate">toate canalele</option>
      </select>
      <button type="button" id="actualizeaza">Actualizează pistele</button>
      <button type="button" id="sari" class="ascuns">Sari peste satelitul acesta</button>
      <button type="button" id="opreste" class="ascuns">Oprește</button>
    </span>
  </div>
  <div class="butoane lista-butoane">
    <button type="button" id="exportM3u" title="__T_export_titlu__">__L_exporta__</button>
    <button type="button" id="aparatFix">__A_din_canale__</button>
  </div>
  <p class="nota" id="stiute"></p>
  <p class="mesaj" id="mesaj"></p>
  <div class="butoane ascuns" id="intrebare">
    <button type="button" id="da">Da, pornește</button>
    <button type="button" id="incearca" class="ascuns">Da, încearcă și pozițiile fără semnal</button>
    <button type="button" id="capat" class="ascuns">De la capăt</button>
    <button type="button" id="nu">Nu</button>
  </div>
  <div id="canale"></div>
</section>
<section class="card" id="istoric">
  <div class="bara">
    <span class="numar">Istoricul semnalului pe acest receptor</span>
    <span class="butoane"><button type="button" id="stergeIstoric">Șterge istoricul</button></span>
  </div>
  <p class="nota" id="istoricNota">Se citește istoricul...</p>
  <div id="istoricLista"></div>
</section>
<section class="card">
  <div class="bara">
    <label for="culegere">Citirea pistelor în timpul vizionării</label>
    <span class="butoane"><select id="culegere" aria-label="Citirea pistelor în timpul vizionării"></select></span>
  </div>
  <p class="mesaj" id="mesajCulegere"></p>
</section>
<p class="nota" id="nota">Pistele (teletext, subtitrări, limbile și formatul sunetului, HbbTV) se află singure când te uiți la un canal. Mono, stereo sau 5.1 se află din datele transmise de canal: din ghidul programelor, la vizionare, și la „Actualizează pistele”. În același rând opțiunile se adună cu „sau”, între rânduri cu „și”; numerele de lângă opțiuni sunt ale felului ales la „Tip”.</p>
</main>
__LIVE_DIALOG__
__APARATE_DIALOG__
<script src="/tv/player.js"></script>
<script>
var CFG = __CONFIG__;
var ALES = {};
var ceasText = null, ceasStare = null;
// memoria paginii: filtrele in adresa (#...) si in localStorage, canalul pornit de aici; vezi citesteMemoria
var MEM_FILTRE = "hds-cautare-filtre", MEM_PORNIT = "hds-cautare-pornit";
var pornit = "", deDerulat = false;
function $(id){ return document.getElementById(id); }
function memCiteste(cheie){ try { return localStorage.getItem(cheie) || ""; } catch(e){ return ""; } }
function memScrie(cheie, valoare){ try { if(valoare){ localStorage.setItem(cheie, valoare); } else { localStorage.removeItem(cheie); } } catch(e){} }
function citesteMemoria(){
  // intai adresa (o fila redeschisa sau un semn de carte), apoi browserul; valorile necunoscute le scoate receptorul
  var text = location.hash.length > 1 ? location.hash.slice(1) : memCiteste(MEM_FILTRE);
  pornit = memCiteste(MEM_PORNIT);
  deDerulat = !!pornit;
  if(!text){ return; }
  new URLSearchParams(text).forEach(function(v, k){
    if(k === "text"){ $("text").value = v.slice(0, 40); }
    else if(/^[a-z]{2,12}$/.test(k)){ ALES[k] = v.split(",").filter(function(x){ return x; }).slice(0, 64); }
  });
}
function tineMinte(){
  var q = filtre().toString();
  memScrie(MEM_FILTRE, q);
  try { history.replaceState(null, "", location.pathname + location.search + (q ? "#" + q : "")); } catch(e){}
}
function marcheazaPornit(){
  var rand = null;
  Array.prototype.forEach.call(document.querySelectorAll("#canale .canal"), function(r){
    var acesta = !!pornit && r.getAttribute("data-ref") === pornit;
    r.classList.toggle("pornit", acesta);
    if(acesta){ rand = r; }
  });
  return rand;
}
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
function filtre(){
  var q = new URLSearchParams();
  var t = $("text").value.trim();
  if(t){ q.set("text", t); }
  Object.keys(ALES).forEach(function(g){ if(ALES[g].length){ q.set(g, ALES[g].join(",")); } });
  return q;
}
function gol(e){ while(e.firstChild){ e.removeChild(e.firstChild); } }
function construiesteGrupuri(d){
  var tot = $("grupuri"); gol(tot);
  var coloane = {stanga: document.createElement("div"), dreapta: document.createElement("div")};
  coloane.stanga.className = "coloana"; coloane.dreapta.className = "coloana";
  tot.appendChild(coloane.stanga); tot.appendChild(coloane.dreapta);
  ALES = {};
  d.grupuri.forEach(function(g){
    var c = coloane[g.coloana] || coloane.dreapta;
    ALES[g.g] = [];
    var rand = document.createElement("div"); rand.className = "grup";
    // pe telefon (o coloana) randurile stau in ordinea de pe televizor (GRUPURI): sunetul impreuna
    if(typeof g.ordine === "number"){ rand.style.order = g.ordine; }
    var nume = document.createElement("div"); nume.className = "nume"; nume.textContent = g.titlu;
    var opt = document.createElement("div"); opt.className = "optiuni";
    g.optiuni.forEach(function(o){
      if(o.ales){ ALES[g.g].push(o.v); }
      // o optiune cu 0 (nu ar ramane niciun canal) se vede, estompata
      var b = document.createElement("button"); b.type = "button"; b.className = o.ales ? "ales" : (o.n === 0 ? "zero" : "");
      b.textContent = o.eticheta;
      var n = document.createElement("small"); n.textContent = "(" + o.n + ")"; b.appendChild(n);
      b.setAttribute("aria-pressed", o.ales ? "true" : "false");
      b.addEventListener("click", function(){
        var l = ALES[g.g], i = l.indexOf(o.v);
        if(i === -1){ l.push(o.v); } else { l.splice(i, 1); }
        cauta();
      });
      opt.appendChild(b);
    });
    rand.appendChild(nume); rand.appendChild(opt); c.appendChild(rand);
  });
}
function textPiste(p){
  if(!p){ return "Pistele nu se știu încă."; }
  var parti = [];
  if(p.sunet && p.sunet.length){ parti.push("Sunet: " + p.sunet.join(", ")); }
  if(p.dvb && p.dvb.length){ parti.push("Subtitrări DVB: " + p.dvb.join(", ")); }
  if(p.ttx && p.ttx.length){ parti.push("Subtitrări teletext: " + p.ttx.join(", ")); }
  if(p.teletext === true){ parti.push("Teletext"); } else if(p.teletext === false){ parti.push("fără teletext"); }
  if(p.hbbtv === true){ parti.push("HbbTV"); } else if(p.hbbtv === false){ parti.push("fără HbbTV"); }
  if(p.data){ parti.push("citite " + new Date(p.data * 1000).toLocaleDateString("ro-RO")); }
  return parti.join(" · ") || "Fără piste.";
}
function porneste(ref, buton){
  buton.disabled = true;
  var q = new URLSearchParams(); q.set("sRef", ref);
  cerere("/api/zap", "POST", q).then(function(d){
    mesaj(d.result ? "Canalul pornește pe televizor." : (d.message || "Nu a pornit."), !d.result);
    if(d.result){ pornit = ref; memScrie(MEM_PORNIT, ref); marcheazaPornit(); }
  })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); })
    .then(function(){ buton.disabled = false; });
}
function arataCanale(d){
  var c = $("canale"); gol(c);
  d.canale.forEach(function(k){
    var r = document.createElement("div"); r.className = "canal"; r.setAttribute("data-ref", k.ref);
    var st = document.createElement("div");
    var a = document.createElement("div"); a.className = "acum"; a.textContent = "Pornit pe televizor din această listă";
    st.appendChild(a);
    var n = document.createElement("div"); n.className = k.fara_nume ? "nume fara" : "nume"; n.textContent = k.nume;
    var s = document.createElement("div"); s.className = "semne";
    s.textContent = [k.pozitie, k.tip, k.ansamblu, k.rez, k.cod, k.sunet, k.acces].filter(function(x){ return x; }).join(" · ");
    if(k.deosebire){
      // ce il deosebeste de randurile care arata la fel (frecventa si polarizarea, furnizorul sau SID-ul)
      var dz = document.createElement("span"); dz.className = "deosebire"; dz.textContent = k.deosebire;
      if(s.textContent){ s.appendChild(document.createTextNode(" · ")); }
      s.appendChild(dz);
    }
    st.appendChild(n); st.appendChild(s);
    var act = document.createElement("div"); act.className = "actiuni";
    var b = document.createElement("button"); b.type = "button"; b.className = "porneste"; b.textContent = "Pornește pe televizor";
    b.addEventListener("click", function(){ porneste(k.ref, b); });
    act.appendChild(b);
    // imaginea live a canalului, in fereastra de pe pagina (playerul comun, ca in /canale); in titlul ferestrei si ce il
    // deosebeste de randurile care arata la fel
    act.appendChild(liveButon({ref: k.ref, nume: k.deosebire ? k.nume + " (" + k.deosebire + ")" : k.nume}, {mutaTv: mutaTv}));
    var p = document.createElement("div"); p.className = "piste"; p.textContent = textPiste(k.piste);
    r.appendChild(st); r.appendChild(act); r.appendChild(p); c.appendChild(r);
  });
  if(d.total > d.canale.length){
    var m = document.createElement("p"); m.className = "nota";
    m.textContent = "Se arată primele " + d.canale.length + ". Restrânge căutarea cu numele sau cu filtrele.";
    c.appendChild(m);
  }
  var rand = marcheazaPornit();
  if(deDerulat){
    // numai la prima lista dupa incarcare: canalul pornit de aici la vedere (pe telefon, la mijloc)
    deDerulat = false;
    if(rand){ try { rand.scrollIntoView({block: "center"}); } catch(e){ rand.scrollIntoView(); } }
  }
}
function arataCulegere(c){
  if(!c){ return; }
  var s = $("culegere"); gol(s);
  c.alegeri.forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
  s.value = c.valoare;
}
function arata(d){
  ULTIM = d;
  $("exportM3u").disabled = !d.total;
  // cautarea de acum nu se poate da unui aparat (are si posturi de radio): butonul ramane, cu motivul
  $("aparatFix").classList.toggle("nu-merge", !(d.aparat && d.aparat.potrivit));
  $("aparatFix").title = d.aparat && d.aparat.potrivit ? "" : TX.aparat_radio;
  arataCulegere(d.culegere);
  $("titlu").textContent = d.titlu;
  $("numar").textContent = d.numar;
  $("stiute").textContent = d.stiute || "";
  if(d.nota){ $("nota").textContent = d.nota; }
  if(d.buton_actualizeaza){ $("actualizeaza").textContent = d.buton_actualizeaza; }
  construiesteGrupuri(d);
  arataCanale(d);
  arataActualizare(d.actualizare);
}
function cauta(){
  cerere("/api/cautare-canale?" + filtre().toString()).then(function(d){
    if(d.pregatire){ $("numar").textContent = d.message; clearTimeout(ceasText); ceasText = setTimeout(cauta, 800); return; }
    if(!d.result){ $("numar").textContent = d.message || "Lista nu s-a putut citi."; return; }
    arata(d);
    // dupa raspuns: ALES are numai valorile pe care receptorul le-a recunoscut
    tineMinte();
  }).catch(function(){ $("numar").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function arataActualizare(s){
  var activ = !!(s && s.activ);
  $("opreste").classList.toggle("ascuns", !activ);
  $("sari").classList.toggle("ascuns", !(activ && s.poate_sari && s.pozitie));
  $("sari").textContent = s && s.satelit === false && s.pozitie ? "Sari peste " + s.pozitie : "Sari peste satelitul acesta";
  $("actualizeaza").disabled = activ;
  if(activ){
    // "antena se roteste" numai cand receptorul are dovada (s.rotire); altfel, dupa comanda de mutare, asteptarea
    // semnalului cu secundele ramase, ca pe televizor
    mesaj("Se citesc pistele pe televizor: transponderul " + s.pas + " din " + s.total + (s.rotire && s.pozitie ? " · antena se rotește spre " + s.pozitie : (s.pozitie ? " · " + s.pozitie : "") + (s.astept_semnal ? " · aștept semnal" + (s.frecventa ? " pe " + s.frecventa : "") + " (încă " + s.semnal_ramas_s + " s)" : (s.canal ? " · " + s.canal : ""))) + " · citite: " + s.citite + textRamas(s.ramas_s));
    if(!ceasStare){ ceasStare = setInterval(stare, 2000); }
  } else if(ceasStare){
    clearInterval(ceasStare); ceasStare = null;
  }
}
function textRamas(secunde){
  if(typeof secunde !== "number"){ return ""; }
  if(secunde < 60){ return " · mai e mai puțin de un minut"; }
  var minute = Math.floor((secunde + 30) / 60);
  // romana: singularul cu litere ("un minut"), pluralul fara "de" ("20 minute"), ca pe televizor
  return minute === 1 ? " · mai durează cam un minut" : " · mai durează cam " + minute + " minute";
}
function stare(){
  cerere("/api/cautare-actualizeaza-stare").then(function(d){
    arataActualizare(d.stare);
    if(d.stare && !d.stare.activ && d.text){ mesaj(d.text); cauta(); }
  }).catch(function(){});
}
var deLaCapat = false;
function cerePornire(confirmat, neprinse){
  var q = filtre(); q.set("fel", $("fel").value);
  if(confirmat){ q.set("confirmat", "1"); q.set("neprinse", neprinse || "lasa"); }
  if(deLaCapat){ q.set("de_la_capat", "1"); }
  cerere("/api/cautare-actualizeaza", "POST", q).then(function(d){
    if(d.confirmare){
      // reluarea: intrebarea ei inaintea celei obisnuite; „Da, pornește” continua, „De la capăt” cere planul intreg
      // pozitiile fara semnal niciodata (istoricul semnalului): Da, porneste le lasa, al doilea buton le incearca
      var text = d.neprinse || d.confirmare;
      mesaj(d.reluare ? d.reluare + " " + text : text);
      $("capat").classList.toggle("ascuns", !d.reluare);
      $("incearca").classList.toggle("ascuns", !d.neprinse);
      $("intrebare").classList.remove("ascuns"); return;
    }
    deLaCapat = false;
    $("intrebare").classList.add("ascuns");
    mesaj(d.message, !d.result);
    if(d.result){ arataActualizare(d.actualizare || {activ: true, pas: 0, total: 0, citite: 0}); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("culegere").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("mod", $("culegere").value);
  var m = $("mesajCulegere");
  cerere("/api/cautare-culegere", "POST", q).then(function(d){
    m.textContent = d.message || ""; m.classList.toggle("eroare", !d.result); arataCulegere(d.culegere);
  }).catch(function(){ m.textContent = "Receptorul nu răspunde."; m.classList.add("eroare"); });
});
$("text").addEventListener("input", function(){ clearTimeout(ceasText); ceasText = setTimeout(cauta, 250); });
$("sterge").addEventListener("click", function(){ $("text").value = ""; Object.keys(ALES).forEach(function(g){ ALES[g] = []; }); tineMinte(); cauta(); });
$("actualizeaza").addEventListener("click", function(){ deLaCapat = false; cerePornire(false); });
$("da").addEventListener("click", function(){ cerePornire(true, "lasa"); });
$("incearca").addEventListener("click", function(){ cerePornire(true, "incearca"); });
// istoricul semnalului (Components/HdsIstoricSemnal.py): pozitiile prinse de acest receptor, de la est la vest
function arataIstoric(d){
  var lista = $("istoricLista"); lista.textContent = "";
  var poz = (d && d.pozitii) || [];
  $("istoricNota").textContent = poz.length ? "Pozițiile pe care acest receptor a recepționat semnal, la schimbarea canalului și la scanare. Actualizează pistele întreabă înainte numai de pozițiile aduse din altă listă, fără semnal aici." : "Niciun semnal ținut minte încă. Se notează singur la fiecare schimbare de canal și la scanare.";
  if(d && d.aduse){ var a = document.createElement("div"); a.className = "nota"; a.textContent = d.aduse; lista.appendChild(a); }
  poz.forEach(function(p){
    var r = document.createElement("div"); r.className = "nota";
    r.textContent = p.pozitie_text + " · " + p.text + " · " + p.transpondere_text;
    lista.appendChild(r);
  });
}
function citesteIstoric(){
  cerere("/api/istoric-semnal").then(arataIstoric).catch(function(){ $("istoricNota").textContent = "Receptorul nu răspunde."; });
}
$("stergeIstoric").addEventListener("click", function(){
  if(!confirm("Ștergi istoricul semnalului? Receptorul îl ia de la capăt la următoarele schimbări de canal.")){ return; }
  cerere("/api/istoric-semnal-sterge", "POST", new URLSearchParams()).then(function(d){
    $("istoricNota").textContent = d.message || ""; if(d.result){ arataIstoric(d); }
  }).catch(function(){ $("istoricNota").textContent = "Receptorul nu răspunde."; });
});
citesteIstoric();
$("capat").addEventListener("click", function(){ deLaCapat = true; cerePornire(false); });
$("nu").addEventListener("click", function(){ deLaCapat = false; $("intrebare").classList.add("ascuns"); mesaj(""); });
$("sari").addEventListener("click", function(){
  cerere("/api/cautare-actualizeaza-sari", "POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); stare(); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
$("opreste").addEventListener("click", function(){
  cerere("/api/cautare-actualizeaza-opreste", "POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); stare(); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
// ---------------------------------------------------------------- Vezi live, playlistul si adresa fixa (ca in /canale)
// fereastra "Vezi live", butonul ei si descarcarea playlistului: codul comun cu /canale (vezi_live_web.py)
__LIVE_JS__
// adresa fixa pentru un aparat: fereastra si scriptul comune cu /canale (aparate_web.py)
var TA = __APARATE_TEXTE__, MAX_CANALE_APARAT = __APARATE_MAX__;
__APARATE_JS__
var TX = __TEXTE__;
// ultimul raspuns al cautarii: eticheta (textul si filtrele, pentru om), sursa aparatului, cate canale
var ULTIM = null;
// "Vezi live" pe un canal pe care transmisia nu-l poate lua fara televizor (receptor cu motor sau cu un singur tuner de
// satelit, canal de pe alta frecventa): televizorul trece pe el ca la "Porneste pe televizor" (/api/zap), apoi imaginea
// urmeaza televizorul; randul ramane marcat ca pornit din aceasta lista
function mutaTv(ref){
  var q = new URLSearchParams(); q.set("sRef", ref);
  return cerere("/api/zap", "POST", q).then(function(d){
    if(d.result){ pornit = ref; memScrie(MEM_PORNIT, ref); marcheazaPornit(); }
    return d;
  });
}
// playlistul tuturor canalelor gasite (nu numai al celor aratate): referintele le da receptorul (refs=1)
function exportaPlaylist(){
  var buton = $("exportM3u");
  buton.disabled = true;
  mesaj(TL.se_strange);
  var q = filtre(); q.set("refs", "1");
  cerere("/api/cautare-canale?" + q.toString()).then(function(d){
    if(!d.result){ throw new Error(d.message || TL.nu_s_a_facut); }
    return liveDescarca(d.refs || [], d.grup, d.eticheta, d.numar, d.nota);
  }).catch(function(e){ mesaj(e.message || TL.nu_s_a_facut, true); })
    .then(function(){ buton.disabled = !(ULTIM && ULTIM.total); });
}
// cautarea de acum ca lista unui aparat din casa (sursa "filtru", ca lista filtrata din /canale)
function deschideAparat(){
  if(!ULTIM || !ULTIM.total){ mesaj(TL.fara_canale, true); return; }
  var a = ULTIM.aparat;
  if(!a || !a.potrivit){ mesaj(TX.aparat_radio, true); return; }
  aparatDeschide({eticheta: ULTIM.eticheta || "", numar: ULTIM.total, inapoi: $("aparatFix"), campuri: function(){
    return {sursa: "filtru", buchet: a.buchet, text: a.text, filtre: JSON.stringify(a.filtre)};
  }});
}
$("exportM3u").addEventListener("click", exportaPlaylist);
$("aparatFix").addEventListener("click", deschideAparat);
citesteMemoria();
cauta();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Căutare canale"),
		N_("Da, încearcă și pozițiile fără semnal"),
		N_("Istoricul semnalului pe acest receptor"),
		N_("Șterge istoricul"),
		N_("Se citește istoricul..."),
		N_("Șterge filtrele"),
		N_("Se citește lista..."),
		N_("canalele fără piste știute"),
		N_("canalele găsite acum"),
		N_("toate canalele"),
		N_("Actualizează pistele"),
		N_("Sari peste satelitul acesta"),
		N_("Oprește"),
		N_("Da, pornește"),
		N_("De la capăt"),
		N_("Nu"),
		N_("Citirea pistelor în timpul vizionării"),
		N_("Pistele (teletext, subtitrări, limbile și formatul sunetului, HbbTV) se află singure când te "
			"uiți la un canal. Mono, stereo sau 5.1 se află din datele transmise de canal: din ghidul "
			"programelor, la vizionare, și la „Actualizează pistele”. În același rând opțiunile se adună cu "
			"„sau”, între rânduri cu „și”; numerele de lângă opțiuni sunt ale felului ales la „Tip”."),
		N_("Numele canalului (orice parte din nume)"),
		N_("Ce canale"),
	),
	"js": (
		N_("Pozițiile pe care acest receptor a recepționat semnal, la schimbarea canalului și la scanare. Actualizează "
			"pistele întreabă înainte numai de pozițiile aduse din altă listă, fără semnal aici."),
		N_("Niciun semnal ținut minte încă. Se notează singur la fiecare schimbare de canal și la scanare."),
		N_("Ștergi istoricul semnalului? Receptorul îl ia de la capăt la următoarele schimbări de canal."),
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Pistele nu se știu încă."),
		N_("Sunet:"),
		N_("Subtitrări DVB:"),
		N_("Subtitrări teletext:"),
		N_("Teletext"),
		N_("fără teletext"),
		N_("fără HbbTV"),
		N_("citite"),
		N_("Fără piste."),
		N_("Canalul pornește pe televizor."),
		N_("Nu a pornit."),
		N_("Receptorul nu răspunde."),
		N_("Pornit pe televizor din această listă"),
		N_("Pornește pe televizor"),
		N_("Se arată primele"),
		N_(". Restrânge căutarea cu numele sau cu filtrele."),
		N_("Lista nu s-a putut citi."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Sari peste"),
		N_("Sari peste satelitul acesta"),
		N_("Se citesc pistele pe televizor: transponderul"),
		N_("din"),
		N_("· antena se rotește spre"),
		N_("· aștept semnal"),
		N_("pe"),
		N_("(încă"),
		N_("· citite:"),
		N_("· mai e mai puțin de un minut"),
		N_("· mai durează cam"),
		N_("· mai durează cam un minut"),
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
