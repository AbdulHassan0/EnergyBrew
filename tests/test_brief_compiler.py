"""Six-beat pilot issue assembly from source-backed original text only."""
import copy
import unittest
from datetime import datetime,timezone
from brief_compiler import compile_pilot
from newsletter import EditorialError, TOPICS, render_html

NOW=datetime(2026,11,19,12,50,tzinfo=timezone.utc)
def fixtures():
    desk={"generated_utc":"2026-11-19T12:30:00+00:00","stories":[]}
    submitted={"edition_date":"2026-11-19","briefs":[]}
    for n,beat in enumerate(TOPICS):
        url=f"https://publisher{n}.com/news/story-{n}"
        row={"url":url,"title":f"Relevant major {beat} energy investment",
             "category":beat,"relevance_score":80}
        desk["stories"].append(row)
        submitted["briefs"].append({
            "source_url":url,"section":beat,"publisher":"Publisher",
            "source_date":"2026-11-18",
            "title":f"Major source-backed development in {beat}",
            "summary":("A new energy development has been reported by the original "
                       "publisher. The source describes material infrastructure "
                       "implications and identifies the relevant market and "
                       "next decisions for participants."),
            "why_it_matters":("The update may affect energy infrastructure planning "
                              "and commercial choices over the coming year."),
        })
    return desk,submitted


class CompilerTests(unittest.TestCase):
    def test_builds_six_sectors_without_any_pending_summary(self):
        desk,briefs=fixtures()
        issue,quality=compile_pilot(desk,briefs,now=NOW)
        self.assertEqual(set(s["section"] for s in issue["stories"]),set(TOPICS))
        self.assertEqual(quality["status"],"pilot_copy_ready")
        self.assertEqual(quality["total_stories"],6)
        self.assertEqual(issue["status"],"pilot")
        self.assertNotIn("pending fact-check",render_html(issue,pilot=True).lower())

    def test_blank_briefs_cannot_become_fake_newsletter(self):
        desk,briefs=fixtures()
        briefs["briefs"][2]["summary"]=""
        with self.assertRaisesRegex(EditorialError,"substantive summary"):
            compile_pilot(desk,briefs,now=NOW)

    def test_missing_beat_blocks_compilation(self):
        desk,briefs=fixtures()
        briefs["briefs"].pop()
        with self.assertRaisesRegex(EditorialError,"Insufficient authored evidence"):
            compile_pilot(desk,briefs,now=NOW)

    def test_unknown_external_url_cannot_be_minted_as_collected_news(self):
        desk,briefs=fixtures()
        briefs["briefs"][2]["source_url"]="https://random.example.com/energy"
        with self.assertRaisesRegex(EditorialError,"no matching saved"):
            compile_pilot(desk,briefs,now=NOW)

    def test_source_in_full_gdelt_history_but_not_desk_is_allowed(self):
        desk,briefs=fixtures()
        desk["stories"].pop(3)
        link=briefs["briefs"][3]["source_url"]
        issue,quality=compile_pilot(
            desk,briefs,now=NOW,
            raw_sources={"discovery":[{"url":link,
                "gdelt_first_seen_utc":"2026-11-19T11:30:00+00:00"}]})
        self.assertEqual(quality["matched_saved_source_links"],6)
        self.assertEqual(quality["matched_research_links"],5)
        self.assertEqual(len(issue["stories"]),6)

    def test_repeated_and_unauthored_source_rejected(self):
        desk,briefs=fixtures()
        briefs["briefs"][1]["source_url"]=briefs["briefs"][0]["source_url"]+"/"
        with self.assertRaisesRegex(EditorialError,"repeats a source URL"):
            compile_pilot(desk,briefs,now=NOW)

    def test_stale_snapshot_fails_closed(self):
        desk,briefs=fixtures()
        desk["generated_utc"]="2026-11-15T00:00:00+00:00"
        with self.assertRaisesRegex(EditorialError,"stale"):
            compile_pilot(desk,briefs,now=NOW)

    def test_wrong_date_blocked_without_inventing_day(self):
        desk,briefs=fixtures()
        briefs["edition_date"]="2026-11-31"
        with self.assertRaisesRegex(EditorialError,"real edition date"):
            compile_pilot(desk,briefs,now=NOW)

    def test_prefer_source_diversity_and_two_per_beat(self):
        desk,briefs=fixtures()
        for i in range(4):
            url=f"https://extra{i}.net/grid/{i}"
            desk["stories"].append({"url":url,"category":"Power & Electricity"})
            briefs["briefs"].append({
                **briefs["briefs"][2],"source_url":url,
                "priority":90-i,
            })
        issue,quality=compile_pilot(desk,briefs,now=NOW)
        # With only one extra power story allowed under two-per-beat, a
        # seven-story issue is correct; never manufacture an eighth.
        self.assertEqual(len(issue["stories"]),7)
        self.assertLessEqual(sum(x["section"]=="Power & Electricity"
                                 for x in issue["stories"]),2)
        self.assertEqual(quality["status"],"pilot_copy_ready")


if __name__=="__main__":
    unittest.main()
