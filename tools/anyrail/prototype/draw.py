import json, math, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
parts=json.load(open('parts.json')); G=json.load(open('graph.json'))
def bpts(P,N=20):
    out=[]
    for s in range(0,len(P)-3,3):
        Q=P[s:s+4]
        for i in range(N+1):
            t=i/N;u=1-t; out.append([u**3*Q[0][j]+3*u*u*t*Q[1][j]+3*u*t*t*Q[2][j]+t**3*Q[3][j] for j in range(2)])
    return out
for ci,c in enumerate(G['comps'][:3]):
    fig,ax=plt.subplots(figsize=(14,20))
    for i in c:
        p=parts[i]
        if p['bez']:
            pts=bpts(p['bez'][0]); z=p['eps'][0]['z']
            ax.plot([q[0] for q in pts],[q[1] for q in pts],color=plt.cm.viridis((z+40)/55),lw=2)
            m=pts[len(pts)//2]; ax.text(m[0],m[1],'f%d'%i,fontsize=5,color='gray')
        else:
            e=p['eps']
            # toe = endpoint farthest from the others' mean
            for a in e[1:]: ax.plot([e[0]['x'],a['x']],[e[0]['y'],a['y']],'r-',lw=2)
            ax.plot([e[1]['x'],e[2]['x']],[e[1]['y'],e[2]['y']],'r:',lw=1)
            cx=sum(a['x'] for a in e)/len(e); cy=sum(a['y'] for a in e)/len(e)
            ax.text(cx,cy,'T%d %s'%(i,p['name'][3:]),fontsize=7,color='red',weight='bold')
    ax.set_aspect('equal'); ax.invert_yaxis(); ax.grid(alpha=.3)
    fig.savefig('comp%d.png'%ci,dpi=110,bbox_inches='tight'); plt.close(fig)
