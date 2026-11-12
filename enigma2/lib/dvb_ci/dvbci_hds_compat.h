/* HD Satelit (moneasoftware.com si hdsatelit.com, 2026): numele de jurnal folosite de codul CI+ luat din sursele GPL
   enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, puse pe jurnalul nostru (lib/base/eerror.h).
   eTrace* este urmarirea octet cu octet a mesajelor modulului: la noi nu se scrie (jurnalul ar creste fara folos). */
#ifndef __dvbci_hds_compat_h
#define __dvbci_hds_compat_h

#include <lib/base/eerror.h>

#ifndef eTrace
#define eTrace(...) do { } while (0)
#endif
#ifndef eTraceNoNewLine
#define eTraceNoNewLine(...) do { } while (0)
#endif
#ifndef eTraceNoNewLineStart
#define eTraceNoNewLineStart(...) do { } while (0)
#endif
#ifndef eDebugNoNewLineStart
#define eDebugNoNewLineStart eDebugNoNewLine
#endif

#endif
