"""
Main entry point for the Vietnam listed-company information plugin.
"""
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List
from rich.console import Console

# Add current directory to path for imports
current_dir = str(Path(__file__).parent)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import BasePlugin
sys.path.append(str(Path(__file__).parent.parent))
from base_plugin import BasePlugin, PluginInfo, PluginStatus
from src.cli import build_cli
# Try to import optional dependencies
try:
    from .core.module_service import ModuleService
    from .utils.config import ModuleConfig
    HAS_FULL_DEPS = True
except ImportError:
    HAS_FULL_DEPS = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
console = Console()


class StockModule(BasePlugin):
    """Plugin for collecting information about companies listed in Vietnam."""
    
    def __init__(self):
        self._plugin_info = PluginInfo(
            name="stock",
            version="1.0.0",
            description="Collect information about companies listed on Vietnamese stock exchanges.",
            author="lkwolfSAI Team",
            status=PluginStatus.DEVELOPMENT,
            dependencies=["click>=8.0.0", "rich>=13.0.0"],
            supported_languages=["vi", "en"],
            required_services=[],
            config_schema={},
            commands=[
                {
                    "name": "run",
                    "description": "Collect information about Vietnamese listed companies",
                    "options": [
                        {
                            "name": "input",
                            "required": True,
                            "help": "Ticker symbol or company name to look up"
                        },
                        {
                            "name": "output",
                            "required": False,
                            "help": "Path for saving the results"
                        }
                    ]
                },
                {
                    "name": "test",
                    "description": "Check the module status",
                    "options": []
                },
                {
                    "name": "info",
                    "description": "Display module information",
                    "options": []
                }
            ]
        )
        self._initialized = False
        self.service = None
        self.config = None
    
    @property
    def plugin_info(self) -> PluginInfo:
        """Return plugin metadata"""
        return self._plugin_info
    
    async def initialize(self) -> bool:
        """Initialize module"""
        try:
            console.print(f"[green]Initializing {self.plugin_info.name}...[/green]")
            
            # Initialize services if available
            if HAS_FULL_DEPS:
                try:
                    self.service = ModuleService()
                    self.config = ModuleConfig()
                    console.print("✓ Full services initialized")
                except Exception as e:
                    console.print(f"Warning: Some services not available: {e}")
                    self.service = None
                    self.config = None
            else:
                console.print("✓ Running in minimal mode")
            
            # Initialize other services if available
            if self.service:
                await self.service.initialize()
            
            self._initialized = True
            console.print(f"[green]✓ {self.plugin_info.name} initialized successfully[/green]")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize {self.plugin_info.name}: {e}")
            console.print(f"[red]✗ Failed to initialize {self.plugin_info.name}[/red]")
            return False
    
    async def cleanup(self) -> bool:
        """Cleanup module resources"""
        try:
            console.print(f"[yellow]Cleaning up {self.plugin_info.name}...[/yellow]")
            if self.service:
                await self.service.cleanup()
            self._initialized = False
            console.print(f"[green]✓ {self.plugin_info.name} cleaned up successfully[/green]")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup {self.plugin_info.name}: {e}")
            return False
    
    def get_cli_commands(self) -> List[Any]:
        """Return Click commands for CLI integration"""
        return [main_cli]
    
    async def health_check(self) -> Dict[str, Any]:
        """Return plugin health status"""
        health_status = {
            "plugin": self.plugin_info.name,
            "version": self.plugin_info.version,
            "status": "healthy" if self._initialized else "not_initialized",
            "services": {}
        }
        
        if self.service:
            try:
                health_status["services"]["main_service"] = "healthy"
            except Exception:
                health_status["services"]["main_service"] = "unhealthy"
        else:
            health_status["services"]["main_service"] = "not_available"
        
        return health_status
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate plugin configuration"""
        errors = []
        
        # Validate required settings
        for setting, schema in self.plugin_info.config_schema.items():
            if setting not in config:
                errors.append(f"Missing required setting: {setting}")
        
        return errors

main_cli = build_cli(StockModule)

if __name__ == "__main__":
    main_cli()
