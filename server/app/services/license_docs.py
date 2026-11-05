"""Read only license documents shipped with this application, never user data."""
from __future__ import annotations

import html
import json
from pathlib import Path
import sys

from app_paths import is_frozen, resource_root


def documents() -> dict[str, Path]:
    root=resource_root()
    result={'app':root/'LICENSE'}
    result['distribution']=(Path(sys.executable).parent/'THIRD_PARTY.txt' if is_frozen()
                            else root/'docs/THIRD_PARTY.md')
    notices=root/'third_party_notices'
    if notices.is_dir():
        for path in sorted(notices.rglob('*')):
            if path.is_file() and path.resolve().is_relative_to(notices.resolve()):
                result['notices/'+path.relative_to(notices).as_posix()]=path
    return {key:path for key,path in result.items() if path.is_file()}


def overview() -> str:
    root=resource_root()
    files=documents()
    inventory=root/'third_party_notices/INVENTORY.json'
    entries=json.loads(inventory.read_text(encoding='utf-8')) if inventory.is_file() else {}
    def link(key, label):
        from urllib.parse import quote
        return f'<a href="/api/app/license-document/{quote(key, safe="/")}">{html.escape(label)}</a>'
    parts=['<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>同梱ソフトウェアのライセンス — ShogiAnalyzer</title>',
           '<style>body{font:16px/1.7 system-ui;max-width:1000px;margin:32px auto;padding:0 20px}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #bbb;text-align:left}a{overflow-wrap:anywhere}</style>',
           '<h1>同梱ソフトウェアのライセンス</h1>',
           '<p>ShogiAnalyzer本体はMITです。同梱ソフトウェアにはそれぞれの条件が適用されます。</p>']
    for key,label in [('app','ShogiAnalyzer本体のMITライセンス'),('distribution','同梱物の条件・対応ソース・差し替え方法')]:
        if key in files: parts.append('<p>'+link(key,label)+'</p>')
    if not entries:
        parts.append('<p>ソース実行版です。ネイティブ配布物の依存一覧はありません。使用中のPython・ライブラリーの原文は、ご自身のPython環境の各パッケージに付属します。上記の同梱物の説明も参照してください。</p>')
    else:
        parts.append('<h2>この配布物のPythonライブラリー</h2><table><tr><th>名前・版</th><th>ライセンス</th><th>原文</th></tr>')
        for row in entries.get('packages',[]):
            links=[link('notices/'+name,Path(name).name) for name in row['notices'] if 'notices/'+name in files]
            parts.append('<tr><td>'+html.escape(row['name']+' '+row['version'])+'</td><td>'+html.escape(row['license'])+'</td><td>'+'<br>'.join(links)+'</td></tr>')
        parts.append('</table>')
    parts.append('<h2>Python本体・ネイティブ部品・原文資料</h2><ul>')
    for key in files:
        if key.startswith('notices/') and '/' not in key[len('notices/'):]:
            parts.append('<li>'+link(key,key[len('notices/'):])+'</li>')
    return ''.join(parts)+'</ul></html>'
