"""Observed catalogue contracts for Grocery, Mall, and nearby restaurant menus."""
import json,os,subprocess
from urllib.parse import urlencode
MALL_WAREHOUSE='6aa6ec75e4d228c43c14ce1d'
SOURCES=('grocery','mall','restaurants')
LABELS={'grocery':'Grocery | October FP #6','mall':'Mall | October Mall catalogue','restaurants':'Restaurants | near District 5, October'}
PREFIX={'grocery':'','mall':'mall-','restaurants':'restaurants-'}

def product_batches(source, identifiers):
    """Observed app batch endpoint, for refreshing previously seen offers."""
    if source=='restaurants':return []
    ids=sorted({str(i) for i in identifiers if str(i).isdigit()})
    jobs=[]
    for start in range(0,len(ids),100):
        query={f'ids[{i}]':value for i,value in enumerate(ids[start:start+100])}
        if source=='mall':query['warehouseId']=MALL_WAREHOUSE
        jobs.append(('products',query))
    return jobs

def food_get(path,**query):
    from catalogue_http import read_json
    url='https://food-aggregator.breadfast.com/api/v1/'+path
    if query:url+='?'+urlencode(query)
    d=read_json(url)
    if d.get('status')!='success' or d.get('errors'):raise RuntimeError('Restaurant catalogue rejected: '+path)
    return d['payload']

def restaurant_list():
    # Area-level coordinates are private deployment configuration, not a home address.
    geo={'latitude':os.environ['BREADFAST_FOOD_LATITUDE'],'longitude':os.environ['BREADFAST_FOOD_LONGITUDE']}
    first=food_get('restaurants',page=1,pageSize=10,**geo)
    total_pages=first['totalPages']
    if not isinstance(total_pages,int) or total_pages>100:raise RuntimeError('Unexpected restaurant pagination')
    rows=list(first['data'])
    for page in range(2,total_pages+1):
        d=food_get('restaurants',page=page,pageSize=10,**geo)
        if d['page']!=page or d['total']!=first['total']:raise RuntimeError('Restaurant listing changed during pagination; retry needed')
        rows.extend(d['data'])
    unique={str(r['id']):r for r in rows}
    if len(unique)!=first['total']:raise RuntimeError('Incomplete restaurant discovery')
    return list(unique.values())

def plan(source,full,get):
    if source=='restaurants':
        restaurants=restaurant_list()
        return len(restaurants),[(f"restaurants/{r['id']}/catalog",{'_restaurant_id':r['id'],'_restaurant_name':r['name'],'_open':r['operatingStatus']=='OPEN'}) for r in restaurants]
    params={'screen':'Shops','warehouseId':MALL_WAREHOUSE} if source=='mall' else {}
    navigation=get('subcategories',**params)['data']
    categories=navigation['categories']
    jobs=[]
    for c in categories:
        if full and source=='mall':
            meta=get('category/'+str(c['id']),warehouseId=MALL_WAREHOUSE)
            if not isinstance(meta.get('subcategories'),list):raise RuntimeError('Missing Mall subcategory metadata')
            jobs.extend(('category/products',{'subcategoryId':s['id'],'warehouseId':MALL_WAREHOUSE}) for s in meta['subcategories'])
        elif full:
            jobs.extend(('subcategories/'+str(s['id']),{}) for s in c.get('subcategories',[]))
        else:
            query={'type':'deals'}
            if source=='mall':query['warehouseId']=MALL_WAREHOUSE
            jobs.append(('categories/'+str(c['id']),query))
    # The app's current campaign tabs use dynamic types (Black Friday, flash
    # sales, etc.), not just `deals`. Rediscover them on every check so a new
    # campaign is covered without changing code or waiting for a full scan.
    for campaign in navigation.get('virtualCategories',[]):
        kind=campaign.get('type')
        if not isinstance(kind,str) or not kind:continue
        for category in campaign.get('categories',[]):
            query={'type':kind}
            if source=='mall':query['warehouseId']=MALL_WAREHOUSE
            job=('categories/'+str(category['id']),query)
            if job not in jobs:jobs.append(job)
    return len(categories),jobs

def normalize(product,source,query):
    p=dict(product)
    if source!='grocery':p['_catalogue']=source
    if source=='restaurants':
        p['original_id']=p['id'];p['id']=str(query['_restaurant_id'])+':'+str(p['id'])
        p['merchant_name']=query['_restaurant_name']
        if not query['_open']:p['stock']=0
        p['base_price_only']=bool(p.get('requiresCustomization')) or any(s.get('minSelection',0)>0 for s in p.get('optionSets',[]))
    if p.get('isOutOfStock') is True:p['stock']=0
    return p
