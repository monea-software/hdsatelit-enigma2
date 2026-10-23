# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# playlisturi_web.py: pagina /playlisturi a interfetei web: liste de canale gata facute pentru playerele din casa (VLC,
# Kodi, Emby, Jellyfin, televizoare cu aplicatii IPTV), pe satelit, pe furnizor, dupa caracteristici (4K, HD, HEVC,
# sunetul si subtitrarea in limba receptorului, teletext, HbbTV, 5.1, necriptate), listele de pe televizor si radioul.
# Fiecare categorie se descarca ca fisier M3U sau devine sursa unui aparat din casa (adresa fixa, aparate_web.py).
# Legata prin aspect_web.MODULE (plugin.py nu se schimba); in /canale un buton duce aici.
#
# Rute (poarta comuna a HdsJsonResource; ce face o cheie cere POST, cookie, aceeasi origine si antetul CSRF):
#   GET  /api/playlisturi?grupa=<satelit>   categoriile cu numarul de canale (grupa = un satelit din "Toate canalele":
#                                           furnizorii, caracteristicile si radioul se numara numai pe el)
#   POST /api/playlisturi-m3u               fisierul M3U al unei categorii: sursa=grupa|buchet|selectie|radio, id=,
#                                           filtre= (JSON {grup: [valori]}), furnizor=, grupa=, eticheta=
#   GET  /playlisturi                       pagina
#
# O SINGURA LOGICA: categoriile se numara pe aceleasi liste ca /canale si /cautare (canale_web: "Toate canalele",
# grupele pe sateliti, indexul cautarii cu trasaturile canalelor, Index.conditii), iar continutul lor vine din acelasi
# loc ca playlistul unui aparat (aparate_web.gen_lista_aparat, sursele "grupa", "buchet" si "selectie"): numarul din
# pagina, fisierul si adresa fixa au aceleasi canale. Se numara numai canalele DVB (cele pe care le poate transmite
# receptorul; fluxurile de internet si releele locale nu intra). Radioul nu se da aparatelor (playlistul unui aparat are
# numai canale TV), deci are numai descarcarea.
#
# FISIERUL DESCARCAT: o cheie de lista (acces_extern, DURATA_LISTA_S, cel mult MAX_CANALE canale, numai reteaua de acasa,
# revocabila din pagina TV in browser), fara jetonul web; numele canalului, numarul de pe telecomanda (la liste),
# group-title (satelitul sau lista). O categorie mai mare se taie la MAX_CANALE, cu un comentariu in fisier si cu nota in
# pagina. Adresa fixa a unui aparat nu expira (aparate_web.py).
#
# FIRUL: totul pe firul enigma2, pe felii (canale_web.PeBucati); numaratoarea se tine in memorie cat aceeasi lista si
# acelasi index (VIATA_REZUMAT_S). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau furnizorul
# canale_web (C), aparate_web (AW), acces_extern (A) si HdsTransmisie (H).

import html
import json
import time

VIATA_REZUMAT_S = 120
TERMEN_S = 90
MAX_FURNIZORI = 400
LIMBA = object()          # locul limbii receptorului in filtrele caracteristicilor


def N_(text):
	"""marcheaza textul pentru xgettext (po/Makefile.am --keyword=N_); traducerea se face la folosire, cu _t"""
	return text


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


# (id, eticheta, filtrele indexului): aceleasi grupe si valori ca filtrele din /canale si /cautare (HdsIndexCanale)
CARACTERISTICI = (
	("4k", N_("4K (UHD)"), {"rez": ["4k"]}),
	("hd", N_("HD (720p și 1080)"), {"rez": ["720", "1080"]}),
	("sd", N_("SD"), {"rez": ["sd"]}),
	("h265", N_("H.265 (HEVC)"), {"cod": ["h265"]}),
	("h264", N_("H.264"), {"cod": ["h264"]}),
	("mpeg2", N_("MPEG-2"), {"cod": ["mpeg2"]}),
	("sunet", N_("Sunet: %s"), {"lsunet": [LIMBA]}),
	("sub", N_("Subtitrare: %s"), {"lsub": [LIMBA]}),
	("subdvb", N_("Subtitrări DVB"), {"are": ["subdvb"]}),
	("ttx", N_("Teletext"), {"are": ["ttx"]}),
	("hbbtv", N_("HbbTV"), {"are": ["hbbtv"]}),
	("multi", N_("Sunet 5.1 (multicanal)"), {"msunet": ["multi"]}),
	("fta", N_("Necriptate (FTA)"), {"acces": ["fta"]}),
)

TEXTE = {
	"titlu": N_("Playlisturi"),
	"intro": N_("Liste de canale gata făcute pentru VLC, Kodi, Emby sau alt player din casă. Descarci fișierul M3U sau dai unui aparat o adresă fixă, care nu expiră."),
	"satelitul": N_("Satelitul"),
	"toate_pozitiile": N_("Toate pozițiile"),
	"nota_satelit": N_("Furnizorii, caracteristicile și radioul se numără pe satelitul ales."),
	"sateliti": N_("Pe sateliți"),
	"caracteristici": N_("După caracteristici"),
	"furnizori": N_("Pe furnizori"),
	"cauta_furnizor": N_("Caută furnizorul"),
	"arata_toti": N_("Arată toți furnizorii (%s)"),
	"liste": N_("Liste de pe televizor"),
	"radio": N_("Radio"),
	"radio_toate": N_("Toate posturile de radio"),
	"canale": N_("%s canale"),
	"posturi": N_("%s posturi"),
	"descarca": N_("Descarcă M3U"),
	"adresa_fixa": N_("Adresă fixă"),
	"se_citeste": N_("Se citește..."),
	"se_face": N_("Se face fișierul..."),
	"descarcat": N_("Fișierul %s s-a descărcat. Deschide-l într-un player din casă."),
	"taiat": N_("Fișierul are primele %s canale din %s."),
	"nimic": N_("Nimic de arătat aici."),
	"niciun_furnizor": N_("Niciun furnizor nu se potrivește."),
	"nota_jos": N_("Fișierul descărcat are cel mult %s canale, iar adresele din el merg 30 de zile, numai în rețeaua de acasă. Adresa fixă nu expiră; aparatele se văd și se revocă în TV în browser, la Aparate din casă."),
	"alta_combinatie": N_("Altă combinație de filtre: Căutare canale"),
	"nu_raspunde": N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
}


def texte():
	"""{cheie: textul tradus in limba interfetei}"""
	return dict((k, _t(v)) for k, v in TEXTE.items())


def _c(C=None):
	if C is not None:
		return C
	from . import canale_web
	return canale_web


def _aw(AW=None):
	if AW is not None:
		return AW
	from . import aparate_web
	return aparate_web


def _a(A=None):
	if A is not None:
		return A
	from . import acces_extern
	return acces_extern


def _h(H=None):
	if H is not None:
		return H
	from Components import HdsTransmisie
	return HdsTransmisie


def _jurnal(text):
	print("[HdsWebControl] playlisturi: %s" % text)


# ---------------------------------------------------------------- numaratoarea

def filtreCaracteristica(filtre, limba):
	"""Filtrele unei caracteristici cu limba receptorului pusa in locul lui LIMBA, ca text (sursa "selectie")."""
	return dict((g, [limba if v is LIMBA else str(v) for v in valori]) for g, valori in filtre.items())


def numeLimba(index, cod):
	"""Numele limbii `cod` cum il arata filtrele (optiunile indexului), altfel codul cu litere mari."""
	for g in ("lsunet", "lsub"):
		for v, eticheta, _n in (getattr(index, "optiuni", None) or {}).get(g, ()):
			if v == cod and eticheta:
				return eticheta
	return (cod or "").upper()


_MEM = {"cheie": None, "ora": 0.0, "rez": None}


def uita():
	_MEM.update(cheie=None, ora=0.0, rez=None)


def _unice(randuri, C, H, grupa=None):
	"""Canalele DVB ale randurilor (fiecare o data), eventual numai cele din grupa `grupa`; generator."""
	vazute = set()
	rez = []
	for j, r in enumerate(randuri):
		if j % C.UNITATE == C.UNITATE - 1:
			yield
		c = r.canal
		if c is None or r.marcaj or id(c) in vazute:
			continue
		vazute.add(id(c))
		if H.refCurata(c.ref) is None:
			continue
		if grupa and C.cheie_grupa(c) != grupa:
			continue
		rez.append(c)
	return rez


def gen_rezumat(argumente_, F, C=None, AW=None, A=None, H=None):
	"""Generator (pe felii): GET /api/playlisturi -> (cod, raspuns)."""
	C, AW, A, H = _c(C), _aw(AW), _a(A), _h(H)
	X = F.X
	grupa = (argumente_ or {}).get("grupa") or ""
	if grupa and not AW._RE_GRUPA.match(grupa):
		grupa = ""
	lista = yield from C.gen_lista(F, "tv", C.TOATE)
	if lista is None:
		return 500, {"result": False, "message": _t("Eroare pe receptor.")}
	index = lista.index
	cheie = (id(lista), getattr(index, "masurari_marcaj", (0, 0))[1], getattr(index, "piste_aplicate", None), grupa,
		_t(TEXTE["titlu"]))
	if _MEM["cheie"] == cheie and time.monotonic() - _MEM["ora"] < VIATA_REZUMAT_S:
		return 200, _MEM["rez"]
	grupe = yield from C.gen_grupe(lista, X)
	sateliti = []
	nume_grupe = {}
	for k, nume, randuri in grupe:
		nume_grupe[k] = nume
		canale = yield from _unice(randuri, C, H)
		if canale:
			sateliti.append({"id": k, "nume": nume, "tv": len(canale)})
	limba = getattr(index, "limba_receptor", None) or "ron"
	car = []
	for cid, eticheta, filtre in CARACTERISTICI:
		f = filtreCaracteristica(filtre, limba)
		text = _t(eticheta)
		if "%s" in text:
			text = text % numeLimba(index, limba)
		car.append({"id": cid, "nume": text, "filtre": f, "tv": 0, "cond": AW.conditiiSelectie(index, f)})
	canale = yield from _unice(lista.randuri, C, H, grupa)
	furnizori = {}
	for j, c in enumerate(canale):
		if j % C.UNITATE == C.UNITATE - 1:
			yield
		for x in car:
			if x["cond"] is not None and all(index.masca(c, i, fel) & m for i, m, fel in x["cond"]):
				x["tv"] += 1
		f = AW.numeFurnizor(c)
		if f:
			d = furnizori.get(f)
			if d is None:
				d = furnizori[f] = {"tv": 0, "grupe": set()}
			d["tv"] += 1
			d["grupe"].add(C.cheie_grupa(c))
	lista_radio = yield from C.gen_lista(F, "radio", C.TOATE)
	radio = (yield from _unice(lista_radio.randuri, C, H, grupa)) if lista_radio is not None else []
	buchete = yield from C.gen_buchete(F, "tv")
	liste = [{"id": b["id"], "nume": b["nume"], "tv": b["numar"]} for b in buchete if b.get("numar")]
	ordine = lambda k: C.ordine_grupa(k, X)
	furn = sorted(furnizori.items(), key=lambda kv: (-kv[1]["tv"], kv[0].casefold()))[:MAX_FURNIZORI]
	rez = {
		"result": True,
		"grupa": grupa,
		"sateliti": sateliti,
		"caracteristici": [dict((k, v) for k, v in x.items() if k != "cond") for x in car],
		"furnizori": [{"id": f, "nume": f, "tv": d["tv"], "unde": ", ".join(nume_grupe.get(k, k) for k in
			sorted(d["grupe"], key=ordine))} for f, d in furn],
		"furnizori_total": len(furnizori),
		"liste": liste,
		"radio": len(radio),
		"max_fisier": A.MAX_CANALE,
		"max_aparat": AW.MAX_CANALE_APARAT,
	}
	_MEM.update(cheie=cheie, ora=time.monotonic(), rez=rez)
	return 200, rez


# ---------------------------------------------------------------- fisierul M3U

def campuriCerere(request):
	"""Campurile POST /api/playlisturi-m3u, luate direct din request.args, fiecare cu limita lui."""
	rez = {}
	for cheie, maxim in ((b"sursa", 16), (b"id", 128), (b"filtre", 8 * 1024), (b"furnizor", 300), (b"grupa", 32),
			(b"eticheta", 300)):
		v = (getattr(request, "args", None) or {}).get(cheie)
		if v:
			x = v[0]
			rez[cheie.decode("ascii")] = (x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x))[:maxim]
	return rez


def textM3u(gazda, cheie_text, canale, total, A):
	"""#EXTM3U (cu un comentariu cand lista e taiata), apoi pentru fiecare canal #EXTINF (tvg-id, tvg-name, tvg-chno,
	group-title) si adresa fluxului. `canale` = [(ref curata, nume, grup, numar)]."""
	randuri = ["#EXTM3U"]
	if total > len(canale):
		randuri.append("# HD Satelit: " + _t(TEXTE["taiat"]) % (len(canale), total))
	for ref, nume, grup, numar in canale:
		cod = A.codCanal(ref)
		nume = A._curataText(nume) or cod
		semne = ['tvg-id="%s"' % cod, 'tvg-name="%s"' % nume]
		if numar:
			semne.append('tvg-chno="%d"' % int(numar))
		grup = A._curataText((grup or "").replace(",", "."), 80)
		if grup:
			semne.append('group-title="%s"' % grup)
		randuri.append("#EXTINF:-1 %s,%s" % (" ".join(semne), nume))
		randuri.append(A.adresaFlux(gazda, cheie_text, ref))
	return "\n".join(randuri) + "\n"


def gen_fisier(campuri, cine, browser_nume, gazda, F, C=None, AW=None, A=None, H=None):
	"""Generator (pe felii): POST /api/playlisturi-m3u -> (cod, (text, numele fisierului, canale, total)) sau (cod, eroare)."""
	C, AW, A, H = _c(C), _aw(AW), _a(A), _h(H)
	if not A.gazdaBuna(gazda):
		return 400, {"result": False, "message": _t("Adresa receptorului din cerere nu e bună.")}
	eticheta = AW.curataEticheta(campuri.get("eticheta"))
	if campuri.get("sursa") == "radio":
		grupa = campuri.get("grupa") or ""
		if grupa and not AW._RE_GRUPA.match(grupa):
			return 400, {"result": False, "message": _t("Lista aleasă nu există pe receptor.")}
		lista = yield from C.gen_lista(F, "radio", C.TOATE)
		radio = (yield from _unice(lista.randuri, C, H, grupa)) if lista is not None else []
		X = F.X
		nume_grupe = {}
		canale = []
		# pe grupe, in ordinea listei de pe televizor (cablul, terestrul, satelitii de la vest la est)
		for c in sorted(radio, key=lambda c: C.ordine_grupa(C.cheie_grupa(c), X)):
			k = C.cheie_grupa(c)
			if k not in nume_grupe:
				nume_grupe[k] = C.nume_grupa(k, c, X)
			canale.append((H.refCurata(c.ref), C.curat(c.nume_afisat() if hasattr(c, "nume_afisat") else c.nume) or "?",
				nume_grupe[k], None))
		eticheta = eticheta or _t(TEXTE["radio_toate"])
	else:
		sursa, motiv = AW.sursaDin(campuri, C)
		if sursa is None:
			return 400, {"result": False, "message": motiv}
		eticheta = eticheta or sursa.get("eticheta") or ""
		lista = yield from AW.gen_lista_aparat(sursa, F, C, H, A)
		canale = [(ref, nume, grup, numar) for ref, nume, grup, _s, numar in lista.canale]
	if not canale:
		return 400, {"result": False, "message": _t("Lista nu are niciun canal.")}
	total = len(canale)
	canale = canale[:A.MAX_CANALE]
	cheie_text, _cheie = A.magazin().creeaza("lista", [x[0] for x in canale], cine or "", browser_nume or "",
		eticheta or "playlist")
	text = textM3u(gazda, cheie_text, canale, total, A)
	_jurnal("fisier: %d canale din %d (%s)" % (len(canale), total, campuri.get("sursa") or "-"))
	return 200, (text, A.numeFisier(["hdsatelit", eticheta or "canale"]), len(canale), total)


# ---------------------------------------------------------------- rutele

def rute(baza, resource, M=None, C=None, AW=None, A=None, H=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py; probele de pe PC
	dau furnizorul canale_web (M) si modulele lor."""

	def _amanat():
		from twisted.web.server import NOT_DONE_YET
		return NOT_DONE_YET

	def _porneste(obiect, request, gen, gata):
		Cx = _c(C)
		Mx = Cx._m(M)
		if Cx._planificator(Mx).numar() >= Cx.MAX_LUCRARI:
			return obiect._eroare(request, _t("Receptorul are prea multe cereri în lucru. Încearcă din nou."), 503)
		lucru = Cx.PeBucati(gen(Mx), gata, Mx, termen_s=TERMEN_S)
		try:
			request.notifyFinish().addErrback(lucru.opreste)
		except Exception:
			pass
		lucru.porneste()
		return _amanat()

	def _trimite(obiect, request, cod, corp):
		try:
			request.write(obiect._raspunde(request, corp, cod))
			request.finish()
		except Exception as e:
			_jurnal("raspunsul nu a plecat (browser plecat?): %r" % (e,))

	class Rezumat(baza):
		"""GET /api/playlisturi: numai citire."""

		def render_GET(self, request):
			a = {}
			v = (getattr(request, "args", None) or {}).get(b"grupa")
			if v:
				a["grupa"] = (v[0].decode("ascii", "replace") if isinstance(v[0], bytes) else str(v[0]))[:16]
			return _porneste(self, request, lambda Mx: gen_rezumat(a, Mx, C, AW, A, H),
				lambda cod, corp: _trimite(self, request, cod, corp))

	class Fisier(baza):
		"""POST /api/playlisturi-m3u: fisierul (descarcat de pagina prin fetch); numai din browser, nu cu ?token=."""
		schimbaCeva = True

		def render_POST(self, request):
			from . import plugin as P
			if P.PARAM_JETON in request.args:
				return self._eroare(request, _t("Playlisturile se fac numai din pagina lor, cu browserul conectat."), 403)
			_secret, browser = P._sesiuneDinCerere(request)
			adresa = P._adresaClient(request) or ""
			if browser is None:
				return self._eroare(request, _t("Playlisturile se fac numai din pagina lor, cu browserul conectat."), 403)
			cine = "b:%s" % browser["id"] if browser.get("id") else "l:%s" % adresa
			nume = browser.get("nume") or adresa
			campuri = campuriCerere(request)
			gazda = P._antet(request, b"host") or ""

			def gata(cod, corp):
				try:
					if cod != 200:
						request.write(self._raspunde(request, corp, cod))
					else:
						text, fisier, _n, _total = corp
						date = text.encode("utf-8", "replace")
						request.setResponseCode(200)
						request.setHeader(b"content-type", b"audio/x-mpegurl; charset=utf-8")
						request.setHeader(b"cache-control", b"no-store")
						request.setHeader(b"x-content-type-options", b"nosniff")
						request.setHeader(b"content-disposition", ('attachment; filename="%s"' % fisier).encode("ascii"))
						request.setHeader(b"x-hds-canale", ("%d/%d" % (_n, _total)).encode("ascii"))
						request.write(date)
					request.finish()
				except Exception as e:
					_jurnal("fisierul nu a plecat (browser plecat?): %r" % (e,))
			return _porneste(self, request, lambda Mx: gen_fisier(campuri, cine, nume, gazda, Mx, C, AW, A, H), gata)

	class Pagina(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			from . import meniu_comun_web
			return meniu_comun_web.pagina(request, pagina_text)

	return {b"playlisturi": Rezumat(), b"playlisturi-m3u": Fisier()}, {b"playlisturi": Pagina()}


# ---------------------------------------------------------------- pagina

def _inlocuieste(sablon, valori):
	for k, v in valori.items():
		sablon = sablon.replace("__P_%s__" % k, html.escape(v, quote=True))
	return sablon


def texteJs():
	text = json.dumps(texte(), ensure_ascii=False)
	return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def pagina_text(stil, config_pagina, AW=None, mc=None):
	"""Pagina, cu fereastra aparatului (aparate_web.inPagina) si textele traduse in limba interfetei."""
	if mc is None:
		from . import meniu_comun_web as mc
	AW = _aw(AW)
	text = AW.inPagina(PAGINA).replace("__PLAYLISTURI_TEXTE__", texteJs())
	text = _inlocuieste(text, texte())
	return mc.sablon(text, stil, config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__P_titlu__</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
__APARATE_STIL__
  main{max-width:1100px;}
  h1{font-size:1.6rem;margin:0 0 6px;}
  .intro{font-size:1rem;color:var(--text-slab);line-height:1.5;margin:0 0 16px;max-width:820px;}
  h2.sectiune{font-size:1.1rem;font-weight:600;margin:22px 0 10px;}
  .bara-sat{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;}
  .bara-sat label{display:flex;align-items:center;gap:10px;font-size:.92rem;}
  .bara-sat select{min-width:240px;}
  .bara-sat .nota{margin:0 0 0 auto;}
  .card.lista-card{padding:0 16px;}
  .randuri{list-style:none;margin:0;padding:0;}
  .randuri li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 16px;align-items:center;padding:14px 0;border-bottom:1px solid var(--bordura);}
  .randuri li:last-child{border-bottom:0;}
  .randuri .cap{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;min-width:0;}
  .randuri .nume{font-weight:600;font-size:1rem;overflow-wrap:anywhere;}
  .randuri .unde{display:block;font-size:.82rem;color:var(--text-slab);margin-top:3px;}
  .numar{display:inline-block;font-size:.72rem;font-weight:600;letter-spacing:.03em;padding:2px 9px;border-radius:999px;border:1px solid var(--bordura);color:var(--text-slab);background:rgba(255,255,255,.04);white-space:nowrap;font-variant-numeric:tabular-nums;}
  .butoane-rand{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;}
  .butoane-rand button{min-height:44px;}
  .butoane-rand button:not(.principal){background:transparent;}
  li.gol,.tigla.gol{opacity:.45;}
  .tigle{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;}
  .tigla{border:1px solid var(--bordura);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:6px;background:var(--panou);}
  .tigla .nume{font-weight:600;font-size:.95rem;}
  .tigla .mare{font-size:1.9rem;font-weight:700;line-height:1.15;font-variant-numeric:tabular-nums;}
  .tigla .unitate{font-size:.8rem;font-weight:400;color:var(--text-slab);margin-left:6px;}
  .tigla .butoane-rand{justify-content:flex-start;margin-top:8px;padding-top:10px;border-top:1px solid var(--bordura);}
  .tigla .butoane-rand button{flex:1 1 auto;padding:8px 10px;font-size:.86rem;}
  .cauta-furnizor{width:100%;margin:14px 0 4px;box-sizing:border-box;}
  .mai-multi{display:flex;justify-content:center;padding:12px 0;border-top:1px solid var(--bordura);}
  .jos{display:flex;flex-wrap:wrap;align-items:center;gap:12px 16px;margin-top:22px;}
  .jos .nota{flex:1 1 380px;margin:0;}
  .jos a{display:inline-flex;align-items:center;min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);color:var(--text);text-decoration:none;font-size:.88rem;}
  .dialog-live{position:fixed;inset:0;z-index:1000;background:rgba(5,8,16,.78);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 12px;}
  .dialog-cutie{width:100%;box-sizing:border-box;background:var(--panou);border:1px solid var(--bordura);border-radius:12px;box-shadow:0 16px 40px -8px rgba(0,0,0,.75);padding:12px 14px 14px;}
  .dialog-antet{display:flex;align-items:center;gap:12px;margin:0 0 10px;}
  .dialog-antet h2{flex:1;font-size:1.05rem;margin:0;min-width:0;overflow-wrap:anywhere;}
  .dialog-antet button{min-width:44px;min-height:44px;font-size:1.2rem;}
  @media (max-width:640px){
    .randuri li{grid-template-columns:minmax(0,1fr);}
    .randuri li .butoane-rand{justify-content:flex-start;}
    .randuri li .butoane-rand button{flex:1 1 0;}
    .bara-sat select{min-width:0;width:100%;}
    .bara-sat label{flex:1 1 100%;flex-wrap:wrap;}
    .bara-sat .nota{margin:0;}
    .jos a{flex:1 1 100%;justify-content:center;}
  }
</style>
</head>
<body>
<main>
<h1>__P_titlu__</h1>
<p class="intro">__P_intro__</p>
<section class="card bara-sat">
  <label for="satelit">__P_satelitul__ <select id="satelit"><option value="">__P_toate_pozitiile__</option></select></label>
  <p class="nota">__P_nota_satelit__</p>
</section>
<p class="mesaj" id="mesaj" role="status"></p>
<h2 class="sectiune">__P_sateliti__</h2>
<section class="card lista-card"><ul class="randuri" id="sateliti"><li class="gol">__P_se_citeste__</li></ul></section>
<h2 class="sectiune">__P_caracteristici__</h2>
<div class="tigle" id="caracteristici"></div>
<h2 class="sectiune">__P_furnizori__</h2>
<section class="card lista-card">
  <input type="search" class="cauta-furnizor" id="cautaFurnizor" placeholder="__P_cauta_furnizor__" aria-label="__P_cauta_furnizor__" autocomplete="off">
  <ul class="randuri" id="furnizori"></ul>
  <div class="mai-multi ascuns" id="randToti"><button type="button" id="totiFurnizorii"></button></div>
</section>
<h2 class="sectiune">__P_liste__</h2>
<section class="card lista-card"><ul class="randuri" id="liste"></ul></section>
<h2 class="sectiune">__P_radio__</h2>
<section class="card lista-card"><ul class="randuri" id="radio"></ul></section>
<section class="card jos">
  <p class="nota" id="notaJos"></p>
  <a href="/cautare">__P_alta_combinatie__</a>
</section>
</main>
__APARATE_DIALOG__
<script>
__SCRIPT_COMUN__
var TP = __PLAYLISTURI_TEXTE__;
var TA = __APARATE_TEXTE__, MAX_CANALE_APARAT = __APARATE_MAX__;
__APARATE_JS__
var D = null, TOTI = false, CITESTE = 0;
function scrie(e, t){ e.textContent = (t === null || t === undefined) ? "" : String(t); }
function el(tag, clasa, text){ var e = document.createElement(tag); if(clasa){ e.className = clasa; } if(text !== undefined){ scrie(e, text); } return e; }
function numar(n){ return Number(n).toLocaleString(document.documentElement.lang || "ro"); }
function grupaAleasa(){ return $("satelit").value; }
function numeGrupa(){ var s = $("satelit"); return s.value ? s.options[s.selectedIndex].textContent : ""; }
function eticheta(parti){ return parti.filter(Boolean).join(", "); }
// descarcarea: POST, fisierul vine ca blob (numele din Content-Disposition), apoi o legatura de descarcare
function descarca(campuri, buton){
  var p = new URLSearchParams();
  Object.keys(campuri).forEach(function(k){ if(campuri[k] !== undefined && campuri[k] !== null && campuri[k] !== ""){ p.set(k, campuri[k]); } });
  buton.disabled = true; mesaj(TP.se_face);
  var optiuni = {method: "POST", cache: "no-store", credentials: "same-origin", headers: {"Content-Type": "application/x-www-form-urlencoded"}, body: p.toString()};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  fetch(adresa("/api/playlisturi-m3u"), optiuni).then(function(r){
    var tip = r.headers.get("content-type") || "";
    if(tip.indexOf("json") >= 0 || !r.ok){
      return r.json().catch(function(){ return {message: TP.nu_raspunde}; }).then(function(d){ throw new Error(d.message || TP.nu_raspunde); });
    }
    var cd = r.headers.get("content-disposition") || "", m = /filename="([^"]+)"/.exec(cd), fisier = m ? m[1] : "hdsatelit.m3u";
    var cate = (r.headers.get("x-hds-canale") || "").split("/");
    return r.blob().then(function(b){
      var u = URL.createObjectURL(b), a = document.createElement("a");
      a.href = u; a.download = fisier; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function(){ URL.revokeObjectURL(u); }, 30000);
      var text = TP.descarcat.replace("%s", fisier);
      if(cate.length === 2 && Number(cate[1]) > Number(cate[0])){ text += " " + TP.taiat.replace("%s", numar(cate[0])).replace("%s", numar(cate[1])); }
      mesaj(text);
    });
  }).catch(function(e){ mesaj(e.message || TP.nu_raspunde, true); }).then(function(){ buton.disabled = false; });
}
function butoane(rand, n, campuri, numeEticheta, faraAparat){
  var b = el("div", "butoane-rand");
  var d = el("button", "principal", TP.descarca); d.type = "button"; d.disabled = !n;
  d.addEventListener("click", function(){ descarca(Object.assign({eticheta: numeEticheta}, campuri), d); });
  b.appendChild(d);
  if(!faraAparat){
    var f = el("button", "", TP.adresa_fixa); f.type = "button"; f.disabled = !n;
    f.addEventListener("click", function(){
      aparatDeschide({eticheta: numeEticheta, numar: n, inapoi: f, campuri: function(){ return Object.assign({}, campuri); }});
    });
    b.appendChild(f);
  }
  rand.appendChild(b);
  return b;
}
function rand(lista, nume, unde, n, campuri, numeEticheta, textNumar, faraAparat){
  var li = el("li", n ? "" : "gol"), stanga = el("div"), cap = el("div", "cap");
  cap.appendChild(el("span", "nume", nume));
  cap.appendChild(el("span", "numar", (textNumar || TP.canale).replace("%s", numar(n))));
  stanga.appendChild(cap);
  if(unde){ stanga.appendChild(el("span", "unde", unde)); }
  li.appendChild(stanga);
  butoane(li, n, campuri, numeEticheta, faraAparat);
  lista.appendChild(li);
}
function gol(lista){ if(!lista.children.length){ lista.appendChild(el("li", "gol", TP.nimic)); } }
function sursaSelectie(filtre, furnizor){ return {sursa: "selectie", filtre: JSON.stringify(filtre || {}), furnizor: furnizor || "", grupa: grupaAleasa()}; }
function arataFurnizori(){
  var u = $("furnizori"); u.textContent = "";
  var q = $("cautaFurnizor").value.trim().toLowerCase(), toti = D.furnizori.filter(function(f){ return !q || f.nume.toLowerCase().indexOf(q) >= 0; });
  var arat = (TOTI || q) ? toti : toti.slice(0, 30);
  arat.forEach(function(f){ rand(u, f.nume, f.unde, f.tv, sursaSelectie({}, f.id), eticheta([f.nume, numeGrupa()])); });
  if(!arat.length){ u.appendChild(el("li", "gol", q ? TP.niciun_furnizor : TP.nimic)); }
  $("randToti").classList.toggle("ascuns", TOTI || !!q || toti.length <= 30);
  scrie($("totiFurnizorii"), TP.arata_toti.replace("%s", numar(D.furnizori_total)));
}
function arata(){
  var s = $("satelit"), ales = D.grupa;
  if(s.options.length <= 1){
    D.sateliti.forEach(function(g){ var o = el("option", "", g.nume); o.value = g.id; s.appendChild(o); });
    s.value = ales;
  }
  var u = $("sateliti"); u.textContent = "";
  D.sateliti.forEach(function(g){ rand(u, g.nume, "", g.tv, {sursa: "grupa", id: g.id}, g.nume); });
  gol(u);
  var c = $("caracteristici"); c.textContent = "";
  D.caracteristici.forEach(function(x){
    var t = el("div", "tigla" + (x.tv ? "" : " gol"));
    t.appendChild(el("span", "nume", x.nume));
    var mare = el("span", "mare", numar(x.tv));
    mare.appendChild(el("span", "unitate", TP.canale.replace("%s", "").trim()));
    t.appendChild(mare);
    butoane(t, x.tv, sursaSelectie(x.filtre, ""), eticheta([x.nume, numeGrupa()]));
    c.appendChild(t);
  });
  arataFurnizori();
  var l = $("liste"); l.textContent = "";
  D.liste.forEach(function(b){ rand(l, b.nume, "", b.tv, {sursa: "buchet", id: b.id}, b.nume); });
  gol(l);
  var r = $("radio"); r.textContent = "";
  rand(r, TP.radio_toate, numeGrupa(), D.radio, {sursa: "radio", grupa: grupaAleasa()}, eticheta([TP.radio_toate, numeGrupa()]), TP.posturi, true);
  scrie($("notaJos"), TP.nota_jos.replace("%s", numar(D.max_fisier)));
}
function citeste(){
  var nr = ++CITESTE, g = grupaAleasa();
  return cerere("/api/playlisturi" + (g ? "?grupa=" + encodeURIComponent(g) : "")).then(function(d){
    if(nr !== CITESTE){ return; }
    if(!d.result){ mesaj(d.message || TP.nu_raspunde, true); return; }
    D = d; mesaj(""); arata();
  }).catch(nimicNuRaspunde);
}
$("satelit").addEventListener("change", function(){ mesaj(TP.se_citeste); citeste(); });
$("cautaFurnizor").addEventListener("input", function(){ if(D){ arataFurnizori(); } });
$("totiFurnizorii").addEventListener("click", function(){ TOTI = true; arataFurnizori(); });
citeste();
</script>
</body>
</html>
"""
