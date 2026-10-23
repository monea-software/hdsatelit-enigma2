/* Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * mouse-ecran.js: mouse-ul pe ecranul receptorului, in panoul web. Pus in pagina de
 * mouse_web.in_panou, inaintea scriptului panoului, cu traducerile textelor in locul semnului de dupa TRADUSE. Foloseste
 * functiile panoului (cerere, grabesteCaptura, live) abia la un gest, si playerul comun (player.js) fara sa-l schimbe:
 * panoul ii da playerul imaginii live prin window.HDS_MOUSE_PLAYER, imediat dupa ce il face.
 *
 * Unde merge: pe captura din caseta "Ecranul receptorului" si pe imaginea live (in caseta si pe ecranul intreg) cat e
 * pornit "Afisajul receptorului" (fara el meniurile televizorului nu se vad, deci clicul ramane al playerului).
 * Gesturile, aceleasi ca in emulator (ce se face pe televizor e in Components/HdsMouseEcran.py, prin POST /api/mouse):
 * - clic = alege randul de sub mouse; clic pe randul ales sau dublu clic = OK (in meniuri un clic alege si deschide; in
 *   setari doi pasi); clic pe un buton colorat = tasta lui;
 * - tras pe bara de derulare a unei liste = selectia merge acolo (cereri drag, una odata, apoi dragend);
 * - rotita = sus/jos, pas cu pas: pasii se aduna cat o cerere e pe drum (cel mult una la ROTITA_MS), iar 3 pasi sau
 *   mai multi odata (o rotire mare) fac o pagina; NUMAI cu caseta activa (mai jos), altfel rotita deruleaza pagina;
 * - clic dreapta = IESIRE, clic pe rotita = MENIU (Inapoi se foloseste mai des);
 * - pe telefon: atingere = clic, glisare spre dreapta (GLISARE_PX sau mai mult, aproape orizontala) = IESIRE, glisare
 *   in sus sau in jos = rotita cu caseta activa (degetul in sus = lista in jos; cu caseta inactiva deruleaza pagina),
 *   atingere tinuta (TINUT_MS) = MENIU, tasta sau gestul Inapoi al telefonului = IESIRE cu caseta activa.
 * CASETA ACTIVA: un clic sau o atingere in caseta o face activa (chenar discret,
 * clasa mw-caseta); atunci rotita (si glisarea in sus si in jos) merg la televizor si pagina nu se deruleaza peste ea.
 * Un clic in afara casetei o face inactiva (Esc ar fi facut-o si el, dar de la cererea din 08:17 Esc e Iesire la
 * televizor, cu tastatura). Pe ecranul intreg e activa cat tine ecranul intreg (fara chenar).
 * TASTATURA: cat caseta e activa, tastele calculatorului merg la receptor ca o telecomanda (TASTE, TASTE_LISTA si
 * semnele prin fel=text, mai jos) si nu fac nimic in pagina; cu caseta inactiva, tastatura e a paginii.
 * Clicurile merg si cu caseta inactiva (primul clic o si activeaza). Inapoi al telefonului: cand caseta devine activa
 * dintr-o atingere (sau pe ecranul intreg, pe telefon), se pune o intrare in istoria browserului (history.pushState);
 * Inapoi o scoate, iar la popstate se trimite IESIRE si intrarea se pune iar. Caseta facuta inactiva isi scoate
 * intrarea (history.back), deci Inapoi face apoi ce face de obicei. Cu mouse-ul nu se pune nicio intrare (pe PC
 * butonul Inapoi al browserului ramane al lui; IESIRE e clicul dreapta). Pe Android, Inapoi pe ecranul intreg al
 * browserului iese intai din ecranul intreg (browserul nu da popstate); ecranul intreg facut din CSS (iPhone) il da.
 * Locul se trimite in procente din imaginea ecranului: pe captura, dreptunghiul aratat al imaginii (fara benzile negre
 * ale casetei); in imaginea live, cadrul 16:9 al playerului, nu elementul <video>, care sta micsorat in fereastra
 * televizorului cand lista de canale e deschisa (clicul pe lista din afisaj merge pe lista). Semnul clicului: un cerc
 * mic care se stinge in 0,35 s. Cursorul arata mana cat mouse-ul merge.
 *
 * TELECOMANDA PE ECRANUL INTREG: in bara playerului, dupa "Afisajul
 * receptorului", comutatorul "Telecomanda", aratat numai pe ecranul intreg. Pornit, telecomanda din panou (aceeasi:
 * tastele ei, apasarea lunga si trimiterea ei; mutata in player cat dureaza ecranul intreg si pusa inapoi la iesire) sta
 * peste imagine, implicit in dreapta, intr-o singura coloana, ca o telecomanda adevarata: Compact = tastele de baza;
 * Toate tastele = dedesubt si cele in plus. Cand nu incape in inaltime se micsoreaza proportional. Se muta tragand-o de
 * bara ei de sus (mouse sau deget); trasa langa marginea din dreapta se lipeste iar acolo (ca telecomanda emulatorului).
 * Locul (lipita in dreapta sau procente din spatiul liber, ca sa ramana in ecran la orice marime) si starea
 * pornit/oprit raman in browser (localStorage; fara el, implicit oprita si in dreapta).
 */
(function(){
  "use strict";
  if(window.HDS_MOUSE){ return; }

  // textele noi (romana); traducerile vin de la receptor, la servire (mouse_web.TEXTE)
  var TEXTE = {
    ajutor: "Mouse pe ecran: clic = alege, dublu clic = OK, clic dreapta = Ieșire, clic pe rotiță = Meniu; după un clic în casetă, rotița = sus și jos (un clic în afară o oprește).",
    taste: "Tastatura, cu caseta activă: săgeți, Enter = OK, Esc sau Backspace = Ieșire, 0-9, PgUp/PgDn = pagină (la privit, canal), Home/End, F1-F4 = culorile, M = Meniu, I = Info, E = EPG, T = Teletext, spațiu = Pauză; într-un câmp de text deschis pe televizor, literele se scriu în el.",
    tastatura: "Tastatură: %s",
    ajutor_deget: "Pe ecran: atinge = alege, atinge rândul ales = OK, glisează spre dreapta sau Înapoi = Ieșire, ține apăsat = Meniu; după o atingere în casetă, glisarea în sus și în jos derulează lista.",
    ajutor_live: "Mouse-ul merge pe imaginea live cu \"Afișajul receptorului\" pornit.",
    tasta: "Mouse: %s",
    rand: "Mouse: rândul %s",
    nimic: "Mouse: nimic de apăsat acolo",
    eroare: "Clicul nu a ajuns la receptor (%s).",
    telecomanda: "Telecomandă",
    telecomanda_titlu: "Telecomanda peste imagine, pe ecranul întreg",
    muta: "Trage de aici ca să muți telecomanda",
    ascunde: "Ascunde telecomanda"
  };
  var TRADUSE = /*__TEXTE__*/null;
  function tx(cheie){
    return (TRADUSE && TRADUSE[cheie]) || TEXTE[cheie] || cheie;
  }

  var ROTITA_MS = 80;       // cel mult o cerere de rotita la atatea ms; pasii de intre ele se aduna
  var PASI_MAXIM = 12;      // la fel ca HdsMouseEcran.PASI_MAXIM
  var PRAG_TRAS = 6;        // px: de la atata miscare cu butonul tinut, clicul devine tras
  var TINUT_MS = 600;       // atingerea tinuta pe telefon = MENIU
  var GLISARE_PX = 60;      // glisarea spre dreapta = IESIRE de la atatia px (sau 15% din latimea imaginii, cat e mai mult)
  var SUPRIMA_MS = 450;     // dupa un tras, o glisare sau o atingere tinuta, clicul venit imediat nu mai pleaca
  // gesturile trimise (numele spun butonul mouse-ului; tasta o alege receptorul: dreapta = IESIRE, mijloc = MENIU)
  var FEL_IESIRE = "dreapta", FEL_MENIU = "mijloc";
  var ISTORIE = "hdsMouseCaseta";   // semnul intrarii puse in istoria browserului cat caseta e activa
  // TASTATURA: cu caseta activa (sau pe ecranul intreg) tastele calculatorului merg la
  // receptor ca o telecomanda si nu fac nimic in pagina; cu caseta inactiva tastatura ramane a paginii.
  // - tastele fara semn: prin /api/remotecontrol (aceeasi cale ca telecomanda din panou), cu codurile telecomenzii;
  // - semnele (litere, cifre, spatiu, Backspace): prin /api/mouse?fel=text; receptorul le scrie in campul de text
  //   deschis pe televizor (cautarea de canale, campurile de text), iar fara camp le face taste: cifrele, M = Meniu,
  //   I = Info, E = EPG, T = Teletext, spatiu = Pauza, Backspace = Iesire (HdsMouseEcran.text).
  var TASTE = {
    ArrowUp: 103, ArrowDown: 108, ArrowLeft: 105, ArrowRight: 106,
    Enter: 352, Escape: 174,
    F1: 398, F2: 399, F3: 400, F4: 401
  };
  // Page Up/Down si Home/End nu sunt taste ale telecomenzii: le face receptorul (HdsMouseEcran: pagina, capat)
  var TASTE_LISTA = {PageUp: ["pagina", -1], PageDown: ["pagina", 1], Home: ["capat", -1], End: ["capat", 1]};
  var TASTA_MS = 150;       // o tasta tinuta apasata: cel mult o repetare la atatea ms (ca rotita)
  var TEXT_MAXIM = 64;      // la fel ca HdsMouseEcran.TEXT_MAXIM
  var PRAG_LIPIRE = 28;     // telecomanda trasa la atatia px de marginea din dreapta se lipeste acolo
  var MARGINE = 12;         // px intre telecomanda si marginea ecranului
  var CHEIE_TL = "hdsTelecomandaImagine";
  var KEY_OK = 352;

  var STIL = [
    /* caseta inactiva: degetul in sus si in jos deruleaza pagina (pan-y); activa: totul merge la televizor */
    ".mw-activ{cursor:pointer;touch-action:pan-y;-webkit-touch-callout:none;-webkit-user-select:none;user-select:none;}",
    ".mw-activ.mw-caseta{touch-action:none;}",
    ".mw-activ img{-webkit-user-drag:none;}",
    /* semnul casetei active: un chenar subtire inauntru (fara chenar pe ecranul intreg, unde e activa mereu) */
    "html .mw-activ.mw-caseta{outline:2px solid rgba(96,165,250,.8);outline-offset:-2px;}",
    "html .hp:fullscreen .mw-activ.mw-caseta,html .hp.hp-plin-css .mw-activ.mw-caseta{outline:none;}",
    ".hp.hp-bara-ascunsa .mw-activ{cursor:none;}",
    "#cutieCaptura{position:relative;}",
    ".mw-semn{position:absolute;width:22px;height:22px;margin:-13px 0 0 -13px;border:2px solid rgba(255,255,255,.9);border-radius:50%;box-shadow:0 0 0 1px rgba(0,0,0,.4);pointer-events:none;z-index:4;animation:mw-semn .35s ease-out forwards;}",
    "@keyframes mw-semn{from{transform:scale(.45);opacity:.95;}to{transform:scale(1.3);opacity:0;}}",
    "@media (prefers-reduced-motion:reduce){.mw-semn{animation:mw-stinge .35s linear forwards;}}",
    "@keyframes mw-stinge{from{opacity:.9;}to{opacity:0;}}",
    /* comutatorul din bara playerului: numai pe ecranul intreg (in caseta, telecomanda sta langa imagine) */
    ".hp .hp-bara label.mw-comutator-tl{display:none;}",
    ".hp:fullscreen .hp-bara label.mw-comutator-tl,.hp.hp-plin-css .hp-bara label.mw-comutator-tl{display:inline-flex;}",
    /* telecomanda peste imagine: bara de tras deasupra, telecomanda panoului dedesubt, intr-o coloana */
    ".mw-tl-plutitor{position:absolute;left:0;top:0;z-index:6;display:flex;flex-direction:column;transform-origin:0 0;cursor:default;filter:drop-shadow(0 8px 24px rgba(0,0,0,.55));}",
    ".mw-tl-bara{display:flex;align-items:center;gap:8px;min-height:36px;padding:0 4px 0 10px;border:1px solid #2a2f38;border-bottom:0;border-radius:12px 12px 0 0;background:rgba(15,18,22,.94);color:#c9d2e3;font-size:13px;font-weight:600;cursor:grab;touch-action:none;-webkit-user-select:none;user-select:none;}",
    ".mw-tl-bara.mw-trag{cursor:grabbing;}",
    ".mw-tl-bara svg{width:16px;height:16px;fill:#8891a0;flex:none;}",
    ".mw-tl-bara .mw-titlu{flex:1;min-width:0;overflow:hidden;white-space:nowrap;}",
    /* (html .hp ...: peste regulile temelor din cadru_web.py, html.hds-cadru[data-tema] button) */
    "html .hp .mw-tl-bara button.mw-inchide{min-width:36px;min-height:32px;padding:0;border:0;border-radius:8px;background:transparent;color:#c9d2e3;font:inherit;font-size:20px;line-height:1;cursor:pointer;}",
    "html .hp .mw-tl-bara button.mw-inchide:hover{background:rgba(255,255,255,.08);}",
    "#telecomanda.mw-plutitoare{width:300px;box-sizing:border-box;margin:0;border-radius:0 0 12px 12px;background:rgba(24,28,35,.9);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);}",
    "#telecomanda.mw-plutitoare .tl-titlu,#telecomanda.mw-plutitoare .tl-stare{display:none;}",
    "#telecomanda.mw-plutitoare .tl-cap{justify-content:center;margin:0 0 10px;}",
    "#telecomanda.mw-plutitoare .tl-compact{display:flex;}",
    /* Toate tastele, sub cele compacte: numai tastele care nu sunt deja sus (fara a doua pornire, cifre, cerc, culori) */
    /* playerul sta in caseta panoului (.ecran-tel.cu-toate): regulile ei de doua coloane nu se aplica aici */
    "#telecomanda.mw-plutitoare .tl-toate{display:none;margin-top:10px;padding-top:10px;border-top:1px solid #2a2f38;}",
    "#telecomanda.mw-plutitoare[data-mod=\"toate\"] .tl-toate{display:flex;flex-direction:column;align-items:stretch;gap:8px;}",
    "#telecomanda.mw-plutitoare .tl-toate .tl-parte+.tl-parte{margin:0;padding:0;border:0;}",
    "#telecomanda.mw-plutitoare .tl-toate .tl-parte:first-child>:not(.tl-r3){display:none;}",
    "#telecomanda.mw-plutitoare .tl-toate .tl-culori,#telecomanda.mw-plutitoare .tl-toate .tl-sunet>.tl-rocker{display:none;}",
    "#telecomanda.mw-plutitoare .tl-toate .tl-sunet{display:block;}",
    "#telecomanda.mw-plutitoare .tl-toate .tl-mijloc{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;}"
  ].join("\n");

  var IC_TELECOMANDA = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 2h6a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm3 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm-2 7v2h4v-2h-4zm0 4v2h4v-2h-4z"/></svg>';
  var IC_MANER = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5a2 2 0 1 1 0 .01zm8 0a2 2 0 1 1 0 .01zM8 12a2 2 0 1 1 0 .01zm8 0a2 2 0 1 1 0 .01zM8 19a2 2 0 1 1 0 .01zm8 0a2 2 0 1 1 0 .01z"/></svg>';

  function stilPus(){
    if(document.getElementById("hdsMouseStil")){ return; }
    var s = document.createElement("style");
    s.id = "hdsMouseStil";
    s.textContent = STIL;
    document.head.appendChild(s);
  }

  // ------------------------------------------------------------ locul in procente
  // r: dreptunghiul imaginii ecranului; strans: in afara lui, locul se aduce la margine (trasul iesit din imagine)
  function procente(r, cx, cy, strans){
    if(!r || r.width < 2 || r.height < 2){ return null; }
    var xp = (cx - r.left) / r.width * 100, yp = (cy - r.top) / r.height * 100;
    if(strans){
      xp = Math.min(100, Math.max(0, xp)); yp = Math.min(100, Math.max(0, yp));
    } else if(xp < 0 || xp > 100 || yp < 0 || yp > 100){
      return null;
    }
    return {xp: Math.round(xp * 100) / 100, yp: Math.round(yp * 100) / 100};
  }
  // captura: imaginea pusa cu object-fit:contain in caseta 16:9; dreptunghiul ei aratat, fara benzile negre. Cat se
  // incarca urmatoarea captura (o data la 3 s) Chrome da naturalWidth 0 (masurat pe receptor: ~0,7 s), desi arata tot
  // captura de dinainte: marimea se ia atunci de la ultima captura incarcata (marimeCaptura)
  var marimeCaptura = {w: 0, h: 0};
  function dreptunghiCaptura(img){
    var r = img.getBoundingClientRect();
    var nw = img.naturalWidth || marimeCaptura.w || 16, nh = img.naturalHeight || marimeCaptura.h || 9;
    var s = Math.min(r.width / nw, r.height / nh);
    var w = nw * s, h = nh * s;
    return {left: r.left + (r.width - w) / 2, top: r.top + (r.height - h) / 2, width: w, height: h};
  }

  // ------------------------------------------------------------ cererile, una odata
  var coada = [], inLucru = false, ceasCoada = null, ultimaRotita = 0;
  function pune(fel, date){
    var ultim = coada[coada.length - 1];
    if(ultim && fel === "drag" && ultim.fel === "drag" && !date.nou){ date.nou = ultim.date.nou; ultim.date = date; urmatorul(); return; }
    // semnele scrise cat o cerere e pe drum pleaca impreuna (cel mult TEXT_MAXIM)
    if(ultim && fel === "text" && ultim.fel === "text" && ultim.date.text.length + date.text.length <= TEXT_MAXIM){
      ultim.date.text += date.text; urmatorul(); return;
    }
    if(ultim && fel === "rotita" && ultim.fel === "rotita"){
      ultim.date.pasi += date.pasi; ultim.date.xp = date.xp; ultim.date.yp = date.yp;
      urmatorul(); return;
    }
    coada.push({fel: fel, date: date});
    urmatorul();
  }
  function urmatorul(){
    if(inLucru || ceasCoada || !coada.length){ return; }
    var c = coada[0];
    if(c.fel === "rotita"){
      var astept = ROTITA_MS - (Date.now() - ultimaRotita);
      if(astept > 0){ ceasCoada = setTimeout(function(){ ceasCoada = null; urmatorul(); }, astept); return; }
    }
    coada.shift();
    if(c.fel === "rotita"){
      c.date.pasi = Math.max(-PASI_MAXIM, Math.min(PASI_MAXIM, c.date.pasi));
      if(!c.date.pasi){ urmatorul(); return; }     // pasi in sens opus, adunati la zero
      ultimaRotita = Date.now();
    }
    var q = ["fel=" + c.fel];
    Object.keys(c.date).forEach(function(k){
      if(c.date[k] !== undefined && c.date[k] !== null){ q.push(k + "=" + encodeURIComponent(c.date[k])); }
    });
    inLucru = true;
    var cale = c.fel === "tasta" ? "/api/remotecontrol?command=" + encodeURIComponent(c.date.command) : "/api/mouse?" + q.join("&");
    window.cerere(cale, "POST").then(function(d){
      laRaspuns(c.fel, d || {}, c.date);
    }).catch(function(e){
      stare(tx("eroare").replace("%s", (e && e.message) || "eroare"));
    }).then(function(){
      inLucru = false;
      urmatorul();
    });
  }

  function stare(text){
    var s = document.getElementById("starTasta");
    if(s){ s.textContent = text; }
  }
  function numeTasta(cod){
    var b = document.querySelector('#telecomanda button[data-cod="' + cod + '"]');
    return (b && b.getAttribute("data-nume")) || String(cod);
  }
  function laRaspuns(fel, d, date){
    var f = d.facut;
    if(fel === "tasta" || fel === "text"){
      var ce = fel === "tasta" ? numeTasta(d.command) : (f === "text" ? date.text.replace(/\u0008/g, "Backspace") :
        (f === "tasta" ? numeTasta(d.tasta) : ""));
      if(ce){ stare(tx("tastatura").replace("%s", ce)); }
      if((d.result && fel === "tasta") || (f && f !== "nimic")){
        if(typeof window.grabesteCaptura === "function"){ window.grabesteCaptura(); }
      }
      return;
    }
    if(f === "selectie" || f === "bara" || f === "derulare"){ stare(tx("rand").replace("%s", (d.rand | 0) + 1)); }
    else if(f === "ok"){ stare(tx("tasta").replace("%s", numeTasta(KEY_OK))); }
    else if(f === "tasta" || f === "buton"){ stare(tx("tasta").replace("%s", numeTasta(d.tasta))); }
    else if(fel === "clic"){ stare(tx("nimic")); }
    // dupa un clic care a facut ceva, captura de langa vine mai repede (ca dupa o tasta a telecomenzii)
    if(f && f !== "nimic" && typeof window.grabesteCaptura === "function"){ window.grabesteCaptura(); }
  }

  // ------------------------------------------------------------ rotita
  var restRotita = 0;
  function pasiRotita(e){
    var px = e.deltaY * (e.deltaMode === 1 ? 33 : (e.deltaMode === 2 ? 800 : 1));
    // o rotita cu trepte da cate un eveniment mare pe treapta (40-125 px): un pas, sau mai multi la o rotire mare;
    // un touchpad da multe evenimente mici: se aduna pana la 100 px
    if(Math.abs(px) >= 40){ restRotita = 0; return (px > 0 ? 1 : -1) * Math.max(1, Math.round(Math.abs(px) / 100)); }
    restRotita += px;
    if(Math.abs(restRotita) >= 100){
      var n = restRotita > 0 ? 1 : -1;
      restRotita -= n * 100;
      return n;
    }
    return 0;
  }

  // ------------------------------------------------------------ o suprafata (captura sau cadrul imaginii live)
  // el: elementul ascultat; dreptunghi(): imaginea ecranului in pagina; activ(): daca mouse-ul merge acum
  var tipUltim = "mouse";
  function semn(el, cx, cy){
    var r = el.getBoundingClientRect();
    var s = document.createElement("span");
    s.className = "mw-semn";
    s.style.left = (cx - r.left) + "px";
    s.style.top = (cy - r.top) + "px";
    el.appendChild(s);
    setTimeout(function(){ if(s.parentNode){ s.parentNode.removeChild(s); } }, 450);
  }
  // ------------------------------------------------------------ caseta activa si Inapoi al telefonului
  // activa: un clic sau o atingere in caseta; cuIstorie: activata din deget (intrarea in istorie); pusa: intrarea
  // noastra e (sau era) in istorie; ignoraPop: cate popstate vin din history.back() al nostru
  var caseta = {activa: false, cuIstorie: false, pusa: false, ignoraPop: 0, plin: false};
  function pePlin(){
    var p = stareMouse.player;
    return !!(p && p._ePlin && p._ePlin());
  }
  function casetaActiva(){ return caseta.activa || pePlin(); }
  function suprafataMerge(){
    return capturaActiva() || !!(stareMouse.player && liveActiv(stareMouse.player));
  }
  function peIntrare(){
    try { return !!(window.history.state && window.history.state[ISTORIE]); } catch(e) { return false; }
  }
  function puneIntrarea(){
    if(peIntrare()){ caseta.pusa = true; return; }
    try {
      var st = {}; st[ISTORIE] = 1;
      window.history.pushState(st, "");
      caseta.pusa = true;
    } catch(e) {}
  }
  function scoateIntrarea(){
    if(!peIntrare()){ return; }
    caseta.ignoraPop++;
    try { window.history.back(); } catch(e) { caseta.ignoraPop--; }
  }
  function activeaza(deget){
    caseta.activa = true;
    if(deget){ caseta.cuIstorie = true; puneIntrarea(); }
    actualizeaza();
  }
  function dezactiveaza(){
    if(!caseta.activa && !peIntrare()){ return; }
    caseta.activa = false; caseta.cuIstorie = false;
    scoateIntrarea();
    actualizeaza();
  }
  function laPopstate(){
    if(caseta.ignoraPop > 0){
      // intrarea scoasa de noi; daca intre timp caseta s-a facut iar activa din deget, intrarea se pune la loc
      caseta.ignoraPop--; caseta.pusa = false;
      if(casetaActiva() && caseta.cuIstorie && !caseta.ignoraPop){ puneIntrarea(); }
      return;
    }
    if(peIntrare()){ caseta.pusa = true; return; }       // Inainte, inapoi pe intrarea noastra: nimic de trimis
    if(!caseta.pusa){ return; }                         // alta intrare a paginii: nu e treaba mouse-ului
    caseta.pusa = false;
    if(!casetaActiva() || !suprafataMerge()){ return; } // caseta inactiva: Inapoi obisnuit
    pune(FEL_IESIRE, {});
    puneIntrarea();
  }
  // ecranul intreg: activa cat tine; la intrare, pe telefon, intrarea in istorie; la iesire, inactiva
  function urmeazaPlin(){
    var plin = pePlin();
    if(plin === caseta.plin){ return; }
    caseta.plin = plin;
    if(plin){
      if(cuDegetul() || tipUltim === "touch"){ caseta.cuIstorie = true; puneIntrarea(); }
    } else {
      caseta.activa = false; caseta.cuIstorie = false;
      scoateIntrarea();
    }
    actualizeaza();
  }
  function legaCaseta(){
    window.addEventListener("popstate", laPopstate);
    // pagina reincarcata pe intrarea noastra (caseta e inactiva la incarcare): intrarea se scoate, ca Inapoi sa nu
    // ramana fara efect o data
    if(peIntrare()){ caseta.pusa = true; scoateIntrarea(); }
    // un clic (sau o atingere) in afara casetei o face inactiva; pe ecranul intreg ramane activa
    document.addEventListener("pointerdown", function(e){
      if(!caseta.activa || pePlin()){ return; }
      var t = e.target, cutie = document.getElementById("cutieCaptura"), p = stareMouse.player;
      if(t && ((cutie && cutie.contains(t)) || (p && p.e && p.e.cadru && p.e.cadru.contains(t)))){ return; }
      dezactiveaza();
    }, true);
    document.addEventListener("keydown", laTasta, true);
  }
  // tastatura ca telecomanda, cat caseta e activa (Esc trimite Iesire; caseta se opreste cu un clic in afara ei)
  var ultimaTasta = 0;
  function laTasta(e){
    if(!casetaActiva() || !suprafataMerge()){ return; }
    var k = e.key || "";
    var altGr = !!(e.getModifierState && e.getModifierState("AltGraph"));
    // scurtaturile browserului (Ctrl, Alt, Cmd) raman ale lui; AltGr scrie semne (ă, ș ...)
    if((e.ctrlKey || e.altKey || e.metaKey) && !(altGr && k.length === 1)){ return; }
    var t = e.target, tag = t && t.tagName;
    if(tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)){ return; }
    // pe ecranul intreg Esc il inchide (browserul sau playerul), ca peste tot
    if(k === "Escape" && pePlin()){ return; }
    var semn = k.length === 1 ? k : (k === "Backspace" ? "\b" : "");
    var lista = TASTE_LISTA[k], cod = TASTE[k];
    if(!semn && !lista && !cod){ return; }
    e.preventDefault(); e.stopPropagation();
    // tinuta apasata: cel mult o repetare la TASTA_MS, si nu mai mult de doua cereri in asteptare
    if(e.repeat && (Date.now() - ultimaTasta < TASTA_MS || coada.length >= 2)){ return; }
    ultimaTasta = Date.now();
    if(semn){ pune("text", {text: semn}); }
    else if(lista){ pune(lista[0], {pasi: lista[1]}); }
    else { pune("tasta", {command: cod}); }
  }

  function legaSuprafata(el, dreptunghi, activ){
    var apasat = null, suprimaPana = 0;
    function punct(cx, cy, strans){ return procente(dreptunghi(), cx, cy, strans); }
    el.addEventListener("pointerdown", function(e){
      if(!activ()){ return; }
      tipUltim = e.pointerType || "mouse";
      // mouse-ul activeaza caseta la apasare (orice buton); degetul abia la atingere (click), ca o glisare care
      // deruleaza pagina sa nu o activeze
      if(tipUltim !== "touch"){ activeaza(false); }
      if(e.button !== 0){ return; }
      var p = punct(e.clientX, e.clientY);
      if(!p){ return; }
      var a = {id: e.pointerId, tip: tipUltim, cx: e.clientX, cy: e.clientY, p: p, ultim: p, tras: false, tinut: null, tinutGata: false};
      apasat = a;
      if(a.tip === "touch"){
        a.tinut = setTimeout(function(){
          if(apasat !== a || a.tras){ return; }
          a.tinutGata = true;
          semn(el, a.cx, a.cy);
          activeaza(true);
          pune(FEL_MENIU, {});
        }, TINUT_MS);
      } else {
        try { el.setPointerCapture(e.pointerId); } catch(er) {}
      }
    }, true);
    el.addEventListener("pointermove", function(e){
      var a = apasat;
      if(!a || a.id !== e.pointerId){ return; }
      var dx = e.clientX - a.cx, dy = e.clientY - a.cy;
      if(a.tip === "touch"){
        // directia se hotaraste o data, la prag: orizontala = glisare (IESIRE la ridicare, spre dreapta), verticala =
        // rotita (un pas la fiecare ~ un rand al listei, 1/14 din inaltimea imaginii), numai cu caseta activa
        if(!a.tras){
          if(Math.abs(dx) < 2 * PRAG_TRAS && Math.abs(dy) < 2 * PRAG_TRAS){ return; }
          a.tras = true; a.yUltim = a.cy; clearTimeout(a.tinut);
          a.orizontal = Math.abs(dx) > Math.abs(dy);
        }
        if(a.orizontal || !casetaActiva()){ return; }
        var pas = Math.max(16, dreptunghi().height / 14);
        var d = a.yUltim - e.clientY;
        var n = d > 0 ? Math.floor(d / pas) : Math.ceil(d / pas);
        if(n){ a.yUltim -= n * pas; pune("rotita", {xp: a.p.xp, yp: a.p.yp, pasi: n}); }
        return;
      }
      if(!a.tras && Math.abs(dx) + Math.abs(dy) < PRAG_TRAS){ return; }
      var p = punct(e.clientX, e.clientY, true);
      if(!p){ return; }
      pune("drag", {xp: p.xp, yp: p.yp, x0p: a.p.xp, y0p: a.p.yp, nou: a.tras ? null : 1});
      a.tras = true; a.ultim = p;
    }, true);
    function sfarsit(e){
      var a = apasat;
      if(!a || a.id !== e.pointerId){ return; }
      apasat = null;
      clearTimeout(a.tinut);
      if(a.tras || a.tinutGata){ suprimaPana = Date.now() + SUPRIMA_MS; }
      if(a.tras && a.orizontal && e.type === "pointerup"){
        // glisarea spre dreapta, aproape orizontala, destul de lunga = IESIRE (spre stanga: nimic)
        var gx = e.clientX - a.cx, gy = e.clientY - a.cy;
        if(gx >= Math.max(GLISARE_PX, dreptunghi().width * 0.15) && Math.abs(gy) <= gx * 0.6){
          semn(el, e.clientX, e.clientY);
          activeaza(true);
          pune(FEL_IESIRE, {});
        }
        return;
      }
      if(a.tras && a.tip !== "touch"){
        var p = punct(e.clientX, e.clientY, true) || a.ultim;
        pune("dragend", {xp: p.xp, yp: p.yp});
      }
    }
    el.addEventListener("pointerup", sfarsit, true);
    el.addEventListener("pointercancel", sfarsit, true);
    // degetul pe caseta activa (sau intr-o glisare orizontala): pagina nu se deruleaza. touch-action:none singur nu
    // ajunge: in Chrome (probat pe receptor, cu atingeri de telefon) pagina se derula si venea pointercancel dupa
    // ~18 px; touchmove oprit cu preventDefault tine gestul in pagina
    el.addEventListener("touchmove", function(e){
      var a = apasat;
      if(e.cancelable && activ() && (casetaActiva() || (a && a.tras && a.orizontal))){ e.preventDefault(); }
    }, {passive: false});
    // tras peste captura: fara tragerea imaginii de catre browser (dupa ea nu mai vin miscari si nici ridicarea)
    el.addEventListener("dragstart", function(e){ if(activ()){ e.preventDefault(); } }, true);
    // in faza de captura: clicul nu mai ajunge la <video> (care porneste redarea oprita la clic)
    el.addEventListener("click", function(e){
      if(!activ()){ return; }
      e.preventDefault(); e.stopPropagation();
      if(Date.now() < suprimaPana || e.button){ return; }
      activeaza(tipUltim === "touch");
      var p = punct(e.clientX, e.clientY);
      if(!p){ return; }
      semn(el, e.clientX, e.clientY);
      pune("clic", {xp: p.xp, yp: p.yp, clicuri: Math.max(1, Math.min(3, e.detail || 1))});
    }, true);
    el.addEventListener("mousedown", function(e){
      // clicul pe rotita: fara derularea automata a browserului
      if(e.button === 1 && activ()){ e.preventDefault(); }
    }, true);
    el.addEventListener("auxclick", function(e){
      if(e.button !== 1 || !activ()){ return; }
      e.preventDefault(); e.stopPropagation();
      if(!punct(e.clientX, e.clientY)){ return; }
      semn(el, e.clientX, e.clientY);
      pune(FEL_MENIU, {});
    }, true);
    el.addEventListener("contextmenu", function(e){
      if(!activ()){ return; }
      e.preventDefault(); e.stopPropagation();
      // pe telefon, atingerea tinuta (MENIU) o trimite ceasul ei (TINUT_MS); meniul browserului nu se deschide
      if(tipUltim === "touch" || !punct(e.clientX, e.clientY)){ return; }
      semn(el, e.clientX, e.clientY);
      pune(FEL_IESIRE, {});
    }, true);
    el.addEventListener("wheel", function(e){
      // caseta inactiva: rotita ramane a paginii (fara preventDefault)
      if(!activ() || !casetaActiva()){ return; }
      var p = punct(e.clientX, e.clientY);
      if(!p){ return; }
      e.preventDefault();
      var n = pasiRotita(e);
      if(n){ pune("rotita", {xp: p.xp, yp: p.yp, pasi: n}); }
    }, {passive: false});
  }

  // ------------------------------------------------------------ captura si imaginea live
  function capturaActiva(){
    var img = document.getElementById("captura");
    var live = window.live;
    return !!img && !(live && live.pornit) && img.style.display !== "none" && (img.naturalWidth > 0 || marimeCaptura.w > 0);
  }
  function liveActiv(p){
    var live = window.live;
    return !!(live && live.pornit && live.player === p && p._stratPornit && p._stratPornit());
  }
  var stareMouse = {player: null, ajutor: null};
  // randul de ajutor: pentru deget pe telefon si tableta (indicatorul principal e degetul, fara mouse), altfel pentru mouse
  function cuDegetul(){
    try { return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches && !window.matchMedia("(any-pointer: fine)").matches); } catch(e) { return false; }
  }
  function actualizeaza(){
    var cutie = document.getElementById("cutieCaptura"), activa = casetaActiva();
    if(cutie){
      var c = capturaActiva();
      cutie.classList.toggle("mw-activ", c);
      cutie.classList.toggle("mw-caseta", c && activa);
    }
    var p = stareMouse.player, liveMerge = false;
    if(p){
      liveMerge = !!(window.live && window.live.pornit && window.live.player === p);
      var l = liveActiv(p);
      p.e.cadru.classList.toggle("mw-activ", l);
      p.e.cadru.classList.toggle("mw-caseta", l && activa);
    }
    if(stareMouse.ajutor){
      stareMouse.ajutor.textContent = (liveMerge && !liveActiv(p)) ? tx("ajutor_live") :
        (cuDegetul() ? tx("ajutor_deget") : tx("ajutor") + " " + tx("taste"));
    }
  }
  function legaCaptura(){
    var cutie = document.getElementById("cutieCaptura"), img = document.getElementById("captura");
    if(!cutie || !img){ return; }
    legaSuprafata(cutie, function(){ return dreptunghiCaptura(img); }, capturaActiva);
    img.addEventListener("load", function(){
      if(img.naturalWidth > 0){ marimeCaptura.w = img.naturalWidth; marimeCaptura.h = img.naturalHeight; }
      actualizeaza();
    });
    img.addEventListener("error", actualizeaza);
    // randul de ajutor: sub caseta (si sub imaginea live, care se deschide in acelasi loc)
    var ajutor = document.createElement("div");
    ajutor.className = "stare";
    ajutor.id = "ajutorMouse";
    var dupa = document.getElementById("playerPanou") || cutie;
    dupa.parentNode.insertBefore(ajutor, dupa.nextSibling);
    stareMouse.ajutor = ajutor;
    var pp = document.getElementById("playerPanou");
    if(pp && window.MutationObserver){ new MutationObserver(actualizeaza).observe(pp, {attributes: true, attributeFilter: ["class"]}); }
    actualizeaza();
  }
  function legaLive(p){
    if(!p || !p.e || !p.e.cadru || stareMouse.player === p){ return; }
    stareMouse.player = p;
    legaSuprafata(p.e.cadru, function(){ return p.e.cadru.getBoundingClientRect(); }, function(){ return liveActiv(p); });
    if(p.e.bifa){ p.e.bifa.addEventListener("change", actualizeaza); }
    // ecranul intreg (Fullscreen API sau facut din CSS, clasa hp-plin-css): caseta activa cat tine
    ["fullscreenchange", "webkitfullscreenchange"].forEach(function(ev){ document.addEventListener(ev, urmeazaPlin); });
    if(window.MutationObserver && p.e.radacina){
      new MutationObserver(urmeazaPlin).observe(p.e.radacina, {attributes: true, attributeFilter: ["class"]});
    }
    telecomandaInPlayer(p);
    urmeazaPlin();
    actualizeaza();
  }

  // ------------------------------------------------------------ telecomanda peste imagine, pe ecranul intreg
  var tl = {player: null, bifa: null, plutitor: null, arata: false, inapoi: null, marime: null, trage: null,
    loc: {pornita: false, dreapta: true, x: 1, y: 0.5}};
  function citesteLoc(){
    var o = null;
    try { o = JSON.parse(localStorage.getItem(CHEIE_TL) || "null"); } catch(e) { o = null; }
    function frac(v, implicit){ v = Number(v); return isFinite(v) ? Math.min(1, Math.max(0, v)) : implicit; }
    if(!o || typeof o !== "object"){ return {pornita: false, dreapta: true, x: 1, y: 0.5}; }
    return {pornita: o.pornita === true, dreapta: o.dreapta !== false, x: frac(o.x, 1), y: frac(o.y, 0.5)};
  }
  function scrieLoc(){
    try { localStorage.setItem(CHEIE_TL, JSON.stringify(tl.loc)); } catch(e) {}
  }
  function ePlin(){
    return !!(tl.player && tl.player._ePlin && tl.player._ePlin());
  }
  function construiestePlutitor(){
    var c = document.createElement("div");
    c.className = "mw-tl-plutitor";
    c.setAttribute("role", "group");
    c.setAttribute("aria-label", tx("telecomanda_titlu"));
    var bara = document.createElement("div");
    bara.className = "mw-tl-bara";
    bara.title = tx("muta");
    bara.innerHTML = IC_MANER;
    var titlu = document.createElement("span");
    // hds-derulant: titlul care nu incape se deruleaza (stilul si scriptul cadrului paginii, cadru_web.py)
    titlu.className = "mw-titlu hds-derulant";
    titlu.textContent = tx("telecomanda");
    var inchide = document.createElement("button");
    inchide.type = "button";
    inchide.className = "mw-inchide";
    inchide.textContent = "×";
    inchide.title = tx("ascunde");
    inchide.setAttribute("aria-label", tx("ascunde"));
    bara.appendChild(titlu); bara.appendChild(inchide);
    c.appendChild(bara);
    inchide.addEventListener("click", function(){
      tl.loc.pornita = false; scrieLoc();
      if(tl.bifa){ tl.bifa.checked = false; }
      urmeazaEcranul();
    });
    bara.addEventListener("pointerdown", function(e){
      if(e.button || !tl.marime || (e.target.closest && e.target.closest("button"))){ return; }
      e.preventDefault();
      tl.trage = {id: e.pointerId, cx: e.clientX, cy: e.clientY, x: tl.marime.x, y: tl.marime.y};
      try { bara.setPointerCapture(e.pointerId); } catch(er) {}
      bara.classList.add("mw-trag");
    });
    bara.addEventListener("pointermove", function(e){
      var t = tl.trage, m = tl.marime;
      if(!t || t.id !== e.pointerId || !m){ return; }
      var x = Math.min(Math.max(0, t.x + e.clientX - t.cx), Math.max(0, m.W - m.ws));
      var y = Math.min(Math.max(0, t.y + e.clientY - t.cy), Math.max(0, m.H - m.hs));
      // langa marginea din dreapta se lipeste (ca telecomanda emulatorului, cu magnet)
      var lipita = (m.W - m.ws - MARGINE) - x < PRAG_LIPIRE;
      if(lipita){ x = Math.max(0, m.W - m.ws - MARGINE); }
      t.lipita = lipita; t.xNou = x; t.yNou = y;
      aseaza(x, y, m.s);
    });
    function gata(e){
      var t = tl.trage, m = tl.marime;
      if(!t || t.id !== e.pointerId){ return; }
      tl.trage = null;
      bara.classList.remove("mw-trag");
      if(t.xNou === undefined || !m){ return; }
      tl.loc.dreapta = !!t.lipita;
      tl.loc.x = m.W - m.ws > 0 ? t.xNou / (m.W - m.ws) : 1;
      tl.loc.y = m.H - m.hs > 0 ? t.yNou / (m.H - m.hs) : 0.5;
      scrieLoc();
      pozitioneaza();
    }
    bara.addEventListener("pointerup", gata);
    bara.addEventListener("pointercancel", gata);
    tl.plutitor = c;
  }
  function aseaza(x, y, s){
    tl.plutitor.style.transform = "translate(" + Math.round(x) + "px," + Math.round(y) + "px) scale(" + s + ")";
    tl.marime.x = x; tl.marime.y = y;
  }
  // marimea (micsorata proportional cand nu incape in inaltime) si locul, in ecranul de acum
  function pozitioneaza(){
    if(!tl.arata || !tl.plutitor){ return; }
    var gazda = tl.player.e.radacina, c = tl.plutitor;
    var W = gazda.clientWidth, H = gazda.clientHeight;
    var w0 = c.offsetWidth, h0 = c.offsetHeight;
    if(!W || !H || !w0 || !h0){ return; }
    var s = Math.min(1, (H - 2 * MARGINE) / h0, (W * 0.6) / w0);
    s = Math.max(0.3, Math.round(s * 1000) / 1000);
    var ws = w0 * s, hs = h0 * s;
    var x = tl.loc.dreapta ? W - ws - MARGINE : (W - ws) * tl.loc.x;
    var y = (H - hs) * tl.loc.y;
    tl.marime = {W: W, H: H, ws: ws, hs: hs, s: s, x: 0, y: 0};
    aseaza(Math.min(Math.max(0, x), Math.max(0, W - ws)), Math.min(Math.max(0, y), Math.max(0, H - hs)), s);
  }
  function arata(){
    var el = document.getElementById("telecomanda");
    if(tl.arata || !el || !tl.player){ return; }
    if(!tl.plutitor){ construiestePlutitor(); }
    tl.inapoi = {parinte: el.parentNode, urmator: el.nextSibling};
    el.classList.add("mw-plutitoare");
    tl.plutitor.appendChild(el);
    tl.player.e.radacina.appendChild(tl.plutitor);
    tl.arata = true;
    pozitioneaza();
  }
  function ascunde(){
    if(!tl.arata){ return; }
    var el = document.getElementById("telecomanda");
    tl.arata = false;
    tl.trage = null;
    if(el){
      el.classList.remove("mw-plutitoare");
      var i = tl.inapoi;
      if(i && i.parinte){
        if(i.urmator && i.urmator.parentNode === i.parinte){ i.parinte.insertBefore(el, i.urmator); } else { i.parinte.appendChild(el); }
      }
    }
    if(tl.plutitor && tl.plutitor.parentNode){ tl.plutitor.parentNode.removeChild(tl.plutitor); }
  }
  function urmeazaEcranul(){
    if(!ePlin() || !tl.loc.pornita){ ascunde(); }
    else if(tl.arata){ pozitioneaza(); }
    else { arata(); }
  }
  function telecomandaInPlayer(p){
    var el = document.getElementById("telecomanda");
    if(!el || !p.e.comutator || !p.e.comutator.parentNode || tl.player){ return; }
    tl.player = p;
    tl.loc = citesteLoc();
    var et = document.createElement("label");
    et.className = "hp-comutator mw-comutator-tl";
    et.title = tx("telecomanda_titlu");
    var bifa = document.createElement("input");
    bifa.type = "checkbox";
    bifa.checked = tl.loc.pornita;
    var text = document.createElement("span");
    text.className = "hp-text";
    text.textContent = tx("telecomanda");
    et.appendChild(bifa);
    et.insertAdjacentHTML("beforeend", IC_TELECOMANDA);
    et.appendChild(text);
    p.e.comutator.parentNode.insertBefore(et, p.e.comutator.nextSibling);
    tl.bifa = bifa;
    bifa.addEventListener("change", function(){
      tl.loc.pornita = bifa.checked;
      scrieLoc();
      urmeazaEcranul();
    });
    ["fullscreenchange", "webkitfullscreenchange"].forEach(function(ev){ document.addEventListener(ev, urmeazaEcranul); });
    // ecranul intreg facut din CSS (unde browserul nu-l are, de pilda pe iPhone): clasa hp-plin-css a playerului
    if(window.MutationObserver){
      new MutationObserver(function(){ if(ePlin() !== tl.arata){ urmeazaEcranul(); } }).observe(p.e.radacina, {attributes: true, attributeFilter: ["class"]});
    }
    window.addEventListener("resize", function(){ if(tl.arata){ pozitioneaza(); } });
    // Compact <-> Toate tastele schimba inaltimea: marimea si locul se refac
    if(window.ResizeObserver){
      new ResizeObserver(function(){ if(tl.arata && !tl.trage){ pozitioneaza(); } }).observe(el);
    } else {
      Array.prototype.forEach.call(el.querySelectorAll(".tl-mod"), function(b){
        b.addEventListener("click", function(){ setTimeout(pozitioneaza, 0); });
      });
    }
  }

  window.HDS_MOUSE = {
    // pentru probe: socotelile fara DOM si starea telecomenzii
    procente: procente,
    dreptunghiCaptura: dreptunghiCaptura,
    pasiRotita: pasiRotita,
    tl: tl,
    caseta: caseta,
    casetaActiva: casetaActiva,
    TEXTE: TEXTE,
    tx: tx
  };
  window.HDS_MOUSE_PLAYER = legaLive;
  stilPus();
  legaCaseta();
  legaCaptura();
  if(window.live && window.live.player){ legaLive(window.live.player); }
  setInterval(actualizeaza, 1000);
})();
