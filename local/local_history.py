"""Persistent offer ledger, independent of notification acknowledgements."""
import datetime, html, json, time
import scan
from catalogue_sources import LABELS

STATUS={'active':'متاح', 'sold_out':'نفد المخزون', 'discount_ended':'انتهى الخصم أو أصبح أقل من 50%', 'unverified':'بانتظار إعادة التأكد'}

def remember(state, source, offer, now, status, origin):
    ledger=state.setdefault('offer_history', {})
    key=source+':'+str(offer['id'])
    record=ledger.setdefault(key, {'source':source,'first_seen':now,'changes':[],'origin':origin})
    previous=record.get('offer', {})
    changed=record.get('status')!=status or any(previous.get(k)!=offer.get(k) for k in ('price','sale_price','discount_percent'))
    if changed:
        record['changes'].append({'checked_at':now,'offer':offer,'status':status})
        record['last_changed']=now
    record.update(offer=offer, status=status, last_checked=now)
    if status=='active':record['last_available']=now
    return record

def seed_history(state, source, offers, checked_at, origin='recovered_snapshot'):
    """Import known old evidence without fabricating new alerts or availability."""
    for offer in offers:
        key=source+':'+str(offer['id'])
        if key not in state.get('offer_history',{}):
            past_status='active' if float(offer.get('stock') or 0)>0 else 'sold_out'
            record=remember(state,source,offer,checked_at,past_status,origin)
            record['status']='unverified'

def update_history(state, source, products, full, now, baseline=False):
    ledger=state.setdefault('offer_history', {})
    for p in products.values():
        key=source+':'+str(p['id'])
        qualifying=scan.match(p,require_stock=False)
        active=scan.match(p)
        record=ledger.get(key)
        if qualifying:
            remember(state,source,qualifying,now,'active' if active else 'sold_out','baseline' if baseline else 'observed')
        elif record:
            remember(state,source,record['offer'],now,'discount_ended',record['origin'])
    if full:
        for key, record in ledger.items():
            if record['source']==source and str(record['offer']['id']) not in products:
                # Absence is not evidence that the price reverted or stock is zero.
                if record['status'] in ('active','unverified'):
                    remember(state,source,record['offer'],now,'unverified',record['origin'])

def timestamp(value):
    return datetime.datetime.fromtimestamp(value).astimezone().strftime('%d/%m %H:%M:%S') if value else '—'

def title(offer):
    names=offer.get('name',{})
    return (names.get('ar') or names.get('en') or str(offer['id'])) if isinstance(names,dict) else str(names)

def render_history(state, root):
    ledger=state.get('offer_history',{})
    ordered=sorted(ledger.values(),key=lambda r:(-r['offer']['discount_percent'],title(r['offer'])))
    active=[r for r in ordered if r['status']=='active']
    uncertain=[r for r in ordered if r['status']=='unverified']
    latest={e['source']+':'+str(e['offer']['id']):e for e in state.get('events',[]) if e['checked_at']>=time.time()-86400}
    new=[r for key,r in ledger.items() if key in latest and r['status']=='active']
    new.sort(key=lambda r:-r['offer']['discount_percent'])
    def table(records, historical=False, empty='لا توجد عروض متاحة بخصم 50% وأكتر وقت آخر فحص.'):
        if not records:return '<p class="empty">'+empty+'</p>'
        rows=[]
        for r in records:
            p=r['offer'];key=r['source']+':'+str(p['id'])
            badge='<span class="new">جديد / محسّن</span>' if key in latest and r['status']=='active' else ''
            english=p.get('name',{}).get('en','') if isinstance(p.get('name'),dict) else ''
            cells=[html.escape(title(p))+' '+badge+'<small dir="ltr">'+html.escape(english)+'</small>',html.escape(p.get('merchant_name') or LABELS[r['source']]),f'{p["discount_percent"]:g}%',f'{p["price"]:g}',f'{p["sale_price"]:g}',STATUS[r['status']],timestamp(r.get('last_checked'))]
            if historical:
                changes=''.join('<li>'+timestamp(c['checked_at'])+f' · {c["offer"]["discount_percent"]:g}% · {c["offer"]["sale_price"]:g} جنيه · '+STATUS[c['status']]+'</li>' for c in r.get('changes',[]))
                cells.append('<details><summary>من '+timestamp(r['first_seen'])+'</summary><ul>'+changes+'</ul></details>')
            rows.append('<tr>'+''.join('<td>'+v+'</td>' for v in cells)+'</tr>')
        headers=['المنتج','القسم','الخصم','قبل العرض','سعر العرض','الحالة','آخر تحقق']+(['سجل التغييرات'] if historical else [])
        return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+v+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    times=' · '.join(html.escape(LABELS[s])+': '+timestamp(e.get('checked_at')) for s,e in state.get('sources',{}).items())
    coverage=[]
    for source,entry in state.get('sources',{}).items():
        scope='فحص كامل' if entry.get('last_scan_scope')=='full' else 'كل المنتجات المعروفة والحملات' if entry.get('last_scan_scope')=='all_known_products_and_discovery' else 'عروض وحملات'
        if source=='restaurants':scope='قوائم المطاعم'
        http=entry.get('http',{})
        detail=f'؛ تحقق بدون تنزيل: {http.get("not_modified",0)} طلب؛ تنزيل مضغوط: {http.get("download_bytes",0)/1024:.0f} كيلوبايت' if http else ''
        warning='؛ تغطية ناقصة: '+html.escape(', '.join(entry['coverage_errors'])) if entry.get('coverage_errors') else ''
        coverage.append('<li>'+html.escape(LABELS[source])+f' — آخر فحص: {scope}، {entry.get("last_scan_product_count","—")} منتج؛ إجمالي المنتجات المعروفة: {len(entry.get("known_product_ids",entry.get("products",{})))}؛ آخر اكتشاف كامل: '+timestamp(entry.get('last_full'))+detail+warning+'</li>')
    page='''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="30"><title>عروض بريدفاست — أكتوبر</title>
<style>body{font:16px system-ui;margin:24px;background:Canvas;color:CanvasText;color-scheme:light dark}h2{margin-top:40px}table{width:100%;border-collapse:collapse}td,th{text-align:right;padding:12px;border-bottom:1px solid GrayText;vertical-align:top}td:first-child{min-width:220px}small{display:block;margin-top:6px;opacity:.75}.scroll{overflow:auto}.new{font-weight:bold}.empty{opacity:.8}nav{display:flex;gap:18px;flex-wrap:wrap}a{color:LinkText}</style>
<h1>عروض بريدفاست — أكتوبر</h1><p>كل العروض المتاحة بخصم 50% وأكتر، مرتبة حسب الخصم. الأسعار بالجنيه. الجديد يتضاف هنا، والمنتهي يظل في السجل.</p>
<nav><a href="#active">المتاح الآن</a><a href="#new">الجديد والمحسّن</a><a href="#history">السجل الكامل</a></nav>
'''
    page+='<small>'+times+'</small><details><summary>تغطية الفحص وعدد المنتجات</summary><ul>'+''.join(coverage)+'</ul></details><h2 id="active">العروض المتاحة الآن ('+str(len(active))+')</h2>'+table(active)
    page+='<h2 id="new">جديد / محسّن خلال آخر 24 ساعة ('+str(len(new))+')</h2>'+table(new,empty='لم يُرصد عرض جديد أو خصم محسّن خلال آخر 24 ساعة. العروض الموجودة عند بدء التشغيل محفوظة في السجل.')
    if uncertain:
        page+='<h2>عروض سابقة بانتظار إعادة التأكد ('+str(len(uncertain))+')</h2><p>لم تعد في آخر كتالوج كامل. نحتفظ بها ولا نعتبرها متاحة أو منتهية بدون دليل.</p>'+table(uncertain)
    page+='<h2 id="history">السجل الكامل ('+str(len(ordered))+')</h2><p>يشمل العروض القديمة والجديدة، المتاحة والمنتهية. سعر العرض هنا تاريخي عندما تكون الحالة منتهية أو غير مؤكدة.</p>'+table(sorted(ordered,key=lambda r:-r.get('first_seen',0)),True)
    page+='</html>'
    (root/'offers.html').write_text(page)
    (root/'offer-history.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
    return len(active)
