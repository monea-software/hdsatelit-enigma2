# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components.MenuList import MenuList
from enigma import eTimer

# parametrul list al constructorului ascunde numele
type_list = list

# fara raspunsuri, un text lung face fereastra mai inalta (centrata), pana la atatea randuri, cat incape pe ecran
RANDURI_MAXIME_FARA_RASPUNS = 9
# cu raspunsuri (DA / NU), la fel: textul creste pana la atatea randuri, iar lista coboara sub el (de exemplu intrebarea
# de dupa instalare, 3 randuri intr-o caseta de skin de 2 randuri si jumatate, era taiata)
RANDURI_MAXIME_CU_RASPUNS = 9
# un text care nu incape nici in fereastra crescuta se arata pe pagini (CH+ si
# CH-, iar fara raspunsuri si sagetile); capatul paginilor care continua
URMARE_PAGINA = u" \u2026"

# Fereastra din tema HDSatelit (design-web-stitch/skin-pro/mesaje, Pro si Clasic; Eduard, 04.11.2026): bara si semnul colorate dupa
# fel, titlul, secundele ramase, textul, randurile cu semn in fata (puncte), raspunsurile si randul de jos cu tastele. Skinul o
# cere avand widgetul felBara; un alt skin ramane la asezarea veche (_potrivesteInaltimea), cu punctele scrise in text.
FEL_INFORMARE = "informare"
FEL_SUCCES = "succes"
FEL_AVERTISMENT = "avertisment"
FEL_EROARE = "eroare"
FEL_INTREBARE = "intrebare"
# numai pentru un rand din puncte: nota de sub lista, cu o linie deasupra, cu text mai sters
FEL_NOTA = "nota"
# rolurile din <colors> ale skinului, deci urmeaza si paleta aleasa
CULORI_FEL = {FEL_INFORMARE: "hdsBrand", FEL_SUCCES: "hdsGood", FEL_AVERTISMENT: "hdsWarn", FEL_EROARE: "hdsBad",
	FEL_INTREBARE: "hdsBrandLight", FEL_NOTA: "hdsBrand"}
PUNCTE_MAXIME = 8
# distantele ferestrei din tema, in px la 1080 de randuri
SPATIU = 16
SPATIU_NOTE = 14
PADDING_RAND = 5
MARGINE_ECRAN = 20


def titluFel(fel):
	"""Titlul ferestrei cand cine o deschide nu da altul"""
	return {FEL_SUCCES: _("Gata"), FEL_AVERTISMENT: _("Atenție"), FEL_EROARE: _("Error"),
		FEL_INTREBARE: _("Întrebare")}.get(fel) or _("Message")


def puncteCurate(puncte, fel):
	"""Randurile cu semn: [(fel, text)]; un rand dat numai ca text ia felul ferestrei. Randurile goale se sar."""
	rez = []
	for p in puncte or []:
		f, t = p if isinstance(p, (tuple, list)) else (fel, p)
		if t:
			rez.append((f or fel, t))
	return rez


def textCuPuncte(text, puncte):
	"""Tot textul, cu randurile dupa el, cu semn in fata: pentru un skin fara locul lor, un rezumat sau o pagina web."""
	return "\n".join(([text] if text else []) + ["\u2022 " + t for _f, t in puncte])


class _HartaPagini(ActionMap):
	"""CH+ si CH- (si |<< >>|, contextul listei de canale) pentru paginile textului. Tastele din context pe care nu le
	foloseste (rosu, verde, galben, albastru) merg mai departe, la harta ferestrei, fara „unknown action” in jurnal."""

	def action(self, context, action):
		fn = self.actions.get(action)
		if fn is None:
			return 0
		fn()
		return 1


def raspunsDinRand(valoare, dinApel=False):
	"""Ce intoarce OK pe un rand din raspunsuri. Randurile noastre au codurile 0 (Da) si 1 (Nu); o subclasa poate pune True si False, iar o
	lista data la apel (parametrul list) isi intoarce valorile ei, oricare ar fi."""
	if dinApel or isinstance(valoare, bool):
		return valoare
	if valoare == 0:
		return True
	if valoare == 1:
		return False
	return valoare


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
	# felurile fara semn ale altor imagini: se arata ca o informare
	TYPE_MESSAGE = 4
	TYPE_NOICON = 5
	secundeInText = False

	# Parametrii pana la title au ordinea din celelalte imagini (pluginurile lor ii dau si pozitional); ai nostri si celelalte nume ale lor
	# se dau numai cu nume, ca o valoare pozitionala straina sa nu ajunga in ei.
	# titlu: titlul ferestrei (altfel cel al felului). fel: FEL_SUCCES pentru un mesaj de reusita (altfel felul vine din type).
	# puncte: randurile cu semn in fata, cate un lucru pe rand, texte sau (fel, text); textul ramane deasupra lor.
	# picon, typeIcon: semnul aratat de skinurile care au semne (False: niciunul). simple, wizard, skin_name, skinName: numele ecranului din skin.
	# list: randurile de raspuns [(text, valoare)], iar OK intoarce valoarea. timeout_default: raspunsul cand se termina timpul.
	# showYESNO: raspunsurile Da si Nu si la alte feluri decat TYPE_YESNO.
	def __init__(self, session, text, type = TYPE_YESNO, timeout = -1, close_on_any_key = False, default = True, enable_input = True, msgBoxID = None,
			picon = None, simple = False, list = None, timeout_default = None, title = None, *, randuri = None, titlu = None, fel = None, puncte = None,
			wizard = False, skin_name = None, windowTitle = None, showYESNO = False, typeIcon = None, timeoutDefault = None, skinName = None,
			closeOnAnyKey = None, enableInput = None):
		# ordinea altor imagini: lista pe locul al cincilea
		if isinstance(close_on_any_key, (type_list, tuple)):
			list, close_on_any_key = close_on_any_key, False
		if closeOnAnyKey is not None:
			close_on_any_key = closeOnAnyKey
		if enableInput is not None:
			enable_input = enableInput
		self.type = type
		Screen.__init__(self, session)
		# numele din skin: cel cerut, apoi ecranul nostru, ca o subclasa straina fara ecran propriu sa nu ramana goala
		nume = skin_name or skinName
		nume = [nume] if isinstance(nume, str) else type_list(nume or [])
		if wizard:
			nume.append("MessageBoxWizard")
		if simple:
			nume.append("MessageBoxSimple")
		if self.__class__ is not MessageBox:
			nume.append(self.__class__.__name__)
		self.skinName = nume + ["MessageBox"] if nume else "MessageBox"
		self.timeout_default = timeout_default if timeout_default is not None else timeoutDefault
		self.fel = fel or {self.TYPE_YESNO: FEL_INTREBARE, self.TYPE_WARNING: FEL_AVERTISMENT,
			self.TYPE_ERROR: FEL_EROARE}.get(type, FEL_INFORMARE)
		self.puncte = puncteCurate(puncte, self.fel)
		# textSus: textul de deasupra randurilor; text: tot, cu randurile in el, cat nu se stie daca skinul are loc pentru ele
		self.textSus = text
		if self.puncte:
			text = textCuPuncte(text, self.puncte)
		# textul etichetei numai cat randurile stau separat (_aseazaCuTema); altfel e self.text, pe care il poate schimba si o subclasa
		self.textEticheta = None
		self.cuTema = False
		self.cuSecunde = False
		self["secunde"] = StaticText("")
		for nume in ("felBara", "felSemn", "ramaDr", "ramaJos", "linieNote", "linieJos"):
			self[nume] = Label("")
		self["tastaOk"] = Label("OK")
		self["indiciu"] = Label("")
		for i in range(PUNCTE_MAXIME):
			self["semn%d" % i] = Label("")
			self["punct%d" % i] = Label("")
		self.setTitle(titlu or title or windowTitle or titluFel(self.fel))

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
		self["WarningPixmap"] = Pixmap()
		self.timerRunning = False
		self.initTimeout(timeout)

		self.list = []
		# semnul: felul ferestrei, altul daca e cerut, niciunul la False
		semn = typeIcon if typeIcon is not None else picon
		if semn is None or semn is True:
			semn = type
		self.picon = semn is not False
		if type == self.TYPE_ERROR:
			try:
				from Components import HdsAfisaj
				HdsAfisaj.mesaj("evenimente.eroare", True)
			except Exception:
				pass
		for valoare, poza in ((self.TYPE_ERROR, "ErrorPixmap"), (self.TYPE_YESNO, "QuestionPixmap"), (self.TYPE_INFO, "InfoPixmap"), (self.TYPE_WARNING, "WarningPixmap")):
			if semn is False or semn != valoare:
				self[poza].hide()
		# temele straine (numele standard): o singura poza „icon” cu pozele in ordinea intrebare, informatie,
		# avertisment, eroare, mesaj (pixmaps="..."), aleasa dupa fel; numai sub alta tema decat HD Satelit
		from Components.HdsNumeStandard import adauga
		from Components.Pixmap import MultiPixmap
		if adauga(self, "icon", MultiPixmap) is not None:
			# fara poza ceruta (picon/typeIcon False): False == 0 in Python, deci intai self.picon
			self._semnOea = semn if self.picon and semn in (self.TYPE_YESNO, self.TYPE_INFO, self.TYPE_WARNING, self.TYPE_ERROR, self.TYPE_MESSAGE) else None
			self.onLayoutFinish.append(self._puneSemnOea)

		self.listaDinApel = bool(list)
		self.randInceput = 0
		if list:
			self.list = list
			if default is False:
				self.randInceput = 1
			elif default is not True and isinstance(default, int):
				self.randInceput = default
		elif type == self.TYPE_YESNO or showYESNO:
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

	def _puneSemnOea(self):
		"""poza „icon” a temelor straine: indexul = felul ferestrei (0 intrebare ... 4 mesaj); fara fel, ascunsa"""
		if self._semnOea is None:
			self["icon"].hide()
		else:
			self["icon"].setPixmapNum(self._semnOea)

	def _marimeDupaText(self):
		if self.randInceput:
			self["list"].moveToIndex(self.randInceput)
			if self["list"].getCurrent():
				self["selectedChoice"].setText(self["list"].getCurrent()[0])
		try:
			# orice componenta are instanta; numai cele din skin au atribute
			if self["felBara"].skinAttributes is not None:
				self.cuTema = True
				self.cuSecunde = any(getattr(r, "source", None) is self["secunde"] for r in self.renderer)
				self._aseazaCuTema()
			else:
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
		text = getattr(self, "textEticheta", None)
		if text is None:
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

	def _aseazaCuTema(self):
		"""Fereastra din tema, de sus in jos: titlul si linia lui, textul cat are nevoie, randurile cu semn (fiecare cu randurile
		lui, sub prima litera, nu sub semn), raspunsurile, randul de jos cu tastele; bara felului si marginile tin toata
		inaltimea, iar fereastra ramane pe acelasi centru. Etichetele pe un rand stau sus in caseta lor, iar caseta e pusa dupa
		inaltimea randului fontului: asa se aliniaza literele, indiferent de semnele din text (centrarea din skin se ia dupa
		literele din text). Ce nu incape pe ecran trece pe pagini (_imparteInPagini); randurile prea multe trec in text."""
		from enigma import eSize, ePoint, fontRenderClass, getDesktop
		from skin import parseColor
		ecran = getDesktop(0).size().height()

		def px(v):
			return int(round(v * ecran / 1080.0))
		randare = fontRenderClass.getInstance()

		def randDe(w):
			return int(randare.getLineHeight(w.getFont()) or 0) or px(40)

		def laMijloc(w, centru):
			r = randDe(w)
			w.move(ePoint(w.position().x(), centru - r // 2))
			w.resize(eSize(w.size().width(), r))

		culoare = parseColor(CULORI_FEL.get(self.fel, CULORI_FEL[FEL_INFORMARE]))
		for nume in ("felBara", "felSemn"):
			if self[nume].instance is not None:
				self[nume].instance.setBackgroundColor(culoare)
		# titlul si secundele: pe mijlocul semnului
		semnFel = self["felSemn"].instance
		if semnFel is not None:
			centru = semnFel.position().y() + semnFel.size().height() // 2
			for r in self.renderer:
				if getattr(r, "source", None) in (self["Title"], self["secunde"]) and getattr(r, "instance", None) is not None:
					laMijloc(r.instance, centru)
		eticheta = self["text"].instance
		pt, mt = eticheta.position(), eticheta.size()
		fereastra = self.instance.size()
		rand = randDe(eticheta)
		spatiu = px(SPATIU)
		y = pt.y()

		lista = self["list"].instance
		cuLista = lista is not None and len(self.list) > 0
		if cuLista and self.listaDinApel:
			lista.resize(eSize(lista.size().width(), min(len(self.list), 8) * int(lista.getItemHeight() or 56)))
		tasta, indiciu, linieJos = self["tastaOk"].instance, self["indiciu"].instance, self["linieJos"].instance
		cuBanda = bool(self.cuTaste and all(self[n].skinAttributes is not None for n in ("tastaOk", "indiciu", "linieJos")))
		inaltimeTasta = tasta.size().height() if tasta is not None else 0
		sub = spatiu + lista.size().height() if cuLista else 0
		sub += (spatiu + 1 + px(12) + inaltimeTasta + px(14)) if cuBanda else px(16)
		locEcran = ecran - 2 * px(MARGINE_ECRAN) - y - sub

		# randurile cu semn: masurate cu eticheta fiecaruia; prea multe sau prea inalte raman in text, pe pagini
		randuri, inaltimi = [], []
		if self["punct0"].skinAttributes is not None and len(self.puncte) <= PUNCTE_MAXIME:
			for i, (fel, text) in enumerate(self.puncte):
				w = self["punct%d" % i]
				if fel == FEL_NOTA:
					if indiciu is not None:
						w.instance.setFont(indiciu.getFont())
					w.instance.setForegroundColor(parseColor("hdsText2"))
				w.setText(text)
				r = randDe(w.instance)
				inaltimi.append(max(1, -(-(w.instance.calculateSize().height() - 2) // r)) * r + px(PADDING_RAND) * 2)
			cuNote = any(f == FEL_NOTA for f, _t in self.puncte)
			total = spatiu + sum(inaltimi) + (px(SPATIU_NOTE) if cuNote else 0)
			if self.puncte and total + (rand if self.textSus else 0) <= locEcran:
				randuri = self.puncte
				sub += total
				locEcran -= total
		if randuri:
			self.textEticheta = self.textSus
			self["text"].setText(self.textSus)
		for i in range(len(randuri), PUNCTE_MAXIME):
			self["semn%d" % i].hide()
			self["punct%d" % i].hide()
		if not any(f == FEL_NOTA for f, _t in randuri):
			self["linieNote"].hide()

		# textul: randuri intregi, cat are nevoie si cat incape pe ecran
		if self.textEticheta if self.textEticheta is not None else self.text:
			randuriMaxime = (getattr(self, "randuriCuRaspuns", None) or RANDURI_MAXIME_CU_RASPUNS) if cuLista else RANDURI_MAXIME_FARA_RASPUNS
			maxima = max(rand, min(randuriMaxime * rand, locEcran))
			nevoie = max(1, -(-(eticheta.calculateSize().height() - 2) // rand)) * rand
			inaltime = min(nevoie, (maxima // rand) * rand)
			eticheta.resize(eSize(mt.width(), inaltime))
			y += inaltime
		else:
			eticheta.hide()
			y -= spatiu

		if randuri:
			y += spatiu
			nota = False
			for i, (fel, _text) in enumerate(randuri):
				if fel == FEL_NOTA and not nota:
					nota = True
					self["linieNote"].instance.move(ePoint(pt.x(), y + px(SPATIU_NOTE) // 2 - 1))
					y += px(SPATIU_NOTE)
				semn, w = self["semn%d" % i].instance, self["punct%d" % i].instance
				r = randDe(w)
				semn.move(ePoint(semn.position().x(), y + px(PADDING_RAND) + (r - semn.size().height()) // 2))
				semn.setBackgroundColor(parseColor(CULORI_FEL.get(fel, CULORI_FEL[FEL_INFORMARE])))
				w.move(ePoint(w.position().x(), y + px(PADDING_RAND)))
				w.resize(eSize(w.size().width(), inaltimi[i] - 2 * px(PADDING_RAND)))
				y += inaltimi[i]
		if cuLista:
			y += spatiu
			lista.move(ePoint(lista.position().x(), y))
			y += lista.size().height()
		elif lista is not None:
			lista.hide()

		if cuBanda:
			y += spatiu
			linieJos.move(ePoint(linieJos.position().x(), y))
			y += 1 + px(12)
			if cuLista:
				# la o intrebare, tastele se spun intr-o fraza, pe tot randul
				self["tastaOk"].hide()
				indiciu.move(ePoint(pt.x(), y))
				indiciu.resize(eSize(mt.width(), indiciu.size().height()))
				self["indiciu"].setText(_("Alege cu săgețile și apasă OK.") if self.listaDinApel else _("Săgețile sus și jos aleg, OK confirmă, EXIT înseamnă „Nu”."))
			else:
				tasta.move(ePoint(tasta.position().x(), y))
				self["indiciu"].setText(_("Închide"))
			laMijloc(indiciu, y + inaltimeTasta // 2)
			y += inaltimeTasta + px(14)
		else:
			for nume in ("tastaOk", "indiciu", "linieJos"):
				self[nume].hide()
			y += px(16)

		if self["felBara"].instance is not None:
			self["felBara"].instance.resize(eSize(self["felBara"].instance.size().width(), y))
		if self["ramaDr"].instance is not None:
			self["ramaDr"].instance.resize(eSize(self["ramaDr"].instance.size().width(), y))
		if self["ramaJos"].instance is not None:
			self["ramaJos"].instance.move(ePoint(0, y - 1))
		pozitie = self.instance.position()
		sus = max(0, min(pozitie.y() + (fereastra.height() - y) // 2, ecran - y))
		self.instance.resize(eSize(fereastra.width(), y))
		self.instance.move(ePoint(pozitie.x(), sus))

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
			if self.cuTema and self.cuSecunde:
				self["secunde"].setText("")
			else:
				self.setTitle(self.origTitle)
			self.timerRunning = False

	def timerTick(self):
		if self.execing:
			self.timeout -= 1
			if self.cuTema and self.cuSecunde:
				# secundele au locul lor, la dreapta titlului; ModeQuestion le scrie in text, ca pana acum
				if not self.secundeInText:
					self["secunde"].setText(_("Se închide în %d s") % self.timeout)
			else:
				if self.origTitle is None:
					self.origTitle = self.instance.getTitle()
				self.setTitle(self.origTitle + " (" + str(self.timeout) + ")")
			if self.timeout == 0:
				self.timer.stop()
				self.timerRunning = False
				self.timeoutCallback()

	def timeoutCallback(self):
		print("Timeout!")
		if self.timeout_default is not None:
			self.close(self.timeout_default)
		else:
			self.ok()

	def cancel(self):
		self.close(False)

	def ok(self):
		if self.list:
			self.close(raspunsDinRand(self["list"].getCurrent()[1], self.listaDinApel))
		else:
			self.close(True)

	def yes(self):
		self.close(True)

	def no(self):
		self.close(False)

	def autoResize(self):
		"""Pentru skinurile care o cheama dintr-un applet: fereastra se potriveste singura, dupa asezare (_marimeDupaText)."""
		pass

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
