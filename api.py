#!/usr/bin/env python

# This is an example of a REST API for Puppet Dashboard and Puppet storeconfigs
# data. This script is a self-contained application written using Python's
# Flask microframework. Run "python api.py 9000" to run a single-threaded web
# server process on port 9000. We recommend running this on 4-8 ports
# simultaneously in production. You can also run this inside a WSGI container
# such as Apache's mod_wsgi.
#
# This script was designed specifically for Pinterest's infrastructure, so it
# might not directly be relevant for your environment. We wanted to publish
# some sample code to show how our REST API works, and we hope this is at least
# a starting point for those of you that choose to create your own API.
#
# Requirements:
# 1. You must be using Puppet Dashboard 1.2 or higher, preferably version
#    1.2.10 or above.
# 2. Your puppetmaster must be configured to use storeconfigs
#    (storeconfigs=true in your puppetmaster's /etc/puppet/puppet.conf).
# 3. This scripts requires Python 2.7 the Python libraries PyMySQL and Flask.
#
# Copyright (C) 2011-2012, Pinterest, Inc. See LICENSE for details.

import pymysql
import sys
import socket
import simplejson as json

# Configure these variables for database access. The user must have read access
# to the puppet database, and read/write access to the dashboard database.
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_USER = "dashboard"
MYSQL_PASSWD = "dashboard"
MYSQL_DASHBOARD_DB = "dashboard"
MYSQL_PUPPET_DB = "puppet"
PROTOCOL = 'https'

# This is the domain in which new hosts should reside. (For example, a host
# called 'pluto001' would have the full domain name 'pluto001.example.com'.)
MAIN_DOMAIN = "example.com"

from flask import Flask, url_for, make_response, request
app = Flask(__name__)


@app.route("/api/")
def index():
    """API home page; lists other available endpoints in the API."""
    data = {"nodes": PROTOCOL + "://%s%s" % (request.host, url_for(
                     'list_nodes')),
            "node_classes": PROTOCOL + "://%s%s" % (request.host, url_for(
                            'list_node_classes')),
            "node_groups": PROTOCOL + "://%s%s" % (request.host, url_for(
                           'list_node_groups'))
            }
    response = make_response(json.dumps(data, indent=2))
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route("/api/nodes/<status>")
@app.route("/api/nodes")
@app.route("/api/node")
def list_nodes(status=None):
    """Lists all nodes defined in Puppet Dashboard."""

    node_facts = {}

    # In case we're not using storedconfigs in Puppet.
    if MYSQL_PUPPET_DB:
        cur = None
        conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                               user=MYSQL_USER, passwd=MYSQL_PASSWD,
                               db=MYSQL_PUPPET_DB)
        try:
            cur = conn.cursor()
            cur.execute("SELECT h.name, fn.name, fv.value "
                        "FROM hosts h, fact_names fn, fact_values fv "
                        "WHERE h.id = fv.host_id "
                        "AND fn.name in ('ec2_local_ipv4', 'ec2_public_ipv4') "
                        "AND fn.id = fv.fact_name_id ORDER BY fv.updated_at")
            for r in cur.fetchall():
                name = r[0]
                if name not in node_facts:
                    node_facts[name] = {'ec2_local_ipv4': None,
                                        'ec2_public_ipv4': None}
                fact = r[1]
                node_facts[name][fact] = r[2]
        finally:
            if cur:
                cur.close()
            conn.close()

    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT n.name, p.`value` FROM parameters p, nodes n "
                    "WHERE p.`key`='aliases' "
                    "AND p.parameterable_type = 'Node' "
                    "AND p.parameterable_id = n.id")
        node_aliases = {}
        for r in cur.fetchall():
            name = r[0]
            node_aliases[name] = r[1]
    finally:
        if cur:
            cur.close()
        conn.close()

    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        if status:
            cur.execute("SELECT id, name FROM nodes WHERE status = %s "
                        "ORDER BY UPPER(name)" % conn.escape(status))
        else:
            cur.execute("SELECT id, name FROM nodes ORDER BY UPPER(name)")
        data = []
        for r in cur.fetchall():
            name = r[1]
            url = PROTOCOL + "://%s%s" % (request.host, url_for(
                                    'get_node', node_name=name))
            rec = {"name": name, "url": url}
            if name in node_facts:
                rec['ec2_local_ipv4'] = node_facts[name]['ec2_local_ipv4']
                rec['ec2_public_ipv4'] = node_facts[name]['ec2_public_ipv4']
            if name in node_aliases:
                rec['aliases'] = node_aliases[name]
            data.append(rec)
    finally:
        if cur:
            cur.close()
        conn.close()
    response = make_response(json.dumps(data, indent=2))
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route("/api/node/<node_name>", methods=['GET'])
def get_node(node_name):
    """Returns detailed information about the specified node."""
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, status FROM nodes WHERE name = %s LIMIT 1" %
                    conn.escape(node_name))
        data = {}
        r = cur.fetchone()
        if r is None:
            return "Node not found", 404
        node_id = data['id'] = r[0]
        data['status'] = r[1]
    finally:
        if cur:
            cur.close()
        conn.close()

    data['node_groups'] = get_groups_for_node(node_id, node_name, True)
    data['node_classes'] = get_classes_for_node(node_id, node_name)
    data['parameters'] = get_parameters_for_node(node_id, node_name)
    data['facts'] = []
    for node_group in data['node_groups']:
        data['node_classes'].extend(
            get_classes_for_group(node_group['id'], node_group['name']))


    # In case we're not using storedconfigs in Puppet.
    if MYSQL_PUPPET_DB:
        cur = None
        conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                               user=MYSQL_USER, passwd=MYSQL_PASSWD,
                               db=MYSQL_PUPPET_DB)
        try:
            cur = conn.cursor()
            cur.execute("SELECT n.name, v.value "
                        "FROM hosts h, fact_names n, fact_values v "
                        "WHERE h.id = v.host_id AND n.id = v.fact_name_id "
                        "AND h.name = %s" % conn.escape(node_name))
            for r in cur.fetchall():
                url = PROTOCOL + "://" + request.host + url_for(
                    'get_node_fact', node_name=node_name, fact_name=r[0])
                data['facts'].append({"name": r[0], "url": url, "value": r[1]})
        finally:
            if cur:
                cur.close()
            conn.close()

    response = make_response(json.dumps(data, indent=2))
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route("/api/node/<node_name>/fact/<fact_name>",
           methods=['PUT', 'GET', 'DELETE'])
def get_node_fact(node_name, fact_name):
    """Returns the value of the specified node fact."""
    if request.method == 'PUT' or request.method == 'DELETE':
        return "This method is deprecated", 200

    # In case we're not using storedconfigs in Puppet.
    if MYSQL_PUPPET_DB:
        cur = None
        conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                               user=MYSQL_USER, passwd=MYSQL_PASSWD,
                               db=MYSQL_PUPPET_DB)
        try:
            cur = conn.cursor()
            cur.execute("SELECT v.value FROM hosts h, fact_names n, fact_values v "
                        "WHERE h.id = v.host_id AND n.id = v.fact_name_id "
                        "AND h.name = %s AND n.name = %s LIMIT 1" %
                        (conn.escape(node_name), conn.escape(fact_name)))
            r = cur.fetchone()
            if r is None:
                return "Fact not found", 404
            data = r[0]
        finally:
            if cur:
                cur.close()
            conn.close()
    else:
        return "This method is disabled due to storedconfigs being disabled.", 200

    response = make_response(data)
    response.headers['Content-Type'] = 'text/plain'
    return response


@app.route("/api/provision/<node_group_name>")
def provision_node(node_group_name):
    """Creates a new node in the specified node group, and returns the
    hostname."""
    node_group_id = get_node_group_id(node_group_name)
    if not node_group_id:
        return "Node group not found", 404
    hostname = next_hostname_for_node_group(node_group_name)
    if not hostname:
        return "Unable to find a suitable hostname for this node group", 500
    create_node(hostname)
    add_node_to_group(hostname, node_group_name)
    data = {"hostname": hostname}
    response = make_response(json.dumps(data, indent=2))
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route("/api/node/<node_name>", methods=['DELETE'])
def delete_node(node_name):
    """Deletes the specified node from Puppet Dashboard's database."""
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM nodes WHERE name = %s LIMIT 1" %
                    conn.escape(node_name))
        r = cur.fetchone()
        if r is None:
            return "Node not found", 404
        node_id = r[0]
        cur.close()
        cur = conn.cursor()
        cur.execute("DELETE FROM node_class_memberships WHERE node_id = %d "
                    "LIMIT 1" % node_id)
        cur.close()
        cur = conn.cursor()
        cur.execute("DELETE FROM node_group_memberships WHERE node_id = %d "
                    "LIMIT 1" % node_id)
        cur.close()
        cur = conn.cursor()
        cur.execute("DELETE FROM nodes WHERE id = %d LIMIT 1" % node_id)
        cur.close()
        cur = None
        conn.commit()
    finally:
        if cur:
            cur.close()
        conn.close()
    return None, 204


@app.route("/api/node_classes")
@app.route("/api/node_class")
@app.route("/api/classes")
@app.route("/api/class")
def list_node_classes():
    """Lists all node classes defined in Puppet Dashboard."""
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM node_classes ORDER BY UPPER(name)")
        data = []
        for r in cur.fetchall():
            name = r[1]
            url = PROTOCOL + "://" + request.host + url_for(
                'get_node_class', node_class_name=name)
            data.append({"name": name, "url": url})
    finally:
        if cur:
            cur.close()
        conn.close()
    response = make_response(json.dumps(data, indent=2))
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route("/api/node_class/<node_class_name>")
@app.route("/api/class/<node_class_name>")
def get_node_class(node_class_name):
    """Returns detailed information about the specified node class."""
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM node_classes WHERE name = %s "
                    "LIMIT 1" % conn.escape(node_class_name))
        data = {}
        r = cur.fetchone()
        if r is None:
            return "Node class not found", 404
        node_class_id = data['id'] = r[0]
        data['name'] = r[1]
        cur.close()
        data['node_groups'] = get_groups_for_class(node_class_id,
                                                   node_class_name)
        data['nodes'] = get_nodes_for_class(node_class_id, node_class_name)
        for node_group in data['node_groups']:
            data['nodes'].extend(get_nodes_for_group(
                node_group['id'], node_group['name']))
    finally:
        if cur:
            cur.close()
        conn.close()
    response = make_response(json.dumps(data, indent=2))
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route("/api/node_groups")
@app.route("/api/node_group")
@app.route("/api/groups")
@app.route("/api/group")
def list_node_groups():
    """Lists all node groups defined in Puppet Dashboard."""
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM node_groups ORDER BY UPPER(name)")
        data = []
        for r in cur.fetchall():
            name = r[1]
            url = PROTOCOL + "://" + request.host + url_for(
                'get_node_group', node_group_name=name)
            data.append({"name": name, "url": url})
    finally:
        if cur:
            cur.close()
        conn.close()
    response = make_response(json.dumps(data, indent=2))
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route("/api/node_group/<node_group_name>")
@app.route("/api/group/<node_group_name>")
def get_node_group(node_group_name):
    """Returns detailed information about the specified node group."""
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM node_groups WHERE name = %s"%(conn.escape(node_group_name)))
        data = {}
        r = cur.fetchone()
        if r is None:
            return "Node group not found", 404
        node_group_id = data['id'] = r[0]
    finally:
        if cur:
            cur.close()
        conn.close()
    data['ancestors'] = get_ancestors_for_group(
        node_group_id, node_group_name, True)
    data['descendants'] = get_descendants_for_group(
        node_group_id, node_group_name)
    data['nodes'] = get_nodes_for_group(node_group_id, node_group_name)
    data['node_classes'] = get_classes_for_group(node_group_id,
                                                 node_group_name)
    data['parameters'] = get_parameters_for_group(node_group_id,
                                                  node_group_name)
    for node_group in data['descendants']:
        data['nodes'].extend(
            get_nodes_for_group(node_group['id'], node_group['name']))
    for node_group in data['ancestors']:
        data['node_classes'].extend(
            get_classes_for_group(node_group['id'], node_group['name']))
    response = make_response(json.dumps(data, indent=2))
    response.headers['Content-Type'] = 'application/json'
    return response


def get_node_id(hostname):
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    result = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM nodes WHERE name = %s LIMIT 1" %
                    conn.escape(hostname))
        for r in cur.fetchall():
            result = r[0]
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def get_node_group_id(node_group_name):
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    result = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM node_groups WHERE name = %s LIMIT 1" %
                    conn.escape(node_group_name))
        for r in cur.fetchall():
            result = r[0]
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def get_parameters_for_element(type, id, source):
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    sql = ("SELECT id, `key`, `value` FROM parameters "
           "WHERE parameterable_type = %s AND parameterable_id = %d "
           "ORDER BY UPPER(`key`), UPPER(`value`)") % (conn.escape(type), id)
    cur = None
    result = {}
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            parameter_id = r[0]
            parameter_key = r[1]
            parameter_value = r[2]
            result[parameter_key] = {'id': parameter_id,
                                     'key': parameter_key,
                                     'value': parameter_value,
                                     'source': source}
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def get_parameters_for_node(node_id, node_name):
    source_url = PROTOCOL + "://" + request.host + url_for('get_node',
                                                     node_name=node_name)
    source = {'type': 'node', 'name': node_name, 'href': source_url}
    params = get_parameters_for_element("Node", node_id, source)
    groups = get_groups_for_node(node_id, node_name, False)
    for group in groups:
        group_params = get_parameters_for_group(
            group['id'], group['name']).values()
        for group_param in group_params:
            key = group_param['key']
            if key not in params:
                params[key] = group_param
    return params


def get_parameters_for_group(node_group_id, node_group_name):
    source_url = PROTOCOL + "://%s%s" % (request.host, url_for(
                 'get_node_group', node_group_name=node_group_name))
    source = {'type': 'node_group', 'name': node_group_name, 'href':
              source_url}
    params = get_parameters_for_element("get_node_group",
                                        node_group_id, source)
    parents = get_ancestors_for_group(node_group_id, node_group_name, False)
    for parent in parents:
        parent_params = get_parameters_for_group(
            parent['id'], parent['name']).values()
        for parent_param in parent_params:
            key = parent_param['key']
            if key not in params:
                params[key] = parent_param
    return params


def get_groups_for_node(node_id, node_name, recurse):
    result = []
    source_url = PROTOCOL + "://" + request.host + url_for('get_node',
                                                     node_name=node_name)
    sql = ("SELECT ng.id, ng.name "
           "FROM node_group_memberships ngm, node_groups ng "
           "WHERE ng.id = ngm.node_group_id AND ngm.node_id = %d") % node_id
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            parent_group_id = r[0]
            parent_group_name = r[1]
            url = PROTOCOL + "://" + request.host + url_for(
                'get_node_group', node_group_name=parent_group_name)
            result.append({'id': parent_group_id, 'name': parent_group_name,
                           'source': {'type': 'node', 'name': node_name,
                                      'href': source_url}, 'href': url})
            if recurse:
                result.extend(get_ancestors_for_group(
                    parent_group_id, parent_group_name, True))
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def get_classes_for_node(node_id, node_name):
    result = []
    source_url = PROTOCOL + "://" + request.host + url_for("get_node",
                                                     node_name=node_name)
    sql = ("SELECT nc.id, nc.name "
           "FROM node_class_memberships ncm, node_classes nc "
           "WHERE nc.id = ncm.node_class_id AND ncm.node_id = %d") % node_id
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            node_class_id = r[0]
            node_class_name = r[1]
            url = PROTOCOL + "://" + request.host + url_for(
                'get_node_class', node_class_name=node_class_name)
            result.append({'id': node_class_id, 'name': node_class_name,
                           'source': {'type': 'node', 'name': node_name,
                                      'href': source_url}, 'href': url})
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def get_nodes_for_class(node_class_id, node_class_name):
    result = []
    source_url = PROTOCOL + "://%s%s" % (request.host, url_for(
                 "get_node_class", node_class_name=node_class_name))
    sql = ("SELECT n.id, n.name FROM node_class_memberships ncm, nodes n "
           "WHERE n.id = ncm.node_id AND ncm.node_class_id = %d" %
           node_class_id)
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            node_id = r[0]
            node_name = r[1]
            url = PROTOCOL + "://" + request.host + url_for('get_node',
                                                      node_name=node_name)
            result.append({'id': node_id, 'name': node_name,
                           'source': {'type': 'node_class',
                                      'name': node_class_name,
                                      'href': source_url}, 'href': url})
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def get_groups_for_class(node_class_id, node_class_name):
    result = []
    source_url = PROTOCOL + "://%s%s" % (request.host, url_for(
                 "get_node_class", node_class_name=node_class_name))
    sql = ("SELECT ng.id, ng.name "
           "FROM node_group_class_memberships ngcm, node_groups ng "
           "WHERE ng.id = ngcm.node_group_id AND ngcm.node_class_id = %d" %
           node_class_id)
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            parent_group_id = r[0]
            parent_group_name = r[1]
            url = PROTOCOL + "://" + request.host + url_for(
                'get_node_group', node_group_name=parent_group_name)
            result.append({'id': parent_group_id, 'name': parent_group_name,
                           'source': {'type': 'node_class',
                                      'name': node_class_name,
                                      'href': source_url}, 'href': url})
            result.extend(get_descendants_for_group(
                parent_group_id, parent_group_name))
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def get_nodes_for_group(node_group_id, node_group_name):
    result = []
    source_url = PROTOCOL + "://%s%s" % (request.host, url_for(
                 "get_node_group", node_group_name=node_group_name))
    sql = ("SELECT n.id, n.name FROM node_group_memberships ngm, nodes n "
           "WHERE n.id = ngm.node_id AND ngm.node_group_id = %d" %
           node_group_id)
    cur = None
    try:
        conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                               user=MYSQL_USER, passwd=MYSQL_PASSWD,
                               db=MYSQL_DASHBOARD_DB)
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            node_id = r[0]
            node_name = r[1]
            url = PROTOCOL + "://" + request.host + url_for('get_node',
                                                      node_name=node_name)
            result.append({'id': node_id, 'name': node_name,
                           'source': {'type': 'node_group',
                                      'name': node_group_name,
                                      'href': source_url}, 'href': url})
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def get_classes_for_group(node_group_id, node_group_name):
    result = []
    source_url = PROTOCOL + "://%s%s" % (request.host, url_for(
                 'get_node_group', node_group_name=node_group_name))
    sql = ("SELECT nc.id, nc.name "
           "FROM node_group_class_memberships ngcm, node_classes nc "
           "WHERE nc.id = ngcm.node_class_id AND ngcm.node_group_id = %d" %
           node_group_id)
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            node_class_id = r[0]
            node_class_name = r[1]
            url = PROTOCOL + "://" + request.host + url_for(
                'get_node_class', node_class_name=node_class_name)
            result.append({'id': node_class_id, 'name': node_class_name,
                           'source': {'type': 'node_group',
                                      'name': node_group_name,
                                      'href': source_url}, 'href': url})
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def get_ancestors_for_group(node_group_id, node_group_name, recurse):
    result = []
    source_url = PROTOCOL + "://%s%s" % (request.host, url_for(
                 'get_node_group', node_group_name=node_group_name))
    sql = ("SELECT ng.id, ng.name FROM node_group_edges nge, node_groups ng "
           "WHERE ng.id = nge.to_id AND nge.from_id = %d") % (node_group_id)
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            parent_group_id = r[0]
            parent_group_name = r[1]
            url = PROTOCOL + "://" + request.host + url_for(
                'get_node_group', node_group_name=parent_group_name)
            result.append({'id': parent_group_id,
                           'name': parent_group_name,
                           'source': {'type': 'node_group',
                                      'name': node_group_name,
                                      'href': source_url},
                           'href': url})
            if recurse:
                result.extend(get_ancestors_for_group(
                    parent_group_id, parent_group_name, True))
        cur.close()
    finally:
        conn.close()
    return result


def get_descendants_for_group(node_group_id, node_group_name):
    result = []
    source_url = PROTOCOL + "://%s%s" % (request.host, url_for(
                 'get_node_group', node_group_name=node_group_name))
    sql = ("SELECT ng.id, ng.name FROM node_group_edges nge, node_groups ng "
           "WHERE ng.id = nge.from_id AND nge.to_id = %d") % node_group_id
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            child_group_id = r[0]
            child_group_name = r[1]
            url = PROTOCOL + "://" + request.host + url_for(
                'get_node_group', node_group_name=child_group_name)
            result.append({'id': child_group_id,
                           'name': child_group_name,
                           'source': {'type': 'node_group',
                                      'name': node_group_name,
                                      'href': source_url},
                           'href': url})
            result.extend(get_descendants_for_group(
                child_group_id, child_group_name))
    finally:
        if cur:
            cur.close()
        conn.close()
    return result


def next_hostname_for_node_group(node_group_name):
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    prev_name = None
    try:
        for i in range(1, 1000):
            sql = ("SELECT COUNT(*) FROM nodes WHERE name = %s "
                   "ORDER BY name DESC LIMIT 1" %
                   conn.escape('%s%03d.%s' % (node_group_name, i,
                                              MAIN_DOMAIN)))
            cur = conn.cursor()
            cur.execute(sql)
            r = cur.fetchone()
            cur.close()
            cur = None
            if r[0] == 0:
                return "%s%03d.%s" % (node_group_name, i, MAIN_DOMAIN)
    finally:
        if cur:
            cur.close()
        conn.close()
    raise Exception(
        "Unable to find an unused hostname for %s" % node_group_name)


def create_node(hostname):
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO nodes(name, created_at, updated_at, hidden) "
                    "VALUES(%s, NOW(), NOW(), 0)" % conn.escape(hostname))
        conn.commit()
    finally:
        if cur:
            cur.close()
        conn.close()


def add_node_to_group(hostname, node_group_name):
    node_id = get_node_id(hostname)
    node_group_id = get_node_group_id(node_group_name)
    cur = None
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, passwd=MYSQL_PASSWD,
                           db=MYSQL_DASHBOARD_DB)
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO node_group_memberships(node_id, "
                    "node_group_id, created_at, updated_at) VALUES(%d, %d, "
                    "NOW(), NOW())" % (node_id, node_group_id))
        conn.commit()
    finally:
        if cur:
            cur.close()
        conn.close()


try:
    port = int(sys.argv[1])
except:
    port = 9000

if __name__ == "__main__":
    app.debug = True
    app.run(host='0.0.0.0', port=port)
