import struct, re, math, collections, json, bisect
d=open('plan.any','rb').read()
R=json.load(open('raw.json'))
names=[n for n in R['names'] if n[1].startswith('SL-') or n[2] in('PSL83','WAL83')]
noffs=[n[0] for n in names]
# bezier point lists: count u64 then n * ('4\x00' id x y)
bez=[]
for m in re.finditer(rb'([\x02-\x40])\x00{7}4\x00',d):
    n=m.group(1)[0]; o=m.end()-2; pts=[]
    for k in range(n):
        if d[o:o+2]!=b'4\x00' and k>0 and False: break
        if d[o:o+2]==b'4\x00': o+=2
        pid=struct.unpack('<I',d[o:o+4])[0]; x,y=struct.unpack('<2d',d[o+4:o+20]); o+=20
        pts.append((x,y))
    if all(math.isfinite(v) and abs(v)<5000 for p in pts for v in p): bez.append((m.start(),pts))
print('bezier lists',len(bez), collections.Counter(len(p) for _,p in bez))
parts=[dict(off=o,name=n,sys=s,eps=[],bez=[]) for o,n,s in names]
def owner(off):
    i=bisect.bisect_right(noffs,off)-1
    return parts[i] if i>=0 else None
for e in R['eps']:
    p=owner(e['off'])
    if not p: continue
    lastoff=p['eps'][-1]['off'] if p['eps'] else p['off']
    if e['off']-lastoff < (200 if p['eps'] else 1500): p['eps'].append(e)
for o,pts in bez:
    p=owner(o)
    if p and p['eps'] and not p['bez'] and 0 < o-p['eps'][-1]['off'] < 200 and len(pts)>=4 and (len(pts)-1)%3==0: p['bez'].append(pts)
print(collections.Counter((p['name'],len(p['eps']),len(p['bez'])) for p in parts).most_common(40))
def blen(pts,N=200):
    L=0
    for s in range(0,len(pts)-3,3):
        P=pts[s:s+4]; prev=P[0]
        for i in range(1,N+1):
            t=i/N; u=1-t
            q=tuple(u**3*P[0][j]+3*u*u*t*P[1][j]+3*u*t*t*P[2][j]+t**3*P[3][j] for j in range(2))
            L+=math.dist(prev,q); prev=q
    return L
for p in parts:
    if p['bez']: p['len']=sum(blen(b) for b in p['bez'])
json.dump(parts,open('parts.json','w'))
fl=[p for p in parts if p['name']=='SL-8300']
print('flex total cm',sum(p.get('len',0) for p in fl))
for p in fl[:5]: print(p['len'], [ (round(e['x'],1),round(e['y'],1)) for e in p['eps']], len(p['bez'][0]) if p['bez'] else None)
