import json,glob
rows=[]
for f in glob.glob('repo/chart-data/shard-*.json'):
    d=json.load(open(f))
    for t,b in d.items():
        b=b[-50:]
        if len(b)<50: continue
        dv=sum(x[4]*x[5] for x in b)/len(b)
        rows.append((t,dv,b[-1][4]))
rows.sort(key=lambda r:-r[1])
u=[t for t,dv,p in rows if dv>=30e6 and p>=10]
print(len(rows),len(u))
json.dump(u,open('work/universe.json','w'))
