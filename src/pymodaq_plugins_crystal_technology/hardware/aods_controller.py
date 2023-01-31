
import os
import sys
from pathlib import Path

import ctypes

path = Path(r'C:\Users\weber\Desktop\AOTF0207\AOTF-RF1')

os.add_dll_directory(str(path))
sys.path.append(str(path))

dll = ctypes.cdll.LoadLibrary('AotfLibrary.dll')