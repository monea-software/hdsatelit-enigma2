/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_driver_rcmapper_h
#define __lib_driver_rcmapper_h

/*
 * HDSatelit: telecomenzile asociate, cititorul de coduri si proba tastelor (ecranul
 * Screens/HdsTelecomenzi.py, datele in Components/HdsTelecomenziDate.py).
 *
 * Fiecare tasta trece prin process(), chemat din keyEvent() (main/enigma.cpp) dupa ce s-a facut apasarea
 * lunga, deci si "apasare lunga" ajunge in cititor:
 *  1. traducerea: (dispozitiv, cod) -> codul unui buton al telecomenzii receptorului, trimis mai departe cu
 *     numele dispozitivului nativ, ca toate blocurile <device name="dreambox advanced remote control (native)">
 *     din keymap.xml sa se potriveasca. Dispozitivele receptorului (numele incep cu "dreambox ") nu sunt
 *     niciodata traduse, deci o asociere gresita nu poate strica telecomanda receptorului. Fara asociere, un cod
 *     care e al unui buton Viper (KEY_UP, KEY_OK, KEY_CHANNELUP...) se trimite implicit ca de pe dispozitivul
 *     nativ (setDefaultViper), fiindca legaturile din keymap.xml trec din "generic" in blocuri pe dispozitivul
 *     nativ. Caracterele (flagAscii) nu se traduc niciodata.
 *  2. captura: tastele intra intr-o coada citita din Python (getEvents), iar rawKey anunta ecranul.
 *     captureAll (cititorul si proba de pe televizor) opreste toate tastele; captureOthers (asocierea) le
 *     opreste numai pe ale altor dispozitive, telecomanda receptorului merge normal; captureListen (pagina web)
 *     nu opreste nimic, numai asculta, cel mult 2 minute (vede si un PIN tastat pe televizor). Pagina web nu
 *     porneste niciodata captureAll. Captura e una singura: cine a pornit-o o atinge (touch) si o opreste;
 *     ecranul de pe televizor nu o ia pe a paginii web, iar pagina web nu o ia pe a ecranului.
 *     Iesirea din captureAll e aici, nu in ecran, si nu depinde de o singura tasta: EXIT, MENU sau ESC de doua
 *     ori in 2 secunde, de pe orice dispozitiv, sau orice tasta tinuta 3 secunde. Termenele (fara taste, total,
 *     semn de viata) le verifica un eTimer: apara de o greseala de logica in ecran si de un ecran inchis fara
 *     setCapture(0), nu si de o bucla principala blocata (acolo opreste paznicul enigma2, dupa 60 s).
 *     Fara niciun ascultator Python pe rawKey, captureAll si captureOthers nu pornesc.
 *     Eliberarea (si repetarile) unei taste apasate inainte de captura nu se arata si nu ajung nicaieri; la fel
 *     eliberarea unei taste apasate in captura, dupa oprirea ei.
 *     Coada exista numai cat e pornita o captura si se goleste la oprire (un PIN scris cu telecomanda nu ramane
 *     in memorie pentru pagina web).
 *  3. tastatura (eRCDevice::isKeyboard, neasociata): tastele care nu sunt butoane Viper primesc sensul lor de pe
 *     telecomanda (keyboardDefault): Enter = OK, Esc = IESIRE, Backspace = IESIRE cand nu se scrie text (kmNone),
 *     F1-F4 = culorile, F5 si tasta de meniu = MENIU, F6 = INFO, F7 = EPG, Spatiu = OK cand nu se scrie text,
 *     cifrele si +/- din dreapta = cifrele si volumul cand nu se scrie text. Tasta tine sensul de la apasare pana
 *     la eliberare (m_keyboardHeld), chiar daca ecranul schimba intre timp felul tastaturii.
 *  4. mouse-ul (eRCDeviceInputDev cu REL_X/REL_Y/BTN_LEFT): miscarea, rotita si cele trei butoane vin la noteMouse,
 *     se aduna pana la EV_SYN si intra intr-o coada (cel mult MAX_MOUSE pachete; pachetele la rand cu aceleasi
 *     butoane apasate se aduna intr-unul). mouseEvent anunta Python-ul cand coada nu mai e goala; getMouse() o
 *     da si o goleste (Components/HdsMouseUsb.py).
 */

#include <lib/base/ebase.h>
#include <lib/python/connections.h>
#include <string>

#ifndef SWIG
#include <deque>
#include <map>
#include <set>
#include <utility>

class eRCDevice;
#endif

class eRCMapper: public sigc::trackable
{
#ifdef SWIG
	eRCMapper();
	~eRCMapper();
#endif
#ifndef SWIG
	static eRCMapper *instance;

	typedef std::pair<std::string, int> Key;
	struct Event
	{
		int seq;
		long long ms;
		std::string device;
		int code, flags, target, scan;
	};

	std::map<Key, int> m_table;
	std::set<std::string> m_blockUnmapped;
	bool m_defaultViper;

	int m_mode;
	int m_idleSeconds, m_totalSeconds, m_heartbeatSeconds;
	long long m_start, m_lastKey, m_lastTouch;
	ePtr<eTimer> m_timer;
	std::set<Key> m_held;           /* tastele apasate in timpul capturii */
	std::set<Key> m_releaseWait;    /* tastele inca apasate la oprirea capturii */
	int m_lastExitCode;
	long long m_lastExitTime;
	Key m_holdKey;
	long long m_holdStart;
	bool m_holdDone;

	std::deque<Event> m_events;
	int m_seq;

	eRCDevice *m_scanProducer;
	int m_scan;

	std::map<int, int> m_keyboardHeld;  /* tasta de tastatura apasata -> sensul primit la apasare */
	int keyboardTarget(int code, int flags);

	struct MousePacket
	{
		int dx, dy, wheel, buttons;
	};
	std::deque<MousePacket> m_mouse;
	int m_mouseDx, m_mouseDy, m_mouseWheel, m_mouseButtons;
	bool m_mousePending;
	bool m_lastKeyboard;                /* ultima tasta apasata (sau caracterul) a venit de la o tastatura */

	void onTimer();
	void stopCapture(int reason);
	bool swallowsDevice(const std::string &device) const;
#endif
public:
#ifndef SWIG
	eRCMapper();
	~eRCMapper();
	static long long now();
	/* din keyEvent(): true = tasta nu merge mai departe; altfel device si code sunt cele de dat lui eActionMap */
	bool process(eRCDevice *producer, std::string &device, int &code, int flags);
	/* din eRCDeviceInputDev::handleCode: codul brut EV_MSC/MSC_SCAN care vine inaintea tastei */
	void noteScan(eRCDevice *producer, int value);
	/* din eRCDeviceInputDev: o tastatura asociata ca telecomanda (tastele neasociate oprite) se ia exclusiv si
	   nu i se filtreaza codurile in kmAscii; codurile asociate ale unei tastaturi nu se filtreaza nici ele */
	bool isRemote(const std::string &device) const;
	bool isMapped(const std::string &device, int code) const;
	static bool isOwnDevice(const std::string &device);
	static bool isViperCode(int code);
	/* sensul de pe telecomanda al unei taste de tastatura care nu e buton Viper (-1 niciunul); keyboardMode = kmNone,
	   kmAscii ... (eRCInput) */
	static int keyboardDefault(int code, int keyboardMode);
	/* din eRCDeviceInputDev::handleCode, pentru un mouse: EV_REL, butoanele (EV_KEY BTN_*) si EV_SYN */
	void noteMouse(int type, int code, int value);
#endif
	static eRCMapper *getInstance();

	enum { captureOff, captureAll, captureOthers, captureListen };
	enum { endRequested, endIdle, endTotal, endExitKeys, endHold, endHeartbeat };

	/* tabelul, pus din Python (HdsTelecomenziDate.incarca_in_mapper); apply() reia luarea exclusiva a
	   dispozitivelor dupa ce s-a schimbat tabelul */
	void clear();
	void add(const std::string &device, int code, int targetCode);
	void setBlockUnmapped(const std::string &device, bool block);
	void setDefaultViper(bool on);
	void apply();
	int getTableSize();

	/* mod: capture*; secundele: 0 = fara termenul acela (captureListen are oricum cel mult 120 s in total);
	   heartbeatSeconds > 0 cere touch() mai des de atat */
	int setCapture(int mode, int idleSeconds, int totalSeconds, int heartbeatSeconds);
	int getCaptureMode();
	int getCaptureSecondsLeft();
	void touch();

	/* evenimentele cu numarul mai mare decat afterSequence: lista de tupluri
	   (numar, ms, dispozitiv, cod, fel, tinta, scan); tinta = codul Viper in care se traduce (-1 niciunul),
	   scan = codul brut MSC_SCAN (-1 niciunul) */
	PyObject *getEvents(int afterSequence);
	int getLastSequence();
	/* numele dispozitivelor de intrare deschise acum, fara dubluri */
	PyObject *getDevices();

	/* o tasta ca de pe telecomanda receptorului (telecomanda virtuala din web): prin keyEvent(), deci cu
	   apasare lunga; pe un receptor fara dispozitivul nativ (emulatorul), direct la eActionMap */
	void inject(int code, int flags);

	/* pachetele mouse-ului venite de la ultima chemare, apoi coada se goleste: lista de tupluri
	   (dx, dy, rotita, butoane); rotita > 0 = spre ecran (in sus), butoane = 1 stanga | 2 dreapta | 4 mijloc, cum
	   sunt tinute dupa pachet */
	PyObject *getMouse();
	/* ultima tasta apasata a venit de la o tastatura (si caracterele consolei); telecomanda, panoul, pagina web si
	   mouse-ul (inject) dau false. Tastatura de pe ecran nu-si mai arata tastele cand e deschisa de la tastatura. */
	bool lastKeyFromKeyboard();

	PSignal1<void, int> rawKey;          /* numarul ultimului eveniment pus in coada */
	PSignal1<void, int> captureEnded;    /* motivul opririi (end*) */
	PSignal1<void, int> mouseEvent;      /* coada mouse-ului nu mai e goala (cate pachete are) */
};

#endif
