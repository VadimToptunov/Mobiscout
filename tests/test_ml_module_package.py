"""ml_module.py was decomposed into a package (ml_base + one module per model +
the MLModule orchestrator). The behavioural coverage lives in test_ml_module.py
(it imports via the package facade, so it already exercises the split); these
just pin the new layout: the granular modules are importable and the historical
paths re-export the very same objects.
"""

import framework.ml.element_scorer as es_mod
import framework.ml.ml_base as base_mod
import framework.ml.ml_module as mm_mod
import framework.ml.next_step_recommender as nsr_mod
import framework.ml.selector_predictor as sp_mod


def test_granular_modules_expose_their_class():
    assert base_mod.MLModel is not None
    assert sp_mod.SelectorPredictor is not None
    assert nsr_mod.NextStepRecommender is not None
    assert es_mod.ElementScorer is not None


def test_ml_module_reexports_the_same_objects():
    # The historical import path must resolve to the identical classes now living
    # in the granular modules (not copies).
    assert mm_mod.SelectorPredictor is sp_mod.SelectorPredictor
    assert mm_mod.NextStepRecommender is nsr_mod.NextStepRecommender
    assert mm_mod.ElementScorer is es_mod.ElementScorer
    assert mm_mod.MLModel is base_mod.MLModel
    assert mm_mod.MLBackend is base_mod.MLBackend
    assert mm_mod.ModelType is base_mod.ModelType


def test_orchestrator_wires_the_three_models():
    mlv = mm_mod.MLModule()
    kinds = {k.value for k in mlv.models}
    assert kinds == {"selector_predictor", "step_recommender", "element_scorer"}
