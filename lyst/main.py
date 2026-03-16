import sys

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from lyst.llm import query
from lyst.config import load_config, save_config, show_config, Config, LLMConfig, DBConfig

app = typer.Typer(help="lyst — plain English to SQL CLI analyst")
config_app = typer.Typer(help="Configure lyst")
app.add_typer(config_app, name="config")

console = Console()

history = []


@config_app.command("set")
def config_set(
    provider: str = typer.Option(..., "--provider", help="LLM provider e.g. anthropic, openai"),
    model: str = typer.Option(..., "--model", help="Model name e.g. anthropic/claude-sonnet-4-20250514"),
    base_url: str = typer.Option(..., "--base-url", help="LLM base URL"),
    stream: bool = typer.Option(False, "--stream", help="Enable streaming"),
    connection: str = typer.Option(..., "--connection", help="Database connection string"),
):
    config = Config(
        llm=LLMConfig(provider=provider, model=model, base_url=base_url, stream=stream),
        db=DBConfig(connection=connection)
    )
    save_config(config)
    rprint("[green]✓ Configuration saved.[/green]")


@config_app.command("llm")
def config_llm(
    provider: str = typer.Option(..., "--provider", help="LLM provider"),
    model: str = typer.Option(..., "--model", help="Model name"),
    base_url: str = typer.Option(..., "--base-url", help="LLM base URL"),
    stream: bool = typer.Option(False, "--stream", help="Enable streaming"),
):
    config = load_config()
    config.llm = LLMConfig(provider=provider, model=model, base_url=base_url, stream=stream)
    save_config(config)
    rprint("[green]✓ LLM configuration saved.[/green]")


@config_app.command("db")
def config_db(
    connection: str = typer.Option(..., "--connection", help="Database connection string"),
):
    config = load_config()
    config.db = DBConfig(connection=connection)
    save_config(config)
    rprint("[green]✓ Database configuration saved.[/green]")


@config_app.command("show")
def config_show():
    show_config()


@app.command()
def ask(
    question: str = typer.Argument(..., help="Plain English question about your data"),
):
    global history

    with console.status("[bold cyan]Thinking...[/bold cyan]"):
        result = query(question, history)

    history = result.history

    if result.success:
        console.print("\n[bold yellow]Generated SQL:[/bold yellow]")
        console.print(f"[dim]{result.sql}[/dim]\n")

        if result.columns and result.rows:
            table = Table(show_header=True, header_style="bold magenta")
            for col in result.columns:
                table.add_column(str(col))
            for row in result.rows:
                table.add_row(*[str(val) for val in row])
            console.print(table)
        else:
            console.print("[dim]No rows returned.[/dim]")

        console.print(f"\n[bold green]Summary:[/bold green] {result.summary}\n")

    else:
        console.print("\n[bold red]Query failed.[/bold red]")
        console.print(f"[dim]LLM correction attempt:[/dim]\n{result.sql}\n")


def run():
    args = sys.argv[1:]
    subcommands = {"chat", "config"}
    if args and args[0] not in subcommands and not args[0].startswith("-"):
        sys.argv.insert(1, "ask")
    app()

if __name__ == "__main__":
    run()