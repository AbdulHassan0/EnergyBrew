"""Regression corpus from real energy feed headlines; headline-only and conservative."""
import unittest
from editorial import evaluate

POSITIVE = {
    "Natural Gas": [
        "China Secures Major Gas Deal as Its Influence Grows Across Central Asia",
        "Orlen spreads its wings across Central and Eastern Europe with new gas pacts",
        "U.S. natural gas inventories end injection season above normal levels",
    ],
    "LNG": [
        "Woodside and Trafigura sign off on decade-long LNG deal",
        "Venture Global expands LNG supply agreement with China Gas",
        "Sabine Pass LNG feedgas deliveries declined after pipeline constraints",
    ],
    "Power & Electricity": [
        "Energy Secretary Acts to Protect Mid-Atlantic Grid",
        "The grid will fall short of AI's power needs. These 6 resources can close the gap.",
        "DOE-funded transmission projects could boost East-West transfer capacity 440%",
        "Elevated demand for gas turbines could persist through 2035: Siemens Energy",
        "NextEra-Dominion merger hearings kick off with focus on scope",
        "Grid operators file closely watched large load interconnection reforms at FERC",
    ],
    "Oil & Energy": [
        "US Oil Inventories On the Rise",
        "EnQuest Exits UK North Sea in $960 Million Deal",
        "Thiel Doubles Down on Vaca Muerta as Trump Calls Venezuela an Acquisition",
        "Democrats Could Slow Venezuela's Push Toward 3 Million Bpd",
    ],
    "Geopolitics": [
        "ADNOC Ship Attacked in Hormuz as Maritime Security Risks Rise",
        "Iranian missiles threaten oil tankers near Strait of Hormuz",
        "Ukraine strikes two Russian oil refineries amid conflict",
        "US imposes new sanctions on Russian crude oil exports",
        "China announces tariffs on US LNG imports",
        "Houthi drone attacks disrupt Red Sea shipping routes",
        "Israel strikes Iranian power grid infrastructure amid conflict",
        "US launches missile strikes against Iran",
        "Russian forces launch a major invasion of Ukraine",
        "China threatens Taiwan with military invasion",
    ],
}

NEGATIVE = [
    "Worker injured near Brent Cross Shopping Centre",
    "Students learn how to conserve electricity in school awareness week",
    "How to save electricity at home with five easy tips",
    "Crossword grid puzzle answers for Wednesday",
    "Cooking with natural gas stove tips for beginners",
    "Grid view shortcuts for spreadsheet software",
    "City government opens new shopping mall",
    "Thames Water rescue deal comes with a dirty catch",
    "Oil painting exhibition opens in city hall",
    "Iran and Israel resume ceasefire talks",
    "Russia announces new election dates",
    "Ukraine and Russia discuss prisoner exchange",
    "US sanctions Russian banks for cybersecurity breaches",
    "Regional school debate discusses the war in Europe",
    "China and Taiwan hold peace negotiations",
    "US and Iran announce new diplomatic meetings",
]

class RelevanceCorpus(unittest.TestCase):
    def test_historical_anniversary_is_not_todays_market_news(self):
        from editorial import non_article_reason
        title="Today in History: November 19, explosions at Mexico City natural gas facility kill hundreds"
        self.assertFalse(evaluate(title)["editorial_candidate"])
        self.assertEqual(non_article_reason(title,"https://example.com/history/gas"),
                         "historical_retrospective")

    def test_real_energy_market_headlines_survive(self):
        for beat, titles in POSITIVE.items():
            for title in titles:
                with self.subTest(title=title):
                    result=evaluate(title)
                    self.assertTrue(result["editorial_candidate"],msg=result)
                    self.assertEqual(result["category"],beat,msg=result)

    def test_common_keyword_collision_and_low_impact_headlines_excluded(self):
        for title in NEGATIVE:
            with self.subTest(title=title):
                self.assertFalse(evaluate(title)["editorial_candidate"],msg=evaluate(title))

    def test_mixed_energy_keywords_cannot_hide_geopolitical_incident(self):
        title=("Iranian drone strikes threaten Strait of Hormuz oil tankers, "
               "crude oil exports and LNG gas shipping supply")
        r=evaluate(title)
        self.assertEqual(r["category"],"Geopolitics")
        self.assertIn("world_context:iranian",r["evidence"])
        self.assertTrue(r["editorial_candidate"])

    def test_inferred_regional_conflict_lower_confidence_than_explicit_oil_risk(self):
        inferred=evaluate("US launches missile strikes against Iran")
        explicit=evaluate("US launches missile strikes against Iranian oil export terminal")
        self.assertEqual(inferred["category"],"Geopolitics")
        self.assertEqual(explicit["category"],"Geopolitics")
        self.assertLess(inferred["relevance_score"],explicit["relevance_score"])
        self.assertTrue(any("inferred_" in x for x in inferred["evidence"]))

    def test_excerpts_do_not_have_to_be_retained_to_classify(self):
        self.assertTrue(evaluate("US Oil Inventories On the Rise")["editorial_candidate"])

if __name__=="__main__":
    unittest.main()
