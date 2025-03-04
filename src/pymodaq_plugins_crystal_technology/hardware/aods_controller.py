
import os
import sys
from pathlib import Path
import time
import ctypes
from typing import Tuple
import portion
import toml
import numpy as np
from numpy.polynomial import Polynomial

from pymodaq_utils.logger import set_logger


path = Path(r'C:\Program Files\Crystal Technology\Developer\AotfLibrary\Dll')
os.add_dll_directory(str(path))
dll = ctypes.cdll.LoadLibrary('AotfLibrary.dll')
calib_path = Path(__file__).parent
calibration = toml.load(calib_path.joinpath('calibration.toml'))
calib_ids = list(calibration.keys())
logger = set_logger('AOTF', add_to_console=True)


class AOTF:
    def __init__(self):
        super().__init__()
        self._handle: int = None
        self._nchannels = 8
        self._calibration: Polynomial = None
        self.calib_ids = calib_ids
        self._timeout = 10  # seconds
        self._current_channel: Channel = None

    def _check_handle(self):
        """make sure the communication with the controller has been opened"""
        if self._handle is None:
            raise IOError('The communication with the controller has not been opened, or failed')

    def _write(self, message: str):
        logger.debug(f'Writing: {message} to the controller')
        self._check_handle()
        buffer = ctypes.create_string_buffer(message.encode())
        ret = dll.AotfWrite(self._handle, len(message), ctypes.byref(buffer))
        if ret == 0:
            raise IOError(f'The program could not send data to the controller')

    def _read(self, length: int = 256) -> str:
        self._check_handle()
        if self._is_data_available():
            buffer = ctypes.create_string_buffer(length)
            nread = ctypes.c_uint()
            ret = dll.AotfRead(self._handle, length, ctypes.byref(buffer), ctypes.byref(nread))
            if ret == 0:
                raise IOError(f'The program could not send data to the controller')
            read = buffer.value[:nread.value].decode()
            logger.debug(f'Reading: {read} from the controller')
            return read
        else:
            return ''

    def _is_data_available(self) -> bool:
        self._check_handle()
        ret = dll.AotfIsReadDataAvailable(self._handle)
        return bool(ret)

    def _check_channel(self, channel: int):
        if channel < 0 and channel >= self._nchannels:
            raise ValueError(f'the requested channel is not a valid integer [0-{self._nchannels-1}]')

    def _loop_read(self, msg: str):
        start = time.perf_counter()
        read = ''
        while True:
            if self._is_data_available():
                read += self._read()
                if self._check_message_done(read, msg):
                    read = read.lstrip(f'{msg}\r\n')
                    read = read.rstrip('\r\n* ')
                    return read
            else:
                time.sleep(0.1)
            if time.perf_counter() - start > self._timeout:
                return ''

    def _check_message_done(self, read: str, msg: str):
        #print(read)
        splits = read.split('\r\n')
        if splits[0] != msg:
            return False
        else:
            return '*' in splits[-1]

    def query(self, msg: str):
        logger.debug(f'Querying: {msg} from the controller')
        self._write(f'{msg}\r')
        response = self._loop_read(msg)
        logger.debug(f'Query answer is: {response} from the controller')
        return response

    def write(self, msg: str):
        print(msg)
        self._write(f'{msg}\r')

    def open(self, controller_index: int = 0):
        ret = dll.AotfOpen(controller_index)
        if ret != 0:
            self._handle = ret
        else:
            raise IOError(f'The AOTF controller with index {controller_index} could not be opened')

    def close(self):
        self._check_handle()
        ret = dll.AotfClose(self._handle)
        if ret == 0:
            raise IOError(f'The AOTF controller could not be closed')
        self._handle = None

    def get_controller_index(self) -> int:
        self._check_handle()
        return dll.AotfGetInstance(self._handle)

    def get_serial(self) -> str:
        return self.query('BoardId Serial')

    def get_date(self) -> str:
        return self.query('BoardId Date')

    def reset(self):
        self.query(f'dds reset')

    @property
    def calibration(self) -> Polynomial:
        return self._calibration

    @calibration.setter
    def calibration(self, calibration_id: 'str'):
        if calibration_id in self.calib_ids:
            self._calibration = Polynomial(calibration[calibration_id]['coeffs'],
                                           domain=calibration[calibration_id]['domain'],
                                           window=calibration[calibration_id]['domain'])

    def get_channel(self, channel: int) -> 'Channel':
        self._check_channel(channel)
        self._current_channel = Channel(channel, self)
        return self._current_channel


class Channel:
    def __init__(self, channel: int, aotf: AOTF = None):
        self._channel = channel
        self._aotf = aotf
        self._amplitude_int_max = 16383

    def __repr__(self):
        return f'Channel {self._channel} from {self._aotf}'

    @property
    def acoustic_frequency_MHz(self) -> float:
        """Get/Set the acoustic frequency in MHz"""
        #Channel 0 profile 0 frequency
        response = self._aotf.query(f'dds frequency {self._channel}')
        if f'Channel {self._channel} profile 0 frequency ' in response:
            response = response.split(f'Channel {self._channel} profile 0 frequency ')[1]
            response = response.split('Hz')[0]
            afreq = float(response)
            return afreq * 1e-6

    @acoustic_frequency_MHz.setter
    def acoustic_frequency_MHz(self, frequency: float):
        """Get/Set the acoustic frequency in MHz"""
        self._aotf.query(f'Dds Frequency {self._channel} {frequency}')

    @property
    def wavelength(self) -> float:
        acoustic_frequency_MHz = self.acoustic_frequency_MHz
        if not np.isclose(acoustic_frequency_MHz, 0.0):
            roots = (self._aotf.calibration-acoustic_frequency_MHz).roots()
            for root in roots:
                if np.isclose(root, np.abs(root)) and np.real(root) in portion.closed(*self._aotf.calibration.domain):
                    return np.real(root)
        else:
            return 0.

    @wavelength.setter
    def wavelength(self, wavelength: float):
        if self._aotf.calibration is not None and wavelength in portion.closed(*self._aotf.calibration.domain):
            self.acoustic_frequency_MHz = self._aotf.calibration(wavelength)

    @property
    def amplitude_int(self) -> int:
        """Get/Set the current channel amplitude in percent"""
        amplitude_str = self._aotf.query(f'dds amplitude {self._channel}')
        return int(amplitude_str.split(f'Channel {self._channel} @ ')[1])

    @amplitude_int.setter
    def amplitude_int(self, amp: int):
        if amp in portion.closed(0, self._amplitude_int_max):
            self._aotf.query(f'Dds Amplitude {self._channel} {amp}')

    @property
    def amplitude(self) -> float:
        """Get/Set the current channel amplitude in percent"""
        amplitude_int = self.amplitude_int
        return amplitude_int * 100 / self._amplitude_int_max

    @amplitude.setter
    def amplitude(self, amp: float):
        self.amplitude_int = int(amp * self._amplitude_int_max / 100)


if __name__ == '__main__':
    aotf = AOTF()
    try:
        aotf.open(0)
        print(f'Serial is: {aotf.get_serial()}')
        print(f'Date is: {aotf.get_date()}')
        print("Reseting")
        aotf.reset()
        calib_ids = aotf.calib_ids
        channel_int = 0
        if 'RF1' in calib_ids:
            print("Setting calibration")
            aotf.calibration = 'RF1'
            channel = aotf.get_channel(channel_int)
            print(f'Selecting channel: {channel}')
            print(f'Wavelength is {channel.wavelength}')
            print(f'Setting wavelength to 532nm')
            channel.wavelength = 532.
            print(f'Wavelength is {channel.wavelength}')
            print(f'Amplitude is {channel.amplitude}')
            print(f'Setting amplitude int to 8000')
            channel.amplitude_int = 8000
            print(f'Amplitude int is {channel.amplitude_int}')
            print(f'Setting amplitude to 0')
            channel.amplitude = 0
            print(f'Amplitude is {channel.amplitude}')
            print(f'Setting amplitude to 60%')
            channel.amplitude = 60
            print(f'Amplitude is {channel.amplitude}%')
            print(f'Setting amplitude to 0')
            channel.amplitude = 0

    except Exception as e:
        print(str(e))
    finally:
        print(f'Close and quit')
        aotf.close()


