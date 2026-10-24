# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTraducereSubtitrari (ecranul) - „Traducerea subtitrărilor": traducerea automata a subtitrarilor text (teletext,
# fisiere si textul citit din subtitrarile DVB), prin serviciul ales de om (Components/HdsTraducereSubtitrari.py).
#
# Randurile: pornit/oprit; serviciul; campurile serviciului ales (cheia API, regiunea la Azure, adresa serverului la
# LibreTranslate si la serverul compatibil OpenAI, ID-ul contului la Cloudflare Workers, modelul la Gemini, Groq,
# Cloudflare Workers si la serverul compatibil OpenAI; la Groq si Cloudflare modelul se alege din lista propusa sau se
# scrie, iar ID-ul contului se verifica la scriere: 32 de semne hex); limba
# traducerii (implicit limba meniului); afisarea (in locul originalului sau sub el); traducerea care intarzie (se
# asteapta, cu ecranul gol, sau dupa 2 s ramane originalul cu semnul „(netradus)”: originalul nu apare niciodata inaintea
# traducerii); timpul de citire (cat sta cel putin o subtitrare tradusa, dupa lungime: Components/HdsTraducereSubtitrari
# TIMP_CITIRE); subtitrarile DVB (prin recunoasterea textului); contorul „Ce s-a tradus” (OK il
# pune la zero); „Tradu bara de jos” (titlurile barei, cu traducerea pornita), „Tradu EPG” si contorul ghidului
# (Components/HdsTraducereEpg.py); "Tradu teletextul", "Teletextul tradus" (in pagina sau intr-un panou), "Tradu HbbTV"
# si contorul lor (Components/HdsTraducereTexte.py). Sub lista: ce face randul, ce lipseste si ce pleaca din receptor
# (confidentialitatea).
# Cheia: OK pe rand deschide alegerea „Scrie cheia nouă” / „Șterge cheia”; cheia scrisa merge direct in fisierul
# criptat (Components/HdsTraducereSubtitrari.chei()) si nu se mai arata niciodata (randul spune numai „pusă”).
# Textele (regiunea, adresa, modelul): OK deschide tastatura de pe ecran.
# Galben: „Probează traducerea”: o fraza de proba trimisa serviciului ales; raspunsul (sau eroarea, pe intelesul
# oricui) apare sub lista, iar originalul si traducerea sunt desenate chiar de eSubtitleWidget, ca subtitrarile
# (showTranslationSample: traducerea sub original, in culoarea ei, ca la afisarea „Sub original”).
# Albastru: instructiunile pas cu pas pentru serviciul ales (avertismentul platii automate la Google Cloud, cont, cheie
# gratuita, cota, ce se intampla la depasire, data verificarii); stanga/dreapta in ordinea din T.SERVICII. Verde salveaza, Rosu anuleaza (valorile se intorc).
# Numai cu sagetile si OK: randurile-buton „Probează traducerea” si „Instrucțiuni” (sub campurile serviciului) fac
# acelasi lucru ca Galben si Albastru; EXIT cu ceva schimbat intreaba (ChoiceBox: salveaza / lasa cum era / inapoi),
# fara schimbari inchide. Rosu anuleaza fara intrebare.
# Campurile text (regiunea, adresele, modelele) se arata prin randuri-proxy (o singura alegere, textul valorii): o
# valoare goala apare „Global” la regiune si „lipsește (OK o scrie)” la celelalte, nu o casuta goala.
# Serviciile de rezerva: randul arata langa fiecare ce ii lipseste („fără cheie”), din T.ceLipseste; ajutorul randului
# spune intreg ce lipseste fiecaruia si care e serviciul principal. OK pe rand: adauga, muta, scoate, si „Fă-l
# principal” pentru serviciile gata (T.serviciiGata, T.punePrincipal: principalul nou iese din rezerve, fostul intra
# primul; salvat cu Verde, ca restul ecranului). Rezultatul unei chei puse ca rezerva (de pe telefon, cand principalul
# merge) e mesajul configuratorului: traducerea ramane pe principal (textRezultat).
# Primul rand, „Configurează de pe telefon”: OK deschide HdsTraducereTelefon, un cod QR mare (Components/HdsQr.py) cu
# adresa http://<IP receptor>/t/<jeton> (HdsWebControl/asociere.py, cereJeton: o folosire, 5 minute, refacut singur la
# expirare, anulat la inchidere); telefonul care il scaneaza ajunge asociat in pagina pas cu pas /traducere-configurare
# (recunoasterea cheii, proba pe loc). Ecranul arata cand s-a conectat telefonul si rezultatul probei facute de pe el.
# La serverul din casa (LibreTranslate, compatibil OpenAI) randul „Caută în rețeaua de acasă” sta inaintea adresei:
# OK porneste cautarea (Components/HdsConfigurareTraducere.py, pe fire separate), apoi lista gasitelor; serverul ales
# se pune si se probeaza singur (modelul ales automat), cu timpul masurat si avertismentul cand e lent.
# „Adresă proprie” (propriu): adresa-sablon, metoda, corpul, felul corpului, numele antetului si valoarea lui (pastrata
# ca o cheie), felul raspunsului, calea in JSON.
# Adresele (LibreTranslate, compatibil OpenAI, adresa proprie): adresa receptorului insusi (127.0.0.1, localhost,
# 0.0.0.0, 169.254.x, IP-ul lui) e refuzata la scriere, cu mesajul sub lista (T.clasaAdresa / C.normalizeazaAdresa).
# Cheia unui serviciu cu adresa (T.CU_ADRESA) pleaca numai spre gazda pentru care a fost pusa: cheia scrisa in ecran se
# leaga, la Verde, de adresa salvata atunci (T.chei().legaDeAdresa), ca ordinea randurilor (intai cheia sau intai
# adresa) sa nu conteze. La anulare (Rosu, sau EXIT si „lasă cum era”), o cheie scrisa aici pentru o adresa care nu
# ramane salvata se inlocuieste cu cheia si legatura de dinainte (tinute in RAM de la prima cheie scrisa, _cheiVechi):
# cheia veche se intoarce numai la gazda ei. Randul cheii spune „pusă pentru alt server” cand cheia nu pleaca la adresa
# de acum (T.notaCheie, si sub lista). Cat timp fisierul cheilor a fost pus deoparte la pornire (nu se mai putea citi pe
# acest receptor), randul cheii spune „trebuie pusă din nou”, iar nota (T.textCheiDinNou) sta numai in ajutorul
# randului cheii; la serviciile fara cheie obligatorie, o nota blanda.
# In instructiuni, un cod QR spre pagina oficiala a cheii (T.instructiuni(serv)["pagina_cheie"]).
# Skinul HDSatelit nu se atinge: ecranul isi poarta skinul aici, facut dupa marimea ecranului (1920x1080 sau 1280x720).
# Lista are mai multe randuri decat incap: eListbox pune bara de derulare (si ingusteaza randurile) abia la prima mutare
# a cursorului si redeseneaza numai randurile mutate, iar valorile celorlalte raman sub bara. La onLayoutFinish
# (_pornit), inainte de primul desen, lista se aseaza pe randul de acum (moveSelectionTo) si se redeseneaza toata.
# Aceleasi alegeri sunt in interfata web, pagina /traducere-subtitrari
# (Plugins/Extensions/HdsWebControl/traducere_subtitrari_web.py).

from __future__ import absolute_import

from enigma import getDesktop, eSubtitleWidget, eTimer

from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import configfile, getConfigListEntry, ConfigSelection
from Components.GUIComponent import GUIComponent
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components.Sources.CanvasSource import CanvasSource

from Components import HdsTraducereSubtitrari as T

RANDURI_VIZIBILE = 9
AJUTOR_RANDURI = 6			# randurile casetei de ajutor (30 px la fontul de 21); sub panou ramane loc pentru proba subtitrarii
CONTOR_MS = 2000
TELEFON_MS = 1000
FUNDAL_PANOU = 0x10141a22		# culoarea panoului (#10141a22), pentru locul codului QR cand nu e cod
LENT_MS = 1000				# peste atat, proba spune ca serverul e prea lent pentru subtitrari la timp
# regiunile Translator cand modulul traducerii nu are lista lui (T.REGIUNI_AZURE): (cod, numele din portal)
REGIUNI_AZURE_REZERVA = (("", "Global"), ("westeurope", "West Europe"), ("northeurope", "North Europe"),
	("germanywestcentral", "Germany West Central"), ("francecentral", "France Central"), ("swedencentral", "Sweden Central"),
	("uksouth", "UK South"), ("switzerlandnorth", "Switzerland North"))


def _C():
	"""Components/HdsConfigurareTraducere (configurarea cu proba, cautarea in retea), sau None daca lipseste"""
	try:
		from Components import HdsConfigurareTraducere
		return HdsConfigurareTraducere
	except Exception as e:
		print("[HdsTraducereSubtitrari] configurarea: %s" % e)
		return None


def _deseneazaQr(ecran, sursa, text, fundal=FUNDAL_PANOU):
	"""Codul QR al textului pe CanvasSource-ul `sursa` al ecranului (marimea din widget), sau locul gol. -> True daca
	s-a desenat"""
	c = ecran[sursa]
	latime = inaltime = 0
	for r in getattr(ecran, "renderer", []) or []:
		if getattr(r, "source", None) is c and r.instance is not None:
			latime, inaltime = r.instance.size().width(), r.instance.size().height()
	if not latime:
		return False
	try:
		if text:
			from Components.HdsQr import deseneaza
			deseneaza(c, text, latime, inaltime)
		else:
			c.clear()
			c.fill(0, 0, latime, inaltime, fundal)
		c.flush()
		return True
	except Exception as e:
		print("[HdsTraducereSubtitrari] codul QR: %s" % e)
		return False


def _E():
	"""Components/HdsTraducereEpg.py (traducerea ghidului), sau None"""
	try:
		from Components import HdsTraducereEpg
		return HdsTraducereEpg
	except Exception:
		return None


def _X():
	"""Components/HdsTraducereTexte.py (traducerea teletextului si a HbbTV), sau None"""
	try:
		from Components import HdsTraducereTexte
		return HdsTraducereTexte
	except Exception:
		return None


def _camp(s, nume):
	"""elementul de setare `nume` din config.hds_traducere, sau None (ConfigSubsection da KeyError, nu AttributeError)"""
	try:
		return getattr(s, nume)
	except (KeyError, AttributeError):
		return None


def _t_lipsa(text):
	"""„Pentru Adresă proprie lipsește: <text>.” (textele campurilor sunt marcate in Components/HdsTraducereSubtitrari.py)"""
	return _("Pentru %s lipsește: %s.") % (T.numeServiciu("propriu"), _(text))


def _adresaWeb():
	"""http://<IP receptor>[:port] (HdsWebControl.adresaWeb), sau None"""
	try:
		from Plugins.Extensions.HdsWebControl.plugin import adresaWeb
		return adresaWeb()
	except Exception as e:
		print("[HdsTraducereSubtitrari] adresa interfetei web: %s" % e)
		return None


def _numeLocal():
	"""numele din reteaua de acasa (hdsatelit.local), ca rezerva scrisa sub cod"""
	try:
		from Plugins.Extensions.HdsWebControl.plugin import CALE_NUME_LOCAL, NUME_LOCAL_IMPLICIT
	except Exception:
		return "hdsatelit.local"
	try:
		with open(CALE_NUME_LOCAL, encoding="utf-8", errors="replace") as f:
			n = f.read(64).strip().lower()
		if n.endswith(".local"):
			n = n[:-6]
		if n and all(c.isalnum() or c == "-" for c in n):
			return n + ".local"
	except (IOError, OSError):
		pass
	return NUME_LOCAL_IMPLICIT + ".local"


def textRezultat(st):
	"""textul pe TV al unei lucrari a configuratorului (HdsConfigurareTraducere.Configurator.stare()), sau "" """
	if not st:
		return u""
	fel = st.get("stare")
	if fel == "lucru":
		return _("Se probează pe receptor: %s") % (st.get("pas") or u"...")
	if fel == "ok":
		if st.get("rezerva"):
			# cheia pusa ca rezerva, principalul ramane: mesajul configuratorului (deja tradus)
			return st.get("mesaj") or u""
		p = st.get("proba") or {}
		text = _("Gata: %s merge. Proba: %s") % (st.get("serviciu_nume") or u"", p.get("traducere") or u"")
		ms = p.get("ms") if p.get("ms") is not None else st.get("ms")
		if ms is not None:
			text += u" (%s)" % _secunde(ms)
			if ms > LENT_MS:
				text += u" " + (st.get("sfat_lent") or _("Serverul e prea lent pentru subtitrări la timp. Alege un "
					"serviciu din internet (Gemini, gratuit, fără card) sau un model mai mic."))
		if st.get("nota_rezerve"):
			# fostul principal a intrat primul la rezerve (mesajul configuratorului, deja tradus)
			text += u" " + st["nota_rezerve"]
		return text
	if fel in ("eroare", "regiune"):
		return _("Nu a mers: %s") % u" ".join(x for x in (st.get("mesaj"), st.get("ce_faci")) if x)
	return u""


class ProbaSubtitrare(GUIComponent):
	"""eSubtitleWidget-ul adevarat: originalul si traducerea probei, desenate ca subtitrarile"""
	GUI_WIDGET = eSubtitleWidget

	def arata(self, text):
		if self.instance is not None and hasattr(self.instance, "showSample"):
			self.instance.showSample(text)

	def arataTraducerea(self, original, traducere):
		"""originalul, apoi traducerea sub el, in culoarea traducerii (ca la afisarea „Sub original”)"""
		if self.instance is None:
			return
		if hasattr(self.instance, "showTranslationSample"):
			self.instance.showTranslationSample(original, traducere)
		else:
			self.arata(u"%s\n%s" % (original, traducere))

	def ascunde(self):
		if self.instance is not None:
			self.instance.clearPage()


def _scala(latime, inaltime):
	x = lambda v: int(round(v * latime / 1920.0))
	y = lambda v: int(round(v * inaltime / 1080.0))
	f = lambda v: max(12, int(round(v * inaltime / 1080.0)))
	return x, y, f


def _butoane(x, y, f, sus):
	rez = []
	for i, (nume, culoare) in enumerate((("key_red", "#9f1313"), ("key_green", "#1f771f"), ("key_yellow", "#a08000"),
			("key_blue", "#18188b"))):
		rez.append('<widget source="%s" render="Label" position="%d,%d" size="%d,%d" zPosition="5" font="Regular;%d" '
			'halign="center" valign="center" foregroundColor="#00ffffff" backgroundColor="%s" transparent="0" />'
			% (nume, x(270 + i * 348), sus, x(336), y(46), f(22), culoare))
	return "\n\t\t".join(rez)


def _skin(latime, inaltime):
	x, y, f = _scala(latime, inaltime)
	panou = "#10141a22"
	return """
	<screen name="HdsTraducereSubtitrari" position="0,0" size="%(l)d,%(h)d" flags="wfNoBorder" backgroundColor="#ff000000" title="Traducerea subtitrărilor">
		<widget name="proba" position="0,0" size="%(l)d,%(h)d" zPosition="2" transparent="1" />
		<eLabel position="%(px)d,%(py)d" size="%(pl)d,%(ph)d" backgroundColor="%(panou)s" zPosition="3" />
		<widget source="Title" render="Label" position="%(cx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" foregroundColor="#00ffffff" backgroundColor="%(panou)s" transparent="1" valign="center" zPosition="4" />
		<widget name="config" position="%(cx)d,%(ly)d" size="%(cl)d,%(lh)d" itemHeight="%(ih)d" font="Regular;%(lf)d" secondfont="Regular;%(vf)d" scrollbarMode="showOnDemand" backgroundColor="%(panou)s" zPosition="4" />
		<widget source="ajutor" render="Label" position="%(cx)d,%(ay)d" size="%(cl)d,%(ah)d" font="Regular;%(af)d" foregroundColor="#00d0d8e0" backgroundColor="%(panou)s" transparent="1" valign="top" zPosition="4" />
		%(butoane)s
	</screen>""" % {
		"l": latime, "h": inaltime, "panou": panou,
		"px": x(240), "py": y(30), "pl": x(1440), "ph": y(750),
		"cx": x(270), "cl": x(1380),
		"ty": y(38), "th": y(52), "tf": f(34),
		"ly": y(96), "lh": y(RANDURI_VIZIBILE * 46), "ih": y(46), "lf": f(26), "vf": f(24),
		"ay": y(96 + RANDURI_VIZIBILE * 46 + 10), "ah": y(AJUTOR_RANDURI * 30), "af": f(21),
		"butoane": _butoane(x, y, f, y(96 + RANDURI_VIZIBILE * 46 + 10 + AJUTOR_RANDURI * 30 + 16)),
	}


def _skinInstructiuni(latime, inaltime):
	x, y, f = _scala(latime, inaltime)
	panou = "#10141a22"
	return """
	<screen name="HdsTraducereInstructiuni" position="0,0" size="%(l)d,%(h)d" flags="wfNoBorder" backgroundColor="#ff000000" title="Instrucțiuni">
		<eLabel position="%(px)d,%(py)d" size="%(pl)d,%(ph)d" backgroundColor="%(panou)s" zPosition="1" />
		<widget source="Title" render="Label" position="%(cx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" foregroundColor="#00ffffff" backgroundColor="%(panou)s" transparent="1" valign="center" zPosition="2" />
		<widget name="text" position="%(cx)d,%(sy)d" size="%(tl)d,%(sh)d" font="Regular;%(sf)d" foregroundColor="#00e8eef4" backgroundColor="%(panou)s" transparent="1" zPosition="2" />
		<widget source="qr" render="Canvas" position="%(qx)d,%(sy)d" size="%(q)d,%(q)d" zPosition="2" />
		<widget source="qr_text" render="Label" position="%(qx)d,%(qty)d" size="%(q)d,%(qth)d" font="Regular;%(qtf)d" foregroundColor="#00e8eef4" backgroundColor="%(panou)s" transparent="1" halign="center" valign="top" zPosition="2" />
		<widget source="jos" render="Label" position="%(cx)d,%(jy)d" size="%(cl)d,%(jh)d" font="Regular;%(jf)d" foregroundColor="#00a8b4c0" backgroundColor="%(panou)s" transparent="1" valign="center" zPosition="2" />
	</screen>""" % {
		"l": latime, "h": inaltime, "panou": panou,
		"px": x(160), "py": y(40), "pl": x(1600), "ph": y(1000),
		"cx": x(200), "cl": x(1520), "tl": x(1110),
		"ty": y(52), "th": y(56), "tf": f(34),
		"sy": y(120), "sh": y(840), "sf": f(27),
		"q": y(400), "qx": x(1720) - y(400), "qty": y(530), "qth": y(300), "qtf": f(22),
		"jy": y(970), "jh": y(50), "jf": f(22),
	}


def textInstructiuni(serviciu):
	"""textul ecranului de instructiuni (acelasi continut ca in web)"""
	d = T.instructiuni(serviciu)
	randuri = []
	if d.get("avertisment"):
		randuri.extend([d["avertisment"], u""])
	for i, pas in enumerate(d["pasi"]):
		randuri.append(u"%d. %s" % (i + 1, pas))
	randuri.append(u"")
	if d["cota"]:
		randuri.append(_("Cota gratuită: %s") % d["cota"])
	if d["depasire"]:
		randuri.append(_("La depășire: %s") % d["depasire"])
	randuri.append(d["verificat"] + ((u" " + d["sursa"]) if d["sursa"] else u""))
	return u"\n".join(randuri)


class HdsTraducereInstructiuni(Screen):
	"""instructiunile pas cu pas pentru un serviciu; stanga/dreapta trec la celelalte servicii"""

	def __init__(self, session, serviciu):
		marime = getDesktop(0).size()
		self.skin = _skinInstructiuni(marime.width(), marime.height())
		Screen.__init__(self, session)
		self.serviciu = serviciu if serviciu in T.SERVICII else T.SERVICII[0]
		self["text"] = ScrollLabel(u"")
		self["qr"] = CanvasSource()
		self["qr_text"] = StaticText(u"")
		self.onLayoutFinish.append(self._qr)
		self["jos"] = StaticText(_("Sus și jos derulează. Stânga și dreapta: alt serviciu. OK sau Ieșire închide."))
		# DirectionActions da si eliberarea (*Up) si tinerea apasata (*Repeated): toate legate, altfel jurnalul scrie
		# „unknown action” la fiecare tasta; tinuta apasat, sus/jos deruleaza mai departe, stanga/dreapta nu sar servicii
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self.close,
			"cancel": self.close,
			"up": self["text"].pageUp,
			"down": self["text"].pageDown,
			"upRepeated": self["text"].pageUp,
			"downRepeated": self["text"].pageDown,
			"left": lambda: self._alt(-1),
			"right": lambda: self._alt(1),
			"leftRepeated": self._nimic,
			"rightRepeated": self._nimic,
			"upUp": self._nimic,
			"downUp": self._nimic,
			"leftUp": self._nimic,
			"rightUp": self._nimic,
		}, -2)
		self._arata()

	def _nimic(self):
		pass

	def _alt(self, pas):
		i = (T.SERVICII.index(self.serviciu) + pas) % len(T.SERVICII)
		self.serviciu = T.SERVICII[i]
		self._arata()

	def _arata(self):
		self.setTitle(T.instructiuni(self.serviciu)["titlu"])
		self["text"].setText(textInstructiuni(self.serviciu))
		self._qr()

	def _qr(self):
		"""codul QR spre pagina oficiala a cheii (numai adrese https), cu adresa scrisa dedesubt"""
		pagina = T.instructiuni(self.serviciu).get("pagina_cheie") or u""
		if not pagina.startswith("https://"):
			pagina = u""
		if _deseneazaQr(self, "qr", pagina):
			self["qr_text"].setText((_("Scanează cu telefonul: pagina oficială") + u"\n" + pagina) if pagina else u"")


def _skinTelefon(latime, inaltime):
	x, y, f = _scala(latime, inaltime)
	panou = "#10141a22"
	q = y(620)
	return """
	<screen name="HdsTraducereTelefon" position="0,0" size="%(l)d,%(h)d" flags="wfNoBorder" backgroundColor="#ff000000" title="Configurează de pe telefon">
		<eLabel position="%(px)d,%(py)d" size="%(pl)d,%(ph)d" backgroundColor="%(panou)s" zPosition="1" />
		<widget source="Title" render="Label" position="%(cx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" foregroundColor="#00ffffff" backgroundColor="%(panou)s" transparent="1" valign="center" zPosition="2" />
		<widget source="qr" render="Canvas" position="%(cx)d,%(qy)d" size="%(q)d,%(q)d" zPosition="2" />
		<widget source="pasi" render="Label" position="%(rx)d,%(qy)d" size="%(rl)d,%(pph)d" font="Regular;%(pf)d" foregroundColor="#00e8eef4" backgroundColor="%(panou)s" transparent="1" valign="top" zPosition="2" />
		<widget source="stare" render="Label" position="%(rx)d,%(sy)d" size="%(rl)d,%(sh)d" font="Regular;%(sf)d" foregroundColor="#00f5d76e" backgroundColor="%(panou)s" transparent="1" valign="top" zPosition="2" />
		<widget source="adresa" render="Label" position="%(cx)d,%(ay)d" size="%(cl)d,%(ah)d" font="Regular;%(af)d" foregroundColor="#00ffffff" backgroundColor="%(panou)s" transparent="1" valign="top" zPosition="2" />
		<widget source="jos" render="Label" position="%(cx)d,%(jy)d" size="%(cl)d,%(jh)d" font="Regular;%(jf)d" foregroundColor="#00a8b4c0" backgroundColor="%(panou)s" transparent="1" valign="center" zPosition="2" />
	</screen>""" % {
		"l": latime, "h": inaltime, "panou": panou,
		"px": x(120), "py": y(40), "pl": x(1680), "ph": y(1000),
		"cx": x(170), "cl": x(1580), "ty": y(56), "th": y(64), "tf": f(38),
		"q": q, "qy": y(140), "rx": x(170) + q + x(60), "rl": x(1750) - (x(170) + q + x(60)),
		"pph": y(300), "pf": f(29), "sy": y(450), "sh": y(320), "sf": f(30),
		"ay": y(785), "ah": y(140), "af": f(28), "jy": y(950), "jh": y(50), "jf": f(22),
	}


class HdsTraducereTelefon(Screen):
	"""Codul QR care deschide pe telefon pagina pas cu pas a receptorului, deja asociata (jetonul de unica folosinta
	din HdsWebControl/asociere.py). Jetonul se reface la expirare si dupa folosire (al doilea aparat poate scana si el)
	si se anuleaza la inchidere; ecranul arata telefonul conectat si rezultatul probei pornite de pe telefon."""
	DESTINATIE = "/traducere-configurare"

	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = _skinTelefon(marime.width(), marime.height())
		Screen.__init__(self, session)
		self.setTitle(_("Configurează de pe telefon"))
		self["qr"] = CanvasSource()
		self["pasi"] = StaticText(_("Scanează codul cu camera telefonului. Se deschide pagina receptorului, deja "
			"conectată: alegi serviciul, îți faci cheia și o lipești. Receptorul o probează pe loc."))
		self["stare"] = StaticText(u"")
		self["adresa"] = StaticText(u"")
		self["jos"] = StaticText(_("OK sau Ieșire închide."))
		self["actiuni"] = ActionMap(["OkCancelActions"], {"ok": self.close, "cancel": self.close}, -1)
		self._asociere = None
		self._jeton = None
		self._conectat = None
		self._lucrare = None
		self._ceas = eTimer()
		self._ceas.callback.append(self._bate)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._inchis)

	def _porneste(self):
		C = _C()
		if C is not None:
			try:
				self._lucrare = C.configurator().stare().get("id")
			except Exception as e:
				print("[HdsTraducereSubtitrari] configurarea: %s" % e)
		self._jetonNou()
		self._ceas.start(TELEFON_MS, False)

	def _jetonNou(self):
		baza = _adresaWeb()
		if not baza:
			self._jeton = None
			_deseneazaQr(self, "qr", u"")
			self["stare"].setText(_("Receptorul nu are legătură în rețea, deci pagina nu se poate deschide pe telefon."))
			self["adresa"].setText(u"")
			return
		try:
			from Plugins.Extensions.HdsWebControl.plugin import obtineAsociere
			self._asociere = obtineAsociere()
			self._jeton = self._asociere.cereJeton(self.DESTINATIE)
		except Exception as e:
			print("[HdsTraducereSubtitrari] jetonul pentru telefon: %s" % e.__class__.__name__)
			self._jeton = None
		_deseneazaQr(self, "qr", (baza + "/t/" + self._jeton["jeton"]) if self._jeton else (baza + self.DESTINATIE))
		gazda = baza.split("//", 1)[-1]
		port = gazda[gazda.index(":"):] if ":" in gazda else u""
		self["adresa"].setText(_("Sau scrie în browser: %s\nsau %s") % (baza + self.DESTINATIE,
			"http://" + _numeLocal() + port + self.DESTINATIE))
		self._bate()

	def _bate(self):
		randuri = []
		if self._asociere is not None and self._jeton is not None:
			stare, info = self._asociere.stareJeton(self._jeton["id"])
			if stare == "folosit":
				self._conectat = info
				self._jetonNou()
				return
			if stare == "expirat":
				self._jetonNou()
				return
			if not self._conectat:
				randuri.append(_("Codul e valabil încă %d:%02d; apoi apare altul.") % (info // 60, info % 60))
		if self._conectat:
			nume = self._conectat.get("nume") or u""
			if self._conectat.get("adresa"):
				nume += u" (%s)" % self._conectat["adresa"]
			randuri.insert(0, _("Telefon conectat: %s. Continuă pe telefon.") % nume)
		C = _C()
		if C is not None:
			try:
				st = C.configurator().stare()
				if st.get("id") != self._lucrare:
					rez = textRezultat(st)
					if rez:
						randuri.append(rez)
			except Exception as e:
				print("[HdsTraducereSubtitrari] starea configurarii: %s" % e)
		text = u"\n".join(randuri)
		if self["stare"].getText() != text:
			self["stare"].setText(text)

	def _inchis(self):
		self._ceas.stop()
		if self._asociere is not None and self._jeton is not None:
			self._asociere.anuleazaJeton(self._jeton["id"])
		self._jeton = None


class HdsTraducereSubtitrari(Screen, ConfigListScreen):
	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = _skin(marime.width(), marime.height())
		Screen.__init__(self, session)
		self.setTitle(_("Traducerea subtitrărilor"))
		self.setari = T.initConfig()
		self._cheiPuse = set()			# serviciile cu adresa a caror cheie s-a scris chiar acum, in acest ecran
		self._cheiVechi = {}			# serviciu -> (cheia, legatura) de dinainte de prima cheie scrisa aici (numai RAM)
		self._proxiuri = {}				# id(element text) -> randul-proxy care ii arata valoarea
		self._realul = {}				# id(randul-proxy) -> (elementul text, textul valorii goale)
		ConfigListScreen.__init__(self, [], session=session)
		self["proba"] = ProbaSubtitrare()
		self["ajutor"] = StaticText(u"")
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Probează traducerea"))
		self["key_blue"] = StaticText(_("Instrucțiuni"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.ok,
			"cancel": self.iesire,
			"red": self.anuleaza,
			"green": self.salveaza,
			"yellow": self.probeaza,
			"blue": self.instructiuni,
		}, -2)
		# randurile de citit (o singura alegere): starea cheii si contorul
		self.randCheie = ConfigSelection(choices=[("cheie", self._textCheie())], default="cheie")
		self.randContor = ConfigSelection(choices=[("contor", self._textContor())], default="contor")
		self.randContorEpg = ConfigSelection(choices=[("contor", self._textContorEpg())], default="contor")
		self.randContorTexte = ConfigSelection(choices=[("contor", self._textContorTexte())], default="contor")
		# randurile-buton: codul QR pentru telefon, cautarea serverului din casa
		self.randTelefon = ConfigSelection(choices=[("telefon", _("OK: cod QR"))], default="telefon")
		self.randCauta = ConfigSelection(choices=[("cauta", _("OK caută"))], default="cauta")
		self.randRezerve = ConfigSelection(choices=[("rezerve", u"")], default="rezerve")
		self.randProba = ConfigSelection(choices=[("proba", _("OK probează"))], default="proba")
		self.randInstructiuni = ConfigSelection(choices=[("instructiuni", _("OK le deschide"))], default="instructiuni")
		self._textProba = None
		self._textMesaj = None
		self._textLucrare = None		# rezultatul cautarii sau al configurarii pornite de aici
		self._cautareMea = False
		self._lucrareVazuta = None
		self._probaVazuta = None
		s = self.setari
		self._propriu = tuple(e for e in (_camp(s, c) for c in ("propriu_adresa", "propriu_metoda", "propriu_corp",
			"propriu_tip_corp", "propriu_antet", "propriu_raspuns", "propriu_cale")) if e is not None)
		# Groq si Cloudflare Workers: modelul (ales din lista propusa sau scris) si ID-ul contului Cloudflare
		self._fixe = tuple(e for e in (_camp(s, "model_groq"), _camp(s, "model_cloudflare"), _camp(s, "cont_cloudflare"))
			if e is not None)
		self._elemente = (s.pornit, s.serviciu, s.limba, s.afisare, s.tarziu, s.dvb, s.regiune, s.adresa_libre,
			s.adresa_openai, s.model_gemini, s.model_openai) + self._fixe + self._propriu + tuple(
			e for e in (_camp(s, "rezerve"), _camp(s, "bara"), _camp(s, "epg"), _camp(s, "citire"), _camp(s, "teletext"),
				_camp(s, "teletext_mod"), _camp(s, "hbbtv")) if e is not None)
		self._texte = (s.regiune, s.adresa_libre, s.adresa_openai, s.model_gemini, s.model_openai) + self._fixe + tuple(
			e for e in self._propriu if not hasattr(e, "choices"))
		C = _C()
		try:
			self._lucrareVazuta = C.configurator().stare().get("id") if C is not None else None
		except Exception:
			pass
		self._probaVazuta = self._semnProba()
		self._urmarite = [self.setari.serviciu, self.setari.pornit] + [e for e in (_camp(self.setari, c) for c in
			("propriu_metoda", "propriu_raspuns")) if e is not None]
		for e in self._urmarite:
			e.addNotifier(self._randuriSchimbate, initial_call=False)
		self._ceas = eTimer()
		self._ceas.callback.append(self._improspateaza)
		self._facLista()
		self["config"].onSelectionChanged.append(self._selectie)
		self.onLayoutFinish.append(self._pornit)
		getattr(self, "onLayoutFinish", []).append(self._cozileAjutorului)
		self.onClose.append(self._inchis)

	def _cozileAjutorului(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): ajutorul randului ales (aliniat sus, se
		schimba cu randul) are loc si pentru cozile ultimului rand, din cei 16 px liberi de sub el (la 130 % se taiau).
		La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			MT.locPentruCozi(self._etichetaMarita("ajutor"), 12)
		except Exception as e:
			print("[HdsTraducereSubtitrari] textul marit: %s" % e)

	def _etichetaMarita(self, nume):
		sursa = self.get(nume)
		for r in getattr(self, "renderer", ()):
			if getattr(r, "source", None) is sursa and getattr(r, "instance", None) is not None:
				return r.instance
		return getattr(sursa, "instance", None)

	# ------------------------------------------------------------------ randurile
	def _randuri(self):
		s = self.setari
		serv = s.serviciu.value
		# Serviciul: fiecare nume cu unde lucreaza, dupa adresele de acum (si cele scrise chiar acum in ecran)
		pune = getattr(T, "puneEticheteleServiciilor", None)
		if pune is not None:
			pune(s)
		lista = [getConfigListEntry(_("Configurează de pe telefon"), self.randTelefon),
			getConfigListEntry(_("Traducerea subtitrărilor"), s.pornit),
			getConfigListEntry(_("Serviciul"), s.serviciu)]
		if _camp(s, "rezerve") is not None:
			self._puneValoare(self.randRezerve, "rezerve", self._textRezerve())
			lista.append(getConfigListEntry(_("Serviciile de rezervă"), self.randRezerve))
		if serv in ("libre", "openai"):
			lista.append(getConfigListEntry(_("Caută în rețeaua de acasă"), self.randCauta))
		lista.append(getConfigListEntry(_("Valoarea antetului (cheia)") if serv == "propriu" else _("Cheia API"),
			self.randCheie))
		if serv == "azure":
			lista.append(getConfigListEntry(_("Regiunea (numai dacă resursa nu e Global)"), self._proxi(s.regiune, _("Global"))))
		if serv == "libre":
			lista.append(getConfigListEntry(_("Adresa serverului"), self._proxi(s.adresa_libre, _("lipsește (OK o scrie)"))))
		if serv == "openai":
			lista.append(getConfigListEntry(_("Adresa serverului"), self._proxi(s.adresa_openai, _("lipsește (OK o scrie)"))))
		if serv == "cloudflare" and _camp(s, "cont_cloudflare") is not None:
			lista.append(getConfigListEntry(_("ID-ul contului Cloudflare"), self._proxi(s.cont_cloudflare,
				_("lipsește (OK îl scrie)"))))
		if serv == "propriu" and self._propriu:
			for camp, eticheta in (("propriu_adresa", _("Adresa (șablon)")), ("propriu_metoda", _("Metoda")),
					("propriu_corp", _("Corpul cererii (șablon)")), ("propriu_tip_corp", _("Felul corpului")),
					("propriu_antet", _("Numele antetului (opțional)")), ("propriu_raspuns", _("Felul răspunsului")),
					("propriu_cale", _("Calea traducerii în răspuns"))):
				e = _camp(s, camp)
				metoda, raspuns = _camp(s, "propriu_metoda"), _camp(s, "propriu_raspuns")
				if e is None or (camp in ("propriu_corp", "propriu_tip_corp") and metoda is not None and metoda.value != "POST"):
					continue
				if camp == "propriu_cale" and raspuns is not None and raspuns.value != "json":
					continue
				lista.append(getConfigListEntry(eticheta, e))
		if serv == "gemini":
			lista.append(getConfigListEntry(_("Modelul"), self._proxi(s.model_gemini, _("lipsește (OK îl scrie)"))))
		if serv == "openai":
			lista.append(getConfigListEntry(_("Modelul"), self._proxi(s.model_openai, _("lipsește (OK îl scrie)"))))
		if serv in ("groq", "cloudflare") and _camp(s, "model_" + serv) is not None:
			lista.append(getConfigListEntry(_("Modelul"), self._proxi(_camp(s, "model_" + serv),
				_("lipsește (OK îl scrie)"))))
		lista.append(getConfigListEntry(_("Probează traducerea"), self.randProba))
		lista.append(getConfigListEntry(_("Instrucțiuni"), self.randInstructiuni))
		lista.append(getConfigListEntry(_("Limba traducerii"), s.limba))
		lista.append(getConfigListEntry(_("Afișarea"), s.afisare))
		lista.append(getConfigListEntry(_("Traducerea care întârzie"), s.tarziu))
		if _camp(s, "citire") is not None:
			lista.append(getConfigListEntry(_("Timpul de citire"), s.citire))
		lista.append(getConfigListEntry(_("Și subtitrările DVB (imagini)"), s.dvb))
		lista.append(getConfigListEntry(_("Ce s-a tradus"), self.randContor))
		if _camp(s, "bara") is not None:
			lista.append(getConfigListEntry(_("Tradu bara de jos"), s.bara))
		if _camp(s, "epg") is not None:
			lista.append(getConfigListEntry(_("Tradu EPG"), s.epg))
			lista.append(getConfigListEntry(_("Ce s-a tradus din EPG"), self.randContorEpg))
		if _camp(s, "teletext") is not None:
			lista.append(getConfigListEntry(_("Tradu teletextul"), s.teletext))
			lista.append(getConfigListEntry(_("Teletextul tradus"), s.teletext_mod))
		if _camp(s, "hbbtv") is not None:
			lista.append(getConfigListEntry(_("Tradu HbbTV"), s.hbbtv))
		if _camp(s, "teletext") is not None or _camp(s, "hbbtv") is not None:
			lista.append(getConfigListEntry(_("Ce s-a tradus din teletext și HbbTV"), self.randContorTexte))
		return lista

	def _facLista(self):
		curent = self["config"].getCurrent()
		lista = self._randuri()
		self["config"].list = lista
		self["config"].l.setList(lista)
		if curent is not None and len(curent) > 1:
			for i, rand in enumerate(lista):
				if rand[1] is curent[1]:
					self["config"].setCurrentIndex(i)
					break
		self._puneValoare(self.randCheie, "cheie", self._textCheie())
		self["ajutor"].setText(self._textAjutor())

	def _proxi(self, element, gol):
		"""randul care arata valoarea campului text `element` (`gol` cand e goala); OK pe el lucreaza pe element"""
		p = self._proxiuri.get(id(element))
		if p is None:
			p = ConfigSelection(choices=[("valoare", u"")], default="valoare")
			self._proxiuri[id(element)] = p
			self._realul[id(p)] = (element, gol)
		self._puneValoare(p, "valoare", (element.value or u"").strip() or gol)
		return p

	def _real(self, e):
		"""elementul de setare din spatele unui rand-proxy (sau randul insusi)"""
		x = self._realul.get(id(e)) if e is not None else None
		return x[0] if x is not None else e

	def _improspateazaProxiurile(self):
		for e, gol in list(self._realul.values()):
			self._proxi(e, gol)

	def _randuriSchimbate(self, element=None):
		# alt serviciu (sau pornit/oprit): rezultatul probei de dinainte nu mai e al lui
		self._textProba = None
		try:
			self["proba"].ascunde()
		except Exception:
			pass
		self._facLista()

	def _curent(self):
		rand = self["config"].getCurrent() if "config" in self else None
		return self._real(rand[1]) if rand is not None and len(rand) > 1 else None

	def _selectie(self):
		self._textMesaj = None
		self["ajutor"].setText(self._textAjutor())

	def _textCheie(self):
		serv = self.setari.serviciu.value
		are = T.chei().stare().get(serv)
		if are and serv in getattr(T, "CU_ADRESA", ()) and serv not in self._cheiPuse:
			try:
				if T.configuratia(self.setari).get("cheie_oprita"):
					return _("pusă pentru alt server (OK o pune din nou)")
			except Exception as e:
				print("[HdsTraducereSubtitrari] cheia: %s" % e)
		if are:
			return _("pusă (OK schimbă)")
		if "cheie" in T.CERE.get(serv, ()):
			if hasattr(T, "textCheiDinNou") and T.chei().deDinNou():
				return _("trebuie pusă din nou (OK o scrie)")
			return _("lipsește (OK o scrie)")
		return _("nu trebuie (numai dacă serverul cere)")

	@staticmethod
	def _textContor():
		c = T.instanta().stare()["contor"]
		if not c["pagini"] and not c["cereri"]:
			return _("nimic încă")
		return _("%d pagini, %d din memorie") % (c["pagini"], c["din_memorie"])

	@staticmethod
	def _textContorEpg():
		E = _E()
		if E is None:
			return u""
		st = E.instanta().stare()
		c = st["contor"]
		if not c["cereri"] and not c["deja_in_limba"]:
			return _("nimic încă") if st["pornit"] or st.get("bara_activ") else _("oprită")
		return _("%d texte, %d semne") % (c["bucati"], c["semne"])

	@staticmethod
	def _textContorTexte():
		X = _X()
		if X is None:
			return u""
		bucati = semne = cereri = 0
		pornit = False
		for fel in X.FELURI:
			st = X.stare(fel)
			pornit = pornit or st["pornit"]
			bucati += st["contor"]["bucati"]
			semne += st["contor"]["semne"]
			cereri += st["contor"]["cereri"]
		if not cereri:
			return _("nimic încă") if pornit else _("oprită")
		return _("%d texte, %d semne") % (bucati, semne)

	def _textDetaliiContorTexte(self):
		X = _X()
		if X is None:
			return u""
		parti = []
		for fel, nume in (("teletext", _("Teletextul")), ("hbbtv", u"HbbTV")):
			st = X.stare(fel)
			c = st["contor"]
			parti.append(_("%s: texte traduse %d (%d semne trimise, din cota serviciului), cereri %d, deja în limba ta %d, "
				"sărite %d.") % (nume, c["bucati"], c["semne"], c["cereri"], c["deja_in_limba"], c["sarite"]))
			if c["ultima_eroare"]:
				parti.append(_("Ultima eroare (%s): %s") % (c["ultima_eroare"]["ora"], c["ultima_eroare"]["text"]))
		parti.append(_("OK pune contorul la zero."))
		return u" ".join(parti)

	def _textDetaliiContorEpg(self):
		E = _E()
		if E is None:
			return u""
		st = E.instanta().stare()
		c = st["contor"]
		parti = [_("Ghidul: texte traduse %d (%d semne trimise, din cota serviciului), cereri %d, deja în limba ta %d, "
			"sărite %d.") % (c["bucati"], c["semne"], c["cereri"], c["deja_in_limba"], c["sarite"])]
		parti.append(_("Traduceri ținute minte: %d (%s).") % (st["memorie"], _("și pe stick sau disc") if st["pe_disc"]
			else _("numai până la repornire; cu un stick sau un disc se păstrează")))
		if c["ms_mediu"] is not None:
			parti.append(_("Timp mediu: %s.") % _secunde(c["ms_mediu"]))
		erori = sum(c["erori"].values())
		if erori:
			parti.append(_("Erori: %d.") % erori)
		if c["ultima_eroare"]:
			parti.append(_("Ultima eroare (%s): %s") % (c["ultima_eroare"]["ora"], c["ultima_eroare"]["text"]))
		parti.append(_("OK pune contorul la zero."))
		return u" ".join(parti)

	def _textDetaliiContor(self):
		s = T.instanta().stare()
		c = s["contor"]
		# intai serviciile oprite dupa refuzurile cheii: ce s-a intamplat si ce faci (aceleasi texte ca in web);
		# caseta are AJUTOR_RANDURI randuri, deci cel mai important sta primul
		parti = [u"%s %s" % (o["text"], o["ce_faci"]) for o in s.get("oprite") or []]
		if s.get("tv_stins_text"):
			# televizorul stins: de aceea contorul sta (0.6.2; numai aici si in web, nu ca fereastra)
			parti.append(s["tv_stins_text"])
		parti.append(_("Pagini: %d. Din memorie: %d. Traduse după afișare: %d. Sărite: %d. Cereri: %d.") % (c["pagini"],
			c["din_memorie"], c["dupa_afisare"], c["sarite"], c["cereri"]))
		if c.get("in_asteptare") is not None:
			parti.append(_("La timp, în așteptare (fără original pe ecran): %d.") % c["in_asteptare"])
		if c["ms_mediu"] is not None:
			parti.append(_("Timp mediu: %s.") % _secunde(c["ms_mediu"]))
		erori = sum(c["erori"].values())
		if erori:
			parti.append(_("Erori: %d.") % erori)
		if c["ultima_eroare"]:
			parti.append(_("Ultima eroare (%s): %s") % (c["ultima_eroare"]["ora"], c["ultima_eroare"]["text"]))
		if s["pauza_s"]:
			parti.append(_("Pauză după erori: încă %d s.") % s["pauza_s"])
		parti.append(_("OK pune contorul la zero."))
		return u" ".join(parti)

	def _textAjutor(self):
		e = self._curent()
		s = self.setari
		if self._textMesaj:
			return self._textMesaj
		if self._textProba is not None and e in (s.serviciu, self.randProba):
			return self._textProba
		lipsa = T.textCeLipseste()
		if e is self.randProba:
			return _("OK trimite o frază de probă serviciului ales. Răspunsul apare aici, iar originalul și traducerea se văd "
				"jos, ca subtitrările.") + ((u" " + lipsa) if lipsa else u"")
		if e is self.randInstructiuni:
			return _("OK deschide pașii pentru serviciul ales: contul, cheia gratuită, cota și ce se întâmplă la depășire.")
		if e is self.randTelefon:
			return _("OK: un cod QR pentru telefon. Pe telefon îți faci cheia și o lipești; receptorul o probează pe loc.")
		if e is s.regiune:
			return _("OK: alegi regiunea din listă. O găsești în portal, la resursa Translator: Overview › Location. "
				"Global pentru o resursă Global.") + ((u" " + lipsa) if lipsa else u"")
		if e is self.randRezerve:
			text = _("Serviciul principal: %s. Din OK îl poți schimba cu alt serviciu gata de folosit („Fă-l "
				"principal”).") % T.numeServiciu(s.serviciu.value) + u" "
			intreg = self._textRezerveIntreg()
			if intreg:
				# lista intreaga, imediat dupa principal (pe rand poate sta mai scurta, ca sa incapa): numele, unde
				# lucreaza, ce lipseste
				text += _("Rezervele, în ordine: %s.") % intreg + u" "
			text += _("Când serviciul principal nu răspunde (prea multe cereri, cota terminată, cheie refuzată, prea "
				"lent), receptorul trece singur la următorul din listă, fără mesaj. Fiecare serviciu cu cheia lui. OK "
				"schimbă lista.")
			for c in self._rezerve():
				try:
					ce = T.textCeLipseste(T.configuratia(s, serviciu=c))
				except Exception as eroare:
					print("[HdsTraducereSubtitrari] rezerva %s: %s" % (c, eroare))
					ce = u""
				if ce:
					text += u" " + ce
			return text
		if self._textLucrare and e in (self.randCauta, s.serviciu, s.adresa_libre, s.adresa_openai, s.model_openai):
			return self._textLucrare
		if e is self.randCauta:
			return _("OK caută singur serverul din casă (LibreTranslate sau Ollama) și îl probează. Adresa se poate "
				"scrie și de mână, mai jos.")
		if e in self._propriu:
			if e is _camp(s, "propriu_cale"):
				return _("Chei și indici despărțiți prin punct, de exemplu translatedText sau data.0.text; * ia toate "
					"elementele, lipite în ordine. Albastru: exemplul.")
			return _("Locurile {text}, {sursa} și {tinta} se înlocuiesc la fiecare cerere. Albastru: exemplul. Se "
				"scrie mai ușor din pagina web.") + ((u" " + lipsa) if lipsa else u"")
		if e is self.randContor:
			return self._textDetaliiContor()
		if e is self.randContorEpg:
			return self._textDetaliiContorEpg()
		if e is self.randContorTexte:
			return self._textDetaliiContorTexte()
		if e is not None and e is _camp(s, "teletext"):
			return _("Traduce paginile de teletext pe care le deschizi (tasta TEXT) în limba traducerii, cu aceleași "
				"servicii și chei. Pagina apare întâi în original, apoi tradusă. În teletext, AUDIO arată originalul "
				"paginii, iar MENU are aceleași alegeri. Consumă din cota serviciului, de aceea din fabrică e oprită; un "
				"text tradus o dată nu se mai cere.") + ((u" " + lipsa) if lipsa else u"")
		if e is not None and e is _camp(s, "teletext_mod"):
			return _("În pagină: rândurile traduse iau locul celor originale, în cele 40 de coloane ale paginii, cu "
				"aceleași culori; ce nu încape se taie cu „…”. Într-un panou: pagina originală, mai mică, în stânga, și "
				"traducerea întreagă în dreapta.")
		if e is not None and e is _camp(s, "hbbtv"):
			return _("Traduce textele văzute din aplicațiile HbbTV (tasta ROȘIE), ca „Traduce pagina” din browsere: "
				"numai textele de pe ecran, nu adresele, codul sau câmpurile de scris. Pagina apare întâi în original. "
				"Consumă din cota serviciului, de aceea din fabrică e oprită. Aplicațiile deschise pe https rămân "
				"deocamdată în original.") + ((u" " + lipsa) if lipsa else u"")
		if e is not None and e is _camp(s, "bara"):
			return _("Traduce titlurile emisiunii de acum și ale celei următoare de pe bara de jos, cu aceleași servicii și "
				"chei. Merge când traducerea subtitrărilor e pornită și folosește foarte puțin din cotă: fiecare titlu se "
				"cere o singură dată. INFO de pe bară arată textul original. Cu „Tradu EPG” pornită, bara se traduce "
				"oricum.") + ((u" " + lipsa) if lipsa else u"")
		if e is not None and e is _camp(s, "epg"):
			return _("Traduce automat titlurile și descrierile emisiunilor care sunt pe ecran (bara de jos, a doua bară, "
				"ghidul, detaliile emisiunii) în limba traducerii, cu aceleași servicii și chei. Consumă din cota "
				"serviciului, de aceea din fabrică e oprită. Textul deja în limba ta nu se trimite, iar o traducere ținută "
				"minte nu se mai cere. În detaliile emisiunii, INFO arată textul original.") + ((u" " + lipsa) if lipsa else u"")
		if e is self.randCheie:
			nota = T.notaCheie() if hasattr(T, "notaCheie") and s.serviciu.value not in self._cheiPuse else u""
			din_nou = T.textCheiDinNou() if hasattr(T, "textCheiDinNou") else u""
			if din_nou and "cheie" not in T.CERE.get(s.serviciu.value, ()):
				din_nou = _("Dacă foloseai o cheie pentru acest server, pune-o din nou.")
			return _("OK: scrii o cheie nouă sau o ștergi. Cheia se păstrează pe receptor, criptată, și nu se mai arată "
				"niciodată. Albastru: cum îți faci cheia gratuită.") + ((u" " + din_nou) if din_nou else u"") + (
				(u" " + lipsa) if lipsa else u"") + ((u" " + nota) if nota else u"")
		if e is not None and e is _camp(s, "cont_cloudflare"):
			text = _("OK deschide tastatura. ID-ul contului are 32 de litere și cifre: în panoul Cloudflare, la "
				"„Account ID”.")
			return text + ((u" " + lipsa) if lipsa else u"")
		if e is not None and e in (_camp(s, "model_groq"), _camp(s, "model_cloudflare")):
			implicit = getattr(T, "MODEL_GROQ_IMPLICIT" if e is _camp(s, "model_groq") else "MODEL_CLOUDFLARE_IMPLICIT", u"")
			return _("OK: alegi modelul din listă (sau îl scrii). Cel din fabrică: %s.") % implicit + (
				(u" " + lipsa) if lipsa else u"")
		if e in (s.regiune, s.adresa_libre, s.adresa_openai, s.model_gemini, s.model_openai):
			text = _("OK deschide tastatura.")
			if e is s.adresa_libre:
				text += u" " + _("De exemplu http://192.168.1.50:5000")
			elif e is s.adresa_openai:
				text += u" " + _("De exemplu http://192.168.1.50:11434 (Ollama) sau http://192.168.1.50:1234 (LM Studio).")
			elif e is s.regiune:
				text += u" " + _("De exemplu westeurope. Gol pentru o resursă Global.")
			elif e is s.model_openai:
				text += u" " + _("De exemplu gemma3:4b")
			return text + ((u" " + lipsa) if lipsa else u"")
		if e is s.dvb:
			return _("Subtitrările DVB sunt imagini: textul lor se citește întâi cu recunoașterea textului (OCR), apoi se "
				"traduce.")
		if e is s.tarziu:
			return _("Originalul nu apare înaintea traducerii: până vine ea, ecranul rămâne gol. „Se pune când vine”: "
				"traducerea se așteaptă. „Rămâne originalul”: după 2 secunde apare originalul și rămâne netradus. Un rând "
				"care nu se poate traduce (eroare, prea multe cereri) apare în original, cu %s în față.") % \
				T.textNetradus()
		if e is not None and e is _camp(s, "citire"):
			return _("Cât stă cel puțin pe ecran o subtitrare tradusă, după lungimea ei. Obișnuit: cam 17 semne pe "
				"secundă, între 1,5 și 7 secunde. Mai lung și Cel mai lung: mai mult timp pentru citit. Subtitrarea "
				"tradusă stă oricum cel puțin cât ar fi stat originalul, iar următoarea apare după ea.")
		if e is s.limba:
			return _("Implicit limba meniului. O subtitrare care e deja în limba aleasă nu se trimite.")
		if e is s.afisare:
			return _("Traducerea apare în locul originalului sau sub el, cu aspectul din «Aspectul subtitrărilor».") + \
				u" " + _("Sub original, traducerea se scrie cu galben deschis, ca s-o deosebești de original.")
		text = T.textConfidentialitate()
		if lipsa:
			text = lipsa + u" " + text
		if e is s.pornit:
			text = _("Traducere automată pentru teletext, subtitrările din fișiere și subtitrările DVB.") + u" " + text
		if e is s.serviciu:
			avertisment = T.instructiuni(s.serviciu.value).get("avertisment")
			if avertisment:
				text = avertisment + u" " + text
			eticheta = (getattr(T, "ETICHETE", None) or {}).get(s.serviciu.value)
			if eticheta:
				eticheta = _(eticheta)
				text = eticheta + (u" " if eticheta.endswith((u".", u"!", u"?")) else u". ") + text
		return text

	def _puneValoare(self, element, cheie, text):
		if element.getText() != text:
			element.setChoices([(cheie, text)], default=cheie)
			element.value = cheie
			for rand in self["config"].list:
				if rand[1] is element:
					self["config"].invalidate(rand)

	def _improspateaza(self):
		self._puneValoare(self.randContor, "contor", self._textContor())
		self._puneValoare(self.randContorEpg, "contor", self._textContorEpg())
		self._puneValoare(self.randContorTexte, "contor", self._textContorTexte())
		self._puneValoare(self.randCheie, "cheie", self._textCheie())
		if _camp(self.setari, "rezerve") is not None:
			self._puneValoare(self.randRezerve, "rezerve", self._textRezerve())
		self._improspateazaProxiurile()
		self._urmaresteLucrarile()
		text = self._textAjutor()
		if self["ajutor"].getText() != text:
			self["ajutor"].setText(text)

	# ------------------------------------------------------------------ tastele
	def ok(self):
		e = self._curent()
		s = self.setari
		if e is self.randContor:
			T.instanta().puneContorulLaZero()
			self._improspateaza()
			return
		if e is self.randContorEpg:
			E = _E()
			if E is not None:
				E.instanta().puneContorulLaZero()
			self._improspateaza()
			return
		if e is self.randContorTexte:
			X = _X()
			if X is not None:
				for fel in X.FELURI:
					X.instanta(fel).puneContorulLaZero()
			self._improspateaza()
			return
		if e is self.randCheie:
			self.session.openWithCallback(self._alegereCheie, ChoiceBox, title=_("Cheia API pentru %s") %
				T.numeServiciu(s.serviciu.value), list=[(_("Scrie cheia nouă"), "scrie"), (_("Șterge cheia"), "sterge")])
			return
		if e is self.randTelefon:
			self.session.open(HdsTraducereTelefon)
			return
		if e is self.randProba:
			self.probeaza()
			return
		if e is self.randInstructiuni:
			self.instructiuni()
			return
		if e is self.randCauta:
			self._cauta()
			return
		if e is self.randRezerve:
			self._alegeRezerve()
			return
		if e is s.regiune:
			self._alegeRegiunea()
			return
		if e is not None and e in (_camp(s, "model_groq"), _camp(s, "model_cloudflare")):
			self._alegeModelul(e)
			return
		if e in self._texte:
			titlu = self["config"].getCurrent()[0]

			def gata(text, element=e):
				if text is None:
					return
				text = text.strip()
				serv = {id(s.adresa_libre): "libre", id(s.adresa_openai): "openai"}.get(id(element))
				C = _C()
				if serv and text and C is not None:
					text, eroare = C.normalizeazaAdresa(serv, text)
					if eroare:
						self._mesaj(eroare)
						return
				if element is _camp(s, "cont_cloudflare") and text:
					text = text.lower()
					if not T.contCloudflareBun(text):
						self._mesaj(_("Pentru %s lipsește: %s.") % (T.numeServiciu("cloudflare"),
							_("un ID de cont Cloudflare bun (32 de litere și cifre, de la Account ID)")))
						return
				if element is _camp(s, "propriu_adresa") and text and hasattr(T, "clasaAdresa") and (
						T.clasaAdresa(text) == T.RECEPTOR):
					self._mesaj(T.textMotivAdresa("adresa_receptor", text))
					return
				if element is _camp(s, "propriu_corp"):
					text = T.curataCorp(text)[:T.MAX_CORP_PROPRIU]
				elif element is _camp(s, "propriu_antet") and text and not T.numeAntetBun(text):
					self._mesaj(_t_lipsa("un nume de antet bun (litere, cifre și - _ ., de exemplu Authorization)"))
					return
				elif element is _camp(s, "propriu_cale") and text and not T.caleBuna(text):
					self._mesaj(_t_lipsa("calea traducerii în răspunsul JSON (chei și numere despărțite prin punct, de "
						"exemplu translatedText)"))
					return
				element.value = text
				self._facLista()
			self.session.openWithCallback(gata, VirtualKeyBoard, title=titlu, text=e.value)
			return
		# celelalte: lista alegerilor (ca in ConfigListScreen)
		try:
			ConfigListScreen.keyOK(self)
		except Exception:
			pass

	def _alegereCheie(self, alegere):
		if not alegere:
			return
		serv = self.setari.serviciu.value
		if alegere[1] == "sterge":
			ok, mesaj = T.chei().schimba(serv, None)
			if ok:
				# stergerea e aleasa anume: la anulare nu se mai pune nimic la loc
				self._cheiPuse.discard(serv)
				self._cheiVechi.pop(serv, None)
			self._mesaj(mesaj)
			return

		def gata(text):
			if text is None or not text.strip():
				return
			if serv in getattr(T, "CU_ADRESA", ()) and serv not in self._cheiVechi:
				try:
					self._cheiVechi[serv] = (T.chei().citeste().get(serv), T.chei().legaturi().get(serv))
				except Exception as e:
					print("[HdsTraducereSubtitrari] cheia de dinainte: %s" % e.__class__.__name__)
			ok, mesaj = T.chei().schimba(serv, text)
			if ok and serv in getattr(T, "CU_ADRESA", ()):
				self._cheiPuse.add(serv)		# legata la Verde de adresa salvata atunci
			self._mesaj(mesaj)
		self.session.openWithCallback(gata, VirtualKeyBoard, title=_("Cheia API pentru %s") % T.numeServiciu(serv),
			text=u"")

	def _mesaj(self, text):
		self._facLista()
		self._textMesaj = text		# ramane sub lista pana la alt rand (ceasul de 2 s nu-l sterge)
		self["ajutor"].setText(text)

	def probeaza(self):
		cfg = T.configuratia()
		self._textProba = _("Se probează traducerea cu %s...") % T.numeServiciu(cfg["serviciu"])
		self._textMesaj = None
		if self._curent() is not self.randProba:
			for i, rand in enumerate(self["config"].list):
				if rand[1] is self.setari.serviciu:
					self["config"].setCurrentIndex(i)
					break
		self["ajutor"].setText(self._textProba)
		self["proba"].ascunde()
		T.instanta().proba(self._gataProba, cfg)

	def _gataProba(self, rez):
		if rez.get("stare") == "ok":
			timp = _secunde(rez["ms"]) if rez.get("ms") is not None else u"?"
			self._textProba = _("Proba a mers (%s, %s): %s") % (rez.get("serviciu", u""), timp, rez["traducere"])
			if rez.get("ms") is not None and rez["ms"] > LENT_MS:
				self._textProba += u" " + _("Serverul e prea lent pentru subtitrări la timp. Alege un serviciu din "
					"internet (Gemini, gratuit, fără card) sau un model mai mic.")
			self["proba"].arataTraducerea(rez["original"], rez["traducere"])
		else:
			self._textProba = _("Proba nu a mers: %s") % rez.get("traducere", u"")
		if self._curent() in (self.setari.serviciu, self.randProba):
			self["ajutor"].setText(self._textProba)

	def instructiuni(self):
		self.session.open(HdsTraducereInstructiuni, self.setari.serviciu.value)

	# ------------------------------------------------------------------ regiunea Azure (din lista, nu de mana)
	def _alegeRegiunea(self):
		regiuni = getattr(T, "REGIUNI_AZURE", None) or REGIUNI_AZURE_REZERVA
		alegeri = []
		for r in regiuni:
			cod, nume = (r[0], r[1]) if isinstance(r, (list, tuple)) else (r, r)
			alegeri.append(((u"%s (%s)" % (nume, cod)) if cod else (nume or _("Global")), cod))
		actuala = self.setari.regiune.value or u""
		if actuala and actuala not in [a[1] for a in alegeri]:
			alegeri.append((actuala, actuala))		# o valoare veche, scrisa de mana, ramane aleasa

		def gata(alegere):
			if alegere is not None:
				self.setari.regiune.value = alegere[1]
				self._facLista()
		self.session.openWithCallback(gata, ChoiceBox, title=_("Regiunea resursei Azure: o găsești în portal, la "
			"resursa Translator, Overview › Location."), list=alegeri)

	# ------------------------------------------------------------------ modelul Groq / Cloudflare Workers (din lista)
	def _alegeModelul(self, element):
		"""modelele propuse (T.MODELE_GROQ / T.MODELE_CLOUDFLARE, primul e cel din fabrica), valoarea de acum daca e
		alta, si randul Scrie alt model (tastatura)"""
		s = self.setari
		groq = element is _camp(s, "model_groq")
		propuse = list(getattr(T, "MODELE_GROQ" if groq else "MODELE_CLOUDFLARE", ()) or ())
		actual = (element.value or u"").strip()
		alegeri = [(m, m) for m in propuse]
		if actual and actual not in propuse:
			alegeri.append((actual, actual))
		alegeri.append((_("Scrie alt model"), None))

		def scris(text):
			if text is not None and text.strip():
				element.value = text.strip()
				self._facLista()

		def gata(alegere):
			if alegere is None:
				return
			if alegere[1] is None:
				self.session.openWithCallback(scris, VirtualKeyBoard, title=_("Modelul"), text=actual)
				return
			element.value = alegere[1]
			self._facLista()
		self.session.openWithCallback(gata, ChoiceBox, title=_("Modelul"), list=alegeri)

	# ------------------------------------------------------------------ serviciile de rezerva (lista in ordine)
	def _rezerve(self):
		"""codurile din config.hds_traducere.rezerve, in ordine, fara principal si fara dubluri"""
		s = self.setari
		citeste = getattr(T, "rezerve", None)
		if citeste is not None:
			try:
				return [c for c in citeste(s) if c != s.serviciu.value]
			except Exception as e:
				print("[HdsTraducereSubtitrari] rezervele: %s" % e)
		e = _camp(s, "rezerve")
		lista = []
		for c in (e.value if e is not None else u"").split(","):
			c = c.strip()
			if c in T.SERVICII and c != s.serviciu.value and c not in lista:
				lista.append(c)
		return lista

	def _scrieRezerve(self, lista):
		pune = getattr(T, "puneRezerve", None)
		if pune is not None:
			ok, mesaj = pune(",".join(lista), self.setari)		# verificata in modul; salvata cu Verde
			if not ok:
				self._mesaj(mesaj)
				return
		else:
			e = _camp(self.setari, "rezerve")
			if e is not None:
				e.value = ",".join(lista)
		self._facLista()

	def _partiRezerve(self):
		"""[(numele scurt, unde lucreaza, ce lipseste sau "")] pentru fiecare rezerva, in ordine"""
		scurt = {"cheie": _("fără cheie"), "adresa": _("fără adresă"), "model": _("fără model")}
		parti = []
		for c in self._rezerve():
			nume = T.numeServiciu(c).split(u" (")[0]		# fara (de ex. Ollama): valoarea incape pe rand
			loc = T.etichetaLoc(c, self.setari) if hasattr(T, "etichetaLoc") else u""
			try:
				lipsa = T.ceLipseste(T.configuratia(self.setari, serviciu=c))
			except Exception as e:
				print("[HdsTraducereSubtitrari] rezerva %s: %s" % (c, e))
				lipsa = []
			parti.append((nume, loc, scurt.get(lipsa[0], _("de completat")) if lipsa else u""))
		return parti

	@staticmethod
	def _cuParanteza(nume, *note):
		note = [x for x in note if x]
		return (u"%s (%s)" % (nume, u", ".join(note))) if note else nume

	def _textRezerveIntreg(self):
		"""lista intreaga a rezervelor: numele, unde lucreaza si ce lipseste (ajutorul randului)"""
		return u" › ".join(self._cuParanteza(n, loc, lipsa) for n, loc, lipsa in self._partiRezerve())

	def _textRezerve(self):
		"""valoarea randului Serviciile de rezerva: intreaga (numele, unde lucreaza, ce lipseste) cand incape pe rand,
		altfel mai scurta (fara unde lucreaza, apoi numai numele, apoi primul nume si ...), ca un rand nealeas sa nu se
		vada taiat; lista intreaga sta in ajutorul randului"""
		parti = self._partiRezerve()
		if not parti:
			return _("niciunul (OK adaugă)")
		variante = [
			u" › ".join(self._cuParanteza(n, loc, lipsa) for n, loc, lipsa in parti),
			u" › ".join(self._cuParanteza(n, lipsa) for n, loc, lipsa in parti),
			u" › ".join(n for n, loc, lipsa in parti),
		]
		if len(parti) > 1:
			variante.append(parti[0][0] + u" › …")
		return self._valoareCareIncape(_("Serviciile de rezervă"), *variante)

	def _valoareCareIncape(self, eticheta, *variante):
		"""Valoarea unui rand al listei: prima dintre variante (de la cea mai bogata la cea mai scurta) care incape
		intreaga dupa eticheta, cu fonturile listei din skin si marimea textului de acum, masurata cu
		Components/HdsLatimeText cum o aseaza lib/gui/elistboxcontent.cpp (valueStart: locul valorii incepe la 200 px
		sau la 20 px dupa eticheta, cel mult la doua treimi din rand; bara de derulare ia cel mult 27 px), ca un rand
		nealeas sa nu se vada taiat. Cand nici cea mai scurta nu incape, sau lista nu se poate masura inca, ramane cea
		mai scurta: randul ales deruleaza (lib/gui/elabel.h). O singura varianta se intoarce ca atare."""
		if not variante:
			return u""
		if len(variante) == 1:
			return variante[0]
		try:
			from Components import HdsLatimeText as LT
			from Components import HdsMarireText as MT
			lista = self["config"]
			latime = lista.instance.size().width() if lista.instance is not None else 0
			atribute = dict(lista.skinAttributes or ())
			procent = MT.procent()

			def marime(nume, implicit):
				try:
					m = int(str(atribute.get(nume, "")).split(";")[1])
				except (IndexError, ValueError):
					m = implicit
				return m if procent == 100 else max(1, m * procent // 100)
			f_eticheta, f_valoare = marime("font", 26), marime("secondfont", 24)
			rand = latime - 27
			if rand <= 0:
				return variante[-1]
			inceput = max(200, min(LT.latime(eticheta, "HdsRegular", f_eticheta) + 20, rand * 2 // 3))
			loc = rand - inceput - 4
			for v in variante:
				if LT.latime(v, "HdsRegular", f_valoare) <= loc:
					return v
		except Exception as e:
			print("[HdsTraducereSubtitrari] latimea valorii: %s" % e)
		return variante[-1]

	def _alegeRezerve(self):
		"""lista in ordine: adauga un serviciu la sfarsit, muta unul mai sus, scoate unul; „Fă-l principal” pentru un
		serviciu gata (T.punePrincipal); Verde salveaza ca de obicei. Numele cu unde lucreaza (T.numeCuLoc)."""
		lista = self._rezerve()
		alegeri = []
		nume = (lambda c: T.numeCuLoc(c, self.setari)) if hasattr(T, "numeCuLoc") else T.numeServiciu
		pregatite = getattr(T, "serviciiGata", None)
		if pregatite is not None and getattr(T, "punePrincipal", None) is not None:
			try:
				for c in pregatite(self.setari):
					alegeri.append((_("Fă-l principal: %s") % nume(c), ("principal", c)))
			except Exception as e:
				print("[HdsTraducereSubtitrari] serviciile gata: %s" % e)
		for c in T.SERVICII:
			if c != self.setari.serviciu.value and c not in lista:
				alegeri.append((_("Adaugă: %s") % nume(c), ("adauga", c)))
		for i, c in enumerate(lista):
			if i:
				alegeri.append((_("Mută mai sus: %s") % nume(c), ("sus", c)))
			alegeri.append((_("Scoate: %s") % nume(c), ("scoate", c)))

		def gata(alegere):
			if not alegere:
				return
			fel, c = alegere[1]
			if fel == "principal":
				ok, mesaj = T.punePrincipal(c, self.setari)		# salvat cu Verde; Rosu il intoarce
				self._mesaj(mesaj)
				return
			noua = list(lista)
			if fel == "adauga":
				noua.append(c)
			elif fel == "scoate" and c in noua:
				noua.remove(c)
			elif fel == "sus" and c in noua:
				i = noua.index(c)
				if i:
					noua[i - 1], noua[i] = noua[i], noua[i - 1]
			self._scrieRezerve(noua)
		self.session.openWithCallback(gata, ChoiceBox, title=_("Serviciile de rezervă: când serviciul principal nu "
			"răspunde, receptorul trece singur la următorul din listă."), list=alegeri)

	# ------------------------------------------------------------------ cautarea si configurarea (HdsConfigurareTraducere)
	def _cauta(self):
		C = _C()
		if C is None:
			self._mesaj(_("Căutarea nu e în această imagine."))
			return
		ok, mesaj = C.cautare().porneste()
		self._cautareMea = bool(ok)
		# mesajele modulului vin traduse (HdsConfigurareTraducere, _t); pornirea cautarii are textul ei aici
		self._textLucrare = _("Se caută în rețeaua de acasă...") if ok else (mesaj or u"")
		self["ajutor"].setText(self._textLucrare)

	def _gataCautarea(self, st):
		"""cautarea pornita de aici s-a terminat: lista gasitelor, sau de ce nu s-a gasit nimic"""
		self._cautareMea = False
		gasite = st.get("gasite") or []
		if not gasite:
			ajutor = st.get("ajutor") or []
			if not isinstance(ajutor, (list, tuple)):
				ajutor = [ajutor]
			self._textLucrare = u" ".join([_("Nu am găsit niciun server în rețeaua de acasă.")] + [_(a) for a in ajutor if a])
			self["ajutor"].setText(self._textLucrare)
			return
		lista = []
		for g in gasite:
			if g.get("fel") == "ollama":
				text = _("Ollama la %s, modelul %s") % (g.get("adresa", u""), g.get("model_ales") or u"?")
			else:
				text = _("LibreTranslate la %s") % g.get("adresa", u"")
			lista.append((text, g))
		self._textLucrare = _("Am găsit %d. Alege serverul.") % len(gasite)
		self["ajutor"].setText(self._textLucrare)
		self.session.openWithCallback(self._alegereServer, ChoiceBox, title=_("Caută în rețeaua de acasă"), list=lista)

	def _alegereServer(self, alegere):
		if not alegere:
			return
		g = alegere[1]
		C = _C()
		serv = "openai" if g.get("fel") == "ollama" else "libre"
		ok, mesaj = C.configurator().porneste_server(serv, g.get("adresa", u""), g.get("model_ales") or u"")
		self._textLucrare = _("Se probează serverul...") if ok else (mesaj or u"")
		self["ajutor"].setText(self._textLucrare)

	def _semnProba(self):
		p = T.instanta().ultima_proba or {}
		return (p.get("ora"), p.get("stare"), p.get("traducere"))

	def _urmaresteLucrarile(self):
		"""cautarea pornita de aici, lucrarea configuratorului (de aici sau de pe telefon) si proba facuta din web:
		ecranul le arata singur, la ceasul de 2 s"""
		C = _C()
		if C is not None:
			try:
				if self._cautareMea:
					st = C.cautare().stare()
					if st.get("stare") == "gata":
						self._gataCautarea(st)
					elif st.get("stare") == "lucru":
						self._textLucrare = _("Se caută în rețeaua de acasă... %d din %d") % (st.get("progres") or 0,
							st.get("total") or 0)
				st = C.configurator().stare()
				if st.get("id") != self._lucrareVazuta and st.get("stare") in ("lucru", "ok", "eroare", "regiune"):
					self._textLucrare = textRezultat(st)
					if st.get("stare") != "lucru":
						self._lucrareVazuta = st.get("id")
						self._facLista()		# serviciul, adresa, modelul si cheia pot fi altele acum
			except Exception as e:
				print("[HdsTraducereSubtitrari] cautarea / configurarea: %s" % e)
		semn = self._semnProba()
		if semn != self._probaVazuta:
			self._probaVazuta = semn
			p = T.instanta().ultima_proba or {}
			if p.get("stare") == "ok" and p.get("original") and p.get("traducere"):
				self["proba"].arataTraducerea(p["original"], p["traducere"])

	def salveaza(self):
		for e in self._elemente:
			e.save()
		configfile.save()
		self._legaCheile()
		self._cheiVechi.clear()
		self.close()

	def _schimbat(self):
		"""o setare schimbata si nesalvata, sau o cheie scrisa aici pentru un server cu adresa (se leaga la Verde)"""
		return bool(self._cheiPuse) or any(e.isChanged() for e in self._elemente)

	def iesire(self):
		"""EXIT: fara schimbari inchide; altfel intreaba (OK alege), ca setarile sa se poata salva si fara Verde"""
		if not self._schimbat():
			self.anuleaza()
			return

		def gata(alegere):
			if alegere is None or alegere[1] == "ramai":
				return
			if alegere[1] == "salveaza":
				self.salveaza()
			else:
				self.anuleaza()
		self.session.openWithCallback(gata, ChoiceBox, title=_("Ai schimbat setările traducerii. Le salvezi?"), list=[
			(_("Da, salvează"), "salveaza"), (_("Nu, lasă cum era"), "renunta"), (_("Înapoi la alegeri"), "ramai")])

	def anuleaza(self):
		for e in self._elemente:
			e.cancel()
		self._cheileLaLoc()
		self._cheiPuse.clear()
		self._cheiVechi.clear()
		self.close()

	def _cheileLaLoc(self):
		"""la anulare: cheia scrisa aici ramane numai daca e legata chiar de adresa care ramane salvata; altfel se pun
		la loc cheia si legatura de dinainte (sau nicio cheie), deci cheia veche pleaca tot numai spre gazda ei"""
		for serv in sorted(self._cheiPuse):
			if serv not in self._cheiVechi:
				continue
			veche, legatura = self._cheiVechi[serv]
			try:
				if T.chei().legaturi().get(serv) == T.origine(T.adresaServiciului(serv, self.setari)):
					continue
				if veche:
					T.chei().schimba(serv, veche, adresa=legatura or u"")
				else:
					T.chei().schimba(serv, None)
			except Exception as e:
				print("[HdsTraducereSubtitrari] cheia %s la anulare: %s" % (serv, e.__class__.__name__))

	def _legaCheile(self):
		"""la Verde: cheile scrise in acest ecran se leaga de adresa salvata odata cu ele (scrise aici, de om, la
		televizor, deci ordinea randurilor nu conteaza; din web cheia se leaga de adresa salvata cand e pusa)"""
		lega = getattr(T.chei(), "legaDeAdresa", None)
		for serv in sorted(self._cheiPuse):
			try:
				if lega is not None:
					lega(serv)
			except Exception as e:
				print("[HdsTraducereSubtitrari] cheia %s: %s" % (serv, e))
		self._cheiPuse.clear()

	# ------------------------------------------------------------------ deschis, inchis
	def _pornit(self):
		self._ceas.start(CONTOR_MS, False)
		if _camp(self.setari, "rezerve") is not None:
			# valoarea randului rezervelor se potriveste dupa latimea listei, care se stie abia acum
			self._puneValoare(self.randRezerve, "rezerve", self._textRezerve())
		lista = self["config"].instance
		if lista is not None:
			try:
				lista.moveSelectionTo(self["config"].getCurrentIndex())		# bara si latimea randurilor de acum
				lista.invalidate()
			except Exception as e:
				print("[HdsTraducereSubtitrari] lista: %s" % e)

	def _inchis(self):
		self._ceas.stop()
		try:
			self["proba"].ascunde()
		except Exception:
			pass
		for e in self._urmarite:
			if self._randuriSchimbate in e.notifiers:
				e.notifiers.remove(self._randuriSchimbate)


def _secunde(ms):
	return (u"%.2f s" % (ms / 1000.0)).replace(".", ",")
