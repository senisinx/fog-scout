"""CR-006 (code review): game languages in another script (RU / ZH / JA / KO) – the manual scan crashed on an empty
lexicon of the main model, and fold() (A-Z0-9 only) made aliases, own maps, log search and killer aliases of such
names empty."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fogscout import fullscan, lobby, textnorm  # noqa: E402
from fogscout.catalog import Catalog  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Det:
    def boxes(self, frame):
        return [(0, 0, 60, 20)]


class _Rec:
    """Reads every crop as noise: a recognizer for any model."""
    def __init__(self):
        self.used = 0

    def probs(self, crop):
        self.used += 1
        return np.full((12, 4), 0.25, np.float32)

    def wide_groups(self, probs, alphabet):
        return np.full((len(probs), len(alphabet) + 2), 1.0 / (len(alphabet) + 2), np.float32)

    def text(self, probs):
        return ""


class _Pool:
    def __init__(self):
        self.asked, self.rec = [], _Rec()

    def get(self, model):
        self.asked.append(model)
        return self.rec


@pytest.mark.parametrize("lang,model", [("ru", "cyrillic"), ("ja", "cjk"), ("ko", "korean"), ("zh-Hans", "cjk")])
def test_the_manual_scan_reads_a_game_language_of_another_script(lang, model):
    cat = Catalog(ROOT, [lang])
    pool = _Pool()
    scanner = fullscan.FullScanner(_Det(), _Rec(), cat, pool)
    assert model in [m[0] for m in scanner.models]
    assert scanner.scan(np.zeros((40, 80, 3), np.uint8)) == []             # no IndexError, nothing made up
    assert model in pool.asked


def test_without_a_pool_the_scan_still_never_crashes():
    cat = Catalog(ROOT, ["ru"])
    assert fullscan.FullScanner(_Det(), _Rec(), cat).scan(np.zeros((40, 80, 3), np.uint8)) == []


@pytest.mark.parametrize("text,model", [("Угольная башня", "cyrillic"), ("石炭の塔", "cjk"), ("탄광 탑", "korean"),
                                        ("煤炭塔", "cjk"), ("Coal Tower", textnorm.MAIN)])
def test_an_alias_in_another_script_is_read_by_its_model(text, model):
    lang = {"cyrillic": "ru", "korean": "ko", "cjk": "ja"}.get(model, "en")
    cat = Catalog(ROOT, [lang], aliases={"coal-tower": [text + " X"]})
    assert cat.alias_problem(text + " Y", "coal-tower") is None
    hyp = [h for h in cat.hypotheses if h.lang == "alias" and h.map_id == "coal-tower"]
    assert hyp and hyp[0].model == model and hyp[0].name_key == textnorm.fold_any(text + " X")


def test_suggest_finds_a_map_by_a_name_in_another_script():
    cat = Catalog(ROOT, ["ru"])
    assert cat.suggest("Угольная Башн", "Поместье МакМилла") == "coal-tower"


def test_a_killer_alias_in_another_script_is_stored_and_found():
    key = textnorm.fold_any("Охотница")
    assert key and lobby.resolve_killer("охотница", {key: "The Huntress"}) == "The Huntress"
    assert lobby.resolve_killer("Murderous Grizzly", {textnorm.fold("Murderous Grizzly"): "The Hillbilly"}) \
        == "The Hillbilly"                                                 # old Latin keys stay valid
