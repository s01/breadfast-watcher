import unittest
from unittest.mock import patch
import scan
from telegram_client import format_batches,prepare_batches,request_config,product_card

def product(sale=50,stock=1,price=100):
    return {'id':1,'name':{'en':'Example'},'price':price,'salePrice':sale,'stock':stock}

class AlertRules(unittest.TestCase):
    def test_threshold_stock_and_zero_sentinel(self):
        self.assertIsNotNone(scan.match(product(50)))
        self.assertIsNone(scan.match(product(50.01)))
        self.assertIsNone(scan.match(product(0)))
        self.assertIsNone(scan.match(product(10,stock=0)))
    def test_first_offer_unchanged_and_improved(self):
        offers,state=scan.new_offers({'1':product()}, {})
        self.assertEqual(len(offers),1)
        state['1']['notified']=offers[0]; state['1']['pending']=False
        self.assertEqual(scan.new_offers({'1':product()},state)[0],[])
        improved,_=scan.new_offers({'1':product(40)},state)
        self.assertEqual(improved[0]['reason'],'improved_discount')
    def test_base_price_increase_is_not_a_better_deal(self):
        offers,state=scan.new_offers({'1':product()}, {})
        state['1']['notified']=offers[0]; state['1']['pending']=False
        self.assertEqual(scan.new_offers({'1':product(60,price=200)},state)[0],[])
    def test_discount_rebounds_and_failed_rebound_stays_pending(self):
        offers,state=scan.new_offers({'1':product(40)}, {})
        state['1']['notified']=offers[0]; state['1']['pending']=False
        _,state=scan.new_offers({'1':product(50)},state)
        offers,state=scan.new_offers({'1':product(45)},state)
        self.assertEqual(len(offers),1)
        self.assertEqual(len(scan.new_offers({'1':product(45)},state)[0]),1)
    def test_new_sale_episode_can_alert_again(self):
        offers,state=scan.new_offers({'1':product()}, {})
        state['1']['notified']=offers[0]; state['1']['pending']=False
        _,state=scan.new_offers({'1':product(80)},state)
        self.assertEqual(len(scan.new_offers({'1':product()},state)[0]),1)
    def test_unconfirmed_sends_remain_pending(self):
        offers,state=scan.new_offers({'1':product()}, {})
        self.assertEqual(len(scan.new_offers({'1':product()},state)[0]),1)
    def test_out_of_stock_discount_alerts_when_available(self):
        offers,state=scan.new_offers({'1':product(40,stock=0)}, {})
        self.assertEqual(offers,[])
        self.assertEqual(len(scan.new_offers({'1':product(40)},state)[0]),1)
    def test_sorting_and_message_size(self):
        matches=[]
        for i in range(100):
            m=scan.match({**product(10+i%40),'id':i,'name':{'en':'Product '+str(i)+' x'*100}})
            matches.append(m)
        messages=format_batches(matches,'12 Nov 2026 21:00 Cairo')
        self.assertTrue(all(len(m)<=3000 for m in messages))
        self.assertIn('90% OFF',messages[0])
        batches=prepare_batches(matches,'12 Nov 2026 21:00 Cairo')
        self.assertEqual(sum(len(m.product_ids) for m in batches),100)
        self.assertTrue(all(len(m.product_ids)<=4 for m in batches))

class MessageTransport(unittest.TestCase):
    def test_curl_config_preserves_unicode_and_json(self):
        import http.server,threading,subprocess,json
        received=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.end_headers();self.wfile.write(b'{}')
            def log_message(self,*args):pass
        server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.handle_request);thread.start()
        payload={'text':'Breadfast · خصم 50% → EGP 90\nArabic: كوين ملمع شفاه & "quotes"'}
        try:
            r=subprocess.run(['curl','--silent','--max-time','5','--config','-'],input=request_config('http://127.0.0.1:'+str(server.server_port),payload),capture_output=True,text=True)
            self.assertEqual(r.returncode,0)
            thread.join(6);self.assertEqual(received,[payload])
        finally:server.server_close()
    def test_names_are_preserved_and_html_is_escaped(self):
        card=product_card({'id':1,'name':{'en':'Bread & Butter <Large>','ar':'خبز وزبدة'},'price':100,'sale_price':44.5,'discount_percent':55.5})
        self.assertIn('Bread &amp; Butter &lt;Large&gt;',card)
        self.assertIn('خبز وزبدة',card)
        self.assertIn('55.5% OFF',card)
        self.assertNotIn('u2192',card)

if __name__=='__main__':unittest.main()
