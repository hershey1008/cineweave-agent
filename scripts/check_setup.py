"""Read-only setup inspection. Never prints environment values or secrets."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_env(path):
    values = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                key,value=line.split('=',1)
                values[key.strip()]=value.strip().strip('\"').strip("'")
    return values


def check(root=ROOT):
    env=read_env(root/'.env')
    checks={'env_file':(root/'.env').is_file()}
    for name in ['DB_PASSWORD','SECRET_KEY']:
        value=env.get(name,'')
        checks[name.lower()+'_configured']=len(value)>=16 and 'please-replace' not in value
    raw=Path(env.get('FUNREC_RAW_DATA_PATH','__missing__'))
    models=Path(env.get('FUNREC_MODELS_PATH','__missing__'))
    if not raw.is_absolute():
        raw=root/raw
    if not models.is_absolute():
        models=root/models
    checks['data_directory']=raw.is_dir()
    checks['movies_pickle']=(raw/'movies.pkl').is_file()
    checks['model_directory']=models.is_dir()
    checks['recall_directory']=(models/'recall').is_dir()
    checks['ranking_directory']=(models/'ranking').is_dir()
    checks['bge_weights']=(root/'artifacts/model_cache/bge-m3/pytorch_model.bin').is_file()
    checks['active_index']=(root/'artifacts/semantic_index/active.json').is_file()
    llm=[bool(env.get(name)) for name in ['LLM_BASE_URL','LLM_MODEL','LLM_API_KEY']]
    checks['llm_configuration_complete_or_empty']=all(llm) or not any(llm)
    local=[env.get(name,'').endswith('.local') for name in ['BACKEND_DOCKERFILE','SEMANTIC_DOCKERFILE','FRONTEND_DOCKERFILE']]
    return {'checks':checks,'all_files_ready':all(checks.values()),
            'llm_mode':'configured' if all(llm) else 'rules_or_incomplete',
            'build_profile':'requires_author_cached_images' if any(local) else 'portable_dockerfiles',
            'note':'File presence only; model integrity and live inference need separate checks.'}


if __name__=='__main__':
    report=check()
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(not report['all_files_ready'])
