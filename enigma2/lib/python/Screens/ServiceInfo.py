# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.HTMLComponent import HTMLComponent
from Components.GUIComponent import GUIComponent
from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from Components.NimManager import nimmanager
from ServiceReference import ServiceReference
from enigma import eListboxPythonMultiContent, eListbox, iServiceInformation, eServiceCenter
from Tools.Transponder import ConvertToHumanReadable
import os
# HDSatelit: randurile celor patru pagini (Serviciu, PID-uri, Multiplex, Stare tuner) si formatarea lor stau in
# Components/HdsInformatiiCanal.py, aceleasi pentru acest ecran si pentru pagina web /informatii-canal
# (Plugins/Extensions/HdsWebControl/canal_info_web.py). Aici raman desenul listei, getReceiverConnectionInfo si numele
# receptorului, date componentei ca argumente.
from Components import HdsInformatiiCanal as H
# HDSatelit: fontul randurilor e pus din cod, deci urmeaza Marimea textului prin Components/HdsMarireText (marimeCod,
# inaltimeCod: cu textul marit randul si casetele textului cresc odata cu fontul; la 100 % aceleasi numere)
from Components import HdsMarireText as MT

RT_HALIGN_LEFT = 0

TYPE_TEXT = H.TYPE_TEXT
TYPE_VALUE_HEX = H.TYPE_VALUE_HEX
TYPE_VALUE_DEC = H.TYPE_VALUE_DEC
TYPE_VALUE_HEX_DEC = H.TYPE_VALUE_HEX_DEC
TYPE_SLIDER = 4

to_unsigned = H.to_unsigned

def _scaraRanduri():
	"""(sx, sy, sf, font): randurile sunt scrise pe 1920x1080 (skinul HDSatelit); sub un skin cu alta rezolutie
	se inmultesc cu marimea ecranului (skin.factorHds), cu fontul HD Satelit (skin.fontHds). Pe 1920x1080 cu HDSatelit:
	(1.0, 1.0, 1.0, "Regular"), deci aceleasi numere ca inainte."""
	try:
		import skin
		sx, sy, sf = skin.factorHds()
		return sx, sy, sf, skin.fontHds("Regular")
	except Exception:
		return 1.0, 1.0, 1.0, "Regular"

def ServiceInfoListEntry(a, b, valueType=TYPE_TEXT, param=4):
	b = H.formateaza(b, valueType, param)
	# HDSatelit: coloanele pe 1920x1080, inmultite cu marimea ecranului
	sx, sy = _scaraRanduri()[:2]
	def x(v):
		return int(round(v * sx))
	def y(v):
		return MT.inaltimeCod(int(round(v * sy)))

	# HDSatelit: primul element e randul (eticheta, valoarea), nu None: eListbox muta pagina numai pe randuri
	# selectabile, iar un rand care incepe cu None e neselectabil (ca in Screens/Information.py); selectia nu se vede
	# (selectionDisabled in skin)
	if not a:
		return [
			(a, b),
			(eListboxPythonMultiContent.TYPE_TEXT, x(16), y(4), x(1680), y(40), 0, RT_HALIGN_LEFT, b)
		]
	return [
		(a, b),
		(eListboxPythonMultiContent.TYPE_TEXT, x(16), y(4), x(450), y(40), 0, RT_HALIGN_LEFT, a),
		(eListboxPythonMultiContent.TYPE_TEXT, x(480), y(4), x(1200), y(40), 0, RT_HALIGN_LEFT, b)
	]


def ServiceInfoListEntries(a, b, valueType=TYPE_TEXT, param=4):
	"""Randurile listei pentru o valoare: una mai lata decat coloana ei (o adresa IPTV lunga) continua pe randurile de
	dedesubt, cu eticheta goala, in loc sa fie taiata la margine (masurata cu fontul listei, Regular 28, marit ca el)."""
	b = H.formateaza(b, valueType, param)
	try:
		from Components import HdsInformatiiTabel as T
		sx, _sy, sf, font = _scaraRanduri()
		bucati = T.rupt(b, int(round((1680 if not a else 1200) * sx)), font, MT.marimeCod(max(1, int(round(28 * sf)))))
	except Exception as e:
		print("[ServiceInfo] ruperea valorii: %r" % (e,))
		bucati = [b]
	# continuarea: sub valoare (eticheta un spatiu, deci tot in coloana valorii), sau pe toata latimea fara eticheta
	return [ServiceInfoListEntry(a, bucati[0])] + [ServiceInfoListEntry(" " if a else "", x) for x in bucati[1:]]

class ServiceInfoList(HTMLComponent, GUIComponent):
	def __init__(self, source):
		GUIComponent.__init__(self)
		self.l = eListboxPythonMultiContent()
		self.list = source
		self.l.setList(self.list)
		_sx, sy, sf, font = _scaraRanduri()
		self.l.setFont(0, MT.fontCod(font, max(1, int(round(28 * sf)))))
		self.rand = MT.inaltimeCod(max(1, int(round(48 * sy))))
		self.l.setItemHeight(self.rand)

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		self.instance.setContent(self.l)

	def applySkin(self, desktop, parent):
		ret = GUIComponent.applySkin(self, desktop, parent)
		# itemHeight din skin (48) ar pune randul inapoi: cu textul marit ramane cel socotit aici
		MT.randuriCod(self, self.rand)
		return ret

TYPE_SERVICE_INFO = 1
TYPE_TRANSPONDER_INFO = 2

def getReceiverConnectionInfo():
	"""
	Verifică starea legăturii dintre emulatorul PC și receptorul fizic (Amiko Viper 4K V20).
	Returnează un dicționar cu starea conectării, adresa receptorului și tunerele active.
	"""
	is_pc_emu = not os.path.exists("/proc/stb/info/model") or bool(os.environ.get("HDS_DECODOR")) or bool(os.environ.get("HDS_TUNER"))
	hds_tuner = os.environ.get("HDS_TUNER") or os.environ.get("HDS_RECEPTOR")
	hds_sloturi = os.environ.get("HDS_TUNER_SLOTURI") or os.environ.get("HDS_RECEPTOR_SLOTURI")
	cheie_path = os.environ.get("HDS_TUNER_CHEIE_FISIER", "/dev/shm/hds/cheie.json")
	cheie_ok = os.path.exists(cheie_path)

	jurnal_path = os.environ.get("HDS_TUNER_JURNAL", "/iesire/dvbfals.log")
	log_connected = False
	adresa_jurnal = ""
	connected_tuners = []
	if os.path.exists(jurnal_path):
		try:
			with open(jurnal_path, "r", encoding="utf-8", errors="ignore") as f:
				for line in f:
					if "legat si autentificat la" in line:
						log_connected = True
						# adresa receptorului scrisa in jurnal dupa "la"
						rest = line.split("legat si autentificat la", 1)[1].split()
						adresa_jurnal = rest[0].strip(",;") if rest else adresa_jurnal
					if "tuner 0 = slot 0" in line:
						t_name = "Tuner A (Satelit DVB-S2X)"
						if t_name not in connected_tuners:
							connected_tuners.append(t_name)
					if "tuner 1 = slot 1" in line:
						t_name = "Tuner B (Cablu/Terestru DVB-C/T2)"
						if t_name not in connected_tuners:
							connected_tuners.append(t_name)
		except Exception:
			pass

	is_connected = bool(hds_tuner and cheie_ok) or log_connected
	receiver_target = hds_tuner or (adresa_jurnal if is_connected else "")
	if not connected_tuners and is_connected:
		connected_tuners = ["Tuner A (Satelit DVB-S2X)", "Tuner B (Cablu/Terestru DVB-C/T2)"]

	return {
		"is_pc_emu": is_pc_emu,
		"is_connected": is_connected,
		"receiver_target": receiver_target,
		"slots": hds_sloturi or "0,1",
		"connected_tuners": connected_tuners
	}

class ServiceInfo(Screen):
	def __init__(self, session, serviceref=None):
		Screen.__init__(self, session)
		self.skinName = ["ServiceInfo", "ServiceInfoSimple"]
		self.setTitle(_("Service info") if _("Service info") != "Service info" else "Informații serviciu")

		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"],
		{
			"ok": self.close,
			"cancel": self.close,
			"red": self.information,
			"green": self.pids,
			"yellow": self.transponder,
			"blue": self.tuner
		}, -1)
		# Sus, Jos, Stanga, Dreapta dau pagina listei (CH+ si CH- o dau prin lista, din C++); tinute apasat merg mai
		# departe, ridicarea tastei nu face nimic (altfel jurnalul scrie „unknown action”)
		directii = {"up": self.paginaSus, "down": self.paginaJos, "left": self.paginaSus, "right": self.paginaJos}
		for s in ("up", "down", "left", "right"):
			directii[s + "Repeated"] = directii[s]
			directii[s + "Up"] = self._nimic
		self["directii"] = ActionMap(["DirectionActions"], directii, -1)

		if serviceref:
			self.type = TYPE_TRANSPONDER_INFO
			self["red"] = Label()
			self["green"] = Label()
			self["yellow"] = Label()
			self["blue"] = Label()
			self["key_red"] = self["red"]
			self["key_green"] = self["green"]
			self["key_yellow"] = self["yellow"]
			self["key_blue"] = self["blue"]
			info = eServiceCenter.getInstance().info(serviceref)
			self.transponder_info = info and info.getInfoObject(serviceref, iServiceInformation.sTransponderData)
			self.info = None
			self.feinfo = None
		else:
			self.type = TYPE_SERVICE_INFO
			red_text = _("Service") if _("Service") != "Service" else "Serviciu"
			green_text = _("PIDs") if _("PIDs") != "PIDs" else "PID-uri"
			yellow_text = _("Multiplex")
			blue_text = _("Tuner status") if _("Tuner status") != "Tuner status" else "Stare tuner"
			self["red"] = Label(red_text)
			self["green"] = Label(green_text)
			self["yellow"] = Label(yellow_text)
			self["blue"] = Label(blue_text)
			self["key_red"] = self["red"]
			self["key_green"] = self["green"]
			self["key_yellow"] = self["yellow"]
			self["key_blue"] = self["blue"]
			service = session.nav.getCurrentService()
			if service is not None:
				self.info = service.info()
				self.feinfo = service.frontendInfo()
			else:
				self.info = None
				self.feinfo = None

		tlist = [ ]
		self["infolist"] = ServiceInfoList(tlist)
		self.onShown.append(self.information)

	def information(self):
		if self.type == TYPE_SERVICE_INFO:
			name, refstr = H.numeSiReferinta(self.session.nav.getCurrentlyPlayingServiceReference(), ServiceReference)
			self.fillList(H.randuriServiciu(self.info, iServiceInformation, name, refstr))
		else:
			if self.transponder_info:
				Labels = self.getTransponderLabels(self.transponder_info)
				self.fillList(Labels)

	def pids(self):
		if self.type == TYPE_SERVICE_INFO:
			self.fillList(H.randuriPid(self.info, iServiceInformation))

	def transponder(self):
		if self.type != TYPE_SERVICE_INFO:
			return
		# datele vii ale redarii, apoi transponderul din lista de canale, apoi informatiile serviciului
		frontendData = H.dateFrontend(self.feinfo, self.session.nav.getCurrentlyPlayingServiceReference(), self.info,
			eServiceCenter.getInstance(), iServiceInformation)
		Labels = self.getTransponderLabels(frontendData)
		self.fillList(Labels)

	def getTransponderLabels(self, frontendDataOrg):
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		refstr = ref.toString() if ref else ""
		return H.randuriTransponder(frontendDataOrg, refstr, getReceiverConnectionInfo(), ConvertToHumanReadable)

	def tuner(self):
		if self.type != TYPE_SERVICE_INFO:
			return
		rec_info = getReceiverConnectionInfo()
		mod_receptie = ""
		if not rec_info["is_pc_emu"]:
			# Pe receptorul fizic: numele receptorului si ale cipurilor tuner erau fixe
			# ("Amiko Viper 4K V20", "AVL6261C"/"SI2168") -- pe un al doilea receptor ar fi aratat gresit. Detectie
			# reala: about.getReceiverName() pentru numele receptorului, nimmanager.getNimDescription() (in
			# componenta) pentru cipurile tuner.
			from Components.About import about as _about_info
			mod_receptie = _("Direct pe receptorul %s") % _about_info.getReceiverName()
		Labels = H.randuriTuner(rec_info, self.feinfo, self.session.nav.getCurrentlyPlayingServiceReference(),
			eServiceCenter.getInstance(), iServiceInformation, nimmanager, mod_receptie)
		self.fillList(Labels)

	def fillList(self, Labels):
		tlist = [ ]

		for item in Labels:
			if item[1] is None:
				continue
			value = item[1]
			prefix = (item[0] + ":") if item[0] else ""
			if len(item) < 4:
				tlist.extend(ServiceInfoListEntries(prefix, value, item[2]))
			else:
				tlist.extend(ServiceInfoListEntries(prefix, value, item[2], item[3]))

		self["infolist"].l.setList(tlist)
		# fiecare pagina (Rosu, Verde, Galben, Albastru) incepe sus, nu unde ramasese cea dinainte
		if self["infolist"].instance is not None:
			self["infolist"].instance.moveSelectionTo(0)

	def _nimic(self):
		pass

	def _muta(self, cum):
		lista = self["infolist"].instance
		if lista is not None:
			lista.moveSelection(cum)

	def paginaSus(self):
		self._muta(eListbox.pageUp)

	def paginaJos(self):
		self._muta(eListbox.pageDown)

	def getHdrText(self):
		return H.textHdr(self.info, iServiceInformation)

	def getServiceInfoValue(self, what):
		return H.valoare(self.info, what)
