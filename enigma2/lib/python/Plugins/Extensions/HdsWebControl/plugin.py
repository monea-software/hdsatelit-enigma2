# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsWebControl: interfata web proprie HDSatelit.
#
# Fisierul e scris de la zero, pe `twisted.web` (deja parte din Enigma2, incarcat oricum de `mytest.py` pentru
# reactor), fara cod luat din alte interfete web (licenta lor, de obicei GPL-3.0, nu se poate uni cu imaginea,
# GPLv2-only).
#
# Ce face:
# Server HTTP real, pornit in procesul enigma2 (acelasi
# reactor Twisted deja rulat de mytest.py), cu 3 API-uri de baza:
#   GET /api/statusinfo     -> JSON cu serviciul curent, volum, standby
#   GET /api/remotecontrol?command=<cod_tasta_linux>  -> injecteaza o apasare
#       de tasta (acelasi mecanism deja folosit si testat in acest arbore de
#       EmulatorMouse/plugin.py: eActionMap.getInstance().keyPressed("SDL", cod, 0/1))
#   GET /api/zap?sRef=<referinta_serviciu>  -> comuta pe alt canal
# Probat cu o cerere HTTP reala (curl, din container, catre 127.0.0.1:PORT, dupa ce enigma2 a pornit).
#
# AUTENTIFICARE (reparatie de securitate): toate rutele
# /api/... cer parametrul ?token=<jeton>, verificat in timp constant (secrets.compare_digest). Jetonul
# se genereaza o singura data, aleator, si se salveaza pe disc (config.plugins.hdswebcontrol.token) --
# vizibil userului in ecranul Setup (Screens/HdsWebControlSetup.py). Motiv: serverul asculta pe TOATE
# interfetele de retea (Twisted listenTCP fara `interface=`), iar CORS NU opreste o cerere GET simpla
# (doar citirea raspunsului din JavaScript) -- fara jeton, orice pagina web sau dispozitiv din aceeasi
# retea putea injecta taste/schimba serviciul curent, exact tipul de risc cunoscut
# (receptoare compromise prin imagini nesecurizate).
#
# ASOCIEREA BROWSERELOR (in locul jetonului, ceva simplu pentru om):
# http://<receptor>/ (portul 80; 8080 trimite spre el) duce direct la panou. Prima data, pagina cere codul de 6 cifre afisat pe televizor
# (valabil o ora, o singura folosire, 5 greseli = pauza de 5 minute); dupa cod, browserul primeste un
# cookie HttpOnly, SameSite=Strict, valabil un an, iar receptorul pastreaza doar amprenta lui (asociere.py,
# /etc/enigma2/hdswebcontrol-browsere.json). Jetonul ?token= ramane valabil pentru scripturi si uneltele
# noastre (GET si POST, ca inainte), dar nu mai apare in paginile obisnuite; lista API s-a mutat in
# /programatori. Cu cookie, comenzile care schimba ceva (remotecontrol, zap) cer POST + antetul X-HDS-CSRF
# (derivat din secretul sesiunii) + Origin/Referer egal cu Host, ca o pagina straina deschisa in acelasi
# browser sa nu poata comanda receptorul. Ecranul de setari arata browserele si le poate deconecta pe toate.
#
# REPARATII DE SECURITATE (verificate pe emulator): serverul are acum propriile Site/Request/canal (_construiesteServer):
# - antetul Host trebuie sa numeasca receptorul (IP scris cu cifre, localhost sau numele lui), altfel 403 pe
#   orice cale: o pagina de pe internet care isi re-lega numele la IP-ul receptorului (DNS rebinding) trecea de
#   verificarea Origin si putea cere coduri, iar daca omul scria codul in pagina ei, primea cookie-ul;
# - corpul unei cereri are cel mult 64 KB, verificat INAINTE de citire (Twisted citea si parsa corpul intreg
#   pe firul enigma2, inaintea oricarei verificari: 32 MB inghetau televizorul 10 s);
# - cel mult 64 de conexiuni deschise, 16 de la aceeasi adresa, iar o cerere trebuie sa soseasca intreaga in
#   20 s (un aparat care trimitea cate un octet tinea mii de conexiuni si lasa enigma2 fara descriptori);
# - blocarea asocierii se scoate din telecomanda (setari, Albastru, Conecteaza un browser nou), iar
#   televizorul arata adresa care a cerut codul.
#
# RETEAUA LOCALA FARA COD: implicit, un browser (sau aplicatia) de pe o
# adresa din reteaua locala (RFC1918 si loopback, _esteAdresaLocala) intra fara cod; cine vrea codul si in casa
# porneste „Cere codul și în rețeaua locală” (config.plugins.hdswebcontrol.cod_retea_locala, implicit Nu; pe
# televizor in ecranul interfetei web, in web pe /setari). Raman la fel: din afara retelei locale 403 pe orice (nu
# se deschide nimic spre Internet); antetul Host verificat la orice cerere (DNS rebinding); comenzile care schimba
# ceva cer si fara cod POST, aceeasi origine si antetul CSRF, facut dintr-un secret derivat din cheia pentru scripturi
# (_secretLiber), pe care o pagina straina nu-l poate citi. Totul trece prin _sesiuneDinCerere, deci si paginile din
# modulele *_web.py merg fara nicio schimbare in ele.
#
# CADRUL PAGINILOR (cadru_web.py): antetul comun (numele receptorului, versiunea, starea pe scurt, calea),
# meniul pe grupe facut la rulare din data/menu.xml si temele Clasic si Pro (culorile din skin.xml, fontul skinului)
# se pun pe orice pagina HTML intreaga intr-un singur loc, _CerereHds.render, numai dupa poarta; paginile *_web.py
# raman cum sunt. Rutele API, poarta, jetonul, CSRF-ul si codul de asociere nu se schimba.
#
# FEREASTRA CODULUI: codul mare, in mijlocul ecranului, „12 34 56”, in ecranul propriu Screens/HdsCodAsociere.py,
# ca sa se vada de la distanta (o fraza intr-un MessageBox se citea greu).
#
# APLICATIILE DE TELEFON (aplicatii_web.py): rutele cerute de aplicatiile obisnuite ale receptoarelor Enigma2 (/web/*,
# rutele cu aceleasi nume din /api, /picon, /file, /grab), scrise de la zero. Pornite din fabrica
# (config.plugins.hdswebcontrol.aplicatii) si fara parola din reteaua locala, cu Host-ul
# receptorului (IP-ul, numele lui si numele lui cu terminatiile date de routere, _numeAcasa). Cu „Cere codul și în
# rețeaua locală” pornit (cod_retea_locala), si din casa numai cu parola pentru aplicatii. Din afara retelei locale
# raspund numai cu „Acces din afara casei” pornit (config.plugins.hdswebcontrol.aplicatii_afara, oprit din fabrica) si
# numai cu HTTP Basic si parola pentru aplicatii. Bariera si rutele: capul fisierului aplicatii_web.py. Restul
# interfetei ramane numai pentru reteaua locala, cu poarta Host de pana acum (fara terminatiile routerelor).
#
# GET /api/screenshot?format=jpg|png&quality=N&width=N (captura de ecran la rezolutia reala, pana la 2160p):
# NU citeste framebuffer-ul direct (ctypes lipseste din imagine, vezi `lib/python/crypt.py`) -- porneste
# unealta `aio-grab` deja
# inclusa in imagine (`hdsatelit-base.bb`, RDEPENDS `aio-grab`), aceeasi folosita de toate
# scripturile de proba (`grab -p ecran.png`), cu `-s` (stdout, fara fisier temporar
# pe disc) si `-q` (fara mesajele ei de jurnal amestecate in bytes-ii imaginii). Rezolutia
# implicita e cea REALA, curenta a semnalului (fara `-r`) -- `grab` insusi suporta pana la
# 3840 latime pe cutii UHD (`-r`, cf. `grab -h`), acoperind cerinta "pana la 2160p".
#
# GET /panou: primul ecran real
# al unui tablou de bord modern -- HTML/CSS/JS de sine statator, fara framework/build, STRICT
# peste API-urile deja existente mai sus (statusinfo/remotecontrol/screenshot), niciun endpoint
# nou de backend. Cere acelasi jeton (`?token=...`) ca restul API-ului -- vezi mecanismul de mai
# jos.
#
# Faza 2, restul NEFACUT: streaming live HTML5 (MSE/HLS/fMP4), upload bootlogo prin
# formular. Cer un flux video real din decodor si/sau un OSD real de capturat --
# niciunul disponibil complet si verificabil in containerul de emulator fara hardware
# sau sursa video reala conectata. Structura de rutare de mai jos (HdsWebRoot) e gata sa
# primeasca aceste resurse suplimentare cand cineva le poate testa corect.

import hashlib
import hmac
import io
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time

from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigInteger, ConfigText, configfile
from Plugins.Plugin import PluginDescriptor

from .asociere import (Asociere, NUME_COOKIE, ANTET_CSRF, DURATA_SESIUNE_S, TIP_BROWSER, TIP_APLICATIE,
	acelasiOrigin, csrfPentru, formatSecretValid, gazdaPermisa)

def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

_server_pornit = None  # pastreaza obiectul IListeningPort ca sa nu pornim de doua ori
_server_8080 = None  # portul 8080 care trimite spre 80 (numai cand interfata asculta pe 80)
_port_folosit = None  # portul pe care asculta interfata dupa pornire (80, sau 8080 cand 80 era ocupat)
# portul interfetei: 80 implicit; 8080 numai daca 80 e tinut de alt program (sau ales anume in setari)
PORT_IMPLICIT = 80
PORT_REZERVA = 8080
# portul pe care asculta interfata acum (pentru paznicul receptorului, hds-watchdog.py)
CALE_PORT_ACUM = "/var/run/hdswebcontrol.port"
# numele din reteaua de acasa publicat de avahi (/etc/init.d/hds-nume-local): „hdsatelit”, sau „hdsatelit-2” cand
# alt receptor din casa il are deja
CALE_NUME_LOCAL = "/var/run/hds-nume-local.nume"
NUME_LOCAL_IMPLICIT = "hdsatelit"
# /favicon.ico: iconita paginilor (PNG 64x64: patratul in culoarea hdsBrand a skinului, „HD” alb cu HdsBold, linia in
# culoarea hdsAmber). Browserele o cer singure la prima pagina; fara ea consola arata o eroare 404.
_FAVICON_PNG_B64 = (
	"iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAJoElEQVR42u1bfWyV1Rn/Pc857/1oe1sQVqwFkYlCJFqZa9EOt8S4"
	"wcaHznmdMSOGGRYTZ2KWmP2xxHLjkiXDP/bhFrNNN6JZJrJlMFH8mFPHulEGKEaRqYCoFZRSWtre977vOefZH++9Fwot3Pa22Bae"
	"5OQm9+N57/M7z/Oc5/mdcwgDihBaVhMyGQcAzTc9fr0jXiLOfhmQeURcLeIEAGFsiBAxibhugN4kVq+yuE2tG1b8EwDQ0sLIrBaA"
	"5OQfnmJAS4twJkMOABbc9MS3ifkecWahUgkSsXAuBEQwJoUIzB6IFKz1hVhvEed+tXXDd5482bYBAUin16mnnrrNzr/xlxfFKic/"
	"qlRsMSCwxoeIWAIRCIyxLAInECEipXQCAMHaYHPQ23nXzhfvbS/YeAoAhQ++uPSxRq0TG1h5dSbotRGwpDAORUQsAOhYpXI2/NgY"
	"/6b/Pv3dbSeCQCe6xjVLftvkeZWbiWiytTlDII0JIAIxSsW1iHSGYe/i7ZtWtRVsJqCF0QI0bruklj3vdWZVa41viVhhAomIs0on"
	"lHP2ExeGDdsa93+CDMDp9DxCJuNYYa3S8Vprc2aiGR+FMStrc0bpeC0rrEUm49LpeUQA0LT88Vu1l3jKhH2GAI0JLAIY7VVoE/rp"
	"to0r1jMgBHH3I588MdFFhCJb3f2AEDUteex69mIviTMKoIkPQAEF1taFwQ1MSi1njmkROOBcMR+OOaZJqeUMkWYRCzpnZh8gEIlY"
	"QKSZBbjKuRBjvsIbWQTYuRACXMXMqmrM1vajHAfMqorzXd05KSJO9FBaWsXUb6GwtrS8yUQgPv4759yATney/kELWwFEZCQct/Ra"
	"nwjo7glg8kYTAanK+Bn/LxEhmzPwc6b4XmXSg+dxPwNO1j9w6ALEBK0Y8ZiCpxkCwJXhxLo04wlhaHHb0rmom1YFAAgCiyf/tht+"
	"zoCZBpwNZkLWN2i6ug6NDXVwVsCK8Ow/9mL/B12IxRRE5BT9IgM4ggB+YHD4SBYftHdj74Gj+LSjD1ozKpLesD1Clzr7QeiQXjoX"
	"cy+dUnz/r8/9D33ZEMw0+Oz7IZoa6nDX7Q3F9996pwN73juCeFwVjR1I/+nk0OE+tO1sx58378H21w8imdTQmofsDTzUELDWwVqH"
	"o91+SYgXQsBaB9+PXsPQnTLDJ+oPQgt7BkOmTa3Asq/Oxu8fWoLVP1gIrRlBYAedjLI84MQkpVSEWeG11CSoFMO56HeD5Y2CfmbA"
	"WIfnXtlbNIqIUFnhoX5aCrMvmQylqDjb3/rGHMy+ZDLufeAFZH0DrankcNBjlNpD1jd48Oet6OzKRslOIm9KJjRmXFSNmxddhjtu"
	"ngfFhDB0aLiiFj/54Vfw/QdegNZq5EPgswChpiqGSak4avIjVRWDUoR9HxzFj3/RivsyLyLrGyhFCI3Dlxqn45bFl6O7J4BSNL4B"
	"AADrpN9wLsr0iZjGtKmV2PzyXvzs0W35EInI6jtvvRLVVXEYIyUVOGUBwEwlDRrhPsuJIAwtpk5O4i/P7sF77x+FVtEKcHF9Na6e"
	"V4usH/YrvkYcAAHQlw3R23f60dMbIAjtaDA7YGb09oV4qfX9fpXp/HnTYIwrCXg93IdrJjRcUYtjvQG04kELoe6eHOovTBXjeoRp"
	"byjF2P3O4Uh/fsZnzZgEVlzSBs7wAHCCiqSHhx/82pBDZqRFKcLhI9njvQSAKZOT0Kq0pZDHO8NJRMgFBtZK0cM8j6GYIZDRqwNE"
	"gN6+4IwoiwjicY14bPSYdmYCnTCVzgpEJN8+ycgDwEzo6Quw4r6n0XXMHzQHKMXo7PLxvTsacNftDbBWRjYMKOoEqypjYCIY66AV"
	"oac36ioTdOY0UJYHdHXncLTbh9aDA3CkK4usb0aJ2YpK5pn11XmeQQAFfHToGIx1JSXdskphrQla82kB8DSPSvIrIEAAFsyv77fT"
	"u/vdDlCJPI8uk1brNwb7fDREKUJfNsRlsy7AwsbpEBFozcjlLLa/cQiJuC6pNeaxTd6eMPJsGTMVDXUOuP/uBUgmdFT6EuGVrQew"
	"90BnkWsYl93g8ZI3KnujEcV4GEZ8Qd3nqvCje69D8zX1sNZBaUIusPjNH19DTCtAxnE7fDzHMLRW0DriECqSER9w7Rcuwi2L52Dq"
	"BUkY46BU1G+seWQrdr/bgUnVcVgr4xcA5wSVSQ+/++nXozgmQCtGqiqGVGWs+D1jXUSDieChR7biTxt3oyZVuvFDBkBEiollKNyb"
	"5N23MOQM+p0TKEWYXpc6/Z9XjNfePISH1+7Av3d8hJpUfMic4JAASMR1cUmrSHolLTQiUWnKTIjHVb+afTD9p1s2+7Ih2g/1YNfu"
	"T/H3f+3H1p3tCI0bktv3S7QLlq+VUtgZawVzZ08puqB1gjfe/hTG2EHbTiJCaCymX5hC/YWpIgP8zr5OdHb5Re5uIP0DhUVvNkRH"
	"ZxYdR7I41hdAccQTEtGw9wZKAqAgfs4UUSYCkgmvhI2RiPIOAlsszRNxPSBxWdQ/QAlfWAILxZXKd3uuzJ29IYVARdI7ZVZKCYGY"
	"p/o1Q4NtYpysf/DiS4bl7mUDMFy0S921cZ/BPu25cyZgtOsARQI5iyWyK5x3GgsACIDuXBxMchb2CwTGMpKegVau7GZLj0zlRri7"
	"eSsaL/4QgVGjdtpIBNDKob2rGr/eci26/AQ0u7I8rywAmATdfhzfvPIt3HPDq3BnwQucI/CcLEQILZtvRE3Chy0jFHTeg2m47mid"
	"wqVTO+BCjc7eZOSWoxj7VggpYcyacgSKy36W6PxNi2Efuoxpg/+8fzHubNqOKdXHSiIiy4JAAHghWvfNhHNU7vlhoqZlfzhGzMM+"
	"KUYkyIYerpt5ANfMaEdgedTu0UQbMg4fHq3B5rcvB5EM/1lEEOd6NAG7mL1mZwI3nLOCIoSkF6J1/0y8/N7nQRjNq0QCAUGRQ1U8"
	"KOtWCSuPncvt0iBqJVLN0UlpGnYoVMYCVNHZqwRsGe4fXalRAFGrFms3Og7uI4Iqj74iYJwcNicCOxcYsXYjt21aucVZu0N5yeId"
	"G0zow5FilZeEs3ZH26aVWxggAfEagAlEE//UKJFEtvIagITT6XWqbeOK9TboeV57FVogZuLeFhGjvQptg57n2zauWJ9Or1PnL00B"
	"GdeC1dj2zMqDxmSXiUin0gk1kTxBIEbphBKRTmOyy7Y9s/JgC1YDyDgGgEyGXDq9Tm3ftKrNGH+RiHysvUotInY8J8bC/8/b8rEx"
	"/qLtm1a1pdPrVOEKLZ2/Oovzl6fP6evz/wd+5Gpfz1qjLAAAAABJRU5ErkJggg=="
)
# sesiunea enigma2 primita la WHERE_SESSIONSTART. Cu ea web-ul
# deschide pe televizor ecranul de scanare (ServiceScan) si ecranele antenei; fara ea paginile spun de ce nu pot.
_sesiune = None

# pagina /telecomenzi exista (telecomenzi_web.py). Ecranul „Telecomenzi” de pe televizor arata
# randul „asociază din pagina web: <adresa>” numai cu acest semn (Components/HdsTelecomenziDate.adresa_pagina_web).
ARE_PAGINA_TELECOMENZI = True


def _trimiteTasta(cod, lung=False):
	"""Tasta din telecomanda virtuala (panou, /telecomenzi) ca de pe telecomanda receptorului: prin
	eRCMapper.inject, deci prin keyEvent (cu apasarea lunga la a patra repetare, ca la tasta tinuta) si cu numele
	dispozitivului nativ, ca legaturile din keymap.xml scrise pentru el sa se potriveasca.
	Inainte, tasta pleca cu numele „SDL” (tastatura emulatorului). Fara eRCMapper (binar vechi), drumul vechi."""
	try:
		from enigma import eRCMapper
		m = eRCMapper.getInstance()
	except Exception:
		m = None
	if m is not None:
		m.inject(cod, 0)                   # apasare
		if lung:
			for _i in range(5):
				m.inject(cod, 2)           # repetari: a patra da apasarea lunga (main/enigma.cpp, keyEvent)
		m.inject(cod, 1)                   # ridicare
		return
	from enigma import eActionMap
	harta = eActionMap.getInstance()
	harta.keyPressed("SDL", cod, 0)
	harta.keyPressed("SDL", cod, 1)

# Bariera „o captura odata” pentru /api/screenshot: citita si scrisa numai pe firul enigma2 (reactorul), niciodata din
# firul care ruleaza grab. Cat e pusa, o a doua cerere primeste 503 imediat, fara sa porneasca alt proces grab. Se
# ridica la orice raspuns al capturii: rezultatul firului, eroarea lui sau termenul tinut pe firul enigma2
# (ScreenshotResource.TERMEN_S), deci o cerere al carei rezultat nu mai vine nu blocheaza capturile pana la repornire.
# Panoul (_PAGINA_PANOU) cere urmatoarea captura numai dupa ce s-a terminat cea curenta; cele doua bariere sunt
# independente.
_captura_in_curs = False

# Capturile cerute de interfata web straina din feedul extern: peticul ei de compatibilitate (compat.py) cere
# /api/screenshot de pe receptor (127.0.0.1), cu ?token= si prin urllib din Python (User-Agent Python-urllib/3.x).
# Numai ele trec prin paza din captura_sigura.py. Panoul (browserul, cu cookie sau ?token=), aplicatiile de telefon
# (/grab: argumentele rescrise, fara token) si scripturile de pe alte aparate nu se potrivesc; in imagine nimic nu cere
# /api/screenshot prin urllib.
_ADRESE_RECEPTOR = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
_AGENT_URLLIB = "python-urllib/"


def _capturaStraina(request):
	"""True numai pentru o captura ceruta de interfata web straina (vezi mai sus)."""
	if PARAM_JETON not in request.args:
		return False
	if _adresaClient(request) not in _ADRESE_RECEPTOR:
		return False
	return (_antet(request, b"user-agent") or "").lower().startswith(_AGENT_URLLIB)

# SECURITATE: API-ul de mai jos pornea fara NICIO autentificare, ascultand pe TOATE interfetele de retea
# (`reactor.listenTCP` fara `interface=`, implicit 0.0.0.0) -- orice dispozitiv din aceeasi retea (sau
# orice pagina web deschisa in browser-ul userului, printr-o cerere GET simpla gen `<img src="http://
# receptor:8080/api/remotecontrol?command=...">`, care ocoleste CORS -- CORS blocheaza doar CITIREA
# raspunsului in JavaScript, NU trimiterea cererii insesi) putea injecta taste, schimba ce se reda, sau
# citi ecranul curent, fara nicio bariera reala. Reparat cu un jeton (token) generat aleator, salvat pe
# disc o singura data (nu regenerat la fiecare pornire, ca un client deja configurat sa nu se strice),
# cerut acum pe toate rutele `/api/*`.
#
# A DOUA BARIERA: jetonul ramane autentificarea
# REALA, dar `listenTCP` tot asculta pe toate interfetele (0.0.0.0), fara `interface=`. Aparare in
# adancime, independenta de jeton: respinge cu 403, INAINTE de verificarea jetonului, orice cerere
# care nu vine din RFC1918/loopback -- daca routerul userului ar redirectiona vreodata portul spre
# internet, aceasta bariera tot opreste accesul (nu doar jetonul, care ar deveni brute-force-abil).
PARAM_JETON = b"token"

# Limitele serverului (vezi _construiesteServer):
# - corpurile legitime au cativa octeti (cod=123456, reafiseaza=0); o ruta viitoare cu incarcare de fisiere
#   (bootlogo) va avea nevoie de limita ei, separata;
# - un browser deschide cel mult 6 conexiuni spre acelasi receptor; 16 lasa loc la doua browsere pe acelasi
#   aparat, iar 64 in total tin enigma2 departe de limita lui de descriptori (adesea 1024 pe receptoare);
# - termenul curge de la deschiderea conexiunii (sau de la sfarsitul raspunsului precedent) pana la cererea
#   intreaga si NU se reia la fiecare octet primit; cat se pregateste raspunsul (captura), e oprit.
MAX_CORP_CERERE = 64 * 1024
MAX_CONEXIUNI = 64
MAX_CONEXIUNI_PE_ADRESA = 16
TERMEN_CERERE_S = 20

# URCAREA UNEI POZE DE ECRAN DE PORNIRE (omul isi pune propria poza de pornire din interfata web).
# Comentariul de mai sus spunea deja ca o ruta de
# incarcare de fisiere va avea nevoie de limita ei: aceasta e.
# 8 MB, si de ce atat: o poza de telefon de 12 megapixeli in JPG are 3-6 MB, iar un PNG de 1920x1080
# facut de unealta noastra are 1,3-2,8 MB. Mai mult n-ar folosi la nimic: poza se aduce oricum la
# 1920x1080, deci octetii in plus se arunca. TOATE celelalte rute raman la 64 KB, ca pana acum:
# limita se ridica DOAR pentru calea de mai jos, verificata inainte de citirea corpului.
# Poza se trimite ca octeti bruti (Content-Type: application/octet-stream), NU ca formular
# multipart: asa Twisted nu parseaza nimic pe firul enigma2 si nu scrie nimic in /tmp.
MAX_CORP_POZA = 8 * 1024 * 1024
CALE_URCARE_POZA = b"/api/ecran-urca"
# 8 MB in 20 de secunde ar cere peste 400 KB/s; pe o retea fara fir slaba nu e sigur. Doar pentru
# calea de urcare, si doar o data, termenul conexiunii se pune la 60 s (setTimeout, nu resetTimeout:
# asteptarea tot nu se reia la fiecare octet, deci paza de mai sus ramane).
TERMEN_URCARE_S = 60

# URCAREA UNUI FISIER DIN TELEFON PENTRU PLAYER (/api/media-urca, media_web.py): fisierul vine pe bucati de cel mult
# 4 MiB (octeti bruti, ca poza), fiecare bucata o cerere, scrisa de media_web pe un disc montat. Limita mare numai pe
# calea asta, cu cookie-ul de sesiune sau pentru browserul intrat fara cod (corpMareMedia); acelasi termen lungit al
# conexiunii. Pagina afla de la /api/media-player cat de mare poate fi bucata ei (media_web.marimeBucata).
MAX_CORP_MEDIA = 4 * 1024 * 1024
CALE_URCARE_MEDIA = b"/api/media-urca"
# playlistul M3U al listei filtrate din /canale (tv_web.py, POST /api/tv-m3u): pana la acces_extern.MAX_CANALE referinte
# in corp (~54 de octeti fiecare, cu ":" si "," codate); aceeasi conditie ca la urcari (corpMareMedia)
CALE_M3U = b"/api/tv-m3u"
MAX_CORP_M3U = 256 * 1024
# editorul de canale (editor_canale_web.py): o operatie poate avea mii de chei de canale (alegerea a 2000 de canale),
# iar importul aduce o arhiva cu lista intreaga (lamedb, buchete; cateva MB) sau un m3u; aceeasi conditie ca la urcari
CALE_EDITOR_OP = b"/api/editor-canale-op"
MAX_CORP_EDITOR_OP = 1024 * 1024
CALE_EDITOR_IMPORT = b"/api/editor-canale-import"
MAX_CORP_EDITOR_IMPORT = 16 * 1024 * 1024
# poza urcata de pe calculator in capturile receptorului (forum_web.py, POST /api/captura-urca): pagina o micsoreaza la
# cel mult 1920 px latime si o trimite ca octeti bruti; limita = forum_web.URCARE_MAX (peste HdsCapturi.ADAUGA_MAX, cat
# primeste forumul pe o poza); aceeasi conditie ca la urcari (corpMareMedia)
CALE_URCARE_CAPTURA = b"/api/captura-urca"
MAX_CORP_CAPTURA = 4 * 1024 * 1024


def corpMareMedia(are_cookie, adresa, aceeasi_origine):
	"""True cand o bucata spre CALE_URCARE_MEDIA poate avea MAX_CORP_MEDIA octeti (la fel poza ecranului de pornire
	spre CALE_URCARE_POZA, MAX_CORP_POZA: aceeasi problema, urcarea nu mergea fara cod): cererea are cookie-ul de sesiune (un
	browser asociat cu cod; o pagina straina nu il poate trimite, SameSite=Strict), sau e a unui browser intrat fara cod
	(adresa din reteaua locala unde codul nu se cere, aceeasi conditie ca in _sesiuneDinCerere) care vine chiar dintr-o
	pagina a receptorului (Origin/Referer = Host, `aceeasi_origine`). Browserul intrat fara cod nu primeste cookie, iar cu
	limita mica urcarea din pagina /player nu mergea deloc in configuratia implicita; cererea de aceeasi origine taie
	corpurile mari trimise de o pagina straina deschisa in browserul cuiva din casa. Altfel ramane limita mica."""
	if are_cookie:
		return True
	return bool(aceeasi_origine) and _esteAdresaLocala(adresa) and not codInReteaLocala()


def _esteAdresaLocala(gazda):
	"""Verifica STRICT prin text/numere daca 'gazda' (text IPv4, ex. '10.0.0.5') e in reteaua
	locala (RFC1918) sau loopback. NU foloseste modulul `ipaddress` -- pachet SEPARAT in aceasta
	distributie (`python3-ipaddress`, cerut ca RDEPENDS de retetele care il folosesc, in feed-ul
	OE-Alliance), NEinclus in `hdsatelit-base.bb` -- aceeasi capcana ca `ctypes` lipsa (vezi nota
	ScreenshotResource mai jos), verificata aici INAINTE sa presupun disponibil, nu dupa un import
	esuat in productie."""
	if not gazda:
		return False
	parti = gazda.split(".")
	if len(parti) != 4:
		return False  # IPv6 sau format neasteptat -- respins implicit, mai sigur decat presupus local
	try:
		octeti = [int(p) for p in parti]
	except ValueError:
		return False
	if any(o < 0 or o > 255 for o in octeti):
		return False
	if octeti[0] == 127:
		return True  # 127.0.0.0/8, loopback
	if octeti[0] == 10:
		return True  # 10.0.0.0/8
	if octeti[0] == 172 and 16 <= octeti[1] <= 31:
		return True  # 172.16.0.0/12 (inclusiv reteaua interna Docker, ex. 172.17.x, folosita la testare)
	if octeti[0] == 192 and octeti[1] == 168:
		return True  # 192.168.0.0/16
	return False


def _adresaClient(request):
	"""Adresa IP a clientului HTTP, text sau None. `getClientAddress()` e API-ul curent Twisted
	(disponibil, imaginea are `python3-twisted` 25.5.0, mult peste minimul care il introduce);
	`getClientIP()` ramane rezerva defensiva daca ceva neasteptat schimba asta."""
	try:
		adresa = request.getClientAddress()
		if adresa is not None and hasattr(adresa, "host"):
			return adresa.host
	except Exception:
		pass
	try:
		return request.getClientIP()
	except Exception:
		return None


def _jetonConfigurat():
	initConfigHdsWebControl()
	return config.plugins.hdswebcontrol.token.value


def _jetonValid(request):
	primit = request.args.get(PARAM_JETON)
	asteptat = _jetonConfigurat()
	if not asteptat:
		return False  # niciodata gol in practica (generat la initConfigHdsWebControl), dar niciodata "acces liber"
	if not primit:
		return False
	# comparatie in timp constant, ca sa nu se poata ghici jetonul octet cu octet dupa timpul de raspuns
	# (pe octeti: compare_digest nu primeste text cu caractere non-ASCII, pe care le-ar putea trimite oricine)
	return secrets.compare_digest(primit[0], asteptat.encode("utf-8"))


# ------------------------------------------------------------------ asocierea browserelor
_asociere = None


def obtineAsociere():
	"""Un singur obiect pentru server si pentru ecranul de setari (acelasi proces, acelasi fir), ca
	"Deconecteaza toate browserele" sa se vada imediat in server, fara repornire."""
	global _asociere
	if _asociere is None:
		_asociere = Asociere(jurnal=_jurnal)
	return _asociere


def _antet(request, nume):
	valoare = request.getHeader(nume)
	if valoare is None:
		return None
	if isinstance(valoare, bytes):
		valoare = valoare.decode("latin-1")
	return valoare


def _secretDinCookie(request):
	try:
		valoare = request.getCookie(NUME_COOKIE.encode("ascii"))
	except Exception:
		return None
	if not valoare:
		return None
	if isinstance(valoare, bytes):
		valoare = valoare.decode("ascii", "replace")
	return valoare if formatSecretValid(valoare) else None


def _secretLiber():
	"""Secretul din care se face tokenul CSRF al browserelor intrate fara cod (reteaua locala, codul oprit): HMAC din
	cheia pentru scripturi (config.plugins.hdswebcontrol.token). Nu se scrie nicaieri si nu pleaca spre browser (pagina
	primeste doar HMAC-ul lui, csrfPentru), iar cheia nu se poate afla din el. Ramane acelasi dupa o repornire a
	interfetei (o pagina deschisa de dinainte merge mai departe; cu un secret nou la fiecare pornire, comenzile ei
	primeau 403 pana la reincarcare) si se schimba odata cu cheia („Cheie nouă pentru scripturi”)."""
	return hmac.new(_jetonConfigurat().encode("utf-8"), b"hds-liber-v1", hashlib.sha256).hexdigest()


def codInReteaLocala():
	"""True daca si in reteaua locala se cere codul de pe televizor (implicit Nu)."""
	initConfigHdsWebControl()
	try:
		return bool(config.plugins.hdswebcontrol.cod_retea_locala.value)
	except Exception as eroare:
		_jurnal("setarea codului in reteaua locala nu se citeste (%s): se cere codul" % eroare)
		return True  # la orice problema, varianta mai sigura


def aplicatiiPornite():
	"""True daca rutele pentru aplicatiile de telefon (aplicatii_web.py) sunt pornite (implicit
	Da)."""
	initConfigHdsWebControl()
	try:
		return bool(config.plugins.hdswebcontrol.aplicatii.value)
	except Exception as eroare:
		_jurnal("setarea aplicatiilor de telefon nu se citeste (%s): oprite" % eroare)
		return False  # la orice problema, varianta mai sigura


def aplicatiiAfara():
	"""True daca rutele aplicatiilor de telefon raspund si din afara retelei locale, numai cu parola pentru aplicatii
	(„Acces din afara casei”, implicit Nu)."""
	initConfigHdsWebControl()
	try:
		return bool(config.plugins.hdswebcontrol.aplicatii_afara.value)
	except Exception as eroare:
		_jurnal("setarea accesului din afara casei nu se citeste (%s): oprit" % eroare)
		return False  # la orice problema, varianta mai sigura


def _sesiuneDinCerere(request):
	"""(secret, browser) pentru un browser asociat si neexpirat. Doar intrari de tip browser: secretul unei aplicatii
	(aceeasi lista) nu trece drept cookie. Fara asociere: daca adresa e din reteaua locala si codul nu se cere acolo
	(implicit), un browser „liber” ({"nume": "", "liber": True}) cu _secretLiber(), din care se face tokenul CSRF;
	altfel (None, None) si paginile dau pagina de asociere (sau 401 la /api)."""
	secret = _secretDinCookie(request)
	if secret is not None:
		browser = obtineAsociere().sesiune(secret, tip=TIP_BROWSER)
		if browser is not None:
			return secret, browser
	if _esteAdresaLocala(_adresaClient(request)) and not codInReteaLocala():
		return _secretLiber(), {"id": "", "nume": "", "tip": TIP_BROWSER, "adresa": _adresaClient(request) or "",
			"liber": True}
	return None, None


def _acelasiOriginCerere(request):
	return acelasiOrigin(_antet(request, b"host"), _antet(request, b"origin"), _antet(request, b"referer"))


def _numeProprii():
	"""Numele receptorului in retea ('viper4kv20') si varianta mDNS ('viper4kv20.local'), pentru gazdaPermisa.
	Citit la fiecare cerere: numele se poate schimba din setarile de retea, fara repornire."""
	try:
		nume = socket.gethostname().strip().lower().rstrip(".")
	except Exception:
		return ()
	if not nume or nume == "localhost":
		nume_retea = ()
	else:
		nume_retea = (nume, nume + ".local")
	# numele publicat de avahi pe langa numele receptorului (hdsatelit.local, sau hdsatelit-2.local)
	local = NUME_LOCAL_IMPLICIT
	try:
		with open(CALE_NUME_LOCAL, encoding="utf-8", errors="replace") as f:
			citit = f.read(64).strip().lower().rstrip(".")
		if citit.endswith(".local"):
			citit = citit[:-len(".local")]
		if citit and all(c.isalnum() or c == "-" for c in citit):
			local = citit
	except (IOError, OSError):
		pass
	return nume_retea + (local + ".local",)


# terminatiile pe care routerele de acasa le dau numelui primit prin DHCP: dnsmasq si OpenWrt .lan, altele .home sau
# .localdomain, RFC 8375 .home.arpa; .local e mDNS. Fara .fritz.box: .box e si domeniu public, deci intr-o retea fara
# FRITZ!Box numele s-ar cauta pe internet. Numai pentru rutele aplicatiilor de telefon (aplicatii_web.Legaturi.gazdaProprie).
TERMINATII_ROUTER = ("", ".lan", ".home", ".localdomain", ".home.arpa", ".local")


def _numeAcasa():
	"""Numele din Host cu care aplicatiile de telefon din casa intra ca prin IP (fara parola): cele din _numeProprii si
	numele receptorului (primul cuvant din gethostname) cu TERMINATII_ROUTER: viper4kv20.lan, viper4kv20.home,
	viper4kv20.localdomain, viper4kv20.home.arpa. Numai numele EXACT: gazdaPermisa compara intreg,
	deci xviper4kv20.lan sau viper4kv20.lan.altceva.ro nu trec; numele publicat de avahi (hdsatelit.local) nu primeste
	terminatii (routerul nu il stie). Orice alt nume in Host ramane cu parola (bariera din aplicatii_web.py). Citit la
	fiecare cerere, ca _numeProprii."""
	proprii = _numeProprii()
	try:
		nume = socket.gethostname().strip().lower().rstrip(".").split(".", 1)[0]
	except Exception:
		return proprii
	if not nume or nume == "localhost":
		return proprii
	return proprii + tuple(nume + t for t in TERMINATII_ROUTER if nume + t not in proprii)


def _gazdaPermisaCerere(request):
	"""Poarta contra DNS rebinding, chemata pentru ORICE cerere (_CerereHds.process), inaintea rutelor. Trece
	un Host care numeste receptorul, sau un ?token= valid oricare ar fi Host-ul (o pagina straina nu are
	jetonul, iar scripturile care folosesc un nume dat de router merg mai departe), sau o cerere cu antet Basic spre
	rutele aplicatiilor de telefon (aplicatii_web.gazdaPermisa; parola o verifica bariera lor, cu numaratoarea
	greselilor). La orice eroare: respins."""
	try:
		if gazdaPermisa(_antet(request, b"host"), _numeProprii()):
			return True
		if PARAM_JETON in request.args and _jetonValid(request):
			return True
		from . import aplicatii_web
		return aplicatii_web.gazdaPermisa(request)
	except Exception as eroare:
		_jurnal("verificarea antetului Host a esuat: %s" % eroare)
		return False


def _mesajGazdaStraina():
	adresa = adresaWeb()
	if adresa:
		return (_t("Adresa folosită nu este a receptorului. Deschide interfața după adresa IP a receptorului: "
			"%s/") % adresa)
	return (_t("Adresa folosită nu este a receptorului. Deschide interfața după adresa IP a receptorului "
		"(o vezi pe receptor, în ecranul de setări al interfeței web)."))


_ultimul_jurnal = {}


def _jurnalRar(fel, text):
	"""Refuzurile serverului pot veni in rafala (o pagina ostila, un script): cel mult un rand pe minut pentru
	fiecare fel de refuz, ca jurnalul sa nu se umple."""
	acum = time.monotonic()
	if acum - _ultimul_jurnal.get(fel, -3600.0) >= 60:
		_ultimul_jurnal[fel] = acum
		_jurnal(text)


def _verificaAcces(request, schimba_ceva=False):
	"""Poarta comuna pentru /api/*. Intoarce ('jeton' | 'browser', None) daca cererea trece, altfel
	(None, (cod_http, mesaj)). Ordinea: reteaua locala (403), apoi ?token= daca e dat (scripturi, ca inainte),
	altfel cookie-ul browserului asociat; cu cookie, o comanda care schimba ceva mai cere POST, Origin/Referer
	egal cu Host si antetul CSRF al panoului."""
	if not _esteAdresaLocala(_adresaClient(request)):
		return None, (403, "acces permis doar din reteaua locala/loopback")
	if PARAM_JETON in request.args:
		if _jetonValid(request):
			return "jeton", None
		return None, (401, "parametrul token e gresit (vezi /programatori)")
	secret, browser = _sesiuneDinCerere(request)
	if browser is None:
		return None, (401, "browserul nu este conectat; deschide pagina principala a receptorului")
	if schimba_ceva:
		if request.method != b"POST":
			return None, (405, "din browser, comenzile se trimit cu POST, din panou")
		if not _acelasiOriginCerere(request):
			return None, (403, "cerere respinsa: nu vine dintr-o pagina a receptorului")
		if not obtineAsociere().csrfValid(secret, _antet(request, ANTET_CSRF.encode("ascii"))):
			return None, (403, "cerere respinsa: lipseste antetul " + ANTET_CSRF + " al panoului")
	return "browser", None


def _puneCookie(request, valoare, max_age):
	"""Cookie-ul sesiunii: HttpOnly (JavaScript nu il poate citi), SameSite=Strict (nu pleaca din alt sit),
	Path=/, fara Secure (serverul e HTTP simplu, in reteaua locala)."""
	try:
		request.addCookie(NUME_COOKIE.encode("ascii"), valoare.encode("ascii"), path=b"/",
			max_age=str(max_age).encode("ascii"), httpOnly=True, sameSite="strict")
	except TypeError:
		# Twisted vechi, fara parametrul sameSite: acelasi antet, scris de mana
		request.cookies.append(("%s=%s; Max-Age=%d; Path=/; HttpOnly; SameSite=Strict" % (NUME_COOKIE, valoare, max_age)).encode("ascii"))


def _sfatDeblocare():
	"""Spus in pagina de asociere cand asocierea e blocata: blocarea se scoate din telecomanda, din ecranul interfetei
	web (drumul din meniu, cu numele de pe televizor)."""
	try:
		from .meniu_web import drumText
		drum = drumText("hds_webcontrol_setup")
	except Exception as eroare:
		print("[HdsWebControl] drumul din meniu: %s" % eroare)
		drum = "Meniu"
	return _t("Sau, din telecomandă: %s, tasta albastră, „Conectează un browser nou”.") % drum


def _durataText(secunde):
	secunde = max(1, int(secunde))
	if secunde >= 60:
		minute = (secunde + 59) // 60
		if minute == 1:
			return _t("un minut")
		return _t("%d minute") % minute
	if secunde == 1:
		return _t("o secundă")
	return _t("%d secunde") % secunde


def _stareTelevizor():
	"""'standby', 'meniu' (InfoBar nu e in fata: un meniu sau o fereastra deschisa, deci notificarea
	asteapta in coada) sau 'ok'."""
	try:
		import Screens.Standby
		if Screens.Standby.inStandby is not None:
			return "standby"
	except Exception:
		pass
	try:
		from Screens.InfoBar import InfoBar
		if InfoBar.instance is not None and not InfoBar.instance.execing:
			return "meniu"
	except Exception:
		pass
	return "ok"


# fereastra cu codul de pe televizor: un id nou la fiecare afisare, ca inchiderea programata a uneia
# vechi sa nu inchida una mai noua
_fereastra_cod = {"id": None, "numar": 0}


def _inchideFereastra(id_fereastra):
	"""Inchide fereastra codului (sau o scoate din coada, daca n-a apucat sa apara), FARA sa anuleze codul: la
	conectare, la o fereastra noua pentru acelasi cod, la expirare."""
	try:
		from Tools import Notifications
		Notifications.RemovePopup(id_fereastra)  # scoate si din coada, daca n-a apucat sa apara
	except Exception as eroare:
		_jurnal("nu am putut inchide fereastra %s: %s" % (id_fereastra, eroare))
	if _fereastra_cod["id"] == id_fereastra:
		_fereastra_cod["id"] = None


def textExpirare():
	"""Mesajul de dupa o ora fara conectare (asociere.DURATA_COD_S), tradus."""
	return _("A trecut o oră de la pornirea asocierii și am oprit-o. Dacă vrei, o poți relua din pagina web sau din aplicație.")


def _anuntaExpirarea(id_fereastra, id_cerere=None):
	"""Codul ferestrei a expirat fara conectare: codul se anuleaza (de obicei a expirat deja in asociere.py, pe acelasi
	ceas; asa „am oprit-o” e adevarat oricum), fereastra se inchide (sau iese din coada) si pe televizor apare
	mesajul scurt, 15 secunde sau pana la OK. Chemat de fereastra insasi (HdsCodAsociere, laExpirare) si, pentru o
	fereastra care a stat in coada toata ora (omul era intr-un meniu), de callLater. Un singur mesaj oricum: al doilea
	apel nu mai gaseste fereastra, iar notificarea are un id fix."""
	if _fereastra_cod["id"] != id_fereastra:
		return  # fereastra a fost inchisa inainte: conectare, EXIT (codul anulat) sau inlocuita de alta
	if not _fereastraInCoadaSauPeEcran(id_fereastra):
		# fereastra s-a inchis singura fiindca, inainte de ora, codul a fost anulat din alta parte (5 coduri gresite,
		# „Deconectează browserele”, Albastru din setari): nimic de spus peste o ora
		_fereastra_cod["id"] = None
		return
	if id_cerere:
		obtineAsociere().anuleazaCod(id_cerere)
	_inchideFereastra(id_fereastra)
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(textExpirare(), MessageBox.TYPE_INFO, 15, "hds_web_cod_expirat")
	except Exception as eroare:
		_jurnal("nu am putut arata mesajul de expirare: %s" % eroare)


def _fereastraInCoadaSauPeEcran(id_fereastra):
	"""True daca notificarea ferestrei asteapta in coada sau e pe ecran (Tools.Notifications, listele lui)."""
	try:
		from Tools import Notifications
		if any(n[4] == id_fereastra for n in getattr(Notifications, "notifications", [])):
			return True
		return any(x[0] == id_fereastra for x in getattr(Notifications, "current_notifications", []))
	except Exception:
		return True  # nu se stie: mai bine mesajul decat nimic


def _anuleazaDeLaTelevizor(id_cerere, id_fereastra):
	"""OK sau EXIT pe fereastra codului: codul acelei ferestre se anuleaza (numai el, dupa id-ul cererii)."""
	if id_cerere and obtineAsociere().anuleazaCod(id_cerere):
		_jurnal("codul de asociere anulat din telecomanda")
	if _fereastra_cod["id"] == id_fereastra:
		_fereastra_cod["id"] = None


def _fereastraCoduluiDeschisa():
	"""True daca fereastra codului e pe ecran acum (deschisa de notificare sau din ecranul de setari)."""
	try:
		from Screens.HdsCodAsociere import _deschise
		return bool(_deschise)
	except Exception:
		return False


def _inchideFerestreleCodului():
	"""Inchide si ferestrele de cod deschise direct (din ecranul de setari), nu prin notificari."""
	try:
		from Screens.HdsCodAsociere import inchideToate
		inchideToate()
	except Exception as eroare:
		_jurnal("nu am putut inchide ferestrele codului: %s" % eroare)


def _arataCodPeTelevizor(cod, secunde, tip=TIP_BROWSER, adresa="", id_cerere=None):
	"""Rulat pe firul reactorului (acelasi cu bucla enigma2), din cererea HTTP. Fereastra Screens/HdsCodAsociere,
	deschisa prin notificarea standard enigma2 (Tools.Notifications): apare cand receptorul arata un canal; din
	meniu, asteapta iesirea. Aceeasi fereastra pentru browser si pentru aplicatie (`tip`), ca sa nu existe doua
	mecanisme. `adresa`: IP-ul aparatului care a cerut codul (un aparat strain din retea nu poate cere coduri pe ascuns): cine se uita la
	televizor vede daca nu e aparatul lui. Fereastra isi stie singura sfarsitul (`expira`, pe ceasul monoton, acelasi
	cu al asocierii), deci nu porneste de la zero daca a stat in coada; callLater de mai jos e numai pentru fereastra
	care n-a apucat sa apara toata ora (callLater poate intarzia in acest reactor). Fereastra se inchide singura si
	cand codul ei nu mai e cel activ (asociere.codActiv)."""
	try:
		from twisted.internet import reactor
		from Tools import Notifications
		from Screens.HdsCodAsociere import HdsCodAsociere
		if _fereastra_cod["id"]:
			_inchideFereastra(_fereastra_cod["id"])
		_fereastra_cod["numar"] += 1
		id_nou = "hds_web_cod_%d" % _fereastra_cod["numar"]
		_fereastra_cod["id"] = id_nou
		asociere = obtineAsociere()
		Notifications.AddNotificationWithID(id_nou, HdsCodAsociere, cod=cod, tip=tip, adresa=adresa,
			expira=time.monotonic() + int(secunde),
			activ=(lambda: asociere.codActiv(id_cerere)) if id_cerere else None,
			anuleaza=lambda: _anuleazaDeLaTelevizor(id_cerere, id_nou),
			laExpirare=lambda: _anuntaExpirarea(id_nou, id_cerere))
		reactor.callLater(int(secunde) + 1, _anuntaExpirarea, id_nou, id_cerere)
	except Exception as eroare:
		_jurnal("nu am putut arata codul pe televizor: %s" % eroare)


def _anuntaBrowserNou(browser):
	"""Inchide fereastra codului si spune pe televizor ce browser s-a conectat (cine se uita la televizor
	afla imediat daca s-a conectat cineva pe care nu-l stie)."""
	try:
		if _fereastra_cod["id"]:
			_inchideFereastra(_fereastra_cod["id"])
		_inchideFerestreleCodului()
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		if browser.get("tip") == TIP_APLICATIE:
			text = _("Telefon conectat la receptor: %s") % browser.get("nume", "Telefon")
		else:
			text = _("Browser conectat la receptor: %s") % browser.get("nume", "Browser")
		if browser.get("adresa"):
			text += " (%s)" % browser["adresa"]
		Notifications.AddPopup(text + ".", MessageBox.TYPE_INFO, 8, "hds_web_browser_nou")
	except Exception as eroare:
		_jurnal("nu am putut anunta browserul nou: %s" % eroare)


def portFolosit():
	"""Portul pe care asculta interfata: cel ales la pornire (80, sau 8080 cand 80 era tinut de alt program), apoi cel
	din CALE_PORT_ACUM (scris la pornire; /var/run e in RAM), iar fara amandoua setarea."""
	if _port_folosit is not None:
		return _port_folosit
	try:
		with open(CALE_PORT_ACUM, encoding="ascii") as f:
			port = int(f.read(16).strip())
		if 0 < port < 65536:
			return port
	except (IOError, OSError, ValueError):
		pass
	initConfigHdsWebControl()
	return config.plugins.hdswebcontrol.port.value


def adresaWeb():
	"""'http://10.0.0.20' (portul 80) sau 'http://10.0.0.20:8080' pentru ecranele de pe televizor, sau None
	daca receptorul nu are retea. Portul e cel pe care asculta interfata (portFolosit). Socket UDP fara trimitere:
	connect() doar alege interfata dupa tabela de rute."""
	initConfigHdsWebControl()
	port = portFolosit()
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			s.connect(("10.254.254.254", 9))
			ip = s.getsockname()[0]
		finally:
			s.close()
	except Exception:
		return None
	if not ip or ip.startswith("0."):
		return None
	if port == 80:
		return "http://%s" % ip
	return "http://%s:%d" % (ip, port)


def initConfigHdsWebControl():
	# NU folosim hasattr(config.plugins, ...): ConfigSubsection.__getattr__ arunca
	# KeyError (nu AttributeError) pentru o cheie lipsa, iar hasattr() din Python 3
	# NU prinde decat AttributeError -- deci hasattr ar lasa KeyError-ul sa treaca
	# mai departe necaptat. Verificam direct in dictionarul intern, sigur.
	if "hdswebcontrol" not in config.plugins.content.items:
		config.plugins.hdswebcontrol = ConfigSubsection()
		config.plugins.hdswebcontrol.activ = ConfigYesNo(default=True)
		# portul 80 implicit (adresa simpla http://hdsatelit.local, http://<ip>); 8080 trimite spre el
		config.plugins.hdswebcontrol.port = ConfigInteger(default=PORT_IMPLICIT, limits=(80, 65535))
		config.plugins.hdswebcontrol.token = ConfigText(default="", fixed_size=False)
	if "cod_retea_locala" not in config.plugins.hdswebcontrol.content.items:
		# codul de pe televizor si pentru aparatele din reteaua locala; implicit Nu: aparatele din casa intra fara cod.
		# Din afara retelei locale accesul ramane refuzat oricum.
		config.plugins.hdswebcontrol.cod_retea_locala = ConfigYesNo(default=False)
	if "aplicatii" not in config.plugins.hdswebcontrol.content.items:
		# rutele pentru aplicatiile de telefon (aplicatii_web.py); pornite din fabrica, fara parola din reteaua locala
		config.plugins.hdswebcontrol.aplicatii = ConfigYesNo(default=True)
	if "aplicatii_afara" not in config.plugins.hdswebcontrol.content.items:
		# „Acces din afara casei”: rutele aplicatiilor si din afara retelei locale, numai cu parola pentru aplicatii;
		# oprit din fabrica (din afara: 403)
		config.plugins.hdswebcontrol.aplicatii_afara = ConfigYesNo(default=False)
	if not config.plugins.hdswebcontrol.token.value:
		# generat o singura data, salvat imediat pe disc -- ramane stabil intre reporniri chiar daca
		# userul nu deschide niciodata ecranul de configurare (HdsWebControlSetup) sa-l vada/salveze
		config.plugins.hdswebcontrol.token.value = secrets.token_urlsafe(24)
		config.plugins.hdswebcontrol.token.save()
		configfile.save()


def _jurnal(text):
	print("[HdsWebControl] %s" % text)


# procesele grab care nu au iesit nici dupa kill() (blocate in driver, starea D); cat traieste unul, nu porneste altul
_grab_ramase = []
_lacat_captura = threading.Lock()
# asteptarile de captura in curs: fara o referinta pastrata aici, eTimer-ul lor ar fi cules de GC si n-ar mai bate
_asteptari_captura = set()


def _ruleazaGrab(comanda, timeout_s, asteptare_oprire_s=2):
	"""Ruleaza in firul separat al capturii (vezi _AsteptareCaptura); nu atinge `request` si nici reactorul. Intoarce
	(stare, rezultat): ("ok", CompletedProcess), ("lipsa", None) cand grab nu exista, ("timeout", None) cand nu
	termina in timeout_s. Popen + communicate(timeout) in loc de subprocess.run(timeout=): la depasire run() face kill()
	urmat de un wait() fara margine, care sta pe loc cat procesul e blocat in nucleu (starea D, driverul video). Aici,
	dupa kill(), asteptarea e marginita la asteptare_oprire_s; procesul care tot nu iese ramane in _grab_ramase, iar
	pipe-urile lui se inchid."""
	try:
		proces = subprocess.Popen(comanda, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	except FileNotFoundError:
		return ("lipsa", None)
	try:
		iesire, erori = proces.communicate(timeout=timeout_s)
	except subprocess.TimeoutExpired:
		try:
			proces.kill()
		except OSError:
			pass
		try:
			proces.communicate(timeout=asteptare_oprire_s)
		except subprocess.TimeoutExpired:
			with _lacat_captura:
				_grab_ramase.append(proces)
			for flux in (proces.stdout, proces.stderr):
				try:
					flux.close()
				except Exception:
					pass
		return ("timeout", None)
	return ("ok", subprocess.CompletedProcess(comanda, proces.returncode, iesire, erori))


def _grabRamasInViata():
	"""Pe firul enigma2: True cat un grab oprit cu kill() n-a iesit inca. poll() il si culege cand a iesit."""
	with _lacat_captura:
		_grab_ramase[:] = [p for p in _grab_ramase if p.poll() is None]
		return bool(_grab_ramase)


class _AsteptareCaptura(object):
	"""Ruleaza `lucru` intr-un fir separat si aduce rezultatul inapoi pe firul enigma2 fara reactor.callLater si fara
	reactor.callFromThread, care in reactorul imaginii (e2reactor peste eMainloop) pot lasa bucla sa doarma minute:
	- callLater: e2reactor.doPoll trimitea eApp.poll(int(secunde * 1000)); un rest sub 1 ms devenea 0, iar 0 inseamna
	  fara termen, deci bucla nu se mai intorcea in Python pana la un eveniment pe un descriptor Python (alta cerere,
	  o conexiune inchisa);
	- callFromThread: mytest.py pune supportsThreads() pe False, iar Twisted foloseste atunci varianta care doar pune
	  apelul in coada, fara sa trezeasca bucla.
	Trezirea de aici nu depinde de ele: firul pune rezultatul, apoi scrie un octet intr-un pipe propriu, al carui capat
	de citire e cititor in reactor (addReader), deci poll() iese pe loc. Plasa de siguranta si termenul: un eTimer
	(ceasul enigma2, rulat de eMainloop la fiecare trecere, orice termen ar cere Twisted) verifica rezultatul la
	fiecare ceas_ms si, dupa termen_s, cheama la_termen(). Raspunde o singura data: primul dintre pipe, ceas si termen.
	Dupa termen firul nu mai scrie in pipe (_abandonat, sub _lacat_captura) si isi inchide singur capatul de scriere."""

	def __init__(self, reactor_, lucru, la_rezultat, la_eroare, la_termen, termen_s, ceas_ms=250, acum=time.monotonic):
		self._reactor = reactor_
		self._lucru = lucru
		self._la_rezultat = la_rezultat
		self._la_eroare = la_eroare
		self._la_termen = la_termen
		self._termen_s = termen_s
		self._ceas_ms = ceas_ms
		self._acum = acum
		self._rezultat = None          # ("gata", rezultat) sau ("eroare", text), pus de fir
		self._incheiat = False         # firul enigma2: raspunsul a plecat
		self._abandonat = False        # sub _lacat_captura: firul enigma2 nu mai citeste din pipe
		self._citire = None            # capatul de citire (int pastrat pentru fileno(), si dupa inchidere)
		self._scriere = None
		self._citire_deschisa = False
		self._ceas = None
		self._legatura = None
		self._pornit = 0.0

	# ------------------------------------------------------------------ firul enigma2
	def porneste(self):
		from enigma import eTimer
		self._pornit = self._acum()
		try:
			self._citire, self._scriere = os.pipe()
			os.set_blocking(self._citire, False)
			self._citire_deschisa = True
		except OSError as eroare:
			_jurnal("screenshot: fara pipe de trezire (%s), rezultatul se ia la ceas" % eroare)
			for fd in (self._citire, self._scriere):
				if fd is not None:
					try:
						os.close(fd)
					except OSError:
						pass
			self._citire = self._scriere = None
		try:
			self._ceas = eTimer()
			try:
				self._ceas.callback.append(self._peTrezireCeas)
			except AttributeError:
				self._legatura = self._ceas.timeout.connect(self._peTrezireCeas)
			_asteptari_captura.add(self)
			if self._citire_deschisa:
				self._reactor.addReader(self)
			threading.Thread(target=self._fir, daemon=True).start()
		except Exception:
			self._incheiat = True
			self._opreste()
			if self._scriere is not None:
				try:
					os.close(self._scriere)
				except OSError:
					pass
			raise
		self._ceas.start(self._ceas_ms, False)

	def fileno(self):
		return self._citire if self._citire is not None else -1

	def logPrefix(self):
		return "HdsWebControl-captura"

	def doRead(self):
		self._trezestePipe()

	def connectionLost(self, motiv=None):
		# pipe inchis de partea firului fara date: rezultatul (daca e) pleaca acum, altfel ramane ceasul
		if self._rezultat is not None:
			self._incheie()
		else:
			self._inchidePipe()

	def _trezestePipe(self):
		if self._incheiat or not self._citire_deschisa:
			return
		try:
			date = os.read(self._citire, 64)
		except BlockingIOError:
			return  # trezire fara date: inca nimic de citit
		except OSError:
			date = b""
		if self._rezultat is not None:
			self._incheie()
		elif not date:
			self._inchidePipe()  # capatul de scriere inchis fara rezultat: ramane ceasul

	def _peTrezireCeas(self):
		if self._incheiat:
			return
		if self._rezultat is not None:
			self._incheie()
		elif self._acum() - self._pornit > self._termen_s:
			self._incheie(termen=True)

	def _incheie(self, termen=False):
		if self._incheiat:
			return
		self._incheiat = True
		self._opreste()
		if termen:
			self._la_termen()
			return
		fel, valoare = self._rezultat
		if fel == "gata":
			self._la_rezultat(valoare)
		else:
			self._la_eroare(valoare)

	def _inchidePipe(self):
		with _lacat_captura:
			self._abandonat = True
			deschisa = self._citire_deschisa
			self._citire_deschisa = False
		if deschisa:
			try:
				self._reactor.removeReader(self)
			except Exception:
				pass
			try:
				os.close(self._citire)
			except OSError:
				pass

	def _opreste(self):
		self._inchidePipe()
		if self._ceas is not None:
			try:
				self._ceas.stop()
			except Exception:
				pass
		_asteptari_captura.discard(self)

	# ------------------------------------------------------------------ firul separat
	def _fir(self):
		try:
			self._rezultat = ("gata", self._lucru())
		except Exception as eroare:
			self._rezultat = ("eroare", str(eroare))
		if self._scriere is None:
			return
		with _lacat_captura:
			if not self._abandonat:
				try:
					os.write(self._scriere, b"x")
				except OSError:
					pass
		try:
			os.close(self._scriere)
		except OSError:
			pass


# optiunile `grab` pentru parametrul `mode` al /api/screenshot (numele cerute de aplicatii): fara optiune grab pune
# meniul peste imaginea canalului, `-v` ia numai imaginea canalului, `-o` numai meniul
_OPTIUNE_MOD_CAPTURA = {"all": [], "video": ["-v"], "osd": ["-o"]}
_NUME_MOD_CAPTURA = {"all": "", "video": "-fara-meniu", "osd": "-meniu"}


def _numeCaptura(mod, extensie, acum=None):
	"""Numele fisierului descarcat: captura-receptor[-fara-meniu|-meniu]-AAAA-LL-ZZ-OOMM.<extensie>, dupa ceasul
	local al receptorului. Cu ceasul nesetat (an sub 2020) numele ramane fara data. Numai ASCII, ca sa intre
	neschimbat in antetul Content-Disposition."""
	if acum is None:
		acum = time.localtime()
	baza = "captura-receptor" + _NUME_MOD_CAPTURA.get(mod, "")
	if acum.tm_year >= 2020:
		baza += "-" + time.strftime("%Y-%m-%d-%H%M", acum)
	return "%s.%s" % (baza, extensie)


# ------------------------------------------------------------------- paginile HTML
# Cod 100% propriu, HTML/CSS/JS simplu fara framework/build (decizie de proiectare, cf.
# CERCETARE-INTERFATA-WEB-SI-STREAMING.md) -- niciun script extern (CDN), functioneaza offline pe
# reteaua locala. Codurile numerice de taste sunt citite din `keyids.py` (radacina depozitului, tabelul
# oficial Dreambox upstream), nu ghicite.
#
# texte simple, in romana, fara jeton/token in paginile obisnuite. Panoul primeste de la server
# un singur obiect de configurare (__CONFIG__, JSON scapat pentru <script>): in modul obisnuit doar tokenul
# CSRF al sesiunii si numele browserului; in modul jeton (cineva a deschis /panou?token=<jeton valid>, ca
# uneltele vechi) jetonul, fiindca pagina il avea deja in adresa. Jetonul nu e niciodata copiat din cerere,
# ci luat din configurarea serverului, doar dupa ce cererea a trecut verificarea.
_STIL_COMUN = """
  :root{
    --fundal:#14171c; --panou:#1c2129; --text:#e6e9ef; --text-slab:#8891a0;
    --accent:#2f8f5b; --rosu:#c0392b; --verde:#2f8f5b;
    --galben:#c9a227; --albastru:#2f6fa8; --bordura:#2a2f38;
  }
  *{box-sizing:border-box;}
  body{margin:0;background:var(--fundal);color:var(--text);font-family:system-ui,Segoe UI,Roboto,sans-serif;padding:16px;}
  a{color:#7fb8ff;}
"""

# Registrul paginilor web: fostul subsol „Toate paginile” al panoului, scos din pagina in 0.3.0 (marunte-030): meniul
# cadrului (cadru_web.py) le arata pe toate, iar cele fara loc in data/menu.xml le ia de aici, in „Alte pagini”. O pagina
# noua fara intrare in menu.xml se adauga aici. Randurile au forma de odinioara (doua spatii, <a href="/cale">Nume</a>,
# cate unul pe rand): _legaturiDisponibile le scoate sau le marcheaza dupa receptor si dupa menu.xml, rand cu rand.
_REGISTRU_PAGINI = """<footer>
  <a href="/canale">Canale</a>
  <a href="/jurnal">Ce e nou</a>
  <a href="/licente">Licențe</a>
  <a href="/scanare">Scanare</a>
  <a href="/antena">Orientarea și setarea antenei</a>
  <a href="/antena/lnb">Configurare LNB</a>
  <a href="/motor">Rotirea antenei</a>
  <a href="/antena/semnal">Găsire semnal</a>
  <a href="/ecrane">Ecranul de pornire</a>
  <a href="/acces-conditionat">Acces condiționat</a>
  <a href="/piste">Sunet și subtitrări</a>
  <a href="/subtitrari">Aspectul subtitrărilor</a>
  <a href="/traducere-subtitrari">Traducerea subtitrărilor</a>
  <a href="/traducere-configurare">Traducerea subtitrărilor: configurare pas cu pas</a>
  <a href="/accel">Accelerare 2D pe placa video</a>
  <a href="/cautare">Căutare canale</a>
  <a href="/ceas">Data și ora</a>
  <a href="/paznic">Paznicul receptorului</a>
  <a href="/forum-receptor">Forumul receptorului</a>
  <a href="/tv">TV în browser</a>
  <a href="/mod-sigur">Mod sigur și opririle interfeței</a>
  <a href="/procesor">Procesor</a>
  <a href="/afisaj">Afișajul din față</a>
  <a href="/copie-setari">Copia setărilor</a>
  <a href="/setari-din-copie">Setările importate</a>
  <a href="/import">Import canale și setări</a>
  <a href="/limba-interfata">Limba meniurilor</a>
  <a href="/limbi">Limba sunetului și a subtitrărilor</a>
  <a href="/temporizatoare">Înregistrări programate</a>
  <a href="/stocare">Locul înregistrărilor</a>
  <a href="/filme">Filmul de acum</a>
  <a href="/subtitrari-film">Subtitrările filmului</a>
  <a href="/teletext">Teletext</a>
  <a href="/descarcare-subtitrari">Descărcare subtitrări</a>
  <a href="/telecomenzi">Telecomenzi</a>
  <a href="/telecomanda-tv">Telecomanda televizorului</a>
  <a href="/informatii">Informații despre receptor</a>
  <a href="/acces-ssh">Parola receptorului</a>
  <a href="/meniu">Tot meniul receptorului</a>
  <a href="/programatori">Pentru programatori</a>
</footer>"""

# ------------------------------------------------------------------- telecomanda din panou
def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: panoul e scris in romana; textele marcate intra in po."""
	return text


# Numele paginilor din registru, pentru xgettext (registrul e un sir, iar _registruTradus le traduce pe rand). Un rand
# nou in _REGISTRU_PAGINI se scrie si aici (proba textelor panoului le compara).
_TEXTE_REGISTRU = (
	N_("Canale"), N_("Ce e nou"), N_("Licențe"), N_("Scanare"), N_("Orientarea și setarea antenei"),
	N_("Configurare LNB"), N_("Rotirea antenei"), N_("Găsire semnal"), N_("Ecranul de pornire"),
	N_("Acces condiționat"), N_("Sunet și subtitrări"), N_("Aspectul subtitrărilor"), N_("Traducerea subtitrărilor"),
	N_("Traducerea subtitrărilor: configurare pas cu pas"), N_("Accelerare 2D pe placa video"), N_("Căutare canale"),
	N_("Data și ora"), N_("Paznicul receptorului"), N_("Forumul receptorului"), N_("TV în browser"),
	N_("Mod sigur și opririle interfeței"),
	N_("Procesor"), N_("Afișajul din față"), N_("Copia setărilor"), N_("Setările importate"),
	N_("Import canale și setări"), N_("Limba meniurilor"), N_("Limba sunetului și a subtitrărilor"),
	N_("Înregistrări programate"), N_("Locul înregistrărilor"), N_("Filmul de acum"), N_("Subtitrările filmului"),
	N_("Teletext"), N_("Descărcare subtitrări"), N_("Telecomenzi"), N_("Telecomanda televizorului"),
	N_("Informații despre receptor"), N_("Parola receptorului"), N_("Tot meniul receptorului"), N_("Pentru programatori"),
)


def _registruTradus():
	"""Registrul paginilor cu numele in limba meniurilor receptorului, pentru meniul cadrului (grupa Alte pagini). Se
	traduce inainte de _legaturiDisponibile: scoaterile merg dupa adresa, iar semnul (netestat) se pune tradus dupa
	nume (proba 0.4.22: numele ramaneau in romana, cu semnul in engleza). Numele raman text simplu, ca cele romanesti:
	cadru_web.registru le scoate din legaturi, iar meniul le scapa la punere."""
	return re.sub(r'(<a href="[^"]*">)([^<]+)(</a>)', lambda m: m.group(1) + _t(m.group(2)) + m.group(3),
		_REGISTRU_PAGINI)


# Telecomanda de langa ecranul receptorului: mai mica, sub imagine sau langa ea, si extinsa, cu toate tastele
# telecomenzii originale. Doua feluri, din acelasi tabel: compacta (ce se apasa des) si toate tastele telecomenzii Viper,
# asezate ca pe telecomanda, de sus in jos. Codurile sunt ale telecomenzii fizice (Components/HdsTelecomenziDate.
# BUTOANE_VIPER, data/telecomanda-viper.json; proba test_telecomanda_panou le compara). Designul: fisele Stitch
# "Panou Control & Telecomanda" (desktop si telefon). id -> (cod Linux, textul de pe tasta, iconita, numele, clasa).
# Fara text, pe tasta e iconita; numele e cel citit (aria-label, title) si cel din "Trimis: ...".
_TASTE_PANOU = {
	"power": (116, "", "power", "POWER", "tl-power"),
	"mute": (113, "", "mut", "MUTE", ""),
	"ecran1": (373, "", "ecran1", N_("ecran 1"), ""),
	"ecran2": (227, "", "ecran2", N_("ecran 2"), ""),
	"ecran3": (438, "", "ecran3", N_("ecran 3"), ""),
	"1": (2, "1", None, "1", ""),
	"2": (3, "2", None, "2", ""),
	"3": (4, "3", None, "3", ""),
	"4": (5, "4", None, "4", ""),
	"5": (6, "5", None, "5", ""),
	"6": (7, "6", None, "6", ""),
	"7": (8, "7", None, "7", ""),
	"8": (9, "8", None, "8", ""),
	"9": (10, "9", None, "9", ""),
	"anterior": (412, "<", None, "<", ""),
	"0": (11, "0", None, "0", ""),
	"urmator": (407, ">", None, ">", ""),
	"epg": (365, "EPG", None, "EPG", ""),
	"info": (358, "Info", None, "Info", ""),
	"sus": (103, "", "sus", N_("sus"), "tl-sageata tl-a-sus"),
	"stanga": (105, "", "stanga", N_("stânga"), "tl-sageata tl-a-stanga"),
	"ok": (352, "OK", None, "OK", "tl-ok"),
	"dreapta": (106, "", "dreapta", N_("dreapta"), "tl-sageata tl-a-dreapta"),
	"jos": (108, "", "jos", N_("jos"), "tl-sageata tl-a-jos"),
	"menu": (139, N_("Meniu"), None, N_("Meniu"), ""),
	"exit": (174, N_("Ieșire"), None, N_("Ieșire"), ""),
	"audio": (392, "AUDIO", None, "AUDIO", ""),
	"ttx": (388, "TTX", None, "TTX", ""),
	"subt": (370, "SUBT", None, "SUBT", ""),
	"volplus": (115, "", "plus", "VOL+", ""),
	"volminus": (114, "", "minus", "VOL-", ""),
	"chplus": (402, "", "sus", "CH+", ""),
	"chminus": (403, "", "jos", "CH-", ""),
	"rosu": (398, N_("Roșu"), None, N_("Roșu"), "b-rosu"),
	"verde": (399, N_("Verde"), None, N_("Verde"), "b-verde"),
	"galben": (400, N_("Galben"), None, N_("Galben"), "b-galben"),
	"albastru": (401, N_("Albastru"), None, N_("Albastru"), "b-albastru"),
	"emc": (393, "EMC", None, "EMC", ""),
	"portal": (150, "Portal", None, "Portal", ""),
	"mplay": (395, "Mplay", None, "Mplay", ""),
	"timer": (359, "Timer", None, "Timer", ""),
	"salt_inapoi": (165, "", "salt_inapoi", N_("salt înapoi"), ""),
	"derulare_inapoi": (168, "", "derulare_inapoi", N_("derulare înapoi"), ""),
	"derulare_inainte": (208, "", "derulare_inainte", N_("derulare înainte"), ""),
	"salt_inainte": (163, "", "salt_inainte", N_("salt înainte"), ""),
	"pauza": (119, "", "pauza", N_("pauză"), ""),
	"stop": (128, "", "stop", N_("stop"), ""),
	"redare": (207, "", "redare", N_("redare"), ""),
	"inregistrare": (167, "", "inregistrare", N_("înregistrare"), "tl-rec"),
	"tv": (377, "TV", None, "TV", ""),
	"help": (138, "HELP", None, "HELP", ""),
	"fav": (364, "FAV", None, "FAV", ""),
	"radio": (385, "Radio", None, "Radio", ""),
}

# iconitele tastelor fara text (SVG 24x24, umplute cu culoarea textului), desenate aici dupa semnele de pe telecomanda
_TL_ICONITE = {
	"power": '<path d="M11 3h2v9h-2z"/><path d="M7.05 6.05l1.41 1.41a5 5 0 1 0 7.08 0l1.41-1.41a7 7 0 1 1-9.9 0z"/>',
	"mut": '<path d="M3 9v6h4l5 5V4L7 9H3zm18.6 1.4-1.4-1.4L18 11.2 15.8 9l-1.4 1.4 2.2 2.2-2.2 2.2 1.4 1.4 2.2-2.2 2.2 2.2 1.4-1.4-2.2-2.2z"/>',
	"ecran1": '<path fill-rule="evenodd" d="M2 5h20v14H2zM4 7v10h16V7z"/><path d="M6 9h5v6H6z"/>'
		'<path fill-rule="evenodd" d="M13 9h5v6h-5zm1.5 1.5v3h2v-3z"/>',
	"ecran2": '<path fill-rule="evenodd" d="M2 5h20v14H2zM4 7v10h16V7z"/><path d="M6 9h1.5v6H6zm10.5 0H18v6h-1.5z"/>'
		'<path fill-rule="evenodd" d="M9 9h6v6H9zm1.5 1.5v3h3v-3z"/>',
	"ecran3": '<path fill-rule="evenodd" d="M1 6h22v12H1zM3 8v8h18V8z"/>',
	"sus": '<path d="M7.4 15.4 12 10.8l4.6 4.6L18 14l-6-6-6 6z"/>',
	"jos": '<path d="M7.4 8.6 12 13.2l4.6-4.6L18 10l-6 6-6-6z"/>',
	"stanga": '<path d="M15.4 7.4 10.8 12l4.6 4.6L14 18l-6-6 6-6z"/>',
	"dreapta": '<path d="M8.6 16.6 13.2 12 8.6 7.4 10 6l6 6-6 6z"/>',
	"plus": '<path d="M11 5h2v14h-2zM5 11h14v2H5z"/>',
	"minus": '<path d="M5 11h14v2H5z"/>',
	"salt_inapoi": '<path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/>',
	"derulare_inapoi": '<path d="M11 18V6l-8.5 6zm.5-6 8.5 6V6z"/>',
	"derulare_inainte": '<path d="M4 18l8.5-6L4 6zm9-12v12l8.5-6z"/>',
	"salt_inainte": '<path d="M6 18l8.5-6L6 6zm10-12h2v12h-2z"/>',
	"pauza": '<path d="M6 5h4v14H6zm8 0h4v14h-4z"/>',
	"stop": '<path d="M6 6h12v12H6z"/>',
	"redare": '<path d="M8 5v14l11-7z"/>',
	"inregistrare": '<circle cx="12" cy="12" r="6"/>',
}


# tastele cu text care se traduce (cele marcate N_ in _TASTE_PANOU); celelalte texte (EPG, Info, OK, TV, Portal...)
# sunt etichetele de pe telecomanda si raman asa in orice limba (proba textelor panoului le compara cu tabelul)
_TL_TEXTE_TRADUSE = frozenset(("Meniu", "Ieșire", "Roșu", "Verde", "Galben", "Albastru"))


def _tlText(text):
	return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _tlTradus(text):
	"""Numele unei taste in limba meniurilor receptorului (builtins._, ca pe televizor), la servire; pe PC, fara
	traducere, asa cum e."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _tlTasta(id_tasta):
	"""O tasta: <button> cu codul (data-cod) si numele (data-nume); fara text, cu iconita, aria-label si title. Numele
	si textul tastei sunt traduse la servire: telecomanda intra in panou dupa traducerea lui (__TELECOMANDA__), deci
	_traducePagina nu le vede (probele 0.3.20: tastele cu iconita aveau numele in romana; proba 0.4.22: Roșu, Ieșire si
	celelalte taste cu text ramaneau in romana)."""
	cod, text, iconita, nume, clasa = _TASTE_PANOU[id_tasta]
	if iconita:
		nume = _tlTradus(nume)
		continut = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">%s</svg>' % _TL_ICONITE[iconita]
		citit = ' aria-label="%s" title="%s"' % (_tlText(nume), _tlText(nume))
	else:
		if text in _TL_TEXTE_TRADUSE:
			text = nume = _tlTradus(text)
		continut, citit = _tlText(text), ""
	return '<button type="button" class="tl-t%s" data-cod="%d" data-nume="%s"%s>%s</button>' % (
		(" " + clasa) if clasa else "", cod, _tlText(nume), citit, continut)


def _htmlTelecomanda():
	"""Telecomanda panoului (locul __TELECOMANDA__ din _PAGINA_PANOU): antetul cu alegerea Compact | Toate tastele,
	tastele compacte (Power, Mute; Meniu, EPG, Info, Iesire; VOL, cercul cu OK, CH; culorile; cifrele) si toate tastele
	telecomenzii Viper in ordinea de pe ea (in doua parti: pana la Meniu si Iesire, apoi de la sunet in jos)."""
	def taste(*idi):
		return "".join(_tlTasta(i) for i in idi)

	def rand(clasa, *idi):
		return '<div class="tl-rand %s">%s</div>' % (clasa, taste(*idi))

	def rocker(sus, jos, eticheta):
		return '<div class="tl-rocker">%s<span aria-hidden="true">%s</span>%s</div>' % (_tlTasta(sus), eticheta, _tlTasta(jos))
	cifre = '<div class="tl-cifre">%s</div>' % taste("1", "2", "3", "4", "5", "6", "7", "8", "9", "anterior", "0", "urmator")
	culori = rand("tl-r4 tl-culori", "rosu", "verde", "galben", "albastru")
	cerc = '<div class="tl-dpad">%s</div>' % taste("sus", "stanga", "ok", "dreapta", "jos")
	vol, ch = rocker("volplus", "volminus", "VOL"), rocker("chplus", "chminus", "CH")
	compacta = (rand("tl-capete", "power", "mute") + rand("tl-r4", "menu", "epg", "info", "exit") +
		'<div class="tl-nav">%s%s%s</div>' % (vol, cerc, ch) + culori + cifre)
	sus = (rand("tl-capete", "power", "mute") + rand("tl-r3", "ecran1", "ecran2", "ecran3") + cifre +
		rand("tl-capete", "epg", "info") + cerc + rand("tl-capete", "menu", "exit"))
	jos = ('<div class="tl-sunet">%s<div class="tl-mijloc">%s</div>%s</div>' % (vol, taste("audio", "ttx", "subt"), ch) +
		culori + rand("tl-r4", "emc", "portal", "mplay", "timer") +
		rand("tl-r4", "salt_inapoi", "derulare_inapoi", "derulare_inainte", "salt_inainte") +
		rand("tl-r4", "pauza", "stop", "redare", "inregistrare") + rand("tl-r4", "tv", "help", "fav", "radio"))
	return ('<section class="tl" id="telecomanda" data-mod="compact" aria-labelledby="tlTitlu">'
		'<div class="tl-cap"><h3 class="tl-titlu" id="tlTitlu">%s</h3>'
		'<div class="tl-comutator" role="group" aria-labelledby="tlTitlu">'
		'<button type="button" class="tl-mod" data-mod="compact" aria-pressed="true">%s</button>'
		'<button type="button" class="tl-mod" data-mod="toate" aria-pressed="false">%s</button></div></div>'
		'<div class="tl-taste tl-compact">%s</div>'
		'<div class="tl-taste tl-toate"><div class="tl-parte">%s</div><div class="tl-parte">%s</div></div>'
		'<div class="stare tl-stare" id="starTasta" role="status"></div></section>') % (
		_tlText(_tlTradus(N_("Telecomandă"))), _tlText(_tlTradus(N_("Compact"))), _tlText(_tlTradus(N_("Toate tastele"))),
		compacta, sus, jos)


_PAGINA_PANOU = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panou de control HD Satelit</title>
<style>""" + _STIL_COMUN + """
  h1{font-size:1.25rem;margin:0 auto 16px;max-width:1360px;}
  .grid{display:grid;grid-template-columns:1fr;gap:16px;max-width:1360px;margin:0 auto;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;}
  .card h2{font-size:.95rem;margin:0 0 12px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .status-linie{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--bordura);font-size:.9rem;}
  .status-linie:last-child{border-bottom:none;}
  .status-linie.cu-nota{flex-wrap:wrap;}
  .status-linie .nota-rand{flex-basis:100%;font-size:.8rem;color:var(--text-slab);line-height:1.35;}
  .captura-cutie{background:#000;border-radius:8px;overflow:hidden;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;}
  .captura-cutie img{width:100%;height:100%;object-fit:contain;display:block;}
  .captura-goala{color:var(--text-slab);font-size:.85rem;text-align:center;padding:16px;}
  .captura-butoane{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px;margin-top:10px;}
  .captura-butoane button{background:#242a33;color:var(--text);border:1px solid var(--bordura);border-radius:8px;padding:10px 8px;min-height:44px;font-size:.9rem;cursor:pointer;text-wrap:balance;}
  .captura-butoane button:active{background:var(--accent);}
  .captura-butoane button:disabled{opacity:.5;cursor:default;}
  .captura-nota{font-size:.75rem;color:var(--text-slab);margin-top:8px;line-height:1.35;}
  /* imaginea live in caseta ecranului (TV in browser, tv_web.py), pornita de butonul de sub capturi (Eduard, 12.10.2026) */
  .captura-butoane.live{grid-template-columns:repeat(auto-fit,minmax(190px,1fr));}
  .ascuns-live{display:none;}
  /* Ecranul receptorului cu telecomanda alaturi (cererea din 12.10.2026 19:48-19:49): pe lat telecomanda sta in dreapta
     ecranului si a imaginii live, pe ingust si pe telefon sub ele; compacta sau cu toate tastele telecomenzii Viper.
     Designul: fisele Stitch "Panou Control & Telecomanda" (desktop si telefon, proiectul interfetei web); temele Clasic si
     Pro le potrivesc in cadru_web.py (.tl). Cu toate tastele, pe ecranele foarte late, tastele stau pe doua coloane; pe
     celelalte ecranul ramane sus cat derulezi tastele. Un browser fara interogari de container le pune una sub alta. */
  .card-ecran{max-width:1360px;margin:0 auto 16px;container-type:inline-size;}
  /* pe ingust (si pe telefon): imaginea, imediat sub ea telecomanda, apoi butoanele si notele de sub imagine */
  .ecran-tel{display:flex;flex-direction:column;gap:16px;}
  .ecran-col{display:contents;}
  .ecran-img{order:1;} .ecran-tel>.tl{order:2;} .ecran-jos{order:3;}
  @container (min-width:700px){
    .ecran-tel{display:grid;grid-template-columns:minmax(0,1fr) 312px;align-items:start;}
    .ecran-col{display:block;position:sticky;top:calc(var(--h-antet,0px) + 12px);}
  }
  @container (min-width:1160px){
    .ecran-tel.cu-toate{grid-template-columns:minmax(0,1fr) 600px;}
    .ecran-tel.cu-toate .tl[data-mod="toate"] .tl-toate{display:grid;grid-template-columns:1fr 1fr;gap:0 16px;align-items:start;}
    .ecran-tel.cu-toate .tl-parte+.tl-parte{margin:0;padding:0 0 0 16px;border-top:0;border-left:1px solid #2a2f38;}
  }
  .tl{--tl-h:38px;background:#181c23;border:1px solid #2a2f38;border-radius:12px;padding:12px;-webkit-user-select:none;user-select:none;}
  @media (pointer:coarse){ .tl{--tl-h:44px;} }
  .tl-cap{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;margin:0 0 12px;}
  .tl-titlu{margin:0;font-size:15px;font-weight:600;}
  .tl-comutator{display:inline-flex;gap:2px;padding:2px;border:1px solid #2a2f38;border-radius:8px;background:#0f1216;}
  .tl .tl-comutator button{min-height:32px;padding:0 10px;border:0;border-radius:6px;background:transparent;color:#8891a0;font:inherit;font-size:12px;font-weight:600;cursor:pointer;}
  .tl .tl-comutator button[aria-pressed="true"]{background:var(--accent);color:#fff;}
  .tl[data-mod="toate"] .tl-compact,.tl:not([data-mod="toate"]) .tl-toate{display:none;}
  .tl-taste,.tl-parte{display:flex;flex-direction:column;gap:8px;}
  .tl-parte+.tl-parte{margin-top:4px;padding-top:12px;border-top:1px solid #2a2f38;}
  .tl-rand,.tl-cifre{display:grid;gap:6px;}
  .tl-r3,.tl-cifre{grid-template-columns:repeat(3,minmax(0,1fr));}
  .tl-r4{grid-template-columns:repeat(4,minmax(0,1fr));}
  .tl-rand.tl-capete{display:flex;justify-content:space-between;}
  .tl-capete .tl-t{width:30%;}
  .tl button.tl-t{display:inline-flex;align-items:center;justify-content:center;min-width:0;min-height:var(--tl-h);padding:0 4px;border:1px solid #2a2f38;border-radius:8px;background:#242a33;color:#e6e9ef;font:inherit;font-size:13px;font-weight:600;line-height:1.1;cursor:pointer;touch-action:manipulation;}
  .tl button.tl-t:active{filter:brightness(1.35);}
  .tl button.tl-t svg{width:20px;height:20px;fill:currentColor;flex:none;}
  .tl-cifre button.tl-t{font-size:15px;}
  .tl button.tl-power{color:#ff8a80;background:rgba(255,107,94,.12);}
  .tl button.tl-rec{color:#ff8a80;}
  .tl-culori button.tl-t{min-height:30px;border-radius:999px;font-size:12px;}
  .tl button.b-rosu{background:var(--rosu);border-color:var(--rosu);color:#fff;}
  .tl button.b-verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  .tl button.b-galben{background:var(--galben);border-color:var(--galben);color:#241d00;}
  .tl button.b-albastru{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  .tl-nav,.tl-sunet{display:grid;grid-template-columns:48px minmax(0,1fr) 48px;gap:8px;align-items:center;}
  .tl-rocker{display:flex;flex-direction:column;gap:4px;padding:4px;border:1px solid #2a2f38;border-radius:12px;background:#0f1216;text-align:center;}
  .tl-rocker span{font-size:11px;font-weight:700;letter-spacing:.06em;color:#8891a0;padding:4px 0;}
  .tl-mijloc{display:flex;flex-direction:column;gap:6px;}
  .tl-dpad{display:grid;grid-template-columns:1fr 60px 1fr;grid-template-rows:1fr 60px 1fr;place-items:center;width:156px;height:156px;margin:0 auto;border:1px solid #2a2f38;border-radius:50%;background:#0f1216;}
  .tl-dpad .tl-a-sus{grid-area:1/2;} .tl-dpad .tl-a-stanga{grid-area:2/1;} .tl-dpad .tl-ok{grid-area:2/2;}
  .tl-dpad .tl-a-dreapta{grid-area:2/3;} .tl-dpad .tl-a-jos{grid-area:3/2;}
  .tl .tl-dpad button.tl-sageata{width:44px;min-height:40px;border:0;background:transparent;}
  .tl .tl-dpad button.tl-ok{width:60px;height:60px;min-height:60px;border:0;border-radius:50%;background:var(--accent);color:#fff;font-size:16px;font-weight:700;}
  .tl-stare{margin-top:12px;}
  .stare{font-size:.75rem;color:var(--text-slab);margin-top:10px;min-height:1em;}
  form.cauta-setari{max-width:1360px;margin:0 auto 16px;display:flex;gap:8px;}
  form.cauta-setari input{flex:1;min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  form.cauta-setari button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  footer{max-width:1360px;margin:16px auto 0;color:var(--text-slab);font-size:.8rem;display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;}
  footer button{background:none;border:none;padding:0;color:#7fb8ff;text-decoration:underline;font:inherit;cursor:pointer;}
</style>
</head>
<body>
<h1>Panou de control HD Satelit</h1>
<form class="cauta-setari" id="cautaSetari" action="/cauta-setari" method="get" role="search"><input type="search" name="q" maxlength="60" placeholder="Caută setări: scrie un cuvânt, de exemplu subtitrări" aria-label="Caută setări" autocomplete="off"><button type="submit">Caută</button></form>
<p id="bandaModSigur" style="display:none;max-width:1360px;margin:0 auto 12px;padding:10px 14px;border:1px solid #f5b83d;border-radius:8px;background:#2b2107;line-height:1.45"><a href="/mod-sigur" id="bandaModSigurText" style="color:#f5b83d"></a></p>
<p id="bandaAltaImagine" style="display:none;max-width:1360px;margin:0 auto 12px;padding:10px 14px;border:1px solid #f5b83d;border-radius:8px;background:#2b2107;line-height:1.45"><a href="/import" id="bandaAltaImagineText" style="color:#f5b83d"></a></p>
<div class="card card-ecran">
  <h2>Ecranul receptorului</h2>
  <div class="ecran-tel" id="ecranTel">
    <div class="ecran-col">
      <div class="ecran-img">
        <div class="captura-cutie" id="cutieCaptura">
          <img id="captura" alt="Imaginea de pe ecranul receptorului" onerror="capturaIndisponibila()" onload="capturaDisponibila()">
        </div>
        <div id="playerPanou" class="ascuns-live"></div>
        <div class="stare" id="notaCaptura">Imaginea se actualizează la fiecare 3 secunde.</div>
      </div>
      <div class="ecran-jos">
        <div class="captura-butoane">
          <button type="button" onclick="descarcaCaptura('all')">Descarcă captura cu afișaj OSD</button>
          <button type="button" onclick="descarcaCaptura('video')">Descarcă captura fără afișaj OSD</button>
        </div>
        <div class="captura-butoane live">
          <button type="button" id="butonLive" onclick="comutaLive()"><span aria-hidden="true">&#9654;</span> Privește live aici</button>
          <button type="button" id="butonM3u" onclick="descarcaM3uPanou()" title="Canalul de acum de pe televizor, pentru VLC, Kodi sau alt player din casă"><span aria-hidden="true">&#8595;</span> Descarcă playlist (M3U)</button>
        </div>
        <div class="stare" id="stareLive" role="status"></div>
        <div class="captura-nota">Cu meniul: exact ce vezi pe televizor. Fără meniu: numai imaginea canalului, fără ce desenează receptorul peste ea (meniuri, bara de informații, subtitrări).</div>
        <div class="stare" id="stareDescarcare" role="status"></div>
      </div>
    </div>
    __TELECOMANDA__
  </div>
</div>
<div class="grid">
  <div class="card">
    <h2>Acum pe receptor</h2>
    <div id="stare">
      <div class="status-linie"><span>Canal</span><span id="stServiciu">-</span></div>
      <div class="status-linie cu-nota" id="stSemnalRand"><span>Semnal</span><span id="stSemnal">-</span><small class="nota-rand" id="stSemnalText"></small></div>
      <div class="status-linie"><span>Volum</span><span id="stVolum">-</span></div>
      <div class="status-linie"><span>Sonor oprit</span><span id="stMut">-</span></div>
      <div class="status-linie"><span>Standby</span><span id="stStandby">-</span></div>
      <div class="status-linie cu-nota"><span>HbbTV</span><span id="stHbbtv">-</span><small class="nota-rand" id="stHbbtvText"></small></div>
      <div class="status-linie" id="stRadio" style="display:none"><a href="/radio">Radio: vezi pagina radio (postul, piesa, barele)</a></div>
      <div class="status-linie"><a href="/canale">Lista de canale: alege și pornește un canal</a></div>
      <div class="status-linie"><a href="/tv">TV în browser: privește canalul live pe acest PC sau telefon</a></div>
      <div class="status-linie"><a href="/ghid">Ghidul canalului: emisiunile și înregistrarea lor</a></div>
    </div>
  </div>
</div>
<footer>
  <span id="numeBrowser"></span>
  <button type="button" id="deconectare">Deconectează acest browser</button>
</footer>
<script>
var CFG = __CONFIG__;
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    if(!r.ok){ throw new Error("HTTP " + r.status); }
    return r.json();
  });
}
// „Caută setări” din capul panoului: in modul cu jeton, jetonul pleaca si cu formularul
(function(){
  var f = document.getElementById("cautaSetari");
  if(f && CFG.jeton){ var t = document.createElement("input"); t.type = "hidden"; t.name = "token"; t.value = CFG.jeton; f.appendChild(t); }
})();
// Telecomanda de langa ecran (tastele le face _htmlTelecomanda din plugin.py): compacta sau toate tastele telecomenzii
// Viper, cu aceleasi coduri ca telecomanda fizica. Alegerea ramane in acest browser (localStorage; fara el, compacta).
// O tasta tinuta 0,7 s pleaca drept apasare lunga, ca in pagina /telecomenzi; din tastatura (Enter, spatiu), apasare
// scurta. Dupa fiecare tasta, captura de langa ea vine mai repede (grabesteCaptura).
var TL_CHEIE = "hdsTelecomanda";
function tlModCitit(){
  try { return localStorage.getItem(TL_CHEIE) === "toate" ? "toate" : "compact"; } catch(e) { return "compact"; }
}
function tlAlege(mod, tine){
  var tl = document.getElementById("telecomanda"), et = document.getElementById("ecranTel");
  if(!tl || !tl.querySelectorAll){ return; }
  tl.setAttribute("data-mod", mod);
  if(et && et.classList){ et.classList.toggle("cu-toate", mod === "toate"); }
  Array.prototype.forEach.call(tl.querySelectorAll(".tl-mod"), function(b){
    b.setAttribute("aria-pressed", b.getAttribute("data-mod") === mod ? "true" : "false");
  });
  if(tine){ try { localStorage.setItem(TL_CHEIE, mod); } catch(e) {} }
}
function tasta(cod, buton, lung){
  var stare = document.getElementById("starTasta");
  var nume = (buton && buton.getAttribute && buton.getAttribute("data-nume")) || (buton && buton.textContent) || String(cod);
  // imaginea live urmeaza televizorul: o tasta care schimba canalul arata semnul pe loc, inainte de raspuns (player.js)
  if(window.HDS_LIVE_TASTA){ window.HDS_LIVE_TASTA(cod, !!lung); }
  cerere("/api/remotecontrol?command=" + cod + (lung ? "&lung=1" : ""), "POST").then(function(){
    stare.textContent = "Trimis: " + nume + (lung ? " (apăsare lungă)" : "");
    if(window.HDS_LIVE_TASTA_TRIMISA){ window.HDS_LIVE_TASTA_TRIMISA(cod, !!lung); }
    grabesteCaptura();
  }).catch(function(e){
    stare.textContent = "Tasta nu a ajuns la receptor (" + e.message + ").";
  });
}
(function(){
  var tl = document.getElementById("telecomanda");
  if(!tl || !tl.querySelectorAll){ return; }
  tlAlege(tlModCitit(), false);
  Array.prototype.forEach.call(tl.querySelectorAll(".tl-mod"), function(b){
    b.addEventListener("click", function(){ tlAlege(b.getAttribute("data-mod"), true); });
  });
  var cuIndicator = !!window.PointerEvent, tinut = null;
  function lasa(){ if(tinut){ clearTimeout(tinut); tinut = null; } }
  Array.prototype.forEach.call(tl.querySelectorAll("button[data-cod]"), function(b){
    var cod = parseInt(b.getAttribute("data-cod"), 10);
    if(cuIndicator){
      b.addEventListener("pointerdown", function(e){
        if(e.button){ return; }   // numai butonul principal al mouse-ului, degetul sau creionul
        lasa();
        tinut = setTimeout(function(){ tinut = null; tasta(cod, b, true); }, 700);
      });
      b.addEventListener("pointerup", function(e){
        if(e.button || !tinut){ return; }
        lasa();
        tasta(cod, b, false);
      });
      b.addEventListener("pointercancel", lasa);
      b.addEventListener("pointerleave", lasa);
      b.addEventListener("contextmenu", function(e){ e.preventDefault(); });
    }
    // Enter sau spatiu pe tasta aleasa: clic fara indicator (detail 0); clicul mouse-ului l-a trimis pointerup
    b.addEventListener("click", function(e){ if(!cuIndicator || !e.detail){ tasta(cod, b, false); } });
  });
})();
function capturaIndisponibila(){
  capturaInLucru = false;
  if(live.pornit){ return; }
  var cutie = document.getElementById("cutieCaptura");
  var img = document.getElementById("captura");
  img.style.display = "none";
  if(!cutie.querySelector(".captura-goala")){
    var gol = document.createElement("div");
    gol.className = "captura-goala";
    gol.textContent = "Imaginea ecranului nu este disponibilă acum.";
    cutie.appendChild(gol);
  }
  planificaCaptura();
}
function capturaDisponibila(){
  capturaInLucru = false;
  // cat merge imaginea live, o captura terminata dupa pornire nu se mai arata langa ea si nu cere alta
  if(live.pornit){ return; }
  // o captura ULTERIOARA poate reusi chiar daca una anterioara a esuat: readuce imaginea
  var cutie = document.getElementById("cutieCaptura");
  var img = document.getElementById("captura");
  img.style.display = "block";
  var gol = cutie.querySelector(".captura-goala");
  if(gol){ gol.remove(); }
  planificaCaptura();
}
function actualizeazaCaptura(){
  // cat merge imaginea live in caseta, capturile stau; le reporneste opresteLive
  if(live.pornit){ return; }
  // cat se descarca o captura, caseta asteapta: receptorul face o singura captura odata
  if(descarcareInCurs){ setTimeout(actualizeazaCaptura, 1000); return; }
  capturaInLucru = true;
  document.getElementById("captura").src = adresa("/api/screenshot?format=jpg&quality=70&width=960&_=" + Date.now());
}
var descarcareInCurs = false;
// ceasul capturii urmatoare; capturaInLucru: o captura ceruta, fara raspuns inca; capturaGrabita: dupa ea, 0,5 s
var ceasCaptura = null, capturaInLucru = false, capturaGrabita = false;
// Imaginea live in caseta ecranului: canalul de pe televizor, prin transmisia paginii /tv (tv_web.py; mpegts.js venit
// cu imaginea, incarcat numai la prima apasare; la imaginea MPEG-2, playerul wasm hds-player.js, ales de player.js).
// Capturile stau cat merge; la oprire (buton, eroare) revin.
// Imaginea URMEAZA TELEVIZORUL (player.js, urmeazaTv): cand televizorul schimba canalul (din telecomanda de aici, din
// cea adevarata, din ghid), imaginea trece singura pe canalul nou, cu semnul "Se schimbă canalul..." cat dureaza.
var live = {pornit: false, player: null, inLucru: false};
var refTvPanou = "";
window.HDS_LIVE_TASTA = function(cod, lung){
  if(live.pornit && live.player && live.player.tastaTelecomanda){ live.player.tastaTelecomanda(cod, lung); }
};
window.HDS_LIVE_TASTA_TRIMISA = function(cod, lung){
  if(live.pornit && live.player && live.player.tastaTrimisa){ live.player.tastaTrimisa(cod, lung); }
};
// Imaginea live in panou: playerul comun (/tv/player.js, acelasi ca in pagina /tv si in "Vezi live" din /canale), cu
// stratul receptorului peste imagine si butoanele sub ea. Cat merge, caseta capturilor sta ascunsa si capturile nu se cer.
function stareLive(text, eroare){
  var s = document.getElementById("stareLive");
  s.textContent = text || "";
  s.style.color = eroare ? "#ff8a80" : "";
}
function incarcaPlayerul(){
  return new Promise(function(da, nu){
    if(window.HdsPlayer){ da(); return; }
    var s = document.createElement("script");
    s.src = "/tv/player.js";
    s.onload = function(){ da(); };
    s.onerror = function(){ nu(new Error("Playerul nu s-a încărcat de pe receptor.")); };
    document.head.appendChild(s);
  });
}
function butonLive(text){
  document.getElementById("butonLive").innerHTML = text;
}
function comutaLive(){
  if(live.inLucru){ return; }
  if(live.pornit){ opresteLive(true, ""); } else { pornesteLive(); }
}
function pornesteLive(){
  if(CFG.jeton){ stareLive("Imaginea live merge numai cu browserul conectat: deschide panoul fără cheia din adresă.", true); return; }
  live.inLucru = true;
  stareLive("");
  incarcaPlayerul().then(function(){
    live.inLucru = false;
    if(!live.player){
      live.player = HdsPlayer.creeaza(document.getElementById("playerPanou"), {csrf: CFG.csrf, textOprire: "Înapoi la captură",
        urmeazaTv: true, laOprire: function(){ opresteLive(false, ""); }});
      // mouse-ul pe imaginea live si telecomanda pe ecranul intreg (mouse-ecran.js, pus de mouse_web.in_panou)
      if(window.HDS_MOUSE_PLAYER){ window.HDS_MOUSE_PLAYER(live.player); }
    }
    live.pornit = true;
    document.getElementById("cutieCaptura").classList.add("ascuns-live");
    document.getElementById("notaCaptura").classList.add("ascuns-live");
    document.getElementById("playerPanou").classList.remove("ascuns-live");
    butonLive('<span aria-hidden="true">&#9632;</span> Oprește live (înapoi la captură)');
    live.player.porneste("", "");
  }).catch(function(e){
    live.inLucru = false;
    stareLive(e.message || "Receptorul nu răspunde.", true);
  });
}
function opresteLive(trimite, text){
  var era = live.pornit;
  if(live.player && trimite){ live.player.opreste(true); }
  live.pornit = false;
  document.getElementById("playerPanou").classList.add("ascuns-live");
  document.getElementById("cutieCaptura").classList.remove("ascuns-live");
  document.getElementById("notaCaptura").classList.remove("ascuns-live");
  document.getElementById("captura").style.display = "block";
  butonLive('<span aria-hidden="true">&#9654;</span> Privește live aici');
  stareLive(text || "", !!text);
  if(era){ actualizeazaCaptura(); }
}
function descarcaM3uPanou(){
  // playlistul canalului de acum de pe televizor (aceeasi cerere ca butonul din player: /api/tv-m3u)
  if(CFG.jeton){ stareLive("Playlistul se face numai cu browserul conectat: deschide panoul fără cheia din adresă.", true); return; }
  if(!refTvPanou){ stareLive("Receptorul nu spune ce canal e pe televizor.", true); return; }
  var ref = refTvPanou;
  incarcaPlayerul().then(function(){
    var st = live.player && live.player.ultimaStare;
    if(live.pornit && (!st || st.sesiuni_max === 1)){
      // receptorul trimite un singur flux odata: imaginea din pagina se opreste, ca VLC sa poata porni
      opresteLive(true, "");
    }
    var q = new URLSearchParams(); q.set("ref", ref);
    return HdsPlayer.descarcaPlaylist(q, CFG.csrf).then(function(nume){
      stareLive("Playlistul s-a descărcat (" + nume + "). Deschide-l în VLC sau în alt player din casă.", false);
    });
  }).catch(function(e){ stareLive(e.message || "Playlistul nu s-a putut descărca.", true); });
}
function numeCapturaLocal(mod, tip){
  // numele dupa ceasul browserului, cand raspunsul nu are antetul Content-Disposition
  function d(n){ return (n < 10 ? "0" : "") + n; }
  var t = new Date();
  var sufix = mod === "video" ? "-fara-meniu" : (mod === "osd" ? "-meniu" : "");
  return "captura-receptor" + sufix + "-" + t.getFullYear() + "-" + d(t.getMonth() + 1) + "-" + d(t.getDate()) +
    "-" + d(t.getHours()) + d(t.getMinutes()) + (tip.indexOf("png") !== -1 ? ".png" : ".jpg");
}
function numeDinAntet(antet){
  var m = /filename="?([A-Za-z0-9._-]+)"?/.exec(antet || "");
  return m ? m[1] : "";
}
function salveazaFisier(date, nume){
  var url = URL.createObjectURL(date);
  var a = document.createElement("a");
  a.href = url;
  a.download = nume;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(function(){ URL.revokeObjectURL(url); }, 60000);
}
function descarcaCaptura(mod){
  if(descarcareInCurs){ return; }
  descarcareInCurs = true;
  var butoane = document.querySelectorAll(".captura-butoane button");
  var stare = document.getElementById("stareDescarcare");
  var incercari = 0;
  var i;
  for(i = 0; i < butoane.length; i++){ butoane[i].disabled = true; }
  stare.textContent = "Se pregătește captura...";
  function gata(text){
    descarcareInCurs = false;
    for(var j = 0; j < butoane.length; j++){ butoane[j].disabled = false; }
    stare.textContent = text;
  }
  function incearca(){
    // termenul acopera captura (sub o secunda) si o retea lenta; fara el, o conexiune pierduta ar lasa butoanele oprite
    var opritor = window.AbortController ? new AbortController() : null;
    var ceas = opritor ? setTimeout(function(){ opritor.abort(); }, 20000) : null;
    var optiuni = {cache: "no-store", credentials: "same-origin"};
    if(opritor){ optiuni.signal = opritor.signal; }
    fetch(adresa("/api/screenshot?format=jpg&quality=95&mode=" + mod + "&download=1&_=" + Date.now()), optiuni).then(function(r){
      if(r.status === 503 && incercari < 10){
        // 503: e in curs captura pentru caseta; se reincearca dupa ea
        incercari++;
        if(ceas){ clearTimeout(ceas); }
        setTimeout(incearca, 700);
        return;
      }
      if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
      if(!r.ok){ throw new Error("HTTP " + r.status); }
      var nume = numeDinAntet(r.headers.get("content-disposition")) || numeCapturaLocal(mod, r.headers.get("content-type") || "");
      return r.blob().then(function(date){
        if(ceas){ clearTimeout(ceas); }
        salveazaFisier(date, nume);
        gata("Captura s-a descărcat.");
      });
    }).catch(function(e){
      if(ceas){ clearTimeout(ceas); }
      var motiv = (e && e.name === "AbortError") ? "receptorul nu a răspuns" : (e && e.message) || "eroare";
      gata("Captura nu s-a putut descărca (" + motiv + ").");
    });
  }
  incearca();
}
function planificaCaptura(){
  // urmatoarea cerere DOAR dupa ce cea curenta s-a terminat (onload/onerror), niciodata pe un cronometru
  // fix: altfel mai multe procese 'grab' concurente pe receptor daca o captura intarzie. Serverul are si
  // el bariera lui (`_captura_in_curs`, 503 daca e deja una in curs).
  clearTimeout(ceasCaptura);
  ceasCaptura = setTimeout(actualizeazaCaptura, capturaGrabita ? 500 : 3000);
  capturaGrabita = false;
}
// dupa o tasta a telecomenzii: captura urmatoare vine dupa o jumatate de secunda, nu dupa 3, ca efectul sa se vada pe
// loc; tot una singura odata (cu una in curs sau cu o descarcare, cea de dupa ea vine mai repede)
function grabesteCaptura(){
  if(live.pornit){ return; }
  if(capturaInLucru || descarcareInCurs){ capturaGrabita = true; return; }
  clearTimeout(ceasCaptura);
  ceasCaptura = setTimeout(actualizeazaCaptura, 500);
}
var hbbtvCanal = null, hbbtvCand = 0;
function actualizeazaHbbtv(ref){
  // starea HbbTV (/api/portal): la schimbarea canalului si cel mult o data la 30 s pe acelasi canal
  if(ref === hbbtvCanal && Date.now() - hbbtvCand < 30000){ return; }
  hbbtvCanal = ref; hbbtvCand = Date.now();
  cerere("/api/portal").then(function(p){
    document.getElementById("stHbbtv").textContent = p.scurt || "-";
    // mesajul intreg sub rand, mai mic (si pe telefon, unde titlul unui element nu se vede)
    document.getElementById("stHbbtvText").textContent = p.activ ? (p.text || "") : "";
  }).catch(function(){});
}
// semnalul si calitatea canalului care merge, ca barele SEMNAL / CALITATE de pe televizor (radio_web.semnal_panou); la
// un post DAB+ / program DVB-T2 din satelit, ale tunerului care tine purtatorul. Dedesubt: tunerul, sistemul, „fără semnal”
// sau „fără date de la tuner”
function arataSemnal(s){
  s = s || {};
  var parti = [];
  if(s.putere !== null && s.putere !== undefined){ parti.push(s.putere + "%"); }
  if(s.calitate !== null && s.calitate !== undefined){ parti.push("calitate " + s.calitate + "%"); }
  var v = document.getElementById("stSemnal");
  v.textContent = parti.length ? parti.join(" · ") : "-";
  v.style.color = s.slab ? "#ff6b5e" : "";
  document.getElementById("stSemnalText").textContent = s.text || "";
}
function actualizeazaStare(){
  cerere("/api/statusinfo").then(function(d){
    if(window.HDS_ANTET){ window.HDS_ANTET.stare(d); }
    // posturile DAB+ / DVB-T2 din satelit: felul dupa nume, ca in lista de canale de pe televizor
    refTvPanou = d.currservice_serviceref || "";
    var cale = (d.currservice_serviceref || "").toLowerCase().replace(/%3a/g, ":");
    var fel = (cale.indexOf("127.0.0.1:8898/dab/") >= 0 || cale.indexOf("127.0.0.1:8888/dab/") >= 0) ? "DAB+" :
      (cale.indexOf("127.0.0.1:8889/t2/") >= 0 ? "DVB-T2" : "");
    document.getElementById("stServiciu").textContent = (d.currservice_name || "necunoscut") + (fel ? " · " + fel : "");
    arataSemnal(d.semnal);
    var dv = d.dvbi || {};
    if(dv.prin_internet){
      document.getElementById("stServiciu").textContent += " · DVB-I";
      document.getElementById("stSemnal").textContent = "prin internet";
      document.getElementById("stSemnal").style.color = "";
      document.getElementById("stSemnalText").textContent = dv.retea || "";
    } else if(dv.are){
      document.getElementById("stServiciu").textContent += " · are și DVB-I";
    }
    document.getElementById("stVolum").textContent = d.volume >= 0 ? d.volume : "-";
    document.getElementById("stMut").textContent = d.muted ? "da" : "nu";
    document.getElementById("stStandby").textContent = d.in_standby ? "da" : "nu";
    document.getElementById("bandaModSigurText").textContent = d.mod_sigur || "";
    document.getElementById("bandaModSigur").style.display = d.mod_sigur ? "" : "none";
    document.getElementById("bandaAltaImagineText").textContent = d.alta_imagine || "";
    document.getElementById("bandaAltaImagine").style.display = d.alta_imagine ? "" : "none";
    actualizeazaHbbtv(d.currservice_serviceref || "");
    var tipServiciu = ((d.currservice_serviceref || "").split(":")[2] || "").toLowerCase();
    document.getElementById("stRadio").style.display = (tipServiciu === "2" || tipServiciu === "a") ? "" : "none";
  }).catch(function(){}).then(function(){
    setTimeout(actualizeazaStare, 3000);
  });
}
(function(){
  if(CFG.browser){ document.getElementById("numeBrowser").textContent = "Acest browser: " + CFG.browser + "."; }
  var buton = document.getElementById("deconectare");
  if(CFG.jeton || !CFG.browser){ buton.style.display = "none"; return; }
  buton.addEventListener("click", function(){
    if(!confirm("Deconectezi acest browser? Pentru a-l folosi din nou vei avea nevoie de un cod nou de pe televizor.")){ return; }
    cerere("/deconectare", "POST").catch(function(){}).then(function(){ location.replace("/"); });
  });
})();
actualizeazaCaptura();
actualizeazaStare();
</script>
</body>
</html>
"""

_PAGINA_ASOCIERE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conectare la receptor</title>
<style>""" + _STIL_COMUN + """
  body{min-height:100vh;display:flex;align-items:center;justify-content:center;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:12px;padding:24px;max-width:420px;width:100%;}
  h1{font-size:1.3rem;margin:0 0 8px;}
  p{margin:0 0 16px;line-height:1.45;}
  input{width:100%;font-size:2rem;letter-spacing:.3em;text-align:center;padding:12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);}
  button{width:100%;margin-top:12px;padding:14px;font-size:1rem;border-radius:8px;border:none;background:var(--accent);color:#fff;cursor:pointer;}
  button.secundar{background:transparent;border:1px solid var(--bordura);color:var(--text);}
  .stare{min-height:1.4em;margin-top:14px;color:#ffd479;font-size:.95rem;line-height:1.4;}
  .nota{margin:18px 0 0;color:var(--text-slab);font-size:.82rem;}
</style>
</head>
<body>
<div class="card">
  <h1>Conectare la receptor</h1>
  <p>Introdu codul afișat pe televizor.</p>
  <form id="formular" autocomplete="off">
    <input id="cod" name="cod" inputmode="numeric" autocomplete="one-time-code" maxlength="12" placeholder="00 00 00" aria-label="Codul de pe televizor" required autofocus>
    <button type="submit">Conectează</button>
  </form>
  <div class="stare" id="stare" role="status">Se cere codul...</div>
  <button type="button" class="secundar" id="reafiseaza">Afișează din nou codul pe televizor</button>
  <p class="nota">Codul apare pe televizor când receptorul arată un canal, nu în meniu și nu în standby. Este valabil o oră. După conectare, acest browser rămâne conectat un an.</p>
</div>
<script>
var stare = document.getElementById("stare");
function trimite(cale, date){
  return fetch(cale, {
    method: "POST", cache: "no-store", credentials: "same-origin",
    headers: {"Content-Type": "application/x-www-form-urlencoded"},
    body: new URLSearchParams(date).toString()
  }).then(function(r){
    return r.json().catch(function(){ return {result: false, mesaj: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function cereCod(reafiseaza){
  trimite("/asociere/cod", {reafiseaza: reafiseaza ? "1" : "0"}).then(function(d){
    stare.textContent = d.mesaj || "";
  }).catch(function(){
    stare.textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.";
  });
}
document.getElementById("formular").addEventListener("submit", function(e){
  e.preventDefault();
  trimite("/asociere", {cod: document.getElementById("cod").value}).then(function(d){
    if(d.result){ stare.textContent = "Conectat. Se deschide panoul..."; location.replace("/"); return; }
    stare.textContent = d.mesaj || "Codul nu a fost primit.";
    document.getElementById("cod").select();
  }).catch(function(){
    stare.textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.";
  });
});
document.getElementById("reafiseaza").addEventListener("click", function(){ cereCod(true); });
cereCod(false);
</script>
</body>
</html>
"""

_PAGINA_PROGRAMATORI = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pentru programatori</title>
<style>""" + _STIL_COMUN + """
  main{max-width:760px;margin:0 auto;line-height:1.5;}
  h1{font-size:1.25rem;} h2{font-size:1rem;color:var(--text-slab);margin-top:24px;}
  code{background:#0f1216;border:1px solid var(--bordura);border-radius:4px;padding:1px 5px;font-size:.88em;overflow-wrap:anywhere;}
  li{margin:6px 0;}
  .buton{display:inline-block;padding:10px 18px;background:#1f771f;color:#fff;text-decoration:none;border-radius:6px;}
</style>
</head>
<body>
<main>
<h1>Pentru programatori</h1>
<p>Receptorul are un API JSON simplu, folosit și de panoul de control.</p>
<h2>Adrese</h2>
<ul>
  <li><code>GET /api/statusinfo</code>: canalul curent, volumul, standby</li>
  <li><code>GET /api/portal</code>: starea HbbTV a canalului care rulează (da, nu are, încă nu se știe), cu mesajul arătat pe televizor la tasta PORTAL</li>
  <li><code>GET /api/remotecontrol?command=&lt;cod&gt;&amp;lung=1</code>: apasă o tastă ca de pe telecomanda receptorului (coduri de tastă Linux, de exemplu 352 pentru OK); cu <code>lung=1</code>, apăsare lungă</li>
  <li><code>GET /api/mouse?fel=clic|dublu|drag|dragend|rotita|dreapta|mijloc&amp;xp=&amp;yp=</code>: mouse-ul pe ecranul televizorului, ca în emulator: <code>xp</code>, <code>yp</code> = locul în procente din ecran (sau <code>x</code>, <code>y</code> în pixelii ecranului, 1920x1080); <code>clic</code> alege rândul de sub mouse, iar pe rândul ales sau cu <code>clicuri=2</code> dă OK; un buton colorat = tasta lui; <code>drag</code> (cu <code>x0p</code>, <code>y0p</code> = locul apăsării, <code>nou=1</code> la prima mișcare) și <code>dragend</code> = trasul pe bara de derulare; <code>rotita&amp;pasi=-12..12</code> = sus/jos (3 pași sau mai mulți = o pagină); <code>dreapta</code> = Meniu, <code>mijloc</code> = Ieșire. Răspunsul spune ce s-a făcut (<code>facut</code>: selectie, ok, buton, bara, derulare, tasta, nimic). Din browser, cu POST și antetul <code>X-HDS-CSRF</code>, ca <code>remotecontrol</code></li>
  <li><code>GET /api/zap?sRef=&lt;referință&gt;</code>: schimbă canalul</li>
  <li><code>GET /api/screenshot?format=jpg|png&amp;quality=N&amp;width=N&amp;mode=all|video|osd&amp;download=1</code>: imaginea de pe ecran; <code>mode</code>: <code>all</code> cu afișajul OSD (implicit), <code>video</code> numai imaginea canalului, <code>osd</code> numai afișajul OSD; <code>download=1</code>: descărcare ca fișier, cu data și ora receptorului în nume</li>
  <li><code>GET /api/jurnal</code>: jurnalul de versiuni (ce s-a schimbat la fiecare actualizare)</li>
  <li><code>GET /api/motor</code>: starea rotirii antenei (de unde, pana unde, poziția estimată, cât mai are de mers)</li>
  <li><code>GET /api/fonturi?cauta=&lt;text&gt;</code>: familiile libere de pe Google Fonts și fonturile deja descărcate</li>
  <li><code>POST /api/fonturi-descarca?familie=&lt;Familia&gt;&amp;mare=1</code>: descarcă, verifică și înregistrează un font</li>
  <li><code>POST /api/fonturi-sterge?alias=&lt;NumeInSkin&gt;</code>: șterge un font descărcat</li>
  <li><code>GET /api/interfete-cam?reincarca=1</code>: modulele de acces condiționat instalate și interfețele lor web, cu numele date de fiecare modul (fără <code>reincarca</code> poate veni o căutare făcută cu câteva secunde înainte)</li>
  <li><code>GET /api/navigator</code>: navigatorul web de pe televizor (deschis sau nu, modul, desenul, felul câmpului ales, mărirea; fără adrese), setările lui și favoritele</li>
  <li><code>POST /api/navigator-deschide?adresa=&lt;adresă&gt;</code>, <code>POST /api/navigator-cam?port=&lt;port&gt;</code>, <code>POST /api/navigator-inchide</code>: navigatorul pe televizor</li>
  <li><code>POST /api/navigator-text</code>: text trimis în câmpul ales pe televizor; numai din browserul asociat, cu textul în corpul cererii (cu <code>?token=</code> se refuză)</li>
  <li><code>GET /api/acces-conditionat</code>: modulele de acces condiționat pe feluri (câmpul <code>fel</code>: numele felului, așa cum îl are receptorul; întâi modulele obișnuite, apoi serverele de carduri), cel ales la pornirea receptorului, cele care rulează, procesul care lucrează și memoria lui, comanda în curs sau ultimul rezultat, dacă receptorul decriptează acum</li>
  <li><code>POST /api/acces-conditionat-comanda?cerere=alege|porneste|opreste|reporneste&amp;fel=&lt;fel&gt;&amp;sufix=&lt;nume&gt;</code> (<code>fel</code> ca în <code>GET /api/acces-conditionat</code>): pornește comanda prin scriptul modulului, pe rând, una singură deodată (și cu televizorul); rezultatul vine prin <code>GET /api/acces-conditionat</code></li>
  <li><code>GET /api/subtitrari-aspect</code>: aspectul subtitrărilor text (fontul, grosimea, mărimea și culoarea literelor, conturul, umbra, fundalul, înălțimea, distanța dintre rânduri) și mărirea subtitrărilor DVB, cu alegerile posibile (<code>alegeri</code>), stilurile gata făcute și valorile de la început</li>
  <li><code>POST /api/subtitrari-aspect-seteaza?stil_font=&lt;skin|ingust|tiresias_info|tiresias_pc|google:Alias&gt;&amp;grosime=&lt;automata|normala|ingrosata|foarte_ingrosata&gt;&amp;marime=&lt;60..200&gt;&amp;culoare=&lt;emisiune|%23rrggbb&gt;&amp;contur=&lt;fara|subtire|normal|gros|foarte_gros&gt;&amp;culoare_contur=&lt;%23rrggbb&gt;&amp;umbra=0|1&amp;culoare_umbra=&lt;%23rrggbb&gt;&amp;directie_umbra=&lt;sus|sus_dreapta|dreapta|jos_dreapta|jos|jos_stanga|stanga|sus_stanga&gt;&amp;distanta_umbra=&lt;50|100|150|200|300&gt;&amp;umbra_moale=&lt;tare|moale|foarte_moale&gt;&amp;fundal=&lt;niciunul|rand|cutie&gt;&amp;culoare_fundal=&lt;%23rrggbb&gt;&amp;opacitate_fundal=&lt;10..100&gt;&amp;jos=&lt;2..25&gt;&amp;spatiere=&lt;80|90|100|110|125|150&gt;&amp;marire_dvb=&lt;clara|ocr&gt;</code>: schimbă și salvează oricare dintre ele (valorile exacte sunt în <code>alegeri</code>; o valoare greșită nu schimbă nimic); sau <code>stil=&lt;cheie&gt;</code>, un stil gata făcut</li>
  <li><code>POST /api/subtitrari-aspect-implicite</code>: toate înapoi la valorile de la început</li>
  <li><code>GET /api/subtitrari-ocr</code>: contorul recunoașterii textului din subtitrările DVB (pagini citite ca text, rămase imagine și de ce, timpul mediu, ultimele pagini, viteza serviciului)</li>
  <li><code>POST /api/subtitrari-ocr-zero</code>: contorul recunoașterii textului pus la zero</li>
  <li><code>GET /api/traducere-subtitrari</code>: traducerea automată a subtitrărilor text: valorile (<code>pornit</code>, <code>serviciu</code>, <code>limba</code>, <code>afisare</code>, <code>tarziu</code>, <code>citire</code>, <code>dvb</code>, <code>bara</code>, <code>epg</code>, <code>regiune</code>, <code>adresa_libre</code>, <code>adresa_openai</code>, <code>model_gemini</code>, <code>model_openai</code>, <code>model_groq</code>, <code>model_cloudflare</code>, <code>cont_cloudflare</code> și, pentru adresa proprie, <code>propriu_adresa</code>, <code>propriu_metoda</code>, <code>propriu_corp</code>, <code>propriu_tip_corp</code>, <code>propriu_antet</code>, <code>propriu_raspuns</code>, <code>propriu_cale</code>), alegerile posibile (<code>alegeri</code>), ce cere fiecare serviciu (<code>cere</code>), care serviciu are cheie (<code>chei</code>, niciodată cheia), dacă cheile trebuie puse din nou (<code>chei_din_nou</code>, textul notei, gol când nu e cazul), starea cheii serviciului ales, ca pe televizor (<code>cheie_fel</code> și <code>cheie_text</code>: pusă, pusă pentru alt server, lipsă), textele paginii în limba receptorului (<code>texte</code>), ce lipsește, confidențialitatea, instrucțiunile pas cu pas (cu <code>pagina_cheie</code>, adresa oficială pentru codul QR) și starea (contorul, proba, pauza după erori)</li>
  <li><code>POST /api/traducere-subtitrari-seteaza?pornit=0|1&amp;serviciu=&lt;gemini|libre|openai|azure|deepl|groq|cloudflare|google|propriu&gt;&amp;limba=&lt;meniu|ro|en|de|...&gt;&amp;afisare=&lt;inlocuieste|sub&gt;&amp;tarziu=&lt;inlocuieste|sare&gt;&amp;citire=&lt;normal|lung|foarte_lung&gt;&amp;dvb=0|1&amp;bara=0|1&amp;epg=0|1&amp;regiune=..&amp;adresa_libre=..&amp;adresa_openai=..&amp;model_gemini=..&amp;model_openai=..&amp;model_groq=..&amp;model_cloudflare=..&amp;cont_cloudflare=..&amp;propriu_adresa=..&amp;propriu_metoda=GET|POST&amp;propriu_corp=..&amp;propriu_tip_corp=json|formular&amp;propriu_antet=..&amp;propriu_raspuns=json|text&amp;propriu_cale=..</code>: schimbă și salvează oricare dintre ele (valorile exacte sunt în <code>alegeri</code>); o valoare greșită refuză tot. Adresa proprie: adresa e un șablon cu <code>{text}</code>, <code>{sursa}</code>, <code>{tinta}</code> (http:// numai pentru un server din rețeaua de acasă); adresa receptorului însuși (127.0.0.1, localhost, IP-ul lui) e refuzată, și la <code>adresa_libre</code> și <code>adresa_openai</code>; calea în JSON are chei și numere despărțite prin punct, <code>*</code> = toate elementele</li>
  <li><code>POST /api/traducere-subtitrari-cheie</code>, corpul <code>serviciu=&lt;cod&gt;&amp;cheie=&lt;cheia&gt;</code>: pune cheia unui serviciu (goală = o șterge); la <code>serviciu=propriu</code> cheia este valoarea antetului adresei proprii (de exemplu <code>Bearer</code> și cheia); numai în corpul cererii, niciodată în adresă; răspunsul spune doar care serviciu are cheie</li>
  <li><code>POST /api/traducere-subtitrari-proba</code>: probează traducerea cu serviciul ales; rezultatul vine în <code>stare.proba</code> din <code>GET /api/traducere-subtitrari</code></li>
  <li><code>POST /api/traducere-subtitrari-zero</code>: contorul traducerii pus la zero</li>
  <li><code>GET /api/traducere-configurare</code>: configurarea pas cu pas a traducerii: ce e pus acum (<code>acum</code>: serviciul, dacă are cheie, pornită sau nu, ultima probă, <code>chei_din_nou</code>), lucrarea configurării (<code>configurare</code>: starea, pasul, proba, modelul și modelele, mesajul și ce să faci), căutarea serverelor din casă (<code>cautare</code>: progresul și serverele găsite), instrucțiunile și pagina cheii fiecărui serviciu, regiunile Azure; niciodată o cheie</li>
  <li><code>POST /api/traducere-configurare-cheie</code>, corpul <code>cheie=&lt;cheia&gt;&amp;serviciu=&lt;auto|gemini|azure|deepl|groq|cloudflare|google&gt;&amp;regiune=..&amp;cont=..&amp;fara_proba=0|1</code>: probează cheia pe loc și, dacă merge, o salvează și pornește traducerea; numai în corpul cererii, niciodată în adresă; rezultatul vine în <code>configurare</code> din <code>GET /api/traducere-configurare</code></li>
  <li><code>POST /api/traducere-configurare-server?serviciu=&lt;libre|openai&gt;&amp;adresa=..&amp;model=..</code>: folosește serverul din casă (adresa completată de receptor, modelul ales singur dacă lipsește) și îl probează</li>
  <li><code>POST /api/traducere-configurare-model?model=..</code>: alt model pentru serviciul ales acum, cu probă</li>
  <li><code>POST /api/traducere-configurare-cauta</code>: caută în rețeaua de acasă serverele Ollama (11434) și LibreTranslate (5000); rezultatul vine în <code>cautare</code></li>
  <li><code>GET /api/ocr-limbi</code>: limbile recunoașterii textului (în imagine, descărcate, de descărcat, cu mărimea și starea fiecăreia) și locul pentru modelele noi</li>
  <li><code>POST /api/ocr-limbi-descarca?model=slk[&amp;intern=1]</code>: descarcă modelul unei limbi (pe stick sau disc; în memoria internă numai cu intern=1)</li>
  <li><code>POST /api/ocr-limbi-opreste?model=slk</code>: oprește descărcarea</li>
  <li><code>POST /api/ocr-limbi-sterge?model=slk</code>: șterge un model descărcat (sau îl scoate din listă când stickul lui nu e pus)</li>
  <li><code>POST /api/ocr-limbi-intreaba</code>: receptorul întreabă din nou pentru limbile cu "Nu mai întreba"</li>
  <li><code>GET /api/accel</code>: accelerarea 2D pe placa video: dacă receptorul o are (<code>disponibila</code>), setarea pentru următoarea pornire (implicit pornită) și ce s-a hotărât la pornirea de acum</li>
  <li><code>POST /api/accel-seteaza?pornita=0|1</code>: pornește sau oprește accelerarea de la următoarea pornire a interfeței (refuzat pe un receptor fără accelerarea 2D)</li>
  <li><code>POST /api/accel-reporneste</code>: repornește interfața (enigma2)</li>
  <li><code>GET /api/ceas</code>: ora receptorului, fusul orar, sursa orei (<code>auto</code>: Internet, apoi transponder; <code>ntp</code>; <code>dvb</code>), serverul NTP, alegerile lor și ultima sincronizare</li>
  <li><code>POST /api/ceas-seteaza?sursa=auto|ntp|dvb&amp;server=&lt;server&gt;&amp;fus=&lt;fus orar&gt;</code>: schimbă și salvează oricare dintre ele (valorile exacte sunt în <code>/api/ceas</code>)</li>
  <li><code>POST /api/ceas-sincronizeaza</code>: o sincronizare a orei prin Internet, acum</li>
  <li><code>GET /api/video</code>: setările video ca în Setări &gt; Video: rezoluțiile, frecvențele fiecărei rezoluții (cu <code>auto</code> = automat după canal), culorile HDMI, <code>zapmode</code> (ce se vede la schimbarea canalului) și încercarea în curs</li>
  <li><code>POST /api/video-seteaza?rezolutie=&lt;2160p|1080p|...&gt;&amp;frecventa=&lt;mod|auto&gt;&amp;colorspace=..&amp;colordepth=..&amp;hdrtype=..&amp;zapmode=&lt;mute|hold|mutetilllock|holdtilllock&gt;&amp;culori_hdmi=&lt;ycbcr|rgb&gt;</code>: un mod nou se încearcă (aceeași întrebare pe televizor, 20 s, fără răspuns revine); zapmode se salvează direct; culori_hdmi=ycbcr se încearcă la fel (aceeași întrebare), rgb se salvează și se aplică după o repornire</li>
  <li><code>POST /api/video-confirma</code> și <code>POST /api/video-revino</code>: păstrează modul încercat sau revine la cel de dinainte</li>
  <li><code>POST /api/video-reporneste</code>: repornește receptorul (culorile „Ca la calculator” se aplică numai după o repornire); cu o înregistrare în curs, întrebarea apare pe televizor</li>
  <li><code>GET /api/sunet</code>: ieșirea sunetului (Automat / Manual), AC3 și DTS downmix, pista AC3, ce primește televizorul (EDID), ce se trimite acum și de ce, ce arată driverul pe HDMI și optic</li>
  <li><code>POST /api/sunet-seteaza?iesire=&lt;auto|manual&gt;&amp;ac3=&lt;da|nu&gt;&amp;dts=&lt;da|nu&gt;&amp;pista=&lt;da|nu&gt;</code>: oricare dintre ele, salvate; ac3 / dts sunt setările pentru Manual</li>
  <li><code>GET /api/paznic</code>: paznicul receptorului: starea, setările (<code>interfata</code>, <code>asteptare</code> în secunde), alegerile și ultimele rânduri din jurnalul lui</li>
  <li><code>POST /api/paznic-seteaza?interfata=0|1&amp;asteptare=60|120|300</code>: repornirea interfeței când nu mai răspunde și așteptarea dinaintea ei</li>
  <li><code>GET /api/tv-stare</code>: TV în browser: transmisiile de acum (canal, browser, de când, octeți), setările, memoria driverului video (câte canale noi se mai pot deschide până la repornire), transmisia acestui browser și motivul ultimei opriri</li>
  <li><code>GET /api/tv-canale?hevc=0|1&amp;ac3=0|1&amp;wasm=0|1</code>: canalele de pe frecvența televizorului și din lista lui, fiecare cu merge acum sau motivul, codecul imaginii și felul sunetului; cu <code>wasm=1</code> (browserul are playerul MPEG-2) merg și canalele cu imagine MPEG-2; <code>ac3=1</code>: pagina redă sunetul AC-3, cu decodorul browserului sau cu decodorul wasm al paginii</li>
  <li><code>POST /api/tv-porneste?ref=&lt;referință&gt;&amp;hevc=0|1&amp;ac3=0|1&amp;wasm=0|1</code>, <code>POST /api/tv-opreste?id=</code>, <code>POST /api/tv-seteaza?permis=0|1&amp;standby=0|1&amp;sesiuni_max=1|2&amp;asteptare=10|20|60</code>; <code>GET /api/tv-flux</code>: fluxul TS al transmisiei acestui browser. Pornirea și fluxul merg numai din browserul conectat, cu antetul <code>X-HDS-CSRF</code>, niciodată cu <code>?token=</code></li>
  <li><code>GET /api/procesor</code>: procesorul: modul de lucru, modurile care există pe receptor, frecvența setată și cea de acum, temperatura, tensiunea, procentul folosit și timpul pe fiecare treaptă</li>
  <li><code>POST /api/procesor-seteaza?mod=automat|racoros|normal|performanta</code>: salvează modul și îl aplică pe loc</li>
  <li><code>GET /api/calitate-imagine</code>: calitatea imaginii: „Reglajele după canal”, profilul canalului de acum, cele 9 profiluri (SD, HD, 4K x SDR, HDR10, HLG) cu reglajele lor, ieșirea HDR (alegerile primite de televizor, ce e scris acum, întrebarea în curs) și textul brut al blocului de calitate</li>
  <li><code>POST /api/calitate-imagine-seteaza?profil=hd_sdr&amp;claritate=0..100&amp;...&amp;pornit=0|1[&amp;incearca=1|&amp;renunta=1]</code>: salvează reglajele unui profil (multipli de 5); cu <code>incearca=1</code> se văd pe loc fără să se salveze, <code>renunta=1</code> pune înapoi ce e salvat; <code>POST /api/calitate-imagine-implicite?profil=&lt;profil&gt;|toate</code>; <code>POST /api/calitate-imagine-hdr?iesire=auto|hdr10|hlg|none</code> (canalul pornește din nou, întrebarea apare pe televizor); <code>POST /api/calitate-imagine-comparatie?reglaj=&lt;cheie&gt;&amp;pornit=0|1</code> (jumătate de ecran, 60 s)</li>
  <li><code>GET /api/afisaj[?grupa=ceas|receptor|...][&amp;catalog=1][&amp;orase=1]</code>: afișajul din față: ce arată acum (măștile celor 4 cifre și textul), lista de rotire, mesajele scurte, așteptarea, setările, minutarul și cronometrul; cu <code>grupa</code> alegerile grupei cu desenul valorii de acum, cu <code>catalog=1</code> toate alegerile (căutarea), cu <code>orase=1</code> fusurile pentru ora din alt oraș</li>
  <li><code>POST /api/afisaj-seteaza?lista=ceas.ora:24@5,canal.nume:derulat&amp;evenimente=evenimente.volum:n&amp;asteptare=ora|ora_data|rec|stins&amp;viteza=200|300|450|600&amp;luminozitate=neschimbat|1..7&amp;luminozitate_noapte=la_fel|1..7&amp;noapte_de_la=18..23|0&amp;noapte_pana_la=5..9&amp;text=...&amp;oras=Asia/Tokyo</code>: salvează și aplică pe loc (oricare dintre ele); <code>previzualizare=1&amp;lista=...</code> arată lista pe afișaj fără salvare (cel mult 2 minute fără o cerere nouă), <code>previzualizare=0</code> revine; <code>minutar=0|1..120</code> și <code>cronometru=porneste|opreste|zero</code> pornesc ceasurile afișajului pe loc; <code>functionare=ora|canal|stins</code> merge ca înainte</li>
  <li><code>GET /api/acces-ssh</code>: parola receptorului (FTP, SSH și SFTP): felul parolei lui root (fără parola însăși), dacă merge FTP (<code>ftp</code>), cheile SSH (tipul, amprenta, comentariul), opțiunea Fără parolă în rețeaua locală, stările periculoase (<code>alarme</code>), lucrarea în curs și rezultatul ultimei comenzi</li>
  <li><code>POST /api/acces-ssh-parola</code>: textul parolei (se vede oricând); <code>GET /api/acces-ssh-brut?pagina=&lt;n&gt;</code>: fișierele serverelor SSH și FTP ca text (fără /etc/shadow)</li>
  <li><code>POST /api/acces-ssh-pune</code> (corp: <code>parola=</code>): parola aleasă (4-64 de semne: litere fără diacritice, cifre și semne, fără spații); <code>POST /api/acces-ssh-parola-noua?confirmat=1</code>: o parolă nouă la întâmplare</li>
  <li><code>POST /api/acces-ssh-adauga</code> (corp: <code>cheie=</code>), <code>POST /api/acces-ssh-stick</code>, <code>POST /api/acces-ssh-sterge?amprenta=SHA256:..&amp;confirmat=1</code>: cheile publice lipite, cele din dosarul hdsatelit/ssh de pe stick, ștergerea unei chei</li>
  <li><code>POST /api/acces-ssh-fara-parola?pornit=0|1</code> (<code>pornit=1</code> cere și <code>confirmat=1</code>): opțiunea Fără parolă în rețeaua locală. Parola, textul brut și toate schimbările merg numai dintr-un browser conectat cu codul de pe televizor (altfel 403 cu <code>trebuie_cod</code>), niciodată cu <code>?token=</code>; cât ecranul Parola receptorului e deschis pe receptor, la fel <code>/api/remotecontrol</code> și <code>/api/screenshot</code></li>
  <li><code>GET /api/setari-din-copie</code>: setările importate: câte așteaptă repornirea interfeței (<code>asteapta</code>), proba lor (<code>garda</code>), scoase după opriri neașteptate (<code>cazut</code>), textele stării</li>
  <li><code>POST /api/setari-din-copie-reporneste</code>: repornește interfața, ca setările importate să se unească</li>
  <li><code>GET /api/copie-setari[?cauta=1]</code>: copia setărilor: stickurile și discurile (<code>implicit</code> = stickul de actualizare), copiile găsite (data, versiunea imaginii, acest receptor sau altul), copia automată, ultimul rezultat; niciodată conținutul copiei</li>
  <li><code>POST /api/copie-setari-fa?mediu=&lt;id&gt;</code>, <code>POST /api/copie-setari-pune?copie=&lt;id&gt;</code> (repornește interfața; copia se pune la loc înainte să pornească), <code>POST /api/copie-setari-sterge?copie=&lt;id&gt;</code>, <code>POST /api/copie-setari-automat?automat=oprita|zilnic&amp;pastrate=1-10</code>, <code>POST /api/copie-setari-anuleaza</code></li>
  <li><code>GET /api/cautare-canale?text=&lt;nume&gt;&amp;tip=..&amp;rez=..&amp;acces=..&amp;sistem=..&amp;cod=..&amp;poz=..&amp;are=ttx,subdvb,subttx,hbbtv&amp;lsunet=&lt;limbă&gt;&amp;lsub=&lt;limbă&gt;</code>: căutarea de canale, cu aceleași rânduri de filtre ca pe televizor și pistele știute ale fiecărui canal</li>
  <li><code>POST /api/cautare-actualizeaza?fel=gasite|fara|toate</code>: întrebarea (durata, motorul); cu <code>confirmat=1</code> pornește pe televizor citirea pistelor, transponder cu transponder</li>
  <li><code>GET /api/cautare-actualizeaza-stare</code>: cât a citit (transponderul, canalele) sau rezultatul</li>
  <li><code>POST /api/cautare-actualizeaza-opreste</code>: oprește citirea și revine la canalul de dinainte</li>
  <li><code>POST /api/cautare-actualizeaza-sari</code>: sare peste satelitul pe care e antena acum și trece la următorul (tasta GALBEN de pe televizor)</li>
  <li><code>POST /api/cautare-culegere?mod=oprita|canal|transponder</code>: citirea pistelor în timpul vizionării (oprită, numai canalul privit, tot transponderul), aceeași setare ca pe televizor</li>
  <li><code>GET /api/scanare</code>: secțiunile „Scanare” și „Orientarea și setarea antenei”, cu felurile de scanare, în ordinea din meniul receptorului; cu <code>scaner=satelit|cablu|terestru&amp;fel=&lt;fel&gt;</code>, câmpurile felului și ce s-ar căuta</li>
  <li><code>POST /api/scanare-porneste?scaner=&lt;scaner&gt;&amp;fel=&lt;fel&gt;&amp;...</code>: pornește căutarea pe televizor (cu <code>confirmat=1</code> după o întrebare)</li>
  <li><code>GET /api/scanare-stare</code>: starea căutării (procent, canale găsite, transpondere, timp rămas, rezultat)</li>
  <li><code>GET /api/scanare-ultima</code>: rezultatul ultimei scanări de canale, ținut până la scanarea următoare: <code>inceput</code>, <code>sfarsit</code>, <code>stare</code> (in_curs, terminata, oprita), <code>fel</code>, <code>pozitii</code>, <code>doar_libere</code>, <code>eroare</code>, <code>transpondere</code> (<code>tp</code> ns:tsid:onid, <code>poz</code>, <code>f_khz</code>, <code>pol</code>, <code>sr</code>, <code>semnal</code>, iar când se știu <code>tsid</code>, <code>onid</code>, <code>nid</code> și, la cablu, <code>mod</code>), <code>servicii</code> (<code>cheie</code> sid:ns:tsid:onid, <code>tip</code>, <code>nume</code>, <code>furnizor</code>, <code>caid</code>, iar când operatorul trimite numerele canalelor <code>lcn</code> și <code>lcn_vizibil</code>): toate serviciile citite din SDT, vechi și noi, și <code>retele</code> (<code>nid</code>, <code>nume</code>, <code>pds</code>, <code>multiplexuri</code>, <code>lcn</code>, <code>privati</code>): rețelele din tabela NIT; câmpurile din tabela NIT (<code>nid</code>, <code>lcn</code>, <code>retele</code>) apar la căutarea în rețea și la scanarea pe cablu pe o singură frecvență; numai citire, lista de canale nu se schimbă; fără nicio scanare de la pornire, <code>result</code> false</li>
  <li><code>POST /api/scanare-opreste</code>: oprește căutarea sau închide rezultatul rămas pe televizor</li>
  <li><code>POST /api/scanare-fluxuri</code>: alegerea de la sfârșitul scanării DAB+ / DVB-T2 de pe televizor (<code>actiune=asculta&amp;post=N</code>, <code>inapoi</code>, <code>din_nou</code>, <code>porneste</code>)</li>
  <li><code>GET /api/dabt2?fel=dab|t2</code>: fereastra „Fluxuri și setări” a DAB+ / DVB-T2 din satelit: fluxurile cu poziția, numele, numărul de posturi și starea, setările, Despre, lucrul în curs și <code>repunere</code> (canalul de dinainte, pornit din nou după „Învață posturile”: starea și mesajul)</li>
  <li><code>POST /api/dabt2-actiune?fel=dab|t2&amp;actiune=actualizeaza|buchete|invata|sterge&amp;flux=..</code>: actualizează lista, reface buchetele, învață posturile unui flux, șterge un flux adăugat de mână</li>
  <li><code>POST /api/dabt2-seteaza?cheie=tasta|dosar|latime|nedecodabile&amp;valoare=..</code>: setările ferestrei, aceleași ca pe televizor</li>
  <li><code>POST /api/dabt2-manual?fel=dab|t2&amp;nume=..&amp;grade=..&amp;emisfera=E|V&amp;frecventa=..&amp;...</code>: un flux adăugat de mână, cu aceleași câmpuri și limite ca „Adaugă manual”</li>
  <li><code>POST /api/dabt2-televizor?fel=dab|t2</code>: deschide fereastra pe televizor</li>
  <li><code>POST /api/scanare-televizor?id=&lt;entryID&gt;</code>: deschide pe televizor ecranul unei intrări din cele două secțiuni</li>
  <li><code>GET /api/antena?lat=&lt;grade&gt;&amp;lon=&lt;grade&gt;</code>: tunerele, LNB-ul, semnalul canalului curent și unghiurile antenei spre fiecare satelit (numai citire)</li>
  <li><code>GET /api/lnb?slot=N</code>: LNB-urile tunerului, cu valorile, alegerile și „Probă de calcul” (numai citire)</li>
  <li><code>POST /api/lnb-plan</code>: ce s-ar schimba pentru câmpurile trimise (<code>l_&lt;lnb&gt;_&lt;câmp&gt;</code>), sau pentru „Ce era înainte” cu <code>fel=inainte</code>; nu scrie nimic</li>
  <li><code>POST /api/lnb-aplica</code>: aplică planul văzut (<code>semn=</code>), verifică semnalul și așteaptă răspunsul 60 de secunde</li>
  <li><code>POST /api/lnb-raspuns?raspuns=pastrez|revin</code>: răspunsul la „Păstrezi noile setări?”</li>
  <li><code>GET /api/lnb-stare</code>: verificarea semnalului, întrebarea și secundele rămase</li>
  <li><code>GET /api/gasire-semnal</code>: tunerele, sateliții, transponderul de la care pornește măsurarea și starea ei</li>
  <li><code>GET /api/gasire-semnal-transpondere?slot=N&amp;poz=P</code>: transponderele unui satelit</li>
  <li><code>GET /api/gasire-semnal-stare</code>: nivelul, calitatea, BER-ul și verdictul măsurării</li>
  <li><code>POST /api/gasire-semnal-porneste</code>, <code>-reacordeaza</code>, <code>-opreste</code>: pornește, acordează din nou sau oprește măsurarea</li>
  <li><code>GET /api/motor-comenzi</code>: tunerele cu motor, sateliții și starea comenzilor</li>
  <li><code>GET /api/motor-comenzi?urma=N</code>: urma comenzilor trimise motorului (ultimele N, implicit 100, cel mult 500, cele mai noi întâi): ora, comanda, unghiul, cine a cerut-o (televizorul, ecranul sau pagina motorului, Găsire semnal, reacordarea), poziția crezută de receptor; numai citire, din <code>/home/root/logs/hds-motor.log</code></li>
  <li><code>POST /api/motor-comanda?actiune=&lt;comanda&gt;</code>: pas, mișcare fără oprire, poziții memorate, mergi la satelit, limite, oprire</li>
  <li><code>GET /api/locul[?tara=RO]</code>: locul antenei pentru motorul USALS, țările și orașele unei țări (tabelul din imagine)</li>
  <li><code>POST /api/locul-seteaza</code>: locul antenei din tabel (<code>tara</code>, <code>oras</code>) sau scris (<code>lat</code>, <code>lon</code>, grade, nord și est pozitive)</li>
  <li><code>POST /api/locul-internet</code>, <code>GET /api/locul-internet-stare</code>: locul antenei aflat după adresa de internet a receptorului, de serverul HD Satelit, numai la cerere și numai din browserul conectat; se scrie abia după confirmare, cu <code>POST /api/locul-seteaza</code> și <code>internet=&lt;semn&gt;</code></li>
  <li><code>GET /api/limbi</code>: limba sunetului și a subtitrărilor: cele 7 setări cu alegerile lor, ce se ține minte pe canalul de acum și canalele cu alegeri de mână</li>
  <li><code>POST /api/limbi-seteaza?audio1=..&amp;audio2=..&amp;audio3=..&amp;fara_subtitrari=0|1&amp;sub1=..&amp;sub2=..&amp;sub3=..&amp;tradu_orice=0|1</code>: schimbă și salvează oricare dintre ele (valorile exacte sunt în <code>/api/limbi</code>; <code>tradu_orice</code> = „Tradu automat din orice subtitrare disponibilă”, contează cu traducerea subtitrărilor pornită) și le aplică pe canalul de acum</li>
  <li><code>POST /api/limbi-uita?cheie=&lt;cheia canalului&gt;</code>, <code>POST /api/limbi-uita-toate?confirmat=1</code>: uită alegerile de mână ale unui canal sau ale tuturor</li>
  <li><code>GET /api/limba-interfata</code>: limba meniurilor de acum și lista limbilor, cu numele de pe televizor</li>
  <li><code>POST /api/limba-interfata-seteaza?limba=ro_RO</code>: schimbă limba meniurilor și o salvează, ca OK în ecranul limbii de pe televizor</li>
  <li><code>GET /api/temporizatoare</code>: înregistrările programate (aceeași ordine, stare și detalii ca pe televizor), locul înregistrărilor și spațiul liber</li>
  <li><code>POST /api/temporizatoare-adauga?ref=&lt;canal&gt;&amp;zi=AAAA-LL-ZZ&amp;inceput=HH:MM&amp;sfarsit=HH:MM&amp;nume=..&amp;doar_comuta=0|1</code>: pune o înregistrare (sau doar schimbarea canalului); la suprapunere nu pune nimic și spune cu ce se suprapune</li>
  <li><code>POST /api/temporizatoare-sterge?id=..&amp;confirmat=1</code>, <code>POST /api/temporizatoare-opreste?id=..&amp;oprit=1|0</code>, <code>POST /api/temporizatoare-curata?confirmat=1</code>: șterge una, o oprește sau o pornește din nou, șterge cele terminate</li>
  <li><code>POST /api/temporizatoare-modifica?id=..&amp;zi=..&amp;inceput=..&amp;sfarsit=..&amp;repetare=o_data|zilnic|luni_vineri|zile&amp;zile=0,1,..&amp;dupa=nimic|asteptare|oprire|automat&amp;loc=..</code>: aceleași câmpuri ca fereastra de pe televizor, cu aceeași verificare a suprapunerii; <code>POST /api/temporizatoare-opreste?id=..&amp;alegere=stoponlycurrent|stopall|stoponlycoming</code>: una repetată care merge acum</li>
  <li><code>GET /api/temporizatoare-jurnal?id=..</code>, <code>POST /api/temporizatoare-jurnal-goleste?id=..&amp;confirmat=1</code>: jurnalul unei înregistrări, pe înțelesul oricui, cu mesajul tehnic; golirea lui</li>
  <li><code>GET /api/telecomenzi</code>: telecomenzile asociate, tastele lor și captura paginii (cititorul, proba, asocierea)</li>
  <li><code>POST /api/telecomenzi-captura?fel=cititor|proba|proba-noua|asociere|oprit</code>: pornește sau oprește captura paginii (cititorul și proba numai ascultă, cel mult 2 minute)</li>
  <li><code>POST /api/telecomenzi-asociere?pas=inapoi|sari|gata|continua|anuleaza|proba|inchide&amp;pastreaza=0|1</code>: pașii asocierii unei telecomenzi noi</li>
  <li><code>POST /api/telecomenzi-schimba?actiune=activa|neasociate|redenumeste|sterge-tasta|sterge|sterge-tot&amp;id=..&amp;cod=..&amp;nume=..&amp;confirmat=1</code>: aceleași schimbări ca în lista de pe televizor</li>
  <li><code>GET /api/telecomenzi-export?format=json|csv</code>: codurile telecomenzii receptorului și ale celor asociate, pentru aplicații</li>
  <li><code>GET /api/meniu</code>: tot meniul receptorului (tasta MENU), cu aceleași intrări ca pe televizor pentru nivelul ales</li>
  <li><code>POST /api/meniu-televizor?id=&lt;entryID&gt;</code>: deschide pe televizor ecranul unei intrări (nu oprirea sau repornirea)</li>
  <li><code>GET /api/setari</code>: ecranele de setări din meniu; cu <code>id=&lt;cheie&gt;</code>, rândurile lor (aceleași ca pe televizor, cu alegerile)</li>
  <li><code>GET /api/cauta-setari?q=&lt;text&gt;</code>: „Caută setări”: meniurile și setările care au textul în nume (fără diacritice), cu drumul din meniu, valoarea de acum și pagina web</li>
  <li><code>POST /api/cauta-setari-televizor?cheie=&lt;cheie&gt;</code>: deschide pe televizor un rezultat al căutării, cu rândul găsit ales</li>
  <li><code>POST /api/setari-seteaza?id=&lt;cheie&gt;&amp;r&lt;N&gt;=&lt;valoare&gt;</code>: schimbă și salvează rândurile trimise (o valoare greșită nu schimbă nimic; la o alegere multiplă, ca vitezele de derulare, alegerile despărțite prin virgulă, de pildă <code>r20=2,8,16</code>; gol = nicio alegere)</li>
  <li><code>GET /api/informatii?pagina=despre|receptor|tunere|memorie|stocare|retea|hdmi</code>: ecranele „System Information”, cu aceleași texte ca pe televizor</li>
  <li><code>GET /api/canale-buchete?fila=tv|radio</code>: listele de ales și lista pe care stă televizorul</li>
  <li><code>GET /api/canale-lista?fila=&amp;buchet=&amp;text=&amp;&lt;grupă&gt;=v1,v2&amp;de_la=&amp;cate=</code>: rândurile, pe pagini de cel mult 200, cu grupele de filtre și numerele lor</li>
  <li><code>GET /api/canale-epg?refs=r1,r2</code>: emisiunea de acum și cea următoare, cel mult 50 de canale</li>
  <li><code>GET /api/canale-acum</code>: canalul de pe televizor</li>
  <li><code>POST /api/canale-porneste?fila=&amp;buchet=&amp;ref=</code>: pornește canalul prin lista de pe televizor</li>
  <li><code>GET /api/canale-sigla?p=&lt;nume&gt;</code>: sigla canalului; la listele de canale, 503 când receptorul are prea multe cereri în lucru și 504 când nu termină în 10 s</li>
  <li><code>GET /api/stocare</code>: locul înregistrărilor, spațiul liber și discurile conectate</li>
  <li><code>POST /api/stocare-foloseste?punct=/media/usb</code>: folosește discul pentru înregistrări (face dosarul movie, fără formatare)</li>
  <li><code>GET /api/subtitrari-film</code>: filmul care merge, subtitrările lui, întârzierea, codarea și cadrele pe secundă</li>
  <li><code>POST /api/subtitrari-film-alege?id=&lt;id&gt;|oprit</code>, <code>POST /api/subtitrari-film-intarziere?ms=N</code> (sau <code>pas=</code>), <code>POST /api/subtitrari-film-codare?cod=..</code>, <code>POST /api/subtitrari-film-fps?fps=..</code>: aceleași alegeri ca tasta SUB la un film din fișier</li>
  <li><code>GET /api/teletext?pagina=N&amp;sub=S&amp;ascuns=0|1&amp;copie=&lt;ref&gt;</code>: o pagină de teletext, ca pe televizor la tasta TEXT: cele 25 de rânduri a câte 40 de celule (litera, culoarea, fundalul, mozaicul, atributele), textul paginii, subpaginile, paginile tastelor colorate, paginile vecine și pagina de pe televizor; fără <code>pagina</code>, pagina de pe televizor sau cea de pornire; <code>sub=-1</code> = cea mai nouă; <code>ascuns=1</code> arată ce e ascuns; cu <code>copie</code>, paginile din copia salvată a canalului, fără tuner (<code>sursa</code>: <code>direct</code> sau <code>copie</code>); <code>hd</code> = setarea Teletext neted, <code>optiuni</code> = conturul literelor, umbra literelor și formele în relief (<code>contur</code>, <code>umbra</code>, <code>relief</code>, ca pe televizor). Pagina lipsă: <code>gasita</code> fals și mesajul că se caută</li>
  <li><code>GET /api/teletext-copii</code> (cu <code>?canale=1</code> și canalele care au teletext): copiile de teletext salvate (canalul, data, paginile, mărimea), dosarul, spațiul folosit și cel ales, urmăritorul (caruselul canalului de acum, reîmprospătarea în lucru) și setările</li>
  <li><code>POST /api/teletext-salveaza</code>, <code>POST /api/teletext-sterge?ref=</code>, <code>POST /api/teletext-reimprospateaza?ref=</code> (receptorul trece pe canal, așteaptă o trecere completă a teletextului, face copia și se întoarce la canalul de dinainte; răspunde pe loc), <code>POST /api/teletext-setari?hd=0|1&amp;contur=0|1&amp;umbra=0|1&amp;relief=0|1&amp;copie_automata=0|1&amp;spatiu=5|10|20|50|100</code> (<code>hd</code> = Teletext neted): aceleași alegeri ca meniul teletextului de pe televizor</li>
  <li><code>GET /api/teletext-descarca?ref=&lt;ref&gt;&amp;fel=html|date</code> (fără <code>ref</code>: canalul de acum): <code>date</code> = fișierul copiei (.ttx, comprimat), <code>html</code> = o singură pagină HTML cu toate paginile, care se citește fără receptor</li>
  <li><code>GET /api/filme</code>: filmul care merge (poziția, lungimea, starea, locul ținut minte, mesajul de refuz) și setările filmelor; <code>GET /api/filme-lista</code>: filmele din dosarul listei de filme, cu locul rămas</li>
  <li><code>POST /api/filme-comanda?fa=pauza|redare|inainte|inapoi</code>, <code>?fa=salt&amp;secunde=-60</code>, <code>?fa=la&amp;secunde=N</code>, <code>POST /api/filme-seteaza?pornire=&amp;oprire=&amp;sfarsit=</code>, <code>POST /api/filme-porneste?cale=..&amp;de_la=loc|inceput</code>: aceleași comenzi ca pe telecomandă în player și în lista de filme</li>
  <li><code>GET /api/descarcare-subtitrari</code> și <code>POST /api/descarcare-subtitrari-cauta</code>, <code>-descarca</code>, <code>-aplica</code>, <code>-verifica</code>, <code>-conturi</code>: descărcarea subtitrărilor (numele, parolele și cheile numai în corpul cererii); pe un canal TV sau la o înregistrare și <code>-film</code> (<code>fapta=identifica|alege|titlu|local</code>: filmul din ghid, identificat în Wikidata) și <code>-potrivire</code> (<code>fapta=urmatoarea|dinainte|plus|minus|reclama|acum|viteza|opreste</code>: potrivirea subtitrării pe canal)</li>
  <li><code>GET /api/import-surse?cauta=1</code>: copiile de canale și setări găsite pe stick-uri și pe receptor, starea căutării și a importului</li>
  <li><code>POST /api/import?sursa=&lt;id&gt;&amp;canale=1&amp;tunere=1&amp;temporizatoare=0&amp;generale=0</code>: pornește importul (întâi copia de siguranță)</li>
  <li><code>POST /api/import-alta-imagine?raspuns=da|nu|ascunde</code>: răspunsul la întrebarea de la prima pornire (canalele și setările din altă imagine, găsite pe stick sau disc); starea în <code>/api/import-surse</code> (<code>alta_imagine</code>)</li>
  <li><code>GET /api/liste-implicite</code>: listele de canale gata făcute și drumurile spre scanare și import</li>
  <li><code>GET /api/radio</code>, <code>GET /api/radio-benzi</code>: postul de radio care merge, cu textele ecranului radio; barele și nivelul sunetului</li>
  <li><code>POST /api/radio-seteaza?ecran=0|1&amp;vizualizator=..&amp;culori=..&amp;bare=..&amp;cadre=..&amp;odihna=..&amp;epg=..&amp;bara_la_zap=0|1</code>: setările ecranului radio</li>
  <li><code>POST /api/radio-urmatoarea?ce=vizualizator|culori</code>: vizualizarea sau culorile următoare (ca tastele galbenă și albastră pe ecranul radio)</li>
  <li><code>GET /api/ghid?ref=&amp;de_la=&amp;cate=</code>, <code>GET /api/ghid-emisiune?ref=&amp;id=</code>: ghidul unui canal (fără <code>ref</code>, canalul de pe televizor) și o emisiune cu descrierile</li>
  <li><code>POST /api/ghid-temporizator?ref=&amp;id=&amp;fel=inregistrare|comutare|scoate</code>: pune sau scoate înregistrarea unei emisiuni (409 la suprapunere)</li>
  <li><code>GET /api/ecran-negru</code>, <code>GET /api/ecran-negru-flux</code>: mesajul de pe ecranul negru (de ce nu se vede imaginea) și analiza fluxului canalului</li>
  <li><code>POST /api/ecran-negru-fapta?fapta=&lt;id&gt;|ascunde</code>: fapta mesajului de acum, pe televizor, sau ascunderea lui</li>
  <li><code>GET /api/standby-tv</code>: ieșirea HDMI în standby (oprită sau pornită, oprirea din nou după aprinderea televizorului) și starea CEC</li>
  <li><code>GET /api/acces-canal</code>: accesul canalului care rulează (criptat sau liber), sistemele, CAID-urile și ce decriptează modulul acum</li>
  <li><code>GET /api/stare-retea</code>: legătura cu routerul și internetul (cablu sau Wi-Fi, treptele semnalului Wi-Fi, internetul merge, routerul nu are internet sau receptorul nu e conectat la router), cu desenul pictogramei și textul ei, ca pictograma din bara de pe televizor</li>
  <li><code>GET /api/pasi-decriptare</code>: pașii decriptării canalului de pe televizor (cererea către modulul de acces, răspunsurile și timpul lor, imaginea decriptată, mesajele modulului CI), numai cu setarea Arată pașii decriptării pornită</li>
  <li><code>POST /api/ecran-sterge?sursa=galerie|propriu&amp;id=..</code>, <code>POST /api/ecran-la-loc</code>: șterge un ecran de pornire din galerie (nu cel din fabrică și nici cel pus) sau pune la loc ecranele șterse</li>
  <li><code>GET /api/egalizator</code>: egalizatorul posturilor de radio: pornit sau oprit, benzile, presetarea, modul de noapte, reglajele postului de acum și dacă merge la acest post; <code>POST /api/egalizator-seteaza</code>: schimbă și aplică pe loc</li>
  <li><code>GET /api/licente</code>, <code>GET /api/licente-text?id=..</code>: programele din imagine cu licența fiecăruia și textul unei licențe</li>
  <li><code>GET /api/mod-sigur</code>, <code>POST /api/mod-sigur-alege</code>, <code>GET /api/mod-sigur-brut?pagina=&lt;n&gt;</code>: modul sigur (opririle interfeței, alegerile de după ele) și fișierele lui ca text</li>
  <li><code>GET /api/paza-model</code>: paza de model (receptorul pentru care e făcută imaginea și amprenta acestuia); <code>GET /api/actualizare-pachete</code>: pachetele de actualizare găsite și verdictul pazei pentru fiecare</li>
  <li><code>GET /api/actualizari</code>, <code>POST /api/actualizari-cauta</code>, <code>POST /api/actualizari-instaleaza?actualizare=&lt;n&gt;</code>, <code>POST /api/actualizari-zilnic?zilnic=0|1</code>, <code>POST /api/actualizari-reporneste</code>: actualizările prin pachete de pe stb.hdsatelit.com (starea, căutarea, instalarea, verificarea zilnică, repornirea interfeței după instalare)</li>
</ul>
<h2>Acces</h2>
<p>Din scripturi: adaugă parametrul <code>token=&lt;cheie&gt;</code> la oricare adresă de mai sus (GET sau POST). Cheia pentru scripturi e ascunsă și se vede numai la cerere: pe receptor, în ecranul interfeței web (Albastru, Alte opțiuni, Arată parola și cheia), sau în pagina Interfața web (butonul Arată). Tot acolo se poate face o cheie nouă.</p>
<p>Din browser: după conectarea cu codul de pe televizor, browserul primește un cookie. Cu el, comenzile care schimbă ceva (<code>remotecontrol</code>, <code>zap</code>) se trimit cu POST, dintr-o pagină a receptorului, cu antetul <code>X-HDS-CSRF</code> primit în panou.</p>
<p>Comenzile care mișcă motorul, pornesc măsurarea semnalului sau schimbă LNB-ul (<code>lnb-aplica</code>, <code>lnb-raspuns</code>, <code>gasire-semnal-porneste</code>, <code>-reacordeaza</code>, <code>-opreste</code>, <code>motor-comanda</code>) se dau numai din paginile receptorului, cu browserul conectat: cu POST, cu antetul <code>X-HDS-CSRF</code>, fără cheia pentru scripturi.</p>
<p>Adresele de mai sus răspund numai din rețeaua locală.</p>
<h2>Aplicații de telefon</h2>
<p>Aplicațiile obișnuite pentru receptoarele Enigma2 (telecomandă, canale, ghid, înregistrări programate, liste m3u) folosesc adresele lor obișnuite: <code>/web/...</code> în XML (de exemplu <code>/web/deviceinfo</code>, <code>/web/getservices</code>, <code>/web/zap?sRef=</code>, <code>/web/epgnow?bRef=</code>, <code>/web/timerlist</code>), cele cu aceleași nume din <code>/api/...</code> în JSON, <code>/picon/</code>, <code>/file?file=</code> (siglele, iar pentru redarea pe telefon înregistrările și filmele din locurile înregistrărilor, cu <code>Range</code>), <code>/web/ts.m3u?file=</code> și <code>/grab</code>. Sunt pornite din fabrică (rândul „Aplicații de telefon” din ecranul interfeței web și din pagina Setări).</p>
<p>Din casă intră fără parolă, cu adresa IP a receptorului, cu numele lui (și cu terminațiile date de router: <code>.lan</code>, <code>.home</code>, <code>.localdomain</code>, <code>.home.arpa</code>, <code>.local</code>) sau cu <code>hdsatelit.local</code>; utilizatorul și parola din aplicație rămân goale. Cu alt nume în adresă, sau cu „Cere codul și în rețeaua locală” pornit, se cer utilizatorul <code>root</code> și parola pentru aplicații (HTTP Basic).</p>
<p>Din afara casei receptorul nu răspunde aplicațiilor până nu pornești „Acces din afara casei”; atunci intră numai cu utilizatorul <code>root</code> și parola pentru aplicații, pe care o vezi pe televizor, în ecranul interfeței web, și în pagina Setări. După 5 parole greșite de la aceeași adresă, receptorul nu-i mai răspunde 5 minute. Cererile venite din alte pagini web sunt refuzate, iar oprirea completă și repornirea nu se fac din aplicații.</p>
</main>
</body>
</html>
"""

# modelele de adrese din /programatori (<cheie>, <referință>...): cuvintele romanesti se traduc dupa traducerea
# paginii, deci randurile lungi din po raman cum sunt; numele la fel in engleza (id, ref, port, lnb) si listele de
# valori ale API-ului (da|nu, auto|manual) raman neschimbate
_MODELE_PROGRAMATORI = (N_("referință"), N_("adresă"), N_("nume"), N_("limbă"), N_("câmp"), N_("grupă"),
	N_("cheie"), N_("cheia"), N_("cheia canalului"), N_("cod"), N_("text"), N_("Familia"), N_("NumeInSkin"),
	N_("fus orar"), N_("profil"), N_("scaner"), N_("comanda"), N_("semn"), N_("canal"), N_("valoare"), N_("fel"),
	N_("grade"))


def _paginaProgramatori():
	"""/programatori in limba receptorului: pagina tradusa, apoi cuvintele din modelele de adrese."""
	pagina = _traducePagina(_PAGINA_PROGRAMATORI)
	for model in _MODELE_PROGRAMATORI:
		tradus = _t(model)
		if tradus and tradus != model:
			tradus = tradus.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
			pagina = pagina.replace("&lt;%s&gt;" % model, "&lt;%s&gt;" % tradus)
	return pagina


def stareInterfataWeb(browser=None):
	"""GET /api/interfata-web: setarile interfetei web care se schimba si din web. Azi numai codul in reteaua locala
	(acelasi rand ca pe televizor, in ecranul interfetei web)."""
	liber = bool(browser and browser.get("liber"))
	rez = {"result": True, "cod_retea_locala": codInReteaLocala(), "fara_cod": liber,
		"drum": _drumSetariWeb()}
	# aplicatiile de telefon: cele doua setari si aplicatiile vazute; parola NU (o da numai POST
	# /api/interfata-web-secrete, la butonul "Arată")
	from . import aplicatii_web
	rez.update(aplicatii_web.stareSetari(aplicatiiPornite(), aplicatiiAfara()))
	return rez


SECRETE = ("parola", "cheie")


def secreteInterfataWeb(ce):
	"""POST /api/interfata-web-secrete?ce=parola|cheie: parola pentru aplicatii sau cheia pentru scripturi, intreaga,
	numai la cererea omului (butonul "Arată" din /setari si /interfata-web; pe televizor Albastru > Alte optiuni).
	Paginile nu le au in HTML si nici in GET /api/interfata-web: se vad numai dupa apasare, deci nu ajung singure in
	capturi. Cine are voie: un browser care a trecut poarta (POST, aceeasi origine, antetul CSRF); cererile cu ?token=
	(scripturile) sunt refuzate inainte (resursa)."""
	if ce == "parola":
		from . import aplicatii_web
		return {"result": True, "parola_aplicatii": aplicatii_web.parola(creeaza=True)}
	if ce == "cheie":
		initConfigHdsWebControl()
		return {"result": True, "cheie": str(config.plugins.hdswebcontrol.token.value or "")}
	return {"result": False, "message": _t("Se cere cu ce=parola sau ce=cheie.")}


def _drumSetariWeb():
	"""Unde e acelasi rand pe televizor (numele din meniu), pentru nota din pagina /setari."""
	try:
		from .meniu_web import drumText
		return drumText("hds_webcontrol_setup")
	except Exception as eroare:
		print("[HdsWebControl] drumul ecranului interfetei web: %s" % eroare)
		return "Meniu"


def seteazaCodReteaLocala(text):
	"""POST /api/interfata-web-seteaza?cod_retea_locala=0|1. Salvat pe disc; se aplica de la cererea urmatoare."""
	if text not in ("0", "1"):
		return {"result": False, "message": _t("Se alege cu cod_retea_locala=0 sau 1.")}
	initConfigHdsWebControl()
	element = config.plugins.hdswebcontrol.cod_retea_locala
	element.value = text == "1"
	element.save()
	configfile.save()
	_jurnal("codul in reteaua locala: %s (din web)" % ("cerut" if element.value else "oprit"))
	if element.value:
		mesaj = (_t("Salvat. Din acum, fiecare browser sau telefon nou din rețeaua locală are nevoie o dată de codul "
			"de pe "
			"televizor. Aplicațiile de telefon cer și acasă utilizatorul root și parola pentru aplicații."))
	else:
		mesaj = _t("Salvat. Din acum, browserele și telefoanele din rețeaua locală intră fără cod.")
	return {"result": True, "message": mesaj, "cod_retea_locala": bool(element.value)}


def seteazaAplicatii(argumente):
	"""POST /api/interfata-web-seteaza?aplicatii=0|1, ?aplicatii_afara=0|1 sau ?parola_aplicatii_noua=1
	(aplicatii_web.py). Salvat pe disc; se aplica de la cererea urmatoare."""
	from . import aplicatii_web
	initConfigHdsWebControl()
	if b"parola_aplicatii_noua" in argumente:
		if argumente[b"parola_aplicatii_noua"][:1] != [b"1"]:
			return {"result": False, "message": _t("Se cere cu parola_aplicatii_noua=1.")}
		return aplicatii_web.parolaNouaWeb(aplicatiiPornite(), aplicatiiAfara())
	cheie = "aplicatii_afara" if b"aplicatii_afara" in argumente else "aplicatii"
	valoare = (argumente.get(cheie.encode("ascii")) or [b""])[0]
	if isinstance(valoare, bytes):
		valoare = valoare.decode("ascii", "replace")
	return aplicatii_web.seteaza(cheie, valoare.strip(), config.plugins.hdswebcontrol.aplicatii,
		config.plugins.hdswebcontrol.aplicatii_afara, configfile.save, cod_acasa=codInReteaLocala())


def _configPanou(csrf, jeton, browser):
	"""Obiectul __CONFIG__ al panoului, ca JSON sigur in interiorul unui <script>. `cod_retea_locala`: daca in
	reteaua locala se cere codul (pagina /setari arata starea, discret)."""
	text = json.dumps({"csrf": csrf, "jeton": jeton, "browser": browser, "cod_retea_locala": codInReteaLocala()})
	return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _anteteHtml(request):
	request.setHeader(b"content-type", b"text/html; charset=utf-8")
	request.setHeader(b"cache-control", b"no-store")
	request.setHeader(b"x-frame-options", b"DENY")
	request.setHeader(b"referrer-policy", b"same-origin")
	request.setHeader(b"content-security-policy",
		b"default-src 'self'; img-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
		b"frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


# Pagina deschisa de telefon din codul QR de pe televizor (GET /t/<jeton>, asociere.py: cereJeton/verificaJeton). GET-ul
# nu consuma jetonul (unele aplicatii de scanare deschid adresa o data inainte, ca previzualizare): pagina trimite
# jetonul cu POST /t (aceeasi origine, reteaua locala, ca la cod), primeste cookie-ul si merge la pagina ceruta de
# ecran. Fara JavaScript, acelasi POST din formular (raspunsul 303). Jetonul se pune in pagina numai dupa ce are forma
# buna (base64url), deci nu poate scapa din sirul JSON; nu se scrie in jurnal si nu pleaca spre alta adresa
# (Referrer-Policy: same-origin: Referer si Origin pleaca numai spre receptor, deci si formularul fara JavaScript trece
# de acelasiOrigin).
_PAGINA_JETON = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="same-origin">
<title>Receptorul HD Satelit</title>
<style>__STIL_COMUN__
  main{max-width:520px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 12px;}
  p{line-height:1.5;}
  button{min-height:44px;padding:10px 16px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  .eroare{color:#ffb4a8;}
</style>
</head>
<body>
<main>
<h1>Receptorul HD Satelit</h1>
<p id="mesaj">Se conectează telefonul la receptor...</p>
<noscript><form method="post" action="/t"><input type="hidden" name="j" value="__JETON__"><input type="hidden" name="fel" value="formular"><button type="submit">Continuă</button></form></noscript>
<p><a href="/" id="panou" hidden>Deschide panoul receptorului</a></p>
</main>
<script>
var JETON = __JETON_JSON__;
function mesaj(t, eroare){ var m = document.getElementById("mesaj"); m.textContent = t; m.className = eroare ? "eroare" : ""; }
if(!JETON){
  mesaj("Codul QR nu e bun. Deschide din nou codul pe televizor și scanează-l.", true);
  document.getElementById("panou").hidden = false;
} else {
  var corp = new URLSearchParams(); corp.set("j", JETON);
  fetch("/t", {method: "POST", credentials: "same-origin", cache: "no-store",
    headers: {"Content-Type": "application/x-www-form-urlencoded"}, body: corp.toString()}).then(function(r){
    return r.json().catch(function(){ return {result: false, mesaj: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  }).then(function(d){
    if(d.result && d.destinatie){ mesaj("Telefonul e conectat. Se deschide pagina..."); location.replace(d.destinatie); return; }
    mesaj(d.mesaj || "Nu s-a putut conecta telefonul.", true);
    document.getElementById("panou").hidden = false;
  }).catch(function(){ mesaj("Receptorul nu răspunde. Verifică dacă telefonul e în aceeași rețea cu receptorul.", true); });
}
</script>
</body>
</html>
"""


def _paginaJeton(request, jeton):
	"""GET /t/<jeton>: numai din reteaua locala; jetonul nu se consuma aici (vezi _PAGINA_JETON)."""
	if not _esteAdresaLocala(_adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	_anteteHtml(request)
	request.setHeader(b"referrer-policy", b"same-origin")
	request.setHeader(b"cache-control", b"no-store")
	bun = jeton if formatSecretValid(jeton) else ""
	return _traducePagina(_PAGINA_JETON).replace("__STIL_COMUN__", _STIL_COMUN).replace("__JETON_JSON__",
		json.dumps(bun)).replace(
		"__JETON__", bun).encode("utf-8")


def _paginaPrincipala(request):
	"""GET / si GET /panou: panoul pentru un browser asociat (sau pentru ?token= valid, ca uneltele vechi),
	altfel pagina de asociere cu codul de pe televizor."""
	if not _esteAdresaLocala(_adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	# pe alt receptor, in locul panoului, mesajul pazei de model (fara asociere: interfata de pe televizor nu porneste)
	from . import paza_model_web
	if paza_model_web.inPaza():
		return paza_model_web.pagina(request)
	_anteteHtml(request)
	if PARAM_JETON in request.args and _jetonValid(request):
		jeton = _jetonConfigurat()  # valoarea de pe SERVER, nu cea primita de la client
		return _legaturiDisponibile(_panouCuEcranNegru()).replace("__TELECOMANDA__", _htmlTelecomanda()).replace("__CONFIG__", _configPanou("", jeton, "")).encode("utf-8")
	secret, browser = _sesiuneDinCerere(request)
	if browser is not None:
		# imaginea live din caseta ecranului: aceeasi politica a continutului ca pagina /tv (numai panoul, nu asocierea)
		try:
			from . import tv_web
			request.setHeader(b"content-security-policy", tv_web.CSP_TV)
		except Exception as eroare:
			print("[HdsWebControl] politica imaginii live: %s" % eroare)
		return _legaturiDisponibile(_panouCuEcranNegru()).replace("__TELECOMANDA__", _htmlTelecomanda()).replace("__CONFIG__", _configPanou(csrfPentru(secret), "",
			browser.get("nume", ""))).encode("utf-8")
	return _traducePagina(_PAGINA_ASOCIERE).encode("utf-8")


def _panouCuEcranNegru():
	"""Panoul principal cu caseta ecranului negru (ecran_negru_web.in_panou); fara modul, panoul de pana acum."""
	try:
		from . import ecran_negru_web
		pagina = ecran_negru_web.in_panou(_traducePagina(_PAGINA_PANOU))
	except Exception as eroare:
		print("[HdsWebControl] caseta ecranului negru: %s" % eroare)
		pagina = _traducePagina(_PAGINA_PANOU)
	# mouse-ul pe ecranul receptorului si telecomanda pe ecranul intreg (mouse_web.in_panou): scriptul lui, inaintea
	# scriptului panoului (ultimul </script> ramane al panoului, pentru modulele care se pun inaintea lui)
	try:
		from . import mouse_web
		pagina = mouse_web.in_panou(pagina)
	except Exception as eroare:
		print("[HdsWebControl] mouse pe ecran: %s" % eroare)
	# randurile „Ieșirea HDMI” si „CEC” sub „Standby” (standby_tv_web.in_panou), deasupra casetei ecranului negru
	try:
		from . import standby_tv_web
		return standby_tv_web.in_panou(pagina)
	except Exception as eroare:
		print("[HdsWebControl] randurile standby si televizorul: %s" % eroare)
		return pagina


# True dupa ce _construiesteResurse a pus rutele descarcarii subtitrarilor (importul descarcare_subtitrari_web a
# reusit); legatura din panou urmeaza aceeasi conditie, ca sa nu duca spre o pagina care nu exista
_DESCARCARE_PUSA = {"pagina": False}


def _legaturiDisponibile(pagina):
	"""Panoul si /ecrane: legatura spre /accel numai pe un receptor cu accelerarea 2D (regula:
	meniul si web-ul arata doar ce exista pe receptor), la fel ca randul din setup.xml (accel_web.py)."""
	try:
		from . import accel_web
		pagina = accel_web.faraLegaturaDacaLipseste(pagina)
		from . import procesor_web
		pagina = procesor_web.faraLegaturaDacaLipseste(pagina)
		from . import afisaj_web
		pagina = afisaj_web.faraLegaturaDacaLipseste(pagina)
		# "Descărcare subtitrări" e in imagine din 0.3.2: legatura lipseste numai daca importul paginii a cazut
		if not _DESCARCARE_PUSA["pagina"]:
			# dupa adresa, nu dupa text: panoul e tradus in limba receptorului
			pagina = re.sub(r'  <a href="/descarcare-subtitrari">[^<]*</a>\n', "", pagina)
	except Exception as eroare:
		print("[HdsWebControl] legaturile panoului: %s" % eroare)
	return _semneLegaturi(pagina)


def _semneLegaturi(pagina):
	"""legaturile primesc semnul „(în lucru)” / „(netestat)” al intrarii de pe televizor care
	are aceeasi pagina (atributul web= si stare= din menu.xml), iar /accel pe cel al randului din setup.xml.
	Starea se scrie numai in menu.xml / setup.xml (Components/HdsStareMeniu.py)."""
	try:
		from Components import HdsStareMeniu
		from . import scanare_web
		stari = HdsStareMeniu.stariWeb(scanare_web._caleMeniu())
		s = HdsStareMeniu.stareSetare(_caleSetup(), "config.usage.hds_accel_2d")
		if s:
			stari["/accel"] = s
		# semnul in limba paginii (panoul e tradus)
		return HdsStareMeniu.semneInLegaturi(pagina, stari, _t)
	except Exception as eroare:
		print("[HdsWebControl] semnele legaturilor: %s" % eroare)
		return pagina


def _caleSetup():
	"""data/setup.xml pe receptor (ca Screens/Setup.py: ${datadir}/enigma2/setup.xml)."""
	try:
		from enigma import eEnv
		return eEnv.resolve("${datadir}/enigma2/setup.xml")
	except Exception:
		return "/usr/share/enigma2/setup.xml"


def _motorPentruWeb():
	"""Corpul raspunsului pentru GET /api/motor: EXACT aceleasi campuri pe care le deseneaza si ecranul de pe
	televizor (Screens/HdsDishMotor.py), luate din acelasi modul Components/HdsMotorStare.py, ca sa nu existe
	doua adevaruri despre acelasi motor. Numai citire: nu trimite nicio comanda spre antena."""
	try:
		from Components.HdsMotorStare import stareJson
	except Exception as eroare:
		return {"result": False, "message": "starea motorului nu se poate citi: %s" % eroare, "activ": False}
	try:
		stare = stareJson()
	except Exception as eroare:
		_jurnal("motor: citirea starii a esuat: %s" % eroare)
		return {"result": False, "message": "starea motorului nu se poate citi", "activ": False}
	stare["result"] = True
	return stare


# Pagina /motor (afisajul rotirii si comenzile motorului) sta in antena_web.py, langa paginile
# „Configurare LNB” si „Găsire semnal”, din aceeasi sectiune; numele de aici ramane pentru cine il foloseste
# (_paginaMotor, probele).
from .antena_web import PAGINA_MOTOR as _PAGINA_MOTOR  # noqa: E402


_PAGINA_FONTURI = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fonturi Google</title>
<style>""" + _STIL_COMUN + """
  main{max-width:900px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 4px;}
  .subtitlu{color:var(--text-slab);font-size:.85rem;margin:0 0 16px;min-height:1.2em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin-bottom:16px;}
  .card h2{font-size:.95rem;margin:0 0 12px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  input[type=search]{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;border:1px solid var(--bordura);background:var(--fundal);color:inherit;font-size:1rem;}
  table{width:100%;border-collapse:collapse;font-size:.9rem;}
  th{text-align:left;color:var(--text-slab);font-weight:600;font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;padding:6px 8px;}
  td{padding:7px 8px;border-top:1px solid var(--bordura);vertical-align:middle;}
  button{border:0;border-radius:8px;padding:7px 12px;color:#fff;background:var(--verde);cursor:pointer;font-size:.85rem;}
  button.sterge{background:var(--rosu);}
  button[disabled]{opacity:.45;cursor:default;}
  .gol{color:var(--text-slab);font-size:.9rem;margin:0;}
  .mic{color:var(--text-slab);font-size:.8rem;}
  footer{color:var(--text-slab);font-size:.8rem;}
</style>
</head>
<body>
<main>
<h1>Fonturi Google</h1>
<p class="subtitlu" id="subtitlu">Se citește lista...</p>

<div class="card">
  <h2>Caută</h2>
  <input type="search" id="cauta" placeholder="Numele fontului, de exemplu Roboto" autocomplete="off">
  <p class="mic" id="unde"></p>
</div>

<div class="card">
  <h2>Fonturi descărcate pe receptor</h2>
  <div id="descarcate"><p class="gol">...</p></div>
</div>

<div class="card">
  <h2>Toate familiile libere</h2>
  <div id="toate"><p class="gol">...</p></div>
</div>


<script>
var CFG = __CONFIG__;
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  return fetch(adresa(cale), optiuni).then(function(r){ return r.json(); });
}
function octeti(n){
  if(n >= 1048576){ return (n/1048576).toFixed(1) + " MB"; }
  if(n >= 1024){ return Math.round(n/1024) + " KB"; }
  return n + " B";
}
var ultima = "";
var ocupat = false;
function stare(text){ document.getElementById("subtitlu").textContent = text; }

function deseneaza(d){
  document.getElementById("unde").textContent = "Se scriu în " + d.unde +
    (d.pe_mediu_extern ? " (mediu extern, rezistă la actualizarea imaginii)" : " (memoria receptorului: o actualizare de imagine le șterge)") +
    ". Liber: " + octeti(d.spatiu_liber) + ".";
  if(d.mod_sigur){ document.getElementById("unde").textContent = d.mod_sigur + " " +
    document.getElementById("unde").textContent; }

  var gazda = document.getElementById("descarcate");
  if(!d.descarcate.length){ gazda.innerHTML = '<p class="gol">Niciun font descărcat încă.</p>'; }
  else {
    var h = '<table><tr><th>Familia</th><th>Nume in skin</th><th>Mărime</th><th>Diacritice</th><th>Verificare</th><th></th></tr>';
    d.descarcate.forEach(function(f){
      h += '<tr><td>' + f.familie + '</td><td><code>' + f.alias + '</code></td><td>' + octeti(f.octeti) + '</td>' +
           '<td>' + (f.diacritice || "-") + '</td><td>' + (f.bun ? "în regulă" : f.motiv) + '</td>' +
           '<td><button class="sterge" data-sterge="' + f.alias + '">Șterge</button></td></tr>';
    });
    gazda.innerHTML = h + '</table>';
  }

  var lista = document.getElementById("toate");
  if(!d.familii.length){ lista.innerHTML = '<p class="gol">Nimic găsit.</p>'; }
  else {
    var t = '<table><tr><th>Familia</th><th>Categorie</th><th>Diacritice</th><th>Familia întreagă</th><th></th></tr>';
    d.familii.forEach(function(f){
      t += '<tr><td>' + f.familie + '</td><td>' + f.categorie + '</td>' +
           '<td>' + (f.diacritice_probabile ? "ăâîșț" : "probabil nu") + '</td>' +
           '<td>' + octeti(f.marime) + '</td><td>' +
           (f.descarcat ? '<span class="mic">descărcat</span>'
                        : '<button data-descarca="' + f.familie.replace(/"/g, "&quot;") + '">Descarcă</button>') +
           '</td></tr>';
    });
    lista.innerHTML = t + '</table>';
  }
  stare("Arătate " + d.aratate + " din " + d.gasite + " găsite (" + d.total + " familii libere în total).");
}

function incarca(){
  if(ocupat){ return; }
  ocupat = true;
  cerere("/api/fonturi?cauta=" + encodeURIComponent(ultima)).then(function(d){
    ocupat = false;
    if(!d.result){ stare(d.message || "Lista nu s-a putut citi."); return; }
    deseneaza(d);
  }).catch(function(){ ocupat = false; stare("Receptorul nu răspunde."); });
}

document.getElementById("cauta").addEventListener("input", function(e){
  ultima = e.target.value;
  clearTimeout(window._t);
  window._t = setTimeout(incarca, 350);
});

document.addEventListener("click", function(e){
  var familie = e.target.getAttribute && e.target.getAttribute("data-descarca");
  var alias = e.target.getAttribute && e.target.getAttribute("data-sterge");
  if(familie){
    e.target.disabled = true;
    stare("Se descarcă „" + familie + "”...");
    cerere("/api/fonturi-descarca?familie=" + encodeURIComponent(familie), "POST").then(function(d){
      if(!d.result && d.confirmare_ceruta && confirm(d.message + "\\n" + "Descarci totuși?")){
        return cerere("/api/fonturi-descarca?mare=1&familie=" + encodeURIComponent(familie), "POST");
      }
      return d;
    }).then(function(d){ stare(d.message || ""); incarca(); })
      .catch(function(){ stare("Descărcarea a eșuat."); e.target.disabled = false; });
  }
  if(alias){
    if(!confirm("Ștergi fontul " + alias + "? Un skin care îl folosește va rămâne fără el.")){ return; }
    cerere("/api/fonturi-sterge?alias=" + encodeURIComponent(alias), "POST")
      .then(function(d){ stare(d.message || ""); incarca(); })
      .catch(function(){ stare("Ștergerea a eșuat."); });
  }
});

incarca();
</script>
</main>
</body>
</html>
"""


def _paginaMotor(request):
	"""GET /motor: aceeasi poarta ca panoul (reteaua locala, apoi ?token= sau cookie-ul browserului asociat);
	un browser neconectat primeste pagina de asociere, exact ca la „/". Pagina (afisajul si
	comenzile motorului) e in antena_web.py; cu cookie primeste tokenul CSRF, fiindca de acolo se dau comenzi."""
	from . import antena_web
	return antena_web.paginaMotor(request)


# ------------------------------------------------------------------ resurse Twisted


# ------------------------------------------------------------------ interfetele web ale cam-urilor
# Un buton „Interfețe CAM" in interfata web, care arata interfetele web
# ale cam-urilor instalate pe receptor (module de acces sau extensii care fac acelasi lucru) si le deschide.
# REGULA DE BAZA: in imagine nu se scrie numele niciunui cam, niciun port si nicio cale a vreunui cam. Numele de
# pe fiecare rand il da cam-ul insusi, la rulare (titlul paginii lui, antetul Server, scriptul sau pachetul lui).
# Descoperirea e toata in Components/HdsInterfeteCam.py (o singura sursa); aici rezultatul trece prin poarta web,
# se curata inca o data (e text venit de la alt program) si se trimite. Pe televizor nu e ecran nou: receptorul are
# deja meniul CAM. Pagina nu face proxy spre cam: da doar portul, iar adresa o face
# browserul din adresa receptorului.
_MAX_TEXT_CAM = 80
_MAX_CAM_URI = 32
_MAX_INTERFETE_PE_CAM = 12
_SURSE_NUME_CAM = ("titlu", "server", "realm", "script", "pachet", "proces")
_FELURI_CAM = ("emulator", "plugin", "program")
_STARI_INTERFATA = ("web", "nu_e_web", "nu_raspunde", "neverificat")


def _textCamCurat(valoare, maxim=_MAX_TEXT_CAM):
	"""Text venit de la alt program (titlul paginii unui cam, antetul lui Server): fara surogate, fara caractere de
	control si de intoarcere a scrisului, spatiile stranse, cel mult `maxim` caractere. In pagina intra oricum numai
	prin textContent; curatarea tine raspunsul UTF-8 valid (`_trimite` codeaza strict)."""
	if valoare is None:
		return ""
	if isinstance(valoare, bytes):
		valoare = valoare.decode("utf-8", "replace")
	elif not isinstance(valoare, str):
		valoare = str(valoare)
	litere = []
	for c in valoare:
		cod = ord(c)
		if (cod < 32 or 127 <= cod < 160 or 0xD800 <= cod <= 0xDFFF or 0x200B <= cod <= 0x200F
				or 0x202A <= cod <= 0x202E or 0x2066 <= cod <= 0x2069 or cod == 0xFEFF):
			litere.append(" ")
		else:
			litere.append(c)
	return " ".join("".join(litere).split())[:maxim].strip()


def _portCamBun(port):
	# bool e si el int in Python: True nu e portul 1
	return isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536


def _codHttpCam(cod):
	if isinstance(cod, int) and not isinstance(cod, bool) and 100 <= cod <= 599:
		return cod
	return None


def _gazdaCamBuna(gazda):
	"""Adresa anume pe care asculta un cam (cand nu asculta pe toate): numai o adresa IP scrisa cu cifre, IPv4 sau
	IPv6, altfel ''. Intra in adresa legaturii din pagina, deci nu trece nimic altceva."""
	if not isinstance(gazda, str) or not gazda or len(gazda) > 45:
		return ""
	parti = gazda.split(".")
	if len(parti) == 4 and all(p.isdigit() and len(p) <= 3 and int(p) <= 255 for p in parti):
		return gazda
	if ":" in gazda and all(c in "0123456789abcdefABCDEF:" for c in gazda):
		return gazda
	return ""


def _rezultatCamPentruWeb(date):
	"""Din ce a intors modulul de descoperire, numai campurile pe care le foloseste pagina, cu tipurile verificate:
	un port care nu e numar intre 1 si 65535 scoate interfata, o schema necunoscuta devine http, listele se taie."""
	if not isinstance(date, dict):
		return {"result": False, "message": _t("Căutarea modulelor a întors un răspuns pe care nu îl înțeleg."),
			"cam_uri": []}
	if date.get("result") is False:
		# mesajul modulului e textul unei exceptii: ramane in jurnal, pagina primeste unul limpede
		_jurnal("interfete CAM: cautarea a esuat: %s" % _textCamCurat(date.get("message"), 200))
		return {"result": False, "message": _t("Căutarea modulelor nu a mers pe receptor."), "cam_uri": []}
	cam_uri = []
	lista = date.get("cam_uri")
	for cam in (lista if isinstance(lista, (list, tuple)) else ())[:_MAX_CAM_URI]:
		if not isinstance(cam, dict):
			continue
		interfete = []
		lista_i = cam.get("interfete")
		for i in (lista_i if isinstance(lista_i, (list, tuple)) else ()):
			if len(interfete) >= _MAX_INTERFETE_PE_CAM:
				break
			if not isinstance(i, dict) or not _portCamBun(i.get("port")):
				continue
			cod = _codHttpCam(i.get("cod_http"))
			verificat = i.get("verificat") is not False
			stare = i.get("stare")
			if stare not in _STARI_INTERFATA:
				stare = ("web" if cod is not None else "nu_e_web") if verificat else "neverificat"
			web = bool(i["web"]) if "web" in i else stare == "web"
			interfete.append({
				"port": i["port"],
				"schema": "https" if i.get("schema") == "https" else "http",
				"doar_local": bool(i.get("doar_local")),
				"gazda": _gazdaCamBuna(i.get("gazda")),
				"stare": stare,
				"web": web and stare == "web",
				"verificat": verificat,
				"cod_http": cod,
				"cere_parola": bool(i.get("cere_parola")) or cod in (401, 403),
				"nume": _textCamCurat(i.get("nume")),
			})
		sursa = cam.get("sursa_nume")
		fel = cam.get("fel")
		cam_uri.append({
			"nume": _textCamCurat(cam.get("nume")),
			"sursa_nume": sursa if sursa in _SURSE_NUME_CAM else "",
			"fel": fel if fel in _FELURI_CAM else "",
			"pornit": bool(cam.get("pornit")),
			"ales": bool(cam.get("ales")),
			"interfete": interfete,
		})
	durata = date.get("durata")
	return {
		"result": True,
		"message": _textCamCurat(date.get("message"), 200),
		"durata": round(float(durata), 1) if isinstance(durata, (int, float)) and not isinstance(durata, bool) and 0 <= durata < 600 else None,
		"decripteaza_acum": bool(date.get("decripteaza_acum")),
		"cam_uri": cam_uri,
	}


def _interfeteCamPentruWeb(reincarca=False, port_web=None):
	"""Corpul raspunsului pentru GET /api/interfete-cam. Blocanta (cautarea deschide conexiuni locale spre porturile
	cam-urilor, cel mult cateva secunde): se cheama NUMAI de pe firul separat al resursei, niciodata de pe firul
	enigma2. Nu atinge `request`, deci merge si pe PC, fara Twisted (teste/test_interfete_cam_web.py).
	`HdsInterfeteCam.rezultat()` tine singur o singura cautare deodata (doua browsere primesc aceeasi) si pastreaza
	rezultatul cateva secunde; `reincarca` cere una noua. Intoarce None cand cautarea nu s-a terminat in termenul lui.
	Un modul de descoperire lipsa sau stricat da `result: false` cu un mesaj, nu eroare 500."""
	try:
		from Components import HdsInterfeteCam as descoperire
	except ImportError:
		return {"result": False, "message": _t("Căutarea modulelor nu este în această versiune a imaginii."),
			"cam_uri": []}
	rezultat = getattr(descoperire, "rezultat", None)
	if not callable(rezultat):
		return {"result": False, "message": _t("Căutarea modulelor nu este în această versiune a imaginii."),
			"cam_uri": []}
	excluse = (port_web,) if _portCamBun(port_web) else ()
	try:
		date = rezultat(reincarca=bool(reincarca), porturi_excluse=excluse)
		if date is None:
			return {"result": False, "cam_uri": [],
				"message": _t("Căutarea nu s-a terminat la timp. Apasă Caută din nou peste câteva secunde.")}
		return _rezultatCamPentruWeb(date)
	except Exception as eroare:
		_jurnal("interfete CAM: cautarea a esuat: %s" % eroare)
		return {"result": False, "message": _t("Căutarea modulelor nu a mers pe receptor."), "cam_uri": []}


# Pagina „Interfețe CAM": un card pe cam, cu randurile interfetelor lui si butonul „Deschide". Tot ce vine de la
# cam-uri (nume, texte) intra in pagina NUMAI prin textContent. Adresa interfetei o face pagina din
# location.hostname (adresa cu care omul a deschis deja receptorul) si portul primit, verificat ca numar.
_PAGINA_INTERFETE_CAM = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interfețele web ale modulelor</title>
<style>""" + _STIL_COMUN + """
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 4px;}
  .subtitlu{color:var(--text-slab);font-size:.85rem;margin:0 0 16px;}
  .bara{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin:0 0 16px;}
  .bara .stare{color:var(--text-slab);font-size:.9rem;}
  .bara .stare.rau{color:#ff9a8f;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin-bottom:16px;}
  .cap{display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;}
  .cap h2{font-size:1.05rem;margin:0;overflow-wrap:anywhere;}
  .semn{font-size:.72rem;border-radius:999px;padding:3px 10px;white-space:nowrap;background:#242a33;color:var(--text-slab);}
  .semn.pornit{background:var(--verde);color:#fff;}
  .de-unde{color:var(--text-slab);font-size:.78rem;margin:6px 0 0;}
  .interfata{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 12px;padding:12px 0 0;margin-top:12px;border-top:1px solid var(--bordura);}
  .interfata .nume{font-size:.95rem;overflow-wrap:anywhere;}
  .interfata .detaliu{color:var(--text-slab);font-size:.8rem;margin-top:3px;}
  .buton{display:inline-flex;align-items:center;justify-content:center;min-height:44px;background:var(--accent);color:#fff;text-decoration:none;border:none;border-radius:8px;padding:0 20px;font-size:.95rem;cursor:pointer;}
  .buton[disabled]{background:#3a424e;color:#8891a0;cursor:default;}
  .gol{color:var(--text-slab);font-size:.9rem;margin:12px 0 0;}
  .card > .gol:first-child{margin-top:0;}
  footer{color:var(--text-slab);font-size:.8rem;display:flex;flex-wrap:wrap;gap:8px 18px;}
  @media(max-width:520px){
    .interfata{flex-direction:column;align-items:stretch;}
    .bara .buton, .interfata .buton{width:100%;}
  }
</style>
</head>
<body>
<main>
<h1>Interfețele web ale modulelor</h1>
<p class="subtitlu">Paginile web ale modulelor de acces condiționat instalate pe receptor. Numele le spune fiecare modul, la căutare.</p>
<div class="bara">
  <span class="stare" id="stare">Se caută...</span>
  <button class="buton" id="cautaDinNou" disabled>Caută din nou</button>
</div>
<div id="lista"></div>
<footer>
  <a id="module" href="/acces-conditionat">Module de acces condiționat</a>
</footer>
</main>
<script>
var CFG = __CONFIG__;
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
document.getElementById("module").href = adresa("/acces-conditionat");
var SURSE = {
  titlu: "Numele e titlul paginii lui.",
  server: "Numele e cel trimis de serverul lui.",
  realm: "Numele e cel din cererea lui de parolă.",
  script: "Numele e cel din scriptul lui de pornire.",
  pachet: "Numele e cel din pachetul lui.",
  proces: "Numele e cel al programului care rulează."
};
var ocupat = false;
function el(tip, clasa, text){
  var e = document.createElement(tip);
  if(clasa){ e.className = clasa; }
  if(text !== undefined && text !== null){ e.textContent = String(text); }
  return e;
}
function stare(text, rau){
  var s = document.getElementById("stare");
  s.textContent = text;
  s.className = "stare" + (rau ? " rau" : "");
}
var FELURI = {emulator: "modul", plugin: "extensie", program: "program"};
function portBun(p){ return typeof p === "number" && Math.floor(p) === p && p > 0 && p < 65536; }
function gazdaInterfetei(i){
  // adresa anume pe care asculta cam-ul (IP scris cu cifre, verificat pe receptor), altfel adresa cu care
  // s-a deschis deja receptorul in browser
  var g = i.gazda;
  if(typeof g === "string" && /^[0-9.]+$/.test(g)){ return g; }
  if(typeof g === "string" && /^[0-9a-fA-F:]+$/.test(g) && g.indexOf(":") !== -1){ return "[" + g + "]"; }
  return location.hostname;
}
function adresaInterfetei(i){
  if(!portBun(i.port)){ return null; }
  return (i.schema === "https" ? "https" : "http") + "://" + gazdaInterfetei(i) + ":" + i.port + "/";
}
function deAratat(i){ return i.web === true || i.stare === "neverificat" || i.stare === "nu_raspunde"; }
function randInterfata(cam, i){
  var rand = el("div", "interfata");
  var stanga = el("div");
  stanga.appendChild(el("div", "nume", (i.nume && i.nume !== cam.nume) ? i.nume : "Interfața web"));
  var detalii = ["portul " + i.port];
  if(i.schema === "https"){ detalii.push("conexiune criptată"); }
  if(i.cere_parola){ detalii.push("cere parolă"); }
  rand.appendChild(stanga);
  if(i.web !== true){
    detalii.push(i.stare === "nu_raspunde"
      ? "nu a răspuns la căutare"
      : "neverificată: căutarea s-a oprit înainte; apasă Caută din nou");
    stanga.appendChild(el("div", "detaliu", detalii.join(", ")));
    return rand;
  }
  if(i.doar_local){
    detalii.push("ascultă doar pe receptor, deci nu se deschide din telefon sau calculator");
    stanga.appendChild(el("div", "detaliu", detalii.join(", ")));
    return rand;
  }
  stanga.appendChild(el("div", "detaliu", detalii.join(", ")));
  var tinta = adresaInterfetei(i);
  if(tinta){
    var a = el("a", "buton", "Deschide");
    a.href = tinta;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    rand.appendChild(a);
  }
  return rand;
}
function cardCam(cam){
  var card = el("div", "card");
  var cap = el("div", "cap");
  cap.appendChild(el("h2", "", cam.nume || "Modul fără nume"));
  cap.appendChild(el("span", "semn" + (cam.pornit ? " pornit" : ""), cam.pornit ? "pornit" : "oprit"));
  if(FELURI[cam.fel]){ cap.appendChild(el("span", "semn", FELURI[cam.fel])); }
  if(cam.ales){ cap.appendChild(el("span", "semn", "ales pe receptor")); }
  card.appendChild(cap);
  if(SURSE[cam.sursa_nume]){ card.appendChild(el("p", "de-unde", SURSE[cam.sursa_nume])); }
  var interfete = (cam.interfete || []).filter(deAratat);
  interfete.forEach(function(i){ card.appendChild(randInterfata(cam, i)); });
  if(!interfete.length){
    card.appendChild(el("p", "gol", cam.pornit
      ? "Pornit, dar nu are interfață web (sau nu răspunde acum)."
      : "Oprit. Se pornește din pagina Module de acces condiționat; după pornire, apasă Caută din nou."));
  }
  return card;
}
function cate(n){ return n === 1 ? "Un modul găsit." : n + (n < 20 ? "" : " de") + " module găsite."; }
function arata(d){
  var lista = document.getElementById("lista");
  lista.textContent = "";
  if(!d || d.result === false){
    stare((d && d.message) || "Căutarea nu a mers.", true);
    return;
  }
  var cam_uri = Array.isArray(d.cam_uri) ? d.cam_uri : [];
  if(!cam_uri.length){
    var card = el("div", "card");
    card.appendChild(el("p", "gol", "Nu e instalat niciun modul de acces condiționat pe receptor. După ce instalezi unul, apasă Caută din nou."));
    lista.appendChild(card);
    stare("Căutare terminată.");
    return;
  }
  cam_uri.forEach(function(cam){ lista.appendChild(cardCam(cam)); });
  stare(cate(cam_uri.length) + (d.decripteaza_acum ? " Receptorul decriptează acum un canal." : ""));
}
function cauta(dinNou){
  if(ocupat){ return; }
  ocupat = true;
  var buton = document.getElementById("cautaDinNou");
  buton.disabled = true;
  stare("Se caută modulele de pe receptor...");
  fetch(adresa("/api/interfete-cam" + (dinNou ? "?reincarca=1" : "")), {cache: "no-store", credentials: "same-origin"}).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    if(r.status === 504){ throw new Error("căutarea a durat prea mult"); }
    return r.json();
  }).then(arata).catch(function(e){
    document.getElementById("lista").textContent = "";
    stare("Receptorul nu a răspuns (" + e.message + ").", true);
  }).then(function(){
    ocupat = false;
    buton.disabled = false;
  });
}
document.getElementById("cautaDinNou").addEventListener("click", function(){ cauta(true); });
cauta(false);
</script>
</body>
</html>
"""


def _paginaInterfeteCam(request):
	"""GET /interfete-cam: aceeasi poarta ca panoul (reteaua locala, apoi ?token= sau cookie-ul browserului
	asociat); un browser neconectat primeste pagina de asociere, exact ca la „/". Antetul Host e verificat inainte,
	in _CerereHds.process, pentru orice cale."""
	if not _esteAdresaLocala(_adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	_anteteHtml(request)
	if PARAM_JETON in request.args and _jetonValid(request):
		jeton = _jetonConfigurat()  # valoarea de pe SERVER, nu cea primita de la client
		return _traducePagina(_PAGINA_INTERFETE_CAM).replace("__CONFIG__", _configPanou("", jeton, "")).encode("utf-8",
			"replace")
	secret, browser = _sesiuneDinCerere(request)
	if browser is not None:
		# pagina doar citeste (GET), deci nu primeste tokenul CSRF al panoului: n-ar avea ce comanda cu el
		return _traducePagina(_PAGINA_INTERFETE_CAM).replace("__CONFIG__", _configPanou("", "", browser.get("nume",
			""))).encode("utf-8", "replace")
	return _traducePagina(_PAGINA_ASOCIERE).encode("utf-8")


def zapReferinta(sref_text):
	"""Porneste referinta pe televizor, ca /api/zap: (True, referinta pornita, 200) sau (False, motivul, cod HTTP).
	Folosita si de rutele aplicatiilor de telefon (aplicatii_web.py, /web/zap si /api/zap in forma compatibila)."""
	import NavigationInstance
	from enigma import eServiceReference
	# o referinta cu adresa decodata o data in plus (sRef cu „%3a” pus in URL fara „%253a”: aici vine cu „:”)
	# ar lua calea „http” si n-ar reda nimic; se reda in forma buna (Hds/DabT2/buchete.repara_cale_decodata)
	try:
		from Hds.DabT2.buchete import repara_cale_decodata
		reparat = repara_cale_decodata(sref_text)
		if reparat is not None:
			_jurnal("zap: sRef cu adresa decodata, redat ca %s" % reparat[:120])
			sref_text = reparat
	except Exception as eroare:
		_jurnal("zap: verificarea adresei din sRef: %s" % eroare)
	nav = NavigationInstance.instance
	if nav is None:
		return False, "navigatia nu e initializata inca", 503
	try:
		ref = eServiceReference(sref_text)
		if not ref.valid():
			return False, "referinta de serviciu invalida: %s" % sref_text, 400
		nav.playService(ref)
	except Exception as eroare:
		return False, "zap esuat: %s" % eroare, 500
	# canalul pornit pentru om: tinut minte ca la zap-ul din lista, ca dupa o repornire a interfetei receptorul sa
	# porneasca pe el (Components/HdsCanalTinut.py)
	try:
		from Components.HdsCanalTinut import tine_minte
		tine_minte(ref)
	except Exception as eroare:
		_jurnal("zap: canalul tinut minte: %s" % eroare)
	return True, sref_text, 200


def _construiesteResurse():
	"""Construieste arborele de resurse Twisted. Import intarziat al twisted.web,
	ca fisierul sa poata fi macar incarcat (py_compile/import de test) chiar si
	fara pachetul twisted instalat pe masina care verifica sintaxa."""
	from twisted.web import resource
	from twisted.web.server import NOT_DONE_YET
	from twisted.internet import reactor

	class HdsJsonResource(resource.Resource):
		"""Baza comuna: raspunde intotdeauna JSON, UTF-8, cu 'result' obligatoriu (True/False).
		Trece FIECARE cerere prin `_verificaAcces` (retea locala, apoi ?token= sau cookie-ul browserului
		asociat), inainte de orice alta procesare -- vezi notele de securitate de la inceputul fisierului.
		`schimbaCeva = True` la resursele care apasa taste sau schimba canalul: cu cookie, ele cer in plus
		POST + Origin/Referer egal cu Host + antetul CSRF al panoului."""
		isLeaf = True
		schimbaCeva = False

		def render(self, request):
			mod, eroare = _verificaAcces(request, self.schimbaCeva)
			if eroare is not None:
				request.setHeader(b"Access-Control-Allow-Origin", b"*")
				if eroare[0] == 405:
					request.setHeader(b"allow", b"POST")
				return self._eroare(request, eroare[1], eroare[0])
			if mod == "jeton":
				# CORS: fara acest antet, un fetch() din
				# JavaScript pornit de pe alt domeniu (ex. o pagina de control gazduita pe hdsatelit.com)
				# nu poate CITI raspunsul. Doar in modul jeton: acolo autentificarea e jetonul din adresa, pe
				# care o pagina straina nu il are. In modul cookie nu trimitem antetul (browserele oricum nu
				# arata unei alte origini un raspuns cu cookie sub "*", dar asa e limpede din cod).
				request.setHeader(b"Access-Control-Allow-Origin", b"*")
			return resource.Resource.render(self, request)

		def _raspunde(self, request, corp, cod=200):
			request.setResponseCode(cod)
			request.setHeader(b"content-type", b"application/json; charset=utf-8")
			request.setHeader(b"cache-control", b"no-store")
			# un nume de canal sau un titlu venit de la emițător poate avea octeți care nu sunt
			# UTF-8 (ajung în Python cu surogate); `encode("utf-8")` strict ar arunca UnicodeEncodeError și
			# cererea s-ar termina cu 500. Cu "replace" răspunsul rămâne UTF-8 valid pentru browser.
			return json.dumps(corp, ensure_ascii=False).encode("utf-8", "replace")

		def _eroare(self, request, mesaj, cod=400):
			return self._raspunde(request, {"result": False, "message": mesaj}, cod)

	class StatusInfoResource(HdsJsonResource):
		def render_GET(self, request):
			import NavigationInstance
			from ServiceReference import ServiceReference
			from . import radio_web
			try:
				from enigma import eDVBVolumecontrol
			except ImportError:
				eDVBVolumecontrol = None

			nav = NavigationInstance.instance
			nume_serviciu = ""
			ref_serviciu = ""
			# inainte `in_standby = nav is None`, dar
			# navigatia ramane viata in standby; standby-ul real e ecranul Standby deschis (Screens.Standby.inStandby)
			in_standby = _stareTelevizor() == "standby"
			if nav is not None:
				try:
					servi = nav.getCurrentlyPlayingServiceReference()
					if servi is not None:
						ref_serviciu = servi.toString()
						nume_serviciu = ServiceReference(servi).getServiceName()
				except Exception as eroare:
					_jurnal("statusinfo: %s" % eroare)

			volum = -1
			mut = False
			if eDVBVolumecontrol is not None:
				try:
					vc = eDVBVolumecontrol.getInstance()
					volum = vc.getVolume()
					mut = bool(vc.isMuted())
				except Exception:
					pass

			return self._raspunde(request, {
				"result": True,
				"currservice_name": nume_serviciu,
				"currservice_serviceref": ref_serviciu,
				"volume": volum,
				"muted": mut,
				"in_standby": in_standby,
				"imagine": "HDSatelit",
				# modul sigur (mod_sigur_web.bandaPanou): textul benzii panoului, "" in afara lui; numai mediul
				"mod_sigur": mod_sigur_web.bandaPanou(),
				# intrebarea primei porniri, copia altei imagini (scanare_import_web.banda_panou): textul benzii cat
				# timp e deschisa, altfel ""
				"alta_imagine": scanare_import_web.banda_panou(),
				# semnalul si calitatea, ca pe bara de la TV (la DAB+ / DVB-T2 din satelit: tunerul purtatorului)
				"semnal": radio_web.semnal_panou(nav) if nav is not None and not in_standby else None,
				# DVB-I (internet_web.dvbiPanou): canalul are si varianta de internet / merge acum prin
				# internet, cu starea retelei in locul semnalului
				"dvbi": _dvbiPanou(ref_serviciu),
			})

	def _dvbiPanou(ref):
		try:
			from .internet_web import dvbiPanou
			return dvbiPanou(ref)
		except Exception:
			return {"are": False, "prin_internet": False, "retea": ""}

	class RemoteControlResource(HdsJsonResource):
		# GET ramane pentru scripturile cu ?token= (compatibilitate); panoul trimite POST (vezi _verificaAcces)
		schimbaCeva = True

		def render_POST(self, request):
			return self.render_GET(request)

		def render_GET(self, request):
			# cat ecranul "Parola receptorului" e deschis pe receptor (parola mare, OK pe "Fără parolă în rețeaua locală"),
			# tastele vin numai dintr-un browser conectat cu codul (acces_ssh_web.refuzEcranDeschis)
			refuz = acces_ssh_web.refuzEcranDeschis(request)
			if refuz is not None:
				return self._raspunde(request, refuz, 403)
			valori = request.args.get(b"command")
			if not valori:
				return self._eroare(request, "lipseste parametrul 'command'")
			try:
				cod = int(valori[0])
			except (ValueError, TypeError):
				return self._eroare(request, _t("'command' trebuie sa fie un cod numeric de tasta Linux"))
			if not 0 < cod <= 0x2FF:
				return self._eroare(request, _t("'command' trebuie sa fie un cod de tasta Linux (1-767)"))
			lung = request.args.get(b"lung", [b"0"])[0] in (b"1", b"da")
			try:
				_trimiteTasta(cod, lung)
			except Exception as eroare:
				return self._eroare(request, "injectare esuata: %s" % eroare, 500)
			return self._raspunde(request, {"result": True, "command": cod})

	class ZapResource(HdsJsonResource):
		schimbaCeva = True

		def render_POST(self, request):
			return self.render_GET(request)

		def render_GET(self, request):
			valori = request.args.get(b"sRef")
			if not valori:
				return self._eroare(request, "lipseste parametrul 'sRef'")
			bun, text, cod = zapReferinta(valori[0].decode("utf-8", "replace"))
			if not bun:
				return self._eroare(request, text, cod)
			return self._raspunde(request, {"result": True, "sRef": text})

	class ScreenshotResource(resource.Resource):
		"""GET /api/screenshot?format=jpg|png&quality=N&width=N&mode=all|video|osd&download=1: captura de ecran prin
		`grab` (aio-grab, inclus in imagine), nu prin citirea directa a framebuffer-ului. `-s` scrie pe stdout (fara
		fisier temporar pe disc), `-q` opreste mesajele care s-ar amesteca in octetii imaginii. Fara `width`, rezolutia
		e cea reala a semnalului (grab merge pana la 3840 latime pe receptoarele UHD).
		`mode`: all (implicit) = imaginea canalului cu afisajul OSD peste ea, fara optiune; video = numai imaginea canalului
		(`-v`); osd = numai afisajul OSD (`-o`). `download=1`: raspunsul reusit primeste `Content-Disposition: attachment`,
		cu numele din `_numeCaptura`; erorile raman JSON, fara acest antet.

		grab ruleaza intr-un fir separat (pe firul enigma2 ar ingheta televizorul si telecomanda cat dureaza), iar
		render_GET intoarce imediat NOT_DONE_YET; celelalte cereri raman servite in paralel. Rezultatul vine inapoi pe
		firul enigma2 prin _AsteptareCaptura (pipe propriu in reactor, plus un eTimer ca plasa de siguranta si termen),
		nu prin reactor.callLater sau callFromThread (vezi _AsteptareCaptura).
		Raspunsuri: 200 cu imaginea; 400 format sau mode gresit; 500 fara grab sau eroare interna; 502 grab a esuat;
		503 o captura e deja in curs sau un grab oprit cu kill() n-a iesit inca; 504 grab n-a terminat in TIMEOUT_S sau
		rezultatul n-a ajuns in TERMEN_S. Bariera `_captura_in_curs` se ridica la fiecare raspuns."""
		isLeaf = True

		LATIME_MAXIMA = 3840  # cf. `grab -h`: "resize to a fixed width, maximum: 1920, 3840 on e2egl/UHD boxes"
		TIMEOUT_S = 8  # o captura reala dureaza sub 1 s; dupa 8 s procesul grab e oprit
		ASTEPTARE_OPRIRE_S = 2  # dupa kill(), cat mai asteapta firul iesirea procesului (marginit si in starea D)
		TERMEN_S = TIMEOUT_S + ASTEPTARE_OPRIRE_S + 2  # pe firul enigma2: fara rezultat dupa atat, 504 si bariera ridicata
		CEAS_MS = 250  # plasa de siguranta: verificarea rezultatului daca trezirea prin pipe n-ar veni

		def _poarta(self, request):
			"""Aceeasi poarta ca /api/* (HdsJsonResource.render): retea locala, apoi ?token= sau cookie; doar citire, deci
			fara conditia de POST/CSRF (un <img> din panou trimite cookie-ul singur). /grab (aplicatii_web.py) o
			inlocuieste: acolo bariera aplicatiilor de telefon e trecuta inainte."""
			return _verificaAcces(request, schimba_ceva=False)

		def render_GET(self, request):
			mod, eroare = self._poarta(request)
			if eroare is not None or mod == "jeton":
				request.setHeader(b"Access-Control-Allow-Origin", b"*")  # vezi nota CORS din HdsJsonResource.render
			if eroare is not None:
				request.setResponseCode(eroare[0])
				request.setHeader(b"content-type", b"application/json; charset=utf-8")
				return json.dumps({"result": False, "message": eroare[1]}).encode("utf-8")
			# cat ecranul "Parola receptorului" e deschis pe receptor, captura numai pentru un browser conectat cu codul
			# (parola se vede mare pe ecran)
			refuz = acces_ssh_web.refuzEcranDeschis(request)
			if refuz is not None:
				request.setResponseCode(403)
				request.setHeader(b"content-type", b"application/json; charset=utf-8")
				return json.dumps(refuz).encode("utf-8")
			global _captura_in_curs
			if _captura_in_curs:
				# bariera serverului, independenta de reprogramarea din /panou (vezi nota de la `_captura_in_curs`)
				request.setResponseCode(503)
				request.setHeader(b"content-type", b"application/json; charset=utf-8")
				request.setHeader(b"retry-after", b"1")
				return json.dumps({"result": False, "message": "o captura e deja in curs -- reincearca peste o clipa"}).encode("utf-8")
			if _grabRamasInViata():
				# un grab oprit cu kill() n-a iesit (blocat in driver): altul ar ramane blocat la fel
				request.setResponseCode(503)
				request.setHeader(b"content-type", b"application/json; charset=utf-8")
				request.setHeader(b"retry-after", b"5")
				return json.dumps({"result": False, "message": "captura anterioara nu s-a oprit inca -- reincearca mai tarziu"}).encode("utf-8")
			format_cerut = request.args.get(b"format", [b"jpg"])[0].decode("ascii", "replace").lower()
			if format_cerut not in ("jpg", "jpeg", "png"):
				request.setResponseCode(400)
				request.setHeader(b"content-type", b"application/json; charset=utf-8")
				return json.dumps({"result": False, "message": "format trebuie sa fie 'jpg' sau 'png'"}).encode("utf-8")
			mod_captura = request.args.get(b"mode", [b"all"])[0].decode("ascii", "replace").lower()
			if mod_captura not in _OPTIUNE_MOD_CAPTURA:
				request.setResponseCode(400)
				request.setHeader(b"content-type", b"application/json; charset=utf-8")
				return json.dumps({"result": False, "message": "mode trebuie sa fie 'all', 'video' sau 'osd'"}).encode("utf-8")
			descarcare = request.args.get(b"download", [b""])[0] == b"1"

			# Paza capturii (captura_sigura.py) NUMAI pentru capturile interfetei web straine (_capturaStraina): imaginea
			# canalului (decodorul video) numai cand driverul e gata, cel mult o data la 1,5 s; altfel numai afisajul OSD,
			# refuz la mode=video, sau ultima poza la cereri dese. Panoul, aplicatiile de telefon (/grab) si scripturile
			# raman numai cu barierele comune (o captura odata, termenul), ca inainte de paza.
			pazita = _capturaStraina(request)
			ce, motiv = "da", ""
			if pazita:
				from . import captura_sigura as CS
				ce, motiv = CS.decide(mod_captura)
				if ce == "refuz":
					request.setResponseCode(503)
					request.setHeader(b"content-type", b"application/json; charset=utf-8")
					request.setHeader(b"retry-after", b"5")
					request.setHeader(b"x-hds-captura", motiv.encode("ascii"))
					return json.dumps({"result": False, "message": "imaginea canalului nu se poate captura acum (%s) -- "
						"reincearca mai tarziu sau cere mode=osd" % motiv}).encode("utf-8")
			mod_efectiv = "osd" if ce == "osd" else mod_captura
			comanda = ["grab", "-q", "-s"] + _OPTIUNE_MOD_CAPTURA[mod_efectiv]
			if format_cerut in ("jpg", "jpeg"):
				calitate = 85
				valori_q = request.args.get(b"quality")
				if valori_q:
					try:
						calitate = max(0, min(100, int(valori_q[0])))
					except (ValueError, TypeError):
						pass
				comanda += ["-j", str(calitate)]
				tip_continut = b"image/jpeg"
			else:
				comanda += ["-p"]
				tip_continut = b"image/png"

			valori_latime = request.args.get(b"width")
			if valori_latime:
				try:
					latime = int(valori_latime[0])
					if 0 < latime <= self.LATIME_MAXIMA:
						comanda += ["-r", str(latime)]
				except (ValueError, TypeError):
					pass

			nume_fisier = _numeCaptura(mod_captura, "png" if format_cerut == "png" else "jpg") if descarcare else None
			cheie_pastrare = tuple(comanda)
			if ce == "des":
				pastrata = CS.dinPastrare(cheie_pastrare)
				if pastrata is None:
					request.setResponseCode(503)
					request.setHeader(b"content-type", b"application/json; charset=utf-8")
					request.setHeader(b"retry-after", b"1")
					return json.dumps({"result": False, "message": "o captura a fost facuta chiar acum -- reincearca "
						"peste o clipa"}).encode("utf-8")
				request.setResponseCode(200)
				request.setHeader(b"content-type", pastrata[1])
				request.setHeader(b"cache-control", b"no-store")
				request.setHeader(b"x-hds-captura", b"des")
				if nume_fisier:
					request.setHeader(b"content-disposition", ('attachment; filename="%s"' % nume_fisier).encode("ascii"))
				return pastrata[0]
			video_pazit = pazita and mod_efectiv != "osd"  # captura straina cu imaginea canalului: intervalul, pastrarea
			timeout_s = self.TIMEOUT_S
			asteptare_oprire_s = self.ASTEPTARE_OPRIRE_S
			termen_s = self.TERMEN_S

			def _eroareJson(cod, mesaj):
				request.setResponseCode(cod)
				request.setHeader(b"content-type", b"application/json; charset=utf-8")
				request.write(json.dumps({"result": False, "message": mesaj}).encode("utf-8"))

			def _gata(perechea):
				# pe firul enigma2 (din _AsteptareCaptura): aici se poate atinge `request`, in firul separat nu
				global _captura_in_curs
				_captura_in_curs = False  # bariera se ridica inainte de orice, chiar daca scrierea raspunsului cade mai jos
				stare, rezultat = perechea
				try:
					if stare == "lipsa":
						_eroareJson(500, "unealta 'grab' nu e disponibila pe acest sistem")
					elif stare == "timeout":
						_eroareJson(504, "captura a durat prea mult (peste %ds)" % timeout_s)
					elif rezultat.returncode != 0 or not rezultat.stdout:
						_jurnal("screenshot: grab a esuat, cod=%s, stderr=%r" % (rezultat.returncode, rezultat.stderr[:200]))
						_eroareJson(502, "captura de ecran a esuat")
					else:
						request.setResponseCode(200)
						request.setHeader(b"content-type", tip_continut)
						request.setHeader(b"cache-control", b"no-store")
						if motiv:
							request.setHeader(b"x-hds-captura", ("osd-" + motiv).encode("ascii"))
						if video_pazit:
							CS.tine(cheie_pastrare, rezultat.stdout, tip_continut)
						if nume_fisier:
							request.setHeader(b"content-disposition", ('attachment; filename="%s"' % nume_fisier).encode("ascii"))
						request.write(rezultat.stdout)
					request.finish()
				except Exception as eroare:
					# clientul poate fi plecat deja (conexiune inchisa intre timp): nu e o eroare a serverului
					_jurnal("screenshot: nu am putut trimite raspunsul (client plecat?): %s" % eroare)

			def _eroareNeasteptata(mesaj_eroare):
				global _captura_in_curs
				_captura_in_curs = False  # ca in _gata: bariera se ridica si pe ramura de eroare
				_jurnal("screenshot: eroare neasteptata in firul separat: %s" % mesaj_eroare)
				try:
					_eroareJson(500, "eroare interna la captura de ecran")
					request.finish()
				except Exception:
					pass

			def _laTermen():
				global _captura_in_curs
				_captura_in_curs = False  # o cerere fara rezultat nu tine bariera pana la repornire
				_jurnal("screenshot: niciun rezultat in %d s, raspuns 504" % termen_s)
				try:
					_eroareJson(504, "captura nu a venit in %d s" % termen_s)
					request.finish()
				except Exception as eroare:
					_jurnal("screenshot: nu am putut trimite raspunsul (client plecat?): %s" % eroare)

			def _lucru():
				return _ruleazaGrab(comanda, timeout_s, asteptare_oprire_s)

			_captura_in_curs = True
			if video_pazit:
				CS.incepeVideo()
			try:
				_AsteptareCaptura(reactor, _lucru, _gata, _eroareNeasteptata, _laTermen, termen_s, self.CEAS_MS).porneste()
			except Exception as eroare:
				_captura_in_curs = False
				_jurnal("screenshot: captura nu a putut porni: %s" % eroare)
				request.setResponseCode(500)
				request.setHeader(b"content-type", b"application/json; charset=utf-8")
				return json.dumps({"result": False, "message": "eroare interna la captura de ecran"}).encode("utf-8")
			return NOT_DONE_YET

	class MotorResource(HdsJsonResource):
		"""GET /api/motor: starea rotirii antenei, aceleasi campuri pe care le arata si ecranul de pe
		televizor. Numai citire (`schimbaCeva` ramane False): de aici nu se misca nimic."""
		def render_GET(self, request):
			return self._raspunde(request, _motorPentruWeb())

	class MotorPaginaResource(resource.Resource):
		"""GET /motor: pagina care arata rotirea antenei si se actualizeaza singura (vezi _paginaMotor)."""
		isLeaf = True

		def render_GET(self, request):
			return _paginaMotor(request)

	class DashboardResource(resource.Resource):
		"""GET /panou: aceeasi pagina ca "/" (vezi _paginaPrincipala). Ramane pentru semnele de carte vechi
		si pentru uneltele care deschid /panou?token=... (mod jeton, ca inainte)."""
		isLeaf = True

		def render_GET(self, request):
			return _paginaPrincipala(request)

	def _json(request, corp, cod=200):
		request.setResponseCode(cod)
		request.setHeader(b"content-type", b"application/json; charset=utf-8")
		request.setHeader(b"cache-control", b"no-store")
		# vezi nota de la HdsJsonResource._raspunde: octeți care nu sunt UTF-8 nu opresc răspunsul
		return json.dumps(corp, ensure_ascii=False).encode("utf-8", "replace")

	def _poartaAsociere(request):
		"""Cererile de asociere nu au inca un cookie, deci nimic de furat, dar o pagina straina ar putea
		umple televizorul de ferestre sau incerca coduri la nimereala. De aceea: doar din reteaua locala si
		doar dintr-o pagina servita chiar de receptor (Origin/Referer egal cu Host). Intoarce None sau
		raspunsul de eroare gata facut."""
		if not _esteAdresaLocala(_adresaClient(request)):
			return _json(request, {"result": False, "mesaj": _t("Acces permis doar din rețeaua locală.")}, 403)
		if not _acelasiOriginCerere(request):
			return _json(request, {"result": False, "mesaj": _t("Cerere respinsă: nu vine din pagina receptorului.")},
				403)
		return None

	class CodAsociereResource(resource.Resource):
		"""POST /asociere/cod: arata codul pe televizor (sau spune de ce nu). Un cod inca valabil se
		refoloseste; `reafiseaza=1` (butonul din pagina) il arata din nou."""
		isLeaf = True

		def render_POST(self, request):
			refuz = _poartaAsociere(request)
			if refuz is not None:
				return refuz
			reafiseaza = request.args.get(b"reafiseaza", [b"0"])[0] == b"1"
			# acelasi cod si aceeasi fereastra ca pentru viitoarea aplicatie (asociere.py: un singur cod activ)
			r = obtineAsociere().cereCod(reafiseaza=reafiseaza, tip=TIP_BROWSER, adresa=_adresaClient(request) or "")
			if r["stare"] == "blocat":
				request.setHeader(b"retry-after", str(r["ramas"]).encode("ascii"))
				return _json(request, {"result": False, "stare": "blocat", "ramas": r["ramas"],
					"mesaj": _t("Au fost prea multe coduri greșite. Încearcă din nou peste %s. %s") % (
						_durataText(r["ramas"]), _sfatDeblocare())}, 429)
			if r["stare"] == "prea_des":
				request.setHeader(b"retry-after", str(r["ramas"]).encode("ascii"))
				return _json(request, {"result": False, "stare": "prea_des", "ramas": r["ramas"],
					"mesaj": _t("Codul a fost cerut de prea multe ori. Încearcă din nou peste %s. %s") % (
						_durataText(r["ramas"]), _sfatDeblocare())}, 429)
			if r["afiseaza"]:
				# codul NU se scrie in jurnal: jurnalele pot ajunge pe un disc partajat in retea, iar cine
				# ar citi codul acolo s-ar putea conecta fara sa vada televizorul
				_jurnal("cod de asociere trimis pe televizor, cerut de %s" % _adresaClient(request))
				# apel direct, nu callLater(0): cererea ruleaza deja pe firul principal enigma2 (reactorul e
				# bucla enigma2), iar callLater putea intarzia 15-20 s in acest reactor cand nu are alte
				# evenimente (vezi _AsteptareCaptura). AddNotification doar pune fereastra in coada / o
				# deschide, nu asteapta dupa om.
				_arataCodPeTelevizor(r["cod"], r["ramas"], r["tip"], r["adresa"], r["id_cerere"])
			televizor = _stareTelevizor()
			if televizor == "meniu" and _fereastraCoduluiDeschisa():
				# InfoBar nu mai e in fata tocmai fiindca fereastra codului s-a deschis peste el (sau omul a cerut
				# codul din ecranul de setari): codul se vede deja (vazut in emulator: pagina spunea „după ce
				# închideți meniul” desi codul era pe ecran)
				televizor = "ok"
			if televizor == "standby":
				mesaj = _t("Receptorul este în standby. Pornește-l din telecomandă: codul apare pe televizor după "
					"pornire.")
			elif televizor == "meniu":
				mesaj = _t("Codul apare pe televizor după ce închizi meniul sau fereastra deschisă pe receptor (tasta "
					"Exit).")
			else:
				mesaj = _t("Codul este afișat pe televizor.")
			return _json(request, {"result": True, "stare": r["stare"], "ramas": r["ramas"], "mesaj": mesaj})

	class AsociereResource(resource.Resource):
		"""POST /asociere cu cod=<6 cifre>: la cod corect, cookie-ul sesiunii (un an) si fereastra
		"Browser conectat" pe televizor."""

		def __init__(self):
			resource.Resource.__init__(self)
			self.putChild(b"cod", CodAsociereResource())

		def render_POST(self, request):
			refuz = _poartaAsociere(request)
			if refuz is not None:
				return refuz
			cod = request.args.get(b"cod", [b""])[0].decode("utf-8", "replace")
			r = obtineAsociere().verificaCod(cod, _antet(request, b"user-agent") or "", _adresaClient(request) or "", tip=TIP_BROWSER)
			stare = r["stare"]
			if stare == "ok":
				_puneCookie(request, r["secret"], DURATA_SESIUNE_S)
				_jurnal("browser asociat: %s (%s)" % (r["browser"]["nume"], r["browser"]["adresa"]))
				_anuntaBrowserNou(r["browser"])  # direct, din acelasi motiv ca la _arataCodPeTelevizor
				return _json(request, {"result": True, "mesaj": _t("Conectat.")})
			if stare == "format":
				return _json(request, {"result": False, "stare": stare, "mesaj": _t("Codul are 6 cifre.")}, 400)
			if stare == "expirat":
				return _json(request, {"result": False, "stare": stare,
					"mesaj": _t("Codul a expirat sau a fost deja folosit. Apasă Afișează din nou codul pe televizor.")},
						410)
			if stare == "gresit":
				ramase = _t("o încercare") if r["ramas"] == 1 else _t("%d încercări") % r["ramas"]
				return _json(request, {"result": False, "stare": stare, "ramas": r["ramas"],
					"mesaj": _t("Cod greșit. Mai ai %s.") % ramase}, 403)
			request.setHeader(b"retry-after", str(r.get("ramas", 300)).encode("ascii"))
			return _json(request, {"result": False, "stare": "blocat", "ramas": r.get("ramas", 300),
				"mesaj": _t("Au fost prea multe coduri greșite. Încearcă din nou peste %s. %s") % (
					_durataText(r.get("ramas", 300)), _sfatDeblocare())}, 429)

	class JetonQrResource(resource.Resource):
		"""/t: telefonul care a scanat codul QR de pe televizor (asociere.py, cereJeton/verificaJeton).
		GET /t/<jeton> = pagina care trimite jetonul; POST /t cu j=<jeton> = asocierea: aceeasi poarta ca POST /asociere
		(reteaua locala si aceeasi origine; antetul Host e verificat pentru orice cerere in _CerereHds.process), apoi
		cookie-ul pe un an, ca dupa cod, si fereastra „Browser conectat” pe televizor (numai pentru o intrare noua).
		Raspunsul: JSON {result, destinatie}; din formularul fara JavaScript (fel=formular), 303 spre pagina."""
		isLeaf = True

		def render_GET(self, request):
			cale = request.postpath[0] if request.postpath else b""
			return _paginaJeton(request, cale.decode("ascii", "replace") if isinstance(cale, bytes) else str(cale))

		def render_POST(self, request):
			refuz = _poartaAsociere(request)
			if refuz is not None:
				return refuz
			jeton = request.args.get(b"j", [b""])[0].decode("ascii", "replace")
			formular = request.args.get(b"fel", [b""])[0] == b"formular"
			r = obtineAsociere().verificaJeton(jeton, _antet(request, b"user-agent") or "", _adresaClient(request) or "",
				secret_existent=_secretDinCookie(request))
			if r["stare"] != "ok":
				if formular:
					request.setResponseCode(303)
					request.setHeader(b"location", b"/")
					return b""
				return _json(request, {"result": False, "stare": "expirat",
					"mesaj": _t("Codul QR a expirat sau a fost deja folosit. Deschide din nou codul pe televizor și "
						"scanează-l.")}, 410)
			if r["secret"]:
				_puneCookie(request, r["secret"], DURATA_SESIUNE_S)
			if r["nou"]:
				_jurnal("browser asociat prin codul QR: %s (%s)" % (r["browser"].get("nume", ""), r["browser"].get("adresa", "")))
				_anuntaBrowserNou(r["browser"])
			if formular:
				request.setResponseCode(303)
				request.setHeader(b"location", r["destinatie"].encode("ascii"))
				return b""
			return _json(request, {"result": True, "destinatie": r["destinatie"]})

	class InterfataWebResource(HdsJsonResource):
		"""GET /api/interfata-web: codul in reteaua locala (ceruta sau nu) si daca browserul a intrat fara cod."""

		def render_GET(self, request):
			_secret, browser = _sesiuneDinCerere(request)
			return self._raspunde(request, stareInterfataWeb(browser=browser))

	class InterfataWebSeteazaResource(HdsJsonResource):
		"""POST /api/interfata-web-seteaza?cod_retea_locala=0|1. Poarta comuna (schimbaCeva): din browser cer POST,
		aceeasi origine si antetul CSRF. Cine intra fara cod poate doar sa porneasca codul (cand codul e cerut, numai
		un browser asociat sau jetonul ajung pana aici)."""
		schimbaCeva = True

		def render_POST(self, request):
			if set(request.args) & {b"aplicatii", b"aplicatii_afara", b"parola_aplicatii_noua"}:
				rezultat = seteazaAplicatii(request.args)
				return self._raspunde(request, rezultat, 200 if rezultat["result"] else 400)
			valoare = request.args.get(b"cod_retea_locala", [b""])[0]
			if isinstance(valoare, bytes):
				valoare = valoare.decode("ascii", "replace")
			rezultat = seteazaCodReteaLocala(valoare.strip())
			return self._raspunde(request, rezultat, 200 if rezultat["result"] else 400)

		def render_GET(self, request):
			return self.render_POST(request)

	class InterfataWebSecreteResource(HdsJsonResource):
		"""POST /api/interfata-web-secrete?ce=parola|cheie: parola pentru aplicatii sau cheia pentru scripturi, la
		butonul "Arată" (secreteInterfataWeb). Numai din browser: POST, aceeasi origine, antetul CSRF (schimbaCeva);
		cu ?token= se refuza (un script nu are nevoie sa citeasca parola sau cheia)."""
		schimbaCeva = True

		def render_POST(self, request):
			if PARAM_JETON in request.args:
				return self._raspunde(request, {"result": False,
					"message": _t("Parola și cheia se văd numai dintr-un browser.")}, 403)
			ce = request.args.get(b"ce", [b""])[0]
			if isinstance(ce, bytes):
				ce = ce.decode("ascii", "replace")
			rezultat = secreteInterfataWeb(ce.strip())
			if rezultat["result"]:
				_jurnal("%s aratata in web, la cerere, de la %s" % ("parola pentru aplicatii" if ce.strip() == "parola"
					else "cheia pentru scripturi", _adresaClient(request)))
			return self._raspunde(request, rezultat, 200 if rezultat["result"] else 400)

	class DeconectareResource(resource.Resource):
		"""POST /deconectare: scoate browserul curent (butonul din subsolul panoului) si sterge cookie-ul.
		Aceleasi conditii ca o comanda din panou: cookie, POST, aceeasi origine, antetul CSRF."""
		isLeaf = True

		def render_POST(self, request):
			if PARAM_JETON in request.args:
				return _json(request, {"result": False, "message": "doar pentru browserele conectate cu cod"}, 400)
			mod, eroare = _verificaAcces(request, schimba_ceva=True)
			if eroare is not None:
				return _json(request, {"result": False, "message": eroare[1]}, eroare[0])
			secret = _secretDinCookie(request)
			obtineAsociere().deconecteaza(secret)
			_puneCookie(request, "", 0)
			_jurnal("browser deconectat din panou, de la %s" % _adresaClient(request))
			return _json(request, {"result": True})

	# ---------------------------------------------------------------- fonturi Google
	# Perechea web a ecranului Screens/HdsFonturi.py: aceleasi date si aceleasi comenzi, peste
	# modulul Components/HdsFonturiGoogle.py. Lista si descarcarea cer internet, deci NU se fac pe
	# firul reactorului (ar ingheta televizorul): fir separat + dictionar simplu, rezultatul luat
	# inapoi pe firul enigma2 cu un eTimer (vezi _porneste si _AsteptareCaptura).

	_CEASURI_FONTURI = []       # eTimer-ele in curs; fara ele, GC-ul le-ar culege si raspunsul n-ar mai veni
	_LEGATURI_FONTURI = []      # variantele vechi de SWIG cer pastrarea obiectului de conexiune

	class _FonturiFirResource(HdsJsonResource):
		"""Baza pentru cererile de fonturi care ating internetul: raspunde de pe un fir separat."""

		TIMEOUT_S = 120

		def _lucru(self, request):
			raise NotImplementedError

		def _peFirulPrincipal(self, corp):
			"""Ce trebuie neaparat facut pe firul enigma2, nu pe firul de lucru. Implicit: nimic."""
			return corp

		def _porneste(self, request):
			# `eTimer` (ceasul enigma2, rulat de eMainloop la fiecare trecere), nu `reactor.callLater`:
			# un callLater recursiv putea lasa bucla de poll sa doarma pana la urmatorul eveniment pe un
			# descriptor Python (vezi _AsteptareCaptura), iar raspunsul nu mai venea.
			from enigma import eTimer
			rezultat_fir = {}
			pornit = [time.time()]

			def _fir():
				try:
					rezultat_fir["gata"] = self._lucru(request)
				except Exception as eroare:
					rezultat_fir["eroare"] = str(eroare)

			def _trimite(corp, cod=200):
				try:
					request.setResponseCode(cod)
					request.setHeader(b"content-type", b"application/json; charset=utf-8")
					request.setHeader(b"cache-control", b"no-store")
					request.write(json.dumps(corp, ensure_ascii=False).encode("utf-8"))
					request.finish()
				except Exception as eroare:
					_jurnal("fonturi: nu am putut trimite raspunsul (client plecat?): %s" % eroare)

			ceas = eTimer()
			_CEASURI_FONTURI.append(ceas)      # fara referinta pastrata, eTimer-ul e cules de GC si nu mai bate

			def _opreste():
				try:
					ceas.stop()
				except Exception:
					pass
				try:
					_CEASURI_FONTURI.remove(ceas)
				except ValueError:
					pass

			def _verificaGata():
				if "gata" in rezultat_fir:
					_opreste()
					corp = rezultat_fir["gata"]
					try:
						corp = self._peFirulPrincipal(corp)
					except Exception as eroare:
						_jurnal("fonturi: %s" % eroare)
					_trimite(corp)
				elif "eroare" in rezultat_fir:
					_opreste()
					_jurnal("fonturi: eroare in firul separat: %s" % rezultat_fir["eroare"])
					_trimite({"result": False, "message": "eroare interna la fonturi"}, 500)
				elif time.time() - pornit[0] > self.TIMEOUT_S:
					_opreste()
					_trimite({"result": False, "message": "a durat prea mult"}, 504)

			try:
				ceas.callback.append(_verificaGata)
			except AttributeError:
				_LEGATURI_FONTURI.append(ceas.timeout.connect(_verificaGata))

			threading.Thread(target=_fir, daemon=True).start()
			ceas.start(150, False)
			return NOT_DONE_YET

	class FonturiResource(_FonturiFirResource):
		"""GET /api/fonturi[?cauta=text][&reincarca=1]: familiile libere de pe Google Fonts si
		fonturile deja descarcate pe receptor. Numai citire."""

		def _lucru(self, request):
			from Components import HdsFonturiGoogle as fg
			cauta = request.args.get(b"cauta", [b""])[0].decode("utf-8", "replace")
			reincarca = bool(request.args.get(b"reincarca"))
			lista, eroare = fg.listaFamilii(reincarca)
			potrivite = fg.cauta(lista, cauta)
			descarcate = fg.fonturiDescarcate()
			aliasuri = set(f["alias"] for f in descarcate)
			return {
				"result": True,
				"message": eroare or "",
				"total": len(lista),
				"unde": fg.directorScriere(),
				"pe_mediu_extern": fg.peMediuExtern(),
				"spatiu_liber": fg.spatiuLiber(fg.directorScriere()),
				"prag_avertisment": fg.PRAG_AVERTISMENT,
				"prag_refuz": fg.PRAG_REFUZ,
				# modul sigur (mod_sigur_web.textFonturi): fonturile descarcate nu sunt incarcate acum
				"mod_sigur": mod_sigur_web.textFonturi(),
				"familii": [{
					"familie": f["familie"],
					"alias": fg.aliasFamilie(f["familie"]),
					"categorie": f["categorie"],
					"marime": f["marime"],
					"subseturi": f["subseturi"],
					"greutati": f["greutati"],
					"variabil": f["variabil"],
					"diacritice_probabile": "latin-ext" in f["subseturi"],
					"descarcat": fg.aliasFamilie(f["familie"]) in aliasuri,
				} for f in potrivite[:400]],
				"aratate": min(len(potrivite), 400),
				"gasite": len(potrivite),
				"descarcate": [{
					"alias": f["alias"],
					"familie": f["familie"],
					"cale": f["cale"],
					"octeti": f["octeti"],
					"bun": f["bun"],
					"motiv": f["motiv"],
					"diacritice": "".join(f["diacritice"]),
					"extern": f["extern"],
				} for f in descarcate],
			}

		def render_GET(self, request):
			return self._porneste(request)

	class FonturiDescarcaResource(_FonturiFirResource):
		"""POST /api/fonturi-descarca?familie=<Familia>[&mare=1]: descarca, verifica si inregistreaza.

		Schimba ceva pe receptor, deci cere POST + CSRF cand accesul e prin cookie (ca zap/remotecontrol).
		Fisierul NU ajunge la addFont daca nu trece verificatorul din modul -- addFont pe un fisier care
		nu e font opreste enigma2 (lib/gdi/font.cpp:133)."""
		schimbaCeva = True

		def _lucru(self, request):
			from Components import HdsFonturiGoogle as fg
			valori = request.args.get(b"familie")
			if not valori:
				return {"result": False, "message": "lipseste parametrul 'familie'"}
			familie = valori[0].decode("utf-8", "replace").strip()
			if not familie or len(familie) > 120:
				return {"result": False, "message": "nume de familie invalid"}
			mare = bool(request.args.get(b"mare"))
			lista, _eroare = fg.listaFamilii()
			gasita = None
			for f in lista:
				if f["familie"].lower() == familie.lower():
					gasita = f
					break
			if gasita is None:
				return {"result": False, "message": "familia „%s” nu e in lista Google Fonts" % familie}
			bun, mesaj, cale = fg.descarca(gasita["familie"], gasita["subseturi"], None, None, mare)
			return {
				"result": bool(bun),
				"message": mesaj,
				"familie": gasita["familie"],
				"alias": fg.aliasFamilie(gasita["familie"]),
				"cale": cale or "",
				# textul tradus, ca in ecranul Screens/HdsFonturi.py (cuvantul "Confirm" nu apare in toate limbile)
				"confirmare_ceruta": (not bun) and (_("Confirmă descărcarea mare") in mesaj),
			}

		def _peFirulPrincipal(self, corp):
			# `addFont` numai de pe firul enigma2: `getFaceID` (font.cpp:105) parcurge lista de
			# fonturi fara lacat, iar `AddFont` i-ar pune un element nou in cap.
			if corp.get("result") and corp.get("cale"):
				from Components import HdsFonturiGoogle as fg
				bun, mesaj = fg.inregistreazaUnFont(corp["cale"], corp.get("familie"))
				if not bun:
					corp["result"] = False
					corp["message"] = mesaj
			return corp

		def render_POST(self, request):
			return self._porneste(request)

		def render_GET(self, request):
			return self._porneste(request)

	class FonturiStergeResource(HdsJsonResource):
		"""POST /api/fonturi-sterge?alias=<NumeInSkin>: sterge un font descarcat. Nu atinge internetul,
		deci raspunde direct."""
		schimbaCeva = True

		def render_POST(self, request):
			return self.render_GET(request)

		def render_GET(self, request):
			from Components import HdsFonturiGoogle as fg
			valori = request.args.get(b"alias")
			if not valori:
				return self._eroare(request, "lipseste parametrul 'alias'")
			alias = valori[0].decode("utf-8", "replace").strip()
			if not alias or not alias.isalnum():
				return self._eroare(request, "alias invalid")
			bun, mesaj = fg.stergeFont(alias)
			return self._raspunde(request, {"result": bool(bun), "message": mesaj, "alias": alias})

	class FonturiPaginaResource(resource.Resource):
		"""GET /fonturi: pagina simpla peste API-ul de mai sus, aceeasi poarta ca panoul."""
		isLeaf = True

		def render_GET(self, request):
			if not _esteAdresaLocala(_adresaClient(request)):
				request.setResponseCode(403)
				request.setHeader(b"content-type", b"text/plain; charset=utf-8")
				return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
			_anteteHtml(request)
			if PARAM_JETON in request.args and _jetonValid(request):
				return _traducePagina(_PAGINA_FONTURI).replace("__CONFIG__", _configPanou("", _jetonConfigurat(),
					"")).encode("utf-8", "replace")
			secret, browser = _sesiuneDinCerere(request)
			if browser is not None:
				# pagina comanda descarcari si stergeri, deci primeste si tokenul CSRF al panoului
				return _traducePagina(_PAGINA_FONTURI).replace("__CONFIG__", _configPanou(csrfPentru(secret), "",
					browser.get("nume", ""))).encode("utf-8", "replace")
			return _traducePagina(_PAGINA_ASOCIERE).encode("utf-8")

	class ProgramatoriResource(resource.Resource):
		"""GET /programatori: lista API-ului si regulile de acces (fosta pagina "/")."""
		isLeaf = True

		def render_GET(self, request):
			if not _esteAdresaLocala(_adresaClient(request)):
				request.setResponseCode(403)
				request.setHeader(b"content-type", b"text/plain; charset=utf-8")
				return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
			_anteteHtml(request)
			return _paginaProgramatori().encode("utf-8")

	# ---------------------------------------------------------------- interfetele web ale cam-urilor
	# Vezi _interfeteCamPentruWeb. Cautarea deschide conexiuni locale
	# spre porturile cam-urilor si poate tine cateva secunde, deci NU se face pe firul enigma2: acelasi tipar ca la
	# fonturi (fir separat + eTimer; paznicul opreste enigma2 dupa 60 s fara raspuns la /api/statusinfo).
	class InterfeteCamResource(_FonturiFirResource):
		"""GET /api/interfete-cam[?reincarca=1]: cam-urile instalate si interfetele lor web, cu numele date de
		fiecare cam. Numai citire (`schimbaCeva` ramane False). Poarta: cea din HdsJsonResource.render (reteaua
		locala, apoi ?token= sau cookie-ul browserului asociat); antetul Host e verificat inainte, in
		_CerereHds.process. `reincarca` si portul nostru se citesc aici, pe firul reactorului: firul de lucru nu
		citeste nimic din cerere si nici din config."""

		TIMEOUT_S = 12  # modulul asteapta cautarea cel mult 10 s; dupa 12 s raspunsul e 504, nu o asteptare fara capat

		def _lucru(self, request):
			reincarca, port_web = request.hdsCautareCam
			return _interfeteCamPentruWeb(reincarca, port_web)

		def render_GET(self, request):
			reincarca = request.args.get(b"reincarca", [b""])[0] in (b"1", b"da", b"true")
			try:
				port_web = int(portFolosit())
			except Exception:
				port_web = None
			request.hdsCautareCam = (reincarca, port_web)
			return self._porneste(request)

	class InterfeteCamPaginaResource(resource.Resource):
		"""GET /interfete-cam: pagina „Interfețe CAM" (vezi _paginaInterfeteCam)."""
		isLeaf = True

		def render_GET(self, request):
			return _paginaInterfeteCam(request)

	# ---------------------------------------------------------------- scanarea si orientarea antenei
	# Aceleasi doua sectiuni ca la tasta MENU pe televizor („Scanare" si „Orientarea și setarea antenei"), cu
	# pornirea cautarii din browser si starea ei. Totul e in scanare_web.py; resursele lui primesc HdsJsonResource,
	# deci trec prin aceeasi poarta. Import intarziat, ca la twisted: fisierul se incarca abia aici.
	from . import scanare_web
	_SCANARE, _SCANARE_PAGINA = scanare_web.rute(HdsJsonResource, resource, NOT_DONE_YET)

	# ---------------------------------------------------------------- Configurare LNB, Găsire semnal, motorul
	# Aceleasi ecrane ca pe televizor, din aceleasi module (antena_web.py). /antena/lnb si /antena/semnal (adresele din
	# menu.xml) sunt paginile lor; restul lui /antena ramane pagina din scanare_web.py.
	from . import antena_web
	_ANTENA, _ANTENA_PAGINA = antena_web.rute(HdsJsonResource, resource, NOT_DONE_YET, _SCANARE_PAGINA)

	# ---------------------------------------------------------------- Sunet si subtitrari
	# Pistele audio si subtitrarile din afisajul detaliat, aceeasi alegere ca pe televizor (Components/HdsPisteLimbi.py).
	from . import piste
	_PISTE, _PISTE_PAGINA = piste.rute(HdsJsonResource, resource)

	# ---------------------------------------------------------------- Aspectul subtitrarilor
	# Aceleasi 17 setari ca ecranul de pe televizor (Screens/HdsSubtitrariAspect.py: cele 16 ale stilului literelor si
	# marirea subtitrarilor DVB), din acelasi modul (Components/HdsSubtitrariAspect.py); o subtitrare text de pe ecran
	# se reface pe loc.
	from . import subtitrari_web
	_SUBTITRARI, _SUBTITRARI_PAGINA = subtitrari_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Traducerea subtitrarilor (traducere_subtitrari_web.py)
	# Aceleasi setari, chei, proba si contor ca ecranul de pe televizor (Screens/HdsTraducereSubtitrari.py), din acelasi
	# modul (Components/HdsTraducereSubtitrari.py); cheile numai scrise si sterse, niciodata aratate.
	from . import traducere_subtitrari_web
	_TRADUCERE, _TRADUCERE_PAGINA = traducere_subtitrari_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Configurarea traducerii pas cu pas (traducere_configurare_web.py)
	# Pagina deschisa si de telefonul care scaneaza codul QR de pe televizor (/t/<jeton>): recunoasterea cheii, proba pe
	# loc, cautarea serverului din casa (Components/HdsConfigurareTraducere.py); cheia numai din corpul POST.
	from . import traducere_configurare_web
	_CONFIGURARE, _CONFIGURARE_PAGINA = traducere_configurare_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Traducerea paginilor HbbTV (traducere_hbbtv_web.py)
	# Calea locala a scriptului din paginile HbbTV ("Tradu HbbTV"), cu poarta ei: numai 127.0.0.1 (navigatorul
	# receptorului) si cheia pornirii aplicatiei de acum (Components/HdsHbbtvPornire.cheieTraducere).
	from . import traducere_hbbtv_web
	_TRADUCERE_HBBTV = traducere_hbbtv_web.rute(resource)
	# ---------------------------------------------------------------- Limbile recunoasterii textului (ocr_limbi_web.py)
	# Aceleasi limbi, stari si descarcari ca ecranul de pe televizor (Screens/HdsOcrLimbi.py, Components/HdsOcrModele.py).
	from . import ocr_limbi_web
	_OCR_LIMBI, _OCR_LIMBI_PAGINA = ocr_limbi_web.rute(HdsJsonResource, resource)

	# ---------------------------------------------------------------- Accelerare 2D pe placa video
	# Aceeasi setare ca pe televizor (Components/HdsAccel2D.py), starea reala de la pornire si repornirea interfetei.
	from . import accel_web
	_ACCEL, _ACCEL_PAGINA = accel_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- Mouse pe ecranul receptorului (mouse_web.py)
	# Clicul, rotita si trasul din caseta ecranului (captura, imaginea live, ecranul intreg); ce se face pe televizor e
	# in Components/HdsMouseEcran.py. Tastele pleaca prin _trimiteTasta, ca telecomanda din web.
	from . import mouse_web
	_MOUSE = mouse_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune, apasa=_trimiteTasta)

	# ---------------------------------------------------------------- Cautare canale
	# Aceleasi randuri de filtre ca pe televizor (Screens/HdsCautareCanale.py), cu pistele canalelor
	# (Components/HdsPisteCanale.py) si „Actualizeaza pistele”.
	from . import cautare_web
	_CAUTARE, _CAUTARE_PAGINA = cautare_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Caută setări
	# Perechea ecranului „Caută setări” de pe televizor (Screens/HdsCautaSetari.py): acelasi index
	# (Components/HdsCautaSetari.py), legaturile spre paginile web si „Deschide pe televizor” cu randul ales.
	from . import cauta_setari_web
	_CAUTA_SETARI, _CAUTA_SETARI_PAGINA = cauta_setari_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Ecranul de pornire, Ce e nou
	# (ecran_pornire_web.py, jurnal_web.py: aceleasi date ca ecranele de pe televizor)
	from . import ecran_pornire_web, jurnal_web
	_ECRANE, _ECRANE_PAGINA = ecran_pornire_web.rute(HdsJsonResource, resource)
	_JURNAL, _JURNAL_PAGINA = jurnal_web.rute(HdsJsonResource, resource)

	# ---------------------------------------------------------------- Data si ora, paznicul receptorului
	# Aceleasi setari si aceeasi stare ca ecranele „Data si ora” (Screens/Time.py, Components/HdsCeas.py) si „Paznicul
	# receptorului” (Screens/HdsPaznic.py, Components/HdsPaznic.py).
	from . import ceas_web
	from . import paznic_web
	_CEAS, _CEAS_PAGINA = ceas_web.rute(HdsJsonResource, resource)
	_PAZNIC, _PAZNIC_PAGINA = paznic_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Jurnalele celorlalte sloturi (sloturi_web.py)
	# Aceeasi cautare si acelasi buton ca ecranul de pe receptor (Screens/HdsJurnaleSloturi.py,
	# Components/HdsJurnaleSloturi.py): pasii pornirilor, rapoartele si caderile altor sloturi, pe stick si trimise.
	from . import sloturi_web
	_SLOTURI, _SLOTURI_PAGINA = sloturi_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Beta tester (betatester_web.py)
	# Acelasi acord si acelasi meniu al testerului ca ecranele de pe televizor (Screens/HdsBetaTester.py,
	# Components/HdsBetaTester.py).
	from . import betatester_web
	_BETA, _BETA_PAGINA = betatester_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Forumul receptorului (forum_web.py)
	# Acelasi forum al modelului ca ecranul de pe televizor (Screens/HdsForumReceptor.py), plus galeria capturilor
	# (Components/HdsForumReceptor.py, Components/HdsCapturi.py).
	from . import forum_web
	_FORUM, _FORUM_PAGINA = forum_web.rute(HdsJsonResource, resource)

	# ---------------------------------------------------------------- TV in browser (tv_web.py)
	# Pagina /tv si perechea ecranului "Transmisie in retea" (Screens/HdsTransmisie.py, Components/HdsTransmisie.py).
	# Fluxul /api/tv-flux il scrie firul sesiunii pe soclul cererii (NOT_DONE_YET).
	from . import tv_web
	_TV, _TV_PAGINA = tv_web.rute(HdsJsonResource, resource, NOT_DONE_YET)
	# fluxul pentru playerele externe (VLC, Kodi): /tv-extern/<cheie>/<canal>.ts, cu cheia playlistului (acces_extern.py)
	_TV_EXTERN = tv_web.ruteExterne(resource, NOT_DONE_YET)

	# ---------------------------------------------------------------- Procesor (modul de lucru si paza de caldura)
	# Acelasi mod si aceleasi citiri ca ecranul „Procesor” de pe televizor (Screens/HdsProcesor.py,
	# Components/HdsProcesor.py).
	from . import procesor_web
	_PROCESOR, _PROCESOR_PAGINA = procesor_web.rute(HdsJsonResource, resource)

	# ---------------------------------------------------------------- Afisajul din fata (4 cifre)
	# Aceleasi setari si acelasi text ca ecranul „Afișajul din față” (Screens/HdsAfisaj.py, Components/HdsAfisaj.py).
	from . import afisaj_web
	_AFISAJ, _AFISAJ_PAGINA = afisaj_web.rute(HdsJsonResource, resource)

	# ---------------------------------------------------------------- Setarile importate
	# Aceeasi stare ca descrierea ecranului „Import Canale si Setari” (Components/HdsSetariDinCopie.py): setarile care
	# asteapta repornirea interfetei, proba lor si garda de caderi; repornirea interfetei.
	from . import setari_copie_web
	_SETARI_COPIE, _SETARI_COPIE_PAGINA = setari_copie_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)

	# ---------------------------------------------------------------- Copia setarilor (copie_setari_web.py)
	# Perechea ecranului „Copia setărilor” (Screens/HdsCopieSetari.py, Components/HdsCopieSetari.py): copia pe stick sau
	# disc, copia automata, copiile gasite, punerea la loc (la repornirea interfetei, prin enigma2.sh) si stergerea.
	from . import copie_setari_web
	_COPIE_SETARI, _COPIE_SETARI_PAGINA = copie_setari_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)

	# ---------------------------------------------------------------- Modul sigur (mod_sigur_web.py)
	# Perechea mesajului modului sigur si a ecranului „Ce s-a întâmplat” (Screens/HdsModSigur.py): starea, alegerile
	# (numai in modul sigur, apoi repornirea interfetei, ca pe televizor) si textul brut al fisierelor.
	from . import mod_sigur_web
	_MOD_SIGUR, _MOD_SIGUR_PAGINA = mod_sigur_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)

	# ---------------------------------------------------------------- Import canale și setări, Liste implicite de canale
	# Aceleași surse, alegeri și import ca ecranul de pe televizor (Plugins/Extensions/HdsImportSetari,
	# Components/HdsImportSurse.py) și aceleași rânduri ca „Liste implicite de canale” (Screens/HdsListeImplicite.py).
	from . import scanare_import_web
	from . import scanare_liste_web
	_IMPORT, _IMPORT_PAGINA = scanare_import_web.rute(HdsJsonResource, resource)
	_LISTE_IMPLICITE, _LISTE_IMPLICITE_PAGINA = scanare_liste_web.rute(HdsJsonResource, resource)

	# ---------------------------------------------------------------- regula web pentru ce e deja pe receptor
	# Limba sunetului si a subtitrarilor (Components/HdsPisteLimbi.py), Telecomenzi (Components/HdsTelecomenziDate.py),
	# ecranele de setari din setup.xml (setari_web.py), tot meniul cu „Deschide pe televizor” (meniu_web.py) si
	# ecranele System Information (informatii_web.py).
	from . import limbi_web
	from . import telecomenzi_web
	from . import meniu_web
	from . import setari_web
	from . import informatii_web
	_LIMBI, _LIMBI_PAGINA = limbi_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- navigatorul web (navigator_web.py)
	from . import navigator_web
	_NAVIGATOR, _NAVIGATOR_PAGINA = navigator_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- DAB+ si DVB-T2 din satelit (dabt2_web.py)
	# Fereastra „Fluxuri și setări” (Hds/DabT2/ecrane.EcranPrincipal): fluxurile, actiunile, setarile, Despre.
	from . import dabt2_web
	_DABT2, _DABT2_PAGINA = dabt2_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- Parola receptorului (acces_ssh_web.py)
	# Aceeasi stare si aceleasi comenzi ca ecranul "Parola receptorului" al receptorului (Screens/HdsAccesSsh.py,
	# Components/HdsAccesSsh.py): parola lui root pentru FTP, SSH si SFTP, cheile SSH, "Fără parolă în rețeaua locală",
	# textul brut.
	from . import acces_ssh_web
	_ACCES_SSH, _ACCES_SSH_PAGINA = acces_ssh_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- paza de model (paza_model_web.py)
	# Perechea mesajului de pe televizor (Screens/HdsPazaModel.py): starea pazei si amprenta receptorului.
	from . import paza_model_web
	_PAZA_MODEL, _PAZA_MODEL_PAGINA = paza_model_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- actualizare software (actualizare_web.py)
	# Perechea ecranului de actualizare (Screens/HdsSoftwareUpdate.py): pachetele gasite si verdictul pazei de model,
	# numai citire; lista se face pe un fir separat, raspunsul pleaca dupa (NOT_DONE_YET).
	from . import actualizare_web
	_ACTUALIZARE, _ACTUALIZARE_PAGINA = actualizare_web.rute(HdsJsonResource, resource, NOT_DONE_YET)
	# ---------------------------------------------------------------- actualizari prin pachete (actualizari_web.py)
	# Perechea ecranului "Actualizare software" (Screens/HdsActualizari.py): starea, cautarea, instalarea si
	# repornirea pe calea sigura; aceeasi lucrare ca pe televizor (Components/HdsActualizari.py).
	from . import actualizari_web
	_ACTUALIZARI, _ACTUALIZARI_PAGINA = actualizari_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- egalizatorul (egalizator_web.py)
	# Perechea ecranului Meniu > Audio > Egalizator (Screens/HdsEgalizator.py, Components/HdsEgalizator.py).
	from . import egalizator_web
	_EGALIZATOR, _EGALIZATOR_PAGINA = egalizator_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- calitatea imaginii (calitate_imagine_web.py)
	# Perechea ecranului „Calitatea imaginii” (Screens/HdsCalitateImagine.py, Components/HdsCalitateImagine.py): profilurile,
	# reglajele blocului de calitate al placii, comparatia pe jumatate de ecran si iesirea HDR (cu intrebarea pe televizor).
	from . import calitate_imagine_web
	_CALITATE, _CALITATE_PAGINA = calitate_imagine_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- limba meniurilor (limba_interfata_web.py)
	# Perechea ecranului limbii de pe televizor (Screens/LanguageSelection.py): aceeasi lista si aceeasi schimbare.
	from . import limba_interfata_web
	_LIMBA_INTERFATA, _LIMBA_INTERFATA_PAGINA = limba_interfata_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- locul inregistrarilor (stocare_web.py)
	# Acelasi ecran ca pe televizor (Screens/HdsLocInregistrari.py, Components/HdsLocInregistrari.py): locul, discurile
	# si „Folosește pentru înregistrări”.
	from . import stocare_web
	_STOCARE, _STOCARE_PAGINA = stocare_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- locurile din retea (locuri_retea_web.py)
	# Perechea ecranelor Media > Locuri din retea (Screens/HdsLocuriRetea.py, Components/HdsStocareRetea.py): SMB, NFS,
	# FTP, WebDAV, DLNA; parolele nu se arata niciodata, filmul porneste pe televizor.
	from . import locuri_retea_web
	_LOCURI_RETEA, _LOCURI_RETEA_PAGINA = locuri_retea_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	_TELECOMENZI, _TELECOMENZI_PAGINA = telecomenzi_web.rute(HdsJsonResource, resource)
	_MENIU, _MENIU_PAGINA = meniu_web.rute(HdsJsonResource, resource)
	_SETARI, _SETARI_PAGINA = setari_web.rute(HdsJsonResource, resource, chei=meniu_web.cheiSetup)
	_INFORMATII, _INFORMATII_PAGINA = informatii_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Licente (licente_web.py)
	# Aceleasi randuri si texte ca ecranul „Licențe” de pe televizor (Screens/HdsLicente.py, Components/HdsLicente.py).
	from . import licente_web
	_LICENTE, _LICENTE_PAGINA = licente_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Ajutor (ajutor_web.py)
	# Aceleasi pagini ca ajutorul de pe televizor (Screens/HdsAjutor.py, Components/HdsAjutor.py, pachetul hdsatelit-ajutor).
	from . import ajutor_web
	_AJUTOR, _AJUTOR_PAGINA = ajutor_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- aspectul ecranului (aspect_web.py)
	# Perechile web ale ecranelor de aspect si de informatii (lista in aspect_web.MODULE); legate dupa celelalte
	# rute, deci o ruta cu acelasi nume o inlocuieste pe cea veche.
	from . import aspect_web
	_ASPECT_API, _ASPECT_PAGINI = aspect_web.rute(HdsJsonResource, resource)

	# ---------------------------------------------------------------- Video (video_web.py)
	# Aceleasi randuri ca Setari > Video (Screens/VideoSetup.py, Components/VideoOutput.py): rezolutia, frecventa,
	# culorile HDMI si „La schimbarea canalului”; un mod nou se incearca cu aceeasi intrebare pe televizor.
	from . import video_web
	_VIDEO, _VIDEO_PAGINA = video_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)

	# ---------------------------------------------------------------- Iesirea sunetului (sunet_web.py)
	# Aceleasi randuri ca in Setari A/V (Ieșirea sunetului, AC3 / DTS downmix, pista AC3) si ce se trimite acum
	# spre televizor si de ce (Components/HdsSunet.py).
	from . import sunet_web
	_SUNET, _SUNET_PAGINA = sunet_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- Volum si intarziere (volum_intarziere_web.py)
	# Perechea ecranului Meniu > Audio & Sound Tracks > Volum și întârziere (Components/HdsSetariSunet.py): pasul
	# volumului, volumul tinut minte pe canal, volumul egal, intarzierea pe HDMI, pe optic si pe pista.
	from . import volum_intarziere_web
	_VOLUM_INTARZIERE, _VOLUM_INTARZIERE_PAGINA = volum_intarziere_web.rute(HdsJsonResource, resource,
		sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- lista de canale (canale_web.py)
	# Alegerea si pornirea canalului pe televizor, cu buchetele, cautarea si filtrele de pe televizor.
	from . import canale_web
	_CANALE, _CANALE_PAGINA = canale_web.rute(HdsJsonResource, resource, NOT_DONE_YET)
	# ---------------------------------------------------------------- editorul de canale (editor_canale_web.py)
	# Perechea ecranelor Screens/HdsEditorCanale*.py: aceeasi sesiune, aceleasi operatii, aceeasi anulare si aceleasi
	# copii de siguranta (Components/HdsEditorCanale.py). Importul e pazit: un modul care nu se incarca nu strica restul.
	try:
		from . import editor_canale_web
		_EDITOR_CANALE, _EDITOR_CANALE_PAGINA = editor_canale_web.rute(HdsJsonResource, resource, NOT_DONE_YET)
	except Exception as eroare:
		print("[HdsWebControl] editorul de canale nu s-a incarcat: %r" % (eroare,))
		_EDITOR_CANALE, _EDITOR_CANALE_PAGINA = {}, None

	# ---------------------------------------------------------------- Inregistrari programate (temporizatoare_web.py)
	# Aceeasi lista, aceleasi texte si acelasi loc al inregistrarilor ca ecranul de pe televizor (Screens/TimerEdit.py,
	# Components/HdsInregistrariProgramate.py); punerea si scoaterea prin Components/HdsTemporizare.py.
	from . import temporizatoare_web
	_TEMPORIZATOARE, _TEMPORIZATOARE_PAGINA = temporizatoare_web.rute(HdsJsonResource, resource)

	# ---------------------------------------------------------------- tasta PORTAL, starea HbbTV (portal_web.py)
	# Aceeasi stare si acelasi mesaj ca pe televizor dupa tasta PORTAL (Components/HdsPortal.py); randul „HbbTV” din
	# panou („Acum pe receptor”).
	from . import portal_web
	_PORTAL = portal_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Subtitrarile filmului (subtitrari_film_web.py)
	# Perechea tastei SUB la un film din fisier: alegerea, intarzierea, codarea, fps-ul (Components/HdsSubtitrariFilm.py).
	from . import subtitrari_film_web
	_SUBTITRARI_FILM, _SUBTITRARI_FILM_PAGINA = subtitrari_film_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- Teletextul (teletext_web.py)
	# Perechea ecranului de pe tasta TEXT (Screens/HdsTeletext.py): aceeasi pagina, din acelasi modul comun
	# (Components/HdsTeletext.py) si din aceeasi memorie a nucleului (eHdsTeletext); copiile salvate, descarcarea
	# si setarile teletextului (Components/HdsTeletextCopie.py). Pagina descarcata se face pe felii (NOT_DONE_YET).
	from . import teletext_web
	_TELETEXT, _TELETEXT_PAGINA = teletext_web.rute(HdsJsonResource, resource, NOT_DONE_YET=NOT_DONE_YET)
	# ---------------------------------------------------------------- Filmul de acum (filme_web.py)
	# Perechea playerului de filme si a listei de filme: pozitia, pauza, salturile, derularea, setarile la pornirea,
	# oprirea si sfarsitul unui film, lista filmelor din dosar (citita pe un fir) si pornirea unui film.
	from . import filme_web
	_FILME, _FILME_PAGINA = filme_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune, NOT_DONE_YET=NOT_DONE_YET)
	# ---------------------------------------------------------------- Descarcarea subtitrarilor (descarcare_subtitrari_web.py)
	# Din 0.3.2 in imagine (Components/HdsSubtitrariInternet), nu mai e plugin separat: pagina si rutele exista mereu.
	# Importul ramane pazit: un modul care nu se incarca nu strica restul paginilor (si legatura din panou dispare).
	try:
		from . import descarcare_subtitrari_web as _descarcare_web
		_DESCARCARE, _DESCARCARE_PAGINA = _descarcare_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	except ImportError:
		_DESCARCARE, _DESCARCARE_PAGINA = {}, None
	_DESCARCARE_PUSA["pagina"] = _DESCARCARE_PAGINA is not None
	# ---------------------------------------------------------------- ecranul radio (radio_web.py)
	# Datele postului de radio, barele din sunetul lui si setarile ecranului radio (Screens/HdsEcranRadio.py).
	from . import radio_web
	_RADIO, _RADIO_PAGINA = radio_web.rute(HdsJsonResource, resource, sesiune=lambda: _sesiune)
	# ---------------------------------------------------------------- ghidul canalului (ghid_web.py)
	# Perechea primei pagini a celei de-a doua bare: emisiunile, descrierea, temporizatorul si inregistrarea.
	from . import ghid_web
	_GHID, _GHID_PAGINA = ghid_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- ecranul negru (ecran_negru_web.py)
	# Perechea mesajului de pe mijlocul ecranului: starea si fapta mesajului de acum.
	from . import ecran_negru_web
	_ECRAN_NEGRU = ecran_negru_web.rute(HdsJsonResource, resource)
	from . import acces_web
	_ACCES_CANAL = acces_web.rute(HdsJsonResource)
	# pictograma retelei din antetul paginilor: cablu sau Wi-Fi si internetul (stare_retea_web.py, aceeasi stare ca
	# pictograma din barele de pe televizor: Components/HdsStareRetea.py)
	from . import stare_retea_web
	_STARE_RETEA = stare_retea_web.rute(HdsJsonResource)
	# pasii decriptarii canalului de pe televizor (Components/HdsPasiDecriptare.py), pentru pagina TV si randul Acces
	from . import pasi_decriptare_web
	_PASI_DECRIPTARE = pasi_decriptare_web.rute(HdsJsonResource)
	# ---------------------------------------------------------------- standby si televizorul (standby_tv_web.py)
	# Starea iesirii HDMI in standby si a CEC (Components/HdsStandbyTv.py); setarile sunt in /setari?id=hds_standby_tv.
	from . import standby_tv_web
	_STANDBY_TV = standby_tv_web.rute(HdsJsonResource)
	# pagina tastelor televizorului prin CEC (tabelul si tastele panoului Mai multe taste)
	_TELECOMANDA_TV_PAGINA = standby_tv_web.pagina_resursa(resource)
	# ---------------------------------------------------------------- culegerea canal cu canal (culegere_canale_web.py)
	# Perechea ecranului „Scanare detaliată” (Screens/HdsCulegereTotala.py, Meniu > Scanare); logica intr-un singur
	# loc, Components/HdsCulegereTotala.py. Pagina are doua adrese: /scanare-detaliata si cea veche, /culegere-canale
	# (legaturile salvate merg mai departe).
	from . import culegere_canale_web
	_CULEGERE_CANALE, _CULEGERE_CANALE_PAGINA = culegere_canale_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- Acces condiționat (acces_conditionat_web.py)
	# Modulele de acces conditionat (alegerea, pornirea, oprirea, repornirea, pe Components/HdsModuleAcces.py), perechea
	# ecranelor CamSetup si CamInfo; interfetele web ale modulelor raman pe /interfete-cam.
	from . import acces_conditionat_web
	_ACCES, _ACCES_PAGINA = acces_conditionat_web.rute(HdsJsonResource, resource)
	# ---------------------------------------------------------------- aplicatiile de telefon (aplicatii_web.py)
	# Rutele aplicatiilor de telefon (/web/*, cele noi din /api, /picon, /file, /grab), numai cu setarea „Aplicații de
	# telefon” si cu bariera lor (din casa fara parola, afara de „Cere codul și în rețeaua locală”
	# pornit; din afara numai cu „Acces din afara casei” si parola pentru aplicatii); /api/statusinfo, /api/zap si /api/remotecontrol raspund in forma compatibila cererilor
	# cu Basic si celor fara ?token=, X-HDS-CSRF si cookie (aplicatii_web.esteCerereAplicatie), altfel ca pana acum.
	from . import aplicatii_web
	_APLICATII = aplicatii_web.rute(resource, NOT_DONE_YET, aplicatii_web.Legaturi(
		activ=aplicatiiPornite, afara=aplicatiiAfara, adresaClient=_adresaClient, antet=_antet,
		gazdaProprie=lambda request: gazdaPermisa(_antet(request, b"host"), _numeAcasa()), codAcasa=codInReteaLocala,
		areCookie=lambda request: _secretDinCookie(request) is not None,
		jetonValid=_jetonValid, jeton=_jetonConfigurat, trimiteTasta=_trimiteTasta, zap=zapReferinta,
		refuzSsh=acces_ssh_web.refuzEcranDeschis, captura=ScreenshotResource))

	# ---------------------------------------------------------------- cadrul paginilor (cadru_web.py)
	# Antetul, meniul pe grupe si temele se pun pe pagini in _CerereHds.render; aici numai /cadru, fonturile skinului.
	from . import cadru_web
	_CADRU = cadru_web.rute(resource)

	class ApiResource(resource.Resource):
		def __init__(self):
			resource.Resource.__init__(self)
			# aceleasi trei rute si pentru aplicatiile de telefon (fara cheia, antetul si cookie-ul panoului: forma
			# ceruta de aplicatii)
			self.putChild(b"statusinfo", _APLICATII["alege"](b"statusinfo", StatusInfoResource()))
			self.putChild(b"remotecontrol", _APLICATII["alege"](b"remotecontrol", RemoteControlResource()))
			self.putChild(b"mouse", _MOUSE[b"mouse"])
			self.putChild(b"zap", _APLICATII["alege"](b"zap", ZapResource()))
			self.putChild(b"screenshot", ScreenshotResource())
			self.putChild(b"jurnal", _JURNAL[b"jurnal"])
			self.putChild(b"motor", MotorResource())
			self.putChild(b"fonturi", FonturiResource())
			self.putChild(b"fonturi-descarca", FonturiDescarcaResource())
			self.putChild(b"fonturi-sterge", FonturiStergeResource())
			self.putChild(b"ecrane", _ECRANE[b"ecrane"])
			self.putChild(b"ecran-poza", _ECRANE[b"ecran-poza"])
			self.putChild(b"ecran-alege", _ECRANE[b"ecran-alege"])
			self.putChild(b"ecran-urca", _ECRANE[b"ecran-urca"])
			self.putChild(b"ecran-sterge", _ECRANE[b"ecran-sterge"])
			self.putChild(b"ecran-la-loc", _ECRANE[b"ecran-la-loc"])
			self.putChild(b"interfete-cam", InterfeteCamResource())
			# modulele de acces conditionat (acces_conditionat_web.py)
			for nume_ruta, resursa in _ACCES.items():
				self.putChild(nume_ruta, resursa)
			# codul de asociere si in reteaua locala (pagina /setari, caseta „Interfața web”)
			self.putChild(b"interfata-web", InterfataWebResource())
			self.putChild(b"interfata-web-seteaza", InterfataWebSeteazaResource())
			# parola pentru aplicatii si cheia pentru scripturi, numai la butonul "Arată"
			self.putChild(b"interfata-web-secrete", InterfataWebSecreteResource())
			# scanarea si antena (scanare_web.py)
			self.putChild(b"scanare", _SCANARE[b"scanare"])
			self.putChild(b"scanare-porneste", _SCANARE[b"scanare-porneste"])
			self.putChild(b"scanare-stare", _SCANARE[b"scanare-stare"])
			self.putChild(b"scanare-ultima", _SCANARE[b"scanare-ultima"])
			self.putChild(b"scanare-opreste", _SCANARE[b"scanare-opreste"])
			self.putChild(b"scanare-fluxuri", _SCANARE[b"scanare-fluxuri"])
			self.putChild(b"scanare-televizor", _SCANARE[b"scanare-televizor"])
			self.putChild(b"antena", _SCANARE[b"antena"])
			self.putChild(b"piste", _PISTE[b"piste"])
			self.putChild(b"pista-audio", _PISTE[b"pista-audio"])
			for nume in (b"ghid", b"ghid-emisiune", b"ghid-temporizator"):
				self.putChild(nume, _GHID[nume])
			for nume in (b"ecran-negru", b"ecran-negru-fapta", b"ecran-negru-flux"):
				self.putChild(nume, _ECRAN_NEGRU[nume])
			self.putChild(b"acces-canal", _ACCES_CANAL[b"acces-canal"])
			self.putChild(b"stare-retea", _STARE_RETEA[b"stare-retea"])
			self.putChild(b"pasi-decriptare", _PASI_DECRIPTARE[b"pasi-decriptare"])
			self.putChild(b"subtitrare", _PISTE[b"subtitrare"])
			self.putChild(b"canal-audio", _PISTE[b"canal-audio"])
			self.putChild(b"downmix", _PISTE[b"downmix"])
			# aspectul subtitrarilor text (subtitrari_web.py)
			self.putChild(b"subtitrari-aspect", _SUBTITRARI[b"subtitrari-aspect"])
			self.putChild(b"subtitrari-aspect-seteaza", _SUBTITRARI[b"subtitrari-aspect-seteaza"])
			self.putChild(b"subtitrari-aspect-implicite", _SUBTITRARI[b"subtitrari-aspect-implicite"])
			self.putChild(b"subtitrari-ocr", _SUBTITRARI[b"subtitrari-ocr"])
			self.putChild(b"subtitrari-ocr-zero", _SUBTITRARI[b"subtitrari-ocr-zero"])
			# traducerea subtitrarilor (traducere_subtitrari_web.py)
			self.putChild(b"traducere-subtitrari", _TRADUCERE[b"traducere-subtitrari"])
			self.putChild(b"traducere-subtitrari-seteaza", _TRADUCERE[b"traducere-subtitrari-seteaza"])
			self.putChild(b"traducere-subtitrari-cheie", _TRADUCERE[b"traducere-subtitrari-cheie"])
			self.putChild(b"traducere-subtitrari-proba", _TRADUCERE[b"traducere-subtitrari-proba"])
			self.putChild(b"traducere-subtitrari-zero", _TRADUCERE[b"traducere-subtitrari-zero"])
			# configurarea traducerii pas cu pas (traducere_configurare_web.py)
			self.putChild(b"traducere-configurare", _CONFIGURARE[b"traducere-configurare"])
			self.putChild(b"traducere-configurare-cheie", _CONFIGURARE[b"traducere-configurare-cheie"])
			self.putChild(b"traducere-configurare-server", _CONFIGURARE[b"traducere-configurare-server"])
			self.putChild(b"traducere-configurare-model", _CONFIGURARE[b"traducere-configurare-model"])
			self.putChild(b"traducere-configurare-cauta", _CONFIGURARE[b"traducere-configurare-cauta"])
			# traducerea textelor din paginile HbbTV (traducere_hbbtv_web.py)
			for nume_ruta, resursa in _TRADUCERE_HBBTV.items():
				self.putChild(nume_ruta, resursa)
			# accelerarea 2D pe placa video (accel_web.py)
			self.putChild(b"accel", _ACCEL[b"accel"])
			self.putChild(b"accel-seteaza", _ACCEL[b"accel-seteaza"])
			self.putChild(b"accel-reporneste", _ACCEL[b"accel-reporneste"])
			# cautarea de canale (cautare_web.py)
			self.putChild(b"cautare-canale", _CAUTARE[b"cautare-canale"])
			self.putChild(b"cautare-actualizeaza", _CAUTARE[b"cautare-actualizeaza"])
			self.putChild(b"cautare-actualizeaza-stare", _CAUTARE[b"cautare-actualizeaza-stare"])
			self.putChild(b"cautare-actualizeaza-opreste", _CAUTARE[b"cautare-actualizeaza-opreste"])
			self.putChild(b"cautare-actualizeaza-sari", _CAUTARE[b"cautare-actualizeaza-sari"])
			self.putChild(b"cautare-culegere", _CAUTARE[b"cautare-culegere"])
			self.putChild(b"istoric-semnal", _CAUTARE[b"istoric-semnal"])
			self.putChild(b"istoric-semnal-sterge", _CAUTARE[b"istoric-semnal-sterge"])
			# data si ora (ceas_web.py), paznicul receptorului (paznic_web.py)
			self.putChild(b"ceas", _CEAS[b"ceas"])
			self.putChild(b"ceas-seteaza", _CEAS[b"ceas-seteaza"])
			self.putChild(b"ceas-sincronizeaza", _CEAS[b"ceas-sincronizeaza"])
			# setarile video (video_web.py)
			for nume_ruta, resursa in _VIDEO.items():
				self.putChild(nume_ruta, resursa)
			# iesirea sunetului (sunet_web.py)
			for nume_ruta, resursa in _SUNET.items():
				self.putChild(nume_ruta, resursa)
			# volumul si intarzierea sunetului (volum_intarziere_web.py)
			for nume_ruta, resursa in _VOLUM_INTARZIERE.items():
				self.putChild(nume_ruta, resursa)
			self.putChild(b"paznic", _PAZNIC[b"paznic"])
			self.putChild(b"paznic-seteaza", _PAZNIC[b"paznic-seteaza"])
			# jurnalele celorlalte sloturi (sloturi_web.py): /api/jurnale-sloturi, -pune, -cauta
			for nume_ruta, resursa in _SLOTURI.items():
				self.putChild(nume_ruta, resursa)
			# beta tester (betatester_web.py)
			for nume_ruta, resursa in _BETA.items():
				self.putChild(nume_ruta, resursa)
			# forumul receptorului si capturile (forum_web.py)
			for nume_ruta, resursa in _FORUM.items():
				self.putChild(nume_ruta, resursa)
			# TV in browser (tv_web.py)
			for nume_ruta, resursa in _TV.items():
				self.putChild(nume_ruta, resursa)
			# modul procesorului (procesor_web.py)
			self.putChild(b"procesor", _PROCESOR[b"procesor"])
			self.putChild(b"procesor-seteaza", _PROCESOR[b"procesor-seteaza"])
			# afisajul din fata (afisaj_web.py)
			self.putChild(b"afisaj", _AFISAJ[b"afisaj"])
			self.putChild(b"afisaj-seteaza", _AFISAJ[b"afisaj-seteaza"])
			self.putChild(b"setari-din-copie", _SETARI_COPIE[b"setari-din-copie"])
			self.putChild(b"setari-din-copie-reporneste", _SETARI_COPIE[b"setari-din-copie-reporneste"])
			# copia setarilor (copie_setari_web.py): /api/copie-setari, -fa, -pune, -sterge, -automat, -anuleaza
			for nume_ruta, resursa in _COPIE_SETARI.items():
				self.putChild(nume_ruta, resursa)
			# modul sigur (mod_sigur_web.py): /api/mod-sigur, /api/mod-sigur-alege, /api/mod-sigur-brut
			for nume_ruta, resursa in _MOD_SIGUR.items():
				self.putChild(nume_ruta, resursa)
			# importul canalelor și listele implicite (scanare_import_web.py, scanare_liste_web.py)
			for nume_ruta, resursa in _IMPORT.items():
				self.putChild(nume_ruta, resursa)
			self.putChild(b"liste-implicite", _LISTE_IMPLICITE[b"liste-implicite"])
			# Configurare LNB, Găsire semnal si comenzile motorului (antena_web.py)
			self.putChild(b"lnb", _ANTENA[b"lnb"])
			self.putChild(b"lnb-plan", _ANTENA[b"lnb-plan"])
			self.putChild(b"lnb-aplica", _ANTENA[b"lnb-aplica"])
			self.putChild(b"lnb-raspuns", _ANTENA[b"lnb-raspuns"])
			self.putChild(b"lnb-stare", _ANTENA[b"lnb-stare"])
			self.putChild(b"gasire-semnal", _ANTENA[b"gasire-semnal"])
			self.putChild(b"gasire-semnal-transpondere", _ANTENA[b"gasire-semnal-transpondere"])
			self.putChild(b"gasire-semnal-stare", _ANTENA[b"gasire-semnal-stare"])
			self.putChild(b"gasire-semnal-porneste", _ANTENA[b"gasire-semnal-porneste"])
			self.putChild(b"gasire-semnal-reacordeaza", _ANTENA[b"gasire-semnal-reacordeaza"])
			self.putChild(b"gasire-semnal-opreste", _ANTENA[b"gasire-semnal-opreste"])
			self.putChild(b"motor-comenzi", _ANTENA[b"motor-comenzi"])
			self.putChild(b"motor-comanda", _ANTENA[b"motor-comanda"])
			# locul antenei pentru motorul USALS (antena_web.py; pagina e /antena/locul)
			self.putChild(b"locul", _ANTENA[b"locul"])
			self.putChild(b"locul-seteaza", _ANTENA[b"locul-seteaza"])
			# locul antenei dupa adresa de internet: pornirea cautarii (POST) si starea ei (GET)
			self.putChild(b"locul-internet", _ANTENA[b"locul-internet"])
			self.putChild(b"locul-internet-stare", _ANTENA[b"locul-internet-stare"])
			# limbile, telecomenzile, meniul, setarile din setup.xml, informatiile
			for rute_lot in (_LIMBI, _LIMBA_INTERFATA, _STOCARE, _LOCURI_RETEA, _TELECOMENZI, _MENIU, _SETARI, _INFORMATII, _CANALE, _EDITOR_CANALE, _TEMPORIZATOARE, _SUBTITRARI_FILM, _FILME, _DESCARCARE, _RADIO, _PAZA_MODEL, _ACTUALIZARE, _ACTUALIZARI, _LICENTE, _OCR_LIMBI, _EGALIZATOR, _ACCES_SSH, _DABT2, _STANDBY_TV, _CULEGERE_CANALE, _CAUTA_SETARI, _NAVIGATOR):
				for nume_ruta, resursa in rute_lot.items():
					self.putChild(nume_ruta, resursa)
			self.putChild(b"portal", _PORTAL[b"portal"])
			# calitatea imaginii (calitate_imagine_web.py): /api/calitate-imagine, -seteaza, -implicite, -hdr, -comparatie
			for nume_ruta, resursa in _CALITATE.items():
				self.putChild(nume_ruta, resursa)
			# teletextul (teletext_web.py): /api/teletext, -copii, -salveaza, -sterge, -reimprospateaza, -setari, -descarca
			for nume_ruta, resursa in _TELETEXT.items():
				self.putChild(nume_ruta, resursa)
			# rutele noi ale aplicatiilor de telefon (aplicatii_web.NUME_API_NOI; niciuna nu are numele uneia de mai sus)
			for nume_ruta, resursa in _APLICATII["api"].items():
				self.putChild(nume_ruta, resursa)
			for nume_ruta, resursa in _ASPECT_API.items():
				self.putChild(nume_ruta, resursa)
			# ajutorul (ajutor_web.py): /api/ajutor, /api/ajutor-pagina, /api/ajutor-cauta, /api/ajutor-ecran
			for nume_ruta, resursa in _AJUTOR.items():
				self.putChild(nume_ruta, resursa)

	class FaviconResource(resource.Resource):
		"""GET /favicon.ico: iconita paginilor (PNG), fara asociere (browserul o cere si pe pagina de asociere); poarta
		antetului Host ramane (_CerereHds.process)."""
		isLeaf = True
		_date = None

		def render_GET(self, request):
			if FaviconResource._date is None:
				import base64
				FaviconResource._date = base64.b64decode(_FAVICON_PNG_B64)
			request.setHeader(b"content-type", b"image/png")
			request.setHeader(b"cache-control", b"public, max-age=604800")
			return FaviconResource._date

	class HdsWebRoot(resource.Resource):
		"""Radacina site-ului. '/' (si '/panou') = panoul pentru un browser asociat, altfel pagina de
		asociere; '/asociere' si '/asociere/cod' = asocierea cu codul de pe televizor; '/deconectare';
		'/programatori' = lista API; '/jurnal' = jurnalul de versiuni; '/api/...' = resursele de mai sus. Streaming (Faza 2, viitor) se adauga
		aici mai tarziu cu putChild(), fara sa schimbe API-urile deja existente."""

		def __init__(self):
			resource.Resource.__init__(self)
			self.putChild(b"api", ApiResource())
			self.putChild(b"panou", DashboardResource())
			self.putChild(b"asociere", AsociereResource())
			# telefonul din codul QR de pe televizor (jetonul de unica folosinta, asociere.py)
			self.putChild(b"t", JetonQrResource())
			self.putChild(b"deconectare", DeconectareResource())
			self.putChild(b"programatori", ProgramatoriResource())
			self.putChild(b"jurnal", _JURNAL_PAGINA)
			self.putChild(b"motor", MotorPaginaResource())
			self.putChild(b"fonturi", FonturiPaginaResource())
			self.putChild(b"ecrane", _ECRANE_PAGINA)
			self.putChild(b"interfete-cam", InterfeteCamPaginaResource())
			self.putChild(b"acces-conditionat", _ACCES_PAGINA)
			# aceeasi pagina pentru amandoua sectiunile; restul adresei alege grupul si felul (/scanare/satelit/operator)
			self.putChild(b"scanare", _SCANARE_PAGINA)
			# /antena/lnb si /antena/semnal: paginile din antena_web.py; restul lui /antena ramane pagina de scanare
			self.putChild(b"antena", _ANTENA_PAGINA)
			self.putChild(b"piste", _PISTE_PAGINA)
			self.putChild(b"subtitrari", _SUBTITRARI_PAGINA)
			self.putChild(b"traducere-subtitrari", _TRADUCERE_PAGINA)
			self.putChild(b"traducere-configurare", _CONFIGURARE_PAGINA)
			self.putChild(b"ocr-limbi", _OCR_LIMBI_PAGINA)
			self.putChild(b"accel", _ACCEL_PAGINA)
			self.putChild(b"cautare", _CAUTARE_PAGINA)
			self.putChild(b"dabt2", _DABT2_PAGINA)
			self.putChild(b"ceas", _CEAS_PAGINA)
			self.putChild(b"video", _VIDEO_PAGINA)
			self.putChild(b"sunet", _SUNET_PAGINA)
			self.putChild(b"volum-intarziere", _VOLUM_INTARZIERE_PAGINA)
			self.putChild(b"paznic", _PAZNIC_PAGINA)
			self.putChild(b"jurnale-sloturi", _SLOTURI_PAGINA)
			self.putChild(b"beta-tester", _BETA_PAGINA)
			self.putChild(b"forum-receptor", _FORUM_PAGINA)
			self.putChild(b"tv", _TV_PAGINA)
			self.putChild(b"tv-extern", _TV_EXTERN)
			self.putChild(b"procesor", _PROCESOR_PAGINA)
			self.putChild(b"afisaj", _AFISAJ_PAGINA)
			self.putChild(b"setari-din-copie", _SETARI_COPIE_PAGINA)
			self.putChild(b"copie-setari", _COPIE_SETARI_PAGINA)
			self.putChild(b"mod-sigur", _MOD_SIGUR_PAGINA)
			self.putChild(b"import", _IMPORT_PAGINA)
			self.putChild(b"liste-implicite", _LISTE_IMPLICITE_PAGINA)
			self.putChild(b"limbi", _LIMBI_PAGINA)
			self.putChild(b"navigator", _NAVIGATOR_PAGINA)
			self.putChild(b"acces-ssh", _ACCES_SSH_PAGINA)
			self.putChild(b"egalizator", _EGALIZATOR_PAGINA)
			self.putChild(b"calitate-imagine", _CALITATE_PAGINA)
			self.putChild(b"favicon.ico", FaviconResource())
			# fonturile skinului pentru cadrul paginilor (cadru_web.py), fara poarta, ca iconita
			self.putChild(b"cadru", _CADRU)
			self.putChild(b"limba-interfata", _LIMBA_INTERFATA_PAGINA)
			self.putChild(b"stocare", _STOCARE_PAGINA)
			self.putChild(b"locuri-retea", _LOCURI_RETEA_PAGINA)
			self.putChild(b"telecomenzi", _TELECOMENZI_PAGINA)
			self.putChild(b"telecomanda-tv", _TELECOMANDA_TV_PAGINA)
			self.putChild(b"meniu", _MENIU_PAGINA)
			self.putChild(b"setari", _SETARI_PAGINA)
			self.putChild(b"cauta-setari", _CAUTA_SETARI_PAGINA)
			self.putChild(b"informatii", _INFORMATII_PAGINA)
			self.putChild(b"licente", _LICENTE_PAGINA)
			self.putChild(b"ajutor", _AJUTOR_PAGINA)
			self.putChild(b"canale", _CANALE_PAGINA)
			if _EDITOR_CANALE_PAGINA is not None:
				self.putChild(b"editor-canale", _EDITOR_CANALE_PAGINA)
			self.putChild(b"temporizatoare", _TEMPORIZATOARE_PAGINA)
			self.putChild(b"subtitrari-film", _SUBTITRARI_FILM_PAGINA)
			self.putChild(b"teletext", _TELETEXT_PAGINA)
			self.putChild(b"filme", _FILME_PAGINA)
			if _DESCARCARE_PAGINA is not None:
				self.putChild(b"descarcare-subtitrari", _DESCARCARE_PAGINA)
			self.putChild(b"radio", _RADIO_PAGINA)
			self.putChild(b"paza-model", _PAZA_MODEL_PAGINA)
			self.putChild(b"actualizare", _ACTUALIZARE_PAGINA)
			self.putChild(b"actualizari", _ACTUALIZARI_PAGINA)
			self.putChild(b"ghid", _GHID_PAGINA)
			self.putChild(b"scanare-detaliata", _CULEGERE_CANALE_PAGINA)
			self.putChild(b"culegere-canale", _CULEGERE_CANALE_PAGINA)   # adresa veche a aceleiasi pagini
			# aplicatiile de telefon (aplicatii_web.py): 404 cat setarea e oprita
			for nume_ruta in ("web", "picon", "file", "grab"):
				self.putChild(nume_ruta.encode("ascii"), _APLICATII[nume_ruta])
			for nume_ruta, resursa in _ASPECT_PAGINI.items():
				self.putChild(nume_ruta, resursa)

		def getChild(self, name, request):
			# Twisted cere un copil si pentru segmentul gol al lui "/" (path exact radacina);
			# fara aceasta suprascriere, "/" ar da 404 desi render_GET de mai jos exista.
			if name == b"":
				return self
			return resource.Resource.getChild(self, name, request)

		def render_GET(self, request):
			return _paginaPrincipala(request)
	return HdsWebRoot()


def _construiesteServer(radacina):
	"""Fabrica pentru reactor.listenTCP: Site-ul cu propriile Request si canal HTTP, invelit intr-o fabrica
	care numara conexiunile (vezi nota de la inceputul fisierului). Import
	intarziat, ca la _construiesteResurse. Merge pe Twisted 25.5 (imaginea) si 26.4 (emulatorul): doar API-uri
	vechi de ani de zile (Request.gotLength/handleContentChunk/requestReceived/process, HTTPChannel,
	TimeoutMixin, WrappingFactory)."""
	from twisted.protocols import policies
	from twisted.web import http, server

	class _CerereHds(server.Request):
		"""Twisted citea corpul intreg (in memorie sau intr-un fisier din /tmp, tot RAM pe receptor) si
		il parsa pe firul enigma2 INAINTE de orice ruta si de orice verificare. Aici corpul are cel mult
		MAX_CORP_CERERE octeti: un Content-Length mai mare primeste 413 si conexiunea se inchide inainte sa se
		citeasca ceva din corp; un corp fara lungime (chunked) se numara bucata cu bucata. Corpul sta mereu in
		memorie (e mic), niciodata in /tmp.
		Tot aici, in process(), poarta antetului Host, pentru orice cale."""
		_respinsa = False
		_primit = 0
		_limita = MAX_CORP_CERERE

		def _limitaCorpului(self):
			"""Cate octeti are voie sa aiba corpul ACESTEI cereri. 64 KB peste tot, afara de calea de
			urcare a unei poze de ecran de pornire (MAX_CORP_POZA). Calea se citeste din canal, fiindca
			aici cererea inca nu are metoda si calea puse in ea (gotLength vine INAINTE de
			requestReceived). Daca dintr-un motiv oarecare nu se poate citi calea, ramane limita mica:
			o greseala aici trebuie sa strice urcarea, nu sa deschida serverul."""
			try:
				cale = getattr(self.channel, "_path", None)
				if cale is None:
					return MAX_CORP_CERERE
				if not isinstance(cale, bytes):
					cale = str(cale).encode("latin-1", "replace")
				cale = cale.split(b"?", 1)[0]
				if len(cale) > 1 and cale.endswith(b"/"):
					cale = cale[:-1]
				if cale in (CALE_URCARE_POZA, CALE_URCARE_MEDIA) and corpMareMedia(self._areCookieDeSesiune(),
						self._adresaCanal(), _acelasiOriginCerere(self)):
					return MAX_CORP_POZA if cale == CALE_URCARE_POZA else MAX_CORP_MEDIA
				if cale in (CALE_EDITOR_OP, CALE_EDITOR_IMPORT) and corpMareMedia(self._areCookieDeSesiune(),
						self._adresaCanal(), _acelasiOriginCerere(self)):
					return MAX_CORP_EDITOR_IMPORT if cale == CALE_EDITOR_IMPORT else MAX_CORP_EDITOR_OP
				if cale == CALE_M3U and corpMareMedia(self._areCookieDeSesiune(), self._adresaCanal(),
						_acelasiOriginCerere(self)):
					return MAX_CORP_M3U
				if cale == CALE_URCARE_CAPTURA and corpMareMedia(self._areCookieDeSesiune(), self._adresaCanal(),
						_acelasiOriginCerere(self)):
					return MAX_CORP_CAPTURA
			except Exception as eroare:
				_jurnal("nu am putut citi calea cererii pentru limita corpului: %s" % eroare)
			return MAX_CORP_CERERE

		def _adresaCanal(self):
			"""Adresa IP a clientului, citita din conexiune: cand vine lungimea corpului, cererea inca nu are adresa
			pusa in ea (requestReceived vine dupa). None la orice indoiala (atunci ramane limita mica)."""
			for citeste in (lambda: self.channel.getPeer(), lambda: self.channel.transport.getPeer()):
				try:
					return citeste().host
				except Exception:
					pass
			return None

		def _areCookieDeSesiune(self):
			"""Cookie-ul nostru de sesiune EXISTA in cerere? (gasire de securitate)

			Limita mare de corp se da numai cererilor care macar par sa vina dintr-un browser asociat. Fara
			asta, oricine din retea putea trimite 8 MB pe calea de urcare si corpul se strangea in memoria lui
			enigma2 INAINTE de orice verificare de acces: 64 de conexiuni x 8 MB = 512 MB pe un receptor cu 822.
			Aici nu se verifica daca sesiunea e buna (aceea se face in render, unde se stie si adresa, si
			CSRF-ul): se cere doar sa existe cookie-ul, ceea ce taie trimiterile anonime. La orice indoiala
			ramane limita mica.
			"""
			try:
				antete = self.requestHeaders.getRawHeaders(b"cookie") or []
				cautat = (NUME_COOKIE + "=").encode("ascii")
				for antet in antete:
					if not isinstance(antet, bytes):
						antet = str(antet).encode("latin-1", "replace")
					for bucata in antet.split(b";"):
						if bucata.strip().startswith(cautat):
							return True
			except Exception as eroare:
				_jurnal("nu am putut citi cookie-ul pentru limita corpului: %s" % eroare)
			return False

		def gotLength(self, length):
			self.content = io.BytesIO()
			self._limita = self._limitaCorpului()
			if self._limita > MAX_CORP_CERERE:
				# o poza mare pe o retea fara fir slaba nu incape in 20 s; termenul se lungeste o data,
				# doar pentru aceasta conexiune si doar pe calea de urcare
				try:
					self.channel.setTimeout(TERMEN_URCARE_S)
				except Exception:
					pass
			if length is not None and length > self._limita:
				self._respingeCorpMare()

		def handleContentChunk(self, data):
			if self._respinsa:
				return
			self._primit += len(data)
			if self._primit > self._limita:
				self._respingeCorpMare()
				return
			self.content.write(data)

		def requestReceived(self, command, path, version):
			if self._respinsa:
				return  # raspunsul 413 a plecat deja, conexiunea se inchide
			server.Request.requestReceived(self, command, path, version)

		def _respingeCorpMare(self):
			if self._respinsa:
				return
			self._respinsa = True
			self.content = io.BytesIO()
			# fara "100 Continue" dupa refuz (curl il cere la corpurile mari, iar canalul il trimite dupa gotLength)
			self.requestHeaders.removeHeader(b"expect")
			canal = self.channel
			_jurnalRar("corp", "cerere respinsa: corp mai mare de %d octeti, de la %s" % (self._limita, _adresaClient(self)))
			corp = json.dumps({"result": False, "message": "cererea e prea mare"}).encode("utf-8")
			# scris direct pe conexiune: cererea nu e inca intreaga (metoda si calea nu sunt puse in Request)
			canal.transport.write(b"HTTP/1.1 413 Payload Too Large\r\n"
				b"Content-Type: application/json; charset=utf-8\r\n"
				b"Content-Length: " + str(len(corp)).encode("ascii") + b"\r\n"
				b"Connection: close\r\n\r\n" + corp)
			canal.loseConnection()

		def render(self, resrc):
			# cadrul comun al paginilor (cadru_web.imbracaRaspuns): numai pe o pagina HTML intreaga, pentru o cerere care
			# a trecut poarta; JSON, imaginile, NOT_DONE_YET, erorile si pagina de asociere trec neatinse
			server.Request.render(self, _CuCadru(resrc))

		def process(self):
			if _gazdaPermisaCerere(self):
				server.Request.process(self)
				return
			_jurnalRar("host", "cerere respinsa: Host %r nu e al receptorului, de la %s" % (
				(_antet(self, b"host") or "")[:80], _adresaClient(self)))
			try:
				self.site = self.channel.site
				self.setResponseCode(403)
				self.setHeader(b"content-type", b"text/plain; charset=utf-8")
				self.setHeader(b"cache-control", b"no-store")
				self.write(_mesajGazdaStraina().encode("utf-8"))
				self.finish()
			except Exception as eroare:
				# clientul poate fi plecat intre antete si raspuns; nu e eroare de server (regula: 0 avertismente)
				_jurnal("nu am putut trimite refuzul de Host (client plecat?): %s" % eroare)

	class _CuCadru(object):
		"""Resursa gasita pentru cerere, cu raspunsul trecut prin cadru_web.imbracaRaspuns. Twisted cheama numai
		render(); o eroare in cadru lasa pagina cum era (imbracaRaspuns nu arunca)."""

		def __init__(self, resursa):
			self.resursa = resursa

		def render(self, request):
			from . import cadru_web
			return cadru_web.imbracaRaspuns(request, self.resursa.render(request))

	class _CanalHttp(http.HTTPChannel):
		"""In Twisted, fiecare octet primit reia de la zero asteptarea de 60 s, deci un aparat care
		trimite cate un octet tine conexiunea deschisa oricat. Aici asteptarea (timeOut = TERMEN_CERERE_S) nu se
		mai reia: curge de la deschiderea conexiunii, sau de la sfarsitul raspunsului precedent, pana la cererea
		intreaga. Cat se pregateste raspunsul, Twisted o opreste singur (allContentReceived) si o reporneste
		dupa raspuns (requestDone)."""

		def resetTimeout(self):
			pass

	class _SiteHds(server.Site):
		protocol = _CanalHttp  # canalul HTTP/1.1 direct, fara stratul de negociere HTTP/2 (doar peste TLS)

	class _FabricaLimitata(policies.WrappingFactory):
		"""Cel mult MAX_CONEXIUNI deschise si MAX_CONEXIUNI_PE_ADRESA de la aceeasi adresa. O conexiune
		peste limita se inchide imediat (buildProtocol intoarce None), deci nu tine niciun descriptor."""

		def buildProtocol(self, addr):
			gazda = getattr(addr, "host", None)
			if len(self.protocols) >= MAX_CONEXIUNI:
				_jurnalRar("conexiuni", "conexiune refuzata de la %s: deja %d deschise" % (gazda, len(self.protocols)))
				return None
			de_la_ea = 0
			for p in self.protocols:
				try:
					if p.getPeer().host == gazda:
						de_la_ea += 1
				except Exception:
					pass
			if de_la_ea >= MAX_CONEXIUNI_PE_ADRESA:
				_jurnalRar("adresa", "conexiune refuzata de la %s: deja %d de la aceeasi adresa" % (gazda, de_la_ea))
				return None
			return policies.WrappingFactory.buildProtocol(self, addr)

	return _FabricaLimitata(_SiteHds(radacina, requestFactory=_CerereHds, timeout=TERMEN_CERERE_S))


def porneste(reason, session=None, **kwargs):
	global _server_pornit, _sesiune, _port_folosit
	if reason != 0:
		return  # 0 = pornire sesiune; alte valori (oprire) nu ne intereseaza aici
	if session is not None:
		_sesiune = session  # pentru scanare_web.py: ecranele se deschid pe televizor prin ea
	initConfigHdsWebControl()
	if not config.plugins.hdswebcontrol.activ.value:
		_jurnal("dezactivat din configurare, nu pornesc")
		# portul scris de o pornire de dinainte (enigma2 repornit fara repornirea receptorului) nu mai e adevarat
		try:
			os.remove(CALE_PORT_ACUM)
		except OSError:
			pass
		return
	if _server_pornit is not None:
		return  # deja pornit (WHERE_SESSIONSTART poate fi chemat mai mult de o data la unele imagini)
	try:
		from twisted.internet import reactor
		radacina = _construiesteResurse()
		port = config.plugins.hdswebcontrol.port.value
		try:
			_server_pornit = reactor.listenTCP(port, _construiesteServer(radacina))
		except Exception as eroare:
			if port != PORT_IMPLICIT:
				raise
			# portul 80 e tinut de alt program (de exemplu o interfata web instalata de om): interfata trece pe 8080
			_jurnal("portul %d e ocupat (%s), pornesc pe %d" % (port, eroare, PORT_REZERVA))
			port = PORT_REZERVA
			_server_pornit = reactor.listenTCP(port, _construiesteServer(radacina))
		_jurnal("pornit pe portul %d" % port)
		_port_folosit = port
		_scriePortulAcum(port)
		if port == PORT_IMPLICIT:
			_pornesteTrimitereaDin8080()
	except Exception as eroare:
		_jurnal("nu am putut porni: %s" % eroare)


def _scriePortulAcum(port):
	"""Portul pe care asculta interfata, pentru paznicul receptorului (/var/run e in RAM)."""
	try:
		with open(CALE_PORT_ACUM + ".nou", "w", encoding="ascii") as f:
			f.write("%d\n" % port)
		os.rename(CALE_PORT_ACUM + ".nou", CALE_PORT_ACUM)
	except (IOError, OSError) as eroare:
		_jurnal("nu am putut scrie %s: %s" % (CALE_PORT_ACUM, eroare))


def _adresaFaraPort(request):
	"""Adresa http://<gazda>/<cale> a cererii venite pe 8080, pe portul 80 (gazda din antetul Host, fara port)."""
	gazda = _antet(request, b"host") or ""
	gazda = gazda.strip()
	if gazda.startswith("["):
		gazda = gazda[:gazda.find("]") + 1] if "]" in gazda else ""
	else:
		gazda = gazda.split(":", 1)[0]
	if not gazda or any(c in gazda for c in "\r\n /\\@"):
		try:
			gazda = request.getHost().host
		except Exception:
			gazda = ""
	cale = request.uri if isinstance(request.uri, bytes) else str(request.uri).encode("latin-1", "replace")
	if not cale.startswith(b"/"):
		cale = b"/"
	return b"http://" + gazda.encode("ascii", "ignore") + cale


def _pornesteTrimitereaDin8080():
	"""Portul 8080 (adresa din 0.1.5 si din semnele de carte) trimite spre acelasi drum pe 80, cu 307 (metoda si
	corpul raman, deci si scripturile cu POST). Nu raspunde la nimic altceva; daca 8080 e ocupat, nu se intampla nimic."""
	global _server_8080
	if _server_8080 is not None:
		return
	try:
		from twisted.internet import reactor
		from twisted.web import resource

		class _Trimite(resource.Resource):
			isLeaf = True

			def render(self, request):
				request.setResponseCode(307)
				request.setHeader(b"location", _adresaFaraPort(request))
				request.setHeader(b"content-type", b"text/plain; charset=utf-8")
				request.setHeader(b"cache-control", b"no-store")
				return "Interfața web a receptorului e acum pe portul 80.\n".encode("utf-8")

		# aceeasi fabrica ca serverul interfetei: corpul cererii marginit (MAX_CORP_CERERE) si poarta antetului Host
		_server_8080 = reactor.listenTCP(PORT_REZERVA, _construiesteServer(_Trimite()))
		_jurnal("portul %d trimite spre %d" % (PORT_REZERVA, PORT_IMPLICIT))
	except Exception as eroare:
		_jurnal("portul %d nu trimite spre %d: %s" % (PORT_REZERVA, PORT_IMPLICIT, eroare))


def Plugins(**kwargs):
	return [PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, needsRestart=True, fnc=porneste)]


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Panou de control HD Satelit"),
		N_("Caută"),
		N_("Ecranul receptorului"),
		N_("Imaginea se actualizează la fiecare 3 secunde."),
		N_("Descarcă captura cu afișaj OSD"),
		N_("Descarcă captura fără afișaj OSD"),
		N_("<span aria-hidden=\"true\">&#9654;</span> Privește live aici"),
		N_("<span aria-hidden=\"true\">&#8595;</span> Descarcă playlist (M3U)"),
		N_("Cu meniul: exact ce vezi pe televizor. Fără meniu: numai imaginea canalului, fără ce desenează "
			"receptorul peste ea (meniuri, bara de informații, subtitrări)."),
		N_("Acum pe receptor"),
		N_("Canal"),
		N_("Semnal"),
		N_("Volum"),
		N_("Sonor oprit"),
		N_("Standby"),
		N_("HbbTV"),
		N_("Radio: vezi pagina radio (postul, piesa, barele)"),
		N_("Lista de canale: alege și pornește un canal"),
		N_("TV în browser: privește canalul live pe acest PC sau telefon"),
		N_("Ghidul canalului: emisiunile și înregistrarea lor"),
		N_("Deconectează acest browser"),
		N_("Caută setări: scrie un cuvânt, de exemplu subtitrări"),
		N_("Caută setări"),
		N_("Imaginea de pe ecranul receptorului"),
		N_("Canalul de acum de pe televizor, pentru VLC, Kodi sau alt player din casă"),
		N_("Conectare la receptor"),
		N_("Introdu codul afișat pe televizor."),
		N_("Conectează"),
		N_("Se cere codul..."),
		N_("Afișează din nou codul pe televizor"),
		N_("Codul apare pe televizor când receptorul arată un canal, nu în meniu și nu în standby. Este "
			"valabil o oră. După conectare, acest browser rămâne conectat un an."),
		N_("Codul de pe televizor"),
		N_("Pentru programatori"),
		N_("Receptorul are un API JSON simplu, folosit și de panoul de control."),
		N_("Adrese"),
		N_("<code>GET /api/statusinfo</code>: canalul curent, volumul, standby"),
		N_("<code>GET /api/portal</code>: starea HbbTV a canalului care rulează (da, nu are, încă nu se "
			"știe), cu mesajul arătat pe televizor la tasta PORTAL"),
		N_("<code>GET /api/remotecontrol?command=&lt;cod&gt;&amp;lung=1</code>: apasă o tastă ca de pe "
			"telecomanda receptorului (coduri de tastă Linux, de exemplu 352 pentru OK); cu "
			"<code>lung=1</code>, apăsare lungă"),
		N_("<code>GET /api/mouse?fel=clic|dublu|drag|dragend|rotita|dreapta|mijloc&amp;xp=&amp;yp=</code>: "
			"mouse-ul pe ecranul televizorului, ca în emulator: <code>xp</code>, <code>yp</code> = locul în "
			"procente din ecran (sau <code>x</code>, <code>y</code> în pixelii ecranului, 1920x1080); "
			"<code>clic</code> alege rândul de sub mouse, iar pe rândul ales sau cu <code>clicuri=2</code> "
			"dă OK; un buton colorat = tasta lui; <code>drag</code> (cu <code>x0p</code>, <code>y0p</code> = "
			"locul apăsării, <code>nou=1</code> la prima mișcare) și <code>dragend</code> = trasul pe bara "
			"de derulare; <code>rotita&amp;pasi=-12..12</code> = sus/jos (3 pași sau mai mulți = o pagină); "
			"<code>dreapta</code> = Meniu, <code>mijloc</code> = Ieșire. Răspunsul spune ce s-a făcut "
			"(<code>facut</code>: selectie, ok, buton, bara, derulare, tasta, nimic). Din browser, cu POST "
			"și antetul <code>X-HDS-CSRF</code>, ca <code>remotecontrol</code>"),
		N_("<code>GET /api/zap?sRef=&lt;referință&gt;</code>: schimbă canalul"),
		N_("<code>GET "
			"/api/screenshot?format=jpg|png&amp;quality=N&amp;width=N&amp;mode=all|video|osd&amp;download=1</code>: imaginea de pe ecran; <code>mode</code>: <code>all</code> cu afișajul OSD (implicit), <code>video</code> numai imaginea canalului, <code>osd</code> numai afișajul OSD; <code>download=1</code>: descărcare ca fișier, cu data și ora receptorului în nume"),
		N_("<code>GET /api/jurnal</code>: jurnalul de versiuni (ce s-a schimbat la fiecare actualizare)"),
		N_("<code>GET /api/motor</code>: starea rotirii antenei (de unde, pana unde, poziția estimată, cât "
			"mai are de mers)"),
		N_("<code>GET /api/fonturi?cauta=&lt;text&gt;</code>: familiile libere de pe Google Fonts și "
			"fonturile deja descărcate"),
		N_("<code>POST /api/fonturi-descarca?familie=&lt;Familia&gt;&amp;mare=1</code>: descarcă, verifică "
			"și înregistrează un font"),
		N_("<code>POST /api/fonturi-sterge?alias=&lt;NumeInSkin&gt;</code>: șterge un font descărcat"),
		N_("<code>GET /api/interfete-cam?reincarca=1</code>: modulele de acces condiționat instalate și "
			"interfețele lor web, cu numele date de fiecare modul (fără <code>reincarca</code> poate veni o "
			"căutare făcută cu câteva secunde înainte)"),
		N_("<code>GET /api/navigator</code>: navigatorul web de pe televizor (deschis sau nu, modul, "
			"desenul, felul câmpului ales, mărirea; fără adrese), setările lui și favoritele"),
		N_("<code>POST /api/navigator-deschide?adresa=&lt;adresă&gt;</code>, <code>POST "
			"/api/navigator-cam?port=&lt;port&gt;</code>, <code>POST /api/navigator-inchide</code>: "
			"navigatorul pe televizor"),
		N_("<code>POST /api/navigator-text</code>: text trimis în câmpul ales pe televizor; numai din "
			"browserul asociat, cu textul în corpul cererii (cu <code>?token=</code> se refuză)"),
		N_("<code>GET /api/acces-conditionat</code>: modulele de acces condiționat pe feluri (câmpul "
			"<code>fel</code>: numele felului, așa cum îl are receptorul; întâi modulele obișnuite, apoi "
			"serverele de carduri), cel ales la pornirea receptorului, cele care rulează, procesul care "
			"lucrează și memoria lui, comanda în curs sau ultimul rezultat, dacă receptorul decriptează acum"),
		N_("<code>POST "
			"/api/acces-conditionat-comanda?cerere=alege|porneste|opreste|reporneste&amp;fel=&lt;fel&gt;&amp;sufix=&lt;nume&gt;</code> (<code>fel</code> ca în <code>GET /api/acces-conditionat</code>): pornește comanda prin scriptul modulului, pe rând, una singură deodată (și cu televizorul); rezultatul vine prin <code>GET /api/acces-conditionat</code>"),
		N_("<code>GET /api/subtitrari-aspect</code>: aspectul subtitrărilor text (fontul, grosimea, mărimea "
			"și culoarea literelor, conturul, umbra, fundalul, înălțimea, distanța dintre rânduri) și "
			"mărirea subtitrărilor DVB, cu alegerile posibile (<code>alegeri</code>), stilurile gata făcute "
			"și valorile de la început"),
		N_("<code>POST "
			"/api/subtitrari-aspect-seteaza?stil_font=&lt;skin|ingust|tiresias_info|tiresias_pc|google:Alias&gt;&amp;grosime=&lt;automata|normala|ingrosata|foarte_ingrosata&gt;&amp;marime=&lt;60..200&gt;&amp;culoare=&lt;emisiune|%23rrggbb&gt;&amp;contur=&lt;fara|subtire|normal|gros|foarte_gros&gt;&amp;culoare_contur=&lt;%23rrggbb&gt;&amp;umbra=0|1&amp;culoare_umbra=&lt;%23rrggbb&gt;&amp;directie_umbra=&lt;sus|sus_dreapta|dreapta|jos_dreapta|jos|jos_stanga|stanga|sus_stanga&gt;&amp;distanta_umbra=&lt;50|100|150|200|300&gt;&amp;umbra_moale=&lt;tare|moale|foarte_moale&gt;&amp;fundal=&lt;niciunul|rand|cutie&gt;&amp;culoare_fundal=&lt;%23rrggbb&gt;&amp;opacitate_fundal=&lt;10..100&gt;&amp;jos=&lt;2..25&gt;&amp;spatiere=&lt;80|90|100|110|125|150&gt;&amp;marire_dvb=&lt;clara|ocr&gt;</code>: schimbă și salvează oricare dintre ele (valorile exacte sunt în <code>alegeri</code>; o valoare greșită nu schimbă nimic); sau <code>stil=&lt;cheie&gt;</code>, un stil gata făcut"),
		N_("<code>POST /api/subtitrari-aspect-implicite</code>: toate înapoi la valorile de la început"),
		N_("<code>GET /api/subtitrari-ocr</code>: contorul recunoașterii textului din subtitrările DVB "
			"(pagini citite ca text, rămase imagine și de ce, timpul mediu, ultimele pagini, viteza "
			"serviciului)"),
		N_("<code>POST /api/subtitrari-ocr-zero</code>: contorul recunoașterii textului pus la zero"),
		N_("<code>GET /api/traducere-subtitrari</code>: traducerea automată a subtitrărilor text: valorile "
			"(<code>pornit</code>, <code>serviciu</code>, <code>limba</code>, <code>afisare</code>, "
			"<code>tarziu</code>, <code>citire</code>, <code>dvb</code>, <code>bara</code>, "
			"<code>epg</code>, <code>regiune</code>, <code>adresa_libre</code>, <code>adresa_openai</code>, "
			"<code>model_gemini</code>, <code>model_openai</code>, <code>model_groq</code>, <code>model_cloudflare</code>, <code>cont_cloudflare</code> și, pentru adresa proprie, "
			"<code>propriu_adresa</code>, <code>propriu_metoda</code>, <code>propriu_corp</code>, "
			"<code>propriu_tip_corp</code>, <code>propriu_antet</code>, <code>propriu_raspuns</code>, "
			"<code>propriu_cale</code>), alegerile posibile (<code>alegeri</code>), ce cere fiecare serviciu "
			"(<code>cere</code>), care serviciu are cheie (<code>chei</code>, niciodată cheia), dacă cheile "
			"trebuie puse din nou (<code>chei_din_nou</code>, textul notei, gol când nu e cazul), starea "
			"cheii serviciului ales, ca pe televizor (<code>cheie_fel</code> și <code>cheie_text</code>: "
			"pusă, pusă pentru alt server, lipsă), textele paginii în limba receptorului "
			"(<code>texte</code>), ce lipsește, confidențialitatea, instrucțiunile pas cu pas (cu "
			"<code>pagina_cheie</code>, adresa oficială pentru codul QR) și starea (contorul, proba, pauza "
			"după erori)"),
		N_("<code>POST "
			"/api/traducere-subtitrari-seteaza?pornit=0|1&amp;serviciu=&lt;gemini|libre|openai|azure|deepl|groq|cloudflare|google|propriu&gt;&amp;limba=&lt;meniu|ro|en|de|...&gt;&amp;afisare=&lt;inlocuieste|sub&gt;&amp;tarziu=&lt;inlocuieste|sare&gt;&amp;citire=&lt;normal|lung|foarte_lung&gt;&amp;dvb=0|1&amp;bara=0|1&amp;epg=0|1&amp;regiune=..&amp;adresa_libre=..&amp;adresa_openai=..&amp;model_gemini=..&amp;model_openai=..&amp;model_groq=..&amp;model_cloudflare=..&amp;cont_cloudflare=..&amp;propriu_adresa=..&amp;propriu_metoda=GET|POST&amp;propriu_corp=..&amp;propriu_tip_corp=json|formular&amp;propriu_antet=..&amp;propriu_raspuns=json|text&amp;propriu_cale=..</code>: schimbă și salvează oricare dintre ele (valorile exacte sunt în <code>alegeri</code>); o valoare greșită refuză tot. Adresa proprie: adresa e un șablon cu <code>{text}</code>, <code>{sursa}</code>, <code>{tinta}</code> (http:// numai pentru un server din rețeaua de acasă); adresa receptorului însuși (127.0.0.1, localhost, IP-ul lui) e refuzată, și la <code>adresa_libre</code> și <code>adresa_openai</code>; calea în JSON are chei și numere despărțite prin punct, <code>*</code> = toate elementele"),
		N_("<code>POST /api/traducere-subtitrari-cheie</code>, corpul "
			"<code>serviciu=&lt;cod&gt;&amp;cheie=&lt;cheia&gt;</code>: pune cheia unui serviciu (goală = o "
			"șterge); la <code>serviciu=propriu</code> cheia este valoarea antetului adresei proprii (de "
			"exemplu <code>Bearer</code> și cheia); numai în corpul cererii, niciodată în adresă; răspunsul "
			"spune doar care serviciu are cheie"),
		N_("<code>POST /api/traducere-subtitrari-proba</code>: probează traducerea cu serviciul ales; "
			"rezultatul vine în <code>stare.proba</code> din <code>GET /api/traducere-subtitrari</code>"),
		N_("<code>POST /api/traducere-subtitrari-zero</code>: contorul traducerii pus la zero"),
		N_("<code>GET /api/traducere-configurare</code>: configurarea pas cu pas a traducerii: ce e pus "
			"acum (<code>acum</code>: serviciul, dacă are cheie, pornită sau nu, ultima probă, "
			"<code>chei_din_nou</code>), lucrarea configurării (<code>configurare</code>: starea, pasul, "
			"proba, modelul și modelele, mesajul și ce să faci), căutarea serverelor din casă "
			"(<code>cautare</code>: progresul și serverele găsite), instrucțiunile și pagina cheii fiecărui "
			"serviciu, regiunile Azure; niciodată o cheie"),
		N_("<code>POST /api/traducere-configurare-cheie</code>, corpul "
			"<code>cheie=&lt;cheia&gt;&amp;serviciu=&lt;auto|gemini|azure|deepl|groq|cloudflare|google&gt;&amp;regiune=..&amp;cont=..&amp;fara_proba=0|1</code>: probează cheia pe loc și, dacă merge, o salvează și pornește traducerea; numai în corpul cererii, niciodată în adresă; rezultatul vine în <code>configurare</code> din <code>GET /api/traducere-configurare</code>"),
		N_("<code>POST "
			"/api/traducere-configurare-server?serviciu=&lt;libre|openai&gt;&amp;adresa=..&amp;model=..</code>: folosește serverul din casă (adresa completată de receptor, modelul ales singur dacă lipsește) și îl probează"),
		N_("<code>POST /api/traducere-configurare-model?model=..</code>: alt model pentru serviciul ales "
			"acum, cu probă"),
		N_("<code>POST /api/traducere-configurare-cauta</code>: caută în rețeaua de acasă serverele Ollama "
			"(11434) și LibreTranslate (5000); rezultatul vine în <code>cautare</code>"),
		N_("<code>GET /api/ocr-limbi</code>: limbile recunoașterii textului (în imagine, descărcate, de "
			"descărcat, cu mărimea și starea fiecăreia) și locul pentru modelele noi"),
		N_("<code>POST /api/ocr-limbi-descarca?model=slk[&amp;intern=1]</code>: descarcă modelul unei limbi "
			"(pe stick sau disc; în memoria internă numai cu intern=1)"),
		N_("<code>POST /api/ocr-limbi-opreste?model=slk</code>: oprește descărcarea"),
		N_("<code>POST /api/ocr-limbi-sterge?model=slk</code>: șterge un model descărcat (sau îl scoate din "
			"listă când stickul lui nu e pus)"),
		N_("<code>POST /api/ocr-limbi-intreaba</code>: receptorul întreabă din nou pentru limbile cu \"Nu "
			"mai întreba\""),
		N_("<code>GET /api/accel</code>: accelerarea 2D pe placa video: dacă receptorul o are "
			"(<code>disponibila</code>), setarea pentru următoarea pornire (implicit pornită) și ce s-a "
			"hotărât la pornirea de acum"),
		N_("<code>POST /api/accel-seteaza?pornita=0|1</code>: pornește sau oprește accelerarea de la "
			"următoarea pornire a interfeței (refuzat pe un receptor fără accelerarea 2D)"),
		N_("<code>POST /api/accel-reporneste</code>: repornește interfața (enigma2)"),
		N_("<code>GET /api/ceas</code>: ora receptorului, fusul orar, sursa orei (<code>auto</code>: "
			"Internet, apoi transponder; <code>ntp</code>; <code>dvb</code>), serverul NTP, alegerile lor și "
			"ultima sincronizare"),
		N_("<code>POST /api/ceas-seteaza?sursa=auto|ntp|dvb&amp;server=&lt;server&gt;&amp;fus=&lt;fus "
			"orar&gt;</code>: schimbă și salvează oricare dintre ele (valorile exacte sunt în "
			"<code>/api/ceas</code>)"),
		N_("<code>POST /api/ceas-sincronizeaza</code>: o sincronizare a orei prin Internet, acum"),
		N_("<code>GET /api/video</code>: setările video ca în Setări &gt; Video: rezoluțiile, frecvențele "
			"fiecărei rezoluții (cu <code>auto</code> = automat după canal), culorile HDMI, "
			"<code>zapmode</code> (ce se vede la schimbarea canalului) și încercarea în curs"),
		N_("<code>POST "
			"/api/video-seteaza?rezolutie=&lt;2160p|1080p|...&gt;&amp;frecventa=&lt;mod|auto&gt;&amp;colorspace=..&amp;colordepth=..&amp;hdrtype=..&amp;zapmode=&lt;mute|hold|mutetilllock|holdtilllock&gt;&amp;culori_hdmi=&lt;ycbcr|rgb&gt;</code>: un mod nou se încearcă (aceeași întrebare pe televizor, 20 s, fără răspuns revine); zapmode se salvează direct; culori_hdmi=ycbcr se încearcă la fel (aceeași întrebare), rgb se salvează și se aplică după o repornire"),
		N_("<code>POST /api/video-confirma</code> și <code>POST /api/video-revino</code>: păstrează modul "
			"încercat sau revine la cel de dinainte"),
		N_("<code>POST /api/video-reporneste</code>: repornește receptorul (culorile „Ca la calculator” se "
			"aplică numai după o repornire); cu o înregistrare în curs, întrebarea apare pe televizor"),
		N_("<code>GET /api/sunet</code>: ieșirea sunetului (Automat / Manual), AC3 și DTS downmix, pista "
			"AC3, ce primește televizorul (EDID), ce se trimite acum și de ce, ce arată driverul pe HDMI și "
			"optic"),
		N_("<code>POST "
			"/api/sunet-seteaza?iesire=&lt;auto|manual&gt;&amp;ac3=&lt;da|nu&gt;&amp;dts=&lt;da|nu&gt;&amp;pista=&lt;da|nu&gt;</code>: oricare dintre ele, salvate; ac3 / dts sunt setările pentru Manual"),
		N_("<code>GET /api/paznic</code>: paznicul receptorului: starea, setările (<code>interfata</code>, "
			"<code>asteptare</code> în secunde), alegerile și ultimele rânduri din jurnalul lui"),
		N_("<code>POST /api/paznic-seteaza?interfata=0|1&amp;asteptare=60|120|300</code>: repornirea "
			"interfeței când nu mai răspunde și așteptarea dinaintea ei"),
		N_("<code>GET /api/tv-stare</code>: TV în browser: transmisiile de acum (canal, browser, de când, "
			"octeți), setările, memoria driverului video (câte canale noi se mai pot deschide până la "
			"repornire), transmisia acestui browser și motivul ultimei opriri"),
		N_("<code>GET /api/tv-canale?hevc=0|1&amp;ac3=0|1&amp;wasm=0|1</code>: canalele de pe frecvența "
			"televizorului și din lista lui, fiecare cu merge acum sau motivul, codecul imaginii și felul "
			"sunetului; cu <code>wasm=1</code> (browserul are playerul MPEG-2) merg și canalele cu imagine "
			"MPEG-2; <code>ac3=1</code>: pagina redă sunetul AC-3, cu decodorul browserului sau cu decodorul "
			"wasm al paginii"),
		N_("<code>POST /api/tv-porneste?ref=&lt;referință&gt;&amp;hevc=0|1&amp;ac3=0|1&amp;wasm=0|1</code>, "
			"<code>POST /api/tv-opreste?id=</code>, <code>POST "
			"/api/tv-seteaza?permis=0|1&amp;standby=0|1&amp;sesiuni_max=1|2&amp;asteptare=10|20|60</code>; "
			"<code>GET /api/tv-flux</code>: fluxul TS al transmisiei acestui browser. Pornirea și fluxul "
			"merg numai din browserul conectat, cu antetul <code>X-HDS-CSRF</code>, niciodată cu "
			"<code>?token=</code>"),
		N_("<code>GET /api/procesor</code>: procesorul: modul de lucru, modurile care există pe receptor, "
			"frecvența setată și cea de acum, temperatura, tensiunea, procentul folosit și timpul pe fiecare "
			"treaptă"),
		N_("<code>POST /api/procesor-seteaza?mod=automat|racoros|normal|performanta</code>: salvează modul "
			"și îl aplică pe loc"),
		N_("<code>GET /api/calitate-imagine</code>: calitatea imaginii: „Reglajele după canal”, profilul "
			"canalului de acum, cele 9 profiluri (SD, HD, 4K x SDR, HDR10, HLG) cu reglajele lor, ieșirea "
			"HDR (alegerile primite de televizor, ce e scris acum, întrebarea în curs) și textul brut al "
			"blocului de calitate"),
		N_("<code>POST "
			"/api/calitate-imagine-seteaza?profil=hd_sdr&amp;claritate=0..100&amp;...&amp;pornit=0|1[&amp;incearca=1|&amp;renunta=1]</code>: salvează reglajele unui profil (multipli de 5); cu <code>incearca=1</code> se văd pe loc fără să se salveze, <code>renunta=1</code> pune înapoi ce e salvat; <code>POST /api/calitate-imagine-implicite?profil=&lt;profil&gt;|toate</code>; <code>POST /api/calitate-imagine-hdr?iesire=auto|hdr10|hlg|none</code> (canalul pornește din nou, întrebarea apare pe televizor); <code>POST /api/calitate-imagine-comparatie?reglaj=&lt;cheie&gt;&amp;pornit=0|1</code> (jumătate de ecran, 60 s)"),
		N_("<code>GET /api/afisaj[?grupa=ceas|receptor|...][&amp;catalog=1][&amp;orase=1]</code>: afișajul "
			"din față: ce arată acum (măștile celor 4 cifre și textul), lista de rotire, mesajele scurte, "
			"așteptarea, setările, minutarul și cronometrul; cu <code>grupa</code> alegerile grupei cu "
			"desenul valorii de acum, cu <code>catalog=1</code> toate alegerile (căutarea), cu "
			"<code>orase=1</code> fusurile pentru ora din alt oraș"),
		N_("<code>POST "
			"/api/afisaj-seteaza?lista=ceas.ora:24@5,canal.nume:derulat&amp;evenimente=evenimente.volum:n&amp;asteptare=ora|ora_data|rec|stins&amp;viteza=200|300|450|600&amp;luminozitate=neschimbat|1..7&amp;luminozitate_noapte=la_fel|1..7&amp;noapte_de_la=18..23|0&amp;noapte_pana_la=5..9&amp;text=...&amp;oras=Asia/Tokyo</code>: salvează și aplică pe loc (oricare dintre ele); <code>previzualizare=1&amp;lista=...</code> arată lista pe afișaj fără salvare (cel mult 2 minute fără o cerere nouă), <code>previzualizare=0</code> revine; <code>minutar=0|1..120</code> și <code>cronometru=porneste|opreste|zero</code> pornesc ceasurile afișajului pe loc; <code>functionare=ora|canal|stins</code> merge ca înainte"),
		N_("<code>GET /api/acces-ssh</code>: parola receptorului (FTP, SSH și SFTP): felul parolei lui root "
			"(fără parola însăși), dacă merge FTP (<code>ftp</code>), cheile SSH (tipul, amprenta, comentariul), "
			"opțiunea Fără parolă în rețeaua locală, stările periculoase (<code>alarme</code>), lucrarea în curs "
			"și rezultatul ultimei comenzi"),
		N_("<code>POST /api/acces-ssh-parola</code>: textul parolei (se vede oricând); <code>GET "
			"/api/acces-ssh-brut?pagina=&lt;n&gt;</code>: fișierele serverelor SSH și FTP ca text (fără "
			"/etc/shadow)"),
		N_("<code>POST /api/acces-ssh-pune</code> (corp: <code>parola=</code>): parola aleasă (4-64 de semne: "
			"litere fără diacritice, cifre și semne, fără spații); <code>POST "
			"/api/acces-ssh-parola-noua?confirmat=1</code>: o parolă nouă la întâmplare"),
		N_("<code>POST /api/acces-ssh-adauga</code> (corp: <code>cheie=</code>), <code>POST "
			"/api/acces-ssh-stick</code>, <code>POST "
			"/api/acces-ssh-sterge?amprenta=SHA256:..&amp;confirmat=1</code>: cheile publice lipite, cele "
			"din dosarul hdsatelit/ssh de pe stick, ștergerea unei chei"),
		N_("<code>POST /api/acces-ssh-fara-parola?pornit=0|1</code> (<code>pornit=1</code> cere și "
			"<code>confirmat=1</code>): opțiunea Fără parolă în rețeaua locală. Parola, textul brut și toate "
			"schimbările merg numai dintr-un browser conectat cu codul de pe televizor (altfel 403 cu "
			"<code>trebuie_cod</code>), niciodată cu <code>?token=</code>; cât ecranul Parola receptorului e "
			"deschis pe receptor, la fel <code>/api/remotecontrol</code> și <code>/api/screenshot</code>"),
		N_("<code>GET /api/setari-din-copie</code>: setările importate: câte așteaptă repornirea interfeței "
			"(<code>asteapta</code>), proba lor (<code>garda</code>), scoase după opriri neașteptate "
			"(<code>cazut</code>), textele stării"),
		N_("<code>POST /api/setari-din-copie-reporneste</code>: repornește interfața, ca setările importate "
			"să se unească"),
		N_("<code>GET /api/copie-setari[?cauta=1]</code>: copia setărilor: stickurile și discurile "
			"(<code>implicit</code> = stickul de actualizare), copiile găsite (data, versiunea imaginii, "
			"acest receptor sau altul), copia automată, ultimul rezultat; niciodată conținutul copiei"),
		N_("<code>POST /api/copie-setari-fa?mediu=&lt;id&gt;</code>, <code>POST "
			"/api/copie-setari-pune?copie=&lt;id&gt;</code> (repornește interfața; copia se pune la loc "
			"înainte să pornească), <code>POST /api/copie-setari-sterge?copie=&lt;id&gt;</code>, <code>POST "
			"/api/copie-setari-automat?automat=oprita|zilnic&amp;pastrate=1-10</code>, <code>POST "
			"/api/copie-setari-anuleaza</code>"),
		N_("<code>GET "
			"/api/cautare-canale?text=&lt;nume&gt;&amp;tip=..&amp;rez=..&amp;acces=..&amp;sistem=..&amp;cod=..&amp;poz=..&amp;are=ttx,subdvb,subttx,hbbtv&amp;lsunet=&lt;limbă&gt;&amp;lsub=&lt;limbă&gt;</code>: căutarea de canale, cu aceleași rânduri de filtre ca pe televizor și pistele știute ale fiecărui canal"),
		N_("<code>POST /api/cautare-actualizeaza?fel=gasite|fara|toate</code>: întrebarea (durata, "
			"motorul); cu <code>confirmat=1</code> pornește pe televizor citirea pistelor, transponder cu "
			"transponder"),
		N_("<code>GET /api/cautare-actualizeaza-stare</code>: cât a citit (transponderul, canalele) sau "
			"rezultatul"),
		N_("<code>POST /api/cautare-actualizeaza-opreste</code>: oprește citirea și revine la canalul de "
			"dinainte"),
		N_("<code>POST /api/cautare-actualizeaza-sari</code>: sare peste satelitul pe care e antena acum și "
			"trece la următorul (tasta GALBEN de pe televizor)"),
		N_("<code>POST /api/cautare-culegere?mod=oprita|canal|transponder</code>: citirea pistelor în "
			"timpul vizionării (oprită, numai canalul privit, tot transponderul), aceeași setare ca pe "
			"televizor"),
		N_("<code>GET /api/scanare</code>: secțiunile „Scanare” și „Orientarea și setarea antenei”, cu "
			"felurile de scanare, în ordinea din meniul receptorului; cu "
			"<code>scaner=satelit|cablu|terestru&amp;fel=&lt;fel&gt;</code>, câmpurile felului și ce s-ar "
			"căuta"),
		N_("<code>POST /api/scanare-porneste?scaner=&lt;scaner&gt;&amp;fel=&lt;fel&gt;&amp;...</code>: "
			"pornește căutarea pe televizor (cu <code>confirmat=1</code> după o întrebare)"),
		N_("<code>GET /api/scanare-stare</code>: starea căutării (procent, canale găsite, transpondere, "
			"timp rămas, rezultat)"),
		N_("<code>GET /api/scanare-ultima</code>: rezultatul ultimei scanări de canale, ținut până la scanarea "
			"următoare: <code>inceput</code>, <code>sfarsit</code>, <code>stare</code> (in_curs, terminata, "
			"oprita), <code>fel</code>, <code>pozitii</code>, <code>doar_libere</code>, <code>eroare</code>, "
			"<code>transpondere</code> (<code>tp</code> ns:tsid:onid, <code>poz</code>, <code>f_khz</code>, "
			"<code>pol</code>, <code>sr</code>, <code>semnal</code>, iar când se știu <code>tsid</code>, "
			"<code>onid</code>, <code>nid</code> și, la cablu, <code>mod</code>), <code>servicii</code> "
			"(<code>cheie</code> sid:ns:tsid:onid, <code>tip</code>, <code>nume</code>, <code>furnizor</code>, "
			"<code>caid</code>, iar când operatorul trimite numerele canalelor <code>lcn</code> și "
			"<code>lcn_vizibil</code>): toate serviciile citite din SDT, vechi și noi, și <code>retele</code> "
			"(<code>nid</code>, <code>nume</code>, <code>pds</code>, <code>multiplexuri</code>, "
			"<code>lcn</code>, <code>privati</code>): rețelele din tabela NIT; câmpurile din tabela NIT "
			"(<code>nid</code>, <code>lcn</code>, <code>retele</code>) apar la căutarea în rețea și la scanarea "
			"pe cablu pe o singură frecvență; numai citire, lista de canale nu se schimbă; fără nicio scanare de "
			"la pornire, <code>result</code> false"),
		N_("<code>POST /api/scanare-opreste</code>: oprește căutarea sau închide rezultatul rămas pe "
			"televizor"),
		N_("<code>POST /api/scanare-fluxuri</code>: alegerea de la sfârșitul scanării DAB+ / DVB-T2 de pe "
			"televizor (<code>actiune=asculta&amp;post=N</code>, <code>inapoi</code>, <code>din_nou</code>, "
			"<code>porneste</code>)"),
		N_("<code>GET /api/dabt2?fel=dab|t2</code>: fereastra „Fluxuri și setări” a DAB+ / DVB-T2 din "
			"satelit: fluxurile cu poziția, numele, numărul de posturi și starea, setările, Despre, lucrul "
			"în curs și <code>repunere</code> (canalul de dinainte, pornit din nou după „Învață posturile”: "
			"starea și mesajul)"),
		N_("<code>POST "
			"/api/dabt2-actiune?fel=dab|t2&amp;actiune=actualizeaza|buchete|invata|sterge&amp;flux=..</code>: actualizează lista, reface buchetele, învață posturile unui flux, șterge un flux adăugat de mână"),
		N_("<code>POST /api/dabt2-seteaza?cheie=tasta|dosar|latime|nedecodabile&amp;valoare=..</code>: "
			"setările ferestrei, aceleași ca pe televizor"),
		N_("<code>POST "
			"/api/dabt2-manual?fel=dab|t2&amp;nume=..&amp;grade=..&amp;emisfera=E|V&amp;frecventa=..&amp;...</code>: un flux adăugat de mână, cu aceleași câmpuri și limite ca „Adaugă manual”"),
		N_("<code>POST /api/dabt2-televizor?fel=dab|t2</code>: deschide fereastra pe televizor"),
		N_("<code>POST /api/scanare-televizor?id=&lt;entryID&gt;</code>: deschide pe televizor ecranul unei "
			"intrări din cele două secțiuni"),
		N_("<code>GET /api/antena?lat=&lt;grade&gt;&amp;lon=&lt;grade&gt;</code>: tunerele, LNB-ul, "
			"semnalul canalului curent și unghiurile antenei spre fiecare satelit (numai citire)"),
		N_("<code>GET /api/lnb?slot=N</code>: LNB-urile tunerului, cu valorile, alegerile și „Probă de "
			"calcul” (numai citire)"),
		N_("<code>POST /api/lnb-plan</code>: ce s-ar schimba pentru câmpurile trimise "
			"(<code>l_&lt;lnb&gt;_&lt;câmp&gt;</code>), sau pentru „Ce era înainte” cu "
			"<code>fel=inainte</code>; nu scrie nimic"),
		N_("<code>POST /api/lnb-aplica</code>: aplică planul văzut (<code>semn=</code>), verifică semnalul "
			"și așteaptă răspunsul 60 de secunde"),
		N_("<code>POST /api/lnb-raspuns?raspuns=pastrez|revin</code>: răspunsul la „Păstrezi noile setări?”"),
		N_("<code>GET /api/lnb-stare</code>: verificarea semnalului, întrebarea și secundele rămase"),
		N_("<code>GET /api/gasire-semnal</code>: tunerele, sateliții, transponderul de la care pornește "
			"măsurarea și starea ei"),
		N_("<code>GET /api/gasire-semnal-transpondere?slot=N&amp;poz=P</code>: transponderele unui satelit"),
		N_("<code>GET /api/gasire-semnal-stare</code>: nivelul, calitatea, BER-ul și verdictul măsurării"),
		N_("<code>POST /api/gasire-semnal-porneste</code>, <code>-reacordeaza</code>, "
			"<code>-opreste</code>: pornește, acordează din nou sau oprește măsurarea"),
		N_("<code>GET /api/motor-comenzi</code>: tunerele cu motor, sateliții și starea comenzilor"),
		N_("<code>GET /api/motor-comenzi?urma=N</code>: urma comenzilor trimise motorului (ultimele N, "
			"implicit 100, cel mult 500, cele mai noi întâi): ora, comanda, unghiul, cine a cerut-o "
			"(televizorul, ecranul sau pagina motorului, Găsire semnal, reacordarea), poziția crezută de "
			"receptor; numai citire, din <code>/home/root/logs/hds-motor.log</code>"),
		N_("<code>POST /api/motor-comanda?actiune=&lt;comanda&gt;</code>: pas, mișcare fără oprire, poziții "
			"memorate, mergi la satelit, limite, oprire"),
		N_("<code>GET /api/locul[?tara=RO]</code>: locul antenei pentru motorul USALS, țările și orașele "
			"unei țări (tabelul din imagine)"),
		N_("<code>POST /api/locul-seteaza</code>: locul antenei din tabel (<code>tara</code>, "
			"<code>oras</code>) sau scris (<code>lat</code>, <code>lon</code>, grade, nord și est pozitive)"),
		N_("<code>POST /api/locul-internet</code>, <code>GET /api/locul-internet-stare</code>: locul "
			"antenei aflat după adresa de internet a receptorului, de serverul HD Satelit, numai la cerere "
			"și numai din browserul conectat; se scrie abia după confirmare, cu <code>POST "
			"/api/locul-seteaza</code> și <code>internet=&lt;semn&gt;</code>"),
		N_("<code>GET /api/limbi</code>: limba sunetului și a subtitrărilor: cele 7 setări cu alegerile "
			"lor, ce se ține minte pe canalul de acum și canalele cu alegeri de mână"),
		N_("<code>POST "
			"/api/limbi-seteaza?audio1=..&amp;audio2=..&amp;audio3=..&amp;fara_subtitrari=0|1&amp;sub1=..&amp;sub2=..&amp;sub3=..&amp;tradu_orice=0|1</code>: schimbă și salvează oricare dintre ele (valorile exacte sunt în <code>/api/limbi</code>; <code>tradu_orice</code> = „Tradu automat din orice subtitrare disponibilă”, contează cu traducerea subtitrărilor pornită) și le aplică pe canalul de acum"),
		N_("<code>POST /api/limbi-uita?cheie=&lt;cheia canalului&gt;</code>, <code>POST "
			"/api/limbi-uita-toate?confirmat=1</code>: uită alegerile de mână ale unui canal sau ale tuturor"),
		N_("<code>GET /api/limba-interfata</code>: limba meniurilor de acum și lista limbilor, cu numele de "
			"pe televizor"),
		N_("<code>POST /api/limba-interfata-seteaza?limba=ro_RO</code>: schimbă limba meniurilor și o "
			"salvează, ca OK în ecranul limbii de pe televizor"),
		N_("<code>GET /api/temporizatoare</code>: înregistrările programate (aceeași ordine, stare și "
			"detalii ca pe televizor), locul înregistrărilor și spațiul liber"),
		N_("<code>POST "
			"/api/temporizatoare-adauga?ref=&lt;canal&gt;&amp;zi=AAAA-LL-ZZ&amp;inceput=HH:MM&amp;sfarsit=HH:MM&amp;nume=..&amp;doar_comuta=0|1</code>: pune o înregistrare (sau doar schimbarea canalului); la suprapunere nu pune nimic și spune cu ce se suprapune"),
		N_("<code>POST /api/temporizatoare-sterge?id=..&amp;confirmat=1</code>, <code>POST "
			"/api/temporizatoare-opreste?id=..&amp;oprit=1|0</code>, <code>POST "
			"/api/temporizatoare-curata?confirmat=1</code>: șterge una, o oprește sau o pornește din nou, "
			"șterge cele terminate"),
		N_("<code>POST "
			"/api/temporizatoare-modifica?id=..&amp;zi=..&amp;inceput=..&amp;sfarsit=..&amp;repetare=o_data|zilnic|luni_vineri|zile&amp;zile=0,1,..&amp;dupa=nimic|asteptare|oprire|automat&amp;loc=..</code>: aceleași câmpuri ca fereastra de pe televizor, cu aceeași verificare a suprapunerii; <code>POST /api/temporizatoare-opreste?id=..&amp;alegere=stoponlycurrent|stopall|stoponlycoming</code>: una repetată care merge acum"),
		N_("<code>GET /api/temporizatoare-jurnal?id=..</code>, <code>POST "
			"/api/temporizatoare-jurnal-goleste?id=..&amp;confirmat=1</code>: jurnalul unei înregistrări, pe "
			"înțelesul oricui, cu mesajul tehnic; golirea lui"),
		N_("<code>GET /api/telecomenzi</code>: telecomenzile asociate, tastele lor și captura paginii "
			"(cititorul, proba, asocierea)"),
		N_("<code>POST /api/telecomenzi-captura?fel=cititor|proba|proba-noua|asociere|oprit</code>: "
			"pornește sau oprește captura paginii (cititorul și proba numai ascultă, cel mult 2 minute)"),
		N_("<code>POST "
			"/api/telecomenzi-asociere?pas=inapoi|sari|gata|continua|anuleaza|proba|inchide&amp;pastreaza=0|1</code>: pașii asocierii unei telecomenzi noi"),
		N_("<code>POST "
			"/api/telecomenzi-schimba?actiune=activa|neasociate|redenumeste|sterge-tasta|sterge|sterge-tot&amp;id=..&amp;cod=..&amp;nume=..&amp;confirmat=1</code>: aceleași schimbări ca în lista de pe televizor"),
		N_("<code>GET /api/telecomenzi-export?format=json|csv</code>: codurile telecomenzii receptorului și "
			"ale celor asociate, pentru aplicații"),
		N_("<code>GET /api/meniu</code>: tot meniul receptorului (tasta MENU), cu aceleași intrări ca pe "
			"televizor pentru nivelul ales"),
		N_("<code>POST /api/meniu-televizor?id=&lt;entryID&gt;</code>: deschide pe televizor ecranul unei "
			"intrări (nu oprirea sau repornirea)"),
		N_("<code>GET /api/setari</code>: ecranele de setări din meniu; cu <code>id=&lt;cheie&gt;</code>, "
			"rândurile lor (aceleași ca pe televizor, cu alegerile)"),
		N_("<code>GET /api/cauta-setari?q=&lt;text&gt;</code>: „Caută setări”: meniurile și setările care "
			"au textul în nume (fără diacritice), cu drumul din meniu, valoarea de acum și pagina web"),
		N_("<code>POST /api/cauta-setari-televizor?cheie=&lt;cheie&gt;</code>: deschide pe televizor un "
			"rezultat al căutării, cu rândul găsit ales"),
		N_("<code>POST /api/setari-seteaza?id=&lt;cheie&gt;&amp;r&lt;N&gt;=&lt;valoare&gt;</code>: schimbă "
			"și salvează rândurile trimise (o valoare greșită nu schimbă nimic; la o alegere multiplă, ca "
			"vitezele de derulare, alegerile despărțite prin virgulă, de pildă <code>r20=2,8,16</code>; gol "
			"= nicio alegere)"),
		N_("<code>GET /api/informatii?pagina=despre|receptor|tunere|memorie|stocare|retea|hdmi</code>: "
			"ecranele „System Information”, cu aceleași texte ca pe televizor"),
		N_("<code>GET /api/canale-buchete?fila=tv|radio</code>: listele de ales și lista pe care stă "
			"televizorul"),
		N_("<code>GET "
			"/api/canale-lista?fila=&amp;buchet=&amp;text=&amp;&lt;grupă&gt;=v1,v2&amp;de_la=&amp;cate=</code>: rândurile, pe pagini de cel mult 200, cu grupele de filtre și numerele lor"),
		N_("<code>GET /api/canale-epg?refs=r1,r2</code>: emisiunea de acum și cea următoare, cel mult 50 de "
			"canale"),
		N_("<code>GET /api/canale-acum</code>: canalul de pe televizor"),
		N_("<code>POST /api/canale-porneste?fila=&amp;buchet=&amp;ref=</code>: pornește canalul prin lista "
			"de pe televizor"),
		N_("<code>GET /api/canale-sigla?p=&lt;nume&gt;</code>: sigla canalului; la listele de canale, 503 "
			"când receptorul are prea multe cereri în lucru și 504 când nu termină în 10 s"),
		N_("<code>GET /api/stocare</code>: locul înregistrărilor, spațiul liber și discurile conectate"),
		N_("<code>POST /api/stocare-foloseste?punct=/media/usb</code>: folosește discul pentru înregistrări "
			"(face dosarul movie, fără formatare)"),
		N_("<code>GET /api/subtitrari-film</code>: filmul care merge, subtitrările lui, întârzierea, "
			"codarea și cadrele pe secundă"),
		N_("<code>POST /api/subtitrari-film-alege?id=&lt;id&gt;|oprit</code>, <code>POST "
			"/api/subtitrari-film-intarziere?ms=N</code> (sau <code>pas=</code>), <code>POST "
			"/api/subtitrari-film-codare?cod=..</code>, <code>POST /api/subtitrari-film-fps?fps=..</code>: "
			"aceleași alegeri ca tasta SUB la un film din fișier"),
		N_("<code>GET /api/teletext?pagina=N&amp;sub=S&amp;ascuns=0|1&amp;copie=&lt;ref&gt;</code>: o "
			"pagină de teletext, ca pe televizor la tasta TEXT: cele 25 de rânduri a câte 40 de celule "
			"(litera, culoarea, fundalul, mozaicul, atributele), textul paginii, subpaginile, paginile "
			"tastelor colorate, paginile vecine și pagina de pe televizor; fără <code>pagina</code>, pagina "
			"de pe televizor sau cea de pornire; <code>sub=-1</code> = cea mai nouă; <code>ascuns=1</code> "
			"arată ce e ascuns; cu <code>copie</code>, paginile din copia salvată a canalului, fără tuner "
			"(<code>sursa</code>: <code>direct</code> sau <code>copie</code>); <code>hd</code> = setarea "
			"Teletext neted, <code>optiuni</code> = conturul literelor, umbra literelor și formele în relief "
			"(<code>contur</code>, <code>umbra</code>, <code>relief</code>, ca pe televizor). Pagina lipsă: "
			"<code>gasita</code> fals și mesajul că se caută"),
		N_("<code>GET /api/teletext-copii</code> (cu <code>?canale=1</code> și canalele care au teletext): "
			"copiile de teletext salvate (canalul, data, paginile, mărimea), dosarul, spațiul folosit și cel "
			"ales, urmăritorul (caruselul canalului de acum, reîmprospătarea în lucru) și setările"),
		N_("<code>POST /api/teletext-salveaza</code>, <code>POST /api/teletext-sterge?ref=</code>, "
			"<code>POST /api/teletext-reimprospateaza?ref=</code> (receptorul trece pe canal, așteaptă o "
			"trecere completă a teletextului, face copia și se întoarce la canalul de dinainte; răspunde pe "
			"loc), <code>POST "
			"/api/teletext-setari?hd=0|1&amp;contur=0|1&amp;umbra=0|1&amp;relief=0|1&amp;copie_automata=0|1&amp;spatiu=5|10|20|50|100</code> (<code>hd</code> = Teletext neted): aceleași alegeri ca meniul teletextului de pe televizor"),
		N_("<code>GET /api/teletext-descarca?ref=&lt;ref&gt;&amp;fel=html|date</code> (fără "
			"<code>ref</code>: canalul de acum): <code>date</code> = fișierul copiei (.ttx, comprimat), "
			"<code>html</code> = o singură pagină HTML cu toate paginile, care se citește fără receptor"),
		N_("<code>GET /api/filme</code>: filmul care merge (poziția, lungimea, starea, locul ținut minte, "
			"mesajul de refuz) și setările filmelor; <code>GET /api/filme-lista</code>: filmele din dosarul "
			"listei de filme, cu locul rămas"),
		N_("<code>POST /api/filme-comanda?fa=pauza|redare|inainte|inapoi</code>, "
			"<code>?fa=salt&amp;secunde=-60</code>, <code>?fa=la&amp;secunde=N</code>, <code>POST "
			"/api/filme-seteaza?pornire=&amp;oprire=&amp;sfarsit=</code>, <code>POST "
			"/api/filme-porneste?cale=..&amp;de_la=loc|inceput</code>: aceleași comenzi ca pe telecomandă în "
			"player și în lista de filme"),
		N_("<code>GET /api/descarcare-subtitrari</code> și <code>POST "
			"/api/descarcare-subtitrari-cauta</code>, <code>-descarca</code>, <code>-aplica</code>, "
			"<code>-verifica</code>, <code>-conturi</code>: descărcarea subtitrărilor (numele, parolele și "
			"cheile numai în corpul cererii); pe un canal TV sau la o înregistrare și <code>-film</code> "
			"(<code>fapta=identifica|alege|titlu|local</code>: filmul din ghid, identificat în Wikidata) și "
			"<code>-potrivire</code> "
			"(<code>fapta=urmatoarea|dinainte|plus|minus|reclama|acum|viteza|opreste</code>: potrivirea "
			"subtitrării pe canal)"),
		N_("<code>GET /api/import-surse?cauta=1</code>: copiile de canale și setări găsite pe stick-uri și "
			"pe receptor, starea căutării și a importului"),
		N_("<code>POST "
			"/api/import?sursa=&lt;id&gt;&amp;canale=1&amp;tunere=1&amp;temporizatoare=0&amp;generale=0</code>: pornește importul (întâi copia de siguranță)"),
		N_("<code>POST /api/import-alta-imagine?raspuns=da|nu|ascunde</code>: răspunsul la întrebarea de la "
			"prima pornire (canalele și setările din altă imagine, găsite pe stick sau disc); starea în "
			"<code>/api/import-surse</code> (<code>alta_imagine</code>)"),
		N_("<code>GET /api/liste-implicite</code>: listele de canale gata făcute și drumurile spre scanare "
			"și import"),
		N_("<code>GET /api/radio</code>, <code>GET /api/radio-benzi</code>: postul de radio care merge, cu "
			"textele ecranului radio; barele și nivelul sunetului"),
		N_("<code>POST "
			"/api/radio-seteaza?ecran=0|1&amp;vizualizator=..&amp;culori=..&amp;bare=..&amp;cadre=..&amp;odihna=..&amp;epg=..&amp;bara_la_zap=0|1</code>: setările ecranului radio"),
		N_("<code>POST /api/radio-urmatoarea?ce=vizualizator|culori</code>: vizualizarea sau culorile "
			"următoare (ca tastele galbenă și albastră pe ecranul radio)"),
		N_("<code>GET /api/ghid?ref=&amp;de_la=&amp;cate=</code>, <code>GET "
			"/api/ghid-emisiune?ref=&amp;id=</code>: ghidul unui canal (fără <code>ref</code>, canalul de pe "
			"televizor) și o emisiune cu descrierile"),
		N_("<code>POST /api/ghid-temporizator?ref=&amp;id=&amp;fel=inregistrare|comutare|scoate</code>: "
			"pune sau scoate înregistrarea unei emisiuni (409 la suprapunere)"),
		N_("<code>GET /api/ecran-negru</code>, <code>GET /api/ecran-negru-flux</code>: mesajul de pe "
			"ecranul negru (de ce nu se vede imaginea) și analiza fluxului canalului"),
		N_("<code>POST /api/ecran-negru-fapta?fapta=&lt;id&gt;|ascunde</code>: fapta mesajului de acum, pe "
			"televizor, sau ascunderea lui"),
		N_("<code>GET /api/standby-tv</code>: ieșirea HDMI în standby (oprită sau pornită, oprirea din nou "
			"după aprinderea televizorului) și starea CEC"),
		N_("<code>GET /api/acces-canal</code>: accesul canalului care rulează (criptat sau liber), "
			"sistemele, CAID-urile și ce decriptează modulul acum"),
		N_("<code>GET /api/stare-retea</code>: legătura cu routerul și internetul (cablu sau Wi-Fi, "
			"treptele semnalului Wi-Fi, internetul merge, routerul nu are internet sau receptorul nu e "
			"conectat la router), cu desenul pictogramei și textul ei, ca pictograma din bara de pe televizor"),
		N_("<code>GET /api/pasi-decriptare</code>: pașii decriptării canalului de pe televizor (cererea "
			"către modulul de acces, răspunsurile și timpul lor, imaginea decriptată, mesajele modulului "
			"CI), numai cu setarea Arată pașii decriptării pornită"),
		N_("<code>POST /api/ecran-sterge?sursa=galerie|propriu&amp;id=..</code>, <code>POST "
			"/api/ecran-la-loc</code>: șterge un ecran de pornire din galerie (nu cel din fabrică și nici "
			"cel pus) sau pune la loc ecranele șterse"),
		N_("<code>GET /api/egalizator</code>: egalizatorul posturilor de radio: pornit sau oprit, benzile, "
			"presetarea, modul de noapte, reglajele postului de acum și dacă merge la acest post; <code>POST "
			"/api/egalizator-seteaza</code>: schimbă și aplică pe loc"),
		N_("<code>GET /api/licente</code>, <code>GET /api/licente-text?id=..</code>: programele din imagine "
			"cu licența fiecăruia și textul unei licențe"),
		N_("<code>GET /api/mod-sigur</code>, <code>POST /api/mod-sigur-alege</code>, <code>GET "
			"/api/mod-sigur-brut?pagina=&lt;n&gt;</code>: modul sigur (opririle interfeței, alegerile de "
			"după ele) și fișierele lui ca text"),
		N_("<code>GET /api/paza-model</code>: paza de model (receptorul pentru care e făcută imaginea și "
			"amprenta acestuia); <code>GET /api/actualizare-pachete</code>: pachetele de actualizare găsite "
			"și verdictul pazei pentru fiecare"),
		N_("<code>GET /api/actualizari</code>, <code>POST /api/actualizari-cauta</code>, <code>POST "
			"/api/actualizari-instaleaza?actualizare=&lt;n&gt;</code>, <code>POST "
			"/api/actualizari-zilnic?zilnic=0|1</code>, <code>POST /api/actualizari-reporneste</code>: "
			"actualizările prin pachete de pe stb.hdsatelit.com (starea, căutarea, instalarea, verificarea "
			"zilnică, repornirea interfeței după instalare)"),
		N_("Acces"),
		N_("Din scripturi: adaugă parametrul <code>token=&lt;cheie&gt;</code> la oricare adresă de mai sus "
			"(GET sau POST). Cheia pentru scripturi e ascunsă și se vede numai la cerere: pe receptor, în "
			"ecranul interfeței web (Albastru, Alte opțiuni, Arată parola și cheia), sau în pagina Interfața "
			"web (butonul Arată). Tot acolo se poate face o cheie nouă."),
		N_("Din browser: după conectarea cu codul de pe televizor, browserul primește un cookie. Cu el, "
			"comenzile care schimbă ceva (<code>remotecontrol</code>, <code>zap</code>) se trimit cu POST, "
			"dintr-o pagină a receptorului, cu antetul <code>X-HDS-CSRF</code> primit în panou."),
		N_("Comenzile care mișcă motorul, pornesc măsurarea semnalului sau schimbă LNB-ul "
			"(<code>lnb-aplica</code>, <code>lnb-raspuns</code>, <code>gasire-semnal-porneste</code>, "
			"<code>-reacordeaza</code>, <code>-opreste</code>, <code>motor-comanda</code>) se dau numai din "
			"paginile receptorului, cu browserul conectat: cu POST, cu antetul <code>X-HDS-CSRF</code>, fără "
			"cheia pentru scripturi."),
		N_("Adresele de mai sus răspund numai din rețeaua locală."),
		N_("Aplicații de telefon"),
		N_("Aplicațiile obișnuite pentru receptoarele Enigma2 (telecomandă, canale, ghid, înregistrări "
			"programate, liste m3u) folosesc adresele lor obișnuite: <code>/web/...</code> în XML (de "
			"exemplu <code>/web/deviceinfo</code>, <code>/web/getservices</code>, "
			"<code>/web/zap?sRef=</code>, <code>/web/epgnow?bRef=</code>, <code>/web/timerlist</code>), cele "
			"cu aceleași nume din <code>/api/...</code> în JSON, <code>/picon/</code>, "
			"<code>/file?file=</code> (siglele, iar pentru redarea pe telefon înregistrările și filmele din "
			"locurile înregistrărilor, cu <code>Range</code>), <code>/web/ts.m3u?file=</code> și "
			"<code>/grab</code>. Sunt pornite din fabrică (rândul „Aplicații de telefon” din ecranul "
			"interfeței web și din pagina Setări)."),
		N_("Din casă intră fără parolă, cu adresa IP a receptorului, cu numele lui (și cu terminațiile date "
			"de router: <code>.lan</code>, <code>.home</code>, <code>.localdomain</code>, "
			"<code>.home.arpa</code>, <code>.local</code>) sau cu <code>hdsatelit.local</code>; utilizatorul "
			"și parola din aplicație rămân goale. Cu alt nume în adresă, sau cu „Cere codul și în rețeaua "
			"locală” pornit, se cer utilizatorul <code>root</code> și parola pentru aplicații (HTTP Basic)."),
		N_("Din afara casei receptorul nu răspunde aplicațiilor până nu pornești „Acces din afara casei”; "
			"atunci intră numai cu utilizatorul <code>root</code> și parola pentru aplicații, pe care o vezi "
			"pe televizor, în ecranul interfeței web, și în pagina Setări. După 5 parole greșite de la "
			"aceeași adresă, receptorul nu-i mai răspunde 5 minute. Cererile venite din alte pagini web sunt "
			"refuzate, iar oprirea completă și repornirea nu se fac din aplicații."),
		N_("Receptorul HD Satelit"),
		N_("Se conectează telefonul la receptor..."),
		N_("Continuă"),
		N_("Deschide panoul receptorului"),
		N_("Fonturi Google"),
		N_("Se citește lista..."),
		N_("Fonturi descărcate pe receptor"),
		N_("Toate familiile libere"),
		N_("Numele fontului, de exemplu Roboto"),
		N_("Interfețele web ale modulelor"),
		N_("Paginile web ale modulelor de acces condiționat instalate pe receptor. Numele le spune fiecare "
			"modul, la căutare."),
		N_("Se caută..."),
		N_("Caută din nou"),
		N_("Module de acces condiționat"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Trimis:"),
		N_("(apăsare lungă)"),
		N_("Tasta nu a ajuns la receptor ("),
		N_("Imaginea ecranului nu este disponibilă acum."),
		N_("Playerul nu s-a încărcat de pe receptor."),
		N_("Imaginea live merge numai cu browserul conectat: deschide panoul fără cheia din adresă."),
		N_("Înapoi la captură"),
		N_("<span aria-hidden=\"true\">&#9632;</span> Oprește live (înapoi la captură)"),
		N_("Receptorul nu răspunde."),
		N_("<span aria-hidden=\"true\">&#9654;</span> Privește live aici"),
		N_("Playlistul se face numai cu browserul conectat: deschide panoul fără cheia din adresă."),
		N_("Receptorul nu spune ce canal e pe televizor."),
		N_("Playlistul s-a descărcat ("),
		N_("). Deschide-l în VLC sau în alt player din casă."),
		N_("Playlistul nu s-a putut descărca."),
		N_("Se pregătește captura..."),
		N_("Captura s-a descărcat."),
		N_("receptorul nu a răspuns"),
		N_("Captura nu s-a putut descărca ("),
		N_("prin internet"),
		N_("· are și DVB-I"),
		N_("Acest browser:"),
		N_("Deconectezi acest browser? Pentru a-l folosi din nou vei avea nevoie de un cod nou de pe "
			"televizor."),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Conectat. Se deschide panoul..."),
		N_("Codul nu a fost primit."),
		N_("Codul QR nu e bun. Deschide din nou codul pe televizor și scanează-l."),
		N_("Telefonul e conectat. Se deschide pagina..."),
		N_("Nu s-a putut conecta telefonul."),
		N_("Receptorul nu răspunde. Verifică dacă telefonul e în aceeași rețea cu receptorul."),
		N_("Se scriu în"),
		N_("(mediu extern, rezistă la actualizarea imaginii)"),
		N_("(memoria receptorului: o actualizare de imagine le șterge)"),
		N_("<p class=\"gol\">Niciun font descărcat încă.</p>"),
		N_("<table><tr><th>Familia</th><th>Nume in "
			"skin</th><th>Mărime</th><th>Diacritice</th><th>Verificare</th><th></th></tr>"),
		N_("în regulă"),
		N_("\">Șterge</button></td></tr>"),
		N_("<p class=\"gol\">Nimic găsit.</p>"),
		N_("<table><tr><th>Familia</th><th>Categorie</th><th>Diacritice</th><th>Familia "
			"întreagă</th><th></th></tr>"),
		N_("ăâîșț"),
		N_("probabil nu"),
		N_("<span class=\"mic\">descărcat</span>"),
		N_("\">Descarcă</button>"),
		N_("Arătate"),
		N_("din"),
		N_("găsite ("),
		N_("familii libere în total)."),
		N_("Lista nu s-a putut citi."),
		N_("Se descarcă „"),
		N_("Descarci totuși?"),
		N_("Descărcarea a eșuat."),
		N_("Ștergi fontul"),
		N_("? Un skin care îl folosește va rămâne fără el."),
		N_("Ștergerea a eșuat."),
		N_("Numele e titlul paginii lui."),
		N_("Numele e cel trimis de serverul lui."),
		N_("Numele e cel din cererea lui de parolă."),
		N_("Numele e cel din scriptul lui de pornire."),
		N_("Numele e cel din pachetul lui."),
		N_("Numele e cel al programului care rulează."),
		N_("Interfața web"),
		N_("portul"),
		N_("conexiune criptată"),
		N_("cere parolă"),
		N_("nu a răspuns la căutare"),
		N_("neverificată: căutarea s-a oprit înainte; apasă Caută din nou"),
		N_("ascultă doar pe receptor, deci nu se deschide din telefon sau calculator"),
		N_("Deschide"),
		N_("Modul fără nume"),
		N_("ales pe receptor"),
		N_("Pornit, dar nu are interfață web (sau nu răspunde acum)."),
		N_("Oprit. Se pornește din pagina Module de acces condiționat; după pornire, apasă Caută din nou."),
		N_("Un modul găsit."),
		N_("de"),
		N_("module găsite."),
		N_("Căutarea nu a mers."),
		N_("Nu e instalat niciun modul de acces condiționat pe receptor. După ce instalezi unul, apasă "
			"Caută din nou."),
		N_("Căutare terminată."),
		N_("Receptorul decriptează acum un canal."),
		N_("Se caută modulele de pe receptor..."),
		N_("căutarea a durat prea mult"),
		N_("Receptorul nu a răspuns ("),
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
