"""Snapshot the experimental runner and the local source dependencies used to build it."""
import hashlib
import json
import shutil
import zipfile
from run_snapshot import ROOT

def main():
    exe=ROOT/'build-stock-fuel/udon_stock_fuel_runner.exe'
    digest=hashlib.sha256(exe.read_bytes()).hexdigest()
    out=ROOT/'solver_versions'/('stock_fuel_'+digest[:12])
    out.mkdir(exist_ok=False)
    shutil.copy2(exe,out/exe.name)
    files=[]
    for base in [ROOT/'solvers/hieu_521',ROOT.parent/'pro26-hieu/promax26/src',
                 ROOT.parent/'pro26-hieu/promax26/include',ROOT/'solvers/promax26_3_adapter']:
        files.extend(p for p in base.rglob('*') if p.is_file() and p.suffix in ('.cpp','.hpp','.h','.py','.txt','.cmake'))
    files.append(ROOT.parent/'pro26-hieu/promax26/CMakeLists.txt')
    manifest={'exe_sha256':digest,'status':'experimental; not promoted','source_hashes':{}}
    with zipfile.ZipFile(out/'source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            name=str(path.relative_to(ROOT.parent)).replace('\\','/')
            manifest['source_hashes'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
            archive.write(path,name)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(out)

if __name__=='__main__': main()
