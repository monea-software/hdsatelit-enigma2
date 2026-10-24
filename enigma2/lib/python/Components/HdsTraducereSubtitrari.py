# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTraducereSubtitrari - traducerea automata a subtitrarilor TEXT: teletextul, subtitrarile din fisiere si textul
# citit din pozele subtitrarilor DVB (Components/HdsOcrSubtitrari.py), prin serviciul ales de om, cu cheia sau adresa
# lui.
#
# SERVICIILE (omul alege unul in setari; din fabrica e Azure, cu rezervele Gemini si serverul din casa), in ordinea din
# liste si din instructiuni (etichetele scurte in ETICHETE):
#   azure   Azure Translator (cheie + regiunea resursei)             api.cognitive.microsofttranslator.com
#   gemini  Gemini, cheia din aistudio.google.com (cheie, modelul)    generativelanguage.googleapis.com
#   libre   LibreTranslate (adresa serverului, cheie numai daca serverul o cere)
#   openai  orice server compatibil OpenAI (adresa, modelul, cheie numai daca o cere), de exemplu Ollama sau LM
#           Studio pe un calculator din casa: atunci textul nu iese din casa
#   deepl   DeepL API (cheie; cheia gratuita veche se termina cu :fx) api-free.deepl.com / api.deepl.com
#   groq    Groq (cheie gsk_..., modelul), format chat/completions    api.groq.com/openai/v1
#   cloudflare  Cloudflare Workers (jetonul, ID-ul contului de 32 de semne hex, modelul), format chat/completions
#           api.cloudflare.com/client/v4/accounts/<ID>/ai/v1
#   google  Google Cloud Translation, Basic v2 (cheie API)            translation.googleapis.com
#           (facturarea e obligatorie si peste cota gratuita se plateste automat: avertismentul din INSTRUCTIUNI)
#   propriu „Adresă proprie”: orice server ales de om, descris prin setari (vezi mai jos)
# La modelele de limbaj (gemini, openai, groq, cloudflare) cererea cere numai traducerea, rand cu rand, cu cateva
# randuri de dinainte ca context; raspunsul se curata (gandurile <think>, ghilimelele, numerele randurilor,
# explicatiile). Groq si Cloudflare au adresa fixa (cheia pleaca numai spre gazda lor, pe https), deci stau in lant
# langa serverul compatibil OpenAI, fiecare cu cheia lui. Campul temperature nu se mai trimite unui server care l-a
# refuzat (400 care il pomeneste: cererea pleaca o data din nou fara el, iar gazda si modelul se tin minte in RAM).
#
# ADRESA PROPRIE (propriu): adresa e un sablon cu locurile {text}, {sursa} (limba pistei sau „auto”), {tinta} (ISO 639-1),
# inlocuite dintr-o singura trecere: in adresa codate pentru URL, in corpul JSON ca sir JSON scapat (fara ghilimelele de
# afara, ca sa mearga in "{text}"), in corpul formular codate ca formular. Metoda GET sau POST (corp JSON sau formular).
# Un antet optional: numele in setari, valoarea = cheia serviciului `propriu` din fisierul criptat. Traducerea din
# raspuns: tot corpul („text simplu”) sau o cale in JSON (chei si indici despartiti prin punct, „*” = toate
# elementele, bucatile lipite in ordine; de ex. data.translations.0.translatedText, 0.*.0). Fiecare rand pleaca
# intr-o cerere separata. http numai pentru adrese din reteaua de acasa (adresaInCasa); altfel https cu certificate
# verificate. La o cale care nu gaseste nimic sau un raspuns care nu e JSON, mesajul (televizor, web) arata inceputul
# corpului raspunsului (fara cheie); jurnalul nu-l scrie niciodata.
#
# ADRESELE (sectiunea „adresele”): adresa receptorului insusi (127.0.0.0/8, localhost, 0.0.0.0, ::1, 169.254.x,
# IP-urile lui, si numele care se rezolva in ele) nu poate fi server de traducere: refuzata la scriere (clasaAdresa,
# fara DNS) si la conectare (verificaConexiunea, pe socketul legat, inainte de cerere; eroarea E_ADRESA). Tot la
# conectare, http:// numai spre reteaua de acasa; fara redirectionari si fara proxy-uri din mediu.
#
# CHEILE: in /etc/enigma2/hdsatelit/traducere-chei.bin (drepturi 0600, criptat cu o cheie facuta din identitatea
# receptorului), nu in /etc/enigma2/settings. Ecranele si web-ul le pot numai scrie si sterge; starea spune doar daca
# exista. Identitatea (identitateAparat, plicul v2) e facuta numai din ce ramane la flash: adresa placii de retea si
# CID-ul memoriei eMMC (scris in cip, se citeste numai pe acel receptor; adresa singura se vede in retea si are
# putina entropie). /etc/machine-id nu intra: il face din nou dbus la prima pornire dupa fiecare flash. Fisierul vechi
# (plicul v1, adresa | machine-id) se citeste si se recripteaza v2 la pornire (verificaLaPornire); unul care nu se mai
# poate citi deloc se muta in traducere-chei.bin.vechi, cu mesajul o singura data si nota din ecran si web pana cand
# omul pune o cheie (textCheiDinNou).
# Cheia unui serviciu cu adresa aleasa de om (libre, openai, propriu) e legata de gazda pentru care a fost pusa si
# pleaca numai spre ea, numai pe https sau spre reteaua de acasa (cheiePentru); o adresa schimbata spre alt server
# primeste cererile fara cheie.
# Jurnalul nu scrie niciodata o cheie, o adresa cu parametri sau textul subtitrarilor: numai serviciul, codul HTTP si
# felul erorii.
#
# DRUMUL (lib/gui/esubtitle.cpp, setTranslationHandler): nucleul da textele fiecarei pagini text inainte s-o
# deseneze; pagina deja tradusa (memoria) se deseneaza tradusa pe loc. Altfel cererea pleaca acum si ecranul ramane GOL
# pana vine traducerea: nucleul tine paginile intr-o coada de afisare, le arata in
# ordine, fiecare cel putin cat ar fi stat originalul si cel putin timpul de citire (setarea „Timpul de citire”,
# TIMP_CITIRE). Originalul nu apare niciodata inaintea traducerii: cand traducerea nu vine (termenul asteptareMs(),
# eroare, pauza, campuri lipsa) se arata originalul cu semnul textNetradus() in fata, iar traducerea venita mai tarziu nu
# se mai pune. laPagina intoarce lista (din memorie), True (vine prin setTranslation), None (nu se traduce: originalul cu
# semn) sau False (deja in limba tinta: originalul curat). Fiecare pagina asteptata primeste un raspuns:
# setTranslation(gen, traducerea) sau setTranslation(gen, []) = renunt (_renunta). Paginile vin si din timp: teletextul
# sosit inainte de afisare (prefetchText din servicedvb.cpp, generatia 0) si textul OCR gata inainte de afisare
# (HdsOcrSubtitrari cheama inainte()): cererea pleaca atunci, iar la afisare traducerea e de obicei in memorie.
#
# LANTUL SERVICIILOR: serviciul ales, apoi serviciile de rezerva in ordine (setarea rezerve, coduri despartite prin
# virgula; numai cele cu campurile complete: si cand principalului ii lipseste cheia, lucreaza prima rezerva completa,
# fara mesaj). Settings fara randul serviciului si cu cheia Gemini (serviciul din fabrica pana la 0.1.8) pastreaza
# Gemini (mutaServiciulVechi, in initConfig). Serviciul si rezervele se scriu in settings si cand sunt egale cu valoarea
# din fabrica (save_forced; randul lipsa pus in legaNucleul, dupa verificarea cheilor: SETARI_FIXE din
# Components/HdsCopieSetari.py), ca o alta valoare din fabrica intr-o versiune noua sa nu mute alegerea omului.
# La o eroare din FELURI_TRECERE (limita atinsa, cheie refuzata, termen, retea, model sau limba) sau un raspuns 5xx
# cererea trece pe loc, singura, la urmatorul serviciu liber din lant, fara pauza si fara original;
# serviciul cazut asteapta (durataBlocarii: cat spune el la 429, Retry-After sau retryDelay, altfel PAUZA_COTA_S; limita
# pe zi: la Gemini pana la miezul noptii ora Pacific, altfel LIMITA_ZI_S; retea, termen, 5xx: pauze crescatoare de la
# PAUZA_COTA_S pana la PAUZA_S; cheie refuzata: PAUZE_REFUZ_S, iar la al REFUZURI_OPRIRE-lea refuz la rand serviciul e
# oprit, cu mesaj, si se mai incearca singur o data pe ora; adresa refuzata la conectare: pana la schimbarea setarilor),
# apoi revine primul. La pornire prima cerere asteapta reteaua si ceasul (asteaptaPornirea). Pe televizor nimic pentru
# o trecere care merge; numai cand toate cad: pauza si mesajul o data (limita pe minut: fara mesaj; limita pe zi:
# mesajul cu sfatul). Memoria tine traducerile fiecarui serviciu sub numele
# lui; o pagina gasita in memoria oricaruia din lant se deseneaza pe loc. Proba incearca numai serviciul ales.
#
# MAI PUTINE CERERI: o singura cerere deodata (MAX_IN_ZBOR); cat e una in zbor, lucrarile noi asteapta, apoi pleaca toate
# intr-o singura cerere (randurile numerotate la modelele de limbaj, liste la celelalte; la adresa proprie tot un rand pe
# cerere); o cerere din timp (generatia 0) asteapta FEREASTRA_LOT_MS, ca randurile venite intre timp sa plece in ea (o
# pagina de pe ecran trezeste firul pe loc). Nicio pagina asteptata nu se sare (coada nucleului le arata pe toate, in
# ordine); numai una ramasa prea veche (PAGINA_VECHE_S) sau fara niciun serviciu liber primeste renuntarea.
#
# FIRELE: cererile HTTP merg in cel mult MAX_IN_ZBOR fire separate (niciodata pe firul enigma2). Rezultatul se pune
# intr-o lista sub lacat, iar firul scrie un octet intr-un pipe al carui capat de citire e urmarit de eSocketNotifier
# pe firul enigma2 (ca la Components/HdsOcrSubtitrari.py si _AsteptareCaptura din HdsWebControl/plugin.py: fara
# reactor.callLater si fara reactor.callFromThread); plasa de siguranta: un eTimer cat sunt cereri in lucru.
# Coada e marginita (MAX_COADA); o cerere a carei pagina a trecut demult nu mai pleaca.
#
# TIMPUL: termenul unei cereri HTTP vine din viteza masurata a serviciului (media alunecatoare): 3 x media + 1 s,
# intre TERMEN_MINIM_MS si TERMEN_MAXIM_MS. Asteptarea fara nimic pe ecran (asteptareMs, termenul din nucleu): cu
# „Traducerea care întârzie” = „Se pune când vine”, ASTEPTARE_SIGURANTA_MS (traducerea se asteapta; Python renunta
# singur mai devreme la o eroare); cu „Rămâne originalul”, ASTEPTARE_MAXIMA_MS, apoi originalul cu semn ramane.
#
# ERORILE: vezi lantul; cand toate serviciile au cazut, pauza pana revine primul (cel mult PAUZA_S cand nu se stie) si
# un mesaj scurt, o singura data, pe televizor; CADERI_MAXIME erori la rand -> serviciul asteapta PAUZA_S. Setarile
# schimbate sau Probeaza traducerea reusita opresc pauzele. Un serviciu oprit dupa refuzurile cheii primeste mesajul
# lui o singura data (televizor), iar starea lui sta in stare()["oprite"] si in stareLant ("refuzat"), pentru web si
# pentru ecran (textOprit, textCeFaciRefuz). Pauzele, refuzurile si serviciile oprite stau numai in memorie. Fara
# niciun serviciu cu campurile cerute, functia nu cere nimic si spune o singura data ce lipseste.
#
# MEMORIA: traducerile in RAM (MEMORIE_INTRARI randuri, cel mult MEMORIE_CARACTERE litere), dupa serviciu, limba tinta
# si text; nimic pe disc (memoria interna nu se uzeaza). Acelasi rand nu se cere a doua oara.
#
# GHIDUL (EPG): setarea epg („Tradu EPG”) e folosita de Components/HdsTraducereEpg.py, care traduce titlurile si
# descrierile emisiunilor de pe ecran prin acelasi lant de servicii (traduceAcum cu fel="epg"), pe firul lui. Setarea
# bara („Tradu bara de jos”, Da din fabrica) cere acelui modul numai titlurile emisiunii de acum si urmatoare de pe bara
# de jos, cat timp traducerea e pornita (pornit); „Tradu EPG” pornita le cuprinde oricum.
#
# TELETEXTUL SI HBBTV: setarile teletext ("Tradu teletextul", cu teletext_mod: in pagina sau intr-un panou) si hbbtv
# ("Tradu HbbTV"), oprite din fabrica (consuma din cota), sunt folosite de Components/HdsTraducereTexte.py (acelasi lant,
# aceleasi chei, fel="teletext" / "hbbtv" la modelele de limbaj): paginile de teletext aratate pe televizor
# (Components/HdsTraducereTeletext.py) si textele vazute ale paginilor HbbTV (HdsNavigator/hds-hbbtv.js, prin
# HdsWebControl/traducere_hbbtv_web.py). Lucreaza si cand traducerea subtitrarilor e oprita, ca "Tradu EPG".
#
# API (nucleu, ecrane, web):
#   initConfig()                     setarile (config.hds_traducere)
#   legaNucleul()                    din Screens/SubtitleDisplay.py: functia pusa sau scoasa dupa setari (si la
#                                    schimbare); intai verificaCheileLaPornire() (plicul vechi recriptat, cel necitit
#                                    pus deoparte)
#   textCheiDinNou()                 nota „cheile trebuie puse din nou” pentru ecran si web, "" cand nu e cazul
#   cereOcr()                        traducerea vrea si subtitrarile DVB (Components/HdsOcrSubtitrari.esteOcrPornit)
#   inainte(texte)                   textul OCR gata inainte de afisare: cererea pleaca acum
#   instanta().stare()               dict pentru ecran si web (fara chei), cu contorul; tv_stins / tv_stins_text:
#                                    televizorul stins, deci nimic nu se traduce (TEXT_TV_STINS, textTvStins())
#   instanta().proba(laRezultat)     „Probează traducerea”: o fraza de proba, raspunsul pe firul enigma2
#   chei().schimba(serviciu, valoare) / chei().stare()
#   ceLipseste(), textCeLipseste(), numeServiciu(), SERVICII, LIMBI_TINTA
#   serviciiGata()                   serviciile, afara de cel principal, cu campurile complete (cheia pusa la cele care
#                                    cer cheie): cele care pot deveni principale
#   punePrincipal(serviciu)          „Fă-l principal”: serviciul devine principal si iese din rezerve, fostul principal
#                                    intra primul in rezerve (fara salvare, ca puneRezerve)
#   instructiuni(serviciu)           pasii, cota, depasirea, sursa si pagina_cheie (adresa pentru codul QR, "" = fara)
#   numeAntetBun(), caleBuna(), curataCorp(), motivAdresaPropriu()   verificarile setarilor adresei proprii
#   umpleSablon(), caleJson()        sablonul si calea in JSON (functii pure)
#   clasaAdresa(), adresaInCasa(), textMotivAdresa()   adresele: RECEPTOR / CASA / INTERNET, mesajul refuzului
#   cheiePentru(serviciu, adresa), notaCheie(cfg)       cheia care poate pleca spre o adresa si de ce nu
#   stareCheie(cfg)                  (fel, text) al cheii serviciului ales, pentru web (pusa / oprita / lipsa)
#   textCheiDinNouBland()            nota pentru serviciile fara cheie obligatorie, dupa ce cheile au fost puse deoparte
#   durataBlocarii(), trecatoare(), treceLaUrmatorul()   cat asteapta un serviciu dupa o eroare (si ghidul, teletextul)
#   asteaptaPornirea()               pe un fir de cereri: o data pe pornire, reteaua si ceasul (cel mult
#                                    PORNIRE_ASTEPTARE_S)
#   textOprit(), textCeFaciRefuz(), textAzureToateRegiunile()   mesajele refuzului cheii (televizor, web, proba)
#   locServiciu(), etichetaLoc(), numeCuLoc()   unde lucreaza un serviciu (pe internet / local), pentru toate listele
#   puneEticheteleServiciilor()      alegerea Serviciul de pe televizor cu unde lucreaza fiecare
#   contCloudflareBun(), MODELE_GROQ, MODELE_CLOUDFLARE   ID-ul contului Cloudflare si modelele propuse (ecran, web)

from __future__ import absolute_import

import base64
import errno
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import ssl
import threading
import time
from collections import OrderedDict, deque

try:
	from urllib.request import Request, build_opener, HTTPSHandler, HTTPHandler, HTTPRedirectHandler, ProxyHandler
	from urllib.error import HTTPError, URLError
	from urllib.parse import urlsplit, quote, quote_plus
	import http.client as _http
except ImportError:		# Python 2 (probele vechi); pe receptor e Python 3
	from urllib2 import Request, build_opener, HTTPSHandler, HTTPHandler, HTTPRedirectHandler, HTTPError, URLError, \
		ProxyHandler
	from urlparse import urlsplit
	from urllib import quote, quote_plus
	import httplib as _http

# ------------------------------------------------------------------ reglaje

MAX_IN_ZBOR = 1               # o singura cerere deodata; serviciile din lant se incearca pe rand, pe acelasi fir
MAX_COADA = 8                 # cereri care asteapta un fir; peste, cea mai veche pleaca (serverul din casa: una)
FEREASTRA_LOT_MS = 300        # o cerere „din timp” (generatia 0) asteapta atat, ca randurile venite intre timp sa plece in ea
MAX_RANDURI_CERERE = 24       # randurile lipite intr-o singura cerere (din lucrarile care asteapta)
INTARZIERE_LENTA_MS = 1500    # o pagina tradusa la atat dupa afisare (sau sarita) e „prea tarziu”
PAGINI_LENTE = 8              # atatea la rand: mesajul „vine prea tarziu”, o singura data
PAGINA_VECHE_S = 8.0          # o pagina afisata de atat timp nu mai merita ceruta (o subtitrare sta 1-7 s)
INAINTE_VECHE_S = 25.0        # o cerere „din timp” mai veche de atat nu mai pleaca
TERMEN_MINIM_MS = 3000
TERMEN_MAXIM_MS = 10000
TERMEN_PORNIRE_MS = 8000      # inainte de prima masuratoare
ASTEPTARE_MAXIMA_MS = 2000    # „Rămâne originalul”: ecranul gol cel mult atat, apoi originalul cu semn (si ramane)
ASTEPTARE_SIGURANTA_MS = 10000  # „Se pune când vine”: termenul de siguranta al nucleului (Python renunta de obicei inainte)
# „Timpul de citire” (setarea citire): cat sta cel putin o subtitrare tradusa, dupa lungime: (baza ms, ms pe semn,
# cel putin ms, cel mult ms), date nucleului (setReadingTime). Obisnuit: ~17 semne pe secunda (ghidurile obisnuite de
# subtitrare), 1,5 s (un rand scurt venit decalat de vorbire trebuie observat) pana la 7 s (plafonul obisnuit).
TIMP_CITIRE = {"normal": (700, 60, 1500, 7000), "lung": (900, 80, 2000, 8000), "foarte_lung": (1200, 100, 2500, 9000)}
PAUZA_S = 300
PAUZA_COTA_S = 30             # limita pe minut (429) cand serviciul nu spune cat sa astepte; si dupa un termen sau o eroare de
                              # retea, cand cererea a trecut la urmatorul serviciu din lant
MAX_ASTEPTARE_SCURTA_S = 120  # asteptarea spusa de serviciu (Retry-After, retryDelay) se taie la atat
LIMITA_ZI_S = 6 * 3600        # limita pe zi (sau pe luna) la serviciile fara ora de reinnoire stiuta: se reincearca dupa 6 ore
                              # (la Gemini: la miezul noptii, ora Pacific, cand se reinnoiesc cererile pe zi)
TRECERI = 10                  # trecerile la alt serviciu tinute minte (contorul)
CADERI_MAXIME = 3
# CHEIA REFUZATA (401/403 de autentificare): un singur refuz nu opreste serviciul. Dupa primul refuz serviciul
# asteapta PAUZE_REFUZ_S[0], dupa al doilea PAUZE_REFUZ_S[1]; abia al REFUZURI_OPRIRE-lea refuz la rand (deci la
# cel putin 6 minute de primul) il opreste: mesajul o data pe televizor, starea 'refuzat' in web, cu ce are omul de
# facut. Oprit, serviciul se mai incearca singur o data la REVERIFICARE_REFUZ_S (o cheie sau o resursa reparata in
# contul serviciului revine fara nimic schimbat pe receptor). O reusita, o proba reusita, setarile sau cheile
# schimbate sterg numaratoarea. Nimic nu se scrie pe disc: dupa o repornire sau o actualizare serviciul porneste curat.
REFUZURI_OPRIRE = 3
PAUZE_REFUZ_S = (60, 300)
REVERIFICARE_REFUZ_S = 3600
# PORNIREA: prima cerere dupa pornirea enigma2 asteapta ruta implicita si ceasul sigur (NTP sau transpondere), cel mult
# PORNIRE_ASTEPTARE_S de la incarcarea modulului (asteaptaPornirea), pe firul cererilor, niciodata pe firul enigma2
PORNIRE_ASTEPTARE_S = 25.0
PORNIRE_PAS_S = 0.5
MEMORIE_INTRARI = 1500
MEMORIE_CARACTERE = 300000
CONTEXT_RANDURI = 3           # randurile de dinainte date modelelor de limbaj
MAX_TEXT = 500                # litere pe element trimise la traducere
MAX_RASPUNS = 256 * 1024
ULTIMELE = 12
CEAS_SIGURANTA_MS = 250

CALE_CHEI = "/etc/enigma2/hdsatelit/traducere-chei.bin"
# plicul fisierului cheilor: 1 = identitateVeche (adresa | /etc/machine-id, se schimba la flash), 2 = identitateAparat
VERSIUNE_CHEI = 2
VERSIUNI_CHEI = (1, 2)
# fisierul care nu se mai poate citi, pus deoparte la pornire langa cel bun (verificaLaPornire): <cale>.vechi; il
# sterge urmatoarea scriere buna
SUFIX_CHEI_VECHI = ".vechi"
MAX_CHEIE = 512

# ordinea din liste (televizor, web) si din instructiuni: Azure (recomandat pentru subtitrari zilnice), Gemini, serverul
# din casa (LibreTranslate, compatibil OpenAI), DeepL, Groq, Cloudflare Workers, Google Cloud, adresa proprie; primul e
# cel din fabrica
SERVICII = ("azure", "gemini", "libre", "openai", "deepl", "groq", "cloudflare", "google", "propriu")
SERVICIU_IMPLICIT = SERVICII[0]
# rezervele din fabrica: lantul Azure -> Gemini -> serverul din casa (cele fara campurile complete se sar)
REZERVE_IMPLICITE = "gemini,libre,openai"
# ce cere fiecare serviciu: campurile obligatorii (cheie, regiune, adresa, model); la propriu ceLipseste spune si
# calea (raspuns JSON), locul {text} si adresa http din afara casei
CERE = {
	"azure": ("cheie",),
	"google": ("cheie",),
	"deepl": ("cheie",),
	"libre": ("adresa",),
	"gemini": ("cheie", "model"),
	"openai": ("adresa", "model"),
	"groq": ("cheie", "model"),
	"cloudflare": ("cheie", "cont", "model"),
	"propriu": ("adresa",),
}
MAX_CORP_PROPRIU = 1000       # corpul-sablon al adresei proprii (semne)
MAX_CALE = 300
MAX_INCEPUT = 300             # semnele din inceputul raspunsului aratate in mesajul de eroare (adresa proprie)
MODEL_GEMINI_IMPLICIT = "gemini-3.5-flash-lite"
MODELE_DE_LIMBAJ = frozenset(("gemini", "openai", "groq", "cloudflare"))
# Groq: modele production din planul gratuit (cele preview pot fi scoase oricand); primul e cel din fabrica
MODELE_GROQ = ("openai/gpt-oss-20b", "openai/gpt-oss-120b")
MODEL_GROQ_IMPLICIT = MODELE_GROQ[0]
GROQ_ADRESA = "https://api.groq.com/openai/v1/chat/completions"
# Cloudflare Workers: modelele in format chat/completions, cu costul mic in unitatile zilnice gratuite; primul e cel din
# fabrica. Adresa are ID-ul contului (32 de semne hex, verificat in ceLipseste)
MODELE_CLOUDFLARE = ("@cf/google/gemma-4-26b-a4b-it", "@cf/openai/gpt-oss-20b", "@cf/meta/llama-4-scout-17b-16e-instruct")
MODEL_CLOUDFLARE_IMPLICIT = MODELE_CLOUDFLARE[0]
CLOUDFLARE_ADRESA = "https://api.cloudflare.com/client/v4/accounts/%s/ai/v1/chat/completions"
_CONT_CLOUDFLARE = re.compile(r"^[0-9a-f]{32}$")

AZURE_ADRESA = "https://api.cognitive.microsofttranslator.com/translate"
# regiunile resursei Translator: codul (antetul Ocp-Apim-Subscription-Region; "" = Global, fara antet) si numele din
# portal. Cele scrise in paginile Translator (Global, Europa) si germanywestcentral (o resursa Translator reala acolo).
REGIUNI_AZURE = (("", "Global"), ("westeurope", "West Europe"), ("northeurope", "North Europe"),
	("germanywestcentral", "Germany West Central"), ("francecentral", "France Central"), ("swedencentral", "Sweden Central"),
	("uksouth", "UK South"), ("switzerlandnorth", "Switzerland North"), ("switzerlandwest", "Switzerland West"))
TERMEN_REGIUNE_S = 4.0        # o cerere de proba cu alta regiune (Azure, 401 la proba)
GOOGLE_ADRESA = "https://translation.googleapis.com/language/translate/v2"
DEEPL_FREE = "https://api-free.deepl.com/v2/translate"
DEEPL_PRO = "https://api.deepl.com/v2/translate"
GEMINI_ADRESA = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"

# felurile erorilor (contorul, mesajele); E_ADRESA = adresa refuzata la conectare (receptorul insusi, sau http spre
# internet), vezi verificaConexiunea
E_CHEIE, E_COTA, E_RETEA, E_TERMEN, E_RASPUNS, E_LIMBA, E_LIPSA, E_ADRESA = (
	"cheie", "cota", "retea", "termen", "raspuns", "limba", "lipsa", "adresa")
FELURI_EROARE = (E_CHEIE, E_COTA, E_RETEA, E_TERMEN, E_RASPUNS, E_LIMBA, E_LIPSA, E_ADRESA)
# erorile dupa care cererea trece singura la urmatorul serviciu din lant (cel cazut asteapta, vezi durataBlocarii);
# si raspunsul cu cod 5xx (trecatoare())
FELURI_TRECERE = (E_CHEIE, E_COTA, E_TERMEN, E_RETEA, E_LIPSA, E_LIMBA, E_ADRESA)


def _jurnal(text):
	print("[HdsTraducereSubtitrari] %s" % text)


def N_(text):
	"""marcaj pentru xgettext (--keyword=N_), fara efect; textul se traduce la folosire cu _()"""
	return text


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


# eticheta scurta a fiecarui serviciu, aceeasi pe televizor si in paginile web (etichetaServiciu); "" = fara eticheta
_ETICHETA_CASA = N_("Fără limită, mai lent pe calculatoarele obișnuite")
ETICHETE = {
	"azure": N_("Recomandat pentru subtitrări zilnice"),
	"gemini": N_("Cel mai simplu de pornit, fără card; se poate opri dacă te uiți mult"),
	"libre": _ETICHETA_CASA,
	"openai": _ETICHETA_CASA,
	"deepl": u"",
	"groq": N_("Gratuit și rapid; limită pe zi, ajunge pentru câteva filme"),
	"cloudflare": N_("Gratuit; ajunge pentru câteva filme pe zi"),
	"google": u"",
	"propriu": u"",
}


# ------------------------------------------------------------------ limbile

# limbile tinta: codul ISO 639-1 si numele englezesc (msgid deja tradus in po pentru limbile meniului; celelalte sunt
# texte noi); numele englezesc merge si in cererea catre modelele de limbaj
LIMBI_TINTA = (
	("ro", N_("Romanian")), ("en", N_("English")), ("de", N_("German")), ("fr", N_("French")),
	("it", N_("Italian")), ("es", N_("Spanish")), ("pt", N_("Portuguese")), ("hu", N_("Hungarian")),
	("cs", N_("Czech")), ("pl", N_("Polish")), ("nl", N_("Dutch")), ("ru", N_("Russian")), ("tr", N_("Turkish")),
	("bg", N_("Bulgarian")), ("sr", N_("Serbian")), ("hr", N_("Croatian")), ("sl", N_("Slovenian")),
	("sk", N_("Slovakian")), ("uk", N_("Ukrainian")), ("el", N_("Greek")), ("sq", N_("Albanian")),
	("mk", N_("Macedonian")), ("sv", N_("Swedish")), ("no", N_("Norwegian")), ("da", N_("Danish")),
	("fi", N_("Finnish")), ("et", N_("Estonian")), ("lv", N_("Latvian")), ("lt", N_("Lithuanian")),
	("is", N_("Icelandic")), ("ca", N_("Catalan")), ("ar", N_("Arabic")), ("he", N_("Hebrew")),
	("fa", N_("Persian")), ("hi", N_("Hindi")), ("zh", N_("Chinese")), ("ja", N_("Japanese")),
	("ko", N_("Korean")), ("vi", N_("Vietnamese")), ("id", N_("Indonesian")), ("th", N_("Thai")),
)
NUME_ENGLEZ = dict(LIMBI_TINTA)

# codurile de 3 litere ale pistelor (ISO 639-2 T si B) -> 639-1
_DIN_TREI = {
	"ron": "ro", "rum": "ro", "mol": "ro", "eng": "en", "deu": "de", "ger": "de", "fra": "fr", "fre": "fr",
	"ita": "it", "spa": "es", "por": "pt", "hun": "hu", "ces": "cs", "cze": "cs", "pol": "pl", "nld": "nl",
	"dut": "nl", "rus": "ru", "tur": "tr", "bul": "bg", "srp": "sr", "scc": "sr", "hrv": "hr", "scr": "hr",
	"slv": "sl", "slk": "sk", "slo": "sk", "ukr": "uk", "ell": "el", "gre": "el", "sqi": "sq", "alb": "sq",
	"mkd": "mk", "mac": "mk", "swe": "sv", "nor": "no", "nob": "no", "nno": "no", "dan": "da", "fin": "fi",
	"est": "et", "lav": "lv", "lit": "lt", "isl": "is", "ice": "is", "cat": "ca", "ara": "ar", "heb": "he",
	"fas": "fa", "per": "fa", "hin": "hi", "zho": "zh", "chi": "zh", "jpn": "ja", "kor": "ko", "vie": "vi",
	"ind": "id", "tha": "th",
}


def cod2(limba):
	"""ISO 639-1 dintr-un cod de 2 sau 3 litere sau „ro_RO”; "" daca nu se stie"""
	if not limba:
		return ""
	l = str(limba).strip().lower().replace("-", "_").split("_")[0]
	if len(l) == 2:
		return l if l.isalpha() else ""
	return _DIN_TREI.get(l[:3], "")


def limbaMeniului():
	try:
		from Components.config import config
		return cod2(config.osd.language.value) or "en"
	except Exception:
		return "en"


def numeLimba(cod):
	"""numele limbii, tradus („Germană”)"""
	n = NUME_ENGLEZ.get(cod)
	return _t(n) if n else cod


# codurile cerute de fiecare serviciu, unde difera de ISO 639-1
_COD_AZURE = {"zh": "zh-Hans", "no": "nb", "sr": "sr-Latn"}
_COD_GOOGLE = {"zh": "zh-CN"}
_COD_DEEPL_TINTA = {"en": "EN-GB", "pt": "PT-PT", "zh": "ZH-HANS", "no": "NB"}
_COD_DEEPL_SURSA = {"no": "NB"}
_COD_LIBRE = {"no": "nb", "zh": "zh-Hans"}


# ------------------------------------------------------------------ setarile

def initConfig():
	"""config.hds_traducere (facut o singura data)"""
	from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigSelection, ConfigText
	try:
		s = config.hds_traducere
		if hasattr(s, "pornit"):
			return s
	except (KeyError, AttributeError):
		pass
	config.hds_traducere = ConfigSubsection()
	s = config.hds_traducere
	s.pornit = ConfigYesNo(default=False)
	s.serviciu = ConfigSelection(default=SERVICIU_IMPLICIT, choices=[(c, numeServiciu(c, traducere=False)) for c in SERVICII])
	# scris si cand e egal cu valoarea din fabrica (care s-a schimbat la 0.1.9): orice save() pune randul
	s.serviciu.save_forced = True
	s.limba = ConfigSelection(default="meniu", choices=[("meniu", _t(N_("Limba meniului")))] +
		[(c, _t(n)) for c, n in LIMBI_TINTA])
	s.afisare = ConfigSelection(default="inlocuieste", choices=[("inlocuieste", _t(N_("În locul originalului"))),
		("sub", _t(N_("Sub original")))])
	s.tarziu = ConfigSelection(default="inlocuieste", choices=[("inlocuieste", _t(N_("Se pune când vine"))),
		("sare", _t(N_("Rămâne originalul")))])
	# „Timpul de citire”: cat sta cel putin o subtitrare tradusa, dupa lungimea ei (TIMP_CITIRE, nucleul: setReadingTime)
	s.citire = ConfigSelection(default="normal", choices=[("normal", _t(N_("Obișnuit"))), ("lung", _t(N_("Mai lung"))),
		("foarte_lung", _t(N_("Cel mai lung")))])
	s.dvb = ConfigYesNo(default=True)
	s.regiune = ConfigText(default="", fixed_size=False)
	s.adresa_libre = ConfigText(default="", fixed_size=False)
	s.adresa_openai = ConfigText(default="", fixed_size=False)
	s.model_gemini = ConfigText(default=MODEL_GEMINI_IMPLICIT, fixed_size=False)
	s.model_openai = ConfigText(default="", fixed_size=False)
	# Groq si Cloudflare Workers: modelul (urmeaza valoarea din fabrica, ca la Gemini) si ID-ul contului Cloudflare
	s.model_groq = ConfigText(default=MODEL_GROQ_IMPLICIT, fixed_size=False)
	s.model_cloudflare = ConfigText(default=MODEL_CLOUDFLARE_IMPLICIT, fixed_size=False)
	s.cont_cloudflare = ConfigText(default="", fixed_size=False)
	# adresa proprie (propriu); valoarea antetului e cheia serviciului propriu din fisierul criptat
	s.propriu_adresa = ConfigText(default="", fixed_size=False)
	s.propriu_metoda = ConfigSelection(default="GET", choices=[("GET", "GET"), ("POST", "POST")])
	s.propriu_corp = ConfigText(default="", fixed_size=False)
	s.propriu_tip_corp = ConfigSelection(default="json", choices=[("json", "JSON"), ("formular", _t(N_("Formular")))])
	s.propriu_antet = ConfigText(default="", fixed_size=False)
	s.propriu_raspuns = ConfigSelection(default="json", choices=[("json", "JSON"), ("text", _t(N_("Text simplu")))])
	s.propriu_cale = ConfigText(default="", fixed_size=False)
	# serviciile de rezerva, in ordine: codurile despartite prin virgula, fara cel principal (rezerve(), puneRezerve())
	s.rezerve = ConfigText(default=REZERVE_IMPLICITE, fixed_size=False)
	s.rezerve.save_forced = True
	# „Tradu EPG”: titlurile si descrierile emisiunilor de pe ecran, prin aceleasi servicii (Components/HdsTraducereEpg.py)
	s.epg = ConfigYesNo(default=False)
	# „Tradu bara de jos”: numai titlurile emisiunii de acum si urmatoare de pe bara de jos (aceeasi cale ca „Tradu
	# EPG”, putina cota); lucreaza numai cu traducerea pornita, deci din fabrica Da (fara traducere nu pleaca nimic)
	s.bara = ConfigYesNo(default=True)
	# "Tradu teletextul" si "Tradu HbbTV" (Components/HdsTraducereTexte.py), oprite din fabrica: consuma din cota.
	# teletext_mod: randurile traduse chiar in pagina sau pagina originala cu traducerea intr-un panou
	s.teletext = ConfigYesNo(default=False)
	s.teletext_mod = ConfigSelection(default="pagina", choices=[("pagina", _t(N_("În pagină"))),
		("panou", _t(N_("Într-un panou")))])
	s.hbbtv = ConfigYesNo(default=False)
	# numele din alegerea Serviciul cu unde lucreaza fiecare (puse din nou la schimbarea adreselor si la ecran)
	puneEticheteleServiciilor(s)
	if s.serviciu.saved_value is None:
		mutaServiciulVechi(s)
	return s


SERVICIU_VECHI = "gemini"     # serviciul din fabrica pana la 0.1.8 (nescris in settings cand omul nu l-a schimbat)
# primul build in care SERVICIU_IMPLICIT (azure) e cel din fabrica: cine a vazut „Ce e nou” de la el incolo si n-are
# randul serviciului in settings a ales azure sau l-a lasat asa (valoarea egala cu cea din fabrica nu se scrie)
BUILD_AZURE_DIN_FABRICA = "0019"
_vazuta_la_pornire = []        # build-ul „Ce e nou” vazut, citit o data (inainte ca ecranul lui sa-l schimbe)


def _vazutaLaPornire():
	if not _vazuta_la_pornire:
		try:
			from Components import HdsJurnalVersiuni
			_vazuta_la_pornire.append(HdsJurnalVersiuni.ultima_vazuta() or "")
		except Exception:
			_vazuta_la_pornire.append("")
	return _vazuta_la_pornire[0]


def _vazutaDeLaAzure(vazuta):
	"""True cand build-ul vazut e al unei versiuni de la BUILD_AZURE_DIN_FABRICA incolo. Un build de 19 cifre (o parte
	a versiunii are doua cifre, 0.3.10: felul, apoi fiecare parte pe cate doua cifre) se compara dupa felul si
	versiune, nu ca sir (inceputul lui, 0000, ar parea mai mic decat 0019)."""
	if len(vazuta) == 19 and vazuta.isdigit() and vazuta.isascii():
		parti = (int(vazuta[0]), int(vazuta[1:3]), int(vazuta[3:5]), int(vazuta[5:7]))
		return parti >= tuple(int(c) for c in BUILD_AZURE_DIN_FABRICA)
	return vazuta[:len(BUILD_AZURE_DIN_FABRICA)] >= BUILD_AZURE_DIN_FABRICA


def mutaServiciulVechi(s, cheile=None, vazuta=None):
	"""Settings fara randul serviciului = omul nu l-a ales niciodata, deci pana la 0.1.8 folosea SERVICIU_VECHI (cel
	din fabrica de atunci, care nu se scria). Cu cheia lui salvata si fara cheia serviciului din fabrica de acum,
	serviciul ramane cel vechi (scris explicit), ca actualizarea sa nu opreasca traducerea. -> True daca l-a mutat.
	Numai pentru setarile venite de la 0.1.8 sau mai vechi: cine a vazut „Ce e nou” al unei versiuni de la
	BUILD_AZURE_DIN_FABRICA incolo (vazuta, implicit cea tinuta minte la prima chemare) are azure ales sau lasat, iar
	alegerea lui nu se schimba (fara cheia azure lucreaza prima rezerva completa, la fel ca inainte).
	Fara configfile.save(): randul ajunge in settings la urmatoarea salvare; pana atunci mutarea se repeta la pornire,
	cu acelasi rezultat."""
	try:
		vazuta = _vazutaLaPornire() if vazuta is None else (vazuta or "")
		if _vazutaDeLaAzure(vazuta):
			return False
		cheile = cheile if cheile is not None else chei().citeste()
		if s.serviciu.value != SERVICIU_IMPLICIT or not cheile.get(SERVICIU_VECHI) or cheile.get(SERVICIU_IMPLICIT):
			return False
		s.serviciu.value = SERVICIU_VECHI
		s.serviciu.save()
		_jurnal("serviciul ramane %s (ales in fabrica la versiunea veche, are cheia)" % SERVICIU_VECHI)
		return True
	except Exception as e:
		_jurnal("serviciul vechi: %s" % e.__class__.__name__)
		return False


def rezerveValide(valoare, principal):
	"""lista serviciilor de rezerva (text cu virgule sau lista de coduri) -> (lista, eroare, codul rau); eroare "" daca
	e buna, altfel "necunoscut", "dublura" sau "principal" (serviciul principal nu intra in lista)"""
	if isinstance(valoare, (list, tuple)):
		bucati = [str(v) for v in valoare]
	else:
		bucati = str(valoare or u"").split(u",")
	lista = []
	for b in bucati:
		c = b.strip()
		if not c:
			continue
		if c not in SERVICII:
			return [], "necunoscut", c
		if c in lista:
			return [], "dublura", c
		if c == principal:
			return [], "principal", c
		lista.append(c)
	return lista, "", u""


def rezerve(s=None):
	"""serviciile de rezerva din setari, curate: numai coduri cunoscute, fara cel principal, fara dubluri, in ordine"""
	s = s or initConfig()
	principal = s.serviciu.value
	lista = []
	for b in (s.rezerve.value or u"").split(u","):
		c = b.strip()
		if c in SERVICII and c != principal and c not in lista:
			lista.append(c)
	return lista


def puneRezerve(valoare, s=None):
	"""scrie lista serviciilor de rezerva, verificata (nu salveaza fisierul setarilor) -> (True/False, mesaj)"""
	s = s or initConfig()
	lista, eroare, rau = rezerveValide(valoare, s.serviciu.value)
	if eroare:
		return False, _t("Lista serviciilor de rezervă nu e bună (un serviciu necunoscut, unul de două ori sau chiar cel "
			"principal). Nu s-a schimbat nimic.")
	s.rezerve.value = u",".join(lista)
	return True, u""


def serviciiGata(s=None, cheile=None, legaturi=None):
	"""serviciile, afara de cel principal, cu campurile complete (ceLipseste gol: cheia pusa la cele care cer cheie,
	adresa la serverele din casa), in ordinea din SERVICII: cele care pot deveni principale („Fă-l principal”)"""
	s = s or initConfig()
	cheile = cheile if cheile is not None else chei().citeste()
	legaturi = legaturi if legaturi is not None else chei().legaturi()
	return [c for c in SERVICII if c != s.serviciu.value and
		not ceLipseste(configuratia(s, cheile, serviciu=c, legaturi=legaturi))]


def punePrincipal(serviciu, s=None):
	"""„Fă-l principal”: `serviciu` devine serviciul principal si iese din rezerve, iar fostul principal intra primul
	in rezerve; numai un serviciu cu campurile complete. Nu salveaza fisierul setarilor (ca puneRezerve).
	-> (True/False, mesajul pentru om)"""
	s = s or initConfig()
	if serviciu not in SERVICII:
		return False, _t("Serviciu necunoscut.") + u" " + _t("Nu s-a schimbat nimic.")
	vechi = s.serviciu.value
	if serviciu == vechi:
		return True, _t("%s e deja serviciul principal.") % numeServiciu(serviciu)
	lipsa = textCeLipseste(configuratia(s, serviciu=serviciu))
	if lipsa:
		return False, lipsa + u" " + _t("Nu s-a schimbat nimic.")
	# lista de acum (fara principal) se ia inainte de schimbare: rezerve() scoate serviciul principal
	lista = [vechi] + [c for c in rezerve(s) if c != serviciu]
	s.serviciu.value = serviciu
	s.rezerve.value = u",".join(lista)
	_jurnal("serviciul principal: %s (inainte %s)" % (serviciu, vechi))
	return True, _t("%s e acum serviciul principal; %s e primul la rezerve.") % (numeServiciu(serviciu),
		numeServiciu(vechi))


def numeServiciu(serviciu, traducere=True):
	nume = {
		"azure": "Azure Translator",
		"google": "Google Cloud Translation",
		"deepl": "DeepL API",
		"libre": "LibreTranslate",
		"gemini": "Gemini",
		"groq": "Groq",
		"cloudflare": "Cloudflare Workers",
		"openai": N_("Server compatibil OpenAI (de ex. Ollama)"),
		"propriu": N_("Adresă proprie"),
	}.get(serviciu, serviciu)
	return _t(nume) if traducere and serviciu in ("openai", "propriu") else nume


# UNDE LUCREAZA fiecare serviciu, in paranteza dupa nume in toate listele (televizor, web, configurarea pas cu pas):
# Azure, Gemini, DeepL, Google Cloud mereu pe internet; LibreTranslate, compatibil OpenAI si adresa proprie dupa
# adresa pusa: in reteaua de acasa (aceeasi regula ca la http://, adresaInCasa; si adresa receptorului insusi) =
# local, altfel pe internet; fara adresa inca, amandoua
LOC_INTERNET, LOC_CASA, LOC_NESTIUT = "internet", "local", ""
ETICHETE_LOC = {LOC_INTERNET: N_("pe internet"), LOC_CASA: N_("local"), LOC_NESTIUT: N_("local sau pe internet")}


def locServiciu(serviciu, s=None, adresa=None):
	"""LOC_INTERNET, LOC_CASA sau LOC_NESTIUT (serviciu cu adresa, fara adresa sau cu una care nu se poate citi)"""
	if serviciu not in CU_ADRESA:
		return LOC_INTERNET
	if adresa is None:
		adresa = adresaServiciului(serviciu, s)
	clasa = clasaAdresa(adresa) if adresa else None
	if clasa is None:
		return LOC_NESTIUT
	return LOC_INTERNET if clasa == INTERNET else LOC_CASA


def etichetaLoc(serviciu, s=None, adresa=None):
	"""eticheta tradusa: pe internet, local, sau local sau pe internet (fara adresa)"""
	return _t(ETICHETE_LOC[locServiciu(serviciu, s, adresa)])


def numeCuLoc(serviciu, s=None, adresa=None, scurt=False):
	"""numele serviciului (tradus) cu unde lucreaza, in paranteza, de exemplu LibreTranslate (local); scurt = fara
	partea (de ex. Ollama) din numele serverului compatibil OpenAI"""
	nume = numeServiciu(serviciu)
	if scurt:
		nume = nume.split(u" (")[0]
	return u"%s (%s)" % (nume, etichetaLoc(serviciu, s, adresa))


def puneEticheteleServiciilor(s=None):
	"""alegerea Serviciul (ConfigSelection, televizor) cu unde lucreaza fiecare, dupa adresele de acum; valoarea si
	randul din settings raman (fara changed(), deci fara notificari). -> True daca s-a schimbat ceva"""
	try:
		s = s or initConfig()
		el = s.serviciu
		nume = [(c, numeCuLoc(c, s)) for c in SERVICII]
		if all(el.description[c] == n for c, n in nume):
			return False
		el.setChoices(nume, default=SERVICIU_IMPLICIT)
		el._descr = None			# textul valorii de acum se ia din nou din alegeri
		return True
	except Exception as e:
		_jurnal("etichetele serviciilor: %s" % e.__class__.__name__)
		return False


def etichetaServiciu(serviciu):
	"""eticheta scurta a serviciului, tradusa („Recomandat pentru subtitrări zilnice”), sau "" """
	e = ETICHETE.get(serviciu)
	return _t(e) if e else u""


def textNetradus():
	"""semnul mic pus de nucleu in fata unei subtitrari care nu s-a putut traduce (setTranslationMark)"""
	return _t(N_("(netradus)"))


def timpCitire(s=None):
	"""(baza ms, ms pe semn, cel putin ms, cel mult ms) pentru setarea „Timpul de citire” (nucleul: setReadingTime)"""
	try:
		s = s or initConfig()
		return TIMP_CITIRE.get(s.citire.value, TIMP_CITIRE["normal"])
	except Exception:
		return TIMP_CITIRE["normal"]


def limbaTinta(s=None):
	s = s or initConfig()
	v = s.limba.value
	return limbaMeniului() if v == "meniu" else v


def lantul(s=None, cheile=None, legaturi=None):
	"""configuratiile serviciilor in ordinea incercarii: cel principal, apoi rezervele (si cele cu campuri lipsa: cine
	foloseste lantul le sare)"""
	s = s or initConfig()
	cheile = cheile if cheile is not None else chei().citeste()
	legaturi = legaturi if legaturi is not None else chei().legaturi()
	return [configuratia(s, cheile, legaturi=legaturi)] + [configuratia(s, cheile, serviciu=c, legaturi=legaturi)
		for c in rezerve(s)]


def adresaServiciului(serviciu, s=None):
	"""adresa din setari a unui serviciu cu adresa (CU_ADRESA), sau "" """
	s = s or initConfig()
	try:
		v = {"libre": s.adresa_libre, "openai": s.adresa_openai, "propriu": s.propriu_adresa}[serviciu].value
	except (KeyError, AttributeError):
		return u""
	return (v or u"").strip()


def _valoareSetare(s, camp, implicit=u""):
	"""valoarea unei setari care poate lipsi (ConfigSubsection da KeyError, nu AttributeError)"""
	try:
		return getattr(s, camp).value
	except (KeyError, AttributeError):
		return implicit


def contCloudflareBun(cont):
	"""ID-ul contului Cloudflare: 32 de semne hex (din panou, la Account ID)"""
	return bool(_CONT_CLOUDFLARE.match((cont or u"").strip().lower()))


def configuratia(s=None, cheile=None, serviciu=None, legaturi=None):
	"""tot ce trebuie unei cereri (fara referinte la config): serviciu, cheie, regiune, adresa, model, tinta; pentru
	serviciul ales sau pentru `serviciu` (o rezerva), cu campurile lui. La serviciile cu adresa (CU_ADRESA) cheia intra
	numai daca e legata de gazda adresei de acum (cheiePentru); altfel cheie_oprita spune de ce ("alta", "http")."""
	s = s or initConfig()
	serv = serviciu or s.serviciu.value
	cheile = cheile if cheile is not None else chei().citeste()
	legaturi = legaturi if legaturi is not None else chei().legaturi()
	adresa = adresaServiciului(serv, s) if serv in CU_ADRESA else u""
	model = {"gemini": s.model_gemini.value, "openai": s.model_openai.value, "groq": _valoareSetare(s, "model_groq"),
		"cloudflare": _valoareSetare(s, "model_cloudflare")}.get(serv, "")
	cheie, oprita = cheiePentru(serv, adresa, cheile, legaturi)
	cfg = {
		"serviciu": serv,
		"cheie": cheie,
		"cheie_oprita": oprita,
		"regiune": (s.regiune.value or "").strip() if serv == "azure" else "",
		"adresa": adresa,
		"model": (model or "").strip(),
		"tinta": limbaTinta(s),
	}
	if serv == "cloudflare":
		cfg["cont"] = (_valoareSetare(s, "cont_cloudflare") or u"").strip().lower()
	if serv == "propriu":
		cfg.update({
			"metoda": s.propriu_metoda.value,
			"corp": curataCorp(s.propriu_corp.value),
			"tip_corp": s.propriu_tip_corp.value,
			"antet": (s.propriu_antet.value or "").strip(),
			"raspuns": s.propriu_raspuns.value,
			"cale": (s.propriu_cale.value or "").strip(),
		})
	return cfg


def ceLipseste(cfg=None):
	"""campurile obligatorii goale ale serviciului ales: lista din cheie/adresa/model (si adresa gresita); la propriu
	si propriu_text (lipseste {text}), propriu_http (http in afara casei), propriu_corp, propriu_antet, cale"""
	cfg = cfg or configuratia()
	lipsa = []
	for camp in CERE.get(cfg["serviciu"], ()):
		if not cfg.get(camp):
			lipsa.append(camp)
	if cfg["serviciu"] == "propriu":
		return lipsa + motivePropriu(cfg)
	if cfg["serviciu"] == "cloudflare" and cfg.get("cont") and not contCloudflareBun(cfg["cont"]):
		lipsa.append("cont_gresit")
	if cfg.get("adresa") and "adresa" in CERE.get(cfg["serviciu"], ()):
		if not adresaBuna(cfg["adresa"]):
			lipsa.append("adresa_gresita")
		elif clasaAdresa(cfg["adresa"]) == RECEPTOR:
			lipsa.append("adresa_receptor")
	return lipsa


def adresaBuna(adresa):
	try:
		p = urlsplit(adresa)
		return p.scheme in ("http", "https") and bool(p.hostname) and not p.username and not p.password
	except Exception:
		return False


# ------------------------------------------------------------------ adresele: reteaua de acasa si receptorul insusi
#
# Serverul de traducere nu poate fi chiar receptorul: pe adresele lui (127.0.0.0/8, ::1, 0.0.0.0, IP-urile placilor de
# retea, numele care duc la ele) asculta alte servicii (8001, modulul de acces, interfata web), iar raspunsul unei
# cereri ajunge in proba si in mesajele din web. La fel adresele de legatura (169.254.0.0/16, fe80::/10) si cele de
# grup.
# Doua verificari:
#   la salvare (clasaAdresa, fara DNS): IP-urile scrise in orice forma primita de inet_aton din glibc (zecimal 2130706433,
#     octal 0177.1, hexazecimal 0x7f000001, 127.1), IPv6 (si IPv4 mapat ::ffff:127.0.0.1), numele receptorului;
#   la conectare (verificaConexiunea, pe socketul tocmai legat, inainte sa plece vreun octet al cererii): adresa reala
#     a celuilalt capat, dupa DNS, deci si un nume care se rezolva in receptor; plus http:// (necriptat) numai spre
#     reteaua de acasa (10/8, 172.16/12, 192.168/16, fc00::/7; 100.64/10 e internet, ca la CGNAT).
# Redirectionarile nu se urmeaza (_FaraRedirectionari), iar proxy-urile din mediu nu se folosesc (ProxyHandler gol).

RECEPTOR, CASA, INTERNET = "receptor", "casa", "internet"
_SUFIXE_CASA = (".local", ".lan", ".home", ".internal", ".home.arpa")
_NUME_RECEPTOR = frozenset(("localhost", "localhost.localdomain", "localhost6", "localhost6.localdomain6",
	"ip6-localhost", "ip6-loopback"))
_NUMAR_IPV4 = re.compile(r"^(0x[0-9a-f]*|[0-9]+)(\.(0x[0-9a-f]*|[0-9]+)){0,3}$")
_LIMITE_IPV4 = {1: (0xffffffff,), 2: (0xff, 0xffffff), 3: (0xff, 0xff, 0xffff), 4: (0xff, 0xff, 0xff, 0xff)}
PROPRII_S = 30.0              # adresele receptorului se recitesc dupa atat (se schimba, de exemplu DHCP dupa flash)
_PROPRII = [None, 0.0]
# perechi (ip, port) primite chiar daca sunt ale receptorului; goala in imagine (o folosesc probele de pe PC, cu
# serverele false ascultand pe 127.0.0.1)
PERMISE_PROBE = set()


def _ipv4Numeric(text):
	"""un IPv4 scris ca la inet_aton din glibc: 1-4 parti, fiecare zecimala, octala (0 in fata) sau hexazecimala (0x),
	ultima umple octetii ramasi -> 4 octeti, sau None"""
	if not _NUMAR_IPV4.match(text):
		return None
	parti = []
	for p in text.split("."):
		try:
			if p.startswith("0x"):
				parti.append(int(p[2:] or "0", 16))
			elif len(p) > 1 and p.startswith("0"):
				parti.append(int(p, 8))
			else:
				parti.append(int(p))
		except ValueError:
			return None
	if any(v > l for v, l in zip(parti, _LIMITE_IPV4[len(parti)])):
		return None
	valoare = parti[-1]
	for i, v in enumerate(parti[:-1]):
		valoare |= v << (8 * (3 - i))
	return bytes(bytearray(((valoare >> 24) & 255, (valoare >> 16) & 255, (valoare >> 8) & 255, valoare & 255)))


def octetiIp(gazda):
	"""IP-ul dintr-o gazda (fara paranteze; zona %eth0 scoasa) -> 4 sau 16 octeti (IPv4 mapat pe IPv6 -> cei 4
	octeti IPv4), sau None pentru un nume"""
	g = (gazda or "").strip().lower().rstrip(".")
	if g.startswith("[") and g.endswith("]"):
		g = g[1:-1]
	if ":" in g:
		try:
			b = socket.inet_pton(socket.AF_INET6, g.split("%", 1)[0])
		except (socket.error, ValueError, OSError):
			return None
		if b[:12] == b"\0" * 10 + b"\xff\xff":
			return b[12:]
		return b
	return _ipv4Numeric(g)


def textIp(octeti):
	try:
		return socket.inet_ntop(socket.AF_INET if len(octeti) == 4 else socket.AF_INET6, octeti)
	except (socket.error, ValueError, OSError):
		return u""


def _citesteProprii(fib, inet6):
	"""fisierele din /proc sunt ASCII; pe Python 2.7 (probele vechi) open nu are encoding=: TypeError = multimea goala"""
	gasite = set()
	try:
		with open(fib, "r", encoding="ascii", errors="replace") as f:
			ultim = None
			for rand in f:
				r = rand.strip()
				if r.startswith("|-- "):
					ultim = r[4:].strip()
				elif ultim and r.startswith("/32 host LOCAL"):
					b = _ipv4Numeric(ultim)
					if b:
						gasite.add(b)
	except (IOError, OSError, TypeError):
		pass
	try:
		with open(inet6, "r", encoding="ascii", errors="replace") as f:
			for rand in f:
				h = (rand.split() or [""])[0]
				if len(h) == 32:
					try:
						gasite.add(bytes(bytearray.fromhex(h)))
					except ValueError:
						pass
	except (IOError, OSError, TypeError):
		pass
	return gasite


def ipuriProprii(fib="/proc/net/fib_trie", inet6="/proc/net/if_inet6"):
	"""adresele receptorului (octeti): tabela locala a nucleului (/proc/net/fib_trie, „/32 host LOCAL”) si
	/proc/net/if_inet6; tinute PROPRII_S. Fara aceste fisiere (alt sistem): multimea goala."""
	if fib != "/proc/net/fib_trie" or inet6 != "/proc/net/if_inet6":
		return _citesteProprii(fib, inet6)
	acum = time.monotonic()
	multime, cand = _PROPRII
	if multime is None or not (0 <= acum - cand < PROPRII_S):
		multime = _citesteProprii(fib, inet6)
		_PROPRII[:] = [multime, acum]
	return multime


def clasaIp(octeti, proprii=None):
	"""RECEPTOR (receptorul insusi, adresele de legatura si de grup), CASA (reteaua de acasa) sau INTERNET"""
	if octeti in (ipuriProprii() if proprii is None else proprii):
		return RECEPTOR
	b = bytearray(octeti)
	if len(b) == 4:
		if b[0] in (0, 127) or b[0] >= 224 or (b[0] == 169 and b[1] == 254):
			return RECEPTOR
		# 100.64.0.0/10 nu e acasa: la CGNAT e reteaua furnizorului, deci http si o cheie ar pleca prin ea (din 0.2.1;
		# pana atunci era CASA, ca pentru retelele private virtuale); tot internet il socoteste si poarta web
		if b[0] == 10 or (b[0] == 172 and 16 <= b[1] <= 31) or (b[0] == 192 and b[1] == 168):
			return CASA
		return INTERNET
	if not any(b[:12]) or b[0] == 0xff or (b[0] == 0xfe and b[1] & 0xc0 == 0x80):
		return RECEPTOR		# ::, ::1 si ::a.b.c.d; grup; legatura
	if b[0] & 0xfe == 0xfc:
		return CASA
	return INTERNET


def numeleReceptorului():
	"""numele sub care receptorul se gaseste pe el insusi (/etc/hosts are 127.0.1.1 <hostname>)"""
	try:
		n = (socket.gethostname() or "").strip().lower().rstrip(".")
	except Exception:
		return ()
	if not n:
		return ()
	baza = n.split(".")[0]
	return tuple(set((n, baza) + tuple(baza + s for s in (".local", ".lan", ".home", ".localdomain"))))


def clasaGazda(gazda, port=None):
	"""clasa gazdei unei adrese, fara DNS: IP-ul (orice forma) dupa clasaIp; un nume al receptorului (localhost,
	*.localhost, hostname) RECEPTOR; un nume fara punct sau cu sufix de casa (.local, .lan...) CASA; altfel INTERNET"""
	b = octetiIp(gazda)
	if b is not None:
		if port is not None and (textIp(b), port) in PERMISE_PROBE:
			return CASA
		return clasaIp(b)
	g = (gazda or "").strip().lower().rstrip(".")
	if not g or ":" in g:
		return INTERNET
	if g in _NUME_RECEPTOR or g.endswith(".localhost") or g in numeleReceptorului():
		return RECEPTOR
	if "." not in g or g.endswith(_SUFIXE_CASA):
		return CASA
	return INTERNET


def gazdaSiPort(adresa):
	"""(gazda, port, schema) dintr-o adresa (portul implicit al schemei), sau None"""
	try:
		p = urlsplit((adresa or u"").strip())
		gazda, schema = p.hostname, (p.scheme or "").lower()
		port = p.port or {"http": 80, "https": 443}.get(schema)
	except (ValueError, AttributeError):
		return None
	if not gazda:
		return None
	return gazda, port, schema


def clasaAdresa(adresa):
	"""RECEPTOR, CASA sau INTERNET pentru gazda adresei (fara DNS); None daca adresa nu se poate citi"""
	g = gazdaSiPort(adresa)
	return clasaGazda(g[0], g[1]) if g else None


def origine(adresa):
	"""„schema://gazda:port” (litere mici, portul implicit scris) a unei adrese, sau "" """
	g = gazdaSiPort(adresa)
	if not g or g[2] not in ("http", "https"):
		return u""
	gazda = g[0].lower().rstrip(".")
	return u"%s://%s:%d" % (g[2], ("[%s]" % gazda) if ":" in gazda else gazda, g[1])


class AdresaOprita(OSError):
	"""conexiunea refuzata de verificaConexiunea; motiv RECEPTOR sau INTERNET (http spre internet)"""

	def __init__(self, motiv, ip=u""):
		OSError.__init__(self, motiv)
		self.motiv, self.ip = motiv, ip


def verificaConexiunea(sock, criptat):
	"""socketul tocmai legat (dupa DNS, inainte de cerere): refuzat daca celalalt capat e receptorul insusi (si cand
	adresa lui e adresa locala a socketului) sau o adresa de legatura sau de grup; fara criptare (http) si daca nu e in
	reteaua de acasa. Ridica AdresaOprita."""
	try:
		pereche, local = sock.getpeername(), sock.getsockname()
	except (socket.error, OSError):
		raise AdresaOprita(RECEPTOR)
	b = octetiIp(pereche[0])
	if b is None:
		raise AdresaOprita(RECEPTOR)
	ip = textIp(b)
	if (ip, pereche[1]) in PERMISE_PROBE:
		return
	clasa = RECEPTOR if b == octetiIp(local[0]) else clasaIp(b)
	if clasa == RECEPTOR:
		raise AdresaOprita(RECEPTOR, ip)
	if not criptat and clasa != CASA:
		raise AdresaOprita(INTERNET, ip)


def textAdresaOprita(motiv, gazda=u""):
	"""mesajul pentru om cand adresa e refuzata (la salvare sau la conectare)"""
	if motiv == INTERNET:
		return _t("Adresa %s e pe internet, iar receptorul trimite pe http:// (necriptat) numai în rețeaua de acasă. "
			"Scrie adresa cu https://.") % (gazda or u"?")
	return _t("Adresa %s duce chiar la receptor. Receptorul nu are server de traducere: scrie adresa calculatorului din "
		"casă sau a serverului din internet (127.0.0.1, localhost, 0.0.0.0, 169.254.x și IP-ul receptorului nu merg).") % (
		gazda or u"?")


_TEXT_CAMP = {
	"cheie": N_("cheia API"),
	"adresa": N_("adresa serverului"),
	"model": N_("modelul"),
	"cont": N_("ID-ul contului Cloudflare"),
	"cont_gresit": N_("un ID de cont Cloudflare bun (32 de litere și cifre, de la Account ID)"),
	"adresa_gresita": N_("o adresă bună (începe cu http:// sau https://)"),
	"adresa_receptor": N_("adresa altui aparat, nu a receptorului (127.0.0.1, localhost, 0.0.0.0, 169.254.x și IP-ul "
		"receptorului nu merg)"),
	"propriu_text": N_("locul {text} în adresă (sau, la POST, în corp)"),
	"propriu_http": N_("o adresă https:// (http:// merge numai pentru un server din rețeaua de acasă)"),
	"propriu_corp": N_("un corp JSON bun (pune locurile între ghilimele, de exemplu \"q\": \"{text}\")"),
	"propriu_antet": N_("un nume de antet bun (litere, cifre și - _ ., de exemplu Authorization)"),
	"cale": N_("calea traducerii în răspunsul JSON (chei și numere despărțite prin punct, de exemplu translatedText)"),
}


# ------------------------------------------------------------------ adresa proprie: setarile, sablonul, calea

_LOC = re.compile(r"\{(text|sursa|tinta)\}")
_NUME_ANTET = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")
# antetele puse de receptor sau de urllib: nu se pot alege
_ANTETE_OPRITE = frozenset(("host", "content-length", "content-type", "transfer-encoding", "connection"))


def curataCorp(text):
	"""corpul-sablon cum se pastreaza: fara randuri noi si tab-uri (fisierul setarilor are un rand pe setare;
	in JSON spatiile dintre elemente nu conteaza), fara spatii la capete"""
	return re.sub(r"[ \t\r\n]+", u" ", text or u"").strip()


def numeAntetBun(nume):
	"""numele antetului: numai caractere de nume de antet (RFC 9110), cel mult 64, nu unul pus de receptor"""
	return bool(nume) and bool(_NUME_ANTET.match(nume)) and nume.lower() not in _ANTETE_OPRITE


def caleBuna(cale):
	"""calea in JSON: chei si numere despartite prin punct, fara bucati goale, fara spatii si caractere de control"""
	if not cale or len(cale) > MAX_CALE:
		return False
	return all(b and not any(c.isspace() or ord(c) < 32 for c in b) for b in cale.split(u"."))


def motivAdresaPropriu(adresa):
	"""adresa-sablon: "" daca e buna, altfel codul motivului: adresa_gresita (schema, nume si parola, spatii, semne
	non-ASCII, locuri in numele gazdei), adresa_receptor (receptorul insusi, clasaAdresa) sau propriu_http (http in
	afara retelei de acasa)"""
	if not adresa or any(ord(c) <= 32 or ord(c) > 126 for c in adresa):
		return "adresa_gresita"
	try:
		p = urlsplit(adresa)
		bun = p.scheme in ("http", "https") and bool(p.hostname) and not p.username and not p.password and \
			"{" not in p.netloc and "}" not in p.netloc
		p.port		# un port gresit ridica ValueError
	except Exception:
		return "adresa_gresita"
	if not bun:
		return "adresa_gresita"
	clasa = clasaAdresa(adresa)
	if clasa == RECEPTOR:
		return "adresa_receptor"
	if p.scheme == "http" and clasa != CASA:
		return "propriu_http"
	return ""


def textMotivAdresa(motiv, adresa=u""):
	"""mesajul pentru un cod din motivAdresaPropriu / ceLipseste (adresa_receptor, propriu_http, adresa_gresita)"""
	if motiv == "adresa_receptor" and adresa:
		return textAdresaOprita(RECEPTOR, _gazda(adresa))
	if motiv in _TEXT_CAMP:
		return _t(_TEXT_CAMP[motiv])
	return u""


def corpJsonBun(corp):
	"""corpul JSON, cu locurile umplute, se poate citi ca JSON"""
	try:
		json.loads(umpleSablon(corp, u"a\"b", u"en", u"ro", "json"))
		return True
	except ValueError:
		return False


def motivePropriu(cfg):
	"""ce nu e bun in setarile adresei proprii (in afara adresei goale): lista de coduri din _TEXT_CAMP"""
	coduri = []
	adresa = cfg.get("adresa") or u""
	post = (cfg.get("metoda") or "GET") == "POST"
	corp = (cfg.get("corp") or u"") if post else u""
	if adresa:
		m = motivAdresaPropriu(adresa)
		if m:
			coduri.append(m)
		if u"{text}" not in adresa and u"{text}" not in corp:
			coduri.append("propriu_text")
	if corp and (cfg.get("tip_corp") or "json") == "json" and not corpJsonBun(corp):
		coduri.append("propriu_corp")
	if cfg.get("antet") and not numeAntetBun(cfg["antet"]):
		coduri.append("propriu_antet")
	if (cfg.get("raspuns") or "json") == "json" and not caleBuna(cfg.get("cale") or u""):
		coduri.append("cale")
	return coduri


def umpleSablon(sablon, text, sursa, tinta, fel="adresa"):
	"""locurile {text}, {sursa} („auto” cand nu se stie), {tinta} inlocuite dintr-o singura trecere (un loc scris in
	textul omului nu se mai inlocuieste). fel: adresa (codat pentru URL, fara semne lasate necodate), json (sir JSON
	scapat, fara ghilimelele de afara), formular (codat ca formular)"""
	valori = {"text": text or u"", "sursa": sursa or u"auto", "tinta": tinta or u""}
	if fel == "json":
		def cod(v):
			return json.dumps(v, ensure_ascii=False)[1:-1]
	elif fel == "formular":
		def cod(v):
			return quote_plus(v, safe="")
	else:
		def cod(v):
			return quote(v, safe="")
	return _LOC.sub(lambda m: cod(valori[m.group(1)]), sablon or u"")


_NIMIC = object()


def _dinCale(obiect, bucati, iesire):
	if not bucati:
		if isinstance(obiect, str):
			iesire.append(obiect)
		elif isinstance(obiect, (int, float)) and not isinstance(obiect, bool):
			iesire.append(str(obiect))
		return
	b, rest = bucati[0], bucati[1:]
	if b == u"*":
		copii = list(obiect.values()) if isinstance(obiect, dict) else obiect if isinstance(obiect, list) else []
		for c in copii:
			_dinCale(c, rest, iesire)
		return
	urmator = _NIMIC
	if isinstance(obiect, dict):
		urmator = obiect.get(b, _NIMIC)
	elif isinstance(obiect, list) and b.isdigit():
		i = int(b)
		if i < len(obiect):
			urmator = obiect[i]
	if urmator is not _NIMIC:
		_dinCale(urmator, rest, iesire)


def caleJson(obiect, cale):
	"""textul gasit la cale in obiectul JSON (bucatile lipite in ordine, fara separator; numerele devin text), sau
	None daca nu se gaseste niciun text. Calea: chei si indici despartiti prin punct, „*” = toate elementele unui
	tablou sau toate valorile unui obiect (de ex. translatedText, data.translations.0.translatedText, 0.*.0)"""
	if not caleBuna(cale):
		return None
	iesire = []
	_dinCale(obiect, cale.split(u"."), iesire)
	return u"".join(iesire) if iesire else None


def _ascundeCheia(text, cheie):
	"""cheia (si bucatile ei de cel putin 8 semne, de ex. cea de dupa „Bearer”; cuvantul „Bearer” ramane) inlocuita cu
	*** intr-un text de aratat"""
	if not cheie or not text:
		return text
	for bucata in sorted(set([cheie] + [b for b in cheie.split() if len(b) >= 8]), key=len, reverse=True):
		text = text.replace(bucata, u"***")
	return text


def inceputRaspuns(date, cheie=u""):
	"""primele MAX_INCEPUT semne din corpul raspunsului, pentru mesajul de pe televizor si din web (niciodata pentru
	jurnal): cheia inlocuita cu ***, caracterele de control scoase, spatiile stranse"""
	t = date.decode("utf-8", "replace") if isinstance(date, bytes) else str(date or u"")
	t = _ascundeCheia(t.lstrip(u"﻿"), cheie)
	t = u" ".join(u"".join(c if ord(c) >= 32 and not 127 <= ord(c) < 160 else u" " for c in t).split())
	return t[:MAX_INCEPUT] + (u"..." if len(t) > MAX_INCEPUT else u"")


def textCeLipseste(cfg=None):
	"""„Pentru DeepL API lipsește: cheia API.” sau "" """
	cfg = cfg or configuratia()
	lipsa = ceLipseste(cfg)
	if not lipsa:
		return u""
	return _t("Pentru %s lipsește: %s.") % (numeServiciu(cfg["serviciu"]), u", ".join(_t(_TEXT_CAMP[c]) for c in lipsa))


# ------------------------------------------------------------------ cheile (fisier separat, criptat, 0600)

def _citesteText(cale):
	try:
		with open(cale, "r", encoding="utf-8") as f:
			return f.read(512).strip()
	except (OSError, IOError, TypeError):
		return ""


_MAC_NUL = ("", "00:00:00:00:00:00")
_TIPAR_CID = re.compile(r"^[0-9a-f]{32}$")


def macAparat(retea="/sys/class/net"):
	"""adresa placii de retea prin cablu (eth0), altfel a primei placi (dupa nume) cu o adresa nenula; "" daca nu e
	niciuna. Pe Viper 4K (u57) eth0 o ia din partitia deviceinfo (addr_assign_type 0), pe care flash-ul nu o
	scrie."""
	mac = _citesteText(os.path.join(retea, "eth0", "address")).lower()
	if mac not in _MAC_NUL:
		return mac
	try:
		nume = sorted(os.listdir(retea))
	except OSError:
		return ""
	for n in nume:
		if n != "lo":
			mac = _citesteText(os.path.join(retea, n, "address")).lower()
			if mac not in _MAC_NUL:
				return mac
	return ""


def cidMemorii(mmc="/sys/bus/mmc/devices"):
	"""CID-urile memoriilor eMMC (type MMC; cardurile SD si SDIO nu intra, ca un card scos sa nu schimbe
	identitatea), sortate (ordinea numerotarii nu conteaza) si lipite cu virgula -> (text, complet). Fara magistrala
	MMC (receptor fara eMMC, PC, emulator): ("", True). complet=False cand magistrala nu se poate citi sau o memorie
	MMC are tipul sau CID-ul necitit: atunci cheile nu se scriu si fisierul nu se muta."""
	try:
		nume = sorted(os.listdir(mmc))
	except OSError as e:
		return u"", getattr(e, "errno", None) == errno.ENOENT
	cid = []
	for n in nume:
		tip = _citesteText(os.path.join(mmc, n, "type"))
		if not tip:
			return u"", False
		if tip != "MMC":
			continue
		c = _citesteText(os.path.join(mmc, n, "cid")).lower()
		if not _TIPAR_CID.match(c):
			return u"", False
		cid.append(c)
	return u",".join(sorted(cid)), True


def identitateAparat(retea="/sys/class/net", mmc="/sys/bus/mmc/devices"):
	"""identitatea plicului v2, numai din ce ramane la flash: adresa placii de retea si CID-ul memoriilor eMMC; ""
	cand nu e completa (fara adresa, sau o memorie eMMC necitita)"""
	mac = macAparat(retea)
	cid, complet = cidMemorii(mmc)
	if not mac or not complet:
		return ""
	return "v2|%s|%s" % (mac, cid)


def identitateVeche(retea="/sys/class/net", masina="/etc/machine-id"):
	"""identitatea plicului v1 (pana la 0.1.9), neschimbata: adresa placii (eth0, altfel prima placa cu adresa) si
	/etc/machine-id, pe care dbus il face din nou la prima pornire dupa flash"""
	mac = _citesteText(os.path.join(retea, "eth0", "address"))
	if not mac:
		try:
			for n in sorted(os.listdir(retea)):
				if n != "lo":
					mac = _citesteText(os.path.join(retea, n, "address"))
					if mac and mac != "00:00:00:00:00:00":
						break
		except OSError:
			mac = ""
	return "%s|%s" % (mac.lower(), _citesteText(masina))


def _identitateCompleta(identitate):
	"""v1: adresa si machine-id; v2: identitateAparat da "" cand nu e completa"""
	return bool(identitate) and all(identitate.split("|", 1)) and "|" in identitate


def _cheiCriptare(identitate, versiune=VERSIUNE_CHEI):
	eticheta = b"hds-traducere-chei-v1" if versiune == 1 else b"hds-traducere-chei-v2"
	baza = hmac.new(eticheta, identitate.encode("utf-8"), hashlib.sha256).digest()
	return (hmac.new(baza, b"criptare", hashlib.sha256).digest(), hmac.new(baza, b"verificare", hashlib.sha256).digest())


def _sir(cheie, nonce, lungime):
	iesire = bytearray()
	contor = 0
	while len(iesire) < lungime:
		iesire += hmac.new(cheie, nonce + contor.to_bytes(8, "big"), hashlib.sha256).digest()
		contor += 1
	return bytes(iesire[:lungime])


def cripteaza(date, identitate, nonce=None, versiune=VERSIUNE_CHEI):
	k_c, k_v = _cheiCriptare(identitate, versiune)
	nonce = nonce or secrets.token_bytes(16)
	text = json.dumps(date, ensure_ascii=False, sort_keys=True).encode("utf-8")
	criptat = bytes(a ^ b for a, b in zip(text, _sir(k_c, nonce, len(text))))
	semn = hmac.new(k_v, nonce + criptat, hashlib.sha256).digest()
	return json.dumps({"v": versiune, "n": base64.b64encode(nonce).decode("ascii"),
		"c": base64.b64encode(criptat).decode("ascii"), "s": base64.b64encode(semn).decode("ascii")}).encode("ascii")


def versiunePlic(octeti):
	"""versiunea plicului (din VERSIUNI_CHEI) sau None pentru un fisier care nu e plic"""
	try:
		v = json.loads(octeti.decode("ascii")).get("v")
	except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
		return None
	return v if v in VERSIUNI_CHEI and not isinstance(v, bool) else None


def decripteaza(octeti, identitate, versiune=None):
	"""octetii fisierului -> dict, sau None (stricat, schimbat, de pe alt receptor, alta versiune decat `versiune`).
	Cheia de criptare se face din `identitate` dupa versiunea scrisa in plic."""
	try:
		plic = json.loads(octeti.decode("ascii"))
		v = plic.get("v")
		if v not in VERSIUNI_CHEI or isinstance(v, bool) or (versiune is not None and v != versiune):
			return None
		nonce = base64.b64decode(plic["n"])
		criptat = base64.b64decode(plic["c"])
		semn = base64.b64decode(plic["s"])
	except (ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError):
		return None
	k_c, k_v = _cheiCriptare(identitate, v)
	if not hmac.compare_digest(semn, hmac.new(k_v, nonce + criptat, hashlib.sha256).digest()):
		return None
	text = bytes(a ^ b for a, b in zip(criptat, _sir(k_c, nonce, len(criptat))))
	try:
		date = json.loads(text.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return None
	return date if isinstance(date, dict) else None


def curataCheie(valoare, spatii=False):
	"""o cheie lipita: fara spatii, fara randuri noi, numai caractere tiparibile ASCII; "" daca nu e buna. Cu
	spatii=True (valoarea antetului adresei proprii, de ex. „Bearer abc”) spatiile din mijloc raman, cate unul."""
	if valoare is None:
		return ""
	parti = str(valoare).split()
	v = u" ".join(parti) if spatii else u"".join(parti)
	if not v or len(v) > MAX_CHEIE or any(ord(c) < 32 or ord(c) > 126 for c in v):
		return ""
	return v


# Serviciile la care adresa o alege omul: cheia lor e LEGATA de gazda pentru care a fost pusa (origine(): schema,
# gazda, portul) si pleaca numai spre ea, numai pe https sau spre un server din reteaua de acasa (cheiePentru). Legaturile
# stau in acelasi fisier criptat, sub CHEIE_LEGATURI ({serviciu: origine}; "" = cheie veche, nelegata, care nu pleaca);
# un fisier fara ele (versiunea veche) se citeste la fel, iar legaCheileVechi le pune o data, la pornire. Serviciile cu
# adresa fixa (azure, gemini, deepl, google) au gazda scrisa in cod, pe https.
CU_ADRESA = ("libre", "openai", "propriu")
CHEIE_LEGATURI = "@legaturi"


MAX_FISIER_CHEI = 64 * 1024


def _desface(date):
	"""continutul decriptat -> (chei {serviciu: cheie}, legaturi {serviciu: origine}), numai valorile bune"""
	curat = dict((k, v) for k, v in date.items() if k in SERVICII and isinstance(v, str) and
		curataCheie(v, k == "propriu"))
	leg = date.get(CHEIE_LEGATURI)
	legaturi = dict((k, v) for k, v in (leg.items() if isinstance(leg, dict) else ())
		if k in CU_ADRESA and k in curat and isinstance(v, str))
	return curat, legaturi


class Chei(object):
	"""cheile serviciilor; `cale`, `identitate` (plicul v2) si `identitate_veche` (plicul v1; implicit aceeasi cu
	`identitate` cand ea e data) se pot schimba (probele)"""

	def __init__(self, cale=CALE_CHEI, identitate=None, identitate_veche=None):
		self.cale = cale
		self._identitate = identitate
		self._identitateVeche = identitate_veche
		self._aflata = None	# identitatea v2 citita o data (adresa si CID-ul nu se schimba cat merge receptorul)
		self._spus = None
		self._memorie = None	# (semnul fisierului, chei, legaturi): citirea nu se reface la fiecare pagina

	def identitate(self):
		"""identitatea plicului v2; "" cand nu se poate citi complet (atunci nu se scrie nimic)"""
		if self._identitate is not None:
			return self._identitate
		if self._aflata is None:
			ident = identitateAparat()
			if not ident:
				return ""
			self._aflata = ident
		return self._aflata

	def identitateVeche(self):
		"""identitatea plicului v1 (adresa | machine-id), numai pentru citirea si recriptarea fisierelor vechi"""
		if self._identitateVeche is not None:
			return self._identitateVeche
		if self._identitate is not None:
			return self._identitate
		return identitateVeche()

	def _decripteaza(self, octeti):
		"""-> (continutul sau None, versiunea plicului sau None, identitatea versiunii lui completa). Un fisier care nu
		e plic nu se poate citi cu nicio identitate (completa=True)."""
		v = versiunePlic(octeti)
		if v is None:
			return None, None, True
		ident = self.identitateVeche() if v == 1 else self.identitate()
		if not _identitateCompleta(ident):
			return None, v, False
		return decripteaza(octeti, ident, v), v, True

	@staticmethod
	def _octeti(cale):
		"""octetii unui fisier de chei; b"" pentru unul prea mare (nu e plic); None daca lipseste sau nu se poate
		citi"""
		try:
			if os.stat(cale).st_size > MAX_FISIER_CHEI:
				return b""
			with open(cale, "rb") as f:
				return f.read()
		except (OSError, IOError):
			return None

	def _citesteTot(self):
		"""-> (chei {serviciu: cheie}, legaturi {serviciu: origine}); ({}, {}) daca fisierul lipseste sau nu se poate
		citi (spus o singura data in jurnal)"""
		try:
			st = os.stat(self.cale)
		except OSError:
			self._memorie = None
			return {}, {}
		semn = (st.st_size, int(st.st_mtime * 1000), st.st_ino)
		if self._memorie is not None and self._memorie[0] == semn:
			return dict(self._memorie[1]), dict(self._memorie[2])
		octeti = self._octeti(self.cale)
		if octeti is None:
			return {}, {}
		date, v, complet = self._decripteaza(octeti)
		if date is None:
			if self._spus != semn:
				self._spus = semn
				_jurnal("cheile nu se pot citi (%s)" % ("identitatea receptorului nu se poate citi acum" if not complet
					else "fisier schimbat, de pe alt receptor sau dinaintea unui flash"))
			return {}, {}
		curat, legaturi = _desface(date)
		self._memorie = (semn, curat, legaturi)
		return dict(curat), dict(legaturi)

	def verificaLaPornire(self):
		"""o data, la pornire (legaNucleul), inaintea legarii cheilor vechi -> ce s-a facut:
		  ""          nimic de facut (fisierul lipseste sau e deja plic v2 citit);
		  "recriptat" plicul v1 se citeste cu identitatea veche (actualizare fara flash, sau machine-id pus la loc):
		              scris din nou v2, cu aceleasi chei si legaturi;
		  "refacut"   cheile lipsesc, dar <cale>.vechi se citeste acum (de ex. machine-id pus la loc dupa ce fisierul a
		              fost pus deoparte): scris v2, iar .vechi sters de scriere;
		  "deoparte"  fisierul nu se poate citi cu nicio identitate (de pe alt receptor, sau v1 dupa un flash care a
		              facut alt machine-id): mutat in <cale>.vechi (aceleasi drepturi); mesajul il da cel care cheama;
		  "incomplet" identitatea nu se poate citi acum: nimic schimbat, fisierul ramane pentru pornirea urmatoare."""
		vechi = self.cale + SUFIX_CHEI_VECHI
		octeti = self._octeti(self.cale)
		if octeti is None:
			if os.path.exists(self.cale) or not os.path.exists(vechi):
				return ""
			date, v, complet = self._decripteaza(self._octeti(vechi) or b"")
			if date is None:
				return ""
			if not _identitateCompleta(self.identitate()):
				return "incomplet"
			curat, legaturi = _desface(date)
			if not self.scrie(curat, legaturi):
				return ""
			_jurnal("cheile puse deoparte se citesc din nou: scrise in formatul nou")
			return "refacut"
		date, v, complet = self._decripteaza(octeti)
		if date is not None:
			if v == VERSIUNE_CHEI:
				return ""
			if not _identitateCompleta(self.identitate()):
				return "incomplet"
			curat, legaturi = _desface(date)
			if not self.scrie(curat, legaturi):
				return ""
			_jurnal("cheile scrise in formatul nou (legat de receptor, nu de instalare)")
			return "recriptat"
		if not complet:
			_jurnal("cheile nu se verifica acum: identitatea receptorului nu se poate citi")
			return "incomplet"
		try:
			os.replace(self.cale, vechi)
		except OSError as e:
			_jurnal("cheile care nu se pot citi nu s-au mutat: %s" % (getattr(e, "strerror", None) or
				e.__class__.__name__))
			return ""
		self._memorie = None
		_jurnal("cheile nu se pot citi pe acest receptor: puse deoparte, trebuie puse din nou")
		return "deoparte"

	def deDinNou(self):
		"""True cat timp cheile vechi stau deoparte (nu se mai puteau citi) si nu s-a scris inca niciun fisier nou"""
		return os.path.exists(self.cale + SUFIX_CHEI_VECHI) and not os.path.exists(self.cale)

	def citeste(self):
		"""{serviciu: cheie}; {} daca fisierul lipseste sau nu se poate citi"""
		return self._citesteTot()[0]

	def legaturi(self):
		"""{serviciu: origine} pentru cheile serviciilor cu adresa; un serviciu lipsa = cheie din versiunea veche"""
		return self._citesteTot()[1]

	def scrie(self, date, legaturi=None):
		"""cheile (si legaturile lor; None = cele din fisier, pentru cheile ramase) criptate in fisier, plicul v2.
		Nimic nu se scrie cand identitatea nu se poate citi complet (cheile ar ramane legate de o identitate gresita).
		Dupa o scriere buna, fisierul pus deoparte (<cale>.vechi) se sterge: cheile au fost puse din nou."""
		ident = self.identitate()
		if not _identitateCompleta(ident):
			_jurnal("cheile nu s-au scris: identitatea receptorului nu se poate citi")
			return False
		if legaturi is None:
			legaturi = self.legaturi()
		continut = dict((k, v) for k, v in date.items() if k in SERVICII and v)
		leg = dict((k, v) for k, v in legaturi.items() if k in CU_ADRESA and k in continut and isinstance(v, str))
		if leg:
			continut[CHEIE_LEGATURI] = leg
		octeti = cripteaza(continut, ident)
		nou = self.cale + ".nou"
		try:
			d = os.path.dirname(self.cale)
			if d and not os.path.isdir(d):
				os.makedirs(d)
			fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
			try:
				if hasattr(os, "fchmod"):
					os.fchmod(fd, 0o600)
				rest = octeti
				while rest:
					rest = rest[os.write(fd, rest):]
				os.fsync(fd)
			finally:
				os.close(fd)
			os.replace(nou, self.cale)
			self._memorie = None
		except (OSError, IOError) as e:
			_jurnal("cheile nu s-au scris: %s" % (getattr(e, "strerror", None) or e.__class__.__name__))
			try:
				os.unlink(nou)
			except OSError:
				pass
			return False
		try:
			os.unlink(self.cale + SUFIX_CHEI_VECHI)
		except OSError:
			pass
		return True

	def schimba(self, serviciu, valoare, adresa=None):
		"""pune cheia unui serviciu (valoare goala sau None = o sterge). La serviciile cu adresa cheia se leaga de
		gazda `adresa` (None = adresa din setari de acum). -> (True/False, mesaj)"""
		if serviciu not in SERVICII:
			return False, _t("Serviciu necunoscut.")
		date, legaturi = self._citesteTot()
		if valoare is None or not str(valoare).strip():
			date.pop(serviciu, None)
			legaturi.pop(serviciu, None)
			mesaj = _t("Cheia a fost ștearsă.")
		else:
			v = curataCheie(valoare, serviciu == "propriu")
			if not v:
				return False, _t("Cheia are caractere care nu pot fi într-o cheie (sau e prea lungă). Nu s-a schimbat nimic.")
			date[serviciu] = v
			mesaj = _t("Cheia e salvată pe receptor.")
			if serviciu in CU_ADRESA:
				legaturi[serviciu] = origine(adresaServiciului(serviciu) if adresa is None else adresa)
				if not legaturi[serviciu]:
					mesaj += u" " + _t("Cheia pleacă numai spre adresa serverului de acum: scrie întâi adresa, apoi pune "
						"cheia.")
		if not self.scrie(date, legaturi):
			return False, _t("Cheia nu s-a putut salva pe receptor.")
		instanta().setariSchimbate()
		return True, mesaj

	def legaDeAdresa(self, serviciu, adresa=None):
		"""cheia deja salvata a unui serviciu cu adresa, legata de gazda `adresa` (None = adresa din setari); numai
		pentru o cheie pusa chiar atunci de om, pe televizor (ecranul o leaga de adresa salvata odata cu ea). -> True
		daca s-a schimbat ceva"""
		if serviciu not in CU_ADRESA:
			return False
		date, legaturi = self._citesteTot()
		if serviciu not in date:
			return False
		noua = origine(adresaServiciului(serviciu) if adresa is None else adresa)
		if legaturi.get(serviciu) == noua:
			return False
		legaturi[serviciu] = noua
		if not self.scrie(date, legaturi):
			return False
		instanta().setariSchimbate()
		return True

	def legaCheileVechi(self, s=None):
		"""o singura data, la pornire: cheile serviciilor cu adresa salvate fara legatura (fisierul versiunii vechi) se
		leaga de adresa de acum, numai daca e https sau in reteaua de acasa; altfel raman nelegate ("") si nu pleaca
		nicaieri pana nu sunt puse din nou. -> cate s-au legat (si scris)"""
		date, legaturi = self._citesteTot()
		vechi = [k for k in CU_ADRESA if k in date and k not in legaturi]
		if not vechi:
			return 0
		for k in vechi:
			adresa = adresaServiciului(k, s)
			g = gazdaSiPort(adresa)
			buna = g is not None and (g[2] == "https" or clasaAdresa(adresa) == CASA) and clasaAdresa(adresa) != RECEPTOR
			legaturi[k] = origine(adresa) if buna else u""
		if self.scrie(date, legaturi):
			_jurnal("cheile vechi legate de adresele lor: %d" % len(vechi))
			return len(vechi)
		return 0

	def stare(self):
		"""{serviciu: True/False}: numai daca exista o cheie, niciodata cheia"""
		date = self.citeste()
		return dict((k, k in date) for k in SERVICII)


_CHEI = [None]


def chei():
	if _CHEI[0] is None:
		_CHEI[0] = Chei()
	return _CHEI[0]


def cheiePentru(serviciu, adresa, cheile=None, legaturi=None):
	"""cheia care poate pleca spre `adresa` -> (cheie, de ce nu: "" / "alta" / "http"). Serviciile cu adresa fixa:
	cheia lor. Cele cu adresa (CU_ADRESA): numai daca cheia e legata chiar de gazda adresei (schema, nume, port) si
	adresa e https sau in reteaua de acasa; o cheie pusa pentru alt server, una veche nelegata sau http spre internet nu
	pleaca (cererea merge fara cheie)."""
	cheile = cheile if cheile is not None else chei().citeste()
	cheie = cheile.get(serviciu, u"") or u""
	if not cheie or serviciu not in CU_ADRESA:
		return cheie, u""
	legaturi = legaturi if legaturi is not None else chei().legaturi()
	o = origine(adresa)
	if not o or not legaturi.get(serviciu) or legaturi.get(serviciu) != o:
		return u"", "alta"
	if o.startswith("http://") and clasaAdresa(adresa) != CASA:
		return u"", "http"
	return cheie, u""


def gazdaLegaturii(serviciu):
	"""gazda pentru care a fost pusa cheia unui serviciu cu adresa (pentru mesaje), sau "" """
	try:
		o = chei().legaturi().get(serviciu) or u""
	except Exception:
		return u""
	g = gazdaSiPort(o)
	return g[0] if g else u""


# ------------------------------------------------------------------ HTTP (fara redirectionari, certificatele verificate)

class EroareTraducere(Exception):
	"""asteptare_s: cat a spus serviciul sa se astepte (Retry-After, retryDelay), sau None; pe_zi: limita care nu
	trece repede (pe zi sau pe luna), nu cea pe minut; cauza si ce_faci: textul in doua, pentru paginile care le arata
	separat (ceasul receptorului in urma, Components/HdsCeasHttps.py); altfel cauza e textul si ce_faci e gol"""

	def __init__(self, fel, text, cod=None, asteptare_s=None, pe_zi=False, cauza=None, ce_faci=u""):
		Exception.__init__(self, text)
		self.fel, self.text, self.cod = fel, text, cod
		self.asteptare_s, self.pe_zi = asteptare_s, pe_zi
		self.cauza = text if cauza is None else cauza
		self.ce_faci = ce_faci or u""
		self.detaliu = (u"HTTP %d" % cod) if isinstance(cod, int) and cod else u""	# detaliuEroare, cand e corpul


class Raspuns(tuple):
	"""raspunsul lui trimite(): (cod, octeti), ca inainte (`cod, date = trimite(...)` merge la fel); in .antete numai
	antetele folosite de modul, cu numele scrise mic (acum: retry-after)"""
	antete = None


def _raspunsCu(cod, date, raspuns):
	r = Raspuns((cod, date))
	antete = {}
	try:
		h = getattr(raspuns, "headers", None)
		v = h.get("Retry-After") if h is not None else None
		if v:
			antete["retry-after"] = str(v)[:100]
	except Exception:
		pass
	r.antete = antete
	return r


class _FaraRedirectionari(HTTPRedirectHandler):
	"""o cheie nu pleaca niciodata spre alta adresa decat cea data"""

	def redirect_request(self, req, fp, code, msg, headers, newurl):
		return None


def motivIp(ip, port, criptat):
	"""de ce nu se poate conecta la IP-ul `ip` (inainte de connect): RECEPTOR, INTERNET (http spre internet) sau None"""
	b = octetiIp(ip)
	if b is None:
		return RECEPTOR
	if (textIp(b), port) in PERMISE_PROBE:
		return None
	clasa = clasaIp(b)
	if clasa == RECEPTOR:
		return RECEPTOR
	if not criptat and clasa != CASA:
		return INTERNET
	return None


def _conectarePazita(criptat):
	"""in locul lui socket.create_connection in conexiunile HTTP ale modulului: adresele numelui (getaddrinfo) se iau
	pe rand, cele refuzate (motivIp) sunt sarite inainte de connect, iar socketul legat trece prin verificaConexiunea
	inainte de TLS si de cerere. Un nume din casa cu doua adrese (IPv6 globala si IPv4 privata) merge pe cea permisa.
	AdresaOprita numai cand nicio adresa nu e permisa; o adresa permisa care nu raspunde da eroarea ei de retea."""
	def conecteaza(adresa, *argumente, **cuvinte):
		gazda, port = adresa[0], adresa[1]
		oprita = eroare = None
		for _fam, _tip, _proto, _nume, sa in socket.getaddrinfo(gazda, port, 0, socket.SOCK_STREAM):
			motiv = motivIp(sa[0], sa[1], criptat)
			if motiv:
				oprita = oprita or AdresaOprita(motiv, textIp(octetiIp(sa[0]) or b""))
				continue
			try:
				s = socket.create_connection((sa[0], sa[1]), *argumente, **cuvinte)
			except (socket.error, OSError) as e:
				eroare = e
				continue
			try:
				verificaConexiunea(s, criptat)
			except Exception as e:
				try:
					s.close()
				except Exception:
					pass
				if not isinstance(e, AdresaOprita):
					raise
				oprita = oprita or e
				continue
			return s
		if eroare is not None:
			raise eroare
		raise oprita or AdresaOprita(RECEPTOR)
	return conecteaza


class _ConexiuneHttp(_http.HTTPConnection):
	def __init__(self, *argumente, **cuvinte):
		_http.HTTPConnection.__init__(self, *argumente, **cuvinte)
		self._create_connection = _conectarePazita(False)


class _ConexiuneHttps(_http.HTTPSConnection):
	def __init__(self, *argumente, **cuvinte):
		_http.HTTPSConnection.__init__(self, *argumente, **cuvinte)
		self._create_connection = _conectarePazita(True)


class _HttpPazit(HTTPHandler):
	def http_open(self, req):
		return self.do_open(_ConexiuneHttp, req)


class _HttpsPazit(HTTPSHandler):
	def https_open(self, req):
		return self.do_open(_ConexiuneHttps, req, context=self._context)


_DESCHIZATOR = []


def _deschizator():
	"""un singur deschizator pentru tot modulul (ca urllib.request.urlopen): ssl.create_default_context() citeste
	certificatele la fiecare apel (19 ms pe PC, la fiecare cerere). Fara proxy-uri din mediu (ProxyHandler gol: cheia
	pleaca numai direct spre gazda ei), conexiunile verificate (verificaConexiunea), fara redirectionari."""
	if not _DESCHIZATOR:
		_DESCHIZATOR.append(build_opener(ProxyHandler({}), _HttpsPazit(context=ssl.create_default_context()),
			_HttpPazit(), _FaraRedirectionari()))
	return _DESCHIZATOR[0]


def _gazda(adresa):
	try:
		return urlsplit(adresa).hostname or "?"
	except Exception:
		return "?"


def _texteCeas(eroare):
	"""(cauza, ce faci) cand certificatul serviciului cade din cauza ceasului receptorului (Components/HdsCeasHttps.py),
	altfel None. Verificarea certificatelor ramane pornita; aici se alege numai textul."""
	try:
		from Components import HdsCeasHttps
		return HdsCeasHttps.texte(eroare)
	except Exception:
		return None


# ------------------------------------------------------------------ pornirea: reteaua si ceasul inainte de prima cerere

# de_la: incarcarea modulului (pornirea enigma2); gata: asteptarea s-a facut o data (cu succes sau dupa termen)
_PORNIRE = {"de_la": time.monotonic(), "gata": False}
_RTF_UP, _RTF_REJECT = 0x0001, 0x0200


def reteaPornita(rute4="/proc/net/route", rute6="/proc/net/ipv6_route"):
	"""True: exista o ruta implicita pornita (IPv4 sau IPv6, alta placa decat lo); False: niciuna; None: tabelele nu se
	pot citi (PC, alt sistem): atunci nu se asteapta. Nimic trimis in retea."""
	citite = False
	try:
		with open(rute4, "r") as f:
			citite = True
			for rand in f.read(65536).splitlines()[1:]:
				p = rand.split()
				if len(p) >= 8 and p[1] == "00000000" and p[7] == "00000000" and int(p[3], 16) & _RTF_UP:
					return True
	except (OSError, IOError, ValueError):
		pass
	try:
		with open(rute6, "r") as f:
			citite = True
			for rand in f.read(65536).splitlines():
				p = rand.split()
				if len(p) >= 10 and p[0] == "0" * 32 and p[1] == "00" and p[9] != "lo":
					fl = int(p[8], 16)
					if fl & _RTF_UP and not fl & _RTF_REJECT:
						return True
	except (OSError, IOError, ValueError):
		pass
	return False if citite else None


def ceasSigur():
	"""ora e sigura (NTP, transpondere, RTC) sau nu se poate spune nimic (PC): Components/HdsCeasHttps.judecaCeasul"""
	try:
		from Components import HdsCeasHttps
		return HdsCeasHttps.judecaCeasul() is None
	except Exception:
		return True


def pornireGata():
	return reteaPornita() is not False and ceasSigur()


def asteaptaPornirea(gata_=None, termen_s=None, dormi=time.sleep, ceas=time.monotonic):
	"""pe un fir de cereri (niciodata pe firul enigma2), inainte de cerere: o singura data pe pornire asteapta ruta
	implicita si ceasul sigur, cel mult PORNIRE_ASTEPTARE_S de la incarcarea modulului; apoi nu mai asteapta nimic.
	O cerere care pleaca inainte (retea sau ceas inca nepornite) ar cadea cu o eroare de retea sau de certificat, care
	oricum nu opreste serviciul. -> True daca a gasit totul gata, False daca a plecat dupa termen"""
	if _PORNIRE["gata"]:
		return True
	gata_ = gata_ or pornireGata
	termen_s = PORNIRE_ASTEPTARE_S if termen_s is None else termen_s
	asteptat = False
	while True:
		try:
			ok = bool(gata_())
		except Exception:
			ok = True
		if ok:
			_PORNIRE["gata"] = True
			if asteptat:
				_jurnal("pornirea: reteaua si ceasul sunt gata (%d s de la pornire)" % int(ceas() - _PORNIRE["de_la"]))
			return True
		if ceas() - _PORNIRE["de_la"] >= termen_s:
			_PORNIRE["gata"] = True
			_jurnal("pornirea: reteaua sau ceasul inca nu sunt gata dupa %d s; cererile pleaca oricum" % int(termen_s))
			return False
		asteptat = True
		dormi(PORNIRE_PAS_S)


def trimite(adresa, antete, corp, termen_s):
	"""POST cu corpul dat (GET cand corp e None) -> (cod, octeti), ca Raspuns (cu .antete). Erorile de retea ridica
	EroareTraducere (fara cheie sau adresa intreaga in text)."""
	r = Request(adresa, data=corp, headers=antete)
	try:
		raspuns = _deschizator().open(r, timeout=termen_s)
		cod = raspuns.getcode()
	except HTTPError as e:
		raspuns, cod = e, e.code
	except (URLError, ssl.SSLError, OSError, ValueError) as e:
		motiv = getattr(e, "reason", e)
		if isinstance(motiv, AdresaOprita) or isinstance(e, AdresaOprita):
			oprita = motiv if isinstance(motiv, AdresaOprita) else e
			raise EroareTraducere(E_ADRESA, textAdresaOprita(oprita.motiv, _gazda(adresa)))
		if "timed out" in str(motiv).lower() or e.__class__.__name__ in ("timeout", "TimeoutError"):
			raise EroareTraducere(E_TERMEN, _t("%s nu a răspuns la timp.") % _gazda(adresa))
		ceas = _texteCeas(e)
		if ceas:
			raise EroareTraducere(E_RETEA, u"%s %s" % ceas, cauza=ceas[0], ce_faci=ceas[1])
		raise EroareTraducere(E_RETEA, _t("Receptorul nu a putut ajunge la %s (%s).") % (_gazda(adresa),
			_motivScurt(motiv)))
	try:
		date = raspuns.read(MAX_RASPUNS + 1)
	except Exception as e:
		if "timed out" in str(e).lower():
			raise EroareTraducere(E_TERMEN, _t("%s nu a răspuns la timp.") % _gazda(adresa))
		raise EroareTraducere(E_RETEA, _t("Răspunsul de la %s s-a întrerupt.") % _gazda(adresa))
	finally:
		try:
			raspuns.close()
		except Exception:
			pass
	if len(date) > MAX_RASPUNS:
		raise EroareTraducere(E_RASPUNS, _t("Răspunsul de la %s e prea mare.") % _gazda(adresa))
	return _raspunsCu(cod, date, raspuns)


# ------------------------------------------------------------------ limita atinsa (429): cat se asteapta, pe minut sau pe zi

_REINCEARCA_IN = re.compile(r"retry in ([0-9]+(?:\.[0-9]+)?)\s*s", re.I)
# Groq: Please try again in 7m12.5s (ore, minute, secunde; oricare poate lipsi)
_INCEARCA_DIN_NOU = re.compile(r"try again in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([0-9]+(?:\.[0-9]+)?)s)?", re.I)
_DURATA_GOOGLE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)s\s*$")
_PE_ZI = re.compile(r"per[ _-]?day|perday|daily|per[ _-]?month|monthly|free quota|billing period")


def _secundeRetryAfter(v):
	"""antetul Retry-After: secunde sau o data HTTP -> secunde (>= 0), sau None"""
	v = (v or u"").strip()
	if not v:
		return None
	try:
		return max(0.0, float(v))
	except ValueError:
		pass
	try:
		from email.utils import parsedate_tz, mktime_tz
		p = parsedate_tz(v)
		return max(0.0, mktime_tz(p) - time.time()) if p else None
	except Exception:
		return None


def _jsonEroare(date):
	try:
		j = json.loads(date.decode("utf-8", "replace") if isinstance(date, bytes) else date)
	except Exception:
		return None
	if isinstance(j, list) and j and isinstance(j[0], dict):
		j = j[0]
	return j if isinstance(j, dict) else None


def asteptareDinRaspuns(cod, antete, date):
	"""raspunsul unei limite atinse -> (secunde de asteptat sau None, pe_zi). Secundele: antetul Retry-After, altfel la
	Gemini error.details[] cu "@type" ...RetryInfo si "retryDelay": "37s", altfel "retry in 37.5s" din mesaj (la Groq
	"try again in 7m12.5s"). pe_zi: la Gemini quotaId / quotaMetric cu PerDay (fata de PerMinute); altfel mesajul
	("per day", "daily", "free quota", pe luna); DeepL 456 (cota perioadei de facturare), 402 (fara credit), Cloudflare
	3036 (unitatile gratuite ale zilei)."""
	j = _jsonEroare(date) or {}
	e = j.get("error")
	mesaj, ids, intarziere = u"", [], None
	zi_cloudflare = False
	if isinstance(e, dict):
		mesaj = u"%s %s" % (e.get("message") or u"", e.get("status") or u"")
		for d in e.get("details") or []:
			if not isinstance(d, dict):
				continue
			if str(d.get("@type") or u"").endswith("RetryInfo"):
				m = _DURATA_GOOGLE.match(str(d.get("retryDelay") or u""))
				if m:
					intarziere = float(m.group(1))
			for v in d.get("violations") or []:
				if isinstance(v, dict):
					ids.append(u"%s %s" % (v.get("quotaId") or u"", v.get("quotaMetric") or u""))
	elif isinstance(e, str):
		mesaj = e
	elif isinstance(j.get("message"), str):
		mesaj = j["message"]
	elif eroareCloudflare(j) is not None:
		c = eroareCloudflare(j)
		mesaj = c[1]
		# 3036: unitatile gratuite ale zilei s-au terminat (pana la 00:00 UTC)
		zi_cloudflare = str(c[0]) == "3036"
	elif isinstance(date, bytes) and not j:
		mesaj = date[:2000].decode("utf-8", "replace")
	secunde = _secundeRetryAfter((antete or {}).get("retry-after"))
	if secunde is None:
		secunde = intarziere
	if secunde is None:
		m = _REINCEARCA_IN.search(mesaj)
		if m:
			secunde = float(m.group(1))
	if secunde is None:
		m = _INCEARCA_DIN_NOU.search(mesaj)
		if m and any(m.groups()):
			secunde = int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0)
	ids_ = u" ".join(ids).lower()
	if "perday" in ids_ or "per_day" in ids_:
		pe_zi = True
	elif "perminute" in ids_ or "persecond" in ids_ or "per_minute" in ids_:
		pe_zi = False
	else:
		pe_zi = bool(_PE_ZI.search(mesaj.lower())) or cod in (402, 456) or zi_cloudflare
	return secunde, pe_zi


def _zile(an, luna, zi):
	"""zilele de la 1.1.1970 (calendarul gregorian), fara modulul calendar"""
	an -= 1 if luna <= 2 else 0
	era = an // 400
	yoe = an - era * 400
	doy = (153 * (luna + (-3 if luna > 2 else 9)) + 2) // 5 + zi - 1
	return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def _duminica(an, luna, a_cata):
	"""ziua lunii pentru a a_cata duminica"""
	zi_saptamana = (_zile(an, luna, 1) + 4) % 7		# 0 = duminica (1.1.1970 a fost joi)
	return 1 + (7 - zi_saptamana) % 7 + 7 * (a_cata - 1)


def panaLaMiezulNoptiiPacific(acum=None):
	"""secundele pana la miezul noptii, ora Pacific (cererile pe zi ale Gemini se reinnoiesc atunci): UTC-8, iar intre a
	doua duminica din martie si prima duminica din noiembrie (ora 2 locala) UTC-7; fara baza de fusuri orare"""
	t = time.time() if acum is None else acum
	an = time.gmtime(t).tm_year
	vara = _zile(an, 3, _duminica(an, 3, 2)) * 86400 + 10 * 3600 <= t < _zile(an, 11, _duminica(an, 11, 1)) * 86400 + 9 * 3600
	local = t - (7 if vara else 8) * 3600
	return max(60, int(86400 - local % 86400))


def panaLaMiezulNoptiiUtc(acum=None):
	"""secundele pana la 00:00 UTC (unitatile gratuite ale zilei la Cloudflare se reinnoiesc atunci), cel putin 60"""
	t = time.time() if acum is None else acum
	return max(60, int(86400 - t % 86400))


def trecatoare(eroare):
	"""caderile care trec singure: reteaua (si DNS, TLS, ceasul in urma), termenul depasit, un raspuns 5xx"""
	return eroare.fel in (E_RETEA, E_TERMEN) or (eroare.fel == E_RASPUNS and (eroare.cod or 0) >= 500)


def treceLaUrmatorul(eroare):
	"""dupa eroarea asta cererea trece pe loc la urmatorul serviciu liber din lant"""
	return eroare.fel in FELURI_TRECERE or trecatoare(eroare)


def opritDupaRefuzuri(refuzuri):
	"""atatea refuzuri ale cheii la rand opresc serviciul (mesajul, starea refuzat)"""
	return refuzuri >= REFUZURI_OPRIRE


def durataBlocarii(eroare, serviciu, alt_serviciu=True, caderi=1, refuzuri=1):
	"""cat asteapta un serviciu dupa eroare, in secunde (None = pana la schimbarea setarilor, 0 = nu asteapta):
	  adresa refuzata la conectare -> pana la schimbarea setarilor (e chiar setarea);
	  cheie refuzata -> dupa `refuzuri` (refuzurile la rand, cu acesta): PAUZE_REFUZ_S[0], PAUZE_REFUZ_S[1], iar de la
	    REFUZURI_OPRIRE serviciul e oprit si se reincearca o data la REVERIFICARE_REFUZ_S (niciodata pentru totdeauna);
	  limita pe minut -> cat spune serviciul (cel mult MAX_ASTEPTARE_SCURTA_S), altfel PAUZA_COTA_S; limita pe zi -> la
	    Gemini pana la miezul noptii ora Pacific, la Cloudflare pana la 00:00 UTC (unitatile gratuite ale zilei), la Groq
	    cat spune el (limita lui pe zi e o fereastra care curge: tokenii se intorc pe rand), altfel LIMITA_ZI_S;
	  model sau limba -> PAUZA_S;
	  caderi trecatoare (retea, termen, 5xx) -> pauze crescatoare: PAUZA_COTA_S dublata la fiecare cadere la rand, cel
	    mult PAUZA_S; fara alt serviciu in lant, primele CADERI_MAXIME - 1 nu asteapta (pagina urmatoare reincearca);
	  alt raspuns neasteptat -> PAUZA_S dupa CADERI_MAXIME la rand"""
	fel = eroare.fel
	if fel == E_ADRESA:
		return None
	if fel == E_CHEIE:
		if opritDupaRefuzuri(refuzuri):
			return REVERIFICARE_REFUZ_S
		return PAUZE_REFUZ_S[min(max(refuzuri, 1), len(PAUZE_REFUZ_S)) - 1]
	if fel == E_COTA:
		s = eroare.asteptare_s
		if eroare.pe_zi:
			if serviciu == "gemini":
				return panaLaMiezulNoptiiPacific()
			if serviciu == "cloudflare":
				return panaLaMiezulNoptiiUtc()
			if serviciu == "groq" and s is not None:
				return min(max(float(PAUZA_COTA_S), s), LIMITA_ZI_S)
			return LIMITA_ZI_S
		return PAUZA_COTA_S if s is None else min(max(1.0, s), MAX_ASTEPTARE_SCURTA_S)
	if fel in (E_LIPSA, E_LIMBA):
		return PAUZA_S
	if trecatoare(eroare):
		if alt_serviciu or caderi >= CADERI_MAXIME:
			return min(PAUZA_S, PAUZA_COTA_S * 2 ** min(max(caderi, 1) - 1, 8))
		return 0
	if caderi >= CADERI_MAXIME:
		return PAUZA_S
	return 0


def _motivScurt(motiv):
	t = str(getattr(motiv, "strerror", None) or motiv)
	t = re.sub(r"https?://\S+", "", t)
	return t[:80] or "?"


# ------------------------------------------------------------------ cererile si raspunsurile serviciilor

def _json(obiect):
	return json.dumps(obiect, ensure_ascii=False).encode("utf-8")


# ce se traduce, pentru instructiunea modelelor de limbaj; teletextul si HbbTV au loc putin pe ecran
_CE_TRADUCE = {
	"epg": u"TV programme guide texts (titles and descriptions)",
	"teletext": u"texts of a TV teletext page (headlines, news, tables, menus)",
	"hbbtv": u"texts of an interactive TV (HbbTV) page (menus, buttons, headlines, articles)",
}
_SCURT = u" Each line has little room on the screen: keep the translation about as short as the original."


def instructiuneModel(tinta, sursa, n, fel="subtitrari"):
	"""textul de sistem pentru modelele de limbaj: numai traducerea, rand cu rand; fel "epg" = textele ghidului,
	"teletext" = o pagina de teletext, "hbbtv" = o pagina HbbTV"""
	din = (u" from %s" % NUME_ENGLEZ.get(sursa, sursa)) if sursa else u""
	ce = _CE_TRADUCE.get(fel, u"TV subtitles")
	return (u"You translate %s%s into %s. Reply with the translation only: no explanations, no notes, no "
		u"quotes, no comments, nothing else. The text has %d numbered lines. Reply with exactly %d lines in the same "
		u"order, each one starting with its number and a colon, for example \"1: ...\". Keep names, numbers and the "
		u"dialogue dashes. The lines under \"Context\" are earlier subtitles: use them only to understand the text, do "
		u"not translate them and do not repeat them." % (ce, din, NUME_ENGLEZ.get(tinta, tinta), n, n)) + (
		_SCURT if fel in ("teletext", "hbbtv") else u"")


def continutModel(texte, context):
	parti = []
	if context:
		parti.append(u"Context:\n" + u"\n".join(context))
	parti.append(u"Translate:\n" + u"\n".join(u"%d: %s" % (i + 1, t) for i, t in enumerate(texte)))
	return u"\n\n".join(parti)


def cererePropriu(cfg, text, sursa, tinta):
	"""adresa proprie: -> (adresa, antete, corp) pentru UN rand; corp None la GET"""
	json_ = (cfg.get("raspuns") or "json") == "json"
	antete = {"Accept": "application/json" if json_ else "text/plain, */*", "User-Agent": "HDSatelit-receptor"}
	adresa = umpleSablon(cfg["adresa"], text, sursa, tinta, "adresa")
	corp = None
	if (cfg.get("metoda") or "GET") == "POST":
		if cfg.get("tip_corp") == "formular":
			corp = umpleSablon(cfg.get("corp"), text, sursa, tinta, "formular").encode("utf-8")
			antete["Content-Type"] = "application/x-www-form-urlencoded"
		else:
			corp = umpleSablon(cfg.get("corp"), text, sursa, tinta, "json").encode("utf-8")
			antete["Content-Type"] = "application/json; charset=utf-8"
	if cfg.get("antet") and cfg.get("cheie") and numeAntetBun(cfg["antet"]):
		antete[cfg["antet"]] = cfg["cheie"]
	return adresa, antete, corp


def cerere(cfg, texte, sursa, tinta, context=(), ollama=None, fel="subtitrari", extra=True):
	"""-> (adresa, antete, corp) pentru serviciul din cfg (la propriu numai primul text: un rand pe cerere).
	ollama: True/False aflat de traduceAcum; None = numai dupa port, fara retea. extra=False: fara campurile gandirii
	trimise la Groq (reincercarea dupa un 400)."""
	serv = cfg["serviciu"]
	if serv == "propriu":
		return cererePropriu(cfg, texte[0] if texte else u"", sursa, tinta)
	cheie = cfg.get("cheie") or ""
	antete = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json",
		"User-Agent": "HDSatelit-receptor"}
	if serv == "azure":
		adresa = AZURE_ADRESA + "?api-version=3.0&to=" + quote(_COD_AZURE.get(tinta, tinta))
		if sursa:
			adresa += "&from=" + quote(_COD_AZURE.get(sursa, sursa))
		antete["Ocp-Apim-Subscription-Key"] = cheie
		if cfg.get("regiune"):
			antete["Ocp-Apim-Subscription-Region"] = cfg["regiune"]
		return adresa, antete, _json([{"Text": t} for t in texte])
	if serv == "google":
		antete["X-goog-api-key"] = cheie
		corp = {"q": list(texte), "target": _COD_GOOGLE.get(tinta, tinta), "format": "text"}
		if sursa:
			corp["source"] = _COD_GOOGLE.get(sursa, sursa)
		return GOOGLE_ADRESA, antete, _json(corp)
	if serv == "deepl":
		antete["Authorization"] = "DeepL-Auth-Key " + cheie
		corp = {"text": list(texte), "target_lang": _COD_DEEPL_TINTA.get(tinta, tinta.upper())}
		if sursa:
			corp["source_lang"] = _COD_DEEPL_SURSA.get(sursa, sursa.upper())
		if context:
			corp["context"] = u"\n".join(context)
		return adresaDeepL(cheie), antete, _json(corp)
	if serv == "libre":
		corp = {"q": list(texte), "source": _COD_LIBRE.get(sursa, sursa) if sursa else "auto",
			"target": _COD_LIBRE.get(tinta, tinta), "format": "text"}
		if cheie:
			corp["api_key"] = cheie
		return cfg["adresa"].rstrip("/") + "/translate", antete, _json(corp)
	if serv == "gemini":
		antete["x-goog-api-key"] = cheie
		model = cfg.get("model") or MODEL_GEMINI_IMPLICIT
		generare = {"temperature": 0.2, "maxOutputTokens": 2048}
		if "2.5-flash" in model:
			generare["thinkingConfig"] = {"thinkingBudget": 0}
		corp = {
			"systemInstruction": {"parts": [{"text": instructiuneModel(tinta, sursa, len(texte), fel)}]},
			"contents": [{"role": "user", "parts": [{"text": continutModel(texte, context)}]}],
			"generationConfig": generare,
		}
		return GEMINI_ADRESA % quote(model, safe="-._"), antete, _json(corp)
	if serv in ("openai", "groq", "cloudflare"):
		if cheie:
			antete["Authorization"] = "Bearer " + cheie
		if serv == "groq":
			adresa, model = GROQ_ADRESA, cfg.get("model") or MODEL_GROQ_IMPLICIT
		elif serv == "cloudflare":
			adresa = CLOUDFLARE_ADRESA % quote((cfg.get("cont") or u"").strip().lower(), safe="")
			model = cfg.get("model") or MODEL_CLOUDFLARE_IMPLICIT
		else:
			adresa, model = adresaOpenAI(cfg["adresa"]), cfg.get("model") or ""
		corp = {
			"model": model,
			"messages": [{"role": "system", "content": instructiuneModel(tinta, sursa, len(texte), fel)},
				{"role": "user", "content": continutModel(texte, context)}],
			"temperature": 0.2,
			"stream": False,
		}
		if not primesteTemperatura(adresa, model):
			del corp["temperature"]
		if serv == "openai" and (esteOllama(cfg["adresa"], retea=False) if ollama is None else ollama):
			# gandirea oprita: gemma4 gandeste implicit (4,4 s in loc de 0,36 s pe PC); modelul tinut in memorie
			# (incarcarea lui dureaza 5,3 s)
			corp["reasoning_effort"] = "none"
			corp["keep_alive"] = OLLAMA_PASTREAZA
		elif serv == "groq" and model.startswith("openai/gpt-oss") and extra:
			# gpt-oss la Groq: gandire putina (low, medium, high; fara none) si gandurile nescrise in raspuns, ca o
			# replica sa vina repede si sa consume putin din tokenii pe zi; la 400 cererea pleaca o data fara ele
			corp["reasoning_effort"] = "low"
			corp["include_reasoning"] = False
		return adresa, antete, _json(corp)
	raise EroareTraducere(E_LIPSA, _t("Serviciu necunoscut."))


# Campul temperature: unele servere compatibile OpenAI il refuza cu 400 (modelele care gandesc obligatoriu, sau unele
# care primesc numai valoarea lor implicita). Dupa un astfel de refuz cererea pleaca o data din nou fara el, iar gazda si
# modelul se tin minte in RAM: cererile urmatoare pleaca direct fara el.
_FARA_TEMPERATURA = set()


def _semnTemperatura(adresa, model):
	try:
		u = urlsplit(adresa or u"")
		locul = u"%s://%s" % (u.scheme, u.netloc.lower())
	except ValueError:
		locul = u"?"
	return (locul, model or u"")


def primesteTemperatura(adresa, model):
	"""False dupa ce serverul de la adresa a refuzat campul temperature pentru acest model"""
	return _semnTemperatura(adresa, model) not in _FARA_TEMPERATURA


_FORMAT_CHAT = ("openai", "groq", "cloudflare")     # serviciile cu cererea in format chat/completions


def _modelDinCorp(corp):
	try:
		return json.loads(corp.decode("utf-8")).get("model") or u""
	except Exception:
		return u""


def refuzaTemperatura(cod, date):
	"""raspunsul e un 400 care pomeneste temperature (camp nesuportat sau valoare refuzata)"""
	if cod != 400:
		return False
	try:
		text = (date or b"")[:4000].decode("utf-8", "replace").lower()
	except Exception:
		return False
	return "temperature" in text


# Cheile planului vechi gratuit se termina cu „:fx” (api-free.deepl.com); pentru planul gratuit nou („Developer”)
# paginile DeepL nu spun adresa: la 403 se incearca o data si cealalta adresa, iar cea care raspunde se tine minte (dupa
# amprenta cheii, in RAM).
_DEEPL_ADRESA = {}


def _amprenta(cheie):
	return hashlib.sha256(cheie.encode("utf-8")).hexdigest()[:16]


def adresaDeepL(cheie):
	return _DEEPL_ADRESA.get(_amprenta(cheie)) or (DEEPL_FREE if cheie.endswith(":fx") else DEEPL_PRO)


def adresaOpenAI(adresa):
	a = adresa.strip().rstrip("/")
	if a.endswith("/chat/completions"):
		return a
	if a.endswith("/v1"):
		return a + "/chat/completions"
	return a + "/v1/chat/completions"


# Ollama (docs.ollama.com/api/openai-compatibility): /v1/chat/completions primeste
# "reasoning_effort" ("none" = gandirea oprita, la modelele care o pot opri; un nume necunoscut modelului = gandirea
# implicita a modelului, fara eroare). "keep_alive" nu e in lista paginii, dar Ollama 0.35 il aplica si pe /v1 (masurat).
# Celelalte servere compatibile OpenAI NU primesc aceste campuri: Groq da 400 la o valoare pe care modelul nu o are
# (gpt-oss nu are "none"; serviciul groq ii trimite "low", vezi cerere), OpenRouter refuza "none" la modelele care
# gandesc obligatoriu si vrea "reasoning": {...}, LM Studio nu le are in lista.
OLLAMA_PORT = 11434
OLLAMA_PASTREAZA = "30m"
_OLLAMA = {}


def esteOllama(adresa, trimite_=None, retea=True):
	"""Ollama: portul lui implicit (11434) sau, o singura data pe adresa si numai pe http, GET /api/version cu raspunsul
	{"version": ...}; raspunsul se tine minte in RAM. Fara retea (retea=False) numai portul si ce s-a aflat deja."""
	try:
		u = urlsplit((adresa or "").strip())
		baza, port = "%s://%s" % (u.scheme, u.netloc), u.port
	except ValueError:
		return False
	if port == OLLAMA_PORT:
		return True
	if baza in _OLLAMA or not retea or u.scheme != "http":
		return _OLLAMA.get(baza, False)
	try:
		cod, date = (trimite_ or trimite)(baza + "/api/version", {"Accept": "application/json",
			"User-Agent": "HDSatelit-receptor"}, None, 2.0)
		j = json.loads(date.decode("utf-8"))
		_OLLAMA[baza] = cod == 200 and isinstance(j, dict) and "version" in j
	except Exception:
		# fara raspuns sau nu e JSON: nu e Ollama (tinut minte, ca o adresa care nu raspunde la GET sa nu coste 2 s la
		# fiecare rand)
		_OLLAMA[baza] = False
	return _OLLAMA[baza]


def _mesajServiciu(date):
	"""mesajul de eroare dat de serviciu (scurt, fara adrese), pentru felul erorii"""
	try:
		j = json.loads(date.decode("utf-8", "replace"))
	except Exception:
		return u""
	m = u""
	if isinstance(j, dict):
		e = j.get("error")
		if isinstance(e, dict):
			m = u"%s %s" % (e.get("status") or e.get("code") or u"", e.get("message") or u"")
		elif isinstance(e, str):
			m = e
		elif j.get("message"):
			m = j.get("message")
		else:
			c = eroareCloudflare(j)
			if c is not None:
				m = u"%s %s" % (c[0] if c[0] is not None else u"", c[1])
	return re.sub(r"https?://\S+", "", str(m)).strip()[:160]


def eroareCloudflare(j):
	"""prima eroare din corpul API-ului Cloudflare ({"success": false, "errors": [{"code": 3036, "message": ...}]})
	-> (codul intern sau None, mesajul), sau None pentru alt corp"""
	if not isinstance(j, dict):
		return None
	lista = j.get("errors")
	if not isinstance(lista, list) or not lista or not isinstance(lista[0], dict):
		return None
	c = lista[0].get("code")
	cod = c if isinstance(c, (int, str)) and not isinstance(c, bool) and str(c).strip() else None
	return cod, str(lista[0].get("message") or u"")


# Cloudflare Workers: codurile interne ale erorilor (developers.cloudflare.com/workers-ai/platform/errors/) care spun ca
# modelul ales nu se poate folosi din acest cont (plan platit, termenii modelului, model privat), nu ca jetonul e rau
_CLOUDFLARE_MODEL = frozenset(("5035", "5016", "5018", "3041", "5007", "3042"))
_MODEL_LIPSA = ("no such model", "model not found", "model_not_found", "does not exist", "decommissioned",
	"model name is invalid")


def felEroareHttp(serv, cod, date):
	"""cod HTTP (si mesajul serviciului) -> felul erorii. Plata (402: credit terminat, la orice serviciu cu credit) si
	capacitatea depasita (498 la Groq) sunt cota: cererea trece la rezerva. Un 400 care cere o cheie (LibreTranslate pe
	un server cu chei) e cheia. La Cloudflare un 403 sau 400 pentru model (plan platit, termenii modelului, model
	necunoscut) e modelul, nu cheia refuzata."""
	m = _mesajServiciu(date).lower()
	if cod in (402, 429, 456, 498) or "quota" in m or "resource_exhausted" in m or "limit" in m and cod in (403, 429):
		return E_COTA
	if serv == "cloudflare" and cod in (400, 403, 404):
		c = eroareCloudflare(_jsonEroare(date))
		if (c is not None and str(c[0]) in _CLOUDFLARE_MODEL) or "paid plan" in m or "model" in m:
			return E_LIPSA
	if cod in (401, 407) or "api key not valid" in m or "api_key_invalid" in m or "invalid api key" in m \
			or "unauthorized" in m or "permission_denied" in m or "invalid subscription" in m \
			or "access denied" in m or "wrong key" in m:
		return E_CHEIE
	if cod == 403 and "paid plan" in m:
		return E_LIPSA
	if cod == 403:
		return E_CHEIE
	if cod == 400 and ("api key" in m or "api_key" in m):
		return E_CHEIE
	if cod == 400 and ("language" in m or "not supported" in m or "unsupported" in m):
		return E_LIMBA
	if cod == 400 and serv in ("google", "gemini") and "key" in m:
		return E_CHEIE
	if cod in (400, 404) and serv in _FORMAT_CHAT and any(x in m for x in _MODEL_LIPSA):
		return E_LIPSA
	if cod == 404 and serv in ("gemini", "openai", "groq", "cloudflare"):
		return E_LIPSA
	return E_RASPUNS


def textEroare(fel, serv, cod=None, mesaj=u""):
	nume = numeServiciu(serv)
	if fel == E_CHEIE:
		return _t("%s a refuzat cheia (cheie greșită, ștearsă sau fără drept pentru traducere).") % nume
	if fel == E_COTA:
		return _t("%s spune că s-a terminat cota gratuită sau că sunt prea multe cereri.") % nume
	if fel == E_LIMBA:
		return _t("%s nu traduce în limba aleasă.") % nume
	if fel == E_LIPSA:
		return _t("%s nu găsește modelul sau adresa (HTTP %d).") % (nume, cod or 0)
	return _t("%s a răspuns neașteptat (HTTP %d).") % (nume, cod or 0)


def textRegiuneAzure(cu_regiune):
	"""Azure a raspuns 401: fara regiune, de obicei lipseste regiunea resursei; cu regiune, cheia sau regiunea gresite"""
	if not cu_regiune:
		return _t("Lipsește regiunea resursei Azure: o găsești în portal, la resursa Translator, Overview › Location (de "
			"exemplu Germany West Central = germanywestcentral).")
	return _t("Cheia sau regiunea nu se potrivesc: verifică amândouă în portal (Keys and Endpoint).")


def textAzureToateRegiunile():
	"""proba (si configurarea): Azure a refuzat cheia (401) cu regiunea din setari si cu toate celelalte regiuni din
	REGIUNI_AZURE: cheia sau resursa (abonamentul) nu mai sunt bune, ori resursa e intr-o regiune din afara listei"""
	return textAzureRefuzaPeste() + u" " + textCeFaciRefuz("azure")


def textAzureRefuzaPeste():
	"""numai ce s-a intamplat (configurarea pas cu pas arata separat ce faci)"""
	return _t("Azure refuză cheia în toate regiunile încercate (HTTP 401): cheia nu mai e bună, resursa sau "
		"abonamentul sunt oprite, ori resursa e într-o regiune din afara listei.")


def textCeFaciRefuz(serviciu):
	"""ce are omul de facut cand un serviciu refuza cheia (televizor, web, proba)"""
	if serviciu == "azure":
		return _t("În portal.azure.com, la resursa Translator, verifică: resursa și abonamentul sunt active, cheia "
			"nu a fost regenerată (Keys and Endpoint) și regiunea de la Overview › Location. Apoi pune din nou KEY 1 "
			"și regiunea în Meniu › Setări › Sunet și subtitrări › Traducerea subtitrărilor sau în pagina web "
			"Traducere subtitrări.")
	return _t("Verifică în contul serviciului că cheia e activă și are drept de traducere, apoi pune-o din nou în "
		"Meniu › Setări › Sunet și subtitrări › Traducerea subtitrărilor sau în pagina web Traducere subtitrări.")


def textOprit(serviciu, refuzuri, detaliu=u""):
	"""serviciul oprit dupa refuzurile cheii: ce s-a intamplat (fara ce faci, vezi textCeFaciRefuz)"""
	return _t("%s a refuzat cheia de %d ori la rând (%s): nu o mai folosesc și o încerc singur o dată pe oră.") % (
		numeServiciu(serviciu), refuzuri, detaliu or u"HTTP 401")


def detaliuEroare(cod, date):
	"""codul exact al erorii, pentru „Detalii” (fara cheie, fara adrese): „HTTP 401, cod 401000” sau „HTTP 429,
	RESOURCE_EXHAUSTED”; "" fara cod HTTP"""
	if not cod:
		return u""
	parti = [u"HTTP %d" % cod]
	j = _jsonEroare(date) or {}
	e = j.get("error")
	if isinstance(e, dict):
		if isinstance(e.get("code"), (int, str)) and str(e.get("code")) != str(cod):
			parti.append(u"cod %s" % str(e["code"])[:40])
		if isinstance(e.get("status"), str) and e["status"]:
			parti.append(e["status"][:60])
	elif isinstance(j.get("code"), (int, str)) and str(j.get("code")) != str(cod):
		parti.append(u"cod %s" % str(j["code"])[:40])
	elif eroareCloudflare(j) is not None and eroareCloudflare(j)[0] is not None:
		parti.append(u"cod %s" % str(eroareCloudflare(j)[0])[:40])
	return re.sub(r"https?://\S+", u"", u", ".join(parti))


_GANDURI = re.compile(r"<think>.*?</think>", re.S | re.I)
_NUMAR = re.compile(r"^\s*(?:\*\*)?(\d{1,2})(?:\*\*)?\s*[:.)\]\-](?:\*\*)?\s?(.*)$")
_PREFIXE = re.compile(r"^\s*(translation|traducere|traduction|übersetzung|ubersetzung)\s*:\s*", re.I)


def _faraGhilimele(t):
	t = t.strip()
	for a, b in ((u'"', u'"'), (u"„", u"”"), (u"“", u"”"), (u"«", u"»"), (u"'", u"'")):
		if len(t) >= 2 and t.startswith(a) and t.endswith(b) and t.count(a) <= 2:
			return t[len(a):-len(b)].strip()
	return t


def curataModel(text, n):
	"""raspunsul unui model de limbaj -> n texte (sau un singur text pus pe primul element, celelalte goale)"""
	t = _GANDURI.sub(u"", text or u"")
	t = re.sub(r"^.*?</think>", u"", t, flags=re.S | re.I) if u"</think>" in t.lower() else t
	t = re.sub(r"```[a-zA-Z]*", u"", t).replace(u"```", u"")
	randuri = [r.strip() for r in t.replace(u"\r", u"").split(u"\n")]
	randuri = [r for r in randuri if r and not r.lower().startswith(u"context:") and r.lower() != u"translate:"]
	numerotate = {}
	for r in randuri:
		m = _NUMAR.match(r)
		if m:
			i = int(m.group(1))
			if 1 <= i <= n and i not in numerotate:
				numerotate[i] = _faraGhilimele(_PREFIXE.sub(u"", m.group(2)))
	if len(numerotate) == n:
		return [numerotate[i + 1] for i in range(n)]
	curate = [_faraGhilimele(_PREFIXE.sub(u"", _NUMAR.sub(lambda m: m.group(2), r))) for r in randuri]
	curate = [c for c in curate if c]
	if not curate:
		raise EroareTraducere(E_RASPUNS, _t("Modelul nu a dat nicio traducere."))
	if len(curate) == n:
		return curate
	return [u" ".join(curate)] + [u""] * (n - 1)


def raspunsPropriu(cfg, cod, date):
	"""adresa proprie: raspunsul pentru un rand -> traducerea (spatiile stranse); altfel EroareTraducere, cu
	inceputul corpului raspunsului in mesaj (fara cheie; jurnalul nu primeste mesajul)"""
	cheie = cfg.get("cheie") or u""
	if cod != 200:
		fel = felEroareHttp("propriu", cod, date)
		raise EroareTraducere(fel, _t("Serverul de la adresa ta a răspuns cu eroarea HTTP %d. Începutul răspunsului: "
			"„%s”") % (cod or 0, inceputRaspuns(date, cheie)), cod)
	if cfg.get("raspuns") == "text":
		text = date.decode("utf-8", "replace").lstrip(u"﻿")
	else:
		try:
			j = json.loads(date.decode("utf-8").lstrip(u"﻿"))
		except (ValueError, UnicodeDecodeError):
			raise EroareTraducere(E_RASPUNS, _t("Răspunsul serverului nu e JSON (dacă serverul dă numai traducerea, "
				"alege „Text simplu” la răspuns). Începutul răspunsului: „%s”") % inceputRaspuns(date, cheie), cod)
		cale = cfg.get("cale") or u""
		text = caleJson(j, cale)
		if text is None:
			raise EroareTraducere(E_RASPUNS, _t("Calea „%s” nu găsește nicio traducere în răspunsul serverului. "
				"Începutul răspunsului: „%s”") % (cale, inceputRaspuns(date, cheie)), cod)
	text = u" ".join(text.split())
	if not text:
		raise EroareTraducere(E_RASPUNS, _t("Serverul nu a dat nicio traducere. Începutul răspunsului: „%s”") %
			inceputRaspuns(date, cheie), cod)
	return text


def raspuns(cfg, cod, date, n):
	"""-> lista de n traduceri; altfel EroareTraducere (la propriu n e 1: un rand pe cerere)"""
	serv = cfg["serviciu"]
	if serv == "propriu":
		if n != 1:
			raise EroareTraducere(E_RASPUNS, textEroare(E_RASPUNS, serv, cod), cod)
		rez = [raspunsPropriu(cfg, cod, date)]
		return [r.translate(_VIRGULITE) for r in rez] if cfg.get("tinta") == "ro" else rez
	if cod != 200:
		fel = felEroareHttp(serv, cod, date)
		if serv == "azure" and cod == 401:
			raise EroareTraducere(fel, textRegiuneAzure(bool(cfg.get("regiune"))), cod)
		if cod == 402:
			raise EroareTraducere(fel, _t("%s spune că nu mai e credit în cont (HTTP 402).") % numeServiciu(serv), cod)
		if serv == "cloudflare" and fel == E_LIPSA:
			raise EroareTraducere(fel, _t("Cloudflare Workers nu dă modelul ales din acest cont (HTTP %d): modelul cere "
				"planul plătit sau nu există. Alege alt model, de exemplu %s.") % (cod, MODEL_CLOUDFLARE_IMPLICIT), cod)
		raise EroareTraducere(fel, textEroare(fel, serv, cod), cod)
	try:
		j = json.loads(date.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		raise EroareTraducere(E_RASPUNS, textEroare(E_RASPUNS, serv, cod), cod)
	try:
		if serv == "azure":
			rez = [e["translations"][0]["text"] for e in j]
		elif serv == "google":
			rez = [e["translatedText"] for e in j["data"]["translations"]]
		elif serv == "deepl":
			rez = [e["text"] for e in j["translations"]]
		elif serv == "libre":
			t = j["translatedText"]
			rez = t if isinstance(t, list) else [t]
		elif serv == "gemini":
			cand = j["candidates"][0]
			parti = cand.get("content", {}).get("parts", [])
			text = u"".join(p.get("text", u"") for p in parti if not p.get("thought"))
			rez = curataModel(text, n)
		elif serv in _FORMAT_CHAT:
			rez = curataModel(j["choices"][0]["message"]["content"], n)
		else:
			raise KeyError(serv)
	except (KeyError, IndexError, TypeError, AttributeError):
		raise EroareTraducere(E_RASPUNS, textEroare(E_RASPUNS, serv, cod), cod)
	if len(rez) != n or not all(isinstance(r, str) for r in rez):
		raise EroareTraducere(E_RASPUNS, textEroare(E_RASPUNS, serv, cod), cod)
	if serv == "google":
		rez = [_htmlInapoi(r) for r in rez]
	rez = [u" ".join(r.split()) for r in rez]
	if cfg.get("tinta") == "ro":
		rez = [r.translate(_VIRGULITE) for r in rez]
	return rez


# romana scrisa corect: s si t cu virgula dedesubt, nu cu sedila (unele servicii dau inca ş ţ)
_VIRGULITE = {0x015F: 0x0219, 0x015E: 0x0218, 0x0163: 0x021B, 0x0162: 0x021A}


def _htmlInapoi(t):
	for a, b in ((u"&#39;", u"'"), (u"&quot;", u'"'), (u"&lt;", u"<"), (u"&gt;", u">"), (u"&amp;", u"&")):
		t = t.replace(a, b)
	return t


def traduceAcum(cfg, texte, sursa, tinta, context=(), termen_s=8.0, trimite_=None, fel="subtitrari"):
	"""o cerere intreaga, pe firul apelantului (firele de lucru, probele) -> lista de traduceri; fel "epg" = textele
	ghidului (Components/HdsTraducereEpg.py; numai instructiunea modelelor difera)"""
	lipsa = ceLipseste(cfg)
	if lipsa:
		raise EroareTraducere(E_LIPSA, textCeLipseste(cfg))
	if cfg["serviciu"] == "propriu":
		# un rand pe cerere, pe rand, pe firul apelantului; cheia nu ramane in niciun mesaj de eroare
		rez = []
		try:
			for t in texte:
				adresa, antete, corp = cerere(cfg, [t], sursa, tinta, context, None, fel)
				r = (trimite_ or trimite)(adresa, antete, corp, termen_s)
				cod, date = r
				rez.extend(_cuAsteptarea(raspuns, r, cfg, cod, date, 1))
		except EroareTraducere as e:
			if cfg.get("cheie"):
				e.text = _ascundeCheia(e.text, cfg["cheie"])
				e.args = (e.text,)
			raise
		return rez
	ollama = esteOllama(cfg["adresa"], trimite_) if cfg["serviciu"] == "openai" else None
	adresa, antete, corp = cerere(cfg, texte, sursa, tinta, context, ollama, fel)
	r = (trimite_ or trimite)(adresa, antete, corp, termen_s)
	cod, date = r
	if cod == 400 and cfg["serviciu"] in _FORMAT_CHAT and b'"temperature"' in corp and refuzaTemperatura(cod, date):
		# serverul nu primeste temperature (la acest model): o data fara el, si tinut minte
		_FARA_TEMPERATURA.add(_semnTemperatura(adresa, _modelDinCorp(corp)))
		_jurnal("%s: fara temperature de acum" % cfg["serviciu"])
		adresa, antete, corp = cerere(cfg, texte, sursa, tinta, context, ollama, fel)
		r = (trimite_ or trimite)(adresa, antete, corp, termen_s)
		cod, date = r
	if cod == 400 and (ollama or (cfg["serviciu"] == "groq" and b'"reasoning_effort"' in corp)):
		# un Ollama, un model sau Groq care nu primeste campurile gandirii: o data fara ele
		adresa, antete, corp = cerere(cfg, texte, sursa, tinta, context, False, fel, extra=False)
		r = (trimite_ or trimite)(adresa, antete, corp, termen_s)
		cod, date = r
	if cfg["serviciu"] == "deepl":
		amprenta = _amprenta(cfg.get("cheie") or "")
		if cod == 403:
			alta = DEEPL_PRO if adresa == DEEPL_FREE else DEEPL_FREE
			r_alta = (trimite_ or trimite)(alta, antete, corp, termen_s)
			cod_alta, date_alta = r_alta
			if cod_alta == 200:
				_DEEPL_ADRESA[amprenta] = alta
				r, cod, date = r_alta, cod_alta, date_alta
		elif cod == 200:
			_DEEPL_ADRESA[amprenta] = adresa
	return _cuAsteptarea(raspuns, r, cfg, cod, date, len(texte))


def _cuAsteptarea(functie, r, cfg, cod, date, n):
	"""raspuns(cfg, cod, date, n); la limita atinsa, eroarea primeste asteptarea si felul limitei (asteptareDinRaspuns)"""
	try:
		return functie(cfg, cod, date, n)
	except EroareTraducere as e:
		if e.fel == E_COTA:
			e.asteptare_s, e.pe_zi = asteptareDinRaspuns(cod, getattr(r, "antete", None), date)
		if cod and cod != 200:
			e.detaliu = detaliuEroare(cod, date)
		raise


# ------------------------------------------------------------------ memoria traducerilor (RAM)

class Memorie(object):
	def __init__(self, intrari=MEMORIE_INTRARI, caractere=MEMORIE_CARACTERE):
		self.intrari, self.caractere = intrari, caractere
		self._d = OrderedDict()
		self._litere = 0

	def ia(self, cheie):
		v = self._d.get(cheie)
		if v is not None:
			self._d.move_to_end(cheie)
		return v

	def pune(self, cheie, valoare):
		if cheie in self._d:
			self._litere -= len(cheie[2]) + len(self._d.pop(cheie))
		self._d[cheie] = valoare
		self._litere += len(cheie[2]) + len(valoare)
		while self._d and (len(self._d) > self.intrari or self._litere > self.caractere):
			k, v = self._d.popitem(last=False)
			self._litere -= len(k[2]) + len(v)

	def goleste(self):
		self._d.clear()
		self._litere = 0

	def __len__(self):
		return len(self._d)


def liniiElement(text):
	"""randurile unui element (teletextul lipeste randurile cu spatiu, fisierele le lasa pe randuri), normalizate"""
	return [normalizeaza(l) for l in (text or u"").replace(u"\r", u"").split(u"\n") if l.strip()]


def normalizeaza(text):
	"""textul unui element, cum se cere si cum se tine minte: spatiile stranse, fara randuri noi, taiat la MAX_TEXT"""
	return u" ".join((text or u"").split())[:MAX_TEXT]


# ------------------------------------------------------------------ trezirea pe firul enigma2

class Trezire(object):
	"""pipe + eSocketNotifier (firul enigma2); fara enigma (probele) nu face nimic: probele cheama proceseaza()"""

	def __init__(self, functie):
		self.functie = functie
		self.citire = self.scriere = None
		self.notificator = None
		self.ceas = None
		try:
			from enigma import eSocketNotifier, eTimer
		except Exception:
			return
		try:
			self.citire, self.scriere = os.pipe()
			os.set_blocking(self.citire, False)
			os.set_blocking(self.scriere, False)
			self.notificator = eSocketNotifier(self.citire, 1)
			self.notificator.callback.append(self._peTrezire)
		except Exception as e:
			_jurnal("fara pipe de trezire (%s), rezultatele se iau la ceas" % e)
			self.notificator = None
		self.ceas = eTimer()
		self.ceas.callback.append(self._peCeas)

	def trezeste(self):
		"""de pe orice fir"""
		if self.scriere is not None:
			try:
				os.write(self.scriere, b"x")
			except OSError:
				pass

	def cereCeas(self, da):
		if self.ceas is not None:
			if da:
				if not self.ceas.isActive():
					self.ceas.start(CEAS_SIGURANTA_MS, False)
			else:
				self.ceas.stop()

	def _peTrezire(self, evenimente=None):
		try:
			while os.read(self.citire, 256):
				pass
		except OSError:
			pass
		self.functie()

	def _peCeas(self):
		self.functie()


# ------------------------------------------------------------------ traducatorul

def cheieServiciu(cfg):
	"""primul element al cheii din memorie: serviciul; la propriu si amprenta sablonului (adresa, metoda, corp,
	raspuns, cale), ca dupa o setare reparata randurile sa se ceara din nou"""
	serv = cfg["serviciu"]
	if serv != "propriu":
		return serv
	semn = u"|".join(cfg.get(k) or u"" for k in ("adresa", "metoda", "corp", "tip_corp", "raspuns", "cale"))
	return "propriu:" + hashlib.sha256(semn.encode("utf-8")).hexdigest()[:16]


class Lucrare(object):
	"""o cerere: textele care lipsesc din memorie, pentru o pagina (sau mai multe pagini care asteapta aceleasi texte);
	lant = configuratiile serviciilor in ordinea incercarii (principalul primul, apoi rezervele cu campurile complete)"""

	def __init__(self, cfg, sursa, texte, context, acum, inainte_=False, lant=None):
		self.cfg, self.sursa, self.texte, self.context = cfg, sursa, tuple(texte), tuple(context)
		self.lant = list(lant) if lant else [cfg]
		self.facuta = acum
		self.inainte = inainte_
		self.asteptatori = []		# (generatie, texte_pagina, afisata_la, asteptarea_de_atunci_ms)
		self.cheie = (cheieServiciu(cfg), cfg["tinta"], self.texte)
		self.semn = (cfg["tinta"], sursa, tuple(cheieServiciu(c) for c in self.lant))	# ce se poate lipi intr-o cerere
		# serviciul ales in setari (primul din lant poate fi o rezerva, cand principalului ii lipsesc campuri)
		self.principal = cfg["serviciu"]


class Lot(object):
	"""o cerere trimisa: una sau mai multe lucrari lipite (aceeasi limba, acelasi lant), randurile lor fara dubluri"""

	def __init__(self, lucrari):
		self.lucrari = lucrari
		p = lucrari[0]
		self.lant, self.sursa, self.context = p.lant, p.sursa, p.context
		self.principal = getattr(p, "principal", p.lant[0]["serviciu"])
		texte = []
		for l in lucrari:
			for t in l.texte:
				if t not in texte:
					texte.append(t)
		self.texte = tuple(texte)
		self.cfg = None				# serviciul care a raspuns


class Traducator(object):
	def __init__(self, acum=time.monotonic, trimite_=None, cu_trezire=True):
		self._acum = acum
		self._trimite = trimite_
		self.memorie = Memorie()
		self.lacat = threading.Lock()
		self.coada = deque()
		self.in_lucru = {}			# cheie -> Lucrare (in coada sau la un fir)
		self.fire = 0
		self.probe = 0				# probe in lucru (firul lor e separat)
		self.rezultate = deque()
		self.abandonate = deque()	# generatiile lasate pe fir (pagina prea veche, toate serviciile cazute): renuntarea
		self._grabeste = threading.Event()	# o pagina de pe ecran asteapta: firul nu mai asteapta fereastra lotului
		self.context = deque(maxlen=CONTEXT_RANDURI)
		self.widget = None
		self.pauza_pana = 0.0		# toate serviciile din lant au cazut: nimic nu pleaca pana atunci
		self.blocat = {}			# serviciu -> (pana_la, felul erorii, pe_zi); pana_la None = pana la schimbarea setarilor
		self.caderi = {}			# serviciu -> erori la rand
		self.refuzuri = {}			# serviciu -> refuzuri ale cheii la rand (E_CHEIE), sterse la o reusita
		self.oprite = {}			# serviciu -> {ora, refuzuri, cod, detaliu}: oprit dupa REFUZURI_OPRIRE refuzuri
		self.oprit_spus = set()		# serviciile oprite al caror mesaj s-a aratat (o data, pana la setari schimbate)
		self._asteaptaPornirea = asteaptaPornirea	# probele il inlocuiesc
		self.generatie_afisata = 0	# cea mai noua pagina data de nucleu (numai pentru stare: nicio pagina nu se mai sare)
		self.mesaj_spus = False
		self.lipsa_spusa = False
		self.lent_spus = False
		self._intarziate = 0			# pagini la rand traduse prea tarziu sau sarite (serverul lent)
		self.media_ms = None
		self.ultima_proba = None
		self.sursa = ""
		self.trezire = Trezire(self.proceseaza) if cu_trezire else None
		self.puneContorulLaZero()

	# ------------------------------------------------------------------ contorul
	def puneContorulLaZero(self):
		self.contor = {"pagini": 0, "din_memorie": 0, "la_timp": 0, "dupa_afisare": 0, "sarite": 0,
			"cereri": 0, "randuri": 0, "erori": dict((f, 0) for f in FELURI_EROARE), "ms_max": None,
			"ultima_eroare": None, "ultimele": deque(maxlen=ULTIMELE), "de_la": time.time(),
			"pe_servicii": {}, "pe_rezerva": 0, "treceri": deque(maxlen=TRECERI), "in_asteptare": 0}
		self._ms = deque(maxlen=50)

	# ------------------------------------------------------------------ setarile
	def setariSchimbate(self):
		"""setari sau chei schimbate: pauzele, serviciile oprite si mesajele uitate; memoria ramane (cheia ei are
		serviciul si limba)"""
		with self.lacat:
			self.pauza_pana = 0.0
			self.blocat.clear()
			self.caderi.clear()
			self.refuzuri.clear()
			self.oprite.clear()
		self.oprit_spus.clear()
		self.mesaj_spus = False
		self.lipsa_spusa = False
		self.lent_spus = False
		self._intarziate = 0

	def pauzaRamasa(self):
		return max(0, int(round(self.pauza_pana - self._acum()))) if self.pauza_pana else 0

	def termenMs(self):
		if self.media_ms is None:
			return TERMEN_PORNIRE_MS
		return int(min(TERMEN_MAXIM_MS, max(TERMEN_MINIM_MS, 3 * self.media_ms + 1000)))

	def asteptareMs(self):
		"""termenul din nucleu: cat asteapta cel mult o pagina, cu ecranul gol, traducerea ei (si textul OCR), de la
		momentul ei; apoi originalul cu semn, iar traducerea tarzie nu se mai pune. „Se pune când vine”:
		ASTEPTARE_SIGURANTA_MS (se asteapta traducerea; la o eroare Python renunta singur, pe loc); „Rămâne originalul”:
		ASTEPTARE_MAXIMA_MS. Niciodata 0: originalul nu apare inaintea traducerii, oricat de lent ar fi serviciul."""
		if initConfigSigur("tarziu") == "sare":
			return ASTEPTARE_MAXIMA_MS
		return ASTEPTARE_SIGURANTA_MS

	# ------------------------------------------------------------------ serviciile din lant
	def _liber(self, serv, acum):
		"""serviciul poate primi cereri (nu asteapta dupa o eroare); sub lacat"""
		b = self.blocat.get(serv)
		return b is None or (b[0] is not None and acum >= b[0])

	def _primulLiber(self, lant, acum):
		for c in lant:
			if self._liber(c["serviciu"], acum):
				return c
		return None

	def serviciuLiber(self, serv):
		"""Components/HdsTraducereEpg.py: serviciul nu asteapta dupa o eroare a subtitrarilor"""
		with self.lacat:
			return self._liber(serv, self._acum())

	def ocupat(self):
		"""subtitrarile au cereri in lucru sau in coada (ghidul nu incarca atunci serverul din casa)"""
		with self.lacat:
			return bool(self.coada) or self.fire > 0

	# ------------------------------------------------------------------ paginile
	def laPagina(self, generatie, texte, fel=0, intarziere_ms=-1, cfg=None, rezerve=None):
		"""functia nucleului. -> lista de traduceri (din memorie), True (vine prin setTranslation; fiecare pagina asteptata
		primeste un raspuns, si renuntarea: setTranslation(gen, [])), None (nu se traduce acum: campuri lipsa, pauza
		dupa erori, niciun serviciu liber; nucleul arata originalul cu semn) sau False (fara text, deja in limba tinta:
		originalul curat). cfg / rezerve: configuratia serviciului principal si ale rezervelor (probele); implicit din
		setari."""
		if cfg is None:
			# televizorul stins (dupa driverul HDMI): nimeni nu citeste, deci nimic nu pleaca la serviciu (originalul curat)
			if _tvStins():
				return False
			lant = lantul()
			cfg = lant[0]
		else:
			lant = [cfg] + list(rezerve or ())
		pagina = [liniiElement(t) for t in texte]		# fiecare element: randurile lui (dialogul ramane pe randuri)
		if generatie:
			self.contor["pagini"] += 1
			self.generatie_afisata = generatie
		if not any(pagina):
			return False
		# serviciile cu campuri lipsa nu se folosesc (si principalul fara cheie: lucreaza prima rezerva completa);
		# fiecare serviciu o singura data
		folosite = []
		for r in lant:
			if r["serviciu"] not in [c["serviciu"] for c in folosite] and not ceLipseste(r):
				folosite.append(r)
		if not folosite:
			if generatie and not self.lipsa_spusa:
				self.lipsa_spusa = True
				self._mesaj(_t("Traducerea subtitrărilor nu merge încă. %s Completează în Meniu › Setări › Sunet și "
					"subtitrări › Traducerea subtitrărilor.") % textCeLipseste(cfg))
			return None
		principal = cfg["serviciu"]
		lant = folosite
		cfg = lant[0]
		sursa = self.sursa
		if sursa and sursa == cfg["tinta"]:
			return False		# subtitrarea e deja in limba tinta
		traduse = self._dinMemorie(lant, pagina)
		if traduse is not None:
			if generatie:
				self.contor["din_memorie"] += 1
				self.contor["la_timp"] += 1
				self._intarziate = 0
				self._tineMinte(pagina, traduse, None, u"memorie")
				self._context(pagina)
			return traduse
		if self.pauzaRamasa():
			return None			# pauza dupa erori (de exemplu 429): originalul cu semn, pe loc
		acum = self._acum()
		with self.lacat:
			liber = self._primulLiber(lant, acum)
		if liber is None:
			return None			# toate serviciile din lant asteapta dupa erori
		lipsa = []
		for linii in pagina:
			for l in linii:
				if l not in lipsa and self._randDinMemorie(lant, l) is None:
					lipsa.append(l)
		lucrare = Lucrare(cfg, sursa, lipsa, list(self.context), acum, inainte_=not generatie, lant=lant)
		lucrare.principal = principal
		# nicio pagina asteptata nu se sare (coada nucleului le arata in ordine): numai coada plina (un server foarte
		# lent) lasa lucrarea cea mai veche, iar paginile ei primesc pe loc renuntarea (originalul cu semn)
		coada_max = MAX_COADA
		asteptare = self.asteptareMs()
		lasate = []
		with self.lacat:
			existenta = self.in_lucru.get(lucrare.cheie)
			if existenta is not None:
				lucrare = existenta
			else:
				self.in_lucru[lucrare.cheie] = lucrare
				self.coada.append(lucrare)
				while len(self.coada) > coada_max:
					veche = self.coada.popleft()
					self.in_lucru.pop(veche.cheie, None)
					if veche.asteptatori:
						self.contor["sarite"] += len(veche.asteptatori)
						lasate.extend(a[0] for a in veche.asteptatori)
			if generatie:
				lucrare.asteptatori.append((generatie, pagina, acum, asteptare))
			porneste = self.fire < MAX_IN_ZBOR and bool(self.coada)
			if porneste:
				self.fire += 1
		for g in lasate:
			self._renunta(g)
		if generatie:
			self._context(pagina)
			self._grabeste.set()		# pagina e pe ecran: firul nu mai asteapta fereastra lotului
		if porneste:
			self._pornesteFir()
		if self.trezire is not None:
			self.trezire.cereCeas(True)
		return bool(generatie)

	def _randDinMemorie(self, lant, rand):
		"""traducerea unui rand din memoria oricarui serviciu din lant (in ordinea lantului), sau None"""
		for c in lant:
			v = self.memorie.ia((cheieServiciu(c), c["tinta"], rand))
			if v is not None:
				return v
		return None

	def _dinMemorie(self, lant, pagina):
		"""traducerea paginii (un text pe element, randurile unite cu un rand nou), sau None daca lipseste un rand;
		fiecare rand din memoria oricarui serviciu din lant"""
		if isinstance(lant, dict):
			lant = [lant]
		rez = []
		for linii in pagina:
			traduse = []
			for l in linii:
				v = self._randDinMemorie(lant, l)
				if v is None:
					return None
				traduse.append(v)
			rez.append(u"\n".join(traduse))
		return rez

	def _context(self, pagina):
		t = u" ".join(l for linii in pagina for l in linii)
		if t and (not self.context or self.context[-1] != t):
			self.context.append(t)

	def inainte(self, texte, cfg=None, rezerve=None):
		"""textul gata inainte de afisare (OCR): cererea pleaca acum, nimic nu vine inapoi"""
		try:
			self.laPagina(0, texte, 2, 0, cfg, rezerve)
		except Exception as e:
			_jurnal("inainte: %s" % e)

	# ------------------------------------------------------------------ firele
	def _pornesteFir(self):
		t = threading.Thread(target=self._fir, name="HdsTraducere")
		t.daemon = True
		t.start()

	def _curataCoada(self, acum):
		"""sub lacat: scoate din coada ce nu mai merita trimis (pagina prea veche, cerere din timp prea veche) sau nu are
		niciun serviciu liber; paginile asteptate de nucleu ale lucrarilor scoase primesc renuntarea (abandonate, pe
		firul enigma2 in proceseaza); memoria ramane"""
		pastrate = deque()
		while self.coada:
			l = self.coada.popleft()
			if self._mergeTrimisa(l, acum) and self._primulLiber(l.lant, acum) is not None:
				pastrate.append(l)
				continue
			self.in_lucru.pop(l.cheie, None)
			if l.asteptatori:
				self.contor["sarite"] += len(l.asteptatori)
				self.abandonate.extend(a[0] for a in l.asteptatori)
				if serverDinCasa(l.cfg):
					self._intarziate += 1		# serverul din casa nu tine pasul cu subtitrarile
		self.coada = pastrate

	def _iaLot(self, acum):
		"""sub lacat: prima lucrare din coada si cele care se pot lipi de ea (aceeasi limba, acelasi lant), cel mult
		MAX_RANDURI_CERERE randuri -> Lot sau None"""
		self._curataCoada(acum)
		if not self.coada:
			return None
		luate, randuri, pastrate = [], [], deque()
		while self.coada:
			l = self.coada.popleft()
			noi = [t for t in l.texte if t not in randuri]
			if not luate or (l.semn == luate[0].semn and len(randuri) + len(noi) <= MAX_RANDURI_CERERE):
				luate.append(l)
				randuri.extend(noi)
			else:
				pastrate.append(l)
		self.coada = pastrate
		return Lot(luate)

	def _fir(self):
		fereastra = FEREASTRA_LOT_MS / 1000.0
		while True:
			lot = None
			try:
				# o data pe pornire: reteaua si ceasul (cel mult PORNIRE_ASTEPTARE_S); paginile ramase prea vechi intre
				# timp le scoate _curataCoada, cu renuntarea
				self._asteaptaPornirea()
				with self.lacat:
					acum = self._acum()
					self._curataCoada(acum)
					trezeste = bool(self.abandonate)
					gata = not self.coada
					if gata:
						self.fire -= 1
					else:
						primul = self.coada[0]
						# o cerere din timp asteapta putin, ca randurile venite intre timp sa plece impreuna; pagina de pe
						# ecran nu (si o pagina venita pe ecran in timpul asteptarii trezeste firul)
						ramas = 0 if primul.asteptatori else primul.facuta + fereastra - acum
				if trezeste and self.trezire is not None:
					self.trezire.trezeste()		# renuntarile ajung la nucleu pe firul enigma2 (proceseaza)
				if gata:
					return
				if ramas > 0:
					# un semn ramas de la o pagina de dinainte nu scurteaza fereastra cererii din timp de acum (unul venit
					# intre clear si wait se pierde fara rau: pagina pleaca oricum la sfarsitul ferestrei)
					self._grabeste.clear()
					self._grabeste.wait(min(ramas, fereastra))
				with self.lacat:
					lot = self._iaLot(self._acum())
				if lot is None:
					continue
				iesire = self._trimiteLot(lot)
			except Exception as e:
				# firul (unul singur) nu are voie sa moara cu fire = 1: traducerea s-ar opri pana la repornire
				_jurnal("firul traducerii: %s" % e.__class__.__name__)
				if lot is None:
					with self.lacat:
						self.fire -= 1
						for l in list(self.coada):
							self.in_lucru.pop(l.cheie, None)
							self.abandonate.extend(a[0] for a in l.asteptatori)	# renuntarea, pe firul enigma2
						self.coada.clear()
					if self.trezire is not None:
						self.trezire.trezeste()
					return
				iesire = (lot, None, EroareTraducere(E_RASPUNS, str(e)[:120]), 0, {})
			with self.lacat:
				self.rezultate.append(iesire)
			if self.trezire is not None:
				self.trezire.trezeste()

	def _trimiteLot(self, lot):
		"""pe fir: lotul la primul serviciu liber din lant; la o eroare din FELURI_TRECERE serviciul cazut asteapta
		(durataBlocarii) si cererea trece pe loc la urmatorul serviciu liber. -> (lot, rez, eroare, ms, info)"""
		info = {"treceri": [], "erori": [], "mesaj": None, "minute": 0, "pe_zi": None, "oprite": [], "revenite": []}
		eroare = None
		incercat = False
		for i, cfg in enumerate(lot.lant):
			serv = cfg["serviciu"]
			with self.lacat:
				if not self._liber(serv, self._acum()):
					continue
			incercat = True
			inceput = self._acum()
			try:
				rez = traduceAcum(cfg, list(lot.texte), lot.sursa, cfg["tinta"], lot.context, self.termenMs() / 1000.0,
					self._trimite)
			except EroareTraducere as e:
				eroare = e
			except Exception as e:
				eroare = EroareTraducere(E_RASPUNS, str(e)[:120])
			else:
				with self.lacat:
					self.caderi.pop(serv, None)
					self.blocat.pop(serv, None)
					self.refuzuri.pop(serv, None)
					if self.oprite.pop(serv, None) is not None:
						info["revenite"].append(serv)
				lot.cfg = cfg
				return (lot, rez, None, int((self._acum() - inceput) * 1000), info)
			info["erori"].append((cfg, eroare))
			with self.lacat:
				acum = self._acum()
				self.caderi[serv] = self.caderi.get(serv, 0) + 1
				refuzuri = 1
				if eroare.fel == E_CHEIE:
					refuzuri = self.refuzuri[serv] = self.refuzuri.get(serv, 0) + 1
				urmator = None
				for c in lot.lant[i + 1:]:
					if self._liber(c["serviciu"], acum):
						urmator = c
						break
				durata = durataBlocarii(eroare, serv, urmator is not None, self.caderi[serv], refuzuri)
				if durata is None or durata > 0:
					self.blocat[serv] = (None if durata is None else acum + durata, eroare.fel, bool(eroare.pe_zi))
				if eroare.fel == E_CHEIE and opritDupaRefuzuri(refuzuri) and serv not in self.oprite:
					self.oprite[serv] = {"ora": time.strftime("%H:%M:%S"), "refuzuri": refuzuri, "cod": eroare.cod,
						"detaliu": getattr(eroare, "detaliu", u"") or (u"HTTP %d" % eroare.cod if eroare.cod else u"")}
					info["oprite"].append(serv)
				if eroare.fel == E_COTA and eroare.pe_zi:
					info["pe_zi"] = serv
				if urmator is None or not treceLaUrmatorul(eroare) or durata == 0:
					break
				info["treceri"].append({"ora": time.strftime("%H:%M:%S"), "de_la": serv, "la": urmator["serviciu"],
					"motiv": eroare.fel, "pe_zi": bool(eroare.pe_zi)})
		with self.lacat:
			acum = self._acum()
			if incercat and self._primulLiber(lot.lant, acum) is None:
				# toate serviciile din lant au cazut: regulile vechi (pauza, mesajul o data)
				ramase = [b[0] - acum for b in (self.blocat.get(c["serviciu"]) for c in lot.lant) if b and b[0] is not None]
				pauza = min(ramase) if ramase else PAUZA_S
				self.pauza_pana = acum + pauza
				for l in list(self.coada):
					self.in_lucru.pop(l.cheie, None)
					# paginile care asteptau in coada nu se mai traduc: renuntarea (originalul cu semn, pe loc)
					self.abandonate.extend(a[0] for a in l.asteptatori)
				self.coada.clear()
				motive = [self.blocat.get(c["serviciu"]) for c in lot.lant]
				if info["pe_zi"]:
					info["mesaj"] = "zi"
				elif all(m and m[1] == E_COTA and not m[2] for m in motive):
					info["mesaj"] = None		# numai limite pe minut: o pauza scurta, fara mesaj
				elif not ramase:
					info["mesaj"] = "setari"
				else:
					info["mesaj"] = "minute"
					info["minute"] = max(1, int(round(pauza / 60.0)))
		if not incercat:
			info["netrimis"] = True
		return (lot, None, eroare, 0, info)

	def _mergeTrimisa(self, l, acum):
		"""o pagina asteptata pleaca oricand e inca ceruta (nucleul le arata pe toate, in ordine: una inlocuita pe ecran
		de alta mai noua nu se mai sare), cat timp nu e mai veche de PAGINA_VECHE_S; o cerere din timp, INAINTE_VECHE_S"""
		if l.asteptatori:
			return any(acum - a[2] < PAGINA_VECHE_S for a in l.asteptatori)
		return acum - l.facuta < INAINTE_VECHE_S

	def asteapta(self, termen_s=5.0):
		"""probele: pana cand nu mai e nimic in lucru, apoi proceseaza()"""
		sfarsit = time.monotonic() + termen_s
		while time.monotonic() < sfarsit:
			with self.lacat:
				gata = not self.coada and self.fire == 0 and self.probe == 0
			if gata:
				break
			time.sleep(0.01)
		self.proceseaza()

	# ------------------------------------------------------------------ rezultatele (firul enigma2)
	def _renuntaLaAbandonate(self):
		"""firul enigma2: paginile lasate pe fir (_curataCoada, toate serviciile cazute) primesc renuntarea"""
		with self.lacat:
			lasate = list(self.abandonate)
			self.abandonate.clear()
		for g in lasate:
			self._renunta(g)

	def proceseaza(self):
		self._renuntaLaAbandonate()
		while True:
			with self.lacat:
				if not self.rezultate:
					gol = not self.coada and self.fire == 0 and self.probe == 0 and not self.abandonate
					break
				lot, rez, eroare, ms, info = self.rezultate.popleft()
				if lot is not _PROBA:
					for l in lot.lucrari:
						if self.in_lucru.get(l.cheie) is l:
							self.in_lucru.pop(l.cheie, None)
			if lot is _PROBA:
				self._gataProba(rez, eroare, ms, info)
				continue
			if info.get("netrimis"):
				# niciun serviciu liber cand a venit randul lotului: paginile lui nu se mai traduc
				self._raspundePaginilor(lot)
				continue
			self.contor["cereri"] += 1
			for cfg, e in info.get("erori", ()):
				self._numaraEroarea(cfg, e)
			for tr in info.get("treceri", ()):
				self.contor["treceri"].append(tr)
				_jurnal("trecere de la %s la %s (%s)" % (tr["de_la"], tr["la"], tr["motiv"]))
			for serv in info.get("revenite", ()):
				_jurnal("%s merge din nou (cheia nu mai e refuzata)" % serv)
				self.oprit_spus.discard(serv)
			for serv in info.get("oprite", ()):
				self._spuneOprit(serv)
			if eroare is None:
				self._reusita(lot, rez, ms)
			else:
				self._eroare(lot, eroare, info)
		self._renuntaLaAbandonate()
		if gol and self.trezire is not None:
			self.trezire.cereCeas(False)

	def _renunta(self, generatie):
		"""nucleul nu mai asteapta traducerea paginii: originalul ei, cu semnul (setTranslation cu lista goala)"""
		w = self.widget
		if w is None or not generatie:
			return
		try:
			w.setTranslation(generatie, [])
		except Exception as e:
			_jurnal("setTranslation: %s" % e)

	def _raspundePaginilor(self, lot):
		"""lotul nu s-a tradus: paginile lui primesc traducerea din memorie, daca a venit intre timp pe alt drum, altfel
		renuntarea"""
		for l in lot.lucrari:
			for generatie, pagina, _afisata, _asteptare in l.asteptatori:
				traduse = self._dinMemorie(l.lant, pagina)
				if traduse is not None:
					self._puneInNucleu(generatie, traduse)
				else:
					self._renunta(generatie)

	def _reusita(self, lot, rez, ms):
		self.mesaj_spus = False
		self._ms.append(ms)
		self.media_ms = ms if self.media_ms is None else 0.8 * self.media_ms + 0.2 * ms
		self.contor["ms_max"] = ms if self.contor["ms_max"] is None else max(self.contor["ms_max"], ms)
		self.contor["randuri"] += len(rez)
		cfg = lot.cfg
		serv = cfg["serviciu"]
		ps = self.contor["pe_servicii"]
		ps[serv] = ps.get(serv, 0) + len(rez)
		if serv != lot.principal:
			self.contor["pe_rezerva"] += 1
		sv = cheieServiciu(cfg)
		for t, tr in zip(lot.texte, rez):
			self.memorie.pune((sv, cfg["tinta"], t), tr)
		self._puneAsteptarea()
		acum = self._acum()
		for lucrare in lot.lucrari:
			for generatie, pagina, afisata, asteptare in lucrare.asteptatori:
				traduse = self._dinMemorie(lucrare.lant, pagina)
				if traduse is None:
					self._renunta(generatie)		# un rand fara traducere (nu se intampla): originalul cu semn
					continue
				intarziere = int((acum - afisata) * 1000)
				if intarziere > asteptare + 100:
					# termenul nucleului a trecut: acolo e deja originalul cu semn, iar traducerea nu se pune peste el
					# (ramane in memorie pentru o repetare)
					self.contor["sarite"] += 1
					self._tineMinte(pagina, traduse, ms, u"sarita")
					self._intarziate = self._intarziate + 1 if intarziere > INTARZIERE_LENTA_MS else 0
					continue
				# a venit cat ecranul astepta gol: originalul nu s-a vazut
				self.contor["la_timp"] += 1
				self.contor["in_asteptare"] += 1
				self._tineMinte(pagina, traduse, ms, u"serviciu" if serv == lot.principal else u"rezerva")
				self._puneInNucleu(generatie, traduse)
				self._intarziate = self._intarziate + 1 if intarziere > INTARZIERE_LENTA_MS else 0
		self._spuneDacaELent()

	def _spuneDacaELent(self):
		"""multe pagini la rand traduse prea tarziu (sau sarite): un mesaj o singura data, cu sfatul"""
		if self._intarziate >= PAGINI_LENTE and not self.lent_spus:
			self.lent_spus = True
			medie = int(self.media_ms or 0)
			_jurnal("traducerea vine prea tarziu (media %d ms)" % medie)
			self._mesaj(_t("Traducerea subtitrărilor vine prea târziu: serverul răspunde în %s, în medie. Alege un "
				"serviciu din internet (Gemini, gratuit, fără card) sau un model mai mic.") % (
				(u"%.1f s" % (medie / 1000.0)).replace(".", ",")))

	def _numaraEroarea(self, cfg, eroare):
		fel = eroare.fel if eroare.fel in FELURI_EROARE else E_RASPUNS
		self.contor["erori"][fel] += 1
		self.contor["ultima_eroare"] = {"fel": fel, "text": eroare.text, "cod": eroare.cod,
			"ora": time.strftime("%H:%M:%S"), "serviciu": cfg["serviciu"], "detaliu": getattr(eroare, "detaliu", u"")}
		_jurnal("%s: eroare %s%s" % (cfg["serviciu"], fel, (" (HTTP %s)" % eroare.cod) if eroare.cod else ""))

	def _eroare(self, lot, eroare, info=None):
		"""toate incercarile lotului au cazut (contorul e facut in _numaraEroarea); mesajul pe televizor numai cand
		toate serviciile din lant asteapta, o singura data. Paginile lotului primesc pe loc renuntarea (originalul cu
		semn), nu asteapta termenul nucleului."""
		info = info or {}
		self._raspundePaginilor(lot)
		fel = eroare.fel if eroare.fel in FELURI_EROARE else E_RASPUNS
		if fel == E_TERMEN and any(l.asteptatori for l in lot.lucrari):
			self._intarziate += 1
			self._spuneDacaELent()
		fel_mesaj = info.get("mesaj")
		if info.get("oprite"):
			# mesajul serviciului oprit dupa refuzurile cheii (_spuneOprit) spune deja ce s-a intamplat si ce faci
			self.mesaj_spus = True
			return
		if not fel_mesaj or self.mesaj_spus:
			return
		self.mesaj_spus = True
		if fel_mesaj == "zi":
			text = _t("%s a ajuns la limita gratuită pe zi (sau pe lună).") % numeServiciu(info["pe_zi"]) + u" " + \
				_t("Traducerea s-a oprit până se reînnoiește limita. Ca să meargă și atunci, pune servicii de rezervă în "
				"Meniu › Setări › Sunet și subtitrări › Traducerea subtitrărilor.")
			if "azure" not in [c["serviciu"] for c in lot.lant]:
				text += u" " + _t("De exemplu Azure Translator: Free F0, 2.000.000 de caractere pe lună, gratuit.")
		elif fel_mesaj == "setari":
			text = _t("Traducerea subtitrărilor s-a oprit până schimbi setările: %s") % eroare.text
		elif (info.get("minute") or 1) == 1:
			text = _t("Traducerea subtitrărilor s-a oprit un minut: %s") % eroare.text
		else:
			text = _t("Traducerea subtitrărilor s-a oprit %d minute: %s") % (info["minute"], eroare.text)
		self._mesaj(text)

	def _spuneOprit(self, serv):
		"""firul enigma2: serviciul tocmai oprit dupa refuzurile cheii: jurnalul si mesajul pe televizor, o singura data
		(pana la setari schimbate sau pana merge din nou)"""
		o = self.oprite.get(serv)
		if o is None:
			return
		_jurnal("%s oprit: cheia refuzata de %d ori la rand (%s); se reincearca o data pe ora" % (serv, o["refuzuri"],
			o.get("detaliu") or "?"))
		if serv in self.oprit_spus:
			return
		self.oprit_spus.add(serv)
		self._mesaj(textOprit(serv, o["refuzuri"], o.get("detaliu")) + u" " + textCeFaciRefuz(serv))

	def opriteLista(self, lant=None):
		"""serviciile oprite dupa refuzurile cheii, in ordinea lantului (cele din afara lui la sfarsit), pentru web si
		ecran: [{serviciu, nume, ora, refuzuri, detaliu, text, ce_faci, reincearca_s}], fara chei"""
		with self.lacat:
			oprite = dict((k, dict(v)) for k, v in self.oprite.items())
			blocat = dict(self.blocat)
		ordine = [c["serviciu"] for c in (lant or [])]
		ordine += sorted(k for k in oprite if k not in ordine)
		acum = self._acum()
		rez = []
		for serv in ordine:
			o = oprite.get(serv)
			if o is None:
				continue
			b = blocat.get(serv)
			ramas = int(round(b[0] - acum)) if b and b[0] is not None and b[0] > acum else 0
			rez.append({"serviciu": serv, "nume": numeServiciu(serv), "ora": o.get("ora"), "refuzuri": o["refuzuri"],
				"detaliu": o.get("detaliu") or u"", "text": textOprit(serv, o["refuzuri"], o.get("detaliu")),
				"ce_faci": textCeFaciRefuz(serv), "reincearca_s": ramas})
		return rez

	def _puneAsteptarea(self):
		w = self.widget
		if w is not None:
			try:
				w.setTranslationWait(self.asteptareMs())
			except Exception:
				pass

	def _puneInNucleu(self, generatie, traduse):
		w = self.widget
		if w is None:
			return
		try:
			w.setTranslation(generatie, traduse)
		except Exception as e:
			_jurnal("setTranslation: %s" % e)

	def _tineMinte(self, pagina, traduse, ms, de_unde):
		self.contor["ultimele"].append({"ora": time.strftime("%H:%M:%S"),
			"original": u" / ".join(l for linii in pagina for l in linii),
			"traducere": u" / ".join(t.replace(u"\n", u" / ") for t in traduse if t), "ms": ms, "de_unde": de_unde})

	def _mesaj(self, text):
		_jurnal("mesaj pe televizor")
		try:
			from Tools import Notifications
			from Screens.MessageBox import MessageBox
			Notifications.AddPopup(text, MessageBox.TYPE_INFO, secundeMesaj(text), "HdsTraducereSubtitrari")
		except Exception as e:
			_jurnal("mesajul nu s-a putut arata: %s" % e)

	# ------------------------------------------------------------------ proba
	def proba(self, laRezultat=None, cfg=None):
		"""„Probează traducerea”: o fraza de proba trimisa serviciului ales, pe un fir separat; laRezultat(dict) pe
		firul enigma2. Intoarce False daca nu se poate porni (campuri lipsa: raspunsul vine pe loc). O proba deodata:
		cat una e in lucru (de pe televizor sau din web), alta nu porneste; raspunsul ei ajunge si la cel nou. Proba
		incearca numai serviciul ales (nu trece la rezerve)."""
		with self.lacat:
			in_lucru = self.probe > 0
		if in_lucru and self.ultima_proba is not None:
			vechi = self.ultima_proba.get("laRezultat")
			if laRezultat is not None and laRezultat is not vechi:
				def ambele(rez, a=vechi, b=laRezultat):
					for f in (a, b):
						if f is not None:
							f(rez)
				self.ultima_proba["laRezultat"] = ambele
			return True
		cfg = cfg or configuratia()
		texte, sursa = frazaProba(cfg["tinta"])
		self.ultima_proba = {"stare": "lucru", "original": u" ".join(texte), "traducere": u"", "ms": None,
			"serviciu": numeServiciu(cfg["serviciu"]), "ora": time.strftime("%H:%M:%S"), "laRezultat": laRezultat}
		lipsa = textCeLipseste(cfg)
		if lipsa:
			self._gataProba(None, EroareTraducere(E_LIPSA, lipsa), None)
			return False
		termen = TERMEN_MAXIM_MS / 1000.0

		def lucru():
			inceput = self._acum()
			try:
				rez = traduceAcum(cfg, texte, sursa, cfg["tinta"], (), termen, self._trimite)
				iesire = (_PROBA, rez, None, int((self._acum() - inceput) * 1000), None)
			except EroareTraducere as e:
				gasita, toate = None, False
				if cfg["serviciu"] == "azure" and e.cod == 401:
					gasita, toate = self._cautaRegiunea(cfg, texte, sursa)
				if gasita is not None:
					regiune, rez, ms = gasita
					iesire = (_PROBA, rez, None, ms, {"regiune": regiune})
				else:
					if cfg["serviciu"] == "azure" and e.cod == 401:
						# toate regiunile refuzate: cheia sau resursa (abonamentul), nu regiunea; altfel cautarea s-a
						# oprit la alta eroare si ramane mesajul cu cheia sau regiunea
						e.text = textAzureToateRegiunile() if toate else textRegiuneAzure(True)
						e.args = (e.text,)
					iesire = (_PROBA, None, e, int((self._acum() - inceput) * 1000), None)
			except Exception as e:
				iesire = (_PROBA, None, EroareTraducere(E_RASPUNS, str(e)[:120]), None, None)
			with self.lacat:
				self.rezultate.append(iesire)
				self.probe -= 1
			if self.trezire is not None:
				self.trezire.trezeste()

		with self.lacat:
			self.probe += 1
		t = threading.Thread(target=lucru, name="HdsTraducereProba")
		t.daemon = True
		t.start()
		if self.trezire is not None:
			self.trezire.cereCeas(True)
		return True

	def _cautaRegiunea(self, cfg, texte, sursa):
		"""pe firul probei: Azure a refuzat cheia (401): se incearca Global si regiunile din REGIUNI_AZURE (cereri scurte,
		nimic in jurnal despre cheie) -> ((regiune, traducerea, ms) la prima care merge, sau None; toate): toate = True
		cand fiecare regiune a raspuns tot 401 (cheia sau resursa sunt de vina, nu regiunea)"""
		incercate = 0
		for cod, nume in REGIUNI_AZURE:
			if cod == (cfg.get("regiune") or ""):
				continue
			inceput = self._acum()
			try:
				rez = traduceAcum(dict(cfg, regiune=cod), texte, sursa, cfg["tinta"], (), TERMEN_REGIUNE_S, self._trimite)
			except EroareTraducere as e:
				if e.cod != 401:
					_jurnal("proba: cautarea regiunii oprita la %s%s" % (e.fel,
						(" (HTTP %s)" % e.cod) if e.cod else ""))
					return None, False		# alta eroare (retea, cota): nu mai are rost
				incercate += 1
				continue
			except Exception:
				return None, False
			_jurnal("proba: regiunea Azure gasita")
			return (cod, rez, int((self._acum() - inceput) * 1000)), False
		_jurnal("proba: Azure refuza cheia in toate cele %d regiuni incercate" % (incercate + 1))
		return None, incercate > 0

	def _puneRegiunea(self, regiune):
		"""pe firul enigma2: regiunea gasita la proba, pusa in setari si salvata"""
		try:
			s = initConfig()
			s.regiune.value = regiune
			s.regiune.save()
			from Components.config import configfile
			configfile.save()
		except Exception as e:
			_jurnal("regiunea nu s-a salvat: %s" % e)

	def _gataProba(self, rez, eroare, ms, info=None):
		p = self.ultima_proba or {}
		if eroare is None:
			p.update({"stare": "ok", "traducere": u" ".join(rez), "ms": ms})
			if info and info.get("regiune") is not None:
				regiune = info["regiune"]
				self._puneRegiunea(regiune)
				nume = dict(REGIUNI_AZURE).get(regiune, regiune)
				p["regiune_gasita"] = regiune
				p["nota"] = _t("Am găsit regiunea: %s (%s).") % (regiune or u"global", nume)
			self.setariSchimbate()
			if ms is not None:
				self.media_ms = ms if self.media_ms is None else 0.8 * self.media_ms + 0.2 * ms
		else:
			p.update({"stare": "eroare", "traducere": eroare.text, "ms": ms, "fel": eroare.fel,
				"detaliu": getattr(eroare, "detaliu", u"") or u""})
			_jurnal("proba: eroare %s%s" % (eroare.fel, (" (HTTP %s)" % eroare.cod) if eroare.cod else ""))
		self.ultima_proba = p
		f = p.get("laRezultat")
		if f is not None:
			try:
				f(dict((k, v) for k, v in p.items() if k != "laRezultat"))
			except Exception as e:
				_jurnal("proba: %s" % e)

	# ------------------------------------------------------------------ starea
	def stareLant(self, lant=None):
		"""serviciile din lant, in ordine, fara chei: [{serviciu, nume, rezerva, lipsa, lipsa_text, folosit, stare
		("merge", "asteapta", "refuzat" = oprit dupa refuzurile cheii, se reincearca singur o data pe ora, "setari" =
		pana la schimbarea setarilor, "lipsa" = campuri lipsa), asteapta_s, motiv, pe_zi, refuzuri (la rand), text si
		ce_faci (la "refuzat")}]"""
		lant = lant if lant is not None else lantul()
		acum = self._acum()
		rez = []
		with self.lacat:
			blocat = dict(self.blocat)
			refuzuri = dict(self.refuzuri)
			oprite = dict((k, dict(v)) for k, v in self.oprite.items())
		for i, c in enumerate(lant):
			serv = c["serviciu"]
			lipsa = ceLipseste(c)
			b = blocat.get(serv)
			if lipsa:
				st, ramas = "lipsa", None
			elif b is not None and b[0] is None:
				st, ramas = "setari", None
			elif serv in oprite:
				st, ramas = "refuzat", int(round(b[0] - acum)) if b is not None and acum < b[0] else 0
			elif b is not None and acum < b[0]:
				st, ramas = "asteapta", int(round(b[0] - acum))
			else:
				st, ramas = "merge", None
			x = {"serviciu": serv, "nume": numeServiciu(serv), "rezerva": i > 0,
				"lipsa": lipsa, "lipsa_text": textCeLipseste(c) if lipsa else u"", "folosit": not lipsa, "stare": st,
				"asteapta_s": ramas, "motiv": b[1] if b and st in ("asteapta", "setari", "refuzat") else None,
				"pe_zi": bool(b and b[2] and st == "asteapta"), "refuzuri": refuzuri.get(serv, 0)}
			if st == "refuzat":
				o = oprite[serv]
				x["text"] = textOprit(serv, o["refuzuri"], o.get("detaliu"))
				x["ce_faci"] = textCeFaciRefuz(serv)
				x["detaliu"] = o.get("detaliu") or u""
				x["refuzuri_oprire"] = o["refuzuri"]		# cate refuzuri l-au oprit (refuzuri creste la reverificari)
			rez.append(x)
		return rez

	def stare(self):
		s = initConfig()
		lant = lantul(s)
		cfg = lant[0]
		c = self.contor
		ms = list(self._ms)
		proba = dict((k, v) for k, v in (self.ultima_proba or {}).items() if k != "laRezultat") or None
		servicii = self.stareLant(lant)
		lucreaza = u""
		if not self.pauzaRamasa():
			for x in servicii:
				if x["stare"] == "merge":
					lucreaza = x["serviciu"]
					break
		tv_stins = _tvStins()
		return {
			"pornit": bool(s.pornit.value),
			# televizorul stins: nimic nu se traduce (laPagina), deci contorul sta; fraza pentru ecran si web
			"tv_stins": tv_stins,
			"tv_stins_text": _t(TEXT_TV_STINS) if tv_stins else u"",
			"serviciu": cfg["serviciu"],
			"serviciu_nume": numeServiciu(cfg["serviciu"]),
			"rezerve": rezerve(s),
			"lant": servicii,
			"lucreaza": lucreaza,
			"lucreaza_nume": numeServiciu(lucreaza) if lucreaza else u"",
			"tinta": cfg["tinta"],
			"tinta_nume": numeLimba(cfg["tinta"]),
			"lipsa": ceLipseste(cfg),
			"lipsa_text": textCeLipseste(cfg),
			"chei": chei().stare(),
			"pauza_s": self.pauzaRamasa(),
			"memorie": len(self.memorie),
			"media_ms": int(self.media_ms) if self.media_ms is not None else None,
			"asteptare_ms": self.asteptareMs(),
			"citire": dict(zip(("baza_ms", "pe_semn_ms", "minim_ms", "maxim_ms"), timpCitire(s))),
			"termen_ms": self.termenMs(),
			"contor": {
				"pagini": c["pagini"], "din_memorie": c["din_memorie"], "la_timp": c["la_timp"],
				"dupa_afisare": c["dupa_afisare"], "sarite": c["sarite"], "cereri": c["cereri"],
				"randuri": c["randuri"], "erori": dict(c["erori"]), "ms_max": c["ms_max"],
				"ms_mediu": int(sum(ms) / len(ms)) if ms else None,
				"ultima_eroare": c["ultima_eroare"], "ultimele": list(c["ultimele"])[::-1], "de_la": c["de_la"],
				"pe_servicii": dict(c["pe_servicii"]), "pe_rezerva": c["pe_rezerva"], "in_asteptare": c["in_asteptare"],
				"treceri": [dict(t) for t in c["treceri"]][::-1],
			},
			"proba": proba,
			"oprite": self.opriteLista(lant),
		}


_PROBA = object()

MESAJ_MINIM_S = 10
MESAJ_MAXIM_S = 30
MESAJ_SEMNE_PE_S = 25         # un mesaj lung sta mai mult pe ecran: o secunda in plus la atatea semne


def secundeMesaj(text):
	"""cat sta pe ecran un mesaj al traducerii (se inchide si cu OK): MESAJ_MINIM_S, plus o secunda la
	MESAJ_SEMNE_PE_S semne, cel mult MESAJ_MAXIM_S"""
	return min(MESAJ_MAXIM_S, MESAJ_MINIM_S + len(text or u"") // MESAJ_SEMNE_PE_S)

_FRAZE_PROBA = {
	"en": ([u"Good evening.", u"Tomorrow will be sunny, with a light wind from the north."], "en"),
	"de": ([u"Guten Abend.", u"Morgen wird es sonnig, mit leichtem Wind aus Norden."], "de"),
}


def frazaProba(tinta):
	"""fraza de proba: engleza, sau germana cand limba tinta e engleza -> (texte, sursa)"""
	return _FRAZE_PROBA["de"] if tinta == "en" else _FRAZE_PROBA["en"]


def initConfigSigur(camp):
	try:
		return getattr(initConfig(), camp).value
	except Exception:
		return None


# ------------------------------------------------------------------ instructiunile si confidentialitatea

# Pentru fiecare serviciu: pasii prin care omul isi face contul si cheia gratuita, cota gratuita, ce se intampla la
# depasire, data verificarii pe pagina oficiala (verificat; implicit VERIFICAT) si pagina; pagina_cheie = adresa
# oficiala unde omul isi face cheia sau instaleaza serverul (codul QR de pe televizor; "" = fara cod). Aceleasi texte pe
# televizor (Screens/HdsTraducereSubtitrari.py) si in web (traducere_subtitrari_web.py).
VERIFICAT = "03.10.2026"
# pasi comuni serverelor din casa (LibreTranslate, compatibil OpenAI)
_PAS_CAUTA = N_("Cel mai simplu: pornește serverul pe calculator (pașii de mai jos), apoi apasă „Caută în rețeaua de "
	"acasă”, pe televizor sau pe telefon. Receptorul găsește singur serverul; nu mai trebuie să scrii adresa.")
_PAS_PARAVAN = N_("Prima dată, Windows poate întreba dacă lași programul să primească conexiuni din rețea: apasă „Allow "
	"access”. Dacă receptorul tot nu găsește serverul: Windows Security, Firewall & network protection, „Allow an app "
	"through firewall”, „Change settings” și bifează programul (Ollama, LM Studio sau Docker) la „Private”. Rețeaua de "
	"acasă trebuie să fie „Private network” (Settings, Network & internet, rețeaua ta, „Network profile type”).")
INSTRUCTIUNI = {
	"azure": {
		"pasi": (
			N_("Intră pe azure.microsoft.com și apasă „Try Azure for free”. Te înscrii cu un cont Microsoft; Microsoft "
				"cere un număr de telefon și un card, numai pentru verificare."),
			N_("Intră pe portal.azure.com, caută „Translator” în bara de sus și începe o resursă nouă („Create”)."),
			N_("La „Resource group” apasă „Create new” și scrie orice nume. La „Region” alege „Global”, la „Name” scrie "
				"un nume al tău, iar la „Pricing tier” alege „Free F0”."),
			N_("Apasă „Review + create”, apoi „Create”. Când e gata, apasă „Go to resource”."),
			N_("În stânga alege „Keys and Endpoint” și copiază „KEY 1”. Dacă nu ai ales „Global”, notează și regiunea "
				"(de exemplu westeurope)."),
			N_("Pune cheia aici (și regiunea, dacă resursa nu e „Global”)."),
			N_("În primele 30 de zile trece abonamentul pe „Pay as you go”, altfel Microsoft oprește contul gratuit. "
				"Resursa „Free F0” rămâne gratuită."),
		),
		"cota": N_("2.000.000 de caractere pe lună, gratuit (Free F0). E alegerea recomandată pentru subtitrări multe "
			"(filme întregi, în fiecare zi), ca serviciu principal sau de rezervă. Cardul se cere la înscriere numai "
			"pentru verificare; pe Free F0 nu se plătește nimic. După 30 de zile contul trebuie trecut pe „Pay as you "
			"go”, tot fără cost cât resursa rămâne Free F0."),
		"depasire": N_("Traducerea se oprește (eroarea 403) până luna următoare. Pe „Free F0” nu se plătește nimic."),
		"sursa": u"https://learn.microsoft.com/azure/ai-services/translator/service-limits",
		"pagina_cheie": u"https://portal.azure.com/#create/Microsoft.CognitiveServicesTextTranslation",
	},
	"google": {
		"pasi": (
			N_("Intră pe console.cloud.google.com cu contul tău Google și fă un proiect nou."),
			N_("Activează facturarea: Google cere un card la înscriere (90 de zile de probă)."),
			N_("Caută „Cloud Translation API” în bara de sus și apasă „Enable”."),
			N_("Mergi la „APIs & Services”, „Credentials”, „Create credentials”, „API key” și copiază cheia."),
			N_("Apasă pe cheie, la „API restrictions” alege „Restrict key”, bifează „Cloud Translation API” și apasă "
				"„Save”."),
			N_("Ca să nu plătești: „APIs & Services”, „Cloud Translation API”, fila „Quotas”, cota de caractere pe zi, "
				"„Edit quotas”, scrie 15000. O alertă de buget NU oprește plata."),
			N_("Pune cheia aici."),
		),
		"avertisment": N_("Atenție: la Google Cloud facturarea e obligatorie, Google îți cere cardul la înscriere. Peste "
			"cota gratuită plătești automat, din card."),
		"cota": N_("Primele 500.000 de caractere pe lună sunt gratuite."),
		"depasire": N_("Peste cotă se plătește automat (20 de dolari pe milion de caractere), dacă nu ai coborât cota pe "
			"zi. Cu cota coborâtă, traducerea se oprește până a doua zi."),
		"sursa": u"https://cloud.google.com/translate/pricing",
		"pagina_cheie": u"https://console.cloud.google.com/apis/credentials",
		"verificat": u"21.10.2026",
	},
	"deepl": {
		"pasi": (
			N_("Intră pe www.deepl.com/en/pro#api (prețurile DeepL) și alege fila „API”, nu „Translator”."),
			N_("La planul gratuit „Developer” apasă „Sign up for free”."),
			N_("Dacă ai deja cont la traducătorul DeepL, ieși din el și fă un cont nou, separat, pentru API."),
			N_("Termină înscrierea (email și parolă). Planul „Developer” e gratuit și nu trece singur pe plată."),
			N_("În cont mergi la „API Keys” („API Keys & Limits”). Dacă nu ai nicio cheie, apasă „Create key”, scrie un "
				"nume și apasă din nou „Create key”."),
			N_("Copiază cheia cu iconița de lângă ea și pune-o aici."),
		),
		"cota": N_("Cont nou (planul „Developer”): 1.000.000 de caractere în total, o singură dată, nu în fiecare lună. "
			"Cheile vechi (se termină cu :fx) merg în continuare."),
		"depasire": N_("Traducerea se oprește (eroarea 456). Nu se plătește nimic singur; pentru mai mult trebuie un plan "
			"plătit."),
		"sursa": u"https://support.deepl.com/hc/en-us/articles/360021200939-DeepL-API-plans",
		"pagina_cheie": u"https://www.deepl.com/your-account/keys",
		"verificat": u"21.10.2026",
	},
	"groq": {
		"pasi": (
			N_("Intră pe console.groq.com și înscrie-te cu emailul sau cu contul tău Google."),
			N_("În meniu alege „API Keys”, apasă „Create API Key”, scrie un nume și copiază cheia (începe cu gsk_). Groq o "
				"arată o singură dată: copiaz-o imediat."),
			N_("Pune cheia aici. Modelul recomandat e openai/gpt-oss-20b (rapid); e scris deja. openai/gpt-oss-120b e mai "
				"mare și mai lent."),
			N_("Nu adăuga card la cont, ca să rămâi pe planul gratuit."),
			N_("Pentru subtitrări multe pune în setări și servicii de rezervă, de exemplu Azure Translator: când Groq dă "
				"eroarea 429, receptorul trece singur la următorul."),
		),
		"cota": N_("Gratuit: 30 de cereri pe minut, 1.000 pe zi și 200.000 de bucăți de text („tokeni”) pe zi; ajung "
			"pentru circa două filme pe zi. Cifrele le poate schimba Groq: le vezi în contul tău, la „Limits”."),
		"depasire": N_("Peste limită Groq răspunde cu eroarea 429: receptorul așteaptă cât spune Groq și trece între timp "
			"la serviciul de rezervă, dacă ai pus unul. Fără card nu se plătește nimic."),
		"sursa": u"https://console.groq.com/docs/rate-limits",
		"pagina_cheie": u"https://console.groq.com/keys",
		"verificat": u"21.10.2026",
	},
	"cloudflare": {
		"pasi": (
			N_("Intră pe dash.cloudflare.com și fă un cont gratuit (email și parolă)."),
			N_("În panou deschide pagina „Workers AI” și apasă „Use REST API”."),
			N_("Apasă „Create a Workers AI API Token”, apoi „Create API Token” și „Copy API Token”. Păstrează jetonul."),
			N_("Pe aceeași pagină, la „Get Account ID”, copiază „Account ID” (ID-ul contului, 32 de litere și cifre)."),
			N_("Pune aici jetonul (la cheie) și ID-ul contului. Modelul e @cf/google/gemma-4-26b-a4b-it; e scris deja."),
			N_("Nu trece contul pe planul plătit („Workers Paid”), ca să rămâi pe gratuit."),
		),
		"cota": N_("Gratuit: 10.000 de unități („neuroni”) pe zi, care ajung pentru câteva filme pe zi. Se reînnoiesc în "
			"fiecare zi la 00:00 UTC (ora 3 vara și ora 2 iarna, ora României)."),
		"depasire": N_("Când s-au terminat, Cloudflare răspunde cu eroarea 429 până a doua zi: receptorul trece la "
			"serviciul de rezervă, dacă ai pus unul. Pe planul gratuit nu se plătește nimic."),
		"sursa": u"https://developers.cloudflare.com/workers-ai/platform/pricing/",
		# pagina Workers AI din panou (legatura din developers.cloudflare.com/workers-ai/get-started/rest-api/)
		"pagina_cheie": u"https://dash.cloudflare.com/?to=/:account/ai/workers-ai",
		"verificat": u"21.10.2026",
	},
	"libre": {
		"pasi": (
			_PAS_CAUTA,
			N_("Pe un calculator din casă instalează Docker Desktop (docs.docker.com) și pornește-l."),
			N_("În PowerShell scrie o singură comandă: docker run -d --restart unless-stopped --name libretranslate "
				"-p 5000:5000 -v lt-local:/home/libretranslate/.local libretranslate/libretranslate --load-only "
				"en,ro,de,fr,it,es,hu"),
			N_("La prima pornire așteaptă câteva minute (descarcă limbile). Deschide http://localhost:5000 în browser: "
				"dacă apare pagina de traducere, merge."),
			_PAS_PARAVAN,
			N_("Află adresa calculatorului în rețea (de exemplu 192.168.1.50) și scrie aici http://192.168.1.50:5000. "
				"Cheie nu trebuie."),
			N_("Calculatorul trebuie să fie pornit când vrei traducere. Calitatea e mai slabă decât la serviciile de pe "
				"internet, dar nu costă nimic și nimic nu iese din casă."),
			N_("Pe internet, cu plată: intră pe portal.libretranslate.com și apasă „Get API Key”. Alege planul (Pro: 29 de "
				"dolari pe lună; Business: 58 de dolari pe lună), apasă „BUY” și plătește. Nu există probă gratuită și nici "
				"cheie gratuită; ai 7 zile să ceri banii înapoi."),
			N_("Cheia apare în portal; o poți verifica la „Test your API Key”. Aici scrie adresa https://libretranslate.com "
				"și lipește cheia."),
		),
		"cota": N_("Pe calculatorul din casă: fără limită, gratuit; viteza depinde de calculator (pentru cele 7 limbi din "
			"comandă, cam 2 GB de memorie liberă). Pe libretranslate.com: Pro, traduceri nelimitate, cu rafale de până la "
			"80 de cereri pe minut; Business, până la 200 pe minut. Varianta de pe internet nu e gratuită."),
		"depasire": N_("În casă nu e cazul. Pe libretranslate.com, peste limita pe minut vine eroarea 429 câteva secunde: "
			"receptorul trece la serviciul de rezervă, dacă ai pus unul. LibreTranslate pe internet costă bani în fiecare "
			"lună; pentru subtitrări gratuite folosește mai bine Azure sau Gemini."),
		"sursa": u"https://docs.libretranslate.com/",
		"pagina_cheie": u"https://docs.libretranslate.com/guides/installation/",
		"verificat": u"21.10.2026",
	},
	"gemini": {
		"pasi": (
			N_("Intră pe aistudio.google.com cu contul tău Google (de la 18 ani) și acceptă termenii."),
			N_("Deschide pagina „API Keys” din meniul din stânga și apasă „Create API key”."),
			N_("Copiază cheia și pune-o aici. Nu adăuga card (facturare) la proiect: așa rămâi pe gratuit."),
			N_("Modelul recomandat e gemini-3.5-flash-lite; e scris deja."),
			N_("Câte cereri ai pe zi vezi la aistudio.google.com/rate-limit."),
			N_("Pentru subtitrări multe (filme întregi, în fiecare zi) pune în setări și servicii de rezervă, de exemplu "
				"Azure Translator: când Gemini dă eroarea 429, receptorul trece singur la următorul. Lista se face din "
				"servicii diferite: limita Gemini e pe proiect, iar mai multe conturi făcute ca să aduni limitele gratuite "
				"înseamnă ocolirea limitelor, pe care termenii Google o interzic."),
		),
		"cota": N_("Gratuit pentru folosire ocazională, cu un număr limitat de cereri pe minut și pe zi; Google arată "
			"cifrele numai în contul tău. La subtitrări fără pauză poate da eroarea 429 după câteva minute, iar limita pe "
			"zi se poate termina."),
		"depasire": N_("Peste limita pe minut, cererile primesc eroarea 429 câteva secunde: receptorul așteaptă cât spune "
			"Google și trece între timp la serviciul de rezervă, dacă ai pus unul. Peste limita pe zi, până a doua zi (în "
			"jurul orei 10, ora României). Fără card nu se plătește nimic."),
		"sursa": u"https://ai.google.dev/gemini-api/docs/billing",
		"pagina_cheie": u"https://aistudio.google.com/apikey",
	},
	"openai": {
		"pasi": (
			_PAS_CAUTA,
			N_("În casă: instalează Ollama de pe ollama.com pe un calculator și pornește-l."),
			N_("În PowerShell scrie: ollama pull gemma3:4b (3,3 GB). gemma3:12b traduce mai bine, dar e mai lent (8,1 GB); "
				"pentru un calculator slab, gemma3:1b (815 MB). Modelele qwen2.5 traduc slab în română."),
			N_("Ca să-l vadă receptorul: deschide Ollama, intră în Settings și pornește „Expose Ollama to the network” "
				"(Ollama 0.9.5 sau mai nou; numele poate fi puțin altul). Dacă nu găsești setarea: închide Ollama de lângă "
				"ceas („Quit”), caută în Start „environment variables” („variabile de mediu”), adaugă la contul tău "
				"OLLAMA_HOST cu valoarea 0.0.0.0:11434, apasă OK și pornește din nou Ollama."),
			_PAS_PARAVAN,
			N_("Fără căutare: scrie aici adresa http://IP-UL-CALCULATORULUI:11434 și modelul gemma3:4b. Cheie nu trebuie."),
			N_("LM Studio merge la fel: fila „Developer”, „Start server”, apoi în setările serverului „Serve on Local "
				"Network”, cu „Require Authentication” oprit; adresa http://IP-UL-CALCULATORULUI:1234 și numele modelului "
				"din LM Studio."),
			N_("Pe internet, cu cheie: orice serviciu compatibil OpenAI merge; scrii adresa, modelul și cheia lui. Groq și "
				"Cloudflare Workers au locul lor în lista serviciilor, cu pașii lor: alege-le acolo."),
			N_("Mistral: adresa https://api.mistral.ai/v1, modelul mistral-small-2603 și cheia din contul tău Mistral, la "
				"„API keys”; limitele planului gratuit le vezi în cont."),
			N_("OpenRouter: adresa https://openrouter.ai/api/v1, un model cu :free la sfârșit (de exemplu "
				"google/gemma-4-31b-it:free) și cheia din contul tău OpenRouter. Gratuit sunt numai 50 de cereri pe zi, prea "
				"puțin pentru un film."),
			N_("Serviciile de pe internet pot avea limită pe zi: pune și un serviciu de rezervă (de exemplu Azure "
				"Translator). Cheia o scrii o singură dată; receptorul o ține criptată și o trimite numai la adresa pentru "
				"care ai pus-o."),
		),
		"cota": N_("În casă nu are cotă: e gratuit, fără limită, și nimic nu iese din casă. Pe internet depinde de "
			"serviciu (vezi pașii)."),
		"depasire": N_("În casă nu e cazul. Pe internet, peste limită vine eroarea 429, iar fără credit eroarea 402: "
			"receptorul trece singur la serviciul de rezervă, dacă ai pus unul."),
		"sursa": u"https://docs.ollama.com/faq",
		"pagina_cheie": u"https://ollama.com/download",
		"verificat": u"21.10.2026",
	},
	"propriu": {
		"pasi": (
			N_("„Adresă proprie” e pentru un server de traducere ales de tine, de exemplu un LibreTranslate pornit pe un "
				"calculator din casă. Receptorul trimite fiecare rând de subtitrare într-o cerere separată."),
			N_("Adresa e un șablon: scrii adresa serverului și pui în ea locurile {text} (textul de tradus), {sursa} "
				"(limba subtitrării, sau auto când nu se știe) și {tinta} (limba traducerii, de exemplu ro). Receptorul le "
				"înlocuiește la fiecare cerere."),
			N_("Adresa începe cu https://. O adresă http:// merge numai pentru un server din rețeaua de acasă (de exemplu "
				"192.168.1.50). Nume și parolă nu se scriu în adresă."),
			N_("Metoda GET trimite totul în adresă, deci {text} trebuie să fie în adresă. Metoda POST trimite și un corp, "
				"cu aceleași locuri: JSON (pune locurile între ghilimele, de exemplu \"q\": \"{text}\") sau formular (de "
				"exemplu q={text}&target={tinta})."),
			N_("Antetul e opțional: dacă serverul cere o cheie, scrie numele antetului (de exemplu Authorization) și, la "
				"valoare, ce cere serverul (de exemplu Bearer, un spațiu și cheia). Valoarea se păstrează criptată pe "
				"receptor și nu se mai arată."),
			N_("Răspunsul: alege „Text simplu” dacă serverul dă numai traducerea. Pentru JSON scrie calea până la "
				"traducere: numele cheilor și numerele pozițiilor (de la 0), despărțite prin punct, de exemplu "
				"translatedText sau data.translations.0.translatedText. Cu * iei toate elementele, lipite în ordine, de "
				"exemplu 0.*.0."),
			N_("Exemplu, un LibreTranslate al tău din casă: adresa http://192.168.1.50:5000/translate, metoda POST, corpul "
				"JSON {\"q\": \"{text}\", \"source\": \"{sursa}\", \"target\": \"{tinta}\", \"format\": \"text\"}, "
				"răspunsul JSON, calea translatedText."),
			N_("Exemplu cu GET: adresa https://example.com/translate?q={text}&from={sursa}&to={tinta} și răspunsul „Text "
				"simplu” (example.com ține locul serverului tău)."),
			N_("Nu scrie niciodată o parolă sau o cheie în adresă: pune-o la antet. Cheia LibreTranslate de pe internet "
				"pleacă în corpul cererii, deci pentru ea alege serviciul LibreTranslate, nu adresa proprie."),
			N_("Apasă „Probează traducerea”. Dacă nu merge, mesajul arată începutul răspunsului serverului, ca să vezi unde "
				"e traducerea și ce cale să scrii."),
		),
		"cota": N_("Depinde de server. Un server al tău din casă nu are cotă."),
		"depasire": N_("Depinde de server."),
		"sursa": u"https://docs.libretranslate.com/guides/api_usage/",
		"pagina_cheie": u"",
		"verificat": u"21.10.2026",
	},
}


def instructiuni(serviciu):
	"""{titlu, avertisment, eticheta, pasi: [text], cota, depasire, verificat, sursa, pagina_cheie} cu textele traduse
	(avertisment: gol sau un text de aratat inaintea pasilor, la serviciile la care se poate plati automat;
	pagina_cheie: adresa pentru codul QR, "" = fara cod)"""
	d = INSTRUCTIUNI.get(serviciu) or {}
	return {
		"serviciu": serviciu,
		"titlu": {"libre": _t("Cum folosești LibreTranslate"),
			"openai": _t("Cum pornești un server compatibil OpenAI"),
			"propriu": _t("Cum folosești o adresă proprie")}.get(serviciu) or
			_t("Cum îți faci cheia pentru %s") % numeServiciu(serviciu),
		"avertisment": _t(d["avertisment"]) if d.get("avertisment") else u"",
		"eticheta": etichetaServiciu(serviciu),
		"pasi": [_t(p) for p in d.get("pasi", ())],
		"cota": _t(d["cota"]) if d.get("cota") else u"",
		"depasire": _t(d["depasire"]) if d.get("depasire") else u"",
		"verificat": _t("Verificat pe pagina oficială la %s.") % (d.get("verificat") or VERIFICAT),
		"sursa": d.get("sursa", u""),
		"pagina_cheie": d.get("pagina_cheie", u""),
	}


def serverDinCasa(cfg):
	"""serviciul ales e un server din reteaua de acasa (LibreTranslate, compatibil OpenAI sau adresa proprie)"""
	try:
		return cfg.get("serviciu") in ("libre", "openai", "propriu") and adresaInCasa(cfg.get("adresa") or "")
	except Exception:
		return False


def adresaInCasa(adresa):
	"""adresa e in reteaua de acasa (clasaAdresa: IP privat in orice forma, nume .local / .lan / .home / fara punct);
	adresele receptorului insusi nu sunt „acasa” (sunt refuzate)"""
	return clasaAdresa(adresa) == CASA


def textConfidentialitate(cfg=None):
	"""ce pleaca din receptor si unde, pentru serviciul ales; cu „Tradu EPG” si textele ghidului"""
	cfg = cfg or configuratia()
	text = _textConfidentialitate(cfg)
	nota = notaCheie(cfg)
	if nota:
		text += u" " + nota
	try:
		s = initConfig()
		if s.epg.value:
			text += u" " + _t("Cu „Tradu EPG” pornită pleacă la același serviciu și titlurile și descrierile emisiunilor de "
				"pe ecran.")
		elif s.pornit.value and s.bara.value:
			text += u" " + _t("Cu „Tradu bara de jos” pornită pleacă la același serviciu și titlurile emisiunilor de pe "
				"bara de jos.")
		if s.teletext.value:
			text += u" " + _t("Cu „Tradu teletextul” pornită pleacă la același serviciu și textul paginilor de teletext "
				"pe care le deschizi.")
		if s.hbbtv.value:
			text += u" " + _t("Cu „Tradu HbbTV” pornită pleacă la același serviciu și textele văzute ale aplicațiilor "
				"HbbTV pe care le deschizi.")
	except Exception:
		pass
	return text


def notaCheie(cfg=None):
	"""pentru serviciile cu adresa: de ce cheia salvata nu pleaca (pusa pentru alt server, sau http spre internet),
	ori avertismentul ca pleaca necriptata (http) spre serverul din casa; "" altfel"""
	cfg = cfg or configuratia()
	serv = cfg.get("serviciu")
	if serv not in CU_ADRESA:
		return u""
	oprita = cfg.get("cheie_oprita")
	if oprita == "alta":
		gazda = gazdaLegaturii(serv)
		if gazda:
			return _t("Cheia salvată a fost pusă pentru alt server (%s), deci nu pleacă spre adresa de acum. Dacă serverul "
				"cere cheie, pune-o din nou.") % gazda
		return _t("Cheia salvată nu e legată de adresa de acum, deci nu pleacă nicăieri. Dacă serverul cere cheie, "
			"pune-o din nou.")
	if oprita == "http":
		return _t("Cheia nu pleacă pe http:// spre internet. Scrie adresa cu https://.")
	if cfg.get("cheie") and (cfg.get("adresa") or u"").lower().startswith("http://"):
		return _t("Atenție: cheia pleacă necriptată (http://) spre serverul din casă. Pune o cheie numai dacă serverul o "
			"cere.")
	return u""


def stareCheie(cfg=None):
	"""starea cheii serviciului ales, pentru paginile web (ca randul cheii de pe televizor) -> (fel, text): "pusa",
	"oprita" (pusa, dar nu pleaca: legata de alt server, nelegata sau http spre internet) sau "lipsa"; niciodata cheia"""
	cfg = cfg or configuratia()
	serv = cfg.get("serviciu")
	pusa = bool(chei().stare().get(serv))
	oprita = cfg.get("cheie_oprita")
	if pusa and oprita == "alta":
		gazda = gazdaLegaturii(serv)
		if gazda:
			return "oprita", _t("Cheie pusă pentru alt server (%s): nu pleacă spre adresa de acum. Pune-o din nou.") % gazda
		return "oprita", _t("Cheie pusă, dar nelegată de adresa de acum: nu pleacă nicăieri. Pune-o din nou.")
	if pusa and oprita == "http":
		return "oprita", _t("Cheie pusă, dar nu pleacă pe http:// spre internet. Scrie adresa cu https://.")
	if pusa:
		return "pusa", _t("Cheie pusă")
	return "lipsa", _t("Fără cheie")


def textCheiDinNouBland():
	"""nota blanda pentru serviciile fara cheie obligatorie, cat timp cheile vechi stau deoparte; "" altfel"""
	try:
		de_pus = chei().deDinNou()
	except Exception:
		de_pus = False
	return _t("Dacă foloseai o cheie pentru acest server, pune-o din nou.") if de_pus else u""


def _textConfidentialitate(cfg):
	serv = cfg["serviciu"]
	if serv in ("libre", "openai", "propriu"):
		if cfg.get("adresa") and adresaInCasa(cfg["adresa"]):
			return _t("Textul subtitrărilor merge la serverul din casa ta (%s). Nimic nu iese din casă.") % _gazda(cfg["adresa"])
		if serv == "propriu" and cfg.get("adresa"):
			return _t("Textul subtitrărilor (numai textul, fără imagine și fără sunet) pleacă din receptor, prin internet, "
				"spre serverul de la adresa scrisă de tine (%s), care îl traduce.") % _gazda(cfg["adresa"])
		return _t("Textul subtitrărilor (numai textul, fără imagine și fără sunet) pleacă din receptor spre serverul de "
			"la adresa pe care o scrii. Dacă serverul e în casa ta, nimic nu iese din casă.")
	text = _t("Textul subtitrărilor (numai textul, fără imagine și fără sunet) pleacă din receptor, prin internet, spre "
		"%s, care îl traduce. Cheia ta rămâne pe receptor.") % numeServiciu(serv)
	if serv == "gemini":
		text += u" " + _t("Pentru Uniunea Europeană, Google spune că nici la nivelul gratuit nu folosește textele trimise "
			"ca să-și îmbunătățească produsele.")
	return text


_INSTANTA = [None]


def instanta():
	if _INSTANTA[0] is None:
		_INSTANTA[0] = Traducator()
	return _INSTANTA[0]


# ------------------------------------------------------------------ legaturile cu nucleul, OCR si ecranele

_URMARIT = [False]


def cereOcr():
	"""traducerea e pornita si vrea si subtitrarile DVB (pozele trec prin recunoasterea textului)"""
	try:
		s = initConfig()
		return bool(s.pornit.value and s.dvb.value)
	except Exception:
		return False


def traduceDvbAcum():
	"""traducerea e pornita pentru subtitrarile DVB si chiar traduce pista de acum: limba ei (pistaAleasa) nu e deja
	limba tinta; o pista fara limba stiuta se traduce (Components/HdsOcrSubtitrari.ocrDeFolos)"""
	try:
		s = initConfig()
		if not (s.pornit.value and s.dvb.value):
			return False
		sursa = _INSTANTA[0].sursa if _INSTANTA[0] is not None else ""
		return not (sursa and sursa == limbaTinta(s))
	except Exception:
		return False


def _tvStins():
	"""Components/HdsStandbyTv.tvStins (televizorul stins, dupa driverul HDMI); fara modul, False"""
	try:
		from Components import HdsStandbyTv
		return bool(HdsStandbyTv.tvStins())
	except Exception:
		return False


# Cu televizorul stins (sau in standby) nimic nu se traduce si nimic nu se citeste cu OCR (laPagina si
# HdsOcrSubtitrari.ocrDeFolos ies inainte de contor), deci contoarele raman la zero. Fara fraza aceasta, ecranul si
# pagina web spuneau numai "nicio pagină" si pareau o stricaciune (integrarea 0.6.1, dupa o repornire: televizorul
# intrase in standby). Cand televizorul se aprinde, totul porneste singur la pagina urmatoare (tvStins se reciteste la
# cateva secunde). Numai in ecranele de setari si in web, niciodata ca fereastra pe televizor.
TEXT_TV_STINS = N_("Televizorul e stins sau în standby: subtitrările nu se citesc și nu se traduc până se aprinde.")


def textTvStins():
	"""TEXT_TV_STINS tradus cand televizorul e stins (HdsStandbyTv.tvStins), altfel sirul gol"""
	return _t(TEXT_TV_STINS) if _tvStins() else u""


def inainte(texte):
	"""Components/HdsOcrSubtitrari.py: textul unei pagini DVB e gata (de obicei inainte de afisare)"""
	if _INSTANTA[0] is None or _INSTANTA[0].widget is None:
		return		# traducerea nu e legata de nucleu
	try:
		s = initConfig()
		if s.pornit.value and s.dvb.value:
			_INSTANTA[0].inainte(texte)
	except Exception as e:
		_jurnal("inainte: %s" % e)


def pistaAleasa(pista):
	"""limba subtitrarii pornite (tuplul din getSubtitleList, sau un cod): sursa cererilor; aceeasi limba = nimic"""
	limba = u""
	try:
		if isinstance(pista, (list, tuple)):
			limba = pista[4] if len(pista) > 4 else u""
			try:
				from Components.HdsPisteLimbi import limbiDinText
				l = limbiDinText(limba)
				limba = l[0] if l else limba
			except Exception:
				pass
		else:
			limba = pista or u""
	except Exception:
		limba = u""
	instanta().sursa = cod2(limba)


def pistaOprita():
	if _INSTANTA[0] is not None:
		_INSTANTA[0].sursa = ""


def pentruNucleu(widget, t=None):
	"""functia data lui eSubtitleWidget.setTranslationHandler"""
	t = t or instanta()

	def laPagina(generatie, texte, fel=0, intarziere_ms=-1):
		try:
			return t.laPagina(generatie, texte, fel, intarziere_ms)
		except Exception as e:
			_jurnal("pagina: %s" % e)
			return None			# nu se traduce: nucleul arata originalul cu semn
	return laPagina


def _clasaNucleu():
	from enigma import eSubtitleWidget
	return eSubtitleWidget


def puneLegatura(widget=None):
	"""functia pusa in nucleu (traducerea pornita) sau scoasa; OCR urmeaza (pentru DVB). -> True daca e pusa"""
	pusa = False
	try:
		w = widget if widget is not None else _clasaNucleu()
		pune = getattr(w, "setTranslationHandler", None)
		if pune is None:
			_jurnal("enigma2 fara eSubtitleWidget.setTranslationHandler: subtitrarile raman netraduse")
		else:
			s = initConfig()
			t = instanta()
			if s.pornit.value:
				t.widget = w
				w.setTranslationMode(1 if s.afisare.value == "sub" else 0)
				w.setTranslationWait(t.asteptareMs())
				# semnul subtitrarii netraduse si timpul de citire (nucleul de dinainte de 0.2.8 nu le are)
				semn = getattr(w, "setTranslationMark", None)
				if semn is not None:
					semn(textNetradus())
				citire = getattr(w, "setReadingTime", None)
				if citire is not None:
					citire(*timpCitire(s))
				pune(pentruNucleu(w, t))
				pusa = True
				_jurnal("pornit (%s)" % s.serviciu.value)
			else:
				t.widget = None
				pune(None)
	except Exception as e:
		_jurnal("legatura cu nucleul: %s" % e)
	try:
		from Components import HdsOcrSubtitrari
		HdsOcrSubtitrari.puneLegatura()
	except Exception as e:
		_jurnal("OCR: %s" % e)
	return pusa


def _laSchimbare(element=None):
	instanta().setariSchimbate()
	puneEticheteleServiciilor()		# o adresa schimbata: (local) sau (pe internet) dupa ea
	try:
		from Components import HdsTraducereEpg
		HdsTraducereEpg.setariSchimbate(element)
	except Exception as e:
		_jurnal("EPG: %s" % e)
	try:
		from Components import HdsTraducereTexte
		HdsTraducereTexte.setariSchimbate(element)
	except Exception as e:
		_jurnal("teletext si HbbTV: %s" % e)
	puneLegatura()


def textCheiDinNou():
	"""nota pentru ecran si web cat timp cheile vechi stau deoparte (Chei.deDinNou); "" altfel"""
	try:
		de_pus = chei().deDinNou()
	except Exception:
		de_pus = False
	return _t("Cheile de traducere trebuie puse din nou: cele salvate înainte nu se mai pot citi pe acest receptor.") \
		if de_pus else u""


# mesajul „cheile trebuie puse din nou”: la cateva secunde dupa pornire (o fereastra deschisa peste InfoBar inainte
# de pornirea canalului o amana pana la o tasta) si cu ceas (o pornire fara om la televizor nu ramane pe mesaj; o
# singura data e asigurat de mutarea fisierului, nu de fereastra)
MESAJ_CHEI_DUPA_MS = 8000
MESAJ_CHEI_S = 60
_CEAS_MESAJ = [None]


def _arataMesajCheiDinNou():
	_CEAS_MESAJ[0] = None
	_jurnal("mesaj pe televizor: cheile trebuie puse din nou")
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		text = _t("Cheile de traducere trebuie puse din nou: cele salvate înainte nu se mai pot citi pe acest "
			"receptor. Le pui în Meniu › Setări › Sunet și subtitrări › Traducerea subtitrărilor sau de pe telefon, "
			"cu codul QR de acolo.")
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, MESAJ_CHEI_S, "HdsTraducereChei")
	except Exception as e:
		_jurnal("mesajul nu s-a putut arata: %s" % e)


def _mesajCheiDinNou():
	"""mesajul de la pornire, o data (fisierul tocmai a fost pus deoparte), peste MESAJ_CHEI_DUPA_MS; pe loc cand
	enigma nu are eTimer (probele de pe PC)"""
	try:
		from enigma import eTimer
	except ImportError:
		_arataMesajCheiDinNou()
		return
	ceas = eTimer()
	ceas.callback.append(_arataMesajCheiDinNou)
	ceas.start(MESAJ_CHEI_DUPA_MS, True)
	_CEAS_MESAJ[0] = ceas


def verificaCheileLaPornire():
	"""fisierul cheilor verificat o data, la pornire (Chei.verificaLaPornire): plicul vechi recriptat, cel care nu se
	mai poate citi pus deoparte, cu mesajul pe televizor o singura data -> ce s-a facut"""
	try:
		rez = chei().verificaLaPornire()
	except Exception as e:
		_jurnal("cheile la pornire: %s" % e.__class__.__name__)
		return ""
	if rez == "deoparte":
		_mesajCheiDinNou()
	elif rez in ("refacut", "recriptat"):
		# initConfig (si mutaServiciulVechi din el) a rulat inaintea acestei verificari, cand cheile nu se puteau citi:
		# acum se pot, deci serviciul vechi (nescris in settings) se pastreaza chiar la aceasta pornire
		try:
			s = initConfig()
			if s.serviciu.saved_value is None:
				mutaServiciulVechi(s)
		except Exception as e:
			_jurnal("serviciul vechi dupa chei: %s" % e.__class__.__name__)
	return rez


def legaNucleul():
	"""Screens/SubtitleDisplay.py, la pornire; setarile urmarite (o singura data). Intai fisierul cheilor
	(verificaCheileLaPornire), apoi legarea cheilor vechi de adresele lor."""
	if not _URMARIT[0]:
		verificaCheileLaPornire()
		try:
			chei().legaCheileVechi()
		except Exception as e:
			_jurnal("cheile vechi: %s" % e.__class__.__name__)
		# randul serviciului si al rezervelor pus in settings cu valoarea de acum, abia dupa verificaCheileLaPornire
		# (mutaServiciulVechi se uita la randul lipsa); fara configfile.save(): intra la urmatoarea salvare
		try:
			from Components import HdsCopieSetari
			initConfig()
			HdsCopieSetari.fixeaza_setari(prefix=HdsCopieSetari.PREFIX_TRADUCERE)
		except Exception as e:
			_jurnal("setarile scrise mereu: %s" % e.__class__.__name__)
		try:
			s = initConfig()
			for e in (s.pornit, s.serviciu, s.afisare, s.dvb, s.limba, s.tarziu, s.citire, s.regiune, s.adresa_libre,
					s.adresa_openai, s.model_gemini, s.model_openai, s.propriu_adresa, s.propriu_metoda, s.propriu_corp,
					s.propriu_tip_corp, s.propriu_antet, s.propriu_raspuns, s.propriu_cale, s.rezerve, s.epg, s.bara):
				e.addNotifier(_laSchimbare, initial_call=False)
			for e in (s.teletext, s.teletext_mod, s.hbbtv):
				e.addNotifier(_laSchimbare, initial_call=False)
			_URMARIT[0] = True
		except Exception as e:
			_jurnal("setarile nu se pot urmari: %s" % e)
	return puneLegatura()
