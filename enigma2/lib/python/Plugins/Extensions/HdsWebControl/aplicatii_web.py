# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# aplicatii_web.py: rutele pentru aplicatiile de telefon, in interfata web (HdsWebControl).
#
# Aplicatiile obisnuite pentru receptoarele Enigma2 (telecomanda, lista de canale, ghidul, temporizatoarele, listele
# m3u: dreamDroid, Kodi cu pvr.vuplus, Home Assistant, VLC si altele) vorbesc cu receptorul prin rutele lor publice:
# /web/* in XML (setul clasic) si /api/* in JSON. Aici sunt aceleasi nume de rute, parametri, elemente XML si chei
# JSON, scrise de la zero dupa forma publica a raspunsurilor (dupa ce citeste fiecare client), fara cod luat din alte
# interfete web (nota de licenta din capul lui plugin.py).
# Logica e a imaginii: buchetele si continutul lor din canale_web.py, pornirea
# canalului si tastele din plugin.py (zapReferinta, _trimiteTasta), temporizatoarele prin Components/HdsTemporizare.py
# si Components/HdsInregistrariProgramate.py (aceleasi reguli ca pagina /temporizatoare), captura prin
# ScreenshotResource, siglele din caile lui Renderer/Picon.py, citite pe firul pentru fisiere al listei de canale.
#
# Versiunea raportata (e2webifversion, webifver) e VERSIUNE_WEBIF, numai cifre: Kodi ramane pe setul clasic /web/*, iar
# dreamDroid porneste toate functiile lui (acum/urmeaza, comenzile prin POST). Fara niciun nume in fata cifrelor.
#
# BARIERA (_poarta, pentru fiecare ruta de aici, inaintea oricarei citiri):
# pornite din fabrica si fara parola din casa; din internet nimic, pana nu porneste omul accesul din afara casei.
# 1. setarea „Aplicații de telefon” (config.plugins.hdswebcontrol.aplicatii) e pornita din
#    fabrica; oprita, toate rutele de aici raspund 404;
# 2. reteaua locala (esteReteaLocala): 10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, ::1, fe80::/10, fc00::/7 si
#    adresele IPv4 scrise in IPv6 (::ffff:a.b.c.d); NU 100.64/10 (NAT-ul operatorului: adrese impartite intre abonati)
#    si nicio adresa publica. Din afara ei: 403 cat „Acces din afara casei” (config.plugins.hdswebcontrol.aplicatii_afara)
#    e oprit, cum vine din fabrica;
# 3. o cerere care vine dintr-o pagina (Origin sau Referer de alta gazda decat Host, Sec-Fetch-Site cross-site cand
#    browserul il trimite) primeste 403, din casa si din afara; aplicatiile nu trimit aceste antete;
# 4. DIN CASA, cu antetul Host al receptorului (IP-ul scris cu cifre, numele lui, numele lui cu terminatiile date de
#    routere: .lan, .home, .localdomain, .home.arpa, .local; hdsatelit.local; L.gazdaProprie =
#    asociere.gazdaPermisa cu plugin._numeAcasa, numai numele EXACT) si cu „Cere codul și în rețeaua locală” oprit
#    (L.codAcasa, cum vine din fabrica): fara parola. Ce are aplicatia scris in Utilizator / Parola nu se verifica si nu
#    se numara: aplicatiile care au deja ceva scris acolo merg mai departe;
# 5. DIN AFARA CASEI (cu „Acces din afara casei” pornit), din casa cu alt nume in Host si din casa cu codul cerut si in
#    reteaua locala (randul „Cere codul și în rețeaua locală”, ca la browsere): HTTP Basic,
#    utilizatorul oricare (aplicatiile au „root” scris), parola = parola pentru aplicatii (12 litere si cifre in grupe
#    de 4, facuta pe receptor, separata de parola root, aratata pe televizor in ecranul interfetei web si in /setari)
#    sau cheia pentru scripturi (?token= merge si el). Fara antet: 401 cu provocarea WWW-Authenticate (Kodi, VLC,
#    libcurl trimit parola numai dupa ea). O cerere care arata a browser (User-Agent cu „Mozilla/”) primeste 401 fara
#    provocare: browserul nu arata fereastra de parola, deci nici nu o tine minte ca s-o trimita apoi singur din
#    paginile altora. Antetele Sec-Fetch-* nu ajuta aici: browserele nu le trimit spre o adresa http. Parola gresita de
#    GRESELI_MAX ori de la aceeasi adresa: 429 pentru BLOCARE_S secunde si un mesaj pe televizor. In casa, un Host
#    strain cere parola fiindca o pagina re-legata prin DNS (DNS rebinding) trimite Host-ul ei, iar Origin / Referer
#    sunt tot ale ei: fara parola, numai Host-ul o deosebeste de o aplicatie;
# 6. comenzile (canal, taste, volum, standby, mesaj, temporizatoare) sunt sub aceeasi bariera; oprirea completa si
#    repornirea (powerstate 1, 2, 3) nu se fac de aici deloc.
# Prima cerere buna a unei aplicatii noi (adresa + felul aplicatiei, dintr-un vocabular fix), cu parola sau fara, pune
# pe televizor „Aplicație conectată”. Parola si aplicatiile vazute stau in CALE_PAROLA (0600, in afara fisierului
# settings); copia setarilor (Components/HdsCopieSetari.py) il ia in setari.tar.gz si il pune la loc numai pe acelasi
# receptor (FISIERE_PROPRII), deci parola ramane si dupa o versiune noua. „Parolă nouă pentru aplicații” o schimba si
# goleste lista.
# Antetul Host: o cerere spre o ruta de aici trece de poarta Host (gazdaPermisa, chemata din _gazdaPermisaCerere) cu
# numele receptorului si terminatiile routerelor (L.gazdaProprie, ca la punctul 4) si, cu un antet Basic, cu orice alt
# nume; parola o verifica apoi bariera (punctul 5), cu numaratoarea greselilor. Fara antet Basic, un nume strain
# primeste 403 de la poarta Host, ca restul interfetei (care nu primeste terminatiile routerelor).
# /api/statusinfo, /api/zap si /api/remotecontrol exista deja pentru panou (cookie-ul interfetei, antetul X-HDS-CSRF) si
# scripturi (?token=): forma de aici raspunde cererilor cu Authorization: Basic si celor fara ?token=, fara X-HDS-CSRF si
# fara cookie-ul interfetei (Home Assistant din casa, fara parola); celelalte merg ca inainte (Alege, din rute;
# esteCerereAplicatie). Paginile receptorului trimit mereu X-HDS-CSRF sau ?token= (functia cerere din fiecare).
#
# Rute (GET, POST si HEAD la fel; 200 si pentru o comanda care nu s-a facut, starea e in corp):
#   /web/deviceinfo, /web/about, /web/currenttime, /web/signal, /web/tunersignal, /web/settings
#   /web/getservices[?sRef=], /web/getallservices[?type=tv|radio]
#   /web/zap?sRef=, /web/remotecontrol?command=[&type=long], /web/vol?set=state|up|down|mute|setNN,
#   /web/powerstate[?newstate=0|4|5], /web/message?text=[&type=&timeout=]
#   /web/epgservice?sRef=[&time=&endTime=], /web/epgservicenow?sRef=, /web/epgservicenext?sRef=,
#   /web/epgnow?bRef=, /web/epgnext?bRef=, /web/epgnownext?bRef=, /web/getcurrent
#   /web/timerlist, /web/timeradd, /web/timerchange, /web/timerdelete, /web/timercleanup
#   /web/getlocations, /web/getcurrlocation, /web/movielist[?dirname=&tag=], /web/gettags
#   /web/stream.m3u?ref=[&name=], /web/services.m3u?bRef=, /web/streamcurrentm3u (si streamm3u, servicesm3u)
#   /web/ts.m3u?file=[&name=] (si tsm3u): lista m3u cu adresa /file a unei inregistrari
#   /api/statusinfo, /api/about, /api/deviceinfo, /api/currenttime, /api/tunersignal, /api/bouquets?stype=tv|radio,
#   /api/getservices, /api/getallservices, /api/zap, /api/remotecontrol, /api/vol, /api/powerstate, /api/message,
#   /api/epgnow, /api/epgnext, /api/epgnownext, /api/epgservice, /api/epgservicenow, /api/epgservicenext,
#   /api/timerlist, /api/timeradd, /api/timerchange, /api/timerdelete, /api/timercleanup, /api/getlocations,
#   /api/getcurrlocation, /api/movielist[?dirname=&tag=], /api/gettags, /api/streamm3u, /api/servicesm3u,
#   /api/tsm3u?file=
#   /picon/<referinta cu _>.png, /file?file=<calea unei sigle sau a unei inregistrari>[&action=stream] (REDAREA),
#   /grab?format=&mode=&r= (captura)
# /web/session raspunde 404 dinadins: clientii merg fara sesiune la 404.
#
# INREGISTRARILE (/web/movielist, /api/movielist, din 0.2.5): filmele unui loc al inregistrarilor, din aceeasi lista ca
# panoul (filme_web.citesteLista: aceleasi fisiere, aceeasi ordine ca pe televizor, cel mult filme_web.MAX_FILME), plus
# ce citesc aplicatiile langa fiecare inregistrare: .meta (canalul, descrierea, ora, etichetele, lungimea), .eit
# (descrierea lunga), .ap (lungimea, cand .meta nu o are la zi) si .cuts (unde s-a ramas, din lista panoului).
# - dirname: numai un loc al inregistrarilor (_locuri, ca /web/getlocations) sau un dosar din el; fara dirname, locul de
#   acum (/web/getcurrlocation). Pe firul enigma2 se verifica doar textul (cale absoluta, fara „..”, fara \x00 si alte
#   caractere de control); locul se verifica pe firul pentru fisiere, cu realpath: o legatura care iese din loc nu
#   trece, un loc care e chiar radacina discului nu se primeste. Filmele care sunt legaturi spre afara locului se sar;
#   fisierele de langa film se deschid numai daca sunt fisiere obisnuite (nu legaturi, tevi sau dispozitive).
# - tag: etichete despartite de spatiu; raman filmele care le au pe toate.
# - cel mult MAX_FILME_APLICATII filme pe raspuns (in JSON, „message” o spune cand lista e taiata).
# - discul (realpath, dosarul, fisierele) se citeste NUMAI pe firul pentru fisiere „inregistrari” al furnizorului
#   listei de canale, separat de cel al siglelor: un disc USB adormit sau cazut nu tine nici televizorul, nici siglele.
#   Raspunsul pleaca de pe firul enigma2, dupa cel mult TERMEN_FILME_S. Discul care nu raspunde la timp: /web/movielist
#   da 503 cu Retry-After (Kodi pastreaza atunci lista veche; o lista goala ar sterge-o), /api/movielist da
#   „result”: false si mesajul. La fel un dosar care exista, dar nu se poate citi (eroare de disc in timpul citirii).
#   Un loc strain sau un dosar care lipseste (discul scos): lista goala in XML, „result”: false in JSON.
# - numai citire: moviedelete, moviemove, movierename nu exista (404); /file da inregistrarile numai pentru redare.
#
# DOSARUL INREGISTRARII (/web/timeradd, /api/timeradd: dirname): un loc al inregistrarilor (_locuri, ca
# /web/getlocations) se ia pe loc; alt dosar (un subdosar al unui loc, alt disc) trebuie sa fie sub RADACINI_INREGISTRARI
# (/media/, /hdd/), cale absoluta fara ".." si fara caractere de control (dosarCerut, pe firul enigma2), apoi pe firul
# pentru fisiere FIR_INREGISTRARI (dosarInregistrare, cu TERMEN_FILME_S): exista, se poate scrie in el, iar calea lui
# reala (legaturile urmate; pe receptor /media/hdd e o legatura spre /run/media/<disc>) sta pe un disc: punctul ei de
# montare din /proc/mounts nu e radacina receptorului si nici o memorie (FARA_DISC: tmpfs, ca /media insusi). Asa o
# legatura care iese spre memoria receptorului nu trece. Un dosar care nu trece: inregistrarea se pune in
# locul obisnuit (ca enigma2 la pornirea ei, cand dosarul lipseste), iar mesajul o spune (TXT_DOSAR_RESPINS). Un
# dirname gol sau "None" (asa il scrie /web/timerlist cand lipseste) = locul obisnuit. /timerchange ia numai locurile.
#
# DECODAREA (/web/timeradd, /api/timeradd, /timerchange: decodare=acum|maitarziu, si 0|1): alegerea "Decriptează acum" /
# "Decodează mai târziu" a inregistrarii (Components/HdsDecodare.py), NUMAI cu programul de decodare pe receptor; fara
# el parametrul nu se citeste. Fara parametru (aplicatiile de telefon nu il stiu) temporizatorul nou ia alegerea din
# setari (din fabrica "Decriptează acum", deci ca inainte); o valoare necunoscuta se ignora la fel. /api/timerlist
# adauga "decodare" la fiecare temporizator, tot numai cu programul.
#
# REDAREA (/file?file=<cale>, din 0.2.5): o inregistrare sau un film se reda pe telefon cum il cer aplicatiile: Kodi
# (pvr.vuplus: <adresa>/file?file=<e2filename>, cu Range la fiecare salt), dreamDroid (acelasi /file, dat playerului
# video sau descarcat), VLC si playerele m3u (/web/ts.m3u?file=, /api/tsm3u?file=, /file?action=stream&file=: o lista
# cu adresa /file, fara parola).
# - pe firul enigma2 numai textul: extensie video sau sunet cunoscuta (TIPURI_REDARE), cale absoluta intr-un loc al
#   inregistrarilor sau intr-un dosar din el (fisierPermis: fara „..”, fara caractere de control). Orice alta cale
#   merge ca pana acum, la sigle (numai PNG din dosarele siglelor). Antetul Range se citeste tot ca text.
# - pe firul fluxului (cate unul pentru fiecare flux; niciodata firul „inregistrari” al listei sau cel al siglelor):
#   realpath si locul real (o legatura care iese din loc nu trece), extensia caii reale, deschiderea (O_NOFOLLOW,
#   O_NONBLOCK; numai fisier obisnuit: nu legatura, teava sau dispozitiv) si fstat, apoi fiecare bucata (BUCATA_FLUX
#   octeti) si inchiderea. Firul preda rezultatele firului enigma2 prin M.predaPeFir = reactor.callFromThread, care in
#   e2reactor (din 0.1.7) trezeste bucla prin waker. Deschiderea are termen (TERMEN_DESCHIDERE_S): un disc care nu
#   raspunde da 503 cu Retry-After, iar firul inchide fisierul cand se intoarce. Un disc USB adormit nu tine
#   televizorul: firul enigma2 nu asteapta niciodata discul.
# - raspunsul: 200 (tot fisierul) sau 206 (un singur interval, Content-Range), Content-Length, Accept-Ranges: bytes,
#   tipul MIME dupa extensie; 416 cu „Content-Range: bytes */<marime>” cand intervalul nu are niciun octet in fisier;
#   un Range scris altfel (alta unitate, mai multe intervale) sau insotit de If-Range se ignora: tot fisierul, cu 200.
#   HEAD: aceleasi antete, fara corp. Marimea e cea din fstat la cerere: o inregistrare care se scrie acum se da pana
#   unde a ajuns pe disc, fara asteptare; Kodi cere din nou (Range de unde a ramas) si primeste marimea noua.
# - frana: raspunsul e un producator Twisted (push, _Flux): o singura bucata ceruta firului la un moment dat;
#   urmatoarea se cere numai dupa ce cea dinainte a fost data conexiunii si numai cat conexiunea nu a cerut pauza
#   (pauseProducing, cand tamponul ei trece de 64 KiB). Un telefon lent tine in memorie cel mult o bucata si tamponul.
# - aplicatia care inchide legatura (stopProducing, notifyFinish cu eroare): fluxul se opreste pe loc si locul lui se
#   elibereaza; firul nu mai citeste nimic si inchide fisierul (dupa citirea in curs, daca e una).
# - cel mult MAX_FLUXURI_APARAT fluxuri de la acelasi aparat (Kodi tine doua conexiuni pe acelasi fisier dupa un salt)
#   si MAX_FLUXURI in total (urmatorul primeste 503 cu Retry-After), cel mult MAX_FIRE_FLUX fire de citire vii (si cele
#   ramase pe un disc care nu raspunde). Fiecare flux in jurnal: aplicatia si adresa, fisierul, cat a trimis si de ce
#   s-a oprit (fara parole si fara antete).
# - legatura pazita (_pazesteLegatura): un telefon iesit din Wi-Fi fara sa inchida legatura se afla in TERMEN_TCP_S
#   (TCP_USER_TIMEOUT cat se trimite, keepalive cat sta), nu in 15-30 de minute, si locul fluxului se elibereaza; un
#   player pus pe pauza nu e taiat, fiindca telefonul tot raspunde.
# - bariera e aceeasi (_poarta). Oprirea: REDARE_INREGISTRARI = False (/file da atunci numai sigle, ca in 0.2.4) sau
#   setarea „Aplicații de telefon” oprita (toate rutele de aici).
#
# FLUXUL: listele m3u au forma obisnuita, http://<ip>:8001/<referinta>. Pe 8001 asculta azi numai serverul releelor
# DAB+ / DVB-T2 (Hds/DabT2/server8001.py), pe 127.0.0.1: din telefon fluxul porneste dupa ce portul acela se deschide in
# retea, cu parola (nu de aici). Parola nu se scrie in listele m3u.
# O referinta de fisier (inregistrare) nu merge pe 8001: serverul primeste numai referinte de canal fara cale (400
# altfel), iar enigma2 nu face o inregistrare dintr-un fisier (eServiceFactoryDVB::record, lib/service/servicedvb.cpp),
# deci nici demux, nici decodor. Inregistrarile pleaca spre telefon prin /file (REDAREA), citite de pe disc.
#
# FIRUL: totul ruleaza pe firul enigma2, din memorie si din cache-ul EPG (C++), afara de sigle (citite pe firul pentru
# fisiere al listei de canale, canale_web._Furnizor.in_fir), de lista inregistrarilor (firul „inregistrari” al
# aceluiasi furnizor), de fluxurile /file (cate un fir pentru fiecare flux, vezi REDAREA) si de captura (firul ei).
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau furnizorul lor (M) si legaturile lor (L).

import json
import os
import re
import time

VERSIUNE_WEBIF = "1.8.0"
NUME_IMAGINE = "HDSatelit"
CALE_PAROLA = "/etc/enigma2/hdswebcontrol-aplicatii.json"
PROVOCARE = b'Basic realm="HDSatelit", charset="UTF-8"'
LITERE_PAROLA = "abcdefghjkmnpqrstuvwxyz23456789"   # fara 0/o, 1/l/i
GRUPE_PAROLA = 3
GRESELI_MAX = 5
BLOCARE_S = 300
FEREASTRA_GRESELI_S = 600
MAX_ADRESE = 256
MAX_VAZUTE = 20
PORT_FLUX = 8001
MAX_REF = 600
MAX_ARG = 2048
MAX_NUME = 200
MAX_DESCRIERE = 4000
MAX_MESAJ = 500
PAUZA_MESAJ_S = 2.0
MAX_SERVICII = 10000
MAX_EVENIMENTE = 1000
MINUTE_GHID = 7 * 24 * 60
DURATA_MAX_TEMPORIZATOR_S = 7 * 24 * 3600
MAX_ETICHETE = 10
TERMEN_SIGLA_S = 5
MAX_SIGLA = 256 * 1024
MAX_FILME_APLICATII = 500   # filme pe raspuns (lista panoului se opreste si ea la filme_web.MAX_FILME)
MAX_DOSARE = 100            # subdosarele din „bookmarks”
MAX_CALE = 1024
MAX_FISIER_MIC = 4096       # .meta si .eit (enigma2 citeste tot 4096 octeti dintr-un .eit)
TERMEN_FILME_S = 20         # ca lista panoului (filme_web.TERMEN_LISTA_S): un disc USB adormit porneste in cateva secunde
FIR_INREGISTRARI = "inregistrari"
RADACINI_INREGISTRARI = ("/media/", "/hdd/")   # unde poate fi dosarul unei inregistrari puse din aplicatii (dirname)
# sisteme de fisiere care nu sunt un disc (dosarul unei inregistrari nu poate sta pe ele)
FARA_DISC = ("tmpfs", "ramfs", "rootfs", "devtmpfs", "proc", "sysfs", "squashfs", "overlay")
REF_INREGISTRARE = "1:0:0:0:0:0:0:0:0:0:"
REF_FILM = "4097:0:0:0:0:0:0:0:0:0:"
# redarea (/file, din 0.2.5); REDARE_INREGISTRARI = False o opreste (/file da atunci numai sigle, ca in 0.2.4)
REDARE_INREGISTRARI = True
MAX_FLUXURI = 4                         # fluxuri /file deodata, de la toate aparatele; urmatorul primeste 503
MAX_FLUXURI_APARAT = 2                  # de la acelasi aparat (Kodi tine doua conexiuni pe un fisier dupa un salt)
MAX_FIRE_FLUX = MAX_FLUXURI + 2         # fire de citire vii, cu cele ramase pe un disc care nu raspunde
TERMEN_TCP_S = 120                      # telefonul plecat fara sa inchida legatura se afla in cel mult atat
BUCATA_FLUX = 64 * 1024                 # octeti cititi deodata; o singura bucata in drum pe flux (frana)
TERMEN_DESCHIDERE_S = TERMEN_FILME_S    # deschiderea si fstat; dupa atat 503 (un disc USB adormit porneste in cateva s)
PAUZA_FLUX_S = 10                       # Retry-After cand fluxurile sunt toate ocupate
PORT_WEB = 80
# extensiile date pentru redare: filmele listei (filme_web.EXTENSII_FILME), inregistrarile, alte video si sunetul
TIPURI_REDARE = {
	"ts": b"video/mp2t", "m2ts": b"video/mp2t", "mts": b"video/mp2t", "mkv": b"video/x-matroska", "webm": b"video/webm",
	"mp4": b"video/mp4", "m4v": b"video/x-m4v", "mov": b"video/quicktime", "3gp": b"video/3gpp", "avi": b"video/x-msvideo",
	"divx": b"video/x-msvideo", "mpg": b"video/mpeg", "mpeg": b"video/mpeg", "vob": b"video/mpeg", "dat": b"video/mpeg",
	"flv": b"video/x-flv", "ogv": b"video/ogg", "wmv": b"video/x-ms-wmv",
	"mp3": b"audio/mpeg", "mp2": b"audio/mpeg", "aac": b"audio/aac", "m4a": b"audio/mp4", "flac": b"audio/flac",
	"ogg": b"audio/ogg", "oga": b"audio/ogg", "opus": b"audio/ogg", "wav": b"audio/wav", "wma": b"audio/x-ms-wma",
	"ac3": b"audio/ac3", "mka": b"audio/x-matroska",
}
# setarile citite de aplicatii (Kodi cere marginile inregistrarilor); NICIODATA altele: nici cheile, nici parolele
SETARI_PERMISE = ("config.recording.margin_before", "config.recording.margin_after", "config.usage.default_path")

# steagurile referintei care nu sunt canale (eServiceReference: isDirectory, isMarker, isNumberedMarker, isInvisible)
DOSAR = 1
MARCAJ = 64
MARCAJ_NUMEROTAT = 256
ASCUNS = 512

_CONTROL = re.compile(u"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f￾￿]")
_SUROGATE = re.compile(u"[\ud800-\udfff]")
_SPATII = re.compile(u"[\t\r\n ]+")
_REF = re.compile(r"^\d{1,4}:\d{1,5}(:[0-9A-Fa-f]{1,8}){8}:")
_NUME_SIGLA = re.compile(r"^[A-Za-z0-9_]{1,120}$")
_ETICHETA = re.compile(r"^[A-Za-z0-9_.\-]{1,40}$")

def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce la folosire."""
	return text


# felul aplicatiei, dupa User-Agent, dintr-un vocabular fix (pe televizor nu ajunge niciodata text copiat din antet)
_APLICATII = (
	("kodi", "Kodi"),
	("dreamdroid", "dreamDroid"),
	("homeassistant", "Home Assistant"),
	("home assistant", "Home Assistant"),
	("libvlc", "VLC"),
	("vlc/", "VLC"),
	("okhttp", N_("aplicație Android")),
	("dalvik", N_("aplicație Android")),
	("cfnetwork", N_("aplicație iPhone")),
	("lavf", N_("player video")),
	("aiohttp", N_("program Python")),
	("python", N_("program Python")),
	("curl", "curl"),
	("wget", "wget"),
	("mozilla/", N_("browser")),
)
APLICATIE = N_("aplicație")
# lista inregistrarilor; ultimele doua sunt textele listei panoului (filme_web.py), deja traduse
TXT_LOC_STRAIN = N_("Dosarul cerut nu este printre locurile înregistrărilor.")
TXT_LISTA_TAIATA = N_("Lista arată cel mult %d filme dintr-un dosar.")
TXT_DOSAR_NECITIT = N_("Dosarul filmelor nu se poate citi.")
TXT_DISC_INCET = N_("Discul nu a răspuns la timp. Încearcă încă o dată.")
# temporizatorul pus din aplicatii cu un dosar care nu trece (DOSARUL INREGISTRARII)
TXT_DOSAR_RESPINS = N_("Dosarul cerut nu există pe un disc al receptorului, așa că înregistrarea merge în locul obișnuit.")
# redarea (/file): toate fluxurile ocupate
TXT_FLUXURI_OCUPATE = N_("Receptorul trimite deja cât poate deodată: %d înregistrări aceluiași aparat, %d în total. "
	"Încearcă din nou după ce se oprește una.")

# rutele JSON de sub /api; primele trei exista deja in plugin.py si se aleg prin Alege
NUME_API_VECHI = (b"statusinfo", b"zap", b"remotecontrol")
NUME_API = NUME_API_VECHI + (
	b"about", b"deviceinfo", b"currenttime", b"tunersignal", b"bouquets", b"getservices", b"getallservices",
	b"vol", b"powerstate", b"message", b"epgnow", b"epgnext", b"epgnownext", b"epgservice", b"epgservicenow",
	b"epgservicenext", b"timerlist", b"timeradd", b"timerchange", b"timerdelete", b"timercleanup", b"getlocations",
	b"getcurrlocation", b"movielist", b"streamm3u", b"servicesm3u", b"tsm3u", b"gettags")
NUME_API_NOI = tuple(n for n in NUME_API if n not in NUME_API_VECHI)

CEAS = time.monotonic       # probele il inlocuiesc


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsWebControl] aplicatii: %s" % _CONTROL.sub("?", str(text)))


# ---------------------------------------------------------------- textele si scrierea raspunsurilor

def curat(text, maxim=MAX_NUME, randuri=False):
	"""Text venit din satelit sau din cerere, bun de pus in XML 1.0 si JSON: octetii ne-UTF-8 devin U+FFFD, randul nou
	DVB (0x8A) devine rand nou, caracterele de control si cele interzise in XML se scot; fara `randuri`, randurile si
	spatiile in sir devin un singur spatiu. Taiat la `maxim`."""
	if text is None:
		return u""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	elif not isinstance(text, str):
		text = str(text)
	text = _SUROGATE.sub(u"�", text.replace(u"\u008a", u"\n"))
	text = _CONTROL.sub(u"", text)
	if randuri:
		text = text.replace(u"\r\n", u"\n").replace(u"\r", u"\n").replace(u"\t", u" ")
	else:
		text = _SPATII.sub(u" ", text)
	return text.strip()[:maxim]


def _scapa(text):
	return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
		.replace("'", "&apos;"))


def _valoare(v):
	"""Valorile logice ca in Python (True / False), lipsa ca „None”, numerele zecimale, textele curatate si scapate."""
	if v is True:
		return "True"
	if v is False:
		return "False"
	if v is None:
		return "None"
	if isinstance(v, int):
		return "%d" % v
	if isinstance(v, float):
		return "%.2f" % v
	return _scapa(curat(v, 100000, randuri=True))


def _nod(nume, valoare, parti):
	if isinstance(valoare, list):
		parti.append("<%s>\n" % nume)
		for n, v in valoare:
			_nod(n, v, parti)
		parti.append("</%s>\n" % nume)
	else:
		parti.append("<%s>%s</%s>\n" % (nume, _valoare(valoare), nume))


def xml(radacina, copii):
	"""Documentul XML: antetul UTF-8 pe primul rand, elementele (nume, valoare | [copii]), `\\n` la sfarsit."""
	parti = ['<?xml version="1.0" encoding="UTF-8"?>\n']
	_nod(radacina, copii, parti)
	return "".join(parti).encode("utf-8")


def _antete(request, tip):
	request.setResponseCode(200)
	request.setHeader(b"content-type", tip)
	request.setHeader(b"cache-control", b"no-store")
	request.setHeader(b"x-content-type-options", b"nosniff")


def _xml(request, radacina, copii):
	_antete(request, b"text/xml; charset=UTF-8")
	return xml(radacina, copii)


def _json(request, obiect):
	"""Separatorii impliciti („, ” si „: ”): Kodi cauta textul exact `"result": true`."""
	_antete(request, b"application/json; charset=utf-8")
	return json.dumps(obiect, ensure_ascii=False).encode("utf-8", "replace")


def _simplu(request, bun, text):
	"""Raspunsul unei comenzi in XML; textul nu are voie sa fie gol (Kodi trateaza elementul gol ca lipsa)."""
	return _xml(request, "e2simplexmlresult", [("e2state", bool(bun)), ("e2statetext", text or ("OK" if bun else "-"))])


def _comanda(c, bun, text, **altele):
	if c.fel == "web":
		return _simplu(c.r, bun, text)
	rez = {"result": bool(bun), "message": text or ""}
	rez.update(altele)
	return _json(c.r, rez)


def _refuz(request, eroare):
	cod, text, antete = eroare
	request.setResponseCode(cod)
	request.setHeader(b"content-type", b"text/plain; charset=utf-8")
	request.setHeader(b"cache-control", b"no-store")
	for k, v in (antete or {}).items():
		request.setHeader(k, v)
	return (text + "\n").encode("utf-8")


def _ora(t):
	try:
		return time.strftime("%H:%M", time.localtime(int(t)))
	except (ValueError, OverflowError, OSError):
		return ""


# ---------------------------------------------------------------- referintele

def _campuri(ref):
	"""([tip, steaguri, 8 campuri], calea) din referinta; numele, dupa cale (al 12-lea camp), nu intra."""
	parti = (ref or "").split(":")
	if len(parti) < 11:
		return None
	try:
		return [int(parti[0]), int(parti[1])] + [int(p or "0", 16) for p in parti[2:10]], parti[10]
	except ValueError:
		return None


def ref_buna(text):
	"""O referinta de serviciu cu forma enigma2 (tip:steaguri:8 campuri hex:...), fara caractere de control."""
	return bool(text) and len(text) <= MAX_REF and _REF.match(text) is not None and _CONTROL.search(text) is None


def steaguri(ref):
	c = _campuri(ref)
	return c[0][1] if c else 0


def eCanal(ref):
	"""Un canal (nu dosar, marcaj sau intrare ascunsa)."""
	return ref_buna(ref) and not steaguri(ref) & (DOSAR | MARCAJ | MARCAJ_NUMEROTAT | ASCUNS)


def ref_epg(ref):
	"""Referinta DVB fara nume si fara cale, cu hex mare (cum o scrie toString), pentru cache-ul EPG; None altfel."""
	c = _campuri(ref)
	if c is None:
		return None
	campuri, cale = c
	if campuri[0] != 1 or cale or campuri[1] & (DOSAR | MARCAJ):
		return None
	return "1:0:" + ":".join("%X" % v for v in campuri[2:10]) + ":"


def caleFisier(ref):
	"""Calea fisierului redat (inregistrare, film), din coada referintei; "" la un canal."""
	c = _campuri(ref)
	if c is None:
		return ""
	return c[1] if c[1].startswith("/") else ""


_SCHEMA = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://")


def _decodeazaCale(text):
	"""Inversul lui _codeazaCale: fiecare %xx din cale inapoi in caracter, cum o citeste eServiceReference."""
	return re.sub(r"%([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)


def caleLocala(ref):
	"""Calea decodata cand referinta arata spre un fisier de pe receptor; None pentru un canal (fara cale) sau pentru o
	adresa de flux (http://, rtsp:// ..., codata „%3a//” sau nu). O adresa file:// sau o cale care nu e absoluta se
	intorc asa cum sunt, ca fisierPermis sa le refuze."""
	parti = (ref or "").split(":")
	if len(parti) < 11 or not parti[10]:
		return None
	m = _SCHEMA.match(_decodeazaCale(":".join(parti[10:])))
	if m and m.group(1).lower() != "file":
		return None
	return _decodeazaCale(parti[10])


def fisierPermis(cale, locuri):
	"""Un fisier pornit pe televizor din aplicatii (/web/zap, /api/zap): numai dintr-un loc al inregistrarilor sau
	dintr-un subdosar al lui. Se verifica numai textul, fara disc (zap-ul vine pe firul enigma2): cale absoluta, fara
	„..”, fara caractere de control, cel mult MAX_CALE."""
	if not cale or len(cale) > MAX_CALE or any(ord(ch) < 0x20 or 0x7f <= ord(ch) <= 0x9f for ch in cale):
		return False
	if not os.path.isabs(cale) or ".." in cale.replace("\\", "/").split("/"):
		return False
	for loc in locuri:
		loc = loc.rstrip("/\\")
		if not loc:
			continue
		for sep in ("/", os.sep):
			if cale.startswith(loc + sep) and len(cale) > len(loc) + 1:
				return True
	return False


def adresaFlux(ref, ip):
	"""Adresa fluxului unui canal pentru listele m3u: http://<ip>:8001/<primele 10 campuri>:, sau adresa din coada
	referintei la un canal de internet. None daca nu se poate."""
	c = _campuri(ref)
	if c is None:
		return None
	coada = c[1]
	if coada:
		try:
			from urllib.parse import unquote
			adresa = unquote(coada)
		except Exception:
			return None
		if adresa.startswith("http://") or adresa.startswith("https://"):
			return adresa if _CONTROL.search(adresa) is None and " " not in adresa else None
		return None
	if not ip:
		return None
	return "http://%s:%d/%s:" % (ip, PORT_FLUX, ":".join((ref or "").split(":")[:10]))


def numeAplicatie(user_agent):
	ua = (user_agent or "").lower()
	for cheie, nume in _APLICATII:
		if cheie in ua:
			return nume
	return APLICATIE


# ---------------------------------------------------------------- parola si aplicatiile vazute

_DATE = {"citit": False, "d": {}}
_VAZUTE_ACUM = set()
_GRESELI = {}
_ULTIMUL_MESAJ = [-3600.0]
_LEG = {"L": None, "M": None}


def _citesteFisier():
	try:
		with open(CALE_PAROLA, encoding="utf-8") as f:
			d = json.loads(f.read(65536))
	except (IOError, OSError, ValueError):
		return {}
	return d if isinstance(d, dict) else {}


def _salveaza(d):
	"""Fisierul se scrie numai de proprietar (0600), prin .nou + rename. Daca scrierea cade, parola ramane in memorie
	pana la repornire."""
	_DATE["d"] = d
	_DATE["citit"] = True
	nou = CALE_PAROLA + ".nou"
	try:
		fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		try:
			date = json.dumps(d, ensure_ascii=True, sort_keys=True).encode("ascii")
			while date:
				date = date[os.write(fd, date):]
		finally:
			os.close(fd)
		try:
			os.chmod(nou, 0o600)
		except OSError:
			pass
		os.replace(nou, CALE_PAROLA)
	except (IOError, OSError) as eroare:
		_jurnal("nu am putut scrie %s: %s" % (CALE_PAROLA, eroare))


def _date():
	if not _DATE["citit"]:
		_DATE["d"] = _citesteFisier()
		_DATE["citit"] = True
	return _DATE["d"]


def uita():
	"""Memoria modulului (probele)."""
	_DATE.update({"citit": False, "d": {}})
	_VAZUTE_ACUM.clear()
	_GRESELI.clear()
	_ULTIMUL_MESAJ[0] = -3600.0
	del _FLUXURI[:]
	_FIRE_FLUX[0] = 0


def formaParola(text):
	"""Parola fara despartitori si fara majuscule: „K7PM-3XQA-9FHE” e aceeasi cu „k7pm3xqa9fhe”."""
	return "".join(ch for ch in (text or "").lower() if ch in LITERE_PAROLA or ch.isdigit())


def _genereaza():
	import secrets
	litere = "".join(secrets.choice(LITERE_PAROLA) for _i in range(4 * GRUPE_PAROLA))
	return "-".join(litere[i:i + 4] for i in range(0, len(litere), 4))


def parola(creeaza=True):
	"""Parola pentru aplicatii; prima data se face si se scrie pe disc."""
	d = _date()
	p = d.get("parola")
	if isinstance(p, str) and len(formaParola(p)) >= 4 * GRUPE_PAROLA:
		return p
	if not creeaza:
		return ""
	nou = {"parola": _genereaza(), "creat": int(time.time()), "vazute": []}
	_salveaza(nou)
	_VAZUTE_ACUM.clear()
	_jurnal("parola pentru aplicatii facuta")
	return nou["parola"]


def parolaNoua():
	"""O parola noua; cea veche nu mai merge de la cererea urmatoare, lista aplicatiilor vazute se goleste."""
	nou = {"parola": _genereaza(), "creat": int(time.time()), "vazute": []}
	_salveaza(nou)
	_VAZUTE_ACUM.clear()
	_GRESELI.clear()
	_jurnal("parola noua pentru aplicatii")
	return nou["parola"]


def vazute():
	"""Aplicatiile vazute de la parola de acum (din casa si fara parola): [{"nume", "adresa", "prima"}], cele mai noi la
	sfarsit."""
	lista = _date().get("vazute")
	if not isinstance(lista, list):
		return []
	rez = []
	for v in lista[-MAX_VAZUTE:]:
		if isinstance(v, dict):
			rez.append({"nume": curat(v.get("nume"), 40), "adresa": curat(v.get("adresa"), 64),
				"prima": int(v.get("prima") or 0)})
	return rez


def _parolaDinAntet(antet):
	"""Parola (octeti) din `Authorization: Basic ...`; None daca antetul lipseste sau nu e Basic bun."""
	if not antet:
		return None
	parti = antet.strip().split(None, 1)
	if len(parti) != 2 or parti[0].lower() != "basic":
		return None
	import base64
	import binascii
	try:
		brut = base64.b64decode(parti[1].strip().encode("ascii"), validate=True)
	except (binascii.Error, ValueError, UnicodeEncodeError):
		return None
	_utilizator, sep, p = brut.partition(b":")
	if not sep:
		return None
	return p


def _parolaBuna(primita, jeton):
	"""Parola pentru aplicatii (fara despartitori si majuscule) sau cheia pentru scripturi, in timp constant."""
	import hmac
	asteptata = formaParola(parola(creeaza=True)).encode("ascii")
	data = formaParola(primita.decode("utf-8", "replace")).encode("ascii", "replace")
	bun = bool(data) and hmac.compare_digest(data, asteptata)
	if jeton:
		bun = hmac.compare_digest(primita, jeton.encode("utf-8")) or bun
	return bun


# ---------------------------------------------------------------- bariera

def _octetiIpv4(text):
	"""[a, b, c, d] din „a.b.c.d” (numai cifre zecimale, 0..255), altfel None."""
	parti = text.split(".")
	if len(parti) != 4:
		return None
	octeti = []
	for p in parti:
		if not 1 <= len(p) <= 3 or any(c not in "0123456789" for c in p):
			return None
		n = int(p)
		if n > 255:
			return None
		octeti.append(n)
	return octeti


def _grupeIpv6(text):
	"""Cele 8 grupe de 16 biti ale unei adrese IPv6 scrise („fe80::1”, „::ffff:10.0.0.5”), altfel None. Fara
	modulul ipaddress: e pachet separat in distributie, neinclus in imagine (nota de la plugin._esteAdresaLocala)."""
	if text.count("::") > 1:
		return None
	if "." in text:
		# ultimele doua grupe scrise ca IPv4
		i = text.rfind(":")
		if i < 0:
			return None
		octeti = _octetiIpv4(text[i + 1:])
		if octeti is None:
			return None
		text = text[:i + 1] + "%x:%x" % (octeti[0] << 8 | octeti[1], octeti[2] << 8 | octeti[3])
	if "::" in text:
		stanga, dreapta = text.split("::")
		parti_s = stanga.split(":") if stanga else []
		parti_d = dreapta.split(":") if dreapta else []
		if len(parti_s) + len(parti_d) > 7:
			return None
		parti = parti_s + ["0"] * (8 - len(parti_s) - len(parti_d)) + parti_d
	else:
		parti = text.split(":")
		if len(parti) != 8:
			return None
	grupe = []
	for p in parti:
		if not 1 <= len(p) <= 4 or any(c not in "0123456789abcdef" for c in p):
			return None
		grupe.append(int(p, 16))
	return grupe


def _formaAdresei(adresa):
	"""(octetii, None) pentru o adresa IPv4 sau IPv4 scrisa in IPv6 (::ffff:a.b.c.d), (None, grupele) pentru una IPv6,
	(None, None) pentru orice alt text."""
	text = (adresa or "").strip().lower()
	if text.startswith("[") and text.endswith("]"):
		text = text[1:-1]
	if ":" not in text:
		return _octetiIpv4(text), None
	g = _grupeIpv6(text.split("%", 1)[0])          # fara zona unei adrese fe80::1%eth0
	if g is not None and g[:6] == [0, 0, 0, 0, 0, 0xffff]:
		return [g[6] >> 8, g[6] & 0xff, g[7] >> 8, g[7] & 0xff], None
	return None, g


def esteReteaLocala(adresa):
	"""True pentru adresele din casa: 10/8, 172.16/12, 192.168/16, 127/8 (receptorul insusi), 169.254/16 (legatura
	directa, fara DHCP), ::1, fe80::/10, fc00::/7 si IPv4 scris in IPv6 (::ffff:a.b.c.d), dupa aceleasi reguli. NU
	100.64/10: e NAT-ul operatorului (CGNAT), cu adrese impartite intre abonati, deci nu e casa omului. Orice alt text
	(adresa publica, gol, nume): False."""
	o, g = _formaAdresei(adresa)
	if o is not None:
		return (o[0] in (10, 127) or (o[0] == 172 and 16 <= o[1] <= 31) or (o[0] == 192 and o[1] == 168)
			or (o[0] == 169 and o[1] == 254))
	if g is None:
		return False
	return g == [0, 0, 0, 0, 0, 0, 0, 1] or (g[0] & 0xffc0) == 0xfe80 or (g[0] & 0xfe00) == 0xfc00


def esteReceptorul(adresa):
	"""True pentru o cerere a receptorului insusi (127/8, ::1): paznicul (hds-watchdog.py intreaba GET /api/statusinfo
	pe 127.0.0.1, fara cheie) si scripturile de pe receptor nu sunt aplicatii de telefon si nu apar pe televizor."""
	o, g = _formaAdresei(adresa)
	return (o is not None and o[0] == 127) or g == [0, 0, 0, 0, 0, 0, 0, 1]


def _dinPagina(request, L):
	"""True daca cererea vine dintr-o pagina de alta gazda (sau, cand browserul o spune, din alt sit)."""
	sfs = (L.antet(request, b"sec-fetch-site") or "").strip().lower()
	if sfs and sfs not in ("same-origin", "none"):
		return True
	origin = L.antet(request, b"origin")
	referer = L.antet(request, b"referer")
	if origin or referer:
		from .asociere import acelasiOrigin
		return not acelasiOrigin(L.antet(request, b"host"), origin, referer)
	return False


def _ramasBlocat(adresa, acum):
	x = _GRESELI.get(adresa)
	if not x or x["pana"] <= acum:
		return 0
	return int(x["pana"] - acum) + 1


def _greseala(adresa, acum):
	"""Noteaza o parola gresita; True cand adresa tocmai a ajuns la GRESELI_MAX (blocata BLOCARE_S secunde)."""
	x = _GRESELI.get(adresa)
	if x is None:
		if len(_GRESELI) >= MAX_ADRESE:
			_GRESELI.pop(next(iter(_GRESELI)))
		x = _GRESELI[adresa] = {"timpi": [], "pana": 0.0}
	x["timpi"] = [t for t in x["timpi"] if acum - t < FEREASTRA_GRESELI_S] + [acum]
	if len(x["timpi"]) >= GRESELI_MAX:
		x["timpi"] = []
		x["pana"] = acum + BLOCARE_S
		return True
	return False


def _noteazaAplicatia(adresa, user_agent, M):
	"""Prima cerere buna a unei aplicatii noi: in lista de pe disc si un mesaj pe televizor. Receptorul insusi nu."""
	if esteReceptorul(adresa):
		return
	nume = numeAplicatie(user_agent)
	cheie = u"%s|%s" % (adresa, nume)
	if cheie in _VAZUTE_ACUM:
		return
	_VAZUTE_ACUM.add(cheie)
	d = _date()
	lista = [v for v in (d.get("vazute") or []) if isinstance(v, dict)]
	if any(v.get("adresa") == adresa and v.get("nume") == nume for v in lista):
		return
	lista = (lista + [{"adresa": adresa, "nume": nume, "prima": int(time.time())}])[-MAX_VAZUTE:]
	nou = dict(d)
	nou["vazute"] = lista
	_salveaza(nou)
	_jurnal("aplicatie noua: %s (%s)" % (nume, adresa))
	try:
		M.popup(_t("Aplicație conectată la receptor: %s (%s).") % (_t(nume), adresa), 8, "hds_aplicatie_noua")
	except Exception as eroare:
		_jurnal("mesajul aplicatiei noi: %s" % eroare)


def _poarta(request, L, M):
	"""None daca cererea trece; altfel (cod HTTP, text, antete)."""
	if not L.activ():
		return (404, "Not found", None)
	adresa = L.adresaClient(request) or ""
	acasa = esteReteaLocala(adresa)
	if not acasa and not L.afara():
		return (403, _t("Acces permis doar din rețeaua locală."), None)
	if _dinPagina(request, L):
		return (403, _t("Cerere respinsă: vine dintr-o pagină web, nu dintr-o aplicație."), None)
	if b"token" in request.args and L.jetonValid(request):
		return None
	user_agent = L.antet(request, b"user-agent") or ""
	if acasa and not L.codAcasa() and L.gazdaProprie(request):
		# din casa, cu Host-ul receptorului si fara codul cerut si in casa: fara parola; ce e scris in Utilizator / Parola nu
		# se verifica si nu se numara
		_noteazaAplicatia(adresa, user_agent, M)
		return None
	acum = CEAS()
	ramas = _ramasBlocat(adresa, acum)
	if ramas:
		return (429, _t("Prea multe parole greșite. Încearcă din nou peste câteva minute."),
			{b"retry-after": str(ramas).encode("ascii")})
	provocare = None if "mozilla/" in user_agent.lower() else {b"www-authenticate": PROVOCARE}
	antet = L.antet(request, b"authorization")
	if not antet:
		return (401, _t("Scrie în aplicație utilizatorul root și parola pentru aplicații de pe receptor."), provocare)
	primita = _parolaDinAntet(antet)
	if primita is not None and _parolaBuna(primita, L.jeton()):
		_GRESELI.pop(adresa, None)
		_noteazaAplicatia(adresa, user_agent, M)
		return None
	if _greseala(adresa, acum):
		nume = numeAplicatie(user_agent)
		_jurnal("parola gresita de %d ori de la %s (%s): oprit %d s" % (GRESELI_MAX, nume, adresa, BLOCARE_S))
		try:
			M.popup(_t("Parolă greșită de %d ori de la %s (%s): am oprit cererile ei pentru %d minute. Parola bună o vezi "
				"în ecranul interfeței web.") % (GRESELI_MAX, _t(nume), adresa, BLOCARE_S // 60), 15, "hds_aplicatie_blocata")
		except Exception as eroare:
			_jurnal("mesajul blocarii: %s" % eroare)
		return (429, _t("Prea multe parole greșite. Încearcă din nou peste câteva minute."),
			{b"retry-after": str(BLOCARE_S).encode("ascii")})
	return (401, _t("Parola pentru aplicații e greșită."), provocare)


def esteCaleAplicatii(cale):
	"""Calea (fara ?...) e a unei rute de aici."""
	if not isinstance(cale, bytes):
		cale = str(cale or "").encode("latin-1", "replace")
	cale = cale.split(b"?", 1)[0]
	if cale in (b"/web", b"/file", b"/grab") or cale.startswith(b"/web/") or cale.startswith(b"/picon/"):
		return True
	if cale.startswith(b"/api/"):
		return cale[5:].split(b"/", 1)[0] in NUME_API
	return False


def gazdaPermisa(request):
	"""Pentru _gazdaPermisaCerere: o cerere spre o ruta de aici, cu setarea pornita, trece cu numele receptorului si
	terminatiile routerelor in Host (L.gazdaProprie: viper4kv20.lan, viper4kv20.home, ca IP-ul) si, cu un antet Basic
	bine scris, cu orice antet Host; parola o verifica ruta (_poarta), cu numaratoarea greselilor si blocarea. Daca parola
	s-ar verifica aici, diferenta 403 / 200 ar lasa pe oricine sa incerce parole fara sa fie numarat."""
	L = _LEG["L"]
	if L is None:
		return False
	try:
		if not L.activ() or not esteCaleAplicatii(getattr(request, "path", b"")):
			return False
		if L.gazdaProprie(request):
			return True
		return _parolaDinAntet(L.antet(request, b"authorization")) is not None
	except Exception as eroare:
		_jurnal("antetul Host: %s" % eroare)
		return False


def esteCerereAplicatie(request, L):
	"""Pentru /api/statusinfo, /api/zap, /api/remotecontrol: forma compatibila pentru cererile cu Basic si pentru cele
	fara ?token=, fara antetul X-HDS-CSRF si fara cookie-ul interfetei (Home Assistant din casa, fara parola). Paginile
	receptorului trimit mereu X-HDS-CSRF sau ?token=, scripturile ?token=: ele raman pe rutele de pana acum."""
	if b"token" in request.args or not L.activ():
		return False
	antet = (L.antet(request, b"authorization") or "").strip().lower()
	if antet.startswith("basic "):
		return True
	return not L.antet(request, b"x-hds-csrf") and not L.areCookie(request)


# ---------------------------------------------------------------- furnizorul adevarat (numai pe receptor)

def _citesteMic(cale):
	try:
		with open(cale, encoding="utf-8", errors="replace") as f:
			return f.read(4096).strip()
	except (IOError, OSError):
		return ""


class _Furnizor(object):
	"""Modulele imaginii, importate abia la prima cerere. Listele si siglele prin furnizorul listei de canale."""

	def _cw(self):
		from . import canale_web
		return canale_web

	def _cm(self):
		return self._cw()._m()

	# canalele
	def surse(self, tip):
		cw = self._cw()
		return list(cw.ruleaza_tot(cw.gen_surse(self._cm(), tip)))

	def radacina(self, tip):
		return self._cw()._radacina(self._cm(), tip)

	def toate(self, tip):
		return "%s ORDER BY name" % self._cm().tipuri_servicii(tip)

	def continut(self, ref):
		return self._cm().continut(ref)

	def nume(self, ref):
		return self._cm().nume(ref)

	def ref_acum(self):
		return self._cm().ref_acum()

	def nume_serviciu(self, ref):
		try:
			return self._cm().nume_serviciu(ref)
		except Exception:
			return ""

	def epg(self, cerere):
		from enigma import eEPGCache
		return eEPGCache.getInstance().lookupEvent(cerere) or []

	# starea
	def standby(self):
		import Screens.Standby
		return Screens.Standby.inStandby is not None

	def intraStandby(self):
		import Screens.Standby
		from Tools import Notifications
		if Screens.Standby.inStandby is None:
			Notifications.AddNotification(Screens.Standby.Standby)

	def standbyInAsteptare(self):
		"""Un standby cerut sta in coada notificarilor: InfoBar il deschide abia cand se inchide fereastra de deasupra
		(un meniu, lista de canale, un mesaj)."""
		import Screens.Standby
		from Tools import Notifications
		return any(n[1] is Screens.Standby.Standby for n in Notifications.notifications)

	def iesiStandby(self):
		import Screens.Standby
		if Screens.Standby.inStandby is not None:
			Screens.Standby.inStandby.Power()

	def _vc(self):
		try:
			from Components.VolumeControl import VolumeControl
			return VolumeControl.instance
		except Exception:
			return None

	def volum(self):
		from enigma import eDVBVolumecontrol
		v = eDVBVolumecontrol.getInstance()
		return max(0, min(100, int(v.getVolume()))), bool(v.isMuted())

	def volumSus(self):
		vc = self._vc()
		if vc is not None:
			vc.volUp()
		else:
			from enigma import eDVBVolumecontrol
			eDVBVolumecontrol.getInstance().volumeUp()

	def volumJos(self):
		vc = self._vc()
		if vc is not None:
			vc.volDown()
		else:
			from enigma import eDVBVolumecontrol
			eDVBVolumecontrol.getInstance().volumeDown()

	def volumMut(self):
		vc = self._vc()
		if vc is not None:
			vc.volMute()
		else:
			from enigma import eDVBVolumecontrol
			eDVBVolumecontrol.getInstance().volumeToggleMute()

	def volumSeteaza(self, n):
		from enigma import eDVBVolumecontrol
		v = eDVBVolumecontrol.getInstance()
		v.setVolume(n, n)
		vc = self._vc()
		if vc is None:
			return
		if v.isMuted() and n > 0:
			vc.volMute()                       # sunetul revine, ca la tasta de volum
		vc.volumeDialog.setValue(0 if v.isMuted() else v.getVolume())
		vc.volSave()

	def inregistreaza(self):
		import NavigationInstance
		nav = NavigationInstance.instance
		return bool(nav is not None and nav.RecordTimer.isRecording())

	def semnal(self):
		"""Procentele barelor de pe televizor (radio_web.semnal_panou) si, din tuner, dB si BER."""
		import NavigationInstance
		from . import radio_web
		rez = {"snr": None, "agc": None, "db": None, "ber": 0, "tip": ""}
		nav = NavigationInstance.instance
		if nav is None:
			return rez
		s = radio_web.semnal_panou(nav) or {}
		rez["snr"], rez["agc"] = s.get("calitate"), s.get("putere")
		try:
			serv = nav.getCurrentService()
			fe = serv.frontendInfo() if serv is not None else None
			st = (fe.getFrontendStatus() if fe is not None else None) or {}
			db = st.get("tuner_signal_quality_db")
			if isinstance(db, int) and 0 <= db < 0x12345678:
				rez["db"] = db / 100.0
			rez["ber"] = int(st.get("tuner_bit_error_rate") or 0)
			fd = (fe.getFrontendData() if fe is not None else None) or {}
			rez["tip"] = str(fd.get("tuner_type") or "")
		except Exception as eroare:
			_jurnal("semnalul: %s" % eroare)
		return rez

	def serviciu_info(self):
		import NavigationInstance
		from enigma import iServiceInformation as I
		nav = NavigationInstance.instance
		serv = nav.getCurrentService() if nav is not None else None
		info = serv.info() if serv is not None else None
		if info is None:
			return {}

		def numar(cheie):
			try:
				v = info.getInfo(getattr(I, cheie))
				return v if isinstance(v, int) and v >= 0 else 0
			except Exception:
				return 0

		rez = {"name": info.getName() or "", "provider": "", "width": numar("sVideoWidth"),
			"height": numar("sVideoHeight"), "aspect": numar("sAspect"), "vpid": numar("sVideoPID"),
			"apid": numar("sAudioPID"), "pcrpid": numar("sPCRPID"), "pmtpid": numar("sPMTPID"), "txtpid": numar("sTXTPID"),
			"tsid": numar("sTSID"), "onid": numar("sONID"), "sid": numar("sSID"), "namespace": numar("sNamespace")}
		try:
			rez["provider"] = info.getInfoString(I.sProvider) or ""
		except Exception:
			pass
		return rez

	# receptorul
	def despre(self):
		from Components.About import about
		rez = {}
		for cheie, f in (("brand", about.getBrand), ("model", about.getModel), ("imagine", about.getImageVersionString),
				("enigma", about.getEnigmaVersionString), ("nucleu", about.getKernelVersionString),
				("cip", about.getChipset), ("pornit", about.getUptimeString)):
			try:
				rez[cheie] = f() or ""
			except Exception:
				rez[cheie] = ""
		rez["boxtype"] = _citesteMic("/proc/stb/info/boxtype")
		return rez

	def retea(self):
		"""Placile de retea, cea cu fir prima (Home Assistant ia MAC-ul primei ca semn al receptorului)."""
		try:
			nume = os.listdir("/sys/class/net")
		except OSError:
			nume = []
		nume = [n for n in nume if n != "lo" and re.match(r"^(eth|wlan|ra|wl)\w{0,12}$", n)]
		nume.sort(key=lambda n: (0 if n.startswith("eth") else 1, n))
		dhcp = _citesteMic("/etc/network/interfaces")
		rez = []
		for n in nume:
			ip, masca = _adresaPlaca(n)
			rez.append({"name": n, "mac": _citesteMic("/sys/class/net/%s/address" % n).upper(), "ip": ip, "mask": masca,
				"gw": _poartaRetea(n), "dhcp": bool(re.search(r"^\s*iface\s+%s\s+inet\s+dhcp" % re.escape(n), dhcp, re.M))})
		return rez

	def tunere(self):
		text = _citesteMic("/proc/bus/nim_sockets")
		rez = []
		for r in text.splitlines():
			r = r.strip()
			if r.startswith("NIM Socket"):
				rez.append({"name": "Tuner %s" % chr(ord("A") + len(rez) % 26), "type": ""})
			elif rez and r.startswith("Type:"):
				rez[-1]["type"] = r[5:].strip()
		return rez

	def discuri(self):
		rez = []
		try:
			from Components.Harddisk import harddiskmanager
			for _desc, hd in harddiskmanager.HDDList():
				try:
					liber = int(hd.free())
				except Exception:
					liber = -1
				rez.append({"model": hd.model(), "capacity": hd.capacity(), "free": _marime(liber)})
		except Exception as eroare:
			_jurnal("discurile: %s" % eroare)
		return rez

	def setari(self):
		from Components.config import config
		rez = []
		for nume in SETARI_PERMISE:
			try:
				obiect = config
				for parte in nume.split(".")[1:]:
					obiect = getattr(obiect, parte)
				rez.append((nume, str(obiect.value)))
			except Exception:
				continue
		return rez

	def locuri(self):
		from . import temporizatoare_web
		return temporizatoare_web._locuri()

	def loc_implicit(self):
		try:
			from Components.UsageConfig import preferredTimerPath, defaultMoviePath
			return preferredTimerPath() or defaultMoviePath() or ""
		except Exception:
			return ""

	def ip(self):
		import socket
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			try:
				s.connect(("10.254.254.254", 9))
				ip = s.getsockname()[0]
			finally:
				s.close()
		except Exception:
			return ""
		return "" if not ip or ip.startswith("0.") else ip

	# temporizatoarele
	def rt(self):
		import NavigationInstance
		return NavigationInstance.instance.RecordTimer

	def H(self):
		from Components import HdsInregistrariProgramate
		return HdsInregistrariProgramate

	def T(self):
		from Components import HdsTemporizare
		return HdsTemporizare

	def fabrica(self):
		from RecordTimer import RecordTimerEntry
		return RecordTimerEntry

	def serviciu(self):
		from ServiceReference import ServiceReference
		return ServiceReference

	def verificare(self):
		from Components.TimerSanityCheck import TimerSanityCheck
		return TimerSanityCheck

	# televizorul, siglele
	def popup(self, text, secunde, id_, tip=1):
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		fel = {2: MessageBox.TYPE_WARNING, 3: MessageBox.TYPE_ERROR}.get(tip, MessageBox.TYPE_INFO)
		Notifications.AddPopup(text, fel, secunde, id_)

	def cai_sigle(self):
		return self._cm().cai_sigle()

	def in_fir(self, functie, dupa, termen_s, fel="citire"):
		"""Pe firul `fel` al furnizorului listei de canale: „citire” pentru sigle, FIR_INREGISTRARI pentru lista
		filmelor (un disc USB adormit sau cazut nu opreste siglele)."""
		self._cm().in_fir(functie, dupa, fel=fel, termen_s=termen_s)

	def lista_filme(self):
		"""Citirea listei de filme a panoului (filme_web.citesteLista), cu ordinea de pe televizor. Se cheama pe firul
		enigma2 (setarile, modulul cu textele timpului); functia intoarsa ruleaza pe firul pentru fisiere."""
		from . import filme_web
		F = filme_web._f()
		filme_web.dosarFilme()        # ca pagina panoului: importa Screens.MovieSelection, care face config.movielist
		alfabetic = filme_web._alfabetic()
		return lambda dosar: filme_web.citesteLista(dosar, alfabetic, F)

	def acum(self):
		return time.time()

	# redarea (/file): firul fiecarui flux, predarea pe firul enigma2, termenul deschiderii
	def predaPeFir(self, functie):
		"""Chemata din firul unui flux: `functie` ruleaza pe firul enigma2. reactor.callFromThread: in e2reactor (din
		0.1.7) pune apelul in coada si trezeste bucla prin waker, si cu supportsThreads() pus pe False de mytest.py
		(test_e2reactor_trezire.py, test_callFromThread_trezeste_bucla)."""
		from twisted.internet import reactor
		reactor.callFromThread(functie)

	def ceas(self, secunde, functie):
		"""`functie` peste `secunde`, pe firul enigma2; intoarce un obiect cu cancel()."""
		from twisted.internet import reactor
		return reactor.callLater(secunde, functie)

	def pornesteFir(self, functie, nume):
		import threading
		threading.Thread(target=functie, name=nume, daemon=True).start()


def _adresaPlaca(nume):
	"""(ip, masca) unei placi de retea, prin ioctl; ("", "") fara adresa."""
	try:
		import fcntl
		import socket
		import struct
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			cerere = struct.pack("256s", nume[:15].encode("ascii"))
			ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, cerere)[20:24])        # SIOCGIFADDR
			masca = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x891b, cerere)[20:24])     # SIOCGIFNETMASK
		finally:
			s.close()
		return ip, masca
	except Exception:
		return "", ""


def _poartaRetea(nume):
	"""Poarta implicita a placii, din /proc/net/route."""
	try:
		import socket
		import struct
		for rand in _citesteMic("/proc/net/route").splitlines()[1:]:
			c = rand.split()
			if len(c) > 2 and c[0] == nume and c[1] == "00000000":
				return socket.inet_ntoa(struct.pack("<L", int(c[2], 16)))
	except Exception:
		pass
	return ""


def _marime(mb):
	if mb is None or mb < 0:
		return ""
	if mb >= 1000:
		return "%.1f GB" % (mb / 1000.0)
	return "%d MB" % mb


_FURNIZOR = []


def _m(M=None):
	if M is not None:
		return M
	if not _FURNIZOR:
		_FURNIZOR.append(_Furnizor())
	return _FURNIZOR[0]


# ---------------------------------------------------------------- cererea

class _Cerere(object):
	"""O cerere servita: argumentele (din adresa si din corp, Twisted le pune impreuna), furnizorul si legaturile."""

	def __init__(self, request, L, M, fel):
		self.r = request
		self.L = L
		self.M = M
		self.fel = fel            # "web" (XML) sau "api" (JSON)

	def arg(self, nume, implicit="", maxim=MAX_ARG):
		v = self.r.args.get(nume.encode("ascii"))
		if not v:
			return implicit
		x = v[0]
		if isinstance(x, bytes):
			x = x.decode("utf-8", "replace")
		return x[:maxim]

	def intreg(self, nume, implicit=None):
		try:
			return int(self.arg(nume, "").strip())
		except ValueError:
			return implicit


# ---------------------------------------------------------------- receptorul: deviceinfo, about, ora, semnal, setari

def _info(M):
	d = M.despre()
	brand = curat(d.get("brand"), 60)
	model = curat(d.get("model"), 60)
	if brand and model and not model.lower().startswith(brand.lower()):
		nume = "%s %s" % (brand, model)
	else:
		nume = model or brand or NUME_IMAGINE
	return {"nume": nume, "brand": brand or NUME_IMAGINE, "model": model or nume, "boxtype": curat(d.get("boxtype"), 40),
		"imagine": curat(d.get("imagine"), 60) or NUME_IMAGINE, "enigma": curat(d.get("enigma"), 60) or NUME_IMAGINE,
		"nucleu": curat(d.get("nucleu"), 60), "cip": curat(d.get("cip"), 60), "pornit": curat(d.get("pornit"), 40),
		"retea": M.retea(), "tunere": M.tunere(), "discuri": M.discuri()}


def _prefix(masca):
	try:
		return sum(bin(int(x)).count("1") for x in masca.split("."))
	except ValueError:
		return 0


def h_deviceinfo(c):
	i = _info(c.M)
	if c.fel == "api":
		return _json(c.r, _infoJson(i))
	return _xml(c.r, "e2deviceinfo", [
		("e2enigmaversion", i["enigma"]),
		("e2imageversion", i["imagine"]),
		("e2webifversion", VERSIUNE_WEBIF),
		("e2fpversion", None),
		("e2devicename", i["nume"]),
		("e2distroversion", NUME_IMAGINE),
		("e2frontends", [("e2frontend", [("e2name", t["name"]), ("e2model", t["type"] or "DVB")]) for t in i["tunere"]]),
		("e2network", [("e2interface", [("e2name", n["name"]), ("e2mac", n["mac"]), ("e2dhcp", n["dhcp"]),
			("e2ip", n["ip"]), ("e2gateway", n["gw"]), ("e2netmask", n["mask"])]) for n in i["retea"]]),
		("e2hdds", [("e2hdd", [("e2model", h["model"]), ("e2capacity", h["capacity"]), ("e2free", h["free"])])
			for h in i["discuri"]]),
	])


def _infoJson(i):
	return {"brand": i["brand"], "model": i["model"], "boxtype": i["boxtype"] or i["model"],
		"machinebuild": i["boxtype"] or i["model"], "chipset": i["cip"], "friendlychipsetdescription": i["cip"],
		"webifver": VERSIUNE_WEBIF, "imagedistro": NUME_IMAGINE, "imagever": i["imagine"], "enigmaver": i["enigma"],
		"kernelver": i["nucleu"], "oever": "", "driverdate": "", "fp_version": 0, "uptime": i["pornit"],
		"mem1": "", "mem2": "", "transcoding": False,
		"ifaces": [{"name": n["name"], "friendlynic": n["name"], "mac": n["mac"], "ip": n["ip"], "mask": n["mask"],
			"gw": n["gw"], "dhcp": n["dhcp"], "v4prefix": _prefix(n["mask"]), "ipv6": ""} for n in i["retea"]],
		"tuners": [{"name": t["name"], "type": t["type"]} for t in i["tunere"]],
		"hdd": [{"model": h["model"], "capacity": h["capacity"], "labelled_capacity": h["capacity"], "free": h["free"]}
			for h in i["discuri"]]}


def _serviciuJson(M):
	s = M.serviciu_info() or {}
	rez = {"result": bool(s), "ref": M.ref_acum() or "", "name": curat(s.get("name")), "provider": curat(s.get("provider")),
		"width": s.get("width", 0), "height": s.get("height", 0), "aspect": s.get("aspect", 0),
		"iswidescreen": s.get("aspect", 0) in (3, 4, 7, 8, 0xB, 0xC, 0xF, 0x10)}
	for k in ("vpid", "apid", "pcrpid", "pmtpid", "txtpid", "tsid", "onid", "sid", "namespace"):
		rez[k] = s.get(k, 0)
	return rez


def h_about(c):
	i = _info(c.M)
	if c.fel == "api":
		return _json(c.r, {"result": True, "info": _infoJson(i), "service": _serviciuJson(c.M)})
	s = c.M.serviciu_info() or {}
	prima = i["retea"][0] if i["retea"] else {"mac": "", "dhcp": False, "ip": "", "mask": "", "gw": ""}
	disc = i["discuri"][0] if i["discuri"] else {"model": "", "capacity": "", "free": ""}
	return _xml(c.r, "e2abouts", [("e2about", [
		("e2oeversion", None),
		("e2enigmaversion", i["enigma"]),
		("e2distroversion", NUME_IMAGINE),
		("e2imageversion", i["imagine"]),
		("e2webifversion", VERSIUNE_WEBIF),
		("e2fpversion", None),
		("e2model", i["nume"]),
		("e2lanmac", prima["mac"]),
		("e2landhcp", prima["dhcp"]),
		("e2lanip", prima["ip"]),
		("e2lanmask", prima["mask"]),
		("e2langw", prima["gw"]),
		("e2hddinfo", [("model", disc["model"]), ("capacity", disc["capacity"]), ("free", disc["free"])]),
		("e2tunerinfo", [("e2nim", [("name", t["name"]), ("type", t["type"])]) for t in i["tunere"]]),
		("e2servicename", curat(s.get("name")) or None),
		("e2serviceprovider", curat(s.get("provider")) or None),
		("e2videowidth", s.get("width", 0)),
		("e2videoheight", s.get("height", 0)),
		("e2servicevideosize", "%dx%d" % (s.get("width", 0), s.get("height", 0))),
		("e2apid", s.get("apid", 0)),
		("e2vpid", s.get("vpid", 0)),
		("e2pcrpid", s.get("pcrpid", 0)),
		("e2pmtpid", s.get("pmtpid", 0)),
		("e2txtpid", s.get("txtpid", 0)),
		("e2tsid", s.get("tsid", 0)),
		("e2onid", s.get("onid", 0)),
		("e2sid", s.get("sid", 0)),
	])])


def h_currenttime(c):
	ora = time.strftime("%H:%M:%S", time.localtime(c.M.acum()))
	if c.fel == "api":
		return _json(c.r, {"result": True, "status": True, "time": ora})
	return _xml(c.r, "e2currenttime", ora)


def h_signal(c):
	s = c.M.semnal()
	snr = int(s.get("snr") or 0)
	agc = int(s.get("agc") or 0)
	db = s.get("db")
	if c.fel == "api":
		return _json(c.r, {"result": True, "snr": snr, "snr_db": round(db, 2) if db is not None else 0, "agc": agc,
			"ber": int(s.get("ber") or 0), "tunernumber": 0, "tunertype": s.get("tip") or ""})
	return _xml(c.r, "e2frontendstatus", [
		("e2snrdb", "%.2f dB" % (db or 0.0)),
		("e2snr", "%d %%" % snr),
		("e2ber", int(s.get("ber") or 0)),
		("e2acg", "%d %%" % agc),
		("e2agc", "%d %%" % agc),
	])


def h_settings(c):
	setari = c.M.setari() or [("config.recording.margin_before", "0"), ("config.recording.margin_after", "0")]
	return _xml(c.r, "e2settings", [("e2setting", [("e2settingname", n), ("e2settingvalue", v)]) for n, v in setari])


# ---------------------------------------------------------------- starea (statusinfo), canalul, tastele, volumul

def _eveniment(t):
	"""Tupla lookupEvent „IBDTSE” -> dict; None pentru tupla goala (canal fara date, steagul X)."""
	if not t or t[0] is None:
		return None
	try:
		return {"id": int(t[0] or 0), "begin": int(t[1] or 0), "dur": int(t[2] or 0), "title": curat(t[3]),
			"short": curat(t[4], MAX_DESCRIERE, True), "ext": curat(t[5], MAX_DESCRIERE, True)}
	except (TypeError, ValueError, IndexError):
		return None


def evenimentul(M, ref, fel):
	"""Emisiunea de acum (fel 0) sau urmatoarea (fel 1) a canalului; None fara date."""
	r = ref_epg(ref)
	if not r:
		return None
	try:
		for t in M.epg(["IBDTSE", (r, fel, -1)]):
			return _eveniment(t)
	except Exception as eroare:
		_jurnal("EPG: %s" % eroare)
	return None


def statusinfo(M):
	try:
		vol, mut = M.volum()
	except Exception:
		vol, mut = 0, False
	standby = bool(M.standby())
	try:
		inregistreaza = bool(M.inregistreaza())
	except Exception:
		inregistreaza = False
	ref = M.ref_acum() or ""
	rez = {"result": True, "inStandby": "true" if standby else "false", "isRecording": "true" if inregistreaza else "false",
		"isStreaming": "false", "transcoding": False, "volume": vol, "muted": mut, "currservice_serviceref": ref,
		"currservice_station": "", "currservice_name": "", "currservice_description": "",
		"currservice_fulldescription": "", "currservice_begin": "", "currservice_end": "",
		"currservice_begin_timestamp": 0, "currservice_end_timestamp": 0, "currservice_id": 0,
		"currservice_filename": caleFisier(ref), "in_standby": standby, "imagine": NUME_IMAGINE}
	if ref:
		rez["currservice_station"] = curat(M.nume_serviciu(ref))
		ev = evenimentul(M, ref, 0)
		if ev:
			sfarsit = ev["begin"] + ev["dur"]
			rez.update({"currservice_name": ev["title"], "currservice_description": ev["short"],
				"currservice_fulldescription": "\n".join(x for x in (ev["title"], "%s - %s" % (_ora(ev["begin"]),
					_ora(sfarsit)), ev["short"], ev["ext"]) if x),
				"currservice_begin": _ora(ev["begin"]), "currservice_end": _ora(sfarsit),
				"currservice_begin_timestamp": ev["begin"], "currservice_end_timestamp": sfarsit,
				"currservice_id": ev["id"]})
	return rez


def h_statusinfo(c):
	return _json(c.r, statusinfo(c.M))


def h_zap(c):
	ref = c.arg("sRef", maxim=MAX_REF).strip()
	if not ref_buna(ref):
		return _comanda(c, False, _t("Canalul nu are o referință bună."))
	cale = caleLocala(ref)
	if cale is not None and not fisierPermis(cale, _locuri(c.M)):
		# fara parola din casa: o aplicatie nu porneste pe televizor orice fisier de pe receptor, numai inregistrarile
		_jurnal("zap: fisier in afara locurilor inregistrarilor, refuzat")
		return _comanda(c, False, _t("Dosarul cerut nu este printre locurile înregistrărilor."))
	if c.M.standby():
		return _comanda(c, False, _t("Receptorul e în standby. Pornește-l, apoi alege canalul."))
	try:
		bun, text, _cod = c.L.zap(ref)
	except Exception as eroare:
		_jurnal("zap: %s" % eroare)
		bun, text = False, ""
	if not bun:
		return _comanda(c, False, _t("Canalul nu a pornit."))
	nume = curat(c.M.nume_serviciu(text)) or text
	return _comanda(c, True, _t("Pornește pe televizor: %s") % nume)


def h_remotecontrol(c):
	cod = c.intreg("command")
	fel = c.arg("type").strip().lower()

	def raspuns(bun, text):
		if c.fel == "web":
			return _xml(c.r, "e2remotecontrol", [("e2result", bool(bun)), ("e2resulttext", text)])
		return _json(c.r, {"result": bool(bun), "message": text})

	if cod is None or not 0 < cod <= 0x2FF or fel == "ascii":
		return raspuns(False, _t("Tasta nu e cunoscută."))
	try:
		refuz = c.L.refuzSsh(c.r)
	except Exception:
		refuz = None
	if refuz is not None:
		return raspuns(False, curat(refuz.get("message"), MAX_MESAJ) or _t("Tasta nu a plecat."))
	try:
		c.L.trimiteTasta(cod, fel == "long")
	except Exception as eroare:
		_jurnal("tasta %d: %s" % (cod, eroare))
		return raspuns(False, _t("Tasta nu a plecat."))
	return raspuns(True, "%d" % cod)


def h_vol(c):
	M = c.M
	fel = c.arg("set").strip().lower()
	bun, text = True, "OK"
	try:
		if fel in ("", "state"):
			pass
		elif fel == "up":
			M.volumSus()
		elif fel == "down":
			M.volumJos()
		elif fel == "mute":
			M.volumMut()
		elif fel.startswith("set") and fel[3:].isdigit():
			M.volumSeteaza(max(0, min(100, int(fel[3:]))))
		else:
			bun, text = False, _t("Comanda de volum nu e cunoscută.")
		vol, mut = M.volum()
	except Exception as eroare:
		_jurnal("volum: %s" % eroare)
		bun, text, vol, mut = False, _t("Volumul nu se poate schimba acum."), 0, False
	if c.fel == "api":
		return _json(c.r, {"result": bun, "message": text, "current": vol, "ismute": mut})
	return _xml(c.r, "e2volume", [("e2result", bun), ("e2resulttext", text), ("e2current", vol), ("e2ismuted", mut)])


def _standbyAsteapta(M):
	"""True cand un standby cerut sta in coada notificarilor (o fereastra deschisa pe televizor); False si cand nu se
	poate afla."""
	f = getattr(M, "standbyInAsteptare", None)
	if f is None:
		return False
	try:
		return bool(f())
	except Exception:
		return False


def h_powerstate(c):
	"""Standby-ul din aplicatii. Intrarea se face pe loc cand InfoBar e deasupra (notificarea deschide ecranul Standby
	in acelasi apel); cu o fereastra deschisa pe televizor (un meniu, lista de canale, "Ce e nou") ea sta in coada pana
	se inchide fereastra. De aceea starea de dupa intrare se citeste din nou: in coada = "instandby" false,
	"standbypending" true si mesajul (XML: e2instandby false). Iesirea se incheie la urmatorul pas al buclei
	(Screen.close), deci acolo "instandby" false e spus dinainte, ca pana acum."""
	M = c.M
	stare = c.intreg("newstate")
	inainte = bool(M.standby())
	dupa = inainte
	bun, text = True, ""
	intrare = False
	try:
		if stare is None or c.arg("newstate").strip() == "":
			pass
		elif stare == 0:
			if inainte:
				M.iesiStandby()
				dupa = False
			else:
				M.intraStandby()
				intrare, dupa = True, bool(M.standby())
		elif stare == 4:
			if inainte:
				M.iesiStandby()
			dupa = False
		elif stare == 5:
			if not inainte:
				M.intraStandby()
				intrare, dupa = True, bool(M.standby())
		elif stare in (1, 2, 3):
			bun, text = False, _t("Oprirea completă și repornirea nu se fac din aplicații. Folosește telecomanda.")
		else:
			bun, text = False, _t("Starea cerută nu e cunoscută.")
	except Exception as eroare:
		_jurnal("standby: %s" % eroare)
		bun, dupa, intrare = False, inainte, False
	asteapta = not dupa and _standbyAsteapta(M)
	if asteapta and not text:
		text = _t("Standby-ul așteaptă închiderea ferestrei deschise pe televizor; apoi receptorul intră singur în "
			"standby.")
	elif intrare and not dupa:
		bun, text = False, _t("Receptorul nu a intrat în standby.")
	if c.fel == "api":
		rez = {"result": bun, "instandby": dupa}
		if asteapta:
			rez["standbypending"] = True
		if text:
			rez["message"] = text
		return _json(c.r, rez)
	return _xml(c.r, "e2powerstate", [("e2instandby", "true" if dupa else "false")])


def h_message(c):
	text = curat(c.arg("text", maxim=MAX_MESAJ * 2), MAX_MESAJ, randuri=True)
	if not text:
		return _comanda(c, False, _t("Mesajul e gol."))
	tip = c.intreg("type", 1)
	if tip not in (1, 2, 3):
		tip = 1              # 0 (intrebare da/nu) se arata ca informatie: raspunsul nu se intoarce in aplicatie
	timeout = c.intreg("timeout", -1)
	timeout = min(timeout, 3600) if timeout and timeout > 0 else -1
	acum = CEAS()
	if acum - _ULTIMUL_MESAJ[0] < PAUZA_MESAJ_S:
		return _comanda(c, False, _t("Prea multe mesaje. Încearcă din nou peste două secunde."))
	_ULTIMUL_MESAJ[0] = acum
	try:
		c.M.popup(text, timeout, "hds_aplicatie_mesaj", tip)
	except Exception as eroare:
		_jurnal("mesaj: %s" % eroare)
		return _comanda(c, False, _t("Mesajul nu a putut apărea pe televizor."))
	return _comanda(c, True, _t("Mesajul a apărut pe televizor."))


# ---------------------------------------------------------------- buchetele si canalele

def _buchete(M, tip):
	"""[(ref, nume)] buchetele filei, ca lista de pe televizor; niciodata goala: „Toate canalele” la nevoie."""
	try:
		surse = [(r, curat(n)) for r, n in M.surse(tip) if ref_buna(r)]
	except Exception as eroare:
		_jurnal("buchetele %s: %s" % (tip, eroare))
		surse = []
	rez = []
	for r, n in surse:
		for coada in (" (TV)", " (Radio)"):
			if n.endswith(coada):
				n = n[:-len(coada)]
		rez.append((r, n or r))
	if not rez:
		rez.append((M.toate(tip), _t("Toate canalele")))
	return rez


def radacinaBuchete(tip):
	"""Radacina buchetelor filei (bouquets.tv / bouquets.radio), ca in ChannelSelection."""
	return '1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.%s" ORDER BY bouquet' % (1 if tip == "tv" else 2, tip)


def _buchetPermis(M, ref):
	"""(tip, ref) daca `ref` e unul din buchetele date de noi (sau lista de pe televizor, sau „Toate canalele”); altfel
	None. Nicio alta interogare venita din retea nu ajunge la eServiceCenter."""
	if not ref_buna(ref):
		return None
	for tip in ("tv", "radio"):
		try:
			if ref in (M.radacina(tip), M.toate(tip)):
				return tip, ref
		except Exception:
			pass
	for tip in ("tv", "radio"):
		if any(r == ref for r, _n in _buchete(M, tip)):
			return tip, ref
	return None


def _radacinaCeruta(ref):
	"""Fila daca `ref` e radacina buchetelor; un singur buchet (Favorite, „mai multe buchete” oprit) nu e radacina:
	pentru el se dau canalele."""
	for tip in ("tv", "radio"):
		if ref == radacinaBuchete(tip):
			return tip
	return None


def _canale(M, bref, cu_marcaje=False, ascunse=False):
	"""[(ref, nume)] din buchet, in ordinea lui; marcajele numai cu `cu_marcaje`, cele ascunse numai cu `ascunse`."""
	rez = []
	try:
		continut = M.continut(bref)
	except Exception as eroare:
		_jurnal("continutul buchetului: %s" % eroare)
		continut = []
	for r, n in continut:
		if len(rez) >= MAX_SERVICII:
			break
		if not ref_buna(r):
			continue
		s = steaguri(r)
		if s & ASCUNS and not ascunse:
			continue
		if s & DOSAR:
			continue
		if s & (MARCAJ | MARCAJ_NUMEROTAT) and not cu_marcaje:
			continue
		rez.append((r, curat(n) or "<n/a>"))
	return rez


def _servicii(c):
	"""getservices: fara sRef buchetele TV; cu radacina, buchetele filei; cu un buchet, canalele lui (cu marcaje)."""
	M = c.M
	ref = c.arg("sRef", maxim=MAX_REF).strip()
	if not ref:
		return _buchete(M, "tv")
	tip = _radacinaCeruta(ref)
	if tip is not None:
		return _buchete(M, tip)
	permis = _buchetPermis(M, ref)
	if permis is None:
		return []
	return _canale(M, ref, cu_marcaje=True, ascunse=c.arg("hidden") == "1")


def h_getservices(c):
	lista = _servicii(c)
	if c.fel == "api":
		return _json(c.r, {"result": True, "services": [{"servicereference": r, "servicename": n, "pos": i + 1}
			for i, (r, n) in enumerate(lista)]})
	return _xml(c.r, "e2servicelist", [("e2service", [("e2servicereference", r), ("e2servicename", n)]) for r, n in lista])


def h_getallservices(c):
	tip = "radio" if c.arg("type").strip().lower() == "radio" else "tv"
	buchete = []
	total = 0
	for bref, bnume in _buchete(c.M, tip):
		canale = _canale(c.M, bref)[:max(0, MAX_SERVICII - total)]
		total += len(canale)
		buchete.append((bref, bnume, canale))
	if c.fel == "api":
		return _json(c.r, {"result": True, "services": [{"servicereference": br, "servicename": bn,
			"subservices": [{"servicereference": r, "servicename": n} for r, n in canale]} for br, bn, canale in buchete]})
	return _xml(c.r, "e2servicelistrecursive", [("e2bouquet", [("e2servicereference", br), ("e2servicename", bn),
		("e2servicelist", [("e2service", [("e2servicereference", r), ("e2servicename", n)]) for r, n in canale])])
		for br, bn, canale in buchete])


def h_bouquets(c):
	tip = "radio" if c.arg("stype").strip().lower() == "radio" else "tv"
	return _json(c.r, {"result": True, "bouquets": [[r, n] for r, n in _buchete(c.M, tip)]})


# ---------------------------------------------------------------- ghidul (EPG)

def _evXml(ev, ref, nume, acum):
	if ev is None:
		return ("e2event", [("e2eventid", 0), ("e2eventstart", 0), ("e2eventduration", 0), ("e2eventcurrenttime", acum),
			("e2eventtitle", "None"), ("e2eventdescription", "None"), ("e2eventdescriptionextended", "None"),
			("e2eventservicereference", ref), ("e2eventservicename", nume)])
	return ("e2event", [("e2eventid", ev["id"]), ("e2eventstart", ev["begin"]), ("e2eventduration", ev["dur"]),
		("e2eventcurrenttime", acum), ("e2eventtitle", ev["title"] or "None"),
		("e2eventdescription", ev["short"] or "None"), ("e2eventdescriptionextended", ev["ext"] or "None"),
		("e2eventservicereference", ref), ("e2eventservicename", nume)])


def _evJson(ev, ref, nume, acum):
	ev = ev or {"id": 0, "begin": 0, "dur": 0, "title": "", "short": "", "ext": ""}
	return {"id": ev["id"], "begin_timestamp": ev["begin"], "duration_sec": ev["dur"], "now_timestamp": acum,
		"title": ev["title"], "shortdesc": ev["short"], "longdesc": ev["ext"], "sref": ref, "sname": nume,
		"begin": _ora(ev["begin"]) if ev["begin"] else "", "end": _ora(ev["begin"] + ev["dur"]) if ev["begin"] else "",
		"duration": ev["dur"] // 60}


def _lista(c, randuri):
	"""randuri: [(ev sau None, ref, nume)] -> raspunsul XML / JSON al unei liste de emisiuni."""
	acum = int(c.M.acum())
	if c.fel == "api":
		return _json(c.r, {"result": True, "events": [_evJson(ev, r, n, acum) for ev, r, n in randuri]})
	return _xml(c.r, "e2eventlist", [_evXml(ev, r, n, acum) for ev, r, n in randuri])


def _epgBuchet(M, bref, feluri):
	"""Pentru fiecare canal din buchet, cate o emisiune pe fiecare fel (0 acum, 1 urmatoarea), in ordinea buchetului;
	None unde nu sunt date. Un singur apel lookupEvent cu steagul X (o tupla pe cerere, si fara date)."""
	canale = _canale(M, bref)
	cereri = ["IBDTSEX"]
	harta = []
	for r, n in canale:
		e = ref_epg(r)
		for f in feluri:
			harta.append((r, n, f, e is not None))
			if e is not None:
				cereri.append((e, f, -1))
	rezultate = []
	if len(cereri) > 1:
		try:
			rezultate = list(M.epg(cereri))
		except Exception as eroare:
			_jurnal("EPG buchet: %s" % eroare)
			rezultate = None
	if rezultate is not None and len(rezultate) != len(cereri) - 1:
		# o tupla pe cerere nu e garantata pentru orice referinta: cererile una cate una
		rezultate = None
	randuri = []
	poz = 0
	for r, n, f, are in harta:
		ev = None
		if are:
			if rezultate is not None:
				ev = _eveniment(rezultate[poz])
			else:
				ev = evenimentul(M, r, f)
			poz += 1
		randuri.append((ev, r, n))
	return randuri


def _bref(c):
	ref = c.arg("bRef", maxim=MAX_REF).strip()
	return ref if _buchetPermis(c.M, ref) is not None else None


def h_epgnow(c):
	b = _bref(c)
	return _lista(c, _epgBuchet(c.M, b, (0,)) if b else [])


def h_epgnext(c):
	b = _bref(c)
	return _lista(c, _epgBuchet(c.M, b, (1,)) if b else [])


def h_epgnownext(c):
	b = _bref(c)
	return _lista(c, _epgBuchet(c.M, b, (0, 1)) if b else [])


def _sref(c):
	ref = c.arg("sRef", maxim=MAX_REF).strip()
	return ref if eCanal(ref) else None


def h_epgservice(c):
	M = c.M
	ref = _sref(c)
	r = ref_epg(ref) if ref else None
	if not r:
		return _lista(c, [])
	acum = int(M.acum())
	inceput = c.intreg("time")
	if inceput is None or inceput <= 0:
		inceput = acum
	sfarsit = c.intreg("endTime")
	if sfarsit is None or sfarsit <= 0:
		minute = MINUTE_GHID
	elif sfarsit < 100000:
		minute = sfarsit                      # minute de la `time` (asa trimit clientii valorile mici)
	else:
		minute = max(1, (sfarsit - inceput) // 60)
	minute = max(1, min(minute, MINUTE_GHID))
	nume = curat(M.nume_serviciu(ref))
	randuri = []
	try:
		for t in M.epg(["IBDTSE", (r, 0, inceput, minute)]):
			ev = _eveniment(t)
			if ev is not None:
				randuri.append((ev, ref, nume))
			if len(randuri) >= MAX_EVENIMENTE:
				break
	except Exception as eroare:
		_jurnal("EPG canal: %s" % eroare)
	return _lista(c, randuri)


def h_epgservicenow(c):
	ref = _sref(c)
	return _lista(c, [(evenimentul(c.M, ref, 0), ref, curat(c.M.nume_serviciu(ref)))] if ref else [])


def h_epgservicenext(c):
	ref = _sref(c)
	return _lista(c, [(evenimentul(c.M, ref, 1), ref, curat(c.M.nume_serviciu(ref)))] if ref else [])


def h_getcurrent(c):
	M = c.M
	ref = M.ref_acum() or ""
	nume = curat(M.nume_serviciu(ref)) if ref else ""
	s = (M.serviciu_info() or {}) if ref else {}
	acum = int(M.acum())
	evenimente = [_evXml(evenimentul(M, ref, f) if ref else None, ref, nume, acum) for f in (0, 1)]
	return _xml(c.r, "e2currentserviceinformation", [
		("e2service", [("e2servicereference", ref or "None"), ("e2servicename", nume or "None"),
			("e2providername", curat(s.get("provider")) or "None"), ("e2videowidth", s.get("width", 0)),
			("e2videoheight", s.get("height", 0)), ("e2servicevideosize", "%dx%d" % (s.get("width", 0),
				s.get("height", 0)))]),
		("e2eventlist", evenimente),
	])


# ---------------------------------------------------------------- temporizatoarele

def _refTemporizator(t):
	try:
		sr = getattr(t, "service_ref", None)
		ref = getattr(sr, "ref", None)
		if ref is not None and hasattr(ref, "toString"):
			return ref.toString()
		return str(sr or "")
	except Exception:
		return ""


def _temporizatoare(M):
	rt = M.rt()
	return [(t, False) for t in list(rt.timer_list)] + [(t, True) for t in list(rt.processed_timers)]


def _numeTemporizator(t, M):
	try:
		canal = M.H().numeCanal(t)
	except Exception:
		canal = ""
	return curat(getattr(t, "name", "")) or curat(canal) or _t("Înregistrare")


def _decodare():
	"""Components/HdsDecodare cand programul de decodare e pe receptor, altfel None (DECODAREA, sus)."""
	try:
		from Components import HdsDecodare
	except ImportError:
		return None
	try:
		return HdsDecodare if HdsDecodare.exista() else None
	except Exception:
		return None


def _dateTemporizator(t, procesat, M):
	try:
		canal = curat(M.H().numeCanal(t))
	except Exception:
		canal = ""
	stare = 3 if procesat else int(getattr(t, "state", 0) or 0)
	eit = getattr(t, "eit", None)
	try:
		eit = int(eit) if eit is not None else 0
	except (TypeError, ValueError):
		eit = 0
	jurnal = []
	for x in list(getattr(t, "log_entries", []) or [])[-50:]:
		try:
			jurnal.append([int(x[0]), int(x[1]), curat(x[2], 300)])
		except Exception:
			continue
	rez = {"serviceref": _refTemporizator(t), "servicename": canal or "<n/a>", "name": _numeTemporizator(t, M),
		"description": curat(getattr(t, "description", ""), MAX_DESCRIERE, True), "descriptionextended": "",
		"begin": int(t.begin), "end": int(t.end), "duration": max(0, int(t.end) - int(t.begin)),
		"startprepare": int(getattr(t, "start_prepare", 0) or 0), "disabled": 1 if getattr(t, "disabled", False) else 0,
		"justplay": 1 if getattr(t, "justplay", False) else 0, "afterevent": int(getattr(t, "afterEvent", 0) or 0),
		"repeated": int(getattr(t, "repeated", 0) or 0), "dontsave": 1 if getattr(t, "dontSave", False) else 0,
		"backoff": int(getattr(t, "backoff", 0) or 0), "state": stare, "eit": eit,
		"dirname": curat(getattr(t, "dirname", "") or "", 500), "tags": " ".join(curat(x, 40) for x in
			(getattr(t, "tags", None) or [])), "filename": curat(getattr(t, "Filename", "") or "", 500),
		"cancelled": bool(getattr(t, "cancelled", False)), "firsttryprepare": bool(getattr(t, "first_try_prepare", False)),
		"always_zap": 0, "nextactivation": None, "logentries": jurnal,
		"realbegin": time.strftime("%d.%m.%Y %H:%M", time.localtime(int(t.begin))),
		"realend": time.strftime("%d.%m.%Y %H:%M", time.localtime(int(t.end)))}
	D = _decodare()
	if D is not None:
		rez["decodare"] = D.text(bool(getattr(t, "hdsDecodareMaiTarziu", False)))
	return rez


def h_timerlist(c):
	M = c.M
	lista = [_dateTemporizator(t, p, M) for t, p in _temporizatoare(M)]
	if c.fel == "api":
		return _json(c.r, {"result": True, "timers": lista, "locations": _locuri(M)})
	return _xml(c.r, "e2timerlist", [("e2timer", [
		("e2servicereference", d["serviceref"]), ("e2servicename", d["servicename"]), ("e2eit", d["eit"]),
		("e2name", d["name"]), ("e2description", d["description"] or "None"),
		("e2descriptionextended", "None"), ("e2disabled", d["disabled"]), ("e2timebegin", d["begin"]),
		("e2timeend", d["end"]), ("e2duration", d["duration"]), ("e2startprepare", d["startprepare"]),
		("e2justplay", d["justplay"]), ("e2afterevent", d["afterevent"]), ("e2location", d["dirname"] or "None"),
		("e2tags", d["tags"]), ("e2logentries", "\n".join("%d %d %s" % tuple(x) for x in d["logentries"])),
		("e2filename", d["filename"]), ("e2backoff", d["backoff"]), ("e2nextactivation", None),
		("e2firsttryprepare", d["firsttryprepare"]), ("e2state", d["state"]), ("e2repeated", d["repeated"]),
		("e2dontsave", d["dontsave"]), ("e2cancled", d["cancelled"]), ("e2toggledisabled", d["disabled"]),
	]) for d in lista])


def _locuri(M):
	rez = []
	try:
		lista = list(M.locuri() or [])
	except Exception:
		lista = []
	for x in lista + [M.loc_implicit()]:
		x = curat(x, 500)
		if x and not x.endswith("/"):
			x += "/"
		if x and x not in rez:
			rez.append(x)
	return rez or ["/media/hdd/movie/"]


def _campuriTemporizator(c, t=None):
	"""Campurile noi din cerere (sRef, begin, end, name, ...) -> (dict, None) sau (None, motivul)."""
	M = c.M
	ref = c.arg("sRef", maxim=MAX_REF).strip()
	inceput, sfarsit = c.intreg("begin"), c.intreg("end")
	if inceput is None or sfarsit is None or sfarsit <= inceput:
		return None, _t("Ora de început și cea de sfârșit nu sunt bune.")
	if sfarsit - inceput > DURATA_MAX_TEMPORIZATOR_S or sfarsit < M.acum() - 60:
		return None, _t("Ora de început și cea de sfârșit nu sunt bune.")
	campuri = {"begin": inceput, "end": sfarsit}
	if ref:
		if not eCanal(ref):
			return None, _t("Canalul nu are o referință bună.")
		campuri["ref"] = ref
	elif t is None:
		return None, _t("Canalul nu are o referință bună.")
	nume = curat(c.arg("name"), MAX_NUME)
	if nume:
		campuri["name"] = nume
	if c.arg("description", None) is not None:
		campuri["description"] = curat(c.arg("description"), MAX_DESCRIERE, True)
	for cheie, camp in (("justplay", "justplay"), ("disabled", "disabled")):
		v = c.intreg(cheie)
		if v is not None:
			campuri[camp] = bool(v)
	dupa = c.intreg("afterevent")
	if dupa is not None:
		campuri["afterEvent"] = dupa if dupa in (0, 1, 2, 3) else 3
	rep = c.intreg("repeated")
	if rep is not None:
		campuri["repeated"] = rep & 127
	eit = c.intreg("eit")
	if eit is not None and eit > 0:
		campuri["eit"] = eit
	# DOSARUL INREGISTRARII: un loc se ia pe loc; alt dosar il verifica h_timeradd pe firul pentru fisiere
	loc = curat(c.arg("dirname", maxim=MAX_CALE + 1), MAX_CALE + 1).strip()
	if loc and loc.lower() != "none":
		cu_bara = loc if loc.endswith("/") else loc + "/"
		dosar = dosarCerut(loc)
		if cu_bara in _locuri(M):
			campuri["dirname"] = cu_bara
		elif dosar is not None and dosar.startswith(RADACINI_INREGISTRARI):
			campuri["dirname_cerut"] = dosar
		else:
			campuri["dirname_respins"] = True
	etichete = [x for x in c.arg("tags").split() if _ETICHETA.match(x)][:MAX_ETICHETE]
	if etichete:
		campuri["tags"] = etichete
	# DECODAREA (sus): numai cu programul de decodare; o valoare necunoscuta lasa alegerea din oficiu
	D = _decodare()
	if D is not None and c.arg("decodare", None) is not None:
		mai_tarziu = D.dinCerere(c.arg("decodare"))
		if mai_tarziu is not None:
			campuri["hdsDecodareMaiTarziu"] = mai_tarziu and not campuri.get("justplay", False)
	return campuri, None


def _suprapuse(lista, M):
	"""Acelasi text ca pagina /temporizatoare (temporizatoare_web._mesajSuprapunere): cu ce se suprapune (primul din
	lista e chiar temporizatorul nou) sau, cand e singur, ca niciun tuner nu poate prinde canalul la ora aleasa."""
	from . import temporizatoare_web
	try:
		return temporizatoare_web._mesajSuprapunere(list(lista or []), M.H())
	except Exception as eroare:
		_jurnal("suprapunerea: %s" % eroare)
		return ""


def h_timeradd(c):
	"""DOSARUL INREGISTRARII (sus): un dosar care nu e loc al inregistrarilor se verifica pe firul FIR_INREGISTRARI
	(un disc USB adormit nu tine televizorul), iar temporizatorul se pune si raspunsul pleaca dupa, pe firul enigma2."""
	M = c.M
	campuri, motiv = _campuriTemporizator(c)
	if motiv:
		return _comanda(c, False, motiv)
	cerut = campuri.pop("dirname_cerut", None)
	if cerut is None:
		return _puneTemporizator(c, campuri, campuri.pop("dirname_respins", False))
	request = c.r

	def lucru():
		return dosarInregistrare(cerut)

	def dupa(dosar, eroare):
		if eroare is not None:
			_jurnal("dosarul inregistrarii %s nu s-a verificat: %s" % (cerut, eroare))
		elif dosar:
			campuri["dirname"] = dosar
		try:
			corp = _puneTemporizator(c, campuri, "dirname" not in campuri)
		except Exception as e:
			_jurnal("temporizatorul nu s-a pus: %s" % e)
			corp = _refuz(request, (500, _t("Eroare pe receptor."), None))
		try:
			if request.method != b"HEAD":
				request.write(corp)
			request.finish()
		except Exception as e:
			_jurnal("raspunsul temporizatorului nu a plecat (aplicatie plecata?): %s" % e)

	M.in_fir(lucru, dupa, TERMEN_FILME_S, FIR_INREGISTRARI)
	return c.NOT_DONE_YET


def _montari(cale="/proc/mounts"):
	"""{punctul de montare: felul sistemului de fisiere}, din /proc/mounts (un spatiu din cale vine ca \\040)."""
	rez = {}
	try:
		with open(cale, encoding="utf-8") as f:
			for rand in f:
				parti = rand.split()
				if len(parti) >= 3:
					rez[parti[1].replace("\\040", " ")] = parti[2]
	except (IOError, OSError):
		pass
	return rez


def dosarInregistrare(dosar):
	"""Pe firul pentru fisiere (isdir, access, realpath si /proc/mounts). `dosar` (text verificat de dosarCerut, sub
	RADACINI_INREGISTRARI) e un dosar existent in care se poate scrie, iar calea lui reala sta pe un disc: punctul de
	montare al ei nu e radacina receptorului si nu e o memorie (FARA_DISC). -> `dosar` sau None."""
	try:
		if not os.path.isdir(dosar) or not os.access(dosar, os.W_OK):
			return None
		punct, montari = os.path.realpath(dosar), _montari()
		while punct not in montari:
			sus = os.path.dirname(punct)
			if sus == punct:
				return None
			punct = sus
		return None if punct == os.sep or montari[punct] in FARA_DISC else dosar
	except (OSError, ValueError):
		return None


def _puneTemporizator(c, campuri, dosar_respins=False):
	"""Temporizatorul din `campuri` (_campuriTemporizator), pe firul enigma2. `dosar_respins`: dirname cerut nu a trecut,
	inregistrarea merge in locul obisnuit (mesajul o spune). Cu justplay (temporizator de comutare) mesajele spun
	comutarea, nu inregistrarea, iar dosarul nu se pomeneste (o comutare nu scrie nimic pe disc)."""
	M = c.M
	from . import temporizatoare_web
	sr, motiv = temporizatoare_web._serviciu(campuri["ref"], M.serviciu())
	if motiv:
		return _comanda(c, False, motiv)
	comutare = bool(campuri.get("justplay", False))
	nume = campuri.get("name") or curat(M.nume_serviciu(campuri["ref"])) or (_t("Comutare") if comutare else
		_t("Înregistrare"))
	loc = campuri.get("dirname") or M.loc_implicit() or None
	rt = M.rt()
	T = M.T()
	H = M.H()
	try:
		intr = M.fabrica()(sr, campuri["begin"], campuri["end"], nume, campuri.get("description", ""),
			campuri.get("eit"), disabled=campuri.get("disabled", False), justplay=campuri.get("justplay", False),
			afterEvent=campuri.get("afterEvent", 3), checkOldTimers=True, dirname=loc, tags=campuri.get("tags"))
		if campuri.get("repeated"):
			intr.repeated = campuri["repeated"]
		if "hdsDecodareMaiTarziu" in campuri:
			intr.hdsDecodareMaiTarziu = campuri["hdsDecodareMaiTarziu"]
		rez, suprapuse = T.pune(intr, rt)
	except Exception as eroare:
		_jurnal("temporizatorul nu s-a pus: %s" % eroare)
		return _comanda(c, False, _t("Receptorul nu a putut pune comutarea.") if comutare else
			_t("Receptorul nu a putut pune înregistrarea."))
	if rez != T.REZULTAT_PUS:
		return _comanda(c, False, (_t("Nu am pus comutarea.") if comutare else _t("Nu am pus înregistrarea.")) + " " +
			_suprapuse(suprapuse, M))
	if not H.existaInca(rt, intr):
		return _comanda(c, False, _t("Există deja o comutare la fel.") if comutare else
			_t("Există deja o înregistrare la fel."))
	_schimbat(rt, intr)
	_jurnal("temporizator pus din aplicatie: %s (%s)" % (nume, "comutare" if comutare else (loc or "-")))
	if comutare:
		return _comanda(c, True, _t('Am pus comutarea "%s".') % nume)
	text = _t("Am pus înregistrarea „%s”.") % nume
	if dosar_respins:
		text += " " + _t(TXT_DOSAR_RESPINS)
	return _comanda(c, True, text)


def _gaseste(M, ref, inceput, sfarsit):
	T = M.T()
	cautat = T._norm(ref)
	for t, _procesat in _temporizatoare(M):
		try:
			if T._norm(_refTemporizator(t)) == cautat and int(t.begin) == inceput and int(t.end) == sfarsit:
				return t
		except Exception:
			continue
	return None


def _schimbat(rt, t):
	try:
		rt.stateChanged(t)
	except Exception as eroare:
		_jurnal("stateChanged: %s" % eroare)


def h_timerdelete(c):
	M = c.M
	ref = c.arg("sRef", maxim=MAX_REF).strip()
	inceput, sfarsit = c.intreg("begin"), c.intreg("end")
	t = _gaseste(M, ref, inceput, sfarsit) if ref and inceput is not None and sfarsit is not None else None
	if t is None:
		return _comanda(c, False, _t("Înregistrarea nu mai e în listă."))
	nume = _numeTemporizator(t, M)
	rt = M.rt()
	if not M.T().scoate(t, rt):
		return _comanda(c, False, _t("Receptorul nu a putut șterge înregistrarea."))
	_schimbat(rt, t)
	return _comanda(c, True, _t("Am șters „%s”.") % nume)


def h_timercleanup(c):
	rt = c.M.rt()
	try:
		rt.cleanup()
		rt.saveTimer()
	except Exception as eroare:
		_jurnal("curatarea: %s" % eroare)
		return _comanda(c, False, _t("Receptorul nu a putut șterge înregistrările terminate."))
	_schimbat(rt, None)
	return _comanda(c, True, _t("Am șters înregistrările terminate."))


def h_timerchange(c):
	"""Temporizatorul vechi se gaseste exact dupa channelOld + beginOld + endOld; schimbarea trece prin aceeasi
	verificare a suprapunerii ca pe televizor (HdsInregistrariProgramate.modifica)."""
	M = c.M
	vechi = c.arg("channelOld", maxim=MAX_REF).strip()
	inceput, sfarsit = c.intreg("beginOld"), c.intreg("endOld")
	t = _gaseste(M, vechi, inceput, sfarsit) if vechi and inceput is not None and sfarsit is not None else None
	if t is None:
		return _comanda(c, False, _t("Înregistrarea nu mai e în listă."))
	campuri, motiv = _campuriTemporizator(c, t)
	if motiv:
		return _comanda(c, False, motiv)
	H = M.H()
	noi = dict((k, v) for k, v in campuri.items() if k in H.CAMPURI)
	if "ref" in campuri and M.T()._norm(campuri["ref"]) != M.T()._norm(_refTemporizator(t)):
		from . import temporizatoare_web
		sr, motiv = temporizatoare_web._serviciu(campuri["ref"], M.serviciu())
		if motiv:
			return _comanda(c, False, motiv)
		noi["service_ref"] = sr
	rt = M.rt()
	try:
		bun, suprapuse = H.modifica(rt, t, noi, M.verificare())
	except Exception as eroare:
		_jurnal("schimbarea temporizatorului: %s" % eroare)
		return _comanda(c, False, _t("Receptorul nu a putut schimba înregistrarea."))
	if not bun:
		return _comanda(c, False, _t("Nu am salvat schimbarea.") + " " + _suprapuse(suprapuse, M))
	if "disabled" in campuri and bool(campuri["disabled"]) != bool(getattr(t, "disabled", False)):
		if campuri["disabled"]:
			t.disable()
		else:
			t.enable()
		rt.timeChanged(t)
		rt.saveTimer()
	if "tags" in campuri:
		t.tags = campuri["tags"]
		rt.saveTimer()
	_schimbat(rt, t)
	return _comanda(c, True, _t("Am salvat „%s”.") % _numeTemporizator(t, M))


def h_getlocations(c):
	locuri = _locuri(c.M)
	if c.fel == "api":
		return _json(c.r, {"result": True, "locations": locuri})
	return _xml(c.r, "e2locations", [("e2location", x) for x in locuri])


def _locImplicit(M):
	"""Locul de acum al inregistrarilor, cu „/” la coada (/web/getcurrlocation si lista filmelor fara dirname)."""
	loc = curat(M.loc_implicit(), 500)
	if loc and not loc.endswith("/"):
		loc += "/"
	return loc or _locuri(M)[0]


def h_getcurrlocation(c):
	loc = _locImplicit(c.M)
	if c.fel == "api":
		return _json(c.r, {"result": True, "location": loc})
	return _xml(c.r, "e2locations", [("e2location", loc)])


# ---------------------------------------------------------------- inregistrarile (movielist)
# Ce ruleaza unde:
#   firul enigma2: textul lui dirname (dosarCerut), locurile (_locuri, din setari), locul de acum, functia listei
#     panoului (M.lista_filme: setarile si modulul cu textele timpului), cititorul de texte DVB, numele canalelor
#     (M.nume_serviciu, numai cu referinta fara cale: cu cale, enigma2 ar citi iar fisierele de pe disc), raspunsul;
#   firul pentru fisiere FIR_INREGISTRARI: realpath (_radacina), lista panoului, .meta, .eit, .ap, subdosarele.

def _fw():
	"""filme_web: lista de filme a panoului (aceeasi sursa de date, nu o a doua)."""
	from . import filme_web
	return filme_web


def _textDvb():
	"""Cititorul de texte DVB al imaginii (Components/HdsAnalizaFlux.text_dvb), luat pe firul enigma2."""
	from Components.HdsAnalizaFlux import text_dvb
	return text_dvb


def dosarCerut(text):
	"""Dosarul cerut (dirname), verificat numai ca text, fara disc: cale absoluta, fara „..”, fara \\x00 sau alte
	caractere de control, cel mult MAX_CALE; intors cu „/” la coada. None daca nu e bun. Locul il verifica _radacina."""
	if not text or len(text) > MAX_CALE or any(ord(ch) < 0x20 or 0x7f <= ord(ch) <= 0x9f for ch in text):
		return None
	if not os.path.isabs(text) or ".." in text.replace("\\", "/").split("/"):
		return None
	return text if text.endswith("/") or text.endswith(os.sep) else text + "/"


def _radacina(dosar, locuri):
	"""Pe firul pentru fisiere (realpath citeste discul). Calea reala a locului in care sta dosarul, cu separator la
	coada, sau None daca dosarul real nu e in niciun loc. realpath urmeaza legaturile pana la capat, deci o legatura care
	iese din loc nu trece; un loc care e chiar radacina discului („/”) nu se primeste."""
	real = os.path.realpath(dosar).rstrip(os.sep) + os.sep
	for loc in locuri:
		r = os.path.realpath(loc)
		if os.path.dirname(r) == r:
			continue
		r = r.rstrip(os.sep) + os.sep
		if real.startswith(r):
			return r
	return None


def _deschide(cale):
	"""(fd, stat) pentru un fisier obisnuit de langa film; None pentru o legatura (ar putea arata in afara locului), o
	teava sau un dispozitiv (citirea s-ar putea bloca) si pentru orice eroare."""
	import stat
	try:
		if os.path.islink(cale):
			return None
		fd = os.open(cale, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
			| getattr(os, "O_BINARY", 0))
	except (OSError, ValueError):
		return None
	try:
		st = os.fstat(fd)
		if stat.S_ISREG(st.st_mode):
			return fd, st
	except OSError:
		pass
	os.close(fd)
	return None


def _citesteFd(fd, maxim):
	parti = []
	while maxim > 0:
		b = os.read(fd, maxim)
		if not b:
			break
		parti.append(b)
		maxim -= len(b)
	return b"".join(parti)


def _fisierMic(cale, maxim=MAX_FISIER_MIC):
	"""Primii `maxim` octeti dintr-un fisier obisnuit de langa film (_deschide), sau None."""
	x = _deschide(cale)
	if x is None:
		return None
	try:
		return _citesteFd(x[0], maxim)
	except OSError:
		return None
	finally:
		os.close(x[0])


def _lungimeAp(cale):
	"""Secundele din <inregistrare>.ap (perechi pozitie + pts, cate 8 octeti big-endian, lib/dvb/pvrparse.cpp): ultimul
	pts minus primul, pe 33 de biti. 0 daca nu se poate."""
	x = _deschide(cale)
	if x is None:
		return 0
	fd, st = x
	try:
		if st.st_size < 32:
			return 0
		inceput = _citesteFd(fd, 16)
		os.lseek(fd, (st.st_size // 16 - 1) * 16, 0)
		sfarsit = _citesteFd(fd, 16)
		if len(inceput) < 16 or len(sfarsit) < 16:
			return 0
		pts = (int.from_bytes(sfarsit[8:16], "big") - int.from_bytes(inceput[8:16], "big")) & ((1 << 33) - 1)
		return pts // 90000
	except OSError:
		return 0
	finally:
		os.close(fd)


def meta(octeti):
	"""<inregistrare>.meta (lib/dvb/metaparser.cpp, un camp pe rand): referinta canalului, titlul, descrierea, ora
	inregistrarii, etichetele, lungimea in pts (90 kHz), marimea fisierului cand s-a masurat lungimea. Ce lipseste e gol
	sau 0."""
	randuri = (octeti or b"").decode("utf-8", "replace").split("\n")

	def rand(i):
		return randuri[i].rstrip("\r") if i < len(randuri) else ""

	def numar(i):
		try:
			return max(0, int(rand(i).strip() or "0"))
		except ValueError:
			return 0

	return {"ref": rand(0).strip(), "titlu": rand(1), "descriere": rand(2), "ora": numar(3),
		"etichete": rand(4).split(), "pts": numar(5), "marime": numar(6)}


def _prefixDvb(b):
	"""Cati octeti din fata unui text DVB aleg setul de caractere (ETSI EN 300 468, anexa A)."""
	if not b or b[0] >= 0x20:
		return 0
	return {0x10: 3, 0x1F: 2}.get(b[0], 1)


def eit(octeti, titlu, text_dvb):
	"""<inregistrare>.eit (un eveniment EIT: 12 octeti de antet, apoi descriptorii; lib/service/event.cpp) -> {"titlu",
	"scurt", "lung"}, sau None. Limba: cea in care titlul e cel din .meta (aleasa la inregistrare), altfel prima.
	Descrierea lunga: textele descriptorilor 0x4E ai limbii, lipite, cu setul de caractere scris o singura data."""
	b = octeti or b""
	if len(b) <= 12:
		return None
	sfarsit = min(len(b), 12 + ((b[10] & 0x0F) << 8 | b[11]))
	scurte, lungi, limbi = {}, {}, []
	i = 12
	while i + 2 <= sfarsit:
		eticheta, n = b[i], b[i + 1]
		d = b[i + 2:i + 2 + n]
		i += 2 + n
		if len(d) < n:
			break
		if eticheta == 0x4D and n >= 5:
			limba = d[0:3]
			rest = d[4 + d[3]:]
			scurte.setdefault(limba, (d[4:4 + d[3]], rest[1:1 + rest[0]] if rest else b""))
		elif eticheta == 0x4E and n >= 6:
			limba = d[1:4]
			j = 5 + d[4]
			lungi.setdefault(limba, []).append(d[j + 1:j + 1 + d[j]] if j < len(d) else b"")
		else:
			continue
		if limba not in limbi:
			limbi.append(limba)
	if not limbi:
		return None
	dorit = " ".join((titlu or "").split())
	alese = limbi[0]
	if dorit:
		for limba in limbi:
			if limba in scurte and text_dvb(scurte[limba][0], MAX_NUME) == dorit:
				alese = limba
				break
	nume, scurt = scurte.get(alese, (b"", b""))
	parti = lungi.get(alese, [])
	lung = b""
	if parti:
		p = _prefixDvb(parti[0])
		lung = parti[0] + b"".join(x[p:] if p and x[:p] == parti[0][:p] else x for x in parti[1:])
	return {"titlu": text_dvb(nume, MAX_NUME), "scurt": text_dvb(scurt, MAX_DESCRIERE),
		"lung": text_dvb(lung, MAX_DESCRIERE)}


def _datePeDisc(cale, marime, text_dvb):
	"""Pe firul pentru fisiere: ce se citeste langa o inregistrare .ts (.meta, .eit, .ap). Lungimea din .meta numai cand
	marimea scrisa acolo e a fisierului de acum (ca enigma2, lib/service/servicedvb.cpp), altfel din .ap. Langa un film
	(mkv, mp4...) nu e nimic de citit: lungimea ramane 0."""
	if not cale.lower().endswith(".ts"):
		return {"meta": None, "eit": None, "lungime": 0}
	m = meta(_fisierMic(cale + ".meta"))
	try:
		ev = eit(_fisierMic(cale[:-3] + ".eit"), m["titlu"], text_dvb)
	except (IndexError, ValueError, TypeError, LookupError):
		ev = None
	lungime = m["pts"] // 90000 if m["pts"] and m["marime"] == marime else 0
	if not lungime:
		lungime = _lungimeAp(cale + ".ap") or m["pts"] // 90000
	return {"meta": m, "eit": ev, "lungime": lungime if lungime <= DURATA_MAX_TEMPORIZATOR_S else 0}


def _subdosare(dosar):
	"""Pe firul pentru fisiere: numele subdosarelor (fara cele ascunse, ca .Trash, si fara legaturi), pentru
	„bookmarks”."""
	fw = _fw()
	rez = []
	try:
		with os.scandir(dosar) as intrari:
			for x in intrari:
				if x.name.startswith("."):
					continue
				try:
					if not x.is_dir(follow_symlinks=False):
						continue
				except OSError:
					continue
				rez.append(fw._afisat(x.name))
				if len(rez) >= MAX_DOSARE:
					break
	except OSError:
		return []
	return sorted(rez, key=lambda n: n.lower())


def citesteDosar(citeste, dosar, locuri, etichete, text_dvb, maxim=None):
	"""Pe firul pentru fisiere. `citeste` e lista panoului (M.lista_filme), `dosar` si `locuri` sunt cai de disc. ->
	{"stare": "strain"} (dosarul real nu e intr-un loc), {"stare": "necitit"} (dosarul lipseste: discul scos),
	{"stare": "cazut"} (dosarul exista, dar lista panoului nu l-a putut citi: eroare de disc; filme_web.citesteLista
	prinde OSError si da None) sau {"stare": "bun", "filme": [(intrarea listei, datele de pe disc)], "dosare": [...],
	"taiat": bool}."""
	maxim = maxim or MAX_FILME_APLICATII
	radacina = _radacina(dosar, locuri)
	if radacina is None:
		return {"stare": "strain"}
	if not os.path.isdir(dosar):
		return {"stare": "necitit"}
	intrari = citeste(dosar)
	if intrari is None:
		return {"stare": "cazut"}
	fw = _fw()
	cerute = set(etichete or ())
	taiat = len(intrari) >= getattr(fw, "MAX_FILME", len(intrari) + 1)
	filme = []
	for e in intrari:
		cale = fw._caleDisc(e.get("cale") or "")
		if not (os.path.realpath(cale).rstrip(os.sep) + os.sep).startswith(radacina):
			continue
		d = _datePeDisc(cale, e.get("marime"), text_dvb)
		if cerute and not cerute.issubset((d["meta"] or {}).get("etichete") or ()):
			continue
		if len(filme) >= maxim:
			taiat = True
			break
		filme.append((e, d))
	return {"stare": "bun", "filme": filme, "dosare": _subdosare(dosar), "taiat": taiat}


def _codeazaCale(cale):
	"""Calea in referinta, ca eServiceReference::toString: „:”, „%” si caracterele sub 0x20 ca %xx."""
	return "".join("%%%02x" % ord(ch) if ch in ":%" or ord(ch) < 0x20 else ch for ch in cale)


def _canalInregistrarii(M, ref):
	"""Numele canalului inregistrarii: din lista de canale, dupa referinta din .meta (numai primele 10 campuri, fara
	cale), altfel numele scris in referinta, altfel „”."""
	c = _campuri(ref)
	if c is None or c[0][0] != 1:
		return ""
	parti = ref.split(":")
	scurta = ":".join(parti[:10]) + ":"
	nume = ""
	if ref_buna(scurta):
		try:
			nume = curat(M.nume_serviciu(scurta))
		except Exception:
			nume = ""
	if not nume and len(parti) > 11:
		nume = curat(":".join(parti[11:]))
	return nume


def _textLungime(secunde):
	"""„M:SS” (minutele trec de 60: „224:57”), cum citesc Kodi si dreamDroid."""
	secunde = max(0, int(secunde or 0))
	return "%d:%02d" % (secunde // 60, secunde % 60)


def _oraFilm(t):
	"""„9.10., 22:15”, ora locala; „” fara ora."""
	if not t:
		return ""
	try:
		x = time.localtime(int(t))
	except (ValueError, OverflowError, OSError):
		return ""
	return "%d.%d., %02d:%02d" % (x.tm_mday, x.tm_mon, x.tm_hour, x.tm_min)


def _film(M, e, d):
	"""Un film pentru raspuns (firul enigma2): intrarea listei panoului si datele citite langa el."""
	cale = e.get("cale") or ""
	nume_fisier = cale.replace("\\", "/").rsplit("/", 1)[-1]
	m = d.get("meta") or {}
	ev = d.get("eit") or {}
	titlu = (curat(m.get("titlu")) or curat(ev.get("titlu")) or curat(nume_fisier.rsplit(".", 1)[0])
		or curat(nume_fisier) or "-")
	lungime = max(0, int(d.get("lungime") or 0))
	loc = e.get("loc")
	try:
		ora = int(m.get("ora") or e.get("data") or 0)
	except (TypeError, ValueError):
		ora = 0
	etichete = [x for x in (curat(t, 40) for t in (m.get("etichete") or [])[:MAX_ETICHETE]) if x]
	return {"ref": (REF_INREGISTRARE if cale.lower().endswith(".ts") else REF_FILM) + _codeazaCale(cale),
		"titlu": titlu, "scurt": curat(m.get("descriere"), MAX_DESCRIERE, True) or curat(ev.get("scurt"), MAX_DESCRIERE,
		True), "lung": curat(ev.get("lung"), MAX_DESCRIERE, True), "canal": _canalInregistrarii(M, m.get("ref") or ""),
		"ora": max(0, ora), "lungime": lungime, "etichete": " ".join(etichete), "cale": cale, "nume_fisier": nume_fisier,
		"marime": max(0, int(e.get("marime") or 0)),
		"vazut": min(100, int(loc) * 100 // lungime) if loc and lungime else 0}


def _filmXml(f):
	return ("e2movie", [("e2servicereference", f["ref"]), ("e2title", f["titlu"]), ("e2description", f["scurt"]),
		("e2descriptionextended", f["lung"]), ("e2servicename", f["canal"]), ("e2time", f["ora"]),
		("e2length", _textLungime(f["lungime"])), ("e2tags", f["etichete"]), ("e2filename", f["cale"]),
		("e2filesize", f["marime"])])


def _filmJson(f):
	return {"serviceref": f["ref"], "fullname": f["ref"], "filename": f["cale"], "filename_stripped": f["nume_fisier"],
		"eventname": f["titlu"], "description": f["scurt"], "descriptionExtended": f["lung"], "servicename": f["canal"],
		"begintime": _oraFilm(f["ora"]), "recordingtime": f["ora"], "length": _textLungime(f["lungime"]),
		"filesize": f["marime"], "tags": f["etichete"], "lastseen": f["vazut"]}


def _filmeGoale(c, dosar, mesaj):
	"""Fara filme (loc strain, dosar care lipseste): lista goala in XML (asa arata si un dosar gol), „result”: false si
	mesajul in JSON."""
	if c.fel == "web":
		return _xml(c.r, "e2movielist", [])
	return _json(c.r, {"result": False, "message": mesaj, "directory": dosar, "movies": [], "bookmarks": []})


def _filmeDiscOprit(c, dosar, eroare):
	"""Lucrul de pe fir nu s-a intors (termen depasit, fir agatat de un disc care nu raspunde) sau a cazut cu o eroare
	de disc: 503 cu Retry-After in XML (Kodi pastreaza lista veche; una goala ar sterge-o), „result”: false in JSON."""
	_jurnal("lista filmelor din %s: %s %s" % (dosar, type(eroare).__name__, eroare))
	if not (isinstance(eroare, (OSError, IOError)) or type(eroare).__name__ in ("TermenDepasit", "FirAgatat")):
		return _refuz(c.r, (500, _t("Eroare pe receptor."), None))
	return _filmeIndisponibile(c, dosar, _t(TXT_DISC_INCET))


def _filmeIndisponibile(c, dosar, mesaj):
	"""Discul nu a dat lista (nu raspunde sau a cazut in timpul citirii): 503 cu Retry-After in XML, „result”: false in
	JSON."""
	if c.fel == "web":
		return _refuz(c.r, (503, mesaj, {b"retry-after": str(TERMEN_FILME_S).encode("ascii")}))
	return _json(c.r, {"result": False, "message": mesaj, "directory": dosar, "movies": [], "bookmarks": []})


def _filmeRaspuns(c, dosar, rez):
	stare = (rez or {}).get("stare")
	if stare == "strain":
		return _filmeGoale(c, dosar, _t(TXT_LOC_STRAIN))
	if stare == "cazut":
		_jurnal("lista filmelor din %s: dosarul nu s-a putut citi" % dosar)
		return _filmeIndisponibile(c, dosar, _t(TXT_DOSAR_NECITIT))
	if stare != "bun":
		return _filmeGoale(c, dosar, _t(TXT_DOSAR_NECITIT))
	filme = [_film(c.M, e, d) for e, d in rez.get("filme") or []]
	if c.fel == "web":
		return _xml(c.r, "e2movielist", [_filmXml(f) for f in filme])
	raspuns = {"result": True, "directory": dosar, "movies": [_filmJson(f) for f in filme],
		"bookmarks": list(rez.get("dosare") or [])}
	if rez.get("taiat"):
		raspuns["message"] = _t(TXT_LISTA_TAIATA) % MAX_FILME_APLICATII
	return _json(c.r, raspuns)


def h_movielist(c):
	"""/web/movielist si /api/movielist[?dirname=&tag=]: filmele unui loc al inregistrarilor (sau ale unui dosar din el).
	Discul se citeste numai pe firul FIR_INREGISTRARI; raspunsul pleaca de aici, de pe firul enigma2, in `dupa`."""
	M = c.M
	request = c.r
	cerut = c.arg("dirname", maxim=MAX_CALE + 1)
	dosar = dosarCerut(cerut if cerut.strip() else _locImplicit(M))
	if dosar is None:
		return _filmeGoale(c, curat(cerut, MAX_CALE), _t(TXT_LOC_STRAIN))
	etichete = curat(c.arg("tag"), MAX_NUME).split()[:MAX_ETICHETE]
	fw = _fw()
	locuri = [fw._caleDisc(x) for x in _locuri(M)]
	dosar_disc = fw._caleDisc(dosar)
	citeste = M.lista_filme()
	text_dvb = _textDvb()

	def lucru():
		return citesteDosar(citeste, dosar_disc, locuri, etichete, text_dvb)

	def dupa(rez, eroare):
		try:
			if eroare is not None:
				corp = _filmeDiscOprit(c, dosar, eroare)
			else:
				corp = _filmeRaspuns(c, dosar, rez)
		except Exception as e:
			_jurnal("lista filmelor: %s" % e)
			corp = _refuz(request, (500, _t("Eroare pe receptor."), None))
		try:
			if request.method != b"HEAD":
				request.write(corp)
			request.finish()
		except Exception as e:
			_jurnal("lista filmelor nu a plecat (aplicatie plecata?): %s" % e)

	M.in_fir(lucru, dupa, TERMEN_FILME_S, FIR_INREGISTRARI)
	return c.NOT_DONE_YET


# ---------------------------------------------------------------- etichetele (gettags)
# /web/gettags si /api/gettags (0.2.8): etichetele pe care aplicatiile le arata ca filtru al listei
# inregistrarilor (dreamDroid le ia de aici si cere apoi /web/movielist?tag=). Ca pe televizor, unde lista
# inregistrarilor arata etichetele filmelor din dosarul deschis: etichetele din .meta ale inregistrarilor din locul de
# acum (aceeasi lista ca /web/movielist fara dirname: lista panoului, aceleasi paze pentru loc si legaturi, cel mult
# MAX_FILME_APLICATII filme, discul citit numai pe firul FIR_INREGISTRARI, cu TERMEN_FILME_S), plus etichetele
# temporizatoarelor (in memorie, pe firul enigma2). Imaginea nu are fisierul movietags al altor imagini. Raspunsul:
# alfabetic, fara dubluri, cel mult MAX_ETICHETE_LISTA; XML <e2tags><e2tag>...</e2tag></e2tags>, JSON {"result": true,
# "tags": [...]}. Locul lipsa (disc scos) sau strain: numai etichetele temporizatoarelor. Discul care nu raspunde sau
# cade la citire: ca la lista, XML 503 cu Retry-After (aplicatia pastreaza ce avea), JSON "result": false cu mesajul.

MAX_ETICHETE_LISTA = 200


def citesteEtichete(citeste, dosar, locuri, maxim=None):
	"""Pe firul pentru fisiere: etichetele din .meta ale inregistrarilor din `dosar` (cale de disc), pe lista panoului,
	cu pazele lui citesteDosar, fara .eit si .ap. -> {"stare": "strain" | "necitit" | "cazut"} sau {"stare": "bun",
	"etichete": [...]} (in ordinea intalnirii, fara dubluri)."""
	maxim = maxim or MAX_FILME_APLICATII
	radacina = _radacina(dosar, locuri)
	if radacina is None:
		return {"stare": "strain"}
	if not os.path.isdir(dosar):
		return {"stare": "necitit"}
	intrari = citeste(dosar)
	if intrari is None:
		return {"stare": "cazut"}
	fw = _fw()
	etichete = []
	for e in intrari[:maxim]:
		cale = fw._caleDisc(e.get("cale") or "")
		if not cale.lower().endswith(".ts"):
			continue
		if not (os.path.realpath(cale).rstrip(os.sep) + os.sep).startswith(radacina):
			continue
		for x in meta(_fisierMic(cale + ".meta"))["etichete"]:
			if x not in etichete:
				etichete.append(x)
	return {"stare": "bun", "etichete": etichete}


def _eticheteTemporizatoare(M):
	"""Etichetele temporizatoarelor (in asteptare si terminate), din memorie."""
	rez = []
	try:
		lista = _temporizatoare(M)
	except Exception as e:
		_jurnal("etichetele temporizatoarelor: %s" % e)
		return rez
	for t, _terminat in lista:
		for x in (getattr(t, "tags", None) or []):
			rez.append(x)
	return rez


def _eticheteRaspuns(c, etichete, mesaj=None):
	# fara dubluri numai la etichete identice: filtrul listei (/web/movielist?tag=) deosebeste literele mari de cele mici
	vazute = set()
	for x in etichete:
		x = curat(x, 40)
		if x:
			vazute.add(x)
	lista = sorted(vazute, key=lambda x: (x.lower(), x))[:MAX_ETICHETE_LISTA]
	if c.fel == "web":
		return _xml(c.r, "e2tags", [("e2tag", x) for x in lista])
	raspuns = {"result": mesaj is None, "tags": lista}
	if mesaj is not None:
		raspuns["message"] = mesaj
	return _json(c.r, raspuns)


def _eticheteDiscOprit(c, din_temporizatoare, mesaj):
	if c.fel == "web":
		return _refuz(c.r, (503, mesaj, {b"retry-after": str(TERMEN_FILME_S).encode("ascii")}))
	return _eticheteRaspuns(c, din_temporizatoare, mesaj)


def h_gettags(c):
	"""/web/gettags si /api/gettags: etichetele inregistrarilor din locul de acum si ale temporizatoarelor. Discul se
	citeste numai pe firul FIR_INREGISTRARI; raspunsul pleaca de pe firul enigma2, in `dupa`."""
	M = c.M
	request = c.r
	din_temporizatoare = _eticheteTemporizatoare(M)
	dosar = dosarCerut(_locImplicit(M))
	if dosar is None:
		return _eticheteRaspuns(c, din_temporizatoare)
	fw = _fw()
	locuri = [fw._caleDisc(x) for x in _locuri(M)]
	dosar_disc = fw._caleDisc(dosar)
	citeste = M.lista_filme()

	def lucru():
		return citesteEtichete(citeste, dosar_disc, locuri)

	def dupa(rez, eroare):
		try:
			stare = (rez or {}).get("stare")
			if eroare is not None:
				_jurnal("etichetele din %s: %s %s" % (dosar, type(eroare).__name__, eroare))
				if not (isinstance(eroare, (OSError, IOError)) or type(eroare).__name__ in ("TermenDepasit", "FirAgatat")):
					corp = _refuz(request, (500, _t("Eroare pe receptor."), None))
				else:
					corp = _eticheteDiscOprit(c, din_temporizatoare, _t(TXT_DISC_INCET))
			elif stare == "cazut":
				_jurnal("etichetele din %s: dosarul nu s-a putut citi" % dosar)
				corp = _eticheteDiscOprit(c, din_temporizatoare, _t(TXT_DOSAR_NECITIT))
			elif stare == "bun":
				corp = _eticheteRaspuns(c, list(rez.get("etichete") or []) + din_temporizatoare)
			else:
				corp = _eticheteRaspuns(c, din_temporizatoare)
		except Exception as e:
			_jurnal("etichetele: %s" % e)
			corp = _refuz(request, (500, _t("Eroare pe receptor."), None))
		try:
			if request.method != b"HEAD":
				request.write(corp)
			request.finish()
		except Exception as e:
			_jurnal("etichetele nu au plecat (aplicatie plecata?): %s" % e)

	M.in_fir(lucru, dupa, TERMEN_FILME_S, FIR_INREGISTRARI)
	return c.NOT_DONE_YET


# ---------------------------------------------------------------- listele m3u

def _m3u(request, randuri, nume_fisier):
	"""#EXTM3U, apoi #EXTINF si adresa pentru fiecare canal; numai `\\n` (Kodi ia randul cu getline)."""
	request.setResponseCode(200)
	request.setHeader(b"content-type", b"audio/x-mpegurl; charset=utf-8")
	request.setHeader(b"content-disposition", ('attachment; filename="%s"' % nume_fisier).encode("ascii"))
	request.setHeader(b"cache-control", b"no-store")
	parti = ["#EXTM3U\n"]
	for nume, adresa in randuri:
		parti.append("#EXTINF:-1,%s\n%s\n" % (curat(nume).replace(",", " "), adresa))
	return "".join(parti).encode("utf-8")


def h_streamm3u(c):
	M = c.M
	ref = (c.arg("ref", maxim=MAX_REF) or c.arg("sRef", maxim=MAX_REF)).strip()
	adresa = adresaFlux(ref, M.ip()) if eCanal(ref) else None
	if adresa is None:
		return _m3u(c.r, [], "stream.m3u")
	nume = curat(c.arg("name")) or curat(M.nume_serviciu(ref)) or ref
	return _m3u(c.r, [(nume, adresa)], "stream.m3u")


def h_servicesm3u(c):
	M = c.M
	b = _bref(c)
	ip = M.ip()
	randuri = []
	for r, n in (_canale(M, b) if b else []):
		adresa = adresaFlux(r, ip)
		if adresa:
			randuri.append((n, adresa))
	return _m3u(c.r, randuri, "services.m3u")


def h_streamcurrentm3u(c):
	M = c.M
	ref = M.ref_acum() or ""
	adresa = adresaFlux(ref, M.ip()) if eCanal(ref) else None
	return _m3u(c.r, [(curat(M.nume_serviciu(ref)) or ref, adresa)] if adresa else [], "stream.m3u")


# ---------------------------------------------------------------- siglele (/picon, /file), captura (/grab)

def _caleSigla(M, nume):
	"""Calea fisierului <nume>.png in dosarele siglelor (aceleasi ca Renderer/Picon.py); None daca nu e."""
	if not _NUME_SIGLA.match(nume or ""):
		return None
	for d in M.cai_sigle():
		cale = os.path.join(d, nume + ".png")
		if os.path.isfile(cale):
			return cale
	return None


def _siglaDinFisier(M, cale):
	"""/file?file=: numai un PNG dintr-un dosar de sigle (fara .. si fara legaturi care ies din dosar)."""
	if not cale or "\x00" in cale or not cale.lower().endswith(".png"):
		return None
	reala = os.path.realpath(cale)
	for d in M.cai_sigle():
		baza = os.path.realpath(d).rstrip(os.sep) + os.sep
		if reala.startswith(baza) and os.path.isfile(reala):
			return reala
	return None


def _servesteSigla(c, gaseste, NOT_DONE_YET):
	"""Cautarea si citirea pe firul pentru fisiere (un disc USB adormit nu tine televizorul); raspunsul pe firul enigma2."""
	request = c.r
	cap = request.method == b"HEAD"

	def lucru():
		cale = gaseste()
		if cale is None:
			return None
		with open(cale, "rb") as f:
			return f.read(MAX_SIGLA + 1)

	def dupa(octeti, eroare):
		try:
			if eroare is not None or not octeti or len(octeti) > MAX_SIGLA:
				request.setResponseCode(404)
				request.setHeader(b"content-type", b"text/plain; charset=utf-8")
				if not cap:
					request.write(b"Not found\n")
			else:
				request.setResponseCode(200)
				request.setHeader(b"content-type", b"image/png")
				request.setHeader(b"cache-control", b"private, max-age=86400")
				request.setHeader(b"x-content-type-options", b"nosniff")
				if not cap:
					request.write(octeti)
			request.finish()
		except Exception as e:
			_jurnal("sigla nu a plecat (aplicatie plecata?): %s" % e)

	c.M.in_fir(lucru, dupa, TERMEN_SIGLA_S)
	return NOT_DONE_YET


# ---------------------------------------------------------------- redarea inregistrarilor (/file, ts.m3u)
# Ce ruleaza unde:
#   firul enigma2: textul caii (tipRedare) si al antetului Range (intervalCerut), locurile (din setari), limita,
#     antetele raspunsului si fiecare scriere pe conexiune (_Flux, producatorul Twisted);
#   firul fluxului (_Flux._fir, cate unul pentru fiecare flux, niciodata firul „inregistrari” al listei): realpath,
#     deschiderea si fstat (_deschideFlux), fiecare bucata (_citesteBucata), inchiderea fisierului. Rezultatele ajung pe
#     firul enigma2 prin M.predaPeFir.

_INTERVAL = re.compile(r"^\s*bytes\s*=\s*(\d{0,18})\s*-\s*(\d{0,18})\s*$", re.I)
_FLUXURI = []           # fluxurile /file in lucru (firul enigma2); locul se elibereaza cand raspunsul se incheie
_FIRE_FLUX = [0]        # firele de citire vii (si cele ramase pe un disc care nu raspunde)


def _extensie(cale):
	nume = (cale or "").replace("\\", "/").rsplit("/", 1)[-1]
	return nume.rsplit(".", 1)[-1].lower() if "." in nume else ""


def tipRedare(cale, locuri):
	"""Tipul MIME al unui fisier cerut prin /file pentru redare, sau None. Numai textul, fara disc (firul enigma2):
	extensie din TIPURI_REDARE si cale intr-un loc al inregistrarilor sau intr-un dosar din el (fisierPermis: cale
	absoluta, fara „..”, fara caractere de control, cel mult MAX_CALE)."""
	tip = TIPURI_REDARE.get(_extensie(cale))
	if tip is None or not fisierPermis(cale, locuri):
		return None
	return tip


def intervalCerut(antet):
	"""Antetul Range (text) -> (inceput, sfarsit), cu None pentru capatul lipsa: (a, None) = „bytes=a-”, (None, n) =
	ultimii n octeti, (a, b) = de la a la b inclusiv. None fara antet si pentru unul care se ignora (atunci se da tot
	fisierul, cu 200): alta unitate, mai multe intervale, scris altfel."""
	m = _INTERVAL.match(antet or "")
	if m is None or not (m.group(1) or m.group(2)):
		return None
	return (int(m.group(1)) if m.group(1) else None, int(m.group(2)) if m.group(2) else None)


def interval(cerut, marime):
	"""(cod, inceput, sfarsit) pentru un fisier de `marime` octeti: 200 cu tot fisierul, 206 cu intervalul (sfarsitul
	inclus, taiat la marime - 1) sau 416 cand intervalul nu are niciun octet in fisier (inceputul la capat sau dincolo
	de el, sfarsitul inaintea inceputului, ultimii 0 octeti)."""
	if cerut is None:
		return 200, 0, marime - 1
	a, b = cerut
	if a is None:
		if not b or not marime:
			return 416, 0, -1
		return 206, max(0, marime - b), marime - 1
	if a >= marime or (b is not None and b < a):
		return 416, 0, -1
	return 206, a, marime - 1 if b is None else min(b, marime - 1)


def _deschideFlux(cale, locuri):
	"""Pe firul fluxului. (fd, marime) pentru fisierul de redat, sau None: calea reala (realpath, dupa toate
	legaturile) in afara locurilor inregistrarilor, extensia caii reale necunoscuta, fisierul lipsa sau care nu e
	obisnuit (legatura, teava, dispozitiv: _deschide, cu O_NOFOLLOW si O_NONBLOCK). Marimea e cea de acum (fstat): o
	inregistrare care se scrie inca se da pana unde a ajuns."""
	reala = os.path.realpath(cale)
	if _extensie(reala) not in TIPURI_REDARE or _radacina(os.path.dirname(reala), locuri) is None:
		return None
	x = _deschide(reala)
	if x is None:
		return None
	return x[0], x[1].st_size


def _citesteBucata(fd, pozitie, n):
	"""Pe firul fluxului: cel mult `n` octeti de la `pozitie` (b"" la capatul fisierului)."""
	os.lseek(fd, pozitie, 0)
	return _citesteFd(fd, n)


def _optiuniTcp():
	"""(nivel, optiune, valoare) pentru legatura unui flux: TCP_USER_TIMEOUT (cat pot sta datele trimise fara
	confirmare; acopera telefonul plecat in timp ce i se trimite) si keepalive 60 s + 6 sonde la 10 s (telefonul plecat
	cat legatura sta), amandoua TERMEN_TCP_S. Pe Linux, numerele din nucleu cand modulul socket nu le are."""
	import socket
	import sys
	linux = sys.platform.startswith("linux")
	rez = []
	for nume, numar_linux, valoare in (("TCP_USER_TIMEOUT", 18, TERMEN_TCP_S * 1000), ("TCP_KEEPIDLE", 4, 60),
			("TCP_KEEPINTVL", 5, 10), ("TCP_KEEPCNT", 6, (TERMEN_TCP_S - 60) // 10)):
		opt = getattr(socket, nume, None)
		if opt is None and linux:
			opt = numar_linux
		if opt is not None:
			rez.append((socket.IPPROTO_TCP, opt, valoare))
	return rez


def _pazesteLegatura(request):
	"""Legatura fluxului pazita (vezi _optiuniTcp). Fara transport TCP (probele) nu face nimic; o optiune pe care
	nucleul nu o are se sare, fluxul merge oricum."""
	t = getattr(request, "transport", None)
	if t is None or not hasattr(t, "getHandle"):
		return
	try:
		t.setTcpKeepAlive(1)
		s = t.getHandle()
	except Exception as e:
		_jurnal("flux: legatura nepazita: %s" % e)
		return
	for nivel, opt, valoare in _optiuniTcp():
		try:
			s.setsockopt(nivel, opt, valoare)
		except Exception as e:
			_jurnal("flux: optiunea tcp %s nepusa: %s" % (opt, e))


class _Flux(object):
	"""Un raspuns /file cu o inregistrare sau un film. Pe firul enigma2 e producatorul Twisted (push) al cererii:
	pauseProducing, resumeProducing si stopProducing vin de la conexiune. Fisierul il tine firul fluxului (_fir), care
	primeste prin `coada` cate o cerere de bucata (pozitie, octeti) sau None (gata: inchide fisierul si iese).
	Frana: o singura bucata ceruta firului la un moment dat (in_lucru); urmatoarea se cere numai dupa ce cea dinainte a
	fost data conexiunii (request.write) si numai cat conexiunea nu a cerut pauza (tamponul ei e plin)."""

	def __init__(self, c, cale_disc, cale, tip, cerut, locuri):
		import queue
		self.r = c.r
		self.M = c.M
		self.cale_disc = cale_disc
		self.cale = cale
		self.tip = tip
		self.cerut = cerut
		self.locuri = locuri
		self.cap = c.r.method == b"HEAD"
		self.coada = queue.Queue()
		self.adresa = c.L.adresaClient(c.r) or "?"
		self.cine = "%s (%s)" % (numeAplicatie(c.L.antet(c.r, b"user-agent")), self.adresa)
		self.oprit = False          # raspunsul s-a incheiat (trimis, aplicatie plecata, termen, eroare)
		self.raspuns = False        # antetele sunt hotarate
		self.pauza = False          # conexiunea a cerut pauza
		self.in_lucru = False       # o bucata ceruta firului, inca nevenita
		self.producator = False     # inregistrat la cerere (registerProducer)
		self.termen = None
		self.pozitie = 0
		self.sfarsit = -1
		self.lungime = 0
		self.trimis = 0

	# ------------------------------------------------ firul enigma2
	def porneste(self):
		"""Locul, termenul deschiderii si firul. True daca firul a pornit; raspunsul vine apoi din _deschis (sau din
		_laTermen)."""
		_FLUXURI.append(self)
		_FIRE_FLUX[0] += 1
		_pazesteLegatura(self.r)
		try:
			self.r.notifyFinish().addErrback(self._plecat)
		except Exception:
			pass
		try:
			self.termen = self.M.ceas(TERMEN_DESCHIDERE_S, self._laTermen)
			self.M.pornesteFir(self._fir, "HdsWebFlux")
		except Exception as e:
			_FIRE_FLUX[0] = max(0, _FIRE_FLUX[0] - 1)
			self._incheie("firul nu a pornit: %s" % e)
			return False
		return True

	def _scurt(self, cod, text, antete=None):
		"""Un raspuns fara fisier (eroare)."""
		try:
			corp = _refuz(self.r, (cod, text, antete))
			if not self.cap:
				self.r.write(corp)
			self.r.finish()
		except Exception as e:
			_jurnal("raspunsul fluxului nu a plecat (aplicatie plecata?): %s" % e)

	def _laTermen(self):
		"""Discul nu a deschis fisierul in TERMEN_DESCHIDERE_S: 503 cu Retry-After. Firul, cand se intoarce, gaseste
		fluxul oprit si inchide fisierul."""
		self.termen = None
		if self.oprit or self.raspuns:
			return
		self.raspuns = True
		self._scurt(503, _t(TXT_DISC_INCET), {b"retry-after": str(TERMEN_DESCHIDERE_S).encode("ascii")})
		self._incheie("discul nu a raspuns in %d s" % TERMEN_DESCHIDERE_S)

	def _deschis(self, rez):
		"""Rezultatul deschiderii, de la fir: marimea (int), None (fisier care nu se da) sau eroarea."""
		if self.termen is not None:
			try:
				self.termen.cancel()
			except Exception:
				pass
			self.termen = None
		if self.oprit:
			self.coada.put(None)
			return
		self.raspuns = True
		if rez is None or isinstance(rez, bool) or not isinstance(rez, int):
			if rez is None:
				self._scurt(404, "Not found")
				motiv = "fisierul nu se da"
			elif isinstance(rez, (OSError, IOError)):
				self._scurt(503, _t(TXT_DISC_INCET), {b"retry-after": str(TERMEN_DESCHIDERE_S).encode("ascii")})
				motiv = "eroare de disc: %s" % rez
			else:
				self._scurt(500, _t("Eroare pe receptor."))
				motiv = "eroare: %s" % rez
			self._incheie(motiv)
			return
		cod, self.pozitie, self.sfarsit = interval(self.cerut, rez)
		r = self.r
		r.setResponseCode(cod)
		r.setHeader(b"accept-ranges", b"bytes")
		r.setHeader(b"cache-control", b"no-store")
		r.setHeader(b"x-content-type-options", b"nosniff")
		if cod == 416:
			r.setHeader(b"content-type", b"text/plain; charset=utf-8")
			r.setHeader(b"content-range", ("bytes */%d" % rez).encode("ascii"))
			r.setHeader(b"content-length", b"0")
			self._termina("intervalul cerut nu e in fisier (%d octeti)" % rez)
			return
		self.lungime = self.sfarsit - self.pozitie + 1
		r.setHeader(b"content-type", self.tip)
		r.setHeader(b"content-length", str(self.lungime).encode("ascii"))
		if cod == 206:
			r.setHeader(b"content-range", ("bytes %d-%d/%d" % (self.pozitie, self.sfarsit, rez)).encode("ascii"))
		try:
			_jurnal("flux pornit: %s, %s, octetii %d-%d din %d%s" % (self.cine, self.cale, self.pozitie, self.sfarsit,
				rez, " (HEAD)" if self.cap else ""))
		except Exception:
			pass
		if self.cap or self.lungime <= 0:
			self._termina("trimis" if not self.cap else "HEAD")
			return
		try:
			r.registerProducer(self, True)
			self.producator = True
		except Exception as e:
			self._taie("producatorul: %s" % e)
			return
		self._cere()

	def _cere(self):
		"""Urmatoarea bucata, daca nu e una in drum, daca nu e pauza si daca mai e ceva de trimis."""
		if self.oprit or self.pauza or self.in_lucru or self.pozitie > self.sfarsit:
			return
		self.in_lucru = True
		self.coada.put((self.pozitie, min(BUCATA_FLUX, self.sfarsit + 1 - self.pozitie)))

	def _bucata(self, b):
		"""O bucata de la fir: pe conexiune, apoi urmatoarea (sau sfarsitul)."""
		self.in_lucru = False
		if self.oprit:
			return
		if isinstance(b, Exception) or not b:
			self._taie("fisierul nu s-a mai putut citi: %s" % b if isinstance(b, Exception) else "fisierul s-a scurtat")
			return
		b = b[:self.sfarsit + 1 - self.pozitie]
		self.pozitie += len(b)
		self.trimis += len(b)
		try:
			self.r.write(b)         # Twisted poate chema aici pauseProducing (tamponul conexiunii plin)
		except Exception as e:
			self._taie("scrierea: %s" % e)
			return
		if self.oprit:
			return
		if self.pozitie > self.sfarsit:
			self._termina("trimis")
		else:
			self._cere()

	# producatorul (IPushProducer), chemat de conexiune
	def pauseProducing(self):
		self.pauza = True

	def resumeProducing(self):
		self.pauza = False
		self._cere()

	def stopProducing(self):
		self.producator = False
		self._incheie("aplicatia a inchis legatura")

	def _plecat(self, _eroare):
		self._incheie("aplicatia a inchis legatura")

	def _termina(self, motiv):
		"""Raspunsul e intreg: producatorul scos INAINTE de finish (altfel urmatoarea cerere de pe aceeasi conexiune ar
		gasi un producator ramas), apoi finish."""
		if self.producator:
			self.producator = False
			try:
				self.r.unregisterProducer()
			except Exception:
				pass
		try:
			self.r.finish()
		except Exception as e:
			_jurnal("fluxul nu s-a putut incheia (aplicatie plecata?): %s" % e)
		self._incheie(motiv)

	def _taie(self, motiv):
		"""Fisierul nu mai da ce s-a promis in Content-Length (scurtat, sters, eroare de disc): conexiunea se inchide, iar
		aplicatia vede un raspuns taiat, nu unul intreg cu alte date."""
		if self.producator:
			self.producator = False
			try:
				self.r.unregisterProducer()
			except Exception:
				pass
		try:
			self.r.loseConnection()
		except Exception:
			try:
				self.r.transport.loseConnection()
			except Exception as e:
				_jurnal("conexiunea fluxului nu s-a inchis: %s" % e)
		self._incheie(motiv)

	def _incheie(self, motiv):
		"""O singura data: locul se elibereaza pe loc (Kodi inchide o conexiune si deschide alta la fiecare salt), firul
		primeste None (nu mai citeste, inchide fisierul) si fluxul intra in jurnal: cine, ce fisier, cat a trimis."""
		if self.oprit:
			return
		self.oprit = True
		try:
			_FLUXURI.remove(self)
		except ValueError:
			pass
		if self.termen is not None:
			try:
				self.termen.cancel()
			except Exception:
				pass
			self.termen = None
		self.coada.put(None)
		try:
			_jurnal("flux incheiat: %s, %s: %d octeti trimisi din %d (%s)" % (self.cine, self.cale, self.trimis,
				self.lungime, motiv))
		except Exception:
			pass

	def _sigur(self, functie, *a):
		"""Pe firul enigma2: o greseala neprevazuta inchide fluxul (locul se elibereaza, firul iese), nu il lasa agatat."""
		try:
			functie(*a)
		except Exception as e:
			_jurnal("fluxul: %s" % e)
			self._taie("eroare: %s" % e)

	def _firIesit(self):
		_FIRE_FLUX[0] = max(0, _FIRE_FLUX[0] - 1)

	# ------------------------------------------------ firul fluxului
	def _fir(self):
		"""Deschiderea, apoi cate o bucata la fiecare cerere din coada, pana la None; fisierul se inchide aici, pe acelasi
		fir. Nu atinge cererea si nici starea de pe firul enigma2: preda totul prin M.predaPeFir."""
		preda = self.M.predaPeFir
		fd = None
		try:
			try:
				rez = _deschideFlux(self.cale_disc, self.locuri)
			except Exception as e:
				rez = e
			if isinstance(rez, tuple):
				fd, rez = rez
			preda(lambda: self._sigur(self._deschis, rez))
			while fd is not None:
				cerere = self.coada.get()
				if cerere is None:
					break
				try:
					b = _citesteBucata(fd, cerere[0], cerere[1])
				except Exception as e:
					b = e
				preda(lambda b=b: self._sigur(self._bucata, b))
		finally:
			if fd is not None:
				try:
					os.close(fd)
				except OSError:
					pass
			try:
				preda(self._firIesit)
			except Exception:
				pass


def _adresaFisier(c, cale):
	"""http://<ip>[:port]/file?file=<cale codata> pentru listele m3u (fara parola), sau None fara adresa IP."""
	from urllib.parse import quote
	ip = c.M.ip()
	if not ip:
		return None
	port = PORT_WEB
	try:
		port = int(c.r.getHost().port)
	except Exception:
		pass
	gazda = ip if port == PORT_WEB else "%s:%d" % (ip, port)
	return "http://%s/file?file=%s" % (gazda, quote(cale, safe="/"))


def _listaFisier(c, cale):
	"""/web/ts.m3u, /web/tsm3u, /api/tsm3u si /file?action=stream: lista m3u cu adresa /file a unei inregistrari (VLC,
	playerele m3u). Numai textul; fisierul il verifica /file cand se reda."""
	adresa = None
	if REDARE_INREGISTRARI and tipRedare(cale, _locuri(c.M)) is not None:
		adresa = _adresaFisier(c, cale)
	if adresa is None:
		return _m3u(c.r, [], "file.m3u")
	nume = curat(c.arg("name")) or curat(cale.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]) or "-"
	return _m3u(c.r, [(nume, adresa)], "file.m3u")


def h_tsm3u(c):
	return _listaFisier(c, c.arg("file", maxim=MAX_CALE + 1))


def _servesteFisier(c, NOT_DONE_YET):
	"""/file?file=<cale>: o inregistrare sau un film din locurile inregistrarilor (redarea, _Flux); orice alta cale
	merge ca pana acum, la sigle (_servesteSigla: numai PNG din dosarele siglelor). Pe firul enigma2 nu se atinge
	discul: textul caii si al lui Range, locurile din setari si limita."""
	request = c.r
	M = c.M
	cale = c.arg("file", maxim=MAX_CALE + 1)
	if not REDARE_INREGISTRARI or _extensie(cale) not in TIPURI_REDARE:
		return _servesteSigla(c, lambda: _siglaDinFisier(M, cale), NOT_DONE_YET)
	cap = request.method == b"HEAD"
	locuri = _locuri(M)
	tip = tipRedare(cale, locuri)
	if tip is None:
		corp = _refuz(request, (404, "Not found", None))
		return b"" if cap else corp
	if c.arg("action").strip().lower() == "stream":
		corp = _listaFisier(c, cale)
		return b"" if cap else corp
	adresa = c.L.adresaClient(request) or "?"
	ale_lui = sum(1 for f in _FLUXURI if f.adresa == adresa)
	if len(_FLUXURI) >= MAX_FLUXURI or ale_lui >= MAX_FLUXURI_APARAT or _FIRE_FLUX[0] >= MAX_FIRE_FLUX:
		_jurnal("flux refuzat: %s (%s), %s: %d fluxuri in lucru (%d ale lui), %d fire de citire" % (
			numeAplicatie(c.L.antet(request, b"user-agent")), adresa, cale, len(_FLUXURI), ale_lui, _FIRE_FLUX[0]))
		# fluxurile ocupate (ale aparatului sau toate), sau firele de citire ramase pe un disc care nu raspunde (se
		# elibereaza abia cand se intoarce discul sau la repornirea enigma2): atunci mesajul e al discului
		if len(_FLUXURI) >= MAX_FLUXURI or ale_lui >= MAX_FLUXURI_APARAT:
			text = _t(TXT_FLUXURI_OCUPATE) % (MAX_FLUXURI_APARAT, MAX_FLUXURI)
		else:
			text = _t(TXT_DISC_INCET)
		corp = _refuz(request, (503, text, {b"retry-after": str(PAUZA_FLUX_S).encode("ascii")}))
		return b"" if cap else corp
	cerut = None if c.L.antet(request, b"if-range") else intervalCerut(c.L.antet(request, b"range"))
	fw = _fw()
	flux = _Flux(c, fw._caleDisc(cale), cale, tip, cerut, [fw._caleDisc(x) for x in locuri])
	if not flux.porneste():
		corp = _refuz(request, (503, _t(TXT_DISC_INCET), {b"retry-after": str(PAUZA_FLUX_S).encode("ascii")}))
		return b"" if cap else corp
	return NOT_DONE_YET


# ---------------------------------------------------------------- tabelele rutelor

RUTE_WEB = {
	b"deviceinfo": h_deviceinfo, b"about": h_about, b"currenttime": h_currenttime, b"signal": h_signal,
	b"tunersignal": h_signal, b"settings": h_settings, b"getservices": h_getservices,
	b"getallservices": h_getallservices, b"zap": h_zap, b"remotecontrol": h_remotecontrol, b"vol": h_vol,
	b"powerstate": h_powerstate, b"message": h_message, b"epgservice": h_epgservice,
	b"epgservicenow": h_epgservicenow, b"epgservicenext": h_epgservicenext, b"epgnow": h_epgnow,
	b"epgnext": h_epgnext, b"epgnownext": h_epgnownext, b"getcurrent": h_getcurrent, b"timerlist": h_timerlist,
	b"timeradd": h_timeradd, b"timerchange": h_timerchange, b"timerdelete": h_timerdelete,
	b"timercleanup": h_timercleanup, b"getlocations": h_getlocations, b"getcurrlocation": h_getcurrlocation,
	b"movielist": h_movielist, b"gettags": h_gettags,
	b"stream.m3u": h_streamm3u, b"streamm3u": h_streamm3u, b"services.m3u": h_servicesm3u,
	b"servicesm3u": h_servicesm3u, b"streamcurrentm3u": h_streamcurrentm3u, b"ts.m3u": h_tsm3u, b"tsm3u": h_tsm3u,
}

RUTE_API = {
	b"statusinfo": h_statusinfo, b"about": h_about, b"deviceinfo": h_deviceinfo, b"currenttime": h_currenttime,
	b"tunersignal": h_signal, b"bouquets": h_bouquets, b"getservices": h_getservices,
	b"getallservices": h_getallservices, b"zap": h_zap, b"remotecontrol": h_remotecontrol, b"vol": h_vol,
	b"powerstate": h_powerstate, b"message": h_message, b"epgnow": h_epgnow, b"epgnext": h_epgnext,
	b"epgnownext": h_epgnownext, b"epgservice": h_epgservice, b"epgservicenow": h_epgservicenow,
	b"epgservicenext": h_epgservicenext, b"timerlist": h_timerlist, b"timeradd": h_timeradd,
	b"timerchange": h_timerchange, b"timerdelete": h_timerdelete, b"timercleanup": h_timercleanup,
	b"getlocations": h_getlocations, b"getcurrlocation": h_getcurrlocation, b"movielist": h_movielist,
	b"gettags": h_gettags, b"streamm3u": h_streamm3u,
	b"servicesm3u": h_servicesm3u, b"tsm3u": h_tsm3u,
}


class Legaturi(object):
	"""Ce ia modulul din plugin.py: cele doua setari (activ, afara), daca se cere codul si in casa (codAcasa), adresa
	clientului, antetele, daca Host-ul numeste receptorul (gazdaProprie, cu terminatiile routerelor), daca cererea are
	cookie-ul interfetei (areCookie), cheia pentru scripturi, tastele,
	pornirea canalului, refuzul cat ecranul „Acces SSH” e deschis, clasa capturii. Probele dau ale lor."""

	def __init__(self, **campuri):
		self.__dict__.update(campuri)


def _serveste(request, fel, nume, L, M, NOT_DONE_YET, captura):
	eroare = _poarta(request, L, M)
	if eroare is not None:
		return _refuz(request, eroare)
	c = _Cerere(request, L, M, fel)
	c.NOT_DONE_YET = NOT_DONE_YET          # raspunsurile care asteapta discul (lista filmelor)
	if fel == "web":
		nume = request.postpath[0] if getattr(request, "postpath", None) else b""
		h = RUTE_WEB.get(nume)
	elif fel == "api":
		h = RUTE_API.get(nume)
	elif fel == "picon":
		parti = getattr(request, "postpath", None) or [b""]
		text = parti[0].decode("ascii", "replace") if len(parti) == 1 else ""
		if not text.endswith(".png"):
			return _refuz(request, (404, "Not found", None))
		return _servesteSigla(c, lambda: _caleSigla(M, text[:-4]), NOT_DONE_YET)
	elif fel == "file":
		return _servesteFisier(c, NOT_DONE_YET)
	elif fel == "grab":
		return _captura(c, captura)
	else:
		h = None
	if h is None:
		return _refuz(request, (404, "Not found", None))
	try:
		corp = h(c)
	except Exception as e:
		_jurnal("%s/%s: %s" % (fel, nume.decode("ascii", "replace"), e))
		return _refuz(request, (500, _t("Eroare pe receptor."), None))
	if request.method == b"HEAD" and corp is not NOT_DONE_YET:
		return b""
	return corp


def _captura(c, captura):
	"""/grab: parametrii aplicatiilor (format, mode sau o/v, r) pe cei ai capturii panoului (format, mode, width)."""
	if captura is None:
		return _refuz(c.r, (404, "Not found", None))
	fmt = "png" if c.arg("format").strip().lower() == "png" else "jpg"
	mod = c.arg("mode").strip().lower()
	if b"o" in c.r.args:
		mod = "osd"
	elif b"v" in c.r.args:
		mod = "video"
	if mod not in ("all", "osd", "video"):
		mod = "all"
	args = {b"format": [fmt.encode("ascii")], b"mode": [mod.encode("ascii")]}
	latime = c.intreg("r")
	if latime is not None and 0 < latime <= 3840:
		args[b"width"] = [str(latime).encode("ascii")]
	c.r.args = args
	return captura.render_GET(c.r)


def rute(resource, NOT_DONE_YET, L, M=None):
	"""Resursele: {"web": /web, "picon": /picon, "file": /file, "grab": /grab, "api": {nume: resursa noua de sub /api},
	"alege": functie(nume, resursa veche) pentru cele trei rute care exista deja}."""
	_LEG["L"] = L
	_LEG["M"] = M

	captura = None
	Captura = getattr(L, "captura", None)
	if Captura is not None:
		class _CapturaAplicatii(Captura):
			"""Captura panoului, dupa bariera de aici (aplicatiile nu au cookie)."""

			def _poarta(self, request):
				return "aplicatie", None

		captura = _CapturaAplicatii()

	class _Ruta(resource.Resource):
		isLeaf = True

		def __init__(self, fel, nume=None):
			resource.Resource.__init__(self)
			self.fel = fel
			self.nume = nume

		def render(self, request):
			try:
				return _serveste(request, self.fel, self.nume, L, _m(M), NOT_DONE_YET, captura)
			except Exception as e:
				_jurnal("cererea: %s" % e)
				return _refuz(request, (500, _t("Eroare pe receptor."), None))

	class _Alege(resource.Resource):
		"""/api/statusinfo, /api/zap, /api/remotecontrol: forma compatibila pentru aplicatii (Basic, fara ?token=),
		ruta de pana acum pentru panou si scripturi."""
		isLeaf = True

		def __init__(self, vechi, nou):
			resource.Resource.__init__(self)
			self.vechi = vechi
			self.nou = nou

		def render(self, request):
			if esteCerereAplicatie(request, L):
				return self.nou.render(request)
			return self.vechi.render(request)

	return {
		"web": _Ruta("web"),
		"picon": _Ruta("picon"),
		"file": _Ruta("file"),
		"grab": _Ruta("grab"),
		"api": dict((n, _Ruta("api", n)) for n in NUME_API_NOI),
		"alege": lambda nume, vechi: _Alege(vechi, _Ruta("api", nume)),
	}


# ---------------------------------------------------------------- setarile (ecranul de pe televizor si /setari)

def stareSetari(activ, afara=False):
	"""Pentru GET /api/interfata-web: cele doua setari, parola (numai cand aplicatiile sunt pornite) si aplicatiile
	vazute."""
	return {"aplicatii": bool(activ), "aplicatii_afara": bool(afara),
		"parola_aplicatii": parola(creeaza=True) if activ else "", "aplicatii_vazute": vazute() if activ else []}


def seteaza(cheie, text, aplicatii, afara, salveaza, cod_acasa=False):
	"""POST /api/interfata-web-seteaza?aplicatii=0|1 sau ?aplicatii_afara=0|1 (`cheie`). `aplicatii` si `afara` sunt
	config.plugins.hdswebcontrol.aplicatii si .aplicatii_afara, `salveaza` scrie setarile pe disc. `cod_acasa`: randul
	„Cere codul și în rețeaua locală” e pornit (atunci aplicatiile cer parola si din casa, mesajul o spune)."""
	element = afara if cheie == "aplicatii_afara" else aplicatii
	if text not in ("0", "1"):
		if element is afara:
			return {"result": False, "message": _t("Se alege cu aplicatii_afara=0 sau 1.")}
		return {"result": False, "message": _t("Se alege cu aplicatii=0 sau 1.")}
	element.value = text == "1"
	element.save()
	salveaza()
	if element is afara:
		_jurnal("accesul aplicatiilor din afara casei: %s (din web)" % ("pornit" if element.value else "oprit"))
		if element.value:
			mesaj = _t("Salvat. Din afara casei, aplicațiile intră numai cu utilizatorul root și parola %s.")
			mesaj = mesaj % parola(creeaza=True)
		else:
			mesaj = _t("Salvat. Din afara casei, receptorul nu mai răspunde aplicațiilor.")
	else:
		_jurnal("aplicatiile de telefon: %s (din web)" % ("pornite" if element.value else "oprite"))
		if element.value and cod_acasa:
			mesaj = _t("Salvat. Codul se cere și în casă, deci aplicațiile de telefon intră și de acasă numai cu "
				"utilizatorul root și parola %s.") % parola(creeaza=True)
		elif element.value:
			mesaj = _t("Salvat. Aplicațiile de telefon din casă intră fără parolă: în aplicație scrii numai adresa "
				"receptorului.")
		else:
			mesaj = _t("Salvat. Aplicațiile de telefon nu mai primesc răspuns de la receptor.")
	rez = {"result": True, "message": mesaj}
	rez.update(stareSetari(aplicatii.value, afara.value))
	return rez


def parolaNouaWeb(activ, afara=False):
	"""POST /api/interfata-web-seteaza?parola_aplicatii_noua=1."""
	p = parolaNoua()
	rez = {"result": True, "message": _t("Parola nouă pentru aplicații: %s. Scrie-o în aplicațiile pe care le "
		"folosești din afara casei.") % p}
	rez.update(stareSetari(activ, afara))
	return rez
