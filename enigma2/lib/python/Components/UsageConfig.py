# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.Harddisk import harddiskmanager
from .config import ConfigSubsection, ConfigYesNo, config, ConfigSelection, ConfigText, ConfigNumber, ConfigSet, ConfigLocations
from Tools.Directories import resolveFilename, SCOPE_HDD
from enigma import Misc_Options, setTunerTypePriorityOrder, eEnv;
from .SystemInfo import SystemInfo
import os

config.usage = ConfigSubsection()
config.usage.keymap = ConfigText(default = eEnv.resolve("${datadir}/enigma2/keymap.xml"))
# Temele LCD citesc valoarea prin ConfigEntryTest si arata semnul REC intermitent.
config.usage.blinking_rec_symbol_during_recording = ConfigYesNo(default=True)
# HDSatelit: releul de flux al modulului de acces, cu nume neutre; valorile salvate sub numele de dinainte trec aici la
# prima pornire (Components/HdsMutareSetari.py, chemat dupa definirea cheilor din config.misc, mai jos)
config.usage.acces_streamrelay_url = ConfigText(default = "http://127.0.0.1:17999")
config.usage.acces_streamrelay_port = ConfigNumber(default = 17999)
config.usage.acces_streamrelay_delay = ConfigNumber(default = 50)
# HDSatelit: hasattr(config, ...) NU e sigur -- ConfigSubsection.__getattr__ arunca
# KeyError (nu AttributeError) pentru o cheie lipsa, iar hasattr() din Python 3 prinde doar
# AttributeError. Modulul asta se importa foarte devreme la pornire; daca ordinea de import
# se schimba vreodata si config.misc chiar lipseste aici, hasattr() ar fi picat toata pornirea.
if "misc" not in config.content.items:
	config.misc = ConfigSubsection()
config.misc.acces_streamrelay_url = ConfigText(default = "http://127.0.0.1:17999")
config.misc.acces_streamrelay_port = ConfigNumber(default = 17999)
config.misc.acces_streamrelay_delay = ConfigNumber(default = 50)


def _mutaSetarileVechi():
	"""HDSatelit: valorile releului salvate sub numele de dinainte trec la cheile de mai sus (o singura data: cheia veche
	se scoate); orice eroare de aici nu opreste pornirea."""
	try:
		from .HdsMutareSetari import muta_releul_peste_tot
		muta_releul_peste_tot(config, lambda t: print("[UsageConfig] setare mutata: %s" % t))
	except Exception as e:
		print("[UsageConfig] mutarea setarilor vechi: %s" % e)


_mutaSetarileVechi()


def _stareStreamRelay():
	"""HDSatelit 0.7.1: randurile starii Stream Relay pentru ecranul setarilor (atributul hdsStare, Screens/Setup.py)."""
	try:
		from Components import HdsStreamRelay
		return HdsStreamRelay.liniiStare()
	except Exception as e:
		print("[UsageConfig] starea Stream Relay: %s" % e)
		return []

def N_(text):
	"""Marcheaza un text pentru traducere fara sa-l traduca acum (xgettext -kN_): ConfigSelection traduce descrierile
	la afisare, iar limba aleasa se activeaza dupa InitUsageConfig."""
	return text


def ngettext(unu, multe, n):
	"""Forma de plural din traducerea activa ("%d secundă" / "%d secunde"; in romana singularul cu litere, "o secundă",
	si pluralul fara "de", "20 secunde"), sau None cand limba activa nu are textul (limbile fara textele noi si
	pornirea, inainte de activarea limbii). enigma2 instaleaza numai _ (Components/Language.py), dar _ e metoda
	obiectului de traducere, deci catalogul si ngettext-ul lui se iau de acolo."""
	try:
		import builtins
		traducere = getattr(builtins.__dict__.get("_"), "__self__", None)
		catalog = getattr(traducere, "_catalog", None)
		if catalog is not None and (unu, 0) in catalog:
			# Forma: % merge si cand forma pentru 1 n-are numarul ("o secundă", "un minut" in ro.po)
			try:
				from Components.HdsPlural import Forma
			except ImportError:
				return traducere.ngettext(unu, multe, n)
			return Forma(traducere.ngettext(unu, multe, n), multe)
	except Exception as eroare:
		print("[UsageConfig] pluralul „%s”: %s" % (unu, eroare))
	return None


def _cuNumar(n, forma, unitate):
	"""20 secunde (sau o secundă) din forma de plural tradusa; fara ea numarul si unitatea tradusa separat
	(20 seconds)."""
	return forma % n if forma else "%d %s" % (n, unitate)


def _alegeriCuNumere():
	"""Alegerile cu numere ale duratei barei de informatii si ale opririi discului, in limba activa acum. Textul e
	compus din numar si unitate, deci ConfigSelection nu il poate traduce la afisare ca pe un text intreg (getMulti
	ar cauta in po tot textul); de aceea se compune din nou la fiecare activare a unei limbi. Secundele si minutele
	vin din pluralul tradus (ngettext), ca romana sa aiba "o secundă", "un minut", "o oră" (singularul cu litere) si
	"20 secunde" (fara "de")."""
	secunda, secunde = _("second"), _("seconds")
	minut, minute = _("minute"), _("minutes")
	ora, ore = _("hour"), _("hours")

	def sec(n):
		return _cuNumar(n, ngettext("%d secundă", "%d secunde", n), secunda if n == 1 else secunde)

	def mn(n):
		return _cuNumar(n, ngettext("%d minut", "%d minute", n), minut if n == 1 else minute)

	def hr(n):
		return _cuNumar(n, ngettext("%d oră", "%d ore", n), ora if n == 1 else ore)

	# bara de informatii: si durate mai lungi (12..30 s); InfoBarGenerics foloseste valoarea, nu pozitia din lista
	infobar = [("0", _("no timeout"))] + [(str(n), sec(n)) for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 30)]
	disc = [("0", _("no standby")), ("10", sec(10)), ("30", sec(30)),
		("60", mn(1)), ("120", mn(2)), ("300", mn(5)), ("600", mn(10)),
		("1200", mn(20)), ("1800", mn(30)), ("3600", hr(1)), ("7200", hr(2)),
		("14400", hr(4))]
	return infobar, disc


def _traduAlegerileCuNumere():
	"""Chemata de Language.activateLanguage. Valoarea aleasa ramane; textul tinut minte de getText/getMulti (_descr)
	e al limbii de dinainte, deci se uita. O eroare se scrie aici: activateLanguage prinde orice exceptie a
	chemarilor si ar raporta-o ca limba inexistenta."""
	try:
		infobar, disc = _alegeriCuNumere()
		for element, alegeri in ((config.usage.infobar_timeout, infobar), (config.usage.hdd_standby, disc)):
			element.setChoices(alegeri, default = element.default)
			element._descr = None
	except Exception as eroare:
		print("[UsageConfig] alegerile cu numere nu s-au tradus: %s" % eroare)


def _setariCerutePluginuri():
	"""Setari pe care imaginea nu le foloseste, citite de pluginuri (config.usage.date...). Nu apar in niciun ecran al nostru;
	un plugin le poate citi si salva. Ce exista deja nu se atinge."""
	from Components.config import ConfigInteger, ConfigSelection, ConfigSubsection, ConfigText, ConfigYesNo, config

	def pune(sectiune, nume, element):
		if not hasattr(sectiune, nume):
			setattr(sectiune, nume, element)

	for sectiune in ("autolanguage", "timeshift", "epg", "recording", "subtitles", "misc"):
		if not hasattr(config, sectiune):
			setattr(config, sectiune, ConfigSubsection())
	pune(config.usage, "date", ConfigSubsection())
	for nume, implicit in (("dayfull", "%a %d.%m.%Y"), ("shortdayfull", "%a %d.%m.%Y"), ("daylong", "%A %d %B %Y"), ("dayshort", "%a %d.%m.%Y"), ("daysmall", "%a %d.%m"), ("full", "%d.%m.%Y"), ("long", "%d %B %Y"), ("short", "%d.%m.%Y"), ("compact", "%d.%m"), ("compressed", "%d%m%y"), ("display", "%d.%m.%Y")):
		pune(config.usage.date, nume, ConfigText(default=implicit))
	pune(config.usage, "time", ConfigSubsection())
	for nume, implicit in (("long", "%T"), ("short", "%R"), ("mins", "%R"), ("wide", False), ("display", "%R")):
		pune(config.usage.time, nume, ConfigYesNo(default=False) if implicit is False else ConfigText(default=implicit))
	for nume in ("subnetwork", "subnetwork_terrestrial", "subnetwork_cable", "movielist_trashcan", "check_timeshift"):
		pune(config.usage, nume, ConfigYesNo(default=True))
	for nume in ("alternative_number_mode", "sort_settings", "timeshift_skipreturntolive"):
		pune(config.usage, nume, ConfigYesNo(default=False))
	pune(config.usage, "servicelist_cursor_behavior", ConfigText(default="keep"))
	pune(config.usage, "show_menupath", ConfigText(default="small"))
	# randul cu modulul de acces din bara temelor facute pentru OE-Alliance (convertorul MercPliExtraInfo: int(valoare) > 0);
	# ca in OE-Alliance: 0 oprit, 1 un rand, 2 doua randuri; fara texte: nu apare in niciun ecran al nostru.
	# Valorile sunt numere, ca in OE-Alliance: PliExtraInfo de acum face `config.usage.show_cryptoinfo.value > 0`, care cu
	# textul "2" cadea (TypeError) si lasa goala bara de codare a temei (darog69, forum 1455, TCN 15.11.2026); textul
	# salvat ("1") se citeste inapoi ca numar (ConfigSelection.fromstring).
	pune(config.usage, "show_cryptoinfo", ConfigSelection(default=2, choices=[(0, "0"), (1, "1"), (2, "2")]))
	# de unde iau temele OE-Alliance datele transponderului din bara (feinfo.getAll(valoare == "settings")): ca in OE-Alliance,
	# implicit "tuner"; tema BlueAccents-HD cadea la fiecare canal fara ea (asistenta 821342, 14.11.2026). Fara rand in meniu.
	pune(config.usage, "infobar_frontend_source", ConfigSelection(default="tuner", choices=["settings", "tuner"]))
	pune(config.usage, "pic_resolution", ConfigText(default=""))
	pune(config.usage, "sleep_timer", ConfigText(default="0"))
	pune(config.usage, "sleepTimer", ConfigInteger(default=0, limits=(0, 86400)))
	pune(config.usage, "sleepTimerAction", ConfigText(default="deepstandby"))
	pune(config.epg, "histminutes", ConfigInteger(default=0, limits=(0, 999)))
	pune(config.misc, "epgcachepath", ConfigText(default="/etc/enigma2/"))
	# Ore pentru valoarea initiala a exportului EPG; nucleul nostru nu pastreaza istoric suplimentar.
	pune(config.misc, "epgcache_outdated_timespan", ConfigInteger(default=0, limits=(0, 168)))
	pune(config.misc, "prev_wakeup_time", ConfigInteger(default=0, limits=(0, 2147483647)))
	pune(config.misc, "prev_wakeup_time_type", ConfigInteger(default=0, limits=(0, 9)))
	pune(config.misc, "lastrotorposition", ConfigInteger(default=9999, limits=(0, 9999)))
	for i in (1, 2, 3, 4):
		pune(config.autolanguage, "audio_autoselect%d" % i, ConfigText(default=""))
	for nume in ("check", "showinfobar", "showInfoBar"):
		pune(config.timeshift, nume, ConfigYesNo(default=True))
	for nume in ("skipReturnToLive", "stopWhileRecording", "stopwhilerecording"):
		pune(config.timeshift, nume, ConfigYesNo(default=False))
	pune(config.timeshift, "favoriteSaveAction", ConfigText(default="askuser"))
	pune(config.timeshift, "startDelay", ConfigInteger(default=0, limits=(0, 9999)))
	pune(config.timeshift, "startdelay", ConfigText(default="0"))
	pune(config.recording, "zap_margin_after", ConfigInteger(default=0, limits=(0, 999)))
	pune(config.recording, "zap_margin_before", ConfigInteger(default=0, limits=(0, 999)))
	pune(config.subtitles, "show", ConfigYesNo(default=True))


class NivelMereuExpert(ConfigSelection):
	"""config.usage.setup_level din 0.7.5 (LVL, Eduard 14.11.2026): toate setarile se vad mereu, fara Simplu /
	Intermediar / Expert. Valoarea ramane "expert" orice i s-ar da: din /etc/enigma2/settings ramas din 0.7.4
	(simple, intermediate), dintr-o copie de setari pusa la loc fara repornire sau dintr-un plugin. Alegerile raman
	toate trei, ca .index sa fie 2: filtrele de nivel (Setup, Menu, ChannelSelection, cautarea setarilor, paginile
	web) si pluginurile din feed care compara .index sau .value lucreaza mai departe si nu mai ascund nimic.
	Valoarea egala cu cea implicita nu se mai scrie in settings, deci randul vechi dispare la prima salvare."""

	def setValue(self, value):
		ConfigSelection.setValue(self, "expert")

	value = property(ConfigSelection.getValue, setValue)


def InitUsageConfig():
	global config
	config.usage.showdish = ConfigYesNo(default = True)
	# HDSatelit: desenul rotirii antenei (ecranele motorului si pagina web /motor) vazut din spatele antenei: estul in
	# stanga, vestul in dreapta, sudul in varful curbei (Silviu, forum 683, 14.11.2026); Nu = vestul in stanga.
	# Da din fabrica de la 0.7.7 (dorinelu, forum 795 #2676, si Silviu; hotararea coordonatorului 16.11.2026 03:20): cine
	# a ales Da il pastreaza; Nu ales de mana nu are rand in settings (era implicitul), deci trece si el pe Da
	config.usage.hds_motor_din_spate = ConfigYesNo(default = True)
	# HDSatelit 0.7.7: capetele desenului rotirii la limitele practice ale antenei (dorinelu, forum 795 #2676): elevatia minima
	# in grade (Components/HdsMotorStare.elevatieDesen); 0 = orizontul, ca pana acum; numai desenul, nu rotirea
	config.usage.hds_motor_elevatie_min = ConfigSelection(default = "0", choices = [(str(x), u"%d°" % x) for x in range(31)])
	# HDSatelit: tasta albastra deschide lista buchetelor (Favorite primul), nu numai Favorite
	config.usage.multibouquet = ConfigYesNo(default = True)
	# OE-Alliance: semnele numerotate (randurile „-” puse de Fast Scan in locul numerelor nefolosite ale operatorului) nu se vad
	# in lista de canale, dar se numara (lib/service/listboxservice.cpp); se vad numai la mutare. Fara rand in meniu: nimic de ales,
	# setarea e aici pentru pluginurile care o citesc.
	config.usage.hide_number_markers = ConfigYesNo(default = True)
	config.usage.multiepg_ask_bouquet = ConfigYesNo(default = False)

	config.usage.quickzap_bouquet_change = ConfigYesNo(default = False)
	config.usage.e1like_radio_mode = ConfigYesNo(default = False)
	# Sagetile deschid lista modului curent. Valorile salvate isi pastreaza sensul anterior.
	config.usage.hds_sageata_sus = ConfigSelection(default = "current", choices = [
		("current", N_("Lista modului curent (TV sau radio)")),
		("radio", N_("Sus lista radio, jos lista TV")), ("tv_radio", N_("Sus lista TV, jos lista radio")),
		("tv", N_("Ambele deschid lista TV")), ("radio_radio", N_("Ambele deschid lista radio")),
		("zap", N_("Schimbă canalul (sus: următorul)")),
		("zap_invers", N_("Schimbă canalul (sus: anteriorul)"))])
	# HDSatelit CUR6 (tamiciav7, LinuxSat 164122 #971593): lista deschisa cu SUS/JOS (Screens/InfoBarGenerics.py,
	# _hdsSageata; Components/HdsSageti.cursor_pe_canal) are cursorul pe canalul care merge. Nu din fabrica: un rand mai
	# sus sau mai jos, ca pana acum. data/setup.xml (usage), in web /setari?id=usage
	config.usage.hds_sageata_cursor = ConfigYesNo(default = False)
	config.usage.hds_ok_privire = ConfigSelection(default = "bara", choices = [
		("bara", N_("Arată bara de informații")), ("lista", N_("Deschide lista de canale"))])
	from Components.HdsTasteRapide import initConfigProfil
	initConfigProfil(config)
	config.usage.hds_stanga_dreapta_privire = ConfigSelection(default = "actual", choices = [
		("actual", N_("Comportamentul obișnuit")),
		("volum", N_("Volumul (stânga mai încet, dreapta mai tare)"))])
	# Navigarea circulara a listei; dalele isi pastreaza navigarea.
	config.usage.hds_meniu_circular = ConfigYesNo(default=False)
	# HDSatelit: cum se misca meniurile, listele de alegere si ecranele de setari la marginea ecranului (Components/Renderer/
	# Listbox.py, margineDerulare -> eListbox.setScrollMargin): rand cu rand, cu doua randuri vazute sub cursor (implicit),
	# sau pagina cu pagina, ca inainte; lista de canale si ghidul raman pe pagini. Se aplica meniurilor deschise dupa schimbare
	config.usage.hds_derulare_liste = ConfigSelection(default = "rand", choices = [
		("rand", N_("Rând cu rând")), ("pagina", N_("Pagină cu pagină"))])
	# HDSatelit: semnele din dreapta randului in lista de canale (lib/service/listboxservice.cpp, serviceMarks; aplicate in
	# Components/ServiceList.py, hdsSemne): $ la canalele codate si sursa canalului (satelit, cablu, terestru)
	config.usage.hds_semne_lista = ConfigSelection(default = "ambele", choices = [
		("ambele", N_("„$” la canalele codate și sursa")), ("codat", N_("Numai „$” la canalele codate")),
		("sursa", N_("Numai sursa (satelit, cablu, terestru)")), ("niciunul", N_("Fără semne"))])
	# 0.7.7 (BQT, Ozgur e-mailul 6509): setarea schimbata (pe televizor, la EXIT fara salvare inapoi, sau din web) se vede pe
	# loc in lista deschisa o data (Components/HdsListaSetari.reface -> ServiceList.hdsSemne), nu abia la urmatoarea deschidere
	def _hdsSemneSchimbate(configElement):
		try:
			from Components.HdsListaSetari import reface
			reface()
		except Exception as e:
			print("[UsageConfig] semnele listei: %s" % e)
	config.usage.hds_semne_lista.addNotifier(_hdsSemneSchimbate, initial_call=False)
	alegeri_infobar, alegeri_disc = _alegeriCuNumere()
	config.usage.infobar_timeout = ConfigSelection(default = "8", choices = alegeri_infobar)
	config.usage.show_infobar_on_zap = ConfigYesNo(default = True)
	config.usage.show_infobar_on_skip = ConfigYesNo(default = True)
	config.usage.show_infobar_on_event_change = ConfigYesNo(default = True)
	# randul ECM din bara canalului (HdsSignal EcmLine: CAID, timpul ECM, protocolul, cat modulul de acces decripteaza
	# canalul) si debitul DVB pe pagina intai a celei de-a doua bare (HdsSignal Debit); le citesc convertoarele temei prin
	# HdsCommon.optiune_usage, la fiecare tic; in web: /setari?id=usage
	config.usage.hds_bara_ecm = ConfigYesNo(default = False)
	# hop-urile si eticheta cititorului pe pagina modulului si in randul ECM (Components/HdsEcm.sursa: niciodata adrese, nimic
	# cat ruleaza asistenta sau o captura pentru un raport); oprita din fabrica
	config.usage.hds_ecm_hopuri_cititor = ConfigYesNo(default = False)
	config.usage.hds_debit_bara = ConfigSelection(default = "da", choices = [
		("nu", _("Nu")), ("da", _("Da")), ("statistici", _("Da, cu minim, maxim și medie"))])
	config.usage.hide_zap_errors = ConfigYesNo(default = False)
	config.usage.hdd_standby = ConfigSelection(default = "600", choices = alegeri_disc)
	# limba aleasa se activeaza dupa InitUsageConfig (SetupDevices), deci textele compuse de mai sus ies in engleza
	from Components.Language import language
	language.addCallback(_traduAlegerileCuNumere)
	config.usage.output_12V = ConfigSelection(default = "do not change", choices = [
		("do not change", _("do not change")), ("off", _("off")), ("on", _("on")) ])

	# HDSatelit 0.7.5 (cererea unui tester, forum 795, probat pe Vu+ Solo4K): 0 cu PiP pornit schimba din fabrica imaginile
	# intre ele (ecranul mare si PiP); "standard" (canalul de dinainte) ramane de ales in Setari, la Comportamentul tastei 0
	config.usage.pip_zero_button = ConfigSelection(default = "swap", choices = [
		("standard", _("standard")), ("swap", _("swap PiP and main picture")),
		("swapstop", _("move PiP to main picture")), ("stop", _("stop PiP")) ])

	config.usage.default_path = ConfigText(default = resolveFilename(SCOPE_HDD))
	config.usage.timer_path = ConfigText(default = "<default>")
	config.usage.instantrec_path = ConfigText(default = "<default>")
	config.usage.timeshift_path = ConfigText(default = "/media/hdd/")
	config.usage.allowed_timeshift_paths = ConfigLocations(default = ["/media/hdd/"])

	config.usage.on_movie_start = ConfigSelection(default = "ask", choices = [
		("ask", _("Ask user")), ("resume", _("Resume from last position")), ("beginning", _("Start from the beginning")) ])
	config.usage.on_movie_stop = ConfigSelection(default = "movielist", choices = [
		("ask", _("Ask user")), ("movielist", _("Return to movie list")), ("quit", _("Return to previous service")) ])
	config.usage.on_movie_eof = ConfigSelection(default = "ask", choices = [
		("ask", _("Ask user")), ("movielist", _("Return to movie list")), ("quit", _("Return to previous service")), ("pause", _("Pause movie at end")) ])

	# 0.7.5 (LVL): toate setarile la vedere, mereu (vezi NivelMereuExpert); randul "Setup Mode" nu mai e in setup.xml
	config.usage.setup_level = NivelMereuExpert(default = "expert", choices = [
		("simple", _("Simple")),
		("intermediate", _("Intermediate")),
		("expert", _("Expert")) ])

	config.usage.on_long_powerpress = ConfigSelection(default = "show_menu", choices = [
		("show_menu", _("show shutdown menu")),
		("shutdown", _("immediate shutdown")),
		("standby", _("Standby")) ] )
	
	config.usage.on_short_powerpress = ConfigSelection(default = "standby", choices = [
		("show_menu", _("show shutdown menu")),
		("shutdown", _("immediate shutdown")),
		("standby", _("Standby")) ] )


	config.usage.alternatives_priority = ConfigSelection(default = "0", choices = [
		("0", "DVB-S/-C/-T"),
		("1", "DVB-S/-T/-C"),
		("2", "DVB-C/-S/-T"),
		("3", "DVB-C/-T/-S"),
		("4", "DVB-T/-C/-S"),
		("5", "DVB-T/-S/-C") ])

	config.usage.show_event_progress_in_servicelist = ConfigYesNo(default = False)
	config.usage.hds_progres_lista_pozitie = ConfigSelection(default = "stanga", choices = [
		("stanga", N_("Stânga (înainte de nume)")), ("dreapta", N_("Dreapta (după nume)"))])
	config.usage.hds_randuri_lista = ConfigSelection(default = "tema", choices = [
		("tema", N_("După temă"))] + [(str(n), str(n)) for n in range(1, 41)])
	# HDSatelit (0.7.5, tamiciav7, LinuxSat 164126): marimea textului in lista de canale, separata de randurile pe pagina.
	# Fiecare pas = 10% din marimea temei (-3 = 70%, +5 = 150%) pentru nume, descriere, numar si bara de progres; cu
	# „Rânduri pe pagină” După temă si randul creste sau scade cu textul, deci si sigla. Components/ServiceList.py (setMode)
	config.usage.hds_marime_text_lista = ConfigSelection(default = "tema", choices = [
		("tema", N_("După temă"))] + [(str(n), "%+d" % n) for n in (-3, -2, -1, 1, 2, 3, 4, 5)])

	def _hdsListaCanaleReface(configElement):
		# lista de canale deschisa o data (ecranul ramane in memorie) se potriveste pe loc, fara repornire
		try:
			from Screens.InfoBar import InfoBar
			ecran = InfoBar.instance and InfoBar.instance.servicelist
			lista = getattr(ecran, "servicelist", None)
			if lista is not None and lista.instance is not None:
				lista.setMode(lista.mode)
		except Exception as e:
			print("[UsageConfig] lista de canale: %s" % e)
	# HDSatelit (0.7.5, tamiciav7, LinuxSat; Eduard 13.11 22:27: optiune, nu din fabrica): aspectul listei de canale. „Obișnuit”
	# = ecranele de pana acum ale temei; „Lista mare” = pe tot ecranul, lista pe ~2/3 in stanga, imaginea canalului si ghidul in
	# dreapta, tastele colorate in dreapta jos (ecranele HdsListaCanaleMare* din tema). Se vede pe loc, fara repornire
	# (Components/HdsAspectLista.py); marimea textului si randurile pe pagina se aplica si peste lista mare
	config.usage.hds_aspect_lista = ConfigSelection(default = "obisnuit", choices = [
		("obisnuit", N_("Obișnuit")), ("mare", N_("Lista mare")),
		("doua_randuri", N_("Două rânduri")), ("mare_doua_randuri", N_("Lista mare, două rânduri"))])
	from Components.HdsAspectLista import initCompatLista
	initCompatLista(config.usage)
	config.usage.hds_marime_text_lista.addNotifier(_hdsListaCanaleReface, initial_call=False)
	config.usage.hds_randuri_lista.addNotifier(_hdsListaCanaleReface, initial_call=False)
	config.usage.hds_aspect_lista.addNotifier(_hdsListaCanaleReface, initial_call=False)

	def _hdsAspectLista(configElement):
		try:
			from Components.HdsAspectLista import laSchimbare
			laSchimbare(configElement)
		except Exception as e:
			print("[UsageConfig] aspectul listei de canale: %s" % e)
	config.usage.hds_aspect_lista.addNotifier(_hdsAspectLista, initial_call=False)
	# HDSatelit: in lista 'Sateliți' (Screens/ChannelSelection.py, hdsUmpleSateliti) si randurile 'Furnizori' si 'Nou' ale
	# fiecarui satelit, sub antetul lui; oprita din fabrica: un singur rand pe satelit (furnizorii pe tasta galbena)
	config.usage.hds_lista_furnizori_nou = ConfigYesNo(default = False)
	# HDSatelit OKP6 (yazoo, forum 1936): OK in lista de canale previzualizeaza canalul (Screens/ChannelSelection.py,
	# hdsPrevizualizeaza); Nu din fabrica = OK porneste canalul si inchide lista, ca pana acum. In web
	# /setari?id=hds_lista_canale (data/setup.xml)
	config.usage.hds_ok_previzualizare = ConfigYesNo(default = False)
	# HDSatelit (0.7.4): 'Actualizează lista de canale la privit' (data/setup.xml, sectiunea usage; in web /setari?id=usage).
	# Pornita din fabrica, ca pana acum: la canalul privit, lib/dvb/pmt.cpp (SDTScanEvent) pune in lista ce gaseste
	# scanarea transponderului (canalele noi, numele la zi, deci si canalele sterse de om). Oprita: lista ramane cum a
	# lasat-o omul. C++ o citeste la fiecare sfarsit de scanare (getResolvedKey: "True" / "False"), deci se aplica pe loc
	config.usage.hds_actualizare_lista = ConfigYesNo(default = True)
	# HDSatelit (0.7.5, sosozah, forum 588 #2055): buchetul "Last Scanned" cu canalele gasite de ultima scanare (lib/dvb/
	# scan.cpp, hdsBuchetUltimaScanare), rescris la fiecare scanare, ca in OE-Alliance; pornita din fabrica. Oprita: nu se
	# mai scrie si iese din lista buchetelor. C++ o citeste la fiecare sfarsit de scanare ("True" / "False")
	config.usage.hds_ultima_scanare = ConfigYesNo(default = True)
	# HDSatelit: siglele canalelor (Components/Renderer/Picon.py): oprita, nicio sigla nu se arata (caseta ramane goala,
	# transparenta), iar pe bare textele raman la locul lor (Components/HdsPiconBare.py); se schimba pe loc
	config.usage.hds_piconuri = ConfigYesNo(default = True)
	# fara nicio sigla: in Setari se vede "Nu ai inca sigle" si OK deschide instalarea (Components/HdsPiconInstalare.py)
	try:
		from Components.HdsPiconInstalare import leaga_setarea
		leaga_setarea(config.usage.hds_piconuri)
	except Exception as e:
		print("[UsageConfig] instalarea siglelor: %s" % e)
	# HDSatelit (0.7.5): functiile televiziunii prin internet, fiecare cu Da/Nu (setup.xml hds_iptv_functii, pereche web /setari).
	# Oprita, functia nu mai face nimic in fundal: nicio cerere la furnizor, nicio scriere.
	# ghidul TV cerut singur la ~90 s dupa pornirea interfetei (Components/HdsIptvLucru._zilnic)
	config.usage.hds_iptv_ghid_pornire = ConfigYesNo(default = True)
	config.usage.hds_iptv_fereastra = ConfigYesNo(default = True)
	# EXL6 (22.11.2026): EXIT tinut apasat inchide fereastra pasilor pana la urmatoarea pornire a unui canal
	# (Components/HdsIptvRedare.Legatura._tastaExit, contextul HdsIptvFereastraActions din keymap.xml); Nu din fabrica,
	# deci EXIT ramane cum era
	config.usage.hds_iptv_fereastra_exit = ConfigYesNo(default = False)
	# semnul canalelor care n-au pornit ultima data, cu motivul (Components/HdsIptvSurse.noteazaNefunctional)
	config.usage.hds_iptv_semn = ConfigYesNo(default = True)
	# timpul mediu de pornire la ultimele 5 porniri (Components/HdsIptvSurse.notaPornire), tinut in memorie si scris rar
	config.usage.hds_iptv_timp_pornire = ConfigYesNo(default = True)
	# cautarea canalelor 4K reale, in fundal, o data pe saptamana (Components/HdsIptv4K.py). Nu din fabrica (coordonatorul,
	# 14.11.2026): o cautare intreaga deschide pe contul omului mii de canale, unul dupa altul, ore in sir (2.654 de canale, ~5 h
	# pe receptorul de probe), iar unii furnizori blocheaza contul pentru asa ceva. Omul o porneste din meniu sau din web cand vrea.
	config.usage.hds_iptv_4k = ConfigYesNo(default = False)
	# „Filme și seriale” (Screens/HdsFilmeSeriale.py, Components/HdsVod*.py; VOD 0.7.5): posterele aduse din internet,
	# pozitia tinuta minte pe film (scrisa pe flash cel mult o data la 5 minute) si „Adăugate recent” (lista intreaga, o data pe zi)
	config.usage.hds_vod_poze = ConfigYesNo(default = True)
	config.usage.hds_vod_continua = ConfigYesNo(default = True)
	config.usage.hds_vod_recente = ConfigYesNo(default = True)
	# categoriile tarii (dupa limba interfetei: germana -> DE, AT, CH) primele in „Filme și seriale”
	config.usage.hds_vod_tara = ConfigYesNo(default = True)
	# HDSatelit (0.7.5, IPI): canalul de internet care s-a oprit porneste singur din nou (Components/HdsIptvReconectare.py);
	# siglele canalelor de internet aduse din lista furnizorului (Components/HdsIptvSigle.py); starea contului Xtream (expira,
	# conexiunile) citita numai cand omul deschide IPTV pe televizor sau in web (HdsIptvClient.stareContXtream)
	config.usage.hds_iptv_reconectare = ConfigYesNo(default = True)
	config.usage.hds_iptv_recuperare_rapida = ConfigYesNo(default = False)
	config.usage.hds_iptv_sigle = ConfigYesNo(default = True)
	config.usage.hds_iptv_cont = ConfigYesNo(default = True)
	# emisiunile trecute (arhiva furnizorului Xtream), din MENU pe canal (Screens/HdsIptvArhiva.py); lista ceruta numai la deschidere
	config.usage.hds_iptv_arhiva = ConfigYesNo(default = True)
	# potrivirea larga a ghidului dupa numele canalului, pentru canalele fara tvg-id (Components/HdsIptvEpg._numeLarg)
	config.usage.hds_iptv_epg_larg = ConfigYesNo(default = True)
	# decalajul orelor din ghidul TV de internet (Components/HdsIptvEpg.decalaj), pentru furnizorii cu ora gresita; 0 = fara
	config.usage.hds_iptv_decalaj_epg = ConfigSelection(default = "0", choices = [("0", _("Fără decalaj"))] +
		[(str(h), ("+%g h" % h if h > 0 else "%g h" % h).replace(".", ",")) for h in
		(-12, -11, -10, -9, -8, -7, -6, -5, -4, -3, -2, -1.5, -1, -0.5, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)])

	config.usage.blinking_display_clock_during_recording = ConfigYesNo(default = False)

	config.usage.show_message_when_recording_starts = ConfigYesNo(default = True)

	config.usage.load_length_of_movies_in_moviellist = ConfigYesNo(default = True)
	
	def TunerTypePriorityOrderChanged(configElement):
		setTunerTypePriorityOrder(int(configElement.value))
	config.usage.alternatives_priority.addNotifier(TunerTypePriorityOrderChanged, immediate_feedback=False)

	def setHDDStandby(configElement):
		for hdd in harddiskmanager.HDDList():
			hdd[1].setIdleTime(int(configElement.value))
	config.usage.hdd_standby.addNotifier(setHDDStandby, immediate_feedback=False)

	def set12VOutput(configElement):
		if configElement.value == "on":
			Misc_Options.getInstance().set_12V_output(1)
		elif configElement.value == "off":
			Misc_Options.getInstance().set_12V_output(0)
	config.usage.output_12V.addNotifier(set12VOutput, immediate_feedback=False)

	SystemInfo["12V_Output"] = Misc_Options.getInstance().detected_12V_output()

	config.usage.keymap = ConfigText(default = eEnv.resolve("${datadir}/enigma2/keymap.xml"))
	config.usage.acces_streamrelay_url = ConfigText(default = "http://127.0.0.1:17999")
	config.usage.acces_streamrelay_port = ConfigNumber(default = 17999)
	config.usage.acces_streamrelay_delay = ConfigNumber(default = 50)
	config.misc.acces_streamrelay_url = ConfigText(default = "http://127.0.0.1:17999")
	config.misc.acces_streamrelay_port = ConfigNumber(default = 17999)
	config.misc.acces_streamrelay_delay = ConfigNumber(default = 50)
	# 0.7.0 (Stream Relay, Components/HdsStreamRelay.py): adresa releului se scrie si din web (/setari?id=hds_stream_relay;
	# setari_web.py o primeste numai cu web_text_max)
	config.misc.acces_streamrelay_url.web_text_max = 64
	# 0.7.0: fluxurile canalelor (serverul 8001, Hds/DabT2/server8001.py) si pentru
	# alte aparate din reteaua de acasa (un releu Stream Relay de pe alt receptor); oprita: numai 127.0.0.1, ca pana acum.
	# Pornita: numai adresele private (192.168.x.x, 10.x.x.x, 172.16-31.x.x, 169.254.x.x), niciodata din internet.
	# PORNITA din fabrica, fiindca nimic nu opreste programele din casa (nici streamul pe 8001);
	# listele m3u ale aplicatiilor de telefon (aplicatii_web.PORT_FLUX) trimit chiar la 8001.
	config.misc.hds_fluxuri_retea_acasa = ConfigYesNo(default=True)
	# 0.7.4 (OE-Alliance): numele standard pe care il citesc pluginurile scrise pentru celelalte imagini (PlutoTV isi alege tastele
	# dupa el). Da = in liste STANGA/DREAPTA dau pagina sus/jos, adica felul listelor noastre; fara ecran, nu schimba nimic la noi.
	config.misc.actionLeftRightToPageUpPageDown = ConfigYesNo(default=True)
	# 0.7.4 (cererea de pe forum, subiectul 1025): trecerea singura prin Stream Relay a canalelor cu ICAM (Sky
	# Deutschland, 098C / 098D), fara lista facuta de mana (Components/HdsStreamRelay.py, TRECEREA SINGURA). OPRITA din
	# fabrica de la 12.11.2026: receptorul descifreaza singur canalele ICAM (SoftCSA), pe televizor si in fluxul catre
	# browser, iar releul le oprea fluxul in browser. Cine o vrea o porneste din setarile Stream Relay. Sistemele: un text
	# (expert, si din web); gol sau gresit = cele din fabrica (le foloseste si HdsSoftCsa, la recunoasterea canalelor ICAM).
	# La schimbare, legatura la zap se pune sau se scoate pe loc.
	config.misc.hds_streamrelay_icam = ConfigYesNo(default=False)
	config.misc.hds_streamrelay_icam_caid = ConfigText(default="098C,098D", fixed_size=False)
	config.misc.hds_streamrelay_icam_caid.web_text_max = 64

	def _trecereaSingura(_el):
		try:
			from Components import HdsStreamRelay
			HdsStreamRelay.setareSchimbata()
		except Exception as e:
			print("[UsageConfig] trecerea singura Stream Relay: %s" % e)
	config.misc.hds_streamrelay_icam.addNotifier(_trecereaSingura, initial_call=False)
	config.misc.hds_streamrelay_icam_caid.addNotifier(_trecereaSingura, initial_call=False, immediate_feedback=False)
	# 0.7.1: in ecranul Stream Relay (Screens/Setup.py) si in pagina lui web (setari_web.py), deasupra ajutorului fiecarui
	# rand, starea de acum: cate canale are lista, de unde se adauga, daca releul raspunde si de ce nu
	# (HdsStreamRelay.liniiStare; modulul se incarca abia la deschiderea ecranului)
	for _el in (config.misc.acces_streamrelay_url, config.misc.acces_streamrelay_port, config.misc.acces_streamrelay_delay,
			config.misc.hds_fluxuri_retea_acasa, config.misc.hds_streamrelay_icam, config.misc.hds_streamrelay_icam_caid):
		_el.hdsStare = _stareStreamRelay
	_mutaSetarileVechi()

	config.seek = ConfigSubsection()
	config.seek.selfdefined_13 = ConfigNumber(default=15)
	config.seek.selfdefined_46 = ConfigNumber(default=60)
	config.seek.selfdefined_79 = ConfigNumber(default=300)

	config.seek.speeds_forward = ConfigSet(default=[2, 4, 8, 16, 32, 64, 128], choices=[2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128])
	config.seek.speeds_backward = ConfigSet(default=[2, 4, 8, 16, 32, 64, 128], choices=[1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128])
	config.seek.speeds_slowmotion = ConfigSet(default=[2, 4, 8], choices=[2, 4, 6, 8, 12, 16, 25])

	config.seek.enter_forward = ConfigSelection(default = "2", choices = ["2", "4", "6", "8", "12", "16", "24", "32", "48", "64", "96", "128"])
	config.seek.enter_backward = ConfigSelection(default = "1", choices = ["1", "2", "4", "6", "8", "12", "16", "24", "32", "48", "64", "96", "128"])

	config.seek.on_pause = ConfigSelection(default = "play", choices = [
		("play", _("Play")),
		("step", _("Singlestep (GOP)")),
		("last", _("Last speed")) ])

	config.usage.timerlist_finished_timer_position = ConfigSelection(default = "beginning", choices = [("beginning", _("at beginning")), ("end", _("at end"))])

	def updateEnterForward(configElement):
		if not configElement.value:
			configElement.value = [2]
		updateChoices(config.seek.enter_forward, configElement.value)

	config.seek.speeds_forward.addNotifier(updateEnterForward, immediate_feedback = False)

	def updateEnterBackward(configElement):
		if not configElement.value:
			configElement.value = [2]
		updateChoices(config.seek.enter_backward, configElement.value)

	config.seek.speeds_backward.addNotifier(updateEnterBackward, immediate_feedback = False)

	# HDSatelit: accelerarea 2D pe placa video (TDE HiSilicon, lib/gdi/accel.cpp), implicit pornita; setarea pune sau
	# scoate fisierul de oprire /etc/enigma2/hds-fara-accel, citit de C++ la urmatoarea pornire a interfetei; pe un
	# receptor fara TDE randul nu se arata (Components/HdsAccel2D.py)
	try:
		from Components import HdsAccel2D
		HdsAccel2D.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsAccel2D: %s" % eroare)

	# HDSatelit (ION1): Dreambox DM7080/DM820/DM900/DM920/DM520, memoria ecranului si accelerarea prin ION, oprita din
	# fabrica; setarea pune sau scoate /etc/enigma2/hds-dreambox-ion, citit de lib/gdi/fb.cpp la urmatoarea pornire a
	# interfetei; pe alte receptoare randul nu se arata (Components/HdsDreamboxIon.py)
	try:
		from Components import HdsDreamboxIon
		HdsDreamboxIon.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsDreamboxIon: %s" % eroare)

	# HDSatelit: IPv6, oprit din fabrica; setarea pune sau scoate semnul /etc/hds-ipv6-pornit si aplica pe loc
	# (disable_ipv6, clientul odhcp6c); aici starea semnului se aplica o data, la pornirea interfetei
	# (Components/HdsIpv6.py)
	try:
		from Components import HdsIpv6
		HdsIpv6.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsIpv6: %s" % eroare)

	# HDSatelit 0.7.5/0.7.6: partajarea in retea (Samba), oprita din fabrica; pornita, se instaleaza din feed daca lipseste
	# si se aplica singura; la pornire alegerea salvata se aduce la zi (Components/HdsSamba.py)
	try:
		from Components import HdsSamba
		HdsSamba.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsSamba: %s" % eroare)

	# HDSatelit: culegerea pistelor la vizionare (oprita / numai canalul privit /
	# tot transponderul, netestat), randul din setup.xml si pagina web /cautare (Components/HdsPisteCanale.py)
	try:
		from Components import HdsPisteCanale
		HdsPisteCanale.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsPisteCanale: %s" % eroare)

	# HDSatelit: "Ia baza de canale de pe stb.hdsatelit.com" (oprita din fabrica), randul din setup.xml langa citirea
	# pistelor; descarcarea zilnica si unirea in Components/HdsBazaPornire.py
	try:
		from Components import HdsBazaPornire
		HdsBazaPornire.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsBazaPornire: %s" % eroare)

	# HDSatelit: cat de des se verifica internetul (30 s, 1, 2 sau 5 minute; din fabrica 1 minut), setup.xml
	# hds_internet; verificarea si pictograma retelei in Components/HdsStareRetea.py
	try:
		from Components import HdsStareRetea
		HdsStareRetea.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsStareRetea: %s" % eroare)

	# HDSatelit: trecerea singura pe alta retea cand se pierde internetul (pornita din fabrica) si ordinea retelelor,
	# setup.xml hds_retea_comutare (Components/HdsComutareRetea.py)
	try:
		from Components import HdsComutareRetea
		HdsComutareRetea.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsComutareRetea: %s" % eroare)

	# HDSatelit: subtitrarile filmelor din fisierele de langa film (codarea implicita, si pentru pistele din MKV care nu
	# sunt UTF-8; s t cu sedila -> ș ț; fisierul inaintea pistei din film; subdosarele Subs), setup.xml hds_subtitrari_filme
	# (Components/HdsSubtitrariFilm.py)
	try:
		from Components import HdsSubtitrariFilm
		HdsSubtitrariFilm.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsSubtitrariFilm: %s" % eroare)

	# HDSatelit: mesajul de pe mijlocul ecranului cat canalul ramane negru (criptat, fara semnal, mutat...), setup.xml
	# hds_ecran_negru (Components/HdsEcranNegru.py); oprit = ferestrele de eroare de pana acum, cu textele noi
	try:
		from Components import HdsEcranNegru
		HdsEcranNegru.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsEcranNegru: %s" % eroare)

	# HDSatelit: protectia ecranului (Screens/ScreenSaver.py, numele OE-Alliance config.usage.screenSaverStartTimer,
	# screenSaverMoveTimer, screenSaverMode). config.hds_radio (cu „La canalele numai cu sunet”) il face tot ecranul radio,
	# la pornirea barei, cu limba activa (ecranul setarilor radio arata alegerile asa cum au fost facute)
	try:
		from Components import HdsRadioSetari
		HdsRadioSetari.initProtectie()
	except Exception as eroare:
		print("[UsageConfig] HdsRadioSetari: %s" % eroare)

	# HDSatelit 0.7.7: tunerul de rezerva din retea (in OE-Alliance "fallback tuner": config.usage.remote_fallback_enabled si
	# remote_fallback), un rand cu receptoarele gasite in casa, setup.xml hds_tuner_rezerva; legatura la zap si anuntul
	# serverului de flux (_e2stream._tcp) in Components/HdsTunerRezerva.py
	try:
		from Components import HdsTunerRezerva
		HdsTunerRezerva.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsTunerRezerva: %s" % eroare)
	from Components import HdsTunerAspect
	HdsTunerAspect.initConfig()


def updateChoices(sel, choices):
	if choices:
		defval = None
		val = int(sel.value)
		if not val in choices:
			tmp = choices[:]
			tmp.reverse()
			for x in tmp:
				if x < val:
					defval = str(x)
					break
		sel.setChoices(list(map(str, choices)), defval)

def preferredPath(path):
	if config.usage.setup_level.index < 2 or path == "<default>":
		return None  # config.usage.default_path.value, but delay lookup until usage
	elif path == "<current>":
		return config.movielist.last_videodir.value
	elif path == "<timer>":
		return config.movielist.last_timer_videodir.value
	else:
		return path

def preferredTimerPath():
	return preferredPath(config.usage.timer_path.value)

def preferredInstantRecordPath():
	return preferredPath(config.usage.instantrec_path.value)

def defaultMoviePath():
	return config.usage.default_path.value

def defaultStorageDevice():
	"""UUID-ul discului tinut minte pentru /media/hdd; marcajul cerut de plugin cand nu este ales."""
	return getattr(harddiskmanager, "hdd_uuid", "") or "<undefined>"


# la sfarsitul lui InitUsageConfig ramane numai ce a pus imaginea; setarile cerute de pluginuri se pun dupa
_InitUsageConfigImagine = InitUsageConfig


def InitUsageConfig():
	_InitUsageConfigImagine()
	try:
		_setariCerutePluginuri()
	except Exception as e:
		print("[UsageConfig] setarile cerute de pluginuri:", e)
