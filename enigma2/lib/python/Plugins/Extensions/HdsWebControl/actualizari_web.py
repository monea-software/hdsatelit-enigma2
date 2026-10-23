# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# actualizari_web.py: "Actualizare software" prin pachete in interfata web (HdsWebControl), perechea ecranului
# Screens/HdsActualizari.py. Aceeasi stare si aceleasi actiuni, din Components/HdsActualizari.py (o singura lucrare
# odata: ce porneste pagina se vede si pe televizor, si invers).
#
# Rute (poarta comuna a HdsJsonResource; cele care schimba ceva cer POST + antetul CSRF al panoului, sau ?token=):
#   GET  /api/actualizari                 starea: imaginea, canalul, rezultatul cautarii, progresul, jurnalul scurt
#   POST /api/actualizari-cauta           porneste cautarea (stare.json, opkg update, planul)
#   POST /api/actualizari-instaleaza      instaleaza planul; actualizare=<N> = numarul intern al publicarii aratate in
#                                         pagina (cu versiunea ei), altfel nimic
#   POST /api/actualizari-zilnic          zilnic=1|0: verificarea zilnica (numai anunta)
#   POST /api/actualizari-reporneste      reporneste interfata pe calea sigura (TryQuitMainloop 3), numai dupa instalare;
#                                         cu memoria decodorului farmitata si fara inregistrare tot receptorul
#                                         (TryQuitMainloop 2, Components/HdsMemorieDriver.py; la fel actualizarea rapida)
#   POST /api/actualizari-rapid           actualizarea rapida: cauta, instaleaza ce gaseste si reporneste interfata,
#                                         totul pe receptor (Components/HdsActualizari.actualizeazaRapid); pagina numai
#                                         urmareste pasii si asteapta sa revina interfata cu versiunea noua
#   GET  /actualizari                     pagina (aceeasi poarta ca /paznic)
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (A) si sesiunea.

import json
import re

try:
	from html import escape as _escape
except ImportError:  # Python 2 (probele vechi)
	from cgi import escape as _escape


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _a(A=None):
	if A is not None:
		return A
	from Components import HdsActualizari
	return HdsActualizari


def stare(A=None):
	"""Corpul lui GET /api/actualizari"""
	A = _a(A)
	rez = A.actualizari.stare_publica()
	r = rez.get("rezultat") or {}
	rez["texte_motive"] = [_t(x) for x in r.get("texte_motive") or []]
	rez["text_imagine_noua"] = _t(A.TEXT_IMAGINE_NOUA) if r.get("stare") == A.IMAGINE_NOUA else ""
	# "Ce e nou" grupat pe versiuni (de la cea instalata pana la cea de pe server), in limba receptorului, ca pe
	# televizor (Components/HdsActualizari.noutati); un feed vechi da numai versiunea de pe server
	rez["noutati"] = [{"versiune": v, "titlu": _t("Ce e nou în %s:") % v, "randuri": randuri}
		for v, randuri in A.noutati(r.get("server") or {})]
	# "Un pachet", "2 pachete", "20 pachete": pluralul dupa numar, cu formele limbii (ca Screens/HdsActualizari
	# text_pachete); %s ramane pentru marime, pe care o scrie pagina
	n = len(r.get("pachete") or [])
	rez["text_pachete"] = _pachete(n) if n else ""
	# intrebarea de repornire (TryQuitMainloop) e pe televizor: pagina o spune cand repornirea rapida nu se face
	rez["intrebare_pe_tv"] = _intrebare_pe_tv()
	rez["result"] = True
	return rez


def _intrebare_pe_tv():
	try:
		from Screens import Standby
		return bool(getattr(Standby, "inTryQuitMainloop", False))
	except Exception:
		return False


def _pachete(n):
	try:
		from Components.HdsImportSurse import ngettext
	except ImportError:
		def ngettext(unu, multe, k):
			return unu if k == 1 else multe
	return ngettext("%d pachet, %s", "%d pachete, %s", n).replace("%d", str(n), 1)


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:6]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:8].strip()
	return rez


def cauta(A=None):
	A = _a(A)
	pornit = A.actualizari.cauta()
	rez = stare(A)
	rez["result"] = bool(pornit) or rez["rezultat"].get("stare") in (A.FARA_SURSA, A.FARA_CHEIE)
	rez["message"] = A.actualizari.mesaj if not pornit else ""
	return rez


def instaleaza(arg, A=None):
	A = _a(A)
	n = arg.get("actualizare", "")
	if not re.match(r"^[0-9]{1,3}\Z", n):
		rez = stare(A)
		rez.update({"result": False, "message": _t("Lipsește numărul actualizării văzute în pagină.")})
		return rez
	pornit = A.actualizari.instaleaza(int(n))
	rez = stare(A)
	rez.update({"result": bool(pornit), "message": "" if pornit else A.actualizari.mesaj})
	return rez


def zilnic(arg, A=None):
	A = _a(A)
	v = arg.get("zilnic")
	if v not in ("0", "1"):
		rez = stare(A)
		rez.update({"result": False, "message": _t("Se alege cu zilnic=1 sau zilnic=0.")})
		return rez
	A.seteaza_zilnic(v == "1")
	rez = stare(A)
	rez["message"] = _t("Verificarea zilnică este pornită.") if v == "1" else _t("Verificarea zilnică este oprită.")
	return rez


def reporneste(sesiune, A=None):
	A = _a(A)
	if not A.actualizari.repornire:
		rez = stare(A)
		rez.update({"result": False, "message": _t("Repornirea de aici se face numai după o actualizare instalată.")})
		return rez
	s = sesiune() if sesiune else None
	if s is None:
		rez = stare(A)
		rez.update({"result": False, "message": _t("Interfața nu este pornită încă.")})
		return rez
	from Screens.Standby import TryQuitMainloop
	cod = _codRepornire(s)
	s.open(TryQuitMainloop, cod)
	rez = stare(A)
	rez["message"] = _t("Receptorul repornește. Pagina se poate reîncărca după două minute.") if cod == 2 else \
		_t("Interfața repornește. Pagina se poate reîncărca după un minut.")
	return rez


def _codRepornire(s, inregistrari=None):
	"""3 (interfata) sau 2 (receptorul intreg: memoria decodorului farmitata, nicio inregistrare;
	Components/HdsMemorieDriver.py). Fara modul (probele de pe PC) sau la o eroare: 3, ca inainte."""
	try:
		from Components.HdsMemorieDriver import codRepornireDupaActualizare
	except Exception:
		return 3
	try:
		return codRepornireDupaActualizare(s, inregistrari=inregistrari)
	except Exception:
		return 3


def rapid(sesiune, A=None):
	"""POST /api/actualizari-rapid: cauta, instaleaza ce gaseste si reporneste interfata, pe receptor
	(Components/HdsActualizari.actualizeazaRapid); pagina numai urmareste pasii. Cand o cautare sau o instalare e deja
	in lucru (sau o actualizare instalata asteapta repornirea), raspunsul spune asta si nu porneste nimic."""
	A = _a(A)
	pornit = A.actualizari.actualizeazaRapid(reporneste_rapid(sesiune))
	rez = stare(A)
	rez["result"] = bool(pornit) or rez["rezultat"].get("stare") in (A.FARA_SURSA, A.FARA_CHEIE)
	rez["message"] = A.actualizari.mesaj if not pornit else ""
	return rez


def reporneste_rapid(sesiune, Standby=None, stare_receptor=None):
	"""Repornirea data modului rapid: aceeasi cale ca reporneste() (sesiunea, TryQuitMainloop 3), deschisa cu
	openWithCallback (chemat numai cand interfata nu reporneste, adica la Nu pe televizor). Numai cand TryQuitMainloop
	nu ar intreba: cu o intrebare de repornire deja pe ecran, cu o inregistrare in curs sau peste mai putin de 6 minute
	ori cu o lucrare in fundal intoarce de ce asteapta (Components/HdsAlimentare.stareReceptor, aceleasi reguli ca
	Screens/Standby.py), iar modul rapid incearca din nou mai tarziu."""
	def reporneste(la_refuz):
		s = sesiune() if sesiune else None
		if s is None:
			return ""
		S = Standby
		if S is None:
			from Screens import Standby as S
		f = stare_receptor
		if f is None:
			from Components.HdsAlimentare import stareReceptor as f
		st = f(s, Standby=S)
		if st.get("intrebare_pe_tv"):
			return "intrebare"
		if st.get("inregistrari") or st.get("curand"):
			return "inregistrare"
		if st.get("lucrari"):
			return "lucrare"
		s.openWithCallback(la_refuz, S.TryQuitMainloop, _codRepornire(s, st.get("inregistrari", 0)))
		return "pornita"
	return reporneste


def rute(baza, resource, sesiune=None, A=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	intoarce sesiunea enigma2 (pentru repornire)."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ActiuneResource(baza):
		schimbaCeva = True
		functie = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.functie(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	def actiune(f):
		r = ActiuneResource()
		r.functie = f
		return r

	class PaginaResource(resource.Resource):
		"""GET /actualizari: pagina "Actualizare software"."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"actualizari": StareResource(),
		b"actualizari-cauta": actiune(lambda arg: cauta(A)),
		b"actualizari-instaleaza": actiune(lambda arg: instaleaza(arg, A)),
		b"actualizari-zilnic": actiune(lambda arg: zilnic(arg, A)),
		b"actualizari-reporneste": actiune(lambda arg: reporneste(sesiune, A)),
		b"actualizari-rapid": actiune(lambda arg: rapid(sesiune, A)),
	}
	return api, PaginaResource()


def _limba():
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	cod = "".join(ch for ch in cod if "a" <= ch <= "z")[:3]
	return cod or "ro"


def pagina(request):
	"""Aceeasi poarta ca /paznic."""
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
	return pagina_text(P._STIL_COMUN, config_pagina, _limba()).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def _e(text):
	return _escape(u"%s" % (text or ""), True)


def texte():
	"""Textele scrise de scriptul paginii, traduse pe receptor"""
	return {
		"citeste": _t("Se citește starea..."),
		"nuRaspunde": _t("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		"imaginea": _t("Versiunea instalată"),
		"baza": _t("Imaginea de bază"),
		"necunoscuta": _t("necunoscută"),
		"canal": _t("Canalul"),
		"canale": {"proba": _t("Probă (numai receptoarele HD Satelit)"), "public": _t("Public"),
			"proba-fara-cheie": _t("Probă, fără parolă"), "": _t("Fără sursă de actualizări")},
		"peServer": _t("Pe server"),
		"nicio": _t("nicio actualizare"),
		"deInstalat": _t("De instalat"),
		"pachete": _t("%d pachete, %s"),
		"deLaLa": _t("de la %s la %s"),
		"nepotrivite": _t("Lista pachetelor și starea de pe server nu sunt din aceeași publicare. Caută din nou."),
		"zilnic": _t("Verificare zilnică"),
		"pornita": _t("Pornită"),
		"oprita": _t("Oprită"),
		"intrebare": _t("Instalezi versiunea %s? La sfârșit interfața trebuie repornită."),
		"gata": _t("Pachete gata: %d din %d."),
		"repornesteNota": _t("Repornește interfața ca să folosești actualizarea."),
		# actualizarea rapida: intrebarea, pasii si ce se vede dupa repornire
		"rapidIntrebare": _t("Pornești actualizarea rapidă? Dacă există o actualizare, se instalează, apoi interfața se "
			"repornește singură."),
		"pasCaut": _t("Caut actualizarea"),
		"pasInstalez": _t("Instalez versiunea %s"),
		"pasInstalezFara": _t("Instalez actualizarea"),
		"pasRepornesc": _t("Repornesc interfața"),
		"astept": _t("Interfața repornește. Aștept să revină..."),
		"actualizat": _t("Actualizat la %s."),
		"altaVersiune": _t("Interfața a repornit cu versiunea %s, nu cu %s."),
		"nuRevine": _t("Interfața nu a revenit în 4 minute. Verifică receptorul."),
		"intrebareTv": _t("Actualizarea s-a instalat. Pe televizor se așteaptă un răspuns la întrebarea de repornire."),
		"nerepornita": _t("Interfața nu s-a repornit. Apasă Repornește interfața."),
	}


def pagina_text(stil, config_pagina, limba="ro"):
	valori = {
		"__STIL_COMUN__": stil,
		"__LIMBA__": _e(limba or "ro"),
		"__CONFIG__": config_pagina,
		"__TEXTE__": json.dumps(texte(), ensure_ascii=False).replace("</", "<\\/"),
		"__T_TITLU__": _e(_t("Actualizare software")),
		"__T_NOTA__": _e(_t("Actualizările vin ca pachete de pe stb.hdsatelit.com. Aceeași pagină pe televizor:")),
		"__DRUM_MENIU__": _drumMeniu("hds_actualizari"),
		"__T_CAUTA__": _e(_t("Caută din nou")),
		"__T_RAPID__": _e(_t("Actualizează rapid")),
		"__T_RAPID_NOTA__": _e(_t("Un singur clic caută actualizarea, o instalează dacă există și repornește interfața.")),
		"__T_INSTALEAZA__": _e(_t("Instalează")),
		"__T_REPORNESTE__": _e(_t("Repornește interfața")),
		"__T_ZILNIC_PORNESTE__": _e(_t("Pornește verificarea zilnică")),
		"__T_ZILNIC_OPRESTE__": _e(_t("Oprește verificarea zilnică")),
		"__T_ZILNIC_NOTA__": _e(_t("Verificarea zilnică doar anunță pe televizor o actualizare nouă. Nu instalează nimic "
			"singură.")),
		"__T_JURNAL__": _e(_t("Jurnalul operației")),
	}
	return re.sub(r"__[A-Z_]+__", lambda m: valori.get(m.group(0), m.group(0)), _traducePagina(PAGINA))


PAGINA = u"""<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.3rem;margin:0 0 12px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px 16px;margin:0 0 10px;}
  .card.bun{border-color:var(--verde);}
  .card.rau{border-color:#f5b83d;}
  .rand{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand .e{color:var(--text-slab);}
  .rand .v{text-align:right;overflow-wrap:anywhere;}
  .rand.pachet .e,.rand.pachet .v{font-size:.88rem;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 10px;line-height:1.45;}
  .text{line-height:1.5;white-space:pre-line;overflow-wrap:anywhere;margin:0;}
  .text:empty{display:none;}
  .text:not(:empty) + #noutati:not(:empty){margin-top:12px;}
  #noutati .versiune{font-weight:600;margin:14px 0 6px;}
  #noutati .versiune:first-child{margin-top:0;}
  #noutati ul{margin:0;padding-left:22px;line-height:1.5;}
  #noutati li{margin:0 0 4px;overflow-wrap:anywhere;}
  .bara{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 10px;}
  .bara button{min-height:40px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  .bara button.principal{background:var(--verde);border-color:var(--verde);}
  .ascuns{display:none;}
  .mesaj{margin:6px 0 10px;line-height:1.45;}
  .pasi{list-style:none;margin:0;padding:0;}
  .pasi:empty{display:none;}
  .pasi li{display:flex;gap:10px;align-items:flex-start;padding:5px 0;color:var(--text-slab);line-height:1.4;}
  .pasi li::before{content:"";flex:0 0 20px;height:20px;box-sizing:border-box;border-radius:50%;border:2px solid var(--bordura);font-size:12px;line-height:16px;text-align:center;color:#fff;}
  .pasi li.acum,.pasi li.facut,.pasi li.rau{color:var(--text);}
  .pasi li.acum{font-weight:600;}
  .pasi li.acum::before{border-color:var(--verde);border-right-color:transparent;animation:roteste 1s linear infinite;}
  .pasi li.facut::before{content:"\\2713";background:var(--verde);border-color:var(--verde);}
  .pasi li.rau::before{content:"\\00d7";background:#c0392b;border-color:#c0392b;font-size:15px;}
  .pasi .detaliu{display:block;font-weight:400;color:var(--text-slab);font-size:.85rem;overflow-wrap:anywhere;}
  .pasi:not(:empty) + #rapidText:not(:empty){margin-top:8px;}
  #rapidText{font-weight:600;}
  @keyframes roteste{to{transform:rotate(360deg);}}
  @media (prefers-reduced-motion:reduce){.pasi li.acum::before{animation:none;}}
  pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.78rem;color:var(--text-slab);margin:0;}
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="nota">__T_NOTA__ __DRUM_MENIU__.</p>
<p class="mesaj" id="mesaj"></p>
<section class="card ascuns" id="rapidCard" aria-live="polite"><ol class="pasi" id="pasi"></ol><p class="text" id="rapidText"></p></section>
<section class="card" id="randuri"></section>
<section class="card ascuns" id="detalii"><p class="text" id="text"></p><div id="noutati"></div></section>
<div class="bara">
  <button id="rapid" type="button" class="principal ascuns">__T_RAPID__</button>
  <button id="cauta" type="button">__T_CAUTA__</button>
</div>
<p class="nota ascuns" id="rapidNota">__T_RAPID_NOTA__</p>
<div class="bara">
  <button id="instaleaza" type="button" class="principal ascuns">__T_INSTALEAZA__</button>
  <button id="reporneste" type="button" class="principal ascuns">__T_REPORNESTE__</button>
  <button id="zilnic" type="button"></button>
</div>
<p class="nota">__T_ZILNIC_NOTA__</p>
<section class="card"><p class="nota">__T_JURNAL__</p><pre id="jurnal"></pre></section>
</main>
<script>
var CFG = __CONFIG__;
var T = __TEXTE__;
var ULTIMA = null;
var CEAS = null;
var RAPID = null;
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
    return r.json();
  });
}
function element(tip, clasa, text){
  var e = document.createElement(tip); if(clasa){ e.className = clasa; } if(text){ e.textContent = text; } return e;
}
function marime(o){
  if(!o){ return "?"; }
  if(o < 1024 * 1024){ return Math.max(1, Math.round(o / 1024)) + " KB"; }
  return (o / 1048576).toFixed(1).replace(".", ",") + " MB";
}
function rand(r, e, v, clasa){
  var d = element("div", "rand" + (clasa ? " " + clasa : ""));
  d.appendChild(element("span", "e", e)); d.appendChild(element("span", "v", v)); r.appendChild(d);
}
// Actualizarea rapida cum o vede pagina. R tine minte de la apasare versiunea de dinainte (inainte), cea gasita pe
// server (tinta), pasul (1 caut, 2 instalez, 3 repornesc), cand a inceput repornirea si cand a cazut prima cerere.
// d = raspunsul lui /api/actualizari, sau null cand cererea a cazut (interfata oprita cat reporneste). Intoarce pasul
// (4 = toti trei facuti, 0 = fara pasi), daca el a mers prost (rau), textul de sub pasi, detaliul pasului de acum,
// peste cate ms se citeste din nou (0 = gata) si daca s-a terminat bine (bun).
function pasRapid(R, d, acum){
  if(!d){
    if(R.pas === 3){
      R.cazut = R.cazut || acum;
      if(acum - R.cazut > 240000){ return {pas: 3, rau: true, text: T.nuRevine, peste: 0}; }
      return {pas: 3, text: T.astept, peste: 3000};
    }
    R.tacere = R.tacere || acum;
    if(acum - R.tacere > 240000){ return {pas: R.pas, rau: true, text: T.nuRaspunde, peste: 0}; }
    return {pas: R.pas, text: T.nuRaspunde, peste: 3000};
  }
  R.tacere = 0;
  var x = d.rezultat || {}, s = x.server || {};
  // tinta vine din cautarea de acum: cat se cauta, rezultatul e inca al cautarii de dinainte
  if(d.rapid && s.versiune && d.faza !== "caut"){ R.tinta = s.versiune; }
  // interfata pornita din nou: alt proces, fara modul rapid si fara repornirea ceruta
  if(R.pas >= 2 && !d.rapid && !d.repornire && (R.cazut || d.imagine_text !== R.inainte || x.stare === "necautat")){
    var v = d.imagine_text || "";
    if(R.tinta && v !== R.tinta){ return {pas: 3, rau: true, text: T.altaVersiune.replace("%s", v || "?").replace("%s", R.tinta), peste: 0}; }
    return {pas: 4, bun: true, text: T.actualizat.replace("%s", v), peste: 0};
  }
  if(d.rapid){
    var p = d.progres || [];
    if(d.faza === "caut"){ R.pas = 1; return {pas: 1, detaliu: d.pas || "", peste: 1500}; }
    if(d.faza === "instalez"){
      R.pas = 2;
      return {pas: 2, detaliu: (p[1] ? T.gata.replace("%d", p[0]).replace("%d", p[1]) + " " : "") + (d.pas || ""), peste: 1500};
    }
    R.pas = 3;
    if(d.rapid_pas === "repornesc"){
      R.repornire = R.repornire || acum;
      // un minut fara sa cada interfata: o intrebare pe televizor, sau repornirea nu s-a facut
      // (butonul Reporneste interfata se arata din nou: textul trimite la el)
      if(acum - R.repornire > 60000){ return {pas: 3, text: d.intrebare_pe_tv ? T.intrebareTv : T.nerepornita, peste: 5000, reporneste: true}; }
      return {pas: 3, text: T.astept, peste: 1500};
    }
    // asteapta inregistrarea, lucrarea din fundal sau raspunsul de pe televizor: textul vine de pe receptor
    R.repornire = 0;
    return {pas: 3, text: d.mesaj || "", peste: 5000};
  }
  // modul rapid s-a oprit pe receptor
  if(R.pas <= 1 && x.stare === "la-zi"){ return {pas: 0, bun: true, text: d.text_stare || "", peste: 0}; }
  if(R.pas === 3 || x.stare === "instalata"){
    return {pas: 3, rau: true, text: d.rapid_pas === "refuzata" ? (d.mesaj || "") : T.nerepornita, peste: 0};
  }
  var instalare = R.pas === 2 || ["disponibila", "imagine-noua", "nesemnata", "eroare-instalare"].indexOf(x.stare) !== -1;
  return {pas: instalare ? 2 : 1, rau: true, text: "", peste: 0};
}
function arataRapid(r){
  var l = $("pasi"); l.textContent = "";
  if(r.pas){
    [T.pasCaut, RAPID.tinta ? T.pasInstalez.replace("%s", RAPID.tinta) : T.pasInstalezFara, T.pasRepornesc].forEach(function(t, i){
      var n = i + 1;
      var li = element("li", n < r.pas ? "facut" : (n === r.pas ? (r.rau ? "rau" : "acum") : ""));
      var e = element("div", "", t);
      if(n === r.pas && r.detaliu){ e.appendChild(element("span", "detaliu", r.detaliu)); }
      li.appendChild(e); l.appendChild(li);
    });
  }
  $("rapidText").textContent = r.text || "";
  $("rapidCard").className = "card" + (r.bun ? " bun" : (r.rau ? " rau" : ""));
}
function arata(d){
  ULTIMA = d;
  if(d.rapid && !RAPID){ RAPID = {inainte: d.imagine_text || "", pas: 1}; }
  var rr = RAPID ? pasRapid(RAPID, d, Date.now()) : null;
  var r = $("randuri"); r.textContent = "";
  var i = d.imagine || {}, x = d.rezultat || {}, s = x.server || {};
  // omul vede numai versiunea; imaginea de baza (de pe stick) numai la avertizarea de imagine noua
  rand(r, T.imaginea, d.imagine_text || T.necunoscuta);
  if(x.stare === "imagine-noua" && i.baza){ rand(r, T.baza, i.baza, "pachet"); }
  rand(r, T.canal, T.canale[d.canal || ""] || T.canale[""]);
  if(["la-zi", "disponibila", "imagine-noua", "instalata", "eroare-instalare"].indexOf(x.stare) !== -1){
    // "actualizare" e numarul intern; 0 = feedul bazei fara pachete
    rand(r, T.peServer, s.actualizare ? (s.versiune || "?") + " (" + (s.data || "?") + ")" : T.nicio);
  }
  var p = x.pachete || [];
  if(p.length && (x.stare === "disponibila" || x.stare === "imagine-noua")){
    rand(r, T.deInstalat, (d.text_pachete || T.pachete.replace("%d", p.length)).replace("%s", marime(x.marime)));
    p.forEach(function(q){ rand(r, q.titlu, T.deLaLa.replace("%s", q.de_la_scurt).replace("%s", q.la_scurt), "pachet"); });
  }
  rand(r, T.zilnic, d.zilnic ? T.pornita : T.oprita);
  var jos = [];
  if(d.mesaj){ jos.push(d.mesaj); }
  if(x.stare === "imagine-noua"){ jos = jos.concat(d.texte_motive || []); jos.push(d.text_imagine_noua); }
  else if(x.stare === "disponibila" || x.stare === "instalata"){
    if((x.nepotrivite || []).length){ jos.push(T.nepotrivite); }
  } else if(d.text_stare){ jos.push(d.text_stare); if(x.eroare){ jos.push(x.eroare); } }
  // ce spune cardul actualizarii rapide nu se mai scrie si aici (nici mesajul receptorului cat merge, nici starea
  // "necautat" dupa repornire)
  if(rr){ jos = jos.filter(function(t){ return t !== rr.text && !(d.rapid && t === d.mesaj) && !(x.stare === "necautat" && t === d.text_stare); }); }
  $("text").textContent = jos.filter(Boolean).join("\\n");
  // ce e nou, grupat pe versiuni: de la cea instalata pana la cea de pe server, ca pe televizor
  var n = $("noutati"); n.textContent = "";
  if(x.stare === "disponibila" || x.stare === "instalata"){
    (d.noutati || []).forEach(function(g){
      n.appendChild(element("p", "versiune", g.titlu));
      var l = element("ul");
      (g.randuri || []).forEach(function(t){ l.appendChild(element("li", "", t)); });
      n.appendChild(l);
    });
  }
  $("detalii").className = "card" + (jos.length || n.childNodes.length ? "" : " ascuns") + (x.stare === "imagine-noua" ? " rau" : (x.stare === "disponibila" ? " bun" : ""));
  var lucreaza = d.faza !== "liber";
  var stareText = "";
  if(lucreaza){
    stareText = d.pas || "";
    if(d.faza === "instalez" && d.progres && d.progres[1]){ stareText = T.gata.replace("%d", d.progres[0]).replace("%d", d.progres[1]) + " " + stareText; }
  } else if(d.repornire){ stareText = T.repornesteNota; }
  $("mesaj").textContent = rr ? "" : stareText;
  if(rr){ arataRapid(rr); } else { $("rapidCard").className = "card ascuns"; }
  // butonul de actualizare rapida si nota lui, numai cand se poate porni
  var rapid = !lucreaza && !d.repornire && !d.rapid;
  $("rapid").className = "principal" + (rapid ? "" : " ascuns");
  $("rapidNota").className = "nota" + (rapid ? "" : " ascuns");
  $("instaleaza").className = "principal" + (!lucreaza && !d.repornire && x.poate_instala ? "" : " ascuns");
  // cat interfata se reporneste singura, nu; cat asteapta o inregistrare, da (repornirea de acum, cu intrebarea de pe
  // televizor)
  $("reporneste").className = "principal" + (d.repornire && !lucreaza && !(d.rapid && d.rapid_pas === "repornesc" && !(rr && rr.reporneste)) ? "" : " ascuns");
  $("cauta").disabled = lucreaza || d.repornire;
  $("zilnic").textContent = d.zilnic ? "__T_ZILNIC_OPRESTE__" : "__T_ZILNIC_PORNESTE__";
  $("jurnal").textContent = (d.jurnal || []).join("\\n");
  if(CEAS){ clearTimeout(CEAS); CEAS = null; }
  var peste = rr && rr.peste ? rr.peste : (lucreaza ? 1500 : 0);
  if(peste){ CEAS = setTimeout(citeste, peste); }
}
function citeste(){
  cerere("/api/actualizari").then(function(d){
    if(!d.result){ $("mesaj").textContent = d.message || T.nuRaspunde; return; }
    arata(d);
  }).catch(function(){
    if(!RAPID){ $("mesaj").textContent = T.nuRaspunde; return; }
    // cat reporneste interfata cererile cad: se incearca din nou, cel mult 4 minute
    var r = pasRapid(RAPID, null, Date.now());
    arataRapid(r);
    if(CEAS){ clearTimeout(CEAS); CEAS = null; }
    if(r.peste){ CEAS = setTimeout(citeste, r.peste); }
  });
}
function trimite(cale, date){
  cerere(cale, "POST", date).then(function(d){
    if(d.rezultat){ arata(d); }
    if(d.message){ $("mesaj").textContent = d.message; }
  }).catch(function(){ $("mesaj").textContent = T.nuRaspunde; });
}
$("rapid").addEventListener("click", function(){
  if(!confirm(T.rapidIntrebare)){ return; }
  var inainte = (ULTIMA && ULTIMA.imagine_text) || "";
  cerere("/api/actualizari-rapid", "POST", new URLSearchParams()).then(function(d){
    RAPID = d.result ? {inainte: d.imagine_text || inainte, pas: 1} : null;
    if(d.rezultat){ arata(d); }
    if(d.message){ $("mesaj").textContent = d.message; }
  }).catch(function(){ $("mesaj").textContent = T.nuRaspunde; });
});
$("cauta").addEventListener("click", function(){ RAPID = null; trimite("/api/actualizari-cauta", new URLSearchParams()); });
$("instaleaza").addEventListener("click", function(){
  var s = (ULTIMA && ULTIMA.rezultat && ULTIMA.rezultat.server) || {};
  if(!confirm(T.intrebare.replace("%s", s.versiune || ""))){ return; }
  RAPID = null;
  var q = new URLSearchParams(); q.set("actualizare", String(s.actualizare));
  trimite("/api/actualizari-instaleaza", q);
});
$("reporneste").addEventListener("click", function(){ trimite("/api/actualizari-reporneste", new URLSearchParams()); });
$("zilnic").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("zilnic", ULTIMA && ULTIMA.zilnic ? "0" : "1");
  trimite("/api/actualizari-zilnic", q);
});
$("mesaj").textContent = T.citeste;
citeste();
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
	),
	"js": (
		N_("browser deconectat"),
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
