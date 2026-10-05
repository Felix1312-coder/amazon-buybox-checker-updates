import hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import runtime,updater

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.bundle=(Path(__file__).parent/'release'/'variation-monitor-0.4.0.zip').read_bytes()
        self.manifest=json.loads((Path(__file__).parent/'release'/'latest.json').read_text())
    def tearDown(self):self.temp.cleanup()
    def test_install_preserves_user_data_and_loads_payload(self):
        db=self.root/'monitor.sqlite';db.write_bytes(b'existing-user-data')
        runtime.install_bundle(self.bundle,self.manifest,self.root/'updates')
        chosen=runtime.active_payload(self.root/'updates',Path(__file__).parent/'payload')
        self.assertIn('versions',str(chosen));self.assertEqual(runtime.validate_payload(chosen)['version'],'0.4.0')
        self.assertEqual(db.read_bytes(),b'existing-user-data')
    def test_corrupted_download_keeps_active(self):
        runtime.install_bundle(self.bundle,self.manifest,self.root)
        pointer=(self.root/'active.json').read_bytes()
        with self.assertRaises(ValueError):runtime.install_bundle(self.bundle+b'x',self.manifest,self.root)
        self.assertEqual(pointer,(self.root/'active.json').read_bytes())
    def test_invalid_archive_paths_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('../app.py','bad')
        m={**self.manifest,'sha256':hashlib.sha256(b.getvalue()).hexdigest()}
        with self.assertRaises(ValueError):runtime.install_bundle(b.getvalue(),m,self.root)
        self.assertFalse((self.root/'active.json').exists())
    def test_bad_active_payload_falls_back(self):
        runtime.install_bundle(self.bundle,self.manifest,self.root)
        target=runtime.active_payload(self.root,Path(__file__).parent/'payload')
        (target/'app.py').write_text('broken')
        self.assertEqual(runtime.active_payload(self.root,Path(__file__).parent/'payload'),Path(__file__).parent/'payload')
    def test_incompatible_runtime_rejected(self):
        with self.assertRaises(ValueError):runtime.install_bundle(self.bundle,{**self.manifest,'launcher_protocol':2},self.root)
    def test_download_restricts_update_origin(self):
        with self.assertRaises(ValueError):updater.fetch('https://example.com/update.zip',100)
    def test_offline_remains_usable(self):
        with patch.object(updater,'manifest',side_effect=OSError('offline')):updater.task(self.root)
        self.assertFalse(updater.STATE['busy']);self.assertIn('bisherige App bleibt nutzbar',updater.STATE['message'])
    def test_version_order(self):
        self.assertGreater(runtime.version_tuple('0.10.0'),runtime.version_tuple('0.9.0'))
        with self.assertRaises(ValueError):runtime.version_tuple('../1.2.3')
