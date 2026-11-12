# -*- coding: UTF-8 -*-
# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_CENTER, RT_VALIGN_CENTER, getPrevAsciiCode
from .Screen import Screen
from Components.Language import language
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.Label import Label
from Components.HdsTextUnicode import stergeUltimaLitera
try:
	# HDSatelit: campul de text pe un rand (cand nu mai incape, se vede coada); fara modul, eticheta obisnuita
	from Components.HdsCampText import CampText
except ImportError:
	CampText = Label
from Components.Pixmap import Pixmap
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaTest, MultiContentEntryRectangle
from Components.SkinIcon import nativ, culoare, codBun, fontPictograme
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
from Tools.LoadPixmap import LoadPixmap

# HDSatelit: tasta Enter a tastaturii in alte imagini; pluginurile lor le dau ca style=. Aici numai numele, ca sa se
# incarce; tastatura noastra arata Enter la fel pentru toate.
VKB_DONE_ICON = 0
VKB_ENTER_ICON = 1
VKB_OK_ICON = 2
VKB_SAVE_ICON = 3
VKB_SEARCH_ICON = 4
VKB_DONE_TEXT = 5
VKB_ENTER_TEXT = 6
VKB_OK_TEXT = 7
VKB_SAVE_TEXT = 8
VKB_SEARCH_TEXT = 9


def antetPesteCamp(antet, camp):
	"""True daca eticheta tastaturii (instanta ei din skin) se suprapune peste campul de text: dreptunghiurile se ating.
	Fara una din ele (skinul nu le are), False."""
	if antet is None or camp is None:
		return False
	a, b = antet.position(), camp.position()
	la, lb = antet.size(), camp.size()
	if la.width() <= 0 or la.height() <= 0 or lb.width() <= 0 or lb.height() <= 0:
		return False
	return a.x() < b.x() + lb.width() and b.x() < a.x() + la.width() and \
		a.y() < b.y() + lb.height() and b.y() < a.y() + la.height()


def _dinTastatura():
	"""Ultima tasta a venit de la o tastatura adevarata (Components/HdsTastaturaUsb.py); fara modul, False."""
	try:
		from Components.HdsTastaturaUsb import dinTastatura
	except ImportError:
		return False
	return dinTastatura()


class VirtualKeyBoardList(MenuList):
	def __init__(self, list, enableWrapAround=False):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		self.l.setFont(0, gFont("Regular", 28))
		self.l.setItemHeight(45)
		if nativ("VirtualKeyboardNative"):
			# OE-Alliance: tastele desenate de tema (_tasteNative): textul mic al tastelor fara glifa si glifele
			self.l.setFont(1, gFont("Regular", 28 * 5 // 9))
			# glifele incap in tasta: cel mult inaltimea ei fara spatiul din jur (VirtualKeyboardNativeGeometry)
			spatiu = _parametruTastatura("VirtualKeyboardNativeGeometry", (4, 6, 2))[0]
			self.l.setFont(2, fontPictograme("VirtualKeyboardIcons", 28, max(12, 45 - 2 * int(spatiu))))

# OE-Alliance: VirtualKeyboardNative=1 in tema deseneaza tastele ca dreptunghiuri in culorile temei
# (VirtualKeyboardNativeColors: fond, fond ales, chenar, text, rosu, verde, galben, albastru; VirtualKeyboardNativeGeometry:
# spatiu, raza, chenar) cu glifele din VirtualKeyboardNativeIcons (13 coduri, in ordinea de mai jos), fontul
# <alias name="VirtualKeyboardIcons"/>. Latimile si ordinea tastelor raman ale tastaturii noastre.
_NUME_GLIFE = ("BACKSPACEICON", "DELETEICON", "ENTERICON", "EXITICON", "FIRSTICON", "LASTICON", "LEFTICON", "LOCALEICON",
	"RIGHTICON", "SHIFTICON", "SPACEICON", "TABICON", "CLEARICON")
_TASTA_GLIFA = {"EXIT": "EXITICON", "BACKSPACE": "BACKSPACEICON", "CLEAR": "CLEARICON", "SHIFT": "SHIFTICON",
	"SPACE": "SPACEICON", "OK": "ENTERICON"}


def _parametruTastatura(nume, implicit):
	try:
		from skin import parameters
		valoare = parameters.get(nume)
	except ImportError:
		valoare = None
	if isinstance(valoare, (tuple, list)) and len(valoare) >= len(implicit):
		return tuple(valoare[:len(implicit)])
	return implicit


def _tasteNative(keys, selectedKey, shiftMode, latimi):
	culori = _parametruTastatura("VirtualKeyboardNativeColors", (0x00202020, 0x00404040, 0x00ffffff, 0x00ffffff, 0x00cc4444, 0x0044cc66, 0x00ddcc44, 0x004488cc))
	fond, ales, chenar, text, rosu, verde, galben, albastru = [culoare(c) for c in culori]
	geometrie = _parametruTastatura("VirtualKeyboardNativeGeometry", (4, 6, 2))
	try:
		spatiu, raza, grosime = [max(0, int(v)) for v in geometrie]
	except (TypeError, ValueError):
		spatiu, raza, grosime = 4, 6, 2
	try:
		from skin import parameters
		coduri = parameters.get("VirtualKeyboardNativeIcons", ())
	except ImportError:
		coduri = ()
	if not isinstance(coduri, (tuple, list)):
		coduri = (coduri,)
	glife = dict((n, c) for n, c in zip(_NUME_GLIFE, coduri) if codBun(c))
	glife.setdefault("CLEARICON", glife.get("DELETEICON"))
	sublinieri = {"EXIT": rosu, "OK": verde, "SHIFT": albastru if shiftMode else galben}
	inaltime = 45
	res = [(keys)]
	x = 0
	for count, key in enumerate(keys):
		latime = latimi(key)
		activ = selectedKey == count
		w, h = max(1, latime - spatiu * 2), max(1, inaltime - spatiu * 2)
		fondTasta = ales if activ or (key == "SHIFT" and shiftMode) else fond
		res.append(MultiContentEntryRectangle(pos=(x + spatiu, spatiu), size=(w, h), backgroundColor=fondTasta,
			backgroundColorSelected=fondTasta, borderWidth=grosime if activ else 0, borderColor=chenar, borderColorSelected=chenar, cornerRadius=raza))
		if key in sublinieri and sublinieri[key] is not None:
			res.append(MultiContentEntryRectangle(pos=(x + spatiu + raza, inaltime - spatiu - grosime * 2), size=(max(1, w - raza * 2), max(1, grosime)),
				backgroundColor=sublinieri[key], backgroundColorSelected=sublinieri[key]))
		cod = glife.get(_TASTA_GLIFA.get(key, ""))
		if cod:
			eticheta, font = chr(cod), 2
		else:
			eticheta = "\u25cc" + key if len(key) == 1 and "\u064b" <= key <= "\u0652" else key
			font = 0 if len(eticheta) <= 2 else 1
		# textul pe toata tasta (ca in tastatura obisnuita), dreptunghiul cu spatiul din jur
		res.append(MultiContentEntryText(pos=(x, 0), size=(latime, inaltime), font=font, text=eticheta,
			flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, color=text, color_sel=text))
		x += latime
	return res

def VirtualKeyBoardEntryComponent(keys, selectedKey,shiftMode=False):
	key_backspace = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_backspace.png"))
	key_bg = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_bg.png"))
	key_clr = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_clr.png"))
	key_esc = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_esc.png"))
	key_ok = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_ok.png"))
	key_sel = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_sel.png"))
	key_shift = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_shift.png"))
	key_shift_sel = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_shift_sel.png"))
	key_space = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_space.png"))
	if nativ("VirtualKeyboardNative"):
		poze = {"EXIT": key_esc, "BACKSPACE": key_backspace, "CLEAR": key_clr, "SHIFT": key_shift, "SPACE": key_space, "OK": key_ok}
		def latimi(key):
			poza = poze.get(key, key_bg)
			return poza.size().width() if poza is not None else 45
		return _tasteNative(keys, selectedKey, shiftMode, latimi)
	res = [ (keys) ]
	
	x = 0
	count = 0
	if shiftMode:
		shiftkey_png = key_shift_sel
	else:
		shiftkey_png = key_shift
	for key in keys:
		width = None
		if key == "EXIT":
			width = key_esc.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_esc))
		elif key == "BACKSPACE":
			width = key_backspace.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_backspace))
		elif key == "CLEAR":
			width = key_clr.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_clr))
		elif key == "SHIFT":
			width = shiftkey_png.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=shiftkey_png))
		elif key == "SPACE":
			width = key_space.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_space))
		elif key == "OK":
			width = key_ok.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_ok))
		#elif key == "<-":
		#	res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(45, 45), png=key_left))
		#elif key == "->":
		#	res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(45, 45), png=key_right))
		
		else:
			width = key_bg.size().width()
			keyText = "\u25cc" + key if len(key) == 1 and "\u064b" <= key <= "\u0652" else key
			res.extend((
				MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_bg),
				MultiContentEntryText(pos=(x, 0), size=(width, 45), font=0, text=keyText, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER)
			))
		
		if selectedKey == count:
			width = key_sel.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_sel))

		if width is not None:
			x += width
		else:
			x += 45
		count += 1
	
	return res


class VirtualKeyBoard(Screen):

	def __init__(self, session, title="", text="", *extra, **optiuni):
		# HDSatelit: pluginurile altor imagini dau si maxSize, visible_width, type, currPos, allMarked, style, windowTitle; aici nu schimba
		# nimic (tastatura e aceeasi), dar nu mai opresc deschiderea. windowTitle, cand vine, e titlul ferestrei.
		Screen.__init__(self, session)
		from Components.HdsAsistentaControl import campSecret
		self.hdsCampSecret = bool(optiuni.get("hdsSecret") or campSecret(eticheta=title))
		titlu = optiuni.get("windowTitle")
		if titlu:
			self.onLayoutFinish.append(lambda: self.setTitle(titlu))
		self.keys_list = []
		self.shiftkeys_list = []
		self.lang = language.getLanguage()
		self.nextLang = None
		self.shiftMode = False
		self.text = text
		self.selectedKey = 0
		# HDSatelit: cu o tastatura adevarata tastele de pe ecran nu se arata (Components/HdsTastaturaUsb.py): ramane
		# campul de text, Enter = gata, Esc = renunta, Backspace = sterge; o sageata de pe telecomanda le aduce inapoi
		self.modTastatura = False
		# locul si marimea ferestrei din skin (pozitia de dat lui move, marimea fara rama), tinute minte la prima strangere
		self.locSkin = None
		
		self["country"] = StaticText("")
		self["key_green"] = StaticText(_("Confirm"))
		self["key_yellow"] = StaticText("")
		self["language"] = Label("")
		self["header"] = Label(title)
		# HDSatelit: campul pe un rand; cand textul nu mai incape, se vede coada lui, ce scrii acum
		# (Components/HdsCampText.py)
		self["text"] = CampText(self.text)
		self["list"] = VirtualKeyBoardList([])
		
		self["actions"] = ActionMap(["OkCancelActions", "WizardActions", "ColorActions", "KeyboardInputActions", "InputBoxActions", "InputAsciiActions"],
			{
				"gotAsciiCode": self.keyGotAscii,
				"ok": self.okClicked,
				"cancel": self.exit,
				"left": self.left,
				"right": self.right,
				"up": self.up,
				"down": self.down,
				"red": self.backClicked,
				"green": self.ok,
				"yellow": self.switchLang,
				"deleteBackward": self.backClicked,
				"back": self.exit				
			}, -2)
		self.setLang()
		self.onExecBegin.append(self.setKeyboardModeAscii)
		self.onLayoutFinish.append(self.buildVirtualKeyBoard)
		self.onLayoutFinish.append(self._antetPesteCamp)
		self.onLayoutFinish.append(self._laDeschidere)
		self._titluCerut = bool(titlu)

	def _antetPesteCamp(self):
		"""0.7.4 (forumul 768, JAKITAKI, o tema din afara): unele teme pun eticheta („header”) chiar peste campul de text,
		ca indemn, iar textul scris se suprapunea peste ea. Cand cele doua dreptunghiuri se ating, eticheta se ascunde si
		devine titlul ferestrei (daca cine a deschis tastatura n-a dat alt titlu). In tema noastra nu se ating: nimic."""
		try:
			if not antetPesteCamp(getattr(self["header"], "instance", None), getattr(self["text"], "instance", None)):
				return
			eticheta = self["header"].getText()
			self["header"].hide()
			if eticheta and not self._titluCerut:
				self.setTitle(eticheta)
		except Exception as e:
			print("[VirtualKeyBoard] eticheta peste camp: %r" % (e,))

	def _laDeschidere(self):
		if _dinTastatura():
			self.punModTastatura(True)

	def punModTastatura(self, da):
		self.modTastatura = da
		if da:
			self["list"].hide()
		else:
			self["list"].show()
		self._potrivesteFereastra()

	def _josCamp(self):
		"""Marginea de jos a campului de text in fereastra (cu fundalul si linia lui din skin, adica elementele
		eLabel/ePixmap care stau pe aceleasi randuri cu el) plus o margine egala cu cea din stanga campului; None fara
		camp."""
		text = getattr(self["text"], "instance", None)
		if text is None:
			return None
		sus = text.position().y()
		jos = sus + text.size().height()
		stanga = text.position().x()
		elemente = [getattr(w, "instance", None) for w in getattr(self, "additionalWidgets", [])]
		elemente = [e for e in elemente if e is not None]
		for _ in range(2):      # o linie lipita sub fundalul campului se vede abia dupa ce fundalul a crescut josul
			for e in elemente:
				y = e.position().y()
				h = e.size().height()
				if y < jos and y + h > sus:
					jos = max(jos, y + h)
					stanga = min(stanga, e.position().x())
		return jos + max(stanga, 0)

	def _potrivesteFereastra(self):
		"""Fara tastele de pe ecran fereastra se strange pana sub camp: tastele si randurile de sub ele raman in afara
		ei, deci sub camp nu mai ramane loc gol, pe orice skin (marimea vine din locul campului in skin). Fereastra
		ramane pe acelasi mijloc. Cu tastele inapoi (o sageata de pe telecomanda) ia din nou locul si marimea din skin."""
		inst = getattr(self, "instance", None)
		if inst is None:
			return
		try:
			from enigma import eSize, ePoint
		except ImportError:
			return
		if self.locSkin is None:
			# move() adauga deplasarea ramei ferestrei (titlul), iar position() o da cu ea: pozitia de dat lui move()
			# pentru locul din skin se afla mutand fereastra pe locul ei si vazand unde ajunge
			p = inst.position()
			inst.move(p)
			q = inst.position()
			self.locSkin = (ePoint(2 * p.x() - q.x(), 2 * p.y() - q.y()), inst.csize())
		poz, marime = self.locSkin
		h = marime.height()
		if self.modTastatura:
			jos = self._josCamp()
			if jos is not None:
				h = min(h, jos)
		inst.resize(eSize(marime.width(), h))
		inst.move(ePoint(poz.x(), poz.y() + (marime.height() - h) // 2))

	def _sageata(self):
		"""In modul tastatura: True = sageata nu misca nimic (de la tastatura nu are ce misca: campul nu are cursor);
		de la telecomanda tastele de pe ecran se arata din nou."""
		if not self.modTastatura:
			return False
		if not _dinTastatura():
			self.punModTastatura(False)
		return True
	
	def switchLang(self):
		self.lang = self.nextLang
		self.setLang()
		self.buildVirtualKeyBoard(self.selectedKey)

	def setLang(self):
		# Codurile scurte si cele cu cratima folosesc aceeasi asezare ca limba completa.
		cod = (self.lang or "en_EN").replace('-', '_').split('_', 1)[0].lower()
		self.lang = {"ar": "ar_AE", "de": "de_DE", "es": "es_ES", "fi": "fi_FI", "sv": "sv_SE",
			"sk": "sk_SK", "cs": "cs_CZ", "uk": "uk_UA", "ru": "ru_RU", "ro": "ro_RO"}.get(cod, "en_EN")
		if self.lang.replace('-', '_').split('_', 1)[0].lower() == 'ar':
			self.lang = 'ar_AE'
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["ض", "ص", "ث", "ق", "ف", "غ", "ع", "ه", "خ", "ح", "ج", "د"],
				["ش", "س", "ي", "ب", "ل", "ا", "ت", "ن", "م", "ك", "ط", "ذ"],
				["ئ", "ء", "ؤ", "ر", "ى", "ة", "و", "ز", "ظ", "،", ".", "CLEAR"],
				["SHIFT", "SPACE", "؟", "؛", "@", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "#", "$", "%", "&", "'", "(", ")", "=", "BACKSPACE"],
				["َ", "ً", "ُ", "ٌ", "ِ", "ٍ", "ْ", "ّ", "أ", "إ", "آ", "ٱ"],
				["ـ", "،", "؛", "؟", ":", "/", "\\", "-", "_", "+", "[", "]"],
				["<", ">", "{", "}", "|", "~", "`", "^", "*", ",", ".", "CLEAR"],
				["SHIFT", "SPACE", "@", "€", "؟", "OK"]]
			self.nextLang = 'en_EN'
		elif self.lang == 'de_DE':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ü", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ö", "ä", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "@", "ß", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "Ü", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ö", "Ä", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "OK"]]
			self.nextLang = 'es_ES'
		elif self.lang == 'es_ES':
			#still missing keys (u"ùÙ")
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ú", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ó", "á", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "@", "Ł", "ŕ", "é", "č", "í", "ě", "ń", "ň", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "Ú", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ó", "Á", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "Ŕ", "É", "Č", "Í", "Ě", "Ń", "Ň", "OK"]]
			self.nextLang = 'fi_FI'
		elif self.lang == 'fi_FI':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "é", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ö", "ä", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "@", "ß", "ĺ", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "É", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ö", "Ä", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "Ĺ", "OK"]]
			self.nextLang = 'sv_SE'
		elif self.lang == 'sv_SE':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "é", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ö", "ä", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "@", "ß", "ĺ", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "É", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ö", "Ä", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "Ĺ", "OK"]]
			self.nextLang = 'sk_SK'
		elif self.lang =='sk_SK':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ú", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ľ", "@", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "š", "č", "ž", "ý", "á", "í", "é", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "ť", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "ň", "ď", "'"],
				["Á", "É", "Ď", "Í", "Ý", "Ó", "Ú", "Ž", "Š", "Č", "Ť", "Ň"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "ä", "ö", "ü", "ô", "ŕ", "ĺ", "OK"]]
			self.nextLang = 'cs_CZ'
		elif self.lang == 'cs_CZ':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ú", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ů", "@", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "ě", "š", "č", "ř", "ž", "ý", "á", "í", "é", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "ť", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "ň", "ď", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "Č", "Ř", "Š", "Ž", "Ú", "Á", "É", "OK"]]
			self.nextLang = 'uk_UA'
		elif self.lang.replace('-', '_').split('_', 1)[0].lower() == 'uk':
			# HDSatelit (cererea unui tester, 30.10.2026): tastatura ucraineana, asezarea obisnuita a tastaturilor ucrainene
			# (ЙЦУКЕН), cu ґ, є, і, ї si apostroful; tot 5 randuri de 12 taste, ca restul
			self.lang = 'uk_UA'
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["й", "ц", "у", "к", "е", "н", "г", "ш", "щ", "з", "х", "ї"],
				["ф", "і", "в", "а", "п", "р", "о", "л", "д", "ж", "є", "ґ"],
				["я", "ч", "с", "м", "и", "т", "ь", "б", "ю", "'", ".", "CLEAR"],
				["SHIFT", "SPACE", ",", "-", "@", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "№", ";", "%", ":", "?", "*", "(", ")", "BACKSPACE"],
				["Й", "Ц", "У", "К", "Е", "Н", "Г", "Ш", "Щ", "З", "Х", "Ї"],
				["Ф", "І", "В", "А", "П", "Р", "О", "Л", "Д", "Ж", "Є", "Ґ"],
				["Я", "Ч", "С", "М", "И", "Т", "Ь", "Б", "Ю", "'", ",", "CLEAR"],
				["SHIFT", "SPACE", "_", "/", "+", "OK"]]
			self.nextLang = 'ru_RU'
		elif self.lang.replace('-', '_').split('_', 1)[0].lower() == 'ru':
			# HDSatelit: tastatura ruseasca (ЙЦУКЕН), cu ъ, э si ё; tot 5 randuri de 12 taste
			self.lang = 'ru_RU'
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["й", "ц", "у", "к", "е", "н", "г", "ш", "щ", "з", "х", "ъ"],
				["ф", "ы", "в", "а", "п", "р", "о", "л", "д", "ж", "э", "ё"],
				["я", "ч", "с", "м", "и", "т", "ь", "б", "ю", ".", ",", "CLEAR"],
				["SHIFT", "SPACE", "-", "@", "_", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "№", ";", "%", ":", "?", "*", "(", ")", "BACKSPACE"],
				["Й", "Ц", "У", "К", "Е", "Н", "Г", "Ш", "Щ", "З", "Х", "Ъ"],
				["Ф", "Ы", "В", "А", "П", "Р", "О", "Л", "Д", "Ж", "Э", "Ё"],
				["Я", "Ч", "С", "М", "И", "Т", "Ь", "Б", "Ю", "/", "+", "CLEAR"],
				["SHIFT", "SPACE", "'", "=", "\\", "OK"]]
			self.nextLang = 'ro_RO'
		elif self.lang == 'ro_RO':
			# HDSatelit: tastatura romaneasca (QWERTY, cu a, i, a cu caciula, s si t cu virgula dedesubt), tot 5 randuri de
			# 12 taste, ca restul (skinul are loc numai pentru atat)
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "\u0103", "\u00ee"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "\u0219", "\u021b", "\u00e2"],
				["-", "z", "x", "c", "v", "b", "n", "m", ",", ".", "@", "CLEAR"],
				["SHIFT", "SPACE", "_", "/", ":", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "#", "$", "%", "&", "'", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "\u0102", "\u00ce"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "\u0218", "\u021a", "\u00c2"],
				["+", "Z", "X", "C", "V", "B", "N", "M", ";", "?", "*", "CLEAR"],
				["SHIFT", "SPACE", "<", ">", "\\", "OK"]]
			self.nextLang = 'ar_AE'
		else:
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "+", "@"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "#", "\\"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "'", "?"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "OK"]]
			self.lang = 'en_EN'
			self.nextLang = 'de_DE'		
		self["country"].setText(self.lang)
		nume = {"en_EN": _("English"), "de_DE": _("German"), "es_ES": _("Spanish"), "fi_FI": _("Finnish"),
			"sv_SE": _("Swedish"), "sk_SK": _("Slovakian"), "cs_CZ": _("Czech"), "uk_UA": _("Ukrainian"),
			"ru_RU": _("Russian"), "ro_RO": _("Romanian"), "ar_AE": _("Arabic")}[self.lang]
		self["language"].setText(nume)
		self["key_yellow"].setText(nume)
		if hasattr(self["text"], "setRtl"):
			self["text"].setRtl(self.lang == 'ar_AE')
		self.max_key=47+len(self.keys_list[4])

	def buildVirtualKeyBoard(self, selectedKey=None):
		list = []
		if selectedKey is None:
			selectedKey = self.selectedKey
		self.k_list = self.shiftkeys_list if self.shiftMode else self.keys_list
		# Limba noua poate avea mai putine taste pe rand. Selectia desenata si cea folosita la OK raman identice.
		rand, coloana = divmod(max(0, selectedKey), 12)
		rand = min(rand, len(self.k_list) - 1)
		self.selectedKey = rand * 12 + min(coloana, len(self.k_list[rand]) - 1)
		selectedKey = self.selectedKey
		self.max_key = (len(self.k_list) - 1) * 12 + len(self.k_list[-1]) - 1
		
		if self.shiftMode:
			self.k_list = self.shiftkeys_list
			for keys in self.k_list:
				if selectedKey < 12 and selectedKey > -1:
					list.append(VirtualKeyBoardEntryComponent(keys, selectedKey,True))
				else:
					list.append(VirtualKeyBoardEntryComponent(keys, -1,True))
				selectedKey -= 12
		else:
			self.k_list = self.keys_list
			for keys in self.k_list:
				if selectedKey < 12 and selectedKey > -1:
					list.append(VirtualKeyBoardEntryComponent(keys, selectedKey))
				else:
					list.append(VirtualKeyBoardEntryComponent(keys, -1))
				selectedKey -= 12
		
		self["list"].setList(list)
	
	def backClicked(self):
		self.text = stergeUltimaLitera(self["text"].getText())
		self["text"].setText(self.text)
			
	def okClicked(self):
		if self.modTastatura:
			return self.ok()
		if self.shiftMode:
			list = self.shiftkeys_list
		else:
			list = self.keys_list
		
		selectedKey = self.selectedKey

		text = None

		for x in list:
			if selectedKey < 12:
				if selectedKey < len(x):
					text = x[selectedKey]
				break
			else:
				selectedKey -= 12

		if text is None:
			return
		if text not in ("EXIT", "BACKSPACE", "CLEAR", "SHIFT", "OK") and self._secretOprit():
			return

		if text == "EXIT":
			self.close(None)
		
		elif text == "BACKSPACE":
			self.backClicked()
		
		elif text == "CLEAR":
			self.text = ""
			self["text"].setText(self.text)
		
		elif text == "SHIFT":
			if self.shiftMode:
				self.shiftMode = False
			else:
				self.shiftMode = True
			
			self.buildVirtualKeyBoard(self.selectedKey)
		
		elif text == "SPACE":
			self.text += " "
			self["text"].setText(self.text)
		
		elif text == "OK":
			self.close(self["text"].getText())
		
		else:
			self.text = self["text"].getText()
			self.text += text
			self["text"].setText(self.text)

	def ok(self):
		self.close(self["text"].getText())

	def exit(self):
		self.close(None)

	def left(self):
		if self._sageata():
			return
		self.selectedKey -= 1
		
		if self.selectedKey == -1:
			self.selectedKey = 11
		elif self.selectedKey == 11:
			self.selectedKey = 23
		elif self.selectedKey == 23:
			self.selectedKey = 35
		elif self.selectedKey == 35:
			self.selectedKey = 47
		elif self.selectedKey == 47:
			self.selectedKey = self.max_key
		
		self.showActiveKey()

	def right(self):
		if self._sageata():
			return
		self.selectedKey += 1
		
		if self.selectedKey == 12:
			self.selectedKey = 0
		elif self.selectedKey == 24:
			self.selectedKey = 12
		elif self.selectedKey == 36:
			self.selectedKey = 24
		elif self.selectedKey == 48:
			self.selectedKey = 36
		elif self.selectedKey > self.max_key:
			self.selectedKey = 48
		
		self.showActiveKey()

	def up(self):
		if self._sageata():
			return
		self.selectedKey -= 12
		
		if (self.selectedKey < 0) and (self.selectedKey > (self.max_key-60)):
			self.selectedKey += 48
		elif self.selectedKey < 0:
			self.selectedKey += 60	
		
		self.showActiveKey()

	def down(self):
		if self._sageata():
			return
		self.selectedKey += 12
		
		if (self.selectedKey > self.max_key) and (self.selectedKey > 59):
			self.selectedKey -= 60
		elif self.selectedKey > self.max_key:
			self.selectedKey -= 48
		
		self.showActiveKey()

	def showActiveKey(self):
		self.buildVirtualKeyBoard(self.selectedKey)

	def inShiftKeyList(self,key):
		for KeyList in self.shiftkeys_list:
			for char in KeyList:
				if char == key:
					return True
		return False

	def keyGotAscii(self):
		# caracterele vin numai de la o tastatura adevarata (consola): tastele de pe ecran se ascund si se scrie orice
		# caracter, nu numai cele care sunt pe tastele de pe ecran
		char = chr(getPrevAsciiCode())
		if char >= " " and self._secretOprit():
			return
		if not self.modTastatura:
			self.punModTastatura(True)
		if char >= " ":
			self.text = self["text"].getText() + char
			self["text"].setText(self.text)

	def _secretOprit(self):
		from Components.HdsAsistentaControl import cereOprirePentruSecret
		return self.hdsCampSecret and cereOprirePentruSecret(self.session)


# numele OE-Alliance al ecranului (tema OverlayHD il importa; lotul TOT, 12.11.2026)
VirtualKeyboard = VirtualKeyBoard
