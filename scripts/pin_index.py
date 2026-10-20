"""Pin the backend's expected semantic index version in the local .env."""
import json
import re
from pathlib import Path

root=Path(__file__).resolve().parents[1]
version=json.loads((root/'artifacts/semantic_index/active.json').read_text(encoding='utf-8'))['version']
if not re.fullmatch(r'[A-Za-z0-9_-]+',version):
    raise ValueError('Invalid index version')
env=root/'.env'
content=env.read_text(encoding='utf-8')
line='SEMANTIC_INDEX_VERSION='+version
if re.search(r'^SEMANTIC_INDEX_VERSION=.*$',content,re.M):
    content=re.sub(r'^SEMANTIC_INDEX_VERSION=.*$',line,content,flags=re.M)
else:
    content=content.rstrip()+'\n'+line+'\n'
env.write_text(content,encoding='utf-8')
print('Pinned index version:',version)
