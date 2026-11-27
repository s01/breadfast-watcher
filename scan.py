#!/usr/bin/env python3
"""Read Breadfast's observed catalogue endpoints without account credentials."""
import argparse, concurrent.futures, datetime, decimal, json, os, subprocess, time
from pathlib import Path
from urllib.parse import urlencode
BASE='https://www.breadfast.com/warehouses-service/warehouses/'
WAREHOUSE='68e4f9bfb2b660d5c7d97147'
SHIFT='5fc84b891758b02853efc357'
ROOT=Path(__file__).resolve().parent
STATE=Path(os.environ.get('BREADFAST_STATE_DIR',str(ROOT)))

def get(path, **params):
    query={'serve':'now','warehouseId':WAREHOUSE,'shiftId':SHIFT,**params}
    result=subprocess.run(['curl','--silent','--show-error','--fail','--max-time','30',BASE+path+'?'+urlencode(query)],capture_output=True,text=True)
    if result.returncode: raise RuntimeError(result.stderr.strip()[:200])
    data=json.loads(result.stdout)
    if isinstance(data,dict) and (data.get('error') or data.get('success') is False): raise RuntimeError(str(data)[:200])
    return data

def extract(data):
    if isinstance(data,list):
        for item in data: yield from extract(item)
    elif isinstance(data,dict):
        if 'price' in data and 'id' in data: yield data
        else:
            for item in data.values(): yield from extract(item)

def match(product, threshold=50, require_stock=True):
    try:
        price=decimal.Decimal(str(product['price'])); sale=decimal.Decimal(str(product['salePrice']))
        # A zero salePrice can indicate no active sale, so exclude it.
        if price<=0 or sale<=0 or sale>=price: return None
        discount=(price-sale)/price*100
        if discount<threshold or (require_stock and float(product.get('stock',0))<=0): return None
        offer={'id':product['id'],'name':product.get('name'),'price':float(price),'sale_price':float(sale),'discount_percent':round(float(discount),3),'stock':product.get('stock'),'image':product.get('image')}
        for key in ('merchant_name','base_price_only','_catalogue'):
            if key in product:offer[key]=product[key]
        return offer
    except (KeyError,TypeError,ValueError,decimal.InvalidOperation): return None

def new_offers(products, old, threshold=50):
    """A new sale episode or a better discount qualifies; price rises do not."""
    offers=[]; current=dict(old)
    for p in products.values():
        key=str(p['id']); qualifying=match(p,threshold,require_stock=False)
        if not qualifying:
            current.pop(key,None)
            continue
        prior=old.get(key,{})
        notified=prior.get('notified') if isinstance(prior,dict) else None
        observed=prior.get('observed',notified) if isinstance(prior,dict) else None
        pending=bool(prior.get('pending')) if isinstance(prior,dict) else False
        current[key]={'observed':qualifying,'notified':notified,'pending':pending}
        if not match(p,threshold): continue
        if notified is None:
            offers.append({**qualifying,'reason':'new_discount'})
        elif pending or any(qualifying['discount_percent']>baseline['discount_percent'] and qualifying['sale_price']<=baseline['sale_price'] for baseline in (observed,notified) if baseline):
            offers.append({**qualifying,'reason':'improved_discount'})
        if offers and offers[-1]['id']==qualifying['id']: current[key]['pending']=True
    return sorted(offers,key=lambda x:x['discount_percent'],reverse=True),current

def save_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    temporary.replace(path)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--full',action='store_true'); parser.add_argument('--auto',action='store_true'); parser.add_argument('--telegram',action='store_true'); parser.add_argument('--threshold',type=float,default=50); parser.add_argument('--catalogue',choices=('grocery','mall','restaurants'),default='grocery'); args=parser.parse_args()
    from catalogue_sources import plan,food_get,normalize,LABELS,PREFIX,MALL_WAREHOUSE
    source=args.catalogue; prefix=PREFIX[source]
    if args.auto:
        previous=STATE/(prefix+'full-scan.json')
        try:
            last=datetime.datetime.fromisoformat(json.loads(previous.read_text())['checked_at'])
            args.full=(datetime.datetime.now(datetime.timezone.utc)-last).total_seconds()>=3600
        except (OSError,KeyError,ValueError): args.full=True
    category_count,planned=plan(source,args.full,get)
    jobs=list({(p,json.dumps(q,sort_keys=True)) for p,q in planned})
    products={}; errors=[]; completed=0
    def fetch(job):
        path,query=job
        time.sleep(0.3)
        params=json.loads(query)
        data=food_get(path) if source=='restaurants' else get(path,**params)
        return path,data,params
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch,j):j[0] for j in jobs}
        for f in concurrent.futures.as_completed(futures):
            try:
                path,data,params=f.result()
                if not isinstance(data,(list,dict)): raise RuntimeError('Unexpected catalogue response')
                for p in extract(data):
                    p=normalize(p,source,params);products[str(p['id'])]=p
                completed+=1
            except Exception as e: errors.append({'path':futures[f],'error':str(e)})
    hits=sorted([m for p in products.values() if (m:=match(p,args.threshold))],key=lambda p:p['discount_percent'],reverse=True)
    report={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'warehouse':{'id':WAREHOUSE,'name':'6th of October FP #6','area':'6th of October City'},'scope':'all advertised subcategories' if args.full else 'deals in all advertised categories','category_count':category_count,'requested_endpoints':len(jobs),'successful_endpoints':completed,'unique_products':len(products),'errors':errors,'matches':hits}
    report['catalogue']=source
    report['coverage']=LABELS[source]
    if source=='mall':report['warehouse']={'id':MALL_WAREHOUSE,'name':'October Mall catalogue'}
    if source=='restaurants':
        report.pop('warehouse',None);report['scope']='all discovered nearby restaurant menus'
    report['minimum_discount_percent']=args.threshold
    state_path=STATE/('telegram-state.json' if source=='grocery' else prefix+'state.json')
    old=json.loads(state_path.read_text()) if state_path.exists() else {}
    report['new_matches'],current=new_offers(products,old,args.threshold)
    # Never acknowledge offers before delivery or after a partial scan.
    if args.telegram and not errors:
        from telegram_client import send,prepare_batches,TelegramError
        from zoneinfo import ZoneInfo
        checked=datetime.datetime.fromisoformat(report['checked_at']).astimezone(ZoneInfo('Africa/Cairo')).strftime('%d %b %Y %H:%M Cairo')
        batches=prepare_batches(report['new_matches'],checked,coverage=LABELS[source])
        report['delivery_batches']=[]
        try:
            for batch in batches:
                receipt=send(batch.text,html_format=True)
                report['delivery_batches'].append({'product_ids':batch.product_ids,'offer_count':len(batch.product_ids),'returned_text_characters':len(receipt['text']),'content_verified':True})
                # Acknowledge explicit IDs; formatting no longer determines delivery state.
                for product_id in batch.product_ids:
                    offer=next(p for p in report['new_matches'] if p['id']==product_id)
                    current[str(product_id)]['notified']=offer
                    current[str(product_id)]['pending']=False
                save_json(state_path,current)
                time.sleep(1)
            save_json(state_path,current)
            report['delivered_messages']=len(batches)
            report['delivered_offers']=sum(len(batch.product_ids) for batch in batches)
        except Exception as exc:
            detail=str(exc) if isinstance(exc,TelegramError) else 'Unexpected notification error'
            report['errors'].append({'stage':'telegram','error':detail+'; unconfirmed offers remain pending'})
    save_json(ROOT/(prefix+'latest-scan.json'),report)
    if not errors:
        save_json(STATE/(prefix+('full-scan.json' if args.full else 'deals-scan.json')),{k:v for k,v in report.items() if k not in ('matches','new_matches')})
    save_json(ROOT/(prefix+'products.json'),list(products.values()))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['errors']: raise SystemExit(2)
if __name__=='__main__': main()
