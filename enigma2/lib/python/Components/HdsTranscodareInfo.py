# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTranscodareInfo.py: ce poate receptorul la transcodare (un canal recodat spre telefon sau tableta), pentru
# Informatii > Receptor si procesor (Screens/Information.py, HdsReceiverInfo) si pentru pagina web a aceluiasi ecran
# (HdsWebControl/informatii_web.py citeste textul ecranului).
#
# Numai ce se stie sigur, din doua locuri:
# - profilul modelului (Components/HdsBoxInfoModele.py: transcoding / multitranscoding, din conf-ul masinii);
# - nodurile driverului /proc/stb/encoder/<n>/ (aceleasi nume ca pluginul TransCodingSetup din OE-Alliance: bitrate,
#   framerate, display_format, width, height, video_codec, audio_codec, level, profile), plus vcodec_choices (codecurile
#   pe care le ofera codorul) si /dev/bcm_enc0 (codorul Broadcom fara noduri /proc).
# Un codor = un dosar /proc/stb/encoder/<n> cu nodul bitrate (ca pluginul). Sesiunile simultane: una fara
# multitranscoding; cu el, cate codoare, numai cand driverul arata mai multe (altfel nu se scrie). „Nu are codor hardware” numai cand e sigur (profilul nu declara
# transcodarea si nici driverul nu arata un codor); ce nu se stie nu se scrie. Valorile de acum (debitul, rezolutia,
# cadrele) sunt cele scrise de plugin sau de serviciul de transcodare in nodurile codorului 0.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau radacina /proc si profilul.

import os

PROC = "/proc/stb/encoder"
DEV = "/dev/bcm_enc0"


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _citeste(cale, n=256):
	try:
		with open(cale, "r") as f:
			return " ".join(f.read(n).split())
	except Exception:
		return ""


def _profilModel():
	"""Profilul receptorului din HdsBoxInfoModele ({} cand nu e cunoscut)."""
	try:
		from Components.SystemInfo import SystemInfo
		mb = SystemInfo.get("machinebuild") or ""
		from Components.HdsBoxInfoModele import valori
		return valori(mb)
	except Exception:
		return {}


def codoare(proc=PROC):
	"""Numele dosarelor codoarelor (["0", "1"]): cele cu nodul bitrate, in ordine."""
	try:
		nume = sorted(os.listdir(proc))
	except Exception:
		return []
	return [n for n in nume if os.path.isdir(os.path.join(proc, n)) and os.path.exists(os.path.join(proc, n, "bitrate"))]


def capabilitati(proc=PROC, dev=DEV, profil=None):
	"""{"are": True/False/None, "multi": True/False/None, "codoare": n, "sesiuni": n sau None, "codecuri": [..],
	"rezolutie": "1280x720" sau "", "format": "720p" sau "", "debit": biti/s sau None, "cadre": cadre/s sau None}."""
	profil = _profilModel() if profil is None else (profil or {})
	cunoscut = bool(profil)
	lista = codoare(proc)
	placa = bool(lista) or os.path.isdir(os.path.join(proc, "0")) or os.path.exists(dev)
	declarat = bool(profil.get("transcoding") or profil.get("multitranscoding"))
	if placa and (declarat or not cunoscut):
		are = True
	elif not placa and not declarat and (cunoscut or not os.path.exists(proc)):
		are = False
	else:
		are = None
	rez = {"are": are, "multi": None, "codoare": len(lista), "sesiuni": None, "codecuri": [], "rezolutie": "",
		"format": "", "debit": None, "cadre": None}
	if are is not True:
		return rez
	if cunoscut:
		rez["multi"] = bool(profil.get("multitranscoding"))
	elif lista:
		rez["multi"] = len(lista) > 1
	# sesiunile deodata: una fara multitranscodare; cu ea, cate codoare, numai cand driverul arata mai multe (un singur nod
	# cu multitranscodare in profil nu spune cate sesiuni duce: nu se scrie)
	if lista and not rez["multi"]:
		rez["sesiuni"] = 1
	elif len(lista) > 1:
		rez["sesiuni"] = len(lista)
	baza = os.path.join(proc, lista[0] if lista else "0")
	rez["codecuri"] = [c for c in _citeste(os.path.join(baza, "vcodec_choices")).split() if c]
	w, h = _citeste(os.path.join(baza, "width")), _citeste(os.path.join(baza, "height"))
	if w.isdigit() and h.isdigit() and int(w) > 0 and int(h) > 0:
		rez["rezolutie"] = "%sx%s" % (int(w), int(h))
	rez["format"] = _citeste(os.path.join(baza, "display_format"), 32)
	for cheie, nod in (("debit", "bitrate"), ("cadre", "framerate")):
		v = _citeste(os.path.join(baza, nod), 32)
		try:
			v = int(v)
		except ValueError:
			continue
		if v > 0:
			rez[cheie] = v
	return rez


def _debitText(biti):
	if biti >= 1000000:
		t = ("%.1f" % (biti / 1000000.0)).rstrip("0").rstrip(".")
		return "%s Mbps" % t.replace(".", ",")
	return "%d kbps" % (biti // 1000)


def _cadreText(v):
	# nodul da cadrele pe 1000 de secunde (25000 = 25 fps, 23976 = 23,976 fps)
	t = ("%.3f" % (v / 1000.0)).rstrip("0").rstrip(".")
	return "%s fps" % t.replace(".", ",")


def randuri(cap=None):
	"""[(eticheta, valoare)] pentru sectiunea „Transcodarea spre telefon sau tabletă” (ecranul si web-ul)."""
	cap = capabilitati() if cap is None else cap
	da, nu = _t("Da"), _t("Nu")
	if cap["are"] is None:
		return [(_t("Transcodare"), _t("Necunoscut"))]
	if cap["are"] is False:
		return [(_t("Transcodare"), _t("Nu are codor hardware"))]
	r = [(_t("Transcodare"), da)]
	if cap["multi"] is not None:
		r.append((_t("Multitranscodare"), da if cap["multi"] else nu))
	if cap["codoare"]:
		r.append((_t("Codoare hardware"), "%d" % cap["codoare"]))
	if cap["sesiuni"]:
		r.append((_t("Sesiuni deodată"), "%d" % cap["sesiuni"]))
	if cap["codecuri"]:
		r.append((_t("Codecuri video"), ", ".join(c.upper().replace("H264", "H.264").replace("H265", "H.265")
			for c in cap["codecuri"])))
	acum = [x for x in (cap["rezolutie"] or cap["format"], _debitText(cap["debit"]) if cap["debit"] else "",
		_cadreText(cap["cadre"]) if cap["cadre"] else "") if x]
	if acum:
		r.append((_t("Reglajul de acum"), " · ".join(acum)))
	return r
