"""Tests for Connectivity Monitor initialization."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest

from custom_components.connectivity_monitor import (
    async_migrate_entry,
    async_reload_entry,
    async_setup,
)
from custom_components.connectivity_monitor.esphome import (
    async_refresh_target_metadata,
)
from custom_components.connectivity_monitor.const import (
    CONF_BLUETOOTH_ADDRESS,
    CONF_DNS_SERVER,
    CONF_ESPHOME_DEVICE_ID,
    CONF_HOST,
    CONF_INTERVAL,
    CONF_PROTOCOL,
    CONF_TARGETS,
    CONF_ZHA_IEEE,
    DEFAULT_DNS_SERVER,
    DOMAIN,
    PROTOCOL_BLUETOOTH,
    PROTOCOL_ESPHOME,
    PROTOCOL_ICMP,
    PROTOCOL_MATTER,
    PROTOCOL_ZHA,
    VERSION,
)

# pylint: disable-next=hass-component-root-import
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_load_unload_entry(
    hass: HomeAssistant,
    network_config_entry: MockConfigEntry,
) -> None:
    """Test loading and unloading the integration."""
    network_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.connectivity_monitor.coordinator."
            "NetworkProbe.async_prepare_host",
            AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.connectivity_monitor.coordinator."
            "NetworkProbe.async_update_target",
            AsyncMock(
                return_value={
                    "connected": True,
                    "latency": 3.2,
                    "resolved_ip": "192.168.1.1",
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                }
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(network_config_entry.entry_id)
        await hass.async_block_till_done()

    assert network_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.connectivity_monitor_router_icmp") is not None

    alert_handler = network_config_entry.runtime_data.alert_handler
    with patch.object(alert_handler, "async_cleanup", wraps=alert_handler.async_cleanup) as cleanup:
        assert await hass.config_entries.async_unload(network_config_entry.entry_id)
        await hass.async_block_till_done()

    cleanup.assert_awaited_once()
    assert network_config_entry.state is ConfigEntryState.NOT_LOADED
    assert not hasattr(network_config_entry, "runtime_data")


async def test_setup_refreshes_existing_esphome_metadata(
    hass: HomeAssistant,
) -> None:
    """Refresh ESPHome metadata before creating the monitor sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ESPHome Monitor",
        unique_id="connectivity_monitor_esphome_metadata_refresh",
        version=2,
        data={
            CONF_TARGETS: [
                {
                    CONF_PROTOCOL: PROTOCOL_ESPHOME,
                    CONF_HOST: "esphome:node-1",
                    CONF_ESPHOME_DEVICE_ID: "node-1",
                    "device_name": "My Garage Node",
                }
            ],
            CONF_INTERVAL: 30,
            CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.connectivity_monitor.esphome."
            "async_get_esphome_devices",
            AsyncMock(
                return_value=[
                    {
                        "device_id": "node-1",
                        "entry_id": "node-1",
                        "name": "Discovered Garage Node",
                        "manufacturer": "Espressif",
                        "model": "ESP32",
                        "sw_version": "2026.1",
                    }
                ]
            ),
        ),
        patch(
            "custom_components.connectivity_monitor.coordinator."
            "async_get_esphome_device_active",
            AsyncMock(return_value=True),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    refreshed_target = entry.data[CONF_TARGETS][0]
    assert refreshed_target["manufacturer"] == "Espressif"
    assert refreshed_target["model"] == "ESP32"
    assert refreshed_target["sw_version"] == "2026.1"
    assert refreshed_target["device_name"] == "My Garage Node"


async def test_esphome_metadata_refresh_keeps_saved_values_when_unavailable(
    hass: HomeAssistant,
) -> None:
    """Keep saved ESPHome metadata when the registry has no replacement values."""
    target = {
        CONF_PROTOCOL: PROTOCOL_ESPHOME,
        CONF_HOST: "esphome:node-1",
        CONF_ESPHOME_DEVICE_ID: "node-1",
        "device_name": "My Garage Node",
        "manufacturer": "Espressif",
        "model": "ESP32",
        "sw_version": "2025.9",
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ESPHome Monitor",
        unique_id="connectivity_monitor_esphome_missing_metadata",
        version=2,
        data={
            CONF_TARGETS: [target],
            CONF_INTERVAL: 30,
            CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.connectivity_monitor.esphome."
        "async_get_esphome_devices",
        AsyncMock(
            return_value=[
                {
                    "device_id": "node-1",
                    "manufacturer": None,
                    "model": None,
                    "sw_version": None,
                }
            ]
        ),
    ):
        assert not await async_refresh_target_metadata(hass, entry)

    assert entry.data[CONF_TARGETS] == [target]


async def test_migrate_entry_splits_legacy_targets(hass: HomeAssistant) -> None:
    """Test legacy v1 entries are migrated into typed entries."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Connectivity Monitor",
        version=1,
        data={
            CONF_TARGETS: [
                {
                    CONF_HOST: "192.168.1.10",
                    CONF_PROTOCOL: PROTOCOL_ICMP,
                    "device_name": "Router",
                },
                {
                    CONF_PROTOCOL: PROTOCOL_ZHA,
                    CONF_HOST: "zha:00:11:22:33:44:55:66:77",
                    CONF_ZHA_IEEE: "00:11:22:33:44:55:66:77",
                    "device_name": "Door Sensor",
                },
                {
                    CONF_PROTOCOL: PROTOCOL_MATTER,
                    CONF_HOST: "matter:1-1234",
                    "matter_node_id": "1-1234",
                    "device_name": "Thermostat",
                },
                {
                    CONF_PROTOCOL: PROTOCOL_ESPHOME,
                    CONF_HOST: "esphome:living-room-air-purifier",
                    CONF_ESPHOME_DEVICE_ID: "living-room-air-purifier",
                    "device_name": "Air Purifier",
                },
                {
                    CONF_PROTOCOL: PROTOCOL_BLUETOOTH,
                    CONF_HOST: "bluetooth:AA:BB:CC:DD:EE:FF",
                    CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
                    "device_name": "Key Tracker",
                },
            ],
            CONF_INTERVAL: 120,
            CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
        },
    )
    config_entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries.flow,
        "async_init",
        AsyncMock(return_value={"type": "create_entry"}),
    ) as mock_async_init:
        assert await async_migrate_entry(hass, config_entry)
        await hass.async_block_till_done()

    assert config_entry.version == 2
    assert config_entry.title == "Network Monitor"
    assert config_entry.unique_id == "connectivity_monitor_network"
    assert config_entry.data == {
        CONF_TARGETS: [
            {
                CONF_HOST: "192.168.1.10",
                CONF_PROTOCOL: PROTOCOL_ICMP,
                "device_name": "Router",
            }
        ],
        CONF_INTERVAL: 120,
        CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
    }
    assert mock_async_init.await_args_list == [
        call(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_TARGETS: [
                    {
                        CONF_PROTOCOL: PROTOCOL_ZHA,
                        CONF_HOST: "zha:00:11:22:33:44:55:66:77",
                        CONF_ZHA_IEEE: "00:11:22:33:44:55:66:77",
                        "device_name": "Door Sensor",
                    }
                ],
                CONF_INTERVAL: 120,
                CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
                "entry_type": "zha",
            },
        ),
        call(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_TARGETS: [
                    {
                        CONF_PROTOCOL: PROTOCOL_MATTER,
                        CONF_HOST: "matter:1-1234",
                        "matter_node_id": "1-1234",
                        "device_name": "Thermostat",
                    }
                ],
                CONF_INTERVAL: 120,
                CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
                "entry_type": "matter",
            },
        ),
        call(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_TARGETS: [
                    {
                        CONF_PROTOCOL: PROTOCOL_ESPHOME,
                        CONF_HOST: "esphome:living-room-air-purifier",
                        CONF_ESPHOME_DEVICE_ID: "living-room-air-purifier",
                        "device_name": "Air Purifier",
                    }
                ],
                CONF_INTERVAL: 120,
                CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
                "entry_type": "esphome",
            },
        ),
        call(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_TARGETS: [
                    {
                        CONF_PROTOCOL: PROTOCOL_BLUETOOTH,
                        CONF_HOST: "bluetooth:AA:BB:CC:DD:EE:FF",
                        CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
                        "device_name": "Key Tracker",
                    }
                ],
                CONF_INTERVAL: 120,
                CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
                "entry_type": "bluetooth",
            },
        ),
    ]


async def test_async_setup_updates_existing_lovelace_resource(
    hass: HomeAssistant,
) -> None:
    """Test setup updates an existing Lovelace card resource to the current version."""
    resources = SimpleNamespace(
        async_load=AsyncMock(),
        async_items=lambda: [
            {
                "id": "resource-id",
                "url": "/connectivity_monitor/connectivity_monitor_card.js?v=old",
            }
        ],
        async_update_item=AsyncMock(),
        async_create_item=AsyncMock(),
    )
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)
    http = SimpleNamespace(async_register_static_paths=AsyncMock())

    with patch.object(hass, "http", http, create=True):
        assert await async_setup(hass, {})
        hass.bus.async_fire("homeassistant_started")
        await hass.async_block_till_done()

    assert http.async_register_static_paths.await_count == 1
    resources.async_load.assert_awaited_once()
    resources.async_update_item.assert_awaited_once_with(
        "resource-id",
        {"url": f"/connectivity_monitor/connectivity_monitor_card.js?v={VERSION}"},
    )
    resources.async_create_item.assert_not_called()


async def test_async_setup_creates_lovelace_resource_when_missing(
    hass: HomeAssistant,
) -> None:
    """Test setup creates the Lovelace card resource when none exists."""
    resources = SimpleNamespace(
        async_load=AsyncMock(),
        async_items=list,
        async_update_item=AsyncMock(),
        async_create_item=AsyncMock(),
    )
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)

    with patch.object(hass, "http", http, create=True):
        assert await async_setup(hass, {})
        hass.bus.async_fire("homeassistant_started")
        await hass.async_block_till_done()

    resources.async_load.assert_awaited_once()
    resources.async_update_item.assert_not_called()
    resources.async_create_item.assert_awaited_once_with(
        {
            "res_type": "module",
            "url": f"/connectivity_monitor/connectivity_monitor_card.js?v={VERSION}",
        }
    )


async def test_async_setup_handles_static_path_registration_error(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test setup logs and continues if static path registration fails."""
    http = SimpleNamespace(
        async_register_static_paths=AsyncMock(side_effect=OSError("boom"))
    )

    with (
        patch.object(hass, "http", http, create=True),
        caplog.at_level(logging.WARNING),
    ):
        assert await async_setup(hass, {})

    assert "could not register static path" in caplog.text


async def test_async_setup_skips_lovelace_registration_without_data(
    hass: HomeAssistant,
) -> None:
    """Test setup skips Lovelace resource registration when data is unavailable."""
    http = SimpleNamespace(async_register_static_paths=AsyncMock())

    with patch.object(hass, "http", http, create=True):
        assert await async_setup(hass, {})
        hass.bus.async_fire("homeassistant_started")
        await hass.async_block_till_done()

    assert http.async_register_static_paths.await_count == 1


async def test_async_setup_skips_lovelace_registration_without_resources(
    hass: HomeAssistant,
) -> None:
    """Test setup skips Lovelace resource registration when resources are unavailable."""
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    hass.data[LOVELACE_DATA] = SimpleNamespace()

    with patch.object(hass, "http", http, create=True):
        assert await async_setup(hass, {})
        hass.bus.async_fire("homeassistant_started")
        await hass.async_block_till_done()

    assert http.async_register_static_paths.await_count == 1


async def test_async_setup_skips_existing_current_lovelace_resource(
    hass: HomeAssistant,
) -> None:
    """Test setup does nothing when the current Lovelace resource already exists."""
    current_url = f"/connectivity_monitor/connectivity_monitor_card.js?v={VERSION}"
    resources = SimpleNamespace(
        async_load=AsyncMock(),
        async_items=lambda: [{"id": "resource-id", "url": current_url}],
        async_update_item=AsyncMock(),
        async_create_item=AsyncMock(),
    )
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)

    with patch.object(hass, "http", http, create=True):
        assert await async_setup(hass, {})
        hass.bus.async_fire("homeassistant_started")
        await hass.async_block_till_done()

    resources.async_load.assert_awaited_once()
    resources.async_update_item.assert_not_called()
    resources.async_create_item.assert_not_called()


async def test_async_setup_logs_lovelace_registration_error(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test setup logs and continues if Lovelace resource registration raises."""
    resources = SimpleNamespace(async_load=AsyncMock())
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)

    with (
        patch.object(hass, "http", http, create=True),
        caplog.at_level(logging.WARNING),
    ):
        assert await async_setup(hass, {})
        hass.bus.async_fire("homeassistant_started")
        await hass.async_block_till_done()

    assert "could not register Lovelace resource" in caplog.text


async def test_async_reload_entry_reloads_config_entry(
    hass: HomeAssistant,
    network_config_entry: MockConfigEntry,
) -> None:
    """Test reload delegates to unload and setup for the config entry."""
    with (
        patch(
            "custom_components.connectivity_monitor.async_unload_entry",
            AsyncMock(return_value=True),
        ) as mock_unload_entry,
        patch(
            "custom_components.connectivity_monitor.async_setup_entry",
            AsyncMock(return_value=True),
        ) as mock_setup_entry,
    ):
        await async_reload_entry(hass, network_config_entry)

    mock_unload_entry.assert_awaited_once_with(hass, network_config_entry)
    mock_setup_entry.assert_awaited_once_with(hass, network_config_entry)
