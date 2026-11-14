# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .config import config, ConfigSelection, ConfigSubsection, ConfigOnOff, ConfigText
from Components.Timezones import timezones
from Components.Language import language
from Components.Keyboard import keyboard

def InitSetupDevices():
	
	def timezoneNotifier(configElement):
		timezones.activateTimezone(configElement.index)
		
	config.timezone = ConfigSubsection();
	config.timezone.val = ConfigSelection(default = timezones.getDefaultTimezone(), choices = timezones.getTimezoneList())
	config.timezone.val.addNotifier(timezoneNotifier)
	timezones.autoDetectTimezone()


	def keyboardNotifier(configElement):
		keyboard.activateKeyboardMap(configElement.index)

	config.keyboard = ConfigSubsection();
	config.keyboard.keymap = ConfigSelection(default = keyboard.getDefaultKeyboardMap(), choices = keyboard.getKeyboardMaplist())
	config.keyboard.keymap.addNotifier(keyboardNotifier)

	def languageNotifier(configElement):
		language.activateLanguage(configElement.value)
	
	config.osd = ConfigSubsection()
	config.osd.language = ConfigText(default = "ro_RO");
	# limba asistentului de la prima pornire dupa tara (Components/HdsLimbaTara.py): aici, cand randul din settings
	# tocmai a fost citit (inaintea lui HdsCopieSetari.fixeaza_setari, care il scrie la fiecare pornire); la prima pornire
	# fara limba aleasa de om, tara se cauta pe un fir, fara sa intarzie pornirea
	try:
		from Components import HdsLimbaTara
		HdsLimbaTara.laPornire(config.osd.language)
	except Exception as e:
		print("[SetupDevices] limba dupa tara: %r" % (e,))
	config.osd.language.addNotifier(languageNotifier)

	# marimea fonturilor (Screens/FontSetup.py, config.osd.fontscale) se pune de la pornire, inaintea primului ecran:
	# skin.parseFont o foloseste la fiecare ecran construit; fara apelul acesta valoarea salvata se vedea numai dupa
	# Salveaza in ecranul ei. config.osd tocmai a fost facut din nou, deci elementul se face aici din valoarea salvata.
	try:
		from Screens.FontSetup import aplicaScalareFonturi
		aplicaScalareFonturi()
	except Exception as e:
		print("[SetupDevices] marimea fonturilor nu s-a putut pune: %r" % (e,))

	config.parental = ConfigSubsection();
	config.parental.lock = ConfigOnOff(default = False)
	config.parental.setuplock = ConfigOnOff(default = False)

	config.expert = ConfigSubsection();
	config.expert.satpos = ConfigOnOff(default = True)
	config.expert.fastzap = ConfigOnOff(default = True)
	config.expert.skipconfirm = ConfigOnOff(default = False)
	config.expert.hideerrors = ConfigOnOff(default = False)
	config.expert.autoinfo = ConfigOnOff(default = True)
