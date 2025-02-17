from pytest_embedded.app import App
from pytest_embedded.dut import Dut
from pytest_embedded.log import PexpectProcess

from .serial import Serial


class SerialDut(Dut):
    """
    Dut class for serial ports
    """

    def __init__(self, pexpect_proc: PexpectProcess, app: App, serial: Serial, **kwargs) -> None:
        """
        Args:
            pexpect_proc: `PexpectProcess` instance
            app: `App` instance
            serial: `Serial` instance
        """
        super().__init__(pexpect_proc, app, **kwargs)

        self.serial = serial
        self.serial.create_forward_io_process(self.pexpect_proc, source='serial')

        self.proc_close_methods.append(self.serial.close)

    def write(self, data: bytes) -> int:
        return self.serial.proc.write(data)
