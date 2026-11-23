# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Same authenticated and CSRF-protected gate as the other receiver settings.
import html


from Components import HdsVorbire as V
_t = V._t


def stare():
	from Components import HdsVorbireTV as TV
	d = TV.stare()
	d["mesaj"] = TV.mesaj(d["motiv"])
	d["alegeri_limba"] = [[x, str(y)] for x, y in V.initConfig().limba.choices.choices]
	from Components import HdsSubtitrariAspect as A
	d["aspect"] = A.stare()
	return d


def seteaza(a):
	s = V.initConfig()
	valori = {}
	for nume, valoare in a.items():
		if nume not in ("pornit", "serviciu", "limba"):
			return {"result": False, "message": V._t("Setare necunoscută.")}
		if nume == "pornit":
			if valoare not in ("0", "1"):
				return {"result": False}
			valori[nume] = valoare == "1"
		elif valoare not in [x for x, y in getattr(s, nume).choices.choices]:
			return {"result": False}
		else:
			valori[nume] = valoare
	if not V.salveaza(valori):
		return {"result": False, "message": V.stareSalvare()["mesaj_salvare"] or V._t("Se salvează setările.")}
	return stare()


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
	return {b"vorbire": Stare(), b"vorbire-seteaza": Schimba(), b"vorbire-proba": Proba()}, Pagina()


def pagina(stil, cfg):
	# Static labels are translated and escaped before insertion, responses use textContent.
	labels = [_t('Subtitrări din vorbire'), _t('Oprit'), _t('Pornit'), _t('Limba textului'), _t('Salvează'), _t('Spune ce auzi acum pe canal'), _t('Pune cheia în același loc ca la traducere'), _t('Groq și Gemini folosesc cheile deja puse pentru traducere. Alege unul dintre ele pe pagina cheilor.')]
	t = [html.escape(x) for x in labels]
	return '''<!doctype html><html lang="ro"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>''' + stil + '''</style><title>''' + t[0] + '''</title><main><h1>''' + t[0] + '''</h1><p>''' + html.escape(V.confidentialitate()) + '''</p>
<select id="pornit"><option value="0">''' + t[1] + '''</option><option value="1">''' + t[2] + '''</option></select>
<select id="serviciu"><option value="groq">Groq</option><option value="gemini">Gemini</option></select>
<label>''' + t[3] + ''' <select id="limba"></select></label><button id="salveaza">''' + t[4] + '''</button>
<p>''' + t[7] + '''</p><p><a href="/traducere-configurare">''' + t[6] + '''</a></p>
<button id="proba">''' + t[5] + '''</button><p id="stare" role="status"></p><p id="text" aria-live="polite"></p></main>
<script>var CONFIG=''' + cfg + ''';
function cerere(url, body){var h={}; if(CONFIG.csrf)h['X-HDS-CSRF']=CONFIG.csrf;
if(CONFIG.jeton)url+=(url.indexOf('?')<0?'?':'&')+'token='+encodeURIComponent(CONFIG.jeton);
if(body)h['Content-Type']='application/x-www-form-urlencoded';
return fetch(url,{method:body?'POST':'GET',headers:h,body:body,credentials:'same-origin'}).then(function(r){return r.json()});}
var $=function(x){return document.getElementById(x)}, init=false;
function mostra(d){if(!d.result){$('stare').textContent=d.message||'';return;} $('text').textContent=(d.proba||{}).text||d.text||'';
$('stare').textContent=d.mesaj_salvare||(d.indiciu?'~'+Math.round(d.intarziere||4)+' s':(d.mesaj||''));
$('salveaza').disabled=!!d.salveaza;
if(!init){d.alegeri_limba.forEach(function(x){var o=document.createElement('option');o.value=x[0];o.textContent=x[1];$('limba').appendChild(o)});
['pornit','serviciu','limba'].forEach(function(n){$(n).value=n==='pornit'?(d[n]?'1':'0'):d[n]});init=true}}
$('salveaza').onclick=function(){var q=new URLSearchParams();['pornit','serviciu','limba'].forEach(function(n){q.set(n,$(n).value)});cerere('/api/vorbire-seteaza',q.toString()).then(mostra)};
$('proba').onclick=function(){cerere('/api/vorbire-proba','proba=1').then(mostra)};
function pas(){cerere('/api/vorbire').then(mostra).catch(function(){}).then(function(){setTimeout(pas,1000)})}pas();
</script></html>'''
