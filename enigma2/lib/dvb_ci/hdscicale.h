/* HD Satelit (moneasoftware.com si hdsatelit.com, 2026): un canal criptat pe o singura cale, modulul CI din slot sau
   modulul de acces (softcam-ul legat de enigma2).
   In enigma2 OE-Alliance (si pana acum aici) un serviciu se inscrie mereu la modulul de acces (eDVBCAService), iar
   daca un modul CI il poate lua, il primeste si el: acelasi canal e decriptat pe doua cai deodata, iar pe unele
   modulele (CAM-ul cu cartela pusa si in slot, si in cititorul modulului de acces) imaginea ingheata.
   Cu optiunea config.cimisc.numai_ci pornita (Nu din fabrica, deci purtarea veche ramane), un canal luat de un modul
   CI nu se mai inscrie la modulul de acces (sau se scoate de acolo, daca modulul CI l-a luat mai tarziu), iar cand
   modulul CI pleaca (scos din slot) canalul se inscrie iar, fara zap. Hotararea e aici, ca sa se probeze si pe PC
   (teste/test_cip9_*.py compileaza antetul). */
#ifndef __hdscicale_h
#define __hdscicale_h

#include <string>

/* cheia setarii (Screens/Ci.py, InitCiConfig) si valoarea ei cand e pornita, asa cum o da ePythonConfigQuery */
#define HDS_CI_NUMAI_CI_CHEIE "config.cimisc.numai_ci"

enum hdsCaleCa
{
	HDS_CALE_LASA = 0,     /* nimic de schimbat la modulul de acces */
	HDS_CALE_INSCRIE = 1,  /* serviciul se inscrie la modulul de acces (purtarea veche) */
	HDS_CALE_RENUNTA = 2   /* serviciul inscris se scoate de la modulul de acces: il are modulul CI */
};

/* numai_ci: optiunea pornita; ci_alocat: un modul CI a luat serviciul (eDVBCIInterfaces::isHandlerAssigned);
   inscris: serviciul e deja inscris la modulul de acces */
static inline hdsCaleCa hdsCaleModulAcces(bool numai_ci, bool ci_alocat, bool inscris)
{
	if (numai_ci && ci_alocat)
		return inscris ? HDS_CALE_RENUNTA : HDS_CALE_LASA;
	return inscris ? HDS_CALE_LASA : HDS_CALE_INSCRIE;
}

/* setarea pornita, citita din memorie prin ePythonConfigQuery; fara sloturi CI e mereu oprita (lib/dvb_ci/dvbci.cpp) */
bool hdsNumaiCi();

/* valoarea setarii citita prin ePythonConfigQuery (ConfigYesNo da "True" / "False") */
static inline bool hdsNumaiCiPornit(const std::string &valoare)
{
	return valoare == "True";
}

#endif
