"""
Model Builder

Automatically builds AppModel from observed events and correlations.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any

from framework.config.settings import Settings
from framework.correlation import CorrelationResult, EventCorrelator
from framework.ml.self_learning import SelfLearningCollector
from framework.model.app_model import (
    AppModel,
    AppModelMeta,
    Screen,
    Element,
    ElementType,
    Action,
    ActionType,
    APICall,
    Selector,
    Platform,
    Flow,
    StateMachine,
    StateTransition,
)
from framework.storage.event_store import EventStore

logger = logging.getLogger(__name__)
settings = Settings()


class ModelBuilder:
    """
    Builds AppModel from observed events

    Takes events and correlations and generates a structured AppModel
    that can be used for test generation.
    """

    def __init__(
            self,
            event_store: Optional[EventStore] = None,
            use_ml_classifier: bool = False,
            ml_model_path: Optional[Path] = None,
            enable_self_learning: bool = True,
    ):
        """
        Initialize model builder

        Args:
            event_store: Optional EventStore for loading events
            use_ml_classifier: Enable ML-based element classification
            ml_model_path: Path to trained ML model (optional)
            enable_self_learning: Enable automatic ML data collection
        """
        self.event_store = event_store
        self.use_ml_classifier = use_ml_classifier
        self.ml_classifier = None

        # Initialize self-learning collector
        self.enable_self_learning = enable_self_learning
        self.ml_collector: Optional[SelfLearningCollector] = None

        if enable_self_learning:
            try:
                # Check if user has opted in
                ml_contribute = getattr(settings, 'ml', {}).get('contribute', True)
                self.ml_collector = SelfLearningCollector(opt_in=ml_contribute)
                logger.info("Self-learning ML collector initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize self-learning collector: {e}")
                self.ml_collector = None

        if use_ml_classifier:
            try:
                from framework.ml.element_classifier import ElementClassifier

                self.ml_classifier = ElementClassifier(model_path=ml_model_path)
                logger.info("ML element classifier enabled")
            except ImportError:
                logger.warning("ML dependencies not available, falling back to rule-based classification")
                self.use_ml_classifier = False
            except Exception as e:
                logger.warning(f"Failed to load ML classifier: {e}, falling back to rule-based")
                self.use_ml_classifier = False

    def build_from_session(
            self,
            session_id: str,
            app_version: str,
            platform: Platform = Platform.ANDROID,
            correlation_result: Optional[CorrelationResult] = None,
    ) -> AppModel:
        """
        Build AppModel from a recorded session

        Args:
            session_id: Session ID to build from
            app_version: Application version
            platform: Target platform
            correlation_result: Pre-computed correlations (optional)

        Returns:
            Complete AppModel
        """
        if not self.event_store:
            raise ValueError("EventStore required for session-based model building")

        # Get session info
        sessions = self.event_store.get_sessions()
        session = next((s for s in sessions if s.get("session_id") == session_id), None)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Get correlations if not provided
        if not correlation_result:
            correlator = EventCorrelator(event_store=self.event_store)
            correlation_result = correlator.correlate_session(session_id)

        # Load events
        ui_events = self.event_store.get_events(session_id=session_id, event_type="UIEvent", limit=10000)
        api_events = self.event_store.get_events(session_id=session_id, event_type="NetworkEvent", limit=10000)
        nav_events = self.event_store.get_events(session_id=session_id, event_type="NavigationEvent", limit=10000)

        # Convert to dicts
        ui_dicts = [self._event_to_dict(e) for e in ui_events]
        api_dicts = [self._event_to_dict(e) for e in api_events]
        nav_dicts = [self._event_to_dict(e) for e in nav_events]

        return self.build_from_events(
            app_version=app_version,
            platform=platform,
            session_id=session_id,
            ui_events=ui_dicts,
            api_events=api_dicts,
            nav_events=nav_dicts,
            correlation_result=correlation_result,
        )

    def build_from_events(
            self,
            app_version: str,
            platform: Platform,
            session_id: str,
            ui_events: List[Dict[str, Any]],
            api_events: List[Dict[str, Any]],
            nav_events: List[Dict[str, Any]],
            correlation_result: Optional[CorrelationResult] = None,
    ) -> AppModel:
        """
        Build AppModel from event lists

        Args:
            app_version: Application version
            platform: Target platform
            session_id: Session identifier
            ui_events: UI event dicts
            api_events: API event dicts
            nav_events: Navigation event dicts
            correlation_result: Pre-computed correlations

        Returns:
            Complete AppModel
        """
        # Create metadata
        meta = AppModelMeta(
            app_version=app_version, platform=platform, recorded_at=datetime.now(), session_id=session_id
        )

        # Build screens
        screens = self._build_screens(nav_events, ui_events)

        # Build API calls
        api_calls = self._build_api_calls(api_events)

        # Build flows
        flows = []
        if correlation_result:
            flows = self._build_flows(correlation_result)

        # Build state machine
        state_machine = self._build_state_machine(nav_events, correlation_result)

        # Collect training data for self-learning ML (if enabled)
        model = AppModel(meta=meta, screens=screens, api_calls=api_calls, flows=flows, state_machine=state_machine)

        if self.ml_collector and self.ml_collector.opt_in:
            try:
                # Convert screens to hierarchies and collect training data
                for screen_name, screen in screens.items():
                    hierarchy = self._screen_to_hierarchy(screen)
                    self.ml_collector.collect_from_hierarchy(
                        hierarchy=hierarchy,
                        platform=platform.value,
                        confidence=0.9 if self.use_ml_classifier else 0.7,  # Higher confidence with ML
                        source="ml-predicted" if self.use_ml_classifier else "rule-based"
                    )
                logger.debug(f"Collected {len(screens)} screens for self-learning")
            except Exception as e:
                logger.warning(f"Failed to collect self-learning data: {e}")

        return model

    def _build_screens(self, nav_events: List[Dict[str, Any]], ui_events: List[Dict[str, Any]]) -> Dict[str, Screen]:
        """
        Build Screen models from navigation and UI events

        Infers screens from navigation events and populates them with
        elements from UI events.
        """
        screens: Dict[str, Screen] = {}

        # Get unique screens from navigation events
        screen_names: Set[str] = set()
        for nav in nav_events:
            if "toScreen" in nav:
                screen_names.add(nav["toScreen"])
            if "fromScreen" in nav:
                screen_names.add(nav["fromScreen"])

        # Also get screens from UI events
        for ui in ui_events:
            if "screen" in ui:
                screen_names.add(ui["screen"])

        # Build each screen
        for screen_name in screen_names:
            if screen_name and screen_name != "unknown":
                # Get UI events for this screen
                screen_ui_events = [ui for ui in ui_events if ui.get("screen") == screen_name]

                # Extract elements
                elements = self._extract_elements(screen_ui_events)

                # Extract actions
                actions = self._extract_actions(screen_ui_events)

                screen = Screen(name=screen_name, class_name=None, elements=list(elements.values()), actions=actions)

                screens[screen_name] = screen

        return screens

    def _extract_elements(self, ui_events: List[Dict[str, Any]]) -> Dict[str, Element]:
        """
        Extract UI elements from UI events

        Each unique element that was interacted with becomes an Element.
        Uses ML classifier if enabled, falls back to rule-based inference.
        """
        elements: Dict[str, Element] = {}

        for event in ui_events:
            element_id = event.get("elementId")
            if not element_id:
                continue

            if element_id in elements:
                continue  # Already extracted

            # Determine element type (ML or rule-based)
            if self.use_ml_classifier and self.ml_classifier and self.ml_classifier.trained:
                try:
                    element_type, confidence = self._classify_element_ml(event)
                    logger.debug(f"ML classified {element_id} as {element_type} (confidence: {confidence:.2f})")

                    # Fall back to rule-based if confidence is too low
                    if confidence < 0.5:
                        logger.debug(f"Low ML confidence ({confidence:.2f}), using rule-based fallback")
                        element_type = self._infer_element_type(event.get("action", "tap"), event)
                except Exception as e:
                    logger.warning(f"ML classification failed: {e}, falling back to rules")
                    element_type = self._infer_element_type(event.get("action", "tap"), event)
            else:
                # Rule-based inference
                element_type = self._infer_element_type(event.get("action", "tap"), event)

            # Build selector
            selector = self._build_selector(event)

            element = Element(
                id=element_id,
                type=element_type,
                selector=selector,
                text=event.get("text") or event.get("contentDescription"),
                visible_when=None,
            )

            elements[element_id] = element

        return elements

    def _classify_element_ml(self, event: Dict[str, Any]) -> tuple[ElementType, float]:
        """
        Classify element using ML model.

        Args:
            event: UI event with element attributes

        Returns:
            (element_type, confidence)
        """
        if not self.ml_classifier:
            raise ValueError("ML classifier not initialized")

        # Prepare element data for ML classifier
        element_data = {
            "clickable": event.get("clickable", False),
            "focusable": event.get("focusable", False),
            "enabled": event.get("enabled", True),
            "checkable": event.get("checkable", False),
            "scrollable": event.get("scrollable", False),
            "selected": event.get("selected", False),
            "password": event.get("password", False),
            "text": event.get("text", ""),
            "content_desc": event.get("contentDescription", ""),
            "resource_id": event.get("resourceId", ""),
            "class": event.get("className", ""),
            "bounds": {"width": event.get("width", 0), "height": event.get("height", 0)},
        }

        return self.ml_classifier.predict(element_data)

    def _infer_element_type(self, action: str, event: Dict[str, Any]) -> ElementType:
        """Infer element type from action and event data"""

        if action == "input":
            return ElementType.INPUT  # Use INPUT instead of TEXT_INPUT
        elif action == "swipe":
            return ElementType.LIST  # Swipeable elements are typically lists
        elif action == "tap":
            text = event.get("text", "").lower()
            if "button" in text or "btn" in text:
                return ElementType.BUTTON
            else:
                return ElementType.BUTTON  # Default for taps
        else:
            return ElementType.GENERIC

    def _build_selector_from_enhanced(self, event: Dict[str, Any], all_selectors: Dict[str, Any]) -> Selector:
        """
        Build Selector from enhanced allSelectors JSON

        allSelectors format (from SelectorBuilder):
        {
            "xpath_id": "//*[@id='login']",
            "xpath_name": "//input[@name='username']",
            "xpath_text": "//button[text()='Login']",
            "xpath_indexed": "//LinearLayout[1]/Button[2]",
            "css_id": "#login",
            "css_class": "button.primary",
            "resourceId": "com.app:id/login",
            "testTag": "login_button",
            "contentDescription": "Login Button",
            ...
        }
        """
        from framework.model.app_model import SelectorStability

        # Extract primary selectors
        android_primary = None
        ios_primary = None
        test_id = None
        xpath = None
        android_fallbacks = []
        ios_fallbacks = []
        stability = SelectorStability.UNKNOWN

        # Priority for Android:
        # 1. resourceId (highest stability)
        # 2. testTag
        # 3. contentDescription
        # 4. xpath_id
        # 5. xpath_text/xpath_name (medium stability)
        # 6. xpath_indexed (low stability)

        resource_id = all_selectors.get("resourceId")
        test_tag = all_selectors.get("testTag")
        content_desc = all_selectors.get("contentDescription")
        xpath_id = all_selectors.get("xpath_id")
        xpath_name = all_selectors.get("xpath_name")
        xpath_text = all_selectors.get("xpath_text")
        xpath_class = all_selectors.get("xpath_class")
        xpath_indexed = all_selectors.get("xpath_indexed")

        if resource_id:
            android_primary = f"id:{resource_id}"
            stability = SelectorStability.HIGH
            # Add fallbacks
            if test_tag:
                android_fallbacks.append(f"accessibility:{test_tag}")
            if content_desc:
                android_fallbacks.append(f"accessibility:{content_desc}")
            if xpath_id:
                android_fallbacks.append(f"xpath:{xpath_id}")
            if xpath_text:
                android_fallbacks.append(f"xpath:{xpath_text}")
        elif test_tag:
            android_primary = f"accessibility:{test_tag}"
            test_id = test_tag
            stability = SelectorStability.HIGH
            if content_desc and content_desc != test_tag:
                android_fallbacks.append(f"accessibility:{content_desc}")
            if xpath_text:
                android_fallbacks.append(f"xpath:{xpath_text}")
            if xpath_name:
                android_fallbacks.append(f"xpath:{xpath_name}")
        elif content_desc:
            android_primary = f"accessibility:{content_desc}"
            stability = SelectorStability.MEDIUM
            if xpath_text:
                android_fallbacks.append(f"xpath:{xpath_text}")
            if xpath_id:
                android_fallbacks.append(f"xpath:{xpath_id}")
        elif xpath_id:
            android_primary = f"xpath:{xpath_id}"
            stability = SelectorStability.MEDIUM
            if xpath_text:
                android_fallbacks.append(f"xpath:{xpath_text}")
            if xpath_name:
                android_fallbacks.append(f"xpath:{xpath_name}")
        elif xpath_text:
            android_primary = f"xpath:{xpath_text}"
            stability = SelectorStability.MEDIUM
            if xpath_name:
                android_fallbacks.append(f"xpath:{xpath_name}")
            if xpath_class:
                android_fallbacks.append(f"xpath:{xpath_class}")
        elif xpath_indexed:
            android_primary = f"xpath:{xpath_indexed}"
            stability = SelectorStability.LOW

        # For iOS, similar priority
        accessibility_id = all_selectors.get("accessibilityIdentifier")
        accessibility_label = all_selectors.get("accessibilityLabel")
        text_content = all_selectors.get("text")

        if accessibility_id:
            ios_primary = f"accessibility:{accessibility_id}"
            if not test_id:
                test_id = accessibility_id
            if stability == SelectorStability.UNKNOWN:
                stability = SelectorStability.HIGH
            # Add fallbacks
            if accessibility_label:
                ios_fallbacks.append(f"accessibility:{accessibility_label}")
            if text_content:
                ios_fallbacks.append(f"text:{text_content}")
            if xpath_text:
                ios_fallbacks.append(f"xpath:{xpath_text}")
        elif accessibility_label:
            ios_primary = f"accessibility:{accessibility_label}"
            if stability == SelectorStability.UNKNOWN:
                stability = SelectorStability.MEDIUM
            if text_content and text_content != accessibility_label:
                ios_fallbacks.append(f"text:{text_content}")
            if xpath_text:
                ios_fallbacks.append(f"xpath:{xpath_text}")
        elif text_content:
            ios_primary = f"text:{text_content}"
            if stability == SelectorStability.UNKNOWN:
                stability = SelectorStability.MEDIUM
            if xpath_text:
                ios_fallbacks.append(f"xpath:{xpath_text}")
        elif xpath_indexed:
            ios_primary = f"xpath:{xpath_indexed}"
            if stability == SelectorStability.UNKNOWN:
                stability = SelectorStability.LOW

        # If we have XPath in original event, use it as ultimate fallback
        if event.get("xpath"):
            xpath = event.get("xpath")
            if not android_primary:
                android_primary = f"xpath:{xpath}"
            if not ios_primary:
                ios_primary = f"xpath:{xpath}"

        return Selector(
            android=android_primary,
            ios=ios_primary,
            test_id=test_id,
            xpath=xpath,
            android_fallback=android_fallbacks,
            ios_fallback=ios_fallbacks,
            stability=stability,
        )

    def _build_selector(self, event: Dict[str, Any]) -> Selector:
        """
        Build selector from event data

        If event contains 'allSelectors' JSON (from enhanced selector generation),
            parse and use those strategies. Otherwise, fall back to legacy logic.
        """
        import json

        # Check if event has enhanced selectors
        all_selectors_json = event.get("allSelectors")
        if all_selectors_json:
            try:
                all_selectors = (
                    json.loads(all_selectors_json) if isinstance(all_selectors_json, str) else all_selectors_json
                )
                return self._build_selector_from_enhanced(event, all_selectors)
            except (json.JSONDecodeError, Exception) as e:
                print(f"[ModelBuilder] Failed to parse allSelectors JSON: {e}")
                # Fall through to legacy logic

        # Legacy selector building
        element_id = event.get("elementId")
        text = event.get("text")
        content_desc = event.get("contentDescription")
        class_name = event.get("className")

        # Build platform-specific selectors
        android_selector = {}
        ios_selector = {}

        if element_id:
            # Assume element_id is a test tag
            android_selector["test_id"] = element_id
            ios_selector["accessibility_id"] = element_id

        if content_desc:
            android_selector["content_desc"] = content_desc
            ios_selector["accessibility_id"] = content_desc

        # Fallback to text
        if text and not android_selector:
            android_selector["text"] = text
            ios_selector["label"] = text

        # Very weak fallback - XPath by class
        if class_name and not android_selector:
            android_selector["xpath"] = f"//{class_name}"
            ios_selector["xpath"] = f"//{class_name}"

        # Build selector with fallbacks
        android_str = None
        ios_str = None
        test_id_str = None
        xpath_str = None
        android_fallbacks = []
        ios_fallbacks = []

        if element_id:
            test_id_str = element_id
            # Add fallbacks
            if "text" in android_selector:
                android_fallbacks.append(android_selector["text"])
            if "xpath" in android_selector:
                android_fallbacks.append(android_selector["xpath"])

        if "resource_id" in android_selector:
            android_str = android_selector["resource_id"]
        elif "text" in android_selector:
            android_str = android_selector["text"]
        elif "xpath" in android_selector:
            android_str = android_selector["xpath"]

        if "accessibility_id" in ios_selector:
            ios_str = ios_selector["accessibility_id"]
        elif "label" in ios_selector:
            ios_str = ios_selector["label"]
        elif "xpath" in ios_selector:
            ios_str = ios_selector["xpath"]

        if "xpath" in android_selector and not test_id_str:
            xpath_str = android_selector["xpath"]

        return Selector(
            android=android_str,
            ios=ios_str,
            test_id=test_id_str,
            xpath=xpath_str,
            android_fallback=android_fallbacks,
            ios_fallback=ios_fallbacks,
        )

    def _extract_actions(self, ui_events: List[Dict[str, Any]]) -> List[Action]:
        """
        Extract actions from UI events

        Groups events by element to create actions.
        """
        actions: List[Action] = []
        seen_actions: Set[str] = set()

        for event in ui_events:
            element_id = event.get("elementId")
            if not element_id:
                continue  # Skip events without element ID

            action_type_str = event.get("action", "tap")

            # Map string to ActionType
            action_type = self._map_action_type(action_type_str)

            # Create unique key
            action_key = f"{element_id}_{action_type.value}"

            if action_key in seen_actions:
                continue

            seen_actions.add(action_key)

            action = Action(
                name=f"{action_type.value}_{element_id}",
                ui_action=action_type,
                element_id=element_id,
                api_call=None,
                validation=None,
            )

            actions.append(action)

        return actions

    def _map_action_type(self, action_str: str) -> ActionType:
        """Map action string to ActionType enum"""
        mapping = {
            "tap": ActionType.TAP,
            "click": ActionType.TAP,
            "input": ActionType.INPUT,
            "swipe": ActionType.SWIPE,
            "scroll": ActionType.SWIPE,  # Map scroll to SWIPE
            "long_press": ActionType.LONG_PRESS,
            "navigate": ActionType.TAP,  # Map navigate to TAP (navigation trigger)
        }
        return mapping.get(action_str.lower(), ActionType.TAP)

    def _build_api_calls(self, api_events: List[Dict[str, Any]]) -> Dict[str, APICall]:
        """
        Build APICall models from network events

        Each unique endpoint becomes an APICall definition.
        """
        api_calls: Dict[str, APICall] = {}

        for event in api_events:
            method = event.get("method", "GET")
            url = event.get("url", "")

            # Extract endpoint path
            endpoint = self._extract_endpoint(url)

            # Create unique key
            key = f"{method}_{endpoint}"

            if key in api_calls:
                continue  # Already processed

            # Extract request/response schemas (simplified)
            request_body = event.get("requestBody")
            response_body = event.get("responseBody")

            schema = {}
            if isinstance(request_body, dict):
                schema["request"] = request_body
            if isinstance(response_body, dict):
                schema["response"] = response_body

            api_call = APICall(
                name=key,
                method=method.upper(),
                endpoint=endpoint,
                request_schema=schema,
                triggers_state_change=None
            )

            api_calls[key] = api_call

        return api_calls

    def _extract_endpoint(self, url: str) -> str:
        """Extract endpoint path from full URL"""
        if not url:
            return "/"

        # Remove protocol and domain
        if "://" in url:
            url = url.split("://", 1)[1]

        if "/" in url:
            path = "/" + "/".join(url.split("/")[1:])
        else:
            path = "/"

        # Remove query parameters
        if "?" in path:
            path = path.split("?")[0]

        return path

    def _build_flows(self, correlation_result: CorrelationResult) -> List[Flow]:
        """
        Build Flow models from correlation results

        Each full flow correlation becomes a Flow.
        """
        flows: List[Flow] = []

        for full_flow in correlation_result.full_flows:
            steps = []

            # Add UI step
            ui_corr = full_flow.ui_correlation
            steps.append(
                {
                    "type": "ui_action",
                    "screen": ui_corr.ui_screen,
                    "action": ui_corr.ui_event_type,
                    "element": ui_corr.ui_element_id,
                }
            )

            # Add API steps
            for api_call in ui_corr.api_calls:
                steps.append(
                    {"type": "api_call", "method": api_call.get("method"), "endpoint": api_call.get("endpoint")}
                )

            # Add navigation steps
            for nav_corr in full_flow.api_navigation_correlations:
                steps.append(
                    {
                        "type": "navigation",
                        "from": nav_corr.from_screen,
                        "to": nav_corr.to_screen,
                        "condition": nav_corr.condition,
                    }
                )

            flow = Flow(name=full_flow.flow_name or full_flow.flow_id, description=full_flow.description, steps=steps)

            flows.append(flow)

        return flows

    def _build_state_machine(
            self, nav_events: List[Dict[str, Any]], correlation_result: Optional[CorrelationResult]
    ) -> Optional[StateMachine]:
        """
        Build state machine from navigation events

        Creates states for each screen and transitions between them.
        """
        states: List[str] = []
        transitions: List[StateTransition] = []

        # Get unique screens
        screen_names: Set[str] = set()
        for nav in nav_events:
            if "toScreen" in nav:
                screen_names.add(nav["toScreen"])
            if "fromScreen" in nav:
                screen_names.add(nav["fromScreen"])

        # Create states (just list of state names)
        for screen in screen_names:
            if screen and screen != "unknown":
                states.append(screen)

        # Create transitions
        seen_transitions: Set[str] = set()

        for nav in nav_events:
            from_screen = nav.get("fromScreen")
            to_screen = nav.get("toScreen")

            if not from_screen or not to_screen:
                continue

            trans_key = f"{from_screen}_to_{to_screen}"
            if trans_key in seen_transitions:
                continue

            seen_transitions.add(trans_key)

            # Try to find trigger from correlations
            trigger = None
            if correlation_result:
                for nav_corr in correlation_result.api_to_navigation:
                    if nav_corr.from_screen == from_screen and nav_corr.to_screen == to_screen:
                        trigger = f"api_{nav_corr.api_method}_{nav_corr.api_endpoint}"
                        break

            transition = StateTransition(
                from_state=from_screen, to_state=to_screen, trigger=trigger or "user_action", condition=None
            )

            transitions.append(transition)

        # Determine initial state (first screen visited)
        initial_state = None
        if nav_events:
            first_nav = nav_events[0]
            initial_state = first_nav.get("toScreen") or first_nav.get("fromScreen")

        if not states:
            return None

        return StateMachine(states=states, transitions=transitions, initial_state=initial_state)

    def _event_to_dict(self, event: Any) -> Dict[str, Any]:
        """Convert event object to dict"""
        if isinstance(event, dict):
            return event

        if hasattr(event, "keys"):
            return {key: event[key] for key in event.keys()}

        if hasattr(event, "model_dump"):
            return event.model_dump()

        return {}

    def _screen_to_hierarchy(self, screen: Screen) -> Dict[str, Any]:
        """
        Convert Screen model to hierarchy dict for self-learning.

        Args:
            screen: Screen model

        Returns:
            Hierarchy dict compatible with SelfLearningCollector
        """
        hierarchy = {
            "class": screen.class_name or "Screen",
            "name": screen.name,
            "children": []
        }

        # Convert elements to hierarchy nodes
        for element in screen.elements:
            element_node = {
                "class": element.type.value if hasattr(element.type, 'value') else str(element.type),
                "text": "",  # Don't include actual text for privacy
                "clickable": element.clickable,
                "focusable": element.focusable,
                "enabled": True,  # Assume enabled if interacted with
                "bounds": {
                    "width": 100,  # Placeholder
                    "height": 50  # Placeholder
                },
                "element_type": element.type.value if hasattr(element.type, 'value') else str(element.type),
                "children": []
            }

            # Add selector info as attributes
            if element.selector:
                if element.selector.id:
                    element_node["has_id"] = True
                if element.selector.accessibility_id:
                    element_node["has_accessibility_id"] = True
                if element.selector.text:
                    element_node["has_text"] = True
                    element_node["text_length"] = len(element.selector.text)

            hierarchy["children"].append(element_node)

        return hierarchy
