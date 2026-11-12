# -*- coding: utf-8 -*-
# HDSatelit 0.7.4: listele desenate dintr-un sablon XML, forma standardului OE-Alliance pe care o folosesc temele si
# pluginurile scrise pentru el (documentatia pentru dezvoltatori: network/list-templates, advanced/template-reference):
#
#   <widget source="list" render="Listbox" position="..." size="...">
#     <template name="Default" fonts="Regular;24,Regular;18" itemHeight="50">      (sau acelasi lucru in <templates>)
#       <mode name="default" itemWidth="..." itemHeight="...">                      (fara <mode>: copiii sunt modul "default")
#         <text index="Name" position="0,0" size="400,50" font="0" verticalAlignment="center" />
#         <pixmap index="Image" position="..." size="..." alpha="blend" scale="centerScaled" />
#         <rectangle position="..." size="..." backgroundColor="..." />
#         <progress index="Progress" position="..." size="..." />
#       </mode>
#       <rowtemplate> ... </rowtemplate>                                            (randul isi alege forma dupa row[0])
#     </template>
#   </widget>
#
# skin.py leaga singur convertorul (nu se scrie <convert type="XmlMultiContent">: argumentul e intern, un dict).
# Sablonul se alege dupa List.template (implicit "Default"), modul dupa List.style (implicit "default"). Un index e un
# numar (coloana randului) sau un nume din List.indexNames; o culoare "+Camp" se citeste din rand.
# Iese aceeasi lista de tupluri pe care o desena si TemplatedMultiContent (eListboxPythonMultiContent: TEXT, PIXMAP*,
# PROGRESS); dreptunghiul e un text gol cu fundal si chenar. Colturile rotunjite si degradeurile din sablon nu se
# deseneaza inca (se primesc si se lasa deoparte). Ecranele si temele HD Satelit nu folosesc forma asta: fara <template>
# in widget nimic nu se schimba.
import enigma
from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_HALIGN_CENTER, RT_HALIGN_RIGHT, \
	RT_VALIGN_TOP, RT_VALIGN_CENTER, RT_VALIGN_BOTTOM, RT_WRAP

from Components.Converter.StringList import StringList

RT_HALIGN_BLOCK = getattr(enigma, "RT_HALIGN_BLOCK", RT_HALIGN_LEFT)
BT_SCALE = getattr(enigma, "BT_SCALE", 4)
BT_KEEP_ASPECT_RATIO = getattr(enigma, "BT_KEEP_ASPECT_RATIO", 8)
BT_HALIGN_CENTER = getattr(enigma, "BT_HALIGN_CENTER", 16)
BT_HALIGN_RIGHT = getattr(enigma, "BT_HALIGN_RIGHT", 32)
BT_VALIGN_CENTER = getattr(enigma, "BT_VALIGN_CENTER", 64)
BT_VALIGN_BOTTOM = getattr(enigma, "BT_VALIGN_BOTTOM", 128)

_ORIZONTAL = {"left": RT_HALIGN_LEFT, "center": RT_HALIGN_CENTER, "right": RT_HALIGN_RIGHT, "block": RT_HALIGN_BLOCK}
_VERTICAL = {"top": RT_VALIGN_TOP, "center": RT_VALIGN_CENTER, "middle": RT_VALIGN_CENTER, "bottom": RT_VALIGN_BOTTOM}
_RUPE = ("wrap", "on", "1", "true", "yes")

_POZ_H = {"left": 0, "center": BT_HALIGN_CENTER, "middle": BT_HALIGN_CENTER, "right": BT_HALIGN_RIGHT}
_POZ_V = {"top": 0, "center": BT_VALIGN_CENTER, "middle": BT_VALIGN_CENTER, "bottom": BT_VALIGN_BOTTOM}


def steaguriPoza(valoare):
	"""scale= al unei poze din sablon -> steagurile poze din rand (BT_*): none/0, scale/1, keepAspect, centerScaled,
	leftTop.. rightBottom (scalate, proportii pastrate), scaleXxx (aceleasi, numele vechi), moveXxx (nescalate, mutate)"""
	v = (valoare or "").strip()
	if v in ("", "0", "none", "off"):
		return 0
	if v in ("1", "on", "scale", "stretch"):
		return BT_SCALE
	if v in ("keepAspect", "scaleKeepAspect", "aspect"):
		return BT_SCALE | BT_KEEP_ASPECT_RATIO
	baza = BT_SCALE | BT_KEEP_ASPECT_RATIO
	if v.startswith("move"):
		baza, v = 0, v[4:]
	elif v.startswith("scale"):
		v = v[5:]
	if v in ("Center", "Middle", "centerScaled", "middleScaled"):
		return baza | BT_HALIGN_CENTER | BT_VALIGN_CENTER
	v = v[:1].lower() + v[1:]
	for h in ("left", "center", "middle", "right"):
		if v.startswith(h):
			rest = v[len(h):].lower()
			if rest in _POZ_V:
				return baza | _POZ_H[h] | _POZ_V[rest]
	return BT_SCALE


def coordonata(text, parinte, scara=None):
	"""o coordonata din sablon, fata de cutia randului sau a panoului (parinte, in pixeli deja scalati): un numar (scalat
	cu scara (numarator, numitor)), center/c, e, e-N, c+N, N%; altceva -> 0"""
	t = (text or "0").strip()
	def scaleaza(n):
		return (2 * n * scara[0] + scara[1]) // (2 * scara[1]) if scara else n
	try:
		n = int(t)
		return scaleaza(n) if n >= 0 else -scaleaza(-n)
	except ValueError:
		pass
	if t.endswith("%"):
		try:
			return parinte * int(t[:-1]) // 100
		except ValueError:
			return 0
	for baza, valoare in (("center", parinte // 2), ("c", parinte // 2), ("e", parinte)):
		if t.startswith(baza):
			rest = t[len(baza):].strip()
			if not rest:
				return valoare
			try:
				n = int(rest[1:].strip())
			except ValueError:
				return valoare
			return valoare + scaleaza(n) if rest[0] == "+" else valoare - scaleaza(n)
	return 0


def _pereche(text, implicit=("0", "0")):
	parti = (text or "").split(",")
	if len(parti) != 2:
		return implicit
	return parti[0].strip(), parti[1].strip()


def umpleRand(tupluri, rand):
	"""tuplurile unui sablon (indexurile = coloanele randului) -> intrarea listei fara sablon C++ ([None, tuplu, ...]): textele,
	pozele, procentele si culorile "+Camp" citite din rand; o poza sau un procent lipsa nu se deseneaza"""
	def valoare(v):
		if isinstance(v, int) and 0 <= v < len(rand):
			return rand[v]
		return v

	def culoare(c):
		if isinstance(c, int) and c >> 24 == 0xff:
			v = rand[c & 0xffffff] if (c & 0xffffff) < len(rand) else None
			return v if isinstance(v, int) else None
		return c
	rez = [None]
	for t in tupluri:
		tip = t[0]
		if tip == eListboxPythonMultiContent.TYPE_TEXT:
			text = valoare(t[7]) if isinstance(t[7], int) else t[7]
			if text is None:
				text = ""
			elif not isinstance(text, str):
				text = str(text)
			rez.append(t[:7] + (text, culoare(t[8]), culoare(t[9]), culoare(t[10]), culoare(t[11])) + t[12:])
		elif tip == eListboxPythonMultiContent.TYPE_PROGRESS:
			p = valoare(t[5])
			if not isinstance(p, int):
				continue
			rez.append(t[:5] + (p,) + t[6:7] + tuple(culoare(c) for c in t[7:]))
		else:
			poza = valoare(t[5]) if isinstance(t[5], int) else t[5]
			if poza is None or isinstance(poza, (str, int)):
				continue
			rez.append(t[:5] + (poza, culoare(t[6]), culoare(t[7])) + t[8:])
	return rez


class XmlMultiContent(StringList):
	"""Lista de randuri (tupluri) a unei surse List, desenata dupa <template> din widget (vezi capul fisierului)."""

	def __init__(self, args):
		StringList.__init__(self, "")
		if not isinstance(args, dict):
			print("[XmlMultiContent] argumentul e intern (din skin.py), nu un text de <convert>")
			args = {}
		self.dom = args.get("dom")
		self.scara = args.get("scara")
		self.latimeWidget = int(args.get("itemWidth") or 0)
		self.inaltimeWidget = int(args.get("itemHeight") or 0)
		self.selectionEnabled = args.get("selectionEnabled", True)
		self.scrollbarMode = "showOnDemand"
		self.sablonActiv = None
		self.modActiv = None
		self.template = {"fonts": [], "modes": {}}
		self.indexNames = {}
		self.additionalTemplateAttributes = {}
		self.templateDataFormats = {}
		self.formeRand = None
		self.listaContinut = None
		self.functieRand = False
		self.dreptunghiPrimPlan = False

	# --- scara temei (resolution= al ecranului) ---
	def _sx(self):
		return self.scara.sx if self.scara is not None and self.scara.scaleaza else None

	def _sy(self):
		return self.scara.sy if self.scara is not None and self.scara.scaleaza else None

	def _sf(self):
		return self.scara.sf if self.scara is not None and self.scara.scaleaza else None

	@staticmethod
	def _ori(n, f):
		return (2 * n * f[0] + f[1]) // (2 * f[1]) if f else n

	def _font(self, text):
		from skin import parseFont
		text = text.strip()
		if self.scara is not None:
			try:
				text = self.scara.font(text)
			except Exception:
				pass
		return parseFont(text, ((1, 1), (1, 1)))

	# --- citirea sablonului ---
	def _alegeSablon(self, nume):
		"""elementul <template> cu numele cerut; fara el, "Default", apoi primul"""
		if self.dom is None:
			return None
		toate = self.dom.findall("template")
		for t in toate:
			if t.get("name", "Default") == nume:
				return t
		for t in toate:
			if t.get("name", "Default") == "Default":
				return t
		return toate[0] if toate else None

	def _index(self, valoare):
		"""index= -> numarul coloanei (int) sau None"""
		if valoare is None:
			return None
		v = valoare.strip()
		if v.lstrip("+-").isdigit():
			n = int(v)
			return n if n >= 0 else None
		n = self.indexNames.get(v)
		if n is None:
			print("[XmlMultiContent] indexul %r nu e in indexNames %s" % (v, sorted(self.indexNames)))
		return n

	def _culoare(self, valoare):
		"""o culoare din sablon -> argb (int) sau culoarea coloanei din rand (0xff000000 | index); None fara culoare"""
		if valoare is None or valoare == "":
			return None
		v = valoare.strip()
		if v[:1] in ("+", "=") and v[1:].isdigit():
			return 0xff000000 | int(v[1:])
		if v[:1] == "+":
			n = self.indexNames.get(v[1:])
			if n is None:
				print("[XmlMultiContent] culoarea %r nu e o coloana din indexNames" % v)
				return None
			return 0xff000000 | n
		try:
			from skin import parseColor
			argb = parseColor(v).argb()
		except Exception as e:
			print("[XmlMultiContent] culoarea %r: %s" % (v, e))
			return None
		# o culoare cu alfa ff s-ar citi ca index de coloana; ca in standard, alfa devine fe
		return argb - 0x1000000 if argb >> 24 == 0xff else argb

	def _poza(self, cale):
		from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
		from Tools.LoadPixmap import LoadPixmap
		try:
			return LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, cale))
		except Exception as e:
			print("[XmlMultiContent] poza %r: %s" % (cale, e))
			return None

	def _cutie(self, element, x0, y0, w, h):
		"""(x, y, latime, inaltime) ale unui element din sablon, fata de cutia parintelui (x0, y0, w, h)"""
		poz = element.get("position", "0,0")
		if poz == "fill":
			return x0, y0, w, h
		pw, ph = _pereche(element.get("size"), ("e", "e"))
		lat = coordonata(pw, w, self._sx())
		ina = coordonata(ph, h, self._sy())
		px, py = _pereche(poz)
		x = coordonata(px, w, self._sx())
		y = coordonata(py, h, self._sy())
		if px == "center":
			x = (w - lat) // 2
		if py == "center":
			y = (h - ina) // 2
		return x0 + x, y0 + y, max(0, lat), max(0, ina)

	def _padding(self, element):
		p = element.get("padding")
		if not p:
			return 0, 0, 0, 0
		try:
			v = [int(x) for x in p.split(",")]
		except ValueError:
			return 0, 0, 0, 0
		if len(v) == 1:
			v = v * 4
		elif len(v) == 2:
			v = [v[0], v[1], v[0], v[1]]
		elif len(v) != 4:
			return 0, 0, 0, 0
		sf = self._sf()
		return tuple(self._ori(x, sf) for x in v)

	def _elemente(self, parinte, x0, y0, w, h, rez):
		"""copiii unui mod / rand / panou -> rez: lista de (tip, atribute citite); panourile se desfac"""
		cursorStanga, cursorDreapta = x0, x0 + w
		orizontal = parinte.get("layout") == "horizontal"
		try:
			spatiu = int(parinte.get("spacing", "0"))
		except ValueError:
			spatiu = 0
		spatiu = self._ori(spatiu, self._sx())
		for el in parinte:
			tag = el.tag
			if tag not in ("text", "pixmap", "rectangle", "progress", "panel"):
				continue
			if not self._conditie(el):
				continue
			pozitie = (el.get("position") or "").split(",")
			if orizontal and pozitie[0].strip() in ("left", "right"):
				# panou orizontal: left/right iau loc de la stanga / dreapta; "e" in latime = locul ramas
				ramas = max(0, cursorDreapta - cursorStanga)
				pw, ph = _pereche(el.get("size"), ("0", "e"))
				lat = coordonata(pw, ramas, self._sx())
				ina = coordonata(ph, h, self._sy())
				dy = coordonata(pozitie[1], h, self._sy()) if len(pozitie) > 1 else 0
				if pozitie[0].strip() == "left":
					cutie = (cursorStanga, y0 + dy, lat, ina)
					cursorStanga += lat + spatiu
				else:
					cursorDreapta -= lat
					cutie = (cursorDreapta, y0 + dy, lat, ina)
					cursorDreapta -= spatiu
			else:
				cutie = self._cutie(el, x0, y0, w, h)
			if tag == "panel":
				self._elemente(el, cutie[0], cutie[1], cutie[2], cutie[3], rez)
				continue
			rez.append((tag, el, cutie))

	def _conditie(self, el):
		"""conditional= al unui element din sablon (cod al temei, ca in standard): fals sau gresit -> elementul nu se deseneaza"""
		c = el.get("conditional")
		if not c:
			return True
		try:
			from Components.config import config
			return bool(eval(c, {"__builtins__": {}}, {"config": config}))
		except Exception as e:
			print("[XmlMultiContent] conditional=%r: %s" % (c, e))
			return False

	def _tupluri(self, elemente):
		"""(tag, element, cutie) -> tuplurile listei; indexurile raman numere (C++ le citeste din rand)"""
		rez = []
		for tag, el, (x, y, w, h) in elemente:
			fundal = self._culoare(el.get("backgroundColor"))
			fundalSel = self._culoare(el.get("backgroundColorSelected"))
			chenar = el.get("borderWidth")
			try:
				chenar = self._ori(int(chenar), self._sf()) if chenar else None
			except ValueError:
				chenar = None
			culoareChenar = self._culoare(el.get("borderColor"))
			if tag == "text":
				st, su, dr, jo = self._padding(el)
				steaguri = _ORIZONTAL.get(el.get("horizontalAlignment", "left"), RT_HALIGN_LEFT) | \
					_VERTICAL.get(el.get("verticalAlignment", "top"), RT_VALIGN_TOP)
				if (el.get("wrap") or "").lower() in _RUPE:
					steaguri |= RT_WRAP
				index = self._index(el.get("index"))
				text = index if index is not None else el.get("text", "")
				try:
					font = int(el.get("font", "0"))
				except ValueError:
					font = 0
				if fundal is not None or fundalSel is not None or chenar:
					# fundalul si chenarul acopera cutia intreaga, textul sta in cutia micsorata cu padding
					if st or su or dr or jo:
						rez.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 0, RT_HALIGN_LEFT, "", None, None,
							fundal, fundalSel, chenar, culoareChenar))
						fundal = fundalSel = chenar = culoareChenar = None
				rez.append((eListboxPythonMultiContent.TYPE_TEXT, x + st, y + su, max(0, w - st - dr), max(0, h - su - jo),
					font, steaguri, text, self._culoare(el.get("foregroundColor")),
					self._culoare(el.get("foregroundColorSelected")), fundal, fundalSel, chenar, culoareChenar))
			elif tag == "pixmap":
				st, su, dr, jo = self._padding(el)
				index = self._index(el.get("index"))
				poza = index if index is not None else (self._poza(el.get("pixmap")) if el.get("pixmap") else None)
				if poza is None:
					continue
				alfa = el.get("alpha", "")
				tip = eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND if alfa == "blend" else \
					eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST if alfa in ("test", "on") else eListboxPythonMultiContent.TYPE_PIXMAP
				rez.append((tip, x + st, y + su, max(0, w - st - dr), max(0, h - su - jo), poza, fundal, fundalSel,
					steaguriPoza(el.get("scale"))))
			elif tag == "rectangle":
				if self.dreptunghiPrimPlan:
					# lista de canale (template-reference): dreptunghiul se umple cu foregroundColor
					fundal = self._culoare(el.get("foregroundColor")) if el.get("foregroundColor") else fundal
					fundalSel = self._culoare(el.get("foregroundColorSelected")) if el.get("foregroundColorSelected") else fundalSel
				rez.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 0, RT_HALIGN_LEFT, "", None, None,
					fundal, fundalSel, chenar, culoareChenar))
			elif tag == "progress":
				index = self._index(el.get("index"))
				if index is None:
					continue
				rez.append((eListboxPythonMultiContent.TYPE_PROGRESS, x, y, w, h, index, chenar or 0,
					self._culoare(el.get("foregroundColor")), self._culoare(el.get("foregroundColorSelected")),
					fundal, fundalSel))
		return rez

	def citesteSablon(self, nume):
		"""citeste <template> cu numele dat: fonturile, modurile ((latime, inaltime), tupluri) si randurile cu forma lor"""
		self.template = {"fonts": [], "modes": {}}
		self.formeRand = None
		sablon = self._alegeSablon(nume)
		if sablon is None:
			print("[XmlMultiContent] niciun <template> in widget")
			return
		try:
			latime = int(sablon.get("itemWidth", self.latimeWidget) or 0)
			inaltime = int(sablon.get("itemHeight", self.inaltimeWidget) or 0)
		except ValueError:
			latime, inaltime = self.latimeWidget, self.inaltimeWidget
		self.additionalTemplateAttributes = dict((k, v) for k, v in sablon.items() if k not in ("name", "fonts", "itemWidth", "itemHeight"))
		self.template["fonts"] = [self._font(f) for f in (sablon.get("fonts") or "Regular;20").split(",") if f.strip()]
		moduri = sablon.findall("mode") or [sablon]
		for mod in moduri:
			numeMod = "default" if mod is sablon else mod.get("name", "default")
			try:
				lat = int(mod.get("itemWidth", latime) or 0)
				ina = int(mod.get("itemHeight", inaltime) or 0)
			except ValueError:
				lat, ina = latime, inaltime
			latS, inaS = self._ori(lat, self._sx()), self._ori(ina, self._sy())
			elemente = []
			self._elemente(mod, 0, 0, latS or self._ori(self.latimeWidget, self._sx()) or 1920, inaS, elemente)
			self.template["modes"][numeMod] = ((latS, inaS), self._tupluri(elemente), mod.get("orientation"))
		randuri = sablon.findall("rowtemplate")
		if randuri:
			latS, inaS = self._ori(latime, self._sx()), self._ori(inaltime, self._sy())
			forme = []
			for r in randuri:
				elemente = []
				self._elemente(r, 0, 0, latS or 1920, inaS, elemente)
				forme.append(self._tupluri(elemente))
			self.formeRand = forme
			self.template["rowTemplates"] = forme
			self.template["rowSize"] = (latS, inaS)

	# --- randurile cu forma lor (rowtemplate): fara sablon in C++, fiecare rand se face aici ---
	def _rand(self, *rand):
		forme = self.formeRand or [[]]
		try:
			alegere = int(rand[0]) if rand else 0
		except (TypeError, ValueError):
			alegere = 0
		if not 0 <= alegere < len(forme):
			alegere = len(forme) - 1
		return umpleRand(forme[alegere], rand)

	# --- legatura cu sursa si cu lista ---
	def _randuri(self):
		lista = self.source.list if self.source is not None else []
		if all(isinstance(x, tuple) for x in lista):
			return lista
		return [x if isinstance(x, tuple) else tuple(x) if isinstance(x, list) else (x,) for x in lista]

	def _aplicaSablon(self):
		if self.source is None:
			return
		nume = getattr(self.source, "template", None) or getattr(self.source, "templateName", None) or "Default"
		if nume != self.sablonActiv:
			self.sablonActiv = nume
			self.modActiv = None
			self.citesteSablon(nume)
			for i, f in enumerate(self.template["fonts"]):
				self.content.setFont(i, f)
			try:
				self.source.additionalTemplateAttributes = self.additionalTemplateAttributes
				self.source.templateDataFormats = self.templateDataFormats
			except Exception:
				pass
			if self.formeRand:
				# forma randului se alege la desen (C++ cheama _rand pentru randurile vazute); fara sablon C++
				self.content.setBuildFunc(self._rand)
				self.functieRand = True
				lat, ina = self.template["rowSize"]
				if ina:
					self.content.setItemHeight(ina)
				if lat and hasattr(self.content, "setItemWidth"):
					self.content.setItemWidth(lat)
				return
			if self.functieRand:
				self.content.setBuildFunc(None)
				self.functieRand = False
		if self.formeRand:
			return
		stil = getattr(self.source, "style", None) or "default"
		if stil == self.modActiv:
			return
		moduri = self.template.get("modes") or {}
		mod = moduri.get(stil) or moduri.get("default") or (list(moduri.values())[0] if moduri else None)
		if mod is None:
			print("[XmlMultiContent] sablonul %r nu are niciun mod de desenat" % self.sablonActiv)
			return
		(lat, ina), tupluri, _orientare = mod
		self.content.setTemplate(tupluri)
		if ina:
			self.content.setItemHeight(ina)
		if lat and hasattr(self.content, "setItemWidth"):
			self.content.setItemWidth(lat)
		self.modActiv = stil

	def changed(self, what):
		if not self.content:
			self.content = eListboxPythonMultiContent()
			self.indexNames = getattr(self.source, "indexNames", None) or {}
		if what[0] == self.CHANGED_SPECIFIC and what[1] in ("style", "template"):
			pass
		elif self.source is not None:
			self.listaContinut = self._randuri()
			self.content.setList(self.listaContinut)
		self._aplicaSablon()
		self.downstream_elements.changed(what)

	def entry_changed(self, index):
		if not self.content or self.source is None:
			return
		lista = self.source.list
		if self.listaContinut is not lista and 0 <= index < len(lista) and self.listaContinut is not None and index < len(self.listaContinut):
			x = lista[index]
			self.listaContinut[index] = x if isinstance(x, tuple) else tuple(x) if isinstance(x, list) else (x,)
		self.content.invalidateEntry(index)
