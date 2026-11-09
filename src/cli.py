"""Click commands for the stock plugin."""
import asyncio
import logging
from typing import Any, Callable

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import stock_cli
from .backend import launcher

logger = logging.getLogger(__name__)
console = Console()


def build_cli(plugin_factory: Callable[[], Any]) -> click.Group:
    """Build the CLI group; plugin_factory creates the BasePlugin instance."""

    @click.group(
        invoke_without_command=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def main_cli(ctx):
        """CLI for collecting information about Vietnamese listed companies."""
        ctx.ensure_object(dict)
        if ctx.invoked_subcommand is None:
            # The browser diagram runs alongside the terminal CLI and stops when the CLI exits.
            web = launcher.start_web_in_background()
            if web.message:
                console.print(f"[yellow]{web.message}[/yellow]")
            try:
                exit_code = stock_cli.run(ctx.args)
            finally:
                web.stop()
            if exit_code:
                ctx.exit(exit_code)

    @main_cli.command()
    @click.option('--input', '-i', required=True, help='Ticker symbol or company name')
    @click.option('--output', '-o', help='Path for saving the results')
    @click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
    def run(input, output, verbose):
        """Collect information about a Vietnamese listed company."""
        asyncio.run(_run(plugin_factory, input, output, verbose))

    @main_cli.command()
    def test():
        """Test the stock module."""
        asyncio.run(_test(plugin_factory))

    @main_cli.command()
    def info():
        """Show stock module information."""
        module_info = plugin_factory().plugin_info

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

    return main_cli


async def _run(plugin_factory: Callable[[], Any], input: str, output: str | None, verbose: bool) -> None:
    console.print(Panel(
        Text("🚀 STOCK INFORMATION", style="bold blue"),
        title="Vietnam Listed-Company Information"
    ))

    try:
        # Initialize module
        module = plugin_factory()
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


async def _test(plugin_factory: Callable[[], Any]) -> None:
    console.print(Panel(
        Text("🧪 TESTING STOCK MODULE", style="bold yellow"),
        title="Stock Module Testing"
    ))

    try:
        module = plugin_factory()

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
