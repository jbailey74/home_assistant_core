"""Support for the Airzone Cloud climate."""
from __future__ import annotations

from typing import Any, Final

from aioairzone_cloud.common import OperationAction, OperationMode, TemperatureUnit
from aioairzone_cloud.const import (
    API_MODE,
    API_OPTS,
    API_PARAMS,
    API_POWER,
    API_SETPOINT,
    API_UNITS,
    API_VALUE,
    AZD_ACTION,
    AZD_AIDOOS,
    AZD_GROUPS,
    AZD_HUMIDITY,
    AZD_INSTALLATIONS,
    AZD_MASTER,
    AZD_MODE,
    AZD_MODES,
    AZD_NUM_DEVICES,
    AZD_NUM_GROUPS,
    AZD_POWER,
    AZD_TEMP,
    AZD_TEMP_SET,
    AZD_TEMP_SET_MAX,
    AZD_TEMP_SET_MIN,
    AZD_TEMP_STEP,
    AZD_ZONES,
)

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AirzoneUpdateCoordinator
from .entity import (
    AirzoneAidooEntity,
    AirzoneEntity,
    AirzoneGroupEntity,
    AirzoneInstallationEntity,
    AirzoneZoneEntity,
)

HVAC_ACTION_LIB_TO_HASS: Final[dict[OperationAction, HVACAction]] = {
    OperationAction.COOLING: HVACAction.COOLING,
    OperationAction.DRYING: HVACAction.DRYING,
    OperationAction.FAN: HVACAction.FAN,
    OperationAction.HEATING: HVACAction.HEATING,
    OperationAction.IDLE: HVACAction.IDLE,
    OperationAction.OFF: HVACAction.OFF,
}
HVAC_MODE_LIB_TO_HASS: Final[dict[OperationMode, HVACMode]] = {
    OperationMode.STOP: HVACMode.OFF,
    OperationMode.COOLING: HVACMode.COOL,
    OperationMode.COOLING_AIR: HVACMode.COOL,
    OperationMode.COOLING_RADIANT: HVACMode.COOL,
    OperationMode.COOLING_COMBINED: HVACMode.COOL,
    OperationMode.HEATING: HVACMode.HEAT,
    OperationMode.HEAT_AIR: HVACMode.HEAT,
    OperationMode.HEAT_RADIANT: HVACMode.HEAT,
    OperationMode.HEAT_COMBINED: HVACMode.HEAT,
    OperationMode.EMERGENCY_HEAT: HVACMode.HEAT,
    OperationMode.VENTILATION: HVACMode.FAN_ONLY,
    OperationMode.DRY: HVACMode.DRY,
    OperationMode.AUTO: HVACMode.HEAT_COOL,
}
HVAC_MODE_HASS_TO_LIB: Final[dict[HVACMode, OperationMode]] = {
    HVACMode.OFF: OperationMode.STOP,
    HVACMode.COOL: OperationMode.COOLING,
    HVACMode.HEAT: OperationMode.HEATING,
    HVACMode.FAN_ONLY: OperationMode.VENTILATION,
    HVACMode.DRY: OperationMode.DRY,
    HVACMode.HEAT_COOL: OperationMode.AUTO,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Airzone climate from a config_entry."""
    coordinator: AirzoneUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[AirzoneClimate] = []

    # Aidoos
    for aidoo_id, aidoo_data in coordinator.data.get(AZD_AIDOOS, {}).items():
        entities.append(
            AirzoneAidooClimate(
                coordinator,
                aidoo_id,
                aidoo_data,
            )
        )

    # Groups
    for group_id, group_data in coordinator.data.get(AZD_GROUPS, {}).items():
        if group_data[AZD_NUM_DEVICES] > 1:
            entities.append(
                AirzoneGroupClimate(
                    coordinator,
                    group_id,
                    group_data,
                )
            )

    # Installations
    for inst_id, inst_data in coordinator.data.get(AZD_INSTALLATIONS, {}).items():
        if inst_data[AZD_NUM_GROUPS] > 1:
            entities.append(
                AirzoneInstallationClimate(
                    coordinator,
                    inst_id,
                    inst_data,
                )
            )

    # Zones
    for zone_id, zone_data in coordinator.data.get(AZD_ZONES, {}).items():
        entities.append(
            AirzoneZoneClimate(
                coordinator,
                zone_id,
                zone_data,
            )
        )

    async_add_entities(entities)


class AirzoneClimate(AirzoneEntity, ClimateEntity):
    """Define an Airzone Cloud climate."""

    _attr_name = None
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update climate attributes."""
        self._attr_current_temperature = self.get_airzone_value(AZD_TEMP)
        self._attr_current_humidity = self.get_airzone_value(AZD_HUMIDITY)
        self._attr_hvac_action = HVAC_ACTION_LIB_TO_HASS[
            self.get_airzone_value(AZD_ACTION)
        ]
        if self.get_airzone_value(AZD_POWER):
            self._attr_hvac_mode = HVAC_MODE_LIB_TO_HASS[
                self.get_airzone_value(AZD_MODE)
            ]
        else:
            self._attr_hvac_mode = HVACMode.OFF
        self._attr_max_temp = self.get_airzone_value(AZD_TEMP_SET_MAX)
        self._attr_min_temp = self.get_airzone_value(AZD_TEMP_SET_MIN)
        self._attr_target_temperature = self.get_airzone_value(AZD_TEMP_SET)


class AirzoneDeviceClimate(AirzoneClimate):
    """Define an Airzone Cloud Device base class."""

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        params = {
            API_POWER: {
                API_VALUE: True,
            },
        }
        await self._async_update_params(params)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        params = {
            API_POWER: {
                API_VALUE: False,
            },
        }
        await self._async_update_params(params)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        params: dict[str, Any] = {}
        if ATTR_TEMPERATURE in kwargs:
            params[API_SETPOINT] = {
                API_VALUE: kwargs[ATTR_TEMPERATURE],
                API_OPTS: {
                    API_UNITS: TemperatureUnit.CELSIUS.value,
                },
            }
        await self._async_update_params(params)


class AirzoneDeviceGroupClimate(AirzoneClimate):
    """Define an Airzone Cloud DeviceGroup base class."""

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        params = {
            API_PARAMS: {
                API_POWER: True,
            },
        }
        await self._async_update_params(params)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        params = {
            API_PARAMS: {
                API_POWER: False,
            },
        }
        await self._async_update_params(params)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        params: dict[str, Any] = {}
        if ATTR_TEMPERATURE in kwargs:
            params[API_PARAMS] = {
                API_SETPOINT: kwargs[ATTR_TEMPERATURE],
            }
            params[API_OPTS] = {
                API_UNITS: TemperatureUnit.CELSIUS.value,
            }
        await self._async_update_params(params)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        params: dict[str, Any] = {
            API_PARAMS: {},
        }
        if hvac_mode == HVACMode.OFF:
            params[API_PARAMS][API_POWER] = False
        else:
            mode = HVAC_MODE_HASS_TO_LIB[hvac_mode]
            params[API_PARAMS][API_MODE] = mode.value
            params[API_PARAMS][API_POWER] = True
        await self._async_update_params(params)


class AirzoneAidooClimate(AirzoneAidooEntity, AirzoneDeviceClimate):
    """Define an Airzone Cloud Aidoo climate."""

    def __init__(
        self,
        coordinator: AirzoneUpdateCoordinator,
        aidoo_id: str,
        aidoo_data: dict,
    ) -> None:
        """Initialize Airzone Cloud Aidoo climate."""
        super().__init__(coordinator, aidoo_id, aidoo_data)

        self._attr_unique_id = aidoo_id
        self._attr_target_temperature_step = self.get_airzone_value(AZD_TEMP_STEP)
        self._attr_hvac_modes = [
            HVAC_MODE_LIB_TO_HASS[mode] for mode in self.get_airzone_value(AZD_MODES)
        ]
        if HVACMode.OFF not in self._attr_hvac_modes:
            self._attr_hvac_modes += [HVACMode.OFF]

        self._async_update_attrs()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        params: dict[str, Any] = {}
        if hvac_mode == HVACMode.OFF:
            params[API_POWER] = {
                API_VALUE: False,
            }
        else:
            mode = HVAC_MODE_HASS_TO_LIB[hvac_mode]
            params[API_MODE] = {
                API_VALUE: mode.value,
            }
            params[API_POWER] = {
                API_VALUE: True,
            }
        await self._async_update_params(params)


class AirzoneGroupClimate(AirzoneGroupEntity, AirzoneDeviceGroupClimate):
    """Define an Airzone Cloud Group climate."""

    def __init__(
        self,
        coordinator: AirzoneUpdateCoordinator,
        group_id: str,
        group_data: dict,
    ) -> None:
        """Initialize Airzone Cloud Group climate."""
        super().__init__(coordinator, group_id, group_data)

        self._attr_unique_id = group_id
        self._attr_target_temperature_step = self.get_airzone_value(AZD_TEMP_STEP)
        self._attr_hvac_modes = [
            HVAC_MODE_LIB_TO_HASS[mode] for mode in self.get_airzone_value(AZD_MODES)
        ]
        if HVACMode.OFF not in self._attr_hvac_modes:
            self._attr_hvac_modes += [HVACMode.OFF]

        self._async_update_attrs()


class AirzoneInstallationClimate(AirzoneInstallationEntity, AirzoneDeviceGroupClimate):
    """Define an Airzone Cloud Installation climate."""

    def __init__(
        self,
        coordinator: AirzoneUpdateCoordinator,
        inst_id: str,
        inst_data: dict,
    ) -> None:
        """Initialize Airzone Cloud Installation climate."""
        super().__init__(coordinator, inst_id, inst_data)

        self._attr_unique_id = inst_id
        self._attr_target_temperature_step = self.get_airzone_value(AZD_TEMP_STEP)
        self._attr_hvac_modes = [
            HVAC_MODE_LIB_TO_HASS[mode] for mode in self.get_airzone_value(AZD_MODES)
        ]
        if HVACMode.OFF not in self._attr_hvac_modes:
            self._attr_hvac_modes += [HVACMode.OFF]

        self._async_update_attrs()


class AirzoneZoneClimate(AirzoneZoneEntity, AirzoneDeviceClimate):
    """Define an Airzone Cloud Zone climate."""

    def __init__(
        self,
        coordinator: AirzoneUpdateCoordinator,
        system_zone_id: str,
        zone_data: dict,
    ) -> None:
        """Initialize Airzone Cloud Zone climate."""
        super().__init__(coordinator, system_zone_id, zone_data)

        self._attr_unique_id = system_zone_id
        self._attr_target_temperature_step = self.get_airzone_value(AZD_TEMP_STEP)
        self._attr_hvac_modes = [
            HVAC_MODE_LIB_TO_HASS[mode] for mode in self.get_airzone_value(AZD_MODES)
        ]
        if HVACMode.OFF not in self._attr_hvac_modes:
            self._attr_hvac_modes += [HVACMode.OFF]

        self._async_update_attrs()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        slave_raise = False

        params: dict[str, Any] = {}
        if hvac_mode == HVACMode.OFF:
            params[API_POWER] = {
                API_VALUE: False,
            }
        else:
            mode = HVAC_MODE_HASS_TO_LIB[hvac_mode]
            cur_mode = self.get_airzone_value(AZD_MODE)
            if hvac_mode != HVAC_MODE_LIB_TO_HASS[cur_mode]:
                if self.get_airzone_value(AZD_MASTER):
                    params[API_MODE] = {
                        API_VALUE: mode.value,
                    }
                else:
                    slave_raise = True
            params[API_POWER] = {
                API_VALUE: True,
            }

        await self._async_update_params(params)

        if slave_raise:
            raise HomeAssistantError(
                f"Mode can't be changed on slave zone {self.entity_id}"
            )
