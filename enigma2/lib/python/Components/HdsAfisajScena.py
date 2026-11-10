# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Datele comune pentru LCD si previzualizare. Fara Pillow, ecran sau scrieri.

import math
import time
from datetime import date as DataCalendar, timedelta


VECHIME_VREME_S = 2 * 60 * 60
ORE_CALENDAR = ("ceas.secunde", "ceas.utc", "ceas.alt_fus")
DATE_CALENDAR = ("ceas.data", "ceas.ziua", "ceas.luna", "ceas.anul",
	"ceas.ziua_anului", "ceas.saptamana")
ZILE = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
LUNI = ("ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie",
	"august", "septembrie", "octombrie", "noiembrie", "decembrie")


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError):
		return text


def _text(v):
	if v is None:
		return ""
	if isinstance(v, bytes):
		v = v.decode("utf-8", "replace")
	return " ".join("".join(c for c in str(v) if not "\x80" <= c <= "\x9f").split())


def _numar(v, minim=None, maxim=None):
	if v is None or isinstance(v, bool):
		return None
	try:
		n = float(v)
	except (ValueError, TypeError, OverflowError):
		return None
	if not math.isfinite(n) or (minim is not None and n < minim) or (maxim is not None and n > maxim):
		return None
	return n


def _apel(obiect, metoda, *args):
	try:
		return getattr(obiect, metoda)(*args)
	except Exception:
		return None


def _catalog():
	try:
		from Components import HdsAfisajDate as D
	except ImportError:
		import HdsAfisajDate as D
	return D


def _vremeModul():
	try:
		from Components import HdsVremea as V
	except ImportError:
		import HdsVremea as V
	return V


def _sigur():
	try:
		from Components import HdsCeas as H
		return bool(H.oraSigura(H._handler()))
	except Exception:
		return False


def _ora(t):
	try:
		return time.strftime("%H:%M", time.localtime(t))
	except (ValueError, TypeError, OverflowError, OSError):
		return "--:--"


def _epg(ctx, i, acum, sincronizat):
	e = _apel(ctx, "eveniment", i)
	if e is None:
		return None
	titlu = _text(_apel(e, "getEventName"))
	inceput = _numar(_apel(e, "getBeginTime"), 1)
	durata = _numar(_apel(e, "getDuration"), 0)
	sfarsit = inceput + durata if inceput is not None and durata is not None and durata > 0 else None
	valid = sfarsit is not None and math.isfinite(sfarsit)
	# Un titlu poate exista fara interval valabil. Bara nu apare in acel caz,
	# nici pentru un eveniment ramas in cache dupa sfarsit sau inainte de inceput.
	progres = None
	if valid and sincronizat and inceput <= acum < sfarsit:
		progres = (acum - inceput) / durata
	return dict(titlu=titlu, inceput=inceput, sfarsit=sfarsit if valid else None,
		interval=("%s - %s" % (_ora(inceput), _ora(sfarsit))) if valid else "",
		progres=progres)


def _canal(ctx, detalii, acum, sincronizat, confirmat=True):
	# Cifrele cerute nu apartin inca serviciului redat: nicio sigla sau EPG vechi.
	if not confirmat:
		return dict(numar=_text(detalii.get("valoare")), nume="", sigla="",
			confirmat=False, emisiune=None, urmatoarea=None)
	numar = getattr(ctx, "numar", None)
	nume = _text(_apel(ctx, "numeServiciu"))
	valoare = detalii.get("valoare")
	if isinstance(valoare, (list, tuple)) and len(valoare) == 2:
		numar, nume = valoare
	num = _numar(numar, 0)
	return dict(numar=str(int(num)) if num is not None and num == int(num) else "",
		nume=_text(nume), sigla=_text(detalii.get("imagine")), confirmat=True,
		emisiune=_epg(ctx, 0, acum, sincronizat), urmatoarea=_epg(ctx, 1, acum, sincronizat))


def _sonor(detalii):
	volum, mut = None, False
	if "volum" not in detalii or "mut" not in detalii:
		try:
			from enigma import eDVBVolumecontrol
			v = eDVBVolumecontrol.getInstance()
			# getVolume conserveaza valoarea si cand isMuted este adevarat.
			volum, mut = v.getVolume(), bool(v.isMuted())
		except Exception:
			pass
	volum = _numar(detalii.get("volum", volum), 0, 100)
	return (int(volum) if volum is not None else None), bool(detalii.get("mut", mut))


def _inregistrari(ctx, detalii):
	if "inregistrari" in detalii:
		n = _numar(detalii["inregistrari"], 0)
		return int(n) if n is not None else 0
	nav = getattr(getattr(ctx, "session", None), "nav", None)
	r = _apel(nav, "getRecordings")
	try:
		return len(r) if r is not None else 0
	except TypeError:
		return 0


def _inregistrare(ctx, detalii, acum, sincronizat):
	# Serviciul inregistrat poate fi altul decat canalul vazut pe televizor.
	timere = _catalog()._timereCareMerg(ctx)
	serviciu = detalii.get("serviciu_inregistrare")
	if serviciu is not None:
		timere = [t for t in timere if getattr(t, "record_service", None) == serviciu]
	if not timere:
		return None
	# Mesajul REC anunta pornirea; luam cea mai recenta inregistrare cunoscuta.
	t = max(timere, key=lambda t: _numar(getattr(t, "begin", None), 1) or 0)
	ref = getattr(t, "service_ref", None)
	nume_canal = _text(_apel(ref, "getServiceName"))
	inceput = _numar(getattr(t, "begin", None), 1)
	scurs = None
	if sincronizat and inceput is not None and inceput <= acum:
		scurs = int(acum - inceput)
	durata = ""
	if scurs is not None:
		ore, secunde = divmod(scurs, 3600)
		minute, secunde = divmod(secunde, 60)
		durata = "%02d:%02d:%02d" % (ore, minute, secunde)
	return dict(nume=_text(getattr(t, "name", "")), canal=nume_canal,
		inceput=inceput, durata_secunde=scurs, durata=durata)


def _temperatura(v, unitate):
	v = _numar(v, -150, 100)
	if v is None:
		return ""
	return _vremeModul().textTemperatura(v, unitate)


def _zi(v):
	if not isinstance(v, str) or len(v) != 10:
		return None
	try:
		return DataCalendar.fromisoformat(v)
	except ValueError:
		return None


def _vreme(detalii, acum, sincronizat):
	V = _vremeModul()
	v = detalii.get("vreme") if "vreme" in detalii else V.date()
	v = v if isinstance(v, dict) else {}
	unitate = detalii.get("unitate") or V.setari().get("unitate", "C")
	unitate = unitate if unitate in V.UNITATI else "C"
	temperatura = _numar(v.get("temperatura"), -150, 100)
	actualizat = _numar(v.get("actualizat"), 1)
	veche = actualizat is None or not sincronizat or not 0 <= acum - actualizat <= VECHIME_VREME_S
	rez = dict(disponibila=temperatura is not None, veche=veche, actualizat=actualizat,
		ora_actualizarii=_ora(actualizat) if actualizat is not None else "",
		oras=_text(v.get("oras")), temperatura=temperatura,
		temperatura_text=_temperatura(temperatura, unitate), stare=_(_text(v.get("stare"))),
		cod=V._codPrognoza(v.get("cod")), pictograma=_text(v.get("pictograma")), zile=[])
	azi = DataCalendar(*time.localtime(acum)[:3]) if sincronizat else None
	lista = v.get("zile")
	for i, nume in enumerate(("azi", "maine", "poimaine")):
		z = lista[i] if isinstance(lista, (list, tuple)) and i < len(lista) and isinstance(lista[i], dict) else {}
		data = _zi(z.get("data", v.get(nume + "_data")))
		cod = V._codPrognoza(z.get("cod", v.get(nume + "_cod")))
		mini = _numar(z.get("min", v.get(nume + "_min")), -150, 100)
		maxi = _numar(z.get("max", v.get(nume + "_max")), -150, 100)
		# Fara data nu atribuim temperaturile unei zile presupuse.
		if data is None:
			cod, mini, maxi = None, None, None
		eticheta = _("Fără date")
		if data is not None:
			if data == azi:
				eticheta = _("Azi")
			elif azi and data == azi + timedelta(days=1):
				eticheta = _("Mâine")
			else:
				eticheta = _(ZILE[data.weekday()])
		poza = V.POZE + "/" + V._stare(cod)[1] + ".png" if cod is not None else ""
		rez["zile"].append(dict(data=data.isoformat() if data else None, eticheta=eticheta,
			cod=cod, min=mini, max=maxi, min_text=_temperatura(mini, unitate),
			max_text=_temperatura(maxi, unitate), pictograma=poza))
	return rez


def scena(ctx, id_data="ceas.ora", text="", pereche=None, acum=None, detalii=None):
	"""Snapshot de valori pentru randare, fara acces la dispozitiv sau retea sincrona.

	`acum` este timpul UNIX, nu monotonic. `detalii` accepta valoare (evenimentul
	brut), imagine, format, titlu, stins, picon_mode, confirmat, asteptare si
	personaj. Probele pot injecta sincronizat, mut, volum, inregistrari, vreme,
	unitate. Progresul este fractie 0..1 sau None; lipsa nu devine zero.
	"""
	detalii = dict(detalii or {})
	acum = _numar(acum if acum is not None else _apel(ctx, "acum"))
	acum = time.time() if acum is None else acum
	sincronizat = bool(detalii["sincronizat"]) if "sincronizat" in detalii else _sigur()
	volum, mut = _sonor(detalii)
	data, ziua = "", ""
	if sincronizat:
		t = time.localtime(acum)
		data = "%d %s %d" % (t.tm_mday, _(LUNI[t.tm_mon - 1]), t.tm_year)
		ziua = _(ZILE[t.tm_wday])
	id_data = _text(id_data)
	rez = dict(pagina="generic", id_data=id_data, titlu=_text(detalii.get("titlu")),
		valoare=_text(text), detaliu="", imagine=_text(detalii.get("imagine")), progres=None,
		ceas=_ora(acum) if sincronizat else "--:--", data=data, ziua=ziua,
		sincronizat=sincronizat, mut=mut, inregistrari=_inregistrari(ctx, detalii),
		stins=bool(detalii.get("stins")) or id_data in ("asteptare.stins", "texte.nimic"),
		canal={}, vreme={}, volum=volum, pereche=pereche)
	if not rez["titlu"]:
		d = _catalog().DUPA_ID.get(id_data)
		rez["titlu"] = _(d.eticheta) if d else ""
	val = detalii.get("valoare")
	if id_data.startswith("asteptare.") or detalii.get("asteptare"):
		rez.update(pagina="asteptare", valoare=rez["ceas"], titlu=_("În așteptare"),
			asteptare=detalii.get("asteptare") or id_data.split(".", 1)[-1])
		if rez["asteptare"] in ("rec", "asteptare.rec"):
			urm = _catalog()._urmatoareaInregistrare(ctx)
			rez["urmatoarea_inregistrare"] = urm
			if urm:
				rez["detaliu"] = _("REC la %s") % _ora(urm["inceput"])
	elif id_data == "ceas.ora":
		rez.update(pagina="ceas", titlu="HD Satelit", valoare=rez["ceas"])
		if sincronizat and detalii.get("format") in ("12", "12ap"):
			t = time.localtime(acum)
			rez["valoare"] = "%d:%02d" % (t.tm_hour % 12 or 12, t.tm_min)
			if detalii.get("format") == "12ap":
				rez["perioada"] = "AM" if t.tm_hour < 12 else "PM"
		elif sincronizat and detalii.get("format") == "ore":
			rez["valoare"] = "%d H" % time.localtime(acum).tm_hour
		rez["vreme"] = _vreme(detalii, acum, sincronizat)
		if rez["vreme"]["disponibila"] and not rez["vreme"]["veche"]:
			rez["pagina"] = "ceas_vreme"
	elif id_data == "vremea.acum":
		v = _vreme(detalii, acum, sincronizat)
		rez.update(pagina="vreme", vreme=v, titlu=v["oras"] or _("Vremea"),
			valoare=v["temperatura_text"], imagine=v["pictograma"], detaliu=v["stare"])
		if not v["disponibila"]:
			rez["detaliu"] = _("Fără date")
		elif v["veche"]:
			rez["detaliu"] = _("Date vechi")
			if v["ora_actualizarii"]:
				rez["detaliu"] += " · " + _("de la %s") % v["ora_actualizarii"]
	elif id_data == "evenimente.cifre":
		detalii["valoare"] = val if val is not None else text
		c = _canal(ctx, detalii, acum, sincronizat, False)
		rez.update(pagina="schimbare_canal", titlu=_("Schimbare canal"),
			valoare=c["numar"], imagine="", canal=c, detaliu=_("Se schimbă canalul"))
	elif id_data in ("canal.numar", "canal.nume", "canal.numar_nume", "evenimente.zap"):
		c = _canal(ctx, detalii, acum, sincronizat, detalii.get("confirmat", True))
		e = c["emisiune"]
		rez.update(pagina="canal", canal=c, titlu=c["nume"], valoare=c["numar"],
			imagine=c["sigla"], detaliu=e["titlu"] if e and e["titlu"] else _("Program indisponibil"),
			progres=e["progres"] if e else None)
	elif id_data in ("evenimente.volum", "evenimente.mut", "sunet.volum", "sunet.mut"):
		if id_data == "evenimente.volum":
			n = _numar(val, 0, 100)
			if n is not None:
				rez["volum"] = int(n)
		if id_data == "evenimente.mut" and "mut" not in detalii:
			rez["mut"] = True
		rez.update(pagina="volum", titlu=_("Volum"),
			valoare=_("MUT") if rez["mut"] else (str(rez["volum"]) if rez["volum"] is not None else ""),
			progres=rez["volum"] / 100.0 if rez["volum"] is not None else None)
	elif id_data in ("evenimente.rec_esuat", "evenimente.rec_esuata") or detalii.get("rec_esuat"):
		rez.update(pagina="inregistrare_esuata", titlu=_("Înregistrare eșuată"),
			valoare="!", detaliu=_text(detalii.get("motiv")))
	elif id_data == "evenimente.rec":
		rec = _inregistrare(ctx, detalii, acum, sincronizat)
		rez.update(pagina="inregistrare", titlu=_("Înregistrare"), valoare="REC",
			detaliu=_("Înregistrarea a pornit"), durata="", inregistrare=rec)
		if rec:
			rez["canal"] = dict(nume=rec["canal"], numar="", sigla="", confirmat=True)
			rez["durata"] = rec["durata"]
			rez["detaliu"] = rec["nume"] or rez["detaliu"]
	elif id_data == "evenimente.fara_semnal":
		c = _canal(ctx, detalii, acum, sincronizat)
		rez.update(pagina="lipsa_semnal", titlu=_("Lipsă semnal"), valoare="!", canal=c, detaliu=c["nume"])
	elif id_data == "evenimente.actualizare":
		# True este semnalul de pornire fara procent, nu valoarea numerica 1.
		n = _numar(val, 0, 100)
		rez.update(pagina="actualizare", titlu=_("Actualizare"),
			valoare=("%d" % n) if n is not None else "", progres=n / 100.0 if n is not None else None,
			detaliu=_("Nu opriți receptorul"), procent=n)
	elif id_data in ("evenimente.motor", "semnal.motor"):
		motor = val if isinstance(val, dict) else _catalog().stareMotor() or {}
		grade = _numar(motor.get("grade"), -180, 180)
		pozitie = ("%g° %s" % (abs(grade), "E" if grade >= 0 else "W")) if grade is not None else ""
		rez.update(pagina="antena", titlu=_("Antena se rotește") if motor.get("misca", True) else _("Poziția antenei"),
			valoare=pozitie, detaliu=_text(motor.get("nume") or motor.get("satelit")),
			antena=dict(grade=grade, directie=motor.get("directie") if motor.get("directie") in ("est", "vest") else "",
				misca=bool(motor.get("misca", True))))
	elif id_data.startswith("personaj.") or (pereche and pereche[0] == "personaj"):
		rez.update(pagina="personaj", personaj=detalii.get("personaj"), valoare="", titlu="HD Satelit")
	elif pereche and pereche[0] == "bara":
		rez["progres"] = _numar(pereche[1], 0, 1)
	if not sincronizat and id_data in ORE_CALENDAR + DATE_CALENDAR:
		# Duratele si sursa orei raman utile; numai calendarul cere ora sigura.
		rez["valoare"] = "--:--" if id_data in ORE_CALENDAR else ""
		rez["progres"] = None
	return rez
