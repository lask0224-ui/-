"""원고의 따옴표 인용을 개역개정 본문과 대조한다.

usage: python3 tools/check_quotes.py <개역개정 txt 폴더> <원고.md ...> > 결과.json
- 성경 본문은 저작권 자료라 저장소에 넣지 않는다(사용자가 올린 전수검증본을 따로 둔다).
- 결과: 원고 구절과 가장 가까운 본문 구절이 다른 곳(일치율 0.75 이상)만 나온다. 강의의 풀어 쓴 말도 섞여 나오므로 사람이 보고 고친다.
"""
import sys,re,glob,os,difflib,json
from collections import defaultdict
krv=sys.argv[1]; files=sys.argv[2:]
V={}; order=[]
for f in sorted(glob.glob(os.path.join(krv,'*.txt'))):
    for line in open(f,encoding='utf-8'):
        m=re.match(r'(\S+?\d+:\d+)\s+(.*)',line.strip())
        if m: V[m.group(1)]=re.sub(r'<[^>]*>','',m.group(2)).strip(); order.append(m.group(1))
norm=lambda s: re.sub(r'[^가-힣0-9]','',s)
pos={k:i for i,k in enumerate(order)}
gram=defaultdict(set)
for i,k in enumerate(order):
    n=norm(V[k])
    for j in range(len(n)-3): gram[n[j:j+4]].add(i)
def span_text(i):  # verse i plus next, raw
    ks=order[i:i+2]; return ks, ' '.join(V[k] for k in ks)
out=[]
for f in files:
    for ln,line in enumerate(open(f,encoding='utf-8').read().split('\n'),1):
        for q in re.findall(r'“([^”]{10,})”',line):
            for s in re.split(r'…',q):
                core=s.strip(); n=norm(core)
                if len(n)<8: continue
                cnt=defaultdict(int)
                for j in range(len(n)-3):
                    for i in gram.get(n[j:j+4],()): cnt[i]+=1
                if not cnt: continue
                best=None
                for i in sorted(cnt,key=cnt.get,reverse=True)[:8]:
                    for start in (i-1,i):
                        if start<0: continue
                        ks,raw=span_text(start)
                        # char-level on raw with mapping
                        sm=difflib.SequenceMatcher(None,core,raw,autojunk=False)
                        blocks=[b for b in sm.get_matching_blocks() if b.size>=3]
                        if not blocks: continue
                        m=sum(b.size for b in blocks)
                        r=m/len(core)
                        if best is None or r>best[0]: best=(r,ks,raw,blocks)
                r,ks,raw,blocks=best
                if r<0.75: continue
                a=blocks[0].b; b=blocks[-1].b+blocks[-1].size
                cand=raw[a:b].strip()
                if norm(cand)==n: continue
                out.append(dict(f=f,ln=ln,book=core,krv=cand,refs=ks,r=round(r,2)))
json.dump(out,open(sys.stdout.fileno(),'w',encoding='utf-8',closefd=False),ensure_ascii=False,indent=0)
