"""Regression corpus from real energy feed headlines; headline-only and conservative."""
import unittest
from editorial import evaluate

POSITIVE = {
    "Natural Gas & LNG": [
        "China Secures Major Gas Deal as Its Influence Grows Across Central Asia",
        "Orlen spreads its wings across Central and Eastern Europe with new gas pacts",
        "U.S. natural gas inventories end injection season above normal levels",
        "Woodside and Trafigura sign off on decade-long LNG deal",
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
        "ADNOC Ship Attacked in Hormuz as Maritime Security Risks Rise",
    ]
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
]

class RelevanceCorpus(unittest.TestCase):
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

    def test_excerpts_do_not_have_to_be_retained_to_classify(self):
        self.assertTrue(evaluate("US Oil Inventories On the Rise")["editorial_candidate"])

if __name__=="__main__":
    unittest.main()
