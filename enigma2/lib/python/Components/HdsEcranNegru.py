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
# - textele: fraza simpla pe intelesul oricui, fapta (butonul) unde ajuta si detaliul tehnic, mai mic. Aceleasi texte
#   pe televizor, in ferestrele de eroare si in web.
#
# Starea pentru web (ultima_stare) si fapta ceruta din web (fapta_web) trec prin _STARE, pusa de fereastra de pe
# televizor. Setarea: config.usage.hds_ecran_negru (setup.xml, sectiunea usage), SystemInfo["HdsEcranNegru"].
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
PAS_ASTEPTARE_MS = 1000
PAS_IMAGINE_MS = 2000
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
# zap pe un satelit pe care numai motorul USALS il prinde, cu locul antenei nestabilit (Components/HdsLocul.py)
LOC_NESTABILIT = "loc_nestabilit"
ANTENA = "antena"
FARA_SEMNAL = "fara_semnal"
FRECVENTA_GOALA = "frecventa_goala"
POST_MUTAT = "post_mutat"
FARA_PMT = "fara_pmt"
FORMAT = "format"
DATE = "date"
CRIPTAT = "criptat"
FARA_IMAGINE = "fara_imagine"
CODURI = (BLOCAT, FARA_TUNER, TUNER_NESETAT, LOC_NESTABILIT, ANTENA, FARA_SEMNAL, FRECVENTA_GOALA, POST_MUTAT, FARA_PMT,
	FORMAT, DATE, CRIPTAT, FARA_IMAGINE)

# faptele (butonul de pe televizor si din web)
F_CAUTA_TP = "cauta_tp"          # cautarea din nou pe transponderul canalului
F_CAUTA = "cauta"                # ecranul de cautare al felului de receptie (satelit, cablu, terestru)
F_INREGISTRARI = "inregistrari"  # lista temporizatoarelor si inregistrarilor
F_COD = "cod"                    # codul pentru parinti, din nou
F_TUNER = "tuner"                # setarile tunerului
F_ANALIZA = "analiza"            # analiza fluxului (serviciu de date, format necunoscut)
F_LOC = "loc"                    # alegerea locului antenei (Screens/HdsLocul.py)
F_ASCUNDE = "ascunde"            # numai din web: ca EXIT pe televizor
FAPTE = (F_CAUTA_TP, F_CAUTA, F_INREGISTRARI, F_COD, F_TUNER, F_ANALIZA, F_LOC)

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
	LOC_NESTABILIT: N_("Locul antenei nu e stabilit"),
	ANTENA: N_("Antena se rotește"),
	FARA_SEMNAL: N_("Fără semnal"),
	FRECVENTA_GOALA: N_("Frecvența nu trimite nimic"),
	POST_MUTAT: N_("Postul nu mai e pe această frecvență"),
	FARA_PMT: N_("Canalul nu răspunde"),
	FORMAT: N_("Imagine într-un format necunoscut"),
	DATE: N_("Serviciu de date"),
	CRIPTAT: N_("Acces condiționat"),
	FARA_IMAGINE: N_("Fără imagine"),
}

TEXTE = {
	BLOCAT: N_("Canalul este blocat cu codul pentru părinți."),
	FARA_TUNER: N_("Tunerul este folosit acum pe altă frecvență, pentru o înregistrare sau o transmisie în rețea, și nu poate porni acest canal."),
	TUNER_NESETAT: N_("Niciun tuner nu e setat să primească acest canal. Verifică setările tunerului."),
	LOC_NESTABILIT: N_("Acest satelit se recepționează numai cu motorul USALS, iar motorul nu știe unde ești, deci antena nu se rotește. Apasă OK și alege țara și orașul."),
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
}
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
	LOC_NESTABILIT: N_("USALS fără locul antenei; nucleul nu primește satelitul"),
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
		return _format_numit(d, analiza=False)
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
	if eroare == E_CONFIGURARE and d.get("loc_nestabilit"):
		return _verdict(LOC_NESTABILIT, d, fapta=F_LOC, detaliu=_detaliu(_t(DETALII[LOC_NESTABILIT])))
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
	if eroare == E_FARA_PAT:
		return _verdict(FRECVENTA_GOALA, d, fapta=F_CAUTA, detaliu=_detaliu(_t(DETALII[FRECVENTA_GOALA])))
	if eroare == E_FARA_SID:
		return _verdict(POST_MUTAT, d, fapta=_fapta_cautare(d), detaliu=_detaliu(_t(DETALII[POST_MUTAT])))
	if eroare == E_FARA_PMT:
		return _verdict(FARA_PMT, d, fapta=_fapta_cautare(d), detaliu=_detaliu(_t(DETALII[FARA_PMT])))
	prins = semnal_prins(d.get("lock", -1), d.get("stare_tuner"))
	if (eroare == E_ACORDARE or prins is False) and secunde >= PRAG_SEMNAL:
		# numai faptele masurate (nivelul si calitatea in bare, tunerul si frecventa in detaliu), fara cauze presupuse
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
		v = _verdict(CRIPTAT, d, text=text, etichete=_etichete_criptare(d),
			detaliu=_detaliu(_caid_text(d.get("caids")), (_t(D_FURNIZOR) % furnizor) if furnizor else u""))
		# pasii decriptarii (Components/HdsPasiDecriptare.py), numai cu setarea lor pornita: randurile vii sub mesaj
		if d.get("pasi"):
			v["pasi"] = list(d["pasi"])
		return v
	return _verdict(FARA_IMAGINE, d, fapta=_fapta_cautare(d),
		detaliu=_detaliu(_t(D_PISTA_FARA_IMAGINE) % d["video_pid"]))


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
	return analizeaza({"fel": fel if fel in FEL_DVB else "s", "eroare": eroare, "secunde": PRAG_SEMNAL, "lock": -1,
		"canal": canal or u""})


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
	"""Cadrele iesite din decodoarele video care ruleaza (suma vdec00 si vdec01), sau None cand nu se pot citi.
	Un decodor oprit nu adauga nimic; fara niciun decodor se intoarce 0."""
	citeste = citeste or _citeste_proc
	total = 0
	gasit = False
	for n in (0, 1):
		rez = cadre_din_text(citeste(HISI_VDEC % n))
		if rez is None:
			continue
		gasit = True
		if rez[0]:
			total += rez[1]
	if not gasit:
		return 0
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

	def __init__(self, session, schimbat, infobar=None, ceas=None, cadre=None):
		self.session = session
		self.schimbat = schimbat
		self.infobar = infobar
		self.ceas = ceas or _monoton
		self.cadre = cadre if cadre is not None else (cadre_hisilicon if hisilicon() else None)
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
		if urmarit:
			self._planifica(PAS_IMAGINE_MS if (vine and v is None) else PAS_ASTEPTARE_MS)

	def calculeaza(self):
		"""(verdict, mai e de urmarit, imaginea vine)."""
		d = self.fotografie()
		v = analizeaza(d)
		urmarit = not d.get("nimic") and not d.get("radio") and (d.get("fel") in FEL_DVB or bool(d.get("flux_dvb")))
		return v, urmarit, d.get("imagine") is True

	# ---- imaginea

	def imagine(self, acum, inaltime):
		"""(imaginea vine: True / False, secunde fara imagine)."""
		if self.cadre is not None:
			n = self.cadre()
			if n is not None:
				if self.cadre_prev is not None and n > self.cadre_prev:
					self.cadre_la = acum
				self.cadre_prev = n
				vazut = self.cadre_la >= self.pornit_la
				baza = self.cadre_la if vazut else self.pornit_la
				return (vazut and acum - self.cadre_la < PRAG_CADRE), max(0.0, acum - baza)
		vazut = self.video_ev or inaltime > 0
		return vazut, (0.0 if vazut else max(0.0, acum - self.pornit_la))

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
		if d["radio"] or d["fel"] not in FEL_DVB:
			_pasi_uita()
			return d
		d["furnizor"] = r.gets("sProvider")
		stare_dvb = r.geti("sDVBState")
		d["eroare"] = eroare_acordare(stare_dvb)
		if d["eroare"] == E_CONFIGURARE and d["fel"] == "s":
			d["loc_nestabilit"] = loc_nestabilit(sref)
		program = _TABEL["program"]
		d["pmt"] = (program is not None and stare_dvb == program) or r.geti("sIsCrypted") in (0, 1)
		d["video_pid"] = r.geti("sVideoPID")
		d["audio_pid"] = r.geti("sAudioPID")
		d["caids"] = C._service_caids(r)
		d["criptat"] = r.crypted()
		if d["criptat"]:
			d["sisteme"] = [g[0] for g in C.group_caids(d["caids"])]
			d["ecm"] = C.ecm_active(r)
		fe = C.frontend_status(service, sref) or {}
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
		if d["eroare"] == E_FARA_TUNER:
			d["inregistrari"] = _inregistrari(nav)
		d["imagine"], d["negru_de"] = self.imagine(acum, r.geti("sVideoHeight"))
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
	try:
		from Components.HdsRadioSetari import ecran_radio_vizibil
		return bool(ecran_radio_vizibil())
	except Exception:
		return False


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
