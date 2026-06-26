"""
Plugin system for extensible test generation
"""

from framework.plugins.languages import (
    LanguagePlugin,
    PythonPlugin,
    JavaPlugin,
    KotlinPlugin,
    get_plugin,
    list_languages,
    PLUGINS,
)

__all__ = [
    'LanguagePlugin',
    'PythonPlugin',
    'JavaPlugin',
    'KotlinPlugin',
    'get_plugin',
    'list_languages',
    'PLUGINS',
]
