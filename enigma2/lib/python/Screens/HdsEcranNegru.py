# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEcranNegru.py: mesajul de pe mijlocul ecranului cat timp canalul ramane negru (verdictul vine din
# Components/HdsEcranNegru.py): numele canalului, titlul, fraza simpla, etichetele sistemelor de criptare, nivelul si
# calitatea semnalului, butonul faptei (OK), detaliul tehnic mai mic, pasii decriptarii la canalul criptat (numai cu
# setarea lor pornita, Components/HdsPasiDecriptare.py) si randul „EXIT ascunde mesajul”.
#
# Fereastra e nemodala (session.instantiateDialog), sub bare (zPosition -2), si se vede numai cand:
# - setarea config.usage.hds_ecran_negru e pornita;
# - bara canalelor (InfoBar) e ecranul din fata: harta de taste a mesajului e pe InfoBar, iar execBegin / execEnd ale
#   ei spun cand alt ecran se deschide peste bara (Session.execEnd ascunde bara si ii opreste componentele);
# - a doua bara (pe tot ecranul) nu e deschisa;
# - panoul motorului antenei (HdsDishMotor, setarea „Show positioner movement”) nu arata deja rotirea;
# - omul nu l-a ascuns cu EXIT pentru acelasi fel de mesaj (pana la alt canal sau alt mesaj).
#
# Tastele (harta la prioritatea -1, inaintea hartilor barei, pornita numai cat se vede mesajul): OK = fapta, EXIT =
# ascunde mesajul; amandoua numai cand prima bara e ascunsa, altfel trec la bara. Fara fapta, OK arata bara ca de obicei.
#
# Asezarea: randurile goale nu lasa loc gol. Dupa layout se citesc pozitiile din skin; la fiecare mesaj nou randurile
# vazute se aseaza unul sub altul cu distantele din skin, fereastra se scurteaza si ramane centrata pe acelasi mijloc.
# Etichetele sistemelor si butonul faptei se centreaza pe latimea textului lor. Skinul HDSatelit are blocul
# <screen name="HdsEcranNegru">; pentru alte skinuri, skinul de rezerva de mai jos (1920, scalat la desktop, font
# „Regular”, culori scrise direct).

from enigma import ePoint, eSize

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components import HdsEcranNegru as E
from Tools.ScaledSkin import scaledSkin

ETICHETE = 4
# randurile, de sus in jos; un rand se vede daca are ce arata
RANDURI = (
	("canal",),
	("titlu",),
	("text",),
	tuple(n for i in range(1, ETICHETE + 1) for n in ("chenar%d" % i, "etic%d" % i)),
	("semnal_text", "semnal", "semnal_val"),
	("calitate_text", "calitate", "calitate_val"),
	("fapta", "fapta_tasta", "fapta_text"),
	("detaliu",),
	("pasi",),
	("indemn",),
)
# pasii decriptarii (Components/HdsPasiDecriptare.py, cu setarea lor pornita): randurile vii sub detaliu, intr-o caseta
# de PASI_RANDURI randuri de font, aceeasi inaltime oricate randuri are acum (textul se schimba in fiecare secunda fara
# sa se refaca asezarea). Un skin fara caseta "pasi" pierde numai acest rand, nu toata asezarea.
PASI_RANDURI = 5
OPTIONALE = ("pasi",)
CONTEXTE_TASTE = ["InfobarShowHideActions"]
# canalul folosit ultima data ramane pastrat de nucleu 3 s dupa oprire; cu 3,5 s programul ia un canal nou, deci un
# acord nou (aceeasi valoare ca in Components/HdsMotorPozitie.py si Components/HdsLnbAplicare.py)
ELIBERARE_CANAL_MS = 3500
# textele care se pot rupe pe randuri: cate randuri au in skin (inaltimea din skin / randuri = inaltimea unui rand,
# folosita numai cand fontul nu se poate masura)
RANDURI_TEXT = {"titlu": 2, "text": 4, "detaliu": 2}
# cate randuri pot avea cel mult. Inaltimea unui rand e a fontului
# (lib/gdi/font.cpp, newLine: size->metrics.height, cu marimea textului aleasa in Setari), nu inaltimea din skin
# impartita la randuri: HdsCond 26 are 35 px la 100% si ~46 la 130%, iar skinul da detaliului 64 px pentru doua
# randuri, deci al doilea rand al detaliului tehnic („acordarea a esuat”) era taiat. Fereastra creste cat textele
# (la 130%, cu toate randurile la maxim, ~1060 px) si ramane in ecran.
RANDURI_MAXIME = {"titlu": 3, "text": 5, "detaliu": 3}

SKIN_REZERVA = """
<screen name="HdsEcranNegru" position="360,99" size="1200,928" backgroundColor="#00141C28" flags="wfNoBorder" zPosition="-2">
	<widget name="canal" position="40,24" size="1120,40" font="Regular;28" halign="center" valign="center" foregroundColor="#00C9D2E3" backgroundColor="#00141C28" transparent="1" noWrap="1" zPosition="1" />
	<widget name="titlu" position="40,68" size="1120,112" font="Regular;44" halign="center" valign="top" foregroundColor="#00FFFFFF" backgroundColor="#00141C28" transparent="1" zPosition="1" />
	<widget name="text" position="40,188" size="1120,176" font="Regular;32" halign="center" valign="top" foregroundColor="#00F2F4F8" backgroundColor="#00141C28" transparent="1" zPosition="1" />
	<widget name="chenar1" position="100,376" size="244,52" backgroundColor="#00F5B83D" zPosition="1" />
	<widget name="etic1" position="102,378" size="240,48" font="Regular;26" halign="center" valign="center" foregroundColor="#00F2F4F8" backgroundColor="#00141C28" noWrap="1" zPosition="2" />
	<widget name="chenar2" position="360,376" size="244,52" backgroundColor="#00F5B83D" zPosition="1" />
	<widget name="etic2" position="362,378" size="240,48" font="Regular;26" halign="center" valign="center" foregroundColor="#00F2F4F8" backgroundColor="#00141C28" noWrap="1" zPosition="2" />
	<widget name="chenar3" position="620,376" size="244,52" backgroundColor="#00F5B83D" zPosition="1" />
	<widget name="etic3" position="622,378" size="240,48" font="Regular;26" halign="center" valign="center" foregroundColor="#00F2F4F8" backgroundColor="#00141C28" noWrap="1" zPosition="2" />
	<widget name="chenar4" position="880,376" size="244,52" backgroundColor="#00F5B83D" zPosition="1" />
	<widget name="etic4" position="882,378" size="240,48" font="Regular;26" halign="center" valign="center" foregroundColor="#00F2F4F8" backgroundColor="#00141C28" noWrap="1" zPosition="2" />
	<widget name="semnal_text" position="120,444" size="240,40" font="Regular;28" halign="right" valign="center" foregroundColor="#00AEB9CC" backgroundColor="#00141C28" transparent="1" noWrap="1" zPosition="1" />
	<widget name="semnal" position="380,458" size="560,12" foregroundColor="#009FB4FF" backgroundColor="#002A3350" zPosition="1" />
	<widget name="semnal_val" position="960,444" size="140,40" font="Regular;28" halign="left" valign="center" foregroundColor="#00F2F4F8" backgroundColor="#00141C28" transparent="1" noWrap="1" zPosition="1" />
	<widget name="calitate_text" position="120,492" size="240,40" font="Regular;28" halign="right" valign="center" foregroundColor="#00AEB9CC" backgroundColor="#00141C28" transparent="1" noWrap="1" zPosition="1" />
	<widget name="calitate" position="380,506" size="560,12" foregroundColor="#004FD18B" backgroundColor="#002A3350" zPosition="1" />
	<widget name="calitate_val" position="960,492" size="140,40" font="Regular;28" halign="left" valign="center" foregroundColor="#00F2F4F8" backgroundColor="#00141C28" transparent="1" noWrap="1" zPosition="1" />
	<widget name="fapta" position="300,556" size="600,60" backgroundColor="#00374EA1" zPosition="1" />
	<widget name="fapta_tasta" position="324,566" size="72,40" font="Regular;26" halign="center" valign="center" foregroundColor="#00374EA1" backgroundColor="#00FFFFFF" noWrap="1" zPosition="2" />
	<widget name="fapta_text" position="412,556" size="480,60" font="Regular;30" halign="left" valign="center" foregroundColor="#00FFFFFF" backgroundColor="#00374EA1" transparent="1" noWrap="1" zPosition="2" />
	<widget name="detaliu" position="40,632" size="1120,64" font="Regular;26" halign="center" valign="top" foregroundColor="#00AEB9CC" backgroundColor="#00141C28" transparent="1" zPosition="1" />
	<widget name="pasi" position="100,704" size="1000,160" font="Regular;24" halign="left" valign="top" foregroundColor="#00C9D2E3" backgroundColor="#00141C28" transparent="1" noWrap="1" zPosition="1" />
	<widget name="indemn" position="40,872" size="1120,32" font="Regular;24" halign="center" valign="center" foregroundColor="#00AEB9CC" backgroundColor="#00141C28" transparent="1" noWrap="1" zPosition="1" />
</screen>"""


def _cheie(v):
	"""Ce schimba asezarea: textele si etichetele (nivelul si calitatea se schimba pe loc)."""
	if not v:
		return None
	f = v.get("fapta") or {}
	# pasii decriptarii: numai daca sunt (randurile lor se schimba pe loc, in valori)
	return (v.get("cod"), v.get("canal"), v.get("titlu"), v.get("text"), tuple(v.get("etichete") or ()), f.get("id"),
		f.get("text"), v.get("detaliu"), v.get("semnal") is not None, v.get("calitate") is not None, bool(v.get("pasi")))


def _procent_text(v):
	return (u"%d %%" % v) if v is not None else u"-"


def _nimic():
	"""Actiune fara efect: tasta e prinsa (ActionMap intoarce 1) si nu ajunge mai departe."""
	return None


class HdsEcranNegru(Screen):
	"""Fereastra mesajului; pune(v) aseaza un mesaj nou, valori(v) schimba numai nivelul si calitatea."""

	def __init__(self, session):
		self.skin = scaledSkin(SKIN_REZERVA, 1920)
		Screen.__init__(self, session)
		for rand in RANDURI:
			for nume in rand:
				if nume in ("semnal", "calitate"):
					self[nume] = ProgressBar()
				else:
					self[nume] = Label(u"")
		self["semnal_text"].setText(E._t(E.T_SEMNAL))
		self["calitate_text"].setText(E._t(E.T_CALITATE))
		self["fapta_tasta"].setText(u"OK")
		self["indemn"].setText(E._t(E.T_INDEMN))
		self.geom = None
		# randurile pasilor deja rupte pe caseta (HdsPasiDecriptare.asezate), pentru latimea si fontul de acum
		self._pasiMemorie = {}
		self._pasiCheie = None
		self.onLayoutFinish.append(self._citesteGeometria)

	# ---- geometria din skin

	def _citesteGeometria(self):
		try:
			g = {}
			for rand in RANDURI:
				for nume in rand:
					inst = self[nume].instance
					if inst is None:
						if nume in OPTIONALE:
							continue
						raise ValueError(nume)
					p, s = inst.position(), inst.size()
					g[nume] = (p.x(), p.y(), s.width(), s.height())
			p, s = self.instance.position(), self.instance.size()
			self.geom = {"w": g, "fereastra": (p.x(), p.y(), s.width(), s.height())}
		except Exception as e:
			print("[HdsEcranNegru] skinul nu are toate randurile (%s): fara asezare" % e)
			self.geom = None

	def _rand_sus(self, rand):
		return min(self.geom["w"][n][1] for n in rand)

	def _rand_jos(self, rand):
		return max(self.geom["w"][n][1] + self.geom["w"][n][3] for n in rand)

	# ---- continutul

	def pune(self, v):
		"""Mesaj nou: textele, ce se vede, asezarea."""
		self["canal"].setText(v.get("canal") or u"")
		self["titlu"].setText(v.get("titlu") or u"")
		self["text"].setText(v.get("text") or u"")
		etichete = list(v.get("etichete") or [])[:ETICHETE]
		for i in range(1, ETICHETE + 1):
			self["etic%d" % i].setText(etichete[i - 1] if i <= len(etichete) else u"")
		f = v.get("fapta")
		self["fapta_text"].setText(f["text"] if f else u"")
		self["detaliu"].setText(v.get("detaliu") or u"")
		self.valori(v)
		vazute = {
			0: bool(v.get("canal")),
			1: True,
			2: bool(v.get("text")),
			3: bool(etichete),
			4: v.get("semnal") is not None,
			5: v.get("calitate") is not None,
			6: bool(f),
			7: bool(v.get("detaliu")),
			8: bool(v.get("pasi")),
			9: True,
		}
		for i, rand in enumerate(RANDURI):
			for nume in rand:
				arata = vazute[i]
				if i == 3:
					k = int(nume[-1])
					arata = k <= len(etichete)
				if arata:
					self[nume].show()
				else:
					self[nume].hide()
		self._aseaza(vazute, len(etichete))

	def valori(self, v):
		for nume in ("semnal", "calitate"):
			val = v.get(nume)
			self[nume].setValue(val if val is not None else 0)
			self[nume + "_val"].setText(_procent_text(val))
		self["pasi"].setText(u"\n".join(self._pasiAsezati(v.get("pasi") or [])))

	def _pasiAsezati(self, pasi):
		"""Randurile pasilor in caseta lor: un rand mai lat decat caseta se rupe intre cuvinte, cu continuarea aliniata
		dupa timp (Components/HdsPasiDecriptare.asezate), cel mult PASI_RANDURI randuri de font. Masura o da eticheta
		insasi, cu fontul ei de acum (si cu textul marit): skinul ii da noWrap, deci calculateSize intoarce latimea
		intreaga a unui rand. Fara caseta in skin sau fara masura: randurile cum sunt, cele mai noi PASI_RANDURI."""
		pasi = list(pasi)
		inst = self["pasi"].instance
		if not pasi or inst is None or not hasattr(inst, "setText") or not hasattr(inst, "calculateSize"):
			return pasi[-PASI_RANDURI:]
		try:
			from Components import HdsPasiDecriptare as P
			latime = int(inst.size().width())
		except Exception:
			return pasi[-PASI_RANDURI:]
		rand_h = self._inaltimeRand("pasi", 0)
		cheie = (latime, rand_h)
		if cheie != self._pasiCheie:
			self._pasiMemorie = {}
			self._pasiCheie = cheie
		# masura e suma avansurilor literelor; ultima litera a unui rand poate iesi cu 1-2 px peste avansul ei (f, j,
		# fontul condensat), deci randul rupt lasa cativa px liberi la marginea casetei
		rezerva = max(4, rand_h // 8)

		def masoara(text):
			inst.setText(text)
			return int(inst.calculateSize().width())
		return P.asezate(pasi, latime - rezerva, masoara, PASI_RANDURI, self._pasiMemorie)

	# ---- asezarea

	def _latime_text(self, nume, implicit):
		try:
			return self[nume].instance.calculateSize().width()
		except Exception:
			return implicit

	def _inaltime_text(self, nume, implicit):
		try:
			return self[nume].instance.calculateSize().height()
		except Exception:
			return implicit

	def _inaltimeRand(self, nume, implicit):
		"""Inaltimea unui rand al etichetei `nume` cu fontul ei de acum (cu marimea textului aleasa), ca in
		Screens/MessageBox.py; `implicit` cand fontul nu se poate masura."""
		try:
			from enigma import fontRenderClass
			h = int(fontRenderClass.getInstance().getLineHeight(self[nume].instance.getFont()) or 0)
			if h > 0:
				return h
		except Exception:
			pass
		return implicit

	def _muta(self, nume, x, y, w=None, h=None):
		inst = self[nume].instance
		if inst is None:
			return
		inst.move(ePoint(int(x), int(y)))
		if w is not None and h is not None:
			inst.resize(eSize(int(w), int(h)))

	def _aseaza(self, vazute, n_etichete):
		if self.geom is None:
			return
		try:
			self._aseazaRanduri(vazute, n_etichete)
		except Exception as e:
			print("[HdsEcranNegru] asezare: %s" % e)

	def _aseazaRanduri(self, vazute, n_etichete):
		g = self.geom["w"]
		fx, fy, fw, fh = self.geom["fereastra"]
		sus0 = self._rand_sus(RANDURI[0])
		jos_ultim = self._rand_jos(RANDURI[-1])
		y = sus0
		jos_anterior = None
		for i, rand in enumerate(RANDURI):
			if not vazute[i] or not self._inSkin(rand):
				continue
			sus = self._rand_sus(rand)
			jos = self._rand_jos(rand)
			if jos_anterior is not None:
				# distanta din skin dintre acest rand si randul vazut dinainte lui in skin
				y += max(0, sus - self._jos_inainte(i))
			inaltime = jos - sus
			if rand[0] in RANDURI_TEXT:
				# textele care se pot rupe pe mai multe randuri: atatea randuri intregi cate are textul (cel mult
				# RANDURI_MAXIME), cu inaltimea randului fontului. calculateSize da cutia literelor desenate (de la
				# varful primului rand la coada ultimului), deci randurile sunt cutia / rand, rotunjit in sus (ca
				# MessageBox.inaltimeText); la capat cativa px pentru coada literelor de pe ultimul rand (ascender +
				# descender ale fontului trec cu 1-2 px de inaltimea randului).
				nume = rand[0]
				x0, y0, w0, h0 = g[nume]
				rand_h = max(1, self._inaltimeRand(nume, h0 // RANDURI_TEXT[nume]))
				maxim = RANDURI_MAXIME[nume]
				self._muta(nume, x0, y, w0, maxim * rand_h)
				cutie = self._inaltime_text(nume, h0)
				n = max(1, min(maxim, -(-(cutie - 2) // rand_h)))
				h = n * rand_h + max(2, rand_h // 10)
				self._muta(nume, x0, y, w0, h)
				inaltime = h
			elif rand[0] == "pasi":
				# o caseta de PASI_RANDURI randuri de font, oricate randuri are acum: textul ei se schimba in valori()
				# fara alta asezare (randul fontului, ca la textele de mai sus, cu marimea textului aleasa)
				x0, y0, w0, h0 = g["pasi"]
				rand_h = max(1, self._inaltimeRand("pasi", h0 // PASI_RANDURI))
				h = PASI_RANDURI * rand_h + max(2, rand_h // 10)
				self._muta("pasi", x0, y, w0, h)
				inaltime = h
			elif i == 3:
				self._aseazaEtichete(y, n_etichete)
			elif rand[0] == "fapta":
				self._aseazaFapta(y)
			else:
				for nume in rand:
					x0, y0, w0, h0 = g[nume]
					self._muta(nume, x0, y + (y0 - sus))
			y += inaltime
			jos_anterior = y
		inaltime_noua = y + (fh - jos_ultim)
		mijloc = fy + fh // 2
		sus = mijloc - inaltime_noua // 2
		# pe acelasi mijloc, dar in ecran (o fereastra mai inalta decat locul de sub mijloc urca)
		try:
			from enigma import getDesktop
			ecran = getDesktop(0).size().height()
		except Exception:
			ecran = 0
		if ecran > 0:
			sus = max(0, min(sus, ecran - inaltime_noua))
		self.instance.resize(eSize(fw, inaltime_noua))
		self.instance.move(ePoint(fx, sus))

	def _jos_inainte(self, i):
		# randul de dinainte din skin (un rand optional pe care skinul nu il are se sare)
		j = i - 1
		while j >= 0 and not self._inSkin(RANDURI[j]):
			j -= 1
		return self._rand_jos(RANDURI[j]) if j >= 0 else self._rand_sus(RANDURI[0])

	def _inSkin(self, rand):
		return all(n in self.geom["w"] for n in rand)

	def _aseazaEtichete(self, y, n):
		g = self.geom["w"]
		cx, cy, cw, ch = g["chenar1"]
		ex, ey, ew, eh = g["etic1"]
		margine = ex - cx
		spatiu = max(8, g["chenar2"][0] - (cx + cw))
		pad = max(8, eh // 2)
		latimi = []
		for i in range(1, n + 1):
			w = self._latime_text("etic%d" % i, ew - 2 * pad) + 2 * pad
			latimi.append(max(eh * 2, w))
		fw = self.geom["fereastra"][2]
		# fiecare caseta cat numele ei (cu textul marit numele e mai lat decat caseta din skin); cand toate nu incap in
		# fereastra (cu marginile din skin), cele mai late se strang la aceeasi latime, iar numele lor deruleaza in caseta
		loc = fw - 2 * cx - spatiu * max(0, n - 1) - 2 * margine * n
		if sum(latimi) > loc > 0:
			plafon = loc // n
			ramase = sorted(latimi)
			for k, w in enumerate(ramase):
				rest = len(ramase) - k
				if w * rest > loc - sum(ramase[:k]):
					plafon = (loc - sum(ramase[:k])) // rest
					break
			latimi = [min(w, max(ew, plafon)) for w in latimi]
		total = sum(w + 2 * margine for w in latimi) + spatiu * max(0, n - 1)
		x = max(0, (fw - total) // 2)
		for i, w in enumerate(latimi, 1):
			self._muta("chenar%d" % i, x, y, w + 2 * margine, ch)
			self._muta("etic%d" % i, x + margine, y + (ey - cy), w, eh)
			x += w + 2 * margine + spatiu

	def _aseazaFapta(self, y):
		g = self.geom["w"]
		bx, by, bw, bh = g["fapta"]
		kx, ky, kw, kh = g["fapta_tasta"]
		tx, ty, tw, th = g["fapta_text"]
		pad = kx - bx
		spatiu = tx - (kx + kw)
		fw = self.geom["fereastra"][2]
		latime_text = min(fw - 2 * pad - kw - spatiu - 40, self._latime_text("fapta_text", tw) + 8)
		latime = pad + kw + spatiu + latime_text + pad
		x = max(0, (fw - latime) // 2)
		self._muta("fapta", x, y, latime, bh)
		self._muta("fapta_tasta", x + pad, y + (ky - by), kw, kh)
		self._muta("fapta_text", x + pad + kw + spatiu, y + (ty - by), latime_text, th)


class HdsEcranNegruFereastra(HdsEcranNegru):
	"""Fereastra scurta de eroare a redarii cand mesajul de pe ecran e oprit din setari (si in MoviePlayer): aceeasi
	asezare si acelasi skin („HdsEcranNegru”), fara buton, deschisa prin Tools.Notifications (id „ZapError”, ca
	fereastra veche), inchisa de OK, EXIT sau dupa `secunde`."""

	def __init__(self, session, verdict, secunde=5):
		HdsEcranNegru.__init__(self, session)
		self.skinName = "HdsEcranNegru"
		self.verdict = dict(verdict or {}, fapta=None)
		# ca fereastra veche (MessageBox cu close_on_any_key): OK, EXIT si sagetile o inchid. Ridicarea sagetii (upUp...)
		# nu face nimic: fereastra se poate deschide cat o sageata e tinuta apasata, iar ridicarea ei ar inchide-o pe loc;
		# prinsa aici, nu mai lasa „unknown action” in jurnal
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self.close, "cancel": self.close,
			"up": self.close, "down": self.close, "left": self.close, "right": self.close,
			"upUp": _nimic, "downUp": _nimic, "leftUp": _nimic, "rightUp": _nimic,
			"upRepeated": _nimic, "downRepeated": _nimic, "leftRepeated": _nimic, "rightRepeated": _nimic,
		}, -1)
		self.onLayoutFinish.append(self._arata)
		self.secunde = secunde
		self.ceas = None
		if secunde > 0:
			from enigma import eTimer
			self.ceas = eTimer()
			self.ceas.callback.append(self.close)
			self.onExecBegin.append(self._porneste)

	def _arata(self):
		self.pune(self.verdict)

	def _porneste(self):
		if self.ceas is not None:
			self.ceas.start(self.secunde * 1000, True)


# ---------------------------------------------------------------- tastele


class HartaEcranNegru(ActionMap):
	"""Harta de taste a mesajului: tasta fara actiune merge mai departe fara nimic in jurnal; execBegin / execEnd
	(chemate de InfoBar cand devine sau nu mai e ecranul din fata) ajung la legatura."""

	def __init__(self, leg, actions, prio):
		ActionMap.__init__(self, CONTEXTE_TASTE, actions, prio)
		self.leg = leg

	def action(self, context, action):
		fn = self.actions.get(action)
		if fn is None:
			return 0
		try:
			return fn() or 0
		except Exception as e:
			print("[HdsEcranNegru] tasta %s: %s" % (action, e))
			return 0

	def execBegin(self):
		ActionMap.execBegin(self)
		self.leg.inFata(True)

	def execEnd(self):
		ActionMap.execEnd(self)
		self.leg.inFata(False)


# ---------------------------------------------------------------- legatura cu bara


class LegaturaEcranNegru(object):
	"""Tine fereastra si urmaritorul, hotaraste cand se vede mesajul si face faptele (de pe televizor si din web)."""

	def __init__(self, infobar):
		self.infobar = infobar
		self.session = infobar.session
		E.initConfig()
		self.ecran = self.session.instantiateDialog(HdsEcranNegru)
		self.urm = E.Urmaritor(self.session, self._verdictNou, infobar)
		self.verdict = None
		self.vizibil = False
		self.in_fata = False
		self.ascuns_de_om = None
		self.cheie_aratata = None
		self.harta = None
		self.bara_legata = False
		self.de_reluat = None
		# locul antenei schimbat: programul oprit, de pornit dupa ELIBERARE_CANAL_MS (_acordaDinNou)
		self.de_pornit = None
		self.ceas_pornire = None
		# referinta pentru care analiza fluxului a pornit singura (setarea „Automat”): o singura data pe serviciu, chiar
		# daca rezultatul iese din memoria analizei (HdsAnalizaFlux.PASTRAT_S); se uita la pornirea altui canal
		self.analiza_auto = None
		E.pune_legatura(self)
		# setarea schimbata (pe televizor sau din web) se vede imediat, nu abia la alt verdict
		try:
			from Components.config import config
			config.usage.hds_ecran_negru.addNotifier(self._setareSchimbata, initial_call=False)
		except Exception as e:
			print("[HdsEcranNegru] setarea nu se urmareste: %s" % e)

	def _setareSchimbata(self, element=None):
		self._actualizeaza()

	def legaHarta(self, harta):
		self.harta = harta
		harta.setEnabled(False)

	def _legaBara(self):
		"""A doua bara (pe tot ecranul) acopera mesajul: la aratarea si ascunderea ei se hotaraste din nou."""
		if self.bara_legata:
			return
		sb = getattr(self.infobar, "secondInfoBarScreen", None)
		if sb is None:
			return
		sb.onShow.append(self._actualizeaza)
		sb.onHide.append(self._actualizeaza)
		self.bara_legata = True

	# ---- evenimentele (InfoBarGenerics.InfoBarServiceErrorPopupSupport)

	def laStart(self):
		"""Serviciul porneste (zap, sau acelasi canal pornit din nou dupa standby, MoviePlayer ori cautare)."""
		self.ascuns_de_om = None
		_opresteAnaliza()
		if self.analiza_auto is not None and self.analiza_auto != self._refRedata():
			self.analiza_auto = None
		self.urm.laStart()

	def _refRedata(self):
		try:
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			return ref.toString() if ref is not None else None
		except Exception:
			return None

	def primesteVerdict(self):
		"""Serviciul redat poate primi mesajul de pe ecran: TV prin DVB, fara PiP si fara pauza. Radioul, PiP-ul,
		fisierele si fluxurile IP nu primesc verdictele acordarii (Components/HdsEcranNegru.analizeaza; fluxurile IP din
		liste primesc numai formatul de imagine numit), deci pentru ele eroarea acordarii ramane in fereastra scurta."""
		try:
			d = self.urm.fotografie()
		except Exception as e:
			print("[HdsEcranNegru] fotografie: %s: %s" % (type(e).__name__, e))
			return False
		if d.get("nimic") or d.get("radio") or d.get("pip") or d.get("pauza"):
			return False
		return d.get("fel") in E.FEL_DVB

	def laEveniment(self, nume):
		if nume == "evEnd":
			_opresteAnaliza()
		self.urm.laEveniment(nume)

	def inFata(self, da):
		self.in_fata = bool(da)
		self._legaBara()
		self._actualizeaza()
		if da:
			self.urm.acum()

	def actualizeazaAcum(self):
		"""Verdictul calculat acum (cerut de web), fara sa astepte ceasul."""
		v = self.urm.calculeaza()[0]
		if v != self.urm.verdict:
			self.urm.verdict = v
			self._verdictNou(v)

	def _verdictNou(self, v):
		if v is None or (self.ascuns_de_om is not None and v.get("cod") != self.ascuns_de_om):
			self.ascuns_de_om = None
		self.verdict = v
		self._actualizeaza()
		# cu mesajul oprit din setari nu se arata nimic pe televizor, deci nici citirea din demultiplexor nu porneste
		if v is not None and (v.get("fapta") or {}).get("id") == E.F_ANALIZA and E.analiza_automata() and E.pornit():
			self._analizaSingura(v)

	def _analizaSingura(self, v):
		"""Setarea „automat”: analiza porneste o singura data pe serviciu, cand apare mesajul (nu dupa o eroare)."""
		ref = v.get("ref")
		if not ref or ref == self.analiza_auto:
			return
		try:
			from Components import HdsAnalizaFlux as A
			if A.stare(ref)["stare"] == "nimic":
				self.analiza_auto = ref
				self.pornesteAnaliza()
		except Exception as e:
			print("[HdsEcranNegru] analiza singura: %s" % e)

	# ---- cand se vede

	def _inStandby(self):
		try:
			from Screens.Standby import inStandby
			return inStandby is not None
		except Exception:
			return False

	def _acoperitDeMotor(self, v):
		if v.get("cod") != E.ANTENA:
			return False
		try:
			from Components.config import config
			return bool(config.usage.showdish.value)
		except Exception:
			return False

	def _poateArata(self, v):
		if v is None or not E.pornit() or not self.in_fata or self._inStandby():
			return False
		if self.ascuns_de_om is not None and self.ascuns_de_om == v.get("cod"):
			return False
		sb = getattr(self.infobar, "secondInfoBarScreen", None)
		if sb is not None and sb.shown:
			return False
		return not self._acoperitDeMotor(v)

	def _actualizeaza(self):
		v = self.verdict
		arata = self._poateArata(v)
		try:
			if arata:
				cheie = _cheie(v)
				if cheie != self.cheie_aratata:
					self.ecran.pune(v)
					self.cheie_aratata = cheie
				else:
					self.ecran.valori(v)
				if not self.vizibil:
					self.ecran.show()
					self.vizibil = True
			elif self.vizibil:
				self.ecran.hide()
				self.vizibil = False
		except Exception as e:
			print("[HdsEcranNegru] %s: %s" % (type(e).__name__, e))
		if self.harta is not None:
			self.harta.setEnabled(self.vizibil)
		E.pune_stare(v, self.vizibil)

	# ---- tastele

	def _baraAscunsa(self):
		return not getattr(self.infobar, "shown", False)

	def ok(self):
		if not self.vizibil or not self._baraAscunsa():
			return 0
		f = (self.verdict or {}).get("fapta")
		if not f:
			return 0
		self.faFapta(f["id"])
		return 1

	def iesire(self):
		if not self.vizibil or not self._baraAscunsa():
			return 0
		self.ascunde()
		return 1

	def ascunde(self):
		if self.verdict is not None:
			self.ascuns_de_om = self.verdict.get("cod")
		self._actualizeaza()

	# ---- faptele

	def faptaDinWeb(self, fapta):
		"""(cod HTTP, mesaj) pentru fapta ceruta din web; numai fapta mesajului de acum, cu bara in fata."""
		self.actualizeazaAcum()
		v = self.verdict
		if v is None:
			return 409, E._t("Ecranul nu mai e negru. Nu mai e nimic de făcut.")
		if fapta == E.F_ASCUNDE:
			self.ascunde()
			return 200, E._t("Mesajul a fost ascuns pe televizor.")
		f = v.get("fapta")
		if not f or f.get("id") != fapta:
			return 409, E._t("Mesajul de pe televizor s-a schimbat. Reîncarcă pagina.")
		if fapta == E.F_ANALIZA:
			# din web analiza porneste fara sa deschida ecranul ei pe televizor; rezultatul se vede in pagina
			return (200, E._t(T_ANALIZA_PORNITA)) if self.pornesteAnaliza() else (200, E._t(T_ANALIZA_MERGE))
		if not self.in_fata:
			return 409, E._t("Pe televizor e deschis alt ecran. Închide-l, apoi încearcă din nou.")
		if self.faFapta(fapta) is False:
			return 500, E._t("Eroare pe receptor.")
		return 200, E._t("S-a pornit pe televizor.")

	def faFapta(self, fapta):
		"""Fapta mesajului pe televizor. -> False cand ecranul ei nu s-a putut deschide."""
		try:
			if fapta == E.F_CAUTA_TP:
				self._cautaTransponder()
			elif fapta == E.F_CAUTA:
				self._deschideCautarea(self._fel())
			elif fapta == E.F_INREGISTRARI:
				from Screens.TimerEdit import TimerEditList
				self.session.open(TimerEditList)
			elif fapta == E.F_COD:
				self._codParinti()
			elif fapta == E.F_TUNER:
				from Screens.Satconfig import NimSelection
				self.session.open(NimSelection)
			elif fapta == E.F_ANALIZA:
				self._deschideAnaliza()
			elif fapta == E.F_LOC:
				self._alegeLocul()
		except Exception as e:
			print("[HdsEcranNegru] fapta %s: %s: %s" % (fapta, type(e).__name__, e))
			return False
		return True

	# ---- faptele care deschid alte ecrane

	def _alegeLocul(self):
		"""Alegerea locului antenei (Screens/HdsLocul.py). Cu locul schimbat, canalul porneste din nou pe un acord nou,
		deci cu comanda de motor calculata din locul nou.

		Locul nou ajunge in nucleu prin sec.update() (Components/HdsLocul.seteaza), dar programul care ruleaza nu se
		reacordeaza singur, iar pornirea lui imediata (vechiul playService cu forceRestart) lua canalul pastrat de nucleu
		inca 3 s dupa oprire (lib/dvb/dvb.cpp, allocateChannel), fara acord nou si fara comanda de motor: locul nou
		intra abia la zap-ul urmator. Acum, ca in Components/HdsMotorPozitie.py (_acordaDinNou, _reia) si
		Components/HdsLnbAplicare.py: programul se opreste, se asteapta ELIBERARE_CANAL_MS pe eTimer si abia apoi
		porneste. seteaza() refuza sub o inregistrare, deci cu locul schimbat nicio inregistrare nu tine canalul. Fapta
		"loc" ceruta din web trece tot pe aici (faptaDinWeb -> faFapta)."""
		from Screens.HdsLocul import HdsLoculEcran
		ref = self.session.nav.getCurrentlyPlayingServiceReference()

		def gata(schimbat=False):
			if schimbat and ref is not None:
				self._acordaDinNou(ref)
		self.session.openWithCallback(gata, HdsLoculEcran)

	def _acordaDinNou(self, ref):
		"""programul se opreste acum si porneste dupa ELIBERARE_CANAL_MS, pe un canal nou (_pornesteDinNou)"""
		nav = self.session.nav
		if nav.getCurrentlyPlayingServiceReference() is not None:
			nav.stopService()
		self.de_pornit = ref
		if self.ceas_pornire is None:
			from enigma import eTimer
			self.ceas_pornire = eTimer()
			self.ceas_pornire.callback.append(self._pornesteDinNou)
		self.ceas_pornire.start(ELIBERARE_CANAL_MS, True)

	def _pornesteDinNou(self):
		ref, self.de_pornit = self.de_pornit, None
		if ref is None:
			return
		try:
			nav = self.session.nav
			if nav.getCurrentlyPlayingServiceReference() is not None:
				print("[HdsEcranNegru] in pauza a pornit alt program; nu il schimb")
				return
			from Screens import Standby
			standby = Standby.inStandby
			# un Screen e si dict: unul fara componente ar fi "fals", deci comparatia cu None
			if standby is not None:
				# Standby porneste la trezire numai programul oprit de el (Standby.py:64-92): i-l dam lui, altfel la
				# trezire ecranul ar ramane negru
				if getattr(standby, "prev_running_service", None) is None and \
						getattr(standby, "paused_service", None) is None:
					standby.prev_running_service = ref
				return
			# acelasi program care rula (deja trecut de controlul parental), acum pe un canal nou
			nav.playService(ref, checkParentalControl=False)
		except Exception as e:
			print("[HdsEcranNegru] programul nu a pornit din nou dupa locul nou: %s: %s" % (type(e).__name__, e))

	def _cititor(self):
		from Components.Converter import HdsCommon as C
		nav = self.session.nav
		service = nav.getCurrentService()
		ref = nav.getCurrentlyPlayingServiceReference()
		if service is None or ref is None:
			return C, None, ref
		return C, C.Reader(E._Sursa(service, ref), None), ref

	def _fel(self):
		try:
			C, r, ref = self._cititor()
			return r.kind() if r is not None else ""
		except Exception:
			return ""

	def _cautaTransponder(self):
		C, r, ref = self._cititor()
		if r is None:
			return
		fel = r.kind()
		parm = E.parametri_transponder(r.tp(), fel)
		feid = C.fe_number(r)
		if parm is None or feid < 0:
			self._deschideCautarea(fel)
			return
		if fel == "s":
			try:
				from Screens.ScanerSatelit import motiv_refuz
				tp = dict((camp, getattr(parm, camp)) for camp, _cheie in E.CAMPURI_TP["s"])
				if motiv_refuz(tp):
					self._deschideCautarea(fel)
					return
			except (ImportError, KeyError, AttributeError):
				pass
		from Screens.ServiceScan import ServiceScan
		self.de_reluat = ref
		self.session.openWithCallback(self._dupaCautare, ServiceScan, [{"transponders": [parm], "feid": feid, "flags": 0}])

	def _dupaCautare(self, *rezultat):
		ref, self.de_reluat = self.de_reluat, None
		if ref is not None and self.session.nav.getCurrentlyPlayingServiceReference() is None:
			self.session.nav.playService(ref)

	def _deschideCautarea(self, fel):
		if fel == "c":
			from Screens.ScanerCablu import ScanerCablu
			self.session.open(ScanerCablu, "banda")
		elif fel == "t":
			from Screens.ScanerTerestru import ScanerTerestru
			self.session.open(ScanerTerestru, "banda")
		else:
			from Screens.ScanerSatelit import ScanerSatelit
			self.session.open(ScanerSatelit, "satelit")

	def _codParinti(self):
		"""Canalul ales se porneste din nou prin navigatie, deci controlul parental cere codul. Un „Anulează” tinut
		minte (storeservicepincancel) nu mai lasa sa apara fereastra: se uita, fiindca omul cere acum codul."""
		ref = E.ref_selectata(self.infobar)
		if ref is None:
			return
		try:
			from Components.ParentalControl import parentalControl
			if getattr(parentalControl, "sessionPinCached", False) and not getattr(parentalControl, "sessionPinCachedValue", True):
				parentalControl.resetSessionPin()
		except Exception:
			pass
		self.session.nav.playService(ref)

	# ---- analiza fluxului (Components/HdsAnalizaFlux.py)

	def _serviciul(self):
		"""(serviciul redat, referinta ca text, numele, furnizorul), sau (None, "", "", "")."""
		nav = self.session.nav
		service = nav.getCurrentService()
		ref = nav.getCurrentlyPlayingServiceReference()
		if service is None or ref is None:
			return None, "", u"", u""
		sref = (self.verdict or {}).get("ref") or ref.toString()
		info = service.info()
		furnizor = u""
		try:
			from enigma import iServiceInformation
			furnizor = E._curat(info.getInfoString(iServiceInformation.sProvider) if info else u"", 60)
		except Exception:
			pass
		return service, sref, E.nume_din_info(info), furnizor

	def pornesteAnaliza(self):
		"""Porneste analiza serviciului redat. -> True daca a pornit acum, False daca mergea deja (sau nu se poate)."""
		from Components import HdsAnalizaFlux as A
		service, sref, nume, furnizor = self._serviciul()
		if service is None:
			return False
		if A.merge(sref):
			return False
		pornita = A.porneste(A.parametri(service, sref, nume, furnizor))
		self.urm.acum()
		return pornita

	def _deschideAnaliza(self):
		"""OK pe mesaj: ecranul analizei; un rezultat proaspat se arata direct, altfel porneste o analiza noua."""
		from Components import HdsAnalizaFlux as A
		_service, sref, nume, _furnizor = self._serviciul()
		if not sref:
			return
		if A.proaspat(sref) is None and not A.merge(sref):
			self.pornesteAnaliza()
		self.session.openWithCallback(self._dupaAnaliza, HdsAnalizaFluxEcran, sref, nume)

	def _dupaAnaliza(self, *rezultat):
		self.urm.acum()


T_ANALIZA_PORNITA = E.N_("Analiza fluxului a pornit. Rezultatul apare aici în câteva secunde.")
T_ANALIZA_MERGE = E.N_("Analiza fluxului merge deja.")


def _opresteAnaliza():
	try:
		from Components import HdsAnalizaFlux as A
		A.opreste(zap=True)
	except Exception as e:
		print("[HdsEcranNegru] analiza fluxului: %s" % e)


# ---------------------------------------------------------------- ecranul analizei fluxului

SKIN_ANALIZA_REZERVA = """
<screen name="HdsAnalizaFlux" position="72,40" size="1776,1000" backgroundColor="#00141C28" flags="wfNoBorder">
	<widget source="Title" render="Label" position="32,18" size="1712,56" font="Regular;40" foregroundColor="#00FFFFFF" backgroundColor="#00141C28" transparent="1" valign="center" noWrap="1" />
	<eLabel position="32,88" size="1712,1" backgroundColor="#00303A52" />
	<widget name="text" position="32,104" size="1712,808" font="Regular;30" foregroundColor="#00F2F4F8" backgroundColor="#00141C28" transparent="1" scrollbarMode="showOnDemand" />
	<widget name="progres" position="32,200" size="1712,12" foregroundColor="#009FB4FF" backgroundColor="#002A3350" zPosition="3" />
	<eLabel position="32,924" size="1712,1" backgroundColor="#00303A52" />
	<widget name="indemn" position="32,936" size="1712,44" font="Regular;28" halign="center" valign="center" foregroundColor="#00AEB9CC" backgroundColor="#00141C28" transparent="1" noWrap="1" />
</screen>"""


class HdsAnalizaFluxEcran(Screen):
	"""Rezultatul analizei fluxului, pe tot ecranul: sectiunile din HdsAnalizaFlux.sectiuni_text intr-o casuta
	derulabila. Cat merge analiza, randul de progres si bara lui se refac de patru ori pe secunda; dupa aceea nimic nu
	mai ruleaza. Sus / jos (si stanga / dreapta) = pagina, OK si EXIT inchid."""

	def __init__(self, session, sref, canal=u""):
		self.skin = scaledSkin(SKIN_ANALIZA_REZERVA, 1920)
		Screen.__init__(self, session)
		self.skinName = "HdsAnalizaFlux"
		from Components.ScrollLabel import ScrollLabel
		from Components import HdsAnalizaFlux as A
		self.A = A
		self.sref = sref
		self["text"] = ScrollLabel(u"")
		self["progres"] = ProgressBar()
		self["indemn"] = Label(u"")
		self["indemn"].setText(E._t(A.T_INDEMN))
		titlu = E._t(A.T_TITLU)
		self.setTitle(u"%s · %s" % (titlu, canal) if canal else titlu)
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self.close, "cancel": self.close,
			"up": self.sus, "down": self.jos, "left": self.sus, "right": self.jos,
			"upRepeated": self.sus, "downRepeated": self.jos,
			"upUp": _nimic, "downUp": _nimic, "leftUp": _nimic, "rightUp": _nimic,
			"leftRepeated": _nimic, "rightRepeated": _nimic,
		}, -1)
		self.ultimul = None
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.reface)
		self.onLayoutFinish.append(self.reface)
		self.onClose.append(self.ceas.stop)

	def sus(self):
		self["text"].pageUp()

	def jos(self):
		self["text"].pageDown()

	def reface(self):
		A = self.A
		s = A.stare(self.sref)
		citeste = s["stare"] == "citeste"
		if citeste:
			facute, stiute = s["progres"]
			text = E._t(A.T_CITESTE) % (facute, stiute)
			if getattr(A, "T_DUREAZA", None):
				text = text + u"\n" + E._t(A.T_DUREAZA)
			self["progres"].setValue(max(0, min(100, facute * 100 // max(1, stiute))))
			self.ceas.start(250, True)
		elif s["stare"] == "nimic":
			text = E._t(A.T_NICIO_ANALIZA)
		else:
			try:
				from Components.Converter.HdsCommon import upper
			except Exception:
				upper = None
			text = A.text_ecran(A.sectiuni_text(s["rezultat"]), upper)
		if citeste:
			self["progres"].show()
		else:
			self["progres"].hide()
		if text != self.ultimul:
			self.ultimul = text
			self["text"].setText(text)



def faLegatura(infobar):
	"""Legatura pentru bara canalelor, sau None cand fereastra nu se poate face (skin stricat, modul lipsa)."""
	try:
		return LegaturaEcranNegru(infobar)
	except Exception as e:
		print("[HdsEcranNegru] fara mesajul de ecran negru: %s: %s" % (type(e).__name__, e))
		return None
