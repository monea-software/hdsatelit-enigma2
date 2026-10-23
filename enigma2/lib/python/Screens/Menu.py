# Modificat de moneasoftware.com si hdsatelit.com, 2026
import importlib
import os
from .Screen import Screen
from Components.Sources.List import List
from Components.ActionMap import NumberActionMap, ActionMap
from Components.Sources.StaticText import StaticText
from Components.config import configfile
from Components.PluginComponent import plugins
from Components.config import config
from Components.SystemInfo import SystemInfo
from Components import HdsDale

from Tools.Directories import resolveFilename, SCOPE_SKIN

import xml.etree.ElementTree

from Screens.Setup import Setup, getSetupTitle

# HDSatelit: semnele „(în lucru)” / „(netestat)” din atributul stare= al lui menu.xml
#; aceeasi functie pune semnul si in interfata web. Fara modul, numele
# simplu: meniul merge oricum.
try:
	from Components.HdsStareMeniu import textNod as _hdsTextNod
except ImportError:
	def _hdsTextNod(nod, traducere, text=None):
		return text if text is not None else traducere(nod.get("text") or "??")
try:
	from Components.HdsStareMeniu import stare as _hdsStare
except ImportError:
	def _hdsStare(nod):
		return None

# HDSatelit: meniul cu dale (aspectul "dale" din config.skin.layout_meniu): 3 dale pe rand, cu pictograma, nume, cifra si
# eticheta de stare (Components/HdsDale.py: geometria, ruperea numelor, mutarea, tuplul randului si sablonul lui).
# Fiecare intrare a meniului e un tuplu cu aceeasi forma, oriunde e facuta (menu.xml, menuupdater, extensii):
#   (titlu_cu_semn, functie, entryID, greutate, titlu_simplu, stare, glif)
# Modul lista foloseste primul element, ca inainte; modul dale foloseste titlul simplu, starea (eticheta) si glif-ul
# (atributul pictograma= din menu.xml; extensiile primesc toate pictograma generica).
HDS_COLOANE_DALE = HdsDale.COLOANE

#		<item text="TV-Mode">self.setModeTV()</item>
#		<item text="Radio-Mode">self.setModeRadio()</item>
#		<item text="File-Mode">self.setModeFile()</item>
#			<item text="Sleep Timer"></item>


# read the menu
mdom = xml.etree.ElementTree.parse(resolveFilename(SCOPE_SKIN, 'menu.xml'))


def intrareMeniu(titlu, functie, entryID, greutate, simplu=None, stare=None, glif=None):
	"""Tuplul unei intrari de meniu, cu aceeasi forma pentru toate (vezi mai sus)."""
	return (titlu, functie, entryID, greutate, titlu if simplu is None else simplu, stare,
		HdsDale.glifCurat(glif) or HdsDale.GLIF_INTRARE)


def _glifNod(nod):
	return nod.get("pictograma")


def skinulAreDale():
	"""True cand skinul cu care a pornit interfata e HDSatelit si are ecranul MenuDale; altfel meniul ramane lista
	(meniul nu are voie sa iasa stricat pe niciun skin)."""
	try:
		import skin
		alt = getattr(skin, "altSkinActiv", None)
		if alt is not None and alt():
			return False
		return skin.lookupScreen("MenuDale", 0)[0] is not None
	except Exception:
		return False


def aspectDale():
	try:
		return config.skin.layout_meniu.value == "dale"
	except AttributeError:
		return False


class boundFunction:
	def __init__(self, fnc, *args):
		self.fnc = fnc
		self.args = args
	def __call__(self):
		self.fnc(*self.args)

class MenuUpdater:
	def __init__(self):
		self.updatedMenuItems = {}

	def addMenuItem(self, id, pos, text, module, screen, weight):
		if not self.updatedMenuAvailable(id):
			self.updatedMenuItems[id] = []
		self.updatedMenuItems[id].append([text, pos, module, screen, weight])

	def delMenuItem(self, id, pos, text, module, screen, weight):
		self.updatedMenuItems[id].remove([text, pos, module, screen, weight])

	def updatedMenuAvailable(self, id):
		return id in self.updatedMenuItems

	def getUpdatedMenu(self, id):
		return self.updatedMenuItems[id]

menuupdater = MenuUpdater()

class MenuSummary(Screen):
	skin = """
	<screen position="0,0" size="132,64">
		<widget source="parent.title" render="Label" position="6,4" size="120,21" font="Regular;18" />
		<widget source="parent.menu" render="Label" position="6,25" size="120,21" font="Regular;16">
			<convert type="StringListSelection" />
		</widget>
		<widget source="global.CurrentTime" render="Label" position="56,46" size="82,18" font="Regular;16" >
			<convert type="ClockToText">WithSeconds</convert>
		</widget>
	</screen>"""


class MenuDaleSummary(Screen):
	"""Afisajul din fata in modul dale: numele dalei alese (sursa dala_aleasa, schimbata la fiecare mutare). Randul ales
	al listei are trei dale, deci StringListSelection n-ar sti care e aleasa."""
	skin = """
	<screen position="0,0" size="132,64">
		<widget source="parent.title" render="Label" position="6,4" size="120,21" font="Regular;18" />
		<widget source="parent.dala_aleasa" render="Label" position="6,25" size="120,21" font="Regular;16" />
		<widget source="global.CurrentTime" render="Label" position="56,46" size="82,18" font="Regular;16" >
			<convert type="ClockToText">WithSeconds</convert>
		</widget>
	</screen>"""


# imaginile dalelor, incarcate o data: (cale, latime, inaltime) -> pixmap sau None
_IMAGINI = {}
# latimea textelor masurate: (marimea fontului, text) -> px
_LATIMI = {}


def _dosarSkin():
	try:
		import skin
		return skin.DOSAR_HDS
	except Exception:
		return os.path.dirname(resolveFilename(SCOPE_SKIN, "HDSatelit/skin.xml"))


def _incarca(cale, latime, inaltime):
	cheie = (cale, latime, inaltime)
	if cheie in _IMAGINI:
		return _IMAGINI[cheie]
	ptr = None
	if os.path.isfile(cale):
		try:
			from enigma import getDesktop
			import skin
			ptr = skin.incarcaPixmapScalat(cale, latime, inaltime, getDesktop(0))
		except Exception as e:
			print("[Menu] imaginea %s nu s-a incarcat: %s" % (cale, e))
			ptr = None
	_IMAGINI[cheie] = ptr
	return ptr


def _culoriSkin():
	"""Culorile skinului (nume -> 0xAARRGGBB): cele din fisierele HDSatelit (paleta aleasa), altfel cele incarcate."""
	rez = {}
	try:
		import skin
		for nume, v in skin.culoriHds.items():
			try:
				rez[nume] = int(v[1:], 16)
			except (TypeError, ValueError):
				pass
		if not rez:
			for nume, c in skin.colorNames.items():
				try:
					rez[nume] = int(c.argb())
				except Exception:
					pass
	except Exception as e:
		print("[Menu] culorile skinului: %s" % e)
	return rez


class _MC(object):
	"""Functiile MultiContent si steagurile, pentru HdsDale.sablon."""
	def __init__(self):
		from Components import MultiContent
		from enigma import RT_HALIGN_CENTER, RT_VALIGN_CENTER, RT_VALIGN_TOP, RT_WRAP
		self.MultiContentEntryText = MultiContent.MultiContentEntryText
		self.MultiContentEntryPixmapAlphaBlend = MultiContent.MultiContentEntryPixmapAlphaBlend
		self.MultiContentTemplateColor = MultiContent.MultiContentTemplateColor
		self.RT_HALIGN_CENTER, self.RT_VALIGN_CENTER, self.RT_VALIGN_TOP, self.RT_WRAP = (RT_HALIGN_CENTER,
			RT_VALIGN_CENTER, RT_VALIGN_TOP, RT_WRAP)


class Menu(Screen):

	ALLOW_SUSPEND = True

	def okbuttonClick(self):
		print("okbuttonClick")
		if self._modDale:
			selection = self._intrareCurenta()
		else:
			selection = self["menu"].getCurrent()
		if selection is not None:
			selection[1]()

	def _intrareCurenta(self):
		"""Intrarea aleasa acum (tuplul din lista plata), in ambele moduri."""
		if self._modDale:
			if 0 <= self._dalaAles < len(self._flatlist):
				return self._flatlist[self._dalaAles]
			return None
		return self["menu"].getCurrent()

	def execText(self, text):
		exec(text)

	def runScreen(self, arg):
		# arg[0] is the module (as string)
		# arg[1] is Screen inside this module
		#        plus possible arguments, as
		#        string (as we want to reference
		#        stuff which is just imported)
		# FIXME. somehow
		# arg[0] si arg[1] vin din menu.xml, fisier al imaginii (nu din date externe)
		namespace = dict(globals())
		if arg[0] != "":
			namespace.update(vars(importlib.import_module(arg[0])))
		namespace["self"] = self
		self.openDialog(*eval(arg[1], namespace))

	def nothing(self): #dummy
		pass

	def openDialog(self, *dialog):				# in every layer needed
		self.session.openWithCallback(self.menuClosed, *dialog)

	def openSetup(self, dialog):
		self.session.openWithCallback(self.menuClosed, Setup, dialog)

	def addMenu(self, destList, node):
		requires = node.get("requires")
		if requires:
			if requires[0] == '!':
				if SystemInfo.get(requires[1:], False):
					return
			elif not SystemInfo.get(requires, False):
				return
		MenuTitle = _hdsTextNod(node, _)
		entryID = node.get("entryID", "undefined")
		weight = node.get("weight", 50)
		x = node.get("flushConfigOnClose")
		if x:
			a = boundFunction(self.session.openWithCallback, self.menuClosedWithConfigFlush, Menu, node)
		else:
			a = boundFunction(self.session.openWithCallback, self.menuClosed, Menu, node)
		#TODO add check if !empty(node.childNodes)
		destList.append(intrareMeniu(MenuTitle, a, entryID, weight, _(node.get("text") or "??"), _hdsStare(node),
			_glifNod(node)))

	def menuClosedWithConfigFlush(self, *res):
		configfile.save()
		self.menuClosed(*res)

	def menuClosed(self, *res):
		if res and res[0]:
			self.close(True)

	def addItem(self, destList, node):
		requires = node.get("requires")
		if requires:
			if requires[0] == '!':
				if SystemInfo.get(requires[1:], False):
					return
			elif not SystemInfo.get(requires, False):
				return
		item_text = node.get("text", "")
		entryID = node.get("entryID", "undefined")
		weight = node.get("weight", 50)
		simplu = _(node.get("text") or "??")
		stare = _hdsStare(node)
		glif = _glifNod(node)
		for x in node:
			if x.tag == 'screen':
				module = x.get("module")
				screen = x.get("screen")

				if screen is None:
					screen = module

				print(module, screen)
				if module:
					module = "Screens." + module
				else:
					module = ""

				# check for arguments. they will be appended to the
				# openDialog call
				args = x.text or ""
				screen += ", " + args

				destList.append(intrareMeniu(_hdsTextNod(node, _), boundFunction(self.runScreen, (module, screen)), entryID,
					weight, simplu, stare, glif))
				return
			elif x.tag == 'code':
				destList.append(intrareMeniu(_hdsTextNod(node, _), boundFunction(self.execText, x.text), entryID, weight,
					simplu, stare, glif))
				return
			elif x.tag == 'setup':
				id = x.get("id")
				if item_text == "":
					item_text = _(getSetupTitle(id))
				else:
					item_text = _(item_text)
				destList.append(intrareMeniu(_hdsTextNod(node, _, item_text), boundFunction(self.openSetup, id), entryID,
					weight, item_text, stare, glif))
				return
		destList.append(intrareMeniu(item_text, self.nothing, entryID, weight, None, stare, glif))


	def __init__(self, session, parent, alegere=None):
		Screen.__init__(self, session)

		list = []
		self.parentNode = parent

		menuID = None
		count = 0
		for x in parent:						#walk through the actual nodelist
			if x.tag == 'item':
				item_level = int(x.get("level", 0))
				if item_level <= config.usage.setup_level.index:
					self.addItem(list, x)
					count += 1
			elif x.tag == 'menu':
				self.addMenu(list, x)
				count += 1
			elif x.tag == "id":
				menuID = x.get("val")
				count = 0

			if menuID is not None:
				# menuupdater?
				if menuupdater.updatedMenuAvailable(menuID):
					for x in menuupdater.getUpdatedMenu(menuID):
						if x[1] == count:
							# HDSatelit: tuplul intreg (inainte avea 3 elemente, iar sortarea dupa greutate cadea)
							list.append(intrareMeniu(x[0], boundFunction(self.runScreen, (x[2], x[3] + ", ")), "undefined",
								x[4], glif=HdsDale.GLIF_EXTENSIE))
							count += 1

		if menuID is not None:
			# plugins
			for l in plugins.getPluginsForMenu(menuID):
				# check if a plugin overrides an existing menu
				plugin_menuid = l[2]
				for x in list:
					if x[2] == plugin_menuid:
						list.remove(x)
						break
				# HDSatelit: o extensie primeste pictograma generica, si cand ia locul unei intrari de-a noastre
				list.append(intrareMeniu(l[0], boundFunction(l[1], self.session), l[2], l[3] or 50,
					glif=HdsDale.GLIF_EXTENSIE))

		# HDSatelit: aspectul dale numai cu skinul HDSatelit (ecranul MenuDale), altfel lista
		self._modDale = aspectDale() and skinulAreDale()

		# for the skin: first try a menu_<menuID>, then Menu (in modul dale: menu_<menuID>_dale, apoi MenuDale)
		self.skinName = [ ]
		if self._modDale:
			if menuID is not None:
				self.skinName.append("menu_" + menuID + "_dale")
			self.skinName.append("MenuDale")
		if menuID is not None:
			self.skinName.append("menu_" + menuID)
		self.skinName.append("Menu")

		# Sort by Weight
		list.sort(key=lambda x: int(x[3]))

		self._flatlist = list
		self._dalaAles = 0
		self._dalaInceput = 0
		self._dalaGata = False
		self._dalaMut = False
		self._alesInitial = self._indexDupaEntryID(alegere)

		if self._modDale:
			if self._alesInitial is not None:
				self._dalaAles = self._alesInitial
			self._dalaSurse()
			self.onLayoutFinish.append(self._dalaPregateste)
		else:
			self["menu"] = List(list)
			if self._alesInitial is not None:
				# o metoda, nu lambda: GUISkin cheama direct numai metodele (restul trece prin exec)
				self.onLayoutFinish.append(self._listaAlege)

		actions = {
				"ok": self.okbuttonClick,
				"cancel": self.closeNonRecursive,
				"menu": self.closeRecursive,
				"1": self.keyNumberGlobal,
				"2": self.keyNumberGlobal,
				"3": self.keyNumberGlobal,
				"4": self.keyNumberGlobal,
				"5": self.keyNumberGlobal,
				"6": self.keyNumberGlobal,
				"7": self.keyNumberGlobal,
				"8": self.keyNumberGlobal,
				"9": self.keyNumberGlobal,
				# HDSatelit: TEXT in orice meniu deschide „Caută setări” (contextul HdsCautareActions din
				# keymap.xml, ca in lista de canale)
				"cautare": self.keyCautaSetari,
				# HDSatelit: tasta galbena comuta pe loc lista / dale (acelasi meniu, aceeasi intrare aleasa)
				"yellow": self.keyGalben,
			}
		contexte = ["OkCancelActions", "MenuActions", "NumberActions", "HdsCautareActions", "ColorActions"]
		self["actions"] = NumberActionMap(contexte, actions)
		if self._modDale:
			# sagetile inaintea listei (care le-ar lua cu prioritatea ei, 0): mutarea in grila e a meniului
			self["dala_sageti"] = ActionMap(["DirectionActions"], {
				"left": self._dalaStanga, "right": self._dalaDreapta, "up": self._dalaSus, "down": self._dalaJos,
				"leftRepeated": self._dalaStanga, "rightRepeated": self._dalaDreapta,
				"upRepeated": self._dalaSus, "downRepeated": self._dalaJos,
				# ridicarea tastei: nimic de facut (altfel jurnalul scrie "unknown action")
				"leftUp": self.nothing, "rightUp": self.nothing, "upUp": self.nothing, "downUp": self.nothing}, -1)

		a = parent.get("title", "") or None
		a = a and _(a)
		if a is None:
			a = _(parent.get("text", ""))
		self["title"] = StaticText(a)
		self.menu_title = a
		# si titlul ferestrei (sursa Title): skinurile il deseneaza in bara de sus, iar fara el bara ramane goala
		self.setTitle(a)

	def _listaAlege(self):
		self["menu"].setIndex(self._alesInitial)

	def _indexDupaEntryID(self, entryID):
		if entryID is None:
			return None
		for i, x in enumerate(self._flatlist):
			if x[2] == entryID:
				return i
		return None

	def alegeIntrarea(self, entryID):
		"""Cursorul pe intrarea cu entryID-ul dat (Caută setări, comutarea lista / dale), in ambele moduri."""
		i = self._indexDupaEntryID(entryID)
		if i is None:
			return False
		if self._modDale:
			if self._dalaGata:
				self._dalaMuta(i)
			else:
				self._dalaAles = i
		else:
			self["menu"].setIndex(i)
		return True

	# ------------------------------------------------------------ modul dale
	def _dalaSurse(self):
		from Components.Label import Label
		from Components.Pixmap import Pixmap
		from Components.Slider import Slider
		self["menu"] = List([])
		self["dala_aleasa"] = StaticText("")
		self["dala_cale"] = Label("")
		self["dala_pozitie"] = StaticText("")
		self["dala_sus"] = StaticText("")
		self["dala_jos"] = StaticText("")
		self["dala_sageata_sus"] = Pixmap()
		self["dala_sageata_jos"] = Pixmap()
		self["dala_bara"] = Slider(0, 1)
		self["dala_masura"] = Label("")
		# tastele din linia de jos: numele tastelor nu se traduc
		self["dala_t_ok"] = StaticText("OK")
		self["dala_t_exit"] = StaticText("EXIT")
		self["dala_t_cifre"] = StaticText("1-9")
		self["dala_t_text"] = StaticText("TEXT")
		self["dala_ok"] = StaticText(_("Deschide"))
		self["dala_exit"] = StaticText(_("Înapoi"))
		self["dala_cifre"] = StaticText(_("Direct"))
		self["dala_text"] = StaticText(_("Caută"))
		self["dala_galben"] = StaticText(_("Listă"))
		self._textLucru = _("ÎN LUCRU")
		self._textNetestat = _("NETESTAT")

	def _dalaPregateste(self):
		"""La asezarea ecranului: masurarea, sablonul (marimea textului, limba, scara ecranului), randurile."""
		try:
			import skin
			procent = skin.getFontScalePercent()
			scara = HdsDale.Scara.din(getattr(skin, "_scaraHds", [None])[0])
		except Exception:
			procent, scara = 100, HdsDale.Scara()
		self._dalaGeom = g = HdsDale.geometrie(procent)
		self._dalaScara = scara
		self._dalaCulori = HdsDale.culoriDale(_culoriSkin())
		self._dalaDosar = _dosarSkin()
		self._dalaFonduri = {}
		w, h = HdsDale.marimeFond(g, scara)
		for stare in HdsDale.STARI_FOND:
			cale = os.path.join(self._dalaDosar, "meniu", "dala", "%s-%d.png" % (stare, g["procent_fond"]))
			self._dalaFonduri[stare] = _incarca(cale, w, h)
		latimi = (HdsDale.latimeEticheta(self._dalaLatime(self._textLucru, g["eticheta_font"]), g),
			HdsDale.latimeEticheta(self._dalaLatime(self._textNetestat, g["eticheta_font"]), g))
		self._dalaPuneSablon(latimi)
		self._dalaIntrari = [self._dalaDescriere(i, x) for i, x in enumerate(self._flatlist)]
		self._dalaCale()
		self._dalaSageti()
		try:
			self["dala_masura"].hide()
		except Exception:
			pass
		self["menu"].onSelectionChanged.append(self._dalaSelectieLista)
		n = len(self._flatlist)
		self._dalaAles = max(0, min(self._dalaAles, n - 1))
		self._dalaInceput = HdsDale.fereastra(self._dalaAles // HdsDale.COLOANE, 0, HdsDale.randuri(n))
		self._dalaGata = True
		self._dalaRefa()

	def _dalaLatime(self, text, marime):
		"""Latimea unui text pe un rand, cu fontul dalelor la `marime` px (eticheta ascunsa dala_masura)."""
		cheie = (marime, text)
		if cheie in _LATIMI:
			return _LATIMI[cheie]
		w = 0
		try:
			from enigma import gFont
			eticheta = self["dala_masura"].instance
			eticheta.setFont(gFont(HdsDale.FONT_DALA, int(marime)))
			eticheta.setText(text)
			w = int(eticheta.calculateSize().width())
		except Exception:
			w = 0
		if w <= 0 and text:
			# fara masurare (skin fara eticheta): larg, ca numele sa nu iasa din dala
			w = len(text) * int(marime) * 62 // 100
		_LATIMI[cheie] = w
		return w

	def _dalaConvertor(self):
		for el in self["menu"].downstream_elements:
			if hasattr(el, "template") and hasattr(el, "setTemplate") and getattr(el, "content", None) is not None:
				return el
		return None

	def _dalaPuneSablon(self, latimi):
		"""Sablonul dalelor facut aici (geometria la marimea textului si etichetele cat textul lor) pus in locul celui din
		skin; daca nu se poate, ramane cel din skin (100 %), care foloseste aceleasi locuri din tuplu."""
		try:
			from enigma import gFont
			conv = self._dalaConvertor()
			if conv is None:
				print("[Menu] dale: lista nu are TemplatedMultiContent, ramane sablonul din skin")
				return False
			g, s = self._dalaGeom, self._dalaScara
			sablon = HdsDale.sablon(g, latimi, _MC(), s)
			fonturi = [gFont(f, m) for f, m in HdsDale.fonturi(g, s)]
			h = s.h(HdsDale.INALTIME_RAND)
			conv.template = {"template": sablon, "itemHeight": h, "fonts": fonturi}
			for i, f in enumerate(fonturi):
				conv.content.setFont(i, f)
			conv.content.setTemplate(sablon)
			conv.content.setItemHeight(h)
			return True
		except Exception as e:
			print("[Menu] dale: sablonul nu s-a pus: %s" % e)
			return False

	def _dalaDescriere(self, i, x):
		"""Ce nu se schimba la mutare pentru intrarea i: numele rupt, daca incape, cifra, starea, pictograma."""
		g = self._dalaGeom
		simplu = x[4] if len(x) > 4 else x[0]
		stare = x[5] if len(x) > 5 else None
		glif = (x[6] if len(x) > 6 else None) or HdsDale.GLIF_INTRARE
		maxim = g["nume_l"] - HdsDale.REZERVA_NUME
		randuri, incape = HdsDale.rupeNume(simplu, lambda t: self._dalaLatime(t, g["nume_font"]), maxim)
		return {"simplu": simplu, "rupt": "\n".join(randuri), "incape": incape, "stare": stare, "glif": glif,
			"cifra": str(i + 1) if i < 9 else None}

	def _dalaPictograma(self, glif, aleasa):
		g, s = self._dalaGeom, self._dalaScara
		culoare = HdsDale.culoarePictograma(aleasa, self._dalaCulori["luminos"])
		p = g["pictograma"]
		w, h = s.l(p), s.h(p)
		cale = os.path.join(self._dalaDosar, "meniu", culoare, glif + ".png")
		ptr = _incarca(cale, w, h)
		if ptr is None and glif != HdsDale.GLIF_INTRARE:
			ptr = _incarca(os.path.join(self._dalaDosar, "meniu", culoare, HdsDale.GLIF_INTRARE + ".png"), w, h)
		return ptr

	def _dalaDala(self, i, aleasa):
		d = self._dalaIntrari[i]
		c = self._dalaCulori
		fond = self._dalaFonduri.get("aleasa" if aleasa else "normala")
		peUnRand = aleasa and not d["incape"]
		return {
			"fond": fond,
			"plat": "" if fond is None else None,
			"plat_fond": c["marca"] if aleasa else c["cartonas"],
			"plat_chenar": c["marca_deschis"] if aleasa else c["cartonas"],
			"pictograma": self._dalaPictograma(d["glif"], aleasa),
			"nume": None if peUnRand else d["rupt"],
			"nume_rand": d["simplu"] if peUnRand else None,
			"culoare_nume": c["nume_ales"] if aleasa else c["nume"],
			"cifra": d["cifra"],
			"culoare_cifra": c["cifra_aleasa"] if aleasa else c["cifra"],
			"fond_cifra": c["cifra_aleasa_fond"] if aleasa else c["cifra_fond"],
			"eticheta_lucru": self._textLucru if d["stare"] == "in-lucru" else None,
			"eticheta_netestat": self._textNetestat if d["stare"] == "netestat" else None,
		}

	def _construiesteRandDala(self, rand):
		"""Tuplul randului `rand` (din toata grila) cu dala aleasa de acum."""
		n = len(self._flatlist)
		inceput = rand * HdsDale.COLOANE
		dale = [self._dalaDala(i, i == self._dalaAles) for i in range(inceput, min(n, inceput + HdsDale.COLOANE))]
		afisaj = self._dalaAles if inceput <= self._dalaAles < inceput + HdsDale.COLOANE else inceput
		nume = self._dalaIntrari[afisaj]["simplu"] if afisaj < n else ""
		return HdsDale.tupluRand(dale, self._dalaCulori, nume)

	def _dalaRanduriVazute(self):
		total = HdsDale.randuri(len(self._flatlist))
		sfarsit = min(total, self._dalaInceput + HdsDale.RANDURI_VIZIBILE)
		return [self._construiesteRandDala(r) for r in range(self._dalaInceput, sfarsit)]

	def _dalaRefa(self):
		"""Toate randurile vazute din nou (la deschidere si cand fereastra se muta)."""
		self._dalaMut = True
		try:
			self["menu"].list = self._dalaRanduriVazute()
			self["menu"].index = self._dalaAles // HdsDale.COLOANE - self._dalaInceput
		finally:
			self._dalaMut = False
		self._dalaStare()

	def _dalaMuta(self, nou):
		n = len(self._flatlist)
		if not self._dalaGata or not n or nou is None:
			return
		nou = max(0, min(int(nou), n - 1))
		vechi = self._dalaAles
		self._dalaAles = nou
		inceput = HdsDale.fereastra(nou // HdsDale.COLOANE, self._dalaInceput, HdsDale.randuri(n))
		if inceput != self._dalaInceput:
			self._dalaInceput = inceput
			self._dalaRefa()
			return
		self._dalaMut = True
		try:
			randuri = sorted(set((vechi // HdsDale.COLOANE, nou // HdsDale.COLOANE)))
			for r in randuri:
				k = r - self._dalaInceput
				if 0 <= k < self["menu"].count():
					self["menu"].modifyEntry(k, self._construiesteRandDala(r))
			self["menu"].index = nou // HdsDale.COLOANE - self._dalaInceput
		finally:
			self._dalaMut = False
		self._dalaStare()

	def _dalaSelectieLista(self):
		"""Lista s-a mutat singura (Pagina +/-, CH +/-): aceeasi coloana pe randul ales de ea."""
		if self._dalaMut or not self._dalaGata:
			return
		idx = self["menu"].index
		if idx is None:
			return
		rand = self._dalaInceput + idx
		nou = min(rand * HdsDale.COLOANE + self._dalaAles % HdsDale.COLOANE, len(self._flatlist) - 1)
		if nou != self._dalaAles:
			self._dalaMuta(nou)

	def _dalaStanga(self):
		self._dalaMuta(HdsDale.stanga(self._dalaAles, len(self._flatlist)))

	def _dalaDreapta(self):
		self._dalaMuta(HdsDale.dreapta(self._dalaAles, len(self._flatlist)))

	def _dalaSus(self):
		self._dalaMuta(HdsDale.sus(self._dalaAles, len(self._flatlist)))

	def _dalaJos(self):
		self._dalaMuta(HdsDale.jos(self._dalaAles, len(self._flatlist)))

	def _dalaStare(self):
		"""Numele dalei alese (afisajul din fata), pozitia, randurile ascunse sus si jos, bara de pozitie."""
		n = len(self._flatlist)
		total = HdsDale.randuri(n)
		if 0 <= self._dalaAles < n:
			self["dala_aleasa"].setText(self._dalaIntrari[self._dalaAles]["simplu"])
		vizibile = HdsDale.RANDURI_VIZIBILE
		multe = total > vizibile
		sus = self._dalaInceput if multe else 0
		jos = max(0, total - self._dalaInceput - vizibile) if multe else 0
		self["dala_pozitie"].setText(_("Poziția %d din %d") % (self._dalaAles + 1, n) if multe else "")
		self["dala_sus"].setText(_("Rânduri mai sus: %d") % sus if sus else "")
		self["dala_jos"].setText(_("Rânduri mai jos: %d") % jos if jos else "")
		for nume, vizibil in (("dala_sageata_sus", sus), ("dala_sageata_jos", jos), ("dala_bara", multe)):
			try:
				if vizibil:
					self[nume].show()
				else:
					self[nume].hide()
			except Exception:
				pass
		bara = getattr(self["dala_bara"], "instance", None)
		if multe and bara is not None:
			try:
				bara.setRange(0, total)
				bara.setStartEnd(self._dalaInceput, min(total, self._dalaInceput + vizibile))
			except Exception as e:
				print("[Menu] bara de pozitie: %s" % e)

	def _dalaSageti(self):
		"""Sagetile de derulare in culoarea paletei (deschise pe paletele intunecate, inchise pe cele luminoase)."""
		culoare = HdsDale.culoarePictograma(False, self._dalaCulori["luminos"])
		for nume, fisier in (("dala_sageata_sus", "sageata-sus"), ("dala_sageata_jos", "sageata-jos")):
			inst = getattr(self[nume], "instance", None)
			if inst is None:
				continue
			try:
				s = inst.size()
				ptr = _incarca(os.path.join(self._dalaDosar, "meniu", culoare, fisier + ".png"), s.width(), s.height())
				if ptr is not None:
					inst.setPixmap(ptr)
			except Exception as e:
				print("[Menu] sageata %s: %s" % (fisier, e))

	def _dalaRenderer(self, sursa):
		for r in self.renderer:
			if getattr(r, "source", None) is sursa:
				return r
		return None

	def _dalaCale(self):
		"""Calea meniului in submeniuri ("Meniu principal › Setări"), langa titlu, din titlurile parintilor."""
		cale = caleMeniu(self.parentNode)
		eticheta = getattr(self["dala_cale"], "instance", None)
		if len(cale) < 2 or eticheta is None:
			try:
				self["dala_cale"].hide()
			except Exception:
				pass
			return
		titlu = self._dalaRenderer(self["Title"])
		ti = getattr(titlu, "instance", None) if titlu is not None else None
		if ti is None:
			return
		try:
			from enigma import ePoint, eSize
			masura = self["dala_masura"].instance
			masura.setFont(ti.getFont())
			masura.setText(self.menu_title or "")
			lt = int(masura.calculateSize().width())
			p, s = ti.position(), ti.size()
			x = p.x() + lt + self._dalaScara.l(20)
			latime = p.x() + s.width() - x
			if latime < self._dalaScara.l(120):
				self["dala_cale"].hide()
				return
			# calea intreaga, sau fara meniul de acum (e deja titlul) cand nu incape; altfel deruleaza
			masura.setFont(eticheta.getFont())
			text = " › ".join(cale)
			masura.setText(text)
			if int(masura.calculateSize().width()) > latime and len(cale) > 2:
				text = " › ".join(cale[:-1])
			self["dala_cale"].setText(text)
			ps = eticheta.position()
			eticheta.move(ePoint(x, ps.y()))
			eticheta.resize(eSize(latime, eticheta.size().height()))
		except Exception as e:
			print("[Menu] calea meniului: %s" % e)

	# ------------------------------------------------------------ tastele
	def keyNumberGlobal(self, number):
		print("menu keyNumber:", number)
		if self._modDale:
			# cifra tinteste intrarea din lista plata (ca in modul lista), nu randul din grila
			i = HdsDale.dupaCifra(number, len(self._flatlist))
			if i is not None:
				self._dalaMuta(i)
				self.okbuttonClick()
			return
		# Calculate index
		number -= 1
		if len(self["menu"].list) > number:
			self["menu"].setIndex(number)
			self.okbuttonClick()

	def keyGalben(self):
		"""Tasta galbena: lista <-> dale pe loc. Acelasi meniu se deschide din nou cu cealalta forma si cu aceeasi intrare
		aleasa; cand se inchide, se inchide si acesta cu acelasi rezultat (EXIT inapoi un nivel, MENU tot meniul)."""
		if not self._modDale and not skinulAreDale():
			return
		try:
			from Components import HdsSkinuri
			HdsSkinuri.comutaAspect()
			configfile.save()
		except Exception as e:
			print("[Menu] aspectul meniului nu s-a schimbat: %s" % e)
			return
		curent = self._intrareCurenta()
		self.session.openWithCallback(self._dupaComutare, self.__class__, self.parentNode, curent and curent[2])

	def _dupaComutare(self, *rezultat):
		self.close(*rezultat)

	def keyCautaSetari(self):
		"""„Caută setări” (Screens/HdsCautaSetari.py); ecranul se incarca abia la apasare. Inchis cu MENU, inchide si
		meniul, ca un submeniu."""
		try:
			from Screens.HdsCautaSetari import HdsCautaSetari
		except ImportError as e:
			print("[Menu] Cauta setari: %s" % e)
			return
		self.session.openWithCallback(self.menuClosed, HdsCautaSetari)

	def closeNonRecursive(self):
		self.close(False)

	def closeRecursive(self):
		self.close(True)

	def createSummary(self):
		if self._modDale:
			return MenuDaleSummary
		return MenuSummary


def _parinti():
	"""{nod: parintele lui} pentru menu.xml (ElementTree nu tine parintii), facut o data."""
	if not _PARINTI:
		for p in mdom.getroot().iter():
			for c in p:
				_PARINTI[c] = p
	return _PARINTI


_PARINTI = {}


def _titluNod(nod):
	t = nod.get("title", "") or None
	return _(t) if t else _(nod.get("text", "") or "")


def caleMeniu(nod):
	"""Titlurile meniurilor de la meniul principal pana la `nod` (inclusiv)."""
	cale = []
	parinti = _parinti()
	while nod is not None and nod.tag == "menu":
		cale.insert(0, _titluNod(nod))
		nod = parinti.get(nod)
	return cale


class MainMenu(Menu):
	#add file load functions for the xml-file

	def __init__(self, *x):
		self.skinName = "Menu"
		Menu.__init__(self, *x)
