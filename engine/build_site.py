"""Dựng trang dashboard GHCM đã mã hoá từ build/months/<YYYY-MM>.json -> docs/.

Ba loại tài khoản:
  admin                      xem toàn GHCM, mọi Vùng, mọi NPP + tab Data Quality
  Vùng (Region)              tên đăng nhập là tên vùng viết liền, ví dụ hcmzone1, hcmzone5, southeast
                             (gõ zone1, se cũng được) — chỉ thấy NPP thuộc vùng mình
  NPP                        tên đăng nhập là mã NPP (DisCode trong Fill Rate); gõ tên NPP (ví dụ P141) cũng được

Mật khẩu lấy từ biến môi trường (GitHub Secrets):
  ADMIN_PASSWORD    mật khẩu admin
  NPP_PASSWORD      mật khẩu chung cho mọi NPP
  NPP_PASSWORDS     (tuỳ chọn) JSON {"P141": "...", ...} mật khẩu riêng từng NPP
  REGION_PASSWORD   (tuỳ chọn) mật khẩu chung cho tài khoản Vùng; không đặt thì không tạo tài khoản Vùng
  REGION_PASSWORDS  (tuỳ chọn) JSON {"HCM Zone 1": "...", ...} mật khẩu riêng từng Vùng

GHCM có nhiều NPP nên mỗi tài khoản là một file mã hoá riêng (docs/data/<mã băm>.bin).
Trang chỉ tải file của người đăng nhập, nên index.html nhẹ dù dữ liệu lớn.
"""
import base64, gzip, hashlib, json, os, re, shutil, sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parents[1]
ITER = 200_000
SALT_ID = 'ghcm-tms:'          # băm tên đăng nhập -> tên file, trùng với template.html

files = sorted((ROOT / 'build' / 'months').glob('*.json'))
if not files:
    sys.exit('LỖI: chưa có dữ liệu tháng nào trong build/months/. Chạy engine/run.py prepare trước.')
MM = json.load(open(ROOT / 'build' / 'months_meta.json')) if (ROOT / 'build' / 'months_meta.json').exists() else {}
MONTHS = {f.stem: json.load(open(f, encoding='utf-8')) for f in files if not MM or f.stem in MM['shown']}
ORDER = sorted(MONTHS)
DONE = [m for m in MM.get('completed', ORDER) if m in MONTHS]   # tháng đã hoàn thành
CUR = MM.get('current')
auth = {}
for d in MONTHS.values():
    auth.update(d.pop('auth'))       # mã đăng nhập NPP (DisCode) — không đưa vào trang
NPPS = sorted(auth)
dup = {}
for n, c in auth.items(): dup.setdefault(c, []).append(n)
for c, ns in dup.items():
    if len(ns) > 1: print(f'Cảnh báo: nhiều NPP dùng chung mã {c}: {", ".join(ns)} — tài khoản này chỉ mở được NPP cuối cùng.')
REGIONS = sorted({r for d in MONTHS.values() for r in d.get('regions', {})})

admin_pw = os.environ.get('ADMIN_PASSWORD', '').strip()
npp_pw = json.loads(os.environ.get('NPP_PASSWORDS', '') or '{}')
common_pw = os.environ.get('NPP_PASSWORD', '').strip()
reg_pw = json.loads(os.environ.get('REGION_PASSWORDS', '') or '{}')
reg_common = os.environ.get('REGION_PASSWORD', '').strip()
if not admin_pw:
    sys.exit('LỖI: chưa đặt secret ADMIN_PASSWORD. Vào Settings → Secrets and variables → Actions để thêm.')
warn = []
for n in NPPS:
    if not str(npp_pw.get(n, '')).strip():
        if common_pw: npp_pw[n] = common_pw
        else: npp_pw[n] = auth[n]; warn.append(n)
if warn:
    print('Cảnh báo: chưa đặt NPP_PASSWORD, dùng DisCode làm mật khẩu cho', ', '.join(warn))


def b64(b): return base64.b64encode(b).decode()


def seal(obj, password):
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(password.strip().encode())
    raw = gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode(), 9)
    return b'GHCM1' + salt + iv + AESGCM(key).encrypt(iv, raw, None)


def fid(user):
    return hashlib.sha256((SALT_ID + user.strip().lower()).encode()).hexdigest()[:24]


def reg_login(r):
    """HCM Zone 1 -> hcmzone1 ; South East -> southeast"""
    return re.sub(r'[^a-z0-9]', '', r.lower())


def reg_alias(r):
    a = {reg_login(r)}
    z = re.search(r'zone\s*(\d+)', r, re.I)
    if z: a |= {f'zone{z.group(1)}', f'z{z.group(1)}'}
    a.add(''.join(w[0] for w in r.lower().split()))           # South East -> se
    return a


def slice_for(data, keep_npps, total, key):
    """Giữ dữ liệu của một nhóm NPP trong một tháng. key: khoá daily/geo/hours dùng làm 'ALL'."""
    S = set(keep_npps)
    d = {k: v for k, v in data.items() if k not in ('dq', 'sens')}
    keep = lambda rows: [r for r in rows if (r.get('npp') or r.get('TenantName')) in S]
    ti = data['err_keys'].index('TenantName')
    sub = lambda obj: {**{n: obj[n] for n in keep_npps if n in obj}, 'ALL': obj[key],
                       **{k: v for k, v in obj.items() if k.startswith('R:') and k == 'R:' + total.get('npp', '')}}
    d.update(npps=list(keep_npps), scorecard=[s for s in data['scorecard'] if s['npp'] in S], total=total,
             npp_info={n: data['npp_info'][n] for n in keep_npps},
             errors=[e for e in data['errors'] if e[ti] in S],
             daily=sub(data['daily']), geo_dist=sub(data['geo_dist']), hours=sub(data['hours']),
             users={'ALL': keep(data['users']['ALL'])},
             dt_top=keep(data['dt_top']), pl_top=keep(data['pl_top']), cd_list=keep(data['cd_list']),
             plan_list=keep(data['plan_list']), late_list=keep(data.get('late_list', [])))
    d['regions'] = {r: v for r, v in data.get('regions', {}).items() if r == total.get('npp')}
    d['meta'] = dict(data['meta'], npps=len(keep_npps), regions=list(d['regions']))
    return d


out = ROOT / 'docs'
shutil.rmtree(out / 'data', ignore_errors=True)
(out / 'data').mkdir(parents=True, exist_ok=True)
logins = {}


def put(user, obj, password):
    (out / 'data' / f'{fid(user)}.bin').write_bytes(seal(obj, password))
    logins[user] = True


put('admin', dict(__role='admin', order=ORDER, completed=DONE, current=CUR, months=MONTHS), admin_pw)
alias = {}
# tài khoản Vùng
made_regions = []
for r in REGIONS:
    pw = str(reg_pw.get(r, '') or reg_common).strip()
    if not pw: continue
    mine = {}
    for m, d in MONTHS.items():
        if r not in d.get('regions', {}): continue
        ns = [n for n in d['npps'] if d['npp_info'][n]['region'] == r]
        mine[m] = slice_for(d, ns, d['regions'][r], 'R:' + r)
    if not mine: continue
    u = reg_login(r)
    put(u, dict(__role='R:' + r, order=sorted(mine), completed=[m for m in DONE if m in mine],
                current=CUR if CUR in mine else None, months=mine), pw)
    for a in reg_alias(r) - {u}: alias[a] = u
    made_regions.append(u)
if not made_regions:
    print('Ghi chú: chưa đặt REGION_PASSWORD nên chưa tạo tài khoản Vùng.')
# tài khoản NPP
for n in NPPS:
    mine = {}
    for m, d in MONTHS.items():
        if n not in d['npps']: continue
        row = next(s for s in d['scorecard'] if s['npp'] == n)
        x = slice_for(d, [n], row, n)
        x['daily'][n] = x['daily']['ALL']
        mine[m] = x
    put(auth[n], dict(__role=n, order=sorted(mine), completed=[m for m in DONE if m in mine],
                      current=CUR if CUR in mine else None, months=mine), npp_pw[n])
    if n.lower() != auth[n].lower(): alias[n.lower()] = auth[n]   # gõ tên NPP cũng mở được

last = MONTHS[ORDER[-1]]['meta']
enc = dict(iter=ITER, salt_id=SALT_ID, period=', '.join(f'T{int(m[5:])}/{m[:4]}' for m in ORDER), built=last['built'],
           alias=alias, regions=[dict(name=r, login=reg_login(r)) for r in REGIONS if reg_login(r) in made_regions])
tpl = (ROOT / 'engine' / 'template.html').read_text(encoding='utf-8')
page = tpl.replace('/*__ENC__*/', json.dumps(enc, ensure_ascii=False).replace('</', '<\\/'))
head = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta name="robots" content="noindex,nofollow"></head><body>')
(out / 'index.html').write_text(head + page + '</body></html>', encoding='utf-8')
(out / '.nojekyll').write_text('')
size = sum(p.stat().st_size for p in (out / 'data').glob('*.bin')) / 1024 / 1024
adm = (out / 'data' / f'{fid("admin")}.bin').stat().st_size / 1024 / 1024
print(f'Đã dựng docs/index.html ({(out / "index.html").stat().st_size/1024:,.0f} KB) · tháng: {", ".join(ORDER)} · '
      f'{len(logins)} tài khoản ({len(made_regions)} Vùng, {len(NPPS)} NPP) · dữ liệu {size:,.1f} MB, admin {adm:,.1f} MB.')
