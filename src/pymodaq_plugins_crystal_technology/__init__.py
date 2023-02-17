from pathlib import Path
from pymodaq.utils.logger import set_logger

with open(str(Path(__file__).parent.joinpath('VERSION')), 'r') as fvers:
    __version__ = fvers.read().strip()
