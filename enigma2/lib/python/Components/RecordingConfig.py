# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .config import ConfigNumber, ConfigYesNo, ConfigSubsection, ConfigSelection, ConfigInteger, config

def InitRecordingConfig():
	config.recording = ConfigSubsection();
	# actually this is "recordings always have priority". "Yes" does mean: don't ask. The RecordTimer will ask when value is 0.
	config.recording.asktozap = ConfigYesNo(default=True)
	config.recording.margin_before = ConfigNumber(default=0)
	config.recording.margin_after = ConfigNumber(default=0)
	config.recording.debug = ConfigYesNo(default = False)
	config.recording.ascii_filenames = ConfigYesNo(default = False)
	config.recording.filename_composition = ConfigSelection(default = "standard", choices = [
		("standard", _("standard")),
		("short", _("Short filenames")),
		("long", _("Long filenames")) ] )
	# HDSatelit: inregistrarile "Decodează mai târziu" (Components/HdsDecodare.py): alegerea din oficiu a unui temporizator
	# nou, oprita din fabrica, si portul local (numai 127.0.0.1) la care programul de decodare cere cheile modulului de
	# acces; 0 = nefolosit. Amandoua se arata numai cu programul de decodare pe receptor (SystemInfo["HdsDecodare"]).
	from . import HdsDecodare
	config.recording.hds_decodare = ConfigSelection(default=HdsDecodare.ACUM, choices=[
		(HdsDecodare.ACUM, _(HdsDecodare.TXT_ACUM)),
		(HdsDecodare.MAI_TARZIU, _(HdsDecodare.TXT_MAI_TARZIU))])
	config.recording.hds_decodare_port = ConfigInteger(default=0, limits=(0, 65535))
