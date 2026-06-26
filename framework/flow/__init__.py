"""
Flow analysis package - STEP 4: Flow-Aware Discovery
"""

from framework.flow.flow_discovery import (
    TransitionType,
    EdgeCaseType,
    UIAction,
    ScreenTransition,
    FlowNode,
    FlowEdge,
    FlowGraph,
    FlowDiscovery,
    StateExtractor
)

__all__ = [
    'TransitionType',
    'EdgeCaseType',
    'UIAction',
    'ScreenTransition',
    'FlowNode',
    'FlowEdge',
    'FlowGraph',
    'FlowDiscovery',
    'StateExtractor',
]
