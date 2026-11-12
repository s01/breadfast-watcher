"""One monitored scheduled check; durable failure/recovery notification state."""
import json,os,subprocess,sys
from pathlib import Path
from telegram_client import send

def main():
    root=Path(os.environ.get('BREADFAST_STATE_DIR',str(Path(__file__).resolve().parent)))
    root.mkdir(parents=True,exist_ok=True)
    health=root/'health-state.json'
    previous=json.loads(health.read_text()) if health.exists() else {}
    r=subprocess.run([sys.executable,str(Path(__file__).with_name('scan.py')),'--auto','--telegram'],capture_output=True,text=True)
    if r.returncode:
        print('Breadfast check failed. Inspect the report and workflow logs; this is not evidence of no offers.')
        if not previous.get('failed'):
            try:
                send('Breadfast watcher: a scan or notification failed. Monitoring may be incomplete; the next scheduled run will retry.')
                health.write_text(json.dumps({'failed':True}))
            except Exception:pass
        return r.returncode
    if previous.get('failed'):
        try:send('Breadfast watcher recovered. Scans and Telegram delivery are working again.')
        except Exception:return 2
    health.write_text(json.dumps({'failed':False}))
    report=json.loads(Path(__file__).with_name('latest-scan.json').read_text())
    print(json.dumps({k:report.get(k) for k in ('checked_at','scope','successful_endpoints','requested_endpoints','unique_products','delivered_messages','errors')}))
    return 0

if __name__=='__main__':raise SystemExit(main())
