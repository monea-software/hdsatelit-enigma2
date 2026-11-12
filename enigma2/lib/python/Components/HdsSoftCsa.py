# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSoftCsa.py: starea descifrarii in software a canalelor CSA-ALT (0.7.4), pentru Python.
#
# Descifrarea o face nucleul (lib/dvb/csasession.h, lib/dvb/cahandler.h): canalele cu ICAM (Sky Deutschland, CAID 098C /
# 098D / 09F0, algoritmul CSA-ALT, pe care descifratorul receptorului nu-l stie) se descifreaza cu libdvbcsa, iar cheile
# le da modulul de acces prin soclul /tmp/.listen.camd.socket, cu protocolul 3 (in configurarea modulului
# „pmt_mode = 6” si „extended_cw_api = 1”). Canalul se reda atunci ca oricare altul: zap direct, ghid, timeshift.
#
# stare(): dictionarul din nucleu (enigma.hdsSoftCsaStare), cu valori goale cand binarul nu are SoftCSA:
#   biblioteca / versiune: libdvbcsa incarcata si versiunea ei;
#   receptor: inregistrarea nucleului stie descifrarea pe acest receptor (pe toate: HiSilicon pe drumul lui, celelalte,
#     Broadcom ARM si MIPS, pe cel obisnuit din lib/base/filepush.cpp);
#   client / protocol / modul / extins: un modul legat pe soclul nou, protocolul lui, textul lui (SERVER_INFO), daca
#     anunta cuvintele de control extinse;
#   gata: descifrarea in software poate merge (biblioteca + modul cu protocolul 3 si cuvinte extinse);
#   conexiune / dovedit: numarul legaturii modulului (unu in plus la fiecare legare) si daca modulul a dat deja cuvinte de
#     control prin soclu de la legare (atunci da CSA-ALT; un modul cu protocolul 3 nu le da neaparat);
#   cuvinte, ecm, descifrate, anulate, chei, active: contoarele (pentru probe).
# gata(): numai raspunsul da / nu (Components/HdsStreamRelay.py: canalele CSA-ALT nu mai trec prin releu).
# canalCsaAlt(ref): 2 (au venit cuvinte de control prin soclu pentru canal), 1 (ECM-ul spune CSA-ALT), 0 (nu e CSA-ALT),
#   -1 (necunoscut), ce a aflat nucleul pe acest receptor de la pornire.
# textStare(_): randul pentru „Despre imagine” (Screens/Information.py, deci si pagina web /informatii/despre).
#
# MODULUL CARE NU STIE ICAM (11.11.2026, proba pe SF8008): OSCam, OSCam-emu si NCam se leaga cu protocolul 3 si dau
# imagine pe Sky Deutschland; OSCam-smod nu (fara protocolul 3, iar releul lui nu descifreaza ICAM), iar omul vede negru.
# Cu un asemenea modul nucleul nu porneste monitorul ECM (servicedvb.cpp, SoftCSA negata), deci hdsSoftCsaCanal da -1
# afara de canalele vazute inainte cu alt modul: semnul adevarat sunt CAID-urile din PMT (aceleasi ca la trecerea
# singura prin releu, Components/HdsStreamRelay.potrivireCaid cu config.misc.hds_streamrelay_icam_caid). Fara niciun
# nume de modul in cod: se uita numai la starea SoftCSA.
#   canalIcam(ref, caids): canalul e ICAM (memoria nucleului, altfel toate CAID-urile din familia celor alese);
#   canalIcamFaraSoftCsa(ref, caids): receptorul stie SoftCSA, dar nu e gata acum (modulul pornit nu e legat cu
#     protocolul 3 si cuvintele extinse), iar canalul e ICAM: textul TEXT_ICAM_CANAL e motivul ecranului negru;
#   randModul(_, ruleaza): randul din ecranul modulelor (Screens/CamSetup.py) si din pagina web a modulelor
#     (acces_conditionat_web.py), numai cand un modul ruleaza si SoftCSA nu e gata; altfel "".
#
# Partea de sus nu importa nimic din enigma2 (probele de pe PC); legatura cu nucleul are import tarziu.

GOL = {"biblioteca": 0, "receptor": 0, "versiune": "", "client": 0, "protocol": -1, "modul": "", "extins": 0, "gata": 0,
	"cuvinte": 0, "ecm": 0, "descifrate": 0, "anulate": 0, "chei": 0, "active": 0, "conexiune": 0, "dovedit": 0}


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXT_LIPSESTE = N_("lipsește (fără libdvbcsa)")
TEXT_ALT_RECEPTOR = N_("nu e încă pe acest model de receptor")
TEXT_GATA = N_("pregătită (libdvbcsa %s, modulul de acces legat cu protocolul 3)")
TEXT_FARA_EXTINSE = N_("libdvbcsa %s; modulul de acces legat nu anunță cuvintele extinse")
TEXT_FARA_MODUL = N_("libdvbcsa %s; niciun modul de acces legat cu protocolul 3")
# canalul ICAM negru cu un modul care nu il descifreaza (motivul ecranului negru) si randul din ecranul modulelor; numele
# modulelor stau numai in text (cerute de Eduard, 11.11.2026), nu in cod
TEXT_ICAM_CANAL = N_("Canalul folosește ICAM (Sky Deutschland), iar modulul de acces pornit nu îl poate descifra. Alege OSCam, OSCam-emu sau NCam în ecranul modulelor.")
TEXT_ICAM_MODUL = N_("Canalele ICAM (Sky Deutschland) nu se descifrează cu modulul pornit: pentru ele alege OSCam, OSCam-emu sau NCam.")
TEXT_FAPTA_MODULE = N_("Deschide modulele de acces")


def _nucleu():
	try:
		import enigma
	except ImportError:
		return None
	return enigma


def stare(nucleu=None):
	"""Starea din nucleu; GOL (copie) cand binarul nu stie SoftCSA sau citirea cade."""
	n = nucleu if nucleu is not None else _nucleu()
	f = getattr(n, "hdsSoftCsaStare", None) if n is not None else None
	rez = dict(GOL)
	if f is None:
		return rez
	try:
		d = f()
	except Exception as e:
		print("[HdsSoftCsa] starea nu se citeste: %r" % (e,))
		return rez
	if isinstance(d, dict):
		for k in rez:
			if k in d:
				rez[k] = d[k]
	return rez


def gata(nucleu=None):
	return bool(stare(nucleu).get("gata"))


def canalCsaAlt(ref, nucleu=None):
	"""2 au venit cuvinte pentru canal, 1 canalul e CSA-ALT, 0 nu e, -1 necunoscut (nevazut de la pornire, binar vechi)."""
	n = nucleu if nucleu is not None else _nucleu()
	f = getattr(n, "hdsSoftCsaCanal", None) if n is not None else None
	if f is None or not ref:
		return -1
	try:
		return int(f(ref if isinstance(ref, str) else ref.toString()))
	except Exception:
		return -1


def textStare(traducere=None, s=None):
	"""Randul de stare pentru om, in romana (traducerea prin `traducere`, de obicei _)."""
	t = traducere or (lambda x: x)
	if s is None:
		s = stare()
	versiune = s.get("versiune") or "?"
	if not s.get("receptor"):
		return t(TEXT_ALT_RECEPTOR)
	if not s.get("biblioteca"):
		return t(TEXT_LIPSESTE)
	if s.get("gata"):
		return t(TEXT_GATA) % versiune
	if s.get("client") and int(s.get("protocol") or 0) >= 3:
		return t(TEXT_FARA_EXTINSE) % versiune
	return t(TEXT_FARA_MODUL) % versiune


def _caidIcam():
	"""CAID-urile ICAM alese (config.misc.hds_streamrelay_icam_caid, Components/HdsStreamRelay.caidDinText); fara setari
	(probele de pe PC) cele din fabrica."""
	try:
		from Components import HdsStreamRelay as SR
	except ImportError:
		import HdsStreamRelay as SR
	text = ""
	try:
		from Components.config import config
		text = config.misc.hds_streamrelay_icam_caid.value
	except Exception:
		pass
	return SR, SR.caidDinText(text)


def canalIcam(ref, caids, nucleu=None, alese=None):
	"""True cand canalul e ICAM: nucleul l-a vazut CSA-ALT de la pornire, altfel are un CAID ales si toate CAID-urile
	lui sunt din familia celor alese (Videoguard 0x09; simulcrypt cu alte sisteme nu, acela se poate vedea si direct)."""
	if canalCsaAlt(ref, nucleu) >= 1:
		return True
	try:
		SR, implicite = _caidIcam()
		return SR.potrivireCaid(caids or [], alese if alese is not None else implicite) == 1
	except Exception as e:
		print("[HdsSoftCsa] CAID-urile ICAM nu se citesc: %r" % (e,))
		return False


def _softCsaLipseste(s):
	"""Receptorul stie SoftCSA (biblioteca incarcata), dar descifrarea nu e gata acum."""
	return bool(s.get("receptor")) and bool(s.get("biblioteca")) and not s.get("gata")


def canalIcamFaraSoftCsa(ref, caids, nucleu=None, s=None, alese=None):
	"""True cand canalul e ICAM si SoftCSA nu e gata (modulul pornit nu stie protocolul 3 cu cuvintele extinse, sau
	niciun modul): motivul ecranului negru e TEXT_ICAM_CANAL. Fara SoftCSA in binar: False (textul ar fi gresit)."""
	if s is None:
		s = stare(nucleu)
	if not _softCsaLipseste(s):
		return False
	return canalIcam(ref, caids, nucleu, alese)


def randModul(traducere=None, ruleaza=True, s=None, nucleu=None):
	"""Randul pentru ecranul modulelor si pagina web: TEXT_ICAM_MODUL cand un modul ruleaza si SoftCSA nu e gata, altfel
	"" (fara modul pornit randul nu spune nimic: „Despre imagine” arata deja starea SoftCSA)."""
	if not ruleaza:
		return ""
	if s is None:
		s = stare(nucleu)
	if not _softCsaLipseste(s):
		return ""
	t = traducere or (lambda x: x)
	return t(TEXT_ICAM_MODUL)
