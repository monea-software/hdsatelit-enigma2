/* SoftCSA (software descrambling of CSA-ALT with libdvbcsa). GPL-2.0-only.
 * Authors: WXbet, Betacentauri, 2026.
 * Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __iservicescrambled_h
#define __iservicescrambled_h

#include <lib/base/object.h>

/**
 * iServiceScrambled - Interface for software descrambling
 *
 * Implemented by eDVBCSASession to provide descrambling
 * callback for eDVBTSRecorder.
 */
class iServiceScrambled: public iObject
{
public:
	/**
	 * Descramble packets in-place
	 * @param packets TS packet buffer
	 * @param len Buffer length in bytes
	 *
	 * When active and CW available: descrambles in-place
	 * Otherwise: passthrough (no changes to data)
	 */
	virtual void descramble(unsigned char*, int) = 0;
	virtual bool hasKeys() const { return true; }
};

#endif // __iservicescrambled_h
