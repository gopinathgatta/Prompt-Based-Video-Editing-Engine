from pathlib import Path
from openpyxl import load_workbook

source=Path(r"C:\Users\balaj\Downloads\IncuBrix_Assessment_2_Prompt_Based_Video_Editing_Engine_Submission_Form.xlsx")
out=Path(__file__).parent/"Assessment2_Gopinath.xlsx"
repo="https://github.com/gopinathgatta/Prompt-Based-Video-Editing-Engine"
base=repo+"/blob/main/"
wb=load_workbook(source)
details=wb["1_Your_Details"]
details["B4"]="Gopinath";details["B7"]="Roll No: CB.SC.U4AIE23127"
details["B12"]=repo;details["B14"]=base+"REPORT.md";details["B15"]="Local Windows 11 host; Python 3.12; FFmpeg/FFprobe (hardware specs not captured)";details["B16"]="No paid services recorded";details["B17"]="OpenAI Codex (see AI_USE.md)";details["B18"]="Not measured"
mh=wb["2_Must_haves"]
statuses=["Yes","Partial","Yes","Yes","Partial","Yes","Yes","No"]
notes=["Synthetic local API flow; source hash and unchanged original checked.","Caption anchors tested; audio/effect lifecycle incomplete.","Supported routes tested with all three statuses.","Three identical fixture runs produced identical canonical hashes.","Duration/start-offset check only; perceptual sync not measured.","Bleep, silence removal, ducked music, undo/redo and targeted earlier-cut undo are tested locally.","Current-edited-timeline policy tested.","No verified Docker deployment or public live demo."]
for i,(status,note) in enumerate(zip(statuses,notes),6):
 mh.cell(i,3).value=status;mh.cell(i,4).value=base+"TRACEABILITY.md";mh.cell(i,5).value=note
levels=wb["3_Levels"]
for r in range(5,16):
 levels.cell(r,3).value="No";levels.cell(r,4).value=base+"TRACEABILITY.md";levels.cell(r,5).value="Not fully verified; see traceability."
integration=wb["4_Integration"]
rows=[("No","Docker Desktop service was unavailable for a full image build."),("Yes","OpenAPI public paths are regression-tested against the service route surface."),("Yes","Async render job tested."),("Yes","Tested idempotency on API paths."),("Partial","Envelope implemented; coverage incomplete."),("Partial","Environment configuration exists; override test not recorded."),("Yes","Local upload/output links tested."),("Partial","Health/readiness tested; logs not fully asserted."),("Partial","Manifest generated; completeness limitations documented."),("Yes","Synthetic session runner executed.")]
for r,(status,note) in enumerate(rows,5):
 integration.cell(r,3).value=status;integration.cell(r,4).value=base+"TRACEABILITY.md"+" — "+note
metrics=wb["5_Metrics"]
vals=[("Not measured for official 5/60-minute videos","8-second synthetic session: median 12.404 ms, max 13.554 ms","evidence/manifest.json"),("Largest measured duration error 0.99999 frames; start offset 0.0 frames","Synthetic 30 fps render only; perceptual sync not measured","evidence/manifest.json"),("100% (3/3) for one synthetic fixture","Canonical timeline hash test","tests/test_timeline_engine.py"),("1 asked / 0 guessed","One synthetic repeated-pricing ambiguity","tests/test_api_e2e.py"),("Not measured","No 20-cut listening test","REPORT.md"),("No external API cost recorded; cost/min unknown","Local compute not monetized","REPORT.md")]
for r,(v,cond,evid) in enumerate(vals,5): metrics.cell(r,3).value=v;metrics.cell(r,4).value=cond;metrics.cell(r,5).value=base+evid
hard=wb["6_Hard_cases"]
texts=["Caption hides when anchored sentence is cut and returns on restore.","Reorder preserves word IDs; mute exists; bleep/filler intersection not fully verified.","Repeated range cut is safe; time parsing tests cover numeric timeline time; other forms partial.","Targeted earlier-cut undo preserves later music; no-caption reference is rejected; candidate-media scenario not yet run.","Repeated pricing/cost asks a clarification question with options.","10x speed and full-video cut rejected; multipart transactions incomplete.","Not tested on real two-speaker/VFR/no-audio media; limitations documented."]
for r,text in enumerate(texts,5): hard.cell(r,3).value="Yes" if r in (5,7,9,10) else "Partial";hard.cell(r,4).value=text;hard.cell(r,5).value=base+"docs/hard_cases.md"
# Declaration deliberately left blank for the candidate to review and sign personally.
wb.save(out)
print(out)
