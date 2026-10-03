import struct,sys
src,dst=sys.argv[1:3]
d=open(src,'rb').read()
assert struct.unpack_from('<HH',d,0)[0]==0x0003
# split chunks
chunks=[];off=8
while off<len(d):
    t,hs,sz=struct.unpack_from('<HHI',d,off); chunks.append([t,d[off:off+sz]]); off+=sz
assert off==len(d)
sp=[c for c in chunks if c[0]==0x0001][0]; rm=[c for c in chunks if c[0]==0x0180][0]
b=sp[1]; n,sc,flags,ss,st=struct.unpack_from('<IIIII',b,8); assert sc==0 and st==0, 'styled strings not supported'
utf8=bool(flags&0x100)
offs=struct.unpack_from('<%dI'%n,b,28)
def rd(i):
    p=ss+offs[i]
    if utf8:
        l=b[p];p+=1
        if l&0x80: l=((l&0x7f)<<8)|b[p];p+=1
        l2=b[p];p+=1
        if l2&0x80: l2=((l2&0x7f)<<8)|b[p];p+=1
        return b[p:p+l2].decode('utf8')
    l=struct.unpack_from('<H',b,p)[0]; return b[p+2:p+2+l*2].decode('utf16')
strs=[rd(i) for i in range(n)]
NEW='usesCleartextTraffic'; RID=0x010104ec
assert NEW not in strs
# resource map: ids for string index 0..m-1
ids=list(struct.unpack_from('<%dI'%((len(rm[1])-8)//4),rm[1],8)); m=len(ids)
assert all(i<m for i in [strs.index('extractNativeLibs'),strs.index('roundIcon')]), 'attr names must be inside resmap'
newidx=n
ids += [0]*(newidx-m) + [RID]
# rebuild string pool (append, original strings unchanged -> all indices stay valid)
def enc(s):
    if utf8:
        e=s.encode('utf8'); l=len(s)
        def ln(x): return bytes([x]) if x<0x80 else bytes([(x>>8)|0x80,x&0xff])
        return ln(l)+ln(len(e))+e+b'\0'
    e=s.encode('utf16')[2:]; l=len(s)
    return (struct.pack('<H',l) if l<0x8000 else struct.pack('<HH',(l>>16)|0x8000,l&0xffff))+e+b'\0\0'
olddata=b[ss:]
# keep original string bytes exactly, append new one
newdata=olddata
# strip trailing padding to append contiguous
last=max(offs)  # start of last string
# find end of last string = original data length minus padding zeros handled by recomputing
def strlen_at(p):
    q=p
    if utf8:
        l=olddata[q];q+=1
        if l&0x80: q+=1
        l2=olddata[q];q+=1
        if l2&0x80: l2=((l2&0x7f)<<8)|olddata[q];q+=1
        return q+l2+1-p
    l=struct.unpack_from('<H',olddata,q)[0]; return 2+l*2+2
end=last+strlen_at(last)
body=olddata[:end]+enc(NEW)
newoff=end
pad=(-len(body))%4; body+=b'\0'*pad
n2=n+1
hdr=struct.pack('<HHI',0x0001,28,0)+struct.pack('<IIIII',n2,0,flags,28+4*n2,0)
offtab=struct.pack('<%dI'%n2,*(list(offs)+[newoff]))
sp_new=hdr+offtab+body
sp_new=sp_new[:4]+struct.pack('<I',len(sp_new))+sp_new[8:]
sp[1]=sp_new
rm_new=struct.pack('<HHI',0x0180,8,8+4*len(ids))+struct.pack('<%dI'%len(ids),*ids); rm[1]=rm_new
# application start element: insert attribute after extractNativeLibs (sorted by resource id)
done=False
for c in chunks:
    if c[0]!=0x0102: continue
    e=c[1]
    ns,nm,astart,asize,ac,idI,clI,stI=struct.unpack_from('<IIHHHHHH',e,16)
    # NOTE layout: ext header: attrStart(2) attrSize(2) attrCount(2) idIndex(2) classIndex(2) styleIndex(2)
    if strs[nm]!='application': continue
    assert astart==20 and asize==20 and idI==0 and clI==0 and stI==0,(astart,asize,idI,clI,stI)
    ap=16+20; attrs=[e[ap+i*20:ap+i*20+20] for i in range(ac)]
    names=[strs[struct.unpack_from('<I',a,4)[0]] for a in attrs]
    pos=names.index('extractNativeLibs')+1
    ansns=struct.unpack_from('<I',attrs[pos-1],0)[0]
    new_attr=struct.pack('<IIIHBBI',ansns,newidx,0xffffffff,8,0,0x12,0xffffffff)
    attrs.insert(pos,new_attr)
    e2=e[:16]+struct.pack('<IIHHHHHH',ns,nm,20,20,ac+1,0,0,0)+b''.join(attrs)
    e2=e2[:4]+struct.pack('<I',len(e2))+e2[8:]
    c[1]=e2; done=True; break
assert done
out=b''.join(c[1] for c in chunks)
out=struct.pack('<HHI',0x0003,8,8+len(out))+out
open(dst,'wb').write(out); print('manifest patched',len(d),'->',len(out))
