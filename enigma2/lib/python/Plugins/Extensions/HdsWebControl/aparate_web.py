# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# aparate_web.py: aparatele din casa care tin o lista de canale pe termen lung (Kodi cu PVR IPTV Simple, Emby,
# Jellyfin, Plex, VLC, televizoare cu aplicatii IPTV) folosesc receptorul ca sursa de canale si de ghid TV.
# Fiecare aparat are cheia lui (acces_extern.py, fel "aparat", cu nume dat de om, fara termen,
# revocabila) si adrese care nu se schimba:
#   GET|HEAD /tv-extern/<cheie>/canale.m3u          playlistul: canalele TV ale sursei, citite din nou la fiecare cerere
#   GET|HEAD /tv-extern/<cheie>/ghid.xml            ghidul XMLTV al acelorasi canale (gzip cand clientul il accepta)
#   GET|HEAD /tv-extern/<cheie>/sigla/<nume>.png    sigla unui canal (numai cele gasite pe disc de canale_web)
#   GET|HEAD /tv-extern/<cheie>/<canal>.ts          fluxul (tv_web.fluxExtern, aceleasi reguli ca la playlisturi)
# Rutele de mai sus le leaga tv_web.ruteExterne (numai din reteaua locala, cheia in adresa, fara jetonul API); API-ul
# paginii (tv_web.rute, poarta comuna; ce schimba cere POST, aceeasi origine si antetul CSRF, nu ?token=):
#   POST /api/tv-aparat-adauga       nume=&sursa=toate|buchet|grupa|filtru&id=&buchet=&text=&filtre=&eticheta=
#   POST /api/tv-aparat-redenumeste  id=&nume=
#   GET  /api/tv-acces               playlisturile si aparatele (fara chei); revocarea: POST /api/tv-acces-revoca?id=
#
# SURSA LISTEI (cheia.sursa): {"fel": "toate"} toate canalele TV, pe sateliti (group-title = satelitul); {"fel":
# "buchet", "id": fisierul buchetului} o lista de pe televizor, de pilda Favorite (group-title = numele listei); {"fel":
# "grupa", "id": "192"} un satelit din "Toate canalele"; {"fel": "filtru", "buchet": .., "text": .., "filtre": {grup:
# [valori]}} lista si filtrele din /canale; {"fel": "selectie", "filtre": {grup: [valori]}, "furnizor": .., "grupa":
# ..} o categorie din pagina /playlisturi (playlisturi_web.py): trasaturile indexului (aceleasi reguli ca filtrele de
# pe televizor, Index.conditii), furnizorul canalului si / sau un satelit. "toate", "grupa" si "selectie" se iau direct
# din indexul de canale (gen_brute), pe grupe in ordineAparat: satelitul canalului de pe televizor primul, apoi ceilalti
# dupa pozitia orbitala, cablul si terestrul la sfarsit; "buchet" si "filtru" din listele paginii /canale
# (canale_web.gen_lista, gen_filtreaza).
# "eticheta" e numele aratat omului. Un buchet sters da un playlist gol, nu o eroare.
#
# PLAYLISTUL: tvg-id = codul canalului din adresa fluxului (acces_extern.codCanal pe referinta curatata), acelasi cu
# id-ul canalului din XMLTV; tvg-name, tvg-chno (numarul telecomenzii, la buchete), tvg-logo numai pentru siglele gasite
# pe disc, group-title (virgula zecimala a pozitiei devine punct: unele playere taie randul la virgula). Antetul
# #EXTM3U are adresa ghidului (x-tvg-url, url-tvg). Cel mult MAX_CANALE_APARAT canale; o lista taiata are dupa antet
# un comentariu "# HD Satelit: Canale în listă: N din M...", iar pagina /tv il arata in randul aparatului.
# MEMORIA (masurat pe receptor: 10-11 s la fiecare cerere, construirea listei, nu numarul canalelor):
# playlistul unei surse se tine ca text cu BAZA in locul adresei (ListaAparat, _LISTE), cel mult VIATA_PLAYLIST_S si
# numai cat fisierele listelor de canale (lamedb, bouquets.*, userbouquet.*) sunt aceleasi; o cerere din memorie face
# un os.stat pe fisiere si un str.replace. Facerea lui: pe firul enigma2 numai copia indexului (sau listele /canale) si
# siglele, iar curatarea, gruparea si textul pe firul "aparate" al furnizorului (gen_pe_fir): interfata nu sta.
# Antetele X-HDS-Lista (memorie / noua), X-HDS-Canale (N/M) si X-HDS-Ms dau masuratorile fara jurnal.
#
# GHIDUL: din eEPGCache (lookupEvent, o cerere pe canal, ZILE_GHID zile de acum), titlul, subtitlul (descrierea scurta),
# descrierea, orele "AAAALLZZhhmmss +hhmm" cu fusul receptorului. Se face pe felii pe firul enigma2 (planificatorul din
# canale_web: un singur eTimer, felii de BUGET_S, poll() intre ele), comprimat pe masura (zlib, gzip) si tinut numai
# comprimat. UN SINGUR generator odata (celelalte surse asteapta la coada); lucrarea merge mai departe si daca playerul
# care a cerut-o pleaca. Memoria: cel mult MAX_GHIDURI ghiduri; unul mai nou de VIATA_GHID_S se da pe loc; pana la
# VIATA_MAXIMA_S se da cel vechi si se face altul in fundal. Limite: MAX_EMISIUNI_CANAL emisiuni pe canal, MAX_OCTETI_XML
# octeti necomprimati (peste: restul canalelor fara emisiuni, scris in jurnal). Fara gzip in Accept-Encoding, ghidul se
# dezarhiveaza pe felii. Raspunsul pleaca pe bucati, cu ritmul legaturii (Ritm, request.registerProducer): un player
# care citeste incet nu face sa stea tot textul in memoria legaturii.
#
# PAGINILE: cardul "Aparate din casa" din /tv (adaugarea, lista cu ultima folosire, redenumirea, revocarea cu intrebare,
# ajutorul pentru playere) si fereastra "Adresa fixa pentru un aparat" din /canale (lista si filtrele de acum) si din
# /cautare (cautarea de acum, cand se potriveste cu sursa "filtru": cautare_web.aparat_din); deschiderea ei si adaugarea
# sunt in scriptul comun (aparatDeschide). Textele lor trec prin traducere la servire (TEXTE, N_). Pe televizor:
# Screens/HdsTransmisie.py, tasta GALBEN.
#
# FIRUL: totul pe firul enigma2; listele si ghidul pe felii (canale_web.PeBucati), siglele citite pe firul de citire al
# paginii /canale. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau furnizorul lor (F), modulul
# canale_web (C), acces_extern (A) si plugin.py (P).

import calendar
import collections
import html
import json
import re
import time
import zlib


def N_(text):
	"""marcheaza textul pentru xgettext (po/Makefile.am --keyword=N_); traducerea se face la folosire, cu _t"""
	return text


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


# ZILE_GHID: fereastra ghidului, de acum. eEPGCache tine tot ce trimit satelitii (de obicei 7-8 zile, la unele programe
# mai mult) si nu are o setare a zilelor; fereastra le cuprinde pe toate, deci ghidul are zilele cate are receptorul.
# MAX_EMISIUNI_CANAL ajunge pentru ZILE_GHID zile cu emisiuni de 30 de minute.
ZILE_GHID = 14
VIATA_GHID_S = 300
VIATA_MAXIMA_S = 3600
MAX_GHIDURI = 2
TERMEN_GHID_S = 240           # lucrarea care face un ghid (pe felii)
ASTEAPTA_GHID_S = 90          # cat asteapta o cerere un ghid in lucru; apoi 503 cu Retry-After
REVINO_GHID_S = 30
TERMEN_LISTA_S = 30
# PLAYLISTUL IN MEMORIE (masurat pe receptor: 10-11 s la fiecare cerere, oricate canale): cel mult
# MAX_LISTE_APARAT playlisturi, fiecare cel mult VIATA_PLAYLIST_S si numai cat fisierele listelor nu s-au schimbat
VIATA_PLAYLIST_S = 300
MAX_LISTE_APARAT = 4
TERMEN_FIR_S = 60             # partea de pe fir a unui playlist (copia indexului -> text)
PAS_INDEX = 500               # canale din index citite pe firul enigma2 intre doua cedari
# MAX_CANALE_APARAT: cate canale primeste un aparat. Masurat pe PC (8500 de servicii pe 9 locuri, 7847 TV):
# prima facere ~10 us pe canal (76 ms; pe firul enigma2 18
# pasi, cel mai lung 0,55 ms, 2,9 ms in total, restul pe fir), textul M3U 1,2 MB, o cerere din memorie 2 ms
# (str.replace + encode), ghidul fara emisiuni ~3 us pe canal (plus un lookupEvent pe canal pe receptor). Python pe
# ARM-ul receptorului e de ~15-30 de ori mai incet decat pe PC: la 8000 de canale ~1-2,5 s prima cerere (pe fir,
# interfata nu sta) si ~0,1 s din memorie. Peste atat creste si ghidul (cate un lookupEvent pe canal) si playerele se
# misca greu cu lista; omul alege atunci un satelit sau o lista (pagina il anunta).
MAX_CANALE_APARAT = 8000
MAX_EMISIUNI_CANAL = 700
MAX_TITLU = 200
MAX_SUBTITLU = 200
MAX_DESC = 1500
MAX_OCTETI_XML = 40 * 1024 * 1024
PAS_EMISIUNI = 40             # emisiuni formatate intre doua cedari ale firului
PAS_CANALE = 50
BUCATA_GZ = 64 * 1024         # cat din forma comprimata se da odata dezarhivarii (fara gzip in Accept-Encoding)
BUCATA_IESIRE = 256 * 1024    # cel mult atat text dezarhivat pe un pas
BUCATA_SCRIERE = 128 * 1024   # forma comprimata se scrie pe bucati atat de mari, cu ritmul legaturii
TERMEN_TRIMITERE_S = 600      # cat poate dura trimiterea ghidului spre un player care citeste incet
MAX_TEXT_SURSA = 40
MAX_ETICHETA = 80
MAX_FILTRE = 12
MAX_VALORI = 64
FELURI_SURSA = ("toate", "buchet", "grupa", "filtru", "selectie")
MAX_FURNIZOR = 80
RUTE = ("canale.m3u", "ghid.xml", "sigla")
_RE_GRUPA = re.compile(r"^[A-Za-z0-9_.-]{1,16}$")
_RE_GRUP_FILTRU = re.compile(r"^[a-z_]{1,12}$")
# XML 1.0 nu primeste caracterele de control (afara de tab si rand nou), surogatele si U+FFFE / U+FFFF; din EPG-ul DVB
# vin si codurile C1 (0x86 / 0x87 sublinierea, 0x8A randul nou)
_XML_RAU = re.compile(u"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\ud800-\udfff￾￿]")

TEXTE = {
	"titlu": N_("Aparate din casă"),
	"intro": N_("Un aparat din casă (un player cu listă de canale, un server media sau un televizor cu aplicație IPTV) primește două adrese care nu expiră: lista de canale (M3U) și ghidul TV (XMLTV). Lista se citește din nou la fiecare cerere, deci canalele noi apar singure. Adresele merg numai din rețeaua de acasă, cu aceleași limite ca transmisia în browser."),
	"nume": N_("Numele aparatului"),
	"nume_exemplu": N_("de pildă Kodi sufragerie"),
	"canale": N_("Canalele"),
	"toate": N_("Toate canalele TV, pe sateliți"),
	"liste": N_("Liste"),
	"sateliti": N_("Sateliți"),
	"adauga": N_("Adaugă aparatul"),
	"se_adauga": N_("Se adaugă aparatul..."),
	"o_data": N_("Copiază acum cele două adrese în aparat: se arată numai o dată. Dacă le pierzi, adaugi aparatul din nou și îl revoci pe cel vechi."),
	"adresa_m3u": N_("Lista de canale (M3U)"),
	"adresa_ghid": N_("Ghidul TV (XMLTV)"),
	"copiaza": N_("Copiază"),
	"copiat": N_("Copiat."),
	"copiaza_manual": N_("Selectează adresa și copiaz-o cu Ctrl+C."),
	"gata": N_("Gata"),
	"niciunul": N_("Niciun aparat adăugat."),
	"taiat": N_("Canale în listă: %s din %s. Alege un satelit sau o listă."),
	"rand_canale": N_("Canale: %s."),
	"rand_adaugat": N_("Adăugat %s."),
	"rand_folosit": N_("Folosit ultima dată %s."),
	"rand_nefolosit": N_("Încă nefolosit."),
	"redenumeste": N_("Redenumește"),
	"salveaza": N_("Salvează"),
	"renunta": N_("Renunță"),
	"revoca": N_("Revocă"),
	"intrebare_revoca": N_("Revoci aparatul %s? Nu mai primește canalele și ghidul TV, iar adresele lui nu mai merg niciodată. Dacă îl vrei din nou, îl adaugi din nou."),
	"nu": N_("Nu"),
	"da_revoca": N_("Da, revocă"),
	"ajutor": N_("Cum pui adresele în aparat"),
	"ajutor_kodi": N_("Kodi: instalează extensia PVR IPTV Simple Client. În setările ei alege pentru listă locația Remote path (Internet address) și pune adresa listei de canale la M3U Play List URL; la EPG alege tot Remote path și pune adresa ghidului la XMLTV URL. Apoi repornește Kodi."),
	"ajutor_emby": N_("Emby și Jellyfin: la Live TV adaugă un tuner de tipul M3U cu adresa listei de canale, apoi un furnizor de ghid TV de tipul XMLTV cu adresa ghidului. Pune 1 la numărul de fluxuri odată. Canalele se potrivesc singure cu ghidul."),
	"ajutor_vlc": N_("VLC: Media, Deschide flux din rețea, apoi adresa listei de canale (fără ghid)."),
	"ajutor_limite": N_("Un aparat primește o singură transmisie: când schimbi canalul în el, transmisia veche se oprește. Pe receptoarele cu antenă cu motor sau cu un singur tuner de satelit merg numai canalele de pe frecvența televizorului."),
	"din_canale": N_("Adresă fixă pentru un aparat"),
	"din_canale_text": N_("Lista aleasă și filtrată acum devine lista unui aparat din casă. Se citește din nou la fiecare cerere, deci canalele noi care se potrivesc apar singure."),
	"numai_tv": N_("Numai canalele TV se pot da unui aparat. Alege fila TV."),
	"vezi_tv": N_("Aparatele se văd, se redenumesc și se revocă în pagina TV în browser."),
	"nu_raspunde": N_("Receptorul nu răspunde."),
	"inchide": N_("Închide"),
	"playlisturi": N_("Playlisturi"),
}


def texte():
	"""{cheie: textul tradus in limba interfetei}"""
	return dict((k, _t(v)) for k, v in TEXTE.items())


def _c(C=None):
	if C is not None:
		return C
	from . import canale_web
	return canale_web


def _a(A=None):
	if A is not None:
		return A
	from . import acces_extern
	return acces_extern


def _p(P=None):
	if P is not None:
		return P
	from . import plugin
	return plugin


def _h(H=None):
	if H is not None:
		return H
	from Components import HdsTransmisie
	return HdsTransmisie


def _jurnal(text):
	print("[HdsWebControl] aparate: %s" % text)


# ---------------------------------------------------------------- sursa listei

def curataEticheta(text, maxim=MAX_ETICHETA):
	text = "".join(ch for ch in str(text or "") if ch >= " " and not ("\x7f" <= ch <= "\x9f"))
	return " ".join(text.split())[:maxim].strip()


def _filtre(text):
	"""filtre= (JSON {grup: [valori]}, din pagina /canale) -> {grup: [valori text]}; ce nu are forma buna se lasa."""
	try:
		d = json.loads(text or "{}")
	except ValueError:
		return {}
	rez = {}
	if not isinstance(d, dict):
		return rez
	for g, valori in list(d.items())[:MAX_FILTRE]:
		if not isinstance(g, str) or not _RE_GRUP_FILTRU.match(g) or not isinstance(valori, list):
			continue
		v = [str(x)[:32] for x in valori[:MAX_VALORI] if isinstance(x, (str, int)) and str(x)]
		if v:
			rez[g] = v
	return rez


def sursaDin(campuri, C=None):
	"""Campurile cererii -> (sursa, None) sau (None, motivul). Filtrul fara text si fara filtre devine lista lui."""
	C = _c(C)
	fel = campuri.get("sursa") or ""
	eticheta = curataEticheta(campuri.get("eticheta"))
	if fel == "filtru":
		buchet = campuri.get("buchet") or C.TOATE
		if buchet != C.TOATE and not C._ID_BUCHET.match(buchet):
			return None, _t("Lista aleasă nu există pe receptor.")
		text = C.curat(campuri.get("text") or "", MAX_TEXT_SURSA)
		filtre = _filtre(campuri.get("filtre"))
		if text or filtre:
			s = {"fel": "filtru", "buchet": buchet, "text": text, "filtre": filtre}
		elif buchet == C.TOATE:
			s = {"fel": "toate"}
		else:
			s = {"fel": "buchet", "id": buchet}
	elif fel == "toate":
		s = {"fel": "toate"}
	elif fel == "buchet":
		id_ = campuri.get("id") or ""
		if id_ == C.TOATE:
			s = {"fel": "toate"}
		elif C._ID_BUCHET.match(id_):
			s = {"fel": "buchet", "id": id_}
		else:
			return None, _t("Lista aleasă nu există pe receptor.")
	elif fel == "grupa":
		id_ = campuri.get("id") or ""
		if not _RE_GRUPA.match(id_):
			return None, _t("Lista aleasă nu există pe receptor.")
		s = {"fel": "grupa", "id": id_}
	elif fel == "selectie":
		filtre = _filtre(campuri.get("filtre"))
		furnizor = curataEticheta(campuri.get("furnizor"), MAX_FURNIZOR)
		grupa = campuri.get("grupa") or ""
		if grupa and not _RE_GRUPA.match(grupa):
			return None, _t("Lista aleasă nu există pe receptor.")
		if not filtre and not furnizor:
			s = {"fel": "grupa", "id": grupa} if grupa else {"fel": "toate"}
		else:
			s = {"fel": "selectie", "filtre": filtre, "furnizor": furnizor, "grupa": grupa}
	else:
		return None, _t("Alege canalele aparatului.")
	if not eticheta:
		baza = _t("Toate canalele TV") if C.TOATE in (s.get("buchet"), s["fel"]) or s["fel"] == "toate" else (
			s.get("id") or s.get("buchet") or s.get("furnizor") or s.get("grupa") or "")
		eticheta = curataEticheta(" ".join(x for x in (baza, s.get("text") or "") if x))
	s["eticheta"] = eticheta
	return s, None


def semnSursa(sursa):
	"""Ce deosebeste doua liste (fara eticheta): cheia ghidului din memorie."""
	return json.dumps(dict((k, v) for k, v in (sursa or {}).items() if k != "eticheta"), sort_keys=True,
		ensure_ascii=True)


def textGrup(text, A=None):
	"""group-title: virgula zecimala a pozitiei ("19,2°E") devine punct; fara ghilimele si caractere de control."""
	return _a(A)._curataText((text or "").replace(",", "."), 80)


class ListaAparat(object):
	"""Playlistul unei surse, tinut in memorie (_LISTE): canalele [(ref curata, nume, grup, sigla, numar)], cate canale
	TV avea sursa (`total`; mai multe decat canalele = lista taiata la MAX_CANALE_APARAT), textul M3U cu BAZA in locul
	adresei (o cerere pune adresa ei cu un singur str.replace) si cat a durat facerea lui."""
	__slots__ = ("semn", "sem", "ora", "canale", "total", "sablon", "ms", "nr")

	def __init__(self, semn, sem, canale, total, sablon, ms):
		self.semn = semn
		self.sem = sem
		self.ora = time.monotonic()
		self.canale = canale
		self.total = total
		self.sablon = sablon
		self.ms = ms
		_NUMAR[0] += 1
		self.nr = _NUMAR[0]       # al catelea playlist facut (o cerere afla asa daca l-a facut ea sau era in memorie)

	def taiata(self):
		return self.total > len(self.canale)


_LISTE = collections.OrderedDict()
_NUMAR = [0]


def uita_listele():
	"""Goleste playlisturile din memorie (probele)."""
	_LISTE.clear()


def ordineAparat(cheie, tv_poz, X):
	"""Locul unei grupe din "Toate canalele" in playlistul aparatului: satelitul canalului de pe televizor primul (pe el
	se aduna EPG-ul si pe el merge transmisia pe receptoarele cu motor), apoi ceilalti sateliti dupa pozitia orbitala
	(de la vest la est, ca lista Sateliti de pe televizor), apoi cablul, terestrul, posturile DVB-T2 / DAB+ din satelit
	si restul. Asa, cand lista se taie la MAX_CANALE_APARAT, pleaca intai ce e departe de antena de acum."""
	if tv_poz is not None and cheie == str(tv_poz):
		return (0, 0)
	try:
		poz = int(cheie)
	except (TypeError, ValueError):
		poz = None
	if poz is not None:
		return (1, poz - 3600 if poz > 1800 else poz)
	for i, k in enumerate((X.POZ_CABLU, X.POZ_TERESTRU, "t2", "dab")):
		if cheie == k:
			return (2 + i, 0)
	return (6, 0)


def pozitieTv(F, H):
	"""Pozitia satelitului canalului de pe televizor (zecimi de grad, ca in referinta), sau None (cablu, terestru, nimic)."""
	try:
		ref = F.ref_acum()
		return H.pozitieSatelit(ref) if ref else None
	except Exception:
		return None


def semnaturaListelor(F, C):
	"""Ce schimba listele de canale: fisierele lor (lamedb, bouquets.*, userbouquet.*: data si marimea) si alegerea
	"mai multe buchete". Cateva os.stat, la fiecare cerere."""
	return (C.semnatura(F.director()), bool(F.multibuchet()))


def gen_pe_fir(F, functie, fel="aparate"):
	"""Generator: functie() pe firul `fel` al furnizorului; firul enigma2 nu asteapta (pasi de 20 ms pana vine
	rezultatul). -> rezultatul; eroarea de pe fir se ridica aici."""
	cutie = {}
	F.in_fir(functie, lambda r, e: cutie.update(r=r, e=e), fel=fel, termen_s=TERMEN_FIR_S)
	while not cutie:
		yield 20
	if cutie["e"] is not None:
		raise cutie["e"]
	return cutie["r"]


def gen_brute(sursa, F, C, tv_poz):
	"""Generator (pe firul enigma2, pasi scurti): -> functie fara argumente care da, pe fir, canalele sursei in ordinea
	playlistului [(ref, nume, grup, sigla sau None, numar)], inca necuratate. "toate" si "grupa": direct din indexul
	de canale, fara lista paginii /canale (pe receptor, peste 8000 de canale, construirea ei tinea secunde): pe firul
	enigma2 numai copia listei indexului si numele grupelor; "buchet" si "filtru": listele paginii /canale."""
	X = F.X
	fel = (sursa or {}).get("fel")
	if fel in ("toate", "grupa", "selectie"):
		index = F.index()
		yield
		canale = list(index.canale)
		nume = {}
		for i, c in enumerate(canale):
			if i % PAS_INDEX == PAS_INDEX - 1:
				yield
			if c.radio:
				continue
			k = C.cheie_grupa(c)
			if k not in nume:
				nume[k] = C.nume_grupa(k, c, X)
		if fel == "selectie":
			# conditiile se fac aici, pe firul enigma2 (bitii indexului); pe fir numai mastile canalelor
			cond = conditiiSelectie(index, sursa.get("filtre"))
			grupa, furnizor = sursa.get("grupa") or None, sursa.get("furnizor") or ""
			return lambda: bruteIndex(canale, nume, grupa, tv_poz, C, X, cond=cond, masca=index.masca,
				furnizor=furnizor)
		grupa = sursa.get("id") if fel == "grupa" else None
		return lambda: bruteIndex(canale, nume, grupa, tv_poz, C, X)
	rez = []
	if fel == "buchet":
		lista = yield from C.gen_lista(F, "tv", sursa.get("id") or "")
		if lista is not None:
			rez = [(r.ref, r.nume, lista.nume, r.sigla, r.n) for r in lista.randuri if not r.marcaj]
	elif fel == "filtru":
		lista = yield from C.gen_lista(F, "tv", sursa.get("buchet") or C.TOATE)
		if lista is not None:
			grupuri = yield from C.gen_numarare(F, lista)
			sel = C.selectie(dict((g, ",".join(v)) for g, v in (sursa.get("filtre") or {}).items()), grupuri)
			gasite, _n, _poz = yield from C.gen_filtreaza(lista, sursa.get("text") or "", sel, X)
			pe_sateliti = lista.id == C.TOATE
			nume = {}
			for i, r in enumerate(gasite):
				if i % C.UNITATE == C.UNITATE - 1:
					yield
				if pe_sateliti:
					k = C.cheie_grupa(r.canal)
					if k not in nume:
						nume[k] = C.nume_grupa(k, r.canal, X)
					grup = nume[k]
				else:
					grup = lista.nume
				rez.append((r.ref, r.nume, grup, r.sigla, r.n))
	return lambda: rez


def conditiiSelectie(index, filtre):
	"""filtre {grup: [valori ca text]} (sursa "selectie") -> conditiile indexului (Index.conditii: SAU in grup, SI intre
	grupuri); None cand un grup sau toate valorile lui nu exista in index (nimic nu se potriveste: playlistul e gol, nu
	toata lista)."""
	sel = {}
	for g, valori in (filtre or {}).items():
		biti = (getattr(index, "biti", None) or {}).get(g)
		if not biti:
			return None
		existente = dict((str(v), v) for v in biti)
		alese = set(existente[v] for v in valori if v in existente)
		if not alese:
			return None
		sel[g] = alese
	return index.conditii(sel)


def numeFurnizor(c):
	"""Furnizorul canalului (din SDT, lamedb), curatat: cheia categoriilor "furnizor" din /playlisturi."""
	return curataEticheta(getattr(c, "furnizor", "") or "", MAX_FURNIZOR)


def potrivesteSelectia(c, cond, masca, furnizor):
	if cond is None:
		return False
	if furnizor and numeFurnizor(c) != furnizor:
		return False
	return all(masca(c, i, fel) & m for i, m, fel in cond)


def bruteIndex(canale, nume_grupe, grupa, tv_poz, C, X, cond=(), masca=None, furnizor=""):
	"""Pe fir: canalele TV din copia indexului, pe grupe in ordineAparat (sau numai `grupa`), in ordinea indexului in
	fiecare grupa -> [(ref, nume, grup, None, None)]. Sursa "selectie": numai canalele care trec de conditiile `cond`
	(conditiiSelectie; None = niciunul) si au furnizorul `furnizor`."""
	selectie = cond is None or bool(cond) or bool(furnizor)
	pe_grupe = {}
	for c in canale:
		if c.radio:
			continue
		k = C.cheie_grupa(c)
		if grupa is not None and k != grupa:
			continue
		if selectie and not potrivesteSelectia(c, cond, masca, furnizor):
			continue
		pe_grupe.setdefault(k, []).append(c)
	rez = []
	for k in sorted(pe_grupe, key=lambda k: ordineAparat(k, tv_poz, X)):
		g = nume_grupe.get(k) or k
		for c in pe_grupe[k]:
			rez.append((c.ref, C.curat(c.nume_afisat() if hasattr(c, "nume_afisat") else c.nume) or "?", g, None, None))
	return rez


def faLista(brute, sigle, A, H, C, limita=None):
	"""Pe fir (numai text si obiecte noi): canalele DVB, fiecare o data, cel mult `limita` (MAX_CANALE_APARAT) ->
	(canale, cate erau, sablonul M3U)."""
	limita = limita or MAX_CANALE_APARAT
	canale, vazute, total, grupe = [], set(), 0, {}
	for ref, nume, grup, sigla, numar in brute:
		# numai serviciile DVB (fara fluxuri de internet si marcaje); felul serviciului ramane cel din lista TV (si UHD
		# / HEVC cu tipurile noi, pe care un player extern le reda)
		curata = H.refCurata(ref)
		if curata is None or curata in vazute:
			continue
		vazute.add(curata)
		total += 1
		if len(canale) < limita:
			g = grupe.get(grup)
			if g is None:
				g = grupe[grup] = textGrup(grup, A)
			canale.append((curata, nume, g, sigla or C.nume_sigla(curata), numar))
	return canale, total, sablonM3u(canale, sigle, A, total)


def gen_lista_aparat(sursa, F, C=None, H=None, A=None):
	"""Generator (pe felii): playlistul sursei (ListaAparat) din memorie, cat timp fisierele listelor de canale nu s-au
	schimbat si nu e mai vechi de VIATA_PLAYLIST_S; altfel facut din nou, o singura constructie pe sursa odata (a doua
	cerere o asteapta pe prima). La "toate" ordinea tine de satelitul televizorului, deci si memoria."""
	C = _c(C)
	H = _h(H)
	A = _a(A)
	sursa = sursa or {}
	pe_grupe = sursa.get("fel") in ("toate", "selectie")
	tv_poz = pozitieTv(F, H) if pe_grupe else None
	semn = semnSursa(sursa) + ("|tv=%s" % tv_poz if pe_grupe else "")
	sem = semnaturaListelor(F, C)
	tinuta = _LISTE.get(semn)
	if tinuta is not None and tinuta.sem == sem and time.monotonic() - tinuta.ora < VIATA_PLAYLIST_S:
		_LISTE.move_to_end(semn)
		return tinuta
	return (yield from C.gen_unul_pe_fel(("aparat-lista", semn),
		lambda: _gen_fa_lista(sursa, F, C, H, A, semn, sem, tv_poz)))


def _gen_fa_lista(sursa, F, C, H, A, semn, sem, tv_poz):
	inceput = time.monotonic()
	brute = yield from gen_brute(sursa, F, C, tv_poz)
	sigle = yield from C.gen_sigle(F)
	sigle = frozenset(sigle or ())
	canale, total, sablon = yield from gen_pe_fir(F, lambda: faLista(brute(), sigle, A, H, C))
	lista = ListaAparat(semn, sem, canale, total, sablon, int((time.monotonic() - inceput) * 1000))
	_LISTE.pop(semn, None)
	_LISTE[semn] = lista
	while len(_LISTE) > MAX_LISTE_APARAT:
		_LISTE.popitem(last=False)
	_jurnal("playlist facut: %d canale din %d, %d ms" % (len(canale), total, lista.ms))
	return lista


def gen_canale(sursa, F, C=None, H=None, A=None):
	"""Generator (pe felii): canalele playlistului sursei [(ref curata, nume, grup, sigla, numar)] (gen_lista_aparat)."""
	lista = yield from gen_lista_aparat(sursa, F, C, H, A)
	return lista.canale


def starePlaylist(sursa):
	"""(canale in playlist, canale in sursa) din cel mai nou playlist al sursei aflat in memorie, sau None."""
	semn = semnSursa(sursa)
	for k in reversed(_LISTE):
		if k == semn or k.startswith(semn + "|"):
			lista = _LISTE[k]
			return len(lista.canale), lista.total
	return None


# ---------------------------------------------------------------- playlistul

BAZA = "\x00"     # locul adresei http://<gazda>/tv-extern/<cheie>/ in sablon (_curataText scoate din nume orice < " ")


def sablonM3u(canale, sigle, A=None, total=None):
	"""#EXTM3U cu adresa ghidului (si un comentariu cand lista e taiata), apoi pentru fiecare canal #EXTINF (tvg-id,
	tvg-name, tvg-chno, tvg-logo, group-title) si adresa fluxului; BAZA in locul inceputului adreselor."""
	A = _a(A)
	randuri = ['#EXTM3U x-tvg-url="%sghid.xml" url-tvg="%sghid.xml"' % (BAZA, BAZA)]
	if total is not None and total > len(canale):
		randuri.append("# HD Satelit: " + _t("Canale în listă: %s din %s. Alege un satelit sau o listă.") % (
			len(canale), total))
	for ref, nume, grup, sigla, numar in canale:
		cod = A.codCanal(ref)
		nume = A._curataText(nume) or cod
		semne = ['tvg-id="%s"' % cod, 'tvg-name="%s"' % nume]
		if numar:
			semne.append('tvg-chno="%d"' % int(numar))
		if sigla and sigle and sigla in sigle:
			semne.append('tvg-logo="%ssigla/%s.png"' % (BAZA, sigla))
		if grup:
			semne.append('group-title="%s"' % grup)
		randuri.append("#EXTINF:-1 %s,%s" % (" ".join(semne), nume))
		randuri.append(BAZA + cod + ".ts")
	return "\n".join(randuri) + "\n"


def aplicaSablon(sablon, gazda, cheie_text):
	return sablon.replace(BAZA, "http://%s/tv-extern/%s/" % (gazda, cheie_text))


def textM3u(gazda, cheie_text, canale, sigle, A=None, total=None):
	"""Playlistul intreg pentru o cerere (sablonM3u cu adresa ei)."""
	return aplicaSablon(sablonM3u(canale, sigle, A, total), gazda, cheie_text)


# ---------------------------------------------------------------- ghidul (XMLTV)

def oraXmltv(t):
	"""Secundele Unix -> "AAAALLZZhhmmss +hhmm" in ora receptorului, cu fusul ei (tm_gmtoff; fara el, din diferenta fata
	de UTC). Nu strftime("%z"), care pe unele sisteme da numele fusului."""
	t = int(t)
	lt = time.localtime(t)
	dif = getattr(lt, "tm_gmtoff", None)
	if dif is None:
		dif = calendar.timegm(lt) - t
	semn = "+" if dif >= 0 else "-"
	dif = abs(int(dif)) // 60
	return "%04d%02d%02d%02d%02d%02d %s%02d%02d" % (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min, lt.tm_sec,
		semn, dif // 60, dif % 60)


def curatXml(text, maxim):
	"""Text din EPG pentru XML: randul nou DVB (0x8A) devine rand nou, fara caracterele pe care XML 1.0 nu le primeste,
	taiat la `maxim` semne (inainte de escape)."""
	if text is None:
		return ""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	text = str(text).replace("\x8a", "\n").replace("\r\n", "\n").replace("\r", "\n")
	return _XML_RAU.sub("", text).strip()[:maxim]


def _x(text):
	return html.escape(text, quote=False)


def _xa(text):
	return html.escape(text, quote=True)


def textEmisiune(ev, cod):
	"""Tupla lookupEvent "IBDTSE" -> <programme> sau "" (fara inceput, durata sau titlu)."""
	if not ev or len(ev) < 6:
		return ""
	_id, inceput, durata, titlu, scurta, lunga = ev[:6]
	if inceput is None or durata is None:
		return ""
	titlu = curatXml(titlu, MAX_TITLU)
	if not titlu:
		return ""
	try:
		inceput = int(inceput)
		sfarsit = inceput + max(0, int(durata))
	except (TypeError, ValueError):
		return ""
	scurta = curatXml(scurta, MAX_DESC)
	lunga = curatXml(lunga, MAX_DESC)
	rez = ['  <programme start="%s" stop="%s" channel="%s">\n    <title>%s</title>\n' % (oraXmltv(inceput),
		oraXmltv(sfarsit), _xa(cod), _x(titlu))]
	desc = lunga
	if scurta and scurta != titlu and scurta != lunga:
		if len(scurta) <= MAX_SUBTITLU and "\n" not in scurta:
			rez.append("    <sub-title>%s</sub-title>\n" % _x(scurta))
		elif not lunga:
			desc = scurta
		elif not lunga.startswith(scurta):
			desc = (scurta + "\n" + lunga)[:MAX_DESC]
	if desc:
		rez.append("    <desc>%s</desc>\n" % _x(desc))
	rez.append("  </programme>\n")
	return "".join(rez)


def epgReceptor(ref, acum, minute):
	"""Emisiunile canalului `ref` de la `acum` (cea in curs inclusiv) pe `minute` minute: [(I, B, D, T, S, E)]."""
	from enigma import eEPGCache
	return eEPGCache.getInstance().lookupEvent(["IBDTSE", (ref, 0, int(acum), int(minute))]) or []


def gen_xmltv(canale, epg, acum, zile=ZILE_GHID, maxim=MAX_OCTETI_XML, A=None):
	"""Generator (pe felii): ghidul XMLTV al canalelor, comprimat pe masura (gzip). Intai toate <channel>, apoi
	<programme> canal dupa canal (ordinea din DTD). -> (octetii gzip, octetii XML, emisiuni, canale cu emisiuni)."""
	A = _a(A)
	z = zlib.compressobj(6, zlib.DEFLATED, 31)
	bucati = []
	stare = {"octeti": 0}

	def pune(text):
		b = text.encode("utf-8")
		stare["octeti"] += len(b)
		iesit = z.compress(b)
		if iesit:
			bucati.append(iesit)

	pune('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE tv SYSTEM "xmltv.dtd">\n'
		'<tv generator-info-name="HD Satelit" source-info-name="DVB EPG">\n')
	for i, (ref, nume, _g, _s, _n) in enumerate(canale):
		if i % PAS_CANALE == PAS_CANALE - 1:
			yield
		cod = A.codCanal(ref)
		pune('  <channel id="%s">\n    <display-name>%s</display-name>\n  </channel>\n' % (_xa(cod),
			_x(curatXml(nume, 120) or cod)))
	emisiuni = 0
	cu_emisiuni = 0
	minute = int(zile) * 1440
	for i, (ref, _nume, _g, _s, _n) in enumerate(canale):
		try:
			evenimente = epg(ref, acum, minute) or []
		except Exception as e:
			_jurnal("ghidul: EPG-ul canalului %s: %r" % (ref, e))
			evenimente = []
		yield
		if not evenimente:
			continue
		cod = A.codCanal(ref)
		parti = []
		for j, ev in enumerate(evenimente[:MAX_EMISIUNI_CANAL]):
			text = textEmisiune(ev, cod)
			if text:
				parti.append(text)
			if j % PAS_EMISIUNI == PAS_EMISIUNI - 1:
				yield
		if not parti:
			continue
		bloc = "".join(parti)
		if stare["octeti"] + len(bloc) * 2 > maxim:
			_jurnal("ghidul a ajuns la %d octeti: %d canale fara emisiuni" % (stare["octeti"], len(canale) - i))
			break
		pune(bloc)
		emisiuni += len(parti)
		cu_emisiuni += 1
	pune("</tv>\n")
	bucati.append(z.flush())
	return b"".join(bucati), stare["octeti"], emisiuni, cu_emisiuni


class Ghid(object):
	__slots__ = ("semn", "ora", "gz", "octeti", "canale", "emisiuni", "etag")

	def __init__(self, semn, gz, octeti, canale, emisiuni):
		self.semn = semn
		self.ora = time.monotonic()
		self.gz = gz
		self.octeti = octeti
		self.canale = canale
		self.emisiuni = emisiuni
		self.etag = '"g%x-%x-%x"' % (int(time.time()), len(gz), octeti)


_GHID = {"memorie": collections.OrderedDict(), "curent": None, "coada": collections.OrderedDict(), "esec": {}}


def uita():
	"""Goleste memoria ghidurilor, coada lor si playlisturile din memorie (probele)."""
	_LISTE.clear()
	_GHID["memorie"].clear()
	_GHID["coada"].clear()
	_GHID["esec"].clear()
	_GHID["curent"] = None


def _gen_lucru(sursa, F, C, H, A, epg):
	canale = yield from gen_canale(sursa, F, C, H, A)
	yield
	rez = yield from gen_xmltv(canale, epg, int(F.acum()), A=A)
	return 200, (rez, len(canale))


def _cere(semn, sursa, F, C, H, A):
	if _GHID["curent"] == semn or semn in _GHID["coada"]:
		return
	_GHID["coada"][semn] = sursa
	_urmatorul(F, C, H, A)


def _urmatorul(F, C, H, A):
	"""Porneste urmatoarea lucrare din coada, daca nu e alta in curs (un singur generator odata)."""
	if _GHID["curent"] is not None or not _GHID["coada"]:
		return
	semn, sursa = _GHID["coada"].popitem(last=False)
	_GHID["curent"] = semn
	epg = getattr(F, "epg_interval", None) or epgReceptor
	inceput = time.monotonic()

	def gata(cod, corp):
		_GHID["curent"] = None
		if cod == 200:
			(gz, octeti, emisiuni, cu_emisiuni), numar = corp
			mem = _GHID["memorie"]
			mem.pop(semn, None)
			mem[semn] = Ghid(semn, gz, octeti, numar, emisiuni)
			while len(mem) > MAX_GHIDURI:
				mem.popitem(last=False)
			_GHID["esec"].pop(semn, None)
			_jurnal("ghid facut: %d canale (%d cu emisiuni), %d emisiuni, %d KB (%d KB comprimat), %.1f s" % (numar,
				cu_emisiuni, emisiuni, octeti // 1024, len(gz) // 1024, time.monotonic() - inceput))
		else:
			_GHID["esec"][semn] = time.monotonic()
			_jurnal("ghidul nu s-a facut (%s): %s" % (cod, (corp or {}).get("message") if isinstance(corp, dict) else corp))
		_urmatorul(F, C, H, A)

	C.PeBucati(_gen_lucru(sursa, F, C, H, A, epg), gata, F, termen_s=TERMEN_GHID_S).porneste()


def gen_ghid(sursa, F, C=None, H=None, A=None):
	"""Generator (pe felii) pentru o cerere: ghidul sursei din memorie, sau dupa lucrarea lui (asteptata cel mult
	ASTEAPTA_GHID_S). -> Ghid sau None (lucrarea a cazut sau nu a terminat la timp)."""
	C = _c(C)
	H = _h(H)
	A = _a(A)
	semn = semnSursa(sursa)
	inceput = time.monotonic()
	while True:
		acum = time.monotonic()
		g = _GHID["memorie"].get(semn)
		if g is not None:
			varsta = acum - g.ora
			if varsta < VIATA_GHID_S:
				return g
			if varsta < VIATA_MAXIMA_S:
				_cere(semn, sursa, F, C, H, A)   # cel vechi acum, altul in fundal
				return g
		esec = _GHID["esec"].get(semn)
		if esec is not None and esec >= inceput:
			return None
		_cere(semn, sursa, F, C, H, A)
		if acum - inceput >= ASTEAPTA_GHID_S:
			return None
		yield 200


# ---------------------------------------------------------------- raspunsurile /tv-extern/<cheie>/...

def scrieText(request, cod, text, cap=False):
	request.setResponseCode(cod)
	request.setHeader(b"content-type", b"text/plain; charset=utf-8")
	request.setHeader(b"cache-control", b"no-store")
	if cod == 503:
		request.setHeader(b"retry-after", str(int(getattr(request, "hds_retry", 2) or 2)).encode("ascii"))
	return b"" if cap else (text + "\n").encode("utf-8")


def _rest(request):
	return [p.decode("ascii", "replace") if isinstance(p, bytes) else p for p in (getattr(request, "postpath", None) or [])
		if p]


def esteRutaAparat(request):
	rest = _rest(request)
	return len(rest) >= 2 and rest[1] in RUTE


def acceptaGzip(antet):
	"""Accept-Encoding cu gzip (fara q=0)."""
	for parte in (antet or "").lower().split(","):
		bucati = [b.strip() for b in parte.split(";")]
		if bucati[0] in ("gzip", "x-gzip", "*"):
			return not any(b.replace(" ", "") in ("q=0", "q=0.0", "q=0.00", "q=0.000") for b in bucati[1:])
	return False


def raspundeExtern(request, amanat, cap=False, F=None, C=None, A=None, P=None, H=None):
	"""GET / HEAD pe /tv-extern/<cheie>/canale.m3u | ghid.xml | sigla/<nume>.png. Aceleasi verificari pentru HEAD si
	GET; HEAD nu face nimic si nu noteaza folosirea. 403 din afara retelei locale si pentru orice cheie care nu e a unui
	aparat (gresita, inventata, revocata, de playlist: acelasi raspuns), 404 pentru o adresa gresita."""
	P = _p(P)
	A = _a(A)
	adresa = P._adresaClient(request) or ""
	if not P._esteAdresaLocala(adresa):
		return scrieText(request, 403, _t("Acces permis doar din rețeaua locală."), cap)
	rest = _rest(request)
	if len(rest) < 2:
		return scrieText(request, 404, _t("Adresa nu e bună."), cap)
	cheie, motiv = A.magazin().verificaAparat(rest[0], noteaza=not cap)
	if cheie is None:
		return scrieText(request, 403, motiv, cap)
	if rest[1] == "canale.m3u" and len(rest) == 2:
		return _m3u(request, amanat, rest[0], cheie, cap, F, C, A, P, H)
	if rest[1] == "ghid.xml" and len(rest) == 2:
		return _ghid(request, amanat, cheie, cap, F, C, A, P, H)
	if rest[1] == "sigla" and len(rest) == 3:
		return _sigla(request, amanat, rest[2], cap, F, C)
	return scrieText(request, 404, _t("Adresa nu e bună."), cap)


def _porneste(request, gen, gata, F, C, termen_s):
	"""Un raspuns pe felii; playerul care pleaca opreste numai cererea lui (lucrarea ghidului merge mai departe)."""
	Fx = C._m(F)
	if C._planificator(Fx).numar() >= C.MAX_LUCRARI:
		request.hds_retry = 5
		return scrieText(request, 503, _t("Receptorul are prea multe cereri în lucru. Încearcă din nou."))
	lucru = C.PeBucati(gen, gata, Fx, termen_s=termen_s)
	try:
		request.notifyFinish().addErrback(lucru.opreste)
	except Exception:
		pass
	lucru.porneste()
	return None


def _scrieSiTermina(request, corp):
	try:
		if corp:
			request.write(corp)
		request.finish()
	except Exception as e:
		_jurnal("raspunsul nu a plecat (player plecat?): %r" % (e,))


def _gataText(request):
	"""gata(cod, corp) al lui PeBucati pentru un raspuns care a scris deja (cod None) sau un refuz text."""
	def gata(cod, corp):
		if cod is None:
			_scrieSiTermina(request, b"")
			return
		if isinstance(corp, dict):
			corp = corp.get("message") or _t("Eroare pe receptor.")
		_scrieSiTermina(request, scrieText(request, cod, corp))
	return gata


def _m3u(request, amanat, cheie_text, cheie, cap, F, C, A, P, H):
	gazda = P._antet(request, b"host") or ""
	if not A.gazdaBuna(gazda):
		return scrieText(request, 400, _t("Adresa receptorului din cerere nu e bună."), cap)
	if cap:
		request.setResponseCode(200)
		request.setHeader(b"content-type", b"audio/x-mpegurl; charset=utf-8")
		request.setHeader(b"cache-control", b"no-store")
		return b""
	C = _c(C)
	Fx = C._m(F)

	def gen():
		inceput = time.monotonic()
		facute = _NUMAR[0]
		lista = yield from gen_lista_aparat(cheie.sursa or {}, Fx, C, H, A)
		text = aplicaSablon(lista.sablon, gazda, cheie_text).encode("utf-8", "replace")
		request.setResponseCode(200)
		request.setHeader(b"content-type", b"audio/x-mpegurl; charset=utf-8")
		request.setHeader(b"cache-control", b"no-store")
		request.setHeader(b"x-content-type-options", b"nosniff")
		request.setHeader(b"content-disposition", b'inline; filename="canale.m3u"')
		request.setHeader(b"content-length", str(len(text)).encode("ascii"))
		# pentru masuratori (curl -D -): din memorie sau facut acum, cate canale din cate, cat a durat pe receptor
		request.setHeader(b"x-hds-lista", b"noua" if lista.nr > facute else b"memorie")
		request.setHeader(b"x-hds-canale", ("%d/%d" % (len(lista.canale), lista.total)).encode("ascii"))
		request.setHeader(b"x-hds-ms", str(int((time.monotonic() - inceput) * 1000)).encode("ascii"))
		yield from gen_scrie(request, (text[i:i + BUCATA_SCRIERE] for i in range(0, len(text), BUCATA_SCRIERE)))
		return None, None

	refuz = _porneste(request, gen(), _gataText(request), Fx, C, TERMEN_LISTA_S + TERMEN_FIR_S)
	return refuz if refuz is not None else amanat


def _anteteGhid(request, g):
	request.setHeader(b"content-type", b"application/xml; charset=utf-8")
	request.setHeader(b"cache-control", b"private, max-age=%d" % VIATA_GHID_S)
	request.setHeader(b"vary", b"Accept-Encoding")
	request.setHeader(b"x-content-type-options", b"nosniff")
	if g is not None:
		request.setHeader(b"etag", g.etag.encode("ascii"))


def _ghid(request, amanat, cheie, cap, F, C, A, P, H):
	if cap:
		request.setResponseCode(200)
		_anteteGhid(request, None)
		return b""
	C = _c(C)
	Fx = C._m(F)
	gz = acceptaGzip(P._antet(request, b"accept-encoding"))
	etag = P._antet(request, b"if-none-match") or ""

	def gen():
		g = yield from gen_ghid(cheie.sursa or {}, Fx, C, H, A)
		if g is None:
			request.hds_retry = REVINO_GHID_S
			return 503, _t("Ghidul TV se pregătește. Mai încearcă peste puțin timp.")
		_anteteGhid(request, g)
		if etag and etag == g.etag:
			request.setResponseCode(304)
			return None, None
		request.setResponseCode(200)
		if gz:
			request.setHeader(b"content-encoding", b"gzip")
			request.setHeader(b"content-length", str(len(g.gz)).encode("ascii"))
			bucati = (g.gz[i:i + BUCATA_SCRIERE] for i in range(0, len(g.gz), BUCATA_SCRIERE))
		else:
			request.setHeader(b"content-length", str(g.octeti).encode("ascii"))
			bucati = bucatiDezarhivate(g.gz)
		yield from gen_scrie(request, bucati)
		return None, None

	refuz = _porneste(request, gen(), _gataText(request), Fx, C, ASTEAPTA_GHID_S + TERMEN_TRIMITERE_S)
	return refuz if refuz is not None else amanat


class Ritm(object):
	"""Producatorul raspunsului (IPushProducer pentru request.registerProducer): Twisted cheama pauseProducing cand
	bufferul legaturii e plin si resumeProducing cand s-a golit; scrierea asteapta intre ele, deci un ghid mare nu
	sta intreg in memoria legaturii cand playerul citeste incet."""

	def __init__(self):
		self.oprit = False
		self.plecat = False

	def pauseProducing(self):
		self.oprit = True

	def resumeProducing(self):
		self.oprit = False

	def stopProducing(self):
		self.plecat = True


def bucatiDezarhivate(gz):
	"""Textul ghidului din forma comprimata, pe bucati de cel mult BUCATA_IESIRE octeti (fara gzip in Accept-Encoding)."""
	d = zlib.decompressobj(31)
	for i in range(0, len(gz), BUCATA_GZ):
		rest = gz[i:i + BUCATA_GZ]
		while rest:
			iesit = d.decompress(rest, BUCATA_IESIRE)
			rest = d.unconsumed_tail
			if iesit:
				yield iesit
	iesit = d.flush()
	if iesit:
		yield iesit


def gen_scrie(request, bucati):
	"""Generator (pe felii): scrie bucatile in raspuns, una pe pas, cu ritmul legaturii (Ritm). -> True daca a scris
	tot, False daca playerul a plecat."""
	ritm = Ritm()
	inregistrat = False
	try:
		request.registerProducer(ritm, True)
		inregistrat = True
	except Exception:
		pass
	try:
		for bucata in bucati:
			while ritm.oprit and not ritm.plecat:
				yield 50
			if ritm.plecat:
				return False
			request.write(bucata)
			yield
		return True
	finally:
		if inregistrat:
			try:
				request.unregisterProducer()
			except Exception:
				pass


def _sigla(request, amanat, fisier, cap, F, C):
	C = _c(C)
	Fx = C._m(F)
	nume = fisier[:-4] if fisier.endswith(".png") else ""
	if not nume or not C._NUME_SIGLA.match(nume):
		return scrieText(request, 404, _t("Sigla nu există pe receptor."), cap)
	sigle = C._MEMORIE["sigle"]
	if sigle is None:
		C.porneste_cautarea_siglelor(Fx)
		request.hds_retry = 3
		return scrieText(request, 503, _t("Sigla nu există pe receptor."), cap)
	if nume not in sigle:
		return scrieText(request, 404, _t("Sigla nu există pe receptor."), cap)

	def png(octeti):
		request.setResponseCode(200)
		request.setHeader(b"content-type", b"image/png")
		request.setHeader(b"cache-control", b"private, max-age=86400")
		request.setHeader(b"x-content-type-options", b"nosniff")
		return octeti

	if cap:
		return png(b"")

	def dupa(octeti):
		if octeti is None:
			_scrieSiTermina(request, scrieText(request, 404, _t("Sigla nu există pe receptor.")))
		else:
			_scrieSiTermina(request, png(octeti))

	rez = C.cere_sigla(Fx, nume, dupa)
	if rez is C.LA_FIR:
		return amanat
	if rez is None:
		return scrieText(request, 404, _t("Sigla nu există pe receptor."))
	return png(rez)


# ---------------------------------------------------------------- API-ul paginii

def campuriCerere(request):
	"""Campurile POST /api/tv-aparat-*, luate direct din request.args, fiecare cu limita lui."""
	rez = {}
	for cheie, maxim in ((b"nume", 200), (b"sursa", 16), (b"id", 128), (b"buchet", 128), (b"text", 120),
			(b"filtre", 8 * 1024), (b"eticheta", 300), (b"furnizor", 300), (b"grupa", 32)):
		v = (getattr(request, "args", None) or {}).get(cheie)
		if v:
			x = v[0]
			rez[cheie.decode("ascii")] = (x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x))[:maxim]
	return rez


def adresePentru(gazda, cheie_text):
	baza = "http://%s/tv-extern/%s/" % (gazda, cheie_text)
	return baza + "canale.m3u", baza + "ghid.xml"


def adauga(campuri, cine, browser_nume, gazda, A=None, C=None):
	"""POST /api/tv-aparat-adauga -> (cod, raspuns). Adresele (cu cheia) se dau numai acum."""
	A = _a(A)
	if not A.gazdaBuna(gazda):
		return 400, {"result": False, "message": _t("Adresa receptorului din cerere nu e bună.")}
	sursa, motiv = sursaDin(campuri, C)
	if sursa is None:
		return 400, {"result": False, "message": motiv}
	text, c, motiv = A.magazin().creeazaAparat(campuri.get("nume"), sursa, cine or "", browser_nume or "")
	if text is None:
		return 400, {"result": False, "message": motiv}
	m3u, ghid = adresePentru(gazda, text)
	_jurnal("aparat adaugat %s (%s)" % (c.id, sursa.get("fel")))
	return 200, {"result": True, "id": c.id, "nume": c.nume, "m3u": m3u, "ghid": ghid,
		"message": _t("Aparatul %s a fost adăugat.") % c.nume}


def redenumeste(campuri, A=None):
	A = _a(A)
	ok, motiv = A.magazin().redenumeste((campuri.get("id") or "")[:16], campuri.get("nume"))
	if not ok:
		return 400, {"result": False, "message": motiv}
	return 200, {"result": True, "message": _t("Aparatul a fost redenumit.")}


# ---------------------------------------------------------------- bucatile de pagina

def _inlocuieste(sablon, valori):
	for k, v in valori.items():
		sablon = sablon.replace("__A_%s__" % k, html.escape(v, quote=True))
	return sablon


def texteJs():
	"""Textele scriptului, ca JSON sigur in <script>."""
	text = json.dumps(texte(), ensure_ascii=False)
	return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def inPagina(pagina):
	"""Bucatile paginii (/tv: __APARATE_CARD__, /canale: __APARATE_DIALOG__; amandoua: __APARATE_STIL__,
	__APARATE_JS__, __APARATE_TEXTE__, __APARATE_MAX__) si textele __A_<cheie>__, traduse in limba interfetei. Se cheama
	inaintea datelor omului (configuratia paginii), ca un nume de browser sa nu poata fi luat drept loc de text."""
	pagina = (pagina.replace("__APARATE_STIL__", STIL).replace("__APARATE_CARD__", CARD)
		.replace("__APARATE_DIALOG__", DIALOG).replace("__APARATE_JS__", JS).replace("__APARATE_TEXTE__", texteJs())
		.replace("__APARATE_MAX__", str(int(MAX_CANALE_APARAT))))
	return _inlocuieste(pagina, texte())


ADRESE = """<div class="aparat-adrese ascuns" role="status">
	<p class="aparat-mesaj"></p>
	<label>__A_adresa_m3u__<span class="copiere"><input type="text" readonly class="adresa-m3u"><button type="button" class="copiaza">__A_copiaza__</button></span></label>
	<label>__A_adresa_ghid__<span class="copiere"><input type="text" readonly class="adresa-ghid"><button type="button" class="copiaza">__A_copiaza__</button></span></label>
	<p class="nota">__A_o_data__</p>
  </div>"""

STIL = """
  .aparat-form{display:grid;grid-template-columns:1fr;gap:8px;margin:12px 0 0;}
  .aparat-form label,.aparat-adrese label{display:grid;gap:4px;font-size:.92rem;}
  .aparat-form input,.aparat-form select,.aparat-adrese input,.aparat-rand input{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;box-sizing:border-box;}
  .aparat-form button,.aparat-adrese button,.aparat-rand button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:var(--panou);color:var(--text);font:inherit;cursor:pointer;}
  .aparat-form button.principal{background:var(--accent,#2f6fd6);color:#fff;border-color:transparent;justify-self:start;}
  .aparat-form button:disabled{opacity:.5;cursor:default;}
  .aparat-adrese{margin:12px 0 0;padding:12px;border:1px solid var(--accent,#2f6fd6);border-radius:8px;display:grid;gap:10px;}
  .aparat-adrese p{margin:0;line-height:1.45;}
  .copiere{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;}
  .aparat-rand .butoane-rand{display:flex;flex-wrap:wrap;gap:8px;}
  .aparat-rand .redenumire{grid-column:1 / -1;display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;}
  .ajutor-aparate{margin:12px 0 0;}
  .ajutor-aparate ul{margin:6px 0 0;padding-left:20px;line-height:1.5;font-size:.92rem;}
  .ajutor-aparate li{margin:0 0 6px;}
  .aparat-stare{margin:8px 0 0;line-height:1.45;font-size:.92rem;}
  .aparat-stare:empty{display:none;}
  .aparat-stare.eroare{color:#ffb4a8;}
  .aparat-marime{margin:8px 0 0;}
  .aparat-marime:empty{display:none;}
  .aparat-rand .taiat{display:block;color:var(--galben,#c9a227);font-size:.8rem;margin-top:2px;line-height:1.35;}
  .ascuns{display:none !important;}
  #dialogAparat .dialog-cutie{max-width:760px;}
  #laPlaylisturi{display:inline-flex;align-items:center;text-decoration:none;vertical-align:middle;box-sizing:border-box;}
  @media (min-width:700px){ .aparat-form{grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto;align-items:end;} }
  @media (max-width:560px){ .aparat-rand .redenumire{grid-template-columns:1fr;} }
"""

CARD = """<section class="card" id="cardAparate">
  <h2>__A_titlu__</h2>
  <p class="nota">__A_intro__</p>
  <ul class="lista" id="aparate"></ul>
  <form class="aparat-form" id="formAparat" autocomplete="off">
	<label>__A_nume__<input type="text" id="aparatNume" maxlength="40" placeholder="__A_nume_exemplu__" required></label>
	<label>__A_canale__<select id="aparatSursa"><option value="toate">__A_toate__</option></select></label>
	<button type="submit" class="principal" id="aparatAdauga">__A_adauga__</button>
  </form>
  <p class="nota aparat-marime" id="aparatMarime"></p>
  <p class="aparat-stare" role="status"></p>
  """ + ADRESE + """
  <details class="ajutor-aparate"><summary>__A_ajutor__</summary>
	<ul><li>__A_ajutor_kodi__</li><li>__A_ajutor_emby__</li><li>__A_ajutor_vlc__</li></ul>
	<p class="nota">__A_ajutor_limite__</p>
  </details>
</section>"""

DIALOG = """<div id="dialogAparat" class="dialog-live ascuns" role="dialog" aria-modal="true" aria-labelledby="dialogAparatTitlu">
  <div class="dialog-cutie">
	<div class="dialog-antet"><h2 id="dialogAparatTitlu">__A_din_canale__</h2><button type="button" id="dialogAparatInchide" aria-label="__A_inchide__">&#10005;</button></div>
	<p class="nota" id="dialogAparatLista"></p>
	<p class="nota">__A_din_canale_text__</p>
	<form class="aparat-form" id="formAparatCanale" autocomplete="off">
	  <label>__A_nume__<input type="text" id="aparatNumeCanale" maxlength="40" placeholder="__A_nume_exemplu__" required></label>
	  <button type="submit" class="principal" id="aparatAdaugaCanale">__A_adauga__</button>
	</form>
	<p class="aparat-stare" role="status"></p>
	""" + ADRESE + """
	<p class="nota"><a href="/tv#cardAparate">__A_vezi_tv__</a></p>
  </div>
</div>"""

# Scriptul comun al celor doua pagini: cererea de adaugare si caseta cu adresele (copierea merge si fara HTTPS, unde
# navigator.clipboard lipseste: textul se selecteaza si se copiaza cu execCommand; altfel omul il copiaza singur).
JS = """
function aparatStare(radacina, text, eroare){
  var e = radacina.querySelector(".aparat-stare");
  e.textContent = text || "";
  e.classList.toggle("eroare", !!eroare);
}
function aparatAdrese(cutie, d){
  cutie.querySelector(".aparat-mesaj").textContent = d.message || "";
  cutie.querySelector(".adresa-m3u").value = d.m3u || "";
  cutie.querySelector(".adresa-ghid").value = d.ghid || "";
  cutie.classList.remove("ascuns");
  Array.prototype.forEach.call(cutie.querySelectorAll(".copiaza"), function(b){
	b.onclick = function(){
	  var camp = b.parentNode.querySelector("input");
	  camp.focus(); camp.select();
	  var ok = false;
	  try { ok = document.execCommand("copy"); } catch(e) { ok = false; }
	  b.textContent = ok ? TA.copiat : TA.copiaza;
	  if(!ok){ cutie.querySelector(".aparat-mesaj").textContent = TA.copiaza_manual; }
	};
  });
  cutie.querySelector(".adresa-m3u").focus();
}
function aparatAdauga(campuri, buton, cutie, laFinal){
  buton.disabled = true;
  var p = new URLSearchParams();
  Object.keys(campuri).forEach(function(k){ if(campuri[k] !== undefined && campuri[k] !== null){ p.set(k, campuri[k]); } });
  cutie.classList.add("ascuns");
  return cerere("/api/tv-aparat-adauga", "POST", p).then(function(d){
	buton.disabled = false;
	if(!d.result){ throw new Error(d.message || TA.nu_raspunde); }
	aparatAdrese(cutie, d);
	if(laFinal){ laFinal(d); }
	return d;
  }, function(e){ buton.disabled = false; throw e; });
}
// fereastra "Adresa fixa pentru un aparat" (/canale si /cautare); o = {eticheta: lista si filtrele, pentru om; numar:
// cate canale are lista; campuri(): sursa, buchet, text si filtre (aparate_web.sursaDin); inapoi: butonul care a
// deschis-o}. Pagina da MAX_CANALE_APARAT si, pentru adaugare, cerere(cale, metoda, date).
var APARAT = {o: null};
function aparatDeschide(o){
  var d = document.getElementById("dialogAparat");
  APARAT.o = o;
  document.getElementById("dialogAparatLista").textContent = o.eticheta || "";
  d.querySelector(".aparat-adrese").classList.add("ascuns");
  // lista e mai mare decat primeste un aparat: se spune dinainte (playlistul pune intai satelitul televizorului)
  aparatStare(d, o.numar > MAX_CANALE_APARAT ? TA.taiat.replace("%s", MAX_CANALE_APARAT).replace("%s", o.numar) : "");
  document.getElementById("formAparatCanale").classList.remove("ascuns");
  d.classList.remove("ascuns");
  document.getElementById("aparatNumeCanale").focus();
}
function aparatInchide(){
  document.getElementById("dialogAparat").classList.add("ascuns");
  if(APARAT.o && APARAT.o.inapoi){ try { APARAT.o.inapoi.focus(); } catch(e) {} }
}
if(document.getElementById("dialogAparat")){
  document.getElementById("dialogAparatInchide").addEventListener("click", aparatInchide);
  document.getElementById("dialogAparat").addEventListener("click", function(e){
	if(e.target === document.getElementById("dialogAparat")){ aparatInchide(); }
  });
  document.addEventListener("keydown", function(e){
	if(e.key === "Escape" && !document.getElementById("dialogAparat").classList.contains("ascuns")){ aparatInchide(); }
  });
  document.getElementById("formAparatCanale").addEventListener("submit", function(e){
	e.preventDefault();
	var d = document.getElementById("dialogAparat"), c = APARAT.o.campuri();
	c.nume = document.getElementById("aparatNumeCanale").value;
	c.eticheta = APARAT.o.eticheta || "";
	aparatStare(d, TA.se_adauga);
	aparatAdauga(c, document.getElementById("aparatAdaugaCanale"), d.querySelector(".aparat-adrese"), function(){
	  aparatStare(d, "");
	  document.getElementById("formAparatCanale").classList.add("ascuns");
	  document.getElementById("aparatNumeCanale").value = "";
	}).catch(function(err){ aparatStare(d, err.message || TA.nu_raspunde, true); });
  });
}
"""
