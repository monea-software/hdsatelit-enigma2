# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# porturi_web.py: paznicul porturilor in interfata web (HdsWebControl), perechea intrebarii de pe televizor din
# Components/HdsPorturi.py (din 0.7.4). O SINGURA LOGICA: citirea, conflictele, planul si
# schimbarea sunt in HdsPorturi; aici numai rutele.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/porturi-conflicte                 conflictele de acum, ca text de aratat: [{"port", "tip", "text",
#                                               "propunere"}], plus "buton" (textul butonului, tradus)
#   POST /api/porturi-conflicte-schimba?port=N  muta serviciile din conflictul de pe portul N (fara port: toate) pe
#                                               porturile libere urmatoare; raspunsul spune noile porturi
# Panoul (plugin.py, cardul "Acum pe receptor", sub legaturile "interfața web a modulului") arata un rand de avertizare
# cu butonul "Schimbă portul" pentru fiecare conflict. Amanarea "Nu acum" de pe televizor nu ascunde randul din panou.
#
# FIRUL: citirea (/proc, configurarile) si scrierea configurarilor merg pe un fir separat (meniu_comun_web.peFir);
# setarea extensiilor mutate si repornirea modulelor mutate se fac pe firul enigma2 (HdsPorturi.termina_pe_principal, prin
# reactor.callFromThread). Fisierul nu importa nimic din enigma2 la incarcare: probele dau modulul P (HdsPorturi).

_STEAG_CITIRE = [False]
_STEAG_SCHIMBARE = [False]
MAX_VALOARE = 8


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _p(P=None):
	if P is not None:
		return P
	from Components import HdsPorturi
	return HdsPorturi


def stare(P=None):
	"""Pentru GET /api/porturi-conflicte (pe un fir separat)."""
	P = _p(P)
	try:
		a = P.analiza_web()
		return {"result": True, "conflicte": P.pentru_om(a), "buton": _t(P.BUTON_SCHIMBA), "titlu": _t(P.TITLU)}
	except Exception as eroare:
		print("[HdsWebControl] porturi: %s: %s" % (eroare.__class__.__name__, eroare))
		return {"result": False, "conflicte": []}


def port_din_cerere(request):
	"""Portul din ?port=N, sau None (fara port: toate conflictele). ValueError pentru o valoare care nu e port."""
	valori = (getattr(request, "args", None) or {}).get(b"port") or (getattr(request, "args", None) or {}).get("port")
	if not valori:
		return None
	v = valori[0]
	if isinstance(v, bytes):
		v = v.decode("ascii", "replace")
	v = str(v).strip()[:MAX_VALOARE]
	if not v.isdigit() or not 0 < int(v) < 65536:
		raise ValueError(v)
	return int(v)


def schimba(port, P=None, pe_principal=None):
	"""Pentru POST /api/porturi-conflicte-schimba (pe un fir separat): schimbarea, apoi ce trebuie pe firul enigma2."""
	P = _p(P)
	try:
		r = P.schimba_viu(port)
	except Exception as eroare:
		print("[HdsWebControl] porturi: %s: %s" % (eroare.__class__.__name__, eroare))
		return {"result": False, "message": _t("Eroare pe receptor: %s") % eroare.__class__.__name__}
	P.uita_analiza_web()
	(pe_principal or P._pe_principal)(lambda: P.termina_pe_principal(r))
	return {"result": bool(r["ok"]), "message": r["mesaj"], "mutate": [{"nume": m["nume"], "de": m["de"],
		"la": m["la"]} for m in r["mutate"]]}


def rute(baza, P=None, pe_fir=None, pe_principal=None):
	"""Resursele de sub /api. `baza` e HdsJsonResource din plugin.py."""

	def lucru(request, functie, steag, termen):
		f = pe_fir
		if f is None:
			from .meniu_comun_web import peFir
			f = peFir
		return f(request, functie, steag, termen)

	class ConflicteResource(baza):
		def render_GET(self, request):
			if _STEAG_CITIRE[0]:
				return self._raspunde(request, {"result": False, "ocupat": True, "conflicte": []})
			return lucru(request, lambda: stare(P), _STEAG_CITIRE, 20)

	class SchimbaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				port = port_din_cerere(request)
			except ValueError:
				return self._eroare(request, _t("Portul ales nu există."))
			if _STEAG_SCHIMBARE[0]:
				return self._raspunde(request, {"result": False, "message": _t("Așteaptă să se termine comanda de acum.")})
			return lucru(request, lambda: schimba(port, P, pe_principal), _STEAG_SCHIMBARE, 30)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	return {
		b"porturi-conflicte": ConflicteResource(),
		b"porturi-conflicte-schimba": SchimbaResource(),
	}
