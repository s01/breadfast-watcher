"""Discover product IDs advertised in observed home/section collections."""
import concurrent.futures, re
from urllib.parse import urlencode
from catalogue_http import read_json
from catalogue_sources import MALL_WAREHOUSE

def advertised_ids(data):
    products=set();collections=set()
    def numeric(value):
        if isinstance(value,(str,int)) and str(value).isdigit():products.add(str(value))
    def walk(value, product_list=False):
        if isinstance(value,dict):
            if 'price' in value or 'salePrice' in value or product_list:
                numeric(value.get('id'));numeric(value.get('productId'))
            collection=value.get('collectionId')
            if isinstance(collection,str) and re.fullmatch('[a-fA-F0-9]{24}',collection):collections.add(collection)
            if ('title' in value or 'imageCollection' in value) and value.get('isExternal') is not True:
                identifier=value.get('_id')
                if isinstance(identifier,str) and re.fullmatch('[a-fA-F0-9]{24}',identifier):collections.add(identifier)
            for key,child in value.items():walk(child,key in ('products','productIds'))
        elif isinstance(value,list):
            for child in value:walk(child,product_list)
        elif product_list:numeric(value)
    walk(data)
    return products,collections

def discover(source):
    if source=='restaurants':return set(),[]
    warehouse=MALL_WAREHOUSE if source=='mall' else '68e4f9bfb2b660d5c7d97147'
    screen='Shops' if source=='mall' else 'Supermarket'
    params={'serve':'now','warehouseId':warehouse}
    urls=['https://www.breadfast.com/dynamic-product-carousel/'+screen+'?'+urlencode(params)]
    # Home/Supermarket are the exact targets observed in the iPhone capture.
    if source=='grocery':
        urls += ['https://ad-management-service.breadfast.com/collections/spotlight?'+urlencode({'area':'36009',**params,'targetPage':page}) for page in ('Home','Supermarket')]
    products=set();collections=set();errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(read_json,url):url for url in urls}
        for future in concurrent.futures.as_completed(futures):
            try:
                ids,groups=advertised_ids(future.result());products.update(ids);collections.update(groups)
            except Exception:errors.append('Promotion discovery unavailable')
        jobs={pool.submit(read_json,'https://ad-management-service.breadfast.com/collections/'+identifier+'?'+urlencode({'area':'6th of October City',**params})):identifier for identifier in collections}
        for future in concurrent.futures.as_completed(jobs):
            try:products.update(advertised_ids(future.result())[0])
            except Exception:errors.append('An advertised collection was unavailable')
    return products,sorted(set(errors))
