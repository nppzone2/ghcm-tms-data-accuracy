"""Đọc file Excel xuất từ Power BI (TMS Order Detail, Fill Rate) cho GHCM.

File xuất có 1–3 dòng "Applied filters" phía trên tiêu đề, vị trí dòng tiêu đề thay đổi theo tháng,
nên tự dò dòng tiêu đề thay vì cố định header=2.
"""
import re
import pandas as pd

KEYS = {'OrderNumber', 'DocNo', 'PlanNumber', 'TenantName', 'Sent_To_distributor'}
EXCEL_EPOCH = pd.Timestamp('1899-12-30')


def header_row(path, scan=12):
    """Trả về chỉ số dòng tiêu đề (0-based) trong `scan` dòng đầu."""
    head = pd.read_excel(path, header=None, nrows=scan)
    for i, row in head.iterrows():
        vals = {str(v).strip() for v in row.tolist() if pd.notna(v)}
        if len(vals & KEYS) >= 1 and len(vals) >= 5:
            return i
    raise SystemExit(f'LỖI: không tìm thấy dòng tiêu đề trong {getattr(path, "name", path)} '
                     f'(cần cột OrderNumber hoặc DocNo).')


def read_export(path, **kw):
    df = pd.read_excel(path, header=header_row(path), **kw)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how='all')


def to_dt(s):
    """Chuẩn hoá cột ngày giờ: nhận datetime, chuỗi, hoặc số seri Excel (46266.5 ...)."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    num = pd.to_numeric(s, errors='coerce')
    if num.notna().sum() >= max(1, s.notna().sum() * 0.9):
        return EXCEL_EPOCH + pd.to_timedelta(num, unit='D')
    return pd.to_datetime(s, errors='coerce', dayfirst=False)


def idstr(s):
    """Mã đơn / chuyến về chuỗi, bỏ đuôi .0 khi Excel lưu dạng số."""
    def one(v):
        if pd.isna(v):
            return ''
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip()
    return s.map(one)


def username_str(s):
    """Tài khoản giao hàng về chuỗi; SĐT bị Excel lưu dạng số (mất số 0 đầu) thì thêm lại."""
    def one(v):
        if pd.isna(v):
            return ''
        if isinstance(v, (int, float)) and float(v).is_integer():
            v = str(int(v))
            return '0' + v if re.fullmatch(r'[35789]\d{8}', v) else v
        return str(v).strip()
    return s.map(one)
