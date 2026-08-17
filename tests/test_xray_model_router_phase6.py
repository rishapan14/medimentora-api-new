"""Phase 6 — smart model router tests."""

from __future__ import annotations

from app.services.xray.models.router import SmartModelRouter
from app.services.xray.models.registry import SpecializedModelRegistry
from app.services.xray.vision_model import VisionModelRegistry


def test_router_selects_chest_specialist():
  router = SmartModelRouter()
  model, route = router.resolve(body_part="Chest", projection="PA")
  assert route.specialist_key == "chest"
  assert "chest" in model.name.lower() or "torchxrayvision" in model.name.lower()
  assert route.future_backend
  assert route.to_dict()["body_part"] == "Chest"


def test_router_selects_hand_for_wrist():
  router = SmartModelRouter()
  model, route = router.resolve(body_part="Wrist")
  assert route.specialist_key == "hand"
  assert model.is_available()


def test_router_selects_dental():
  _, route = SmartModelRouter().resolve(body_part="Dental")
  assert route.specialist_key == "dental"


def test_router_unknown_falls_back_generic():
  _, route = SmartModelRouter().resolve(body_part="Other")
  assert route.specialist_key == "generic"


def test_router_explicit_preferred():
  model, route = SmartModelRouter().resolve(body_part="Chest", preferred="knee")
  assert route.specialist_key == "knee"
  assert "knee" in model.name.lower()


def test_specialized_registry_lists_all():
  specs = SpecializedModelRegistry.list_specialists()
  keys = {s["key"] for s in specs}
  assert {"chest", "hand", "dental", "spine", "knee", "generic"}.issubset(keys)


def test_vision_registry_get_model_for_case_routes():
  model, route = VisionModelRegistry.get_model_for_case(body_part="Foot", projection="AP")
  assert model.is_available()
  assert route["specialist_key"] == "foot"
  assert route["model_name"]
