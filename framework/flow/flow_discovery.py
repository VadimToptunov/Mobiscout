"""
STEP 4: Flow-Aware Discovery - Build flow graphs with ML hooks

Features:
- Screen/action/transition graph building
- State machine extraction
- API call correlation with UI events
- Element property tracking
- ML hooks for edge-case detection
- Flow visualization export
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable


class TransitionType(Enum):
    """Types of screen transitions"""
    TAP = "tap"
    SWIPE = "swipe"
    INPUT = "input"
    NAVIGATION = "navigation"
    BACK = "back"
    DEEP_LINK = "deep_link"
    AUTOMATIC = "automatic"


class EdgeCaseType(Enum):
    """Types of edge cases detected"""
    ERROR_SCREEN = "error_screen"
    LOADING_SCREEN = "loading_screen"
    PERMISSION_DIALOG = "permission_dialog"
    EMPTY_STATE = "empty_state"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    UNEXPECTED_POPUP = "unexpected_popup"


@dataclass
class UIAction:
    """User action on UI"""
    action_type: str
    element_id: Optional[str]
    element_label: Optional[str]
    input_value: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    screen_before: Optional[str] = None
    screen_after: Optional[str] = None


@dataclass
class ScreenTransition:
    """Transition between screens"""
    from_screen: str
    to_screen: str
    action: UIAction
    transition_type: TransitionType
    duration_ms: float
    api_calls: List[Dict[str, Any]] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)


@dataclass
class FlowNode:
    """Node in flow graph (screen)"""
    screen_id: str
    screen_name: str
    elements: List[Dict[str, Any]]
    visit_count: int = 0
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: Optional[datetime] = None
    is_edge_case: bool = False
    edge_case_type: Optional[EdgeCaseType] = None
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowEdge:
    """Edge in flow graph (transition)"""
    from_node: str
    to_node: str
    action: UIAction
    transition_type: TransitionType
    count: int = 1
    avg_duration_ms: float = 0.0
    api_calls_pattern: List[str] = field(default_factory=list)


@dataclass
class FlowGraph:
    """Complete flow graph"""
    nodes: Dict[str, FlowNode]
    edges: List[FlowEdge]
    entry_points: List[str]
    dead_ends: List[str]
    loops: List[List[str]]
    edge_cases: List[FlowNode]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'nodes': {k: {
                'screen_id': v.screen_id,
                'screen_name': v.screen_name,
                'visit_count': v.visit_count,
                'is_edge_case': v.is_edge_case,
                'edge_case_type': v.edge_case_type.value if v.edge_case_type else None,
                'element_count': len(v.elements)
            } for k, v in self.nodes.items()},
            'edges': [{
                'from': e.from_node,
                'to': e.to_node,
                'action': e.action.action_type,
                'type': e.transition_type.value,
                'count': e.count,
                'avg_duration_ms': e.avg_duration_ms
            } for e in self.edges],
            'entry_points': self.entry_points,
            'dead_ends': self.dead_ends,
            'loops': self.loops,
            'edge_case_count': len(self.edge_cases)
        }


class FlowDiscovery:
    """
    STEP 4: Flow-Aware Discovery Engine

    Builds comprehensive flow graph of app navigation including:
    - Screen transitions
    - API call correlation
    - Edge case detection
    - State machine extraction
    """

    def __init__(self):
        self.nodes: Dict[str, FlowNode] = {}
        self.edges: List[FlowEdge] = []
        self.transitions: List[ScreenTransition] = []
        self.current_screen: Optional[str] = None
        self.ml_hooks: List[Callable] = []

    def register_ml_hook(self, hook: Callable):
        """
        Register ML hook for edge case detection

        Args:
            hook: Callable that takes (screen_data) and returns edge_case_type or None
        """
        self.ml_hooks.append(hook)

    def record_screen(self, screen_id: str, screen_name: str, elements: List[Dict[str, Any]]) -> FlowNode:
        """
        Record a discovered screen

        Args:
            screen_id: Unique screen identifier
            screen_name: Human-readable screen name
            elements: List of UI elements on screen

        Returns:
            FlowNode for the screen
        """
        if screen_id in self.nodes:
            # Update existing node
            node = self.nodes[screen_id]
            node.visit_count += 1
            node.last_seen = datetime.now()
        else:
            # Create new node
            node = FlowNode(
                screen_id=screen_id,
                screen_name=screen_name,
                elements=elements,
                visit_count=1
            )

            # Check for edge cases using ML hooks
            for hook in self.ml_hooks:
                edge_case_type = hook({'screen_name': screen_name, 'elements': elements})
                if edge_case_type:
                    node.is_edge_case = True
                    node.edge_case_type = edge_case_type
                    break

            # Simple heuristic edge case detection
            if not node.is_edge_case:
                node.is_edge_case, node.edge_case_type = self._detect_edge_case(screen_name, elements)

            self.nodes[screen_id] = node

        self.current_screen = screen_id
        return node

    def record_transition(
            self,
            from_screen: str,
            to_screen: str,
            action: UIAction,
            duration_ms: float,
            api_calls: List[Dict[str, Any]] = None
    ):
        """
        Record a screen transition

        Args:
            from_screen: Source screen ID
            to_screen: Destination screen ID
            action: UI action that caused transition
            duration_ms: Transition duration
            api_calls: API calls made during transition
        """
        # Determine transition type
        transition_type = self._classify_transition(action, from_screen, to_screen)

        # Record transition
        transition = ScreenTransition(
            from_screen=from_screen,
            to_screen=to_screen,
            action=action,
            transition_type=transition_type,
            duration_ms=duration_ms,
            api_calls=api_calls or []
        )
        self.transitions.append(transition)

        # Update or create edge
        edge = self._find_edge(from_screen, to_screen, action.action_type)
        if edge:
            edge.count += 1
            edge.avg_duration_ms = (edge.avg_duration_ms * (edge.count - 1) + duration_ms) / edge.count
        else:
            api_pattern = [call.get('endpoint', '') for call in (api_calls or [])]
            edge = FlowEdge(
                from_node=from_screen,
                to_node=to_screen,
                action=action,
                transition_type=transition_type,
                avg_duration_ms=duration_ms,
                api_calls_pattern=api_pattern
            )
            self.edges.append(edge)

    def build_flow_graph(self) -> FlowGraph:
        """
        Build complete flow graph from recorded data

        Returns:
            FlowGraph with nodes, edges, and analysis
        """
        # Find entry points (screens with no incoming edges)
        all_target_screens = set(e.to_node for e in self.edges)
        all_source_screens = set(e.from_node for e in self.edges)
        entry_points = list(all_source_screens - all_target_screens)

        # Find dead ends (screens with no outgoing edges)
        dead_ends = list(all_target_screens - all_source_screens)

        # Find loops
        loops = self._detect_loops()

        # Get edge case screens
        edge_cases = [node for node in self.nodes.values() if node.is_edge_case]

        return FlowGraph(
            nodes=self.nodes,
            edges=self.edges,
            entry_points=entry_points,
            dead_ends=dead_ends,
            loops=loops,
            edge_cases=edge_cases
        )

    def export_to_json(self, output_path: Path):
        """Export flow graph to JSON"""
        graph = self.build_flow_graph()
        with open(output_path, 'w') as f:
            json.dump(graph.to_dict(), f, indent=2)

    def export_to_graphviz(self, output_path: Path):
        """Export flow graph to Graphviz DOT format"""
        graph = self.build_flow_graph()

        dot = ['digraph FlowGraph {']
        dot.append('  rankdir=LR;')
        dot.append('  node [shape=box, style=rounded];')
        dot.append('')

        # Nodes
        for node_id, node in graph.nodes.items():
            color = 'red' if node.is_edge_case else 'lightblue'
            label = f"{node.screen_name}\\n({node.visit_count} visits)"
            dot.append(f'  "{node_id}" [label="{label}", fillcolor={color}, style=filled];')

        dot.append('')

        # Edges
        for edge in graph.edges:
            label = f"{edge.action.action_type}\\n({edge.count}x)"
            dot.append(f'  "{edge.from_node}" -> "{edge.to_node}" [label="{label}"];')

        dot.append('}')

        with open(output_path, 'w') as f:
            f.write('\n'.join(dot))

    def _detect_edge_case(self, screen_name: str, elements: List[Dict[str, Any]]) -> Tuple[
        bool, Optional[EdgeCaseType]]:
        """Simple heuristic edge case detection"""
        screen_lower = screen_name.lower()

        # Error screens
        if any(keyword in screen_lower for keyword in ['error', 'failed', 'crash']):
            return True, EdgeCaseType.ERROR_SCREEN

        # Loading screens
        if any(keyword in screen_lower for keyword in ['loading', 'progress', 'wait']):
            return True, EdgeCaseType.LOADING_SCREEN

        # Permission dialogs
        if any(keyword in screen_lower for keyword in ['permission', 'allow', 'grant']):
            return True, EdgeCaseType.PERMISSION_DIALOG

        # Empty states
        if len(elements) < 3:
            return True, EdgeCaseType.EMPTY_STATE

        # Network errors
        if any(keyword in screen_lower for keyword in ['network', 'offline', 'connection']):
            return True, EdgeCaseType.NETWORK_ERROR

        return False, None

    def _classify_transition(self, action: UIAction, from_screen: str, to_screen: str) -> TransitionType:
        """Classify transition type based on action and screens"""
        action_type = action.action_type.lower()

        if 'tap' in action_type or 'click' in action_type:
            return TransitionType.TAP
        elif 'swipe' in action_type:
            return TransitionType.SWIPE
        elif 'input' in action_type or 'type' in action_type:
            return TransitionType.INPUT
        elif 'back' in action_type:
            return TransitionType.BACK
        elif from_screen == to_screen:
            return TransitionType.AUTOMATIC

        return TransitionType.NAVIGATION

    def _find_edge(self, from_node: str, to_node: str, action_type: str) -> Optional[FlowEdge]:
        """Find existing edge"""
        for edge in self.edges:
            if (edge.from_node == from_node and
                    edge.to_node == to_node and
                    edge.action.action_type == action_type):
                return edge
        return None

    def _detect_loops(self) -> List[List[str]]:
        """Detect loops in flow graph using DFS"""
        loops = []
        visited = set()
        path = []

        def dfs(node: str):
            if node in path:
                # Found a loop
                loop_start = path.index(node)
                loops.append(path[loop_start:] + [node])
                return

            if node in visited:
                return

            visited.add(node)
            path.append(node)

            # Visit neighbors
            for edge in self.edges:
                if edge.from_node == node:
                    dfs(edge.to_node)

            path.pop()

        for screen_id in self.nodes.keys():
            dfs(screen_id)

        return loops

    def get_critical_paths(self) -> List[List[str]]:
        """Get critical user paths (most frequently used)"""
        # Build path frequency map
        path_freq = defaultdict(int)

        for transition in self.transitions:
            path_key = f"{transition.from_screen}->{transition.to_screen}"
            path_freq[path_key] += 1

        # Sort by frequency
        sorted_paths = sorted(path_freq.items(), key=lambda x: x[1], reverse=True)

        # Return top 10 paths
        return [path.split('->') for path, _ in sorted_paths[:10]]

    def get_untested_transitions(self) -> List[Tuple[str, str]]:
        """Get screen transitions that haven't been tested"""
        tested = set((e.from_node, e.to_node) for e in self.edges)

        # Generate all possible transitions based on element actions
        possible = set()
        for screen_id, node in self.nodes.items():
            for element in node.elements:
                if element.get('enabled') and element.get('type') in ['button', 'link']:
                    # This element could potentially navigate somewhere
                    # In practice, we'd need to track which elements lead where
                    pass

        return list(possible - tested)

    def generate_test_scenarios(self) -> List[Dict[str, Any]]:
        """Generate test scenarios from flow graph"""
        scenarios = []

        # Critical paths
        for path in self.get_critical_paths():
            scenarios.append({
                'type': 'critical_path',
                'path': path,
                'priority': 'high',
                'description': f"Test critical path: {' -> '.join(path)}"
            })

        # Edge cases
        for node in self.nodes.values():
            if node.is_edge_case:
                scenarios.append({
                    'type': 'edge_case',
                    'screen': node.screen_name,
                    'edge_case_type': node.edge_case_type.value if node.edge_case_type else 'unknown',
                    'priority': 'medium',
                    'description': f"Test edge case: {node.screen_name}"
                })

        # Loops
        for loop in self._detect_loops()[:5]:  # Top 5 loops
            scenarios.append({
                'type': 'loop',
                'path': loop,
                'priority': 'low',
                'description': f"Test loop: {' -> '.join(loop)}"
            })

        return scenarios


class StateExtractor:
    """Extract state machines from flow graph"""

    def __init__(self, flow_discovery: FlowDiscovery):
        self.flow_discovery = flow_discovery

    def extract_states(self) -> List[Dict[str, Any]]:
        """
        Extract state machines from flow graph

        Returns:
            List of state machine definitions
        """
        graph = self.flow_discovery.build_flow_graph()
        state_machines = []

        # Simple heuristic: group related screens
        # In practice, this would use ML to identify logical groupings

        for node in graph.nodes.values():
            states = self._extract_screen_states(node)
            if states:
                state_machines.append({
                    'screen': node.screen_name,
                    'states': states,
                    'transitions': self._extract_state_transitions(node.screen_id)
                })

        return state_machines

    def _extract_screen_states(self, node: FlowNode) -> List[str]:
        """Extract states for a screen"""
        # Common UI states
        states = ['initial', 'loading']

        if node.is_edge_case:
            states.append('error')

        if node.visit_count > 10:
            states.append('loaded')

        return states

    def _extract_state_transitions(self, screen_id: str) -> Dict[str, List[str]]:
        """Extract state transitions"""
        transitions = defaultdict(list)

        # Build transitions from edges
        for edge in self.flow_discovery.edges:
            if edge.from_node == screen_id:
                transitions['loaded'].append(edge.to_node)

        return dict(transitions)
