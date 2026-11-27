import unittest
from unittest.mock import patch
import catalogue_sources as sources
from scan import extract,match
from run_once import summarize
from telegram_client import prepare_batches,product_card

class CatalogueSources(unittest.TestCase):
    def test_known_offer_batch_refresh_uses_captured_indexed_ids(self):
        jobs=sources.product_batches('grocery',[11368529,11368529,44295646])
        self.assertEqual(jobs,[('products',{'ids[0]':'11368529','ids[1]':'44295646'})])
        self.assertEqual(sources.product_batches('restaurants',['restaurant:item']),[])
        self.assertEqual(sources.product_batches('mall',[1])[0][1]['warehouseId'],sources.MALL_WAREHOUSE)
    def test_live_virtual_campaigns_are_scanned_without_hardcoded_names(self):
        navigation={'data':{'categories':[{'id':1,'subcategories':[{'id':10}]}],
                            'virtualCategories':[{'type':'new_flash_campaign_123','categories':[{'id':1}]}]}}
        for full in (False,True):
            _,jobs=sources.plan('grocery',full,lambda *a,**k:navigation)
            self.assertIn(('categories/1',{'type':'new_flash_campaign_123'}),jobs)

    def test_mall_full_discovers_subcategories(self):
        def get(path,**params):
            self.assertEqual(params.get('warehouseId'),sources.MALL_WAREHOUSE)
            if path=='subcategories':
                self.assertEqual(params['screen'],'Shops')
                return {'data':{'categories':[{'id':1},{'id':2}]}}
            return {'subcategories':[{'id':10 if path.endswith('/1') else 20}]}
        count,jobs=sources.plan('mall',True,get)
        self.assertEqual(count,2)
        self.assertEqual([q['subcategoryId'] for _,q in jobs],[10,20])
        self.assertTrue(all(p=='category/products' for p,_ in jobs))
    def test_mall_offers_uses_mall_warehouse(self):
        count,jobs=sources.plan('mall',False,lambda *a,**k:{'data':{'categories':[{'id':1}]}})
        self.assertEqual(jobs,[('categories/1',{'type':'deals','warehouseId':sources.MALL_WAREHOUSE})])
    def test_restaurant_discovery_checks_all_pages(self):
        def food(path,**q):
            return {'totalPages':2,'total':2,'page':q['page'],'data':[{'id':q['page']}]}
        with patch.dict('os.environ',{'BREADFAST_FOOD_LATITUDE':'0','BREADFAST_FOOD_LONGITUDE':'0'}),patch('catalogue_sources.food_get',side_effect=food):
            self.assertEqual(len(sources.restaurant_list()),2)
    def test_incomplete_restaurant_pagination_is_error(self):
        with patch.dict('os.environ',{'BREADFAST_FOOD_LATITUDE':'0','BREADFAST_FOOD_LONGITUDE':'0'}),patch('catalogue_sources.food_get',return_value={'totalPages':1,'total':2,'data':[{'id':1}]}):
            with self.assertRaisesRegex(RuntimeError,'Incomplete'):sources.restaurant_list()
    def test_modifiers_do_not_become_menu_products(self):
        p={'id':1,'price':100,'salePrice':40,'stock':1,'optionSets':[{'minSelection':1,'options':[{'id':2,'price':20,'salePrice':5,'stock':1}]}]}
        self.assertEqual([x['id'] for x in extract({'payload':[{'products':[p]}]})],[1])
        a=sources.normalize(p,'restaurants',{'_restaurant_id':5,'_restaurant_name':'Shop A','_open':True})
        b=sources.normalize(p,'restaurants',{'_restaurant_id':6,'_restaurant_name':'Shop B','_open':True})
        self.assertNotEqual(a['id'],b['id'])
        self.assertTrue(a['base_price_only'])
        self.assertIn('required options',product_card(match(a)))
    def test_closed_restaurant_and_out_of_stock_do_not_alert(self):
        p={'id':1,'price':100,'salePrice':40,'stock':1}
        p=sources.normalize(p,'restaurants',{'_restaurant_id':5,'_restaurant_name':'Shop','_open':False})
        self.assertIsNone(match(p))
        self.assertIsNone(match(sources.normalize({'id':1,'price':100,'salePrice':40,'stock':1,'isOutOfStock':True},'mall',{})))
    def test_source_label_in_message(self):
        m=prepare_batches([{'id':1,'name':{'en':'Example'},'price':100,'sale_price':40,'discount_percent':60}], 'Now',coverage='Mall | October Mall catalogue')[0]
        self.assertIn('Mall | October Mall catalogue',m.text)
        self.assertNotIn('October FP #6',m.text)
    def test_partial_source_failure_stays_visible(self):
        r=summarize([{'catalogue':'grocery','unique_products':100,'errors':[]},{'catalogue':'mall','errors':[{'stage':'discovery','error':'Failed'}]}],None)
        self.assertEqual(r['unique_products'],100)
        self.assertEqual(r['errors'][0]['catalogue'],'mall')

if __name__=='__main__':unittest.main()
