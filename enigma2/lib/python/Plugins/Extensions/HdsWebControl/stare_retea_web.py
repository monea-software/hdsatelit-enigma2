# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# stare_retea_web.py: pictograma retelei in antetul paginilor web (HdsWebControl), perechea pictogramei din barele de
# pe televizor (din 0.4.4). Aceeasi stare, prin aceeasi functie: Components/HdsStareRetea.stare().
#
#   GET /api/stare-retea   (poarta comuna a HdsJsonResource: retea locala, apoi cookie-ul browserului sau ?token=)
#       -> {"result": true, "cod": "ok"|"fara_internet"|"fara_router"|"verific", "fel": "cablu"|"wifi",
#           "treapta": 0..4, "pictograma": <cheia>, "titlu": <textul la trecerea mouse-ului>, "svg": <desenul>}
#
# Desenele sunt SVG-urile din Google Stitch (proiectul "HD Satelit - interfata web receptor", sistemul de design
# "HD Satelit Control", ecranul "Pictograme retea - bara de informatii"), la 40x30: cablu = monitor cu mufa de retea si
# cablul in jos; Wi-Fi = trei arce si un punct, treptele stinse la 30%; insigna jos-dreapta: verde cu bifa (internetul
# merge), chihlimbar cu glob taiat (routerul nu are internet), rosu cu X (fara legatura cu routerul); "se verifica" fara
# insigna, la 60%. Din aceleasi desene unealta skinului (skin/tools/fa_pictograme_retea.py) face pozele
# HDSatelit/retea/<cheie>.png (48x36) si <cheie>@2x.png (96x72) pentru televizor.
#
# Fisierul nu importa nimic din enigma2 la incarcare (unealta skinului si probele de pe PC il citesc direct).

ALB = "#FFFFFF"
INEL = "#0E1323"
VERDE = "#10B981"
CHIHLIMBAR = "#F59E0B"
ROSU = "#EF4444"

# aceleasi chei ca Components/HdsStareRetea.PICTOGRAME
CHEI = ("cablu_ok", "cablu_fara_internet", "cablu_fara_router", "cablu_verific",
	"wifi1_ok", "wifi2_ok", "wifi3_ok", "wifi4_ok",
	"wifi1_fara_internet", "wifi2_fara_internet", "wifi3_fara_internet", "wifi4_fara_internet",
	"wifi_fara_router", "wifi_verific")


def _t(text):
	"""Traducerea enigma2; un text gol ramane gol."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _op(atribut, op):
	return (' %s="%s"' % (atribut, op)) if op is not None else ""


def _linie(d, latime, op=None):
	return '<path d="%s" stroke="%s"%s stroke-width="%s" stroke-linecap="round"/>' % (d, ALB, _op("stroke-opacity", op), latime)


def _cablu(op=None, scos=False):
	"""Monitorul cu piciorul, mufa si cablul (Stitch, 40x30). scos: mufa trasa in jos, departe de picior."""
	parti = ['<rect x="8" y="4" width="24" height="15" rx="2" stroke="%s"%s stroke-width="1.6" fill="none"/>'
		% (ALB, _op("stroke-opacity", op))]
	if scos:
		parti += [_linie("M20 19V21", 1.6, op), _linie("M16 21H24", 1.6, op),
			'<rect x="18" y="23" width="4" height="3" rx="0.5" fill="%s"%s/>' % (ALB, _op("fill-opacity", op))]
	else:
		parti += [_linie("M20 19V22", 1.6, op), _linie("M16 22H24", 1.6, op),
			'<rect x="18" y="22" width="4" height="4" rx="0.5" fill="%s"%s/>' % (ALB, _op("fill-opacity", op))]
	parti.append(_linie("M20 26V28", 1.6, op))
	return "".join(parti)


ARCE = ("M12 19C14 17 18 17 20 19", "M8.5 15C12.5 11.5 19.5 11.5 23.5 15", "M5 11C11 5.5 21 5.5 27 11")
ARCE_CENTRU = ("M16 19C18 17 22 17 24 19", "M12.5 15C16.5 11.5 23.5 11.5 27.5 15", "M9 11C15 5.5 25 5.5 31 11")


def _wifi(aprinse, op_aprins=None, centrat=False):
	"""Punctul si cele trei arce (Stitch, 40x30). aprinse = cate trepte sunt pline (1 = numai punctul, 4 = tot);
	celelalte la 30%. centrat: fara loc pentru insigna (starea "se verifica")."""
	cx = 20 if centrat else 16
	op_punct = op_aprins if aprinse >= 1 else 0.3
	parti = ['<circle cx="%d" cy="23" r="1.5" fill="%s"%s/>' % (cx, ALB, _op("fill-opacity", op_punct))]
	for i, d in enumerate(ARCE_CENTRU if centrat else ARCE):
		parti.append(_linie(d, 1.4, op_aprins if aprinse >= i + 2 else 0.3))
	return "".join(parti)


def _insigna(fel):
	baza = '<circle cx="31" cy="22" r="5" fill="%s" stroke="%s" stroke-width="1.2"/>'
	if fel == "ok":
		return (baza % (VERDE, INEL)) + ('<path d="M29 22L30.5 23.5L33.5 20.5" stroke="%s" stroke-width="1.2" '
			'stroke-linecap="round" stroke-linejoin="round"/>' % ALB)
	if fel == "fara_internet":
		return (baza % (CHIHLIMBAR, INEL)) + ('<circle cx="31" cy="22" r="3" stroke="%s" stroke-width="0.8" fill="none"/>'
			'<path d="M28 19L34 25" stroke="%s" stroke-width="1" stroke-linecap="round"/>' % (ALB, ALB))
	return (baza % (ROSU, INEL)) + ('<path d="M29 20L33 24" stroke="%s" stroke-width="1.2" stroke-linecap="round"/>'
		'<path d="M33 20L29 24" stroke="%s" stroke-width="1.2" stroke-linecap="round"/>' % (ALB, ALB))


def corp_svg(cheie):
	"""Elementele desenului (fara <svg>) pentru o cheie din CHEI; "" pentru o cheie necunoscuta."""
	if cheie == "cablu_ok":
		return _cablu() + _insigna("ok")
	if cheie == "cablu_fara_internet":
		return _cablu() + _insigna("fara_internet")
	if cheie == "cablu_fara_router":
		return _cablu(scos=True) + _insigna("fara_router")
	if cheie == "cablu_verific":
		return _cablu(op=0.6)
	if cheie == "wifi_fara_router":
		return _wifi(0) + _insigna("fara_router")
	if cheie == "wifi_verific":
		return _wifi(4, op_aprins=0.6, centrat=True)
	for n in (1, 2, 3, 4):
		if cheie == "wifi%d_ok" % n:
			return _wifi(n) + _insigna("ok")
		if cheie == "wifi%d_fara_internet" % n:
			return _wifi(n) + _insigna("fara_internet")
	return ""


def svg(cheie, latime=40, inaltime=30):
	corp = corp_svg(cheie)
	if not corp:
		return ""
	return ('<svg width="%d" height="%d" viewBox="0 0 40 30" fill="none" xmlns="http://www.w3.org/2000/svg" '
		'aria-hidden="true" focusable="false">%s</svg>' % (latime, inaltime, corp))


SVG = dict((k, svg(k)) for k in CHEI)


def stare(R=None):
	"""Raspunsul pentru GET /api/stare-retea (si pentru antetul facut pe receptor). `R` = HdsStareRetea (probele)."""
	if R is None:
		from Components import HdsStareRetea as R
	st = R.stare()
	cheie = R.cheie_pictograma(st)
	try:
		treapta = int(st.get("treapta") or 0)
	except (TypeError, ValueError):
		treapta = 0
	return {"result": True, "cod": st.get("cod") or "verific", "fel": st.get("fel") or "cablu", "treapta": treapta,
		"pictograma": cheie, "titlu": R.text_ajutor(st), "svg": SVG.get(cheie, ""), "aratata": aratata(R)}


def aratata(R):
	"""Setarea "Arata pictograma internetului in bare" (HdsStareRetea.pictograma_aratata); la orice eroare da."""
	try:
		return bool(R.pictograma_aratata())
	except Exception:
		return True


def rute(baza):
	"""Resursele de sub /api: {nume: resursa}. `baza` e HdsJsonResource din plugin.py."""

	class StareReteaResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare())
			except Exception as eroare:
				print("[HdsWebControl] stare retea: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	return {b"stare-retea": StareReteaResource()}


# ---------------------------------------------------------------- antetul paginilor (cadru_web.antetHtml)
# Desenele stau o singura data in pagina, ca <symbol id="hr-<cheie>"> (langa iconitele cadrului); pictograma din antet
# si cea din cardul paginii /retea sunt un <svg><use href="#hr-<cheie>"/></svg>, iar scriptul schimba numai href-ul
# (fara innerHTML).

SIMBOLURI = ('<svg class="hds-simboluri" aria-hidden="true" focusable="false" width="0" height="0" fill="none">%s</svg>'
	% "".join('<symbol id="hr-%s" viewBox="0 0 40 30">%s</symbol>' % (k, corp_svg(k)) for k in CHEI))


def folosire_svg(cheie, latime=40, inaltime=30):
	"""Pictograma ca trimitere la simbolul ei (cheie necunoscuta: "se verifica" pe cablu)."""
	if cheie not in CHEI:
		cheie = "cablu_verific"
	return ('<svg width="%d" height="%d" viewBox="0 0 40 30" aria-hidden="true" focusable="false"><use href="#hr-%s"/>'
		'</svg>' % (latime, inaltime, cheie))


def antet_html():
	"""Simbolurile si pictograma din antet, cu starea de acum (fara sa astepte prima cerere a paginii); "" la orice
	eroare."""
	try:
		d = stare()
	except Exception as eroare:
		print("[HdsWebControl] stare retea in antet: %s" % eroare)
		return ""
	return SIMBOLURI + pictograma_html(d)


def pictograma_html(d):
	"""Pictograma din antet; cu setarea oprita ramane in pagina, ascunsa (hidden), ca scriptul antetului s-o arate cand
	setarea se porneste din nou."""
	titlu = (d.get("titlu") or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
	return ('<span class="hds-retea" id="hdsRetea" role="img" title="%s" aria-label="%s" data-cod="%s"%s>%s</span>'
		% (titlu, titlu, d.get("cod") or "verific", "" if d.get("aratata", True) else " hidden",
		folosire_svg(d.get("pictograma") or "")))
