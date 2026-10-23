# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""
LogManager.py: Manager si vizualizator jurnale Enigma2.

STARE: clasele de ecran (LogManager,
LogManagerViewLog, LogInfo) erau complet goale (doar "pass", nici macar
mostenite din Screen) -- inaccesibile si nefunctionale.
Scrise acum de la zero, cod propriu.
De asemenea, comentariul vechi "config.logmanager e initializat in config.py" era
fals -- config.logmanager nu exista nicaieri; acum il face Components/HdsJurnale.initConfig(), chemat la incarcarea
acestui fisier (si de pagina web /jurnale-sistem).
Si AutoLogManager/LogManagerPoller de mai jos nu sunt apelate de nicaieri -- raman
scrise, gata de folosit cand cineva le adauga in mytest.py, dar nu pornesc
singure la pornirea reala a receptorului inca.
"""
import os
import time

from .Screen import Screen
from .MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Button import Button
from Components.ScrollLabel import ScrollLabel
from Components.config import config
from Components import HdsJurnale

# Logica (lista, citirea, stergerea, setarile config.logmanager) e in Components/HdsJurnale.py, folosita si de pagina
# web /jurnale-sistem (HdsWebControl/jurnale_sistem_web.py).
CALE_JURNALE = HdsJurnale.CALE_JURNALE
MARIME_MAX_AFISATA = HdsJurnale.MARIME_MAX_AFISATA  # un jurnal mai mare se citeste doar pe ultima portiune

# config.logmanager se face la incarcare, ca inainte; HdsJurnale.initConfig verifica in config.content.items
# (ConfigSubsection.__getattr__ arunca KeyError, nu AttributeError, pentru o cheie lipsa).
HdsJurnale.initConfig()


class AutoLogManager:
    """Porneste pollerul de log-uri automat."""
    def __init__(self):
        try:
            LogManagerPoller()
        except Exception as e:
            print(f"[LogManager] AutoLogManager start error: {e}")


class LogManagerPoller:
    """Poller pentru curatarea log-urilor periodica."""
    def __init__(self):
        from enigma import eTimer
        self._trim_timer = eTimer()
        self._trim_timer.callback.append(self.TrimTimerJob)
        self._trim_timer.start(30000, True)  # 30s one-shot

        self._trash_timer = eTimer()
        self._trash_timer.callback.append(self.TrashTimerJob)
        self._trash_timer.start(35000, True)  # 35s one-shot

        print("[LogManager] Trim Poll Started")
        print("[LogManager] Trash Poll Started")

    def TrimTimerJob(self):
        try:
            self.JobTrim()
        except Exception as e:
            print(f"[LogManager] TrimTimerJob error: {e}")

    def TrashTimerJob(self):
        try:
            self.JobTrash()
        except Exception as e:
            print(f"[LogManager] TrashTimerJob error: {e}")

    def JobTrim(self):
        import re
        try:
            limit = int(config.logmanager.debugloglimit.value or 5)
        except Exception:
            limit = 5
        try:
            logs = sorted([f for f in os.listdir(CALE_JURNALE) if f.endswith('-enigma2-debug.log')], reverse=True)
            for old in logs[limit:]:
                try:
                    os.remove(os.path.join(CALE_JURNALE, old))
                    print(f"[LogManager] Trimmed: {old}")
                except Exception:
                    pass
        except Exception as e:
            print(f"[LogManager] JobTrim error: {e}")

    def JobTrash(self):
        try:
            days = int(config.logmanager.daysloglimit.value)
        except Exception:
            days = 14
        cutoff = time.time() - days * 86400
        try:
            for f in os.listdir(CALE_JURNALE):
                fp = os.path.join(CALE_JURNALE, f)
                if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                    try:
                        os.remove(fp)
                        print(f"[LogManager] Trashed old log: {f}")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[LogManager] JobTrash error: {e}")


# ------------------------------------------------------------------ ecrane reale
def _listaJurnale():
    """Fisierele din CALE_JURNALE, cele mai noi primele (Components/HdsJurnale.listaJurnale)."""
    return HdsJurnale.listaJurnale()


class LogInfo(Screen):
    """Informatii generale: cate jurnale, cat spatiu ocupa, setarile de curatare automata."""
    skin = """
    <screen name="LogInfo" resolution="1920,1080" position="center,center" size="900,420" title="Informații jurnale">
        <widget name="text" position="30,30" size="840,320" font="Regular;22" />
        <widget name="key_red" position="30,360" size="840,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle(_("Informații jurnale"))
        dosar, numar, total_mb, pastrate, zile = HdsJurnale.informatii(_listaJurnale())
        text = _(
            "Director jurnale: %s\n"
            "Număr fișiere: %d\n"
            "Spațiu total: %.1f MB\n\n"
            "Păstrează cel mult %d jurnale de depanare, șterge tot ce e mai vechi de %d zile "
            "(curățare automată, rulează doar dacă AutoLogManager e pornit din codul principal)."
        ) % (dosar, numar, total_mb, pastrate, zile)
        self["text"] = Label(text)
        self["key_red"] = Button(_("Înapoi"))
        self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"],
            {"cancel": self.close, "red": self.close}, -2)


class HdsLogManagerViewLog(Screen):
    """Continutul unui singur fisier de jurnal, cu derulare."""
    # HDSatelit (gasit la testare reala, live, in emulator -- blocaj real reprodus, "main
    # thread is non-idle! display spinner!", capcana deja cunoscuta in acest depozit
    # -- vezi HdsSoftwareUpdate/TempFanControl): clasa se numea `LogManagerViewLog`, nume care COLIDA cu
    # `<screen name="LogManagerViewLog">` deja existent in skin.xml (pregatit pentru echivalentul
    # altor imagini, cu un widget "list", nu "text") -- Enigma2 cauta INTAI dupa numele clasei in skin.xml
    # INCARCAT, inaintea atributului `skin` din clasa Python (cf. `skin.py:readSkin()`). Ecranul se deschidea
    # fara Traceback, dar widget-ul "text" nu exista in skinul GRESIT gasit ("warning, skin is missing
    # element text"), skinAttributes ramanea None, iar ScrollLabel calcula un pageHeight NEGATIV -> bucla de
    # paginare din ScrollLabel.setText() nu se mai oprea (blocaj real). Redenumit `Hds...`, consistent cu
    # restul codului propriu, ca sa nu mai colideze cu nimic din skin.xml.
    skin = """
    <screen name="HdsLogManagerViewLog" resolution="1920,1080" position="center,center" size="1600,900" title="Jurnal">
        <widget name="text" position="20,20" size="1560,820" font="Regular;20" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="20,860" size="1560,30" zPosition="1" font="Regular;18" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
    </screen>
    """

    def __init__(self, session, cale_fisier):
        Screen.__init__(self, session)
        self._cale = cale_fisier
        self.setTitle(_("Jurnal: %s") % os.path.basename(cale_fisier))
        # Continutul se citeste in constructor si se da direct la ScrollLabel(), tiparul folosit si de
        # `HdsAbout` (Information.py) -- mai simplu si mai robust decat text gol + setText() mai tarziu.
        continut = self._citesteJurnal(cale_fisier)
        self["text"] = ScrollLabel(continut)
        self["key_red"] = Button(_("Înapoi"))
        # Sus, Jos, Stanga, Dreapta dau pagina (si tinute apasat); ridicarea tastei nu face nimic, dar e legata, ca
        # jurnalul enigma2 sa nu scrie „unknown action”
        text = self["text"]
        directii = {"up": text.pageUp, "down": text.pageDown, "left": text.pageUp, "right": text.pageDown}
        for s in ("up", "down", "left", "right"):
            directii[s + "Repeated"] = directii[s]
            directii[s + "Up"] = self._nimic
        directii.update({"cancel": self.close, "red": self.close})
        self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], directii, -2)
        # CH+ si CH- (si |<< >>|) dau si ele pagina, ca in „Informatii despre sistem”; tastele colorate din acelasi
        # context: rosu inchide, celelalte nimic (altfel jurnalul scrie „unknown action”)
        self["pagini"] = ActionMap(["ChannelSelectBaseActions"], {
            "nextBouquet": text.pageUp,
            "prevBouquet": text.pageDown,
            "prevMarker": text.pageUp,
            "nextMarker": text.pageDown,
            "showAllServices": self.close,
            "showSatellites": self._nimic,
            "showProviders": self._nimic,
            "showFavourites": self._nimic,
        }, -2)

    def _nimic(self):
        pass

    def _citesteJurnal(self, cale_fisier):
        return HdsJurnale.citesteJurnal(cale_fisier)


class HdsLogManager(Screen):
    """Lista jurnalelor din CALE_JURNALE; OK deschide jurnalul selectat, Galben sterge, Albastru arata info."""
    # HDSatelit: redenumit din `LogManager` -- acelasi motiv ca `HdsLogManagerViewLog` de mai
    # sus, `<screen name="LogManager">` exista deja in skin.xml (widget "list"/"LogsSize", nu "lista"/
    # butoanele proprii) -- fara redenumire, ecranul ar fi luat skinul gresit la fel de tacut.
    skin = """
    <screen name="HdsLogManager" resolution="1920,1080" position="center,center" size="1200,700" title="Manager jurnale">
        <widget name="lista" position="30,30" size="1140,560" font="Regular;22" itemHeight="40" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="30,640" size="270,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
        <widget name="key_green" position="310,640" size="270,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
        <widget name="key_yellow" position="590,640" size="270,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
        <widget name="key_blue" position="870,640" size="270,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#185090" transparent="0" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle(_("Manager jurnale"))
        self["key_red"] = Button(_("Înapoi"))
        self["key_green"] = Button(_("Deschide"))
        self["key_yellow"] = Button(_("Șterge"))
        self["key_blue"] = Button(_("Informații"))
        self["actiuni"] = ActionMap(
            ["OkCancelActions", "ColorActions"],
            {
                "cancel": self.close,
                "red": self.close,
                "ok": self._deschide,
                "green": self._deschide,
                "yellow": self._sterge,
                "blue": self._informatii,
            }, -2)
        # HDSatelit (gasit la proba in emulator, cu 2 jurnale false):
        # `MenuList` se creeaza O SINGURA DATA aici, in constructor; `_reincarca()` foloseste `.setList()`,
        # NU mai reasigneaza `self["lista"]` la un obiect nou. Reasignarea dupa ce ecranul e deja construit
        # nu re-leaga widget-ul C++ -- lista vizibila ramanea NESCHIMBATA dupa o stergere (jurnalul disparea
        # de pe disc, dar tot aparea in lista, cu riscul real ca urmatoarea stergere sa loveasca alt fisier
        # decat cel aratat userului). Tiparul corect e deja folosit in HdsCrashlogAutoSubmit.
        self["lista"] = MenuList([])
        self._jurnale = []
        self._reincarca()

    def _reincarca(self):
        self._jurnale = _listaJurnale()
        randuri = [HdsJurnale.textRand(nume, marime, mtime) for mtime, nume, marime in self._jurnale]
        self["lista"].setList(randuri or [_("Niciun fișier de jurnal găsit în %s") % CALE_JURNALE])

    def _selectat(self):
        index = self["lista"].getSelectionIndex()
        if self._jurnale and 0 <= index < len(self._jurnale):
            return os.path.join(CALE_JURNALE, self._jurnale[index][1])
        return None

    def _deschide(self):
        cale = self._selectat()
        if cale:
            self.session.open(HdsLogManagerViewLog, cale)

    def _sterge(self):
        cale = self._selectat()
        if not cale:
            return
        # HDSatelit: adaugata confirmarea, care lipsea (ca la `HdsCrashlogAutoSubmit`/`CleanupWizard`, care
        # confirma). Tiparul e identic.
        self.session.openWithCallback(
            lambda raspuns: self._dupaConfirmareStergere(raspuns, cale),
            MessageBox,
            _("Ștergi jurnalul „%s”?") % os.path.basename(cale),
            MessageBox.TYPE_YESNO,
            default=False,
        )

    def _dupaConfirmareStergere(self, raspuns, cale):
        if not raspuns:
            return
        HdsJurnale.stergeFisier(cale)
        self._reincarca()

    def _informatii(self):
        self.session.open(LogInfo)
