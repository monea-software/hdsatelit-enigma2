# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .HTMLComponent import HTMLComponent
from .GUIComponent import GUIComponent
from skin import parseColor, parseFont, skinWarning

from enigma import eListboxServiceContent, eListbox, eServiceCenter, eServiceReference, gFont, eRect
from Tools.LoadPixmap import LoadPixmap

from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN

from Components.config import config

import os


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la folosire."""
	return text

# semnul canalelor transmise acum in retea (Components/HdsTransmisie.py), pictograma din skin
PICTOGRAMA_TRANSMIS = "liste/transmis.png"


def refs_inregistrate(nav=None):
	"""Canalele care se inregistreaza acum, ca texte de referinta, sortate: inregistrarile programate si cele pornite
	cu REC care merg (RecordTimer, starea 'ruleaza'), fara cele numai de pornit canalul (justplay). () fara navigare."""
	if nav is None:
		try:
			import NavigationInstance
			nav = NavigationInstance.instance
		except Exception:
			nav = None
	rez = set()
	try:
		for t in nav.RecordTimer.timer_list:
			if getattr(t, "justplay", False) or not t.isRunning():
				continue
			ref = getattr(getattr(t, "service_ref", None), "ref", None)
			if ref is not None and ref.valid():
				rez.add(ref.toString())
	except Exception:
		pass
	return tuple(sorted(rez))


class ServiceList(HTMLComponent, GUIComponent):
	MODE_NORMAL = 0
	MODE_FAVOURITES = 1

	def __init__(self):
		GUIComponent.__init__(self)
		self.l = eListboxServiceContent()

		pic = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/folder.png"))
		if pic:
			self.l.setPixmap(self.l.picFolder, pic)

		pic = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/marker.png"))
		self.picMarker = pic
		self.marcajFaraIcon = False
		if pic:
			self.l.setPixmap(self.l.picMarker, pic)

		pic = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "ico_dvb_s-fs8.png"))
		if pic:
			self.l.setPixmap(self.l.picDVB_S, pic)

		pic = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "ico_dvb_c-fs8.png"))
		if pic:
			self.l.setPixmap(self.l.picDVB_C, pic)

		pic = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "ico_dvb_t-fs8.png"))
		if pic:
			self.l.setPixmap(self.l.picDVB_T, pic)

		pic = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "ico_service_group-fs8.png"))
		if pic:
			self.l.setPixmap(self.l.picServiceGroup, pic)

		# eticheta din dreapta randului la posturile DAB+ / DVB-T2 din satelit, dupa calea lor (Components/HdsCapLista.py)
		try:
			from Components.HdsCapLista import ETICHETE_CAI
			for marcaj, eticheta in ETICHETE_CAI:
				self.l.setPathLabel(marcaj, eticheta)
		except (ImportError, AttributeError) as e:
			print("[ServiceList] etichetele fluxurilor: %s" % e)

		self.root = None
		self.mode = self.MODE_NORMAL
		self.ItemHeight = 28
		self.ServiceNameFont = parseFont("Regular;22", ((1,1),(1,1)))
		self.ServiceInfoFont = parseFont("Regular;18", ((1,1),(1,1)))
		self.ServiceNumberFont = parseFont("Regular;20", ((1,1),(1,1)))
		self.onSelectionChanged = [ ]
		# canalele care se inregistreaza acum, cum le stie nucleul listei (hdsInregistrari)
		self.hdsInregistrate = ()
		self.hdsCeasInregistrari = None
		# canalele transmise acum in retea, cum le stie nucleul listei (hdsTransmiseAcum): semnul din dreapta randului
		self.hdsTransmise = ()
		# etichetele DVB-I ale randurilor (hdsEticheteDvbI): ce s-a dat ultima oara nucleului listei, si randurile puse cu
		# addService peste radacina (lista "Sateliti" pe grupe le pune asa, nu prin radacina)
		self.hdsEticheteDate = {}
		self.hdsAdaugate = []
		# drumurile buchetelor aratate in lista tuturor buchetelor cu numele tradus (hdsNumeleBuchetelor)
		self.hdsNumite = set()
		if hasattr(self.l, "addStreamed"):
			self.hdsPictogramaTransmis(resolveFilename(SCOPE_CURRENT_SKIN, PICTOGRAMA_TRANSMIS))
			self.l.setStreamedLabel(_("În rețea"))

	COLOR_ATTRIBUTES = {
		"foregroundColorMarked": eListboxServiceContent.markedForeground,
		"foregroundColorMarkedSelected": eListboxServiceContent.markedForegroundSelected,
		"backgroundColorMarked": eListboxServiceContent.markedBackground,
		"backgroundColorMarkedSelected": eListboxServiceContent.markedBackgroundSelected,
		"foregroundColorServiceNotAvail": eListboxServiceContent.serviceNotAvail,
		"colorEventProgressbar": eListboxServiceContent.serviceEventProgressbarColor,
		"colorEventProgressbarSelected": eListboxServiceContent.serviceEventProgressbarColorSelected,
		"colorEventProgressbarBorder": eListboxServiceContent.serviceEventProgressbarBorderColor,
		"colorEventProgressbarBorderSelected": eListboxServiceContent.serviceEventProgressbarBorderColorSelected,
		"colorServiceDescription": eListboxServiceContent.serviceDescriptionColor,
		"colorServiceDescriptionSelected": eListboxServiceContent.serviceDescriptionColorSelected,
		# newer skins name the color of the current event text like this
		"foregroundColorEvent": eListboxServiceContent.serviceDescriptionColor,
		"foregroundColorEventSelected": eListboxServiceContent.serviceDescriptionColorSelected,
	}
	# culoarea canalelor care se inregistreaza acum (numarul si numele, pe randurile nealese): numai cu nucleul care o
	# deseneaza; cu unul mai vechi atributul ramane in ATRIBUTE_NEDESENATE, primit fara efect
	if hasattr(eListboxServiceContent, "serviceRecorded"):
		COLOR_ATTRIBUTES["colorServiceRecorded"] = eListboxServiceContent.serviceRecorded
	# semnul canalelor transmise acum (textul lui, pe randurile nealese si pe cel ales): numai cu nucleul care il deseneaza
	if hasattr(eListboxServiceContent, "serviceStreamed"):
		COLOR_ATTRIBUTES["colorServiceStreamed"] = eListboxServiceContent.serviceStreamed
		COLOR_ATTRIBUTES["colorServiceStreamedSelected"] = eListboxServiceContent.serviceStreamedSelected

	def applySkinAttribute(self, attrib, value):
		"""applies one list attribute; returns False when it belongs to the generic widget attributes"""
		if attrib in self.COLOR_ATTRIBUTES:
			self.l.setColor(self.COLOR_ATTRIBUTES[attrib], parseColor(value))
		elif attrib == "picServiceEventProgressbar":
			pic = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, value))
			if pic:
				self.l.setPixmap(self.l.picServiceEventProgressbar, pic)
		elif attrib == "picServiceStreamed":
			self.hdsPictogramaTransmis(resolveFilename(SCOPE_CURRENT_SKIN, value))
		elif attrib == "progressbarHeight":
			self.l.setProgressbarHeight(int(value))
		elif attrib == "progressbarBorderWidth":
			self.l.setProgressbarBorderWidth(int(value))
		elif attrib == "serviceItemHeight":
			self.ItemHeight = int(value)
		elif attrib == "serviceNameFont":
			self.ServiceNameFont = parseFont(value, ((1,1),(1,1)))
		elif attrib == "serviceInfoFont":
			self.ServiceInfoFont = parseFont(value, ((1,1),(1,1)))
		elif attrib == "serviceNumberFont":
			self.ServiceNumberFont = parseFont(value, ((1,1),(1,1)))
		elif attrib in self.ATRIBUTE_NEDESENATE:
			pass
		else:
			return False
		return True

	# atribute ale skinurilor facute pentru mai multe imagini, pe care lista de aici nu le deseneaza: se primesc fara
	# efect (eListbox nu le are; ajunse la el, jurnalul ar scrie 'attribute ... is not supported yet').
	# colorServiceRecorded ajunge aici numai cu un nucleu fara eListboxServiceContent.serviceRecorded (vezi mai sus).
	ATRIBUTE_NEDESENATE = frozenset(("colorServiceRecorded", "colorServiceStreamed", "colorServiceStreamedSelected",
		"picServiceStreamed"))

	# ---- canalele care se inregistreaza acum
	def hdsInregistrari(self):
		"""Da listei canalele care se inregistreaza acum (refs_inregistrate); lista le scrie numele in culoarea
		colorServiceRecorded si se redeseneaza numai cand multimea s-a schimbat. Fara nucleul care le stie
		(addRecorded), nimic."""
		l = self.l
		if not hasattr(l, "addRecorded"):
			return
		refs = refs_inregistrate()
		if refs == self.hdsInregistrate:
			return
		self.hdsInregistrate = refs
		l.clearRecorded()
		for text in refs:
			l.addRecorded(eServiceReference(text))

	def hdsLaInregistrare(self, serviciu=None, eveniment=None):
		"""Un eveniment al unei inregistrari (navigarea, record_event): pornire, oprire, acord. Starea temporizatorului
		trece pe 'ruleaza' abia dupa ce inregistrarea a pornit, deci multimea se reface putin mai tarziu."""
		try:
			if self.hdsCeasInregistrari is None:
				from enigma import eTimer
				self.hdsCeasInregistrari = eTimer()
				self.hdsCeasInregistrari.callback.append(self.hdsInregistrari)
			self.hdsCeasInregistrari.start(1000, True)
		except Exception as e:
			print("[ServiceList] inregistrarile: %s" % e)

	def hdsLeagaInregistrarile(self, leaga):
		"""Asculta (leaga True) sau nu mai asculta evenimentele inregistrarilor."""
		try:
			import NavigationInstance
			nav = NavigationInstance.instance
			if nav is None:
				return
			if leaga:
				if self.hdsLaInregistrare not in nav.record_event:
					nav.record_event.append(self.hdsLaInregistrare)
			elif self.hdsLaInregistrare in nav.record_event:
				nav.record_event.remove(self.hdsLaInregistrare)
		except Exception as e:
			print("[ServiceList] evenimentele inregistrarilor: %s" % e)
		if not leaga and self.hdsCeasInregistrari is not None:
			self.hdsCeasInregistrari.stop()

	# ---- canalele transmise acum in retea (Components/HdsTransmisie.py, LISTA DE CANALE SI SEMNUL)
	def hdsPictogramaTransmis(self, cale):
		"""Pictograma semnului (picStreamed), daca nucleul o stie si fisierul exista."""
		l = self.l
		if not hasattr(l, "picStreamed") or not cale or not os.path.isfile(cale):
			return
		pic = LoadPixmap(cale)
		if pic:
			l.setPixmap(l.picStreamed, pic)

	def hdsTransmiseAcum(self):
		"""Da listei canalele transmise acum (Manager.transmise: aceleasi inregistrari care cedeaza la zap); lista se
		redeseneaza numai cand multimea s-a schimbat. Fara nucleul care le stie (addStreamed), nimic."""
		l = self.l
		if not hasattr(l, "addStreamed"):
			return
		try:
			from Components import HdsTransmisie
			refs = HdsTransmisie.manager().transmise()
		except Exception as e:
			print("[ServiceList] transmisiile: %s" % e)
			refs = ()
		if refs == self.hdsTransmise:
			return
		self.hdsTransmise = refs
		l.clearStreamed()
		for text in refs:
			l.addStreamed(eServiceReference(text))

	# ---- DVB-I: "DVB-I" pe canalul de satelit care are si varianta de internet, iar in buchetul DVB-I
	# starea canalului incercat din casa ("oprit in tara ta", "adresa moarta", "nu raspunde"). Datele vin din
	# Components/HdsDvbIDate (scrise de pluginul DVB-I); nucleul listei le deseneaza ca eticheta de la capatul randului
	# (setRefLabel, lib/service/listboxservice.cpp). Fara nucleul care le stie, nimic.
	ETICHETE_STARI_DVBI = {"oprit_tara": N_("oprit în țara ta"), "adresa_moarta": N_("adresă moartă"),
		"nu_raspunde": N_("nu răspunde")}

	def hdsEticheteDvbI(self):
		l = self.l
		if not hasattr(l, "setRefLabel") or self.root is None:
			return
		try:
			from Components import HdsDvbIDate as DD
			legaturi = DD.legaturi()
			urluri = set(c.get("url", "") for c in DD.canale())
		except Exception as e:
			print("[ServiceList] etichetele DVB-I: %s" % e)
			legaturi, urluri = {}, set()
		noi = {}
		if legaturi or urluri:
			randuri = []
			lista = eServiceCenter.getInstance().list(self.root)
			while lista is not None:
				s = lista.getNext()
				if not s.valid():
					break
				randuri.append(s)
			for s in randuri + list(self.hdsAdaugate):
				if s.flags & (eServiceReference.isMarker | eServiceReference.isDirectory):
					continue
				if s.type == 1 and legaturi:
					ns = s.getUnsignedData(4)
					cheie = "%X:%X:%X:%X" % (s.getUnsignedData(1), s.getUnsignedData(2), s.getUnsignedData(3), ns & 0xFFFF0000)
					if cheie in legaturi:
						noi[s.toString()] = (s, "DVB-I")
				elif s.type == 4097 and urluri:
					url = s.getPath()
					if url in urluri:
						stare = DD.stareUrl(url)[0]
						if stare in self.ETICHETE_STARI_DVBI:
							noi[s.toString()] = (s, _(self.ETICHETE_STARI_DVBI[stare]))
		vechi = self.hdsEticheteDate
		if dict((k, v[1]) for k, v in noi.items()) == vechi:
			return
		l.clearRefLabels()
		for text, (s, eticheta) in noi.items():
			l.setRefLabel(s, eticheta)
		self.hdsEticheteDate = dict((k, v[1]) for k, v in noi.items())

	def hdsLeagaDvbI(self, leaga):
		"""Afla (leaga True) sau nu mai afla cand pluginul DVB-I a scris date noi (reincarcare, incercari)."""
		if not hasattr(self.l, "setRefLabel"):
			return
		try:
			from Plugins.SystemPlugins.HdsDvbI import plugin as P
			if leaga:
				if self.hdsEticheteDvbI not in P.ASCULTATORI:
					P.ASCULTATORI.append(self.hdsEticheteDvbI)
			elif self.hdsEticheteDvbI in P.ASCULTATORI:
				P.ASCULTATORI.remove(self.hdsEticheteDvbI)
		except Exception as e:
			print("[ServiceList] DVB-I: %s" % e)

	def hdsLeagaTransmise(self, leaga):
		"""Afla (leaga True) sau nu mai afla cand pornesc si se opresc transmisiile."""
		if not hasattr(self.l, "addStreamed"):
			return
		try:
			from Components import HdsTransmisie
			m = HdsTransmisie.manager()
			if leaga:
				m.urmaresteTransmise(self.hdsTransmiseAcum)
			else:
				m.renuntaTransmise(self.hdsTransmiseAcum)
		except Exception as e:
			print("[ServiceList] transmisiile: %s" % e)

	def applySkin(self, desktop, parent):
		attribs = [ ]
		if self.skinAttributes is not None:
			for (attrib, value) in self.skinAttributes:
				# a wrong value is reported and skipped; the rest of the list still gets its skin
				try:
					if not self.applySkinAttribute(attrib, value):
						attribs.append((attrib, value))
				except Exception as e:
					skinWarning("ServiceList: attribute %s=\"%s\" not applied (%s)" % (attrib, value, e))
		self.skinAttributes = attribs
		return GUIComponent.applySkin(self, desktop, parent)

	def connectSelChanged(self, fnc):
		if not fnc in self.onSelectionChanged:
			self.onSelectionChanged.append(fnc)

	def disconnectSelChanged(self, fnc):
		if fnc in self.onSelectionChanged:
			self.onSelectionChanged.remove(fnc)

	def selectionChanged(self):
		for x in self.onSelectionChanged:
			x()

	# ---- buchetul Favorite in lista tuturor buchetelor: numele lui implicit din fisier ("Favourites (TV)", textul
	# englezesc pus de enigma2) se arata tradus, ca in titlul listei (ChannelSelection.getServiceName: "Favorite").
	# Fisierul buchetului ramane neatins. Randul primeste o referinta cu acelasi drum si cu nume: pentru o referinta de
	# buchet cu nume, eServiceFactoryDVB::info da numele referintei (eStaticServiceDVBInformation), nu #NAME din fisier.
	# Spre restul codului (getCurrent, getMarked) iese referinta din fisier, fara nume.
	NUME_FAVORITE = ("Favourites (TV)", "Favourites (Radio)", "Favourites")

	def hdsNumeleBuchetelor(self):
		self.hdsNumite = set()
		root = self.root
		if root is None or self.instance is None or 'FROM BOUQUET "bouquets.' not in (root.getPath() or ""):
			return
		try:
			handler = eServiceCenter.getInstance()
			lista = handler.list(root)
			randuri = []
			while lista is not None:
				s = lista.getNext()
				if not s.valid():
					break
				randuri.append(s)
			numite = {}
			for i, s in enumerate(randuri):
				if not (s.flags & eServiceReference.isDirectory) or s.getName():
					continue
				info = handler.info(s)
				if info is not None and info.getName(s) in self.NUME_FAVORITE:
					numite[i] = _("Favourites")
			if not numite:
				return
			acum = self.getCurrent()
			# ca la listele facute din Python (ChannelSelection: setRoot(..., True), addService, FillFinished)
			self.l.setRoot(root, True)
			for i, s in enumerate(randuri):
				if i in numite:
					s = eServiceReference(s.toString())
					s.setName(numite[i])
					self.hdsNumite.add(s.getPath())
				self.l.addService(s)
			self.l.FillFinished()
			self.l.sort()
			if acum.valid():
				self.l.setCurrent(acum)
		except Exception as e:
			print("[ServiceList] numele buchetelor: %s" % e)

	def hdsFaraNume(self, ref):
		"""Referinta din fisier pentru un rand cu numele tradus (hdsNumeleBuchetelor); celelalte raman cum sunt."""
		numite = getattr(self, "hdsNumite", None)
		if numite and ref.getName() and ref.getPath() in numite:
			ref.setName("")
		return ref

	def setCurrent(self, ref):
		self.l.setCurrent(ref)
		# serviciul cautat nu e in lista (de pilda postul de acum, din alt buchet): cursorul ramanea dupa ultimul rand,
		# iar bara de selectie se desena peste tot locul gol de sub posturi; il punem pe primul rand
		if self.instance is not None and not self.getCurrent().valid():
			self.instance.moveSelectionTo(0)

	def getCurrent(self):
		r = eServiceReference()
		self.l.getCurrent(r)
		return self.hdsFaraNume(r)

	def hdsCurentAfisat(self):
		"""Randul ales cum e desenat in lista (cu numele tradus al buchetului Favorite, hdsNumeleBuchetelor): pentru
		panoul cu numele randului ales. Restul codului foloseste getCurrent (referinta din fisier)."""
		r = eServiceReference()
		self.l.getCurrent(r)
		return r

	def atBegin(self):
		return self.instance.atBegin()

	def atEnd(self):
		return self.instance.atEnd()

	def moveUp(self):
		self.instance.moveSelection(self.instance.moveUp)

	def moveDown(self):
		self.instance.moveSelection(self.instance.moveDown)

	def moveToChar(self, char):
		# TODO fill with life
		print("Next char: ")
		index = self.l.getNextBeginningWithChar(char)
		indexup = self.l.getNextBeginningWithChar(char.upper())
		if indexup != 0:
			if (index > indexup or index == 0):
				index = indexup

		self.instance.moveSelectionTo(index)
		print("Moving to character " + str(char))

	def moveToNextMarker(self):
		idx = self.l.getNextMarkerPos()
		self.instance.moveSelectionTo(idx)

	def moveToPrevMarker(self):
		idx = self.l.getPrevMarkerPos()
		self.instance.moveSelectionTo(idx)

	def moveToIndex(self, index):
		self.instance.moveSelectionTo(index)

	def getCurrentIndex(self):
		return self.instance.getCurrentIndex()

	GUI_WIDGET = eListbox
	
	def postWidgetCreate(self, instance):
		instance.setWrapAround(True)
		instance.setContent(self.l)
		instance.selectionChanged.get().append(self.selectionChanged)
		self.setMode(self.mode)
		self.hdsLeagaInregistrarile(True)
		self.hdsInregistrari()
		self.hdsLeagaTransmise(True)
		self.hdsTransmiseAcum()
		self.hdsLeagaDvbI(True)
		self.hdsNumeleBuchetelor()

	def preWidgetRemove(self, instance):
		instance.setContent(None)
		instance.selectionChanged.get().remove(self.selectionChanged)
		self.hdsLeagaInregistrarile(False)
		self.hdsLeagaTransmise(False)
		self.hdsLeagaDvbI(False)

	def getRoot(self):
		return self.root

	def getRootServices(self):
		serviceHandler = eServiceCenter.getInstance()
		list = serviceHandler.list(self.root)
		dest = [ ]
		if list is not None:
			while 1:
				s = list.getNext()
				if s.valid():
					dest.append(s.toString())
				else:
					break
		return dest

	def setNumberOffset(self, offset):
		self.l.setNumberOffset(offset)

	def setPlayableIgnoreService(self, ref):
		self.l.setIgnoreService(ref)

	def setRoot(self, root, justSet=False):
		self.root = root
		self.hdsAdaugate = []
		self.iconitaMarcaj(root)
		self.hdsInregistrari()
		self.l.setRoot(root, justSet)
		if not justSet:
			self.l.sort()
			self.hdsNumeleBuchetelor()
		else:
			self.hdsNumite = set()
		self.hdsEticheteDvbI()
		self.selectionChanged()

	def iconitaMarcaj(self, root):
		"""In buchetele DAB+ / DVB-T2 din satelit marcajele sunt capetele ansamblurilor („MUX DAB+: DR Deutschland”) si
		se arata fara iconita marcajului (agrafa); in celelalte liste iconita ramane. Un pixmap gol (gPixmapPtr()) nu se
		deseneaza (listboxservice.cpp: if (pixmap))."""
		try:
			from Components.HdsCapLista import buchet_cu_capete
			fara = buchet_cu_capete(root.getPath() if root is not None else "")
		except Exception as e:
			print("[ServiceList] iconita marcajului: %s" % e)
			return
		if fara == self.marcajFaraIcon:
			return
		try:
			if fara:
				from enigma import gPixmapPtr
				self.l.setPixmap(self.l.picMarker, gPixmapPtr())
			elif self.picMarker:
				self.l.setPixmap(self.l.picMarker, self.picMarker)
			self.marcajFaraIcon = fara
		except Exception as e:
			print("[ServiceList] iconita marcajului: %s" % e)

	def removeCurrent(self):
		self.l.removeCurrent()

	def addService(self, service, beforeCurrent=False):
		self.l.addService(service, beforeCurrent)
		if service is not None and len(self.hdsAdaugate) < 20000:
			self.hdsAdaugate.append(service)

	def finishFill(self):
		self.l.FillFinished()
		self.l.sort()
		self.hdsEticheteDvbI()

# stuff for multiple marks (edit mode / later multiepg)
	def clearMarks(self):
		self.l.initMarked()

	def isMarked(self, ref):
		return self.l.isMarked(ref)

	def addMarked(self, ref):
		self.l.addMarked(ref)

	def removeMarked(self, ref):
		self.l.removeMarked(ref)

	def getMarked(self):
		i = self.l
		i.markedQueryStart()
		ref = eServiceReference()
		marked = [ ]
		while i.markedQueryNext(ref) == 0:
			marked.append(self.hdsFaraNume(ref).toString())
			ref = eServiceReference()
		return marked

#just for movemode.. only one marked entry..
	def setCurrentMarked(self, state):
		self.l.setCurrentMarked(state)

	def setMode(self, mode):
		self.mode = mode
		self.l.setItemHeight(self.ItemHeight)
		self.l.setVisualMode(eListboxServiceContent.visModeComplex)
		if mode == self.MODE_NORMAL:
			if config.usage.show_event_progress_in_servicelist.value:
				self.l.setElementPosition(self.l.celServiceEventProgressbar, eRect(0, 0, 52, self.ItemHeight))
			else:
				self.l.setElementPosition(self.l.celServiceEventProgressbar, eRect(0, 0, 0, 0))
			self.l.setElementFont(self.l.celServiceName, self.ServiceNameFont)
			self.l.setElementPosition(self.l.celServiceName, eRect(0, 0, self.instance.size().width(), self.ItemHeight))
			self.l.setElementFont(self.l.celServiceInfo, self.ServiceInfoFont)
		else:
			# HDSatelit: coloana numarului e mai lata cand numerele operatorului au mai multe cifre (radio de la 1001)
			nr = getattr(self, "hdsLatimeNumar", 50)
			if config.usage.show_event_progress_in_servicelist.value:
				self.l.setElementPosition(self.l.celServiceEventProgressbar, eRect(nr + 10, 0, 52, self.ItemHeight))
			else:
				self.l.setElementPosition(self.l.celServiceEventProgressbar, eRect(nr + 10, 0, 0, 0))
			self.l.setElementFont(self.l.celServiceNumber, self.ServiceNumberFont)
			self.l.setElementPosition(self.l.celServiceNumber, eRect(0, 0, nr, self.ItemHeight))
			self.l.setElementFont(self.l.celServiceName, self.ServiceNameFont)
			self.l.setElementPosition(self.l.celServiceName, eRect(nr + 10, 0, self.instance.size().width() - nr - 10, self.ItemHeight))
			self.l.setElementFont(self.l.celServiceInfo, self.ServiceInfoFont)

	# HDSatelit: numerele operatorului in lista unei retele de cablu (Components/HdsRetele.py, Screens/ChannelSelection.py
	# hdsUmpleRetea): in coloana numarului fiecare canal are numarul dat de operator (23 = TVR 1, cu golurile lui), nu
	# locul randului (lib/service/listboxservice.cpp, setRefNumber). Celelalte liste raman cu numaratoarea randurilor.
	HDS_LATIME_NUMAR = 50

	def hdsNumereOperator(self, numere):
		"""numere: [(referinta, numarul)] pentru lista de acum, sau None (alta lista: numaratoarea randurilor).
		-> True daca nucleul le poate arata."""
		l = self.l
		if not hasattr(l, "setRefNumber"):
			return False
		l.clearRefNumbers()
		latime = self.HDS_LATIME_NUMAR
		if numere:
			for ref, numar in numere:
				l.setRefNumber(ref, int(numar))
			cifre = len(str(max(int(n) for _r, n in numere)))
			try:
				marime = int(self.ServiceNumberFont.pointSize)
			except Exception:
				marime = 28
			latime = max(latime, cifre * marime * 62 // 100 + 8)
		if latime != getattr(self, "hdsLatimeNumar", self.HDS_LATIME_NUMAR):
			self.hdsLatimeNumar = latime
			if getattr(self, "mode", None) is not None and self.mode != self.MODE_NORMAL and self.instance is not None:
				self.setMode(self.mode)
		return True

