import xml.etree.ElementTree as ET, collections, json
t=ET.parse(__import__('sys').argv[1]).getroot()
le=[p for p in t.iter('LayoutEditor')]
print('panels',[p.get('name') for p in le])
P=le[0]
tos={x.get('ident'):x for x in P.iter('layoutturnout')}
segs={x.get('ident'):x for x in P.iter('tracksegment')}
pps={x.get('ident'):x for x in P.iter('positionablepoint')}
print(len(tos),len(segs),len(pps), collections.Counter(x.get('type') for x in tos.values()))
# segment adjacency
def other_end(seg, frm):
    a=(seg.get('connect1name'),seg.get('type1')); b=(seg.get('connect2name'),seg.get('type2'))
    return b if a[0]==frm else a
def walk(start_to, leg):
    # find segment attached to turnout leg
    for s in segs.values():
        for n,ty in ((s.get('connect1name'),s.get('type1')),(s.get('connect2name'),s.get('type2'))):
            if n==start_to and ty=='TURNOUT_'+leg:
                return follow(s,start_to)
    return None
def follow(s,frm):
    blocks=[s.get('blockname')]; segsseen=[s.get('ident')]
    while True:
        n,ty=other_end(s,frm)
        if ty and ty.startswith('TURNOUT'): return dict(to=n,leg=ty[-1],blocks=blocks)
        pp=pps.get(n)
        if pp is None: return dict(to=n,leg=ty,blocks=blocks)
        if pp.get('type')=='END_BUMPER': return dict(to='END',leg=n,blocks=blocks)
        c=[pp.get('connect1name'),pp.get('connect2name')]
        nxt=[x for x in c if x and x!=s.get('ident')]
        if not nxt or nxt[0] not in segs: return dict(to=pp.get('type'),leg=n,blocks=blocks)
        frm=n; s=segs[nxt[0]]
        if s.get('blockname')!=blocks[-1]: blocks.append(s.get('blockname'))
out={}
for i,x in tos.items():
    legs='ABCD' if x.get('type') in ('DOUBLE_XOVER','RH_XOVER','LH_XOVER') else 'ABC'
    out[i]=dict(name=x.get('turnoutname'),block=x.get('blockname'),type=x.get('type'),legs={L:walk(i,L) for L in legs})
for i,v in out.items():
    print(i,v['type'],v['block'])
    for L,w in v['legs'].items(): print('   ',L,'->',w and (w['to'],w['leg'],w['blocks']))
json.dump(out,open('hart.json','w'),indent=1)
