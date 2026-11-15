# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Pagina web „Filme și seriale” (/filme-seriale): perechea ecranului de pe televizor (Screens/HdsFilmeSeriale.py), regula din
24.09.2026. Aceeasi sursa (Components/HdsVod.py), aceleasi randuri (Continuă să vizionezi, Favorite, Adăugate recent, categoriile),
pagina filmului si a serialului, cautarea, favoritele, iar „Redă” porneste filmul pe televizor, de unde ai ramas.

Posterele trec prin receptor (/api/vod-poza, cu semnul pozei, nu cu adresa ei): browserul nu vede gazda furnizorului, iar
receptorul le micsoreaza o singura data, in acelasi cache ca ecranul.
API: GET /api/vod-surse; GET /api/vod?fel=categorii|rand|recente|detalii|cauta&id=&tip=&arg= (sau &cerere=<cheie>);
GET /api/vod-locale?id=&tip=; GET /api/vod-poza?s=&l=&h=&fel=; POST /api/vod-reda (id, cheie, de_la), POST /api/vod-favorit.
Serverele Emby / Jellyfin (Components/HdsVodServere): GET /api/vod-servere; POST /api/vod-server (fel=cauta: cautarea in retea;
fel=adauga: adresa, utilizator, parola; fel=scoate: id), apoi GET /api/vod-server?lucrare= pana e gata (reteaua merge pe un fir,
pagina si televizorul nu asteapta). Parola nu se intoarce niciodata in pagina.
"""
import json
import os
import re
import threading
import time
import uuid


def _(text):
	from .meniu_comun_web import _t
	return _t(text)


def N_(text):
	return text


def _V():
	from Components import HdsVod
	return HdsVod


def _P():
	from Components import HdsVodPoze
	return HdsVodPoze


def _Z():
	from Components import HdsVodPozitii
	return HdsVodPozitii


_SID = re.compile(r"^[0-9a-f]{8}$")
_CHEIE = re.compile(r"^[ves][0-9A-Za-z]{1,40}(\.[A-Za-z0-9]{1,5})?$")   # Xtream: numere; Emby: numere; Jellyfin: hex; disc: suma
_FELURI = ("categorii", "rand", "recente", "detalii", "cauta")


def _titluPublic(t, sid, Z, P):
	"""Un titlu fara adrese: poza devine semnul ei; se adauga progresul si favoritul."""
	t = dict(t)
	for camp in ("poza", "poster", "fundal"):
		if t.get(camp):
			t[camp] = P.semn(t[camp])
	cheie = t.get("cheie") or ""
	if cheie:
		k = Z.cheie(sid, cheie)
		t["progres"] = round(Z.progres(k), 3)
		t["pozitie"] = Z.pozitie(k)
	if t.get("sezoane"):
		t["sezoane"] = [dict(sz, episoade=[_titluPublic(e, sid, Z, P) for e in sz["episoade"]]) for sz in t["sezoane"]]
	return t


def raspunsPublic(rez, sid, Z=None, P=None):
	Z, P = Z or _Z(), P or _P()
	rez = dict(rez)
	if isinstance(rez.get("titluri"), list):
		rez["titluri"] = [_titluPublic(t, sid, Z, P) for t in rez["titluri"]]
	if isinstance(rez.get("detalii"), dict):
		d = _titluPublic(rez["detalii"], sid, Z, P)
		if d.get("tip") == "seriale":
			d["favorit"] = Z.favorit(Z.cheie(sid, "s" + d["id"]))
		elif d.get("cheie"):
			k = Z.cheie(sid, d["cheie"])
			d["favorit"] = Z.favorit(k)
			st = Z.stare(k)
			d["subtitrari"], d["audio_vazut"] = st.get("sub") or [], st.get("aud") or []
		rez["detalii"] = d
	if "message" in rez and rez["message"]:
		rez["message"] = _(rez["message"])
	return rez


def _pozitiiServer(rez, src):
	"""Serverele Emby/Jellyfin tin pozitia (vazut si pe alt aparat): pagina arata pozitia de acolo."""
	if src is None or not src.continuaPeServer:
		return rez
	for t in (rez.get("titluri") or []) + ([rez["detalii"]] if isinstance(rez.get("detalii"), dict) else []):
		for x in [t] + [e for sz in t.get("sezoane") or [] for e in sz.get("episoade") or []]:
			p = src.pozitieServer(x.get("cheie") or "") if x.get("cheie") else None
			if p is not None:
				x["pozitie"] = p
	return rez


def vod(arg, V=None, Z=None, P=None):
	V = V or _V()
	cerere = arg.get("cerere", "")
	sid = arg.get("id", "")
	if not _SID.match(sid):
		return {"result": False, "message": _(V.E_FARA_SURSA)}
	if not cerere:
		fel = arg.get("fel", "")
		if fel not in _FELURI:
			return {"result": False, "message": _(V.E_LIPSA)}
		cerere = V.cere(fel, sid, arg.get("tip", ""), arg.get("arg", ""))
		if not cerere:
			return {"result": False, "message": _(V.E_OCUPAT)}
	rez = V.rezultat(cerere)
	rez["cerere"] = cerere
	rez = raspunsPublic(rez, sid, Z, P)
	if not rez.get("lucreaza"):
		rez = _pozitiiServer(rez, V.sursa(sid))
	return rez


def locale(arg, V=None, Z=None, P=None):
	"""Randurile fara retea: Continuă să vizionezi si Favorite."""
	V, Z, P = V or _V(), Z or _Z(), P or _P()
	sid, tip = arg.get("id", ""), arg.get("tip", "filme")
	if not _SID.match(sid):
		return {"result": False, "message": _(V.E_FARA_SURSA)}

	def titlu(k, r):
		cheie = k.split("/", 1)[1]
		t = {"nume": r.get("nume") or cheie, "poza": P.semn(r["poza"]) if r.get("poza") else "", "tip": r.get("tip") or "filme"}
		if cheie.startswith("s"):
			t.update(id=cheie[1:], tip="seriale")
		elif r.get("serial"):
			t.update(id=r["serial"], tip="seriale", nume=r.get("serial_nume") or t["nume"], episod=cheie,
				sub=_("S%s E%s") % (r.get("sezon", "?"), r.get("numar", "?")))
		else:
			t.update(id=cheie[1:].split(".")[0], cheie=cheie, progres=round(Z.progres(k), 3), pozitie=Z.pozitie(k))
		return t
	src = V.sursa(sid)
	cont = [titlu(k, r) for k, r in Z.continua(sid) if (r.get("tip") or "filme") == tip]
	if src is not None and src.continuaPeServer:
		cont = []               # randul 'Continuă de unde ai rămas' vine de la server, cu categoriile
	fav = [titlu(k, r) for k, r in Z.favorite(sid) if (r.get("tip") or "filme") == tip]
	return {"result": True, "continua": cont, "favorite": fav, "recente": V.activ("recente")}


def reda(arg, V=None, Z=None, zap=None):
	"""Porneste pe televizor, in playerul de filme, de unde ai ramas (de_la=0: de la inceput)."""
	V, Z = V or _V(), Z or _Z()
	sid, cheie = arg.get("id", ""), arg.get("cheie", "")
	if not _SID.match(sid) or not _CHEIE.match(cheie) or cheie[0] == "s":
		return {"result": False, "message": _(V.E_LIPSA)}
	src = V.sursa(sid)
	if src is None:
		return {"result": False, "message": _(V.E_FARA_SURSA)}
	meta = {"nume": arg.get("nume", "")[:200] or cheie, "tip": "seriale" if cheie[0] == "e" else "filme"}
	for camp in ("serial", "serial_nume", "sezon", "numar"):
		if arg.get(camp):
			meta[camp] = arg[camp][:200]
	poza = _P().adresaSemn(arg.get("poza", ""))
	if poza:
		meta["poza"] = poza
	de_la = Z.pozitie(Z.cheie(sid, cheie)) if arg.get("de_la", "1") != "0" else 0
	if arg.get("de_la", "1") != "0" and src.continuaPeServer and src.pozitieServer(cheie) is not None:
		de_la = src.pozitieServer(cheie)
	(zap or _zapPlayer)(src, cheie, meta, de_la)
	return {"result": True, "message": _(N_("Pornește pe televizor.")) + ((" " + _(N_("Continuă de la %s.")) % _ora(de_la)) if de_la else "")}


def _ora(s):
	return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60) if s >= 3600 else "%d:%02d" % (s // 60, s % 60)


def _zapPlayer(src, cheie, meta, de_la):
	"""Pe firul enigma2 (cererile web vin pe el): deschide playerul de filme peste ce e pe ecran."""
	from Screens.HdsFilmeSeriale import reda as redaTv
	from . import meniu_comun_web as M
	redaTv(M.sesiune(), src, cheie, meta, de_la)


def favorit(arg, V=None, Z=None, P=None):
	V, Z, P = V or _V(), Z or _Z(), P or _P()
	sid, cheie = arg.get("id", ""), arg.get("cheie", "")
	if not _SID.match(sid) or not _CHEIE.match(cheie):
		return {"result": False, "message": _(V.E_LIPSA)}
	poza = P.adresaSemn(arg.get("poza", ""))
	acum = Z.comutaFavorit(Z.cheie(sid, cheie), {"nume": arg.get("nume", "")[:200], "poza": poza or "",
		"tip": "seriale" if cheie[0] == "s" else "filme"})
	return {"result": True, "favorit": acum, "message": _(N_("Adăugat la favorite.")) if acum else _(N_("Scos de la favorite."))}


def poza(arg, P=None):
	"""-> (octetii JPEG, None) sau (None, cod HTTP). 404 = inca nu e gata (pagina incearca din nou)."""
	P = P or _P()
	adresa = P.adresaSemn(arg.get("s", ""))
	if not adresa:
		return None, 410
	try:
		l, h = int(arg.get("l", "0")), int(arg.get("h", "0"))
	except ValueError:
		return None, 400
	fel = arg.get("fel", "poster")
	if fel not in ("poster", "lat", "fundal") or not (16 <= l <= 1280 and 16 <= h <= 720):
		return None, 400
	cale = P.cere(adresa, l, h, fel)
	if not cale:
		return None, 404
	with open(cale, "rb") as f:
		return f.read(2 * 1024 * 1024), None


# ------------------------------------------------------------------ serverele Emby / Jellyfin

def _S():
	from Components import HdsVodServere
	return HdsVodServere


_lucrariServer = {}
_lacatServer = threading.Lock()


def servere(arg=None, S=None):
	S = S or _S()
	return {"result": True, "servere": S.publice()}


def _inFundal(functie, *argumente):
	cheie = uuid.uuid4().hex[:16]
	with _lacatServer:
		for k in [k for k, v in _lucrariServer.items() if time.monotonic() - v["ora"] > 600]:
			del _lucrariServer[k]
		if len(_lucrariServer) >= 8:
			return ""
		_lucrariServer[cheie] = {"ora": time.monotonic(), "rez": None}

	def lucru():
		try:
			rez = functie(*argumente)
		except Exception as e:
			print("[HdsWebControl] server media: %s" % type(e).__name__)
			rez = {"result": False, "message": _(_S().E_SERVER)}
		with _lacatServer:
			if cheie in _lucrariServer:
				_lucrariServer[cheie]["rez"] = rez
	fir = threading.Thread(target=lucru, name="HdsWebVodServer")
	fir.daemon = True
	fir.start()
	return cheie


def server(arg, S=None, fundal=None):
	"""POST: fel=cauta (fel_server) | adauga (fel_server, adresa, utilizator, parola) | scoate (id). Cautarea si logarea pe un fir."""
	S = S or _S()
	fundal = fundal or _inFundal
	fel, fs = arg.get("fel", ""), arg.get("fel_server", "")
	if fel == "scoate":
		ok = S.scoate(arg.get("id", ""))
		return {"result": ok, "servere": S.publice()}
	if fs not in S.FELURI:
		return {"result": False, "message": _(S.E_ADRESA)}
	if fel == "cauta":
		cheie = fundal(lambda: {"result": True, "gasite": S.descopera(2.0, (fs,))})
	elif fel == "adauga":
		if not S.adresaBuna(arg.get("adresa", "")):
			return {"result": False, "message": _(S.E_ADRESA)}

		def adauga():
			ok, mesaj, sid = S.adauga(fs, arg.get("adresa", ""), arg.get("utilizator", ""), arg.get("parola", ""))
			return {"result": ok, "message": "" if ok else _(mesaj), "id": sid, "servere": S.publice()}
		cheie = fundal(adauga)
	else:
		return {"result": False, "message": _(_V().E_LIPSA)}
	if not cheie:
		return {"result": False, "message": _(_V().E_OCUPAT)}
	return {"result": True, "lucreaza": True, "lucrare": cheie}


def stareServer(arg):
	with _lacatServer:
		v = _lucrariServer.get(arg.get("lucrare", ""))
	if v is None:
		return {"result": False, "message": _(_V().E_EXPIRAT)}
	if v["rez"] is None:
		return {"result": True, "lucreaza": True, "lucrare": arg.get("lucrare", "")}
	return dict(v["rez"], lucreaza=False)


def _argumente(request, chei, maxim=200):
	rez = {}
	for c in chei:
		v = request.args.get(c.encode("ascii"), [b""])[0][:maxim * 4].decode("utf-8", "replace")[:maxim]
		rez[c] = v.strip()
	return rez


def rute(baza, resource):
	from . import meniu_comun_web as M

	def _eroare():
		return _("Filmele și serialele nu se pot citi acum. Încearcă din nou.")

	def citire(functie, chei):
		class Citire(baza):
			def render_GET(self, request):
				try:
					return self._raspunde(request, functie(_argumente(request, chei)))
				except Exception as e:
					print("[HdsWebControl] filme si seriale: %s" % type(e).__name__)
					return self._eroare(request, _eroare(), 503)
		return Citire()

	def schimbare(functie, chei):
		class Schimbare(baza):
			schimbaCeva = True

			def render_POST(self, request):
				try:
					return self._raspunde(request, functie(_argumente(request, chei)))
				except Exception as e:
					print("[HdsWebControl] filme si seriale: %s" % type(e).__name__)
					return self._eroare(request, _eroare(), 503)
		return Schimbare()

	class Surse(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, {"result": True, "surse": _V().publicSurse()})
			except Exception as e:
				print("[HdsWebControl] filme si seriale: %s" % type(e).__name__)
				return self._eroare(request, _eroare(), 503)

	class Server(baza):
		schimbaCeva = True

		def render_GET(self, request):
			try:
				return self._raspunde(request, stareServer(_argumente(request, ("lucrare",), 40)))
			except Exception as e:
				print("[HdsWebControl] filme si seriale: %s" % type(e).__name__)
				return self._eroare(request, _eroare(), 503)

		def render_POST(self, request):
			try:
				return self._raspunde(request, server(_argumente(request, ("fel", "fel_server", "adresa", "utilizator", "parola", "id"))))
			except Exception as e:
				print("[HdsWebControl] filme si seriale: %s" % type(e).__name__)
				return self._eroare(request, _eroare(), 503)

	class Poza(baza):
		def render_GET(self, request):
			octeti, cod = poza(_argumente(request, ("s", "l", "h", "fel"), 40))
			if octeti is None:
				request.setResponseCode(cod)
				request.setHeader(b"cache-control", b"no-store")
				return b""
			request.setHeader(b"content-type", b"image/jpeg")
			request.setHeader(b"cache-control", b"private, max-age=86400")
			return octeti

	class Pagina(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return M.pagina(request, pagina_text)

	api = {
		b"vod-surse": Surse(),
		b"vod": citire(vod, ("fel", "id", "tip", "arg", "cerere")),
		b"vod-locale": citire(locale, ("id", "tip")),
		b"vod-poza": Poza(),
		b"vod-reda": schimbare(reda, ("id", "cheie", "de_la", "nume", "poza", "serial", "serial_nume", "sezon", "numar")),
		b"vod-favorit": schimbare(favorit, ("id", "cheie", "nume", "poza")),
		b"vod-servere": citire(servere, ()),
		b"vod-server": Server(),
	}
	return api, {b"filme-seriale": Pagina()}


def texte():
	return {k: _(v) for k, v in {
		"neasteptat": N_("Receptorul a răspuns neașteptat."),
		"nuRaspunde": N_("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		"faraSursa": N_("Nu ai niciun cont IPTV cu filme. Adaugă contul primit de la furnizor la IPTV."),
		"incarca": N_("Se încarcă..."), "gol": N_("Nimic aici încă."), "continua": N_("Continuă să vizionezi"),
		"favorite": N_("Favorite"), "recente": N_("Adăugate recent"), "filme": N_("Filme"), "seriale": N_("Seriale"),
		"rezultate": N_("Rezultate pentru „%s”"), "reda": N_("Redă pe televizor"), "inceput": N_("Redă de la început"),
		"continuaDe": N_("Continuă de la %s"), "adaugaFav": N_("Adaugă la favorite"), "scoateFav": N_("Scoate de la favorite"),
		"sezonul": N_("Sezonul %s"), "nota": N_("Nota %s"), "regia": N_("Regia: %s"), "actori": N_("Actori: %s"),
		"imagine": N_("Imagine: %s"), "audio": N_("Audio: %s"), "subtitrari": N_("Subtitrări: %s"), "inapoi": N_("Înapoi"),
		"caut": N_("Caut în tot catalogul; rezultatele apar pe măsură ce le găsesc."), "h": N_("%d h %02d min"), "min": N_("%d min"),
		"faraServer": N_("Nu ai încă un server %s. Îl caut în rețea; scrii apoi utilizatorul și parola."),
		"cautServer": N_("Caut serverul %s în rețea..."), "nuGasit": N_("Nu l-am găsit în rețea. Scrie adresa lui mai jos."),
		"adresa": N_("Adresa serverului"), "utilizator": N_("Utilizatorul"), "parola": N_("Parola"),
		"adauga": N_("Adaugă serverul"), "scoate": N_("Scoate serverul"), "maLeg": N_("Mă conectez la server..."),
		"legat": N_("Gata: serverul %s este adăugat."), "cautaIar": N_("Caută din nou în rețea"),
		"faraDisc": N_("Nu am găsit filme pe discuri, stick-uri sau în locurile din rețea."),
	}.items() if k != "grupe"} | {"grupe": dict((g, _(t)) for g, t in _V().GRUPE)}


def pagina_text(stil, config_pagina):
	from html import escape
	from .meniu_comun_web import STIL_PAGINI
	text = PAGINA.replace("__STIL_COMUN__", stil).replace("__STIL_PAGINI__", STIL_PAGINI)
	for cheie, valoare in {"__TITLU__": _("Filme și seriale"), "__CAUTA__": _("Caută"), "__CAUTA_ETICHETA__": _("Caută filme și seriale"),
			"__CONT__": _("Contul")}.items():
		text = text.replace(cheie, escape(valoare, quote=True))
	text = text.replace("__CONFIG__", config_pagina)
	return _cuLimba(text.replace("__TEXTE__", json.dumps(texte(), ensure_ascii=True).replace("</", "<\\/")))


PAGINA = """<!doctype html>
<html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLU__</title><style>__STIL_COMUN__ __STIL_PAGINI__
body{background:#0b1020} main{max-width:1600px!important;width:auto}
#fundal{position:fixed;inset:0;background-size:cover;background-position:center top;opacity:.55;z-index:-1;transition:background-image .3s}
.bara{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.fila{background:#10162a;border:0;color:#c9d2e3;padding:10px 18px;font-size:17px;cursor:pointer}
.fila.aleasa{background:#374ea1;color:#f2f4f8}
#mesaj{margin:6px 0 0;min-height:0}#info{min-height:150px;max-width:900px}#info h2{font-size:32px;margin:12px 0 4px}#meta{color:#c9d2e3}#desc{color:#c9d2e3;max-height:4.8em;overflow:hidden}
.vrand h3{margin:18px 0 8px;font-size:19px}
.vpostere{display:flex;gap:12px;overflow-x:auto;padding-bottom:8px;scroll-snap-type:x proximity}
.poster{flex:0 0 140px;cursor:pointer;scroll-snap-align:start;background:none;border:0;padding:0;color:#c9d2e3;text-align:center}
.poster .img{position:relative;width:140px;height:210px;background:#1a2340;border:3px solid transparent;display:flex;align-items:center;justify-content:center;overflow:hidden;font-size:13px;padding:4px;box-sizing:border-box}
.poster.lat{flex-basis:260px}.poster.lat .img{width:260px;height:146px}
.poster img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.poster:hover .img,.poster:focus .img{border-color:#374ea1}
.poster .t{font-size:13px;margin-top:4px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.progres{position:absolute;left:0;right:0;bottom:0;height:6px;background:#000}.progres i{display:block;height:100%;background:#374ea1}
.progres i.plin{background:#4fd18b}
#pagina{display:flex;gap:24px;flex-wrap:wrap}#pagina h2{font-size:34px;margin:0 0 6px}#pagina .mare{width:240px;height:360px;background:#1a2340;object-fit:cover}
#pagina .dreapta{flex:1;min-width:280px}.piste{color:#f2f4f8}.oameni{color:#aeb9cc}
.ascuns{display:none!important}
</style></head><body><div id="fundal"></div><main><h1>__TITLU__</h1>
<section class="card"><div class="bara" id="grupe" role="tablist"></div>
<div id="server" class="ascuns"><p id="serverText"></p><div class="bara" id="gasite"></div>
<div class="bara"><input id="sAdresa" maxlength="200" placeholder="192.168.1.10:8096" autocomplete="off">
<input id="sUtilizator" maxlength="100" autocomplete="username"><input id="sParola" type="password" maxlength="200" autocomplete="current-password">
<button type="button" id="sAdauga"></button><button type="button" id="sCauta"></button></div></div>
<div class="bara" id="baraFilme">
<button class="fila aleasa" id="filaFilme" type="button"></button><button class="fila" id="filaSeriale" type="button"></button>
<input type="search" id="text" maxlength="80" aria-label="__CAUTA_ETICHETA__" placeholder="__CAUTA_ETICHETA__">
<button type="button" id="cauta">__CAUTA__</button>
<label id="contEticheta" class="ascuns">__CONT__ <select id="cont"></select></label>
<button type="button" id="sScoate" class="ascuns"></button></div>
<p id="mesaj" class="mesaj" role="status" aria-live="polite"></p></section>
<section id="acasa"><div id="info"><h2 id="titlu"></h2><div id="meta"></div><p id="desc"></p></div><div id="randuri"></div></section>
<section id="detalii" class="card ascuns"><button type="button" id="inapoi"></button><div id="pagina"></div></section>
</main><script>
"use strict";
var CFG=__CONFIG__, T=__TEXTE__;
var S={sid:"",tip:"filme",randuri:[],cat:[],catPus:0,detalii:{},cereri:0};
function $(id){return document.getElementById(id)}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function cale(c){if(CFG.jeton)c+=(c.indexOf("?")<0?"?":"&")+"token="+encodeURIComponent(CFG.jeton);return c}
function cerere(c,metoda,date){
 var opt={method:metoda||"GET",cache:"no-store",credentials:"same-origin",headers:{}};
 if(CFG.csrf)opt.headers["X-HDS-CSRF"]=CFG.csrf;
 if(date){opt.headers["Content-Type"]="application/x-www-form-urlencoded";opt.body=date.toString()}
 return fetch(cale(c),opt).then(function(r){
  if(r.status===401&&!CFG.jeton){location.replace("/");throw new Error()}
  return r.json().catch(function(){return {result:false,message:T.neasteptat}})
 })
}
function mesaj(t){$("mesaj").textContent=t||""}
function durata(s){if(!s)return "";var m=Math.round(s/60);return m>=60?T.h.replace("%d",Math.floor(m/60)).replace("%02d",("0"+m%60).slice(-2)):T.min.replace("%d",m)}
function ora(s){var h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return (h?h+":"+("0"+m).slice(-2):m)+":"+("0"+x).slice(-2)}
function nota(n){return n?T.nota.replace("%s",n.replace(".",",")):""}
function meta(d){return [d.an,durata(d.durata),nota(d.nota),d.gen,d.varsta].filter(Boolean).join("  ·  ")}
function lucrare(q){
 return cerere("/api/vod?"+q.toString()).then(function asteapta(d){
  if(d.lucreaza){return new Promise(function(r){setTimeout(r,500)}).then(function(){return cerere("/api/vod?id="+S.sid+"&cerere="+encodeURIComponent(d.cerere))}).then(function(x){if(x.lucreaza&&x.titluri&&q.onPartial)q.onPartial(x.titluri);return asteapta(x)})}
  return d})
}
function cere(fel,arg,tip){var q=new URLSearchParams();q.set("fel",fel);q.set("id",S.sid);q.set("tip",tip||S.tip);q.set("arg",arg||"");return q}
function imagine(box,semn,l,h,fel){
 if(!semn)return;var i=new Image(),n=0;i.alt="";i.loading="lazy";
 i.onerror=function(){if(++n<12)setTimeout(function(){i.src=src+"&r="+n},1000+300*n);else i.remove()};
 var src=cale("/api/vod-poza?s="+semn+"&l="+l+"&h="+h+"&fel="+fel);i.src=src;box.appendChild(i)
}
function poster(t,lat){
 var b=el("button","poster"+(lat?" lat":""));b.type="button";
 var box=el("div","img",t.nume);b.appendChild(box);imagine(box,t.poza,lat?320:162,lat?180:243,lat?"lat":"poster");
 if(t.progres>0){var p=el("div","progres"),i=el("i",t.progres>=1?"plin":"");i.style.width=Math.round(t.progres*100)+"%";p.appendChild(i);box.appendChild(p)}
 b.appendChild(el("div","t",t.sub||t.nume));
 b.addEventListener("focus",function(){arata(t)});b.addEventListener("mouseenter",function(){arata(t)});
 b.addEventListener("click",function(){deschide(t)});return b
}
function rand(titlu,titluri,lat){
 var r=el("div","vrand");r.appendChild(el("h3","",titlu));var p=el("div","vpostere");
 if(titluri===null)p.appendChild(el("p","nota",T.incarca));else if(!titluri.length)p.appendChild(el("p","nota",T.gol));
 else{titluri.forEach(function(t){p.appendChild(poster(t,lat))});if(!S.aratat&&$("acasa").contains(document.activeElement)===false){S.aratat=true;arata(titluri[0])}}r.appendChild(p);return r
}
var infoT=null;
function arata(t){
 $("titlu").textContent=t.nume;$("meta").textContent=[t.an,nota(t.nota)].filter(Boolean).join("  ·  ");$("desc").textContent="";
 clearTimeout(infoT);infoT=setTimeout(function(){detalii(t).then(function(d){if(!d)return;$("titlu").textContent=d.nume||t.nume;$("meta").textContent=meta(d);$("desc").textContent=d.descriere||"";fundal(d)})},400)
}
function fundal(d){var s=d.fundal||d.poster;$("fundal").style.backgroundImage=s?"url('"+cale("/api/vod-poza?s="+s+"&l=960&h=540&fel=fundal")+"')":""}
function detalii(t){
 var k=(t.tip||S.tip)+t.id;if(S.detalii[k])return Promise.resolve(S.detalii[k]);
 return lucrare(cere("detalii",t.id,t.tip||S.tip)).then(function(d){if(d.result){S.detalii[k]=d.detalii;return d.detalii}mesaj(d.message);return null})
}
function porneste(){
 var tura=++S.cereri;S.aratat=false;$("randuri").innerHTML="";S.cat=[];S.catPus=0;$("detalii").classList.add("ascuns");$("acasa").classList.remove("ascuns");
 var cont=$("randuri");
 cerere("/api/vod-locale?id="+S.sid+"&tip="+S.tip).then(function(d){
  if(tura!==S.cereri||!d.result)return;
  if(d.continua.length)cont.insertBefore(rand(T.continua,d.continua,false),cont.firstChild);
  if(d.favorite.length)cont.insertBefore(rand(T.favorite,d.favorite,false),cont.children[d.continua.length?1:0]||null)});
 var rec=rand(T.recente,null,false);cont.appendChild(rec);
 lucrare(cere("recente","")).then(function(d){if(tura!==S.cereri)return;if(d.oprit){rec.remove();return}cont.replaceChild(rand(T.recente,d.result?d.titluri:[],false),rec)});
 lucrare(cere("categorii","")).then(function(d){if(tura!==S.cereri)return;if(!d.result){mesaj(d.message);return}S.cat=d.categorii;if(!S.cat.length&&G.grupa==="disc")mesaj(T.faraDisc);maiMulte()})
}
function maiMulte(){
 var tura=S.cereri,cont=$("randuri");
 S.cat.slice(S.catPus,S.catPus+4).forEach(function(c){
  var r=rand(c.nume,null,false);cont.appendChild(r);
  lucrare(cere("rand",c.id)).then(function(d){if(tura===S.cereri)cont.replaceChild(rand(c.nume,d.result?d.titluri:[],false),r)})});
 S.catPus+=4
}
window.addEventListener("scroll",function(){if(S.catPus<S.cat.length&&innerHeight+scrollY>document.body.offsetHeight-400)maiMulte()});
function buton(text,cls,f){var b=el("button",cls||"",text);b.type="button";b.addEventListener("click",f);return b}
function reda(t,d,deLa,extra){
 var q=new URLSearchParams();q.set("id",S.sid);q.set("cheie",t.cheie);q.set("de_la",deLa?"1":"0");q.set("nume",t.nume||"");q.set("poza",t.poza||d.poster||"");
 Object.keys(extra||{}).forEach(function(k){q.set(k,extra[k])});
 cerere("/api/vod-reda","POST",q).then(function(r){mesaj(r.message)}).catch(function(){mesaj(T.nuRaspunde)})
}
function favorit(cheie,nume,poza,b){
 var q=new URLSearchParams();q.set("id",S.sid);q.set("cheie",cheie);q.set("nume",nume);q.set("poza",poza||"");
 cerere("/api/vod-favorit","POST",q).then(function(r){mesaj(r.message);if(r.result)b.textContent=r.favorit?T.scoateFav:T.adaugaFav})
}
function deschide(t){
 $("acasa").classList.add("ascuns");$("detalii").classList.remove("ascuns");var p=$("pagina");p.innerHTML="";p.appendChild(el("p","nota",T.incarca));scrollTo(0,0);
 detalii(t).then(function(d){
  p.innerHTML="";if(!d)return;fundal(d);
  var st=el("div");var img=el("div","mare");img.style.position="relative";st.appendChild(img);imagine(img,d.poster||t.poza,240,360,"poster");p.appendChild(st);
  var dr=el("div","dreapta");p.appendChild(dr);
  dr.appendChild(el("h2","",d.nume||t.nume));dr.appendChild(el("p","",meta(d)));dr.appendChild(el("p","",d.descriere||""));
  if(d.regia)dr.appendChild(el("p","oameni",T.regia.replace("%s",d.regia)));if(d.actori)dr.appendChild(el("p","oameni",T.actori.replace("%s",d.actori)));
  var piste=[];if(d.video)piste.push(T.imagine.replace("%s",d.video));var aud=(d.audio_vazut&&d.audio_vazut.length)?d.audio_vazut:(d.audio?[d.audio]:[]);
  if(aud.length)piste.push(T.audio.replace("%s",aud.join(", ")));if(d.subtitrari&&d.subtitrari.length)piste.push(T.subtitrari.replace("%s",d.subtitrari.join(", ")));
  if(piste.length)dr.appendChild(el("p","piste",piste.join("   ·   ")));
  var b=el("div","butoane");dr.appendChild(b);
  if(d.tip!=="seriale"){
   if(d.pozitie)b.appendChild(buton(T.continuaDe.replace("%s",ora(d.pozitie)),"principal",function(){reda(d,d,true)}));
   b.appendChild(buton(d.pozitie?T.inceput:T.reda,d.pozitie?"":"principal",function(){reda(d,d,false)}));
   var fb=buton(d.favorit?T.scoateFav:T.adaugaFav,"",function(){favorit(d.cheie,d.nume,t.poza||d.poster,fb)});b.appendChild(fb)
  }else{
   var fs=buton(d.favorit?T.scoateFav:T.adaugaFav,"",function(){favorit("s"+d.id,d.nume,t.poza||d.poster,fs)});b.appendChild(fs);
   var file=el("div","bara"),ep=el("div");dr.appendChild(file);dr.appendChild(ep);
   (d.sezoane||[]).forEach(function(sz,i){var f=buton(T.sezonul.replace("%s",sz.numar),"fila",function(){alege(i)});file.appendChild(f)});
   function alege(i){
    Array.prototype.forEach.call(file.children,function(f,j){f.classList.toggle("aleasa",i===j)});ep.innerHTML="";
    var sz=d.sezoane[i],r=el("div","vpostere");
    sz.episoade.forEach(function(e){var x=poster({nume:e.nume,poza:e.poza,progres:e.progres,sub:(e.numar?e.numar+". ":"")+e.nume+(e.durata?"  "+durata(e.durata):"")},true);
     x.addEventListener("click",function(){reda(e,d,true,{serial:d.id,serial_nume:d.nume,sezon:sz.numar,numar:e.numar||""})},true);r.appendChild(x)});
    ep.appendChild(r)
   }
   var start=0;(d.sezoane||[]).forEach(function(sz,i){sz.episoade.forEach(function(e){if(t.episod&&e.cheie===t.episod)start=i})});
   if(d.sezoane&&d.sezoane.length)alege(start)
  }
 })
}
$("inapoi").textContent=T.inapoi;$("inapoi").addEventListener("click",function(){$("detalii").classList.add("ascuns");$("acasa").classList.remove("ascuns")});
$("filaFilme").textContent=T.filme;$("filaSeriale").textContent=T.seriale;
function fila(tip){S.tip=tip;$("filaFilme").classList.toggle("aleasa",tip==="filme");$("filaSeriale").classList.toggle("aleasa",tip==="seriale");porneste()}
$("filaFilme").addEventListener("click",function(){fila("filme")});$("filaSeriale").addEventListener("click",function(){fila("seriale")});
function cauta(){
 var text=$("text").value.trim();if(!text)return;mesaj(T.caut);$("detalii").classList.add("ascuns");$("acasa").classList.remove("ascuns");
 ["seriale","filme"].forEach(function(tip){
  var titlu=T.rezultate.replace("%s",text)+"  ·  "+(tip==="filme"?T.filme:T.seriale),r=rand(titlu,null,false),cont=$("randuri");cont.insertBefore(r,cont.firstChild);
  var q=cere("cauta",text,tip);q.onPartial=function(l){var n=rand(titlu,l,false);cont.replaceChild(n,r);r=n};
  lucrare(q).then(function(d){(d.titluri||[]).forEach(function(x){x.tip=tip});var n=rand(titlu,d.result?d.titluri:[],false);cont.replaceChild(n,r);r=n})
 })
}
$("cauta").addEventListener("click",cauta);$("text").addEventListener("keydown",function(e){if(e.key==="Enter"){e.preventDefault();cauta()}});
var G={surse:[],grupa:""};
function grupa(g){
 G.grupa=g;Array.prototype.forEach.call($("grupe").children,function(b){b.classList.toggle("aleasa",b.dataset.g===g)});
 var lista=G.surse.filter(function(s){return s.grupa===g}),c=$("cont");c.innerHTML="";
 lista.forEach(function(s){var o=el("option","",s.nume);o.value=s.id;c.appendChild(o)});
 $("contEticheta").classList.toggle("ascuns",lista.length<2);mesaj("");
 var srv=(g==="emby"||g==="jellyfin");$("sScoate").classList.toggle("ascuns",!srv||!lista.length);
 $("server").classList.toggle("ascuns",!srv||lista.length>0);
 $("baraFilme").classList.toggle("ascuns",!lista.length);$("acasa").classList.toggle("ascuns",!lista.length);$("detalii").classList.add("ascuns");
 if(!lista.length){S.sid="";$("randuri").innerHTML="";if(srv)cautaServer();else mesaj(T.faraSursa);return}
 S.sid=lista[0].id;S.detalii={};porneste()
}
function incarcaSurse(alege){
 return cerere("/api/vod-surse").then(function(d){
  if(!d.result){mesaj(d.message||T.neasteptat);return}
  G.surse=d.surse;var gr=$("grupe");gr.innerHTML="";
  Object.keys(T.grupe).forEach(function(g){var b=buton(T.grupe[g],"fila",function(){grupa(g)});b.dataset.g=g;b.setAttribute("role","tab");gr.appendChild(b)});
  grupa(alege||(G.surse.length?G.surse[0].grupa:"iptv"))
 })
}
function asteaptaServer(r){
 if(!r.lucreaza)return Promise.resolve(r);
 return new Promise(function(x){setTimeout(x,700)}).then(function(){return cerere("/api/vod-server?lucrare="+encodeURIComponent(r.lucrare))}).then(asteaptaServer)
}
function postServer(campuri){var q=new URLSearchParams();Object.keys(campuri).forEach(function(k){q.set(k,campuri[k])});return cerere("/api/vod-server","POST",q).then(asteaptaServer)}
function cautaServer(){
 var g=G.grupa,nume=T.grupe[g];$("serverText").textContent=T.faraServer.replace("%s",nume);mesaj(T.cautServer.replace("%s",nume));$("gasite").innerHTML="";
 postServer({fel:"cauta",fel_server:g}).then(function(r){
  if(G.grupa!==g)return;var l=r.gasite||[];mesaj(l.length?"":T.nuGasit);
  l.forEach(function(x){$("gasite").appendChild(buton(x.nume+"  ·  "+x.adresa.replace("http://","").replace("https://",""),"fila",function(){$("sAdresa").value=x.adresa;$("sUtilizator").focus()}))});
  if(l.length===1){$("sAdresa").value=l[0].adresa;$("sUtilizator").focus()}
 }).catch(function(){mesaj(T.nuRaspunde)})
}
$("sAdresa").setAttribute("aria-label",T.adresa);$("sUtilizator").placeholder=T.utilizator;$("sUtilizator").setAttribute("aria-label",T.utilizator);
$("sParola").placeholder=T.parola;$("sParola").setAttribute("aria-label",T.parola);
$("sAdauga").textContent=T.adauga;$("sCauta").textContent=T.cautaIar;$("sScoate").textContent=T.scoate;
$("sCauta").addEventListener("click",cautaServer);
$("sAdauga").addEventListener("click",function(){
 var g=G.grupa;mesaj(T.maLeg);
 postServer({fel:"adauga",fel_server:g,adresa:$("sAdresa").value,utilizator:$("sUtilizator").value,parola:$("sParola").value}).then(function(r){
  $("sParola").value="";if(!r.result){mesaj(r.message||T.neasteptat);return}
  incarcaSurse(g).then(function(){mesaj(T.legat.replace("%s",T.grupe[g]))})
 }).catch(function(){mesaj(T.nuRaspunde)})
});
$("sScoate").addEventListener("click",function(){var q=new URLSearchParams();q.set("fel","scoate");q.set("id",S.sid);
 cerere("/api/vod-server","POST",q).then(function(){incarcaSurse(G.grupa)})});
$("cont").addEventListener("change",function(){S.sid=$("cont").value;S.detalii={};porneste()});
incarcaSurse().catch(function(){mesaj(T.nuRaspunde)});
</script></body></html>
"""


def _cuLimba(text):
	"""<html lang> in limba receptorului: textele paginii vin deja traduse din Python (_()), deci traduce() din
	traducere_pagini, care schimba lang, nu trece pe aici. Pe PC (fara pachet) si in romana pagina ramane lang="ro"."""
	try:
		from .traducere_pagini import limba
	except ImportError:
		return text
	cod = limba()
	return text if cod == "ro" else text.replace('<html lang="ro">', '<html lang="%s">' % cod, 1)
