"""Create a truthful copy of the supplied assessment form with candidate details."""
from pathlib import Path
from openpyxl import load_workbook

SOURCE=Path(r"C:\Users\balaj\OneDrive\Desktop\IncuBrix_Assessment_2_Prompt_Based_Video_Editing_Engine_Submission_Form.xlsx")
OUT=Path(__file__).parent / "Assessment2_Gopinath.xlsx"
wb=load_workbook(SOURCE)
ws=wb["1_Your_Details"]
ws["B4"]="Gopinath"
ws["B7"]="Roll No: CB.SC.U4AIE23127"
ws["B14"]="Local project: REPORT.md"
ws["B17"]="OpenAI Codex (see AI_USE.md)"
ws["B18"]="Not measured"
for sheet in ("2_Must_haves","3_Levels","4_Integration"):
    for row in range(5, wb[sheet].max_row+1):
        cell=wb[sheet].cell(row,3)
        if cell.value is None: cell.value="Partial" if sheet=="4_Integration" and row in (6,8,9,10,12) else "No"
ws=wb["5_Metrics"]
for row in range(5,11): ws.cell(row,3).value="Not measured"
wb.save(OUT)
print(OUT)
