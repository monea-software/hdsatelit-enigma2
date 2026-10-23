/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_base_xmltree_h
#define __lib_base_xmltree_h

/*
 * Arbore XML minimal peste libxml2, pentru citirea fisierelor satellites.xml,
 * cables.xml si terrestrial.xml. Pastreaza forma folosita de codul existent:
 * elementele si atributele se parcurg ca liste de pointeri.
 */

#include <string>
#include <list>
#include <libxml/parser.h>
#include <libxml/tree.h>

namespace xmltree {

class Attribute
{
	std::string m_name, m_value;
public:
	Attribute(const std::string &name, const std::string &value): m_name(name), m_value(value) { }
	const std::string &name() const { return m_name; }
	const std::string &value() const { return m_value; }
};

class Element;
typedef std::list<Element *> ElementList;
typedef ElementList::const_iterator ElementConstIterator;
typedef std::list<Attribute *> AttributeList;
typedef AttributeList::const_iterator AttributeConstIterator;

class Element
{
	std::string m_name;
	ElementList m_elements;
	AttributeList m_attributes;
public:
	explicit Element(xmlNodePtr node)
	{
		if (node->name)
			m_name = (const char *)node->name;
		for (xmlAttrPtr a = node->properties; a; a = a->next)
		{
			xmlChar *v = xmlNodeListGetString(node->doc, a->children, 1);
			m_attributes.push_back(new Attribute((const char *)a->name, v ? (const char *)v : ""));
			if (v)
				xmlFree(v);
		}
		for (xmlNodePtr c = node->children; c; c = c->next)
			if (c->type == XML_ELEMENT_NODE)
				m_elements.push_back(new Element(c));
	}
	~Element()
	{
		for (ElementConstIterator it = m_elements.begin(); it != m_elements.end(); ++it)
			delete *it;
		for (AttributeConstIterator it = m_attributes.begin(); it != m_attributes.end(); ++it)
			delete *it;
	}
	Element(const Element &) = delete;
	Element &operator=(const Element &) = delete;
	const std::string &name() const { return m_name; }
	const ElementList &getElementList() const { return m_elements; }
	const AttributeList &getAttributeList() const { return m_attributes; }
};

class XMLTree
{
	std::string m_filename;
	Element *m_root;
public:
	XMLTree(): m_root(0) { }
	~XMLTree() { delete m_root; }
	XMLTree(const XMLTree &) = delete;
	XMLTree &operator=(const XMLTree &) = delete;
	void setFilename(const std::string &filename) { m_filename = filename; }
	bool read()
	{
		delete m_root;
		m_root = 0;
		xmlDocPtr doc = xmlReadFile(m_filename.c_str(), NULL, XML_PARSE_NONET | XML_PARSE_NOBLANKS);
		if (!doc)
			return false;
		xmlNodePtr root = xmlDocGetRootElement(doc);
		if (root)
			m_root = new Element(root);
		xmlFreeDoc(doc);
		return m_root != 0;
	}
	Element *getRoot() { return m_root; }
};

}

#endif
