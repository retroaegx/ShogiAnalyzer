from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from app_paths import runtime_home, resource_root
from external_process import external_env, split_command
from installer.cpu_variants import choose_engine, binary_target
from installer.installer_lib import _pick_engine_variant, _platform_key


class PortableTests(unittest.TestCase):
    def test_quoted_command_paths_and_arguments(self):
        import subprocess
        import shlex
        expected=["C:/Program Files/ShogiAnalyzer/engine.exe", "--name", "two words", ""]
        command=subprocess.list2cmdline(expected) if sys.platform=="win32" else shlex.join(expected)
        self.assertEqual(split_command(command),expected)

    def test_native_platform_does_not_fall_back_to_another_cpu(self):
        engine = {'platforms':[{'os':'linux','arch':'amd64'}, {'os':'darwin','arch':'arm64'}]}
        with patch('installer.installer_lib._os_key', return_value='linux'), patch('installer.installer_lib._arch_key',return_value='arm64'):
            self.assertIsNone(_pick_engine_variant(engine))
            self.assertEqual(_platform_key(), 'linux_arm64')

    def test_runtime_and_resources_are_separate_in_frozen_build(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(sys,'frozen',True,create=True), patch.object(sys,'_MEIPASS',str(Path(temp)/'_internal'),create=True), patch.object(sys,'executable',str(Path(temp)/'ShogiAnalyzer.exe')), patch.dict(os.environ,{'SHOGI_ANALYZER_HOME':''}):
                self.assertEqual(resource_root(),Path(temp)/'_internal')
                self.assertEqual(runtime_home(),Path(temp))
            with patch.dict(os.environ,{'SHOGI_ANALYZER_HOME':temp}):
                self.assertEqual(runtime_home(),Path(temp))

    def test_external_libraries_restore_original_environment(self):
        with patch.object(sys,'frozen',True,create=True), patch.object(sys,'_MEIPASS','/bundle',create=True):
            env={'LD_LIBRARY_PATH':'/bundle','LD_LIBRARY_PATH_ORIG':'/system/lib','PATH':os.pathsep.join(['/bundle','/bundle/bin','/bundle-other','/usr/bin'])}
            result=external_env(env)
            self.assertEqual(result['LD_LIBRARY_PATH'],'/system/lib')
            self.assertEqual(result['PATH'],os.pathsep.join(['/bundle-other','/usr/bin']))
            self.assertEqual(env['LD_LIBRARY_PATH'],'/bundle')

    def test_unsupported_cpu_binary_is_never_the_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            elf=bytearray(64)
            elf[:6]=b'\x7fELF\x02\x01'
            elf[18:20]=(62).to_bytes(2,'little')
            (root/'Engine_AVX512').write_bytes(elf)
            (root/'Engine_AVX2').write_bytes(elf)
            (root/'Engine_SSE42').write_bytes(elf)
            self.assertIsNone(choose_engine(root,'linux','amd64',set()))
            self.assertEqual(choose_engine(root,'linux','amd64',{'avx2'}).name,'Engine_AVX2')
            self.assertEqual(choose_engine(root,'linux','amd64',{'sse4_2'}).name,'Engine_SSE42')
            self.assertIsNone(choose_engine(root,'darwin','amd64',{'avx2'}))
            self.assertIsNone(choose_engine(root,'linux','arm64',{'avx2'}))

    def test_universal_macos_and_type_hint_are_respected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            universal=b'\xca\xfe\xba\xbe'+struct.pack('>I',2)
            universal+=struct.pack('>IIIII',0x01000007,0,0,0,0)+struct.pack('>IIIII',0x0100000c,0,0,0,0)
            path=root/'Engine_M1'
            path.write_bytes(universal)
            self.assertEqual(binary_target(path),('darwin',{'amd64','arm64'}))
            self.assertEqual(choose_engine(root,'darwin','arm64',set(),'M1'),path)
            self.assertIsNone(choose_engine(root,'darwin','arm64',set(),'AnotherEdition'))


if __name__=='__main__':
    unittest.main()
