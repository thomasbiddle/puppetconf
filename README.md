## Puppet API and Related Code Examples

The script **api.py** is an example of a REST API for Puppet Dashboard and
Puppet storeconfigs data. This script is a self-contained application written
using Python's Flask microframework.

This script was designed specifically for Pinterest's infrastructure, so it
might not directly be relevant for your environment. We wanted to publish some
sample code to show how our REST API works, and we hope this is at least a
starting point for those of you that choose to create your own API.

Copyright (c) 2011-2012 Pinterest, Inc. See LICENSE for details.

**Prerequisites:**

1. You must be using Puppet Dashboard 1.2 or higher, preferably version 1.2.10
or above.
2. Your puppetmaster must be configured to use storeconfigs (storeconfigs=true
in your puppetmaster's /etc/puppet/puppet.conf).
3. This scripts requires Python 2.7 the Python libraries PyMySQL and Flask.

**Usage:** `python api.py <port>` to run a single-threaded web server process
on the given port. Defaults to port 9000.

We recommend running this in conjunction with Supervisor, a watchdog daemon for
Python applications. Here's an example Supervisor config stanza to run 8
processes on ports 9000-9007:

    [program:puppet_api]
    directory=/usr/local/puppet-api
    command=python api.py 90%(process_num)02d
    process_name=%(program_name)s_%(process_num)02d
    numprocs=8
    priority=999
    autostart=true
    autorestart=true
    startsecs=10
    user=nobody
