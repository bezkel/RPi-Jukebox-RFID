# RPi-Jukebox-RFID Version 3
# Copyright (c) See file LICENSE in project root folder
"""
Provide connector functions to hook up to some kind of Jukebox functionality and change the output device's state
accordingly.

Connector functions can often be used for various output devices. Some connector functions are specific to
an output device type.
"""
import inspect
import itertools
import logging
from typing import List, Callable, Union, Optional

import gpiozero.tones

import components.volume
import components.rfid.reader
import components.gpio.gpioz.plugin
from components.gpio.gpioz.core.output_devices import LED, PWMLED, Buzzer, TonalBuzzer, RGBLED
from components.gpio.gpioz.core.converter import VolumeToRGB
from components.rfid.reader import RfidCardDetectState

logger = logging.getLogger('gpioz')

#: The tone to be used as buzz tone when the buzzer is an active buzzer
BUZZ_TONE = gpiozero.tones.Tone(1000)


def _check_device_type(device, device_types, functions: Union[Callable, List[Callable]]) -> Optional[Callable]:
    """
    Check device instance is among valid devices types and return according function

    :param device: Device instance
    :param device_types: Valid device classes
    :param functions: List of functions - one for each device class in identical order. If only one function
        is given, it is assumed that the same function is valid for all device classes
    :return: The respective device function on success, else None
    """
    func_list = itertools.repeat(functions, len(device_types)) if callable(functions) else functions
    for d, f in zip(device_types, func_list):
        if isinstance(device, d):
            func = f
            break
    else:
        func = None
        logger.error(f"({device.name}) Unsupported device type '{device.__class__.__name__}' for "
                     f"connection function '{inspect.stack()[1].function}'")
    return func


def register_rfid_callback(device):
    """
    Flash the output device once on successful RFID card detection and thrice if card ID is unknown

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.LED`
    * :class:`components.gpio.gpioz.core.output_devices.PWMLED`
    * :class:`components.gpio.gpioz.core.output_devices.RGBLED`
    * :class:`components.gpio.gpioz.core.output_devices.Buzzer`
    * :class:`components.gpio.gpioz.core.output_devices.TonalBuzzer`
    """

    def rfid_callback(card_id: str, state: RfidCardDetectState):
        if state == RfidCardDetectState.isRegistered:
            device.flash(on_time=0.1, n=1, tone=BUZZ_TONE)
        elif state == RfidCardDetectState.isUnkown:
            device.flash(on_time=0.1, off_time=0.1, n=3, tone=BUZZ_TONE)

    components.rfid.reader.rfid_card_detect_callbacks.register(
        _check_device_type(device, [LED, PWMLED, RGBLED, Buzzer, TonalBuzzer], rfid_callback))


def register_status_led_callback(device):
    """
    Turn LED on when Jukebox App has started

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.LED`
    * :class:`components.gpio.gpioz.core.output_devices.PWMLED`
    * :class:`components.gpio.gpioz.core.output_devices.RGBLED`
    """

    def set_status_led(state):
        if state > 1:
            device.flash(on_time=0.1, off_time=0.1, n=1, background=True)
        elif state == 1:
            device.on()
        else:
            device.off()

    components.gpio.gpioz.plugin.service_is_running_callbacks.register(
        _check_device_type(device, [LED, PWMLED, RGBLED], set_status_led))


def register_status_buzzer_callback(device):
    """
    Buzz once when Jukebox App has started, twice when closing down

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.Buzzer`
    * :class:`components.gpio.gpioz.core.output_devices.TonalBuzzer`
    """

    def set_status_buzzer(state):
        if state == 1:
            device.flash(on_time=1.0, n=1, tone=BUZZ_TONE)
        else:
            device.flash(on_time=0.5, off_time=0.2, n=2)

    components.gpio.gpioz.plugin.service_is_running_callbacks.register(
        _check_device_type(device, [Buzzer, TonalBuzzer], set_status_buzzer))


def register_status_tonalbuzzer_callback(device):
    """
    Buzz a multi-note melody when Jukebox App has started and when closing down

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.TonalBuzzer`
    """

    def set_status_buzzer(state):
        if state == 1:
            device.melody(on_time=0.1, off_time=0.05, tone=['G4', 'B4', 'D5', 'F#5'])
        else:
            # When closing down, do not push thread in background
            # Closing down will be faster than playing the melody and steal your device from underneath your feet!
            device.melody(on_time=0.1, off_time=0.05, tone=['F#5', 'B4', 'D4'], background=False)

    components.gpio.gpioz.plugin.service_is_running_callbacks.register(
        _check_device_type(device, [TonalBuzzer], set_status_buzzer))


def register_audio_sink_change_callback(device):
    """
    Turn LED on if secondary audio output is selected. If audio output change
    fails, blink thrice

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.LED`
    * :class:`components.gpio.gpioz.core.output_devices.PWMLED`
    * :class:`components.gpio.gpioz.core.output_devices.RGBLED`
    """

    def audio_sink_change_callback(alias, sink_name, sink_index, error_state):
        if error_state:
            device.flash(on_time=0.2, off_time=0.2, n=3, background=True)
        elif sink_index == 1:
            device.on()
        else:
            device.off()

    components.volume.pulse_control.on_output_change_callbacks.register(
        _check_device_type(device, [LED, PWMLED, RGBLED], audio_sink_change_callback))


def register_volume_led_callback(device):
    """
    Have a PWMLED change it's brightness according to current volume. LED flashes when minimum or maximum volume
    is reached. Minimum value is still a very dimly turned on LED (i.e. LED is never off).

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.PWMLED`
    """

    def audio_volume_change_callback(volume, is_min, is_max):
        # We need a non-linear scaling, to give a visually
        # constant brightness change across the volume range
        if is_min:
            volume = 1
        device.value = float(volume * volume) / 10000.0
        if is_min:
            device.flash(on_time=0.1, off_time=0, n=1)
        if is_max:
            device.flash(on_time=0.0, off_time=0.3, n=1)

    components.volume.pulse_control.on_volume_change_callbacks.register(
        _check_device_type(device, [PWMLED], audio_volume_change_callback))


def register_volume_buzzer_callback(device):
    """
    Sound a buzzer once when minimum or maximum value is reached

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.Buzzer`
    * :class:`components.gpio.gpioz.core.output_devices.TonalBuzzer`
    """

    def set_volume_buzzer(volume, is_min, is_max):
        if is_min or is_max:
            device.flash(on_time=0.1, off_time=0, n=1, tone=BUZZ_TONE)

    components.volume.pulse_control.on_volume_change_callbacks.register(
        _check_device_type(device, [Buzzer, TonalBuzzer], set_volume_buzzer))


def register_volume_rgbled_callback(device):
    """
    Have a :class:`RGBLED` change it's color according to current volume. LED flashes when minimum or maximum volume
    is reached.

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.RGBLED`
    """

    volume_to_rgb = VolumeToRGB(100, 120, 180)

    def audio_volume_change_callback(volume, is_min, is_max):
        device.value = volume_to_rgb(volume)
        if is_min or is_max:
            device.flash(on_time=0.1, off_time=0, n=1, color=volume_to_rgb.luminize(1, 1, 1))

    components.volume.pulse_control.on_volume_change_callbacks.register(
        _check_device_type(device, [RGBLED], audio_volume_change_callback))


def register_playback_led_callback(device):
    """
    Control an LED strip that fades in/out with music playback.

    The LED fades in slowly when a song starts and fades out when a song ends.
    On startup when the jukebox is ready, the LED pulses once for 1 second.

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.PWMLED`
    """
    import threading
    import time
    import jukebox.publishing as publishing

    # Track the current song to detect changes
    current_song = {'file': None, 'state': None}
    fade_lock = threading.Lock()

    def status_callback(state):
        """Pulse the LED once when the jukebox is ready"""
        if state == 1:
            device.flash(on_time=1.0, off_time=0, n=1, fade_in_time=0.3, fade_out_time=0.3, background=True)

    def playerstatus_callback(topic, status):
        """Handle player status updates to fade LED on song changes"""
        if not isinstance(status, dict):
            return

        with fade_lock:
            new_file = status.get('file')
            new_state = status.get('state')

            # Detect song change
            if new_file != current_song['file'] and new_file is not None:
                # Song has changed - fade in
                if new_state == 'play':
                    # Fade in over 2 seconds
                    device.pulse(fade_in_time=2.0, fade_out_time=0, n=1, background=True)
                    # After fade in, keep it on
                    def keep_on():
                        time.sleep(2.0)
                        device.on()
                    threading.Thread(target=keep_on, daemon=True).start()
                current_song['file'] = new_file

            # Detect playback stopping
            if new_state != current_song['state']:
                if new_state == 'stop' and current_song['state'] in ['play', 'pause']:
                    # Song ended - fade out over 2 seconds
                    device.pulse(fade_in_time=0, fade_out_time=2.0, n=1, background=True)
                current_song['state'] = new_state

    # Subscribe to player status updates
    def subscribe_thread():
        subscriber = publishing.Subscriber(url=None, topics='playerstatus')
        while True:
            try:
                topic, message = subscriber.receive()
                if message:  # Check if message is not empty (not a revocation)
                    playerstatus_callback(topic, message)
            except Exception as e:
                logger.error(f"Error in playback LED subscriber: {e.__class__.__name__}: {e}")
                break

    # Start subscriber thread
    thread = threading.Thread(target=subscribe_thread, daemon=True)
    thread.start()

    # Register for startup pulse
    components.gpio.gpioz.plugin.service_is_running_callbacks.register(
        _check_device_type(device, [PWMLED], status_callback))
