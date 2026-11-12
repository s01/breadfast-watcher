"""Telegram HTTP client. Credentials never appear in command arguments or logs."""
import json, os, subprocess

class TelegramError(RuntimeError): pass

def api(method, payload, token=None):
    token=token or os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    if not token: raise TelegramError('Telegram bot token is missing')
    if not all(c.isalnum() or c in ':_-' for c in token): raise TelegramError('Invalid Telegram token format')
    config='\n'.join(['url = '+json.dumps('https://api.telegram.org/bot'+token+'/'+method),'request = "POST"','header = "Content-Type: application/json"','data = '+json.dumps(json.dumps(payload,ensure_ascii=False))])
    result=subprocess.run(['curl','--silent','--show-error','--max-time','30','--config','-'],input=config,text=True,capture_output=True)
    if result.returncode: raise TelegramError('Telegram connection failed; delivery is unconfirmed')
    try: response=json.loads(result.stdout)
    except ValueError: raise TelegramError('Telegram returned an unreadable response') from None
    if not response.get('ok'): raise TelegramError('Telegram rejected '+method+' (error '+str(response.get('error_code','unknown'))+')')
    return response['result']

def send(text):
    chat=os.environ.get('TELEGRAM_CHAT_ID','').strip()
    if not chat: raise TelegramError('Telegram chat ID is missing')
    return api('sendMessage',{'chat_id':chat,'text':text,'link_preview_options':{'is_disabled':True}})

def format_batches(products, checked_at):
    header='Breadfast · October FP #6\nNew or improved discounts — 50% and above\n'+checked_at+'\n'
    messages=[]; chunk=header
    for p in sorted(products,key=lambda x:x['discount_percent'],reverse=True):
        name=p.get('name'); name=(name.get('en') or name.get('ar')) if isinstance(name,dict) else name
        name=' '.join(str(name or 'Product '+str(p['id'])).split())[:350]
        label=p.get('reason','new discount').replace('_',' ')
        line=f"\n{p['discount_percent']:g}% off · {name}\nEGP {p['price']:g} → {p['sale_price']:g} · {label}\nProduct ID: {p['id']}\n"
        # Conservative cap leaves room for Unicode differences in Telegram limits.
        if len(chunk)+len(line)>3000:
            messages.append(chunk); chunk=header
        chunk+=line
    if chunk!=header: messages.append(chunk)
    return messages
