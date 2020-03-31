#
# This file is part of LUNA.
#
""" Low-level USB transciever gateware -- exposes packet interfaces. """

import unittest

from nmigen            import Signal, Module, Elaboratable, Memory, Cat, Const, Record
from ...test           import LunaGatewareTestCase, usb_domain_test_case, sync_test_case

from .                 import USBSpeed
from .packet           import USBTokenDetector, USBHandshakeGenerator, USBDataPacketCRC
from .packet           import USBInterpacketTimer, USBDataPacketGenerator, USBHandshakeDetector
from .control          import USBControlEndpoint
from ...interface.ulpi import UTMITranslator
from ...interface.utmi import UTMIInterfaceMultiplexer


class USBDevice(Elaboratable):
    """ Class representing an abstract USB device.

    Can be instantiated directly, and used to build a USB device,
    or can be subclassed to create custom device types.

    The I/O for this device is generically created dynamically; but
    a few signals are exposed:

        I: connect          -- Held high to keep the current USB device connected; or
                               held low to disconnect.

        O: frame_number[11] -- The current USB frame number.
        O: sof_detected     -- Pulses for one cycle each time a SOF is detected; and thus our
                               frame number has changed.
    """

    def __init__(self, *, bus):
        """
        Parameters:
            bus -- The UTMI or ULPI PHY connection to be used for communications.
        """

        # If this looks more like a ULPI bus than a UTMI bus, translate it.
        if not hasattr(bus, 'rx_valid'):
            self.utmi       = UTMITranslator(ulpi=bus)
            self.translator = self.utmi

        # Otherwise, use it directly.
        else:
            self.utmi       = bus
            self.translator = None


        #
        # I/O port
        #
        self.connect      = Signal()

        self.frame_number = Signal(11)
        self.sof_detected = Signal()

        # Debug I/O.
        self.last_request = Signal(8)
        self.new_packet   = Signal()


    def elaborate(self, platform):
        m = Module()

        # If we have a bus translator, include it in our submodules.
        if self.translator:
            m.submodules.translator = self.translator


        #
        # Internal device state.
        #

        # Stores the device's current address. Used to identify which packets are for us.
        address = Signal(7, reset=0)

        # Stores the device's current speed (a USBSpeed value).
        speed   = Signal(2, reset=USBSpeed.FULL)


        #
        # Internal interconnections.
        #

        # Device operating state controls.
        m.d.comb += [

            # Disable our host-mode pulldowns; as we're a device.
            self.utmi.dm_pulldown  .eq(0),

            # Connect our termination whenever the device is connected.
            # TODO: support high-speed termination disconnect.
            self.utmi.term_select  .eq(self.connect),

            # For now, fix us into FS mode.
            self.utmi.op_mode      .eq(0b00),
            self.utmi.xcvr_select  .eq(0b01)
        ]


        # Create our internal packet components:
        # - A token detector, which will identify and parse the tokens that start transactions.
        # - A data transmitter, which will transmit provided data streams.
        # - A handshake generator, which will assist in generating response packets.
        # - A handshake detector, which detects handshakes generated by the host.
        # - A data CRC16 handler, which will compute data packet CRCs.
        # - An interpacket delay timer, which will enforce interpacket delays.
        m.submodules.token_detector      = token_detector      = USBTokenDetector(utmi=self.utmi)
        m.submodules.transmitter         = transmitter         = USBDataPacketGenerator()
        m.submodules.handshake_generator = handshake_generator = USBHandshakeGenerator()
        m.submodules.handshake_detector  = handshake_detector  = USBHandshakeDetector(utmi=self.utmi)
        m.submodules.data_crc            = data_crc            = USBDataPacketCRC()
        m.submodules.timer               = timer               = USBInterpacketTimer()

        # Connect our transmitter to its CRC generator.
        data_crc.add_interface(transmitter.crc)

        m.d.comb += [
            # Ensure our token detector only responds to tokens addressed to us.
            token_detector.address  .eq(address),

            # Hook up our data_crc to our receive inputs.
            data_crc.rx_data        .eq(self.utmi.rx_data),
            data_crc.rx_valid       .eq(self.utmi.rx_valid),

            # Connect our state signals to our subordinate components.
            token_detector.speed    .eq(speed),
            timer.speed             .eq(speed)
        ]

        #
        # Endpoint generation.
        #

        # TODO: abstract this into an add-control-endpoint function
        m.submodules.control_ep = control_ep = USBControlEndpoint(utmi=self.utmi)

        # Connect our timer, data-CRC computer, and tokenizer to our control EP.
        timer.add_interface(control_ep.timer)
        data_crc.add_interface(control_ep.data_crc)
        m.d.comb += [
            token_detector.interface     .connect(control_ep.tokenizer),
            handshake_detector.detected  .connect(control_ep.handshakes_detected),

            control_ep.speed             .eq(speed),

            # FIXME: multiplex access to the transmitter
            transmitter.stream           .connect(control_ep.tx),
            transmitter.data_pid         .eq(control_ep.tx_pid_toggle)
        ]

        #
        # Transmitter multiplexing.
        #

        # Create a multiplexer that will arbitrate access to the transmit lines.
        m.submodules.tx_multiplexer = tx_multiplexer = UTMIInterfaceMultiplexer()

        # Connect each of our transmitters.
        tx_multiplexer.add_input(transmitter.tx)
        tx_multiplexer.add_input(handshake_generator.tx)


        m.d.comb += [

            # Connect our transmit multiplexer to the actual UTMI bus.
            tx_multiplexer.output            .attach(self.utmi),

            # Connect up the transmit interface for out ULPI bus.
            data_crc.tx_valid                .eq(tx_multiplexer.output.valid),
            data_crc.tx_data                 .eq(tx_multiplexer.output.data),

            # FIXME: multiplex access to the transmit / handshake generators
            handshake_generator.issue_ack    .eq(control_ep.issue_ack),
            handshake_generator.issue_nak    .eq(control_ep.issue_nak),
            handshake_generator.issue_stall  .eq(control_ep.issue_stall),

        ]


        #
        # Device state management.
        #
        with m.If(control_ep.address_changed):
            m.d.usb += address.eq(control_ep.new_address)


        #
        # Device-state outputs.
        #
        m.d.comb += [
            self.sof_detected  .eq(token_detector.interface.new_frame),
            self.frame_number  .eq(token_detector.interface.frame),

            # Debug only.
            self.last_request  .eq(control_ep.last_request),
            self.new_packet    .eq(control_ep.new_packet)
        ]

        return m


if __name__ == "__main__":
    unittest.main()
