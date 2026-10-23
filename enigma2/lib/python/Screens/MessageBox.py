# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components.MenuList import MenuList
from enigma import eTimer

# fara raspunsuri, un text lung face fereastra mai inalta (centrata), pana la atatea randuri, cat incape pe ecran
RANDURI_MAXIME_FARA_RASPUNS = 9
# cu raspunsuri (DA / NU), la fel: textul creste pana la atatea randuri, iar lista coboara sub el (de exemplu intrebarea
# de dupa instalare, 3 randuri intr-o caseta de skin de 2 randuri si jumatate, era taiata)
RANDURI_MAXIME_CU_RASPUNS = 9
# un text care nu incape nici in fereastra crescuta se arata pe pagini (CH+ si
# CH-, iar fara raspunsuri si sagetile); capatul paginilor care continua
URMARE_PAGINA = u" \u2026"


class _HartaPagini(ActionMap):
	"""CH+ si CH- (si |<< >>|, contextul listei de canale) pentru paginile textului. Tastele din context pe care nu le
	foloseste (rosu, verde, galben, albastru) merg mai departe, la harta ferestrei, fara „unknown action” in jurnal."""

	def action(self, context, action):
		fn = self.actions.get(action)
		if fn is None:
			return 0
		fn()
		return 1


def inaltimeText(continut, rand, inaltimeSkin, inaltimeMaxima):
	"""Inaltimea casetei de text a unei ferestre de mesaj, pentru `continut` px de text in randuri de `rand` px.
	Textul care incape in caseta din skin primeste numai randurile lui. Unul mai lung primeste cel mult
	`inaltimeMaxima` (fara raspunsuri: pana la marginea de jos a ferestrei), numai randuri intregi, ca sa nu fie taiat
	dupa randurile din skin; cu raspunsuri `inaltimeMaxima` = caseta din skin, deci ramane ca in skin. Fara inaltimea
	randului: textul + 8 px, cel mult caseta din skin."""
	if rand <= 0:
		return min(inaltimeSkin, continut + 8)
	# calculateSize da marginea desenului, fara coada literelor de pe ultimul rand: se ia numarul de randuri
	nevoie = max(1, -(-(continut - 2) // rand)) * rand
	if nevoie <= inaltimeSkin:
		return nevoie
	if inaltimeMaxima <= inaltimeSkin:
		return inaltimeSkin
	return max(inaltimeSkin, min(nevoie, (inaltimeMaxima // rand) * rand))


class MessageBox(Screen):
	TYPE_YESNO = 0
	TYPE_INFO = 1
	TYPE_WARNING = 2
	TYPE_ERROR = 3

	def __init__(self, session, text, type = TYPE_YESNO, timeout = -1, close_on_any_key = False, default = True, enable_input = True, msgBoxID = None, randuri = None):
		self.type = type
		Screen.__init__(self, session)

		self.msgBoxID = msgBoxID
		# cate randuri poate creste textul cu raspunsuri (DA / NU) inainte sa treaca pe pagini; un mesaj lung pe care
		# omul trebuie sa-l citeasca intreg inainte sa raspunda cere mai multe decat RANDURI_MAXIME_CU_RASPUNS
		self.randuriCuRaspuns = randuri or RANDURI_MAXIME_CU_RASPUNS

		self["text"] = Label(text)
		self["Text"] = StaticText(text)
		self["selectedChoice"] = StaticText()

		self.text = text
		self.close_on_any_key = close_on_any_key

		self["ErrorPixmap"] = Pixmap()
		self["QuestionPixmap"] = Pixmap()
		self["InfoPixmap"] = Pixmap()
		self.timerRunning = False
		self.initTimeout(timeout)

		self.list = []
		if type != self.TYPE_ERROR:
			self["ErrorPixmap"].hide()
		else:
			try:
				from Components import HdsAfisaj
				HdsAfisaj.mesaj("evenimente.eroare", True)
			except Exception:
				pass
		if type != self.TYPE_YESNO:
			self["QuestionPixmap"].hide()
		if type != self.TYPE_INFO:
			self["InfoPixmap"].hide()

		if type == self.TYPE_YESNO:
			# HDSatelit: raspunsurile cu litera mare ("Da" / "Nu"), ca in restul ferestrelor; "da" / "nu" mici raman
			# valorile setarilor (ConfigYesNo)
			if default == True:
				self.list = [ (_("Yes"), 0), (_("No"), 1) ]
			else:
				self.list = [ (_("No"), 1), (_("Yes"), 0) ]
		
		if self.list:
			self["selectedChoice"].setText(self.list[0][0])
		self["list"] = MenuList(self.list)

		# paginile textului, cand nu incape (_imparteInPagini, dupa asezarea ferestrei); harta lor se porneste numai atunci
		self.paginiText = []
		self.paginaText = 0
		self.cuTaste = enable_input
		self["paginiText"] = _HartaPagini(["ChannelSelectBaseActions"], {
			"nextBouquet": self.paginaAnterioara,
			"prevBouquet": self.paginaUrmatoare,
			"prevMarker": self.paginaAnterioara,
			"nextMarker": self.paginaUrmatoare,
		}, -1)
		self["paginiText"].setEnabled(False)

		self.onLayoutFinish.append(self._marimeDupaText)

		if enable_input:
			self["actions"] = ActionMap(["MsgBoxActions", "DirectionActions"],
				{
					"cancel": self.cancel,
					"ok": self.ok,
					"alwaysOK": self.alwaysOK,
					"up": self.up,
					"down": self.down,
					"left": self.left,
					"right": self.right,
					"upRepeated": self.up,
					"downRepeated": self.down,
					"leftRepeated": self.left,
					"rightRepeated": self.right,
					# ridicarea sagetii: nimic de facut, dar legata, ca jurnalul sa nu scrie „unknown action”
					"upUp": self._nimic,
					"downUp": self._nimic,
					"leftUp": self._nimic,
					"rightUp": self._nimic,
				}, -1)

	def _nimic(self):
		pass

	def _marimeDupaText(self):
		try:
			self._potrivesteInaltimea()
		except Exception as eroare:
			print("[MessageBox] marimea dupa text: %s" % eroare)
		try:
			self._imparteInPagini()
		except Exception as eroare:
			print("[MessageBox] paginile textului: %s" % eroare)

	def _imparteInPagini(self):
		"""Un text care nu incape in caseta lui (cat a ajuns dupa _potrivesteInaltimea: pana la 9 randuri, cat ecranul)
		se imparte pe pagini masurate cu eticheta insasi (Screens/Setup.imparteAjutorul: la spatii, cat mai multe
		cuvinte pe pagina, cu „…” la capatul celor care continua). Ultimul rand al fiecarei pagini spune pagina si
		tastele (_semnPagina; locul lui se masoara cu cele mai mari numere de pagina). Numai randuri intregi, ca la
		ScrollLabel. Un text care incape ramane exact ca inainte."""
		from enigma import fontRenderClass
		eticheta = self["text"].instance
		text = self.text
		# fara taste (enable_input=False) nimic n-ar putea schimba pagina: ramane ca inainte
		if eticheta is None or not text or not isinstance(text, str) or not self.cuTaste:
			return
		caseta = eticheta.size().height()
		rand = int(fontRenderClass.getInstance().getLineHeight(eticheta.getFont()) or 0)
		if rand <= 0:
			return
		caseta = (caseta // rand) * rand

		def inaltimea(t):
			eticheta.setText(t)
			return eticheta.calculateSize().height()

		# calculateSize da cutia literelor: 2 px de toleranta, ca in inaltimeText
		if inaltimea(text) - 2 <= caseta:
			eticheta.setText(text)
			return
		semn = max(1, -(-(inaltimea(self._semnPagina(88, 88)) - 2) // rand)) * rand
		loc = caseta - semn
		pagini = []
		if loc >= rand:
			from Screens.Setup import imparteAjutorul
			pagini = imparteAjutorul(text, lambda t: inaltimea(t) - 2 <= loc, URMARE_PAGINA)
		if len(pagini) < 2:
			eticheta.setText(text)
			return
		self.paginiText = pagini
		self.paginaText = 0
		self._arataPagina()
		self["paginiText"].setEnabled(True)

	def _semnPagina(self, pagina, pagini):
		p = _("page %d of %d") % (pagina, pagini)
		if self.list:
			return _("CH+ și CH-: altă pagină (%s)") % p
		return _("Sus, Jos, CH+ și CH-: altă pagină (%s)") % p

	def _arataPagina(self):
		n = len(self.paginiText)
		self["text"].setText(self.paginiText[self.paginaText] + "\n" + self._semnPagina(self.paginaText + 1, n))

	def _schimbaPagina(self, pas):
		if len(self.paginiText) < 2:
			return
		# omul citeste: fereastra nu se mai inchide singura
		self.stopTimer()
		p = max(0, min(len(self.paginiText) - 1, self.paginaText + pas))
		if p != self.paginaText:
			self.paginaText = p
			self._arataPagina()

	def paginaUrmatoare(self):
		self._schimbaPagina(1)

	def paginaAnterioara(self):
		self._schimbaPagina(-1)

	def _sageataPeText(self, pas):
		"""Fara raspunsuri, sagetile dau pagina textului impartit; cu raspunsuri raman ale listei."""
		if len(self.paginiText) > 1 and not self.list:
			self._schimbaPagina(pas)
			return True
		return False

	def _potrivesteInaltimea(self):
		"""Fereastra cat textul: un skin cu marime fixa (loc pentru cateva randuri si doua raspunsuri) lasa un gol
		mare sub un mesaj scurt. Numai cand skinul cere, cu parametrul MessageBoxDupaText (marginea de jos, in px,
		din <hdsparameters>). Textul se strange la inaltimea lui (cel putin un rand), lista urca sub el si ramane cum
		e in skin, iar fara raspunsuri dispare; fereastra se micsoreaza si ramane pe acelasi centru. Fara raspunsuri,
		un text mai lung decat caseta din skin coboara in locul listei (inaltimeText) si, cand nici asa nu incape,
		fereastra creste in sus si in jos, pe acelasi centru, pana la RANDURI_MAXIME_FARA_RASPUNS randuri (cel mult cat
		ecranul), in loc ca textul sa fie taiat. Cu raspunsuri, un text mai lung decat caseta din skin o face mai inalta (pana
		la RANDURI_MAXIME_CU_RASPUNS randuri sau cate cere parametrul `randuri`, cat incape pe ecran cu lista sub el), lista coboara cu aceeasi diferenta, iar
		fereastra creste pe acelasi centru. La micsorare nu se schimba nimic daca alt element al ferestrei ar ramane in
		afara ei."""
		from skin import getParameterFromSkin
		from enigma import eSize, ePoint, fontRenderClass, getDesktop
		marja, dinSkin = getParameterFromSkin("MessageBoxDupaText", 0)
		text = self["text"].instance
		if not dinSkin or self.instance is None or text is None:
			return
		pt, mt = text.position(), text.size()
		rand = int(fontRenderClass.getInstance().getLineHeight(text.getFont()) or 0)
		continut = text.calculateSize().height()
		lista = self["list"].instance
		cuLista = lista is not None and len(self.list) > 0
		fereastra = self.instance.size()
		maxima = mt.height() if cuLista else fereastra.height() - max(0, marja) - pt.y()
		ecran = 0
		if rand > 0:
			ecran = getDesktop(0).size().height()
			margini = 2 * pt.y() + 2 * max(0, marja)
			if not cuLista:
				maxima = max(maxima, min(RANDURI_MAXIME_FARA_RASPUNS * rand, ecran - margini))
			else:
				# sub text raman spatiul de pana la lista si lista, cum sunt in skin
				pl, ml = lista.position(), lista.size()
				sub = max(0, pl.y() - pt.y() - mt.height()) + ml.height()
				randuri = getattr(self, "randuriCuRaspuns", None) or RANDURI_MAXIME_CU_RASPUNS
				maxima = max(maxima, min(randuri * rand, ecran - margini - sub))
		inaltime = inaltimeText(continut, rand, mt.height(), maxima)
		scade = mt.height() - inaltime
		if cuLista:
			pl, ml = lista.position(), lista.size()
			if pl.y() < pt.y() + mt.height():
				return
			jos = pl.y() - scade + ml.height()
		else:
			jos = pt.y() + inaltime
		inaltimeNoua = jos + max(0, marja)
		if inaltimeNoua > fereastra.height() and (not ecran or inaltimeNoua > ecran):
			return
		pastrate = (self["text"], self["list"])
		widgeturi = [x for x in list(self.values()) + list(self.renderer) if x not in pastrate]
		for x in widgeturi + list(self.additionalWidgets):
			w = getattr(x, "instance", None)
			if w is None:
				continue
			p, m = w.position(), w.size()
			if m.width() > 2 and m.height() > 2 and p.y() + m.height() > inaltimeNoua:
				return
		text.resize(eSize(mt.width(), inaltime))
		if cuLista:
			lista.move(ePoint(pl.x(), pl.y() - scade))
		elif lista is not None:
			lista.hide()
		pozitie = self.instance.position()
		y = pozitie.y() + (fereastra.height() - inaltimeNoua) // 2
		if ecran:
			y = max(0, min(y, ecran - inaltimeNoua))
		self.instance.resize(eSize(fereastra.width(), inaltimeNoua))
		self.instance.move(ePoint(pozitie.x(), y))

	def initTimeout(self, timeout):
		self.timeout = timeout
		if timeout > 0:
			self.timer = eTimer()
			self.timer.callback.append(self.timerTick)
			self.onExecBegin.append(self.startTimer)
			self.origTitle = None
			if self.execing:
				self.timerTick()
			else:
				self.onShown.append(self.__onShown)
			self.timerRunning = True
		else:
			self.timerRunning = False

	def __onShown(self):
		self.onShown.remove(self.__onShown)
		self.timerTick()

	def startTimer(self):
		self.timer.start(1000)

	def stopTimer(self):
		if self.timerRunning:
			del self.timer
			self.onExecBegin.remove(self.startTimer)
			self.setTitle(self.origTitle)
			self.timerRunning = False

	def timerTick(self):
		if self.execing:
			self.timeout -= 1
			if self.origTitle is None:
				self.origTitle = self.instance.getTitle()
			self.setTitle(self.origTitle + " (" + str(self.timeout) + ")")
			if self.timeout == 0:
				self.timer.stop()
				self.timerRunning = False
				self.timeoutCallback()

	def timeoutCallback(self):
		print("Timeout!")
		self.ok()

	def cancel(self):
		self.close(False)

	def ok(self):
		if self.type == self.TYPE_YESNO:
			self.close(self["list"].getCurrent()[1] == 0)
		else:
			self.close(True)

	def alwaysOK(self):
		self.close(True)

	def up(self):
		if self._sageataPeText(-1):
			return
		self.move(self["list"].instance.moveUp)

	def down(self):
		if self._sageataPeText(1):
			return
		self.move(self["list"].instance.moveDown)

	def left(self):
		if self._sageataPeText(-1):
			return
		self.move(self["list"].instance.pageUp)

	def right(self):
		if self._sageataPeText(1):
			return
		self.move(self["list"].instance.pageDown)

	def move(self, direction):
		if self.close_on_any_key:
			self.close(True)
		self["list"].instance.moveSelection(direction)
		if self.list:
			self["selectedChoice"].setText(self["list"].getCurrent()[0])
		self.stopTimer()

	def __repr__(self):
		return str(type(self)) + "(" + self.text + ")"
