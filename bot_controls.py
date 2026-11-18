"""Authorized private-chat scan controls, polled by the existing cloud schedule."""
import json,os
from pathlib import Path
from telegram_client import api,send
OFFERS='🏷 Offers scan'
FULL='🔎 Full scan'
KEYBOARD={'keyboard':[[{'text':OFFERS},{'text':FULL}]],'resize_keyboard':True,'is_persistent':True,'input_field_placeholder':'Choose a scan'}

def menu():
    return send('Choose a Breadfast scan below.\n\nOffers scan: check Grocery and Mall offers plus nearby restaurant menus.\nFull scan: check all Grocery and Mall subcategories plus nearby restaurant menus.\n\nRequests are picked up on the next five-minute check; GitHub queues may add a delay. Only new or improved in-stock discounts of 50% or more are sent.',reply_markup=KEYBOARD)

def command_for(update,chat):
    message=update.get('message',{})
    if message.get('chat',{}).get('type')!='private' or str(message.get('chat',{}).get('id'))!=str(chat):return None
    text=message.get('text','').strip()
    commands={OFFERS:'offers',FULL:'full','/offers':'offers','/full':'full','/start':'menu','/menu':'menu'}
    return commands.get(text.split('@')[0] if text.startswith('/') else text)

def poll(root):
    path=root/'bot-state.json'
    state=json.loads(path.read_text()) if path.exists() else {}
    updates=api('getUpdates',{'offset':state.get('next_offset',0),'timeout':0,'limit':100,'allowed_updates':['message']})
    # First installation baselines the old pairing/start messages before publishing buttons.
    if 'next_offset' not in state:
        state={'next_offset':max((u['update_id']+1 for u in updates),default=0)}
        path.write_text(json.dumps(state))
        return None
    requests=[]
    for update in updates:
        action=command_for(update,os.environ['TELEGRAM_CHAT_ID'])
        if action=='menu':menu()
        elif action:requests.append(action)
        state['next_offset']=max(state['next_offset'],update['update_id']+1)
    # Coalesce repeated taps; a full scan also covers an offers request.
    queued=requests+([state['pending_scan']] if state.get('pending_scan') else [])
    chosen='full' if 'full' in queued else 'offers' if queued else None
    if chosen:
        if requests:send(('Full catalogue' if chosen=='full' else 'Offers')+' scan started. I will send a completion summary here. Repeated pending taps are combined.',reply_markup=KEYBOARD)
        state['pending_scan']=chosen
    path.write_text(json.dumps(state))
    return chosen or state.get('pending_scan')

def complete(root,report):
    path=root/'bot-state.json'
    state=json.loads(path.read_text())
    scope='Full catalogue' if report.get('scope')=='all advertised subcategories' or state.get('pending_scan')=='full' else 'Offers'
    offers=report.get('delivered_offers',0)
    breakdown=''.join(f"{r['catalogue'].title()}: {r.get('unique_products',0):,} products; {r.get('delivered_offers',0)} new offers sent.\n" for r in report.get('catalogues',[]))
    send(f"{scope} scan complete.\n{breakdown}\nProducts checked: {report['unique_products']:,}\nCatalogue requests completed: {report['successful_endpoints']}/{report['requested_endpoints']}\nNew or improved offers sent: {offers}\nUnchanged offers were suppressed.\nCoverage: October FP #6, October Mall catalogue and restaurants near District 5.",reply_markup=KEYBOARD)
    state.pop('pending_scan',None)
    path.write_text(json.dumps(state))
