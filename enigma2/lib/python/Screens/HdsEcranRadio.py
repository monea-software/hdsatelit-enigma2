# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEcranRadio.py: ecranul radio pe tot ecranul.
#
# Cand merge un post de radio, sub bara si sub toate celelalte ferestre sta o fereastra opaca pe tot ecranul cu tot ce
# se afla din semnal: sigla si numele postului, furnizorul, satelitul si numarul din lista, emisiunea de acum (cu cat
# a trecut din ea) si urmatoarele, textul radio (RDS), piesa si artistul (RT+), semnul RaSS, sunetul (codec, debit,
# esantionare, mod, limba), transponderul, semnalul si ceasul, plus vizualizatorul ales (Components/HdsRadioDesen.py),
# hranit numai de sunetul adevarat al postului (Components/HdsRadioAnaliza.py). Datele vin din Components/HdsRadioDate.py,
# aceleasi ca in pagina web /radio.
#
# Cand se arata: dupa serviciul care merge (evStart), nu dupa o tasta, deci la fel din lista radio, din cautare, din
# web, din cifre si din temporizatoare. La un canal TV, la oprirea serviciului si in standby se ascunde. Setarea
# „Ecranul radio pe tot ecranul” (config.hds_radio.ecran, Components/HdsRadioSetari.py) il opreste cu totul.
#
# Tastele (harta HartaRadio din Screens/InfoBar.py, pornita numai cat merge un post de radio):
# - OK: lista de canale pe radio; OK tinut apasat (0,7 s): optiunile ecranului radio (vizualizatorul, culorile,
#   programul postului cand il transmite, setarile, „Ascunde ecranul radio”). Apasarea lunga se afla din ascultatorul global de taste (apasare si
#   eliberare), deci nu cere nimic nou in data/keymap.xml; setarile sunt si in Meniu > Audio > Ecranul radio;
# - stanga / dreapta: postul anterior / urmator din lista radio (lista barei cand e pe radio, altfel lista radio
#   aleasa ultima data, config.radio.lastroot); sus / jos: lista radio;
# - GALBEN: vizualizarea urmatoare; ALBASTRU: culorile urmatoare. Numele alegerii apare cateva secunde peste bare,
#   iar sub bare un rand mic arata tastele. Alegerea ramane in setari (fisierul se scrie o data, la cateva secunde
#   dupa ultima apasare, nu la fiecare). Albastrul deschide altfel extensiile la eliberare (InfobarExtensions, „b”),
#   iar pe telecomanda Viper galbenul deschide la eliberare pistele audio (InfobarAudioSelectionActions,
#   „audioSelection”, „b”): dupa o apasare prinsa de ecranul radio, eliberarea tastei e oprita aici. Tasta AUDIO
#   (audioSelectionPressed / Released / Long) nu e in harta si merge ca inainte;
# - EXIT: inchide bara daca e deschisa, altfel ascunde ecranul radio pana la urmatorul post sau pana la OK.
# OK pe un post de radio in lista de canale porneste postul si inchide lista (Screens/ChannelSelection.py cheama
# okDinLista), deci ecranul radio apare pe tot ecranul, chiar daca fusese ascuns cu EXIT.
#
# Randul „Piesa” si textul radio: pe unul sau doua randuri intregi, niciodata taiate; barele coboara cat trebuie
# (fara sa urce peste texte). Cand postul da mai putine emisiuni urmatoare decat randurile din skin, textele urca sub
# ultima emisiune aratata. Textele vin din Components/HdsRdsText.py (numai mesaje anuntate de decodor, text valid; la
# AAC si din elementul DSE al cadrelor, lib/dvb/radiotext.cpp).
#
# Jos, semnalul si calitatea ca bare, cu aceleasi valori si aceleasi cuvinte ca pe bara de la TV
# (Converter/HdsSignal, Converter/HdsCommon), plus sistemul si accesul in cuvinte. O valoare pe care tunerul nu o da isi
# ascunde bara, procentul si cuvantul; ce ramane se strange la stanga, iar textul randului ia tot locul pana la satelit.
#
# Arderea ecranului: fereastra se muta o data pe minut cu cativa pixeli, pe un drum inchis de cel mult 16 px; ea are in
# skin 16 px in plus in fiecare directie, deci ecranul ramane acoperit la orice pas. Dupa atatea minute fara nicio tasta
# (implicit 10) ramane numai un bloc mic (numele, piesa, ceasul, barele mici si mai inchise) care se muta incet pe
# ecran. Orice tasta aduce ecranul intreg (ascultatorul global de taste nu le opreste).
#
# Asezarea: cand postul nu transmite nici program, nici text radio, barele iau si locul acelor randuri (zona
# „zonaBareMari” din skin); fara sigla pe disc, numele postului ia si locul casetei siglei.
#
# Lista radio separata (ChannelSelectionRadio) e si ea InfoBarBase: cat e deschisa, posturile alese in ea sunt tot ale
# barei (_barPrincipala), iar la inchiderea ei starea se potriveste din nou cu ce merge (dupaListaRadio).
#
# Procesorul: ceasul cadrelor merge numai cat bara e fereastra din fata si vizualizatorul are date; analizorul se
# opreste cand ecranul nu se vede (dupa 5 s) si nu l-a cerut nici pagina web in ultimele 5 s. Pe disc nu se scrie nimic
# in timpul ascultarii; setarile se scriu numai cand omul le schimba.
#
# Skinul: blocurile HdsEcranRadio, HdsEcranRadioOdihna si HdsEcranRadioSetari din skinul HDSatelit; pentru alte
# skinuri, skinurile de rezerva de mai jos, facute la 1920x1080 si scalate la marimea ecranului, numai cu fontul
# „Regular” si culori scrise direct.

import math
import time

from enigma import eActionMap, eTimer, ePoint, eSize, getDesktop, iPlayableService, gFont

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.CanvasSource import CanvasSource
from Components.Sources.Progress import Progress
from Components.Sources.StaticText import StaticText
from Components.config import config, configfile, getConfigListEntry

from Components import HdsRadioSetari as S
from Components import HdsRadioDate as RD
from Components import HdsRadioDesen as DES
from Components import HdsRadioAnaliza as AN
from Components import HdsMarireText as MT
from Tools.ScaledSkin import scaledSkin

# ---------------------------------------------------------------- timpi

MS_SECUNDA = 1000
MS_ASTEPTARE = 1000          # cat timp nu e bara in fata: o privire pe secunda, fara desen
PORNIRE_ANALIZA_MS = 1000    # dupa PMT: decodorul isi ia intai canalul de demultiplexor
SFARSIT_MS = 1500            # dupa evEnd, cat se asteapta urmatorul post inainte de ascundere
OPRIRE_ANALIZA_S = 5         # analizorul se opreste dupa atatea secunde fara ecran vazut si fara web
WEB_S = 5
EPG_S = 30                   # emisiunile se recitesc din cache la atatea secunde (si la fiecare eveniment EPG)
MUTARE_S = 60                # mutarea impotriva arderii
ODIHNA_PAS_S = 20
DRUM_PX = 16
CADRE_ODIHNA = 10

URMATOARE = 4                # randuri „Urmeaza” din skin
ASTEPTARE_DATE_S = 6         # dupa atatea secunde fara program si fara text radio, barele iau locul lor
ANUNT_MS = 2500              # cat sta numele alegerii facute cu GALBEN / ALBASTRU peste bare
SALVARE_MS = 8000            # fisierul setarilor se scrie la atatea ms dupa ultima apasare GALBEN / ALBASTRU

_LEGATURA = [None]


def legatura():
	"""Legatura ecranului radio cu bara (una singura), sau None."""
	return _LEGATURA[0]


def _jurnal(text):
	print("[HdsRadio] %s" % text)


def drum_ardere(pas, px=DRUM_PX):
	"""(dx, dy) intre 0 si px pentru pasul `pas`: un drum inchis, lin, care trece prin toata zona."""
	dx = int(round(px / 2.0 + px / 2.0 * math.sin(2 * math.pi * pas / 17.0)))
	dy = int(round(px / 2.0 + px / 2.0 * math.sin(2 * math.pi * pas / 13.0 + 1.0)))
	return (max(0, min(px, dx)), max(0, min(px, dy)))


def drum_odihna(pas, latime, inaltime, bloc_l, bloc_i, margine=64):
	"""Coltul blocului de odihna pentru pasul `pas`: se plimba incet pe tot ecranul, fara sa iasa din el."""
	lx = max(0, latime - 2 * margine - bloc_l)
	ly = max(0, inaltime - 2 * margine - bloc_i)
	x = margine + int(lx * (0.5 + 0.5 * math.sin(2 * math.pi * pas / 23.0)))
	y = margine + int(ly * (0.5 + 0.5 * math.sin(2 * math.pi * pas / 17.0 + 0.7)))
	return (x, y)


def potriveste(eticheta, text):
	"""Textul intreg pe eticheta de un rand: cand nu incape, deruleaza (lib/gui/elabel.h). Se pune numai cand se
	schimba, ca derularea sa nu o ia de la capat la fiecare improspatare."""
	text = text or u""
	if getattr(eticheta, "_hds_text", None) == text:
		return
	eticheta._hds_text = text
	eticheta.setText(text)


# ---------------------------------------------------------------- skinurile de rezerva (1920x1080, scalate)

SKIN_ECRAN = """
<screen name="HdsEcranRadio" position="0,0" size="1936,1096" backgroundColor="#000A0F1A" flags="wfNoBorder" zPosition="-3">
	<widget source="session.CurrentService" render="Picon" position="112,72" size="220,132" alphatest="blend" zPosition="1">
		<convert type="ServiceName">Reference</convert>
	</widget>
	<widget name="nume" position="360,68" size="1180,80" font="Regular;58" foregroundColor="#00F2F4F8" backgroundColor="#000A0F1A" transparent="1" noWrap="1" valign="center" />
	<widget name="detalii" position="360,152" size="1180,44" font="Regular;30" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" noWrap="1" valign="center" />
	<widget source="global.CurrentTime" render="Label" position="1560,68" size="280,80" font="Regular;62" foregroundColor="#00F2F4F8" backgroundColor="#000A0F1A" transparent="1" halign="right" valign="center">
		<convert type="ClockToText">Format:%H:%M</convert>
	</widget>
	<widget name="data" position="1380,152" size="460,44" font="Regular;28" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" halign="right" valign="center" noWrap="1" />
	<eLabel position="112,224" size="1728,2" backgroundColor="#00232C40" />
	<widget name="acumEticheta" position="112,248" size="180,48" font="Regular;30" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="acumOra" position="296,248" size="110,48" font="Regular;32" foregroundColor="#00F5B83D" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="acumTitlu" position="412,248" size="940,48" font="Regular;36" foregroundColor="#00F2F4F8" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget source="progres" render="Progress" position="1368,266" size="200,12" foregroundColor="#009FB4FF" backgroundColor="#00232C40" borderWidth="0" />
	<widget name="ramas" position="1584,248" size="256,48" font="Regular;26" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" halign="right" valign="center" noWrap="1" />
	<widget name="urmeazaEticheta" position="112,306" size="180,40" font="Regular;28" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="urmeazaOra1" position="296,306" size="110,40" font="Regular;28" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="urmeazaTitlu1" position="412,306" size="1428,40" font="Regular;28" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="urmeazaOra2" position="296,348" size="110,40" font="Regular;28" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="urmeazaTitlu2" position="412,348" size="1428,40" font="Regular;28" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="urmeazaOra3" position="296,390" size="110,40" font="Regular;28" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="urmeazaTitlu3" position="412,390" size="1428,40" font="Regular;28" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="urmeazaOra4" position="296,432" size="110,40" font="Regular;28" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="urmeazaTitlu4" position="412,432" size="1428,40" font="Regular;28" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="epgLipsa" position="112,248" size="1728,48" font="Regular;28" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="linieMijloc" position="112,488" size="1728,1" backgroundColor="#00232C40" />
	<widget name="piesaEticheta" position="112,506" size="180,48" font="Regular;30" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="piesa" position="296,506" size="1544,96" font="Regular;38" foregroundColor="#00F5B83D" backgroundColor="#000A0F1A" transparent="1" valign="top" />
	<widget name="radiotext" position="296,556" size="1544,80" font="Regular;30" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="top" />
	<widget source="bare" render="Canvas" position="112,628" size="1728,236" />
	<widget name="zonaBareMari" position="112,316" size="1728,548" backgroundColor="#000A0F1A" transparent="1" zPosition="0" />
	<widget name="mesajBare" position="112,724" size="1728,44" font="Regular;30" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" halign="center" valign="center" noWrap="1" zPosition="2" />
	<widget name="anunt" position="112,714" size="1728,64" font="Regular;34" foregroundColor="#00F2F4F8" backgroundColor="#00232C40" halign="center" valign="center" noWrap="1" zPosition="4" />
	<widget name="tastaGalbena" position="112,881" size="26,26" backgroundColor="#00E8C53A" zPosition="1" />
	<widget name="tastaGalbenaText" position="148,874" size="400,40" font="Regular;26" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="tastaAlbastra" position="560,881" size="26,26" backgroundColor="#003A7BD5" zPosition="1" />
	<widget name="tastaAlbastraText" position="596,874" size="400,40" font="Regular;26" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="tastaVerde" position="1008,881" size="26,26" backgroundColor="#0022A84A" zPosition="1" />
	<widget name="tastaVerdeText" position="1044,874" size="400,40" font="Regular;26" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="tastaOk" position="1008,874" size="832,40" font="Regular;26" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<eLabel position="112,928" size="1728,1" backgroundColor="#00232C40" />
	<widget name="sunet" position="112,944" size="1000,44" font="Regular;29" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="transponder" position="1126,944" size="714,44" font="Regular;29" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" halign="right" valign="center" noWrap="1" />
	<widget name="semnalEticheta" position="112,994" size="126,40" font="Regular;24" foregroundColor="#009FB4FF" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget source="semnalBara" render="Progress" position="242,1008" size="150,12" foregroundColor="#009FB4FF" backgroundColor="#00232C40" borderWidth="0" />
	<widget name="semnalValoare" position="400,992" size="84,44" font="Regular;29" foregroundColor="#00F2F4F8" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="calitateEticheta" position="496,994" size="160,40" font="Regular;24" foregroundColor="#002FB84F" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget source="calitateBara" render="Progress" position="660,1008" size="150,12" foregroundColor="#002FB84F" backgroundColor="#00232C40" borderWidth="0" />
	<widget name="calitateValoare" position="818,992" size="84,44" font="Regular;29" foregroundColor="#00F2F4F8" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="semnal" position="918,992" size="922,44" font="Regular;29" foregroundColor="#00C9D2E3" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="semnalSlab" position="918,992" size="922,44" font="Regular;29" foregroundColor="#00FF6B5E" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget name="satelit" position="1380,992" size="460,44" font="Regular;29" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" halign="right" valign="center" noWrap="1" />
</screen>"""

SKIN_ODIHNA = """
<screen name="HdsEcranRadioOdihna" position="0,0" size="1920,1080" backgroundColor="#000A0F1A" flags="wfNoBorder" zPosition="-3">
	<widget name="odihnaNume" position="0,0" size="720,64" font="Regular;46" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" valign="center" noWrap="1" />
	<widget source="global.CurrentTime" render="Label" position="740,0" size="220,64" font="Regular;46" foregroundColor="#00AEB9CC" backgroundColor="#000A0F1A" transparent="1" halign="right" valign="center">
		<convert type="ClockToText">Format:%H:%M</convert>
	</widget>
	<widget name="odihnaPiesa" position="0,72" size="960,88" font="Regular;32" foregroundColor="#008C96A8" backgroundColor="#000A0F1A" transparent="1" valign="top" />
	<widget source="bareMici" render="Canvas" position="0,176" size="480,80" />
</screen>"""

SKIN_SETARI = """
<screen name="HdsEcranRadioSetari" position="center,center" size="1240,860" title="Ecranul radio" backgroundColor="#0010162A">
	<widget name="config" position="32,24" size="1176,540" itemHeight="60" font="Regular;32" secondfont="Regular;30" scrollbarMode="showOnDemand" />
	<eLabel position="32,580" size="1176,1" backgroundColor="#00AEB9CC" />
	<widget name="descriere" position="32,596" size="1176,160" font="Regular;28" foregroundColor="#00C9D2E3" backgroundColor="#0010162A" transparent="1" />
	<widget source="key_red" render="Label" position="32,780" size="360,56" font="Regular;28" halign="center" valign="center" backgroundColor="#009F1313" foregroundColor="#00FFFFFF" />
	<widget source="key_green" render="Label" position="408,780" size="360,56" font="Regular;28" halign="center" valign="center" backgroundColor="#001F771F" foregroundColor="#00FFFFFF" />
</screen>"""


def _skin(sablon):
	return scaledSkin(sablon, 1920)


def _latime_ecran():
	try:
		m = getDesktop(0).size()
		return m.width(), m.height()
	except Exception:
		return 1920, 1080


# ---------------------------------------------------------------- ferestrele


def _instanta_canvas(ecran, sursa):
	"""Renderer-ul Canvas legat de `sursa` (marimea panzei vine din skin)."""
	for r in ecran.renderer:
		if getattr(r, "source", None) is sursa and getattr(r, "instance", None) is not None:
			return r
	return None


def _fontSkin(eticheta):
	"""(fata, marime) a fontului dat etichetei de skin („HdsBold;38” -> („HdsBold”, 38)), sau None."""
	for atribut in getattr(eticheta, "skinAttributes", None) or ():
		try:
			nume, valoare = atribut[0], atribut[1]
		except (TypeError, IndexError):
			continue
		if nume == "font":
			try:
				fata, marime = valoare.split(";")
				return fata.strip(), int(marime)
			except ValueError:
				return None
	return None


def _font(fata, marime):
	"""Fontul `fata` la `marime`, prin skin.parseFont (stie si numele scurte ale skinului, de ex. „Regular”)."""
	try:
		from skin import parseFont
		return parseFont("%s;%d" % (fata, marime), ((1, 1), (1, 1)))
	except Exception:
		return gFont(fata, marime)


def _geometrie(inst):
	"""(x, y, latime, inaltime) a unei instante de widget, sau None."""
	try:
		p = inst.position()
		m = inst.size()
		return (p.x(), p.y(), m.width(), m.height())
	except Exception:
		return None


def _masoara_randuri(eticheta, randuri):
	"""Inaltimea a `randuri` randuri de text cu fontul de acum al etichetei, masurata pe „Ag” („A” are inaltimea
	majusculelor, „g” coada de jos: aceeasi pentru orice text), sau None. Textul etichetei ramane cel de dinainte."""
	inst = getattr(eticheta, "instance", None)
	masoara = getattr(inst, "calculateSize", None)
	if masoara is None:
		return None
	vechi = eticheta.getText()
	try:
		eticheta.setText(u"Ag")
		h1 = masoara().height()
		h = h1
		if randuri > 1:
			eticheta.setText(u"\n".join([u"Ag"] * randuri))
			h = masoara().height()
			if h < h1 * randuri * 0.9:       # un desen care nu trece la rand dupa „\n”: randuri x un rand
				h = h1 * randuri
	except Exception:
		h = None
	eticheta.setText(vechi)
	return h if h and h > 0 else None


def _inaltime_rand(ecran, nume):
	"""Inaltimea unui rand de text pe eticheta `nume` a ferestrei, cu fontul din skin (masurata o data), sau None."""
	h = ecran.inaltime_rand.get(nume)
	if h:
		return h
	h = _masoara_randuri(ecran[nume], 1)
	if h:
		ecran.inaltime_rand[nume] = h
	return h


def randuri_text(ecran, nume, text):
	"""Textul intreg pe eticheta `nume` a ferestrei (fara noWrap): 1 sau 2 randuri; daca nici doua nu ajung, scrisul se
	micsoreaza (fontul din skin, cu 15% la fiecare pas, de cel mult 3 ori) pana incape. Niciodata taiat.
	In ecran.inaltime_text ramane inaltimea randurilor lui, masurata pe „Ag” cu fontul de acum (nu pe literele textului:
	parantezele si cozile ar muta textul de sub el cu cativa pixeli). -> numarul de randuri (1 sau 2)."""
	e = ecran[nume]
	text = text or u""
	if getattr(e, "_hds_text", None) == text:
		return ecran.randuri_rds.get(nume, 1)
	e._hds_text = text
	inst = getattr(e, "instance", None)
	font = _fontSkin(e)
	h1 = _inaltime_rand(ecran, nume)
	if nume in ecran.font_mic and font is not None:
		# textul de dinainte micsorase scrisul: fontul din skin inapoi
		try:
			inst.setFont(_font(font[0], font[1]))
		except Exception:
			pass
		del ecran.font_mic[nume]
	e.setText(text)
	masoara = getattr(inst, "calculateSize", None)
	if not text or masoara is None or not h1:
		ecran.randuri_rds[nume] = 1
		ecran.inaltime_text.pop(nume, None)
		return 1
	randuri = 1
	inaltime_rand = h1
	for pas in range(4):
		try:
			h = masoara().height()
		except Exception:
			break
		randuri = max(1, int(round(float(h) / inaltime_rand)))
		if randuri <= 2 or font is None or pas == 3:
			break
		marime = int(font[1] * (0.85 ** (pas + 1)))
		try:
			inst.setFont(_font(font[0], marime))
		except Exception:
			break
		ecran.font_mic[nume] = marime
		inaltime_rand = max(1, int(h1 * (0.85 ** (pas + 1))))
	randuri = min(randuri, 2)
	ecran.randuri_rds[nume] = randuri
	h = _masoara_randuri(e, randuri)
	if h:
		ecran.inaltime_text[nume] = h
	else:
		ecran.inaltime_text.pop(nume, None)
	return randuri


class HdsEcranRadio(Screen):
	"""Fereastra e cu MARGINE px mai mare decat ecranul in fiecare directie (skinul: 1936x1096 la 1920x1080, continutul
	cu 16 px mai jos si mai la dreapta); se pune la (-margine + dx, -margine + dy), cu dx, dy intre 0 si margine, deci
	mutarea impotriva arderii nu lasa niciodata o banda neacoperita. Un skin fara margine (1920x1080) se muta ca
	inainte, de la (0, 0).

	Asezarea stransa: cand postul nu transmite nici programul, nici text radio, panoul barelor ia locul din zona
	„zonaBareMari” a skinului (mai sus si mai inalt); linia din mijloc se ascunde, mesajele barelor se muta in mijlocul
	panoului. Panza se face din nou la marimea noua (eCanvas.setSize da un pixmap nou) si se goleste pe loc."""
	ALLOW_SUSPEND = True

	ETICHETE = ("nume", "detalii", "data", "acumEticheta", "acumOra", "acumTitlu", "ramas", "urmeazaEticheta",
		"urmeazaOra1", "urmeazaOra2", "urmeazaOra3", "urmeazaOra4",
		"urmeazaTitlu1", "urmeazaTitlu2", "urmeazaTitlu3", "urmeazaTitlu4", "epgLipsa", "linieMijloc",
		"piesaEticheta", "piesa", "radiotext", "mesajBare", "zonaBareMari", "anunt",
		"tastaGalbena", "tastaGalbenaText", "tastaAlbastra", "tastaAlbastraText", "tastaVerde", "tastaVerdeText",
		"tastaOk",
		"sunet", "transponder", "semnalEticheta", "semnalValoare", "calitateEticheta", "calitateValoare",
		"semnal", "semnalSlab", "satelit")
	# randul semnalului: urca impreuna in locul randului sunetului cand acela e gol (etichete si barele lor)
	GRUP_SEMNAL = ("semnalEticheta", "semnalValoare", "calitateEticheta", "calitateValoare", "semnal", "semnalSlab")
	SURSE_SEMNAL = ("semnalBara", "calitateBara")
	# distanta dintre textele RDS si panoul barelor, cand textele coboara barele; intre piesa si textul radio (cat
	# spatiul dintre doua randuri ale piesei, ca textul radio sa nu para al treilea rand al ei)
	SPATIU_BARE = 16
	SPATIU_TEXTE = 20
	# randul semnalului: intre text si satelit
	SPATIU_SATELIT = 32
	# anuntul GALBEN / ALBASTRU: caseta cat textul plus atat in fiecare parte (cel mult cat panoul barelor)
	MARGINE_ANUNT = 32
	# cele doua grupuri ale randului semnalului: cuvantul, bara (sursa Progress) si procentul
	GRUPURI_SEMNAL = (("semnalEticheta", "semnalBara", "semnalValoare"), ("calitateEticheta", "calitateBara",
		"calitateValoare"))

	def __init__(self, session, leg):
		Screen.__init__(self, session)
		self.skinName = ["HdsEcranRadio"]
		self.skin = _skin(SKIN_ECRAN)
		self.leg = leg
		for nume in self.ETICHETE:
			self[nume] = Label(u"")
		self["acumEticheta"].setText(_("Acum"))
		self["urmeazaEticheta"].setText(_("Urmează"))
		self["piesaEticheta"].setText(_("Piesa"))
		self["tastaGalbenaText"].setText(_("Altă vizualizare"))
		self["tastaAlbastraText"].setText(_("Alte culori"))
		self["tastaVerdeText"].setText(_("Egalizator"))
		self["tastaOk"].setText(_("OK: lista posturilor.   OK ținut apăsat: opțiunile."))
		eticheta_semnal, eticheta_calitate = RD.etichete_semnal()
		self["semnalEticheta"].setText(eticheta_semnal)
		self["calitateEticheta"].setText(eticheta_calitate)
		self["progres"] = Progress(0)
		self["semnalBara"] = Progress(0)
		self["calitateBara"] = Progress(0)
		self["bare"] = CanvasSource()
		self.__urmaritor = ServiceEventTracker(screen=self, eventmap={
			iPlayableService.evStart: leg.laStart,
			iPlayableService.evEnd: leg.laSfarsit,
			iPlayableService.evUpdatedInfo: leg.laInfo,
			iPlayableService.evUpdatedEventInfo: leg.laEpg,
			iPlayableService.evUpdatedRadioText: leg.laRds,
			iPlayableService.evUpdatedRtpText: leg.laRds,
			iPlayableService.evUpdatedRassInteractivePicMask: leg.laRds,
			iPlayableService.evTunedIn: leg.laInfo,
			iPlayableService.evTuneFailed: leg.laInfo,
		})
		self.panza = None
		self.margine = (0, 0)
		self.geom = {}               # geometria de la asezare: (x, y, l, i) pe nume
		self.stransa = False         # asezarea stransa (fara program si fara text radio)
		self.fara_sigla = False
		self.bare_sus = None         # marginea de sus a panoului barelor in asezarea obisnuita (coboara sub textele RDS)
		self.randuri_rds = {}        # cate randuri ocupa acum piesa si textul radio
		self.inaltime_rand = {}      # inaltimea unui rand de text pe eticheta, cu fontul din skin (masurata o data)
		self.font_mic = {}           # etichetele cu scrisul micsorat pentru textul de acum: marimea folosita
		self.inaltime_text = {}      # inaltimea randurilor textului de acum pe piesa si pe textul radio
		self.urcare_rds = 0          # cat urca textele RDS cand postul da mai putine emisiuni urmatoare
		self._dy_semnal = 0          # randul semnalului urcat in locul randului sunetului (randuriJos)
		self._dy_satelit = 0
		self._rand_semnal = None     # asezarea randului semnalului facuta ultima data (nu se reface fara schimbare)
		self._latime_satelit = (None, 0)
		self.taste_viz = True        # randul tastelor arata GALBEN / ALBASTRU
		self.onLayoutFinish.append(self._asezat)

	def _asezat(self):
		for nume in ("nume", "detalii", "mesajBare", "zonaBareMari", "sunet", "transponder", "satelit", "piesaEticheta",
				"piesa", "radiotext", "anunt", "linieMijloc", "urmeazaOra1", "urmeazaOra2", "tastaGalbena",
				"tastaOk") + self.GRUP_SEMNAL:
			g = _geometrie(getattr(self[nume], "instance", None))
			if g is not None:
				self.geom[nume] = g
		for nume in self.SURSE_SEMNAL:
			r = _instanta_canvas(self, self[nume])
			g = _geometrie(r.instance) if r is not None else None
			if g is not None:
				self.geom[nume] = g
		r = _instanta_canvas(self, self["bare"])
		if r is not None:
			g = _geometrie(r.instance)
			if g is not None:
				self.geom["bare"] = g
				self.bare_sus = g[1]
			m = r.instance.size()
			self.panza = DES.Panza(m.width(), m.height())
			# pixmap-ul nou al panzei e negru: o umplere cu fundalul ferestrei, o singura data
			DES.aplica(self["bare"], self.panza.goleste())
		for nume in ("mesajBare", "semnalSlab", "zonaBareMari", "anunt"):
			self[nume].hide()
		self._aseazaTaste()
		lat, inalt = _latime_ecran()
		try:
			m = self.instance.size()
			self.margine = (max(0, m.width() - lat), max(0, m.height() - inalt))
		except Exception:
			self.margine = (0, 0)
		self.muta(0)

	def muta(self, pas):
		"""Mutarea impotriva arderii, pasul `pas` al drumului (Screens/HdsEcranRadio.drum_ardere)."""
		mx, my = self.margine
		px = min(mx, my, DRUM_PX) if mx and my else DRUM_PX
		dx, dy = drum_ardere(pas, px)
		if mx and my:
			x, y = dx - mx, dy - my
		else:
			x, y = dx, dy
		try:
			self.instance.move(ePoint(x, y))
		except Exception:
			pass

	def _dreptunghiBare(self, strans):
		"""(x, y, l, i) al panoului barelor: zona mare in asezarea stransa; altfel locul din skin, cu marginea de sus
		coborata sub textele RDS cand acestea au doua randuri (marginea de jos ramane)."""
		if strans:
			return self.geom["zonaBareMari"]
		x, y, l, i = self.geom["bare"]
		sus = max(y, self.bare_sus if self.bare_sus is not None else y)
		sus = min(sus, y + i - 80)          # panoul nu scade sub 80 px
		return (x, sus, l, y + i - sus)

	def _aseazaBare(self, strans):
		"""Muta si reface panza barelor dupa asezare. -> True daca s-a schimbat (panza e noua)."""
		r = _instanta_canvas(self, self["bare"])
		if r is None:
			return False
		x, y, l, i = self._dreptunghiBare(strans)
		inst = r.instance
		try:
			p = inst.position()
			m = inst.size()
			if (p.x(), p.y(), m.width(), m.height()) == (x, y, l, i) and strans == self.stransa:
				return False
			inst.move(ePoint(x, y))
			inst.resize(eSize(l, i))
			inst.setSize(eSize(l, i))
		except Exception as e:
			_jurnal("asezarea barelor: %s" % e)
			return False
		self.stransa = strans
		self.panza = DES.Panza(l, i, fel=self.panza.fel if self.panza else "varfuri",
			culori=self.panza.culori if self.panza else None)
		DES.aplica(self["bare"], self.panza.goleste())
		# mesajele barelor si numele alegerii (GALBEN / ALBASTRU) stau in mijlocul panoului
		bx, by, bl, bi = self.geom["bare"]
		dy = (y + i // 2) - (by + bi // 2)
		for nume in ("mesajBare", "anunt"):
			g = self.geom.get(nume)
			if g is not None:
				try:
					p = self[nume].instance.position()
					# anuntul isi pastreaza locul pe orizontala (e centrat dupa latimea textului, anunta)
					self[nume].instance.move(ePoint(p.x() if nume == "anunt" else g[0], g[1] + dy))
				except Exception:
					pass
		self["linieMijloc"].setVisible(not strans)
		return True

	def aseazaStrans(self, strans):
		"""Asezarea stransa sau cea obisnuita a panoului barelor. -> True daca s-a schimbat (panza e noua)."""
		strans = bool(strans) and "zonaBareMari" in self.geom and "bare" in self.geom
		if strans == self.stransa:
			return False
		return self._aseazaBare(strans)

	def _inaltimeRand(self, nume):
		return _inaltime_rand(self, nume)

	def randuriText(self, nume, text):
		return randuri_text(self, nume, text)

	def pasUrmatoare(self):
		"""Distanta dintre doua randuri „Urmeaza” din skin (42 px la HDSatelit), sau 0."""
		g1 = self.geom.get("urmeazaOra1")
		g2 = self.geom.get("urmeazaOra2")
		return max(0, g2[1] - g1[1]) if g1 is not None and g2 is not None else 0

	def aseazaRds(self, piesa_vazuta, text_vazut, urcare=0):
		"""Textul radio sta sub piesa (sub cate randuri are ea; in locul ei cand nu e piesa), iar panoul barelor coboara
		sub textele RDS cand ele trec de locul din skin. `urcare`: cu cati pixeli urca linia din mijloc, piesa si textul
		radio cand postul da mai putine emisiuni urmatoare decat randurile skinului (panoul barelor ramane in locul
		lui, deci nu se mai strange degeaba)."""
		gp = self.geom.get("piesa")
		gt = self.geom.get("radiotext")
		if gp is None or gt is None:
			return
		urcare = max(0, int(urcare))
		self.urcare_rds = urcare
		for nume in ("linieMijloc", "piesaEticheta", "piesa"):
			g = self.geom.get(nume)
			if g is not None:
				try:
					inst = self[nume].instance
					if inst.position().y() != g[1] - urcare:
						inst.move(ePoint(g[0], g[1] - urcare))
				except Exception:
					pass
		y_piesa = gp[1] - urcare
		h_p = self._inaltimeRand("piesa") or (gp[3] // 2)
		h_t = self._inaltimeRand("radiotext") or (gt[3] // 2)
		jos_piesa = y_piesa + (self.inaltime_text.get("piesa") or self.randuri_rds.get("piesa", 1) * h_p if piesa_vazuta else 0)
		y_text = max(y_piesa, jos_piesa + (self.SPATIU_TEXTE if piesa_vazuta else 0))
		try:
			if self["radiotext"].instance.position().y() != y_text:
				self["radiotext"].instance.move(ePoint(gt[0], y_text))
		except Exception:
			pass
		jos = jos_piesa
		if text_vazut:
			jos = y_text + (self.inaltime_text.get("radiotext") or self.randuri_rds.get("radiotext", 1) * h_t)
		sus = max(self.geom["bare"][1], jos + self.SPATIU_BARE) if "bare" in self.geom else None
		if sus != self.bare_sus:
			self.bare_sus = sus
			if not self.stransa:
				self._aseazaBare(False)

	def randuriJos(self, sunet_gol, transponder_gol):
		"""Randurile de jos: cand randul de sus al unei coloane e gol (sunetul, transponderul), randul de sub el urca in
		locul lui, ca sa nu ramana un gol deasupra lui. Randul semnalului (etichetele, barele, valorile, textul) e mai lat
		decat coloana sunetului si trece sub transponder, deci urca intreg numai cand si transponderul lipseste. Dupa
		asta se aseaza randul semnalului pe orizontala (_aseazaRandSemnal)."""
		g_sunet = self.geom.get("sunet")
		g_transp = self.geom.get("transponder")
		g_satelit = self.geom.get("satelit")
		dy_semnal = 0
		if sunet_gol and transponder_gol and g_sunet is not None and "semnal" in self.geom:
			dy_semnal = g_sunet[1] - self.geom["semnal"][1]
		dy_satelit = 0
		if transponder_gol and g_transp is not None and g_satelit is not None:
			dy_satelit = g_transp[1] - g_satelit[1]
		self._dy_semnal = dy_semnal
		self._dy_satelit = dy_satelit
		inst = getattr(self["satelit"], "instance", None)
		if inst is not None and g_satelit is not None:
			try:
				if inst.position().y() != g_satelit[1] + dy_satelit:
					inst.move(ePoint(g_satelit[0], g_satelit[1] + dy_satelit))
			except Exception:
				pass
		self._aseazaRandSemnal()

	def _instantaSemnal(self, nume):
		"""Instanta unui element al randului semnalului (eticheta sau bara Progress), sau None."""
		if nume in self.SURSE_SEMNAL:
			r = _instanta_canvas(self, self[nume])
			return r.instance if r is not None else None
		return getattr(self[nume], "instance", None)

	def _latimeSatelit(self):
		"""Latimea textului satelitului (masurata numai cand textul se schimba), 0 fara text."""
		text = self["satelit"].getText()
		if self._latime_satelit[0] == text:
			return self._latime_satelit[1]
		lat = 0
		inst = getattr(self["satelit"], "instance", None)
		masoara = getattr(inst, "calculateSize", None)
		if text and masoara is not None:
			try:
				lat = min(inst.size().width(), masoara().width())
			except Exception:
				lat = 0
		self._latime_satelit = (text, lat)
		return lat

	def _aseazaRandSemnal(self):
		"""Randul semnalului pe orizontala: grupurile SEMNAL / CALITATE care au valoare, in locurile lor din skin, fiecare
		mutat la stanga cu locul grupurilor ascunse dinaintea lui (un grup fara valoare nu lasa gol), apoi textul („DVB-S2
		8PSK, 13,1 dB, liber”) pe tot locul pana la textul satelitului (cand satelitul e pe acelasi rand). Se reface
		numai cand ceva din toate astea s-a schimbat."""
		g_text = self.geom.get("semnal")
		g0 = self.geom.get(self.GRUPURI_SEMNAL[0][0])
		if g_text is None or g0 is None:
			return
		putere, calitate = getattr(self, "_semnal_aratat", None) or (None, None)
		cheie = (putere is None, calitate is None, self._dy_semnal, self._dy_satelit, self._latimeSatelit())
		if cheie == self._rand_semnal:
			return
		self._rand_semnal = cheie
		dy = self._dy_semnal
		grupuri = [g for g in self.GRUPURI_SEMNAL if g[0] in self.geom]
		# unde incepe fiecare grup in skin si unde incepe textul: locul unui grup e pana la inceputul urmatorului
		starturi = [self.geom[g[0]][0] for g in grupuri] + [g_text[0]]
		valori = dict(zip((g[0] for g in self.GRUPURI_SEMNAL), (putere, calitate)))
		ascuns = 0
		for k, grup in enumerate(grupuri):
			valoare = valori.get(grup[0])
			# un grup fara valoare ramane ascuns (arataSemnal), in locul lui din skin, pe randul de acum
			dx = -ascuns if valoare is not None else 0
			for nume in grup:
				inst = self._instantaSemnal(nume)
				g = self.geom.get(nume)
				if inst is None or g is None:
					continue
				try:
					p = inst.position()
					if (p.x(), p.y()) != (g[0] + dx, g[1] + dy):
						inst.move(ePoint(g[0] + dx, g[1] + dy))
				except Exception:
					pass
			if valoare is None:
				ascuns += starturi[k + 1] - starturi[k]
		x = g_text[0] - ascuns
		# textul: de la x pana la satelit (pe acelasi rand) sau pana la marginea randului
		g_sat = self.geom.get("satelit")
		dreapta = g_text[0] + g_text[2]
		if g_sat is not None:
			dreapta = g_sat[0] + g_sat[2]
			lat_sat = self._latimeSatelit()
			if lat_sat and g_sat[1] + self._dy_satelit == g_text[1] + dy:
				dreapta -= lat_sat + self.SPATIU_SATELIT
		latime = max(120, dreapta - x)
		for nume in ("semnal", "semnalSlab"):
			inst = getattr(self[nume], "instance", None)
			if inst is None:
				continue
			try:
				p = inst.position()
				m = inst.size()
				if (p.x(), p.y()) != (x, g_text[1] + dy):
					inst.move(ePoint(x, g_text[1] + dy))
				if m.width() != latime:
					inst.resize(eSize(latime, g_text[3]))
					self[nume]._hds_text = None      # potriveste() pune textul din nou, pe latimea noua
			except Exception:
				pass

	def arataSemnal(self, putere, calitate):
		"""Barele SEMNAL si CALITATE cu procentele lor; o valoare pe care tunerul nu o da isi ascunde bara, procentul si
		cuvantul (altfel „SEMNAL” ar ramane singur pe rand). Se cheama la fiecare secunda: cand valorile nu s-au
		schimbat nu se redeseneaza nimic; locurile le pune _aseazaRandSemnal."""
		if getattr(self, "_semnal_aratat", None) == (putere, calitate):
			return
		self._semnal_aratat = (putere, calitate)
		for (eticheta, sursa, procent), valoare in zip(
				(("semnalEticheta", "semnalBara", "semnalValoare"), ("calitateEticheta", "calitateBara", "calitateValoare")),
				(putere, calitate)):
			# cuvantul si procentul prin eticheta (starea ei „visible” ramane adevarata), bara prin instanta ei
			bara = self._instantaSemnal(sursa)
			if valoare is None:
				self[procent].setText(u"")
				self[eticheta].hide()
				self[procent].hide()
				if bara is not None:
					bara.hide()
				continue
			self[sursa].value = valoare
			self[procent].setText(u"%d%%" % valoare)
			self[eticheta].show()
			self[procent].show()
			if bara is not None:
				bara.show()
		self._aseazaRandSemnal()

	def _aseazaTaste(self, ordine=None, x=None):
		"""Randul tastelor de sub bare: patratul galben si textul lui, patratul albastru si textul lui, patratul verde
		(egalizatorul) si textul lui, apoi OK; fiecare pus dupa latimea textului dinainte (textele au lungimi diferite
		in fiecare limba). Cu `ordine` si `x`: numai acele elemente, de la x (randul fara galben si albastru)."""
		if ordine is None:
			ordine = ("tastaGalbena", "tastaGalbenaText", "tastaAlbastra", "tastaAlbastraText", "tastaVerde",
				"tastaVerdeText", "tastaOk")
		inst = [getattr(self[n], "instance", None) for n in ordine]
		if any(i is None for i in inst):
			return
		try:
			if x is None:
				x = inst[0].position().x()
			for n, i in zip(ordine, inst):
				p = i.position()
				if p.x() != x:
					i.move(ePoint(x, p.y()))
				latime = i.size().width()
				masoara = getattr(i, "calculateSize", None)
				if n.endswith("Text") and masoara is not None and self[n].getText():
					latime = min(latime, masoara().width())
				x += latime + (10 if not n.endswith("Text") else 36)
		except Exception as e:
			_jurnal("randul tastelor: %s" % e)

	def arataTasteViz(self, da):
		"""Randul tastelor: GALBEN / ALBASTRU numai cand barele se pot arata (altfel ar schimba o vizualizare care nu se
		vede); fara ele randul incepe cu VERDE (egalizatorul nu depinde de bare), apoi OK, la stanga."""
		da = bool(da)
		if da == self.taste_viz:
			return
		self.taste_viz = da
		for nume in ("tastaGalbena", "tastaGalbenaText", "tastaAlbastra", "tastaAlbastraText"):
			self[nume].setVisible(da)
		if da:
			self._aseazaTaste()
			return
		g = self.geom.get("tastaGalbena")
		if g is not None:
			self._aseazaTaste(("tastaVerde", "tastaVerdeText", "tastaOk"), g[0])

	def anunta(self, text):
		"""Numele alegerii facute cu GALBEN / ALBASTRU, peste bare, cateva secunde (ascuns de LegaturaRadio). Caseta
		are latimea textului plus o margine, centrata pe panoul barelor; cel mult cat panoul (1728 px la HDSatelit), cu
		textul intreg (cand tot nu incape, deruleaza)."""
		e = self["anunt"]
		inst = getattr(e, "instance", None)
		g = self.geom.get("anunt")
		e._hds_text = None
		if inst is None or g is None:
			e.setText(text)
			e.show()
			return
		try:
			p = inst.position()
			inst.resize(eSize(g[2], g[3]))
			potriveste(e, text)
			latime = min(g[2], inst.calculateSize().width() + 2 * self.MARGINE_ANUNT)
			inst.move(ePoint(g[0] + (g[2] - latime) // 2, p.y()))
			inst.resize(eSize(latime, g[3]))
		except Exception:
			e.setText(text)
		e.show()

	def _sigla(self):
		"""Renderer-ul siglei postului (Renderer/Picon), daca skinul il are."""
		for r in self.renderer:
			if r.__class__.__name__ == "Picon" and getattr(r, "instance", None) is not None:
				return r
		return None

	def aseazaFaraSigla(self, fara):
		"""Fara sigla pentru post: caseta siglei se ascunde, iar numele si detaliile iau si locul ei (altfel ar ramane
		o caseta goala in coltul ecranului)."""
		r = self._sigla()
		g_sigla = _geometrie(r.instance) if r is not None else None
		fara = bool(fara) and "nume" in self.geom and g_sigla is not None
		if fara == self.fara_sigla:
			return
		self.fara_sigla = fara
		try:
			if fara:
				r.instance.hide()
			else:
				r.instance.show()
		except Exception:
			pass
		for nume in ("nume", "detalii"):
			g = self.geom.get(nume)
			if g is None:
				continue
			x, y, l, i = g
			if fara and g_sigla[0] < x:
				x, l = g_sigla[0], l + (x - g_sigla[0])
			try:
				self[nume].instance.move(ePoint(x, y))
				self[nume].instance.resize(eSize(l, i))
			except Exception:
				pass
			self[nume]._hds_text = None   # potriveste() pune textul din nou, pe latimea noua

	def arataProgres(self, da):
		"""Bara emisiunii de acum: ascunsa cand postul nu transmite programul (altfel s-ar vedea sina goala)."""
		r = _instanta_canvas(self, self["progres"])
		if r is not None:
			if da:
				r.instance.show()
			else:
				r.instance.hide()


class HdsEcranRadioOdihna(Screen):
	ALLOW_SUSPEND = True

	def __init__(self, session, leg):
		Screen.__init__(self, session)
		self.skinName = ["HdsEcranRadioOdihna"]
		self.skin = _skin(SKIN_ODIHNA)
		self.leg = leg
		self["odihnaNume"] = Label(u"")
		self["odihnaPiesa"] = Label(u"")
		self["bareMici"] = CanvasSource()
		self.panza = None
		self.locuri = []            # (instanta, x, y) de la asezare: blocul se muta cu aceeasi deplasare
		self.bloc = (0, 0)
		# piesa pe unul sau doua randuri intregi, ca pe ecranul radio (randuri_text)
		self.inaltime_rand = {}
		self.font_mic = {}
		self.randuri_rds = {}
		self.inaltime_text = {}
		self.onLayoutFinish.append(self._asezat)

	def randuriText(self, nume, text):
		return randuri_text(self, nume, text)

	def _asezat(self):
		self.locuri = []
		lat = inalt = 0
		for w in [self["odihnaNume"], self["odihnaPiesa"]] + list(self.renderer):
			inst = getattr(w, "instance", None)
			if inst is None:
				continue
			p = inst.position()
			m = inst.size()
			self.locuri.append((inst, p.x(), p.y()))
			lat = max(lat, p.x() + m.width())
			inalt = max(inalt, p.y() + m.height())
		self.bloc = (lat, inalt)
		r = _instanta_canvas(self, self["bareMici"])
		if r is not None:
			m = r.instance.size()
			self.panza = DES.Panza(m.width(), m.height(), fel="bare", fundal=DES.FUNDAL_ODIHNA)
			DES.aplica(self["bareMici"], self.panza.goleste())

	def muta(self, x, y):
		for inst, x0, y0 in self.locuri:
			inst.move(ePoint(x0 + x, y0 + y))


class HdsEcranRadioSetari(Screen, ConfigListScreen):
	"""Setarile ecranului radio (Meniu > Audio > Ecranul radio si OK tinut pe ecranul radio). Numai cu sagetile si OK:
	OK deschide lista alegerilor (sau schimba Da/Nu) si alegerea se vede pe loc pe ecranul radio si ramane (se tine
	minte in setari; fisierul setarilor se scrie o singura data, la iesire). EXIT si Verde inchid, Rosu pune la loc
	valorile de la deschidere.

	Randurile au doua elemente (eticheta, element): ConfigList.selectionChanged cheama onSelectionChanged numai pentru
	randuri de doua, deci numele setarii se afla din element (self._nume), nu dintr-un al treilea camp."""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["HdsEcranRadioSetari"]
		self.skin = _skin(SKIN_SETARI)
		self.setTitle(_("Ecranul radio"))
		self.setari = S.initConfig()
		ConfigListScreen.__init__(self, [], session=session)
		self["descriere"] = Label(u"")
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.ok,
			"cancel": self.salveaza,
			"red": self.anuleaza,
			"green": self.salveaza,
		}, -2)
		self._nume = {}
		self._initiale = {}
		lista = []
		for n in S.ORDINE:
			element = getattr(self.setari, n)
			self._nume[id(element)] = n
			self._initiale[n] = element.value
			lista.append(getConfigListEntry(_(S.ETICHETE[n]), element))
		self["config"].list = lista
		self["config"].l.setList(lista)
		self["config"].onSelectionChanged.append(self._descriere)
		self.onLayoutFinish.append(self._descriere)

	def _numeRand(self, rand):
		return self._nume.get(id(rand[1])) if rand else None

	def _descriere(self):
		n = self._numeRand(self["config"].getCurrent())
		self["descriere"].setText(_(S.DESCRIERI[n]) if n in S.DESCRIERI else u"")

	def ok(self):
		rand = self["config"].getCurrent()
		n = self._numeRand(rand)
		if n is None:
			return
		element = rand[1]
		if n in S.DA_NU:
			element.value = not element.value
			self._pune(element)
			return
		alegeri = [(descriere, valoare) for valoare, descriere in element.choices.choices]
		valori = [v for d, v in alegeri]
		from Screens.ChoiceBox import ChoiceBox
		self._element = element
		self.session.openWithCallback(self._ales, ChoiceBox, title=rand[0], list=alegeri,
			selection=valori.index(element.value) if element.value in valori else 0)

	def _ales(self, ales):
		element = getattr(self, "_element", None)
		self._element = None
		if ales is None or element is None:
			return
		element.value = ales[1]
		self._pune(element)

	def _pune(self, element):
		"""Alegerea ramane in setari (in memorie) si se vede pe loc pe ecranul radio."""
		element.save()
		self["config"].invalidateCurrent()
		self._aplica()

	def _aplica(self):
		leg = legatura()
		if leg is not None:
			leg.setariSchimbate()

	def salveaza(self):
		"""Iesirea: fisierul setarilor se scrie o data, numai daca s-a schimbat ceva."""
		schimbat = False
		for rand in self["config"].list:
			n = self._numeRand(rand)
			if n is not None and rand[1].value != self._initiale.get(n):
				schimbat = True
		if schimbat:
			configfile.save()
		self.close(schimbat)

	def anuleaza(self):
		for rand in self["config"].list:
			n = self._numeRand(rand)
			if n is not None and rand[1].value != self._initiale.get(n):
				rand[1].value = self._initiale[n]
				rand[1].save()
		self._aplica()
		self.close(False)

	def iesire(self):
		self.salveaza()


# ---------------------------------------------------------------- tastele (folosita de Screens/InfoBar.py)


class HartaRadio(ActionMap):
	"""Harta de taste a ecranului radio: actiunile pe care nu le are lasa tasta mai departe fara nimic in jurnal
	(ActionMap ar scrie „unknown action ... typo in keymap?” pentru fiecare tasta a contextelor comune)."""

	def action(self, context, action):
		if action not in self.actions:
			return 0
		return ActionMap.action(self, context, action)


# contextele hartii: cele ale barei (OK si EXIT, sagetile si listele), tastele colorate (GALBEN / ALBASTRU la apasare),
# extensiile barei (ALBASTRU la eliberare, oprit dupa o apasare a albastrului prinsa aici) si pistele audio (GALBEN la
# eliberare pe telecomanda Viper, oprit dupa o apasare a galbenului prinsa aici; actiunile tastei AUDIO nu sunt in harta)
CONTEXTE_TASTE = ["InfobarShowHideActions", "InfobarChannelSelection", "ColorActions", "InfobarExtensions",
	"InfobarAudioSelectionActions"]


def actiuniHarta(leg):
	"""Actiunile hartii ecranului radio (Screens/InfoBar.py le leaga cu prioritatea -1, inaintea hartilor barei)."""
	return {
		"toggleShow": leg.okBara,
		"hide": leg.iesire,
		"zapUp": leg.zapAnterior,
		"zapDown": leg.zapUrmator,
		"switchChannelUp": leg.listaSus,
		"switchChannelDown": leg.listaJos,
		"openServiceList": leg.listaRadio,
		"yellow": leg.tastaGalbena,
		"green": leg.tastaVerde,
		"blue": leg.tastaAlbastra,
		"extensions": leg.faraExtensii,
		"audioSelection": leg.faraPisteAudio,
	}
# OK si ENTER (linux/input.h) pentru ascultatorul global; steagurile eRCKey: 0 apasare, 1 eliberare
TASTE_OK = (352, 28)
STEAG_APASAT = 0
STEAG_ELIBERAT = 1
OK_LUNG_MS = 700


# ---------------------------------------------------------------- legatura cu bara


class LegaturaRadio(object):
	"""Face si tine ferestrele radio, urmareste serviciul, porneste si opreste analizorul, deseneaza cadrele si
	raspunde tastelor venite prin harta din InfoBar."""

	def __init__(self, infobar):
		self.infobar = infobar
		self.session = infobar.session
		S.initConfig()
		self.radio = False            # merge un post de radio (si ecranul e pornit din setari)
		self.ascuns_de_om = False     # EXIT: ascuns pana la urmatorul post sau pana la OK
		self.vizibil = False
		self.in_odihna = False
		self.ultima_tasta = time.time()
		self.tasta_legata = False
		self.analizor = None
		self.analiza_pid = None
		self.analiza_nevazuta_de = None
		self.cerere_web = 0.0
		self.fisier_proba = None      # emulatorul si probele: sunetul dintr-un fisier, nu din demultiplexor
		self.d = {}
		self.epg_la = 0.0
		self.pas_ardere = 0
		self.mutat_la = time.time()
		self.pas_odihna = 0
		self.odihna_la = 0.0
		self.fara_date_desenat = True
		self._ok_lung = False
		self._ok_armat = False
		self.fara_pid = False
		self._harta = None
		self.mesaj_aratat = False
		# asezarea stransa: postul de acum, cand a pornit, daca a trimis program sau text radio; ce s-a vazut la un post
		# se tine minte (in memorie), ca la urmatoarea pornire lui sa inceapa direct cu asezarea potrivita
		self.asezare_ref = None
		self.post_pornit_la = 0.0
		self.date_vazute = False
		self.asezari = {}
		self.sigle = {}
		self.ecran = self.session.instantiateDialog(HdsEcranRadio, self)
		self.odihna = self.session.instantiateDialog(HdsEcranRadioOdihna, self)
		self.tCadru = eTimer()
		self.tCadru.callback.append(self._cadru)
		self.tSecunda = eTimer()
		self.tSecunda.callback.append(self._secunda)
		self.tAnaliza = eTimer()
		self.tAnaliza.callback.append(self._pornesteAnaliza)
		self.tSfarsit = eTimer()
		self.tSfarsit.callback.append(self._dupaSfarsit)
		self.tOkLung = eTimer()
		self.tOkLung.callback.append(self._okTinut)
		self.tOkScurt = eTimer()
		self.tOkScurt.callback.append(self._okScurt)
		self.tAnunt = eTimer()
		self.tAnunt.callback.append(self._ascundeAnunt)
		self.tSalvare = eTimer()
		self.tSalvare.callback.append(self._salveazaSetari)
		self.albastru_apasat = False
		self.galben_apasat = False
		# eticheta nivelului: 30 pe 1920x1080, inmultita cu marimea ecranului si cu fontul HD Satelit sub un skin cu alta
		# rezolutie (skin.factorHds, skin.fontHds), apoi cu Marimea textului (Components/HdsMarireText: fontul e pus din
		# cod); cu HDSatelit pe 1920x1080 la 100 % ramane Regular 30
		try:
			import skin
			sf = skin.factorHds()[2]
		except Exception:
			sf = 1.0
		try:
			self.font_nivel = MT.fontCod("Regular", max(1, int(round(30 * sf))))
		except Exception:
			self.font_nivel = None
		# textul radio si piesa: numai dupa mesajele anuntate de decodorul RDS pentru serviciul care merge
		try:
			from Components import HdsRdsText
			HdsRdsText.urmareste(self.session.nav)
		except Exception as e:
			_jurnal("paza textului RDS: %s" % e)
		_LEGATURA[0] = self

	def legaHarta(self, harta):
		self._harta = harta
		self._harta.setEnabled(False)

	# ---- starea

	def pornit(self):
		return S.ecran_pornit()

	def _hartaActiva(self, da):
		if self._harta is not None:
			self._harta.setEnabled(bool(da))

	def _inFata(self):
		return self.session.current_dialog is self.infobar

	def _barPrincipala(self):
		"""Serviciul e al barei principale, nu al unui player (MoviePlayer e si el InfoBarBase). Lista radio separata
		(ChannelSelectionRadio) e tot InfoBarBase si sta in varful stivei cat e deschisa, dar porneste posturile pentru
		bara: o recunoaste atributul `infobar`, care e chiar bara."""
		stiva = ServiceEventTracker.InfoBarStack
		if not stiva:
			return True
		varf = stiva[-1]
		return varf is self.infobar or getattr(varf, "infobar", None) is self.infobar

	def refRadioCurenta(self):
		"""Textul referintei postului de radio care merge acum pe bara, sau None (canal TV, fisier, nimic)."""
		try:
			ref, ref_text = RD.ref_curenta(self.session)
			service = self.session.nav.getCurrentService()
		except Exception:
			return None
		if ref_text and RD.este_post_radio(service, ref_text):
			return ref_text
		return None

	def _inStandby(self):
		try:
			from Screens.Standby import inStandby
			return inStandby is not None
		except Exception:
			return False

	# ---- evenimentele serviciului
	# ServiceEventTracker cheama ascultatorii la rand, fara try: o exceptie de aici i-ar lasa fara eveniment pe cei
	# inregistrati dupa fereastra radio, deci fiecare eveniment se prinde si se scrie o linie in jurnal.

	def laStart(self):
		try:
			self._laStart()
		except Exception as e:
			_jurnal("evStart: %s: %s" % (type(e).__name__, e))

	def _laStart(self):
		self.tSfarsit.stop()
		ref, ref_text = RD.ref_curenta(self.session)
		try:
			service = self.session.nav.getCurrentService()
		except Exception:
			service = None
		radio = bool(ref_text) and self._barPrincipala() and RD.este_post_radio(service, ref_text)
		self._opresteAnaliza()
		self.radio = radio
		self.ascuns_de_om = False
		self.analiza_pid = None
		self.fara_pid = False
		if not radio:
			self.ascunde()
			self._hartaActiva(False)
			return
		self.d = {}
		self.epg_la = 0.0
		self.asezare_ref = ref_text
		self.post_pornit_la = time.time()
		self.date_vazute = False
		cunoscut = self.asezari.get(RD._cheie_ref(ref_text))
		if cunoscut is not None:
			self._aseaza(cunoscut)
		# PMT-ul vine cu evUpdatedInfo; daca nu vine (fisier, flux), analizorul porneste oricum dupa o vreme. Ceasul
		# porneste inaintea desenului: starea e „asteapta”, deci panoul barelor postului de dinainte se goleste acum.
		self.tAnaliza.start(PORNIRE_ANALIZA_MS * 3, True)
		# cu ecranul radio oprit din setari tastele raman ale barei, ca inainte
		self._hartaActiva(self.pornit())
		if self.pornit():
			self.arata()
			self.actualizeaza(tot=True)

	def dupaListaRadio(self):
		"""Lista radio separata s-a inchis (Screens/InfoBar.py, ChannelSelectionRadioClosed). Starea se reface numai
		cand nu se potriveste cu serviciul care merge; altfel analizorul ar porni din nou si barele ar clipi."""
		try:
			este = self.refRadioCurenta() is not None and self._barPrincipala()
			if este != self.radio:
				self._laStart()
			elif este and self.pornit() and not self.vizibil and not self.ascuns_de_om:
				self.arata()
				self.actualizeaza(tot=True)
		except Exception as e:
			_jurnal("lista radio inchisa: %s: %s" % (type(e).__name__, e))

	def laSfarsit(self):
		self._opresteAnaliza()
		self.tAnaliza.stop()
		self.tSfarsit.start(SFARSIT_MS, True)

	def _dupaSfarsit(self):
		# niciun post nou in SFARSIT_MS (serviciul oprit, standby): ecranul se ascunde
		try:
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
		except Exception:
			ref = None
		if ref is None:
			self.radio = False
			self.ascunde()
			self._hartaActiva(False)

	def laInfo(self):
		try:
			self._laInfo()
		except Exception as e:
			_jurnal("evUpdatedInfo: %s: %s" % (type(e).__name__, e))

	def _laInfo(self):
		if not self.radio:
			return
		self.actualizeaza(tot=True)
		try:
			pid = RD.pid_audio(self.session.nav.getCurrentService())
		except Exception:
			pid = -1
		if pid > 0 and pid != self.analiza_pid:
			self._opresteAnaliza()
			self.fara_pid = False
			self.tAnaliza.start(PORNIRE_ANALIZA_MS, True)

	def laEpg(self):
		try:
			if self.radio:
				self.epg_la = 0.0
				self.actualizeaza(tot=True)
		except Exception as e:
			_jurnal("evUpdatedEventInfo: %s: %s" % (type(e).__name__, e))

	def laRds(self):
		try:
			if self.radio and self.vizibil:
				self.actualizeaza(tot=False, rds=True)
		except Exception as e:
			_jurnal("RDS: %s: %s" % (type(e).__name__, e))

	# ---- aratare, ascundere, odihna

	def arata(self):
		if self._inStandby() or not self.pornit() or self.ascuns_de_om:
			return
		if not self.vizibil:
			self.vizibil = True
			self.in_odihna = False
			self.ultima_tasta = time.time()
			self.mutat_la = time.time()
			self.ecran.show()
			S.pune_vizibil(True)
			self._legaTasta(True)
			self._rdsBara(False)
		self.tSecunda.start(MS_SECUNDA)
		self._planificaCadru()

	def ascunde(self):
		self._ok_armat = False
		self.tOkLung.stop()
		self.tAnunt.stop()
		self.albastru_apasat = False
		self.galben_apasat = False
		try:
			self.ecran["anunt"].hide()
		except Exception:
			pass
		if self.vizibil or self.in_odihna:
			self.vizibil = False
			self.in_odihna = False
			self.ecran.hide()
			self.odihna.hide()
			S.pune_vizibil(False)
			self._legaTasta(False)
			self._rdsBara(True)
			if self.ecran.panza is not None:
				self.ecran.panza.curata = True
		self.tCadru.stop()
		if not self._webActiv():
			self.tSecunda.stop()
			self._opresteAnaliza()

	def _rdsBara(self, arata):
		"""Textul radio al barei (RdsInfoDisplay, peste imagine) ar aparea de doua ori cat se vede ecranul radio."""
		rds = getattr(self.infobar, "rds_display", None)
		if rds is None:
			return
		if not arata:
			rds.hide()
		elif not getattr(self.infobar, "hdsListaRadioDeschisa", False):
			rds.show()

	def _legaTasta(self, da):
		if da and not self.tasta_legata:
			eActionMap.getInstance().bindAction('', -0x7FFFFFFF, self._tasta)
			self.tasta_legata = True
		elif not da and self.tasta_legata:
			eActionMap.getInstance().unbindAction('', self._tasta)
			self.tasta_legata = False

	def _tasta(self, tasta, steag):
		"""Orice tasta: se tine minte ora (ecranul de odihna) si se iese din odihna. Tasta merge mai departe.
		OK pe ecranul radio, cu bara in fata: apasarea porneste ceasul apasarii lungi, eliberarea inainte de el e OK
		scurt (lista radio), ceasul ajuns la capat e OK tinut (optiunile). Merge cu orice harta de taste: nu are nevoie
		de un context cu OK lung."""
		self.ultima_tasta = time.time()
		if self.in_odihna:
			self._iesiDinOdihna()
		if tasta in TASTE_OK:
			if steag == STEAG_APASAT:
				self._ok_armat = self.radio and self.vizibil and self.pornit() and self._inFata()
				self._ok_lung = False
				if self._ok_armat:
					self.tOkLung.start(OK_LUNG_MS, True)
			elif steag == STEAG_ELIBERAT and self._ok_armat:
				self._ok_armat = False
				self.tOkLung.stop()
				if not self._ok_lung:
					# in afara impartirii tastei: lista se deschide dupa ce eActionMap a terminat cu eliberarea
					self.tOkScurt.start(0, True)
		return 0

	def _intraInOdihna(self):
		self.in_odihna = True
		self.ecran.hide()
		self.pas_odihna = 0
		self.odihna_la = time.time()
		self._mutaOdihna()
		p = self.odihna.panza
		if p is not None:
			p.schimba(culori=[DES.intunecat(c, 0.55) for c in self._culori()])
			p.curata = True
		self.odihna.show()
		self._planificaCadru()

	def _iesiDinOdihna(self):
		self.in_odihna = False
		self.odihna.hide()
		if self.vizibil:
			if self.ecran.panza is not None:
				self.ecran.panza.curata = True
			self.ecran.show()
			self.actualizeaza(tot=True)
		self._planificaCadru()

	def _mutaOdihna(self):
		lat, inalt = _latime_ecran()
		bl, bi = self.odihna.bloc
		x, y = drum_odihna(self.pas_odihna, lat, inalt, bl, bi)
		self.odihna.muta(x, y)

	# ---- datele pe ecran

	def analiza(self):
		"""Starea si datele analizorului (pentru pagina web), sau None."""
		return self._analiza()

	def _analiza(self):
		if self.analizor is None:
			if not self.radio:
				return None
			if self.fara_pid:
				return {"stare": AN.STARE_FARA_DATE, "motiv": "serviciul nu are PID audio"}
			if self.tAnaliza.isActive():
				return {"stare": AN.STARE_ASTEAPTA, "motiv": ""}
			return None
		try:
			return self.analizor.descriere()
		except Exception:
			return None

	def actualizeaza(self, tot=True, rds=False):
		"""Datele din HdsRadioDate pe etichete. tot=False: numai semnalul, sunetul si ce a trecut din emisiune."""
		if not self.radio:
			return
		acum = time.time()
		try:
			if tot or not self.d or acum - self.epg_la >= EPG_S:
				self.d = RD.date(self.session, S.numar_epg(), self._analiza(), acum)
				self.epg_la = acum
			else:
				self.d = RD.rapid(self.d, self.session, self._analiza(), acum, cu_rds=rds)
		except Exception as e:
			_jurnal("date: %s" % e)
			return
		if not (self.vizibil or self.in_odihna):
			return
		d = self.d
		e = self.ecran
		self._asezarea(d, acum)
		nume = RD.text_nume(d)
		potriveste(e["nume"], nume)
		potriveste(e["detalii"], RD.text_detalii(d))
		e["data"].setText(self._data(acum))
		ep = d.get("epg")
		if ep is None:
			for n in ("acumEticheta", "acumOra", "acumTitlu", "ramas", "urmeazaEticheta") + tuple(
					"urmeaza%s%d" % (f, i) for f in ("Ora", "Titlu") for i in range(1, URMATOARE + 1)):
				e[n].hide()
			e["progres"].value = 0
			e.arataProgres(False)
			e["epgLipsa"].setText(_("Postul nu transmite programul emisiunilor."))
			e["epgLipsa"].show()
		else:
			e["epgLipsa"].hide()
			cur = ep.get("acum")
			if cur:
				e["acumEticheta"].show()
				e["acumOra"].setText(RD.ora(cur["inceput"]))
				potriveste(e["acumTitlu"], cur["titlu"])
				e["ramas"].setText(RD.text_ramas(cur))
				for n in ("acumOra", "acumTitlu", "ramas"):
					e[n].show()
				e["progres"].value = max(0, cur.get("progres", 0))
				e.arataProgres(cur.get("progres", -1) >= 0)
			else:
				for n in ("acumEticheta", "acumOra", "acumTitlu", "ramas"):
					e[n].hide()
				e["progres"].value = 0
				e.arataProgres(False)
			urm = ep.get("urmatoare") or []
			cate = S.numar_epg()
			if urm:
				e["urmeazaEticheta"].show()
			else:
				e["urmeazaEticheta"].hide()
			randuri_epg = min(len(urm), cate, URMATOARE)
			# ora si titlul in etichete separate, pe coloanele orei si titlului emisiunii de acum
			for i in range(1, URMATOARE + 1):
				wo = e["urmeazaOra%d" % i]
				wt = e["urmeazaTitlu%d" % i]
				if i <= len(urm) and i <= cate:
					wo.setText(RD.ora(urm[i - 1]["inceput"]))
					potriveste(wt, urm[i - 1]["titlu"])
					wo.show()
					wt.show()
				else:
					wo.hide()
					wt.hide()
		# piesa si textul radio: intregi, pe unul sau doua randuri (randuriText), textul radio sub piesa, barele sub ele;
		# cu mai putine emisiuni urmatoare decat randurile skinului, textele urca sub ultima aratata
		if ep is None:
			randuri_epg = 0
		urcare = (URMATOARE - randuri_epg) * e.pasUrmatoare()
		r = d.get("rds") or {}
		if r.get("piesa"):
			e.randuriText("piesa", r["piesa"])
			e["piesaEticheta"].show()
			e["piesa"].show()
		else:
			e["piesaEticheta"].hide()
			e["piesa"].hide()
		text = r.get("text") or u""
		if r.get("rass"):
			text = (text + u"  (RaSS)") if text else _("Postul transmite pagini RaSS.")
		if text and text != r.get("piesa"):
			e.randuriText("radiotext", text)
			e["radiotext"].show()
		else:
			text = u""
			e["radiotext"].hide()
		e.aseazaRds(bool(r.get("piesa")), bool(text), urcare)
		# randurile de jos taiate la cuvant (textele lungi in unele limbi trec de caseta); un rand gol lasa locul
		# randului de sub el. Randul semnalului se aseaza (grupurile, latimea textului) inainte de scrierea textului.
		sunet = RD.text_sunet(d)
		transponder = RD.text_transponder(d)
		potriveste(e["sunet"], sunet)
		potriveste(e["transponder"], transponder)
		potriveste(e["satelit"], RD.text_satelit(d))
		slab = RD.semnal_slab(d)
		e["semnal"].setVisible(not slab)
		e["semnalSlab"].setVisible(slab)
		e.arataSemnal(*RD.procente_semnal(d))
		e.randuriJos(not sunet, not transponder)
		potriveste(e["semnal" if not slab else "semnalSlab"], RD.text_semnal(d))
		self._mesajBare(d.get("analiza"))
		o = self.odihna
		potriveste(o["odihnaNume"], nume)
		o.randuriText("odihnaPiesa", r.get("piesa") or text or u"")

	def _asezarea(self, d, acum):
		"""Asezarea stransa (fara program si fara text radio) si locul siglei, dupa datele postului. Asezarea se
		schimba cel mult de doua ori la un post: dupa ASTEPTARE_DATE_S fara date se strange, iar cand vin date se
		intinde si ramane asa pana la alt post (textul radio care vine si pleaca nu muta barele)."""
		r = d.get("rds") or {}
		are_date = bool(d.get("epg")) or bool(r.get("text") or r.get("piesa") or r.get("rass"))
		cheie = RD._cheie_ref(d.get("ref") or u"")
		if are_date:
			self.date_vazute = True
		if self.date_vazute:
			self._aseaza(False, cheie)
		elif acum - self.post_pornit_la >= ASTEPTARE_DATE_S:
			self._aseaza(True, cheie)
		if cheie and cheie not in self.sigle:
			if len(self.sigle) > 500:
				self.sigle.clear()
			self.sigle[cheie] = self._areSigla(d.get("ref"))
		self.ecran.aseazaFaraSigla(self.sigle.get(cheie) is False)

	def _aseaza(self, strans, cheie=None):
		if cheie:
			if len(self.asezari) > 500:
				self.asezari.clear()
			self.asezari[cheie] = bool(strans)
		if self.ecran.aseazaStrans(strans):
			self.fara_date_desenat = True
			self.mesaj_aratat = None      # mesajele barelor se scriu din nou in locul nou

	def _areSigla(self, ref_text):
		"""True / False daca postul are sigla pe disc; None cand nu se poate afla (atunci caseta ramane)."""
		try:
			from Components.Renderer.Picon import cauta_sigla
		except Exception:
			return None
		try:
			return bool(cauta_sigla(ref_text or ""))
		except Exception:
			return None

	def _data(self, acum):
		zile = (_("Monday"), _("Tuesday"), _("Wednesday"), _("Thursday"), _("Friday"), _("Saturday"), _("Sunday"))
		t = time.localtime(acum)
		return u"%s, %s" % (zile[t.tm_wday], time.strftime("%d.%m.%Y", t))

	# starile in care barele nu se pot arata deloc (nu „asteapta”: atunci barele vin in cateva clipe si randul tastelor
	# ar clipi la fiecare post)
	STARI_FARA_BARE = (AN.STARE_FARA_BARE, AN.STARE_ALTUL, AN.STARE_FARA_DATE, "aac-fara-bare")

	def _mesajBare(self, analiza):
		fel = S.valoare("vizualizator")
		text = RD.text_bare(analiza, fel)
		e = self.ecran
		stare = (analiza or {}).get("stare")
		e.arataTasteViz(stare not in self.STARI_FARA_BARE)
		if text and stare != AN.STARE_BARE:
			e["mesajBare"].setText(text)
			e["mesajBare"].show()
			self.mesaj_aratat = True
			if not self.fara_date_desenat and e.panza is not None:
				try:
					DES.aplica(e["bare"], e.panza.goleste())
				except Exception as ex:
					_jurnal("desen: %s" % ex)
				self.fara_date_desenat = True
		else:
			self._ascundeMesajBare()

	def _ascundeMesajBare(self):
		if self.mesaj_aratat is not False:
			self.ecran["mesajBare"].hide()
			self.mesaj_aratat = False

	# ---- ceasurile

	def _culori(self):
		return DES.tema(S.valoare("culori"))

	def _planificaCadru(self):
		if not (self.vizibil or self.in_odihna):
			self.tCadru.stop()
			return
		if not self._inFata() and not self.in_odihna:
			self.tCadru.start(MS_ASTEPTARE, True)
			return
		fps = CADRE_ODIHNA if self.in_odihna else S.numar_cadre()
		self.tCadru.start(int(1000 / fps), True)

	def _cadru(self):
		try:
			self._deseneaza()
		except Exception as e:
			_jurnal("cadru: %s" % e)
		self._planificaCadru()

	def _deseneaza(self):
		an = self.analizor
		if an is None or an.stare != AN.STARE_MP2:
			return
		if self.in_odihna:
			p = self.odihna.panza
			sursa = self.odihna["bareMici"]
			fel = "bare"
		else:
			if not self._inFata():
				return
			p = self.ecran.panza
			sursa = self.ecran["bare"]
			fel = S.valoare("vizualizator")
			if p is not None:
				p.schimba(fel=fel, culori=self._culori())
		if p is None or fel == "oprit":
			return
		fps = CADRE_ODIHNA if self.in_odihna else S.numar_cadre()
		nivele = an.nivele(1.5 / fps)
		if nivele is None:
			return
		info = an.flux.info
		ops = p.cadru(nivele, S.numar_bare() if not self.in_odihna else 12, time.time(), info.get("esantionare", 48000),
			font=self.font_nivel)
		if ops:
			DES.aplica(sursa, ops)
			self.fara_date_desenat = False
			# „Se citește sunetul postului...” nu ramane peste primele bare pana la secunda urmatoare
			if not self.in_odihna:
				self._ascundeMesajBare()

	def _secunda(self):
		try:
			self._pasSecunda()
		except Exception as e:
			_jurnal("secunda: %s" % e)

	def _pasSecunda(self):
		acum = time.time()
		if self._inStandby():
			self.ascunde()
			return
		if self.radio and (self.vizibil or self._webActiv()):
			self.actualizeaza(tot=False)
		self._pazaAnaliza(acum)
		if not self.vizibil:
			if not self._webActiv():
				self.tSecunda.stop()
			return
		# la pornirea receptorului pe radio bara arata textul radio dupa ce s-a aratat ecranul radio
		self._rdsBara(False)
		minute = S.minute_odihna()
		if not self.in_odihna and minute and self._inFata() and acum - self.ultima_tasta >= minute * 60:
			self._intraInOdihna()
		if self.in_odihna and acum - self.odihna_la >= ODIHNA_PAS_S:
			self.odihna_la = acum
			self.pas_odihna += 1
			self._mutaOdihna()
		if not self.in_odihna and acum - self.mutat_la >= MUTARE_S:
			self.mutat_la = acum
			self.pas_ardere += 1
			self.ecran.muta(self.pas_ardere)
		if not self.tCadru.isActive():
			self._planificaCadru()

	# ---- analizorul

	def _webActiv(self):
		return time.time() - self.cerere_web < WEB_S

	def cerereWeb(self):
		"""Pagina web a cerut benzile: analizorul merge inca WEB_S secunde, chiar daca ecranul nu se vede."""
		self.cerere_web = time.time()
		if self.radio and self.analizor is None and not self.tAnaliza.isActive():
			self.tAnaliza.start(10, True)
		if not self.tSecunda.isActive():
			self.tSecunda.start(MS_SECUNDA)

	def _trebuieAnaliza(self):
		if not self.radio:
			return False
		if self._webActiv():
			return True
		if not (self.vizibil or self.in_odihna):
			return False
		if S.valoare("vizualizator") == "oprit" and not self.in_odihna:
			return False
		return True

	def _pazaAnaliza(self, acum):
		# pista audio schimbata cu AUDIO: selectAudioStream (lib/service/servicedvb.cpp) schimba sAudioPID fara niciun
		# eveniment, deci PID-ul se compara aici, o data pe secunda, cat merge analizorul (un getInfo, nimic greu)
		if self.analizor is not None and not self.fisier_proba and self.analiza_pid and self.analiza_pid > 0:
			try:
				pid = RD.pid_audio(self.session.nav.getCurrentService())
			except Exception:
				pid = -1
			if pid > 0 and pid != self.analiza_pid:
				_jurnal("pista audio noua: PID 0x%X" % pid)
				self._opresteAnaliza()
				self.fara_pid = False
				self.tAnaliza.start(PORNIRE_ANALIZA_MS, True)
				return
		if self._trebuieAnaliza() and (self._inFata() or self.in_odihna or self._webActiv()):
			self.analiza_nevazuta_de = None
			if self.analizor is None and not self.tAnaliza.isActive():
				self.tAnaliza.start(10, True)
			return
		if self.analizor is None:
			return
		if self.analiza_nevazuta_de is None:
			self.analiza_nevazuta_de = acum
		elif acum - self.analiza_nevazuta_de >= OPRIRE_ANALIZA_S:
			self._opresteAnaliza()

	def _pornesteAnaliza(self):
		if not self._trebuieAnaliza() or self.analizor is not None:
			return
		try:
			service = self.session.nav.getCurrentService()
		except Exception:
			service = None
		releu = None
		if not self.fisier_proba and service is not None:
			# post DAB+ / program DVB-T2 prin releul local (tipul 1 cu sursa http): sunetul trece prin demultiplexorul
			# redarii, unde filtrul din frontend nu primeste nimic; barele citesc acelasi flux de la releu
			ref_text = RD.ref_curenta(self.session)[1]
			campuri = ref_text.split(u":") if ref_text else []
			if len(campuri) > 10 and AN.adresa_releu(campuri[10]) is not None:
				releu = campuri[10]
		if self.fisier_proba:
			sursa = AN.SursaFisier(self.fisier_proba)
			pid = -2
		elif releu is not None:
			# PID-ul pistei alese, cand PMT-ul a venit; altfel primul PID cu sunet din flux
			pid = RD.pid_audio(service)
			sursa = AN.SursaHttp(releu, pid if pid > 0 else None)
			_jurnal("barele din fluxul releului %s (PID %s)" % (AN.adresa_releu(releu)[2], ("0x%X" % pid) if pid > 0
				else "din flux"))
		else:
			pid = RD.pid_audio(service) if service is not None else -1
			if pid <= 0:
				self.analiza_pid = None
				self.fara_pid = True
				self._mesajBare(self._analiza())
				return
			# demultiplexorul serviciului, cand imaginea il da (getStreamingData); pe altul acelasi PID poate fi al altui
			# post. Numai fara el se incearca demux0 si demultiplexorul cu numarul tunerului.
			demux = RD.demux_serviciu(service)
			if demux is not None:
				cai = [AN.DEMUX % (0, demux)]
			else:
				tuner = RD.numar_tuner(service)
				cai = [AN.DEMUX % (0, 0)]
				if tuner > 0:
					cai.append(AN.DEMUX % (0, tuner))
			sursa = AN.SursaDemux(pid, cai)
		self.analiza_pid = pid
		self.fara_pid = False
		self.analiza_nevazuta_de = None
		self.analizor = AN.Analizor(sursa)
		self.analizor.porneste(inainte=getattr(self, "_analizor_vechi", None))
		self._analizor_vechi = None
		self.fara_date_desenat = False

	def _opresteAnaliza(self):
		if self.analizor is not None:
			self.analizor.opreste()
			self._analizor_vechi = self.analizor
			self.analizor = None
		self.analiza_nevazuta_de = None

	def analizaDinFisier(self, cale):
		"""Pentru emulator si probe: barele din fisierul `cale` (TS sau PES), nu din demultiplexor."""
		self.fisier_proba = cale
		self._opresteAnaliza()
		self.tAnaliza.start(10, True)

	# ---- tastele (din HartaRadio, Screens/InfoBar.py)

	def okBara(self):
		"""OK din harta barei (toggleShow, la apasare). Cand ascultatorul global a vazut apasarea, OK se hotaraste la
		eliberare (scurt = lista, tinut = optiunile) si apasarea nu mai ajunge la bara; altfel OK lucreaza pe loc."""
		if self._ok_armat:
			return 1
		return self.ok()

	def _okTinut(self):
		if self._ok_armat:
			self._ok_lung = True
			self.optiuni()

	def _okScurt(self):
		self.ok()

	def ok(self):
		if not self.radio or not self.pornit():
			return 0
		if self.ascuns_de_om or not self.vizibil:
			self.ascuns_de_om = False
			self.arata()
			self.actualizeaza(tot=True)
			return 1
		self.lista()
		return 1

	def iesire(self):
		if getattr(self.infobar, "shown", False):
			return 0              # bara e deschisa: EXIT o inchide, ca de obicei
		if self.vizibil:
			self.ascuns_de_om = True
			self.ascunde()
			return 1
		return 0

	def okDinLista(self):
		"""OK pe un post de radio in lista de canale (Screens/ChannelSelection.py): ecranul radio pe tot ecranul, si daca
		fusese ascuns cu EXIT. Un post nou vine cu evStart (laStart il arata); pe postul care merge deja se arata aici."""
		try:
			self.ascuns_de_om = False
			if self.radio and self.pornit() and not self.vizibil:
				self.arata()
				self.actualizeaza(tot=True)
		except Exception as e:
			_jurnal("OK din lista: %s: %s" % (type(e).__name__, e))

	# ---- GALBEN / ALBASTRU: vizualizarea si culorile urmatoare

	def _tastaColorata(self):
		"""Tastele colorate sunt ale ecranului radio numai cat el se vede si bara e fereastra din fata."""
		return bool(self.radio and self.pornit() and self.vizibil and self._inFata())

	def tastaGalbena(self):
		if not self._tastaColorata():
			self.galben_apasat = False
			return 0
		self.galben_apasat = True
		self.schimbaAlegerea("vizualizator")
		return 1

	def tastaAlbastra(self):
		if not self._tastaColorata():
			self.albastru_apasat = False
			return 0
		self.albastru_apasat = True
		self.schimbaAlegerea("culori")
		return 1

	def tastaVerde(self):
		"""VERDE pe ecranul radio: egalizatorul (Screens/HdsEgalizator.py), deschis peste ecranul radio."""
		if not self._tastaColorata():
			return 0
		self.egalizator()
		return 1

	def egalizator(self):
		from Screens.HdsEgalizator import HdsEgalizator
		self.session.open(HdsEgalizator)

	def faraExtensii(self):
		"""Eliberarea albastrului (InfobarExtensions „extensions”, la eliberare) nu mai deschide extensiile dupa ce
		apasarea lui a schimbat culorile."""
		if self.albastru_apasat:
			self.albastru_apasat = False
			return 1
		return 0

	def faraPisteAudio(self):
		"""Eliberarea galbenului pe telecomanda Viper (InfobarAudioSelectionActions „audioSelection”, la eliberare) nu
		mai deschide pistele audio dupa ce apasarea lui a schimbat vizualizarea. O eliberare fara apasarea prinsa aici
		(canal TV, ecranul radio ascuns, alt ecran in fata) merge mai departe, la pistele audio, ca inainte."""
		if self.galben_apasat:
			self.galben_apasat = False
			return 1
		return 0

	def schimbaAlegerea(self, nume, valoare=None):
		"""Alegerea urmatoare (sau `valoare`) a setarii `nume` („vizualizator”, „culori”), vazuta pe loc si anuntata
		peste bare. Setarea ramane in memorie; fisierul setarilor se scrie o data, la SALVARE_MS dupa ultima schimbare
		(nu la fiecare apasare). -> valoarea noua."""
		element = getattr(S.initConfig(), nume)
		noua = valoare if valoare is not None else S.urmatoarea(nume, element.value)
		if element.value != noua:
			element.value = noua
			element.save()
			self.tSalvare.start(SALVARE_MS, True)
		self.setariSchimbate()
		if self.vizibil and not self.in_odihna:
			self.ecran.anunta(_(S.TITLURI_ALEGERE[nume]) % _(S.text_alegere(nume, noua)))
			self.tAnunt.start(ANUNT_MS, True)
		return noua

	def _ascundeAnunt(self):
		self.ecran["anunt"].hide()

	def _salveazaSetari(self):
		try:
			configfile.save()
		except Exception as e:
			_jurnal("setarile: %s" % e)

	def _listaPeRadio(self):
		lista = getattr(self.infobar, "servicelist", None)
		return lista is not None and getattr(lista, "mode", 0) == 1

	def zapUrmator(self):
		return self._zap(1)

	def zapAnterior(self):
		return self._zap(-1)

	def _zap(self, directie):
		if not self.radio:
			return 0
		if self._listaPeRadio():
			return 0              # lista barei e pe radio: zapUp / zapDown obisnuite
		ref, ref_text = RD.ref_curenta(self.session)
		nou = RD.vecin(ref_text, directie)
		if nou is None:
			# nicio lista radio aleasa inca (radioul pornit din web sau din cifre): tasta nu face nimic; lasata barei
			# ar schimba canalul din lista TV
			return 1
		self.session.nav.playService(nou)
		try:
			config.radio.lastservice.value = nou.toString()
			config.radio.lastservice.save()
		except Exception:
			pass
		return 1

	def listaSus(self):
		return self._sageata(True)

	def listaJos(self):
		return self._sageata(False)

	def _sageata(self, sus):
		"""Sagetile SUS si JOS pe radio, dupa setarea "Săgețile sus și jos la privit" (Components/HdsSageti.py, aceeasi
		regula ca bara TV): lista radio, lista de canale TV (InfoBar.showTv: canalul TV de dinainte si lista TV) sau
		postul urmator (SUS) si anterior (JOS). Pe lista comuna in modul radio o face InfoBarChannelSelection."""
		if not self.radio or self._listaPeRadio():
			return 0
		from Components.HdsSageti import sageata
		fel = sageata(sus)
		if fel == "zap":
			return self._zap(1 if sus else -1)
		if fel == "radio":
			return self.listaRadio()
		arata_tv = getattr(self.infobar, "showTv", None)
		if arata_tv is None:
			return 0
		arata_tv()
		return 1

	def listaRadio(self):
		"""Lista radio (si tasta care deschide lista, openServiceList), oricare ar fi setarea sagetilor."""
		if not self.radio or self._listaPeRadio():
			return 0
		self.lista()
		return 1

	def lista(self):
		"""Lista de canale pe radio: lista comuna (TV / Radio) sau, cu „mod radio separat” oprit, lista radio."""
		ib = self.infobar
		# amandoua listele pornesc la deschidere config.radio.lastservice (lista separata il porneste sau opreste
		# serviciul daca e gol; lista comuna face zap pe el daca difera): postul care merge acum (pornit din web, din
		# cautare, din cifre) devine ultimul post, ca sa ramana pornit
		ref_radio = self.refRadioCurenta()
		if ref_radio and config.radio.lastservice.value != ref_radio:
			config.radio.lastservice.value = ref_radio
			config.radio.lastservice.save()
		if config.usage.e1like_radio_mode.value:
			ib.showRadioChannelList(True)
		else:
			ib.showRadio()

	def optiuni(self):
		"""OK tinut: optiunile ecranului radio. Randurile au numai numele (alegerea de acum e aleasa in lista care se
		deschide), ca sa incapa in orice limba."""
		from Screens.ChoiceBox import ChoiceBox
		lista = [
			(_("Vizualizatorul"), "viz"),
			(_("Culorile"), "cul"),
			(_("Egalizator"), "egal"),
		]
		if (self.d or {}).get("epg"):
			lista.append((_("Programul postului"), "program"))
		lista += [
			(_("Setările ecranului radio"), "setari"),
			(_("Ascunde ecranul radio"), "ascunde"),
		]
		self.session.openWithCallback(self._optiune, ChoiceBox, title=_("Ecranul radio"), list=lista)

	def _program(self):
		"""Ghidul programelor pe postul de acum (EPG-ul unui singur post al barei)."""
		ib = self.infobar
		for nume in ("openSingleServiceEPG", "openEventView"):
			f = getattr(ib, nume, None)
			if f is not None:
				try:
					f()
					return
				except Exception as e:
					_jurnal("programul postului: %s" % e)

	def _optiune(self, ales):
		if not ales:
			return
		from Screens.ChoiceBox import ChoiceBox
		if ales[1] == "viz":
			alegeri = [(_(t), v) for v, t in S.VIZUALIZATOARE]
			valori = [v for t, v in alegeri]
			cur = S.valoare("vizualizator")
			self.session.openWithCallback(lambda r: self._pune("vizualizator", r), ChoiceBox, title=_("Vizualizatorul"),
				list=alegeri, selection=valori.index(cur) if cur in valori else 0)
		elif ales[1] == "cul":
			alegeri = [(_(t), v) for v, t in S.CULORI]
			valori = [v for t, v in alegeri]
			cur = S.valoare("culori")
			self.session.openWithCallback(lambda r: self._pune("culori", r), ChoiceBox, title=_("Culorile"),
				list=alegeri, selection=valori.index(cur) if cur in valori else 0)
		elif ales[1] == "egal":
			self.egalizator()
		elif ales[1] == "program":
			self._program()
		elif ales[1] == "setari":
			self.session.openWithCallback(lambda *a: self.setariSchimbate(), HdsEcranRadioSetari)
		elif ales[1] == "ascunde":
			self.ascuns_de_om = True
			self.ascunde()

	def _pune(self, nume, ales):
		if not ales:
			return
		if nume in S.TASTE_ALEGERI:
			# aceeasi cale ca GALBEN / ALBASTRU (numele alegerii apare peste bare); aleasa din lista, se scrie pe loc
			self.schimbaAlegerea(nume, ales[1])
			self.tSalvare.stop()
			self._salveazaSetari()
			return
		element = getattr(S.initConfig(), nume)
		if element.value != ales[1]:
			element.value = ales[1]
			element.save()
			configfile.save()
		self.setariSchimbate()

	def setariSchimbate(self):
		"""Setarile s-au schimbat (din web sau din ecranul setarilor): ecranul, tastele si analizorul dupa ele."""
		self._hartaActiva(self.radio and self.pornit())
		if not self.radio:
			return
		if not self.pornit():
			self.ascunde()
			return
		if self.ecran.panza is not None:
			self.ecran.panza.curata = True
			# „Oprit”: desenul se opreste (_deseneaza iese), deci panza se goleste acum, o data; altfel ar ramane pe
			# ecran ultimul cadru, nemiscat
			if S.valoare("vizualizator") == "oprit":
				try:
					DES.aplica(self.ecran["bare"], self.ecran.panza.goleste())
				except Exception as ex:
					_jurnal("desen: %s" % ex)
				self.fara_date_desenat = True
		if not self.ascuns_de_om:
			self.arata()
		self.actualizeaza(tot=True)
		if self._trebuieAnaliza() and self.analizor is None:
			self.tAnaliza.start(10, True)

	# ---- bara la schimbarea postului (Screens/InfoBar.py, serviceStarted)

	def faraBaraLaZap(self):
		"""True cand bara obisnuita nu trebuie aratata singura la pornirea postului: ecranul radio are totul.
		Se cheama din InfoBar.serviceStarted, la evStart, INAINTE de laStart (urmaritorul barei e facut inaintea celui
		al ferestrei radio): self.radio descrie inca serviciul de dinainte, deci hotararea se ia numai din serviciul
		care porneste. Tot de aici intreaba si InfoBar.hdsDupaListaRadio, la inchiderea listei radio separate
		(ChannelSelectionRadio, care primeste ea evStart-ul posturilor alese in ea), si InfoBar.__eventInfoChanged, la
		prima emisiune a unui post pornit pe alta cale fara serviceStarted la bara."""
		if not self.pornit() or S.valoare("bara_la_zap"):
			return False
		ref, ref_text = RD.ref_curenta(self.session)
		try:
			service = self.session.nav.getCurrentService()
		except Exception:
			service = None
		return bool(ref_text) and self._barPrincipala() and RD.este_post_radio(service, ref_text)


def faLegatura(infobar):
	"""Pentru Screens/InfoBar.py: legatura sau None (cu o linie in jurnal) daca ferestrele nu se pot face."""
	try:
		return LegaturaRadio(infobar)
	except Exception as e:
		_jurnal("ecranul radio nu se poate face, merge bara obisnuita: %s: %s" % (type(e).__name__, e))
		return None
