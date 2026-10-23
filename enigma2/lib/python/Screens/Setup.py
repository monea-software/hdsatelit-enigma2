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


class SetupError(Exception):
    def __init__(self, message):
        self.msg = message

    def __str__(self):
        return self.msg

class SetupSummary(Screen):

	def __init__(self, session, parent):

		Screen.__init__(self, session, parent = parent)
		self["SetupTitle"] = StaticText(_(parent.setup_title))
		self["SetupEntry"] = StaticText("")
		self["SetupValue"] = StaticText("")
		self.onShow.append(self.addWatcher)
		self.onHide.append(self.removeWatcher)

	def addWatcher(self):
		self.parent.onChangedEntry.append(self.selectionChanged)
		self.parent["config"].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def removeWatcher(self):
		self.parent.onChangedEntry.remove(self.selectionChanged)
		self.parent["config"].onSelectionChanged.remove(self.selectionChanged)

	def selectionChanged(self):
		self["SetupEntry"].text = self.parent.getCurrentEntry()
		self["SetupValue"].text = self.parent.getCurrentValue()

class Setup(ConfigListScreen, Screen):

	ALLOW_SUSPEND = True

	def removeNotifier(self):
		config.usage.setup_level.notifiers.remove(self.levelChanged)

	def levelChanged(self, configElement):
		list = []
		self.refill(list)
		self["config"].setList(list)
		self.updateDescription()

	def refill(self, list):
		xmldata = setupdom.getroot()
		for x in xmldata.findall("setup"):
			if x.get("key") != self.setup:
				continue
			self.addItems(list, x);
			self.setup_title = x.get("title", "")

	def __init__(self, session, setup):
		Screen.__init__(self, session)
		# for the skin: first try a setup_<setupID>, then Setup
		self.skinName = ["setup_" + setup, "Setup" ]

		self.onChangedEntry = [ ]
		# id(setare) -> textul de ajutor (atributul description din setup.xml).
		# Nu ca al treilea element al randului: ConfigList.selectionChanged cheama onSelectionChanged numai pentru
		# randuri de doua elemente.
		self.descriptions = {}
		# randurile cu atributul conditional= (o expresie peste config) se arata numai cand
		# expresia e adevarata; lista se reface la fiecare schimbare de valoare, daca ecranul are asemenea randuri
		self.conditionale = False

		self.setup = setup
		list = []
		self.refill(list)

		#check for list.entries > 0 else self.close
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))

		self["actions"] = NumberActionMap(["SetupActions"], 
			{
				"cancel": self.keyCancel,
				"save": self.keySave,
			}, -2)

		ConfigListScreen.__init__(self, list, session = session, on_change = self.changedEntry)

		# textul de ajutor al randului curent, in zona „description” a skinului HDSatelit (HdsSetupBase); gol la
		# randurile fara text
		self["description"] = Label("")
		self["config"].onSelectionChanged.append(self.updateDescription)

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
		self.setTitle(_(self.setup_title))
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
	def conditieAdevarata(expresie):
		"""conditional= din setup.xml; o expresie care nu se poate evalua arata randul (fara mesaj cand numai setarea
		lipseste: modulul care o face nu e instalat)"""
		try:
			return bool(eval(expresie))
		except (KeyError, AttributeError):
			return True
		except Exception as e:
			print("[Setup] conditional %r: %s" % (expresie, e))
			return True

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		return SetupSummary

	def addItems(self, list, parentNode):
		for x in parentNode:
			if x.tag == 'item':
				item_level = int(x.get("level", 0))

				if not self.levelChanged in config.usage.setup_level.notifiers:
					config.usage.setup_level.notifiers.append(self.levelChanged)
					self.onClose.append(self.removeNotifier)

				if item_level > config.usage.setup_level.index:
					continue

				requires = x.get("requires")
				if requires and not SystemInfo.get(requires, False):
					continue;

				conditional = x.get("conditional")
				if conditional:
					self.conditionale = True
					if not self.conditieAdevarata(conditional):
						continue

				# HDSatelit: semnul „(în lucru)” / „(netestat)” din atributul stare= (HdsStareMeniu)
				item_text = _hdsTextNod(x, _)
				description = x.get("description")
				b = eval(x.text or "");
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
