# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.Harddisk import harddiskmanager
from .config import ConfigSubsection, ConfigYesNo, config, ConfigSelection, ConfigText, ConfigNumber, ConfigSet, ConfigLocations
from Tools.Directories import resolveFilename, SCOPE_HDD
from enigma import Misc_Options, setTunerTypePriorityOrder, eEnv;
from .SystemInfo import SystemInfo
import os

config.usage = ConfigSubsection()
config.usage.keymap = ConfigText(default = eEnv.resolve("${datadir}/enigma2/keymap.xml"))
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


def InitUsageConfig():
	global config
	config.usage.showdish = ConfigYesNo(default = True)
	# HDSatelit: tasta albastra deschide lista buchetelor (Favorite primul), nu numai Favorite
	config.usage.multibouquet = ConfigYesNo(default = True)
	config.usage.multiepg_ask_bouquet = ConfigYesNo(default = False)

	config.usage.quickzap_bouquet_change = ConfigYesNo(default = False)
	config.usage.e1like_radio_mode = ConfigYesNo(default = False)
	# HDSatelit: sagetile SUS si JOS la privit (Components/HdsSageti.py: bara TV si ecranul radio): lista de canale radio
	# sau TV, ori canalul urmator si anterior. Numele vechi al setarii ramane (0.1.6 avea numai SUS: "radio", implicit,
	# si "tv", cand si SUS deschidea lista TV, ca JOS), deci o valoare salvata isi pastreaza intelesul
	config.usage.hds_sageata_sus = ConfigSelection(default = "radio", choices = [
		("radio", N_("Sus lista radio, jos lista TV")), ("tv_radio", N_("Sus lista TV, jos lista radio")),
		("tv", N_("Ambele deschid lista TV")), ("radio_radio", N_("Ambele deschid lista radio")),
		("zap", N_("Schimbă canalul (sus: următorul)"))])
	alegeri_infobar, alegeri_disc = _alegeriCuNumere()
	config.usage.infobar_timeout = ConfigSelection(default = "8", choices = alegeri_infobar)
	config.usage.show_infobar_on_zap = ConfigYesNo(default = True)
	config.usage.show_infobar_on_skip = ConfigYesNo(default = True)
	config.usage.show_infobar_on_event_change = ConfigYesNo(default = True)
	config.usage.hide_zap_errors = ConfigYesNo(default = False)
	config.usage.hdd_standby = ConfigSelection(default = "600", choices = alegeri_disc)
	# limba aleasa se activeaza dupa InitUsageConfig (SetupDevices), deci textele compuse de mai sus ies in engleza
	from Components.Language import language
	language.addCallback(_traduAlegerileCuNumere)
	config.usage.output_12V = ConfigSelection(default = "do not change", choices = [
		("do not change", _("do not change")), ("off", _("off")), ("on", _("on")) ])

	config.usage.pip_zero_button = ConfigSelection(default = "standard", choices = [
		("standard", _("standard")), ("swap", _("swap PiP and main picture")),
		("swapstop", _("move PiP to main picture")), ("stop", _("stop PiP")) ])

	config.usage.default_path = ConfigText(default = resolveFilename(SCOPE_HDD))
	config.usage.timer_path = ConfigText(default = "<default>")
	config.usage.instantrec_path = ConfigText(default = "<default>")
	config.usage.timeshift_path = ConfigText(default = "/media/hdd/")
	config.usage.allowed_timeshift_paths = ConfigLocations(default = ["/media/hdd/"])

	config.usage.on_movie_start = ConfigSelection(default = "ask", choices = [
		("ask", _("Ask user")), ("resume", _("Resume from last position")), ("beginning", _("Start from the beginning")) ])
	config.usage.on_movie_stop = ConfigSelection(default = "ask", choices = [
		("ask", _("Ask user")), ("movielist", _("Return to movie list")), ("quit", _("Return to previous service")) ])
	config.usage.on_movie_eof = ConfigSelection(default = "ask", choices = [
		("ask", _("Ask user")), ("movielist", _("Return to movie list")), ("quit", _("Return to previous service")), ("pause", _("Pause movie at end")) ])

	config.usage.setup_level = ConfigSelection(default = "intermediate", choices = [
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
	# HDSatelit: in lista 'Sateliți' (Screens/ChannelSelection.py, hdsUmpleSateliti) si randurile 'Furnizori' si 'Nou' ale
	# fiecarui satelit, sub antetul lui; oprita din fabrica: un singur rand pe satelit (furnizorii pe tasta galbena)
	config.usage.hds_lista_furnizori_nou = ConfigYesNo(default = False)
	# HDSatelit: siglele canalelor (Components/Renderer/Picon.py): oprita, nicio sigla nu se arata (caseta ramane goala,
	# transparenta), iar pe bare textele raman la locul lor (Components/HdsPiconBare.py); se schimba pe loc
	config.usage.hds_piconuri = ConfigYesNo(default = True)

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

	# HDSatelit: IPv6, oprit din fabrica; setarea pune sau scoate semnul /etc/hds-ipv6-pornit si aplica pe loc
	# (disable_ipv6, clientul odhcp6c); aici starea semnului se aplica o data, la pornirea interfetei
	# (Components/HdsIpv6.py)
	try:
		from Components import HdsIpv6
		HdsIpv6.initConfig()
	except Exception as eroare:
		print("[UsageConfig] HdsIpv6: %s" % eroare)

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

