# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSubtitrariAspect - cum arata subtitrarile TEXT (teletext, subtitrarile din fisiere si
# textul citit din pozele subtitrarilor DVB): fontul, grosimea, marimea si culoarea literelor, conturul si culoarea
# lui, umbra (culoarea, directia, distanta, moale sau tare), fundalul din spatele randurilor (pe fiecare rand sau o
# cutie, culoarea, opacitatea), inaltimea fata de marginea de jos si distanta dintre randuri; si cateva stiluri gata
# facute. Plus marirea subtitrarilor DVB (vezi mai jos).
#
# Subtitrarile teletext sunt litere, deci se pot desena frumos, cu umbra; la fel cele facute litere prin OCR: umbra,
# grosimea literelor, marimea, fontul, fundalul, conturul, directia umbrei, culoarea literei si a conturului.
#
# Desenul e in C++ (lib/gui/esubtitle.cpp, eSubtitleWidget::setStyle): aici sunt numai setarile
# (config.subtitles.hds_*), trecerea lor in numere si punerea lor in eSubtitleWidget, la pornire (din
# Screens/SubtitleDisplay.py, inainte de prima subtitrare) si la fiecare schimbare (notificari), deci si din ecranul
# „Aspectul subtitrărilor" in timp ce omul alege, si la anulare. Cand se schimba multe deodata (un stil gata facut,
# valorile de la inceput, anularea, pagina web), notificarile tac si stilul se pune o singura data (altfel textul de
# pe ecran s-ar reface de zeci de ori).
#
# Fonturile: al imaginii (skinul: HdsBold la teletext, HdsRegular la fisiere), al imaginii ingust (HdsCond), Tiresias
# Infofont si PCfont (GPL-3.0-or-later cu exceptia de font; fisiere separate, nemodificate, in /usr/share/fonts/tiresias,
# din pachetul hdsatelit-fonturi-tiresias, cu licenta langa ele; date lui addFont aici, dupa verificaFisierFont, pentru
# ca addFont opreste enigma2 pe un fisier care nu e font; fara pachet, alegerile Tiresias lipsesc si o setare salvata
# Tiresias cade pe fontul imaginii) si fonturile descarcate de pe Google (Components/HdsFonturiGoogle.py le
# inregistreaza la pornire). Tiresias are numai Latin-1 (fara ă, ș, ț): eticheta o spune, iar C++ lasa pe fontul
# imaginii textul pe care fontul ales nu-l poate scrie intreg (eTextPara::missingGlyphs).
#
# Culorile se tin ca text „#rrggbb": pe televizor se alege din paleta, in web orice culoare; o culoare din afara
# paletei apare pe televizor ca „Altă culoare (#RRGGBB)".
#
# Pentru interfata web (Plugins/Extensions/HdsWebControl/subtitrari_web.py, pagina /subtitrari): stare() da valorile
# ca text, seteaza() le verifica si le salveaza, aplicaStil() pune un stil gata facut; aceeasi sursa ca ecranul.
#
# „Mărirea subtitrărilor DVB" (config.subtitles.hds_marire_dvb): cum se
# mareste poza unei subtitrari DVB (720x576) pe ecran: fara netezire (pixelii mariti), clara (amestecul cu marginea
# stransa din lib/gdi/gpixmap.cpp, blit_scaled_sharp_8, 3e1e1db8: ce face imaginea acum), OCR (literele recunoscute
# si desenate cu stilul de mai sus) si GPU (placa video Mali). OCR e legat: lib/gui/esubtitle.cpp
# (setOcrHandler) + Components/HdsOcrSubtitrari.py, care urmareste singur setarea (legaNucleul); fara serviciul hds-ocr
# sau fara modele ramane poza, marita „clar". Probat pe receptor pe canale, deci fara eticheta „(netestat)"; implicit
# ramane „clara". Aceeasi alegere se aplica si pozelor din filme (VobSub, PGS), prin aceeasi cale (setPage).
# Se ofera NUMAI ce merge (meniul si web-ul arata doar variantele
# disponibile): „clara" si OCR, iar OCR numai cand exista /usr/bin/hds-ocr si cel putin un model (ocrDisponibil);
# fara el ramane o singura alegere si randul nu se arata deloc (seAlegeMarireaDvb), nici pe
# televizor, nici in web. „fara" si „gpu" sunt moduri ale lui gPixmap (lib/gdi/gpixmap.cpp, setSubtitleScaleMode;
# GPU in lib/gdi/hdsgpu.cpp, cu rezerva pe procesor), dar nimic din Python nu le trimite inca: pana atunci nu apar nici pe televizor, nici in web, iar o valoare salvata „fara"/„gpu" se citeste
# „clara". numarMarireDvb() da numarul pentru gPixmap (0 fara, 1 clara, 2 OCR = poza tot clara, 3 GPU); ordinea din
# MARIRI_DVB nu se schimba.

from __future__ import absolute_import

import os
import re
from contextlib import contextmanager


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: etichetele din tabelele de mai jos se
	traduc la folosire, cu _t()."""
	return text


# procente fata de litera din skin (<subtitles> in skin.xml: 50 px la HDSatelit)
MARIMI = tuple(range(60, 201, 10))
# procente din inaltimea ecranului, de la marginea de jos pana sub ultimul rand
INALTIMI = tuple(range(2, 26))
# ordinea da numarul trimis in C++ (eSubtitleWidget::setStyle)
GROSIMI = ("automata", "normala", "ingrosata", "foarte_ingrosata")
CONTURURI = ("fara", "subtire", "normal", "gros", "foarte_gros")
DIRECTII = ("sus", "sus_dreapta", "dreapta", "jos_dreapta", "jos", "jos_stanga", "stanga", "sus_stanga")
UMBRE = ("tare", "moale", "foarte_moale")
FUNDALURI = ("niciunul", "rand", "cutie")
# procente fata de distanta obisnuita a umbrei, opacitatea fundalului, distanta dintre randuri
DISTANTE = (50, 100, 150, 200, 300)
OPACITATI = tuple(range(10, 101, 10))
SPATIERI = (80, 90, 100, 110, 125, 150)
# marirea subtitrarilor DVB (poze): ordinea da numarul pentru C++ (numarMarireDvb, gPixmap::setSubtitleScaleMode);
# se ofera numai MARIRI_DVB_OFERITE (vezi sus); MARIRI_DVB_NETESTATE (acum niciuna) nu mai pune nicio eticheta
MARIRI_DVB = ("fara", "clara", "ocr", "gpu")
MARIRI_DVB_OFERITE = ("clara", "ocr")
MARIRI_DVB_NETESTATE = ()
# OCR se ofera numai cand exista serviciul si macar un model (meniul si web-ul arata doar ce exista). Aceleasi cai ca BINAR si TESSDATA din Components/HdsOcrSubtitrari.py.
OCR_BINAR = "/usr/bin/hds-ocr"
OCR_MODELE = "/usr/share/hds-ocr/tessdata"

# paleta, fara culori de firme; pe televizor se alege din ea, in web orice culoare
PALETA = (
	("#ffffff", N_("Alb")), ("#ffff00", N_("Galben")), ("#fff3b0", N_("Crem")), ("#ffa500", N_("Portocaliu")),
	("#ff3030", N_("Roșu")), ("#ff80c0", N_("Roz")), ("#ff00ff", N_("Magenta")), ("#a060ff", N_("Mov")),
	("#3070ff", N_("Albastru")), ("#80c0ff", N_("Albastru deschis")), ("#00ffff", N_("Cyan")),
	("#00ff00", N_("Verde")), ("#a0ffa0", N_("Verde deschis")), ("#c8c8c8", N_("Gri deschis")),
	("#808080", N_("Gri")), ("#404040", N_("Gri închis")), ("#000000", N_("Negru")),
)
EMISIUNE = "emisiune"
CULOARE_TEXT = re.compile("^#[0-9a-fA-F]{6}$")

# Tiresias: fisierele din reteta hdsatelit-fonturi-tiresias (stratul meta-local);
# aliasul lui addFont = numele fisierului fara .ttf. Un fisier lipsa sau stricat e sarit.
DOSAR_TIRESIAS = "/usr/share/fonts/tiresias"
TIRESIAS = (
	("tiresias_info", "Tiresias Infofont", "TiresiasInfofont", "TiresiasInfofontBold"),
	("tiresias_pc", "Tiresias PCfont", "TiresiasPCfont", "TiresiasPCfontBold"),
)

IMPLICITE = {
	"stil_font": "skin",
	"grosime": "automata",
	"marime": "100",
	"culoare": EMISIUNE,
	"contur": "normal",
	"culoare_contur": "#000000",
	"umbra": True,
	"culoare_umbra": "#000000",
	"directie_umbra": "jos_dreapta",
	"distanta_umbra": "100",
	"umbra_moale": "moale",
	"fundal": "niciunul",
	"culoare_fundal": "#000000",
	"opacitate_fundal": "60",
	"jos": "8",
	"spatiere": "100",
	"marire_dvb": "clara",
}

# ordinea din ecran si din pagina web: intai cele 16 ale stilului literelor (trimise lui eSubtitleWidget.setStyle),
# apoi marirea subtitrarilor DVB (nu merge la setStyle: OCR o urmareste singur, vezi sus)
CHEI_STIL = ("stil_font", "grosime", "marime", "culoare", "contur", "culoare_contur", "umbra", "culoare_umbra",
	"directie_umbra", "distanta_umbra", "umbra_moale", "fundal", "culoare_fundal", "opacitate_fundal", "jos", "spatiere")
CHEI = CHEI_STIL + ("marire_dvb",)
CULORI = ("culoare", "culoare_contur", "culoare_umbra", "culoare_fundal")

# Stilurile gata facute: toate setarile stilului afara de font si de inaltimea fata de marginea de jos (acelea tin de om
# si de televizorul lui, nu de stil); marirea DVB nu tine de stil. Fara nume de firme.
def _stil(**schimbari):
	v = dict((k, IMPLICITE[k]) for k in CHEI_STIL if k not in ("stil_font", "jos"))
	v.update(schimbari)
	return v


STILURI = (
	("clasic", N_("Clasic (ca la început)"), _stil()),
	("galben", N_("Galben, cu contur"), _stil(culoare="#ffff00")),
	("contur_gros", N_("Alb, contur gros, fără umbră"), _stil(culoare="#ffffff", contur="gros", umbra=False)),
	("cutie", N_("Alb pe o cutie neagră"), _stil(culoare="#ffffff", contur="fara", umbra=False, fundal="cutie",
		opacitate_fundal="80")),
	("banda", N_("Alb pe o bandă, pe fiecare rând"), _stil(culoare="#ffffff", contur="fara", umbra=False,
		fundal="rand", opacitate_fundal="60")),
	("umbra_tare", N_("Umbră tare, fără contur"), _stil(culoare="#ffffff", contur="fara", umbra_moale="tare",
		distanta_umbra="150")),
	("citire_usoara", N_("Mare și groasă, pentru citire ușoară"), _stil(marime="130", grosime="ingrosata",
		culoare="#ffff00", contur="gros")),
	("discret", N_("Discret, mai mic"), _stil(marime="90", culoare="#c8c8c8", contur="subtire")),
)
PERSONALIZAT = "personalizat"


def _t(text):
	try:
		return _(text)
	except NameError:	# fara traduceri instalate (probe pe PC)
		return text


# ---------------------------------------------------------------- textele alegerilor

def textPaleta():
	return [(v, _t(t)) for v, t in PALETA]


def textCuloareAltfel(valoare):
	return _t("Altă culoare (%s)") % valoare.upper()


def textGrosimi():
	return [("automata", _t("Ca în imagine (teletextul îngroșat)")), ("normala", _t("Normală")),
		("ingrosata", _t("Îngroșată")), ("foarte_ingrosata", _t("Foarte îngroșată"))]


def textContururi():
	return [("fara", _t("Fără")), ("subtire", _t("Subțire")), ("normal", _t("Normal")), ("gros", _t("Gros")),
		("foarte_gros", _t("Foarte gros"))]


def textDirectii():
	return [("sus", _t("Sus")), ("sus_dreapta", _t("Sus, la dreapta")), ("dreapta", _t("La dreapta")),
		("jos_dreapta", _t("Jos, la dreapta")), ("jos", _t("Jos")), ("jos_stanga", _t("Jos, la stânga")),
		("stanga", _t("La stânga")), ("sus_stanga", _t("Sus, la stânga"))]


def textUmbre():
	return [("tare", _t("Tare (margine netă)")), ("moale", _t("Moale")), ("foarte_moale", _t("Foarte moale"))]


def textFundaluri():
	return [("niciunul", _t("Niciunul")), ("rand", _t("Pe fiecare rând")),
		("cutie", _t("O cutie pentru toate rândurile"))]


def textDistante():
	return [(str(v), "%d%%" % v) for v in DISTANTE]


def textProcente(valori):
	return [(str(v), "%d%%" % v) for v in valori]


def textStiluri():
	return [(PERSONALIZAT, _t("Personalizat"))] + [(cheie, _t(text)) for cheie, text, valori in STILURI]


def ocrDisponibil():
	"""True numai daca serviciul hds-ocr se poate porni (executabil) si are cel putin un model (.traineddata). Altfel
	alegerea OCR nu se arata, nici pe televizor, nici in web, iar o valoare „ocr” salvata se citeste „clara”."""
	if not os.access(OCR_BINAR, os.X_OK):
		return False
	try:
		return any(nume.endswith(".traineddata") for nume in os.listdir(OCR_MODELE))
	except OSError:
		return False


def maririDvbOferite():
	"""MARIRI_DVB_OFERITE fara ce lipseste acum pe receptor (OCR fara serviciu sau fara modele)."""
	return tuple(c for c in MARIRI_DVB_OFERITE if c != "ocr" or ocrDisponibil())


def textMaririDvb():
	"""Alegerile oferite (maririDvbOferite(), in ordinea din MARIRI_DVB), fara semne de stare (MARIRI_DVB_NETESTATE
	ramane numai pentru probe; Components/HdsStareMeniu.py: starea nu se arata). Textele
	lui „fara" si „gpu" raman aici (si in traduceri) pentru mai tarziu, desi deocamdata nu se ofera."""
	texte = {"fara": _t("Fără netezire"), "clara": _t("Clară (margini netede)"),
		"ocr": _t("Recunoașterea textului (OCR)"), "gpu": _t("Cu placa video (GPU)")}
	oferite = maririDvbOferite()
	return [(cheie, texte[cheie]) for cheie in MARIRI_DVB if cheie in oferite]


def seAlegeMarireaDvb(s=None):
	"""Randul „Mărirea subtitrărilor DVB” se arata (pe televizor si in web) numai cand are ce alege: fara OCR ramane o
	singura alegere, „clara”, deci randul si nota lui nu se arata."""
	return len(element("marire_dvb", s).choices.choices) > 1


def textNotaMarireDvb():
	"""Ce face acum alegerea „Mărirea subtitrărilor DVB" (ecranul o arata sub lista, pagina web sub rand); se aplica si
	pozelor din filme (VobSub, PGS), deci nota le numeste."""
	return _t("Subtitrările DVB și cele DVD sau Blu-ray din filme sunt imagini. Recunoașterea textului citește literele "
		"și le desenează cu aspectul de mai sus; când textul nu e sigur, rămâne imaginea, mărită clar.")


def textProba():
	"""Fraza de proba din previzualizare: doua randuri, ca o subtitrare obisnuita."""
	return u"%s\n%s" % (_t("Așa vor arăta subtitrările text."), _t("Literele se citesc și pe o imagine deschisă."))


# ---------------------------------------------------------------- fonturile

_tiresias = {}	# alias -> verificarea fisierului (numai cele date lui addFont)
_tiresias_cautat = [False]


def _verifica(cale):
	"""verificaFisierFont din HdsFonturiGoogle (semnatura, tabelele, numele, diacriticele); None daca nu se poate."""
	try:
		from Components.HdsFonturiGoogle import verificaFisierFont
	except Exception as e:
		print("[HdsSubtitrariAspect] verificarea fonturilor nu se poate incarca: %s" % e)
		return None
	return verificaFisierFont(cale)


def inregistreazaTiresias(dosar=None):
	"""Da fonturile Tiresias lui addFont, o singura data, numai dupa verificare (addFont opreste enigma2 pe un fisier
	care nu e font). Un fisier lipsa sau stricat e sarit: alegerea nu apare. Nu arunca."""
	if _tiresias_cautat[0]:
		return dict(_tiresias)
	_tiresias_cautat[0] = True
	dosar = dosar or DOSAR_TIRESIAS
	try:
		from enigma import addFont
	except Exception as e:
		print("[HdsSubtitrariAspect] addFont nu se poate incarca: %s" % e)
		return {}
	for cheie, nume, obisnuit, gros in TIRESIAS:
		for alias in (obisnuit, gros):
			cale = os.path.join(dosar, alias + ".ttf")
			if not os.path.isfile(cale):
				continue
			verificare = _verifica(cale)
			if not verificare or not verificare.get("bun"):
				print("[HdsSubtitrariAspect] sarit %s: %s" % (cale, verificare and verificare.get("motiv")))
				continue
			try:
				addFont(cale, alias, 100, 0)
			except Exception as e:
				print("[HdsSubtitrariAspect] addFont a esuat pentru %s: %s" % (cale, e))
				continue
			_tiresias[alias] = verificare
	return dict(_tiresias)


def _aliasuriGoogle():
	try:
		from Components import HdsFonturiGoogle
		return list(HdsFonturiGoogle.aliasuriInregistrate())
	except Exception:
		return []


def _faraDiacritice(verificare):
	try:
		from Components.HdsFonturiGoogle import areDiacriticeRomanesti
		return not areDiacriticeRomanesti(verificare)
	except Exception:
		return False


def fonturi(cu_diacritice=False):
	"""Fonturile care se pot alege acum: [(cheie, text, alias, alias_gros)], in ordinea din ecran. „skin" = fonturile
	skinului (alias gol). cu_diacritice: la fonturile descarcate se citeste fisierul, ca eticheta sa spuna daca are
	ă, ș, ț (la Tiresias se stie din verificarea de la inregistrare)."""
	inregistreazaTiresias()
	lista = [("skin", _t("Fontul imaginii"), "", ""), ("ingust", _t("Fontul imaginii, îngust"), "HdsCond", "")]
	for cheie, nume, obisnuit, gros in TIRESIAS:
		if obisnuit not in _tiresias:
			continue
		text = nume
		if _faraDiacritice(_tiresias[obisnuit]):
			text = _t("%s (fără ă, ș, ț)") % nume
		lista.append((cheie, text, obisnuit, gros if gros in _tiresias else ""))
	google = _aliasuriGoogle()
	detalii = {}
	if google and cu_diacritice:
		try:
			from Components import HdsFonturiGoogle
			for f in HdsFonturiGoogle.fonturiDescarcate():
				detalii[f["alias"]] = f
		except Exception:
			detalii = {}
	for alias in google:
		text = detalii.get(alias, {}).get("familie") or alias
		if alias in detalii and _faraDiacritice(detalii[alias]):
			text = _t("%s (fără ă, ș, ț)") % text
		lista.append(("google:" + alias, _t("%s (descărcat)") % text, alias, ""))
	return lista


# ---------------------------------------------------------------- setarile

_tacere = [0]


@contextmanager
def oSinguraAplicare(pune=True):
	"""Cat tine blocul, schimbarile nu pun stilul pe rand; la sfarsit se pune o data (pune=False: deloc, cand s-a
	schimbat numai marirea DVB, care nu tine de stil)."""
	_tacere[0] += 1
	try:
		yield
	finally:
		_tacere[0] -= 1
		if not _tacere[0] and pune:
			aplica()


def _alegeriCuloare(cu_emisiune, curenta):
	alegeri = ([(EMISIUNE, _t("Culorile emisiunii"))] if cu_emisiune else []) + textPaleta()
	if curenta and CULOARE_TEXT.match(curenta) and curenta.lower() not in [v for v, t in alegeri]:
		alegeri.append((curenta.lower(), textCuloareAltfel(curenta)))
	return alegeri


# valorile vechi (6 setari): culoarea dupa nume, fundalul „semitransparent" (atunci 160 din
# 255, cam 63%; acum „pe fiecare rand" cu opacitatea implicita de 60%, adica 153 din 255)
_CULORI_VECHI = {"alb": "#ffffff", "galben": "#ffff00", "cyan": "#00ffff", "verde": "#00ff00"}
_FUNDAL_VECHI = {"semitransparent": "rand"}


def initConfig():
	"""config.subtitles.hds_*; se poate chema de oricate ori (a doua oara intoarce ce exista)."""
	from Components.config import config, ConfigSubsection, ConfigSelection, ConfigYesNo
	if "subtitles" not in config.content.items:
		config.subtitles = ConfigSubsection()
	s = config.subtitles
	if "hds_marime" in s.content.items:
		return s
	salvate = s.content.stored_values
	migrate = {}
	for cheie, vechi in (("hds_culoare", _CULORI_VECHI), ("hds_fundal", _FUNDAL_VECHI)):
		v = salvate.get(cheie)
		if v in vechi:
			migrate[cheie] = vechi[v]
	s.hds_stil_font = ConfigSelection(choices=[(c, t) for c, t, o, g in fonturi()],
		default=IMPLICITE["stil_font"])
	s.hds_grosime = ConfigSelection(choices=textGrosimi(), default=IMPLICITE["grosime"])
	s.hds_marime = ConfigSelection(choices=textProcente(MARIMI), default=IMPLICITE["marime"])
	s.hds_culoare = ConfigSelection(choices=_alegeriCuloare(True, salvate.get("hds_culoare")),
		default=IMPLICITE["culoare"])
	s.hds_contur = ConfigSelection(choices=textContururi(), default=IMPLICITE["contur"])
	s.hds_culoare_contur = ConfigSelection(choices=_alegeriCuloare(False, salvate.get("hds_culoare_contur")),
		default=IMPLICITE["culoare_contur"])
	s.hds_umbra = ConfigYesNo(default=IMPLICITE["umbra"])
	s.hds_culoare_umbra = ConfigSelection(choices=_alegeriCuloare(False, salvate.get("hds_culoare_umbra")),
		default=IMPLICITE["culoare_umbra"])
	s.hds_directie_umbra = ConfigSelection(choices=textDirectii(), default=IMPLICITE["directie_umbra"])
	s.hds_distanta_umbra = ConfigSelection(choices=textDistante(), default=IMPLICITE["distanta_umbra"])
	s.hds_umbra_moale = ConfigSelection(choices=textUmbre(), default=IMPLICITE["umbra_moale"])
	s.hds_fundal = ConfigSelection(choices=textFundaluri(), default=IMPLICITE["fundal"])
	s.hds_culoare_fundal = ConfigSelection(choices=_alegeriCuloare(False, salvate.get("hds_culoare_fundal")),
		default=IMPLICITE["culoare_fundal"])
	s.hds_opacitate_fundal = ConfigSelection(choices=textProcente(OPACITATI), default=IMPLICITE["opacitate_fundal"])
	s.hds_jos = ConfigSelection(choices=textProcente(INALTIMI), default=IMPLICITE["jos"])
	s.hds_spatiere = ConfigSelection(choices=textProcente(SPATIERI), default=IMPLICITE["spatiere"])
	s.hds_marire_dvb = ConfigSelection(choices=textMaririDvb(), default=IMPLICITE["marire_dvb"])
	# valorile vechi, puse si ca salvate: Anularea le intoarce pe cele noi, nu la implicit
	for cheie, valoare in migrate.items():
		element = getattr(s, cheie)
		element.value = valoare
		element.saved_value = valoare
	# numai stilul literelor ajunge in setStyle; marirea DVB o urmareste Components/HdsOcrSubtitrari.py (legaNucleul)
	for element in elemente(s, CHEI_STIL):
		element.addNotifier(_laSchimbare, initial_call=False)
	return s


def elemente(s=None, chei=CHEI):
	"""Setarile, in ordinea CHEI (toate 17: cele 16 ale stilului si marirea DVB) sau in ordinea `chei`."""
	s = s if s is not None else initConfig()
	return [getattr(s, "hds_" + cheie) for cheie in chei]


def element(cheie, s=None):
	s = s if s is not None else initConfig()
	return getattr(s, "hds_" + cheie)


def reimprospateazaFonturi():
	"""Alegerile de font din nou (un font descarcat intre timp, eticheta cu ă, ș, ț); valoarea ramane daca mai
	exista."""
	s = initConfig()
	e = s.hds_stil_font
	alegeri = [(c, t) for c, t, o, g in fonturi(cu_diacritice=True)]
	valoare = e.value
	# stilul se pune din nou numai daca fontul ales a disparut (pagina web cheama asta la fiecare citire)
	_tacere[0] += 1
	try:
		e.setChoices(alegeri, default=IMPLICITE["stil_font"])
		if valoare in [c for c, t in alegeri] and e.value != valoare:
			e.value = valoare
	finally:
		_tacere[0] -= 1
	if e.value != valoare and not _tacere[0]:
		aplica()
	return alegeri


def _numar(valoare, permise, implicit):
	try:
		n = int(valoare)
	except (TypeError, ValueError):
		return int(implicit)
	return n if n in permise else int(implicit)


def _index(valoare, lista, implicit):
	return lista.index(valoare) if valoare in lista else lista.index(implicit)


def _culoare(valoare, implicit):
	if valoare and CULOARE_TEXT.match(valoare):
		return int(valoare[1:], 16)
	return int(implicit[1:], 16)


def valoriStil():
	"""Argumentele pentru eSubtitleWidget.setStyle, toate in limitele de acolo: (font, font_gros, grosime, marime,
	culoare, contur, culoare_contur, umbra, culoare_umbra, directie, distanta, moale, fundal, culoare_fundal,
	opacitate, jos, spatiere); culorile ca 0xRRGGBB, culoarea literelor -1 = a emisiunii."""
	s = initConfig()
	font, gros = "", ""
	for cheie, text, obisnuit, varianta in fonturi():
		if cheie == s.hds_stil_font.value:
			font, gros = obisnuit, varianta
	culoare = -1 if s.hds_culoare.value == EMISIUNE else _culoare(s.hds_culoare.value, "#ffffff")
	return (
		font, gros,
		_index(s.hds_grosime.value, GROSIMI, IMPLICITE["grosime"]),
		_numar(s.hds_marime.value, MARIMI, IMPLICITE["marime"]),
		culoare,
		_index(s.hds_contur.value, CONTURURI, IMPLICITE["contur"]),
		_culoare(s.hds_culoare_contur.value, IMPLICITE["culoare_contur"]),
		1 if s.hds_umbra.value else 0,
		_culoare(s.hds_culoare_umbra.value, IMPLICITE["culoare_umbra"]),
		_index(s.hds_directie_umbra.value, DIRECTII, IMPLICITE["directie_umbra"]),
		_numar(s.hds_distanta_umbra.value, DISTANTE, IMPLICITE["distanta_umbra"]),
		_index(s.hds_umbra_moale.value, UMBRE, IMPLICITE["umbra_moale"]),
		_index(s.hds_fundal.value, FUNDALURI, IMPLICITE["fundal"]),
		_culoare(s.hds_culoare_fundal.value, IMPLICITE["culoare_fundal"]),
		_numar(s.hds_opacitate_fundal.value, OPACITATI, IMPLICITE["opacitate_fundal"]),
		_numar(s.hds_jos.value, INALTIMI, IMPLICITE["jos"]),
		_numar(s.hds_spatiere.value, SPATIERI, IMPLICITE["spatiere"]),
	)


def numarMarireDvb():
	"""Marirea subtitrarilor DVB ca numar, in ordinea MARIRI_DVB (0 fara netezire, 1 clara, 2 OCR, 3 GPU), pentru
	enigma.setSubtitleScaleMode (gpixmap.h). Deocamdata nu o cheama nimeni (vezi sus)."""
	return _index(initConfig().hds_marire_dvb.value, MARIRI_DVB, IMPLICITE["marire_dvb"])


def aplica(*argumente):
	"""Pune setarile in eSubtitleWidget (si textul de pe ecran se reface). Intoarce True daca s-au pus.
	Nu arunca: la pornire, o greseala aici nu trebuie sa opreasca subtitrarile."""
	try:
		valori = valoriStil()
	except Exception as e:
		print("[HdsSubtitrariAspect] setarile nu se pot citi: %s" % e)
		return False
	try:
		from enigma import eSubtitleWidget
		pune = getattr(eSubtitleWidget, "setStyle", None)
	except Exception as e:
		print("[HdsSubtitrariAspect] eSubtitleWidget nu se poate incarca: %s" % e)
		return False
	if pune is None:
		print("[HdsSubtitrariAspect] enigma2 fara eSubtitleWidget.setStyle: aspectul ramane cel din skin")
		return False
	try:
		pune(*valori)
	except Exception as e:
		print("[HdsSubtitrariAspect] setStyle%s: %s" % (valori, e))
		return False
	return True


def _laSchimbare(element):
	if not _tacere[0]:
		aplica()


def pornire():
	"""La pornire (Screens/SubtitleDisplay.py): fonturile Tiresias inregistrate, setarile citite si puse."""
	initConfig()
	return aplica()


# ---------------------------------------------------------------- stilurile gata facute

def stilCurent():
	"""Cheia stilului gata facut care se potriveste cu setarile de acum, altfel PERSONALIZAT."""
	v = stare()
	for cheie, text, valori in STILURI:
		if all(v[k] == valori[k] for k in valori):
			return cheie
	return PERSONALIZAT


def aplicaStil(cheie, salveaza=False):
	"""Pune un stil gata facut (fara font si inaltime); True daca stilul exista."""
	for c, text, valori in STILURI:
		if c == cheie:
			s = initConfig()
			with oSinguraAplicare():
				for k, v in valori.items():
					element(k, s).value = v
			if salveaza:
				_salveaza(s)
			return True
	return False


# ---------------------------------------------------------------- pentru interfata web

def stare():
	"""Valorile ca text: {"stil_font": "skin", "marime": "100", ..., "umbra": True}."""
	s = initConfig()
	rez = {}
	for cheie in CHEI:
		valoare = element(cheie, s).value
		rez[cheie] = bool(valoare) if cheie == "umbra" else valoare
	return rez


def alegeri():
	"""Alegerile fiecarei setari, [valoare, text], ca in ecran (culorile: paleta si culoarea curenta daca e alta)."""
	s = initConfig()
	rez = {}
	for cheie in CHEI:
		if cheie == "umbra":
			rez[cheie] = [["1", _t("Da")], ["0", _t("Nu")]]
			continue
		e = element(cheie, s)
		rez[cheie] = [[v, t] for v, t in e.choices.choices]
	return rez


def _valoareBuna(cheie, valoare):
	if cheie == "umbra":
		return isinstance(valoare, bool)
	if not isinstance(valoare, str):
		valoare = str(valoare)
	if cheie == "culoare":
		return valoare == EMISIUNE or bool(CULOARE_TEXT.match(valoare))
	if cheie in CULORI:
		return bool(CULOARE_TEXT.match(valoare))
	if cheie == "stil_font":
		return valoare in [c for c, t, o, g in fonturi()]
	if cheie == "marire_dvb":
		# ce arata acum setarea (ca pe televizor): OCR numai cand serviciul si modelele erau la pornire
		return valoare in [str(v) for v, t in element(cheie).choices.choices]
	permise = {"grosime": GROSIMI, "contur": CONTURURI, "directie_umbra": DIRECTII, "umbra_moale": UMBRE,
		"fundal": FUNDALURI, "marime": MARIMI, "jos": INALTIMI, "distanta_umbra": DISTANTE,
		"opacitate_fundal": OPACITATI, "spatiere": SPATIERI}[cheie]
	return valoare in [str(p) for p in permise]


def _puneCuloare(e, valoare, cu_emisiune):
	valoare = valoare.lower() if valoare != EMISIUNE else valoare
	if valoare not in list(e.choices):
		e.setChoices(_alegeriCuloare(cu_emisiune, valoare), default=e.default)
	e.value = valoare


def _salveaza(s):
	for e in elemente(s):
		e.save()
	from Components.config import configfile
	configfile.save()


def seteaza(valori, salveaza=True):
	"""Pune valorile date (dictionar cu o parte din CHEI) si le salveaza. Intoarce lista cheilor respinse;
	daca e vreuna respinsa, nu se schimba nimic. Stilul se pune o singura data, la sfarsit."""
	s = initConfig()
	respinse = [cheie for cheie in valori if cheie not in CHEI or not _valoareBuna(cheie, valori[cheie])]
	if respinse:
		return respinse
	with oSinguraAplicare(pune=any(cheie in CHEI_STIL for cheie in valori)):
		for cheie in CHEI:
			if cheie not in valori:
				continue
			valoare = valori[cheie]
			e = element(cheie, s)
			if cheie in CULORI:
				_puneCuloare(e, str(valoare), cheie == "culoare")
			elif cheie == "umbra":
				e.value = valoare
			else:
				e.value = str(valoare)
	if salveaza:
		_salveaza(s)
	return []


def implicite():
	"""Toate setarile inapoi la valorile de la inceput (fara salvare: ecranul salveaza la Verde)."""
	s = initConfig()
	with oSinguraAplicare():
		for cheie in CHEI:
			element(cheie, s).value = IMPLICITE[cheie]
