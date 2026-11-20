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
    def test_different_contract_amounts_do_not_merge(self):
        a=item("Venture Global and China Gas announce 1 million tpy LNG supply agreement",
               "https://a.test/contract1")
        b=item("China Gas and Venture Global sign 2 million tpy LNG supply contract",
               "https://b.test/contract2")
        self.assertFalse(same_event(a,b))

    def test_separate_2026_and_2027_contract_coverage_does_not_merge(self):
        a=item("Venture Global and China Gas 2026 LNG supply contract","https://a.test/a")
        b=item("China Gas and Venture Global 2027 LNG supply deal","https://b.test/b")
        self.assertFalse(same_event(a,b))

    def test_same_parties_new_deal_after_60_hours_is_not_suppressed(self):
        a=item("Venture Global signs LNG agreement with China Gas","https://a.test/a")
        b=item("China Gas signs LNG agreement with Venture Global",
               "https://b.test/b","2026-11-21T02:00:00Z")
        self.assertFalse(same_event(a,b))

    def test_distinct_event_families_same_counterparties_not_merged(self):
        a=item("Venture Global and China Gas announce LNG supply agreement", "https://a.test/a")
        b=item("Venture Global and China Gas announce LNG stake acquisition", "https://b.test/b")
        self.assertFalse(same_event(a,b))

    def test_different_named_counterparties_do_not_merge_on_generic_words(self):
        a=item("Shell and BP announce natural gas supply expansion investment project", "https://a.test/a")
        b=item("Shell and Chevron announce natural gas supply expansion investment project", "https://b.test/b")
        self.assertFalse(same_event(a,b))

    def test_signed_then_cancelled_lng_agreement_remain_two_events(self):
        signed=item("Venture Global and China Gas signed LNG supply agreement", "https://a.test/signed")
        cancelled=item("Venture Global and China Gas cancelled LNG supply agreement", "https://b.test/cancelled")
        self.assertFalse(same_event(signed, cancelled))

    def test_approved_then_revoked_energy_permit_remain_two_events(self):
        approved=item("FERC approved major natural gas pipeline expansion project in Texas", "https://a.test/approved")
        revoked=item("FERC revoked major natural gas pipeline expansion project in Texas", "https://b.test/revoked")
        self.assertFalse(same_event(approved, revoked))

    def test_two_reports_of_same_signed_deal_still_merge(self):
        a=item("Venture Global and China Gas signed LNG supply agreement", "https://a.test/a")
        b=item("China Gas and Venture Global signed LNG supply agreement", "https://b.test/b")
        self.assertTrue(same_event(a, b))

    def test_markers(self):
        self.assertIn("venture global",entities("Venture Global shipping LNG"))
        self.assertEqual(family("Venture Global LNG supply agreement"),"lng_contract")

if __name__=="__main__":
    unittest.main()
