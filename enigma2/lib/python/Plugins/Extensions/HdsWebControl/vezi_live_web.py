# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# vezi_live_web.py: "Vezi live" si playlisturile M3U din paginile cu liste de canale ale interfetei web (HdsWebControl):
# /canale (canale_web.py) si /cautare (cautare_web.py). Acelasi cod in amandoua, pus in pagina la servire (inPagina):
#   __LIVE_STIL__    fereastra (dialogul) si butoanele "Vezi live" / "Ghid" ale randurilor
#   __LIVE_DIALOG__  fereastra "Vezi live", copil direct al paginii (dupa </main>), peste antetul si barele cadrului
#   __LIVE_JS__      liveDeschide (playerul comun /tv/player.js, HdsPlayer), liveInchide, liveButon, liveDescarca
#   __LIVE_TEXTE__   textele scriptului (TL), traduse in limba interfetei; __L_<cheie>__ textele din HTML
#
# Playerul e cel din panou si din /tv: verifica intai canalul (/api/tv-verifica) si, daca nu se poate reda acum in
# browser, arata motivul fara sa porneasca nimic; "Descarca playlist (M3U)" (al canalului) ramane sub imagine. Un canal
# pe care transmisia nu-l poate lua fara televizor (receptor cu motor sau cu un singur tuner de satelit, alta
# frecventa) muta televizorul pe el prin functia paginii (mutaTv: /api/canale-porneste in /canale, /api/zap in
# /cautare), apoi imaginea urmeaza televizorul; canalul de pe televizor urmeaza si el televizorul. Mesajele pentru
# canalele criptate si pentru eroarea de decodare sunt ale playerului.
# Playlistul unei liste (liveDescarca): referintele stranse de pagina, POST /api/tv-m3u (tv_web.py, acces_extern.py),
# cel mult MAX_EXPORT canale; adresele au cheia playlistului, nu jetonul API.
#
# Pagina da: CFG (csrf, jeton), $(id), mesaj(text, eroare) si politica continutului paginii /tv (tv_web.CSP_TV) cu
# <script src="/tv/player.js">. Fisierul nu importa nimic din enigma2: pe PC textele raman in romana.

import html
import json

# cel mult cate canale primeste receptorul intr-un playlist (acces_extern.MAX_CANALE)
MAX_EXPORT = 2000


def N_(text):
	"""marcheaza textul pentru xgettext (po/Makefile.am --keyword=N_); traducerea se face la folosire, cu _t"""
	return text


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


TEXTE = {
	"vezi_live": N_("Vezi live"),
	"vezi_live_canal": N_("Vezi live canalul %s"),
	"titlu": N_("Vezi live: %s"),
	"inchide": N_("Închide"),
	"fara_player": N_("Playerul nu s-a încărcat de pe receptor. Reîncarcă pagina."),
	"exporta": N_("Exportă playlist (M3U)"),
	"se_strange": N_("Se strânge lista..."),
	"descarcat": N_("Playlistul s-a descărcat (%s). Deschide-l într-un player din casă."),
	"nu_s_a_facut": N_("Playlistul nu s-a putut face."),
	"fara_canale": N_("Lista nu are niciun canal."),
}


def texte():
	"""{cheie: textul tradus in limba interfetei}"""
	return dict((k, _t(v)) for k, v in TEXTE.items())


def texteJs():
	"""Textele scriptului, ca JSON sigur in <script>."""
	text = json.dumps(texte(), ensure_ascii=False)
	return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def inPagina(pagina):
	"""Bucatile comune si textele __L_<cheie>__, traduse in limba interfetei. Se cheama inaintea datelor omului
	(configuratia paginii), ca un nume de browser sa nu poata fi luat drept loc de text."""
	pagina = (pagina.replace("__LIVE_STIL__", STIL).replace("__LIVE_DIALOG__", DIALOG).replace("__LIVE_JS__", JS)
		.replace("__LIVE_TEXTE__", texteJs()).replace("__LIVE_MAX__", str(int(MAX_EXPORT))))
	for k, v in texte().items():
		pagina = pagina.replace("__L_%s__" % k, html.escape(v, quote=True))
	return pagina


# peste antetul cadrului (50), bara listei (40), meniul (55, 60) si bara de jos de pe telefon (52): altfel titlul si X
# stau sub antet si X nu se poate apasa pe telefon
STIL = """
.dialog-live{position:fixed;inset:0;z-index:1000;background:rgba(5,8,16,.78);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 12px;}
.dialog-live.ascuns{display:none !important;}
.dialog-cutie{width:100%;max-width:980px;box-sizing:border-box;background:#10162a;border:1px solid rgba(55,78,161,.5);border-radius:12px;box-shadow:0 16px 40px -8px rgba(0,0,0,.75);padding:12px 14px 14px;}
.dialog-antet{display:flex;align-items:center;gap:12px;margin:0 0 10px;}
.dialog-antet h2{flex:1;font-size:1.05rem;margin:0;min-width:0;overflow-wrap:anywhere;}
.dialog-antet button{min-width:44px;min-height:44px;border-radius:8px;border:1px solid var(--bordura);background:#161f3b;color:var(--text);font:inherit;font-size:1.2rem;cursor:pointer;}
.ghid{display:flex;align-items:center;justify-content:center;min-width:64px;min-height:44px;padding:0 12px;border:1px solid var(--bordura);border-radius:10px;background:#242a33;color:var(--text);text-decoration:none;}
.ghid:focus-visible{outline:2px solid #7fb8ff;outline-offset:2px;}
button.ghid{font:inherit;cursor:pointer;white-space:nowrap;}
button.ghid.nu-merge{color:var(--text-slab);}
"""

DIALOG = """<div id="dialogLive" class="dialog-live ascuns" role="dialog" aria-modal="true" aria-labelledby="dialogTitlu">
  <div class="dialog-cutie">
    <div class="dialog-antet"><h2 id="dialogTitlu">__L_vezi_live__</h2><button type="button" id="dialogInchide" aria-label="__L_inchide__">&#10005;</button></div>
    <div id="dialogPlayer"></div>
  </div>
</div>"""

JS = """
var TL = __LIVE_TEXTE__, MAX_EXPORT = __LIVE_MAX__;
var LIVE = {player: null, buton: null, o: {}};
// fereastra "Vezi live" a canalului r ({ref, nume}); o.mutaTv(ref) -> Promise({result, message}): televizorul trece pe
// canal (pagina il porneste cum porneste orice canal din lista ei)
function liveDeschide(r, buton, o){
  LIVE.o = o || {};
  if(!window.HdsPlayer){ mesaj(TL.fara_player, true); return; }
  LIVE.buton = buton;
  $("dialogTitlu").textContent = TL.titlu.replace("%s", r.nume || "");
  $("dialogLive").classList.remove("ascuns");
  if(!LIVE.player){
    LIVE.player = HdsPlayer.creeaza($("dialogPlayer"), {csrf: CFG.csrf, jeton: CFG.jeton, m3u: true, textOprire: TL.inchide,
      // canalul de pe televizor (sau cel pe care a trecut televizorul) urmeaza televizorul; titlul spune canalul de acum
      urmeazaPeTv: true, mutaTv: function(ref){ return LIVE.o.mutaTv ? LIVE.o.mutaTv(ref) : Promise.resolve(null); },
      laCanal: function(nume){ $("dialogTitlu").textContent = TL.titlu.replace("%s", nume || ""); },
      laOprire: function(){ liveInchide(false); },
      laMotiv: function(motiv){
        // canalul nu se poate reda acum: butonul randului arata motivul, fara alta pornire
        if(LIVE.buton){ LIVE.buton.classList.add("nu-merge"); LIVE.buton.title = motiv || ""; }
      }});
  }
  LIVE.player.porneste(r.ref, r.nume || "");
  $("dialogInchide").focus();
}
function liveInchide(opreste){
  if(LIVE.player && opreste !== false){ LIVE.player.opreste(true); }
  $("dialogLive").classList.add("ascuns");
  if(LIVE.buton){ try { LIVE.buton.focus(); } catch(e) {} }
}
// butonul "Vezi live" al unui rand
function liveButon(r, o){
  var v = document.createElement("button");
  v.type = "button"; v.className = "ghid"; v.textContent = TL.vezi_live;
  v.setAttribute("aria-label", TL.vezi_live_canal.replace("%s", r.nume || ""));
  v.addEventListener("click", function(){ liveDeschide(r, v, o); });
  return v;
}
// playlistul unei liste: refs (referintele, cel mult MAX_EXPORT), grupul si numele fisierului; numar = cate canale, ca
// text al receptorului; nota = ce se spune in plus (lista taiata)
function liveDescarca(refs, grup, nume, numar, nota){
  if(!window.HdsPlayer){ return Promise.reject(new Error(TL.fara_player)); }
  if(!refs.length){ return Promise.reject(new Error(TL.fara_canale)); }
  var corp = new URLSearchParams();
  corp.set("canale", refs.slice(0, MAX_EXPORT).join(","));
  corp.set("grup", grup || "HD Satelit");
  corp.set("nume", nume || "canale");
  return HdsPlayer.descarcaPlaylist(corp, CFG.csrf).then(function(fisier){
    mesaj(TL.descarcat.replace("%s", [fisier, numar].filter(Boolean).join(", ")) + (nota ? " " + nota : ""));
    return fisier;
  });
}
$("dialogInchide").addEventListener("click", function(){ liveInchide(true); });
$("dialogLive").addEventListener("click", function(e){ if(e.target === $("dialogLive")){ liveInchide(true); } });
document.addEventListener("keydown", function(e){
  if(e.key === "Escape" && !$("dialogLive").classList.contains("ascuns") && !document.fullscreenElement){ liveInchide(true); }
});
"""
