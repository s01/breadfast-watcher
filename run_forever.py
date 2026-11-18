"""Run the same multi-catalogue check independently on a persistent server."""
import os,subprocess,sys,time
from pathlib import Path

def main():
    interval=max(300,int(os.environ.get('SCAN_INTERVAL_SECONDS','300')))
    while True:
        started=time.monotonic()
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('run_once.py'))])
        print('Breadfast check completed.' if result.returncode==0 else 'Breadfast check failed; the next check will retry.',flush=True)
        time.sleep(max(1,interval-(time.monotonic()-started)))

if __name__=='__main__':main()
