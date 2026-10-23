# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ecrane.py: ecranele descarcarii subtitrarilor de pe internet pentru filmul care merge. Din 0.3.2 fac parte din imagine
# (pachetul enigma2-hdsatelit, Components/HdsSubtitrariInternet), nu mai sunt plugin separat (ce se
# poate pune direct in imagine nu sta in lista de pluginuri); inainte erau pluginul HdsSubtitleDownloader.
# Fara descriptori de plugin:
# - setarile, "Descărcare subtitrări", se deschid din meniul audio ("Audio & Sound Tracks"), langa celelalte intrari ale
#   subtitrarilor (data/menu.xml, entryID hds_descarcare_subtitrari, mereu in imagine; Screens/HdsDescarcareSubtitrari.py
#   numeste ecranul);
# - cautarea, "Caută subtitrări pe internet", e un rand al ecranului tastei SUB (Screens/AudioSelection.py, numai pe
#   pagina subtitrarilor si numai la un film din fisier), care cheama cautaPeInternet() de mai jos;
# - in web: /descarcare-subtitrari (HdsWebControl/descarcare_subtitrari_web.py).
#
# Sursele: numai servicii cu API oficial si cu permisiune pentru aplicatii, fiecare un modul in surse/ care se poate
# scoate repede: OpenSubtitles.com (cheia aplicatiei HD Satelit si contul fiecarui om), subs.ro si SubDL (cheia API a
# fiecarui om). Subtitrarea se cauta la cererea omului, pentru fisierul lui, si se salveaza langa film; nu trece prin
# serverele HD Satelit si nu se tine nicaieri altundeva. Citirea ei o face imaginea (Components/HdsSubtitrariFilm.py).
#
# Ecranele (numai sagetile si OK):
# - "Caută subtitrări pe internet" (randul din ecranul tastei SUB, numai la un film din fisier): randurile
#   "Caută din nou", "Textul căutat" (OK = tastatura), "Limbile" (stanga/dreapta), "Conturi" (OK = setarile), apoi
#   rezultatele pe doua linii; OK pe un rezultat il descarca, il pune langa film si il porneste;
# - "Descărcare subtitrări" (meniul, vezi mai sus): conturile si cheile (OK = tastatura; valorile secrete nu se arata,
#   se vede numai "scrisă"), "Verifică sursele", "Șterge contul OpenSubtitles", textele despre reguli.
# Conturile stau criptate in conturi.py; cautarea si descarcarea in lucru.py (aceleasi si pentru pagina web).

import threading

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import ConfigElement, getConfigListEntry, KEY_LEFT, KEY_RIGHT, KEY_OK
from Components.Label import Label
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from . import lucru as LU
from . import limbi as LB
from .conturi import Conturi
from .surse import EroareSursa, module

def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am: --keyword=N_): textele din tabele se traduc abia la afisare, cu _t()."""
	return text


NUME_PLUGIN = N_("Descărcare subtitrări")


def _t(text):
	return _(text)


# ------------------------------------------------------------------ setarile (conturile si cheile)

class _Camp(ConfigElement):
	"""Un rand de setare care arata un text (valoarea nu se arata cand e secreta); OK il schimba (ecranul)."""

	def __init__(self, cheie, secret, text):
		ConfigElement.__init__(self)
		self.cheie = cheie
		self.secret = secret
		self._value = text
		self.default = text
		self.save_disabled = True

	def handleKey(self, key):
		pass

	def getText(self):
		return self._value

	def getMulti(self, selected):
		return ("text", self._value)


# (cheia din conturi, eticheta, secret)
CAMPURI = (
	("os_utilizator", N_("OpenSubtitles: nume de utilizator"), False),
	("os_parola", N_("OpenSubtitles: parola"), True),
	("os_cheie_aplicatie", N_("OpenSubtitles: cheia aplicației"), True),
	("subsro_cheie", N_("subs.ro: cheia API"), True),
	("subdl_cheie", N_("SubDL: cheia API"), True),
)

DESCRIERI = {
	"os_utilizator": N_("Numele de utilizator al contului tău OpenSubtitles.com (nu adresa de e-mail). Un cont gratuit dă 20 de descărcări pe zi."),
	"os_parola": N_("Folosește pentru OpenSubtitles o parolă pe care nu o mai folosești în altă parte. Parola stă criptată pe receptor și nu se mai arată."),
	"os_cheie_aplicatie": N_("Cheia aplicației HD Satelit la OpenSubtitles. O dă HD Satelit; nu e cheia contului tău."),
	"subsro_cheie": N_("Cheia API din profilul tău de pe subs.ro. Fiecare cheie are o cotă de cereri pe zi."),
	"subdl_cheie": N_("Cheia API din panoul contului tău SubDL. Parola contului SubDL nu se cere."),
	"verifica": N_("Încearcă fiecare sursă cu datele scrise și spune dacă merge și câte descărcări mai sunt azi."),
	"sterge": N_("Șterge numele, parola și autentificarea OpenSubtitles de pe receptor."),
}

NOTA = N_("Subtitrările se caută la cererea ta, pentru fișierul tău, și se salvează lângă film; nu "
	"trec prin serverele HD Satelit. Răspunzi de ce descarci. Pe contul gratuit, OpenSubtitles poate pune o reclamă "
	"a lor la începutul sau la sfârșitul subtitrării. Subtitrări de la OpenSubtitles.com, subs.ro și SubDL.")


class HdsDescarcareSetari(Screen, ConfigListScreen):
	"""Conturile si cheile surselor; OK pe un rand deschide tastatura de pe ecran."""

	skin = """
	<screen name="HdsDescarcareSetari" position="center,center" size="1240,900" title="Descărcare subtitrări">
		<widget name="config" position="30,20" size="1180,378" itemHeight="54" scrollbarMode="showOnDemand" />
		<widget name="description" position="30,410" size="1180,176" font="Regular;28" />
		<widget name="footnote" position="30,600" size="1180,220" font="Regular;24" />
		<widget name="key_red" position="30,840" size="300,50" backgroundColor="#009f1313" font="Regular;28" halign="center" valign="center" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_t(NUME_PLUGIN))
		self.conturi = Conturi()
		self["description"] = Label("")
		self["footnote"] = Label(_t(NOTA))
		self["key_red"] = Label(_t("Închide"))
		ConfigListScreen.__init__(self, [], session=session)
		self["actiuni"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"red": self.close,
		}, -2)
		self._verificare = None
		self._rezultatVerificare = None
		self._ceas = None
		self.onClose.append(self._opresteCeasul)
		self["config"].onSelectionChanged.append(self._descriere)
		self._faLista()

	def _opresteCeasul(self):
		if self._ceas is not None:
			self._ceas.stop()

	def _faLista(self):
		stare = self.conturi.stare()
		lista = []
		for cheie, eticheta, secret in CAMPURI:
			if secret:
				text = _t("scrisă") if stare.get(cheie) else _t("nescrisă")
			else:
				text = stare.get("os_utilizator_text") or _t("nescris")
			lista.append(getConfigListEntry(_t(eticheta), _Camp(cheie, secret, text)))
		lista.append(getConfigListEntry(_t("Verifică sursele"), _Camp("verifica", False, "")))
		lista.append(getConfigListEntry(_t("Șterge contul OpenSubtitles"), _Camp("sterge", False, "")))
		index = self["config"].getCurrentIndex() if self["config"].list else 0
		self["config"].list = lista
		self["config"].l.setList(lista)
		self["config"].setCurrentIndex(min(index, len(lista) - 1))
		self._descriere()

	def _descriere(self):
		c = self["config"].getCurrent()
		if c is not None:
			self["description"].setText(_t(DESCRIERI.get(c[1].cheie, "")))

	def ok(self):
		c = self["config"].getCurrent()
		if c is None:
			return
		cheie = c[1].cheie
		if cheie == "verifica":
			self._verifica()
		elif cheie == "sterge":
			self.session.openWithCallback(self._stergeConfirmat, MessageBox,
				_t("Ștergi contul OpenSubtitles de pe receptor?"), MessageBox.TYPE_YESNO, default=False)
		else:
			from Screens.VirtualKeyBoard import VirtualKeyBoard
			text = "" if c[1].secret else self.conturi.stare().get("os_utilizator_text", "")
			self.session.openWithCallback(lambda valoare: self._scris(cheie, valoare), VirtualKeyBoard,
				title=c[0], text=text)

	def _scris(self, cheie, valoare):
		if valoare is None:
			return
		valoare = valoare.strip()
		if not valoare:
			return
		if cheie.startswith("os_"):
			self._iesireOpenSubtitles()
		if not self.conturi.schimba(**{cheie: valoare}):
			self.session.open(MessageBox, _t("Datele nu s-au putut scrie pe receptor."), MessageBox.TYPE_ERROR, timeout=8)
		self._faLista()

	def _iesireOpenSubtitles(self):
		try:
			from .surse import opensubtitles
			date = self.conturi.citeste()
			fir = threading.Thread(target=opensubtitles.iesire, args=(date,), name="HdsSubtitrariInternet")
			fir.daemon = True
			fir.start()
		except Exception as e:
			print("[HdsSubtitrariInternet] iesirea din OpenSubtitles: %s" % e.__class__.__name__)

	def _stergeConfirmat(self, da):
		if not da:
			return
		self._iesireOpenSubtitles()
		self.conturi.schimba(os_utilizator=None, os_parola=None)
		self._faLista()

	def _verifica(self):
		if self._verificare is not None:
			return
		self["description"].setText(_t("Se verifică sursele..."))

		def lucreaza():
			# citirea conturilor (fisier, HMAC) si cererile, toate pe fir
			self._rezultatVerificare = "\n".join(LU.verificaSurse(self.conturi.citeste(), module()))
		self._rezultatVerificare = None
		self._verificare = threading.Thread(target=lucreaza)
		self._verificare.daemon = True
		self._verificare.start()
		from enigma import eTimer
		self._ceas = eTimer()
		self._ceas.callback.append(self._bateVerificare)
		self._ceas.start(300, False)

	def _bateVerificare(self):
		if self._rezultatVerificare is None:
			return
		self._ceas.stop()
		self._verificare = None
		self["description"].setText(self._rezultatVerificare)


# ------------------------------------------------------------------ cautarea si descarcarea

# alegerile de limbi (stanga / dreapta pe randul „Limbile”): preferintele receptorului, apoi cateva
def _alegeriLimbi():
	implicite = LB.implicite()
	alegeri = [implicite]
	for c in (["ron"], ["eng"], ["ron", "eng"], ["fra"], ["deu"], ["ita"], ["spa"], ["hun"]):
		if c != implicite and c not in alegeri:
			alegeri.append(c)
	return alegeri


class HdsDescarcareCautare(Screen):
	"""Cautarea pentru filmul care merge si rezultatele; OK pe un rezultat il descarca si il porneste."""

	skin = """
	<screen name="HdsDescarcareCautare" position="center,center" size="1240,900" title="Caută subtitrări pe internet">
		<widget source="list" render="Listbox" position="30,20" size="1180,616" scrollbarMode="showOnDemand">
			<convert type="TemplatedMultiContent">{"template": [MultiContentEntryText(pos=(10, 4), size=(1130, 44), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=0), MultiContentEntryText(pos=(10, 48), size=(1130, 34), font=1, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=1)], "fonts": [gFont("Regular", 30), gFont("Regular", 24)], "itemHeight": 88}</convert>
		</widget>
		<widget name="description" position="30,650" size="1180,170" font="Regular;28" />
		<widget name="key_red" position="30,840" size="300,50" backgroundColor="#009f1313" font="Regular;28" halign="center" valign="center" />
		<widget name="key_yellow" position="350,840" size="300,50" backgroundColor="#00a08020" font="Regular;28" halign="center" valign="center" />
	</screen>"""

	RAND_CAUTA, RAND_TEXT, RAND_LIMBI, RAND_CONTURI = range(4)
	PRIMUL_REZULTAT = 4
	MAX_NUME = 56

	def __init__(self, session, cale_film):
		Screen.__init__(self, session)
		self.setTitle(_t("Caută subtitrări pe internet"))
		self.cale = cale_film
		self.lucrare = LU.lucrare()
		self.alegeriLimbi = _alegeriLimbi()
		self.limbi = 0
		self.text = None
		self["list"] = List([])
		self["description"] = Label("")
		self["key_red"] = Label(_t("Închide"))
		self["key_yellow"] = Label(_t("Conturi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"red": self.close,
			"yellow": self.conturi,
			"left": lambda: self.stangaDreapta(-1),
			"right": lambda: self.stangaDreapta(1),
			"up": lambda: self["list"].selectPrevious(),
			"down": lambda: self["list"].selectNext(),
		}, -2)
		from enigma import eTimer
		self._ceas = eTimer()
		self._ceas.callback.append(self._bate)
		self._ultima = None
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._ceas.stop)

	def _porneste(self):
		self.cauta()
		self._ceas.start(300, False)

	def cauta(self):
		if not self.lucrare.cauta(self.cale, self.text, self.alegeriLimbi[self.limbi]):
			self["description"].setText(_t("O căutare sau o descărcare merge deja; așteaptă să se termine."))
		self._reface()

	def _textLimbi(self):
		return ", ".join(LB.nume(c) for c in self.alegeriLimbi[self.limbi])

	def _reface(self):
		s = self.lucrare.stare()
		info = s.get("film") or {}
		# fiecare rand pe doua linii: sus ce e, jos detaliile (la rezultate: sursa si semnele, ca sa se vada intotdeauna)
		randuri = [
			(_t("Caută din nou"), ""),
			(_t("Textul căutat: %s") % (self.text or info.get("titlu") or ""), ""),
			(_t("Limbile: %s") % self._textLimbi(), ""),
			(_t("Conturi"), ", ".join(m.NUME for m in self.lucrare.surse())),
		]
		for r in s["rezultate"]:
			semne = [r["sursa"]]
			if r["potrivire"]:
				semne.append(_t("potrivită cu fișierul"))
			if r["surzi"]:
				semne.append(_t("pentru surzi"))
			if r.get("descarcari"):
				semne.append(_t("%s descărcări") % r["descarcari"])
			randuri.append(("%s  %s" % (r["limba_text"], r["nume"][:self.MAX_NUME]), ", ".join(semne)))
		index = self["list"].getIndex() if self["list"].list else 0
		self["list"].setList(randuri)
		self["list"].setIndex(max(0, min(index or 0, len(randuri) - 1)))
		self["description"].setText(s["mesaj"])
		self._ultima = (s["faza"], len(s["rezultate"]), s["mesaj"])

	def _bate(self):
		s = self.lucrare.stare()
		if s["salvat"] and not s["aplicat"]:
			if self.lucrare.aplica(self.session):
				self._reface()
				self.session.open(MessageBox, self.lucrare.stare()["mesaj"], MessageBox.TYPE_INFO, timeout=6)
				self.close()
				return
		if (s["faza"], len(s["rezultate"]), s["mesaj"]) != self._ultima:
			self._reface()

	def stangaDreapta(self, directie):
		i = self["list"].getIndex() or 0
		if i == self.RAND_LIMBI:
			self.limbi = (self.limbi + directie) % len(self.alegeriLimbi)
			self._reface()
		else:
			# o pagina (7 randuri) in sus sau in jos
			self["list"].setIndex(max(0, min(i + 7 * directie, self["list"].count() - 1)))

	def ok(self):
		i = self["list"].getIndex() or 0
		if i == self.RAND_CAUTA:
			self.cauta()
		elif i == self.RAND_TEXT:
			from Screens.VirtualKeyBoard import VirtualKeyBoard
			info = self.lucrare.stare().get("film") or {}
			self.session.openWithCallback(self._textScris, VirtualKeyBoard, title=_t("Textul căutat"),
				text=self.text or info.get("titlu") or "")
		elif i == self.RAND_LIMBI:
			self.stangaDreapta(1)
		elif i == self.RAND_CONTURI:
			self.conturi()
		elif i >= self.PRIMUL_REZULTAT:
			if not self.lucrare.descarca(i - self.PRIMUL_REZULTAT):
				self["description"].setText(_t("O căutare sau o descărcare merge deja; așteaptă să se termine."))
			self._reface()

	def _textScris(self, text):
		if text and text.strip():
			self.text = text.strip()
			self.cauta()

	def conturi(self):
		self.session.open(HdsDescarcareSetari)


# ------------------------------------------------------------------ pe un canal TV sau pe o inregistrare .ts (tv.py)

class RandTv(ConfigElement):
	"""Un rand de reglaj (bara de potrivire si tasta SUB): textul din `text()`; stanga, dreapta si OK cheama functiile
	date (None = tasta nu face nimic)."""

	def __init__(self, text, stanga=None, dreapta=None, ok=None):
		ConfigElement.__init__(self)
		self._text = text
		self._fapte = {KEY_LEFT: stanga, KEY_RIGHT: dreapta, KEY_OK: ok}
		self._value = u""
		self.default = u""
		self.save_disabled = True

	def handleKey(self, key):
		fapta = self._fapte.get(key)
		if fapta is not None:
			fapta()

	def getText(self):
		try:
			return self._text() or u""
		except Exception:
			return u""

	def getMulti(self, selected):
		return ("text", self.getText())


def _scurt(text):
	"""Replica pe un rand (fara <i>, randurile unite cu " / "), intreaga: cand nu incape, deruleaza (lib/gui/elabel.h)."""
	return u" / ".join(r.replace(u"<i>", u"").replace(u"</i>", u"").strip() for r in (text or u"").split(u"\n") if r.strip())


class HdsPotrivireSubtitrare(Screen, ConfigListScreen):
	"""Bara "Potrivirea subtitrării", deasupra imaginii (sus; subtitrarea ramane la vedere): replica dinainte /
	urmatoarea (stanga / dreapta: replica aleasa incepe acum), +/- 0,5 s, Reclamă (si tasta GALBEN), viteza, Acum
	începe filmul, oprirea. Jos: replica urmatoare, ca omul sa stie pe care o asteapta. Aceeasi asezare ca setarile rapide
	ale subtitrarii (QuickSubtitlesConfigMenu din skin), deci fara ecran nou in skin."""

	skin = """
	<screen name="HdsPotrivireSubtitrare" position="72,40" size="1000,520" title="Potrivirea subtitrării" flags="wfNoBorder" backgroundColor="#20101318">
		<widget source="Title" render="Label" position="32,14" size="936,56" font="Regular;36" transparent="1" valign="center" noWrap="1" />
		<widget name="config" position="32,80" size="936,360" itemHeight="60" font="Regular;32" secondfont="Regular;16" scrollbarMode="showOnDemand" transparent="1" />
		<widget name="videofps" position="32,452" size="600,48" font="Regular;28" transparent="1" valign="center" noWrap="1" />
		<widget name="key_red" position="640,452" size="328,48" font="Regular;28" transparent="1" halign="right" valign="center" noWrap="1" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["HdsPotrivireSubtitrare", "QuickSubtitlesConfigMenu"]
		self.setTitle(_t("Potrivirea subtitrării"))
		from . import tv as TV
		self.TV = TV
		self["videofps"] = Label("")
		self["key_red"] = Label(_t("GALBEN: reclamă"))
		randuri = [
			getConfigListEntry(_t("Replica: < dinainte, următoarea >"), RandTv(self._replica,
				lambda: self._fa(TV.salt(session, -1)), lambda: self._fa(TV.salt(session, 1)), lambda: self._fa(TV.salt(session, 1)))),
			getConfigListEntry(_t("Potrivire fină: < -0,5 s, +0,5 s >"), RandTv(self._pozitie,
				lambda: self._fa(TV.muta(session, -TV.PAS_MS)), lambda: self._fa(TV.muta(session, TV.PAS_MS)))),
			getConfigListEntry(_t("Reclamă"), RandTv(self._reclama, self.reclama, self.reclama, self.reclama)),
			getConfigListEntry(_t("Viteza"), RandTv(self._viteza, lambda: self._viteza_pas(-1), lambda: self._viteza_pas(1),
				lambda: self._viteza_pas(1))),
			getConfigListEntry(_t("Acum începe filmul"), RandTv(lambda: u"OK", None, None, lambda: self._fa(TV.acumIncepe(session)))),
			getConfigListEntry(_t("Oprește subtitrarea"), RandTv(lambda: u"OK", None, None, self.opreste)),
		]
		ConfigListScreen.__init__(self, randuri, session=session)
		self["actiuni"] = ActionMap(["SetupActions", "ColorActions"], {
			"cancel": self.close,
			"red": self.close,
			"yellow": self.reclama,
		}, -2)
		from enigma import eTimer
		self._st = {}
		self._ceas = eTimer()
		self._ceas.callback.append(self._bate)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._ceas.stop)

	def _porneste(self):
		# o data pe secunda: pozitia se scrie in secunde, iar redesenarea barei costa (masurat in emulator)
		self._bate()
		self._ceas.start(1000, False)

	def _bate(self):
		self._st = self.TV.stare(self.session)
		if not self._st.get("tv") or not self._st.get("subtitrare"):
			self["videofps"].setText(_t("Acum nu merge o subtitrare de pe internet."))
		else:
			urm = _scurt(self._st.get("urmatoarea"))
			self["videofps"].setText((_t("Următoarea: %s") % urm) if urm else u"")
		try:
			self["config"].l.invalidate()
		except Exception:
			pass

	def _fa(self, reusit):
		self._bate()

	def _replica(self):
		return _scurt(self._st.get("replica")) or u"-"

	def _pozitie(self):
		return self._st.get("pozitie_text") or u""

	def _reclama(self):
		return _t("ceasul stă") if self._st.get("reclama") else _t("ceasul merge")

	def _viteza(self):
		return self._st.get("viteza_text") or u""

	def _viteza_pas(self, directie):
		cod = self._st.get("viteza_cod") or "auto"
		v = self.TV.VITEZE
		i = (v.index(cod) + directie) % len(v) if cod in v else 0
		self._fa(self.TV.alegeViteza(self.session, v[i]))

	def reclama(self):
		self._fa(self.TV.reclama(self.session))

	def opreste(self):
		self.TV.opreste(self.session)
		self.close()


class HdsDescarcareCautareTv(HdsDescarcareCautare):
	"""Cautarea pe un canal TV sau pe o inregistrare: filmul din EPG (identificat in Wikidata; OK pe primul rand =
	alegerea dintre mai multe filme sau titlul scris de mana), apoi subtitrarile deja pe receptor si cele gasite la surse.
	OK pe o subtitrare o pune pe canal; ecranul se inchide si se deschide bara de potrivire. Aceeasi asezare ca
	HdsDescarcareCautare."""

	RAND_FILM, RAND_CAUTA, RAND_TEXT, RAND_LIMBI, RAND_CONTURI = range(5)
	PRIMUL_REZULTAT = 5

	def __init__(self, session, film):
		self.film = film
		self._locale = []
		self._cautat = False
		self._incarc = False
		HdsDescarcareCautare.__init__(self, session, film.caleSalvare())
		self.skinName = ["HdsDescarcareCautareTv", "HdsDescarcareCautare"]
		from . import tv as TV
		self.TV = TV

	def _porneste(self):
		st = self.film.stareIdentificare()
		if st["stare"] == "nepornita":
			self.TV.identificaPeFir(self.film)
		elif st["stare"] == "sigur" or st["ales"]:
			self.cauta()
		self._reface()
		self._ceas.start(300, False)

	def cauta(self):
		self._cautat = True
		if not self.lucrare.cauta(self.film.caleSalvare(), self.text, self.alegeriLimbi[self.limbi], film=self.film.pentruCautare()):
			self["description"].setText(_t("O căutare sau o descărcare merge deja; așteaptă să se termine."))
		self._reface()

	def _randFilm(self, st):
		info = self.film.info
		a = st.get("ales")
		if a:
			sus = u"%s (%s)" % (a.get("original") or a.get("titlu"), a.get("an") or info.get("an") or u"?")
			jos = u", ".join(x for x in (a.get("titlu") if a.get("titlu") != a.get("original") else u"",
				(_t("regia %s") % a["regizor"]) if a.get("regizor") else u"", u"IMDb %s" % a.get("imdb")) if x)
			return (_t("Filmul: %s") % sus, jos)
		titlu = st.get("text_om") or info.get("titlu") or self.film.eveniment.get("titlu") or u"?"
		sus = _t("Filmul: %s") % (u"%s (%s)" % (titlu, info["an"]) if info.get("an") else titlu)
		if st["stare"] == "cauta":
			return (sus, _t("Se caută filmul în Wikidata..."))
		if st["stare"] == "mai_multe":
			return (sus, _t("Mai multe filme: OK alege filmul."))
		return (sus, st.get("mesaj") or _t("OK: scrie titlul."))

	def _reface(self):
		if not hasattr(self, "film"):
			return HdsDescarcareCautare._reface(self)
		s = self.lucrare.stare()
		st = self.film.stareIdentificare()
		with self.film.lacat:
			self._locale = [dict(x) for x in self.film.locale]
		randuri = [
			self._randFilm(st),
			(_t("Caută din nou"), u""),
			(_t("Textul căutat: %s") % (self.text or self.film.pentruCautare().get("titlu") or u""), u""),
			(_t("Limbile: %s") % self._textLimbi(), u""),
			(_t("Conturi"), u", ".join(m.NUME for m in self.lucrare.surse())),
		]
		for x in self._locale:
			randuri.append((_t("Pe receptor: %s") % x["nume"][:self.MAX_NUME], _t("deja descărcată, fără cotă")))
		if self._cautat and s.get("film", {}) and (s.get("film") or {}).get("tv"):
			for r in s["rezultate"]:
				semne = [r["sursa"]]
				if r.get("fps"):
					semne.append(_t("%s cadre/s") % (u"%g" % r["fps"]).replace(u".", u","))
				if r.get("automata"):
					semne.append(_t("tradusă automat"))
				if r["surzi"]:
					semne.append(_t("pentru surzi"))
				if r.get("descarcari"):
					semne.append(_t("%s descărcări") % r["descarcari"])
				randuri.append(("%s  %s" % (r["limba_text"], r["nume"][:self.MAX_NUME]), ", ".join(semne)))
		index = self["list"].getIndex() if self["list"].list else 0
		self["list"].setList(randuri)
		self["list"].setIndex(max(0, min(index or 0, len(randuri) - 1)))
		mesaj = self.film.mesaj if self._incarc else (s["mesaj"] if self._cautat else st.get("mesaj") or u"")
		self["description"].setText(mesaj or u"")
		self._ultima = (s["faza"], len(s["rezultate"]), s["mesaj"], st["stare"], bool(st.get("ales")), len(self._locale),
			self.film.mesaj)

	def _bate(self):
		s = self.lucrare.stare()
		st = self.film.stareIdentificare()
		if not self._cautat and (st["stare"] == "sigur" or st.get("ales")) and not st.get("lucreaza"):
			self.cauta()
			return
		if s["salvat"] and not s["aplicat"] and (s.get("film") or {}).get("tv"):
			if self.lucrare.aplica(self.session):
				self._incarc = True
		if self._incarc and self.film.subtitrare is not None:
			self.close(True)
			return
		with self.film.lacat:
			n_locale = len(self.film.locale)
		if (s["faza"], len(s["rezultate"]), s["mesaj"], st["stare"], bool(st.get("ales")), n_locale,
				self.film.mesaj) != self._ultima:
			self._reface()

	def ok(self):
		i = self["list"].getIndex() or 0
		if i == self.RAND_FILM:
			st = self.film.stareIdentificare()
			if len(st["candidati"]) > 1:
				from Screens.ChoiceBox import ChoiceBox
				lista = [(u"%s (%s)%s" % (c.get("original") or c.get("titlu"), c.get("an") or u"?",
					(u", " + c["regizor"]) if c.get("regizor") else u""), k) for k, c in enumerate(st["candidati"])]
				self.session.openWithCallback(self._candidatAles, ChoiceBox, title=_t("Care film este?"), list=lista)
			else:
				self._scrieTitlu()
		elif i == self.RAND_TEXT:
			self._scrieTitlu()
		elif i >= self.PRIMUL_REZULTAT + len(self._locale):
			if not self.lucrare.descarca(i - self.PRIMUL_REZULTAT - len(self._locale)):
				self["description"].setText(_t("O căutare sau o descărcare merge deja; așteaptă să se termine."))
			self._reface()
		elif i >= self.PRIMUL_REZULTAT:
			x = self._locale[i - self.PRIMUL_REZULTAT]
			reusit, mesaj = self.TV.incarca(self.session, x["cale"], None)
			self._incarc = reusit
			self["description"].setText(mesaj)
		else:
			HdsDescarcareCautare.ok(self)

	def _candidatAles(self, ales):
		if ales is None:
			return
		if self.TV.alegeCandidat(self.film, ales[1]):
			self.cauta()

	def _scrieTitlu(self):
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(self._titluScris, VirtualKeyBoard, title=_t("Titlul filmului (original, dacă îl știi)"),
			text=self.film.pentruCautare().get("titlu") or u"")

	def _titluScris(self, text):
		if text and text.strip():
			self.text = None
			self._cautat = False
			self.TV.scrieTitlu(self.film, text)
			self._reface()

	def _textScris(self, text):
		# "Textul căutat" pe TV: titlul scris intra si in identificare (ID-ul se schimba cu filmul)
		self._titluScris(text)


_CEAS_BARA = [None]


def _baraPesteImagine(session):
	"""Bara de potrivire peste imagine: ecranul tastei SUB (sub cautare sau sub randul "Potrivirea subtitrării…") se
	inchide intai, altfel ar acoperi imaginea si subtitrarea; bara se deschide dupa inchidere (un ecran se deschide
	numai peste unul care ruleaza)."""
	d = session.current_dialog
	if d is not None and d.__class__.__name__ in ("AudioSelection", "SubtitleSelection"):
		d.close(0)
	from enigma import eTimer
	if _CEAS_BARA[0] is None:
		_CEAS_BARA[0] = eTimer()
		_CEAS_BARA[0].callback.append(lambda: session.open(HdsPotrivireSubtitrare))
	_CEAS_BARA[0].start(150, True)


def _deschideBara(session, rezultat=None):
	if rezultat:
		_baraPesteImagine(session)


def potrivire(session, **kwargs):
	"""Randul "Potrivirea subtitrării…" din tasta SUB (ca un plugin: runPlugin)."""
	_baraPesteImagine(session)


# ------------------------------------------------------------------ intrarile
# Setarile (HdsDescarcareSetari) se deschid din meniu (data/menu.xml, hds_descarcare_subtitrari). Cautarea porneste din
# randul "Caută subtitrări pe internet" al ecranului tastei SUB (Screens/AudioSelection.py, numai pe pagina
# subtitrarilor: la un film din fisier, pe un canal TV cu imagine si la o inregistrare .ts), in bara TV si in playerul
# de filme. Din 0.3.2 fara descriptor de plugin: randul e pus direct de AudioSelection, in locul unde era descriptorul
# WHERE_AUDIOMENU, cu acelasi text.

def cautaPeInternet(session, **kwargs):
	"""Deschide cautarea pentru filmul care merge (din fisier, sau de pe canal / din inregistrare: tv.py); altfel un
	mesaj. kwargs: ce mai da bara (servicelist)."""
	cale = LU.filmulDeAcum()
	if cale:
		session.open(HdsDescarcareCautare, cale)
		return
	from . import tv as TV
	f = TV.filmulDeAcum(session)
	if f is None:
		session.open(MessageBox, _t("Căutarea subtitrărilor merge în timpul unui film din fișier, pe un canal TV sau la o "
			"înregistrare."), MessageBox.TYPE_INFO, timeout=8)
		return
	session.openWithCallback(lambda r=None: _deschideBara(session, r), HdsDescarcareCautareTv, f)
