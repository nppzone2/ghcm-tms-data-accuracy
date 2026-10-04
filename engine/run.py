"""GHCM · Điều phối dữ liệu nhiều tháng.

  python engine/run.py prepare   1) mở kho mã hoá input/vault/*.enc ra work/<YYYY-MM>/
                                 2) file mới tải lên input/*.xlsx: tự nhận tháng từ cột Date của file TMS,
                                    chuyển vào work/<YYYY-MM>/ (thay dữ liệu cũ của tháng đó)
                                 3) tính KPI cho các tháng gần nhất -> build/months/<YYYY-MM>.json
  python engine/run.py save      mã hoá lại các tháng vừa thay vào input/vault/<YYYY-MM>.enc

Mỗi tháng tải 2 file (TMS Order Detail + Fill Rate) của tháng đó. Tải lại giữa tháng thì dữ liệu tháng đó
được thay bằng file mới. Kho giữ mọi tháng; trang hiển thị tháng hiện tại (đang chạy) và
N tháng đã hoàn thành gần nhất (completed_months_shown trong engine/config.json, mặc định 3).
Khoá mã hoá dẫn xuất từ secret ADMIN_PASSWORD.
"""
import io, json, os, re, shutil, subprocess, sys, zipfile
from pathlib import Path
import pandas as pd
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parents[1]
INPUT, VAULT, WORK, BUILD = ROOT / 'input', ROOT / 'input' / 'vault', ROOT / 'work', ROOT / 'build' / 'months'
from datetime import datetime, timedelta, timezone
CFG = json.load(open(ROOT / 'engine' / 'config.json', encoding='utf-8'))
DONE_SHOWN = int(CFG.get('completed_months_shown', 3))
CHANGED = ROOT / 'work' / '.changed'

pw = os.environ.get('ADMIN_PASSWORD', '').strip()
if not pw:
    sys.exit('LỖI: chưa đặt secret ADMIN_PASSWORD.')

def key(salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000).derive(pw.encode())

def decrypt(path):
    raw = path.read_bytes()
    salt, iv, ct = raw[5:21], raw[21:33], raw[33:]
    try:
        return AESGCM(key(salt)).decrypt(iv, ct, None)
    except Exception:
        sys.exit(f'LỖI: không giải mã được {path.name} (ADMIN_PASSWORD đã đổi?). Hãy tải lại file dữ liệu.')

def encrypt(data):
    salt, iv = os.urandom(16), os.urandom(12)
    return b'GHCMV' + salt + iv + AESGCM(key(salt)).encrypt(iv, data, None)

norm = lambda s: re.sub(r'[\s_\-]', '', s.lower())
is_tms = lambda p: 'tms' in norm(p.name)
is_fill = lambda p: 'fill' in norm(p.name)

def month_of(tms_path):
    """Tháng của dữ liệu = tháng xuất hiện nhiều nhất ở cột Date của file TMS."""
    from xlio import read_export, to_dt
    d = read_export(tms_path, usecols=lambda c: str(c).strip() == 'Date')
    if 'Date' not in d.columns:
        sys.exit(f'LỖI: file {tms_path.name} không có cột Date.')
    return to_dt(d['Date']).dt.strftime('%Y-%m').mode().iloc[0]

def fill_month_of(path):
    """Tháng của file Fill Rate: YYYYMM trong tên file, nếu không có thì cột Calendar_Month."""
    hit = re.search(r'(20\d{2})[-_]?(0[1-9]|1[0-2])(?!\d)', path.stem)
    if hit:
        return f'{hit.group(1)}-{hit.group(2)}'
    from xlio import read_export
    d = read_export(path, usecols=lambda c: str(c).strip() == 'Calendar_Month')
    if 'Calendar_Month' not in d.columns:
        sys.exit(f'LỖI: không xác định được tháng của {path.name} (đặt tên dạng Fill_Rate_YYYYMM.xlsx).')
    v = str(int(float(d.Calendar_Month.dropna().mode().iloc[0])))
    return f'{v[:4]}-{v[4:6]}'

def unpack(data, dest):
    dest.mkdir(parents=True, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(data)).extractall(dest)

def prepare():
    shutil.rmtree(WORK, ignore_errors=True); shutil.rmtree(BUILD, ignore_errors=True)
    WORK.mkdir(parents=True); BUILD.mkdir(parents=True)
    changed = set()
    # 1. kho mã hoá theo tháng
    for f in sorted(VAULT.glob('*.enc')):
        unpack(decrypt(f), WORK / f.stem)
    # chuyển đổi kho cũ (một file last_data.enc) sang kho theo tháng
    legacy = INPUT / 'last_data.enc'
    if legacy.exists():
        tmp = WORK / '_legacy'; unpack(decrypt(legacy), tmp)
        t = next((p for p in tmp.glob('*.xlsx') if is_tms(p)), None)
        if t:
            m = month_of(t)
            if not (WORK / m).exists():
                tmp.rename(WORK / m); changed.add(m); print(f'Chuyển dữ liệu cũ sang tháng {m}')
        shutil.rmtree(tmp, ignore_errors=True)
    # 2. file mới tải lên
    # Nhận được nhiều tháng trong một lần: ghép file TMS và Fill Rate theo tháng.
    new = [p for p in INPUT.glob('*.xlsx') if not p.name.startswith('~$')]
    if new:
        t = [p for p in new if is_tms(p)]; f = [p for p in new if is_fill(p)]
        other = [p.name for p in new if p not in t and p not in f]
        if other:
            print(f'Cảnh báo: bỏ qua file không nhận ra (tên cần có chữ TMS hoặc Fill): {other}')
        if not t or not f:
            sys.exit(f'LỖI: cần cả file TMS và file Fill Rate của cùng tháng, đang có: {[p.name for p in new]}')
        tm = {}
        for p in t:
            m = month_of(p)
            if m in tm: sys.exit(f'LỖI: có 2 file TMS cùng tháng {m}: {tm[m].name}, {p.name}')
            tm[m] = p
        fm = {}
        for p in f:
            m = fill_month_of(p)
            if m in fm: sys.exit(f'LỖI: có 2 file Fill Rate cùng tháng {m}: {fm[m].name}, {p.name}')
            fm[m] = p
        if set(tm) != set(fm):
            sys.exit(f'LỖI: file TMS và Fill Rate không khớp tháng. TMS: {sorted(tm)}, Fill Rate: {sorted(fm)}')
        for m in sorted(tm):
            dest = WORK / m
            shutil.rmtree(dest, ignore_errors=True); dest.mkdir(parents=True)
            for p in (tm[m], fm[m]): shutil.copy2(p, dest / p.name)
            changed.add(m); print(f'Nhận dữ liệu mới cho tháng {m}: {tm[m].name}, {fm[m].name}')
    months = sorted(p.name for p in WORK.iterdir() if p.is_dir() and re.fullmatch(r'\d{4}-\d{2}', p.name))
    if not months:
        sys.exit('LỖI: chưa có dữ liệu. Hãy tải 2 file TMS Order Detail và Fill Rate vào input/.')
    cur = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m')   # tháng hiện tại (giờ Việt Nam)
    done = [m for m in months if m < cur][-DONE_SHOWN:]
    live = [m for m in months if m >= cur][-1:]
    shown = done + live
    (ROOT / 'build').mkdir(exist_ok=True)
    (ROOT / 'build' / 'months_meta.json').write_text(json.dumps(dict(shown=shown, completed=done, current=live[0] if live else None)))
    print('Có dữ liệu các tháng:', ', '.join(months), '· hoàn thành hiển thị:', ', '.join(done) or '—', '· đang chạy:', ', '.join(live) or '—')
    # 3. tính KPI từng tháng
    for m in shown:
        r = subprocess.run([sys.executable, str(ROOT / 'engine' / 'compute.py'), str(WORK / m), str(BUILD / f'{m}.json')])
        if r.returncode: sys.exit(f'LỖI khi tính tháng {m}.')
    CHANGED.write_text('\n'.join(sorted(changed)))

def save():
    VAULT.mkdir(parents=True, exist_ok=True)
    changed = [m for m in (CHANGED.read_text().split() if CHANGED.exists() else []) if m]
    for m in changed:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted((WORK / m).glob('*.xlsx')): z.write(p, p.name)
        (VAULT / f'{m}.enc').write_bytes(encrypt(buf.getvalue()))
        print(f'Đã lưu kho mã hoá tháng {m}')
    legacy = INPUT / 'last_data.enc'
    if legacy.exists(): legacy.unlink()

{'prepare': prepare, 'save': save}.get(sys.argv[1] if len(sys.argv) > 1 else '', lambda: sys.exit('Cách dùng: python engine/run.py prepare|save'))()
