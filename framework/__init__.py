"""
Mobile Mobiscout & Test Framework

Intelligent Mobile Testing Platform - Scout, Analyze, Automate
"""

__version__ = "1.0.0"
__author__ = "Vadim Toptunov"
__license__ = "MIT"

from framework.model.app_model import AppModel, Screen, Element, Action, APICall

__all__ = [
    "AppModel",
    "Screen",
    "Element",
    "Action",
    "APICall",
]
