# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# editor_canale_web.py: editorul de canale in interfata web (HdsWebControl), pagina /editor-canale. Aceleasi date,
# aceleasi operatii, aceeasi anulare si aceleasi copii de siguranta ca ecranele de pe televizor: totul trece prin
# Components/HdsEditorCanale.py (sesiunea, o singura editare odata: televizorul sau un browser).
#
# PAGINA, pe telefon si pe calculator (aceeasi pagina, asezarea dupa latime):
# - lat (de la LATIME_DOUA px): doua coloane, „Adaugă canale” (sursa: toate, sateliti, furnizori, cautarea, filtrele)
#   si „Buchet”; ingust: o singura coloana, cu comutarea „Buchet” / „Adaugă canale”;
# - fiecare rand are bifa lui (selectia), manerul de mutare (tras cu mouse-ul sau cu degetul) si butonul „⋯” cu
#   toate actiunile randului; jos, bara cu cel mult patru actiuni mari si „Mai mult”; „Anulează: <schimbarea>” mereu
#   la vedere dupa o schimbare; inainte de orice stergere, intrebarea cu numarul randurilor;
# - tastele de pe calculator sunt numai scurtaturi (sagetile, Shift / Ctrl + sageti, Space, Enter, Delete, Ctrl+C / X
#   / V, Ctrl+Z / Y, Ctrl+A, Ctrl+S, F2, Esc); nimic nu cere tastatura;
# - listele lungi (9000 de canale) se deseneaza numai cat se vede (lista virtuala, randuri de aceeasi inaltime).
#
# RUTELE (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; cele care
# schimba ceva cer, cu cookie, POST, aceeasi origine si antetul CSRF al panoului). `eu` = numarul paginii deschise
# (facut in pagina), ca sesiunea sa fie a ei; numele browserului vine din asociere.
#   GET  /api/editor-canale-stare?eu=             cine editeaza, starea sesiunii (versiunea, anularea, nesalvate),
#                                                  rezultatul ultimei lucrari in fundal (deschidere, salvare)
#   POST /api/editor-canale-deschide?eu=&preia=   ia sesiunea (citirea in fundal) / o preia de la televizor
#   POST /api/editor-canale-inchide?eu=
#   GET  /api/editor-canale-buchete?eu=&radio=    buchetele (arborele) si cele nelegate
#   GET  /api/editor-canale-intrari?eu=&buchet=   randurile unui buchet (si ale listei buchetelor)
#   GET  /api/editor-canale-servicii?eu=&radio=&de_la=&cate=   canalele din lamedb, pe pagini, si pozitiile
#   POST /api/editor-canale-op?eu=                o operatie (corpul JSON: {"op": ..., ...}), cu anulare
#   POST /api/editor-canale-salveaza?eu=          salvarea (in fundal; rezultatul in -stare)
#   GET  /api/editor-canale-copii?eu=             copiile de siguranta
#   GET  /api/editor-canale-schimbari?eu=         ce s-a schimbat de la ultima salvare (numerele, buchetele)
#   POST /api/editor-canale-intoarce?eu=&id=      intoarcerea la o copie (in fundal)
#   GET  /api/editor-canale-unelte?eu=&fel=test|dubluri|moarte|goale|transpondere|probleme   grupele uneltelor
#   GET  /api/editor-canale-unelte?eu=&fel=compara&id=   lista de acum fata de o copie de siguranta
#   GET  /api/editor-canale-unelte?eu=&fel=verifica|compara_import|sigle_nefolosite|fluxuri
#   GET  /api/editor-canale-detalii?eu=&cheie=    tot ce stie lamedb despre un canal (Mod avansat)
#   GET  /api/editor-canale-transponder?eu=&tp=   parametrii unui transponder din lamedb (Mod avansat)
#   GET  /api/editor-canale-copie?eu=&id=         o copie de siguranta, descarcata (tar.gz)
#   GET  /api/editor-canale-sateliti?eu=[&poz=]   satellites.xml: satelitii, sau transponderele unuia (Mod avansat)
#   POST /api/editor-canale-sateliti-op?eu=       o schimbare in satellites.xml (in memorie) / salvarea / renuntarea
#   POST /api/editor-canale-sigla?eu=&fel=pune|copiaza|sterge|redenumeste|sterge_nefolosite   siglele canalelor
#                                                  (pune: PNG-ul in corp, prin editor-canale-import?fel=sigla)
#   GET  /api/editor-canale-export?eu=&fel=tar.gz|zip|m3u&buchet=   lista sau buchetul, ca fisier
#   POST /api/editor-canale-import?eu=&fel=arhiva|m3u&nume=   arhiva sau m3u in corp (octeti); arhiva: ce are
#   POST /api/editor-canale-import-aplica?eu=     arhiva despachetata pusa in editor (corpul: mod, ce, buchete)
#   GET  /editor-canale                           pagina
#
# FIRUL: operatiile sunt pe firul enigma2 si scurte (sub 50 ms pe o lista de 9000 de servicii, pe PC); citirea,
# salvarea, intoarcerea si uneltele merg pe firul lor (HdsEditorCanale), iar raspunsul pleaca la sfarsit
# (NOT_DONE_YET) sau starea se citeste din nou (-stare). Paginile listei de servicii (cel mult MAX_PAGINA randuri)
# tin firul putin.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau sesiunea lor.

import json
import os
import re
import shutil
import time

MAX_PAGINA = 3000
MAX_CORP_OP = 1024 * 1024
MAX_CORP_IMPORT = 16 * 1024 * 1024
DOSAR_IMPORT = "/tmp/hds-editor-import"
CALE_OP = b"/api/editor-canale-op"
CALE_IMPORT = b"/api/editor-canale-import"
_EU = re.compile(r"^[A-Za-z0-9]{6,40}$")
_ID_BUCHET = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")
_CHEIE = re.compile(r"^[0-9a-f]{1,8}(:[0-9a-f]{1,8}){3}$")
_TP = re.compile(r"^[0-9a-f]{8}:[0-9a-f]{4}:[0-9a-f]{4}$")
FEL_COD = {"canal": "c", "marcaj": "m", "spatiu": "g", "subbuchet": "b", "alternative": "a", "flux": "f", "altul": "x"}


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	return text


def _jurnal(text):
	print("[HdsWebControl] editor-canale: %s" % text)


def _E():
	"""Modulul comun (Components/HdsEditorCanale); pe PC il dau probele (sys.modules)."""
	try:
		from Components import HdsEditorCanale as E
	except ImportError:
		import HdsEditorCanale as E
	return E


def _U():
	try:
		from Components import HdsEditorCanaleUnelte as U
	except ImportError:
		import HdsEditorCanaleUnelte as U
	return U


def _S():
	try:
		from Components import HdsEditorSateliti as S
	except ImportError:
		import HdsEditorSateliti as S
	return S


def _G():
	try:
		from Components import HdsEditorSigle as G
	except ImportError:
		import HdsEditorSigle as G
	return G


def _D():
	try:
		from Components import HdsEditorCanaleDate as D
	except ImportError:
		import HdsEditorCanaleDate as D
	return D


# ---------------------------------------------------------------- argumentele

def argumente(request):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:24]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not re.match(r"^[a-z_]{1,12}$", cheie):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:400].strip()
	return rez


def _intreg(text, implicit, minim, maxim):
	try:
		return max(minim, min(maxim, int(text)))
	except (TypeError, ValueError):
		return implicit


def _corp_json(request, maxim=MAX_CORP_OP):
	try:
		request.content.seek(0)
		date = request.content.read(maxim + 1)
	except Exception:
		return None
	if not date or len(date) > maxim:
		return None
	try:
		obiect = json.loads(date.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return None
	return obiect if isinstance(obiect, dict) else None


def _nume_browser(request):
	try:
		from . import plugin as P
		if P.PARAM_JETON in request.args:
			return _t("un program")
		_secret, browser = P._sesiuneDinCerere(request)
		if browser is not None:
			return browser.get("nume", "") or _t("un browser")
	except Exception:
		pass
	return _t("un browser")


# ---------------------------------------------------------------- starea paginii (rezultatele lucrarilor in fundal)

_REZULTAT = {}      # eu -> {"fel": ..., ...} (ultima lucrare in fundal a paginii)
_SATELITI = {}      # satellites.xml schimbat in pagina si nesalvat: {"s": Sateliti, "schimbat": True}


def _sesiunea(eu):
	"""Sesiunea paginii `eu`, sau (None, motiv)."""
	E = _E()
	s = E.sesiune()
	if s is None or s.cine != E.WEB or s.id_client != eu:
		return None
	return s


def _ocupat_json(o):
	if o is None:
		return None
	E = _E()
	return {"cine": o["cine"], "nume": o.get("nume") or "", "de_la": int(o.get("de_la") or 0),
		"nesalvate": o.get("nesalvate", 0), "lucreaza": bool(o.get("lucreaza")),
		"mesaj": E.Ocupat(o["cine"], o.get("nume", ""), 0, o.get("nesalvate", 0), bool(o.get("lucreaza"))).mesaj()}


def stare(a):
	E = _E()
	eu = a.get("eu", "")
	s = _sesiunea(eu)
	rez = {"result": True, "a_mea": s is not None, "ocupat": None, "rezultat": _REZULTAT.get(eu)}
	if s is None:
		rez["ocupat"] = _ocupat_json(E.ocupat_de())
		return 200, rez
	s.atinge()
	rez.update({"lucreaza": s.lucreaza(), "gata": s.lucreaza() is False and s._baza is not None,
		"versiune": s.versiune(), "nesalvate": s.nesalvate(), "de_anulat": s.de_anulat(), "de_refacut": s.de_refacut()})
	return 200, rez


def _info_sesiune(s):
	return {"versiune": s.versiune(), "nesalvate": s.nesalvate(), "de_anulat": s.de_anulat(),
		"de_refacut": s.de_refacut()}


# ---------------------------------------------------------------- randurile

def _poz_cod(poz):
	if isinstance(poz, int):
		return poz
	return {"cablu": -1, "terestru": -2}.get(poz, -3)


def sigle_stiute():
	"""Siglele gasite pe disc de pagina /canale (canale_web: numele -> calea), cu cautarea lor pornita pe firul ei daca
	nu s-a facut sau e veche. Pana vine rezultatul randurile pleaca fara sigla (nicio cerere la /api/canale-sigla care
	ar da 404). Fara canale_web (probele de pe PC): None."""
	try:
		from . import canale_web as CW
	except ImportError:
		return None
	try:
		M = CW._m()
		mem = CW._MEMORIE
		if mem.get("sigle") is None or M.acum() - (mem.get("sigle_ora") or 0) >= CW.VIATA_SIGLE_S:
			CW.porneste_cautarea_siglelor(M)
		return mem.get("sigle") or {}
	except Exception as e:
		_jurnal("siglele: %r" % (e,))
		return None


def _sigla(ref, sigle):
	if not sigle:
		return ""
	try:
		from . import canale_web
		nume = canale_web.nume_sigla(ref) or ""
	except Exception:
		return ""
	return nume if nume in sigle else ""


def rand_intrare(x, sigle=None):
	biti = (1 if x.ascuns else 0) | (2 if x.blocat else 0) | (4 if x.mort else 0) | (8 if x.numerotat else 0)
	detaliu = ""
	sigla = ""
	if x.fel == "canal" and x.serviciu is not None:
		c = x.serviciu
		detaliu = " · ".join(p for p in (c.poz_text, c.tp_text, c.furnizor) if p)
		sigla = _sigla(c.ref, sigle)
	elif x.fel == "canal" and x.mort:
		detaliu = _t("Canalul nu mai există în lista receptorului")
	elif x.fel == "flux":
		D = _D()
		cale = D.decodeaza(D.Referinta(x.ref).cale)
		detaliu = cale.split("://", 1)[-1].split("/", 1)[0] if "://" in cale else cale
	return [x.id, FEL_COD.get(x.fel, "x"), x.nume, x.numar, biti, x.cheie or "", detaliu, x.buchet_id or "", sigla,
		x.serviciu.hd if x.fel == "canal" and x.serviciu is not None else "", x.ref if x.fel == "flux" else ""]


def text_tp(k):
	"""Cheia transponderului (ns, tsid, onid) ca text, pentru pagina."""
	try:
		return "%08x:%04x:%04x" % tuple(k)
	except (TypeError, ValueError):
		return ""


def rand_serviciu(c, harta, sigle=None):
	biti = (1 if c.ascuns else 0) | (2 if c.blocat else 0) | (4 if c.are_video else 0) | (8 if c.are_sunet else 0) | \
		(16 if (c.steaguri or 0) & 64 else 0) | (32 if _U().hd_in_nume_sd(c.nume, c.stype) else 0)
	return [c.cheie, c.ref, c.nume, c.furnizor, _poz_cod(c.poz), c.frecv or 0, c.pol, c.sid, c.hd, c.acces or "", biti,
		len(harta.get(c.cheie, ())), c.tp_text, _sigla(c.ref, sigle), c.tip, text_tp(c.tp_cheie), c.stype]


def rezumat(s):
	"""Ce s-a schimbat de la ultima salvare (s.schimbari()): numerele canalelor, numele buchetelor noi, sterse si
	schimbate, iar „lista” = lista buchetelor (radacina) schimbata (ordinea, ascunderea, un buchet pus sau scos)."""
	x = s.schimbari()
	D = _D()
	baza = s._baza[1]
	noi, sterse, schimbate = [], [], []
	lista = False
	for bid in x["buchete"]:
		if bid in ("bouquets.tv", "bouquets.radio"):
			lista = True
			continue
		b = s.d.buchete.get(bid)
		vechi = baza.get(bid)
		nume = (D.fara_mod((b or vechi).nume) if (b or vechi) is not None else "") or bid
		(noi if vechi is None else sterse if b is None else schimbate).append(nume)
	return {"servicii_noi": x["servicii_noi"], "servicii_sterse": x["servicii_sterse"],
		"servicii_schimbate": x["servicii_schimbate"], "buchete_noi": noi, "buchete_sterse": sterse,
		"buchete": schimbate, "lista": lista, "parental": bool(x["parental"]), "nesalvate": x["nesalvate"]}


def _de_internet(s, bid):
	"""Buchetul are mai multe fluxuri (adrese de internet) decat canale de satelit / cablu / terestru."""
	b = s.d.buchete.get(bid)
	if b is None:
		return False
	fl = sum(1 for i in b.intrari if i.fel == "flux")
	return fl > 0 and fl >= sum(1 for i in b.intrari if i.fel == "canal")


def buchete(s, a):
	radio = a.get("radio") == "1"
	arbore = [[b.id, b.nume, b.n, adancime, b.parinte, 1 if b.favorite else 0, 1 if b.blocat else 0,
		1 if _de_internet(s, b.id) else 0] for b, adancime in s.toate_buchetele(radio)]
	nelegate = [[b.id, b.nume, b.n] for b in s.nelegate(radio)]
	return 200, {"result": True, "radacina": s.radacina(radio), "arbore": arbore, "nelegate": nelegate}


def intrari(s, a):
	bid = a.get("buchet", "")
	if not _ID_BUCHET.match(bid):
		return 400, {"result": False, "message": _t("Buchetul nu e bun.")}
	b = s.buchet(bid)
	if b is None:
		return 404, {"result": False, "message": _t("Buchetul nu mai există.")}
	sigle = sigle_stiute()
	randuri = [rand_intrare(x, sigle) for x in s.intrari(bid)]
	r = {"result": True, "buchet": bid, "nume": b.nume, "radio": b.radio, "favorite": b.favorite,
		"blocat": b.blocat, "parinte": b.parinte or "", "randuri": randuri}
	if bid in ("bouquets.tv", "bouquets.radio"):
		r["nume"] = _t("Lista buchetelor")
	r["automat"] = _E().buchet_automat(bid)
	r.update(_info_sesiune(s))
	return 200, r


def servicii(s, a):
	r = a.get("radio", "0")
	radio = None if r == "2" else (r == "1")
	toate = s.toate(radio)
	de_la = _intreg(a.get("de_la"), 0, 0, len(toate))
	cate = _intreg(a.get("cate"), MAX_PAGINA, 1, MAX_PAGINA)
	harta = s._harta_buchete()
	sigle = sigle_stiute()
	randuri = [rand_serviciu(c, harta, sigle) for c in toate[de_la:de_la + cate]]
	rez = {"result": True, "total": len(toate), "de_la": de_la, "randuri": randuri, "versiune": s.versiune()}
	if de_la == 0:
		rez["sateliti"] = [[_poz_cod(p), t, s.nume_satelit(p), n] for p, t, n in s.sateliti(radio)]
	return 200, rez


# ---------------------------------------------------------------- operatiile

def _ids(o, cheie="ids"):
	v = o.get(cheie) or []
	if not isinstance(v, list):
		return []
	return [x for x in v[:20000] if isinstance(x, int)]


def _chei(s, o, cheie="chei"):
	"""Cheile canalelor (sid:ns:tsid:onid) -> referintele lor din lamedb."""
	v = o.get(cheie) or []
	if not isinstance(v, list):
		return []
	rez = []
	for k in v[:20000]:
		if isinstance(k, str) and _CHEIE.match(k):
			sv = s.d.lamedb.dupa_cheie(k)
			if sv:
				rez.append(sv[0].ref)
	return rez


def _tp(text):
	"""Cheia transponderului din textul paginii (ns:tsid:onid hex) -> (ns, tsid, onid); altfel Eroare."""
	if not isinstance(text, str) or not _TP.match(text):
		raise _E().Eroare(_t("Transponderul nu mai există."))
	return tuple(int(p, 16) for p in text.split(":"))


ORDINI = ("nume", "pozitie", "furnizor", "frecventa", "sid", "pozitie_nume", "furnizor_nume")


def _campuri(o):
	"""Campurile transponderului din pagina: frecventa in MHz, rata de simbol in kS/s -> unitatile din lamedb."""
	v = o.get("campuri") if isinstance(o.get("campuri"), dict) else {}
	rez = {}
	for nume, x in v.items():
		if not isinstance(nume, str) or not isinstance(x, (int, float)) or isinstance(x, bool):
			continue
		if nume == "frecventa":
			rez[nume] = int(round(x * 1000))
		elif nume == "sr":
			rez[nume] = int(round(x * 1000))
		else:
			rez[nume] = int(x)
	return rez


def _bid(o, cheie="buchet"):
	v = o.get(cheie)
	if not isinstance(v, str) or not _ID_BUCHET.match(v):
		raise _E().Eroare(_t("Buchetul nu e bun."))
	return v


def _text(o, cheie, maxim=200):
	v = o.get(cheie)
	return v[:maxim] if isinstance(v, str) else ""


def _la(s, bid, o, dupa_scoatere=None):
	"""Locul cerut: „inainte_de” = id-ul randului inaintea caruia se pune (None = la sfarsit), „pozitie” = numarul
	randului (de la 1). dupa_scoatere: id-urile care se scot intai (mutarea)."""
	b = s.d.buchete.get(bid)
	if b is None:
		return None
	l = [i.id for i in b.intrari if dupa_scoatere is None or i.id not in dupa_scoatere]
	if isinstance(o.get("pozitie"), int):
		return max(0, min(len(l), o["pozitie"] - 1))
	x = o.get("inainte_de")
	if isinstance(x, int) and x in l:
		return l.index(x)
	return None


def fa_operatia(s, o):
	"""Operatia ceruta de pagina -> (raspunsul, ce s-a atins). Ridica E.Eroare cu textul pentru om."""
	E = _E()
	op = o.get("op")
	rez = {}
	if op == "anuleaza":
		rez["facut"] = s.anuleaza()
		rez["tot"] = True
	elif op == "reface":
		rez["facut"] = s.reface()
		rez["tot"] = True
	elif op == "adauga":
		bid = _bid(o)
		rez["n"] = s.adauga(bid, _chei(s, o), _la(s, bid, o))
	elif op == "muta":
		bid = _bid(o)
		ids = _ids(o)
		ind = s.indici(bid, ids)
		la = _la(s, bid, o, set(ids))
		if la is None:
			la = len(s.d.buchete[bid].intrari) - len(ind)
		rez["facut"] = s.muta(bid, ind, la)
	elif op in ("muta_sus", "muta_jos"):
		bid = _bid(o)
		ind = s.indici(bid, _ids(o))
		rez["facut"] = (s.muta_sus if op == "muta_sus" else s.muta_jos)(bid, ind)
	elif op in ("muta_in", "copiaza"):
		din, in_ = _bid(o, "din"), _bid(o, "in")
		ind = s.indici(din, _ids(o))
		la = _la(s, in_, o)
		rez["facut"] = (s.muta_in if op == "muta_in" else s.copiaza)(din, ind, in_, la)
	elif op == "scoate":
		bid = _bid(o)
		rez["facut"] = s.scoate(bid, s.indici(bid, _ids(o)))
	elif op == "scoate_din_toate":
		rez["n"] = s.scoate_din_toate(_chei(s, o))
	elif op == "redenumeste":
		bid = _bid(o)
		ind = s.indici(bid, _ids(o))
		if len(ind) != 1:
			raise E.Eroare(_t("Alege un singur rând."))
		if o.get("peste_tot"):
			x = s.intrari(bid)[ind[0]]
			if x.fel != "canal" or x.serviciu is None:
				raise E.Eroare(_t("Numai un canal se poate redenumi peste tot."))
			rez["facut"] = s.redenumeste_serviciu(x.serviciu.ref, _text(o, "nume"))
			# numele propriu din buchet (daca avea) pleaca, ca peste tot sa se vada acelasi
			if x.descriere:
				s.redenumeste(bid, ind[0], _text(o, "nume"))
		else:
			rez["facut"] = s.redenumeste(bid, ind[0], _text(o, "nume"))
	elif op == "redenumeste_serviciu":
		refs = _chei(s, o)
		if len(refs) != 1:
			raise E.Eroare(_t("Alege un singur canal."))
		rez["facut"] = s.redenumeste_serviciu(refs[0], _text(o, "nume"))
	elif op == "redenumeste_buchet":
		rez["facut"] = s.redenumeste_buchet(_bid(o), _text(o, "nume", 100))
	elif op == "ascunde":
		rez["n"] = s.ascunde(_chei(s, o), bool(o.get("da", True)))
	elif op == "blocheaza":
		rez["n"] = s.blocheaza(_chei(s, o), bool(o.get("da", True)))
	elif op == "blocheaza_buchet":
		rez["facut"] = s.blocheaza_buchet(_bid(o), bool(o.get("da", True)))
	elif op == "ascunde_buchet":
		rez["facut"] = s.ascunde_buchet(_bid(o), bool(o.get("da", True)))
	elif op == "marcaj_nou":
		bid = _bid(o)
		rez["poz"] = s.marcaj_nou(bid, _la(s, bid, o), _text(o, "nume"), bool(o.get("numerotat")))
	elif op == "spatiu_nou":
		bid = _bid(o)
		rez["poz"] = s.spatiu_nou(bid, _la(s, bid, o))
	elif op == "flux_nou":
		bid = _bid(o)
		rez["poz"] = s.flux_nou(bid, _la(s, bid, o), _text(o, "adresa", 1000), _text(o, "nume"))
	elif op == "buchet_nou":
		parinte = o.get("parinte")
		parinte = _bid(o, "parinte") if parinte else None
		la = _la(s, parinte, o) if parinte else None
		rez["buchet"] = s.buchet_nou(_text(o, "nume", 100), bool(o.get("radio")), parinte, la, _chei(s, o))
	elif op == "copiaza_buchet":
		rez["buchet"] = s.copiaza_buchet(_bid(o), _text(o, "nume", 100) or None)
	elif op == "sterge_buchet":
		rez["n"] = s.sterge_buchet(_bid(o))
	elif op == "leaga_buchet":
		rez["facut"] = s.leaga_buchet(_bid(o))
	elif op == "sterge_nelegat":
		rez["facut"] = s.sterge_nelegat(_bid(o))
	elif op == "sorteaza":
		bid = _bid(o)
		dupa = o.get("dupa") if o.get("dupa") in ORDINI else "nume"
		ids = _ids(o)
		ind = s.indici(bid, ids) if len(ids) > 1 else None
		rez["facut"] = s.sorteaza(bid, dupa, ind, bool(o.get("invers")))
	elif op == "sterge_servicii":
		rez["n"] = s.sterge_servicii(_chei(s, o))
	elif op == "sterge_transpondere":
		tpuri = o.get("tpuri") if isinstance(o.get("tpuri"), list) else []
		rez["n"] = s.sterge_transpondere([_tp(t) for t in tpuri[:5000]])
	elif op == "sterge_sateliti":
		poz = [{-1: "cablu", -2: "terestru"}.get(p, p) for p in (o.get("pozitii") or [])[:4000] if isinstance(p, int)]
		rez["n"] = s.sterge_sateliti(poz, bool(o.get("pastreaza")))
	elif op == "muta_satelit":
		rez["n"] = s.muta_satelit(o.get("din") if isinstance(o.get("din"), int) else -1,
			o.get("la") if isinstance(o.get("la"), int) else -1, bool(o.get("copiaza")))
	elif op == "schimba_transponder":
		rez["facut"] = s.schimba_transponder(_tp(o.get("tp")), _campuri(o))
	elif op == "transponder_nou":
		poz = o.get("poz")
		rez["tp"] = s.transponder_nou(poz if isinstance(poz, int) else -1, _campuri(o), _intreg(o.get("tsid"), -1, -1,
			0x10000), _intreg(o.get("onid"), -1, -1, 0x10000))
	elif op == "curata_steaguri":
		rez["n"] = s.curata_steaguri(o.get("fel") if o.get("fel") in ("ascunse", "blocate", "noi") else "")
	elif op == "scoate_nou":
		rez["n"] = s.scoate_nou(_chei(s, o))
	elif op == "schimba_serviciu":
		refs = _chei(s, o)
		if len(refs) != 1:
			raise E.Eroare(_t("Alege un singur canal."))
		pids = o.get("pids")
		if pids is not None:
			if not isinstance(pids, dict):
				raise E.Eroare(_t("Un PID nu e bun."))
			pids = dict((k, v) for k, v in list(pids.items())[:40] if str(k).isdigit() and isinstance(v, int))
		st = o.get("steaguri")
		rez["facut"] = s.schimba_serviciu(refs[0], _text(o, "furnizor") if isinstance(o.get("furnizor"), str) else None,
			st if isinstance(st, int) else None, pids)
	elif op == "scoate_canale":
		rez["facut"] = s.scoate_canale(_bid(o), _chei(s, o))
	elif op == "schimba_flux":
		bid = _bid(o)
		ind = s.indici(bid, _ids(o))
		if len(ind) != 1:
			raise E.Eroare(_t("Alege un singur rând."))
		nr = dict((k, o.get(k) if isinstance(o.get(k), int) else None) for k in ("tip", "sid", "tsid", "onid", "ns"))
		rez["facut"] = s.schimba_flux(bid, ind[0], _text(o, "adresa", 1000) or None, **nr)
	elif op == "sorteaza_buchete":
		dupa = o.get("dupa") if o.get("dupa") in ORDINI else "nume"
		bids = [b for b in (o.get("buchete") or [])[:500] if isinstance(b, str) and _ID_BUCHET.match(b)]
		rez["n"] = s.sorteaza_buchete(bids, dupa, bool(o.get("invers")))
	elif op == "aranjeaza_dupa":
		rez["facut"] = s.aranjeaza_dupa(_bid(o), _bid(o, "model"))
	elif op == "inlocuieste_nume":
		bids = [b for b in (o.get("buchete") or [])[:2000] if isinstance(b, str) and _ID_BUCHET.match(b)]
		rez["n"] = s.inlocuieste_nume(_text(o, "cauta", 100), _text(o, "cu", 100), _chei(s, o), bids)
		rez["tot"] = True
	elif op == "readu_din_copie":
		chei = [k for k in (o.get("chei") or [])[:20000] if isinstance(k, str) and _CHEIE.match(k)]
		rez["n"] = s.readu_din_copie(_text(o, "id", 40), chei)
	elif op in ("alternative_noi", "alternative_desface", "alternative_adauga"):
		bid = _bid(o)
		ind = s.indici(bid, _ids(o))
		if op == "alternative_noi":
			rez["poz"] = s.alternative_noi(bid, ind, _text(o, "nume", 100) or None)
		elif len(ind) != 1:
			raise E.Eroare(_t("Alege un singur rând."))
		elif op == "alternative_desface":
			rez["facut"] = s.alternative_desface(bid, ind[0])
		else:
			rez["n"] = s.alternative_adauga(bid, ind[0], _chei(s, o))
	elif op == "buchete_din":
		fel = o.get("fel")
		valori = o.get("valori") if isinstance(o.get("valori"), list) else []
		if fel == "satelit":
			valori = [{-1: "cablu", -2: "terestru"}.get(v, v) for v in valori[:500] if isinstance(v, int)]
		elif fel == "furnizor":
			valori = [v[:200] for v in valori[:500] if isinstance(v, str)]
		else:
			raise E.Eroare(_t("Nu știu din ce să fac buchetul."))
		rez["buchete"] = s.buchete_din(fel, valori, bool(o.get("radio")))
	elif op == "sterge_randuri":
		# randuri din mai multe buchete (dublurile): {"randuri": [[buchet, id], ...]}
		pe = {}
		for r in (o.get("randuri") or [])[:20000]:
			if isinstance(r, list) and len(r) == 2 and isinstance(r[0], str) and _ID_BUCHET.match(r[0]) and \
					isinstance(r[1], int):
				pe.setdefault(r[0], []).append(r[1])
		n = 0
		for bid, ids in pe.items():
			ind = s.indici(bid, ids)
			if ind:
				s.scoate(bid, ind)
				n += len(ind)
		rez["n"] = n
	elif op == "repara_moarte":
		U = _U()
		alese = set()
		for r in (o.get("randuri") or [])[:20000]:
			if isinstance(r, list) and len(r) == 2:
				alese.add((r[0], r[1]))
		randuri = [r for r in s.referinte_moarte()[0].randuri if (r.buchet_id, r.id_intrare) in alese]
		rez["n"] = s.repara_moarte(randuri)
		del U
	elif op == "buchet_din":
		fel = o.get("fel")
		radio = bool(o.get("radio"))
		if fel == "satelit":
			p = o.get("valoare")
			poz = {-1: "cablu", -2: "terestru"}.get(p, p)
			rez["buchet"] = s.buchet_din("satelit", poz, radio, _text(o, "nume", 100) or None)
		elif fel == "furnizor":
			rez["buchet"] = s.buchet_din("furnizor", _text(o, "valoare"), radio, _text(o, "nume", 100) or None)
		elif fel == "transponder":
			rez["buchet"] = s.buchet_din("transponder", _tp(o.get("valoare")), radio, _text(o, "nume", 100) or None)
		elif fel == "refs":
			rez["buchet"] = s.buchet_din("refs", _chei(s, o), radio, _text(o, "nume", 100) or None)
		else:
			raise E.Eroare(_t("Nu știu din ce să fac buchetul."))
	else:
		raise E.Eroare(_t("Operația nu e cunoscută."))
	rez.update(_info_sesiune(s))
	rez["result"] = True
	return rez


def _servicii_atinse(s, o, rez):
	"""Randurile noi ale canalelor atinse (redenumite, ascunse, blocate), ca pagina sa nu ceara toata lista."""
	if o.get("op") not in ("ascunde", "blocheaza", "redenumeste_serviciu", "redenumeste"):
		return
	harta = s._harta_buchete()
	chei = [k for k in (o.get("chei") or []) if isinstance(k, str)][:5000]
	if o.get("op") == "redenumeste" and o.get("peste_tot"):
		bid = o.get("buchet")
		for i in (s.d.buchete.get(bid).intrari if s.d.buchete.get(bid) else ()):
			if i.id in (o.get("ids") or []) and i.cheie:
				chei.append(i.cheie)
	rand = []
	sigle = sigle_stiute()
	for k in chei:
		sv = s.d.lamedb.dupa_cheie(k)
		if sv:
			rand.append(rand_serviciu(s._canal(sv[0]), harta, sigle))
	if rand:
		rez["servicii"] = rand


# ---------------------------------------------------------------- rutele

def rute(baza, resource, NOT_DONE_YET=None):
	"""({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	def _trimite(obiect, request, cod, corp):
		try:
			request.write(obiect._raspunde(request, corp, cod))
			request.finish()
		except Exception as e:
			_jurnal("raspunsul nu a plecat (browser plecat?): %s" % e)

	class _Baza(baza):
		def _a(self, request):
			return argumente(request)

		def _sesiune(self, request, a, scrie=False):
			"""(sesiunea paginii, None) sau (None, raspunsul). scrie=True: cererea schimba ceva sau porneste o unealta,
			deci asteapta si cat merge o unealta (care numai citeste; citirile nu o asteapta)."""
			eu = a.get("eu", "")
			if not _EU.match(eu):
				return None, self._eroare(request, _t("Pagina nu e bună. Deschide din nou editorul."), 400)
			s = _sesiunea(eu)
			if s is None:
				o = _E().ocupat_de()
				corp = {"result": False, "pierdut": True, "ocupat": _ocupat_json(o),
					"message": _t("Editorul nu mai e deschis în această pagină. Deschide-l din nou.")}
				return None, self._raspunde(request, corp, 409)
			if s.lucreaza() or (scrie and s.unealta_merge()):
				corp = {"result": False, "lucreaza": True,
					"message": _t("Editorul lucrează încă (citește sau salvează lista). Încearcă din nou peste câteva "
						"secunde.")}
				return None, self._raspunde(request, corp, 409)
			s.atinge()
			return s, None

		def _ruleaza(self, request, f):
			try:
				cod, corp = f()
				return self._raspunde(request, corp, cod)
			except Exception as e:
				E = _E()
				if isinstance(e, E.Eroare):
					return self._raspunde(request, {"result": False, "message": e.mesaj()}, 409)
				_jurnal("%r" % (e,))
				import traceback
				traceback.print_exc()
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class StareResource(_Baza):
		def render_GET(self, request):
			return self._ruleaza(request, lambda: stare(self._a(request)))

	class DeschideResource(_Baza):
		schimbaCeva = True

		def render_POST(self, request):
			a = self._a(request)
			eu = a.get("eu", "")
			if not _EU.match(eu):
				return self._eroare(request, _t("Pagina nu e bună. Deschide din nou editorul."), 400)
			E = _E()
			nume = _nume_browser(request)

			def gata(s):
				_REZULTAT[eu] = {"fel": "deschis", "ora": time.time()}

			def eroare(e):
				_REZULTAT[eu] = {"fel": "eroare", "message": e.mesaj(), "ora": time.time()}

			def porneste():
				_REZULTAT.pop(eu, None)
				E.deschide_fundal(E.WEB, nume, gata, eroare, id_client=eu, preia=a.get("preia") == "1")
				return 200, {"result": True}

			try:
				return self._ruleaza(request, porneste)
			finally:
				pass

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class InchideResource(_Baza):
		schimbaCeva = True

		def render_POST(self, request):
			a = self._a(request)
			s = _sesiunea(a.get("eu", ""))

			def f():
				if s is not None:
					s.inchide()
				_REZULTAT.pop(a.get("eu", ""), None)
				return 200, {"result": True}
			return self._ruleaza(request, f)

		def render_GET(self, request):
			return self.render_POST(request)

	class BucheteResource(_Baza):
		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err
			return self._ruleaza(request, lambda: buchete(s, a))

	class IntrariResource(_Baza):
		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err
			return self._ruleaza(request, lambda: intrari(s, a))

	class ServiciiResource(_Baza):
		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err
			return self._ruleaza(request, lambda: servicii(s, a))

	class OpResource(_Baza):
		schimbaCeva = True

		def render_POST(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a, scrie=True)
			if s is None:
				return err
			o = _corp_json(request)
			if o is None:
				return self._eroare(request, _t("Cererea nu e bună."), 400)

			def f():
				inceput = time.time()
				rez = fa_operatia(s, o)
				_servicii_atinse(s, o, rez)
				durata = time.time() - inceput
				if durata > 0.2:
					_jurnal("operatia %s: %d ms" % (o.get("op"), durata * 1000))
				return 200, rez
			return self._ruleaza(request, f)

		def render_GET(self, request):
			return self._eroare(request, _t("Cererea nu e bună."), 405)

	class SalveazaResource(_Baza):
		schimbaCeva = True

		def render_POST(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a, scrie=True)
			if s is None:
				return err
			eu = a.get("eu", "")

			ce = {}

			def gata(c):
				_REZULTAT[eu] = {"fel": "salvat", "ora": time.time(), "copie": c.id if c is not None else "",
					"verificat": c.verificat if c is not None else None,
					"avertismente": list(c.avertismente) if c is not None else [],
					"diferente": dict(c.diferente) if c is not None else {}, "rezumat": ce.get("r")}

			def eroare(e):
				_REZULTAT[eu] = {"fel": "eroare", "message": e.mesaj(), "ora": time.time()}

			def f():
				_REZULTAT.pop(eu, None)
				try:
					ce["r"] = rezumat(s)
				except Exception as e:
					_jurnal("rezumatul: %r" % (e,))
				s.salveaza_fundal(gata, eroare)
				return 200, {"result": True}
			return self._ruleaza(request, f)

		def render_GET(self, request):
			return self.render_POST(request)

	class DetaliiResource(_Baza):
		"""GET /api/editor-canale-detalii?cheie= (Mod avansat)."""

		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err

			def f():
				refs = _chei(s, {"chei": [a.get("cheie", "")]})
				if not refs:
					raise _E().Eroare(_t("Canalul nu mai există în lista receptorului."))
				r = {"result": True}
				r.update(s.detalii(refs[0]))
				r["buchete_id"] = [b for b in s.in_buchete(refs[0]) if b in s.d.buchete]
				r["buchete"] = [s._info_buchet(s.d.buchete[b]).nume for b in r["buchete_id"]]
				r["pids"] = dict((str(k), v) for k, v in r["pids"].items())
				return 200, r
			return self._ruleaza(request, f)

	class TransponderResource(_Baza):
		"""GET /api/editor-canale-transponder?tp= (Mod avansat)."""

		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err

			def f():
				r = {"result": True}
				r.update(s.transponder(_tp(a.get("tp"))))
				r["poz"] = _poz_cod(r["poz"])
				return 200, r
			return self._ruleaza(request, f)

	class CopieResource(_Baza):
		"""GET /api/editor-canale-copie?id=: copia de siguranta, ca fisier tar.gz."""

		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err
			E = _E()
			id_ = a.get("id", "")
			if not E._id_bun(id_):
				return self._eroare(request, _t("Copia nu mai există."), 404)
			cale = os.path.join(E._dosar_copii(s.director), id_ + ".tar.gz")
			try:
				with open(cale, "rb") as fis:
					date = fis.read()
			except (IOError, OSError):
				return self._eroare(request, _t("Copia nu mai există."), 404)
			request.setResponseCode(200)
			request.setHeader(b"content-type", b"application/gzip")
			request.setHeader(b"content-disposition", ('attachment; filename="copie-lista-%s.tar.gz"' % id_).encode("ascii"))
			request.setHeader(b"cache-control", b"no-store")
			request.setHeader(b"x-content-type-options", b"nosniff")
			return date

	class SatelitiResource(_Baza):
		"""GET /api/editor-canale-sateliti[?poz=]: satellites.xml (cel schimbat in pagina, daca e unul nesalvat)."""

		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err

			def f():
				S = _S()
				sat = _SATELITI.get("s") or S.citeste()
				_SATELITI["s"] = sat
				r = {"result": True, "nesalvat": bool(_SATELITI.get("schimbat"))}
				if a.get("poz", "") != "":
					r["satelit"] = S.json_satelit(sat, a.get("poz"))
				else:
					r["sateliti"] = S.json(sat)
				return 200, r
			return self._ruleaza(request, f)

	class SatelitiOpResource(_Baza):
		"""POST /api/editor-canale-sateliti-op: o schimbare in satellites.xml, tinuta in memorie pana la op=salveaza
		(atunci copia fisierului vechi, scrierea, reincarcarea cand se poate) sau op=renunta."""
		schimbaCeva = True

		def render_POST(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a, scrie=True)
			if s is None:
				return err
			o = _corp_json(request)
			if o is None:
				return self._eroare(request, _t("Cererea nu e bună."), 400)

			def f():
				S = _S()
				op = o.get("op")
				if op == "renunta":
					_SATELITI.clear()
					return 200, {"result": True}
				sat = _SATELITI.get("s") or S.citeste()
				_SATELITI["s"] = sat
				poz = o.get("poz")
				v = o.get("valori") if isinstance(o.get("valori"), dict) else {}
				rez = {"result": True}
				if op == "salveaza":
					rez["copie"] = S.scrie(sat)
					rez["reincarcat"] = bool(S.reincarca())
					_SATELITI.clear()
					s.d.sateliti = _D().citeste_sateliti()
					return 200, rez
				if op == "satelit_nou":
					sat.satelit_nou(_text(o, "nume", 100), poz, _intreg(o.get("flags"), 1, 0, 255))
				elif op == "schimba_satelit":
					sat.schimba_satelit(poz, _text(o, "nume", 100) or None, o.get("pozitie_noua"), o.get("flags"))
				elif op == "sterge_satelit":
					sat.sterge_satelit(poz)
				elif op == "transponder_nou":
					sat.transponder_nou(poz, v)
				elif op == "schimba_transponder":
					sat.schimba_transponder(poz, _text(o, "cheie", 200), v)
				elif op == "sterge_transponder":
					sat.sterge_transponder(poz, _text(o, "cheie", 200))
				else:
					raise _E().Eroare(_t("Operația nu e cunoscută."))
				_SATELITI["schimbat"] = True
				rez["nesalvat"] = True
				return 200, rez
			return self._ruleaza(request, f)

	class SiglaResource(_Baza):
		"""POST /api/editor-canale-sigla?fel=copiaza|sterge|redenumeste|sterge_nefolosite (corpul JSON)."""
		schimbaCeva = True

		def render_POST(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a, scrie=True)
			if s is None:
				return err
			o = _corp_json(request) or {}

			def f():
				G = _G()
				fel = a.get("fel", "")
				if fel == "copiaza":
					din, la = _chei(s, {"chei": [o.get("din", "")]}), _chei(s, {"chei": [o.get("la", "")]})
					if not din or not la:
						raise _E().Eroare(_t("Canalul nu mai există în lista receptorului."))
					G.copiaza(din[0], la[0])
					n = 1
				elif fel == "sterge":
					refs = _chei(s, o)
					n = sum(G.sterge(r) for r in refs)
				elif fel == "redenumeste":
					perechi = [(sv.ref, sv.nume) for sv in s.d.lamedb.servicii.values()]
					n = G.redenumeste(G.REFERINTA if o.get("dupa") == "referinta" else G.NUME, perechi)
				elif fel == "sterge_nefolosite":
					cai = [c for c in (o.get("cai") or [])[:20000] if isinstance(c, str)]
					n = G.sterge_nefolosite(cai)
				else:
					raise _E().Eroare(_t("Operația nu e cunoscută."))
				return 200, {"result": True, "n": n}
			return self._ruleaza(request, f)

	class SchimbariResource(_Baza):
		"""GET /api/editor-canale-schimbari: ce s-a schimbat de la ultima salvare (numerele si buchetele)."""

		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err

			def f():
				r = {"result": True}
				r.update(rezumat(s))
				return 200, r
			return self._ruleaza(request, f)

	class CopiiResource(_Baza):
		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err

			def f():
				return 200, {"result": True, "copii": [[c.id, int(c.cand), c.descriere, c.marime, c.cine, c.servicii,
					c.buchete] for c in s.copii()]}
			return self._ruleaza(request, f)

	class IntoarceResource(_Baza):
		schimbaCeva = True

		def render_POST(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a, scrie=True)
			if s is None:
				return err
			eu = a.get("eu", "")

			def gata(c):
				_REZULTAT[eu] = {"fel": "intors", "ora": time.time(), "copie": c.id if c is not None else ""}

			def eroare(e):
				_REZULTAT[eu] = {"fel": "eroare", "message": e.mesaj(), "ora": time.time()}

			def f():
				_REZULTAT.pop(eu, None)
				s.intoarce_fundal(a.get("id", ""), gata, eroare)
				return 200, {"result": True}
			return self._ruleaza(request, f)

		def render_GET(self, request):
			return self.render_POST(request)

	class UnelteResource(_Baza):
		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a, scrie=True)
			if s is None:
				return err
			fel = a.get("fel", "")
			U = _U()
			functii = {"test": lambda: U.canale_test(s), "dubluri": lambda: U.dubluri(s),
				"moarte": lambda: U.referinte_moarte(s), "goale": lambda: [U.buchete_goale(s)],
				"transpondere": lambda: [U.transpondere_goale(s)],
				"compara": lambda: s.compara(a.get("id", "")),
				"verifica": lambda: s.verifica(),
				"compara_import": lambda: _compara_import(s),
				"sigle_nefolosite": lambda: [_sigle_nefolosite(s)],
				"fluxuri": lambda: [_U().fluxuri_care_nu_raspund(s)],
				"probleme": lambda: U.probleme(s)}
			if fel not in functii:
				return self._eroare(request, _t("Unealta nu e cunoscută."), 400)

			def gata(grupe):
				if fel == "probleme":
					_trimite(self, request, 200, {"result": True, "probleme": grupe})
					return
				_trimite(self, request, 200, {"result": True, "grupe": [grupa_json(g) for g in grupe]})

			def eroare(e):
				_trimite(self, request, 409, {"result": False, "message": e.mesaj()})

			try:
				s._unealta_fundal(functii[fel], gata, eroare)
			except Exception as e:
				E = _E()
				if isinstance(e, E.Eroare):
					return self._raspunde(request, {"result": False, "message": e.mesaj()}, 409)
				raise
			if NOT_DONE_YET is None:
				return b""
			return NOT_DONE_YET

	class ExportResource(_Baza):
		def render_GET(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a)
			if s is None:
				return err
			fel = a.get("fel", "tar.gz")
			try:
				if fel == "m3u":
					bid = a.get("buchet", "")
					if not _ID_BUCHET.match(bid) or bid not in s.d.buchete:
						return self._eroare(request, _t("Buchetul nu mai există."), 404)
					gazda = (request.getRequestHostname() or b"").decode("ascii", "replace") if hasattr(
						request, "getRequestHostname") else ""
					date = s.exporta_m3u(bid, gazda).encode("utf-8")
					nume = re.sub(r"[^A-Za-z0-9_.-]+", "_", bid) + ".m3u"
					tip = b"audio/x-mpegurl"
				else:
					fel = "zip" if fel == "zip" else "tar.gz"
					date = _U().arhiva_listei(s, fel)
					nume = "lista-canale-%s.%s" % (time.strftime("%Y%m%d-%H%M"), fel)
					tip = b"application/zip" if fel == "zip" else b"application/gzip"
			except Exception as e:
				_jurnal("exportul: %r" % (e,))
				return self._eroare(request, _t("Fișierul nu s-a putut face."), 500)
			request.setResponseCode(200)
			request.setHeader(b"content-type", tip)
			request.setHeader(b"content-disposition", ('attachment; filename="%s"' % nume).encode("ascii"))
			request.setHeader(b"cache-control", b"no-store")
			request.setHeader(b"x-content-type-options", b"nosniff")
			return date

	class ImportResource(_Baza):
		schimbaCeva = True

		def render_POST(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a, scrie=True)
			if s is None:
				return err
			try:
				request.content.seek(0)
				date = request.content.read(MAX_CORP_IMPORT + 1)
			except Exception:
				date = b""
			if not date or len(date) > MAX_CORP_IMPORT:
				return self._eroare(request, _t("Fișierul e gol sau prea mare."), 400)
			fel = a.get("fel", "arhiva")

			def f():
				E = _E()
				if fel == "sigla":
					refs = _chei(s, {"chei": [a.get("cheie", "")]})
					if not refs:
						raise E.Eroare(_t("Canalul nu mai există în lista receptorului."))
					_G().pune(refs[0], date)
					return 200, {"result": True}
				if fel == "m3u":
					nume = a.get("nume", "") or _t("Fluxuri")
					bid = s.importa_m3u(date, nume, a.get("radio") == "1", a.get("grupe") == "1")
					r = {"result": True, "buchet": bid}
					r.update(_info_sesiune(s))
					return 200, r
				shutil.rmtree(DOSAR_IMPORT, True)
				os.makedirs(DOSAR_IMPORT)
				try:
					rad = _U().despacheteaza_arhiva(date, DOSAR_IMPORT)
				except Exception as e:
					_jurnal("arhiva: %r" % (e,))
					shutil.rmtree(DOSAR_IMPORT, True)
					raise E.Eroare(_t("Arhiva nu se poate citi (merg zip, tar și tar.gz)."))
				if rad is None:
					shutil.rmtree(DOSAR_IMPORT, True)
					raise E.Eroare(_t("În arhivă nu e nicio listă de canale (lamedb sau bouquets.tv)."))
				ce = _U().ce_are_arhiva(rad)
				_IMPORT["dosar"] = rad
				return 200, {"result": True, "servicii": ce["servicii"], "transpondere": ce["transpondere"],
					"buchete": [list(b) for b in ce["buchete"]]}
			return self._ruleaza(request, f)

	class ImportAplicaResource(_Baza):
		schimbaCeva = True

		def render_POST(self, request):
			a = self._a(request)
			s, err = self._sesiune(request, a, scrie=True)
			if s is None:
				return err
			o = _corp_json(request) or {}

			def f():
				E = _E()
				rad = _IMPORT.get("dosar")
				if not rad or not os.path.isdir(rad):
					raise E.Eroare(_t("Arhiva nu mai e pe receptor. Alege-o din nou."))
				mod = "uneste" if o.get("mod") == "uneste" else "inlocuieste"
				ce = [x for x in (o.get("ce") or ["lamedb", "buchete"]) if x in ("lamedb", "buchete")]
				alese = [b for b in (o.get("buchete") or []) if isinstance(b, str) and _ID_BUCHET.match(b)] or None
				r = s.importa_dosar(rad, ce, alese, mod)
				shutil.rmtree(DOSAR_IMPORT, True)
				_IMPORT.pop("dosar", None)
				rez = {"result": True}
				rez.update(r)
				rez.update(_info_sesiune(s))
				return 200, rez
			return self._ruleaza(request, f)

	class FiltreResource(_Baza):
		"""GET /api/editor-canale-filtre: grupele filtrelor bazei noastre si mastile fiecarui canal (indexul cautarii,
		pe felii, prin executorul paginii /canale)."""

		def render_GET(self, request):
			a = self._a(request)
			if not _EU.match(a.get("eu", "")) or _sesiunea(a.get("eu", "")) is None:
				return self._eroare(request, _t("Editorul nu mai e deschis în această pagină. Deschide-l din nou."),
					409)
			try:
				from . import canale_web as CW
			except ImportError:
				return self._raspunde(request, {"result": True, "grupe": [], "masti": {}})
			Mx = CW._m()
			lucru = CW.PeBucati(gen_filtre(CW, Mx), lambda cod, corp: _trimite(self, request, cod, corp), Mx)
			try:
				request.notifyFinish().addErrback(lucru.opreste)
			except Exception:
				pass
			lucru.porneste()
			if NOT_DONE_YET is None:
				return b""
			return NOT_DONE_YET

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"editor-canale-stare": StareResource(),
		b"editor-canale-deschide": DeschideResource(),
		b"editor-canale-inchide": InchideResource(),
		b"editor-canale-buchete": BucheteResource(),
		b"editor-canale-intrari": IntrariResource(),
		b"editor-canale-servicii": ServiciiResource(),
		b"editor-canale-op": OpResource(),
		b"editor-canale-salveaza": SalveazaResource(),
		b"editor-canale-copii": CopiiResource(),
		b"editor-canale-schimbari": SchimbariResource(),
		b"editor-canale-detalii": DetaliiResource(),
		b"editor-canale-transponder": TransponderResource(),
		b"editor-canale-copie": CopieResource(),
		b"editor-canale-sateliti": SatelitiResource(),
		b"editor-canale-sateliti-op": SatelitiOpResource(),
		b"editor-canale-sigla": SiglaResource(),
		b"editor-canale-intoarce": IntoarceResource(),
		b"editor-canale-unelte": UnelteResource(),
		b"editor-canale-export": ExportResource(),
		b"editor-canale-import": ImportResource(),
		b"editor-canale-import-aplica": ImportAplicaResource(),
		b"editor-canale-filtre": FiltreResource(),
	}
	return api, PaginaResource()


_IMPORT = {}


def gen_filtre(CW, Mx, pas=200):
	"""Generator (executorul PeBucati din canale_web): indexul cautarii (cel din memorie sau pregatit in fundal), apoi
	grupele vizibile cu optiunile lor ([bit, eticheta, cate canale]) si mastile canalelor ({cheie: [masca pe grupa]}),
	ca pagina sa filtreze singura: SAU in grupa, SI intre grupe, ca pe televizor."""
	index = yield from CW.gen_index(Mx)
	try:
		from Components import HdsIndexCanale as X
	except ImportError:
		X = Mx.X
	grupuri = [g for g in index.grupuri_vizibile() if g not in ("tip",)]
	poz = [X.GRUPURI.index(g) for g in grupuri]
	grupe = []
	for g in grupuri:
		opt = []
		for v, eticheta, n in index.optiuni.get(g, ()):
			bit = index.biti.get(g, {}).get(v, 0)
			if bit:
				opt.append([bit, eticheta, n])
		grupe.append([g, X.titlu(g), opt])
	masti = {}
	for i, c in enumerate(index.canale):
		if i % pas == pas - 1:
			yield
		k = c.cheie_mas
		if k and c.masti is not None and k not in masti:
			masti[k] = [c.masti[j] for j in poz]
	return 200, {"result": True, "grupe": grupe, "masti": masti}


def _compara_import(s):
	rad = _IMPORT.get("dosar")
	if not rad or not os.path.isdir(rad):
		raise _E().Eroare(_t("Arhiva nu mai e pe receptor. Alege-o din nou."))
	return _U().compara_import(s, rad)


def _sigle_nefolosite(s):
	G, U = _G(), _U()
	refs = [sv.ref for sv in s.d.lamedb.servicii.values()]
	for b in s.d.buchete.values():
		refs.extend(i.ref for i in b.intrari if i.fel == "flux")
	nume = [sv.nume for sv in s.d.lamedb.servicii.values()]
	cai = G.nefolosite(refs, nume)
	return U.Grupa("sigle_nefolosite", _t("Sigle nefolosite"), _t("Siglele din dosarele de sigle care nu se potrivesc "
		"cu niciun canal din listă (nici după referință, nici după nume). Nimic nu e bifat."),
		[U.Rand(nume=os.path.basename(c), poz_text=os.path.dirname(c), cheie=c) for c in cai])


def grupa_json(g):
	rand = []
	for r in g.randuri:
		inl = r.inlocuire
		rand.append([r.cheie or "", r.ref or "", r.nume or "", r.poz_text or "", r.frecv or 0, r.pol or "", r.sid,
			None if r.are_video is None else (1 if r.are_video else 0),
			None if r.are_sunet is None else (1 if r.are_sunet else 0), r.buchete or 0, r.tp_text or "",
			r.buchet_id or "", r.id_intrare, (inl.nume + " · " + inl.poz_text + " · " + inl.tp_text) if inl else "",
			r.buchet_nume or "", r.grup or ""])
	return {"id": g.id, "titlu": g.titlu, "explicatie": g.explicatie, "randuri": rand}


def pagina(request):
	"""Aceeasi poarta ca /canale: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
	neconectat primeste pagina de asociere."""
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


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)


PAGINA = r"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Editorul de canale</title>
<style>__STIL_COMUN__
  body{font-size:16px;}
  main{max-width:1400px;margin:0 auto;}
  .ascuns{display:none !important;}
  button{font:inherit;}
  .sus{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin:0 0 10px;}
  h1{font-size:1.25rem;margin:0;flex:1 1 auto;}
  .file{display:inline-flex;border:1px solid var(--bordura);border-radius:10px;overflow:hidden;}
  .file button{background:transparent;color:var(--text);border:0;padding:0 16px;min-height:44px;cursor:pointer;}
  .file button[aria-selected="true"]{background:var(--albastru);color:#fff;}
  .buton{background:var(--panou);color:var(--text);border:1px solid var(--bordura);border-radius:10px;padding:0 14px;
    min-height:48px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px;
    text-decoration:none;}
  .buton:disabled{opacity:.45;cursor:default;}
  .buton.principal{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  .buton.rosu{background:var(--rosu);border-color:var(--rosu);color:#fff;}
  .buton.mic{min-height:40px;padding:0 10px;font-size:.92rem;}
  .actiuni-sus{display:flex;flex-wrap:wrap;gap:8px;align-items:center;}
  /* bloc, nu flex: altfel textul lung al schimbarii se taie in ambele parti; textul care nu incape se deruleaza
     (hds-derulant, cadru_web.py), inaltimea barei ramane aceeasi */
  #anuleaza{display:inline-block;line-height:46px;text-align:center;max-width:340px;overflow:hidden;
    white-space:nowrap;}
  .nesalvate{color:var(--galben);font-size:.92rem;}
  .panou-mesaj{background:var(--panou);border:1px solid var(--bordura);border-radius:12px;padding:16px;margin:12px 0;
    line-height:1.5;}
  .panou-mesaj .actiuni{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
  .comutare{display:none;}
  .comutare .file{display:flex;width:100%;}
  .comutare .file button{flex:1 1 50%;padding:0 8px;}
  .coloane{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:12px;}
  .panou{background:var(--panou);border:1px solid var(--bordura);border-radius:12px;display:flex;flex-direction:column;
    height:var(--inaltime-panou, calc(100vh - 150px));min-height:380px;min-width:0;}
  .cap{padding:10px 10px 6px;border-bottom:1px solid var(--bordura);display:flex;flex-direction:column;gap:8px;}
  .cap .rand-cap{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
  .titlu-panou{font-weight:600;flex:1 1 auto;min-width:0;overflow-wrap:anywhere;}
  .drum{display:flex;flex-wrap:wrap;gap:4px;align-items:center;font-size:.95rem;}
  .drum button{background:none;border:0;color:#7fb8ff;padding:6px 4px;min-height:36px;cursor:pointer;}
  .drum .sep{color:var(--text-slab);}
  .drum .nota-auto{flex-basis:100%;font-size:.85rem;color:var(--text-slab);border-left:3px solid var(--galben);padding:2px 8px;}
  input[type=search],input[type=text],input[type=number],input[type=url],select{background:var(--fundal);color:var(--text);
    border:1px solid var(--bordura);border-radius:10px;padding:0 12px;min-height:44px;font:inherit;width:100%;}
  .filtre{display:flex;flex-wrap:wrap;gap:6px;}
  .filtre button{background:transparent;color:var(--text);border:1px solid var(--bordura);border-radius:999px;
    padding:0 12px;min-height:36px;cursor:pointer;font-size:.9rem;}
  .filtre button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff;}
  .lista{flex:1 1 auto;overflow-y:auto;position:relative;outline:none;overscroll-behavior:contain;font-size:var(--marime-litere,1em);}
  .lista .semn.hd{border-color:#7fb8ff;color:#7fb8ff;}
  .lista .semn.nou{border-color:var(--galben);color:var(--galben);}
  .vedere textarea{width:100%;min-height:160px;font:inherit;}
  .grupa .actiune-grupa{margin:6px 0;}
  .lista:focus-visible{box-shadow:inset 0 0 0 2px var(--albastru);}
  .spatiu-lista{position:relative;width:100%;}
  .rand{position:absolute;left:0;right:0;height:56px;display:flex;align-items:center;gap:6px;padding:0 6px;
    border-bottom:1px solid var(--bordura);box-sizing:border-box;cursor:default;user-select:none;-webkit-user-select:none;
    touch-action:pan-y;}
  .rand.ales{background:rgba(47,111,168,.28);}
  .rand.focus{box-shadow:inset 3px 0 0 var(--albastru);}
  .rand.marcaj{background:rgba(255,255,255,.04);}
  .rand.marcaj .n{font-weight:700;color:var(--galben);}
  .rand.tinta-sus{box-shadow:inset 0 3px 0 var(--galben);}
  .rand .bifa{width:44px;height:44px;display:flex;align-items:center;justify-content:center;flex:0 0 44px;}
  .rand .bifa input{width:22px;height:22px;margin:0;}
  .rand .maner{width:36px;height:48px;flex:0 0 36px;display:flex;align-items:center;justify-content:center;
    color:var(--text-slab);cursor:grab;touch-action:none;font-size:20px;}
  .rand .nr{width:44px;flex:0 0 44px;text-align:right;color:var(--text-slab);font-variant-numeric:tabular-nums;
    font-size:.9rem;}
  .rand .sigla{width:50px;height:30px;flex:0 0 50px;object-fit:contain;}
  .rand .txt{flex:1 1 auto;min-width:0;}
  /* randul listei virtuale are inaltimea fixa: numele si detaliile pe un rand, taiate curat; cel care nu incape se
     deruleaza (hds-derulant, cadru_web.py) la randul ales, bifat sau cu mouse-ul, iar textul intreg e si in title */
  .rand .n{white-space:nowrap;overflow:hidden;text-overflow:clip;}
  .rand .d{white-space:nowrap;overflow:hidden;text-overflow:clip;color:var(--text-slab);font-size:.82rem;}
  .rand .semn{font-size:.75rem;border:1px solid var(--bordura);border-radius:6px;padding:1px 6px;color:var(--text-slab);
    white-space:nowrap;}
  .rand .semn.rau{color:#fff;background:var(--rosu);border-color:var(--rosu);}
  .rand .mai,.rand .plus,.rand .intra{width:44px;height:44px;flex:0 0 44px;border:0;background:none;color:var(--text);
    font-size:20px;cursor:pointer;border-radius:8px;}
  .rand .plus{color:var(--verde);font-size:26px;}
  .rand .mai:hover,.rand .plus:hover,.rand .intra:hover{background:rgba(255,255,255,.08);}
  .gol-lista{padding:24px 16px;color:var(--text-slab);line-height:1.5;}
  .bara-jos{border-top:1px solid var(--bordura);padding:8px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;}
  .bara-jos .buton{flex:1 1 0;min-width:0;}
  .bara-jos .info{flex:1 1 100%;font-size:.9rem;color:var(--text-slab);display:flex;justify-content:space-between;
    align-items:center;gap:8px;}
  .bara-jos .info button{background:none;border:0;color:#7fb8ff;cursor:pointer;min-height:36px;}
  #foaie{position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;
    z-index:1000;padding:16px;}
  #foaie .cutie{background:var(--panou);border:1px solid var(--bordura);border-radius:14px;width:min(520px,100%);
    max-height:calc(100vh - 32px);overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px;}
  #foaie h2{font-size:1.1rem;margin:0;}
  #foaie p{margin:0;line-height:1.5;}
  #foaie .lista-actiuni{display:flex;flex-direction:column;gap:6px;}
  #foaie .lista-actiuni .buton{justify-content:flex-start;text-align:left;width:100%;}
  #foaie .butoane{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;}
  #foaie .butoane .buton{flex:1 1 140px;}
  #foaie label.opt{display:flex;align-items:center;gap:10px;min-height:44px;}
  #foaie label.opt input{width:22px;height:22px;}
  .indent1{padding-left:24px !important;} .indent2{padding-left:44px !important;} .indent3{padding-left:64px !important;}
  #mesaj{position:fixed;left:50%;bottom:92px;transform:translateX(-50%);background:var(--panou);border:1px solid var(--bordura);
    border-radius:10px;padding:12px 16px;z-index:60;max-width:min(560px,calc(100% - 32px));box-shadow:0 6px 24px rgba(0,0,0,.4);}
  #mesaj.eroare{border-color:var(--rosu);}
  #fantoma{position:fixed;z-index:70;pointer-events:none;background:var(--albastru);color:#fff;border-radius:8px;
    padding:8px 12px;font-size:.92rem;box-shadow:0 6px 18px rgba(0,0,0,.4);}
  .vedere{background:var(--panou);border:1px solid var(--bordura);border-radius:12px;padding:12px;}
  .vedere .rand-cap{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px;}
  .vedere h2{font-size:1.1rem;margin:0;flex:1 1 auto;}
  .grupa{border-top:1px solid var(--bordura);padding:10px 0;}
  .grupa h3{font-size:1rem;margin:0 0 4px;}
  .grupa .expl{color:var(--text-slab);font-size:.9rem;margin:0 0 8px;line-height:1.4;}
  .grupa .rand-u{display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-bottom:1px solid var(--bordura);}
  .grupa .rand-u label{display:flex;gap:10px;align-items:flex-start;flex:1 1 auto;min-width:0;cursor:pointer;}
  .grupa .rand-u input{width:22px;height:22px;margin:10px 0 0;flex:0 0 22px;}
  .grupa .rand-u .n{font-weight:600;overflow-wrap:anywhere;}
  .grupa .rand-u .d{color:var(--text-slab);font-size:.85rem;overflow-wrap:anywhere;}
  .bara-vedere{position:sticky;bottom:0;background:var(--panou);border-top:1px solid var(--bordura);padding:8px 0 0;
    display:flex;flex-wrap:wrap;gap:8px;}
  .bara-vedere .buton{flex:1 1 200px;}
  @media (max-width:899px){
    body{padding:10px;}
    .sus{gap:6px;margin-bottom:6px;}
    .sus h1{display:none;}
    /* telefon: bara editorului ramane sus cand pagina coboara, iar filtrele stau pe un singur rand (se trag lateral) */
    body.cu-editor .sus{position:sticky;top:var(--sus-editor, 0px);z-index:20;background:var(--fundal);padding:6px 0;}
    #panouSursa .titlu-panou{display:none;}
    .bara-jos .info{font-size:.85rem;}
    .bara-jos .info button{min-height:40px;}
    .filtre{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;padding-bottom:2px;}
    .filtre::-webkit-scrollbar{display:none;}
    .filtre button{flex:0 0 auto;}
    body.cu-editor .comutare{display:block;flex:1 1 0;min-width:0;}
    .file button{padding:0 10px;}
    .comutare .file button{font-size:.92rem;line-height:1.15;}
    /* lista sursei derulata: randul filtrelor iese, ca sa se vada mai multe canale */
    .panou.strans .filtre{display:none;}
    /* mesajul scurt nu acopera bara de jos a panoului (butoanele): sta sub bara editorului */
    #mesaj{bottom:auto;top:calc(var(--sus-editor, 0px) + 116px);}
    #reface{display:none;}
    .rand .maner{width:28px;flex-basis:28px;}
    .rand .bifa{width:40px;flex-basis:40px;}
    .coloane{grid-template-columns:minmax(0,1fr);}
    .coloane .panou.ascuns-ingust{display:none;}
    .panou{height:var(--inaltime-panou, calc(100vh - 180px));}
    .rand .sigla{display:none;}
    .rand .nr{width:34px;flex-basis:34px;}
    #anuleaza{max-width:none;flex:1 1 auto;min-width:0;display:block;}
    .actiuni-sus{width:100%;flex-wrap:nowrap;}
    .actiuni-sus .buton{flex:0 0 auto;padding:0 10px;}
  }
</style>
</head>
<body>
<main>
<div class="sus">
  <h1>Editorul de canale</h1>
  <div class="file" role="tablist" aria-label="Felul listei">
    <button type="button" role="tab" id="filaTv" aria-selected="true">TV</button>
    <button type="button" role="tab" id="filaRadio" aria-selected="false">Radio</button>
  </div>
  <div class="comutare">
    <div class="file" role="tablist" aria-label="Ce vezi">
      <button type="button" role="tab" id="arataBuchet" aria-selected="true">Buchet</button>
      <button type="button" role="tab" id="arataSursa" aria-selected="false">Adaugă canale</button>
    </div>
  </div>
  <div class="actiuni-sus" id="actiuniSus">
    <button type="button" class="buton hds-derulant" id="anuleaza" disabled>Anulează schimbarea</button>
    <button type="button" class="buton" id="reface" disabled>Refă</button>
    <button type="button" class="buton principal" id="salveaza" disabled>Salvează</button>
    <button type="button" class="buton" id="maiMultSus">Mai mult</button>
  </div>
</div>
<div class="panou-mesaj" id="incarcare" aria-live="polite">Se citește lista de canale...</div>
<div class="panou-mesaj ascuns" id="ocupat">
  <div id="ocupatText"></div>
  <div class="actiuni">
    <button type="button" class="buton principal" id="preia">Preia lista aici</button>
    <button type="button" class="buton" id="incearca">Încearcă din nou</button>
  </div>
</div>
<div id="editor" class="ascuns">
  <div class="coloane">
    <section class="panou" id="panouSursa" aria-label="Adaugă canale">
      <div class="cap">
        <div class="rand-cap">
          <span class="titlu-panou">Adaugă canale</span>
          <div class="file" role="tablist" aria-label="De unde">
            <button type="button" role="tab" id="sursaToate" aria-selected="true">Toate</button>
            <button type="button" role="tab" id="sursaSateliti" aria-selected="false">Sateliți</button>
            <button type="button" role="tab" id="sursaFurnizori" aria-selected="false">Furnizori</button>
            <button type="button" role="tab" id="sursaBuchete" aria-selected="false">Buchete</button>
          </div>
        </div>
        <input id="cauta" type="search" maxlength="60" autocomplete="off" placeholder="Caută după nume, furnizor, SID sau frecvență" aria-label="Caută după nume, furnizor, SID sau frecvență">
        <div class="filtre" id="filtre" aria-label="Filtre">
          <button type="button" data-f="hd" aria-pressed="false">HD și 4K</button>
          <button type="button" data-f="sd" aria-pressed="false">SD</button>
          <button type="button" data-f="fta" aria-pressed="false">Necriptate</button>
          <button type="button" data-f="criptat" aria-pressed="false">Criptate</button>
          <button type="button" data-f="liber" aria-pressed="false">În niciun buchet</button>
          <button type="button" data-f="ascuns" aria-pressed="false">Ascunse</button>
          <button type="button" data-f="fara_sigla" aria-pressed="false">Fără siglă</button>
          <button type="button" data-f="hd_nume" aria-pressed="false">HD în nume, tip SD</button>
          <button type="button" data-f="noi" aria-pressed="false">Noi</button>
          <button type="button" data-f="blocate" aria-pressed="false">Blocate</button>
          <button type="button" id="maiMulteFiltre" aria-pressed="false">Limba, subtitrări și altele</button>
        </div>
        <div class="drum" id="drumSursa"></div>
      </div>
      <div class="lista" id="listaSursa" tabindex="0" aria-label="Canalele receptorului"></div>
      <div class="bara-jos" id="baraSursa"></div>
    </section>
    <section class="panou" id="panouBuchet" aria-label="Buchet">
      <div class="cap">
        <div class="drum" id="drumBuchet"></div>
      </div>
      <div class="lista" id="listaBuchet" tabindex="0" aria-label="Rândurile buchetului"></div>
      <div class="bara-jos" id="baraBuchet"></div>
    </section>
  </div>
</div>
<div id="vedere" class="vedere ascuns"></div>
</main>
<div id="foaie" class="ascuns" role="dialog" aria-modal="true"><div class="cutie" id="cutie"></div></div>
<div id="mesaj" class="ascuns" role="status" aria-live="polite"></div>
<input type="file" id="fisier" class="ascuns" accept=".zip,.tar,.gz,.tgz,.m3u,.m3u8">
<div id="texte" hidden>
  <span data-k="buchet">Buchet</span>
  <span data-k="buchete">Lista buchetelor</span>
  <span data-k="toate">Toate canalele</span>
  <span data-k="sateliti">Sateliți</span>
  <span data-k="furnizori">Furnizori</span>
  <span data-k="fara_furnizor">Fără furnizor</span>
  <span data-k="mai_mult">Mai mult</span>
  <span data-k="adauga">Adaugă</span>
  <span data-k="adauga_in">Adaugă în buchet</span>
  <span data-k="adauga_canale">Adaugă canale</span>
  <span data-k="muta_sus">Mută sus</span>
  <span data-k="muta_jos">Mută jos</span>
  <span data-k="muta_poz">Mută la poziția...</span>
  <span data-k="muta_in">Mută în...</span>
  <span data-k="copiaza_in">Copiază în...</span>
  <span data-k="sterge">Șterge</span>
  <span data-k="sterge_receptor">Șterge din receptor</span>
  <span data-k="redenumeste">Redenumește</span>
  <span data-k="redenumeste_tot">Redenumește peste tot</span>
  <span data-k="ascunde">Ascunde</span>
  <span data-k="arata">Arată</span>
  <span data-k="blocheaza">Blochează</span>
  <span data-k="deblocheaza">Deblochează</span>
  <span data-k="sorteaza">Sortează</span>
  <span data-k="sorteaza_alese">Sortează cele alese</span>
  <span data-k="sel_tot">Selectează tot</span>
  <span data-k="desel_tot">Deselectează tot</span>
  <span data-k="sel_grupa">Selectează grupa de sub marcaj</span>
  <span data-k="marcaj_nou">Marcaj nou</span>
  <span data-k="spatiu_nou">Rând gol nou</span>
  <span data-k="flux_nou">Flux nou (adresă de internet)</span>
  <span data-k="buchet_nou">Buchet nou</span>
  <span data-k="sub_buchet_nou">Sub-buchet nou</span>
  <span data-k="buchet_din_alese">Buchet nou din cele alese</span>
  <span data-k="buchet_din_satelit">Fă un buchet din acest satelit</span>
  <span data-k="buchet_din_furnizor">Fă un buchet din acest furnizor</span>
  <span data-k="deschide">Deschide</span>
  <span data-k="redenumeste_buchet">Redenumește buchetul</span>
  <span data-k="copiaza_buchet">Copiază buchetul</span>
  <span data-k="sterge_buchet">Șterge buchetul</span>
  <span data-k="blocheaza_buchet">Blochează buchetul</span>
  <span data-k="deblocheaza_buchet">Deblochează buchetul</span>
  <span data-k="exporta_buchet">Descarcă buchetul (m3u)</span>
  <span data-k="unelte_test">Canale de test</span>
  <span data-k="unelte_dubluri">Dubluri</span>
  <span data-k="unelte_moarte">Canale care nu mai există</span>
  <span data-k="unelte_goale">Buchete goale</span>
  <span data-k="nelegate">Buchete găsite pe disc, care nu sunt în listă</span>
  <span data-k="copii">Copii de siguranță</span>
  <span data-k="import_arhiva">Importă o listă (arhivă zip sau tar)</span>
  <span data-k="import_m3u">Importă fluxuri (m3u)</span>
  <span data-k="export_zip">Descarcă lista (zip)</span>
  <span data-k="export_tar">Descarcă lista (tar.gz)</span>
  <span data-k="ajutor">Ajutor</span>
  <span data-k="inchide_editor">Închide editorul</span>
  <span data-k="inapoi">Înapoi la editor</span>
  <span data-k="renunta">Renunță</span>
  <span data-k="gata">Gata</span>
  <span data-k="da">Da</span>
  <span data-k="nu">Nu</span>
  <span data-k="ok">Bine</span>
  <span data-k="nume">Numele</span>
  <span data-k="adresa">Adresa fluxului</span>
  <span data-k="pozitia">Poziția (numărul rândului)</span>
  <span data-k="anuleaza_x">Anulează: </span>
  <span data-k="anuleaza">Anulează schimbarea</span>
  <span data-k="salveaza">Salvează</span>
  <span data-k="reface">Refă</span>
  <span data-k="nesalvate_n">Schimbări nesalvate:</span>
  <span data-k="alese_n">Rânduri alese:</span>
  <span data-k="canale_n">Canale:</span>
  <span data-k="in_buchete">în buchete: </span>
  <span data-k="mort">nu mai există</span>
  <span data-k="ascuns">ascuns</span>
  <span data-k="blocat">blocat</span>
  <span data-k="lista_goala">Buchetul e gol. Adaugă canale din „Adaugă canale”.</span>
  <span data-k="nimic_gasit">Nu am găsit niciun canal.</span>
  <span data-k="se_citeste">Se citește lista de canale...</span>
  <span data-k="se_salveaza">Se salvează lista și se face copia de siguranță...</span>
  <span data-k="salvat">Salvat. Copia de siguranță e făcută, iar lista de pe televizor e la zi.</span>
  <span data-k="salvat_neverificat">Salvat. Lista din memorie nu s-a putut verifica.</span>
  <span data-k="salvat_diferente">Salvat, dar lista din memorie diferă de cea scrisă. Repornește interfața.</span>
  <span data-k="intors">Lista e cea din copia aleasă. Copia de dinainte e păstrată.</span>
  <span data-k="se_intoarce">Se pune înapoi copia...</span>
  <span data-k="intoarce">Întoarce la această copie</span>
  <span data-k="fara_copii">Nu e nicio copie de siguranță încă. Prima se face la prima salvare.</span>
  <span data-k="q_sterge_buchet">Ștergi canalele alese din acest buchet? Rămân în lista receptorului.</span>
  <span data-k="q_sterge_receptor">Ștergi canalele alese din receptor? Dispar și din toate buchetele. Poți anula până la salvare.</span>
  <span data-k="q_sterge_tot_buchetul">Ștergi tot buchetul? Canalele lui rămân în lista receptorului.</span>
  <span data-k="q_intoarce">Lista de acum se înlocuiește cu cea din copie. Înainte se face o copie a listei de acum.</span>
  <span data-k="q_iesire">Ai schimbări nesalvate. Dacă pleci acum, se pierd.</span>
  <span data-k="q_preia">Lista e deschisă în altă parte. Dacă o preiei, schimbările nesalvate de acolo se pierd.</span>
  <span data-k="unde_muti">Unde le muți?</span>
  <span data-k="unde_copiezi">Unde le copiezi?</span>
  <span data-k="sortare_dupa">Sortează după</span>
  <span data-k="dupa_nume">Nume</span>
  <span data-k="dupa_pozitie">Satelit și frecvență</span>
  <span data-k="dupa_furnizor">Furnizor</span>
  <span data-k="dupa_frecventa">Frecvență</span>
  <span data-k="dupa_sid">SID</span>
  <span data-k="invers">În ordine inversă</span>
  <span data-k="sortare_nota">Marcajele rămân pe loc: se sortează fiecare grupă de sub un marcaj.</span>
  <span data-k="peste_tot_nota">„Redenumește” schimbă numele numai în acest buchet. „Redenumește peste tot” îl schimbă în lista receptorului.</span>
  <span data-k="bifeaza_tot">Bifează tot</span>
  <span data-k="debifeaza_tot">Debifează tot</span>
  <span data-k="se_cauta">Se caută...</span>
  <span data-k="nimic_unealta">Nu am găsit nimic aici.</span>
  <span data-k="imagine">imagine</span>
  <span data-k="sunet">sunet</span>
  <span data-k="nu_se_stie">nu se știe</span>
  <span data-k="repara">Repară cele bifate</span>
  <span data-k="sterge_randuri">Șterge rândurile în plus bifate</span>
  <span data-k="sterge_bifate_receptor">Șterge din receptor cele bifate</span>
  <span data-k="inlocuire">se leagă la: </span>
  <span data-k="fara_inlocuire">se scoate din buchet</span>
  <span data-k="import_ce">Ce faci cu lista din arhivă?</span>
  <span data-k="import_inlocuieste">Înlocuiește lista de acum</span>
  <span data-k="import_uneste">Adaugă numai ce lipsește</span>
  <span data-k="import_buchete">Buchetele din arhivă (debifează ce nu vrei)</span>
  <span data-k="import_canale_text">canale și buchete în arhivă: </span>
  <span data-k="m3u_un_buchet">Un buchet, cu marcaje pe grupe</span>
  <span data-k="m3u_pe_grupe">Câte un buchet pe fiecare grupă</span>
  <span data-k="ajutor_text">Bifează rândurile, apoi alege ce faci cu butoanele de jos. Mânerul ≡ mută rândul trăgându-l. „Anulează” întoarce ultima schimbare. Nimic nu se scrie în receptor până nu apeși „Salvează”; înainte de fiecare salvare se face o copie de siguranță.</span>
  <span data-k="ajutor_taste">Pe calculator: săgețile aleg rândul, Shift + săgeți alege mai multe, Ctrl + săgeți mută, Spațiu bifează, Delete șterge, Ctrl+C / Ctrl+X / Ctrl+V copiază, taie și lipește, Ctrl+Z / Ctrl+Y anulează și reface, Ctrl+A alege tot, Ctrl+S salvează, F2 redenumește.</span>
  <span data-k="lipit">Lipit.</span>
  <span data-k="copiat">Copiate. Alege locul și apasă Ctrl+V.</span>
  <span data-k="pierdut">Editorul nu mai e deschis în această pagină.</span>
  <span data-k="deschide_iar">Deschide din nou</span>
  <span data-k="eroare_retea">Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.</span>
  <span data-k="deja">Erau deja în buchet.</span>
  <span data-k="alege_buchet">Deschide întâi un buchet, apoi adaugă canalele.</span>
  <span data-k="trage">Trage ca să muți</span>
  <span data-k="actiuni_rand">Acțiunile rândului</span>
  <span data-k="probleme">Am găsit în listă: </span>
  <span data-k="vezi">Vezi</span>
  <span data-k="lega">Pune în listă</span>
  <span data-k="filtre_baza">Filtrele bazei de canale</span>
  <span data-k="filtre_nota">În aceeași grupă opțiunile bifate se adună cu «sau», între grupe cu «și». Numărul arată câte canale au opțiunea.</span>
  <span data-k="sterge_filtrele">Șterge filtrele</span>
  <span data-k="filtre_citire">Se citesc filtrele...</span>
  <span data-k="arata_buchet">Arată buchetul</span>
  <span data-k="ascunde_buchet">Ascunde buchetul</span>
  <span data-k="scoate_din_toate">Scoate din toate buchetele</span>
  <span data-k="q_scoate_din_toate">Le scoți din toate buchetele? Rămân în lista receptorului.</span>
  <span data-k="porneste_tv">Pornește pe televizor</span>
  <span data-k="pornit_tv">Pornit pe televizor.</span>
  <span data-k="sterge_nelegat">Șterge de pe disc</span>
  <span data-k="q_sterge_nelegat">Fișierul buchetului se șterge la salvare. Poți anula până atunci.</span>
  <span data-k="pe_transpondere">Pe transpondere</span>
  <span data-k="toate_satelitului">Toate canalele satelitului</span>
  <span data-k="buchet_din_tp">Fă un buchet din acest transponder</span>
  <span data-k="sterge_tp">Șterge transponderul</span>
  <span data-k="q_sterge_tp">Ștergi transponderul din receptor, cu toate canalele lui? Dispar și din buchete. Poți anula până la salvare.</span>
  <span data-k="buchete_din_alese">Fă câte un buchet din fiecare ales</span>
  <span data-k="unelte_tp">Transpondere fără canale</span>
  <span data-k="sterge_tp_bifate">Șterge transponderele bifate</span>
  <span data-k="transpondere_n">Transpondere:</span>
  <span data-k="q_sterge_tp_goale">Le ștergi din lista receptorului? Nu au niciun canal. Poți anula până la salvare.</span>
  <span data-k="schimbari">Ce s-a schimbat de la ultima salvare</span>
  <span data-k="fara_schimbari">Nimic schimbat de la ultima salvare.</span>
  <span data-k="s_noi">Canale noi:</span>
  <span data-k="s_sterse">Canale șterse:</span>
  <span data-k="s_schimbate">Canale schimbate:</span>
  <span data-k="b_schimbate">Buchete schimbate:</span>
  <span data-k="b_noi">Buchete noi:</span>
  <span data-k="b_sterse">Buchete șterse:</span>
  <span data-k="lista_schimbata">Lista buchetelor s-a schimbat (ordinea sau buchetele ascunse).</span>
  <span data-k="parental_schimbat">Blocările s-au schimbat.</span>
  <span data-k="compara">Compară cu lista de acum</span>
  <span data-k="sursa_buchete">Buchete</span>
  <span data-k="alternative_noi">Unește ca alternative (același canal din alte locuri)</span>
  <span data-k="alternative_desface">Desface alternativele</span>
  <span data-k="muta_satelit">Mută satelitul pe altă poziție...</span>
  <span data-k="copiaza_satelit">Copiază satelitul pe altă poziție...</span>
  <span data-k="f_hd_nume">HD în nume, tip SD</span>
  <span data-k="f_noi">Noi</span>
  <span data-k="f_blocate">Blocate</span>
  <span data-k="nou_semn">nou</span>
  <span data-k="internet_semn">internet</span>
  <span data-k="detalii">Detalii</span>
  <span data-k="scoate_din_unul">Scoate dintr-un buchet...</span>
  <span data-k="din_care_buchet">Din ce buchet îl scoți?</span>
  <span data-k="pune_sigla">Pune siglă...</span>
  <span data-k="copiaza_sigla">Copiază sigla de la alt canal...</span>
  <span data-k="sterge_sigla">Șterge sigla</span>
  <span data-k="sigla_pusa">Sigla e pusă.</span>
  <span data-k="sigla_numai_dvb">Alege o imagine (PNG, JPG): se micșorează la 220 x 132 și se pune ca siglă.</span>
  <span data-k="scoate_nou">Scoate semnul „nou”</span>
  <span data-k="editeaza_flux">Editează fluxul</span>
  <span data-k="tip_flux">Tipul fluxului</span>
  <span data-k="numere_dvb">Numerele DVB ale fluxului (pentru siglă): SID, TSID, ONID, namespace (hex)</span>
  <span data-k="aranjeaza_dupa">Aranjează după alt buchet...</span>
  <span data-k="scoate_marcajele">Scoate marcajele din buchet</span>
  <span data-k="descarca_csv">Descarcă tabelul (CSV)</span>
  <span data-k="lipeste_nume">Lipește o listă de nume...</span>
  <span data-k="lipeste_nota">Câte un nume de canal pe rând. Cele găsite se adaugă în buchet, în ordinea din listă.</span>
  <span data-k="gasite_negasite">Găsite / negăsite:</span>
  <span data-k="dupa_poz_nume">Satelit, apoi nume</span>
  <span data-k="dupa_furn_nume">Furnizor, apoi nume</span>
  <span data-k="sorteaza_buchetele">Sortează buchetele alese</span>
  <span data-k="sterge_satelitii">Șterge din receptor</span>
  <span data-k="pastreaza_satelitii">Păstrează numai cei bifați</span>
  <span data-k="q_sterge_satelitii">Toate canalele și transponderele sateliților bifați se șterg din receptor și din buchete. Poți anula până la salvare.</span>
  <span data-k="q_pastreaza_satelitii">Se șterg din receptor toate canalele celorlalți sateliți (și din buchete). Poți anula până la salvare.</span>
  <span data-k="sateliti_n">Sateliți:</span>
  <span data-k="verifica">Verifică lista</span>
  <span data-k="curatenie">Curățenie</span>
  <span data-k="arata_ascunse">Arată toate canalele ascunse</span>
  <span data-k="deblocheaza_tot">Deblochează toate canalele</span>
  <span data-k="scoate_nou_tot">Scoate semnul „nou” de pe toate canalele</span>
  <span data-k="fluxuri">Fluxuri care nu răspund</span>
  <span data-k="sigle">Sigle</span>
  <span data-k="sigle_nefolosite">Sigle nefolosite</span>
  <span data-k="redenumeste_sigle_ref">Redenumește siglele după referință</span>
  <span data-k="redenumeste_sigle_nume">Redenumește siglele după nume</span>
  <span data-k="inlocuieste_nume">Înlocuiește în nume...</span>
  <span data-k="cauta_text">Caută</span>
  <span data-k="inlocuieste_cu">Înlocuiește cu</span>
  <span data-k="in_buchete_si">Și în numele buchetelor</span>
  <span data-k="previzualizare">Se schimbă:</span>
  <span data-k="inlocuieste">Înlocuiește</span>
  <span data-k="marime_litere">Mărimea literelor</span>
  <span data-k="mai_mari">Mai mari</span>
  <span data-k="mai_mici">Mai mici</span>
  <span data-k="avansat_pornit">Mod avansat: pornit</span>
  <span data-k="avansat_oprit">Mod avansat: oprit</span>
  <span data-k="avansat_nota">Modul avansat arată și editarea transponderelor, a fișierului satellites.xml și a detaliilor canalelor. Greșelile de acolo pot opri canalele.</span>
  <span data-k="sateliti_xml">Sateliți și transpondere (satellites.xml)</span>
  <span data-k="satelit_nou">Satelit nou</span>
  <span data-k="salveaza_sateliti">Salvează satellites.xml</span>
  <span data-k="renunta_sateliti">Renunță la schimbări</span>
  <span data-k="sateliti_nota">Schimbările se scriu în satellites.xml numai la „Salvează satellites.xml”, cu o copie înainte. Nu intră în „Anulează”.</span>
  <span data-k="sateliti_reincarcat">satellites.xml e salvat și receptorul îl folosește.</span>
  <span data-k="sateliti_repornire">satellites.xml e salvat; se vede după repornirea interfeței.</span>
  <span data-k="transpondere_btn">Transpondere</span>
  <span data-k="transponder_nou">Transponder nou</span>
  <span data-k="editeaza">Editează</span>
  <span data-k="pozitia_sat">Poziția (de pildă 19.2E sau 30W)</span>
  <span data-k="editeaza_tp">Editează transponderul</span>
  <span data-k="tp_nou_lista">Transponder nou în lista de canale</span>
  <span data-k="tp_nou_nota">Transponderul nou n-are canale: o căutare pe el le aduce.</span>
  <span data-k="frecventa_mhz">Frecvența (MHz)</span>
  <span data-k="sr_ks">Rata de simbol (kS/s)</span>
  <span data-k="polarizare">Polarizarea</span>
  <span data-k="sistem">Sistemul</span>
  <span data-k="modulatie">Modulația</span>
  <span data-k="salveaza_btn">Salvează</span>
  <span data-k="furnizor">Furnizorul</span>
  <span data-k="steaguri">Steagurile</span>
  <span data-k="pids">PID-uri ținute minte (cod:valoare hex)</span>
  <span data-k="st_ascuns">Ascuns în listă</span>
  <span data-k="st_nume">Păstrează numele la scanare</span>
  <span data-k="st_nou">Nou găsit</span>
  <span data-k="st_nosdt">Fără SDT</span>
  <span data-k="st_nodvb">Fără DVB</span>
  <span data-k="buchet_din_bifate">Buchet nou din cele bifate</span>
  <span data-k="adu_inapoi">Adu înapoi cele bifate</span>
  <span data-k="sterge_marcajele_bifate">Șterge marcajele bifate</span>
  <span data-k="scoate_din_buchete_bifate">Scoate din buchete cele bifate</span>
  <span data-k="sterge_siglele_bifate">Șterge siglele bifate</span>
  <span data-k="vezi_ce_se_schimba">Vezi ce se schimbă</span>
  <span data-k="inapoi_import">Înapoi la import</span>
  <span data-k="descarca">Descarcă</span>
  <span data-k="sfat_1">Sfat: bifează rândurile, apoi folosește butoanele de jos. Nimic nu se scrie în receptor până la „Salvează”.</span>
  <span data-k="toate_buchetele">Toate</span>
  <span data-k="buchete_satelit">Satelit</span>
  <span data-k="buchete_internet">Internet</span>
  <span data-k="referinta">Referința</span>
  <span data-k="in_buchetele">În buchetele</span>
  <span data-k="namespace">Namespace</span>
  <span data-k="tip">Tip</span>
  <span data-k="auto">Auto</span>
  <span data-k="rolloff">Roll-off</span>
  <span data-k="pilot">Pilot</span>
  <span data-k="oprit">Oprit</span>
  <span data-k="pornit">Pornit</span>
  <span data-k="mis">MIS (is_id)</span>
  <span data-k="pls_cod">Codul PLS</span>
  <span data-k="pls_mod">Modul PLS</span>
  <span data-k="pls_root">Root</span>
  <span data-k="pls_gold">Gold</span>
  <span data-k="pls_combo">Combo</span>
</div>
<script>
var CFG = __CONFIG__;
var H = 56, LATIME_DOUA = 900, MAX_PAGINA = 3000;
function $(id){ return document.getElementById(id); }
var TX = {};
(function(){ var l = document.querySelectorAll("#texte span"); for(var i = 0; i < l.length; i++){ TX[l[i].getAttribute("data-k")] = l[i].textContent; } })();
function L(k){ return TX[k] || k; }
// numarul dupa eticheta („Canale: 3”): fara acordul formei cu numarul, care in unele limbi are trei forme
function nCanale(n){ return L("canale_n") + " " + n; }
function nAlese(n){ return L("alese_n") + " " + n; }
function el(tag, clasa, text){
  var e = document.createElement(tag);
  if(clasa){ e.className = clasa; }
  if(text !== undefined && text !== null){ e.textContent = text; }
  return e;
}
function gol(e){ while(e.firstChild){ e.removeChild(e.firstChild); } }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
var EU = (function(){
  var a = new Uint8Array(12), s = "";
  (window.crypto || window.msCrypto).getRandomValues(a);
  for(var i = 0; i < a.length; i++){ s += ("0" + a[i].toString(16)).slice(-2); }
  return s;
})();
function cerere(cale, metoda, corp, tip, incercari){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(corp !== undefined && corp !== null){
    optiuni.headers["Content-Type"] = tip || "application/json";
    optiuni.body = tip ? corp : JSON.stringify(corp);
  }
  var cu = cale + (cale.indexOf("?") === -1 ? "?" : "&") + "eu=" + EU;
  return fetch(adresa(cu), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("deconectat"); }
    return r.json().catch(function(){ return {result: false, message: L("eroare_retea")}; });
  }, function(){ return {result: false, message: L("eroare_retea"), retea: true}; }).then(function(j){
    // editorul lucreaza (o unealta, salvarea): aceeasi cerere peste putin, cel mult un minut
    if(j && j.lucreaza && (incercari || 0) < 150){
      return new Promise(function(gata){ setTimeout(gata, 400); }).then(function(){ return cerere(cale, metoda, corp, tip, (incercari || 0) + 1); });
    }
    return j;
  });
}
var S = {radio: false, gata: false, versiune: 0, drum: ["bouquets.tv"], numeDrum: {}, randuri: [], sel: {}, nsel: 0,
  focus: -1, ancora: -1, sv: [], svRadio: null, sateliti: [], sursa: "toate", sursaPoz: null, sursaFurn: null, filtre: {},
  text: "", vazute: [], fb: null, fsel: {}, nfb: 0, ssel: {}, nssel: 0, sfocus: -1, sancora: -1, panou: "buchet", clip: null, deAnulat: null,
  deRefacut: null, nesalvate: 0, arbore: [], lucru: false, vedere: null, ceas: null, plecat: false,
  lsel: {}, peTp: false, sursaTp: null, sursaBuchet: null, sursaRanduri: null, automat: "", felBuchete: "toate",
  avansat: citeste("hds-editor-avansat") === "1", marime: parseFloat(citeste("hds-editor-marime") || "1") || 1};
// ce tine minte browserul (modul avansat, marimea literelor, filtrele, sfaturile vazute); fara el pagina merge la fel
function citeste(k){ try { return window.localStorage.getItem(k); } catch(e){ return null; } }
function tine(k, v){ try { window.localStorage.setItem(k, v); } catch(e){} }
document.documentElement.style.setProperty("--marime-litere", S.marime + "em");
(function(){ try { var f = JSON.parse(citeste("hds-editor-filtre") || "{}"); for(var k in f){ if(f[k]){ S.filtre[k] = true; } } } catch(e){} })();

function mesaj(text, eroare){
  var m = $("mesaj");
  m.textContent = text;
  m.className = eroare ? "eroare" : "";
  clearTimeout(mesaj.ceas);
  mesaj.ceas = setTimeout(function(){ m.className = "ascuns"; }, eroare ? 7000 : 3500);
}

// ---------------------------------------------------------------- foaia (o singura fereastra simpla)
function foaie(titlu, continut, butoane){
  var c = $("cutie");
  gol(c);
  if(titlu){ c.appendChild(el("h2", "", titlu)); }
  (continut || []).forEach(function(x){ if(x){ c.appendChild(typeof x === "string" ? el("p", "", x) : x); } });
  if(butoane && butoane.length){
    var b = el("div", "butoane");
    butoane.forEach(function(x){
      var e = el("button", "buton" + (x.clasa ? " " + x.clasa : ""), x.text);
      e.type = "button";
      e.onclick = function(){ if(x.fa){ if(x.fa() === false){ return; } } inchideFoaia(); };
      b.appendChild(e);
    });
    c.appendChild(b);
  }
  $("foaie").classList.remove("ascuns");
  var f = c.querySelector("input,button");
  if(f){ setTimeout(function(){ f.focus(); }, 30); }
}
function inchideFoaia(){ $("foaie").classList.add("ascuns"); }
$("foaie").addEventListener("click", function(ev){ if(ev.target === $("foaie")){ inchideFoaia(); } });
function listaActiuni(titlu, actiuni, nota){
  var l = el("div", "lista-actiuni");
  actiuni.forEach(function(a){
    if(!a){ return; }
    var b = el("button", "buton" + (a.clasa ? " " + a.clasa : ""), a.text);
    if(a.indent){ b.classList.add("indent" + a.indent); }
    b.type = "button";
    b.onclick = function(){ inchideFoaia(); a.fa(); };
    l.appendChild(b);
  });
  foaie(titlu, [nota ? el("p", "", nota) : null, l], [{text: L("renunta")}]);
}
function intreaba(text, daText, fa, rosu){
  foaie("", [text], [{text: L("renunta")}, {text: daText, clasa: rosu ? "rosu" : "principal", fa: fa}]);
}
function cereText(titlu, eticheta, valoare, fa, tip){
  var i = el("input");
  i.type = tip || "text";
  i.value = valoare || "";
  i.setAttribute("aria-label", eticheta);
  i.maxLength = tip === "url" ? 900 : 120;
  var lbl = el("label", "", eticheta);
  lbl.style.display = "flex"; lbl.style.flexDirection = "column"; lbl.style.gap = "6px";
  lbl.appendChild(i);
  i.addEventListener("keydown", function(ev){ if(ev.key === "Enter"){ ev.preventDefault(); inchideFoaia(); fa(i.value); } });
  foaie(titlu, [lbl], [{text: L("renunta")}, {text: L("ok"), clasa: "principal", fa: function(){ fa(i.value); }}]);
  setTimeout(function(){ i.focus(); i.select(); }, 40);
}

// ---------------------------------------------------------------- lista virtuala
function ListaVirtuala(cutie, deseneaza){
  this.cutie = cutie; this.deseneaza = deseneaza; this.n = 0; this.desenate = {};
  this.spatiu = el("div", "spatiu-lista"); cutie.appendChild(this.spatiu);
  this.golText = null;
  var t = this;
  cutie.addEventListener("scroll", function(){ t.arata(); }, {passive: true});
  window.addEventListener("resize", function(){ t.arata(true); });
}
ListaVirtuala.prototype.pune = function(n, golText){
  this.n = n; this.spatiu.style.height = (n * H) + "px";
  this.golText = golText;
  this.arata(true);
};
ListaVirtuala.prototype.arata = function(tot){
  var sus = this.cutie.scrollTop, inalt = this.cutie.clientHeight || 600;
  var de = Math.max(0, Math.floor(sus / H) - 8), la = Math.min(this.n, Math.ceil((sus + inalt) / H) + 8);
  var noi = {}, i;
  if(tot){ gol(this.spatiu); this.desenate = {}; }
  if(!this.n && this.golText){ this.spatiu.appendChild(el("div", "gol-lista", this.golText)); }
  for(i = de; i < la; i++){
    var r = this.desenate[i];
    if(!r){ r = this.deseneaza(i); r.style.top = (i * H) + "px"; this.spatiu.appendChild(r); }
    noi[i] = r;
  }
  for(var k in this.desenate){ if(!noi[k] && this.desenate[k].parentNode){ this.spatiu.removeChild(this.desenate[k]); } }
  this.desenate = noi;
};
// randul cu cursorul: cu aria-current si textul lui care nu incape se deruleaza (hds-derulant-rand, cadru_web.py)
function cursor(d, da){
  d.classList.toggle("focus", da);
  if(da){ d.setAttribute("aria-current", "true"); } else { d.removeAttribute("aria-current"); }
}
// selectia si randul ales puse pe randurile deja desenate, fara sa le faca din nou: un rand facut din nou sub mouse sau
// sub deget pierde tragerea inceputa pe el si dublul clic
function redaSel(){
  var k, d, c;
  for(k in VB.desenate){
    d = VB.desenate[k]; var r = S.randuri[k];
    if(!r){ continue; }
    var a = !!S.sel[r[0]];
    d.classList.toggle("ales", a); cursor(d, +k === S.focus);
    c = d.querySelector(".bifa input"); if(c){ c.checked = a; }
  }
  if(S.lista || !S.vazute){ return; }
  for(k in VS.desenate){
    d = VS.desenate[k]; var x = S.sv[S.vazute[k]];
    if(!x){ continue; }
    var b = !!S.ssel[x[0]];
    d.classList.toggle("ales", b); cursor(d, +k === S.sfocus);
    c = d.querySelector(".bifa input"); if(c){ c.checked = b; }
  }
}
ListaVirtuala.prototype.laVedere = function(i){
  var sus = this.cutie.scrollTop, inalt = this.cutie.clientHeight;
  if(i * H < sus){ this.cutie.scrollTop = i * H; }
  else if((i + 1) * H > sus + inalt){ this.cutie.scrollTop = (i + 1) * H - inalt; }
};
ListaVirtuala.prototype.indiceLa = function(y){
  var r = this.cutie.getBoundingClientRect();
  return Math.max(0, Math.min(this.n, Math.round((y - r.top + this.cutie.scrollTop) / H)));
};

// ---------------------------------------------------------------- starea sesiunii
function puneStarea(r){
  if(!r){ return; }
  if(typeof r.versiune === "number"){ S.versiune = r.versiune; }
  if("de_anulat" in r){ S.deAnulat = r.de_anulat; S.deRefacut = r.de_refacut; S.nesalvate = r.nesalvate || 0; }
  var a = $("anuleaza");
  a.disabled = !S.deAnulat || S.lucru;
  a.textContent = S.deAnulat ? L("anuleaza_x") + S.deAnulat : L("anuleaza");
  a.title = a.textContent;
  $("reface").disabled = !S.deRefacut || S.lucru;
  $("salveaza").disabled = !S.nesalvate || S.lucru;
  $("salveaza").textContent = L("salveaza") + (S.nesalvate ? " (" + S.nesalvate + ")" : "");
  $("salveaza").title = S.nesalvate ? L("nesalvate_n") + " " + S.nesalvate : "";
}
function arataOcupat(o){
  $("incarcare").classList.add("ascuns");
  $("editor").classList.add("ascuns");
  $("vedere").classList.add("ascuns");
  $("ocupat").classList.remove("ascuns");
  $("ocupatText").textContent = (o && o.mesaj) || L("pierdut");
}
function deschide(preia){
  S.gata = false;
  $("ocupat").classList.add("ascuns");
  $("incarcare").classList.remove("ascuns");
  $("incarcare").textContent = L("se_citeste");
  cerere("/api/editor-canale-deschide" + (preia ? "?preia=1" : ""), "POST").then(function(r){
    if(!r.result){
      if(r.message && !r.retea){ arataOcupat({mesaj: r.message}); } else { $("incarcare").textContent = r.message || L("eroare_retea"); }
      return;
    }
    asteapta(function(){ incarcaTot(); });
  });
}
function asteapta(dupa){
  S.lucru = true; puneStarea({});
  clearTimeout(S.ceas);
  cerere("/api/editor-canale-stare").then(function(r){
    if(r.rezultat && r.rezultat.fel === "eroare"){ S.lucru = false; puneStarea({}); mesaj(r.rezultat.message, true);
      if(!r.a_mea){ arataOcupat(r.ocupat); } return; }
    if(!r.a_mea){ S.lucru = false; arataOcupat(r.ocupat); return; }
    if(r.lucreaza){ S.ceas = setTimeout(function(){ asteapta(dupa); }, 500); return; }
    S.lucru = false;
    puneStarea(r);
    dupa(r);
    bataie();
  });
}
function bataie(){
  clearTimeout(S.ceas);
  S.ceas = setTimeout(function(){
    if(S.lucru){ return; }
    cerere("/api/editor-canale-stare").then(function(r){
      if(r.result && !r.a_mea && S.gata){ S.gata = false; arataOcupat(r.ocupat); return; }
      if(r.result && r.a_mea && !r.lucreaza && r.versiune !== S.versiune){ puneStarea(r); incarcaBuchet(); incarcaServicii(); }
      bataie();
    });
  }, 20000);
}
function incarcaTot(){
  S.gata = true;
  $("incarcare").classList.add("ascuns");
  $("ocupat").classList.add("ascuns");
  $("editor").classList.remove("ascuns");
  document.body.classList.add("cu-editor");
  potrivesteInaltimea();
  S.drum = [radacina()];
  if(!citeste("hds-editor-sfaturi")){
    tine("hds-editor-sfaturi", "1");
    setTimeout(function(){ foaie(L("ajutor"), [L("sfat_1"), L("ajutor_text"), L("ajutor_taste")], [{text: L("ok"), clasa: "principal"}]); }, 600);
  }
  incarcaArbore().then(incarcaBuchet).then(incarcaServicii).then(function(){
    return cerere("/api/editor-canale-unelte?fel=probleme");
  }).then(function(r){
    if(!r.result || !r.probleme){ return; }
    var p = r.probleme, parti = [];
    if(p.fara_nume || p.test){ parti.push(L("unelte_test") + ": " + ((p.fara_nume || 0) + (p.test || 0))); }
    if(p.moarte){ parti.push(L("unelte_moarte") + ": " + p.moarte); }
    if(p.in_buchet){ parti.push(L("unelte_dubluri") + ": " + p.in_buchet); }
    if(p.nelegate){ parti.push(L("nelegate") + ": " + p.nelegate); }
    if(parti.length){ mesaj(L("probleme") + parti.join(" · ")); }
  });
}
function radacina(){ return S.radio ? "bouquets.radio" : "bouquets.tv"; }
function buchetAcum(){ return S.drum[S.drum.length - 1]; }
function laRadacina(){ return buchetAcum() === radacina(); }

// ---------------------------------------------------------------- buchetul
var VB = new ListaVirtuala($("listaBuchet"), desenRandBuchet);
var VS = new ListaVirtuala($("listaSursa"), desenRandSursa);
$("listaSursa").addEventListener("scroll", function(){
  var strans = ingust() && this.scrollTop > 40;
  if(strans !== $("panouSursa").classList.contains("strans")){ $("panouSursa").classList.toggle("strans", strans); VS.arata(); }
}, {passive: true});

function incarcaArbore(){
  return cerere("/api/editor-canale-buchete?radio=" + (S.radio ? 1 : 0)).then(function(r){
    if(r.result){ S.arbore = r.arbore; S.nelegate = r.nelegate; r.arbore.forEach(function(b){ S.numeDrum[b[0]] = b[1]; }); }
    return r;
  });
}
function incarcaBuchet(pastreaza){
  var bid = buchetAcum();
  return cerere("/api/editor-canale-intrari?buchet=" + encodeURIComponent(bid)).then(function(r){
    if(r.pierdut){ S.gata = false; arataOcupat(r.ocupat); return; }
    if(!r.result){
      if(S.drum.length > 1){ S.drum.pop(); return incarcaBuchet(); }
      mesaj(r.message || L("eroare_retea"), true); return;
    }
    S.numeDrum[bid] = r.nume;
    S.randuri = r.randuri;
    if(laRadacina() && S.felBuchete !== "toate"){
      S.randuri = r.randuri.filter(function(x){ return x[1] !== "b" || esteInternet(x[7]) === (S.felBuchete === "internet"); });
    }
    S.automat = r.automat || "";
    var ids = {};
    r.randuri.forEach(function(x){ ids[x[0]] = true; });
    var sel = {}, n = 0;
    for(var k in S.sel){ if(ids[k]){ sel[k] = true; n++; } }
    S.sel = sel; S.nsel = n;
    if(S.focus >= r.randuri.length){ S.focus = r.randuri.length - 1; }
    puneStarea(r);
    deseneazaDrum();
    VB.pune(r.randuri.length, laRadacina() ? "" : L("lista_goala"));
    if(!pastreaza){ /* locul ramane */ }
    deseneazaBaraBuchet();
    deseneazaBaraSursa();
  });
}
function deseneazaDrum(){
  var d = $("drumBuchet");
  gol(d);
  S.drum.forEach(function(bid, i){
    if(i){ d.appendChild(el("span", "sep", "›")); }
    var b = el("button", "", i === 0 ? L("buchete") : (S.numeDrum[bid] || bid));
    b.type = "button";
    if(i === S.drum.length - 1){ b.style.color = "var(--text)"; b.style.fontWeight = "600"; }
    b.onclick = function(){ S.drum = S.drum.slice(0, i + 1); S.sel = {}; S.nsel = 0; S.focus = -1; incarcaBuchet(); };
    d.appendChild(b);
  });
  if(S.automat){ d.appendChild(el("div", "nota-auto", S.automat)); }
  if(laRadacina() && (S.arbore || []).some(function(b){ return b[7]; })){
    [["toate", "toate_buchetele"], ["satelit", "buchete_satelit"], ["internet", "buchete_internet"]].forEach(function(x){
      var b = buton(L(x[1]), function(){ S.felBuchete = x[0]; S.sel = {}; S.nsel = 0; incarcaBuchet(); }, "mic");
      b.setAttribute("aria-pressed", S.felBuchete === x[0] ? "true" : "false");
      if(S.felBuchete === x[0]){ b.style.fontWeight = "700"; }
      d.appendChild(b);
    });
  }
}
function esteInternet(bid){
  for(var i = 0; i < (S.arbore || []).length; i++){ if(S.arbore[i][0] === bid){ return !!S.arbore[i][7]; } }
  return false;
}
function esteMarcaj(r){ return r[1] === "m" || r[1] === "g"; }
function desenRandBuchet(i){
  var r = S.randuri[i], d = el("div", "rand hds-derulant-rand");
  d.dataset.i = i;
  if(S.sel[r[0]]){ d.classList.add("ales"); }
  if(i === S.focus){ cursor(d, true); }
  if(esteMarcaj(r)){ d.classList.add("marcaj"); }
  var bifa = el("label", "bifa"), c = el("input");
  c.type = "checkbox"; c.checked = !!S.sel[r[0]];
  c.setAttribute("aria-label", r[2] || L("buchet"));
  c.addEventListener("change", function(){ comutaSel(i, c.checked); });
  bifa.appendChild(c); d.appendChild(bifa);
  var m = el("span", "maner", "≡");
  m.title = L("trage"); m.setAttribute("aria-hidden", "true");
  m.addEventListener("pointerdown", function(ev){ incepeTragerea(ev, "buchet", i); });
  d.appendChild(m);
  if(!laRadacina()){ d.appendChild(el("span", "nr", r[3] ? String(r[3]) : "")); }
  if(r[8]){
    var img = el("img", "sigla"); img.alt = ""; img.loading = "lazy";
    img.onerror = function(){ img.style.visibility = "hidden"; };
    img.src = adresa("/api/canale-sigla?p=" + encodeURIComponent(r[8]));
    d.appendChild(img);
  }
  var t = el("div", "txt");
  var nume = r[2] || (r[1] === "g" ? "" : "?");
  t.appendChild(el("div", "n hds-derulant", (r[1] === "b" ? "📁 " : r[1] === "f" ? "🌐 " : "") + nume));
  var det = r[6] || "";
  if(r[1] === "b"){ det = ""; }
  t.appendChild(el("div", "d hds-derulant", det));
  d.appendChild(t);
  if(r[9] === "HD" || r[9] === "UHD"){ d.appendChild(el("span", "semn hd", r[9])); }
  if(r[1] === "b" && esteInternet(r[7])){ d.appendChild(el("span", "semn", L("internet_semn"))); }
  t.title = [nume, det].filter(Boolean).join("\n");
  if(r[4] & 4){ d.appendChild(el("span", "semn rau", L("mort"))); }
  if(r[4] & 1){ d.appendChild(el("span", "semn", L("ascuns"))); }
  if(r[4] & 2){ d.appendChild(el("span", "semn", L("blocat"))); }
  if(r[1] === "b" || r[1] === "a"){
    var intra = el("button", "intra", "›"); intra.type = "button"; intra.setAttribute("aria-label", L("deschide"));
    intra.onclick = function(ev){ ev.stopPropagation(); intraIn(r[7], r[2]); };
    d.appendChild(intra);
  }
  var mai = el("button", "mai", "⋯"); mai.type = "button"; mai.setAttribute("aria-label", L("actiuni_rand"));
  mai.onclick = function(ev){ ev.stopPropagation(); if(!S.sel[r[0]]){ alegeNumai(i); } meniuBuchet(); };
  d.appendChild(mai);
  d.addEventListener("click", function(ev){
    if(ev.target.closest("button,input,.maner")){ return; }
    clicRand(i, ev);
  });
  d.addEventListener("dblclick", function(ev){
    if(ev.target.closest("button,input")){ return; }
    if(r[1] === "b" || r[1] === "a"){ intraIn(r[7], r[2]); }
  });
  d.addEventListener("contextmenu", function(ev){ ev.preventDefault(); if(!S.sel[r[0]]){ alegeNumai(i); } meniuBuchet(); });
  return d;
}
function intraIn(bid, nume){
  if(!bid){ return; }
  S.numeDrum[bid] = nume;
  S.drum.push(bid); S.sel = {}; S.nsel = 0; S.focus = -1;
  $("listaBuchet").scrollTop = 0;
  incarcaBuchet();
}
function clicRand(i, ev){
  S.focus = i;
  if(ev && ev.shiftKey && S.ancora >= 0){
    alegeIntre(S.ancora, i);
  } else if(ev && (ev.ctrlKey || ev.metaKey)){
    comutaSel(i, !S.sel[S.randuri[i][0]]);
    S.ancora = i;
  } else {
    comutaSel(i, !S.sel[S.randuri[i][0]]);
    S.ancora = i;
  }
  redaSel();
}
function comutaSel(i, da){
  var id = S.randuri[i][0];
  if(da && !S.sel[id]){ S.sel[id] = true; S.nsel++; }
  else if(!da && S.sel[id]){ delete S.sel[id]; S.nsel--; }
  S.focus = i;
  redaSel();
  deseneazaBaraBuchet();
}
function alegeNumai(i){ S.sel = {}; S.nsel = 0; comutaSel(i, true); S.ancora = i; }
function alegeIntre(a, b){
  var de = Math.min(a, b), la = Math.max(a, b);
  for(var k = de; k <= la; k++){ var id = S.randuri[k][0]; if(!S.sel[id]){ S.sel[id] = true; S.nsel++; } }
  deseneazaBaraBuchet();
}
function alesele(){ return S.randuri.filter(function(r){ return S.sel[r[0]]; }); }
function idsAlese(){ return alesele().map(function(r){ return r[0]; }); }
function selTot(da){
  S.sel = {}; S.nsel = 0;
  if(da){ S.randuri.forEach(function(r){ S.sel[r[0]] = true; }); S.nsel = S.randuri.length; }
  redaSel(); deseneazaBaraBuchet();
}
function buton(text, fa, clasa){
  var b = el("button", "buton" + (clasa ? " " + clasa : ""), text); b.type = "button"; b.onclick = fa; return b;
}
function ingust(){ return window.innerWidth < LATIME_DOUA; }
function deseneazaBaraBuchet(){
  var b = $("baraBuchet");
  gol(b);
  if(S.nsel){
    var info = el("div", "info");
    info.appendChild(el("span", "", nAlese(S.nsel)));
    var d = el("button", "", L("desel_tot")); d.type = "button"; d.onclick = function(){ selTot(false); };
    info.appendChild(d);
    b.appendChild(info);
    b.appendChild(buton(L("muta_sus"), function(){ op({op: "muta_sus", buchet: buchetAcum(), ids: idsAlese()}); }));
    b.appendChild(buton(L("muta_jos"), function(){ op({op: "muta_jos", buchet: buchetAcum(), ids: idsAlese()}); }));
    b.appendChild(buton(L("sterge"), stergeAlese, "rosu"));
    b.appendChild(buton(L("mai_mult"), meniuBuchet));
  } else {
    if(laRadacina()){
      b.appendChild(buton(L("buchet_nou"), function(){ buchetNou(null); }, "principal"));
    } else if(ingust()){
      b.appendChild(buton(L("adauga_canale"), function(){ comutaPanou("sursa"); }, "principal"));
    } else {
      b.appendChild(buton(L("marcaj_nou"), function(){ marcajNou(null); }));
    }
    b.appendChild(buton(L("sorteaza"), function(){ sortare(false); }));
    b.appendChild(buton(L("mai_mult"), meniuBuchet));
  }
}
function stergeAlese(){
  var a = alesele();
  if(!a.length){ return; }
  if(laRadacina()){
    if(a.length === 1){ return stergeBuchetul(a[0][7], a[0][2]); }
  }
  intreaba(nAlese(a.length) + ". " + L("q_sterge_buchet"), L("sterge"), function(){
    op({op: "scoate", buchet: buchetAcum(), ids: idsAlese()}, true);
  }, true);
}
function stergeBuchetul(bid, nume){
  intreaba((nume || bid) + ": " + L("q_sterge_tot_buchetul"), L("sterge_buchet"), function(){
    op({op: "sterge_buchet", buchet: bid}, true).then(function(){ incarcaArbore(); });
  }, true);
}
function cheiAlese(){ return alesele().filter(function(r){ return r[5]; }).map(function(r){ return r[5]; }); }
function meniuBuchet(){
  var a = alesele(), bid = buchetAcum(), act = [];
  var unul = a.length === 1 ? a[0] : null, chei = cheiAlese();
  if(a.length){
    act.push({text: L("muta_poz"), fa: mutaLaPozitie});
    act.push({text: L("muta_in"), fa: function(){ alegeBuchetTinta(L("unde_muti"), "muta_in"); }});
    act.push({text: L("copiaza_in"), fa: function(){ alegeBuchetTinta(L("unde_copiezi"), "copiaza"); }});
    if(unul){ act.push({text: L("redenumeste"), fa: function(){ redenumeste(unul, false); }}); }
    if(unul && unul[1] === "c" && !(unul[4] & 4)){ act.push({text: L("redenumeste_tot"), fa: function(){ redenumeste(unul, true); }}); }
    if(unul && (unul[1] === "b" || unul[1] === "a")){ act.push({text: L("deschide"), fa: function(){ intraIn(unul[7], unul[2]); }}); }
    if(unul && unul[1] === "b"){ act.push({text: unul[4] & 1 ? L("arata_buchet") : L("ascunde_buchet"), fa: function(){ op({op: "ascunde_buchet", buchet: unul[7], da: !(unul[4] & 1)}).then(function(){ incarcaArbore(); }); }}); }
    if(unul && unul[1] === "a"){ act.push({text: L("alternative_desface"), fa: function(){ op({op: "alternative_desface", buchet: bid, ids: [unul[0]]}, true); }}); }
    if(!laRadacina() && a.every(function(r){ return r[1] === "c" && !(r[4] & 4); })){ act.push({text: L("alternative_noi"), fa: function(){ op({op: "alternative_noi", buchet: bid, ids: idsAlese()}, true); }}); }
    if(unul && unul[1] === "c" && unul[5] && !(unul[4] & 4)){ act.push({text: L("porneste_tv"), fa: function(){ pornesteTv(unul[5]); }}); }
    if(unul && unul[1] === "c" && unul[5] && !(unul[4] & 4)){
      act.push({text: L("detalii"), fa: function(){ arataDetalii(unul[5]); }});
      act.push({text: L("pune_sigla"), fa: function(){ puneSigla(unul[5]); }});
      act.push({text: L("copiaza_sigla"), fa: function(){ copiazaSigla(unul[5]); }});
      if(unul[8]){ act.push({text: L("sterge_sigla"), clasa: "rosu", fa: function(){ stergeSigla(unul[5]); }}); }
      act.push({text: L("scoate_din_unul"), fa: function(){ scoateDinUnul(unul[5]); }});
    }
    if(unul && unul[1] === "f"){ act.push({text: L("editeaza_flux"), fa: function(){ editeazaFlux(unul); }}); }
    if(laRadacina() && a.length > 1 && a.every(function(r){ return r[1] === "b"; })){ act.push({text: L("sorteaza_buchetele"), fa: function(){ sortare(false, a.map(function(r){ return r[7]; })); }}); }
    if(unul && unul[1] === "m"){ act.push({text: L("sel_grupa"), fa: function(){ alegeGrupa(S.randuri.indexOf(unul)); }}); }
    if(chei.length){
      var toateAscunse = a.every(function(r){ return r[4] & 1; }), toateBlocate = a.every(function(r){ return r[4] & 2; });
      act.push({text: toateAscunse ? L("arata") : L("ascunde"), fa: function(){ op({op: "ascunde", chei: chei, da: !toateAscunse}); }});
      act.push({text: toateBlocate ? L("deblocheaza") : L("blocheaza"), fa: function(){ op({op: "blocheaza", chei: chei, da: !toateBlocate}); }});
    }
    if(a.length > 1){ act.push({text: L("sorteaza_alese"), fa: function(){ sortare(true); }}); }
    if(laRadacina() && unul){
      act.push({text: unul[4] & 2 ? L("deblocheaza_buchet") : L("blocheaza_buchet"), fa: function(){ op({op: "blocheaza_buchet", buchet: unul[7], da: !(unul[4] & 2)}); }});
      act.push({text: L("copiaza_buchet"), fa: function(){ op({op: "copiaza_buchet", buchet: unul[7]}).then(function(){ incarcaArbore(); }); }});
      act.push({text: L("sterge_buchet"), clasa: "rosu", fa: function(){ stergeBuchetul(unul[7], unul[2]); }});
    }
    if(chei.length){ act.push({text: L("scoate_din_toate"), fa: function(){ scoateDinToate(chei); }}); }
    if(chei.length){ act.push({text: L("sterge_receptor"), clasa: "rosu", fa: function(){ stergeDinReceptor(chei); }}); }
    act.push({text: L("marcaj_nou"), fa: function(){ marcajNou(a[0][0]); }});
    act.push({text: L("sel_tot"), fa: function(){ selTot(true); }});
    act.push({text: L("desel_tot"), fa: function(){ selTot(false); }});
  } else {
    if(laRadacina()){
      act.push({text: L("buchet_nou"), fa: function(){ buchetNou(null); }});
      (S.nelegate || []).forEach(function(n){
        act.push({text: L("lega") + ": " + n[1], fa: function(){ op({op: "leaga_buchet", buchet: n[0]}).then(function(){ incarcaArbore(); }); }});
        act.push({text: L("sterge_nelegat") + ": " + n[1], clasa: "rosu", fa: function(){
          intreaba(n[1] + ". " + L("q_sterge_nelegat"), L("sterge_nelegat"), function(){ op({op: "sterge_nelegat", buchet: n[0]}).then(function(){ incarcaArbore(); }); }, true);
        }});
      });
    } else {
      act.push({text: L("marcaj_nou"), fa: function(){ marcajNou(null); }});
      act.push({text: L("spatiu_nou"), fa: function(){ op({op: "spatiu_nou", buchet: bid}); }});
      act.push({text: L("flux_nou"), fa: fluxNou});
      act.push({text: L("sub_buchet_nou"), fa: function(){ buchetNou(bid); }});
      act.push({text: L("redenumeste_buchet"), fa: function(){
        cereText(L("redenumeste_buchet"), L("nume"), S.numeDrum[bid], function(v){ op({op: "redenumeste_buchet", buchet: bid, nume: v}).then(function(){ S.numeDrum[bid] = v; incarcaArbore(); deseneazaDrum(); }); });
      }});
      act.push({text: L("copiaza_buchet"), fa: function(){ op({op: "copiaza_buchet", buchet: bid}).then(function(){ incarcaArbore(); }); }});
      act.push({text: L("exporta_buchet"), fa: function(){ descarca("/api/editor-canale-export?fel=m3u&buchet=" + encodeURIComponent(bid)); }});
      act.push({text: L("descarca_csv"), fa: descarcaCsv});
      act.push({text: L("lipeste_nume"), fa: lipesteNume});
      act.push({text: L("aranjeaza_dupa"), fa: function(){
        listaActiuni(L("aranjeaza_dupa"), S.arbore.filter(function(b){ return b[0] !== bid; }).map(function(b){
          return {text: b[1] + "  (" + nCanale(b[2]) + ")", indent: Math.min(3, b[3]), fa: function(){ op({op: "aranjeaza_dupa", buchet: bid, model: b[0]}); }};
        }));
      }});
      if(S.randuri.some(function(r){ return esteMarcaj(r); })){ act.push({text: L("scoate_marcajele"), fa: function(){
        op({op: "scoate", buchet: bid, ids: S.randuri.filter(esteMarcaj).map(function(r){ return r[0]; })}, true);
      }}); }
      if(bid.indexOf("favourites") === -1){
        act.push({text: L("sterge_buchet"), clasa: "rosu", fa: function(){
          stergeBuchetul(bid, S.numeDrum[bid]);
          S.drum.pop();
        }});
      }
    }
    act.push({text: L("sorteaza"), fa: function(){ sortare(false); }});
    act.push({text: L("sel_tot"), fa: function(){ selTot(true); }});
  }
  listaActiuni(a.length ? nAlese(a.length) : (S.numeDrum[bid] || L("buchet")), act);
}
function alegeGrupa(i){
  if(i < 0){ return; }
  for(var k = i + 1; k < S.randuri.length && S.randuri[k][1] !== "m"; k++){
    var id = S.randuri[k][0]; if(!S.sel[id]){ S.sel[id] = true; S.nsel++; }
  }
  redaSel(); deseneazaBaraBuchet();
}
function mutaLaPozitie(){
  cereText(L("muta_poz"), L("pozitia") + " (1 - " + S.randuri.length + ")", "", function(v){
    var p = parseInt(v, 10);
    if(!(p >= 1)){ return; }
    op({op: "muta", buchet: buchetAcum(), ids: idsAlese(), pozitie: p});
  }, "number");
}
function alegeBuchetTinta(titlu, fel){
  var act = [];
  if(fel === "muta_in" || fel === "copiaza"){
    S.arbore.forEach(function(b){
      if(b[0] === buchetAcum()){ return; }
      act.push({text: b[1] + "  (" + nCanale(b[2]) + ")", indent: Math.min(3, b[3]), fa: function(){
        op({op: fel, din: buchetAcum(), "in": b[0], ids: idsAlese()}).then(function(){ incarcaArbore(); });
      }});
    });
  }
  listaActiuni(titlu, act);
}
function redenumeste(r, pesteTot){
  cereText(pesteTot ? L("redenumeste_tot") : L("redenumeste"), L("nume"), r[2], function(v){
    if(laRadacina()){ op({op: "redenumeste_buchet", buchet: r[7], nume: v}).then(function(){ incarcaArbore(); }); return; }
    op({op: "redenumeste", buchet: buchetAcum(), ids: [r[0]], nume: v, peste_tot: !!pesteTot, chei: r[5] ? [r[5]] : []});
  });
}
function marcajNou(inainte){
  cereText(L("marcaj_nou"), L("nume"), "", function(v){
    op({op: "marcaj_nou", buchet: buchetAcum(), nume: v, inainte_de: inainte});
  });
}
function fluxNou(){
  var a = el("input"); a.type = "url"; a.placeholder = "http://"; a.setAttribute("aria-label", L("adresa"));
  var n = el("input"); n.type = "text"; n.setAttribute("aria-label", L("nume"));
  var la = el("label", "", L("adresa")); la.style.display = "flex"; la.style.flexDirection = "column"; la.style.gap = "6px"; la.appendChild(a);
  var ln = el("label", "", L("nume")); ln.style.display = "flex"; ln.style.flexDirection = "column"; ln.style.gap = "6px"; ln.appendChild(n);
  var inainte = S.nsel ? idsAlese()[0] : null;
  foaie(L("flux_nou"), [la, ln], [{text: L("renunta")}, {text: L("ok"), clasa: "principal", fa: function(){
    op({op: "flux_nou", buchet: buchetAcum(), adresa: a.value, nume: n.value, inainte_de: inainte});
  }}]);
}
function buchetNou(parinte, chei){
  cereText(parinte ? L("sub_buchet_nou") : L("buchet_nou"), L("nume"), "", function(v){
    op({op: "buchet_nou", nume: v, radio: S.radio, parinte: parinte, chei: chei || []}).then(function(r){
      incarcaArbore();
      if(r && r.buchet && !parinte && !chei){ intraIn(r.buchet, v); }
    });
  });
}
function sortare(numaiAlese, buchete){
  var inv = el("input"); inv.type = "checkbox";
  var lbl = el("label", "opt"); lbl.appendChild(inv); lbl.appendChild(document.createTextNode(L("invers")));
  var l = el("div", "lista-actiuni");
  [["nume", "dupa_nume"], ["pozitie", "dupa_pozitie"], ["pozitie_nume", "dupa_poz_nume"], ["furnizor", "dupa_furnizor"],
    ["furnizor_nume", "dupa_furn_nume"], ["frecventa", "dupa_frecventa"], ["sid", "dupa_sid"]].forEach(function(x){
    l.appendChild(buton(L(x[1]), function(){
      inchideFoaia();
      if(buchete){ op({op: "sorteaza_buchete", buchete: buchete, dupa: x[0], invers: inv.checked}); return; }
      op({op: "sorteaza", buchet: buchetAcum(), dupa: x[0], invers: inv.checked, ids: numaiAlese ? idsAlese() : []});
    }));
  });
  foaie(L("sortare_dupa"), [numaiAlese ? null : el("p", "", L("sortare_nota")), l, lbl], [{text: L("renunta")}]);
}
function scoateDinToate(chei){
  intreaba(nCanale(chei.length) + ". " + L("q_scoate_din_toate"), L("scoate_din_toate"), function(){
    op({op: "scoate_din_toate", chei: chei}, true).then(function(r){ if(r){ incarcaArbore(); } });
  }, true);
}
function pornesteTv(cheie){
  var i = S.svIndex ? S.svIndex[cheie] : undefined;
  if(i === undefined){ return; }
  cerere("/api/zap?sRef=" + encodeURIComponent(S.sv[i][1]), "POST").then(function(r){
    if(r && r.result){ mesaj(L("pornit_tv")); } else { mesaj((r && r.message) || L("eroare_retea"), true); }
  });
}
function stergeTp(cheie, text){
  var n = 0;
  S.sv.forEach(function(x){ if(x[15] === cheie){ n++; } });
  intreaba(text + " · " + nCanale(n) + ". " + L("q_sterge_tp"), L("sterge_tp"), function(){
    op({op: "sterge_transpondere", tpuri: [cheie]}, true).then(function(r){ if(r){ S.sursaTp = null; filtreaza(); } });
  }, true);
}
function bucheteDinAlese(){
  var l = [];
  for(var k in S.lsel){ l.push(S.lsel[k]); }
  if(!l.length){ return; }
  var fel = l[0].fel === "sat" ? "satelit" : "furnizor";
  op({op: "buchete_din", fel: fel, valori: l.map(function(g){ return fel === "satelit" ? g.poz : g.nume; }), radio: S.radio}).then(function(r){
    if(r){ S.lsel = {}; VS.arata(true); deseneazaBaraSursa(); incarcaArbore(); mesaj(r.de_anulat || ""); }
  });
}
function textRezumat(z){
  if(!z){ return ""; }
  var p = [];
  if(z.servicii_noi){ p.push(L("s_noi") + " " + z.servicii_noi); }
  if(z.servicii_sterse){ p.push(L("s_sterse") + " " + z.servicii_sterse); }
  if(z.servicii_schimbate){ p.push(L("s_schimbate") + " " + z.servicii_schimbate); }
  function nume(l){ return l.length + " (" + l.slice(0, 6).join(", ") + (l.length > 6 ? ", ..." : "") + ")"; }
  if(z.buchete_noi && z.buchete_noi.length){ p.push(L("b_noi") + " " + nume(z.buchete_noi)); }
  if(z.buchete_sterse && z.buchete_sterse.length){ p.push(L("b_sterse") + " " + nume(z.buchete_sterse)); }
  if(z.buchete && z.buchete.length){ p.push(L("b_schimbate") + " " + nume(z.buchete)); }
  if(z.lista && !(z.buchete_noi && z.buchete_noi.length) && !(z.buchete_sterse && z.buchete_sterse.length)){ p.push(L("lista_schimbata")); }
  if(z.parental){ p.push(L("parental_schimbat")); }
  return p.join(" · ");
}
function arataSchimbari(){
  cerere("/api/editor-canale-schimbari").then(function(r){
    if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
    var t = textRezumat(r);
    foaie(L("schimbari"), [t || L("fara_schimbari")], r.nesalvate ?
      [{text: L("renunta")}, {text: L("salveaza"), clasa: "principal", fa: salveaza}] : [{text: L("ok"), clasa: "principal"}]);
  });
}
function arataDetalii(cheie){
  cerere("/api/editor-canale-detalii?cheie=" + encodeURIComponent(cheie)).then(function(r){
    if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
    var p = [];
    p.push(r.nume + " · " + (r.furnizor || L("fara_furnizor")));
    p.push(L("referinta") + ": " + r.ref);
    p.push("SID " + r.sid + " (0x" + r.sid.toString(16) + ") · TSID " + r.tsid + " · ONID " + r.onid + " · " + L("namespace") + " " + r.ns + " · " + L("tip") + " " + r.tip);
    p.push([r.poz_text, r.tp_text].filter(Boolean).join(" · "));
    var pids = []; for(var k in r.pids){ pids.push(k + ":" + ("000" + r.pids[k].toString(16)).slice(-4)); }
    if(pids.length){ p.push("PID: " + pids.join(" ")); }
    if(r.caids.length){ p.push("CAID: " + r.caids.join(" ")); }
    if(r.buchete.length){ p.push(L("in_buchetele") + ": " + r.buchete.join(", ")); }
    if(!S.avansat){ foaie(L("detalii"), p, [{text: L("ok"), clasa: "principal"}]); return; }
    var furn = el("input"); furn.type = "text"; furn.value = r.furnizor || "";
    var lf = el("label", "", L("furnizor")); lf.style.display = "flex"; lf.style.flexDirection = "column"; lf.appendChild(furn);
    var bife = [[2, "st_ascuns"], [8, "st_nume"], [64, "st_nou"], [1, "st_nosdt"], [4, "st_nodvb"]].map(function(x){
      var lab = el("label", "opt"), c = el("input"); c.type = "checkbox"; c.checked = !!(r.steaguri & x[0]);
      lab.appendChild(c); lab.appendChild(document.createTextNode(L(x[1]))); return [c, x[0], lab];
    });
    var pid = el("input"); pid.type = "text"; pid.value = pids.join(" ");
    var lp = el("label", "", L("pids")); lp.style.display = "flex"; lp.style.flexDirection = "column"; lp.appendChild(pid);
    foaie(L("detalii"), p.map(function(x){ return el("p", "", x); }).concat([lf, el("p", "", L("steaguri"))], bife.map(function(b){ return b[2]; }), [lp]),
      [{text: L("renunta")}, {text: L("salveaza_btn"), clasa: "principal", fa: function(){
        var st = 0; bife.forEach(function(b){ if(b[0].checked){ st |= b[1]; } });
        var pd = {}, bun = true;
        pid.value.trim().split(/\s+/).filter(Boolean).forEach(function(x){
          var m = /^(\d{1,2}):([0-9a-f]{1,4})$/i.exec(x); if(!m){ bun = false; return; } pd[String(parseInt(m[1], 10))] = parseInt(m[2], 16);
        });
        if(!bun){ mesaj(L("pids"), true); return false; }
        op({op: "schimba_serviciu", chei: [cheie], furnizor: furn.value, steaguri: st, pids: pd}).then(function(){ incarcaServicii(); });
      }}]);
  });
}
function scoateDinUnul(cheie){
  cerere("/api/editor-canale-detalii?cheie=" + encodeURIComponent(cheie)).then(function(r){
    if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
    listaActiuni(L("din_care_buchet"), (r.buchete_id || []).map(function(bid, i){
      return {text: r.buchete[i] || bid, fa: function(){ op({op: "scoate_canale", buchet: bid, chei: [cheie]}).then(function(){ reimprospateazaNrBuchete(); }); }};
    }));
  });
}
function puneSigla(cheie){
  var i = el("input"); i.type = "file"; i.accept = "image/*";
  i.addEventListener("change", function(){
    var f = i.files && i.files[0]; if(!f){ return; }
    var img = new Image(), u = URL.createObjectURL(f);
    img.onload = function(){
      // micsorata in browser la 220 x 132 (marimea obisnuita a siglelor), cu marginile transparente, PNG
      var c = document.createElement("canvas"); c.width = 220; c.height = 132;
      var k = Math.min(220 / img.width, 132 / img.height, 1), w = Math.round(img.width * k), h = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, Math.round((220 - w) / 2), Math.round((132 - h) / 2), w, h);
      URL.revokeObjectURL(u);
      c.toBlob(function(b){ b.arrayBuffer().then(function(buf){
        cerere("/api/editor-canale-import?fel=sigla&cheie=" + encodeURIComponent(cheie), "POST", buf, "application/octet-stream").then(function(r){
          if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
          mesaj(L("sigla_pusa")); setTimeout(incarcaServicii, 1500); incarcaBuchet();
        });
      }); }, "image/png");
    };
    img.onerror = function(){ URL.revokeObjectURL(u); mesaj(L("sigla_numai_dvb"), true); };
    img.src = u;
  });
  foaie(L("pune_sigla"), [L("sigla_numai_dvb")], [{text: L("renunta")}, {text: L("pune_sigla"), clasa: "principal", fa: function(){ i.click(); }}]);
}
function copiazaSigla(cheie){
  cereText(L("copiaza_sigla"), L("nume"), "", function(v){
    var q = fara(v).trim(), l = [];
    for(var i = 0; i < S.sv.length && l.length < 12; i++){ var x = S.sv[i]; if(x[13] && x[0] !== cheie && fara(x[2]).indexOf(q) !== -1){ l.push(x); } }
    if(!l.length){ mesaj(L("nimic_gasit"), true); return; }
    listaActiuni(L("copiaza_sigla"), l.map(function(x){ return {text: x[2] + " · " + (x[12] || ""), fa: function(){
      cerere("/api/editor-canale-sigla?fel=copiaza", "POST", {din: x[0], la: cheie}).then(function(r){
        if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
        mesaj(L("sigla_pusa")); setTimeout(incarcaServicii, 1500); incarcaBuchet();
      });
    }}; }));
  });
}
function stergeSigla(cheie){
  intreaba(L("sterge_sigla") + "?", L("sterge_sigla"), function(){
    cerere("/api/editor-canale-sigla?fel=sterge", "POST", {chei: [cheie]}).then(function(r){
      if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
      setTimeout(incarcaServicii, 1500); incarcaBuchet();
    });
  }, true);
}
function editeazaFlux(r){
  var parti = (r[10] || "").split(":"), adr = "";
  try { adr = decodeURIComponent(parti[10] || ""); } catch(e){ adr = parti[10] || ""; }
  var a = el("input"); a.type = "url"; a.value = adr;
  var la = el("label", "", L("adresa")); la.style.display = "flex"; la.style.flexDirection = "column"; la.appendChild(a);
  var tip = el("select");
  ["4097", "5001", "5002", "1"].forEach(function(t){ var o = el("option", "", t); o.value = t; if(t === parti[0]){ o.selected = true; } tip.appendChild(o); });
  var lt = el("label", "", L("tip_flux")); lt.style.display = "flex"; lt.style.flexDirection = "column"; lt.appendChild(tip);
  var nr = el("input"); nr.type = "text"; nr.value = [parti[3], parti[4], parti[5], parti[6]].map(function(x){ return x || "0"; }).join(" ");
  var ln = el("label", "", L("numere_dvb")); ln.style.display = "flex"; ln.style.flexDirection = "column"; ln.appendChild(nr);
  foaie(L("editeaza_flux"), [la, lt, S.avansat ? ln : null], [{text: L("renunta")}, {text: L("salveaza_btn"), clasa: "principal", fa: function(){
    var o = {op: "schimba_flux", buchet: buchetAcum(), ids: [r[0]], adresa: a.value, tip: parseInt(tip.value, 10)};
    if(S.avansat){
      var v = nr.value.trim().split(/\s+/);
      if(v.length === 4 && v.every(function(x){ return /^[0-9a-f]{1,8}$/i.test(x); })){
        o.sid = parseInt(v[0], 16); o.tsid = parseInt(v[1], 16); o.onid = parseInt(v[2], 16); o.ns = parseInt(v[3], 16);
      }
    }
    op(o);
  }}]);
}
function descarcaCsv(){
  // tabelul buchetului deschis: numarul, numele, pozitia si transponderul, referinta (separate prin ;)
  var r = ["nr;nume;detalii;cheie"];
  S.randuri.forEach(function(x){ r.push([x[3] || "", x[2], x[6], x[5]].map(function(v){ return '"' + String(v || "").replace(/"/g, '""') + '"'; }).join(";")); });
  var b = new Blob(["\ufeff" + r.join("\r\n") + "\r\n"], {type: "text/csv"}), a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = (S.numeDrum[buchetAcum()] || "buchet").replace(/[^A-Za-z0-9_.-]+/g, "_") + ".csv";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(function(){ URL.revokeObjectURL(a.href); }, 5000);
}
function lipesteNume(){
  var t = el("textarea");
  foaie(L("lipeste_nume"), [L("lipeste_nota"), t], [{text: L("renunta")}, {text: L("adauga_in"), clasa: "principal", fa: function(){
    var pe = {}, chei = [], lipsa = 0;
    S.sv.forEach(function(x){ var k = fara(x[2]).trim(); if(!(k in pe)){ pe[k] = x[0]; } });
    t.value.split(/\r?\n/).map(function(x){ return fara(x).trim(); }).filter(Boolean).forEach(function(k){
      if(k in pe){ chei.push(pe[k]); } else { lipsa++; }
    });
    if(chei.length){ adaugaCanale(chei); }
    mesaj(L("gasite_negasite") + " " + chei.length + " / " + lipsa, !chei.length);
  }}]);
}
function stergeSatelitii(lsat, pastreaza){
  var nume = lsat.map(function(g){ return g.text; }).join(", ");
  intreaba(L("sateliti_n") + " " + nume + ". " + L(pastreaza ? "q_pastreaza_satelitii" : "q_sterge_satelitii"),
    L(pastreaza ? "pastreaza_satelitii" : "sterge_satelitii"), function(){
      op({op: "sterge_sateliti", pozitii: lsat.map(function(g){ return g.poz; }), pastreaza: pastreaza}, true).then(function(r){
        if(r){ S.lsel = {}; incarcaServicii(); incarcaArbore(); }
      });
    }, true);
}
function campTp(eticheta, valoare, tip){
  var i = el("input"); i.type = tip || "number"; i.value = valoare === undefined || valoare === null ? "" : valoare;
  var l = el("label", "", eticheta); l.style.display = "flex"; l.style.flexDirection = "column"; l.appendChild(i);
  return [l, i];
}
function alegeTp(eticheta, valori, ales){
  var s = el("select");
  valori.forEach(function(v){ var o = el("option", "", v[1]); o.value = v[0]; if(String(v[0]) === String(ales)){ o.selected = true; } s.appendChild(o); });
  var l = el("label", "", eticheta); l.style.display = "flex"; l.style.flexDirection = "column"; l.appendChild(s);
  return [l, s];
}
function formTp(c){
  // aceleasi valori ca lamedb si satellites.xml: polarizarea H V L R = 0 1 2 3, sistemul DVB-S / DVB-S2 = 0 / 1 ...
  return [
    ["frecventa", campTp(L("frecventa_mhz"), c.frecventa !== undefined ? c.frecventa / 1000 : "")],
    ["sr", campTp(L("sr_ks"), c.sr !== undefined ? c.sr / 1000 : "")],
    ["pol", alegeTp(L("polarizare"), [[0, "H"], [1, "V"], [2, "L"], [3, "R"]], c.pol)],
    ["fec", alegeTp("FEC", [[0, L("auto")], [1, "1/2"], [2, "2/3"], [3, "3/4"], [4, "5/6"], [5, "7/8"], [6, "8/9"], [7, "3/5"], [8, "4/5"], [9, "9/10"], [15, "-"]], c.fec)],
    ["sistem", alegeTp(L("sistem"), [[0, "DVB-S"], [1, "DVB-S2"]], c.sistem)],
    ["modulatie", alegeTp(L("modulatie"), [[0, L("auto")], [1, "QPSK"], [2, "8PSK"], [3, "QAM16"], [4, "16APSK"], [5, "32APSK"]], c.modulatie)],
    ["rolloff", alegeTp(L("rolloff"), [[0, "0.35"], [1, "0.25"], [2, "0.20"], [3, L("auto")]], c.rolloff)],
    ["pilot", alegeTp(L("pilot"), [[0, L("oprit")], [1, L("pornit")], [2, L("auto")]], c.pilot)],
    ["is_id", campTp(L("mis"), c.is_id !== undefined ? c.is_id : -1)],
    ["pls_cod", campTp(L("pls_cod"), c.pls_cod !== undefined ? c.pls_cod : 0)],
    ["pls_mod", alegeTp(L("pls_mod"), [[0, L("pls_root")], [1, L("pls_gold")], [2, L("pls_combo")]], c.pls_mod)]
  ];
}
function valoriTp(f){
  var v = {};
  f.forEach(function(x){ var s = x[1][1].value; if(s === ""){ return; } v[x[0]] = x[0] === "frecventa" || x[0] === "sr" ? parseFloat(s) : parseInt(s, 10); });
  return v;
}
function editeazaTp(tp, poz){
  function arata(c, tsid, onid){
    var f = formTp(c), extra = [];
    var ts = campTp("TSID", tsid), on = campTp("ONID", onid);
    if(!tp){ extra = [ts[0], on[0], el("p", "expl", L("tp_nou_nota"))]; }
    foaie(tp ? L("editeaza_tp") : L("tp_nou_lista"), f.map(function(x){ return x[1][0]; }).concat(extra), [{text: L("renunta")},
      {text: L("salveaza_btn"), clasa: "principal", fa: function(){
        if(tp){ op({op: "schimba_transponder", tp: tp, campuri: valoriTp(f)}).then(function(){ incarcaServicii(); }); return; }
        op({op: "transponder_nou", poz: poz, campuri: valoriTp(f), tsid: parseInt(ts[1].value, 10), onid: parseInt(on[1].value, 10)});
      }}]);
  }
  if(!tp){ arata({sistem: 1, modulatie: 2, fec: 0, rolloff: 0, pilot: 2}, 1, 1); return; }
  cerere("/api/editor-canale-transponder?tp=" + encodeURIComponent(tp)).then(function(r){
    if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
    arata(r.campuri || {});
  });
}
function inlocuiesteNume(){
  var c = el("input"); c.type = "text"; var u = el("input"); u.type = "text";
  var lc = el("label", "", L("cauta_text")); lc.style.display = "flex"; lc.style.flexDirection = "column"; lc.appendChild(c);
  var lu = el("label", "", L("inlocuieste_cu")); lu.style.display = "flex"; lu.style.flexDirection = "column"; lu.appendChild(u);
  var bb = el("input"); bb.type = "checkbox"; var lb = el("label", "opt"); lb.appendChild(bb); lb.appendChild(document.createTextNode(L("in_buchete_si")));
  var pv = el("p", "expl", "");
  function potrivite(){
    var q = c.value; if(!q){ return [[], []]; }
    var re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
    // canalele vazute in sursa (cu filtrele de acum) sau, fara ele, toate; buchetele din arbore
    var lista = S.vazute || S.sv.map(function(x, i){ return i; });
    return [lista.map(function(i){ return S.sv[i]; }).filter(function(x){ return re.test(x[2]); }),
      bb.checked ? S.arbore.filter(function(b){ return re.test(b[1]); }) : []];
  }
  function arata(){
    var p = potrivite(), ex = p[0].slice(0, 5).map(function(x){ return x[2] + " → " + x[2].replace(new RegExp(c.value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "ig"), u.value); });
    pv.textContent = L("previzualizare") + " " + (p[0].length + p[1].length) + (ex.length ? " · " + ex.join(" · ") : "");
  }
  c.addEventListener("input", arata); u.addEventListener("input", arata); bb.addEventListener("change", arata);
  foaie(L("inlocuieste_nume"), [lc, lu, lb, pv], [{text: L("renunta")}, {text: L("inlocuieste"), clasa: "principal", fa: function(){
    var p = potrivite();
    if(!p[0].length && !p[1].length){ return false; }
    op({op: "inlocuieste_nume", cauta: c.value, cu: u.value, chei: p[0].map(function(x){ return x[0]; }), buchete: p[1].map(function(b){ return b[0]; })}).then(function(){ incarcaArbore(); incarcaServicii(); });
  }}]);
}
function mutaSatelit(din, copiaza){
  cereText(L(copiaza ? "copiaza_satelit" : "muta_satelit"), L("pozitia_sat"), "", function(v){
    var m = /^\s*(\d{1,3})(?:[.,](\d))?\s*°?\s*([ewEW])\s*$/.exec(v || "");
    if(!m){ mesaj(L("pozitia_sat"), true); return; }
    var p = parseInt(m[1], 10) * 10 + (m[2] ? parseInt(m[2], 10) : 0);
    if(m[3].toUpperCase() === "W"){ p = 3600 - p; }
    op({op: "muta_satelit", din: din, la: p % 3600, copiaza: copiaza}, true).then(function(r){ if(r){ S.sursaPoz = null; incarcaServicii(); } });
  });
}
function curatenie(){
  listaActiuni(L("curatenie"), [
    {text: L("arata_ascunse"), fa: function(){ op({op: "curata_steaguri", fel: "ascunse"}).then(function(){ incarcaServicii(); }); }},
    {text: L("deblocheaza_tot"), fa: function(){ op({op: "curata_steaguri", fel: "blocate"}).then(function(){ incarcaServicii(); }); }},
    {text: L("scoate_nou_tot"), fa: function(){ op({op: "curata_steaguri", fel: "noi"}).then(function(){ incarcaServicii(); }); }}
  ]);
}
function sigle(){
  listaActiuni(L("sigle"), [
    {text: L("sigle_nefolosite"), fa: function(){ unealta("sigle_nefolosite", L("sigle_nefolosite")); }},
    {text: L("redenumeste_sigle_ref"), fa: function(){ redenumesteSigle("referinta"); }},
    {text: L("redenumeste_sigle_nume"), fa: function(){ redenumesteSigle("nume"); }}
  ]);
}
function redenumesteSigle(dupa){
  intreaba(L(dupa === "referinta" ? "redenumeste_sigle_ref" : "redenumeste_sigle_nume") + "?", L("ok"), function(){
    cerere("/api/editor-canale-sigla?fel=redenumeste", "POST", {dupa: dupa}).then(function(r){
      if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
      mesaj(L("gata") + ": " + r.n); setTimeout(incarcaServicii, 1500);
    });
  });
}
function marimeLitere(){
  listaActiuni(L("marime_litere"), [
    {text: L("mai_mari"), fa: function(){ S.marime = Math.min(1.6, S.marime + 0.1); aplicaMarimea(); }},
    {text: L("mai_mici"), fa: function(){ S.marime = Math.max(0.8, S.marime - 0.1); aplicaMarimea(); }}
  ]);
}
function aplicaMarimea(){
  document.documentElement.style.setProperty("--marime-litere", S.marime.toFixed(2) + "em");
  tine("hds-editor-marime", S.marime.toFixed(2)); VB.arata(true); VS.arata(true);
}
function comutaAvansat(){
  S.avansat = !S.avansat; tine("hds-editor-avansat", S.avansat ? "1" : "0");
  mesaj(L(S.avansat ? "avansat_pornit" : "avansat_oprit") + (S.avansat ? ". " + L("avansat_nota") : ""));
  filtreaza(true);
}
// ---------------------------------------------------------------- satellites.xml (Mod avansat)
function satelitiXml(){
  arataVederea();
  capVedere(L("sateliti_xml"));
  var st = el("p", "", L("se_cauta")); $("vedere").appendChild(st);
  cerere("/api/editor-canale-sateliti").then(function(r){
    st.textContent = L("sateliti_nota");
    if(!r.result){ st.textContent = r.message || L("eroare_retea"); return; }
    var bara = el("div", "bara-vedere");
    bara.appendChild(buton(L("satelit_nou"), function(){ editeazaSatelit(null); }, "principal"));
    if(r.nesalvat){
      bara.appendChild(buton(L("salveaza_sateliti"), salveazaSateliti, "principal"));
      bara.appendChild(buton(L("renunta_sateliti"), function(){ cerere("/api/editor-canale-sateliti-op", "POST", {op: "renunta"}).then(satelitiXml); }));
    }
    $("vedere").appendChild(bara);
    r.sateliti.forEach(function(s){
      var g = el("div", "grupa");
      g.appendChild(el("h3", "", s.text + (s.nume ? "  " + s.nume : "")));
      g.appendChild(el("p", "expl", L("transpondere_n") + " " + s.transpondere));
      var bt = el("div", ""); bt.style.display = "flex"; bt.style.gap = "8px"; bt.style.flexWrap = "wrap";
      bt.appendChild(buton(L("transpondere_btn"), function(){ satelitXml(s.poz); }, "mic"));
      bt.appendChild(buton(L("editeaza"), function(){ editeazaSatelit(s); }, "mic"));
      bt.appendChild(buton(L("sterge"), function(){ opSateliti({op: "sterge_satelit", poz: s.poz}, satelitiXml, s.text); }, "mic rosu"));
      g.appendChild(bt);
      $("vedere").appendChild(g);
    });
  });
}
function opSateliti(o, dupa, intrebare){
  function fa(){ cerere("/api/editor-canale-sateliti-op", "POST", o).then(function(r){ if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; } dupa(); }); }
  if(intrebare){ intreaba(intrebare + ": " + L("sterge") + "?", L("sterge"), fa, true); } else { fa(); }
}
function salveazaSateliti(){
  cerere("/api/editor-canale-sateliti-op", "POST", {op: "salveaza"}).then(function(r){
    if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
    mesaj(L(r.reincarcat ? "sateliti_reincarcat" : "sateliti_repornire")); satelitiXml();
  });
}
function editeazaSatelit(s){
  var n = campTp(L("nume"), s ? s.nume : "", "text"), p = campTp(L("pozitia_sat"), s ? s.text : "", "text");
  foaie(s ? L("editeaza") : L("satelit_nou"), [n[0], p[0]], [{text: L("renunta")}, {text: L("ok"), clasa: "principal", fa: function(){
    if(s){ opSateliti({op: "schimba_satelit", poz: s.poz, nume: n[1].value, pozitie_noua: p[1].value !== s.text ? p[1].value : null}, satelitiXml); }
    else { opSateliti({op: "satelit_nou", poz: p[1].value, nume: n[1].value}, satelitiXml); }
  }}]);
}
function satelitXml(poz){
  arataVederea();
  capVedere(L("transpondere_btn"));
  cerere("/api/editor-canale-sateliti?poz=" + encodeURIComponent(poz)).then(function(r){
    if(!r.result){ $("vedere").appendChild(el("p", "", r.message || L("eroare_retea"))); return; }
    var s = r.satelit;
    $("vedere").appendChild(el("p", "", s.text + (s.nume ? "  " + s.nume : "") + " · " + L("sateliti_nota")));
    var bara = el("div", "bara-vedere");
    bara.appendChild(buton(L("transponder_nou"), function(){ editeazaTpXml(poz, null); }, "principal"));
    bara.appendChild(buton(L("sateliti_xml"), satelitiXml));
    $("vedere").appendChild(bara);
    s.transpondere.forEach(function(t){
      var a = t.atribute, rd = el("div", "rand-u"), tx = el("div", "");
      var pol = {"0": "H", "1": "V", "2": "L", "3": "R"}[a.polarization] || "";
      tx.appendChild(el("div", "n", Math.round((a.frequency || 0) / 1000) + " " + pol + " " + Math.round((a.symbol_rate || 0) / 1000)));
      tx.appendChild(el("div", "d", [L("sistem") + " " + (a.system === "1" ? "DVB-S2" : "DVB-S"), "FEC " + (a.fec_inner || ""), a.modulation ? "mod " + a.modulation : "", a.is_id ? "MIS " + a.is_id : ""].filter(Boolean).join(" · ")));
      rd.appendChild(tx);
      rd.appendChild(buton(L("editeaza"), function(){ editeazaTpXml(poz, t); }, "mic"));
      rd.appendChild(buton(L("sterge"), function(){ opSateliti({op: "sterge_transponder", poz: poz, cheie: t.cheie}, function(){ satelitXml(poz); }, tx.firstChild.textContent); }, "mic rosu"));
      $("vedere").appendChild(rd);
    });
  });
}
function editeazaTpXml(poz, t){
  var a = t ? t.atribute : {system: "1", modulation: "2", fec_inner: "0", polarization: "0"};
  var campuri = [["frequency", "kHz"], ["symbol_rate", "S/s"], ["polarization", "0 H · 1 V · 2 L · 3 R"], ["fec_inner", "FEC"], ["system", "0 DVB-S · 1 DVB-S2"],
    ["modulation", "0 " + L("auto") + " · 1 QPSK · 2 8PSK"], ["rolloff", "0 0.35 · 1 0.25 · 2 0.20"],
    ["pilot", "0 " + L("oprit") + " · 1 " + L("pornit") + " · 2 " + L("auto")], ["is_id", "MIS"], ["pls_code", "PLS"],
    ["pls_mode", "0 " + L("pls_root") + " · 1 " + L("pls_gold")]];
  var f = campuri.map(function(c){ return [c[0], campTp(c[0] + " (" + c[1] + ")", a[c[0]] !== undefined ? a[c[0]] : "", "text")]; });
  foaie(t ? L("editeaza") : L("transponder_nou"), f.map(function(x){ return x[1][0]; }), [{text: L("renunta")}, {text: L("ok"), clasa: "principal", fa: function(){
    var v = {}; f.forEach(function(x){ var s = x[1][1].value.trim(); v[x[0]] = s === "" ? null : s; });
    if(t){ opSateliti({op: "schimba_transponder", poz: poz, cheie: t.cheie, valori: v}, function(){ satelitXml(poz); }); }
    else { opSateliti({op: "transponder_nou", poz: poz, valori: v}, function(){ satelitXml(poz); }); }
  }}]);
}
function stergeDinReceptor(chei){
  intreaba(nCanale(chei.length) + ". " + L("q_sterge_receptor"), L("sterge_receptor"), function(){
    op({op: "sterge_servicii", chei: chei}, true).then(function(){ incarcaServicii(); });
  }, true);
}

// ---------------------------------------------------------------- operatiile
function op(o, golesteSel){
  if(S.lucru){ return Promise.resolve(null); }
  return cerere("/api/editor-canale-op", "POST", o).then(function(r){
    if(r.pierdut){ S.gata = false; arataOcupat(r.ocupat); return null; }
    if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return null; }
    puneStarea(r);
    if(golesteSel){ S.sel = {}; S.nsel = 0; }
    if(o.op === "adauga" && r.n === 0){ mesaj(L("deja")); }
    if(r.tot || o.op === "sterge_servicii" || o.op === "scoate_din_toate" || o.op === "sterge_transpondere"){ incarcaServicii(); }
    if(r.servicii){ actualizeazaServicii(r.servicii); }
    incarcaBuchet();
    if(S.sursa === "buchete"){ if(S.sursaBuchet){ reiaBuchetSursa(); } else { incarcaArbore().then(function(){ filtreaza(true); }); } }
    if(o.op === "adauga" || o.op === "scoate" || o.op === "muta_in" || o.op === "copiaza" || r.tot){ reimprospateazaNrBuchete(); }
    return r;
  });
}
function reimprospateazaNrBuchete(){ clearTimeout(S.ceasNr); S.ceasNr = setTimeout(incarcaServicii, 1500); }
$("anuleaza").onclick = function(){ op({op: "anuleaza"}).then(function(){ incarcaArbore(); }); };
$("reface").onclick = function(){ op({op: "reface"}).then(function(){ incarcaArbore(); }); };
$("salveaza").onclick = salveaza;
function salveaza(){
  if(S.lucru || !S.nesalvate){ return; }
  cerere("/api/editor-canale-salveaza", "POST").then(function(r){
    if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
    mesaj(L("se_salveaza"));
    asteapta(function(st){
      var z = st.rezultat || {};
      if(z.fel === "salvat"){
        var t = z.verificat === false ? L("salvat_diferente") : (z.verificat === null ? L("salvat_neverificat") : L("salvat"));
        if(z.avertismente && z.avertismente.length){ t += " " + z.avertismente.join(" "); }
        if(z.rezumat && textRezumat(z.rezumat)){ t += " " + textRezumat(z.rezumat); }
        mesaj(t, z.verificat === false);
      }
      incarcaArbore(); incarcaBuchet(); incarcaServicii();
    });
  });
}

// ---------------------------------------------------------------- sursa (canalele receptorului)
function incarcaServicii(){
  var radio = S.radio, toate = [];
  function pagina(de_la){
    return cerere("/api/editor-canale-servicii?radio=" + (radio ? 1 : 0) + "&de_la=" + de_la + "&cate=" + MAX_PAGINA).then(function(r){
      if(!r.result){ return; }
      if(r.sateliti){ S.sateliti = r.sateliti; }
      toate = toate.concat(r.randuri);
      if(de_la + r.randuri.length < r.total && r.randuri.length){ return pagina(de_la + r.randuri.length); }
      if(radio !== S.radio){ return; }
      S.sv = toate;
      S.svIndex = {};
      toate.forEach(function(x, i){ S.svIndex[x[0]] = i; });
      filtreaza();
    });
  }
  return pagina(0);
}
function actualizeazaServicii(randuri){
  randuri.forEach(function(x){ var i = S.svIndex && S.svIndex[x[0]]; if(i !== undefined){ S.sv[i] = x; } });
  filtreaza(true);
}
function fara(t){ return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
function seamana(a, b){
  // cel mult o litera diferita, lipsa, in plus sau doua litere vecine schimbate intre ele (cautarea tolerata la
  // greseli, numai pentru cuvinte de 4+ litere)
  if(Math.abs(a.length - b.length) > 1){ return false; }
  if(a.length === b.length){
    var d = []; for(var z = 0; z < a.length && d.length < 3; z++){ if(a[z] !== b[z]){ d.push(z); } }
    if(d.length === 2 && d[1] === d[0] + 1 && a[d[0]] === b[d[1]] && a[d[1]] === b[d[0]]){ return true; }
  }
  var i = 0, j = 0, dif = 0;
  while(i < a.length && j < b.length){
    if(a[i] === b[j]){ i++; j++; continue; }
    if(++dif > 1){ return false; }
    if(a.length > b.length){ i++; } else if(b.length > a.length){ j++; } else { i++; j++; }
  }
  return dif + (a.length - i) + (b.length - j) <= 1;
}
function filtreaza(pastreaza){
  var q = fara(S.text).trim(), cuv = q ? q.split(/\s+/) : [], f = S.filtre, nr = null;
  var t = S.text.trim().toLowerCase();
  // „*” si „?” in text: tiparul pe tot numele (*sport = se termina cu sport); o referinta 1:0:... cauta referinta
  var tipar = null, refCauta = /^[0-9a-f]+:[0-9a-f]+:/.test(t) ? t : null;
  if(!refCauta && /[*?]/.test(q)){ tipar = new RegExp("^" + q.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".") + "$"); }
  if(/^0x[0-9a-f]+$/.test(t)){ nr = parseInt(t, 16); } else if(/^\d+$/.test(t)){ nr = parseInt(t, 10); }
  var rez = [];
  if(S.sursa === "sateliti" && S.sursaPoz === null){ rez = null; }
  else if(S.sursa === "furnizori" && S.sursaFurn === null){ rez = null; }
  else if(S.sursa === "sateliti" && S.peTp && S.sursaTp === null){ rez = null; }
  else if(S.sursa === "buchete" && (S.sursaBuchet === null || S.sursaRanduri === null)){ rez = null; }
  if(rez !== null){
    // din alt buchet: numai canalele lui, in ordinea din buchet
    var din = null;
    if(S.sursa === "buchete"){ din = []; S.sursaRanduri.forEach(function(k){ var j = S.svIndex[k]; if(j !== undefined){ din.push(j); } }); }
    var nTot = din ? din.length : S.sv.length;
    for(var qi = 0; qi < nTot; qi++){
      var i = din ? din[qi] : qi;
      var x = S.sv[i];
      if(S.sursa === "sateliti" && x[4] !== S.sursaPoz){ continue; }
      if(S.sursa === "sateliti" && S.sursaTp !== null && x[15] !== S.sursaTp){ continue; }
      if(f.fara_sigla && x[13]){ continue; }
      if(S.sursa === "furnizori" && x[3] !== S.sursaFurn){ continue; }
      if(f.hd && x[8] !== "HD" && x[8] !== "UHD"){ continue; }
      if(f.sd && x[8] !== "SD"){ continue; }
      if(f.fta && x[9] !== "fta"){ continue; }
      if(f.criptat && x[9] !== "criptat"){ continue; }
      if(f.liber && x[11]){ continue; }
      if(f.ascuns ? !(x[10] & 1) : false){ continue; }
      if(S.nfb){
        var m = S.fb.masti[x[0]];
        if(!m){ continue; }
        var bun = true;
        for(var gi in S.fsel){ if(S.fsel[gi] && !(m[gi] & S.fsel[gi])){ bun = false; break; } }
        if(!bun){ continue; }
      }
      if(f.hd_nume && !(x[10] & 32)){ continue; }
      if(f.noi && !(x[10] & 16)){ continue; }
      if(f.blocate && !(x[10] & 2)){ continue; }
      if(refCauta){ if(x[1].toLowerCase().indexOf(refCauta) !== 0){ continue; } }
      else if(tipar){ if(!tipar.test(fara(x[2]).trim())){ continue; } }
      else if(cuv.length){
        var s = fara(x[2] + " " + x[3]), ok = true;
        for(var k = 0; k < cuv.length; k++){ if(s.indexOf(cuv[k]) === -1){ ok = false; break; } }
        if(!ok && !(nr !== null && (x[7] === nr || x[5] === nr))){ continue; }
      }
      rez.push(i);
    }
    if(!rez.length && cuv.length && !tipar && !refCauta && cuv.every(function(c){ return c.length >= 4; })){
      // nimic gasit: aceeasi cautare cu o litera gresita in fiecare cuvant
      for(var qj = 0; qj < nTot; qj++){
        var ij = din ? din[qj] : qj, xj = S.sv[ij];
        if(S.sursa === "sateliti" && xj[4] !== S.sursaPoz){ continue; }
        var cuvinte = fara(xj[2]).split(/[^0-9a-z+]+/);
        if(cuv.every(function(c){ return cuvinte.some(function(w){ return seamana(w, c); }); })){ rez.push(ij); }
      }
    }
    if(S.sursa === "sateliti"){ rez.sort(function(a, b){ var A = S.sv[a], B = S.sv[b]; return (A[5] - B[5]) || (A[6] < B[6] ? -1 : A[6] > B[6] ? 1 : 0) || (A[7] - B[7]); }); }
    else if(q && S.sursa !== "buchete"){
      var rang = function(j){ var n = fara(S.sv[j][2]).replace(/[^0-9a-z+]+/g, " ").trim(); return n.indexOf(q) === 0 ? 0 : (" " + n).indexOf(" " + q) !== -1 ? 1 : 2; };
      var r0 = [], r1 = [], r2 = [];
      rez.forEach(function(j){ var k = rang(j); (k === 0 ? r0 : k === 1 ? r1 : r2).push(j); });
      rez = r0.concat(r1, r2);
    }
  }
  S.vazute = rez;
  deseneazaDrumSursa();
  if(rez === null){
    S.lista = S.sursa === "buchete" ? S.arbore.filter(function(b){ return b[0] !== buchetAcum(); }).map(function(b){ return {fel: "buc", id: b[0], text: b[1], n: b[2], indent: b[3]}; })
      : S.sursa === "sateliti" && S.sursaPoz !== null ? transpondere()
      : S.sursa === "sateliti" ? S.sateliti.map(function(s){ return {fel: "sat", poz: s[0], text: s[1] + (s[2] ? "  " + s[2] : ""), n: s[3]}; })
      : furnizori().map(function(p){ return {fel: "furn", nume: p[0], text: p[0] || L("fara_furnizor"), n: p[1]}; });
    VS.pune(S.lista.length, L("nimic_gasit"));
  } else {
    S.lista = null;
    VS.pune(rez.length, L("nimic_gasit"));
  }
  if(!pastreaza){ $("listaSursa").scrollTop = 0; }
  deseneazaBaraSursa();
}
function transpondere(){
  // transponderele satelitului ales, din canalele deja citite (cheia transponderului e x[15]), dupa frecventa
  var t = {}, l = [];
  S.sv.forEach(function(x){
    if(x[4] !== S.sursaPoz || !x[15]){ return; }
    var g = t[x[15]];
    if(!g){ g = t[x[15]] = {fel: "tp", cheie: x[15], text: x[12] || x[15], n: 0, f: x[5], p: x[6]}; l.push(g); }
    g.n++;
  });
  l.sort(function(a, b){ return (a.f - b.f) || (a.p < b.p ? -1 : a.p > b.p ? 1 : 0); });
  return l;
}
function alegeBuchetSursa(bid, nume){
  S.numeDrum[bid] = nume;
  S.sursaBuchet = bid; S.sursaRanduri = null;
  return reiaBuchetSursa();
}
function reiaBuchetSursa(){
  var bid = S.sursaBuchet;
  if(S.sursa !== "buchete" || !bid){ return Promise.resolve(); }
  return cerere("/api/editor-canale-intrari?buchet=" + encodeURIComponent(bid)).then(function(r){
    if(bid !== S.sursaBuchet){ return; }
    if(!r.result){ S.sursaBuchet = null; S.sursaRanduri = null; filtreaza(); return; }
    S.sursaRanduri = r.randuri.filter(function(x){ return x[1] === "c" && x[5]; }).map(function(x){ return x[5]; });
    filtreaza(true);
  });
}
function textTp(cheie){
  for(var i = 0; i < S.sv.length; i++){ if(S.sv[i][15] === cheie){ return S.sv[i][12] || cheie; } }
  return cheie;
}
function furnizori(){
  var n = {}, l = [];
  S.sv.forEach(function(x){ n[x[3]] = (n[x[3]] || 0) + 1; });
  for(var k in n){ l.push([k, n[k]]); }
  l.sort(function(a, b){ return fara(a[0]) < fara(b[0]) ? -1 : 1; });
  return l;
}
// actiunile satelitului / transponderului / furnizorului ales: pe calculator butoane langa drum, pe telefon in „Mai
// mult” din bara de jos a sursei (drumul ramane un rand, lista ramane la vedere)
function actiuneDrum(d, text, fa, clasa){
  if(ingust()){ S.actDrum.push({text: text, fa: fa, clasa: clasa && clasa.indexOf("rosu") !== -1 ? "rosu" : ""}); }
  else { d.appendChild(buton(text, fa, clasa)); }
}
function deseneazaDrumSursa(){
  var d = $("drumSursa");
  gol(d);
  S.actDrum = [];
  if(S.sursa === "sateliti" && S.sursaPoz !== null){
    var b = el("button", "", L("sateliti")); b.type = "button"; b.onclick = function(){ S.sursaPoz = null; S.sursaTp = null; S.lsel = {}; filtreaza(); };
    d.appendChild(b); d.appendChild(el("span", "sep", "›"));
    var s = S.sateliti.filter(function(x){ return x[0] === S.sursaPoz; })[0];
    var numeSat = s ? s[1] + (s[2] ? " " + s[2] : "") : "";
    if(S.sursaTp !== null){
      var bs = el("button", "", numeSat); bs.type = "button"; bs.onclick = function(){ S.sursaTp = null; filtreaza(); };
      d.appendChild(bs); d.appendChild(el("span", "sep", "›"));
      var tp = S.sursaTp, tt = textTp(tp);
      d.appendChild(el("span", "", tt));
      actiuneDrum(d, L("buchet_din_tp"), function(){ op({op: "buchet_din", fel: "transponder", valoare: tp, radio: S.radio}).then(function(){ incarcaArbore(); }); }, "mic");
      actiuneDrum(d, L("sterge_tp"), function(){ stergeTp(tp, tt); }, "mic rosu");
      if(S.avansat){ actiuneDrum(d, L("editeaza_tp"), function(){ editeazaTp(tp); }, "mic"); }
    } else {
      d.appendChild(el("span", "", numeSat));
      actiuneDrum(d, S.peTp ? L("toate_satelitului") : L("pe_transpondere"), function(){ S.peTp = !S.peTp; filtreaza(); }, "mic");
      actiuneDrum(d, L("buchet_din_satelit"), function(){ op({op: "buchet_din", fel: "satelit", valoare: S.sursaPoz, radio: S.radio}).then(function(){ incarcaArbore(); }); }, "mic");
      if(S.avansat && S.sursaPoz >= 0){ actiuneDrum(d, L("tp_nou_lista"), function(){ editeazaTp(null, S.sursaPoz); }, "mic"); }
      if(S.avansat && S.sursaPoz >= 0){ actiuneDrum(d, L("muta_satelit"), function(){ mutaSatelit(S.sursaPoz, false); }, "mic"); }
      if(S.avansat && S.sursaPoz >= 0){ actiuneDrum(d, L("copiaza_satelit"), function(){ mutaSatelit(S.sursaPoz, true); }, "mic"); }
    }
  } else if(S.sursa === "buchete" && S.sursaBuchet !== null){
    var b3 = el("button", "", L("sursa_buchete")); b3.type = "button"; b3.onclick = function(){ S.sursaBuchet = null; S.sursaRanduri = null; filtreaza(); };
    d.appendChild(b3); d.appendChild(el("span", "sep", "›"));
    d.appendChild(el("span", "", S.numeDrum[S.sursaBuchet] || S.sursaBuchet));
  } else if(S.sursa === "furnizori" && S.sursaFurn !== null){
    var b2 = el("button", "", L("furnizori")); b2.type = "button"; b2.onclick = function(){ S.sursaFurn = null; S.lsel = {}; filtreaza(); };
    d.appendChild(b2); d.appendChild(el("span", "sep", "›"));
    d.appendChild(el("span", "", S.sursaFurn || L("fara_furnizor")));
    actiuneDrum(d, L("buchet_din_furnizor"), function(){ op({op: "buchet_din", fel: "furnizor", valoare: S.sursaFurn, radio: S.radio}).then(function(){ incarcaArbore(); }); }, "mic");
  }
  if(S.vazute){ d.appendChild(el("span", "sep", nCanale(S.vazute.length))); }
}
function desenRandSursa(i){
  var d = el("div", "rand hds-derulant-rand");
  if(S.lista){
    var g = S.lista[i];
    if(g.fel === "sat" || g.fel === "furn"){
      // bifa: mai multe buchete deodata, cate unul din fiecare satelit / furnizor bifat
      var kl = g.fel === "sat" ? "s" + g.poz : "f" + g.nume;
      if(S.lsel[kl]){ d.classList.add("ales"); }
      var bl = el("label", "bifa"), cl = el("input");
      cl.type = "checkbox"; cl.checked = !!S.lsel[kl]; cl.setAttribute("aria-label", g.text);
      bl.addEventListener("click", function(ev){ ev.stopPropagation(); });
      cl.addEventListener("change", function(){
        if(cl.checked){ S.lsel[kl] = g; } else { delete S.lsel[kl]; }
        d.classList.toggle("ales", cl.checked); deseneazaBaraSursa();
      });
      bl.appendChild(cl); d.appendChild(bl);
    } else {
      d.appendChild(el("span", "nr", ""));
      if(g.indent){ d.style.paddingLeft = (g.indent * 18) + "px"; }
    }
    var t = el("div", "txt"); t.appendChild(el("div", "n hds-derulant", g.text));
    t.appendChild(el("div", "d hds-derulant", nCanale(g.n))); t.title = g.text;
    d.appendChild(t);
    var intra = el("button", "intra", "›"); intra.type = "button"; intra.setAttribute("aria-label", L("deschide"));
    d.appendChild(intra);
    d.addEventListener("click", function(){
      if(g.fel === "buc"){ alegeBuchetSursa(g.id, g.text); return; }
      if(g.fel === "sat"){ S.sursaPoz = g.poz; S.lsel = {}; } else if(g.fel === "tp"){ S.sursaTp = g.cheie; } else { S.sursaFurn = g.nume; S.lsel = {}; }
      filtreaza();
    });
    return d;
  }
  var x = S.sv[S.vazute[i]];
  if(S.ssel[x[0]]){ d.classList.add("ales"); }
  if(i === S.sfocus){ cursor(d, true); }
  var bifa = el("label", "bifa"), c = el("input");
  c.type = "checkbox"; c.checked = !!S.ssel[x[0]]; c.setAttribute("aria-label", x[2] || "?");
  c.addEventListener("change", function(){ comutaSSel(i, c.checked); });
  bifa.appendChild(c); d.appendChild(bifa);
  if(!ingust()){
    var m = el("span", "maner", "≡"); m.title = L("trage"); m.setAttribute("aria-hidden", "true");
    m.addEventListener("pointerdown", function(ev){ incepeTragerea(ev, "sursa", i); });
    d.appendChild(m);
  }
  if(x[13]){
    var img = el("img", "sigla"); img.alt = ""; img.loading = "lazy";
    img.onerror = function(){ img.style.visibility = "hidden"; };
    img.src = adresa("/api/canale-sigla?p=" + encodeURIComponent(x[13]));
    d.appendChild(img);
  }
  var t2 = el("div", "txt");
  t2.appendChild(el("div", "n hds-derulant", x[2] || "?"));
  var pz = "";
  for(var k = 0; k < S.sateliti.length; k++){ if(S.sateliti[k][0] === x[4]){ pz = S.sateliti[k][1]; break; } }
  t2.appendChild(el("div", "d hds-derulant", [pz, x[12], "SID " + x[7], x[3]].filter(Boolean).join(" · ")));
  d.appendChild(t2);
  if(x[8] === "HD" || x[8] === "UHD"){ d.appendChild(el("span", "semn hd", x[8])); }
  if(x[10] & 16){ d.appendChild(el("span", "semn nou", L("nou_semn"))); }
  if(x[10] & 1){ d.appendChild(el("span", "semn", L("ascuns"))); }
  if(x[11]){ var sb = el("span", "semn", "✓ " + x[11]); sb.title = L("in_buchete") + x[11]; d.appendChild(sb); }
  t2.title = [x[2], x[3], pz, x[12], "SID " + x[7], x[1]].filter(Boolean).join("\n");
  var p = el("button", "plus", "+"); p.type = "button"; p.setAttribute("aria-label", L("adauga_in"));
  p.onclick = function(ev){ ev.stopPropagation(); adaugaCanale([x[0]]); };
  d.appendChild(p);
  d.addEventListener("click", function(ev){
    if(ev.target.closest("button,input,.maner")){ return; }
    S.sfocus = i;
    if(ev.shiftKey && S.sancora >= 0){
      var de = Math.min(S.sancora, i), la = Math.max(S.sancora, i);
      for(var q = de; q <= la; q++){ var k2 = S.sv[S.vazute[q]][0]; if(!S.ssel[k2]){ S.ssel[k2] = true; S.nssel++; } }
      redaSel(); deseneazaBaraSursa();
    } else { comutaSSel(i, !S.ssel[x[0]]); S.sancora = i; }
  });
  d.addEventListener("contextmenu", function(ev){ ev.preventDefault(); if(!S.ssel[x[0]]){ comutaSSel(i, true); } meniuSursa(); });
  return d;
}
function comutaSSel(i, da){
  var k = S.sv[S.vazute[i]][0];
  if(da && !S.ssel[k]){ S.ssel[k] = true; S.nssel++; }
  else if(!da && S.ssel[k]){ delete S.ssel[k]; S.nssel--; }
  S.sfocus = i;
  redaSel(); deseneazaBaraSursa();
}
function cheiSursa(){ var l = []; for(var k in S.ssel){ l.push(k); } return l; }
function selTotSursa(da){
  S.ssel = {}; S.nssel = 0;
  if(da && S.vazute){ S.vazute.forEach(function(i){ S.ssel[S.sv[i][0]] = true; }); S.nssel = S.vazute.length; }
  redaSel(); deseneazaBaraSursa();
}
function numeBuchetAcum(){ return laRadacina() ? "" : (S.numeDrum[buchetAcum()] || ""); }
function deseneazaBaraSursa(){
  var b = $("baraSursa");
  gol(b);
  if(S.lista && !S.nssel){
    var nl = Object.keys(S.lsel).length;
    if(nl){
      b.appendChild(buton(L("buchete_din_alese") + " (" + nl + ")", bucheteDinAlese, "principal"));
      var lsat = []; for(var ks in S.lsel){ if(S.lsel[ks].fel === "sat"){ lsat.push(S.lsel[ks]); } }
      if(lsat.length === nl){ b.appendChild(buton(L("mai_mult"), function(){ listaActiuni(L("sateliti_n") + " " + nl, [
        {text: L("sterge_satelitii"), clasa: "rosu", fa: function(){ stergeSatelitii(lsat, false); }},
        {text: L("pastreaza_satelitii"), clasa: "rosu", fa: function(){ stergeSatelitii(lsat, true); }},
        {text: L("desel_tot"), fa: function(){ S.lsel = {}; VS.arata(true); deseneazaBaraSursa(); }}]); })); }
      else { b.appendChild(buton(L("desel_tot"), function(){ S.lsel = {}; VS.arata(true); deseneazaBaraSursa(); })); }
    } else if(S.actDrum && S.actDrum.length){
      b.appendChild(buton(L("mai_mult"), function(){ listaActiuni(L("mai_mult"), S.actDrum); }));
    }
    return;
  }
  if(S.nssel){
    // pe telefon fara randul cu numarul (e pe buton; „Deselectează tot” e si in „Mai mult”): lista ramane mai inalta
    if(!ingust()){
      var info = el("div", "info");
      info.appendChild(el("span", "", nCanale(S.nssel)));
      var d = el("button", "", L("desel_tot")); d.type = "button"; d.onclick = function(){ selTotSursa(false); };
      info.appendChild(d); b.appendChild(info);
    }
    var a = buton(L("adauga_in") + (numeBuchetAcum() ? ": " + numeBuchetAcum() : "") + (ingust() ? " (" + S.nssel + ")" : ""), function(){ adaugaCanale(cheiSursa()); }, "principal");
    b.appendChild(a);
    if(!ingust()){ b.appendChild(buton(L("buchet_din_alese"), function(){ buchetNou(null, cheiSursa()); })); }
    else { a.style.flex = "2 1 0"; }
    b.appendChild(buton(L("mai_mult"), meniuSursa));
  } else if(S.vazute && S.vazute.length){
    b.appendChild(buton(L("sel_tot"), function(){ selTotSursa(true); }));
    if(ingust()){ b.appendChild(buton(L("buchet"), function(){ comutaPanou("buchet"); })); }
    if(S.actDrum && S.actDrum.length){ b.appendChild(buton(L("mai_mult"), function(){ listaActiuni(L("mai_mult"), S.actDrum); })); }
  }
}
function meniuSursa(){
  var chei = cheiSursa(), act = [];
  if(!chei.length){ return; }
  var x = chei.length === 1 ? S.sv[S.svIndex[chei[0]]] : null;
  act.push({text: L("adauga_in") + (numeBuchetAcum() ? ": " + numeBuchetAcum() : ""), fa: function(){ adaugaCanale(chei); }});
  act.push({text: L("buchet_din_alese"), fa: function(){ buchetNou(null, chei); }});
  if(x){ act.push({text: L("redenumeste_tot"), fa: function(){
    cereText(L("redenumeste_tot"), L("nume"), x[2], function(v){ op({op: "redenumeste_serviciu", chei: chei, nume: v}); });
  }}); }
  if(x){ act.push({text: L("porneste_tv"), fa: function(){ pornesteTv(x[0]); }}); }
  if(x){
    act.push({text: L("detalii"), fa: function(){ arataDetalii(x[0]); }});
    act.push({text: L("pune_sigla"), fa: function(){ puneSigla(x[0]); }});
    act.push({text: L("copiaza_sigla"), fa: function(){ copiazaSigla(x[0]); }});
    if(x[13]){ act.push({text: L("sterge_sigla"), clasa: "rosu", fa: function(){ stergeSigla(x[0]); }}); }
    if(x[11]){ act.push({text: L("scoate_din_unul"), fa: function(){ scoateDinUnul(x[0]); }}); }
  }
  if(chei.some(function(k){ return S.sv[S.svIndex[k]][10] & 16; })){ act.push({text: L("scoate_nou"), fa: function(){ op({op: "scoate_nou", chei: chei}).then(function(){ incarcaServicii(); }); }}); }
  if(chei.some(function(k){ return S.sv[S.svIndex[k]][11]; })){ act.push({text: L("scoate_din_toate"), fa: function(){ scoateDinToate(chei); }}); }
  var toateAscunse = chei.every(function(k){ return S.sv[S.svIndex[k]][10] & 1; });
  var toateBlocate = chei.every(function(k){ return S.sv[S.svIndex[k]][10] & 2; });
  act.push({text: toateAscunse ? L("arata") : L("ascunde"), fa: function(){ op({op: "ascunde", chei: chei, da: !toateAscunse}); }});
  act.push({text: toateBlocate ? L("deblocheaza") : L("blocheaza"), fa: function(){ op({op: "blocheaza", chei: chei, da: !toateBlocate}); }});
  act.push({text: L("sterge_receptor"), clasa: "rosu", fa: function(){ stergeDinReceptor(chei); selTotSursa(false); }});
  act.push({text: L("sel_tot"), fa: function(){ selTotSursa(true); }});
  act.push({text: L("desel_tot"), fa: function(){ selTotSursa(false); }});
  listaActiuni(nCanale(chei.length), act);
}
function adaugaCanale(chei, inainte){
  if(laRadacina()){ mesaj(L("alege_buchet"), true); if(ingust()){ comutaPanou("buchet"); } return; }
  op({op: "adauga", buchet: buchetAcum(), chei: chei, inainte_de: inainte === undefined ? null : inainte}).then(function(r){
    if(r && r.n){ selTotSursa(false); mesaj(r.de_anulat || ""); }
  });
}
$("cauta").addEventListener("input", function(){ S.text = this.value; clearTimeout(S.ceasCauta); S.ceasCauta = setTimeout(function(){ filtreaza(); }, 120); });
Array.prototype.forEach.call(document.querySelectorAll("#filtre button[data-f]"), function(b){
  b.onclick = function(){
    var f = b.getAttribute("data-f"), da = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", da ? "true" : "false");
    S.filtre[f] = da;
    tine("hds-editor-filtre", JSON.stringify(S.filtre));
    if(da && (f === "hd" || f === "sd")){ var o = f === "hd" ? "sd" : "hd"; S.filtre[o] = false; document.querySelector('#filtre [data-f="' + o + '"]').setAttribute("aria-pressed", "false"); }
    if(da && (f === "fta" || f === "criptat")){ var o2 = f === "fta" ? "criptat" : "fta"; S.filtre[o2] = false; document.querySelector('#filtre [data-f="' + o2 + '"]').setAttribute("aria-pressed", "false"); }
    filtreaza();
  };
});
function filtreBaza(){
  function arata(){
    var corp = [el("p", "", L("filtre_nota"))];
    S.fb.grupe.forEach(function(g, gi){
      var gr = el("div", "grupa");
      gr.appendChild(el("h3", "", g[1]));
      g[2].forEach(function(o){
        var lab = el("label", "opt"), c = el("input");
        c.type = "checkbox"; c.checked = !!((S.fsel[gi] || 0) & o[0]);
        c.addEventListener("change", function(){ S.fsel[gi] = (S.fsel[gi] || 0) ^ o[0]; });
        lab.appendChild(c); lab.appendChild(document.createTextNode(o[1] + " (" + o[2] + ")"));
        gr.appendChild(lab);
      });
      corp.push(gr);
    });
    foaie(L("filtre_baza"), corp, [
      {text: L("sterge_filtrele"), fa: function(){ S.fsel = {}; aplicaFiltreBaza(); }},
      {text: L("ok"), clasa: "principal", fa: aplicaFiltreBaza}]);
  }
  if(S.fb){ arata(); return; }
  mesaj(L("filtre_citire"));
  cerere("/api/editor-canale-filtre").then(function(r){
    if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
    S.fb = r; S.fsel = {}; arata();
  });
}
function aplicaFiltreBaza(){
  var n = 0;
  for(var g in S.fsel){ if(S.fsel[g]){ n++; } }
  S.nfb = n;
  $("maiMulteFiltre").setAttribute("aria-pressed", n ? "true" : "false");
  filtreaza();
}
$("maiMulteFiltre").onclick = filtreBaza;
Array.prototype.forEach.call(document.querySelectorAll("#filtre button[data-f]"), function(b){ if(S.filtre[b.getAttribute("data-f")]){ b.setAttribute("aria-pressed", "true"); } });
function alegeSursa(fel){
  S.sursa = fel; S.sursaPoz = null; S.sursaFurn = null; S.sursaTp = null; S.lsel = {}; S.sursaBuchet = null; S.sursaRanduri = null;
  [["sursaToate", "toate"], ["sursaSateliti", "sateliti"], ["sursaFurnizori", "furnizori"], ["sursaBuchete", "buchete"]].forEach(function(x){
    $(x[0]).setAttribute("aria-selected", x[1] === fel ? "true" : "false");
  });
  filtreaza();
}
$("sursaToate").onclick = function(){ alegeSursa("toate"); };
$("sursaSateliti").onclick = function(){ alegeSursa("sateliti"); };
$("sursaFurnizori").onclick = function(){ alegeSursa("furnizori"); };
$("sursaBuchete").onclick = function(){ alegeSursa("buchete"); };
function comutaPanou(p){
  S.panou = p;
  $("arataBuchet").setAttribute("aria-selected", p === "buchet" ? "true" : "false");
  $("arataSursa").setAttribute("aria-selected", p === "sursa" ? "true" : "false");
  $("panouBuchet").classList.toggle("ascuns-ingust", p !== "buchet");
  $("panouSursa").classList.toggle("ascuns-ingust", p !== "sursa");
  VB.arata(true); VS.arata(true);
  deseneazaBaraBuchet(); deseneazaBaraSursa();
}
$("arataBuchet").onclick = function(){ comutaPanou("buchet"); };
$("arataSursa").onclick = function(){ comutaPanou("sursa"); };
comutaPanou("buchet");
function alegeFila(radio){
  if(radio === S.radio){ return; }
  S.radio = radio;
  $("filaTv").setAttribute("aria-selected", radio ? "false" : "true");
  $("filaRadio").setAttribute("aria-selected", radio ? "true" : "false");
  S.drum = [radacina()]; S.sel = {}; S.nsel = 0; S.ssel = {}; S.nssel = 0; S.sv = []; S.focus = -1; S.sursaTp = null; S.lsel = {};
  S.sursaBuchet = null; S.sursaRanduri = null;
  incarcaArbore(); incarcaBuchet(); incarcaServicii();
}
$("filaTv").onclick = function(){ alegeFila(false); };
$("filaRadio").onclick = function(){ alegeFila(true); };

// ---------------------------------------------------------------- tragerea (mouse si deget)
var T = null;
function incepeTragerea(ev, din, i){
  if(ev.button > 0){ return; }
  ev.preventDefault();
  var ids, chei, text;
  if(din === "buchet"){
    var r = S.randuri[i];
    if(!S.sel[r[0]]){ alegeNumai(i); }
    ids = idsAlese(); text = nAlese(ids.length);
  } else {
    var x = S.sv[S.vazute[i]];
    if(!S.ssel[x[0]]){ comutaSSel(i, true); }
    chei = cheiSursa(); text = nCanale(chei.length);
  }
  var f = el("div", "", text); f.id = "fantoma"; document.body.appendChild(f);
  T = {din: din, ids: ids, chei: chei, fantoma: f, tinta: -1, x: ev.clientX, y: ev.clientY, id: ev.pointerId};
  try { ev.target.setPointerCapture(ev.pointerId); } catch(e){}
  // pe document, nu pe maner: randul poate fi desenat din nou cat tine tragerea (derularea listei)
  document.addEventListener("pointermove", miscaTragerea);
  document.addEventListener("pointerup", lasaTragerea);
  document.addEventListener("pointercancel", opresteTragerea);
  miscaTragerea(ev);
}
function miscaTragerea(ev){
  if(!T || ev.pointerId !== T.id){ return; }
  T.x = ev.clientX; T.y = ev.clientY;
  T.fantoma.style.left = (ev.clientX + 14) + "px"; T.fantoma.style.top = (ev.clientY + 10) + "px";
  var l = $("listaBuchet"), r = l.getBoundingClientRect();
  var inauntru = ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top - 30 && ev.clientY <= r.bottom + 30;
  if(inauntru){
    if(ev.clientY < r.top + 40){ l.scrollTop -= 18; } else if(ev.clientY > r.bottom - 40){ l.scrollTop += 18; }
    T.tinta = VB.indiceLa(ev.clientY);
  } else { T.tinta = -1; }
  Array.prototype.forEach.call(l.querySelectorAll(".rand.tinta-sus"), function(e){ e.classList.remove("tinta-sus"); });
  if(T.tinta >= 0 && VB.desenate[T.tinta]){ VB.desenate[T.tinta].classList.add("tinta-sus"); }
}
function lasaTragerea(ev){
  if(!T || ev.pointerId !== T.id){ return; }
  var t = T; opresteTragerea(ev);
  if(t.tinta < 0){ return; }
  var inainte = t.tinta < S.randuri.length ? S.randuri[t.tinta][0] : null;
  if(t.din === "buchet"){
    while(inainte !== null && S.sel[inainte]){
      var k = S.randuri.findIndex(function(r){ return r[0] === inainte; }) + 1;
      inainte = k < S.randuri.length ? S.randuri[k][0] : null;
    }
    op({op: "muta", buchet: buchetAcum(), ids: t.ids, inainte_de: inainte});
  } else {
    adaugaCanale(t.chei, inainte);
  }
}
function opresteTragerea(ev){
  if(!T){ return; }
  if(T.fantoma.parentNode){ T.fantoma.parentNode.removeChild(T.fantoma); }
  Array.prototype.forEach.call(document.querySelectorAll(".rand.tinta-sus"), function(e){ e.classList.remove("tinta-sus"); });
  document.removeEventListener("pointermove", miscaTragerea);
  document.removeEventListener("pointerup", lasaTragerea);
  document.removeEventListener("pointercancel", opresteTragerea);
  T = null;
}

// ---------------------------------------------------------------- tastele (numai scurtaturi)
document.addEventListener("keydown", function(ev){
  if(!S.gata || S.vedere){ if(ev.key === "Escape"){ if(!$("foaie").classList.contains("ascuns")){ inchideFoaia(); } else if(S.vedere){ inchideVederea(); } } return; }
  if(!$("foaie").classList.contains("ascuns")){ if(ev.key === "Escape"){ inchideFoaia(); } return; }
  var tinta = ev.target, inCamp = tinta && (tinta.tagName === "INPUT" && tinta.type !== "checkbox" || tinta.tagName === "SELECT" || tinta.tagName === "TEXTAREA");
  var ctrl = ev.ctrlKey || ev.metaKey, k = ev.key;
  if(ctrl && (k === "s" || k === "S")){ ev.preventDefault(); salveaza(); return; }
  if(ctrl && (k === "f" || k === "F")){ ev.preventDefault(); if(ingust()){ comutaPanou("sursa"); } $("cauta").focus(); $("cauta").select(); return; }
  if(inCamp){ if(k === "Escape"){ tinta.blur(); } return; }
  var inSursa = document.activeElement && $("panouSursa").contains(document.activeElement) && !$("panouBuchet").contains(document.activeElement);
  if(ctrl && (k === "z" || k === "Z") && !ev.shiftKey){ ev.preventDefault(); $("anuleaza").click(); return; }
  if(ctrl && ((k === "y" || k === "Y") || ((k === "z" || k === "Z") && ev.shiftKey))){ ev.preventDefault(); $("reface").click(); return; }
  if(inSursa){ tasteSursa(ev, ctrl, k); return; }
  var n = S.randuri.length;
  if(k === "ArrowDown" || k === "ArrowUp"){
    ev.preventDefault();
    if(ctrl && S.nsel){ op({op: k === "ArrowUp" ? "muta_sus" : "muta_jos", buchet: buchetAcum(), ids: idsAlese()}); return; }
    var nou = Math.max(0, Math.min(n - 1, S.focus + (k === "ArrowDown" ? 1 : -1)));
    if(S.focus < 0){ nou = 0; }
    if(ev.shiftKey){ if(S.ancora < 0){ S.ancora = Math.max(0, S.focus); } S.focus = nou; alegeIntre(S.ancora, nou); }
    else { S.focus = nou; }
    VB.laVedere(nou); VB.arata(); redaSel(); return;
  }
  if(k === "PageDown" || k === "PageUp" || k === "Home" || k === "End"){
    ev.preventDefault();
    var pas = Math.max(1, Math.floor($("listaBuchet").clientHeight / H) - 1);
    if(ctrl && S.nsel){
      // Ctrl + Home / End / PageUp / PageDown muta randurile alese la inceput, la sfarsit sau o pagina
      var a0 = 0; for(; a0 < n && !S.sel[S.randuri[a0][0]]; a0++){}
      var poz = k === "Home" ? 1 : k === "End" ? n + 1 : Math.max(1, Math.min(n + 1, a0 + 1 + (k === "PageDown" ? pas : -pas)));
      op({op: "muta", buchet: buchetAcum(), ids: idsAlese(), pozitie: poz}); return;
    }
    S.focus = k === "Home" ? 0 : k === "End" ? n - 1 : Math.max(0, Math.min(n - 1, S.focus + (k === "PageDown" ? pas : -pas)));
    VB.laVedere(S.focus); VB.arata(); redaSel(); return;
  }
  if(k === " " && S.focus >= 0){ ev.preventDefault(); comutaSel(S.focus, !S.sel[S.randuri[S.focus][0]]); S.ancora = S.focus; return; }
  if(k === "Enter" && S.focus >= 0){ var r = S.randuri[S.focus]; if(r[1] === "b" || r[1] === "a"){ intraIn(r[7], r[2]); } return; }
  if(k === "Delete"){ if(!S.nsel && S.focus >= 0){ alegeNumai(S.focus); } ev.preventDefault(); stergeAlese(); return; }
  if(k === "Escape"){ if(S.nsel){ selTot(false); } else if(S.drum.length > 1){ S.drum.pop(); incarcaBuchet(); } return; }
  if(k === "F2"){ ev.preventDefault(); if(!S.nsel && S.focus >= 0){ alegeNumai(S.focus); } var a = alesele(); if(a.length === 1){ redenumeste(a[0], false); } return; }
  if(ctrl && (k === "a" || k === "A")){ ev.preventDefault(); selTot(true); return; }
  if(ctrl && (k === "c" || k === "C" || k === "x" || k === "X") && S.nsel){
    ev.preventDefault();
    S.clip = {fel: (k === "x" || k === "X") ? "taiere" : "copie", din: buchetAcum(), ids: idsAlese()};
    mesaj(L("copiat")); return;
  }
  if(ctrl && (k === "v" || k === "V") && S.clip){
    ev.preventDefault();
    var inainte = S.focus >= 0 && S.focus < n ? S.randuri[S.focus][0] : null, c = S.clip;
    if(c.fel === "canale"){ adaugaCanale(c.chei, inainte); return; }
    if(c.din === buchetAcum()){
      op(c.fel === "taiere" ? {op: "muta", buchet: c.din, ids: c.ids, inainte_de: inainte} : {op: "copiaza", din: c.din, "in": c.din, ids: c.ids, inainte_de: inainte});
    } else {
      op({op: c.fel === "taiere" ? "muta_in" : "copiaza", din: c.din, "in": buchetAcum(), ids: c.ids, inainte_de: inainte});
    }
    if(c.fel === "taiere"){ S.clip = null; }
    return;
  }
});
function tasteSursa(ev, ctrl, k){
  var n = S.vazute ? S.vazute.length : 0;
  if(k === "ArrowDown" || k === "ArrowUp"){
    ev.preventDefault();
    if(!n){ return; }
    var nou = Math.max(0, Math.min(n - 1, S.sfocus + (k === "ArrowDown" ? 1 : -1)));
    if(ev.shiftKey){ comutaSSel(nou, true); }
    S.sfocus = nou; VS.laVedere(nou); VS.arata(); redaSel(); return;
  }
  if(k === " " && S.sfocus >= 0 && n){ ev.preventDefault(); comutaSSel(S.sfocus, !S.ssel[S.sv[S.vazute[S.sfocus]][0]]); return; }
  if(k === "Enter" && S.sfocus >= 0 && n){ ev.preventDefault(); adaugaCanale(S.nssel ? cheiSursa() : [S.sv[S.vazute[S.sfocus]][0]]); return; }
  if(ctrl && (k === "a" || k === "A")){ ev.preventDefault(); selTotSursa(true); return; }
  if(ctrl && (k === "c" || k === "C") && S.nssel){ ev.preventDefault(); S.clip = {fel: "canale", chei: cheiSursa()}; mesaj(L("copiat")); return; }
  if(k === "Escape"){ selTotSursa(false); }
}

// ---------------------------------------------------------------- uneltele, copiile, importul, exportul
function arataVederea(){
  S.vedere = true;
  $("editor").classList.add("ascuns");
  $("vedere").classList.remove("ascuns");
  gol($("vedere"));
  window.scrollTo(0, 0);
}
function inchideVederea(){
  S.vedere = null;
  $("vedere").classList.add("ascuns");
  $("editor").classList.remove("ascuns");
  VB.arata(true); VS.arata(true);
}
function capVedere(titlu){
  var c = el("div", "rand-cap");
  c.appendChild(el("h2", "", titlu));
  c.appendChild(buton(L("inapoi"), inchideVederea));
  $("vedere").appendChild(c);
}
function unealta(fel, titlu){
  arataVederea();
  capVedere(titlu);
  var stare = el("p", "", L("se_cauta")); $("vedere").appendChild(stare);
  cerere("/api/editor-canale-unelte?fel=" + fel).then(function(r){
    if(!r.result){ stare.textContent = r.message || L("eroare_retea"); return; }
    stare.parentNode.removeChild(stare);
    var bife = [], numaiVedere = fel.indexOf("compara") === 0 || fel === "verifica";
    var idCopie = (/[&]id=([^&]+)/.exec(fel) || [])[1];
    // grupele care au o actiune a lor (bifabile, cu butonul sub titlu)
    var actiuniGrupe = {
      fara_satelit: [L("sterge_bifate_receptor"), "rosu", function(x){ stergeDinReceptor(x.map(function(r){ return r[0]; })); }],
      date: [L("sterge_bifate_receptor"), "rosu", function(x){ stergeDinReceptor(x.map(function(r){ return r[0]; })); }],
      marcaje_goale: [L("sterge_marcajele_bifate"), "rosu", function(x){ op({op: "sterge_randuri", randuri: x.map(function(r){ return [r[11], r[12]]; })}).then(function(){ unealta(fel, titlu); }); }]
    };
    if(idCopie){
      actiuniGrupe.canale_noi = [L("buchet_din_bifate"), "principal", function(x){ buchetNou(null, x.map(function(r){ return r[0]; })); }];
      actiuniGrupe.canale_scoase = [L("adu_inapoi"), "principal", function(x){ op({op: "readu_din_copie", id: decodeURIComponent(idCopie), chei: x.map(function(r){ return r[0]; })}).then(function(){ incarcaServicii(); unealta(fel, titlu); }); }];
    }
    function numara(){ var n = bife.filter(function(b){ return b.c.checked; }).length; actiune.disabled = !n; actiune.textContent = textActiune + (n ? " (" + n + ")" : ""); }
    var textActiune = fel === "test" ? L("sterge_bifate_receptor") : fel === "moarte" ? L("repara") : fel === "dubluri" ? L("sterge_randuri") : fel === "transpondere" ? L("sterge_tp_bifate") :
      fel === "fluxuri" ? L("scoate_din_buchete_bifate") : fel === "sigle_nefolosite" ? L("sterge_siglele_bifate") : L("sterge_buchet");
    r.grupe.forEach(function(g){
      var gr = el("div", "grupa");
      gr.appendChild(el("h3", "", g.titlu + " (" + g.randuri.length + ")"));
      gr.appendChild(el("p", "expl", g.explicatie));
      var bifabil = !(fel === "dubluri" && g.id !== "in_buchet") && (!numaiVedere || !!actiuniGrupe[g.id]);
      var aleGrupei = [];
      if(bifabil && g.randuri.length){
        var bt = el("div", ""); bt.style.display = "flex"; bt.style.gap = "8px"; bt.style.marginBottom = "6px";
        bt.appendChild(buton(L("bifeaza_tot"), function(){ aleGrupei.forEach(function(b){ b.c.checked = true; }); numara(); }, "mic"));
        bt.appendChild(buton(L("debifeaza_tot"), function(){ aleGrupei.forEach(function(b){ b.c.checked = false; }); numara(); }, "mic"));
        gr.appendChild(bt);
      }
      if(!g.randuri.length){ gr.appendChild(el("p", "expl", L("nimic_unealta"))); }
      g.randuri.forEach(function(x){
        var rd = el("div", "rand-u"), lab = el("label"), c = el("input");
        c.type = "checkbox"; c.disabled = !bifabil;
        if(bifabil){ lab.appendChild(c); }
        var t = el("div", "");
        t.appendChild(el("div", "n", x[2] || "?"));
        var det = [x[3], x[10] || (x[4] ? x[4] + " " + x[5] : ""), x[6] !== null && x[6] !== undefined ? "SID " + x[6] : ""].filter(Boolean).join(" · ");
        if(x[14]){ det = x[14] + (det ? " · " + det : ""); }
        if(fel === "transpondere"){ det = x[3]; }
        if(fel === "sigle_nefolosite"){ det = x[3]; }
        if(fel === "fluxuri" || g.id === "marcaje_goale"){ det = [x[3], x[14]].filter(Boolean).join(" · "); }
        t.appendChild(el("div", "d", det));
        if(fel === "test"){
          var vs = L("imagine") + ": " + (x[7] === null ? L("nu_se_stie") : x[7] ? L("da") : L("nu")) + " · " + L("sunet") + ": " + (x[8] === null ? L("nu_se_stie") : x[8] ? L("da") : L("nu"));
          if(x[9]){ vs += " · " + L("in_buchete") + x[9]; }
          t.appendChild(el("div", "d", vs));
        }
        if(fel === "moarte"){ t.appendChild(el("div", "d", x[13] ? L("inlocuire") + x[13] : L("fara_inlocuire"))); }
        lab.appendChild(t); rd.appendChild(lab); gr.appendChild(rd);
        if(bifabil){ var b = {c: c, x: x, g: g.id}; bife.push(b); aleGrupei.push(b); c.addEventListener("change", numara); }
      });
      if(actiuniGrupe[g.id] && g.randuri.length){
        var ag = actiuniGrupe[g.id];
        gr.appendChild(buton(ag[0], function(){
          var x = aleGrupei.filter(function(b){ return b.c.checked; }).map(function(b){ return b.x; });
          if(x.length){ ag[2](x); }
        }, ag[1] + " actiune-grupa"));
      }
      $("vedere").appendChild(gr);
    });
    if(fel === "compara_import" && S.importAplica){
      var bi = el("div", "bara-vedere");
      bi.appendChild(buton(L("inapoi_import"), function(){ inchideVederea(); S.importArata(); }));
      bi.appendChild(buton(L("import_uneste"), function(){ inchideVederea(); S.importAplica("uneste"); }));
      bi.appendChild(buton(L("import_inlocuieste"), function(){ inchideVederea(); S.importAplica("inlocuieste"); }, "rosu"));
      $("vedere").appendChild(bi);
    }
    if(numaiVedere){ return; }
    var bara = el("div", "bara-vedere");
    var actiune = buton(textActiune, function(){
      var alese = bife.filter(function(b){ return b.c.checked; }).map(function(b){ return b.x; });
      if(!alese.length){ return; }
      if(fel === "test"){
        intreaba(nCanale(alese.length) + ". " + L("q_sterge_receptor"), L("sterge_receptor"), function(){
          op({op: "sterge_servicii", chei: alese.map(function(x){ return x[0]; })}, true).then(function(r){ if(r){ unealta(fel, titlu); incarcaServicii(); } });
        }, true);
      } else if(fel === "moarte"){
        op({op: "repara_moarte", randuri: alese.map(function(x){ return [x[11], x[12]]; })}).then(function(r){ if(r){ unealta(fel, titlu); } });
      } else if(fel === "dubluri"){
        intreaba(nAlese(alese.length) + ". " + L("q_sterge_buchet"), L("sterge"), function(){
          op({op: "sterge_randuri", randuri: alese.map(function(x){ return [x[11], x[12]]; })}).then(function(r){ if(r){ unealta(fel, titlu); } });
        }, true);
      } else if(fel === "fluxuri"){
        intreaba(nAlese(alese.length) + ". " + L("q_sterge_buchet"), L("sterge"), function(){
          op({op: "sterge_randuri", randuri: alese.map(function(x){ return [x[11], x[12]]; })}).then(function(r){ if(r){ unealta(fel, titlu); } });
        }, true);
      } else if(fel === "sigle_nefolosite"){
        intreaba(nAlese(alese.length) + ". " + L("sterge_siglele_bifate") + "?", L("sterge"), function(){
          cerere("/api/editor-canale-sigla?fel=sterge_nefolosite", "POST", {cai: alese.map(function(x){ return x[0]; })}).then(function(r){
            if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; } unealta(fel, titlu);
          });
        }, true);
      } else if(fel === "transpondere"){
        intreaba(L("transpondere_n") + " " + alese.length + ". " + L("q_sterge_tp_goale"), L("sterge_tp_bifate"), function(){
          op({op: "sterge_transpondere", tpuri: alese.map(function(x){ return x[0]; })}, true).then(function(r){ if(r){ unealta(fel, titlu); } });
        }, true);
      } else if(fel === "goale"){
        alese.forEach(function(x){ op({op: "sterge_buchet", buchet: x[11]}); });
        setTimeout(function(){ unealta(fel, titlu); incarcaArbore(); }, 600);
      }
    }, fel === "moarte" ? "principal" : "rosu");
    actiune.disabled = true;
    bara.appendChild(actiune);
    bara.appendChild(buton(L("anuleaza"), function(){ $("anuleaza").click(); setTimeout(function(){ unealta(fel, titlu); }, 400); }));
    $("vedere").appendChild(bara);
  });
}
function copii(){
  arataVederea();
  capVedere(L("copii"));
  cerere("/api/editor-canale-copii").then(function(r){
    if(!r.result){ $("vedere").appendChild(el("p", "", r.message || L("eroare_retea"))); return; }
    if(!r.copii.length){ $("vedere").appendChild(el("p", "", L("fara_copii"))); return; }
    r.copii.forEach(function(c){
      var g = el("div", "grupa"), d = new Date(c[1] * 1000);
      g.appendChild(el("h3", "", d.toLocaleDateString() + " " + d.toLocaleTimeString().slice(0, 5)));
      g.appendChild(el("p", "expl", [c[2], nCanale(c[5]), (c[3] / 1024).toFixed(0) + " KB"].filter(Boolean).join(" · ")));
      g.appendChild(buton(L("descarca"), function(){ descarca("/api/editor-canale-copie?id=" + encodeURIComponent(c[0])); }));
      g.appendChild(buton(L("compara"), function(){
        unealta("compara&id=" + encodeURIComponent(c[0]), L("compara") + ": " + d.toLocaleDateString() + " " + d.toLocaleTimeString().slice(0, 5));
      }));
      g.appendChild(buton(L("intoarce"), function(){
        intreaba(L("q_intoarce"), L("intoarce"), function(){
          cerere("/api/editor-canale-intoarce?id=" + encodeURIComponent(c[0]), "POST").then(function(r2){
            if(!r2.result){ mesaj(r2.message || L("eroare_retea"), true); return; }
            mesaj(L("se_intoarce"));
            asteapta(function(st){
              if(st.rezultat && st.rezultat.fel === "intors"){ mesaj(L("intors")); }
              inchideVederea(); S.drum = [radacina()]; S.sursaBuchet = null; S.sursaRanduri = null;
              incarcaArbore(); incarcaBuchet(); incarcaServicii();
            });
          });
        }, true);
      }));
      $("vedere").appendChild(g);
    });
  });
}
function descarca(cale){
  var a = document.createElement("a");
  a.href = adresa(cale + (cale.indexOf("?") === -1 ? "?" : "&") + "eu=" + EU);
  a.download = "";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}
var FEL_IMPORT = null;
$("fisier").addEventListener("change", function(){
  var f = this.files && this.files[0];
  this.value = "";
  if(!f){ return; }
  var fel = FEL_IMPORT;
  f.arrayBuffer().then(function(buf){
    if(fel === "m3u"){
      var nume = el("input"); nume.type = "text"; nume.value = f.name.replace(/\.m3u8?$/i, "");
      var ln = el("label", "", L("nume")); ln.style.display = "flex"; ln.style.flexDirection = "column"; ln.style.gap = "6px"; ln.appendChild(nume);
      foaie(L("import_m3u"), [ln], [{text: L("renunta")},
        {text: L("m3u_pe_grupe"), fa: function(){ trimiteM3u(buf, nume.value, true); }},
        {text: L("m3u_un_buchet"), clasa: "principal", fa: function(){ trimiteM3u(buf, nume.value, false); }}]);
      return;
    }
    cerere("/api/editor-canale-import?fel=arhiva", "POST", buf, "application/octet-stream").then(function(r){
      if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
      var l = el("div", "lista-actiuni"), bife = [];
      r.buchete.forEach(function(b){
        var lab = el("label", "opt"), c = el("input"); c.type = "checkbox"; c.checked = true;
        lab.appendChild(c); lab.appendChild(document.createTextNode(b[1] + " (" + nCanale(b[2]) + ")"));
        l.appendChild(lab); bife.push([c, b[0]]);
      });
      function aplica(mod){
        var alese = bife.filter(function(x){ return x[0].checked; }).map(function(x){ return x[1]; });
        cerere("/api/editor-canale-import-aplica", "POST", {mod: mod, ce: ["lamedb", "buchete"], buchete: alese.length === bife.length ? [] : alese}).then(function(r2){
          if(!r2.result){ mesaj(r2.message || L("eroare_retea"), true); return; }
          puneStarea(r2); S.drum = [radacina()]; incarcaArbore(); incarcaBuchet(); incarcaServicii();
          mesaj(r2.de_anulat || L("gata"));
        });
      }
      S.importAplica = aplica;
      S.importArata = function(){
        foaie(L("import_ce"), [el("p", "", L("import_canale_text") + r.servicii + " · " + r.buchete.length), r.buchete.length ? el("p", "", L("import_buchete")) : null, l],
          [{text: L("renunta")}, {text: L("vezi_ce_se_schimba"), fa: function(){ unealta("compara_import", L("vezi_ce_se_schimba")); }},
            {text: L("import_uneste"), fa: function(){ aplica("uneste"); }}, {text: L("import_inlocuieste"), clasa: "rosu", fa: function(){ aplica("inlocuieste"); }}]);
      };
      S.importArata();
    });
  });
});
function trimiteM3u(buf, nume, grupe){
  cerere("/api/editor-canale-import?fel=m3u&radio=" + (S.radio ? 1 : 0) + "&grupe=" + (grupe ? 1 : 0) + "&nume=" + encodeURIComponent(nume || ""), "POST", buf, "application/octet-stream").then(function(r){
    if(!r.result){ mesaj(r.message || L("eroare_retea"), true); return; }
    puneStarea(r); incarcaArbore(); incarcaBuchet();
    if(r.buchet){ S.drum = [radacina(), r.buchet]; incarcaBuchet(); }
  });
}
function importa(fel){ FEL_IMPORT = fel; $("fisier").click(); }
$("maiMultSus").onclick = function(){
  if(!S.gata){ return; }
  listaActiuni(L("mai_mult"), [
    S.deRefacut ? {text: L("reface") + ": " + S.deRefacut, fa: function(){ $("reface").click(); }} : null,
    S.nesalvate ? {text: L("schimbari"), fa: arataSchimbari} : null,
    {text: L("unelte_test"), fa: function(){ unealta("test", L("unelte_test")); }},
    {text: L("unelte_dubluri"), fa: function(){ unealta("dubluri", L("unelte_dubluri")); }},
    {text: L("unelte_moarte"), fa: function(){ unealta("moarte", L("unelte_moarte")); }},
    {text: L("unelte_goale"), fa: function(){ unealta("goale", L("unelte_goale")); }},
    {text: L("unelte_tp"), fa: function(){ unealta("transpondere", L("unelte_tp")); }},
    {text: L("verifica"), fa: function(){ unealta("verifica", L("verifica")); }},
    {text: L("fluxuri"), fa: function(){ unealta("fluxuri", L("fluxuri")); }},
    {text: L("curatenie"), fa: curatenie},
    {text: L("sigle"), fa: sigle},
    {text: L("inlocuieste_nume"), fa: inlocuiesteNume},
    {text: L("marime_litere"), fa: marimeLitere},
    {text: L(S.avansat ? "avansat_pornit" : "avansat_oprit"), fa: comutaAvansat},
    S.avansat ? {text: L("sateliti_xml"), fa: satelitiXml} : null,
    {text: L("copii"), fa: copii},
    {text: L("import_arhiva"), fa: function(){ importa("arhiva"); }},
    {text: L("import_m3u"), fa: function(){ importa("m3u"); }},
    {text: L("export_zip"), fa: function(){ descarca("/api/editor-canale-export?fel=zip"); }},
    {text: L("export_tar"), fa: function(){ descarca("/api/editor-canale-export?fel=tar.gz"); }},
    {text: L("ajutor"), fa: function(){ foaie(L("ajutor"), [L("ajutor_text"), L("ajutor_taste")], [{text: L("ok"), clasa: "principal"}]); }},
    {text: L("inchide_editor"), fa: inchideEditorul}
  ]);
};
function inchideEditorul(){
  function inchide(){ cerere("/api/editor-canale-inchide", "POST").then(function(){ S.gata = false; S.plecat = true; location.href = "/canale"; }); }
  if(S.nesalvate){ intreaba(L("q_iesire"), L("inchide_editor"), inchide, true); } else { inchide(); }
}
$("preia").onclick = function(){ intreaba(L("q_preia"), L("deschide_iar"), function(){ deschide(true); }, true); };
$("incearca").onclick = function(){ deschide(false); };
window.addEventListener("beforeunload", function(ev){
  if(S.nesalvate && !S.plecat){ ev.preventDefault(); ev.returnValue = ""; return ""; }
});
function potrivesteInaltimea(){
  // calculator: panourile umplu ecranul de sub antetul cadrului, fara sa coboare pagina. Telefon: bara editorului
  // (TV / Radio, Buchet / Adaugă canale, Anulează, Salvează) sta sus pe ecran si panoul umple restul pana la bara de
  // jos a cadrului; pagina coboara o data, la deschidere, pana la bara editorului (antetul site-ului iese din ecran)
  var c = document.querySelector(".coloane");
  if(!c || $("editor").classList.contains("ascuns")){ return; }
  var jos = window.innerHeight;
  var nav = document.querySelector("nav.hds-jos");
  if(nav && getComputedStyle(nav).display !== "none"){ jos = Math.min(jos, nav.getBoundingClientRect().top); }
  var h;
  if(ingust()){
    // antetul cadrului (siglă, drumul, canalul de acum) sta si el sus pe ecran: bara editorului se lipeste sub el
    var antet = document.querySelector(".hds-antet"), hA = 0;
    if(antet && getComputedStyle(antet).position !== "static"){ hA = antet.getBoundingClientRect().height; }
    document.documentElement.style.setProperty("--sus-editor", hA + "px");
    var bara = document.querySelector(".sus");
    h = Math.max(240, jos - hA - bara.getBoundingClientRect().height - 12);
    if(!S.derulat){
      S.derulat = true;
      window.scrollTo(0, Math.max(0, bara.getBoundingClientRect().top + window.scrollY - hA - 2));
    }
  } else {
    h = Math.max(300, jos - (c.getBoundingClientRect().top + window.scrollY) - 8);
  }
  document.documentElement.style.setProperty("--inaltime-panou", h + "px");
  VB.arata(true); VS.arata(true);
}
window.addEventListener("resize", function(){ potrivesteInaltimea(); deseneazaBaraBuchet(); deseneazaBaraSursa(); });
deschide(false);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
TEXTE_PAGINA = {
	"html": (
		N_("Editorul de canale"),
		N_("Radio"),
		N_("Buchet"),
		N_("Adaugă canale"),
		N_("Anulează schimbarea"),
		N_("Refă"),
		N_("Salvează"),
		N_("Mai mult"),
		N_("Se citește lista de canale..."),
		N_("Preia lista aici"),
		N_("Încearcă din nou"),
		N_("Toate"),
		N_("Sateliți"),
		N_("Furnizori"),
		N_("HD și 4K"),
		N_("Necriptate"),
		N_("Criptate"),
		N_("În niciun buchet"),
		N_("Ascunse"),
		N_("Limba, subtitrări și altele"),
		N_("Lista buchetelor"),
		N_("Toate canalele"),
		N_("Fără furnizor"),
		N_("Adaugă"),
		N_("Adaugă în buchet"),
		N_("Mută sus"),
		N_("Mută jos"),
		N_("Mută la poziția..."),
		N_("Mută în..."),
		N_("Copiază în..."),
		N_("Șterge"),
		N_("Șterge din receptor"),
		N_("Redenumește"),
		N_("Redenumește peste tot"),
		N_("Ascunde"),
		N_("Arată"),
		N_("Blochează"),
		N_("Deblochează"),
		N_("Sortează"),
		N_("Sortează cele alese"),
		N_("Selectează tot"),
		N_("Deselectează tot"),
		N_("Selectează grupa de sub marcaj"),
		N_("Marcaj nou"),
		N_("Rând gol nou"),
		N_("Flux nou (adresă de internet)"),
		N_("Buchet nou"),
		N_("Sub-buchet nou"),
		N_("Buchet nou din cele alese"),
		N_("Fă un buchet din acest satelit"),
		N_("Fă un buchet din acest furnizor"),
		N_("Deschide"),
		N_("Redenumește buchetul"),
		N_("Copiază buchetul"),
		N_("Șterge buchetul"),
		N_("Blochează buchetul"),
		N_("Deblochează buchetul"),
		N_("Descarcă buchetul (m3u)"),
		N_("Canale de test"),
		N_("Dubluri"),
		N_("Canale care nu mai există"),
		N_("Buchete goale"),
		N_("Buchete găsite pe disc, care nu sunt în listă"),
		N_("Copii de siguranță"),
		N_("Importă o listă (arhivă zip sau tar)"),
		N_("Importă fluxuri (m3u)"),
		N_("Descarcă lista (zip)"),
		N_("Descarcă lista (tar.gz)"),
		N_("Ajutor"),
		N_("Închide editorul"),
		N_("Înapoi la editor"),
		N_("Renunță"),
		N_("Gata"),
		N_("Da"),
		N_("Nu"),
		N_("Bine"),
		N_("Numele"),
		N_("Adresa fluxului"),
		N_("Poziția (numărul rândului)"),
		N_("Anulează:"),
		N_("Schimbări nesalvate:"),
		N_("Rânduri alese:"),
		N_("Canale:"),
		N_("în buchete:"),
		N_("nu mai există"),
		N_("ascuns"),
		N_("blocat"),
		N_("Buchetul e gol. Adaugă canale din „Adaugă canale”."),
		N_("Nu am găsit niciun canal."),
		N_("Se salvează lista și se face copia de siguranță..."),
		N_("Salvat. Copia de siguranță e făcută, iar lista de pe televizor e la zi."),
		N_("Salvat. Lista din memorie nu s-a putut verifica."),
		N_("Salvat, dar lista din memorie diferă de cea scrisă. Repornește interfața."),
		N_("Lista e cea din copia aleasă. Copia de dinainte e păstrată."),
		N_("Se pune înapoi copia..."),
		N_("Întoarce la această copie"),
		N_("Nu e nicio copie de siguranță încă. Prima se face la prima salvare."),
		N_("Ștergi canalele alese din acest buchet? Rămân în lista receptorului."),
		N_("Ștergi canalele alese din receptor? Dispar și din toate buchetele. Poți anula până la salvare."),
		N_("Ștergi tot buchetul? Canalele lui rămân în lista receptorului."),
		N_("Lista de acum se înlocuiește cu cea din copie. Înainte se face o copie a listei de acum."),
		N_("Ai schimbări nesalvate. Dacă pleci acum, se pierd."),
		N_("Lista e deschisă în altă parte. Dacă o preiei, schimbările nesalvate de acolo se pierd."),
		N_("Unde le muți?"),
		N_("Unde le copiezi?"),
		N_("Sortează după"),
		N_("Nume"),
		N_("Satelit și frecvență"),
		N_("Furnizor"),
		N_("Frecvență"),
		N_("În ordine inversă"),
		N_("Marcajele rămân pe loc: se sortează fiecare grupă de sub un marcaj."),
		N_("„Redenumește” schimbă numele numai în acest buchet. „Redenumește peste tot” îl schimbă în lista receptorului."),
		N_("Bifează tot"),
		N_("Debifează tot"),
		N_("Se caută..."),
		N_("Nu am găsit nimic aici."),
		N_("imagine"),
		N_("sunet"),
		N_("nu se știe"),
		N_("Repară cele bifate"),
		N_("Șterge rândurile în plus bifate"),
		N_("Șterge din receptor cele bifate"),
		N_("se leagă la:"),
		N_("se scoate din buchet"),
		N_("Ce faci cu lista din arhivă?"),
		N_("Înlocuiește lista de acum"),
		N_("Adaugă numai ce lipsește"),
		N_("Buchetele din arhivă (debifează ce nu vrei)"),
		N_("canale și buchete în arhivă:"),
		N_("Un buchet, cu marcaje pe grupe"),
		N_("Câte un buchet pe fiecare grupă"),
		N_("Bifează rândurile, apoi alege ce faci cu butoanele de jos. Mânerul ≡ mută rândul trăgându-l. „Anulează” întoarce ultima schimbare. Nimic nu se scrie în receptor până nu apeși „Salvează”; înainte de fiecare salvare se face o copie de siguranță."),
		N_("Pe calculator: săgețile aleg rândul, Shift + săgeți alege mai multe, Ctrl + săgeți mută, Spațiu bifează, Delete șterge, Ctrl+C / Ctrl+X / Ctrl+V copiază, taie și lipește, Ctrl+Z / Ctrl+Y anulează și reface, Ctrl+A alege tot, Ctrl+S salvează, F2 redenumește."),
		N_("Lipit."),
		N_("Copiate. Alege locul și apasă Ctrl+V."),
		N_("Editorul nu mai e deschis în această pagină."),
		N_("Deschide din nou"),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Erau deja în buchet."),
		N_("Deschide întâi un buchet, apoi adaugă canalele."),
		N_("Trage ca să muți"),
		N_("Acțiunile rândului"),
		N_("Am găsit în listă:"),
		N_("Vezi"),
		N_("Pune în listă"),
		N_("Filtrele bazei de canale"),
		N_("În aceeași grupă opțiunile bifate se adună cu «sau», între grupe cu «și». Numărul arată câte canale au opțiunea."),
		N_("Șterge filtrele"),
		N_("Se citesc filtrele..."),
		N_("Felul listei"),
		N_("Ce vezi"),
		N_("De unde"),
		N_("Caută după nume, furnizor, SID sau frecvență"),
		N_("Filtre"),
		N_("Canalele receptorului"),
		N_("Rândurile buchetului"),
		N_("Fără siglă"),
		N_("Arată buchetul"),
		N_("Ascunde buchetul"),
		N_("Scoate din toate buchetele"),
		N_("Le scoți din toate buchetele? Rămân în lista receptorului."),
		N_("Pornește pe televizor"),
		N_("Pornit pe televizor."),
		N_("Șterge de pe disc"),
		N_("Fișierul buchetului se șterge la salvare. Poți anula până atunci."),
		N_("Pe transpondere"),
		N_("Toate canalele satelitului"),
		N_("Fă un buchet din acest transponder"),
		N_("Șterge transponderul"),
		N_("Ștergi transponderul din receptor, cu toate canalele lui? Dispar și din buchete. Poți anula până la salvare."),
		N_("Fă câte un buchet din fiecare ales"),
		N_("Transpondere fără canale"),
		N_("Șterge transponderele bifate"),
		N_("Transpondere:"),
		N_("Le ștergi din lista receptorului? Nu au niciun canal. Poți anula până la salvare."),
		N_("Ce s-a schimbat de la ultima salvare"),
		N_("Nimic schimbat de la ultima salvare."),
		N_("Canale noi:"),
		N_("Canale șterse:"),
		N_("Canale schimbate:"),
		N_("Buchete schimbate:"),
		N_("Buchete noi:"),
		N_("Buchete șterse:"),
		N_("Lista buchetelor s-a schimbat (ordinea sau buchetele ascunse)."),
		N_("Blocările s-au schimbat."),
		N_("Compară cu lista de acum"),
		N_("Buchete"),
		N_("Unește ca alternative (același canal din alte locuri)"),
		N_("Desface alternativele"),
		N_("Mută satelitul pe altă poziție..."),
		N_("Copiază satelitul pe altă poziție..."),
		N_("HD în nume, tip SD"),
		N_("Noi"),
		N_("Blocate"),
		N_("nou"),
		N_("internet"),
		N_("Detalii"),
		N_("Scoate dintr-un buchet..."),
		N_("Din ce buchet îl scoți?"),
		N_("Pune siglă..."),
		N_("Copiază sigla de la alt canal..."),
		N_("Șterge sigla"),
		N_("Sigla e pusă."),
		N_("Alege o imagine (PNG, JPG): se micșorează la 220 x 132 și se pune ca siglă."),
		N_("Scoate semnul „nou”"),
		N_("Editează fluxul"),
		N_("Tipul fluxului"),
		N_("Numerele DVB ale fluxului (pentru siglă): SID, TSID, ONID, namespace (hex)"),
		N_("Aranjează după alt buchet..."),
		N_("Scoate marcajele din buchet"),
		N_("Descarcă tabelul (CSV)"),
		N_("Lipește o listă de nume..."),
		N_("Câte un nume de canal pe rând. Cele găsite se adaugă în buchet, în ordinea din listă."),
		N_("Găsite / negăsite:"),
		N_("Satelit, apoi nume"),
		N_("Furnizor, apoi nume"),
		N_("Sortează buchetele alese"),
		N_("Șterge din receptor"),
		N_("Păstrează numai cei bifați"),
		N_("Toate canalele și transponderele sateliților bifați se șterg din receptor și din buchete. Poți anula până la salvare."),
		N_("Se șterg din receptor toate canalele celorlalți sateliți (și din buchete). Poți anula până la salvare."),
		N_("Sateliți:"),
		N_("Verifică lista"),
		N_("Curățenie"),
		N_("Arată toate canalele ascunse"),
		N_("Deblochează toate canalele"),
		N_("Scoate semnul „nou” de pe toate canalele"),
		N_("Fluxuri care nu răspund"),
		N_("Sigle"),
		N_("Sigle nefolosite"),
		N_("Redenumește siglele după referință"),
		N_("Redenumește siglele după nume"),
		N_("Înlocuiește în nume..."),
		N_("Caută"),
		N_("Înlocuiește cu"),
		N_("Și în numele buchetelor"),
		N_("Se schimbă:"),
		N_("Înlocuiește"),
		N_("Mărimea literelor"),
		N_("Mai mari"),
		N_("Mai mici"),
		N_("Mod avansat: pornit"),
		N_("Mod avansat: oprit"),
		N_("Modul avansat arată și editarea transponderelor, a fișierului satellites.xml și a detaliilor canalelor. Greșelile de acolo pot opri canalele."),
		N_("Sateliți și transpondere (satellites.xml)"),
		N_("Satelit nou"),
		N_("Salvează satellites.xml"),
		N_("Renunță la schimbări"),
		N_("Schimbările se scriu în satellites.xml numai la „Salvează satellites.xml”, cu o copie înainte. Nu intră în „Anulează”."),
		N_("satellites.xml e salvat și receptorul îl folosește."),
		N_("satellites.xml e salvat; se vede după repornirea interfeței."),
		N_("Transpondere"),
		N_("Transponder nou"),
		N_("Editează"),
		N_("Poziția (de pildă 19.2E sau 30W)"),
		N_("Editează transponderul"),
		N_("Transponder nou în lista de canale"),
		N_("Transponderul nou n-are canale: o căutare pe el le aduce."),
		N_("Frecvența (MHz)"),
		N_("Rata de simbol (kS/s)"),
		N_("Polarizarea"),
		N_("Sistemul"),
		N_("Modulația"),
		N_("Salvează"),
		N_("Furnizorul"),
		N_("Steagurile"),
		N_("PID-uri ținute minte (cod:valoare hex)"),
		N_("Ascuns în listă"),
		N_("Păstrează numele la scanare"),
		N_("Nou găsit"),
		N_("Fără SDT"),
		N_("Fără DVB"),
		N_("Buchet nou din cele bifate"),
		N_("Adu înapoi cele bifate"),
		N_("Șterge marcajele bifate"),
		N_("Scoate din buchete cele bifate"),
		N_("Șterge siglele bifate"),
		N_("Vezi ce se schimbă"),
		N_("Înapoi la import"),
		N_("Descarcă"),
		N_("Sfat: bifează rândurile, apoi folosește butoanele de jos. Nimic nu se scrie în receptor până la „Salvează”."),
		N_("Toate"),
		N_("Satelit"),
		N_("Internet"),
		N_("Referința"),
		N_("În buchetele"),
		N_("Namespace"),
		N_("Tip"),
		N_("Auto"),
		N_("Roll-off"),
		N_("Pilot"),
		N_("Oprit"),
		N_("Pornit"),
		N_("MIS (is_id)"),
		N_("Codul PLS"),
		N_("Modul PLS"),
		N_("Root"),
		N_("Gold"),
		N_("Combo"),
	),
	"js": (
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
