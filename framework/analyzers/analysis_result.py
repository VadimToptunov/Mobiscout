"""
Analysis Result Types

Data structures for static analysis results.
"""

from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field


class ScreenCandidate(BaseModel):
    """Potential screen discovered from source code"""
    name: str
    file_path: str
    line_number: int
    composable_name: Optional[str] = None
    route: Optional[str] = None
    parameters: List[str] = Field(default_factory=list)
    ui_elements: List[str] = Field(default_factory=list)


class UIElementCandidate(BaseModel):
    """Potential UI element discovered from source code"""
    id: str
    type: str  # Button, TextField, Text, etc.
    screen: Optional[str] = None
    file_path: str
    line_number: int
    test_tag: Optional[str] = None
    content_description: Optional[str] = None
    text: Optional[str] = None
    modifiers: List[str] = Field(default_factory=list)


class NavigationCandidate(BaseModel):
    """Navigation route discovered from source code"""
    from_screen: Optional[str] = None
    to_screen: str
    route: str
    trigger: Optional[str] = None  # Button/action that triggers navigation
    file_path: str
    line_number: int


class APIEndpointCandidate(BaseModel):
    """API endpoint discovered from source code"""
    method: str  # GET, POST, PUT, DELETE
    path: str
    interface_name: str
    function_name: str
    request_type: Optional[str] = None
    response_type: Optional[str] = None
    file_path: str
    line_number: int


class AnalysisResult(BaseModel):
    """
    Complete static analysis result

    Contains hypotheses about app structure discovered from source code.
    """
    platform: str  # "android" or "ios"
    source_path: str

    screens: List[ScreenCandidate] = Field(default_factory=list)
    ui_elements: List[UIElementCandidate] = Field(default_factory=list)
    navigation: List[NavigationCandidate] = Field(default_factory=list)
    api_endpoints: List[APIEndpointCandidate] = Field(default_factory=list)

    files_analyzed: int = 0
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    metadata: Dict[str, Any] = Field(default_factory=dict)
