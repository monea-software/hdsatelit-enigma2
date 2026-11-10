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
		self["SetupEntry"].text = self.parent.getCurrentEntry()
		self["SetupValue"].text = self.parent.getCurrentValue()

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
		list = []
		self.refill(list)

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
		current = self["config"].getCurrent()
		text = self.descriptions.get(id(current[1]), "") if current is not None and len(current) > 1 else ""
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
		if [id(r[1]) for r in lista] == [id(r[1]) for r in vechi]:
			return
		curent = self["config"].getCurrent()
		self["config"].setList(lista)
		for i, r in enumerate(lista):
			if curent is not None and len(curent) > 1 and r[1] is curent[1]:
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
		return self.descriptions.get(id(self.getCurrentItem()), "")

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

	def addIf(self, list, nod):
		"""<if conditional="..."> randuri <else /> randuri </if>, cum scriu pluginurile in setup.xml; se pot imbrica.
		Lista se reface la fiecare schimbare de valoare, ca la randurile cu conditional=."""
		self.conditionale = True
		activ = self.conditieAdevarata(nod.get("conditional", "True"), self)
		for copil in nod:
			if copil.tag == "else":
				activ = not activ
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

				# ecranul unui plugin nu are alt drum spre setarile lui: nivelul nu il lasa gol
				if item_level > config.usage.setup_level.index and self.plugin is None:
					continue

				requires = x.get("requires")
				if requires and not SystemInfo.get(requires, False):
					continue;

				conditional = x.get("conditional")
				if conditional:
					self.conditionale = True
					if not self.conditieAdevarata(conditional, self):
						continue

				# HDSatelit: semnul „(în lucru)” / „(netestat)” din atributul stare= (HdsStareMeniu)
				item_text = _hdsTextNod(x, _)
				description = x.get("description")
				try:
					b = eval(x.text or "");
				except Exception as e:
					if self.plugin is None:
						raise
					print("[Setup] %s: randul %r: %r" % (self.plugin, x.text, e))
					continue
				if b == "":
					continue
				#add to configlist
				item = b
				# the first b is the item itself, ignored by the configList.
				# the second one is converted to string.
				if not isinstance(item, ConfigNothing):
					list.append( (item_text, item) )
					if description:
						self.descriptions[id(item)] = _(description)

def getSetupTitle(id):
	xmldata = setupdom.getroot()
	for x in xmldata.findall("setup"):
		if x.get("key") == id:
			return x.get("title", "")
	raise SetupError("unknown setup id '%s'!" % repr(id))
