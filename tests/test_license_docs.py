import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server.app.services import license_docs


class LicenseDocumentTests(unittest.TestCase):
    def test_catalog_excludes_runtime_settings_and_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'LICENSE').write_text('app MIT')
            (root/'docs').mkdir()
            (root/'docs/THIRD_PARTY.md').write_text('distribution terms')
            (root/'.env').write_text('private setting')
            notices=root/'third_party_notices'
            notices.mkdir()
            (notices/'library.txt').write_text('library terms')
            with patch.object(license_docs,'resource_root',return_value=root),patch.object(license_docs,'is_frozen',return_value=False):
                catalog=license_docs.documents()
                self.assertIn('notices/library.txt',catalog)
                self.assertNotIn('.env',catalog)
                self.assertNotIn('notices/../.env',catalog)
                self.assertNotIn('../.env',catalog)

    def test_inventory_text_is_escaped_and_license_documents_are_linked(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            notices=root/'third_party_notices'
            notices.mkdir()
            (notices/'license.txt').write_text('copyright')
            (notices/'INVENTORY.json').write_text(json.dumps({'packages':[
                {'name':'<script>bad()</script>','version':'1','license':'MIT',
                 'notices':['license.txt']}]}))
            with patch.object(license_docs,'resource_root',return_value=root),patch.object(license_docs,'is_frozen',return_value=False):
                page=license_docs.overview()
                self.assertNotIn('<script>',page)
                self.assertIn('&lt;script&gt;',page)
                self.assertIn('/api/app/license-document/notices/license.txt',page)
