"""
Unit tests for STEP 4: Flow-Aware Discovery

Tests flow graph building, edge case detection, and state extraction.
"""

import pytest

from framework.flow import (
    TransitionType,
    EdgeCaseType,
    UIAction,
    FlowNode,
    FlowEdge,
    FlowDiscovery,
    StateExtractor
)


class TestUIAction:
    """Test UIAction dataclass"""

    def test_create_action(self):
        """Test creating UI action"""
        action = UIAction(
            action_type="tap",
            element_id="login_button",
            element_label="Login",
            input_value=None
        )

        assert action.action_type == "tap"
        assert action.element_id == "login_button"
        assert action.element_label == "Login"

    def test_action_with_input(self):
        """Test action with input value"""
        action = UIAction(
            action_type="input",
            element_id="username_field",
            element_label="Username",
            input_value="testuser"
        )

        assert action.input_value == "testuser"


class TestFlowNode:
    """Test FlowNode dataclass"""

    def test_create_node(self):
        """Test creating flow node"""
        node = FlowNode(
            screen_id="login_screen",
            screen_name="LoginScreen",
            elements=[{'id': 'btn1', 'type': 'button'}]
        )

        assert node.screen_id == "login_screen"
        assert node.screen_name == "LoginScreen"
        assert node.visit_count == 0
        assert not node.is_edge_case

    def test_node_properties(self):
        """Test node with properties"""
        node = FlowNode(
            screen_id="test",
            screen_name="Test",
            elements=[],
            properties={'has_list': True, 'item_count': 5}
        )

        assert node.properties['has_list'] is True
        assert node.properties['item_count'] == 5


class TestFlowEdge:
    """Test FlowEdge dataclass"""

    def test_create_edge(self):
        """Test creating flow edge"""
        action = UIAction("tap", "btn1", "Login")
        edge = FlowEdge(
            from_node="login",
            to_node="home",
            action=action,
            transition_type=TransitionType.TAP
        )

        assert edge.from_node == "login"
        assert edge.to_node == "home"
        assert edge.count == 1

    def test_edge_with_api_pattern(self):
        """Test edge with API call pattern"""
        action = UIAction("tap", "btn1", "Submit")
        edge = FlowEdge(
            from_node="form",
            to_node="success",
            action=action,
            transition_type=TransitionType.TAP,
            api_calls_pattern=["/api/submit", "/api/verify"]
        )

        assert len(edge.api_calls_pattern) == 2
        assert "/api/submit" in edge.api_calls_pattern


class TestFlowDiscovery:
    """Test FlowDiscovery engine"""

    def test_discovery_initialization(self):
        """Test discovery engine initialization"""
        discovery = FlowDiscovery()

        assert len(discovery.nodes) == 0
        assert len(discovery.edges) == 0
        assert discovery.current_screen is None

    def test_record_screen(self):
        """Test recording a screen"""
        discovery = FlowDiscovery()

        elements = [
            {'id': 'username', 'type': 'textfield'},
            {'id': 'password', 'type': 'textfield'},
            {'id': 'login_btn', 'type': 'button'}
        ]

        node = discovery.record_screen("login_screen", "LoginScreen", elements)

        assert node.screen_id == "login_screen"
        assert node.screen_name == "LoginScreen"
        assert node.visit_count == 1
        assert "login_screen" in discovery.nodes

    def test_record_screen_multiple_visits(self):
        """Test recording same screen multiple times"""
        discovery = FlowDiscovery()

        elements = [{'id': 'btn1', 'type': 'button'}]

        # First visit
        node1 = discovery.record_screen("test", "Test", elements)
        assert node1.visit_count == 1

        # Second visit
        node2 = discovery.record_screen("test", "Test", elements)
        assert node2.visit_count == 2
        assert node1 is node2  # Same object

    def test_record_transition(self):
        """Test recording screen transition"""
        discovery = FlowDiscovery()

        # Record screens
        discovery.record_screen("login", "Login", [])
        discovery.record_screen("home", "Home", [])

        # Record transition
        action = UIAction("tap", "login_btn", "Login")
        discovery.record_transition("login", "home", action, 500.0)

        assert len(discovery.transitions) == 1
        assert len(discovery.edges) == 1

        edge = discovery.edges[0]
        assert edge.from_node == "login"
        assert edge.to_node == "home"
        assert edge.count == 1

    def test_record_multiple_transitions_same_path(self):
        """Test recording same transition multiple times"""
        discovery = FlowDiscovery()

        discovery.record_screen("a", "A", [])
        discovery.record_screen("b", "B", [])

        action = UIAction("tap", "btn", "Next")

        # First transition
        discovery.record_transition("a", "b", action, 100.0)
        assert discovery.edges[0].count == 1
        assert discovery.edges[0].avg_duration_ms == 100.0

        # Second transition (same path)
        discovery.record_transition("a", "b", action, 200.0)
        assert len(discovery.edges) == 1
        assert discovery.edges[0].count == 2
        assert discovery.edges[0].avg_duration_ms == 150.0  # (100 + 200) / 2

    def test_build_flow_graph(self):
        """Test building complete flow graph"""
        discovery = FlowDiscovery()

        # Create simple flow: A -> B -> C
        discovery.record_screen("a", "A", [])
        discovery.record_screen("b", "B", [])
        discovery.record_screen("c", "C", [])

        action_ab = UIAction("tap", "btn1", "Next")
        action_bc = UIAction("tap", "btn2", "Next")

        discovery.record_transition("a", "b", action_ab, 100.0)
        discovery.record_transition("b", "c", action_bc, 100.0)

        graph = discovery.build_flow_graph()

        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2
        assert "a" in graph.entry_points
        assert "c" in graph.dead_ends

    def test_edge_case_detection_error_screen(self):
        """Test edge case detection for error screens"""
        discovery = FlowDiscovery()

        elements = [{'id': 'error_msg', 'type': 'label'}]
        node = discovery.record_screen("error_screen", "Error Screen", elements)

        assert node.is_edge_case
        assert node.edge_case_type == EdgeCaseType.ERROR_SCREEN

    def test_edge_case_detection_loading_screen(self):
        """Test edge case detection for loading screens"""
        discovery = FlowDiscovery()

        elements = [{'id': 'spinner', 'type': 'activity_indicator'}]
        node = discovery.record_screen("loading", "Loading Screen", elements)

        assert node.is_edge_case
        assert node.edge_case_type == EdgeCaseType.LOADING_SCREEN

    def test_edge_case_detection_permission_dialog(self):
        """Test edge case detection for permission dialogs"""
        discovery = FlowDiscovery()

        elements = [
            {'id': 'allow_btn', 'type': 'button'},
            {'id': 'deny_btn', 'type': 'button'}
        ]
        node = discovery.record_screen("perm", "Permission Dialog", elements)

        assert node.is_edge_case
        assert node.edge_case_type == EdgeCaseType.PERMISSION_DIALOG

    def test_ml_hook_registration(self):
        """Test ML hook registration and execution"""
        discovery = FlowDiscovery()

        # Register custom ML hook
        def custom_hook(screen_data):
            if 'custom' in screen_data['screen_name'].lower():
                return EdgeCaseType.UNEXPECTED_POPUP
            return None

        discovery.register_ml_hook(custom_hook)

        elements = []
        node = discovery.record_screen("custom_dialog", "Custom Dialog", elements)

        assert node.is_edge_case
        assert node.edge_case_type == EdgeCaseType.UNEXPECTED_POPUP

    def test_transition_type_classification(self):
        """Test transition type classification"""
        discovery = FlowDiscovery()

        discovery.record_screen("a", "A", [])
        discovery.record_screen("b", "B", [])

        # Tap transition
        tap_action = UIAction("tap", "btn", "Click")
        discovery.record_transition("a", "b", tap_action, 100.0)
        assert discovery.edges[0].transition_type == TransitionType.TAP

        # Swipe transition
        discovery.record_screen("c", "C", [])
        swipe_action = UIAction("swipe", None, None)
        discovery.record_transition("b", "c", swipe_action, 100.0)
        assert discovery.edges[1].transition_type == TransitionType.SWIPE

    def test_export_to_json(self, tmp_path):
        """Test exporting flow graph to JSON"""
        discovery = FlowDiscovery()

        discovery.record_screen("a", "A", [])
        discovery.record_screen("b", "B", [])

        action = UIAction("tap", "btn", "Next")
        discovery.record_transition("a", "b", action, 100.0)

        output = tmp_path / "flow.json"
        discovery.export_to_json(output)

        assert output.exists()

        import json
        with open(output) as f:
            data = json.load(f)

        assert 'nodes' in data
        assert 'edges' in data
        assert len(data['nodes']) == 2
        assert len(data['edges']) == 1

    def test_export_to_graphviz(self, tmp_path):
        """Test exporting flow graph to Graphviz"""
        discovery = FlowDiscovery()

        discovery.record_screen("a", "A", [])
        discovery.record_screen("b", "B", [])

        action = UIAction("tap", "btn", "Next")
        discovery.record_transition("a", "b", action, 100.0)

        output = tmp_path / "flow.dot"
        discovery.export_to_graphviz(output)

        assert output.exists()

        with open(output) as f:
            content = f.read()

        assert 'digraph FlowGraph' in content
        assert '"a"' in content
        assert '"b"' in content
        assert '->' in content

    def test_loop_detection(self):
        """Test detecting loops in flow graph"""
        discovery = FlowDiscovery()

        # Create loop: A -> B -> C -> A
        discovery.record_screen("a", "A", [])
        discovery.record_screen("b", "B", [])
        discovery.record_screen("c", "C", [])

        action = UIAction("tap", "btn", "Next")

        discovery.record_transition("a", "b", action, 100.0)
        discovery.record_transition("b", "c", action, 100.0)
        discovery.record_transition("c", "a", action, 100.0)

        graph = discovery.build_flow_graph()

        assert len(graph.loops) > 0

    def test_get_critical_paths(self):
        """Test getting critical (most used) paths"""
        discovery = FlowDiscovery()

        discovery.record_screen("a", "A", [])
        discovery.record_screen("b", "B", [])
        discovery.record_screen("c", "C", [])

        action = UIAction("tap", "btn", "Next")

        # Record transitions with different frequencies
        for _ in range(5):
            discovery.record_transition("a", "b", action, 100.0)

        for _ in range(2):
            discovery.record_transition("b", "c", action, 100.0)

        critical_paths = discovery.get_critical_paths()

        assert len(critical_paths) > 0
        # Most critical path should be a->b (5 times)
        assert critical_paths[0] == ["a", "b"]

    def test_generate_test_scenarios(self):
        """Test generating test scenarios from flow"""
        discovery = FlowDiscovery()

        # Normal flow
        discovery.record_screen("login", "Login", [{'id': 'btn', 'type': 'button'}])
        discovery.record_screen("home", "Home", [{'id': 'btn', 'type': 'button'}])

        # Edge case
        discovery.record_screen("error", "Error Screen", [])

        action = UIAction("tap", "btn", "Login")
        discovery.record_transition("login", "home", action, 100.0)

        scenarios = discovery.generate_test_scenarios()

        assert len(scenarios) > 0
        assert any(s['type'] == 'critical_path' for s in scenarios)
        assert any(s['type'] == 'edge_case' for s in scenarios)


class TestStateExtractor:
    """Test StateExtractor"""

    def test_extractor_initialization(self):
        """Test state extractor initialization"""
        discovery = FlowDiscovery()
        extractor = StateExtractor(discovery)

        assert extractor.flow_discovery is discovery

    def test_extract_states(self):
        """Test extracting state machines"""
        discovery = FlowDiscovery()

        discovery.record_screen("login", "Login", [{'id': 'btn', 'type': 'button'}])
        discovery.record_screen("loading", "Loading", [])

        extractor = StateExtractor(discovery)
        states = extractor.extract_states()

        assert len(states) > 0

    def test_extract_screen_states(self):
        """Test extracting states for a screen"""
        discovery = FlowDiscovery()

        node = discovery.record_screen("test", "Test", [])

        extractor = StateExtractor(discovery)
        states = extractor._extract_screen_states(node)

        assert 'initial' in states
        assert 'loading' in states


class TestFlowGraphAnalysis:
    """Test flow graph analysis features"""

    @pytest.fixture
    def complex_flow(self):
        """Create complex flow for testing"""
        discovery = FlowDiscovery()

        # Entry point
        discovery.record_screen("splash", "Splash", [])

        # Main flow
        discovery.record_screen("login", "Login", [{'id': 'btn', 'type': 'button'}])
        discovery.record_screen("home", "Home", [{'id': 'btn', 'type': 'button'}])
        discovery.record_screen("profile", "Profile", [{'id': 'btn', 'type': 'button'}])

        # Edge cases
        discovery.record_screen("error", "Network Error", [])
        discovery.record_screen("loading", "Loading...", [])

        action = UIAction("tap", "btn", "Next")

        # Main flow transitions
        discovery.record_transition("splash", "login", action, 100.0)
        discovery.record_transition("login", "home", action, 200.0)
        discovery.record_transition("home", "profile", action, 150.0)

        # Error transitions
        discovery.record_transition("login", "error", action, 300.0)

        return discovery

    def test_complex_graph_structure(self, complex_flow):
        """Test complex graph structure"""
        graph = complex_flow.build_flow_graph()

        assert len(graph.nodes) == 6
        assert len(graph.edges) == 4
        assert len(graph.entry_points) > 0
        assert len(graph.edge_cases) >= 2  # error and loading

    def test_graph_to_dict(self, complex_flow):
        """Test converting graph to dictionary"""
        graph = complex_flow.build_flow_graph()
        data = graph.to_dict()

        assert 'nodes' in data
        assert 'edges' in data
        assert 'entry_points' in data
        assert 'dead_ends' in data
        assert 'loops' in data
        assert 'edge_case_count' in data


class TestTransitionTypes:
    """Test transition type classification"""

    def test_all_transition_types(self):
        """Test all transition type enums"""
        types = [
            TransitionType.TAP,
            TransitionType.SWIPE,
            TransitionType.INPUT,
            TransitionType.NAVIGATION,
            TransitionType.BACK,
            TransitionType.DEEP_LINK,
            TransitionType.AUTOMATIC
        ]

        assert len(types) == 7
        assert all(isinstance(t, TransitionType) for t in types)


class TestEdgeCaseTypes:
    """Test edge case type classification"""

    def test_all_edge_case_types(self):
        """Test all edge case type enums"""
        types = [
            EdgeCaseType.ERROR_SCREEN,
            EdgeCaseType.LOADING_SCREEN,
            EdgeCaseType.PERMISSION_DIALOG,
            EdgeCaseType.EMPTY_STATE,
            EdgeCaseType.NETWORK_ERROR,
            EdgeCaseType.TIMEOUT,
            EdgeCaseType.UNEXPECTED_POPUP
        ]

        assert len(types) == 7
        assert all(isinstance(t, EdgeCaseType) for t in types)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
