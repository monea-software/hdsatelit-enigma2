# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ActionMap import NumberActionMap
from Components.config import config, ConfigNothing
from Components.SystemInfo import SystemInfo
from Components.ConfigList import ConfigListScreen
try:
	from Components.ConfigList import esteTextDeScris
except ImportError:          # un ConfigList fara tastatura (probele de pe PC cu inlocuitori)
	def esteTextDeScris(el):
		return False
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from enigma import eEnv

import xml.etree.ElementTree
from gettext import dgettext

# HDSatelit: semnele „(în lucru)” / „(netestat)”; fara modul, numele simplu (setarile merg oricum)
try:
	from Components.HdsStareMeniu import textNod as _hdsTextNod
except ImportError:
	def _hdsTextNod(nod, traducere, text=None):
		return text if text is not None else traducere(nod.get("text") or "??")

# FIXME: use resolveFile!
# read the setupmenu
# setup.xml se deschide binar: ElementTree ia codarea din fisier (UTF-8, textele au diacritice), nu din locale;
# in mod text, cu locale C (pornirea de pe receptor, fara LANG), citirea cadea cu UnicodeDecodeError.
try:
	# first we search in the current path
	setupfile = open('data/setup.xml', 'rb')
except:
	# if not found in the current path, we use the global datadir-path
	setupfile = open(eEnv.resolve('${datadir}/enigma2/setup.xml'), 'rb')
setupdom = xml.etree.ElementTree.parse(setupfile)
setupfile.close()

# HDSatelit: textul de ajutor al randului ales sta intr-o eticheta fixa
# ("description", 1176x144 in skinul HDSatelit: 3 randuri intregi); unul mai lung se taia jos (la 130% cam 20 de texte
# din setup.xml). Tastele sunt ale listei, deci un text care nu incape se arata pe pagini care se schimba singure la
# AJUTOR_PAGINA_MS, cu AJUTOR_URMARE la capatul celor care continua, de la prima pagina la fiecare rand nou ales.
AJUTOR_PAGINA_MS = 6000
AJUTOR_URMARE = u" \u2026"


def imparteAjutorul(text, incape, urmare=AJUTOR_URMARE):
	"""Textul pe pagini care incap in eticheta (incape(text) -> bool, masurat de eticheta insasi): la spatii, cat mai
	multe cuvinte pe pagina, cu `urmare` la capatul paginilor care continua. Un text care incape ramane o pagina; un
	cuvant care nu incape nici singur ramane pe pagina lui."""
	if not text or incape(text):
		return [text]
	cuvinte = text.split(" ")
	pagini = []
	i = 0
	while i < len(cuvinte):
		rest = " ".join(cuvinte[i:])
		if incape(rest):
			pagini.append(rest)
			break
		# cel mai mare capat cu cuvinte[i:capat] + urmare care incape (cautare binara; mai multe cuvinte, mai inalt)
		bun, jos, sus = i + 1, i + 1, len(cuvinte) - 1
		while jos <= sus:
			mij = (jos + sus) // 2
			if incape(" ".join(cuvinte[i:mij]) + urmare):
				bun, jos = mij, mij + 1
			else:
				sus = mij - 1
		pagini.append(" ".join(cuvinte[i:bun]) + urmare)
		i = bun
	return pagini


def _xmlPlugin(plugin):
	"""Radacina setup.xml-ului din dosarul unui plugin (plugin="Extensions/Nume"), sau None cand nu se poate citi."""
	from Tools.Directories import resolveFilename, SCOPE_PLUGINS
	cale = resolveFilename(SCOPE_PLUGINS, "%s/setup.xml" % plugin.strip("/"))
	try:
		with open(cale, "rb") as f:
			return xml.etree.ElementTree.parse(f).getroot()
	except Exception as e:
		print("[Setup] %s: %r" % (cale, e))
		return None


def _traducere(domeniu):
	"""Traducerea textelor unui ecran: domeniul pluginului (PluginLanguageDomain), apoi cea a imaginii; fara domeniu,
	numai cea a imaginii."""
	if not domeniu:
		return lambda text: _(text)

	def tradu(text):
		tradus = dgettext(domeniu, text)
		return tradus if tradus != text else _(text)
	return tradu


class SetupError(Exception):
    def __init__(self, message):
        self.msg = message

    def __str__(self):
        return self.msg

class SetupSummary(Screen):

	def __init__(self, session, parent):

		Screen.__init__(self, session, parent = parent)
		# un ecran de plugin nu are neaparat setup_title
		titlu = getattr(parent, "setup_title", None) or (parent.getTitle() if hasattr(parent, "getTitle") else "")
		self["SetupTitle"] = StaticText(_(titlu) if titlu else "")
		self["SetupEntry"] = StaticText("")
		self["SetupValue"] = StaticText("")
		# numele din alte imagini ale acelorasi texte (skin-urile scrise pentru el au <widget source="entry"/"value">)
		self["entry"] = StaticText("")
		self["value"] = StaticText("")
		self.onShow.append(self.addWatcher)
		self.onHide.append(self.removeWatcher)

	def addWatcher(self):
		# HDSatelit: un ecran de plugin cu SetupSummary nu are neaparat lista onChangedEntry (BitrateViewer): o primeste aici
		if not isinstance(getattr(self.parent, "onChangedEntry", None), list):
			self.parent.onChangedEntry = []
		self.parent.onChangedEntry.append(self.selectionChanged)
		self.parent["config"].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def removeWatcher(self):
		for lista in (getattr(self.parent, "onChangedEntry", None), self.parent["config"].onSelectionChanged):
			if lista is not None and self.selectionChanged in lista:
				lista.remove(self.selectionChanged)

	def selectionChanged(self):
		self["SetupEntry"].text = self["entry"].text = self.parent.getCurrentEntry()
		self["SetupValue"].text = self["value"].text = self.parent.getCurrentValue()

class Setup(ConfigListScreen, Screen):

	ALLOW_SUSPEND = True

	def removeNotifier(self):
		config.usage.setup_level.notifiers.remove(self.levelChanged)

	def levelChanged(self, configElement):
		if self.faceRandurileSingur():
			self.createSetup()
			self.updateDescription()
			return
		list = []
		self.refill(list)
		self["config"].setList(list)
		self.updateDescription()

	def refill(self, list):
		# ecranul unui plugin se cauta intai in setup.xml-ul lui, apoi in cel al imaginii
		for xmldata in (self.xmlPlugin, setupdom.getroot()):
			if xmldata is None:
				continue
			gasit = False
			for x in xmldata.findall("setup"):
				if x.get("key") != self.setup:
					continue
				gasit = True
				# skin= (alte imagini): numele ecranului din skin cerut de <setup>, inaintea celor implicite
				skin = x.get("skin")
				if skin and isinstance(self.skinName, type([])) and skin not in self.skinName:
					self.skinName.insert(0, skin)
				self.pendingHeading = None
				self.addItems(list, x);
				self.setup_title = x.get("title", "")
			if gasit:
				break
		# Actiunea este numai a ecranului de volum; foloseste aceeasi memorie ca butonul din web.
		if self.setup == "hds_setari_sunet":
			if self.uitaVolumeSetare is None:
				self.uitaVolumeSetare = ConfigNothing()
			list.append((_("Uită volumele ținute minte"), self.uitaVolumeSetare))
			self.descriptions[id(self.uitaVolumeSetare)] = _("OK: uită volumele tuturor canalelor. Întârzierile pistelor rămân.")

	def createSetup(self, appendItems=None, prependItems=None):
		"""Randurile ecranului din nou, in lista. Un plugin o suprascrie cand isi face randurile singur (ecranul i-o
		cheama la deschidere) sau o cheama cu randuri in plus."""
		lista = (prependItems or [])[:]
		self.refill(lista)
		lista.extend(appendItems or [])
		self.list = lista
		self["config"].setList(lista)

	def faceRandurileSingur(self):
		return type(self).createSetup is not Setup.createSetup

	def __init__(self, session, setup=None, plugin=None, PluginLanguageDomain=None, **altele):
		"""setup: cheia din setup.xml; plugin ("Extensions/Nume"): pluginul cu setup.xml-ul propriu in dosarul lui;
		PluginLanguageDomain: domeniul de traducere al textelor lui. Ecranele imaginii dau numai cheia."""
		Screen.__init__(self, session)
		if altele:
			print("[Setup] parametri necunoscuti, ignorati: %s" % ", ".join(sorted(altele)))
		# for the skin: first try a setup_<setupID>, then Setup
		self.skinName = ["setup_" + setup, "Setup" ] if setup else ["Setup"]
		# ca in alte imagini: o subclasa a unui plugin isi cauta intai ecranul cu numele clasei ei; „SetupX” (forma OE-Alliance
		# a temelor) e a doua forma a lui „setup_X”: se cauta setup_X, apoi SetupX, apoi Setup (si pe ecranele noastre)
		if setup:
			self.skinName.insert(1, "Setup" + setup)
		if type(self) is not Setup and type(self).__name__ not in self.skinName:
			self.skinName.insert(0, type(self).__name__)
		getattr(self, "setImage", lambda *a: None)(setup, "setup")  # probele pe PC au un Screen fara setImage
		self.plugin = plugin
		self.xmlPlugin = _xmlPlugin(plugin) if plugin else None
		self.traducere = _traducere(PluginLanguageDomain)
		self.setup_title = setup or ""

		self.onChangedEntry = [ ]
		# id(setare) -> textul de ajutor (atributul description din setup.xml).
		# Nu ca al treilea element al randului: ConfigList.selectionChanged cheama onSelectionChanged numai pentru
		# randuri de doua elemente.
		self.descriptions = {}
		# randurile cu atributul conditional= (o expresie peste config) se arata numai cand
		# expresia e adevarata; lista se reface la fiecare schimbare de valoare, daca ecranul are asemenea randuri
		self.conditionale = False

		self.setup = setup
		self.uitaVolumeSetare = None
		# restart= din setup.xml (alte imagini): id(setare) -> "gui" / "system"
		self.repornire = {}
		self.pendingHeading = None
		self.pluginLanguageDomain = PluginLanguageDomain
		list = []
		self.refill(list)
		self.list = list

		#check for list.entries > 0 else self.close
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))

		self["actions"] = NumberActionMap(["SetupActions"], 
			{
				"cancel": self.keyCancel,
				"save": self.keySave,
			}, -2)

		ConfigListScreen.__init__(self, list, session = session, on_change = self.changedEntry)

		# textul de ajutor al randului curent, in zona „description” a skinului HDSatelit (HdsSetupBase); gol la
		# randurile fara text
		self["description"] = Label("")
		# nota de sub ajutor a unui plugin (setFootnote); ascunsa la toate celelalte ecrane
		self["footnote"] = Label("")
		self["footnote"].visible = False
		self["config"].onSelectionChanged.append(self.updateDescription)

		if self.faceRandurileSingur():
			self.createSetup()
		self.changedEntry()
		self.onLayoutFinish.append(self.layoutFinished)
		# HDSatelit: o setare cu atributul hdsStare (o functie care da randurile starii de acum, de pilda
		# config.usage.hds_ipv6 din Components/HdsIpv6.py) isi arata starea deasupra textului de ajutor, citita din nou
		# la STARE_MS cat ecranul e deschis
		self.hdsStareText = None
		self.hdsCeasStare = None
		if any(getattr(x[1], "hdsStare", None) is not None for x in list if len(x) > 1):
			from enigma import eTimer
			self.hdsCeasStare = eTimer()
			self.hdsCeasStare.callback.append(self.hdsStareSchimbata)
			self.onClose.append(self.hdsCeasStare.stop)

	STARE_MS = 3000

	def layoutFinished(self):
		if self.setup_title:
			self.setTitle(self.traducere(self.setup_title))
		self.updateDescription()
		if self.hdsCeasStare is not None:
			self.hdsCeasStare.start(self.STARE_MS, False)

	def hdsStare(self, element):
		"""Randurile starii de acum ale setarii (atributul hdsStare), sau []."""
		f = getattr(element, "hdsStare", None)
		if f is None:
			return []
		try:
			return list(f() or [])
		except Exception as eroare:
			print("[Setup] starea setarii: %s" % eroare)
			return []

	def hdsStareSchimbata(self):
		current = self["config"].getCurrent()
		text = "\n".join(self.hdsStare(current[1])) if current is not None and len(current) > 1 else ""
		if text != self.hdsStareText:
			self.updateDescription()

	def updateDescription(self):
		if self.repornire:
			# setarile cu restart= din setup.xml: nota de sub ajutor spune ce cere schimbarea (ca in alte imagini)
			cur = self["config"].getCurrent()
			fel = self.repornire.get(id(cur[1])) if cur is not None and len(cur) > 1 else None
			self.setFootnote(_("* = după schimbare se repornește interfața") if fel == "gui" else
				_("# = după schimbare se repornește receptorul") if fel == "system" else None)
		current = self["config"].getCurrent()
		text = self.descriptions.get(id(current[1]), "") if current is not None and len(current) > 1 else ""
		# Alte imagini: descrierea poate fi al treilea element al randului (getConfigListEntry(text, setare, descriere))
		if not text and current is not None and len(current) > 2 and isinstance(current[2], str):
			text = current[2]
		stare = "\n".join(self.hdsStare(current[1])) if current is not None and len(current) > 1 else ""
		self.hdsStareText = stare
		if stare:
			text = stare + ("\n" + text if text else "")
		# HDSatelit: pe un camp de text, OK deschide tastatura de pe ecran (Components/ConfigList.deschideTastatura)
		if current is not None and len(current) > 1 and esteTextDeScris(current[1]):
			text = (text + "\n" if text else "") + _("OK: tastatura")
		self.arataAjutorul(text)

	def arataAjutorul(self, text):
		"""Textul de ajutor in eticheta; cand nu incape, pe pagini care se schimba singure (imparteAjutorul), masurate
		cu eticheta insasi (calculateSize, la latimea si fontul ei)."""
		eticheta = self["description"]
		pagini = [text]
		inst = getattr(eticheta, "instance", None)
		if inst is not None and text:
			try:
				inaltime = inst.size().height()
				# numai randuri intregi, ca ScrollLabel: cutia literelor (calculateSize) a 4 randuri poate iesi sub
				# inaltimea casetei, desi al patrulea rand e taiat jos (vazut in emulator)
				try:
					from enigma import fontRenderClass
					rand = fontRenderClass.getInstance().getLineHeight(inst.getFont())
				except Exception:
					rand = 0
				if rand and 0 < rand <= inaltime:
					inaltime = (inaltime // rand) * rand

				def incape(t):
					inst.setText(t)
					return inst.calculateSize().height() <= inaltime
				pagini = imparteAjutorul(text, incape) or [text]
			except Exception as e:
				print("[Setup] ajutorul pe pagini: %r" % (e,))
				pagini = [text]
		self.paginiAjutor = pagini
		self.paginaAjutor = 0
		eticheta.setText(pagini[0])
		ceas = getattr(self, "ceasAjutor", None)
		if len(pagini) > 1:
			if ceas is None:
				from enigma import eTimer
				ceas = self.ceasAjutor = eTimer()
				ceas.callback.append(self.paginaAjutorUrmatoare)
				self.onClose.append(ceas.stop)
			ceas.start(AJUTOR_PAGINA_MS, False)
		elif ceas is not None:
			ceas.stop()

	def paginaAjutorUrmatoare(self):
		pagini = getattr(self, "paginiAjutor", [])
		if len(pagini) > 1:
			self.paginaAjutor = (self.paginaAjutor + 1) % len(pagini)
			self["description"].setText(pagini[self.paginaAjutor])

	# for summary:
	def changedEntry(self):
		if self.conditionale and "config" in self:
			self.refaConditionale()
		for x in self.onChangedEntry:
			x()

	def refaConditionale(self):
		"""lista din nou dupa conditional=; cursorul ramane pe aceeasi setare (randurile ascunse sunt sub ea)"""
		if self.faceRandurileSingur():
			self.createSetup()
			return
		lista = []
		self.refill(lista)
		vechi = self["config"].list
		# randurile de titlu (un singur element) se compara dupa text
		cheie = lambda r: id(r[1]) if len(r) > 1 else r[0]
		if [cheie(r) for r in lista] == [cheie(r) for r in vechi]:
			return
		curent = self["config"].getCurrent()
		self.list = lista
		self["config"].setList(lista)
		for i, r in enumerate(lista):
			if curent is not None and len(curent) > 1 and len(r) > 1 and r[1] is curent[1]:
				self["config"].setCurrentIndex(i)
				break
		self.updateDescription()

	@staticmethod
	def conditieAdevarata(expresie, ecran=None):
		"""conditional= din setup.xml; o expresie care nu se poate evalua arata randul (fara mesaj cand numai setarea
		lipseste: modulul care o face nu e instalat). In expresie, self este ecranul (setup.xml-ul unui plugin)."""
		try:
			return bool(eval(expresie, globals(), {"self": ecran}))
		except (KeyError, AttributeError):
			return True
		except Exception as e:
			print("[Setup] conditional %r: %s" % (expresie, e))
			return True

	# HDSatelit: lista goala (un plugin care o umple mai tarziu, BouquetCleanup) sau un rand de titlu fara setare nu mai dau eroare;
	# ca ConfigListScreen din Components/ConfigList.py
	def getCurrentEntry(self):
		curent = self["config"].getCurrent()
		return curent[0] if curent else ""

	def getCurrentValue(self):
		# fara getCurrentItem: SetupSummary o cheama si pe ecrane de plugin care au numai lista (test_compat_lot6_071)
		curent = self["config"].getCurrent()
		return str(curent[1].getText()) if curent is not None and len(curent) > 1 and curent[1] is not None else ""

	def getCurrentItem(self):
		"""Setarea randului curent, sau None."""
		curent = self["config"].getCurrent()
		return curent[1] if curent is not None and len(curent) > 1 else None

	def getCurrentDescription(self):
		text = self.descriptions.get(id(self.getCurrentItem()), "")
		if not text:
			cur = self["config"].getCurrent()
			if cur is not None and len(cur) > 2 and isinstance(cur[2], str):
				text = cur[2]
		return text

	def setFootnote(self, footnote):
		"""Nota de sub ajutor; goala sau None o ascunde."""
		self["footnote"].setText(footnote or "")
		self["footnote"].visible = bool(footnote)

	def keyOK(self):
		self.keySelect()

	def keySelect(self):
		"""Tasta OK; un plugin o suprascrie ca sa deschida un ecran al lui de pe un rand."""
		if self.setup == "hds_setari_sunet" and self.getCurrentItem() is self.uitaVolumeSetare:
			from Components import HdsSetariSunet
			from Screens.MessageBox import MessageBox
			HdsSetariSunet.uitaVolume()
			self.session.open(MessageBox, _("Volumele ținute minte au fost uitate."), MessageBox.TYPE_INFO, timeout=5)
			return
		ConfigListScreen.keyOK(self)

	def createSummary(self):
		return SetupSummary

	# HDSatelit: restul API-ului din alte imagini al ecranului Setup (pluginurile care il mostenesc il cheama)
	def includeElement(self, element):
		"""Se arata elementul (<item>, <if>, <elif>)? level= (nivelul setarilor; ecranul unui plugin nu are alt drum spre
		setarile lui, deci acolo nivelul nu ascunde), requires= (chei SystemInfo sau setari config.*, mai multe cu ';',
		'!' in fata = negat) si conditional= (expresie)."""
		try:
			nivel = int(element.get("level", 0))
		except ValueError:
			nivel = 0
		if nivel > config.usage.setup_level.index and self.plugin is None:
			return False
		x = element
		requires = x.get("requires")
		if requires:
			for requires in [c.strip() for c in requires.split(";") if c.strip()]:
				negat = requires.startswith("!")
				if negat:
					requires = requires[1:].strip()
				if requires.startswith("config."):
					try:
						valoare = eval(requires).value
						rezultat = bool(valoare) and str(valoare).lower() not in ("0", "disable", "false", "no", "off")
					except Exception as e:
						print("[Setup] requires %r: %r" % (requires, e))
						return False
				else:
					rezultat = bool(SystemInfo.get(requires, False))
				if negat == rezultat:
					return False
		conditional = element.get("conditional")
		if conditional:
			self.conditionale = True
			if not self.conditieAdevarata(conditional, self):
				return False
		return True

	def formatItemText(self, text, data=None):
		"""data="a,b" (alte imagini): valorile puse in locul lui %s din text, cand numarul se potriveste."""
		if data:
			valori = data.split(",") if isinstance(data, str) else list(data)
			if text.count("%s") == len(valori):
				try:
					return text % tuple(valori)
				except (TypeError, ValueError):
					pass
		return text

	def selectionChanged(self):
		self.updateDescription()

	def getFootnote(self):
		return self["footnote"].getText()

	def getIndexFromItem(self, item):
		if item is None:
			return 0
		lista = self["config"].list
		if item in lista:
			return lista.index(item)
		for i, rand in enumerate(lista):
			if len(rand) > 1 and len(item) > 1 and rand[0] == item[0] and rand[1] is item[1]:
				return i
		return 0

	def moveToItem(self, item):
		if item != self["config"].getCurrent():
			self["config"].setCurrentIndex(self.getIndexFromItem(item))

	def keySave(self):
		"""Ca la ConfigListScreen; in plus, o setare cu restart= (setup.xml) schimbata intreaba de repornire."""
		fel = None
		for rand in self["config"].list:
			if len(rand) > 1 and id(rand[1]) in self.repornire and rand[1].isChanged():
				fel = "system" if self.repornire[id(rand[1])] == "system" or fel == "system" else "gui"
		if fel is None:
			return ConfigListScreen.keySave(self)
		for notifier in list(self.__dict__.get("onSave", ())):
			notifier()
		self.saveAll()
		from Screens.MessageBox import MessageBox
		text = _("Repornești receptorul acum?") if fel == "system" else self.restartMsg
		self.session.openWithCallback(lambda da: self.__repornire(da, 2 if fel == "system" else 3), MessageBox, text, MessageBox.TYPE_YESNO)

	def __repornire(self, da, cod):
		if da:
			from Screens.Standby import TryQuitMainloop
			self.session.open(TryQuitMainloop, cod)
		self.close()

	def addIf(self, list, nod):
		"""<if conditional="..."> randuri <else /> randuri </if>, cum scriu pluginurile in setup.xml; se pot imbrica.
		Lista se reface la fiecare schimbare de valoare, ca la randurile cu conditional=."""
		self.conditionale = True
		activ = self.includeElement(nod)
		gasit = activ
		for copil in nod:
			if copil.tag == "elif":
				# <elif conditional=... requires=... /> (alte imagini): ramura urmatoare, numai daca nicio ramura de dinainte n-a mers
				activ = (not gasit) and self.includeElement(copil)
				gasit = gasit or activ
			elif copil.tag == "else":
				activ = not gasit
				gasit = True
			elif activ:
				self.addItems(list, [copil])

	def addItems(self, list, parentNode):
		# textele se traduc cu domeniul pluginului, cand ecranul are unul
		_ = self.traducere
		for x in parentNode:
			if x.tag == 'if':
				self.addIf(list, x)
			elif x.tag == 'item':
				item_level = int(x.get("level", 0))

				if not self.levelChanged in config.usage.setup_level.notifiers:
					config.usage.setup_level.notifiers.append(self.levelChanged)
					self.onClose.append(self.removeNotifier)

				if not self.includeElement(x):
					continue

				# HDSatelit: semnul „(în lucru)” / „(netestat)” din atributul stare= (HdsStareMeniu)
				item_text = _hdsTextNod(x, _)
				description = x.get("description")
				if (x.text or "").strip() == "":
					# Alte imagini: un <item> fara setare e titlul grupului de sub el; se arata numai daca urmeaza o
					# setare vizibila (rand de un element: ConfigList il sare, lista il deseneaza ca titlu)
					self.pendingHeading = (self.formatItemText(item_text, x.get("data")),)
					continue
				try:
					b = eval(x.text or "");
				except Exception as e:
					if self.plugin is None:
						raise
					print("[Setup] %s: randul %r: %r" % (self.plugin, x.text, e))
					continue
				item_text = self.formatItemText(item_text, x.get("data"))
				if b == "":
					continue
				#add to configlist
				item = b
				# the first b is the item itself, ignored by the configList.
				# the second one is converted to string.
				if not isinstance(item, ConfigNothing):
					if getattr(self, "pendingHeading", None):
						list.append(self.pendingHeading)
						self.pendingHeading = None
					restart = (x.get("restart") or "").lower()
					if restart == "gui" and not item_text.endswith("*"):
						item_text += " *"
					elif restart == "system" and not item_text.endswith("#"):
						item_text += " #"
					if restart in ("gui", "system"):
						self.repornire[id(item)] = restart
					list.append( (item_text, item) )
					if description:
						self.descriptions[id(item)] = _(description)

MODULE_NAME = __name__.split(".")[-1]


def setupDom(setup=None, plugin=None):
	"""Alte imagini: radacina setup.xml-ului (al pluginului, cand e dat si exista; altfel al imaginii)."""
	if plugin:
		radacina = _xmlPlugin(plugin)
		if radacina is not None:
			return radacina
	return setupdom.getroot()


def getSetupTitle(id):
	xmldata = setupdom.getroot()
	for x in xmldata.findall("setup"):
		if x.get("key") == id:
			return x.get("title", "")
	raise SetupError("unknown setup id '%s'!" % repr(id))
