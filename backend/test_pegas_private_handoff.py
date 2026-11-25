import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from backend import pegas_private_handoff as h
from backend.test_pegas_public_projection import Tests as Fixture

class Tests(unittest.TestCase):
    def setUp(self):
        fixture=Fixture()
        fixture.setUp()
        self.now=fixture.now
        self.s,self.a=fixture.s,fixture.a
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"private.json"

    def save(self,pairs):
        self.path.write_text(json.dumps({"schema":h.SCHEMA,"pairs":pairs}),encoding="utf-8")
        self.path.chmod(0o600)

    def project(self,now=None):
        return h.project_file(self.path,now=now or self.now)

    def test_valid_exact_pair_and_no_private_fields(self):
        self.save([[self.s,self.a]])
        state,data=self.project()
        self.assertEqual(state,"VERIFIED_PROJECTION")
        self.assertEqual(len(data["previews"]),1)
        row=data["previews"][0]
        self.assertEqual(row["price_reference_rub"],120000)
        self.assertFalse(row["bookable"])
        self.assertNotIn("selected_offer_id",row)
        self.assertNotIn("browser_session_digest",row)

    def test_missing_invalid_and_permissions_fail_closed(self):
        self.assertEqual(self.project()[0],"PRIVATE_HANDOFF_MISSING")
        self.save([[self.s,self.a]])
        self.path.chmod(0o644)
        self.assertEqual(self.project()[0],"PRIVATE_HANDOFF_INVALID")
        self.path.unlink()
        self.path.symlink_to("/dev/null")
        self.assertEqual(self.project()[0],"PRIVATE_HANDOFF_INVALID")
        self.path.unlink()
        self.path.write_text("{}");self.path.chmod(0o600)
        self.assertEqual(self.project()[1]["previews"],[])

    def test_expired_unverified_and_conflicts_never_publish(self):
        self.save([[self.s,self.a]])
        self.assertEqual(self.project(self.now+timedelta(minutes=16))[1]["previews"],[])
        self.save([[self.s,{**self.a,"mandatory_fees_included":False}]])
        self.assertEqual(self.project()[1]["previews"],[])
        self.save([[self.s,self.a],[self.s,{**self.a,"total_rub":1}]])
        self.assertEqual(self.project()[1]["previews"],[])

    def test_hardlink_and_nonprivate_parent_rejected(self):
        self.save([[self.s,self.a]])
        linked=self.path.with_name("linked.json")
        os.link(self.path,linked)
        self.assertEqual(self.project()[0],"PRIVATE_HANDOFF_INVALID")
        linked.unlink()
        self.path.parent.chmod(0o755)
        self.assertEqual(self.project()[0],"PRIVATE_HANDOFF_INVALID")

if __name__=="__main__":unittest.main()
