"""Run independently of Codex, in a container or on a server with persistent storage."""
import os,subprocess,sys,time
from pathlib import Path
from telegram_client import send

def main():
    interval=max(300,int(os.environ.get('SCAN_INTERVAL_SECONDS','600')))
    previous_failure=None
    while True:
        started=time.monotonic()
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('scan.py')),'--auto','--telegram'],capture_output=True,text=True)
        if result.returncode:
            failure='Breadfast scanner could not complete a check. Results may be incomplete; it will retry on the next check.'
            print(failure,flush=True)
            if previous_failure!=failure:
                try:send(failure)
                except Exception:pass
            previous_failure=failure
        else:
            print('Breadfast check completed.',flush=True)
            if previous_failure:
                try:send('Breadfast scanning has recovered. Checks are running again.')
                except Exception:pass
            previous_failure=None
        time.sleep(max(1,interval-(time.monotonic()-started)))

if __name__=='__main__':main()
