#!/usr/bin/env python

# Example API client: Generates /etc/hosts style listing of all EC2 nodes in
# Puppet Dashboard. This is a client of the the Puppet API (api.py) in this Git
# repository.
#
# Copyright (C) 2011-2012, Pinterest, Inc. See LICENSE for details.

import json
import socket
import urllib2

# Base URL to the Puppet API
PUPPET_API_URL = "https://puppet-dashboard/api"


def download_and_decode(url):
    """Downloads a resource from the Puppet API and decodes the JSON output
into a Python dict."""
    request = urllib2.Request(url)
    response = urllib2.urlopen(request)
    return json.loads(response.read())


def main():
    global options
    nodes = download_and_decode('%s/nodes' % PUPPET_API_URL)
    local_fqdn = socket.getfqdn()
    local_ip = socket.gethostbyname(local_fqdn)
    local_hostname = local_fqdn.split('.')[0]

    print """127.0.0.1 localhost

# The following lines are desirable for IPv6 capable hosts
::1 ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
ff02::3 ip6-allhosts

# Additional entries added by puppet_to_hosts.py"""

    for node in nodes:
        if ".%s" % DOMAIN in node['name']:
            if 'ipaddress' in node and node['ipaddress']:
                print node['ipaddress'] + " " + node['name'].split(".")[0]

if __name__ == "__main__":
    main()
