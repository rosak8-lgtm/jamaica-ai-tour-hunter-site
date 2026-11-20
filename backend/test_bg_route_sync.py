import json, os, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from scripts import oracle_bg_route_sync as bg

TODAY=datetime.now(timezone.utc).date()
FUTURE=(TODAY+timedelta(days=9)).strftime("%d.%m.%Y")
PAST=(TODAY-timedelta(days=2)).strftime("%d.%m.%Y")
def entry(**kw):
    v={"date":FUTURE,"route":"Тур <b>Таиланд</b> · Пхукет",
       "duration":"/3/4/7/10","id_price":"121132934133","minprice":"999","cur":"USD"}
    v.update(kw)
    return v
COUNTRY={"id":"100410000051","name":"Таиланд",
  "has_tour_catalog":True,"origins":[bg.CITY_ID]}

class Tests(unittest.TestCase):
 def test_sanitize_route_and_ignore_unverified_prices(self):
    a=bg.parse_entries({"entries":[entry()]},COUNTRY,TODAY,TODAY+timedelta(days=180))
    self.assertEqual(len(a),1)
    self.assertEqual(a[0]["nights"],[3,4,7,10])
    self.assertNotIn("<",a[0]["route"])
    self.assertFalse(a[0]["bookable"])
    for key in ["minprice","cur","id_price","url","operator","total_rub"]:
       self.assertNotIn(key,a[0])
 def test_stops_and_past_excluded(self):
    x=bg.parse_entries({"entries":[entry(stop="1"),entry(date=PAST)]},
      COUNTRY,TODAY,TODAY+timedelta(days=180))
    self.assertEqual(x,[])
 def test_invalid_schema_fails_closed(self):
    with self.assertRaises(bg.SyncHold):
        bg.parse_entries({"items":[entry()]},COUNTRY,TODAY,TODAY+timedelta(days=180))
 def test_build_count_and_no_payment(self):
    class Client:
      def get(self,url):
        self.assert_url=url
        return json.dumps({"entries":[entry()]}).encode()
    obj={"schema":"jamaica.destination-directory.v1","countries":[COUNTRY]}
    with patch.object(bg.time,"sleep",lambda _:None):
      out=bg.build(obj,Client())
    self.assertEqual(out["countries_success"],1)
    self.assertEqual(len(out["routes"]),1)
    self.assertFalse(out["quote_verified"])
    self.assertFalse(out["availability_verified"])
    self.assertFalse(out["bookable"])
 def test_private_credentials_permissions(self):
    with tempfile.TemporaryDirectory() as d:
      p=Path(d)/"credential.json"
      p.write_text('{"login":"test","pwd":"testpass"}')
      os.chmod(p,0o600)
      self.assertEqual(bg.read_secret(p),("test","testpass"))
      os.chmod(p,0o644)
      with self.assertRaises(bg.SyncHold):bg.read_secret(p)
 def test_strict_host(self):
    class C(bg.ApiClient):
      pass
    client=C("test","test")
    with self.assertRaises(bg.SyncHold):client.call("https://bad-example.com/no")
if __name__=="__main__":unittest.main()
