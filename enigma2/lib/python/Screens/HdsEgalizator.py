# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEgalizator.py: ecranul „Egalizator”. Meniu > Audio & Sound Tracks > Egalizator (si, dupa legare, tasta VERDE pe
# ecranul radio). Setarile si motorul sunt in Components/HdsEgalizator.py; pagina web /egalizator e perechea lui.
#
# Un singur rand de alegeri, parcurs cu stanga/dreapta (de la capat se trece la celalalt capat):
#   Egalizator (pornit / oprit), Presetare, Mod de noapte, Pentru acest post, cele 10 benzi (31 Hz ... 16 kHz), Nivel.
# Sus/jos schimba alegerea din fata: banda si nivelul cu 1 dB (-12..+12), presetarea urmatoare / de dinainte, celelalte
# da / nu. OK schimba alegerile cu da / nu si presetarea; pe o banda sau pe nivel OK pastreaza si inchide. Randul de jos
# („nota”) spune ce face OK acolo unde esti. Tastele colorate sunt numai scurtaturi: ROSU renunta, VERDE pastreaza,
# GALBEN presetarea urmatoare, ALBASTRU pornit / oprit.
# Cat reglezi, sunetul se schimba pe loc (HdsEgalizator.incearca). OK sau VERDE salveaza (HdsEgalizator.seteaza); ROSU
# pune inapoi ce era; EXIT, cand s-a schimbat ceva, intreaba „Păstrezi schimbările?” (Da / Nu, cu sagetile si OK).
# „Pentru acest post” pe Nu arata din acel moment reglajele obisnuite (HdsEgalizator.comutaPePost).
#
# Desenul (Canvas, marimea din skin; asezarea din HdsEgalizator.geometriePanzei): sus 4 casete pentru alegeri, jos cate
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
POZ_PORNIT, POZ_PRESETARE, POZ_NOAPTE, POZ_POST = 0, 1, 2, 3
POZ_BANDA0 = 4
POZ_NIVEL = POZ_BANDA0 + E.BENZI
NUMAR_POZ = POZ_NIVEL + 1


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


class HdsEgalizator(Screen):
	skin = """
	<screen name="HdsEgalizator" position="center,center" size="1180,680" title="Egalizator">
		<widget source="stare" render="Label" position="20,4" size="1140,68" font="Regular;24" halign="left" valign="top" transparent="1" />
		<widget source="stare_bine" render="Label" position="20,4" size="1140,68" font="Regular;24" halign="left" valign="top" foregroundColor="#0066d18b" transparent="1" />
		<widget source="stare_rau" render="Label" position="20,4" size="1140,68" font="Regular;24" halign="left" valign="top" foregroundColor="#00ffd24d" transparent="1" />
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
			"noapte": s["noapte"], "nivel": s["nivel"], "pe_post": s["pe_post"]}
		self.orig = dict(self.v, benzi=list(s["benzi"]))
		self.poz = POZ_PRESETARE if s["pornit"] else POZ_PORNIT
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
		self.poz = (self.poz - 1) % NUMAR_POZ
		self._dupaMutare()

	def dreapta(self):
		self.poz = (self.poz + 1) % NUMAR_POZ
		self._dupaMutare()

	def _dupaMutare(self):
		self.arataDescrierea()
		self.deseneaza()

	def sus(self):
		self.schimba(1)

	def jos(self):
		self.schimba(-1)

	def ok(self):
		if self.poz in (POZ_PORNIT, POZ_NOAPTE, POZ_POST):
			self.schimba(1)
		elif self.poz == POZ_PRESETARE:
			self.schimba(1)
		else:
			self.pastreaza()

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
		elif p == POZ_NOAPTE:
			self.v["noapte"] = not self.v["noapte"]
			self.v["presetare"] = E.presetareDupaBenzi(self.v["benzi"], self.v["noapte"])
		elif p == POZ_POST:
			if not self.post.get("cheie"):
				return
			# pe Nu se vad (si se aud) reglajele obisnuite; pe Da cele de acum raman si devin ale postului
			self.v = E.comutaPePost(self.v, not self.v["pe_post"])
		elif p == POZ_NIVEL:
			self.v["nivel"] = E.limiteaza(self.v["nivel"] + pas, E.NIVEL_MIN, E.NIVEL_MAX)
		else:
			i = p - POZ_BANDA0
			self.v["benzi"][i] = E.limiteaza(self.v["benzi"][i] + pas, E.DB_MIN, E.DB_MAX)
			self.v["presetare"] = E.presetareDupaBenzi(self.v["benzi"], self.v["noapte"])
		self._dupaSchimbare()

	def _presetare(self, pas):
		chei = list(E.CHEI_PRESETARI)
		try:
			i = chei.index(self.v["presetare"])
		except ValueError:
			i = -1 if pas > 0 else 0
		cheie = chei[(i + pas) % len(chei)]
		p = E.presetare(cheie)
		self.v["presetare"] = cheie
		self.v["benzi"] = list(p[2])
		self.v["noapte"] = bool(p[3])

	def _pornit(self, pornit):
		self.v["pornit"] = bool(pornit)
		E.incearca(benzi=self.v["benzi"], noapte=self.v["noapte"], nivel=self.v["nivel"], pornit=self.v["pornit"])

	def _dupaSchimbare(self):
		E.incearca(benzi=self.v["benzi"], noapte=self.v["noapte"], nivel=self.v["nivel"])
		self.arataDescrierea()
		self.deseneaza()

	def _schimbat(self):
		o = self.orig
		return any(self.v[k] != o[k] for k in ("pornit", "noapte", "nivel", "presetare", "pe_post")) or \
			self.v["benzi"] != o["benzi"]

	def pastreaza(self):
		E.seteaza(pornit=self.v["pornit"], benzi=self.v["benzi"], noapte=self.v["noapte"], nivel=self.v["nivel"],
			pePost=self.v["pe_post"] if self.post.get("cheie") else None)
		# fara True: meniul (Screens/Menu.py, menuClosed) ar inchide atunci toate meniurile, nu numai ecranul
		self.close()

	def renunta(self):
		"""EXIT: fara schimbari se inchide; cu schimbari intreaba (Da = pastreaza, Nu = pune inapoi)."""
		if not self._schimbat():
			self.close(False)
			return
		from Screens.MessageBox import MessageBox
		self.session.openWithCallback(self._dupaIntrebare, MessageBox, _("Păstrezi schimbările?"), MessageBox.TYPE_YESNO,
			default=True)

	def _dupaIntrebare(self, da):
		if da:
			self.pastreaza()
		else:
			self.puneInapoi()

	def puneInapoi(self):
		"""ROSU (si Nu la intrebare): motorul primeste inapoi reglajele pastrate, fara nicio scriere."""
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
			t = _("Pornit, sunetul posturilor de radio trece prin procesor și se aude cu reglajele de mai jos.")
		elif p == POZ_PRESETARE:
			t = _("Presetarea pune singură toate benzile; apoi le poți potrivi una câte una. Barele din spate: cât de tare se aude acum fiecare bandă.")
		elif p == POZ_NOAPTE:
			t = _("Modul de noapte: sunetele tari devin mai încete, cele încete mai tari. Potrivit seara, când asculți încet.")
		elif p == POZ_POST:
			if self.post.get("cheie"):
				t = _("Da: reglajele de aici se țin minte numai pentru %s. Nu: postul folosește reglajele obișnuite, ale tuturor posturilor, pe care le vezi aici.") % (self.post.get("nume") or _("acest post"))
			else:
				t = _("Nu merge niciun post acum, deci reglajele se păstrează pentru toate posturile.")
		elif p == POZ_NIVEL:
			t = _("Nivel: potrivești tăria sunetului cu egalizator față de sunetul obișnuit, între −12 și +12 dB.")
		else:
			i = p - POZ_BANDA0
			t = _("%s, %s. Sus și jos: cu 1 dB mai mult sau mai puțin, între −12 și +12 dB.") % (E.ETICHETE[i], _(DESCRIERI_BENZI[i]))
		self["descriere"].setText(t)
		self.arataNota()

	def arataNota(self):
		"""Randul de jos: ce fac tastele acolo unde esti (OK nu face peste tot acelasi lucru)."""
		p = self.poz
		if p == POZ_PORNIT:
			t = _("Stânga și dreapta: alegi. OK: pornești sau oprești. EXIT: ieși.")
		elif p == POZ_PRESETARE:
			t = _("Stânga și dreapta: alegi. Sus, jos sau OK: presetarea următoare. EXIT: ieși.")
		elif p in (POZ_NOAPTE, POZ_POST):
			t = _("Stânga și dreapta: alegi. OK: da sau nu. EXIT: ieși.")
		else:
			t = _("Stânga și dreapta: alegi. Sus și jos: schimbi. OK: păstrezi și închizi.")
		self["nota"].setText(t)

	# ---- desenul ----

	def deseneaza(self, fortat=False):
		if self.geom is None:
			return
		cheie = (self.poz, self.v["pornit"], self.v["presetare"], tuple(self.v["benzi"]), self.v["noapte"],
			self.v["nivel"], self.v["pe_post"], self.spectru, self.geom)
		if not fortat and cheie == self.desenat:
			return
		self.desenat = cheie
		c = self["desen"]
		c.clear()
		W, H = self.geom
		g = E.geometriePanzei(W, H)
		c.fill(0, 0, W, H, FUNDAL)
		f_mic = _font("HdsRegular", g["f_mic"], self.hds)
		f_val = _font("HdsBold", g["f_val"], self.hds)
		f_eticheta = _font("HdsRegular", g["f_eticheta"], self.hds)
		f_bold = _font("HdsBold", g["f_bold"], self.hds)
		pornit = self.v["pornit"]

		# casetele de sus
		h_caseta = g["h_caseta"]
		w_caseta = g["w_caseta"]
		casete = (
			(POZ_PORNIT, _("Egalizator"), _("Pornit") if pornit else _("Oprit")),
			(POZ_PRESETARE, _("Presetare"), E.numePresetare(self.v["presetare"])),
			(POZ_NOAPTE, _("Mod de noapte"), _("Pornit") if self.v["noapte"] else _("Oprit")),
			(POZ_POST, _("Pentru acest post"), (_("Da") if self.v["pe_post"] else _("Nu")) if self.post.get("cheie") else _("Fără post")),
		)
		for k, (poz, eticheta, valoare) in enumerate(casete):
			x = k * (w_caseta + g["spatiu"])
			ales = poz == self.poz
			fond = CASETA_ALEASA if ales else CASETA
			c.fill(x, 0, w_caseta, h_caseta, fond)
			c.writeText(x + 16, 4, w_caseta - 32, h_caseta // 2 - 6, TEXT if ales else TEXT_SLAB, fond, f_mic, eticheta,
				RT_HALIGN_LEFT | RT_VALIGN_CENTER)
			c.writeText(x + 16, h_caseta // 2 - 4, w_caseta - 32, h_caseta // 2, TEXT, fond, f_val, valoare,
				RT_HALIGN_LEFT | RT_VALIGN_CENTER)

		# coloanele benzilor si a nivelului: valoarea sus, eticheta jos, butonul intre ele (la +/-12 dB nu intra in ele)
		sus = g["sus"]
		w_scala = g["w_scala"]
		w_col = g["w_col"]
		h_text = g["h_text"]
		y_sus, y_jos, y_zero = g["y_sus"], g["y_jos"], g["y_zero"]
		inalt = y_jos - y_sus

		def y_db(db):
			return y_zero - int(round(db * (inalt / 2.0) / E.DB_MAX))

		# scala din stanga si linia de 0 dB
		for db, text in ((E.DB_MAX, u"+12"), (0, u"0"), (E.DB_MIN, u"−12")):
			c.writeText(0, y_db(db) - 16, w_scala - 12, 32, TEXT_SLAB, FUNDAL, f_mic, text, RT_HALIGN_RIGHT | RT_VALIGN_CENTER)
		c.fill(w_scala, y_zero, W - w_scala, 1, LINIE_ZERO)

		puncte = []
		butoane = []
		for k in range(E.BENZI + 1):
			x0 = w_scala + k * w_col
			cx = x0 + w_col // 2
			poz = POZ_BANDA0 + k
			ales = poz == self.poz
			nivel = k == E.BENZI
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
			c.fill(cx - 6, y_sus, 12, inalt, SINA)
			c.fill(cx - 6, y_zero - 1, 12, 3, LINIE_ZERO)
			yv = y_db(valoare)
			culoare = (BARA_ALEASA if ales else BARA) if pornit else STINS
			if yv < y_zero:
				c.fill(cx - 6, yv, 12, y_zero - yv, culoare)
			elif yv > y_zero:
				c.fill(cx - 6, y_zero, 12, yv - y_zero, culoare)
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
		c.flush()
