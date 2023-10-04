#!/usr/bin/env python3
#
# This file is part of LUNA.
#
# Copyright (c) 2020 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

import time
import logging
import random

from prompt_toolkit import HTML
from prompt_toolkit import print_formatted_text as pprint

from amaranth import Cat, Signal, Elaboratable, Module, Mux
from amaranth.lib.fifo import SyncFIFO

from luna                             import top_level_cli
from apollo_fpga                      import ApolloDebugger
from luna.gateware.interface.jtag     import JTAGRegisterInterface
from luna.gateware.architecture.car   import LunaECP5DomainGenerator
from luna.gateware.interface.psram    import HyperRAMPHY, HyperRAMInterface

REGISTER_RAM_REGISTER_SPACE = 1
REGISTER_RAM_ADDR           = 2
REGISTER_RAM_READ_LENGTH    = 3
REGISTER_RAM_FIFO           = 4
REGISTER_RAM_START          = 5
REGISTER_RAM_STATUS         = 6
REGISTER_RAM_WRITE_LENGTH   = 7
REGISTER_RAM_CYCLE_COUNT    = 8


class HyperRAMDiagnostic(Elaboratable):
    """
    Temporary gateware that evaluates HyperRAM skews.
    """


    def elaborate(self, platform):
        m = Module()

        # Generate our clock domains.
        clocking = LunaECP5DomainGenerator()
        m.submodules.clocking = clocking

        # Create a set of registers...
        registers = JTAGRegisterInterface(address_size=7, default_read_value=0xDEADBEEF)
        m.submodules.registers = registers

        #
        # HyperRAM test connections.
        #
        ram_bus = platform.request('ram')
        psram_phy = HyperRAMPHY(bus=ram_bus)
        psram = HyperRAMInterface(phy=psram_phy.phy)
        m.submodules += [psram_phy, psram]

        psram_address = registers.add_register(REGISTER_RAM_ADDR)
        read_length   = registers.add_register(REGISTER_RAM_READ_LENGTH, reset=1)
        write_length  = registers.add_register(REGISTER_RAM_WRITE_LENGTH, reset=1)

        m.submodules.read_fifo  = read_fifo  = SyncFIFO(width=16, depth=32)
        registers.add_sfr(REGISTER_RAM_FIFO,
            read=read_fifo.r_data,
            read_strobe=read_fifo.r_en)

        register_space = registers.add_register(REGISTER_RAM_REGISTER_SPACE, size=1)

        start_read = Signal()
        start_write = Signal()
        registers.add_sfr(REGISTER_RAM_START,
            read_strobe=start_read,
            write_strobe=start_write)

        read_counter = Signal.like(read_length)
        write_counter = Signal.like(write_length)
        cycle_count = Signal(32)
        final_word = Signal()
        idle = Signal()
        m.d.comb += final_word.eq(1)
        with m.FSM() as fsm:
            with m.State("IDLE"):
                m.d.comb += idle.eq(1)

                with m.If(start_read):
                    m.d.sync += read_counter.eq(read_length)
                    m.next = "READ"

                with m.If(start_write):
                    m.d.sync += write_counter.eq(write_length)
                    m.d.sync += cycle_count.eq(0)
                    m.next = "WRITE"

            with m.State("READ"):
                m.d.comb += final_word.eq(read_counter == 1)
                with m.If(psram.read_ready):
                    m.d.sync += read_counter.eq(read_counter - 1)
                with m.If(psram.idle):
                    m.next = "IDLE"

            with m.State("WRITE"):
                m.d.comb += final_word.eq(write_counter == 1)
                with m.If(psram.write_ready):
                    m.d.sync += write_counter.eq(write_counter - 1)
                with m.If(psram.idle):
                    m.next = "IDLE"
                m.d.sync += cycle_count.eq(cycle_count + 1)
                

        registers.add_sfr(REGISTER_RAM_CYCLE_COUNT, read=cycle_count)


        # PSRAM Status register
        status = Signal(1)
        #m.d.sync += status.eq(Cat(psram.idle, psram.read_ready, psram.write_ready))
        m.d.sync += status.eq(idle)
        registers.add_sfr(REGISTER_RAM_STATUS, read=status)

        # Hook up our PSRAM.
        m.d.comb += [
            ram_bus.reset.o        .eq(0),
            psram.single_page      .eq(0),
            psram.register_space   .eq(register_space),
            psram.final_word       .eq(final_word),
            psram.perform_write    .eq(start_write),
            psram.start_transfer   .eq(start_read | start_write),
            psram.address          .eq(psram_address),
            psram.write_data       .eq(write_counter),
            read_fifo.w_data       .eq(psram.read_data),
            read_fifo.w_en         .eq(psram.read_ready),
            #write_fifo.r_en        .eq(psram.write_ready),
        ]

        #pmodA = platform.request("user_pmod", 0, dir="o")
        #pmodB = platform.request("user_pmod", 1, dir="o")

        # Return our elaborated module.
        return m


if __name__ == "__main__":
    test = top_level_cli(HyperRAMDiagnostic)

    # Create a debug and ILA connection.
    dut = ApolloDebugger()
    logging.info(f"Connected to onboard dut; hardware revision r{dut.major}.{dut.minor} (s/n: {dut.serial_number}).")

    logging.info("Running basic HyperRAM diagnostics.")

    iterations = 1

    passes   = 0
    failures = 0
    failed_tests = set()

    def read_hyperram_register(addr):
        dut.registers.register_write(REGISTER_RAM_REGISTER_SPACE, 1)
        dut.registers.register_write(REGISTER_RAM_ADDR, addr)
        dut.registers.register_read(REGISTER_RAM_START)
        time.sleep(0.1)
        return dut.registers.register_read(REGISTER_RAM_FIFO)

    def test_id_read():
        return read_hyperram_register(0x0) in (0x0c81, 0x0c86)

    def test_config_read():
        return read_hyperram_register(0x800) in (0x8f1f, 0x8f2f)

    def test_mem_benchmark():
        dut.registers.register_write(REGISTER_RAM_REGISTER_SPACE, 0)

        total = 0x400000
        read_length = 10


        write_length = total

        runs = 10

        # Initiate burst write at address 0.
        logging.info("Starting write benchmark...")
        dut.registers.register_write(REGISTER_RAM_ADDR, 0)
        dut.registers.register_write(REGISTER_RAM_WRITE_LENGTH, write_length)

        spent_cycles = 0
        for run in range(runs):
            dut.registers.register_write(REGISTER_RAM_START, 1)
            while (dut.registers.register_read(REGISTER_RAM_STATUS) & 1) == 0:
                pass
            spent_cycles += dut.registers.register_read(REGISTER_RAM_CYCLE_COUNT)

        # Figure out how long this took us.
        elapsed = spent_cycles / 120e6
        total_data_exchanged = runs * 2 * write_length  # bytes
        bytes_per_second = total_data_exchanged / elapsed
        logging.info(f"Exchanged {total_data_exchanged / 1000000}MiB total at {bytes_per_second / 1000000}MiB/s.")

        # Set read length & initiate read.
        if 0:
            pprint("Starting burst read...")
            dut.registers.register_write(REGISTER_RAM_ADDR, 0)
            dut.registers.register_write(REGISTER_RAM_READ_LENGTH, read_length)
            dut.registers.register_read(REGISTER_RAM_START)
            while (dut.registers.register_read(REGISTER_RAM_STATUS) & 1) == 0:
                time.sleep(0.1)
            pprint("Read finished!!")

            for addr in range(read_length):
                result = dut.registers.register_read(REGISTER_RAM_FIFO)
                pprint(f"{result=:x} {addr=}")
                #pprint(f".", end="")

        return True

    # Run each of our tests.
    for test in (test_id_read, test_config_read, test_mem_benchmark):
        for i in range(iterations):

            if test():
                pprint(f".", end="")
                passes += 1
            else:
                pprint(f"✗", end="")

                failures += 1
                failed_tests.add(test)

    fail_text = "<red>✗ FAILED</red>"
    pass_text = "<green>✓ PASSED</green>"
    pprint(HTML("\n\n<b><u>Results:</u></b>"))

    pprint(HTML(f"    ID READ:     {fail_text if test_id_read in failed_tests else pass_text}"))
    pprint(HTML(f"    CONFIG READ: {fail_text if test_config_read in failed_tests else pass_text}"))
    pprint(HTML(f"    BENCHMARK:   {fail_text if test_mem_benchmark in failed_tests else pass_text}"))


    print(f"\nDiagnostics completed with {passes} passes and {failures} failures.\n")
