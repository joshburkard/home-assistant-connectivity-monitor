# Change Log

| Version | Date | Description |
| --- | --- | --- |
| 0.1.00059 | 22/07/2026 | removed "shell-out" to receive mac-address of a device |
| 0.1.00058 | 23/04/2026 | adjusted LoveLace card allows selecting multiple devices or device type |
| 0.1.00057 | 21/04/2026 | added general sensors to display count of active inactive sensors / devices per device type |
| 0.1.00056 | 17/04/2026 | added mdi icon picker to LoveLace card configurator |
| 0.1.00055 | 16/04/2026 | fixed wrong named LoveLace file |
| 0.1.00054 | 06/04/2026 | cleanup |
| 0.1.00053 | 06/04/2026 | optimization for creating a real HA Integration (later target) and for HACS integration |
| 0.1.00052 | 02/04/2026 | adjusted and standardized config flow |
| 0.1.00051 | 02/04/2026 | separate network.py from sensor.py |
| 0.1.00050 | 02/04/2026 | use DataUpdateCoordinator instead of custom schedulers |
| 0.1.00049 | 02/04/2026 | changed to use icmplib instead of ping3 |
| 0.1.00048 | 02/04/2026 | added support for monitoring Bluetooth connected devices |
| 0.1.00047 | 02/04/2026 | cleanup of old panel.js and adjusted readme |
| 0.1.00046 | 02/04/2026 | LoveLace card device order and title |
| 0.1.00045 | 02/04/2026 | first working version of LoveLace card |
| 0.1.00044 | 02/04/2026 | added visual editor to LoveLace card |
| 0.1.00043 | 02/04/2026 | minimal working version of LoveLace card |
| 0.1.00042 | 01/04/2026 | added support for monitoring ESPHome (ESP32) devices |
| 0.1.00041 | 31/03/2026 | split integration entries into 3 categories: Network Monitor, ZigBee Monitor and Matter Monitor |
| 0.1.00040 | 31/03/2026 | Clean up orphaned devices |
| 0.1.00039 | 31/03/2026 | fixed issue with ZigBee tab in the sidebar panel |
| 0.1.00038 | 31/03/2026 | added Matter devices to the sidebar panel |
| 0.1.00037 | 31/03/2026 | adding support for Matter devices |
| 0.1.00036 | 31/03/2026 | changed structure of Config Flow |
| 0.1.00035 | 30/03/2026 | fixing issue with ICMP sensor |
| 0.1.00034 | 28/03/2026 | added Alert Actions for both Network and ZigBee devices |
| 0.1.00033 | 28/03/2026 | add alert settings for ZigBee devices |
| 0.1.00032 | 28/03/2026 | moved "Add ZigBee Device (ZHA)" to "Add Entry" button and removed it from the "Configure" button |
| 0.1.00031 | 28/03/2026 | merge ZigBee (ZHA) devices with other devices and move sensors to diagnostic category |
| 0.1.00030 | 28/03/2026 | added support for monitoring ZigBee (ZHA) devices |
| 0.1.00029 | 27/03/2026 | add labeled 'Enable Alerts' checkbox to new device and alert config flows |
| 0.1.00028 | 27/03/2026 | add 'Configure' button in sidebar panel |
| 0.1.00027 | 27/03/2026 | fix issue with wrong Overall sensor value |
| 0.1.00026 | 27/03/2026 | sidebar panel: collapsible device sensor lists, healthy devices collapsed by default |
| 0.1.00025 | 27/03/2026 | sidebar panel: show all devices grouped by status, clickable device/sensor rows open more-info dialog |
| 0.1.00024 | 27/03/2026 | added Connectivity Issues sidebar panel showing all devices and sensors with connectivity problems |
| 0.1.00023 | 27/03/2026 | display device address in device info and optimize reload of custom component |
| 0.1.00022 | 27/03/2026 | added posibility to change host address / device name |
| 0.1.00021 | 27/03/2026 | fixed issue with config flow in newer Home Assistant |
| 0.1.00020 | 05/01/2025 | fixed Firmware version in device info |
| 0.1.00019 | 05/01/2025 | added action for alert notification |
| 0.1.00018 | 05/01/2025 | added Alert Notification group and Alert delay to each device |
| 0.1.00017 | 04/01/2025 | fixed issue with AD Overview sensor |
| 0.1.00016 | 31/12/2024 | link devices of differemt integrations together |
| 0.1.00015 | 18/12/2024 | added host and ip address to device information |
| 0.1.00014 | 03/12/2024 | added overall sensor for Active Directory |
| 0.1.00013 | 03/12/2024 | changed default interval to 300 seconds |
| 0.1.00012 | 02/12/2024 | changed back all devices to one integration config, but allowing to adding devices through `ADD DEVICE` or `ADD INTEGRATION` buttons and allowing to remove devices and sensors through `CONFIGURE` button |
| 0.1.00011 | 02/12/2024 | fixed issues after moved each device to a separate config and added an Overall sensor per device |
| 0.1.00010 | 02/12/2024 | moved each device to a separate config and added an Overall sensor per device |
| 0.1.00009 | 30/11/2024 | add device name to config flow |
| 0.1.00008 | 30/11/2024 | removed firmware and hardware version on devices cause it's not needed and useless |
| 0.1.00007 | 30/11/2024 | added protocol type for Active Directory |
| 0.1.00006 | 30/11/2024 | fixed Readme |
| 0.1.00005 | 30/11/2024 | changed all files and vscode default settings to UTF-8 encoding |
| 0.1.00004 | 30/11/2024 | added DNS configuration |
| 0.1.00003 | 30/11/2024 | renamed entity_id to be unique |
| 0.1.00002 | 30/11/2024 | added RPC and ICMP, grouped by target device |
| 0.1.00001 | 30/11/2024 | initial version |
