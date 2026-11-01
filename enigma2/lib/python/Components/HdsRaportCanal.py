# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRaportCanal.py: "Raporteaza canalul asta" (meniul Beta tester si pagina web a beta testerului). Pe canalul de acum
# receptorul face pe loc un raport: datele tehnice ale canalului (numele, referinta, satelitul sau pozitia, frecventa,
# polarizarea, rata de simboluri, sistemul, SID-ul, PID-urile video si audio, codecul, criptat, tunerul, semnalul,
# marimea imaginii) si ultimele randuri din jurnalele tunerului, zap-ului si decodorului (Components/HdsJurnal.py).
# Omul poate adauga un rand de text, dar nu e obligat.
#
# Raportul pleaca prin coada beta testerului (Components/HdsBetaTester.py), ca un mesaj de fel "greseala" (ruta "mesaj"
# a serverului, aceeasi limita de mesaje pe zi), cu ecranul RAPORT_ECRAN si cu raportul tehnic ca jurnal atasat
# ("raport-canal.txt"). Numai pentru cine e inscris in program.
# Fisierul nu importa nimic din enigma2 la incarcare (probele de pe PC).

import os

from Components import HdsJurnal

RAPORT_ECRAN = "Raporteaza canalul"
RAPORT_JURNAL = "raport-canal.txt"
RANDURI_JURNAL = 30
JURNALE = ("tuner", "zap", "decodor")
TEXT_OM_MAX = 300


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _poz(orbital):
	try:
		o = int(orbital)
	except (TypeError, ValueError):
		return ""
	if o > 1800:
		return "%.1fW" % ((3600 - o) / 10.0)
	return "%.1fE" % (o / 10.0)


POL = {0: "H", 1: "V", 2: "L", 3: "R"}
VIDEO = {0: "MPEG2", 1: "H264", 3: "VC1", 4: "MPEG4", 5: "VC1-SM", 6: "MPEG1", 7: "H265", 16: "AVS"}


def dateDinServiciu(ref_text, nume, fe, info_valori, semnal=None):
	"""Datele tehnice ale canalului, din valori deja citite (ca sa se poata proba pe PC):
	fe = dict-ul tunerului (getAll / sTransponderData), info_valori = dict cu vpid, apid, sid, vtip, criptat, latime,
	inaltime; semnal = dict (snr_db, calitate, lock) sau None."""
	d = HdsJurnal.canalDinReferinta(ref_text, nume)
	fe = fe or {}
	tip = fe.get("tuner_type") or fe.get("system") or ""
	frecv = fe.get("frequency")
	if isinstance(frecv, int) and frecv > 0:
		if tip == "DVB-S" or "orbital_position" in fe:
			d["frecventa"] = "%d MHz" % (frecv // 1000 if frecv > 100000 else frecv)
		else:
			d["frecventa"] = "%.3f MHz" % (frecv / 1000000.0 if frecv > 10000000 else frecv / 1000.0)
	if "polarization" in fe:
		d["pol"] = POL.get(fe.get("polarization"), fe.get("polarization"))
	sr = fe.get("symbol_rate")
	if isinstance(sr, int) and sr > 0:
		d["sr"] = sr // 1000 if sr > 100000 else sr
	if "orbital_position" in fe:
		d["poz"] = _poz(fe.get("orbital_position")) or d.get("poz", "")
	sistem = fe.get("system")
	if sistem is not None:
		d["sistem"] = {0: "DVB-S", 1: "DVB-S2"}.get(sistem, sistem) if tip == "DVB-S" else sistem
	if fe.get("tuner_number") is not None:
		try:
			d["tuner"] = chr(65 + int(fe.get("tuner_number")))
		except (TypeError, ValueError):
			pass
	v = info_valori or {}
	if v.get("sid", -1) not in (-1, None):
		d["sid"] = "0x%x" % v["sid"]
	if v.get("vpid", -1) not in (-1, None):
		d["vpid"] = "0x%x" % v["vpid"]
		if v.get("vtip", -1) not in (-1, None):
			d["codec"] = VIDEO.get(v["vtip"], v["vtip"])
	if v.get("apid", -1) not in (-1, None):
		d["apid"] = "0x%x" % v["apid"]
	if v.get("criptat") is not None:
		d["criptat"] = "da" if v["criptat"] else "nu"
	if v.get("latime", -1) not in (-1, None) and v.get("inaltime", -1) not in (-1, None):
		d["imagine"] = "%dx%d" % (v["latime"], v["inaltime"])
	if semnal:
		for k in ("lock", "snr_db", "calitate"):
			if semnal.get(k) is not None:
				d[k] = semnal[k]
	return d


def dateCanalCurent(session=None):
	"""Datele tehnice ale canalului de acum, din redare (session None: NavigationInstance, pentru pagina web);
	{} daca nu ruleaza niciun canal."""
	try:
		from enigma import iServiceInformation as I, iFrontendInformation as F
		from ServiceReference import ServiceReference
	except ImportError:
		return {}
	try:
		if session is None:
			import NavigationInstance
			nav = NavigationInstance.instance
		else:
			nav = session.nav
		ref = nav.getCurrentlyPlayingServiceReference()
		serviciu = nav.getCurrentService()
	except Exception:
		return {}
	if not ref or not serviciu:
		return {}
	info = serviciu.info()
	fe_info = serviciu.frontendInfo()
	fe = {}
	if fe_info:
		try:
			fe = fe_info.getAll(True) or {}
		except Exception:
			fe = {}
	valori = {}
	if info:
		for cheie, nume in (("vpid", "sVideoPID"), ("apid", "sAudioPID"), ("sid", "sSID"), ("vtip", "sVideoType"),
				("criptat", "sIsCrypted"), ("latime", "sVideoWidth"), ("inaltime", "sVideoHeight")):
			try:
				valori[cheie] = info.getInfo(getattr(I, nume))
			except Exception:
				pass
	semnal = {}
	if fe_info:
		try:
			semnal["lock"] = "da" if fe_info.getFrontendInfo(F.lockState) else "nu"
			db = fe_info.getFrontendInfo(F.signalQualitydB)
			if db and db > 0:
				semnal["snr_db"] = "%.2f" % (db / 100.0)
			semnal["calitate"] = "%d%%" % (fe_info.getFrontendInfo(F.signalQuality) * 100 // 65536)
		except Exception:
			pass
	try:
		nume = ServiceReference(ref).getServiceName()
	except Exception:
		nume = ""
	return dateDinServiciu(ref.toString(), nume, fe, valori, semnal)


def textRaport(date, coada=None):
	"""Raportul tehnic atasat: datele canalului si ultimele randuri din jurnalele tunerului, zap-ului si decodorului."""
	coada = coada or HdsJurnal.coada
	randuri = ["Raportul canalului", HdsJurnal.textCanal(date) or "canal: necunoscut", ""]
	for comp in JURNALE:
		randuri.append("--- hds-%s.log (ultimele %d randuri)" % (comp, RANDURI_JURNAL))
		randuri += [HdsJurnal.curata(r) for r in coada(comp, RANDURI_JURNAL)] or ["-"]
		randuri.append("")
	return "\n".join(randuri)


def textMesaj(date, text_om=""):
	"""Textul mesajului: o fraza fixa cu numele canalului si, daca e, randul scris de om."""
	t = "Canalul nu merge: %s" % (date.get("nume") or date.get("ref") or "necunoscut")
	om = " ".join((text_om or "").split())[:TEXT_OM_MAX]
	return t + ("\n" + om if om else "")


def trimite(session, text_om="", B=None, date=None):
	"""Pune raportul in coada beta testerului. -> (reusit, mesaj pentru om)"""
	if B is None:
		from Components import HdsBetaTester as B
	b = B._b()
	if not B.inscris(b):
		return False, _("Nu ești înscris în programul de beta testeri.")
	if date is None:
		date = dateCanalCurent(session)
	if not date:
		return False, _("Nu rulează niciun canal acum.")
	stare = B.citesteStare()
	zi = B.ziUtc()
	if stare.get("mesaje_zi") == zi and int(stare.get("mesaje_azi", 0)) >= B.MESAJE_PE_ZI:
		return False, _("Ai trimis deja 10 mesaje azi. Mai poți trimite mâine.")
	model, _paza = B._modelTinut()
	text = textMesaj(date, text_om)
	corp = {"v": B.PROTOCOL, "id": b.id.value, "nota": int(b.nota.value), "model": model,
		"versiune": B.versiuneImagine(), "limba": B.limba(), "ore": B._oreTinute(),
		"local": os.urandom(8).hex(), "fel": "greseala", "text": text, "ecran": RAPORT_ECRAN,
		"jurnal": {"nume": RAPORT_JURNAL, "text": B.coada(textRaport(date))}, "captura": None}
	if not B.puneInCoada("mesaj", "mesaj", corp, limita=B.PACHET_MAX):
		return False, _("Mesajul e prea mare.")
	intrare = {"local": corp["local"], "fel": "greseala", "cand": B.oraUtc(), "text": text[:200]}

	def adauga(s):
		if s.get("mesaje_zi") != zi:
			s["mesaje_zi"] = zi
			s["mesaje_azi"] = 0
		s["mesaje_azi"] = int(s.get("mesaje_azi", 0)) + 1
		mesaje = s.setdefault("mesaje", [])
		mesaje.insert(0, intrare)
		del mesaje[50:]
	B.schimbaStare(adauga)
	try:
		B._ceruteAcum["trimite"] = True
	except Exception:
		pass
	HdsJurnal.info("zap", "raport", "raportul canalului pus in coada beta testerului")
	return True, _("Raportul canalului a intrat în coadă și pleacă îndată ce receptorul are internet.")
