#!/usr/bin/env python

# Example API client: Cleans up any certificates on this server for hosts that
# are not defined in Puppet Dashboard. This is a client of the the Puppet API
# (api.py) in this Git repository.
#
# Warning: This script will revoke certificates signed by your certificate
# authorirty -- be sure you understand how it works before you run it. Make
# sure to set the variables PUPPET_API_URL and PUPPET_HOST.
#
# Copyright (C) 2011-2012, Pinterest, Inc. See LICENSE for details.

import json
import socket
import subprocess
import urllib2

# Base URL to the Puppet API
PUPPET_API_URL = "https://puppet-dashboard/api"

# Puppet hostname
PUPPET_HOST = "puppet.example.com"


def download_and_decode(url):
    """Downloads a resource from the Puppet API and decodes the JSON output
into a Python dict."""
    request = urllib2.Request(url)
    response = urllib2.urlopen(request)
    return json.loads(response.read())


def get_certs():
    """Returns a list of all certificates known to puppetca on this server."""
    cmd = "/usr/sbin/puppetca --list --all | grep '^+ ' | cut -f 2 -d '\"'"
    proc = subprocess.Popen([cmd], stdout=subprocess.PIPE, shell=True)
    (stdout, stderr) = proc.communicate()
    return [c for c in stdout.split("\n") if c and len(c) > 0]


def main():
    nodes = download_and_decode('%s/nodes' % PUPPET_API_URL)
    nodes = [n['name'] for n in nodes]

    certs = get_certs()
    certs_without_nodes = [c for c in certs if c not in nodes]

    return_code = 0

    for hostname in certs_without_nodes:
        if hostname == PUPPET_HOST:
            continue
        print "Removing certificate for %s" % hostname
        cmd = "/usr/sbin/puppetca --color=false --clean %s" % hostname
        proc = subprocess.Popen([cmd], stdout=subprocess.PIPE, shell=True)
        (stdout, stderr) = proc.communicate()
        if proc.returncode != 0:
            return_code = 1
        if stdout and len(stdout) > 0:
            print stdout
        if stderr and len(stderr) > 0:
            print stderr

    sys.exit(return_code)


if __name__ == "__main__":
    main()
