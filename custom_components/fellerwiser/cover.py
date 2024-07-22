from __future__ import annotations

import logging

import requests
import websockets
import asyncio
import json
import socket
import math


import voluptuous as vol
from .const import (
    DOMAIN,
)

# Import the device class from the component that you want to support
import homeassistant.helpers.config_validation as cv
from homeassistant.components.cover import (
    ATTR_POSITION, ATTR_TILT_POSITION, PLATFORM_SCHEMA, CoverEntity, CoverEntityFeature
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

async def hello(covers, hass, host, apikey):
    ip = host

    while True:
    # outer loop restarted every time the connection fails
        _LOGGER.info('Creating new connection...')
        try:
            async with websockets.connect("ws://"+ip+"/api", extra_headers={'authorization':'Bearer ' + apikey}, ping_timeout=None) as ws:
                while True:
                # listener loop
                    try:
                        result = await asyncio.wait_for(ws.recv(), timeout=None)
                    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                        try:
                            pong = await ws.ping()
                            await asyncio.wait_for(pong, timeout=None)
                            _LOGGER.info('Ping OK, keeping connection alive...')
                            continue
                        except:
                            _LOGGER.info(
                                'Ping error - retrying connection in {} sec (Ctrl-C to quit)'.format(10))
                            await asyncio.sleep(10)
                            break
                    _LOGGER.info('Server said > {}'.format(result))
                    data = json.loads(result)     
                    for l in covers:
                        if l.unique_id == "cover-"+str(data["load"]["id"]):
                            _LOGGER.info("found entity to update")
                            l.updateExternal(data["load"]["state"]["level"], data["load"]["state"]["moving"], data["load"]["state"]["tilt"])
        except socket.gaierror:
            _LOGGER.info(
                'Socket error - retrying connection in {} sec (Ctrl-C to quit)'.format(10))
            await asyncio.sleep(10)
            continue
        except ConnectionRefusedError:
            _LOGGER.info('Nobody seems to listen to this endpoint. Please check the URL.')
            _LOGGER.info('Retrying connection in {} sec (Ctrl-C to quit)'.format(10))
            await asyncio.sleep(10)
            continue
        except KeyError:
            _LOGGER.info("KeyError")
            continue

def updatedata(host, apikey):
    #ip = "192.168.0.18"
    ip = host
    key = apikey
    return requests.get("http://"+ip+"/api/loads", headers= {'authorization':'Bearer ' + key})

async def async_setup_entry(hass, entry, async_add_entities):
    host = entry.data['host']
    apikey = entry.data['apikey']

    _LOGGER.info("---------------------------------------------- %s %s", host, apikey)

    response = await hass.async_add_executor_job(updatedata, host, apikey)

    loads = response.json()

    covers= []
    for value in loads["data"]:
        if value["type"] == "motor":
            covers.append(FellerCover(value, host, apikey))

    asyncio.get_event_loop().create_task(hello(covers, hass, host, apikey))
    async_add_entities(covers, True)


class FellerCover(CoverEntity):

    def __init__(self, data, host, apikey) -> None:
        self._data = data
        self._name = data["name"]
        self._id = str(data["id"])
        self._is_opening = False
        self._is_closing = False
        self._is_opened = False
        self._is_closed = False
        self._is_partially_opened = False
        self._position = None
        self._tilt = None
        self._host = host
        self._apikey = apikey

    @property
    def name(self) -> str:
        return self._name

    @property
    def unique_id(self):
        return "cover-" + self._id

    @property
    def current_cover_position(self):
        return self._position
    
    @property
    def current_cover_tilt_position(self):
        return self._tilt

    @property
    def is_opening(self) -> bool | None:
        return self._is_opening

    @property
    def is_closing(self) -> bool | None:
        return self._is_closing

    @property
    def is_opened(self) -> bool | None:
        return self._is_opened

    @property
    def is_closed(self) -> bool | None:
        return self._is_closed

    @property
    def is_partially_opened(self) -> bool | None:
        return self._is_partially_opened
    
    @property
    def should_poll(self) -> bool | None:
        return False
    
    @property
    def supported_features(self):
        return (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION | CoverEntityFeature.STOP | CoverEntityFeature.SET_TILT_POSITION | CoverEntityFeature.OPEN_TILT | CoverEntityFeature.CLOSE_TILT
        )

    def open_cover(self, **kwargs: Any) -> None:
        self._position = kwargs.get(ATTR_POSITION, 100)
        ip = self._host
        response = requests.put("http://"+ip+"/api/loads/"+self._id+"/target_state", headers= {'authorization':'Bearer ' + self._apikey}, json={'level': 0})
        _LOGGER.info(response.json())
        self._state = True
        self._position = 100-(response.json()["data"]["target_state"]["level"]/100)

    def close_cover(self, **kwargs: Any) -> None:
        self._position = kwargs.get(ATTR_POSITION, 100)
        ip = self._host
        response = requests.put("http://"+ip+"/api/loads/"+self._id+"/target_state", headers= {'authorization':'Bearer ' + self._apikey}, json={'level': 10000})
        _LOGGER.info(response.json())
        self._state = True
        self._position = 100-(response.json()["data"]["target_state"]["level"]/100)

    def set_cover_position(self, **kwargs: Any) -> None:
        self._position = kwargs.get(ATTR_POSITION, 100)
        ip = self._host
        response = requests.put("http://"+ip+"/api/loads/"+self._id+"/target_state", headers= {'authorization':'Bearer ' + self._apikey}, json={'level': (100-self._position)*100})
        _LOGGER.info(response.json())
        self._state = True
        self._position = 100-(response.json()["data"]["target_state"]["level"]/100)

    def stop_cover(self, **kwargs: Any) -> None:
        ip = self._host
        response = requests.put("http://"+ip+"/api/loads/"+self._id+"/ctrl", headers= {'authorization':'Bearer ' + self._apikey}, json={'button': "stop", 'event': 'click'})
        _LOGGER.info(response.json())

    def open_cover_tilt(self, **kwargs: Any) -> None:
        ip = self._host
        response = requests.put("http://"+ip+"/api/loads/"+self._id+"/ctrl", headers= {'authorization':'Bearer ' + self._apikey}, json={'button': "up", 'event': 'click'})
        _LOGGER.info(response.json())

    def close_cover_tilt(self, **kwargs: Any) -> None:
        ip = self._host
        response = requests.put("http://"+ip+"/api/loads/"+self._id+"/ctrl", headers= {'authorization':'Bearer ' + self._apikey}, json={'button': "down", 'event': 'click'})
        _LOGGER.info(response.json())

    def set_cover_tilt_position(self, **kwargs: Any) -> None:
        self._tilt = kwargs.get(ATTR_TILT_POSITION, 0)
        ip = self._host
        response = requests.put("http://"+ip+"/api/loads/"+self._id+"/target_state", headers= {'authorization':'Bearer ' + self._apikey}, json={'tilt': self.translate_cover_tilt_position(self._tilt, (0, 100), (0, 9))})
        _LOGGER.info(response.json())
        self._state = True
        self._tilt = self.translate_cover_tilt_position(response.json()["data"]["target_state"]["tilt"])

    #ha: 0 = closed/no tilt, 100 = open/max tilt
    #feller: 0 = closed/no tilt, 9 = open/max tilt
    #tilt over 4 has no effect in my installation!
    @staticmethod
    def translate_cover_tilt_position(value, src_range=(0, 9), tgt_range=(0, 100)):
        src_min, src_max = src_range
        tgt_min, tgt_max = tgt_range
        
        scale = (tgt_max - tgt_min) / (src_max - src_min)
        translated_value = tgt_min + (value - src_min) * scale
    
        return math.floor(translated_value) # round to the nearest int

    def updatestate(self):
        ip = self._host
        # _LOGGER.info("requesting http://"+ip+"/api/loads/"+self._id)
        return requests.get("http://"+ip+"/api/loads/"+self._id, headers= {'authorization':'Bearer ' + self._apikey})


    def update(self) -> None:
        response = self.updatestate()
        load = response.json()
        _LOGGER.info(load)

        #ha: 100 = open, 0 = closed
        #feller: 10000 = closed, 0 = open
        self._position = 100-(load["data"]["state"]["level"]/100)

        #ha: 100 = open, 0 = closed
        #feller: 0 = closed, 9 = open
        self._tilt = self.translate_cover_tilt_position(load["data"]["state"]["tilt"])

        if load["data"]["state"]["moving"] == "stop":
            self._is_closing = False
            self._is_opening = False
        if load["data"]["state"]["moving"]  == "up":
            self._is_closing = False
            self._is_opening = True
        if load["data"]["state"]["moving"] == "down":
            self._is_closing = True
            self._is_opening = False

        if self._position >= 100:
            self._is_closed = False
            self._is_opened = True
            self._is_partially_opened = False
        elif self._position <= 0:
            self._is_closed = True
            self._is_opened = False
            self._is_partially_opened = False
        else:
            self._is_closed = False
            self._is_opened = False
            self._is_partially_opened = True
    
    def updateExternal(self, position, moving, tilt):
        self._position = 100-(position/100)
        self._tilt = self.translate_cover_tilt_position(tilt)

        if moving == "stop":
            self._is_closing = False
            self._is_opening = False
        if moving == "up":
            self._is_closing = False
            self._is_opening = True
        if moving == "down":
            self._is_closing = True
            self._is_opening = False

        if self._position >= 100:
            self._is_closed = False
            self._is_opened = True
            self._is_partially_opened = False
        elif self._position <= 0:
            self._is_closed = True
            self._is_opened = False
            self._is_partially_opened = False
        else:
            self._is_closed = False
            self._is_opened = False
            self._is_partially_opened = True

        self.schedule_update_ha_state()
