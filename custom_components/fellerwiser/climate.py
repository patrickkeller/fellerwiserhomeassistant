"""Platform for climate integration."""

from __future__ import annotations

import logging

import requests
import websockets
import asyncio
import json
import socket

import voluptuous as vol

# Import the device class from the component that you want to support
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_HVAC_ACTION,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)

from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

_LOGGER = logging.getLogger(__name__)


async def hello(thermostats, hass, host, apikey):
    ip = host

    while True:
        # outer loop restarted every time the connection fails
        _LOGGER.info("Creating new connection...")
        try:
            async with websockets.connect(
                "ws://" + ip + "/api",
                additional_headers={"authorization": "Bearer " + apikey},
                ping_timeout=None,
            ) as ws:
                while True:
                    # listener loop
                    try:
                        result = await asyncio.wait_for(ws.recv(), timeout=None)
                    except (
                        asyncio.TimeoutError,
                        websockets.exceptions.ConnectionClosed,
                    ):
                        try:
                            pong = await ws.ping()
                            await asyncio.wait_for(pong, timeout=None)
                            _LOGGER.info("Ping OK, keeping connection alive...")
                            continue
                        except:
                            _LOGGER.info(
                                "Ping error - retrying connection in {} sec (Ctrl-C to quit)".format(
                                    10
                                )
                            )
                            await asyncio.sleep(10)
                            break
                    _LOGGER.info("Server said > {}".format(result))
                    data = json.loads(result)
                    for l in thermostats:
                        if l.unique_id == "thermostat-" + str(data["hvacgroup"]["id"]):
                            _LOGGER.info("found entity to update: %s", l.unique_id)
                            _LOGGER.info(
                                "Updating entity %s with %s",
                                l.unique_id,
                                data["hvacgroup"]["state"],
                            )
                            l.updateExternal(
                                # {"hvacgroup":{"id":87,"state":{"on":true,"flags":{"remote_controlled":0,"sensor_error":0,"valve_error":0,"noise":0,"output_on":0,"cooling":0},"boost_temperature":0,"heating_cooling_level":0,"unit":"C","ambient_temperature":25.4,"target_temperature":18.5}}}
                                data["hvacgroup"]["state"]["ambient_temperature"],
                                data["hvacgroup"]["state"]["target_temperature"],
                                data["state"]["on"],
                                data["hvacgroup"]["state"]["flags"]["cooling"],
                            )
        except socket.gaierror:
            _LOGGER.info(
                "Socket error - retrying connection in {} sec (Ctrl-C to quit)".format(
                    10
                )
            )
            await asyncio.sleep(10)
            continue
        except ConnectionRefusedError:
            _LOGGER.info(
                "Nobody seems to listen to this endpoint. Please check the URL."
            )
            _LOGGER.info("Retrying connection in {} sec (Ctrl-C to quit)".format(10))
            await asyncio.sleep(10)
            continue
        except KeyError:
            _LOGGER.info("KeyError")
            continue


def updatedata(host: str, apikey: str) -> dict:
    """Fetch HVAC group data from the API."""
    ip = host
    key = apikey
    response = requests.get(
        f"http://{ip}/api/hvacgroups", headers={"authorization": f"Bearer {key}"}
    )
    response.raise_for_status()
    return response.json()


async def async_setup_entry(hass, entry, async_add_entities):
    host = entry.data["host"]
    apikey = entry.data["apikey"]

    _LOGGER.info("---------------------------------------------- %s %s", host, apikey)

    hvacgroups = await hass.async_add_executor_job(updatedata, host, apikey)

    thermostats = []
    for value in hvacgroups["data"]:
        _LOGGER.info("Found thermostat: %s", value["name"])
        thermostats.append(FellerThermostat(value, host, apikey))

    asyncio.get_event_loop().create_task(hello(thermostats, hass, host, apikey))
    async_add_entities(thermostats, True)


class FellerThermostat(ClimateEntity):
    """A thermostat class for Feller."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, data, host, apikey) -> None:
        """Initialize the thermostat."""
        self._data = data
        self._name = data["name"]
        self._id = str(data["id"])
        self._host = host
        self._apikey = apikey
        self._is_on = True
        self._is_cooling = False
        # self._attr_current_temperature = data["name"]
        # self._attr_target_temperature = ATTR_TEMPERATURE
        # self._attr_target_temperature_high = ATTR_TARGET_TEMP_HIGH
        # self._attr_target_temperature_low = ATTR_TARGET_TEMP_LOW
        # self._attr_hvac_modes = HVACMode.HEAT_COOL
        # self._attr_hvac_mode = HVACMode.HEAT_COOL
        # self._attr_hvac_action = None

    @property
    def unique_id(self):
        return "thermostat-" + self._id

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def turn_on(self):
        return super().turn_on()

    @property
    def turn_off(self):
        return super().turn_off()

    @property
    def supported_features(self):
        """Return the supported features of the thermostat."""
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE
            # | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        )

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of supported HVAC modes."""
        return [HVACMode.HEAT_COOL]

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        if self._is_on:
            if self._is_cooling:
                return HVACMode.COOL
            else:
                return HVACMode.HEAT
        else:
            return HVACMode.OFF

    @property
    def hvac_action(self):
        """Return the current hvac action."""
        if self._is_on:
            if self._is_cooling:
                return HVACAction.COOLING
            else:
                return HVACAction.HEATING
        return HVACAction.OFF

    @property
    def is_cooling(self):
        """Return true if the thermostat is cooling."""
        if self._cooling == 1:
            return True
        elif self._cooling == 0:
            return False
        else:
            return False

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._target_temperature

    @property
    def target_temperature_high(self) -> float | None:
        """Return the high target temperature."""
        return self._target_temperature_high

    @property
    def target_temperature_low(self) -> float | None:
        """Return the low target temperature."""
        return self._target_temperature_low

    @property
    def is_on(self):
        """Return true if the thermostat is on."""
        return self._is_on

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        NotImplemented

    def set_temperature(self, **kwargs) -> None:
        """Set the target temperature."""
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            ip = self._host
        response = requests.put(
            "http://" + ip + "/api/hvacgroups/" + self._id + "/target_state",
            headers={"authorization": "Bearer " + self._apikey},
            json={"target_temperature": kwargs.get(ATTR_TEMPERATURE)},
        )
        self._target_temperature = response.json()["data"]["target_state"][
            "target_temperature"
        ]
        _LOGGER.info("Setting target temperature to %s", self._target_temperature)

    def update(self) -> None:
        response = self.updatestate()
        hvacgroup = response.json()

        self._current_temperature = hvacgroup["data"]["state"]["ambient_temperature"]
        self._target_temperature = hvacgroup["data"]["state"]["target_temperature"]
        # self._target_temperature_high = hvacgroup["data"]["max_temperature"]
        # self._target_temperature_low = hvacgroup["data"]["min_temperature"]
        self._is_on = hvacgroup["data"]["state"]["on"]
        self._cooling = hvacgroup["data"]["state"]["flags"]["cooling"]

    def updatestate(self):
        ip = self._host
        # _LOGGER.info("requesting http://"+ip+"/api/loads/"+self._id)
        return requests.get(
            "http://" + ip + "/api/hvacgroups/" + self._id,
            headers={"authorization": "Bearer " + self._apikey},
        )

    def updateExternal(self, ambient_temperature, target_temperature, state, cooling):
        """Update the thermostat with external values."""
        self._current_temperature = ambient_temperature
        self._target_temperature = target_temperature
        self._is_on = state
        self._cooling = cooling  # 0 = heating, 1 = cooling ??
        schedule_update_ha_state()