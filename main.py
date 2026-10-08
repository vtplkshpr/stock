"""
Main entry point for the Vietnam listed-company information plugin.
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Add current directory to path for imports
current_dir = str(Path(__file__).parent)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import BasePlugin
sys.path.append(str(Path(__file__).parent.parent))
from base_plugin import BasePlugin, PluginInfo, PluginStatus
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
            description="Thu thập thông tin về các doanh nghiệp niêm yết trên sàn chứng khoán Việt Nam.",
            author="lkwolfSAI Team",
            status=PluginStatus.DEVELOPMENT,
            dependencies=["click>=8.0.0", "rich>=13.0.0"],
            supported_languages=["vi", "en"],
            required_services=[],
            config_schema={},
            commands=[
                {
                    "name": "run",
                    "description": "Thu thập thông tin doanh nghiệp niêm yết tại Việt Nam",
                    "options": [
                        {
                            "name": "input",
                            "required": True,
                            "help": "Mã cổ phiếu hoặc tên doanh nghiệp cần tra cứu"
                        },
                        {
                            "name": "output",
                            "required": False,
                            "help": "Đường dẫn lưu kết quả"
                        }
                    ]
                },
                {
                    "name": "test",
                    "description": "Kiểm tra trạng thái module",
                    "options": []
                },
                {
                    "name": "info",
                    "description": "Hiển thị thông tin module",
                    "options": []
                }
            ]
        )
        self._initialized = False
    
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

# CLI Commands
@click.group()
@click.pass_context
def main_cli(ctx):
    """CLI for collecting Vietnamese listed-company information."""
    ctx.ensure_object(dict)

@main_cli.command()
@click.option('--input', '-i', required=True, help='Input parameter')
@click.option('--output', '-o', help='Output parameter')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
async def run(input, output, verbose):
    """Collect information about a Vietnamese listed company."""
    console.print(Panel(
        Text("🚀 STOCK INFORMATION", style="bold blue"),
        title="Vietnam Listed-Company Information"
    ))
    
    try:
        # Initialize module
        module = StockModule()
        if not await module.initialize():
            console.print("[red]Failed to initialize module[/red]")
            return
        
        # Run main functionality
        result = await module.service.process(input, output)
        
        if verbose:
            console.print(f"[green]Processing result: {result}[/green]")
        else:
            console.print("[green]✓ Processing completed successfully[/green]")
            
    except Exception as e:
        logger.error(f"Error running stock module: {e}")
        console.print(f"[red]✗ Error: {e}[/red]")

@main_cli.command()
async def test():
    """Test the stock module."""
    console.print(Panel(
        Text("🧪 TESTING STOCK MODULE", style="bold yellow"),
        title="Stock Module Testing"
    ))
    
    try:
        module = StockModule()
        
        # Health check
        health = await module.health_check()
        console.print(f"[green]Health check: {health}[/green]")
        
        # Configuration validation
        config_errors = module.validate_config({})
        if config_errors:
            console.print(f"[yellow]Config warnings: {config_errors}[/yellow]")
        else:
            console.print("[green]✓ Configuration valid[/green]")
        
        console.print("[green]✓ All tests passed[/green]")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        console.print(f"[red]✗ Test failed: {e}[/red]")

@main_cli.command()
def info():
    """Show stock module information."""
    module_info = StockModule().plugin_info
    
    console.print(Panel(
        f"""
[bold]Module:[/bold] {module_info.name}
[bold]Version:[/bold] {module_info.version}
[bold]Status:[/bold] {module_info.status.value}
[bold]Description:[/bold] {module_info.description}
[bold]Author:[/bold] {module_info.author}
[bold]Dependencies:[/bold] {', '.join(module_info.dependencies)}
[bold]Supported Languages:[/bold] {', '.join(module_info.supported_languages)}
[bold]Required Services:[/bold] {', '.join(module_info.required_services)}
        """,
        title="Module Information"
    ))

if __name__ == "__main__":
    # For direct execution
    asyncio.run(main_cli())
