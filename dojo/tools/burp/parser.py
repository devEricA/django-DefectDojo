"""
Faraday Penetration Test IDE
Copyright (C) 2013  Infobyte LLC (http://www.infobytesec.com/)
See the file 'doc/LICENSE' for the license information

"""
from __future__ import with_statement
from urlparse import urlparse

import re
# from defusedxml import ElementTree as etree
from lxml import etree
import html2text
import string

from dojo.models import Finding, Endpoint

__author__ = "Francisco Amato"
__copyright__ = "Copyright (c) 2013, Infobyte LLC"
__credits__ = ["Francisco Amato"]
__license__ = ""
__version__ = "1.0.0"
__maintainer__ = "Francisco Amato"
__email__ = "famato@infobytesec.com"
__status__ = "Development"


class BurpXmlParser(object):
    """
    The objective of this class is to parse an xml file generated by the burp tool.

    TODO: Handle errors.
    TODO: Test burp output version. Handle what happens if the parser doesn't support it.
    TODO: Test cases.

    @param xml_output A proper xml generated by burp
    @param test A Dojo Test object
    """

    def __init__(self, xml_output, test):
        self.target = None
        self.port = "80"
        self.host = None

        tree = self.parse_xml(xml_output)
        if tree is not None:
            self.items = [data for data in self.get_items(tree, test)]
        else:
            self.items = []

    def parse_xml(self, xml_file):
        """
        Open and parse an xml file.

        TODO: Write custom parser to just read the nodes that we need instead of
        reading the whole file.

        @return xml_tree An xml tree instance. None if error.
        """

        tree = None
        try:
            tree = etree.parse(xml_file, etree.XMLParser(resolve_entities=False))
        except Exception, e:
            # Solution to remove unicode characters in xml, tried several
            xml_file.seek(0)
            data = xml_file.read()
            printable = set(string.printable)
            data = filter(lambda x: x in printable, data)
            tree = etree.fromstring(data, etree.XMLParser(encoding='ISO-8859-1', ns_clean=True, recover=True, resolve_entities=False))

        return tree

    def get_items(self, tree, test):
        """
        @return items A list of Host instances
        """
        bugtype = ""
        items = {}

        for node in tree.findall('issue'):
            item = get_item(node, test)
            dupe_key = str(item.url) + item.severity + item.title
            if dupe_key in items:
                items[dupe_key].unsaved_endpoints = items[dupe_key].unsaved_endpoints + item.unsaved_endpoints
                items[dupe_key].unsaved_req_resp = items[dupe_key].unsaved_req_resp + item.unsaved_req_resp
                # make sure only unique endpoints are retained
                unique_objs = []
                new_list = []
                for o in items[dupe_key].unsaved_endpoints:
                    if o.__unicode__() in unique_objs:
                        continue
                    new_list.append(o)
                    unique_objs.append(o.__unicode__())

                items[dupe_key].unsaved_endpoints = new_list

                # Description details of the finding are added
                items[dupe_key].description = item.description + items[dupe_key].description

                # Parameters of the finding are added
                if items[dupe_key].param and items[dupe_key].param:
                    items[dupe_key].param = item.param + ", " + items[dupe_key].param
            else:
                items[dupe_key] = item

        return items.values()


def get_attrib_from_subnode(xml_node, subnode_xpath_expr, attrib_name):
    """
    Finds a subnode in the item node and the retrieves a value from it

    @return An attribute value
    """
    global ETREE_VERSION
    node = None

    if ETREE_VERSION[0] <= 1 and ETREE_VERSION[1] < 3:

        match_obj = re.search(r"([^\@]+?)\[\@([^=]*?)=\'([^\']*?)\'",
                              subnode_xpath_expr)
        if match_obj is not None:
            node_to_find = match_obj.group(1)
            xpath_attrib = match_obj.group(2)
            xpath_value = match_obj.group(3)
            for node_found in xml_node.findall(node_to_find):
                if node_found.attrib[xpath_attrib] == xpath_value:
                    node = node_found
                    break
        else:
            node = xml_node.find(subnode_xpath_expr)

    else:
        node = xml_node.find(subnode_xpath_expr)

    if node is not None:
        return node.get(attrib_name)

    return None


def do_clean(value):
    myreturn = ""
    if value is not None:
        if len(value) > 0:
            for x in value:
                myreturn += x.text
    return myreturn


def get_item(item_node, test):
    endpoints = []
    host_node = item_node.findall('host')[0]

    url_host = host_node.text

    # rhost = re.search(
    #     "(http|https|ftp)\://([a-zA-Z0-9\.\-]+(\:[a-zA-Z0-9\.&amp;%\$\-]+)*@)*((25[0-5]|2[0-4][0-9]|[0-1]{1}[0-9]{2}|[1-9]{1}[0-9]{1}|[1-9])\.(25[0-5]|2[0-4][0-9]|[0-1]{1}[0-9]{2}|[1-9]{1}[0-9]{1}|[1-9]|0)\.(25[0-5]|2[0-4][0-9]|[0-1]{1}[0-9]{2}|[1-9]{1}[0-9]{1}|[1-9]|0)\.(25[0-5]|2[0-4][0-9]|[0-1]{1}[0-9]{2}|[1-9]{1}[0-9]{1}|[0-9])|localhost|([a-zA-Z0-9\-]+\.)*[a-zA-Z0-9\-]+\.(com|edu|gov|int|mil|net|org|biz|arpa|info|name|pro|aero|coop|museum|[a-zA-Z]{2}))[\:]*([0-9]+)*([/]*($|[a-zA-Z0-9\.\,\?\'\\\+&amp;%\$#\=~_\-]+)).*?$",
    #     url_host)
    # protocol = rhost.group(1)
    # host = rhost.group(4)
    protocol = urlparse(url_host).scheme
    host = urlparse(url_host).netloc

    port = 80
    if protocol == 'https':
        port = 443

    # if rhost.group(11) is not None:
    #     port = rhost.group(11)
    if urlparse(url_host).port is not None:
        port = urlparse(url_host).port

    ip = host_node.get('ip')
    url = item_node.get('url')
    path = item_node.findall('path')[0].text
    location = item_node.findall('location')[0].text
    rparameter = re.search(r"(?<=\[)(.*)(\])", location)
    parameter = None
    if rparameter:
        parameter = rparameter.group(1)

    unsaved_req_resp = list()
    for request_response in item_node.findall('./requestresponse'):
        try:
            request = request_response.findall('request')[0].text
        except:
            request = ""
        try:
            response = request_response.findall('response')[0].text
        except:
            response = ""
        unsaved_req_resp.append({"req": request, "resp": response})
    collab_details = list()
    collab_text = None
    for event in item_node.findall('./collaboratorEvent'):
        collab_details.append(event.findall('interactionType')[0].text)
        collab_details.append(event.findall('originIp')[0].text)
        collab_details.append(event.findall('time')[0].text)
        if collab_details[0] == 'DNS':
            collab_details.append(event.findall('lookupType')[0].text)
            collab_details.append(event.findall('lookupHost')[0].text)
            collab_text = "The Collaborator server received a " + collab_details[0] + " lookup of type " + collab_details[3] + \
                " for the domain name " + \
                collab_details[4] + " at " + collab_details[2] + \
                " originating from " + collab_details[1] + " ."

        for request_response in event.findall('./requestresponse'):
            try:
                request = request_response.findall('request')[0].text
            except:
                request = ""
            try:
                response = request_response.findall('response')[0].text
            except:
                response = ""
            unsaved_req_resp.append({"req": request, "resp": response})
        if collab_details[0] == 'HTTP':
            collab_text = "The Collaborator server received an " + \
                collab_details[0] + " request at " + collab_details[2] + \
                " originating from " + collab_details[1] + " ."


    try:
        dupe_endpoint = Endpoint.objects.get(
            protocol=protocol,
            host=host + (":" + port) if port is not None else "",
            path=path,
            query=None,
            fragment=None,
            product=test.engagement.product)
    except:
        dupe_endpoint = None

    if not dupe_endpoint:
        endpoint = Endpoint(
            protocol=protocol,
            host=host + (":" + str(port)) if port is not None else "",
            path=path,
            query=None,
            fragment=None,
            product=test.engagement.product)
    else:
        endpoint = dupe_endpoint

    if ip:
        try:
            dupe_endpoint = Endpoint.objects.get(
                protocol=None,
                host=ip,
                path=None,
                query=None,
                fragment=None,
                product=test.engagement.product)
        except:
            dupe_endpoint = None

        if not dupe_endpoint:
            endpoints = [
                endpoint,
                Endpoint(host=ip, product=test.engagement.product)
            ]
        else:
            endpoints = [endpoint, dupe_endpoint]

    if len(endpoints) == 0:
        endpoints = [endpoint]

    text_maker = html2text.HTML2Text()
    text_maker.body_width = 0

    background = do_clean(item_node.findall('issueBackground'))
    if background:
        background = text_maker.handle(background)

    detail = do_clean(item_node.findall('issueDetail'))
    if detail:
        detail = text_maker.handle(detail)
        if collab_text:
            detail = text_maker.handle(detail + '<p>' + collab_text + '</p>')

    remediation = do_clean(item_node.findall('remediationBackground'))
    if remediation:
        remediation = text_maker.handle(remediation)

    remediation_detail = do_clean(item_node.findall('remediationDetail'))
    if remediation_detail:
        remediation = text_maker.handle(remediation_detail + "\n") + remediation

    references = do_clean(item_node.findall('references'))
    if references:
        references = text_maker.handle(references)

    severity = item_node.findall('severity')[0].text

    scanner_confidence = item_node.findall('confidence')[0].text
    if scanner_confidence:
        if scanner_confidence == "Certain":
            scanner_confidence = 1
        elif scanner_confidence == "Firm":
            scanner_confidence = 4
        elif scanner_confidence == "Tentative":
            scanner_confidence = 7

    # Finding and Endpoint objects returned have not been saved to the database
    finding = Finding(
        title=item_node.findall('name')[0].text,
        url=url,
        test=test,
        severity=severity,
        param=parameter,
        scanner_confidence=scanner_confidence,
        description="URL: " + url_host + path + "\n\n" + detail + "\n",
        mitigation=remediation,
        references=references,
        active=False,
        verified=False,
        false_p=False,
        duplicate=False,
        out_of_scope=False,
        mitigated=None,
        dynamic_finding=True,
        impact=background,
        numerical_severity=Finding.get_numerical_severity(severity))
    finding.unsaved_endpoints = endpoints
    finding.unsaved_req_resp = unsaved_req_resp

    return finding
