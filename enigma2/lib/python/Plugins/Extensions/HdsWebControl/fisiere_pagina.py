# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Pagina /fisiere. Cadrul, meniul si paleta sunt aplicate de cadru_web.

API-ul foloseste cookie-ul separat al parolei root si CSRF-ul browserului.
Un 401 redeschide formularul pe loc; editorul nesalvat ramane in pagina.
"""

import html
import json


def _(text):
	try:
		import builtins
		traducere = getattr(builtins, "_", None)
		return traducere(text) if callable(traducere) else text
	except Exception:
		return text


def _texte():
	# Literale pentru xgettext; traducerea se face la fiecare cerere, nu la import.
	return {
		"title": _("Fișiere"),
		"intro": _("Dosarele și fișierele receptorului, direct în browser."),
		"authTitle": _("Parola receptorului"),
		"authNote": _("Din afara casei se cere parola utilizatorului root al receptorului, o dată în această sesiune a browserului. În casă fișierele se deschid fără parolă."),
		"password": _("Parolă"),
		"login": _("Deschide fișierele"),
		"logout": _("Închide accesul"),
		"checking": _("Se verifică accesul..."),
		"authExpired": _("Accesul la fișiere a expirat. Introdu din nou parola receptorului."),
		"connected": _("Acces la fișiere deschis în acest browser."),
		"external": _("Permite accesul la fișiere din afara casei"),
		"externalNote": _("Se schimbă numai din rețeaua locală. Accesul din afara casei cere în continuare un browser intrat pe receptor și parola receptorului."),
		"externalSaved": _("Setarea accesului din afara casei a fost salvată."),
		"shortcuts": _("Scurtături"),
		"manage": _("Organizează"),
		"finish": _("Gata"),
		"noShortcuts": _("Nu sunt scurtături. Alege un dosar sau un fișier și adaugă-l aici."),
		"shortcutNote": _("Scurtăturile sunt păstrate pe receptor și sunt aceleași în toate browserele."),
		"path": _("Cale"),
		"go": _("Deschide"),
		"up": _("Dosarul de sus"),
		"refresh": _("Reîncarcă"),
		"upload": _("Încarcă fișiere"),
		"newDir": _("Dosar nou"),
		"newFile": _("Fișier nou"),
		"filter": _("Filtrează numele din lista încărcată"),
		"drop": _("Poți trage aici mai multe fișiere pentru a le încărca în dosarul deschis."),
		"dropNow": _("Lasă fișierele aici"),
		"name": _("Nume"),
		"size": _("Mărime"),
		"date": _("Modificat"),
		"mode": _("Permisiuni"),
		"selectAll": _("Selectează toate fișierele afișate"),
		"select": _("Selectează %s"),
		"selected": _("Selectate: %s"),
		"shown": _("Afișate: %s din %s"),
		"actions": _("Acțiuni"),
		"open": _("Deschide"),
		"edit": _("Editează textul"),
		"download": _("Descarcă"),
		"copy": _("Copiază"),
		"move": _("Mută"),
		"rename": _("Redenumește"),
		"delete": _("Șterge"),
		"addShortcut": _("Adaugă la scurtături"),
		"clear": _("Golește selecția"),
		"empty": _("Dosarul este gol."),
		"noMatch": _("Niciun nume nu se potrivește filtrului."),
		"loadMore": _("Arată mai multe"),
		"loading": _("Se citește dosarul..."),
		"folder": _("Dosar"),
		"file": _("Fișier"),
		"link": _("Legătură simbolică"),
		"other": _("Fișier special"),
		"linkTo": _("Legătură către %s"),
		"openTarget": _("Deschide ținta legăturii"),
		"missingTarget": _("Ținta legăturii simbolice nu poate fi deschisă."),
		"destination": _("Dosarul destinație"),
		"newName": _("Numele nou"),
		"chmodHelp": _("Permisiunile în format octal, de exemplu 0644 pentru un fișier sau 0755 pentru un dosar. Se aplică elementelor selectate, fără parcurgerea subdosarelor."),
		"invalidMode": _("Scrie 3 sau 4 cifre între 0 și 7."),
		"invalidName": _("Scrie un nume fără /, diferit de „.” și „..”."),
		"required": _("Completează câmpul."),
		"continue": _("Continuă"),
		"cancel": _("Renunță"),
		"close": _("Închide"),
		"confirm": _("Confirmare"),
		"confirmAction": _("Da, continuă"),
		"pending": _("Se trimite..."),
		"done": _("Operațiunea s-a încheiat."),
		"cancelled": _("Operațiune oprită."),
		"cancelNote": _("Oprirea păstrează fișierele deja prelucrate; verifică dosarul destinație."),
		"jobTitle": _("Operațiuni și transferuri"),
		"stop": _("Oprește"),
		"running": _("În lucru"),
		"failed": _("Operațiunea nu a reușit."),
		"partial": _("Elemente prelucrate"),
		"resultCount": _("Elemente prelucrate: %s."),
		"errorCount": _("Elemente neprelucrate: %s."),
		"chooseOne": _("Alege un singur element pentru această acțiune."),
		"chooseAny": _("Selectează mai întâi un fișier sau un dosar."),
		"downloadFolders": _("Pentru descărcare, selectează fișiere. Deschide dosarele pentru a alege conținutul lor."),
		"network": _("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
		"badResponse": _("Receptorul a răspuns neașteptat (HTTP %s)."),
		"editorTitle": _("Editor de text"),
		"save": _("Salvează"),
		"saved": _("Fișier salvat."),
		"unsaved": _("Ai modificări nesalvate. Le abandonezi?"),
		"modified": _("Modificări nesalvate"),
		"editorNote": _("Fișierul se salvează cu codarea și sfârșiturile de linie citite de pe receptor."),
		"editorChanged": _("Fișierul a fost schimbat pe receptor. Reîncarcă-l înainte de a salva."),
		"editorReload": _("Reîncarcă fișierul"),
		"uploading": _("Se încarcă %s"),
		"uploadDone": _("Încărcat: %s"),
		"uploadCancelled": _("Încărcare oprită: %s"),
		"uploadFailed": _("Nu s-a încărcat: %s"),
		"uploadConfirm": _("Fișierul există. Confirmi înlocuirea lui?"),
		"shortcutName": _("Numele scurtăturii"),
		"shortcutRemove": _("Elimină scurtătura"),
		"shortcutUp": _("Mută scurtătura mai sus"),
		"shortcutDown": _("Mută scurtătura mai jos"),
		"shortcutAdded": _("Scurtătură adăugată."),
		"shortcutRemoved": _("Scurtătura a fost eliminată. Fișierul a rămas pe receptor."),
		"bytes": _("octeți"),
	}


def _json(date):
	return (json.dumps(date, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c")
		.replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def pagina_text(stil, config_pagina):
	texte = _texte()
	try:
		from .meniu_comun_web import STIL_PAGINI
	except ImportError:
		STIL_PAGINI = ""
	try:
		config = json.loads(config_pagina) if isinstance(config_pagina, str) else config_pagina
	except (TypeError, ValueError):
		config = {}
	text = PAGINA.replace("__STIL_COMUN__", stil).replace("__STIL_PAGINI__", STIL_PAGINI)
	for cheie, valoare in texte.items():
		text = text.replace("__T_%s__" % cheie, html.escape(valoare, quote=True))
	return text.replace("__TEXTE__", _json(texte)).replace("__CONFIG__", _json(config or {}))


PAGINA = r'''<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="same-origin">
<title>__T_title__</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
main{max-width:1240px;margin:0 auto;min-width:0}h1{font-size:1.4rem;margin:0 0 8px}.sub{color:var(--text-slab);line-height:1.45;margin:0 0 18px}
.ascuns,[hidden]{display:none!important}.f-top,.f-tools,.f-path,.f-selection,.f-heading{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.f-top{justify-content:space-between;margin-bottom:12px}.f-top p{margin:0}.f-layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:14px;align-items:start}.f-main{min-width:0}.f-side{padding:14px}.f-side h2{margin:0}.f-heading{justify-content:space-between;margin-bottom:8px}.f-heading button{padding:5px 8px;font-size:.8rem;min-height:36px}.f-shortcuts{display:flex;flex-direction:column;gap:4px}.f-shortcut{padding:5px 0;border-bottom:1px solid var(--bordura)}.f-shortcut:last-child{border:0}.f-shortcut-open{width:100%;text-align:left;white-space:normal;overflow-wrap:anywhere;border:0;background:transparent;padding:7px}.f-shortcut-open span{display:block;font-size:.75rem;color:var(--text-slab);margin-top:2px;font-family:monospace}.f-shortcut-controls{display:flex;gap:4px;flex-wrap:wrap}.f-shortcut-controls button{padding:4px 8px;min-height:36px;font-size:.8rem}.f-path{margin-bottom:10px}.f-path label{font-size:.9rem}.f-path input{flex:1;min-width:120px;font-family:monospace}.f-tools{margin-bottom:12px}.f-filter{flex:1;min-width:160px}.f-drop{border:1px dashed var(--bordura);padding:10px 12px;border-radius:8px;color:var(--text-slab);font-size:.85rem;margin-bottom:10px}.f-drop.active{border:2px dashed var(--accent);background:var(--panou);color:var(--text)}.f-selection{position:sticky;top:4px;z-index:2;background:var(--panou);padding:8px 10px;border:1px solid var(--bordura);border-radius:8px;margin-bottom:8px}.f-selection span{flex:1}.f-selection button{min-height:36px;padding:5px 10px}.f-table-wrap{border:1px solid var(--bordura);border-radius:8px;overflow:auto}.f-table{table-layout:fixed;margin:0}.f-table th{vertical-align:middle}.f-table th:nth-child(1){width:44px}.f-table th:nth-child(3){width:95px}.f-table th:nth-child(4){width:145px}.f-table th:nth-child(5){width:90px}.f-table th:nth-child(6){width:42px}.f-table td{vertical-align:middle;padding:9px 7px}.f-table input[type=checkbox]{width:21px;height:21px;min-height:0;vertical-align:middle;cursor:pointer}.f-table tr.selected{background:var(--panou)}.f-sort{border:0;background:transparent;padding:0;min-height:32px;color:inherit;font-weight:600;text-align:left}.f-name{min-height:36px;border:0;background:transparent;padding:2px 0;text-align:left;color:var(--text);font:inherit;max-width:100%;overflow-wrap:anywhere}.f-type{font-size:.72rem;color:var(--text-slab);display:block;font-weight:400;margin-top:2px}.f-link{font-size:.75rem;color:var(--text-slab);display:block;overflow-wrap:anywhere}.f-size,.f-date,.f-mode{font-size:.8rem;overflow-wrap:anywhere}.f-mode{font-family:monospace}.f-row-actions{padding:2px 8px;min-height:36px}.f-footer{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:10px}.f-footer p{margin:0}.f-auth{max-width:570px}.f-auth label{display:block;margin-bottom:6px}.f-auth input{width:100%}.f-auth button{margin-top:12px}.f-context{position:fixed;z-index:10020;background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:5px;box-shadow:0 10px 32px #0006;min-width:200px;max-width:calc(100vw - 20px);max-height:80vh;overflow:auto}.f-context button{display:block;width:100%;text-align:left;border:0;background:transparent;min-height:38px;padding:7px 12px}.f-context button:hover,.f-context button:focus{background:var(--fundal)}.f-context .danger{color:var(--rosu)}.f-overlay{position:fixed;inset:0;background:#0009;display:flex;align-items:center;justify-content:center;padding:20px;z-index:10010}.f-dialog{width:min(540px,100%);max-height:90vh;overflow:auto;box-shadow:0 15px 60px #0008;margin:0}.f-dialog h2{font-size:1.1rem;text-transform:none}.f-dialog p{overflow-wrap:anywhere}.f-field{display:block;margin:12px 0}.f-field span{display:block;margin-bottom:6px}.f-field input{width:100%}.f-details{padding-left:20px;max-height:34vh;overflow:auto;overflow-wrap:anywhere}.f-editor{width:min(1100px,100%);height:min(860px,94vh);display:flex;flex-direction:column;gap:8px;min-height:250px}.f-editor .f-heading{margin:0}.f-editor h2{margin:0}.f-editor-path{font-family:monospace;overflow-wrap:anywhere;margin:0;font-size:.85rem}.f-editor textarea{width:100%;flex:1;min-height:140px;resize:none;white-space:pre;overflow:auto;font:14px/1.5 Consolas,monospace;tab-size:4}.f-editor .butoane{margin:0}.f-editor .nota{margin:0}.f-editor-format{color:var(--text-slab);font-size:.78rem}.f-job{border-bottom:1px solid var(--bordura);padding:10px 0}.f-job:last-child{border-bottom:0}.f-job-top{display:flex;gap:8px;justify-content:space-between;align-items:center}.f-job-name{overflow-wrap:anywhere;font-size:.9rem;flex:1}.f-job button{min-height:32px;padding:3px 9px;font-size:.8rem}.f-job progress{display:block;width:100%;height:12px;margin:7px 0;accent-color:var(--accent)}.f-job-status{font-size:.8rem;color:var(--text-slab);overflow-wrap:anywhere;margin:4px 0}.f-job.error .f-job-status{color:var(--rosu)}.f-jobs{margin-top:14px}.f-jobs h2{margin-bottom:0}.f-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
@media(max-width:900px){.f-layout{grid-template-columns:1fr}.f-shortcuts{display:flex;flex-direction:row;flex-wrap:wrap;gap:6px}.f-shortcut{border:1px solid var(--bordura);border-radius:7px;padding:2px;max-width:100%}.f-shortcut-open span{display:none}.f-side .nota{margin-top:8px}.f-side{padding:12px}.f-shortcut-controls{padding:3px}}
@media(max-width:650px){.f-top{align-items:flex-start}.f-top p{font-size:.8rem;flex:1}.f-tools{gap:6px}.f-tools button{font-size:.83rem;padding:7px 10px}.f-filter{flex-basis:100%}.f-path label{flex-basis:100%}.f-path input{font-size:.85rem}.f-table-wrap{border:0;overflow:visible}.f-table,.f-table tbody{display:block}.f-table thead{display:block}.f-table thead tr{display:flex;align-items:center;border-bottom:1px solid var(--bordura)}.f-table th{display:none;border:0}.f-table th:first-child{display:block;padding:7px}.f-table th:nth-child(2){display:block;width:auto;flex:1}.f-table tbody tr{display:grid;grid-template-columns:34px minmax(0,1fr) 38px;border:1px solid var(--bordura);border-radius:8px;margin:7px 0;padding:6px}.f-table td{border:0;padding:4px 5px}.f-table td:first-child{grid-column:1;grid-row:1/4;align-self:center}.f-table td:nth-child(2){grid-column:2;grid-row:1}.f-table td:nth-child(3){grid-column:2;grid-row:2}.f-table td:nth-child(4){grid-column:2;grid-row:3}.f-table td:nth-child(5){grid-column:2;grid-row:4}.f-table td:nth-child(6){grid-column:3;grid-row:1/5;align-self:start}.f-size:before{content:attr(data-label) ': ';color:var(--text-slab)}.f-date:before{content:attr(data-label) ': ';color:var(--text-slab)}.f-mode:before{content:attr(data-label) ': ';color:var(--text-slab);font-family:inherit}.f-name{font-size:.95rem}.f-drop{font-size:.8rem}.f-overlay{padding:8px;align-items:center}.f-editor{height:96vh;max-height:96vh;padding:12px}.f-editor textarea{font-size:13px}.f-editor .butoane button{font-size:.8rem;padding:6px 10px}.f-context{left:8px!important;right:8px;bottom:8px;top:auto!important;max-width:none;max-height:70vh}.f-context button{min-height:44px}.f-selection{top:0}.f-selection button{font-size:.8rem}.f-footer{flex-wrap:wrap}}
</style>
</head>
<body>
<main id="f-main">
<h1>__T_title__</h1>
<p class="sub">__T_intro__</p>
<p class="mesaj" id="f-message" role="status" aria-live="polite">__T_checking__</p>
<section class="card f-auth" id="f-auth">
  <h2>__T_authTitle__</h2><p class="nota">__T_authNote__</p>
  <form id="f-login"><label for="f-password">__T_password__</label><input id="f-password" type="text" name="password" autocomplete="off" autocapitalize="off" spellcheck="false" required maxlength="256"><button class="principal" type="submit" id="f-login-button">__T_login__</button></form>
</section>
<div id="f-content" hidden>
  <div class="f-top"><p class="nota">__T_connected__</p><button type="button" id="f-logout">__T_logout__</button></div>
  <section class="card" id="f-external" hidden><label><input type="checkbox" id="externPermis"> __T_external__</label><p class="nota">__T_externalNote__</p></section>
  <div class="f-layout">
    <aside class="card f-side"><div class="f-heading"><h2>__T_shortcuts__</h2><button type="button" id="f-manage">__T_manage__</button></div><div id="f-shortcuts" class="f-shortcuts"></div><p class="nota">__T_shortcutNote__</p></aside>
    <section class="f-main" id="f-browser" aria-label="__T_title__">
      <form class="f-path" id="f-path-form"><label for="f-path">__T_path__</label><input id="f-path" value="/" autocomplete="off" spellcheck="false"><button type="submit">__T_go__</button></form>
      <div class="f-tools"><button type="button" id="f-up">↑ __T_up__</button><button type="button" id="f-refresh">__T_refresh__</button><button type="button" id="f-upload-button" class="principal">__T_upload__</button><button type="button" id="f-new-dir">__T_newDir__</button><button type="button" id="f-new-file">__T_newFile__</button><input type="search" class="f-filter" id="f-filter" placeholder="__T_filter__" aria-label="__T_filter__"><input type="file" id="f-upload" multiple hidden></div>
      <div class="f-drop" id="f-drop">__T_drop__</div>
      <div class="f-selection" id="f-selection" hidden><span id="f-count"></span><button type="button" id="f-actions">__T_actions__</button><button type="button" id="f-clear">__T_clear__</button></div>
      <div class="f-table-wrap"><table class="f-table"><thead><tr><th><input type="checkbox" id="f-all" aria-label="__T_selectAll__"></th><th><button type="button" class="f-sort" data-sort="name">__T_name__</button></th><th><button type="button" class="f-sort" data-sort="size">__T_size__</button></th><th><button type="button" class="f-sort" data-sort="mtime">__T_date__</button></th><th>__T_mode__</th><th><span class="f-sr">__T_actions__</span></th></tr></thead><tbody id="f-list"></tbody></table></div>
      <p class="nota" id="f-empty" hidden></p><div class="f-footer"><p class="nota" id="f-total"></p><button type="button" id="f-more" hidden>__T_loadMore__</button></div>
    </section>
  </div>
  <section class="card f-jobs" id="f-jobs" hidden><h2>__T_jobTitle__</h2><div id="f-job-list"></div></section>
</div>
</main>
<div id="f-context" class="f-context" role="menu" hidden></div>
<div id="f-prompt-overlay" class="f-overlay" hidden><section class="card f-dialog" role="dialog" aria-modal="true" aria-labelledby="f-prompt-title" tabindex="-1"><h2 id="f-prompt-title"></h2><form id="f-prompt-form"><div id="f-prompt-body"></div><p class="mesaj eroare" id="f-prompt-error" role="alert"></p><div class="butoane"><button class="principal" id="f-prompt-ok" type="submit">__T_continue__</button><button type="button" id="f-prompt-cancel">__T_cancel__</button></div></form></section></div>
<div id="f-editor-overlay" class="f-overlay" hidden><section class="card f-dialog f-editor" role="dialog" aria-modal="true" aria-labelledby="f-editor-title" tabindex="-1"><div class="f-heading"><h2 id="f-editor-title">__T_editorTitle__</h2><button type="button" id="f-editor-close">__T_close__</button></div><p class="f-editor-path" id="f-editor-path"></p><p class="f-editor-format" id="f-editor-format"></p><textarea id="f-editor-text" aria-label="__T_editorTitle__" spellcheck="false" autocapitalize="off" autocomplete="off"></textarea><p class="mesaj" id="f-editor-message" role="status" aria-live="polite"></p><div class="butoane"><button type="button" class="principal" id="f-editor-save">__T_save__</button><button type="button" id="f-editor-reload">__T_editorReload__</button></div><p class="nota">__T_editorNote__</p></section></div>
<script>
(function(){
"use strict";
var T=__TEXTE__,CFG=__CONFIG__;
var S={authenticated:false,path:"/",parent:null,entries:[],selected:new Set(),shortcuts:[],manage:false,sort:"name",ascending:true,offset:0,total:0,more:false,loading:false,request:0,editor:null,jobs:new Map(),uploads:[],uploading:false,prompt:null,contextAnchor:null};
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var n=document.createElement(tag);if(cls){n.className=cls;}if(text!==undefined){n.textContent=text;}return n;}
function fmt(text){var values=Array.prototype.slice.call(arguments,1),i=0;return String(text).replace(/%s/g,function(){return String(values[i++]);});}
function message(text,error){$("f-message").textContent=text||"";$("f-message").classList.toggle("eroare",!!error);}
function fail(error){if(error&&error.auth){return;}message(error&&error.message||T.network,true);}
function joined(base,name){return (base==="/"?"/":base.replace(/\/$/,"")+"/")+name;}
function basename(path){return path.replace(/\/$/,"").split("/").pop()||"/";}
function bytes(n){n=Number(n)||0;if(n<1024){return n+" "+T.bytes;}var u=["KiB","MiB","GiB","TiB"],i=-1;do{n/=1024;i++;}while(n>=1024&&i<u.length-1);return n.toLocaleString(undefined,{maximumFractionDigits:1})+" "+u[i];}
function date(n){if(!n){return "—";}var d=new Date(Number(n)*1000);return isNaN(d.getTime())?String(n):d.toLocaleString();}
function setAuth(value,expired){S.authenticated=!!value;$("f-auth").hidden=value;$("f-content").hidden=!value;if(!value){hideContext();if(S.prompt){closePrompt(null);}$("f-editor-overlay").hidden=true;if(expired){message(T.authExpired,true);$("f-password").focus();}}else if(S.editor){$("f-editor-overlay").hidden=false;}}
function showAccess(d){$("f-external").hidden=!d.local;$("externPermis").checked=!!d.extern_permis;}
async function api(route,data,options){
  options=options||{};var o={method:data===undefined?"GET":"POST",credentials:"same-origin",cache:"no-store",headers:{"X-HDS-CSRF":CFG.csrf||""}},path="/api/fisiere-"+route;
  if(data!==undefined){o.headers["Content-Type"]="application/json";o.body=JSON.stringify(data);}if(options.raw){o.headers["Content-Type"]="application/octet-stream";o.body=options.raw;o.method="POST";}if(options.signal){o.signal=options.signal;}
  var r;try{r=await fetch(path,o);}catch(e){if(e.name==="AbortError"){throw e;}throw new Error(T.network);}
  var d;try{d=await r.json();}catch(e){throw new Error(fmt(T.badResponse,r.status));}
  if(r.status===401){setAuth(false,route!=="login");var authError=new Error(d.message||T.authExpired);authError.auth=true;if(route==="login"){message(authError.message,true);}throw authError;}
  if(!r.ok||d.result===false){var error=new Error(d.message||T.failed);error.response=d;throw error;}return d;
}
function visible(){var q=$("f-filter").value.toLocaleLowerCase();return S.entries.filter(function(x){return !q||x.name.toLocaleLowerCase().indexOf(q)!==-1;}).sort(function(a,b){if((a.type==="directory")!==(b.type==="directory")){return a.type==="directory"?-1:1;}var v=S.sort==="name"?a.name.localeCompare(b.name):Number(a[S.sort]||0)-Number(b[S.sort]||0);return S.ascending?v:-v;});}
function selected(){return S.entries.filter(function(x){return S.selected.has(x.path);});}
function updateSelection(){var list=visible(),n=S.selected.size;$("f-count").textContent=fmt(T.selected,n);$("f-selection").hidden=!n;$("f-all").checked=!!list.length&&list.every(function(x){return S.selected.has(x.path);});$("f-all").indeterminate=list.some(function(x){return S.selected.has(x.path);})&&!$("f-all").checked;Array.prototype.forEach.call($("f-list").children,function(row){var checked=S.selected.has(row.dataset.path);row.classList.toggle("selected",checked);row.querySelector("input").checked=checked;});}
function renderList(){
  var body=$("f-list"),list=visible();body.textContent="";list.forEach(function(x){
    var row=el("tr");row.dataset.path=x.path;var cell=el("td"),check=el("input");check.type="checkbox";check.setAttribute("aria-label",fmt(T.select,x.name));check.addEventListener("change",function(){if(check.checked){S.selected.add(x.path);}else{S.selected.delete(x.path);}updateSelection();});cell.appendChild(check);row.appendChild(cell);
    cell=el("td");var name=el("button","f-name",(x.type==="directory"?"▸ ":x.type==="symlink"?"↗ ":"")+x.name);name.type="button";name.addEventListener("click",function(){openEntry(x);});cell.appendChild(name);cell.appendChild(el("span","f-type",x.type==="directory"?T.folder:x.type==="symlink"?T.link:x.type==="file"?T.file:T.other));if(x.link_target!==undefined){cell.appendChild(el("span","f-link",fmt(T.linkTo,x.link_target)));}row.appendChild(cell);
    [["f-size",T.size,x.type==="directory"?"—":bytes(x.size)],["f-date",T.date,date(x.mtime)],["f-mode",T.mode,x.mode||"—"]].forEach(function(v){var td=el("td",v[0],v[2]);td.dataset.label=v[1];row.appendChild(td);});
    cell=el("td");var act=el("button","f-row-actions","⋮");act.type="button";act.setAttribute("aria-label",T.actions+": "+x.name);act.addEventListener("click",function(e){e.stopPropagation();if(!S.selected.has(x.path)){S.selected.clear();S.selected.add(x.path);updateSelection();}showContext(act);});cell.appendChild(act);row.appendChild(cell);
    row.addEventListener("contextmenu",function(e){e.preventDefault();if(!S.selected.has(x.path)){S.selected.clear();S.selected.add(x.path);updateSelection();}showContext(act,e.clientX,e.clientY);});body.appendChild(row);
  });$("f-empty").hidden=!!list.length;$("f-empty").textContent=S.entries.length?T.noMatch:T.empty;$("f-total").textContent=fmt(T.shown,S.entries.length,S.total);$("f-more").hidden=!S.more;$("f-up").disabled=S.path==="/"||!S.parent;$("f-path").value=S.path;updateSelection();
}
async function load(path,append){
  var id=++S.request;S.loading=true;$("f-browser").setAttribute("aria-busy","true");$("f-more").disabled=true;message(T.loading);
  try{var d=await api("list?cale="+encodeURIComponent(path||S.path)+"&offset="+(append?S.entries.length:0));if(id!==S.request){return;}S.path=d.path;S.parent=d.parent;if(!append){S.selected.clear();S.offset=0;}S.entries=append?S.entries.concat(d.entries||[]):d.entries||[];S.total=d.total===undefined?S.entries.length:d.total;S.more=!!d.has_more;renderList();message("");}catch(e){if(id===S.request){fail(e);}}finally{if(id===S.request){S.loading=false;$("f-browser").removeAttribute("aria-busy");$("f-more").disabled=false;}}
}
function linkTarget(x){if(x.resolved_path){return x.resolved_path;}if(!x.link_target){return null;}return x.link_target.charAt(0)==="/"?x.link_target:joined(x.path.slice(0,x.path.lastIndexOf("/"))||"/",x.link_target);}
async function openPath(path){try{var d=await api("list?cale="+encodeURIComponent(path)+"&offset=0");++S.request;S.path=d.path;S.parent=d.parent;S.entries=d.entries||[];S.selected.clear();S.total=d.total===undefined?S.entries.length:d.total;S.more=!!d.has_more;renderList();message("");}catch(e){if(e.auth){throw e;}await openEditor(path);}}
function openEntry(x){if(x.type==="directory"||x.is_directory){load(x.path);}else if(x.type==="symlink"){var target=linkTarget(x);if(target){openPath(target).catch(fail);}else{message(T.missingTarget,true);}}else{openEditor(x.path).catch(fail);}}
function hideContext(){var was=!$("f-context").hidden;$("f-context").hidden=true;if(was&&S.contextAnchor){S.contextAnchor.focus();}S.contextAnchor=null;}
function showContext(anchor,x,y){
  var list=selected();if(!list.length){message(T.chooseAny,true);return;}var menu=$("f-context");menu.textContent="";S.contextAnchor=anchor;var actions=[["open",T.open],["edit",T.edit],["download",T.download],["copy",T.copy],["move",T.move],["rename",T.rename],["chmod",T.mode],["shortcut",T.addShortcut],["delete",T.delete]];
  actions.forEach(function(a){if(list.length!==1&&["open","edit","rename"].indexOf(a[0])!==-1){return;}if(a[0]==="edit"&&(list[0].type==="directory"||list[0].is_directory)){return;}if(a[0]==="download"&&list.some(function(v){return v.type!=="file"&&!(v.type==="symlink"&&v.resolved_path&&!v.is_directory);})){return;}var text=a[0]==="open"&&list[0].type==="symlink"?T.openTarget:a[1],b=el("button",a[0]==="delete"?"danger":"",text);b.type="button";b.setAttribute("role","menuitem");b.addEventListener("click",function(){hideContext();runAction(a[0],list).catch(fail);});menu.appendChild(b);});
  menu.hidden=false;var rect=anchor.getBoundingClientRect();menu.style.left=Math.max(8,Math.min(x===undefined?rect.left:x,window.innerWidth-menu.offsetWidth-8))+"px";menu.style.top=Math.max(8,Math.min(y===undefined?rect.bottom:y,window.innerHeight-menu.offsetHeight-8))+"px";menu.querySelector("button").focus();
}
var lastFocus=null;
function closePrompt(value){var callback=S.prompt;S.prompt=null;$("f-prompt-overlay").hidden=true;if(lastFocus&&document.contains(lastFocus)){lastFocus.focus();}if(callback){callback(value);}}
function promptForm(title,fields,note,ok,details){
  hideContext();if(S.prompt){closePrompt(null);}lastFocus=document.activeElement;$("f-prompt-title").textContent=title;$("f-prompt-ok").textContent=ok||T.continue;$("f-prompt-error").textContent="";var body=$("f-prompt-body");body.textContent="";
  if(note){body.appendChild(el("p","nota",note));}if(details&&details.length){var ul=el("ul","f-details");details.forEach(function(v){ul.appendChild(el("li","",v));});body.appendChild(ul);}
  (fields||[]).forEach(function(f){var label=el("label","f-field"),input=el("input");label.appendChild(el("span","",f.label));input.name=f.name;input.value=f.value||"";input.required=true;input.autocomplete="off";input.spellcheck=false;if(f.max){input.maxLength=f.max;}label.appendChild(input);body.appendChild(label);});$("f-prompt-overlay").hidden=false;var first=body.querySelector("input")||$("f-prompt-ok");first.focus();if(first.select){first.select();}return new Promise(function(resolve){S.prompt=resolve;});
}
$("f-prompt-form").addEventListener("submit",function(e){e.preventDefault();var result={},valid=true;Array.prototype.forEach.call($("f-prompt-body").querySelectorAll("input"),function(i){var v=i.value.trim();if(!v){$("f-prompt-error").textContent=T.required;valid=false;}if(i.name==="name"&&(v==="."||v===".."||v.indexOf("/")!==-1)){valid=false;$("f-prompt-error").textContent=T.invalidName;}if(i.name==="mode"&&!/^[0-7]{3,4}$/.test(v)){valid=false;$("f-prompt-error").textContent=T.invalidMode;}result[i.name]=v;});if(valid){closePrompt(result);}});
$("f-prompt-cancel").addEventListener("click",function(){closePrompt(null);});
async function confirmed(route,payload){
  var d=await api(route,payload);while(d.confirmare){var c=d.confirmare,answer=await promptForm(c.intrebare||T.confirm,[],c.avertisment||"",c.buton||T.confirmAction,c.detalii||[]);if(!answer){return null;}payload=Object.assign({},payload,{cod:c.cod});d=await api(route,payload);}return d;
}
async function operate(payload,label){var d=await confirmed("operate",payload);if(!d){return;}if(d.job){watchJob(d.job,label||T.running);}else{message(d.message||T.done);await load(S.path);}return d;}
async function runAction(action,list){
  list=list||selected();if(!list.length){message(T.chooseAny,true);return;}var one=list[0],paths=list.map(function(x){return x.path;});
  if(action==="open"){var target=one.type==="symlink"?linkTarget(one):one.path;if(target){await openPath(target);}else{message(T.missingTarget,true);}return;}if(action==="edit"){await openEditor(one.resolved_path||one.path);return;}if(action==="download"){if(list.some(function(x){return x.type!=="file"&&!(x.type==="symlink"&&x.resolved_path&&!x.is_directory);})){message(T.downloadFolders,true);return;}var access=await api("status");if(!access.autentificat){setAuth(false,true);return;}list.forEach(function(x){var a=el("a");a.href="/api/fisiere-download?cale="+encodeURIComponent(x.resolved_path||x.path);a.download=x.name;document.body.appendChild(a);a.click();a.remove();});return;}
  if(action==="shortcut"){for(var i=0;i<list.length;i++){var s=list[i],r=await promptForm(T.addShortcut,[{name:"name",label:T.shortcutName,value:s.name,max:100}],s.path);if(!r){break;}await api("shortcuts",{action:"add",name:r.name,path:s.path});}await loadShortcuts();message(T.shortcutAdded);return;}
  var payload={action:action,items:paths},answer;if(action==="copy"||action==="move"){answer=await promptForm(action==="copy"?T.copy:T.move,[{name:"destination",label:T.destination,value:S.path}],null,null,paths);if(!answer){return;}payload.destination=answer.destination;}
  if(action==="rename"){answer=await promptForm(T.rename,[{name:"name",label:T.newName,value:one.name,max:255}],one.path);if(!answer){return;}payload.name=answer.name;}
  if(action==="chmod"){answer=await promptForm(T.mode,[{name:"mode",label:T.mode,value:one.mode||"0644",max:4}],T.chmodHelp,null,paths);if(!answer){return;}payload.mode=answer.mode;}
  await operate(payload,(T[action]||T.running)+": "+list.map(function(x){return x.name;}).join(", "));
}
async function newEntry(action){var r=await promptForm(action==="mkdir"?T.newDir:T.newFile,[{name:"name",label:T.name,value:"",max:255}],S.path);if(r){await operate({action:action,items:[],destination:S.path,name:r.name},r.name);}}
function makeJob(id,label,cancel){
  var old=S.jobs.get(id);if(old){return old;}var row=el("div","f-job"),top=el("div","f-job-top"),title=el("span","f-job-name",label),stop=el("button","",T.stop),bar=el("progress"),status=el("p","f-job-status",T.running);stop.type="button";top.appendChild(title);top.appendChild(stop);row.appendChild(top);row.appendChild(bar);row.appendChild(status);$("f-job-list").appendChild(row);$("f-jobs").hidden=false;var job={id:id,row:row,title:title,stop:stop,bar:bar,status:status,done:false};stop.addEventListener("click",function(){stop.disabled=true;Promise.resolve(cancel()).catch(function(e){stop.disabled=false;fail(e);});});S.jobs.set(id,job);return job;
}
function jobProgress(job,current,total,text){if(total>0){job.bar.max=total;job.bar.value=Math.min(current,total);}else{job.bar.removeAttribute("value");}job.status.textContent=text||T.running;}
function finishJob(job,text,error){job.done=true;job.stop.hidden=true;job.row.classList.toggle("error",!!error);job.bar.max=1;job.bar.value=1;job.status.textContent=text;}
function watchJob(id,label){
  if(typeof id==="object"){id=id.id;}var j=makeJob("job-"+id,label,function(){return api("cancel",{id:id});});
  async function poll(){if(!S.authenticated){setTimeout(poll,1200);return;}try{var d=await api("job?id="+encodeURIComponent(id)),v=d.job;jobProgress(j,v.bytes||0,v.total||0,T.running+(v.total?" · "+bytes(v.bytes)+" / "+bytes(v.total):v.bytes?" · "+bytes(v.bytes):""));if(v.state==="running"||v.state==="queued"){setTimeout(poll,700);return;}var output=v.output||{},errors=output.errors||[],bad=v.state==="error"||errors.length>0,text=v.state==="error"?(v.error||T.failed):v.state==="cancelled"?T.cancelled+" "+T.cancelNote:T.done;if(output.results){text+=" "+fmt(T.resultCount,output.results.length);}if(errors.length){text+=" "+fmt(T.errorCount,errors.length)+" "+errors.map(function(e){return e.path+": "+e.message;}).join(" · ");}finishJob(j,text,bad);await load(S.path);}catch(e){if(e.auth){setTimeout(poll,1500);}else{finishJob(j,e.message||T.network,true);}}}poll();
}
async function loadShortcuts(){try{var d=await api("shortcuts");S.shortcuts=d.items||d.shortcuts||[];renderShortcuts();}catch(e){fail(e);}}
function renderShortcuts(){
  var body=$("f-shortcuts");body.textContent="";$("f-manage").textContent=S.manage?T.finish:T.manage;if(!S.shortcuts.length){body.appendChild(el("p","nota",T.noShortcuts));return;}
  S.shortcuts.forEach(function(s,index){var row=el("div","f-shortcut"),open=el("button","f-shortcut-open",s.name);open.type="button";open.title=s.path;open.appendChild(el("span","",s.path));open.addEventListener("click",function(){openPath(s.path).catch(fail);});row.appendChild(open);
    if(S.manage){var buttons=el("div","f-shortcut-controls");[[T.rename,"rename"],["↑","up"],["↓","down"],[T.shortcutRemove,"remove"]].forEach(function(v){var b=el("button","",v[0]);b.type="button";b.setAttribute("aria-label",v[1]==="up"?T.shortcutUp:v[1]==="down"?T.shortcutDown:v[0]);b.disabled=v[1]==="up"&&index===0||v[1]==="down"&&index===S.shortcuts.length-1;b.addEventListener("click",function(){changeShortcut(s,index,v[1]).catch(fail);});buttons.appendChild(b);});row.appendChild(buttons);}body.appendChild(row);});
}
async function changeShortcut(s,index,action){var data={action:action,id:s.id};if(action==="rename"){var r=await promptForm(T.rename,[{name:"name",label:T.shortcutName,value:s.name,max:100}],s.path);if(!r){return;}data.name=r.name;}if(action==="up"||action==="down"){var order=S.shortcuts.map(function(x){return x.id;}),target=index+(action==="up"?-1:1),tmp=order[index];order[index]=order[target];order[target]=tmp;data={action:"reorder",order:order};}await api("shortcuts",data);await loadShortcuts();if(action==="remove"){message(T.shortcutRemoved);}}
function editorDirty(){return S.editor&&$("f-editor-text").value!==S.editor.original;}
function editorMessage(text,error){$("f-editor-message").textContent=text||"";$("f-editor-message").classList.toggle("eroare",!!error);}
async function allowEditorClose(){if(!editorDirty()){return true;}return !!(await promptForm(T.unsaved,[],"",T.continue));}
async function openEditor(path){
  if(S.editor&&!(await allowEditorClose())){return;}var d=await api("editor?cale="+encodeURIComponent(path));S.editor={path:d.path||path,original:"",version:d.version,format:d.format};$("f-editor-path").textContent=S.editor.path;$("f-editor-text").value=d.text;S.editor.original=$("f-editor-text").value;var f=d.format||{};$("f-editor-format").textContent=[f.encoding,f.eol,bytes(d.size||0)].filter(Boolean).join(" · ");editorMessage("");$("f-editor-overlay").hidden=false;$("f-editor-text").focus();
}
async function closeEditor(){if(await allowEditorClose()){S.editor=null;$("f-editor-overlay").hidden=true;$("f-path").focus();}}
$("f-editor-close").addEventListener("click",function(){closeEditor().catch(fail);});
$("f-editor-text").addEventListener("input",function(){editorMessage(editorDirty()?T.modified:"");});
$("f-editor-save").addEventListener("click",async function(){if(!S.editor){return;}var button=$("f-editor-save"),text=$("f-editor-text").value;button.disabled=true;editorMessage(T.pending);try{var d=await confirmed("save",{cale:S.editor.path,text:text,version:S.editor.version,format:S.editor.format});if(!d){editorMessage(T.modified);return;}S.editor.original=text;S.editor.version=d.version||(d.editor&&d.editor.version)||S.editor.version;S.editor.format=d.format||S.editor.format;editorMessage(T.saved);load(S.path);}catch(e){editorMessage(e.message||T.failed,true);}finally{button.disabled=false;}});
$("f-editor-reload").addEventListener("click",function(){if(S.editor){openEditor(S.editor.path).catch(function(e){editorMessage(e.message,true);});}});
function queueUploads(files){Array.prototype.forEach.call(files,function(file){S.uploads.push({file:file,path:joined(S.path,file.name),cancelled:false,id:null,controller:null});});pumpUploads();}
async function pumpUploads(){
  if(S.uploading){return;}S.uploading=true;
  while(S.uploads.length){var item=S.uploads.shift(),file=item.file,job=makeJob("upload-"+Date.now()+"-"+Math.random(),fmt(T.uploading,file.name),async function(){item.cancelled=true;if(item.controller){item.controller.abort();}if(item.id){await api("upload-abort",{id:item.id});}});try{
    var start=await confirmed("upload-start",{cale:item.path,size:file.size});if(!start){finishJob(job,fmt(T.uploadCancelled,file.name),false);continue;}item.id=start.id;var offset=start.offset||0;
    while(offset<file.size){if(item.cancelled){break;}item.controller=new AbortController();var end=Math.min(offset+65536,file.size),chunk=file.slice(offset,end);var response=await api("upload-chunk?id="+encodeURIComponent(item.id)+"&offset="+offset,undefined,{raw:chunk,signal:item.controller.signal});offset=response.offset===undefined?end:response.offset;jobProgress(job,offset,file.size,bytes(offset)+" / "+bytes(file.size)+" · "+Math.floor(offset/Math.max(1,file.size)*100)+" %");}
    if(item.cancelled){throw {name:"AbortError"};}var done=await confirmed("upload-commit",{id:item.id});if(!done){await api("upload-abort",{id:item.id});finishJob(job,fmt(T.uploadCancelled,file.name),false);continue;}finishJob(job,fmt(T.uploadDone,file.name),false);
  }catch(e){if(item.id){try{await api("upload-abort",{id:item.id});}catch(ignore){}}finishJob(job,e.name==="AbortError"?fmt(T.uploadCancelled,file.name):fmt(T.uploadFailed,file.name)+" "+(e.message||T.failed),e.name!=="AbortError");if(e.auth){S.uploads=[];}}
  }S.uploading=false;if(S.authenticated){await load(S.path);}
}
$("f-login").addEventListener("submit",async function(e){e.preventDefault();var b=$("f-login-button");b.disabled=true;message(T.checking);try{await api("login",{parola:$("f-password").value});$("f-password").value="";setAuth(true);showAccess(await api("status"));await Promise.all([load(S.path),loadShortcuts()]);}catch(error){fail(error);}finally{b.disabled=false;}});
$("externPermis").addEventListener("change",async function(){var input=$("externPermis"),value=input.checked;input.disabled=true;try{var d=await api("access",{permis:value});input.checked=d.extern_permis===undefined?value:!!d.extern_permis;message(d.message||T.externalSaved);}catch(e){input.checked=!value;fail(e);}finally{input.disabled=false;}});
$("f-logout").addEventListener("click",async function(){try{await api("logout",{});setAuth(false);message("");}catch(e){fail(e);}});
$("f-path-form").addEventListener("submit",function(e){e.preventDefault();load($("f-path").value.trim()||"/");});
$("f-up").addEventListener("click",function(){if(S.parent){load(S.parent);}});$("f-refresh").addEventListener("click",function(){load(S.path);loadShortcuts();});$("f-more").addEventListener("click",function(){load(S.path,true);});$("f-filter").addEventListener("input",renderList);
$("f-all").addEventListener("change",function(){var value=$("f-all").checked;visible().forEach(function(x){if(value){S.selected.add(x.path);}else{S.selected.delete(x.path);}});updateSelection();});$("f-clear").addEventListener("click",function(){S.selected.clear();updateSelection();});$("f-actions").addEventListener("click",function(e){e.stopPropagation();showContext($("f-actions"));});
Array.prototype.forEach.call(document.querySelectorAll("[data-sort]"),function(b){b.addEventListener("click",function(){var key=b.dataset.sort;S.ascending=S.sort===key?!S.ascending:true;S.sort=key;renderList();});});
$("f-manage").addEventListener("click",function(){S.manage=!S.manage;renderShortcuts();});$("f-new-dir").addEventListener("click",function(){newEntry("mkdir").catch(fail);});$("f-new-file").addEventListener("click",function(){newEntry("touch").catch(fail);});
$("f-upload-button").addEventListener("click",function(){$("f-upload").click();});$("f-upload").addEventListener("change",function(){queueUploads($("f-upload").files);$("f-upload").value="";});
var dragDepth=0;$("f-browser").addEventListener("dragenter",function(e){if(!e.dataTransfer||Array.prototype.indexOf.call(e.dataTransfer.types,"Files")===-1){return;}e.preventDefault();dragDepth++;$("f-drop").classList.add("active");$("f-drop").textContent=T.dropNow;});$("f-browser").addEventListener("dragover",function(e){e.preventDefault();if(e.dataTransfer){e.dataTransfer.dropEffect="copy";}});$("f-browser").addEventListener("dragleave",function(){dragDepth=Math.max(0,dragDepth-1);if(!dragDepth){$("f-drop").classList.remove("active");$("f-drop").textContent=T.drop;}});$("f-browser").addEventListener("drop",function(e){e.preventDefault();dragDepth=0;$("f-drop").classList.remove("active");$("f-drop").textContent=T.drop;if(e.dataTransfer){queueUploads(e.dataTransfer.files);}});
document.addEventListener("click",function(e){if(!$("f-context").contains(e.target)){hideContext();}});
document.addEventListener("keydown",function(e){
  if(!$("f-context").hidden){var buttons=Array.prototype.slice.call($("f-context").querySelectorAll("button")),index=buttons.indexOf(document.activeElement);if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();buttons[(index+(e.key==="ArrowDown"?1:-1)+buttons.length)%buttons.length].focus();return;}if(e.key==="Escape"){e.preventDefault();hideContext();return;}}
  var overlay=!$("f-prompt-overlay").hidden?$("f-prompt-overlay"):!$("f-editor-overlay").hidden?$("f-editor-overlay"):null;
  if(overlay){if(e.key==="Tab"){var focusable=Array.prototype.slice.call(overlay.querySelectorAll("button:not(:disabled),input:not(:disabled),textarea:not(:disabled),[tabindex='0']")),first=focusable[0],last=focusable[focusable.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}if(e.key==="Escape"){e.preventDefault();if(S.prompt){closePrompt(null);}else{closeEditor().catch(fail);}}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="s"&&overlay===$("f-editor-overlay")){e.preventDefault();$("f-editor-save").click();}return;}
  if(!S.authenticated||/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)){return;}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="a"){e.preventDefault();visible().forEach(function(x){S.selected.add(x.path);});updateSelection();}if(e.key==="Delete"){e.preventDefault();runAction("delete").catch(fail);}if(e.key==="F2"){e.preventDefault();if(selected().length===1){runAction("rename").catch(fail);}else{message(T.chooseOne,true);}}
});
window.addEventListener("beforeunload",function(e){if(editorDirty()||S.uploading){e.preventDefault();e.returnValue="";}});window.addEventListener("focus",function(){if(S.authenticated){loadShortcuts();}});setInterval(function(){if(S.authenticated&&!document.hidden&&!S.manage){loadShortcuts();}},30000);
async function boot(){try{var d=await api("status");showAccess(d);setAuth(d.autentificat);if(d.autentificat){await Promise.all([load(S.path),loadShortcuts()]);}else{message("");}}catch(e){fail(e);}}
boot();
})();
</script>
</body>
</html>'''
