import unittest
from promotion_sources import advertised_ids

class PromotionTests(unittest.TestCase):
    def test_collects_product_ids_and_internal_collections_without_confusing_categories(self):
        data=[{'_id':'a'*24,'title':'Collection','products':[11368529,{'id':44295646}]},
              {'id':436,'name':'Category'}, {'id':999,'price':100},
              {'_id':'b'*24,'title':'External','isExternal':True}]
        products,collections=advertised_ids(data)
        self.assertEqual(products,{'11368529','44295646','999'})
        self.assertEqual(collections,{'a'*24})

if __name__=='__main__':unittest.main()
