#!/usr/bin/env python3
"""Memory-bounded, read-only GLB topology audit.

This intentionally avoids Blender's Python mesh traversal for very dense cloud
outputs. It reads the GLB payload directly and writes JSON/CSV/PNG evidence
only to the specified audit directory.
"""
import argparse, csv, hashlib, json, math, os, struct
from collections import Counter, defaultdict
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CTYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}

def r6(v): return round(float(v), 6)

def read_glb(path):
    data = open(path, 'rb').read()
    magic, version, total = struct.unpack_from('<4sII', data, 0)
    if magic != b'glTF' or version != 2 or total != len(data):
        raise ValueError('Invalid or unsupported GLB')
    off = 12; chunks = []
    while off < len(data):
        ln, typ = struct.unpack_from('<I4s', data, off); off += 8
        chunks.append((typ, data[off:off+ln])); off += ln
    gltf = json.loads(next(b for t,b in chunks if t == b'JSON').decode('utf-8'))
    bin_chunk = next(b for t,b in chunks if t == b'BIN\x00')
    return gltf, bin_chunk

def accessor(gltf, blob, ai):
    acc = gltf['accessors'][ai]; view = gltf['bufferViews'][acc['bufferView']]
    dtype = np.dtype(CTYPES[acc['componentType']]); nc = NCOMP[acc['type']]
    start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    stride = view.get('byteStride', dtype.itemsize * nc)
    if stride == dtype.itemsize * nc:
        arr = np.frombuffer(blob, dtype=dtype, count=acc['count']*nc, offset=start).reshape(acc['count'], nc)
    else:
        arr = np.ndarray((acc['count'], nc), dtype=dtype, buffer=blob, offset=start, strides=(stride, dtype.itemsize)).copy()
    return arr

def find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x

def union(parent, rank, a, b):
    ra = find(parent, int(a)); rb = find(parent, int(b))
    if ra == rb: return
    if rank[ra] < rank[rb]: ra, rb = rb, ra
    parent[rb] = ra
    if rank[ra] == rank[rb]: rank[ra] += 1

def draw_distribution(summary, path):
    img = Image.new('RGB', (1260, 620), (25, 28, 34)); d = ImageDraw.Draw(img)
    title = 'Mira Hunyuan GLB — disconnected-component audit'
    d.text((45, 28), title, fill=(245,245,245), font=ImageFont.load_default())
    colors = {'structural_shell':(50,142,237), 'medium_island':(48,201,105), 'small_fragment':(255,166,45), 'micro_fragment':(228,66,77)}
    categories = ['structural_shell','medium_island','small_fragment','micro_fragment']
    count = summary['components_by_category']; faces = summary['faces_by_category']
    maxc=max(count.values()) or 1; maxf=max(faces.values()) or 1
    d.text((45, 90), 'component count', fill=(205,210,220), font=ImageFont.load_default())
    d.text((660, 90), 'face coverage', fill=(205,210,220), font=ImageFont.load_default())
    for i,cat in enumerate(categories):
        y=135+i*105; c=colors[cat]
        d.rectangle((45,y,315,y+42), fill=(50,54,62)); d.rectangle((45,y,45+270*count.get(cat,0)/maxc,y+42),fill=c)
        d.text((325,y+14),f'{cat}: {count.get(cat,0):,}',fill=(240,240,240),font=ImageFont.load_default())
        d.rectangle((660,y,930,y+42),fill=(50,54,62)); d.rectangle((660,y,660+270*faces.get(cat,0)/maxf,y+42),fill=c)
        d.text((940,y+14),f'{faces.get(cat,0):,} faces',fill=(240,240,240),font=ImageFont.load_default())
    verdict=summary['direct_reduceface_verdict']
    d.text((45,570),f'ReduceFace: {verdict}; boundary edges {summary["boundary_edges"]:,}; non-manifold edges {summary["nonmanifold_edges"]:,}',fill=(255,210,115) if verdict=='BLOCKED' else (110,230,145),font=ImageFont.load_default())
    img.save(path)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output-dir',required=True); args=ap.parse_args()
    os.makedirs(args.output_dir,exist_ok=True)
    with open(args.input,'rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    g,b=read_glb(args.input)
    primitives=[]
    for mi,m in enumerate(g.get('meshes',[])):
        for pi,p in enumerate(m.get('primitives',[])):
            if p.get('mode',4) != 4: continue
            pos=accessor(g,b,p['attributes']['POSITION']).astype(np.float64,copy=False)
            if 'indices' in p: ind=accessor(g,b,p['indices']).reshape(-1).astype(np.int64,copy=False)
            else: ind=np.arange(len(pos),dtype=np.int64)
            if len(ind)%3: raise ValueError('Non-triangle index count')
            primitives.append((mi,pi,pos,ind.reshape(-1,3),p.get('material')))
    # Topology is assessed per primitive; object-level component counts are the sum.
    all_reports=[]; aggregate=Counter(); largest=[]; primitive_reports=[]
    for mi,pi,pos,tri,mat in primitives:
        n=len(tri); bbox_min=pos.min(axis=0); bbox_max=pos.max(axis=0); diag=float(np.linalg.norm(bbox_max-bbox_min))
        eps=max(diag*diag*1e-12,1e-18); length_eps=max(diag*1e-12,1e-18)
        pa,pb,pc=pos[tri[:,0]],pos[tri[:,1]],pos[tri[:,2]]
        twice=np.linalg.norm(np.cross(pb-pa,pc-pa),axis=1); deg=twice<=2*eps
        directed=np.concatenate((tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]),axis=0)
        face_ids=np.repeat(np.arange(n,dtype=np.int64),3)
        # The concatenate order is blocks; update face IDs accordingly.
        face_ids=np.concatenate((np.arange(n),np.arange(n),np.arange(n))).astype(np.int64)
        undirected=np.sort(directed,axis=1)
        order=np.lexsort((undirected[:,1],undirected[:,0])); ue=undirected[order]; of=face_ids[order]; od=directed[order]
        starts=np.r_[0,np.flatnonzero(np.any(ue[1:]!=ue[:-1],axis=1))+1]; ends=np.r_[starts[1:],len(ue)]
        counts=ends-starts
        boundary_idx=np.flatnonzero(counts==1); nonman_idx=np.flatnonzero(counts>2); pair_idx=np.flatnonzero(counts==2)
        parent=list(range(n)); rank=[0]*n
        # Two faces meeting along one edge establish a shell component. Fan
        # connections on non-manifold edges are also retained for reporting.
        for s,e in zip(starts,ends):
            if e-s>=2:
                root=of[s]
                for k in range(s+1,e): union(parent,rank,root,of[k])
        roots=np.fromiter((find(parent,i) for i in range(n)),dtype=np.int64,count=n)
        unique_roots, inv, face_counts=np.unique(roots,return_inverse=True,return_counts=True)
        cc=len(unique_roots)
        # Attribute all edge defects to their incident component.
        b_by=np.bincount(inv[of[starts[boundary_idx]]],minlength=cc)
        nm_by=np.bincount(inv[of[starts[nonman_idx]]],minlength=cc)
        # Same directed orientation on a shared edge is a winding conflict.
        winding_by=np.zeros(cc,dtype=np.int64)
        for s in starts[pair_idx]:
            a,b0=od[s],od[s+1]
            if int(a[0])==int(b0[0]) and int(a[1])==int(b0[1]): winding_by[inv[of[s]]] += 1
        deg_by=np.bincount(inv,weights=deg.astype(np.int64),minlength=cc).astype(np.int64)
        # Component extent and unique vertices. Iterate components only (not all
        # pairs), retaining a bounded working slice each time.
        order_faces=np.argsort(inv,kind='stable'); fs=np.r_[0,np.cumsum(face_counts)]
        comp_rows=[]
        for ci in range(cc):
            ids=order_faces[fs[ci]:fs[ci+1]]; vids=np.unique(tri[ids].reshape(-1)); pts=pos[vids]
            lo=pts.min(axis=0); hi=pts.max(axis=0); cdiag=float(np.linalg.norm(hi-lo)); rel=cdiag/diag if diag else 0.0; nf=int(face_counts[ci])
            if nf<=8 or rel<0.002: cat='micro_fragment'
            elif nf<=80 or rel<0.01: cat='small_fragment'
            elif nf<=500 or rel<0.03: cat='medium_island'
            else: cat='structural_shell'
            row={'primitive':f'{mi}:{pi}','component_id':ci,'category':cat,'faces':nf,'vertices':int(len(vids)),
                 'boundary_edges':int(b_by[ci]),'nonmanifold_edges':int(nm_by[ci]),'winding_conflict_edges':int(winding_by[ci]),
                 'degenerate_faces':int(deg_by[ci]),'bbox_min':[r6(x) for x in lo],'bbox_max':[r6(x) for x in hi],
                 'bbox_diagonal':r6(cdiag),'relative_bbox_diagonal':r6(rel),'material':mat}
            comp_rows.append(row)
        edge_lengths=np.linalg.norm(pos[undirected[:,0]]-pos[undirected[:,1]],axis=1)
        obj={'primitive':f'{mi}:{pi}','vertices':len(pos),'faces':n,'edges':len(starts),'boundary_edges':int(len(boundary_idx)),
             'nonmanifold_edges':int(len(nonman_idx)),'winding_conflict_edges':int(winding_by.sum()),'degenerate_faces':int(deg.sum()),
             'zero_length_edges':int(np.sum(edge_lengths[starts]<=length_eps)),'components':cc,'area_epsilon':eps,'bbox_min':[r6(x) for x in bbox_min],'bbox_max':[r6(x) for x in bbox_max], 'bbox_diagonal':r6(diag)}
        primitive_reports.append(obj)
        all_reports+=comp_rows; aggregate.update(obj); largest+=comp_rows
    cats=Counter(x['category'] for x in all_reports); cat_faces=Counter()
    for x in all_reports: cat_faces[x['category']]+=x['faces']
    largest.sort(key=lambda x:x['faces'],reverse=True)
    summary={'objects_primitives':len(primitives),'vertices':int(aggregate['vertices']),
             'faces':sum(x['faces'] for x in all_reports),'components':len(all_reports),
             'boundary_edges':int(aggregate['boundary_edges']),'nonmanifold_edges':int(aggregate['nonmanifold_edges']),
             'winding_conflict_edges':int(aggregate['winding_conflict_edges']),'degenerate_faces':int(aggregate['degenerate_faces']),
             'zero_length_edges':int(aggregate['zero_length_edges']),'components_by_category':dict(cats),'faces_by_category':dict(cat_faces),
             'largest_components':largest[:30]}
    summary['direct_reduceface_verdict']='BLOCKED' if summary['boundary_edges'] or summary['nonmanifold_edges'] else 'CONDITIONALLY_READY'
    summary['verdict_reason']='Open boundaries and/or non-manifold edges must be repaired before ReduceFace.' if summary['direct_reduceface_verdict']=='BLOCKED' else 'No open/non-manifold edges found; verify shell separation and self-intersection policy before ReduceFace.'
    summary['closed_components']=sum(1 for x in all_reports if x['boundary_edges']==0 and x['nonmanifold_edges']==0)
    summary['open_components']=len(all_reports)-summary['closed_components']
    summary['face_share_by_category']={k:r6(v/max(summary['faces'],1)) for k,v in cat_faces.items()}
    out={'audit_version':2,'method':'direct GLB accessor scan; per-primitive edge incidence + union-find face islands', 'input':os.path.abspath(args.input),'input_sha256':digest,
         'source_modified':False,'primitives':primitives and [{'primitive':f'{a}:{b}','vertices':len(c),'faces':len(d),'material':e} for a,b,c,d,e in primitives], 'object_reports':primitive_reports, 'components':all_reports,'summary':summary,
         'limitations':['This audit proves edge incidence, degenerate triangles and orientation conflicts. Exact triangle-triangle self-intersection requires a separate robust narrow-phase test.', 'Separate watertight shells may be intentional clothing/accessory parts; their count alone is not a repair target.']}
    # object reports must be recomputed cleanly without Counter key collisions.
    # Keep the direct primitive totals available in the source JSON for auditability.
    with open(os.path.join(args.output_dir,'topology_audit.json'),'w') as f: json.dump(out,f,indent=2)
    with open(os.path.join(args.output_dir,'component_inventory.csv'),'w',newline='') as f:
        fields=['primitive','component_id','category','faces','vertices','boundary_edges','nonmanifold_edges','winding_conflict_edges','degenerate_faces','bbox_diagonal','relative_bbox_diagonal','material']
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows([{k:x.get(k) for k in fields} for x in all_reports])
    draw_distribution(summary,os.path.join(args.output_dir,'component_distribution.png'))
    with open(os.path.join(args.output_dir,'README.md'),'w') as f:
        f.write('# Read-only topology audit\\n\\n`topology_audit.json` is an exact GLB edge-incidence scan. `component_distribution.png` maps blue=structural shells, green=medium islands, orange=small fragments, red=micro fragments. No source geometry was rewritten.\\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
