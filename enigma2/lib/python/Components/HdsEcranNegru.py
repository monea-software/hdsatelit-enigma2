# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEcranNegru.py: de ce e negru ecranul canalului de pe televizor. Un singur mecanism pentru toate cazurile, folosit
# de mesajul de pe mijlocul ecranului (Screens/HdsEcranNegru.py), de ferestrele de eroare ale redarii cand mesajul e
# oprit din setari (Screens/InfoBarGenerics.py, InfoBarServiceErrorPopupSupport) si de interfata web
# (Plugins/Extensions/HdsWebControl/ecran_negru_web.py).
#
# Trei parti:
# - analizeaza(d): verdictul dintr-o fotografie a starii (un dictionar simplu), fara nimic din enigma2, deci se
#   verifica pe PC. Ordinea: nimic pornit (canal blocat cu codul pentru parinti), eroarea acordarii (tuner ocupat,
#   tuner nesetat), motorul antenei, frecventa fara PAT / SID lipsa din PAT / PMT lipsa, fara semnal (cu nivelul si
#   calitatea), formatul de imagine numit (PMT-ul are numai o pista video pe care decodorul nu o cunoaste, de exemplu
#   AV1, H.266 VVC, AVS2, AVS3: imediat, fara asteptare, cu numele din nucleu, iServiceInformation.sPisteNecunoscute),
#   apoi, numai dupa PRAG_IMAGINE secunde fara imagine: format de imagine necunoscut (PMT fara pista video),
#   serviciu de date, canal criptat nedecriptat, canal liber fara imagine. Radioul nu are mesaj (ecranul lui e fundalul
#   postului). O pauza (timeshift) sau PiP opresc orice verdict. Fluxurile IP din liste (IPTV prin servicedvb) primesc
#   numai formatul numit (FEL_FLUX), fara fapta analizei.
# - Urmaritor: culege fotografia din serviciul redat, pe firul enigma2, o data pe secunda cat se asteapta imaginea sau
#   se vede un mesaj si o data la doua secunde cat imaginea vine; fara disc si fara retea. „Imaginea vine” se afla:
#   pe HiSilicon din contorul de cadre al decodorului (/proc/hisi/msp/vdecNN, „VFMW->VPSS AcquireFrame” OK: creste cat
#   iese imagine din decodor, sta pe loc cand pachetele sunt criptate sau nu vin), altfel din evVideoSizeChanged venit
#   dupa evStart sau din inaltimea video (nesigure pe unele drivere, deci numai in partea care nu arata mesajul).
#   Un contor care scade (decodor refacut) nu se socoteste imagine.
#   Din 0.7.7, pe celelalte placi (Vu+ si restul Broadcom) contorul se face din PTS-ul video al decodorului (CadreDinPts,
#   lib/service/servicedvb.cpp getInfo(sUser+40)): fiecare citire cu PTS diferit de cea dinainte e un cadru nou. Pe Vu+
#   evenimentul video vine numai cand se schimba marimea imaginii, iar cu „Ultima imagine” inaltimea ramane a canalului de
#   dinainte, deci un canal acordat fara imagine (criptat fara modul) parea cu imagine: niciun mesaj, iar cadrul vechi
#   ramanea pe ecran oricat (asistenta 888733, Vu+ Duo 4K SE; mesajul de tester 18 „imaginea ingheata la schimbarea
#   canalului”). Contorul din PTS se foloseste numai dupa ce PTS-ul s-a vazut miscandu-se pe acel receptor in pornirea de
#   acum (_PTS["dovedit"]); pana atunci, si pe un enigma2 fara cheie, ramane felul de dinainte.
# - fondul negru (0.7.7): cu „La schimbarea canalului” = „Ultima imagine” (din fabrica) driverul tine cadrul canalului de
#   dinainte pana vine primul cadru al celui nou, deci pe un canal care nu da imagine ramanea fara limita. Cand masura e
#   sigura (contorul de mai sus, nu evenimentul sau inaltimea) si de la schimbare au trecut PRAG_FOND secunde fara niciun
#   cadru nou pe un canal TV prin DVB (nu radio, pauza, PiP, fisier, flux IP, standby), urmaritorul spune „negru”
#   (stareFond), iar legatura (Screens/HdsEcranNegru.py) pune peste imagine, sub bare si sub mesaj, un fond negru pe tot
#   ecranul. Fondul ramane si la zap-ul urmator pana vin cadre noi (cine trece prin mai multe canale criptate la rand vede
#   negru, nu iar cadrul vechi) si se ascunde la cel mult PAS_FOND_MS dupa primul cadru nou. Cu „Ecran negru” nu se vede
#   nicio diferenta. Fara setare noua; o masura nesigura nu pune niciodata fondul (mai bine cadrul vechi decat negru peste
#   un canal bun).
# - textele: fraza simpla pe intelesul oricui, fapta (butonul) unde ajuta si detaliul tehnic, mai mic. Aceleasi texte
#   pe televizor, in ferestrele de eroare si in web.
#
# Starea pentru web (ultima_stare) si fapta ceruta din web (fapta_web) trec prin _STARE, pusa de fereastra de pe
# televizor. Setarea: config.usage.hds_ecran_negru (setup.xml, sectiunea usage), SystemInfo["HdsEcranNegru"].
# Canalele numai cu sunet (0.7.5): un canal TV care nu are nicio pista video, dar are sunet, primeste verdictul
# NUMAI_SUNET, fara asteptare: la DVB (si la fluxurile IP prin servicedvb) dupa PMT (fara pista video, fara pista video
# necunoscuta numita de nucleu, cu pista audio), la fluxurile prin GStreamer (4097 si celelalte) dupa numarul pistelor
# video spus de servicemp3 (getInfo(sUser+17), -1 cat nu se stie) si pistele audio; fara numarul pistelor (alt serviciu
# de redare), dupa PRAG_SUNET_FLUX secunde fara imagine si fara codec video. Verdictul il primeste Screens/HdsEcranNegru.py:
# ecranul radio ca fundal (Screens/HdsEcranRadio.py, numaiSunet) si protectia ecranului (Screens/ScreenSaver.py), dupa
# setarea „La canalele numai cu sunet” (Components/HdsRadioSetari.py); mesajul se vede numai fara ecranul radio.
# Analiza fluxului (Components/HdsAnalizaFlux.py) se leaga la verdictele „date” si „format”: fapta F_ANALIZA, iar
# fotografia primeste ce s-a aflat deja (d["analiza"]: ce trimite serviciul, tipul pistei video necunoscute), deci
# analizeaza() ramane fara citiri. Pornirea singura a analizei: config.usage.hds_analiza_flux („automat”).
# Pasii decriptarii (Components/HdsPasiDecriptare.py, setarea config.usage.hds_pasi_decriptare, oprita din fabrica):
# cu setarea pornita, fotografia canalului DVB ii noteaza (noteaza_din) si primeste randurile vii (d["pasi"]), pe care
# verdictul CRIPTAT le duce sub mesaj (v["pasi"]); cu setarea oprita nu se cheama nimic.
#
# mesajele spun numai ce s-a masurat. "Fara semnal" nu mai da sfaturi despre
# cablu sau despre vreme (cauza nu se stie din receptor); cand plecarea antenei cu motor nu se stie, mesajul nu mai spune
# ca antena se roteste si nici ca imaginea apare dupa ce ajunge, ci ca a plecat comanda si ca receptorul asteapta
# semnalul (d["rotor_plecare_nestiuta"], din plecare_nestiuta()).
# La Fara semnal pe o antena cu motor, cand verificarea readucerii a prins alt transponder al aceluiasi satelit
# (Components/HdsMotorPozitie.py, transponderNuEmite), antena e la locul ei: mesajul spune ca transponderul canalului
# nu emite acum, iar detaliul numeste transponderul prins (d["tp_nu_emite"], din transponder_nu_emite()).

import os
import time

# ---------------------------------------------------------------- pragurile (secunde)

PRAG_SEMNAL = 4.0      # dupa evStart fara semnal prins: „Fără semnal” (acordarea normala ia sub o secunda)
PRAG_IMAGINE = 6.0     # fara cadre noi atatea secunde (de la pornire sau de la ultimul cadru): ecran negru
PRAG_CADRE = 3.0       # cadre noi in ultimele atatea secunde: imaginea vine
PRAG_SUNET_FLUX = 8.0  # flux prin alt serviciu de redare, fara numarul pistelor video: numai sunet dupa atatea secunde
URMARIRE_FLUX_S = 30.0 # fluxul prin GStreamer fara imagine si fara verdict se mai urmareste atatea secunde
PAS_ASTEPTARE_MS = 1000
PAS_IMAGINE_MS = 2000
# fondul negru: fara niciun cadru nou atatea secunde de la schimbare (toate zap-urile reusite masurate pe Vu+ Duo 4K SE in
# asistenta 888733 au dat imaginea in 0,7-2,9 s), apoi verificarea repede a cadrelor cat se vede fondul
PRAG_FOND = 4.0
PAS_FOND_MS = 300
# lib/service/servicedvb.cpp: getInfo(sUser + INFO_PTS) = PTS-ul video (31 de biti), -1 fara PTS, -2 fara decodor
INFO_PTS = 40
MAX_ETICHETE = 4
MAX_CAID_DETALIU = 6
# „Tunerul este ocupat”: cate inregistrari se numesc (celelalte: „și încă N”) si cate litere are cel mult un nume
MAX_INREGISTRARI = 2
NUME_INREGISTRARE = 36

FEL_DVB = ("s", "c", "t", "a")
# fluxurile IP prin servicedvb (canalele IPTV din liste, http://...): primesc numai formatul numit din PMT (semnalul,
# tunerul, criptarea si celelalte verdicte nu au sens acolo; erorile lor raman in fereastra scurta de eroare)
FEL_FLUX = "ip"
# tipurile de serviciu cu imagine (DVB): SD, MPEG-2 HD, AVC SD/HD, HEVC, si 0x86 folosit de unii operatori pentru HD
TV_STYPES = (1, 0x11, 0x16, 0x19, 0x1F, 0x20, 0x86)
RADIO_STYPES = (2, 10)

# ---------------------------------------------------------------- codurile verdictului (aceleasi si in web)

BLOCAT = "blocat"
FARA_TUNER = "fara_tuner"
TUNER_NESETAT = "tuner_nesetat"
# satelitul canalului e setat pe un tuner, dar transponderul cere un tuner care alege fluxul (multistream: flux 1..255 sau o
# secventa PLS aleasa) si niciun tuner setat pe satelit nu stie (lib/dvb/hdsmultistream.h, cereTunerMultistream)
MULTISTREAM_FARA_TUNER = "multistream_fara_tuner"
# zap pe un satelit pe care numai motorul USALS il prinde, cu locul antenei nestabilit (Components/HdsLocul.py)
LOC_NESTABILIT = "loc_nestabilit"
# zap pe un satelit USALS care e sub orizont din locul antenei stabilit (locul scris gresit, de pilda emisferele schimbate):
# nucleul nu primeste satelitul (NimManager.SecConfigure, hdsSubOrizont), deci nicio comanda spre motor
SUB_ORIZONT = "sub_orizont"
ANTENA = "antena"
FARA_SEMNAL = "fara_semnal"
FRECVENTA_GOALA = "frecventa_goala"
POST_MUTAT = "post_mutat"
FARA_PMT = "fara_pmt"
FORMAT = "format"
DATE = "date"
CRIPTAT = "criptat"
FARA_IMAGINE = "fara_imagine"
NUMAI_SUNET = "numai_sunet"
# canal DVB-T2 din satelit prin releul local: binarul T2 nu a deschis inca sesiunea 8001 pe purtator (pauza, limita sau
# conectarea), deci lipsa PAT-ului nu spune nimic despre frecventa (OC2, Abertis 30W: 45-54 s dupa player)
T2_PORNESTE = "t2_porneste"
CODURI = (BLOCAT, FARA_TUNER, TUNER_NESETAT, MULTISTREAM_FARA_TUNER, LOC_NESTABILIT, SUB_ORIZONT, ANTENA, FARA_SEMNAL, FRECVENTA_GOALA, POST_MUTAT, FARA_PMT,
	FORMAT, DATE, CRIPTAT, FARA_IMAGINE, NUMAI_SUNET, T2_PORNESTE)

# faptele (butonul de pe televizor si din web)
F_CAUTA_TP = "cauta_tp"          # cautarea din nou pe transponderul canalului
F_CAUTA = "cauta"                # ecranul de cautare al felului de receptie (satelit, cablu, terestru)
F_INREGISTRARI = "inregistrari"  # lista temporizatoarelor si inregistrarilor
F_COD = "cod"                    # codul pentru parinti, din nou
F_TUNER = "tuner"                # setarile tunerului
F_ANALIZA = "analiza"            # analiza fluxului (serviciu de date, format necunoscut)
F_LOC = "loc"                    # alegerea locului antenei (Screens/HdsLocul.py)
F_MODULE = "module"              # ecranul modulelor de acces (Screens/CamSetup.py), la ICAM fara SoftCSA
F_ASCUNDE = "ascunde"            # numai din web: ca EXIT pe televizor
FAPTE = (F_CAUTA_TP, F_CAUTA, F_INREGISTRARI, F_COD, F_TUNER, F_ANALIZA, F_LOC, F_MODULE)

# erorile acordarii, dupa numele evenimentelor eDVBServicePMTHandler (sDVBState)
E_FARA_TUNER = "fara_tuner"
E_ACORDARE = "acordare"
E_FARA_PAT = "fara_pat"
E_FARA_SID = "fara_sid"
E_FARA_PMT = "fara_pmt"
E_CONFIGURARE = "configurare"
NUME_EVENIMENTE = (("eventNoResources", E_FARA_TUNER), ("eventTuneFailed", E_ACORDARE), ("eventNoPAT", E_FARA_PAT),
	("eventNoPATEntry", E_FARA_SID), ("eventNoPMT", E_FARA_PMT), ("eventMisconfiguration", E_CONFIGURARE))


def N_(text):
	"""Marcaj pentru xgettext, fara efect: textul se traduce la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# ---------------------------------------------------------------- textele

TITLURI = {
	BLOCAT: N_("Canal blocat"),
	FARA_TUNER: N_("Tunerul este ocupat"),
	TUNER_NESETAT: N_("Tunerul nu e setat pentru acest canal"),
	MULTISTREAM_FARA_TUNER: N_("Tunerul nu poate alege fluxul"),
	LOC_NESTABILIT: N_("Locul antenei nu e stabilit"),
	SUB_ORIZONT: N_("Satelitul nu se vede din locul antenei"),
	ANTENA: N_("Antena se rotește"),
	FARA_SEMNAL: N_("Fără semnal"),
	FRECVENTA_GOALA: N_("Frecvența nu trimite nimic"),
	POST_MUTAT: N_("Postul nu mai e pe această frecvență"),
	FARA_PMT: N_("Canalul nu răspunde"),
	FORMAT: N_("Imagine într-un format necunoscut"),
	DATE: N_("Serviciu de date"),
	CRIPTAT: N_("Acces condiționat"),
	FARA_IMAGINE: N_("Fără imagine"),
	NUMAI_SUNET: N_("Numai sunet"),
	T2_PORNESTE: N_("Pornește fluxul DVB-T2"),
}

TEXTE = {
	BLOCAT: N_("Canalul este blocat cu codul pentru părinți."),
	FARA_TUNER: N_("Tunerul este folosit acum pe altă frecvență, pentru o înregistrare sau o transmisie în rețea, și nu poate porni acest canal."),
	TUNER_NESETAT: N_("Niciun tuner nu e setat să primească acest canal. Verifică setările tunerului."),
	MULTISTREAM_FARA_TUNER: N_("Satelitul e setat corect, dar acest canal emite în multistream (mai multe fluxuri pe aceeași frecvență), iar tunerul setat pe acest satelit nu poate alege fluxul. Canalul merge pe un tuner cu multistream."),
	LOC_NESTABILIT: N_("Acest satelit se recepționează numai cu motorul USALS, iar motorul nu știe unde ești, deci antena nu se rotește. Apasă OK și alege țara și orașul."),
	SUB_ORIZONT: N_("Din locul antenei scris în setări, acest satelit e sub orizont, deci motorul nu rotește antena spre el. Probabil emisfera (Nord sau Sud) ori partea față de Greenwich (Est sau Vest) e aleasă greșit. Apasă OK și verifică locul antenei."),
	# numai ce s-a masurat (un sfat despre cablu sau vreme poate fi gresit cand cauza nu se
	# stie)
	FARA_SEMNAL: N_("Receptorul nu recepționează semnalul acestui canal."),
	FRECVENTA_GOALA: N_("Pe această frecvență nu vine nicio emisiune. Canalele de aici s-au oprit sau s-au mutat. O căutare nouă a canalelor le poate găsi."),
	POST_MUTAT: N_("Postul nu mai emite pe această frecvență. Probabil s-a mutat sau s-a oprit. O căutare nouă a canalelor îl poate găsi."),
	FARA_PMT: N_("Canalul nu trimite datele de pornire. Poate e oprit acum sau s-a mutat. O căutare nouă pe această frecvență îl poate găsi."),
	FORMAT: N_("Canalul trimite imaginea într-un format pe care acest receptor nu îl poate reda."),
	DATE: N_("Acest serviciu nu are imagine și nici sunet. Trimite numai date, de exemplu actualizări sau ghidul programelor."),
	CRIPTAT: N_("Canalul este criptat. Niciun modul de acces condiționat nu îl decriptează."),
	FARA_IMAGINE: N_("Canalul nu trimite imagine acum. Emisia poate fi oprită sau canalul s-a mutat."),
	NUMAI_SUNET: N_("Canalul trimite acum numai sunet, fără imagine."),
	T2_PORNESTE: N_("Receptorul pornește fluxul DVB-T2 din satelit. Canalul apare după ce tunerul primește datele."),
}
T_T2_PORNESTE_SEC = N_("Receptorul pornește fluxul DVB-T2 din satelit. Tunerul se conectează în %d secunde.")
T_ANTENA_SPRE = N_("Antena se rotește spre %s. Imaginea apare după ce ajunge.")
T_ANTENA = N_("Antena se rotește. Imaginea apare după ce ajunge.")
# plecarea antenei nu se stie (dupa pornire, dupa flash, dupa o pozitie uitata): se stie numai ca a plecat comanda
T_COMANDA_TITLU = N_("Comanda a plecat spre motor")
T_COMANDA_SPRE = N_("Receptorul a trimis motorului comanda spre %s. De unde pleacă antena nu se știe. Receptorul așteaptă semnalul.")
T_COMANDA = N_("Receptorul a trimis comanda motorului. De unde pleacă antena nu se știe. Receptorul așteaptă semnalul.")
T_DOAR_SUNET = N_("Se aude doar sunetul.")
T_CRIPTAT_ECM = N_("Canalul este criptat. Accesul condiționat răspunde, dar imaginea nu se decriptează.")
T_INREGISTREAZA = N_("Se înregistrează: %s")
T_FORMAT_TITLU = N_("Imagine în formatul %s")
T_FORMAT_NUMIT = N_("Canalul trimite imaginea în formatul %s, pe care acest receptor nu îl poate reda.")
T_SI_INCA = N_("și încă %d")

FAPTE_TEXT = {
	F_CAUTA_TP: N_("Caută din nou pe această frecvență"),
	F_CAUTA: N_("Caută canalele din nou"),
	F_INREGISTRARI: N_("Arată înregistrările"),
	F_COD: N_("Introdu codul"),
	F_TUNER: N_("Deschide setările tunerului"),
	F_ANALIZA: N_("Analizează fluxul"),
	F_LOC: N_("Alege locul antenei"),
	F_MODULE: N_("Deschide modulele de acces"),
}
T_ARATA_ANALIZA = N_("Arată analiza fluxului")
T_DATE_STIUT = N_("Acest serviciu nu are imagine și nici sunet. Trimite: %s.")
T_SE_ANALIZEAZA = N_("Se analizează fluxul...")
ANALIZA_OK, ANALIZA_AUTOMAT = "ok", "automat"
ALEGERI_ANALIZA = ((ANALIZA_OK, N_("La apăsarea OK")), (ANALIZA_AUTOMAT, N_("Automat")))

T_DETALIU = N_("Detaliu tehnic: %s")
DETALII = {
	FARA_TUNER: N_("niciun tuner liber"),
	TUNER_NESETAT: N_("configurarea tunerului nu se potrivește canalului"),
	MULTISTREAM_FARA_TUNER: N_("transponder multistream (%s); tunerele setate pe satelit (%s) nu au multistream"),
	LOC_NESTABILIT: N_("USALS fără locul antenei; nucleul nu primește satelitul"),
	SUB_ORIZONT: N_("USALS: satelitul e sub orizont din locul antenei; nucleul nu primește satelitul"),
	FRECVENTA_GOALA: N_("PAT necitit în timpul așteptat"),
	POST_MUTAT: N_("SID negăsit în PAT"),
	FARA_PMT: N_("PMT necitit în timpul așteptat"),
	FORMAT: N_("nicio pistă video cunoscută în PMT (de exemplu AVS2, VVC sau AV1)"),
}
D_ACORDARE = N_("acordarea a eșuat")
D_TUNER_PE = N_("tunerul %s nu recepționează pe %s")
D_TIP_SERVICIU = N_("tipul serviciului %s, fără piste video și audio")
D_FURNIZOR = N_("Furnizor: %s")
D_PISTA_FARA_IMAGINE = N_("semnal bun, pista video %d fără imagine")

T_SEMNAL = N_("Semnal")
T_CALITATE = N_("Calitate")
T_INDEMN = N_("EXIT ascunde mesajul")
# antena cu motor e la locul ei (alt transponder al satelitului se prinde), dar transponderul canalului nu emite
T_TP_NU_EMITE = N_("Transponderul acestui canal nu emite acum. Antena e la locul ei: alt transponder al aceluiași satelit se recepționează.")
D_TP_PRINS = N_("alt transponder se recepționează: %s")
# antena pe alt satelit (AS26, asistenta la un GigaBlue UHD Quad 4K Pro): tunerul prinde semnal pe doua sau mai multe frecvente ale satelitului,
# dar fluxurile prinse nu au canalele din lista (SID negasit in PAT); vezi flux_strain_noteaza si _alt_satelit
T_ALT_SAT_TITLU = N_("Antena pare îndreptată spre alt satelit")
T_ALT_SAT = N_("Tunerul %s prinde semnal, dar nu de la %s: pe frecvențele lui vin alte emisiuni decât cele din lista de canale. Antena legată la tunerul %s pare îndreptată spre alt satelit sau cablul ei e în altă mufă. Verifică antena și cablul, cu receptorul oprit.")
D_ALT_SAT = N_("tunerul %s: SID negăsit în PAT pe %s")


def _curat(text, n=120):
	"""Text venit din satelit: fara caractere de control, taiat."""
	try:
		t = text if isinstance(text, str) else str(text)
	except Exception:
		return u""
	return u"".join(c if c >= u" " else u" " for c in t)[:n].strip()


def _scurt(text, n):
	"""Textul taiat la `n` litere, cu „…” la capat cand s-a taiat."""
	return text if len(text) <= n else text[:max(1, n - 1)].rstrip() + u"…"


def _lista_inregistrari(nume):
	"""„Tagesschau, Sportschau live: Bundesliga, 5. Spiel… și încă 1”: primele MAX_INREGISTRARI nume, scurtate, apoi
	cate au mai ramas."""
	nume = [n for n in nume if n]
	aratate = [_scurt(n, NUME_INREGISTRARE) for n in nume[:MAX_INREGISTRARI]]
	text = u", ".join(aratate)
	rest = len(nume) - len(aratate)
	if rest > 0:
		text = text + u" " + _t(T_SI_INCA) % rest
	return text


def _fapta(cod_fapta, text=None):
	return {"id": cod_fapta, "text": text or _t(FAPTE_TEXT[cod_fapta])} if cod_fapta else None


def _detaliu(*parti):
	parti = [p for p in parti if p]
	return _t(T_DETALIU) % u" · ".join(parti) if parti else u""


def _verdict(cod, d, text=None, fapta=None, detaliu=u"", etichete=None, bare=False, fapta_text=None, titlu=None):
	v = {
		"cod": cod,
		"canal": _curat(d.get("canal") or u""),
		"titlu": titlu if titlu is not None else _t(TITLURI[cod]),
		"text": text if text is not None else _t(TEXTE[cod]),
		"etichete": list(etichete or []),
		"semnal": None,
		"calitate": None,
		"fapta": _fapta(fapta, fapta_text),
		"detaliu": detaliu,
		"ref": d.get("ref"),
	}
	if bare:
		v["semnal"] = _procent(d.get("nivel"))
		v["calitate"] = _procent(d.get("calitate"))
	return v


def _procent(v):
	try:
		v = int(v)
	except (TypeError, ValueError):
		return None
	return max(0, min(100, v)) if v >= 0 else None


def _fapta_cautare(d):
	"""Cautarea din nou pe aceeasi frecventa unde se poate face direct (satelit, cablu), altfel ecranul de cautare."""
	return F_CAUTA_TP if d.get("fel") in ("s", "c") and d.get("tp_cautare") else F_CAUTA


def _etichete_criptare(d):
	"""Numele sistemelor de criptare ale canalului, in ordinea CAID-urilor, cel mult MAX_ETICHETE etichete; cand sunt
	mai multe sisteme, ultima eticheta spune cate au ramas („+2”)."""
	nume = []
	for n in d.get("sisteme") or []:
		n = _curat(n, 32)
		if n and n not in nume:
			nume.append(n)
	if len(nume) > MAX_ETICHETE:
		aratate = nume[:MAX_ETICHETE - 1]
		return aratate + [u"+%d" % (len(nume) - len(aratate))]
	return nume


def _caid_text(caids):
	lista = []
	for c in caids or []:
		try:
			lista.append(u"%04X" % (int(c) & 0xFFFF))
		except (TypeError, ValueError):
			continue
	if not lista:
		return u""
	rest = len(lista) - MAX_CAID_DETALIU
	text = u"CAID " + u", ".join(lista[:MAX_CAID_DETALIU])
	return text + (u" +%d" % rest if rest > 0 else u"")


def _tip_serviciu_text(stype):
	try:
		return u"0x%02X" % int(stype)
	except (TypeError, ValueError):
		return u"?"


STARI_FARA_SEMNAL = ("FAILED", "LOSTLOCK", "TUNING", "IDLE")


def semnal_prins(lock, stare):
	"""True / False dupa bitul de prindere al placii (FE_HAS_LOCK, citit acum); cand placa nu il da, dupa starea
	tunerului din enigma2; None cand nu se stie nimic (atunci nu se spune „Fără semnal”)."""
	if lock == 1:
		return True
	if lock == 0:
		return False
	stare = (stare or "").upper()
	if stare == "LOCKED":
		return True
	if stare in STARI_FARA_SEMNAL:
		return False
	return None


def analizeaza(d):
	"""Verdictul pentru fotografia `d` (vezi Urmaritor.fotografie), sau None cand ecranul nu e negru sau nu se stie
	inca. Verdictul: {cod, canal, titlu, text, etichete, semnal, calitate, fapta: {id, text} | None, detaliu}."""
	if not d:
		return None
	if d.get("pauza") or d.get("pip"):
		return None
	if d.get("nimic"):
		if d.get("blocat"):
			return _verdict(BLOCAT, d, fapta=F_COD)
		return None
	if d.get("radio"):
		return None
	if d.get("fel") == FEL_FLUX:
		numit = _format_numit(d, analiza=False)
		if numit is None and numai_sunet(d):
			return _verdict(NUMAI_SUNET, d)
		return numit
	if d.get("fel") not in FEL_DVB:
		return None
	if d.get("imagine") is True:
		return None
	eroare = d.get("eroare")
	secunde = d.get("secunde") or 0.0
	if eroare == E_FARA_TUNER:
		text = _t(TEXTE[FARA_TUNER])
		nume = [_curat(n, 60) for n in (d.get("inregistrari") or []) if n]
		if nume:
			text = text + u"\n" + _t(T_INREGISTREAZA) % _lista_inregistrari(nume)
		return _verdict(FARA_TUNER, d, text=text, fapta=F_INREGISTRARI, detaliu=_detaliu(_t(DETALII[FARA_TUNER])))
	if eroare == E_CONFIGURARE and d.get("sub_orizont"):
		return _verdict(SUB_ORIZONT, d, fapta=F_LOC, detaliu=_detaliu(_t(DETALII[SUB_ORIZONT])))
	if eroare == E_CONFIGURARE and d.get("loc_nestabilit"):
		return _verdict(LOC_NESTABILIT, d, fapta=F_LOC, detaliu=_detaliu(_t(DETALII[LOC_NESTABILIT])))
	if eroare == E_CONFIGURARE and d.get("multistream_fara_tuner"):
		m = d["multistream_fara_tuner"]
		detaliu = _detaliu(_t(DETALII[MULTISTREAM_FARA_TUNER]) % (m.get("flux") or u"?", m.get("tunere") or u"?"))
		# setarile tunerului ajuta numai cand receptorul are un tuner cu multistream (satelitul se poate pune pe el)
		return _verdict(MULTISTREAM_FARA_TUNER, d, fapta=F_TUNER if m.get("alt_tuner") else None, detaliu=detaliu)
	if eroare == E_CONFIGURARE:
		return _verdict(TUNER_NESETAT, d, fapta=F_TUNER, detaliu=_detaliu(_t(DETALII[TUNER_NESETAT])))
	if d.get("rotor") and d.get("fel") == "s":
		spre = _curat(d.get("rotor_spre") or u"", 60)
		if d.get("rotor_plecare_nestiuta"):
			# plecarea nu se stie: nici ca antena se roteste, nici cand ajunge; numai ca a plecat comanda
			text = _t(T_COMANDA_SPRE) % spre if spre else _t(T_COMANDA)
			return _verdict(ANTENA, d, text=text, titlu=_t(T_COMANDA_TITLU))
		text = _t(T_ANTENA_SPRE) % spre if spre else _t(T_ANTENA)
		return _verdict(ANTENA, d, text=text)
	if eroare == E_FARA_PAT and d.get("t2_criptat"):
		# canalul DVB-T2 din satelit prin releul local cu fluxul numai criptat (BISS fara cheie, Abertis 30W): frecventa
		# trimite, dar releul nu are ce desface; nu "Frecventa nu trimite nimic" cu o cautare noua
		return _verdict(CRIPTAT, d, text=_t(TEXTE[CRIPTAT]))
	if eroare == E_FARA_PAT and d.get("t2_porneste") is not None:
		# releul T2 nu a deschis inca sesiunea 8001 pe purtator: nimic de facut de om, fara cautare noua
		sec = d["t2_porneste"]
		text = _t(T_T2_PORNESTE_SEC) % sec if sec > 0 else _t(TEXTE[T2_PORNESTE])
		return _verdict(T2_PORNESTE, d, text=text)
	if eroare == E_FARA_PAT:
		return _verdict(FRECVENTA_GOALA, d, fapta=F_CAUTA, detaliu=_detaliu(_t(DETALII[FRECVENTA_GOALA])))
	if eroare == E_FARA_SID:
		if d.get("alt_satelit"):
			return _verdict_alt_satelit(POST_MUTAT, d)
		return _verdict(POST_MUTAT, d, fapta=_fapta_cautare(d), detaliu=_detaliu(_t(DETALII[POST_MUTAT])))
	if eroare == E_FARA_PMT:
		return _verdict(FARA_PMT, d, fapta=_fapta_cautare(d), detaliu=_detaliu(_t(DETALII[FARA_PMT])))
	prins = semnal_prins(d.get("lock", -1), d.get("stare_tuner"))
	if (eroare == E_ACORDARE or prins is False) and secunde >= PRAG_SEMNAL:
		# numai faptele masurate (nivelul si calitatea in bare, tunerul si frecventa in detaliu), fara cauze presupuse
		if d.get("alt_satelit") and not d.get("tp_nu_emite"):
			# alte frecvente ale satelitului s-au prins pe acest tuner cu fluxuri straine: antena pare pe alt satelit
			return _verdict_alt_satelit(FARA_SEMNAL, d, bare=True)
		text = _t(TEXTE[FARA_SEMNAL])
		parti = []
		if d.get("tp_text"):
			parti.append(_t(D_TUNER_PE) % (d.get("tuner") or u"A", _curat(d["tp_text"], 90)))
		if eroare == E_ACORDARE:
			parti.append(_t(D_ACORDARE))
		if d.get("tp_nu_emite"):
			text = _t(T_TP_NU_EMITE)
			parti.append(_t(D_TP_PRINS) % _curat(d["tp_nu_emite"], 60))
		return _verdict(FARA_SEMNAL, d, text=text, detaliu=_detaliu(*parti), bare=True)
	if prins is False:
		return None
	numit = _format_numit(d)
	if numit is not None:
		return numit
	if numai_sunet(d):
		return _verdict(NUMAI_SUNET, d)
	if d.get("imagine") is None or (d.get("negru_de") or 0.0) < PRAG_IMAGINE:
		return None
	if not d.get("pmt"):
		return None
	video = (d.get("video_pid") or -1) > 0
	audio = (d.get("audio_pid") or -1) > 0
	if not video:
		a = d.get("analiza") or {}
		fapta_text = _t(T_ARATA_ANALIZA) if a.get("stare") == "gata" else None
		if not audio and d.get("tip_serviciu") not in TV_STYPES:
			text = None
			if a.get("stare") == "citeste":
				text = _t(TEXTE[DATE]) + u"\n" + _t(T_SE_ANALIZEAZA)
			elif a.get("stare") == "gata" and a.get("feluri"):
				text = _t(T_DATE_STIUT) % a["feluri"]
			return _verdict(DATE, d, text=text, fapta=F_ANALIZA, fapta_text=fapta_text,
				detaliu=_detaliu(_t(D_TIP_SERVICIU) % _tip_serviciu_text(d.get("tip_serviciu"))))
		text = _t(TEXTE[FORMAT])
		if audio:
			text = text + u" " + _t(T_DOAR_SUNET)
		if a.get("stare") == "citeste":
			text = text + u"\n" + _t(T_SE_ANALIZEAZA)
		detaliu = _detaliu(a["codec"]) if a.get("codec") else _detaliu(_t(DETALII[FORMAT]))
		return _verdict(FORMAT, d, text=text, fapta=F_ANALIZA, fapta_text=fapta_text, detaliu=detaliu)
	furnizor = _curat(d.get("furnizor") or u"", 60)
	if d.get("criptat"):
		text = _t(T_CRIPTAT_ECM) if (d.get("ecm") or -1) > 0 else _t(TEXTE[CRIPTAT])
		fapta = None
		if d.get("icam_fara_modul"):
			# ICAM cu un modul care nu il descifreaza: textul din Components/HdsSoftCsa (TEXT_ICAM_CANAL, cu numele
			# modulelor care il descifreaza), fapta deschide ecranul modulelor
			text, fapta = _t(d["icam_fara_modul"]), F_MODULE
		v = _verdict(CRIPTAT, d, text=text, fapta=fapta, etichete=_etichete_criptare(d),
			detaliu=_detaliu(_caid_text(d.get("caids")), (_t(D_FURNIZOR) % furnizor) if furnizor else u""))
		# pasii decriptarii (Components/HdsPasiDecriptare.py), numai cu setarea lor pornita: randurile vii sub mesaj
		if d.get("pasi"):
			v["pasi"] = list(d["pasi"])
		return v
	return _verdict(FARA_IMAGINE, d, fapta=_fapta_cautare(d),
		detaliu=_detaliu(_t(D_PISTA_FARA_IMAGINE) % d["video_pid"]))


def numai_sunet(d):
	"""True cand canalul TV din fotografia `d` nu are nicio pista video, dar are sunet (vezi antetul)."""
	if not d or d.get("radio") or d.get("pauza") or d.get("pip") or d.get("imagine") is True:
		return False
	if d.get("flux_gst"):
		if (d.get("piste_audio") or 0) <= 0:
			return False
		n = d.get("piste_video")
		if n is not None and n >= 0:
			return n == 0
		return not d.get("codec_video") and (d.get("secunde") or 0.0) >= PRAG_SUNET_FLUX
	if not d.get("pmt") or d.get("video_necunoscut"):
		return False
	if (d.get("video_pid") or -1) > 0 or (d.get("audio_pid") or -1) <= 0:
		return False
	# analiza fluxului a gasit o pista video pe care decodorul nu o cunoaste: ramane „format necunoscut”
	return not (d.get("analiza") or {}).get("codec")


def _format_numit(d, analiza=True):
	"""Verdictul FORMAT cu numele formatului, cand PMT-ul e citit, nu are nicio pista video pe care decodorul o
	cunoaste si nucleul a numit una pe care nu o cunoaste (d["video_necunoscut"]: {"codec", "detaliu"}, din
	HdsAnalizaFlux.video_necunoscut_din_nucleu). Nu asteapta PRAG_IMAGINE: se stie din PMT ca imaginea nu va veni.
	`analiza` = fapta „Analizează fluxul” (numai la canalele DVB: analiza citeste demultiplexorul tunerului)."""
	vn = d.get("video_necunoscut")
	if not vn or not vn.get("codec") or not d.get("pmt") or (d.get("video_pid") or -1) > 0:
		return None
	nume = _curat(vn["codec"], 40)
	text = _t(T_FORMAT_NUMIT) % nume
	if (d.get("audio_pid") or -1) > 0:
		text = text + u" " + _t(T_DOAR_SUNET)
	a = d.get("analiza") or {}
	fapta_text = _t(T_ARATA_ANALIZA) if a.get("stare") == "gata" else None
	return _verdict(FORMAT, d, text=text, titlu=_t(T_FORMAT_TITLU) % nume, fapta=F_ANALIZA if analiza else None,
		fapta_text=fapta_text if analiza else None, detaliu=_detaliu(vn.get("detaliu") or u""))


def verdict_eroare(eroare, fel="s", canal=u""):
	"""Verdictul pentru o eroare a acordarii (E_*), fara fotografie: pentru ferestrele de eroare, cand mesajul de pe
	ecran e oprit; `canal` e numele serviciului redat (randul de sus al ferestrei). None pentru o eroare necunoscuta."""
	if eroare not in (E_FARA_TUNER, E_CONFIGURARE, E_FARA_PAT, E_FARA_SID, E_FARA_PMT, E_ACORDARE):
		return None
	d = {"fel": fel if fel in FEL_DVB else "s", "eroare": eroare, "secunde": PRAG_SEMNAL, "lock": -1, "canal": canal or u""}
	if eroare == E_CONFIGURARE and d["fel"] == "s":
		# ca la mesajul de pe ecran (fotografie): satelitul prins numai cu motorul USALS si locul antenei nestabilit spune
		# „Locul antenei nu e stabilit” (OK = alege locul), nu „Tunerul nu e setat” (Quad 4K Pro cu motor)
		d["loc_nestabilit"] = loc_nestabilit(_refRedata())
		d["sub_orizont"] = sub_orizont(_refRedata())
		d["multistream_fara_tuner"] = multistream_fara_tuner(_refRedata())
	if eroare == E_FARA_PAT:
		d["t2_criptat"] = t2_releu_criptat(_refRedata())
		d["t2_porneste"] = t2_releu_porneste(_refRedata())
	return analizeaza(d)


STAT_T2 = "/tmp/hdst2mi-stat.json"      # statisticile binarului T2 (Hds/DabT2/t2/bin/t2mi_decap.c, -j)
# starile intrarii HTTP a binarului in care nu a venit inca nicio sesiune 8001 (h_nume din t2mi_decap.c)
STARI_T2_INAINTE = ("asteapta_client", "conectare", "astept_date", "pauza", "limita")


def _este_releu_t2(ref):
	try:
		s = ref.toString() if hasattr(ref, "toString") else str(ref or "")
	except Exception:
		return False
	return "127.0.0.1%3a8889/t2/" in s or "127.0.0.1:8889/t2/" in s


def t2_releu_porneste(ref, cale=STAT_T2, proc="/proc"):
	"""Canal DVB-T2 din satelit prin releul local, iar binarul T2 (viu) nu a deschis inca nicio sesiune 8001 pe
	purtator si nu a primit niciun octet: asteapta clientul, pauza, limita de conexiuni sau raspunsul serverului.
	-> secundele pana la conectare (pauza_ramasa_ms rotunjit in sus; 0 = nu se stie) sau None (alt caz: fara releu,
	sesiune deja deschisa, date venite, fisier lipsa sau stricat). Masurat pe Octagon (OC2): dupa o cautare
	DVB-T2 prin satelit binarul pornit la zap sta in limita (fereastra de 4 conexiuni plina) pana la 50 s, iar eventNoPAT
	vine dupa ~10 s."""
	if not _este_releu_t2(ref):
		return None
	import json
	try:
		with open(cale) as f:
			st = json.loads(f.read(65536))
		if str(st.get("http_stare")) not in STARI_T2_INAINTE:
			return None
		if int(st.get("sesiuni_8001") or 0) or int(st.get("octeti_intrare") or 0) or st.get("antet_200") is True:
			return None
		pid = int(st.get("pid") or 0)
		if pid <= 0 or not os.path.exists(os.path.join(proc, str(pid))):
			return None
		ms = int(st.get("pauza_ramasa_ms") or 0)
	except Exception:
		return None
	return max(0, (ms + 999) // 1000)


def t2_releu_criptat(ref):
	"""True cand serviciul e un canal DVB-T2 din satelit redat prin releul local (http://127.0.0.1:8889/t2/...) si
	binarul T2 primeste fluxul numai criptat, fara nimic iesit (Hds/DabT2/pornire.flux_criptat). Fara releu pornit
	(modulul neincarcat), alt serviciu sau o eroare: False. Nu importa nimic: controlorul T2 e deja incarcat cand canta."""
	try:
		s = ref.toString() if hasattr(ref, "toString") else str(ref or "")
	except Exception:
		return False
	if "127.0.0.1%3a8889/t2/" not in s and "127.0.0.1:8889/t2/" not in s:
		return False
	import sys
	pornire = sys.modules.get("Hds.DabT2.pornire")
	try:
		return bool(pornire is not None and pornire.flux_criptat())
	except Exception:
		return False


def _refRedata():
	"""Referinta serviciului redat acum (pentru ferestrele de eroare, care primesc numai info), sau None."""
	try:
		import NavigationInstance
		return NavigationInstance.instance.getCurrentlyPlayingServiceReference()
	except Exception:
		return None


def nume_din_info(info):
	"""Numele serviciului din iServiceInformation, fara caractere de control, sau "" cand nu se poate citi."""
	try:
		return _curat(info.getName() if info is not None else u"")
	except Exception:
		return u""


FEL_DUPA_TUNER = {"DVB-S": "s", "DVB-S2": "s", "DVB-C": "c", "DVB-T": "t", "DVB-T2": "t", "ATSC": "a"}


def fel_din_info(info):
	"""Felul receptiei ("s", "c", "t", "a") din datele transponderului serviciului, sau "s" cand nu se stie."""
	try:
		from enigma import iServiceInformation
		d = info.getInfoObject(iServiceInformation.sTransponderData) if info else None
		return FEL_DUPA_TUNER.get(str((d or {}).get("tuner_type", "")).upper(), "s")
	except Exception:
		return "s"


def text_fereastra(v):
	"""Textul ferestrei de eroare (cand mesajul de pe ecran e oprit): fraza simpla, apoi detaliul tehnic."""
	if not v:
		return u""
	parti = [v.get("text") or u""]
	if v.get("detaliu"):
		parti.append(v["detaliu"])
	return u"\n\n".join(p for p in parti if p)


def eroare_acordare(stare_dvb):
	"""Numele erorii (E_*) pentru valoarea sDVBState, sau None; constantele vin din enigma2 la prima chemare."""
	tabel = _tabel_erori()
	return tabel.get(stare_dvb) if tabel else None


_TABEL = {"erori": None, "program": None}


def _tabel_erori():
	if _TABEL["erori"] is None:
		tabel = {}
		try:
			from enigma import eDVBServicePMTHandler as P
			for nume, cod in NUME_EVENIMENTE:
				val = getattr(P, nume, None)
				if val is not None:
					tabel[val] = cod
			_TABEL["program"] = getattr(P, "eventNewProgramInfo", None)
		except Exception:
			tabel = {}
		_TABEL["erori"] = tabel
	return _TABEL["erori"]


# ---------------------------------------------------------------- cautarea din nou pe transponderul canalului

# campul din eDVBFrontendParameters* <- cheia din datele transponderului (sTransponderData / getTransponderData:
# frecventa in kHz, rata de simbol in simboluri pe secunda, ca in lamedb); cheile obligatorii sunt primele
CAMPURI_TP = {
	"s": (("frequency", "frequency"), ("symbol_rate", "symbol_rate"), ("polarisation", "polarization"),
		("orbital_position", "orbital_position"), ("fec", "fec_inner"), ("inversion", "inversion"), ("system", "system"),
		("modulation", "modulation"), ("rolloff", "rolloff"), ("pilot", "pilot")),
	"c": (("frequency", "frequency"), ("symbol_rate", "symbol_rate"), ("modulation", "modulation"),
		("fec_inner", "fec_inner"), ("inversion", "inversion")),
}
OBLIGATORII_TP = {"s": 4, "c": 2}


def parametri_transponder(tp, fel, clasa=None):
	"""Parametrii pentru ServiceScan ai transponderului canalului (satelit sau cablu), sau None cand lipsesc datele.
	`clasa` se da in probe; altfel eDVBFrontendParametersSatellite / Cable din enigma2."""
	campuri = CAMPURI_TP.get(fel)
	if not campuri or not isinstance(tp, dict):
		return None
	if clasa is None:
		try:
			import enigma
			clasa = enigma.eDVBFrontendParametersSatellite if fel == "s" else enigma.eDVBFrontendParametersCable
		except (ImportError, AttributeError):
			return None
	parm = clasa()
	for i, (camp, cheie) in enumerate(campuri):
		try:
			v = int(tp.get(cheie))
		except (TypeError, ValueError):
			if i < OBLIGATORII_TP[fel]:
				return None
			continue
		if i < 2 and v <= 0:
			return None
		setattr(parm, camp, v)
	return parm


# ---------------------------------------------------------------- cadrele decodorului (HiSilicon)

HISI_DIR = "/proc/hisi/msp"
HISI_VDEC = HISI_DIR + "/vdec%02d"
_HISI = {"are": None}


def hisilicon():
	"""True pe receptoarele cu decodorul HiSilicon care arata starea in /proc/hisi/msp (citit o singura data)."""
	if _HISI["are"] is None:
		try:
			_HISI["are"] = os.path.isdir(HISI_DIR)
		except Exception:
			_HISI["are"] = False
	return _HISI["are"]


def cadre_din_text(text):
	"""(ruleaza, cadre) din textul unui /proc/hisi/msp/vdecNN: „Work State: RUN” si numarul OK din randul
	„AcquireFrame(Try/OK)” de dupa „VFMW->VPSS” (cadrele iesite din decodor), sau None cand textul nu le are."""
	if not text:
		return None
	i = text.find("VFMW->VPSS")
	if i < 0:
		return None
	j = text.find("AcquireFrame", i)
	if j < 0:
		return None
	sfarsit = text.find("\n", j)
	rand = text[j:sfarsit if sfarsit > 0 else len(text)]
	try:
		valoare = rand.split(":", 1)[1].strip()
		ok = int(valoare.split("/")[1].strip())
	except (IndexError, ValueError):
		return None
	k = text.find("Work State")
	ruleaza = True
	if k >= 0:
		sf = text.find("\n", k)
		ruleaza = "RUN" in text[k:sf if sf > 0 else len(text)]
	return ruleaza, ok


def cadre_hisilicon(citeste=None):
	"""Cadrele iesite din decodoarele video (suma vdec00 si vdec01), sau None cand nu se pot citi (fisierele lipsesc sau firul de
	citire e ocupat: dupa un flux de internet driverul poate tine citirea cat se inchide playerul). Un decodor oprit isi pastreaza
	contorul in suma (PRN, masurat pe receptor: la zap decodorul trece RUN 1 -> STOP 1 -> RUN 1; fara el suma era 1 -> 0 -> 1, iar 0 -> 1 parea un
	cadru nou si fondul negru VUZ se ascundea pe un canal fara semnal); el nu creste, deci nu aduce cadre noi.
	Inainte, necititul dadea 0, adica "nicio imagine", si aparea "Fara imagine" peste un canal cu imagine buna.
	Fara citeste (pe receptor): amandoua fisierele intr-o singura cerere catre firul de fundal (_citeste_vdec_direct)."""
	if citeste is None:
		citeste = (_procFundal(_citeste_vdec_direct, HISI_DIR) or {}).get
	total = 0
	gasit = False
	for n in (0, 1):
		rez = cadre_din_text(citeste(HISI_VDEC % n))
		if rez is None:
			continue
		gasit = True
		total += rez[1]
	if not gasit:
		return None
	return total


def _procFundal(functie, *argumente):
	# fisierele driverului (/proc/msp, /proc/hisi), citite de pe firul principal: prin firul de fundal
	# (Components/HdsProcFundal.py); fara modul (probele de pe PC), direct
	try:
		from Components import HdsProcFundal
	except Exception:
		return functie(*argumente)
	return HdsProcFundal.citeste(functie, *argumente)


def _citeste_proc_direct(cale):
	try:
		with open(cale, "rb") as f:
			return f.read(8192).decode("latin-1")
	except (IOError, OSError):
		return None


def _citeste_proc(cale):
	"""Ca _citeste_proc_direct; fisierele driverului (/proc/msp, /proc/hisi) le citeste pe firul de fundal."""
	return _procFundal(_citeste_proc_direct, cale)


def _citeste_vdec_direct(dosar):
	"""{HISI_VDEC % n: text} pentru vdec00 si vdec01 din dosar, numai cele care exista. Ruleaza pe firul de fundal: o
	singura cerere la pasul urmaritorului in loc de doua (pe Octagon SF8008, sub incarcarea obisnuita, un fir nou pornit
	si asteptat costa ~1,6 ms, citirea lui vdec00 ~0,8 ms; vdec01 apare numai cu imaginea in imagine, iar fara el se
	pornea degeaba al doilea fir la fiecare pas). Cheile sunt caile din HISI_VDEC,
	ca cadre_hisilicon sa le caute la fel ca pana acum."""
	rez = {}
	for n in (0, 1):
		cale = os.path.join(dosar, "vdec%02d" % n)
		if not os.path.exists(cale):
			continue
		text = _citeste_proc_direct(cale)
		if text is not None:
			rez[HISI_VDEC % n] = text
	return rez


# ---------------------------------------------------------------- setarea si starea pentru web

_STARE = {"verdict": None, "vizibil": False, "la": 0.0, "legatura": None}


def pornit():
	"""Mesajul de pe mijlocul ecranului e pornit (setarea; implicit da)."""
	try:
		from Components.config import config
		return bool(config.usage.hds_ecran_negru.value)
	except (ImportError, AttributeError, KeyError):
		return True


def analiza_automata():
	"""Analiza fluxului porneste singura cand apare „Serviciu de date” / „format necunoscut” (setarea; implicit nu:
	citirea bruta din demux se face numai la cererea omului)."""
	try:
		from Components.config import config
		return config.usage.hds_analiza_flux.value == ANALIZA_AUTOMAT
	except (ImportError, AttributeError, KeyError):
		return False


def analiza_pentru(sref):
	"""Ce stie analiza fluxului despre serviciul `sref` (Components/HdsAnalizaFlux.pentru_verdict), sau None."""
	if not sref:
		return None
	try:
		from Components import HdsAnalizaFlux
		return HdsAnalizaFlux.pentru_verdict(sref)
	except Exception as e:
		print("[HdsEcranNegru] analiza fluxului: %s" % e)
		return None


def video_necunoscut_din(text):
	"""Pista video necunoscuta numita de nucleu (textul iServiceInformation.sPisteNecunoscute), sau None."""
	if not text:
		return None
	try:
		from Components import HdsAnalizaFlux
		return HdsAnalizaFlux.video_necunoscut_din_nucleu(text)
	except Exception as e:
		print("[HdsEcranNegru] pistele necunoscute: %s" % e)
		return None


def initConfig():
	"""config.usage.hds_ecran_negru, config.usage.hds_analiza_flux si SystemInfo["HdsEcranNegru"] (randurile din
	setup.xml). Se poate chema de mai multe ori."""
	try:
		from Components.config import config, ConfigYesNo
		try:
			config.usage.hds_ecran_negru
		except (KeyError, AttributeError):
			# ConfigSubsection da KeyError (nu AttributeError) pentru o cheie care lipseste, deci nu merge hasattr
			config.usage.hds_ecran_negru = ConfigYesNo(default=True)
	except Exception as e:
		print("[HdsEcranNegru] setarea: %s" % e)
	try:
		from Components.config import config, ConfigSelection
		try:
			config.usage.hds_analiza_flux
		except (KeyError, AttributeError):
			# textele raman netraduse: setarea se face la pornire, inainte ca limba sa fie activa, iar ConfigSelection
			# si pagina web le traduc la afisare
			config.usage.hds_analiza_flux = ConfigSelection(default=ANALIZA_OK, choices=list(ALEGERI_ANALIZA))
	except Exception as e:
		print("[HdsEcranNegru] setarea analizei: %s" % e)
	# pasii decriptarii sub mesajul canalului criptat (setup.xml, langa randurile de mai sus), oprita din fabrica
	try:
		from Components import HdsPasiDecriptare
		HdsPasiDecriptare.initConfig()
	except Exception as e:
		print("[HdsEcranNegru] setarea pasilor decriptarii: %s" % e)
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsEcranNegru"] = True
	except Exception:
		pass


def pune_stare(verdict, vizibil):
	_STARE["verdict"] = verdict
	_STARE["vizibil"] = bool(vizibil)
	_STARE["la"] = time.time()


def pune_legatura(leg):
	"""Legatura noua (sau niciuna): verdictul vechi nu mai spune nimic pana la prima fotografie a ei."""
	_STARE["legatura"] = leg
	_STARE["verdict"] = None
	_STARE["vizibil"] = False


def ultima_stare():
	"""Ce stie televizorul acum: {"verdict": dict | None, "vizibil": bool, "pornit": bool, "urmarit": bool}."""
	leg = _STARE["legatura"]
	if leg is not None:
		try:
			leg.actualizeazaAcum()
		except Exception as e:
			print("[HdsEcranNegru] web: %s" % e)
	return {"verdict": _STARE["verdict"], "vizibil": _STARE["vizibil"], "pornit": pornit(), "urmarit": leg is not None}


def fapta_web(fapta):
	"""Fapta ceruta din web pe televizor: (cod HTTP, mesaj). Numai fapta verdictului de acum sau „ascunde”."""
	leg = _STARE["legatura"]
	if leg is None:
		return 409, _t("Mesajul de pe televizor nu e pornit pe acest receptor.")
	return leg.faptaDinWeb(fapta)


# ---------------------------------------------------------------- urmaritorul (pe receptor)

# PTS-ul s-a vazut miscandu-se pe acest receptor in pornirea de acum: abia atunci contorul din PTS e o masura sigura
_PTS = {"dovedit": False}


class CadreDinPts(object):
	"""Contorul de cadre al placilor fara contorul HiSilicon, facut din PTS-ul video (aceeasi forma ca cadre_hisilicon,
	pentru Urmaritor.imagine): creste cu 1 la fiecare citire cu PTS diferit de citirea buna de dinainte. citeste() -> PTS
	(>= 0), -1 (decodorul nu da PTS), -2 (fara decodor) sau None (fara serviciu, raspuns ciudat). Intoarce None cat PTS-ul nu
	s-a vazut miscandu-se pe receptor (_PTS) sau cand citirea nu spune nimic; -1 si -2 nu adauga nimic (niciun cadru nou)."""

	def __init__(self, citeste):
		self.citeste = citeste
		self.n = 0
		self.ultim = None

	def dinNou(self):
		"""Canal nou: prima citire numai se tine minte (PTS-ul canalului dinainte nu e un cadru nou)."""
		self.ultim = None

	def __call__(self):
		v = self.citeste()
		if type(v) is not int or v < -2:
			return None
		if v >= 0:
			if self.ultim is not None and v != self.ultim:
				self.n += 1
				_PTS["dovedit"] = True
			self.ultim = v
		return self.n if _PTS["dovedit"] else None


def _monoton():
	try:
		return time.monotonic()
	except AttributeError:
		return time.time()


class _Sursa(object):
	"""Ce asteapta HdsCommon.Reader de la o sursa: serviciul si referinta."""

	def __init__(self, service, ref):
		self.service = service
		self.serviceref = ref


class Urmaritor(object):
	"""Culege fotografia si da verdictul prin `schimbat(verdict)`; eTimer-ul merge numai cat e ceva de urmarit."""

	def __init__(self, session, schimbat, infobar=None, ceas=None, cadre=None, fond=None):
		self.session = session
		self.schimbat = schimbat
		self.infobar = infobar
		self.ceas = ceas or _monoton
		self.cadre = cadre if cadre is not None else (cadre_hisilicon if hisilicon() else CadreDinPts(self._citestePts))
		# fondul negru: fond(stare) la fiecare pas, cu stare "negru" / "asteapta" / None (stareFond)
		self.fond = fond
		self.stare_fond = None
		# masura de la ultimul imagine(): contorul a spus ceva (nu evenimentul sau inaltimea)
		self.sigur = False
		self.pornit_la = self.ceas()
		self.cadre_prev = None
		self.cadre_la = -1.0
		self.video_ev = False
		# serviciul s-a oprit (evEnd): prima fotografie cu serviciu porneste socoteala de la capat, si cand acelasi
		# canal porneste din nou fara laStart
		self.oprit = False
		self.verdict = None
		self.pas = 0
		self.timer = None

	# ---- evenimentele serviciului (InfoBarGenerics)

	def _dinNou(self, acum):
		self.pornit_la = acum
		self.cadre_prev = None
		self.cadre_la = -1.0
		self.video_ev = False
		self.oprit = False
		dinNou = getattr(self.cadre, "dinNou", None)
		if dinNou is not None:
			dinNou()

	def laStart(self):
		self._dinNou(self.ceas())
		_cam_start()
		self._planifica(500)

	def laEveniment(self, nume):
		if nume == "evVideoSizeChanged":
			self.video_ev = True
		elif nume == "evEnd":
			self.oprit = True
			self._planifica(300)
			return
		self._planifica(200)

	def acum(self):
		self._planifica(0)

	def opreste(self):
		if self.timer is not None:
			self.timer.stop()

	def _planifica(self, ms):
		if self.timer is None:
			try:
				from enigma import eTimer
			except ImportError:
				return
			self.timer = eTimer()
			self.timer.callback.append(self._pas)
		self.pas = ms
		self.timer.start(max(0, int(ms)), True)

	def _pas(self):
		try:
			v, urmarit, vine = self.calculeaza()
		except Exception as e:
			print("[HdsEcranNegru] %s: %s" % (type(e).__name__, e))
			v, urmarit, vine = None, False, False
		if v != self.verdict:
			self.verdict = v
			try:
				self.schimbat(v)
			except Exception as e:
				print("[HdsEcranNegru] fereastra: %s: %s" % (type(e).__name__, e))
		if self.fond is not None:
			try:
				self.fond(self.stare_fond if urmarit else None)
			except Exception as e:
				print("[HdsEcranNegru] fondul: %s: %s" % (type(e).__name__, e))
		if urmarit:
			self._planifica(PAS_IMAGINE_MS if (vine and v is None) else PAS_ASTEPTARE_MS)

	def calculeaza(self):
		"""(verdict, mai e de urmarit, imaginea vine)."""
		self.sigur = False
		d = self.fotografie()
		v = analizeaza(d)
		self.stare_fond = self.stareFond(d)
		urmarit = not d.get("nimic") and not d.get("radio") and (d.get("fel") in FEL_DVB or bool(d.get("flux_dvb")))
		if d.get("flux_gst") and not d.get("nimic"):
			# fluxul prin GStreamer: cat nu vine imaginea, cel mult URMARIRE_FLUX_S fara verdict (evenimentele il pornesc din nou)
			urmarit = d.get("imagine") is not True and (v is not None or (d.get("secunde") or 0.0) < URMARIRE_FLUX_S)
		return v, urmarit, d.get("imagine") is True

	# ---- imaginea

	def imagine(self, acum, inaltime):
		"""(imaginea vine: True / False, secunde fara imagine). self.sigur: raspunsul vine din contorul de cadre."""
		self.sigur = False
		if self.cadre is not None:
			n = self.cadre()
			if n is not None:
				if self.cadre_prev is not None and n > self.cadre_prev:
					self.cadre_la = acum
				self.cadre_prev = n
				vazut = self.cadre_la >= self.pornit_la
				if not vazut and self.video_ev:
					# marimea imaginii a venit dupa pornire, dar contorul nu s-a miscat deloc: contorul nu spune nimic despre acest decodor
					# (de pilda dupa un flux de internet); fara cadre deloc nu vine nici marimea, deci nu e ecran negru
					return True, 0.0
				self.sigur = True
				baza = self.cadre_la if vazut else self.pornit_la
				return (vazut and acum - self.cadre_la < PRAG_CADRE), max(0.0, acum - baza)
		vazut = self.video_ev or inaltime > 0
		return vazut, (0.0 if vazut else max(0.0, acum - self.pornit_la))

	def cadreNoi(self):
		"""Numai contorul, fara fotografie (fondul negru il intreaba la PAS_FOND_MS cat se vede): True cand au venit cadre
		noi de la pornirea canalului, False cand nu, None cand contorul nu spune nimic."""
		if self.cadre is None:
			return None
		n = self.cadre()
		if n is None:
			return None
		if self.cadre_prev is not None and n > self.cadre_prev:
			self.cadre_la = self.ceas()
		self.cadre_prev = n
		return self.cadre_la >= self.pornit_la

	def stareFond(self, d):
		"""Fondul negru pentru fotografia d: "negru" (canal TV prin DVB, masura sigura, niciun cadru nou de PRAG_FOND
		secunde de la pornire), "asteapta" (la fel, dar mai devreme: fondul ramane cum e), "nestiut" (canal TV prin DVB,
		masura nesigura acum: pe HiSilicon contorul nu se poate citi chiar in timpul zap-ului; fondul nu se pune, iar unul
		vazut ramane cel mult Screens/HdsEcranNegru.FOND_NESTIUT_S), None (nu se pune: cadre noi, radio, pauza, PiP,
		fisier, flux, nimic redat)."""
		if not d or d.get("nimic") or d.get("radio") or d.get("pauza") or d.get("pip") or d.get("fel") not in FEL_DVB:
			return None
		if self.cadre_la >= self.pornit_la:
			return None
		if not self.sigur:
			return "nestiut"
		return "negru" if (d.get("secunde") or 0.0) >= PRAG_FOND else "asteapta"

	def _citestePts(self):
		"""PTS-ul video al canalului redat (lib/service/servicedvb.cpp getInfo(sUser + INFO_PTS)), sau None."""
		try:
			from enigma import iServiceInformation
			service = self.session.nav.getCurrentService()
			info = service.info() if service is not None else None
			if info is None:
				return None
			return info.getInfo(iServiceInformation.sUser + INFO_PTS)
		except Exception:
			return None

	def inPauza(self):
		ib = self.infobar
		if ib is None:
			return False
		stare = getattr(ib, "seekstate", None)
		joc = getattr(ib, "SEEK_STATE_PLAY", None)
		return stare is not None and joc is not None and stare != joc

	# ---- fotografia

	def fotografie(self):
		acum = self.ceas()
		nav = self.session.nav
		service = nav.getCurrentService()
		ref = nav.getCurrentlyPlayingServiceReference()
		if service is None or ref is None:
			_pasi_uita()
			if _in_standby():
				# in standby nu e nimic de explicat (nici pe televizor, nici in web)
				return {"nimic": True, "blocat": False, "canal": u""}
			blocat, nume = _blocat_parinti(self.infobar)
			return {"nimic": True, "blocat": blocat, "canal": nume}
		if self.oprit:
			self._dinNou(acum)
		from Components.Converter import HdsCommon as C
		r = C.Reader(_Sursa(service, ref), None)
		sref = r.sref() or ref.toString()
		pr = C.parse_ref(sref)
		d = {"ref": sref, "tip_serviciu": pr["stype"], "fel": r.kind(), "secunde": acum - self.pornit_la,
			"pauza": self.inPauza(), "pip": bool(getattr(self.session, "pipshown", False))}
		d["radio"] = pr["stype"] in RADIO_STYPES or r.is_dab() or _radio_vizibil()
		if not d["radio"] and d["fel"] == FEL_FLUX:
			# un post de radio de pe internet (adresa de sunet, ca la bara: HdsInfo._radio_calc), si cu ecranul radio oprit
			try:
				d["radio"] = bool(C.is_audio_url(r.ref().get("path") or u""))
			except Exception:
				pass
		info = r.info()
		d["canal"] = _curat(info.getName() if info is not None else u"")
		if d["fel"] == FEL_FLUX and not d["radio"] and r.ref().get("type") == 1:
			# fluxul IP redat prin servicedvb (tipul 1; 4097 si celelalte merg prin GStreamer, cu mesajele lor din
			# HdsFilmRedare): numai cat trebuie pentru formatul numit (PMT citit, pistele, textul nucleului) si
			# imaginea, ca urmarirea sa se rareasca la PAS_IMAGINE_MS cand imaginea vine
			d["flux_dvb"] = True
			_pasi_uita()
			d["imagine"], d["negru_de"] = self.imagine(acum, r.geti("sVideoHeight"))
			eroare_acordare(r.geti("sDVBState"))
			program = _TABEL["program"]
			d["pmt"] = (program is not None and r.geti("sDVBState") == program) or r.geti("sIsCrypted") in (0, 1)
			d["video_pid"] = r.geti("sVideoPID")
			d["audio_pid"] = r.geti("sAudioPID")
			if d["video_pid"] is None or d["video_pid"] <= 0:
				d["video_necunoscut"] = video_necunoscut_din(r.gets("sPisteNecunoscute"))
			return d
		if d["fel"] == FEL_FLUX and not d["radio"]:
			# fluxul prin GStreamer (4097, 5001, 5002): numai cat trebuie pentru „numai sunet”, fara tuner si fara PMT
			d["flux_gst"] = True
			_pasi_uita()
			inaltime = r.geti("sVideoHeight")
			vazut = self.video_ev or inaltime > 0
			d["imagine"], d["negru_de"] = vazut, (0.0 if vazut else max(0.0, acum - self.pornit_la))
			d["piste_video"] = _piste_video(info)
			d["piste_audio"] = _piste_audio(service)
			d["codec_video"] = bool(r.gets("sTagVideoCodec"))
			return d
		if d["radio"] or d["fel"] not in FEL_DVB:
			_pasi_uita()
			return d
		d["furnizor"] = r.gets("sProvider")
		stare_dvb = r.geti("sDVBState")
		d["eroare"] = eroare_acordare(stare_dvb)
		if d["eroare"] == E_FARA_PAT:
			d["t2_criptat"] = t2_releu_criptat(sref)
			d["t2_porneste"] = t2_releu_porneste(sref)
		if d["eroare"] == E_CONFIGURARE and d["fel"] == "s":
			d["loc_nestabilit"] = loc_nestabilit(sref)
			d["sub_orizont"] = sub_orizont(sref)
			d["multistream_fara_tuner"] = multistream_fara_tuner(sref, r.tp())
		program = _TABEL["program"]
		d["pmt"] = (program is not None and stare_dvb == program) or r.geti("sIsCrypted") in (0, 1)
		d["video_pid"] = r.geti("sVideoPID")
		d["audio_pid"] = r.geti("sAudioPID")
		d["caids"] = C._service_caids(r)
		d["criptat"] = r.crypted()
		if d["criptat"]:
			d["sisteme"] = [g[0] for g in C.group_caids(d["caids"])]
			d["ecm"] = C.ecm_active(r)
			d["icam_fara_modul"] = _icam_fara_modul(ref, d["caids"])
		# imaginea intai: cand vine, analizeaza() nu se uita la semnal, deci starea tunerului nu se cere (pe Vu+ fiecare
		# citire e un ioctl pe I2C, cu firul principal blocat cat dureaza; paznicul ruleaza la 2 s cat omul se uita la TV)
		d["imagine"], d["negru_de"] = self.imagine(acum, r.geti("sVideoHeight"))
		if d["imagine"] is True:
			d["lock"], d["nivel"], d["calitate"], d["stare_tuner"] = -1, -1, -1, u""
		else:
			fe = C.frontend_status(service, sref, ("lock", "power", "quality")) or {}
			d["lock"] = fe.get("lock", -1)
			d["nivel"] = C.percent16(fe.get("power", -1))
			d["calitate"] = C.percent16(fe.get("quality", -1))
			d["stare_tuner"] = C.tuner_state(service, sref)
		tp = r.tp()
		d["tp_text"] = C.tp_line(tp, d["fel"], True)
		d["tp_cautare"] = bool(tp) and C.ival(tp, "frequency") > 0
		numar = C.fe_number(r)
		d["tuner"] = u"%c" % (65 + numar) if 0 <= numar <= 25 else u""
		if d["fel"] == "s":
			d["rotor"] = C.rotor_position()[1] and not readucere_in_curs()
			if d["rotor"]:
				poz = C.ival(tp, "orbital_position")
				d["rotor_spre"] = C.sat_full(poz) if poz >= 0 else u""
				d["rotor_plecare_nestiuta"] = plecare_nestiuta()
			d["tp_nu_emite"] = transponder_nu_emite()
			d["alt_satelit"] = _alt_satelit(d, tp, C, acum)
		if d["eroare"] == E_FARA_TUNER:
			d["inregistrari"] = _inregistrari(nav)
		if d["video_pid"] is None or d["video_pid"] <= 0:
			d["analiza"] = analiza_pentru(sref)
			d["video_necunoscut"] = video_necunoscut_din(r.gets("sPisteNecunoscute"))
		# pasii decriptarii (Components/HdsPasiDecriptare.py): numai cu setarea lor pornita, altfel nicio citire in plus
		pasi = _pasi_noteaza(r, C, d, self.pornit_la, acum)
		if pasi:
			d["pasi"] = pasi
		return d


def plecare_nestiuta():
	"""True cand motorul care se misca acum are tinta stiuta si plecarea nestiuta (sec.cpp: curRotorPos = -1, dupa
	pornire, dupa flash sau dupa o pozitie uitata; hdsRotorFromOrbital, aceeasi sursa ca Components/HdsMotorStare.py)"""
	try:
		from enigma import eDVBSatelliteEquipmentControl
		sec = eDVBSatelliteEquipmentControl.getInstance()
		slot = int(sec.hdsRotorMovingSlot())
		return slot >= 0 and int(sec.hdsRotorFromOrbital(slot)) < 0 and int(sec.hdsRotorToOrbital(slot)) >= 0
	except Exception:
		return False


def readucere_in_curs():
	"""True cat merge mutarea readucerii antenei dupa pierderea semnalului (Components/HdsMotorStare.readucereInCurs):
	mesajul ramane Fara semnal, ca pana atunci"""
	import sys
	m = sys.modules.get("Components.HdsMotorStare")
	f = getattr(m, "readucereInCurs", None) if m is not None else None
	try:
		return bool(f()) if f is not None else False
	except Exception:
		return False


def transponder_nu_emite():
	"""transponderul prins de verificarea readucerii cand antena e la locul ei si transponderul canalului nu emite
	(Components/HdsMotorPozitie.transponderNuEmite), altfel "" (fara import: fara motor modulul nu e incarcat)"""
	import sys
	m = sys.modules.get("Components.HdsMotorPozitie")
	f = getattr(m, "transponderNuEmite", None) if m is not None else None
	try:
		return f() if f is not None else u""
	except Exception:
		return u""


# ---------------------------------------------------------------- antena pe alt satelit
# AS26 (asistenta de la distanta, GigaBlue UHD Quad 4K Pro): tunerul A setat corect pe 42,0E prindea doua
# frecvente (12207 H si 12245 H, SNR 55-57 %), dar fluxurile nu aveau canalele din lista (eventNoPATEntry), iar celelalte nu
# aveau purtatoare: antena din mufa A era pe alt satelit. Ecranul spunea "Postul nu mai emite pe aceasta frecventa" si "Fara
# semnal", deci omul n-avea de unde sti. Un singur transponder cu SID negasit poate fi un post mutat; doua sau mai multe
# transpondere diferite ale aceluiasi satelit, pe acelasi tuner, prinse cu fluxuri fara canalele din lista, in STRAIN_S
# secunde si fara nicio imagine pe acel satelit intre timp, arata antena (sau cablul) pe alt satelit. Atunci mesajul de
# SID negasit si cel de fara semnal pentru canalele acelui satelit pe acel tuner spun asta. Codul verdictului ramane cel
# vechi (POST_MUTAT, FARA_SEMNAL): rezerva DVB-I (Components/HdsDvbIRezerva.py) si web-ul il folosesc neschimbat; fapta
# trece pe setarile tunerului, fiindca o cautare pe transponder cu antena pe alt satelit ar baga in lista canale straine.
STRAIN_S = 15 * 60      # cat se tine minte un transponder prins cu flux strain
STRAIN_MIN = 2          # de la cate transpondere diferite se spune ca antena e pe alt satelit
MAX_STRAINE_DETALIU = 3
POLARIZARI = (u"H", u"V", u"L", u"R")   # eDVBFrontendParametersSatellite.Polarisation_*
_STRAINE = {}           # (orbital, tuner) -> {cheia transponderului: (moment, textul transponderului)}


def flux_strain_noteaza(orbital, tuner, cheie, text, acum):
	"""Transponderul `cheie` al satelitului `orbital`, pe tunerul `tuner`, s-a prins cu un flux fara canalul cerut."""
	_STRAINE.setdefault((orbital, tuner or u""), {})[cheie] = (acum, text or u"")


def flux_strain_uita(orbital):
	"""O imagine pe satelitul `orbital`: antena e la locul ei, deci nimic din ce s-a notat pentru el nu mai conteaza."""
	for k in [k for k in _STRAINE if k[0] == orbital]:
		del _STRAINE[k]


def flux_strain(orbital, tuner, acum):
	"""Textele transponderelor straine ale satelitului pe tuner, cele mai vechi intai, cand sunt cel putin STRAIN_MIN in
	ultimele STRAIN_S secunde; altfel lista goala."""
	tp = _STRAINE.get((orbital, tuner or u""))
	if not tp:
		return []
	for cheie in [c for c, (t, _x) in tp.items() if acum - t > STRAIN_S or acum < t]:
		del tp[cheie]
	if len(tp) < STRAIN_MIN:
		return []
	return [x for _t0, x in sorted(tp.values())]


def _alt_satelit(d, tp, C, acum):
	"""{"sat", "tuner", "tp"} cand antena tunerului pare pe alt satelit (vezi mai sus), altfel None. Noteaza fotografia."""
	if d.get("fel") != "s" or not tp:
		return None
	poz = C.ival(tp, "orbital_position")
	if poz < 0:
		return None
	if d.get("imagine") is True:
		flux_strain_uita(poz)
		return None
	tuner = d.get("tuner") or u""
	if d.get("eroare") == E_FARA_SID and semnal_prins(d.get("lock", -1), d.get("stare_tuner")) is True:
		frecventa = C.ival(tp, "frequency")
		if frecventa > 0:
			mhz, pol = int(round(frecventa / 1000.0)), C.ival(tp, "polarization")
			text = u"%d %s" % (mhz, POLARIZARI[pol]) if 0 <= pol < len(POLARIZARI) else u"%d" % mhz
			flux_strain_noteaza(poz, tuner, "%d:%d" % (mhz, pol), text, acum)
	straine = flux_strain(poz, tuner, acum)
	if not straine:
		return None
	return {"sat": C.sat_full(poz), "tuner": tuner, "tp": straine}


def _verdict_alt_satelit(cod, d, bare=False):
	a = d["alt_satelit"]
	tuner = _curat(a.get("tuner") or u"A", 4)
	sat = _curat(a.get("sat") or u"", 60)
	tp = u", ".join(_curat(x, 48) for x in (a.get("tp") or [])[:MAX_STRAINE_DETALIU])
	return _verdict(cod, d, text=_t(T_ALT_SAT) % (tuner, sat, tuner), titlu=_t(T_ALT_SAT_TITLU), fapta=F_TUNER,
		detaliu=_detaliu(_t(D_ALT_SAT) % (tuner, tp)), bare=bare)


def loc_nestabilit(sref):
	"""True cand satelitul canalului se prinde numai cu motorul USALS si locul antenei nu e stabilit: nucleul nu are
	satelitul (NimManager.SecConfigure), deci acordul cade ca la o configurare gresita (eventMisconfiguration)"""
	try:
		from Components import HdsLocul
		orbital = HdsLocul.orbitalDinReferinta(sref)
		return orbital is not None and HdsLocul.blocatDeLoc(orbital)
	except Exception as e:
		print("[HdsEcranNegru] locul antenei: %s" % e)
		return False


def sub_orizont(sref):
	"""True cand satelitul canalului se prinde numai cu motorul USALS si e sub orizont din locul antenei stabilit: nucleul
	nu are satelitul (NimManager.SecConfigure, hdsSubOrizont), deci acordul cade ca la o configurare gresita"""
	try:
		from Components import HdsLocul
		orbital = HdsLocul.orbitalDinReferinta(sref)
		return orbital is not None and HdsLocul.blocatDeOrizont(orbital)
	except Exception as e:
		print("[HdsEcranNegru] satelitul sub orizont: %s" % e)
		return False


ISI_MAX = 255


def _int(v, implicit):
	try:
		return int(v)
	except (TypeError, ValueError):
		return implicit


def cere_tuner_multistream(tp):
	"""True cand transponderul (datele din lamedb: is_id, pls_mode, pls_code) are nevoie de un tuner care alege fluxul:
	un flux 1..255, sau o secventa PLS aleasa. Fluxul 0 cu secventa implicita (coada ":0:0:1" scrisa de listele facute pe
	alte imagini) nu cere asa ceva. Aceeasi regula ca nucleul (lib/dvb/hdsmultistream.h, cereTunerMultistream)."""
	if not isinstance(tp, dict):
		return False
	isi = _int(tp.get("is_id"), -1)
	if not 0 <= isi <= ISI_MAX:
		isi = -1
	mod, cod = _int(tp.get("pls_mode"), 1) & 3, _int(tp.get("pls_code"), 0) & 0x3FFFF
	if mod == 0:
		implicit = cod in (0, 1)
	elif mod in (1, 2):
		implicit = cod == 0
	else:
		implicit = False
	if isi == -1:
		return not implicit
	return not (isi == 0 and implicit)


def _text_flux(tp):
	"""flux 5, "flux 0, PLS Gold 8", "PLS Root 262141": ce cere transponderul, pentru detaliul tehnic."""
	parti = []
	isi = _int(tp.get("is_id"), -1)
	if 0 <= isi <= ISI_MAX:
		parti.append(u"flux %d" % isi)
	mod, cod = _int(tp.get("pls_mode"), 1) & 3, _int(tp.get("pls_code"), 0) & 0x3FFFF
	if not ((mod == 0 and cod in (0, 1)) or (mod in (1, 2) and cod == 0)):
		parti.append(u"PLS %s %d" % ({0: u"Root", 1: u"Gold", 2: u"Combo"}.get(mod, u"?"), cod))
	return u", ".join(parti)


def _tp_din_referinta(sref):
	"""Datele transponderului din lamedb pentru referinta (fara tuner: eStaticServiceDVBInformation), sau {}."""
	try:
		from enigma import eServiceCenter, iServiceInformation
		info = eServiceCenter.getInstance().info(sref)
		tp = info.getInfoObject(sref, iServiceInformation.sTransponderData) if info else None
		return tp if isinstance(tp, dict) else {}
	except Exception:
		return {}


def multistream_fara_tuner(sref, tp=None, nim=None):
	"""La o configurare gresita (eventMisconfiguration) pe satelit: {"flux", "tunere", "alt_tuner"} cand satelitul canalului
	e setat pe cel putin un tuner, transponderul cere un tuner care alege fluxul si niciunul din tunerele setate pe satelit
	nu are multistream (lib/dvb/frontend.cpp, isCompatibleWith, il refuza); "alt_tuner" = receptorul are totusi un tuner
	cu multistream, nesetat pe satelit. Altfel None (mesajul ramane "Tunerul nu e setat pentru acest canal")."""
	try:
		from Components import HdsLocul
		orbital = HdsLocul.orbitalDinReferinta(sref)
		if orbital is None:
			return None
		if not tp:
			tp = _tp_din_referinta(sref)
		if not cere_tuner_multistream(tp):
			return None
		if nim is None:
			from Components.NimManager import nimmanager as nim
		setate = nim.getNimListForSat(orbital)
		if not setate:
			return None
		if any(nim.nim_slots[s].isMultistream() for s in setate):
			return None
		alt = any(t.isMultistream() for t in nim.nim_slots if t.slot not in setate)
		litere = u", ".join(u"%c" % (65 + s) if 0 <= s <= 25 else u"%d" % s for s in setate)
		return {"flux": _text_flux(tp), "tunere": litere, "alt_tuner": bool(alt)}
	except Exception as e:
		print("[HdsEcranNegru] multistream fara tuner: %s" % e)
		return None


def _pasi_noteaza(r, C, d, t0, acum):
	"""Randurile pasilor decriptarii pentru canalul DVB redat (HdsPasiDecriptare.noteaza_din), sau None cand setarea
	lor e oprita (atunci nu se citeste nimic in plus)."""
	try:
		from Components import HdsPasiDecriptare as P
		if not P.pornit():
			return None
		return P.noteaza_din(r, C, d, t0, acum)
	except Exception as e:
		print("[HdsEcranNegru] pasii decriptarii: %s: %s" % (type(e).__name__, e))
		return None


def _pasi_uita():
	"""Pe televizor nu mai e un canal DVB (radio, fisier, flux, nimic): pasii vechi nu mai sunt ai nimanui."""
	try:
		from Components import HdsPasiDecriptare as P
		if P.jurnal_tv() is not None:
			P.uita()
	except Exception:
		pass


def _icam_fara_modul(ref, caids):
	"""Textul (netradus) al canalului ICAM cu SoftCSA negata (Components/HdsSoftCsa.canalIcamFaraSoftCsa), altfel "";
	referinta e cea din navigatie (a canalului, nu a releului). "" la o eroare."""
	try:
		from Components import HdsSoftCsa
		return HdsSoftCsa.TEXT_ICAM_CANAL if HdsSoftCsa.canalIcamFaraSoftCsa(ref.toString(), caids) else ""
	except Exception:
		return ""


def _cam_start():
	"""Pornirea serviciului, si pentru raspunsul camului (HdsCommon.ecm_active): raspunsul scris inainte e al canalului
	dinainte. Convertoarele CAM o afla singure din evStart, dar numai cand sunt treze."""
	try:
		from Components.Converter import HdsCommon as C
		C.cam_start()
	except Exception:
		pass


def _in_standby():
	try:
		from Screens.Standby import inStandby
		return inStandby is not None
	except Exception:
		return False


def _radio_vizibil():
	"""Ecranul radio se vede pe un post de radio (nu ca fundal al unui canal TV numai cu sunet)."""
	try:
		from Components.HdsRadioSetari import ecran_radio_vizibil, ecran_numai_sunet
		return bool(ecran_radio_vizibil()) and not ecran_numai_sunet()
	except Exception:
		return False


def _piste_video(info):
	"""Numarul pistelor video ale fluxului redat prin GStreamer (lib/service/servicemp3.cpp, getInfo(sUser+17)); -1 cat
	nu se stie (inainte de preroll, alt serviciu de redare, nucleu mai vechi)."""
	try:
		from enigma import iServiceInformation
		v = info.getInfo(iServiceInformation.sUser + 17) if info is not None else -1
		return int(v) if v is not None else -1
	except Exception:
		return -1


def _piste_audio(service):
	try:
		a = service.audioTracks() if service is not None else None
		return int(a.getNumberOfTracks()) if a is not None else 0
	except Exception:
		return 0


def _inregistrari(nav):
	"""Numele inregistrarilor care merg acum (cel mult zece: primele se numesc, celelalte se numara)."""
	nume = []
	try:
		for t in nav.RecordTimer.timer_list:
			if getattr(t, "justplay", False) or not t.isRunning():
				continue
			nume.append(_curat(getattr(t, "name", u""), 60))
			if len(nume) >= 10:
				break
	except Exception:
		pass
	return [n for n in nume if n]


def ref_selectata(infobar):
	"""Canalul ales ultima data in lista (cel pornit sau refuzat), ca eServiceReference, sau None."""
	lista = getattr(infobar, "servicelist", None)
	try:
		ref = lista.getCurrentSelection() if lista is not None else None
		if ref is not None and ref.valid():
			return ref
	except Exception:
		pass
	try:
		from Components.config import config
		from enigma import eServiceReference
		text = config.tv.lastservice.value
		return eServiceReference(text) if text else None
	except Exception:
		return None


def _blocat_parinti(infobar):
	"""(canalul ales e blocat cu codul pentru parinti, numele lui) cand nu merge nimic."""
	try:
		from Components.config import config
		if not (config.ParentalControl.configured.value and config.ParentalControl.servicepinactive.value):
			return False, u""
		from Components.ParentalControl import parentalControl
		ref = ref_selectata(infobar)
		if ref is None:
			return False, u""
		if parentalControl.getProtectionLevel(ref.toCompareString()) == -1:
			return False, u""
		nume = u""
		try:
			from ServiceReference import ServiceReference
			nume = ServiceReference(ref).getServiceName()
		except Exception:
			nume = u""
		return True, _curat(nume)
	except Exception:
		return False, u""
