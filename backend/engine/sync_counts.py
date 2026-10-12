"""The "loaded" number of a synchronisation run, as a Figure (count) with its breakdown."""

from engine.figure import Figure, FigureItem


def sync_counts_figure(new: int, updated: int, skipped_duplicates: int) -> Figure:
    """value = new + updated; records skipped as already known are named in the note, not in the sum."""
    note = (
        f"Новых записей {new}, обновлено {updated}, "
        f"пропущено как дубли (уже были, без изменений): {skipped_duplicates}."
    )
    return Figure(
        value=new + updated,
        unit="count",
        breakdown=(
            FigureItem("Новых записей", new, "count"),
            FigureItem("Обновлено", updated, "count"),
        ),
        source=("vetmanager",),
        note=note,
    )
