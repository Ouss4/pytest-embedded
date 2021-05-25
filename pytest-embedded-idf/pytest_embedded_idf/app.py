import json
import logging
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from pytest_embedded.app import App


class IdfApp(App):
    """
    Idf App class

    :ivar: sdkconfig: dict contains all k-v pairs from the sdkconfig file
    :ivar: partition_table: dict generated by partition tool
    :ivar: flash_files: list of (offset, file path) of normal flash files
    :ivar: encrypt_files: list of (offset, file path) of encrypted flash files
    :ivar: flash_settings: dict of flash settings
    """

    FLASH_ARGS_FILENAME = 'flasher_args.json'

    def __init__(
        self,
        app_path: str = os.getcwd(),
        part_tool: Optional[str] = None,
        *args,
        **kwargs,
    ):
        super().__init__(app_path, *args, **kwargs)
        self.binary_path = self._get_binary_path()
        if not self.binary_path:
            return

        self.elf_file = self._get_elf_file()
        self.parttool_path = self._get_parttool_file(part_tool)

        self.sdkconfig = self._parse_sdkconfig()
        self.flash_files, self.flash_settings = self._parse_flash_args()
        self.partition_table = self._parse_partition_table()

        self.target = self._get_target_from_sdkconfig()

    def _get_binary_path(self) -> Optional[str]:
        path = os.path.join(self.app_path, 'build')

        if path and os.path.exists(path):
            return os.path.realpath(path)
        logging.warning(f'{path} not exists')
        return None

    def _get_elf_file(self) -> Optional[str]:
        for fn in os.listdir(self.binary_path):
            if os.path.splitext(fn)[-1] == '.elf':
                return os.path.realpath(os.path.join(self.binary_path, fn))
        return None

    def _get_possible_sdkconfig_paths(self) -> List[str]:
        return [
            os.path.join(self.binary_path, '..', 'sdkconfig'),
            os.path.join(self.binary_path, 'sdkconfig'),
        ]

    def _get_sdkconfig_file(self) -> Optional[str]:
        for file in self._get_possible_sdkconfig_paths():
            if os.path.isfile(file):
                return os.path.realpath(file)
        return None

    def _parse_sdkconfig(self) -> Optional[Dict[str, Any]]:
        sdkconfig_filepath = self._get_sdkconfig_file()
        if not sdkconfig_filepath:
            return None

        res = {}
        with open(self._get_sdkconfig_file()) as fr:
            for line in fr:
                configs = line.split('=')
                if len(configs) == 2:
                    res[configs[0]] = configs[1].rstrip().strip('"')
        return res

    def _get_flash_args_file(self) -> Optional[str]:
        for fn in os.listdir(self.binary_path):
            if fn == self.FLASH_ARGS_FILENAME:
                return os.path.realpath(os.path.join(self.binary_path, fn))
        return None

    def _is_encrypted(self, flash_args: Dict[str, Any], offset: int, file_path: str):
        for entry in flash_args.values():
            try:
                if (entry['offset'], entry['file']) == (offset, file_path):
                    return entry['encrypted'] == 'true'
            except (TypeError, KeyError):
                continue

        return False

    def _parse_flash_args(
        self,
    ) -> Tuple[Optional[List[Tuple[int, str, bool]]], Optional[Dict[str, Any]]]:
        """
        :return: (flash_files: [(offset, file_path, encrypted), ...],
                  flash_settings: dict[str, str])
        """
        flash_args_filepath = self._get_flash_args_file()
        if not flash_args_filepath:
            return None, None

        with open(flash_args_filepath) as fr:
            flash_args = json.load(fr)

        res = []
        for (offset, file_path) in flash_args['flash_files'].items():
            encrypted = self._is_encrypted(flash_args, offset, file_path)
            res.append((int(offset, 0), os.path.join(self.binary_path, file_path), encrypted))

        flash_files = sorted(res)
        flash_settings = flash_args['flash_settings']
        flash_settings['encrypt'] = any([file[2] for file in res])

        return flash_files, flash_settings

    def _get_parttool_file(self, parttool: Optional[str]) -> Optional[str]:
        parttool_filepath = parttool or os.path.join(
            os.getenv('IDF_PATH', ''),
            'components',
            'partition_table',
            'gen_esp32part.py',
        )
        if os.path.isfile(parttool_filepath):
            return os.path.realpath(parttool_filepath)
        return None

    def _parse_partition_table(self) -> Optional[Dict[str, Any]]:
        if not (self.parttool_path and self.flash_files):
            return None

        errors = []
        for _, file, _ in self.flash_files:
            if 'partition' in os.path.split(file)[1]:
                partition_file = os.path.join(self.binary_path, file)
                process = subprocess.Popen(
                    [sys.executable, self.parttool_path, partition_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                (raw_data, raw_error) = process.communicate()
                if isinstance(raw_error, bytes):
                    raw_error = raw_error.decode()
                if 'Traceback' in raw_error:
                    # Some exception occurred. It is possible that we've tried the wrong binary file.
                    errors.append((file, raw_error))
                    continue
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode()
                break
        else:
            traceback_msg = '\n'.join([f'{self.parttool_path} {p}:{os.linesep}{msg}' for p, msg in errors])
            raise ValueError(f'No partition table found under {self.binary_path}\n' f'{traceback_msg}')

        partition_table = {}
        for line in raw_data.splitlines():
            if line[0] != '#':
                try:
                    _name, _type, _subtype, _offset, _size, _flags = line.split(',')
                    if _size[-1] == 'K':
                        _size = int(_size[:-1]) * 1024
                    elif _size[-1] == 'M':
                        _size = int(_size[:-1]) * 1024 * 1024
                    else:
                        _size = int(_size)
                    _offset = int(_offset, 0)
                except ValueError:
                    continue
                partition_table[_name] = {
                    'type': _type,
                    'subtype': _subtype,
                    'offset': _offset,
                    'size': _size,
                    'flags': _flags,
                }
        return partition_table

    def _get_target_from_sdkconfig(self):
        return self.sdkconfig.get('CONFIG_IDF_TARGET', 'esp32')
