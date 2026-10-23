# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# pasi_decriptare_web.py: pasii decriptarii canalului de pe televizor in interfata web (HdsWebControl), perechea
# randurilor vii de sub mesajul canalului criptat de pe televizor (Screens/HdsEcranNegru.py). Aceleasi randuri, din
# aceeasi functie: Components/HdsPasiDecriptare.date_web, deci nicio a doua logica.
#
# Ruta (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat):
#   GET /api/pasi-decriptare   {result, pornit, ref, criptat, decriptat, pasi: [{t, text, fel}]}
# "pornit" = setarea "Arata pasii decriptarii" (config.usage.hds_pasi_decriptare, oprita din fabrica); oprita: lista
# goala. "ref" = canalul de pe televizor caruia ii sunt pasii: pagina TV (player.js) ii arata numai cand e canalul ei,
# iar randul Acces din panou numai cand canalul de pe televizor e criptat. Raspunsurile modulului de acces au numai
# sistemul, CAID-ul si timpul; cititoarele, adresele si porturile nu ajung aici.
#
# FIRUL: render_GET ruleaza pe firul enigma2 si citeste numai ce a notat urmaritorul ecranului negru (fara fisiere,
# fara retea). Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (P).

import re

MAX_RANDURI = 12
_CONTROL = re.compile(u"[\u0000-\u001f\u007f-\u009f\ud800-\udfff]")


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _p(P=None):
	if P is not None:
		return P
	from Components import HdsPasiDecriptare
	return HdsPasiDecriptare


def curat(text, n=200):
	"""Text pentru JSON: fara caractere de control, taiat; pagina il pune numai ca text."""
	try:
		t = text if isinstance(text, str) else str(text)
	except Exception:
		return u""
	return _CONTROL.sub(u" ", t)[:n].strip()


def stare(P=None):
	"""GET /api/pasi-decriptare -> (cod, corp)."""
	d = _p(P).date_web() or {}
	corp = {"result": True, "pornit": bool(d.get("pornit")), "ref": curat(d.get("ref"), 512),
		"criptat": bool(d.get("criptat")), "decriptat": bool(d.get("decriptat")), "pasi": []}
	if not corp["pornit"]:
		corp["ref"] = u""
		return 200, corp
	for x in (d.get("pasi") or [])[:MAX_RANDURI]:
		corp["pasi"].append({"t": curat(x.get("t"), 16), "text": curat(x.get("text"), 240), "fel": curat(x.get("fel"), 24)})
	return 200, corp


def rute(baza, P=None):
	"""Resursele de sub /api: {nume: resursa}. `baza` e HdsJsonResource din plugin.py."""

	class PasiResource(baza):
		def render_GET(self, request):
			try:
				cod, corp = stare(P=P)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				print("[HdsWebControl] pasii decriptarii: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	return {b"pasi-decriptare": PasiResource()}
