import telnetlib
from time import sleep
from typing import Optional, Union

from pytest_embedded.log import to_bytes
from pytest_embedded_idf.app import IdfApp
from pytest_embedded_serial.dut import SerialDut

from .gdb import Gdb
from .openocd import OpenOcd


class JtagDut(SerialDut):
    """
    JTAG dut class

    :ivar: app: :class:`pytest_embedded_idf.app.IdfApp` instance
    :ivar: openocd: :class:`pytest_embedded_jtag.openocd.OpenOcd` instance
    :ivar: gdb: :class:`pytest_embedded_jtag.gdb.Gdb` instance
    """

    def __init__(
        self,
        openocd: OpenOcd,
        gdb: Gdb,
        app: Optional[IdfApp] = None,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(app, *args, **kwargs)
        self.openocd = openocd
        self.gdb = gdb

        sleep(1)  # make sure openocd already opened telnet port
        self.telnet = telnetlib.Telnet(self.openocd.TELNET_HOST, self.openocd.TELNET_PORT, 5)
        self.telnet.send = self.telnet_send

        self.openocd.create_forward_io_process(self.pexpect_proc, source='openocd')
        self.gdb.create_forward_io_process(self.pexpect_proc, source='gdb')

        self._sessions_close_methods.extend(
            [
                self.openocd.terminate,
                self.gdb.terminate,
                self.telnet.close,
            ]
        )

    def telnet_send(self, s: Union[bytes, str]) -> None:
        """
        Send commands through telnet port, could also be called by :func:`self.telnet.send`

        :param s: ``bytes`` or ``str``
        """
        self.telnet.write(to_bytes(s, '\n'))