"""
Module metadata and configuration for Template Module
"""
from typing import Dict, Any, List
from lkwolfSAI_ablilities.module_interface import ModuleInfo, ModuleStatus

def get_module_info() -> ModuleInfo:
    """Return module metadata"""
    return ModuleInfo(
        name="template_module",
        version="1.0.0",
        description="Template module for lkwolfSAI ecosystem",
        author="lkwolfSAI Team",
        status=ModuleStatus.EXPERIMENTAL,
        dependencies=[
            "click>=8.0.0",
            "rich>=13.0.0",
            "asyncio",
            "logging"
        ],
        supported_languages=["en", "vi"],
        required_services=["database"],  # database, redis, ollama, etc.
        config_schema={
            "MODULE_SETTING": {
                "type": "string",
                "default": "default_value",
                "description": "Example module setting"
            },
            "MODULE_TIMEOUT": {
                "type": "integer",
                "default": 30,
                "description": "Module timeout in seconds"
            }
        },
        commands=[
            {
                "name": "run",
                "description": "Run the template module",
                "options": [
                    {
                        "name": "--input",
                        "type": "string",
                        "required": True,
                        "help": "Input parameter"
                    },
                    {
                        "name": "--output",
                        "type": "string",
                        "required": False,
                        "help": "Output parameter"
                    }
                ]
            },
            {
                "name": "test",
                "description": "Test the template module",
                "options": []
            }
        ]
    )
