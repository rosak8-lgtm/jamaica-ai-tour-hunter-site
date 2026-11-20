import json
import os
import tempfile
import unittest
from pathlib import Path
from backend.sqlite_order_repository import SqliteOrders
from backend.order_engine import BadOrder

class Tests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path=Path(self.dir.name)/"private"/"orders.sqlite"
        self.preview=Path(self.dir.name)/"tour-previews.json"
        self.preview.write_text(json.dumps({"schema":"jamaica.tour-previews.v1",
            "bookable":False,"previews":[{"id":"p_"+"a"*24,
            "hotel":"CI Hotel","bookable":False}]}),encoding="utf-8")
        self.repo=SqliteOrders(self.path,preview_path=self.preview)
    def test_private_permissions(self):
        self.assertEqual(self.path.stat().st_mode&0o077,0)
    def test_atomic_transition_and_replay_after_restart(self):
        self.repo.create_order({"id":"order-123","status":"CONTRACT_CREATING",
                                "signed_total_rub":85000})
        self.assertTrue(self.repo.transition("order-123","CONTRACT_CREATING",
                                             "AWAITING_SIGNATURE",{"contract_id":"contract-123"}))
        self.assertFalse(self.repo.transition("order-123","CONTRACT_CREATING",
                                              "PAYMENT_PENDING",{"payment_id":"bad"}))
        fresh=SqliteOrders(self.path,preview_path=self.preview)
        order=fresh.get_order("order-123")
        self.assertEqual(order["status"],"AWAITING_SIGNATURE")
        self.assertEqual(order["contract_id"],"contract-123")
        self.assertNotIn("payment_id",order)
    def test_separate_private_quote_not_written_to_public_feed(self):
        self.repo.save_verified_offer({"id":"tour-private-123",
            "total_rub":95000,"quote_verified":True})
        self.assertEqual(self.repo.get_offer("tour-private-123")["total_rub"],95000)
        self.assertNotIn("95000",self.preview.read_text())
    def test_customer_can_read_only_own_private_quote_and_contract(self):
        self.repo.save_verified_offer({"id":"tour-user1","buyer_id":"customer-11111111",
                                       "total_rub":95000})
        self.assertIsNotNone(self.repo.get_offer_for_buyer("tour-user1","customer-11111111"))
        self.assertIsNone(self.repo.get_offer_for_buyer("tour-user1","customer-22222222"))
        self.assertIsNone(self.repo.get_offer_for_buyer("tour-user1",""))
        self.repo.create_order({"id":"order-123456","status":"AWAITING_SIGNATURE",
                                "buyer_id":"customer-11111111","contract_digest":"PRIVATE"})
        self.assertIsNotNone(self.repo.get_order_for_buyer("order-123456","customer-11111111"))
        self.assertIsNone(self.repo.get_order_for_buyer("order-123456","customer-22222222"))
    def test_preview_lookup_from_public_file(self):
        p=self.repo.get_preview("p_"+"a"*24)
        self.assertEqual(p["hotel"],"CI Hotel")
        self.assertIsNone(self.repo.get_preview("p_"+"b"*24))
    def test_notification_outbox_is_durable_and_deduplicates(self):
        event={"type":"TOUR_BOOKED","order_id":"order-123"}
        self.repo.enqueue_once("order-123:booked",event)
        self.repo.enqueue_once("order-123:booked",event)
        fresh=SqliteOrders(self.path,preview_path=self.preview)
        self.assertEqual(len(fresh.pending_events()),1)
        fresh.mark_delivered("order-123:booked")
        self.assertEqual(self.repo.pending_events(),[])
    def test_reject_invalid_transition(self):
        self.repo.create_order({"id":"order-123","status":"AWAITING_SIGNATURE"})
        with self.assertRaises(BadOrder):
            self.repo.transition("order-123","AWAITING_SIGNATURE","PAYMENT_PENDING",{"status":"BOOKED"})
    def test_missing_order_is_false(self):
        self.assertFalse(self.repo.transition("missing","NEW","PAID",{}))
        self.assertIsNone(self.repo.get_order("missing"))
if __name__=="__main__":unittest.main()
