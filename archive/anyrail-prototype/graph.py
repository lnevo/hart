import json, math, collections
parts=json.load(open('parts.json'))
for i,p in enumerate(parts): p['i']=i
E=[(p['i'],k,e) for p in parts for k,e in enumerate(p['eps'])]
key=lambda e:(round(e['x']*5),round(e['y']*5))
buck=collections.defaultdict(list)
for t in E: buck[key(t[2])].append(t)
links=[]; 
for i,(pi,k,e) in enumerate(E):
    for dx in(-1,0,1):
        for dy in(-1,0,1):
            kk=key(e); 
            for (qj,kj,f) in buck[(kk[0]+dx,kk[1]+dy)]:
                if qj<=pi: continue
                if math.hypot(e['x']-f['x'],e['y']-f['y'])<0.15 and abs(e['z']-f['z'])<0.5:
                    links.append((pi,k,qj,kj))
print('links',len(links))
deg=collections.Counter()
for a,ka,b,kb in links: deg[(a,ka)]+=1; deg[(b,kb)]+=1
free=[(p['i'],k) for p in parts for k,e in enumerate(p['eps']) if deg[(p['i'],k)]==0]
print('unconnected endpoints',len(free), 'multi',sum(1 for v in deg.values() if v>1))
# components
par=list(range(len(parts)))
def f(x):
    while par[x]!=x: par[x]=par[par[x]]; x=par[x]
    return x
for a,_,b,_ in links: par[f(a)]=f(b)
comp=collections.defaultdict(list)
for p in parts: comp[f(p['i'])].append(p['i'])
cs=sorted(comp.values(),key=len,reverse=True)
for c in cs[:12]:
    zs=collections.Counter(round(e['z'],1) for i in c for e in parts[i]['eps'])
    L=sum(parts[i].get('len',0) for i in c)
    xs=[e['x'] for i in c for e in parts[i]['eps']]; ys=[e['y'] for i in c for e in parts[i]['eps']]
    print(len(c),'parts', 'turnouts',sum(1 for i in c if parts[i]['name']!='SL-8300'), 'flexcm',round(L), 'z',zs.most_common(3),'bbox',round(min(xs)),round(max(xs)),round(min(ys)),round(max(ys)))
json.dump(dict(links=links,comps=cs),open('graph.json','w'))
