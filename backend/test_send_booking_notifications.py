import tempfile
import unittest
from pathlib import Path
from backend.sqlite_order_repository import SqliteOrders
from backend.send_booking_notifications import format_event, deliver

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo=SqliteOrders(Path(self.tmp.name)/"orders.sqlite")
    def test_booked_notification_only_for_authoritative_event(self):
        message=format_event({"type":"TOUR_BOOKED","order_id":"order-12345",
                              "supplier_booking_id":"booking-12345"})
        self.assertIn("забронирован",message)
        self.assertIn("booking-12345",message)
    def test_on_request_not_called_confirmed_booking(self):
        message=format_event({"type":"TOUR_REQUESTED_WAITING_HOTEL",
                              "order_id":"order-12345"})
        self.assertIn("под запрос",message)
        self.assertNotIn("забронирован",message)
    def test_reject_unknown_or_malformed_event(self):
        for event in ({"type":"UNKNOWN","order_id":"order-12345"},
                      {"type":"TOUR_BOOKED","order_id":"\nTOKEN\n"}):
            with self.assertRaises(ValueError):
                format_event(event)
    def test_failed_delivery_keeps_event_for_retry(self):
        self.repo.enqueue_once("order-12345:BOOKED",
                               {"type":"TOUR_BOOKED","order_id":"order-12345"})
        def broken(message):
            raise OSError("connection lost")
        self.assertEqual(deliver(self.repo,broken),0)
        self.assertEqual(len(self.repo.pending_events()),1)
        sent=[]
        self.assertEqual(deliver(self.repo,lambda message:sent.append(message)),1)
        self.assertEqual(len(self.repo.pending_events()),0)
        self.assertEqual(len(sent),1)
if __name__=="__main__":unittest.main()
