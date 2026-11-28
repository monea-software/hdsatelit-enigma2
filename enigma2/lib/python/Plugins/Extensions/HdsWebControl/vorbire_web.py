# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Same authenticated and CSRF-protected gate as the other receiver settings.
#
# The page shows the key steps of the chosen service in place (the short steps, PASI_SCURTI, and the official key page
# of the translation configurator, traducere_configurare_web). A pasted key goes through the configurator route
# function (traducere_configurare_web.cheie: same checks, then HdsConfigurareTraducere.configurator().porneste_cheie,
# which recognises, probes and saves it in the shared key store). The same request turns speech subtitles on with
# the chosen service: when the key is saved the key store calls HdsVorbire.setariSchimbate() and the TV loop starts
# listening by itself. Key presence is read from the key store (T.chei().stare()), never from the TV loop copy.
import html
import json
import time


from Components import HdsVorbire as V
_t = V._t

ORDINE = ("gemini", "groq")	# Gemini first: no card needed
_T = None			# translation module given by PC tests (default Components.HdsTraducereSubtitrari)
_C = None			# configurator module given by PC tests (default Components.HdsConfigurareTraducere)
_cerere = {"id": 0, "serviciu": ""}	# the configurator job started from this page
ASTEPTARE_S = 40.0		# no missing-key message on TV while the key check started here runs
REZULTAT_S = 60.0		# how long the result of that check stays the status line; then the live state speaks


def _tcw():
	"""traducere_configurare_web: from the package, or loaded by path when this file is loaded alone (PC tests)."""
	try:
		from . import traducere_configurare_web as m
		return m
	except ImportError:
		import importlib.util
		import os
		import sys
		nume = "hds_vorbire_traducere_configurare_web"
		m = sys.modules.get(nume)
		if m is None:
			cale = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traducere_configurare_web.py")
			spec = importlib.util.spec_from_file_location(nume, cale)
			m = importlib.util.module_from_spec(spec)
			sys.modules[nume] = m
			spec.loader.exec_module(m)
		return m


def _cheia():
	W = _tcw()
	T = W._tr(_T)
	try:
		puse = dict(T.chei().stare())
	except Exception:
		puse = {}
	etichete = W.etichete(T)
	pasi = {}
	for s in ORDINE:
		# the same pieces as W.servicii(T), only for the two speech services (the page asks every second)
		d = W._instructiuni(T, s)
		pasi[s] = {"nume": T.numeServiciu(s), "pagina_cheie": W.doarHttps(d.get("pagina_cheie", "")),
			"pasi": [W._t(p) for p in W.PASI_SCURTI.get(s, ())], "eticheta": etichete.get(s, "")}
	conf = None
	if _cerere["id"]:
		c = W._cf(_C).configurator().stare()
		if c.get("id") == _cerere["id"]:
			conf = dict((k, c.get(k)) for k in ("stare", "pas", "mesaj", "ce_faci", "serviciu", "serviciu_nume", "salvat",
				"rezerva"))
			if conf["stare"] != "lucru":
				V._cheie_asteptata = 0
				_cerere.setdefault("gata_la", time.monotonic())
				if time.monotonic() - _cerere["gata_la"] > REZULTAT_S:
					conf = None
	return {"chei": dict((s, bool(puse.get(s))) for s in ORDINE), "servicii": pasi, "ordine": list(ORDINE),
		"configurare": conf}


def _textStare(d):
	"""(text, fel) for the status line: lucru, eroare, avertisment, ok or nota."""
	chei, conf, serv = d["chei"], d.get("configurare"), d.get("serviciu")
	nume = lambda s: (d["servicii"].get(s) or {}).get("nume") or s
	if d.get("salveaza"):
		return d.get("mesaj_salvare") or "", "lucru"
	if conf:
		if conf["stare"] == "lucru":
			return conf.get("pas") or _t("Se trimite..."), "lucru"
		if conf["stare"] != "ok":
			return " ".join(x for x in (conf.get("mesaj"), conf.get("ce_faci")) if x), "eroare"
		if conf.get("serviciu") not in V.SERVICII:
			return _t("Cheia e bună, dar e pentru %s. Subtitrările din vorbire merg numai cu Gemini sau Groq: fă cheia de "
				"mai jos.") % (conf.get("serviciu_nume") or conf.get("serviciu") or ""), "avertisment"
	if not any(chei.values()):
		if d.get("pornit"):
			return _t("Subtitrările din vorbire sunt pornite, dar lipsește cheia. Fă cheia mai jos și lipește-o aici; apoi "
				"pornesc singure."), "avertisment"
		return _t("Subtitrările din vorbire au nevoie de o cheie gratuită. Fă-o mai jos și lipește-o aici; apoi pornesc "
			"singure."), "avertisment"
	if d.get("mesaj_salvare"):
		return d["mesaj_salvare"], "eroare"
	if not d.get("pornit") and not (d.get("proba") or {}).get("lucreaza"):
		# the TV loop keeps its last reason after a stop: off is said as off
		return _t("Subtitrările din vorbire sunt oprite."), "nota"
	if d.get("motiv") in ("serviciu", "sunet", "format", "nucleu"):
		# a problem seen now (quota, no sound) comes before the result of the key check
		return d.get("mesaj") or "", "avertisment"
	if conf and conf["stare"] == "ok":
		return _t("Gata: cheia pentru %s merge, iar subtitrările din vorbire sunt pornite.") % nume(conf["serviciu"]), "ok"
	if not chei.get(serv):
		alt = [s for s in ORDINE if chei.get(s)][0]
		return _t("%s nu are cheie, așa că ascultă %s.") % (nume(serv), nume(alt)), "nota"
	return ("" if d.get("motiv") == "cheie" else d.get("mesaj") or ""), "nota"


def stare():
	from Components import HdsVorbireTV as TV
	d = TV.stare()
	d["mesaj"] = TV.mesaj(d["motiv"])
	d["alegeri_limba"] = [[x, str(y)] for x, y in V.initConfig().limba.choices.choices]
	from Components import HdsSubtitrariAspect as A
	d["aspect"] = A.stare()
	d.update(_cheia())
	d["stare_text"], d["stare_fel"] = _textStare(d)
	return d


def _valori(a, s):
	"""{nume: valoare} for the speech settings in a, or None on an unknown name or value."""
	valori = {}
	for nume, valoare in a.items():
		if nume not in ("pornit", "serviciu", "limba"):
			return None
		if nume == "pornit":
			if valoare not in ("0", "1"):
				return None
			valori[nume] = valoare == "1"
		elif valoare not in [x for x, y in getattr(s, nume).choices.choices]:
			return None
		else:
			valori[nume] = valoare
	return valori


def seteaza(a):
	s = V.initConfig()
	if any(n not in ("pornit", "serviciu", "limba") for n in a):
		return {"result": False, "message": V._t("Setare necunoscută.")}
	valori = _valori(a, s)
	if valori is None:
		return {"result": False}
	if valori.get("pornit") is False:
		_cerere.pop("gata_la", None)
		_cerere.update(id=0, serviciu="")		# an old key check result is not shown after Off
	if not V.salveaza(valori):
		return {"result": False, "message": V.stareSalvare()["mesaj_salvare"] or V._t("Se salvează setările.")}
	return stare()


def cheie(a):
	"""POST /api/vorbire-cheie: serviciu (gemini / groq), cheie, limba (optional). The key goes to the configurator
	route function (same checks and the same probe and save); when it started, speech subtitles are turned on with
	this service and start by themselves once the key is saved."""
	W = _tcw()
	s = V.initConfig()
	serv = a.get("serviciu", "")
	if serv not in ORDINE:
		return dict(stare(), result=False, message=_t("Serviciu necunoscut. Nu s-a pornit nimic."))
	valori = _valori(dict((k, a[k]) for k in ("limba",) if a.get(k)), s)
	if valori is None:
		return dict(stare(), result=False, message=_t("Serviciu necunoscut. Nu s-a pornit nimic."))
	r = W.cheie({"cheie": a.get("cheie", ""), "serviciu": serv}, set(), _T, _C)
	if not r.get("result"):
		return dict(stare(), result=False, message=r.get("message") or "")
	_cerere.pop("gata_la", None)
	_cerere.update(id=W._cf(_C).configurator().stare().get("id"), serviciu=serv)
	V._cheie_asteptata = time.monotonic() + ASTEPTARE_S
	valori.update(pornit=True, serviciu=serv)
	if not V.salveaza(valori):
		return dict(stare(), result=False, message=V.stareSalvare()["mesaj_salvare"] or _t("Se salvează setările."))
	return dict(stare(), result=True)


def proba():
	# An explicit request has the same privacy meaning as enabling speech subtitles.
	from Components import HdsVorbireTV as TV, HdsPisteLimbi as P
	p = P.infobarActiv()
	if p is None:
		return {"result": False, "message": V._t("Pornește întâi un canal pe televizor.")}
	if not TV.incearca():
		return {"result": False}
	return stare()


def rute(baza, resource):
	class Stare(baza):
		def render_GET(self, request):
			return self._raspunde(request, stare())

	class Schimba(baza):
		schimbaCeva = True
		def render_POST(self, request):
			from .traducere_subtitrari_web import argumente
			return self._raspunde(request, seteaza(argumente(request)))

	class Cheie(baza):
		schimbaCeva = True
		def render_POST(self, request):
			return self._raspunde(request, cheie(_tcw().argumente(request)))

	class Proba(baza):
		schimbaCeva = True
		def render_POST(self, request):
			return self._raspunde(request, proba())

	class Pagina(resource.Resource):
		isLeaf = True
		def render_GET(self, request):
			from . import plugin as P
			if not P._esteAdresaLocala(P._adresaClient(request)):
				request.setResponseCode(403)
				return b"403"
			P._anteteHtml(request)
			if P.PARAM_JETON in request.args and P._jetonValid(request):
				cfg = P._configPanou("", P._jetonConfigurat(), "")
			else:
				secret, browser = P._sesiuneDinCerere(request)
				if browser is None:
					return P._PAGINA_ASOCIERE.encode("utf-8")
				cfg = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
			return pagina(P._STIL_COMUN, cfg).encode("utf-8")
	return {b"vorbire": Stare(), b"vorbire-seteaza": Schimba(), b"vorbire-cheie": Cheie(), b"vorbire-proba": Proba()}, Pagina()


STIL = """
  main{max-width:760px;margin:0 auto;overflow-wrap:anywhere;}
  h1{font-size:1.25rem;margin:0 0 6px;line-height:1.3;}
  h2{font-size:1.05rem;margin:0 0 10px;}
  p{line-height:1.45;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px 16px;margin:0 0 12px;}
  .alegeri{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;}
  .alegere{display:flex;flex-direction:column;align-items:flex-start;gap:4px;width:100%;min-width:0;min-height:76px;padding:12px 14px;border-radius:10px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;text-align:left;cursor:pointer;}
  .alegere strong{font-size:1.02rem;}
  .alegere.ales{border-color:var(--accent);box-shadow:inset 0 0 0 2px var(--accent);}
  .eticheta{color:#8fd19e;font-size:.84rem;font-style:normal;font-weight:600;line-height:1.35;}
  .semn{font-size:.84rem;font-weight:600;border-radius:6px;padding:1px 8px;}
  .semn.bine{background:rgba(47,143,91,.25);color:#8fd19e;}
  .semn.lipsa{background:rgba(240,198,116,.18);color:#f0c674;}
  button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  button:disabled{opacity:.55;cursor:default;}
  .mare{display:flex;align-items:center;justify-content:center;width:100%;min-height:52px;margin:10px 0 0;padding:12px 16px;border-radius:10px;font-weight:600;font-size:1.02rem;text-align:center;text-decoration:none;}
  .principal{background:var(--accent);border:1px solid var(--accent);color:#fff;}
  a.mare{color:#fff;}
  input,select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;min-width:0;}
  label{display:block;margin:12px 0 6px;}
  .nota{color:var(--text-slab);font-size:.86rem;margin:8px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .stare{border-radius:8px;padding:10px 12px;margin:0 0 12px;line-height:1.45;border:1px solid var(--bordura);}
  .stare.avertisment{color:#f0c674;background:rgba(240,198,116,.12);border-color:rgba(240,198,116,.45);}
  .stare.eroare{color:#ffb4a8;background:rgba(192,57,43,.14);border-color:rgba(255,180,168,.45);}
  .stare.ok{color:#8fd19e;background:rgba(47,143,91,.16);border-color:rgba(143,209,158,.45);font-weight:600;}
  .stare.lucru{color:#f0c674;}
  .eroare{color:#ffb4a8;}
  .bine{color:#8fd19e;font-weight:600;}
  .traducere-sub{color:#fff3b0;}
  ol.pasi{margin:8px 0;padding:0 0 0 22px;line-height:1.5;}
  ol.pasi li{margin:0 0 5px;}
  a.leg{display:inline-block;padding:12px 0;line-height:20px;margin:0 18px 0 0;}
  .ascuns{display:none !important;}
"""


def _json(o):
	return json.dumps(o, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def pagina(stil, cfg):
	# Static labels are translated and escaped before insertion, responses use textContent.
	e = html.escape		# labels go through _t(...) literally, so xgettext sees them
	tx = {"pusa": _t("cheia e pusă"), "fara": _t("fără cheie"), "pentru": _t("Cheia pentru %s"),
		"e_pusa": _t("Cheia pentru %s e pusă."), "lipeste": _t("Lipește întâi cheia."), "trimite": _t("Se trimite..."),
		"nu_raspunde": _t("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.")}
	try:
		drum = _tcw()._drumMeniu("hds_vorbire")
	except Exception:
		drum = e(_t("Meniu"))
	jos = e(_t("Aceleași setări sunt pe televizor, în __DRUM_MENIU__.")).replace("__DRUM_MENIU__", drum)
	alegeri = "".join('<button type="button" class="alegere" id="alege-%s" aria-pressed="false"><strong id="nume-%s">%s</strong>'
		'<em class="eticheta" id="eticheta-%s"></em><span class="semn" id="semn-%s"></span></button>' % (s, s, html.escape(n), s, s)
		for s, n in (("gemini", "Gemini"), ("groq", "Groq")))
	return '''<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>''' + e(_t("Subtitrări din vorbire")) + '''</title>
<style>''' + stil + STIL + '''</style>
</head>
<body>
<main>
<h1>''' + e(_t("Subtitrări din vorbire")) + '''</h1>
<p class="nota">''' + html.escape(V.confidentialitate()) + '''</p>
<p class="stare nota" id="stare" role="status">''' + e(_t("Se citește starea...")) + '''</p>
<section class="card" id="card-setari">
  <label for="pornit">''' + e(_t("Subtitrări din vorbire")) + '''</label>
  <select id="pornit"><option value="0">''' + e(_t("Oprit")) + '''</option><option value="1">''' + e(_t("Pornit")) + '''</option></select>
  <label>''' + e(_t("Serviciul care ascultă")) + '''</label>
  <div class="alegeri" id="alegeri">''' + alegeri + '''</div>
  <label for="limba">''' + e(_t("Limba textului")) + '''</label>
  <select id="limba"></select>
  <button type="button" class="mare" id="salveaza">''' + e(_t("Salvează")) + '''</button>
</section>
<section class="card" id="card-cheie">
  <h2 id="cheie-titlu">''' + e(_t("Cheia")) + '''</h2>
  <p class="bine ascuns" id="cheie-pusa"></p>
  <button type="button" class="ascuns" id="alta">''' + e(_t("Pune altă cheie")) + '''</button>
  <div id="cheie-bloc">
    <a class="mare principal ascuns" id="cheie-pagina" target="_blank" rel="noopener noreferrer">''' + e(_t("Deschide pagina cheii")) + '''</a>
    <ol class="pasi" id="cheie-pasi"></ol>
    <p>''' + e(_t("Apoi întoarce-te aici și lipește cheia.")) + '''</p>
    <label for="cheie">''' + e(_t("Lipește cheia")) + '''</label>
    <input type="text" id="cheie" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="2048" placeholder="''' + e(_t("lipește cheia aici")) + '''">
    <button type="button" class="mare principal" id="cheie-trimite">''' + e(_t("Verifică și salvează")) + '''</button>
    <p class="mesaj" id="mesaj-cheie" role="status"></p>
  </div>
  <p class="nota">''' + e(_t("Aceeași cheie merge și la traducerea subtitrărilor: receptorul o probează cu o traducere scurtă și pornește și traducerea.")) + '''</p>
</section>
<section class="card" id="card-proba">
  <button type="button" class="mare" id="proba">''' + e(_t("Spune ce auzi acum pe canal")) + '''</button>
  <p class="mesaj traducere-sub" id="text" aria-live="polite"></p>
</section>
<footer>
  <p><a class="leg" href="/traducere-configurare">''' + e(_t("Traducerea subtitrărilor: configurare pas cu pas")) + '''</a><a class="leg" href="/traducere-subtitrari">''' + e(_t("Toate setările traducerii")) + '''</a><a class="leg" href="/">''' + e(_t("Panoul receptorului")) + '''</a></p>
  <p class="nota">''' + jos + '''</p>
</footer>
</main>
<script>
var CONFIG=''' + cfg + ''';
var TX=''' + _json(tx) + ''';
function cerere(url, body){var h={}; if(CONFIG.csrf)h['X-HDS-CSRF']=CONFIG.csrf;
if(CONFIG.jeton)url+=(url.indexOf('?')<0?'?':'&')+'token='+encodeURIComponent(CONFIG.jeton);
if(body)h['Content-Type']='application/x-www-form-urlencoded';
return fetch(url,{method:body?'POST':'GET',headers:h,body:body,credentials:'same-origin',cache:'no-store'}).then(function(r){return r.json()});}
var $=function(x){return document.getElementById(x)}, init=false, ales=null, ultim=null, alta=false, pasiPentru=null;
function nume(d,s){return ((d.servicii||{})[s]||{}).nume||s}
function arataCheia(d){
  var s=(d.servicii||{})[ales]||{}, are=!!(d.chei||{})[ales], deschis=!are||alta;
  (d.ordine||[]).forEach(function(c){var b=$('alege-'+c); if(!b)return; var x=c===ales;
    b.classList.toggle('ales',x); b.setAttribute('aria-pressed',x?'true':'false');
    $('eticheta-'+c).textContent=((d.servicii||{})[c]||{}).eticheta||'';
    var m=$('semn-'+c), p=!!(d.chei||{})[c]; m.textContent=p?TX.pusa:TX.fara; m.className='semn '+(p?'bine':'lipsa');});
  $('cheie-titlu').textContent=TX.pentru.replace('%s',nume(d,ales));
  $('cheie-pusa').textContent=TX.e_pusa.replace('%s',nume(d,ales));
  $('cheie-pusa').classList.toggle('ascuns',!are);
  $('alta').classList.toggle('ascuns',deschis);
  $('cheie-bloc').classList.toggle('ascuns',!deschis);
  if(pasiPentru!==ales){pasiPentru=ales; var ol=$('cheie-pasi'); while(ol.firstChild)ol.removeChild(ol.firstChild);
    (s.pasi||[]).forEach(function(t){var li=document.createElement('li'); li.textContent=t; ol.appendChild(li)});
    var a=$('cheie-pagina'); if((s.pagina_cheie||'').indexOf('https://')===0){a.href=s.pagina_cheie; a.classList.remove('ascuns')}else{a.removeAttribute('href'); a.classList.add('ascuns')}}
}
function mostra(d){
  if(!d||!d.chei){$('stare').textContent=(d&&d.message)||''; $('stare').className='stare eroare'; return;}
  ultim=d;
  if(!init){d.alegeri_limba.forEach(function(x){var o=document.createElement('option');o.value=x[0];o.textContent=x[1];$('limba').appendChild(o)});
    $('pornit').value=d.pornit?'1':'0'; $('limba').value=d.limba;
    ales=(d.chei.gemini||d.chei.groq)?d.serviciu:d.ordine[0]; init=true}
  arataCheia(d);
  var t=d.stare_text||''; if(d.indiciu&&d.stare_fel!=='eroare')t+=(t?' ':'')+'~'+Math.round(d.intarziere||4)+' s';
  $('stare').textContent=t; $('stare').className='stare '+(d.stare_fel||'nota')+(t?'':' ascuns');
  $('text').textContent=(d.proba||{}).text||d.text||'';
  var lucru=!!(d.configurare&&d.configurare.stare==='lucru');
  $('salveaza').disabled=!!d.salveaza; $('cheie-trimite').disabled=lucru||!!d.salveaza;
}
function la(id,f){$(id).addEventListener('click',f)}
['gemini','groq'].forEach(function(c){la('alege-'+c,function(){ales=c; alta=false; if(ultim)mostra(ultim)})});
la('alta',function(){alta=true; if(ultim)mostra(ultim); $('cheie').focus()});
la('salveaza',function(){var q=new URLSearchParams(); q.set('pornit',$('pornit').value); q.set('serviciu',ales||'gemini'); q.set('limba',$('limba').value);
  cerere('/api/vorbire-seteaza',q.toString()).then(function(d){mostra(d); if(d&&d.chei&&d.pornit&&!d.chei[ales])$('card-cheie').scrollIntoView()})});
la('cheie-trimite',function(){var v=$('cheie').value.trim(); if(!v){$('mesaj-cheie').textContent=TX.lipeste; return}
  var q=new URLSearchParams(); q.set('serviciu',ales||'gemini'); q.set('cheie',v); q.set('limba',$('limba').value);
  $('mesaj-cheie').textContent=TX.trimite;
  cerere('/api/vorbire-cheie',q.toString()).then(function(d){$('mesaj-cheie').textContent=d.result===false?(d.message||''):'';
    if(d.result!==false){$('cheie').value=''; $('pornit').value='1'} mostra(d)}).catch(function(){$('mesaj-cheie').textContent=TX.nu_raspunde})});
la('proba',function(){cerere('/api/vorbire-proba','proba=1').then(mostra)});
function pas(){cerere('/api/vorbire').then(mostra).catch(function(){$('stare').textContent=TX.nu_raspunde; $('stare').className='stare eroare'}).then(function(){setTimeout(pas,1000)})}pas();
</script>
</body>
</html>'''
