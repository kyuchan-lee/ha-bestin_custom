"""Light platform for BESTIN"""

from __future__ import annotations

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_MIREDS,
    ColorMode,
    DOMAIN as LIGHT_DOMAIN,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import NEW_LIGHT, LOGGER
from .device import BestinDevice
from .hub import BestinHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Setup light platform."""
    hub: BestinHub = BestinHub.get_hub(hass, entry)
    hub.entity_groups[LIGHT_DOMAIN] = set()

    @callback
    def async_add_light(devices=None):
        if devices is None:
            # Safely handle cases where hub.api is not yet initialized
            if hub.api:
                devices = hub.api.get_devices_from_domain(LIGHT_DOMAIN)
            else:
                devices = []

        entities = [
            BestinLight(device, hub) 
            for device in devices 
            if device.unique_id not in hub.entity_groups[LIGHT_DOMAIN]
        ]
        
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, hub.async_signal_new_device(NEW_LIGHT), async_add_light
        )
    )
    async_add_light()
    return True


class BestinLight(BestinDevice, LightEntity):
    """Define the Light."""
    TYPE = LIGHT_DOMAIN

    def __init__(self, device, hub):
        """Initialize the light."""
        super().__init__(device, hub)
        self._attr_min_mireds = 153 # ~6500K
        self._attr_max_mireds = 500 # ~2000K

    @property
    def supported_color_modes(self) -> set[ColorMode] | None:
        """Flag supported color modes."""
        if self.hub.gateway_type in ["AIO", "Gen2"]:
            # Only index 0 lights support dimming and color temperature
            if self.device_id.endswith("_0"):
                return {ColorMode.COLOR_TEMP, ColorMode.BRIGHTNESS}
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode | None:
        """Return the current color mode."""
        if self.hub.gateway_type in ["AIO", "Gen2"] and self.device_id.endswith("_0"):
            return ColorMode.COLOR_TEMP
        return ColorMode.ONOFF

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        state = self._device_info.state
        if isinstance(state, dict):
            return bool(state.get("state", False))
        return bool(state)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light."""
        state = self._device_info.state
        if isinstance(state, dict):
            val = state.get("brightness")
            if val is not None:
                if self.hub.gateway_type == "AIO":
                    return int(val * 25.5)
                return val
        return None

    @property
    def color_temp(self) -> int | None:
        """Return the color temperature in mireds."""
        state = self._device_info.state
        if isinstance(state, dict):
            val = state.get("color_temp")
            if val is not None and self.hub.gateway_type == "AIO" and 1 <= val <= 7:
                # 1 (Warmest) -> 500, 7 (Coolest) -> 153
                return int(500 - (val - 1) * (500 - 153) / 6)
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        mireds = self.color_temp
        if mireds:
            return int(1000000 / mireds)
        return None

    async def async_turn_on(self, **kwargs):
        """Turn on light."""
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            if self.hub.gateway_type == "AIO":
               val = max(1, min(10, round(brightness / 25.5)))
               await self.enqueue_command(brightness=val)
            else:
               await self.enqueue_command(brightness=brightness)
        elif ATTR_COLOR_TEMP_MIREDS in kwargs:
             mireds = kwargs.get(ATTR_COLOR_TEMP_MIREDS)
             if mireds:
                 if self.hub.gateway_type == "AIO":
                    val = max(1, min(7, round(7 - (mireds - 153) * 6 / (500 - 153))))
                    await self.enqueue_command(color_temp=val)
                 else:
                    await self.enqueue_command(color_temp=mireds)
        else:
            await self.enqueue_command(True)

    async def async_turn_off(self, **kwargs):
        """Turn off light."""
        await self.enqueue_command(False)
