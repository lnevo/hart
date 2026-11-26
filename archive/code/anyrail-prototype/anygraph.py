import json, math, collections, sys
parts=json.load(open('parts.json')); G=json.load(open('graph.json'))
comp=G['comps'][int(sys.argv[1]) if len(sys.argv)>1 else 1]
cs=set(comp)
nbr={}
for a,ka,b,kb in G['links']: nbr[(a,ka)]=(b,kb); nbr[(b,kb)]=(a,ka)
def angd(x,y):
    d=(x-y)%(2*math.pi); return min(d,2*math.pi-d)
legname={}
for i in comp:
    p=parts[i]
    if p['name']=='SL-8300': continue
    e=p['eps']
    # toe: endpoint farthest from the other two
    best=None
    for k in range(len(e)):
        others=[e[j] for j in range(len(e)) if j!=k]
        dmin=min(math.hypot(e[k]['x']-o['x'],e[k]['y']-o['y']) for o in others)
        if best is None or dmin>best[0]: best=(dmin,k)
    toe=best[1]; legs=[k for k in range(len(e)) if k!=toe]
    # straight = leg whose angle is most opposite the toe
    legs.sort(key=lambda k: abs(angd(e[k]['a'],e[toe]['a'])-math.pi))
    legname[(i,toe)]='A'; legname[(i,legs[0])]='B'; legname[(i,legs[1])]='C'
    p['legdev']=[round(math.degrees(abs(angd(e[k]['a'],e[toe]['a'])-math.pi)),1) for k in legs]
    p['leglen']={legname[(i,k)]:math.hypot(e[k]['x']-e[toe]['x'],e[k]['y']-e[toe]['y']) for k in legs}
def walk(i,k):
    L=0; chain=[]
    while True:
        if (i,k) not in nbr: return ('END',None,L,chain)
        j,kj=nbr[(i,k)]
        if parts[j]['name']!='SL-8300': return (j,legname[(j,kj)],L,chain)
        L+=parts[j]['len']; chain.append(j); k=1-kj; i=j
res={}
for (i,k),n in sorted(legname.items()):
    to,leg,L,ch=walk(i,k)
    res.setdefault(i,{'name':parts[i]['name'],'xy':(round(parts[i]['eps'][0]['x']),round(parts[i]['eps'][0]['y'])),'legdev':parts[i]['legdev'],'leglen':parts[i]['leglen'],'legs':{}})['legs'][n]=dict(to=to,leg=leg,cm=round(L,1),flex=ch)
for i,v in res.items():
    print('T%d'%i,v['name'],v['xy'],'dev',v['legdev'],{k:round(x,1) for k,x in v['leglen'].items()})
    for L,w in sorted(v['legs'].items()): print('   ',L,'->',('T%d'%w['to'] if w['to']!='END' else 'END'),w['leg'],w['cm'],'cm',len(w['flex']),'flex')
json.dump(res,open('any_c%s.json'%(sys.argv[1] if len(sys.argv)>1 else 1),'w'),indent=1)
