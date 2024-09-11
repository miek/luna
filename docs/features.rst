================
Status & Support
================

.. role:: planned
.. role:: inprogress
.. role:: complete

The LUNA library is a work in progress; but many of its features are usable enough for inclusion in your own designs.
More testing of our work -- and more feedback -- is always appreciated!

Support for Device Mode
-----------------------

.. list-table::
    :header-rows: 1
    :widths: 1 2 1

    * - Feature
      -
      - Status
    * - **USB Communications**
      - high-/full-speed with ``UTMI`` PHY
      - :inprogress:`complete, needs testing`
    * -
      - high-/full-speed with ``ULPI`` PHY
      - :complete:`feature complete`
    * -
      - full-speed using raw gpio / pull resistors
      - :complete:`feature complete`
    * -
      - super-speed using PIPE PHY
      - :inprogress:`basic support complete; still experimental`
    * -
      - super-speed using SerDes PHY
      - :inprogress:`in progress`
    * -
      - low speed, via ULPI/UTMI PHY
      - :planned:`untested`
    * -
      - low speed, using raw gpio / pull resistors
      - :planned:`unsupported, currently`
    * -
      -
      -
    * - **Control Transfers / Endpoints**
      - user-defined
      - :complete:`feature complete`
    * -
      - fully-gateware-implemented, with user vendor request handler support
      - :inprogress:`complete, could use improvements`
    * -
      -
      -
    * - **Bulk Transfers / Endpoints**
      - user-defined
      - :complete:`feature complete`
    * -
      - ``IN`` stream helpers
      - :complete:`feature complete`
    * -
      - ``OUT`` stream helpers
      - :complete:`feature complete`
    * -
      -
      -
    * - **Interrupt Transfers / Endpoints**
      - user-defined
      - :complete:`feature complete`
    * -
      - status-to-host helper
      - :inprogress:`complete, needs testing`
    * -
      - status-from-host helper
      - :planned:`planned`
    * -
      -
      -
    * - **Isochronous Transfers / Endpoints**
      - user-defined
      - :planned:`planned`
    * -
      - ``IN`` transfer helpers
      - :inprogress:`complete; needs examples and testing`
    * -
      - ``OUT`` transfer helpers
      - :planned:`planned`


Support for Host Mode
-----------------------

The LUNA library currently does not provide any support for operating as a USB host; though the low-level USB
communications interfaces have been designed to allow for eventual host support. Host support is not currently
a priority, but contributions are welcome.


"Reference" Boards
------------------

The LUNA library is intended to work on any FPGA with sufficient fabric performance and resources. We regularly
test on `Cynthion <https://greatscottgadgets.com/cynthion/>`_ and it serves as a reference platform for LUNA.
See the repositories for `Cynthion software/gateware <https://github.com/greatscottgadgets/cynthion>`_ and
`Cynthion hardware <https://github.com/greatscottgadgets/cynthion-hardware>`_ for more.

Previously, this repository contained platform definitions for a range of other hardware. These are retained in
the `luna-boards repository <https://github.com/greatscottgadgets/luna-boards>`_, but are unmaintained going forward.
