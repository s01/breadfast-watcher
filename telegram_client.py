"""Telegram HTTP client. Credentials never appear in command arguments or logs."""
import html, json, os, subprocess
from decimal import Decimal
from dataclasses import dataclass
from urllib.parse import urlparse
from html.parser import HTMLParser

class TelegramError(RuntimeError): pass

def api(method, payload, token=None):
    token=token or os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    if not token: raise TelegramError('Telegram bot token is missing')
    if not all(c.isalnum() or c in ':_-' for c in token): raise TelegramError('Invalid Telegram token format')
    config=request_config('https://api.telegram.org/bot'+token+'/'+method,payload)
    result=subprocess.run(['curl','--silent','--show-error','--max-time','30','--config','-'],input=config,text=True,capture_output=True)
    if result.returncode: raise TelegramError('Telegram connection failed; delivery is unconfirmed')
    try: response=json.loads(result.stdout)
    except ValueError: raise TelegramError('Telegram returned an unreadable response') from None
    if not response.get('ok'): raise TelegramError('Telegram rejected '+method+' (error '+str(response.get('error_code','unknown'))+')')
    return response['result']

def request_config(url,payload):
    # Encode JSON Unicode escapes *inside* the body; curl must preserve their backslashes.
    body=json.dumps(payload,ensure_ascii=True)
    return '\n'.join(['url = '+json.dumps(url),'request = "POST"','header = "Content-Type: application/json"','data = '+json.dumps(body)])

def send(text, html_format=False):
    chat=os.environ.get('TELEGRAM_CHAT_ID','').strip()
    if not chat: raise TelegramError('Telegram chat ID is missing')
    payload={'chat_id':chat,'text':text,'link_preview_options':{'is_disabled':True}}
    if html_format: payload['parse_mode']='HTML'
    result=api('sendMessage',payload)
    expected=visible_text(text) if html_format else text
    if result.get('text','').strip()!=expected.strip():
        raise TelegramError('Telegram returned different message text; delivery completeness is unconfirmed')
    return result

def visible_text(markup):
    class Parser(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
        def handle_data(self,data):self.parts.append(data)
    parser=Parser();parser.feed(markup);parser.close()
    return ''.join(parser.parts)

@dataclass
class MessageBatch:
    text: str
    product_ids: list

def money(value):
    amount=Decimal(str(value))
    return format(amount,',.0f') if amount==amount.to_integral_value() else format(amount,',.2f')

def clean_name(value):
    return ' '.join(html.unescape(str(value or '')).split())[:350]

def product_url(product):
    # Populated only after a real Breadfast share link has been verified.
    return None

def product_card(p):
    names=p.get('name')
    if isinstance(names,dict):
        english=clean_name(names.get('en')); arabic=clean_name(names.get('ar'))
    else: english=clean_name(names); arabic=''
    title=english or arabic or 'Product '+str(p['id'])
    discount=f"{p['discount_percent']:.1f}".rstrip('0').rstrip('.')
    card=f"<b>{discount}% OFF</b>\n<b>{html.escape(title)}</b>\n"
    if arabic and arabic!=title: card+=html.escape(arabic)+'\n'
    saved=Decimal(str(p['price']))-Decimal(str(p['sale_price']))
    card+=f"Was: <s>EGP {money(p['price'])}</s>\nNow: <b>EGP {money(p['sale_price'])}</b>\nSave: EGP {money(saved)}\n"
    url=product_url(p)
    if url: card+=f'<a href="{html.escape(url,quote=True)}">Open product in Breadfast</a>\n'
    else: card+='<a href="https://app.breadfast.com/Breadfast">Open Breadfast (search by name)</a>'
    image=p.get('image','')
    if isinstance(image,str) and urlparse(image).scheme=='https' and urlparse(image).hostname=='cdn.breadfast.com':
        card+=f' | <a href="{html.escape(image,quote=True)}">Product photo</a>'
    card+='\n'
    return card

def prepare_batches(products,checked_at):
    header='<b>Breadfast offers</b>\n'+str(len(products))+' new or improved offers | 50% off and above\nOctober FP #6 | '+html.escape(checked_at)+'\n\n'
    messages=[]; cards=[]; ids=[]
    ordered=sorted(products,key=lambda x:(-x['discount_percent'],str(x['id'])))
    for p in ordered:
        card=product_card(p)
        if cards and (len(cards)>=4 or len(header)+len('\n'.join(cards))+len(card)>2900):
            messages.append(MessageBatch(header+'\n'.join(cards),ids)); cards=[];ids=[]
        cards.append(card);ids.append(p['id'])
    if cards: messages.append(MessageBatch(header+'\n'.join(cards),ids))
    if len(messages)>1:
        for i,m in enumerate(messages,1): m.text=m.text.replace('<b>Breadfast offers</b>',f'<b>Breadfast offers ({i}/{len(messages)})</b>',1)
    return messages

def format_batches(products,checked_at):
    return [m.text for m in prepare_batches(products,checked_at)]
