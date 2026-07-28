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
import threading
import time
from typing import List, Callable, Union, Optional

import gpiozero.tones

import components.volume
import components.rfid.reader
import components.gpio.gpioz.plugin
from components.gpio.gpioz.core.output_devices import LED, PWMLED, Buzzer, TonalBuzzer, RGBLED
from components.gpio.gpioz.core.converter import VolumeToRGB
from components.rfid.reader import RfidCardDetectState

logger = logging.getLogger('jb.gpioz.connectivity')

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


class _SongActivityLED:
    """Drive a PWMLED as playback indicator with smooth, interruptible fades.

    All brightness changes are executed by a single worker thread which
    processes a small sequence of (target, fade_time, hold_time) steps.
    A new event simply replaces the pending sequence - the worker picks up
    the change mid-fade without spawning or cancelling threads.
    """

    def __init__(self, led_device, idle_brightness=0.05, playing_brightness=0.2,
                 active_brightness=0.8, fade_duration=2.0, active_duration=5.0):
        self.device = led_device
        self.idle_brightness = float(idle_brightness)
        self.playing_brightness = float(playing_brightness)
        self.active_brightness = float(active_brightness)
        self.fade_duration = float(fade_duration)
        self.active_duration = float(active_duration)
        self.current_song = None
        self.current_state = None
        # Update rate of the fade worker in steps per second
        self._fade_fps = 50.0
        self._cond = threading.Condition()
        self._sequence = []
        self._generation = 0
        threading.Thread(target=self._worker, name='SongActivityLED', daemon=True).start()
        # Power-on indication: brief blink, then idle brightness
        self._enqueue([(1.0, 0.0, 0.2), (self.idle_brightness, 0.3, 0.0)])

    def _enqueue(self, steps):
        with self._cond:
            self._sequence = list(steps)
            self._generation += 1
            self._cond.notify()

    def _worker(self):
        step_dt = 1.0 / self._fade_fps
        while True:
            with self._cond:
                while not self._sequence:
                    self._cond.wait()
                target, fade_time, hold_time = self._sequence.pop(0)
                generation = self._generation
            start = float(self.device.value)
            steps = max(1, int(fade_time * self._fade_fps))
            aborted = False
            for i in range(1, steps + 1):
                with self._cond:
                    if self._generation != generation:
                        aborted = True
                        break
                self.device.value = min(1.0, max(0.0, start + (target - start) * i / steps))
                time.sleep(step_dt)
            if aborted:
                continue
            self.device.value = min(1.0, max(0.0, target))
            if hold_time > 0:
                with self._cond:
                    # Returns early if a new sequence arrives during the hold phase
                    self._cond.wait(timeout=hold_time)

    def handle_player_status(self, status):
        """Evaluate playerstatus updates and translate them into LED sequences"""
        try:
            song = status.get('file')
            state = status.get('state')
            song_changed = bool(song) and song != self.current_song
            state_changed = state != self.current_state
            if not song_changed and not state_changed:
                return
            logger.debug(f"Song Activity LED: state {self.current_state} -> {state}, "
                         f"song {self.current_song} -> {song}")
            if state == 'play':
                if song_changed or self.current_state in ('stop', None):
                    # New song or fresh playback start: quick ramp to peak, hold,
                    # then settle at playing brightness
                    self._enqueue([(self.active_brightness, 0.15, self.active_duration),
                                   (self.playing_brightness, self.fade_duration, 0.0)])
                elif state_changed:
                    # Resume from pause without song change
                    self._enqueue([(self.playing_brightness, self.fade_duration, 0.0)])
            elif state in ('pause', 'stop') and state_changed:
                self._enqueue([(self.idle_brightness, self.fade_duration, 0.0)])
            if song:
                self.current_song = song
            self.current_state = state
        except Exception as e:
            logger.error(f"Song Activity LED: error processing playerstatus: {e.__class__.__name__}: {e}")

    def handle_countdown(self, payload):
        """Card removal countdown: pulse with linearly rising base brightness.

        The closer the timeout, the brighter the pulsing - a visual reminder
        to put the card back. On abort return to playing brightness; on
        time-out the player stop event fades to idle via handle_player_status.
        """
        try:
            state = payload.get('state')
            if state == 'running':
                total = float(payload.get('total') or 1.0)
                remaining = float(payload.get('remaining') or 0.0)
                progress = min(1.0, max(0.0, 1.0 - (remaining / total)))
                base = self.playing_brightness + (1.0 - self.playing_brightness) * progress
                self._enqueue([(min(1.0, base + 0.1), 0.25, 0.0),
                               (max(0.0, base - 0.2), 0.25, 0.0)])
            elif state == 'aborted':
                # Back to playing brightness - or idle if playback is paused/stopped
                target = self.playing_brightness if self.current_state == 'play' else self.idle_brightness
                self._enqueue([(target, 0.5, 0.0)])
            # state 'ended': the player stop event handles the fade to idle
        except Exception as e:
            logger.error(f"Song Activity LED: error processing countdown: {e.__class__.__name__}: {e}")


def register_song_activity_led_callback(device, idle_brightness=0.05, playing_brightness=0.2,
                                        active_brightness=0.8, fade_duration=2.0, active_duration=5.0):
    """
    Have a PWMLED indicate song activity with smooth fade effects:

    * brief blink on start-up, then constant idle brightness
    * on song start/change: peak brightness for :attr:`active_duration` seconds,
      then fade to playing brightness
    * on pause/stop: fade back down to idle brightness

    All brightness values are in the range 0.0 to 1.0 and can be set via
    ``connect_kwargs`` in the GPIO configuration. Set ``idle_brightness: 0.0``
    to turn the LED fully off when nothing is playing.

    Compatible devices:

    * :class:`components.gpio.gpioz.core.output_devices.PWMLED`
    """
    import jukebox.publishing.subscriber as subscriber

    if _check_device_type(device, [PWMLED], lambda: None) is None:
        return

    led_manager = _SongActivityLED(device, idle_brightness, playing_brightness,
                                   active_brightness, fade_duration, active_duration)

    def subscription_worker():
        while True:
            try:
                sub = subscriber.Subscriber("inproc://PublisherToProxy", ["playerstatus", "rfid.countdown"])
                logger.debug("Song Activity LED: playerstatus subscriber started")
                while True:
                    topic, payload = sub.receive()
                    if topic == 'playerstatus' and isinstance(payload, dict):
                        led_manager.handle_player_status(payload)
                    elif topic == 'rfid.countdown' and isinstance(payload, dict):
                        led_manager.handle_countdown(payload)
            except Exception as e:
                logger.error(f"Song Activity LED: subscriber error, retrying: {e.__class__.__name__}: {e}")
                time.sleep(2)

    threading.Thread(target=subscription_worker, name='SongActivityLEDSub', daemon=True).start()
