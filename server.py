from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import json, os, time, uuid, threading, hashlib
from engine import Engine
from renderer import render
from media import inspect
sessions={}; idem={}; jobs={}
def err(code,message,status=400,details=None): return status,{"error":{"code":code,"message":message,"retryable":False,"details":details or {}}}
class API(SimpleHTTPRequestHandler):
    def log_message(self, fmt,*args): print(json.dumps({"timestamp":time.time(),"level":"info","message":fmt%args,"correlation_id":self.headers.get("X-Correlation-Id","")}))
    def json(self,status,body): self.send_response(status); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps(body).encode())
    def do_GET(self):
        p=urlparse(self.path).path
        if p in ("/health","/ready"): return self.json(200,{"status":"ok"})
        if p.startswith("/api/v1/sessions/"):
            sid=p.rsplit("/",1)[-1]; e=sessions.get(sid)
            return self.json(200,{"id":sid,"timeline":e.timeline.data(),"history":[{"id":h["id"],"type":h["type"],"instruction":h["instruction"],"operation":h["operation"]} for h in e.history],"timeline_hash":e.timeline.hash()}) if e else self.json(*err("SESSION_NOT_FOUND","Session not found",404))
        if p.startswith("/api/v1/jobs/"):
            job=jobs.get(p.rsplit('/',1)[-1]);return self.json(200,job) if job else self.json(*err("JOB_NOT_FOUND","Job not found",404))
        return super().do_GET()
    def do_POST(self):
        key=self.headers.get("Idempotency-Key")
        if not key:return self.json(*err("IDEMPOTENCY_KEY_REQUIRED","Idempotency-Key is required"))
        if key in idem:return self.json(200,idem[key])
        try: data=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
        except: return self.json(*err("INVALID_JSON","Request body must be JSON"))
        p=urlparse(self.path).path
        if p=="/api/v1/sessions":
            sid=str(uuid.uuid4()); sessions[sid]=Engine(data.get("video","mock://talking-head.mp4"),data.get("duration",300),data.get("transcript")); body={"id":sid,"timeline_hash":sessions[sid].timeline.hash()}; idem[key]=body; return self.json(201,body)
        if p=="/api/v1/uploads":
            filename=os.path.basename(data.get("filename","upload.mp4")); content=data.get("content_base64")
            if not content:return self.json(*err("UPLOAD_CONTENT_REQUIRED","Use content_base64 for this local API."))
            import base64
            raw=base64.b64decode(content); ext=os.path.splitext(filename)[1].lower()
            if ext not in (".mp4",".mov"): return self.json(*err("UNSUPPORTED_MEDIA","Only MP4 and MOV are accepted."))
            os.makedirs("uploads",exist_ok=True); path=os.path.join("uploads",str(uuid.uuid4())+ext);open(path,"wb").write(raw)
            body=inspect(path);idem[key]=body;return self.json(201,body)
        if p.endswith("/render"):
            sid=p.split("/")[-2];e=sessions.get(sid)
            if not e:return self.json(*err("SESSION_NOT_FOUND","Session not found",404))
            source=data.get("source_path")
            if not source:return self.json(*err("SOURCE_PATH_REQUIRED","Provide the uploaded immutable source_path."))
            jid=str(uuid.uuid4()); jobs[jid]={"job_id":jid,"status":"queued","progress":0,"result_links":[]}
            def work():
                jobs[jid].update(status="running",progress=10)
                try:
                    output=os.path.join("outputs",jid+".mp4"); manifest=render(e.timeline,source,output);jobs[jid].update(status="succeeded",progress=100,result_links=[output,output+".manifest.json"],manifest=manifest)
                except Exception as ex: jobs[jid].update(status="failed",progress=100,error=str(ex))
            threading.Thread(target=work,daemon=True).start();body={"job_id":jid,"status":"queued"};idem[key]=body;return self.json(202,body)
        if p.endswith("/instructions"):
            sid=p.split("/")[-2]; e=sessions.get(sid)
            if not e:return self.json(*err("SESSION_NOT_FOUND","Session not found",404))
            body=e.apply(data.get("instruction","")); idem[key]=body; return self.json(200,body)
        return self.json(*err("NOT_FOUND","Route not found",404))
if __name__=="__main__":
    os.chdir(os.path.dirname(__file__)); ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","8080"))),API).serve_forever()
