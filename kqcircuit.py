import pya
from kqcircuit.pcells.waveguide_cop import WaveguideCopStreight
from kqcircuit.pcells.waveguide_cop import WaveguideCopCurve
from kqcircuit.pcells.waveguide_cop import WaveguideCop
from kqcircuit.pcells.circle import Circle
from kqcircuit.pcells.chip import ChipFrame


import sys
import inspect
from importlib import reload
reload(sys.modules[WaveguideCop.__module__])

"""
Quantum Circuits in KLayout
"""


class KQCircuitLibrary(pya.Library):
  """
  Quantum Circuits in KLayout
  """

  def __init__(self):
  
    # Set the description
    self.description = "Library for superconducting quantum circuits."
    
    # Create the PCell declarations
    print("Populating library")
    self.layout().register_pcell("Circle", Circle())
    self.layout().register_pcell("Waveguide", WaveguideCop())
    self.layout().register_pcell("Waveguide streight", WaveguideCopStreight())
    self.layout().register_pcell("Waveguide curved", WaveguideCopCurve())
    self.layout().register_pcell("Chip", ChipFrame())
    self.layout().register_pcell("Meander", WaveguideCopCurve())
    self.layout().register_pcell("Swissmon", WaveguideCopCurve())
    self.layout().register_pcell("FingerCap", WaveguideCopCurve())
    self.layout().register_pcell("TJunction", WaveguideCopCurve())
    self.layout().register_pcell("Launcher", WaveguideCopCurve())
    
    self.register("KQCircuit")
    
    

# Instantiate and register the library
KQCircuitLibrary()
