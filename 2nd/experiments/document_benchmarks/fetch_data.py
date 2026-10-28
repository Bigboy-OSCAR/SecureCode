"""Fetch pinned public evaluation splits; retain source provenance and raw bytes."""
from __future__ import annotations
import concurrent.futures, hashlib, io, json, os, time, urllib.request, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / 'Documents/test_results/evidence/document_benchmarks_20261027'
SCROLLS = '927b875150ac8f02262ddd3b078d33a9debc935b'
LONGBENCH = '5e628be450b7e67fb7ae6e201bd6d8f7056f7672'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def get(url, headers=None):
    for attempt in range(5):
        try:
            return urllib.request.urlopen(urllib.request.Request(url,headers=headers or {}), timeout=180)
        except Exception:
            if attempt == 4: raise
            time.sleep(2 ** attempt)

class RemoteZip(io.RawIOBase):
    """Seekable HTTP range reader, checked against requested byte interval."""
    def __init__(self, url, size):
        self.url, self.size, self.pos = url, size, 0
        self.block_size = 8*1024*1024
        self.cached = {}
        self.transferred = 0
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos
    def read(self, n=-1):
        n = min(self.size-self.pos, n if n >= 0 else self.size-self.pos)
        parts=[]
        while n:
            start=self.pos//self.block_size*self.block_size
            if start not in self.cached:
                end=min(start+self.block_size,self.size)-1
                # A unique query avoids intermediary caches mixing different ranges.
                with get(self.url+f'?download=true&range={start}-{end}', {'Range':f'bytes={start}-{end}'}) as r:
                    assert r.status == 206, (r.status, 'Server ignored HTTP Range')
                    assert r.headers['Content-Range'] == f'bytes {start}-{end}/{self.size}', dict(r.headers)
                    block=r.read()
                assert len(block)==end-start+1
                self.transferred += len(block)
                self.cached={start:block}
                print(json.dumps({'download':'narrative_qa','transferred_MB':round(self.transferred/1e6,1)}),flush=True)
            block=self.cached[start]; offset=self.pos-start; count=min(n,len(block)-offset)
            parts.append(block[offset:offset+count]); self.pos+=count; n-=count
        return b''.join(parts)

def fetch_one(name, meta):
    raw=OUT/'raw'; raw.mkdir(parents=True,exist_ok=True)
    archive_name='data.zip' if name=='longbench' else name+'.zip'
    revision=LONGBENCH if name=='longbench' else SCROLLS
    repo='zai-org/LongBench' if name=='longbench' else 'tau/scrolls'
    entry=next(s for s in meta['siblings'] if s['rfilename']==archive_name)
    url=f'https://huggingface.co/datasets/{repo}/resolve/{revision}/{archive_name}'
    targets=['hotpotqa','musique','multifieldqa_en'] if name=='longbench' else [name]
    manifest=OUT/'downloads'/f'{name}.json'
    if manifest.exists():
        previous=json.loads(manifest.read_text())
        for record in previous['members']: assert sha(raw/record['local_name'])==record['sha256']
        return previous
    remote=None
    if name=='narrative_qa':
        remote=RemoteZip(url,entry['size']); archive=zipfile.ZipFile(remote)
    else:
        zipped=OUT/'downloads'/archive_name
        if not zipped.exists():
            temp=zipped.with_suffix('.part')
            with get(url) as r,temp.open('wb') as f:
                for b in iter(lambda:r.read(1048576),b''):f.write(b)
            assert sha(temp)==entry['lfs']['sha256']
            os.replace(temp,zipped)
        assert sha(zipped)==entry['lfs']['sha256']
        archive=zipfile.ZipFile(zipped)
    result={'repo':repo,'revision':revision,'url':url,'archive_bytes':entry['size'],
            'published_archive_sha256':entry['lfs']['sha256'],
            'archive_fully_verified':remote is None,'members':[]}
    for target in targets:
        candidates=[s for s in archive.namelist() if s.endswith('/validation.jsonl') and s.startswith(target+'/')] if name!='longbench' else [s for s in archive.namelist() if s==target+'.jsonl' or s.endswith('/'+target+'.jsonl')]
        assert len(candidates)==1,(target,candidates)
        member=candidates[0]; info=archive.getinfo(member); dest=raw/(target+'.jsonl'); temp=dest.with_suffix('.part')
        with archive.open(member) as r,temp.open('wb') as f:
            for b in iter(lambda:r.read(1048576),b''):f.write(b)
        assert temp.stat().st_size==info.file_size
        os.replace(temp,dest)
        result['members'].append({'member':member,'local_name':dest.name,'bytes':info.file_size,
            'compressed_bytes':info.compress_size,'crc32':f'{info.CRC:08x}','sha256':sha(dest),
            'integrity':'ZIP CRC verified by complete ZipExtFile read; local SHA256 recorded'})
    archive.close()
    if remote is not None:result['transferred_bytes']=remote.transferred
    manifest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'complete':name,'members':result['members']}),flush=True)
    return result

def main():
    (OUT/'downloads').mkdir(parents=True,exist_ok=True)
    metas={}
    for repo in ['tau/scrolls','zai-org/LongBench']:
        with get('https://huggingface.co/api/datasets/'+repo+'?blobs=true') as f:meta=json.load(f)
        assert meta['sha']==(SCROLLS if repo=='tau/scrolls' else LONGBENCH)
        metas[repo]=meta
        (OUT/'downloads'/(repo.split('/')[-1]+'_api.json')).write_text(json.dumps(meta,indent=2)+'\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        jobs=[ex.submit(fetch_one,name,metas['zai-org/LongBench' if name=='longbench' else 'tau/scrolls']) for name in ['qmsum','qasper','quality','longbench','narrative_qa']]
        for job in concurrent.futures.as_completed(jobs):job.result()

if __name__=='__main__':main()
