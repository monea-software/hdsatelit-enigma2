# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# portal_web.py: starea HbbTV a canalului care ruleaza, in interfata web (HdsWebControl).
#
# Pereche web a tastei PORTAL din bara (Components/HdsPortal.py): aceeasi stare si acelasi mesaj pe care il arata
# televizorul peste lista extensiilor. Panoul („Acum pe receptor”) il arata pe randul „HbbTV”: valoarea scurta, iar
# dedesubt, mai mic, mesajul intreg (se vede si pe telefon).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat):
#   GET /api/portal    {"result", "activ", "stare": da|nu|nu_stiu|fara_dvb|fara_canal, "hbbtv": true|false|null,
#                       "scurt", "text", "ref"}
# Numai citire: nimic de schimbat, deci fara POST. Tasta PORTAL nu e pe telecomanda desenata in panou; prin API se
# trimite ca orice tasta (/api/remotecontrol?command=150, KEY_WWW), iar starea ei e randul de mai sus.
#
# FIRUL: render_GET ruleaza pe firul enigma2; cererea citeste numai memoria bazei pistelor (un rand), sub o
# milisecunda. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (Po).


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _po(Po=None):
	if Po is not None:
		return Po
	from Components import HdsPortal
	return HdsPortal


def stare(Po=None, nav=None):
	"""Pentru GET /api/portal."""
	Po = _po(Po)
	st, hb = Po.stare_hbbtv(nav)
	ref = ""
	if st != Po.STARE_FARA_CANAL:
		ref = Po.serviciul(nav)[2]
	return {
		"result": True,
		"activ": st != Po.STARE_FARA_CANAL,
		"stare": st,
		"hbbtv": hb,
		"scurt": Po.text_scurt(st),
		"text": Po.text(st),
		"ref": ref,
	}


def rute(baza, resource=None, Po=None, nav=None):
	"""Resursele de sub /api: {nume: resursa}. `baza` e HdsJsonResource din plugin.py; `resource` (twisted) nu
	trebuie: nu e nicio pagina, randul sta in panou."""

	class StareResource(baza):
		"""GET /api/portal: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(Po, nav))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	return {b"portal": StareResource()}
