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
  - WebPage (HTTP / HTTPS availability, response text, and certificate expiry)
- allows to add later more targets or remove them again
- allows to use a custom DNS server to resolve FQDN

## Example

### WebPage monitoring

Choose **WebPage** when adding the integration. Enter an absolute HTTP(S) URL,
an optional case-sensitive substring to find in the raw response body, and a
certificate warning threshold in days (default 30; 0 warns only at expiry).
Each URL has an **Overall Status** sensor. It is `Connected` only when system DNS
resolves the hostname, the final HTTP response is 2xx, the configured text is
present, and all HTTPS redirect-hop
certificates are trusted, valid, and outside the warning threshold.

Separate sensors identify which check failed:

- **DNS Status**: Resolved / Failed; attributes list resolved IP addresses.
- **WebPage Reachable**: Reachable / Unreachable (final response must be 2xx);
  attributes show the HTTP status and request error.
- **Certificate Status** (HTTPS targets): Valid / Expiring Soon / Invalid / Error.
  Attributes show expiry and certificate-check errors.
- **Content Status** (only when text is configured): Found / Missing / Error /
  Not Checked.
- **Response Time**: HTTP request and optional body-read duration in milliseconds,
  excluding the separate DNS and certificate probes.
- **Certificate Days Remaining** (HTTPS targets): days until expiry.

All sensors share one device; only Overall Status triggers configured alerts.
Existing overall entity IDs are preserved when upgrading from WebPage Status.
Checks remain independent: a content or certificate problem does not hide a
successful HTTP response. Overall attributes also expose all failure reasons.
Certificate attributes are unset for plain HTTP; text match is unset when no text
is configured.
Checks use a 5-second system DNS timeout, follow redirects (at most 10), use a
15-second HTTP timeout, and inspect
certificates with separate verified TLS connections (10-second timeout each).
Text checks are limited to 2 MiB of decoded response bytes; oversized or
undecodable content makes the check unhealthy. JavaScript is not executed.
WebPage requests use Home Assistant's system DNS, not the custom network DNS setting.

Use **Configure > Modify WebPage Checks and Alerts** to edit checks and the
existing delayed notifications / automation or script actions. Currently unhealthy
pages can be added so outages can be monitored. URL credentials are rejected;
authentication configuration is planned for a later step.

### LoveLace Cards

Choose **WebPage** in the Connectivity Monitor card editor to list monitored
pages, filtered by **Connected**, **Disconnected**, or **All**. Expand a page to
see its DNS, HTTP, certificate, content, and measurement sensors (only configured
checks are shown). WebPages can also be included in a mixed **Device List**.
The header uses overall health; each detail row shows its own result.
WebPage headers display only the device name, and child rows display only the
check name (for example, **DNS Status**), without repeating the device name.
Existing WebPage sensors without the newer `monitor_type` / `webpage_check`
attributes are also recognized from their WebPage diagnostic attributes and
check names.

```yaml
type: custom:connectivity-monitor-card
device_type: WebPage
status_filter: All
```

After updating, restart Home Assistant to load the sensor metadata and hard-refresh
the dashboard to reload the card JavaScript.

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
