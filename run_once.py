"""One scheduled multi-catalogue check with durable private-chat controls."""
import json,os,subprocess,sys
from pathlib import Path
from telegram_client import send
from catalogue_sources import SOURCES

def summarize(reports,requested):
    result={'catalogues':reports,'requested_scan':requested,'errors':[]}
    for key in ('unique_products','successful_endpoints','requested_endpoints','delivered_messages','delivered_offers'):
        result[key]=sum(r.get(key,0) for r in reports)
    for r in reports:
        result['errors'].extend({'catalogue':r['catalogue'],**e} for e in r.get('errors',[]))
    result['checked_at']=max((r.get('checked_at','') for r in reports),default='')
    result['scope']='combined Grocery, Mall and restaurant checks'
    return result

def main():
    root=Path(os.environ.get('BREADFAST_STATE_DIR',str(Path(__file__).resolve().parent)))
    root.mkdir(parents=True,exist_ok=True)
    health=root/'health-state.json'
    previous=json.loads(health.read_text()) if health.exists() else {}
    from bot_controls import poll,complete
    requested=poll(root)
    mode='--full' if os.environ.get('BREADFAST_FORCE_FULL','').lower()=='true' or requested=='full' else None if requested=='offers' else '--auto'
    reports=[]
    for source in SOURCES:
        command=[sys.executable,str(Path(__file__).with_name('scan.py')),'--telegram','--catalogue',source]
        if mode:command.append(mode)
        r=subprocess.run(command,capture_output=True,text=True)
        try:report=json.loads(r.stdout)
        except ValueError:report={'catalogue':source,'errors':[{'stage':'discovery','error':'Catalogue scan failed before producing a report'}]}
        if r.returncode and not report.get('errors'):report['errors']=[{'stage':'scan','error':'Catalogue scan did not complete'}]
        reports.append(report)
    report=summarize(reports,requested)
    # Keep the summary free of product bodies, credentials, and private coordinates.
    slim=[]
    for r in reports:
        slim.append({k:r.get(k) for k in ('catalogue','coverage','scope','category_count','requested_endpoints','successful_endpoints','unique_products','delivered_messages','delivered_offers','delivery_batches','errors')})
    report['catalogues']=slim
    Path(__file__).with_name('combined-scan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if report['errors']:
        print(json.dumps(report,ensure_ascii=False))
        if not previous.get('failed'):
            try:
                send('Breadfast watcher: a catalogue scan or notification failed. Other successful catalogues may have sent offers. The next check will retry; a complete scan is not confirmed.')
                health.write_text(json.dumps({'failed':True}))
            except Exception:pass
        return 2
    if previous.get('failed'):
        try:send('Breadfast watcher recovered. All catalogue checks and Telegram delivery are working again.')
        except Exception:return 2
    health.write_text(json.dumps({'failed':False}))
    if requested:complete(root,report)
    print(json.dumps(report,ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
