from datetime import datetime

TOP_LEVEL_KEYS = {"version", "generated_at", "credits", "scenes", "artists", "related"}
CREDIT_KEYS = {"name", "url"}
SCENE_KEYS = {"id", "label", "size"}
ARTIST_KEYS = {"id", "name", "aliases", "nights", "cities", "scene", "pos"}


def assert_map_contract(payload: object) -> None:
    assert isinstance(payload, dict)
    assert set(payload) == TOP_LEVEL_KEYS
    assert payload["version"] == 1
    assert datetime.fromisoformat(payload["generated_at"]).utcoffset() is not None
    for credit in payload["credits"]:
        assert set(credit) == CREDIT_KEYS
        assert all(isinstance(value, str) for value in credit.values())
    scene_ids = set()
    for scene in payload["scenes"]:
        assert set(scene) == SCENE_KEYS
        assert isinstance(scene["id"], int) and isinstance(scene["size"], int)
        assert isinstance(scene["label"], str)
        scene_ids.add(scene["id"])
    artist_ids = set()
    for artist in payload["artists"]:
        assert set(artist) == ARTIST_KEYS
        assert isinstance(artist["id"], int) and isinstance(artist["name"], str)
        assert isinstance(artist["nights"], int)
        assert isinstance(artist["aliases"], list)
        assert all(isinstance(alias, str) for alias in artist["aliases"])
        assert isinstance(artist["cities"], list)
        assert all(isinstance(city, str) for city in artist["cities"])
        assert artist["scene"] is None or artist["scene"] in scene_ids
        position = artist["pos"]
        assert position is None or (
            isinstance(position, list) and len(position) == 3 and all(isinstance(v, float) for v in position)
        )
        artist_ids.add(artist["id"])
    for pair in payload["related"]:
        assert isinstance(pair, list) and len(pair) == 3
        source, target, score = pair
        assert source in artist_ids and target in artist_ids
        assert isinstance(score, float)
