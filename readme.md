# Connectivity Monitor

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Adds a Connectivity Monitor to Home assistant. This integration requires [HACS](https://hacs.xyz).

## Features

This integration allows to monitor devices and create Alert Notification and Alert Actions.

- Device Types:
  - Network Devices:
    - TCP
    - UDP
    - ICMP
    - Active Directory Domain Controller
    - supports targets with IP-Address or FQDN
  - ESPHome / ESP32 devices
  - Matter
  - ZigBee (ZHA)
- allows to add later more targets or remove them again
- allows to use a custom DNS server to resolve FQDN

## Example

### LoveLace Cards

![configure LoveLace Card](images/example-003.png)

![configure LoveLace Card](images/example-004.png)

![LoveLace Card](images/example-001.png)

### Device View

![Device-View](images/example-002.png)

## Setup

Recommended to be installed via [HACS](https://github.com/hacs/integration)

1. [Open your Home Assistant instance and look for the Connectivity Monitor integration inside HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=joshburkard&repository=home-assistant-connectivity-monitor&category=integration)
2. Install the integration.
3. Restart Home Assistant
4. Open Home Assistant Settings -> Devices & Serivces
5. Shift+reload your browser to clear config flow caches.
6. Click ADD INTEGRATION
7. Search for "Connectivity Monitor"
8. Define the DNS Server to use
9. Define the Target Host to monitor, the needed protocol and port and click on `Submit`
10. if you want to monitor additional targets check the checkbox `another` and click on `Submit`
11. configure the interval and click on `Submit`
12. done, if you want to edit your settings, you can click on your integration on on `CONFIGURE`
13. add a LoveLace card do your dashboards

## Change Log

here you will find the [Change Log](changelog.md)

## Notes

This custom component was created without any knowledge of Python but with use of Claude AI

## Tasks

this changes are planned:

- [x] create an Overall sensor per device
- [ ] add Device information:
  - [ ] IP-Address
  - [ ] MAC Address
- [x] let use of `Add Device`
- [x] change default interval to 300 seconds

## Icon

the icon and logo is made by [Freepik - Flaticon](https://www.flaticon.com/free-icons/electronics)
