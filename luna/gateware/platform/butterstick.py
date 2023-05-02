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

from amaranth import *
from amaranth.build import *
from amaranth.vendor.lattice_ecp5 import LatticeECP5Platform

from amaranth_boards.butterstick import ButterStickPlatform as _ButterStickPlatform

from luna.gateware.interface.pipe import AsyncPIPEInterface
from luna.gateware.interface.serdes_phy.ecp5 import ECP5SerDesPIPE

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
        m.d.comb += self.vccio_pins.pdm[2].eq(pwm_timer < int(2**14 * (0.1)))

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


class ButterStickSSDomainGenerator(Elaboratable):
    """ Clock generator for ECPIX5 boards. """

    def __init__(self, *, clock_frequencies=None, clock_signal_name=None):
        pass

    def elaborate(self, platform):
        m = Module()
        m.submodules.vccio_ctrl = VccioCtrl(platform.request("vccio_ctrl", 0))

        # Create our domains.
        m.domains.ss     = ClockDomain()
        m.domains.sync   = ClockDomain()
        m.domains.usb    = ClockDomain()
        m.domains.usb_io = ClockDomain()
        m.domains.fast   = ClockDomain()


        # Grab our clock and global reset signals.
        clk30 = platform.request(platform.default_clk)
        reset  = platform.request(platform.default_rst)

        # Generate the clocks we need for running our SerDes.
        feedback = Signal()
        locked   = Signal()
        m.submodules.pll = Instance("EHXPLLL",

                # Clock in.
                i_CLKI=clk30,

                # Generated clock outputs.
                o_CLKOP=feedback,
                o_CLKOS= ClockSignal("sync"),
                o_CLKOS2=ClockSignal("fast"),

                # Status.
                o_LOCK=locked,

                # PLL parameters...
                p_CLKI_DIV=3,
                p_PLLRST_ENA="ENABLED",
                p_INTFB_WAKE="DISABLED",
                p_STDBY_ENABLE="DISABLED",
                p_DPHASE_SOURCE="DISABLED",
                p_CLKOS3_FPHASE=0,
                p_CLKOS3_CPHASE=0,
                p_CLKOS2_FPHASE=0,
                p_CLKOS2_CPHASE=5,
                p_CLKOS_FPHASE=0,
                p_CLKOS_CPHASE=5,
                p_CLKOP_FPHASE=0,
                p_CLKOP_CPHASE=4,
                p_PLL_LOCK_MODE=0,
                p_CLKOS_TRIM_DELAY="0",
                p_CLKOS_TRIM_POL="FALLING",
                p_CLKOP_TRIM_DELAY="0",
                p_CLKOP_TRIM_POL="FALLING",
                p_OUTDIVIDER_MUXD="DIVD",
                p_CLKOS3_ENABLE="DISABLED",
                p_OUTDIVIDER_MUXC="DIVC",
                p_CLKOS2_ENABLE="ENABLED",
                p_OUTDIVIDER_MUXB="DIVB",
                p_CLKOS_ENABLE="ENABLED",
                p_OUTDIVIDER_MUXA="DIVA",
                p_CLKOP_ENABLE="ENABLED",
                p_CLKOS3_DIV=1,
                p_CLKOS2_DIV=2,
                p_CLKOS_DIV=4,
                p_CLKOP_DIV=1,
                p_CLKFB_DIV=50,
                p_FEEDBK_PATH="CLKOP",

                # Internal feedback.
                i_CLKFB=feedback,

                # Control signals.
                i_RST=reset,
                i_PHASESEL0=0,
                i_PHASESEL1=0,
                i_PHASEDIR=1,
                i_PHASESTEP=1,
                i_PHASELOADREG=1,
                i_STDBY=0,
                i_PLLWAKESYNC=0,

                # Output Enables.
                i_ENCLKOP=0,
                i_ENCLKOS=0,
                i_ENCLKOS2=0,
                i_ENCLKOS3=0,

                # Synthesis attributes.
                a_ICP_CURRENT="12",
                a_LPF_RESISTOR="8"
        )

        # Temporary: USB FS PLL
        feedback    = Signal()
        usb2_locked = Signal()
        m.submodules.fs_pll = Instance("EHXPLLL",

                # Status.
                o_LOCK=usb2_locked,

                # PLL parameters...
                p_PLLRST_ENA="ENABLED",
                p_INTFB_WAKE="DISABLED",
                p_STDBY_ENABLE="DISABLED",
                p_DPHASE_SOURCE="DISABLED",
                p_OUTDIVIDER_MUXA="DIVA",
                p_OUTDIVIDER_MUXB="DIVB",
                p_OUTDIVIDER_MUXC="DIVC",
                p_OUTDIVIDER_MUXD="DIVD",

                p_CLKI_DIV = 6,
                p_CLKOP_ENABLE = "ENABLED",
                p_CLKOP_DIV = 16,
                p_CLKOP_CPHASE = 15,
                p_CLKOP_FPHASE = 0,

                p_CLKOS_DIV = 12,
                p_CLKOS_CPHASE = 0,
                p_CLKOS_FPHASE = 0,


                p_CLKOS2_ENABLE = "ENABLED",
                p_CLKOS2_DIV = 10,
                p_CLKOS2_CPHASE = 0,
                p_CLKOS2_FPHASE = 0,

                p_CLKOS3_ENABLE = "ENABLED",
                p_CLKOS3_DIV = 40,
                p_CLKOS3_CPHASE = 5,
                p_CLKOS3_FPHASE = 0,

                p_FEEDBK_PATH = "CLKOP",
                p_CLKFB_DIV = 6,

                # Clock in.
                i_CLKI=clk30,

                # Internal feedback.
                i_CLKFB=feedback,

                # Control signals.
                i_RST=reset,
                i_PHASESEL0=0,
                i_PHASESEL1=0,
                i_PHASEDIR=1,
                i_PHASESTEP=1,
                i_PHASELOADREG=1,
                i_STDBY=0,
                i_PLLWAKESYNC=0,

                # Output Enables.
                i_ENCLKOP=0,
                i_ENCLKOS2=0,

                # Generated clock outputs.
                o_CLKOP=feedback,
                o_CLKOS2=ClockSignal("usb_io"),
                o_CLKOS3=ClockSignal("usb"),

                # Synthesis attributes.
                a_FREQUENCY_PIN_CLKI="25",
                a_FREQUENCY_PIN_CLKOP="48",
                a_FREQUENCY_PIN_CLKOS="48",
                a_FREQUENCY_PIN_CLKOS2="12",
                a_ICP_CURRENT="12",
                a_LPF_RESISTOR="8",
                a_MFG_ENABLE_FILTEROPAMP="1",
                a_MFG_GMCREF_SEL="2"
        )

        # Control our resets.
        m.d.comb += [
            ClockSignal("ss")      .eq(ClockSignal("sync")),

            ResetSignal("ss")      .eq(~locked),
            ResetSignal("sync")    .eq(~locked),
            ResetSignal("fast")    .eq(~locked),

            ResetSignal("usb")     .eq(~usb2_locked),
            ResetSignal("usb_io")  .eq(~usb2_locked),
        ]

        return m


class ButterStickSuperSpeedPHY(AsyncPIPEInterface):
    """ Superspeed PHY configuration for the ECPIX5. """

    REFCLK_FREQUENCY = 100e6
    SS_FREQUENCY     = 125e6
    FAST_FREQUENCY   = 250e6

    SERDES_DUAL    = 0
    SERDES_CHANNEL = 0


    def __init__(self, platform):

        # Grab the I/O that implements our SerDes interface...
        serdes_io_directions = {
            'ch0':    {'tx':"-", 'rx':"-"},
            'ch1':    {'tx':"-", 'rx':"-"},
            'refclk': '-',
        }
        serdes_io      = platform.request("serdes", self.SERDES_DUAL, dir=serdes_io_directions)
        serdes_channel = getattr(serdes_io, f"ch{self.SERDES_CHANNEL}")

        # Use it to create our soft PHY...
        serdes_phy = ECP5SerDesPIPE(
            tx_pads             = serdes_channel.tx,
            rx_pads             = serdes_channel.rx,
            dual                = self.SERDES_DUAL,
            channel             = self.SERDES_CHANNEL,
            refclk_frequency    = self.FAST_FREQUENCY,
        )

        # ... and bring the PHY interface signals to the MAC domain.
        super().__init__(serdes_phy, width=4, domain="ss")


    def elaborate(self, platform):
        m = super().elaborate(platform)

        # Patch in our soft PHY as a submodule.
        m.submodules.phy = self.phy

        # Drive the PHY reference clock with our fast generated clock.
        m.d.comb += self.clk.eq(ClockSignal("fast"))

        # This board does not have a way to detect Vbus, so assume it's always present.
        m.d.comb += self.phy.power_present.eq(1)

        return m


class ButterStickPlatform(_ButterStickPlatform, LUNAPlatform):
    name                   = "ButterStick"
    clock_domain_generator = ButterStickSSDomainGenerator
    default_usb_connection = "usb"
    default_usb3_phy       = ButterStickSuperSpeedPHY
    default_clk = "clk30"
    DEFAULT_CLOCK_FREQUENCIES_MHZ = {
        "fast": 240,
        "sync": 120,
        "usb":  60
    }
    
    # Add I/O aliases with standard LUNA naming.
    additional_resources = [
        Resource("serdes", 0,
            Subsignal("ch0",
                Subsignal("rx", DiffPairs("Y5", "Y6")),
                Subsignal("tx", DiffPairs("W4", "W5")),
            ),
            #Subsignal("ch1",
            #    Subsignal("rx", DiffPairs("Y7", "Y8")),
            #    Subsignal("tx", DiffPairs("W8", "W9")),
            #),
            #Subsignal("refclk", DiffPairs("Y11", "Y12"))
        ),
        #Resource("serdes", 1,
        #    Subsignal("ch0",
        #        Subsignal("rx", DiffPairs("Y14", "Y15")),
        #        Subsignal("tx", DiffPairs("W13", "W14")),
        #    ),
        #    Subsignal("ch1",
        #        Subsignal("rx", DiffPairs("Y16", "Y17")),
        #        Subsignal("tx", DiffPairs("W17", "W18")),
        #    ),
        #    #Subsignal("refclk", DiffPairs("AF21", "AF22"))
        #),
    ]

    # Create our semantic aliases.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_resources(self.additional_resources)
