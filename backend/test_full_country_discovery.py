"""Country discovery beyond operator's coarse Irkutsk town_from flag."""
import json
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import oracle_bg_preview_export as export
import oracle_bg_route_sync as bg

TODAY=(datetime.now(timezone.utc)+timedelta(days=7)).strftime("%d.%m.%Y")

def country(n,i,origin=False):
    return {"name":n,"id":str(100410000000+i),
            "has_tour_catalog":True,
            "origins":[bg.CITY_ID] if origin else ["100510000863"]}

def directory():
    return {"schema":"jamaica.destination-directory.v1",
            "countries":[country("Таиланд",1,True)]+[
                country("Направление "+str(i),i+1) for i in range(16)],
            "hotels":[
                {"id":"102610001486","name":"TEST","country":"Таиланд",
                 "resort":"Пхукет"},
                {"id":"102610001487","name":"TEST","country":"Направление 0",
                 "resort":"Центр"},
            ]}

class Api:
    def __init__(self):
        self.urls=[]
    def get(self,url):
        self.urls.append(url)
        if "/yandex?" in url:
            if "flt=100410000002" in url or "flt=100410000001" in url:
                fid="100410000002" if "flt=100410000002" in url else "100410000001"
                val={"entries":[{"date":TODAY,"url":
                     "https://export.bgoperator.ru/partners?action=price&tid=211&flt="+
                     fid+"&flt2="+bg.CITY_ID+"&id_price=121132934133&data="+TODAY+"&xml=11"}]}
                return json.dumps(val).encode()
            return b'{"entries":[]}'
        fid="102610001487" if "flt=100410000002" in url else "102610001486"
        rows=[{"id_hotel":fid,"tour_date":TODAY,"duration":"7",
               "room":"DBL HB","town":"TEST",
               "prices":[{"amount":"1200","RUR":"130000","ag":"12+,12+"}]}]
        return json.dumps({"cur":"EUR","entries":rows}).encode()

class Tests(unittest.TestCase):
    def test_full_country_catalog_is_in_discovery_scope(self):
        d=directory()
        selected,scope=export.select_source_countries(d,probe_slot=0)
        self.assertEqual(scope["source_tour_countries"],17)
        self.assertEqual(scope["irkutsk_catalog_countries"],1)
        self.assertEqual(len(selected),9)
        self.assertEqual(selected[0]["name"],"Таиланд")
        self.assertEqual(scope["other_countries_probed_this_cycle"],8)
    def test_all_extra_countries_are_visited_over_multiple_five_minute_runs(self):
        d=directory()
        visited=set()
        for slot in range(3):
            selected,_=export.select_source_countries(d,probe_slot=slot)
            visited.update(c["name"] for c in selected)
        self.assertEqual(visited,{c["name"] for c in d["countries"]})
    def test_official_list_can_be_found_even_if_directory_origin_flag_missing(self):
        d=directory()
        api=Api()
        feed=export.build(d,api,max_countries=120,per_country=1,probe_slot=0)
        self.assertEqual({x["country"] for x in feed["previews"]},
                         {"Таиланд","Направление 0"})
        self.assertTrue(all(x["bookable"] is False for x in feed["previews"]))
        self.assertTrue(any(x["price_reference_rub"]==130000 for x in feed["previews"]))
        self.assertEqual(feed["source_scope"]["source_tour_countries"],17)
        self.assertTrue(all("flt2="+bg.CITY_ID in url for url in api.urls))
    def test_other_countries_with_no_price_lists_are_not_fake_offers(self):
        d=directory()
        data=export.build(d,Api(),max_countries=120,per_country=1,probe_slot=0)
        missing=[x for x in data["countries_status"] if x["country"]=="Направление 1"]
        self.assertEqual(missing[0]["previews"],0)
        self.assertEqual(missing[0]["status"],"NO_FUTURE_LIST")
    def test_global_row_limit_fairly_interleaves_countries(self):
        rows=[]
        for cname in ("Таиланд","Турция","Индонезия"):
            for i in range(10):
                rows.append({"country":cname,"id":f"{cname}_{i}",
                  "depart_date":"2026-12-01","hotel":"TEST","room":"DBL"})
        subset=export.fair_catalog(rows,max_rows=7)
        counts={}
        for x in subset:counts[x["country"]]=counts.get(x["country"],0)+1
        self.assertEqual(set(counts),{"Таиланд","Турция","Индонезия"})
        self.assertEqual(sorted(counts.values()),[2,2,3])
    def test_scans_five_separate_future_price_lists(self):
        from datetime import date
        now=date(2026,11,21)
        vals=[{"date":(now+timedelta(days=i)).strftime("%d.%m.%Y")}
              for i in range(1,9)]
        self.assertEqual(len(export.choose_price_lists(vals,5,today=now)),5)

if __name__=="__main__": unittest.main()
