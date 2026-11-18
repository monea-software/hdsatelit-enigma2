# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Pagina /fisiere: navigatorul cu doua panouri. Cadrul, meniul si paleta sunt aplicate de cadru_web.

In stanga calculatorul (sau telefonul) de pe care e deschis browserul, in dreapta receptorul. Intre panouri:
copiere, mutare, stergere, redenumire, dosar nou, fisier nou si editare, in ambele sensuri, cu butoane mari,
cu tastele F2-F8, Tab, Insert si cu tragerea cu mouse-ul (simpla copiaza, cu Shift muta).

Panoul calculatorului are doua moduri (designul din Stitch, proiectul interfetei web, ecranul 98442a18...):
- intreg: Chrome/Edge pe adresa https a receptorului (https_web.py): alegerea dosarului (showDirectoryPicker),
  citire, scriere, stergere, creare; dosarul ales se tine minte in browser (IndexedDB);
- simplu: orice alt browser sau adresa http: fisierele alese sau trase din Explorer se copiaza pe receptor, iar de
  pe receptor se copiaza prin descarcare. Pe http (cum intra omul din casa) asta e ce vede intai, fara sa fie trimis
  spre avertismentul certificatului; adresa https ramane o legatura mica sub butoane, pentru cine o alege (browserul da
  voie la dosarele calculatorului numai pe https, isSecureContext). Ce nu merge spune de ce, cand omul il cere.
Latimea panoului calculatorului sta in variabila CSS --f-st (bara dintre panouri), nu in --st: --st e marginea paginii
din cadru_web (16-32 px), iar cu acelasi nume panoul calculatorului ramanea lat de 16-32 px.
API-ul receptorului e cel de pana acum (fisiere_web.py): cookie-ul fisierelor, CSRF-ul browserului asociat,
confirmarile serverului la stergere si la inlocuire.
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
		"intro": _("Navigatorul cu două panouri: calculatorul în stânga, receptorul în dreapta."),
		"authTitle": _("Parola receptorului"),
		"authNote": _("Din afara casei se cere parola utilizatorului root al receptorului, o dată în această sesiune a browserului. În casă fișierele se deschid fără parolă."),
		"password": _("Parolă"),
		"login": _("Deschide fișierele"),
		"logout": _("Închide accesul"),
		"checking": _("Se verifică accesul..."),
		"authExpired": _("Accesul la fișiere a expirat. Introdu din nou parola receptorului."),
		"external": _("Permite accesul la fișiere din afara casei"),
		"externalSaved": _("Setarea accesului din afara casei a fost salvată."),
		"pc": _("Calculatorul"),
		"rx": _("Receptorul"),
		"active": _("Activ"),
		"chooseDir": _("Alege dosarul"),
		"reopenDir": _("Redeschide %s"),
		"chooseFiles": _("Alege fișiere"),
		"chooseFolder": _("Alege un dosar"),
		"pcEmpty": _("Alege un dosar de pe calculator. Apoi copiezi, muți, ștergi și editezi în ambele sensuri."),
		"pcSimpleEmpty": _("Alege fișiere sau un dosar de pe calculator ori trage-le aici din Explorer. Le copiezi pe receptor cu Copiază →; de pe receptor copiezi pe calculator prin descărcare."),
		"pcHttp": _("Pe această adresă browserul nu dă voie paginii să lucreze cu dosarele calculatorului. Pe adresa criptată a receptorului merg toate: copiere, mutare, ștergere, redenumire, creare și editare."),
		"openHttps": _("Deschide cu panoul calculatorului"),
		"httpsWarn": _("Prima dată Chrome arată Conexiunea nu este privată: apasă Avansate, apoi Accesați hdsatelit.local (nesigur). Certificatul e făcut de receptorul tău, nu de o firmă, de aceea întreabă."),
		"httpsOff": _("Adresa criptată a receptorului nu merge acum: %s"),
		"otherBrowser": _("Acest browser nu are alegerea dosarului. Pentru panoul calculatorului întreg folosește Chrome sau Edge pe calculator."),
		"phone": _("Pe telefon poți alege fișiere și le poți copia pe receptor; de pe receptor le copiezi pe telefon prin descărcare."),
		"limited": _("Pe calculator asta merge numai în Chrome sau Edge, pe adresa criptată a receptorului (butonul Deschide cu panoul calculatorului)."),
		"limitedFolders": _("Dosarele receptorului se copiază pe calculator numai în Chrome sau Edge, pe adresa criptată a receptorului. Aici poți descărca fișiere."),
		"permission": _("Browserul nu mai are voie la dosarul ales. Apasă Alege dosarul."),
		"shortcuts": _("Scurtături"),
		"shortcutRemoveAsk": _("Elimini scurtătura %s? Dosarul rămâne pe receptor."),
		"path": _("Cale"),
		"up": _("Dosarul de sus"),
		"refresh": _("Reîncarcă"),
		"name": _("Nume"),
		"size": _("Mărime"),
		"date": _("Modificat"),
		"mode": _("Permisiuni"),
		"selectAll": _("Selectează tot"),
		"select": _("Selectează %s"),
		"selection": _("Selectate: %s din %s · %s"),
		"locked": _("Fișierul are parole sau chei ale sistemului și nu se deschide din browser."),
		"lockedShort": _("sistem"),
		"empty": _("Dosarul este gol."),
		"loading": _("Se citește dosarul..."),
		"folder": _("Dosar"),
		"link": _("Legătură către %s"),
		"keyView": _("Vezi"),
		"keyEdit": _("Editează"),
		"copyRight": _("Copiază →"),
		"copyLeft": _("← Copiază"),
		"move": _("Mută"),
		"newDir": _("Dosar nou"),
		"newFile": _("Fișier nou"),
		"rename": _("Redenumește"),
		"delete": _("Șterge"),
		"download": _("Descarcă"),
		"addShortcut": _("Adaugă la scurtături"),
		"shortcutName": _("Numele scurtăturii"),
		"shortcutAdded": _("Scurtătură adăugată."),
		"open": _("Deschide"),
		"copyAsk": _("Copiezi %s în %s?"),
		"moveAsk": _("Muți %s în %s?"),
		"deleteAsk": _("Ștergi definitiv de pe calculator %s?"),
		"items": _("%s elemente"),
		"from": _("Din: %s"),
		"destination": _("Dosarul destinație"),
		"newName": _("Numele nou"),
		"overwriteAsk": _("%s există deja în destinație. Îl înlocuiești?"),
		"chmodHelp": _("Permisiunile în format octal, de exemplu 0644 pentru un fișier sau 0755 pentru un dosar."),
		"invalidMode": _("Scrie 3 sau 4 cifre între 0 și 7."),
		"invalidName": _("Scrie un nume fără / și diferit de . și .."),
		"required": _("Completează câmpul."),
		"exists": _("Există deja un element cu acest nume."),
		"continue": _("Continuă"),
		"cancel": _("Renunță"),
		"close": _("Închide"),
		"confirm": _("Confirmare"),
		"confirmAction": _("Da, continuă"),
		"done": _("Operațiunea s-a încheiat."),
		"cancelled": _("Operațiune oprită. Ce s-a prelucrat deja rămâne."),
		"jobTitle": _("Operațiuni"),
		"stop": _("Oprește"),
		"running": _("În lucru"),
		"failed": _("Operațiunea nu a reușit."),
		"resultCount": _("Elemente prelucrate: %s."),
		"errorCount": _("Elemente neprelucrate: %s."),
		"skipped": _("Fișiere sărite, cu parole ale sistemului: %s."),
		"chooseAny": _("Selectează mai întâi un fișier sau un dosar."),
		"chooseOne": _("Alege un singur element pentru această acțiune."),
		"needFile": _("Alege un fișier, nu un dosar."),
		"samePanel": _("Sursa și destinația sunt același dosar."),
		"network": _("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
		"badResponse": _("Receptorul a răspuns neașteptat (HTTP %s)."),
		"copyingTo": _("Se copiază pe %s: %s"),
		"copyFile": _("%s din %s fișiere"),
		"editorTitle": _("Editor de text"),
		"viewTitle": _("Vezi fișierul"),
		"save": _("Salvează"),
		"saved": _("Fișier salvat."),
		"savedDownload": _("Browserul descarcă versiunea nouă; pune-o în locul celei vechi."),
		"unsaved": _("Ai modificări nesalvate. Le abandonezi?"),
		"modified": _("Modificări nesalvate"),
		"editorNote": _("Fișierul se salvează cu codarea și sfârșiturile de linie pe care le avea. Pe receptor versiunea de dinainte rămâne în dosarul .copii."),
		"editorReload": _("Reîncarcă fișierul"),
		"binary": _("Fișierul conține date binare și nu poate fi deschis ca text."),
		"tooLarge": _("Editorul deschide fișiere de cel mult 1 MiB."),
		"notUtf8": _("Fișierul nu e scris în UTF-8; se poate citi aici, dar se salvează numai din editorul receptorului."),
		"mixedEol": _("Fișierul are sfârșituri de linie amestecate; se poate citi, dar nu se salvează de aici."),
		"tabPc": _("Calculatorul"),
		"tabRx": _("Receptorul"),
		"dropHere": _("Lasă aici"),
		"bytes": _("octeți"),
		"keysNote": _("Tab schimbă panoul, Insert bifează, Enter deschide, Backspace urcă. Tragerea copiază, cu Shift mută."),
	}


def _json(date):
	return (json.dumps(date, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c")
		.replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def pagina_text(stil, config_pagina, https=None):
	"""https: starea din https_web.stare() plus "sigur" (cererea a venit pe https)."""
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
	text = text.replace("__TEXTE__", _json(texte)).replace("__CONFIG__", _json(config or {}))
	return _cuLimba(text.replace("__HTTPS__", _json(https or {})))


PAGINA = r'''<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="same-origin">
<title>__T_title__</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
main{max-width:none;margin:0 auto;min-width:0}.ascuns,[hidden]{display:none!important}
.f-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin:0 0 8px}.f-head h1{font-size:1.25rem;margin:0}.f-head p{margin:0;color:var(--text-slab);font-size:.85rem;flex:1}.f-head label{font-size:.8rem;color:var(--text-slab)}.f-head button{min-height:32px;padding:4px 10px;font-size:.8rem}
.f-auth{max-width:570px}.f-auth input{width:100%}.f-auth button{margin-top:12px}
.f-tabs{display:none;gap:6px;margin-bottom:6px}.f-tabs button{flex:1;min-height:44px}.f-tabs button.on{background:var(--accent);color:#fff}
.f-panes{display:flex;gap:0;align-items:stretch;height:calc(100vh - 230px);min-height:380px}
.f-pane{display:flex;flex-direction:column;min-width:0;border:1px solid var(--bordura);border-radius:10px;background:var(--panou);overflow:hidden}
#f-pane-0{flex:0 0 var(--f-st,50%)}#f-pane-1{flex:1 1 0}.f-pane.activ{border-top:3px solid var(--accent)}
.f-split{flex:0 0 10px;cursor:col-resize;display:flex;align-items:center;justify-content:center;touch-action:none}.f-split:before{content:"";width:3px;height:36px;border-radius:2px;background:var(--bordura)}.f-split:hover:before,.f-split.trage:before{background:var(--accent)}
.f-ph{display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid var(--bordura);flex-wrap:wrap}.f-ph h2{margin:0;font-size:1rem;text-transform:none;display:flex;align-items:center;gap:6px}.f-ph h2 svg{width:18px;height:18px}.f-badge{font-size:.7rem;padding:1px 7px;border-radius:9px;background:var(--accent);color:#fff}.f-ph .f-sp{flex:1}.f-ph button{min-height:32px;padding:4px 10px;font-size:.8rem}
.f-pills{display:flex;gap:5px;flex-wrap:wrap}.f-pills button{min-height:28px;padding:2px 10px;border-radius:14px;font-size:.75rem}
.f-pathbar{display:flex;gap:6px;padding:6px 10px;border-bottom:1px solid var(--bordura);align-items:center}.f-pathbar input{flex:1;min-width:60px;font-family:monospace;font-size:.85rem;min-height:32px;padding:3px 8px}.f-pathbar button{min-height:32px;padding:3px 9px;font-size:.8rem}.f-pcpath{flex:1;font-size:.85rem;color:var(--text-slab);overflow-wrap:anywhere}
.f-note{padding:10px;border-bottom:1px solid var(--bordura);font-size:.82rem;line-height:1.4}.f-note p{margin:0 0 8px}.f-note .f-big{display:inline-block;padding:10px 16px;border-radius:8px;background:var(--accent);color:#fff;font-weight:600;text-decoration:none;margin:2px 0 6px}.f-note .f-row{display:flex;gap:6px;flex-wrap:wrap}.f-note .nota{margin:0;color:var(--text-slab)}.f-note .f-row+.nota{margin-top:8px}.f-note .f-https{color:var(--accent);font-weight:600}
.f-listwrap{flex:1;overflow:auto;position:relative}.f-listwrap.drop{outline:2px dashed var(--accent);outline-offset:-4px}
.f-t{width:100%;border-collapse:collapse;table-layout:fixed;margin:0;font-size:.85rem}.f-t th{position:sticky;top:0;background:var(--fundal);z-index:1;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;color:var(--text-slab);padding:5px 6px;text-align:left;cursor:pointer;user-select:none}.f-t th.c{width:30px;cursor:default}.f-t th.s{width:84px;text-align:right}.f-t th.d{width:118px;text-align:right}.f-t th.m{width:80px}
.f-t td{padding:3px 6px;border-top:1px solid var(--bordura);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:default}.f-t td.s,.f-t td.d{text-align:right;font-variant-numeric:tabular-nums;color:var(--text-slab);font-size:.8rem}.f-t td.m{font-family:monospace;font-size:.78rem;color:var(--text-slab)}
.f-t tr.sel td{background:color-mix(in srgb,var(--accent) 30%,transparent)}.f-t tr.cur td{box-shadow:inset 0 1px 0 var(--accent),inset 0 -1px 0 var(--accent)}.f-t tr.cur td:first-child{box-shadow:inset 3px 0 0 var(--accent),inset 0 1px 0 var(--accent),inset 0 -1px 0 var(--accent)}.f-t tr.tinta td{background:color-mix(in srgb,var(--accent) 45%,transparent)}
.f-t tr.lacat td{color:var(--text-slab)}.f-t input[type=checkbox]{width:17px;height:17px;min-height:0;margin:0;vertical-align:middle}.f-ico{display:inline-block;width:1.2em;text-align:center;margin-right:4px}.f-tag{font-size:.65rem;border:1px solid var(--bordura);border-radius:6px;padding:0 5px;margin-left:6px;color:var(--text-slab)}
.f-foot{display:flex;justify-content:space-between;gap:8px;padding:5px 10px;border-top:1px solid var(--bordura);font-size:.78rem;color:var(--text-slab)}
.f-keys{display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:6px;margin-top:8px}.f-keys button{min-height:46px;padding:3px 4px;display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.15;font-size:.88rem}.f-keys button:before{content:attr(data-tasta);font-size:.66rem;color:var(--text-slab);font-weight:600}.f-keys button.danger{color:var(--rosu);border-color:var(--rosu)}.f-keys button.limitat{opacity:.55}
.f-keysnote{font-size:.72rem;color:var(--text-slab);margin:4px 0 0}
.f-jobs{position:fixed;right:14px;bottom:14px;width:min(380px,calc(100vw - 28px));max-height:45vh;overflow:auto;z-index:10005;padding:10px 12px;margin:0;box-shadow:0 10px 32px #0008}.f-jobs h2{font-size:.9rem;margin:0 0 4px;text-transform:none;display:flex;justify-content:space-between}.f-job{border-top:1px solid var(--bordura);padding:7px 0}.f-job-top{display:flex;gap:8px;justify-content:space-between;align-items:center}.f-job-name{overflow-wrap:anywhere;font-size:.82rem;flex:1}.f-job button{min-height:28px;padding:2px 8px;font-size:.75rem}.f-job progress{display:block;width:100%;height:8px;margin:5px 0;accent-color:var(--accent)}.f-job-status{font-size:.75rem;color:var(--text-slab);overflow-wrap:anywhere;margin:0}.f-job.error .f-job-status{color:var(--rosu)}
.f-context{position:fixed;z-index:10020;background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:5px;box-shadow:0 10px 32px #0006;min-width:210px;max-height:80vh;overflow:auto}.f-context button{display:block;width:100%;text-align:left;border:0;background:transparent;min-height:36px;padding:6px 12px}.f-context button:hover,.f-context button:focus{background:var(--fundal)}.f-context .danger{color:var(--rosu)}
.f-overlay{position:fixed;inset:0;background:#0009;display:flex;align-items:center;justify-content:center;padding:20px;z-index:10010}.f-dialog{width:min(540px,100%);max-height:90vh;overflow:auto;margin:0}.f-dialog h2{font-size:1.05rem;text-transform:none}.f-dialog p{overflow-wrap:anywhere}.f-field{display:block;margin:12px 0}.f-field span{display:block;margin-bottom:6px}.f-field input{width:100%}.f-details{padding-left:20px;max-height:30vh;overflow:auto;overflow-wrap:anywhere;font-size:.85rem}
.f-editor{width:min(1100px,100%);height:min(860px,94vh);display:flex;flex-direction:column;gap:8px}.f-editor .f-eh{display:flex;justify-content:space-between;align-items:center;gap:8px}.f-editor h2{margin:0}.f-editor-path{font-family:monospace;overflow-wrap:anywhere;margin:0;font-size:.85rem}.f-editor textarea{width:100%;flex:1;min-height:140px;resize:none;white-space:pre;overflow:auto;font:14px/1.5 Consolas,monospace;tab-size:4}.f-editor .butoane,.f-editor .nota{margin:0}.f-editor-format{color:var(--text-slab);font-size:.78rem;margin:0}
@media(max-width:1000px){.f-keys{grid-template-columns:repeat(5,minmax(0,1fr))}.f-t th.d,.f-t td.d{display:none}}
@media(max-width:760px) and (orientation:portrait),(max-width:559px){.f-tabs{display:flex}.f-split{display:none}.f-panes{height:auto;min-height:0;display:block}.f-pane{height:62vh}#f-pane-0,#f-pane-1{flex:none}.f-panes[data-activ="0"] #f-pane-1,.f-panes[data-activ="1"] #f-pane-0{display:none}.f-keys{grid-template-columns:repeat(3,minmax(0,1fr))}.f-keys button{min-height:48px}.f-keysnote{display:none}.f-t th.m,.f-t td.m{display:none}.f-t th.s{width:70px}.f-t td{padding:7px 6px}.f-jobs{left:8px;right:8px;width:auto}}
/* telefonul culcat (Eduard 14.11.2026 18:53): cele doua panouri alaturate, ca pe PC, fara file; butoanele F pe un rand jos care deruleaza; texte de cel putin 12 px */
@media(orientation:landscape) and (max-height:500px) and (min-width:560px){main{padding-top:0}.f-head{margin:0 0 2px;gap:8px}.f-head h1{font-size:16px}.f-head p{display:none}#f-message{margin:0 0 2px;min-height:0;font-size:12px}
.f-panes{height:calc(100vh - 112px);height:calc(100dvh - 112px);min-height:150px}.f-split{flex-basis:18px}.f-split:before{width:4px;height:44px}
.f-ph{padding:3px 8px;gap:6px;flex-wrap:nowrap}.f-ph h2{font-size:14px;flex:0 0 auto}.f-ph .f-sp{display:none}.f-ph button{min-height:32px;font-size:13px}.f-badge,.f-tag{font-size:12px}.f-pills{flex:1 1 0;min-width:0;flex-wrap:nowrap;overflow-x:auto;scrollbar-width:thin}.f-pills button{flex:0 0 auto;white-space:nowrap;min-height:30px;font-size:12px}
.f-pathbar{padding:3px 8px}.f-pathbar input,.f-pcpath{font-size:13px}.f-note{padding:4px 8px;font-size:13px;max-height:40%;overflow:auto}.f-note p{margin:0 0 4px}.f-note .f-row button{min-height:34px;padding:3px 10px}.f-note .f-big{padding:6px 12px;margin:0 0 4px}
.f-t{font-size:14px}.f-t th{font-size:12px;padding:3px 6px}.f-t td{padding:6px 6px}.f-t td.s{font-size:12px}.f-t th.s{width:70px}.f-t th.m,.f-t td.m,.f-t th.d,.f-t td.d{display:none}.f-foot{font-size:12px;padding:2px 8px}
.f-keys{display:flex;gap:5px;margin-top:4px;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:thin}.f-keys button{flex:1 0 auto;min-width:86px;min-height:42px;padding:2px 8px;font-size:14px;white-space:nowrap}.f-keys button:before{font-size:12px}.f-keysnote{display:none}
.f-jobs{max-height:70vh}}
</style>
</head>
<body>
<main id="f-main">
<div class="f-head"><h1>__T_title__</h1><p>__T_intro__</p><label id="f-external-wrap" hidden><input type="checkbox" id="externPermis"> __T_external__</label><button type="button" id="f-logout" hidden>__T_logout__</button></div>
<p class="mesaj" id="f-message" role="status" aria-live="polite">__T_checking__</p>
<section class="card f-auth" id="f-auth" hidden>
  <h2>__T_authTitle__</h2><p class="nota">__T_authNote__</p>
  <form id="f-login"><label for="f-password">__T_password__</label><input id="f-password" type="text" name="password" autocomplete="off" autocapitalize="off" spellcheck="false" required maxlength="256"><button class="principal" type="submit" id="f-login-button">__T_login__</button></form>
</section>
<div id="f-content" hidden>
  <div class="f-tabs" role="tablist"><button type="button" id="f-tab-0" role="tab">__T_tabPc__</button><button type="button" id="f-tab-1" role="tab">__T_tabRx__</button></div>
  <div class="f-panes" id="f-panes" data-activ="1">
    <section class="f-pane" id="f-pane-0" aria-label="__T_pc__">
      <div class="f-ph"><h2><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>__T_pc__</h2><span class="f-badge" hidden>__T_active__</span><span class="f-sp"></span><button type="button" id="f-reopen" hidden></button><button type="button" id="f-choose" class="principal" hidden>__T_chooseDir__</button></div>
      <div class="f-note" id="f-pcnote" hidden></div>
      <div class="f-pathbar"><button type="button" id="f-up-0" aria-label="__T_up__">↑</button><span class="f-pcpath" id="f-path-0"></span><button type="button" id="f-refresh-0" aria-label="__T_refresh__">⟳</button></div>
      <div class="f-listwrap" id="f-wrap-0"><table class="f-t"><thead><tr><th class="c"><input type="checkbox" id="f-all-0" aria-label="__T_selectAll__"></th><th data-sort="name">__T_name__</th><th class="s" data-sort="size">__T_size__</th><th class="d" data-sort="mtime">__T_date__</th></tr></thead><tbody id="f-list-0"></tbody></table><p class="nota" id="f-empty-0" style="padding:10px" hidden></p></div>
      <div class="f-foot"><span id="f-count-0"></span></div>
      <input type="file" id="f-files" multiple hidden><input type="file" id="f-folder" multiple webkitdirectory hidden>
    </section>
    <div class="f-split" id="f-split" role="separator" aria-orientation="vertical" tabindex="0"></div>
    <section class="f-pane" id="f-pane-1" aria-label="__T_rx__">
      <div class="f-ph"><h2><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="8" width="20" height="9" rx="2"/><path d="M6 12.5h.01M10 12.5h4M8 4l4 4 4-4"/></svg>__T_rx__</h2><span class="f-badge" hidden>__T_active__</span><span class="f-sp"></span><div class="f-pills" id="f-shortcuts" aria-label="__T_shortcuts__"></div></div>
      <form class="f-pathbar" id="f-pathform"><button type="button" id="f-up-1" aria-label="__T_up__">↑</button><input id="f-path-1" value="/" autocomplete="off" spellcheck="false" aria-label="__T_path__"><button type="button" id="f-refresh-1" aria-label="__T_refresh__">⟳</button></form>
      <div class="f-listwrap" id="f-wrap-1"><table class="f-t"><thead><tr><th class="c"><input type="checkbox" id="f-all-1" aria-label="__T_selectAll__"></th><th data-sort="name">__T_name__</th><th class="s" data-sort="size">__T_size__</th><th class="m">__T_mode__</th><th class="d" data-sort="mtime">__T_date__</th></tr></thead><tbody id="f-list-1"></tbody></table><p class="nota" id="f-empty-1" style="padding:10px" hidden></p></div>
      <div class="f-foot"><span id="f-count-1"></span></div>
    </section>
  </div>
  <div class="f-keys" id="f-keys">
    <button type="button" data-k="view" data-tasta="F3">__T_keyView__</button>
    <button type="button" data-k="edit" data-tasta="F4">__T_keyEdit__</button>
    <button type="button" data-k="copyRight" data-tasta="F5" class="principal">__T_copyRight__</button>
    <button type="button" data-k="copyLeft" data-tasta="F5">__T_copyLeft__</button>
    <button type="button" data-k="move" data-tasta="F6">__T_move__</button>
    <button type="button" data-k="mkdir" data-tasta="F7">__T_newDir__</button>
    <button type="button" data-k="newfile" data-tasta="Shift+F4">__T_newFile__</button>
    <button type="button" data-k="rename" data-tasta="F2">__T_rename__</button>
    <button type="button" data-k="delete" data-tasta="F8" class="danger">__T_delete__</button>
  </div>
  <p class="f-keysnote">__T_keysNote__</p>
</div>
</main>
<section class="card f-jobs" id="f-jobs" hidden><h2>__T_jobTitle__ <button type="button" id="f-jobs-close" aria-label="__T_close__">×</button></h2><div id="f-job-list"></div></section>
<div id="f-context" class="f-context" role="menu" hidden></div>
<div id="f-prompt-overlay" class="f-overlay" hidden><section class="card f-dialog" role="dialog" aria-modal="true" aria-labelledby="f-prompt-title" tabindex="-1"><h2 id="f-prompt-title"></h2><form id="f-prompt-form"><div id="f-prompt-body"></div><p class="mesaj eroare" id="f-prompt-error" role="alert"></p><div class="butoane"><button class="principal" id="f-prompt-ok" type="submit">__T_continue__</button><button type="button" id="f-prompt-cancel">__T_cancel__</button></div></form></section></div>
<div id="f-editor-overlay" class="f-overlay" hidden><section class="card f-dialog f-editor" role="dialog" aria-modal="true" aria-labelledby="f-editor-title" tabindex="-1"><div class="f-eh"><h2 id="f-editor-title">__T_editorTitle__</h2><button type="button" id="f-editor-close">__T_close__</button></div><p class="f-editor-path" id="f-editor-path"></p><p class="f-editor-format" id="f-editor-format"></p><textarea id="f-editor-text" aria-label="__T_editorTitle__" spellcheck="false" autocapitalize="off" autocomplete="off"></textarea><p class="mesaj" id="f-editor-message" role="status" aria-live="polite"></p><div class="butoane"><button type="button" class="principal" id="f-editor-save">__T_save__</button><button type="button" id="f-editor-reload">__T_editorReload__</button></div><p class="nota">__T_editorNote__</p></section></div>
<script>
(function(){
"use strict";
var T=__TEXTE__,CFG=__CONFIG__,H=__HTTPS__;
var FSA=typeof window.showDirectoryPicker==="function"&&window.isSecureContext;
var UA=navigator.userAgent,MOBIL=/Android|iPhone|iPad|Mobile/.test(UA),CHROMIUM=/Chrome\/|Edg\//.test(UA)&&!MOBIL;
/* pe https: semnul saltului iese din adresa; linkurile spre celelalte pagini (cu fluxul de pe 8001) duc inapoi pe http, la acelasi nume */
if(location.protocol==="https:"){try{if(new URLSearchParams(location.search).has("s")){history.replaceState(null,"",location.pathname);}}catch(e){}
  document.addEventListener("click",function(e){var a=e.target&&e.target.closest?e.target.closest("a[href]"):null;if(!a||a.hasAttribute("download")){return;}var u;try{u=new URL(a.getAttribute("href"),location.href);}catch(x){return;}
    if(u.protocol!=="https:"||u.host!==location.host||/^\/(fisiere\/?$|api\/fisiere-)/.test(u.pathname)){return;}u.protocol="http:";u.port=H.port_http&&H.port_http!==80?String(H.port_http):"";a.href=u.href;},true);}
var S={auth:false,active:1,jobs:new Map(),prompt:null,editor:null,shortcuts:[],pcMode:FSA?"fsa":"simplu",vroot:null,drag:null};
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var n=document.createElement(tag);if(cls){n.className=cls;}if(text!==undefined){n.textContent=text;}return n;}
function fmt(t){var v=Array.prototype.slice.call(arguments,1),i=0;return String(t).replace(/%s/g,function(){return String(v[i++]);});}
function message(t,err){$("f-message").textContent=t||"";$("f-message").classList.toggle("eroare",!!err);}
function fail(e){if(e&&(e.auth||e.name==="AbortError")){return;}message(e&&e.message||T.network,true);}
function joined(base,name){return (base==="/"?"/":base.replace(/\/$/,"")+"/")+name;}
function bytes(n){n=Number(n)||0;if(n<1024){return n+" "+T.bytes;}var u=["KiB","MiB","GiB","TiB"],i=-1;do{n/=1024;i++;}while(n>=1024&&i<u.length-1);return n.toLocaleString(undefined,{maximumFractionDigits:1})+" "+u[i];}
function date(n){if(!n){return "";}var d=new Date(Number(n)*1000);return isNaN(d.getTime())?"":d.toLocaleString(undefined,{year:"2-digit",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"});}
function validName(v){return v&&v!=="."&&v!==".."&&v.indexOf("/")===-1&&v.indexOf("\\")===-1;}
function isDir(x){return x.type==="directory"||!!x.is_directory;}
function names(list){return list.length===1?list[0].name:fmt(T.items,list.length);}
/* ---------- receptorul: API ---------- */
async function api(route,data,options){
  options=options||{};var o={method:data===undefined?"GET":"POST",credentials:"same-origin",cache:"no-store",headers:{"X-HDS-CSRF":CFG.csrf||""}};
  if(data!==undefined){o.headers["Content-Type"]="application/json";o.body=JSON.stringify(data);}if(options.raw){o.headers["Content-Type"]="application/octet-stream";o.body=options.raw;o.method="POST";}if(options.signal){o.signal=options.signal;}
  var r;try{r=await fetch("/api/fisiere-"+route,o);}catch(e){if(e.name==="AbortError"){throw e;}throw new Error(T.network);}
  var d;try{d=await r.json();}catch(e){throw new Error(fmt(T.badResponse,r.status));}
  if(r.status===401){setAuth(false,route!=="login");var a=new Error(d.message||T.authExpired);a.auth=true;if(route==="login"){message(a.message,true);}throw a;}
  if(!r.ok||d.result===false){var er=new Error(d.message||T.failed);er.response=d;er.code=d.code;throw er;}return d;
}
async function confirmed(route,payload){var d=await api(route,payload);while(d.confirmare){var c=d.confirmare,ok=await promptForm(c.intrebare||T.confirm,[],c.avertisment||"",c.buton||T.confirmAction,c.detalii||[]);if(!ok){return null;}payload=Object.assign({},payload,{cod:c.cod});d=await api(route,payload);}return d;}
async function rxList(path){var all=[],d,off=0;do{d=await api("list?cale="+encodeURIComponent(path)+"&offset="+off);all=all.concat(d.entries||[]);off=all.length;}while(d.has_more&&all.length<3000);return {path:d.path,parent:d.parent,entries:all};}
async function rxJob(payload,label,quiet){
  var d=await confirmed("operate",payload);if(!d){return null;}if(!d.job){return d;}var id=d.job.id||d.job,j=quiet?{row:el("div"),stop:el("button"),bar:el("progress"),status:el("p")}:makeJob("job-"+id,label,function(){return api("cancel",{id:id});});
  while(true){await new Promise(function(r){setTimeout(r,500);});var v=(await api("job?id="+encodeURIComponent(id))).job;jobProgress(j,v.bytes||0,v.total||0,T.running+(v.bytes?" · "+bytes(v.bytes):""));
    if(v.state==="running"||v.state==="queued"){continue;}if(quiet&&v.state==="error"&&v.code==="exists"){v.output={};return v;}var out=v.output||{},errs=out.errors||[],text=v.state==="error"?(v.error||T.failed):v.state==="cancelled"?T.cancelled:T.done;
    if(out.results){text+=" "+fmt(T.resultCount,out.results.length);}if(out.skipped){text+=" "+fmt(T.skipped,out.skipped);}if(errs.length){text+=" "+fmt(T.errorCount,errs.length)+" "+errs.map(function(e){return e.path+": "+e.message;}).join(" · ");}
    finishJob(j,text,v.state==="error"||errs.length>0);v.output=out;return v;}
}
async function rxUpload(file,path,job,state){
  var start=await confirmed("upload-start",{cale:path,size:file.size});if(!start){return false;}var id=start.id,off=start.offset||0;
  try{while(off<file.size){if(state.stop){throw {name:"AbortError"};}var end=Math.min(off+65536,file.size),r=await api("upload-chunk?id="+encodeURIComponent(id)+"&offset="+off,undefined,{raw:file.slice(off,end)});off=r.offset===undefined?end:r.offset;jobProgress(job,state.bytes+off,state.total,fmt(T.copyFile,state.n,state.count)+" · "+bytes(state.bytes+off));}
    var ok=await confirmed("upload-commit",{id:id});if(!ok){await api("upload-abort",{id:id});return false;}state.bytes+=file.size;return true;
  }catch(e){try{await api("upload-abort",{id:id});}catch(ignore){}throw e;}
}
/* ---------- calculatorul ---------- */
var IDB={db:function(){return new Promise(function(res,rej){var q=indexedDB.open("hds-fisiere",1);q.onupgradeneeded=function(){q.result.createObjectStore("d");};q.onsuccess=function(){res(q.result);};q.onerror=function(){rej(q.error);};});},
  put:async function(k,v){var db=await IDB.db();return new Promise(function(res){var t=db.transaction("d","readwrite");t.objectStore("d").put(v,k);t.oncomplete=res;t.onerror=res;});},
  get:async function(k){var db=await IDB.db();return new Promise(function(res){var q=db.transaction("d").objectStore("d").get(k);q.onsuccess=function(){res(q.result);};q.onerror=function(){res(null);};});}};
function vnode(){return {dirs:{},files:{}};}
function vadd(files){if(!S.vroot){S.vroot=vnode();}Array.prototype.forEach.call(files,function(f){var parts=(f.webkitRelativePath||f.name).split("/").filter(Boolean),n=S.vroot;for(var i=0;i<parts.length-1;i++){n=n.dirs[parts[i]]||(n.dirs[parts[i]]=vnode());}n.files[parts[parts.length-1]]=f;});}
async function pcList(p){
  var out=[];if(S.pcMode==="fsa"){if(!p.stack.length){return out;}var dir=p.stack[p.stack.length-1].h;
    for await (var pair of dir.entries()){var name=pair[0],h=pair[1];if(h.kind==="directory"){out.push({key:name,name:name,type:"directory",size:0,mtime:0,h:h});}else{var f=null;try{f=await h.getFile();}catch(e){}out.push({key:name,name:name,type:"file",size:f?f.size:0,mtime:f?f.lastModified/1000:0,h:h});}if(out.length>=3000){break;}}
  }else{var n=S.vroot;if(!n){return out;}p.stack.forEach(function(s){n=n&&n.dirs[s.name];});if(!n){p.stack=[];n=S.vroot;}
    Object.keys(n.dirs).forEach(function(k){out.push({key:k,name:k,type:"directory",size:0,mtime:0,node:n.dirs[k]});});Object.keys(n.files).forEach(function(k){var f=n.files[k];out.push({key:k,name:k,type:"file",size:f.size,mtime:f.lastModified/1000,file:f});});}
  return out;
}
function pcDir(p){return p.stack.length?p.stack[p.stack.length-1].h:null;}
function pcLabel(p){return p.stack.map(function(s){return s.name;}).join(" / ");}
async function useDir(h){var P0=P[0];if(h.requestPermission&&(await h.queryPermission({mode:"readwrite"}))!=="granted"&&(await h.requestPermission({mode:"readwrite"}))!=="granted"){message(T.permission,true);return;}S.pcMode="fsa";P0.stack=[{name:h.name,h:h}];$("f-reopen").hidden=true;try{await IDB.put("dosar",h);}catch(e){}renderNote();await load(P0);setActive(0);}
async function pcExists(dir,name){try{await dir.getFileHandle(name);return "file";}catch(e){}try{await dir.getDirectoryHandle(name);return "directory";}catch(e){}return null;}
async function pcWriteFile(dir,name,blobOrStream,state,job){var fh=await dir.getFileHandle(name,{create:true}),w=await fh.createWritable();try{if(blobOrStream instanceof Blob){await w.write(blobOrStream);state.bytes+=blobOrStream.size;}else{var rd=blobOrStream.getReader();while(true){if(state.stop){throw {name:"AbortError"};}var c=await rd.read();if(c.done){break;}await w.write(c.value);state.bytes+=c.value.length;if(job){jobProgress(job,state.bytes,state.total,fmt(T.copyFile,state.n,state.count)+" · "+bytes(state.bytes));}}}await w.close();}catch(e){try{await w.abort();}catch(ignore){}throw e;}}
async function pcCopyEntry(srcDir,x,dstDir,state,job){if(state.stop){throw {name:"AbortError"};}
  if(isDir(x)){var nd=await dstDir.getDirectoryHandle(x.name,{create:true});for await (var pair of x.h.entries()){var h=pair[1];await pcCopyEntry(x.h,{name:pair[0],type:h.kind==="directory"?"directory":"file",h:h},nd,state,job);}return;}
  state.n++;await pcWriteFile(dstDir,x.name,await x.h.getFile(),state,job);}
/* ---------- panourile ---------- */
var P=[{i:0,stack:[],entries:[],sel:new Set(),cur:0,sort:"name",asc:true},{i:1,path:"/",parent:null,entries:[],sel:new Set(),cur:0,sort:"name",asc:true}];
function other(p){return P[1-p.i];}
function sorted(p){return p.entries.slice().sort(function(a,b){if(isDir(a)!==isDir(b)){return isDir(a)?-1:1;}var v=p.sort==="name"?a.name.localeCompare(b.name):Number(a[p.sort]||0)-Number(b[p.sort]||0);return p.asc?v:-v;});}
function chosen(p){var list=p.view||[];var s=list.filter(function(x){return p.sel.has(x.key);});if(!s.length&&list[p.cur]){s=[list[p.cur]];}return s;}
function setActive(i){S.active=i;$("f-panes").dataset.activ=String(i);[0,1].forEach(function(k){$("f-pane-"+k).classList.toggle("activ",k===i);$("f-pane-"+k).querySelector(".f-badge").hidden=k!==i;$("f-tab-"+k).classList.toggle("on",k===i);$("f-tab-"+k).setAttribute("aria-selected",String(k===i));});P.forEach(function(p){if(p.view){mark(p);}});}
async function load(p,path){
  message(T.loading);try{if(p.i===1){var d=await rxList(path||p.path);if(d.path!==p.path){p.sel.clear();p.cur=0;}p.path=d.path;p.parent=d.parent;p.entries=d.entries.map(function(x){x.key=x.path;return x;});}else{p.entries=await pcList(p);}
    var keys=new Set(p.entries.map(function(x){return x.key;}));p.sel.forEach(function(k){if(!keys.has(k)){p.sel.delete(k);}});render(p);message("");}catch(e){if(e.name==="NotFoundError"||e.name==="NotAllowedError"){p.stack=[];p.entries=[];render(p);message(T.permission,true);return;}fail(e);}
}
function icon(x){return x.locked?"🔒":isDir(x)?"📁":x.type==="symlink"?"↗":"📄";}
function render(p){
  var body=$("f-list-"+p.i),list=sorted(p);p.view=list;body.textContent="";if(p.cur>=list.length){p.cur=Math.max(0,list.length-1);}
  list.forEach(function(x,idx){var tr=el("tr");tr.dataset.k=x.key;tr.draggable=!x.locked;if(x.locked){tr.classList.add("lacat");tr.title=T.locked;}
    var td=el("td"),cb=el("input");cb.type="checkbox";cb.setAttribute("aria-label",fmt(T.select,x.name));cb.checked=p.sel.has(x.key);cb.addEventListener("click",function(e){e.stopPropagation();});cb.addEventListener("change",function(){toggle(p,x.key,cb.checked);});td.appendChild(cb);tr.appendChild(td);
    td=el("td","n");td.appendChild(el("span","f-ico",icon(x)));td.appendChild(document.createTextNode(x.name));if(x.locked){td.appendChild(el("span","f-tag",T.lockedShort));}if(x.link_target!==undefined){td.title=fmt(T.link,x.link_target);}tr.appendChild(td);
    tr.appendChild(el("td","s",isDir(x)?T.folder:bytes(x.size)));if(p.i===1){tr.appendChild(el("td","m",x.mode||""));}tr.appendChild(el("td","d",date(x.mtime)));
    tr.addEventListener("click",function(e){setActive(p.i);if(e.ctrlKey||e.metaKey){toggle(p,x.key);}else if(e.shiftKey){var a=Math.min(p.cur,idx),b=Math.max(p.cur,idx);for(var k=a;k<=b;k++){p.sel.add(list[k].key);}}else{p.sel.clear();}p.cur=idx;mark(p);});
    tr.addEventListener("dblclick",function(){openEntry(p,x).catch(fail);});
    tr.addEventListener("contextmenu",function(e){e.preventDefault();setActive(p.i);p.cur=idx;mark(p);showContext(p,e.clientX,e.clientY);});
    tr.addEventListener("dragstart",function(e){if(!p.sel.has(x.key)){p.sel.clear();p.sel.add(x.key);mark(p);}S.drag={from:p.i,items:chosen(p)};e.dataTransfer.effectAllowed="copyMove";e.dataTransfer.setData("text/plain",S.drag.items.map(function(v){return v.name;}).join("\n"));});
    tr.addEventListener("dragend",function(){S.drag=null;clearTargets();});
    if(isDir(x)){tr.addEventListener("dragover",function(e){if(dropAllowed(e,p)){e.preventDefault();e.stopPropagation();clearTargets();tr.classList.add("tinta");e.dataTransfer.dropEffect=e.shiftKey?"move":"copy";}});tr.addEventListener("drop",function(e){e.preventDefault();e.stopPropagation();clearTargets();onDrop(e,p,x);});}
    body.appendChild(tr);});
  $("f-empty-"+p.i).hidden=!!list.length||(p.i===0&&!p.stack.length&&!$("f-pcnote").hidden);$("f-empty-"+p.i).textContent=p.i===0&&!p.stack.length?(S.pcMode==="fsa"?T.pcEmpty:T.pcSimpleEmpty):T.empty;
  if(p.i===1){$("f-path-1").value=p.path;$("f-up-1").disabled=!p.parent;}else{$("f-path-0").textContent=pcLabel(p);$("f-up-0").disabled=p.stack.length<2;}
  mark(p);
}
function toggle(p,k,on){if(on===undefined){on=!p.sel.has(k);}if(on){p.sel.add(k);}else{p.sel.delete(k);}mark(p);}
function mark(p){var list=p.view||[],total=0;Array.prototype.forEach.call($("f-list-"+p.i).children,function(tr,idx){var s=p.sel.has(tr.dataset.k);tr.classList.toggle("sel",s);tr.classList.toggle("cur",idx===p.cur&&S.active===p.i);tr.querySelector("input").checked=s;});list.forEach(function(x){if(p.sel.has(x.key)){total+=Number(x.size)||0;}});
  $("f-count-"+p.i).textContent=fmt(T.selection,p.sel.size,list.length,bytes(total));var all=$("f-all-"+p.i);all.checked=!!list.length&&p.sel.size===list.length;all.indeterminate=p.sel.size>0&&p.sel.size<list.length;var row=$("f-list-"+p.i).children[p.cur];if(row&&S.active===p.i&&row.scrollIntoView){row.scrollIntoView({block:"nearest"});}}
async function openEntry(p,x){
  if(x.locked){message(T.locked,true);return;}
  if(p.i===1){if(isDir(x)){await load(p,x.type==="symlink"?(x.resolved_path||x.path):x.path);}else{await openEditor(p,x,false);}return;}
  if(isDir(x)){p.stack.push(S.pcMode==="fsa"?{name:x.name,h:x.h}:{name:x.name});p.sel.clear();p.cur=0;await load(p);}else{await openEditor(p,x,false);}
}
async function up(p){if(p.i===1){if(p.parent){await load(p,p.parent);}}else if(p.stack.length>1){p.stack.pop();p.sel.clear();p.cur=0;await load(p);}}
/* ---------- operatiile ---------- */
function limited(t){message(t||T.limited,true);}
function destLabel(q){return q.i===1?q.path:(pcLabel(q)||T.pc);}
async function transfer(from,to,items,move,target){
  /* target: optional directory entry in the destination panel (tragerea pe un dosar) */
  if(!items.length){message(T.chooseAny,true);return;}
  if(items.some(function(x){return x.locked;})){message(T.locked,true);return;}
  var dstRx=to.i===1?(target?(target.resolved_path||target.path):to.path):null,dstPc=to.i===0?(target?target.h:pcDir(to)):null;
  if(to.i===0&&S.pcMode!=="fsa"&&!(from.i===1&&!move)){limited();return;}
  if(to.i===0&&S.pcMode==="fsa"&&!dstPc){message(T.pcEmpty,true);return;}
  if(from.i===1&&to.i===0&&S.pcMode!=="fsa"&&items.some(isDir)){limited(T.limitedFolders);return;}
  if(move&&from.i===0&&S.pcMode!=="fsa"){limited();return;}
  var where=target?target.name:destLabel(to),detail=items.map(function(x){return x.name;});
  var ask=await promptForm(fmt(move?T.moveAsk:T.copyAsk,names(items),where),from.i===1&&to.i===1?[{name:"destination",label:T.destination,value:dstRx}]:[],fmt(T.from,destLabel(from)),move?T.move:T.continue,detail);if(!ask){return;}
  if(from.i===1&&to.i===1){await rxJob({action:move?"move":"copy",items:items.map(function(x){return x.path;}),destination:ask.destination||dstRx},(move?T.move:T.copyRight)+": "+names(items));await refreshAll();return;}
  if(from.i===0&&to.i===0){await pcToPc(items,dstPc,move);return;}
  if(from.i===0){await pcToRx(items,dstRx,move);}else{await rxToPc(items,dstPc,move);}
}
async function pcFiles(items){var list=[];async function walk(x,rel){if(isDir(x)){list.push({dir:rel.concat([x.name])});if(S.pcMode==="fsa"){for await (var pair of x.h.entries()){var h=pair[1];await walk({name:pair[0],type:h.kind==="directory"?"directory":"file",h:h},rel.concat([x.name]));}}else{var n=x.node;for(var k in n.dirs){await walk({name:k,type:"directory",node:n.dirs[k]},rel.concat([x.name]));}for(var f in n.files){list.push({rel:rel.concat([x.name]),name:f,file:n.files[f]});}}}else{list.push({rel:rel,name:x.name,file:x.file||null,h:x.h||null});}}
  for(var i=0;i<items.length;i++){await walk(items[i],[]);}return list;}
async function pcToRx(items,dst,move){
  var list=await pcFiles(items),files=list.filter(function(v){return !v.dir;}),state={stop:false,bytes:0,total:0,n:0,count:files.length,done:0};
  for(var i=0;i<files.length;i++){if(!files[i].file){files[i].file=await files[i].h.getFile();}state.total+=files[i].file.size;}
  var job=makeJob("pc-"+Date.now(),fmt(T.copyingTo,T.rx,names(items)),function(){state.stop=true;}),errors=[];
  try{for(var d=0;d<list.length;d++){if(list[d].dir){var path=dst,parts=list[d].dir;for(var k=0;k<parts.length-1;k++){path=joined(path,parts[k]);}var r=await rxJob({action:"mkdir",items:[],destination:path,name:parts[parts.length-1]},T.newDir+": "+parts.join("/"),true);var e=r&&r.output&&r.output.errors||[];if(r&&r.state==="error"&&r.code!=="exists"){errors.push(r.error||T.failed);}if(e.length&&e[0].code!=="exists"){errors.push(e[0].message);}}}
    for(var f=0;f<files.length;f++){var it=files[f],p=dst;it.rel.forEach(function(s){p=joined(p,s);});state.n=f+1;try{if(await rxUpload(it.file,joined(p,it.name),job,state)&&move&&S.pcMode==="fsa"){await removeFrom(it,items);}}catch(e){if(e.name==="AbortError"||e.auth){throw e;}errors.push(it.name+": "+(e.message||T.failed));}}
    if(move&&S.pcMode==="fsa"&&!errors.length){await pcRemoveTop(items.filter(isDir));}
    finishJob(job,errors.length?fmt(T.errorCount,errors.length)+" "+errors.join(" · "):T.done+" "+fmt(T.resultCount,files.length),errors.length>0);
  }catch(e){finishJob(job,e.name==="AbortError"?T.cancelled:(e.message||T.failed),e.name!=="AbortError");}
  await refreshAll();
}
async function removeFrom(it,items){/* fisierul de sus mutat: sters indata; cele din dosare se sterg la sfarsit cu dosarul */if(!it.rel.length){await pcDir(P[0]).removeEntry(it.name);}}
async function pcRemoveTop(dirs){var parent=pcDir(P[0]);for(var i=0;i<dirs.length;i++){await parent.removeEntry(dirs[i].name,{recursive:true});}}
async function rxToPc(items,dst,move){
  if(S.pcMode!=="fsa"){items.forEach(function(x){var a=el("a");a.href="/api/fisiere-download?cale="+encodeURIComponent(x.resolved_path||x.path);a.download=x.name;document.body.appendChild(a);a.click();a.remove();});return;}
  var state={stop:false,bytes:0,total:0,n:0,count:0},plan=[],errors=[];
  async function walk(x,dir){if(isDir(x)){var nd=await dir.getDirectoryHandle(x.name,{create:true}),d=await rxList(x.resolved_path||x.path);for(var i=0;i<d.entries.length;i++){if(!d.entries[i].locked){await walk(d.entries[i],nd);}}}else{plan.push({x:x,dir:dir});state.total+=Number(x.size)||0;}}
  for(var i=0;i<items.length;i++){if(isDir(items[i])&&await pcExists(dst,items[i].name)==="file"){errors.push(items[i].name+": "+T.exists);continue;}await walk(items[i],dst);}
  state.count=plan.length;var job=makeJob("rx-"+Date.now(),fmt(T.copyingTo,T.pc,names(items)),function(){state.stop=true;});
  try{for(var k=0;k<plan.length;k++){var it=plan[k];state.n=k+1;if(await pcExists(it.dir,it.x.name)){if(!(await promptForm(fmt(T.overwriteAsk,it.x.name),[],"",T.confirmAction))){continue;}}
      var r=await fetch("/api/fisiere-download?cale="+encodeURIComponent(it.x.resolved_path||it.x.path),{credentials:"same-origin",cache:"no-store"});if(!r.ok){var m=T.failed;try{m=(await r.json()).message||m;}catch(ignore){}errors.push(it.x.name+": "+m);continue;}
      await pcWriteFile(it.dir,it.x.name,r.body,state,job);}
    if(move&&!errors.length){await rxDeleteMoved(items);}
    finishJob(job,errors.length?fmt(T.errorCount,errors.length)+" "+errors.join(" · "):T.done+" "+fmt(T.resultCount,plan.length),errors.length>0);
  }catch(e){finishJob(job,e.name==="AbortError"?T.cancelled:(e.message||T.failed),e.name!=="AbortError");}
  await refreshAll();
}
async function rxDeleteMoved(items){/* mutarea a fost deja confirmata: a doua intrebare numai cand serverul are un avertisment (fisiere ale sistemului) */
  var paths=items.map(function(x){return x.path;}),d=await api("operate",{action:"delete",items:paths});if(d.confirmare){var c=d.confirmare;if((c.detalii||[])[0]||c.avertisment){await rxJob({action:"delete",items:paths},T.delete+": "+names(items));return;}d=await api("operate",{action:"delete",items:paths,cod:c.cod});}
  if(d.job){var id=d.job.id||d.job;for(var i=0;i<120;i++){await new Promise(function(r){setTimeout(r,500);});var v=(await api("job?id="+encodeURIComponent(id))).job;if(v.state!=="running"&&v.state!=="queued"){break;}}}}
async function pcToPc(items,dst,move){var src=pcDir(P[0]),state={stop:false,bytes:0,total:0,n:0,count:items.length},job=makeJob("pp-"+Date.now(),(move?T.move:T.copyRight)+": "+names(items),function(){state.stop=true;});
  try{for(var i=0;i<items.length;i++){var x=items[i];if(await pcExists(dst,x.name)){throw new Error(x.name+": "+T.exists);}if(move&&x.h.move){try{await x.h.move(dst);continue;}catch(e){}}await pcCopyEntry(src,x,dst,state,job);if(move){await src.removeEntry(x.name,{recursive:true});}}finishJob(job,T.done,false);}catch(e){finishJob(job,e.name==="AbortError"?T.cancelled:(e.message||T.failed),e.name!=="AbortError");}await refreshAll();}
async function del(p){var items=chosen(p);if(!items.length){message(T.chooseAny,true);return;}
  if(p.i===1){await rxJob({action:"delete",items:items.map(function(x){return x.path;})},T.delete+": "+names(items));await load(p);return;}
  if(S.pcMode!=="fsa"){limited();return;}if(!(await promptForm(fmt(T.deleteAsk,names(items)),[],"",T.delete,items.map(function(x){return x.name;})))){return;}
  var dir=pcDir(p);try{for(var i=0;i<items.length;i++){await dir.removeEntry(items[i].name,{recursive:true});}}catch(e){fail(e);}await load(p);}
async function rename(p){var items=chosen(p);if(items.length!==1){message(T.chooseOne,true);return;}var x=items[0];if(x.locked){message(T.locked,true);return;}if(p.i===0&&S.pcMode!=="fsa"){limited();return;}
  var r=await promptForm(T.rename,[{name:"name",label:T.newName,value:x.name,max:255}],x.name);if(!r||r.name===x.name){return;}
  if(p.i===1){await rxJob({action:"rename",items:[x.path],name:r.name},T.rename+": "+x.name);await load(p);return;}
  var dir=pcDir(p);if(await pcExists(dir,r.name)){message(T.exists,true);return;}try{var moved=false;if(x.h.move){try{await x.h.move(r.name);moved=true;}catch(e){}}if(!moved){var st={stop:false,bytes:0,total:0,n:0,count:0};await pcCopyEntry(dir,{name:r.name,type:x.type,h:x.h},dir,st,null);await dir.removeEntry(x.name,{recursive:true});}}catch(e){fail(e);}await load(p);}
async function create(p,kind){if(p.i===0&&S.pcMode!=="fsa"){limited();return;}if(p.i===0&&!pcDir(p)){message(T.pcEmpty,true);return;}
  var r=await promptForm(kind==="mkdir"?T.newDir:T.newFile,[{name:"name",label:T.name,value:"",max:255}],p.i===1?p.path:pcLabel(p));if(!r){return;}
  if(p.i===1){await rxJob({action:kind,items:[],destination:p.path,name:r.name},r.name);await load(p);}else{var dir=pcDir(p);if(await pcExists(dir,r.name)){message(T.exists,true);return;}try{if(kind==="mkdir"){await dir.getDirectoryHandle(r.name,{create:true});}else{await dir.getFileHandle(r.name,{create:true});}}catch(e){fail(e);}await load(p);}
  var v=p.view||[];for(var i=0;i<v.length;i++){if(v[i].name===r.name){p.cur=i;mark(p);if(kind==="newfile"){await openEditor(p,v[i],false);}break;}}}
async function refreshAll(){await Promise.all([load(P[0]),load(P[1])]);}
async function action(k){var p=P[S.active];hideContext();
  if(k==="copyRight"){await transfer(P[0],P[1],chosen(P[0]),false);}else if(k==="copyLeft"){await transfer(P[1],P[0],chosen(P[1]),false);}
  else if(k==="copy"){await transfer(p,other(p),chosen(p),false);}else if(k==="move"){await transfer(p,other(p),chosen(p),true);}
  else if(k==="delete"){await del(p);}else if(k==="rename"){await rename(p);}else if(k==="mkdir"||k==="newfile"){await create(p,k);}
  else if(k==="view"||k==="edit"){var it=(p.view||[])[p.cur]?[(p.view||[])[p.cur]]:[];if(it.length!==1){message(T.chooseAny,true);return;}if(isDir(it[0])){await openEntry(p,it[0]);return;}await openEditor(p,it[0],k==="view");}
  else if(k==="download"){await rxToPcSimple(chosen(p));}else if(k==="chmod"){await chmod(p);}else if(k==="shortcut"){await addShortcut(p);}
}
async function rxToPcSimple(items){items=items.filter(function(x){return !isDir(x)&&!x.locked;});if(!items.length){message(T.needFile,true);return;}var mode=S.pcMode;S.pcMode="simplu";try{await rxToPc(items,null,false);}finally{S.pcMode=mode;}}
async function chmod(p){var it=chosen(p);if(!it.length){message(T.chooseAny,true);return;}var r=await promptForm(T.mode,[{name:"mode",label:T.mode,value:it[0].mode||"0644",max:4}],T.chmodHelp,null,it.map(function(x){return x.path;}));if(r){await rxJob({action:"chmod",items:it.map(function(x){return x.path;}),mode:r.mode},T.mode);await load(p);}}
async function addShortcut(p){var it=chosen(p);for(var i=0;i<it.length;i++){var r=await promptForm(T.addShortcut,[{name:"name",label:T.shortcutName,value:it[i].name,max:100}],it[i].path);if(!r){break;}await api("shortcuts",{action:"add",name:r.name,path:it[i].path});}await loadShortcuts();message(T.shortcutAdded);}
/* ---------- tragerea ---------- */
function clearTargets(){Array.prototype.forEach.call(document.querySelectorAll(".tinta,.drop"),function(n){n.classList.remove("tinta");n.classList.remove("drop");});}
function externalFiles(e){return !S.drag&&e.dataTransfer&&Array.prototype.indexOf.call(e.dataTransfer.types,"Files")!==-1;}
function dropAllowed(e,p){return !!S.drag||externalFiles(e);}
async function onDrop(e,p,target){var move=e.shiftKey;
  if(S.drag){var d=S.drag;S.drag=null;var from=P[d.from];if(target&&d.items.some(function(x){return x.key===target.key;})){return;}if(from.i===p.i&&!target){message(T.samePanel,true);return;}await transfer(from,p,d.items,move,target);return;}
  if(!externalFiles(e)){return;}var items=Array.prototype.slice.call(e.dataTransfer.items||[]),handles=[];
  if(items.length&&items[0].getAsFileSystemHandle&&window.isSecureContext){var hs=await Promise.all(items.map(function(i){return i.kind==="file"?i.getAsFileSystemHandle():null;}));hs.forEach(function(h){if(h){handles.push({name:h.name,type:h.kind==="directory"?"directory":"file",h:h});}});}
  if(p.i===0){if(S.pcMode==="fsa"&&pcDir(p)){var st={stop:false,bytes:0,total:0,n:0,count:0};for(var i=0;i<handles.length;i++){await pcCopyEntry(null,handles[i],target?target.h:pcDir(p),st,null);}await load(p);}else{S.pcMode="simplu";vadd(e.dataTransfer.files);renderNote();await load(p);}return;}
  var dst=target?(target.resolved_path||target.path):p.path;
  if(handles.length){var mode=S.pcMode;S.pcMode="fsa";try{await pcToRx(handles,dst,false);}finally{S.pcMode=mode;}}else{var fl=Array.prototype.map.call(e.dataTransfer.files,function(f){return {name:f.name,type:"file",file:f,size:f.size};});var m=S.pcMode;S.pcMode="simplu";try{await pcToRx(fl,dst,false);}finally{S.pcMode=m;}}
}
[0,1].forEach(function(i){var w=$("f-wrap-"+i);w.addEventListener("dragover",function(e){if(dropAllowed(e,P[i])){e.preventDefault();clearTargets();w.classList.add("drop");e.dataTransfer.dropEffect=e.shiftKey?"move":"copy";}});w.addEventListener("dragleave",function(e){if(!w.contains(e.relatedTarget)){w.classList.remove("drop");}});w.addEventListener("drop",function(e){e.preventDefault();clearTargets();onDrop(e,P[i],null).catch(fail);});
  $("f-pane-"+i).addEventListener("mousedown",function(){if(S.active!==i){setActive(i);mark(P[0]);mark(P[1]);}});$("f-tab-"+i).addEventListener("click",function(){setActive(i);});
  $("f-up-"+i).addEventListener("click",function(){up(P[i]).catch(fail);});$("f-refresh-"+i).addEventListener("click",function(){load(P[i]);if(i===1){loadShortcuts();}});
  $("f-all-"+i).addEventListener("change",function(){var on=$("f-all-"+i).checked;(P[i].view||[]).forEach(function(x){if(on){P[i].sel.add(x.key);}else{P[i].sel.delete(x.key);}});mark(P[i]);});
  Array.prototype.forEach.call($("f-pane-"+i).querySelectorAll("th[data-sort]"),function(th){th.addEventListener("click",function(){var p=P[i],k=th.dataset.sort;p.asc=p.sort===k?!p.asc:true;p.sort=k;render(p);});});});
/* bara dintre panouri */
(function(){var sp=$("f-split"),panes=$("f-panes"),saved=Number(localStorage.getItem("hds-fisiere-latime"));if(saved>15&&saved<85){panes.style.setProperty("--f-st",saved+"%");}
  function set(pct){pct=Math.max(18,Math.min(82,pct));panes.style.setProperty("--f-st",pct+"%");try{localStorage.setItem("hds-fisiere-latime",String(Math.round(pct)));}catch(e){}}
  sp.addEventListener("pointerdown",function(e){e.preventDefault();sp.setPointerCapture(e.pointerId);sp.classList.add("trage");});sp.addEventListener("pointermove",function(e){if(!sp.classList.contains("trage")){return;}var r=panes.getBoundingClientRect();set((e.clientX-r.left)/r.width*100);});
  sp.addEventListener("pointerup",function(){sp.classList.remove("trage");});sp.addEventListener("keydown",function(e){var cur=parseFloat(getComputedStyle(panes).getPropertyValue("--f-st"))||50;if(e.key==="ArrowLeft"){set(cur-3);}if(e.key==="ArrowRight"){set(cur+3);}});})();
/* ---------- nota panoului calculatorului ---------- */
function renderNote(){var n=$("f-pcnote");n.textContent="";var fsa=S.pcMode==="fsa";$("f-choose").hidden=!FSA;n.hidden=FSA&&!!P[0].stack.length;
  if(FSA){if(!P[0].stack.length){n.appendChild(el("p","",T.pcEmpty));}return;}
  var http=CHROMIUM&&!window.isSecureContext;
  if(MOBIL){n.appendChild(el("p","",T.phone));}else if(http){n.appendChild(el("p","",T.pcSimpleEmpty));}else{n.appendChild(el("p","",T.otherBrowser));}
  var row=el("div","f-row"),b1=el("button","",T.chooseFiles),b2=el("button","",T.chooseFolder);b1.type=b2.type="button";b1.addEventListener("click",function(){$("f-files").click();});b2.addEventListener("click",function(){$("f-folder").click();});row.appendChild(b1);if("webkitdirectory" in document.createElement("input")&&!MOBIL){row.appendChild(b2);}n.appendChild(row);
  if(http&&H.pornit&&H.adresa){var a=el("a","f-https",T.openHttps);a.href=H.adresa;a.addEventListener("click",function(e){e.preventDefault();api("salt",{}).then(function(d){location.href=d.adresa;}).catch(function(){location.href=H.adresa;});});var pa=el("p","nota");pa.appendChild(a);pa.appendChild(document.createTextNode(" "+T.httpsWarn));n.appendChild(pa);}
  if(fsa){n.hidden=true;}}
["f-files","f-folder"].forEach(function(id){$(id).addEventListener("change",function(){if($(id).files.length){S.pcMode="simplu";vadd($(id).files);P[0].stack=[];load(P[0]);setActive(0);}$(id).value="";});});
$("f-choose").addEventListener("click",async function(){try{var h=await window.showDirectoryPicker({id:"hds-fisiere",mode:"readwrite"});await useDir(h);}catch(e){if(e.name!=="AbortError"){fail(e);}}});
$("f-reopen").addEventListener("click",async function(){try{var h=await IDB.get("dosar");if(h){await useDir(h);$("f-reopen").hidden=true;}}catch(e){fail(e);}});
/* ---------- scurtaturile receptorului ---------- */
async function loadShortcuts(){try{var d=await api("shortcuts");S.shortcuts=d.items||d.shortcuts||[];}catch(e){S.shortcuts=[];}var box=$("f-shortcuts");box.textContent="";
  S.shortcuts.forEach(function(s){var b=el("button","",s.name);b.type="button";b.title=s.path;b.addEventListener("click",function(){setActive(1);load(P[1],s.path);});b.addEventListener("contextmenu",async function(e){e.preventDefault();if(await promptForm(fmt(T.shortcutRemoveAsk,s.name),[],s.path,T.delete)){await api("shortcuts",{action:"remove",id:s.id});loadShortcuts();}});box.appendChild(b);});}
/* ---------- meniul de la clic dreapta ---------- */
function hideContext(){$("f-context").hidden=true;}
function showContext(p,x,y){var list=chosen(p);if(!list.length){return;}var m=$("f-context");m.textContent="";
  var acts=[["open",T.open],["view",T.keyView],["edit",T.keyEdit],[p.i===0?"copyRight":"copyLeft",p.i===0?T.copyRight:T.copyLeft],["move",T.move],["rename",T.rename]];if(p.i===1){acts.push(["download",T.download],["chmod",T.mode],["shortcut",T.addShortcut]);}acts.push(["delete",T.delete]);
  acts.forEach(function(a){if(list.length!==1&&["open","view","edit","rename"].indexOf(a[0])!==-1){return;}var b=el("button",a[0]==="delete"?"danger":"",a[1]);b.type="button";b.setAttribute("role","menuitem");b.addEventListener("click",function(){hideContext();if(a[0]==="open"){openEntry(p,list[0]).catch(fail);}else{action(a[0]).catch(fail);}});m.appendChild(b);});
  m.hidden=false;m.style.left=Math.max(8,Math.min(x,innerWidth-m.offsetWidth-8))+"px";m.style.top=Math.max(8,Math.min(y,innerHeight-m.offsetHeight-8))+"px";m.querySelector("button").focus();}
document.addEventListener("click",function(e){if(!$("f-context").contains(e.target)){hideContext();}});
/* ---------- ferestrele de intrebare ---------- */
var lastFocus=null;
function closePrompt(v){var cb=S.prompt;S.prompt=null;$("f-prompt-overlay").hidden=true;if(lastFocus&&document.contains(lastFocus)){lastFocus.focus();}if(cb){cb(v);}}
function promptForm(title,fields,note,ok,details){hideContext();if(S.prompt){closePrompt(null);}lastFocus=document.activeElement;$("f-prompt-title").textContent=title;$("f-prompt-ok").textContent=ok||T.continue;$("f-prompt-error").textContent="";var body=$("f-prompt-body");body.textContent="";
  if(note){body.appendChild(el("p","nota",note));}if(details&&details.length){var ul=el("ul","f-details");details.slice(0,200).forEach(function(v){ul.appendChild(el("li","",v));});body.appendChild(ul);}
  (fields||[]).forEach(function(f){var l=el("label","f-field"),i=el("input");l.appendChild(el("span","",f.label));i.name=f.name;i.value=f.value||"";i.required=true;i.autocomplete="off";i.spellcheck=false;if(f.max){i.maxLength=f.max;}l.appendChild(i);body.appendChild(l);});
  $("f-prompt-overlay").hidden=false;var first=body.querySelector("input")||$("f-prompt-ok");first.focus();if(first.select){first.select();}return new Promise(function(res){S.prompt=res;});}
$("f-prompt-form").addEventListener("submit",function(e){e.preventDefault();var res={},ok=true;Array.prototype.forEach.call($("f-prompt-body").querySelectorAll("input"),function(i){var v=i.value.trim();if(!v){$("f-prompt-error").textContent=T.required;ok=false;}if(i.name==="name"&&!validName(v)){ok=false;$("f-prompt-error").textContent=T.invalidName;}if(i.name==="mode"&&!/^[0-7]{3,4}$/.test(v)){ok=false;$("f-prompt-error").textContent=T.invalidMode;}res[i.name]=v;});if(ok){closePrompt(res);}});
$("f-prompt-cancel").addEventListener("click",function(){closePrompt(null);});
/* ---------- lucrarile ---------- */
function makeJob(id,label,cancel){var row=el("div","f-job"),top=el("div","f-job-top"),t=el("span","f-job-name",label),stop=el("button","",T.stop),bar=el("progress"),st=el("p","f-job-status",T.running);stop.type="button";top.appendChild(t);top.appendChild(stop);row.appendChild(top);row.appendChild(bar);row.appendChild(st);$("f-job-list").prepend(row);$("f-jobs").hidden=false;var j={row:row,stop:stop,bar:bar,status:st};stop.addEventListener("click",function(){stop.disabled=true;Promise.resolve(cancel()).catch(fail);});S.jobs.set(id,j);return j;}
function jobProgress(j,cur,total,text){if(total>0){j.bar.max=total;j.bar.value=Math.min(cur,total);}else{j.bar.removeAttribute("value");}j.status.textContent=text||T.running;}
function finishJob(j,text,err){j.stop.hidden=true;j.row.classList.toggle("error",!!err);j.bar.max=1;j.bar.value=1;j.status.textContent=text;}
$("f-jobs-close").addEventListener("click",function(){$("f-jobs").hidden=true;$("f-job-list").textContent="";});
/* ---------- editorul, pe ambele parti ---------- */
function eolOf(t){var k=new Set(t.match(/\r\n|\r|\n/g)||[]);return k.size>1?"mixed":k.has("\r\n")?"crlf":k.has("\r")?"cr":k.has("\n")?"lf":"none";}
function editorDirty(){return S.editor&&!S.editor.ro&&$("f-editor-text").value!==S.editor.original;}
function editorMessage(t,err){$("f-editor-message").textContent=t||"";$("f-editor-message").classList.toggle("eroare",!!err);}
async function openEditor(p,x,ro){
  if(x.locked){message(T.locked,true);return;}if(S.editor&&editorDirty()&&!(await promptForm(T.unsaved,[],"",T.continue))){return;}
  var e={p:p.i,x:x,ro:!!ro};
  if(p.i===1){var d=await api("editor?cale="+encodeURIComponent(x.resolved_path||x.path));e.path=d.path;e.text=d.text;e.version=d.version;e.format=d.format;e.info=[d.format.encoding,d.format.eol,bytes(d.size||0)].join(" · ");}
  else{var f=x.file||await x.h.getFile();if(f.size>1048576){message(T.tooLarge,true);return;}var buf=new Uint8Array(await f.arrayBuffer()),bom=buf.length>=3&&buf[0]===0xEF&&buf[1]===0xBB&&buf[2]===0xBF,txt;
    try{txt=new TextDecoder("utf-8",{fatal:true}).decode(bom?buf.subarray(3):buf);e.enc="utf-8";}catch(err){txt=new TextDecoder("windows-1250").decode(buf);e.enc="other";e.ro=true;e.why=T.notUtf8;}
    if(/[\x00-\x08\x0e-\x1f]/.test(txt)){message(T.binary,true);return;}e.bom=bom;e.eol=eolOf(txt);if(e.eol==="mixed"&&!e.ro){e.ro=true;e.why=T.mixedEol;}e.text=txt;e.path=(pcLabel(P[0])?pcLabel(P[0])+" / ":"")+x.name;e.info=[e.enc==="utf-8"?(bom?"UTF-8 BOM":"UTF-8"):"?",e.eol,bytes(f.size)].join(" · ");}
  S.editor=e;$("f-editor-title").textContent=e.ro?T.viewTitle:T.editorTitle;$("f-editor-path").textContent=e.path;$("f-editor-format").textContent=e.info;$("f-editor-text").value=e.text;$("f-editor-text").readOnly=e.ro;e.original=$("f-editor-text").value;$("f-editor-save").hidden=e.ro;editorMessage(e.why||"");$("f-editor-overlay").hidden=false;$("f-editor-text").focus();
}
async function closeEditor(){if(editorDirty()&&!(await promptForm(T.unsaved,[],"",T.continue))){return;}S.editor=null;$("f-editor-overlay").hidden=true;}
async function saveEditor(){var e=S.editor;if(!e||e.ro){return;}var text=$("f-editor-text").value,b=$("f-editor-save");b.disabled=true;
  try{if(e.p===1){var d=await confirmed("save",{cale:e.path,text:text,version:e.version,format:e.format});if(!d){return;}e.version=d.version||e.version;e.format=d.format||e.format;e.original=text;editorMessage(T.saved);load(P[1]);return;}
    var out=text.replace(/\r\n|\r|\n/g,"\n");if(e.eol==="crlf"){out=out.replace(/\n/g,"\r\n");}else if(e.eol==="cr"){out=out.replace(/\n/g,"\r");}var data=new TextEncoder().encode(out);if(e.bom){var w=new Uint8Array(data.length+3);w.set([0xEF,0xBB,0xBF]);w.set(data,3);data=w;}
    var blob=new Blob([data]);if(S.pcMode==="fsa"&&e.x.h){var wr=await e.x.h.createWritable();await wr.write(blob);await wr.close();editorMessage(T.saved);load(P[0]);}else{var a=el("a");a.href=URL.createObjectURL(blob);a.download=e.x.name;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(a.href);},5000);editorMessage(T.savedDownload);}e.original=text;
  }catch(err){editorMessage(err.message||T.failed,true);}finally{b.disabled=false;}}
$("f-editor-close").addEventListener("click",function(){closeEditor().catch(fail);});$("f-editor-save").addEventListener("click",function(){saveEditor();});
$("f-editor-reload").addEventListener("click",function(){var e=S.editor;if(e){S.editor=null;openEditor(P[e.p],e.x,e.ro).catch(function(er){editorMessage(er.message,true);});}});
$("f-editor-text").addEventListener("input",function(){editorMessage(editorDirty()?T.modified:"");});
/* ---------- tastele ---------- */
Array.prototype.forEach.call(document.querySelectorAll("#f-keys button"),function(b){b.addEventListener("click",function(){action(b.dataset.k).catch(fail);});});
function moveCur(p,d){var n=(p.view||[]).length;if(!n){return;}p.cur=Math.max(0,Math.min(n-1,p.cur+d));mark(p);}
document.addEventListener("keydown",function(e){
  if(!$("f-context").hidden&&e.key==="Escape"){hideContext();return;}
  var ov=!$("f-prompt-overlay").hidden?$("f-prompt-overlay"):!$("f-editor-overlay").hidden?$("f-editor-overlay"):null;
  if(ov){if(e.key==="Escape"){e.preventDefault();if(S.prompt){closePrompt(null);}else{closeEditor().catch(fail);}}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="s"&&ov===$("f-editor-overlay")){e.preventDefault();saveEditor();}if(e.key==="F2"&&ov===$("f-editor-overlay")){e.preventDefault();saveEditor();}return;}
  if(!S.auth){return;}var inField=/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)&&document.activeElement.type!=="checkbox",p=P[S.active],keys={F3:"view",F4:e.shiftKey?"newfile":"edit",F5:"copy",F6:"move",F7:"mkdir",F8:"delete",Delete:"delete",F2:"rename"};
  if(keys[e.key]&&!(inField&&e.key==="Delete")){e.preventDefault();action(keys[e.key]).catch(fail);return;}if(inField){return;}var onButton=/BUTTON|^A$/.test(document.activeElement.tagName);
  if(e.key==="Tab"){e.preventDefault();setActive(1-S.active);mark(P[0]);mark(P[1]);return;}
  if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();moveCur(p,e.key==="ArrowDown"?1:-1);return;}if(e.key==="PageDown"||e.key==="PageUp"){e.preventDefault();moveCur(p,e.key==="PageDown"?15:-15);return;}if(e.key==="Home"||e.key==="End"){e.preventDefault();moveCur(p,e.key==="Home"?-1e6:1e6);return;}
  if(e.key==="Insert"||(e.key===" "&&!e.ctrlKey&&!onButton)){e.preventDefault();var x=(p.view||[])[p.cur];if(x){toggle(p,x.key);moveCur(p,1);}return;}
  if(e.key==="Enter"&&!onButton){e.preventDefault();var y=(p.view||[])[p.cur];if(y){openEntry(p,y).catch(fail);}return;}if(e.key==="Backspace"){e.preventDefault();up(p).catch(fail);return;}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="a"){e.preventDefault();(p.view||[]).forEach(function(v){p.sel.add(v.key);});mark(p);}
});
/* ---------- accesul ---------- */
function setAuth(v,expired){S.auth=!!v;$("f-auth").hidden=!!v;$("f-content").hidden=!v;$("f-logout").hidden=!v;if(!v&&expired){message(T.authExpired,true);$("f-password").focus();}}
$("f-login").addEventListener("submit",async function(e){e.preventDefault();var b=$("f-login-button");b.disabled=true;message(T.checking);try{await api("login",{parola:$("f-password").value});$("f-password").value="";await boot();}catch(er){fail(er);}finally{b.disabled=false;}});
$("externPermis").addEventListener("change",async function(){var i=$("externPermis"),v=i.checked;i.disabled=true;try{var d=await api("access",{permis:v});i.checked=d.extern_permis===undefined?v:!!d.extern_permis;message(T.externalSaved);}catch(e){i.checked=!v;fail(e);}finally{i.disabled=false;}});
$("f-logout").addEventListener("click",async function(){try{await api("logout",{});setAuth(false);message("");}catch(e){fail(e);}});
$("f-pathform").addEventListener("submit",function(e){e.preventDefault();load(P[1],$("f-path-1").value.trim()||"/");});
window.addEventListener("beforeunload",function(e){if(editorDirty()){e.preventDefault();e.returnValue="";}});
async function boot(){try{var d=await api("status");$("f-external-wrap").hidden=!d.local;$("externPermis").checked=!!d.extern_permis;setAuth(d.autentificat);
    if(d.autentificat){setActive(1);renderNote();if(FSA){try{var h=await IDB.get("dosar");if(h){$("f-reopen").textContent=fmt(T.reopenDir,h.name);$("f-reopen").hidden=false;}}catch(e){}}await Promise.all([load(P[1]),loadShortcuts()]);render(P[0]);}else{message("");}}catch(e){fail(e);}}
window.hdsFisiere={folosesteDosar:useDir};
boot();
})();
</script>
</body>
</html>'''


def _cuLimba(text):
	"""<html lang> in limba receptorului: textele paginii vin deja traduse din Python (_()), deci traduce() din
	traducere_pagini, care schimba lang, nu trece pe aici. Pe PC (fara pachet) si in romana pagina ramane lang="ro"."""
	try:
		from .traducere_pagini import limba
	except ImportError:
		return text
	cod = limba()
	return text if cod == "ro" else text.replace('<html lang="ro">', '<html lang="%s">' % cod, 1)
