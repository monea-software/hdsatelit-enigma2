# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTemporizare.py: temporizatoarele si inregistrarile puse pe o emisiune din ghid, intr-un singur loc.
#
# Il folosesc a doua bara (Screens/SecondInfoBar.py, pagina ghidului: Verde, Rosu, REC si meniul de pe OK) si
# interfata web (Plugins/Extensions/HdsWebControl/ghid_web.py). Aceleasi reguli ca ghidul imaginii
# (Screens/EpgSelection.py, timerAdd / finishedAdd): temporizatorul primeste marginile din setarile de inregistrare
# (parseEvent), dosarul preferat (preferredTimerPath) si, la suprapunere, se incearca intai scurtarea celor care se
# lungesc singure (setAutoincreaseEnd), apoi se raporteaza lista suprapusa.
#
# Emisiunea se da ca dictionar (Components/Converter/HdsCommon.ev_dict): id, begin, dur, name, short. Serviciul ca
# referinta text. Nimic de aici nu deschide un ecran, in afara de pune_din_fereastra (TimerEntry, apoi fereastra de
# suprapunere); web-ul foloseste numai functiile fara ferestre. Importurile enigma2 sunt tarzii, ca modulul sa se
# incarce si in probele de pe PC (acolo se da RecordTimer si fabrica de temporizatoare).

import time

REZULTAT_PUS = "pus"
REZULTAT_SUPRAPUS = "suprapus"
REZULTAT_EROARE = "eroare"


def _rt(rt=None):
	"""RecordTimer-ul navigatiei (NavigationInstance.instance.RecordTimer) sau cel dat de probe."""
	if rt is not None:
		return rt
	import NavigationInstance
	return NavigationInstance.instance.RecordTimer


def _norm(sref):
	try:
		return ":".join(str(sref).strip().split(":")[:11]).lower()
	except Exception:
		return ""


def _ref_text(t):
	try:
		sr = getattr(t, "service_ref", None)
		ref = getattr(sr, "ref", sr)
		fn = getattr(ref, "toString", None)
		return _norm(fn() if fn is not None else ref)
	except Exception:
		return ""


# un temporizator de comutare nu are durata: e al emisiunii care incepe la cel mult atatea secunde de el
COMUTARE_S = 900


def cauta(sref, ev, rt=None):
	"""Temporizatorul pus pe emisiune: acelasi serviciu si acelasi id; cand temporizatorul sau emisiunea nu are id, o
	inregistrare al carei interval acopera mijlocul emisiunii sau o comutare care porneste aproape de inceputul ei
	(COMUTARE_S). Cele repetate nu se socotesc. None daca nu e."""
	me = _norm(sref)
	if not me or not ev:
		return None
	try:
		lista = list(_rt(rt).timer_list)
	except Exception:
		return None
	begin = int(ev.get("begin", 0))
	mijloc = begin + max(int(ev.get("dur", 0)), 0) // 2
	eid = ev.get("id", -1)
	for t in lista:
		try:
			if _ref_text(t) != me or getattr(t, "repeated", 0):
				continue
			teit = getattr(t, "eit", None)
			if teit is not None and eid is not None and int(eid) >= 0:
				# amandoua au id: numai acelasi id e al emisiunii (orele ar prinde si vecinii scurti)
				if int(teit) == int(eid):
					return t
				continue
			if getattr(t, "justplay", False):
				if abs(int(t.begin) - begin) <= COMUTARE_S:
					return t
			elif int(t.begin) <= mijloc <= int(t.end):
				return t
		except Exception:
			continue
	return None


def margini():
	"""(minute inainte, minute dupa) din setarile de inregistrare; (0, 0) cand lipsesc."""
	try:
		from Components.config import config
		return int(config.recording.margin_before.value), int(config.recording.margin_after.value)
	except Exception:
		return 0, 0


def intrare(sref, ev, justplay=False, fabrica=None):
	"""Temporizatorul nou (nepus inca) pentru emisiune, cu marginile din setari si dosarul preferat. `fabrica`
	(probele) primeste aceleasi argumente ca RecordTimerEntry."""
	inainte, dupa = margini()
	begin = int(ev["begin"]) - inainte * 60
	end = int(ev["begin"]) + max(int(ev.get("dur", 0)), 0) + dupa * 60
	nume = ev.get("name", "") or ""
	descriere = ev.get("short", "") or ""
	eid = ev.get("id", None)
	if eid is not None and int(eid) < 0:
		eid = None
	if fabrica is not None:
		return fabrica(sref, begin, end, nume, descriere, eid, justplay=justplay)
	from RecordTimer import RecordTimerEntry
	from ServiceReference import ServiceReference
	from Components.UsageConfig import preferredTimerPath
	return RecordTimerEntry(ServiceReference(sref), begin, end, nume, descriere, eid, justplay=justplay,
		checkOldTimers=True, dirname=preferredTimerPath())


def _anunta(r, t):
	"""RecordTimer.stateChanged: ecranele care urmaresc temporizatoarele prin on_state_change (lista de pe televizor,
	TimerEdit) se refac. record() si removeEntry() nu il cheama. Il cer (anunta=True) a doua bara si ghidul web; pagina
	web a temporizatoarelor (temporizatoare_web.py) anunta singura, deci acolo ramane implicitul, fara dublura."""
	try:
		r.stateChanged(t)
	except Exception as eroare:
		print("[HdsTemporizare] stateChanged: %s" % eroare)


def pune(intr, rt=None, anunta=False):
	"""Pune temporizatorul. (REZULTAT_PUS, None) sau (REZULTAT_SUPRAPUS, lista suprapusa); ca in ghidul imaginii, intai
	se scurteaza cele care se lungesc singure."""
	r = _rt(rt)
	suprapuse = r.record(intr)
	if suprapuse is not None:
		for x in suprapuse:
			try:
				if x.setAutoincreaseEnd(intr):
					r.timeChanged(x)
			except Exception:
				continue
		suprapuse = r.record(intr)
	if suprapuse is not None:
		return REZULTAT_SUPRAPUS, suprapuse
	if anunta:
		_anunta(r, intr)
	return REZULTAT_PUS, None


def inregistreaza(sref, ev, justplay=False, rt=None, fabrica=None, anunta=True):
	"""Temporizator pus direct, fara fereastra (Rosu pe o emisiune viitoare, web-ul). (rezultat, temporizator sau lista)."""
	try:
		intr = intrare(sref, ev, justplay=justplay, fabrica=fabrica)
		rez, suprapuse = pune(intr, rt, anunta=anunta)
	except Exception as eroare:
		print("[HdsTemporizare] nu s-a putut pune: %s" % eroare)
		return REZULTAT_EROARE, None
	if rez == REZULTAT_SUPRAPUS:
		return rez, suprapuse
	return rez, intr


def scoate(t, rt=None, anunta=False):
	"""Scoate temporizatorul (ca removeTimer din ghid: fara actiune la sfarsit). True daca a mers."""
	try:
		from RecordTimer import AFTEREVENT
		t.afterEvent = AFTEREVENT.NONE
	except Exception:
		pass
	try:
		r = _rt(rt)
		r.removeEntry(t)
	except Exception as eroare:
		print("[HdsTemporizare] nu s-a putut scoate: %s" % eroare)
		return False
	if anunta:
		_anunta(r, t)
	return True


def e_acum(ev, acum=None):
	"""Emisiunea ruleaza acum."""
	acum = time.time() if acum is None else acum
	try:
		return int(ev["begin"]) <= acum < int(ev["begin"]) + max(int(ev.get("dur", 0)), 1)
	except Exception:
		return False


def nume_scurt(t):
	"""Numele temporizatorului pentru mesaje: titlul emisiunii si ora de inceput."""
	try:
		return "%s, %s" % (t.name, time.strftime("%H:%M", time.localtime(int(t.begin))))
	except Exception:
		return getattr(t, "name", "") or ""


def pune_din_fereastra(session, sref, ev, la_final):
	"""Verde pe ghid: fereastra temporizatorului (TimerEntry; acolo se alege inregistrare sau doar comutare), apoi,
	la suprapunere, fereastra de suprapunere. `la_final(pus)` se cheama o singura data, la sfarsit."""
	from Screens.TimerEntry import TimerEntry
	from Screens.TimerEdit import TimerSanityConflict

	def dupa_suprapunere(raspuns):
		dupa_fereastra(raspuns)

	def dupa_fereastra(raspuns):
		if not raspuns or not raspuns[0]:
			la_final(False)
			return
		intr = raspuns[1]
		try:
			rez, suprapuse = pune(intr, anunta=True)
		except Exception as eroare:
			print("[HdsTemporizare] nu s-a putut pune: %s" % eroare)
			la_final(False)
			return
		if rez == REZULTAT_SUPRAPUS:
			session.openWithCallback(dupa_suprapunere, TimerSanityConflict, suprapuse)
			return
		la_final(True)

	session.openWithCallback(dupa_fereastra, TimerEntry, intrare(sref, ev))
