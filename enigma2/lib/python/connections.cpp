/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/python/connections.h>

PSignal::PSignal()
{
}

PSignal::~PSignal()
{
	/* objects destroyed at process exit can outlive Py_Finalize: never touch Python then */
	if (Py_IsInitialized())
		Py_XDECREF(m_list);
}

void PSignal::callPython(ePyObject tuple)
{
	/* HDSatelit: se merge pe o copie a listei (un tuplu care tine cate o referinta la fiecare functie).
	   Pe lista vie, cu lungimea luata o singura data, o functie care se scotea pe sine sau pe alta din lista in
	   timpul chemarii facea ca alta functie sa fie chemata de doua ori, sau ca bucla sa citeasca dupa capatul
	   listei si sa cheme un obiect eliberat (revizia Telecomenzi, P24: rawKey si captureEnded pot avea doua
	   ascultatoare, ecranul si pagina web). Acum fiecare functie din lista de la inceputul semnalului e chemata o
	   singura data si ramane in viata pana la capat; una adaugata in timpul chemarii intra de la semnalul urmator. */
	if (!m_list)
		return;
	ePyObject copy = PyList_AsTuple(m_list);
	if (!copy)
	{
		PyErr_Clear();
		return;
	}
	Py_ssize_t size = PyTuple_GET_SIZE(copy);
	for (Py_ssize_t i = 0; i < size; ++i)
	{
		ePyObject b = PyTuple_GET_ITEM(copy, i);
		ePython::call(b, tuple);
	}
	Py_DECREF(copy);
}

PyObject *PSignal::get()
{
	if (!m_list)
		m_list = PyList_New(0);
	Py_INCREF(m_list);
	return m_list;
}

PyObject *PSignal::getSteal(bool clear)
{
	if (clear)
	{
		ePyObject ret = m_list;
		m_list = (PyObject*)0;
		return ret;
	}
	return m_list;
}
