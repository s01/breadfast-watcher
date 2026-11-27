import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_worker as local

def product(sale=50, stock=1):
    return {'id': 1, 'price': 100, 'salePrice': sale, 'stock': stock, 'name': {'en':'Example'}}

class LocalMonitorTests(unittest.TestCase):
    def test_failed_refresh_does_not_deliver_a_stale_pending_offer(self):
        import json, tempfile, argparse, io, contextlib
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state={}
            local.ingest(state,'grocery',{},True,1)
            local.ingest(state,'grocery',{'1':product(1)},False,2)
            local.scan.save_json(root/'local-state.json',state)
            (root/'config.json').write_text('{}')
            failed=local.ScanResult();failed.errors=['products: TimeoutError'];failed.missing_ids=set()
            args=argparse.Namespace(root=root,source='grocery',mode='offers',ack=False)
            output=io.StringIO()
            with patch('argparse.ArgumentParser.parse_args',return_value=args),patch('local_worker.fetch_catalogue',return_value=failed),contextlib.redirect_stdout(output):
                local.main()
            self.assertEqual(json.loads(output.getvalue())['pending'],[])
            self.assertIn('grocery:1',json.loads((root/'local-state.json').read_text())['pending'])

    def test_new_discount_on_previously_full_price_product_is_checked_without_a_campaign(self):
        import json, tempfile, argparse, io, contextlib
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state={}
            local.ingest(state,'grocery',{'1':product(100)},True,1)
            local.scan.save_json(root/'local-state.json',state)
            (root/'config.json').write_text('{}')
            def fetch(source,full,watched):
                self.assertEqual(source,'grocery')
                self.assertFalse(full)
                self.assertIn('1',watched)
                return {'1':product(1)}
            args=argparse.Namespace(root=root,source='grocery',mode='offers',ack=False)
            with patch('argparse.ArgumentParser.parse_args',return_value=args),patch('local_worker.fetch_catalogue',side_effect=fetch),contextlib.redirect_stdout(io.StringIO()):
                local.main()
            saved=json.loads((root/'local-state.json').read_text())
            self.assertEqual(saved['pending']['grocery:1']['offer']['sale_price'],1)
            self.assertEqual(saved['offer_history']['grocery:1']['status'],'active')

    def test_baseline_offers_remain_in_history_after_discount_ends(self):
        import tempfile
        state={}
        local.ingest(state,'grocery',{'1':product()},True,1)
        local.ingest(state,'grocery',{'1':product(100)},True,2)
        with tempfile.TemporaryDirectory() as directory:
            local.render(state,Path(directory))
            self.assertIn('Example',(Path(directory)/'offers.html').read_text())

    def test_old_active_and_new_offer_coexist_and_keep_history(self):
        state={};local.ingest(state,'grocery',{'1':product()},True,1)
        second={**product(40),'id':2,'name':{'en':'New item'}}
        local.ingest(state,'grocery',{'2':second},False,2)
        self.assertEqual(set(state['offer_history']),{'grocery:1','grocery:2'})
        self.assertTrue(all(r['status']=='active' for r in state['offer_history'].values()))
        self.assertEqual(len(state['events']),1)
        self.assertEqual(state['sources']['grocery']['last_scan_product_count'],1)
        self.assertEqual(state['sources']['grocery']['last_full_product_count'],1)
        self.assertEqual(len(state['sources']['grocery']['products']),2)
        local.ingest(state,'grocery',{'1':product(50,0),'2':second},True,3)
        self.assertEqual(state['offer_history']['grocery:1']['status'],'sold_out')
        self.assertEqual(state['offer_history']['grocery:2']['status'],'active')

    def test_missing_from_full_scan_is_unconfirmed_not_deleted_or_ended(self):
        state={};local.ingest(state,'grocery',{'1':product()},True,1)
        local.ingest(state,'grocery',{},True,2)
        self.assertEqual(state['offer_history']['grocery:1']['status'],'unverified')

    def test_distinct_price_changes_are_kept_without_poll_duplicates(self):
        state={};local.ingest(state,'grocery',{'1':product()},True,1)
        local.ingest(state,'grocery',{'1':product(40)},False,2)
        local.ingest(state,'grocery',{'1':product(40)},False,3)
        self.assertEqual([c['offer']['sale_price'] for c in state['offer_history']['grocery:1']['changes']],[50,40])

    def test_recovery_does_not_fabricate_new_alerts_or_current_availability(self):
        from local_history import seed_history
        state={};seed_history(state,'grocery',[local.scan.match(product())],1)
        record=state['offer_history']['grocery:1']
        self.assertEqual(record['status'],'unverified')
        self.assertEqual(record['changes'][0]['status'],'active')
        self.assertFalse(state.get('events'))
        self.assertFalse(state.get('pending'))

    def test_baseline_is_quiet_then_improved_one_pound_alerts(self):
        state={}
        local.ingest(state,'grocery',{'1':product()},True,1)
        self.assertFalse(state.get('pending'))
        local.ingest(state,'grocery',{'1':product(1)},False,2)
        event=next(iter(state['pending'].values()))
        self.assertEqual(event['offer']['discount_percent'],99)
        local.ingest(state,'grocery',{'1':product(1)},False,3)
        self.assertEqual(len(state['events']),1)
        local.acknowledge(state,[event['event_id']])
        local.ingest(state,'grocery',{'1':product(1)},False,4)
        self.assertFalse(state['pending'])
        self.assertEqual(len(state['events']),1)

    def test_pending_survives_restart_and_unknown_ack_does_nothing(self):
        import json
        state={};local.ingest(state,'mall',{},True,1)
        local.ingest(state,'mall',{'1':product(1)},False,2)
        restored=json.loads(json.dumps(state))
        local.acknowledge(restored,['unrelated'])
        self.assertEqual(len(restored['pending']),1)

    def test_ended_offer_is_removed_from_delivery_queue(self):
        state={};local.ingest(state,'grocery',{},True,1)
        local.ingest(state,'grocery',{'1':product(1)},False,2)
        local.ingest(state,'grocery',{'1':product(1,0)},False,3)
        self.assertFalse(state['pending'])

    def test_source_histories_are_independent(self):
        state={}
        for source in ('grocery','mall'):local.ingest(state,source,{},True,1)
        for source in ('grocery','mall'):local.ingest(state,source,{'1':product(1)},False,2)
        self.assertEqual(len(state['pending']),2)

if __name__=='__main__':unittest.main()
