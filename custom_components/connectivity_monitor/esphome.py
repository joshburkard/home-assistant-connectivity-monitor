"""ESPHome device access helpers for Connectivity Monitor."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_ESPHOME_DEVICE_ID, CONF_PROTOCOL, CONF_TARGETS, PROTOCOL_ESPHOME

_LOGGER = logging.getLogger(__name__)

ESPHOME_DOMAIN = "esphome"


async def async_get_esphome_devices(hass: HomeAssistant) -> list[dict]:
    """Return a list of all ESPHome devices discovered in Home Assistant.

    Primary path: iterate loaded ESPHome config entries (one per node) and
    find the device registry entry associated with each.  This is the most
    reliable method because each ESPHome node has exactly one config entry.

    Fallback: scan the device registry for any device whose identifiers
    contain the 'esphome' domain (older HA / edge-case layout).

    The stable key stored as device_id is the config-entry entry_id so it
    survives device renames.
    """
    # pylint: disable=too-many-nested-blocks
    devices: list[dict] = []
    seen_device_registry_ids: set[str] = set()

    try:
        device_registry = dr.async_get(hass)

        # ── Primary path: one config entry per ESPHome node ───────────────────
        for entry in hass.config_entries.async_entries(ESPHOME_DOMAIN):
            if entry.state is not ConfigEntryState.LOADED:
                continue

            # Find the device that lists this config entry
            device_entry = None
            for de in dr.async_entries_for_config_entry(
                device_registry, entry.entry_id
            ):
                if de.config_entry_id == entry.entry_id:
                    # Prefer the device that also has an 'esphome' identifier
                    # when there are sub-devices (e.g. multi-device firmware).
                    has_esphome_id = any(
                        idf[0] == ESPHOME_DOMAIN for idf in de.identifiers
                    )
                    if has_esphome_id or device_entry is None:
                        device_entry = de
                    if has_esphome_id:
                        break

            if device_entry is None:
                _LOGGER.debug(
                    "ESPHome config entry '%s' (%s) has no associated device yet",
                    entry.title,
                    entry.entry_id,
                )
                continue

            if device_entry.id in seen_device_registry_ids:
                continue
            seen_device_registry_ids.add(device_entry.id)

            # Extract the real ESPHome identifier (e.g. MAC-based) so the sensor
            # can attach to the existing device rather than create a new one.
            esphome_identifier = (
                next(
                    (
                        str(idf[1])
                        for idf in device_entry.identifiers
                        if idf[0] == ESPHOME_DOMAIN
                    ),
                    None,
                )
                or entry.unique_id
            )  # entry.unique_id is the MAC for ESPHome config entries

            # Also grab the MAC from connections — used as a reliable fallback
            # in DeviceInfo so HA can always match the existing ESPHome device.
            mac_address = next(
                (str(con[1]) for con in device_entry.connections if con[0] == "mac"),
                None,
            )

            # Use entry_id as the stable device_id key
            device_id = entry.entry_id
            devices.append(
                {
                    "device_id": device_id,
                    "entry_id": entry.entry_id,
                    "esphome_identifier": esphome_identifier,
                    "esphome_mac": mac_address,
                    "name": (
                        device_entry.name_by_user
                        or device_entry.name
                        or entry.title
                        or device_id
                    ),
                    "model": device_entry.model,
                    "manufacturer": device_entry.manufacturer,
                    "sw_version": device_entry.sw_version,
                }
            )

        # ── Fallback for devices without a loaded ESPHome entry ───────────────
        if not devices:
            _LOGGER.debug(
                "ESPHome config-entry scan found no loaded devices; scanning "
                "the device registry"
            )
            for device_entry in device_registry.async_get_devices():
                esphome_identifier = next(
                    (
                        str(identifier[1])
                        for identifier in device_entry.identifiers
                        if identifier[0] == ESPHOME_DOMAIN
                    ),
                    None,
                )
                if (
                    esphome_identifier is None
                    or device_entry.id in seen_device_registry_ids
                ):
                    continue
                seen_device_registry_ids.add(device_entry.id)
                mac_address = next(
                    (
                        str(connection[1])
                        for connection in device_entry.connections
                        if connection[0] == "mac"
                    ),
                    None,
                )
                devices.append(
                    {
                        "device_id": device_entry.config_entry_id,
                        "entry_id": None,
                        "esphome_identifier": esphome_identifier,
                        "esphome_mac": mac_address,
                        "name": device_entry.name_by_user or device_entry.name,
                        "model": device_entry.model,
                        "manufacturer": device_entry.manufacturer,
                        "sw_version": device_entry.sw_version,
                    }
                )

    except (AttributeError, RuntimeError) as err:
        _LOGGER.warning("Could not enumerate ESPHome devices: %s", err)

    _LOGGER.debug("ESPHome devices found: %d", len(devices))
    return devices


async def async_refresh_target_metadata(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Refresh stored ESPHome metadata from the current device registry."""
    targets = config_entry.data.get(CONF_TARGETS, [])
    if not any(target.get(CONF_PROTOCOL) == PROTOCOL_ESPHOME for target in targets):
        return False

    devices = await async_get_esphome_devices(hass)
    devices_by_id: dict[str, dict] = {}
    for device in devices:
        for device_key in (
            device.get("device_id"),
            device.get("entry_id"),
            device.get("esphome_identifier"),
        ):
            if device_key:
                devices_by_id[str(device_key)] = device

    updated_targets = []
    changed = False
    for target in targets:
        updated_target = dict(target)
        if target.get(CONF_PROTOCOL) == PROTOCOL_ESPHOME:
            device_id = str(target.get(CONF_ESPHOME_DEVICE_ID, ""))
            device = devices_by_id.get(device_id)
            if device:
                for metadata_key in ("manufacturer", "model", "sw_version"):
                    value = device.get(metadata_key)
                    if value and updated_target.get(metadata_key) != value:
                        updated_target[metadata_key] = value
                        changed = True
        updated_targets.append(updated_target)

    if changed:
        hass.config_entries.async_update_entry(
            config_entry,
            data={**config_entry.data, CONF_TARGETS: updated_targets},
        )
        _LOGGER.info(
            "Connectivity Monitor: refreshed ESPHome metadata for config entry %s",
            config_entry.entry_id,
        )

    return changed


async def async_get_esphome_device_active(
    hass: HomeAssistant, device_id: str
) -> bool | None:
    """Return True if the ESPHome device has at least one available entity.

    A dedicated connectivity entity takes precedence over other entity states.
    Otherwise, any known and available entity indicates that the node is
    connected. Returns None when the device cannot be found at all.

    device_id is either a config-entry entry_id (primary) or an identifier
    value (fallback).
    """
    try:
        device_registry = dr.async_get(hass)
        entity_registry = er.async_get(hass)

        # ── Primary: look up by config-entry entry_id ─────────────────────────
        device_entry = None
        entry = hass.config_entries.async_get_entry(device_id)
        if entry is not None and entry.domain == ESPHOME_DOMAIN:
            for de in dr.async_entries_for_config_entry(
                device_registry, entry.entry_id
            ):
                if de.config_entry_id == entry.entry_id:
                    has_esphome_id = any(
                        idf[0] == ESPHOME_DOMAIN for idf in de.identifiers
                    )
                    if has_esphome_id or device_entry is None:
                        device_entry = de
                    if has_esphome_id:
                        break

        # ── Fallback: identifier-based lookup ─────────────────────────────────
        if device_entry is None:
            devices = device_registry.async_get_devices(
                identifiers={(ESPHOME_DOMAIN, device_id)}
            )
            device_entry = devices[0] if devices else None

        if device_entry is None:
            _LOGGER.debug("ESPHome device not found for device_id '%s'", device_id)
            return None

        # Gather all non-disabled entities belonging to the ESPHome integration.
        # Entities from other integrations (e.g. our own ESPHomeSensor) are
        # excluded so they don't cause a false-Active result.
        entities = [
            e
            for e in entity_registry.entities.values()
            if e.device_id == device_entry.id
            and not e.disabled
            and e.platform == ESPHOME_DOMAIN
        ]

        if not entities:
            _LOGGER.debug(
                "No enabled ESPHome entities found for device '%s'", device_id
            )
            return None

        connectivity_states = []
        has_available_entity = False
        for entity_entry in entities:
            state = hass.states.get(entity_entry.entity_id)
            if state is None:
                continue
            if state.attributes.get("device_class") == "connectivity":
                connectivity_states.append(state.state)
            elif state.state not in ("unknown", "unavailable"):
                has_available_entity = True

        if connectivity_states:
            return "on" in connectivity_states
        if has_available_entity:
            return True

    except (AttributeError, RuntimeError) as err:
        _LOGGER.warning(
            "Failed to determine active state for ESPHome device '%s': %s",
            device_id,
            err,
        )
        return None
    else:
        return False
