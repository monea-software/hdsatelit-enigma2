# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Wizard import wizardManager
from Components.config import config, ConfigBoolean, configfile
from Screens.HdsStartWizard import HdsStartWizard

config.misc.firstrun = ConfigBoolean(default = True)
# HDSatelit: config.misc.startwizard (shownimconfig, doservicescan) a fost scos. Il citea
# numai data/startwizard.xml, ghidul vechi ramas orfan dupa trecerea la HdsStartWizard; fisierul acela
# a fost scos in acelasi lot, asa ca reglajele nu mai aveau cine sa le intrebe.
config.misc.languageselected = ConfigBoolean(default = False)

# Asistentul HD Satelit de la prima pornire (Screens/HdsStartWizard.py), in doua pagini:
# configurarea (limba, Romana implicit, si rezolutia), apoi prezentarea imaginii; la final pune
# config.misc.firstrun=False si deschide meniul principal. Evaluat la pornire pe valoarea curenta a lui firstrun.
wizardManager.registerWizard(HdsStartWizard, config.misc.firstrun, priority = 10)


