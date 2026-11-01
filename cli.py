"""CLI: tester run / tune / calibrate — для расписания и CI."""
import typer

app = typer.Typer(help="Автотестер ИИ-агентов")


@app.command()
def run(project: str, mode: str = "scripted", repeats: int = 1, label: str = ""):
    """Прогон проекта в выбранном режиме."""
    raise NotImplementedError


@app.command()
def tune(project: str, trials: int = 25):
    """Автоподбор конфигурации агента."""
    raise NotImplementedError


@app.command()
def calibrate(project: str):
    """Проверка судьи на эталонных диалогах."""
    raise NotImplementedError


if __name__ == "__main__":
    app()
