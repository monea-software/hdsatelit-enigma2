# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# intrari_web.py: trei ecrane de pe televizor in interfata web (HdsWebControl), paginile /dispozitive-intrare,
# /taste-rapide si /skin.
#
# Orice ecran sau setare de pe receptor are pereche in interfata web. Pe televizor:
# - Meniu > Setari > Sistem & Dispozitive > Remote Control Setup (Screens/InputDeviceSetup.py): dispozitivele de intrare
#   (/dev/input/event*) si, pentru fiecare, "Change repeat and delay settings?", intervalul dintre taste la repetare si
#   intarzierea pana incepe repetarea (config.inputDevices.<dispozitiv>.*), cu intrebarea "Use this input device
#   settings?" la Verde. config.misc.rcused nu e un rand al ecranului (alege numai iconita), deci nu e nici aici. Ecranul
#   Telecomenzi (HdsTelecomenzi, /telecomenzi) e altul: pagina pune legatura spre el;
# - ... > Butoane colorate si taste rapide (Screens/ButtonSetup.py):
#   tastele barei, cu aceleasi actiuni si salvare in config.hds_buttons;
# - ... > Butoane colorate si taste rapide > Lista butonului albastru (Screens/ButtonSetup.HdsListaAlbastra): ce apare
#   pe ALBASTRU si in ce ordine (config.hds_albastru, Components/HdsTasteRapide.schimba_albastru), pagina /lista-albastra;
# - Meniu > Setari > Interfata & Aspect > Aspectul ecranelor (Plugins/SystemPlugins/SkinSelector): skinurile instalate cu
#   previzualizarea lor (prev.png, servit numai pentru dosarele din lista), alegerea (config.skin.primary_skin, verificata
#   ca pe televizor: fisierul trebuie sa fie un skin; ecranele HD Satelit se scaleaza la rezolutia lui, iar la un skin
#   mai ingust de 1024 de puncte se spune ca literele lor sunt mici: HdsSkinuri.avertismentRezolutie) si intrebarea de
#   repornire a interfetei, apoi TryQuitMainloop 3, si aspectul meniului (tasta galbena, config.skin.layout_meniu);
#   skinul cu care merge interfata acum si, daca skinul ales nu a pornit, motivul intoarcerii pe HDSatelit
#   (Components/HdsSkinuri.py, pornirea sigura); legaturi spre /tema-tv si /culori-skin.
#
# O SINGURA LOGICA: Components/HdsDispozitiveIntrare.py, Components/HdsTasteRapide.py, Components/HdsSkinuri.py,
# folosite si de ecranele de pe televizor; repornirea interfetei: Components/HdsAlimentare.deschide (aceeasi cale ca
# intrarea "Restart Interface" din meniu, dupa 1,5 s, ca raspunsul sa plece inainte).
#
# Setarile unui dispozitiv de intrare si repornirea interfetei se fac in doi pasi (meniu_comun_web: intrebarea, apoi un
# cod de unica folosinta), numai din browserul conectat (nu cu ?token=), ca intrebarile de pe televizor.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/dispozitive-intrare                    dispozitivele si setarile lor, limitele din config
#   POST /api/dispozitive-intrare-seteaza?dispozitiv=eventN&activ=0|1&repetare=<ms>&intarziere=<ms>   (+ pas / cod)
#   GET  /api/taste-rapide                           tastele si actiunile de ales
#   POST /api/taste-rapide-seteaza                    o valoare straina nu schimba nimic
#   GET  /api/skin                                   skinurile (cautarea prin ${datadir}/enigma2 pe un fir), alegerea,
#                                                    aspectul meniului
#   GET  /api/skin-poza?nume=<skin>                  previzualizarea (PNG sau JPEG, cel mult 2 MiB)
#   POST /api/skin-alege?nume=<skin>                 ca OK pe ecran (se vede dupa repornirea interfetei)
#   POST /api/skin-aspect?aspect=lista|dale          ca tasta galbena
#   POST /api/skin-reporneste                        (+ pas / cod) repornirea interfetei
#   POST /api/skin-sterge?nume=<skin>                (+ pas / cod) ca ROSU pe ecran: stergerea temei (Components/HdsTemaStergere.py);
#                                                    tema de pe ecran se sterge dupa repornirea interfetei cu tema HD Satelit
#   GET  /api/lista-albastra                        randurile butonului ALBASTRU si tot ce se poate pune
#   POST /api/lista-albastra-schimba?actiune=comuta|sus|jos|fabrica&id=<rand>   salvat pe loc
#   GET  /dispozitive-intrare, /taste-rapide, /skin, /lista-albastra  paginile
#
# FIRUL: totul pe firul enigma2 si scurt, afara de cautarea skinurilor (os.walk prin tot dosarul, pe un fir:
# meniu_comun_web.peFir). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC pun in DEP modulele,
# config, configfile, iInputDevices, radacina skinurilor, sesiunea si peFir.

MAX_POZA = 2 * 1024 * 1024
CHEI_DISPOZITIV = ("dispozitiv", "activ", "repetare", "intarziere", "pas", "cod")
TIPURI = ("remote", "keyboard", "mouse")

# ce dau probele de pe PC: "HdsDispozitiveIntrare", "HdsTasteRapide", "HdsSkinuri", "HdsAlimentare", "dispozitive"
# (iInputDevices), "config", "configfile", "radacina", "poza_lipsa", "sesiune", "peFir", "skinPornit" (functia care da
# skinul cu care a pornit interfata), "refuz" (fisierul refuzului din RAM)
DEP = {}

_STEAG_SKIN = [False]


def _mc():
	from . import meniu_comun_web
	return meniu_comun_web


def _t(text):
	return _mc()._t(text)


def _dep(nume):
	if nume in DEP:
		return DEP[nume]
	if nume in ("HdsDispozitiveIntrare", "HdsTasteRapide", "HdsSkinuri", "HdsAlimentare"):
		return __import__("Components." + nume, fromlist=[nume])
	if nume == "dispozitive":
		from Components.InputDevice import iInputDevices
		return iInputDevices
	if nume == "config":
		from Components.config import config
		return config
	if nume == "configfile":
		from Components.config import configfile
		return configfile
	if nume == "radacina":
		return _dep("HdsSkinuri").radacina()
	if nume == "poza_lipsa":
		from Tools.Directories import resolveFilename, SCOPE_PLUGINS
		return resolveFilename(SCOPE_PLUGINS, _dep("HdsSkinuri").POZA_LIPSA)
	if nume == "sesiune":
		return _mc().sesiune()
	if nume == "peFir":
		return _mc().peFir
	if nume == "skinPornit":
		return _dep("HdsSkinuri").skinPornit
	if nume == "refuz":
		return None      # fisierul din RAM al lui HdsSkinuri (REFUZ)
	if nume in ("HdsTemaStergere", "HdsExtensiiLucru"):
		return __import__("Components." + nume, fromlist=[nume])
	if nume == "plugins":
		from Components.PluginComponent import plugins
		return plugins
	if nume == "HdsPartiTema":
		from Components import HdsPartiTema
		return HdsPartiTema
	if nume == "setari_web":
		return __import__(__package__ + "." + nume, fromlist=[nume])
	raise KeyError(nume)


def _alegeri(el):
	"""[[valoare, text]] dintr-o setare ConfigSelection (aceleasi alegeri ca pe televizor, traduse acolo)."""
	alegeri = el.choices.choices
	if not isinstance(alegeri, list):
		alegeri = list(alegeri.items())
	rez = []
	for x in alegeri:
		if isinstance(x, tuple):
			rez.append([str(x[0]), str(x[1]) if x[1] else str(x[0])])
		else:
			rez.append([str(x), str(x)])
	return rez


def _doiPasi(request, argumente, actiune, tinta, intrebare, buton, detalii, fapta):
	mc = _mc()
	refuz = mc.numaiBrowser(request)
	if refuz:
		return {"result": False, "message": refuz}
	if argumente.get("pas") == "renunta":
		mc.uita(actiune, tinta)
		return {"result": True, "message": _t("Nu s-a schimbat nimic.")}
	cod = argumente.get("cod")
	if cod:
		if not mc.verifica(actiune, tinta, cod):
			return mc.codGresit()
		return fapta()
	return mc.raspunsIntrebare(actiune, tinta, intrebare, buton, detalii)


# ------------------------------------------------------------------ dispozitivele de intrare

def _glisor(el):
	return [int(el.min), int(el.max), int(el.increment or 1)]


def stareDispozitive():
	"""Pentru GET /api/dispozitive-intrare."""
	HD = _dep("HdsDispozitiveIntrare")
	D = _dep("dispozitive")
	config = _dep("config")
	rez = []
	for x, nume, tip in HD.lista(D, config):
		s = HD.sectiune(x, config)
		rez.append({"dispozitiv": x, "nume": _t(nume), "tip": tip if tip in TIPURI else "",
			"activ": bool(s.enabled.value), "repetare": int(s.repeat.value), "intarziere": int(s.delay.value),
			"repetare_limite": _glisor(s.repeat), "intarziere_limite": _glisor(s.delay)})
	return {"result": True, "dispozitive": rez}


def _ms(text, el):
	"""Numarul de milisecunde, daca e unul din pasii glisorului de pe televizor, altfel None."""
	if text is None or not text.isdigit() or len(text) > 6:
		return None
	n = int(text)
	minim, maxim, pas = _glisor(el)
	if n < minim or n > maxim or (n - minim) % pas:
		return None
	return n


def seteazaDispozitiv(request):
	"""POST /api/dispozitive-intrare-seteaza: ca Verde si Da pe ecranul dispozitivului."""
	HD = _dep("HdsDispozitiveIntrare")
	D = _dep("dispozitive")
	config = _dep("config")
	a = _mc().argumente(request, CHEI_DISPOZITIV, 20)
	x = a.get("dispozitiv", "")
	s = HD.sectiune(x, config)
	if s is None or x not in [d for d, _n, _t2 in HD.lista(D, config)]:
		return {"result": False, "message": _t("Dispozitivul %s nu există pe receptor.") % x[:20]}
	if a.get("activ") not in ("0", "1"):
		return {"result": False, "message": _t("Se alege cu activ=1 sau activ=0.")}
	activ = a["activ"] == "1"
	repetare = intarziere = None
	if activ:
		for cheie, el in (("repetare", s.repeat), ("intarziere", s.delay)):
			if cheie in a:
				n = _ms(a[cheie], el)
				if n is None:
					minim, maxim, pas = _glisor(el)
					return {"result": False, "message": _t("Valoarea %s ms nu e bună: se alege între %d și %d ms, din %d în %d.")
						% (a[cheie][:8], minim, maxim, pas, pas)}
				if cheie == "repetare":
					repetare = n
				else:
					intarziere = n
	tinta = "%s|%d|%s|%s" % (x, activ, repetare, intarziere)
	nume = _t(D.getDeviceName(x))

	def fapta():
		HD.aplica(x, activ, repetare, intarziere, D, config, _dep("configfile"))
		rez = stareDispozitive()
		rez.update(result=True, message=_t("Salvat."))
		return rez

	return _doiPasi(request, a, "dispozitive-intrare", tinta, _t("Use this input device settings?"), _t("Da, folosește-le"),
		[_t("Dispozitivul: %s") % nume], fapta)


# ------------------------------------------------------------------ butoanele colorate

_PROFILURI_TASTE = []
_EROARE_PROFILURI_TASTE = ""


def stareTaste():
	"""Aceeasi lista de taste si actiuni ca pe televizor."""
	# The main parser is already loaded at startup; only read its RAM state here.
	import sys
	keymap = sys.modules.get("keymapparser")
	TR = _dep("HdsTasteRapide")
	b = TR.actualizeaza_alegeri(_dep("config"))
	tt = lambda k, text: TR.text_tasta(k, text, _t)  # traduse acum, nu la importul listelor
	butoane = [{"cheie": k, "text": tt(k, text), "valoare": getattr(b, k).value} for k, text in TR.BUTOANE]
	scurte = [{"cheie": k, "text": tt(k, text), "valoare": getattr(b, k).value} for k, text in TR.SCURTE]
	u = TR.initConfigProfil(_dep("config"))
	profil = []
	implicite = dict(TR.VALORI_IMPLICITE)
	for k, implicit, text in TR.PROFIL_SETARI:
		v = getattr(u, k).value
		alegeri = [["1", _t("Da")], ["0", _t("Nu")]] if isinstance(implicit, bool) else _alegeri(getattr(u, k))
		profil.append({"cheie": k, "text": tt(k, text), "valoare": str(int(v)) if isinstance(v, bool) else str(v), "alegeri": alegeri})
		implicite[k] = str(int(implicit)) if isinstance(implicit, bool) else str(implicit)
	return {"result": True, "keymap_avertisment": keymap.recoveryMessage(_t) if keymap else "", "butoane": butoane, "scurte": scurte, "profil": profil,
		"profiluri_mele": list(_PROFILURI_TASTE), "profiluri_eroare": _EROARE_PROFILURI_TASTE, "poza_taste": TR.poza_profil("", _dep("config")),
		"asezare_ajutor": tt("", TR.ASEZARE_AJUTOR),
		"actiuni": _alegeri(getattr(b, TR.BUTOANE[0][0])), "implicite": implicite,
		"nume_taste": dict(TR.ETICHETE_TASTE),
		"sensuri": dict((c, TR.profil_context(c, config=_dep("config"))) for c in
			("live", "radio", "channel_list", "movie_list", "movie", "menu", "setup", "timeshift"))}


def cereTaste():
	# The HTTP route refreshes the file; stareTaste itself only reads config and RAM.
	def citit(lista):
		global _PROFILURI_TASTE, _EROARE_PROFILURI_TASTE
		_PROFILURI_TASTE = [{"id": x["id"], "nume": x["profile"]["name"]} for x in lista]
		_EROARE_PROFILURI_TASTE = ""
		return stareTaste()
	def esec(f):
		global _PROFILURI_TASTE, _EROARE_PROFILURI_TASTE
		_PROFILURI_TASTE = []
		_EROARE_PROFILURI_TASTE = _eroareProfilTaste(f.value)
		return stareTaste()
	return _dep("HdsTasteRapide").operatie_profil("lista").addCallbacks(citit, esec)


def _eroareProfilTaste(e):
	return str(e) if isinstance(e, (ValueError, _dep("HdsTasteRapide").EroareSalvareTaste)) else _t("Nu pot salva profilurile. Fișierul tău a rămas neatins.")


def _raspunsTaste(result, message):
	def gata(rez):
		rez.update(result=result, message=message)
		return rez
	return cereTaste().addCallback(gata)


def seteazaTaste(request):
	"""POST /api/taste-rapide-seteaza: ca Verde pe ecran. Toate valorile trimise trebuie sa fie bune."""
	TR = _dep("HdsTasteRapide")
	if TR.profil_ocupat():
		return {"result": False, "message": _t("Se lucrează la un profil. Încearcă din nou după terminare.")}
	config = _dep("config")
	b = TR.actualizeaza_alegeri(config)
	u = TR.initConfigProfil(config)
	chei = [k for k, _text in TR.BUTOANE + TR.SCURTE]
	profil = dict((k, implicit) for k, implicit, _text in TR.PROFIL_SETARI)
	chei += list(profil)
	a = _mc().argumente(request, chei, 128, limita=len(chei) + 8)
	if not a:
		rez = stareTaste()
		rez.update(result=False, message=_t("Nu s-a trimis nicio setare."))
		return rez
	noi = []
	for k in chei:
		if k in a:
			el = getattr(u if k in profil else b, k)
			boolean = k in profil and isinstance(profil[k], bool)
			alegeri = ("0", "1") if boolean else [x[0] for x in _alegeri(el)]
			if a[k] not in alegeri:
				rez = stareTaste()
				rez.update(result=False, message=_t("Acțiunea %s nu există.") % a[k][:20])
				return rez
			noi.append((el, a[k] == "1" if boolean else a[k]))
	for el, v in noi:
		el.value = v
		el.save()
	TR.salveaza(config)
	_dep("configfile").save()
	rez = stareTaste()
	rez.update(result=True, message=_t("Salvat."))
	return rez


def _argumenteProfilTaste(request):
	TR = _dep("HdsTasteRapide")
	rez = {}
	for k, values in (getattr(request, "args", None) or {}).items():
		k = k.decode("utf-8", "strict") if isinstance(k, bytes) else k
		if k not in ("actiune", "id", "nume", "continut"):
			continue
		if len(values) != 1:
			raise ValueError(_t("Cererea profilului nu este validă."))
		v = values[0]
		v = v.decode("utf-8", "strict") if isinstance(v, bytes) else v
		limita = TR.MAX_PROFIL if k == "continut" else (64 if k == "nume" else 40)
		if len(v.encode("utf-8")) > (limita if k == "continut" else limita * 4) or (k != "continut" and len(v) > limita):
			raise ValueError(_t("Profilul sau numele lui este prea mare."))
		rez[k] = v
	return rez


def exportaProfilTaste(request):
	a = _argumenteProfilTaste(request)
	return _dep("HdsTasteRapide").operatie_profil("exporta", ident=a.get("id", ""))


def profilTaste(request):
	"""The operation finishes only after worker IO and main-thread configuration."""
	TR = _dep("HdsTasteRapide")
	try:
		a = _argumenteProfilTaste(request)
		d = TR.operatie_profil(a.get("actiune"), _dep("config"), _dep("configfile"),
			ident=a.get("id", ""), nume=a.get("nume", ""), continut=a.get("continut"))
	except (ValueError, OSError) as e:
		return {"result": False, "message": _eroareProfilTaste(e)}
	def gata(rez):
		mesaj = (_t("Profil aplicat. Setări sărite pentru taste sau funcții care lipsesc: %d.") % rez
			if a.get("actiune") == "aplica" else _t("Salvat."))
		return _raspunsTaste(True, mesaj)
	def esec(f):
		mesaj = (_t("Nu pot confirma salvarea tastelor pe disc.") if a.get("actiune") == "aplica"
			and isinstance(f.value, OSError) and not isinstance(f.value, TR.EroareSalvareTaste) else _eroareProfilTaste(f.value))
		return {"result": False, "message": mesaj}
	return d.addCallback(gata).addErrback(esec)


# ------------------------------------------------------------------ skinul

def _stergere(p):
	"""ce vede pagina din planul stergerii unei teme (HdsTemaStergere.plan)"""
	if not p:
		return {"poate": False, "motiv": ""}
	return {"poate": bool(p["poate"]), "motiv": p["motiv"] if not p["poate"] else "", "pe_ecran": bool(p.get("pe_ecran"))}


def _lucrareTema():
	"""lucrarea opkg din Extensii, cand sterge o tema (pagina se uita la ea pana se termina), sau None"""
	try:
		l = _dep("HdsExtensiiLucru").STARE["lucrare"]
	except Exception:
		return None
	if l is None or not l.plan.get("tema"):
		return None
	r = l.rezultat or {}
	return {"faza": l.faza, "tema": l.plan.get("tema"), "titlu": l.titluLucru() if l.faza == "lucru" else r.get("titlu", ""),
		"stare": r.get("stare", ""), "reusit": bool(r.get("reusit"))}


def stareSkin(skinuri, ales, aspect, aspecte, activ=None, refuz=None, stare_tema="", planuri=None, lucrare=None,
		incomplete=(), parti_tema=None):
	"""Corpul raspunsului GET /api/skin, din lista citita pe fir si din setarile citite pe firul enigma2. `incomplete`:
	temele ramase fara skin.xml (HdsTemaStergere.incomplete), la coada listei, numai cu Sterge"""
	S = _dep("HdsSkinuri")
	activ = activ or S.DOSAR_IMAGINE
	planuri = planuri or {}
	incomplete = [x for x in incomplete if x not in skinuri]
	return {"result": True,
		"skinuri": [{"nume": x, "eticheta": _t("Skinul implicit") if x == S.IMPLICIT else x,
			"ales": x not in incomplete and (x == ales or (ales is None and x == S.IMPLICIT)), "activ": x == activ,
			"imaginii": x == S.DOSAR_IMAGINE, "incompleta": x in incomplete, "stergere": _stergere(planuri.get(x))}
			for x in list(skinuri) + incomplete],
		"aspect": aspect, "aspecte": aspecte, "activ": activ, "refuz": refuz or "", "stare_tema": stare_tema or "",
		"lucrare": lucrare, "parti_tema": parti_tema}


def _partiTema(radacina, ales):
	"""Read only convention data on the list worker; no theme code is loaded or run."""
	import os
	from urllib.parse import quote
	S = _dep("HdsSkinuri")
	if ales in (None, S.IMPLICIT, S.DOSAR_IMAGINE):
		return None
	try:
		cale = S.caleSkin(radacina, ales)
		if not cale:
			return None
		try:
			os.listdir(os.path.join(os.path.dirname(cale), "allScreens"))
		except (FileNotFoundError, NotADirectoryError):
			return None
		P = _dep("HdsPartiTema")
		if not P.areParti(os.path.dirname(cale)):
			return None
		instalat = P.pluginInstalat()
	except OSError:
		return {"tema": ales, "instalat": None, "drum": "", "setari_web": [],
			"mesaj": _t("Părțile temei nu pot fi citite acum.")}
	setari = []
	if instalat:
		try:
			for e in _dep("setari_web").listaPluginuri():
				if e["id"].startswith("Extensions/AtileHD/"):
					setari.append({"href": "/setari?id=" + quote(e["id"], safe=""),
						"text": e.get("titlu") or e.get("text") or _t("Setările pluginului")})
		except Exception:
			pass
		mesaj = _t("Pluginul de configurare este instalat.")
		mesaj += " " + _t("Părțile temei se aleg pe televizor, în pluginul de configurare al temei.")
	else:
		mesaj = _t("Pluginul de configurare a părților temei nu este instalat. Imaginea îl cere automat după pornirea reușită cu această temă.")
	return {"tema": ales, "instalat": instalat, "drum": "", "mesaj": mesaj, "setari_web": setari}


def _planuri(skinuri, radacina, activ, ales):
	try:
		return _dep("HdsTemaStergere").planuri(skinuri, radacina, "/", activ, ales, _t)
	except Exception as eroare:
		_mc().jurnal("skin: stergerea temelor: %r" % eroare)
		return {}


def _incomplete(radacina):
	try:
		return _dep("HdsTemaStergere").incomplete(radacina)
	except Exception as eroare:
		_mc().jurnal("skin: temele incomplete: %r" % eroare)
		return []


def _listaSkin(radacina, ales, aspect, aspecte, activ, refuz, stare_tema, lucrare):
	skinuri = _dep("HdsSkinuri").lista(radacina)
	incomplete = _incomplete(radacina)
	return stareSkin(skinuri, ales, aspect, aspecte, activ, refuz, stare_tema,
		_planuri(skinuri + [x for x in incomplete if x not in skinuri], radacina, activ, ales), lucrare, incomplete,
		_partiTema(radacina, ales))


def _aspecte(config):
	text = {"lista": _t("Listă"), "dale": _t("Dale")}
	return [[v, text.get(v, t)] for v, t in _alegeri(config.skin.layout_meniu)]


def cereSkin(request):
	"""GET /api/skin: setarile pe firul enigma2, cautarea skinurilor pe un fir."""
	S = _dep("HdsSkinuri")
	config = _dep("config")
	if _STEAG_SKIN[0]:
		return {"result": False, "message": _t("Lista skinurilor se citește deja. Încearcă din nou peste câteva secunde.")}
	ales = S.curent(config)
	aspect = S.aspect(config)
	aspecte = _aspecte(config)
	radacina = _dep("radacina")
	activ = S.numeDinValoare(_dep("skinPornit")()) or S.DOSAR_IMAGINE
	refuz = S.textRefuz(S.refuzDeSpus(_dep("refuz")), _t)
	stare_tema = S.textStareTema(_t)
	lucrare = _lucrareTema()
	return _dep("peFir")(request, lambda: _listaSkin(radacina, ales, aspect, aspecte, activ, refuz, stare_tema, lucrare),
		_STEAG_SKIN, 20)


def _numeSkin(a):
	S = _dep("HdsSkinuri")
	nume = a.get("nume", "")
	if S.caleSkin(_dep("radacina"), nume) is None:
		return None
	return nume


def pozaSkin(a):
	"""(octetii, felul) sau (None, motivul)."""
	S = _dep("HdsSkinuri")
	nume = _numeSkin(a)
	if nume is None:
		return None, _t("Tema nu există.")
	cale = S.previzualizare(_dep("radacina"), nume, _dep("poza_lipsa"))
	try:
		with open(cale, "rb") as f:
			date = f.read(MAX_POZA + 1)
	except (IOError, OSError):
		return None, _t("Previzualizarea lipsește.")
	if len(date) > MAX_POZA:
		return None, _t("Previzualizarea nu e bună.")
	if date[:8] == b"\x89PNG\r\n\x1a\n":
		return date, b"image/png"
	if date[:3] == b"\xff\xd8\xff":
		return date, b"image/jpeg"
	return None, _t("Previzualizarea nu e bună.")


def alegeSkin(request):
	"""POST /api/skin-alege: ca OK pe ecran (aceeasi verificare a fisierului, acelasi avertisment de rezolutie)."""
	S = _dep("HdsSkinuri")
	a = _mc().argumente(request, ("nume", "aplicare"), 120)
	mod = a.get("aplicare", "pornire")
	if mod not in ("acum", "pornire"):
		return {"result": False, "message": _t("Alege Aplică acum sau La următoarea pornire.")}
	if mod == "acum":
		refuz = _mc().numaiBrowser(request)
		if refuz:
			return {"result": False, "message": refuz}
		if _dep("sesiune") is None:
			return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}
	nume = _numeSkin(a)
	if nume is None:
		return {"result": False, "message": _t("Tema nu există.")}
	bun, mesaj, avertisment = S.alege(nume, _dep("config"), _dep("radacina"), _t, _dep("refuz"))
	if not bun:
		return {"result": False, "message": mesaj}
	_dep("configfile").save()
	pornita = mod == "acum" and _dep("HdsAlimentare").deschide(_dep("sesiune"), "interfata", dupa_ms=1500)
	if mod == "acum" and not pornita:
		mesaj += " " + _t("Interfața nu este gata pentru repornire.")
	return {"result": mod != "acum" or bool(pornita), "message": (avertisment + " " + mesaj) if avertisment else mesaj, "avertisment": avertisment,
		"reporneste": bool(pornita)}


def stergeSkin(request):
	"""POST /api/skin-sterge: ca ROSU pe ecran, in doi pasi (intrebarea, apoi codul). Aceeasi hotarare ca pe televizor
	(HdsTemaStergere.plan); tema din pachet prin lucrarea opkg a Extensiilor, tema de pe ecran dupa repornirea interfetei."""
	S = _dep("HdsSkinuri")
	T = _dep("HdsTemaStergere")
	config = _dep("config")
	a = _mc().argumente(request, ("nume", "pas", "cod"), 120)
	nume = a.get("nume", "")
	radacina = _dep("radacina")

	def planAcum():
		activ = S.numeDinValoare(_dep("skinPornit")()) or S.DOSAR_IMAGINE
		return T.plan(nume, radacina, "/", activ, S.curent(config), _t)

	if not T.numeBun(nume):
		return {"result": False, "message": _t("Tema nu există.")}
	if a.get("pas") == "renunta":
		return _doiPasi(request, a, "skin-sterge", nume, "", "", None, None)
	p = planAcum()
	if not p["poate"]:
		return {"result": False, "message": p["motiv"]}

	def fapta():
		p = planAcum()
		if not p["poate"]:
			return {"result": False, "message": p["motiv"]}
		if p["pe_ecran"]:
			sesiune = _dep("sesiune")
			if sesiune is None:
				return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}
			if not T.programeaza(p, config):
				return {"result": False, "message": S.textMotiv(S.MOTIV_SCRIERE, "", _t)}
			_dep("configfile").save()
			if not _dep("HdsAlimentare").deschide(sesiune, "interfata", dupa_ms=1500):
				return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}
			return {"result": True, "reporneste": True, "message": _t("Interfața se repornește cu tema %s, apoi tema %s se "
				"șterge. Pagina se reîncarcă singură în câteva secunde.") % (T.titluTema(p["urmatoarea"]), nume)}
		if p["fel"] == T.FEL_PACHET:
			L = _dep("HdsExtensiiLucru")
			motiv = L.motivOcupat(None)
			if motiv is not None:
				return {"result": False, "message": motiv[0]}
			plan, eroare = T.planPachet(p, traducere=_t)
			if plan is None:
				return {"result": False, "message": eroare[0]}
			plan.setdefault("titluri", L.titluri(L.catalogLaZi() or L.incarcaCatalog()))
			l = L.pornesteLucrarea(plan, plugins=_dep("plugins"), din_web=True)

			def gata(fel, *date):
				if fel == "gata":
					l.lasa(gata)
					if T.dupaPachet(nume, config, radacina):
						_dep("configfile").save()
			l.asculta(gata)
			return {"result": True, "message": _t("A pornit ștergerea temei %s.") % nume, "lucrare": _lucrareTema()}
		bun, mesaj = T.stergeDosarAles(p, config, radacina, _t)
		if bun:
			_dep("configfile").save()
		return {"result": bun, "message": mesaj}

	return _doiPasi(request, a, "skin-sterge", nume, p["intrebare"], _t("Șterge"), p["detalii"], fapta)


def aspectMeniu(request):
	"""POST /api/skin-aspect: ca tasta galbena (aspectul meniului)."""
	S = _dep("HdsSkinuri")
	config = _dep("config")
	a = _mc().argumente(request, ("aspect",), 12)
	v = a.get("aspect", "")
	if v not in [x[0] for x in _alegeri(config.skin.layout_meniu)]:
		return {"result": False, "message": _t("Se alege aspect=lista sau aspect=dale.")}
	S.seteazaAspect(v, config)
	_dep("configfile").save()
	return {"result": True, "message": _t("Salvat."), "aspect": S.aspect(config)}


def reporneste(request):
	"""POST /api/skin-reporneste: Da pe intrebarea de pe televizor (TryQuitMainloop 3), cu codul."""
	A = _dep("HdsAlimentare")
	sesiune = _dep("sesiune")
	a = _mc().argumente(request, ("pas", "cod"), 40)
	detalii = []
	try:
		if A.vaIntreba(sesiune):
			detalii.append(_t("Pe televizor se cere o confirmare: o înregistrare e în curs sau începe curând. Repornirea "
				"se face numai dacă răspunzi Da acolo."))
	except Exception as eroare:
		_mc().jurnal("skin: %r" % eroare)

	def fapta():
		if not A.deschide(sesiune, "interfata", dupa_ms=1500):
			return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}
		return {"result": True, "reporneste": True,
			"message": _t("Interfața se repornește. Pagina se reîncarcă singură în câteva secunde.")}

	return _doiPasi(request, a, "skin-reporneste", "", _t("GUI needs a restart to apply a new skin\nDo you want to Restart "
		"the GUI now?"), _t("Da, repornește interfața"), detalii, fapta)


# ------------------------------------------------------------------ rutele si paginile

def _corpAlbastru(st, result=True, message=""):
	lista = st["lista"]
	return {"result": result, "message": message, "lista": list(lista),
		"catalog": [dict(x, ales=x["id"] in lista) for x in st["catalog"]]}


def stareAlbastru(request=None):
	"""GET /api/lista-albastra: aceeasi alegere ca ecranul Lista butonului albastru de pe televizor
	(Components/HdsTasteRapide.stare_albastru)."""
	TR = _dep("HdsTasteRapide")
	return _corpAlbastru(TR.stare_albastru(_dep("config"), tr=_t, pluginuri=_dep("plugins")))


def schimbaAlbastru(request):
	"""POST /api/lista-albastra-schimba?actiune=comuta|sus|jos|fabrica&id=<rand>: ca OK, GALBEN, ALBASTRU si ROSU pe
	ecranul de pe televizor; se salveaza pe loc."""
	TR = _dep("HdsTasteRapide")
	a = _mc().argumente(request, ("actiune", "id"), 200)
	st = TR.schimba_albastru(a.get("actiune", ""), a.get("id", ""), _dep("config"), _dep("configfile"), tr=_t,
		pluginuri=_dep("plugins"))
	if st is None:
		rez = stareAlbastru()
		rez.update(result=False, message=_t("Rândul nu mai există. Am citit lista din nou."))
		return rez
	return _corpAlbastru(st, True, _t("Salvat."))


def rute(baza, resource):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	def _eroare(self, request, eroare):
		_mc().jurnal("intrari: %r" % eroare)
		return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	def _asteapta(self, request, rez, raspunde=None):
		raspunde = raspunde or (lambda r: self._raspunde(request, r))
		if not hasattr(rez, "addCallbacks"):
			return raspunde(rez)
		from twisted.web.server import NOT_DONE_YET
		viu = [True]
		def inchis(f):
			viu[0] = False
			return None
		request.notifyFinish().addErrback(inchis)
		def trimite(date):
			if viu[0]:
				request.write(date)
				request.finish()
			return None
		def gata(r):
			if viu[0]:
				trimite(raspunde(r))
		def esec(f):
			if viu[0]:
				trimite(_eroare(self, request, f.value))
		rez.addCallback(gata).addErrback(esec)
		return NOT_DONE_YET

	def _citire(functie):
		class Citire(baza):
			def render_GET(self, request):
				try:
					rez = functie(request)
				except Exception as eroare:
					return _eroare(self, request, eroare)
				if not isinstance(rez, dict) and not hasattr(rez, "addCallbacks"):
					return rez          # NOT_DONE_YET from the existing skin worker
				return _asteapta(self, request, rez)
		return Citire()

	def _scriere(functie):
		class Scriere(baza):
			schimbaCeva = True

			def render_POST(self, request):
				try:
					return _asteapta(self, request, functie(request))
				except Exception as eroare:
					return _eroare(self, request, eroare)

			def render_GET(self, request):
				return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST
		return Scriere()

	class Poza(baza):
		def render_GET(self, request):
			try:
				date, fel = pozaSkin(_mc().argumente(request, ("nume",), 120))
			except Exception as eroare:
				return _eroare(self, request, eroare)
			if date is None:
				return self._eroare(request, fel, 404)
			request.setHeader(b"content-type", fel)
			request.setHeader(b"cache-control", b"private, max-age=3600")
			return date

	class ProfilFisier(baza):
		def render_GET(self, request):
			import json
			try:
				d = exportaProfilTaste(request)
			except (ValueError, OSError) as e:
				return self._eroare(request, _eroareProfilTaste(e), 400)
			def esec(f):
				f.trap(ValueError, OSError)
				return {"result": False, "message": _eroareProfilTaste(f.value)}
			d.addErrback(esec)
			def raspunde(p):
				if p.get("result") is False:
					return self._eroare(request, p["message"], 400)
				request.setHeader(b"content-type", b"application/json; charset=utf-8")
				request.setHeader(b"content-disposition", b'attachment; filename="profil-taste.json"')
				request.setHeader(b"cache-control", b"no-store")
				return json.dumps(p, ensure_ascii=False, indent=2).encode("utf-8")
			return _asteapta(self, request, d, raspunde)

	def _pagina(text):
		class Pagina(resource.Resource):
			isLeaf = True

			def render_GET(self, request):
				return _mc().pagina(request, text)
		return Pagina()

	api = {
		b"dispozitive-intrare": _citire(lambda r: stareDispozitive()),
		b"dispozitive-intrare-seteaza": _scriere(seteazaDispozitiv),
		b"taste-rapide": _citire(lambda r: cereTaste()),
		b"taste-rapide-seteaza": _scriere(seteazaTaste),
		b"taste-profil": _scriere(profilTaste),
		b"taste-profil-descarca": ProfilFisier(),
		b"lista-albastra": _citire(stareAlbastru),
		b"lista-albastra-schimba": _scriere(schimbaAlbastru),
		b"skin": _citire(cereSkin),
		b"skin-poza": Poza(),
		b"skin-alege": _scriere(alegeSkin),
		b"skin-aspect": _scriere(aspectMeniu),
		b"skin-reporneste": _scriere(reporneste),
		b"skin-sterge": _scriere(stergeSkin),
	}
	pagini = {
		b"dispozitive-intrare": _pagina(pagina_dispozitive),
		b"taste-rapide": _pagina(pagina_taste),
		b"lista-albastra": _pagina(pagina_albastru),
		b"skin": _pagina(pagina_skin),
	}
	return api, pagini


def _sablon(text, stil, config_pagina, intrare):
	mc = _mc()
	return mc.sablon(text, stil, config_pagina, {"__DRUM_MENIU__": mc.drumHtml(intrare)})


def pagina_dispozitive(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_DISPOZITIVE), stil, config_pagina, "input_device_setup")


def pagina_taste(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_TASTE), stil, config_pagina, "hds_button_setup")


def pagina_skin(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_SKIN), stil, config_pagina, "skin_setup")


PAGINA_DISPOZITIVE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dispozitive de intrare</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .sub{color:var(--text-slab);margin:0 0 14px;font-size:.92rem;line-height:1.45;}
  .glisor{display:flex;align-items:center;gap:10px;}
  .glisor input{flex:1;min-width:0;}
  .glisor output{min-width:72px;text-align:right;}
</style>
</head>
<body>
<main>
<h1>Dispozitive de intrare</h1>
<p class="sub">Telecomenzile, tastaturile și mouse-urile găsite de receptor la pornire. Pentru fiecare se poate schimba cât de repede se repetă o tastă ținută apăsat.</p>
<p class="mesaj" id="incarcare">Se citesc dispozitivele...</p>
<div id="continut" class="ascuns">
  <div id="lista"></div>
  <p class="nota ascuns" id="gol">Receptorul n-a găsit niciun dispozitiv de intrare la pornire.</p>
  <section class="card">
    <h2>Telecomenzi</h2>
    <p class="nota">Codurile tastelor, proba tastelor și folosirea altei telecomenzi au pagina lor.</p>
    <div class="butoane"><button type="button" id="spreTelecomenzi">Deschide Telecomenzi</button></div>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var TIP = {remote: "telecomandă", keyboard: "tastatură", mouse: "mouse"};
function rand(cutie, eticheta, control, id){
  var r = document.createElement("div"); r.className = "rand";
  var l = document.createElement("label"); l.textContent = eticheta; l.htmlFor = id; r.appendChild(l);
  r.appendChild(control); cutie.appendChild(r); return r;
}
function glisor(id, valoare, limite){
  var d = document.createElement("div"); d.className = "glisor";
  var i = document.createElement("input"); i.type = "range"; i.id = id;
  i.min = limite[0]; i.max = limite[1]; i.step = limite[2]; i.value = valoare;
  var o = document.createElement("output"); o.textContent = valoare + " ms";
  i.addEventListener("input", function(){ o.textContent = i.value + " ms"; });
  d.appendChild(i); d.appendChild(o); return d;
}
function card(x){
  var c = document.createElement("section"); c.className = "card";
  var h = document.createElement("h2"); h.textContent = x.nume; c.appendChild(h);
  var n = document.createElement("p"); n.className = "nota"; n.textContent = (TIP[x.tip] || "alt dispozitiv") + " · " + x.dispozitiv; c.appendChild(n);
  var s = document.createElement("select"); s.id = "activ-" + x.dispozitiv;
  [["1", "Da"], ["0", "Nu"]].forEach(function(v){ var o = document.createElement("option"); o.value = v[0]; o.textContent = v[1]; s.appendChild(o); });
  s.value = x.activ ? "1" : "0";
  rand(c, "Schimbi intervalul și întârzierea repetării?", s, s.id);
  var r1 = rand(c, "Intervalul dintre taste la repetare", glisor("repetare-" + x.dispozitiv, x.repetare, x.repetare_limite), "repetare-" + x.dispozitiv);
  var r2 = rand(c, "Întârzierea până începe repetarea", glisor("intarziere-" + x.dispozitiv, x.intarziere, x.intarziere_limite), "intarziere-" + x.dispozitiv);
  function vizibile(){ var da = s.value === "1"; r1.classList.toggle("ascuns", !da); r2.classList.toggle("ascuns", !da); }
  s.addEventListener("change", vizibile); vizibile();
  var b = document.createElement("div"); b.className = "butoane";
  var salv = document.createElement("button"); salv.type = "button"; salv.className = "principal"; salv.textContent = "Salvează";
  salv.addEventListener("click", function(){
    var q = new URLSearchParams(); q.set("dispozitiv", x.dispozitiv); q.set("activ", s.value);
    if(s.value === "1"){ q.set("repetare", $("repetare-" + x.dispozitiv).value); q.set("intarziere", $("intarziere-" + x.dispozitiv).value); }
    cuConfirmare("/api/dispozitive-intrare-seteaza", q, function(d){ if(d.result && d.dispozitive){ arata(d); } });
  });
  var inapoi = document.createElement("button"); inapoi.type = "button"; inapoi.textContent = "Pune înapoi valorile salvate";
  inapoi.addEventListener("click", function(){ mesaj(""); citeste(); });
  b.appendChild(salv); b.appendChild(inapoi); c.appendChild(b);
  var a = document.createElement("p"); a.className = "nota";
  a.textContent = "Cu Nu, intervalul și întârzierea se întorc la valorile din fabrică.";
  c.appendChild(a);
  return c;
}
function arata(d){
  var l = $("lista"); l.textContent = "";
  (d.dispozitive || []).forEach(function(x){ l.appendChild(card(x)); });
  $("gol").classList.toggle("ascuns", (d.dispozitive || []).length > 0);
}
function citeste(){
  return cerere("/api/dispozitive-intrare").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi dispozitivele."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("spreTelecomenzi").addEventListener("click", function(){ location.href = adresa("/telecomenzi"); });
citeste();
</script>
</body>
</html>
"""


PAGINA_TASTE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Butoane colorate și taste rapide</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .sub{color:var(--text-slab);margin:0 0 14px;font-size:.92rem;line-height:1.45;}
</style>
</head>
<body>
<main>
<h1>Butoane colorate și taste rapide</h1>
<p class="sub">Alege o funcție sau un plugin instalat pentru fiecare tastă, cât te uiți la televizor. Funcția obișnuită urmează profilul curent. Cifrele lungi se alocă în afara timeshiftului.</p>
<p class="mesaj" id="incarcare">Se citesc butoanele...</p>
<div id="continut" class="ascuns">
  <p class="sub" id="asezare-ajutor"></p>
  <section class="card"><h2>Liste și meniuri</h2><div id="profil"></div></section>
  <section class="card"><h2>Profilurile mele</h2>
    <p class="nota">Alegerea unui profil îl aplică pe loc. Așezările predefinite rămân puncte de plecare.</p>
    <label for="profilul-meu">Profilurile mele</label><select id="profilul-meu"></select>
    <label for="nume-profil">Numele profilului (poți lăsa gol)</label><input id="nume-profil" maxlength="64">
    <div class="butoane">
      <button type="button" id="profil-salveaza">Salvează ca profil</button>
      <button type="button" id="profil-redenumeste">Redenumește profilul</button>
      <button type="button" id="profil-sterge">Șterge profilul</button>
      <a id="profil-descarca" download="profil-taste.json">Descarcă profilul</a>
    </div>
    <label for="profil-fisier">Încarcă un profil</label><input id="profil-fisier" type="file" accept=".json,application/json">
    <label for="profil-text">Sau lipește aici conținutul profilului</label><textarea id="profil-text" rows="4" maxlength="65536"></textarea>
    <button type="button" id="profil-importa">Încarcă un profil</button>
    <p class="nota" id="profil-eroare"></p>
    <p class="nota" id="keymap-avertisment" role="status"></p>
  </section>
  <section class="card">
    <h2>Apăsarea scurtă</h2>
    <div id="scurte"></div>
    <p class="nota">Subcanalele se pot aloca unei taste sau se găsesc în Lista extensiilor.</p>
    <p class="nota">Ce apare în lista butonului albastru și în ce ordine alegi la</p>
    <div class="butoane"><button type="button" id="spreAlbastru">Lista butonului albastru</button></div>
  </section>
  <section class="card">
    <h2>Apăsarea lungă</h2>
    <p class="nota">Apăsare lungă: ține tasta apăsată ~1 s.</p>
    <div id="butoane"></div>
  </section>
  <section class="card"><h2>Tastele acestui ecran</h2>
    <label for="sensContext">Context</label><select id="sensContext">
      <option value="live">TV</option><option value="radio">Radio</option><option value="channel_list">Lista de canale</option>
      <option value="movie_list">Lista de filme</option><option value="movie">Film</option><option value="timeshift">Timeshift</option>
      <option value="menu">Meniu</option><option value="setup">Setări</option>
    </select><div id="sensuri"></div>
  </section>
  <div class="butoane">
    <button type="button" class="principal" id="salveaza">Salvează</button>
    <button type="button" id="renunta">Renunță</button>
    <button type="button" id="implicite">Valori implicite</button>
  </div>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var D = null, profilOcupat = false;
function randuri(c, lista, actiuni){
  c.textContent = "";
  lista.forEach(function(b){
    var r = document.createElement("div"); r.className = "rand";
    var l = document.createElement("label"); l.htmlFor = "b-" + b.cheie; l.textContent = b.text; r.appendChild(l);
    var s = document.createElement("select"); s.id = "b-" + b.cheie;
    (b.alegeri || actiuni).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
    s.value = b.valoare; r.appendChild(s); c.appendChild(r);
  });
}
function toate(){ return D.butoane.concat(D.scurte || [], D.profil || []); }
function arataSensuri(){
  var c = $("sensuri"); c.textContent = "";
  ((D.sensuri || {})[$("sensContext").value] || []).forEach(function(r){
    var p = document.createElement("p"); p.className = "nota";
    p.textContent = ((D.nume_taste || {})[r.key] || r.key.toUpperCase()) + ": " + "Scurt: " + r.text_short + ". " + "Lung: " + r.text_long;
    c.appendChild(p);
  });
}
function arata(d){
  D = d;
  $("keymap-avertisment").textContent = d.keymap_avertisment || "";
  $("asezare-ajutor").textContent = d.asezare_ajutor || "";
  randuri($("scurte"), d.scurte || [], d.actiuni);
  randuri($("butoane"), d.butoane, d.actiuni);
  randuri($("profil"), d.profil || [], []);
  var s = $("profilul-meu"); s.textContent = "";
  var gol = document.createElement("option"); gol.value = ""; gol.textContent = "Alege un profil"; s.appendChild(gol);
  (d.profiluri_mele || []).forEach(function(p){ var o = document.createElement("option"); o.value = p.id; o.textContent = p.nume; s.appendChild(o); });
  $("profil-eroare").textContent = d.profiluri_eroare || "";
  profilSelectat();
  arataSensuri();
}
function citeste(){
  return cerere("/api/taste-rapide").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi butoanele."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams();
  toate().forEach(function(b){ q.set(b.cheie, $("b-" + b.cheie).value); });
  mesaj("Se salvează...");
  cerere("/api/taste-rapide-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); if(d.butoane){ arata(d); } }).catch(nimicNuRaspunde);
});
$("renunta").addEventListener("click", function(){ mesaj("Nu s-a schimbat nimic."); citeste(); });
$("implicite").addEventListener("click", function(){
  toate().forEach(function(b){ $("b-" + b.cheie).value = D.implicite[b.cheie]; });
  mesaj("Valorile implicite sunt pregătite. Apasă Salvează pentru a le păstra.");
});
$("sensContext").addEventListener("change", arataSensuri);
$("spreAlbastru").addEventListener("click", function(){ location.href = adresa("/lista-albastra"); });
function profilSelectat(){
  var id = $("profilul-meu").value;
  ["profil-sterge", "profil-redenumeste"].forEach(function(k){ $(k).disabled = profilOcupat || !id; });
  var link = $("profil-descarca");
  if(id){ link.href = "/api/taste-profil-descarca?id=" + encodeURIComponent(id); }
  else { link.removeAttribute("href"); }
}
function operatieProfil(actiune, extra){
  if(profilOcupat){ return Promise.resolve(); }
  var q = new URLSearchParams(); q.set("actiune", actiune); q.set("id", $("profilul-meu").value);
  q.set("nume", $("nume-profil").value);
  if(extra !== undefined){ q.set("continut", extra); }
  profilOcupat = true; profilBlocare();
  return cerere("/api/taste-profil", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){
      // Salvarea unui profil pastreaza in editor modificarile inca nesalvate.
      var draft = {};
      if(actiune !== "aplica"){ toate().forEach(function(b){ draft[b.cheie] = $("b-" + b.cheie).value; }); }
      var ales = $("profilul-meu").value;
      arata(d);
      Object.keys(draft).forEach(function(k){ $("b-" + k).value = draft[k]; });
      $("profilul-meu").value = ales; profilSelectat();
    }
  }).catch(nimicNuRaspunde).finally(function(){ profilOcupat = false; profilBlocare(); });
}
function profilBlocare(){
  ["profilul-meu", "nume-profil", "profil-salveaza", "profil-importa", "profil-fisier", "profil-text",
    "salveaza", "renunta", "implicite"].forEach(function(k){ $(k).disabled = profilOcupat; });
  toate().forEach(function(b){ $("b-" + b.cheie).disabled = profilOcupat; });
  profilSelectat();
}
$("profilul-meu").addEventListener("change", function(){ profilSelectat(); if(this.value){ operatieProfil("aplica"); } });
$("profil-salveaza").addEventListener("click", function(){
  var p = JSON.parse(JSON.stringify(D.poza_taste));
  toate().forEach(function(b){
    var grup = Object.prototype.hasOwnProperty.call(p.buttons, b.cheie) ? p.buttons : p.usage;
    var v = $("b-" + b.cheie).value; grup[b.cheie] = typeof grup[b.cheie] === "boolean" ? v === "1" : v;
  });
  operatieProfil("salveaza", JSON.stringify(p));
});
$("profil-redenumeste").addEventListener("click", function(){ operatieProfil("redenumeste"); });
$("profil-sterge").addEventListener("click", function(){ operatieProfil("sterge"); });
$("profil-importa").addEventListener("click", function(){
  var f = $("profil-fisier").files[0];
  if(f){
    if(f.size > 65536){ mesaj("Profilul este prea mare (maximum 64 KiB).", true); return; }
    var r = new FileReader(); r.onload = function(){ operatieProfil("importa", String(r.result)); };
    r.onerror = function(){ mesaj("Fișierul nu a putut fi citit.", true); }; r.readAsText(f, "UTF-8");
  } else { operatieProfil("importa", $("profil-text").value); }
});
citeste();
window.addEventListener("beforeunload", function(e){
  if(D && toate().some(function(b){ return $("b-" + b.cheie).value !== b.valoare; })){ e.preventDefault(); e.returnValue = ""; }
});
</script>
</body>
</html>
"""


PAGINA_SKIN = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aspectul ecranelor</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .sub{color:var(--text-slab);margin:0 0 14px;font-size:.92rem;line-height:1.45;}
  .skinuri{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin:0 0 12px;}
  .skinuri .card{margin:0;display:flex;flex-direction:column;gap:8px;}
  .skinuri .card.ales{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent);}
  .cap{display:flex;justify-content:space-between;align-items:baseline;gap:10px;}
  .cap h2{margin:0;}
  .eticheta{font-size:.78rem;color:var(--text-slab);white-space:nowrap;}
  .poza{width:100%;aspect-ratio:16/9;object-fit:contain;border-radius:8px;display:block;}
</style>
</head>
<body>
<main>
<h1>Aspectul ecranelor</h1>
<p class="sub">Skinurile instalate pe receptor. Skinul ales se vede pe televizor după repornirea interfeței.</p>
<p class="nota">Aplică acum repornește interfața. La următoarea pornire păstrează alegerea fără repornire.</p>
<p class="nota">Șterge scoate tema de pe receptor. Tema HD Satelit nu se șterge; tema de pe ecran se șterge după ce interfața repornește cu tema HD Satelit.</p>
<p class="mesaj" id="incarcare">Se caută skinurile...</p>
<div id="continut" class="ascuns">
  <p class="mesaj eroare ascuns" id="refuz"></p>
  <p class="mesaj ascuns" id="stareTema"></p>
  <p class="nota ascuns" id="partiTema"></p>
  <div class="butoane ascuns" id="setariPartiTema"></div>
  <div class="skinuri" id="skinuri"></div>
  <section class="card">
    <h2>Aspectul meniului</h2>
    <div class="rand">
      <label for="aspect">Meniul ca</label>
      <select id="aspect"></select>
    </div>
  </section>
  <section class="card">
    <h2>Tema și culorile</h2>
    <p class="nota">Tema skinului HD Satelit (Clasic sau Pro) și culorile lui au paginile lor.</p>
    <div class="butoane">
      <button type="button" id="spreTema">Tema interfeței</button>
      <button type="button" id="spreCulori">Culorile skinului</button>
    </div>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Skinul ales se încarcă la pornirea interfeței. Ecranele pe care skinul ales nu le are (cele ale receptorului HD Satelit) vin din skinul HD Satelit, potrivite la rezoluția skinului ales, deci încap întregi, cu culorile și literele lor; pe un skin mai îngust de 1024 de puncte (720x576) literele lor sunt mici. Dacă skinul ales nu pornește (lipsește, e stricat sau interfața se oprește cu el), receptorul revine singur la skinul HD Satelit și spune de ce, aici și pe televizor. Tema Clasic sau Pro e numai a skinului HD Satelit. Meniul rămâne deocamdată listă. Același ecran e pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
function arata(d){
  var parti = $("partiTema"); parti.textContent = d.parti_tema ? d.parti_tema.mesaj : "";
  parti.classList.toggle("ascuns", !d.parti_tema);
  var setariParti = $("setariPartiTema"); setariParti.textContent = "";
  ((d.parti_tema || {}).setari_web || []).forEach(function(x){
    var a = document.createElement("a"); a.href = adresa(x.href); a.textContent = x.text; setariParti.appendChild(a);
  });
  setariParti.classList.toggle("ascuns", !setariParti.children.length);
  var c = $("skinuri"); c.textContent = "";
  d.skinuri.forEach(function(x){
    var card = document.createElement("section"); card.className = "card" + (x.ales ? " ales" : "");
    var cap = document.createElement("div"); cap.className = "cap";
    var h = document.createElement("h2"); h.textContent = x.eticheta; cap.appendChild(h);
    var e = document.createElement("span"); e.className = "eticheta";
    e.textContent = x.incompleta ? "incompletă" : (x.ales && x.activ ? "ales, pe ecran acum" : (x.ales ? "ales, după repornire" : (x.activ ? "pe ecran până la repornire" : "")));
    cap.appendChild(e);
    card.appendChild(cap);
    var img = document.createElement("img"); img.className = "poza"; img.alt = "Previzualizarea skinului " + x.eticheta;
    img.src = adresa("/api/skin-poza?nume=" + encodeURIComponent(x.nume));
    img.addEventListener("error", function(){ img.classList.add("ascuns"); });
    card.appendChild(img);
    var bs = document.createElement("div"); bs.className = "butoane";
    if(x.incompleta){
      var ni = document.createElement("p"); ni.className = "nota";
      ni.textContent = "Tema e incompletă: lipsește skin.xml, deci nu se mai poate folosi. Șterge scoate ce a rămas din ea.";
      card.appendChild(ni);
    } else {
      var b = document.createElement("button"); b.type = "button"; b.className = x.ales ? "" : "principal";
      b.textContent = "Aplică acum";
      b.addEventListener("click", function(){ alege(x.nume, "acum"); });
      bs.appendChild(b);
      var maiTarziu = document.createElement("button"); maiTarziu.type = "button";
      maiTarziu.textContent = "La următoarea pornire";
      maiTarziu.addEventListener("click", function(){ alege(x.nume, "pornire"); });
      bs.appendChild(maiTarziu);
    }
    var st = x.stergere || {};
    if(st.poate){
      var sterge = document.createElement("button"); sterge.type = "button"; sterge.className = "rosu";
      sterge.textContent = "Șterge";
      sterge.addEventListener("click", function(){ stergeTema(x.nume); });
      bs.appendChild(sterge);
    }
    card.appendChild(bs);
    if(!st.poate && st.motiv && !x.imaginii){
      var m = document.createElement("p"); m.className = "nota"; m.textContent = st.motiv; card.appendChild(m);
    }
    c.appendChild(card);
  });
  $("refuz").textContent = d.refuz || "";
  $("refuz").classList.toggle("ascuns", !d.refuz);
  $("stareTema").textContent = d.stare_tema || "";
  $("stareTema").classList.toggle("ascuns", !d.stare_tema);
  var s = $("aspect");
  if(document.activeElement !== s){
    s.textContent = "";
    (d.aspecte || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
    s.value = d.aspect;
  }
}
var urmaresteLucrarea = false;
function lucrarea(l){
  if(l && l.faza === "lucru"){ urmaresteLucrarea = true; mesaj(l.titlu); setTimeout(citeste, 2000); return; }
  if(l && urmaresteLucrarea){ urmaresteLucrarea = false; mesaj((l.titlu + " " + (l.stare || "")).trim(), !l.reusit); }
}
function citeste(){
  return cerere("/api/skin").then(function(d){
    if(!d.result && urmaresteLucrarea){ setTimeout(citeste, 2000); return; }
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi skinurile."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
    lucrarea(d.lucrare);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function alege(nume, aplicare){
  var q = new URLSearchParams(); q.set("nume", nume); q.set("aplicare", aplicare);
  mesaj("Se salvează...");
  cerere("/api/skin-alege", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(!d.result){ return; }
    citeste();
    if(d.reporneste){ setTimeout(function(){ location.reload(); }, 15000); }
  }).catch(nimicNuRaspunde);
}
function stergeTema(nume){
  var q = new URLSearchParams(); q.set("nume", nume);
  cuConfirmare("/api/skin-sterge", q, function(d){
    if(!d.result){ return; }
    if(d.reporneste){ setTimeout(function(){ location.reload(); }, 20000); return; }
    if(d.lucrare){ urmaresteLucrarea = true; }
    citeste();
  });
}
$("aspect").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("aspect", $("aspect").value);
  mesaj("Se salvează...");
  cerere("/api/skin-aspect", "POST", q).then(function(d){ mesaj(d.message, !d.result); }).catch(nimicNuRaspunde);
});
$("spreTema").addEventListener("click", function(){ location.href = adresa("/tema-tv"); });
$("spreCulori").addEventListener("click", function(){ location.href = adresa("/culori-skin"); });
citeste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Aplică acum repornește interfața. La următoarea pornire păstrează alegerea fără repornire."),
		N_("Dispozitive de intrare"),
		N_("Telecomenzile, tastaturile și mouse-urile găsite de receptor la pornire. Pentru fiecare se "
			"poate schimba cât de repede se repetă o tastă ținută apăsat."),
		N_("Se citesc dispozitivele..."),
		N_("Receptorul n-a găsit niciun dispozitiv de intrare la pornire."),
		N_("Telecomenzi"),
		N_("Codurile tastelor, proba tastelor și folosirea altei telecomenzi au pagina lor."),
		N_("Deschide Telecomenzi"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
		N_("Butoane colorate și taste rapide"),
		N_("Valori implicite"),
		N_("Se citesc butoanele..."),
		N_("Apăsarea scurtă"),
		N_("Subcanalele se pot aloca unei taste sau se găsesc în Lista extensiilor."),
		N_("Apăsarea lungă"),
		N_("Apăsare lungă: ține tasta apăsată ~1 s."),
		N_("Salvează"),
		N_("Renunță"),
		N_("Aspectul ecranelor"),
		N_("Skinurile instalate pe receptor. Skinul ales se vede pe televizor după repornirea interfeței."),
		N_("Se caută skinurile..."),
		N_("Aspectul meniului"),
		N_("Meniul ca"),
		N_("Tema și culorile"),
		N_("Tema skinului HD Satelit (Clasic sau Pro) și culorile lui au paginile lor."),
		N_("Tema interfeței"),
		N_("Culorile skinului"),
		N_("Șterge scoate tema de pe receptor. Tema HD Satelit nu se șterge; tema de pe ecran se șterge după ce interfața "
			"repornește cu tema HD Satelit."),
		N_("Skinul ales se încarcă la pornirea interfeței. Ecranele pe care skinul ales nu le are (cele ale "
			"receptorului HD Satelit) vin din skinul HD Satelit, potrivite la rezoluția skinului ales, deci "
			"încap întregi, cu culorile și literele lor; pe un skin mai îngust de 1024 de puncte (720x576) "
			"literele lor sunt mici. Dacă skinul ales nu pornește (lipsește, e stricat sau interfața se "
			"oprește cu el), receptorul revine singur la skinul HD Satelit și spune de ce, aici și pe "
			"televizor. Tema Clasic sau Pro e numai a skinului HD Satelit. Meniul rămâne deocamdată listă. "
			"Același ecran e pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Aplică acum"),
		N_("La următoarea pornire"),
		N_("telecomandă"),
		N_("tastatură"),
		N_("alt dispozitiv"),
		N_("Da"),
		N_("Nu"),
		N_("Schimbi intervalul și întârzierea repetării?"),
		N_("Intervalul dintre taste la repetare"),
		N_("Întârzierea până începe repetarea"),
		N_("Salvează"),
		N_("Pune înapoi valorile salvate"),
		N_("Cu Nu, intervalul și întârzierea se întorc la valorile din fabrică."),
		N_("Receptorul nu a putut citi dispozitivele."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Receptorul nu a putut citi butoanele."),
		N_("Se salvează..."),
		N_("Nu s-a schimbat nimic."),
		N_("Valorile implicite sunt pregătite. Apasă Salvează pentru a le păstra."),
		N_("ales, pe ecran acum"),
		N_("ales, după repornire"),
		N_("pe ecran până la repornire"),
		N_("Previzualizarea skinului"),
		N_("Receptorul nu a putut citi skinurile."),
		N_("Șterge"),
		N_("incompletă"),
		N_("Tema e incompletă: lipsește skin.xml, deci nu se mai poate folosi. Șterge scoate ce a rămas din ea."),
	),
}


TEXTE_PAGINA["html"] += (
	N_("Alege o funcție sau un plugin instalat pentru fiecare tastă, cât te uiți la televizor. Funcția obișnuită urmează profilul curent. Cifrele lungi se alocă în afara timeshiftului."),
	N_("Liste și meniuri"),
	N_("Tastele acestui ecran"), N_("Context"), N_("TV"), N_("Radio"), N_("Lista de canale"),
	N_("Lista de filme"), N_("Film"), N_("Timeshift"), N_("Meniu"), N_("Setări"),
)
TEXTE_PAGINA["js"] += (N_("Scurt:"), N_("Lung:"))
TEXTE_PAGINA["html"] += (
	N_("Profilurile mele"), N_("Alegerea unui profil îl aplică pe loc. Așezările predefinite rămân puncte de plecare."),
	N_("Numele profilului (poți lăsa gol)"), N_("Salvează ca profil"), N_("Redenumește profilul"),
	N_("Șterge profilul"), N_("Descarcă profilul"), N_("Încarcă un profil"), N_("Sau lipește aici conținutul profilului"),
)
TEXTE_PAGINA["js"] += (N_("Alege un profil"), N_("Profilul este prea mare (maximum 64 KiB)."), N_("Fișierul nu a putut fi citit."))


def pagina_albastru(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_ALBASTRU), stil, config_pagina, "hds_button_setup")


# Lista butonului ALBASTRU (perechea ecranului Screens/ButtonSetup.HdsListaAlbastra): sus randurile listei, in ordinea
# lor, cu Sus, Jos si Scoate; dedesubt tot ce se mai poate pune, cu cautare. Fiecare apasare se salveaza pe loc.
PAGINA_ALBASTRU = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lista butonului albastru</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .sub{color:var(--text-slab);margin:0 0 14px;font-size:.92rem;line-height:1.45;}
  .linie{display:flex;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid var(--bordura);}
  .linie:last-child{border-bottom:0;}
  .linie .nume{flex:1;min-width:0;overflow-wrap:anywhere;}
  .linie .grupa{display:block;color:var(--text-slab);font-size:.8rem;}
  .linie button{min-width:44px;}
  #cauta{width:100%;margin:0 0 8px;}
</style>
</head>
<body>
<main>
<h1>Lista butonului albastru</h1>
<p class="sub">Ce apare când apeși butonul albastru, cât te uiți la televizor, și în ce ordine. Fiecare schimbare se salvează pe loc.</p>
<p class="mesaj" id="incarcare">Se citește lista...</p>
<div id="continut" class="ascuns">
  <section class="card"><h2>Pe butonul albastru</h2><div id="lista"></div>
    <div class="butoane"><button type="button" id="fabrica">Lista din fabrică</button></div>
  </section>
  <section class="card"><h2>Adaugă</h2>
    <input id="cauta" type="search" maxlength="60" placeholder="Caută un meniu, o funcție sau un plugin" aria-label="Caută un meniu, o funcție sau un plugin">
    <div id="catalog"></div>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Aceeași listă e pe televizor, în __DRUM_MENIU__, la Lista butonului albastru.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var D = null;
function buton(text, actiune, id){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text;
  b.addEventListener("click", function(){ schimba(actiune, id); });
  return b;
}
function linie(x){
  var r = document.createElement("div"); r.className = "linie";
  var n = document.createElement("span"); n.className = "nume"; n.textContent = x.nume;
  if(x.grupa){ var g = document.createElement("span"); g.className = "grupa"; g.textContent = x.grupa; n.appendChild(g); }
  r.appendChild(n);
  return r;
}
function arata(d){
  D = d;
  var dupaId = {};
  d.catalog.forEach(function(x){ dupaId[x.id] = x; });
  var l = $("lista"); l.textContent = "";
  d.lista.forEach(function(id){
    var r = linie(dupaId[id] || {nume: "Indisponibil acum", grupa: ""});
    r.appendChild(buton("Sus", "sus", id)); r.appendChild(buton("Jos", "jos", id)); r.appendChild(buton("Scoate", "comuta", id));
    l.appendChild(r);
  });
  filtreaza();
}
function filtreaza(){
  if(!D){ return; }
  var c = $("catalog"); c.textContent = "";
  var t = $("cauta").value.trim().toLowerCase();
  D.catalog.forEach(function(x){
    if(x.ales){ return; }
    if(t && (x.nume + " " + x.grupa).toLowerCase().indexOf(t) === -1){ return; }
    var r = linie(x); r.appendChild(buton("Adaugă", "comuta", x.id)); c.appendChild(r);
  });
}
function schimba(actiune, id){
  var q = new URLSearchParams(); q.set("actiune", actiune); q.set("id", id || "");
  cerere("/api/lista-albastra-schimba", "POST", q).then(function(d){
    mesaj(d.message, !d.result); if(d.catalog){ arata(d); }
  }).catch(nimicNuRaspunde);
}
function citeste(){
  return cerere("/api/lista-albastra").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi lista."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("cauta").addEventListener("input", filtreaza);
$("fabrica").addEventListener("click", function(){ schimba("fabrica", ""); });
citeste();
</script>
</body>
</html>
"""

TEXTE_PAGINA["html"] += (
	N_("Lista butonului albastru"),
	N_("Ce apare când apeși butonul albastru, cât te uiți la televizor, și în ce ordine. Fiecare schimbare se salvează pe loc."),
	N_("Se citește lista..."), N_("Pe butonul albastru"), N_("Lista din fabrică"), N_("Adaugă"),
	N_("Caută un meniu, o funcție sau un plugin"),
	N_("Aceeași listă e pe televizor, în __DRUM_MENIU__, la Lista butonului albastru."),
	N_("Ce apare în lista butonului albastru și în ce ordine alegi la"),
)
TEXTE_PAGINA["js"] += (N_("Indisponibil acum"), N_("Sus"), N_("Jos"), N_("Scoate"), N_("Adaugă"),
	N_("Receptorul nu a putut citi lista."))


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
