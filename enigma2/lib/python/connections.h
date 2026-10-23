/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_python_connections_h
#define __lib_python_connections_h

#include <libsig_comp.h>

#include <lib/python/python.h>

class PSignal
{
protected:
	ePyObject m_list;
public:
	PSignal();
	~PSignal();
	void callPython(SWIG_PYOBJECT(ePyObject) tuple);
#ifndef SWIG
	PyObject *getSteal(bool clear=false);
	/* HDSatelit: are macar o functie Python legata (eRCMapper nu opreste tastele fara ascultator) */
	bool hasPython() { return m_list && PyList_Size(m_list) > 0; }
#endif
	PyObject *get();
};

inline PyObject *PyFrom(int v)
{
	return PyLong_FromLong(v);
}

inline PyObject *PyFrom(const char *c)
{
	/* HDSatelit: un sir care nu e UTF-8 bun (de exemplu numele unui dispozitiv taiat la jumatatea
	   unui caracter) dadea NULL in tuplu; acum caracterele stricate se inlocuiesc, iar NULL nu mai iese */
	PyObject *r = c ? PyUnicode_DecodeUTF8(c, (Py_ssize_t)strlen(c), "replace") : NULL;
	if (!r)
	{
		PyErr_Clear();
		r = PyUnicode_FromString("");
	}
	return r;
}

template <class R>
class PSignal0: public PSignal, public sigc::signal<R()>
{
public:
	R operator()()
	{
		if (m_list)
		{
			PyObject *pArgs = PyTuple_New(0);
			callPython(pArgs);
			Org_Py_DECREF(pArgs);
		}
		return sigc::signal<R()>::operator()();
	}
};

template <class R, class V0>
class PSignal1: public PSignal, public sigc::signal<R(V0)>
{
public:
	R operator()(V0 a0)
	{
		if (m_list)
		{
			PyObject *pArgs = PyTuple_New(1);
			PyTuple_SET_ITEM(pArgs, 0, PyFrom(a0));
			callPython(pArgs);
			Org_Py_DECREF(pArgs);
		}
		return sigc::signal<R(V0)>::operator()(a0);
	}
};

template <class R, class V0, class V1>
class PSignal2: public PSignal, public sigc::signal<R(V0, V1)>
{
public:
	R operator()(V0 a0, V1 a1)
	{
		if (m_list)
		{
			PyObject *pArgs = PyTuple_New(2);
			PyTuple_SET_ITEM(pArgs, 0, PyFrom(a0));
			PyTuple_SET_ITEM(pArgs, 1, PyFrom(a1));
			callPython(pArgs);
			Org_Py_DECREF(pArgs);
		}
		return sigc::signal<R(V0, V1)>::operator()(a0, a1);
	}
};

template <class R, class V0, class V1, class V2>
class PSignal3: public PSignal, public sigc::signal<R(V0, V1, V2)>
{
public:
	R operator()(V0 a0, V1 a1, V2 a2)
	{
		if (m_list)
		{
			PyObject *pArgs = PyTuple_New(3);
			PyTuple_SET_ITEM(pArgs, 0, PyFrom(a0));
			PyTuple_SET_ITEM(pArgs, 1, PyFrom(a1));
			PyTuple_SET_ITEM(pArgs, 2, PyFrom(a2));
			callPython(pArgs);
			Org_Py_DECREF(pArgs);
		}
		return sigc::signal<R(V0, V1, V2)>::operator()(a0, a1, a2);
	}
};

#endif
