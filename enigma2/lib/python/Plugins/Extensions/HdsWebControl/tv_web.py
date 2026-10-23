# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# tv_web.py: TV in browser (pagina /tv) si perechea web a ecranului "Transmisie in retea" (Meniu > Setari > Retea &
# Conexiuni, Screens/HdsTransmisie.py). Logica sesiunilor, prioritatea televizorului si paza memoriei:
# Components/HdsTransmisie.py.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi cookie-ul browserului asociat sau browserul "liber" din
# casa; ce schimba ceva cere POST, aceeasi origine si antetul X-HDS-CSRF al paginii):
#   GET  /api/tv-stare                         sesiunile, setarile, memoria driverului, sesiunea acestui browser
#   GET  /api/tv-canale?hevc=&ac3=&wasm=       canalele de pe frecventa televizorului si din lista lui, cu ce merge
#   POST /api/tv-porneste?ref=&hevc=0|1&ac3=0|1&wasm=0|1  porneste (sau reia) transmisia acestui browser
#   POST /api/tv-opreste?id=                   opreste o transmisie (fara id: a acestui browser)
#   POST /api/tv-seteaza?permis=0|1&standby=0|1&sesiuni_max=1|2&asteptare=10|20|60
#   GET  /api/tv-flux                          TS-ul sesiunii acestui browser (video/mp2t), cu antetul X-HDS-CSRF
#   GET  /tv                                   pagina; /tv/mpegts.js si /tv/mpegts-licenta.txt (biblioteca, Apache-2.0)
#   GET  /tv/player.js                         playerul comun (panou, /tv, /canale): imaginea, stratul receptorului
#                                              peste ea, butoanele sub ea, ecranul intreg
#   GET  /tv/hds-player.js, /tv/hds-worker.js  playerul wasm al canalelor MPEG-2 / MPEG-1 (cod propriu, GPL-2.0-only)
#   GET  /tv/hds-sunet.js                       sunetul AC-3 decodat in pagina (acelasi decodor), dat lui mpegts.js ca FLAC
#   GET  /tv/tv-wasm/<nume>                    decodorul lui (hdsdec.js, hdsdec.wasm: FFmpeg 8.1.3, LGPL-2.1-or-later)
#                                              si licentele lui (ffmpeg-licenta.txt si celelalte din FISIERE_WASM)
#   GET  /api/tv-osd?l=960                     stratul grafic al receptorului (osd_strat.py): BGRA brut, gzip, cu ETag;
#                                              304 cand nu s-a schimbat. Ca fluxul: numai din browser, cu antetul CSRF.
#                                              Antetul x-hds-video (si pe 304): fereastra imaginii pe televizor, "x,y,l,h"
#                                              in procente din ecran ("0,0,100,100" = ecran intreg; lista de canale o
#                                              micsoreaza), ca pagina sa puna imaginea din browser in acelasi loc
#   POST /api/tv-pista?pid=                    pista audio a fluxului acestui browser (se aplica la reconectare)
#   GET  /api/tv-verifica?ref=&hevc=&ac3=&wasm=  merge canalul acum in browser? (fara sa porneasca nimic) si in VLC?
#                                              muta_tv: televizorul poate trece pe canal ("Vezi live", motor / un tuner)
#   GET  /api/tv-urmeaza?ref=&standby=0|1      cererea lunga a paginii care urmeaza televizorul: raspunde cand
#                                              televizorul nu mai e pe `ref` / `standby` sau dupa URMEAZA_S
#   POST /api/tv-m3u  ref= sau canale=r1,r2,..&grup=&nume=  playlist M3U pentru playerele externe (acces_extern.py)
#   GET  /api/tv-acces                         adresele date playerelor externe (fara chei); POST /api/tv-acces-revoca?id=
#   GET  /tv-extern/<cheie>/<canal>.ts         fluxul pentru VLC / Kodi: numai din reteaua locala, numai canalele cheii
#   GET  /tv-extern/<cheie>/canale.m3u | ghid.xml | sigla/<nume>.png   aparatele din casa (aparate_web.py): playlistul
#                                              care nu se schimba, ghidul XMLTV si siglele, numai cu cheia unui aparat
#   POST /api/tv-aparat-adauga?nume=&sursa=..   cheia unui aparat (adresele se dau o singura data); POST
#        /api/tv-aparat-redenumeste?id=&nume=; /api/tv-acces da si aparatele, /api/tv-acces-revoca le revoca
#
# MPEG-2 IN BROWSER: pagina trimite wasm=1 cand browserul are playerul wasm (WebAssembly,
# WebGL, Worker); atunci potrivire() lasa canalele cu imagine MPEG-2 / MPEG-1, iar sesiunea pastreaza in PMT sunetul
# MP2 / MP3 sau AC-3 pe care decodorul wasm il are (RescrierePsi, wasm). CSP_TV are 'wasm-unsafe-eval' (fara el
# Chrome refuza compilarea decodorului); decodorul se serveste ca application/wasm, cu cache o zi (adresa lui are
# versiunea, ?v=, pusa de hds-player.js si de hds-sunet.js).
# AC-3 IN BROWSER: la imaginea H.264 / HEVC, pagina trimite ac3=1 cand poate reda AC-3, nativ (MediaSource) sau prin
# decodorul wasm (hds-sunet.js: decodorul ac3 pe firul paginii, sunetul dat lui MediaSource ca FLAC); RescrierePsi
# lasa atunci pista AC-3 in PMT. Cu wasm=1 si ac3=1 sunetul AC-3 merge sigur, deci potrivire() nu mai avertizeaza.
#
# FERESTRELE: playerul trimite antetul X-HDS-Fereastra (un id aleator pe fila). O sesiune folosita de alta
# fereastra a aceluiasi browser nu se mai inlocuieste pe tacute: pornirea raspunde cu "alta_fereastra" si pagina
# intreaba; cu preia=1 transmisia trece la fereastra noua. Fluxul cerut de alta fereastra decat a sesiunii: 409.
# Fluxul si pornirea merg numai dintr-un browser (cookie sau browserul "liber" + antetul CSRF), niciodata cu ?token=:
# nicio cheie in adresa. Fluxul nu raspunde unei pagini straine: un <video src> nu poate pune antetul, iar un fetch
# strain cu antet cere CORS, pe care ruta nu il da.
#
# CANALELE CRIPTATE (Components/HdsTransmisie.py, CANALELE CRIPTATE): cu setarea ascunsa criptate pe Nu
# (implicit) pornirea raspunde TEXT_CRIPTAT. Cu Da, o pornire care trebuie sa astepte (CRIPTAT_ASTEAPTA) raspunde paginii
# {"asteapta": true, "secunde": n} si player.js intreaba din nou singur, numai pentru canalul ales ultimul; playerele
# externe asteapta in cerere (raspunsul amanat, cel mult EXTERN_ASTEPTARE_S), iar cand asteptarea ar fi mai lunga sau
# expira primesc 503 cu Retry-After.
#
# COMUTARILE RAPIDE ALE PLAYERELOR EXTERNE: un player care sare repede intre canale
# (PREA_REPEDE, pauza dintre doua porniri) nu mai primeste 503 la prima incercare: cererea asteapta tot asa, cel mult
# EXTERN_REPEDE_S, si porneste cand trece pauza; o cerere noua a aceluiasi player o inlocuieste (ultima castiga). Regulile
# managerului raman aceleasi (o sesiune pe cheie, criptatele serializate, numai frecventa televizorului pe receptoarele
# cu motor). Sesiunea unui aparat din casa poarta numele lui (lista transmisiilor, pe televizor si in /tv).
#
# URMEAZA TELEVIZORUL (Components/HdsTransmisie.py, URMEAZA TELEVIZORUL): /api/tv-urmeaza tine cererea deschisa pana
# cand extensia de zap (sau ceasul, la standby si la termen) o anunta; pornirea cu urmeaza=1 ia canalul de ACUM al
# televizorului. Opririle au cod in starea paginii (oprita.cod). "Vezi live" pe un canal de pe alta frecventa, pe un
# receptor cu motor sau cu un singur tuner de satelit: verifica() raspunde muta_tv (televizorul poate trece pe el; zap-ul
# il face pagina canalelor) sau, cand o inregistrare tine tunerul, motivul. Playerele externe nu muta televizorul.
#
# DECRIPTAREA (Components/HdsTransmisie.py, DECRIPTAREA): un player extern primeste fluxul unui canal criptat abia cand
# imaginea iese clara; cand camul nu-l decripteaza, 403 cu textul; cand inca incearca dupa EXTERN_ASTEPTARE_S, 503 cu
# Retry-After. Pagina vede starea in a_mea.decriptare.
#
# TEXTELE PLAYERULUI: player.js are textele lui noi in romana (TEXTE); la servire, in locul semnului SEMN_TEXTE se pun
# traducerile lor in limba meniurilor (TEXTE_PLAYER, aceleasi chei).
#
# AVERTIZAREA SUNETULUI: baza de canale poate avea alte piste decat are canalul acum (Das Erste HD: numai AC-3 in baza,
# trei piste MP2 si una AC-3 in PMT), deci pornirea da numai avertizarile imaginii (MPEG-2 decodat in browser, formatul
# necunoscut). Cea despre sunet vine din PMT-ul fluxului: /api/tv-stare, a_mea.avertizare (HdsTransmisie.avertizarePmt;
# null cat PMT-ul nu s-a citit), iar player.js reface randul de stare cand se schimba. Lista pistelor (a_mea.piste) are
# limba, felul si rolul (descriere audio, vorbire clara), tot din PMT.
#
# FLUXUL: dupa antetul HTTP (scris de noi, Connection: close, fara lungime), soclul trece la firul sesiunii
# (HdsTransmisie): Twisted nu mai citeste pe el (pauseProducing; oricum nu citeste cat o cerere e in lucru) si nu
# scrie nimic; firul primeste o copie a descriptorului (os.dup) si scrie TS-ul (cu PAT-ul rescris). Cand browserul
# pleaca sau sesiunea se opreste, firul isi inchide copia, iar pe firul principal Twisted inchide legatura
# (loseConnection).
#
# FIRUL: render_* ruleaza pe firul enigma2; lista de canale e de cel mult MAX_CANALE randuri. Fisierul nu importa
# nimic din enigma2 la incarcare: probele de pe PC dau managerul lor (M) si functiile de enigma2.

import os

MAX_CANALE = 400
# canalele criptate cu setarea ascunsa criptate pe Nu (implicit; Components/HdsTransmisie.py, CRIPTAT_OPRIT)
def N_(text):
	"""marcheaza textul pentru xgettext (po/Makefile.am --keyword=N_); traducerea se face la folosire, cu _t"""
	return text


TEXT_CRIPTAT = N_("Canalele criptate nu se pot vedea încă în browser sau în alte playere. Merg canalele necriptate (FTA).")
EXTERN_ASTEPTARE_S = 30        # cat ramane deschisa cererea unui player extern care asteapta o pornire criptata
URMEAZA_S = 25                 # cererea lunga a paginii care urmeaza televizorul (HdsTransmisie.URMEAZA_S)
REF_MAXIM = 512                # cat se citeste din ref= in cererea lunga (o cale de fisier pe televizor poate fi lunga)
# textele de ecran ale playerului (player.js, TEXTE: aceleasi chei si aceeasi romana), traduse la servire
TEXTE_PLAYER = {
	"schimba": N_("Se schimbă canalul..."),
	"muta": N_("Televizorul trece pe %s..."),
	"antena": N_("Antena se rotește..."),
	"decriptare": N_("Se decriptează..."),
	"nedecriptat": N_("Canalul e criptat și receptorul nu-l poate decripta acum (fără card sau fără drepturi pentru el)."),
	"decodare": N_("Browserul nu poate reda imaginea acestui canal. Încearcă din nou."),
	"decodare_m3u": N_("Browserul nu poate reda imaginea acestui canal. Încearcă din nou sau deschide-l într-un player din casă cu playlistul de mai jos."),
	"sunet": N_("Browserul nu poate reda sunetul acestui canal. Încearcă din nou."),
	"sunet_m3u": N_("Browserul nu poate reda sunetul acestui canal. Încearcă din nou sau deschide-l într-un player din casă cu playlistul de mai jos."),
	"hevc": N_("Acest browser nu poate decoda imaginea HEVC (H.265) a acestui canal, de pildă 4K pe 10 biți. Încearcă alt browser sau un player din casă."),
	"hevc_m3u": N_("Acest browser nu poate decoda imaginea HEVC (H.265) a acestui canal, de pildă 4K pe 10 biți. Deschide-l într-un player din casă cu playlistul de mai jos."),
	"detalii": N_("Detalii"),
	"din_nou": N_("Pornește din nou"),
	"incearca": N_("Încearcă din nou"),
	"nu_a_trecut": N_("Televizorul nu a trecut pe acest canal."),
	"standby": N_("Receptorul e în standby."),
	"descriere_audio": N_("descriere audio"),
	"vorbire_clara": N_("vorbire clară"),
	# mesajele paginii: "Imaginea merge." numai cat vin cadre adevarate; mesajul pazei cadrelor (player.js, paza cadrelor)
	"imaginea_merge": N_("Imaginea merge."),
	"fara_imagine": N_("Canalul nu trimite imagine acum."),
	# fara PMT-ul fluxului dupa player.js FARA_PMT_MS (HdsTransmisie, PMT-UL LIPSA)
	"fara_pmt": N_("Canalul nu trimite descrierea pistelor (imagine și sunet), deci browserul nu știe ce să redea. Încearcă din nou."),
	# numele limbilor pistelor de sunet (LIMBI: codul din PMT -> cheia)
	"l_deu": N_("Germană"),
	"l_eng": N_("Engleză"),
	"l_ron": N_("Română"),
	"l_fra": N_("Franceză"),
	"l_ita": N_("Italiană"),
	"l_spa": N_("Spaniolă"),
	"l_hun": N_("Maghiară"),
	"l_pol": N_("Poloneză"),
	"l_ces": N_("Cehă"),
	"l_tur": N_("Turcă"),
	"l_rus": N_("Rusă"),
	"l_ukr": N_("Ucraineană"),
	"l_nld": N_("Olandeză"),
	"l_por": N_("Portugheză"),
	"l_bul": N_("Bulgară"),
	"l_srp": N_("Sârbă"),
	"l_hrv": N_("Croată"),
	"l_ell": N_("Greacă"),
	"l_qaa": N_("Limba originală"),
	"l_mis": N_("Altă limbă"),
	"l_und": N_("Nedefinită"),
	"l_nar": N_("Descriere audio"),
	# scripturile care nu s-au incarcat
	"e_mpegts": N_("Biblioteca de redare nu s-a încărcat de pe receptor."),
	"e_wasm": N_("Decodorul MPEG-2 nu s-a încărcat de pe receptor."),
	"e_sunet": N_("Decodorul de sunet nu s-a încărcat de pe receptor."),
	# pistele si subtitrarea
	"sunet_pista": N_("Sunet: %s"),
	"pista_nr": N_("pista %s"),
	"nu_merge": N_("nu merge în browser"),
	"sunet_canal": N_("Sunet: pista canalului"),
	"sub_numai_tv": N_("Subtitrare: numai pe canalul televizorului"),
	"sub_fara": N_("Subtitrare: -"),
	"sub_oprita": N_("Subtitrare: oprită"),
	"sub_aleasa": N_("Subtitrare: %s"),
	# bara de sub imagine (butoanele, titlurile si numele lor pentru cititoarele de ecran)
	"imaginea_canalului": N_("Imaginea canalului"),
	"pasi": N_("Pașii decriptării"),
	"comenzi": N_("Comenzile imaginii"),
	"volum": N_("Volumul"),
	"pista_audio": N_("Pista audio"),
	"pista_titlu": N_("Pista audio a imaginii din browser"),
	"subtitrarea": N_("Subtitrarea"),
	"sub_titlu": N_("Subtitrarea o desenează receptorul: se schimbă și pe televizor"),
	"afisaj": N_("Afișajul receptorului"),
	"afisaj_titlu": N_("Meniurile, bara de informații, subtitrarea și ghidul receptorului, peste imagine"),
	"afisaj_alt": N_("Afișajul e al canalului de pe televizor, nu al acestui canal"),
	"opreste": N_("Oprește"),
	"reda": N_("Redă"),
	"pauza": N_("Pune pauză"),
	"sunet_pornit": N_("Pornește sunetul"),
	"sunet_oprit": N_("Oprește sunetul"),
	"iesire": N_("Ieșire"),
	"ecran_intreg": N_("Ecran întreg"),
	"iesire_ecran": N_("Ieșire din ecranul întreg"),
	"m3u": N_("Descarcă playlist (M3U)"),
	"m3u_nota": N_("pentru un player din casă; acolo merg toate pistele de sunet"),
	# mesajele pornirii si ale transmisiei
	"se_porneste": N_("Se pornește..."),
	"acum": N_("Acum: %s"),
	"deconectat": N_("Browserul nu mai e conectat la receptor."),
	"raspuns_http": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"nu_raspunde": N_("Receptorul nu răspunde."),
	"jeton": N_("Imaginea live merge numai cu browserul conectat: deschide pagina fără cheia din adresă."),
	"fara_mse": N_("Acest browser nu poate reda fluxul (îi lipsește MediaSource). Încearcă Chrome, Edge, Firefox sau Safari nou."),
	"oprita_setari": N_("Transmisia în browser e oprită din setări (Rețea și internet, Transmisie în rețea)."),
	"tv_gol": N_("Pe televizor nu merge acum niciun canal."),
	"neverificat": N_("Canalul nu se poate verifica."),
	"nu_merge_acum": N_("Canalul nu se poate reda acum în browser."),
	"nu_a_pornit": N_("Imaginea live nu a pornit."),
	"preia_aici": N_("Preia aici"),
	"apasa_reda": N_("Apasă ca să pornească redarea."),
	"fara_sunet": N_("Browserul a pornit imaginea fără sunet. Apasă ca să pornească și sunetul."),
	"oprita": N_("Transmisia s-a oprit."),
	"preluata": N_("Transmisia a fost preluată de altă fereastră."),
	"preia_inapoi": N_("Preia înapoi"),
	"mpeg2": N_("Imaginea acestui canal e MPEG-2: o decodează browserul."),
	# erorile fluxului (cauza pe scurt; detaliul tehnic sta sub Detalii)
	"nu_transmite": N_("Receptorul nu mai transmite spre acest browser."),
	"refuzat": N_("Receptorul a refuzat fluxul (HTTP %s)."),
	"flux_oprit": N_("Fluxul s-a oprit de la receptor."),
	"legatura": N_("Legătura cu receptorul s-a întrerupt."),
	"wasm_oprit": N_("Decodorul MPEG-2 din browser nu a pornit."),
	"format": N_("Browserul nu cunoaște formatul imaginii sau al sunetului."),
	"forma": N_("Fluxul are o formă pe care playerul nu o înțelege."),
	"cod4": N_("Browserul nu a putut deschide imaginea (n-a primit date pe care să le înțeleagă)."),
	"redare_browser": N_("Redarea s-a oprit în browser."),
	"redare": N_("Redarea s-a oprit."),
	# alegerile din bara si playlistul
	"pista_rea": N_("Pista nu s-a putut alege."),
	"sub_schimbata": N_("Subtitrarea s-a schimbat (și pe televizor)."),
	"sub_neschimbata": N_("Subtitrarea nu s-a putut schimba."),
	"alege_canal": N_("Alege întâi un canal."),
	"extern": N_("Imaginea din pagină s-a oprit, ca să se poată deschide în playerul extern."),
	"reia_aici": N_("Reia aici"),
	"m3u_gata": N_("Playlistul s-a descărcat (%s). Deschide-l într-un player din casă."),
	"m3u_rau": N_("Playlistul nu s-a putut descărca."),
	"m3u_http": N_("Playlistul nu s-a putut face (HTTP %s)."),
}
SEMN_TEXTE = b"/*__TEXTE__*/null"
EXTERN_REPEDE_S = 6            # cat asteapta cererea unui player extern care a schimbat canalul prea repede
TERMEN_TCP_S = 30
ANTET_FLUX = (b"HTTP/1.1 200 OK\r\n"
	b"Content-Type: video/mp2t\r\n"
	b"Cache-Control: no-store\r\n"
	b"X-Content-Type-Options: nosniff\r\n"
	b"Connection: close\r\n"
	b"Server: HDSatelit\r\n\r\n")
CSP_TV = (b"default-src 'self'; img-src 'self'; style-src 'unsafe-inline'; "
	b"script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; media-src 'self' blob:; connect-src 'self'; "
	b"worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
FISIER_JS = "mpegts.js"
FISIER_LICENTA = "mpegts-licenta.txt"
FISIER_PLAYER = "player.js"
FISIER_PLAYER_WASM = "hds-player.js"
FISIER_WORKER = "hds-worker.js"
FISIER_SUNET = "hds-sunet.js"
DOSAR_WASM = "tv-wasm"
# ce se serveste din tv-wasm/ (orice alt nume: 404): decodorul si textele licentelor lui
FISIERE_WASM = ("hdsdec.js", "hdsdec.wasm", "ffmpeg-licenta.txt", "emscripten-licenta.txt", "musl-licenta.txt",
	"compiler-rt-licenta.txt", "dlmalloc-licenta.txt")
TIPURI_TV = (1, 0x11, 0x16, 0x19, 0x1F, 0x86, 0xC3)
TIPURI_RADIO = (2, 0x0A)


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _T(H=None):
	if H is not None:
		return H
	from Components import HdsTransmisie
	return HdsTransmisie


def _m(H=None, M=None):
	if M is not None:
		return M
	return _T(H).manager()


def argumente(request, chei=("ref", "id", "hevc", "ac3", "wasm", "permis", "standby", "sesiuni_max", "asteptare", "preia",
		"pid", "l", "grup", "nume", "urmeaza")):
	"""Argumentele cererii ca text scurt: {cheie: text}, numai cheile stiute, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:12]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in chei:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:64].strip()
	return rez


def cineDinBrowser(browser, adresa):
	"""Cheia browserului pentru sesiuni: asocierea lui sau, pentru browserul "liber" din casa, adresa."""
	if not browser:
		return None
	if browser.get("id"):
		return "b:%s" % browser["id"]
	return "l:%s" % (adresa or browser.get("adresa") or "")


def numeCanal(ref):
	try:
		from enigma import eServiceCenter, eServiceReference
		r = eServiceReference(ref)
		info = eServiceCenter.getInstance().info(r)
		nume = info.getName(r) if info else ""
		return (nume or "").replace("\xc2\x86", "").replace("\xc2\x87", "").replace("\x86", "").replace("\x87", "")
	except Exception:
		return ""


# ---------------------------------------------------------------- starea si canalele

def stare(cine, H=None, M=None, ref_tv=None, nume_tv=None):
	"""Pentru GET /api/tv-stare."""
	T = _T(H)
	m = _m(H, M)
	d = m.stare()
	a_mea = m.sesiunePentru(cine) if cine else None
	oprita = m.oprite.get(cine) if cine else None
	if ref_tv is None:
		ref_tv = T.refTv()
	d.update({
		"result": True,
		"a_mea": a_mea.descriere(T.monoton()) if a_mea is not None else None,
		"oprita": {"motiv": oprita[0], "ora": int(oprita[1]), "cod": oprita[2] if len(oprita) > 2 else None}
			if (oprita and a_mea is None) else None,
		"tv": {"ref": ref_tv or "", "nume": nume_tv if nume_tv is not None else (numeCanal(ref_tv) if ref_tv else "")},
		"asteptari": [[s, T.textDurata(s)] for s in T.ASTEPTARI_PERMISE_S],
		"in_standby": bool(T.inStandby()),
	})
	return d


def _continut(ref):
	from enigma import eServiceCenter, eServiceReference
	lista = eServiceCenter.getInstance().list(eServiceReference(ref))
	if lista is None:
		return []
	return lista.getContent("SN", False) or []


def _radacinaTv():
	try:
		from Screens.InfoBar import InfoBar
		sl = getattr(InfoBar.instance, "servicelist", None) if InfoBar.instance is not None else None
		root = sl.getRoot() if sl is not None else None
		return root.toString() if root is not None else None
	except Exception:
		return None


def interogareTransponder(ref, T):
	tp = T.transponder(ref)
	if tp is None:
		return None
	return "1:7:1:0:0:0:0:0:0:0:(channelID == %08x%04x%04x) ORDER BY name" % tp


def canale(H=None, M=None, ref_tv=None, continut=None, radacina=None, hevc=False, ac3=False, serviciu=None, baza=None,
		wasm=False):
	"""Pentru GET /api/tv-canale: intai canalele de pe frecventa televizorului (merg mereu, tunerul e impartit),
	apoi cele din lista de pe televizor, fiecare cu merge acum sau motivul. Codecul numai la cele care merg.
	`wasm` = browserul are playerul wasm (canalele MPEG-2 merg)."""
	T = _T(H)
	m = _m(H, M)
	continut = continut or _continut
	if ref_tv is None:
		ref_tv = T.refTv()
	rez, vazute = [], set()

	def adauga(ref, nume, sursa):
		curata = T.refCurata(ref)
		if curata is None or curata in vazute or len(rez) >= MAX_CANALE:
			return
		tip = T.campuriRef(curata)[0]
		if tip not in TIPURI_TV and tip not in TIPURI_RADIO:
			return
		vazute.add(curata)
		rez.append({"ref": curata, "nume": nume or curata, "radio": tip in TIPURI_RADIO, "sursa": sursa})

	if ref_tv:
		q = interogareTransponder(ref_tv, T)
		try:
			for ref, nume in (continut(q) if q else []):
				adauga(ref, nume, "frecventa")
		except Exception as e:
			print("[tv_web] canalele frecventei: %r" % (e,))
	if radacina is None:
		radacina = _radacinaTv()
	if radacina:
		try:
			for ref, nume in continut(radacina):
				adauga(ref, nume, "lista")
		except Exception as e:
			print("[tv_web] lista televizorului: %r" % (e,))
	if serviciu is None:
		serviciu = T.serviciuTv()
	for c in rez:
		ok, motiv = m.verificaCanal(c["ref"]) if c["sursa"] != "frecventa" else (True, None)
		if ok:
			info = T.infoCanal(c["ref"], serviciu, ref_tv, baza=baza)
			merge, text = T.potrivire(info["video"], info["audio"], hevc, ac3, wasm)
			if c["radio"] and not info["video"]:
				merge, text = True, ""
			c.update({"merge": bool(merge), "motiv": "" if merge else text, "avertizare": text if merge else "",
				"video": info["video"], "audio": info["audio"]})
		else:
			c.update({"merge": False, "motiv": motiv, "avertizare": "", "video": "", "audio": []})
		c["pe_tv"] = bool(ref_tv) and T.refCurata(ref_tv) == c["ref"]
	return {"result": True, "tv": T.refCurata(ref_tv) if ref_tv else "", "canale": rez}


# ---------------------------------------------------------------- comenzile

def porneste(argumente_, cine, browser_nume, adresa, H=None, M=None, ref_tv=None, serviciu=None, baza=None,
		fereastra=""):
	"""POST /api/tv-porneste. `fereastra` = antetul X-HDS-Fereastra; `preia=1` = omul a ales sa ia transmisia din alta
	fereastra a acestui browser; `wasm=1` = pagina are playerul wasm (imaginea MPEG-2 se decodeaza in browser);
	`urmeaza=1` = pagina urmeaza televizorul: canalul e cel de ACUM al televizorului (fara ref, ales aici)."""
	T = _T(H)
	m = _m(H, M)
	urmeaza = argumente_.get("urmeaza") == "1"
	if ref_tv is None:
		ref_tv = T.refTv()
	if urmeaza:
		# `ref` in raspuns = ce e pe televizor: pagina asteapta altceva (nu incearca din nou acelasi lucru)
		if not ref_tv:
			return {"result": False, "fara_canal": True, "ref": "", "message": _t("Pe televizor nu merge acum niciun canal.")}
		ref = T.refCurata(ref_tv)
		if ref is None:
			return {"result": False, "fara_canal": True, "ref": ref_tv,
				"message": _t("Pe televizor merge acum ceva ce nu se poate transmite în browser.")}
	else:
		ref = T.refCurata(argumente_.get("ref", ""))
		if ref is None:
			return {"result": False, "message": _t("Alege un canal din listă.")}
	hevc = argumente_.get("hevc") == "1"
	ac3 = argumente_.get("ac3") == "1"
	wasm = argumente_.get("wasm") == "1"
	if serviciu is None:
		serviciu = T.serviciuTv()
	info = T.infoCanal(ref, serviciu, ref_tv, baza=baza)
	merge, text = T.potrivire(info["video"], info["audio"], hevc, ac3, wasm)
	nume = numeCanal(ref) or ref
	if not merge:
		return {"result": False, "message": text, "nume": nume, "ref": ref}
	ses, motiv = m.porneste(ref, nume, cine, browser_nume, adresa, ac3=ac3, fereastra=fereastra,
		preia=argumente_.get("preia") == "1", wasm=wasm)
	if ses is None:
		if motiv == T.ALTA_FEREASTRA:
			return {"result": False, "alta_fereastra": True,
				"message": _t("Transmisia e folosită în altă fereastră a acestui browser. O preiei aici?")}
		if motiv == T.PREA_REPEDE:
			# pagina reincearca singura dupa `ms` (cat mai e din pauza dintre doua porniri)
			ms = m.msPanaLaPornire() if hasattr(m, "msPanaLaPornire") else 2000
			return {"result": False, "repede": True, "ms": ms, "nume": nume, "ref": ref,
				"message": _t("Canalele se schimbă prea repede. Se reîncearcă peste o clipă.")}
		if motiv == T.CRIPTAT_OPRIT:
			return {"result": False, "criptat": True, "message": _t(TEXT_CRIPTAT)}
		if motiv == T.CRIPTAT_ASTEAPTA:
			# player.js intreaba din nou singur dupa `secunde`, numai pentru canalul ales ultimul
			return {"result": False, "asteapta": True, "secunde": max(1, m.secundeCriptat()), "nume": nume, "ref": ref,
				"message": _t("Canalul pornește în câteva secunde.")}
		return {"result": False, "message": motiv, "nume": nume, "ref": ref}
	# AVERTIZAREA SUNETULUI (sus): din PMT cand sesiunea l-a citit deja (sesiune reluata), altfel numai a imaginii
	if getattr(ses, "pmt_citit", False) and hasattr(T, "avertizarePmt"):
		avertizare = T.avertizarePmt(ses.video, ses.piste, ses.ac3, ses.wasm)
	else:
		avertizare = T.potrivire(info["video"], [], hevc, ac3, wasm)[1]
	return {"result": True, "id": ses.id, "ref": ses.ref, "nume": ses.nume, "avertizare": avertizare,
		"video": info["video"], "audio": info["audio"], "urmeaza": urmeaza,
		"pe_tv": bool(ref_tv) and T.refCurata(ref_tv) == ses.ref, "decriptare": getattr(ses, "decriptare", None)}


def opreste(argumente_, cine, H=None, M=None):
	"""POST /api/tv-opreste: o sesiune dupa id (din lista sesiunilor) sau sesiunea acestui browser."""
	m = _m(H, M)
	sid = argumente_.get("id", "")
	if not sid:
		ses = m.sesiunePentru(cine) if cine else None
		if ses is None:
			return {"result": True, "message": _t("Nu transmite nimic spre acest browser.")}
		sid = ses.id
	if m.opreste(sid, _t("Transmisia a fost oprită din pagină.")):
		m.oprite.pop(cine, None)
		return {"result": True, "message": _t("Transmisia s-a oprit.")}
	return {"result": False, "message": _t("Transmisia nu mai există. Reîncarcă pagina.")}


def seteaza(argumente_, H=None, config=None, salveaza=None):
	"""POST /api/tv-seteaza: o valoare straina nu schimba nimic."""
	T = _T(H)
	if config is None:
		T.initConfig()
		from Components.config import config as cfg
		config = cfg.hds_transmisie
	schimbat = []
	for cheie, permise in (("permis", ("0", "1")), ("standby", ("0", "1")), ("sesiuni_max", T.SESIUNI_PERMISE),
			("asteptare", tuple(str(s) for s in T.ASTEPTARI_PERMISE_S))):
		v = argumente_.get(cheie)
		if v is None:
			continue
		if v not in permise:
			return {"result": False, "message": _t("Valoare necunoscută.")}
		element = getattr(config, cheie)
		element.value = (v == "1") if cheie in ("permis", "standby") else v
		element.save()
		schimbat.append(cheie)
	if not schimbat:
		return {"result": False, "message": _t("Nimic de schimbat.")}
	if salveaza is None:
		from Components.config import configfile
		salveaza = configfile.save
	salveaza()
	return {"result": True, "message": _t("Salvat.")}


def verifica(argumente_, cine, H=None, M=None, ref_tv=None, serviciu=None, baza=None):
	"""GET /api/tv-verifica: merge canalul acum in browser (aceleasi verificari ca pornirea, fara inregistrare) si intr-un
	player extern (VLC reda si MPEG-2, deci acolo conteaza numai tunerul, antena, limitele si memoria)."""
	T = _T(H)
	m = _m(H, M)
	ref = T.refCurata(argumente_.get("ref", ""))
	if ref is None:
		return {"result": False, "message": _t("Alege un canal din listă.")}
	if ref_tv is None:
		ref_tv = T.refTv()
	if serviciu is None:
		serviciu = T.serviciuTv()
	ok, motiv = m.poateIncepe(ref, cine)
	# "Vezi live" pe un canal pe care transmisia nu-l poate lua fara televizor (motor, un singur tuner): televizorul poate
	# trece pe el? (None = nu e cazul)
	mutare = m.mutareTv(ref, cine) if (not ok and hasattr(m, "mutareTv")) else None
	info = T.infoCanal(ref, serviciu, ref_tv, baza=baza)
	merge, text = T.potrivire(info["video"], info["audio"], argumente_.get("hevc") == "1", argumente_.get("ac3") == "1",
		argumente_.get("wasm") == "1")
	rez = {"result": True, "ref": ref, "nume": numeCanal(ref) or ref, "video": info["video"], "audio": info["audio"],
		"pe_tv": bool(ref_tv) and T.refCurata(ref_tv) == ref, "extern": bool(ok), "extern_motiv": "" if ok else motiv}
	if not ok and mutare is not None and not mutare[0]:
		rez.update({"merge": False, "motiv": mutare[1], "ocupat": True, "avertizare": ""})
	elif not ok and mutare is not None and merge:
		rez.update({"merge": False, "muta_tv": True, "motiv": motiv, "avertizare": text})
	elif not ok and mutare is not None:
		rez.update({"merge": False, "motiv": text, "avertizare": ""})
	elif not ok:
		rez.update({"merge": False, "motiv": motiv, "avertizare": ""})
	elif not merge:
		rez.update({"merge": False, "motiv": text, "avertizare": ""})
	else:
		rez.update({"merge": True, "motiv": "", "avertizare": text})
	# un canal MPEG-2 trece ca "merge" cand pagina trimite wasm=1 (are playerul wasm); fluxul e acelasi, numai redarea
	# din pagina difera (player.js alege playerul dupa "video")
	return rez


def urmeaza(ref_stiut, standby_stiut, cheie, scrie, H=None, M=None, nume_canal=None):
	"""GET /api/tv-urmeaza: -> (raspunsul pe loc, None) cand televizorul nu mai e pe `ref_stiut` / `standby_stiut` (sau
	sunt deja prea multe cereri lungi: "plin", pagina intreaba din nou peste o secunda), altfel (None, (intrarea, gata)):
	raspunsul il trimite scrie(dict) mai tarziu, o singura data (dupa un zap, la standby, la URMEAZA_S).
	`cheie` = (browserul, fereastra): o cerere noua a aceleiasi ferestre o inlocuieste pe cea veche."""
	T = _T(H)
	m = _m(H, M)
	nume_canal = nume_canal or numeCanal

	def raspuns(ref, standby, plin=False):
		d = {"result": True, "tv": {"ref": ref or "", "nume": nume_canal(ref) if ref else ""}, "in_standby": bool(standby)}
		if plin:
			d["plin"] = True
		return d

	ref, standby = m.starePentruUrmarire()
	if not T._acelasiTv(ref, ref_stiut) or standby != bool(standby_stiut):
		return raspuns(ref, standby), None
	gata = [False]

	def la_tv(ref_nou, standby_nou):
		if gata[0]:
			return
		gata[0] = True
		scrie(raspuns(ref_nou, standby_nou))

	u = m.urmaresteTv(la_tv, ref_stiut, bool(standby_stiut), URMEAZA_S, cheie)
	if u is None:
		return raspuns(ref, standby, plin=True), None
	return None, (u, gata)


def argLung(request, nume, maxim=REF_MAXIM):
	"""Un argument al cererii intreg (argumente() taie la 64), cel mult `maxim` caractere; '' daca lipseste."""
	v = (getattr(request, "args", None) or {}).get(nume)
	if not v:
		return ""
	x = v[0]
	return (x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x))[:maxim].strip()


def alegePista(argumente_, cine, H=None, M=None):
	"""POST /api/tv-pista?pid=: pista audio a fluxului acestui browser; pagina reconecteaza fluxul dupa raspuns."""
	m = _m(H, M)
	ok, motiv = m.alegePista(cine, argumente_.get("pid", ""))
	if not ok:
		return {"result": False, "message": motiv}
	return {"result": True, "message": _t("Pista aleasă. Imaginea se reconectează.")}


def _refsDinText(text, T, maxim):
	rez, vazute = [], set()
	for bucata in (text or "").split(","):
		r = T.refCurata(bucata.strip())
		if r is not None and r not in vazute:
			vazute.add(r)
			rez.append(r)
			if len(rez) >= maxim:
				break
	return rez


def m3u(argumente_, corp, cine, browser_nume, gazda, H=None, A=None, nume_canal=None):
	"""POST /api/tv-m3u: playlistul pentru playerele externe. `ref=` un canal (cheie de DURATA_CANAL_S) sau, in corp,
	`canale=r1,r2,...` cu `grup=` si `nume=` (lista filtrata din pagina canalelor, cheie de DURATA_LISTA_S). -> (cod,
	text sau dict de eroare, numele fisierului). Jetonul API nu intra niciodata in fisier: adresele au cheia lor."""
	T = _T(H)
	if A is None:
		from . import acces_extern as A
	nume_canal = nume_canal or numeCanal
	if not A.gazdaBuna(gazda):
		return 400, {"result": False, "message": _t("Adresa receptorului din cerere nu e bună.")}, None
	ref = T.refCurata(argumente_.get("ref", ""))
	if ref is not None:
		refs, fel = [ref], "canal"
	else:
		refs, fel = _refsDinText((corp or {}).get("canale", ""), T, A.MAX_CANALE), "lista"
	if not refs:
		return 400, {"result": False, "message": _t("Alege un canal din listă.")}, None
	canale = [(r, nume_canal(r) or r) for r in refs]
	grup = (corp or {}).get("grup") or argumente_.get("grup") or ""
	eticheta = (corp or {}).get("nume") or argumente_.get("nume") or (canale[0][1] if fel == "canal" else grup)
	cheie_text, _c = A.magazin().creeaza(fel, refs, cine or "", browser_nume or "", eticheta)
	text = A.textM3u(gazda, cheie_text, canale, grup)
	parti = [canale[0][1]] if fel == "canal" else ["hdsatelit", eticheta or "canale"]
	return 200, text, A.numeFisier(parti)


def accesLista(A=None, AW=None):
	"""GET /api/tv-acces: playlisturile date (fara aparate) si aparatele din casa, fara chei. La un aparat al carui
	playlist din memorie e taiat (aparate_web.MAX_CANALE_APARAT): "taiat": [canale in playlist, canale in sursa]."""
	if A is None:
		from . import acces_extern as A
	if AW is None:
		from . import aparate_web as AW
	m = A.magazin()
	aparate = m.aparate()
	for a in aparate:
		c = m.aparat(a["id"])
		stare = AW.starePlaylist(c.sursa) if c is not None and c.sursa else None
		if stare is not None and stare[1] > stare[0]:
			a["taiat"] = list(stare)
	return {"result": True, "adrese": m.lista(cu_aparate=False), "aparate": aparate, "max_aparate": A.MAX_APARATE,
		"max_canale": AW.MAX_CANALE_APARAT}


def accesRevoca(argumente_, A=None, H=None, M=None):
	"""POST /api/tv-acces-revoca?id=: cheia nu mai deschide nimic, iar transmisia ei in curs (sesiunea "x:<id>") se
	opreste pe loc."""
	if A is None:
		from . import acces_extern as A
	m = A.magazin()
	id_ = argumente_.get("id", "")
	aparat = m.aparat(id_) is not None
	if m.revoca(id_):
		if aparat:
			mesaj = _t("Aparatul a fost revocat. Adresele lui nu mai merg.")
		else:
			mesaj = _t("Adresa a fost revocată. Playlisturile cu ea nu mai merg.")
		try:
			mg = _m(H, M)
			ses = mg.sesiunePentru("x:" + id_)
			if ses is not None:
				mg.opreste(ses.id, mesaj)
		except Exception as e:
			print("[tv_web] transmisia cheii revocate: %r" % (e,))
		return {"result": True, "message": mesaj}
	return {"result": False, "message": _t("Adresa nu mai există.")}


# ---------------------------------------------------------------- fluxul

def predaSoclul(request, ses, m, scrie=None, H=None, antet=None):
	"""Scrie antetul fluxului pe soclul cererii si il preda firului sesiunii. -> True daca a mers."""
	transport = getattr(request, "transport", None) or getattr(getattr(request, "channel", None), "transport", None)
	if transport is None or not hasattr(transport, "fileno"):
		return False
	try:
		fd = os.dup(transport.fileno())
	except (OSError, ValueError):
		return False
	try:
		transport.pauseProducing()
	except Exception:
		pass
	canal = getattr(request, "channel", None)
	if canal is not None and hasattr(canal, "setTimeout"):
		try:
			canal.setTimeout(None)
		except Exception:
			pass
	_pazesteSoclul(fd)
	scrie = scrie or _T(H).trimiteTot
	if not scrie(fd, antet or ANTET_FLUX):
		try:
			os.close(fd)
		except OSError:
			pass
		return False

	def la_plecare():
		try:
			transport.loseConnection()
		except Exception:
			pass

	if not m.ataseaza(ses, fd, la_plecare):
		try:
			os.close(fd)
		except OSError:
			pass
		la_plecare()
		return False
	return True


def _pazesteSoclul(fd):
	"""TCP_USER_TIMEOUT si keepalive: un telefon iesit din Wi-Fi elibereaza tunerul in zeci de secunde, nu in 15
	minute. Optiunile pe care nucleul nu le are se sar."""
	import socket
	import sys
	try:
		s = socket.socket(fileno=os.dup(fd))
	except Exception:
		return
	try:
		s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
		linux = sys.platform.startswith("linux")
		for nume, numar_linux, valoare in (("TCP_USER_TIMEOUT", 18, TERMEN_TCP_S * 1000), ("TCP_KEEPIDLE", 4, 20),
				("TCP_KEEPINTVL", 5, 5), ("TCP_KEEPCNT", 6, 2)):
			opt = getattr(socket, nume, None)
			if opt is None and linux:
				opt = numar_linux
			if opt is not None:
				try:
					s.setsockopt(socket.IPPROTO_TCP, opt, valoare)
				except OSError:
					pass
	except Exception:
		pass
	finally:
		s.close()


def _caleFisier(*parti):
	return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parti)


# ---------------------------------------------------------------- rutele

OSD_FIRE_MAX = 3
OSD_TERMEN_S = 6
_osd_fire = [0]


def _strat(O=None):
	if O is not None:
		return O
	from . import osd_strat
	return osd_strat.strat()


def fereastraDin(request):
	"""Id-ul ferestrei (antetul X-HDS-Fereastra): litere si cifre, cel mult 32; altfel ''."""
	from . import plugin as P
	v = P._antet(request, b"x-hds-fereastra") or ""
	return v if (0 < len(v) <= 32 and v.isalnum()) else ""


def corpLista(request):
	"""Campurile lungi ale POST /api/tv-m3u (lista de canale), luate direct din request.args (argumente() taie la 64)."""
	rez = {}
	for cheie, maxim in ((b"canale", 64 * 1024), (b"grup", 80), (b"nume", 80)):
		v = (getattr(request, "args", None) or {}).get(cheie)
		if v:
			x = v[0]
			rez[cheie.decode("ascii")] = (x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x))[:maxim]
	return rez


def fereastraStrat(S):
	"""Textul antetului x-hds-video: fereastra imaginii pe televizor (osd_strat.Strat.fereastra, procente), sau None cand
	nu se stie (fara noduri /proc/stb/vmpeg; un strat de proba fara ea)."""
	f = getattr(S, "fereastra", None)
	if f is None:
		return None
	try:
		v = f()
		if v is None:
			return None
		from . import osd_strat
		return osd_strat.textFereastra(v)
	except Exception as e:
		print("[tv_web] fereastra imaginii nu s-a citit: %r" % (e,))
		return None


def scrieOsd(request, rez, fereastra=None):
	"""Raspunsul stratului (pe firul enigma2): 200 cu BGRA gzip, 304, sau eroare JSON. `fereastra` (fereastraStrat): pe
	orice raspuns, in antetul x-hds-video; pe 304 tot el spune paginii ca lista s-a inchis cand stratul nu s-a mai
	schimbat (evideo.cpp pune ecranul intreg la 100 ms dupa ce ecranul cu fereastra a disparut)."""
	cod = rez.get("cod")
	if fereastra:
		request.setHeader(b"x-hds-video", fereastra.encode("ascii"))
	if cod == 304:
		request.setResponseCode(304)
		request.setHeader(b"etag", rez["etag"].encode("ascii"))
		request.setHeader(b"cache-control", b"no-store")
		return b""
	if cod != 200:
		import json
		request.setResponseCode(cod or 503)
		request.setHeader(b"content-type", b"application/json; charset=utf-8")
		return json.dumps({"result": False, "message": rez.get("mesaj") or _t("Stratul nu se poate citi acum.")},
			ensure_ascii=False).encode("utf-8")
	l, h = rez["marime"]
	request.setResponseCode(200)
	request.setHeader(b"content-type", b"application/octet-stream")
	request.setHeader(b"content-encoding", b"gzip")
	request.setHeader(b"cache-control", b"no-store")
	request.setHeader(b"x-content-type-options", b"nosniff")
	request.setHeader(b"etag", rez["etag"].encode("ascii"))
	request.setHeader(b"x-hds-osd", ("%dx%d" % (l, h)).encode("ascii"))
	request.setHeader(b"x-hds-osd-gol", b"1" if rez.get("gol") else b"0")
	return rez["date"]


def osdPeFir(request, S, latime, etag, amanat, asteptare=None, reactor_=None):
	"""Verificarea stratului pe un fir (P._AsteptareCaptura: rezultatul vine inapoi pe firul enigma2 printr-un pipe si un
	eTimer, nu prin reactor.callLater sau callFromThread, care in reactorul imaginii pot lasa bucla sa doarma)."""
	if asteptare is None:
		from . import plugin as P
		asteptare = P._AsteptareCaptura
	if reactor_ is None:
		try:
			from twisted.internet import reactor as reactor_
		except ImportError:   # probele de pe PC dau o asteptare care nu are nevoie de reactor
			reactor_ = None
	_osd_fire[0] += 1
	gata = [False]

	def _incheie(corp):
		if gata[0]:
			return
		gata[0] = True
		_osd_fire[0] = max(0, _osd_fire[0] - 1)
		try:
			if corp:
				request.write(corp)
			request.finish()
		except Exception as e:
			print("[tv_web] stratul: raspunsul nu a plecat (client plecat?): %r" % (e,))

	def _rezultat(rez):
		# fereastra de acum, cand pleaca raspunsul (verificarea a durat)
		_incheie(scrieOsd(request, rez, fereastraStrat(S)))

	def _eroare(mesaj):
		print("[tv_web] stratul: %s" % mesaj)
		_incheie(scrieOsd(request, {"cod": 500, "mesaj": _t("Eroare la citirea stratului.")}))

	def _termen():
		_incheie(scrieOsd(request, {"cod": 504, "mesaj": _t("Stratul nu s-a citit la timp.")}))

	try:
		asteptare(reactor_, lambda: S.cadru(latime, etag), _rezultat, _eroare, _termen, OSD_TERMEN_S, 50).porneste()
	except Exception as e:
		_osd_fire[0] = max(0, _osd_fire[0] - 1)
		print("[tv_web] stratul: firul nu a pornit: %r" % (e,))
		return scrieOsd(request, {"cod": 500, "mesaj": _t("Eroare la citirea stratului.")})
	return amanat


ANTET_FLUX_EXTERN = (b"HTTP/1.1 200 OK\r\n"
	b"Content-Type: video/mp2t\r\n"
	b"Cache-Control: no-store\r\n"
	b"Connection: close\r\n"
	b"Server: HDSatelit\r\n\r\n")


def verificaExtern(request, H=None, A=None, noteaza=True):
	"""Verificarile adresei /tv-extern/<cheie>/<canal>.ts care nu pornesc nimic, aceleasi pentru GET si HEAD:
	-> (None, adresa clientului, cheia, referinta) cand adresa e buna, altfel (cod, text pentru om, None, None): 403 din
	afara retelei locale, 404 adresa gresita, 403 cheie gresita, revocata, expirata sau canal care nu e in playlist.
	noteaza=False (HEAD): ora folosirii cheii nu se schimba."""
	from . import plugin as P
	T = _T(H)
	if A is None:
		from . import acces_extern as A
	adresa = P._adresaClient(request) or ""
	if not P._esteAdresaLocala(adresa):
		return 403, _t("Acces permis doar din rețeaua locală."), None, None
	rest = [p.decode("ascii", "replace") if isinstance(p, bytes) else p for p in (getattr(request, "postpath", None) or []) if p]
	if len(rest) != 2 or not rest[1].endswith(".ts"):
		return 404, _t("Adresa nu e bună."), None, None
	ref = T.refCurata(A.refDinCod(rest[1][:-3]) or "")
	if ref is None:
		return 404, _t("Adresa nu e bună."), None, None
	cheie, motiv = A.magazin().verifica(rest[0], ref, noteaza=noteaza)
	if cheie is None:
		return 403, motiv, None, None
	return None, adresa, cheie, ref


def fluxExtern(request, H=None, M=None, A=None, amanat=None, termen=None):
	"""GET /tv-extern/<cheie>/<canal>.ts. -> (None, amanat) cand fluxul a pornit, altfel (cod, text pentru om).
	Sesiunea are cheia ei de client ("x:<id>"), separata de a browserului: o comutare in Kodi inlocuieste numai
	sesiunea acestei chei. Daca limita de sesiuni o opreste si cealalta sesiune e a browserului care a dat cheia, dar
	fara nimeni care se uita, aceea se opreste; cu cineva in fata imaginii raspunsul e 503 cu motivul (nimic furat).
	CANAL CRIPTAT care trebuie sa astepte (CRIPTAT_ASTEAPTA): (None, amanat) si cererea ramane deschisa pana ii vine
	randul, cel mult EXTERN_ASTEPTARE_S (`termen` = ceasul managerului pana la care, pus la prima incercare); atunci
	pornirea se incearca din nou prin aceeasi functie. Cand asteptarea ar trece de termen: 503 cu Retry-After
	(request.hds_retry). La fel PREA_REPEDE (comutari rapide): asteapta cel mult EXTERN_REPEDE_S."""
	T = _T(H)
	m = _m(H, M)
	cod, adresa_sau_motiv, cheie, ref = verificaExtern(request, H, A)
	if cod is not None:
		return cod, adresa_sau_motiv
	adresa = adresa_sau_motiv
	cine = "x:" + cheie.id
	if cheie.fel == "aparat" and cheie.nume:
		eticheta = cheie.nume              # aparatul din casa, cu numele dat de om
	else:
		eticheta = _t("Player extern") + (" (%s)" % cheie.proprietar_nume if cheie.proprietar_nume else "")
	nume = numeCanal(ref) or ref
	ses, motiv = m.porneste(ref, nume, cine, eticheta, adresa, ac3=True, extern=True)
	if ses is None and motiv not in (T.PREA_REPEDE, T.CRIPTAT_OPRIT, T.CRIPTAT_ASTEAPTA):
		# numai cand refuzul vine din limita de sesiuni si una din ele e a browserului care a dat cheia; un refuz din alt
		# motiv (motorul, standby, memoria, transmisia oprita din setari) nu opreste nimic
		a_lui = m.sesiunePentru(cheie.proprietar) if cheie.proprietar else None
		alte = [s for s in m.vii() if s.cine != cine]
		la_limita = a_lui is not None and a_lui in alte and len(alte) >= m.setari.sesiuniMax()
		if la_limita:
			ok_canal, motiv_canal = m.verificaCanal(ref, a_lui)
			if not ok_canal:
				motiv = motiv_canal      # canalul nu merge oricum (antena, tunerul): nimic de oprit
			elif not a_lui.cu_client:
				m.opreste(a_lui.id, _t("Transmisia a trecut în playerul extern."))
				ses, motiv = m.porneste(ref, nume, cine, eticheta, adresa, ac3=True, extern=True)
			else:
				motiv = _t("Transmisia e folosită acum în browser. Oprește imaginea din pagină și deschide din nou canalul.")
	# dupa limita de sesiuni (a doua pornire, cea de dupa oprirea sesiunii nefolosite a browserului, poate astepta si ea)
	if termen is not None and motiv in (T.CRIPTAT_ASTEAPTA, T.PREA_REPEDE) and m.ceas() < termen:
		return _asteaptaExtern(request, H, M, A, amanat, m, cine, termen)
	if motiv == T.CRIPTAT_ASTEAPTA:
		secunde = m.secundeCriptat()
		if termen is None and secunde <= EXTERN_ASTEPTARE_S:
			return _asteaptaExtern(request, H, M, A, amanat, m, cine, m.ceas() + EXTERN_ASTEPTARE_S)
		request.hds_retry = max(2, secunde)
		return 503, _t("Canalul pornește în câteva secunde. Deschide-l din nou puțin mai târziu.")
	if motiv == T.PREA_REPEDE:
		if termen is None:
			# un player care sare repede intre canale: cererea asteapta pana trece pauza dintre porniri (ceasul
			# managerului o incearca din nou); o cerere noua a aceluiasi player o inlocuieste (ultima castiga)
			return _asteaptaExtern(request, H, M, A, amanat, m, cine, m.ceas() + EXTERN_REPEDE_S)
		return 503, _t("Canalele se schimbă prea repede. Mai încearcă peste o clipă.")
	if motiv == T.CRIPTAT_OPRIT:
		return 403, _t(TEXT_CRIPTAT)
	if ses is None:
		return 503, motiv
	if getattr(ses, "decriptare", None) == getattr(T, "DECRIPTARE_ASTEAPTA", "-") and hasattr(m, "asteaptaDecriptarea"):
		# canal criptat (DECRIPTAREA): fluxul pleaca abia cand imaginea iese clara; daca camul nu-l decripteaza, refuzul
		return _asteaptaDecriptareaExtern(request, H, amanat, m, ses)
	if not predaSoclul(request, ses, m, H=H, antet=ANTET_FLUX_EXTERN):
		return 500, _t("Fluxul nu a putut porni.")
	return None, amanat


def _asteaptaDecriptareaExtern(request, H, amanat, m, ses):
	"""Raspunsul amanat al unui player extern pe un canal criptat: managerul cheama la_gata(None) cand imaginea iese clara
	(fluxul pleaca) sau la termen (EXTERN_ASTEPTARE_S: 503 cu Retry-After, sesiunea ramane pentru cererea urmatoare),
	la_gata(motiv) cand camul nu decripteaza canalul (403) sau sesiunea s-a oprit (503). Clientul plecat isi lasa locul."""
	T = _T(H)
	gata = [False]

	def la_gata(motiv):
		if gata[0]:
			return
		gata[0] = True
		if motiv is None and ses.decriptare == T.DECRIPTARE_MERGE and not ses.oprita.is_set():
			if predaSoclul(request, ses, m, H=H, antet=ANTET_FLUX_EXTERN):
				return
			cod, corp = 500, _t("Fluxul nu a putut porni.")
		elif motiv is None:
			request.hds_retry = 5
			cod, corp = 503, _t("Canalul se decriptează încă. Deschide-l din nou peste câteva secunde.")
		elif ses.decriptare == T.DECRIPTARE_NU:
			cod, corp = 403, motiv
		else:
			cod, corp = 503, motiv
		try:
			request.write(scrieExtern(request, cod, corp))
			request.finish()
		except Exception as e:
			print("[tv_web] raspunsul amanat (decriptarea): %r" % (e,))

	def plecat(_eroare=None):
		gata[0] = True
		m.renuntaDecriptarea(ses, la_gata)

	try:
		request.notifyFinish().addErrback(plecat)
	except Exception:
		pass
	m.asteaptaDecriptarea(ses, la_gata, EXTERN_ASTEPTARE_S)
	return None, amanat


def _asteaptaExtern(request, H, M, A, amanat, m, cine, termen):
	"""Raspunsul amanat al unui player extern care asteapta o pornire criptata. Managerul cheama la_rand(None) cand ii
	vine randul (sau la termen): pornirea se incearca din nou (fluxul porneste, cererea asteapta iar sau primeste
	raspunsul); la_rand(motiv) cand alta cerere a aceleiasi chei o inlocuieste (503 cu motivul). Clientul plecat isi
	lasa locul (notifyFinish)."""
	gata = [False]

	def la_rand(motiv):
		if gata[0]:
			return
		gata[0] = True
		if motiv is None:
			cod, corp = fluxExtern(request, H, M, A, amanat, termen)
			if cod is None:
				return
		else:
			cod, corp = 503, motiv
		try:
			request.write(scrieExtern(request, cod, corp))
			request.finish()
		except Exception as e:
			print("[tv_web] raspunsul amanat al playerului extern: %r" % (e,))

	def plecat(_eroare=None):
		gata[0] = True
		m.renuntaAsteptarea(cine, la_rand)

	try:
		request.notifyFinish().addErrback(plecat)
	except Exception:
		pass
	m.asteaptaCriptat(cine, la_rand, max(0, termen - m.ceas()))
	return None, amanat


def scrieExtern(request, cod, corp):
	"""Raspunsul text al /tv-extern (si cel amanat): codul, textul pentru om; la 503 Retry-After (2 s sau cat a pus
	fluxExtern in request.hds_retry)."""
	request.setResponseCode(cod)
	request.setHeader(b"content-type", b"text/plain; charset=utf-8")
	request.setHeader(b"cache-control", b"no-store")
	if cod == 503:
		request.setHeader(b"retry-after", str(int(getattr(request, "hds_retry", 2) or 2)).encode("ascii"))
	return (corp + "\n").encode("utf-8")


def ruteExterne(resource, amanat, H=None, M=None, A=None, C=None, F=None):
	"""-> resursa /tv-extern (fluxul pentru playerele externe; nu e sub /api: fara cookie, fara antete, cu cheia
	playlistului in adresa). canale.m3u, ghid.xml si sigla/<nume>.png ale aparatelor din casa: aparate_web.py (C =
	canale_web si F = furnizorul lui, in probe)."""

	class ExternResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			from . import aparate_web
			if aparate_web.esteRutaAparat(request):
				return aparate_web.raspundeExtern(request, amanat, F=F, C=C, A=A, H=H)
			cod, corp = fluxExtern(request, H, M, A, amanat)
			if cod is None:
				return corp
			return scrieExtern(request, cod, corp)

		def render_HEAD(self, request):
			# unele playere intreaba intai cu HEAD: raspunsul nu porneste nimic, dar spune ca GET daca adresa merge (o cheie
			# revocata sau inventata: 403, o adresa gresita: 404; inainte era 200 pe orice cheie)
			from . import aparate_web
			if aparate_web.esteRutaAparat(request):
				return aparate_web.raspundeExtern(request, amanat, cap=True, F=F, C=C, A=A, H=H)
			cod, _text, _cheie, _ref = verificaExtern(request, H, A, noteaza=False)
			request.setHeader(b"cache-control", b"no-store")
			if cod is not None:
				request.setResponseCode(cod)
				request.setHeader(b"content-type", b"text/plain; charset=utf-8")
				return b""
			request.setResponseCode(200)
			request.setHeader(b"content-type", b"video/mp2t")
			return b""

	return ExternResource()


def rute(baza, resource, amanat, H=None, M=None, O=None, A=None):
	"""-> ({nume: resursa de sub /api}, resursa paginii /tv). `baza` e HdsJsonResource din plugin.py, `amanat` e
	NOT_DONE_YET din twisted.web.server (raspunsul fluxului il scrie firul sesiunii)."""

	def _browser(request):
		from . import plugin as P
		secret, browser = P._sesiuneDinCerere(request)
		adresa = P._adresaClient(request) or ""
		return secret, browser, adresa

	def _doarBrowser(self, request):
		"""Pornirea si fluxul: numai din browser, niciodata cu ?token= (nicio cheie in adresa)."""
		from . import plugin as P
		if P.PARAM_JETON in request.args:
			return self._eroare(request, _t("Transmisia se pornește numai din pagina TV în browser, cu browserul conectat."), 403)
		return None

	def _poartaPagina(self, request):
		"""Ca fluxul: numai browserul (nu ?token=), cu antetul CSRF al paginii si din aceeasi origine. -> (refuz, secret,
		browser, adresa); refuz None daca trece."""
		from . import plugin as P
		refuz = _doarBrowser(self, request)
		if refuz is not None:
			return refuz, None, None, None
		secret, browser, adresa = _browser(request)
		if browser is None or not P.obtineAsociere().csrfValid(secret, P._antet(request, P.ANTET_CSRF.encode("ascii"))):
			return self._eroare(request, _t("Cerere respinsă: lipsește antetul paginii."), 403), None, None, None
		origin, referer = P._antet(request, b"origin"), P._antet(request, b"referer")
		if (origin or referer) and not P._acelasiOriginCerere(request):
			return self._eroare(request, _t("Cerere respinsă: nu vine dintr-o pagină a receptorului."), 403), None, None, None
		return None, secret, browser, adresa

	class StareResource(baza):
		def render_GET(self, request):
			try:
				_s, browser, adresa = _browser(request)
				return self._raspunde(request, stare(cineDinBrowser(browser, adresa), H, M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class CanaleResource(baza):
		def render_GET(self, request):
			try:
				a = argumente(request)
				return self._raspunde(request, canale(H, M, hevc=a.get("hevc") == "1", ac3=a.get("ac3") == "1",
					wasm=a.get("wasm") == "1"))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PornesteResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			refuz = _doarBrowser(self, request)
			if refuz is not None:
				return refuz
			try:
				_s, browser, adresa = _browser(request)
				cine = cineDinBrowser(browser, adresa)
				nume = (browser or {}).get("nume") or adresa
				return self._raspunde(request, porneste(argumente(request), cine, nume, adresa, H, M,
					fereastra=fereastraDin(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class OpresteResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				_s, browser, adresa = _browser(request)
				return self._raspunde(request, opreste(argumente(request), cineDinBrowser(browser, adresa), H, M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), H))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class FluxResource(baza):
		"""GET /api/tv-flux: numai browserul care a pornit sesiunea, cu antetul CSRF al paginii."""

		def render_GET(self, request):
			from . import plugin as P
			refuz = _doarBrowser(self, request)
			if refuz is not None:
				return refuz
			secret, browser, adresa = _browser(request)
			if browser is None or not P.obtineAsociere().csrfValid(secret, P._antet(request, P.ANTET_CSRF.encode("ascii"))):
				return self._eroare(request, _t("Cerere respinsă: lipsește antetul paginii."), 403)
			origin, referer = P._antet(request, b"origin"), P._antet(request, b"referer")
			if (origin or referer) and not P._acelasiOriginCerere(request):
				return self._eroare(request, _t("Cerere respinsă: nu vine dintr-o pagină a receptorului."), 403)
			m = _m(H, M)
			ses = m.sesiunePentru(cineDinBrowser(browser, adresa))
			if ses is None:
				return self._eroare(request, _t("Nu transmite nimic spre acest browser. Apasă Pornește."), 404)
			fer = fereastraDin(request)
			if fer and ses.fereastra and fer != ses.fereastra:
				# fereastra veche nu ia inapoi singura transmisia preluata de alta fereastra
				return self._raspunde(request, {"result": False, "preluata": True,
					"message": _t("Transmisia a fost preluată de altă fereastră.")}, 409)
			if not predaSoclul(request, ses, m, H=H):
				return self._eroare(request, _t("Fluxul nu a putut porni."), 500)
			return amanat

	class PaginaResource(resource.Resource):
		"""GET /tv (pagina), /tv/<fisier> (mpegts.js, playerele, licenta) si /tv/tv-wasm/<fisier> (decodorul wasm)."""
		isLeaf = True

		def render_GET(self, request):
			rest = [p for p in (getattr(request, "postpath", None) or []) if p]
			if len(rest) == 2 and rest[0] in (DOSAR_WASM, DOSAR_WASM.encode("ascii")):
				nume = rest[1].decode("ascii", "replace") if isinstance(rest[1], bytes) else rest[1]
				return fisierStatic(request, DOSAR_WASM + "/" + nume)
			if len(rest) == 1:
				return fisierStatic(request, rest[0])
			if rest:
				return fisierStatic(request, "")
			return pagina(request)

	class VerificaResource(baza):
		def render_GET(self, request):
			try:
				_s, browser, adresa = _browser(request)
				return self._raspunde(request, verifica(argumente(request), cineDinBrowser(browser, adresa), H, M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class UrmeazaResource(baza):
		"""GET /api/tv-urmeaza?ref=&standby=0|1: cererea lunga a paginii care urmeaza televizorul (urmeaza()). Numai
		citire; raspunsul amanat pleaca de pe firul enigma2 (extensia de zap prin coada managerului, ceasul lui)."""

		def render_GET(self, request):
			try:
				_s, browser, adresa = _browser(request)
				cheie = (cineDinBrowser(browser, adresa), fereastraDin(request))
				resursa = self

				def scrie(corp):
					try:
						request.write(resursa._raspunde(request, corp))
						request.finish()
					except Exception as e:
						print("[tv_web] raspunsul cererii lungi (client plecat?): %r" % (e,))

				pe_loc, asteapta = urmeaza(argLung(request, b"ref"), argumente(request).get("standby") == "1", cheie,
					scrie, H, M)
				if pe_loc is not None:
					return self._raspunde(request, pe_loc)
				u, gata = asteapta

				def plecat(_eroare=None):
					gata[0] = True
					_m(H, M).renuntaUrmarirea(u)

				try:
					request.notifyFinish().addErrback(plecat)
				except Exception:
					pass
				return amanat
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PistaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			refuz = _doarBrowser(self, request)
			if refuz is not None:
				return refuz
			try:
				_s, browser, adresa = _browser(request)
				return self._raspunde(request, alegePista(argumente(request), cineDinBrowser(browser, adresa), H, M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class M3uResource(baza):
		"""POST /api/tv-m3u: fisierul M3U (descarcat de pagina prin fetch); numai din browser, nu cu ?token=."""
		schimbaCeva = True

		def render_POST(self, request):
			from . import plugin as P
			refuz = _doarBrowser(self, request)
			if refuz is not None:
				return refuz
			try:
				_s, browser, adresa = _browser(request)
				cine = cineDinBrowser(browser, adresa)
				nume = (browser or {}).get("nume") or adresa
				corp = corpLista(request)
				cod, rez, fisier = m3u(argumente(request), corp, cine, nume, P._antet(request, b"host") or "", H)
				if cod != 200:
					return self._raspunde(request, rez, cod)
				request.setResponseCode(200)
				request.setHeader(b"content-type", b"audio/x-mpegurl; charset=utf-8")
				request.setHeader(b"cache-control", b"no-store")
				request.setHeader(b"x-content-type-options", b"nosniff")
				request.setHeader(b"content-disposition", ('attachment; filename="%s"' % fisier).encode("ascii"))
				return rez.encode("utf-8", "replace")
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class AccesResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, accesLista(A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class AccesRevocaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, accesRevoca(argumente(request), A, H, M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class AparatAdaugaResource(baza):
		"""POST /api/tv-aparat-adauga: cheia unui aparat din casa (aparate_web.py); numai din browser, nu cu ?token=.
		Raspunsul are adresele aparatului (cu cheia), date numai acum."""
		schimbaCeva = True

		def render_POST(self, request):
			from . import plugin as P
			from . import aparate_web
			refuz = _doarBrowser(self, request)
			if refuz is not None:
				return refuz
			try:
				_s, browser, adresa = _browser(request)
				nume = (browser or {}).get("nume") or adresa
				cod, rez = aparate_web.adauga(aparate_web.campuriCerere(request), cineDinBrowser(browser, adresa), nume,
					P._antet(request, b"host") or "", A=A)
				return self._raspunde(request, rez, cod)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class AparatRedenumesteResource(baza):
		"""POST /api/tv-aparat-redenumeste?id=&nume="""
		schimbaCeva = True

		def render_POST(self, request):
			from . import aparate_web
			try:
				cod, rez = aparate_web.redenumeste(aparate_web.campuriCerere(request), A=A)
				return self._raspunde(request, rez, cod)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class OsdResource(baza):
		"""GET /api/tv-osd?l=<latimea afisata>: stratul grafic (osd_strat.py). Poarta fluxului (browser, antet CSRF,
		aceeasi origine) si, cat ecranul "Acces SSH" e deschis pe televizor, numai un browser conectat cu codul (parola
		e mare pe ecran). Raspunsul gata facut pleaca de pe firul enigma2; o verificare a stratului ruleaza pe un fir."""

		def render_GET(self, request):
			refuz, _s, _b, _a = _poartaPagina(self, request)
			if refuz is not None:
				return refuz
			try:
				from . import acces_ssh_web
				refuz_ssh = acces_ssh_web.refuzEcranDeschis(request)
			except Exception:
				refuz_ssh = None
			if refuz_ssh is not None:
				return self._raspunde(request, refuz_ssh, 403)
			try:
				latime = int(argumente(request).get("l") or 960)
			except ValueError:
				latime = 960
			latime = max(160, min(3840, latime))
			from . import plugin as P
			etag = P._antet(request, b"if-none-match") or ""
			S = _strat(O)
			# fereastra imaginii (lista de canale o micsoreaza): citita inainte de dinMemorie, ca o fereastra noua sa
			# verifice stratul pe loc (osd_strat.Strat.fereastra), iar pagina sa le primeasca impreuna
			fereastra = fereastraStrat(S)
			rez = S.dinMemorie(latime, etag)
			if rez is not None:
				return scrieOsd(request, rez, fereastra)
			if _osd_fire[0] >= OSD_FIRE_MAX:
				request.setHeader(b"retry-after", b"1")
				return self._eroare(request, _t("Stratul se citește deja. Reîncearcă peste o clipă."), 503)
			return osdPeFir(request, S, latime, etag, amanat)

	api = {
		b"tv-stare": StareResource(),
		b"tv-canale": CanaleResource(),
		b"tv-porneste": PornesteResource(),
		b"tv-opreste": OpresteResource(),
		b"tv-seteaza": SeteazaResource(),
		b"tv-flux": FluxResource(),
		b"tv-osd": OsdResource(),
		b"tv-pista": PistaResource(),
		b"tv-verifica": VerificaResource(),
		b"tv-urmeaza": UrmeazaResource(),
		b"tv-m3u": M3uResource(),
		b"tv-acces": AccesResource(),
		b"tv-acces-revoca": AccesRevocaResource(),
		b"tv-aparat-adauga": AparatAdaugaResource(),
		b"tv-aparat-redenumeste": AparatRedenumesteResource(),
	}
	return api, PaginaResource()


JS = b"application/javascript; charset=utf-8"
TEXT = b"text/plain; charset=utf-8"


def tipuriStatice():
	"""{nume servit: tipul}: mpegts.js si licenta lui, playerele (comun si wasm), sunetul AC-3 al paginii, decodorul
	wasm si licentele lui."""
	tipuri = {FISIER_JS: JS, FISIER_LICENTA: TEXT, FISIER_PLAYER: JS, FISIER_PLAYER_WASM: JS, FISIER_WORKER: JS,
		FISIER_SUNET: JS}
	for nume in FISIERE_WASM:
		tipuri[DOSAR_WASM + "/" + nume] = (JS if nume.endswith(".js") else
			(b"application/wasm" if nume.endswith(".wasm") else TEXT))
	return tipuri


def fisierStatic(request, nume):
	"""Fisierele din tipuriStatice() (o lista inchisa: orice alt nume, 404); aceeasi poarta a retelei locale ca pagina.
	Playerele se verifica la fiecare incarcare (se schimba cu imaginea); mpegts.js si decodorul raman o zi in browser
	(adresa decodorului are versiunea lui, ?v=, deci o imagine noua il cere din nou)."""
	from . import plugin as P
	if isinstance(nume, bytes):
		nume = nume.decode("ascii", "replace")
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		return b""
	tipuri = tipuriStatice()
	if nume not in tipuri:
		request.setResponseCode(404)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return b"404"
	try:
		with open(_caleFisier(*nume.split("/")), "rb") as f:
			date = f.read(2 * 1024 * 1024)
	except (IOError, OSError):
		request.setResponseCode(404)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Biblioteca de redare lipsește din imagine.").encode("utf-8")
	if nume == FISIER_PLAYER:
		date = playerTradus(date)
	request.setHeader(b"content-type", tipuri[nume])
	# mpegts.js e si el fara cache: cand se schimba prin actualizare (de pilda pornirea la IDR pentru imaginea
	# intretesuta), browserele trebuie sa-l ia pe cel nou pe loc, nu dupa o zi
	fara_cache = nume in (FISIER_JS, FISIER_PLAYER, FISIER_PLAYER_WASM, FISIER_WORKER, FISIER_SUNET)
	request.setHeader(b"cache-control", b"no-cache" if fara_cache else b"public, max-age=86400")
	request.setHeader(b"x-content-type-options", b"nosniff")
	if nume == FISIER_WORKER:
		# workerul are politica lui (CSP-ul vine cu scriptul lui): fetch numai spre receptor, decodorul de pe receptor
		request.setHeader(b"content-security-policy", CSP_TV)
	return date


def textePlayer():
	"""{cheie: textul in limba meniurilor} pentru player.js (TEXTE_PLAYER)."""
	return dict((k, _t(v)) for k, v in TEXTE_PLAYER.items())


def playerTradus(date):
	"""player.js cu traducerile textelor lui puse in locul semnului SEMN_TEXTE (JSON numai ASCII)."""
	import json
	return date.replace(SEMN_TEXTE, json.dumps(textePlayer(), ensure_ascii=True, sort_keys=True).encode("ascii"), 1)


def pagina(request):
	"""Aceeasi poarta ca /paznic; CSP propriu: scriptul mpegts.js de pe receptor si redarea prin MediaSource (blob:)."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	request.setHeader(b"content-security-policy", CSP_TV)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	"""Cardul aparatelor si textele lui (traduse) intai, apoi stilul, configuratia si drumul din meniu."""
	from . import aparate_web
	return aparate_web.inPagina(_traducePagina(PAGINA)).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace(
		"__DRUM_MENIU__", _drumMeniu("hds_transmisie"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TV în browser</title>
<style>__STIL_COMUN__
  main{max-width:980px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1.02rem;margin:0 0 10px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0;}
  .butoane button,.rand button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:var(--panou);color:var(--text);font:inherit;cursor:pointer;}
  .butoane button.principal{background:var(--accent,#2f6fd6);color:#fff;border-color:transparent;}
  .butoane button:disabled{opacity:.5;cursor:default;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .lista{list-style:none;margin:0;padding:0;}
  .lista li{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .lista li:last-child{border-bottom:0;}
  .lista .nume{font-size:.98rem;}
  .lista .sub{display:block;color:var(--text-slab);font-size:.8rem;margin-top:2px;line-height:1.35;}
  .lista button{min-height:40px;padding:6px 12px;border-radius:8px;border:1px solid var(--bordura);background:var(--panou);color:var(--text);font:inherit;cursor:pointer;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,220px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  details summary{cursor:pointer;min-height:40px;display:flex;align-items:center;}
  /* intrebarea din randul unui playlist (Revoca): pe toata latimea randului, ca intrebarile din paginile antenei */
  .lista li .intrebare{grid-column:1 / -1;margin:2px 0 0;padding:10px 12px;border:1px solid var(--galben,#c9a227);border-radius:8px;line-height:1.45;}
  .lista li .intrebare p{margin:0;}
  .lista li .intrebare .butoane{margin:8px 0 0;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} .lista li{grid-template-columns:1fr;} }
__APARATE_STIL__
</style>
</head>
<body>
<main>
<h1>TV în browser</h1>
<section class="card">
  <div id="player"></div>
  <div class="butoane">
    <button class="principal" id="pornesteTv">Pornește canalul de pe televizor</button>
  </div>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota" id="memorie"></p>
</section>
<section class="card">
  <h2>Poți vedea acum</h2>
  <p class="nota">Canalele de pe frecvența televizorului merg mereu. Altele merg numai dacă un tuner e liber și antena nu trebuie să se rotească.</p>
  <ul class="lista" id="merg"></ul>
  <details id="nuMerg" class="ascuns"><summary>Nu merg acum</summary><ul class="lista" id="nuMergLista"></ul></details>
  <div class="butoane"><button id="reimprospateaza">Reîmprospătează lista</button></div>
</section>
<section class="card">
  <h2>Transmisii active</h2>
  <ul class="lista" id="sesiuni"></ul>
  <p class="nota">Televizorul și înregistrările au prioritate: o transmisie se oprește singură înainte ca televizorul sau o înregistrare să aibă nevoie de tunerul ei.</p>
</section>
__APARATE_CARD__
<section class="card">
  <h2>Playlisturi pentru playerele din casă</h2>
  <p class="nota">Un playlist (M3U) descărcat de aici sau din lista de canale deschide în VLC, Kodi sau alt player numai canalele din el, numai din rețeaua de acasă. Adresa unui canal ține 7 zile, a unei liste 30 de zile; o poți revoca oricând.</p>
  <ul class="lista" id="adrese"></ul>
</section>
<section class="card">
  <h2>Setări</h2>
  <div class="rand"><label for="permis">Permite transmisia în browser</label><select id="permis"><option value="1">Da</option><option value="0">Nu</option></select></div>
  <div class="rand dupa-permis"><label for="standby">Permite transmisia în standby</label><select id="standby"><option value="1">Da</option><option value="0">Nu</option></select></div>
  <div class="rand dupa-permis"><label for="sesiuni_max">Cel mult transmisii odată</label><select id="sesiuni_max"><option value="1">1</option><option value="2">2</option></select></div>
  <div class="rand dupa-permis"><label for="asteptare">Oprire când nu se mai uită nimeni, după</label><select id="asteptare"></select></div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Redarea folosește biblioteca mpegts.js (Apache-2.0), venită cu imaginea: <a href="/tv/mpegts-licenta.txt">licența</a>. Canalele cu imagine MPEG-2 și sunetul AC-3 (unde browserul nu îl redă singur) se decodează în browser, pe procesorul calculatorului, cu decodorul FFmpeg (LGPL-2.1) venit tot cu imaginea: <a href="/tv/tv-wasm/ffmpeg-licenta.txt">licența și sursa</a>; toate licențele sunt în <a href="/licente">Licențe</a>.</p>
</section>
</main>
<script src="/tv/mpegts.js"></script>
<script src="/tv/player.js"></script>
<script>
var CFG = __CONFIG__;
var player = null, ultimaStare = null, ultimulTv = null;
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
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function textDurata(s){
  s = Math.max(0, Math.floor(s));
  var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  if(h){ return h + " h " + m + " min"; }
  if(m){ return m + " min"; }
  return s + " s";
}
function textOcteti(n){
  if(n >= 1073741824){ return (n / 1073741824).toFixed(1) + " GB"; }
  if(n >= 1048576){ return (n / 1048576).toFixed(0) + " MB"; }
  return Math.round(n / 1024) + " KB";
}
function textData(t){
  if(!t){ return "fără termen"; }
  var d = new Date(t * 1000);
  function z(n){ return (n < 10 ? "0" : "") + n; }
  return z(d.getDate()) + "." + z(d.getMonth() + 1) + "." + d.getFullYear() + " " + z(d.getHours()) + ":" + z(d.getMinutes());
}
function porneste(ref, nume){
  if(!player){ return; }
  player.porneste(ref || "", nume || "");
  $("player").scrollIntoView({behavior: "smooth", block: "start"});
}
function opreste(id){
  var q = new URLSearchParams(); if(id){ q.set("id", id); }
  cerere("/api/tv-opreste", "POST", q).then(function(d){ mesaj(d.message, !d.result); citesteStarea(); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function randCanal(c){
  var li = document.createElement("li");
  var st = document.createElement("div");
  var n = document.createElement("span"); n.className = "nume"; n.textContent = c.nume + (c.pe_tv ? " (pe televizor)" : ""); st.appendChild(n);
  var detalii = [];
  if(c.video){ detalii.push(c.video.toUpperCase()); }
  if(c.audio && c.audio.length){ detalii.push("sunet " + c.audio.join(", ")); }
  if(c.radio){ detalii.push("radio"); }
  var text = c.merge ? (c.avertizare || "") : (c.motiv || "");
  if(detalii.length || text){ var s = document.createElement("span"); s.className = "sub"; s.textContent = [detalii.join(", "), text].filter(Boolean).join(". "); st.appendChild(s); }
  li.appendChild(st);
  if(c.merge){
    var b = document.createElement("button"); b.textContent = "Pornește"; b.addEventListener("click", function(){ porneste(c.ref, c.nume); }); li.appendChild(b);
  }
  return li;
}
function citesteCanalele(){
  // ce poate browserul: aceleasi verificari ca playerul comun (HEVC prin MediaSource, AC-3 prin MediaSource sau prin
  // decodorul wasm al paginii, MPEG-2 prin playerul wasm)
  var pt = (window.HdsPlayer && HdsPlayer.poate) ? HdsPlayer.poate() : {hevc: false, ac3: false, wasm: false};
  return cerere("/api/tv-canale?hevc=" + (pt.hevc ? "1" : "0") + "&ac3=" + (pt.ac3 ? "1" : "0") + "&wasm=" + (pt.wasm ? "1" : "0")).then(function(d){
    var merg = $("merg"), nu = $("nuMergLista"); merg.textContent = ""; nu.textContent = "";
    var nr_nu = 0;
    (d.canale || []).forEach(function(c){ if(c.merge){ merg.appendChild(randCanal(c)); } else { nu.appendChild(randCanal(c)); nr_nu++; } });
    if(!merg.children.length){ var li = document.createElement("li"); li.textContent = "Niciun canal nu se poate porni acum."; merg.appendChild(li); }
    $("nuMerg").classList.toggle("ascuns", !nr_nu);
  }).catch(function(){});
}
function arataSetari(d){
  ["permis", "standby"].forEach(function(k){ if(document.activeElement !== $(k)){ $(k).value = d[k] ? "1" : "0"; } });
  Array.prototype.forEach.call(document.querySelectorAll(".dupa-permis"), function(r){ r.classList.toggle("ascuns", !d.permis); });
  if(document.activeElement !== $("sesiuni_max")){ $("sesiuni_max").value = String(d.sesiuni_max); }
  if(document.activeElement !== $("asteptare")){
    var s = $("asteptare"); s.textContent = "";
    (d.asteptari || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
    s.value = String(d.asteptare);
  }
  $("pornesteTv").disabled = !d.permis;
}
function arataSesiunile(d){
  var ul = $("sesiuni"); ul.textContent = "";
  (d.sesiuni || []).forEach(function(s){
    var li = document.createElement("li"), st = document.createElement("div");
    var n = document.createElement("span"); n.className = "nume"; n.textContent = s.nume + ", spre " + (s.browser || s.adresa || "?"); st.appendChild(n);
    var sub = document.createElement("span"); sub.className = "sub";
    sub.textContent = "De " + textDurata(s.secunde) + ", " + textOcteti(s.octeti) + (s.cu_spectator ? "" : ", fără spectator acum") + (s.extern ? ", player extern" : "");
    st.appendChild(sub); li.appendChild(st);
    var b = document.createElement("button"); b.textContent = "Oprește"; b.addEventListener("click", function(){ opreste(s.id); }); li.appendChild(b);
    ul.appendChild(li);
  });
  if(!ul.children.length){ var li = document.createElement("li"); li.textContent = "Nicio transmisie acum."; ul.appendChild(li); }
}
function arataMemoria(d){
  var m = d.memorie, t = "";
  if(m && m.ramase !== null && m.ramase !== undefined){
    t = m.ramase > 0 ? ("Porniri noi care se mai pot face până la repornirea receptorului: " + m.ramase + ". O pornire după o pauză ține 4 MB din memoria driverului video până la repornire; schimbarea canalului pe aceeași frecvență și reîncărcarea paginii nu costă nimic.")
      : "Memoria driverului video e pe sfârșite. Repornește receptorul ca să poți transmite din nou.";
  }
  $("memorie").textContent = t;
}
// Revoca: un playlist revocat nu mai merge in niciun player si nu se poate intoarce, deci intai o intrebare in randul
// lui (fara ferestrele browserului, ca in paginile antenei); "Nu" e alegerea pregatita si pune butonul la loc
function intreabaRevoca(li, buton, a){
  if(li.querySelector(".intrebare")){ return; }
  var q = document.createElement("div"); q.className = "intrebare"; q.setAttribute("role", "group");
  var t = document.createElement("p");
  t.textContent = "Revoci " + (a.nume || "playlistul") + "? Playerele care îl folosesc nu mai primesc canalele, iar adresa nu mai merge niciodată. Dacă îl vrei din nou, descarci alt playlist.";
  q.appendChild(t);
  var r = document.createElement("div"); r.className = "butoane";
  var nu = document.createElement("button"); nu.type = "button"; nu.textContent = "Nu";
  var da = document.createElement("button"); da.type = "button"; da.textContent = "Da, revocă";
  nu.addEventListener("click", function(){ li.removeChild(q); buton.classList.remove("ascuns"); buton.focus(); });
  da.addEventListener("click", function(){
    da.disabled = nu.disabled = true;
    var p = new URLSearchParams(); p.set("id", a.id);
    cerere("/api/tv-acces-revoca", "POST", p).then(function(d){ mesaj(d.message, !d.result); citesteAdresele(); })
      .catch(function(){ mesaj("Receptorul nu răspunde.", true); da.disabled = nu.disabled = false; });
  });
  r.appendChild(nu); r.appendChild(da); q.appendChild(r);
  buton.classList.add("ascuns");
  li.appendChild(q);
  nu.focus();
}
function citesteAdresele(){
  return cerere("/api/tv-acces").then(function(d){
    var ul = $("adrese"); ul.textContent = "";
    (d.adrese || []).forEach(function(a){
      var li = document.createElement("li"), st = document.createElement("div");
      var n = document.createElement("span"); n.className = "nume";
      n.textContent = (a.nume || "Playlist") + (a.canale !== null && a.canale !== undefined ? ", " + a.canale + (a.canale === 1 ? " canal" : " canale") : ", toate canalele");
      st.appendChild(n);
      var sub = document.createElement("span"); sub.className = "sub";
      sub.textContent = "Făcut " + textData(a.creat) + (a.browser ? " din " + a.browser : "") + ". Expiră: " + textData(a.expira) + (a.folosit ? ". Folosit ultima dată " + textData(a.folosit) : "");
      st.appendChild(sub); li.appendChild(st);
      var b = document.createElement("button"); b.textContent = "Revocă";
      b.addEventListener("click", function(){ intreabaRevoca(li, b, a); });
      li.appendChild(b);
      ul.appendChild(li);
    });
    if(!ul.children.length){ var li = document.createElement("li"); li.textContent = "Niciun playlist dat."; ul.appendChild(li); }
    if(d.max_canale){ MAX_CANALE_APARAT = d.max_canale; verificaMarimea(); }
    arataAparatele(d.aparate);
  }).catch(function(){});
}
function citesteStarea(){
  return cerere("/api/tv-stare").then(function(d){
    if(!d.result){ return; }
    ultimaStare = d;
    arataSetari(d); arataSesiunile(d); arataMemoria(d);
    // televizorul a trecut pe alt canal: lista a ce merge acum se schimba
    var tv = d.tv ? d.tv.ref : "";
    if(ultimulTv !== null && tv !== ultimulTv){ citesteCanalele(); }
    ultimulTv = tv;
    if(!d.permis){ mesaj("Transmisia în browser e oprită din setări."); }
  }).catch(function(){});
}
// ---------------------------------------------------------------- aparatele din casa (aparate_web.py)
// cheia unui aparat nu expira; adresele lui (cu cheia) se arata o singura data, la adaugare; lista arata numele, canalele,
// cand a fost adaugat si folosit; redenumirea si revocarea (cu intrebare in rand, "Nu" ales) nu ating adresele altora
var TA = __APARATE_TEXTE__;
__APARATE_JS__
function textTA(cheie){
  // textul tradus cu valorile in locul fiecarui %s, in ordine
  var text = TA[cheie] || "";
  Array.prototype.slice.call(arguments, 1).forEach(function(v){ text = text.replace("%s", v); });
  return text;
}
var MAX_CANALE_APARAT = 0, SURSE_UMPLUTE = false;
function cardAparate(){ return $("cardAparate"); }
function randAparat(a){
  var li = document.createElement("li"); li.className = "aparat-rand";
  var st = document.createElement("div");
  var n = document.createElement("span"); n.className = "nume"; n.textContent = a.nume; st.appendChild(n);
  var sub = document.createElement("span"); sub.className = "sub";
  sub.textContent = [textTA("rand_canale", a.sursa || "?"),
    textTA("rand_adaugat", textData(a.creat) + (a.browser ? " (" + a.browser + ")" : "")),
    a.folosit ? textTA("rand_folosit", textData(a.folosit)) : TA.rand_nefolosit].join(" ");
  st.appendChild(sub);
  if(a.taiat){
    // playlistul are numai primele canale (satelitul televizorului intai); omul poate alege o lista mai mica
    var taiat = document.createElement("span"); taiat.className = "taiat";
    taiat.textContent = textTA("taiat", a.taiat[0], a.taiat[1]);
    st.appendChild(taiat);
  }
  li.appendChild(st);
  var butoane = document.createElement("div"); butoane.className = "butoane-rand";
  var ren = document.createElement("button"); ren.type = "button"; ren.textContent = TA.redenumeste;
  var rev = document.createElement("button"); rev.type = "button"; rev.textContent = TA.revoca;
  ren.addEventListener("click", function(){ redenumesteAparat(li, butoane, a); });
  rev.addEventListener("click", function(){ intreabaRevocaAparat(li, butoane, a); });
  butoane.appendChild(ren); butoane.appendChild(rev); li.appendChild(butoane);
  return li;
}
function redenumesteAparat(li, butoane, a){
  if(li.querySelector(".redenumire, .intrebare")){ return; }
  var f = document.createElement("form"); f.className = "redenumire";
  var camp = document.createElement("input"); camp.type = "text"; camp.maxLength = 40; camp.value = a.nume;
  camp.setAttribute("aria-label", TA.nume);
  var da = document.createElement("button"); da.type = "submit"; da.textContent = TA.salveaza;
  var nu = document.createElement("button"); nu.type = "button"; nu.textContent = TA.renunta;
  nu.addEventListener("click", function(){ li.removeChild(f); butoane.classList.remove("ascuns"); butoane.firstChild.focus(); });
  f.addEventListener("submit", function(e){
    e.preventDefault();
    da.disabled = nu.disabled = true;
    var p = new URLSearchParams(); p.set("id", a.id); p.set("nume", camp.value);
    cerere("/api/tv-aparat-redenumeste", "POST", p).then(function(d){
      if(!d.result){ da.disabled = nu.disabled = false; aparatStare(cardAparate(), d.message, true); camp.focus(); return; }
      aparatStare(cardAparate(), d.message);
      citesteAdresele();
    }).catch(function(){ da.disabled = nu.disabled = false; aparatStare(cardAparate(), TA.nu_raspunde, true); });
  });
  f.appendChild(camp); f.appendChild(da); f.appendChild(nu);
  butoane.classList.add("ascuns");
  li.appendChild(f);
  camp.focus(); camp.select();
}
function intreabaRevocaAparat(li, butoane, a){
  if(li.querySelector(".redenumire, .intrebare")){ return; }
  var q = document.createElement("div"); q.className = "intrebare"; q.setAttribute("role", "group");
  var t = document.createElement("p"); t.textContent = textTA("intrebare_revoca", a.nume); q.appendChild(t);
  var r = document.createElement("div"); r.className = "butoane";
  var nu = document.createElement("button"); nu.type = "button"; nu.textContent = TA.nu;
  var da = document.createElement("button"); da.type = "button"; da.textContent = TA.da_revoca;
  nu.addEventListener("click", function(){ li.removeChild(q); butoane.classList.remove("ascuns"); butoane.firstChild.focus(); });
  da.addEventListener("click", function(){
    da.disabled = nu.disabled = true;
    var p = new URLSearchParams(); p.set("id", a.id);
    cerere("/api/tv-acces-revoca", "POST", p).then(function(d){ aparatStare(cardAparate(), d.message, !d.result); citesteAdresele(); })
      .catch(function(){ aparatStare(cardAparate(), TA.nu_raspunde, true); da.disabled = nu.disabled = false; });
  });
  r.appendChild(nu); r.appendChild(da); q.appendChild(r);
  butoane.classList.add("ascuns");
  li.appendChild(q);
  nu.focus();
}
function arataAparatele(lista){
  var ul = $("aparate"); ul.textContent = "";
  (lista || []).forEach(function(a){ ul.appendChild(randAparat(a)); });
  if(!ul.children.length){ var li = document.createElement("li"); li.textContent = TA.niciunul; ul.appendChild(li); }
}
function optiune(parinte, valoare, text, eticheta, numar){
  var o = document.createElement("option"); o.value = valoare; o.textContent = text;
  o.setAttribute("data-eticheta", eticheta || text);
  if(numar){ o.setAttribute("data-n", String(numar)); }
  parinte.appendChild(o);
  return o;
}
function verificaMarimea(){
  // lista aleasa are mai multe canale decat primeste un aparat: se spune inainte, nu dupa
  var s = $("aparatSursa"), o = s.options[s.selectedIndex], n = o ? parseInt(o.getAttribute("data-n") || "0", 10) : 0;
  $("aparatMarime").textContent = (MAX_CANALE_APARAT && n > MAX_CANALE_APARAT) ? textTA("taiat", MAX_CANALE_APARAT, n) : "";
}
function umpleSursele(){
  // listele de pe televizor (Favorite si celelalte) si satelitii din Toate canalele, ca in pagina Canale; la prima
  // umplere alegerea pregatita e Favorite (lista de pe televizor), nu toate canalele
  var s = $("aparatSursa");
  var nimic = function(){ return {}; };
  Promise.all([cerere("/api/canale-buchete?fila=tv").catch(nimic), cerere("/api/canale-lista?fila=tv&buchet=toate&grupe=1").catch(nimic)])
    .then(function(r){
      var ales = s.value;
      while(s.children.length > 1){ s.removeChild(s.lastChild); }
      if(r[1].total){ s.options[0].setAttribute("data-n", String(r[1].total)); }
      var g = document.createElement("optgroup"); g.label = TA.liste;
      var favorite = null;
      (r[0].buchete || []).forEach(function(b){
        if(b.id === "toate"){ return; }
        var o = optiune(g, "buchet:" + b.id, b.nume, b.nume, b.numar);
        if(favorite === null && b.id.indexOf("userbouquet.favourites.") === 0){ favorite = o.value; }
      });
      if(g.children.length){ s.appendChild(g); }
      var sat = document.createElement("optgroup"); sat.label = TA.sateliti;
      (r[1].grupe || []).forEach(function(x){ optiune(sat, "grupa:" + x.g, x.nume + " (" + (x.nt || x.n) + ")", x.nume, x.n); });
      if(sat.children.length){ s.appendChild(sat); }
      s.value = (!SURSE_UMPLUTE && favorite) ? favorite : ales;
      if(s.selectedIndex < 0){ s.selectedIndex = 0; }
      SURSE_UMPLUTE = true;
      verificaMarimea();
    });
}
$("aparatSursa").addEventListener("change", verificaMarimea);
$("formAparat").addEventListener("submit", function(e){
  e.preventDefault();
  var s = $("aparatSursa"), o = s.options[s.selectedIndex], v = s.value || "toate", k = v.indexOf(":");
  var campuri = {nume: $("aparatNume").value, sursa: k > 0 ? v.slice(0, k) : v, id: k > 0 ? v.slice(k + 1) : "",
    eticheta: o ? (o.getAttribute("data-eticheta") || o.textContent) : ""};
  aparatStare(cardAparate(), TA.se_adauga);
  aparatAdauga(campuri, $("aparatAdauga"), cardAparate().querySelector(".aparat-adrese"), function(){
    aparatStare(cardAparate(), "");
    $("aparatNume").value = "";
    citesteAdresele();
  }).catch(function(err){ aparatStare(cardAparate(), err.message || TA.nu_raspunde, true); });
});
function trimiteSetarea(cheie, valoare){
  var q = new URLSearchParams(); q.set(cheie, valoare);
  cerere("/api/tv-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); citesteStarea(); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
["permis", "standby", "sesiuni_max", "asteptare"].forEach(function(k){ $(k).addEventListener("change", function(){ trimiteSetarea(k, $(k).value); }); });
$("pornesteTv").addEventListener("click", function(){ porneste("", ""); });
$("reimprospateaza").addEventListener("click", citesteCanalele);
if(window.HdsPlayer){
  player = HdsPlayer.creeaza($("player"), {csrf: CFG.csrf, jeton: CFG.jeton, m3u: true});
  player.mesaj("Alege un canal și apasă Pornește.");
} else {
  mesaj("Playerul nu s-a încărcat de pe receptor.", true);
}
if(CFG.jeton){ mesaj("Transmisia merge numai cu browserul conectat. Deschide pagina fără cheia din adresă.", true); }
citesteStarea().then(citesteCanalele);
citesteAdresele();
umpleSursele();
setInterval(function(){ if(!document.hidden){ citesteStarea(); } }, 5000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("TV în browser"),
		N_("Pornește canalul de pe televizor"),
		N_("Poți vedea acum"),
		N_("Canalele de pe frecvența televizorului merg mereu. Altele merg numai dacă un tuner e liber și "
			"antena nu trebuie să se rotească."),
		N_("Nu merg acum"),
		N_("Reîmprospătează lista"),
		N_("Transmisii active"),
		N_("Televizorul și înregistrările au prioritate: o transmisie se oprește singură înainte ca "
			"televizorul sau o înregistrare să aibă nevoie de tunerul ei."),
		N_("Playlisturi pentru playerele din casă"),
		N_("Un playlist (M3U) descărcat de aici sau din lista de canale deschide în VLC, Kodi sau alt "
			"player numai canalele din el, numai din rețeaua de acasă. Adresa unui canal ține 7 zile, a unei "
			"liste 30 de zile; o poți revoca oricând."),
		N_("Setări"),
		N_("Permite transmisia în browser"),
		N_("Da"),
		N_("Nu"),
		N_("Permite transmisia în standby"),
		N_("Cel mult transmisii odată"),
		N_("Oprire când nu se mai uită nimeni, după"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Redarea folosește biblioteca mpegts.js "
			"(Apache-2.0), venită cu imaginea: <a href=\"/tv/mpegts-licenta.txt\">licența</a>. Canalele cu "
			"imagine MPEG-2 și sunetul AC-3 (unde browserul nu îl redă singur) se decodează în browser, pe "
			"procesorul calculatorului, cu decodorul FFmpeg (LGPL-2.1) venit tot cu imaginea: <a "
			"href=\"/tv/tv-wasm/ffmpeg-licenta.txt\">licența și sursa</a>; toate licențele sunt în <a "
			"href=\"/licente\">Licențe</a>."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("fără termen"),
		N_("Receptorul nu răspunde."),
		N_("(pe televizor)"),
		N_("Pornește"),
		N_("Niciun canal nu se poate porni acum."),
		N_(", spre"),
		N_(", fără spectator acum"),
		N_(", player extern"),
		N_("Oprește"),
		N_("Nicio transmisie acum."),
		N_("Porniri noi care se mai pot face până la repornirea receptorului:"),
		N_(". O pornire după o pauză ține 4 MB din memoria driverului video până la repornire; schimbarea "
			"canalului pe aceeași frecvență și reîncărcarea paginii nu costă nimic."),
		N_("Memoria driverului video e pe sfârșite. Repornește receptorul ca să poți transmite din nou."),
		N_("Revoci"),
		N_("? Playerele care îl folosesc nu mai primesc canalele, iar adresa nu mai merge niciodată. Dacă "
			"îl vrei din nou, descarci alt playlist."),
		N_("Nu"),
		N_("Da, revocă"),
		N_("Playlist"),
		N_(", toate canalele"),
		N_("Făcut"),
		N_("din"),
		N_(". Expiră:"),
		N_(". Folosit ultima dată"),
		N_("Revocă"),
		N_("Niciun playlist dat."),
		N_("Transmisia în browser e oprită din setări."),
		N_("Alege un canal și apasă Pornește."),
		N_("Playerul nu s-a încărcat de pe receptor."),
		N_("Transmisia merge numai cu browserul conectat. Deschide pagina fără cheia din adresă."),
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
