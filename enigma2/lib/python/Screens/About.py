# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.ScrollLabel import ScrollLabel
from Components.Harddisk import harddiskmanager
from Components.NimManager import nimmanager
from Components.About import about

from Tools.DreamboxHardware import getFPVersion

class About(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("About"))

		receiver_name = about.getReceiverName()
		image_ver = about.getImageVersionString()
		enigma_ver = about.getEnigmaVersionString()
		kernel_ver = about.getKernelVersionString()
		uptime_str = about.getUptimeString()

		cpu_model, cpu_cores = about.getCPUInfo()
		ram_total, ram_available = about.getRAMInfo()
		storage_total, storage_free, storage_used = about.getStorageInfo("/")

		# Surse individuale pentru skin_default sau skinuri clasice
		self["EnigmaVersion"] = StaticText("Enigma: " + enigma_ver)
		self["ImageVersion"] = StaticText("HD Satelit: " + image_ver)
		self["ReceiverName"] = StaticText(_("Receiver: %s") % receiver_name)
		self["CPUInfo"] = StaticText(_("Processor: %s (%d cores)") % (cpu_model, cpu_cores))
		self["RAMInfo"] = StaticText(_("RAM: %s, available %s") % (about.formatSize(ram_total), about.formatSize(ram_available)))
		self["StorageInfo"] = StaticText(_("Storage: %s, used %s, free %s") % (about.formatSize(storage_total), about.formatSize(storage_used), about.formatSize(storage_free)))
		self["KernelVersion"] = StaticText(_("Kernel: %s") % kernel_ver)
		self["Uptime"] = StaticText(_("Uptime: %s") % uptime_str)

		self["TunerHeader"] = StaticText(_("Detected NIMs:"))

		fp_version = getFPVersion()
		if fp_version is None:
			fp_str = ""
		else:
			fp_str = _("Frontprocessor version: %d") % fp_version
		self["FPVersion"] = StaticText(fp_str)

		nims = nimmanager.nimList()
		for count in (0, 1, 2, 3):
			if count < len(nims):
				self["Tuner" + str(count)] = StaticText(nims[count])
			else:
				self["Tuner" + str(count)] = StaticText("")

		self["HDDHeader"] = StaticText(_("Detected HDD:"))
		hddlist = harddiskmanager.HDDList()
		hdd = hddlist and hddlist[0][1] or None
		if hdd is not None and hdd.model() != "":
			hdd_str = _("%s (%s, %s free)") % (hdd.model(), hdd.capacity(), about.formatSize(hdd.free()))
			self["hddA"] = StaticText(hdd_str)
		else:
			hdd_str = _("none")
			self["hddA"] = StaticText(_("none"))

		# Constructie text complet structurat pentru panourile AboutOE (HDSatelit si alte imagini)
		lines = [
			_("HARDWARE & DISPOZITIV"),
			"  " + _("Receptor") + ": " + receiver_name,
			"  " + _("Procesor") + ": " + cpu_model + " (" + str(cpu_cores) + " " + _("nuclee") + ")",
			"  " + _("Memorie RAM") + ": " + about.formatSize(ram_total) + " (" + _("disponibil") + " " + about.formatSize(ram_available) + ")",
			"  " + _("Stocare flash") + ": " + about.formatSize(storage_total) + " (" + _("liber") + " " + about.formatSize(storage_free) + ", " + _("ocupat") + " " + about.formatSize(storage_used) + ")",
			"",
			_("SISTEM & SOFTWARE"),
			"  " + _("Distribuție") + ": " + image_ver,
			"  " + _("Versiune Enigma") + ": " + enigma_ver,
			"  " + _("Versiune Kernel") + ": " + kernel_ver,
			"  " + _("Timp funcționare") + ": " + uptime_str,
		]
		if fp_str:
			lines.append("  " + fp_str)

		lines.append("")
		lines.append(_("TUNERE DETECTATE"))
		if nims:
			for i, nim in enumerate(nims):
				if nim.strip().lower().startswith("tuner"):
					lines.append("  %s" % nim.strip())
				else:
					lines.append("  Tuner %s: %s" % (chr(ord('A') + i), nim.strip()))
		else:
			lines.append("  " + _("Niciun tuner detectat"))

		lines.append("")
		lines.append(_("DISPOZITIVE STOCARE"))
		lines.append("  HDD: " + hdd_str)

		# HDSatelit: lista de sateliti/cablu/terestru (satellites.xml/cables.xml/terrestrial.xml) vine din pachetul
		# tuxbox-common (cod deschis), nu e compilata de noi; sursa e scrisa aici vizibil, cu acelasi text ca in
		# "Despre imagine" (Screens/Information.py, HdsAbout), fara nume de comunitati sau situri straine
		lines.append("")
		lines.append(_("SURSA LISTEI DE CANALE"))
		lines.append("  " + _("Lista inițială de sateliți/cablu/terestru (transpondere) provine din"))
		lines.append("  " + _("pachetul tuxbox-common (cod deschis, date tehnice publice); licența e la Licențe"))

		clean_lines = []
		for line in lines:
			if isinstance(line, str):
				clean_lines.append("".join(c for c in line if (ord(c) < 0xD800 or ord(c) > 0xDFFF) and (ord(c) >= 32 or c in "\n\t")))
			else:
				clean_lines.append(str(line or ""))

		full_about_text = "\n".join(clean_lines)
		self["AboutScrollLabel"] = ScrollLabel(full_about_text)
		self["HintText"] = StaticText(_("Folosește săgețile Sus / Jos pentru derulare. Apasă OK sau Ieșire pentru a închide."))

		self["key_red"] = StaticText(_("Închide"))
		self["key_green"] = StaticText(_("Traduceri"))

		self["actions"] = ActionMap(["SetupActions", "ColorActions", "DirectionActions"], 
			{
				"cancel": self.close,
				"ok": self.close,
				"red": self.close,
				"green": self.showTranslationInfo,
				"up": self.scrollUp,
				"down": self.scrollDown,
				"pageUp": self.scrollPageUp,
				"pageDown": self.scrollPageDown,
			}, -1)

	def scrollUp(self):
		self["AboutScrollLabel"].pageUp()

	def scrollDown(self):
		self["AboutScrollLabel"].pageDown()

	def scrollPageUp(self):
		self["AboutScrollLabel"].pageUp()

	def scrollPageDown(self):
		self["AboutScrollLabel"].pageDown()

	def showTranslationInfo(self):
		self.session.open(TranslationInfo)

class TranslationInfo(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Translation"))
		# don't remove the string out of the _(), or it can't be "translated" anymore.

		# TRANSLATORS: Add here whatever should be shown in the "translator" about screen, up to 6 lines (use \n for newline)
		info = _("TRANSLATOR_INFO")

		if info == "TRANSLATOR_INFO":
			info = "Localizare și optimizare pentru limba română:\nHD Satelit (https://hdsatelit.com)"

		# gettext("") intoarce antetul fisierului de traduceri (echipa, traducator);
		# cheia goala trece printr-o variabila ca xgettext sa nu o extraga
		header_key = ""
		infolines = _(header_key).split("\n")
		infomap = {}
		for x in infolines:
			l = x.split(': ')
			if len(l) != 2:
				continue
			(type, value) = l
			infomap[type] = value

		self["TranslationInfo"] = StaticText(info)

		translator_name = infomap.get("Language-Team", "none")
		if translator_name in ("none", ""):
			translator_name = infomap.get("Last-Translator", "")
		if not translator_name or translator_name == "none":
			translator_name = "Echipa HD Satelit"

		self["TranslatorName"] = StaticText(translator_name)
		self["key_red"] = StaticText(_("Închide"))

		self["actions"] = ActionMap(["SetupActions", "ColorActions"], 
			{
				"cancel": self.close,
				"ok": self.close,
				"red": self.close,
			})
