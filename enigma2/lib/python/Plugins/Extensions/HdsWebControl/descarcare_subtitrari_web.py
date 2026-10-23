# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# descarcare_subtitrari_web.py: perechea web a descarcarii subtitrarilor de pe internet. Din 0.3.2 descarcarea face
# parte din imagine (Components/HdsSubtitrariInternet; inainte era pluginul separat HdsSubtitleDownloader, iar fisierul
# acesta era web.py al lui), deci pagina si rutele exista mereu: HdsWebControl/plugin.py le leaga ca pe celelalte.
#
# Pe televizor: "Caută subtitrări pe internet" si "Descărcare subtitrări" (setarile). Aici: aceeasi cautare si
# descarcare pentru filmul care merge (lucru.py, aceeasi lucrare ca pe televizor), si conturile: parolele si cheile
# numai se scriu, nu se citesc inapoi (pagina arata doar „scrisă” / „nescrisă”); numele de utilizator OpenSubtitles se
# vede.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/descarcare-subtitrari                      filmul, sursele, conturile (fara valori secrete), lucrarea,
#                                                        rezultatul verificarii; numai citeste
#   POST /api/descarcare-subtitrari-cauta                corpul: text=&limbi=ron,eng
#   POST /api/descarcare-subtitrari-descarca             corpul: index=N
#   POST /api/descarcare-subtitrari-aplica               pune in film subtitrarea descarcata (lucru.aplica), o data
#   POST /api/descarcare-subtitrari-verifica             „Verifică sursele”, pe fir; rezultatul vine in GET
#   POST /api/descarcare-subtitrari-film                 filmul de pe un canal TV sau din inregistrare (tv.py):
#        fapta=identifica | alege&index=N | titlu&text=... | local&index=N (o subtitrare deja pe receptor, pusa pe canal)
#   POST /api/descarcare-subtitrari-potrivire            potrivirea subtitrarii de pe internet pe canal, ca bara de pe
#        televizor: fapta=urmatoarea | dinainte | plus | minus | reclama | acum | viteza&viteza=auto|23.976|24|1 | opreste
# Fara film din fisier, GET da in "tv" filmul de pe canal (emisiunea, identificarea, fisierele de pe receptor, potrivirea);
# cautarea (POST -cauta) foloseste atunci filmul identificat (ID-ul IMDb), iar -aplica pune subtitrarea pe canal.
#   POST /api/descarcare-subtitrari-conturi              corpul: os_utilizator=&os_parola=&os_cheie_aplicatie=&
#        subsro_cheie=&subdl_cheie= (un camp gol nu schimba nimic; sterge=os sterge contul OpenSubtitles; din 0.3.0.2
#        sterge=<camp>, de exemplu sterge=subsro_cheie, sterge numai acea parola sau cheie). Numele,
#        parolele si cheile se iau NUMAI din corpul cererii: scrise in adresa (care poate ajunge in istoricul
#        browserului sau in jurnale) se ignora.
#   GET  /descarcare-subtitrari                          pagina
# Pe firul enigma2 numai citirea starii si pornirea lucrarilor (reteaua merge pe firul lucrarii). Cand descarcarea s-a
# terminat, pagina vede „salvat” neaplicat si cere aplicarea prin POST (un GET nu schimba nimic).

MAX_TEXT = 256


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _lu(LU=None):
	if LU is not None:
		return LU
	from Components.HdsSubtitrariInternet import lucru
	return lucru


def _tv(TV=None):
	if TV is not None:
		return TV
	from Components.HdsSubtitrariInternet import tv
	return tv


def _stareTv(TV, sesiune):
	"""Filmul de pe canalul TV sau din inregistrarea de acum (tv.stare), fara nimic din conturi; {"tv": False} altfel."""
	try:
		rez = _tv(TV).stare(sesiune)
	except Exception as e:
		print("[HdsWebControl] subtitrarile pe canal: %s" % e.__class__.__name__)
		return {"tv": False}
	if rez.get("tv"):
		rez["vitezele"] = rez.get("vitezele") or []
	return rez


def stare(LU=None, sesiune=None, cale_film=None, TV=None):
	"""Numai citeste (GET): aplicarea subtitrarii descarcate e in aplica() (POST). Conturile se citesc o singura data.
	Fara film din fisier: "tv" = filmul de pe canalul TV sau din inregistrarea .ts (Components/HdsSubtitrariInternet/
	tv.py): emisiunea, identificarea, fisierele de pe receptor, subtitrarea pusa si potrivirea ei."""
	LU = _lu(LU)
	lucrare = LU.lucrare()
	from Components.HdsSubtitrariInternet import limbi as LB
	st = lucrare.stare()
	date = lucrare.conturi.citeste()
	cale = cale_film if cale_film is not None else LU.filmulDeAcum()
	import os
	conturi = lucrare.conturi.stare(date)
	return {"result": True, "film": os.path.basename(cale) if cale else "",
		"tv": _stareTv(TV, sesiune) if not cale else {"tv": False},
		"surse": [{"id": s.ID, "nume": s.NUME, "adresa": s.ADRESA, "configurat": bool(s.configurat(date))} for s in lucrare.surse()],
		"conturi": conturi, "lucrare": {"faza": st["faza"], "in_curs": st["in_curs"], "mesaj": st["mesaj"],
			"eroare": st["eroare"], "rezultate": st["rezultate"], "text": st["text"], "salvat": os.path.basename(st["salvat"] or ""),
			"aplicat": bool(st.get("aplicat"))},
		"verificare": st.get("verificare") or "", "verificare_in_curs": bool(st.get("verificare_in_curs")),
		"limbi": [[c, LB.nume(c)] for c in (st["limbi"] or LB.implicite())],
		"limbi_toate": [[c, LB.nume(c)] for c in sorted(LB.DOUA)]}


def _cuMesaj(LU, sesiune, cale, reusit, mesaj, TV=None):
	rez = stare(LU, sesiune, cale, TV)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def cauta(argumente, LU=None, sesiune=None, cale_film=None, TV=None):
	LU = _lu(LU)
	cale = cale_film if cale_film is not None else LU.filmulDeAcum()
	from Components.HdsSubtitrariInternet import limbi as LB
	limbi = [c for c in (argumente.get("limbi") or "").split(",") if c in LB.DOUA][:LB.MAX_LIMBI] or None
	if not cale:
		# pe un canal TV sau la o inregistrare: filmul identificat din EPG (dupa ID-ul IMDb, daca e ales)
		f = _filmTv(TV, sesiune)
		if f is None:
			return _cuMesaj(LU, sesiune, cale, False, _t("Căutarea subtitrărilor merge în timpul unui film din fișier, pe un "
				"canal TV sau la o înregistrare."), TV)
		film_tv = dict(f.pentruCautare())
		text = (argumente.get("text") or "").strip()
		if text and text != film_tv.get("titlu"):
			# alt titlu scris in "Textul căutat": cautarea merge dupa el (si anul din ghid), nu dupa ID-ul filmului
			# identificat; filmul altfel se schimba in cardul "Filmul din ghidul programelor" (-film, fapta=titlu)
			film_tv.update({"titlu": text, "imdb": "", "tmdb": ""})
		pornit = LU.lucrare().cauta(f.caleSalvare(), text or None, limbi, film=film_tv)
		return _cuMesaj(LU, sesiune, cale, pornit, _t("Se caută subtitrări...") if pornit else
			_t("O căutare sau o descărcare merge deja; așteaptă să se termine."), TV)
	pornit = LU.lucrare().cauta(cale, argumente.get("text") or None, limbi)
	return _cuMesaj(LU, sesiune, cale, pornit, _t("Se caută subtitrări...") if pornit else
		_t("O căutare sau o descărcare merge deja; așteaptă să se termine."))


def _filmTv(TV, sesiune):
	try:
		return _tv(TV).filmulDeAcum(sesiune)
	except Exception as e:
		print("[HdsWebControl] filmul de pe canal: %s" % e.__class__.__name__)
		return None


def _index(argumente):
	try:
		return int(argumente.get("index", ""))
	except ValueError:
		return -1


def film(argumente, LU=None, sesiune=None, cale_film=None, TV=None):
	"""POST /api/descarcare-subtitrari-film: filmul de pe canal. fapta=identifica (din nou), alege&index=N (unul dintre
	filmele gasite), titlu&text=... (titlul scris de om, identificarea din nou), local&index=N (o subtitrare deja pe
	receptor pusa pe canal)."""
	LU = _lu(LU)
	TVm = _tv(TV)
	f = _filmTv(TV, sesiune)
	if f is None:
		return _cuMesaj(LU, sesiune, cale_film, False, _t("Acum nu merge un canal TV sau o înregistrare."), TV)
	fapta = argumente.get("fapta", "")
	if fapta == "identifica":
		pornit = TVm.identificaPeFir(f)
		return _cuMesaj(LU, sesiune, cale_film, True, _t("Se caută filmul în Wikidata...") if pornit else "", TV)
	if fapta == "alege":
		reusit = TVm.alegeCandidat(f, _index(argumente))
		return _cuMesaj(LU, sesiune, cale_film, reusit, _t("Filmul s-a ales. Caută subtitrările.") if reusit else
			_t("Filmul acesta nu e în listă."), TV)
	if fapta == "titlu":
		reusit = TVm.scrieTitlu(f, argumente.get("text") or "")
		return _cuMesaj(LU, sesiune, cale_film, reusit, _t("Se caută filmul în Wikidata...") if reusit else
			_t("Scrie titlul filmului."), TV)
	if fapta == "local":
		with f.lacat:
			locale = list(f.locale)
		i = _index(argumente)
		if not (0 <= i < len(locale)):
			return _cuMesaj(LU, sesiune, cale_film, False, _t("Fișierul acesta nu mai e pe receptor."), TV)
		reusit, mesaj = TVm.incarca(sesiune, locale[i]["cale"], None)
		return _cuMesaj(LU, sesiune, cale_film, reusit, mesaj, TV)
	return _cuMesaj(LU, sesiune, cale_film, False, _t("Valoarea aceasta nu există."), TV)


def potrivire(argumente, LU=None, sesiune=None, cale_film=None, TV=None):
	"""POST /api/descarcare-subtitrari-potrivire: reglajul subtitrarii de pe internet pe canal, ca bara de pe televizor.
	fapta=urmatoarea | dinainte (replica aleasa incepe acum) | plus | minus (0,5 s) | reclama (ceasul sta / merge) |
	acum (filmul incepe acum) | viteza&viteza=auto|23.976|24|1 | opreste."""
	LU = _lu(LU)
	TVm = _tv(TV)
	fapta = argumente.get("fapta", "")
	if fapta in ("urmatoarea", "dinainte"):
		reusit = TVm.salt(sesiune, 1 if fapta == "urmatoarea" else -1)
		mesaj = _t("Replica aleasă începe acum.") if reusit else _t("Nu mai e nicio replică în partea aceasta.")
	elif fapta in ("plus", "minus"):
		reusit = TVm.muta(sesiune, TVm.PAS_MS if fapta == "plus" else -TVm.PAS_MS)
		mesaj = _t("Subtitrarea s-a mutat cu 0,5 s.") if reusit else ""
	elif fapta == "reclama":
		nou = TVm.reclama(sesiune)
		reusit = nou is not None
		mesaj = (_t("Reclamă: ceasul subtitrării stă. Apasă din nou când revine filmul.") if nou else
			_t("Ceasul subtitrării merge din nou.")) if reusit else ""
	elif fapta == "acum":
		reusit = TVm.acumIncepe(sesiune)
		mesaj = _t("Subtitrarea pornește acum de la începutul filmului.") if reusit else ""
	elif fapta == "viteza":
		reusit = TVm.alegeViteza(sesiune, argumente.get("viteza", ""))
		mesaj = _t("Viteza s-a schimbat.") if reusit else ""
	elif fapta == "opreste":
		reusit = TVm.opreste(sesiune)
		mesaj = _t("Subtitrarea de pe internet s-a oprit.") if reusit else ""
	else:
		return _cuMesaj(LU, sesiune, cale_film, False, _t("Valoarea aceasta nu există."), TV)
	if not reusit and not mesaj:
		mesaj = _t("Acum nu merge o subtitrare de pe internet.")
	return _cuMesaj(LU, sesiune, cale_film, reusit, mesaj, TV)


def descarca(argumente, LU=None, sesiune=None, cale_film=None):
	LU = _lu(LU)
	try:
		index = int(argumente.get("index", ""))
	except ValueError:
		return _cuMesaj(LU, sesiune, cale_film, False, _t("Rezultatul nu există."))
	pornit = LU.lucrare().descarca(index)
	return _cuMesaj(LU, sesiune, cale_film, pornit, _t("Se descarcă subtitrarea...") if pornit else
		_t("Rezultatul nu există sau o lucrare merge deja."))


def aplica(argumente, LU=None, sesiune=None, cale_film=None):
	"""Pe firul enigma2: subtitrarea descarcata intra in lista filmului si porneste (o singura data)."""
	LU = _lu(LU)
	pornit = LU.lucrare().aplica(sesiune)
	return _cuMesaj(LU, sesiune, cale_film, True, LU.lucrare().stare()["mesaj"] if pornit else "")


def verifica(argumente, LU=None, sesiune=None, cale_film=None):
	LU = _lu(LU)
	LU.lucrare().verifica()     # o verificare care merge deja se lasa sa se termine
	return _cuMesaj(LU, sesiune, cale_film, True, _t("Se verifică sursele..."))


def conturi(argumente, LU=None, sesiune=None, cale_film=None):
	LU = _lu(LU)
	lucrare = LU.lucrare()
	from Components.HdsSubtitrariInternet.conturi import CAMPURI
	if argumente.get("sterge") == "os":
		reusit = lucrare.conturi.schimba(os_utilizator=None, os_parola=None)
		try:
			from Components.HdsSubtitrariInternet.surse import opensubtitles
			opensubtitles.uitaJetonul()
		except ImportError:
			pass
		return _cuMesaj(LU, sesiune, cale_film, reusit, _t("Contul OpenSubtitles s-a șters de pe receptor.") if reusit else
			_t("Datele nu s-au putut scrie pe receptor."))
	# 0.3.0.2: o singura parola sau cheie stearsa (sterge=<camp>); valoarea nu se arata nici inainte, nici dupa
	if argumente.get("sterge") in CAMPURI:
		camp = argumente["sterge"]
		reusit = lucrare.conturi.schimba(**{camp: None})
		if camp.startswith("os_"):
			try:
				from Components.HdsSubtitrariInternet.surse import opensubtitles
				opensubtitles.uitaJetonul()
			except ImportError:
				pass
		return _cuMesaj(LU, sesiune, cale_film, reusit, _t("Șters de pe receptor.") if reusit else
			_t("Datele nu s-au putut scrie pe receptor."))
	noi = dict((k, argumente[k]) for k in CAMPURI if argumente.get(k))
	if not noi:
		return _cuMesaj(LU, sesiune, cale_film, False, _t("Nu s-a scris nimic nou."))
	if any(k.startswith("os_") for k in noi):
		try:
			from Components.HdsSubtitrariInternet.surse import opensubtitles
			opensubtitles.uitaJetonul()
		except ImportError:
			pass
	reusit = lucrare.conturi.schimba(**noi)
	return _cuMesaj(LU, sesiune, cale_film, reusit, _t("Salvat.") if reusit else _t("Datele nu s-au putut scrie pe receptor."))


# campurile conturilor: se primesc numai din corpul cererii, niciodata din adresa
SECRETE = ("os_utilizator", "os_parola", "os_cheie_aplicatie", "subsro_cheie", "subdl_cheie")


def _cheiDinAdresa(request):
	"""Numele argumentelor scrise in adresa (request.args le amesteca cu cele din corp)."""
	uri = getattr(request, "uri", b"") or b""
	if isinstance(uri, bytes):
		uri = uri.decode("utf-8", "replace")
	try:
		from urllib.parse import urlsplit, parse_qsl
	except ImportError:
		return set()
	return set(k for k, v in parse_qsl(urlsplit(uri).query, keep_blank_values=True))


def argumente(request):
	"""Argumentele cererii ca text scurt, fara token; numai cheile stiute; conturile numai din corp."""
	permise = ("text", "limbi", "index", "sterge", "fapta", "viteza") + SECRETE
	din_adresa = _cheiDinAdresa(request)
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise or (cheie in SECRETE and cheie in din_adresa):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_TEXT].strip()
	return rez


def rute(baza, resource, sesiune=None, LU=None):
	"""({nume: resursa de sub /api}, resursa paginii), ca celelalte pagini ale HdsWebControl."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(LU, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request), LU=LU, sesiune=_ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class CautaResource(_Schimba):
		lucru = staticmethod(cauta)

	class DescarcaResource(_Schimba):
		lucru = staticmethod(descarca)

	class ConturiResource(_Schimba):
		lucru = staticmethod(conturi)

	class AplicaResource(_Schimba):
		lucru = staticmethod(aplica)

	class VerificaResource(_Schimba):
		lucru = staticmethod(verifica)

	class FilmResource(_Schimba):
		lucru = staticmethod(film)

	class PotrivireResource(_Schimba):
		lucru = staticmethod(potrivire)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"descarcare-subtitrari": StareResource(),
		b"descarcare-subtitrari-cauta": CautaResource(),
		b"descarcare-subtitrari-descarca": DescarcaResource(),
		b"descarcare-subtitrari-conturi": ConturiResource(),
		b"descarcare-subtitrari-aplica": AplicaResource(),
		b"descarcare-subtitrari-verifica": VerificaResource(),
		b"descarcare-subtitrari-film": FilmResource(),
		b"descarcare-subtitrari-potrivire": PotrivireResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca celelalte pagini ale HdsWebControl."""
	from Plugins.Extensions.HdsWebControl import plugin as P
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


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Descărcare subtitrări</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .camp{display:grid;grid-template-columns:minmax(160px,240px) 1fr auto;gap:10px;align-items:center;padding:6px 0;}
  .sursa{padding:2px 0;}
  .titlu{font-size:.98rem;word-break:break-word;}
  .detalii{color:var(--text-slab);font-size:.85rem;margin-top:2px;}
  input,select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;box-sizing:border-box;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .scrisa{color:var(--verde);}
  @media (max-width:560px){ .rand,.camp{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Descărcare subtitrări</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Filmul de acum</h2>
    <p class="titlu" id="film"></p>
    <div class="camp"><label for="text">Textul căutat</label><input type="text" id="text" maxlength="120"></div>
    <div class="camp"><label for="limbi">Limbile</label><select id="limbi"></select></div>
    <div class="butoane"><button type="button" class="verde" id="cauta">Caută</button></div>
    <p class="mesaj" id="mesajLucrare"></p>
    <div id="rezultate"></div>
  </section>
  <section class="card ascuns" id="cardTv">
    <h2>Filmul din ghidul programelor</h2>
    <p class="titlu" id="tvFilm"></p>
    <p class="detalii" id="tvStare"></p>
    <div id="tvCandidati"></div>
    <div class="camp"><label for="tvTitlu">Titlul filmului (original, dacă îl știi)</label><input type="text" id="tvTitlu" maxlength="120"><button type="button" id="tvCautaFilm">Caută filmul</button></div>
    <div id="tvLocale"></div>
    <p class="nota">Filmul se caută în Wikidata, fără cheie, după titlul și anul din ghid; subtitrările se caută apoi după codul IMDb al filmului. Subtitrările descărcate rămân pe receptor: la o reluare a filmului apar aici, fără o descărcare nouă.</p>
  </section>
  <section class="card ascuns" id="cardPotrivire">
    <h2>Potrivirea subtitrării</h2>
    <p class="titlu" id="ptPozitie"></p>
    <p class="detalii" id="ptReplica"></p>
    <p class="detalii" id="ptUrmatoarea"></p>
    <div class="butoane">
      <button type="button" data-fapta="dinainte">&#9664; Replica dinainte</button>
      <button type="button" data-fapta="urmatoarea">Replica următoare &#9654;</button>
      <button type="button" data-fapta="minus">&minus;0,5 s</button>
      <button type="button" data-fapta="plus">+0,5 s</button>
    </div>
    <div class="butoane">
      <button type="button" class="verde" id="ptReclama">Reclamă</button>
      <button type="button" data-fapta="acum">Acum începe filmul</button>
      <button type="button" data-fapta="opreste">Oprește subtitrarea</button>
    </div>
    <div class="camp"><label for="ptViteza">Viteza</label><select id="ptViteza"></select></div>
    <p class="nota">Când auzi o replică, apasă Replica următoare (sau dinainte) până o vezi scrisă: replica aleasă începe atunci. La o pauză de reclame apasă Reclamă la început și din nou când revine filmul. Viteza: subtitrările făcute pe copii de 23,976 cadre pe secundă merg mai repede pe canalele de 25.</p>
  </section>
  <section class="card">
    <h2>Conturi și chei</h2>
    <div class="camp"><label for="os_utilizator">OpenSubtitles: nume de utilizator</label><input type="text" id="os_utilizator" autocomplete="off"></div>
    <div class="camp"><label for="os_parola">OpenSubtitles: parola <span class="detalii" id="st_os_parola"></span></label><input type="password" id="os_parola" autocomplete="new-password"><button type="button" class="ascuns" id="sterge_os_parola">Șterge</button></div>
    <div class="camp"><label for="os_cheie_aplicatie">OpenSubtitles: cheia aplicației <span class="detalii" id="st_os_cheie_aplicatie"></span></label><input type="password" id="os_cheie_aplicatie" autocomplete="off"><button type="button" class="ascuns" id="sterge_os_cheie_aplicatie">Șterge</button></div>
    <div class="camp"><label for="subsro_cheie">subs.ro: cheia API <span class="detalii" id="st_subsro_cheie"></span></label><input type="password" id="subsro_cheie" autocomplete="off"><button type="button" class="ascuns" id="sterge_subsro_cheie">Șterge</button></div>
    <div class="camp"><label for="subdl_cheie">SubDL: cheia API <span class="detalii" id="st_subdl_cheie"></span></label><input type="password" id="subdl_cheie" autocomplete="off"><button type="button" class="ascuns" id="sterge_subdl_cheie">Șterge</button></div>
    <div class="butoane"><button type="button" class="verde" id="salveaza">Salvează</button><button type="button" id="verifica">Verifică sursele</button><button type="button" id="stergeOs">Șterge contul OpenSubtitles</button></div>
    <p class="mesaj" id="verificare"></p>
    <p class="nota">Parolele și cheile numai se scriu sau se șterg aici; nu se mai arată. Un câmp lăsat gol nu schimbă nimic. Folosește pentru OpenSubtitles o parolă pe care nu o mai folosești în altă parte. Numele de utilizator, nu adresa de e-mail.</p>
  </section>
  <section class="card">
    <h2>Sursele</h2>
    <div class="nota" id="surse"></div>
    <p class="nota">Subtitrările se caută la cererea ta, pentru fișierul tău, și se salvează lângă film; nu trec prin serverele HD Satelit. Răspunzi de ce descarci. Pe contul gratuit, OpenSubtitles poate pune o reclamă a lor la începutul sau la sfârșitul subtitrării.</p>
  </section>
  <p class="mesaj" id="mesaj"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var DATE = null;
var APLICAT_CERUT = "";
var CAMPURI = ["os_utilizator", "os_parola", "os_cheie_aplicatie", "subsro_cheie", "subdl_cheie"];
var SECRETE = {os_parola: "OpenSubtitles: parola", os_cheie_aplicatie: "OpenSubtitles: cheia aplicației",
  subsro_cheie: "subs.ro: cheia API", subdl_cheie: "SubDL: cheia API"};
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
var IDENTIFICARE_CERUTA = "";
function buton(text, clasa, fapta){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text;
  if(clasa){ b.className = clasa; }
  b.addEventListener("click", fapta);
  return b;
}
function aratTv(t){
  // filmul de pe canal (sau din inregistrare): emisiunea, identificarea, filmele gasite, fisierele de pe receptor
  $("cardTv").classList.toggle("ascuns", !t.tv);
  $("cardPotrivire").classList.toggle("ascuns", !(t.tv && t.subtitrare));
  if(!t.tv){ return; }
  var idf = t.identificare || {};
  var a = idf.ales;
  $("tvFilm").textContent = a ? ((a.original || a.titlu) + " (" + (a.an || "?") + ")" + (a.regizor ? ", regia " + a.regizor : "") + ", IMDb " + a.imdb)
    : ((t.info.titlu || t.emisiune || "?") + (t.info.an ? " (" + t.info.an + ")" : ""));
  var st = $("tvStare");
  st.textContent = (t.fel === "inregistrare" ? "Înregistrare" : "Canal") + (t.canal ? ": " + t.canal : "") + ". " +
    (idf.stare === "cauta" ? "Se caută filmul în Wikidata..." : (idf.mesaj || (a ? "Film identificat." : "")));
  var c = $("tvCandidati"); c.textContent = "";
  if(!a && (idf.candidati || []).length > 1){
    idf.candidati.forEach(function(x, k){
      var rand = document.createElement("div"); rand.className = "rand";
      var s = document.createElement("div"); s.className = "titlu";
      s.textContent = (x.original || x.titlu) + " (" + (x.an || "?") + ")" + (x.regizor ? ", regia " + x.regizor : "") + ", IMDb " + x.imdb;
      rand.appendChild(s);
      rand.appendChild(buton("Acesta e", "", function(){ trimite("/api/descarcare-subtitrari-film", {fapta: "alege", index: k}); }));
      c.appendChild(rand);
    });
  }
  var l = $("tvLocale"); l.textContent = "";
  (t.locale || []).forEach(function(x, k){
    var rand = document.createElement("div"); rand.className = "rand";
    var s = document.createElement("div"); s.className = "titlu"; s.textContent = "Pe receptor: " + x.nume;
    rand.appendChild(s);
    rand.appendChild(buton("Pune pe canal", "", function(){ trimite("/api/descarcare-subtitrari-film", {fapta: "local", index: k}); }));
    l.appendChild(rand);
  });
  if(idf.stare === "nepornita" && IDENTIFICARE_CERUTA !== t.emisiune){
    IDENTIFICARE_CERUTA = t.emisiune;
    trimite("/api/descarcare-subtitrari-film", {fapta: "identifica"});
  }
  if(t.subtitrare){
    $("ptPozitie").textContent = "Filmul la " + (t.pozitie_text || "") + " · " + (t.viteza_text || "") + " · " + t.subtitrare.nume;
    $("ptReplica").textContent = "Acum: " + (t.replica || "-").replace(/\\n/g, " / ");
    $("ptUrmatoarea").textContent = "Următoarea: " + (t.urmatoarea || "-").replace(/\\n/g, " / ");
    $("ptReclama").textContent = t.reclama ? "Reclamă: pornește ceasul" : "Reclamă: oprește ceasul";
    if(document.activeElement !== $("ptViteza")){
      var sel = $("ptViteza"); sel.textContent = "";
      (t.vitezele || []).forEach(function(v){ var o = document.createElement("option"); o.value = v[0]; o.textContent = v[1]; sel.appendChild(o); });
      sel.value = t.viteza_cod || "auto";
    }
  }
}
function arata(d){
  DATE = d;
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  var t = d.tv || {tv: false};
  $("film").textContent = d.film ? d.film : (t.tv ? ((t.fel === "inregistrare" ? "Înregistrarea: " : "Pe canal: ") + (t.emisiune || t.canal || ""))
    : "Acum nu rulează un film din fișier, un canal TV sau o înregistrare. Pornește filmul, apoi caută.");
  $("cauta").disabled = !(d.film || t.tv) || d.lucrare.in_curs;
  aratTv(t);
  if(document.activeElement !== $("text") && !$("text").value){ $("text").value = d.lucrare.text || ""; }
  if(document.activeElement !== $("limbi") && !$("limbi").options.length){
    var sel = $("limbi"); var imp = d.limbi.map(function(x){ return x[0]; }).join(",");
    var o = document.createElement("option"); o.value = imp; o.textContent = d.limbi.map(function(x){ return x[1]; }).join(", "); sel.appendChild(o);
    d.limbi_toate.forEach(function(x){ if(x[0] !== imp){ var p = document.createElement("option"); p.value = x[0]; p.textContent = x[1]; sel.appendChild(p); } });
  }
  var l = d.lucrare;
  var ml = $("mesajLucrare"); ml.textContent = l.mesaj || ""; ml.classList.toggle("eroare", !!l.eroare);
  var r = $("rezultate"); r.textContent = "";
  (l.rezultate || []).forEach(function(x){
    var rand = document.createElement("div"); rand.className = "rand";
    var st = document.createElement("div");
    var t = document.createElement("div"); t.className = "titlu"; t.textContent = x.limba_text + "  " + x.nume;
    var det = document.createElement("div"); det.className = "detalii";
    var parti = [x.sursa];
    if(x.potrivire){ parti.push("potrivită cu fișierul"); }
    if(x.surzi){ parti.push("pentru surzi"); }
    if(x.descarcari){ parti.push(x.descarcari + " descărcări"); }
    if(x.fps){ parti.push(String(x.fps).replace(".", ",") + " cadre/s"); }
    if(x.automata){ parti.push("tradusă automat"); }
    if(x.detalii){ parti.push(x.detalii); }
    det.textContent = parti.join(", ");
    st.appendChild(t); st.appendChild(det);
    var b = document.createElement("button"); b.type = "button"; b.textContent = "Descarcă"; b.disabled = l.in_curs;
    b.addEventListener("click", function(){ trimite("/api/descarcare-subtitrari-descarca", {index: x.index}); });
    rand.appendChild(st); rand.appendChild(b); r.appendChild(rand);
  });
  if(l.salvat && !l.aplicat && APLICAT_CERUT !== l.salvat){
    APLICAT_CERUT = l.salvat;
    trimite("/api/descarcare-subtitrari-aplica", {});
  }
  $("verifica").disabled = !!d.verificare_in_curs;
  var v = $("verificare"); v.textContent = d.verificare_in_curs ? "Se verifică sursele..." : (d.verificare || "");
  v.style.whiteSpace = "pre-line";
  CAMPURI.forEach(function(c){
    var s = $("st_" + c); if(s){ s.textContent = d.conturi[c] ? "(scrisă)" : "(nescrisă)"; s.classList.toggle("scrisa", !!d.conturi[c]); }
  });
  if(document.activeElement !== $("os_utilizator") && !$("os_utilizator").value){ $("os_utilizator").value = d.conturi.os_utilizator_text || ""; }
  Object.keys(SECRETE).forEach(function(c){ $("sterge_" + c).classList.toggle("ascuns", !d.conturi[c]); });
  // fiecare sursa: pregatita (are datele de care are nevoie) sau nu; o sursa se foloseste numai cand e pregatita
  var s = $("surse"); s.textContent = "";
  d.surse.forEach(function(x){
    var p = document.createElement("div"); p.className = "sursa";
    p.textContent = x.nume + ": " + (x.configurat ? "pregătită, se folosește la căutare" : "nepregătită, lipsesc datele de mai sus");
    p.classList.toggle("scrisa", !!x.configurat);
    s.appendChild(p);
  });
}
function citeste(){
  return cerere("/api/descarcare-subtitrari").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde."; });
}
function trimite(cale, valori){
  var q = new URLSearchParams();
  Object.keys(valori).forEach(function(k){ q.set(k, valori[k]); });
  mesaj("Se trimite...");
  return cerere(cale, "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.lucrare){ arata(d); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("cauta").addEventListener("click", function(){ trimite("/api/descarcare-subtitrari-cauta", {text: $("text").value, limbi: $("limbi").value}); });
$("salveaza").addEventListener("click", function(){
  var v = {};
  CAMPURI.forEach(function(c){ var x = $(c).value.trim(); if(x && !(c === "os_utilizator" && DATE && x === DATE.conturi.os_utilizator_text)){ v[c] = x; } });
  trimite("/api/descarcare-subtitrari-conturi", v).then(function(){ CAMPURI.forEach(function(c){ if(c !== "os_utilizator"){ $(c).value = ""; } }); });
});
$("verifica").addEventListener("click", function(){ trimite("/api/descarcare-subtitrari-verifica", {}); });
$("tvCautaFilm").addEventListener("click", function(){
  var x = $("tvTitlu").value.trim();
  if(!x){ mesaj("Scrie titlul filmului.", true); return; }
  trimite("/api/descarcare-subtitrari-film", {fapta: "titlu", text: x});
});
Array.prototype.forEach.call(document.querySelectorAll("button[data-fapta]"), function(b){
  b.addEventListener("click", function(){ trimite("/api/descarcare-subtitrari-potrivire", {fapta: b.getAttribute("data-fapta")}); });
});
$("ptReclama").addEventListener("click", function(){ trimite("/api/descarcare-subtitrari-potrivire", {fapta: "reclama"}); });
$("ptViteza").addEventListener("change", function(){ trimite("/api/descarcare-subtitrari-potrivire", {fapta: "viteza", viteza: $("ptViteza").value}); });
$("stergeOs").addEventListener("click", function(){
  if(!confirm("Ștergi contul OpenSubtitles de pe receptor?")){ return; }
  trimite("/api/descarcare-subtitrari-conturi", {sterge: "os"}).then(function(){ $("os_utilizator").value = ""; });
});
Object.keys(SECRETE).forEach(function(c){
  $("sterge_" + c).addEventListener("click", function(){
    if(!confirm("Ștergi de pe receptor " + SECRETE[c] + "?")){ return; }
    trimite("/api/descarcare-subtitrari-conturi", {sterge: c}).then(function(){ $(c).value = ""; });
  });
});
citeste();
setInterval(function(){ citeste(); }, 1500);
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
		N_("Descărcare subtitrări"),
		N_("Se citește starea..."),
		N_("Filmul de acum"),
		N_("Textul căutat"),
		N_("Limbile"),
		N_("Caută"),
		N_("Filmul din ghidul programelor"),
		N_("Titlul filmului (original, dacă îl știi)"),
		N_("Caută filmul"),
		N_("Filmul se caută în Wikidata, fără cheie, după titlul și anul din ghid; subtitrările se caută "
			"apoi după codul IMDb al filmului. Subtitrările descărcate rămân pe receptor: la o reluare a "
			"filmului apar aici, fără o descărcare nouă."),
		N_("Potrivirea subtitrării"),
		N_("&#9664; Replica dinainte"),
		N_("Replica următoare &#9654;"),
		N_("Reclamă"),
		N_("Acum începe filmul"),
		N_("Oprește subtitrarea"),
		N_("Viteza"),
		N_("Când auzi o replică, apasă Replica următoare (sau dinainte) până o vezi scrisă: replica aleasă "
			"începe atunci. La o pauză de reclame apasă Reclamă la început și din nou când revine filmul. "
			"Viteza: subtitrările făcute pe copii de 23,976 cadre pe secundă merg mai repede pe canalele de "
			"25."),
		N_("Conturi și chei"),
		N_("OpenSubtitles: nume de utilizator"),
		N_("OpenSubtitles: parola <span class=\"detalii\" id=\"st_os_parola\"></span>"),
		N_("Șterge"),
		N_("OpenSubtitles: cheia aplicației <span class=\"detalii\" id=\"st_os_cheie_aplicatie\"></span>"),
		N_("subs.ro: cheia API <span class=\"detalii\" id=\"st_subsro_cheie\"></span>"),
		N_("SubDL: cheia API <span class=\"detalii\" id=\"st_subdl_cheie\"></span>"),
		N_("Salvează"),
		N_("Verifică sursele"),
		N_("Șterge contul OpenSubtitles"),
		N_("Parolele și cheile numai se scriu sau se șterg aici; nu se mai arată. Un câmp lăsat gol nu "
			"schimbă nimic. Folosește pentru OpenSubtitles o parolă pe care nu o mai folosești în altă "
			"parte. Numele de utilizator, nu adresa de e-mail."),
		N_("Sursele"),
		N_("Subtitrările se caută la cererea ta, pentru fișierul tău, și se salvează lângă film; nu trec "
			"prin serverele HD Satelit. Răspunzi de ce descarci. Pe contul gratuit, OpenSubtitles poate pune "
			"o reclamă a lor la începutul sau la sfârșitul subtitrării."),
	),
	"js": (
		N_("OpenSubtitles: parola"),
		N_("OpenSubtitles: cheia aplicației"),
		N_("subs.ro: cheia API"),
		N_("SubDL: cheia API"),
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_(", regia"),
		N_("Înregistrare"),
		N_("Canal"),
		N_("Se caută filmul în Wikidata..."),
		N_("Film identificat."),
		N_("Acesta e"),
		N_("Pe receptor:"),
		N_("Pune pe canal"),
		N_("Filmul la"),
		N_("Acum:"),
		N_("Următoarea:"),
		N_("Reclamă: pornește ceasul"),
		N_("Reclamă: oprește ceasul"),
		N_("Înregistrarea:"),
		N_("Pe canal:"),
		N_("Acum nu rulează un film din fișier, un canal TV sau o înregistrare. Pornește filmul, apoi caută."),
		N_("potrivită cu fișierul"),
		N_("pentru surzi"),
		N_("descărcări"),
		N_("tradusă automat"),
		N_("Descarcă"),
		N_("Se verifică sursele..."),
		N_("(scrisă)"),
		N_("(nescrisă)"),
		N_("pregătită, se folosește la căutare"),
		N_("nepregătită, lipsesc datele de mai sus"),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde."),
		N_("Se trimite..."),
		N_("Scrie titlul filmului."),
		N_("Ștergi contul OpenSubtitles de pe receptor?"),
		N_("Ștergi de pe receptor"),
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
