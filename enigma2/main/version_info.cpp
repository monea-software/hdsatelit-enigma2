#include "version_info.h"
#include "version.h"

#ifndef ENIGMA2_COMMIT_DATE
#define ENIGMA2_COMMIT_DATE __DATE__
#endif
const char *enigma2_date = ENIGMA2_COMMIT_DATE;

/* numele fix al constructiei (jurnalul unei caderi): numele ramurii git din care s-a construit nu intra in executabil */
const char *enigma2_branch = "hdsatelit";

#ifndef ENIGMA2_REV
#define ENIGMA2_REV ""
#endif
const char *enigma2_rev = ENIGMA2_REV;

