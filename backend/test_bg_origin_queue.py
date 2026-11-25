import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from scripts.bg_origin_queue import OriginQueue

def registry():
    return {"schema":"jamaica.origin-registry.v1","classification":"SEARCH_SCOPE_ONLY_NOT_OFFERS",
        "cities":{"100510397223":"Иркутск","100510397224":"Москва"},
        "countries":{"100510397225":"Китай","100510397226":"Таиланд"},
        "pairs":[{"origin_id":o,"origin":name,"country_id":c,"country":cn}
        for o,name in (("100510397223","Иркутск"),("100510397224","Москва"))
        for c,cn in (("100510397225","Китай"),("100510397226","Таиланд"))]}
class OriginQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"queue.sqlite"
        self.q=OriginQueue(self.path)
        self.addCleanup(self.q.close)
        self.t=datetime(2026,11,25,tzinfo=timezone.utc)
        self.assertEqual(self.q.sync(registry()),4)
    def at(self,n):
        return self.t+timedelta(seconds=n)
    def test_single_claim_and_durable_cooldown(self):
        token,s=self.q.claim(self.t)
        self.assertEqual((s.origin,s.country),("Иркутск","Таиланд"))
        q2=OriginQueue(self.path)
        self.addCleanup(q2.close)
        self.assertIsNone(q2.claim(self.at(9999)))
        with self.assertRaises(ValueError):
            q2.finish("wrong","OBSERVED",self.t)
        self.q.finish(token,"PROVIDER_COOLDOWN",self.at(5),retry_after=900)
        self.assertIsNone(q2.claim(self.at(904)))
        self.assertIsNotNone(q2.claim(self.at(905)))
    def test_fair_rotation_all_cities(self):
        order=[]
        for i in range(4):
            t=self.at(i*180)
            token,s=self.q.claim(t)
            order.append((s.origin,s.country))
            self.q.finish(token,"NO_MATCH",t)
        self.assertEqual(len(set(order)),4)
        self.assertEqual({s[0] for s in order},{"Иркутск","Москва"})
        self.assertIsNone(self.q.claim(self.at(719)))
        self.assertIsNotNone(self.q.claim(self.at(720)))
    def test_duplicate_and_bad_scope_atomic(self):
        r=registry()
        r["pairs"].append(r["pairs"][0])
        with self.assertRaises(ValueError):
            self.q.sync(r)
        self.assertEqual(len(self.q.snapshot()["scopes"]),4)
        r=registry()
        r["pairs"][0]["origin"]="Москва"
        with self.assertRaises(ValueError):
            self.q.sync(r)
    def test_registry_changes_disable_removed_scope(self):
        r=registry()
        r["pairs"]=r["pairs"][:2]
        self.assertEqual(self.q.sync(r),2)
        self.assertEqual(len(self.q.snapshot()["scopes"]),2)
    def test_active_claim_blocks_sync_and_local_hold_not_offer(self):
        token,_=self.q.claim(self.t)
        with self.assertRaises(RuntimeError):
            self.q.sync(registry())
        self.q.finish(token,"LOCAL_HOLD",self.t)
        snap=self.q.snapshot()
        self.assertFalse(snap["active_claim"])
        self.assertEqual(snap["classification"],"SCHEDULER_STATE_NOT_OFFERS")
        self.assertEqual(snap["scopes"][0]["last_result"],"LOCAL_HOLD")
    def test_invalid_clock_and_gap(self):
        with self.assertRaises(ValueError):
            OriginQueue(self.path,global_gap=30)
        with self.assertRaises(ValueError):
            self.q.claim(datetime(2026,11,25))
