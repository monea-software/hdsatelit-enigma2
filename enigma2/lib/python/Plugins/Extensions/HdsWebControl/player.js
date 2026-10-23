/* Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * player.js: playerul comun al interfetei web (panoul, pagina /tv, dialogul "Vezi live" din /canale). Servit de
 * tv_web.py la /tv/player.js; foloseste mpegts.js (/tv/mpegts.js, Apache-2.0) pentru imagine.
 *
 * Canalele cu imagine MPEG-2 / MPEG-1 (pe care browserele nu o redau) merg prin playerul wasm (/tv/hds-player.js,
 * window.HdsPlayerWasm: decodorul FFmpeg in WebAssembly, imaginea pe un al doilea <canvas>, sunetul cu Web Audio), pe
 * acelasi /api/tv-flux; restul, prin mpegts.js si elementul <video>. Butoanele (redare, sunet, volum, ecran intreg) si
 * stratul receptorului merg la fel cu amandoua: _media() da elementul <video> sau playerul wasm, care are aceleasi
 * proprietati (paused, muted, volume, play(), pause()). Pagina trimite wasm=1 cand browserul are WebAssembly, WebGL si
 * Worker; un canal la care formatul nu se stia trece singur pe playerul wasm cand fluxul arata MPEG-2.
 * Sunetul AC-3 al canalelor H.264 / HEVC, in browserele care nu il redau singure (Chrome, Edge, Firefox): il
 * decodeaza pagina, cu acelasi decodor wasm, si il da lui MediaSource ca FLAC (/tv/hds-sunet.js, convertorul trecut
 * lui mpegts.js prin config.hdsSunetAc3); pagina trimite atunci ac3=1, ca receptorul sa lase AC-3 in PMT.
 *
 * Ce face: imaginea live a unui canal (transmisia din HdsTransmisie, /api/tv-flux) si PESTE ea stratul grafic al
 * receptorului (meniurile, bara de informatii, subtitrarea, ghidul: /api/tv-osd, BGRA brut comprimat, desenat pe un
 * canvas de aceeasi marime), ca pe televizor. Butoanele stau SUB imagine (redare, sunet, pista audio, subtitrarea,
 * afisajul receptorului, ecran intreg, oprire); pe ecran intreg intra tot playerul (imaginea, stratul si bara), iar
 * bara apare la miscarea mouse-ului sau la atingere si se ascunde singura. Designul barei: fisa Stitch "Live TV Player
 * Card HD Satelit" (proiectul HD Satelit - interfata web receptor), geometria e a noastra.
 *
 * Stratul e al TELEVIZORULUI: pe canalul de pe televizor e pornit implicit; pe alt canal e oprit implicit (ar arata
 * meniurile altui canal). Imaginea din browser vine cu 1-3 s in urma televizorului; cadrele stratului se arata cu
 * aceeasi intarziere (cat are playerul in tampon), ca subtitrarea sa cada pe imagine.
 *
 * FEREASTRA IMAGINII: unele ecrane ale televizorului micsoreaza imaginea canalului intr-o fereastra (lista de canale,
 * HbbTV). Raspunsul stratului (/api/tv-osd, si pe 304) are antetul x-hds-video cu fereastra de acum ("x,y,l,h" in
 * procente din ecran, din /proc/stb/vmpeg/0/dst_*). Cat e bifat "Afisajul receptorului", imaginea din browser (<video>
 * sau canvas-ul playerului wasm) se pune in acelasi loc, cu o trecere de 0,2 s, iar in jur ramane negrul ecranului;
 * fereastra trece prin aceeasi coada ca stratul (aceeasi intarziere), deci lista si imaginea micsorata apar odata, ca
 * pe televizor. Fara bifa imaginea ramane pe tot cadrul: fereastra are rost numai cu ecranul care o inconjoara (fara el
 * ar fi o imagine mica intr-un chenar negru), iar fereastra e a televizorului, nu a canalului din browser.
 *
 * URMEAZA TELEVIZORUL: porneste("") (caseta din panou, "Pornește canalul de pe televizor" din /tv) nu leaga imaginea
 * de un canal, ci de ce merge pe televizor; la fel "Vezi live" pe canalul de pe televizor (urmeazaPeTv) si dupa ce
 * televizorul a trecut pe canalul ales (mutaTv). O cerere lunga (/api/tv-urmeaza) primeste raspuns cand televizorul
 * trece pe alt canal (receptorul il afla la inceputul zap-ului, din orice parte vine: telecomanda, panoul, ghidul),
 * intra sau iese din standby. Atunci pagina arata semnul "Se schimbă canalul..." cu numele canalului si porneste singura
 * canalul de ACUM al televizorului (urmeaza=1: il alege receptorul, nu pagina). Sesiunea veche nu se opreste din pagina:
 * pe aceeasi frecventa receptorul porneste intai inregistrarea noua si o opreste apoi pe cea veche (fara pauza nici
 * spre un canal criptat), iar pe alta frecventa zap-ul a eliberat deja tunerul (prioritatea televizorului). Tastele
 * telecomenzii din panou care schimba canalul (tastaTelecomanda, chemata INAINTE sa plece tasta) opresc pe loc fluxul
 * din browser si arata semnul; dupa raspunsul tastei (tastaTrimisa) starea spune si ea canalul nou. "Pornește din nou"
 * si reincercarile pornesc canalul de acum al televizorului, nu pe cel vechi.
 *
 * Ferestrele: fiecare player are un id (antetul X-HDS-Fereastra). Daca alta fereastra a acestui browser se uita, nu se
 * ia transmisia pe tacute: playerul intreaba ("O preiei aici?"); fereastra din care a fost preluata arata motivul.
 *
 * Erorile de decodare (o imagine pe care browserul n-o poate decoda): o singura reconectare singura, apoi un text scurt
 * pentru om; detaliul tehnic sta sub "Detalii" si in consola browserului.
 *
 * Toate textele de ecran stau in TEXTE (romana, cu cheie); tv_web.py pune la servire, in locul semnului de dupa
 * TRADUSE, traducerile lor in limba meniurilor receptorului (tv_web.TEXTE_PLAYER, aceleasi chei). In cod textele se
 * iau numai prin tx(cheie) si txs(cheie, valoare) (cu %s), niciodata scrise direct.
 *
 * PASII DECRIPTARII: cat pagina asteapta un canal criptat ("Se decriptează..." sau pauza dintre pornirile criptate), in
 * josul imaginii stau randurile vii ale televizorului (/api/pasi-decriptare, Components/HdsPasiDecriptare.py: cererea
 * catre modulul de acces, raspunsurile si timpul lor, imaginea decriptata), cerute o data pe secunda, numai cand sunt
 * ale canalului acestui player (aceeasi referinta) si numai cu setarea lor pornita pe receptor. Textele vin traduse de la
 * receptor. Imaginea venita, oprirea sau alta pornire le ascund.
 *
 * Folosire: var p = HdsPlayer.creeaza(elementGazda, {csrf: CFG.csrf, m3u: true, laOprire: function(){}});
 *           p.porneste(ref, nume)   (ref "" = canalul de pe televizor, urmarit);  p.opreste();  p.distruge();
 * Optiuni: urmeazaTv (implicit da: porneste("") urmeaza televizorul), urmeazaPeTv (un canal care e pe televizor trece
 * in modul "urmeaza televizorul"), mutaTv(ref) -> Promise({result, message}) (televizorul trece pe un canal pe care
 * transmisia nu-l poate lua altfel), laCanal(nume, ref) (canalul urmarit s-a schimbat), laMotiv, laOprire, textOprire.
 */
(function(){
  "use strict";
  if(window.HdsPlayer){ return; }

  // textele de ecran (romana); traducerile vin de la receptor, la servire (tv_web.TEXTE_PLAYER)
  var TEXTE = {
    schimba: "Se schimbă canalul...",
    muta: "Televizorul trece pe %s...",
    antena: "Antena se rotește...",
    decriptare: "Se decriptează...",
    nedecriptat: "Canalul e criptat și receptorul nu-l poate decripta acum (fără card sau fără drepturi pentru el).",
    decodare: "Browserul nu poate reda imaginea acestui canal. Încearcă din nou.",
    decodare_m3u: "Browserul nu poate reda imaginea acestui canal. Încearcă din nou sau deschide-l într-un player din casă cu playlistul de mai jos.",
    sunet: "Browserul nu poate reda sunetul acestui canal. Încearcă din nou.",
    sunet_m3u: "Browserul nu poate reda sunetul acestui canal. Încearcă din nou sau deschide-l într-un player din casă cu playlistul de mai jos.",
    hevc: "Acest browser nu poate decoda imaginea HEVC (H.265) a acestui canal, de pildă 4K pe 10 biți. Încearcă alt browser sau un player din casă.",
    hevc_m3u: "Acest browser nu poate decoda imaginea HEVC (H.265) a acestui canal, de pildă 4K pe 10 biți. Deschide-l într-un player din casă cu playlistul de mai jos.",
    detalii: "Detalii",
    din_nou: "Pornește din nou",
    incearca: "Încearcă din nou",
    nu_a_trecut: "Televizorul nu a trecut pe acest canal.",
    standby: "Receptorul e în standby.",
    descriere_audio: "descriere audio",
    vorbire_clara: "vorbire clară",
    imaginea_merge: "Imaginea merge.",
    fara_imagine: "Canalul nu trimite imagine acum.",
    fara_pmt: "Canalul nu trimite descrierea pistelor (imagine și sunet), deci browserul nu știe ce să redea. Încearcă din nou.",
    // numele limbilor pistelor de sunet (LIMBI: codul din PMT -> cheia)
    l_deu: "Germană",
    l_eng: "Engleză",
    l_ron: "Română",
    l_fra: "Franceză",
    l_ita: "Italiană",
    l_spa: "Spaniolă",
    l_hun: "Maghiară",
    l_pol: "Poloneză",
    l_ces: "Cehă",
    l_tur: "Turcă",
    l_rus: "Rusă",
    l_ukr: "Ucraineană",
    l_nld: "Olandeză",
    l_por: "Portugheză",
    l_bul: "Bulgară",
    l_srp: "Sârbă",
    l_hrv: "Croată",
    l_ell: "Greacă",
    l_qaa: "Limba originală",
    l_mis: "Altă limbă",
    l_und: "Nedefinită",
    l_nar: "Descriere audio",
    // scripturile care nu s-au incarcat
    e_mpegts: "Biblioteca de redare nu s-a încărcat de pe receptor.",
    e_wasm: "Decodorul MPEG-2 nu s-a încărcat de pe receptor.",
    e_sunet: "Decodorul de sunet nu s-a încărcat de pe receptor.",
    // pistele si subtitrarea
    sunet_pista: "Sunet: %s",
    pista_nr: "pista %s",
    nu_merge: "nu merge în browser",
    sunet_canal: "Sunet: pista canalului",
    sub_numai_tv: "Subtitrare: numai pe canalul televizorului",
    sub_fara: "Subtitrare: -",
    sub_oprita: "Subtitrare: oprită",
    sub_aleasa: "Subtitrare: %s",
    // bara de sub imagine (butoanele, titlurile si numele lor pentru cititoarele de ecran)
    imaginea_canalului: "Imaginea canalului",
    pasi: "Pașii decriptării",
    comenzi: "Comenzile imaginii",
    volum: "Volumul",
    pista_audio: "Pista audio",
    pista_titlu: "Pista audio a imaginii din browser",
    subtitrarea: "Subtitrarea",
    sub_titlu: "Subtitrarea o desenează receptorul: se schimbă și pe televizor",
    afisaj: "Afișajul receptorului",
    afisaj_titlu: "Meniurile, bara de informații, subtitrarea și ghidul receptorului, peste imagine",
    afisaj_alt: "Afișajul e al canalului de pe televizor, nu al acestui canal",
    opreste: "Oprește",
    reda: "Redă",
    pauza: "Pune pauză",
    sunet_pornit: "Pornește sunetul",
    sunet_oprit: "Oprește sunetul",
    iesire: "Ieșire",
    ecran_intreg: "Ecran întreg",
    iesire_ecran: "Ieșire din ecranul întreg",
    m3u: "Descarcă playlist (M3U)",
    m3u_nota: "pentru un player din casă; acolo merg toate pistele de sunet",
    // mesajele pornirii si ale transmisiei
    se_porneste: "Se pornește...",
    acum: "Acum: %s",
    deconectat: "Browserul nu mai e conectat la receptor.",
    raspuns_http: "Receptorul a răspuns neașteptat (HTTP %s).",
    nu_raspunde: "Receptorul nu răspunde.",
    jeton: "Imaginea live merge numai cu browserul conectat: deschide pagina fără cheia din adresă.",
    fara_mse: "Acest browser nu poate reda fluxul (îi lipsește MediaSource). Încearcă Chrome, Edge, Firefox sau Safari nou.",
    oprita_setari: "Transmisia în browser e oprită din setări (Rețea și internet, Transmisie în rețea).",
    tv_gol: "Pe televizor nu merge acum niciun canal.",
    neverificat: "Canalul nu se poate verifica.",
    nu_merge_acum: "Canalul nu se poate reda acum în browser.",
    nu_a_pornit: "Imaginea live nu a pornit.",
    preia_aici: "Preia aici",
    apasa_reda: "Apasă ca să pornească redarea.",
    fara_sunet: "Browserul a pornit imaginea fără sunet. Apasă ca să pornească și sunetul.",
    oprita: "Transmisia s-a oprit.",
    preluata: "Transmisia a fost preluată de altă fereastră.",
    preia_inapoi: "Preia înapoi",
    mpeg2: "Imaginea acestui canal e MPEG-2: o decodează browserul.",
    // erorile fluxului (cauza pe scurt; detaliul tehnic sta sub Detalii)
    nu_transmite: "Receptorul nu mai transmite spre acest browser.",
    refuzat: "Receptorul a refuzat fluxul (HTTP %s).",
    flux_oprit: "Fluxul s-a oprit de la receptor.",
    legatura: "Legătura cu receptorul s-a întrerupt.",
    wasm_oprit: "Decodorul MPEG-2 din browser nu a pornit.",
    format: "Browserul nu cunoaște formatul imaginii sau al sunetului.",
    forma: "Fluxul are o formă pe care playerul nu o înțelege.",
    cod4: "Browserul nu a putut deschide imaginea (n-a primit date pe care să le înțeleagă).",
    redare_browser: "Redarea s-a oprit în browser.",
    redare: "Redarea s-a oprit.",
    // alegerile din bara si playlistul
    pista_rea: "Pista nu s-a putut alege.",
    sub_schimbata: "Subtitrarea s-a schimbat (și pe televizor).",
    sub_neschimbata: "Subtitrarea nu s-a putut schimba.",
    alege_canal: "Alege întâi un canal.",
    extern: "Imaginea din pagină s-a oprit, ca să se poată deschide în playerul extern.",
    reia_aici: "Reia aici",
    m3u_gata: "Playlistul s-a descărcat (%s). Deschide-l într-un player din casă.",
    m3u_rau: "Playlistul nu s-a putut descărca.",
    m3u_http: "Playlistul nu s-a putut face (HTTP %s)."
  };
  var TRADUSE = /*__TEXTE__*/null;
  function tx(cheie){
    return (TRADUSE && TRADUSE[cheie]) || TEXTE[cheie] || cheie;
  }
  // textul cu %s inlocuit de valoare (o functie, ca $& sau $1 dintr-un nume de canal sa ramana cum sunt)
  function txs(cheie, valoare){
    return tx(cheie).replace("%s", function(){ return String(valoare); });
  }

  // tastele telecomenzii care schimba canalul: CH+, CH-, canalul de dinainte (<) si urmatorul (>)
  var TASTE_ZAP = [402, 403, 412, 407];
  var SEMN_TASTA_MS = 2500;      // cat ramane semnul unei taste de zap fara ca televizorul sa schimbe canalul
  var MUTARE_MS = 8000;          // cat se asteapta televizorul sa ajunga pe canalul ales (mutaTv)
  var REPORNIRI_MAX = 2;         // reporniri singure pe acelasi canal al televizorului, intr-un minut
  var DECODARE_MS = 60000;       // dupa atat, o noua eroare de decodare are iar dreptul la o reconectare singura
  // PAZA CADRELOR (_cadrePas): fara niciun cadru nou atata timp, pagina spune ce se intampla. Receptorul opreste singur o
  // sesiune fara date dupa 15 s (HdsTransmisie.FARA_DATE_S, "Canalul nu mai trimite date.") si pagina ii citeste starea
  // la 3 s: dupa 15 + 3 s fara cadre, datele vin, dar imaginea nu
  var FARA_CADRE_MS = (15 + 3) * 1000;
  // "Imaginea merge." pleaca din randul de stare dupa atat fara cadru nou: o imagine vie are 25-50 de cadre pe secunda
  // (proba de noapte 13-14.10: 360-899 de cadre in 15 s), deci 2 s fara niciunul inseamna ca s-a oprit
  var CADRE_OPRITE_MS = 2000;
  // PMT-ul fluxului (a_mea.pmt_citit) nu vine: receptorul face unul din fluxuri dupa ~3-6 s de flux (HdsTransmisie,
  // PMT-UL LIPSA); daca nici dupa atat de la pornirea imaginii pagina nu stie ce sa redea, o spune (proba din 14.10:
  // EBS+HD a stat 60 s fara niciun mesaj)
  var FARA_PMT_MS = 12000;
  var PASI_MS = 1000;            // cat de des se cer pasii decriptarii cat pagina asteapta un canal criptat
  var PASI_VAZUTI = 6;           // cate randuri se vad peste imagine (primul, cererea, si ultimele)
  var ASCULTARE_MS = 35000;      // cererea lunga raspunde cel tarziu dupa 25 s (tv_web.URMEAZA_S); fara raspuns, alta

  var STIL = [
    ".hp{position:relative;color:#dee1f9;font-size:.9rem;}",
    ".hp-ecran{position:relative;background:#000;border-radius:12px 12px 0 0;overflow:hidden;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;}",
    ".hp-cadru{position:relative;width:100%;aspect-ratio:16/9;max-height:100%;}",
    ".hp-cadru video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000;display:block;}",
    ".hp-cadru canvas{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;display:block;}",
    /* imaginea playerului wasm (MPEG-2): sub stratul receptorului, primeste apasarea ca <video> */
    ".hp-cadru canvas.hp-imagine{pointer-events:auto;background:#000;}",
    /* imaginea in fereastra televizorului (_fereastra: left/top/width/height in procente), cu o trecere scurta */
    ".hp-cadru video,.hp-cadru canvas.hp-imagine{transition:left .2s ease-out,top .2s ease-out,width .2s ease-out,height .2s ease-out;}",
    "@media (prefers-reduced-motion:reduce){.hp-cadru video,.hp-cadru canvas.hp-imagine{transition:none;}}",
    ".hp-mesaj{position:absolute;inset:0;display:flex;flex-direction:column;gap:12px;align-items:center;justify-content:center;text-align:center;padding:18px;background:rgba(8,13,29,.72);line-height:1.45;font-size:.95rem;}",
    ".hp-mesaj button{min-height:44px;padding:8px 16px;border-radius:8px;border:1px solid rgba(255,255,255,.15);background:#374ea1;color:#f2f4f8;font:inherit;cursor:pointer;}",
    /* semnul trecerii pe alt canal (urmeaza televizorul): peste imagine, ca bara de zap a televizorului; nu prinde clicuri */
    ".hp-semn{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);box-sizing:border-box;max-width:calc(100% - 24px);display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 20px;border-radius:12px;background:rgba(8,13,29,.86);border:1px solid rgba(255,255,255,.12);box-shadow:0 6px 24px rgba(0,0,0,.45);text-align:center;line-height:1.35;pointer-events:none;}",
    ".hp-semn i{width:20px;height:20px;border-radius:50%;border:2px solid rgba(255,255,255,.22);border-top-color:#38bdf8;animation:hp-roata .8s linear infinite;flex:none;}",
    ".hp-semn b{font-size:1rem;font-weight:600;overflow-wrap:anywhere;}",
    ".hp-semn span{font-size:.85rem;color:#c9d2e3;overflow-wrap:anywhere;}",
    "@keyframes hp-roata{to{transform:rotate(360deg);}}",
    "@media (prefers-reduced-motion:reduce){.hp-semn i{animation:none;border-top-color:rgba(255,255,255,.22);}}",
    "@media (max-width:420px){.hp-semn{padding:8px 12px;gap:4px;}.hp-semn b{font-size:.9rem;}.hp-semn span{font-size:.78rem;}}",
    ".hp-ascuns{display:none !important;}",
    /* pasii decriptarii: in josul imaginii, cat se asteapta un canal criptat; nu prind clicuri */
    ".hp-pasi{position:absolute;left:10px;right:10px;bottom:10px;margin:0;padding:6px 10px;list-style:none;border-radius:8px;background:rgba(8,13,29,.80);border:1px solid rgba(255,255,255,.10);font-size:.78rem;line-height:1.4;color:#c9d2e3;text-align:left;pointer-events:none;max-height:46%;overflow:hidden;}",
    ".hp-pasi li{white-space:nowrap;overflow:hidden;}",
    ".hp-pasi b{display:inline-block;min-width:4.4em;font-weight:600;color:#9fb4ff;font-variant-numeric:tabular-nums;}",
    "@media (max-width:420px){.hp-pasi{font-size:.7rem;padding:4px 8px;left:6px;right:6px;bottom:6px;}}",
    ".hp-bara{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-height:56px;padding:6px 8px;background:#0f172a;border:1px solid #1e293b;border-top:0;border-radius:0 0 12px 12px;}",
    ".hp-bara button,.hp-bara label.hp-comutator,.hp-bara select{min-height:44px;min-width:44px;border-radius:8px;border:1px solid #1e293b;background:#131e36;color:#dee1f9;font:inherit;font-size:.82rem;cursor:pointer;}",
    ".hp-bara button{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:0 10px;}",
    ".hp-bara button:hover,.hp-bara select:hover,.hp-bara label.hp-comutator:hover{background:#182442;}",
    ".hp-bara button:focus-visible,.hp-bara select:focus-visible,.hp-bara input:focus-visible{outline:2px solid #38bdf8;outline-offset:1px;}",
    ".hp-bara button:disabled,.hp-bara select:disabled{opacity:.45;cursor:default;}",
    ".hp-bara svg{width:22px;height:22px;fill:currentColor;flex:none;}",
    ".hp-bara .hp-sunet{display:inline-flex;align-items:center;gap:4px;padding:0 6px 0 0;border:1px solid #1e293b;border-radius:8px;background:rgba(19,30,54,.6);}",
    ".hp-bara .hp-sunet button{border:0;background:transparent;}",
    ".hp-bara input[type=range]{width:84px;accent-color:#38bdf8;}",
    ".hp-bara select{padding:0 8px;max-width:190px;}",
    ".hp-bara label.hp-comutator{display:inline-flex;align-items:center;gap:8px;padding:0 10px;}",
    ".hp-bara label.hp-comutator input{width:18px;height:18px;accent-color:#374ea1;margin:0;}",
    ".hp-bara .hp-spatiu{flex:1 1 0;}",
    ".hp-bara .hp-oprire{color:#ff6b5e;}",
    ".hp-stare{margin:8px 2px 0;font-size:.82rem;color:#aeb9cc;line-height:1.4;min-height:1.2em;}",
    ".hp-stare.hp-eroare{color:#ffb4ab;}",
    /* detaliul tehnic al unei erori: mic, inchis implicit */
    ".hp-detalii{margin:2px 2px 0;font-size:.75rem;color:#8b96aa;}",
    ".hp-detalii summary{cursor:pointer;min-height:24px;line-height:24px;}",
    ".hp-detalii code{display:block;white-space:pre-wrap;overflow-wrap:anywhere;font-size:.72rem;margin:2px 0 0;color:#aeb9cc;}",
    ".hp-extra{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:10px;}",
    ".hp-extra button{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid rgba(255,255,255,.1);background:#161f3b;color:#c9d2e3;font:inherit;cursor:pointer;}",
    /* iconita butonului M3U: marimea si culoarea textului, ca in bara (fara ele svg-ul ia toata latimea, negru) */
    ".hp-extra svg{width:20px;height:20px;fill:currentColor;flex:none;}",
    ".hp-extra small{color:#aeb9cc;font-size:.8rem;}",
    "@media (max-width:560px){.hp-bara .hp-text{display:none;} .hp-bara input[type=range]{display:none;} .hp-bara select{max-width:130px;}}",
    /* ecran intreg: tot playerul; bara pluteste jos peste un degrade si se ascunde singura */
    ".hp:fullscreen,.hp.hp-plin-css{background:#000;width:100%;height:100%;}",
    ".hp.hp-plin-css{position:fixed;inset:0;z-index:2147483000;}",
    ".hp:fullscreen .hp-ecran,.hp.hp-plin-css .hp-ecran{aspect-ratio:auto;height:100%;border-radius:0;}",
    ".hp:fullscreen .hp-cadru,.hp.hp-plin-css .hp-cadru{width:min(100%,calc(100vh * 16 / 9));}",
    ".hp:fullscreen .hp-bara,.hp.hp-plin-css .hp-bara{position:absolute;left:0;right:0;bottom:0;border:0;border-radius:0;padding:18px 14px 12px;background:linear-gradient(rgba(0,0,0,0),rgba(0,0,0,.85));transition:opacity .25s;}",
    ".hp:fullscreen .hp-stare,.hp:fullscreen .hp-detalii,.hp:fullscreen .hp-extra,.hp.hp-plin-css .hp-stare,.hp.hp-plin-css .hp-detalii,.hp.hp-plin-css .hp-extra{display:none;}",
    ".hp.hp-bara-ascunsa .hp-bara{opacity:0;pointer-events:none;}",
    ".hp.hp-bara-ascunsa{cursor:none;}"
  ].join("\n");

  var IC = {
    pauza: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>',
    reda: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>',
    sunet: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4z"/></svg>',
    mut: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 9v6h4l5 5V4L7 9H3zm18.6 1.4-1.4-1.4L18 11.2 15.8 9l-1.4 1.4 2.2 2.2-2.2 2.2 1.4 1.4 2.2-2.2 2.2 2.2 1.4-1.4-2.2-2.2z"/></svg>',
    plin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 14H5v5h5v-2H7zm-2-4h2V7h3V5H5zm12 7h-3v2h5v-5h-2zM14 5v2h3v3h2V5z"/></svg>',
    iesi: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 16h3v3h2v-5H5zm3-8H5v2h5V5H8zm6 11h2v-3h3v-2h-5zm2-11V5h-2v5h5V8z"/></svg>',
    stop: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h12v12H6z"/></svg>',
    descarca: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 20h14v-2H5zM19 9h-4V3H9v6H5l7 7z"/></svg>'
  };

  // codul limbii din PMT -> cheia numelui ei in TEXTE
  var LIMBI = {deu: "l_deu", ger: "l_deu", eng: "l_eng", ron: "l_ron", rum: "l_ron", fra: "l_fra", fre: "l_fra",
    ita: "l_ita", spa: "l_spa", hun: "l_hun", pol: "l_pol", ces: "l_ces", cze: "l_ces", tur: "l_tur",
    rus: "l_rus", ukr: "l_ukr", nld: "l_nld", dut: "l_nld", por: "l_por", bul: "l_bul", srp: "l_srp",
    hrv: "l_hrv", ell: "l_ell", gre: "l_ell", qaa: "l_qaa", mis: "l_mis", und: "l_und", nar: "l_nar", qad: "l_nar"};

  function stilPus(){
    if(document.getElementById("hdsPlayerStil")){ return; }
    var s = document.createElement("style");
    s.id = "hdsPlayerStil";
    s.textContent = STIL;
    document.head.appendChild(s);
  }

  function el(tip, clasa, text){
    var e = document.createElement(tip);
    if(clasa){ e.className = clasa; }
    if(text){ e.textContent = text; }
    return e;
  }

  // referinta unui canal ca cheie de comparat: primele 10 campuri, litere mari (ca refCurata pe receptor); altceva (o
  // cale de fisier) ramane cum e
  function refCheie(r){
    var p = String(r || "").split(":");
    if(p.length < 10 || p[0] !== "1"){ return String(r || ""); }
    return p.slice(0, 10).join(":").toUpperCase() + ":";
  }

  // fereastra imaginii pe televizor, din antetul x-hds-video al stratului ("x,y,l,h" in procente din ecran): {x, y, l, h}
  // in procente, null = ecranul intreg; undefined = antetul lipseste (receptor mai vechi) sau nu se intelege: nimic nou
  function fereastraDin(antet){
    if(antet === null || antet === undefined){ return undefined; }
    var p = String(antet).split(",");
    if(p.length !== 4){ return undefined; }
    var n = p.map(function(x){ x = x.trim(); return /^\d{1,3}(\.\d+)?$/.test(x) ? parseFloat(x) : NaN; });
    if(n.some(isNaN)){ return undefined; }
    var x = Math.min(n[0], 100), y = Math.min(n[1], 100);
    var l = Math.min(n[2], 100 - x), h = Math.min(n[3], 100 - y);
    if(l <= 0 || h <= 0 || (x <= 0 && y <= 0 && l >= 100 && h >= 100)){ return null; }
    return {x: x, y: y, l: l, h: h};
  }
  function cheieFereastra(f){ return f ? [f.x, f.y, f.l, f.h].join(",") : "plin"; }

  function idFereastra(){
    // un id pe fila (sessionStorage), ca reincarcarea paginii sa ramana aceeasi fereastra
    var id = "";
    try { id = sessionStorage.getItem("hdsFereastra") || ""; } catch(e) {}
    if(!/^[A-Za-z0-9]{8,32}$/.test(id)){
      var a = new Uint8Array(9);
      (window.crypto || window.msCrypto).getRandomValues(a);
      id = Array.prototype.map.call(a, function(b){ return ("0" + b.toString(16)).slice(-2); }).join("");
      try { sessionStorage.setItem("hdsFereastra", id); } catch(e) {}
    }
    return id;
  }

  function citesteLocal(cheie, implicit){
    try { var v = localStorage.getItem(cheie); return v === null ? implicit : v; } catch(e) { return implicit; }
  }
  function scrieLocal(cheie, v){ try { localStorage.setItem(cheie, v); } catch(e) {} }

  function suporta(tip){
    var MS = window.ManagedMediaSource || window.MediaSource;
    try { return !!(MS && MS.isTypeSupported && MS.isTypeSupported(tip)); } catch(e) { return false; }
  }
  // playerul wasm (MPEG-2) cere WebAssembly, WebGL, un Worker si fluxul citit pe bucati (fetch cu ReadableStream)
  function suportaWasm(){
    try {
      if(typeof WebAssembly !== "object" || typeof WebAssembly.instantiate !== "function" || typeof Worker !== "function"){ return false; }
      if(typeof ReadableStream !== "function" || typeof fetch !== "function"){ return false; }
      var c = document.createElement("canvas");
      var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if(!gl){ return false; }
      var pierde = gl.getExtension("WEBGL_lose_context");
      if(pierde){ pierde.loseContext(); }
      return true;
    } catch(e) { return false; }
  }
  var POATE = null;
  function poate(){
    if(!POATE){
      var nativ = suporta('audio/mp4; codecs="ac-3"'), wasm = suportaWasm();
      POATE = {
        hevc: suporta('video/mp4; codecs="hvc1.1.6.L93.B0"') || suporta('video/mp4; codecs="hev1.1.6.L93.B0"'),
        // AC-3: nativ (MediaSource il ia), sau decodat in pagina (hds-sunet.js: decodorul wasm, apoi FLAC in MediaSource)
        ac3nativ: nativ,
        ac3wasm: !nativ && wasm && suporta('audio/mp4; codecs="flac"'),
        wasm: wasm
      };
      POATE.ac3 = POATE.ac3nativ || POATE.ac3wasm;
    }
    return POATE;
  }
  function imagineWasm(video){ return video === "mpeg2" || video === "mpeg1"; }
  // programul (sid-ul) canalului, din referinta lui: al patrulea camp, in hex ("1:0:19:157F:41F:..." -> 0x157F); 0 = nu
  // se stie. Playerul wasm il cauta in PAT: la inceputul fluxului pot trece inca PAT-ul si PMT-ul canalului de dinainte
  function programDinRef(ref){
    var c = String(ref || "").split(":");
    var n = c.length > 3 && /^[0-9a-fA-F]{1,4}$/.test(c[3]) ? parseInt(c[3], 16) : 0;
    return n > 0 ? n : 0;
  }

  function incarcaScript(cale, nume, eroare){
    return new Promise(function(da, nu){
      if(window[nume]){ da(); return; }
      var s = document.createElement("script");
      s.src = cale;
      s.onload = function(){ if(window[nume]){ da(); } else { nu(new Error(eroare)); } };
      s.onerror = function(){ nu(new Error(eroare)); };
      document.head.appendChild(s);
    });
  }
  function incarcaMpegts(){
    return incarcaScript("/tv/mpegts.js", "mpegts", tx("e_mpegts"));
  }
  function incarcaWasm(){
    return incarcaScript("/tv/hds-player.js", "HdsPlayerWasm", tx("e_wasm"));
  }
  // sunetul AC-3 decodat in pagina (hds-sunet.js): fara el, AC-3 ramane numai cu decodorul browserului
  function faraAc3Wasm(){
    var pt = poate();
    pt.ac3wasm = false;
    pt.ac3 = pt.ac3nativ;
  }
  function incarcaSunet(){
    if(!poate().ac3wasm){ return Promise.resolve(); }
    return incarcaScript("/tv/hds-sunet.js", "HdsSunetAc3", tx("e_sunet")).then(function(){
      if(!HdsSunetAc3.poate()){ faraAc3Wasm(); }
    }, function(){ faraAc3Wasm(); });
  }

  function numeLimba(cod){
    cod = (cod || "").toLowerCase();
    return LIMBI[cod] ? tx(LIMBI[cod]) : (cod ? cod.toUpperCase() : "");
  }
  // felul pistei din PMT (HdsTransmisie.RescrierePsi), scris ca pe televizor
  var FEL_SUNET = {AC3: "AC-3", "E-AC3": "E-AC-3"};
  // eticheta unei piste: limba, rolul (descriere audio, vorbire clara: din descriptorii PMT-ului) si felul
  function numePista(p){
    var rol = p.rol === "descriere" ? tx("descriere_audio") : (p.rol === "clar" ? tx("vorbire_clara") : "");
    return txs("sunet_pista", (numeLimba(p.limba) || txs("pista_nr", p.pid)) + (rol ? ", " + rol : "") + " (" +
      (FEL_SUNET[p.fel] || p.fel) + ")" + (p.merge ? "" : ", " + tx("nu_merge")));
  }

  function Player(gazda, o){
    stilPus();
    this.o = o || {};
    this.fereastra = idFereastra();
    this.ref = null;
    this.nume = "";
    this.jucator = null;
    this.felJucator = "";      // "mse" (mpegts.js + <video>) sau "wasm" (hds-player.js + canvas)
    this.cuWasm = false;       // canalul de acum are imagine MPEG-2 / MPEG-1 si browserul are playerul wasm
    this.sesiune = null;
    this.pornit = false;
    this.inLucru = false;
    this.peTv = false;
    this.urmeaza = false;      // modul "urmeaza televizorul"
    this.tv = null;            // ce merge pe televizor, stiut din ultimul raspuns: {ref, nume, standby}
    this.ceasStare = null;
    this.ceasStrat = null;
    this.ceasBara = null;
    this.etag = "";
    this.coada = [];
    this.ultimAfisat = 0;
    this.ultimaStare = null;
    this.distrus = false;
    this.reconectare = true;
    this.reconectari = [];
    this._fereastraArata = "";       // fereastra imaginii aratata acum (cheieFereastra)
    this._fereastraCoada = undefined; // ultima fereastra pusa in coada stratului
    this._construieste(gazda);
  }

  Player.prototype._construieste = function(gazda){
    var self = this;
    var r = el("div", "hp");
    r.tabIndex = -1;
    var ecran = el("div", "hp-ecran");
    var cadru = el("div", "hp-cadru");
    var video = document.createElement("video");
    video.playsInline = true;
    video.setAttribute("playsinline", "");
    // imaginea playerului wasm (canalele MPEG-2): intre <video> si stratul receptorului, ascunsa cat nu e folosita
    var imagine = document.createElement("canvas");
    imagine.className = "hp-imagine hp-ascuns";
    imagine.width = 960; imagine.height = 540;
    imagine.setAttribute("role", "img");
    imagine.setAttribute("aria-label", tx("imaginea_canalului"));
    var canvas = document.createElement("canvas");
    canvas.width = 960; canvas.height = 540;
    canvas.setAttribute("aria-hidden", "true");
    cadru.appendChild(video); cadru.appendChild(imagine); cadru.appendChild(canvas);
    var mesaj = el("div", "hp-mesaj hp-ascuns");
    mesaj.setAttribute("role", "status");
    // semnul trecerii pe alt canal: roata, titlul (ce se intampla) si numele canalului
    var semn = el("div", "hp-semn hp-ascuns");
    semn.setAttribute("role", "status");
    semn.setAttribute("aria-live", "polite");
    var semnTitlu = el("b"), semnSub = el("span");
    semn.appendChild(el("i")); semn.appendChild(semnTitlu); semn.appendChild(semnSub);
    // pasii decriptarii (PASII DECRIPTARII, sus): randurile vii ale televizorului cat se asteapta un canal criptat
    var pasi = el("ul", "hp-pasi hp-ascuns");
    pasi.setAttribute("aria-live", "polite");
    pasi.setAttribute("aria-label", tx("pasi"));
    ecran.appendChild(cadru); ecran.appendChild(mesaj); ecran.appendChild(semn); ecran.appendChild(pasi);
    r.appendChild(ecran);

    var bara = el("div", "hp-bara");
    bara.setAttribute("role", "toolbar");
    bara.setAttribute("aria-label", tx("comenzi"));
    var bReda = el("button"); bReda.type = "button";
    var cutieSunet = el("div", "hp-sunet");
    var bMut = el("button"); bMut.type = "button";
    var volum = document.createElement("input");
    volum.type = "range"; volum.min = "0"; volum.max = "100"; volum.value = citesteLocal("hdsVolum", "80");
    volum.setAttribute("aria-label", tx("volum"));
    cutieSunet.appendChild(bMut); cutieSunet.appendChild(volum);
    var selPista = document.createElement("select");
    selPista.setAttribute("aria-label", tx("pista_audio"));
    selPista.title = tx("pista_titlu");
    var selSub = document.createElement("select");
    selSub.setAttribute("aria-label", tx("subtitrarea"));
    selSub.title = tx("sub_titlu");
    var comutator = el("label", "hp-comutator");
    comutator.title = tx("afisaj_titlu");
    var bifa = document.createElement("input"); bifa.type = "checkbox";
    comutator.appendChild(bifa);
    comutator.appendChild(el("span", "hp-text", tx("afisaj")));
    var spatiu = el("span", "hp-spatiu");
    var bPlin = el("button"); bPlin.type = "button";
    var bStop = el("button", "hp-oprire"); bStop.type = "button";
    bStop.innerHTML = IC.stop;
    bStop.appendChild(el("span", "hp-text", self.o.textOprire || tx("opreste")));
    bStop.title = self.o.textOprire || tx("opreste");
    [bReda, cutieSunet, selPista, selSub, comutator, spatiu, bPlin, bStop].forEach(function(x){ bara.appendChild(x); });
    r.appendChild(bara);

    var stare = el("div", "hp-stare");
    stare.setAttribute("aria-live", "polite");
    r.appendChild(stare);
    // detaliul tehnic al ultimei erori (tipul, codul, mesajul browserului), ascuns sub "Detalii"
    var detalii = el("details", "hp-detalii hp-ascuns");
    detalii.appendChild(el("summary", "", tx("detalii")));
    var tehnic = el("code");
    detalii.appendChild(tehnic);
    r.appendChild(detalii);
    var extra = el("div", "hp-extra");
    if(self.o.m3u){
      var bM3u = el("button"); bM3u.type = "button";
      bM3u.innerHTML = IC.descarca;
      bM3u.appendChild(el("span", "", tx("m3u")));
      extra.appendChild(bM3u);
      extra.appendChild(el("small", "", tx("m3u_nota")));
      bM3u.addEventListener("click", function(){ self.descarcaM3u(); });
    }
    r.appendChild(extra);
    gazda.appendChild(r);

    this.e = {radacina: r, ecran: ecran, cadru: cadru, video: video, imagine: imagine, canvas: canvas, mesaj: mesaj, bara: bara, reda: bReda,
      mut: bMut, volum: volum, pista: selPista, sub: selSub, bifa: bifa, comutator: comutator, plin: bPlin, stop: bStop,
      stare: stare, detalii: detalii, tehnic: tehnic, extra: extra, semn: semn, semnTitlu: semnTitlu, semnSub: semnSub,
      pasi: pasi};
    this.ctx = canvas.getContext("2d");
    video.volume = Math.max(0, Math.min(1, parseInt(volum.value, 10) / 100));

    bReda.addEventListener("click", function(){ self.comutaRedarea(); });
    video.addEventListener("play", function(){ self._butoane(); });
    video.addEventListener("pause", function(){ self._butoane(); });
    video.addEventListener("volumechange", function(){ self._butoane(); });
    video.addEventListener("click", function(){ if(video.paused){ self.comutaRedarea(); } });
    imagine.addEventListener("click", function(){ if(self._media().paused){ self.comutaRedarea(); } });
    video.addEventListener("error", function(){
      if(self.jucator && self.felJucator === "mse" && video.error){ self._eroareFlux("MediaError", "video", {code: video.error.code, msg: video.error.message}); }
    });
    // sunetul si volumul: pe imaginea de acum (<video> sau playerul wasm); <video> tine minte alegerea pentru amandoua
    bMut.addEventListener("click", function(){
      var m = self._media();
      m.muted = !m.muted;
      video.muted = m.muted;
    });
    volum.addEventListener("input", function(){
      var m = self._media();
      m.volume = parseInt(volum.value, 10) / 100;
      if(m.volume > 0){ m.muted = false; }
      video.volume = m.volume; video.muted = m.muted;
      scrieLocal("hdsVolum", volum.value);
    });
    selPista.addEventListener("change", function(){ self.alegePista(selPista.value); });
    selSub.addEventListener("change", function(){ self.alegeSubtitrarea(selSub.value); });
    bifa.addEventListener("change", function(){
      if(self.peTv){ scrieLocal("hdsStrat", bifa.checked ? "1" : "0"); }
      self._strat();
    });
    bPlin.addEventListener("click", function(){ self.comutaEcranul(); });
    bStop.addEventListener("click", function(){
      self.opreste(true);
      if(self.o.laOprire){ self.o.laOprire(); }
    });
    ["fullscreenchange", "webkitfullscreenchange"].forEach(function(ev){
      document.addEventListener(ev, function(){ self._laEcran(); });
    });
    ["mousemove", "touchstart", "keydown", "focusin"].forEach(function(ev){
      r.addEventListener(ev, function(){ self._arataBara(); }, {passive: true});
    });
    r.addEventListener("keydown", function(e){
      if(e.key === "Escape" && r.classList.contains("hp-plin-css")){ self.comutaEcranul(); e.stopPropagation(); }
    });
    this._vizibil = function(){ if(!document.hidden){ self._stratAcum(); } };
    document.addEventListener("visibilitychange", this._vizibil);
    this._fereastra(null);
    this._butoane();
    this._piste([]);
    this._subtitrari(null);
  };

  // ------------------------------------------------------------ cererile
  Player.prototype._antete = function(){
    var a = {"X-HDS-Fereastra": this.fereastra};
    if(this.o.csrf){ a["X-HDS-CSRF"] = this.o.csrf; }
    return a;
  };
  Player.prototype._cerere = function(cale, metoda, corp, semnal){
    var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: this._antete()};
    if(semnal){ optiuni.signal = semnal; }
    if(corp){
      optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
      optiuni.body = corp.toString();
    }
    return fetch(cale, optiuni).then(function(r){
      if(r.status === 401){ location.replace("/"); throw new Error(tx("deconectat")); }
      return r.json().catch(function(){ return {result: false, message: txs("raspuns_http", r.status)}; });
    });
  };

  // ------------------------------------------------------------ afisajul
  Player.prototype.mesaj = function(text, buton, laButon){
    var m = this.e.mesaj;
    m.textContent = "";
    if(!text){ m.classList.add("hp-ascuns"); return; }
    m.appendChild(el("div", "", text));
    if(buton){
      var b = el("button", "", buton); b.type = "button";
      b.addEventListener("click", laButon);
      m.appendChild(b);
      // un mesaj cu buton (o eroare, o intrebare) ia locul semnului
      this._semn("");
    }
    m.classList.remove("hp-ascuns");
  };
  // semnul de peste imagine: titlu (ce se intampla) si, dedesubt, numele canalului; "" il ascunde
  Player.prototype._semn = function(titlu, sub){
    var s = this.e.semn;
    if(!titlu){
      s.classList.add("hp-ascuns");
      clearTimeout(this._ceasAntena); this._ceasAntena = null;
      return;
    }
    this.e.semnTitlu.textContent = titlu;
    this.e.semnSub.textContent = sub || "";
    this.e.semnSub.classList.toggle("hp-ascuns", !sub);
    s.classList.remove("hp-ascuns");
    this.e.mesaj.classList.add("hp-ascuns");
  };
  Player.prototype._semnVizibil = function(){ return !this.e.semn.classList.contains("hp-ascuns"); };
  // "Se pornește..." numai cand nu e semnul (semnul spune deja ce se intampla)
  Player.prototype._sePorneste = function(){
    if(!this._semnVizibil()){ this.mesaj(tx("se_porneste")); }
  };
  // primul cadru al canalului: mesajul si semnul pleaca
  Player.prototype._primulCadru = function(){
    this.mesaj("");
    this._semn("");
    this._pasiOpreste();
    this._stareReluata();
  };
  Player.prototype.stare = function(text, eroare, tehnic){
    this.e.stare.textContent = text || "";
    this.e.stare.classList.toggle("hp-eroare", !!eroare);
    this.e.tehnic.textContent = tehnic || "";
    this.e.detalii.classList.toggle("hp-ascuns", !tehnic);
    if(!tehnic){ this.e.detalii.open = false; }
  };
  // randul de stare: canalul de acum (si avertizarea lui); dupa o reconectare reusita, in locul erorii ramase
  Player.prototype._stareAcum = function(){
    var d = this.sesiune || {};
    this._textAcum = txs("acum", d.nume || this.nume || this.ref) + (d.avertizare ? ". " + d.avertizare : "") +
      (d.avertizare && d.sunet_lipsa && this._imagineMerge ? " " + tx("imaginea_merge") : "");
    this.stare(this._textAcum);
  };
  // avertizarea dupa PMT-ul fluxului (a.avertizare din tv-stare; null cat nu s-a citit): randul de stare se reface numai
  // cand arata canalul (nu peste o eroare sau peste raspunsul alegerii unei piste)
  Player.prototype._avertizarePmt = function(a){
    if(typeof a.avertizare !== "string" || !this.sesiune){ return; }
    if(a.avertizare === this.sesiune.avertizare && !!a.sunet_lipsa === !!this.sesiune.sunet_lipsa){ return; }
    var randulCanalului = this.e.stare.textContent === this._textAcum;
    this.sesiune.avertizare = a.avertizare;
    this.sesiune.sunet_lipsa = !!a.sunet_lipsa;
    if(randulCanalului){ this._stareAcum(); }
  };
  Player.prototype._stareReluata = function(){
    // si dupa alegerea unei piste ("Pista aleasă..."): fluxul reconectat merge, randul arata iar canalul
    if(this.pornit && (this.e.stare.classList.contains("hp-eroare") || this._dupaPista)){ this._dupaPista = false; this._stareAcum(); }
  };

  // ------------------------------------------------------------ paza cadrelor
  // Imaginea chiar vine? Cadrele aratate se citesc o data pe secunda cat merge playerul (<video>: getVideoPlaybackQuality
  // sau webkitDecodedFrameCount; playerul wasm: st.afisate). Cat vin cadre noi, randul de stare spune "Imaginea merge."
  // (numai cand sunetul nu se aude, a_mea.sunet_lipsa); fara cadru nou CADRE_OPRITE_MS textul pleaca, iar dupa
  // FARA_CADRE_MS pagina spune ce se intampla, in loc sa ramana tacuta (proba de noapte 13-14.10: Cubavision ramanea pe
  // "Se schimbă canalul...", SACHSEN EINS cu o imagine inghetata, SBN, Belsat, Canale Italia fara imagine si fara mesaj).
  // O imagine care a venit si s-a oprit primeste o reconectare singura (ca la o eroare de decodare, o data pe
  // DECODARE_MS); apoi mesajul: "Canalul nu trimite imagine acum." cand nici receptorul nu mai vede pachete ale imaginii
  // (a_mea.video_pachete), altfel textul de decodare. Nu se judeca: cat se decripteaza, pe pauza, in fila ascunsa, la un
  // post fara imagine (radio: a_mea.video gol) si cat antena se roteste. Cand cadrele revin, mesajul pleaca singur.
  Player.prototype._imagineVine = function(da){
    if(!!this._imagineMerge === !!da){ return; }
    var randulCanalului = this.e.stare.textContent === this._textAcum;
    this._imagineMerge = !!da;
    if(randulCanalului && this.pornit){ this._stareAcum(); }
  };
  Player.prototype._cadre = function(){
    if(this.felJucator === "wasm"){
      var st = this.jucator && this.jucator.st;
      return st && typeof st.afisate === "number" ? st.afisate : null;
    }
    var v = this.e.video;
    if(v.getVideoPlaybackQuality){ try { return v.getVideoPlaybackQuality().totalVideoFrames; } catch(e) {} }
    return typeof v.webkitDecodedFrameCount === "number" ? v.webkitDecodedFrameCount : null;
  };
  Player.prototype._paziCadrele = function(){
    var self = this, gen = self._generatie;
    clearTimeout(self._ceasCadre);
    self._cadreN = null; self._cadreLa = Date.now(); self._cadreVp = null; self._cadreAu = false;
    self._faraCadre = false; self._antenaMisca = false; self._jucatorLa = Date.now();
    function pas(){
      self._ceasCadre = null;
      if(gen !== self._generatie || !self.jucator || self.distrus){ return; }
      self._cadrePas();
      if(gen === self._generatie && self.jucator){ self._ceasCadre = setTimeout(pas, 1000); }
    }
    self._ceasCadre = setTimeout(pas, 1000);
  };
  Player.prototype._cadrePas = function(){
    var self = this, acum = Date.now();
    var a = self.ultimaStare && self.ultimaStare.a_mea;
    if(a && (!self.sesiune || a.id !== self.sesiune.id)){ a = null; }
    var vp = a && typeof a.video_pachete === "number" ? a.video_pachete : null;
    var n = self._cadre();
    if(n === null){ return; }
    if(self._cadreN === null || n < self._cadreN){ self._cadreN = n; }
    if(n > self._cadreN){
      self._cadreN = n; self._cadreLa = acum; self._cadreVp = vp; self._cadreAu = true; self._antenaMisca = false;
      self._imagineVine(true);
      if(self._faraCadre){ self._faraCadre = false; self.mesaj(""); self._stareAcum(); }
      return;
    }
    if(self._cadreVp === null){ self._cadreVp = vp; }
    var m = self._media();
    if(a && a.pmt_citit === false && !self._seDecripteaza && !m.paused && !document.hidden && !self._antenaMisca &&
       !self._faraCadre && acum - (self._jucatorLa || acum) >= FARA_PMT_MS){
      // fara PMT (FARA_PMT_MS, sus) pagina nu stie nici daca e imagine (a.video gol): mesajul lui, in locul tacerii
      self._faraCadre = true;
      self._semn("");
      self.mesaj(tx("fara_pmt"), tx("incearca"), function(){ self._dinNou(); });
      self.stare(tx("fara_pmt"), true);
      return;
    }
    if(self._seDecripteaza || m.paused || document.hidden || !(a && a.video) || self._antenaMisca || self._faraCadre){
      // nimic de judecat acum: ceasul pleaca de aici
      if(!self._faraCadre){ self._cadreLa = acum; self._cadreVp = vp; }
      return;
    }
    if(acum - self._cadreLa >= CADRE_OPRITE_MS){ self._imagineVine(false); }
    if(acum - self._cadreLa < FARA_CADRE_MS){ return; }
    if(self._cadreAu && (!self._decodareLa || acum - self._decodareLa > DECODARE_MS)){
      // imaginea a venit si s-a oprit: o reconectare singura (fluxul de la capat)
      self._decodareLa = acum;
      self._opresteJucatorul();
      self._jucator();
      return;
    }
    var faraPachete = vp !== null && self._cadreVp !== null && vp <= self._cadreVp;
    var cauza = faraPachete ? tx("fara_imagine") : (self.o.m3u ? tx("decodare_m3u") : tx("decodare"));
    self._faraCadre = true;
    self._semn("");
    self.mesaj(cauza, tx("incearca"), function(){ self._dinNou(); });
    self.stare(cauza, true);
  };
  // imaginea de acum pentru butoane: playerul wasm (aceleasi proprietati ca <video>) sau elementul <video>
  Player.prototype._media = function(){
    return (this.felJucator === "wasm" && this.jucator) ? this.jucator : this.e.video;
  };
  Player.prototype._butoane = function(){
    var v = this._media(), merge = !!this.jucator;
    this.e.reda.innerHTML = v.paused ? IC.reda : IC.pauza;
    this.e.reda.appendChild(el("span", "hp-text", v.paused ? tx("reda") : tx("pauza")));
    this.e.reda.title = v.paused ? tx("reda") : tx("pauza");
    this.e.reda.disabled = !merge;
    this.e.mut.innerHTML = (v.muted || v.volume === 0) ? IC.mut : IC.sunet;
    this.e.mut.title = v.muted ? tx("sunet_pornit") : tx("sunet_oprit");
    var plin = this._ePlin();
    this.e.plin.innerHTML = plin ? IC.iesi : IC.plin;
    this.e.plin.appendChild(el("span", "hp-text", plin ? tx("iesire") : tx("ecran_intreg")));
    this.e.plin.title = plin ? tx("iesire_ecran") : tx("ecran_intreg");
  };
  Player.prototype._piste = function(piste, aleasa){
    var s = this.e.pista;
    // lista se reface numai cand s-a schimbat (o lista deschisa nu se inchide singura la fiecare citire a starii)
    var semn = JSON.stringify([piste || [], aleasa]);
    if(semn === this._semnPiste){ return; }
    this._semnPiste = semn;
    s.textContent = "";
    var bune = (piste || []);
    if(!bune.length){
      var o = el("option", "", tx("sunet_canal")); o.value = ""; s.appendChild(o);
      s.disabled = true;
      return;
    }
    bune.forEach(function(p){
      var o = el("option", "", numePista(p));
      o.value = String(p.pid);
      o.disabled = !p.merge;
      if(p.aleasa || p.pid === aleasa){ o.selected = true; }
      s.appendChild(o);
    });
    // nicio pista aleasa (numai piste care nu merg in browser, de pilda numai AC-3): lista arata prima, nu un camp gol
    if(s.selectedIndex < 0){ s.options[0].selected = true; }
    s.disabled = bune.filter(function(p){ return p.merge; }).length < 2;
  };
  Player.prototype._subtitrari = function(d){
    var s = this.e.sub;
    s.textContent = "";
    if(!d){
      var o = el("option", "", this.ref !== null && !this.peTv ? tx("sub_numai_tv") : tx("sub_fara"));
      o.value = ""; s.appendChild(o); s.disabled = true;
      return;
    }
    var oprit = el("option", "", tx("sub_oprita")); oprit.value = "oprit"; s.appendChild(oprit);
    (d.subtitrari || []).forEach(function(x){
      var o = el("option", "", txs("sub_aleasa", x.limba || x.text || x.id));
      o.value = x.id;
      if(x.pornita){ o.selected = true; }
      s.appendChild(o);
    });
    if(d.fara_subtitrari){ oprit.selected = true; }
    s.disabled = !(d.subtitrari || []).length;
  };

  // ------------------------------------------------------------ pornirea si oprirea
  // "Pornește din nou" si "Încearcă din nou": in modul "urmeaza televizorul", canalul de ACUM al televizorului
  Player.prototype._dinNou = function(preia){
    var self = this;
    if(self.urmeaza){ self.porneste("", "", preia); } else { self.porneste(self.ref, self.nume, preia); }
  };

  Player.prototype.porneste = function(ref, nume, preia){
    var self = this;
    var reluare = !!self._dinReluare;
    self._dinReluare = false;
    if(self.inLucru){
      // o pornire e in lucru: in modul "urmeaza televizorul" o pornire noua vine dupa ea (ultima castiga)
      if(self.urmeaza && !ref){ self._dupa = {preia: preia}; }
      return;
    }
    // o alegere noua anuleaza reincercarea unui canal criptat care astepta (ultima cerere castiga)
    clearTimeout(self._reia); self._reia = null;
    clearTimeout(self._ceasRepede); self._ceasRepede = null;
    if(!reluare){ self._asteapta = 0; }
    if(self.o.jeton){ self.mesaj(tx("jeton")); return; }
    var urmeaza = !ref && self.o.urmeazaTv !== false;
    if(!urmeaza){ self._opresteUrmarirea(); }
    self.urmeaza = urmeaza;
    self._dupa = null;
    self.inLucru = true;
    // starea ceruta inainte de aceasta pornire nu mai conteaza (_citesteStarea): proba de noapte 13-14.10, RTL Television
    self._porniri = (self._porniri || 0) + 1;
    self._opresteJucatorul();
    self.ref = ref || "";
    self.nume = nume || "";
    self._sePorneste();
    self.stare("");
    var pt = poate();
    // mpegts.js (MediaSource) reda H.264 / HEVC; imaginea MPEG-2 merge si fara el, prin playerul wasm
    var mse = false, eroareMse = null;
    function faraMse(){
      return eroareMse || new Error(tx("fara_mse"));
    }
    function q0(){
      var q = new URLSearchParams();
      q.set("hevc", pt.hevc ? "1" : "0"); q.set("ac3", pt.ac3 ? "1" : "0"); q.set("wasm", pt.wasm ? "1" : "0");
      if(preia){ q.set("preia", "1"); }
      return q;
    }
    Promise.all([incarcaMpegts().catch(function(e){ eroareMse = e; }), incarcaSunet()]).then(function(){
      mse = !!(window.mpegts && mpegts.getFeatureList && mpegts.getFeatureList().mseLivePlayback);
      if(!mse && !pt.wasm){ throw faraMse(); }
      if(self.urmeaza){
        // urmeaza televizorul: o singura cerere; receptorul alege canalul de acum al televizorului (fara tv-stare si
        // tv-verifica: tv-porneste face aceleasi verificari)
        var q = q0(); q.set("urmeaza", "1");
        return self._cerere("/api/tv-porneste?" + q.toString(), "POST");
      }
      return self._cerere("/api/tv-stare").then(function(st){
        self.ultimaStare = st;
        if(!st.permis){ throw new Error(tx("oprita_setari")); }
        var tv = st.tv && st.tv.ref;
        if(!self.ref){
          if(!tv){ throw new Error(tx("tv_gol")); }
          self.ref = tv;
          self.nume = self.nume || (st.tv && st.tv.nume) || "";
        }
        var q = q0(); q.delete("preia"); q.set("ref", self.ref);
        return self._cerere("/api/tv-verifica?" + q.toString());
      }).then(function(v){
        if(!v.result){ throw new Error(v.message || tx("neverificat")); }
        self.nume = self.nume || v.nume || "";
        self.peTv = !!v.pe_tv;
        if(!v.merge){
          if(v.muta_tv && self.o.mutaTv){
            // canalul nu e pe frecventa televizorului, iar receptorul nu-l poate lua altfel (antena cu motor, un singur
            // tuner de satelit): televizorul trece pe el, apoi imaginea urmeaza televizorul
            return {mutare: true};
          }
          var err = new Error(v.motiv || tx("nu_merge_acum"));
          err.extern = v.extern;
          throw err;
        }
        if(v.pe_tv && self.o.urmeazaPeTv){ self.urmeaza = true; }
        // imaginea MPEG-2 / MPEG-1: playerul wasm (HdsPlayerWasm, /tv/hds-player.js) in locul lui mpegts.js, pe acelasi
        // /api/tv-flux; receptorul trimite fluxul la fel
        self.cuWasm = pt.wasm && imagineWasm(v.video);
        if(!self.cuWasm && !mse){ throw faraMse(); }
        var q = q0(); q.set("ref", self.ref);
        return self._cerere("/api/tv-porneste?" + q.toString(), "POST").then(function(d){ d._verificare = v; return d; });
      });
    }).then(function(d){
      self.inLucru = false;
      if(d.mutare){ self._mutaTv(self.ref, self.nume); return; }
      if(self._dupa){
        // televizorul a trecut intre timp pe alt canal: pornirea lui (receptorul inlocuieste sesiunea de acum)
        var dupa = self._dupa; self._dupa = null;
        self.porneste("", "", dupa.preia);
        return;
      }
      if(!d.result){
        self._refuz(d, preia);
        return;
      }
      if(self.urmeaza && !d._verificare){
        self.ref = d.ref || self.ref;
        self.nume = d.nume || self.nume;
        self.peTv = true;
        self.cuWasm = pt.wasm && imagineWasm(d.video);
        if(!self.cuWasm && !mse){ throw faraMse(); }
      }
      self.sesiune = d;
      self._repede = 0;
      self._asteapta = 0;
      self.pornit = true;
      // canal criptat: "Se decriptează..." de la pornire, cat camul de pe receptor inca n-a dat cheia
      self._seDecripteaza = d.decriptare === "asteapta";
      if(self._seDecripteaza){ self._semn(tx("decriptare"), self.nume); self._pasi(); }
      self.reconectare = true;
      self.reconectari = [];
      self._decodareLa = 0;
      self._stareAcum();
      self.e.bifa.checked = self.peTv ? citesteLocal("hdsStrat", "1") === "1" : false;
      self.e.comutator.title = self.peTv ? tx("afisaj_titlu") : tx("afisaj_alt");
      if(self.urmeaza){
        self.tv = {ref: d.ref || self.ref, nume: self.nume, standby: !!(self.tv && self.tv.standby && refCheie(self.tv.ref) === refCheie(d.ref))};
        if(self.o.laCanal){ try { self.o.laCanal(self.nume, self.ref); } catch(e) {} }
        self._asculta();
      }
      self._jucator();
      self._ceasStare();
      self._strat();
      self._citestePistele();
    }).catch(function(e){
      self.inLucru = false;
      if(self._dupa){ var dupa = self._dupa; self._dupa = null; self.porneste("", "", dupa.preia); return; }
      self.mesaj(e.message || tx("nu_raspunde"), self.urmeaza ? tx("incearca") : "", function(){ self._dinNou(); });
      if(self.o.laMotiv){ self.o.laMotiv(e.message, e.extern); }
      // si cand canalul de acum nu merge, imaginea urmeaza televizorul mai departe (alt canal poate merge); ce e acum pe
      // televizor se afla din nou (fara alta pornire)
      if(self.urmeaza){ self.tv = null; self._asculta(); }
    });
  };

  // raspunsul tv-porneste fara sesiune
  Player.prototype._refuz = function(d, preia){
    var self = this;
    if(self.urmeaza){
      // ce e pe televizor: canalul refuzat (cererea lunga asteapta un canal nou, nu acelasi din nou)
      self.tv = d.ref !== undefined ? {ref: d.ref || "", nume: d.nume || "", standby: false} : null;
    }
    if(d.asteapta && (self._asteapta = (self._asteapta || 0) + 1) <= 12){
      // canal criptat: receptorul lasa o pauza intre o oprire si o pornire criptata; sesiunea veche s-a oprit, iar
      // pagina intreaba din nou singura dupa `secunde` (in modul "urmeaza televizorul": canalul de atunci al televizorului)
      self.opreste(false);
      if(self.urmeaza){ self._semn(d.message || TEXTE.schimba, d.nume || self.nume); } else { self.mesaj(d.message); }
      self._reia = setTimeout(function(){
        self._reia = null;
        self._dinReluare = true;
        self._dinNou(preia);
      }, Math.min(20, Math.max(1, d.secunde || 3)) * 1000 + 300);
      self._pasi();
      if(self.urmeaza){ self._asculta(); }
      return;
    }
    self._asteapta = 0;
    if(d.repede && (self._repede = (self._repede || 0) + 1) <= 3){
      // receptorul cere o pauza intre doua porniri noi: reincercarea vine singura, cand trece pauza (ms, de la receptor)
      if(!self._semnVizibil()){ self.mesaj(d.message); }
      self._ceasRepede = setTimeout(function(){ self._ceasRepede = null; self._dinNou(preia); },
        Math.min(2100, Math.max(150, (d.ms || 2000) + 100)));
      if(self.urmeaza){ self._asculta(); }
      return;
    }
    self._repede = 0;
    if(d.alta_fereastra){
      self.mesaj(d.message, tx("preia_aici"), function(){ self._dinNou(true); });
    } else {
      self.mesaj(d.message || tx("nu_a_pornit"), self.urmeaza ? tx("din_nou") : "", function(){ self._dinNou(); });
    }
    if(self.urmeaza){ self._asculta(); }
  };

  Player.prototype._jucator = function(){
    var self = this;
    self._opresteJucatorul();
    if(self.cuWasm){ self._jucatorWasm(); return; }
    var v = self.e.video;
    self.e.imagine.classList.add("hp-ascuns");
    v.classList.remove("hp-ascuns");
    self.felJucator = "mse";
    // sunetul AC-3 decodat in pagina (browserul nu-l reda): convertorul primeste PES-urile AC-3 de la mpegts.js si da
    // cadre FLAC; daca decodorul lui nu porneste, pagina porneste din nou fara AC-3 (receptorul il scoate din PMT)
    var generatie = self._generatie;
    self._sunetAc3 = (poate().ac3wasm && window.HdsSunetAc3) ? HdsSunetAc3.convertor({laEsec: function(e){
      if(generatie !== self._generatie || self.distrus){ return; }
      try { console.warn("[HdsPlayer] AC-3: " + (e && e.message)); } catch(x) {}
      faraAc3Wasm();
      self._dinNou();
    }}) : null;
    self.jucator = mpegts.createPlayer({type: "mpegts", isLive: true, url: "/api/tv-flux"}, {
      enableWorker: false, enableStashBuffer: false, lazyLoad: false, autoCleanupSourceBuffer: true,
      liveBufferLatencyChasing: true, liveBufferLatencyMaxLatency: 3.0, liveBufferLatencyMinRemain: 0.8,
      headers: self._antete(), hdsSunetAc3: self._sunetAc3 || undefined
    });
    var j = self.jucator;
    self.jucator.on(mpegts.Events.ERROR, function(tip, detaliu, info){ if(self.jucator === j){ self._eroareFlux(tip, detaliu, info); } });
    // codul exact al imaginii (de pilda hvc1.2.1.L153.B0): la o eroare de decodare spune daca browserul nu-l cunoaste
    self._codecImagine = "";
    self.jucator.on(mpegts.Events.MEDIA_INFO, function(mi){ if(self.jucator === j){ self._codecImagine = (mi && mi.videoCodec) || ""; } });
    self.jucator.attachMediaElement(v);
    self.jucator.load();
    self._sePorneste();
    var p = self.jucator.play();
    if(p && p.then){
      p.then(function(){ if(self.jucator === j){ self._primulCadru(); } }).catch(function(){
        if(self.jucator !== j){ return; }
        self.mesaj(tx("apasa_reda"), tx("reda"), function(){ self.e.video.play(); self.mesaj(""); });
      });
    }
    v.addEventListener("playing", function(){ if(self.jucator === j){ self._primulCadru(); } }, {once: true});
    self._paziAntena();
    self._paziCadrele();
    self._butoane();
  };

  // imaginea MPEG-2 / MPEG-1: playerul wasm pe al doilea canvas; butoanele il folosesc prin _media()
  Player.prototype._jucatorWasm = function(){
    var self = this, v = self.e.video;
    v.classList.add("hp-ascuns");
    self.e.imagine.classList.remove("hp-ascuns");
    self._sePorneste();
    var generatie = self._generatie;
    incarcaWasm().then(function(){
      if(generatie !== self._generatie || !self.pornit || self.distrus){ return; }
      var j = new HdsPlayerWasm(self.e.imagine, {antete: self._antete(), volum: v.volume, mut: v.muted,
        program: programDinRef((self.sesiune && self.sesiune.ref) || self.ref),
        laEveniment: function(tip, d){ if(self.jucator === j){ self._laWasm(j, tip, d); } }});
      self.jucator = j;
      self.felJucator = "wasm";
      j.porneste("/api/tv-flux");
      self._paziAntena();
      self._paziCadrele();
      self._butoane();
    }).catch(function(e){
      if(generatie !== self._generatie){ return; }
      self.mesaj(e.message, tx("incearca"), function(){ self._dinNou(); });
      self.stare(e.message, true);
    });
    self._butoane();
  };

  Player.prototype._laWasm = function(j, tip, d){
    var self = this;
    if(tip === "primul_cadru"){ self._primulCadru(); return; }
    if(tip === "schimbare"){ self._butoane(); return; }
    if(tip === "sunet_blocat"){
      // browserul porneste sunetul numai dupa o apasare; imaginea merge pana atunci
      self.mesaj(tx("fara_sunet"), tx("sunet_pornit"), function(){ j.play(); self.mesaj(""); });
      return;
    }
    if(tip !== "eroare"){ return; }
    if(d.fel === "format"){
      // fluxul nu are imagine MPEG-2 (formatul nu se stia dinainte): imaginea trece pe mpegts.js
      if(window.mpegts && mpegts.getFeatureList && mpegts.getFeatureList().mseLivePlayback){
        self.cuWasm = false;
        self._jucator();
        return;
      }
      self._eroareFlux("MediaError", "FormatUnsupported", {msg: d.text});
      return;
    }
    if(d.fel === "http"){ self._eroareFlux("NetworkError", "HttpStatusCodeInvalid", {code: d.cod}); return; }
    if(d.fel === "sfarsit"){ self._eroareFlux("NetworkError", "EarlyEof", {msg: d.text}); return; }
    if(d.fel === "retea"){ self._eroareFlux("NetworkError", "Exception", {msg: d.text}); return; }
    self._eroareFlux("MediaError", "DecodorWasm", {msg: d.text});
  };

  Player.prototype._opresteJucatorul = function(){
    // o incarcare a playerului wasm inca in lucru nu mai porneste nimic
    this._generatie = (this._generatie || 0) + 1;
    clearTimeout(this._ceasCadre); this._ceasCadre = null;
    if(this._sunetAc3){ try { this._sunetAc3.inchide(); } catch(e) {} this._sunetAc3 = null; }
    this._imagineVine(false);
    if(this.jucator){
      if(this.felJucator === "wasm"){
        try { this.jucator.opreste(); } catch(e) {}
      } else {
        try { this.jucator.pause(); this.jucator.unload(); this.jucator.detachMediaElement(); this.jucator.destroy(); } catch(e) {}
      }
      this.jucator = null;
    }
    this.felJucator = "";
    this._butoane();
  };

  Player.prototype.opreste = function(trimite){
    var era = this.pornit;
    clearTimeout(this._reia); this._reia = null;
    clearTimeout(this._ceasRepede); this._ceasRepede = null;
    if(trimite){
      // oprirea ceruta de om: imaginea nu mai urmeaza televizorul
      this._opresteUrmarirea();
      this.urmeaza = false;
      this._dupa = null;
      this._semn("");
    }
    this._opresteJucatorul();
    this.e.imagine.classList.add("hp-ascuns");
    this.e.video.classList.remove("hp-ascuns");
    this.pornit = false;
    this.sesiune = null;
    this._seDecripteaza = false;
    this._pasiOpreste();
    clearTimeout(this.ceasStare); this.ceasStare = null;
    clearTimeout(this.ceasStrat); this.ceasStrat = null;
    this.coada = [];
    this.ctx.clearRect(0, 0, this.e.canvas.width, this.e.canvas.height);
    this._fereastraCoada = undefined;
    this._fereastra(null);
    // stratul a fost sters: la pornirea urmatoare se cere intreg (fara ETag), nu un 304
    this.etag = "";
    this.ultimAfisat = 0;
    this._piste([]);
    this._subtitrari(null);
    this.mesaj("");
    if(trimite && era){ this._cerere("/api/tv-opreste", "POST").catch(function(){}); }
  };

  Player.prototype.distruge = function(trimite){
    this.opreste(trimite);
    this._opresteUrmarirea();
    this.urmeaza = false;
    if(this._ePlin()){ this.comutaEcranul(); }
    document.removeEventListener("visibilitychange", this._vizibil);
    this.distrus = true;
    if(this.e.radacina.parentNode){ this.e.radacina.parentNode.removeChild(this.e.radacina); }
  };

  // ------------------------------------------------------------ urmeaza televizorul
  // Cererea lunga: raspunde cand televizorul nu mai e pe ce stie pagina (alt canal, standby) sau dupa ~25 s; urmatoarea
  // pleaca imediat. O eroare (receptorul nu raspunde, ruta lipseste): starea o data pe secunda, din /api/tv-stare.
  Player.prototype._asculta = function(){
    var self = this;
    if(self._ascult || !self.urmeaza || self.distrus){ return; }
    var gen = self._ascult = (self._ascultNr = (self._ascultNr || 0) + 1);
    var nr = 0;
    function viu(){ return self._ascult === gen && self.urmeaza && !self.distrus; }
    function pas(){
      if(!viu()){ return; }
      var tv = self.tv || {};
      var q = new URLSearchParams();
      q.set("ref", tv.ref || ""); q.set("standby", tv.standby ? "1" : "0");
      // o cerere care nu se mai intoarce (legatura pierduta fara eroare) nu opreste urmarirea: dupa ASCULTARE_MS alta
      var a = ++nr, opritor = window.AbortController ? new AbortController() : null;
      self._ceasAscult = setTimeout(function(){
        if(a !== nr || !viu()){ return; }
        nr++;
        if(opritor){ try { opritor.abort(); } catch(e) {} }
        pas();
      }, ASCULTARE_MS);
      self._cerere("/api/tv-urmeaza?" + q.toString(), "GET", null, opritor && opritor.signal).then(function(d){
        if(a !== nr || !viu()){ return; }
        nr++;
        clearTimeout(self._ceasAscult);
        if(!d.result || !d.tv){ return rezerva(); }
        self._laTv(d.tv.ref || "", d.tv.nume || "", !!d.in_standby);
        self._ceasAscult = setTimeout(pas, d.plin ? 1000 : 0);
      }).catch(function(){
        if(a !== nr || !viu()){ return; }
        nr++;
        clearTimeout(self._ceasAscult);
        self._ceasAscult = setTimeout(pas, 1500);
      });
    }
    function rezerva(){
      return self._cerere("/api/tv-stare").then(function(st){
        if(!viu()){ return; }
        if(st.result && st.tv){ self._laTv(st.tv.ref || "", st.tv.nume || "", !!st.in_standby); }
        self._ceasAscult = setTimeout(pas, 1000);
      }).catch(function(){ if(viu()){ self._ceasAscult = setTimeout(pas, 1500); } });
    }
    pas();
  };
  Player.prototype._opresteUrmarirea = function(){
    this._ascult = null;
    clearTimeout(this._ceasAscult); this._ceasAscult = null;
    clearTimeout(this._semnTasta); this._semnTasta = null;
    clearTimeout(this._ceasMutare); this._ceasMutare = null;
    this._tinta = null;
  };

  // ce merge pe televizor, din cererea lunga (sau din starea transmisiei)
  Player.prototype._laTv = function(ref, nume, standby){
    var self = this;
    var vechi = self.tv;
    self.tv = {ref: ref, nume: nume, standby: standby};
    if(!self.urmeaza || self.distrus){ return; }
    if(self._tinta){
      // televizorul trece pe canalul ales (mutaTv): pornirea, cand a ajuns
      if(refCheie(ref) !== self._tinta){ return; }
      self._tinta = null;
      clearTimeout(self._ceasMutare); self._ceasMutare = null;
      self._schimba(nume || self.nume, true);
      return;
    }
    // nu se stia ce era pe televizor (dupa o pornire refuzata): numai se tine minte, fara alta pornire
    if(!vechi){ return; }
    var alt = refCheie(ref) !== refCheie(vechi.ref);
    if(standby){
      // standby: receptorul opreste transmisia (daca nu e permisa in standby) si spune de ce
      if(!vechi.standby){ self._semn(""); self._citesteStarea(); }
      return;
    }
    if(!alt && !vechi.standby){ return; }
    if(!ref){
      // zap-ul n-a pornit nimic pe televizor: semnul pleaca, starea spune restul
      self._semn("");
      return;
    }
    if(!alt && self.pornit && self.jucator){ self._semn(""); return; }
    self._schimba(nume);
  };

  // televizorul a trecut pe alt canal (sau s-a trezit din standby): semnul, apoi canalul de acum al televizorului
  Player.prototype._schimba = function(nume, mutat){
    var self = this;
    clearTimeout(self._reia); self._reia = null;
    clearTimeout(self._ceasRepede); self._ceasRepede = null;
    clearTimeout(self._semnTasta); self._semnTasta = null;
    self._asteapta = 0; self._repede = 0;
    self._semn(mutat ? tx("muta").replace("%s", nume || "") : tx("schimba"), mutat ? "" : (nume || ""));
    if(self.inLucru){ self._dupa = {}; return; }
    // imaginea veche pleaca; sesiunea veche o inlocuieste receptorul la pornirea celei noi
    self._opresteJucatorul();
    self.porneste("", "");
  };

  // tastele telecomenzii din panou, INAINTE sa plece: la cele care schimba canalul (CH+, CH-, <, >) fluxul din browser
  // se opreste si semnul apare pe loc; cererea lunga aduce apoi canalul nou (cu numele lui) si pornirea. Sesiunea de pe
  // receptor nu se opreste de aici: zap-ul o inlocuieste (aceeasi frecventa) sau ii ia singur tunerul (alta frecventa).
  // Daca televizorul nu schimba nimic (un meniu deschis), dupa 2,5 s semnul pleaca si imaginea revine.
  Player.prototype.tastaTelecomanda = function(cod, lung){
    var self = this;
    if(!self.urmeaza || lung || !self.pornit || TASTE_ZAP.indexOf(+cod) < 0){ return; }
    self._semn(tx("schimba"), "");
    self._opresteJucatorul();
    clearTimeout(self._semnTasta);
    self._semnTasta = setTimeout(function(){
      self._semnTasta = null;
      if(self.pornit && !self.inLucru){
        self._semn("");
        if(!self.jucator){ self._jucator(); }
      }
    }, SEMN_TASTA_MS);
  };
  // tasta a ajuns la receptor (raspunsul /api/remotecontrol): tasta se aplica pe loc, deci un zap s-a facut deja; starea
  // spune canalul nou si cand cererea lunga ar intarzia (un drum in plus, ieftin)
  Player.prototype.tastaTrimisa = function(cod, lung){
    var self = this;
    if(!self.urmeaza || self.distrus){ return; }
    self._cerere("/api/tv-stare").then(function(st){
      if(st.result && st.tv && self.urmeaza){ self._laTv(st.tv.ref || "", st.tv.nume || "", !!st.in_standby); }
    }).catch(function(){});
  };

  // "Vezi live" pe un canal pe care transmisia nu-l poate lua fara televizor: televizorul trece pe el (mutaTv, zap ca
  // din telecomanda), iar imaginea porneste cand televizorul a ajuns pe canal; de atunci urmeaza televizorul
  Player.prototype._mutaTv = function(ref, nume){
    var self = this;
    self.urmeaza = true;
    self.inLucru = true;
    self.mesaj("");
    self._semn(tx("muta").replace("%s", nume || ""), "");
    Promise.resolve().then(function(){ return self.o.mutaTv(ref); }).then(function(d){
      self.inLucru = false;
      if(!d || !d.result){
        self._semn("");
        self.mesaj((d && d.message) || tx("nu_a_trecut"), tx("incearca"), function(){ self.porneste(ref, nume); });
        return;
      }
      self._tinta = refCheie(ref);
      self.tv = self.tv || {ref: "", nume: "", standby: false};
      self._ceasMutare = setTimeout(function(){
        self._ceasMutare = null;
        if(!self._tinta){ return; }
        self._tinta = null;
        self._semn("");
        self.mesaj(tx("nu_a_trecut"), tx("incearca"), function(){ self.porneste(ref, nume); });
      }, MUTARE_MS);
      // zap-ul s-a facut cand a raspuns ruta; starea spune pe loc daca televizorul e deja pe canal
      self._cerere("/api/tv-stare").then(function(st){
        if(st.result && st.tv){ self._laTv(st.tv.ref || "", st.tv.nume || "", !!st.in_standby); }
      }).catch(function(){});
      self._asculta();
    }).catch(function(e){
      self.inLucru = false;
      self._semn("");
      self.mesaj((e && e.message) || tx("nu_raspunde"), tx("incearca"), function(){ self.porneste(ref, nume); });
    });
  };

  // cat semnul sta peste imagine si primul cadru nu vine: antena se roteste? (/api/motor, numai citire)
  Player.prototype._paziAntena = function(){
    var self = this;
    clearTimeout(self._ceasAntena);
    if(!self.urmeaza){ return; }
    var gen = self._generatie;
    function pas(){
      self._ceasAntena = null;
      if(gen !== self._generatie || !self._semnVizibil() || self.distrus){ return; }
      self._cerere("/api/motor").then(function(d){
        if(gen !== self._generatie || !self._semnVizibil()){ return; }
        self._antenaMisca = !!(d && d.result && d.se_misca);
        if(d && d.result && d.se_misca){ self.e.semnSub.textContent = tx("antena"); self.e.semnSub.classList.remove("hp-ascuns"); }
        self._ceasAntena = setTimeout(pas, 1500);
      }).catch(function(){});
    }
    self._ceasAntena = setTimeout(pas, 1500);
  };

  // ------------------------------------------------------------ starea transmisiei
  Player.prototype._ceasStare = function(){
    var self = this;
    clearTimeout(self.ceasStare);
    self.ceasStare = setTimeout(function(){
      if(!self.pornit || self.distrus){ return; }
      if(document.hidden){ self._ceasStare(); return; }
      self._citesteStarea().then(function(){ self._ceasStare(); });
    }, self._seDecripteaza ? 1000 : 3000);
  };

  Player.prototype._citesteStarea = function(){
    var self = this;
    // un raspuns cerut inaintea unei porniri noi e al sesiunii vechi: fluxul wasm oprit de un zap pe alta frecventa
    // (EarlyEof) cere starea, iar raspunsul ("oprita: zap", fara sesiune) venea dupa ce canalul nou pornise deja si il
    // oprea cu mesajul zap-ului (proba de noapte 13-14.10, RTL Television)
    var porniri = self._porniri;
    return self._cerere("/api/tv-stare").then(function(d){
      // o pornire in lucru sau un canal criptat care asteapta: starea veche nu mai conteaza
      if(!d.result || !self.pornit || self.inLucru || self._reia || porniri !== self._porniri){ return; }
      self.ultimaStare = d;
      var a = d.a_mea;
      if(!a){
        if(self.urmeaza){ self._faraSesiune(d); return; }
        var motiv = (d.oprita && d.oprita.motiv) || tx("oprita");
        self.opreste(false);
        self.mesaj(motiv, tx("din_nou"), function(){ self._dinNou(); });
        self.stare(motiv, true);
        return;
      }
      if(a.fereastra && a.fereastra !== self.fereastra){
        self.opreste(false);
        self.mesaj(tx("preluata"), tx("preia_inapoi"), function(){ self._dinNou(true); });
        return;
      }
      if(self.urmeaza && d.tv && d.tv.ref && refCheie(d.tv.ref) !== refCheie(a.ref) && !d.in_standby){
        // televizorul e pe alt canal decat sesiunea (un zap pierdut de cererea lunga): canalul lui
        self._laTv(d.tv.ref, d.tv.nume || "", false);
        return;
      }
      self.peTv = !!(d.tv && d.tv.ref && a.ref && d.tv.ref.toUpperCase() === a.ref.toUpperCase());
      self._piste(a.piste, a.pista);
      self._avertizarePmt(a);
      if(a.video && imagineWasm(a.video) && poate().wasm && !self.cuWasm && !self.inLucru){
        // formatul nu se stia la pornire, iar PMT-ul fluxului arata MPEG-2: imaginea trece pe playerul wasm
        self.cuWasm = true;
        self.reconectare = true;
        self.mesaj("");
        self.stare(tx("mpeg2"));
        self._jucator();
        return;
      }
      self._decriptarea(a);
      // dupa o tasta de zap fluxul asteapta canalul nou (_semnTasta), iar cat se decripteaza, imaginea clara: nu se reia
      if(!self.jucator && !self.inLucru && self.reconectare && !self._semnTasta && !self._seDecripteaza){ self._jucator(); }
    }).catch(function(){});
  };

  // canalul criptat, dupa raspunsul camului de pe receptor (a.decriptare): "asteapta" = camul inca incearca (semnul "Se
  // decriptează...", fara eroare), "merge" = imaginea vine; un refuz definitiv sau un cam care nu raspunde opresc sesiunea
  // pe receptor (motivul vine in starea opririi)
  Player.prototype._decriptarea = function(a){
    var self = this;
    var asteapta = a.decriptare === "asteapta";
    if(asteapta && !self._seDecripteaza){
      self._seDecripteaza = true;
      self.mesaj("");
      self._semn(tx("decriptare"), a.nume || self.nume);
      self._pasi();
    } else if(!asteapta && self._seDecripteaza){
      self._seDecripteaza = false;
      if(self._semnVizibil() && self.e.semnTitlu.textContent === tx("decriptare")){ self._semn(""); }
      self._pasiOpreste();
    }
  };

  // PASII DECRIPTARII (sus): cat se asteapta un canal criptat, o cerere pe secunda; setarea oprita pe receptor = nicio
  // cerere in plus pana la urmatoarea asteptare
  Player.prototype._pasiAsteapta = function(){
    return !this.distrus && (this._seDecripteaza || !!this._reia);
  };
  Player.prototype._pasi = function(){
    var self = this;
    clearTimeout(self._ceasPasi); self._ceasPasi = null;
    if(!self._pasiAsteapta()){ self._pasiArata(null); return; }
    if(document.hidden){ self._ceasPasi = setTimeout(function(){ self._pasi(); }, PASI_MS); return; }
    self._cerere("/api/pasi-decriptare").then(function(d){
      if(!self._pasiAsteapta()){ self._pasiArata(null); return; }
      self._pasiArata(d);
      if(d && d.result && !d.pornit){ return; }
      self._ceasPasi = setTimeout(function(){ self._pasi(); }, PASI_MS);
    }).catch(function(){
      if(self._pasiAsteapta()){ self._ceasPasi = setTimeout(function(){ self._pasi(); }, PASI_MS * 3); }
    });
  };
  Player.prototype._pasiOpreste = function(){
    clearTimeout(this._ceasPasi); this._ceasPasi = null;
    this._pasiArata(null);
  };
  // randurile numai cand sunt ale canalului acestui player (televizorul poate fi pe alt canal)
  Player.prototype._pasiArata = function(d){
    var ul = this.e.pasi;
    var ref = this.ref || (this.tv && this.tv.ref) || "";
    var randuri = (d && d.result && d.pornit && d.criptat && d.pasi) || [];
    if(!randuri.length || !ref || refCheie(d.ref) !== refCheie(ref)){
      ul.classList.add("hp-ascuns"); ul.textContent = ""; this._pasiSemn = "";
      return;
    }
    if(randuri.length > PASI_VAZUTI){ randuri = [randuri[0]].concat(randuri.slice(randuri.length - PASI_VAZUTI + 1)); }
    // aceleasi randuri: lista ramane, ca randul care se deruleaza sa nu porneasca la fiecare cerere de la capat
    var semn = randuri.map(function(p){ return (p.t || "") + " " + (p.text || ""); }).join("|");
    if(semn === this._pasiSemn && !ul.classList.contains("hp-ascuns")){ return; }
    this._pasiSemn = semn;
    ul.textContent = "";
    randuri.forEach(function(p, i){
      // randul de acum (ultimul) se deruleaza cand nu incape (hds-derulant, cadru_web.py); celelalte raman taiate curat
      var li = el("li", i === randuri.length - 1 ? "hds-derulant" : "");
      li.appendChild(el("b", "", p.t || ""));
      li.appendChild(document.createTextNode(" " + (p.text || "")));
      li.title = p.text || "";
      ul.appendChild(li);
    });
    ul.classList.remove("hp-ascuns");
  };

  // urmeaza televizorul, iar sesiunea nu mai e: alt canal pe televizor (un zap) = canalul lui; acelasi canal = motivul,
  // iar dupa un zap sau date lipsa (antena se rotea) inca o pornire singura, de cel mult doua ori pe minut
  Player.prototype._faraSesiune = function(d){
    var self = this;
    var tv = d.tv || {}, o = d.oprita || {};
    if(tv.ref && !d.in_standby && refCheie(tv.ref) !== refCheie(self.ref)){
      self.tv = {ref: tv.ref, nume: tv.nume || "", standby: false};
      self._schimba(tv.nume || "");
      return;
    }
    var acum = Date.now();
    self._reporniri = (self._reporniri || []).filter(function(t){ return acum - t < 60000; });
    if((o.cod === "zap" || o.cod === "fara_date") && d.permis && !d.in_standby && tv.ref && self._reporniri.length < REPORNIRI_MAX){
      self._reporniri.push(acum);
      self._opresteJucatorul();
      self.pornit = false;
      self._semn(tx("schimba"), tv.nume || self.nume);
      self.porneste("", "");
      return;
    }
    var motiv = o.motiv || (d.in_standby ? tx("standby") : tx("oprita"));
    self.opreste(false);
    self.mesaj(motiv, tx("din_nou"), function(){ self._dinNou(); });
    self.stare(motiv, true);
  };

  Player.prototype._eroareFlux = function(tip, detaliu, info){
    // cauza reala, pe scurt, in limba omului; tipul si detaliul erorii (mpegts.js sau elementul video) sub "Detalii" si
    // in consola
    var self = this;
    if(!self.jucator){ return; }
    var cod = info && info.code, msg = String((info && (info.msg || info.message)) || "").slice(0, 160);
    var tehnic = tip + ", " + detaliu + (cod !== undefined && cod !== null ? " " + cod : "") + (msg ? ": " + msg : "");
    try { console.warn("[HdsPlayer] " + tehnic); } catch(e) {}
    if(self._seDecripteaza){
      // camul de pe receptor inca decripteaza: fluxul n-are inca imagine; fara mesaj, receptorul hotaraste (imaginea
      // clara: playerul porneste din nou; refuzul: motivul in starea opririi)
      self._opresteJucatorul();
      return;
    }
    var decodare = tip === "MediaError" && (detaliu === "MediaMSEError" || (detaliu === "video" && cod === 3));
    if(decodare && (!self._decodareLa || Date.now() - self._decodareLa > DECODARE_MS)){
      // o eroare de decodare: o singura reconectare singura (fluxul de la capat, de la un cadru intreg), apoi mesajul
      self._decodareLa = Date.now();
      self._opresteJucatorul();
      self._jucator();
      return;
    }
    if(self.urmeaza && tip === "NetworkError" && detaliu !== "HttpStatusCodeInvalid"){
      // urmeaza televizorul: fluxul se opreste si la un zap pe alta frecventa; intai starea (alt canal = canalul lui),
      // fara mesaj; acelasi canal = reconectarea obisnuita
      var acum0 = Date.now();
      self._opresteJucatorul();
      self.reconectari = self.reconectari.filter(function(t){ return acum0 - t < 60000; });
      self.reconectare = self.reconectari.length < 3;
      if(self.reconectare){ self.reconectari.push(acum0); }
      self._citesteStarea();
      return;
    }
    var cauza, reincearca = false;
    if(decodare){
      // sunetul sau imaginea, dupa pachetul refuzat; imaginea HEVC pe care browserul nu o cunoaste (Main 10, 4K), dupa
      // codul ei: fara oprire inainte de eroare (unele browsere spun ca nu stiu un cod pe care totusi il redau)
      var cImg = self._codecImagine || "";
      if(/audio packet/i.test(msg)){ cauza = self.o.m3u ? tx("sunet_m3u") : tx("sunet"); }
      else if(/^(hvc1|hev1)\./.test(cImg) && !suporta('video/mp4; codecs="' + cImg + '"')){
        cauza = self.o.m3u ? tx("hevc_m3u") : tx("hevc");
      } else { cauza = self.o.m3u ? tx("decodare_m3u") : tx("decodare"); }
    } else if(detaliu === "HttpStatusCodeInvalid"){
      cauza = cod === 409 ? tx("preluata") : (cod === 404 ? tx("nu_transmite") : txs("refuzat", cod));
    } else if(tip === "NetworkError"){
      reincearca = true;
      cauza = (detaliu === "EarlyEof" || detaliu === "UnrecoverableEarlyEof") ? tx("flux_oprit") :
        (detaliu === "ConnectingTimeout" ? tx("nu_raspunde") : tx("legatura"));
    } else if(tip === "MediaError"){
      if(detaliu === "DecodorWasm"){ cauza = tx("wasm_oprit"); }
      else if(detaliu === "FormatUnsupported" || detaliu === "CodecUnsupported"){ cauza = tx("format"); }
      else if(detaliu === "FormatError"){ cauza = tx("forma"); }
      else if(cod === 4){ cauza = tx("cod4"); }
      else { cauza = tx("redare_browser"); }
    } else {
      cauza = tx("redare");
    }
    self._opresteJucatorul();
    var acum = Date.now();
    self.reconectari = self.reconectari.filter(function(t){ return acum - t < 60000; });
    self.reconectare = reincearca && self.reconectari.length < 3;
    if(self.reconectare){ self.reconectari.push(acum); }
    self.mesaj(cauza, tx("incearca"), function(){ self._dinNou(); });
    self.stare(cauza, true, tehnic);
    // starea sesiunii poate spune mai mult (oprita cu motiv, canal care nu se decripteaza)
    setTimeout(function(){ self._citesteStarea(); }, 800);
  };

  Player.prototype._citestePistele = function(){
    var self = this;
    // pistele fluxului vin cu primul PMT (cateva secunde); subtitrarile sunt ale televizorului
    setTimeout(function(){ if(self.pornit){ self._citesteStarea(); } }, 2500);
    if(!self.peTv){ self._subtitrari(null); return; }
    self._cerere("/api/piste").then(function(d){ if(self.pornit && d.result){ self._subtitrari(d); } }).catch(function(){});
  };

  Player.prototype.alegePista = function(pid){
    var self = this;
    if(!pid){ return; }
    var q = new URLSearchParams(); q.set("pid", pid);
    self._cerere("/api/tv-pista?" + q.toString(), "POST").then(function(d){
      if(!d.result){ self.stare(d.message || tx("pista_rea"), true); return; }
      self.stare(d.message || "");
      self._dupaPista = true;
      self._jucator();
    }).catch(function(){ self.stare(tx("nu_raspunde"), true); });
  };

  Player.prototype.alegeSubtitrarea = function(id){
    var self = this;
    if(!id){ return; }
    var q = new URLSearchParams(); q.set("id", id);
    self._cerere("/api/subtitrare?" + q.toString(), "POST").then(function(d){
      self.stare(d.message || (d.result ? tx("sub_schimbata") : tx("sub_neschimbata")), !d.result);
      setTimeout(function(){ self._citestePistele(); }, 600);
    }).catch(function(){ self.stare(tx("nu_raspunde"), true); });
  };

  Player.prototype.comutaRedarea = function(){
    var v = this.e.video;
    if(!this.jucator){ return; }
    if(this.felJucator === "wasm"){
      // playerul wasm reia singur din direct (ce se vede acum pe televizor)
      var j = this.jucator;
      if(j.paused){ j.play(); } else { j.pause(); }
      return;
    }
    if(v.paused){
      // in direct: la reluare, inapoi la capatul tamponului (ce se vede acum pe televizor)
      try {
        if(v.buffered.length){
          var capat = v.buffered.end(v.buffered.length - 1);
          if(capat - v.currentTime > 3){ v.currentTime = capat - 0.5; }
        }
      } catch(e) {}
      v.play();
    } else {
      v.pause();
    }
  };

  // ------------------------------------------------------------ stratul receptorului
  Player.prototype._stratPornit = function(){
    return this.pornit && this.e.bifa.checked && !this.distrus;
  };
  Player.prototype._strat = function(){
    if(this._stratPornit()){
      this.e.canvas.classList.remove("hp-ascuns");
      this._stratAcum();
    } else {
      clearTimeout(this.ceasStrat); this.ceasStrat = null;
      this.coada = [];
      this.e.canvas.classList.add("hp-ascuns");
      // la repornirea stratului se cere cadrul intreg, nu ramane unul vechi
      this.ctx.clearRect(0, 0, this.e.canvas.width, this.e.canvas.height);
      this.etag = "";
      // fara strat imaginea sta pe tot cadrul (fereastra are rost numai cu ecranul televizorului in jur)
      this._fereastraCoada = undefined;
      this._fereastra(null);
    }
  };
  Player.prototype._stratAcum = function(){
    var self = this;
    clearTimeout(self.ceasStrat);
    self.ceasStrat = null;
    if(!self._stratPornit() || document.hidden || self._stratInLucru){ return; }
    self._stratInLucru = true;
    var latime = Math.round((self.e.cadru.clientWidth || 960) * (window.devicePixelRatio || 1));
    var antete = self._antete();
    if(self.etag){ antete["If-None-Match"] = self.etag; }
    var urmatoarea = 300, fereastra;
    fetch("/api/tv-osd?l=" + latime, {cache: "no-store", credentials: "same-origin", headers: antete}).then(function(r){
      // fereastra imaginii pe televizor: si pe 304 (lista s-a inchis, iar stratul gol nu s-a mai schimbat)
      fereastra = fereastraDin(r.headers.get("x-hds-video"));
      if(r.status === 304){ return null; }
      if(r.status === 503){ urmatoarea = 1000; return null; }
      if(!r.ok){ urmatoarea = 3000; return null; }
      var m = /^(\d+)x(\d+)$/.exec(r.headers.get("x-hds-osd") || "");
      if(!m){ return null; }
      var gol = r.headers.get("x-hds-osd-gol") === "1";
      self.etag = r.headers.get("etag") || "";
      return r.arrayBuffer().then(function(b){ return {l: +m[1], h: +m[2], gol: gol, date: b}; });
    }).then(function(c){
      var noua = fereastra !== undefined && cheieFereastra(fereastra) !== self._fereastraCoada;
      if(c || noua){ self._puneInCoada(c, fereastra); }
      // fereastra si stratul se schimba aproape odata (la inchiderea listei, fereastra vine ~100 ms dupa strat): dupa o
      // fereastra noua sau un cadru nou cu imaginea micsorata, cererea urmatoare vine mai repede
      if(urmatoarea === 300 && (noua || (c && fereastra))){ urmatoarea = 150; }
    }).catch(function(){ urmatoarea = 2000; }).then(function(){
      self._stratInLucru = false;
      if(self._stratPornit() && !document.hidden){
        self.ceasStrat = setTimeout(function(){ self._stratAcum(); }, urmatoarea);
      }
    });
  };
  Player.prototype._intarziere = function(){
    // cat e imaginea in urma: ce are playerul in tampon peste momentul aratat acum (0 pe pauza)
    if(this.felJucator === "wasm" && this.jucator){ return this.jucator.intarziere(); }
    var v = this.e.video;
    try {
      if(v.paused || !v.buffered.length){ return 0; }
      var d = v.buffered.end(v.buffered.length - 1) - v.currentTime;
      return Math.max(0, Math.min(4, d)) * 1000;
    } catch(e) { return 0; }
  };
  // c: cadrul stratului (null = numai fereastra s-a schimbat); fereastra: a televizorului, cand a venit cadrul (undefined =
  // nu se stie). Amandoua se arata cu intarzierea imaginii: lista si imaginea micsorata apar impreuna, ca pe televizor.
  Player.prototype._puneInCoada = function(c, fereastra){
    var self = this;
    var cadru = c ? self._cadruImagine(c) : null;
    if(fereastra !== undefined){ self._fereastraCoada = cheieFereastra(fereastra); }
    var cand = Math.max(self.ultimAfisat, Date.now() + self._intarziere());
    self.ultimAfisat = cand;
    if(self.coada.length >= 8){ self.coada.shift(); }
    var intrare = {cadru: cadru, fereastra: fereastra};
    self.coada.push(intrare);
    setTimeout(function(){
      var i = self.coada.indexOf(intrare);
      if(i < 0 || !self._stratPornit()){ return; }
      self.coada.splice(0, i + 1);
      if(intrare.cadru){ self._deseneaza(intrare.cadru); }
      if(intrare.fereastra !== undefined){ self._fereastra(intrare.fereastra); }
    }, Math.max(0, cand - Date.now()));
  };
  Player.prototype._cadruImagine = function(c){
    if(c.gol){ return {l: c.l, h: c.h, gol: true}; }
    var n = c.l * c.h;
    if(c.date.byteLength < n * 4){ return {l: c.l, h: c.h, gol: true}; }
    var img = this.ctx.createImageData(c.l, c.h);
    var src = new Uint32Array(c.date, 0, n);
    var dst = new Uint32Array(img.data.buffer);
    // pixelii vin B,G,R,A (stratul receptorului); canvas-ul vrea R,G,B,A
    for(var i = 0; i < n; i++){
      var v = src[i];
      dst[i] = (v & 0xff00ff00) | ((v & 0xff) << 16) | ((v >>> 16) & 0xff);
    }
    return {l: c.l, h: c.h, img: img};
  };
  Player.prototype._deseneaza = function(c){
    var cv = this.e.canvas;
    if(cv.width !== c.l || cv.height !== c.h){ cv.width = c.l; cv.height = c.h; }
    if(c.gol){ this.ctx.clearRect(0, 0, cv.width, cv.height); return; }
    this.ctx.putImageData(c.img, 0, 0);
  };
  // imaginea (<video> si canvas-ul playerului wasm) in fereastra televizorului, in procente din cadru; null = tot cadrul.
  // Stratul receptorului ramane pe tot cadrul; in jurul imaginii se vede negrul ecranului. Playerul wasm isi potriveste
  // singur canvas-ul la marimea noua (_marimeSchimbata), <video> pastreaza raportul (object-fit:contain).
  Player.prototype._fereastra = function(f){
    var k = cheieFereastra(f);
    if(k === this._fereastraArata){ return; }
    this._fereastraArata = k;
    var s = f || {x: 0, y: 0, l: 100, h: 100};
    [this.e.video, this.e.imagine].forEach(function(e){
      e.style.left = s.x + "%"; e.style.top = s.y + "%"; e.style.width = s.l + "%"; e.style.height = s.h + "%";
    });
  };

  // ------------------------------------------------------------ ecranul intreg
  Player.prototype._ePlin = function(){
    var f = document.fullscreenElement || document.webkitFullscreenElement;
    return f === this.e.radacina || this.e.radacina.classList.contains("hp-plin-css");
  };
  Player.prototype.comutaEcranul = function(){
    var r = this.e.radacina;
    if(this._ePlin()){
      if(r.classList.contains("hp-plin-css")){ r.classList.remove("hp-plin-css"); this._laEcran(); return; }
      (document.exitFullscreen || document.webkitExitFullscreen).call(document);
      return;
    }
    // tot playerul (imaginea, stratul si bara) pe ecran intreg; unde nu se poate (iPhone), peste toata pagina
    var cere = r.requestFullscreen || r.webkitRequestFullscreen;
    if(cere){
      try {
        var p = cere.call(r);
        if(p && p.catch){ p.catch(function(){ r.classList.add("hp-plin-css"); }); }
      } catch(e) { r.classList.add("hp-plin-css"); }
    } else {
      r.classList.add("hp-plin-css");
    }
    this._laEcran();
  };
  Player.prototype._laEcran = function(){
    this._butoane();
    if(this._ePlin()){ this._arataBara(); try { this.e.radacina.focus({preventScroll: true}); } catch(e) {} }
    else { this.e.radacina.classList.remove("hp-bara-ascunsa"); clearTimeout(this.ceasBara); }
    this.etag = "";   // latimea se schimba: stratul se cere din nou la marimea noua
    this._stratAcum();
  };
  Player.prototype._arataBara = function(){
    var self = this, r = self.e.radacina;
    r.classList.remove("hp-bara-ascunsa");
    clearTimeout(self.ceasBara);
    if(!self._ePlin()){ return; }
    self.ceasBara = setTimeout(function(){
      var activ = document.activeElement;
      if(activ && activ.tagName === "SELECT" && self.e.bara.contains(activ)){ self._arataBara(); return; }
      if(self._ePlin()){ r.classList.add("hp-bara-ascunsa"); }
    }, 3000);
  };

  // ------------------------------------------------------------ playlistul pentru playerele externe
  Player.prototype.descarcaM3u = function(){
    var self = this;
    if(!self.ref){ self.stare(tx("alege_canal"), true); return; }
    var q = new URLSearchParams(); q.set("ref", self.ref);
    var st = self.ultimaStare;
    if(self.jucator && st && st.sesiuni_max === 1){
      // receptorul trimite un singur flux odata: imaginea din pagina se opreste, ca VLC sa poata porni
      self._opresteJucatorul();
      self.mesaj(tx("extern"), tx("reia_aici"), function(){ self._jucator(); self.mesaj(""); });
    }
    descarcaPlaylist(q, self.o.csrf).then(function(nume){
      self.stare(txs("m3u_gata", nume));
    }).catch(function(e){ self.stare(e.message || tx("m3u_rau"), true); });
  };

  function descarcaPlaylist(corp, csrf){
    var optiuni = {method: "POST", cache: "no-store", credentials: "same-origin",
      headers: {"Content-Type": "application/x-www-form-urlencoded"}, body: corp.toString()};
    if(csrf){ optiuni.headers["X-HDS-CSRF"] = csrf; }
    return fetch("/api/tv-m3u", optiuni).then(function(r){
      if(!r.ok){
        return r.json().catch(function(){ return {}; }).then(function(d){ throw new Error(d.message || txs("m3u_http", r.status)); });
      }
      var m = /filename="?([A-Za-z0-9._-]+)"?/.exec(r.headers.get("content-disposition") || "");
      var nume = m ? m[1] : "hdsatelit.m3u";
      return r.blob().then(function(b){
        var url = URL.createObjectURL(b);
        var a = document.createElement("a");
        a.href = url; a.download = nume; a.style.display = "none";
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function(){ URL.revokeObjectURL(url); }, 60000);
        return nume;
      });
    });
  }

  window.HdsPlayer = {
    creeaza: function(gazda, optiuni){ return new Player(gazda, optiuni); },
    descarcaPlaylist: descarcaPlaylist,
    numeLimba: numeLimba,
    poate: poate,
    // pentru probe: textele, tastele de zap si cheia referintelor
    TEXTE: TEXTE,
    txs: txs,
    TASTE_ZAP: TASTE_ZAP,
    refCheie: refCheie,
    fereastraDin: fereastraDin,
    tx: tx
  };
})();
