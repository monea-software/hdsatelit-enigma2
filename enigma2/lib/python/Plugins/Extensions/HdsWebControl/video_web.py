# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# video_web.py: „Video” in interfata web (HdsWebControl), perechea ecranului Setari > Video (Screens/VideoSetup.py).
#
# Aceleasi randuri ca pe televizor: „Rezoluție” si „Frecvență” (cu „Automat după canal” unde receptorul are fisierele
# de frecventa), spatiul de culoare, adancimea de culoare si HDR cand driverul le are, „La schimbarea canalului”
# (zapmode) cand driverul are fisierul. O SINGURA LOGICA: listele, despartirea modului in cele doua randuri si
# incercarea unui mod nou sunt in Components/VideoOutput.py (screenModes, resolutionChoices, rateRow, splitMode,
# joinMode, tryVideo, keepVideo, cancelVideo); intrebarea si mesajele vin din Screens/VideoSetup.py.
#
# Un mod video nou se incearca, nu se salveaza direct: pe televizor se deschide aceeasi intrebare ca in Setari > Video
# (CONFIRM_SECONDS, implicit Nu), iar pagina arata cate secunde mai are si butoanele „Păstrează” si „Revino”. Primul
# raspuns, de pe televizor sau din pagina, inchide intrebarea (pagina o inchide prin dlg.close, deci acelasi drum);
# fara raspuns revine modul de dinainte. Telefonul ramane locul de unde se intoarce un mod care lasa televizorul negru.
# Un ceas de rezerva (cateva secunde dupa termen) intoarce modul si daca intrebarea de pe televizor nu s-a inchis
# singura. „La schimbarea canalului” nu poate lasa televizorul negru: se scrie si se salveaza direct. La fel „Imaginea
# 4:3” (VideoOutput.policyElement, fisierul policy al driverului), numai cand driverul il are.
# „Culorile pe HDMI” (VideoOutput.HdmiColors): YCbCr se scrie pe loc si trece prin aceeasi intrebare (singur sau
# impreuna cu un mod nou); fara „Da” nu se salveaza, dar iesirea ramane YCbCr pana la urmatoarea pornire (driverul nu
# are drum inapoi). RGB se salveaza direct si se aplica la urmatoarea pornire. In ambele cazuri, cand iesirea e YCbCr
# acum, mesajul intreaba daca receptorul reporneste acum, iar pagina arata butonul de repornire (POST
# /api/video-reporneste, acelasi drum ca „Da” pe televizor: TryQuitMainloop 2). GET /api/video numai citeste: scrierile
# de YCbCr le fac privirile HdmiColors, pe ceasul lor.
# Nu se schimba nimic cat e deschis pe televizor Setari > Video sau asistentul de pornire (ar strica ecranul deschis),
# cat merge o cautare de canale sau o incercare, in standby si inainte ca interfata web sa aiba sesiunea enigma2.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/video                                        randurile, valorile, alegerile, incercarea in curs
#   POST /api/video-seteaza?rezolutie=..&frecventa=..&colorspace=..&colordepth=..&hdrtype=..&zapmode=..&imagine43=..&culori_hdmi=..
#                                                          oricare dintre ele; un mod video nou sau YCbCr pornesc
#                                                          incercarea
#   POST /api/video-confirma                               pastreaza setarea incercata (ca „Da” pe televizor)
#   POST /api/video-revino                                 setarea de dinainte, acum (ca „Nu” pe televizor)
#   POST /api/video-reporneste                             reporneste receptorul (dupa culorile nepastrate sau RGB)
#   GET  /video                                            pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; scrierile sunt cateva fisiere din /proc/stb/video si
# repornirea canalului, ca in Setari > Video. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau
# modulele lor (V = Components.VideoOutput, S = Screens.VideoSetup), sesiunea, fisierul de setari si ceasul.

import time

# ce se poate trimite si cat de lung
ARGUMENTE = ("rezolutie", "frecventa", "colorspace", "colordepth", "hdrtype", "zapmode", "imagine43", "culori_hdmi")
CULORI = (("colorspace", "HDMI color space"), ("colordepth", "Color depth"), ("hdrtype", "HDR type"))
MAX_VALOARE = 40
# ceasul de rezerva: atatea secunde dupa termenul intrebarii, modul revine si daca intrebarea nu s-a inchis singura
REZERVA_S = 5
# repornirea receptorului incepe dupa atatea secunde, ca raspunsul sa ajunga intai la telefon
REPORNIRE_S = 1
# cat timp arata pagina rezultatul ultimei incercari
ULTIMUL_S = 60
ECRANE_OCUPATE = ("VideoSetup", "HdsStartWizard")

# incercarea in curs (una singura): id, fereastra intrebarii, ce avea driverul inainte, termenul, ceasul de rezerva;
# video = un mod nou in incercare, culori = „Culorile pe HDMI” schimbate, culori_scrise = YCbCr scris la incercare,
# culori_text = ce se spune dupa „Da” (RGB ales impreuna cu un mod)
_INCERCARE = {"id": 0, "activa": False, "dlg": None, "inainte": None, "pana_la": 0, "ceas": None, "fisier": None,
	"video": True, "culori": False, "culori_scrise": False, "culori_text": None}
_ULTIMUL = {"mesaj": "", "reusit": None, "t": 0, "repornire": False}


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _v(V=None):
	if V is not None:
		return V
	from Components import VideoOutput
	return VideoOutput


def _s(S=None):
	if S is not None:
		return S
	from Screens import VideoSetup
	return VideoSetup


def _fisierSetari(configfile=None):
	if configfile is not None:
		return configfile
	from Components.config import configfile as fisier
	return fisier


def _ceasImplicit(secunde, functie):
	"""un eTimer o singura data; intors ca sa fie tinut in viata cat merge"""
	from enigma import eTimer
	ceas = eTimer()
	ceas.callback.append(functie)
	ceas.start(int(secunde * 1000), True)
	return ceas


def _jurnal(text):
	print("[HdsWebControl] video: %s" % text)


def _alegeri(element):
	"""[[valoare, text tradus]] din alegerile unei setari, in ordinea de pe televizor."""
	return [[str(v), _t(element.description[v])] for v in element.choices]


def _dialoguri(sesiune):
	deschise = []
	curent = getattr(sesiune, "current_dialog", None)
	if curent is not None:
		deschise.append(curent)
	for x in getattr(sesiune, "dialog_stack", None) or []:
		deschise.append(x[0] if isinstance(x, tuple) else x)
	return deschise


def _inStandby():
	try:
		from Screens import Standby
		return Standby.inStandby is not None
	except Exception:
		return False


def _cautareInCurs(sesiune):
	"""textul refuzului cand o cautare de canale merge pe receptor (scanare_web), altfel None"""
	try:
		from . import scanare_web
	except Exception:
		return None
	try:
		return scanare_web._ocupat(sesiune)
	except Exception:
		return None


def ocupat(sesiune, acum=None):
	"""Textul refuzului cand pagina nu are voie sa schimbe setarile video, altfel None."""
	if sesiune is None:
		return _t("Interfața web nu are încă legătura cu ecranul receptorului. Așteaptă pornirea completă a receptorului, apoi încearcă din nou.")
	if _inStandby():
		return _t("Receptorul este în standby. Pornește-l din telecomandă, apoi încearcă din nou.")
	if _INCERCARE["activa"]:
		return _t("Un mod video nou se încearcă acum. Răspunde întâi la întrebarea de pe televizor sau din pagină.")
	for d in _dialoguri(sesiune):
		if type(d).__name__ in ECRANE_OCUPATE:
			return _t("Pe televizor e deschis ecranul Video sau asistentul de pornire. Închide-l, apoi încearcă din nou.")
	return _cautareInCurs(sesiune)


def _stareIncercare(S, acum):
	rez = {"activa": bool(_INCERCARE["activa"]), "secunde": 0, "intrebare": ""}
	if _INCERCARE["activa"]:
		rez["secunde"] = max(0, int(round(_INCERCARE["pana_la"] - acum)))
		rez["intrebare"] = _INCERCARE.get("intrebare") or ""
		if not _INCERCARE.get("video", True):
			# numai culorile: fara raspuns nu se pastreaza, dar YCbCr ramane pana la urmatoarea pornire
			rez["doarCulori"] = True
	if _ULTIMUL["mesaj"] and acum - _ULTIMUL["t"] <= ULTIMUL_S:
		rez["ultimul"] = {"mesaj": _ULTIMUL["mesaj"], "reusit": _ULTIMUL["reusit"]}
		if _ULTIMUL.get("repornire"):
			# culorile „Ca la calculator” vin numai dupa o repornire: pagina arata butonul
			rez["ultimul"]["repornire"] = True
	return rez


def _numaratoare(S, acum):
	"""randul cu secundele al intrebarii in curs, acelasi text ca pe televizor (tradus), sau "" """
	if not _INCERCARE["activa"]:
		return ""
	secunde = max(0, int(round(_INCERCARE["pana_la"] - acum)))
	if not _INCERCARE.get("video", True):
		return S.colorCountdown(secunde)
	return S.countdownText(secunde)


def stare(V=None, S=None, sesiune=None, acum=None, reciteste=True):
	"""Pentru GET /api/video: randurile ecranului Setari > Video, cu valorile de acum (cele incercate, cat merge o
	incercare) si alegerile lor."""
	V = _v(V)
	S = _s(S)
	acum = time.time() if acum is None else acum
	iesire = V.videoOutput
	element = V.configElement("hds_videomode")
	if iesire is None or element is None or not iesire.available("videomode"):
		return {"result": False, "message": _t("Ieșirea video a receptorului nu e pregătită.")}
	refuz = ocupat(sesiune, acum)
	if reciteste and refuz is None:
		# ce accepta televizorul, citit din nou (poate fi pornit dupa receptor), ca la deschiderea ecranului; nu cat
		# e deschis pe televizor Setari > Video (randurile lui sunt facute din lista de la deschidere) sau cat merge
		# o incercare
		V.updateModeChoices()
	moduri = S.screenModes()
	rata = V.configElement(V.VideoOutput.RATE_ATTR)
	rezolutie, frecventa = iesire.splitMode(moduri, element.value, bool(rata is not None and rata.value))
	rezolutii = V.resolutionChoices(moduri)
	frecvente = {}
	for grup, eticheta in rezolutii:
		frecvente[grup] = [[v, _t(e)] for v, e in iesire.rateRow(moduri, grup)]
	culori = []
	for nume, text in CULORI:
		el = V.configElement("hds_" + nume)
		if el is not None and iesire.available(nume):
			culori.append({"nume": nume, "eticheta": _t(text), "valoare": str(el.value), "alegeri": _alegeri(el)})
	zap = V.configElement(V.ZAP_ATTR)
	imagine43 = V.policyElement()
	culori_hdmi = None
	el = V.colorElement()
	if el is not None:
		hdmi = V.hdmiColors()
		# numai citire (hdmi0_sink, ~0,2 ms pe u57): pagina intreaba la cateva secunde, iar YCbCr il scriu privirile
		# HdmiColors pe ceasul lor, nu cererile paginii
		primeste = hdmi.tvAccepts() if hdmi is not None else None
		culori_hdmi = {"eticheta": _t("Culorile pe HDMI"), "valoare": str(el.value), "alegeri": _alegeri(el),
			"descriere": V.colorDescription(primeste)}
	return {
		"result": True,
		"simulare": bool(iesire.simulation),
		"rezolutii": [[g, e] for g, e in rezolutii],
		"rezolutie": rezolutie,
		"frecvente": frecvente,
		"frecventa": frecventa,
		"mod": element.value,
		"eticheta_mod": V.modeLabel(element.value),
		"culori": culori,
		"zapmode": None if zap is None else {"eticheta": _t("La schimbarea canalului"), "valoare": zap.value,
			"alegeri": _alegeri(zap), "descriere": V.zapDescription()},
		"imagine43": None if imagine43 is None else {"eticheta": V.policyRowText(), "valoare": imagine43.value,
			"alegeri": _alegeri(imagine43), "descriere": V.policyDescription()},
		"culori_hdmi": culori_hdmi,
		"avertisment": S.rateWarning(),
		"incercare": _stareIncercare(S, acum),
		"numaratoare": _numaratoare(S, acum),
		"ocupat": refuz,
	}


def _cuMesaj(rez, reusit, mesaj):
	rez = dict(rez)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def _alegeValoare(element, text):
	for v in element.choices:
		if str(v) == text:
			return v
	return None


def seteaza(argumente, V=None, S=None, sesiune=None, configfile=None, acum=None, ceas=None):
	"""POST /api/video-seteaza. Toate valorile primite trebuie sa existe, altfel nu se schimba nimic. zapmode se scrie
	si se salveaza pe loc; un mod video sau o culoare noua porneste incercarea, cu intrebarea pe televizor."""
	V = _v(V)
	S = _s(S)
	acum = time.time() if acum is None else acum
	ceas = ceas or _ceasImplicit
	baza = stare(V, S, sesiune, acum, reciteste=False)
	if not baza["result"]:
		return baza
	if not any(k in argumente for k in ARGUMENTE):
		return _cuMesaj(baza, False, _t("Nu s-a trimis nicio setare."))
	refuz = ocupat(sesiune, acum)
	if refuz:
		return _cuMesaj(baza, False, refuz)
	iesire = V.videoOutput
	moduri = S.screenModes()
	noi = {}
	# rezolutia si frecventa: impreuna, sau una din ele fata de ce e acum (ca pe televizor)
	if "rezolutie" in argumente or "frecventa" in argumente:
		rezolutie = argumente.get("rezolutie", baza["rezolutie"])
		if rezolutie not in [g for g, e in baza["rezolutii"]]:
			return _cuMesaj(baza, False, _t("Alegerea „%s” nu există pentru „%s”.") % (rezolutie[:MAX_VALOARE], _t("Resolution")))
		frecventa = argumente.get("frecventa")
		if frecventa is None:
			frecventa = iesire.rateAfterResolution(moduri, rezolutie, baza["frecventa"])
		lipit = iesire.joinMode(moduri, rezolutie, frecventa)
		if lipit is None:
			return _cuMesaj(baza, False, _t("Alegerea „%s” nu există pentru „%s”.") % (frecventa[:MAX_VALOARE], _t("Frecvență")))
		noi["hds_videomode"], noi[V.VideoOutput.RATE_ATTR] = lipit
	for nume, text in CULORI:
		if nume in argumente:
			el = V.configElement("hds_" + nume)
			valoare = _alegeValoare(el, argumente[nume]) if el is not None and iesire.available(nume) else None
			if valoare is None:
				return _cuMesaj(baza, False, _t("Alegerea „%s” nu există pentru „%s”.") % (argumente[nume][:MAX_VALOARE], _t(text)))
			noi["hds_" + nume] = valoare
	zap = V.configElement(V.ZAP_ATTR)
	zap_nou = None
	if "zapmode" in argumente:
		zap_nou = _alegeValoare(zap, argumente["zapmode"]) if zap is not None else None
		if zap_nou is None:
			return _cuMesaj(baza, False, _t("Alegerea „%s” nu există pentru „%s”.") % (argumente["zapmode"][:MAX_VALOARE], _t("La schimbarea canalului")))
	imagine43 = V.policyElement()
	imagine43_nou = None
	if "imagine43" in argumente:
		imagine43_nou = _alegeValoare(imagine43, argumente["imagine43"]) if imagine43 is not None else None
		if imagine43_nou is None:
			return _cuMesaj(baza, False, _t("Alegerea „%s” nu există pentru „%s”.") % (argumente["imagine43"][:MAX_VALOARE], V.policyRowText()))
	culori = V.colorElement()
	culori_nou = None
	if "culori_hdmi" in argumente:
		culori_nou = _alegeValoare(culori, argumente["culori_hdmi"]) if culori is not None else None
		if culori_nou is None:
			return _cuMesaj(baza, False, _t("Alegerea „%s” nu există pentru „%s”.") % (argumente["culori_hdmi"][:MAX_VALOARE], _t("Culorile pe HDMI")))
	fisier = _fisierSetari(configfile)
	if zap_nou is not None and zap_nou != zap.value:
		zap.value = zap_nou             # notificatorul il scrie in driver
		zap.save()
		fisier.save()
	if imagine43_nou is not None and imagine43_nou != imagine43.value:
		imagine43.value = imagine43_nou   # notificatorul il scrie in driver (policy); nu schimba formatul HDMI
		imagine43.save()
		fisier.save()
	for atribut, valoare in noi.items():
		el = V.configElement(atribut)
		if el is not None:
			el.value = valoare
	# „Culorile pe HDMI”: YCbCr se scrie acum (imaginea se schimba pe loc, deci se intreaba), RGB la urmatoarea pornire
	culori_scrise = False
	culori_text = None
	culori_repornire = False
	if culori_nou is not None and culori_nou != culori.value:
		culori.value = culori_nou
		hdmi = V.hdmiColors()
		if culori_nou == V.COLOR_YCBCR:
			incercat = hdmi.tryNow() if hdmi is not None else V.TRY_LATER
			culori_scrise = incercat == V.TRY_WRITTEN
			if incercat == V.TRY_TV:
				culori_text = S.colorTvText()
			elif incercat == V.TRY_LATER:
				culori_text = S.colorLaterText()
		elif hdmi is not None and hdmi.ycbcrNow():
			# RGB cu iesirea YCbCr acum: se aplica numai dupa o repornire, pagina o ofera
			culori_text = S.colorRestartQuestion(True)
			culori_repornire = True
	culori_schimbate = culori is not None and culori.isChanged()
	if not V.videoChanged():
		if culori_scrise:
			return _pornesteIntrebarea(V, S, sesiune, fisier, None, True, acum, ceas, video=False, culori=True,
				culori_scrise=True)
		if culori_schimbate:
			culori.save()
			fisier.save()
			# ca mesajul unei incercari vechi (rosu) sa nu mai ramana in pagina dupa o salvare reusita
			mesaj = culori_text or _t("Salvat.")
			_noteaza(mesaj, True, acum, culori_repornire)
			return _cuMesaj(stare(V, S, sesiune, acum, reciteste=False), True, mesaj)
		rez = stare(V, S, sesiune, acum, reciteste=False)
		return _cuMesaj(rez, True, _t("Salvat.") if (zap_nou is not None or imagine43_nou is not None) else _t("Setarea era deja aceasta."))
	inainte, pe_ecran = V.tryVideo(sesiune.nav)
	if pe_ecran is None:
		if culori_schimbate:
			culori.cancel()
		mesaj = _faraCulori(S, S.refusedText(), culori_scrise)
		_noteaza(mesaj, False, acum, culori_scrise)
		return _cuMesaj(stare(V, S, sesiune, acum, reciteste=False), False, mesaj)
	return _pornesteIntrebarea(V, S, sesiune, fisier, inainte, pe_ecran, acum, ceas, video=True,
		culori=culori_schimbate, culori_scrise=culori_scrise, culori_text=culori_text,
		culori_repornire=culori_repornire)


def _faraCulori(S, mesaj, culori_scrise):
	"""mesajul dupa „Nu” sau dupa un mod refuzat; cand YCbCr a fost scris la incercare, cu intrebarea repornirii (in
	pagina, sub ea, butonul de repornire)"""
	if culori_scrise:
		mesaj = (mesaj + "\n" + S.colorRestartQuestion(False)).strip()
	return mesaj


def _noteaza(mesaj, reusit, acum=None, repornire=False):
	_ULTIMUL.update({"mesaj": mesaj, "reusit": reusit, "t": time.time() if acum is None else acum,
		"repornire": bool(repornire)})


def _pornesteIntrebarea(V, S, sesiune, fisier, inainte, pe_ecran, acum, ceas, video=True, culori=False,
		culori_scrise=False, culori_text=None, culori_repornire=False):
	"""intrebarea de pe televizor (aceeasi ca in Setari > Video) si ceasul de rezerva; video = un mod nou in
	incercare, culori = „Culorile pe HDMI” schimbate (salvate sau anulate odata cu raspunsul)"""
	_INCERCARE["id"] += 1
	numar = _INCERCARE["id"]
	intrebare = S.confirmText(pe_ecran) if video else S.colorQuestion()
	_INCERCARE.update({"activa": True, "dlg": None, "inainte": inainte, "pana_la": acum + S.CONFIRM_SECONDS,
		"fisier": fisier, "intrebare": intrebare, "sesiune": sesiune, "V": V, "S": S, "video": video,
		"culori": culori, "culori_scrise": culori_scrise, "culori_text": culori_text,
		"culori_repornire": culori_repornire})
	try:
		from Screens.MessageBox import MessageBox
		# aceeasi intrebare ca in Setari > Video, cu secundele ramase in text (VideoSetup.ModeQuestion); pentru
		# culorile singure, cu randul lor de numaratoare (colorCountdown)
		ecran = getattr(S, "ModeQuestion", None)
		optiuni = {"timeout": S.CONFIRM_SECONDS, "default": False}
		if ecran is not None and not video:
			optiuni["countdown"] = S.colorCountdown
		_INCERCARE["dlg"] = sesiune.openWithCallback(lambda raspuns=False: _raspuns(numar, raspuns),
			ecran or MessageBox, intrebare, MessageBox.TYPE_YESNO, **optiuni)
	except Exception as eroare:
		# fara intrebare pe televizor nu se tine un mod pe care nu-l poate refuza nimeni de acolo
		_jurnal("intrebarea nu s-a deschis pe televizor: %s" % eroare)
		_raspuns(numar, False)
		return _cuMesaj(stare(V, S, sesiune, acum, reciteste=False), False, _ULTIMUL["mesaj"])
	try:
		_INCERCARE["ceas"] = ceas(S.CONFIRM_SECONDS + REZERVA_S, lambda: _laTermen(numar))
	except Exception as eroare:
		_jurnal("ceasul de rezerva: %s" % eroare)
	if video:
		_jurnal("incercare %d: %s%s, pe ecran acum: %s" % (numar, V.configElement("hds_videomode").value,
			" + YCbCr" if culori_scrise else "", pe_ecran))
	else:
		_jurnal("incercare %d: numai YCbCr" % numar)
	return _cuMesaj(stare(V, S, sesiune, acum, reciteste=False), True, intrebare)


def _raspuns(numar, raspuns):
	"""raspunsul la intrebare (de pe televizor, din pagina sau la termen); o incercare veche nu mai schimba nimic"""
	if not _INCERCARE["activa"] or numar != _INCERCARE["id"]:
		return
	V, S = _INCERCARE["V"], _INCERCARE["S"]
	sesiune, fisier, inainte = _INCERCARE["sesiune"], _INCERCARE["fisier"], _INCERCARE["inainte"]
	video, culori = _INCERCARE.get("video", True), _INCERCARE.get("culori", False)
	culori_scrise, culori_text = _INCERCARE.get("culori_scrise", False), _INCERCARE.get("culori_text")
	culori_repornire = _INCERCARE.get("culori_repornire", False)
	_INCERCARE.update({"activa": False, "dlg": None, "ceas": None, "inainte": None, "video": True, "culori": False,
		"culori_scrise": False, "culori_text": None, "culori_repornire": False})
	el = V.colorElement() if culori else None
	if raspuns:
		if video:
			V.keepVideo(fisier, [el] if el is not None else [])
			mesaj = _t("Setarea video nouă a rămas.")
		else:
			if el is not None:
				el.save()
			fisier.save()
			mesaj = _t("Salvat.")
		if culori_text:
			mesaj += "\n" + culori_text
		_noteaza(mesaj, True, repornire=culori_repornire)
		_jurnal("incercare %d: pastrata" % numar)
	else:
		if video:
			V.cancelVideo(inainte, sesiune.nav, True)
		if el is not None:
			el.cancel()
		_noteaza(_faraCulori(S, S.notConfirmedText() if video else "", culori_scrise), False,
			repornire=culori_scrise)
		_jurnal("incercare %d: setarea de dinainte" % numar)


def _inchideIntrebarea(raspuns):
	"""inchide intrebarea de pe televizor cu raspunsul dat, ca tasta de pe telecomanda (acelasi drum, _raspuns); daca
	fereastra nu se mai poate inchide (alta fereastra deasupra), raspunsul se aplica direct"""
	numar = _INCERCARE["id"]
	dlg = _INCERCARE["dlg"]
	try:
		if dlg is None:
			raise RuntimeError("fara fereastra")
		dlg.close(raspuns)
	except Exception as eroare:
		_jurnal("intrebarea de pe televizor nu s-a inchis (%s), raspunsul se aplica direct" % eroare)
	_raspuns(numar, raspuns)


def _laTermen(numar):
	if _INCERCARE["activa"] and numar == _INCERCARE["id"]:
		_jurnal("incercare %d: termenul a trecut fara raspuns" % numar)
		_inchideIntrebarea(False)


def raspunde(raspuns, V=None, S=None, sesiune=None, acum=None):
	"""POST /api/video-confirma (raspuns True) si /api/video-revino (False)."""
	V = _v(V)
	S = _s(S)
	acum = time.time() if acum is None else acum
	if not _INCERCARE["activa"]:
		rez = stare(V, S, sesiune, acum, reciteste=False)
		return _cuMesaj(rez, False, _t("Nu se încearcă acum niciun mod video."))
	_inchideIntrebarea(bool(raspuns))
	return _cuMesaj(stare(V, S, sesiune, acum, reciteste=False), True, _ULTIMUL["mesaj"])


def _repornireInCurs(sesiune):
	"""True cand merge o inregistrare sau o lucrare: TryQuitMainloop intreaba atunci pe televizor"""
	try:
		if sesiune.nav.getRecordings():
			return True
	except Exception:
		pass
	try:
		from Components.Task import job_manager
		return bool(job_manager.getPendingJobs())
	except Exception:
		return False


def reporneste(V=None, S=None, sesiune=None, acum=None, ceas=None):
	"""POST /api/video-reporneste: repornirea receptorului, ca „Da” la intrebarea de repornire de pe televizor
	(numai o repornire intreaga readuce iesirea la RGB). Deschide TryQuitMainloop(2) pe televizor dupa REPORNIRE_S, ca
	raspunsul sa plece intai; cu o inregistrare in curs TryQuitMainloop intreaba acolo."""
	V = _v(V)
	S = _s(S)
	acum = time.time() if acum is None else acum
	ceas = ceas or _ceasImplicit
	baza = stare(V, S, sesiune, acum, reciteste=False)
	if not baza["result"]:
		return baza
	refuz = ocupat(sesiune, acum)
	if refuz:
		return _cuMesaj(baza, False, refuz)

	def deschide():
		from Screens.Standby import TryQuitMainloop
		sesiune.open(TryQuitMainloop, 2)
	intreaba = _repornireInCurs(sesiune)
	_INCERCARE["repornire"] = ceas(REPORNIRE_S, deschide)
	_ULTIMUL["repornire"] = False          # butonul dispare din pagina
	_jurnal("repornirea receptorului ceruta din pagina%s" % (", cu intrebare pe televizor" if intreaba else ""))
	if intreaba:
		mesaj = _t("Merge o înregistrare sau o lucrare: răspunde la întrebarea de pe televizor.")
	else:
		mesaj = _t("Receptorul repornește. Pagina merge din nou după pornire.")
	return _cuMesaj(stare(V, S, sesiune, acum, reciteste=False), True, mesaj)


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, numai cheile stiute, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ARGUMENTE:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_VALOARE].strip()
	return rez


def rute(baza, resource, sesiune=None, V=None, S=None, configfile=None, ceas=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	e o functie care da sesiunea enigma2."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/video: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(V, S, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True

		def fa(self, a):
			raise NotImplementedError

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.fa(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class SeteazaResource(_Schimba):
		def fa(self, a):
			return seteaza(a, V, S, _ses(), configfile, ceas=ceas)

	class ConfirmaResource(_Schimba):
		def fa(self, a):
			return raspunde(True, V, S, _ses())

	class RevinoResource(_Schimba):
		def fa(self, a):
			return raspunde(False, V, S, _ses())

	class ReportesteResource(_Schimba):
		def fa(self, a):
			return reporneste(V, S, _ses(), ceas=ceas)

	class PaginaResource(resource.Resource):
		"""GET /video: pagina „Video”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"video": StareResource(),
		b"video-seteaza": SeteazaResource(),
		b"video-confirma": ConfirmaResource(),
		b"video-revino": RevinoResource(),
		b"video-reporneste": ReportesteResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /ceas si /limbi."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("video_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,300px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-of-type{border-bottom:0;}
  .rand label{font-size:.98rem;}
  select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .butoane{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 0;}
  .acum{font-size:1rem;line-height:1.45;margin:0;}
  #intrebare{font-size:1.2rem;font-weight:600;}
  .nota{color:var(--text-slab);font-size:.875rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .atentie{color:#ffd28a;}
  .incercare{border-color:var(--galben);}
  .secunde{font-size:1rem;font-variant-numeric:tabular-nums;margin:6px 0;color:var(--text-slab);}
  .ascuns{display:none;}
  .rand.lat{grid-template-columns:1fr minmax(150px,420px);}
  @media (max-width:560px){ .rand, .rand.lat{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Video</h1>
<p class="mesaj" id="incarcare">Se citesc setările video ale receptorului...</p>
<div id="continut" class="ascuns">
  <section class="card incercare ascuns" id="incercare">
    <p class="acum" id="intrebare"></p>
    <p class="secunde" id="secunde"></p>
    <div class="butoane">
      <button type="button" class="verde" id="pastreaza">Păstrează</button>
      <button type="button" id="revino">Revino</button>
    </div>
  </section>
  <section class="card">
    <p class="acum">Acum: <span id="acum"></span></p>
    <div class="rand">
      <label for="rezolutie">Rezoluție</label>
      <select id="rezolutie"></select>
    </div>
    <div class="rand">
      <label for="frecventa">Frecvență</label>
      <select id="frecventa"></select>
    </div>
    <div id="culori"></div>
    <p class="nota atentie" id="avertisment"></p>
    <div class="butoane"><button type="button" class="verde" id="incearca">Încearcă pe televizor</button></div>
    <p class="nota">Un mod nou se vede întâi pe televizor și rămâne numai dacă îl păstrezi, aici sau din telecomandă. Dacă televizorul rămâne negru, apasă Revino.</p>
  </section>
  <section class="card ascuns" id="cardCulori">
    <div class="rand lat">
      <label for="culoriHdmi" id="culoriEticheta">Culorile pe HDMI</label>
      <select id="culoriHdmi"></select>
    </div>
    <p class="nota" id="culoriDescriere"></p>
  </section>
  <section class="card ascuns" id="cardImagine43">
    <div class="rand lat">
      <label for="imagine43" id="imagine43Eticheta">Imaginea 4:3</label>
      <select id="imagine43"></select>
    </div>
    <p class="nota" id="imagine43Descriere"></p>
  </section>
  <section class="card ascuns" id="cardZap">
    <div class="rand lat">
      <label for="zapmode" id="zapEticheta">La schimbarea canalului</label>
      <select id="zapmode"></select>
    </div>
    <p class="nota" id="zapDescriere"></p>
  </section>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
  <p class="mesaj" id="mesaj"></p>
  <div class="butoane ascuns" id="cardRepornire"><button type="button" id="reporneste">Repornește receptorul</button></div>
</div>
</main>
<script>
var CFG = __CONFIG__;
var D = null;
var alegeriSchimbate = false;
var eraActiva = false;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function umple(sel, alegeri, ales){
  sel.textContent = "";
  alegeri.forEach(function(a){
    var o = document.createElement("option");
    o.value = a[0]; o.textContent = a[1];
    sel.appendChild(o);
  });
  sel.value = ales;
}
function frecventePentru(rez){ return (D && D.frecvente && D.frecvente[rez]) || []; }
function alegeFrecventa(rez, veche, vecheText){
  // ca pe televizor: „Automat” ramane „Automat”, aceeasi frecventa (acelasi text, „60 Hz”) ramane, altfel prima
  var lista = frecventePentru(rez);
  for(var i = 0; i < lista.length; i++){ if(lista[i][0] === veche){ return veche; } }
  for(var j = 0; j < lista.length; j++){ if(lista[j][0] !== "auto" && lista[j][1] === vecheText){ return lista[j][0]; } }
  return lista.length ? lista[0][0] : "";
}
function randCuloare(c){
  var div = document.createElement("div"); div.className = "rand";
  var l = document.createElement("label"); l.htmlFor = "c_" + c.nume; l.textContent = c.eticheta;
  var s = document.createElement("select"); s.id = "c_" + c.nume; s.dataset.nume = c.nume;
  umple(s, c.alegeri, c.valoare);
  s.addEventListener("change", function(){ alegeriSchimbate = true; });
  div.appendChild(l); div.appendChild(s);
  return div;
}
function arata(d){
  D = d;
  var inc = d.incercare || {};
  $("incercare").classList.toggle("ascuns", !inc.activa);
  // numai intrebarea; ce se intampla fara raspuns spune randul secundelor, acelasi text ca pe televizor
  $("intrebare").textContent = (inc.intrebare || "").split("\\n")[0];
  $("secunde").textContent = inc.activa ? (d.numaratoare || "") : "";
  // pe telefon cartea intrebarii poate fi deasupra ecranului (s-a ales din cartea culorilor): adusa in ecran la
  // inceputul incercarii; la sfarsit, mesajul de jos si butonul de repornire (la capatul functiei, dupa ce se vede)
  if(inc.activa && !eraActiva){ $("incercare").scrollIntoView({block: "start", behavior: "smooth"}); }
  var sfarsit = !inc.activa && eraActiva;
  eraActiva = !!inc.activa;
  $("acum").textContent = d.eticheta_mod + (d.frecventa === "auto" ? ", automat după canal" : "") + (d.simulare ? " (simulare, fără driver video)" : "");
  if(!alegeriSchimbate || inc.activa){
    umple($("rezolutie"), d.rezolutii || [], d.rezolutie);
    umple($("frecventa"), frecventePentru(d.rezolutie), d.frecventa);
    var culori = $("culori"); culori.textContent = "";
    (d.culori || []).forEach(function(c){ culori.appendChild(randCuloare(c)); });
    alegeriSchimbate = false;
  }
  $("avertisment").textContent = d.avertisment || "";
  var blocat = !!(inc.activa || d.ocupat);
  ["rezolutie", "frecventa", "incearca", "zapmode", "imagine43", "culoriHdmi"].forEach(function(id){ $(id).disabled = blocat; });
  if(d.culori_hdmi){
    $("cardCulori").classList.remove("ascuns");
    $("culoriEticheta").textContent = d.culori_hdmi.eticheta;
    if(document.activeElement !== $("culoriHdmi")){ umple($("culoriHdmi"), d.culori_hdmi.alegeri, d.culori_hdmi.valoare); }
    $("culoriDescriere").textContent = d.culori_hdmi.descriere || "";
  } else {
    $("cardCulori").classList.add("ascuns");
  }
  if(d.imagine43){
    $("cardImagine43").classList.remove("ascuns");
    $("imagine43Eticheta").textContent = d.imagine43.eticheta;
    if(document.activeElement !== $("imagine43")){ umple($("imagine43"), d.imagine43.alegeri, d.imagine43.valoare); }
    $("imagine43Descriere").textContent = d.imagine43.descriere || "";
  } else {
    $("cardImagine43").classList.add("ascuns");
  }
  if(d.zapmode){
    $("cardZap").classList.remove("ascuns");
    $("zapEticheta").textContent = d.zapmode.eticheta;
    if(document.activeElement !== $("zapmode")){ umple($("zapmode"), d.zapmode.alegeri, d.zapmode.valoare); }
    $("zapDescriere").textContent = d.zapmode.descriere || "";
  } else {
    $("cardZap").classList.add("ascuns");
  }
  if(d.ocupat && !inc.activa){ mesaj(d.ocupat, true); }
  else if(inc.ultimul && !$("mesaj").dataset.fix){ mesaj(inc.ultimul.mesaj, !inc.ultimul.reusit && !inc.ultimul.repornire); }
  var repornire = !!(inc.ultimul && inc.ultimul.repornire && !inc.activa);
  $("cardRepornire").classList.toggle("ascuns", !repornire);
  $("reporneste").disabled = !!d.ocupat;
  if(sfarsit && repornire){ $("cardRepornire").scrollIntoView({block: "end", behavior: "smooth"}); }
  else if(sfarsit){ $("mesaj").scrollIntoView({block: "center", behavior: "smooth"}); }
}
function citeste(){
  return cerere("/api/video").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările video."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cale, q){
  mesaj("Se trimite...");
  $("mesaj").dataset.fix = "1";
  return cerere(cale, "POST", q).then(function(d){
    // cat merge o incercare, intrebarea e deja in chenarul de sus: jos nu se mai scrie a doua oara
    var inCurs = d.result && d.incercare && d.incercare.activa;
    var ultimul = d.incercare && d.incercare.ultimul;
    mesaj(inCurs ? "" : d.message, !d.result && !(ultimul && ultimul.repornire));
    if(d.rezolutii){ alegeriSchimbate = false; arata(d); }
    // o salvare directa care cere repornirea (RGB cu iesirea YCbCr): mesajul si butonul adusi in ecran
    if(!inCurs && ultimul && ultimul.repornire && d.message === ultimul.mesaj){
      $("cardRepornire").scrollIntoView({block: "end", behavior: "smooth"});
    }
    setTimeout(function(){ delete $("mesaj").dataset.fix; }, 4000);
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("rezolutie").addEventListener("change", function(){
  alegeriSchimbate = true;
  var sel = $("frecventa");
  var vecheText = sel.selectedIndex >= 0 ? sel.options[sel.selectedIndex].textContent : "";
  umple(sel, frecventePentru($("rezolutie").value), alegeFrecventa($("rezolutie").value, sel.value, vecheText));
});
$("frecventa").addEventListener("change", function(){ alegeriSchimbate = true; });
$("incearca").addEventListener("click", function(){
  var q = new URLSearchParams();
  q.set("rezolutie", $("rezolutie").value);
  q.set("frecventa", $("frecventa").value);
  Array.prototype.forEach.call(document.querySelectorAll("#culori select"), function(s){ q.set(s.dataset.nume, s.value); });
  trimite("/api/video-seteaza", q);
});
$("zapmode").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("zapmode", $("zapmode").value);
  trimite("/api/video-seteaza", q);
});
$("imagine43").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("imagine43", $("imagine43").value);
  trimite("/api/video-seteaza", q);
});
$("culoriHdmi").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("culori_hdmi", $("culoriHdmi").value);
  trimite("/api/video-seteaza", q);
});
$("pastreaza").addEventListener("click", function(){ trimite("/api/video-confirma", new URLSearchParams()); });
$("revino").addEventListener("click", function(){ trimite("/api/video-revino", new URLSearchParams()); });
$("reporneste").addEventListener("click", function(){
  $("cardRepornire").classList.add("ascuns");
  trimite("/api/video-reporneste", new URLSearchParams());
});
function bucla(){
  citeste().then(function(){
    var activa = D && D.incercare && D.incercare.activa;
    setTimeout(bucla, activa ? 1000 : 5000);
  });
}
bucla();
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
		N_("Video"),
		N_("Se citesc setările video ale receptorului..."),
		N_("Păstrează"),
		N_("Revino"),
		N_("Acum: <span id=\"acum\"></span>"),
		N_("Rezoluție"),
		N_("Frecvență"),
		N_("Încearcă pe televizor"),
		N_("Un mod nou se vede întâi pe televizor și rămâne numai dacă îl păstrezi, aici sau din "
			"telecomandă. Dacă televizorul rămâne negru, apasă Revino."),
		N_("Culorile pe HDMI"),
		N_("Imaginea 4:3"),
		N_("La schimbarea canalului"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
		N_("Repornește receptorul"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_(", automat după canal"),
		N_("(simulare, fără driver video)"),
		N_("Receptorul nu a putut citi setările video."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("Receptorul nu răspunde."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
