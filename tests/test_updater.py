import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from installer import update as u
from installer.update_lock import installation_lock, InstallationBusy
from installer.update_launchers import write_launchers


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, {k: '' for k in ['SHOGI_ANALYZER_ENGINE_PATH',
            'SHOGI_ANALYZER_ENGINE_EVAL_DIR','SHOGI_ANALYZER_HOME','SHOGI_ANALYZER_UPDATE_REPO']})
        self.env.start(); self.port = patch.object(u, 'app_running', return_value=False); self.port.start()
    def tearDown(self):
        self.port.stop(); self.env.stop(); self.temp.cleanup()
    def package(self, path, version='2.0.0', native=False):
        path.mkdir(parents=True)
        if native:
            (path/'_internal').mkdir(); (path/'_internal/VERSION').write_text(version)
            (path/('ShogiAnalyzer.exe' if sys.platform=='win32' else 'ShogiAnalyzer')).write_bytes(b'new executable')
        else:
            (path/'VERSION').write_text(version); (path/'installer').mkdir(); (path/'installer/run.py').write_text('new')
            (path/'server/assets_web').mkdir(parents=True); (path/'server/assets_web/index.html').write_text('new page')
        return path
    def zip(self, folder, out):
        with zipfile.ZipFile(out, 'w') as z:
            for p in folder.rglob('*'):
                if p.is_file(): z.write(p, Path('ShogiAnalyzer')/p.relative_to(folder))
        return hashlib.sha256(out.read_bytes()).hexdigest()
    def test_each_os_cpu_selects_native_asset_not_source(self):
        assets=[{'name':f'ShogiAnalyzer-v2.0.0-{os_key}-{arch}{ext}'} for os_key,arch,ext in
                [('windows','amd64','.zip'),('linux','amd64','.tar.gz'),('macos','amd64','.tar.gz'),('macos','arm64','.tar.gz')]]
        release={'tag_name':'v2.0.0','assets':assets+[{'name':'ShogiAnalyzer-v2.0.0.zip'}]}
        for system,machine,label in [('Windows','AMD64','windows-amd64'),('Linux','x86_64','linux-amd64'),
                ('Darwin','x86_64','macos-amd64'),('Darwin','arm64','macos-arm64')]:
            self.assertIn(label,u.select_asset(release,native=True,system=system,machine=machine)['name'])
        with self.assertRaises(u.UpdateError):u.select_asset(release,native=True,system='Linux',machine='arm64')
    def test_source_update_preserves_user_data_even_if_archive_contains_it(self):
        target=self.package(self.root/'target','1.0.0');src=self.package(self.root/'pkg')
        keep={'.env':b'password=private','server/data/app.db':b'kifu','server/data/auth.json':b'auth',
              'engines/engine':b'engine','tools/cloudflared/cloudflared':b'tunnel','.venv/keep':b'python'}
        for name,data in keep.items():
            for base,content in [(target,data),(src,b'wrong')]:
                p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content)
        work=target/(u.WORK_PREFIX+'test');work.mkdir();unpacked=work/'unpacked';unpacked.mkdir();shutil.move(src,unpacked/'pkg')
        u.apply_package(unpacked/'pkg',target,work,native=False,home=target,version='v2.0.0')
        self.assertEqual((target/'VERSION').read_text(),'2.0.0')
        for name,data in keep.items():self.assertEqual((target/name).read_bytes(),data)
    def test_failed_native_health_check_restores_complete_old_runtime(self):
        target=self.package(self.root/'target','1.0.0',True);(target/'_internal/obsolete.dll').write_bytes(b'old')
        work=target/(u.WORK_PREFIX+'test');(work/'unpacked').mkdir(parents=True)
        src=self.package(work/'unpacked/pkg',native=True)
        with patch.object(u,'self_check',side_effect=[None,u.UpdateError('failed')]):
            with self.assertRaisesRegex(u.UpdateError,'元のアプリ'):u.apply_package(src,target,work,native=True,home=target,version='2.0.0')
        self.assertEqual((target/'_internal/VERSION').read_text(),'1.0.0')
        self.assertEqual((target/'_internal/obsolete.dll').read_bytes(),b'old')
    def test_partial_backup_copy_never_replaces_intact_original(self):
        target=self.package(self.root/'target','1.0.0');work=target/(u.WORK_PREFIX+'test');(work/'unpacked').mkdir(parents=True)
        (target/'installer/run.py').write_text('old code')
        src=self.package(work/'unpacked/pkg');copy=shutil.copy2;failed=False
        def fail(source,destination,*args,**kwargs):
            nonlocal failed
            if Path(source)==target/'installer/run.py' and not failed:
                failed=True;Path(destination).write_bytes(b'partial');raise OSError('disk full')
            return copy(source,destination,*args,**kwargs)
        with patch.object(u.shutil,'copy2',side_effect=fail):
            with self.assertRaises(u.UpdateError):u.apply_package(src,target,work,native=False,home=target,version='2.0.0')
        self.assertEqual((target/'installer/run.py').read_text(),'old code')
        self.assertEqual((target/'VERSION').read_text(),'1.0.0')
    def test_checksum_failure_changes_no_application_files(self):
        target=self.package(self.root/'target','1.0.0');src=self.package(self.root/'pkg');archive=self.root/'release.zip';self.zip(src,archive)
        asset={'name':'ShogiAnalyzer-v2.0.0.zip','browser_download_url':'https://example.invalid/release.zip','digest':'sha256:'+'0'*64}
        def download(url,dest,**kwargs):shutil.copyfile(archive,dest);return hashlib.sha256(dest.read_bytes()).hexdigest()
        with self.assertRaisesRegex(u.UpdateError,'SHA256'):
            u.perform_update(target,target,native=False,confirm=lambda:True,fetch_release=lambda repo:{'tag_name':'v2.0.0','assets':[asset]},downloader=download)
        self.assertEqual((target/'VERSION').read_text(),'1.0.0');self.assertEqual(list(target.glob(u.WORK_PREFIX+'*')),[])
    def test_cancel_does_not_download_or_create_workspace(self):
        target=self.package(self.root/'target','1.0.0');asset={'name':'ShogiAnalyzer-v2.0.0.zip'}
        with patch.object(u,'download') as download:
            self.assertFalse(u.perform_update(target,target,native=False,confirm=lambda:False,fetch_release=lambda r:{'tag_name':'v2.0.0','assets':[asset]}))
            download.assert_not_called()
        self.assertFalse(list(target.glob(u.WORK_PREFIX+'*')))
    def test_zip_rejects_traversal_windows_ads_and_protected_aliases(self):
        for i,name in enumerate(['../escape','/absolute','C:/escape','pkg/.env.','pkg/CON','pkg/a\\b']):
            with self.assertRaises(u.UpdateError):u.member_path(name)
            archive=self.root/f'{i}.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr(name,b'bad')
            # ZipInfo normalizes backslashes to '/' on Windows; that archive is safe.
            with zipfile.ZipFile(archive) as z:
                if z.namelist()[0]!=name:continue
            with self.assertRaises(u.UpdateError):u.extract_archive(archive,self.root/f'extract{i}')
    def test_interrupted_runtime_rename_recovers_before_version_read(self):
        target=self.package(self.root/'target','1.0.0',True);work=target/(u.WORK_PREFIX+'crash')
        (work/'backup').mkdir(parents=True);(work/'unpacked/pkg').mkdir(parents=True)
        os.replace(target/'_internal',work/'backup/_internal')
        u._journal(work/'transaction.json',{'target':str(target),'package':'pkg','status':'applying',
                   'operations':[{'path':'_internal','had_old':True}]})
        self.assertFalse(u.perform_update(target,target,native=True,fetch_release=lambda r:{'tag_name':'v1.0.0'}))
        self.assertEqual((target/'_internal/VERSION').read_text(),'1.0.0');self.assertFalse(work.exists())
    def test_helper_lifecycle_preserves_runtime_and_cleans_own_recovery_entry(self):
        target=self.package(self.root/'target','1.0.0',True);job=self.root/(u.JOB_PREFIX+'test')
        exe=target/('ShogiAnalyzer.exe' if sys.platform=='win32' else 'ShogiAnalyzer')
        with patch.object(u,'is_frozen',return_value=True),patch.object(u,'installation_root',return_value=target), \
             patch.object(u,'runtime_home',return_value=target),patch.object(u.sys,'executable',str(exe)):
            u.prepare_helper(job)
            self.assertEqual((job/'_internal/VERSION').read_text(),'1.0.0')
            self.assertTrue((target/'.UpdateRecovery.json').exists())
            with installation_lock(job):
                with self.assertRaises(InstallationBusy):u.cleanup_helper(job)
            u.cleanup_helper(job)
            self.assertFalse(job.exists());self.assertFalse((target/'.UpdateRecovery.json').exists())
    def test_tar_keeps_safe_links_and_rejects_escaping_chain(self):
        if sys.platform=='win32':self.skipTest('POSIX native bundles use symlinks')
        archive=self.root/'safe.tar.gz'
        with tarfile.open(archive,'w:gz') as t:
            f=tarfile.TarInfo('pkg/_internal/lib/version');f.size=2;f.mode=0o755;t.addfile(f,io.BytesIO(b'ok'))
            link=tarfile.TarInfo('pkg/_internal/library');link.type=tarfile.SYMTYPE;link.linkname='lib/version';t.addfile(link)
        root=u.extract_archive(archive,self.root/'safe');self.assertTrue((root/'_internal/library').is_symlink())
        self.assertEqual((root/'_internal/library').read_bytes(),b'ok')
        archive=self.root/'bad.tar.gz'
        with tarfile.open(archive,'w:gz') as t:
            link=tarfile.TarInfo('pkg/out');link.type=tarfile.SYMTYPE;link.linkname='../../escape';t.addfile(link)
        with self.assertRaises(u.UpdateError):u.extract_archive(archive,self.root/'bad')
    def test_locks_allow_multiple_app_processes_and_exclude_updater(self):
        root=self.root/'target';root.mkdir()
        code='from pathlib import Path;from installer.update_lock import installation_lock;import sys\nwith installation_lock(Path(sys.argv[1]),shared=sys.argv[2]=="shared"):pass'
        with installation_lock(root,shared=True):
            shared=subprocess.run([sys.executable,'-c',code,str(root),'shared'],capture_output=True)
            exclusive=subprocess.run([sys.executable,'-c',code,str(root),'exclusive'],capture_output=True)
            self.assertEqual(shared.returncode,0,shared.stderr);self.assertNotEqual(exclusive.returncode,0)
        with installation_lock(root):
            blocked=subprocess.run([sys.executable,'-c',code,str(root),'shared'],capture_output=True)
            self.assertNotEqual(blocked.returncode,0)
    def test_launchers_are_packaged_for_all_platforms(self):
        for platform,names in [('win32',['Update.bat']),('linux',['Update.sh']),('darwin',['Update.sh','Update.command'])]:
            folder=self.root/platform;folder.mkdir();write_launchers(folder,platform)
            for name in names:self.assertTrue((folder/name).is_file())
            if platform!='win32':self.assertNotIn(b'\r', (folder/names[0]).read_bytes())


if __name__=='__main__':unittest.main()
