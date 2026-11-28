"""1.50 (user: "alles in der entsprechenden Sprache" – map names stayed English with the UI in another language): map
and realm names are shown in the language of the user interface; what is stored keeps the English label."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fogscout import catalog, i18n  # noqa: E402
from fogscout.catalog import Catalog  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def lang():
    before = i18n.current()
    yield i18n.set_language
    i18n.set_language(before)


def test_names_follow_the_language_of_the_interface_and_the_stored_label_stays_english(lang):
    cat = Catalog(ROOT, ["en", "de"])
    coal = cat.maps["coal-tower"]
    lang("ru")
    assert coal.label(2) == "Coal Tower II"                      # rounds.jsonl, recordings, official data
    assert coal.shown_label(2) == coal.names["ru"] + " II" and coal.title == coal.names["ru"]
    assert coal.realm_title == coal.realm_names["ru"] and cat.realm_display(coal) == coal.realm_names["ru"]
    assert catalog.shown("Coal Tower II") == coal.names["ru"] + " II"
    assert catalog.shown("Coal Tower") == coal.names["ru"]       # older rounds without the layout number
    lang("zh")                                                     # the UI says zh, maps.json zh-Hans
    assert coal.title == coal.names["zh-Hans"] and catalog.shown("Coal Tower II") == coal.names["zh-Hans"] + " II"
    lang("de")
    assert coal.title == coal.names["de"]
    lang("en")
    assert coal.title == "Coal Tower" and catalog.shown("Coal Tower II") == "Coal Tower II"


def test_unknown_labels_stay_as_they_are_and_own_pictures_keep_their_name(lang):
    Catalog(ROOT, ["en"])
    lang("ja")
    assert catalog.shown("Some Own Map") == "Some Own Map" and catalog.shown("") == ""


def test_every_map_has_its_name_in_every_language_of_the_interface(lang):
    cat = Catalog(ROOT, ["en"])
    for code in i18n.CODES:
        lang(code)
        want = catalog.shown_lang()
        missing = [m.id for m in cat.maps.values() if not m.custom and want not in m.names]
        assert missing == [], (code, missing)


def test_the_maps_page_finds_a_map_by_its_name_in_another_script(lang):
    cat = Catalog(ROOT, ["en"])
    lang("ru")
    coal = cat.maps["coal-tower"]
    assert coal in cat.search(coal.names["ru"][:5]) and coal in cat.search("coal")
    assert coal in cat.search(cat.maps["coal-tower"].names["ja"])


def test_killer_names_follow_the_language_of_the_interface_and_discord_stays_english(lang):
    """1.50 (user: "mach die Killernamen auch"): every listed killer has its name in every language of the interface
    (from DBD's own Steam achievements) – except the three Steam has no "Adept" achievement for, which stay English.
    1.57.102: The Judgment translated by now, The Terrifier new."""
    from fogscout import lobby
    no_source = {"The Shape", "The Demogorgon", "The Cenobite"}
    assert set(lobby.KILLER_NAMES) == set(lobby.KILLERS) - no_source
    langs = set(i18n.CODES) - {"en"}
    assert all(set(v) == langs and all(v.values()) for v in lobby.KILLER_NAMES.values())
    lang("ru")
    assert lobby.killer_label("The Hillbilly") == "Деревенщина"            # as the user's Russian lobby shows it
    assert lobby.killer_label("The Shape") == "Shape" and lobby.killer_label("Frank Stone") == "Frank Stone"
    assert lobby.killer_label_en("The Hillbilly") == "Hillbilly"
    lang("ja")
    assert lobby.killer_label("The Nurse") == "ナース"
    assert lobby.killer_label("The Terrifier") == "テリファー"
    lang("de")
    assert lobby.killer_label("The Judgment") == "Urteil" and lobby.killer_label("The Terrifier") == "Terrifier"
    lang("en")
    assert lobby.killer_label("The Nurse") == "Nurse"


def test_the_terrifier_is_known_below_the_lobby_button():
    """1.57.102 (Saru: "Es gibt neue Killer Art the Clown (the Terrifier)"): read with a slip it still counts, and
    his own name as an outfit would be shown counts for him too."""
    from fogscout import lobby
    assert "The Terrifier" in lobby.KILLERS
    assert lobby.fuzzy_killer("THE TERRIFIFR") == "The Terrifier" and lobby.fuzzy_killer("TERRIFIER") == "The Terrifier"
    assert lobby.resolve_killer("Art the Clown", {}) == "The Terrifier"


def test_hartshorne_mall_is_known_with_its_realm():
    """1.57.51 (Saru: "Es gibt eine neue Map in DBD die heisst: Hartshorne Mall"; debug banners: the OCR read
    "HARTSHORNE MALL" / "THE SUBDIVISIONS" exactly, but the catalog had no such map – best guess Coal Tower II at fit
    -111). The name and realm are hypotheses of the main model now; no picture is supplied yet."""
    from fogscout.textnorm import MAIN
    cat = Catalog(ROOT, ["en", "de"])
    hyp = [h for h in cat.hypotheses if h.map_id == "hartshorne-mall"]
    assert hyp and all(h.model == MAIN and h.name_key == "HARTSHORNEMALL" for h in hyp)
    realms = {h.lang: h.realm_keys for h in hyp}
    assert "THESUBDIVISIONS" in realms["en"] and "DIEUNTERABTEILUNGEN" in realms["de"]     # DE from the DBD wiki
    assert "HARTSHORNEMALL" in cat.name_strings and "THESUBDIVISIONS" in cat.realm_strings
    assert cat.image_path("hartshorne-mall")[0] is None                 # until a picture is there: name only


def test_an_own_picture_fills_a_new_map_without_a_supplied_one(tmp_path):
    """1.57.51: no callout map of Hartshorne Mall exists yet – an own picture under the name maps.json plans
    (user_maps/The Subdivisions/Hartshorne Mall.*) becomes its picture, never a second, custom map."""
    from PIL import Image
    cat = Catalog(ROOT, ["en"], data_dir=str(tmp_path))
    assert cat.own_stem("hartshorne-mall") == "The Subdivisions/Hartshorne Mall"
    folder = tmp_path / "user_maps" / "The Subdivisions"
    folder.mkdir(parents=True)
    Image.new("RGBA", (8, 8)).save(folder / "Hartshorne Mall.webp")
    cat = Catalog(ROOT, ["en"], data_dir=str(tmp_path))
    assert cat.image_path("hartshorne-mall")[0].endswith("Hartshorne Mall.webp")
    assert not [m for m in cat.maps if m.startswith("custom:")]
