"""Platform for light integration."""

from __future__ import annotations

import logging

import requests
import websockets
import asyncio
import json
import socket

import voluptuous as vol
from .const import (
    DOMAIN,
)

# Import the device class from the component that you want to support
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    LightEntity,
)

_LOGGER = logging.getLogger(__name__)


async def hello(lights, hass, host, apikey):
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
                    doUpdate = False

                    # dim/dali
                    if "flags" in data["load"]["state"]:
                        if "fading" in data["load"]["state"]["flags"]:
                            if data["load"]["state"]["flags"]["fading"] == 0:
                                doUpdate = True
                        else:
                            doUpdate = True
                    # onoff
                    else:
                        doUpdate = True
                    if doUpdate:
                        for l in lights:
                            if l.unique_id == "light-" + str(data["load"]["id"]):
                                _LOGGER.info("found entity to update")
                                l.updateExternal(data["load"]["state"]["bri"])
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


def updatedata(host, apikey):
    # ip = "192.168.0.18"
    ip = host
    key = apikey
    return requests.get(
        "http://" + ip + "/api/loads", headers={"authorization": "Bearer " + key}
    )

async def async_setup_entry(hass, entry, async_add_entities):
    host = entry.data["host"]
    apikey = entry.data["apikey"]

    _LOGGER.info("---------------------------------------------- %s %s", host, apikey)

    response = await hass.async_add_executor_job(updatedata, host, apikey)

    loads = response.json()

    lights = []
    for value in loads["data"]:
        if value["type"] in ["dim", "dali", "onoff"]:
            lights.append(FellerLight(value, host, apikey))

    asyncio.get_event_loop().create_task(hello(lights, hass, host, apikey))
    async_add_entities(lights, True)

class FellerLight(LightEntity):
    """Representation of an Awesome Light."""

    def __init__(self, data, host, apikey) -> None:
        """Initialize an AwesomeLight."""
        # Phasecut Dimmer {'name': '00005341_0', 'device': '00005341', 'channel': 0, 'type': 'dim', 'id': 14, 'unused': False}
        # DALI Dimmer {'name': '00005341_0', 'device': '00005341', 'channel': 0, 'type': 'dali', 'id': 14, 'unused': False}

        self._data = data
        self._name = data["name"]
        self._id = str(data["id"])
        self._state = None
        self._brightness = None
        self._host = host
        self._apikey = apikey
        self._type = data["type"]

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self):
        return "light-" + self._id

    @property
    def brightness(self):
        """Return the brightness of the light.
        This method is optional. Removing it indicates to Home Assistant
        that brightness is not supported for this light.
        """
        return self._brightness

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._state

    @property
    def should_poll(self) -> bool | None:
        return False

    @property
    def color_mode(self) -> str | None:
        if self._type == "onoff":
            return "onoff"
        return "brightness"

    @property
    def supported_color_modes(self) -> set | None:
        if self._type == "onoff":
            return {"onoff"}
        return {"brightness"}

    def turn_on(self, **kwargs: Any) -> None:
        """Instruct the light to turn on.

        You can skip the brightness part if your light does not support
        brightness control.
        """

        if not kwargs:
            ip = self._host
            response = requests.put(
                "http://" + ip + "/api/loads/" + self._id + "/ctrl",
                headers={"authorization": "Bearer " + self._apikey},
                json={"button": "on", "event": "click"},
            )
            _LOGGER.info(response.json())
            self._state = True
            response = requests.get(
                "http://" + ip + "/api/loads/" + self._id,
                headers={"authorization": "Bearer " + self._apikey},
            )
            self._brightness = int(
                (response.json()["data"]["state"]["bri"] / 10000) * 255
            )

        else:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            convertedBrightness = int((self._brightness / 255) * 10000)
            if convertedBrightness > 10000:
                convertedBrightness = 10000

            ip = self._host
            response = requests.put(
                "http://" + ip + "/api/loads/" + self._id + "/target_state",
                headers={"authorization": "Bearer " + self._apikey},
                json={"bri": convertedBrightness},
            )
            _LOGGER.info(response.json())
            self._state = True
            self._brightness = int(
                (response.json()["data"]["target_state"]["bri"] / 10000) * 255
            )

    def turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""
        ip = self._host
        self._oldbrightness = self._brightness
        response = requests.put(
            "http://" + ip + "/api/loads/" + self._id + "/ctrl",
            headers={"authorization": "Bearer " + self._apikey},
            json={"button": "off", "event": "click"},
        )
        _LOGGER.info(response.json())
        # {'data': {'id': 6, 'target_state': {'bri': 0}}, 'status': 'success'}
        self._state = False
        response = requests.get(
            "http://" + ip + "/api/loads/" + self._id,
            headers={"authorization": "Bearer " + self._apikey},
        )
        self._brightness = int((response.json()["data"]["state"]["bri"] / 10000) * 255)

    def updatestate(self):
        ip = self._host
        # _LOGGER.info("requesting http://"+ip+"/api/loads/"+self._id)
        return requests.get(
            "http://" + ip + "/api/loads/" + self._id,
            headers={"authorization": "Bearer " + self._apikey},
        )

    def update(self) -> None:
        """Fetch new state data for this light.
        This is the only method that should fetch new data for Home Assistant.
        """

        response = self.updatestate()
        load = response.json()
        _LOGGER.info(load)
        # 'data': {'id': 7, 'unused': False, 'name': '000086dd_0', 'state': {'bri': 0, 'flags': {'over_current': 0, 'fading': 0, 'noise': 0, 'direction': 1, 'over_temperature': 0}}, 'device': '000086dd', 'channel': 0, 'type': 'dim'}, 'status': 'success'}

        self._data = load["data"]
        if load["data"]["state"]["bri"] > 0:
            self._state = True
        else:
            self._state = False
        self._brightness = int((load["data"]["state"]["bri"] / 10000) * 255)

    def updateExternal(self, brightness):
        self._brightness = int((brightness / 10000) * 255)
        if self._brightness > 0:
            self._state = True
        else:
            self._state = False
        self.schedule_update_ha_state()
