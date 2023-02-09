
import os
import sys
from pathlib import Path
import time
import ctypes
from typing import Tuple
import portion

import toml

from numpy.polynomial import Polynomial


path = Path(r'C:\Program Files\Crystal Technology\Developer\AotfLibrary\Dll')
os.add_dll_directory(str(path))

dll = ctypes.cdll.LoadLibrary('AotfLibrary.dll')

calibration = toml.load('./calibration.toml')

class AOTF:

    def __init__(self):
        super().__init__()
        self._handle: int = None
        self._nchannels = 8
        self._calibration: Polynomial = None
        self.calib_ids = list(calibration.keys())
        self._timeout = 10  # seconds
        self._amplitude_int_max = 16383

    def _check_handle(self):
        """make sure the communication with the controller has been opened"""
        if self._handle is None:
            raise IOError('The communication with the controller has not been opened, or failed')

    def _write(self, message: str):
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
            return buffer.value[:nread.value].decode()
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
        splits = read.split('\r\n')
        if splits[0] != msg:
            return False
        else:
            return '*' in splits[-1]

    def query(self, msg: str):
        self._write(f'{msg}\r')
        return self._loop_read(msg)

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
        self.write(f'dds reset')

    def set_acoustic_frequency(self, frequency: float, channel: int = 0) -> float:
        """Get/Set the acoustic frequency in Hz"""
        return self.set_acoustic_frequency_Hz(frequency, channel)

    def set_acoustic_frequency_MHz(self, frequency: float, channel: int = 0) -> float:
        """Get/Set the acoustic frequency in MHz"""
        self._check_channel(channel)
        self.write(f'Dds Frequency {channel} {frequency}')

    def set_acoustic_frequency_Hz(self, frequency: float, channel: int = 0) -> float:
        """Get/Set the acoustic frequency in Hz"""
        self._check_channel(channel)
        self.write(f'Dds Frequency {channel} !{frequency}')

    @property
    def calibration(self) -> Polynomial:
        return self._calibration

    @calibration.setter
    def calibration(self, calibration_id: 'str'):
        if calibration_id in self.calib_ids:
            self._calibration = Polynomial(calibration[calibration_id]['coeffs'],
                                           domain=calibration[calibration_id]['domain'],
                                           window=calibration[calibration_id]['domain'])

    def set_wavelength(self, wavelength: float, channel: int = 0):
        self._check_channel(channel)
        if self._calibration is not None and wavelength in portion.closed(*self._calibration.domain):
            self.set_acoustic_frequency_MHz(self.calibration(wavelength), channel)

    def set_amplitude_int(self, amplitude: int, channel: int = 0):
        self._check_channel(channel)
        if amplitude in portion.closed(0, self._amplitude_int_max):
            self.write(f'Dds Amplitude {channel} {amplitude}')

    def set_amplitude_percent(self, amplitude: float, channel: int = 0):
        amplitude_int = self._amplitude_int_max * amplitude / 100
        self.set_amplitude_int(amplitude_int, channel)

    def set_amplitude(self, amplitude: float, channel: int = 0):
        self.set_amplitude_percent(amplitude, channel)



if __name__ == '__main__':
    aotf = AOTF()
    try:
        aotf.open(0)
        print(aotf.get_serial())
        print(aotf.get_date())
        aotf.reset()
        calib_ids = aotf.calib_ids
        channel = 0
        if 'RF1' in calib_ids:
            aotf.calibration = 'RF1'
            aotf.set_wavelength(532., channel)
            aotf.set_amplitude_int(8000, 0)
            aotf.set_amplitude(0, 0)
            aotf.set_amplitude(60, 0)
            aotf.set_amplitude(0, 0)

    except Exception as e:
        print(str(e))
    finally:
        aotf.close()


