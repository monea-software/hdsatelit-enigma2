# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# vpn_web.py: "VPN" in interfata web (HdsWebControl), perechea ecranului de pe televizor (Screens/HdsVpn.py, Setari >
# Retea & Internet > VPN). Aceleasi date, aceleasi texte si aceleasi comenzi, din Components/HdsVpn.py: starea si
# adresa vazuta pe internet, pornirea si oprirea, furnizorul (HMA, OpenVPN, WireGuard), serverul, numele si parola
# (scrise aici, niciodata aratate inapoi), importul fisierelor din telefon sau de pe stick, ce trece prin VPN (tot sau
# numai IPTV si adresele scrise aici), oprirea totala, pornirea odata cu receptorul, instalarea programelor si
# stergerile. Legat din meniu_pagini_web.MODULE (plugin.py nu se schimba). Numai cu programele VPN in imagine
# (SystemInfo["HdsVpn"], ca intrarea din meniu): altfel modulul nu da nicio ruta.
#
# Cine are voie: poarta comuna a HdsJsonResource lasa sa treaca reteaua locala cu ?token= sau cu cookie-ul
# browserului. Starea (GET) o vede oricine trece de poarta: nu are secrete. Orice schimbare (POST) cere in plus un
# browser conectat CU CODUL de pe televizor (nivel "asociat"): numele si parola contului, fisierele cu chei si
# pornirea VPN-ului nu se dau unui browser intrat fara cod si nici cheii pentru scripturi.
#   GET  /api/vpn                         starea (fara nume, parola sau chei)
#   POST /api/vpn-porneste, /api/vpn-opreste, /api/vpn-ip, /api/vpn-stick
#   POST /api/vpn-setari                  furnizor=, profil=, mod=tot|ales, oprire_totala=0|1, la_pornire=0|1,
#                                         iptv=0|1, adrese= (numai cheile date se schimba)
#   POST /api/vpn-cont  (corp: nume=, parola=)   /api/vpn-cont-sterge?confirmat=1
#   POST /api/vpn-importa (corp: nume=, text=, de mai multe ori: fisierele alese in telefon, cel mult 60 KB odata)
#   POST /api/vpn-sterge?id=..&confirmat=1, /api/vpn-sterge-toate?confirmat=1, /api/vpn-instaleaza?confirmat=1
#   GET  /vpn                             pagina
# Etichetele paginii si mesajele din script trec prin _t() (ETICHETE, TEXTE_JS); lang e limba receptorului.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 si citesc numai fisiere mici (importul unui fisier se
# verifica pe loc, e text mic); ce porneste un program merge pe firul lucrarilor din Components/HdsVpn.py. Fisierul nu
# importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor.

MAX_TEXT_FISIER = 61440
MAX_FISIERE = 40
CHEI_SETARI = ("furnizor", "profil", "mod", "oprire_totala", "la_pornire", "iptv", "adrese")


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la afisare cu _t()."""
	return text


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _v(V=None):
	if V is not None:
		return V
	from Components import HdsVpn
	return HdsVpn


def disponibil(V=None):
	"""True cand programele VPN sunt in imagine (SystemInfo["HdsVpn"], aceeasi hotarare ca intrarea din menu.xml;
	cu modulul dat, V.disponibil()). Fara ele pagina nu exista: nici starea, nici instalarea."""
	if V is not None:
		return bool(V.disponibil())
	try:
		from Components.SystemInfo import SystemInfo
	except Exception as eroare:
		print("[HdsWebControl] vpn: %r" % (eroare,))
		return False
	return bool(SystemInfo.get("HdsVpn"))


def _lista(request, nume):
	valori = (getattr(request, "args", None) or {}).get(nume.encode("ascii")) or []
	rez = []
	for v in valori:
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez.append(str(v))
	return rez


def _arg(request, nume, maxim=200):
	v = _lista(request, nume)
	return v[0][:maxim] if v else ""


def _cuJeton(request):
	return b"token" in (getattr(request, "args", None) or {})


def _sesiunePlugin(request):
	from . import plugin as P
	return P._sesiuneDinCerere(request)


def nivel(request, sesiune_cerere=None):
	""""jeton" (?token=), "asociat" (browser conectat cu codul de pe televizor) sau "liber"."""
	if _cuJeton(request):
		return "jeton"
	_secret, browser = (sesiune_cerere or _sesiunePlugin)(request)
	if browser is not None and not browser.get("liber"):
		return "asociat"
	return "liber"


NEASOCIAT = N_("VPN-ul se schimbă numai dintr-un browser conectat cu codul de pe televizor.")


def stare(V=None, nivel_cerere="asociat"):
	"""Starea pentru pagina: ce arata ecranul de pe televizor, cu textele lui, fara secrete."""
	V = _v(V)
	s = V.stare()
	l = s["lucrare"]
	return dict(s, result=True, nivel=nivel_cerere, asociat=nivel_cerere == "asociat",
		text_legatura=V.textLegatura(s),
		culoare={"conectat": "bun", "se_conecteaza": "chihlimbar", "blocat": "rau", "eroare": "rau"}.get(s["legatura"],
			"slab"),
		detalii=V.textDetalii(s),
		furnizori=[[f, V.textFurnizor(f)] for f in V.FURNIZORI],
		moduri=[[m, V.textMod(m)] for m in V.MODURI],
		cum_iei=V.textCumIeiFisierele(s["furnizor"]),
		explicatie_mod=V.textExplicatieMod(s),
		text_cont=V.textCont(s["furnizor"]),
		text_cont_nota=V.textExplicatieCont(s["furnizor"]),
		text_programe=V.textProgrameLipsa(s["fel"]) if s["lipsesc"] else "",
		text_lucreaza=V.textLucrare(l["lucreaza"]) if l["lucreaza"] else "")


def _pornit(numar, mesaj):
	if numar is None:
		return {"result": False, "message": _t("Așteaptă să se termine ce ai pornit înainte (pe televizor sau aici).")}
	return {"result": True, "lucrare": numar, "message": mesaj}


def porneste(request, V=None):
	V = _v(V)
	return _pornit(V.pornesteVpn(), V.textLucrare(V.LUCRARE_PORNESTE))


def opreste(request, V=None):
	V = _v(V)
	return _pornit(V.opresteVpn(), V.textLucrare(V.LUCRARE_OPRESTE))


def ip(request, V=None):
	V = _v(V)
	return _pornit(V.pornesteIp(), V.textLucrare(V.LUCRARE_IP))


def stick(request, V=None):
	V = _v(V)
	return _pornit(V.pornesteStick(), V.textLucrare(V.LUCRARE_STICK))


def instaleaza(request, V=None):
	V = _v(V)
	if _arg(request, "confirmat") != "1":
		return {"result": False, "message": _t("Confirmă instalarea programelor VPN.")}
	return _pornit(V.pornesteInstalarea(V.felFurnizor(V.setari()["furnizor"])), V.textLucrare(V.LUCRARE_INSTALEAZA))


def setari(request, V=None):
	V = _v(V)
	args = getattr(request, "args", None) or {}
	schimbari = {}
	for k in CHEI_SETARI:
		if k.encode("ascii") not in args:
			continue
		v = _arg(request, k, 4096)
		if k in ("oprire_totala", "la_pornire", "iptv"):
			if v not in ("0", "1"):
				return {"result": False, "message": _t("Alege da sau nu.")}
			schimbari[k] = v == "1"
		elif k == "adrese":
			bune, rele = V.adreseDinText(v)
			if rele:
				return {"result": False, "message": _t("Adrese care nu sunt bune: %s") % ", ".join(rele[:5])}
			schimbari[k] = bune
		else:
			schimbari[k] = v
	if not schimbari:
		return {"result": False, "message": _t("Nimic de schimbat.")}
	reusit, mesaj, numar = V.schimba(**schimbari)
	rez = {"result": reusit, "message": mesaj}
	if numar is not None:
		rez["lucrare"] = numar
	return rez


def cont(request, V=None):
	V = _v(V)
	nume = _arg(request, "nume", V.MAX_CAMP_CONT + 1)
	parola = _arg(request, "parola", V.MAX_CAMP_CONT + 1)
	reusit, mesaj = V.salveazaCont(nume, parola)
	return {"result": reusit, "message": mesaj}


def contSterge(request, V=None):
	V = _v(V)
	if _arg(request, "confirmat") != "1":
		return {"result": False, "message": _t("Confirmă ștergerea.")}
	reusit, mesaj = V.stergeCont()
	return {"result": reusit, "message": mesaj}


def importa(request, V=None):
	V = _v(V)
	nume = _lista(request, "nume")
	texte = _lista(request, "text")
	if not nume or len(nume) != len(texte):
		return {"result": False, "message": _t("Alege întâi fișierele.")}
	if len(nume) > MAX_FISIERE or sum(len(t) for t in texte) > MAX_TEXT_FISIER:
		return {"result": False, "message": _t("Prea multe fișiere odată.")}
	fisiere = []
	for n, t in zip(nume, texte):
		n = n.replace("\\", "/").rsplit("/", 1)[-1][:120]
		if n.lower().endswith(".zip"):
			return {"result": False, "message": _t("Arhiva .zip se despachetează întâi sau se pune pe stick.")}
		fisiere.append((n, t.encode("utf-8")))
	reusit, mesaj, detalii = V.importa(fisiere, V.setari()["furnizor"])
	return {"result": reusit, "message": mesaj, "detalii": detalii}


def sterge(request, V=None):
	V = _v(V)
	if _arg(request, "confirmat") != "1":
		return {"result": False, "message": _t("Confirmă ștergerea.")}
	reusit, mesaj = V.stergeProfil(_arg(request, "id", 16))
	return {"result": reusit, "message": mesaj}


def stergeToate(request, V=None):
	V = _v(V)
	if _arg(request, "confirmat") != "1":
		return {"result": False, "message": _t("Confirmă ștergerea.")}
	reusit, mesaj = V.stergeGrup(V.setari()["furnizor"])
	return {"result": reusit, "message": mesaj}


def rute(baza, resource, V=None, sesiune_cerere=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}); `baza` e HdsJsonResource din plugin.py. Fara
	programele VPN in imagine: ({}, {})."""
	if not disponibil(V):
		return {}, {}

	def neasociat(request):
		if nivel(request, sesiune_cerere) == "asociat":
			return None
		return {"result": False, "trebuie_cod": True, "message": _t(NEASOCIAT)}

	class StareResource(baza):
		"""GET /api/vpn: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(V, nivel(request, sesiune_cerere)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Comanda(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			refuz = neasociat(request)
			if refuz is not None:
				return self._raspunde(request, refuz, 403)
			try:
				return self._raspunde(request, type(self).lucru(request, V))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # poarta cere POST din browser; cu ?token= raspunsul e refuzul

	def comanda(functie):
		return type("Comanda", (_Comanda,), {"lucru": staticmethod(functie)})()

	class PaginaResource(resource.Resource):
		"""GET /vpn: pagina VPN."""
		isLeaf = True

		def render_GET(self, request):
			from .meniu_comun_web import pagina as poarta
			return poarta(request, pagina_text)

	api = {
		b"vpn": StareResource(),
		b"vpn-porneste": comanda(porneste),
		b"vpn-opreste": comanda(opreste),
		b"vpn-ip": comanda(ip),
		b"vpn-stick": comanda(stick),
		b"vpn-setari": comanda(setari),
		b"vpn-cont": comanda(cont),
		b"vpn-cont-sterge": comanda(contSterge),
		b"vpn-importa": comanda(importa),
		b"vpn-sterge": comanda(sterge),
		b"vpn-sterge-toate": comanda(stergeToate),
		b"vpn-instaleaza": comanda(instaleaza),
	}
	return api, {b"vpn": PaginaResource()}


def _limba():
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	return cod if (2 <= len(cod) <= 3 and cod.isalpha()) else "ro"


def _json(obiect):
	import json
	return json.dumps(obiect, ensure_ascii=False).replace("</", "<\\/")


ETICHETE = {
	"TITLU": N_("VPN"),
	"INCARCARE": N_("Se citește starea..."),
	"CONECTARE": N_("Conectează browserul cu codul"),
	"CONECTARE_TEXT": N_("VPN-ul se schimbă numai dintr-un browser conectat cu codul de pe televizor. Așa, cine e doar în "
		"rețeaua ta de acasă nu îți poate afla contul și nu poate porni sau opri VPN-ul."),
	"ARATA_COD": N_("Arată codul pe televizor"),
	"COD": N_("Codul de pe televizor"),
	"CONECTEAZA": N_("Conectează"),
	"STARE": N_("Starea"),
	"PORNESTE": N_("Pornește"),
	"VERIFICA_IP": N_("Verifică adresa văzută pe internet"),
	"PROGRAME": N_("Programele VPN"),
	"INSTALEAZA": N_("Instalează programele VPN"),
	"FURNIZOR": N_("Furnizorul și serverul"),
	"ETICHETA_FURNIZOR": N_("Furnizorul"),
	"ETICHETA_SERVER": N_("Serverul"),
	"STERGE_SERVER": N_("Șterge serverul ales"),
	"STERGE_TOATE": N_("Șterge toate serverele acestui furnizor"),
	"IMPORT": N_("Fișierele furnizorului"),
	"ALEGE_FISIERE": N_("Alege fișierele (.ovpn, .conf și certificatele lor)"),
	"TRIMITE": N_("Trimite fișierele"),
	"STICK": N_("Importă fișierele de pe stick"),
	"STICK_NOTA": N_("De pe stick: dosarul hdsatelit/vpn, cu fișierele .ovpn sau .conf ori cu arhiva .zip a furnizorului."),
	"CONT": N_("Numele și parola contului"),
	"NUME": N_("Numele"),
	"PAROLA": N_("Parola"),
	"SALVEAZA": N_("Salvează"),
	"STERGE_CONT": N_("Șterge numele și parola"),
	"CONT_NOTA": N_("Sunt cele ale contului la furnizor (la HMA, cele ale contului HMA). După salvare nu se mai arată "
		"nicăieri, nici aici, nici pe televizor."),
	"TRAFIC": N_("Ce trece prin VPN"),
	"IPTV": N_("Sursele IPTV din liste"),
	"ADRESE": N_("Alte adrese (nume de situri sau adrese IP, câte una pe rând)"),
	"SALVEAZA_ADRESE": N_("Salvează adresele"),
	"OPTIUNI": N_("Opțiuni"),
	"OPRIRE_TOTALA": N_("Oprire totală la căderea VPN-ului"),
	"OPRIRE_NOTA": N_("Dacă VPN-ul cade, receptorul nu mai iese în internet până revine. Rețeaua din casă merge."),
	"LA_PORNIRE": N_("Pornește odată cu receptorul"),
	"LA_PORNIRE_NOTA": N_("VPN-ul pornește singur după fiecare pornire a receptorului, dacă era pornit."),
}

NOTA_TV = N_("Aceleași lucruri sunt pe televizor, în %s.")

TEXTE_JS = {
	"neasteptat": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"necitit": N_("Receptorul nu a putut citi starea."),
	"nuRaspunde": N_("Receptorul nu răspunde."),
	"seTrimite": N_("Se trimite..."),
	"niciunServer": N_("niciunul (importă întâi fișierele)"),
	"alegeFisiere": N_("Alege întâi fișierele."),
	"zip": N_("Arhiva .zip se despachetează întâi sau se pune pe stick."),
	"prea": N_("Fișierul %s este prea mare."),
	"scrieNumele": N_("Scrie întâi numele și parola contului."),
	"intrebareInstaleaza": N_("Instalezi programele VPN din feedul de extensii HD Satelit? Durează câteva minute."),
	"intrebareSterge": N_("Ștergi serverul %s?"),
	"intrebareStergeToate": N_("Ștergi toate serverele acestui furnizor (%s)?"),
	"intrebareStergeCont": N_("Ștergi numele și parola de pe receptor?"),
	"salvate": N_("salvate"),
	"lipsesc": N_("lipsesc"),
	"seCereCodul": N_("Se cere codul..."),
	"codulPeTv": N_("Codul e pe televizor."),
	"scrieCodul": N_("Scrie codul aici, apoi apasă Conectează."),
	"codNecerut": N_("Codul nu s-a putut cere."),
	"codSase": N_("Codul are 6 cifre."),
	"conectat": N_("Conectat."),
	"codGresit": N_("Codul nu a mers."),
	"numaiStarea": N_("Cu cheia pentru scripturi pagina arată numai starea."),
	"porneste": N_("Pornește"),
	"opreste": N_("Oprește"),
}


def pagina_text(stil, config_pagina):
	import html
	from . import meniu_comun_web as MC
	text = _traducePagina(PAGINA)
	for cheie, eticheta in ETICHETE.items():
		text = text.replace("__T_%s__" % cheie, html.escape(_t(eticheta), quote=True))
	nota = html.escape(_t(NOTA_TV), quote=False)
	nota = nota.replace("%s", MC.drumHtml("hds_vpn"), 1) if "%s" in nota else nota
	text = text.replace("__LIMBA__", _limba()).replace("__NOTA_TV__", nota).replace("__TEXTE_JS__",
		_json(dict((k, _t(v)) for k, v in TEXTE_JS.items())))
	return MC.sablon(text, stil, config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="same-origin">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .stare-mare{font-size:1.6rem;font-weight:600;margin:2px 0 8px;}
  .stare-mare.bun{color:#7ddc8a;} .stare-mare.chihlimbar{color:#f5b83d;} .stare-mare.rau{color:#ff8a7a;} .stare-mare.slab{color:var(--text-slab);}
  .detalii p{margin:0 0 4px;line-height:1.45;}
  .rand > *{min-width:0;}
  .rand select, .rand input[type=text], .rand input[type=password], .rand input[type=file]{width:100%;box-sizing:border-box;}
  .rand input[type=file]{max-width:100%;overflow:hidden;}
  textarea{width:100%;box-sizing:border-box;min-height:88px;}
  .bifa{display:flex;gap:10px;align-items:center;padding:8px 0;}
  #cod{width:9em;font:1.1rem ui-monospace,Consolas,monospace;letter-spacing:.1em;}
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="mesaj" id="incarcare">__T_INCARCARE__</p>
<div id="continut" class="ascuns">
  <section class="card ascuns" id="conectare">
    <h2>__T_CONECTARE__</h2>
    <p class="nota" id="textConectare">__T_CONECTARE_TEXT__</p>
    <div class="butoane" id="butoaneCod">
      <button type="button" class="principal" id="arataCod">__T_ARATA_COD__</button>
      <input id="cod" inputmode="numeric" autocomplete="one-time-code" maxlength="8" placeholder="12 34 56" aria-label="__T_COD__">
      <button type="button" class="principal" id="conecteaza">__T_CONECTEAZA__</button>
    </div>
    <p class="mesaj" id="mesajCod"></p>
  </section>
  <section class="card">
    <h2>__T_STARE__</h2>
    <p class="stare-mare slab" id="stareMare">-</p>
    <div class="detalii" id="detalii"></div>
    <div class="butoane">
      <button type="button" class="principal" id="comuta">__T_PORNESTE__</button>
      <button type="button" id="verificaIp">__T_VERIFICA_IP__</button>
    </div>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <section class="card ascuns" id="cardPrograme">
    <h2>__T_PROGRAME__</h2>
    <p class="nota" id="textPrograme"></p>
    <div class="butoane"><button type="button" class="principal" id="instaleaza">__T_INSTALEAZA__</button></div>
  </section>
  <section class="card">
    <h2>__T_FURNIZOR__</h2>
    <div class="rand"><label for="furnizor">__T_ETICHETA_FURNIZOR__</label><select id="furnizor"></select></div>
    <div class="rand"><label for="server">__T_ETICHETA_SERVER__</label><select id="server"></select></div>
    <p class="nota" id="cumIei"></p>
    <div class="butoane">
      <button type="button" id="stergeServer">__T_STERGE_SERVER__</button>
      <button type="button" class="rosu" id="stergeToate">__T_STERGE_TOATE__</button>
    </div>
  </section>
  <section class="card">
    <h2>__T_IMPORT__</h2>
    <div class="rand"><label for="fisiere">__T_ALEGE_FISIERE__</label><input type="file" id="fisiere" multiple accept=".ovpn,.conf,.crt,.key,.pem,.txt"></div>
    <div class="butoane">
      <button type="button" class="principal" id="trimite">__T_TRIMITE__</button>
      <button type="button" id="stick">__T_STICK__</button>
    </div>
    <p class="nota">__T_STICK_NOTA__</p>
  </section>
  <section class="card" id="cardCont">
    <h2><span id="titluCont">__T_CONT__</span> <span class="nota" id="contStare"></span></h2>
    <div class="rand"><label for="nume">__T_NUME__</label><input type="text" id="nume" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="128"></div>
    <div class="rand"><label for="parola">__T_PAROLA__</label><input type="password" id="parola" autocomplete="new-password" maxlength="128"></div>
    <div class="butoane">
      <button type="button" class="principal" id="salveazaCont">__T_SALVEAZA__</button>
      <button type="button" id="stergeCont">__T_STERGE_CONT__</button>
    </div>
    <p class="nota" id="contNota">__T_CONT_NOTA__</p>
  </section>
  <section class="card">
    <h2>__T_TRAFIC__</h2>
    <div id="moduri"></div>
    <p class="nota" id="explicatieMod"></p>
    <div id="ales">
      <label class="bifa"><input type="checkbox" id="iptv"> __T_IPTV__</label>
      <p class="nota"><label for="adrese">__T_ADRESE__</label></p>
      <textarea id="adrese" spellcheck="false" autocapitalize="off" placeholder="exemplu.ro"></textarea>
      <div class="butoane"><button type="button" id="salveazaAdrese">__T_SALVEAZA_ADRESE__</button></div>
    </div>
  </section>
  <section class="card">
    <h2>__T_OPTIUNI__</h2>
    <div id="randOprire">
    <label class="bifa"><input type="checkbox" id="oprireTotala"> __T_OPRIRE_TOTALA__</label>
    <p class="nota">__T_OPRIRE_NOTA__</p>
    </div>
    <label class="bifa"><input type="checkbox" id="laPornire"> __T_LA_PORNIRE__</label>
    <p class="nota">__T_LA_PORNIRE_NOTA__</p>
  </section>
  <p class="nota">__NOTA_TV__</p>
</div>
</main>
<script>__SCRIPT_COMUN__
var TXT = __TEXTE_JS__;
var D = null, ASTEPT = null, VAZUTA = null, ADRESE_ATINSE = false;
function pune(id, text){ $(id).textContent = text || ""; }
function optiuni(sel, lista, ales){
  if(document.activeElement === sel){ return; }
  var vechi = Array.prototype.map.call(sel.options, function(o){ return o.value + "|" + o.textContent; }).join("\\n");
  var nou = lista.map(function(x){ return x[0] + "|" + x[1]; }).join("\\n");
  if(vechi !== nou){
    sel.textContent = "";
    lista.forEach(function(x){ var o = document.createElement("option"); o.value = x[0]; o.textContent = x[1]; sel.appendChild(o); });
  }
  sel.value = ales;
}
function arata(d){
  D = d;
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  $("conectare").classList.toggle("ascuns", !!d.asociat || d.nivel === "jeton");
  var m = $("stareMare"); m.textContent = d.text_legatura; m.className = "stare-mare " + d.culoare;
  var det = $("detalii"); det.textContent = "";
  (d.detalii || []).forEach(function(x){ var p = document.createElement("p"); p.textContent = x; det.appendChild(p); });
  if(d.nivel === "jeton"){ var n = document.createElement("p"); n.className = "nota"; n.textContent = TXT.numaiStarea; det.appendChild(n); }
  var pornit = d.pornit || ["conectat", "se_conecteaza", "blocat"].indexOf(d.legatura) !== -1;
  $("comuta").textContent = pornit ? TXT.opreste : TXT.porneste;
  $("comuta").classList.toggle("rosu", pornit); $("comuta").classList.toggle("principal", !pornit);
  $("cardPrograme").classList.toggle("ascuns", !d.lipsesc); pune("textPrograme", d.text_programe);
  optiuni($("furnizor"), d.furnizori, d.furnizor);
  var servere = (d.profiluri || []).map(function(p){ return [p.id, p.titlu]; });
  if(!servere.length){ servere = [["", TXT.niciunServer]]; } else if(!d.profil){ servere.unshift(["", "-"]); }
  optiuni($("server"), servere, d.profil ? d.profil.id : "");
  $("stergeServer").disabled = !d.profil; $("stergeToate").disabled = !d.nr_profiluri;
  pune("cumIei", d.cum_iei);
  $("cardCont").classList.toggle("ascuns", d.fel !== "openvpn");
  pune("contStare", "(" + (d.cont ? TXT.salvate : TXT.lipsesc) + ")"); pune("titluCont", d.text_cont); pune("contNota", d.text_cont_nota); $("stergeCont").disabled = !d.cont;
  var mod = $("moduri");
  if(!mod.children.length){
    d.moduri.forEach(function(x){
      var l = document.createElement("label"); l.className = "bifa";
      var r = document.createElement("input"); r.type = "radio"; r.name = "mod"; r.value = x[0];
      r.addEventListener("change", function(){ trimite("/api/vpn-setari", {mod: x[0]}); });
      l.appendChild(r); l.appendChild(document.createTextNode(" " + x[1])); mod.appendChild(l);
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll("input[name=mod]"), function(r){ r.checked = r.value === d.mod; });
  $("ales").classList.toggle("ascuns", d.mod !== "ales");
  $("iptv").checked = !!d.iptv;
  if(!ADRESE_ATINSE && document.activeElement !== $("adrese")){ $("adrese").value = (d.adrese || []).join("\\n"); }
  $("oprireTotala").checked = !!d.oprire_totala; $("laPornire").checked = !!d.la_pornire;
  // in modul navigator oprirea totala e mereu (navigatorul n-are alta iesire decat tunelul)
  $("randOprire").classList.toggle("ascuns", d.mod === "navigator");
  pune("explicatieMod", d.explicatie_mod);
  var schimba = !!d.asociat;
  Array.prototype.forEach.call(document.querySelectorAll("#continut button, #continut select, #continut input, #continut textarea"), function(e){
    if(e.closest("#conectare")){ return; }
    if(!schimba){ e.disabled = true; }
  });
  var l = d.lucrare || {};
  if(l.lucreaza){ mesaj(d.text_lucreaza); }
  if(l.ultima && l.ultima.id !== VAZUTA){
    var noua = VAZUTA !== null || ASTEPT !== null;
    VAZUTA = l.ultima.id;
    if(noua && (ASTEPT === null || l.ultima.id >= ASTEPT)){ mesaj(l.ultima.mesaj, !l.ultima.reusit); ASTEPT = null; }
  }
}
function citeste(){
  return cerere("/api/vpn").then(function(d){
    if(d && d.result){ arata(d); } else { mesaj((d && d.message) || TXT.necitit, true); }
  }).catch(function(){ mesaj(TXT.nuRaspunde, true); });
}
function trimite(cale, campuri){
  var q = new URLSearchParams(); Object.keys(campuri || {}).forEach(function(k){ q.append(k, campuri[k]); });
  mesaj(TXT.seTrimite);
  return cerere(cale, "POST", q).then(function(r){
    mesaj(r.message, !r.result);
    if(r.lucrare){ ASTEPT = r.lucrare; }
    return citeste().then(function(){ return r; });
  }).catch(function(){ mesaj(TXT.nuRaspunde, true); });
}
$("comuta").addEventListener("click", function(){
  if(!D){ return; }
  var pornit = D.pornit || ["conectat", "se_conecteaza", "blocat"].indexOf(D.legatura) !== -1;
  trimite(pornit ? "/api/vpn-opreste" : "/api/vpn-porneste", {});
});
$("verificaIp").addEventListener("click", function(){ trimite("/api/vpn-ip", {}); });
$("instaleaza").addEventListener("click", function(){ if(confirm(TXT.intrebareInstaleaza)){ trimite("/api/vpn-instaleaza", {confirmat: "1"}); } });
$("furnizor").addEventListener("change", function(){ trimite("/api/vpn-setari", {furnizor: this.value}); });
$("server").addEventListener("change", function(){ if(this.value){ trimite("/api/vpn-setari", {profil: this.value}); } });
$("stergeServer").addEventListener("click", function(){
  if(D && D.profil && confirm(TXT.intrebareSterge.replace("%s", D.profil.titlu))){ trimite("/api/vpn-sterge", {id: D.profil.id, confirmat: "1"}); }
});
$("stergeToate").addEventListener("click", function(){
  if(D && confirm(TXT.intrebareStergeToate.replace("%s", String(D.nr_profiluri)))){ trimite("/api/vpn-sterge-toate", {confirmat: "1"}); }
});
$("stick").addEventListener("click", function(){ trimite("/api/vpn-stick", {}); });
$("salveazaCont").addEventListener("click", function(){
  var n = $("nume").value.trim(), p = $("parola").value;
  if(!n || !p){ mesaj(TXT.scrieNumele, true); return; }
  trimite("/api/vpn-cont", {nume: n, parola: p}).then(function(r){ if(r && r.result){ $("nume").value = ""; $("parola").value = ""; } });
});
$("stergeCont").addEventListener("click", function(){ if(confirm(TXT.intrebareStergeCont)){ trimite("/api/vpn-cont-sterge", {confirmat: "1"}); } });
$("adrese").addEventListener("input", function(){ ADRESE_ATINSE = true; });
$("salveazaAdrese").addEventListener("click", function(){
  trimite("/api/vpn-setari", {adrese: $("adrese").value}).then(function(r){ if(r && r.result){ ADRESE_ATINSE = false; } });
});
$("iptv").addEventListener("change", function(){ trimite("/api/vpn-setari", {iptv: this.checked ? "1" : "0"}); });
$("oprireTotala").addEventListener("change", function(){ trimite("/api/vpn-setari", {oprire_totala: this.checked ? "1" : "0"}); });
$("laPornire").addEventListener("change", function(){ trimite("/api/vpn-setari", {la_pornire: this.checked ? "1" : "0"}); });
// fisierele din telefon: citite ca text in browser; toate odata daca incap (certificatele alaturi se potrivesc), altfel
// cate unul
function citesteFisier(f){
  return new Promise(function(da, nu){ var r = new FileReader(); r.onload = function(){ da([f.name, String(r.result)]); }; r.onerror = nu; r.readAsText(f); });
}
function trimiteFisiere(lista){
  var q = new URLSearchParams(); lista.forEach(function(x){ q.append("nume", x[0]); q.append("text", x[1]); });
  return cerere("/api/vpn-importa", "POST", q);
}
$("trimite").addEventListener("click", function(){
  var alese = Array.prototype.slice.call($("fisiere").files || []);
  if(!alese.length){ mesaj(TXT.alegeFisiere, true); return; }
  if(alese.some(function(f){ return /\\.zip$/i.test(f.name); })){ mesaj(TXT.zip, true); return; }
  var mare = alese.filter(function(f){ return f.size > 60000; })[0];
  if(mare){ mesaj(TXT.prea.replace("%s", mare.name), true); return; }
  mesaj(TXT.seTrimite);
  Promise.all(alese.map(citesteFisier)).then(function(lista){
    var total = lista.reduce(function(s, x){ return s + x[1].length; }, 0);
    var loturi = (total <= 56000 && lista.length <= 40) ? [lista] : lista.map(function(x){ return [x]; });
    var mesaje = [], i = 0;
    function urmatorul(){
      if(i >= loturi.length){ mesaj(mesaje.join(" "), false); $("fisiere").value = ""; return citeste(); }
      return trimiteFisiere(loturi[i++]).then(function(r){ mesaje.push(r.message); return urmatorul(); });
    }
    return urmatorul();
  }).catch(function(){ mesaj(TXT.nuRaspunde, true); });
});
// conectarea cu codul de pe televizor (aceleasi cereri ca pagina de conectare a receptorului: /asociere/cod, /asociere)
function mesajCod(text, eroare){ var m = $("mesajCod"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function asociere(cale, date){
  return fetch(cale, {method: "POST", cache: "no-store", credentials: "same-origin",
    headers: {"Content-Type": "application/x-www-form-urlencoded"}, body: date.toString()}).then(function(r){
    return r.json().catch(function(){ return {result: false, mesaj: TXT.neasteptat.replace("%s", r.status)}; });
  });
}
$("arataCod").addEventListener("click", function(){
  mesajCod(TXT.seCereCodul);
  asociere("/asociere/cod", new URLSearchParams("reafiseaza=1")).then(function(r){
    mesajCod(r.result ? (r.mesaj || TXT.codulPeTv) + " " + TXT.scrieCodul : (r.mesaj || TXT.codNecerut), !r.result);
    if(r.result){ $("cod").focus(); }
  }).catch(function(){ mesajCod(TXT.nuRaspunde, true); });
});
$("conecteaza").addEventListener("click", function(){
  var cod = $("cod").value.replace(/[^0-9]/g, "");
  if(cod.length !== 6){ mesajCod(TXT.codSase, true); return; }
  asociere("/asociere", new URLSearchParams("cod=" + cod)).then(function(r){
    if(r.result){ mesajCod(TXT.conectat); location.reload(); return; }
    mesajCod(r.mesaj || TXT.codGresit, true);
  }).catch(function(){ mesajCod(TXT.nuRaspunde, true); });
});
function planifica(){ setTimeout(function(){ citeste().then(planifica, planifica); }, (ASTEPT !== null || (D && D.lucrare && D.lucrare.lucreaza)) ? 800 : 2500); }
citeste().then(planifica, planifica);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("exemplu.ro"),
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
