/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __LIBSIG_COMP_H
#define __LIBSIG_COMP_H

#include <sigc++/sigc++.h>

/* Leaga un semnal de o metoda a obiectului curent:
 *   void bla::foo(int x);
 *   sigc::signal<void(int)> testSig;
 *   CONNECT(testSig, bla::foo);
 * Semnalul si metoda trebuie sa aiba aceeasi semnatura.
 */
#define CONNECT(SENDER, EMPFAENGER) SENDER.connect(sigc::mem_fun(*this, &EMPFAENGER))

#endif // __LIBSIG_COMP_H
