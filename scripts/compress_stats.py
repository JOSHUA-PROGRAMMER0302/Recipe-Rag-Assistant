import json
p='data/compressed_index.json'
with open(p,'r',encoding='utf-8') as f:
    idx=json.load(f)
entries=idx.get('entries',[])
count=idx.get('count',len(entries))
bytes_saved=sum((e.get('orig_len') or 0)-(e.get('compressed_len') or 0) for e in entries if e.get('orig_len'))
print('count', count)
print('bytes_saved', bytes_saved)
# top 5 savings
saves=sorted([((e.get('orig_len') or 0)-(e.get('compressed_len') or 0), e.get('id')) for e in entries], reverse=True)[:5]
for s in saves:
    print('save', s[0], s[1])
