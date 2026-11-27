"""Private local monitor. No Telegram access; stdout is a small UI report."""
import argparse, concurrent.futures, contextlib, datetime, fcntl, html, json, os, sys, threading, time, uuid
from pathlib import Path
sys.dont_write_bytecode = True  # Keep the signed app's Resources immutable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan
from catalogue_sources import plan, normalize, food_get, LABELS, product_batches
from local_history import update_history, render_history
from promotion_sources import discover
from catalogue_http import statistics,HTTPFailure

INTERVALS = {'grocery': 30, 'mall': 30, 'restaurants': 120}
FULL_INTERVAL = 180

class ScanResult(dict):
    errors = None
    retry_after = 0
    missing_ids = None

def fetch_catalogue(source, full, watched_ids=()):
    _, jobs = plan(source, full, scan.get)
    promoted,discovery_errors=discover(source)
    requested=set(map(str,watched_ids)) if not full else set()
    requested.update(promoted)
    jobs.extend(product_batches(source,requested))
    jobs = list({(p, json.dumps(q, sort_keys=True)) for p, q in jobs})
    products = ScanResult();products.errors=list(discovery_errors);queried=set()
    stopped=threading.Event()
    def fetch(job):
        if stopped.is_set():return None
        path, raw = job; query = json.loads(raw)
        time.sleep(.1)
        try:
            data = food_get(path) if source == 'restaurants' else scan.get(path, **query)
        except HTTPFailure as exc:
            if exc.status in (429,503):stopped.set()
            raise
        if not isinstance(data, (list, dict)):
            raise RuntimeError('Unexpected catalogue response')
        keep={'id','name','price','salePrice','stock','image','merchant_name','base_price_only','_catalogue','original_id'}
        normalized=[normalize(p, source, query) for p in scan.extract(data)]
        return [{k:v for k,v in p.items() if k in keep} for p in normalized]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch,j):j for j in jobs}
        for future in concurrent.futures.as_completed(futures):
            try:
                rows=future.result()
                if rows is None:continue
                for p in rows:products[str(p['id'])]=p
                path,raw=futures[future]
                if path=='products':queried.update(v for k,v in json.loads(raw).items() if k.startswith('ids['))
            except Exception as exc:
                path=futures[future][0]
                products.errors.append(path+': '+type(exc).__name__)
                if isinstance(exc,HTTPFailure) and exc.status in (429,503):products.retry_after=max(products.retry_after,exc.retry_after)
    products.missing_ids=queried-set(products)
    return products

def ingest(state, source, products, full, now):
    entry = state.setdefault('sources', {}).setdefault(source, {})
    first = not entry.get('initialized')
    update_history(state,source,products,full,now,baseline=first)
    offers, current = scan.new_offers(products, entry.get('offers', {}))
    if first:
        # Current stock is the baseline, not hundreds of new notifications.
        for offer in offers:
            row = current[str(offer['id'])]
            row.update(notified=offer, pending=False)
    else:
        pending = state.setdefault('pending', {})
        # Don't notify an unavailable/ended offer after permissions were delayed.
        for p in products.values():
            if not scan.match(p): pending.pop(source + ':' + str(p['id']), None)
        for offer in offers:
            key = source + ':' + str(offer['id'])
            previous = pending.get(key)
            if previous and previous['offer']['sale_price'] == offer['sale_price'] and previous['offer']['discount_percent'] == offer['discount_percent']:
                continue
            event = {'event_id': uuid.uuid4().hex, 'source': source,
                     'checked_at': now, 'offer': offer}
            pending[key] = event
            state.setdefault('events', []).append(event)
    entry.update(offers=current, initialized=True, checked_at=now)
    cached = {} if full else entry.get('products', {})
    cached.update(products)
    entry['products'] = cached
    entry['known_product_ids']=sorted(set(entry.get('known_product_ids',[]))|set(cached)|set(products))
    entry['last_scan_product_count']=len(products)
    entry['last_scan_scope']='full' if full else 'offers_and_campaigns'
    if full:
        entry['last_full'] = now
        entry['last_full_product_count']=len(products)

def acknowledge(state, identifiers):
    ids = set(identifiers)
    for key, event in list(state.get('pending', {}).items()):
        if event['event_id'] not in ids: continue
        row = state['sources'][event['source']]['offers'].get(str(event['offer']['id']))
        if row:
            row.update(notified=event['offer'], pending=False)
        del state['pending'][key]

def name(offer):
    names = offer.get('name', {})
    text = names.get('ar') or names.get('en') if isinstance(names, dict) else str(names)
    return ' '.join((text or 'Product').split())

def render(state, root):
    return render_history(state,root)

@contextlib.contextmanager
def transaction(root):
    with (root/'worker.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=root/'local-state.json'
        state=json.loads(path.read_text()) if path.exists() else {}
        yield state
        scan.save_json(path,state)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--mode',choices=['auto','offers','full'],default='auto')
    parser.add_argument('--source',choices=list(INTERVALS))
    parser.add_argument('--ack',action='store_true')
    args=parser.parse_args();root=args.root;root.mkdir(parents=True,exist_ok=True);os.chmod(root,0o700)
    os.environ['BREADFAST_HTTP_CACHE_DIR']=str(root/'http-cache')
    config=json.loads((root/'config.json').read_text())
    os.environ.update({k:str(v) for k,v in config.items() if k.startswith('BREADFAST_')})
    if args.ack:
        identifiers=json.load(sys.stdin)
        with transaction(root) as state:acknowledge(state,identifiers)
        return
    selected=[args.source] if args.source else list(INTERVALS)
    errors=[];skipped=[];validated={};started=time.monotonic()
    with contextlib.ExitStack() as stack:
        locks={}
        for source in selected:
            handle=stack.enter_context((root/(source+'-scan.lock')).open('w'))
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:skipped.append(source);continue
            locks[source]=handle
        with transaction(root) as state:
            now=time.time();specs={}
            for source in locks:
                entry=state.setdefault('sources',{}).setdefault(source,{})
                if now<entry.get('backoff_until',0):
                    errors.append(source+': backing off after server throttling');continue
                if args.mode=='auto' and now-entry.get('last_attempt',0)<INTERVALS[source]:continue
                full=args.mode=='full' or not entry.get('initialized') or (args.mode=='auto' and now-entry.get('last_full',0)>=FULL_INTERVAL)
                watched=sorted(set(entry.get('known_product_ids',[]))|set(entry.get('products',{}))|{str(r['offer']['id']) for r in state.get('offer_history',{}).values() if r['source']==source})
                specs[source]=(full,watched)
                entry['last_attempt']=now
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(fetch_catalogue,source,*spec):source for source,spec in specs.items()}
            for future in concurrent.futures.as_completed(futures):
                source=futures[future];full=specs[source][0]
                try:
                    products=future.result()
                    failures=getattr(products,'errors',None) or []
                    validated[source]={str(p['id']) for p in products.values() if scan.match(p)}
                    with transaction(root) as state:
                        # Merge just this source into the latest state. Other sources
                        # and notification acknowledgements may have advanced.
                        was_initialized=state['sources'][source].get('initialized',False)
                        if products or not failures:ingest(state,source,products,full and not failures,time.time())
                        entry=state['sources'][source]
                        if failures and not was_initialized:entry['initialized']=False
                        entry['coverage_errors']=failures
                        entry['last_scan_scope']='full' if full and not failures else 'all_known_products_and_discovery'
                        entry['last_known_ids_requested']=len(specs[source][1]) if not full else 0
                        entry['last_scan_seconds']=round(time.monotonic()-started,2)
                        entry['http']=statistics()
                        entry['last_missing_ids_count']=len(getattr(products,'missing_ids',set()))
                        if getattr(products,'retry_after',0):entry['backoff_until']=time.time()+products.retry_after
                        for missing in getattr(products,'missing_ids',set()):
                            key=source+':'+missing;record=state.get('offer_history',{}).get(key)
                            if record and record['status']=='active':
                                from local_history import remember
                                remember(state,source,record['offer'],time.time(),'unverified',record['origin'])
                                state.get('pending',{}).pop(key,None)
                        count=render(state,root)
                    errors.extend(source+': '+error for error in failures)
                except Exception as exc:
                    errors.append(source+': '+type(exc).__name__)
        with transaction(root) as state:
            count=render(state,root)
            (root/'history.json').write_text(json.dumps(state.get('events',[]),ensure_ascii=False,indent=2))
            pending=[e for e in state.get('pending',{}).values() if str(e['offer']['id']) in validated.get(e['source'],set())]
            report={'checked_at':datetime.datetime.now().astimezone().isoformat(),'offer_count':count,
                    'source':args.source,'errors':errors,'skipped_busy':skipped,'pending':pending,
                    'scan_seconds':round(time.monotonic()-started,2),'http':statistics(),
                    'initialized_sources':[s for s,e in state.get('sources',{}).items() if e.get('initialized')]}
            scan.save_json(root/((('status-'+args.source) if args.source else 'status')+'.json'),report)
            scan.save_json(root/'status.json',report)
        print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
