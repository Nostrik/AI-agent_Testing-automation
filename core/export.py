"""Экспорт таблиц в Excel (числа хранятся числами)."""
import io

import pandas as pd


def to_xlsx(df: pd.DataFrame, sheet="Прогоны") -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name=sheet)
        ws = xw.sheets[sheet]
        for col in ws.columns:
            width = max(len(str(c.value or "")) for c in col) + 2
            ws.column_dimensions[col[0].column_letter].width = min(max(width, 10), 45)
        ws.freeze_panes = "A2"
    return buf.getvalue()
