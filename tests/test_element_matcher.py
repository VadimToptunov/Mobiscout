"""Tests for framework.healing.element_matcher.

These guard the scoring that picks the correct replacement selector during
self-healing: without an ML model the selector's own confidence wins; with a
model the ML and base confidences are blended (0.4/0.6) and an expected-type
mismatch halves the ML contribution; context boosts nudge stable selector types
and screen-name matches; the highest combined score is returned and empty input
yields no match. validate_match must gate on the combined confidence.
"""

from framework.healing.element_matcher import ElementMatcher, MatchResult
from framework.healing.selector_discovery import AlternativeSelector, SelectorStrategy


def _alt(strategy, value, confidence, **attrs):
    return AlternativeSelector(strategy=strategy, value=value, confidence=confidence, element_attributes=dict(attrs))


class _FakeType:
    """Stand-in for an ElementType with a .value the matcher reads."""

    def __init__(self, value):
        self.value = value


class _FakeMLModel:
    """Minimal ML model: returns a fixed (type, confidence) from predict().

    Mocks only the injected ML dependency, not the code under test, so the real
    _get_ml_confidence / _score_alternative blending runs against known numbers.
    """

    def __init__(self, type_value, confidence):
        self._type = _FakeType(type_value)
        self._confidence = confidence
        self.last_features = None

    def predict(self, features):
        self.last_features = features
        return self._type, self._confidence


def test_no_alternatives_returns_none():
    assert ElementMatcher().find_best_match([]) is None


def test_without_ml_model_combined_equals_base_confidence():
    """No model and no context: combined confidence is the selector's own."""
    matcher = ElementMatcher()  # ml_model_path=None -> self.ml_model stays None
    alt = _alt(SelectorStrategy.TEXT, "Login", 0.70)

    match = matcher.find_best_match([alt])

    assert match is not None
    assert match.ml_confidence == 0.0
    assert match.combined_confidence == 0.70
    assert match.selector is alt


def test_highest_combined_confidence_wins():
    """The ID selector (0.95) outranks text (0.70) when nothing else differs."""
    matcher = ElementMatcher()
    id_alt = _alt(SelectorStrategy.ID, "com.app:id/login", 0.95, **{"resource-id": "com.app:id/login"})
    text_alt = _alt(SelectorStrategy.TEXT, "Login", 0.70, text="Login")

    match = matcher.find_best_match([text_alt, id_alt])

    assert match.selector is id_alt
    assert match.combined_confidence == 0.95


def test_ml_confidence_blends_with_base():
    """combined = base*0.4 + ml*0.6 when the ML model returns a positive score."""
    matcher = ElementMatcher()
    matcher.ml_model = _FakeMLModel("button", 1.0)
    alt = _alt(SelectorStrategy.XPATH, "//Button", 0.50, **{"class": "android.widget.Button"})

    match = matcher.find_best_match([alt])  # expected_element_type=None

    assert match.ml_confidence == 1.0
    # 0.50*0.4 + 1.0*0.6 = 0.80
    assert abs(match.combined_confidence - 0.80) < 1e-9
    # features were actually extracted from the alternative's attributes
    assert matcher.ml_model.last_features["class"] == "android.widget.Button"


def test_ml_type_mismatch_halves_confidence():
    """When an expected type is supplied and the model disagrees, ML weight halves."""
    matcher = ElementMatcher()
    matcher.ml_model = _FakeMLModel("input", 0.80)
    alt = _alt(SelectorStrategy.XPATH, "//Button", 0.50)

    match = matcher.find_best_match([alt], expected_element_type="button")

    # ml -> 0.80 * 0.5 = 0.40 ; combined = 0.50*0.4 + 0.40*0.6 = 0.44
    assert abs(match.ml_confidence - 0.40) < 1e-9
    assert abs(match.combined_confidence - 0.44) < 1e-9


def test_ml_type_match_keeps_full_confidence():
    matcher = ElementMatcher()
    matcher.ml_model = _FakeMLModel("button", 0.80)
    alt = _alt(SelectorStrategy.XPATH, "//Button", 0.50)

    match = matcher.find_best_match([alt], expected_element_type="button")

    assert abs(match.ml_confidence - 0.80) < 1e-9
    # 0.50*0.4 + 0.80*0.6 = 0.68
    assert abs(match.combined_confidence - 0.68) < 1e-9


def test_context_boost_for_stable_selector_type():
    """id/accessibility_id get a +0.05 stability boost when context is present."""
    matcher = ElementMatcher()
    alt = _alt(SelectorStrategy.ACCESSIBILITY_ID, "login", 0.90)

    boosted = matcher.find_best_match([alt], context={"screen_name": "Home"})
    plain = matcher.find_best_match([alt])

    assert abs(boosted.combined_confidence - 0.95) < 1e-9
    assert plain.combined_confidence == 0.90


def test_context_boost_caps_at_one():
    matcher = ElementMatcher()
    alt = _alt(SelectorStrategy.ID, "x", 0.99)
    match = matcher.find_best_match([alt], context={"screen_name": "Home"})
    assert match.combined_confidence == 1.0


def test_context_screen_name_boost_on_matching_class():
    """A screen name found inside the element's class adds +0.05 (non-stable type)."""
    matcher = ElementMatcher()
    alt = _alt(SelectorStrategy.TEXT, "Go", 0.70, **{"class": "com.app.LoginActivity"})
    match = matcher.find_best_match([alt], context={"screen_name": "Login"})
    assert abs(match.combined_confidence - 0.75) < 1e-9


def test_reasoning_includes_strategy_and_key_attributes():
    matcher = ElementMatcher()
    alt = _alt(
        SelectorStrategy.ID,
        "com.app:id/login",
        0.95,
        **{"resource-id": "com.app:id/login", "text": "Login"},
    )
    match = matcher.find_best_match([alt])
    assert "Strategy: id" in match.reasoning
    assert "Base confidence: 0.95" in match.reasoning
    assert "Has ID: com.app:id/login" in match.reasoning
    assert "Text: 'Login'" in match.reasoning


def test_ml_prediction_error_is_swallowed_to_zero():
    """A model whose predict() raises must not crash matching; ML confidence -> 0."""

    class _Boom:
        def predict(self, features):
            raise ValueError("bad features")

    matcher = ElementMatcher()
    matcher.ml_model = _Boom()
    alt = _alt(SelectorStrategy.TEXT, "Login", 0.70)

    match = matcher.find_best_match([alt])
    assert match.ml_confidence == 0.0
    assert match.combined_confidence == 0.70


def test_corrupt_model_file_degrades_gracefully(tmp_path):
    """A model path that exists but is not a loadable model must not crash the
    constructor; the matcher falls back to selector-only scoring."""
    bad = tmp_path / "model.pkl"
    bad.write_bytes(bytes(range(64)))  # not a valid joblib payload

    matcher = ElementMatcher(ml_model_path=bad)

    assert matcher.ml_model is None
    match = matcher.find_best_match([_alt(SelectorStrategy.ID, "x", 0.95)])
    assert match.combined_confidence == 0.95
    assert match.ml_confidence == 0.0


def test_validate_match_thresholds():
    matcher = ElementMatcher()
    high = MatchResult(
        selector=_alt(SelectorStrategy.ID, "x", 0.9), ml_confidence=0.0, combined_confidence=0.85, reasoning=""
    )
    low = MatchResult(
        selector=_alt(SelectorStrategy.TEXT, "y", 0.6), ml_confidence=0.0, combined_confidence=0.60, reasoning=""
    )

    assert matcher.validate_match(high) is True
    assert matcher.validate_match(low) is False
    # boundary: exactly at threshold is valid
    boundary = MatchResult(
        selector=_alt(SelectorStrategy.ID, "z", 0.7), ml_confidence=0.0, combined_confidence=0.70, reasoning=""
    )
    assert matcher.validate_match(boundary, min_confidence=0.70) is True


def test_match_result_repr_shows_strategy_and_confidence():
    m = MatchResult(
        selector=_alt(SelectorStrategy.ID, "x", 0.9), ml_confidence=0.0, combined_confidence=0.91, reasoning=""
    )
    assert m.__repr__() == "MatchResult(id, confidence=0.91)"


def _trained_classifier():
    """A minimally-fitted real ElementClassifier (button vs text).

    Fitting the model directly (bypassing train()'s cross-validation) keeps the
    test fast while still exercising the real extract_features/predict path — the
    path that used to raise AttributeError when the matcher handed it a raw
    ``bounds`` string.
    """
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import LabelEncoder

    from framework.ml.element_classifier import ElementClassifier

    clf = ElementClassifier()
    rows, labels = [], []
    for _ in range(3):
        rows.append(
            clf.extract_features(
                {
                    "class": "android.widget.Button",
                    "clickable": True,
                    "text": "OK",
                    "bounds": {"width": 200, "height": 80},
                }
            )
        )
        labels.append("button")
        rows.append(
            clf.extract_features(
                {
                    "class": "android.widget.TextView",
                    "text": "some longer body text",
                    "bounds": {"width": 300, "height": 40},
                }
            )
        )
        labels.append("text")

    df = pd.DataFrame(rows)
    clf.feature_names = list(df.columns)
    clf.label_encoder = LabelEncoder()
    y = clf.label_encoder.fit_transform(labels)
    model = RandomForestClassifier(n_estimators=10, random_state=0)
    model.fit(df, y)
    clf.model = model
    clf.trained = True
    return clf


def test_get_ml_confidence_positive_for_known_element_with_model():
    """With a real model, ML confidence must be > 0 for a concrete element.

    The matcher's _extract_features used to return ``bounds`` as the raw
    UIAutomator string; ElementClassifier.extract_features then did
    ``bounds.get("width")`` on a str, raising AttributeError which was swallowed
    to a 0.0 confidence. Parsing bounds into a dict restores a real prediction.
    """
    matcher = ElementMatcher()
    matcher.ml_model = _trained_classifier()

    alt = _alt(
        SelectorStrategy.ID,
        "com.app:id/ok",
        0.9,
        **{
            "class": "android.widget.Button",
            "clickable": "true",
            "text": "OK",
            "bounds": "[0,0][200,80]",  # raw UIAutomator bounds string
        },
    )

    confidence = matcher._get_ml_confidence(alt, expected_type=None)
    assert confidence > 0.0


def test_extract_features_parses_bounds_string_to_dict():
    """_extract_features must hand the ML model a bounds *dict* with width/height,
    parsed from the ``[x1,y1][x2,y2]`` UIAutomator string."""
    matcher = ElementMatcher()
    alt = _alt(SelectorStrategy.ID, "x", 0.9, **{"bounds": "[10,20][110,80]"})

    features = matcher._extract_features(alt)

    assert features["bounds"] == {"width": 100, "height": 60}


def test_extract_features_bounds_missing_or_malformed_is_zero_dict():
    matcher = ElementMatcher()
    missing = matcher._extract_features(_alt(SelectorStrategy.ID, "x", 0.9))
    malformed = matcher._extract_features(_alt(SelectorStrategy.ID, "x", 0.9, **{"bounds": "not-bounds"}))

    assert missing["bounds"] == {"width": 0, "height": 0}
    assert malformed["bounds"] == {"width": 0, "height": 0}
