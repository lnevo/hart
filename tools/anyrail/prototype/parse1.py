import struct, re, math, collections, sys, json
d=open(sys.argv[1] if len(sys.argv)>1 else 'plan.any','rb').read()
# part names: u64 len + "SL-xxxx"-like followed by u64 len + track system
names=[]
for m in re.finditer(rb'([\x03-\x30])\x00{7}([\x20-\x7e]{3,48})([\x03-\x10])\x00{7}(PSL83|[A-Z0-9]{2,8})',d):
    n=m.group(1)[0]
    if len(m.group(2))!=n: continue
    if len(m.group(4))!=m.group(3)[0]: continue
    names.append((m.start(), m.group(2).decode(), m.group(4).decode()))
print('parts',len(names)); print(collections.Counter(n for _,n,_ in names).most_common(30))
eps=[]
for m in re.finditer(rb'X\x00(.{4})(.{4})(.{32})([\x01-\x10])\x00{7}',d,re.S):
    L=m.group(4)[0]; s=d[m.end():m.end()+L]
    if not re.fullmatch(rb'[\x20-\x7e]+',s): continue
    eid,pid=struct.unpack('<II',m.group(1)+m.group(2)); x,y,z,a=struct.unpack('<4d',m.group(3))
    if not all(math.isfinite(v) for v in (x,y,z,a)) or abs(x)>5000 or abs(y)>5000: continue
    eps.append(dict(off=m.start(),id=eid,x=x,y=y,z=z,a=a,sys=s.decode()))
print('endpoints',len(eps)); print(collections.Counter(round(e['z'],2) for e in eps).most_common(20))
print(collections.Counter(e['sys'] for e in eps))
json.dump(dict(names=names,eps=eps),open('raw.json','w'))
