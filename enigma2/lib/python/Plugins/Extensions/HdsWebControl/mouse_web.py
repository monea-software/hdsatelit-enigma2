# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# mouse_web.py: mouse-ul pe ecranul receptorului in interfata web (HdsWebControl). Aici e numai partea web: ruta si
# scriptul paginii. Ce se face la un clic (lista, rand, buton, bara de derulare, rotita) e in Components/HdsMouseEcran.py,
# aceeasi logica pe care o poate folosi mai tarziu un mouse USB legat la receptor; nicio a doua logica aici.
#
# Ruta (poarta comuna a HdsJsonResource, ca /api/remotecontrol: reteaua locala, apoi ?token= sau cookie-ul browserului
# asociat; cu cookie, numai POST, din pagina receptorului, cu antetul X-HDS-CSRF; cat ecranul "Acces SSH" e deschis pe
# televizor, numai dintr-un browser conectat cu codul, la fel ca tastele):
#   POST /api/mouse?fel=clic|dublu|drag|dragend|rotita|dreapta|mijloc|pagina|capat|text&xp=&yp=   (GET numai cu ?token=)
#     xp, yp: locul in procente din ecran (0-100, cu zecimale), sau x, y in pixelii ecranului enigma2 (1920x1080);
#     clicuri=1|2 (al catelea clic: 2 = dublu clic); drag: si x0p, y0p (sau x0, y0) = locul unde s-a apasat,
#     nou=1 la prima miscare a trasului; clic / dublu: mod=ctrl|shift|ctrl,shift = tastele tinute la clic in pagina
#     (Ctrl / Shift + clic in editorul de canale: bife), lipsa = nicio tasta;
#     rotita: pasi = -12..12 (pozitiv = in jos), 3 sau mai multi = o pagina;
#     dreapta = IESIRE, mijloc (clic pe rotita) = MENIU, ca in emulator; numele spun butonul mouse-ului, nu tasta;
#     pagina (Page Up/Down din tastatura paginii): pasi=-1|1, o pagina in lista principala, fara lista canalul +/-;
#     capat (Home/End): pasi=-1|1, primul sau ultimul rand al listei principale;
#     text: text=semnele scrise (cel mult HdsMouseEcran.TEXT_MAXIM; %08 = Backspace): in campul de text deschis pe
#     televizor, altfel tastele telecomenzii (cifre, M, I, E, T, spatiu, Backspace); vezi HdsMouseEcran.text.
#   Tastele fara semn (sageti, Enter, Esc, F1-F4) pleaca din pagina prin /api/remotecontrol, ca tastele telecomenzii
#   din panou (mouse-ecran.js, TASTE).
#   -> {result, fel, facut: selectie|ok|buton|bara|derulare|tasta|nimic, ecran, lista, rand, tasta, nume, total, tras}
#
# Pagina: in_panou(pagina) pune in panoul principal scriptul mouse-ecran.js (fisierul de langa, citit o data), cu
# traducerile textelor lui in limba meniurilor in locul semnului SEMN_TEXTE, inaintea scriptului panoului. Scriptul sta
# in pagina, nu la o adresa a lui: asa merge si cu panoul deschis cu ?token= (politica paginii de acolo nu primeste
# scripturi de la alte adrese).
#
# FIRUL: render_* ruleaza pe firul enigma2 (reactorul e bucla enigma2), deci ecranele se ating direct, ca la tastele
# telecomenzii. Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau sesiunea si tastele lor.
import json
import os


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce la servire cu _t()."""
	return text


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


# textele scriptului (mouse-ecran.js, TEXTE: aceleasi chei si aceeasi romana), traduse la servire
TEXTE = {
	"ajutor": N_("Mouse pe ecran: clic = alege, dublu clic = OK, clic dreapta = Ieșire, clic pe rotiță = Meniu; după un clic în casetă, rotița = sus și jos (un clic în afară o oprește)."),
	"taste": N_("Tastatura, cu caseta activă: săgeți, Enter = OK, Esc sau Backspace = Ieșire, 0-9, PgUp/PgDn = pagină (la privit, canal), Home/End, F1-F4 = culorile, M = Meniu, I = Info, E = EPG, T = Teletext, spațiu = Pauză; într-un câmp de text deschis pe televizor, literele se scriu în el."),
	"tastatura": N_("Tastatură: %s"),
	"ajutor_deget": N_("Pe ecran: atinge = alege, atinge rândul ales = OK, glisează spre dreapta sau Înapoi = Ieșire, ține apăsat = Meniu; după o atingere în casetă, glisarea în sus și în jos derulează lista."),
	"ajutor_live": N_("Mouse-ul merge pe imaginea live cu \"Afișajul receptorului\" pornit."),
	"tasta": N_("Mouse: %s"),
	"rand": N_("Mouse: rândul %s"),
	"nimic": N_("Mouse: nimic de apăsat acolo"),
	"eroare": N_("Clicul nu a ajuns la receptor (%s)."),
	"telecomanda": N_("Telecomandă"),
	"telecomanda_titlu": N_("Telecomanda peste imagine, pe ecranul întreg"),
	"muta": N_("Trage de aici ca să muți telecomanda"),
	"ascunde": N_("Ascunde telecomanda"),
}
SEMN_TEXTE = "/*__TEXTE__*/null"
FISIER_JS = "mouse-ecran.js"
# inceputul scriptului panoului (_PAGINA_PANOU, inainte de inlocuirea lui __CONFIG__): scriptul mouse-ului se pune
# inaintea lui, deci ultimul </script> ramane al panoului (ecran_negru_web, standby_tv_web si acces_web isi pun scriptul
# inaintea ultimului </script>). Nu are nevoie de functiile panoului la incarcare: cerere, live si grabesteCaptura le
# cauta abia la un clic.
ANCORA = "<script>\nvar CFG = __CONFIG__;"
SEMN_PUS = "window.HDS_MOUSE_PLAYER = legaLive;"


def _caleJs():
	return os.path.join(os.path.dirname(os.path.abspath(__file__)), FISIER_JS)


def scriptTradus():
	"""mouse-ecran.js cu traducerile textelor lui in locul semnului SEMN_TEXTE (JSON numai ASCII, deci fara "</").
	Citit la fiecare panou (ca player.js in tv_web.py): un fisier mic, iar o actualizare a lui merge fara repornire."""
	with open(_caleJs(), "rb") as f:
		text = f.read().decode("utf-8")
	traduse = json.dumps(dict((k, _t(v)) for k, v in TEXTE.items()), ensure_ascii=True, sort_keys=True)
	return text.replace(SEMN_TEXTE, traduse, 1)


def in_panou(pagina):
	"""Panoul principal cu mouse-ul pe ecran: scriptul inaintea scriptului panoului (ANCORA). Fara ancora (o singura
	data), fara caseta ecranului sau fara fisierul scriptului, pagina ramane cum e."""
	try:
		# semnul "pus deja" e o linie a scriptului, nu numele lui: panoul insusi cheama window.HDS_MOUSE_PLAYER
		if pagina.count(ANCORA) != 1 or 'id="cutieCaptura"' not in pagina or SEMN_PUS in pagina:
			return pagina
		js = scriptTradus()
		if "</script" in js.lower():
			raise ValueError("scriptul are </script> in el")
		i = pagina.index(ANCORA)
		return pagina[:i] + "<script>\n" + js + "\n</script>\n" + pagina[i:]
	except Exception as eroare:
		print("[HdsWebControl] mouse pe ecran: %s" % eroare)
		return pagina


# ---------------------------------------------------------------- ruta
_MOUSE = {}


def _mouse(sesiune, apasa, M=None):
	"""Un singur MouseEcran pentru toate browserele (tine minte ultimul clic si trasul pe bara)."""
	if "m" not in _MOUSE:
		if M is None:
			from Components import HdsMouseEcran as M

		def ecranCurent():
			s = sesiune() if sesiune is not None else None
			return getattr(s, "current_dialog", None) if s is not None else None
		_MOUSE["m"] = M.MouseEcran(ecranCurent, apasa)
	return _MOUSE["m"]


def _arg(request, nume):
	v = request.args.get(nume.encode("ascii"))
	if not v:
		return None
	return v[0].decode("utf-8", "replace").strip()


def _numar(request, nume, fel=float):
	v = _arg(request, nume)
	if v is None or v == "":
		return None
	return fel(v)


MODURI = ("ctrl", "shift")


def _mod(text):
	"""mod=ctrl|shift|ctrl,shift -> multimea tastelor tinute; None cand lipseste (ecranul citeste tastatura receptorului)."""
	if text is None:
		return None
	alese = frozenset(t.strip() for t in text.lower().split(",") if t.strip())
	if not alese <= frozenset(MODURI):
		raise ValueError("mod trebuie sa fie ctrl, shift sau ctrl,shift")
	return alese


def _punct(request, M, px, py, pp_x, pp_y):
	"""(x, y) in pixelii ecranului enigma2, din x/y (pixeli) sau din procente; (None, None) cand lipsesc."""
	xp, yp = _numar(request, pp_x), _numar(request, pp_y)
	if xp is not None and yp is not None:
		if not (-1.0 <= xp <= 101.0 and -1.0 <= yp <= 101.0):
			raise ValueError("procentele trebuie sa fie intre 0 si 100")
		return M.dinProcente(xp, yp)
	x, y = _numar(request, px, int), _numar(request, py, int)
	if x is not None and y is not None:
		w, h = M.marimeEcran()
		if not (0 <= x < w and 0 <= y < h):
			raise ValueError("x, y trebuie sa fie in ecran (%dx%d)" % (w, h))
		return x, y
	return None, None


def raspunde(request, sesiune, apasa, M=None, acces_ssh=None):
	"""Lucrul rutei: (corp, cod_http). Separat de resursa, ca probele de pe PC sa-l ruleze fara twisted."""
	if acces_ssh is None:
		from . import acces_ssh_web as acces_ssh
	refuz = acces_ssh.refuzEcranDeschis(request)
	if refuz is not None:
		return refuz, 403
	if M is None:
		from Components import HdsMouseEcran as M
	fel = _arg(request, "fel") or ""
	if fel not in M.GESTURI:
		return {"result": False, "message": _t("'fel' trebuie sa fie unul din: %s") % ", ".join(M.GESTURI)}, 400
	try:
		x, y = _punct(request, M, "x", "y", "xp", "yp")
		x0, y0 = _punct(request, M, "x0", "y0", "x0p", "y0p")
		clicuri = max(1, min(3, _numar(request, "clicuri", int) or 1))
		pasi = max(-M.PASI_MAXIM, min(M.PASI_MAXIM, _numar(request, "pasi", int) or 0))
		nou = _arg(request, "nou") == "1"
		mod = _mod(_arg(request, "mod"))
		# textul fara strip: spatiul e un semn
		brut = request.args.get(b"text")
		text = brut[0].decode("utf-8", "strict") if brut else ""
	except (ValueError, TypeError) as eroare:
		return {"result": False, "message": "parametri gresiti: %s" % eroare}, 400
	if fel in ("clic", "dublu", "drag") and x is None:
		return {"result": False, "message": "lipseste locul: xp si yp (procente) sau x si y (pixeli)"}, 400
	if fel == "text" and not 0 < len(text) <= M.TEXT_MAXIM:
		return {"result": False, "message": "text: intre 1 si %d semne" % M.TEXT_MAXIM}, 400
	try:
		extra = {"mod": mod} if mod is not None else {}
		rezultat = _mouse(sesiune, apasa, M).gest(fel, x, y, clicuri=clicuri, pasi=pasi, x0=x0, y0=y0, nou=nou, text=text,
			**extra)
	except Exception as eroare:
		print("[HdsWebControl] mouse %s: %s" % (fel, eroare))
		return {"result": False, "message": "mouse: %s" % eroare}, 500
	corp = {"result": True, "fel": fel}
	corp.update(rezultat)
	return corp, 200


def rute(HdsJsonResource, resource, sesiune, apasa):
	"""{b"mouse": resursa}. sesiune() da sesiunea enigma2 (ecranul de deasupra: current_dialog), apasa(cod) trimite o tasta
	ca telecomanda din web (plugin.py, _trimiteTasta)."""

	class MouseResource(HdsJsonResource):
		# GET ramane pentru scripturile cu ?token=; din browser, POST cu antetul CSRF (schimbaCeva, ca remotecontrol)
		schimbaCeva = True

		def render_POST(self, request):
			return self.render_GET(request)

		def render_GET(self, request):
			corp, cod = raspunde(request, sesiune, apasa)
			return self._raspunde(request, corp, cod)

	return {b"mouse": MouseResource()}
