"""Cross-publication event similarity has conservative false-positive behavior."""
import unittest
from event_dedup import same_event, entities, family

def item(title, uri, date="2026-11-18T14:00:00+00:00"):
    return {"title":title,"url":uri,"observed_time_utc":date}

class EventDedupTests(unittest.TestCase):
    def test_multiple_venture_global_coverage_is_one_event_candidate(self):
        a=item("China Gas Upsizes Long-Term LNG Supply with U.S. Venture Global","https://a.test/story")
        b=item("Venture Global’s bigger LNG deal with China Gas adds 500,000 tons annually","https://b.test/story")
        c=item("Venture Global and China Gas Announce Increased Long-Term LNG Agreement","https://c.test/story")
        self.assertTrue(same_event(a,b))
        self.assertTrue(same_event(a,c))
    def test_distinct_named_companies(self):
        a=item("Venture Global signs LNG agreement with China Gas","https://a.test/a")
        b=item("Cheniere signs LNG agreement with QatarEnergy","https://b.test/b")
        self.assertFalse(same_event(a,b))
    def test_distinct_topic_same_firm(self):
        a=item("ExxonMobil LNG project acquisition","https://a.test/a")
        b=item("ExxonMobil launches power infrastructure plans","https://b.test/b")
        self.assertFalse(same_event(a,b))
    def test_far_apart_dates_never_merged(self):
        a=item("Venture Global signs LNG agreement with China Gas","https://a.test/a")
        b=item("Venture Global signs LNG agreement with China Gas","https://b.test/b","2026-11-10T15:00:00Z")
        self.assertFalse(same_event(a,b))
    def test_gas_project_different_location_not_merged(self):
        a=item("FERC approves natural gas pipeline project in Alabama","https://a.test/a")
        b=item("FERC approves natural gas pipeline project in Texas","https://a.test/b")
        self.assertFalse(same_event(a,b))
    def test_markers(self):
        self.assertIn("venture global",entities("Venture Global shipping LNG"))
        self.assertEqual(family("Venture Global LNG supply agreement"),"lng_contract")

if __name__=="__main__":
    unittest.main()
