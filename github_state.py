"""Persist only non-personal discount state on the monitor-state branch."""
import base64,datetime,json,os,re,subprocess,sys
from pathlib import Path
BRANCH='monitor-state'
FILES=('telegram-state.json','full-scan.json','health-state.json')
ROOT=Path(os.environ.get('BREADFAST_STATE_DIR','state'))
REPO=os.environ.get('GITHUB_REPOSITORY','')

def api(path,method='GET',payload=None,missing_ok=False):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',REPO): raise RuntimeError('Invalid repository configuration')
    cmd=['gh','api','repos/'+REPO+'/'+path,'--method',method]
    if payload is not None: cmd+=['--input','-']
    r=subprocess.run(cmd,input=json.dumps(payload) if payload is not None else None,text=True,capture_output=True)
    if r.returncode:
        if missing_ok and '(HTTP 404)' in r.stderr:return None
        raise RuntimeError('GitHub state request failed: '+method+' '+path)
    return json.loads(r.stdout) if r.stdout.strip() else None

def load():
    ROOT.mkdir(parents=True,exist_ok=True)
    ref=api('git/ref/heads/'+BRANCH,missing_ok=True)
    if ref is None:
        print('No prior cloud state; first successful delivery is the initial snapshot.')
        return
    tree=api('git/trees/'+ref['object']['sha'])
    for item in tree['tree']:
        if item['path'] not in FILES:continue
        blob=api('git/blobs/'+item['sha'])
        raw=base64.b64decode(blob['content'])
        json.loads(raw)
        (ROOT/item['path']).write_bytes(raw)
    print('Restored cloud alert state.')

def save():
    ref=api('git/ref/heads/'+BRANCH,missing_ok=True)
    previous={}
    if ref:
        tree=api('git/trees/'+ref['object']['sha'])
        previous={i['path']:i['sha'] for i in tree['tree'] if i['path'] in FILES}
    entries=[];changed=False
    for name in FILES:
        p=ROOT/name
        if not p.exists():continue
        value=json.loads(p.read_text())
        if name=='full-scan.json':value={'checked_at':value['checked_at']}
        raw=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
        import hashlib
        digest=hashlib.sha1(b'blob '+str(len(raw.encode())).encode()+b'\0'+raw.encode()).hexdigest()
        entries.append({'path':name,'mode':'100644','type':'blob','content':raw})
        changed|=previous.get(name)!=digest
    if not entries or not changed:
        print('Cloud state unchanged.');return
    newtree=api('git/trees','POST',{'tree':entries})
    payload={'message':'Update discount alert state','tree':newtree['sha'],'parents':[ref['object']['sha']] if ref else []}
    commit=api('git/commits','POST',payload)
    if ref:api('git/refs/heads/'+BRANCH,'PATCH',{'sha':commit['sha'],'force':False})
    else:api('git/refs','POST',{'ref':'refs/heads/'+BRANCH,'sha':commit['sha']})
    print('Saved cloud alert state.')

if __name__=='__main__':
    try:
        {'load':load,'save':save}[sys.argv[1]]()
    except Exception as e:
        print(str(e),file=sys.stderr);raise SystemExit(1)
