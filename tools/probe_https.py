"""Exercise the packaged downloader without accepting engine terms or fetching engines."""
import argparse
import json
from pathlib import Path
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

if not getattr(sys,'frozen',False):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from https_client import create_https_context, verified_urlopen
from installer.installer_lib import _download
from server.app.services.update_checker import _latest_release


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--full',action='store_true')
    args=parser.parse_args()
    report={'ok':False,'checks':{}}
    try:
        context=create_https_context()
        assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
        report['checks']['verification_required']=True
        targets=[
            'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe',
            'https://storage.yaneu.com/yaneuraou/YaneuraOuV990-win64-forTuyo11.7z',
        ]
        if args.full:
            targets.append('https://drive.usercontent.google.com/download?id=1bf7GGGM8vM8kQ_icAwbiR7IM6uH3BJ4u&export=download&confirm=t')
        for url in targets:
            request=urllib.request.Request(url,method='HEAD',headers={'User-Agent':'ShogiAnalyzer HTTPS check'})
            with verified_urlopen(request,timeout=40) as response:
                assert response.status==200
                # Never persist signed redirect query strings.
                report['checks'][urllib.parse.urlsplit(url).hostname]={'status':response.status,
                    'final_host':urllib.parse.urlsplit(response.url).hostname}
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'LICENSE.txt'
            _download('https://raw.githubusercontent.com/python/cpython/v3.12.10/LICENSE',target)
            assert b'PYTHON SOFTWARE FOUNDATION LICENSE' in target.read_bytes()
            report['checks']['real_download_bytes']=target.stat().st_size
        try:
            release=_latest_release('retroaegx/ShogiAnalyzer')
            assert release.get('tag_name')
            report['checks']['release_check']=True
        except urllib.error.HTTPError as error:
            # Shared CI egress can exhaust GitHub's unauthenticated API quota.
            # A verified HTTP response proves TLS, but not release metadata.
            if error.code != 403 or error.headers.get('x-ratelimit-remaining') != '0':
                raise
            report['checks']['release_check']={'status':'rate_limited',
                'http_status':403,'release_metadata_verified':False}
        if args.full:
            for host in ('self-signed.badssl.com','wrong.host.badssl.com'):
                try:
                    verified_urlopen('https://'+host,timeout=20).close()
                except urllib.error.URLError as error:
                    if not isinstance(error.reason,ssl.SSLCertVerificationError):
                        raise
                    report['checks'][host]='certificate rejected'
                else:
                    raise AssertionError('Invalid certificate accepted: '+host)
        report['ok']=True
    except Exception as error:
        report['error']=repr(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':
    main()
