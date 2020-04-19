# unifi-tools
Command line tools to manage/monitor UniFi network.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## References
This projet is based on [`UniFi-API-client`](https://github.com/Art-of-WiFi/UniFi-API-client)

## Requirements
- [Python requests](http://python-requests.org)

## Usage
### Management
```
usage: unifi-manager.py [-h] [-d] [-r <mac address>] [-l]
                        [-p <mac address/device name>]
                        address site user passwd

positional arguments:
  address               controller address
  site                  target site
  user                  username for authentication
  passwd                password for authentication

optional arguments:
  -h, --help            show this help message and exit
  -d, --dev             enable development logging
  -r <mac address>, --reconnect <mac address>
                        reconnect client
  -l, --list-devices    list devices
  -p <mac address/device name>, --provision <mac address/device name>
```

### Monitoring
TODO ...

## Licensing
This project is licensed under the MIT license.
