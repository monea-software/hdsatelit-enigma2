#include <lib/gdi/gmaindc.h>

gMainDC *gMainDC::m_instance;

ePtr<gMainDC> NewgMainDCPtr(void)
{
	ePtr<gMainDC> ptr;
	gMainDC::getInstance(ptr);
	return ptr;
}

gMainDC::gMainDC()
{
	ASSERT(m_instance == 0);
	m_instance = this;
}

gMainDC::gMainDC(gPixmap *pixmap) : gDC(pixmap)
{
	ASSERT(m_instance == 0);
	m_instance = this;
}

gMainDC::~gMainDC()
{
	m_instance = 0;
}


// HD Satelit: marimea suprafetei de desen de acum (skin.py vede asa daca driverul a refuzat rezolutia temei)
int gMainDC::resolutionX()
{
	return m_pixmap ? m_pixmap->size().width() : 0;
}

int gMainDC::resolutionY()
{
	return m_pixmap ? m_pixmap->size().height() : 0;
}
