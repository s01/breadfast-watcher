import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bot_controls as bot

class BotControls(unittest.TestCase):
    def update(self,text,chat=123,kind='private',uid=1):
        return {'update_id':uid,'message':{'chat':{'id':chat,'type':kind},'text':text}}
    def test_private_owner_only(self):
        self.assertEqual(bot.command_for(self.update(bot.FULL),123),'full')
        self.assertIsNone(bot.command_for(self.update(bot.FULL,456),123))
        self.assertIsNone(bot.command_for(self.update(bot.FULL,kind='group'),123))
        self.assertEqual(bot.command_for(self.update('/offers@saiffastbot'),123),'offers')
    def test_baseline_skips_old_commands(self):
        with tempfile.TemporaryDirectory() as d,patch('bot_controls.api',return_value=[self.update('/full',uid=10)]),patch('bot_controls.send') as send:
            root=Path(d);self.assertIsNone(bot.poll(root));send.assert_not_called()
            self.assertEqual(json.loads((root/'bot-state.json').read_text())['next_offset'],11)
    def test_buttons_coalesce_and_survive_retry(self):
        with tempfile.TemporaryDirectory() as d,patch.dict('os.environ',{'TELEGRAM_CHAT_ID':'123'}),patch('bot_controls.send'):
            root=Path(d);(root/'bot-state.json').write_text(json.dumps({'next_offset':1}))
            with patch('bot_controls.api',return_value=[self.update(bot.OFFERS),self.update(bot.FULL,uid=2),self.update(bot.FULL,uid=3)]):
                self.assertEqual(bot.poll(root),'full')
            with patch('bot_controls.api',return_value=[]):self.assertEqual(bot.poll(root),'full')
            bot.complete(root,{'unique_products':7000,'successful_endpoints':233,'requested_endpoints':233,'delivered_offers':0})
            self.assertNotIn('pending_scan',json.loads((root/'bot-state.json').read_text()))
    def test_other_chat_cannot_trigger(self):
        with tempfile.TemporaryDirectory() as d,patch.dict('os.environ',{'TELEGRAM_CHAT_ID':'123'}),patch('bot_controls.send') as send,patch('bot_controls.api',return_value=[self.update(bot.FULL,456)]):
            root=Path(d);(root/'bot-state.json').write_text('{"next_offset":1}')
            self.assertIsNone(bot.poll(root));send.assert_not_called()

if __name__=='__main__':unittest.main()
