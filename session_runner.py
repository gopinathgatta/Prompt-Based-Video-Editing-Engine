import argparse,json,os,re
from engine import Engine
def parse(path):
 lines=open(path,encoding='utf8').read().splitlines(); video='mock://talking-head.mp4'; steps=[]
 for line in lines:
  if line.startswith('video:'): video=line.split(':',1)[1].strip()
  if 'say:' in line: steps.append(re.search(r'["\'](.*)["\']',line).group(1))
 return video,steps
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('session');p.add_argument('--output',default='evidence/session');a=p.parse_args();video,steps=parse(a.session);e=Engine(video); results=[]
 for step in steps:
  r=e.apply(step)
  results.append({'say':step,**r})
 os.makedirs(a.output,exist_ok=True)
 with open(os.path.join(a.output,'results.json'),'w',encoding='utf8') as out:
  json.dump({'results':results,'final_timeline':e.timeline.data(),'history':e.history},out,indent=2,default=lambda value:value.data() if hasattr(value,'data') else str(value))
 print(os.path.join(a.output,'results.json'))
