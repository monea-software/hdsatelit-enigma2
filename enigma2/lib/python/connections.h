/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_python_connections_h
#define __lib_python_connections_h

#include <libsig_comp.h>
#include <utility>
#include <initializer_list>

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
		if (PyErr_Occurred())
			PyErr_Print();
		r = PyUnicode_FromString("");
	}
	return r;
}

/* HDSatelit: the output of a console program (eConsoleAppContainer) goes to Python as bytes with the length read, like
   on the other Python 3 images: the plugins written for them do data.decode() or b"" + data, and the data can hold
   zero bytes (a picture) or a UTF-8 character cut between two reads. */
inline PyObject *PyFrom(const std::pair<const char*, int> &p)
{
	PyObject *r = PyBytes_FromStringAndSize(p.first, p.first && p.second > 0 ? p.second : 0);
	if (!r)
	{
		if (PyErr_Occurred())
			PyErr_Print();
		r = PyBytes_FromStringAndSize("", 0);
	}
	return r;
}

/* Ia referintele valorilor. Un esec nu ajunge ca NULL in callback. */
inline PyObject *signalArgs(std::initializer_list<PyObject *> values)
{
	PyObject *args = PyTuple_New(values.size());
	bool ok = args != NULL;
	Py_ssize_t index = 0;
	for (PyObject *value : values)
	{
		if (args && value)
			PyTuple_SET_ITEM(args, index, value);
		else if (value)
			Org_Py_DECREF(value);
		if (!value)
			ok = false;
		++index;
	}
	if (!ok)
	{
		if (args)
			Org_Py_DECREF(args);
		if (PyErr_Occurred())
			PyErr_Print();
		return NULL;
	}
	return args;
}

template <class R>
class PSignal0: public PSignal, public sigc::signal<R()>
{
public:
	R operator()()
	{
		if (m_list)
		{
			PyObject *pArgs = signalArgs({});
			if (pArgs)
			{
				callPython(pArgs);
				Org_Py_DECREF(pArgs);
			}
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
			PyObject *pArgs = signalArgs({PyFrom(a0)});
			if (pArgs)
			{
				callPython(pArgs);
				Org_Py_DECREF(pArgs);
			}
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
			PyObject *pArgs = signalArgs({PyFrom(a0), PyFrom(a1)});
			if (pArgs)
			{
				callPython(pArgs);
				Org_Py_DECREF(pArgs);
			}
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
			PyObject *pArgs = signalArgs({PyFrom(a0), PyFrom(a1), PyFrom(a2)});
			if (pArgs)
			{
				callPython(pArgs);
				Org_Py_DECREF(pArgs);
			}
		}
		return sigc::signal<R(V0, V1, V2)>::operator()(a0, a1, a2);
	}
};

#endif
