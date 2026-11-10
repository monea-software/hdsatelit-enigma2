# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEgalizator.py: ecranul „Egalizator”. Meniu > Audio & Sound Tracks > Egalizator (si, dupa legare, tasta VERDE pe
# ecranul radio). Setarile si motorul sunt in Components/HdsEgalizator.py; pagina web /egalizator e perechea lui.
#
# Doua zone: cinci casete sus, separat cele 10 benzi si Nivel. OK/Jos pe Reglaj manual intra la 31 Hz.
# In coloane, stanga/dreapta aleg, sus/jos schimba cu 1 dB, OK salveaza Manual fara inchidere, EXIT renunta.
# Tastele colorate: ROSU renunta, VERDE pastreaza, GALBEN presetarea urmatoare, ALBASTRU pornit/oprit.
# Cat reglezi, sunetul se schimba pe loc (HdsEgalizator.incearca). OK sau VERDE salveaza (HdsEgalizator.seteaza); ROSU
# pune inapoi ce era; EXIT renunta la schimbarile nepastrate, la fel ca ROSU.
# „Pentru acest post” pe Nu arata din acel moment reglajele obisnuite (HdsEgalizator.comutaPePost).
#
# Desenul (Canvas, marimea din skin; asezarea din HdsEgalizator.geometriePanzei): sus 5 casete pentru alegeri, jos cate
# o coloana pe banda: sina, linia de 0 dB, bara de la 0 la valoare, butonul, valoarea deasupra si frecventa dedesubt;
# in spatele sinei, nivelul sunetului care iese pe banda aceea (spectrul din motor, -60..0 dBFS), iar peste butoane
# curba egalizatorului. Cu egalizatorul oprit desenul e stins. Fonturile HdsRegular / HdsBold numai pe skinul care are
# blocul HdsEgalizator (HDSatelit); pe celelalte skinuri „Regular”, pe care il are orice skin.
# Ceasul merge numai cat ecranul e aratat: la CEAS_MS cat vine spectrul, altfel la CEAS_RAR_MS; se redeseneaza numai
# cand s-a schimbat ceva (alegerea, valorile sau spectrul).

from enigma import eTimer, gFont, RT_HALIGN_CENTER, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Sources.CanvasSource import CanvasSource
from Components.Sources.StaticText import StaticText
from Components import HdsEgalizator as E

CEAS_MS = 250
CEAS_RAR_MS = 1000
SPECTRU_MIN_DB = -60.0

# culorile desenului (0xAARRGGBB, AA = 0 opac)
FUNDAL = 0x0D10162A
CASETA = 0x00282D3F
CASETA_ALEASA = 0x00374EA1
COLOANA_ALEASA = 0x00303650
SINA = 0x002A3350
LINIE_ZERO = 0x00667085
BARA = 0x009FB4FF
BARA_ALEASA = 0x00F5B83D
BUTON = 0x00F2F4F8
SPECTRU = 0x00323D63
STINS = 0x00667085
STINS_SPECTRU = 0x002A2F40
TEXT = 0x00F2F4F8
TEXT_SLAB = 0x00AEB9CC

# alegerile in ordinea de pe ecran
POZ_PORNIT, POZ_PRESETARE, POZ_MANUAL, POZ_POST, POZ_EFECTE = 0, 1, 2, 3, 4
POZ_BANDA0 = 5
POZ_NIVEL = POZ_BANDA0 + E.BENZI


def _culoareSelectie():
	"""Culoarea selectiei din stilul activ, inclusiv pe teme cu alte nume de culori."""
	try:
		import skin
		for _cale, dom in skin.dom_skins:
			for stil in dom.findall("windowstyle"):
				if stil.get("id", "0") == "0":
					for culoare in stil.findall("color"):
						if culoare.get("name") == "ListboxSelectedBackground":
							return skin.parseColor(culoare.get("color")).argb() & 0xFFFFFF
	except Exception:
		pass
	return BARA


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele din tabel se traduc la folosire."""
	return text


DESCRIERI_BENZI = (
	N_("basul cel mai adânc, care se simte mai mult decât se aude"),
	N_("basul adânc: toba mare, chitara bas"),
	N_("basul: căldura muzicii și a vocilor bărbătești"),
	N_("partea de jos a vocilor și a instrumentelor"),
	N_("mijlocul de jos: prea mult sună înfundat"),
	N_("mijlocul: corpul vocilor"),
	N_("prezența vocilor: se înțeleg mai bine cuvintele"),
	N_("claritatea: consoanele, chitarele"),
	N_("strălucirea: talgerele, respirația vocii"),
	N_("aerul: cele mai înalte sunete"),
)


def _fonturiHds():
	"""True cand skinul are blocul HdsEgalizator (skinul HDSatelit), deci si fonturile HdsRegular / HdsBold. Pe alt
	skin un font lipsa ar scrie „FONT ... MISSING” in jurnal la fiecare text si textul nu s-ar vedea."""
	try:
		import skin
		return skin.lookupScreen("HdsEgalizator", 0)[0] is not None
	except Exception:
		return False


def _font(fata, marime, hds=True):
	"""Fontul `fata` („HdsRegular” / „HdsBold”) la `marime` pe skinul HDSatelit; pe celelalte skinuri „Regular”."""
	nume = fata if hds else "Regular"
	try:
		from skin import parseFont
		return parseFont("%s;%d" % (nume, marime), ((1, 1), (1, 1)))
	except Exception:
		return gFont(nume, marime)


def _fontCaseta(text, latime, marime, obisnuit, hds=True):
	"""Valoarea dintr-o caseta: pe panza nu exista derulare, iar numele lungi (mai ales traduse) ar intra in caseta vecina.
	Un text prea lung se scrie cu un font mai mic. 0.56 = latimea unei litere fata de marime, masurata pe HdsBold pe textele lungi."""
	if 0.56 * len(text) * marime <= latime:
		return obisnuit
	return _font("HdsBold", max(12, int(latime / (0.56 * len(text)))), hds)


class HdsEgalizator(Screen):
	skin = """
	<screen name="HdsEgalizator" position="center,center" size="1180,680" title="Egalizator">
		<widget source="stare" render="Label" position="20,4" size="1140,70" font="Regular;24" halign="left" valign="top" transparent="1" />
		<widget source="stare_bine" render="Label" position="20,4" size="1140,70" font="Regular;24" halign="left" valign="top" foregroundColor="#0066d18b" transparent="1" />
		<widget source="stare_rau" render="Label" position="20,4" size="1140,70" font="Regular;24" halign="left" valign="top" foregroundColor="#00ffd24d" transparent="1" />
		<widget source="detaliu" render="Label" position="20,74" size="1140,24" font="Regular;17" halign="left" valign="center" foregroundColor="#00a8a8a8" transparent="1" noWrap="1" />
		<widget source="desen" render="Canvas" position="20,100" size="1140,418" />
		<widget source="descriere" render="Label" position="20,526" size="1140,56" font="Regular;19" halign="left" valign="top" transparent="1" />
		<widget source="nota" render="Label" position="20,586" size="1140,24" font="Regular;17" halign="left" valign="center" foregroundColor="#00a8a8a8" transparent="1" noWrap="1" />
		<widget source="key_red" render="Label" position="20,626" size="270,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="310,626" size="270,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="600,626" size="270,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget source="key_blue" render="Label" position="890,626" size="270,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		E.initConfig()
		self.setTitle(_("Egalizator"))
		self["stare"] = StaticText("")
		self["stare_bine"] = StaticText("")
		self["stare_rau"] = StaticText("")
		self["detaliu"] = StaticText("")
		self["desen"] = CanvasSource()
		self["descriere"] = StaticText("")
		self["nota"] = StaticText("")
		self["key_red"] = StaticText(_("Renunță"))
		self["key_green"] = StaticText(_("Păstrează"))
		self["key_yellow"] = StaticText(_("Presetarea următoare"))
		self["key_blue"] = StaticText(_("Pornit / Oprit"))
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
			"ok": self.ok,
			"cancel": self.renunta,
			"left": self.stanga,
			"right": self.dreapta,
			"up": self.sus,
			"down": self.jos,
			"red": self.puneInapoi,
			"green": self.pastreaza,
			"yellow": self.presetareaUrmatoare,
			"blue": self.pornitOprit,
		}, -1)
		s = E.stareCompleta()
		self.post = s["post"]
		self.v = {"pornit": s["pornit"], "presetare": s["presetare"], "benzi": list(s["benzi"]),
			"noapte": s["noapte"], "nivel": s["nivel"], "pe_post": s["pe_post"], "efect": s.get("efect", "fara")}
		self.orig = dict(self.v, benzi=list(s["benzi"]))
		self.poz = POZ_PRESETARE if s["pornit"] else POZ_PORNIT
		self.salvat = False
		self.selectie = _culoareSelectie()
		self.stareMotor = s["motor"]
		self.spectru = None
		self.desenat = None
		self.geom = None
		self.hds = _fonturiHds()
		self.ceas_ms = None
		self.ceas = eTimer()
		self.ceas.callback.append(self.improspateaza)
		self.onLayoutFinish.append(self._laAsezare)
		self.onShown.append(self._pornesteCeasul)
		self.onHide.append(self._opresteCeasul)
		self.onClose.append(self._opresteCeasul)
		self.arataStarea(s)
		self.arataDescrierea()

	# ---- ceasul: numai cat ecranul e aratat; des numai cat vine spectrul ----

	def _pornesteCeasul(self):
		self.ceas_ms = None
		self.improspateaza()

	def _opresteCeasul(self):
		self.ceas.stop()
		self.ceas_ms = None

	def _ceasLa(self, ms):
		if ms != self.ceas_ms:
			self.ceas_ms = ms
			self.ceas.start(ms, False)

	def _laAsezare(self):
		self.geom = self._marimeaPanzei()
		self.deseneaza(fortat=True)

	def _marimeaPanzei(self):
		for r in self.renderer:
			if getattr(r, "source", None) is self["desen"] and getattr(r, "instance", None) is not None:
				m = r.instance.size()
				return (m.width(), m.height())
		return (1140, 418)

	def improspateaza(self):
		st = E.stareMotor()
		self.stareMotor = st
		sp = None
		activ = bool(st and st.get("stare") in ("merge", "fara-date"))
		if activ and st.get("spectru"):
			sp = tuple(int(round(x)) for x in st["spectru"])
		schimbat = sp != self.spectru
		self.spectru = sp
		fmt, trimis = (None, None)
		if st is not None and st.get("post") == "format":
			fmt, trimis = E.felPistei()
		text, bine, detaliu = E.textStare(st, fmt, trimis)
		self._puneStarea(text, bine, detaliu)
		if schimbat:
			self.deseneaza()
		self._ceasLa(CEAS_MS if activ else CEAS_RAR_MS)

	def arataStarea(self, s):
		self._puneStarea(s["text"], s["bine"], s["detaliu"])

	def _puneStarea(self, text, bine, detaliu):
		self["stare"].setText(text if bine is None else "")
		self["stare_bine"].setText(text if bine is True else "")
		self["stare_rau"].setText(text if bine is False else "")
		self["detaliu"].setText(detaliu or "")

	# ---- tastele ----

	def stanga(self):
		self._muta(-1)

	def _muta(self, pas):
		if self.poz < POZ_BANDA0:
			self.poz = (self.poz + pas) % POZ_BANDA0
		else:
			self.poz = POZ_BANDA0 + (self.poz - POZ_BANDA0 + pas) % (E.BENZI + 1)
		# dupa mutare, descrierea e a locului nou; confirmarea salvarii ramane numai pana atunci
		self.salvat = False
		self._dupaMutare()

	def dreapta(self):
		self._muta(1)

	def _dupaMutare(self):
		self.arataDescrierea()
		self.deseneaza()

	def sus(self):
		self.schimba(1)

	def jos(self):
		if self.poz == POZ_MANUAL:
			self.intraInColoane()
		else:
			self.schimba(-1)

	def intraInColoane(self):
		self.poz = POZ_BANDA0
		self._dupaMutare()

	def ok(self):
		if self.poz == POZ_MANUAL:
			self.intraInColoane()
		elif self.poz in (POZ_PORNIT, POZ_POST):
			self.schimba(1)
		elif self.poz == POZ_PRESETARE:
			self.schimba(1)
		elif self.poz == POZ_EFECTE:
			self.deschideEfecte()
		else:
			self.pastreaza(inchide=False)

	def presetareaUrmatoare(self):
		self._presetare(1)
		self._dupaSchimbare()

	def pornitOprit(self):
		self._pornit(not self.v["pornit"])
		self._dupaSchimbare()

	def schimba(self, pas):
		p = self.poz
		if p == POZ_PORNIT:
			self._pornit(not self.v["pornit"])
		elif p == POZ_PRESETARE:
			self._presetare(pas)
		elif p in (POZ_MANUAL, POZ_EFECTE):
			return
		elif p == POZ_POST:
			if not self.post.get("cheie"):
				return
			# pe Nu se vad (si se aud) reglajele obisnuite; pe Da cele de acum raman si devin ale postului
			self.v = E.comutaPePost(self.v, not self.v["pe_post"])
		elif p == POZ_NIVEL:
			self.v["nivel"] = E.limiteaza(self.v["nivel"] + pas, E.NIVEL_MIN, E.NIVEL_MAX)
			self.v["presetare"], self.v["noapte"] = E.MANUAL, False
		else:
			i = p - POZ_BANDA0
			self.v["benzi"][i] = E.limiteaza(self.v["benzi"][i] + pas, E.DB_MIN, E.DB_MAX)
			self.v["presetare"], self.v["noapte"] = E.MANUAL, False
		self._dupaSchimbare()

	def _presetare(self, pas):
		chei = list(E.CHEI_PRESETARI) + [E.MANUAL]
		try:
			i = chei.index(self.v["presetare"])
		except ValueError:
			i = -1 if pas > 0 else 0
		cheie = chei[(i + pas) % len(chei)]
		if cheie == E.MANUAL:
			m = E.reglajManual(self.v["pe_post"], self.post.get("cheie"))
			self.v.update(presetare=E.MANUAL, benzi=list(m["benzi"]), noapte=m["noapte"], nivel=m["nivel"],
				efect=m.get("efect", "fara"))
			return
		p = E.presetare(cheie)
		self.v["presetare"] = cheie
		self.v["benzi"] = list(p[2])
		self.v["noapte"] = bool(p[3])
		self.v["efect"] = "fara"

	def deschideEfecte(self):
		"""Lista nativa derulabila: selectia se asculta, OK o pastreaza, EXIT revine la intrare."""
		from Screens.ChoiceBox import ChoiceBox

		class Efecte(ChoiceBox):
			def __init__(self, session, alegeri, selectie, asculta):
				ChoiceBox.__init__(self, session,
					title=_("Sus/jos: asculți efectul. OK: păstrezi. EXIT: revii la efectul anterior."),
					list=alegeri, keys=[], selection=selectie, skin_name="HdsEgalizatorEfecte")
				self.setTitle(_("Efecte speciale"))
				self.asculta = asculta
				self["list"].onSelectionChanged.append(self._ascultaSelectia)

			def _ascultaSelectia(self):
				rand = self["list"].getCurrent()
				if rand:
					self.asculta(rand[0][1])

		self.inainteEfecte = dict(self.v, benzi=list(self.v["benzi"]))
		self.salvatInainteEfecte = self.salvat
		alegeri = [(nume, cheie) for cheie, nume in E.numeEfecte()]
		selectie = next((i for i, alegere in enumerate(alegeri) if alegere[1] == self.v["efect"]), 0)
		self.session.openWithCallback(self._dupaEfecte, Efecte, alegeri, selectie, self._ascultaEfect)

	def _ascultaEfect(self, efect):
		efect = E.curataEfect(efect)
		if efect != self.v["efect"]:
			self.v.update(efect=efect, presetare=E.MANUAL)
			self._dupaSchimbare()

	def _dupaEfecte(self, alegere):
		if alegere is None:
			self.v = self.inainteEfecte
			self.salvat = self.salvatInainteEfecte
			E.incearca(benzi=self.v["benzi"], noapte=self.v["noapte"], nivel=self.v["nivel"],
				pornit=self.v["pornit"], efect=self.v["efect"])
		else:
			self._ascultaEfect(alegere[1])
		del self.inainteEfecte, self.salvatInainteEfecte
		self._dupaMutare()

	def _pornit(self, pornit):
		self.v["pornit"] = bool(pornit)
		E.incearca(benzi=self.v["benzi"], noapte=self.v["noapte"], nivel=self.v["nivel"], pornit=self.v["pornit"],
			efect=self.v["efect"])

	def _dupaSchimbare(self):
		self.salvat = False
		E.incearca(benzi=self.v["benzi"], noapte=self.v["noapte"], nivel=self.v["nivel"], efect=self.v["efect"])
		self.arataDescrierea()
		self.deseneaza()

	def _schimbat(self):
		o = self.orig
		return any(self.v[k] != o[k] for k in ("pornit", "noapte", "nivel", "presetare", "pe_post", "efect")) or \
			self.v["benzi"] != o["benzi"]

	def pastreaza(self, inchide=True):
		manual = self.poz >= POZ_BANDA0
		s = E.seteaza(pornit=self.v["pornit"], presetare_=self.v["presetare"], benzi=self.v["benzi"],
			noapte=self.v["noapte"], nivel=self.v["nivel"], efect=self.v["efect"], salveazaManual=manual,
			pePost=self.v["pe_post"] if self.post.get("cheie") else None)
		self.v.update(presetare=s["presetare"])
		self.orig = dict(self.v, benzi=list(self.v["benzi"]))
		# fara True: meniul (Screens/Menu.py, menuClosed) ar inchide atunci toate meniurile, nu numai ecranul
		if inchide:
			self.close()
		else:
			self.salvat = True
			self._dupaMutare()

	def renunta(self):
		"""EXIT si ROSU renunta la proba nesalvata, fara intrebare."""
		self.puneInapoi()

	def puneInapoi(self):
		"""ROSU si EXIT: motorul primeste inapoi reglajele pastrate, fara nicio scriere."""
		if self._schimbat():
			m = E.motor()
			if m is not None:
				E.trimiteLaMotor(E.setariEfective(self.post.get("cheie")), m)
				m.setPornit(1 if self.orig["pornit"] else 0)
		self.close(False)

	# ---- textele ----

	def arataDescrierea(self):
		p = self.poz
		if p == POZ_PORNIT:
			# oprit din fabrica; textul spune la ce posturi lucreaza (numai sunet MPEG) si ca pe unele receptoare poate intrerupe sunetul
			t = _("Oprit din fabrică. Lucrează numai la posturile cu sunet MPEG (MP2), radio și TV. Pe unele receptoare poate produce distorsiuni sau întreruperi; atunci oprește-l.")
		elif p == POZ_PRESETARE:
			t = _("Presetarea pune singură toate benzile; apoi le poți potrivi una câte una. Barele din spate: cât de tare se aude acum fiecare bandă.")
		elif p == POZ_MANUAL:
			t = _("OK sau Jos: intri la 31 Hz. Reglezi benzile și Nivel, apoi OK salvează în presetarea „Manual”. La modificare, comprimarea se oprește.")
		elif p == POZ_POST:
			if self.post.get("cheie"):
				t = _("Da: reglajele de aici se țin minte numai pentru %s. Nu: postul folosește reglajele obișnuite, ale tuturor posturilor, pe care le vezi aici.") % (self.post.get("nume") or _("acest post"))
			else:
				t = _("Nu merge niciun post acum, deci reglajele se păstrează pentru toate posturile.")
		elif p == POZ_NIVEL:
			t = _("Nivel: potrivești tăria sunetului cu egalizator față de sunetul obișnuit, între −12 și +12 dB.")
		elif p == POZ_EFECTE:
			t = _("OK: deschizi lista de efecte. Sus și jos în listă: asculți pe loc. OK păstrează alegerea, EXIT revine la efectul anterior.")
		else:
			i = p - POZ_BANDA0
			t = _("%s, %s. Sus și jos: cu 1 dB mai mult sau mai puțin, între −24 și +18 dB.") % (E.ETICHETE[i], _(DESCRIERI_BENZI[i]))
		self["descriere"].setText(_("Reglaj salvat în presetarea „Manual”.") if self.salvat else t)
		self.arataNota()

	def arataNota(self):
		"""Randul de jos: ce fac tastele acolo unde esti (OK nu face peste tot acelasi lucru)."""
		p = self.poz
		if p == POZ_PORNIT:
			t = _("Stânga și dreapta: alegi. OK: pornești sau oprești. EXIT: ieși.")
		elif p == POZ_PRESETARE:
			t = _("Stânga și dreapta: alegi. Sus, jos sau OK: presetarea următoare. EXIT: ieși.")
		elif p == POZ_MANUAL:
			t = _("OK sau Jos: reglezi coloanele. EXIT: ieși.")
		elif p == POZ_POST:
			t = _("Stânga și dreapta: alegi. OK: da sau nu. EXIT: ieși.")
		elif p == POZ_EFECTE:
			t = _("OK: alegi un efect special. EXIT: ieși.")
		else:
			t = _("Stânga/dreapta: coloana. Sus/jos: 1 dB. OK: salvezi Manual. EXIT: renunți.")
		self["nota"].setText(t)

	# ---- desenul ----

	def deseneaza(self, fortat=False):
		if self.geom is None:
			return
		cheie = (self.poz, self.v["pornit"], self.v["presetare"], tuple(self.v["benzi"]), self.v["noapte"],
			self.v["nivel"], self.v["pe_post"], self.v["efect"], self.spectru, self.geom)
		if not fortat and cheie == self.desenat:
			return
		self.desenat = cheie
		c = self["desen"]
		c.clear()
		W, H = self.geom
		g = E.geometriePanzei(W, H)
		c.fill(0, 0, W, H, FUNDAL)
		f_mic = _font("HdsRegular", g["f_mic"], self.hds)
		f_val = _font("HdsBold", 28 if g["mare"] else 19, self.hds)
		f_eticheta = _font("HdsRegular", g["f_eticheta"], self.hds)
		f_bold = _font("HdsBold", g["f_bold"], self.hds)
		pornit = self.v["pornit"]

		# casetele de sus
		h_caseta = g["h_caseta"]
		w_caseta = g["w_caseta"]
		casete = (
			(POZ_PORNIT, _("Egalizator"), _("Pornit") if pornit else _("Oprit")),
			(POZ_PRESETARE, _("Presetare"), E.numePresetare(self.v["presetare"])),
			(POZ_MANUAL, _("Reglaj manual"), _("Comprimare activă") if self.v["noapte"] else _("OK / Jos")),
			(POZ_POST, _("Pentru acest post"), (_("Da") if self.v["pe_post"] else _("Nu")) if self.post.get("cheie") else _("Fără post")),
			(POZ_EFECTE, _("Efecte speciale"), E.numeEfect(self.v["efect"])),
		)
		for k, (poz, eticheta, valoare) in enumerate(casete):
			x = k * (w_caseta + g["spatiu"])
			ales = poz == self.poz
			fond = CASETA_ALEASA if ales else CASETA
			c.fill(x, 0, w_caseta, h_caseta, fond)
			c.writeText(x + 12, 0, w_caseta - 24, h_caseta // 2 - 4, TEXT if ales else TEXT_SLAB, fond, f_mic, eticheta,
				RT_HALIGN_LEFT | RT_VALIGN_CENTER)
			font_valoare = _fontCaseta(valoare, w_caseta - 24, 28 if g["mare"] else 19, f_val, self.hds)
			c.writeText(x + 12, h_caseta // 2 - 4, w_caseta - 24, h_caseta // 2, TEXT, fond, font_valoare, valoare,
				RT_HALIGN_LEFT | RT_VALIGN_CENTER)

		# coloanele: valoarea sus, eticheta jos, butonul intre ele, inclusiv la capetele fiecarei scale
		sus = g["sus"]
		w_scala = g["w_scala"]
		w_col = g["w_col"]
		h_text = g["h_text"]
		y_sus, y_jos, y_zero = g["y_sus"], g["y_jos"], g["y_zero"]
		inalt = y_jos - y_sus

		def y_db(db, nivel=False):
			jos, sus = (E.NIVEL_MIN, E.NIVEL_MAX) if nivel else (E.DB_MIN, E.DB_MAX)
			return y_sus + int(round((sus - db) * inalt / float(sus - jos)))

		# scala din stanga si linia de 0 dB
		for db, text in ((E.DB_MAX, u"+18"), (0, u"0"), (E.DB_MIN, u"−24")):
			c.writeText(0, y_db(db) - 16, w_scala - 12, 32, TEXT_SLAB, FUNDAL, f_mic, text, RT_HALIGN_RIGHT | RT_VALIGN_CENTER)

		puncte = []
		butoane = []
		for k in range(E.BENZI + 1):
			x0 = w_scala + k * w_col
			poz = POZ_BANDA0 + k
			ales = poz == self.poz
			nivel = k == E.BENZI
			# Langa sina Nivel ramane loc pentru propria scala; valorile/etichetele raman centrate pe coloana.
			cx = x0 + (w_col // 3 if nivel else w_col // 2)
			zero = g["y_nivel_zero"] if nivel else y_zero
			valoare = self.v["nivel"] if nivel else self.v["benzi"][k]
			if ales:
				c.fill(x0 + 4, sus, w_col - 8, H - sus, COLOANA_ALEASA)
			fond = COLOANA_ALEASA if ales else FUNDAL
			if nivel:
				c.fill(x0, sus, 2, H - sus, LINIE_ZERO)
			# spectrul, in spatele sinei
			if self.spectru is not None and not nivel:
				niv = max(SPECTRU_MIN_DB, min(0.0, float(self.spectru[k])))
				h = int((niv - SPECTRU_MIN_DB) / -SPECTRU_MIN_DB * inalt)
				if h > 0:
					lat = int(w_col * 0.56)
					c.fill(cx - lat // 2, y_jos - h, lat, h, SPECTRU if pornit else STINS_SPECTRU)
			c.fill(x0 + 4, zero, w_col - 8, 1, LINIE_ZERO)
			c.fill(cx - 6, y_sus, 12, inalt, SINA)
			c.fill(cx - 6, zero - 1, 12, 3, LINIE_ZERO)
			yv = y_db(valoare, nivel)
			culoare = (BARA_ALEASA if ales else BARA) if pornit else STINS
			if yv < zero:
				c.fill(cx - 6, yv, 12, zero - yv, culoare)
			elif yv > zero:
				c.fill(cx - 6, zero, 12, yv - zero, culoare)
			if nivel:
				for db, text in ((E.NIVEL_MAX, u"+12"), (0, u"0"), (E.NIVEL_MIN, u"−12")):
					x_text = cx + g["raza"] + 6
					c.writeText(x_text, y_db(db, True) - h_text // 2, x0 + w_col - x_text - 4, h_text,
						TEXT_SLAB, fond, f_mic, text, RT_HALIGN_LEFT | RT_VALIGN_CENTER)
			butoane.append((cx, yv, ales))
			c.writeText(x0, sus, w_col, h_text, TEXT, fond, f_bold, E.textDb(valoare), RT_HALIGN_CENTER | RT_VALIGN_CENTER)
			eticheta = _("Nivel") if nivel else E.ETICHETE[k]
			c.writeText(x0, g["y_eticheta"], w_col, h_text, TEXT if ales else TEXT_SLAB, fond, f_eticheta, eticheta,
				RT_HALIGN_CENTER | RT_VALIGN_CENTER)
			if not nivel:
				puncte.append((cx, yv))
		# curba egalizatorului, apoi butoanele peste ea
		for (xa, ya), (xb, yb) in zip(puncte, puncte[1:]):
			c.drawLine(xa, ya, xb, yb, 3, BARA if pornit else STINS)
		for cx, yv, ales in butoane:
			c.fillCircle(cx, yv, g["raza"], (BARA_ALEASA if ales else BUTON) if pornit else STINS)
		if self.poz >= POZ_BANDA0:
			# Contur comun, cu suport contrastant si culoarea selectiei din tema.
			x, y, w, h = w_scala, sus - 6, W - w_scala - 1, H - sus + 5
			for grosime, culoare in ((5, TEXT), (3, self.selectie)):
				c.fill(x, y, w, grosime, culoare)
				c.fill(x, y + h - grosime, w, grosime, culoare)
				c.fill(x, y, grosime, h, culoare)
				c.fill(x + w - grosime, y, grosime, h, culoare)
		c.flush()
