# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: Asistent HD Satelit, 2026

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ScrollLabel import ScrollLabel
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components.ConfigList import ConfigListScreen
from Components.config import config, ConfigSelection, configfile, getConfigListEntry
from Components.Language import language
from Components.About import about
import unicodedata

try:
    from Components import VideoOutput as VideoOutputModule
except Exception:
    VideoOutputModule = None

# secunde pentru confirmarea rezolutiei (ca in Setari > Video): fara raspuns revine setarea de dinainte
VIDEO_CONFIRM_SECONDS = 20

# lista rezolutiilor cand iesirea video lipseste (probele de pe PC): aceleasi 8 ca pe un televizor Full HD / 4K, in
# ordinea din Setari > Video, cu etichetele din VideoOutput.modeLabel, si modul luminat
REZOLUTII_REZERVA = (
    ("2160p50", "2160p 4K UHD 50 Hz"),
    ("2160p", "2160p 4K UHD 60 Hz"),
    ("1080p50", "1080p Full HD 50 Hz"),
    ("1080p", "1080p Full HD 60 Hz"),
    ("1080i50", "1080i Full HD 50 Hz"),
    ("1080i", "1080i Full HD 60 Hz"),
    ("720p50", "720p HD 50 Hz"),
    ("720p", "720p HD 60 Hz"),
)
REZOLUTIE_IMPLICITA = "1080p50"


def cheieSortare(nume):
    """cheia listei limbilor: fara semnele diacritice (NFKD, fara categoriile Mn si Cf) si fara majuscule, ca
    „Čeština” sa stea langa „Català”, nu dupa „Türkçe”; scrierile nelatine raman la coada"""
    descompus = unicodedata.normalize("NFKD", nume)
    return "".join(c for c in descompus if unicodedata.category(c) not in ("Mn", "Cf")).casefold()


# Dictionar multilingv integrat pentru asistentul HD Satelit
# Textele spun numai ce face acum imaginea, verificat in cod. Asistentul are doua pagini, configurarea si prezentarea
# imaginii.
# Din 0.2.8 lista de pe pagina 2 nu mai sta aici. Functiile principale
# ale receptorului sunt o singura lista, in Components/HdsFunctii.py, tradusa prin po in 13 limbi si folosita la fel de
# "Despre imagine" si de interfata web (vezi listaFunctii mai jos).
WIZARD_TRANSLATIONS = {
    "ro_RO": {
        "title": "Asistent Configurare HD Satelit",
        "step_counter": "Pagina {0} din {1}",
        "btn_back": "Înapoi",
        "btn_next": "Continuă",
        "btn_finish": "Meniul principal",
        "box_info": "Receptor: {0}\nChipset: {1}\nSistem: HD Satelit\n{2}\nHD Satelit coordonează, Monea Software programează.",
        "page1_title": "Configurare: limba și rezoluția",
        "page1_desc": "Bun venit la noul sistem HD Satelit.\nCu SUS / JOS alegi rândul, cu STÂNGA / DREAPTA sau OK schimbi valoarea.\nApoi apasă butonul VERDE pentru a continua.",
        "entry_lang": "Limbă",
        "entry_video": "Rezoluție video HDMI",
        "page1_help_title": "Limbă și rezoluție",
        "page1_help_desc": "Meniurile și asistentul sunt traduse complet în toate cele 13 limbi din listă.\n\nLista arată numai rezoluțiile acceptate de televizor. Recomandat: 1080p 50 Hz (Full HD) sau 2160p 50 Hz (4K UHD); canalele din Europa au 50 Hz.\n\nO rezoluție nouă rămâne numai după confirmare; fără răspuns, după 20 de secunde revine cea de dinainte.",
        "page1_feature_title": "DUPĂ CONFIGURARE",
        "page1_feature_desc": "Pagina următoare arată funcțiile principale ale receptorului.\n\nApoi asistentul se închide și se deschide meniul principal al receptorului. Primele în meniu sunt „Scanare” (tasta 1), pentru căutarea canalelor, și „Orientarea și setarea antenei” (tasta 2).\n\nLimba, rezoluția și celelalte setări se pot schimba oricând din meniu.",
        "page2_title": "Funcțiile receptorului HD Satelit",
        "page2_desc": "Funcțiile principale, pe grupe: derulează cu CH+ / CH- sau SUS / JOS.\nVERDE sau OK: asistentul se închide și se deschide meniul principal.\nEXIT: înapoi la limbă și rezoluție.",
        "page2_help_title": "Ce urmează",
        "page2_help_desc": "Setările alese sunt salvate pe receptor.\n\nVERDE sau OK deschide meniul principal. Primele în meniu:\n„Scanare” (tasta 1), pentru căutarea canalelor prin satelit, cablu sau terestru;\n„Orientarea și setarea antenei” (tasta 2).\n\nAsistentul nu mai pornește după aceea; limba și rezoluția se schimbă din meniu.",
    },
    "en_EN": {
        "title": "HD Satelit Setup Wizard",
        "step_counter": "Page {0} of {1}",
        "btn_back": "Back",
        "btn_next": "Continue",
        "btn_finish": "Main menu",
        "box_info": "Receiver: {0}\nChipset: {1}\nSystem: HD Satelit\n{2}\nCoordinated by HD Satelit, programmed by Monea Software.",
        "page1_title": "Setup: language and resolution",
        "page1_desc": "Welcome to the new HD Satelit system.\nUP / DOWN picks the row, LEFT / RIGHT or OK changes the value.\nThen press the GREEN button to continue.",
        "entry_lang": "Language",
        "entry_video": "HDMI video resolution",
        "page1_help_title": "Language and resolution",
        "page1_help_desc": "The menus and the wizard are fully translated into all 13 languages in the list.\n\nThe list shows only the resolutions your TV accepts. Recommended: 1080p 50 Hz (Full HD) or 2160p 50 Hz (4K UHD); channels in Europe use 50 Hz.\n\nA new resolution stays only after you confirm it; without an answer, the previous one comes back after 20 seconds.",
        "page1_feature_title": "AFTER SETUP",
        "page1_feature_desc": "The next page shows the main features of the receiver.\n\nThen the wizard closes and the main menu of the receiver opens. The first menu entries are “Channel scan” (key 1), to search for channels, and “Dish alignment and setup” (key 2).\n\nThe language, the resolution and the other settings can be changed at any time from the menu.",
        "page2_title": "HD Satelit receiver features",
        "page2_desc": "The main features, by group: scroll with CH+ / CH- or UP / DOWN.\nGREEN or OK: the wizard closes and the main menu opens.\nEXIT: back to language and resolution.",
        "page2_help_title": "What comes next",
        "page2_help_desc": "The chosen settings are saved on the receiver.\n\nGREEN or OK opens the main menu. The first entries:\n“Channel scan” (key 1), to search for satellite, cable or terrestrial channels;\n“Dish alignment and setup” (key 2).\n\nThe wizard does not start again; language and resolution are changed from the menu.",
    },
    "de_DE": {
        "title": "HD Satelit Einrichtungsassistent",
        "step_counter": "Seite {0} von {1}",
        "btn_back": "Zurück",
        "btn_next": "Weiter",
        "btn_finish": "Hauptmenü",
        "box_info": "Receiver: {0}\nChipsatz: {1}\nSystem: HD Satelit\n{2}\nKoordination: HD Satelit, Programmierung: Monea Software.",
        "page1_title": "Einrichtung: Sprache und Auflösung",
        "page1_desc": "Willkommen beim neuen HD Satelit System.\nAUF / AB wählt die Zeile, LINKS / RECHTS oder OK ändert den Wert.\nDann drück die GRÜNE Taste, um weiterzumachen.",
        "entry_lang": "Sprache",
        "entry_video": "HDMI Video-Auflösung",
        "page1_help_title": "Sprache und Auflösung",
        "page1_help_desc": "Die Menüs und der Assistent sind in alle 13 Sprachen der Liste vollständig übersetzt.\n\nDie Liste zeigt nur die Auflösungen, die dein Fernseher annimmt. Empfohlen: 1080p 50 Hz (Full HD) oder 2160p 50 Hz (4K UHD); Sender in Europa senden mit 50 Hz.\n\nEine neue Auflösung bleibt nur nach deiner Bestätigung; ohne Antwort kehrt nach 20 Sekunden die vorherige zurück.",
        "page1_feature_title": "NACH DER EINRICHTUNG",
        "page1_feature_desc": "Die nächste Seite zeigt die wichtigsten Funktionen des Receivers.\n\nDann schließt sich der Assistent und das Hauptmenü des Receivers öffnet sich. Die ersten Einträge im Menü sind „Sendersuche“ (Taste 1), um Sender zu suchen, und „Antenne ausrichten und einstellen“ (Taste 2).\n\nSprache, Auflösung und die anderen Einstellungen lassen sich jederzeit im Menü ändern.",
        "page2_title": "Funktionen des HD Satelit Receivers",
        "page2_desc": "Die wichtigsten Funktionen, nach Gruppen: blättern mit CH+ / CH- oder AUF / AB.\nGRÜN oder OK: der Assistent schließt sich und das Hauptmenü öffnet sich.\nEXIT: zurück zu Sprache und Auflösung.",
        "page2_help_title": "Wie es weitergeht",
        "page2_help_desc": "Die gewählten Einstellungen sind auf dem Receiver gespeichert.\n\nGRÜN oder OK öffnet das Hauptmenü. Die ersten Einträge:\n„Sendersuche“ (Taste 1), um Satelliten-, Kabel- oder terrestrische Sender zu suchen;\n„Antenne ausrichten und einstellen“ (Taste 2).\n\nDer Assistent startet nicht wieder; Sprache und Auflösung änderst du im Menü.",
    },
    "hu_HU": {
        "title": "HD Satelit Beállítási Varázsló",
        "step_counter": "{0}. oldal, összesen {1}",
        "btn_back": "Vissza",
        "btn_next": "Tovább",
        "btn_finish": "Főmenü",
        "box_info": "Vevő: {0}\nLapkakészlet: {1}\nRendszer: HD Satelit\n{2}\nKoordinálás: HD Satelit, programozás: Monea Software.",
        "page1_title": "Beállítás: nyelv és felbontás",
        "page1_desc": "Üdv az új HD Satelit rendszerben.\nA FEL / LE gomb a sort választja, a BAL / JOBB vagy az OK az értéket módosítja.\nA folytatáshoz nyomd meg a ZÖLD gombot.",
        "entry_lang": "Nyelv",
        "entry_video": "HDMI videó felbontás",
        "page1_help_title": "Nyelv és felbontás",
        "page1_help_desc": "A menük és a varázsló a lista mind a 13 nyelvére teljesen le vannak fordítva.\n\nA lista csak a tévéd által elfogadott felbontásokat mutatja. Ajánlott: 1080p 50 Hz (Full HD) vagy 2160p 50 Hz (4K UHD); az európai csatornák 50 Hz-esek.\n\nAz új felbontás csak megerősítés után marad meg; válasz nélkül 20 másodperc múlva visszaáll az előző.",
        "page1_feature_title": "A BEÁLLÍTÁS UTÁN",
        "page1_feature_desc": "A következő oldal a vevőkészülék fő funkcióit mutatja.\n\nEzután a varázsló bezárul, és megnyílik a vevőkészülék főmenüje. A menü első pontjai a „Csatornakeresés” (1-es gomb) a csatornák kereséséhez és az „Antenna irányzása és beállítása” (2-es gomb).\n\nA nyelv, a felbontás és a többi beállítás a menüből bármikor módosítható.",
        "page2_title": "A HD Satelit vevőkészülék funkciói",
        "page2_desc": "A fő funkciók, csoportonként: görgetés a CH+ / CH- vagy a FEL / LE gombbal.\nZÖLD vagy OK: a varázsló bezárul, és megnyílik a főmenü.\nEXIT: vissza a nyelvhez és a felbontáshoz.",
        "page2_help_title": "A következő lépés",
        "page2_help_desc": "A választott beállítások el vannak mentve a vevőkészüléken.\n\nA ZÖLD vagy az OK gomb megnyitja a főmenüt. Az első pontok:\n„Csatornakeresés” (1-es gomb) műholdas, kábeles vagy földi csatornák kereséséhez;\n„Antenna irányzása és beállítása” (2-es gomb).\n\nA varázsló nem indul el újra; a nyelvet és a felbontást a menüben módosíthatod.",
    },
    "fr_FR": {
        "title": "Assistant de configuration HD Satelit",
        "step_counter": "Page {0} sur {1}",
        "btn_back": "Retour",
        "btn_next": "Continuer",
        "btn_finish": "Menu principal",
        "box_info": "Récepteur : {0}\nChipset : {1}\nSystème : HD Satelit\n{2}\nCoordination : HD Satelit, programmation : Monea Software.",
        "page1_title": "Configuration : langue et résolution",
        "page1_desc": "Bienvenue dans le nouveau système HD Satelit.\nHAUT / BAS choisit la ligne, GAUCHE / DROITE ou OK change la valeur.\nAppuie ensuite sur le bouton VERT pour continuer.",
        "entry_lang": "Langue",
        "entry_video": "Résolution vidéo HDMI",
        "page1_help_title": "Langue et résolution",
        "page1_help_desc": "Les menus et l'assistant sont entièrement traduits dans les 13 langues de la liste.\n\nLa liste ne montre que les résolutions acceptées par ton téléviseur. Conseillé : 1080p 50 Hz (Full HD) ou 2160p 50 Hz (4K UHD) ; les chaînes en Europe sont en 50 Hz.\n\nUne nouvelle résolution ne reste qu'après confirmation ; sans réponse, la précédente revient après 20 secondes.",
        "page1_feature_title": "APRÈS LA CONFIGURATION",
        "page1_feature_desc": "La page suivante montre les fonctions principales du récepteur.\n\nEnsuite l'assistant se ferme et le menu principal du récepteur s'ouvre. Les premières entrées du menu sont « Recherche de chaînes » (touche 1), pour chercher les chaînes, et « Orientation et réglage de l'antenne » (touche 2).\n\nLa langue, la résolution et les autres réglages se changent à tout moment depuis le menu.",
        "page2_title": "Fonctions du récepteur HD Satelit",
        "page2_desc": "Les fonctions principales, par groupe : fais défiler avec CH+ / CH- ou HAUT / BAS.\nVERT ou OK : l'assistant se ferme et le menu principal s'ouvre.\nEXIT : retour à la langue et à la résolution.",
        "page2_help_title": "La suite",
        "page2_help_desc": "Les réglages choisis sont enregistrés sur le récepteur.\n\nVERT ou OK ouvre le menu principal. Les premières entrées :\n« Recherche de chaînes » (touche 1), pour chercher les chaînes satellite, câble ou terrestres ;\n« Orientation et réglage de l'antenne » (touche 2).\n\nL'assistant ne se relance plus ; la langue et la résolution se changent dans le menu.",
    },
    "es_ES": {
        "title": "Asistente de configuración HD Satelit",
        "step_counter": "Página {0} de {1}",
        "btn_back": "Atrás",
        "btn_next": "Continuar",
        "btn_finish": "Menú principal",
        "box_info": "Receptor: {0}\nChipset: {1}\nSistema: HD Satelit\n{2}\nCoordinación: HD Satelit, programación: Monea Software.",
        "page1_title": "Configuración: idioma y resolución",
        "page1_desc": "Bienvenido al nuevo sistema HD Satelit.\nARRIBA / ABAJO elige la fila, IZQUIERDA / DERECHA u OK cambia el valor.\nLuego pulsa el botón VERDE para continuar.",
        "entry_lang": "Idioma",
        "entry_video": "Resolución de vídeo HDMI",
        "page1_help_title": "Idioma y resolución",
        "page1_help_desc": "Los menús y el asistente están traducidos por completo a los 13 idiomas de la lista.\n\nLa lista muestra solo las resoluciones que acepta tu televisor. Recomendado: 1080p 50 Hz (Full HD) o 2160p 50 Hz (4K UHD); los canales en Europa usan 50 Hz.\n\nUna resolución nueva solo se queda tras confirmarla; sin respuesta, a los 20 segundos vuelve la anterior.",
        "page1_feature_title": "DESPUÉS DE LA CONFIGURACIÓN",
        "page1_feature_desc": "La página siguiente muestra las funciones principales del receptor.\n\nLuego el asistente se cierra y se abre el menú principal del receptor. Las primeras entradas del menú son “Búsqueda de canales” (tecla 1), para buscar canales, y “Orientación y ajuste de la antena” (tecla 2).\n\nEl idioma, la resolución y los demás ajustes se pueden cambiar en cualquier momento desde el menú.",
        "page2_title": "Funciones del receptor HD Satelit",
        "page2_desc": "Las funciones principales, por grupos: desplázate con CH+ / CH- o ARRIBA / ABAJO.\nVERDE u OK: el asistente se cierra y se abre el menú principal.\nEXIT: volver al idioma y la resolución.",
        "page2_help_title": "Lo que sigue",
        "page2_help_desc": "Los ajustes elegidos se guardan en el receptor.\n\nVERDE u OK abre el menú principal. Las primeras entradas:\n“Búsqueda de canales” (tecla 1), para buscar canales por satélite, cable o terrestres;\n“Orientación y ajuste de la antena” (tecla 2).\n\nEl asistente no vuelve a arrancar; el idioma y la resolución se cambian desde el menú.",
    },
    "it_IT": {
        "title": "Configurazione guidata HD Satelit",
        "step_counter": "Pagina {0} di {1}",
        "btn_back": "Indietro",
        "btn_next": "Continua",
        "btn_finish": "Menu principale",
        "box_info": "Ricevitore: {0}\nChipset: {1}\nSistema: HD Satelit\n{2}\nCoordinamento: HD Satelit, programmazione: Monea Software.",
        "page1_title": "Configurazione: lingua e risoluzione",
        "page1_desc": "Benvenuto nel nuovo sistema HD Satelit.\nSU / GIÙ sceglie la riga, SINISTRA / DESTRA oppure OK cambia il valore.\nPoi premi il tasto VERDE per continuare.",
        "entry_lang": "Lingua",
        "entry_video": "Risoluzione video HDMI",
        "page1_help_title": "Lingua e risoluzione",
        "page1_help_desc": "I menu e la configurazione guidata sono tradotti completamente in tutte le 13 lingue dell'elenco.\n\nL'elenco mostra solo le risoluzioni accettate dal tuo televisore. Consigliato: 1080p 50 Hz (Full HD) o 2160p 50 Hz (4K UHD); i canali in Europa usano 50 Hz.\n\nUna nuova risoluzione resta solo dopo la conferma; senza risposta, dopo 20 secondi torna quella di prima.",
        "page1_feature_title": "DOPO LA CONFIGURAZIONE",
        "page1_feature_desc": "La pagina successiva mostra le funzioni principali del ricevitore.\n\nPoi la configurazione guidata si chiude e si apre il menu principale del ricevitore. Le prime voci del menu sono “Ricerca canali” (tasto 1), per cercare i canali, e “Puntamento e impostazione dell'antenna” (tasto 2).\n\nLa lingua, la risoluzione e le altre impostazioni si possono cambiare in qualsiasi momento dal menu.",
        "page2_title": "Funzioni del ricevitore HD Satelit",
        "page2_desc": "Le funzioni principali, per gruppi: scorri con CH+ / CH- o SU / GIÙ.\nVERDE oppure OK: la configurazione guidata si chiude e si apre il menu principale.\nEXIT: torna a lingua e risoluzione.",
        "page2_help_title": "Cosa succede dopo",
        "page2_help_desc": "Le impostazioni scelte sono salvate sul ricevitore.\n\nVERDE oppure OK apre il menu principale. Le prime voci:\n“Ricerca canali” (tasto 1), per cercare i canali via satellite, cavo o digitale terrestre;\n“Puntamento e impostazione dell'antenna” (tasto 2).\n\nLa configurazione guidata non riparte più; lingua e risoluzione si cambiano dal menu.",
    },
    "cs_CZ": {
        "title": "Průvodce nastavením HD Satelit",
        "step_counter": "Strana {0} z {1}",
        "btn_back": "Zpět",
        "btn_next": "Pokračovat",
        "btn_finish": "Hlavní nabídka",
        "box_info": "Přijímač: {0}\nČipová sada: {1}\nSystém: HD Satelit\n{2}\nKoordinace: HD Satelit, programování: Monea Software.",
        "page1_title": "Nastavení: jazyk a rozlišení",
        "page1_desc": "Vítej v novém systému HD Satelit.\nNAHORU / DOLŮ vybírá řádek, VLEVO / VPRAVO nebo OK mění hodnotu.\nPak stiskni ZELENÉ tlačítko a pokračuj.",
        "entry_lang": "Jazyk",
        "entry_video": "Rozlišení videa HDMI",
        "page1_help_title": "Jazyk a rozlišení",
        "page1_help_desc": "Nabídky i průvodce jsou úplně přeložené do všech 13 jazyků v seznamu.\n\nSeznam ukazuje jen rozlišení, která tvůj televizor přijímá. Doporučeno: 1080p 50 Hz (Full HD) nebo 2160p 50 Hz (4K UHD); kanály v Evropě vysílají v 50 Hz.\n\nNové rozlišení zůstane jen po potvrzení; bez odpovědi se po 20 sekundách vrátí předchozí.",
        "page1_feature_title": "PO NASTAVENÍ",
        "page1_feature_desc": "Další strana ukazuje hlavní funkce přijímače.\n\nPak se průvodce zavře a otevře se hlavní nabídka přijímače. První položky nabídky jsou „Vyhledávání kanálů“ (tlačítko 1) pro hledání kanálů a „Nasměrování a nastavení antény“ (tlačítko 2).\n\nJazyk, rozlišení a ostatní nastavení můžeš kdykoli změnit v nabídce.",
        "page2_title": "Funkce přijímače HD Satelit",
        "page2_desc": "Hlavní funkce podle skupin: posouvej pomocí CH+ / CH- nebo NAHORU / DOLŮ.\nZELENÉ nebo OK: průvodce se zavře a otevře se hlavní nabídka.\nEXIT: zpět k jazyku a rozlišení.",
        "page2_help_title": "Co bude dál",
        "page2_help_desc": "Zvolená nastavení jsou uložená v přijímači.\n\nZELENÉ nebo OK otevře hlavní nabídku. První položky:\n„Vyhledávání kanálů“ (tlačítko 1) pro hledání satelitních, kabelových nebo pozemních kanálů;\n„Nasměrování a nastavení antény“ (tlačítko 2).\n\nPrůvodce se už znovu nespustí; jazyk a rozlišení změníš v nabídce.",
    },
    "pl_PL": {
        "title": "Kreator konfiguracji HD Satelit",
        "step_counter": "Strona {0} z {1}",
        "btn_back": "Wstecz",
        "btn_next": "Dalej",
        "btn_finish": "Menu główne",
        "box_info": "Odbiornik: {0}\nChipset: {1}\nSystem: HD Satelit\n{2}\nKoordynacja: HD Satelit, programowanie: Monea Software.",
        "page1_title": "Konfiguracja: język i rozdzielczość",
        "page1_desc": "Witaj w nowym systemie HD Satelit.\nGÓRA / DÓŁ wybiera wiersz, LEWO / PRAWO lub OK zmienia wartość.\nPotem naciśnij ZIELONY przycisk, aby kontynuować.",
        "entry_lang": "Język",
        "entry_video": "Rozdzielczość wideo HDMI",
        "page1_help_title": "Język i rozdzielczość",
        "page1_help_desc": "Menu i kreator są w pełni przetłumaczone na wszystkie 13 języków z listy.\n\nLista pokazuje tylko rozdzielczości, które przyjmuje twój telewizor. Zalecane: 1080p 50 Hz (Full HD) lub 2160p 50 Hz (4K UHD); kanały w Europie nadają w 50 Hz.\n\nNowa rozdzielczość zostaje tylko po potwierdzeniu; bez odpowiedzi po 20 sekundach wraca poprzednia.",
        "page1_feature_title": "PO KONFIGURACJI",
        "page1_feature_desc": "Następna strona pokazuje główne funkcje odbiornika.\n\nPotem kreator się zamyka i otwiera się menu główne odbiornika. Pierwsze pozycje menu to „Wyszukiwanie kanałów” (przycisk 1), do szukania kanałów, i „Ustawianie i konfiguracja anteny” (przycisk 2).\n\nJęzyk, rozdzielczość i pozostałe ustawienia możesz zmienić w każdej chwili w menu.",
        "page2_title": "Funkcje odbiornika HD Satelit",
        "page2_desc": "Główne funkcje, według grup: przewijaj przyciskami CH+ / CH- lub GÓRA / DÓŁ.\nZIELONY lub OK: kreator się zamyka i otwiera się menu główne.\nEXIT: powrót do języka i rozdzielczości.",
        "page2_help_title": "Co dalej",
        "page2_help_desc": "Wybrane ustawienia są zapisane w odbiorniku.\n\nZIELONY lub OK otwiera menu główne. Pierwsze pozycje:\n„Wyszukiwanie kanałów” (przycisk 1), do szukania kanałów satelitarnych, kablowych lub naziemnych;\n„Ustawianie i konfiguracja anteny” (przycisk 2).\n\nKreator nie uruchomi się ponownie; język i rozdzielczość zmieniasz w menu.",
    },
    "pt_PT": {
        "title": "Assistente de configuração HD Satelit",
        "step_counter": "Página {0} de {1}",
        "btn_back": "Voltar",
        "btn_next": "Continuar",
        "btn_finish": "Menu principal",
        "box_info": "Recetor: {0}\nChipset: {1}\nSistema: HD Satelit\n{2}\nCoordenação: HD Satelit, programação: Monea Software.",
        "page1_title": "Configuração: idioma e resolução",
        "page1_desc": "Bem-vindo ao novo sistema HD Satelit.\nCIMA / BAIXO escolhe a linha, ESQUERDA / DIREITA ou OK muda o valor.\nDepois carrega no botão VERDE para continuar.",
        "entry_lang": "Idioma",
        "entry_video": "Resolução de vídeo HDMI",
        "page1_help_title": "Idioma e resolução",
        "page1_help_desc": "Os menus e o assistente estão totalmente traduzidos nos 13 idiomas da lista.\n\nA lista mostra só as resoluções que o teu televisor aceita. Recomendado: 1080p 50 Hz (Full HD) ou 2160p 50 Hz (4K UHD); os canais na Europa usam 50 Hz.\n\nUma resolução nova só fica depois de a confirmares; sem resposta, ao fim de 20 segundos volta a anterior.",
        "page1_feature_title": "DEPOIS DA CONFIGURAÇÃO",
        "page1_feature_desc": "A página seguinte mostra as principais funções do recetor.\n\nDepois o assistente fecha-se e abre-se o menu principal do recetor. As primeiras entradas do menu são “Procura de canais” (tecla 1), para procurar canais, e “Orientação e configuração da antena” (tecla 2).\n\nO idioma, a resolução e as outras definições podem ser mudados a qualquer momento no menu.",
        "page2_title": "Funções do recetor HD Satelit",
        "page2_desc": "As funções principais, por grupos: percorre com CH+ / CH- ou CIMA / BAIXO.\nVERDE ou OK: o assistente fecha-se e abre-se o menu principal.\nEXIT: volta ao idioma e à resolução.",
        "page2_help_title": "O que vem a seguir",
        "page2_help_desc": "As definições escolhidas ficam guardadas no recetor.\n\nVERDE ou OK abre o menu principal. As primeiras entradas:\n“Procura de canais” (tecla 1), para procurar canais por satélite, cabo ou terrestres;\n“Orientação e configuração da antena” (tecla 2).\n\nO assistente não volta a arrancar; o idioma e a resolução mudam-se no menu.",
    },
    "nl_NL": {
        "title": "Installatiewizard HD Satelit",
        "step_counter": "Pagina {0} van {1}",
        "btn_back": "Terug",
        "btn_next": "Verder",
        "btn_finish": "Hoofdmenu",
        "box_info": "Ontvanger: {0}\nChipset: {1}\nSysteem: HD Satelit\n{2}\nCoördinatie: HD Satelit, programmering: Monea Software.",
        "page1_title": "Instellen: taal en resolutie",
        "page1_desc": "Welkom bij het nieuwe HD Satelit-systeem.\nOMHOOG / OMLAAG kiest de regel, LINKS / RECHTS of OK verandert de waarde.\nDruk daarna op de GROENE knop om verder te gaan.",
        "entry_lang": "Taal",
        "entry_video": "HDMI-videoresolutie",
        "page1_help_title": "Taal en resolutie",
        "page1_help_desc": "De menu's en de wizard zijn volledig vertaald in alle 13 talen van de lijst.\n\nDe lijst toont alleen de resoluties die je tv aanvaardt. Aanbevolen: 1080p 50 Hz (Full HD) of 2160p 50 Hz (4K UHD); zenders in Europa gebruiken 50 Hz.\n\nEen nieuwe resolutie blijft alleen na bevestiging; zonder antwoord komt na 20 seconden de vorige terug.",
        "page1_feature_title": "NA HET INSTELLEN",
        "page1_feature_desc": "De volgende pagina toont de belangrijkste functies van de ontvanger.\n\nDaarna sluit de wizard en opent het hoofdmenu van de ontvanger. De eerste menu-items zijn “Kanalen zoeken” (toets 1), om zenders te zoeken, en “Schotel richten en instellen” (toets 2).\n\nTaal, resolutie en de andere instellingen kun je altijd in het menu wijzigen.",
        "page2_title": "Functies van de HD Satelit-ontvanger",
        "page2_desc": "De belangrijkste functies, per groep: scrol met CH+ / CH- of OMHOOG / OMLAAG.\nGROEN of OK: de wizard sluit en het hoofdmenu opent.\nEXIT: terug naar taal en resolutie.",
        "page2_help_title": "Wat er nu komt",
        "page2_help_desc": "De gekozen instellingen zijn op de ontvanger opgeslagen.\n\nGROEN of OK opent het hoofdmenu. De eerste items:\n“Kanalen zoeken” (toets 1), om satelliet-, kabel- of antennezenders te zoeken;\n“Schotel richten en instellen” (toets 2).\n\nDe wizard start niet opnieuw; taal en resolutie wijzig je in het menu.",
    },
    "ru_RU": {
        "title": "Мастер настройки HD Satelit",
        "step_counter": "Страница {0} из {1}",
        "btn_back": "Назад",
        "btn_next": "Далее",
        "btn_finish": "Главное меню",
        "box_info": "Ресивер: {0}\nЧипсет: {1}\nСистема: HD Satelit\n{2}\nКоординация: HD Satelit, программирование: Monea Software.",
        "page1_title": "Настройка: язык и разрешение",
        "page1_desc": "Добро пожаловать в новую систему HD Satelit.\nВВЕРХ / ВНИЗ выбирает строку, ВЛЕВО / ВПРАВО или OK меняет значение.\nПотом нажми ЗЕЛЁНУЮ кнопку, чтобы продолжить.",
        "entry_lang": "Язык",
        "entry_video": "Разрешение видео HDMI",
        "page1_help_title": "Язык и разрешение",
        "page1_help_desc": "Меню и мастер полностью переведены на все 13 языков из списка.\n\nВ списке только разрешения, которые принимает твой телевизор. Рекомендуется: 1080p 50 Гц (Full HD) или 2160p 50 Гц (4K UHD); каналы в Европе вещают с частотой 50 Гц.\n\nНовое разрешение остаётся только после подтверждения; без ответа через 20 секунд вернётся прежнее.",
        "page1_feature_title": "ПОСЛЕ НАСТРОЙКИ",
        "page1_feature_desc": "На следующей странице показаны основные функции ресивера.\n\nПотом мастер закроется и откроется главное меню ресивера. Первые пункты меню: «Поиск каналов» (кнопка 1), для поиска каналов, и «Наведение и настройка антенны» (кнопка 2).\n\nЯзык, разрешение и другие настройки можно в любой момент изменить в меню.",
        "page2_title": "Функции ресивера HD Satelit",
        "page2_desc": "Основные функции по группам: листай кнопками CH+ / CH- или ВВЕРХ / ВНИЗ.\nЗЕЛЁНАЯ или OK: мастер закроется и откроется главное меню.\nEXIT: назад к языку и разрешению.",
        "page2_help_title": "Что дальше",
        "page2_help_desc": "Выбранные настройки сохранены на ресивере.\n\nЗЕЛЁНАЯ или OK открывает главное меню. Первые пункты:\n«Поиск каналов» (кнопка 1), для поиска спутниковых, кабельных или эфирных каналов;\n«Наведение и настройка антенны» (кнопка 2).\n\nМастер больше не запускается; язык и разрешение меняются в меню.",
    },
    "tr_TR": {
        "title": "HD Satelit Kurulum Sihirbazı",
        "step_counter": "Sayfa {0} / {1}",
        "btn_back": "Geri",
        "btn_next": "Devam",
        "btn_finish": "Ana menü",
        "box_info": "Alıcı: {0}\nYonga seti: {1}\nSistem: HD Satelit\n{2}\nKoordinasyon: HD Satelit, programlama: Monea Software.",
        "page1_title": "Kurulum: dil ve çözünürlük",
        "page1_desc": "Yeni HD Satelit sistemine hoş geldin.\nYUKARI / AŞAĞI satırı seçer, SOL / SAĞ veya OK değeri değiştirir.\nSonra devam etmek için YEŞİL tuşa bas.",
        "entry_lang": "Dil",
        "entry_video": "HDMI video çözünürlüğü",
        "page1_help_title": "Dil ve çözünürlük",
        "page1_help_desc": "Menüler ve sihirbaz listedeki 13 dilin hepsine tamamen çevrildi.\n\nListe yalnızca televizyonunun kabul ettiği çözünürlükleri gösterir. Önerilen: 1080p 50 Hz (Full HD) veya 2160p 50 Hz (4K UHD); Avrupa'daki kanallar 50 Hz kullanır.\n\nYeni çözünürlük yalnızca onayladıktan sonra kalır; yanıt yoksa 20 saniye sonra öncekine döner.",
        "page1_feature_title": "KURULUMDAN SONRA",
        "page1_feature_desc": "Sonraki sayfa alıcının ana işlevlerini gösterir.\n\nArdından sihirbaz kapanır ve alıcının ana menüsü açılır. Menünün ilk girişleri, kanal aramak için “Kanal Arama” (1 tuşu) ve “Anten yönlendirme ve ayarları” (2 tuşu).\n\nDil, çözünürlük ve diğer ayarlar menüden istediğin zaman değiştirilebilir.",
        "page2_title": "HD Satelit alıcısının işlevleri",
        "page2_desc": "Ana işlevler, gruplara göre: CH+ / CH- veya YUKARI / AŞAĞI ile kaydır.\nYEŞİL veya OK: sihirbaz kapanır ve ana menü açılır.\nEXIT: dil ve çözünürlüğe geri dön.",
        "page2_help_title": "Sırada ne var",
        "page2_help_desc": "Seçilen ayarlar alıcıya kaydedildi.\n\nYEŞİL veya OK ana menüyü açar. İlk girişler:\n“Kanal Arama” (1 tuşu), uydu, kablo veya karasal kanalları aramak için;\n“Anten yönlendirme ve ayarları” (2 tuşu).\n\nSihirbaz bir daha başlamaz; dili ve çözünürlüğü menüden değiştirirsin.",
    }
}


# asistentul are doua pagini, configurarea (limba si rezolutia) si prezentarea imaginii;
# la VERDE pe a doua se inchide si interfata deschide meniul principal. Id-ul notificarii cu meniul principal:
ID_MENIU_PRINCIPAL = "HdsStartWizardMeniuPrincipal"


def radacinaMeniuluiPrincipal():
    """nodul meniului principal din menu.xml, gasit ca in InfoBarMenu.mainMenu (Screens/InfoBarGenerics.py), deci
    acelasi meniu ca la tasta MENU"""
    from Screens.Menu import mdom
    menu = mdom.getroot()
    if menu.tag == "menuxml":
        gasit = next((m for m in menu.iter("menu") if m.get("key") == "mainmenu"), None)
        if gasit is None:
            gasit = menu.find("menu")
        if gasit is None:
            gasit = menu[0]
        menu = gasit
    return menu


def deschideMeniulPrincipal():
    """Pune meniul principal (acelasi ecran ca la tasta MENU) in coada de notificari. Asistentul ruleaza inaintea
    interfetei (mytest.py, screensToRun), iar interfata goleste coada cand porneste (InfoBarNotifications), ca la
    „Ce e nou” (Screens/HdsJurnalVersiuni.py): meniul apare peste imaginea TV, iar EXIT din el duce la TV.
    Intoarce True daca meniul a intrat in coada; o eroare ramane in jurnal si nu opreste inchiderea asistentului."""
    try:
        from Screens.Menu import MainMenu
        from Tools.Notifications import AddNotificationWithID
        AddNotificationWithID(ID_MENIU_PRINCIPAL, MainMenu, radacinaMeniuluiPrincipal())
        print("[HdsStartWizard] meniul principal pus in coada interfetei")
        return True
    except Exception as e:
        print("[HdsStartWizard] meniul principal nu a putut fi pus in coada:", e)
        return False



def listaFunctii():
    """(titlul, textul) listei de pe pagina 2: functiile principale ale receptorului din Components/HdsFunctii.py
    (aceeasi lista ca in "Despre imagine" si in web), in limba activa, titlul cu majuscule. Modulul se incarca abia aici,
    ca probele care incarca asistentul fara Components sa mearga; o eroare lasa chenarul gol si ramane in jurnal."""
    try:
        from Components import HdsFunctii
        return HdsFunctii.majuscule(HdsFunctii.titlu()), HdsFunctii.text()
    except Exception as e:
        print("[HdsStartWizard] lista functiilor: %r" % (e,))
        return "", ""


def _listaAlegerilor():
    """ChoiceBox pentru listele asistentului (limba, modul video): toate actiunile hartilor lui tratate (ChoiceBox leaga
    si DirectionActions, dar trateaza numai up / down, deci fiecare eliberare a unei sageti scria „unknown action” in
    jurnal) si bara de derulare aratata de la deschidere (eListbox o potriveste la prima mutare a selectiei; o lista
    lunga deschisa pe primul rand parea ca nu mai are nimic dedesubt)."""
    from Screens.ChoiceBox import ChoiceBox

    class ListaAlegerilor(ChoiceBox):
        def __init__(self, session, **k):
            ChoiceBox.__init__(self, session, **k)
            actiuni = self["actions"].actions
            for nume in ("left", "right", "upUp", "downUp", "leftUp", "rightUp", "upRepeated", "downRepeated",
                    "leftRepeated", "rightRepeated"):
                actiuni.setdefault(nume, self.nimic)
            self.onLayoutFinish.append(self.aratBara)

        def nimic(self):
            pass

        def aratBara(self):
            try:
                lista = self["list"]
                inst = lista.instance
                n = len(lista.list)
                if inst is None or n < 2:
                    return
                i = lista.getSelectionIndex()
                inst.moveSelection(inst.moveDown if i + 1 < n else inst.moveUp)
                inst.moveSelectionTo(i)
            except Exception as e:
                print("[HdsStartWizard] bara listei: %s" % e)
    return ListaAlegerilor

class HdsStartWizard(Screen, ConfigListScreen):
    """
    Asistentul HD Satelit de la prima pornire (Full HD 1080p nativ), in doua pagini:
    1. Configurare: sus limba (textele asistentului se schimba pe loc), jos rezolutia (numai modurile acceptate de
       televizor, cand le anunta; un mod nou ramane numai dupa confirmare, altfel revine dupa 20 s). VERDE mai departe.
    2. Functiile principale ale receptorului (Components/HdsFunctii.py, aceeasi lista ca in "Despre imagine" si in web),
       pe grupe, derulate cu CH+/CH-, sus/jos sau stanga/dreapta.
       VERDE sau OK termina: config.misc.firstrun=False pe disc, asistentul se inchide si interfata deschide meniul
       principal (deschideMeniulPrincipal). EXIT sau ROSU: inapoi la pagina 1.
    Pe pagina 1, EXIT nu inchide asistentul: se iese numai prin pagina 2, cu limba salvata. Asistentul nu scrie nimic
    in setarile tunerului; antena, canalele si reteaua se fac din meniul principal.
    """
    skinName = "HdsStartWizard"

    skin = """
    <screen name="HdsStartWizard" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#0e1118">
        <eLabel position="0,0" size="1920,1080" backgroundColor="#0e1118" zPosition="0" />
        <eLabel position="72,50" size="1776,2" backgroundColor="#232936" zPosition="1" />
        <eLabel position="72,970" size="1776,2" backgroundColor="#232936" zPosition="1" />

        <widget source="Title" render="Label" position="72,60" size="1300,50" font="Bold;38" foregroundColor="#ffffff" backgroundColor="#0e1118" transparent="1" valign="center" zPosition="2" />
        <widget name="StepCounter" position="1400,60" size="448,50" font="Bold;30" foregroundColor="#2563eb" backgroundColor="#0e1118" transparent="1" halign="right" valign="center" zPosition="2" />
        <eLabel position="72,120" size="1776,1" backgroundColor="#1e2430" zPosition="1" />

        <widget name="StepTitle" position="72,145" size="1150,45" font="Bold;34" foregroundColor="#3b82f6" backgroundColor="#0e1118" transparent="1" valign="center" zPosition="2" />
        <widget name="StepDesc" position="72,195" size="1150,115" font="Regular;25" foregroundColor="#cbd5e1" backgroundColor="#0e1118" transparent="1" zPosition="2" />
        <eLabel position="72,318" size="1150,1" backgroundColor="#1e2430" zPosition="1" />

        <widget name="config" position="72,328" size="1150,135" itemHeight="60" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#0e1118" backgroundColorSelected="#1e3a8a" foregroundColorSelected="#ffffff" scrollbarMode="showNever" enableWrapAround="1" transparent="1" zPosition="2" />

        <!-- Chenarul de jos: pe pagina 2, functiile principale ale receptorului -->
        <eLabel position="72,475" size="1150,475" backgroundColor="#101522" zPosition="1" />
        <eLabel position="72,475" size="6,475" backgroundColor="#3b82f6" zPosition="2" />
        <eLabel position="78,475" size="1144,2" backgroundColor="#1e293b" zPosition="2" />
        <eLabel position="78,948" size="1144,2" backgroundColor="#1e293b" zPosition="2" />
        <eLabel position="1220,475" size="2,475" backgroundColor="#1e293b" zPosition="2" />

        <widget name="FeatureTitle" position="96,488" size="1100,36" font="Bold;26" foregroundColor="#60a5fa" backgroundColor="#101522" transparent="1" valign="center" zPosition="2" />
        <eLabel position="96,528" size="1100,1" backgroundColor="#1e293b" zPosition="2" />
        <widget name="FeatureText" position="96,538" size="1100,395" font="Regular;22" foregroundColor="#f1f5f9" backgroundColor="#101522" transparent="1" zPosition="2" />

        <!-- Panou informativ de asistenta (dreapta) -->
        <eLabel position="1250,140" size="1,810" backgroundColor="#1e2430" zPosition="1" />
        <widget name="HelpTitle" position="1280,145" size="568,45" font="Bold;28" foregroundColor="#3b82f6" backgroundColor="#0e1118" transparent="1" zPosition="2" />
        <widget name="HelpDesc" position="1280,200" size="568,340" font="Regular;23" foregroundColor="#cbd5e1" backgroundColor="#0e1118" transparent="1" zPosition="2" />
        <eLabel position="1280,560" size="568,1" backgroundColor="#1e2430" zPosition="1" />
        <widget name="BoxInfo" position="1280,580" size="568,180" font="Regular;21" foregroundColor="#64748b" backgroundColor="#0e1118" transparent="1" zPosition="2" />
        <widget name="rc" position="1370,770" size="380,180" alphatest="blend" zPosition="2" />
        <widget name="rc_glow_dpad" position="1370,770" size="380,180" alphatest="blend" zPosition="3" />
        <widget name="rc_glow_ok" position="1370,770" size="380,180" alphatest="blend" zPosition="3" />
        <widget name="rc_glow_colors" position="1370,770" size="380,180" alphatest="blend" zPosition="3" />

        <!-- Butoane colorate inferioare -->
        <eLabel position="72,990" size="6,40" backgroundColor="#ef4444" zPosition="2" />
        <widget source="key_red" render="Label" position="88,985" size="360,50" font="Regular;28" foregroundColor="#ffffff" backgroundColor="#0e1118" transparent="1" valign="center" zPosition="2" />

        <eLabel position="516,990" size="6,40" backgroundColor="#22c55e" zPosition="2" />
        <widget source="key_green" render="Label" position="532,985" size="360,50" font="Regular;28" foregroundColor="#ffffff" backgroundColor="#0e1118" transparent="1" valign="center" zPosition="2" />

        <eLabel position="960,990" size="6,40" backgroundColor="#eab308" zPosition="2" />
        <widget source="key_yellow" render="Label" position="976,985" size="360,50" font="Regular;28" foregroundColor="#ffffff" backgroundColor="#0e1118" transparent="1" valign="center" zPosition="2" />

        <eLabel position="1404,990" size="6,40" backgroundColor="#3b82f6" zPosition="2" />
        <widget source="key_blue" render="Label" position="1420,985" size="428,50" font="Regular;28" foregroundColor="#ffffff" backgroundColor="#0e1118" transparent="1" valign="center" zPosition="2" />
    </screen>
    """

    STEP_CONFIG = 1
    STEP_PREZENTARE = 2
    TOTAL_STEPS = 2

    def __init__(self, session):
        Screen.__init__(self, session)

        # Componente grafice cerute de skin-ul Full HD
        self["Title"] = StaticText("Asistent Configurare HD Satelit")
        self["ScreenPath"] = StaticText("")
        self["StepCounter"] = Label("")
        self["StepTitle"] = Label("")
        self["StepDesc"] = Label("")

        # Panou informativ de asistenta (dreapta)
        self["HelpTitle"] = Label("")
        self["HelpDesc"] = Label("")
        # HDSatelit: era text FIX, "Amiko Viper 4K /
        # HiSilicon Hi3798MV200", indiferent de hardware-ul real -- pe un al doilea model ar fi aratat
        # informatie GRESITA, nu doar generica. `Components.About.about` are deja detectie reala, testata
        # (`getReceiverName()`/`getChipset()`, cu fallback-uri corecte pentru orice alt model/emulator) --
        # refolosita aici, nu reinventata.
        # HDSatelit (continuare):
        # "HDR10" era ALT text fix, in aceeasi eticheta -- dar `hdmi_hdrtype_choices` NU
        # exista pe driverul acestui SoC (confirmat direct pe receptor), deci HDR nu e disponibil
        # niciodata aici -- afirmatia era falsa, nu doar negenerica. Verificat dinamic, cu acelasi mecanism
        # deja folosit de `VideoSetup.py`/`Components.VideoOutput` ("un buton apare doar daca driverul chiar
        # il ofera") -- daca driverul (acest SoC sau un altul, viitor) chiar expune HDR, textul il arata din
        # nou automat, fara alta interventie manuala.
        try:
            from Components.VideoOutput import VideoOutput as _VideoOutputProba
            _are_hdr = _VideoOutputProba().available("hdrtype")
        except Exception:
            _are_hdr = False
        # Fara „60 FPS”: iesirea ramane pe frecventa modului ales (lista ofera 50 si 60 Hz, implicit 1080p 50 Hz),
        # iar „Frecventa dupa canal” nu se ofera aici (VideoOutput.InitVideoOutput, implicit Nu).
        # „4K” numai daca driverul ofera un mod 2160p (inainte:
        # pe orice receptor), textul in limba aleasa (inainte numai romaneste) si creditele dupa regula casei (HD Satelit
        # coordoneaza, Monea Software programeaza), nu „Dezvoltat de hdsatelit.com”. Se rescrie la schimbarea limbii.
        self._are_hdr = _are_hdr
        self["BoxInfo"] = Label(self.textBoxInfo())

        # Chenarul de jos: pe pagina 1 ce urmeaza dupa configurare, pe pagina 2 functiile receptorului (derulare ScrollLabel)
        self["FeatureTitle"] = Label("")
        self["FeatureText"] = ScrollLabel("")

        # Telecomanda HD Satelit si indicatoare de taste active
        self["rc"] = Pixmap()
        self["rc_glow_dpad"] = Pixmap()
        self["rc_glow_ok"] = Pixmap()
        self["rc_glow_colors"] = Pixmap()

        # Butoane colorate: ROSU (inapoi) numai pe pagina 2, VERDE mai departe; galben si albastru nu se folosesc
        self["key_red"] = StaticText("")
        self["key_green"] = StaticText("Continuă")
        self["key_yellow"] = StaticText("")
        self["key_blue"] = StaticText("")

        # ConfigListScreen: pe pagina 1 limba si rezolutia, pe pagina 2 ce s-a ales (doar de citit)
        self.list = []
        ConfigListScreen.__init__(self, self.list, session=session)

        # pagina curenta (inainte de initWizardConfigs: notificarea limbii o citeste)
        self.currentStep = self.STEP_CONFIG
        self.initWizardConfigs()

        # Taste
        self["actions"] = ActionMap(
            ["SetupActions", "ColorActions", "DirectionActions", "OkCancelActions", "WizardActions", "ChannelSelectBaseActions"],
            {
                "ok": self.keyOK,
                "cancel": self.keyExit,
                "red": self.keyExit,
                "green": self.keyGreen,
                "save": self.keyGreen,          # VERDE in SetupActions
                "left": self.keyLeft,
                "right": self.keyRight,
                "up": self.keyUp,
                "down": self.keyDown,
                "upRepeated": self.keyUp,
                "downRepeated": self.keyDown,
                # ridicarea tastelor: nimic de facut, dar legate, ca jurnalul sa nu scrie „unknown action”
                "upUp": self.keyNimic,
                "downUp": self.keyNimic,
                "leftUp": self.keyNimic,
                "rightUp": self.keyNimic,
                "pageUp": self.scrollFeatureUp,
                "pageDown": self.scrollFeatureDown,
                "nextBouquet": self.scrollFeatureDown,
                "prevBouquet": self.scrollFeatureUp,
            },
            -2
        )

        self.onLayoutFinish.append(self.startWizard)

    def are4K(self):
        """Driverul ofera un mod 2160p (videomode_choices, prin Components/VideoOutput)."""
        try:
            vo = VideoOutputModule.videoOutput if VideoOutputModule is not None else None
            return bool(vo is not None and any(str(m).startswith("2160") for m in vo.choices.get("videomode", [])))
        except Exception:
            return False

    def textBoxInfo(self):
        """Panoul „Receptor / Chipset / Sistem”, in limba aleasa; video: HDR10 si 4K numai unde exista."""
        video = " | ".join((["HDR10"] if getattr(self, "_are_hdr", False) else []) +
            ["H.265 4K" if self.are4K() else "H.265"])
        return self.tr("box_info", about.getReceiverName(), about.getChipset(), video)

    def tr(self, key, *args):
        lang = getattr(self, "selected_lang", "ro_RO")
        texts = WIZARD_TRANSLATIONS.get(lang, WIZARD_TRANSLATIONS.get("en_EN", WIZARD_TRANSLATIONS["ro_RO"]))
        txt = texts.get(key, WIZARD_TRANSLATIONS["ro_RO"].get(key, key))
        if args:
            try:
                return txt.format(*args)
            except Exception:
                return txt
        return txt

    def updateBottomButtons(self):
        self["Title"].setText(self.tr("title"))
        if self.currentStep == self.STEP_PREZENTARE:
            self["key_red"].setText(self.tr("btn_back"))
            self["key_green"].setText(self.tr("btn_finish"))
        else:
            self["key_red"].setText("")
            self["key_green"].setText(self.tr("btn_next"))
        self["key_yellow"].setText("")
        self["key_blue"].setText("")

    def onLanguageChanged(self, configElement):
        """notificarea lui cfg_lang (la STANGA / DREAPTA si la alegerea din lista): limba se aplica pe loc, iar pagina
        se scrie din nou in limba aleasa"""
        self.selected_lang = configElement.value
        try:
            language.activateLanguage(self.selected_lang)
        except Exception as e:
            print("[HdsStartWizard] activateLanguage err:", e)
        if self.currentStep == self.STEP_CONFIG:
            self.setStep(self.STEP_CONFIG)
        else:
            self.updateBottomButtons()

    def initWizardConfigs(self):
        # 1. Toate limbile Enigma2 disponibile in sistem, cu Romana pe prima pozitie
        current_lang = language.getActiveLanguage()
        native_map = {
            "ro_RO": "Română (România)",
            "en_EN": "English (UK / US)",
            "de_DE": "Deutsch (Deutschland)",
            "hu_HU": "Magyar (Magyarország)",
            "fr_FR": "Français (France)",
            "it_IT": "Italiano (Italia)",
            "es_ES": "Español (España)",
            "ru_RU": "Русский (Россия)",
            "tr_TR": "Türkçe (Türkiye)",
            "el_GR": "Ελληνικά (Ελλάδα)",
            "pl_PL": "Polski (Polska)",
            "nl_NL": "Nederlands (Nederland)",
            "cs_CZ": "Čeština (Česká republika)",
            "sk_SK": "Slovenčina (Slovensko)",
            "hr_HR": "Hrvatski (Hrvatska)",
            "sr_YU": "Srpski (Srbija)",
            "bg_BG": "Български (България)",
            "uk_UA": "Українська (Україна)",
            "pt_PT": "Português (Portugal)",
            "da_DK": "Dansk (Danmark)",
            "sv_SE": "Svenska (Sverige)",
            "no_NO": "Norsk (Norge)",
            "fi_FI": "Suomi (Suomi)",
            # numele latin intai: prima litera tare e stanga-dreapta, deci randul se aliniaza la stanga ca celelalte
            # (un paragraf care incepe cu o litera araba e aliniat la dreapta de lib/gdi/font.cpp)
            "ar_AE": "Arabic (العربية)",
            "ca_AD": "Català (Andorra)",
            "et_EE": "Eesti (Eesti)",
            "fy_x-FY": "Frysk (Nederlân)",
            "is_IS": "Íslenska (Ísland)",
            "lv_LV": "Latviešu (Latvija)",
            "lt_LT": "Lietuvių (Lietuva)",
            "sl_SI": "Slovenščina (Slovenija)",
        }

        lang_choices = []
        try:
            raw_langs = language.getLanguageList()
            for item in raw_langs:
                code = item[0]
                name = native_map.get(code, item[1][0] if len(item[1]) > 0 else code)
                if code != "ro_RO":
                    lang_choices.append((code, name))
        except Exception as e:
            print("[HdsStartWizard] Eroare getLanguageList:", e)

        if not lang_choices:
            for c, n in [("en_EN", "English"), ("de_DE", "Deutsch"), ("hu_HU", "Magyar")]:
                lang_choices.append((c, n))

        lang_choices.sort(key=lambda x: cheieSortare(x[1]))
        lang_choices.insert(0, ("ro_RO", native_map["ro_RO"]))

        chosen_default = "ro_RO"
        self.selected_lang = chosen_default
        try:
            language.activateLanguage("ro_RO")
        except Exception:
            pass
        self.cfg_lang = ConfigSelection(default=chosen_default, choices=lang_choices)
        self.cfg_lang.addNotifier(self.onLanguageChanged, initial_call=False)

        # 2. Video: 2160p, 1080p, 1080i si 720p la 50 si 60 Hz, numai cele oferite de driver si acceptate de televizor
        # (screenModes, cu videomode_preferred citit din nou: televizorul poate fi pornit dupa receptor), in ordinea
        # din Setari > Video, plus modul deja ales acolo (config.av.hds_videomode), care e si cel luminat; alegerea se
        # salveaza in config si ramane dupa zap si dupa repornire. Etichetele sunt aceleasi in orice limba
        # (VideoOutput.modeLabel); „Recomandat” e in ajutor. Fara iesire video (probele de pe PC): lista de rezerva.
        video_current = None
        video_choices = []
        vo = VideoOutputModule.videoOutput if VideoOutputModule is not None else None
        if vo is not None:
            el = VideoOutputModule.configElement("hds_videomode")
            video_current = el.value if el is not None else None
            keep = [video_current] if video_current else []
            vo.readPreferred()
            modes = VideoOutputModule.wizardModes(vo.screenModes(keep), keep)
            video_choices = [(m, VideoOutputModule.modeLabel(m)) for m in modes or vo.screenModes(keep)]
        if not video_choices:
            video_choices = list(REZOLUTII_REZERVA)
        coduri = [c[0] for c in video_choices]
        if video_current not in coduri:
            video_current = REZOLUTIE_IMPLICITA if REZOLUTIE_IMPLICITA in coduri else coduri[0]
        self.cfg_videomode = ConfigSelection(default=video_current, choices=video_choices)

    def startWizard(self):
        print("[HdsStartWizard] pagina 1: limba si rezolutia")
        self.setStep(self.STEP_CONFIG)

    @staticmethod
    def valoareFixa(cfg):
        """rand doar de citit pentru pagina 2: o alegere cu o singura valoare, cea aleasa (STANGA / DREAPTA nu schimba nimic)"""
        return ConfigSelection(choices=[(cfg.value, cfg.getText())])

    def setStep(self, step):
        """scrie pagina `step` (STEP_CONFIG sau STEP_PREZENTARE) in limba aleasa"""
        self.currentStep = step
        self.updateBottomButtons()
        pagina = "page%d_" % step
        self["StepCounter"].setText(self.tr("step_counter", step, self.TOTAL_STEPS))
        self["StepTitle"].setText(self.tr(pagina + "title"))
        self["StepDesc"].setText(self.tr(pagina + "desc"))
        self["HelpTitle"].setText(self.tr(pagina + "help_title"))
        self["HelpDesc"].setText(self.tr(pagina + "help_desc"))
        self["BoxInfo"].setText(self.textBoxInfo())
        self.setGlow(dpad=True, ok=True, colors=True)

        if step == self.STEP_CONFIG:
            # sus limba, jos rezolutia; OK deschide lista valorilor, STANGA / DREAPTA trece la valoarea urmatoare
            self.list = [
                getConfigListEntry(self.tr("entry_lang"), self.cfg_lang),
                getConfigListEntry(self.tr("entry_video"), self.cfg_videomode),
            ]
            self["FeatureTitle"].setText(self.tr("page1_feature_title"))
            self["FeatureText"].setText(self.tr("page1_feature_desc"))
        else:
            # ce s-a ales, fara rand luminat, si functiile principale ale receptorului, de la inceputul listei.
            # 0.2.8: lista unica din Components/HdsFunctii.py (aceeasi in "Despre imagine" si in web), pe grupe, in
            # limba aleasa (po, 13 limbi); "(netestat)" si "in lucru" dupa data/menu.xml; fara acolade (nu trece prin
            # .format()).
            self.list = [
                getConfigListEntry(self.tr("entry_lang"), self.valoareFixa(self.cfg_lang)),
                getConfigListEntry(self.tr("entry_video"), self.valoareFixa(self.cfg_videomode)),
            ]
            titlu, functii = listaFunctii()
            self["FeatureTitle"].setText(titlu)
            self["FeatureText"].setText(functii)

        self["config"].list = self.list
        self["config"].l.setList(self.list)
        if hasattr(self["config"].l, "setSeperation"):
            self["config"].l.setSeperation(400)
        if self["config"].instance is not None:
            self["config"].instance.setSelectionEnable(1 if step == self.STEP_CONFIG else 0)
            self["config"].instance.moveSelectionTo(0)
        self.potrivesteTextulMarit()

    def potrivesteTextulMarit(self):
        """Cu textul marit (Marimea textului peste 100 %, Components/HdsMarireText): descrierea pasului creste cat ii
        trebuie (al treilea rand se taia jos de la 110 %), iar lista si chenarul de jos coboara (chenarul se strange, textul
        lui se deruleaza); in dreapta, ajutorul creste cat ii trebuie si caseta receptorului coboara, dar ii raman cel
        putin trei randuri; cand ajutorul tot nu incape, fontul lui scade (nu sub marimea de la 100 %), iar ce nu mai
        incape in caseta receptorului se taie dupa ultimul cuvant, cu "...". La 100 % nu se schimba nimic."""
        try:
            from Components import HdsMarireText as M
            if not M.marit() or self.instance is None:
                return
            if getattr(self, "_asezare", None) is None:
                self._asezare = M.Asezare(self)
            a = self._asezare
            a.refa()
            desc = self["StepDesc"].instance
            jos = a.cuprinde(self["FeatureText"].instance) or a.dinSkin(self["FeatureText"].instance)
            sk = a.dinSkin(desc)
            if jos and sk:
                a.creste(desc, M.inaltimeText(desc), jos[1] + jos[3], maxim=jos[3] // 3)
            ajutor, info = self["HelpDesc"].instance, self["BoxInfo"].instance
            skA, skI, panou = a.dinSkin(ajutor), a.dinSkin(info), a.cuprinde(info)
            if skA and skI:
                if panou is None or panou[3] > 2 * skI[3]:
                    panou = skI     # fara panou propriu (cel gasit e fundalul ferestrei)
                margine = panou[1] + panou[3]
                rest = (skI[1] - panou[1]) + (margine - skI[1] - skI[3]) + (panou[1] - skA[1] - skA[3])
                textInfo = self.textBoxInfo()
                self["BoxInfo"].setText(textInfo)
                minimInfo = min(M.inaltimeText(info), M.marimeFont(info) * 3 * 14 // 10 + 4)
                loc = margine - skA[1] - rest - minimInfo
                d = a.creste(ajutor, min(M.inaltimeText(ajutor), loc), margine)
                # cand nici asa nu incape (125-130 %), fontul ajutorului scade, dar nu sub marimea de la 100 %
                M.potrivesteFont(ajutor, skA[3] + d, a.marimeSkin(ajutor))
                textAjutor = self["HelpDesc"].getText()
                self["HelpDesc"].setText(M.scurtatPeInaltime(ajutor, textAjutor, skA[3] + d))
                self["BoxInfo"].setText(M.scurtatPeInaltime(info, textInfo, skI[3] - d))
        except Exception as e:
            print("[HdsStartWizard] textul marit: %s" % e)

    def setGlow(self, dpad=False, ok=False, colors=False):
        try:
            if "rc_glow_dpad" in self and self["rc_glow_dpad"].instance:
                if dpad:
                    self["rc_glow_dpad"].show()
                else:
                    self["rc_glow_dpad"].hide()

            if "rc_glow_ok" in self and self["rc_glow_ok"].instance:
                if ok:
                    self["rc_glow_ok"].show()
                else:
                    self["rc_glow_ok"].hide()

            if "rc_glow_colors" in self and self["rc_glow_colors"].instance:
                if colors:
                    self["rc_glow_colors"].show()
                else:
                    self["rc_glow_colors"].hide()
        except Exception as e:
            print("[HdsStartWizard] setGlow error:", e)

    def salveazaLimba(self):
        """limba aleasa pe pagina 1: activata si scrisa pe disc (config.osd.language)"""
        chosen = self.cfg_lang.value
        try:
            language.activateLanguage(chosen)
        except Exception as e:
            print("[HdsStartWizard] activateLanguage err:", e)
        config.osd.language.value = chosen
        config.osd.language.save()
        configfile.save()

    def salveazaVideo(self):
        """rezolutia aleasa pe pagina 1 (confirmata sau neschimbata): in config.av.hds_videomode si pe disc"""
        # prin config.av.hds_videomode: modul intra in cele trei fisiere videomode_50hz/60hz/24hz (videomode
        # doar ca rezerva), se salveaza (configfile.save() mai jos) si se aplica din nou la
        # fiecare pornire. „Frecventa dupa canal” nu se ofera aici: ramane cum e (implicit Nu)
        mode = self.cfg_videomode.value
        vo = VideoOutputModule.videoOutput if VideoOutputModule is not None else None
        try:
            el = VideoOutputModule.configElement("hds_videomode") if vo is not None else None
            if el is None:
                print("[HdsStartWizard] fara iesire video, modul %s nu se aplica" % mode)
            elif el.value != mode:
                if not vo.setMode(mode):
                    print("[HdsStartWizard] modul %s nu a putut fi aplicat" % mode)
            else:
                el.save()
        except Exception as e:
            print("[HdsStartWizard] VideoOutput apply error:", e)
        configfile.save()

    def keyOK(self):
        if self.currentStep == self.STEP_PREZENTARE:
            self.finishWizard()
            return
        cur = self["config"].getCurrent()
        if cur and len(cur) > 1 and isinstance(cur[1], ConfigSelection):
            self.openSelectionDropdown(cur[1])
        else:
            self.keyGreen()

    def openSelectionDropdown(self, cfg):
        choices_list = []
        current_idx = 0
        idx = 0
        raw_choices = getattr(cfg.choices, "choices", cfg.choices)
        if isinstance(raw_choices, list) and raw_choices and isinstance(raw_choices[0], tuple) and len(raw_choices[0]) >= 2:
            for item in raw_choices:
                val, name = item[0], item[1]
                choices_list.append((str(name), val))
                if val == cfg.value:
                    current_idx = idx
                idx += 1
        elif isinstance(raw_choices, dict):
            for val, name in raw_choices.items():
                choices_list.append((str(name), val))
                if val == cfg.value:
                    current_idx = idx
                idx += 1
        else:
            for val in cfg.choices:
                name = str(cfg.description[val]) if hasattr(cfg, "description") else str(val)
                choices_list.append((name, val))
                if val == cfg.value:
                    current_idx = idx
                idx += 1

        def onSelected(choice):
            if choice:
                val = choice[1]
                # limba: notificarea lui cfg_lang (onLanguageChanged) aplica limba si rescrie pagina
                cfg.setValue(val)
                self["config"].invalidateCurrent()

        self.session.openWithCallback(
            onSelected,
            _listaAlegerilor(),
            title=self.tr("entry_lang") if cfg == self.cfg_lang else self.tr("entry_video"),
            list=choices_list,
            selection=current_idx
        )

    def keyLeft(self):
        if self.currentStep == self.STEP_PREZENTARE:
            self.scrollFeatureUp()
        else:
            # limba: notificarea lui cfg_lang (onLanguageChanged) aplica limba si rescrie pagina
            ConfigListScreen.keyLeft(self)

    def keyRight(self):
        if self.currentStep == self.STEP_PREZENTARE:
            self.scrollFeatureDown()
        else:
            ConfigListScreen.keyRight(self)

    def keyUp(self):
        if self.currentStep == self.STEP_PREZENTARE:
            self.scrollFeatureUp()
        elif self["config"].instance is not None:
            self["config"].instance.moveSelection(self["config"].instance.moveUp)

    def keyDown(self):
        if self.currentStep == self.STEP_PREZENTARE:
            self.scrollFeatureDown()
        elif self["config"].instance is not None:
            self["config"].instance.moveSelection(self["config"].instance.moveDown)

    def keyGreen(self):
        if self.currentStep == self.STEP_PREZENTARE:
            self.finishWizard()
            return
        # pagina 1: limba se salveaza oricum; o rezolutie noua numai dupa confirmare (continua in videoConfirmed)
        self.salveazaLimba()
        if self.askVideoMode():
            return
        self.salveazaVideo()
        self.setStep(self.STEP_PREZENTARE)

    def keyNimic(self):
        pass

    def keyExit(self):
        """EXIT si ROSU: pe pagina 2 inapoi la configurare; pe pagina 1 asistentul ramane pe ecran (se termina numai
        prin pagina 2, dupa ce limba s-a salvat)"""
        if self.currentStep == self.STEP_PREZENTARE:
            self.setStep(self.STEP_CONFIG)

    def askVideoMode(self):
        """un mod nou se incearca pe televizor si se pastreaza doar cu Da (ca in Setari > Video): un televizor
        care nu accepta modul ramane negru, iar modul salvat s-ar aplica din nou la fiecare pornire.
        True daca s-a deschis intrebarea sau mesajul ca driverul a refuzat modul (pasul ramane pe ecran)."""
        vo = VideoOutputModule.videoOutput if VideoOutputModule is not None else None
        el = VideoOutputModule.configElement("hds_videomode") if vo is not None else None
        mode = self.cfg_videomode.value
        if el is None or el.value == mode or mode not in vo.choices.get("videomode", []):
            return False
        from Screens.MessageBox import MessageBox
        rate = VideoOutputModule.configElement(vo.RATE_ATTR)
        self.videoPrevious = vo.snapshot()
        vo.apply({"videomode": mode, "rate_by_channel": rate is not None and rate.value})
        if vo.lastModeReached is False:
            # driverul a refuzat fisierele: imaginea nu s-a schimbat, deci nu se intreaba (un Da ar salva un mod
            # nevazut); fisierele revin, pasul ramane pe ecran
            vo.restore(self.videoPrevious)
            if el.value in self.cfg_videomode.choices:
                self.cfg_videomode.value = el.value
            self["config"].invalidateCurrent()
            self.session.open(MessageBox, _("The receiver did not accept the new video mode. The previous setting is back."), MessageBox.TYPE_INFO, timeout=5)
            return True
        # driverul foloseste fisierele noi abia la pornirea unui video: canalul care ruleaza porneste din nou,
        # ca modul nou sa se vada in timpul intrebarii; fara canal, intrebarea spune ca modul se aplica la
        # pornirea unui canal (si tot nu se salveaza fara Da)
        if VideoOutputModule.applyNow(self.session.nav, vo):
            text = _("Is the picture shown correctly?\nWithout an answer the previous setting comes back.")
        else:
            text = _("The new mode is used when a channel starts. Keep it?\nWithout an answer the previous setting comes back.")
        self.session.openWithCallback(self.videoConfirmed, MessageBox, text,
            MessageBox.TYPE_YESNO, timeout=VIDEO_CONFIRM_SECONDS, default=False)
        return True

    def videoConfirmed(self, answer):
        vo = VideoOutputModule.videoOutput
        el = VideoOutputModule.configElement("hds_videomode")
        if answer:
            # deja aplicat: doar in config si pe disc (salveazaVideo), apoi pagina 2
            mode = self.cfg_videomode.value
            if mode not in el.choices:
                # lista din Setari > Video tine doar ce accepta televizorul; modul ales intra in ea
                VideoOutputModule.updateModeChoices(False, (mode,), vo)
            el.value = mode
            self.salveazaVideo()
            self.setStep(self.STEP_PREZENTARE)
            return
        vo.restore(self.videoPrevious)
        # modul de dinainte se vede imediat (canalul porneste din nou)
        VideoOutputModule.applyNow(self.session.nav, vo)
        if el.value in self.cfg_videomode.choices:
            self.cfg_videomode.value = el.value
        self["config"].invalidateCurrent()
        from Screens.MessageBox import MessageBox
        self.session.open(MessageBox, _("The new video setting was not confirmed. The previous setting is back."), MessageBox.TYPE_INFO, timeout=5)

    def scrollFeatureUp(self):
        if "FeatureText" in self and hasattr(self["FeatureText"], "pageUp"):
            self["FeatureText"].pageUp()

    def scrollFeatureDown(self):
        if "FeatureText" in self and hasattr(self["FeatureText"], "pageDown"):
            self["FeatureText"].pageDown()

    def finishWizard(self):
        """VERDE sau OK pe pagina 2: semnele de prima pornire pe disc (asistentul nu mai porneste: StartWizard.py il
        inregistreaza pe config.misc.firstrun), apoi asistentul se inchide si interfata deschide meniul principal"""
        print("[HdsStartWizard] asistent terminat: firstrun=False, se deschide meniul principal")
        # ConfigSubsection.__getattr__ arunca KeyError pentru o cheie lipsa, deci se cauta in content.items
        for key in ("firstrun", "languageselected", "defaultchosen", "videowizardenabled"):
            item = config.misc.content.items.get(key)
            if item is not None:
                item.value = False
                item.save()
        configfile.save()
        deschideMeniulPrincipal()
        # fara valoare de intoarcere: runNextScreen din mytest.py ar opri interfata (quitMainloop) cu ea
        self.close()
