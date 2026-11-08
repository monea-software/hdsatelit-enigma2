# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Setarile reale ale functiilor producatorului, pe televizor si in web.

GET nu deschide nimic. Omul deschide ecranul original prin POST, iar pagina
foloseste chiar elementele listei lui. Salveaza si Anuleaza cheama ecranul.
O intrebare aparuta deasupra ramane pe televizor, cu termenul original.
Poarta comuna cere reteaua locala, asociere si POST cu CSRF pentru schimbari.
"""
import xml.etree.ElementTree as ET

FELURI_EDITABILE = ('bool', 'alegere', 'numar', 'glisor', 'cifre')


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _f(F=None):
	if F is not None:
		return F
	from Components import HdsFunctiiImagine
	return HdsFunctiiImagine


def _s(S=None):
	if S is not None:
		return S
	from . import setari_web
	return setari_web


def stare(cheie, F=None, S=None, sesiune=None):
	"""Numai citire: disponibilitatea si lista ecranului deschis prin acest adaptor."""
	F = _f(F)
	date = F.FUNCTII.get(cheie)
	if date is None:
		return {'result': False, 'message': _t('Funcția nu este disponibilă pe acest receptor.')}
	disponibil = F.disponibil(cheie)
	ecran = F.ecranCurent(sesiune, cheie) if sesiune is not None else None
	detinut = F.ecranDeschis(sesiune, cheie) if sesiune is not None else None
	asteapta = detinut is not None and ecran is None
	rez = {'result': True, 'id': cheie, 'titlu': _t(date[2]), 'disponibil': bool(disponibil),
		'deschis': ecran is not None, 'asteapta': asteapta, 'randuri': [], 'message': '',
		'editor_marcaje': cheie == 'marcaje', 'marcaje': [], 'pozitie': ''}
	if not disponibil:
		rez['message'] = _t('Funcția nu este disponibilă pe acest receptor.')
	elif asteapta:
		rez['message'] = _t('Răspunde la fereastra de pe televizor, folosind telecomanda.')
	elif sesiune is None:
		rez['message'] = _t('Așteaptă pornirea completă a receptorului, apoi reîncarcă pagina.')
	elif ecran is None:
		rez['message'] = _t('Deschide ecranul pe televizor pentru a-l folosi din această pagină.')
	if ecran is None:
		return rez
	if cheie == 'marcaje':
		try:
			rez.update(F.marcaje(sesiune))
		except ValueError as eroare:
			rez.update(result=False, message=str(eroare))
		return rez
	S = _s(S)
	for nr, rand in enumerate(F.randuri(ecran)[:200]):
		if not isinstance(rand, (tuple, list)) or len(rand) < 2:
			continue
		eticheta, el = str(rand[0]), rand[1]
		fel = S._fel(el, ET.Element('item', text=eticheta))
		if fel is None:
			continue
		modificabil = fel in FELURI_EDITABILE and bool(getattr(el, 'enabled', True))
		if not modificabil and fel != 'secret':
			fel = 'citire'
		r = S._descriere(el, fel)
		r.update(nr=nr, semn=str(id(el)), eticheta=eticheta, modificabil=modificabil)
		rez['randuri'].append(r)
	return rez


def actiune(nume, argumente, F=None, S=None, sesiune=None):
	"""O singura actiune asupra ecranului original; nicio tasta injectata."""
	F, S = _f(F), _s(S)
	cheie = argumente.get('id', '')
	rez = stare(cheie, F, S, sesiune)
	inchide_editor = cheie == 'marcaje' and nume == 'anuleaza' and rez.get('deschis')
	if (not rez.get('result') and not inchide_editor) or not rez.get('disponibil') or sesiune is None:
		rez['result'] = False
		return rez
	try:
		if nume == 'deschide':
			F.deschide(sesiune, cheie)
		elif nume == 'schimba':
			try:
				nr = int(argumente.get('nr', ''))
			except (TypeError, ValueError):
				raise ValueError(_t('Lista setărilor s-a schimbat. Reîncarcă pagina.'))
			F.schimba(sesiune, cheie, nr, argumente.get('semn', ''), argumente.get('valoare', ''), S)
		elif nume in ('salveaza', 'anuleaza'):
			F.incheie(sesiune, cheie, nume == 'salveaza')
		elif nume == 'marcaje' and cheie == 'marcaje':
			F.actiuneMarcaje(sesiune, argumente.get('operatie', ''),
				argumente.get('pts'), argumente.get('tip'))
		else:
			raise ValueError(_t('Acțiunea nu este disponibilă.'))
	except ValueError as eroare:
		rez = stare(cheie, F, S, sesiune)
		rez.update(result=False, message=str(eroare))
		return rez
	rez = stare(cheie, F, S, sesiune)
	if not rez['asteapta'] and nume in ('salveaza', 'anuleaza'):
		if cheie == 'marcaje':
			rez['message'] = _t('Editorul a fost închis. Marcajele se păstrează la fiecare schimbare.')
		else:
			rez['message'] = _t('Salvat.') if nume == 'salveaza' else _t('Modificările au fost anulate.')
	return rez


def argumente(request):
	"""Numai campurile cunoscute, scurte; semnul apartine elementului ConfigElement."""
	rez = {}
	for cheie in ('id', 'nr', 'semn', 'valoare', 'operatie', 'pts', 'tip'):
		valori = (getattr(request, 'args', None) or {}).get(cheie.encode('ascii'), [])
		if not valori:
			continue
		valoare = valori[0]
		if isinstance(valoare, bytes):
			valoare = valoare.decode('utf-8', 'replace')
		rez[cheie] = str(valoare)[:120].strip()
	return rez


def rute(baza, resource, F=None, S=None, sesiune=None):
	"""API cu poarta HdsJsonResource si pagina protejata ca celelalte setari."""
	def curenta():
		return sesiune() if sesiune is not None else None

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(argumente(request).get('id', ''), F, S, curenta()))
			except Exception as eroare:
				return self._eroare(request, _t('Eroare pe receptor: %s') % eroare, 500)

	class SchimbaResource(baza):
		schimbaCeva = True

		def __init__(self, nume):
			baza.__init__(self)
			self.nume = nume

		def render_POST(self, request):
			try:
				rez = actiune(self.nume, argumente(request), F, S, curenta())
				return self._raspunde(request, rez)
			except Exception as eroare:
				return self._eroare(request, _t('Eroare pe receptor: %s') % eroare, 500)

		def render_GET(self, request):
			return self._eroare(request, _t('Această acțiune cere POST.'), 405)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {b'functii-imagine': StareResource()}
	for nume in ('deschide', 'schimba', 'salveaza', 'anuleaza', 'marcaje'):
		api[('functii-imagine-' + nume).encode('ascii')] = SchimbaResource(nume)
	return api, PaginaResource()


def pagina(request):
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b'content-type', b'text/plain; charset=utf-8')
		return _t('Acces permis doar din rețeaua locală.').encode('utf-8')
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou('', P._jetonConfigurat(), '')
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode('utf-8')
		config_pagina = P._configPanou(P.csrfPentru(secret), '', browser.get('nume', ''))
	return pagina_text(P._STIL_COMUN, config_pagina).encode('utf-8', 'replace')


def pagina_text(stil, config_pagina):
	try:
		from .traducere_pagini import traduce
		sablon = traduce(PAGINA, TEXTE_PAGINA, 'pagina')
	except ImportError:
		sablon = PAGINA
	return sablon.replace('__STIL_COMUN__', stil).replace('__CONFIG__', config_pagina)


PAGINA = '''<!DOCTYPE html>
<html lang="ro"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Setările receptorului</title><style>__STIL_COMUN__
main{max-width:760px;margin:0 auto;}
h1{font-size:1.3rem;margin:0 0 16px;}
.card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;}
.rand{display:grid;grid-template-columns:1fr minmax(150px,300px);gap:12px;align-items:center;padding:10px 0;}
.rand+.rand{border-top:1px solid var(--bordura);}
input,select,button{min-height:44px;padding:8px;border-radius:8px;border:1px solid var(--bordura);
background:var(--panou);color:var(--text);font:inherit;max-width:100%;box-sizing:border-box;}
button{cursor:pointer;}button:disabled{opacity:.5;cursor:default;}
.butoane{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0;}
.nota{color:var(--text-slab);line-height:1.5;}.eroare{color:#ffb4a8;}
[hidden]{display:none!important;}@media(max-width:560px){.rand{grid-template-columns:1fr;}}
</style></head><body><main>
<h1 id="titlu">Setările receptorului</h1>
<p id="stare" role="status">Se citesc setările...</p>
<div class="butoane"><button id="deschide" type="button" hidden>Deschide setările pe televizor</button></div>
<section id="lista" class="card" hidden></section>
<section id="editorMarcaje" class="card" hidden>
<p id="pozitie"></p><div class="butoane">
<button id="adaugaMarcaj" type="button">Adaugă marcaj aici</button>
<button id="start" type="button">START păstrare aici</button>
<button id="stop" type="button">STOP păstrare aici</button></div>
<div id="marcaje"></div></section>
<div id="final" class="butoane" hidden>
<button id="salveaza" type="button">Salvează</button>
<button id="anuleaza" type="button">Anulează</button></div>
<p class="nota" id="notaSetari">Setările se schimbă și pe televizor. Salvează sau anulează când ai terminat.
Dacă apare o confirmare, răspunde cu telecomanda.</p>
<p class="nota" id="notaMarcaje" hidden>Marcajele se păstrează imediat.
START și STOP delimitează porțiunile care se redau; ce rămâne în afara lor este sărit.
Ștergerea și un STOP fără START cer confirmare pe televizor, din telecomandă.</p>
<p id="mesaj" role="status"></p>
</main><script>
var CFG=__CONFIG__;
var ID=new URLSearchParams(location.search).get("id")||"";
var OCUPAT=false;
var REVIZIE=0;
function $(id){return document.getElementById(id);}
function el(tag,text){var n=document.createElement(tag);if(text!==undefined){n.textContent=text;}return n;}
function adresa(cale){
  if(!CFG.jeton){return cale;}
  return cale+(cale.indexOf("?")<0?"?":"&")+"token="+encodeURIComponent(CFG.jeton);
}
function cerere(cale,metoda,date){
  var opt={method:metoda||"GET",cache:"no-store",credentials:"same-origin",headers:{}};
  if(CFG.csrf){opt.headers["X-HDS-CSRF"]=CFG.csrf;}
  if(date){opt.headers["Content-Type"]="application/x-www-form-urlencoded";opt.body=date.toString();}
  return fetch(adresa(cale),opt).then(function(r){
    if(r.status===401&&!CFG.jeton){location.replace("/");throw new Error("browser deconectat");}
    if(!r.ok){throw new Error("HTTP "+r.status);}
    return r.json();
  });
}
function mesaj(text,rau){$("mesaj").textContent=text||"";$("mesaj").classList.toggle("eroare",!!rau);}
function arata(d,fortat){
  $("titlu").textContent=d.titlu||"Setările receptorului";
  document.title=$("titlu").textContent;
  $("stare").textContent=d.message||"";
  $("deschide").hidden=!d.disponibil||d.deschis||d.asteapta;
  $("deschide").textContent=d.editor_marcaje?"Deschide editorul pe televizor":"Deschide setările pe televizor";
  $("final").hidden=!d.deschis;
  $("salveaza").hidden=!!d.editor_marcaje;
  $("anuleaza").textContent=d.editor_marcaje?"Închide":"Anulează";
  $("notaSetari").hidden=!!d.editor_marcaje;
  $("notaMarcaje").hidden=!d.editor_marcaje;
  $("editorMarcaje").hidden=!d.deschis||!d.editor_marcaje;
  if(d.editor_marcaje){arataMarcaje(d);}
  var lista=$("lista");lista.hidden=!d.deschis||d.editor_marcaje;
  if(d.deschis&&!fortat&&lista.contains(document.activeElement)){return;}
  lista.textContent="";
  (d.randuri||[]).forEach(function(r){
    var rand=el("div"),camp;rand.className="rand";
    var eticheta=el("label",r.eticheta);rand.appendChild(eticheta);
    if(r.modificabil&&(r.fel==="bool"||r.fel==="alegere")){
      camp=el("select");
      (r.alegeri||[]).forEach(function(a){var o=el("option",a[1]);o.value=a[0];camp.appendChild(o);});
      camp.value=r.valoare;
    }else if(r.modificabil){
      camp=el("input");camp.type="number";camp.min=r.min;camp.max=r.max;camp.step=r.pas||1;
      camp.value=r.valoare;
    }else{camp=el("span",r.valoare_text||"");}
    if(r.modificabil){
      camp.id="setare"+r.nr;eticheta.htmlFor=camp.id;
      camp.addEventListener("change",function(){
        actiune("schimba",{nr:String(r.nr),semn:r.semn,valoare:camp.value});
      });
    }
    rand.appendChild(camp);lista.appendChild(rand);
  });
}
function arataMarcaje(d){
  $("pozitie").textContent="Poziția curentă: "+(d.pozitie||"?");
  var lista=$("marcaje");lista.textContent="";
  if(!(d.marcaje||[]).length){lista.appendChild(el("p","Niciun marcaj încă."));}
  (d.marcaje||[]).forEach(function(r){
    var rand=el("div"),butoane=el("div");rand.className="rand";butoane.className="butoane";
    rand.appendChild(el("span",r.text));
    [["sari","Sari aici"],["sterge","Șterge"]].forEach(function(a){
      var b=el("button",a[1]);b.type="button";
      b.addEventListener("click",function(){actiune("marcaje",{operatie:a[0],pts:r.pts,tip:String(r.tip)});});
      butoane.appendChild(b);
    });
    rand.appendChild(butoane);lista.appendChild(rand);
  });
}
function citeste(){
  if(OCUPAT){return;}
  var revizie=REVIZIE;
  cerere("/api/functii-imagine?id="+encodeURIComponent(ID)).then(function(d){
    if(revizie!==REVIZIE||OCUPAT){return;}
    arata(d,false);if(!d.result){mesaj(d.message,true);}
  }).catch(function(){mesaj("Receptorul nu răspunde.",true);});
}
function actiune(nume,date){
  if(OCUPAT){return;}OCUPAT=true;REVIZIE++;
  var q=new URLSearchParams(date||{});q.set("id",ID);mesaj("Se aplică...");
  document.querySelectorAll("button,input,select").forEach(function(n){n.disabled=true;});
  cerere("/api/functii-imagine-"+nume,"POST",q).then(function(d){
    arata(d,true);mesaj(d.message,!d.result);
  }).catch(function(){mesaj("Receptorul nu răspunde.",true);}).then(function(){
    OCUPAT=false;document.querySelectorAll("button,input,select").forEach(function(n){n.disabled=false;});
  });
}
["deschide","salveaza","anuleaza"].forEach(function(n){
  $(n).addEventListener("click",function(){actiune(n);});
});
[["adaugaMarcaj","adauga-marcaj"],["start","start"],["stop","stop"]].forEach(function(a){
  $(a[0]).addEventListener("click",function(){actiune("marcaje",{operatie:a[1]});});
});
citeste();setInterval(citeste,1500);
</script></body></html>'''


def N_(text):
	return text


TEXTE_PAGINA = {
	'html': (
		N_('Setările receptorului'), N_('Se citesc setările...'),
		N_('Deschide setările pe televizor'), N_('Salvează'), N_('Anulează'),
		N_('Adaugă marcaj aici'), N_('START păstrare aici'), N_('STOP păstrare aici'),
		N_('Setările se schimbă și pe televizor. Salvează sau anulează când ai terminat. '
			'Dacă apare o confirmare, răspunde cu telecomanda.'),
		N_('Marcajele se păstrează imediat. START și STOP delimitează porțiunile care se redau; '
			'ce rămâne în afara lor este sărit. Ștergerea și un STOP fără START cer confirmare pe televizor, '
			'din telecomandă.'),
	),
	'js': (
		N_('Setările receptorului'), N_('browser deconectat'),
		N_('Receptorul nu răspunde.'), N_('Se aplică...'),
		N_('Deschide editorul pe televizor'), N_('Deschide setările pe televizor'),
		N_('Închide'), N_('Anulează'), N_('Poziția curentă: '), N_('Niciun marcaj încă.'),
		N_('Sari aici'), N_('Șterge'),
	),
}
