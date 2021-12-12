#
# This file is part of LUNA.
#
# Copyright (c) 2020 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

""" ButterStick platform definitions.

This is a non-core platform. To use it, you'll need to set your LUNA_PLATFORM variable:

    > export LUNA_PLATFORM="luna.gateware.platform.butterstick:ButterStickPlatform"
"""

import os
import subprocess

from nmigen import *
from nmigen.build import *
from nmigen.vendor.lattice_ecp5 import LatticeECP5Platform

from nmigen_boards.butterstick import ButterStickPlatform as _ButterStickPlatform

from .core import LUNAPlatform
from ..architecture.car import LunaECP5DomainGenerator

__all__ = ["ButterStickPlatform"]

class VccioCtrl(Elaboratable):
    def __init__(self, vccio_pins):
        self.vccio_pins = vccio_pins
        
    def elaborate(self, platform):
        m = Module()

        pwm_timer = Signal(14)

        m.d.sync += pwm_timer.eq(pwm_timer + 1)
        # SYGYZY 0
        m.d.comb += self.vccio_pins.pdm[0].eq(pwm_timer < int(2**14 * (0.1)))
        # SYGYZY 1
        m.d.comb += self.vccio_pins.pdm[1].eq(pwm_timer < int(2**14 * (0.1)))
        # SYGYZY 2 & ULPI USB (limit to 1.8V - 3.3V for USB3343) 
        m.d.comb += self.vccio_pins.pdm[2].eq(pwm_timer < int(2**14 * (0.70)))

        m.d.comb += self.vccio_pins.en.eq(1)

        return m

class ButterStickDomainGenerator(LunaECP5DomainGenerator):
    """ clock domain generator; uses the luna one with 30Mhz input

    We also add vccio management here for want of a better place.  This is needed to bring up the ulpi.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def elaborate(self, platform):
        m = super().elaborate(platform)
        m.submodules.vccio_ctrl = VccioCtrl(platform.request("vccio_ctrl", 0))
        return m


class ButterStickPlatform(_ButterStickPlatform, LUNAPlatform):
    name                   = "ButterStick"
    clock_domain_generator = ButterStickDomainGenerator
    default_usb_connection = "usb"
    default_clk = "clk30"
    DEFAULT_CLOCK_FREQUENCIES_MHZ = {
        "fast": 240,
        "sync": 120,
        "usb":  60
    }
    
    # Add I/O aliases with standard LUNA naming.
    additional_resources = [
    ]

    # Create our semantic aliases.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_resources(self.additional_resources)
