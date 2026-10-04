# GHCM TMS Data Accuracy

Dashboard KPI Data Accuracy cho toàn **Greater HCM**: 6 vùng (HCM Zone 1–5, South East), từng NPP, chi tiết đến từng đơn, từng chuyến. Logic chấm giữ nguyên repo `tms-data-accuracy`, thêm lớp **Vùng** và tài khoản cho quản lý vùng.

## Cập nhật dữ liệu hằng tháng

1. Mở thư mục **`input/`** trên trang GitHub của repo.
2. Bấm **Add file → Upload files**, kéo thả 2 file **của cùng một tháng**:
   - `GHCM_TMS_Order_Detail_YYYYMM.xlsx` (tên có chữ `TMS`)
   - `Fill_Rate_YYYYMM.xlsx` (tên có chữ `Fill`)
3. Bấm **Commit changes**. Khoảng 3–5 phút sau trang tự cập nhật (dấu ✓ xanh ở tab **Actions**).

- Workflow tự nhận tháng từ cột `Date` của file TMS và tự dò dòng tiêu đề (file Power BI có 1–3 dòng "Applied filters" phía trên).
- Mỗi lần chỉ tải 2 file của **một** tháng. Nạp nhiều tháng: tải lần lượt, đợi lần trước chạy xong.
- Tải lại giữa tháng thì dữ liệu tháng đó được thay bằng file mới; tháng cũ vẫn được giữ.
- Trang hiển thị **3 tháng đã hoàn thành gần nhất + tháng đang chạy**; tab **3 tháng** chỉ tổng hợp các tháng đã hoàn thành. Trang tự dựng lại lúc 10:00 mỗi ngày.
- GitHub giới hạn **25 MB/file** khi tải qua web. File TMS lớn hơn: xoá bớt cột không dùng (`Picked_LatLong`, `BI_Calculated_Distance`, `distance_drop_drop`, `new_geocompliant`…) trước khi tải.

**Loại trừ ngày:** khai báo trong `engine/config.json` (`exclude_dates`). Đơn có `Date` trong khoảng này bị loại khỏi toàn bộ KPI. Hiện đang loại trừ 16/09–23/09/2026 (lỗi hệ thống do update Portal 4X).

## Cài đặt lần đầu (làm một lần)

1. **Tạo repo** `ghcm-tms-data-accuracy` trên GitHub, tải toàn bộ nội dung thư mục này lên (gồm cả thư mục ẩn `.github/`).
2. **Đặt mật khẩu** — Settings → Secrets and variables → Actions → New repository secret:

   | Secret | Bắt buộc | Dùng cho |
   |---|---|---|
   | `ADMIN_PASSWORD` | Có | Tài khoản `admin`, đồng thời là khoá kho dữ liệu mã hoá |
   | `NPP_PASSWORD` | Có | Mật khẩu chung cho mọi NPP, ví dụ `User@123` |
   | `REGION_PASSWORD` | Nên có | Mật khẩu chung cho tài khoản Vùng. Không đặt thì không tạo tài khoản Vùng |
   | `NPP_PASSWORDS` | Tuỳ chọn | Mật khẩu riêng từng NPP, JSON `{"P141":"...","DN24":"..."}` |
   | `REGION_PASSWORDS` | Tuỳ chọn | Mật khẩu riêng từng Vùng, JSON `{"HCM Zone 1":"...","South East":"..."}` |

3. **Bật trang web** — Settings → Pages → Build and deployment → Source: **GitHub Actions**.
4. Tải 2 file dữ liệu vào `input/` như trên. Link trang ở Settings → Pages, dạng `https://<tài-khoản>.github.io/ghcm-tms-data-accuracy/`.

Đổi mật khẩu NPP/Vùng: sửa secret rồi bấm **Actions → Cập nhật dashboard GHCM → Run workflow**. Lưu ý: đổi `ADMIN_PASSWORD` thì kho cũ không mở được, cần tải lại dữ liệu các tháng.

## Đăng nhập

| Tài khoản | Tên đăng nhập | Thấy gì |
|---|---|---|
| Admin | `admin` | Toàn GHCM, mọi Vùng, mọi NPP + tab Data Quality |
| Vùng | `hcmzone1` … `hcmzone5`, `southeast` (gõ `zone1`, `z1`, `se` cũng được) | Các NPP thuộc vùng mình, tổng hợp vùng |
| NPP | Mã NPP (DisCode), gõ tên NPP như `P141` cũng được | Chỉ dữ liệu NPP đó |

NPP không ghép được với Fill Rate (không có DisCode) đăng nhập bằng tên NPP (TenantName).

## Cách chấm (giữ nguyên repo gốc)

**Kết quả tháng = đạt cả 4 tiêu chí:**

| Tiêu chí | Lỗi | NPP đạt khi |
|---|---|---|
| Payload | chuyến có tổng tải / tải trọng xe ≥ 1,5 | chuyến quá tải < 5% tổng chuyến |
| Distance & Time | đơn có `time_outlet_outlet` < 2 phút và cách outlet trước > 10m; chuyến hỏng khi đơn lỗi > 30%; **không tính đơn tài khoản DSA** | chuyến hỏng < 5% tổng chuyến (không tính chuyến chỉ có DSA) |
| Created Date | đơn tạo (Fill Rate `Sent_To_distributor`, ghép `DocNo = OrderNumber`) sau giờ giao; 1 đơn lỗi là chuyến lỗi | 0 chuyến lỗi |
| User name | tài khoản không phải SĐT, biển số xe hoặc DSA | 0 tài khoản sai |

**Năng lực giao hàng (không tính là lỗi):** On time `is_ontime` (tham chiếu > 95%), On time 24H (tham chiếu > 95%; chốt 17:00, thứ 7 sau 17:00 sang thứ 2, trừ Chủ nhật nếu không giao Chủ nhật, giao sau 20:00 là chưa đạt).

**Chỉ số theo dõi:** Geo Compliance (≥ 85%), Chuyến lỗi > 30% (≤ 5% chuyến), Đơn duyệt bởi DSA.

**Vùng:** vùng của NPP lấy theo cột `Region` của file TMS (giá trị xuất hiện nhiều nhất). Kết quả vùng = số NPP đạt / tổng NPP của vùng; các tỷ lệ (Payload, D&T, On time…) của vùng tính trên toàn bộ đơn, chuyến của vùng.

## Khác biệt so với repo `tms-data-accuracy`

- Đọc đúng định dạng file GHCM: cột `Name` (thay `DriverName`), dòng tiêu đề thay đổi, ngày dạng số seri Excel, mã đơn dạng số, SĐT bị mất số 0 đầu.
- Thêm lớp Vùng: bảng **Kết quả theo Vùng**, NPP nhóm theo vùng, ô chọn Vùng/NPP, bảng vùng qua các tháng, cột Vùng trong file Excel đơn lỗi.
- Thêm tài khoản Vùng.
- Mỗi tài khoản là một file mã hoá riêng `docs/data/<mã>.bin`, trang chỉ tải file của người đăng nhập nên mở nhanh dù GHCM có nhiều NPP.

## Bảo mật

Dữ liệu được mã hoá AES-GCM, khoá dẫn xuất PBKDF2-SHA256 (200.000 vòng) từ mật khẩu. Mỗi tài khoản chỉ giải mã được file của mình; xem mã nguồn trang cũng không đọc được số liệu. Mật khẩu không nằm trong repo. Kho dữ liệu gốc lưu mã hoá trong `input/vault/`; nếu repo công khai, workflow xoá file Excel thô khỏi `input/` sau khi xử lý (file vẫn còn trong lịch sử commit — muốn kín hoàn toàn, chuyển repo sang **Private**, cần gói GitHub Pro/Team cho Pages).

## Cấu trúc

```
input/                  nơi tải 2 file Excel lên
input/vault/            kho dữ liệu mã hoá, mỗi tháng một file
engine/xlio.py          đọc file Power BI: dò tiêu đề, chuẩn hoá ngày / mã
engine/compute.py       tính toàn bộ KPI theo NPP và Vùng -> build/months/<YYYY-MM>.json
engine/run.py           nhận tháng, lưu / mở kho mã hoá, tính KPI từng tháng
engine/build_site.py    mã hoá dữ liệu theo tài khoản, dựng docs/
engine/template.html    giao diện dashboard
engine/config.json      loại trừ ngày, số tháng hiển thị
.github/workflows/      workflow tự chạy khi có file mới
```

Chạy trên máy: `pip install -r requirements.txt`, đặt 2 file vào `input/`, rồi

```
export ADMIN_PASSWORD=... NPP_PASSWORD=... REGION_PASSWORD=...
python engine/run.py prepare && python engine/build_site.py
python -m http.server -d docs
```

Mở `http://localhost:8000` (trang cần chạy qua web server, không mở trực tiếp file).
