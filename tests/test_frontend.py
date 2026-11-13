"""Basic static integration test for documented UI features."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])

class UiTests(unittest.TestCase):
    def test_corpus_controls_exist(self):
        html = (ROOT/'index.html').read_text(encoding='utf-8')
        ids = IdParser()
        ids.feed(html)
        required = {'corpusStatus', 'corpusQuery', 'corpusField', 'corpusPeriod', 'corpusGenre', 'corpusResults', 'searchCorpus'}
        self.assertTrue(required.issubset(ids.ids), required - ids.ids)
        script = (ROOT/'corpus-ui.js').read_text(encoding='utf-8')
        used = set(re.findall(r"\$\('([\w-]+)'\)",script))
        self.assertTrue(used.issubset(ids.ids), used - ids.ids)
    def test_vision_controls_and_script_loaded(self):
        html = (ROOT/'index.html').read_text(encoding='utf-8')
        ids=IdParser(); ids.feed(html)
        expected={'predictionInput','visionThreshold','visionResults','visionStatus',
                  'visionThresholdValue','acceptVisibleDetections','clearDetections'}
        self.assertTrue(expected.issubset(ids.ids), expected - ids.ids)
        self.assertIn('src="vision.js"', html)
        app=(ROOT/'app.js').read_text(encoding='utf-8')
        used=set(re.findall(r"\$\('([\w-]+)'\)",app))
        self.assertTrue(used.issubset(ids.ids), used - ids.ids)
        server=(ROOT/'server.py').read_text(encoding='utf-8')
        self.assertIn("'/vision.js'",server)

    def test_corpus_ui_script_loaded(self):
        html = (ROOT/'index.html').read_text(encoding='utf-8')
        self.assertIn('src="corpus-ui.js"', html)
        self.assertIn('value="id"', html)

if __name__ == '__main__': unittest.main()
